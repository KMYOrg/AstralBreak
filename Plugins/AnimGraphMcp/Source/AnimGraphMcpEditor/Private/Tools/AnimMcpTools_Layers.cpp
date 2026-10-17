#include "AnimMcpTools.h"

#include "Animation/AnimBlueprint.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAnimLayer.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpCompiler.h"
#include "Core/AnimMcpGraphInspector.h"

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
	}

	void RegisterLayerTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("create_anim_layer_interface"),
			TEXT("Create an Animation Layer Interface asset (Lyra-style layer separation) with one layer graph per entry. Params: asset_path, layers [{name, group?, input_poses? [names]}], overwrite? (default false; refused for protected assets), save? (default false). The interface is compiled so other Animation Blueprints can implement it. Pose inputs only (no value parameters)."),
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
	}
}
