#include "AnimMcpTools.h"

#include "Animation/AnimBlueprint.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpOperations.h"

namespace AnimMcpTools
{
	namespace
	{
		const TCHAR* OperationsDoc =
			TEXT("Operations: "
			     "add_node {ref?, graph?(guid; default root AnimGraph), class (e.g. AnimGraphNode_SequencePlayer), pos?[x,y], asset?, enum?(BlendListByEnum only), properties?{name:value}} | "
			     "connect {from:{node|ref, pin}, to:{node|ref, pin}} | "
			     "disconnect {from:{node|ref, pin}, to?:{node|ref, pin}} (no 'to' = break all links of 'from') | "
			     "remove_node {node|ref} | "
			     "set_property {node|ref, property, value} (allow-listed properties only; see node 'properties' in get_anim_graph_structure) | "
			     "set_asset {node|ref, asset} | "
			     "expose_pin {node|ref, property, visible?=true} (see node 'optional_pins') | "
			     "add_blend_pose {node|ref, entry?(enum element for BlendListByEnum)} | "
			     "add_state {ref?, sm:{node|ref}|graph, name?, pos?} | "
			     "add_transition {ref?, from:{node|ref}, to:{node|ref}, properties?, rule?} | "
			     "set_entry_state {sm:{node|ref}|graph, state:{node|ref}} | "
			     "set_transition_rule {node|ref, rule} where rule is a JSON tree of {var}|{not}|{and:[..]}|{or:[..]}|{compare:{op,left,right}}|{literal}|{call:{function,args}}|{automatic:true,trigger_time?}. "
			     "'ref' names a node created by an earlier add_node/add_state/add_transition in the same batch.");
	}

	void RegisterGraphTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("preview_graph_operations"),
			FString(TEXT("Validate a batch of graph operations WITHOUT changing the asset. Params: asset_path, operations[]. ")) + OperationsDoc,
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint) { return nullptr; }

				TArray<AnimMcpOperations::FOperation> Ops;
				if (!AnimMcpOperations::ParseOperations(*Context.Request.Params, Ops, OutError)) { return nullptr; }

				return AnimMcpOperations::Preview(Blueprint, Ops, Context);
			});

		Dispatcher.RegisterTool(TEXT("apply_graph_operations"),
			FString(TEXT("Apply a batch of graph operations inside one undoable transaction. All operations are validated first; a mid-batch failure is undone. "
			             "Params: asset_path, operations[], expected_revision? (abort if the graph changed), compile? (default false), save? (default false; only if compile ok). ")) + OperationsDoc,
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint) { return nullptr; }

				TArray<AnimMcpOperations::FOperation> Ops;
				if (!AnimMcpOperations::ParseOperations(*Context.Request.Params, Ops, OutError)) { return nullptr; }

				const FString ExpectedRevision = Context.Request.GetOptionalString(TEXT("expected_revision"));
				const bool bCompile = Context.Request.GetOptionalBool(TEXT("compile"), false);
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);

				return AnimMcpOperations::Apply(Blueprint, Ops, ExpectedRevision, bCompile, bSave, Context, OutError);
			});
	}
}
