#include "AnimMcpOperations.h"

#include "AnimGraphNode_Base.h"
#include "AnimMcpAssetResolver.h"
#include "AnimMcpCompiler.h"
#include "AnimMcpGraphInspector.h"
#include "AnimMcpGraphMutator.h"
#include "AnimMcpLog.h"
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
		/** connect 가 바꾸기 전의 양 끝 핀 링크 — 롤백 시 그대로 복원 */
		struct FLinkSnapshot
		{
			UEdGraphPin* Pin = nullptr;
			TArray<UEdGraphPin*> LinkedTo;
		};

		/** 배치 실행 중 상태 — ref 표, 결과 누적, 보상 롤백용 기록 */
		struct FBatchState
		{
			UAnimBlueprint* Blueprint = nullptr;
			TMap<FString, UEdGraphNode*> Refs;
			/** Preview 전용 — 아직 만들어지지 않은 ref 와 그 클래스 (핀 검증을 미룬다) */
			TMap<FString, UClass*> PendingRefClasses;

			/** 이 배치가 만든 노드 (생성 순서) */
			TArray<UEdGraphNode*> CreatedNodes;
			/** connect 직전 링크 스냅샷 (적용 순서) */
			TArray<FLinkSnapshot> LinkSnapshots;
		};

		/**
		 * 보상 롤백 — 에디터 Undo 를 호출하지 않는다. 이 배치가 한 일을 역순으로 되돌린다:
		 * connect 가 바꾼 핀 링크를 스냅샷으로 복원하고, 만든 노드를 DestroyNode 로 제거한다 (서브그래프 보유 노드는 자기 그래프도 지운다).
		 * 호출자는 이 뒤에 트랜잭션을 Cancel 해 기록을 버린다
		 */
		void RollbackBatch(FBatchState& State)
		{
			for (int32 i = State.LinkSnapshots.Num() - 1; i >= 0; --i)
			{
				const FLinkSnapshot& Snapshot = State.LinkSnapshots[i];
				if (!Snapshot.Pin || !Snapshot.Pin->GetOwningNodeUnchecked())
				{
					continue;
				}
				Snapshot.Pin->GetOwningNodeUnchecked()->Modify();
				Snapshot.Pin->BreakAllPinLinks(/*bNotifyNodes*/ true);
				for (UEdGraphPin* Old : Snapshot.LinkedTo)
				{
					// 상대 노드가 이 배치에서 생성된 것이면 곧 삭제되므로 복원하지 않는다
					UEdGraphNode* OldOwner = Old ? Old->GetOwningNodeUnchecked() : nullptr;
					if (OldOwner && !State.CreatedNodes.Contains(OldOwner))
					{
						OldOwner->Modify();
						Snapshot.Pin->MakeLinkTo(Old);
					}
				}
			}
			for (int32 i = State.CreatedNodes.Num() - 1; i >= 0; --i)
			{
				UEdGraphNode* Node = State.CreatedNodes[i];
				if (!Node)
				{
					continue;
				}
				if (UEdGraph* Graph = Node->GetGraph())
				{
					Graph->Modify();
				}
				Node->Modify();
				Node->BreakAllNodeLinks();
				Node->DestroyNode();
			}
			State.CreatedNodes.Empty();
			State.LinkSnapshots.Empty();
		}

		TSharedPtr<FJsonObject> GetObjectField(const TSharedPtr<FJsonObject>& Json, const TCHAR* Key)
		{
			const TSharedPtr<FJsonObject>* Obj = nullptr;
			return (Json.IsValid() && Json->TryGetObjectField(Key, Obj) && Obj) ? *Obj : nullptr;
		}

		/** {node:"guid"} | {ref:"name"} | "guid" → 노드. ref 가 아직 미생성(Preview)이면 bOutPending */
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

			if (!Ref.IsEmpty())
			{
				if (UEdGraphNode** Found = State.Refs.Find(Ref))
				{
					return *Found;
				}
				if (State.PendingRefClasses.Contains(Ref))
				{
					bOutPending = true;
					return nullptr;
				}
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("ref '%s' is not defined by an earlier add_node in this batch"), *Ref));
				return nullptr;
			}
			if (!Guid.IsEmpty())
			{
				return AnimMcpGraphMutator::FindNode(State.Blueprint, Guid, OutError);
			}
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("Node reference needs 'node' (guid) or 'ref'"));
			return nullptr;
		}

		struct FAddNodeArgs
		{
			UEdGraph* Graph = nullptr;
			UClass* NodeClass = nullptr;
			UAnimationAsset* Asset = nullptr;
			FVector2D Position = FVector2D::ZeroVector;
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
				if (!Out.Asset)
				{
					return false;
				}
				if (!AnimMcpGraphMutator::ValidateNodeAsset(Out.NodeClass, Out.Asset, State.Blueprint, Context, OutError))
				{
					return false;
				}
			}
			return true;
		}

		struct FConnectArgs
		{
			UEdGraphPin* From = nullptr;
			UEdGraphPin* To = nullptr;
			/** Preview 에서 ref 가 아직 없어 핀 검증을 건너뛴 경우 */
			bool bDeferred = false;
		};

		bool ResolveConnect(FBatchState& State, const FOperation& Op, FConnectArgs& Out, FAnimMcpError& OutError)
		{
			const TSharedPtr<FJsonObject> From = GetObjectField(Op.Json, TEXT("from"));
			const TSharedPtr<FJsonObject> To = GetObjectField(Op.Json, TEXT("to"));
			if (!From.IsValid() || !To.IsValid())
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("connect requires 'from' and 'to' objects {node|ref, pin}"));
				return false;
			}
			FString FromPin, ToPin;
			if (!From->TryGetStringField(TEXT("pin"), FromPin) || !To->TryGetStringField(TEXT("pin"), ToPin))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("connect endpoints need 'pin'"));
				return false;
			}

			bool bFromPending = false, bToPending = false;
			UEdGraphNode* FromNode = ResolveNodeRef(State, MakeShared<FJsonValueObject>(From), bFromPending, OutError);
			if (!FromNode && !bFromPending)
			{
				return false;
			}
			UEdGraphNode* ToNode = ResolveNodeRef(State, MakeShared<FJsonValueObject>(To), bToPending, OutError);
			if (!ToNode && !bToPending)
			{
				return false;
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
			Out.To = AnimMcpGraphMutator::FindPin(ToNode, ToPin, OutError);
			if (!Out.To)
			{
				return false;
			}
			return AnimMcpGraphMutator::ValidateConnection(Out.From, Out.To, OutError);
		}

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

		/** 공통 검증 — Preview 본체. Apply 도 적용 전에 같은 함수를 돌린다 */
		bool Validate(FBatchState& State, const TArray<FOperation>& Ops, FAnimMcpContext& Context, TArray<TSharedPtr<FJsonValue>>& OutPlanned, int32& OutCreate, int32& OutConnect)
		{
			bool bAllOk = true;
			OutCreate = 0;
			OutConnect = 0;
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
						++OutCreate;
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
					FConnectArgs Args;
					bOk = ResolveConnect(State, Op, Args, Error);
					if (bOk)
					{
						++OutConnect;
						if (Args.bDeferred)
						{
							Note = TEXT("endpoint node is created earlier in this batch; pin check happens at apply");
						}
					}
				}
				else
				{
					Error = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Unknown op '%s' (supported: add_node, connect)"), *Op.Op));
				}

				bAllOk &= bOk;
				OutPlanned.Add(MakeShared<FJsonValueObject>(MakePlanned(Op, bOk, &Error, Note)));
			}
			return bAllOk;
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
			Op.Json->TryGetStringField(TEXT("ref"), Op.Ref);
			OutOps.Add(MoveTemp(Op));
		}
		return true;
	}

	TSharedRef<FJsonObject> Preview(UAnimBlueprint* Blueprint, const TArray<FOperation>& Ops, FAnimMcpContext& Context)
	{
		FBatchState State;
		State.Blueprint = Blueprint;

		TArray<TSharedPtr<FJsonValue>> Planned;
		int32 Create = 0, Connect = 0;
		const bool bValid = Validate(State, Ops, Context, Planned, Create, Connect);

		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetBoolField(TEXT("valid"), bValid);
		Result->SetStringField(TEXT("revision"), AnimMcpGraphInspector::ComputeRevision(Blueprint));
		Result->SetArrayField(TEXT("planned"), Planned);
		Result->SetNumberField(TEXT("would_create"), Create);
		Result->SetNumberField(TEXT("would_connect"), Connect);
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
			int32 Create = 0, Connect = 0;
			if (!Validate(PreState, Ops, Context, Planned, Create, Connect))
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
				bool bOk = false;
				FString NewGuid;

				if (Op.Op == TEXT("add_node"))
				{
					FAddNodeArgs Args;
					if (ResolveAddNode(State, Op, Args, Context, Error))
					{
						if (UAnimGraphNode_Base* Node = AnimMcpGraphMutator::AddNode(Args.Graph, Args.NodeClass, Args.Position, Args.Asset, Error))
						{
							bOk = true;
							NewGuid = Node->NodeGuid.ToString();
							State.CreatedNodes.Add(Node);
							if (!Op.Ref.IsEmpty())
							{
								State.Refs.Add(Op.Ref, Node);
							}
						}
					}
				}
				else if (Op.Op == TEXT("connect"))
				{
					FConnectArgs Args;
					if (ResolveConnect(State, Op, Args, Error) && !Args.bDeferred)
					{
						State.LinkSnapshots.Add({ Args.From, Args.From->LinkedTo });
						State.LinkSnapshots.Add({ Args.To, Args.To->LinkedTo });
						bOk = AnimMcpGraphMutator::Connect(Args.From, Args.To, Error);
					}
					else if (!Error.IsSet())
					{
						Error = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("connect endpoint unresolved at apply time"));
					}
				}

				TSharedRef<FJsonObject> Entry = MakePlanned(Op, bOk, &Error);
				if (!NewGuid.IsEmpty())
				{
					Entry->SetStringField(TEXT("node_guid"), NewGuid);
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
