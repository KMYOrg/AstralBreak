#include "AnimMcpTools.h"

#include "Animation/AnimBlueprint.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAnimLayer.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpCompiler.h"
#include "Core/AnimMcpGraphInspector.h"
#include "Kismet2/BlueprintEditorUtils.h"

namespace AnimMcpTools
{
	namespace
	{
		/** 공통 응답 — info + layers + implemented_interfaces + (선택) compile · saved */
		TSharedRef<FJsonObject> BuildLayerResult(UAnimBlueprint* Blueprint, FAnimMcpContext& Context, bool bCompile, bool bSave)
		{
			TSharedPtr<FJsonObject> Compile;
			bool bSaved = false;
			if (bCompile)
			{
				Compile = AnimMcpCompiler::Compile(Blueprint, Context);
			}
			if (bSave)
			{
				if (!bCompile || Compile->GetBoolField(TEXT("ok")))
				{
					FAnimMcpError SaveError;
					bSaved = AnimMcpCompiler::Save(Blueprint, SaveError);
					if (!bSaved) { Context.AddDiagnostic(TEXT("error"), *SaveError.Code, SaveError.Message); }
				}
				else
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("SAVE_SKIPPED"), TEXT("Not saved because compile reported errors"));
				}
			}
			TSharedRef<FJsonObject> Result = AnimMcpGraphInspector::BuildBlueprintInfo(Blueprint, Context);
			if (Compile.IsValid()) { Result->SetObjectField(TEXT("compile"), Compile); }
			Result->SetBoolField(TEXT("saved"), bSaved);
			return Result;
		}

		/** (7-4) 인터페이스를 바꾼 뒤 — conform_implementers 면 참조 ABP 를 로드해 동기화·컴파일하고 implementers[] 를 붙인다 */
		void AppendImplementers(TSharedRef<FJsonObject>& Result, UAnimBlueprint* Blueprint, FAnimMcpContext& Context, bool bConform)
		{
			if (bConform && AnimMcpAnimLayer::IsLayerInterface(Blueprint))
			{
				Result->SetArrayField(TEXT("implementers"), AnimMcpAnimLayer::ConformImplementers(Blueprint, Context));
			}
			else
			{
				Result->SetArrayField(TEXT("implementers"), TArray<TSharedPtr<FJsonValue>>());
			}
		}
	}

	void RegisterLayerTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("create_anim_layer_interface"),
			TEXT("Create an Animation Layer Interface asset (Lyra-style layer separation) with one layer graph per entry. Params: asset_path, layers [{name, group?, input_poses? [\"Name\" | {name, inputs? [{name, type}]}]}], overwrite? (default false; refused for protected assets), save? (default false). The interface is compiled so other Animation Blueprints can implement it. Value parameters (inputs) live on an input pose node and become value pins on LinkedAnimLayer nodes."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				AnimMcpAnimLayer::FCreateInterfaceParams Params;
				if (!AnimMcpAnimLayer::ParseCreateInterfaceParams(Context.Request.Params, Params, OutError)) { return nullptr; }
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);
				UAnimBlueprint* Interface = AnimMcpAnimLayer::CreateLayerInterface(Params, Context, OutError);
				if (!Interface) { return nullptr; }
				TSharedRef<FJsonObject> Result = BuildLayerResult(Interface, Context, /*bCompile*/ true, bSave);
				Result->SetBoolField(TEXT("created"), true);
				return Result;
			});

		Dispatcher.RegisterTool(TEXT("implement_anim_layer_interface"),
			TEXT("Make an Animation Blueprint implement an Animation Layer Interface: one layer graph per interface layer is added (root + input pose nodes come from the interface signature). Params: asset_path (the Animation Blueprint), interface (the layer interface asset path), compile? (default true), save? (default false). Afterwards add_node AnimGraphNode_LinkedAnimLayer with \"layer\": \"<name>\" to use a layer, and edit the layer graphs via get_anim_blueprint_info.layers[].graph_guid."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath, InterfacePath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				if (!Context.Request.GetRequiredString(TEXT("interface"), InterfacePath, OutError)) { return nullptr; }
				const bool bCompile = Context.Request.GetOptionalBool(TEXT("compile"), true);
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);

				UAnimBlueprint* Target = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Target) { return nullptr; }
				UAnimBlueprint* Interface = AnimMcpAssetResolver::LoadAnimBlueprint(InterfacePath, OutError);
				if (!Interface)
				{
					if (OutError.Details.IsValid()) { OutError.Details->SetStringField(TEXT("field"), TEXT("interface")); }
					return nullptr;
				}
				if (!AnimMcpAnimLayer::ImplementInterface(Target, Interface, Context, OutError)) { return nullptr; }

				TSharedRef<FJsonObject> Result = BuildLayerResult(Target, Context, bCompile, bSave);
				Result->SetBoolField(TEXT("implemented"), true);
				Result->SetStringField(TEXT("interface"), Interface->GeneratedClass ? Interface->GeneratedClass->GetPathName() : Interface->GetPathName());
				return Result;
			});

		// ---- Phase 7-4 ----------------------------------------------------------------------------------------------

		Dispatcher.RegisterTool(TEXT("set_layer_inputs"),
			TEXT("Replace the value parameters of a layer (the Inputs of its input pose node). Params: asset_path (a layer interface, or an Animation Blueprint for one of its own layers — interface implementation graphs are refused with NOT_EDITABLE), layer, input_pose? (required when the layer has several input poses), inputs [{name, type}] (whole list; [] clears; types as in add_blueprint_variable), compile? (default true), save? (default false), conform_implementers? (default true; for an interface: load referencing Animation Blueprints, conform and compile them → implementers[]). Same list = unchanged. Implementers see the parameters as value pins on their LinkedAnimLayer nodes (expose_pin) and as output pins of the input pose node inside the layer graph."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath, Layer;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				if (!Context.Request.GetRequiredString(TEXT("layer"), Layer, OutError)) { return nullptr; }
				const FString InputPose = Context.Request.GetOptionalString(TEXT("input_pose"));
				const bool bCompile = Context.Request.GetOptionalBool(TEXT("compile"), true);
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);
				const bool bConform = Context.Request.GetOptionalBool(TEXT("conform_implementers"), true);
				const TArray<TSharedPtr<FJsonValue>>* InputsArr = nullptr;
				if (!Context.Request.Params->TryGetArrayField(TEXT("inputs"), InputsArr) || !InputsArr)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("set_layer_inputs requires 'inputs' ([{name, type}]; [] to clear)"));
					return nullptr;
				}
				TArray<AnimMcpAnimLayer::FInputParam> Inputs;
				if (!AnimMcpAnimLayer::ParseInputParams(*InputsArr, Inputs, OutError, TEXT("inputs"))) { return nullptr; }

				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint) { return nullptr; }
				bool bUnchanged = false;
				if (!AnimMcpAnimLayer::SetLayerInputs(Blueprint, Layer, InputPose, Inputs, bUnchanged, OutError)) { return nullptr; }

				TSharedRef<FJsonObject> Result = BuildLayerResult(Blueprint, Context, bCompile && !bUnchanged, bSave);
				Result->SetBoolField(TEXT("unchanged"), bUnchanged);
				AppendImplementers(Result, Blueprint, Context, bConform && !bUnchanged);
				return Result;
			});

		Dispatcher.RegisterTool(TEXT("add_anim_layers"),
			TEXT("Add layer graphs to an existing Animation Layer Interface (interface layers) or to an Animation Blueprint (its own layers). Params: asset_path, layers [{name, group?, input_poses? [\"Name\" | {name, inputs? [{name, type}]}]}], compile? (default true), save? (default false), conform_implementers? (default true; interface only: referencing Animation Blueprints are loaded, conformed — they gain the new layer graphs — and compiled → implementers[]). Names must not collide with existing graphs; nothing is added when any entry is invalid."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				const bool bCompile = Context.Request.GetOptionalBool(TEXT("compile"), true);
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);
				const bool bConform = Context.Request.GetOptionalBool(TEXT("conform_implementers"), true);
				const TArray<TSharedPtr<FJsonValue>>* LayersArr = nullptr;
				if (!Context.Request.Params->TryGetArrayField(TEXT("layers"), LayersArr) || !LayersArr)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("add_anim_layers requires 'layers' ([{name, group?, input_poses?}])"));
					return nullptr;
				}
				TArray<AnimMcpAnimLayer::FLayerParams> Layers;
				if (!AnimMcpAnimLayer::ParseLayerList(*LayersArr, Layers, OutError)) { return nullptr; }

				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint) { return nullptr; }
				Blueprint->Modify();
				if (!AnimMcpAnimLayer::AddLayerGraphs(Blueprint, Layers, OutError)) { return nullptr; }
				FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
				Blueprint->MarkPackageDirty();

				TSharedRef<FJsonObject> Result = BuildLayerResult(Blueprint, Context, bCompile, bSave);
				TArray<TSharedPtr<FJsonValue>> Added;
				for (const AnimMcpAnimLayer::FLayerParams& L : Layers) { Added.Add(MakeShared<FJsonValueString>(L.Name)); }
				Result->SetArrayField(TEXT("added"), Added);
				AppendImplementers(Result, Blueprint, Context, bConform);
				return Result;
			});

		Dispatcher.RegisterTool(TEXT("remove_anim_layers"),
			TEXT("Remove layer graphs from an Animation Layer Interface or an Animation Blueprint's own layers. Params: asset_path, layers [names], force? (default false), compile? (default true), save? (default false), conform_implementers? (default true). For an interface, referencing Animation Blueprints are inspected first: a non-empty implementation graph or a LinkedAnimLayer node using the layer is refused with LAYER_IN_USE_BY (details.usage[]) unless force=true — then the implementation contents are lost and such nodes fail to compile. Interface implementation graphs cannot be removed from the implementer (NOT_EDITABLE)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				const bool bForce = Context.Request.GetOptionalBool(TEXT("force"), false);
				const bool bCompile = Context.Request.GetOptionalBool(TEXT("compile"), true);
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);
				const bool bConform = Context.Request.GetOptionalBool(TEXT("conform_implementers"), true);
				const TArray<TSharedPtr<FJsonValue>>* LayersArr = nullptr;
				if (!Context.Request.Params->TryGetArrayField(TEXT("layers"), LayersArr) || !LayersArr || LayersArr->Num() == 0)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("remove_anim_layers requires a non-empty 'layers' array of names"));
					return nullptr;
				}
				TArray<FString> Names;
				for (const TSharedPtr<FJsonValue>& V : *LayersArr)
				{
					FString Name;
					if (!V.IsValid() || !V->TryGetString(Name))
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("'layers' entries must be layer name strings"));
						return nullptr;
					}
					Names.Add(Name);
				}

				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint) { return nullptr; }
				TArray<TSharedPtr<FJsonValue>> Usage;
				if (!AnimMcpAnimLayer::RemoveLayerGraphs(Blueprint, Names, bForce, Context, OutError, Usage)) { return nullptr; }
				Blueprint->MarkPackageDirty();

				TSharedRef<FJsonObject> Result = BuildLayerResult(Blueprint, Context, bCompile, bSave);
				TArray<TSharedPtr<FJsonValue>> Removed;
				for (const FString& N : Names) { Removed.Add(MakeShared<FJsonValueString>(N.TrimStartAndEnd())); }
				Result->SetArrayField(TEXT("removed"), Removed);
				Result->SetArrayField(TEXT("usage"), Usage);
				Result->SetBoolField(TEXT("forced"), bForce && Usage.Num() > 0);
				AppendImplementers(Result, Blueprint, Context, bConform);
				return Result;
			});
	}
}
