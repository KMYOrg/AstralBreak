"""AnimGraph MCP 서버 — stdio 전송. Claude Code 가 .mcp.json 으로 띄운다.

Tool 하나 = 에디터 플러그인 라우트 하나. 입력 스키마는 함수 시그니처(pydantic)로 검증되고 그 외 로직은 없다.
실행: Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_graph_mcp/server.py
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# mcp 2.x: FastMCP 가 MCPServer 로 개명됨 (mcp.server.mcpserver). 1.x 와 호환하지 않는다 — requirements.txt 가 2.x 를 고정
from mcp.server.mcpserver import MCPServer  # noqa: E402

from anim_graph_mcp import bridge  # noqa: E402

# stdio 전송에서 stderr 로 새는 요청 로그를 줄인다 (stdout 은 MCP 프레임 전용이라 건드리지 않는다)
import logging  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)

mcp = MCPServer(
    "anim-graph-mcp",
    version="0.1.0",
    instructions=(
        "Inspect and edit Unreal Engine Animation Blueprints through the running editor. "
        "Every tool returns an envelope {ok, tool, request_id, result, error, diagnostics}. "
        "If error.code is EDITOR_GONE the editor is not running or the AnimGraphMcp plugin is disabled. "
        f"Bridge: {bridge.BASE_URL}"
    ),
)


@mcp.tool()
def get_editor_status() -> dict:
    """Editor/plugin health check: engine version, project, PIE state, related plugins, open asset editors, registered tools.

    Call this first in a session to confirm the editor bridge is reachable.
    """
    return bridge.call("get_editor_status")


@mcp.tool()
def get_anim_blueprint_info(asset_path: str) -> dict:
    """Read-only summary of an Animation Blueprint.

    Args:
        asset_path: Content path such as "/Game/Characters/Hero/ABP_Hero" (with or without the ".Name" suffix).

    Returns target skeleton, parent class, graph tree with graph_guid values (use them with graph tools),
    BlueprintVisible variables usable in transition rules, implemented_interfaces and layers (layer graphs with input_poses —
    interface layers and own layer graphs), linked anim layer nodes, and a revision hash for change detection.
    """
    return bridge.call("get_anim_blueprint_info", {"asset_path": asset_path})


@mcp.tool()
def get_anim_graph_structure(asset_path: str, graph_guid: str | None = None, depth: int = 1) -> dict:
    """Nodes, pins and connections of one graph of an Animation Blueprint.

    Args:
        asset_path: Content path of the Animation Blueprint.
        graph_guid: Graph to inspect (from get_anim_blueprint_info). Omit for the root AnimGraph.
        depth: How many levels of sub-graphs (state machines, states, transitions) to include. 0 = this graph only, -1 = all.

    Node identity is node_guid; pins are addressed by name. Use the returned revision as expected_revision when applying changes.
    Each node also carries "properties" (allow-listed values set_property can change), "optional_pins" (pins expose_pin can
    toggle; "bound" pins carry "binding" {path, path_text, type, context, promotion} — bind_pin/unbind_pin edit them) and "has_binding".
    "state_machines" lists every state machine graph in range: entry_state, states (name, bound_graph_guid, transitions in/out) and
    transitions (from/to, crossfade, priority, automatic, rule_source = the rule tree this tool generated, rule_modified = edited by hand since).
    """
    params = {"asset_path": asset_path, "depth": depth}
    if graph_guid:
        params["graph_guid"] = graph_guid
    return bridge.call("get_anim_graph_structure", params)


@mcp.tool()
def list_animation_assets(skeleton: str | None = None, asset_class: str = "all", path_prefix: str = "/Game", limit: int = 200,
                          details: bool = False) -> dict:
    """List animation assets (AnimSequence, BlendSpace, AnimMontage, AnimComposite) from the asset registry.

    Args:
        skeleton: Skeleton asset path; when given, only assets built for that skeleton are returned.
        asset_class: AnimSequence | BlendSpace | AnimMontage | AnimComposite | all.
        path_prefix: Content folder to search recursively.
        limit: Maximum number of entries to return.
        details: Load each returned BlendSpace and add its axes and samples under "blendspace" (slower; use with
            asset_class="BlendSpace" and a narrow path_prefix).
    """
    params = {"class": asset_class, "path_prefix": path_prefix, "limit": limit, "details": details}
    if skeleton:
        params["skeleton"] = skeleton
    return bridge.call("list_animation_assets", params, timeout=bridge.COMPILE_TIMEOUT if details else bridge.DEFAULT_TIMEOUT)


@mcp.tool()
def create_blendspace(asset_path: str, skeleton: str, dimensions: int, axes: list[dict], samples: list[dict] | None = None,
                      preview_mesh: str | None = None, overwrite: bool = False, save: bool = False) -> dict:
    """Create a BlendSpace (dimensions=2) or BlendSpace1D (dimensions=1) asset with axes and samples.

    Args:
        asset_path: Where to create it, e.g. "/Game/Animation/Test/BS_McpTest". Never target a production asset.
        skeleton: Target skeleton asset path; every sample animation must be compatible with it.
        dimensions: 1 or 2.
        axes: One per dimension: {"name": "Speed", "min": 0, "max": 600, "grid": 4, "snap": false, "wrap": false}.
        samples: [{"animation": "/Game/.../AS_Walk", "value": [300]}] (1D) or "value": [x, y] (2D). Values must lie inside the
            axis range (the engine would otherwise silently expand the axis), positions must be unique, additive types must match.
        preview_mesh: Optional skeletal mesh for the preview viewport.
        overwrite: If true, an existing asset at asset_path is DELETED first (refused for protected assets). Ask the user first.
        save: Save the new asset to disk right away.

    Returns the asset summary (axes, samples, sample_count, grid_sample_count) plus created=true and saved. Use set_asset on an
    AnimGraphNode_BlendSpacePlayer to plug it into a graph.
    """
    params = {"asset_path": asset_path, "skeleton": skeleton, "dimensions": dimensions, "axes": axes,
              "samples": samples or [], "overwrite": overwrite, "save": save}
    if preview_mesh:
        params["preview_mesh"] = preview_mesh
    return bridge.call("create_blendspace", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def create_animation_blueprint(asset_path: str, skeleton: str, parent_class: str = "/Script/Engine.AnimInstance",
                               preview_mesh: str | None = None, overwrite: bool = False) -> dict:
    """Create a new Animation Blueprint with an empty AnimGraph (only the Output Pose node).

    Args:
        asset_path: Where to create it, e.g. "/Game/Animation/Test/ABP_McpTest". Never target a production asset.
        skeleton: Target skeleton asset path.
        parent_class: AnimInstance subclass, e.g. "/Script/Engine.AnimInstance" or "/Script/MyGame.MyAnimInstance".
        preview_mesh: Optional skeletal mesh for the preview viewport.
        overwrite: If true, an existing asset at asset_path is DELETED first. Ask the user before using this.

    Returns the same summary as get_anim_blueprint_info plus created=true. The asset is not saved to disk yet.
    """
    params = {"asset_path": asset_path, "skeleton": skeleton, "parent_class": parent_class, "overwrite": overwrite}
    if preview_mesh:
        params["preview_mesh"] = preview_mesh
    return bridge.call("create_animation_blueprint", params)


_OPERATIONS_DOC = """
    Each operation is a dict. Nodes are addressed by {"node": "<guid>"} or {"ref": "<name>"} ('ref' = a node created by an
    earlier add_node in the same batch). Pins are addressed by name (see get_anim_graph_structure).
      {"op": "add_node", "ref": "idle", "graph": "<graph_guid or omit for root AnimGraph>",
       "class": "AnimGraphNode_SequencePlayer", "pos": [-400, 0], "asset": "/Game/.../AS_Idle",
       "properties": {"bLoopAnimation": true}, "enum": "/Script/Engine.EAlphaBlendOption" (BlendListByEnum only)}
      {"op": "add_node", "ref": "speed", "graph": "<state bound_graph_guid>", "class": "K2Node_VariableGet", "variable": "Speed", "pos": [-700, 100]}
          # variable getter (AnimInstance BlueprintVisible property) inside the AnimGraph or a state graph; output pin = variable name.
          # Then {"op": "connect", "from": {"ref": "speed", "pin": "Speed"}, "to": {"ref": "bs", "pin": "X"}} drives BlendSpacePlayer.X.
      {"op": "connect", "from": {"ref": "idle", "pin": "Pose"}, "to": {"node": "<root_node_guid>", "pin": "Result"}}
      {"op": "disconnect", "from": {"node": "<guid>", "pin": "Pose"}, "to": {...}}   # omit "to" to break every link of "from"
      {"op": "remove_node", "node": "<guid>"}                                         # not allowed for Output Pose / result / entry nodes
      {"op": "set_property", "node": "<guid>", "property": "PlayRate", "value": 1.5}   # allow-listed only; node "properties" lists them
      {"op": "set_property", "node": "<use_cached_pose_guid>", "property": "SaveCachedPoseNode", "value": {"ref": "save"}}
      {"op": "set_asset", "node": "<guid>", "asset": "/Game/.../AS_Other"}
      {"op": "expose_pin", "node": "<guid>", "property": "PlayRate", "visible": true}  # node "optional_pins" lists candidates
      {"op": "add_blend_pose", "node": "<layered_blend_guid>"}                        # BlendListByEnum needs "entry": "<enum element>"
      {"op": "set_property", "node": "<layered_blend_guid>", "property": "LayerSetup",
       "value": [{"BranchFilters": [{"BoneName": "spine_01", "BlendDepth": 0}]}]}    # one entry per blend pose (after add_blend_pose); bones must exist in the skeleton
    State machines (the StateMachine node's editor graph; see "state_machines" in get_anim_graph_structure):
      {"op": "add_state", "ref": "idle", "sm": {"ref": "sm"}, "name": "Idle", "pos": [0, 0]}      # or "graph": "<state machine graph guid>"
      {"op": "set_entry_state", "sm": {"ref": "sm"}, "state": {"ref": "idle"}}
      {"op": "add_transition", "ref": "t1", "from": {"ref": "idle"}, "to": {"ref": "run"},
       "properties": {"CrossfadeDuration": 0.2}, "rule": {"compare": {"op": ">", "left": {"var": "Speed"}, "right": {"literal": 10.0}}}}
      {"op": "set_transition_rule", "node": "<transition guid>", "rule": {"and": [{"var": "bIsFalling"}, {"not": {"var": "bIsOnGround"}}]}}
      {"op": "add_conduit", "ref": "sel", "sm": {"ref": "sm"}, "name": "JumpSelector", "rule": {"literal": true}}   # conduit: rule graph, no automatic
      {"op": "add_state_alias", "ref": "any", "sm": {"ref": "sm"}, "name": "JumpSources", "states": [{"ref": "idle"}, {"ref": "run"}]}
          # or "global": true. An alias used as a transition TARGET must alias exactly one state (engine compile rule).
      {"op": "set_alias_states", "node": "<alias guid>", "states": [{"ref": "idle"}]}
      {"op": "rename_node", "node": "<state|conduit|alias|state machine guid>", "name": "Locomotions"}
      {"op": "bind_pin", "node": "<blendspace player guid>", "property": "X", "path": ["Speed"]}     # property binding: the pin reads the
          # AnimInstance property (or BlueprintPure function, e.g. ["GetDeltaSeconds"]) directly, no VariableGet node. "path" may also be
          # "A.B". The pin is exposed if hidden; it must not be linked. Type promotion (float->double etc.) is allowed.
      {"op": "unbind_pin", "node": "<guid>", "property": "X"}                           # remove the binding (the pin stays exposed)
      {"op": "add_node", "ref": "layer", "class": "AnimGraphNode_LinkedAnimLayer", "layer": "FullBody_Idle", "pos": [-400, 0]}
          # Linked Anim Layer node (Lyra-style): "layer" must be a layer of an implemented layer interface (see
          # implement_anim_layer_interface / get_anim_blueprint_info.layers) or an own layer graph. Input pose pins follow the layer signature.
      {"op": "set_linked_layer", "node": "<layer node guid>", "layer": "UpperBody_Additive"}   # retarget an existing layer node
      {"op": "add_node", "ref": "idle_seq", "graph": {"ref": "idle"}, "class": "AnimGraphNode_SequencePlayer", "asset": "..."}   # graph = a state's pose graph, same batch ok
      {"op": "connect", "from": {"ref": "idle_seq", "pin": "Pose"}, "to": {"result_of": {"ref": "idle"}, "pin": "Result"}}      # result_of = that state's Output Animation Pose
    Rule trees: {"var": "<BlueprintVisible property>"} | {"not": R} | {"and": [R, R, ...]} | {"or": [R, R, ...]}
      | {"compare": {"op": ">|<|>=|<=|==|!=", "left": R, "right": R}} (one side may be {"literal": v}; real/int/int64 ordered, bool/name ==/!= only)
      | {"literal": true} | {"call": {"function": "GetCurveValue", "args": {"CurveName": {"literal": "Foo"}}}} (BlueprintPure + BlueprintThreadSafe,
      AnimInstance class chain or KismetMathLibrary) | {"automatic": true, "trigger_time": -1.0} (no graph; uses the asset player's remaining time)
      | {"access": "GetOwningComponent.ComponentVelocity"} (Property Access node: a property/pure-function path starting at the AnimInstance,
      resolved by the engine, thread-safety checked at compile; vectors/structs may flow into "call" args, e.g.
      {"call": {"function": "VSize", "args": {"A": {"access": "..."}}}}). {"param": "DeltaTime"} is only valid inside set_update_function.
    Variables: C++ BlueprintVisible properties and Blueprint variables added with add_blueprint_variable are both usable in rules, VariableGet, bind_pin.
    The rule graph is regenerated from the tree and the tree is stored in a comment node; re-applying the same tree is a no-op.
    Removing a state also removes its transitions, like the editor does.
    Supported node classes include SequencePlayer, BlendSpacePlayer, Slot, LayeredBoneBlend, BlendListByBool, BlendListByEnum,
    SaveCachedPose/UseCachedPose, StateMachine and K2Node_VariableGet (with "variable"). set_property also covers (allow-listed, see the
    node's "properties" in get_anim_graph_structure): RotationOffsetBlendSpace (AimOffset: X/Y/Alpha/sync group), SequenceEvaluator,
    SequencePlayer sync group (GroupName/GroupRole/Method), ApplyAdditive, TwoBoneIK, ModifyBone, Mirror, Inertialization, BlendList
    (BlendType/TransitionType/BlendProfile/CustomBlendCurve) and LayeredBoneBlend BlendMasks/CurveBlendOption. Values: bones as
    {"BoneName": "hand_r"} (validated against the skeleton), enums by name ("BCS_ComponentSpace", "BMM_Additive"), vectors/rotators as
    {"X","Y","Z"}/{"Pitch","Yaw","Roll"}, nested structs as objects ({"bUseSocket": false, "BoneReference": {"BoneName": "hand_l"}}),
    asset references as object paths (BlendProfile/BlendMask: get_anim_blueprint_info.skeleton_blend_profiles[].path; null clears). State internals (the state's bound graph,
    see state "bound_graph_guid") are edited with the ordinary ops via "graph"; its sink node is AnimGraphNode_StateResult with input pin "Result".
"""


@mcp.tool()
def preview_graph_operations(asset_path: str, operations: list[dict]) -> dict:
    """Validate a batch of graph operations without changing the asset. Always call this before apply_graph_operations.

    Args:
        asset_path: Animation Blueprint to plan against.
        operations: Ordered list of operations.
""" + _OPERATIONS_DOC
    return bridge.call("preview_graph_operations", {"asset_path": asset_path, "operations": operations})


@mcp.tool()
def apply_graph_operations(asset_path: str, operations: list[dict], expected_revision: str | None = None,
                           compile: bool = False, save: bool = False) -> dict:
    """Apply a batch of graph operations in one undoable transaction. Validated first; a mid-batch failure is rolled back.

    Args:
        asset_path: Animation Blueprint to modify.
        operations: Ordered list of operations (same format as preview_graph_operations).
        expected_revision: Revision from the last inspection; the call aborts with REVISION_MISMATCH if the graph changed.
        compile: Compile after applying and include the result.
        save: Save to disk after a successful compile (requires compile=true to be meaningful).

    Returns revision_before/after, refs (ref name -> node_guid), per-operation results, compile result and saved flag.
""" + _OPERATIONS_DOC
    params = {"asset_path": asset_path, "operations": operations, "compile": compile, "save": save}
    if expected_revision:
        params["expected_revision"] = expected_revision
    return bridge.call("apply_graph_operations", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def compile_animation_blueprint(asset_path: str, save_on_success: bool = False) -> dict:
    """Compile an Animation Blueprint. Errors and warnings come back with node_guid/graph_guid when they point at a node.

    Args:
        asset_path: Animation Blueprint to compile.
        save_on_success: Save the package when there are no errors.
    """
    return bridge.call("compile_animation_blueprint", {"asset_path": asset_path, "save_on_success": save_on_success},
                       timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def save_animation_blueprint(asset_path: str) -> dict:
    """Save an Animation Blueprint package to disk (forced, even if the editor does not consider it dirty)."""
    return bridge.call("save_animation_blueprint", {"asset_path": asset_path})


@mcp.tool()
def duplicate_animation_blueprint(source_path: str, dest_path: str, overwrite: bool = False,
                                  preserve_node_guids: bool = True, save: bool = False) -> dict:
    """Duplicate an Animation Blueprint to a new content path (e.g. to edit a copy of a production asset).

    Args:
        source_path: Existing Animation Blueprint.
        dest_path: New path, e.g. "/Game/Animation/Test/ABP_Copy". Must differ from source_path.
        overwrite: If true, an existing asset at dest_path is DELETED first. Refused (ASSET_PROTECTED) for assets listed in
            the project's [AnimGraphMcp] ProtectedAssets / ProtectedPaths. Ask the user before using this.
        preserve_node_guids: Keep every node_guid identical to the source (default). With false the engine assigns new guids.
        save: Save the duplicate to disk right away.

    Returns the same summary as get_anim_blueprint_info plus duplicated=true, source_path, source_revision, node_guids_preserved, saved.
    """
    return bridge.call("duplicate_animation_blueprint", {
        "source_path": source_path, "dest_path": dest_path, "overwrite": overwrite,
        "preserve_node_guids": preserve_node_guids, "save": save,
    }, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def delete_animation_blueprint(asset_path: str, confirm: bool = False, force: bool = False) -> dict:
    """Delete an Animation Blueprint asset. Destructive — always ask the user first and pass confirm=true.

    Args:
        asset_path: Animation Blueprint to delete (other asset classes are refused).
        confirm: Must be true; the call is refused otherwise.
        force: Required when other assets reference this one (error ASSET_REFERENCED lists them); their references become null.

    Protected assets ([AnimGraphMcp] ProtectedAssets / ProtectedPaths in DefaultEngine.ini) are refused with ASSET_PROTECTED.
    """
    return bridge.call("delete_animation_blueprint", {"asset_path": asset_path, "confirm": confirm, "force": force})


@mcp.tool()
def create_anim_layer_interface(asset_path: str, layers: list[dict], overwrite: bool = False, save: bool = False) -> dict:
    """Create an Animation Layer Interface asset (Lyra-style layer separation) with one layer graph per entry and compile it.

    Args:
        asset_path: Where to create it, e.g. "/Game/Animation/Test/ALI_McpTest". Never target a production asset.
        layers: [{"name": "FullBody_Idle"}, {"name": "UpperBody_Additive", "group": "Body", "input_poses": ["InPose"]}].
            Names must be unique valid identifiers (not "AnimGraph"). "group" sets the layer group (grouped layers share one
            instance). "input_poses" adds Input Pose nodes to the layer signature (pose inputs only, no value parameters).
        overwrite: If true, an existing asset at asset_path is DELETED first (refused for protected assets). Ask the user first.
        save: Save the new asset to disk right away.

    Returns the blueprint summary plus "layers" (name, graph_guid, group, input_poses), "compile" and created=true.
    Next: implement_anim_layer_interface on each Animation Blueprint that should implement it.
    """
    return bridge.call("create_anim_layer_interface", {"asset_path": asset_path, "layers": layers, "overwrite": overwrite, "save": save},
                       timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def implement_anim_layer_interface(asset_path: str, interface: str, compile: bool = True, save: bool = False) -> dict:
    """Make an Animation Blueprint implement an Animation Layer Interface. One layer graph per interface layer is added with its
    root and input pose nodes; edit them with apply_graph_operations via "layers"[].graph_guid, and place
    {"op": "add_node", "class": "AnimGraphNode_LinkedAnimLayer", "layer": "<name>"} in the AnimGraph to use a layer.

    Args:
        asset_path: The Animation Blueprint (not an interface).
        interface: The Animation Layer Interface asset path (must be compiled and expose at least one layer).
        compile: Compile after implementing (default true).
        save: Save after a successful compile.

    Refused when already implemented, when a graph of the same name exists, or when the interface has no layers.
    """
    return bridge.call("implement_anim_layer_interface", {"asset_path": asset_path, "interface": interface, "compile": compile, "save": save},
                       timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def add_blueprint_variable(asset_path: str, name: str, type: str, default: str | None = None, category: str | None = None,
                           instance_editable: bool = False, compile: bool = False, save: bool = False) -> dict:
    """Add a member variable to an Animation Blueprint, so rules ({"var"}), K2Node_VariableGet, bind_pin and set_update_function can use it
    without touching C++ (e.g. per-enemy flags such as bIsAttacking driven by set_update_function or by gameplay code).

    Args:
        asset_path: The Animation Blueprint.
        name: Variable name (must be unique in the class chain; validated like the editor).
        type: bool | float | int | int64 | name | string | text | byte | vector | vector2d | rotator | transform | linearcolor
              | object:<class path> | class:<class path> | struct:<struct path> | enum:<enum path>.
        default: Default value text ("true", "0.5", "(X=0,Y=0,Z=0)" ...). Omit for the type default.
        category: Editor category for the variable.
        instance_editable: Expose on instances (default false).
        compile: Compile afterwards (the skeleton class is regenerated either way, so the variable is usable immediately).
        save: Save the asset after a successful compile.

    Returns the blueprint info (variables[] now contains it with source="blueprint" and a "declaration") plus added and declaration.
    """
    params = {"asset_path": asset_path, "name": name, "type": type, "instance_editable": instance_editable, "compile": compile, "save": save}
    if default is not None:
        params["default"] = default
    if category:
        params["category"] = category
    return bridge.call("add_blueprint_variable", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def remove_blueprint_variable(asset_path: str, name: str, force: bool = False, compile: bool = False, save: bool = False) -> dict:
    """Remove a variable declared by this Animation Blueprint (C++ properties cannot be removed). If graph nodes reference it the call fails
    with VARIABLE_IN_USE unless force=true, which also deletes those nodes (a generated update function then reports modified=true —
    re-run set_update_function). Returns the blueprint info plus removed and was_used."""
    return bridge.call("remove_blueprint_variable", {"asset_path": asset_path, "name": name, "force": force, "compile": compile, "save": save}, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def set_update_function(asset_path: str, assignments: list[dict] | None = None, remove: bool = False, compile: bool = True, save: bool = False) -> dict:
    """Generate the Animation Blueprint's BlueprintThreadSafeUpdateAnimation override from a spec: a chain of variable assignments evaluated
    on the animation worker thread every update, before the graph. The whole function graph is regenerated from the spec (stored in a comment
    node like transition rules), re-applying the same spec is a no-op, and hand edits are detected (update_function.modified).

    Args:
        asset_path: The Animation Blueprint.
        assignments: [{"variable": "<name>", "value": <expression>}] in execution order. Expressions use the rule-tree grammar:
            {"access": "GetOwningComponent.ComponentVelocity"} (Property Access path), {"param": "DeltaTime"} (the function's input),
            {"var": "Speed"}, {"call": {"function": "VSize", "args": {"A": {...}}}}, {"compare": ...}, {"and"/"or"/"not": ...}, {"literal": v}.
            Variables must be BlueprintVisible and not BlueprintReadOnly: Blueprint variables from add_blueprint_variable, or C++ BlueprintReadWrite
            properties. Use [] to leave the function empty.
        remove: Delete the override graph instead.
        compile: Compile afterwards (default true) — a thread-unsafe call shows up as a compiler warning and disables multi-threaded update.
        save: Save after a successful compile.

    Returns the blueprint info (update_function {graph_guid, generated, source, modified, node_count, assignments}) plus applied
    {graph_guid, created_graph, unchanged, node_count, assignment_count} and compile/saved.
    """
    params = {"asset_path": asset_path, "compile": compile, "save": save}
    if remove:
        params["remove"] = True
    else:
        params["assignments"] = assignments or []
    return bridge.call("set_update_function", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def run_automation_tests(filter: str, timeout: float = 120.0, dry_run: bool = False) -> dict:
    """Run Unreal Automation tests inside the running editor (the plugin drives FAutomationTestFramework directly — no
    Session Frontend). Use it to verify Animation Blueprints after editing: filter "AnimGraphMcp.Smoke" runs the structural
    smoke test over every AnimBP under [AnimGraphMcp] SmokeTestPaths (compile errors, unconnected Output Pose, empty states,
    broken Save/UseCachedPose links, invalid linked layers); the project's own tests (filter = its test path prefix) work the same way.

    Args:
        filter: Test path prefix or substring (case-insensitive), e.g. "AnimGraphMcp.Smoke", "MyGame.Combat", "." for all.
        timeout: Seconds allowed per test (for tests with latent commands).
        dry_run: Only list the matching tests.

    Returns {job_id, total, completed, passed, failed, done, ok, tests[{name, state, duration, errors, warnings}]}. Tests without
    latent commands finish synchronously (done=true); otherwise call poll_automation_tests(job_id) until done.
    """
    return bridge.call("run_automation_tests", {"filter": filter, "timeout": timeout, "dry_run": dry_run}, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def poll_automation_tests(job_id: str) -> dict:
    """Progress and results of an automation job started by run_automation_tests (same shape; "running" names the current test)."""
    return bridge.call("poll_automation_tests", {"job_id": job_id})


@mcp.tool()
def quit_editor(save_dirty: bool = False, discard_dirty: bool = False) -> dict:
    """Ask the running editor to exit (PIE is ended first). The tool returns before the process ends; poll get_editor_status
    until it reports EDITOR_GONE (Tools/mcp/wait_for_exit.py does this).

    Args:
        save_dirty: Save dirty CONTENT packages before quitting (maps are never saved by this tool).
        discard_dirty: Quit even if unsaved packages remain (their changes are lost).

    With neither flag, unsaved packages make the call fail with DIRTY_PACKAGES (listing them) and the editor keeps running.
    Only use this on an editor you started for automation, never on the user's working editor without asking.
    """
    return bridge.call("quit_editor", {"save_dirty": save_dirty, "discard_dirty": discard_dirty}, timeout=bridge.COMPILE_TIMEOUT)


if __name__ == "__main__":
    mcp.run()
