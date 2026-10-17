#include "AnimMcpPropertyAccessNode.h"

#include "AnimMcpGraphMutator.h"
#include "AnimMcpLog.h"
#include "Animation/AnimBlueprint.h"
#include "Bridge/AnimMcpTypes.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphSchema_K2.h"
#include "Features/IModularFeatures.h"
#include "IPropertyAccessEditor.h"
#include "K2Node.h"
#include "UObject/UnrealType.h"

namespace AnimMcpPropertyAccessNode
{
	namespace
	{
		const TCHAR* const ClassPath = TEXT("/Script/PropertyAccessNode.K2Node_PropertyAccess");
		const FName PathPropertyName(TEXT("Path"));
		const FName PropertyAccessEditorFeature(TEXT("PropertyAccessEditor"));

		FAnimMcpError Reason(const FString& Message, const TCHAR* ReasonCode)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("reason"), ReasonCode);
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
		}

		FArrayProperty* PathProperty(const UClass* Class)
		{
			FArrayProperty* Prop = Class ? CastField<FArrayProperty>(Class->FindPropertyByName(PathPropertyName)) : nullptr;
			return (Prop && CastField<FStrProperty>(Prop->Inner)) ? Prop : nullptr;
		}

		UClass* ResolveClassOf(UAnimBlueprint* Blueprint)
		{
			if (!Blueprint) { return nullptr; }
			if (Blueprint->SkeletonGeneratedClass) { return Blueprint->SkeletonGeneratedClass; }
			if (Blueprint->GeneratedClass) { return Blueprint->GeneratedClass; }
			return Blueprint->ParentClass;
		}
	}

	UClass* NodeClass()
	{
		return FindObject<UClass>(nullptr, ClassPath);
	}

	bool IsPropertyAccessNode(const UEdGraphNode* Node)
	{
		UClass* Class = NodeClass();
		return Node && Class && Node->IsA(Class);
	}

	bool ParsePath(const TSharedPtr<FJsonValue>& Value, TArray<FString>& OutPath, FAnimMcpError& OutError)
	{
		OutPath.Reset();
		if (Value.IsValid() && Value->Type == EJson::String)
		{
			Value->AsString().ParseIntoArray(OutPath, TEXT("."), /*bCullEmpty*/ true);
		}
		else if (Value.IsValid() && Value->Type == EJson::Array)
		{
			for (const TSharedPtr<FJsonValue>& Element : Value->AsArray())
			{
				if (!Element.IsValid() || Element->Type != EJson::String)
				{
					OutError = Reason(TEXT("access path array must contain strings"), TEXT("BAD_PATH"));
					return false;
				}
				const FString Segment = Element->AsString().TrimStartAndEnd();
				if (!Segment.IsEmpty())
				{
					OutPath.Add(Segment);
				}
			}
		}
		for (FString& Segment : OutPath)
		{
			Segment.TrimStartAndEndInline();
		}
		if (OutPath.Num() == 0)
		{
			OutError = Reason(TEXT("access expects a non-empty property path (\"Pawn.Velocity\" or [\"Pawn\",\"Velocity\"])"), TEXT("EMPTY_PATH"));
			return false;
		}
		return true;
	}

	FString JoinPath(const TArray<FString>& Path)
	{
		return FString::Join(Path, TEXT("."));
	}

	bool ResolvePath(UAnimBlueprint* Blueprint, const TArray<FString>& Path, FProperty*& OutLeaf, bool& bOutThreadSafe, bool& bOutLeafIsFunction, FAnimMcpError& OutError)
	{
		OutLeaf = nullptr;
		bOutThreadSafe = false;
		bOutLeafIsFunction = false;
		if (!IModularFeatures::Get().IsModularFeatureAvailable(PropertyAccessEditorFeature))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("PropertyAccessEditor modular feature is not available"));
			return false;
		}
		UClass* Class = ResolveClassOf(Blueprint);
		if (!Class)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("Animation Blueprint has no class to resolve the access path against"));
			return false;
		}
		IPropertyAccessEditor& PAE = IModularFeatures::Get().GetModularFeature<IPropertyAccessEditor>(PropertyAccessEditorFeature);
		int32 ArrayIndex = INDEX_NONE;
		const FPropertyAccessResolveResult Resolved = PAE.ResolvePropertyAccess(Class, Path, OutLeaf, ArrayIndex);
		if (Resolved.Result != EPropertyAccessResolveResult::Succeeded || !OutLeaf)
		{
			OutLeaf = nullptr;
			OutError = Reason(FString::Printf(TEXT("access path '%s' does not resolve on %s (BlueprintVisible property or BlueprintPure function chain starting at the AnimInstance, e.g. \"Pawn.Velocity\")"), *JoinPath(Path), *Class->GetName()), TEXT("PATH_UNRESOLVED"));
			return false;
		}
		bOutThreadSafe = Resolved.bIsThreadSafe;
		{
			IPropertyAccessEditor::FResolvePropertyAccessArgs Args;
			bool bLeafIsFunction = false;
			Args.PropertyFunction = [&bLeafIsFunction](int32, FProperty*, int32) { bLeafIsFunction = false; };
			Args.ArrayFunction = [&bLeafIsFunction](int32, FArrayProperty*, int32) { bLeafIsFunction = false; };
			Args.FunctionFunction = [&bLeafIsFunction](int32, UFunction*, FProperty*) { bLeafIsFunction = true; };
			PAE.ResolvePropertyAccess(Class, Path, Args);
			bOutLeafIsFunction = bLeafIsFunction;
		}
		return true;
	}

	bool GetPath(const UEdGraphNode* Node, TArray<FString>& OutPath)
	{
		OutPath.Reset();
		if (!IsPropertyAccessNode(Node))
		{
			return false;
		}
		FArrayProperty* Prop = PathProperty(Node->GetClass());
		if (!Prop)
		{
			return false;
		}
		FScriptArrayHelper Helper(Prop, Prop->ContainerPtrToValuePtr<void>(Node));
		const FStrProperty* Inner = CastField<FStrProperty>(Prop->Inner);
		for (int32 i = 0; i < Helper.Num(); ++i)
		{
			OutPath.Add(Inner->GetPropertyValue(Helper.GetRawPtr(i)));
		}
		return true;
	}

	bool SetPath(UEdGraphNode* Node, const TArray<FString>& Path, FAnimMcpError& OutError)
	{
		if (!IsPropertyAccessNode(Node))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("SetPath called on a node that is not a Property Access node"));
			return false;
		}
		FArrayProperty* Prop = PathProperty(Node->GetClass());
		if (!Prop)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("K2Node_PropertyAccess has no TArray<FString> Path property (engine layout changed?)"));
			return false;
		}
		Node->Modify();
		FScriptArrayHelper Helper(Prop, Prop->ContainerPtrToValuePtr<void>(Node));
		const FStrProperty* Inner = CastField<FStrProperty>(Prop->Inner);
		Helper.EmptyValues();
		for (const FString& Segment : Path)
		{
			const int32 Index = Helper.AddValue();
			Inner->SetPropertyValue(Helper.GetRawPtr(Index), Segment);
		}
		return true;
	}

	UK2Node* Spawn(UEdGraph* Graph, const TArray<FString>& Path, int32 PosX, int32 PosY, FAnimMcpError& OutError)
	{
		UClass* Class = NodeClass();
		if (!Class)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("Property Access node class is not loaded — enable the engine plugin 'PropertyAccessNode' (enabled by default)"));
			return nullptr;
		}
		if (!Graph)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("Spawn Property Access: no graph"));
			return nullptr;
		}
		Graph->Modify();
		// CreateNode 가 노드를 그래프에 넣어 두므로 Finalize 의 AllocateDefaultPins 가 GetBlueprint() 로 경로를 해석할 수 있다
		FGraphNodeCreator<UK2Node> Creator(*Graph);
		UK2Node* Node = Creator.CreateNode(/*bSelectNewNode*/ false, TSubclassOf<UK2Node>(Class));
		if (!Node || !SetPath(Node, Path, OutError))
		{
			if (Node)
			{
				Creator.Finalize();
				AnimMcpGraphMutator::DestroyNodeQuietly(Node);
			}
			return nullptr;
		}
		Node->NodePosX = PosX;
		Node->NodePosY = PosY;
		Creator.Finalize();

		const UEdGraphPin* Value = Node->FindPin(TEXT("Value"), EGPD_Output);
		if (!Value || Value->PinType.PinCategory == UEdGraphSchema_K2::PC_Wildcard)
		{
			AnimMcpGraphMutator::DestroyNodeQuietly(Node);
			OutError = Reason(FString::Printf(TEXT("access path '%s' could not be resolved to a typed pin"), *JoinPath(Path)), TEXT("PATH_UNRESOLVED"));
			return nullptr;
		}
		UE_LOG(LogAnimGraphMcp, Verbose, TEXT("Spawned Property Access '%s' %s in %s"), *JoinPath(Path), *Node->NodeGuid.ToString(), *Graph->GetName());
		return Node;
	}
}
