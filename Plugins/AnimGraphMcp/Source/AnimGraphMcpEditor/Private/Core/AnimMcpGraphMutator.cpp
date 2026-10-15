#include "AnimMcpGraphMutator.h"

#include "AnimGraphNode_AssetPlayerBase.h"
#include "AnimGraphNode_Base.h"
#include "AnimMcpGraphInspector.h"
#include "AnimMcpLog.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimationAsset.h"
#include "Animation/Skeleton.h"
#include "Bridge/AnimMcpTypes.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraph/EdGraphSchema.h"
#include "UObject/UObjectGlobals.h"

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
}
