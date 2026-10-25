#include "AnimMcpTools.h"

#include "Animation/AnimBlueprint.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpGeneration.h"
#include "Core/AnimMcpOperations.h"

namespace AnimMcpTools
{
	namespace
	{
		const TCHAR* OperationsDoc =
			TEXT("Operations: "
			     "add_node {ref?, graph?(guid; default root AnimGraph), class (e.g. AnimGraphNode_SequencePlayer), pos?[x,y], asset?, enum?(BlendListByEnum only), properties?{name:value}} | "
			     "add_node {ref?, graph?, class:\"K2Node_VariableGet\", variable:\"<BlueprintVisible property>\", pos?} (variable getter inside AnimGraph/state graphs; output pin = variable name, e.g. connect Speed -> BlendSpacePlayer.X) | "
			     "connect {from:{node|ref, pin}, to:{node|ref, pin}} | "
			     "disconnect {from:{node|ref, pin}, to?:{node|ref, pin}} (no 'to' = break all links of 'from') | "
			     "remove_node {node|ref} | "
			     "set_property {node|ref, property, value} (allow-listed properties only; see node 'properties' in get_anim_graph_structure; "
			     "LayeredBoneBlend.LayerSetup = [{BranchFilters:[{BoneName, BlendDepth}]}, ...] one entry per blend pose, bones checked against the target skeleton) | "
			     "set_asset {node|ref, asset} | "
			     "expose_pin {node|ref, property, visible?=true} (see node 'optional_pins') | "
			     "add_blend_pose {node|ref, entry?(enum element for BlendListByEnum)} | "
			     "add_state {ref?, sm:{node|ref}|graph, name?, pos?} | "
			     "add_transition {ref?, from:{node|ref}, to:{node|ref}, properties?, rule?} | "
			     "set_entry_state {sm:{node|ref}|graph, state:{node|ref}} | "
			     "set_transition_rule {node|ref, rule} (transition or conduit) where rule is a JSON tree of {var}|{not}|{and:[..]}|{or:[..]}|{compare:{op,left,right}}|{literal}|{call:{function,args}}|{automatic:true,trigger_time?} (automatic: transitions only) | "
			     "add_conduit {ref?, sm:{node|ref}|graph, name?, pos?, rule?} | "
			     "add_state_alias {ref?, sm|graph, name?, pos?, states:[{node|ref}] | global:true} (an alias that is a transition TARGET must alias exactly one state) | "
			     "set_alias_states {node|ref, states | global} | "
			     "rename_node {node|ref, name} (state, conduit, alias or state machine node). "
			     "'ref' names a node created by an earlier add_* in the same batch. add_node 'graph' also accepts {ref|node} of a state (its pose graph), "
			     "and node references accept {result_of: {ref|node}} = that state's Output Animation Pose node (pin 'Result').");
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
			             "Params: asset_path, operations[], expected_revision? (abort if the graph changed), compile? (default false), save? (default false; only if compile ok), "
			             "generation_guard? (default false; true = the AnimBP must be inside [AnimGraphMcp] GenerationOutputPaths and the global dirty-package diff is checked after compiling and before saving — UNEXPECTED_DIRTY; result guard{newly_dirty[]}). ")) + OperationsDoc,
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				AnimMcpGeneration::FWriteGuard Guard(Context.Request);
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				if (!Guard.CheckPath(AssetPath, TEXT("asset_path"), OutError)) { return nullptr; }
				UAnimBlueprint* Blueprint = AnimMcpAssetResolver::LoadAnimBlueprint(AssetPath, OutError);
				if (!Blueprint) { return nullptr; }

				TArray<AnimMcpOperations::FOperation> Ops;
				if (!AnimMcpOperations::ParseOperations(*Context.Request.Params, Ops, OutError)) { return nullptr; }

				const FString ExpectedRevision = Context.Request.GetOptionalString(TEXT("expected_revision"));
				const bool bCompile = Context.Request.GetOptionalBool(TEXT("compile"), false);
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);

				return AnimMcpOperations::Apply(Blueprint, Ops, ExpectedRevision, bCompile, bSave, Context, OutError, Guard.IsEnabled() ? &Guard : nullptr);
			});
	}
}
