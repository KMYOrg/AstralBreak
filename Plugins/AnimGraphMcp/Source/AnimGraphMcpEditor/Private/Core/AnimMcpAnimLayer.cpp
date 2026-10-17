#include "AnimMcpAnimLayer.h"

#include "AnimGraphNode_LinkedAnimGraphBase.h"
#include "AnimGraphNode_LinkedAnimLayer.h"
#include "AnimGraphNode_LinkedInputPose.h"
#include "AnimGraphNode_Root.h"
#include "AnimMcpAssetOps.h"
#include "AnimMcpAssetProtection.h"
#include "AnimMcpAssetResolver.h"
#include "AnimMcpLog.h"
#include "AnimationGraph.h"
#include "AnimationGraphSchema.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimLayerInterface.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Bridge/AnimMcpTypes.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphSchema_K2.h"
#include "Engine/BlueprintGeneratedClass.h"
#include "Engine/MemberReference.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/PackageName.h"
#include "UObject/Package.h"
#include "UObject/UnrealType.h"

namespace AnimMcpAnimLayer
{
	namespace
	{
		FAnimMcpError Reason(const FString& Message, const TCHAR* ReasonCode, const FString& Field = FString())
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("reason"), ReasonCode);
			if (!Field.IsEmpty()) { Details->SetStringField(TEXT("field"), Field); }
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
		}

		/** protected FunctionReference (AnimGraphNode_LinkedAnimGraphBase.h:96-98) — 리플렉션 */
		FMemberReference* FunctionReferenceOf(UAnimGraphNode_LinkedAnimLayer* Node)
		{
			static const FName PropName(TEXT("FunctionReference"));
			FStructProperty* Prop = CastField<FStructProperty>(UAnimGraphNode_LinkedAnimGraphBase::StaticClass()->FindPropertyByName(PropName));
			return Prop ? Prop->ContainerPtrToValuePtr<FMemberReference>(Node) : nullptr;
		}

		UAnimGraphNode_Root* RootOf(UEdGraph* Graph)
		{
			TArray<UAnimGraphNode_Root*> Roots;
			Graph->GetNodesOfClass<UAnimGraphNode_Root>(Roots);
			return Roots.Num() > 0 ? Roots[0] : nullptr;
		}

		TArray<FString> InputPoseNamesOf(UEdGraph* Graph)
		{
			TArray<UAnimGraphNode_LinkedInputPose*> Inputs;
			Graph->GetNodesOfClass<UAnimGraphNode_LinkedInputPose>(Inputs);
			Inputs.Sort([](const UAnimGraphNode_LinkedInputPose& A, const UAnimGraphNode_LinkedInputPose& B)
			{
				return A.InputPoseIndex != B.InputPoseIndex ? A.InputPoseIndex < B.InputPoseIndex : A.NodePosY < B.NodePosY;
			});
			TArray<FString> Names;
			for (const UAnimGraphNode_LinkedInputPose* N : Inputs) { Names.Add(N->Node.Name.ToString()); }
			return Names;
		}

		bool IsValidLayerName(const FString& Name, FAnimMcpError& OutError, const FString& Field)
		{
			FText Why;
			if (Name.IsEmpty() || !FName::IsValidXName(Name, INVALID_OBJECTNAME_CHARACTERS TEXT(" "), &Why))
			{
				OutError = Reason(FString::Printf(TEXT("Invalid layer name '%s': %s"), *Name, *Why.ToString()), TEXT("INVALID_NAME"), Field);
				return false;
			}
			if (Name == UEdGraphSchema_K2::GN_AnimGraph.ToString())
			{
				OutError = Reason(TEXT("'AnimGraph' is reserved for the root graph"), TEXT("RESERVED_NAME"), Field);
				return false;
			}
			return true;
		}

		int32 CountAnimFunctions(UClass* Class)
		{
			int32 Count = 0;
			for (TFieldIterator<UFunction> It(Class, EFieldIteratorFlags::IncludeSuper); It; ++It)
			{
				if (It->HasMetaData(FBlueprintMetadata::MD_AnimBlueprintFunction)) { ++Count; }
			}
			return Count;
		}
	}

	bool ParseCreateInterfaceParams(const TSharedRef<FJsonObject>& Params, FCreateInterfaceParams& Out, FAnimMcpError& OutError)
	{
		if (!Params->TryGetStringField(TEXT("asset_path"), Out.AssetPath) || Out.AssetPath.IsEmpty())
		{
			OutError = Reason(TEXT("Missing or empty required string parameter 'asset_path'"), TEXT("MISSING"), TEXT("asset_path"));
			return false;
		}
		Params->TryGetBoolField(TEXT("overwrite"), Out.bOverwrite);
		const TArray<TSharedPtr<FJsonValue>>* Layers = nullptr;
		if (!Params->TryGetArrayField(TEXT("layers"), Layers) || !Layers || Layers->Num() == 0)
		{
			OutError = Reason(TEXT("'layers' must be a non-empty array of {name, group?, input_poses?}"), TEXT("MISSING"), TEXT("layers"));
			return false;
		}
		TSet<FString> Seen;
		for (int32 i = 0; i < Layers->Num(); ++i)
		{
			const FString Field = FString::Printf(TEXT("layers[%d]"), i);
			const TSharedPtr<FJsonObject>* Obj = nullptr;
			if (!(*Layers)[i].IsValid() || !(*Layers)[i]->TryGetObject(Obj) || !Obj)
			{
				OutError = Reason(TEXT("Each layer must be an object {name, group?, input_poses?}"), TEXT("BAD_SHAPE"), Field);
				return false;
			}
			FLayerParams L;
			(*Obj)->TryGetStringField(TEXT("name"), L.Name);
			L.Name = L.Name.TrimStartAndEnd();
			if (!IsValidLayerName(L.Name, OutError, Field + TEXT(".name"))) { return false; }
			if (Seen.Contains(L.Name))
			{
				OutError = Reason(FString::Printf(TEXT("Duplicate layer name '%s'"), *L.Name), TEXT("DUPLICATE_NAME"), Field + TEXT(".name"));
				return false;
			}
			Seen.Add(L.Name);
			(*Obj)->TryGetStringField(TEXT("group"), L.Group);
			const TArray<TSharedPtr<FJsonValue>>* Poses = nullptr;
			if ((*Obj)->TryGetArrayField(TEXT("input_poses"), Poses) && Poses)
			{
				TSet<FString> SeenPoses;
				for (const TSharedPtr<FJsonValue>& V : *Poses)
				{
					FString Pose;
					if (!V.IsValid() || !V->TryGetString(Pose) || !IsValidLayerName(Pose.TrimStartAndEnd(), OutError, Field + TEXT(".input_poses")))
					{
						if (!OutError.IsSet()) { OutError = Reason(TEXT("'input_poses' entries must be non-empty strings"), TEXT("BAD_SHAPE"), Field + TEXT(".input_poses")); }
						return false;
					}
					Pose = Pose.TrimStartAndEnd();
					if (SeenPoses.Contains(Pose))
					{
						OutError = Reason(FString::Printf(TEXT("Duplicate input pose '%s' in layer '%s'"), *Pose, *L.Name), TEXT("DUPLICATE_NAME"), Field + TEXT(".input_poses"));
						return false;
					}
					SeenPoses.Add(Pose);
					L.InputPoses.Add(Pose);
				}
			}
			Out.Layers.Add(L);
		}
		return true;
	}

	UAnimBlueprint* CreateLayerInterface(const FCreateInterfaceParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		check(IsInGameThread());
		const FString PackagePath = AnimMcpAssetResolver::ToPackagePath(Params.AssetPath);
		FText PathReason;
		if (!FPackageName::IsValidLongPackageName(PackagePath, false, &PathReason))
		{
			OutError = Reason(FString::Printf(TEXT("Invalid package path '%s': %s"), *PackagePath, *PathReason.ToString()), TEXT("INVALID_PATH"), TEXT("asset_path"));
			return nullptr;
		}
		const FString AssetName = FPackageName::GetLongPackageAssetName(PackagePath);
		const FString ObjectPath = PackagePath + TEXT(".") + AssetName;

		if (AnimMcpAssetResolver::AssetExists(ObjectPath))
		{
			if (!Params.bOverwrite)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetExists, FString::Printf(TEXT("'%s' already exists (pass overwrite=true to replace)"), *ObjectPath));
				return nullptr;
			}
			if (!AnimMcpAssetProtection::EnsureNotProtected(ObjectPath, TEXT("overwrite"), OutError)) { return nullptr; }
			if (!AnimMcpAssetOps::DeleteAssetAtPath(ObjectPath, Context, OutError)) { return nullptr; }
			Context.AddDiagnostic(TEXT("info"), TEXT("ASSET_REPLACED"), FString::Printf(TEXT("Deleted existing '%s' before creating"), *ObjectPath));
		}

		UPackage* Package = CreatePackage(*PackagePath);
		if (!Package)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("CreatePackage failed for '%s'"), *PackagePath));
			return nullptr;
		}
		Package->FullyLoad();
		if (UObject* Stale = FindObject<UObject>(Package, *AssetName))
		{
			const FName StaleName = MakeUniqueObjectName(GetTransientPackage(), Stale->GetClass(), FName(*(AssetName + TEXT("_MCP_STALE"))));
			Stale->ClearFlags(RF_Public | RF_Standalone);
			if (!Stale->Rename(*StaleName.ToString(), GetTransientPackage(), REN_DontCreateRedirectors | REN_NonTransactional | REN_DoNotDirty))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetExists, FString::Printf(TEXT("An object named '%s' still exists in package '%s' and could not be moved aside"), *AssetName, *PackagePath));
				return nullptr;
			}
			Stale->MarkAsGarbage();
			Context.AddDiagnostic(TEXT("info"), TEXT("STALE_OBJECT_MOVED"), FString::Printf(TEXT("In-memory object '%s' survived deletion; moved to transient package before creating"), *AssetName));
		}

		// 팩토리 재현 (AnimBlueprintFactory.cpp:465-466, BPTYPE_Interface → 부모 UAnimLayerInterface)
		UAnimBlueprint* NewBP = Cast<UAnimBlueprint>(FKismetEditorUtilities::CreateBlueprint(
			UAnimLayerInterface::StaticClass(), Package, FName(*AssetName), BPTYPE_Interface,
			UAnimBlueprint::StaticClass(), UBlueprintGeneratedClass::StaticClass(), FName(TEXT("AnimGraphMcp"))));
		if (!NewBP)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("FKismetEditorUtilities::CreateBlueprint returned null for the layer interface"));
			return nullptr;
		}
		NewBP->bIsTemplate = false;
		NewBP->TargetSkeleton = nullptr;

		// 레이어 그래프 (BlueprintEditor.cpp:9717-9718 과 동일) + 그룹 + 입력 포즈 (AnimGraphDetails.cpp:295 SpawnNode<UAnimGraphNode_LinkedInputPose>)
		for (const FLayerParams& L : Params.Layers)
		{
			UEdGraph* Graph = FBlueprintEditorUtils::CreateNewGraph(NewBP, FName(*L.Name), UAnimationGraph::StaticClass(), UAnimationGraphSchema::StaticClass());
			FBlueprintEditorUtils::AddDomainSpecificGraph(NewBP, Graph);
			UAnimGraphNode_Root* Root = RootOf(Graph);
			if (!Root)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("Layer graph '%s' has no root node after creation"), *L.Name));
				return nullptr;
			}
			if (!L.Group.IsEmpty())
			{
				Root->Modify();
				Root->Node.SetGroup(FName(*L.Group));
			}
			int32 PoseIndex = 0;
			for (const FString& Pose : L.InputPoses)
			{
				FGraphNodeCreator<UAnimGraphNode_LinkedInputPose> Creator(*Graph);
				UAnimGraphNode_LinkedInputPose* Input = Creator.CreateNode(/*bSelectNewNode*/ false);
				Input->NodePosX = Root->NodePosX - 500;
				Input->NodePosY = Root->NodePosY + PoseIndex * 150;
				Creator.Finalize();   // PostPlacedNewNode 가 기본 이름(InPose…)을 준다 — 아래서 덮어쓴다
				Input->Node.Name = FName(*Pose);
				Input->ReconstructNode();
				++PoseIndex;
			}
		}

		FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(NewBP);
		FAssetRegistryModule::AssetCreated(NewBP);
		NewBP->MarkPackageDirty();
		UE_LOG(LogAnimGraphMcp, Log, TEXT("Created Anim Layer Interface %s (%d layers)"), *ObjectPath, Params.Layers.Num());
		return NewBP;
	}

	bool ValidateLayerInterface(UAnimBlueprint* InterfaceBP, FAnimMcpError& OutError)
	{
		if (InterfaceBP->BlueprintType != BPTYPE_Interface || !InterfaceBP->ParentClass || !InterfaceBP->ParentClass->IsChildOf(UAnimLayerInterface::StaticClass()))
		{
			OutError = Reason(FString::Printf(TEXT("'%s' is not an Animation Layer Interface (BPTYPE_Interface with parent UAnimLayerInterface)"), *InterfaceBP->GetPathName()), TEXT("NOT_LAYER_INTERFACE"), TEXT("interface"));
			return false;
		}
		if (!InterfaceBP->GeneratedClass)
		{
			OutError = Reason(FString::Printf(TEXT("'%s' has no generated class — compile it first"), *InterfaceBP->GetPathName()), TEXT("NOT_COMPILED"), TEXT("interface"));
			return false;
		}
		if (CountAnimFunctions(InterfaceBP->GeneratedClass) == 0)
		{
			OutError = Reason(FString::Printf(TEXT("'%s' exposes no animation layers (no function with AnimBlueprintFunction metadata) — add layers and compile"), *InterfaceBP->GetPathName()), TEXT("NO_LAYERS"), TEXT("interface"));
			return false;
		}
		return true;
	}

	bool ImplementInterface(UAnimBlueprint* Target, UAnimBlueprint* InterfaceBP, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		check(IsInGameThread());
		if (!ValidateLayerInterface(InterfaceBP, OutError)) { return false; }
		if (Target->BlueprintType == BPTYPE_Interface)
		{
			OutError = Reason(TEXT("Target must be a normal Animation Blueprint, not an interface"), TEXT("TARGET_IS_INTERFACE"), TEXT("asset_path"));
			return false;
		}
		UClass* InterfaceClass = InterfaceBP->GeneratedClass;
		for (const FBPInterfaceDescription& Desc : Target->ImplementedInterfaces)
		{
			if (Desc.Interface == InterfaceClass)
			{
				OutError = Reason(FString::Printf(TEXT("'%s' already implements '%s'"), *Target->GetPathName(), *InterfaceBP->GetPathName()), TEXT("ALREADY_IMPLEMENTED"), TEXT("interface"));
				return false;
			}
		}
		for (TFieldIterator<UFunction> It(InterfaceClass, EFieldIteratorFlags::IncludeSuper); It; ++It)
		{
			if (It->HasMetaData(FBlueprintMetadata::MD_AnimBlueprintFunction) && FindObject<UEdGraph>(Target, *It->GetName()))
			{
				OutError = Reason(FString::Printf(TEXT("'%s' already has a graph named '%s' which conflicts with the interface layer"), *Target->GetPathName(), *It->GetName()), TEXT("GRAPH_NAME_CONFLICT"), TEXT("interface"));
				return false;
			}
		}

		Target->Modify();
		if (!FBlueprintEditorUtils::ImplementNewInterface(Target, InterfaceClass->GetClassPathName()))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("ImplementNewInterface('%s') returned false (see editor notifications/log)"), *InterfaceClass->GetPathName()));
			return false;
		}
		UE_LOG(LogAnimGraphMcp, Log, TEXT("%s now implements %s"), *Target->GetPathName(), *InterfaceClass->GetPathName());
		return true;
	}

	UEdGraph* FindLayerGraph(UAnimBlueprint* Blueprint, FName Layer, UClass*& OutInterface)
	{
		OutInterface = nullptr;
		for (const FBPInterfaceDescription& Desc : Blueprint->ImplementedInterfaces)
		{
			for (UEdGraph* G : Desc.Graphs)
			{
				if (G && G->GetFName() == Layer)
				{
					OutInterface = Desc.Interface;
					return G;
				}
			}
		}
		for (UEdGraph* G : Blueprint->FunctionGraphs)
		{
			if (G && G->IsA<UAnimationGraph>() && G->GetFName() == Layer && Layer != UEdGraphSchema_K2::GN_AnimGraph)
			{
				return G;
			}
		}
		return nullptr;
	}

	bool ValidateLayerName(UAnimBlueprint* Blueprint, const FString& Layer, FAnimMcpError& OutError)
	{
		if (Layer.IsEmpty())
		{
			OutError = Reason(TEXT("'layer' must be a non-empty layer name"), TEXT("MISSING"), TEXT("layer"));
			return false;
		}
		UClass* Interface = nullptr;
		if (!FindLayerGraph(Blueprint, FName(*Layer), Interface))
		{
			TArray<FString> Known;
			for (const TSharedPtr<FJsonValue>& V : DescribeLayers(Blueprint)) { Known.Add(V->AsObject()->GetStringField(TEXT("name"))); }
			OutError = Reason(FString::Printf(TEXT("Layer '%s' is not an implemented interface layer or own layer graph of %s (known: %s)"), *Layer, *Blueprint->GetName(), *FString::Join(Known, TEXT(", "))), TEXT("UNKNOWN_LAYER"), TEXT("layer"));
			return false;
		}
		return true;
	}

	bool ValidateLayerAssignable(UAnimBlueprint* Blueprint, const FString& Layer, const UAnimGraphNode_LinkedAnimLayer* ExcludeNode, FAnimMcpError& OutError)
	{
		if (!ValidateLayerName(Blueprint, Layer, OutError)) { return false; }
		TArray<UAnimGraphNode_LinkedAnimLayer*> LayerNodes;
		FBlueprintEditorUtils::GetAllNodesOfClass<UAnimGraphNode_LinkedAnimLayer>(Blueprint, LayerNodes);
		for (const UAnimGraphNode_LinkedAnimLayer* Other : LayerNodes)
		{
			if (Other && Other != ExcludeNode && Other->Node.Layer == FName(*Layer))
			{
				OutError = Reason(FString::Printf(TEXT("Layer '%s' is already used by node %s in graph '%s' — a layer can be used only once per Animation Blueprint"), *Layer, *Other->NodeGuid.ToString(), *GetNameSafe(Other->GetGraph())), TEXT("LAYER_IN_USE"), TEXT("layer"));
				return false;
			}
		}
		return true;
	}

	bool SetLinkedLayer(UAnimGraphNode_LinkedAnimLayer* Node, FName Layer, FLayerRef& OutOld, FAnimMcpError& OutError)
	{
		UAnimBlueprint* Blueprint = Cast<UAnimBlueprint>(FBlueprintEditorUtils::FindBlueprintForNode(Node));
		if (!Blueprint)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("Linked layer node has no Animation Blueprint"));
			return false;
		}
		if (!ValidateLayerAssignable(Blueprint, Layer.ToString(), Node, OutError)) { return false; }
		TArray<FString> LinkedInputs;
		for (const UEdGraphPin* Pin : Node->Pins)
		{
			if (Pin && Pin->Direction == EGPD_Input && UAnimationGraphSchema::IsPosePin(Pin->PinType) && Pin->LinkedTo.Num() > 0)
			{
				LinkedInputs.Add(Pin->PinName.ToString());
			}
		}
		if (LinkedInputs.Num() > 0)
		{
			OutError = Reason(FString::Printf(TEXT("Input pose pin(s) %s are linked; disconnect them before changing the layer (pins that vanish would stay as orphans and fail compilation)"), *FString::Join(LinkedInputs, TEXT(", "))), TEXT("PINS_LINKED"), TEXT("layer"));
			return false;
		}
		FMemberReference* FunctionReference = FunctionReferenceOf(Node);
		if (!FunctionReference)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("FunctionReference not found on UAnimGraphNode_LinkedAnimGraphBase by reflection"));
			return false;
		}
		OutOld.Layer = Node->Node.Layer;
		OutOld.Interface = Node->Node.Interface;
		OutOld.Guid = Node->InterfaceGuid;

		UClass* Interface = nullptr;
		UEdGraph* Graph = FindLayerGraph(Blueprint, Layer, Interface);

		// SetupFromLayerId 재현 (self 인스턴스: InstanceClass=null → FunctionReference 는 self member)
		Node->Modify();
		Node->Node.Layer = Layer;
		FunctionReference->SetSelfMember(Layer);
		Node->Node.Interface = Interface ? TSubclassOf<UAnimLayerInterface>(Interface) : nullptr;
		Node->InterfaceGuid = Graph ? Graph->InterfaceGuid : FGuid();
		Node->Node.InstanceClass = nullptr;
		Node->ReconstructNode();
		return true;
	}

	void RestoreLinkedLayer(UAnimGraphNode_LinkedAnimLayer* Node, const FLayerRef& Old)
	{
		FMemberReference* FunctionReference = FunctionReferenceOf(Node);
		Node->Modify();
		Node->Node.Layer = Old.Layer;
		if (FunctionReference) { FunctionReference->SetSelfMember(Old.Layer); }
		Node->Node.Interface = Old.Interface;
		Node->InterfaceGuid = Old.Guid;
		Node->ReconstructNode();
	}

	TArray<TSharedPtr<FJsonValue>> DescribeImplementedInterfaces(UAnimBlueprint* Blueprint)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		for (const FBPInterfaceDescription& Desc : Blueprint->ImplementedInterfaces)
		{
			TSharedRef<FJsonObject> O = AnimMcpJson::MakeObject();
			O->SetField(TEXT("interface"), Desc.Interface ? AnimMcpJson::StringOrNull(Desc.Interface->GetPathName()) : MakeShared<FJsonValueNull>());
			O->SetField(TEXT("blueprint"), Desc.Interface && Desc.Interface->ClassGeneratedBy ? AnimMcpJson::StringOrNull(Desc.Interface->ClassGeneratedBy->GetPathName()) : MakeShared<FJsonValueNull>());
			TArray<TSharedPtr<FJsonValue>> Graphs;
			for (UEdGraph* G : Desc.Graphs)
			{
				if (!G) { continue; }
				TSharedRef<FJsonObject> GO = AnimMcpJson::MakeObject();
				GO->SetStringField(TEXT("name"), G->GetName());
				GO->SetStringField(TEXT("graph_guid"), G->GraphGuid.ToString());
				GO->SetField(TEXT("interface_guid"), G->InterfaceGuid.IsValid() ? AnimMcpJson::StringOrNull(G->InterfaceGuid.ToString()) : MakeShared<FJsonValueNull>());
				Graphs.Add(MakeShared<FJsonValueObject>(GO));
			}
			O->SetArrayField(TEXT("graphs"), Graphs);
			Out.Add(MakeShared<FJsonValueObject>(O));
		}
		return Out;
	}

	TArray<TSharedPtr<FJsonValue>> DescribeLayers(UAnimBlueprint* Blueprint)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		auto Describe = [&Out](UEdGraph* G, UClass* Interface)
		{
			TSharedRef<FJsonObject> O = AnimMcpJson::MakeObject();
			O->SetStringField(TEXT("name"), G->GetName());
			O->SetStringField(TEXT("graph_guid"), G->GraphGuid.ToString());
			O->SetField(TEXT("interface"), Interface ? AnimMcpJson::StringOrNull(Interface->GetPathName()) : MakeShared<FJsonValueNull>());
			O->SetField(TEXT("interface_guid"), G->InterfaceGuid.IsValid() ? AnimMcpJson::StringOrNull(G->InterfaceGuid.ToString()) : MakeShared<FJsonValueNull>());
			const UAnimGraphNode_Root* Root = RootOf(G);
			const FName Group = Root ? Root->Node.GetGroup() : NAME_None;
			O->SetField(TEXT("group"), Group.IsNone() ? MakeShared<FJsonValueNull>() : AnimMcpJson::StringOrNull(Group.ToString()));
			TArray<TSharedPtr<FJsonValue>> Poses;
			for (const FString& P : InputPoseNamesOf(G)) { Poses.Add(MakeShared<FJsonValueString>(P)); }
			O->SetArrayField(TEXT("input_poses"), Poses);
			Out.Add(MakeShared<FJsonValueObject>(O));
		};
		for (const FBPInterfaceDescription& Desc : Blueprint->ImplementedInterfaces)
		{
			for (UEdGraph* G : Desc.Graphs) { if (G) { Describe(G, Desc.Interface); } }
		}
		for (UEdGraph* G : Blueprint->FunctionGraphs)
		{
			if (G && G->IsA<UAnimationGraph>() && G->GetFName() != UEdGraphSchema_K2::GN_AnimGraph) { Describe(G, nullptr); }
		}
		return Out;
	}

	TSharedRef<FJsonObject> DescribeLinkedLayerNode(const UAnimGraphNode_LinkedAnimLayer* Node)
	{
		TSharedRef<FJsonObject> O = AnimMcpJson::MakeObject();
		O->SetField(TEXT("layer"), Node->Node.Layer.IsNone() ? MakeShared<FJsonValueNull>() : AnimMcpJson::StringOrNull(Node->Node.Layer.ToString()));
		O->SetField(TEXT("interface"), Node->Node.Interface.Get() ? AnimMcpJson::StringOrNull(Node->Node.Interface->GetPathName()) : MakeShared<FJsonValueNull>());
		O->SetField(TEXT("instance_class"), Node->Node.InstanceClass.Get() ? AnimMcpJson::StringOrNull(Node->Node.InstanceClass->GetPathName()) : MakeShared<FJsonValueNull>());
		O->SetField(TEXT("interface_guid"), Node->InterfaceGuid.IsValid() ? AnimMcpJson::StringOrNull(Node->InterfaceGuid.ToString()) : MakeShared<FJsonValueNull>());
		return O;
	}
}
