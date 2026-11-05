"""StateTree MCP 서버 — stdio 전송. Claude Code 가 .mcp.json 으로 띄운다.

Tool 하나 = 에디터 플러그인 라우트 하나. 로직은 없고 anim_graph_mcp.bridge 를 공유한다.
설계: Docs/StateTree/DevelopmentGuide.md. 실행: Tools/mcp/.venv/Scripts/python.exe Tools/mcp/state_tree_mcp/server.py
"""
from __future__ import annotations

import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# mcp 2.x: FastMCP 가 MCPServer 로 개명됨 — requirements.txt 가 2.x 를 고정
from mcp.server.mcpserver import MCPServer  # noqa: E402

from anim_graph_mcp import bridge  # noqa: E402

# stdio 전송에서 stderr 로 새는 요청 로그를 줄인다
logging.getLogger("httpx").setLevel(logging.WARNING)

OPERATIONS_DOC = """
    Operations (state/node/target accept a GUID, a ref from this batch, or a name; duplicate names fail with AMBIGUOUS_NAME):
      add_state {ref?, parent? (default Root), name, type? (state|group), selection?, tag?, enabled?}
      remove_state {state, cascade?} - refused while transitions or bindings reference it, unless cascade
      set_state_properties {state, properties} - TasksCompletion, SelectionBehavior, Tag, bEnabled, CustomTickRate, Weight, RequiredEventToEnter
      add_task {ref?, state, type, values?}
      add_enter_condition {ref?, state, type, values?, operand?, indent?}
      add_evaluator {ref?, type, values?}
      add_global_task {ref?, type, values?}
      add_transition {ref?, state, trigger, target, event_tag?, priority?, delay?, conditions?}
          target = a state, or succeeded | failed | next_state | next_selectable_state
          conditions = [{ref?, type, values?, operand?, indent?}]
      remove_transition {state, transition}
      remove_node {node}
      set_node_values {node, values}
      bind_property {source: {struct, path}, target: {node, path}}
      unbind_property {target: {node, path}}
      bind_property_function {ref?, function, output?, target: {node, path}}
          creates a function node and binds its output to the target; bind its input with a later bind_property whose target.node is this ref

    'type' and 'function' are full paths from list_state_tree_node_types, e.g. /Script/GameplayStateTreeModule.StateTreeMoveToTask.
    'values' are looked up on the instance data first, then on the node struct (a distance condition's Operator lives there).
    source.struct = ref, GUID, node name, a context name (Actor, AIController) or "parameters"; an empty source.path means the struct itself.
    A ref must be defined by an earlier op, so add every state before the transitions between them.
    Binding a property the engine binding menu does not show fails with NOT_BINDABLE.
"""



def with_operations_doc(func):
    """mcp.tool() 이 등록 때 docstring 을 읽으므로 그보다 먼저 붙인다."""
    func.__doc__ = (func.__doc__ or "") + OPERATIONS_DOC
    return func


mcp = MCPServer(
    "state-tree-mcp",
    version="0.1.0",
    instructions=(
        "Author, inspect and compile Unreal Engine StateTree assets through the running editor. "
        "Flow: create_state_tree -> list_state_tree_node_types -> preview_state_tree_operations -> apply_state_tree_operations -> inspect_state_tree. "
        "Every tool returns an envelope {ok, tool, request_id, result, error, diagnostics}. "
        "If error.code is EDITOR_GONE the editor is not running or the AnimGraphMcp plugin is disabled; "
        "get_editor_status on anim-graph-mcp reports editor health and state_tree_edit_paths. "
        f"Bridge: {bridge.BASE_URL}"
    ),
)


@mcp.tool()
def create_state_tree(asset_path: str, schema_class: str | None = None, schema_properties: dict | None = None, save: bool = True) -> dict:
    """Create an empty StateTree (Root state only), compile it and save it. Never overwrites an existing asset.

    Args:
        asset_path: Content path inside [AnimGraphMcp] StateTreeEditPaths, e.g. "/Game/AI/ST_Enemy_Melee". Test assets go to /Game/AI/Test/.
        schema_class: Full class path. Default /Script/GameplayStateTreeModule.StateTreeAIComponentSchema.
        schema_properties: {"ContextActorClass": class path, "AIControllerClass": class path}. Without them the tree binds to Pawn and AAIController only.
        save: Save right after creating. With false the asset stays dirty, so apply_state_tree_operations refuses it (ASSET_DIRTY).

    Returns the same structure as inspect_state_tree.
    """
    params: dict = {"asset_path": asset_path, "save": save}
    if schema_class:
        params["schema_class"] = schema_class
    if schema_properties:
        params["schema_properties"] = schema_properties
    return bridge.call("create_state_tree", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def inspect_state_tree(asset_path: str) -> dict:
    """Read a StateTree: schema, context, parameters, state tree, nodes with values, transitions, bindings, revision and compile_state.

    Args:
        asset_path: Content path of the StateTree. Blueprint nodes are read too.

    compile_state is up_to_date, stale (edited since the last compile) or failed. Use revision as expected_revision when applying.
    """
    return bridge.call("inspect_state_tree", {"asset_path": asset_path})


@mcp.tool()
def list_state_tree_node_types(asset_path: str | None = None, schema_class: str | None = None, kind: str | None = None) -> dict:
    """List the node types a schema allows, with their properties.

    Args:
        asset_path: Use this asset's schema.
        schema_class: Or a schema class path. Default the AI schema.
        kind: task | condition | evaluator | property_function. Omit for all.

    Each property has name, type, usage (Input, Output, Context, Parameter) and bindable. Input properties must be bound or the compile fails;
    Context properties are bound automatically by type. Use the returned "type" in operations.
    """
    params: dict = {}
    if asset_path:
        params["asset_path"] = asset_path
    if schema_class:
        params["schema_class"] = schema_class
    if kind:
        params["kind"] = kind
    return bridge.call("list_state_tree_node_types", params)


@mcp.tool()
def list_state_tree_bindable_sources(asset_path: str, node: str) -> dict:
    """List what a node can bind to: the engine's GetBindableStructs for that node.

    Args:
        asset_path: Content path of the StateTree.
        node: GUID of the target node (from inspect_state_tree).

    Properties the engine binding menu does not show are left out and counted in hidden_properties.
    """
    return bridge.call("list_state_tree_bindable_sources", {"asset_path": asset_path, "node": node})


@mcp.tool()
@with_operations_doc
def preview_state_tree_operations(asset_path: str, operations: list[dict]) -> dict:
    """Validate a batch WITHOUT changing the asset. Stops at the first invalid op; later ops are marked skipped.

    A binding that involves a node created in the same batch reports deferred: ["scope"]. Its scope can only be judged once the node exists,
    so apply checks it right before binding. A valid preview therefore does not guarantee those bindings are in scope.
    """
    return bridge.call("preview_state_tree_operations", {"asset_path": asset_path, "operations": operations})


@mcp.tool()
@with_operations_doc
def apply_state_tree_operations(asset_path: str, operations: list[dict], expected_revision: str | None = None, compile: bool = True, save: bool = True) -> dict:
    """Apply a batch in one undoable transaction, compile and save.

    Any failure (invalid op, compile error, bindings silently removed by the compiler, save error) rolls the asset back. error.details then carries
    stage (preflight, apply, compile, fixups, save), messages, fixups and rollback {verified, method (none, undo, reload), undo_history_cleared,
    editor_reopened, revision}. A reload rollback clears the whole editor undo history and reopens open asset editors.

    Refused with ASSET_DIRTY while the asset has unsaved changes, PIE_ACTIVE during play and TRANSACTION_ACTIVE while another transaction is open.
    With save=false the asset stays dirty, so the next apply is refused until it is saved in the editor or reverted.

    Args:
        asset_path: Content path inside [AnimGraphMcp] StateTreeEditPaths.
        operations: The batch.
        expected_revision: Abort with REVISION_MISMATCH if the asset changed since it was inspected.
        compile: Compile after applying.
        save: Save after a successful compile.

    Returns revision_before, revision_after, compile_state, refs {ref: GUID}, compile {ok, messages, fixups}.
    """
    params: dict = {"asset_path": asset_path, "operations": operations, "compile": compile, "save": save}
    if expected_revision:
        params["expected_revision"] = expected_revision
    return bridge.call("apply_state_tree_operations", params, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def compile_state_tree(asset_path: str) -> dict:
    """Compile manually. Returns ok, messages and fixups (bindings or nodes the compiler silently removed).

    A failed compile clears the previous compiled data until the next successful compile. Nothing is saved.
    """
    return bridge.call("compile_state_tree", {"asset_path": asset_path}, timeout=bridge.COMPILE_TIMEOUT)


@mcp.tool()
def revert_state_tree(asset_path: str) -> dict:
    """Reload the asset from disk, dropping unsaved changes.

    This clears the WHOLE editor undo history (every asset, not just this one) and closes and reopens open asset editors.
    The result carries undo_history_cleared and editor_reopened. Ask the user first when they may be editing.
    """
    return bridge.call("revert_state_tree", {"asset_path": asset_path}, timeout=bridge.COMPILE_TIMEOUT)


if __name__ == "__main__":
    mcp.run()
