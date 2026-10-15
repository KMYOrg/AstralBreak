#include "AnimMcpOperations.h"

#include "AnimGraphNode_Base.h"
#include "AnimMcpAssetResolver.h"
#include "AnimMcpCompiler.h"
#include "AnimMcpGraphInspector.h"
#include "AnimMcpGraphMutator.h"
#include "AnimMcpLog.h"
#include "AnimMcpPropertyRules.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimationAsset.h"
#include "Bridge/AnimMcpTypes.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "ScopedTransaction.h"

#define LOCTEXT_NAMESPACE "AnimGraphMcp"

namespace AnimMcpOperations
{
	namespace
	{
		/** 핀 하나의 링크 상태 — 포인터가 아니라 (노드, 핀 이름). ReconstructNode 뒤에도 유효 */
		struct FPinLinks
		{
			UEdGraphNode* Node = nullptr;
			FName Pin;
			TArray<TPair<UEdGraphNode*, FName>> Linked;
		};

		FPinLinks SnapshotPin(UEdGraphPin* Pin)
		{
			FPinLinks Out;
			Out.Node = Pin->GetOwningNode();
			Out.Pin = Pin->PinName;
			for (UEdGraphPin* Other : Pin->LinkedTo)
			{
				if (Other && Other->GetOwningNodeUnchecked())
				{
					Out.Linked.Emplace(Other->GetOwningNodeUnchecked(), Other->PinName);
				}
			}
			return Out;
		}

		/** 스냅샷 복원 — 현재 링크를 다 끊고 기록된 상대와 다시 잇는다. MakeLinkTo 는 양방향이라 상대 핀의 LinkedTo 도 함께 맞는다 */
		void RestorePin(const FPinLinks& Snapshot)
		{
			UEdGraphPin* Pin = Snapshot.Node ? Snapshot.Node->FindPin(Snapshot.Pin) : nullptr;
			if (!Pin)
			{
				return;
			}
			Snapshot.Node->Modify();
			Pin->BreakAllPinLinks(/*bNotifyNodes*/ true);
			for (const TPair<UEdGraphNode*, FName>& Other : Snapshot.Linked)
			{
				UEdGraphPin* OtherPin = Other.Key ? Other.Key->FindPin(Other.Value) : nullptr;
				if (OtherPin)
				{
					Other.Key->Modify();
					Pin->MakeLinkTo(OtherPin);
				}
			}
		}

		/** 배치 실행 중 상태 — ref 표, 되돌리기 저널, 성공 확정 시 처리할 것 */
		struct FBatchState
		{
			UAnimBlueprint* Blueprint = nullptr;
			TMap<FString, UEdGraphNode*> Refs;
			/** Preview 전용 — 아직 만들어지지 않은 ref 와 그 클래스 (핀 검증을 미룬다) */
			TMap<FString, UClass*> PendingRefClasses;
			/** 이 배치에서 remove_node 된 노드 (뒤 op 가 가리키면 거부) */
			TSet<UEdGraphNode*> Removed;

			/** 되돌리기 — 적용 순서대로 쌓고 역순으로 실행 */
			TArray<TFunction<void()>> Undo;
			/** 분리 보관된 노드 — 배치 성공 시 DestroyNode 로 확정 */
			TArray<UEdGraphNode*> Detached;
		};

		void RollbackBatch(FBatchState& State)
		{
			for (int32 i = State.Undo.Num() - 1; i >= 0; --i)
			{
				State.Undo[i]();
			}
			State.Undo.Empty();
			State.Detached.Empty();
		}

		TSharedPtr<FJsonObject> GetObjectField(const TSharedPtr<FJsonObject>& Json, const TCHAR* Key)
		{
			const TSharedPtr<FJsonObject>* Obj = nullptr;
			return (Json.IsValid() && Json->TryGetObjectField(Key, Obj) && Obj) ? *Obj : nullptr;
		}

		/** {node:"guid"} | {ref:"name"} | "guid" → 노드. ref 가 아직 미생성(Preview)이면 bOutPending. 이 배치에서 제거된 노드는 거부 */
		UEdGraphNode* ResolveNodeRef(FBatchState& State, const TSharedPtr<FJsonValue>& Value, bool& bOutPending, FAnimMcpError& OutError)
		{
			bOutPending = false;
			if (!Value.IsValid())
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("Node reference missing"));
				return nullptr;
			}
			FString Guid, Ref;
			if (Value->Type == EJson::String)
			{
				Guid = Value->AsString();
			}
			else if (Value->Type == EJson::Object)
			{
				Value->AsObject()->TryGetStringField(TEXT("node"), Guid);
				Value->AsObject()->TryGetStringField(TEXT("ref"), Ref);
			}

			UEdGraphNode* Node = nullptr;
			if (!Ref.IsEmpty())
			{
				if (UEdGraphNode** Found = State.Refs.Find(Ref))
				{
					Node = *Found;
				}
				else if (State.PendingRefClasses.Contains(Ref))
				{
					bOutPending = true;
					return nullptr;
				}
				else
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("ref '%s' is not defined by an earlier add_node in this batch"), *Ref));
					return nullptr;
				}
			}
			else if (!Guid.IsEmpty())
			{
				Node = AnimMcpGraphMutator::FindNode(State.Blueprint, Guid, OutError);
				if (!Node)
				{
					return nullptr;
				}
			}
			else
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("Node reference needs 'node' (guid) or 'ref'"));
				return nullptr;
			}

			if (State.Removed.Contains(Node))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::NodeNotFound, FString::Printf(TEXT("Node %s is removed earlier in this batch"), *Node->NodeGuid.ToString()));
				return nullptr;
			}
			return Node;
		}

		/** op 객체 자체가 {node|ref} 를 갖는 경우 (remove_node · set_property · set_asset · expose_pin · add_blend_pose) */
		UEdGraphNode* ResolveOpTarget(FBatchState& State, const FOperation& Op, bool& bOutPending, UClass*& OutPendingClass, FAnimMcpError& OutError)
		{
			OutPendingClass = nullptr;
			UEdGraphNode* Node = ResolveNodeRef(State, MakeShared<FJsonValueObject>(Op.Json), bOutPending, OutError);
			if (bOutPending)
			{
				FString Ref;
				Op.Json->TryGetStringField(TEXT("ref"), Ref);
				OutPendingClass = State.PendingRefClasses.FindRef(Ref);
			}
			return Node;
		}

		//~ add_node

		struct FAddNodeArgs
		{
			UEdGraph* Graph = nullptr;
			UClass* NodeClass = nullptr;
			UAnimationAsset* Asset = nullptr;
			UEnum* Enum = nullptr;
			FVector2D Position = FVector2D::ZeroVector;
			TSharedPtr<FJsonObject> Properties;
		};

		bool ResolveAddNode(FBatchState& State, const FOperation& Op, FAddNodeArgs& Out, FAnimMcpContext& Context, FAnimMcpError& OutError)
		{
			FString GraphGuid;
			if (Op.Json->TryGetStringField(TEXT("graph"), GraphGuid) && !GraphGuid.IsEmpty())
			{
				Out.Graph = AnimMcpGraphMutator::FindGraph(State.Blueprint, GraphGuid, OutError);
			}
			else
			{
				Out.Graph = AnimMcpGraphInspector::FindRootAnimGraph(State.Blueprint);
				if (!Out.Graph)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::GraphNotFound, TEXT("Blueprint has no root AnimGraph and no 'graph' was given"));
				}
			}
			if (!Out.Graph)
			{
				return false;
			}

			FString ClassName;
			if (!Op.Json->TryGetStringField(TEXT("class"), ClassName) || ClassName.IsEmpty())
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("add_node requires 'class'"));
				return false;
			}
			Out.NodeClass = AnimMcpGraphMutator::ResolveNodeClass(ClassName, OutError);
			if (!Out.NodeClass)
			{
				return false;
			}

			const TArray<TSharedPtr<FJsonValue>>* Pos = nullptr;
			if (Op.Json->TryGetArrayField(TEXT("pos"), Pos) && Pos && Pos->Num() == 2)
			{
				Out.Position.X = (*Pos)[0]->AsNumber();
				Out.Position.Y = (*Pos)[1]->AsNumber();
			}

			FString AssetPath;
			if (Op.Json->TryGetStringField(TEXT("asset"), AssetPath) && !AssetPath.IsEmpty())
			{
				Out.Asset = AnimMcpAssetResolver::LoadAnimationAsset(AssetPath, OutError);
				if (!Out.Asset || !AnimMcpGraphMutator::ValidateNodeAsset(Out.NodeClass, Out.Asset, State.Blueprint, Context, OutError))
				{
					return false;
				}
			}

			FString EnumPath;
			if (Op.Json->TryGetStringField(TEXT("enum"), EnumPath) && !EnumPath.IsEmpty())
			{
				if (Out.NodeClass->GetName() != TEXT("AnimGraphNode_BlendListByEnum"))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("'enum' is only accepted for AnimGraphNode_BlendListByEnum"));
					return false;
				}
				Out.Enum = FindObject<UEnum>(nullptr, *EnumPath);
				if (!Out.Enum)
				{
					Out.Enum = LoadObject<UEnum>(nullptr, *EnumPath);
				}
				if (!Out.Enum)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetNotFound, FString::Printf(TEXT("Enum '%s' not found (use a full path like /Script/Engine.EAlphaBlendOption or /Game/.../E_MyEnum.E_MyEnum)"), *EnumPath));
					return false;
				}
			}

			Out.Properties = GetObjectField(Op.Json, TEXT("properties"));
			if (Out.Properties.IsValid())
			{
				for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : Out.Properties->Values)
				{
					if (!AnimMcpGraphMutator::ValidatePropertyOnClass(Out.NodeClass, FName(*Pair.Key), Pair.Value, OutError))
					{
						return false;
					}
					if (const AnimMcpPropertyRules::FRule* Rule = AnimMcpPropertyRules::Find(Out.NodeClass, FName(*Pair.Key)); Rule && Rule->Scope == AnimMcpPropertyRules::EScope::NodeRef)
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' is a node reference; set it with a separate set_property after the node exists"), *Pair.Key));
						return false;
					}
				}
			}
			return true;
		}

		//~ connect / disconnect

		struct FEndpointArgs
		{
			UEdGraphPin* From = nullptr;
			UEdGraphPin* To = nullptr;
			bool bHasTo = false;
			/** Preview 에서 ref 가 아직 없어 핀 검증을 건너뛴 경우 */
			bool bDeferred = false;
		};

		bool ResolveEndpoints(FBatchState& State, const FOperation& Op, bool bToRequired, FEndpointArgs& Out, FAnimMcpError& OutError)
		{
			const TSharedPtr<FJsonObject> From = GetObjectField(Op.Json, TEXT("from"));
			const TSharedPtr<FJsonObject> To = GetObjectField(Op.Json, TEXT("to"));
			Out.bHasTo = To.IsValid();
			if (!From.IsValid() || (bToRequired && !To.IsValid()))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("%s requires 'from'%s objects {node|ref, pin}"), *Op.Op, bToRequired ? TEXT(" and 'to'") : TEXT(" (and optional 'to')")));
				return false;
			}
			FString FromPin, ToPin;
			if (!From->TryGetStringField(TEXT("pin"), FromPin) || (To.IsValid() && !To->TryGetStringField(TEXT("pin"), ToPin)))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("endpoints need 'pin'"));
				return false;
			}

			bool bFromPending = false, bToPending = false;
			UEdGraphNode* FromNode = ResolveNodeRef(State, MakeShared<FJsonValueObject>(From), bFromPending, OutError);
			if (!FromNode && !bFromPending)
			{
				return false;
			}
			UEdGraphNode* ToNode = nullptr;
			if (To.IsValid())
			{
				ToNode = ResolveNodeRef(State, MakeShared<FJsonValueObject>(To), bToPending, OutError);
				if (!ToNode && !bToPending)
				{
					return false;
				}
			}
			if (bFromPending || bToPending)
			{
				Out.bDeferred = true;
				return true;
			}

			Out.From = AnimMcpGraphMutator::FindPin(FromNode, FromPin, OutError);
			if (!Out.From)
			{
				return false;
			}
			if (ToNode)
			{
				Out.To = AnimMcpGraphMutator::FindPin(ToNode, ToPin, OutError);
				if (!Out.To)
				{
					return false;
				}
			}
			return true;
		}

		//~ 결과 항목

		TSharedRef<FJsonObject> MakePlanned(const FOperation& Op, bool bOk, const FAnimMcpError* Error, const TCHAR* Note = nullptr)
		{
			TSharedRef<FJsonObject> P = AnimMcpJson::MakeObject();
			P->SetNumberField(TEXT("index"), Op.Index);
			P->SetStringField(TEXT("op"), Op.Op);
			P->SetField(TEXT("ref"), AnimMcpJson::StringOrNull(Op.Ref));
			P->SetBoolField(TEXT("ok"), bOk);
			if (Error && Error->IsSet())
			{
				P->SetObjectField(TEXT("error"), Error->ToJson());
			}
			if (Note)
			{
				P->SetStringField(TEXT("note"), Note);
			}
			return P;
		}

		struct FCounts
		{
			int32 Create = 0, Connect = 0, Disconnect = 0, Remove = 0, Modify = 0;
		};

		const TCHAR* DeferredNote = TEXT("target node is created earlier in this batch; full check happens at apply");

		/**
		 * 공통 검증 — Preview 본체. Apply 도 적용 전에 같은 함수를 돌린다.
		 * 미생성 ref 를 가리키는 op 는 클래스 수준에서 할 수 있는 검증만 하고 나머지는 apply 로 미룬다 (note)
		 */
		bool Validate(FBatchState& State, const TArray<FOperation>& Ops, FAnimMcpContext& Context, TArray<TSharedPtr<FJsonValue>>& OutPlanned, FCounts& Counts)
		{
			bool bAllOk = true;
			for (const FOperation& Op : Ops)
			{
				FAnimMcpError Error;
				bool bOk = false;
				const TCHAR* Note = nullptr;

				if (Op.Op == TEXT("add_node"))
				{
					FAddNodeArgs Args;
					bOk = ResolveAddNode(State, Op, Args, Context, Error);
					if (bOk)
					{
						++Counts.Create;
						if (!Op.Ref.IsEmpty())
						{
							if (State.PendingRefClasses.Contains(Op.Ref) || State.Refs.Contains(Op.Ref))
							{
								bOk = false;
								Error = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("ref '%s' is defined twice in this batch"), *Op.Ref));
							}
							else
							{
								State.PendingRefClasses.Add(Op.Ref, Args.NodeClass);
							}
						}
					}
				}
				else if (Op.Op == TEXT("connect"))
				{
					FEndpointArgs Args;
					bOk = ResolveEndpoints(State, Op, /*bToRequired*/ true, Args, Error);
					if (bOk && !Args.bDeferred)
					{
						bOk = AnimMcpGraphMutator::ValidateConnection(Args.From, Args.To, Error);
					}
					if (bOk)
					{
						++Counts.Connect;
						Note = Args.bDeferred ? DeferredNote : nullptr;
					}
				}
				else if (Op.Op == TEXT("disconnect"))
				{
					FEndpointArgs Args;
					bOk = ResolveEndpoints(State, Op, /*bToRequired*/ false, Args, Error);
					if (bOk && !Args.bDeferred && Args.To)
					{
						bOk = AnimMcpGraphMutator::ValidateLinked(Args.From, Args.To, Error);
					}
					if (bOk)
					{
						++Counts.Disconnect;
						Note = Args.bDeferred ? DeferredNote : nullptr;
					}
				}
				else if (Op.Op == TEXT("remove_node"))
				{
					bool bPending = false;
					UClass* PendingClass = nullptr;
					UEdGraphNode* Node = ResolveOpTarget(State, Op, bPending, PendingClass, Error);
					if (Node)
					{
						bOk = AnimMcpGraphMutator::ValidateRemovable(Node, Error);
						if (bOk)
						{
							State.Removed.Add(Node);
						}
					}
					else if (bPending)
					{
						bOk = true;
						Note = DeferredNote;
					}
					if (bOk)
					{
						++Counts.Remove;
					}
				}
				else if (Op.Op == TEXT("set_property"))
				{
					FString PropertyName;
					if (!Op.Json->TryGetStringField(TEXT("property"), PropertyName) || PropertyName.IsEmpty())
					{
						Error = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("set_property requires 'property'"));
					}
					else
					{
						bool bPending = false;
						UClass* PendingClass = nullptr;
						UEdGraphNode* Node = ResolveOpTarget(State, Op, bPending, PendingClass, Error);
						const UClass* NodeClass = Node ? Node->GetClass() : PendingClass;
						if (NodeClass)
						{
							bOk = AnimMcpGraphMutator::ValidatePropertyOnClass(NodeClass, FName(*PropertyName), Op.Json->TryGetField(TEXT("value")), Error);
							if (bOk)
							{
								// NodeRef 값은 지금 해석 가능한지 본다 (미생성 ref 면 미룸)
								if (const AnimMcpPropertyRules::FRule* Rule = AnimMcpPropertyRules::Find(NodeClass, FName(*PropertyName)); Rule && Rule->Scope == AnimMcpPropertyRules::EScope::NodeRef)
								{
									bool bRefPending = false;
									UEdGraphNode* Target = ResolveNodeRef(State, Op.Json->TryGetField(TEXT("value")), bRefPending, Error);
									bOk = (Target != nullptr) || bRefPending;
									if (bRefPending)
									{
										Note = DeferredNote;
									}
								}
								if (bPending)
								{
									Note = DeferredNote;
								}
							}
						}
					}
					if (bOk)
					{
						++Counts.Modify;
					}
				}
				else if (Op.Op == TEXT("set_asset"))
				{
					FString AssetPath;
					bool bPending = false;
					UClass* PendingClass = nullptr;
					UEdGraphNode* Node = ResolveOpTarget(State, Op, bPending, PendingClass, Error);
					const UClass* NodeClass = Node ? Node->GetClass() : PendingClass;
					if (NodeClass)
					{
						if (!Op.Json->TryGetStringField(TEXT("asset"), AssetPath) || AssetPath.IsEmpty())
						{
							Error = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("set_asset requires 'asset'"));
						}
						else if (UAnimationAsset* Asset = AnimMcpAssetResolver::LoadAnimationAsset(AssetPath, Error))
						{
							bOk = AnimMcpGraphMutator::ValidateNodeAsset(const_cast<UClass*>(NodeClass), Asset, State.Blueprint, Context, Error);
							Note = bPending ? DeferredNote : nullptr;
						}
					}
					if (bOk)
					{
						++Counts.Modify;
					}
				}
				else if (Op.Op == TEXT("expose_pin"))
				{
					FString PropertyName;
					if (!Op.Json->TryGetStringField(TEXT("property"), PropertyName) || PropertyName.IsEmpty())
					{
						Error = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("expose_pin requires 'property'"));
					}
					else
					{
						bool bPending = false;
						UClass* PendingClass = nullptr;
						UEdGraphNode* Node = ResolveOpTarget(State, Op, bPending, PendingClass, Error);
						if (Node)
						{
							bOk = AnimMcpGraphMutator::FindOptionalPinIndex(Cast<UAnimGraphNode_Base>(Node), FName(*PropertyName), Error) != INDEX_NONE;
						}
						else if (bPending)
						{
							// CDO 의 ShowPinForProperties 는 비어 있어 이름을 확인할 수 없다 — apply 로 미룬다
							bOk = PendingClass && PendingClass->IsChildOf(UAnimGraphNode_Base::StaticClass());
							Note = DeferredNote;
						}
					}
					if (bOk)
					{
						++Counts.Modify;
					}
				}
				else if (Op.Op == TEXT("add_blend_pose"))
				{
					bool bPending = false;
					UClass* PendingClass = nullptr;
					UEdGraphNode* Node = ResolveOpTarget(State, Op, bPending, PendingClass, Error);
					const FString Entry = Op.Json->HasTypedField<EJson::String>(TEXT("entry")) ? Op.Json->GetStringField(TEXT("entry")) : FString();
					if (Node)
					{
						bOk = AnimMcpGraphMutator::ValidateAddBlendPose(Node, Entry, Error);
					}
					else if (bPending)
					{
						const FString ClassName = PendingClass ? PendingClass->GetName() : FString();
						bOk = (ClassName == TEXT("AnimGraphNode_LayeredBoneBlend") || ClassName == TEXT("AnimGraphNode_BlendListByEnum"));
						if (!bOk)
						{
							Error = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("add_blend_pose supports LayeredBoneBlend and BlendListByEnum, not %s"), *ClassName));
						}
						Note = DeferredNote;
					}
					if (bOk)
					{
						++Counts.Modify;
					}
				}
				else
				{
					Error = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Unknown op '%s' (supported: add_node, connect, disconnect, remove_node, set_property, set_asset, expose_pin, add_blend_pose)"), *Op.Op));
				}

				bAllOk &= bOk;
				OutPlanned.Add(MakeShared<FJsonValueObject>(MakePlanned(Op, bOk, &Error, Note)));
			}
			return bAllOk;
		}

		//~ Apply 단계별 실행 — 성공하면 되돌리기를 저널에 넣는다

		bool ApplyAddNode(FBatchState& State, const FOperation& Op, FAnimMcpContext& Context, TSharedRef<FJsonObject>& Entry, FAnimMcpError& Error)
		{
			FAddNodeArgs Args;
			if (!ResolveAddNode(State, Op, Args, Context, Error))
			{
				return false;
			}
			UAnimGraphNode_Base* Node = AnimMcpGraphMutator::AddNode(Args.Graph, Args.NodeClass, Args.Position, Args.Asset, Error);
			if (!Node)
			{
				return false;
			}
			// 만든 노드는 되돌릴 때 통째로 지운다 — 그 위의 enum·properties 는 별도 되돌리기가 필요 없다
			State.Undo.Add([Node]()
			{
				if (UEdGraph* Graph = Node->GetGraph())
				{
					Graph->Modify();
				}
				Node->Modify();
				Node->BreakAllNodeLinks();
				Node->DestroyNode();
			});
			if (!Op.Ref.IsEmpty())
			{
				State.Refs.Add(Op.Ref, Node);
			}
			Entry->SetStringField(TEXT("node_guid"), Node->NodeGuid.ToString());

			if (Args.Enum && !AnimMcpGraphMutator::SetBlendListEnum(Node, Args.Enum, Error))
			{
				return false;
			}
			if (Args.Properties.IsValid())
			{
				for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : Args.Properties->Values)
				{
					FString OldText;
					if (!AnimMcpGraphMutator::SetPropertyFromJson(Node, FName(*Pair.Key), Pair.Value, OldText, Error))
					{
						return false;
					}
				}
			}
			return true;
		}

		bool ApplyConnect(FBatchState& State, const FOperation& Op, FAnimMcpError& Error)
		{
			FEndpointArgs Args;
			if (!ResolveEndpoints(State, Op, /*bToRequired*/ true, Args, Error))
			{
				return false;
			}
			if (Args.bDeferred)
			{
				Error = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("connect endpoint unresolved at apply time"));
				return false;
			}
			const FPinLinks FromBefore = SnapshotPin(Args.From);
			const FPinLinks ToBefore = SnapshotPin(Args.To);
			if (!AnimMcpGraphMutator::Connect(Args.From, Args.To, Error))
			{
				return false;
			}
			State.Undo.Add([FromBefore, ToBefore]()
			{
				RestorePin(FromBefore);
				RestorePin(ToBefore);
			});
			return true;
		}

		bool ApplyDisconnect(FBatchState& State, const FOperation& Op, FAnimMcpError& Error)
		{
			FEndpointArgs Args;
			if (!ResolveEndpoints(State, Op, /*bToRequired*/ false, Args, Error))
			{
				return false;
			}
			if (Args.bDeferred)
			{
				Error = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("disconnect endpoint unresolved at apply time"));
				return false;
			}
			const FPinLinks FromBefore = SnapshotPin(Args.From);
			if (Args.To)
			{
				if (!AnimMcpGraphMutator::Disconnect(Args.From, Args.To, Error))
				{
					return false;
				}
			}
			else
			{
				AnimMcpGraphMutator::DisconnectAll(Args.From);
			}
			State.Undo.Add([FromBefore]() { RestorePin(FromBefore); });
			return true;
		}

		bool ApplyRemoveNode(FBatchState& State, const FOperation& Op, FAnimMcpError& Error)
		{
			bool bPending = false;
			UClass* PendingClass = nullptr;
			UEdGraphNode* Node = ResolveOpTarget(State, Op, bPending, PendingClass, Error);
			if (!Node || !AnimMcpGraphMutator::ValidateRemovable(Node, Error))
			{
				return false;
			}
			UEdGraph* Graph = Node->GetGraph();
			TArray<FPinLinks> Links;
			for (UEdGraphPin* Pin : Node->Pins)
			{
				if (Pin && Pin->LinkedTo.Num() > 0)
				{
					Links.Add(SnapshotPin(Pin));
				}
			}
			AnimMcpGraphMutator::DetachNode(Node);
			State.Removed.Add(Node);
			State.Detached.Add(Node);
			State.Undo.Add([Graph, Node, Links]()
			{
				AnimMcpGraphMutator::ReattachNode(Graph, Node);
				for (const FPinLinks& L : Links)
				{
					RestorePin(L);
				}
			});
			return true;
		}

		bool ApplySetProperty(FBatchState& State, const FOperation& Op, FAnimMcpError& Error)
		{
			bool bPending = false;
			UClass* PendingClass = nullptr;
			UEdGraphNode* Node = ResolveOpTarget(State, Op, bPending, PendingClass, Error);
			if (!Node)
			{
				return false;
			}
			const FName Property(*Op.Json->GetStringField(TEXT("property")));
			const TSharedPtr<FJsonValue> Value = Op.Json->TryGetField(TEXT("value"));

			if (const AnimMcpPropertyRules::FRule* Rule = AnimMcpPropertyRules::Find(Node->GetClass(), Property); Rule && Rule->Scope == AnimMcpPropertyRules::EScope::NodeRef)
			{
				bool bRefPending = false;
				UEdGraphNode* Target = ResolveNodeRef(State, Value, bRefPending, Error);
				if (!Target)
				{
					return false;
				}
				UEdGraphNode* Old = nullptr;
				if (!AnimMcpGraphMutator::SetCachedPoseSource(Node, Target, Old, Error))
				{
					return false;
				}
				State.Undo.Add([Node, Old]() { AnimMcpGraphMutator::RestoreCachedPoseSource(Node, Old); });
				return true;
			}

			FString OldText;
			if (!AnimMcpGraphMutator::SetPropertyFromJson(Node, Property, Value, OldText, Error))
			{
				return false;
			}
			State.Undo.Add([Node, Property, OldText]()
			{
				FAnimMcpError Ignored;
				AnimMcpGraphMutator::SetPropertyFromText(Node, Property, OldText, Ignored);
			});
			return true;
		}

		bool ApplySetAsset(FBatchState& State, const FOperation& Op, FAnimMcpContext& Context, FAnimMcpError& Error)
		{
			bool bPending = false;
			UClass* PendingClass = nullptr;
			UEdGraphNode* Node = ResolveOpTarget(State, Op, bPending, PendingClass, Error);
			if (!Node)
			{
				return false;
			}
			UAnimationAsset* Asset = AnimMcpAssetResolver::LoadAnimationAsset(Op.Json->GetStringField(TEXT("asset")), Error);
			if (!Asset || !AnimMcpGraphMutator::ValidateNodeAsset(Node->GetClass(), Asset, State.Blueprint, Context, Error))
			{
				return false;
			}
			UAnimGraphNode_Base* AnimNode = Cast<UAnimGraphNode_Base>(Node);
			UAnimationAsset* Old = nullptr;
			if (!AnimMcpGraphMutator::SetAsset(AnimNode, Asset, Old, Error))
			{
				return false;
			}
			State.Undo.Add([AnimNode, Old]() { AnimMcpGraphMutator::RestoreAsset(AnimNode, Old); });
			return true;
		}

		bool ApplyExposePin(FBatchState& State, const FOperation& Op, FAnimMcpError& Error)
		{
			bool bPending = false;
			UClass* PendingClass = nullptr;
			UEdGraphNode* Node = ResolveOpTarget(State, Op, bPending, PendingClass, Error);
			UAnimGraphNode_Base* AnimNode = Cast<UAnimGraphNode_Base>(Node);
			if (!AnimNode)
			{
				if (!Error.IsSet())
				{
					Error = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("expose_pin needs an AnimGraph node"));
				}
				return false;
			}
			const FName Property(*Op.Json->GetStringField(TEXT("property")));
			bool bVisible = true;
			Op.Json->TryGetBoolField(TEXT("visible"), bVisible);
			bool bChanged = false;
			if (!AnimMcpGraphMutator::SetPinVisible(AnimNode, Property, bVisible, Error, &bChanged))
			{
				return false;
			}
			if (bChanged)
			{
				State.Undo.Add([AnimNode, Property, bVisible]()
				{
					FAnimMcpError Ignored;
					AnimMcpGraphMutator::SetPinVisible(AnimNode, Property, !bVisible, Ignored);
				});
			}
			return true;
		}

		bool ApplyAddBlendPose(FBatchState& State, const FOperation& Op, FAnimMcpError& Error)
		{
			bool bPending = false;
			UClass* PendingClass = nullptr;
			UEdGraphNode* Node = ResolveOpTarget(State, Op, bPending, PendingClass, Error);
			if (!Node)
			{
				return false;
			}
			const FString Entry = Op.Json->HasTypedField<EJson::String>(TEXT("entry")) ? Op.Json->GetStringField(TEXT("entry")) : FString();
			if (!AnimMcpGraphMutator::AddBlendPose(Node, Entry, Error))
			{
				return false;
			}
			State.Undo.Add([Node]() { AnimMcpGraphMutator::RemoveLastBlendPose(Node); });
			return true;
		}
	}

	bool ParseOperations(const FJsonObject& Params, TArray<FOperation>& OutOps, FAnimMcpError& OutError)
	{
		const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
		if (!Params.TryGetArrayField(TEXT("operations"), Array) || !Array)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("'operations' array is required"));
			return false;
		}
		if (Array->Num() == 0)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("'operations' is empty"));
			return false;
		}
		OutOps.Reset();
		for (int32 Index = 0; Index < Array->Num(); ++Index)
		{
			const TSharedPtr<FJsonValue>& Value = (*Array)[Index];
			if (!Value.IsValid() || Value->Type != EJson::Object)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("operations[%d] is not an object"), Index));
				return false;
			}
			FOperation Op;
			Op.Index = Index;
			Op.Json = Value->AsObject();
			if (!Op.Json->TryGetStringField(TEXT("op"), Op.Op) || Op.Op.IsEmpty())
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("operations[%d] has no 'op'"), Index));
				return false;
			}
			// add_node 의 ref 만 "정의" 다. 다른 op 의 ref 는 "참조" 이므로 Op.Ref 에 두지 않는다 (중복 정의 검사와 섞이지 않게)
			if (Op.Op == TEXT("add_node"))
			{
				Op.Json->TryGetStringField(TEXT("ref"), Op.Ref);
			}
			OutOps.Add(MoveTemp(Op));
		}
		return true;
	}

	namespace
	{
		void WriteCounts(TSharedRef<FJsonObject>& Result, const FCounts& Counts)
		{
			Result->SetNumberField(TEXT("would_create"), Counts.Create);
			Result->SetNumberField(TEXT("would_connect"), Counts.Connect);
			Result->SetNumberField(TEXT("would_disconnect"), Counts.Disconnect);
			Result->SetNumberField(TEXT("would_remove"), Counts.Remove);
			Result->SetNumberField(TEXT("would_modify"), Counts.Modify);
		}
	}

	TSharedRef<FJsonObject> Preview(UAnimBlueprint* Blueprint, const TArray<FOperation>& Ops, FAnimMcpContext& Context)
	{
		FBatchState State;
		State.Blueprint = Blueprint;

		TArray<TSharedPtr<FJsonValue>> Planned;
		FCounts Counts;
		const bool bValid = Validate(State, Ops, Context, Planned, Counts);

		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetBoolField(TEXT("valid"), bValid);
		Result->SetStringField(TEXT("revision"), AnimMcpGraphInspector::ComputeRevision(Blueprint));
		Result->SetArrayField(TEXT("planned"), Planned);
		WriteCounts(Result, Counts);
		return Result;
	}

	TSharedPtr<FJsonObject> Apply(UAnimBlueprint* Blueprint, const TArray<FOperation>& Ops, const FString& ExpectedRevision, bool bCompile, bool bSave, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		check(IsInGameThread() && Blueprint);

		const FString RevisionBefore = AnimMcpGraphInspector::ComputeRevision(Blueprint);
		if (!ExpectedRevision.IsEmpty() && ExpectedRevision != RevisionBefore)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("expected"), ExpectedRevision);
			Details->SetStringField(TEXT("actual"), RevisionBefore);
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::RevisionMismatch, TEXT("Graph changed since the plan was made; re-inspect and retry"), Details);
			return nullptr;
		}

		// 1) 적용 전 전체 검증 — 하나라도 틀리면 아무것도 바꾸지 않는다
		{
			FBatchState PreState;
			PreState.Blueprint = Blueprint;
			TArray<TSharedPtr<FJsonValue>> Planned;
			FCounts Counts;
			if (!Validate(PreState, Ops, Context, Planned, Counts))
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetArrayField(TEXT("planned"), Planned);
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("One or more operations failed validation; nothing was applied"), Details);
				return nullptr;
			}
		}

		// 2) 트랜잭션 안에서 순차 적용. 실패하면 같은 스코프 안에서 보상 롤백 → 트랜잭션 Cancel (Undo 히스토리에 남기지 않는다)
		FBatchState State;
		State.Blueprint = Blueprint;
		TArray<TSharedPtr<FJsonValue>> Applied;
		FAnimMcpError FailError;
		int32 FailedIndex = INDEX_NONE;
		FString RevisionAfterRollback;
		{
			FScopedTransaction Transaction(LOCTEXT("ApplyGraphOperations", "AnimGraphMcp: apply graph operations"));
			Blueprint->Modify();

			for (const FOperation& Op : Ops)
			{
				FAnimMcpError Error;
				TSharedRef<FJsonObject> Entry = MakePlanned(Op, /*bOk*/ true, nullptr);
				bool bOk = false;

				if (Op.Op == TEXT("add_node"))            { bOk = ApplyAddNode(State, Op, Context, Entry, Error); }
				else if (Op.Op == TEXT("connect"))        { bOk = ApplyConnect(State, Op, Error); }
				else if (Op.Op == TEXT("disconnect"))     { bOk = ApplyDisconnect(State, Op, Error); }
				else if (Op.Op == TEXT("remove_node"))    { bOk = ApplyRemoveNode(State, Op, Error); }
				else if (Op.Op == TEXT("set_property"))   { bOk = ApplySetProperty(State, Op, Error); }
				else if (Op.Op == TEXT("set_asset"))      { bOk = ApplySetAsset(State, Op, Context, Error); }
				else if (Op.Op == TEXT("expose_pin"))     { bOk = ApplyExposePin(State, Op, Error); }
				else if (Op.Op == TEXT("add_blend_pose")) { bOk = ApplyAddBlendPose(State, Op, Error); }
				else
				{
					Error = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Unknown op '%s'"), *Op.Op));
				}

				Entry->SetBoolField(TEXT("ok"), bOk);
				if (!bOk && Error.IsSet())
				{
					Entry->SetObjectField(TEXT("error"), Error.ToJson());
				}
				Applied.Add(MakeShared<FJsonValueObject>(Entry));

				if (!bOk)
				{
					FailError = Error;
					FailedIndex = Op.Index;
					break;
				}
			}

			if (FailedIndex == INDEX_NONE)
			{
				// 분리 보관된 노드를 이제 확정 삭제 (서브그래프 포함)
				for (UEdGraphNode* Node : State.Detached)
				{
					AnimMcpGraphMutator::FinalizeRemoval(Node);
				}
				FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
			}
			else
			{
				RollbackBatch(State);
				RevisionAfterRollback = AnimMcpGraphInspector::ComputeRevision(Blueprint);
				Transaction.Cancel();
			}
		} // 트랜잭션 종료

		// 3) 실패 → 보상 롤백 결과를 revision 으로 검증해 보고
		if (FailedIndex != INDEX_NONE)
		{
			const bool bRollbackVerified = (RevisionAfterRollback == RevisionBefore);

			// 새 객체여야 한다 — FailError.Details 는 Applied 의 해당 항목 안에도 들어 있어서 재사용하면 JSON 이 자기 자신을 참조해
			// 직렬화가 무한 재귀한다 (2026-10-14 에디터 크래시 원인)
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			if (FailError.Details.IsValid())
			{
				Details->SetObjectField(TEXT("cause"), FailError.Details);
			}
			Details->SetNumberField(TEXT("failed_index"), FailedIndex);
			Details->SetArrayField(TEXT("applied"), Applied);
			Details->SetBoolField(TEXT("rolled_back"), true);
			Details->SetBoolField(TEXT("rollback_verified"), bRollbackVerified);
			Details->SetStringField(TEXT("revision_before"), RevisionBefore);
			Details->SetStringField(TEXT("revision_after"), RevisionAfterRollback);
			if (!bRollbackVerified)
			{
				UE_LOG(LogAnimGraphMcp, Error, TEXT("Rollback of failed batch on %s left the graph changed (%s -> %s)"), *Blueprint->GetPathName(), *RevisionBefore, *RevisionAfterRollback);
				Context.AddDiagnostic(TEXT("error"), TEXT("ROLLBACK_UNVERIFIED"), TEXT("Graph revision differs after rollback; inspect before continuing"));
			}
			OutError = FAnimMcpError::Make(*FailError.Code, FString::Printf(TEXT("operations[%d] failed: %s"), FailedIndex, *FailError.Message), Details);
			return nullptr;
		}

		// 4) 성공 — 결과 조립, 옵션 컴파일·저장
		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetStringField(TEXT("revision_before"), RevisionBefore);
		Result->SetStringField(TEXT("revision_after"), AnimMcpGraphInspector::ComputeRevision(Blueprint));
		Result->SetNumberField(TEXT("applied"), Applied.Num());
		Result->SetArrayField(TEXT("operations"), Applied);

		TSharedRef<FJsonObject> Refs = AnimMcpJson::MakeObject();
		for (const TPair<FString, UEdGraphNode*>& Pair : State.Refs)
		{
			Refs->SetStringField(Pair.Key, Pair.Value->NodeGuid.ToString());
		}
		Result->SetObjectField(TEXT("refs"), Refs);

		bool bCompileOk = true;
		if (bCompile)
		{
			TSharedRef<FJsonObject> CompileResult = AnimMcpCompiler::Compile(Blueprint, Context);
			bCompileOk = CompileResult->GetBoolField(TEXT("ok"));
			Result->SetObjectField(TEXT("compile"), CompileResult);
		}
		else
		{
			TSharedRef<FJsonObject> Skipped = AnimMcpJson::MakeObject();
			Skipped->SetBoolField(TEXT("ran"), false);
			Result->SetObjectField(TEXT("compile"), Skipped);
		}

		bool bSaved = false;
		if (bSave)
		{
			if (!bCompileOk)
			{
				Context.AddDiagnostic(TEXT("warning"), TEXT("SAVE_SKIPPED"), TEXT("Not saved because compile reported errors"));
			}
			else
			{
				FAnimMcpError SaveError;
				bSaved = AnimMcpCompiler::Save(Blueprint, SaveError);
				if (!bSaved)
				{
					Context.AddDiagnostic(TEXT("error"), *SaveError.Code, SaveError.Message);
				}
			}
		}
		Result->SetBoolField(TEXT("saved"), bSaved);
		return Result;
	}
}

#undef LOCTEXT_NAMESPACE
