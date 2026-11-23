"""영역 몫 — 컨셉에서 보이는 픽셀이 어느 루트 직계 영역의 것인가 (L-2 기본 전환 ④, 11-23 — 설계 §11).

접히는 위젯(시작 때 숨음 · flag 바인딩)의 빛 · 넘침이 늘 보이는 정적 판에 남던 문제의 공용 정의: layer 는 이 몫을 그 위젯 텍스처로 옮기고,
상태 검사(state_check.hidden_halo)는 그 위젯을 껐을 때 이 몫에 정적 판이 그린 것이 남았는지 본다 — 둘이 같은 정의를 써야 고침과 검사가 갈리지 않는다.
주인 = 상자 안이면 그 영역, 밖이면 가장 가까운 상자(layer.plan 이 판 조각의 영역을 정하던 규칙 그대로).
"""
from __future__ import annotations

import numpy as np

PLATE_PREFIX = "StaticPlate"          # stages/layer 와 같은 이름(돌려 쓰기 방지 — layer 가 이 모듈을 부른다)
OVERHANG_SUFFIX = "Overhang"
REACH = 96                            # 상자에서 이만큼(px) 안의 픽셀만 그 영역 몫(빛 · 넘침) — 더 먼 것은 별개의 그림
VISIBLE = 0.02


def region_widgets(spec: dict) -> list[dict]:
    """루트 직계 영역 — 정적 판 · 넘침 장식 Image 는 뺀다."""
    root = spec.get("root") or "Root"
    return [w for w in spec.get("widgets", []) if w.get("parent") == root and not w["id"].startswith(PLATE_PREFIX) and not w["id"].endswith(OVERHANG_SUFFIX)]


def _box(w: dict, boxes: dict | None):
    if boxes is not None:
        b = boxes.get(w["id"])
        return None if not b or b["w"] <= 0 or b["h"] <= 0 else [float(b[k]) for k in ("x", "y", "w", "h")]
    return [float(v) for v in w["bbox_intent"]] if w.get("bbox_intent") else None


def int_box(bb, W: int, H: int) -> tuple[int, int, int, int]:
    x0, y0 = int(np.floor(float(bb[0]))), int(np.floor(float(bb[1])))
    x1, y1 = int(np.ceil(float(bb[0]) + float(bb[2]))), int(np.ceil(float(bb[1]) + float(bb[3])))
    return max(0, x0), max(0, y0), min(W, x1), min(H, y1)


def owner_map(spec: dict, shape, boxes: list[dict] | None = None) -> tuple[list[dict], np.ndarray, np.ndarray]:
    """→ (영역 위젯 목록, 픽셀마다 영역 번호(-1 = 영역 없음), 그 영역 상자까지 거리 px). boxes = 렌더 상자(없으면 bbox_intent)."""
    import cv2
    H, W = shape
    geo = {b["id"]: b for b in boxes} if boxes is not None else None
    regs = [r for r in region_widgets(spec) if _box(r, geo) is not None]
    dist = np.full((H, W), np.inf, np.float32)
    owner = np.full((H, W), -1, np.int32)
    for k, r in enumerate(regs):
        x0, y0, x1, y1 = int_box(_box(r, geo), W, H)
        m = np.ones((H, W), np.uint8)
        m[y0:y1, x0:x1] = 0
        d = cv2.distanceTransform(m, cv2.DIST_L2, 3)
        sel = d < dist
        owner[sel] = k
        dist[sel] = d[sel]
    return regs, owner, dist


def collapsible(w: dict) -> str | None:
    """런타임에 접히는 위젯이면 이유(flag 바인딩 · 시작 때 숨음), 아니면 None."""
    if (w.get("binding") or {}).get("kind") == "flag":
        return "flag binding"
    if w.get("visibility") in ("collapsed", "hidden"):
        return f"starts {w['visibility']}"
    return None


def toggle_regions(spec: dict) -> list[dict]:
    """접히는 루트 직계 영역(자기가 접히는 것 — 조상은 루트뿐)."""
    return [r for r in region_widgets(spec) if collapsible(r)]


def claim(spec: dict, alpha, rid: str, boxes: list[dict] | None = None, omap=None) -> np.ndarray:
    """그 영역의 몫(캔버스 bool) — 보이는(알파 > VISIBLE) 픽셀 중 주인이 그 영역이고 상자에서 REACH 안."""
    regs, owner, dist = omap if omap is not None else owner_map(spec, alpha.shape, boxes)
    k = next((i for i, r in enumerate(regs) if r["id"] == rid), None)
    if k is None:
        return np.zeros(alpha.shape, bool)
    return (alpha > VISIBLE) & (owner == k) & (dist <= REACH)
