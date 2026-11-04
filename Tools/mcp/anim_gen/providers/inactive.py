"""비활성 Provider 자리 — 매니페스트와 상태만 있고 실행은 NOT_IMPLEMENTED (구현이 없는 매니페스트 행의 기본값. blender 는 Phase 4 —
blender.py, local_ai 는 Phase 5 — local_ai.py, external.meshy 는 Phase 6 — meshy.py, control_rig 자리는 Phase 8-4b 에 body_fit 파이프 — body_fit.py)."""
from __future__ import annotations

from .base import Provider


class InactiveProvider(Provider):
    implemented = False
