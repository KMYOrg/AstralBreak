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
        asset_path: Content path such as "/Game/Animation/Hero/ABP_Hero_Base" (with or without the ".Name" suffix).

    Returns target skeleton, parent class, graph tree with graph_guid values (use them with graph tools),
    BlueprintVisible variables usable in transition rules, linked anim layers, and a revision hash for change detection.
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
    toggle, with "bound" for property bindings that must be preserved) and "has_binding".
    """
    params = {"asset_path": asset_path, "depth": depth}
    if graph_guid:
        params["graph_guid"] = graph_guid
    return bridge.call("get_anim_graph_structure", params)


@mcp.tool()
def list_animation_assets(skeleton: str | None = None, asset_class: str = "all", path_prefix: str = "/Game", limit: int = 200) -> dict:
    """List animation assets (AnimSequence, BlendSpace, AnimMontage, AnimComposite) from the asset registry.

    Args:
        skeleton: Skeleton asset path; when given, only assets built for that skeleton are returned.
        asset_class: AnimSequence | BlendSpace | AnimMontage | AnimComposite | all.
        path_prefix: Content folder to search recursively.
        limit: Maximum number of entries to return.
    """
    params = {"class": asset_class, "path_prefix": path_prefix, "limit": limit}
    if skeleton:
        params["skeleton"] = skeleton
    return bridge.call("list_animation_assets", params)


@mcp.tool()
def create_animation_blueprint(asset_path: str, skeleton: str, parent_class: str = "/Script/Engine.AnimInstance",
                               preview_mesh: str | None = None, overwrite: bool = False) -> dict:
    """Create a new Animation Blueprint with an empty AnimGraph (only the Output Pose node).

    Args:
        asset_path: Where to create it, e.g. "/Game/Animation/Test/ABP_McpTest". Never target a production asset.
        skeleton: Target skeleton asset path.
        parent_class: AnimInstance subclass, e.g. "/Script/AstralBreak.AstralAnimInstance".
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
      {"op": "connect", "from": {"ref": "idle", "pin": "Pose"}, "to": {"node": "<root_node_guid>", "pin": "Result"}}
      {"op": "disconnect", "from": {"node": "<guid>", "pin": "Pose"}, "to": {...}}   # omit "to" to break every link of "from"
      {"op": "remove_node", "node": "<guid>"}                                         # not allowed for Output Pose / result / entry nodes
      {"op": "set_property", "node": "<guid>", "property": "PlayRate", "value": 1.5}   # allow-listed only; node "properties" lists them
      {"op": "set_property", "node": "<use_cached_pose_guid>", "property": "SaveCachedPoseNode", "value": {"ref": "save"}}
      {"op": "set_asset", "node": "<guid>", "asset": "/Game/.../AS_Other"}
      {"op": "expose_pin", "node": "<guid>", "property": "PlayRate", "visible": true}  # node "optional_pins" lists candidates
      {"op": "add_blend_pose", "node": "<layered_blend_guid>"}                        # BlendListByEnum needs "entry": "<enum element>"
    Supported node classes include SequencePlayer, BlendSpacePlayer, Slot, LayeredBoneBlend, BlendListByBool, BlendListByEnum,
    SaveCachedPose/UseCachedPose and StateMachine (creation only; states and transitions come in a later phase).
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


if __name__ == "__main__":
    mcp.run()
