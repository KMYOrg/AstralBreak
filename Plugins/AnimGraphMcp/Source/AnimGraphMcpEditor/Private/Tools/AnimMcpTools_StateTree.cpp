#include "AnimMcpTools.h"

#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpStateTreeAsset.h"
#include "Core/AnimMcpStateTreeBindings.h"
#include "Core/AnimMcpStateTreeInspector.h"
#include "Core/AnimMcpStateTreeOperations.h"
#include "Misc/PackageName.h"
#include "StateTree.h"
#include "StateTreeEditorData.h"
#include "StateTreeSchema.h"

namespace AnimMcpTools
{
	namespace
	{
		const TCHAR* OperationsDoc =
			TEXT("Operations (state/node/target = GUID, a ref from this batch, or a name — duplicates fail with AMBIGUOUS_NAME): "
			     "add_state {ref?, parent? (default Root), name, type? (state|group), selection?, tag?, enabled?} | "
			     "remove_state {state, cascade?} (refused while transitions or bindings reference it, unless cascade) | "
			     "set_state_properties {state, properties} (TasksCompletion, SelectionBehavior, Tag, bEnabled, CustomTickRate, Weight, RequiredEventToEnter) | "
			     "add_task {ref?, state, type, values?} | "
			     "add_enter_condition {ref?, state, type, values?, operand?, indent?} | "
			     "add_evaluator {ref?, type, values?} | add_global_task {ref?, type, values?} | "
			     "add_transition {ref?, state, trigger, target (state or succeeded|failed|next_state|next_selectable_state), event_tag?, priority?, delay?, conditions? [{ref?, type, values?, operand?, indent?}]} | "
			     "remove_transition {state, transition} | remove_node {node} | set_node_values {node, values} | "
			     "bind_property {source:{struct, path}, target:{node, path}} | unbind_property {target:{node, path}} | "
			     "bind_property_function {ref?, function, output?, target:{node, path}} (the function's input is bound by a later bind_property whose target.node is this ref). "
			     "'type' and 'function' are full paths from list_state_tree_node_types. 'values' are looked up on the instance data first, then on the node struct (e.g. a distance condition's Operator). "
			     "source.struct = ref, GUID, node name, a context name (Actor, AIController) or 'parameters'; an empty source.path means the struct itself. "
			     "A ref must be defined by an earlier op, so add every state before transitions between them.");

		bool EnsureCanWrite(const FString& AssetPath, FAnimMcpError& OutError)
		{
			return AnimMcpStateTreeAsset::EnsureWritable(AssetPath, OutError)
				&& AnimMcpStateTreeAsset::EnsureNotInPie(OutError)
				&& AnimMcpStateTreeAsset::EnsureNoActiveTransaction(OutError);
		}

		const UStateTreeSchema* ResolveSchemaForListing(const FAnimMcpContext& Context, FAnimMcpError& OutError)
		{
			const FString AssetPath = Context.Request.GetOptionalString(TEXT("asset_path"));
			if (!AssetPath.IsEmpty())
			{
				const UStateTree* Tree = AnimMcpStateTreeAsset::Load(AssetPath, OutError);
				const UStateTreeEditorData* Data = AnimMcpStateTreeAsset::GetEditorData(Tree);
				return Data ? Data->Schema.Get() : nullptr;
			}
			const FString ClassPath = Context.Request.GetOptionalString(TEXT("schema_class"), AnimMcpStateTreeAsset::DefaultSchemaClass);
			const UClass* Class = ClassPath.StartsWith(TEXT("/")) && ClassPath.Contains(TEXT(".")) ? FindObject<UClass>(nullptr, *ClassPath) : nullptr;
			if (!Class || !Class->IsChildOf(UStateTreeSchema::StaticClass()) || Class->HasAnyClassFlags(CLASS_Abstract))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotFound, FString::Printf(TEXT("schema_class '%s' is not a concrete UStateTreeSchema"), *ClassPath));
				return nullptr;
			}
			return GetDefault<UStateTreeSchema>(const_cast<UClass*>(Class));
		}
	}

	void RegisterStateTreeTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("create_state_tree"),
			TEXT("Create an empty StateTree (Root state only), compile it and save it. Never overwrites. "
			     "Params: asset_path (inside [AnimGraphMcp] StateTreeEditPaths), schema_class? (default StateTreeAIComponentSchema), schema_properties? {ContextActorClass, AIControllerClass}, save? (default true)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError) || !AnimMcpStateTreeAsset::EnsureNotInPie(OutError))
				{
					return nullptr;
				}
				const FString SchemaClass = Context.Request.GetOptionalString(TEXT("schema_class"), AnimMcpStateTreeAsset::DefaultSchemaClass);
				const TSharedPtr<FJsonObject>* SchemaProperties = nullptr;
				Context.Request.Params->TryGetObjectField(TEXT("schema_properties"), SchemaProperties);
				const UStateTree* Tree = AnimMcpStateTreeAsset::Create(AssetPath, SchemaClass, SchemaProperties ? *SchemaProperties : nullptr, Context.Request.GetOptionalBool(TEXT("save"), true), OutError);
				return Tree ? TSharedPtr<FJsonObject>(AnimMcpStateTreeInspector::Inspect(*Tree)) : nullptr;
			});

		Dispatcher.RegisterTool(TEXT("inspect_state_tree"),
			TEXT("Read a StateTree: schema, context, parameters, state tree, nodes with values, transitions, bindings, revision, compile_state (up_to_date|stale|failed). Blueprint nodes are read too. Params: asset_path."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError))
				{
					return nullptr;
				}
				const UStateTree* Tree = AnimMcpStateTreeAsset::Load(AssetPath, OutError);
				return Tree ? TSharedPtr<FJsonObject>(AnimMcpStateTreeInspector::Inspect(*Tree)) : nullptr;
			});

		Dispatcher.RegisterTool(TEXT("list_state_tree_node_types"),
			TEXT("Node types a schema allows, with properties (name, type, usage Input|Output|Context|Parameter, bindable). "
			     "Params: asset_path? or schema_class? (default the AI schema), kind? (task|condition|evaluator|property_function)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				const UStateTreeSchema* Schema = ResolveSchemaForListing(Context, OutError);
				return Schema ? TSharedPtr<FJsonObject>(AnimMcpStateTreeInspector::ListNodeTypes(*Schema, Context.Request.GetOptionalString(TEXT("kind")))) : nullptr;
			});

		Dispatcher.RegisterTool(TEXT("list_state_tree_bindable_sources"),
			TEXT("What a node can bind to: GetBindableStructs for the target node, with the properties the engine binding menu shows (others are only counted in hidden_properties). Params: asset_path, node (GUID)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath, NodeText;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError) || !Context.Request.GetRequiredString(TEXT("node"), NodeText, OutError))
				{
					return nullptr;
				}
				const UStateTree* Tree = AnimMcpStateTreeAsset::Load(AssetPath, OutError);
				const UStateTreeEditorData* Data = AnimMcpStateTreeAsset::GetEditorData(Tree);
				if (!Data)
				{
					return nullptr;
				}
				FGuid NodeId;
				TInstancedStruct<FPropertyBindingBindableStructDescriptor> Desc;
				if (!FGuid::Parse(NodeText, NodeId) || !Data->GetBindableStructByID(NodeId, Desc))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::NodeNotFound, FString::Printf(TEXT("Node %s not found"), *NodeText));
					return nullptr;
				}
				return AnimMcpStateTreeBindings::ListSources(*Data, NodeId);
			});

		Dispatcher.RegisterTool(TEXT("preview_state_tree_operations"),
			FString(TEXT("Validate a batch WITHOUT changing the asset. Stops at the first invalid op (later ops are marked skipped). "
			             "A binding that involves a node created in the same batch reports deferred:[\"scope\"]: its scope can only be judged once the node exists, so apply checks it right before binding. Params: asset_path, operations[]. ")) + OperationsDoc,
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError))
				{
					return nullptr;
				}
				const UStateTree* Tree = AnimMcpStateTreeAsset::Load(AssetPath, OutError);
				TArray<AnimMcpStateTreeOperations::FOperation> Ops;
				if (!Tree || !AnimMcpStateTreeOperations::ParseOperations(*Context.Request.Params, Ops, OutError))
				{
					return nullptr;
				}
				return AnimMcpStateTreeOperations::Preview(*Tree, Ops);
			});

		Dispatcher.RegisterTool(TEXT("apply_state_tree_operations"),
			FString(TEXT("Apply a batch in one undoable transaction, compile and save. Any failure (invalid op, compile error, bindings silently removed by the compiler, save error) rolls the asset back; "
			             "the error details carry stage, messages, fixups and rollback {verified, method none|undo|reload, undo_history_cleared, editor_reopened, revision}. A reload rollback clears the whole editor undo history. "
			             "Refused while the asset has unsaved changes (ASSET_DIRTY), while PIE runs or while another transaction is open. With save=false the asset stays dirty, so the next apply is refused until it is saved in the editor or reverted. "
			             "Params: asset_path, operations[], expected_revision?, compile? (default true), save? (default true). ")) + OperationsDoc,
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError) || !EnsureCanWrite(AssetPath, OutError))
				{
					return nullptr;
				}
				UStateTree* Tree = AnimMcpStateTreeAsset::Load(AssetPath, OutError);
				TArray<AnimMcpStateTreeOperations::FOperation> Ops;
				if (!Tree || !AnimMcpStateTreeOperations::ParseOperations(*Context.Request.Params, Ops, OutError))
				{
					return nullptr;
				}
				return AnimMcpStateTreeOperations::Apply(*Tree, Ops,
					Context.Request.GetOptionalString(TEXT("expected_revision")),
					Context.Request.GetOptionalBool(TEXT("compile"), true),
					Context.Request.GetOptionalBool(TEXT("save"), true),
					Context, OutError);
			});

		Dispatcher.RegisterTool(TEXT("compile_state_tree"),
			TEXT("Compile manually. Returns ok, messages and fixups (bindings or nodes the compiler silently removed). A failed compile clears the previous compiled data until the next successful compile; nothing is saved. Params: asset_path."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError) || !EnsureCanWrite(AssetPath, OutError))
				{
					return nullptr;
				}
				UStateTree* Tree = AnimMcpStateTreeAsset::Load(AssetPath, OutError);
				if (!Tree || !AnimMcpStateTreeAsset::GetEditorData(Tree))
				{
					return nullptr;
				}
				const AnimMcpStateTreeAsset::FCompileResult Compiled = AnimMcpStateTreeAsset::Compile(*Tree);
				TSharedRef<FJsonObject> Result = Compiled.ToJson();
				Result->SetStringField(TEXT("revision"), AnimMcpStateTreeAsset::GetRevision(*Tree));
				Result->SetStringField(TEXT("compile_state"), AnimMcpStateTreeAsset::GetCompileState(*Tree));
				return Result;
			});

		Dispatcher.RegisterTool(TEXT("revert_state_tree"),
			TEXT("Reload the asset from disk, dropping unsaved changes. This clears the WHOLE editor undo history (all assets) and closes and reopens open asset editors — result carries undo_history_cleared and editor_reopened. Params: asset_path."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError) || !EnsureCanWrite(AssetPath, OutError))
				{
					return nullptr;
				}
				const FString Package = AnimMcpAssetResolver::ToPackagePath(AssetPath);
				if (!FPackageName::DoesPackageExist(Package))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetNotFound, FString::Printf(TEXT("'%s' has no file on disk to revert to"), *Package));
					return nullptr;
				}
				if (!AnimMcpStateTreeAsset::Load(AssetPath, OutError))
				{
					return nullptr;
				}
				const AnimMcpStateTreeAsset::FRollback Reloaded = AnimMcpStateTreeAsset::ReloadFromDisk(AnimMcpAssetResolver::NormalizeObjectPath(AssetPath), 0, /*bCheckHash*/ false);
				if (!Reloaded.bVerified)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("Reloading '%s' failed"), *Package), Reloaded.ToJson());
					return nullptr;
				}
				TSharedRef<FJsonObject> Result = Reloaded.ToJson();
				if (const UStateTree* Tree = FindObject<UStateTree>(nullptr, *AnimMcpAssetResolver::NormalizeObjectPath(AssetPath)))
				{
					Result->SetStringField(TEXT("compile_state"), AnimMcpStateTreeAsset::GetCompileState(*Tree));
				}
				return Result;
			});
	}
}
