#include "AnimMcpTools.h"

#include "Animation/AnimBlueprint.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpGraphInspector.h"

namespace AnimMcpTools
{
	void RegisterInspectTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("get_anim_blueprint_info"),
			TEXT("Read-only summary of an Animation Blueprint: skeleton, parent class, graph tree (guids), BlueprintVisible variables, revision hash. Params: asset_path."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError))
				{
					return nullptr;
				}

				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint)
				{
					return nullptr;
				}

				return AnimMcpGraphInspector::BuildBlueprintInfo(Blueprint, Context);
			});
	}
}
