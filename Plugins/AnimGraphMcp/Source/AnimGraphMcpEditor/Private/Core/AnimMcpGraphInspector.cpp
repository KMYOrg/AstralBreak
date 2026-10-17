#include "AnimMcpGraphInspector.h"

#include "AnimGraphNode_Base.h"
#include "AnimGraphNode_LinkedAnimLayer.h"
#include "AnimGraphNode_SaveCachedPose.h"
#include "AnimGraphNode_UseCachedPose.h"
#include "AnimMcpAnimLayer.h"
#include "AnimMcpGraphMutator.h"
#include "AnimMcpMontage.h"
#include "AnimMcpUpdateFunction.h"
#include "AnimMcpVariables.h"
#include "AnimMcpPropertyBinding.h"
#include "AnimMcpPropertyRules.h"
#include "AnimMcpTransitionRule.h"
#include "AnimStateAliasNode.h"
#include "AnimStateConduitNode.h"
#include "AnimStateEntryNode.h"
#include "AnimStateNode.h"
#include "AnimStateNodeBase.h"
#include "AnimStateTransitionNode.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimBlueprintGeneratedClass.h"
#include "Animation/BlendProfile.h"
#include "Animation/Skeleton.h"
#include "AnimationGraph.h"
#include "AnimationStateMachineGraph.h"
#include "AnimGraphNode_StateMachineBase.h"
#include "Bridge/AnimMcpTypes.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphSchema_K2.h"
#include "Engine/SkeletalMesh.h"
#include "Misc/SecureHash.h"
#include "UObject/UnrealType.h"

namespace AnimMcpGraphInspector
{
	namespace
	{
		void AppendGraphRecursive(UEdGraph* Graph, UEdGraph* Parent, TArray<FGraphRecord>& Out, TSet<UEdGraph*>& Visited)
		{
			if (!Graph || Visited.Contains(Graph))
			{
				return;
			}
			Visited.Add(Graph);
			Out.Add({ Graph, Parent });
			for (UEdGraph* Sub : Graph->SubGraphs)
			{
				AppendGraphRecursive(Sub, Graph, Out, Visited);
			}
		}

		UEdGraphNode* FindOwnerNode(UEdGraph* Graph)
		{
			if (UAnimationStateMachineGraph* SMGraph = Cast<UAnimationStateMachineGraph>(Graph))
			{
				if (UAnimGraphNode_StateMachineBase* Owner = SMGraph->OwnerAnimGraphNode.Get())
				{
					return Owner;
				}
			}
			// State/Transition BoundGraph 는 CreateNewGraph(this, ...) 로 만들어져 Outer 가 소유 노드다
			return Cast<UEdGraphNode>(Graph->GetOuter());
		}

		FString PinDirectionToString(EEdGraphPinDirection Direction)
		{
			return Direction == EGPD_Input ? TEXT("in") : TEXT("out");
		}

		/** 구조체 상속 사슬에 이 이름이 있는가 — StaticStruct() 링크 의존 없이 판정 (FPoseLinkBase 는 API 매크로가 없다) */
		bool StructDerivesFrom(const UStruct* Struct, const TCHAR* BaseName)
		{
			for (const UStruct* S = Struct; S; S = S->GetSuperStruct())
			{
				if (S->GetName() == BaseName)
				{
					return true;
				}
			}
			return false;
		}

		/** FPoseLink · FComponentSpacePoseLink · 그 배열 — 컴파일러가 LinkID 를 바꾸므로 revision 에서 제외 */
		bool IsPoseLinkProperty(const FProperty* Property)
		{
			if (const FStructProperty* SP = CastField<FStructProperty>(Property))
			{
				return StructDerivesFrom(SP->Struct, TEXT("PoseLinkBase"));
			}
			if (const FArrayProperty* AP = CastField<FArrayProperty>(Property))
			{
				return IsPoseLinkProperty(AP->Inner);
			}
			return false;
		}

		bool ShouldSkipForRevision(const FProperty* Property)
		{
			return Property->HasAnyPropertyFlags(CPF_Transient | CPF_Deprecated) || IsPoseLinkProperty(Property) || CastField<FTextProperty>(Property) != nullptr;
		}

		void AppendStructValues(const UStruct* Struct, const void* Container, UObject* Owner, const FString& Prefix, FString& Out)
		{
			for (TFieldIterator<FProperty> It(Struct); It; ++It)
			{
				FProperty* Property = *It;
				if (ShouldSkipForRevision(Property))
				{
					continue;
				}
				FString Text;
				Property->ExportText_Direct(Text, Property->ContainerPtrToValuePtr<void>(Container), nullptr, Owner, PPF_None);
				Out += FString::Printf(TEXT("V|%s%s|%s\n"), *Prefix, *Property->GetName(), *Text);
			}
		}
	}

	void AppendEditableProperties(UEdGraphNode* Node, FString& Out)
	{
		UAnimGraphNode_Base* AnimNode = Cast<UAnimGraphNode_Base>(Node);
		// (7-4) 커스텀 핀 노출 상태 — CustomPinProperties 는 EditAnywhere 가 아니라 아래 루프에 안 걸린다 (없으면 줄 없음 → 기존 revision 호환)
		if (TArray<FOptionalPinFromProperty>* Custom = AnimMcpGraphMutator::CustomPinsOf(AnimNode))
		{
			for (const FOptionalPinFromProperty& Optional : *Custom)
			{
				Out += FString::Printf(TEXT("C|%s|%d\n"), *Optional.PropertyName.ToString(), Optional.bShowPin ? 1 : 0);
			}
		}
		for (TFieldIterator<FProperty> It(Node->GetClass()); It; ++It)
		{
			FProperty* Property = *It;
			if (!Property->HasAnyPropertyFlags(CPF_Edit) || ShouldSkipForRevision(Property))
			{
				continue;
			}

			// 노출 핀 상태 — FOptionalPinFromProperty 에는 FText 툴팁이 들어 있어 통째로 내보내지 않고 (이름, bShowPin) 만 넣는다
			if (AnimNode && Property->GetFName() == GET_MEMBER_NAME_CHECKED(UAnimGraphNode_Base, ShowPinForProperties))
			{
				for (const FOptionalPinFromProperty& Optional : AnimNode->ShowPinForProperties)
				{
					Out += FString::Printf(TEXT("O|%s|%d\n"), *Optional.PropertyName.ToString(), Optional.bShowPin ? 1 : 0);
				}
				continue;
			}

			if (const FStructProperty* SP = CastField<FStructProperty>(Property); SP && StructDerivesFrom(SP->Struct, TEXT("AnimNode_Base")))
			{
				AppendStructValues(SP->Struct, SP->ContainerPtrToValuePtr<void>(Node), Node, SP->GetName() + TEXT("."), Out);
				continue;
			}

			FString Text;
			Property->ExportText_Direct(Text, Property->ContainerPtrToValuePtr<void>(Node), nullptr, Node, PPF_None);
			Out += FString::Printf(TEXT("V|%s|%s\n"), *Property->GetName(), *Text);
		}
	}

	void CollectGraphs(UAnimBlueprint* Blueprint, TArray<FGraphRecord>& OutGraphs)
	{
		OutGraphs.Reset();
		if (!Blueprint)
		{
			return;
		}
		TSet<UEdGraph*> Visited;
		for (UEdGraph* Graph : Blueprint->FunctionGraphs)
		{
			AppendGraphRecursive(Graph, nullptr, OutGraphs, Visited);
		}
		// Phase 6-4b — 구현한 인터페이스의 레이어 그래프는 FunctionGraphs 가 아니라 ImplementedInterfaces[].Graphs 에 있다
		for (const FBPInterfaceDescription& Desc : Blueprint->ImplementedInterfaces)
		{
			for (UEdGraph* Graph : Desc.Graphs)
			{
				AppendGraphRecursive(Graph, nullptr, OutGraphs, Visited);
			}
		}
		for (UEdGraph* Graph : Blueprint->UbergraphPages)
		{
			AppendGraphRecursive(Graph, nullptr, OutGraphs, Visited);
		}
		for (UEdGraph* Graph : Blueprint->MacroGraphs)
		{
			AppendGraphRecursive(Graph, nullptr, OutGraphs, Visited);
		}
	}

	UEdGraph* FindRootAnimGraph(UAnimBlueprint* Blueprint)
	{
		if (!Blueprint)
		{
			return nullptr;
		}
		for (UEdGraph* Graph : Blueprint->FunctionGraphs)
		{
			if (Graph && Graph->IsA<UAnimationGraph>() && Graph->GetFName() == UEdGraphSchema_K2::GN_AnimGraph)
			{
				return Graph;
			}
		}
		// 인터페이스 BP 의 UAnimationGraph 는 전부 레이어 — 루트가 없다 (폴백이 레이어를 루트로 오인하면 안 된다)
		if (Blueprint->BlueprintType == BPTYPE_Interface)
		{
			return nullptr;
		}
		// 이름이 바뀐 경우의 폴백 — 최상위 UAnimationGraph 중 첫 번째
		for (UEdGraph* Graph : Blueprint->FunctionGraphs)
		{
			if (Graph && Graph->GetClass() == UAnimationGraph::StaticClass())
			{
				return Graph;
			}
		}
		return nullptr;
	}

	FString ComputeRevision(UAnimBlueprint* Blueprint)
	{
		TArray<FGraphRecord> Graphs;
		CollectGraphs(Blueprint, Graphs);

		// 결정적 순서 — 그래프는 Guid 문자열, 노드는 Guid 문자열, 핀은 (방향, 이름) 로 정렬
		Graphs.Sort([](const FGraphRecord& A, const FGraphRecord& B)
		{
			return A.Graph->GraphGuid.ToString() < B.Graph->GraphGuid.ToString();
		});

		FString Buffer;
		Buffer.Reserve(64 * 1024);
		for (const FGraphRecord& Record : Graphs)
		{
			UEdGraph* Graph = Record.Graph;
			Buffer += FString::Printf(TEXT("G|%s|%s|%s\n"), *Graph->GraphGuid.ToString(), *Graph->GetClass()->GetName(), *Graph->GetName());

			TArray<UEdGraphNode*> Nodes = Graph->Nodes;
			Nodes.RemoveAll([](UEdGraphNode* N) { return N == nullptr; });
			Nodes.Sort([](const UEdGraphNode& A, const UEdGraphNode& B) { return A.NodeGuid.ToString() < B.NodeGuid.ToString(); });

			for (UEdGraphNode* Node : Nodes)
			{
				Buffer += FString::Printf(TEXT("N|%s|%s|%d|%d\n"), *Node->NodeGuid.ToString(), *Node->GetClass()->GetName(), Node->NodePosX, Node->NodePosY);
				AppendEditableProperties(Node, Buffer);
				// Phase 6-4: 핀 바인딩 (Binding 객체는 Instanced 참조라 ExportText 로는 내용이 안 들어간다). 없으면 줄이 없어 기존 해시와 호환
				if (const UAnimGraphNode_Base* AnimNode = Cast<UAnimGraphNode_Base>(Node))
				{
					AnimMcpPropertyBinding::AppendRevision(AnimNode, Buffer);
				}

				TArray<UEdGraphPin*> Pins = Node->Pins;
				Pins.RemoveAll([](UEdGraphPin* P) { return P == nullptr; });
				Pins.Sort([](const UEdGraphPin& A, const UEdGraphPin& B)
				{
					if (A.Direction != B.Direction)
					{
						return A.Direction < B.Direction;
					}
					return A.PinName.LexicalLess(B.PinName);
				});

				for (UEdGraphPin* Pin : Pins)
				{
					TArray<FString> Links;
					for (UEdGraphPin* Linked : Pin->LinkedTo)
					{
						if (Linked && Linked->GetOwningNodeUnchecked())
						{
							Links.Add(Linked->GetOwningNodeUnchecked()->NodeGuid.ToString() + TEXT(":") + Linked->PinName.ToString());
						}
					}
					Links.Sort();
					Buffer += FString::Printf(TEXT("P|%s|%s|%s|%s|%s\n"), *Pin->PinName.ToString(), *PinDirectionToString(Pin->Direction),
						*Pin->PinType.PinCategory.ToString(), *Pin->DefaultValue, *FString::Join(Links, TEXT(";")));
				}
			}
		}

		// (7-1) BP 변수 선언 — NewVariables 가 없으면 줄이 없어 기존 revision 과 호환
		AnimMcpVariables::AppendRevisionLines(Blueprint, Buffer);

		const FTCHARToUTF8 Utf8(*Buffer);
		const FSHAHash Hash = FSHA1::HashBuffer(Utf8.Get(), Utf8.Length());
		return TEXT("sha1:") + Hash.ToString().ToLower();
	}

	TSharedRef<FJsonObject> DescribeGraph(const FGraphRecord& Record)
	{
		UEdGraph* Graph = Record.Graph;
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetStringField(TEXT("graph_guid"), Graph->GraphGuid.ToString());
		Obj->SetStringField(TEXT("name"), Graph->GetName());
		Obj->SetStringField(TEXT("class"), Graph->GetClass()->GetName());
		Obj->SetField(TEXT("parent_graph_guid"), Record.ParentGraph ? AnimMcpJson::StringOrNull(Record.ParentGraph->GraphGuid.ToString()) : MakeShared<FJsonValueNull>());
		UEdGraphNode* Owner = FindOwnerNode(Graph);
		Obj->SetField(TEXT("owner_node_guid"), Owner ? AnimMcpJson::StringOrNull(Owner->NodeGuid.ToString()) : MakeShared<FJsonValueNull>());
		// Phase 6-4b — 인터페이스 레이어 그래프는 InterfaceGuid 를 갖는다 (ImplementNewInterface 가 FindInterfaceFunctionGuid 로 채움)
		Obj->SetField(TEXT("interface_guid"), Graph->InterfaceGuid.IsValid() ? AnimMcpJson::StringOrNull(Graph->InterfaceGuid.ToString()) : MakeShared<FJsonValueNull>());
		Obj->SetField(TEXT("owner_node_class"), Owner ? AnimMcpJson::StringOrNull(Owner->GetClass()->GetName()) : MakeShared<FJsonValueNull>());
		Obj->SetNumberField(TEXT("node_count"), Graph->Nodes.Num());
		return Obj;
	}

	UEdGraph* FindGraphByGuid(UAnimBlueprint* Blueprint, const FGuid& Guid)
	{
		TArray<FGraphRecord> Graphs;
		CollectGraphs(Blueprint, Graphs);
		for (const FGraphRecord& Record : Graphs)
		{
			if (Record.Graph->GraphGuid == Guid)
			{
				return Record.Graph;
			}
		}
		return nullptr;
	}

	UEdGraphNode* FindNodeByGuid(UAnimBlueprint* Blueprint, const FGuid& Guid)
	{
		TArray<FGraphRecord> Graphs;
		CollectGraphs(Blueprint, Graphs);
		for (const FGraphRecord& Record : Graphs)
		{
			for (UEdGraphNode* Node : Record.Graph->Nodes)
			{
				if (Node && Node->NodeGuid == Guid)
				{
					return Node;
				}
			}
		}
		return nullptr;
	}

	TSharedRef<FJsonObject> DescribePin(const UEdGraphPin* Pin)
	{
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetStringField(TEXT("name"), Pin->PinName.ToString());
		Obj->SetStringField(TEXT("dir"), PinDirectionToString(Pin->Direction));

		FString Type = Pin->PinType.PinCategory.ToString();
		if (Pin->PinType.PinSubCategoryObject.IsValid())
		{
			Type += TEXT(":") + Pin->PinType.PinSubCategoryObject->GetName();
		}
		else if (!Pin->PinType.PinSubCategory.IsNone())
		{
			Type += TEXT(":") + Pin->PinType.PinSubCategory.ToString();
		}
		if (Pin->PinType.IsArray())
		{
			Type += TEXT("[]");
		}
		Obj->SetStringField(TEXT("type"), Type);

		if (Pin->DefaultObject)
		{
			Obj->SetStringField(TEXT("default"), Pin->DefaultObject->GetPathName());
		}
		else
		{
			Obj->SetField(TEXT("default"), AnimMcpJson::StringOrNull(Pin->DefaultValue));
		}
		Obj->SetBoolField(TEXT("hidden"), Pin->bHidden);

		TArray<TSharedPtr<FJsonValue>> Linked;
		for (const UEdGraphPin* Other : Pin->LinkedTo)
		{
			if (Other && Other->GetOwningNodeUnchecked())
			{
				Linked.Add(MakeShared<FJsonValueString>(Other->GetOwningNodeUnchecked()->NodeGuid.ToString() + TEXT(":") + Other->PinName.ToString()));
			}
		}
		Obj->SetArrayField(TEXT("linked"), Linked);
		return Obj;
	}

	TSharedRef<FJsonObject> DescribeNode(UEdGraphNode* Node)
	{
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetStringField(TEXT("node_guid"), Node->NodeGuid.ToString());
		Obj->SetField(TEXT("graph_guid"), Node->GetGraph() ? AnimMcpJson::StringOrNull(Node->GetGraph()->GraphGuid.ToString()) : MakeShared<FJsonValueNull>());
		Obj->SetStringField(TEXT("class"), Node->GetClass()->GetName());
		Obj->SetStringField(TEXT("title"), Node->GetNodeTitle(ENodeTitleType::ListView).ToString());

		TArray<TSharedPtr<FJsonValue>> Pos;
		Pos.Add(MakeShared<FJsonValueNumber>(Node->NodePosX));
		Pos.Add(MakeShared<FJsonValueNumber>(Node->NodePosY));
		Obj->SetArrayField(TEXT("pos"), Pos);

		if (UAnimGraphNode_Base* AnimNode = Cast<UAnimGraphNode_Base>(Node))
		{
			Obj->SetField(TEXT("asset"), AnimMcpJson::ObjectPathOrNull(AnimNode->GetAnimationAsset()));
			Obj->SetBoolField(TEXT("is_sink"), AnimNode->IsSinkNode());

			// 노출 가능 핀과 바인딩 — Phase 6-4: bind_pin/unbind_pin 이 쓰고, 묶인 핀은 binding{path, path_text, type, context, promotion}
			TArray<AnimMcpPropertyBinding::FBindingInfo> Bindings;
			AnimMcpPropertyBinding::ReadBindings(AnimNode, Bindings);
			TArray<TSharedPtr<FJsonValue>> OptionalPins;
			bool bAnyBinding = false;
			for (const FOptionalPinFromProperty& Optional : AnimNode->ShowPinForProperties)
			{
				const bool bBound = AnimNode->HasBinding(Optional.PropertyName);
				bAnyBinding |= bBound;
				TSharedRef<FJsonObject> O = AnimMcpJson::MakeObject();
				O->SetStringField(TEXT("property"), Optional.PropertyName.ToString());
				O->SetBoolField(TEXT("shown"), Optional.bShowPin);
				O->SetBoolField(TEXT("can_toggle"), Optional.bCanToggleVisibility);
				O->SetBoolField(TEXT("bound"), bBound);
				if (bBound)
				{
					const FName PinName = Optional.PropertyName;
					if (const AnimMcpPropertyBinding::FBindingInfo* Info = Bindings.FindByPredicate([PinName](const AnimMcpPropertyBinding::FBindingInfo& B) { return FName(B.Name, 0) == PinName; }))
					{
						TSharedRef<FJsonObject> BO = AnimMcpJson::MakeObject();
						TArray<TSharedPtr<FJsonValue>> PathArr;
						for (const FString& Seg : Info->Path) { PathArr.Add(MakeShared<FJsonValueString>(Seg)); }
						BO->SetArrayField(TEXT("path"), PathArr);
						BO->SetStringField(TEXT("path_text"), Info->PathText);
						BO->SetStringField(TEXT("type"), Info->Type);
						BO->SetField(TEXT("context"), AnimMcpJson::StringOrNull(Info->Context.IsNone() ? FString() : Info->Context.ToString()));
						BO->SetBoolField(TEXT("promotion"), Info->bPromotion);
						O->SetObjectField(TEXT("binding"), BO);
					}
				}
				OptionalPins.Add(MakeShared<FJsonValueObject>(O));
			}
			// (7-4) LinkedAnimLayer/LinkedAnimGraph 의 값 파라미터 핀 (CustomPinProperties) — expose_pin 으로 켜고 connect 로 값을 넣는다
			if (TArray<FOptionalPinFromProperty>* Custom = AnimMcpGraphMutator::CustomPinsOf(AnimNode))
			{
				for (const FOptionalPinFromProperty& Optional : *Custom)
				{
					TSharedRef<FJsonObject> O = AnimMcpJson::MakeObject();
					O->SetStringField(TEXT("property"), Optional.PropertyName.ToString());
					O->SetBoolField(TEXT("shown"), Optional.bShowPin);
					O->SetBoolField(TEXT("can_toggle"), Optional.bCanToggleVisibility);
					O->SetBoolField(TEXT("bound"), false);
					O->SetBoolField(TEXT("custom"), true);
					OptionalPins.Add(MakeShared<FJsonValueObject>(O));
				}
			}
			Obj->SetArrayField(TEXT("optional_pins"), OptionalPins);
			Obj->SetBoolField(TEXT("has_binding"), bAnyBinding);
			// Phase 6-4b — Linked Anim Layer 노드
			if (const UAnimGraphNode_LinkedAnimLayer* LayerNode = Cast<UAnimGraphNode_LinkedAnimLayer>(AnimNode))
			{
				Obj->SetObjectField(TEXT("linked_layer"), AnimMcpAnimLayer::DescribeLinkedLayerNode(LayerNode));
			}
		}
		else
		{
			Obj->SetField(TEXT("asset"), MakeShared<FJsonValueNull>());
		}
		if (!Node->NodeComment.IsEmpty())
		{
			Obj->SetStringField(TEXT("comment"), Node->NodeComment);
		}

		// 허용 목록 프로퍼티의 현재 값 — set_property 가 받는 이름과 같다
		TSharedRef<FJsonObject> Properties = AnimMcpJson::MakeObject();
		for (const AnimMcpPropertyRules::FRule& Rule : AnimMcpPropertyRules::RulesFor(Node->GetClass()))
		{
			if (Rule.Scope == AnimMcpPropertyRules::EScope::NodeRef)
			{
				if (UAnimGraphNode_UseCachedPose* UseNode = Cast<UAnimGraphNode_UseCachedPose>(Node))
				{
					UAnimGraphNode_SaveCachedPose* Source = UseNode->SaveCachedPoseNode.Get();
					Properties->SetField(Rule.Property.ToString(), Source ? AnimMcpJson::StringOrNull(Source->NodeGuid.ToString()) : MakeShared<FJsonValueNull>());
				}
				continue;
			}
			FAnimMcpError Ignored;
			AnimMcpPropertyRules::FResolved Resolved;
			if (AnimMcpPropertyRules::ResolveOnNode(Node, Rule.Property, Resolved, Ignored) && Resolved.Property && Resolved.Container)
			{
				Properties->SetField(Rule.Property.ToString(), AnimMcpPropertyRules::PropertyToJson(Resolved.Property, Resolved.Property->ContainerPtrToValuePtr<void>(Resolved.Container), Node));
			}
		}
		Obj->SetObjectField(TEXT("properties"), Properties);

		TArray<TSharedPtr<FJsonValue>> Pins;
		for (const UEdGraphPin* Pin : Node->Pins)
		{
			if (Pin)
			{
				Pins.Add(MakeShared<FJsonValueObject>(DescribePin(Pin)));
			}
		}
		Obj->SetArrayField(TEXT("pins"), Pins);

		TArray<TSharedPtr<FJsonValue>> SubGraphs;
		for (UEdGraph* Sub : Node->GetSubGraphs())
		{
			if (Sub)
			{
				SubGraphs.Add(MakeShared<FJsonValueString>(Sub->GraphGuid.ToString()));
			}
		}
		Obj->SetArrayField(TEXT("sub_graphs"), SubGraphs);
		return Obj;
	}

	TSharedRef<FJsonObject> BuildGraphStructure(UAnimBlueprint* Blueprint, UEdGraph* Graph, int32 Depth, FAnimMcpContext& Context)
	{
		check(Blueprint && Graph);

		// 대상 그래프 집합 — Depth 만큼 하위로
		TArray<FGraphRecord> Records;
		{
			struct FPending { UEdGraph* Graph; UEdGraph* Parent; int32 Level; };
			TArray<FPending> Queue;
			Queue.Add({ Graph, nullptr, 0 });
			TSet<UEdGraph*> Visited;
			while (Queue.Num() > 0)
			{
				const FPending Current = Queue[0];
				Queue.RemoveAt(0);
				if (!Current.Graph || Visited.Contains(Current.Graph))
				{
					continue;
				}
				Visited.Add(Current.Graph);
				Records.Add({ Current.Graph, Current.Parent });
				if (Depth < 0 || Current.Level < Depth)
				{
					for (UEdGraph* Sub : Current.Graph->SubGraphs)
					{
						Queue.Add({ Sub, Current.Graph, Current.Level + 1 });
					}
				}
			}
		}

		TArray<TSharedPtr<FJsonValue>> GraphArray, NodeArray, ConnectionArray;
		for (const FGraphRecord& Record : Records)
		{
			GraphArray.Add(MakeShared<FJsonValueObject>(DescribeGraph(Record)));
			for (UEdGraphNode* Node : Record.Graph->Nodes)
			{
				if (!Node)
				{
					continue;
				}
				NodeArray.Add(MakeShared<FJsonValueObject>(DescribeNode(Node)));
				for (const UEdGraphPin* Pin : Node->Pins)
				{
					if (!Pin || Pin->Direction != EGPD_Output)
					{
						continue;
					}
					for (const UEdGraphPin* Other : Pin->LinkedTo)
					{
						if (!Other || !Other->GetOwningNodeUnchecked())
						{
							continue;
						}
						TSharedRef<FJsonObject> From = AnimMcpJson::MakeObject();
						From->SetStringField(TEXT("node"), Node->NodeGuid.ToString());
						From->SetStringField(TEXT("pin"), Pin->PinName.ToString());
						TSharedRef<FJsonObject> To = AnimMcpJson::MakeObject();
						To->SetStringField(TEXT("node"), Other->GetOwningNodeUnchecked()->NodeGuid.ToString());
						To->SetStringField(TEXT("pin"), Other->PinName.ToString());
						TSharedRef<FJsonObject> Conn = AnimMcpJson::MakeObject();
						Conn->SetObjectField(TEXT("from"), From);
						Conn->SetObjectField(TEXT("to"), To);
						ConnectionArray.Add(MakeShared<FJsonValueObject>(Conn));
					}
				}
			}
		}

		// 상태머신 전용 뷰 — 조회 범위에 든 UAnimationStateMachineGraph 마다 (2026-10-15 확정: 새 Tool 대신 structure 응답 확장)
		TArray<TSharedPtr<FJsonValue>> StateMachines;
		for (const FGraphRecord& Record : Records)
		{
			if (UAnimationStateMachineGraph* SMGraph = Cast<UAnimationStateMachineGraph>(Record.Graph))
			{
				StateMachines.Add(MakeShared<FJsonValueObject>(DescribeStateMachine(SMGraph)));
			}
		}

		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetStringField(TEXT("schema_version"), TEXT("1.1"));
		Result->SetStringField(TEXT("asset_path"), Blueprint->GetPathName());
		Result->SetStringField(TEXT("revision"), ComputeRevision(Blueprint));
		Result->SetStringField(TEXT("root_graph_guid"), Graph->GraphGuid.ToString());
		Result->SetNumberField(TEXT("depth"), Depth);
		Result->SetArrayField(TEXT("graphs"), GraphArray);
		Result->SetArrayField(TEXT("nodes"), NodeArray);
		Result->SetArrayField(TEXT("connections"), ConnectionArray);
		Result->SetArrayField(TEXT("state_machines"), StateMachines);
		return Result;
	}

	namespace
	{
		/** 규칙 그래프 요약 — 전이와 conduit 가 같은 필드를 낸다 (Phase 6-1) */
		void WriteRuleFields(TSharedRef<FJsonObject>& Obj, UEdGraph* RuleGraph)
		{
			Obj->SetField(TEXT("rule_graph_guid"), RuleGraph ? AnimMcpJson::StringOrNull(RuleGraph->GraphGuid.ToString()) : MakeShared<FJsonValueNull>());
			// 도구가 만든 규칙이면 원문 복원 + 사람 편집 감지. 없으면 규칙 노드 수만
			const AnimMcpTransitionRule::FSource Source = AnimMcpTransitionRule::ReadSource(RuleGraph);
			Obj->SetBoolField(TEXT("rule_generated"), Source.bHasSource);
			TSharedPtr<FJsonValue> SourceValue = Source.Source.IsValid() ? TSharedPtr<FJsonValue>(MakeShared<FJsonValueObject>(Source.Source)) : TSharedPtr<FJsonValue>(MakeShared<FJsonValueNull>());
			Obj->SetField(TEXT("rule_source"), SourceValue);
			Obj->SetBoolField(TEXT("rule_modified"), Source.bHasSource && Source.bModified);
			TArray<UEdGraphNode*> RuleNodes;
			AnimMcpTransitionRule::CollectRuleNodes(RuleGraph, RuleNodes);
			Obj->SetNumberField(TEXT("rule_node_count"), RuleNodes.Num());
		}
	}

	TSharedRef<FJsonObject> DescribeStateMachine(UAnimationStateMachineGraph* Graph)
	{
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetStringField(TEXT("graph_guid"), Graph->GraphGuid.ToString());
		Obj->SetStringField(TEXT("name"), Graph->GetName());
		UEdGraphNode* Owner = FindOwnerNode(Graph);
		Obj->SetField(TEXT("node_guid"), Owner ? AnimMcpJson::StringOrNull(Owner->NodeGuid.ToString()) : MakeShared<FJsonValueNull>());

		UEdGraphNode* EntryTarget = Graph->EntryNode ? Graph->EntryNode->GetOutputNode() : nullptr;
		Obj->SetField(TEXT("entry_node_guid"), Graph->EntryNode ? AnimMcpJson::StringOrNull(Graph->EntryNode->NodeGuid.ToString()) : MakeShared<FJsonValueNull>());
		Obj->SetField(TEXT("entry_state"), EntryTarget ? AnimMcpJson::StringOrNull(EntryTarget->NodeGuid.ToString()) : MakeShared<FJsonValueNull>());

		TArray<TSharedPtr<FJsonValue>> States, Transitions;
		for (UEdGraphNode* Node : Graph->Nodes)
		{
			UAnimStateNodeBase* StateBase = Cast<UAnimStateNodeBase>(Node);
			if (!StateBase)
			{
				continue;
			}
			if (UAnimStateTransitionNode* Transition = Cast<UAnimStateTransitionNode>(Node))
			{
				TSharedRef<FJsonObject> T = AnimMcpJson::MakeObject();
				T->SetStringField(TEXT("node_guid"), Transition->NodeGuid.ToString());
				T->SetStringField(TEXT("name"), Transition->GetStateName());
				UAnimStateNodeBase* Prev = Transition->GetPreviousState();
				UAnimStateNodeBase* Next = Transition->GetNextState();
				T->SetField(TEXT("from"), Prev ? AnimMcpJson::StringOrNull(Prev->NodeGuid.ToString()) : MakeShared<FJsonValueNull>());
				T->SetField(TEXT("to"), Next ? AnimMcpJson::StringOrNull(Next->NodeGuid.ToString()) : MakeShared<FJsonValueNull>());
				T->SetField(TEXT("from_name"), Prev ? AnimMcpJson::StringOrNull(Prev->GetStateName()) : MakeShared<FJsonValueNull>());
				T->SetField(TEXT("to_name"), Next ? AnimMcpJson::StringOrNull(Next->GetStateName()) : MakeShared<FJsonValueNull>());
				T->SetNumberField(TEXT("priority_order"), Transition->PriorityOrder);
				T->SetNumberField(TEXT("crossfade_duration"), Transition->CrossfadeDuration);
				T->SetStringField(TEXT("blend_mode"), StaticEnum<EAlphaBlendOption>()->GetNameStringByValue(static_cast<int64>(Transition->BlendMode)));
				T->SetBoolField(TEXT("bidirectional"), Transition->Bidirectional);
				T->SetBoolField(TEXT("disabled"), Transition->bDisabled);
				T->SetBoolField(TEXT("automatic"), Transition->bAutomaticRuleBasedOnSequencePlayerInState);
				T->SetNumberField(TEXT("automatic_trigger_time"), Transition->AutomaticRuleTriggerTime);
				T->SetBoolField(TEXT("shared_rules"), Transition->bSharedRules);
				WriteRuleFields(T, Transition->BoundGraph);
				Transitions.Add(MakeShared<FJsonValueObject>(T));
			}
			else
			{
				TSharedRef<FJsonObject> S = AnimMcpJson::MakeObject();
				S->SetStringField(TEXT("node_guid"), StateBase->NodeGuid.ToString());
				S->SetStringField(TEXT("name"), StateBase->GetStateName());
				S->SetStringField(TEXT("class"), StateBase->GetClass()->GetName());
				const TCHAR* Kind = TEXT("state");
				if (Cast<UAnimStateConduitNode>(StateBase)) { Kind = TEXT("conduit"); }
				else if (Cast<UAnimStateAliasNode>(StateBase)) { Kind = TEXT("alias"); }
				S->SetStringField(TEXT("kind"), Kind);
				UEdGraph* Bound = StateBase->GetBoundGraph();
				S->SetField(TEXT("bound_graph_guid"), Bound ? AnimMcpJson::StringOrNull(Bound->GraphGuid.ToString()) : MakeShared<FJsonValueNull>());
				if (UAnimStateNode* StateNode = Cast<UAnimStateNode>(StateBase))
				{
					S->SetBoolField(TEXT("always_reset_on_entry"), StateNode->bAlwaysResetOnEntry);
				}
				// Phase 6-1 — conduit 는 규칙, alias 는 대상
				if (UAnimStateConduitNode* Conduit = Cast<UAnimStateConduitNode>(StateBase))
				{
					WriteRuleFields(S, Conduit->BoundGraph);
				}
				else if (UAnimStateAliasNode* Alias = Cast<UAnimStateAliasNode>(StateBase))
				{
					S->SetBoolField(TEXT("global"), Alias->bGlobalAlias);
					TArray<TSharedPtr<FJsonValue>> Targets, TargetNames;
					for (const TWeakObjectPtr<UAnimStateNodeBase>& Weak : Alias->GetAliasedStates())
					{
						if (UAnimStateNodeBase* Target = Weak.Get())
						{
							Targets.Add(MakeShared<FJsonValueString>(Target->NodeGuid.ToString()));
							TargetNames.Add(MakeShared<FJsonValueString>(Target->GetStateName()));
						}
					}
					S->SetArrayField(TEXT("aliased_states"), Targets);
					S->SetArrayField(TEXT("aliased_state_names"), TargetNames);
				}
				TArray<FString> Out, In;
				for (UEdGraphPin* Pin : StateBase->Pins)
				{
					if (!Pin)
					{
						continue;
					}
					for (UEdGraphPin* Other : Pin->LinkedTo)
					{
						if (UAnimStateTransitionNode* T = Other ? Cast<UAnimStateTransitionNode>(Other->GetOwningNodeUnchecked()) : nullptr)
						{
							(Pin->Direction == EGPD_Output ? Out : In).Add(T->NodeGuid.ToString());
						}
					}
				}
				TArray<TSharedPtr<FJsonValue>> OutArr, InArr;
				for (const FString& G : Out) { OutArr.Add(MakeShared<FJsonValueString>(G)); }
				for (const FString& G : In) { InArr.Add(MakeShared<FJsonValueString>(G)); }
				S->SetArrayField(TEXT("outgoing_transitions"), OutArr);
				S->SetArrayField(TEXT("incoming_transitions"), InArr);
				States.Add(MakeShared<FJsonValueObject>(S));
			}
		}
		Obj->SetArrayField(TEXT("states"), States);
		Obj->SetArrayField(TEXT("transitions"), Transitions);
		return Obj;
	}

	TSharedRef<FJsonObject> BuildBlueprintInfo(UAnimBlueprint* Blueprint, FAnimMcpContext& Context)
	{
		check(Blueprint);
		TSharedRef<FJsonObject> Info = AnimMcpJson::MakeObject();
		Info->SetStringField(TEXT("asset_path"), Blueprint->GetPathName());
		Info->SetStringField(TEXT("revision"), ComputeRevision(Blueprint));
		Info->SetField(TEXT("parent_class"), AnimMcpJson::ObjectPathOrNull(Blueprint->ParentClass));
		Info->SetField(TEXT("parent_anim_blueprint"), AnimMcpJson::ObjectPathOrNull(UAnimBlueprint::GetParentAnimBlueprint(Blueprint)));
		Info->SetBoolField(TEXT("is_template"), Blueprint->bIsTemplate);
		Info->SetField(TEXT("target_skeleton"), AnimMcpJson::ObjectPathOrNull(Blueprint->TargetSkeleton));
		// (7-2) 스켈레톤의 블렌드 프로파일/마스크 — set_property BlendProfile · DefaultBlendProfile · BlendMasks 의 값(경로)
		{
			TArray<TSharedPtr<FJsonValue>> Profiles;
			if (const USkeleton* Skeleton = Blueprint->TargetSkeleton)
			{
				for (const TObjectPtr<UBlendProfile>& Profile : Skeleton->BlendProfiles)
				{
					if (!Profile) { continue; }
					TSharedRef<FJsonObject> P = AnimMcpJson::MakeObject();
					P->SetStringField(TEXT("name"), Profile->GetName());
					P->SetStringField(TEXT("path"), Profile->GetPathName());
					P->SetStringField(TEXT("mode"), StaticEnum<EBlendProfileMode>()->GetNameStringByValue(static_cast<int64>(Profile->GetMode())));
					P->SetBoolField(TEXT("is_blend_mask"), Profile->IsBlendMask());
					Profiles.Add(MakeShared<FJsonValueObject>(P));
				}
			}
			Info->SetArrayField(TEXT("skeleton_blend_profiles"), Profiles);
		}
		// (7-3) 스켈레톤의 슬롯 그룹 — Slot 노드 SlotName · set_montage_slots · add_skeleton_slot 의 대상
		Info->SetArrayField(TEXT("skeleton_slot_groups"), AnimMcpMontage::SlotGroupsArray(Blueprint->TargetSkeleton));
		Info->SetField(TEXT("preview_mesh"), AnimMcpJson::ObjectPathOrNull(Blueprint->GetPreviewMesh()));
		Info->SetStringField(TEXT("blueprint_type"), StaticEnum<EBlueprintType>()->GetNameStringByValue(static_cast<int64>(Blueprint->BlueprintType)));
		Info->SetStringField(TEXT("status"), StaticEnum<EBlueprintStatus>()->GetNameStringByValue(static_cast<int64>(Blueprint->Status)));

		// 그래프 트리
		TArray<FGraphRecord> Graphs;
		CollectGraphs(Blueprint, Graphs);
		TArray<TSharedPtr<FJsonValue>> GraphArray;
		int32 LinkedAnimLayerCount = 0;
		TArray<TSharedPtr<FJsonValue>> LinkedLayerPaths;
		for (const FGraphRecord& Record : Graphs)
		{
			GraphArray.Add(MakeShared<FJsonValueObject>(DescribeGraph(Record)));
			for (UEdGraphNode* Node : Record.Graph->Nodes)
			{
				if (UAnimGraphNode_LinkedAnimLayer* Layer = Cast<UAnimGraphNode_LinkedAnimLayer>(Node))
				{
					++LinkedAnimLayerCount;
					LinkedLayerPaths.Add(MakeShared<FJsonValueString>(Record.Graph->GraphGuid.ToString() + TEXT(":") + Layer->NodeGuid.ToString()));
				}
			}
		}
		Info->SetArrayField(TEXT("graphs"), GraphArray);

		UEdGraph* RootAnimGraph = FindRootAnimGraph(Blueprint);
		Info->SetField(TEXT("anim_graph_guid"), RootAnimGraph ? AnimMcpJson::StringOrNull(RootAnimGraph->GraphGuid.ToString()) : MakeShared<FJsonValueNull>());
		if (!RootAnimGraph && Blueprint->BlueprintType != BPTYPE_Interface)
		{
			Context.AddDiagnostic(TEXT("error"), TEXT("NO_ANIM_GRAPH"), TEXT("No root AnimGraph found in this Animation Blueprint"));
		}

		// 변수 — Transition Rule 이 참조할 수 있는 BlueprintVisible 프로퍼티 (네이티브 부모 + BP 변수)
		TArray<TSharedPtr<FJsonValue>> Variables;
		UClass* QueryClass = Blueprint->SkeletonGeneratedClass ? Blueprint->SkeletonGeneratedClass.Get() : Blueprint->GeneratedClass.Get();
		if (!QueryClass)
		{
			QueryClass = Blueprint->ParentClass;
		}
		if (QueryClass)
		{
			for (TFieldIterator<FProperty> It(QueryClass, EFieldIteratorFlags::IncludeSuper); It; ++It)
			{
				FProperty* Property = *It;
				if (!Property->HasAnyPropertyFlags(CPF_BlueprintVisible))
				{
					continue;
				}
				TSharedRef<FJsonObject> Var = AnimMcpJson::MakeObject();
				Var->SetStringField(TEXT("name"), Property->GetName());
				Var->SetStringField(TEXT("cpp_type"), Property->GetCPPType());
				FEdGraphPinType PinType;
				if (GetDefault<UEdGraphSchema_K2>()->ConvertPropertyToPinType(Property, PinType))
				{
					Var->SetStringField(TEXT("pin_category"), PinType.PinCategory.ToString());
					Var->SetStringField(TEXT("pin_subcategory"), PinType.PinSubCategory.ToString());
				}
				UClass* OwnerClass = Property->GetOwnerClass();
				const bool bNative = OwnerClass && OwnerClass->HasAnyClassFlags(CLASS_Native);
				Var->SetStringField(TEXT("source"), bNative ? TEXT("native") : TEXT("blueprint"));
				Var->SetField(TEXT("owner_class"), AnimMcpJson::ObjectPathOrNull(OwnerClass));
				Var->SetBoolField(TEXT("read_only"), Property->HasAnyPropertyFlags(CPF_BlueprintReadOnly));
				// (7-1) 이 BP 가 선언한 변수면 선언 정보 {type, default_value, category, instance_editable}
				const TSharedPtr<FJsonObject> Declaration = bNative ? nullptr : AnimMcpVariables::DescribeDeclaration(Blueprint, Property->GetFName());
				TSharedPtr<FJsonValue> DeclarationValue = Declaration.IsValid() ? TSharedPtr<FJsonValue>(MakeShared<FJsonValueObject>(Declaration)) : TSharedPtr<FJsonValue>(MakeShared<FJsonValueNull>());
				Var->SetField(TEXT("declaration"), DeclarationValue);
				Variables.Add(MakeShared<FJsonValueObject>(Var));
			}
		}
		Info->SetArrayField(TEXT("variables"), Variables);

		Info->SetNumberField(TEXT("linked_anim_layer_count"), LinkedAnimLayerCount);
		Info->SetArrayField(TEXT("linked_anim_layers"), LinkedLayerPaths);
		// Phase 6-4b — 구현한 인터페이스와 레이어 그래프(인터페이스 BP 자신의 레이어 포함)
		Info->SetArrayField(TEXT("implemented_interfaces"), AnimMcpAnimLayer::DescribeImplementedInterfaces(Blueprint));
		Info->SetArrayField(TEXT("layers"), AnimMcpAnimLayer::DescribeLayers(Blueprint));
		// Phase 7-1 — BlueprintThreadSafeUpdateAnimation 오버라이드 (없으면 null)
		Info->SetField(TEXT("update_function"), AnimMcpUpdateFunction::Describe(Blueprint));

		if (!Blueprint->bIsTemplate && !Blueprint->TargetSkeleton)
		{
			Context.AddDiagnostic(TEXT("warning"), TEXT("NO_SKELETON"), TEXT("Animation Blueprint has no TargetSkeleton and is not a template"));
		}

		return Info;
	}
}
