#include "AnimMcpAnimLayer.h"

#include "AnimGraphNode_LinkedAnimGraphBase.h"
#include "AnimGraphNode_LinkedAnimLayer.h"
#include "AnimGraphNode_LinkedInputPose.h"
#include "AnimGraphNode_Root.h"
#include "AnimMcpAssetOps.h"
#include "AnimMcpAssetProtection.h"
#include "AnimMcpAssetResolver.h"
#include "AnimMcpCompiler.h"
#include "AnimMcpLog.h"
#include "AnimMcpVariables.h"
#include "AnimationGraph.h"
#include "AnimationGraphSchema.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimInstance.h"
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

		TArray<UAnimGraphNode_LinkedInputPose*> InputPoseNodesOf(UEdGraph* Graph)
		{
			TArray<UAnimGraphNode_LinkedInputPose*> Inputs;
			Graph->GetNodesOfClass<UAnimGraphNode_LinkedInputPose>(Inputs);
			Inputs.Sort([](const UAnimGraphNode_LinkedInputPose& A, const UAnimGraphNode_LinkedInputPose& B)
			{
				return A.InputPoseIndex != B.InputPoseIndex ? A.InputPoseIndex < B.InputPoseIndex : A.NodePosY < B.NodePosY;
			});
			return Inputs;
		}

		TArray<FString> InputPoseNamesOf(UEdGraph* Graph)
		{
			TArray<FString> Names;
			for (const UAnimGraphNode_LinkedInputPose* N : InputPoseNodesOf(Graph)) { Names.Add(N->Node.Name.ToString()); }
			return Names;
		}

		/** 편집 가능한 레이어 그래프인가 — 인터페이스 BP 의 레이어와 ABP 의 자체 레이어(FunctionGraphs). 구현 그래프(ImplementedInterfaces[].Graphs)는 아님 */
		bool IsOwnLayerGraph(UAnimBlueprint* Blueprint, UEdGraph* Graph)
		{
			return Graph && Blueprint->FunctionGraphs.Contains(Graph) && Graph->GetFName() != UEdGraphSchema_K2::GN_AnimGraph;
		}

		/** Input Pose 노드의 값 입력 핀(비-포즈 출력) — 구현 그래프는 스텁 함수에서, 자체 그래프는 Inputs 에서 만들어진다 */
		TArray<TPair<FName, FEdGraphPinType>> ValueInputsOf(const UAnimGraphNode_LinkedInputPose* Node)
		{
			TArray<TPair<FName, FEdGraphPinType>> Out;
			for (const UEdGraphPin* Pin : Node->Pins)
			{
				if (Pin && !Pin->bOrphanedPin && Pin->Direction == EGPD_Output && !UAnimationGraphSchema::IsPosePin(Pin->PinType))
				{
					Out.Emplace(Pin->PinName, Pin->PinType);
				}
			}
			return Out;
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

	bool ParseInputParams(const TArray<TSharedPtr<FJsonValue>>& Inputs, TArray<FInputParam>& Out, FAnimMcpError& OutError, const FString& Field)
	{
		TSet<FString> Seen;
		for (int32 i = 0; i < Inputs.Num(); ++i)
		{
			const FString F = FString::Printf(TEXT("%s[%d]"), *Field, i);
			const TSharedPtr<FJsonObject>* Obj = nullptr;
			if (!Inputs[i].IsValid() || !Inputs[i]->TryGetObject(Obj) || !Obj)
			{
				OutError = Reason(TEXT("Each input must be an object {name, type}"), TEXT("BAD_SHAPE"), F);
				return false;
			}
			FInputParam P;
			(*Obj)->TryGetStringField(TEXT("name"), P.Name);
			(*Obj)->TryGetStringField(TEXT("type"), P.Type);
			P.Name = P.Name.TrimStartAndEnd();
			if (!IsValidLayerName(P.Name, OutError, F + TEXT(".name"))) { return false; }
			if (Seen.Contains(P.Name))
			{
				OutError = Reason(FString::Printf(TEXT("Duplicate input name '%s'"), *P.Name), TEXT("DUPLICATE_NAME"), F + TEXT(".name"));
				return false;
			}
			Seen.Add(P.Name);
			FEdGraphPinType PinType;
			if (P.Type.IsEmpty() || !AnimMcpVariables::ParsePinType(P.Type, PinType, OutError))
			{
				if (!OutError.IsSet()) { OutError = Reason(TEXT("Input 'type' is required (bool, float, int, name, vector, object:<class> …)"), TEXT("BAD_TYPE"), F + TEXT(".type")); }
				else if (OutError.Details.IsValid()) { OutError.Details->SetStringField(TEXT("field"), F + TEXT(".type")); }
				return false;
			}
			if (UAnimationGraphSchema::IsPosePin(PinType))
			{
				OutError = Reason(TEXT("Pose types are not value inputs — add an input pose instead"), TEXT("BAD_TYPE"), F + TEXT(".type"));
				return false;
			}
			Out.Add(P);
		}
		return true;
	}

	bool ParseLayerList(const TArray<TSharedPtr<FJsonValue>>& Layers, TArray<FLayerParams>& Out, FAnimMcpError& OutError, const FString& Field)
	{
		if (Layers.Num() == 0)
		{
			OutError = Reason(FString::Printf(TEXT("'%s' must be a non-empty array of {name, group?, input_poses?}"), *Field), TEXT("MISSING"), Field);
			return false;
		}
		TSet<FString> Seen;
		for (int32 i = 0; i < Layers.Num(); ++i)
		{
			const FString F = FString::Printf(TEXT("%s[%d]"), *Field, i);
			const TSharedPtr<FJsonObject>* Obj = nullptr;
			if (!Layers[i].IsValid() || !Layers[i]->TryGetObject(Obj) || !Obj)
			{
				OutError = Reason(TEXT("Each layer must be an object {name, group?, input_poses?}"), TEXT("BAD_SHAPE"), F);
				return false;
			}
			FLayerParams L;
			(*Obj)->TryGetStringField(TEXT("name"), L.Name);
			L.Name = L.Name.TrimStartAndEnd();
			if (!IsValidLayerName(L.Name, OutError, F + TEXT(".name"))) { return false; }
			if (Seen.Contains(L.Name))
			{
				OutError = Reason(FString::Printf(TEXT("Duplicate layer name '%s'"), *L.Name), TEXT("DUPLICATE_NAME"), F + TEXT(".name"));
				return false;
			}
			Seen.Add(L.Name);
			(*Obj)->TryGetStringField(TEXT("group"), L.Group);
			const TArray<TSharedPtr<FJsonValue>>* Poses = nullptr;
			if ((*Obj)->TryGetArrayField(TEXT("input_poses"), Poses) && Poses)
			{
				TSet<FString> SeenPoses;
				for (int32 p = 0; p < Poses->Num(); ++p)
				{
					const TSharedPtr<FJsonValue>& V = (*Poses)[p];
					const FString PF = FString::Printf(TEXT("%s.input_poses[%d]"), *F, p);
					FInputPoseParams Pose;
					const TSharedPtr<FJsonObject>* PoseObj = nullptr;
					if (V.IsValid() && V->Type == EJson::String)
					{
						Pose.Name = V->AsString();
					}
					else if (V.IsValid() && V->TryGetObject(PoseObj) && PoseObj)
					{
						(*PoseObj)->TryGetStringField(TEXT("name"), Pose.Name);
						const TArray<TSharedPtr<FJsonValue>>* Inputs = nullptr;
						if ((*PoseObj)->TryGetArrayField(TEXT("inputs"), Inputs) && Inputs && !ParseInputParams(*Inputs, Pose.Inputs, OutError, PF + TEXT(".inputs")))
						{
							return false;
						}
					}
					else
					{
						OutError = Reason(TEXT("'input_poses' entries must be a name string or {name, inputs?[{name, type}]}"), TEXT("BAD_SHAPE"), PF);
						return false;
					}
					Pose.Name = Pose.Name.TrimStartAndEnd();
					if (!IsValidLayerName(Pose.Name, OutError, PF)) { return false; }
					if (SeenPoses.Contains(Pose.Name))
					{
						OutError = Reason(FString::Printf(TEXT("Duplicate input pose '%s' in layer '%s'"), *Pose.Name, *L.Name), TEXT("DUPLICATE_NAME"), PF);
						return false;
					}
					SeenPoses.Add(Pose.Name);
					L.InputPoses.Add(Pose);
				}
			}
			Out.Add(L);
		}
		return true;
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
		if (!Params->TryGetArrayField(TEXT("layers"), Layers) || !Layers)
		{
			OutError = Reason(TEXT("'layers' must be a non-empty array of {name, group?, input_poses?}"), TEXT("MISSING"), TEXT("layers"));
			return false;
		}
		return ParseLayerList(*Layers, Out.Layers, OutError);
	}

	bool AddLayerGraphs(UAnimBlueprint* Blueprint, const TArray<FLayerParams>& Layers, FAnimMcpError& OutError)
	{
		check(Blueprint);
		// 사전 검증 — 기존 그래프 이름과 충돌하면 전부 거부(하나도 만들지 않는다)
		for (const FLayerParams& L : Layers)
		{
			if (FindObject<UEdGraph>(Blueprint, *L.Name))
			{
				OutError = Reason(FString::Printf(TEXT("'%s' already has a graph named '%s'"), *Blueprint->GetName(), *L.Name), TEXT("DUPLICATE_NAME"), TEXT("layers"));
				return false;
			}
			if (Blueprint->BlueprintType != BPTYPE_Interface)
			{
				// 자체 레이어 — 구현한 인터페이스의 함수 이름과도 충돌하면 안 된다
				for (const FBPInterfaceDescription& Desc : Blueprint->ImplementedInterfaces)
				{
					if (Desc.Interface && FindUField<UFunction>(Desc.Interface, *L.Name))
					{
						OutError = Reason(FString::Printf(TEXT("'%s' is a layer of implemented interface '%s'"), *L.Name, *Desc.Interface->GetName()), TEXT("DUPLICATE_NAME"), TEXT("layers"));
						return false;
					}
				}
			}
		}

		// 레이어 그래프 (BlueprintEditor.cpp:9717-9718 과 동일) + 그룹 + 입력 포즈 (AnimGraphDetails.cpp:295 SpawnNode<UAnimGraphNode_LinkedInputPose>) + 값 입력(Inputs)
		for (const FLayerParams& L : Layers)
		{
			UEdGraph* Graph = FBlueprintEditorUtils::CreateNewGraph(Blueprint, FName(*L.Name), UAnimationGraph::StaticClass(), UAnimationGraphSchema::StaticClass());
			FBlueprintEditorUtils::AddDomainSpecificGraph(Blueprint, Graph);
			UAnimGraphNode_Root* Root = RootOf(Graph);
			if (!Root)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("Layer graph '%s' has no root node after creation"), *L.Name));
				return false;
			}
			if (!L.Group.IsEmpty())
			{
				Root->Modify();
				Root->Node.SetGroup(FName(*L.Group));
			}
			int32 PoseIndex = 0;
			for (const FInputPoseParams& Pose : L.InputPoses)
			{
				FGraphNodeCreator<UAnimGraphNode_LinkedInputPose> Creator(*Graph);
				UAnimGraphNode_LinkedInputPose* Input = Creator.CreateNode(/*bSelectNewNode*/ false);
				Input->NodePosX = Root->NodePosX - 500;
				Input->NodePosY = Root->NodePosY + PoseIndex * 150;
				Creator.Finalize();   // PostPlacedNewNode 가 기본 이름(InPose…)을 준다 — 아래서 덮어쓴다
				Input->Node.Name = FName(*Pose.Name);
				for (const FInputParam& P : Pose.Inputs)
				{
					FEdGraphPinType PinType;
					FAnimMcpError Ignored;
					AnimMcpVariables::ParsePinType(P.Type, PinType, Ignored);   // ParseInputParams 가 이미 검증했다
					Input->Inputs.Emplace(FName(*P.Name), PinType);
				}
				Input->ReconstructNode();
				++PoseIndex;
			}
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

		if (!AddLayerGraphs(NewBP, Params.Layers, OutError))
		{
			return nullptr;
		}

		FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(NewBP);
		FAssetRegistryModule::AssetCreated(NewBP);
		NewBP->MarkPackageDirty();
		UE_LOG(LogAnimGraphMcp, Log, TEXT("Created Anim Layer Interface %s (%d layers)"), *ObjectPath, Params.Layers.Num());
		return NewBP;
	}

	bool IsLayerInterface(const UAnimBlueprint* Blueprint)
	{
		return Blueprint && Blueprint->BlueprintType == BPTYPE_Interface && Blueprint->ParentClass && Blueprint->ParentClass->IsChildOf(UAnimLayerInterface::StaticClass());
	}

	bool RemoveLayerGraphs(UAnimBlueprint* Blueprint, const TArray<FString>& Names, bool bForce, FAnimMcpContext& Context, FAnimMcpError& OutError, TArray<TSharedPtr<FJsonValue>>& OutUsage)
	{
		check(Blueprint);
		OutUsage.Reset();
		// 대상 그래프 — 자체 레이어(FunctionGraphs)만. 구현 그래프는 인터페이스 쪽에서 지운다
		TArray<UEdGraph*> Graphs;
		TSet<FString> Seen;
		for (const FString& Raw : Names)
		{
			const FString Name = Raw.TrimStartAndEnd();
			if (Name.IsEmpty() || Seen.Contains(Name))
			{
				OutError = Reason(FString::Printf(TEXT("Layer name '%s' is empty or repeated"), *Name), TEXT("BAD_SHAPE"), TEXT("layers"));
				return false;
			}
			Seen.Add(Name);
			UClass* Interface = nullptr;
			UEdGraph* Graph = FindLayerGraph(Blueprint, FName(*Name), Interface);
			if (!Graph || !IsOwnLayerGraph(Blueprint, Graph))
			{
				OutError = Reason(FString::Printf(TEXT("'%s' is not a layer graph owned by %s%s"), *Name, *Blueprint->GetName(), Graph ? TEXT(" (it implements an interface layer — remove it from the interface)") : TEXT("")), Graph ? TEXT("NOT_EDITABLE") : TEXT("UNKNOWN_LAYER"), TEXT("layers"));
				return false;
			}
			Graphs.Add(Graph);
		}

		// 사용 검사 — 인터페이스면 참조 ABP(디스크 참조자), 아니면 자기 자신
		auto CollectUsage = [&OutUsage](UAnimBlueprint* Implementer, const FString& LayerName, bool bInterfaceGraph)
		{
			UClass* Interface = nullptr;
			if (UEdGraph* Graph = bInterfaceGraph ? FindLayerGraph(Implementer, FName(*LayerName), Interface) : nullptr)
			{
				int32 Extra = 0;
				for (const UEdGraphNode* N : Graph->Nodes)
				{
					if (N && !N->IsA<UAnimGraphNode_Root>() && !N->IsA<UAnimGraphNode_LinkedInputPose>()) { ++Extra; }
				}
				if (Extra > 0)
				{
					TSharedRef<FJsonObject> U = AnimMcpJson::MakeObject();
					U->SetStringField(TEXT("asset_path"), Implementer->GetPathName());
					U->SetStringField(TEXT("layer"), LayerName);
					U->SetStringField(TEXT("kind"), TEXT("implementation_graph_not_empty"));
					U->SetNumberField(TEXT("node_count"), Extra);
					OutUsage.Add(MakeShared<FJsonValueObject>(U));
				}
			}
			TArray<UAnimGraphNode_LinkedAnimLayer*> LayerNodes;
			FBlueprintEditorUtils::GetAllNodesOfClass<UAnimGraphNode_LinkedAnimLayer>(Implementer, LayerNodes);
			for (const UAnimGraphNode_LinkedAnimLayer* N : LayerNodes)
			{
				if (N && N->Node.Layer == FName(*LayerName))
				{
					TSharedRef<FJsonObject> U = AnimMcpJson::MakeObject();
					U->SetStringField(TEXT("asset_path"), Implementer->GetPathName());
					U->SetStringField(TEXT("layer"), LayerName);
					U->SetStringField(TEXT("kind"), TEXT("linked_layer_node"));
					U->SetStringField(TEXT("node_guid"), N->NodeGuid.ToString());
					U->SetStringField(TEXT("graph"), GetNameSafe(N->GetGraph()));
					OutUsage.Add(MakeShared<FJsonValueObject>(U));
				}
			}
		};
		if (IsLayerInterface(Blueprint))
		{
			for (const FString& RefPath : AnimMcpAssetOps::FindReferencers(Blueprint->GetPathName()))
			{
				FAnimMcpError Ignored;
				UAnimBlueprint* Implementer = Cast<UAnimBlueprint>(AnimMcpAssetResolver::LoadAssetOfClass(RefPath, UAnimBlueprint::StaticClass(), Ignored));
				if (!Implementer || Implementer == Blueprint) { continue; }
				for (const FString& Name : Seen) { CollectUsage(Implementer, Name, /*bInterfaceGraph*/ true); }
			}
		}
		else
		{
			for (const FString& Name : Seen) { CollectUsage(Blueprint, Name, /*bInterfaceGraph*/ false); }
		}
		if (OutUsage.Num() > 0 && !bForce)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("reason"), TEXT("LAYER_IN_USE_BY"));
			Details->SetStringField(TEXT("field"), TEXT("layers"));
			Details->SetArrayField(TEXT("usage"), OutUsage);
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("%d usage(s) of the layer(s) found (filled implementation graphs or LinkedAnimLayer nodes) — pass force=true to remove anyway (implementation contents are lost, nodes fail to compile)"), OutUsage.Num()), Details);
			return false;
		}
		if (OutUsage.Num() > 0)
		{
			Context.AddDiagnostic(TEXT("warning"), TEXT("LAYER_IN_USE_BY"), FString::Printf(TEXT("Removing layer(s) with %d usage(s) (force=true)"), OutUsage.Num()));
		}

		Blueprint->Modify();
		for (UEdGraph* Graph : Graphs)
		{
			UE_LOG(LogAnimGraphMcp, Log, TEXT("%s: removing layer graph '%s'"), *Blueprint->GetPathName(), *Graph->GetName());
			FBlueprintEditorUtils::RemoveGraph(Blueprint, Graph, EGraphRemoveFlags::MarkTransient);   // 재컴파일은 호출자가 한 번에
		}
		FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
		return true;
	}

	bool SetLayerInputs(UAnimBlueprint* Blueprint, const FString& Layer, const FString& InputPose, const TArray<FInputParam>& Inputs, bool& bOutUnchanged, FAnimMcpError& OutError)
	{
		check(Blueprint);
		bOutUnchanged = false;
		if (!ValidateLayerName(Blueprint, Layer, OutError)) { return false; }
		UClass* Interface = nullptr;
		UEdGraph* Graph = FindLayerGraph(Blueprint, FName(*Layer), Interface);
		if (!IsOwnLayerGraph(Blueprint, Graph))
		{
			OutError = Reason(FString::Printf(TEXT("Layer '%s' implements interface '%s' — its inputs are defined on the interface asset"), *Layer, *GetNameSafe(Interface)), TEXT("NOT_EDITABLE"), TEXT("layer"));
			return false;
		}
		TArray<UAnimGraphNode_LinkedInputPose*> Poses = InputPoseNodesOf(Graph);
		UAnimGraphNode_LinkedInputPose* Target = nullptr;
		if (Poses.Num() == 0)
		{
			OutError = Reason(FString::Printf(TEXT("Layer '%s' has no input pose — value inputs live on an Input Pose node (add one with input_poses)"), *Layer), TEXT("NO_INPUT_POSE"), TEXT("input_pose"));
			return false;
		}
		if (InputPose.IsEmpty())
		{
			if (Poses.Num() > 1)
			{
				OutError = Reason(FString::Printf(TEXT("Layer '%s' has %d input poses — name one with 'input_pose'"), *Layer, Poses.Num()), TEXT("AMBIGUOUS_INPUT_POSE"), TEXT("input_pose"));
				return false;
			}
			Target = Poses[0];
		}
		else
		{
			for (UAnimGraphNode_LinkedInputPose* P : Poses) { if (P->Node.Name == FName(*InputPose)) { Target = P; break; } }
			if (!Target)
			{
				OutError = Reason(FString::Printf(TEXT("Layer '%s' has no input pose named '%s' (known: %s)"), *Layer, *InputPose, *FString::Join(InputPoseNamesOf(Graph), TEXT(", "))), TEXT("UNKNOWN_INPUT_POSE"), TEXT("input_pose"));
				return false;
			}
		}
		// 다른 Input Pose 와의 이름 충돌 (HandleInputPinArrayChanged 가 BP 안의 모든 Input Pose Inputs 에서 유일 이름을 만든다 — 같은 규칙)
		TArray<FAnimBlueprintFunctionPinInfo> NewInputs;
		for (const FInputParam& P : Inputs)
		{
			FEdGraphPinType PinType;
			if (!AnimMcpVariables::ParsePinType(P.Type, PinType, OutError)) { return false; }
			if (FName(*P.Name) == Target->Node.Name)
			{
				OutError = Reason(FString::Printf(TEXT("Input '%s' has the same name as the input pose"), *P.Name), TEXT("DUPLICATE_NAME"), TEXT("inputs"));
				return false;
			}
			for (UEdGraph* G : Blueprint->FunctionGraphs)
			{
				if (!G || !G->IsA<UAnimationGraph>()) { continue; }
				for (const UAnimGraphNode_LinkedInputPose* Other : InputPoseNodesOf(G))
				{
					if (Other == Target) { continue; }
					for (const FAnimBlueprintFunctionPinInfo& Existing : Other->Inputs)
					{
						if (Existing.Name == FName(*P.Name))
						{
							OutError = Reason(FString::Printf(TEXT("Input '%s' is already used by input pose '%s' of layer '%s' (input names are unique per blueprint)"), *P.Name, *Other->Node.Name.ToString(), *G->GetName()), TEXT("DUPLICATE_NAME"), TEXT("inputs"));
							return false;
						}
					}
				}
			}
			NewInputs.Emplace(FName(*P.Name), PinType);
		}
		// 같은 목록이면 no-op
		if (NewInputs.Num() == Target->Inputs.Num())
		{
			bool bSame = true;
			for (int32 i = 0; i < NewInputs.Num() && bSame; ++i)
			{
				bSame = NewInputs[i].Name == Target->Inputs[i].Name && NewInputs[i].Type == Target->Inputs[i].Type;
			}
			if (bSame) { bOutUnchanged = true; return true; }
		}
		Target->Modify();
		Target->Inputs = NewInputs;
		// Persona 디테일 패널과 같은 경로 — PostEditChangeProperty(Inputs) 가 이름 보정·재구성·구조 변경·self 레이어 노드 재구성을 한다
		FProperty* InputsProp = UAnimGraphNode_LinkedInputPose::StaticClass()->FindPropertyByName(GET_MEMBER_NAME_CHECKED(UAnimGraphNode_LinkedInputPose, Inputs));
		FPropertyChangedEvent Event(InputsProp, EPropertyChangeType::ValueSet);
		Target->PostEditChangeProperty(Event);
		return true;
	}

	TArray<TSharedPtr<FJsonValue>> ConformImplementers(UAnimBlueprint* InterfaceBP, FAnimMcpContext& Context)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		if (!InterfaceBP || !InterfaceBP->GeneratedClass) { return Out; }
		for (const FString& RefPath : AnimMcpAssetOps::FindReferencers(InterfaceBP->GetPathName()))
		{
			FAnimMcpError Ignored;
			UAnimBlueprint* Implementer = Cast<UAnimBlueprint>(AnimMcpAssetResolver::LoadAssetOfClass(RefPath, UAnimBlueprint::StaticClass(), Ignored));
			if (!Implementer || Implementer == InterfaceBP) { continue; }
			bool bImplements = false;
			for (const FBPInterfaceDescription& Desc : Implementer->ImplementedInterfaces)
			{
				bImplements |= Desc.Interface && Desc.Interface->ClassGeneratedBy == InterfaceBP;
			}
			if (!bImplements) { continue; }
			Implementer->Modify();
			FBlueprintEditorUtils::ConformImplementedInterfaces(Implementer);
			TSharedRef<FJsonObject> Compile = AnimMcpCompiler::Compile(Implementer, Context);
			TSharedRef<FJsonObject> O = AnimMcpJson::MakeObject();
			O->SetStringField(TEXT("asset_path"), Implementer->GetPathName());
			O->SetBoolField(TEXT("conformed"), true);
			O->SetObjectField(TEXT("compile"), Compile);
			Out.Add(MakeShared<FJsonValueObject>(O));
		}
		return Out;
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

	// ---- Phase 7-4 InstanceClass --------------------------------------------------------------------------------

	UClass* ResolveAnimInstanceClass(const FString& Path, FAnimMcpError& OutError)
	{
		const FString Trimmed = Path.TrimStartAndEnd();
		UClass* Class = nullptr;
		// 1) AnimBP 애셋 경로 → GeneratedClass
		{
			FAnimMcpError Ignored;
			if (UAnimBlueprint* BP = Cast<UAnimBlueprint>(AnimMcpAssetResolver::LoadAssetOfClass(Trimmed, UAnimBlueprint::StaticClass(), Ignored)))
			{
				if (!BP->GeneratedClass)
				{
					OutError = Reason(FString::Printf(TEXT("'%s' has no generated class — compile it first"), *BP->GetPathName()), TEXT("NOT_COMPILED"), TEXT("instance_class"));
					return nullptr;
				}
				Class = BP->GeneratedClass;
			}
		}
		// 2) 클래스 경로 ("/Game/A/ABP_X.ABP_X_C" · "/Script/Module.Class")
		if (!Class)
		{
			Class = LoadObject<UClass>(nullptr, *Trimmed);
		}
		if (!Class)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetNotFound, FString::Printf(TEXT("No Animation Blueprint or class at '%s'"), *Trimmed));
			if (!OutError.Details.IsValid()) { OutError.Details = AnimMcpJson::MakeObject(); }
			OutError.Details->SetStringField(TEXT("field"), TEXT("instance_class"));
			return nullptr;
		}
		if (!Class->IsChildOf(UAnimInstance::StaticClass()))
		{
			OutError = Reason(FString::Printf(TEXT("'%s' is not an AnimInstance class"), *Class->GetPathName()), TEXT("BAD_CLASS"), TEXT("instance_class"));
			return nullptr;
		}
		return Class;
	}

	bool ValidateInstanceClass(UAnimGraphNode_LinkedAnimLayer* Node, UClass* Class, FAnimMcpError& OutError)
	{
		check(Node);
		UAnimBlueprint* Blueprint = Cast<UAnimBlueprint>(FBlueprintEditorUtils::FindBlueprintForNode(Node));
		if (!Blueprint)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("Linked layer node has no Animation Blueprint"));
			return false;
		}
		if (!Class)
		{
			return true;   // 해제는 언제나 가능
		}
		UClass* Interface = Node->Node.Interface.Get();
		if (!Interface)
		{
			OutError = Reason(FString::Printf(TEXT("Layer '%s' is a self layer — only interface layers can be redirected to an InstanceClass"), *Node->Node.Layer.ToString()), TEXT("SELF_LAYER"), TEXT("instance_class"));
			return false;
		}
		if (!Class->ImplementsInterface(Interface))
		{
			OutError = Reason(FString::Printf(TEXT("'%s' does not implement interface '%s'"), *Class->GetPathName(), *Interface->GetPathName()), TEXT("NOT_IMPLEMENTING"), TEXT("instance_class"));
			return false;
		}
		if (Class == Blueprint->GeneratedClass || Class == Blueprint->SkeletonGeneratedClass)
		{
			OutError = Reason(TEXT("InstanceClass cannot be this blueprint's own class (would loop)"), TEXT("SELF_CLASS"), TEXT("instance_class"));
			return false;
		}
		if (UAnimBlueprint* TargetBP = Cast<UAnimBlueprint>(UBlueprint::GetBlueprintFromClass(Class)))
		{
			if (!Blueprint->IsCompatible(TargetBP))
			{
				OutError = Reason(FString::Printf(TEXT("'%s' (skeleton %s) is not compatible with this blueprint (skeleton %s)"), *TargetBP->GetPathName(), *GetNameSafe(TargetBP->TargetSkeleton), *GetNameSafe(Blueprint->TargetSkeleton)), TEXT("INCOMPATIBLE"), TEXT("instance_class"));
				return false;
			}
		}
		// 값 핀(비-포즈 입력)이 링크돼 있으면 재구성 뒤 고아가 될 수 있다 — 먼저 끊는다
		TArray<FString> Linked;
		for (const UEdGraphPin* Pin : Node->Pins)
		{
			if (Pin && Pin->Direction == EGPD_Input && !UAnimationGraphSchema::IsPosePin(Pin->PinType) && Pin->LinkedTo.Num() > 0)
			{
				Linked.Add(Pin->PinName.ToString());
			}
		}
		if (Linked.Num() > 0)
		{
			OutError = Reason(FString::Printf(TEXT("Value pin(s) %s are linked; disconnect them before changing the instance class (pins are rebuilt from the new class)"), *FString::Join(Linked, TEXT(", "))), TEXT("PINS_LINKED"), TEXT("instance_class"));
			return false;
		}
		return true;
	}

	bool SetInstanceClass(UAnimGraphNode_LinkedAnimLayer* Node, UClass* Class, FInstanceRef& OutOld, FAnimMcpError& OutError)
	{
		if (!ValidateInstanceClass(Node, Class, OutError)) { return false; }
		FMemberReference* FunctionReference = FunctionReferenceOf(Node);
		if (!FunctionReference)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("FunctionReference not found on UAnimGraphNode_LinkedAnimGraphBase by reflection"));
			return false;
		}
		OutOld.InstanceClass = Node->Node.InstanceClass;
		OutOld.FunctionReference = *FunctionReference;

		// SetupFromLayerId :994-1005 — TargetClass(=InstanceClass) 가 있으면 외부 멤버(함수 Guid 포함), 없으면 self 멤버
		Node->Modify();
		Node->Node.InstanceClass = Class ? TSubclassOf<UAnimInstance>(Class) : nullptr;
		const FName Layer = Node->Node.Layer;
		if (Class)
		{
			FGuid FunctionGuid;
			FBlueprintEditorUtils::GetFunctionGuidFromClassByFieldName(FBlueprintEditorUtils::GetMostUpToDateClass(Class), Layer, FunctionGuid);
			FunctionReference->SetExternalMember(Layer, Class, FunctionGuid);
		}
		else
		{
			FunctionReference->SetSelfMember(Layer);
		}
		Node->ReconstructNode();
		return true;
	}

	void RestoreInstanceClass(UAnimGraphNode_LinkedAnimLayer* Node, const FInstanceRef& Old)
	{
		Node->Modify();
		Node->Node.InstanceClass = Old.InstanceClass;
		if (FMemberReference* FunctionReference = FunctionReferenceOf(Node)) { *FunctionReference = Old.FunctionReference; }
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
		auto Describe = [&Out, Blueprint](UEdGraph* G, UClass* Interface)
		{
			TSharedRef<FJsonObject> O = AnimMcpJson::MakeObject();
			O->SetStringField(TEXT("name"), G->GetName());
			O->SetStringField(TEXT("graph_guid"), G->GraphGuid.ToString());
			O->SetField(TEXT("interface"), Interface ? AnimMcpJson::StringOrNull(Interface->GetPathName()) : MakeShared<FJsonValueNull>());
			O->SetField(TEXT("interface_guid"), G->InterfaceGuid.IsValid() ? AnimMcpJson::StringOrNull(G->InterfaceGuid.ToString()) : MakeShared<FJsonValueNull>());
			const UAnimGraphNode_Root* Root = RootOf(G);
			const FName Group = Root ? Root->Node.GetGroup() : NAME_None;
			O->SetField(TEXT("group"), Group.IsNone() ? MakeShared<FJsonValueNull>() : AnimMcpJson::StringOrNull(Group.ToString()));
			O->SetBoolField(TEXT("editable"), IsOwnLayerGraph(Blueprint, G));
			TArray<TSharedPtr<FJsonValue>> Poses;
			TArray<TSharedPtr<FJsonValue>> Inputs;
			for (const UAnimGraphNode_LinkedInputPose* P : InputPoseNodesOf(G))
			{
				Poses.Add(MakeShared<FJsonValueString>(P->Node.Name.ToString()));
				// (7-4) 값 입력 = Input Pose 노드의 비-포즈 출력 핀 (자체 그래프는 Inputs, 구현 그래프는 스텁 함수 파라미터)
				for (const TPair<FName, FEdGraphPinType>& V : ValueInputsOf(P))
				{
					TSharedRef<FJsonObject> I = AnimMcpJson::MakeObject();
					I->SetStringField(TEXT("name"), V.Key.ToString());
					I->SetStringField(TEXT("type"), AnimMcpVariables::PinTypeToText(V.Value));
					I->SetStringField(TEXT("input_pose"), P->Node.Name.ToString());
					Inputs.Add(MakeShared<FJsonValueObject>(I));
				}
			}
			O->SetArrayField(TEXT("input_poses"), Poses);
			O->SetArrayField(TEXT("inputs"), Inputs);
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
