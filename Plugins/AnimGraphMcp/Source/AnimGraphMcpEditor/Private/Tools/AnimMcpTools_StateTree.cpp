#include "AnimMcpTools.h"

#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpAutomationRunner.h"
#include "Core/AnimMcpStateTreeAsset.h"
#include "Core/AnimMcpStateTreeBindings.h"
#include "Core/AnimMcpStateTreeInspector.h"
#include "Core/AnimMcpStateTreeOperations.h"
#include "Core/AnimMcpStateTreeRuntime.h"
#include "Engine/Blueprint.h"
#include "GameFramework/Pawn.h"
#include "GameplayTagContainer.h"
#include "Misc/PackageName.h"
#include "StateTree.h"
#include "StateTreeEditorData.h"
#include "StateTreeSchema.h"

namespace AnimMcpTools
{
	namespace
	{
		const TCHAR* StateTreeOperationsDoc =
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

		/** BP 경로 · 클래스 경로 둘 다 받는다 */
		UClass* ResolvePawnClass(const FString& Path, FAnimMcpError& OutError)
		{
			UClass* Class = nullptr;
			if (Path.StartsWith(TEXT("/Script/")) || Path.EndsWith(TEXT("_C")))
			{
				Class = LoadObject<UClass>(nullptr, *Path);
			}
			else if (const UBlueprint* Blueprint = Cast<UBlueprint>(AnimMcpAssetResolver::LoadAssetOfClass(Path, UBlueprint::StaticClass(), OutError)))
			{
				Class = Blueprint->GeneratedClass;
			}
			else
			{
				return nullptr;
			}
			if (!Class || !Class->IsChildOf(APawn::StaticClass()) || Class->HasAnyClassFlags(CLASS_Abstract))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotFound, FString::Printf(TEXT("pawn_class '%s' is not a concrete APawn class"), *Path));
				return nullptr;
			}
			return Class;
		}

		/** 컴파일 산출물의 상태 이름으로 본다 — 오타를 PIE 를 띄우기 전에 잡는다 */
		bool EnsureStateExists(const UStateTree& Tree, const FString& Name, const TCHAR* Field, FAnimMcpError& OutError)
		{
			TArray<TSharedPtr<FJsonValue>> Names;
			for (const FCompactStateTreeState& State : Tree.GetStates())
			{
				if (State.Name.ToString() == Name)
				{
					return true;
				}
				Names.Add(MakeShared<FJsonValueString>(State.Name.ToString()));
			}
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), Field);
			Details->SetArrayField(TEXT("states"), Names);
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::StateNotFound, FString::Printf(TEXT("%s: state '%s' does not exist in '%s'"), Field, *Name, *Tree.GetName()), Details);
			return false;
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
			             "A binding that involves a node created in the same batch reports deferred:[\"scope\"]: its scope can only be judged once the node exists, so apply checks it right before binding. Params: asset_path, operations[]. ")) + StateTreeOperationsDoc,
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
			             "Params: asset_path, operations[], expected_revision?, compile? (default true), save? (default true). ")) + StateTreeOperationsDoc,
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

		// §6 — PIE 시나리오. 검증 · 정규화한 시나리오를 테스트 명령에 실어 잡 하나로 돌린다 (run_anim_scenario 와 같은 경로)
		Dispatcher.RegisterTool(TEXT("run_state_tree_scenario"),
			TEXT("Run a StateTree inside PIE and record what it actually does. The scenario starts PIE itself, observes the instance in the server world, sends events and ends PIE. "
			     "Params: asset_path (the tree the component references), map? (PIE map override), pawn_class? (BP or class path), spawn_location? [x,y,z] (spawns pawn_class at runtime; without it the instance must already be in the map and pawn_class only filters), "
			     "player_location? [x,y,z], events? [{tag, after? seconds, when_state?, expect_state?, expect_transition? (default true; false = the event must not cause a state change), window? seconds (default 2)}], "
			     "actions? [{kind (damage|unpossess|repossess|destroy|spawn_controller), after? seconds since the tree started or the previous action, when_state?, amount? (damage)}] — spawn_controller must come first and needs spawn_location, "
			     "expect_states? [names, in order], duration? (seconds of observation after the tree starts, default 30), start_timeout? (default 10), clients? (0 = standalone, N = listen server + N clients), timeout? (job seconds, default duration + 120). "
			     "Returns the automation job (never synchronous) — poll with poll_automation_tests(job_id). The test result carries observed {timeline[{t, active_states, run_status, state_changes, pawn_location}], events[{tag, sent, transitioned, state_changes, expect_state, reached_expected, expect_transition, ok, t_sent, t_transition, states_before, states_after}], actions[{kind, done, ok, detail?, t, states_before}], probe[{event (enter|exit), label, t, pawn, has_asc, avatar_is_pawn, pawn_ext_bound, abilities, try_ability?, ability_class_found?, activated?, status?}], expect{matched, ok}, worlds[{name, net_mode, observed, instances, pawns}], instance, started, finished_because, instance_gone_at?, pawn_start, pawn_end, pawn_travel, log[], candidates? (no instance found)}. "
			     "Without expect_states the scenario runs for the whole duration, or until the tree ends. With actions it does not end when the tree stops: it runs for the whole duration or until the instance is destroyed (finished_because instance_gone)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError) || !AnimMcpStateTreeAsset::EnsureNotInPie(OutError))
				{
					return nullptr;
				}
				const UStateTree* Tree = AnimMcpStateTreeAsset::Load(AssetPath, OutError);
				if (!Tree)
				{
					return nullptr;
				}
				if (!Tree->IsReadyToRun())
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::CompileFailed, FString::Printf(TEXT("'%s' has no compiled data to run — compile it first"), *Tree->GetName()));
					return nullptr;
				}
				const FString CompileState = AnimMcpStateTreeAsset::GetCompileState(*Tree);
				if (CompileState != TEXT("up_to_date"))
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("TREE_STALE"), FString::Printf(TEXT("compile_state is %s — PIE recompiles changed trees when it starts"), *CompileState));
				}

				AnimMcpStateTreeRuntime::FScenario Scenario;
				if (!AnimMcpStateTreeRuntime::ParseScenario(*Context.Request.Params, Scenario, OutError))
				{
					return nullptr;
				}
				Scenario.TreePath = Tree->GetPathName();
				if (!Scenario.PawnClass.IsEmpty())
				{
					const UClass* PawnClass = ResolvePawnClass(Scenario.PawnClass, OutError);
					if (!PawnClass)
					{
						return nullptr;
					}
					Scenario.PawnClass = PawnClass->GetPathName();
				}
				for (const FString& State : Scenario.ExpectStates)
				{
					if (!EnsureStateExists(*Tree, State, TEXT("expect_states"), OutError))
					{
						return nullptr;
					}
				}
				for (const AnimMcpStateTreeRuntime::FEventSpec& Event : Scenario.Events)
				{
					if (!FGameplayTag::RequestGameplayTag(FName(*Event.Tag), /*ErrorIfNotFound*/ false).IsValid())
					{
						TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
						Details->SetStringField(TEXT("reason"), TEXT("BAD_TAG"));
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Event tag '%s' is not a registered gameplay tag"), *Event.Tag), Details);
						return nullptr;
					}
					if ((!Event.WhenState.IsEmpty() && !EnsureStateExists(*Tree, Event.WhenState, TEXT("events.when_state"), OutError))
						|| (!Event.ExpectState.IsEmpty() && !EnsureStateExists(*Tree, Event.ExpectState, TEXT("events.expect_state"), OutError)))
					{
						return nullptr;
					}
				}
				for (const AnimMcpStateTreeRuntime::FActionSpec& Action : Scenario.Actions)
				{
					if (!Action.WhenState.IsEmpty() && !EnsureStateExists(*Tree, Action.WhenState, TEXT("actions.when_state"), OutError))
					{
						return nullptr;
					}
				}

				const TSharedRef<FJsonObject> ScenarioJson = AnimMcpStateTreeRuntime::ScenarioToJson(Scenario);
				const FString ScenarioText = AnimMcpJson::ToString(ScenarioJson);
				const FString Name = Tree->GetName();
				TArray<FAutomationTestInfo> Tests;
				Tests.Emplace(Name, FString::Printf(TEXT("%s.%s"), AnimMcpStateTreeRuntime::TestPath, *Name), AnimMcpStateTreeRuntime::MakeTestCommand(ScenarioText),
					EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter, /*NumParticipants*/ 1, ScenarioText);
				const double Timeout = Context.Request.GetOptionalNumber(TEXT("timeout"), Scenario.Duration + 120.0);
				TSharedPtr<AnimMcpAutomationRunner::FJob> Job = AnimMcpAutomationRunner::StartJobWithTests(FString::Printf(TEXT("run_state_tree_scenario %s"), *Name), MoveTemp(Tests), Timeout, OutError);
				if (!Job.IsValid())
				{
					return nullptr;
				}
				TSharedRef<FJsonObject> Result = AnimMcpAutomationRunner::DescribeJob(*Job);
				Result->SetObjectField(TEXT("scenario"), ScenarioJson);
				return Result;
			});
	}
}
