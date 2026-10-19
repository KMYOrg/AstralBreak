#include "AnimMcpTools.h"

#include "Animation/AnimBlueprint.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpCompiler.h"
#include "Core/AnimMcpGraphInspector.h"
#include "Core/AnimMcpUpdateFunction.h"
#include "Core/AnimMcpVariables.h"
#include "ScopedTransaction.h"

namespace AnimMcpTools
{
	namespace
	{
		/** 공통 응답 — info + (선택) compile · saved */
		TSharedRef<FJsonObject> BuildVariableResult(UAnimBlueprint* Blueprint, FAnimMcpContext& Context, bool bCompile, bool bSave)
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

	void RegisterVariableTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("add_blueprint_variable"),
			TEXT("Add a member variable to an Animation Blueprint (so rules, K2Node_VariableGet, bind_pin and set_update_function can use it without C++ changes). Params: asset_path, name, type (bool|float|int|int64|name|string|text|byte|vector|vector2d|rotator|transform|linearcolor|object:<class path>|class:<class path>|struct:<struct path>|enum:<enum path>), default? (text, e.g. \"true\", \"0.5\", \"(X=0,Y=0,Z=0)\"), category?, instance_editable? (default false), compile? (default false), save? (default false). Returns the blueprint info plus 'added' and 'declaration'."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				AnimMcpVariables::FAddParams Params;
				if (!Context.Request.GetRequiredString(TEXT("name"), Params.Name, OutError)) { return nullptr; }
				if (!Context.Request.GetRequiredString(TEXT("type"), Params.Type, OutError)) { return nullptr; }
				Params.DefaultValue = Context.Request.GetOptionalString(TEXT("default"));
				Params.Category = Context.Request.GetOptionalString(TEXT("category"));
				Params.bInstanceEditable = Context.Request.GetOptionalBool(TEXT("instance_editable"), false);
				const bool bCompile = Context.Request.GetOptionalBool(TEXT("compile"), false);
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);

				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint) { return nullptr; }
				{
					FScopedTransaction Transaction(NSLOCTEXT("AnimGraphMcp", "AddVariable", "AnimGraphMcp add_blueprint_variable"));
					if (!AnimMcpVariables::AddVariable(Blueprint, Params, OutError))
					{
						Transaction.Cancel();
						return nullptr;
					}
				}
				TSharedRef<FJsonObject> Result = BuildVariableResult(Blueprint, Context, bCompile, bSave);
				Result->SetStringField(TEXT("added"), Params.Name.TrimStartAndEnd());
				const TSharedPtr<FJsonObject> Declaration = AnimMcpVariables::DescribeDeclaration(Blueprint, FName(*Params.Name.TrimStartAndEnd()));
				TSharedPtr<FJsonValue> DeclarationValue = Declaration.IsValid() ? TSharedPtr<FJsonValue>(MakeShared<FJsonValueObject>(Declaration)) : TSharedPtr<FJsonValue>(MakeShared<FJsonValueNull>());
				Result->SetField(TEXT("declaration"), DeclarationValue);
				return Result;
			});

		Dispatcher.RegisterTool(TEXT("remove_blueprint_variable"),
			TEXT("Remove a member variable declared by this Animation Blueprint (native C++ properties cannot be removed). Params: asset_path, name, force? (default false; if graph nodes reference the variable the call fails with VARIABLE_IN_USE unless force=true, which also deletes those nodes), compile? (default false), save? (default false). Returns the blueprint info plus 'removed' and 'was_used'."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath, Name;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				if (!Context.Request.GetRequiredString(TEXT("name"), Name, OutError)) { return nullptr; }
				const bool bForce = Context.Request.GetOptionalBool(TEXT("force"), false);
				const bool bCompile = Context.Request.GetOptionalBool(TEXT("compile"), false);
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);

				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint) { return nullptr; }
				bool bWasUsed = false;
				{
					FScopedTransaction Transaction(NSLOCTEXT("AnimGraphMcp", "RemoveVariable", "AnimGraphMcp remove_blueprint_variable"));
					if (!AnimMcpVariables::RemoveVariable(Blueprint, Name, bForce, bWasUsed, OutError))
					{
						Transaction.Cancel();
						return nullptr;
					}
				}
				if (bWasUsed)
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("VARIABLE_NODES_REMOVED"), FString::Printf(TEXT("Graph nodes referencing '%s' were removed with the variable"), *Name));
				}
				TSharedRef<FJsonObject> Result = BuildVariableResult(Blueprint, Context, bCompile, bSave);
				Result->SetStringField(TEXT("removed"), Name.TrimStartAndEnd());
				Result->SetBoolField(TEXT("was_used"), bWasUsed);
				return Result;
			});

		Dispatcher.RegisterTool(TEXT("set_update_function"),
			TEXT("Generate the Animation Blueprint's BlueprintThreadSafeUpdateAnimation function from a spec (the whole function graph is regenerated, like transition rules; re-applying the same spec is a no-op). Params: asset_path, assignments [{variable, value}] where value is a rule-style expression ({\"access\": \"Pawn.Velocity\"} property access, {\"param\": \"DeltaTime\"}, {\"var\"}, {\"call\"}, {\"compare\"}, {\"literal\"} ...), remove? (true deletes the override), compile? (default true), save? (default false). Variables must be BlueprintVisible and not BlueprintReadOnly (add_blueprint_variable or BlueprintReadWrite C++ properties). Returns the blueprint info plus 'update_function'."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				const bool bRemove = Context.Request.GetOptionalBool(TEXT("remove"), false);
				const bool bCompile = Context.Request.GetOptionalBool(TEXT("compile"), true);
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);

				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint) { return nullptr; }

				TSharedRef<FJsonObject> Applied = AnimMcpJson::MakeObject();
				if (bRemove)
				{
					if (!AnimMcpUpdateFunction::Remove(Blueprint, OutError)) { return nullptr; }
					Applied->SetBoolField(TEXT("removed"), true);
				}
				else
				{
					TArray<AnimMcpUpdateFunction::FAssignment> Assignments;
					FString Canonical;
					if (!AnimMcpUpdateFunction::ParseAndValidate(Blueprint, Context.Request.Params, Assignments, Canonical, OutError)) { return nullptr; }
					if (!AnimMcpUpdateFunction::Apply(Blueprint, Assignments, Canonical, Context, Applied, OutError)) { return nullptr; }
				}
				TSharedRef<FJsonObject> Result = BuildVariableResult(Blueprint, Context, bCompile, bSave);
				Result->SetObjectField(TEXT("applied"), Applied);
				return Result;
			});
	}
}
