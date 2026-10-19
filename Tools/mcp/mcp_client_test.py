"""MCP 종단 테스트 — Claude Code 가 하는 것과 같은 방식으로 server.py 를 stdio 로 띄워 Tool 을 호출한다.

    Tools/mcp/.venv/Scripts/python.exe Tools/mcp/mcp_client_test.py [asset_path]

통과 기준: initialize → list_tools 에 2개 이상 → get_editor_status ok → get_anim_blueprint_info ok.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

HERE = pathlib.Path(__file__).resolve().parent
PROJECT_DIR = HERE.parent.parent


def _payload(result) -> dict:
    if getattr(result, "structured_content", None):
        sc = result.structured_content
        # structured_output 래핑("result" 키)과 그대로 돌려주는 경우 둘 다 허용
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc.keys()) == {"result"} else sc
    for block in result.content or []:
        if getattr(block, "type", "") == "text":
            return json.loads(block.text)
    return {}


async def main(asset_path: str) -> int:
    params = StdioServerParameters(
        command=str(HERE / ".venv" / "Scripts" / "python.exe"),
        args=[str(HERE / "anim_graph_mcp" / "server.py")],
        cwd=str(PROJECT_DIR),
    )
    failures = 0
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"server: {init.server_info.name} {init.server_info.version}")

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            print(f"tools: {names}")
            if len(names) < 2:
                failures += 1

            status = _payload(await session.call_tool("get_editor_status"))
            print(f"get_editor_status ok={status.get('ok')} port={status.get('result', {}).get('port')}")
            if not status.get("ok"):
                failures += 1

            info = _payload(await session.call_tool("get_anim_blueprint_info", {"asset_path": asset_path}))
            r = info.get("result") or {}
            print(f"get_anim_blueprint_info ok={info.get('ok')} graphs={len(r.get('graphs', []))} "
                  f"variables={len(r.get('variables', []))} revision={r.get('revision')}")
            if not info.get("ok"):
                print(json.dumps(info.get("error"), ensure_ascii=False))
                failures += 1

    print("PASS" if failures == 0 else f"FAIL ({failures})")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "/Game/Animation/Hero/ABP_Hero_Base"
    sys.exit(asyncio.run(main(target)))
