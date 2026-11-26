"""1b 후속 L — L-1 정답 = 사람이 승인한 그림(아트 모드는 원본 생성 아트일 때만) · L-3a 스페이서 겹침 · L-3b 투명 위 글자 / 판 투명 구멍 / 매끈한 메움 ·
L-3c 그림자 단일 측정."""
from __future__ import annotations

import json

import numpy as np

from core import geometry
from gen import diagnose as dg
from stages import normalize, refine


def test_art_mode_only_for_original_generated_art(tmp_path):
    """L-1 — 글자 든 컨셉(generated · external)은 아트 모드가 아니다(컨셉 픽셀 + 글자 자리만 판, 진단도 컨셉과). K 의 run(role 없음)도 L-1 길로."""
    assert not dg.art_mode({"art": {"used": True, "color": "a.png", "alpha": "b.png"}})            # K (가) 기록 — role 없음
    assert not dg.art_mode({"art": {"used": False, "role": "original"}})
    assert dg.art_mode({"art": {"used": True, "role": "original", "color": "a.png", "alpha": "b.png"}})
    # make_concept 출처 기록 — codex 새 그림 = generated(글자 든 컨셉), 편집 = external
    c = tmp_path / "concept.png"
    c.write_bytes(b"")
    (tmp_path / "concept.json").write_text(json.dumps({"kind": "concept", "generator": "codex image_gen"}), encoding="utf-8")
    assert normalize.concept_source({}, c)["value"] == "generated"
    assert normalize.concept_source({"concept_source": "external"}, c)["value"] == "external"


def test_overlap_gate_ignores_spacers():
    """L-3a — 스페이서는 그리지 않는 빈칸: 글자 상자가 걸쳐도 겹침이 아니다(위치 판이 세로 이동을 버리던 원인)."""
    rows = [{"id": "Row", "type": "HorizontalBox", "parent": "Root", "x": 0, "y": 0, "w": 200, "h": 100},
            {"id": "Gap", "type": "Spacer", "parent": "Row", "x": 100, "y": 0, "w": 28, "h": 94},
            {"id": "Count", "type": "TextBlock", "parent": "Row", "x": 96, "y": 0, "w": 41, "h": 87}]
    spec = {"widgets": [{"id": r["id"], "type": r["type"], "parent": r["parent"]} for r in rows]}
    out = geometry.overlaps(rows, spec, 0.04, [])
    assert out["violations"] == [] and out["skipped_spacer"] == 1
    rows[1]["type"] = "Image"
    assert geometry.overlaps(rows, spec, 0.04, [])["violations"]


def test_smooth_fill_has_no_row_streaks():
    """L-3b — 매끈한 메움은 줄마다 다른 양끝 원천을 잇지 않는다(줄 보간의 가로 줄무늬 없음)."""
    h, w = 60, 120
    pm = np.zeros((h, w, 3))
    a = np.zeros((h, w))
    pm[::2, :10] = 200.0                         # 왼쪽 원천이 줄마다 밝고 어둡다
    a[::2, :10] = 1.0
    hole = np.zeros((h, w), bool)
    hole[:, 30:90] = True
    fpm, fa = refine._smooth_fill(pm, a, ~hole)
    mid = fa[10:50, 55:65]
    assert float(np.abs(np.diff(mid, axis=0)).max()) < 0.05      # 줄마다 번갈아 바뀌지 않음


def _transparent_text(line_in_plate: bool):
    """투명 바탕 위 빛 글자 + 상자 아래를 지나는 가로 구조선(막대 윗선) — 판에도 선이 1 px 어긋나고 더 밝게 있다."""
    h, w = 90, 220
    col, a = np.zeros((h, w, 3)), np.zeros((h, w))
    glyph = np.zeros((h, w), bool)
    for gx in (60, 82, 104):
        glyph[30:50, gx:gx + 4] = glyph[30:50, gx + 14:gx + 18] = glyph[30:34, gx:gx + 18] = glyph[46:50, gx:gx + 18] = True
    halo = dg._dilate(glyph, 6) & ~glyph
    col[halo], a[halo] = (20, 55, 80), 1.0                                      # 파란 빛(컨셉 알파 1 — 변환 컨셉)
    col[glyph], a[glyph] = (220, 230, 235), 1.0
    line = np.zeros((h, w), bool)
    line[58:60, :] = True                                                       # 상자 아래쪽 안으로 들어오는 가로 선(상자 밖까지 이어짐)
    col[line], a[line] = (190, 220, 222), 1.0
    nt, nta = np.zeros((h, w, 3)), np.zeros((h, w))
    if line_in_plate:
        nt[59:61, :], nta[59:61, :] = (245, 248, 246), 1.0
    P = 6
    pad = lambda x: np.pad(x, ((P, P), (P, P), (0, 0)) if x.ndim == 3 else P, mode="edge")  # noqa: E731
    return col, a, pad(nt), pad(nta), glyph, halo, line


def test_text_on_transparency_clears_glow_but_keeps_structure_in_plate():
    """L-3b — 투명 바탕 위 글자는 판을 안 쓰고 상자를 비운다(빛 덩어리까지) — 단 판에도 있는 구조선은 지킨다."""
    col, a, ntp, ntap, glyph, halo, line = _transparent_text(True)
    c2, a2 = col.copy(), a.copy()
    r = refine._plate_item_fill(c2, a2, ntp, ntap, {"id": "T", "box": [48, 22, 92, 40], "glow": 6, "colors": [[220, 230, 235]]}, orig=(col, a))
    assert r["used"] and "transparent" in r["alpha_from"]
    assert a2[glyph].max() < 0.1 and float(a2[halo & ~dg._dilate(line, 2)].mean()) < 0.1     # 글자 · 빛 비움
    assert float(a2[line].mean()) > 0.9                                                       # 막대 윗선은 그대로


def test_plate_transparent_glyph_holes_come_from_neighbourhood():
    """L-3b — 판이 트랙 위 글자 자리를 투명하게 비웠으면 그 픽셀은 둘레 컨셉 메움(어두운 글자 모양 구멍 없음)."""
    h, w = 80, 200
    col = np.zeros((h, w, 3))
    col[...] = (40, 90, 130)
    a = np.ones((h, w))
    glyph = np.zeros((h, w), bool)
    glyph[30:50, 80:84] = glyph[30:50, 96:100] = glyph[30:34, 80:100] = glyph[46:50, 80:100] = True
    col[glyph] = (240, 200, 120)
    nt, nta = col.copy(), a.copy()
    nt[glyph] = (40, 90, 130)
    nta[dg._dilate(glyph, 2)] = 0.0                                              # 판은 글자 자리를 투명하게
    P = 6
    ntp, ntap = np.pad(nt, ((P, P), (P, P), (0, 0)), mode="edge"), np.pad(nta, P, mode="edge")
    c2, a2 = col.copy(), a.copy()
    r = refine._plate_item_fill(c2, a2, ntp, ntap, {"id": "T", "box": [70, 24, 40, 32], "glow": 0, "colors": [[240, 200, 120]]}, orig=(col, a))
    assert r["used"] and r.get("plate_clear_px", 0) > 0
    assert a2[glyph].min() > 0.8 and np.abs(c2[glyph] - np.array([40, 90, 130])).max() < 12


def test_shadow_measure_finds_one_sided_dark_offset_only():
    """L-3c — 그림자 = 한쪽(오프셋)만 바탕보다 어두움. 사방이 같은 외곽선 · 그림자 없는 글자는 '없음'."""
    h, w = 80, 160
    bg = np.full((h, w, 3), 120.0)
    st = np.zeros((h, w), bool)
    st[30:50, 40:46] = st[30:36, 40:110] = st[44:50, 70:76] = True
    img = bg.copy()
    sh = np.zeros_like(st)
    sh[32:52, 42:48] = sh[32:38, 42:112] = sh[46:52, 72:78] = True               # (2, 2) 그림자
    img[sh & ~st] = 30.0
    img[st] = 250.0
    m = dg.shadow_measure(img, bg, st)
    assert m["present"] and m["offset"] == [2, 2]
    plain = bg.copy()
    plain[st] = 250.0
    assert not dg.shadow_measure(plain, bg, st)["present"]
    ring = bg.copy()
    ring[dg._dilate(st, 3) & ~st] = 30.0                                         # 사방 외곽선
    ring[st] = 250.0
    assert not dg.shadow_measure(ring, bg, st)["present"]
