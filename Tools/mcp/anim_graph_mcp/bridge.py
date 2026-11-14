"""호환 별칭 — 공용 브리지 클라이언트는 editor_bridge/bridge.py 로 옮겼다 (2026-11-14 플러그인 분리).

`from anim_graph_mcp import bridge` · `import anim_graph_mcp.bridge` 가 editor_bridge.bridge 모듈 객체 그 자체를 돌려주도록
sys.modules 를 바꿔 끼운다. 그래서 어느 이름으로 속성을 고치든(시험의 monkeypatch 등) 같은 모듈에 반영된다.
"""
from __future__ import annotations

import sys

from editor_bridge import bridge as _bridge

sys.modules[__name__] = _bridge
