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
    transitions (from/to, crossfade, priority, automatic, rule_source = the rule tree this tool generated, rule_modified = edited by hand since,
    logic_type = "TLT_StandardBlend" | "TLT_Inertialization" | "TLT_Custom" — the transition's LogicType, settable via set_property).
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
        details: Load each returned asset and add a summary (slower; use a narrow path_prefix): BlendSpace → "blendspace"
            (axes, samples, aim_offset), AnimMontage → "montage" (slots, sections, skeleton_slot_groups), AnimSequence → "additive_type".
    """
    params = {"class": asset_class, "path_prefix": path_prefix, "limit": limit, "details": details}
    if skeleton:
        params["skeleton"] = skeleton
    return bridge.call("list_animation_assets", params, timeout=bridge.COMPILE_TIMEOUT if details else bridge.DEFAULT_TIMEOUT)


@mcp.tool()
def create_blendspace(asset_path: str, skeleton: str, dimensions: int, axes: list[dict], samples: list[dict] | None = None,
                      aim_offset: bool = False, preview_mesh: str | None = None, overwrite: bool = False, save: bool = False) -> dict:
    """Create a BlendSpace (dimensions=2) or BlendSpace1D (dimensions=1) asset with axes and samples — or an AimOffset.

    Args:
        asset_path: Where to create it, e.g. "/Game/Animation/Test/BS_McpTest". Never target a production asset.
        skeleton: Target skeleton asset path; every sample animation must be compatible with it.
        dimensions: 1 or 2.
        axes: One per dimension: {"name": "Speed", "min": 0, "max": 600, "grid": 4, "snap": false, "wrap": false}.
        samples: [{"animation": "/Game/.../AS_Walk", "value": [300]}] (1D) or "value": [x, y] (2D). Values must lie inside the
            axis range (the engine would otherwise silently expand the axis), positions must be unique, additive types must match.
        aim_offset: Create an AimOffsetBlendSpace (2D) / AimOffsetBlendSpace1D instead. Every sample must be a Mesh Space additive
            sequence (AAT_RotationOffsetMeshSpace; see list_animation_assets details=true → additive_type), ADDITIVE_TYPE otherwise.
        preview_mesh: Optional skeletal mesh for the preview viewport.
        overwrite: If true, an existing asset at asset_path is DELETED first (refused for protected assets). Ask the user first.
        save: Save the new asset to disk right away.

    Returns the asset summary (axes, samples, sample_count, grid_sample_count, aim_offset) plus created=true and saved. Use set_asset on an
    AnimGraphNode_BlendSpacePlayer (or AnimGraphNode_RotationOffsetBlendSpace for an AimOffset) to plug it into a graph.
    """
    params = {"asset_path": asset_path, "skeleton": skeleton, "dimensions": dimensions, "axes": axes,
              "samples": samples or [], "aim_offset": aim_offset, "overwrite": overwrite, "save": save}
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
      {"op": "set_layer_instance_class", "node": "<layer node guid>", "instance_class": "/Game/.../ABP_Provider"}   # (7-4) run an INTERFACE layer on another
          # Animation Blueprint's instance (Lyra: weapon layer providers); null = back to this blueprint's implementation. The class must
          # implement the node's interface, be skeleton-compatible and not be this blueprint (SELF_LAYER / NOT_IMPLEMENTING / SELF_CLASS /
          # INCOMPATIBLE / PINS_LINKED). Value parameter pins of layer nodes appear in optional_pins with custom=true: expose_pin + connect.
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
        layers: [{"name": "FullBody_Idle"}, {"name": "UpperBody_Additive", "group": "Body", "input_poses": ["InPose"]},
            {"name": "Aim", "input_poses": [{"name": "InPose", "inputs": [{"name": "AimYaw", "type": "float"}]}]}].
            Names must be unique valid identifiers (not "AnimGraph"). "group" sets the layer group (grouped layers share one
            instance). "input_poses" adds Input Pose nodes to the layer signature; an entry may carry "inputs" (value parameters,
            types as in add_blueprint_variable) — they become value pins on LinkedAnimLayer nodes of implementers (expose_pin) and
            output pins of the input pose node inside the layer graph. Change them later with set_layer_inputs.
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
def set_layer_inputs(asset_path: str, layer: str, inputs: list[dict], input_pose: str | None = None, compile: bool = True, save: bool = False,
                     conform_implementers: bool = True) -> dict:
    """Replace the value parameters of an animation layer (the Inputs of its input pose node).

    Args:
        asset_path: A layer interface asset, or an Animation Blueprint for one of its OWN layers. Interface implementation graphs
            inside an implementer are refused (NOT_EDITABLE) — edit the interface instead.
        layer: Layer (graph) name.
        inputs: The whole list, [{"name": "AimYaw", "type": "float"}, ...]; [] clears. Types as in add_blueprint_variable. Names are
            unique per blueprint and must not equal the input pose name.
        input_pose: Which input pose carries the parameters; required only when the layer has several (NO_INPUT_POSE when it has none —
            value parameters need an input pose node).
        compile: Compile afterwards (default true).
        save: Save after a successful compile.
        conform_implementers: For an interface (default true): load the Animation Blueprints that reference it, conform them to the
            new signature and compile → "implementers" [{asset_path, compile}]. They are left dirty (not saved).

    Same list = unchanged. Afterwards implementers see the parameters as optional value pins on their LinkedAnimLayer nodes
    (get_anim_graph_structure optional_pins with custom=true; show them with expose_pin, feed them with connect) and as output pins
    of the input pose node inside the layer graph.
    """
    params = {"asset_path": asset_path, "layer": layer, "inputs": inputs, "compile": compile, "save": save, "conform_implementers": conform_implementers}
    if input_pose:
        params["input_pose"] = input_pose
    return bridge.call("set_layer_inputs", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def add_anim_layers(asset_path: str, layers: list[dict], compile: bool = True, save: bool = False, conform_implementers: bool = True) -> dict:
    """Add layer graphs to an existing Animation Layer Interface (interface layers) or to an Animation Blueprint (its own layers).

    Args:
        asset_path: The layer interface or Animation Blueprint.
        layers: Same shape as create_anim_layer_interface: [{"name", "group"?, "input_poses"? ["Name" | {"name", "inputs"? [{"name", "type"}]}]}].
        compile: Compile afterwards (default true).
        save: Save after a successful compile.
        conform_implementers: Interface only (default true): referencing Animation Blueprints are loaded, conformed (they gain the new
            layer graphs with root + input poses) and compiled → "implementers".

    Names must not collide with existing graphs or implemented interface layers; nothing is added when any entry is invalid.
    Returns the blueprint info (layers[] now includes them) plus added[] and implementers[].
    """
    return bridge.call("add_anim_layers", {"asset_path": asset_path, "layers": layers, "compile": compile, "save": save, "conform_implementers": conform_implementers},
                       timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def remove_anim_layers(asset_path: str, layers: list[str], force: bool = False, compile: bool = True, save: bool = False,
                       conform_implementers: bool = True) -> dict:
    """Remove layer graphs from an Animation Layer Interface or an Animation Blueprint's own layers.

    Args:
        asset_path: The layer interface or Animation Blueprint (implementation graphs of an interface cannot be removed from the
            implementer — NOT_EDITABLE).
        layers: Layer names to remove.
        force: For an interface, referencing Animation Blueprints are inspected first: an implementation graph with nodes beyond
            root/input poses, or a LinkedAnimLayer node using the layer, is refused with LAYER_IN_USE_BY (details.usage[] names the
            asset and node) unless force=true — then those implementation contents are lost and such nodes fail to compile. Ask the user first.
        compile: Compile afterwards (default true).
        save: Save after a successful compile.
        conform_implementers: Interface only (default true): referencing Animation Blueprints are conformed (their graphs for the
            removed layers are dropped) and compiled → "implementers".

    Returns the blueprint info plus removed[], usage[] (what force overrode) and implementers[].
    """
    return bridge.call("remove_anim_layers", {"asset_path": asset_path, "layers": layers, "force": force, "compile": compile, "save": save,
                                              "conform_implementers": conform_implementers}, timeout=bridge.COMPILE_TIMEOUT)


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
def create_anim_montage(asset_path: str, animation: str, slot: str | None = None, blend_in: float | None = None, blend_out: float | None = None,
                        preview_mesh: str | None = None, overwrite: bool = False, save: bool = False) -> dict:
    """Create an AnimMontage from one AnimSequence: one slot track with one segment and a "Default" section at 0.

    Args:
        asset_path: Where to create it, e.g. "/Game/Animation/Test/AM_McpTest". Never target a production asset.
        animation: Source AnimSequence path; its skeleton becomes the montage skeleton and its length the montage length.
        slot: Slot track name (default DefaultSlot). Must already be registered in the skeleton (add_skeleton_slot), SLOT_NOT_IN_SKELETON otherwise.
        blend_in: Blend-in time in seconds (engine default when omitted).
        blend_out: Blend-out time in seconds (engine default when omitted).
        preview_mesh: Optional skeletal mesh for the preview viewport.
        overwrite: If true, an existing asset at asset_path is DELETED first (refused for protected assets). Ask the user first.
        save: Save the new asset to disk right away.

    Notifies are not created here (they are project specific — use the project's own notify pipeline). Returns the montage summary
    (slots, sections, length, skeleton_slot_groups) plus created=true and saved. Next: set_montage_sections for combo/loop sections.
    """
    params = {"asset_path": asset_path, "animation": animation, "overwrite": overwrite, "save": save}
    if slot:
        params["slot"] = slot
    if blend_in is not None:
        params["blend_in"] = blend_in
    if blend_out is not None:
        params["blend_out"] = blend_out
    if preview_mesh:
        params["preview_mesh"] = preview_mesh
    return bridge.call("create_anim_montage", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def set_montage_slots(asset_path: str, slots: list[dict | str], save: bool = False) -> dict:
    """Rename the slot tracks of an AnimMontage (e.g. move an attack montage from DefaultSlot to an UpperBody slot).

    Args:
        asset_path: The AnimMontage.
        slots: [{"index": 0, "slot": "UpperBody"}] — index defaults to the array position; a plain string entry is allowed.
        save: Save the montage afterwards.

    Every name must already be registered in the montage's skeleton (SLOT_NOT_IN_SKELETON — call add_skeleton_slot first; the error
    lists the skeleton's slot_groups). Duplicate track names are refused. Notifies and sections link by track index, so they survive the
    rename. Returns the montage summary plus changed (track count) / unchanged and saved.
    """
    return bridge.call("set_montage_slots", {"asset_path": asset_path, "slots": slots, "save": save}, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def set_montage_sections(asset_path: str, sections: list[dict], save: bool = False) -> dict:
    """Replace the section list of an AnimMontage (combo sections, loops, section chains).

    Args:
        asset_path: The AnimMontage.
        sections: [{"name": "Start", "start": 0.0, "next": "Loop"}, {"name": "Loop", "start": 0.4, "next": "Loop"}, {"name": "End", "start": 0.9}]
            — start in seconds inside [0, length]; next = the section played after this one (omit/null = stop at its end, its own
            name = loop). Names must be unique and next must name a section in this list.
        save: Save the montage afterwards.

    The whole list is replaced and sorted by start; notifies are untouched. Re-applying the same list is a no-op (unchanged=true).
    A first section that does not start at 0 is applied with a NO_SECTION_AT_ZERO warning. Returns the montage summary plus unchanged and saved.
    """
    return bridge.call("set_montage_sections", {"asset_path": asset_path, "sections": sections, "save": save}, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def add_skeleton_slot(skeleton: str, slot: str, group: str | None = None, confirm: bool = False, save: bool = False) -> dict:
    """Register a montage slot name on a Skeleton (what Slot nodes, set_montage_slots and create_anim_montage may use).

    Args:
        skeleton: The Skeleton asset path.
        slot: Slot name to register, e.g. "UpperBody".
        group: Slot group (default DefaultGroup; created when missing). A slot already in another group is moved.
        confirm: Must be true — this edits a shared asset that every animation for the skeleton depends on. Ask the user first.
        save: Save the skeleton afterwards (otherwise the registration is lost when the editor closes).

    Slot and group names share one namespace (SLOT_IS_GROUP / GROUP_IS_SLOT). Returns {slot, group, added, moved_from, group_created,
    unchanged, slot_groups[], saved}. get_anim_blueprint_info.skeleton_slot_groups shows the same list.
    """
    params = {"skeleton": skeleton, "slot": slot, "confirm": confirm, "save": save}
    if group:
        params["group"] = group
    return bridge.call("add_skeleton_slot", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def reassign_skeleton(skeleton: str, assets: list[str] | None = None, from_skeleton: str | None = None, path_prefix: str = "/Game",
                      confirm: bool = False, dry_run: bool = False, allow_missing_bones: bool = False,
                      convert_spaces: bool = False, save: bool = True) -> dict:
    """Move animation assets onto another Skeleton in place (the engine's "retarget to another skeleton" path: bone tracks are
    remapped by name, curve names copied to the target skeleton). Use it when the same character was imported twice and its
    animations ended up split across two skeletons with identical bones — an AnimBP can only reference assets of its own skeleton.

    Args:
        skeleton: Target Skeleton asset path.
        assets: Explicit animation asset paths (AnimSequence, AnimMontage, BlendSpace, AimOffset, AnimComposite). Either this
            or from_skeleton.
        from_skeleton: Collect every animation asset currently on this skeleton under path_prefix instead of listing them.
        path_prefix: Folder searched with from_skeleton (default /Game).
        confirm: Must be true to write — this rewrites assets on disk. Run with dry_run first and ask the user.
        dry_run: Only return the plan (planned[], skipped[], referred[]).
        allow_missing_bones: Proceed even when an AnimSequence has a bone track the target skeleton lacks (that track is dropped);
            otherwise such assets make the call fail with BONES_MISSING listing them.
        convert_spaces: Convert animation data in component space (only for skeletons with different reference poses).
        save: Save every changed asset, and the target skeleton if copying curves made it dirty (default true).

    Assets the listed ones reference (montage segments, BlendSpace samples, additive base poses) ALWAYS move along — the engine's
    ReplaceSkeleton does that itself — so check "referred" in the dry_run plan before confirming.

    Returns {skeleton, from_skeleton, total, referred[], planned[] (dry_run) | changed_assets[], referred_changed[], failed[],
    skipped[{asset, reason}], changed, saved, skeleton_saved}. Assets already on the target are skipped (already_on_target).
    """
    params: dict = {"skeleton": skeleton, "path_prefix": path_prefix, "confirm": confirm, "dry_run": dry_run,
                    "allow_missing_bones": allow_missing_bones, "convert_spaces": convert_spaces, "save": save}
    if assets:
        params["assets"] = assets
    if from_skeleton:
        params["from_skeleton"] = from_skeleton
    return bridge.call("reassign_skeleton", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def inspect_skeleton(skeleton: str | None = None, skeletal_mesh: str | None = None, details: bool = False,
                     compare_to: str | None = None) -> dict:
    """Read-only facts about a Skeleton for animation generation / IK retargeting (measured values only, nothing guessed).

    Args:
        skeleton: Skeleton asset path. Either this or skeletal_mesh (if both, the mesh must use this skeleton).
        skeletal_mesh: Skeletal mesh — its skeleton is inspected and it is the mesh used for template_match and mesh sockets.
        details: Add reference pose transforms per bone (ref_local / ref_component {t, r[pitch,yaw,roll], s?}) and socket transforms.
        compare_to: Another Skeleton to compare with. Rigs are judged by REFERENCE POSE, not bone names — a skeleton can share
            every bone name and still be 10-40 degrees off (UE4 mannequin vs UE5-style skeletons).

    Returns skeleton_path, meshes[], animation_count, bone_count, root_bone, bones[{name, parent}], virtual_bones[], mesh +
    mesh_source (argument | skeleton_preview | first_registered | none), sockets[{name, bone, owner, asset}], slot_groups[],
    curve_count, ik_rigs[{asset, preview_mesh}] and retargeters[{asset, source_rig, target_rig, roles}] (candidates for
    existing_rig / existing_retargeter), template_match{used, name, percent, matching_bones, missing_bones, pelvis, chains[]}
    (used=false means create_ik_rig auto mode will fail — define chains manually), and with compare_to: compare{common,
    missing_in_other[], only_in_other_count, ref_rot_diff_deg{p50, max, max_bone}, bone_length_ratio{p50, min, max},
    verdict same_rig | needs_ik_retarget | no_common_bones}. The verdict is reference info: generation always duplicates via
    retarget_animations, never reassign_skeleton.
    """
    params: dict = {"details": details}
    if skeleton:
        params["skeleton"] = skeleton
    if skeletal_mesh:
        params["skeletal_mesh"] = skeletal_mesh
    if compare_to:
        params["compare_to"] = compare_to
    return bridge.call("inspect_skeleton", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def import_animation_file(file: str, dest_path: str, skeleton: str | None = None, sample_rate: int = 0, name: str | None = None,
                          save: bool = False) -> dict:
    """Import an FBX through Interchange as a retarget source (BVH and other formats: convert with Blender first).

    Args:
        file: Absolute path under [AnimGraphMcp] ImportSourceRoots (get_editor_status.generation.import_source_roots) —
            anything else is IMPORT_SOURCE_NOT_ALLOWED.
        dest_path: Content folder under GenerationOutputPaths that must be EMPTY (ASSET_EXISTS reason DEST_NOT_EMPTY otherwise —
            names produced from an FBX cannot be checked beforehand, so nothing is ever replaced or renamed).
        skeleton: Import only the animations onto this existing Skeleton. Omit to create skeletal mesh + new skeleton + animations.
        sample_rate: Bake rate in Hz; 0 lets Interchange pick the best matching rate.
        name: Base asset name (default: the file name).
        save: Save the imported assets.

    A clip whose length is not on the bake rate's frame borders is snapped to the closest frames (warning LENGTH_SNAPPED
    {track}; the result length is animations[].length). Curve metadata on the skeleton, materials, textures, physics asset and static meshes are always off; the project's default
    pipeline stack is duplicated transiently. A package outside GenerationOutputPaths that becomes dirty fails the call with
    UNEXPECTED_DIRTY and nothing is saved. Returns imported[], animations[{asset, skeleton, frame_rate, frames, length}],
    skeleton, skeleton_created, mesh, source_frame_rate, pipelines[], seconds, saved.
    """
    params: dict = {"file": file, "dest_path": dest_path, "sample_rate": sample_rate, "save": save}
    if skeleton:
        params["skeleton"] = skeleton
    if name:
        params["name"] = name
    return bridge.call("import_animation_file", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def create_ik_rig(skeletal_mesh: str, asset_path: str | None = None, existing_rig: str | None = None, mode: str = "auto",
                  pelvis: str | None = None, chains: list[dict] | None = None, fbik: bool = True, save: bool = False) -> dict:
    """Create an IK Rig (retarget chains + pelvis, optional Full Body IK) for a skeletal mesh, the way the editor's
    auto-retarget does.

    Args:
        skeletal_mesh: The mesh the rig is for (always required — a skeleton can have dozens of meshes).
        asset_path: New asset under GenerationOutputPaths, e.g. "/Game/Animation/Generated/Vesper/IK_Vesper". Required unless existing_rig.
        existing_rig: Reuse this IK Rig instead (only checks the mesh is compatible; writes nothing).
        mode: "auto" — skeleton template characterization (works for UE4/UE5 mannequin-like skeletons). A mesh that matches no
            template fails with IKRIG_AUTO_FAILED and details.bones[{name, parent}] before anything is created; then propose
            chains from that hierarchy, confirm with the user, and call again with mode="manual".
            "manual" — pelvis + chains you give.
        pelvis: Retarget root bone (manual: required; auto: override).
        chains: manual only — [{"name": "Spine", "start": "spine_01", "end": "spine_05", "goal": null}, ...]. Use the target's
            chain names where they mean the same thing (create_ik_retargeter maps chains by exact name). Validated first
            (BONE_NOT_FOUND, END_NOT_BELOW_START, DUPLICATE_NAME/GOAL → BAD_REQUEST reason BAD_CHAINS, details.chains[]).
        fbik: auto: template Full Body IK; manual: a FullBodyIK solver on the pelvis connected to the goals you gave.
        save: Save the new rig.

    Returns asset_path, reused, mode, preview_mesh, template_match, pelvis, chains[], goals[], solvers[], saved.
    """
    params: dict = {"skeletal_mesh": skeletal_mesh, "mode": mode, "fbik": fbik, "save": save}
    if asset_path:
        params["asset_path"] = asset_path
    if existing_rig:
        params["existing_rig"] = existing_rig
    if pelvis:
        params["pelvis"] = pelvis
    if chains:
        params["chains"] = chains
    return bridge.call("create_ik_rig", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def create_ik_retargeter(source_rig: str, target_rig: str, source_mesh: str, target_mesh: str, asset_path: str | None = None,
                         existing_retargeter: str | None = None, ops: str = "default", auto_align: bool = False,
                         facing_yaw_deg: float = 0.0, save: bool = False) -> dict:
    """Create an IK Retargeter between two IK Rigs.

    Args:
        source_rig / target_rig: IK Rigs to copy animation FROM / TO.
        source_mesh / target_mesh: Meshes used for retargeting (required; each must be compatible with its rig).
        asset_path: New asset under GenerationOutputPaths. Required unless existing_retargeter.
        existing_retargeter: Reuse this retargeter (its rigs must be exactly source_rig/target_rig — RIG_MISMATCH otherwise).
        ops: "default" — engine default ops, every op's chains mapped by exact name. "match_existing" — the editor's
            auto-retarget recipe (exact FK mapping, target retarget pose auto-aligned, Run IK Rig off, root motion op configured,
            Pin Bones op with the template's pinned IK bones); the project's RTG_* assets were made this way.
        auto_align: default ops only — auto-align the target retarget pose to the source.
        facing_yaw_deg: Yaw (degrees about UE +Z) that turns the SOURCE's facing onto the TARGET's, e.g. source faces +X and
            target +Y → 90. FK chains copy global rotation deltas, so differently facing skeletons move in the wrong plane. Non-zero:
            the target root (bone 0) is turned by -yaw in the target retarget pose before auto-align, an Additive Pose op before the
            Root Motion op turns it back, and a root motion op copying the source root gets +yaw in GlobalOffset. Refused when the
            target root is the pelvis (FACING_NEEDS_ROOT).
        save: Save the new retargeter.

    Returns asset_path, reused, ops_recipe, ops[{name, type, enabled, parent}], chain_mapping{target: source|null},
    unmapped_target_chains[] (warning UNMAPPED_TARGET_CHAINS), pin_bones[], root_motion{}, retarget_poses{},
    facing_alignment{yaw_deg, target_root, restore_pose, op, op_index, enabled, consistent}|null (read from the asset; a reused
    retargeter whose yaw differs warns FACING_MISMATCH_EXISTING), saved.
    """
    params: dict = {"source_rig": source_rig, "target_rig": target_rig, "source_mesh": source_mesh, "target_mesh": target_mesh,
                    "ops": ops, "auto_align": auto_align, "save": save}
    if facing_yaw_deg:
        params["facing_yaw_deg"] = facing_yaw_deg
    if asset_path:
        params["asset_path"] = asset_path
    if existing_retargeter:
        params["existing_retargeter"] = existing_retargeter
    return bridge.call("create_ik_retargeter", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def retarget_animations(retargeter: str, assets: list[str], source_mesh: str, target_mesh: str, output_path: str,
                        name_rule: dict | None = None, include_referenced: bool = True, dry_run: bool = False,
                        validate: bool = True, thresholds: dict | None = None, save: bool = False) -> dict:
    """Duplicate animation assets onto another skeleton through an IK Retargeter (the engine batch "Duplicate and Retarget",
    with an explicit output folder). Sources are only read; results are new assets.

    Args:
        retargeter: IK Retargeter (create_ik_retargeter or an existing one).
        assets: AnimSequence / AnimMontage / BlendSpace (AimOffset) paths on the source mesh's skeleton. AnimBlueprints are
            refused (the engine would duplicate and recompile parent blueprints).
        source_mesh / target_mesh: Meshes to evaluate the source and build the target (required; compatible with the rigs).
        output_path: Folder under GenerationOutputPaths, e.g. "/Game/Animation/Generated/Vesper".
        name_rule: {"prefix", "suffix", "replace_from", "replace_to"} applied to each source name, e.g.
            {"replace_from": "Katana_", "replace_to": "AS_Vesper_Katana_"}.
        include_referenced: Montage segments and blend space samples come along (default true).
        dry_run: Only return planned[{source, asset, class, referenced}].
        validate: validate_animation of every generated sequence against its source (default true). FAILED → nothing saved,
            error VALIDATION_FAILED with details.partial.
        thresholds: validate_animation thresholds.
        save: Save the generated assets.

    Never overwrites: existing outputs → ASSET_EXISTS (details.problems), two outputs with the same name → BAD_REQUEST
    NAME_COLLISION_IN_BATCH, more planned assets (inputs + referenced) than get_editor_status.generation.max_retarget_assets_per_call
    → BAD_REQUEST LIMIT. The engine shows a progress dialog; cancelling it pops a delete confirmation — don't cancel during automation.
    Returns generated[], referred[], seconds, seconds_per_asset, frames, ms_per_frame, validation{status, assets[]}, saved.
    """
    params: dict = {"retargeter": retargeter, "assets": assets, "source_mesh": source_mesh, "target_mesh": target_mesh,
                    "output_path": output_path, "include_referenced": include_referenced, "dry_run": dry_run, "validate": validate,
                    "save": save}
    if name_rule:
        params["name_rule"] = name_rule
    if thresholds:
        params["thresholds"] = thresholds
    return bridge.call("retarget_animations", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def validate_animation(assets: list[str], sources: list[str | None] | None = None, skeleton: str | None = None,
                       checks: list[str] | None = None, thresholds: dict | None = None, feet: list[str] | None = None,
                       pelvis: str | None = None, source_feet: list[str] | None = None, source_pelvis: str | None = None,
                       expect: dict | None = None, seams: list[float] | None = None, profile_bones: list[str] | None = None,
                       profile_positions: bool = False) -> dict:
    """Measure AnimSequences (read-only): structure, obvious breakage, comparison with a source, and whether a request was met.

    Args:
        assets: AnimSequence paths.
        sources: Same order as assets (null to skip) — a source on ANOTHER skeleton gives retarget ratios (angular speed p99,
            planted-foot speed, root travel — size-corrected by pelvis height — length, loop boundary); a source on the SAME
            skeleton gives a per-bone rotation/position difference (regression comparison of two retargeters).
        skeleton: Expected skeleton (SKELETON_MISMATCH error otherwise).
        checks: Subset of "structural", "numeric", "relative" (default all).
        thresholds: Overrides — max_deg_per_frame (90), ang_speed_p99_ratio_min/max (0.5/2.0), foot_planted_ratio_max (3.0),
            root_travel_ratio_min/max (0.67/1.5), loop_boundary_ratio_max (3.0), foot_planted_height (3 cm), seam_ratio_max (3.0).
        feet / pelvis: Bones of the assets used for foot slide and size correction (default foot_l, foot_r / pelvis).
        source_feet / source_pelvis: The same for the sources.
        expect: Request checks for every asset — {length, length_tolerance (default one frame), loop, root_yaw_delta
            (degrees first→last, signed), root_yaw_tolerance (default 5)}. A mismatch is an EXPECT_* error (FAILED).
        seams: Times (seconds) where segments meet — a pose step over seam_ratio_max × the surrounding frames is SEAM_JUMP.
        profile_bones: Bones whose per-frame speed (cm/s) is returned in numeric.profile — use it to find strike windows.
        profile_positions: Also return numeric.profile.position_cm{bone: [[x, y, z]]} (component space, same times) — e.g. the
            plane a hand moves in, to compare a retarget with its source.

    Per asset: status PASSED | PASSED_WITH_WARNINGS | NEEDS_REVIEW | FAILED, structural[], numeric{}, relative{}, needs_review[]
    (always lists the visual check — passing checks is not motion quality). No absolute speed limits: normal attacks reach
    ~2,000°/s p99; only NaN, abnormal scale, missing track bones and a one-frame rotation over max_deg_per_frame fail.
    """
    params: dict = {"assets": assets}
    for key, value in (("sources", sources), ("skeleton", skeleton), ("checks", checks), ("thresholds", thresholds), ("feet", feet),
                       ("pelvis", pelvis), ("source_feet", source_feet), ("source_pelvis", source_pelvis), ("expect", expect),
                       ("seams", seams), ("profile_bones", profile_bones), ("profile_positions", profile_positions)):
        if value:
            params[key] = value
    return bridge.call("validate_animation", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def search_animations(query: str | None = None, skeleton: str | None = None, path_prefix: str = "/Game",
                      asset_class: str = "AnimSequence", min_length: float | None = None, max_length: float | None = None,
                      root_motion: bool | None = None, additive: bool | None = None, loop: bool | None = None,
                      tags: list[str] | None = None, limit: int = 50, details: bool = False, max_loads: int = 300) -> dict:
    """Search existing animations by metadata (read-only) — the first step of reusing a motion.

    Index = asset registry tags (no loading) + manual tags from [AnimGraphMcp] AnimationTagFiles
    (Config/AnimGraphMcp/AnimationTags.json: {"tags": {"<asset path or folder/>": ["tag", ...]}}).

    Args:
        query: Name tokens ("sickle attack") — split at '_', CamelCase and digit edges; each must equal or prefix a token of
            the asset name or its folders. Best matches first.
        skeleton: Only assets on this skeleton.
        path_prefix: Content folder (default /Game; market packs live under /Game/Assets).
        asset_class: AnimSequence (default) | AnimMontage | AnimComposite | all.
        min_length / max_length: Seconds.
        root_motion / additive: Registry flags.
        loop: bLoop is not a registry tag — candidates are loaded; more than max_loads is BAD_REQUEST LOAD_LIMIT.
        tags: Manual tags, all required.
        limit: Items returned (default 50).
        details: Load the returned assets — loop, notifies[{name, time, duration}], sync_markers, curves, root{displacement_cm,
            yaw_delta_deg}.
        max_loads: Load budget for loop/details (default 300).

    Returns total, returned, truncated, items[{asset_path, name, class, skeleton, length, frames, frame_rate, root_motion,
    additive_type, loop|null, tags[], score, matched[]}], loaded, tag_files[], query_tokens[].
    """
    params: dict = {"path_prefix": path_prefix, "class": asset_class, "limit": limit, "details": details, "max_loads": max_loads}
    for key, value in (("query", query), ("skeleton", skeleton), ("min_length", min_length), ("max_length", max_length),
                       ("root_motion", root_motion), ("additive", additive), ("loop", loop), ("tags", tags)):
        if value is not None:
            params[key] = value
    return bridge.call("search_animations", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def preview_animation_edits(source: str, operations: list[dict], asset_path: str | None = None, loop: bool | None = None,
                            root_motion: bool | None = None) -> dict:
    """Compute key edits of an AnimSequence in memory without creating anything — check ranges, lengths and seams first.

    Args:
        source: The AnimSequence to read (never modified).
        operations: Ordered edits — see below.
        asset_path: Optional output path to check (would_create{allowed, exists}).
        loop / root_motion: Override the result's bLoop / bEnableRootMotion (default: the source's).

    Returns valid, planned[{index, op, ok, error?, skipped?, range{start, end, start_key, end_key}, length_before, length_after,
    note?}], result{frame_rate, frames, length, bone_tracks, curves, root_yaw_delta_deg, root_displacement_cm, max_rate,
    notifies{kept, truncated, dropped[]}, sync_markers}, seams[{time, frame, step_ratio, jump}], limitations[].

    Operations (seconds on the timeline as it is before that op; start/end default to the whole clip; ranges snap to frames):
        trim {start?, end?} · retime {start?, end?, rate | duration} (rate 1.5 = 1.5x faster) · hold_pose {at, duration}
        · concat {asset? (same skeleton; default the original source), start?, end? (on that asset), reverse?, blend? (s),
          align_root? (true)} · mirror {axis? (x|y|z), mirror_table?} · offset_bone {targets[{bone, rotation?{pitch, yaw, roll},
          translation?[x, y, z]}], space? (component|local), start?, end?, blend_in? (0.2), blend_out? (0.2)}
        · rotate_root {yaw, start?, end?, ease? (smooth|linear)}.
    """
    params: dict = {"source": source, "operations": operations}
    for key, value in (("asset_path", asset_path), ("loop", loop), ("root_motion", root_motion)):
        if value is not None:
            params[key] = value
    return bridge.call("preview_animation_edits", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def apply_animation_edits(source: str, asset_path: str, operations: list[dict], loop: bool | None = None,
                          root_motion: bool | None = None, validate: bool = True, thresholds: dict | None = None,
                          save: bool = False) -> dict:
    """Create a NEW AnimSequence from key edits of an existing one (the source is only read).

    All operations are computed in memory first; any failure is BAD_REQUEST with details.planned and nothing is created.
    Then the source is duplicated to asset_path (must be under [AnimGraphMcp] GenerationOutputPaths and not exist), bone
    tracks and curves are rewritten, notifies/sync markers move with the timeline (trimmed or reversed parts drop theirs),
    and the result is validated (structure, one-frame rotation vs the sources × max playback rate, written length/loop/root
    yaw, seams). FAILED → VALIDATION_FAILED and nothing saved. A package outside the allow-list turning dirty → UNEXPECTED_DIRTY.

    Args:
        source: The AnimSequence to read.
        asset_path: The new asset (e.g. /Game/Animation/Generated/Vesper/AS_Vesper_Sickle_AttackVar).
        operations: Ordered edits — see below.
        loop / root_motion: Override bLoop / bEnableRootMotion (default: the source's).
        validate: Run the built-in validation (default true).
        thresholds: validate_animation thresholds (seam_ratio_max, max_deg_per_frame, …).
        save: Save the new asset (default false — it stays dirty).

    Operations (seconds on the timeline as it is before that op; start/end default to the whole clip; ranges snap to frames):
        trim {start?, end?} · retime {start?, end?, rate | duration} (rate 1.5 = 1.5x faster) · hold_pose {at, duration}
        · concat {asset? (same skeleton; default the original source), start?, end? (on that asset), reverse?, blend? (s),
          align_root? (true)} · mirror {axis? (x|y|z), mirror_table?} · offset_bone {targets[{bone, rotation?{pitch, yaw, roll},
          translation?[x, y, z]}], space? (component|local), start?, end?, blend_in? (0.2), blend_out? (0.2)}
        · rotate_root {yaw, start?, end?, ease? (smooth|linear)}.
    """
    params: dict = {"source": source, "asset_path": asset_path, "operations": operations, "validate": validate, "save": save}
    for key, value in (("loop", loop), ("root_motion", root_motion), ("thresholds", thresholds)):
        if value is not None:
            params[key] = value
    return bridge.call("apply_animation_edits", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def set_sequence_additive(asset_path: str, additive_type: str | None = None, ref_pose_type: str | None = None,
                          ref_pose_sequence: str | None = None, clear_ref_pose_sequence: bool = False,
                          ref_frame_index: int | None = None, save: bool = False) -> dict:
    """Set an AnimSequence's additive settings (the Details panel's "Additive Settings") — what makes a sequence usable as an
    AimOffset sample: additive_type RotationOffsetMeshSpace plus a base pose (ref_pose_type AnimFrame + ref_pose_sequence, or
    RefPose). create_blendspace(aim_offset=true) refuses samples whose base pose is missing (ADDITIVE_INVALID); fix them here first.

    Args:
        asset_path: The AnimSequence.
        additive_type: None | LocalSpaceBase | RotationOffsetMeshSpace (AAT_ prefix optional).
        ref_pose_type: None | RefPose | AnimScaled | AnimFrame | LocalAnimFrame (ABPT_ prefix optional).
        ref_pose_sequence: Base pose AnimSequence (must be on the same skeleton — SKELETON_MISMATCH otherwise).
        clear_ref_pose_sequence: Clear the base pose sequence instead.
        ref_frame_index: Frame of ref_pose_sequence used when ref_pose_type is AnimFrame.
        save: Save the sequence afterwards.

    Omitted fields keep their value; identical values report unchanged=true. Returns {additive_type, ref_pose_type,
    ref_pose_sequence, ref_frame_index, additive_valid, changed[], unchanged, saved, dirty}.
    """
    params: dict = {"asset_path": asset_path, "save": save}
    if additive_type is not None:
        params["additive_type"] = additive_type
    if ref_pose_type is not None:
        params["ref_pose_type"] = ref_pose_type
    if clear_ref_pose_sequence:
        params["ref_pose_sequence"] = None
    elif ref_pose_sequence is not None:
        params["ref_pose_sequence"] = ref_pose_sequence
    if ref_frame_index is not None:
        params["ref_frame_index"] = ref_frame_index
    return bridge.call("set_sequence_additive", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def run_automation_tests(filter: str, timeout: float = 120.0, dry_run: bool = False) -> dict:
    """Run Unreal Automation tests inside the running editor (the plugin drives FAutomationTestFramework directly — no
    Session Frontend). Use it to verify Animation Blueprints after editing: filter "AnimGraphMcp.Smoke" runs the structural
    smoke tests over every AnimBP under [AnimGraphMcp] SmokeTestPaths (compile errors, unconnected Output Pose, empty states,
    broken Save/UseCachedPose links, invalid linked layers) and every AnimMontage there (slots registered in the skeleton, a Slot
    node of that name in some AnimBP, valid section chain); the project's own tests (filter = its test path prefix) work the same way.

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
    """Progress and results of an automation job started by run_automation_tests or run_anim_scenario (same shape; "running" names
    the current test; a runtime scenario's test carries "observed")."""
    return bridge.call("poll_automation_tests", {"job_id": job_id})


@mcp.tool()
def run_anim_scenario(asset_path: str, mesh: str | None = None, map: str | None = None, set_variables: dict | None = None,
                      montage: str | None = None, wait_frames: int = 10, expect: dict | None = None, timeout: float = 120.0) -> dict:
    """Run an Animation Blueprint inside PIE and check what it actually does — the step after the structural smoke test
    ("does Speed=300 really take the state machine to Run?", "is the UpperBody slot active while the attack montage plays?").

    The plugin starts PIE (the current editor world, or `map`), spawns a SkeletalMeshActor with the AnimBP, sets variables on the
    anim instance, optionally plays a montage, waits `wait_frames` frames, reads every state machine's current state and slot
    activity, compares them with `expect`, then ends PIE. Variables set here only stick if nothing overwrites them each frame —
    a native AnimInstance that recomputes Speed from its pawn will win; use BP variables (add_blueprint_variable) for driven tests.

    Args:
        asset_path: The compiled Animation Blueprint.
        mesh: Skeletal mesh to spawn (default: the AnimBP's preview mesh, else the skeleton's). Must match the AnimBP skeleton.
        map: Map to run PIE in (default: the world currently open in the editor).
        set_variables: {name: value} applied to the anim instance right after spawn (BlueprintVisible or BP variables; bool/number/string).
        montage: AnimMontage to Montage_Play after spawn (needed for slots_active expectations).
        wait_frames: Frames to wait before observing (default 10).
        expect: {"state_machines": {"Locomotion": "Run"}, "slots_active": ["UpperBody"]} — machine, state and slot names are validated
                against the compiled class before PIE starts.
        timeout: Seconds for the whole scenario; on timeout the test is marked "timeout" and PIE is ended.

    Returns the automation job (never finished synchronously): poll_automation_tests(job_id) until done. The test entry has
    state passed|failed|timeout, errors[] (each mismatch), and observed{state_machines{name: {state, elapsed}}, slots{name: bool},
    montage_playing, montage_length, variables_applied, frames_waited}. Rejections (BAD_REQUEST details.reason): PIE_ACTIVE,
    NOT_COMPILED, NO_PREVIEW_MESH, SKELETON_MISMATCH, VARIABLE_NOT_FOUND, STATE_MACHINE_NOT_FOUND, STATE_NOT_FOUND, BAD_WAIT_FRAMES.
    """
    params: dict = {"asset_path": asset_path, "wait_frames": wait_frames, "timeout": timeout}
    if mesh:
        params["mesh"] = mesh
    if map:
        params["map"] = map
    if set_variables:
        params["set_variables"] = set_variables
    if montage:
        params["montage"] = montage
    if expect:
        params["expect"] = expect
    return bridge.call("run_anim_scenario", params, timeout=bridge.COMPILE_TIMEOUT)


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
