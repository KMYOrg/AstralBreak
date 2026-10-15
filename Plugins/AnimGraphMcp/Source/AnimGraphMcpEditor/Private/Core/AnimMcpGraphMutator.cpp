#include "AnimMcpGraphMutator.h"

#include "AnimGraphNode_AssetPlayerBase.h"
#include "AnimGraphNode_Base.h"
#include "AnimGraphNode_BlendListByEnum.h"
#include "AnimGraphNode_LayeredBoneBlend.h"
#include "AnimGraphNode_SaveCachedPose.h"
#include "AnimGraphNode_UseCachedPose.h"
#include "AnimMcpGraphInspector.h"
#include "AnimMcpLog.h"
#include "AnimMcpPropertyRules.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimationAsset.h"
#include "Animation/Skeleton.h"
#include "Bridge/AnimMcpTypes.h"
#include "Dom/JsonValue.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraph/EdGraphSchema.h"
#include "EdGraphSchema_K2.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "UObject/UObjectGlobals.h"
#include "UObject/UnrealType.h"

namespace AnimMcpGraphMutator
{
	bool ParseGuid(const FString& Text, FGuid& OutGuid, FAnimMcpError& OutError, const TCHAR* What)
	{
		if (Text.IsEmpty() || !FGuid::Parse(Text, OutGuid))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("%s '%s' is not a valid GUID"), What, *Text));
			return false;
		}
		return true;
	}

	UEdGraph* FindGraph(UAnimBlueprint* Blueprint, const FString& GraphGuid, FAnimMcpError& OutError)
	{
		FGuid Guid;
		if (!ParseGuid(GraphGuid, Guid, OutError, TEXT("graph")))
		{
			return nullptr;
		}
		UEdGraph* Graph = AnimMcpGraphInspector::FindGraphByGuid(Blueprint, Guid);
		if (!Graph)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::GraphNotFound, FString::Printf(TEXT("No graph with guid %s in %s"), *GraphGuid, *Blueprint->GetPathName()));
		}
		return Graph;
	}

	UEdGraphNode* FindNode(UAnimBlueprint* Blueprint, const FString& NodeGuid, FAnimMcpError& OutError)
	{
		FGuid Guid;
		if (!ParseGuid(NodeGuid, Guid, OutError, TEXT("node")))
		{
			return nullptr;
		}
		UEdGraphNode* Node = AnimMcpGraphInspector::FindNodeByGuid(Blueprint, Guid);
		if (!Node)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::NodeNotFound, FString::Printf(TEXT("No node with guid %s in %s"), *NodeGuid, *Blueprint->GetPathName()));
		}
		return Node;
	}

	UEdGraphPin* FindPin(UEdGraphNode* Node, const FString& PinName, FAnimMcpError& OutError)
	{
		UEdGraphPin* Pin = Node ? Node->FindPin(PinName) : nullptr;
		if (!Pin)
		{
			TArray<FString> Available;
			if (Node)
			{
				for (UEdGraphPin* P : Node->Pins)
				{
					if (P)
					{
						Available.Add(FString::Printf(TEXT("%s(%s)"), *P->PinName.ToString(), P->Direction == EGPD_Input ? TEXT("in") : TEXT("out")));
					}
				}
			}
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("available_pins"), FString::Join(Available, TEXT(", ")));
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PinNotFound, FString::Printf(TEXT("Node %s has no pin '%s'"), Node ? *Node->NodeGuid.ToString() : TEXT("?"), *PinName), Details);
		}
		return Pin;
	}

	UClass* ResolveNodeClass(const FString& InClassName, FAnimMcpError& OutError)
	{
		const FString ClassName = InClassName.TrimStartAndEnd();
		UClass* Found = nullptr;
		if (ClassName.StartsWith(TEXT("/Script/")))
		{
			Found = FindObject<UClass>(nullptr, *ClassName);
		}
		else if (!ClassName.IsEmpty())
		{
			Found = FindFirstObject<UClass>(*ClassName, EFindFirstObjectOptions::None, ELogVerbosity::Warning, TEXT("AnimGraphMcp ResolveNodeClass"));
			if (!Found && !ClassName.StartsWith(TEXT("AnimGraphNode_")))
			{
				Found = FindFirstObject<UClass>(*(TEXT("AnimGraphNode_") + ClassName), EFindFirstObjectOptions::None, ELogVerbosity::Warning, TEXT("AnimGraphMcp ResolveNodeClass"));
			}
		}

		if (!Found)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Node class '%s' not found"), *ClassName));
			return nullptr;
		}
		if (!Found->IsChildOf(UAnimGraphNode_Base::StaticClass()) || Found->HasAnyClassFlags(CLASS_Abstract))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' is not a concrete UAnimGraphNode_Base subclass"), *Found->GetPathName()));
			return nullptr;
		}
		return Found;
	}

	bool ValidateNodeAsset(UClass* NodeClass, UAnimationAsset* Asset, UAnimBlueprint* Blueprint, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		if (!Asset)
		{
			return true;
		}
		const UAnimGraphNode_Base* NodeCDO = NodeClass ? NodeClass->GetDefaultObject<UAnimGraphNode_Base>() : nullptr;
		if (!NodeCDO || !NodeClass->IsChildOf(UAnimGraphNode_AssetPlayerBase::StaticClass()))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Node class %s is not an asset player; 'asset' is not accepted"), NodeClass ? *NodeClass->GetName() : TEXT("?")));
			return false;
		}
		if (NodeCDO->SupportsAssetClass(Asset->GetClass()) == EAnimAssetHandlerType::NotSupported)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Node class %s does not accept assets of class %s"), *NodeClass->GetName(), *Asset->GetClass()->GetName()));
			return false;
		}
		if (Blueprint && Blueprint->TargetSkeleton && Asset->GetSkeleton() && Asset->GetSkeleton() != Blueprint->TargetSkeleton)
		{
			TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
			Extra->SetStringField(TEXT("asset"), Asset->GetPathName());
			Extra->SetStringField(TEXT("asset_skeleton"), Asset->GetSkeleton()->GetPathName());
			Extra->SetStringField(TEXT("blueprint_skeleton"), Blueprint->TargetSkeleton->GetPathName());
			Context.AddDiagnostic(TEXT("warning"), TEXT("SKELETON_MISMATCH"), TEXT("Animation asset skeleton differs from the Blueprint's TargetSkeleton; compile may fail"), Extra);
		}
		return true;
	}

	bool ValidateConnection(UEdGraphPin* A, UEdGraphPin* B, FAnimMcpError& OutError)
	{
		if (!A || !B)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PinNotFound, TEXT("Connection endpoint pin is null"));
			return false;
		}
		UEdGraphNode* NodeA = A->GetOwningNodeUnchecked();
		UEdGraphNode* NodeB = B->GetOwningNodeUnchecked();
		if (!NodeA || !NodeB || !NodeA->GetGraph() || NodeA->GetGraph() != NodeB->GetGraph())
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::ConnectionRejected, TEXT("Pins must belong to nodes in the same graph"));
			return false;
		}
		const UEdGraphSchema* Schema = NodeA->GetGraph()->GetSchema();
		const FPinConnectionResponse Response = Schema->CanCreateConnection(A, B);
		switch (Response.Response)
		{
		case CONNECT_RESPONSE_MAKE:
		case CONNECT_RESPONSE_MAKE_WITH_PROMOTION:
		case CONNECT_RESPONSE_BREAK_OTHERS_A:
		case CONNECT_RESPONSE_BREAK_OTHERS_B:
		case CONNECT_RESPONSE_BREAK_OTHERS_AB:
			return true;
		case CONNECT_RESPONSE_MAKE_WITH_CONVERSION_NODE:
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::ConnectionRejected, FString::Printf(TEXT("Connection %s.%s -> %s.%s needs a conversion node; add it explicitly"), *NodeA->NodeGuid.ToString(), *A->PinName.ToString(), *NodeB->NodeGuid.ToString(), *B->PinName.ToString()));
			return false;
		default:
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::ConnectionRejected, FString::Printf(TEXT("Connection %s.%s -> %s.%s rejected: %s"), *NodeA->NodeGuid.ToString(), *A->PinName.ToString(), *NodeB->NodeGuid.ToString(), *B->PinName.ToString(), *Response.Message.ToString()));
			return false;
		}
	}

	UAnimGraphNode_Base* AddNode(UEdGraph* Graph, UClass* NodeClass, const FVector2D& Position, UAnimationAsset* Asset, FAnimMcpError& OutError)
	{
		if (!Graph || !NodeClass)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("AddNode called without graph or class"));
			return nullptr;
		}

		Graph->Modify();

		FGraphNodeCreator<UAnimGraphNode_Base> Creator(*Graph);
		UAnimGraphNode_Base* Node = Creator.CreateNode(/*bSelectNewNode*/ false, NodeClass);
		if (!Node)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("Failed to create node of class %s"), *NodeClass->GetName()));
			return nullptr;
		}
		Node->NodePosX = static_cast<int32>(Position.X);
		Node->NodePosY = static_cast<int32>(Position.Y);
		Creator.Finalize();

		if (Asset)
		{
			if (UAnimGraphNode_AssetPlayerBase* Player = Cast<UAnimGraphNode_AssetPlayerBase>(Node))
			{
				Player->Modify();
				Player->SetAnimationAsset(Asset);
			}
		}

		UE_LOG(LogAnimGraphMcp, Verbose, TEXT("Added %s %s to graph %s"), *NodeClass->GetName(), *Node->NodeGuid.ToString(), *Graph->GetName());
		return Node;
	}

	bool Connect(UEdGraphPin* A, UEdGraphPin* B, FAnimMcpError& OutError)
	{
		if (!ValidateConnection(A, B, OutError))
		{
			return false;
		}
		UEdGraphNode* NodeA = A->GetOwningNode();
		UEdGraphNode* NodeB = B->GetOwningNode();
		NodeA->Modify();
		NodeB->Modify();
		const UEdGraphSchema* Schema = NodeA->GetGraph()->GetSchema();
		if (!Schema->TryCreateConnection(A, B))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::ConnectionRejected, FString::Printf(TEXT("TryCreateConnection failed for %s.%s -> %s.%s"), *NodeA->NodeGuid.ToString(), *A->PinName.ToString(), *NodeB->NodeGuid.ToString(), *B->PinName.ToString()));
			return false;
		}
		return true;
	}

	//~ Phase 3

	bool ValidateLinked(UEdGraphPin* A, UEdGraphPin* B, FAnimMcpError& OutError)
	{
		if (!A || !B)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PinNotFound, TEXT("disconnect endpoint pin is null"));
			return false;
		}
		if (!A->LinkedTo.Contains(B))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Pins %s.%s and %s.%s are not linked"),
				*A->GetOwningNode()->NodeGuid.ToString(), *A->PinName.ToString(), *B->GetOwningNode()->NodeGuid.ToString(), *B->PinName.ToString()));
			return false;
		}
		return true;
	}

	bool Disconnect(UEdGraphPin* A, UEdGraphPin* B, FAnimMcpError& OutError)
	{
		if (!ValidateLinked(A, B, OutError))
		{
			return false;
		}
		UEdGraphNode* NodeA = A->GetOwningNode();
		NodeA->Modify();
		B->GetOwningNode()->Modify();
		NodeA->GetGraph()->GetSchema()->BreakSinglePinLink(A, B);
		return true;
	}

	void DisconnectAll(UEdGraphPin* Pin)
	{
		if (!Pin || Pin->LinkedTo.Num() == 0)
		{
			return;
		}
		UEdGraphNode* Node = Pin->GetOwningNode();
		Node->Modify();
		for (UEdGraphPin* Other : Pin->LinkedTo)
		{
			if (Other && Other->GetOwningNodeUnchecked())
			{
				Other->GetOwningNodeUnchecked()->Modify();
			}
		}
		Node->GetGraph()->GetSchema()->BreakPinLinks(*Pin, /*bSendsNodeNotifcation*/ true);
	}

	bool ValidateRemovable(UEdGraphNode* Node, FAnimMcpError& OutError)
	{
		if (!Node)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::NodeNotFound, TEXT("remove_node target is null"));
			return false;
		}
		if (!Node->CanUserDeleteNode())
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Node %s (%s) cannot be deleted (result/root/entry nodes are fixed)"), *Node->NodeGuid.ToString(), *Node->GetClass()->GetName()));
			return false;
		}
		return true;
	}

	void DetachNode(UEdGraphNode* Node)
	{
		UEdGraph* Graph = Node->GetGraph();
		Graph->Modify();
		Node->Modify();
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (!Pin)
			{
				continue;
			}
			for (UEdGraphPin* Other : Pin->LinkedTo)
			{
				if (Other && Other->GetOwningNodeUnchecked())
				{
					Other->GetOwningNodeUnchecked()->Modify();
				}
			}
		}
		// Nodes 배열에서만 제거 + 링크 끊기. 객체·서브그래프는 그대로 — 롤백이 ReattachNode 로 되돌릴 수 있다
		Graph->RemoveNode(Node, /*bBreakAllLinks*/ true);
	}

	void ReattachNode(UEdGraph* Graph, UEdGraphNode* Node)
	{
		Graph->Modify();
		Graph->AddNode(Node, /*bUserAction*/ false, /*bSelectNewNode*/ false);
	}

	void FinalizeRemoval(UEdGraphNode* Node)
	{
		// 이미 Nodes 에서 빠져 있다 — DestroyNode 는 RemoveNode 를 다시 부르지만(0건 제거) 서브그래프 제거·포즈 워치 정리 등 파생 클래스 후처리를 수행한다
		Node->Modify();
		Node->DestroyNode();
	}

	namespace
	{
		bool ImportPropertyText(UEdGraphNode* Node, const AnimMcpPropertyRules::FResolved& Resolved, const FString& ImportText, FAnimMcpError& OutError)
		{
			void* ValuePtr = Resolved.Property->ContainerPtrToValuePtr<void>(Resolved.Container);
			FProperty* EditProperty = Resolved.MemberProperty ? static_cast<FProperty*>(Resolved.MemberProperty) : Resolved.Property;

			Node->Modify();
			Node->PreEditChange(EditProperty);

			FString OldText;
			Resolved.Property->ExportText_Direct(OldText, ValuePtr, nullptr, Node, PPF_None);

			const TCHAR* Result = Resolved.Property->ImportText_Direct(*ImportText, ValuePtr, Node, PPF_None, GLog);
			if (!Result)
			{
				// 실패하면 부분 수정이 없도록 되돌린다
				Resolved.Property->ImportText_Direct(*OldText, ValuePtr, Node, PPF_None, GLog);
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' rejected value '%s' (type %s)"), *Resolved.Property->GetName(), *ImportText, *Resolved.Property->GetCPPType()));
				return false;
			}

			FPropertyChangedEvent Event(Resolved.Property, EPropertyChangeType::ValueSet);
			if (Resolved.MemberProperty)
			{
				Event.SetActiveMemberProperty(Resolved.MemberProperty);
			}
			Node->PostEditChangeProperty(Event);

			// 핀이 노출돼 있으면 핀 기본값이 진실이다 — 컴파일이 핀 → 구조체로 복사하고, 핀을 숨길 때도 핀 → 구조체로 되돌린다
			// (AnimBlueprintNodeOptionalPinManager.cpp:108-121). 구조체만 바꾸면 컴파일에서 덮어쓰이므로 연결되지 않은 노출 핀도 같은 값으로 맞춘다
			if (Resolved.MemberProperty && !CastField<FArrayProperty>(Resolved.Property))
			{
				if (UEdGraphPin* Pin = Node->FindPin(Resolved.Property->GetFName(), EGPD_Input); Pin && Pin->LinkedTo.Num() == 0 && !Pin->bOrphanedPin)
				{
					FString Literal;
					FBlueprintEditorUtils::PropertyValueToString_Direct(Resolved.Property, static_cast<const uint8*>(ValuePtr), Literal, Node);
					GetDefault<UEdGraphSchema_K2>()->TrySetDefaultValue(*Pin, Literal);
				}
			}
			return true;
		}
	}

	bool SetPropertyFromJson(UEdGraphNode* Node, FName Property, const TSharedPtr<FJsonValue>& Value, FString& OutOldText, FAnimMcpError& OutError)
	{
		AnimMcpPropertyRules::FResolved Resolved;
		if (!AnimMcpPropertyRules::ResolveOnNode(Node, Property, Resolved, OutError))
		{
			return false;
		}
		if (Resolved.Rule->bReadOnly)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, FString::Printf(TEXT("Property '%s' is read-only"), *Property.ToString()));
			return false;
		}
		if (Resolved.Rule->Scope == AnimMcpPropertyRules::EScope::NodeRef)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("'%s' is a node reference; use SetCachedPoseSource"), *Property.ToString()));
			return false;
		}
		FString ImportText;
		if (!AnimMcpPropertyRules::JsonToImportText(Resolved.Property, Value, ImportText, OutError))
		{
			return false;
		}
		Resolved.Property->ExportText_Direct(OutOldText, Resolved.Property->ContainerPtrToValuePtr<void>(Resolved.Container), nullptr, Node, PPF_None);
		return ImportPropertyText(Node, Resolved, ImportText, OutError);
	}

	bool SetPropertyFromText(UEdGraphNode* Node, FName Property, const FString& ImportText, FAnimMcpError& OutError)
	{
		AnimMcpPropertyRules::FResolved Resolved;
		if (!AnimMcpPropertyRules::ResolveOnNode(Node, Property, Resolved, OutError) || !Resolved.Property)
		{
			return false;
		}
		return ImportPropertyText(Node, Resolved, ImportText, OutError);
	}

	bool ValidatePropertyOnClass(const UClass* NodeClass, FName Property, const TSharedPtr<FJsonValue>& Value, FAnimMcpError& OutError)
	{
		AnimMcpPropertyRules::FResolved Resolved;
		if (!AnimMcpPropertyRules::ResolveOnClass(NodeClass, Property, Resolved, OutError))
		{
			return false;
		}
		if (Resolved.Rule->bReadOnly)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, FString::Printf(TEXT("Property '%s' is read-only"), *Property.ToString()));
			return false;
		}
		if (Resolved.Rule->Scope == AnimMcpPropertyRules::EScope::NodeRef)
		{
			// 값은 노드 참조 — 형태만 확인 (해석은 Operations 가 ref 표로)
			if (!Value.IsValid() || (Value->Type != EJson::String && Value->Type != EJson::Object))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' expects a node reference: \"<guid>\" or {\"node\"|\"ref\"}"), *Property.ToString()));
				return false;
			}
			return true;
		}
		FString Unused;
		return AnimMcpPropertyRules::JsonToImportText(Resolved.Property, Value, Unused, OutError);
	}

	namespace
	{
		/** FAnimNode 구조체 안의 애셋 참조 프로퍼티 (Sequence · BlendSpace …) — null 로 되돌릴 때 SetAnimationAsset 이 무시하므로 직접 쓴다 */
		FObjectProperty* FindAssetProperty(UAnimGraphNode_Base* Node, void*& OutContainer)
		{
			OutContainer = nullptr;
			FStructProperty* NodeProp = Node ? Node->GetFNodeProperty() : nullptr;
			if (!NodeProp)
			{
				return nullptr;
			}
			OutContainer = NodeProp->ContainerPtrToValuePtr<void>(Node);
			for (TFieldIterator<FObjectProperty> It(NodeProp->Struct); It; ++It)
			{
				if (It->PropertyClass && It->PropertyClass->IsChildOf(UAnimationAsset::StaticClass()))
				{
					return *It;
				}
			}
			return nullptr;
		}
	}

	bool SetAsset(UAnimGraphNode_Base* Node, UAnimationAsset* Asset, UAnimationAsset*& OutOld, FAnimMcpError& OutError)
	{
		UAnimGraphNode_AssetPlayerBase* Player = Cast<UAnimGraphNode_AssetPlayerBase>(Node);
		if (!Player || !Asset)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("set_asset needs an asset player node and a non-null asset"));
			return false;
		}
		OutOld = Player->GetAnimationAsset();
		Player->Modify();
		Player->SetAnimationAsset(Asset);
		if (Player->GetAnimationAsset() != Asset)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("%s did not accept asset %s"), *Node->GetClass()->GetName(), *Asset->GetPathName()));
			return false;
		}
		return true;
	}

	void RestoreAsset(UAnimGraphNode_Base* Node, UAnimationAsset* Old)
	{
		if (!Node)
		{
			return;
		}
		Node->Modify();
		if (Old)
		{
			if (UAnimGraphNode_AssetPlayerBase* Player = Cast<UAnimGraphNode_AssetPlayerBase>(Node))
			{
				Player->SetAnimationAsset(Old);
				return;
			}
		}
		void* Container = nullptr;
		if (FObjectProperty* AssetProp = FindAssetProperty(Node, Container))
		{
			AssetProp->SetObjectPropertyValue(AssetProp->ContainerPtrToValuePtr<void>(Container), Old);
		}
	}

	int32 FindOptionalPinIndex(UAnimGraphNode_Base* Node, FName Property, FAnimMcpError& OutError)
	{
		if (!Node)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("expose_pin needs an AnimGraph node"));
			return INDEX_NONE;
		}
		TArray<FString> Toggleable;
		for (int32 i = 0; i < Node->ShowPinForProperties.Num(); ++i)
		{
			const FOptionalPinFromProperty& Optional = Node->ShowPinForProperties[i];
			if (Optional.bCanToggleVisibility)
			{
				Toggleable.Add(Optional.PropertyName.ToString());
			}
			if (Optional.PropertyName == Property)
			{
				if (!Optional.bCanToggleVisibility)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, FString::Printf(TEXT("Pin '%s' on %s cannot toggle visibility"), *Property.ToString(), *Node->GetClass()->GetName()));
					return INDEX_NONE;
				}
				return i;
			}
		}
		TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
		Details->SetStringField(TEXT("toggleable"), FString::Join(Toggleable, TEXT(", ")));
		OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PinNotFound, FString::Printf(TEXT("%s has no optional pin for property '%s'"), *Node->GetClass()->GetName(), *Property.ToString()), Details);
		return INDEX_NONE;
	}

	bool SetPinVisible(UAnimGraphNode_Base* Node, FName Property, bool bVisible, FAnimMcpError& OutError, bool* bOutChanged)
	{
		const int32 Index = FindOptionalPinIndex(Node, Property, OutError);
		if (Index == INDEX_NONE)
		{
			return false;
		}
		const bool bChanged = (Node->ShowPinForProperties[Index].bShowPin != bVisible);
		if (bOutChanged)
		{
			*bOutChanged = bChanged;
		}
		if (bChanged)
		{
			Node->Modify();
			// 내부에서 ReconstructNode — 이 노드의 모든 핀 포인터가 무효가 된다
			Node->SetPinVisibility(bVisible, Index);
		}
		return true;
	}

	bool SetCachedPoseSource(UEdGraphNode* UseNode, UEdGraphNode* SaveNode, UEdGraphNode*& OutOld, FAnimMcpError& OutError)
	{
		UAnimGraphNode_UseCachedPose* Use = Cast<UAnimGraphNode_UseCachedPose>(UseNode);
		UAnimGraphNode_SaveCachedPose* Save = Cast<UAnimGraphNode_SaveCachedPose>(SaveNode);
		if (!Use)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("SaveCachedPoseNode can only be set on AnimGraphNode_UseCachedPose"));
			return false;
		}
		if (!Save)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("SaveCachedPoseNode must reference an AnimGraphNode_SaveCachedPose (got %s)"), SaveNode ? *SaveNode->GetClass()->GetName() : TEXT("null")));
			return false;
		}
		if (FBlueprintEditorUtils::FindBlueprintForNode(Use) != FBlueprintEditorUtils::FindBlueprintForNode(Save))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("UseCachedPose and SaveCachedPose must be in the same Animation Blueprint"));
			return false;
		}
		OutOld = Use->SaveCachedPoseNode.Get();
		Use->Modify();
		Use->SaveCachedPoseNode = Save;
		return true;
	}

	void RestoreCachedPoseSource(UEdGraphNode* UseNode, UEdGraphNode* Old)
	{
		if (UAnimGraphNode_UseCachedPose* Use = Cast<UAnimGraphNode_UseCachedPose>(UseNode))
		{
			Use->Modify();
			Use->SaveCachedPoseNode = Cast<UAnimGraphNode_SaveCachedPose>(Old);
		}
	}

	namespace
	{
		/**
		 * UAnimGraphNode_BlendListByEnum::VisibleEnumEntries 는 protected UPROPERTY() 라 리플렉션으로 읽고 쓴다
		 * (AnimGraphNode_BlendListByEnum.h:23-29). BoundEnum 은 공개 가상 GetEnum()/ReloadEnum() 으로
		 */
		TArray<FName>* VisibleEnumEntriesOf(UAnimGraphNode_BlendListByEnum* Node)
		{
			static FArrayProperty* Property = CastField<FArrayProperty>(UAnimGraphNode_BlendListByEnum::StaticClass()->FindPropertyByName(TEXT("VisibleEnumEntries")));
			return Property ? Property->ContainerPtrToValuePtr<TArray<FName>>(Node) : nullptr;
		}
	}

	bool SetBlendListEnum(UEdGraphNode* Node, UEnum* Enum, FAnimMcpError& OutError)
	{
		UAnimGraphNode_BlendListByEnum* BlendNode = Cast<UAnimGraphNode_BlendListByEnum>(Node);
		if (!BlendNode)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("'enum' is only accepted for AnimGraphNode_BlendListByEnum"));
			return false;
		}
		if (!Enum)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("'enum' did not resolve to a UEnum"));
			return false;
		}
		BlendNode->Modify();
		// ReloadEnum = BoundEnum 설정 + 제목 캐시 무효화 (AnimGraphNode_BlendListByEnum.cpp:352)
		BlendNode->ReloadEnum(Enum);
		BlendNode->ReconstructNode();
		return true;
	}

	bool ValidateAddBlendPose(UEdGraphNode* Node, const FString& EnumEntry, FAnimMcpError& OutError)
	{
		if (Cast<UAnimGraphNode_LayeredBoneBlend>(Node))
		{
			return true;
		}
		if (UAnimGraphNode_BlendListByEnum* BlendNode = Cast<UAnimGraphNode_BlendListByEnum>(Node))
		{
			UEnum* BoundEnum = BlendNode->GetEnum();
			if (!BoundEnum)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("BlendListByEnum has no enum bound; create it with 'enum' first"));
				return false;
			}
			if (EnumEntry.IsEmpty())
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("add_blend_pose on BlendListByEnum requires 'entry' (enum element name)"));
				return false;
			}
			const int32 EnumIndex = BoundEnum->GetIndexByNameString(EnumEntry);
			// 마지막 항목(_MAX)은 에디터 메뉴도 제외한다
			if (EnumIndex == INDEX_NONE || EnumIndex >= BoundEnum->NumEnums() - 1)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' is not an element of %s"), *EnumEntry, *BoundEnum->GetName()));
				return false;
			}
			const TArray<FName>* Visible = VisibleEnumEntriesOf(BlendNode);
			if (Visible && Visible->Contains(BoundEnum->GetNameByIndex(EnumIndex)))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' already has a pose pin"), *EnumEntry));
				return false;
			}
			return true;
		}
		OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("add_blend_pose supports LayeredBoneBlend and BlendListByEnum, not %s"), Node ? *Node->GetClass()->GetName() : TEXT("null")));
		return false;
	}

	bool AddBlendPose(UEdGraphNode* Node, const FString& EnumEntry, FAnimMcpError& OutError)
	{
		if (!ValidateAddBlendPose(Node, EnumEntry, OutError))
		{
			return false;
		}
		if (UAnimGraphNode_LayeredBoneBlend* Layered = Cast<UAnimGraphNode_LayeredBoneBlend>(Node))
		{
			// 자체 FScopedTransaction 을 열지만 바깥 트랜잭션에 합쳐진다. Modify + Node.AddPose + ReconstructNode
			Layered->AddPinToBlendByFilter();
			return true;
		}
		UAnimGraphNode_BlendListByEnum* BlendNode = CastChecked<UAnimGraphNode_BlendListByEnum>(Node);
		TArray<FName>* Visible = VisibleEnumEntriesOf(BlendNode);
		if (!Visible)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("VisibleEnumEntries not found by reflection"));
			return false;
		}
		// ExposeEnumElementAsPin 은 비가상·비내보내기(MinimalAPI) 라 같은 순서를 재현한다 (AnimGraphNode_BlendListByEnum.cpp:143-158)
		UEnum* BoundEnum = BlendNode->GetEnum();
		BlendNode->Modify();
		Visible->Add(BoundEnum->GetNameByIndex(BoundEnum->GetIndexByNameString(EnumEntry)));
		BlendNode->Node.AddPose();
		BlendNode->ReconstructNode();
		return true;
	}

	namespace
	{
		/**
		 * 제거되는 배열 인덱스의 핀(BlendPoses_N · BlendWeights_N · BlendPose_N · BlendTime_N)은 재구성 때 고아 핀으로 남지 않게 표시한다.
		 * 엔진의 RemovePinFromBlendList 도 같은 처리를 한다 (AnimGraphNode_BlendListByEnum.cpp:187). 기본값이 비기본(0.1 · 1.0)이라 표시 없이는 남는다
		 */
		void DiscardPinsOfArrayIndex(UEdGraphNode* Node, int32 Index)
		{
			const FString Suffix = FString::Printf(TEXT("_%d"), Index);
			for (UEdGraphPin* Pin : Node->Pins)
			{
				if (Pin && Pin->PinName.ToString().EndsWith(Suffix))
				{
					Pin->SetSavePinIfOrphaned(false);
				}
			}
		}
	}

	void RemoveLastBlendPose(UEdGraphNode* Node)
	{
		if (UAnimGraphNode_LayeredBoneBlend* Layered = Cast<UAnimGraphNode_LayeredBoneBlend>(Node))
		{
			const int32 Last = Layered->Node.BlendPoses.Num() - 1;
			if (Last >= 0)
			{
				Layered->Modify();
				DiscardPinsOfArrayIndex(Layered, Last);
				Layered->Node.RemovePose(Last);
				Layered->ReconstructNode();
			}
			return;
		}
		if (UAnimGraphNode_BlendListByEnum* BlendNode = Cast<UAnimGraphNode_BlendListByEnum>(Node))
		{
			// BlendPose 배열은 protected — 공개 GetBlendTimes() 가 같은 길이다
			const int32 Last = BlendNode->Node.GetBlendTimes().Num() - 1;
			TArray<FName>* Visible = VisibleEnumEntriesOf(BlendNode);
			if (Last >= 1 && Visible && Visible->Num() > 0) // 0 번은 Default 포즈
			{
				BlendNode->Modify();
				Visible->Pop();
				DiscardPinsOfArrayIndex(BlendNode, Last);
				BlendNode->Node.RemovePose(Last);
				BlendNode->ReconstructNode();
			}
		}
	}
}
