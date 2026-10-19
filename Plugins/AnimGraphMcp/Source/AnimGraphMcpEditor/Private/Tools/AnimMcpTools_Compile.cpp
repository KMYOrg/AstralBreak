#include "AnimMcpTools.h"

#include "Animation/AnimBlueprint.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpCompiler.h"
#include "Core/AnimMcpGraphInspector.h"

namespace AnimMcpTools
{
	void RegisterCompileTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("compile_animation_blueprint"),
			TEXT("Compile an Animation Blueprint and return errors/warnings mapped to node guids. Params: asset_path, save_on_success? (default false)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint) { return nullptr; }

				TSharedRef<FJsonObject> Result = AnimMcpCompiler::Compile(Blueprint, Context);
				Result->SetStringField(TEXT("asset_path"), Blueprint->GetPathName());
				Result->SetStringField(TEXT("revision"), AnimMcpGraphInspector::ComputeRevision(Blueprint));

				bool bSaved = false;
				if (Context.Request.GetOptionalBool(TEXT("save_on_success"), false))
				{
					if (Result->GetBoolField(TEXT("ok")))
					{
						FAnimMcpError SaveError;
						bSaved = AnimMcpCompiler::Save(Blueprint, SaveError);
						if (!bSaved)
						{
							Context.AddDiagnostic(TEXT("error"), *SaveError.Code, SaveError.Message);
						}
					}
					else
					{
						Context.AddDiagnostic(TEXT("warning"), TEXT("SAVE_SKIPPED"), TEXT("Not saved because compile reported errors"));
					}
				}
				Result->SetBoolField(TEXT("saved"), bSaved);
				return Result;
			});
	}
}
