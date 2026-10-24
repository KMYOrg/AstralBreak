"""비활성 Provider 자리 — 매니페스트와 상태만 있고 실행은 NOT_IMPLEMENTED (Phase 6 · 8 에서 채운다. blender 는 Phase 4 — blender.py,
local_ai 는 Phase 5 — local_ai.py)."""
from __future__ import annotations

from .base import Provider


class InactiveProvider(Provider):
    implemented = False
