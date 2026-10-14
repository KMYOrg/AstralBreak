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


if __name__ == "__main__":
    mcp.run()
