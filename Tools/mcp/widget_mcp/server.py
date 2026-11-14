"""Widget MCP 서버 — stdio 전송. 사람 · Claude 가 대화로 WidgetMcp 도구를 쓸 때의 창구 (설계 Docs/Design/ui-autogen-pipeline.md §2-1 · §6).

파이프라인(Tools/uigen)은 같은 브리지 엔드포인트를 HTTP 로 직접 부르고, 무인 LLM 단계에는 이 서버(UE 도구)를 주지 않는다.
Tool 하나 = 에디터 플러그인(WidgetMcp) 라우트 하나. 로직은 없고 공용 editor_bridge.bridge 를 쓴다.
실행: Tools/mcp/.venv/Scripts/python.exe Tools/mcp/widget_mcp/server.py
"""
from __future__ import annotations

import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from editor_bridge import bridge  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)

mcp = MCPServer(
    "widget-mcp",
    version="0.1.0",
    instructions=(
        "Build and check UMG Widget Blueprints from a spec (Tools/uigen spec shape) through the running editor. "
        "Flow: import_ui_textures -> create_widget_blueprint -> preview_widget_spec -> apply_widget_spec -> compile/render/export -> save_widget_run or discard_run_packages. "
        "Assets live only under [WidgetMcp] WidgetOutputPaths (/Game/_AutoGen/<run_id>/) and are never saved until save_widget_run. "
        "Every tool returns an envelope {ok, tool, request_id, result, error, diagnostics}; EDITOR_GONE means the editor or the EditorMcpCore/WidgetMcp plugins are down. "
        f"Bridge: {bridge.BASE_URL}"
    ),
)


def _call(tool: str, params: dict, slow: bool = False) -> dict:
    return bridge.call(tool, {k: v for k, v in params.items() if v is not None}, timeout=bridge.COMPILE_TIMEOUT if slow else bridge.DEFAULT_TIMEOUT)


@mcp.tool()
def import_ui_textures(dest_path: str, textures: list[dict]) -> dict:
    """Import PNGs as UI textures through Interchange into a run folder (not saved).

    Args:
        dest_path: Run folder, e.g. "/Game/_AutoGen/R20261114_153000_CombatHUD".
        textures: [{file, name, compression?, lod_group?, mip_gen?, never_stream?, srgb?}] — file under [WidgetMcp] WidgetImportSourceRoots
            (Tools/uigen/work/), name like "T_ult_frame", compression TC_EditorIcon (default) or TC_BC7.
    """
    return _call("import_ui_textures", {"dest_path": dest_path, "textures": textures}, slow=True)


@mcp.tool()
def create_widget_blueprint(asset_path: str, parent_class: str | None = None, root_id: str | None = None) -> dict:
    """Create an empty Widget Blueprint with a CanvasPanel root (not saved). Returns revision for apply_widget_spec.

    Args:
        asset_path: e.g. "/Game/_AutoGen/<run_id>/WBP_CombatHUD".
        parent_class: "/Script/AstralBreak.AstralCombatHUDWidget" (the stub — never the generated ViewBase). Default UserWidget.
        root_id: Root canvas name (default Root).
    """
    return _call("create_widget_blueprint", {"asset_path": asset_path, "parent_class": parent_class, "root_id": root_id}, slow=True)


@mcp.tool()
def preview_widget_spec(asset_path: str, spec: dict, assets: dict | None = None) -> dict:
    """Dry run of the reconciler: validate the target spec and list the ops; changes nothing.

    Args:
        asset_path: Widget Blueprint.
        spec: {root, widgets[], locked[]?} (normalize with Tools/uigen core.spec first for exact round trips).
        assets: {asset_id: texture path} for brush assets.
    """
    return _call("preview_widget_spec", {"asset_path": asset_path, "spec": spec, "assets": assets})


@mcp.tool()
def apply_widget_spec(asset_path: str, spec: dict, expected_revision: str, assets: dict | None = None, compile: bool = True) -> dict:
    """Make the Widget Blueprint equal to the spec in one atomic batch (copy -> apply -> verify -> swap). Never saves.

    Refused: stale expected_revision (REVISION_MISMATCH), removing/retyping widgets bound by the parent class (BINDING_REMOVAL/BINDING_TYPE),
    changing spec.locked widgets (LOCKED). On any failure the blueprint is unchanged.
    """
    return _call("apply_widget_spec", {"asset_path": asset_path, "spec": spec, "assets": assets, "expected_revision": expected_revision,
                                       "compile": compile}, slow=True)


@mcp.tool()
def apply_widget_patch(asset_path: str, patch: dict, assets: dict | None = None, locked: list[str] | None = None, compile: bool = True) -> dict:
    """Apply a spec patch {base_revision, ops[set|add_widget|remove_widget|move]} through the reconciler.

    binding changes and replace_asset are pipeline-only (PIPELINE_ONLY) — they need codegen / asset generation in Tools/uigen.
    """
    return _call("apply_widget_patch", {"asset_path": asset_path, "patch": patch, "assets": assets, "locked": locked, "compile": compile}, slow=True)


@mcp.tool()
def export_widget_spec(asset_path: str, assets: dict | None = None) -> dict:
    """Widget Blueprint -> spec + revision + unsupported[] + textures[] (settings) + bindings[] + GUID map check.

    Args:
        assets: {asset_id: texture path} — when given, brush textures come back as asset ids.
    """
    return _call("export_widget_spec", {"asset_path": asset_path, "assets": assets})


@mcp.tool()
def compile_widget_blueprint(asset_path: str) -> dict:
    """Compile; returns ok, messages and missing_bindings (required BindWidget absent or wrongly typed)."""
    return _call("compile_widget_blueprint", {"asset_path": asset_path}, slow=True)


@mcp.tool()
def list_bind_widgets(class_path: str | None = None, asset_path: str | None = None) -> dict:
    """BindWidget contract of a C++ class (/Script/<Module>.<Class>) or of a Widget Blueprint's parent class."""
    return _call("list_bind_widgets", {"class": class_path, "asset_path": asset_path})


@mcp.tool()
def render_widget(asset_path: str, output_dir: str, resolutions: list[list[int]] | None = None, force_visible: bool = False,
                  overrides: dict | None = None, probes: list[dict] | None = None, scale: float = 1.0, draws: int = 2, prefix: str = "render") -> dict:
    """Offscreen render to PNG (sRGB-corrected) + paint-space geometry of every widget from the same draw.

    Args:
        output_dir: New/empty folder under [WidgetMcp] WidgetRenderOutputRoots (Tools/uigen/work/...). Saved/ cannot be shown in chat.
        resolutions: [[1920,1080],[2560,1080],[1920,1200]] for the off-screen gate. Default [[1920,1080]].
        force_visible: Draw collapsed/hidden widgets too (layout checks).
        overrides: {widget: {visible?, percent?, text?}} — sample values.
        probes: [{id, at:[x,y]}] — corrected colour at a pixel (first resolution).
    """
    return _call("render_widget", {"asset_path": asset_path, "output_dir": output_dir, "resolutions": resolutions, "force_visible": force_visible,
                                   "overrides": overrides, "probes": probes, "scale": scale, "draws": draws, "prefix": prefix}, slow=True)


@mcp.tool()
def save_widget_run(run_path: str) -> dict:
    """Save every package under a run folder (/Game/_AutoGen/<run_id>) — finalize only."""
    return _call("save_widget_run", {"run_path": run_path}, slow=True)


@mcp.tool()
def discard_run_packages(run_path: str) -> dict:
    """Drop never-saved packages under a run folder (refuses if any are saved on disk)."""
    return _call("discard_run_packages", {"run_path": run_path}, slow=True)


if __name__ == "__main__":
    mcp.run()
