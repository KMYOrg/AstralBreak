"""1b 후속 L 다음 — 외부 · 단색 입력 결함 고침: 판 글자 메우기는 원래 컨셉으로 판정(순서 무관) · 다른 글자 몫 빼기 · 다른 글자 상자는 메움 원천에서 빼기 ·
판만 투명한 글자는 판 중앙값 메움(길고 가는 선 · 판과 같은 구조물은 지킴) · 판 글자 자국에서 긴 선 빼기 · 글자 맞춤의 컨셉 대비 안전망."""
from __future__ import annotations

import numpy as np
from PIL import Image

from core import config
from gen import diagnose as dg
from stages import refine, style

CFG = config.load_pipeline()
P = 6


def _pad(x):
    return np.pad(x, ((P, P), (P, P), (0, 0)) if x.ndim == 3 else P, mode="edge")


def _ring_digit(m, x, y, w=18, h=26, t=4):
    m[y:y + h, x:x + t] = m[y:y + h, x + w - t:x + w] = m[y:y + t, x:x + w] = m[y + h - t:y + h, x:x + w] = True


def test_fill_judges_on_the_original_concept_so_order_does_not_leave_residue():
    """앞 글자(빛 여백으로 넓은 상자)의 메움이 뒤 글자 일부를 먹어도, 뒤 글자는 원래 컨셉으로 획을 찾아 전부 판으로 — 남은 발 끝 잔상 없음
    [실측 단색 R20261118_124503 '4.2' → '2/4' 의 '4' 발 12 px]."""
    h, w = 120, 160
    panel = np.array([40.0, 20.0, 45.0])
    col, a = np.tile(panel, (h, w, 1)), np.ones((h, w))
    top, low = np.zeros((h, w), bool), np.zeros((h, w), bool)
    for x in (40, 70, 100):
        _ring_digit(top, x, 15, 22, 34, 6)
    for x in (55, 80):
        _ring_digit(low, x, 70)
    low[93:96, 98:104] = True                                    # '4' 발 끝 — 앞 글자 상자 밖으로 나감
    col[top | low] = (235, 225, 200)
    ntp, ntap = _pad(np.tile(panel, (h, w, 1))), _pad(np.ones((h, w)))
    box_top, box_low = [30, 8, 100, 80], [50, 64, 58, 36]           # 위 상자가 아래 글자 윗부분과 겹침(발 끝은 안 겹침)
    orig = (col.copy(), a.copy())
    c2, a2 = col.copy(), a.copy()
    for box, oth in ((box_top, [box_low]), (box_low, [box_top])):
        r = refine._plate_item_fill(c2, a2, ntp, ntap, {"id": "T", "box": box, "glow": 0, "colors": [[235, 225, 200]]}, orig=orig, others=oth)
        assert r["used"]
    assert float(np.abs(c2[low] - panel).max()) < 12 and float(np.abs(c2[top] - panel).max()) < 12


def test_other_text_boxes_are_not_fill_sources_for_text_on_transparency():
    """투명 위 글자 상자 둘레에 이웃 글자 빛(불투명)이 있어도 메움은 투명 — 이웃 상자는 둘레 · 원천에서 뺀다 [실측 파티 '100' — 고리 알파 0.765 → 남색 상자]."""
    h, w = 120, 220
    col, a = np.zeros((h, w, 3)), np.zeros((h, w))
    me, nb = np.zeros((h, w), bool), np.zeros((h, w), bool)
    for x in (110, 135, 160):
        _ring_digit(me, x, 30)
    _ring_digit(nb, 30, 66, 150, 22, 5)                          # 아래 이웃 글자(넓음)
    for m in (me, nb):
        halo = dg._dilate(m, 7) & ~m
        col[halo], a[halo] = (25, 60, 90), 0.85
    col[me | nb], a[me | nb] = (235, 240, 245), 1.0
    ntp, ntap = _pad(np.zeros((h, w, 3))), _pad(np.zeros((h, w)))
    box_me, box_nb = [100, 22, 90, 42], [20, 56, 172, 44]
    c2, a2 = col.copy(), a.copy()
    r = refine._plate_item_fill(c2, a2, ntp, ntap, {"id": "Me", "box": box_me, "glow": 7, "colors": [[235, 240, 245]]}, orig=(col, a), others=[box_nb])
    assert r["used"]
    inside = np.zeros((h, w), bool)
    inside[24:56, 102:188] = True
    assert float(a2[inside].mean()) < 0.1


def test_text_on_plate_transparency_with_opaque_glow_ring_uses_plate_median_and_keeps_bar_line():
    """컨셉 둘레가 빛 · 아래 막대로 불투명(고리 알파 ≈ 1)이라도 판이 글자 자리를 투명하게 그렸으면 판 중앙값으로 비우고, 상자 밖으로 이어진 막대 윗선
    (판은 1 px 어긋나고 더 밝게)은 지킨다 [실측 파티 이름 — 둘레 메움이 HP 막대 초록으로 상자를 덮음]."""
    h, w = 110, 240
    col, a = np.zeros((h, w, 3)), np.zeros((h, w))
    g = np.zeros((h, w), bool)
    for x in (60, 85, 110, 135):
        _ring_digit(g, x, 30)
    halo = dg._dilate(g, 15) & ~g
    col[halo], a[halo] = (25, 60, 90), 1.0                       # 넓은 불투명 빛(분석 빛 크기 6 보다 넓음) — 아래 막대 윗선까지 이어짐
    col[g], a[g] = (235, 240, 245), 1.0
    bar = np.zeros((h, w), bool)
    bar[72:100, :] = True
    col[bar], a[bar] = (120, 230, 40), 1.0
    line = np.zeros((h, w), bool)
    line[70:72, :] = True
    col[line], a[line] = (190, 250, 240), 1.0
    nt, nta = np.zeros((h, w, 3)), np.zeros((h, w))
    nt[bar], nta[bar] = (120, 230, 40), 1.0
    nt[69:71, :], nta[69:71, :] = (230, 255, 250), 1.0           # 판의 윗선 — 1 px 위 · 더 밝게
    c2, a2 = col.copy(), a.copy()
    r = refine._plate_item_fill(c2, a2, _pad(nt), _pad(nta), {"id": "Name", "box": [50, 20, 118, 48], "glow": 6, "colors": [[235, 240, 245]]},
                                orig=(col, a))
    assert r["used"] and r["alpha_from"].startswith("text-free concept median")
    assert float(a2[g].max()) < 0.15
    assert float(a2[(dg._dilate(g, 9) & ~g) & ~dg._dilate(line, 2)].mean()) < 0.15
    assert float(a2[line].min()) > 0.9 and float(np.abs(c2[line] - (190, 250, 240)).max()) < 12      # 컨셉 윗선 그대로


def test_thin_lines_are_lines_not_bands_or_glyph_rings():
    h, w = 80, 200
    pm = np.zeros((h, w, 3))
    pm[40:42, :] = 200.0                                         # 가는 가로 선
    pm[50:75, :] = 150.0                                         # 넓은 띠(트랙)
    ring = np.zeros((h, w), bool)
    _ring_digit(ring, 90, 5, 20, 26)
    pm[ring] = 220.0
    m = refine._thin_lines(pm / 255.0 * 255.0, np.ones((h, w)), 30.0)
    assert m[40:42, 20:180].mean() > 0.9
    assert m[55:70, :].mean() < 0.05 and m[ring].mean() < 0.05


def test_notext_unused_includes_plate_median_fill(tmp_path):
    import json
    (tmp_path / "refine.json").write_text(json.dumps({"passes": [{"assets": [{"source_mode": "plate", "windows": [
        {"item": "A", "used": True, "alpha_from": "text-free concept median (glyph-sized) — x"},
        {"item": "B", "used": True, "alpha_from": "text-free concept — its transparent glyph holes from the concept neighbourhood"}]}]}]}), encoding="utf-8")
    assert dg.notext_unused(tmp_path) == {"A"}


def test_glyph_like_tells_band_from_glyphs():
    own = np.zeros((60, 200), bool)
    own[5:55, 5:195] = True
    band = np.zeros_like(own)
    band[5:30, 5:195] = True                                     # 상자 테두리까지 이어진 띠
    glyph = np.zeros_like(own)
    for x in (30, 70, 110):
        _ring_digit(glyph, x, 15, 20, 28, 4)                     # 상자 안에 뜬 획
    assert refine._glyph_like(band & own, own) < 0.1 and refine._glyph_like(glyph & own, own) > 0.9


def test_baked_glyphs_flags_text_left_in_the_texture():
    """텍스처가 컨셉 글자를 그대로 가지면(컨셉 획 마스크가 빔) E1 baked — 진단이 말없이 건너뛰던 자리 [controls_alpha R20261119_004119 '돌진 공격' 이중]."""
    h, w = 60, 200
    plate = np.tile(np.array([40.0, 130.0, 190.0]), (h, w, 1))
    concept = plate.copy()
    g = np.zeros((h, w), bool)
    for x in (40, 80, 120):
        _ring_digit(g, x, 15)
    concept[g] = (240, 238, 205)
    own = np.zeros((h, w), bool)
    own[8:52, 30:170] = True
    masks = {"own": own}
    assert dg.baked_glyphs(masks, concept, concept.copy(), plate)["kept_frac"] == 1.0      # 텍스처 = 컨셉(글자 남음)
    assert dg.baked_glyphs(masks, concept, plate.copy(), plate) is None                    # 텍스처가 글자를 지움
    assert dg.baked_glyphs(masks, concept, concept.copy(), None) is None                   # 판 없음 — 판정 안 함


def test_text_fit_skips_a_glyph_whose_concept_contrast_failed(tmp_path, monkeypatch):
    """진단 E6 unmeasured 와 같은 판정 — 컨셉 대비 < 10 이면 글자 맞춤이 그 측정으로 색 · 크기를 바꾸지 않는다 [실측 파티 '100' → 검정 · 52]."""
    spec = {"root": "Root", "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "T", "type": "TextBlock", "parent": "Root", "bbox_intent": [60, 30, 120, 50], "font": {"size": 40, "color": "#EDF2F4FF"},
         "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [60, 30], "size": [120, 50]},
         "text": {"source": "static", "value": "100"}}]}
    Image.new("RGB", (240, 120), (10, 10, 10)).save(tmp_path / "reference.png")
    Image.new("RGB", (240, 120), (10, 10, 10)).save(tmp_path / "render.png")
    m = np.zeros((120, 240), bool)
    m[40:70, 70:160] = True
    monkeypatch.setattr(dg, "run_text_masks", lambda *a, **k: {"T": {"concept": m, "render": m, "concept_cand": m, "concept_contrast": 0.5}})
    after, recs = style.text_fit(spec, tmp_path / "reference.png", tmp_path / "render.png", CFG, mode="size")
    rec = next(r for r in recs if r.get("widget") == "T")
    assert rec.get("concept_contrast") == 0.5 and "contrast" in rec.get("skipped", "")
    assert after["widgets"][1]["font"] == spec["widgets"][1]["font"]
