#include "AnimMcpTools.h"

#include "Animation/AnimBlueprint.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpGraphInspector.h"
#include "Core/AnimMcpGraphMutator.h"
#include "EdGraph/EdGraph.h"

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

		Dispatcher.RegisterTool(TEXT("get_anim_graph_structure"),
			TEXT("Nodes, pins and connections of one graph (default: root AnimGraph) plus sub-graphs to 'depth' (default 1, -1 = all). Params: asset_path, graph_guid?, depth?."),
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

				UEdGraph* Graph = nullptr;
				const FString GraphGuid = Context.Request.GetOptionalString(TEXT("graph_guid"));
				if (!GraphGuid.IsEmpty())
				{
					Graph = AnimMcpGraphMutator::FindGraph(Blueprint, GraphGuid, OutError);
				}
				else
				{
					Graph = AnimMcpGraphInspector::FindRootAnimGraph(Blueprint);
					if (!Graph)
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::GraphNotFound, TEXT("Blueprint has no root AnimGraph"));
					}
				}
				if (!Graph)
				{
					return nullptr;
				}

				const int32 Depth = static_cast<int32>(Context.Request.GetOptionalNumber(TEXT("depth"), 1.0));
				return AnimMcpGraphInspector::BuildGraphStructure(Blueprint, Graph, Depth, Context);
			});
	}
}
