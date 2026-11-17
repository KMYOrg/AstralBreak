"""1b 후속 G — 따온 프레임에 컨셉 픽셀 옮겨 심기(gen/concept_pixels) · 모서리 장식선 지표 · 외형 라운드 교체 기준(style.replace_guard) ·
글자 위치 결정적 맞춤(style.text_fit)."""
from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image, ImageDraw

from core import color, config
from core.run import Run
from gen import concept_pixels as cp
from gen import fidelity
from stages import refine, style

CFG = config.load_pipeline()
GOLD, YELLOW, SCENE = (232, 181, 74), (255, 230, 0), (40, 30, 60)


def _concept_frame(ornaments=("tl",), text=True, inset: int = 10) -> np.ndarray:
    """300×150 — 장면 위 패널: 금테 3 px · 안쪽 위아래 빛(세로 단면) · 모서리 장식(테두리에 이어짐) · 가운데 금색 글자 막대.
    inset 0 = 패널이 상자를 꽉 채움(사각 패널)."""
    im = Image.new("RGB", (300, 150), SCENE)
    d = ImageDraw.Draw(im)
    for y in range(inset, 150 - inset):
        k = int(40 * max(0.0, 1 - (y - 13) / 20) + 40 * max(0.0, 1 - (136 - y) / 20))
        d.line([(inset, y), (299 - inset, y)], fill=(30 + k, 20 + k // 2, 15))
    for i in range(3):
        d.rectangle([inset + i, inset + i, 299 - inset - i, 149 - inset - i], outline=GOLD)
    corners = {"tl": ((13, 13), (40, 40), (13, 18, 44, 20)), "tr": ((286, 13), (259, 40), (255, 18, 286, 20)),
               "bl": ((13, 136), (40, 109), (13, 129, 44, 131)), "br": ((286, 136), (259, 109), (255, 129, 286, 131))}
    for c in ornaments:
        a, b, r = corners[c]
        d.line([a, b], fill=GOLD, width=3)
        d.rectangle(r, fill=GOLD)
    if text:
        for i in range(4):
            d.rectangle([124 + 16 * i, 60, 130 + 16 * i, 90], fill=GOLD)
    return np.asarray(im)


def _codex_texture(dx: int = 0, half: bool = False) -> Image.Image:
    """codex 따오기 흉내(2배): 같은 실루엣 · 노란 테두리 · 안쪽 한 색 · 모서리 장식 없음 · 글자 없음 · 바깥 투명."""
    im = Image.new("RGBA", (600, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x1 = 300 if half else 579
    d.rectangle([20 + 2 * dx, 20, x1 + 2 * dx, 279], fill=(40, 25, 20, 255))
    for i in range(6):
        d.rectangle([20 + 2 * dx + i, 20 + i, x1 + 2 * dx - i, 279 - i], outline=YELLOW + (255,))
    return im


def _L(rgb) -> float:
    return float(color.srgb_to_lab(np.asarray(rgb, float).reshape(1, 3))[0, 0])


def test_transplant_keeps_concept_colors_corners_and_interior_glow_without_the_text():
    out, rec = cp.transplant(_concept_frame(), _codex_texture(), texts=[{"id": "T", "box": [110, 50, 80, 50], "glow": 0}])
    assert out.size == (600, 300) and rec["silhouette_iou"] > 0.95 and rec["registration"]["shift_px"] == [0, 0]
    small = np.asarray(out.resize((300, 150), Image.Resampling.LANCZOS)).astype(float)
    gold = color.srgb_to_lab(np.array([GOLD], float))
    # 모서리 장식(codex 에는 없음)이 컨셉 자리 · 색으로, 알파 1
    assert small[27, 27, 3] > 250 and color.delta_e00(gold, color.srgb_to_lab(small[27:28, 27, :3]))[0] < 10
    # 테두리 색 = 컨셉 금색(codex 노랑 아님)
    assert color.delta_e00(gold, color.srgb_to_lab(small[11:12, 150, :3]))[0] < 8
    # 안쪽 위아래 빛(세로 단면)이 남는다 — 한 색 칠하기면 같은 값
    assert _L(small[16, 150, :3]) > _L(small[75, 60, :3]) + 10 and _L(small[133, 150, :3]) > _L(small[75, 60, :3]) + 10
    # 글자 막대는 메워져 이웃 줄 색과 같다 · 안쪽 알파 0.9 · 바깥 투명
    assert abs(_L(small[75, 127, :3]) - _L(small[75, 100, :3])) < 4 and abs(small[75, 60, 3] - 229.5) < 3 and small[3, 3, 3] == 0
    t = rec["texts"][0]
    assert t["widget"] == "T" and t["ink_box"][0] == 124 and t["hole_px"] > 0


def test_text_holes_leave_a_dull_border_line_inside_a_panel_wide_text_box():
    """[실측 G 끝 run 2] 체인 패널 오른쪽 테두리 가운데는 채도 낮은 연보라 선 — 장식선 판정 밖이라 패널 폭 글자 상자의 획으로 잡혀 메워졌다."""
    c = _concept_frame(text=True).copy()
    c[40:110, 286:290] = (30, 20, 15)                                                         # 오른쪽 가운데는 금테 대신
    for y0 in range(40, 110, 20):
        c[y0:y0 + 12, 287:289] = (170, 140, 165)                                              # 연보라 선 조각
    sil = np.zeros((150, 300), bool)
    sil[10:140, 10:290] = True
    edge = max(2.0, cp.EDGE_FRAC * 130)
    texts = [{"id": "Wide", "box": [10, 50, 280, 50], "glow": 0}]                            # 패널 폭 상자
    hole, recs = cp.text_holes(c, texts, cp.frame_lines(c, sil, edge), ring=cp.edge_ring(sil, edge))
    assert not hole[40:110, 286:290].any() and hole[75, 127] and recs[0]["border_pieces_dropped"] >= 1
    hole0, _ = cp.text_holes(c, texts, cp.frame_lines(c, sil, edge))                         # 띠 없이(예전)는 선 조각까지 구멍
    assert hole0[40:110, 286:290].any()


def test_transplant_registers_a_shifted_extraction_and_refuses_a_wrong_silhouette():
    out, rec = cp.transplant(_concept_frame(text=False), _codex_texture(dx=3))
    assert rec["registration"]["applied"] and rec["registration"]["shift_px"] == [-3, 0]
    a = np.asarray(out.resize((300, 150)))[:, :, 3]
    assert a[75, 11] > 200 and a[75, 291] < 60                                              # 옮긴 뒤 실루엣이 컨셉 자리
    with pytest.raises(cp.ConceptPixelsError, match="IoU"):
        cp.transplant(_concept_frame(text=False), _codex_texture(half=True))
    # 상자를 꽉 채우는 사각 패널은 실루엣 = 상자 — codex 실루엣이 틀려도(run 5 체인 패널 오목 · IoU 0.804) 옮겨 심는다
    out, rec = cp.transplant(_concept_frame(text=False, inset=0), _codex_texture(half=True))
    a = np.asarray(out.resize((300, 150)))[:, :, 3]
    assert rec["silhouette_from"].startswith("widget box") and rec["concept_box_fill"] >= cp.RECT_FILL and rec["silhouette_iou"] < 0.85
    assert a[75, 290] > 200 and a[1, 150] == 255 and abs(int(a[75, 150]) - 229) <= 2


def test_concept_pixel_inputs_skip_gauge_frames_and_collect_texts():
    frame = {"id": "Panel", "type": "Border", "bbox_intent": [100, 100, 300, 150], "style": {"brush": {"draw_as": "image", "asset": "panel"}}}
    label = {"id": "Label", "type": "TextBlock", "bbox_intent": [150, 120, 100, 40], "font": {"glow": {"size": 6, "color": "#FFFFFF80"}}}
    icon = {"id": "Icon", "type": "Image", "bbox_intent": [300, 150, 40, 40], "style": {"brush": {"draw_as": "image", "asset": "icon"}}}
    asset = {"asset_id": "panel"}
    texts, excl, skip, gauges = refine.concept_pixel_inputs({"widgets": [frame, label, icon]}, asset, frame["bbox_intent"])
    assert skip is None and texts == [{"id": "Label", "box": [50.0, 20.0, 100.0, 40.0], "glow": 6.0}] and excl == [[200.0, 50.0, 40.0, 40.0]] and gauges == []
    # 1b 후속 G2 — 숨은 이미지 · 프레임보다 큰 이미지(뒤에 깔린 빛)는 빼지 않는다(빼면 프레임 전체가 구멍)
    glow = {"id": "Glow", "type": "Image", "bbox_intent": [90, 90, 320, 170], "visibility": "collapsed", "style": {"brush": {"draw_as": "image", "asset": "glow"}}}
    big = dict(glow, id="Big", visibility="visible")
    assert refine.concept_pixel_inputs({"widgets": [frame, glow, big]}, asset, frame["bbox_intent"])[1] == []
    portrait = {"id": "Portrait", "type": "Image", "bbox_intent": [120, 110, 200, 120], "binding": {"data": "portrait", "kind": "image"},
                "style": {"brush": {"draw_as": "rounded_box", "color": "#101010FF"}}}
    assert refine.concept_pixel_inputs({"widgets": [frame, portrait]}, asset, frame["bbox_intent"])[1] == [[20.0, 10.0, 200.0, 120.0]]   # 런타임 이미지는 구멍
    # 게이지가 겹친 프레임 — 채움이 컨셉 모양(concept_fill)이 아니면 예전처럼 건너뜀, 맞으면 측정값을 넘긴다
    bar = {"id": "Gauge", "type": "ProgressBar", "bbox_intent": [110, 200, 280, 30], "style": {"fill": {"draw_as": "box", "asset": "gauge_fill"}}}
    assert "gauge Gauge" in refine.concept_pixel_inputs({"widgets": [frame, label, bar]}, asset, frame["bbox_intent"])[2]
    spec = {"widgets": [frame, label, bar], "assets": [{"asset_id": "gauge_fill", "procedural": {"shape": "concept_fill", "track": [1, 2, 3, 4]}}]}
    texts, excl, skip, gauges = refine.concept_pixel_inputs(spec, asset, frame["bbox_intent"])
    assert skip is None and gauges == [{"widget": "Gauge", "params": {"shape": "concept_fill", "track": [1, 2, 3, 4]}}] and len(texts) == 1


def test_corner_f1_catches_a_missing_corner_ornament_that_the_ring_f1_misses():
    concept = _concept_frame(ornaments=("tl", "tr", "bl", "br"), text=False)
    render = _concept_frame(ornaments=("tl", "tr", "bl"), text=False)
    rec, _ = fidelity.render_vs_concept(concept, render)
    # 모서리 정사각에는 테두리 직선도 들어 있어 장식이 통째로 빠져도 0 은 아니다([실측] run 4 체인 패널 오른쪽 아래 0.643)
    assert rec["line_f1"]["f1"] > 0.95 and rec["corners"]["f1"]["br"] < 0.75 and rec["corners"]["min"] == rec["corners"]["f1"]["br"]
    assert rec["corners"]["f1"]["tl"] == 1.0
    # 패널 폭 글자 상자를 통째로 빼면 모서리가 가려진다 → 글자 획 둘레만 빼면 잡는다
    boxes = [[0, 0, 300, 50], [0, 100, 300, 50]]
    wide = np.zeros((150, 300), bool)
    for x, y, w, h in boxes:
        wide[y:y + h, x:x + w] = True
    hidden, _ = fidelity.render_vs_concept(concept, render, wide)
    assert hidden["corners"] is None or hidden["corners"]["min"] > 0.9                         # 남은 가운데 띠만 재서 못 잡는다
    seen, _ = fidelity.render_vs_concept(concept, render, wide, fidelity.glyph_exclusion(concept, render, boxes))
    assert seen["corners"]["f1"]["br"] < 0.75 and seen["line_f1"] == hidden["line_f1"]         # 기존 지표 값은 그대로


def _fid(score: float) -> dict:
    return {"shape_iou": 0.99, "line_f1": {"f1": score}, "corners": None}


def test_replace_guard_keeps_the_old_asset_when_the_redo_is_worse(tmp_path):
    run = Run("R20261115_200000_CombatHUD", tmp_path / "work", CFG, tmp_path / "m.jsonl")
    run.create()
    bdir = run.path("style", "round_001_backup")
    for root, tag, scores in ((bdir, b"old", {"a": 0.98, "b": 0.90}), (run.path(), b"new", {"a": 0.91, "b": 0.95})):
        for kind in ("final", "raw", "compare"):
            for aid in ("a", "b"):
                p = root / "assets" / kind / f"{aid}.png"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(tag)
        (root / "refine.json").write_text(json.dumps({"passes": [{"assets": [{"asset_id": k, "fidelity": _fid(v)} for k, v in scores.items()]}]}), encoding="utf-8")
        (root / "manifest.json").write_text(json.dumps({"assets": [{"asset_id": k, "sha256": tag.decode()} for k in scores]}), encoding="utf-8")
    recs = style.replace_guard(run, "style/round_001_backup", ["a", "b"], 0.02)
    assert [r["action"] for r in recs] == ["restored_old", "kept_new"] and recs[0]["before"] == 0.98 and recs[0]["after"] == 0.91
    assert run.path("assets", "final", "a.png").read_bytes() == b"old" and run.path("assets", "final", "b.png").read_bytes() == b"new"
    m = {a["asset_id"]: a["sha256"] for a in run.read_json("manifest.json")["assets"]}
    assert m == {"a": "old", "b": "new"}


def test_shift_text_along_a_box_takes_room_from_the_neighbour():
    """[실측 G 굵기 끝 run] 채움 칸 배너 라벨을 자기 padding ±5 로 옮기자 칸을 넘어 옆 Spacer 와 겹쳤다(overlap 게이트) — 주축은 이웃에서 가져온다."""
    def row():
        return {"widgets": [
            {"id": "Row", "type": "HorizontalBox"},
            {"id": "A", "type": "TextBlock", "parent": "Row", "bbox_intent": [0, 0, 100, 40], "slot": {"kind": "horizontal_box", "size_rule": "fill", "padding": [0, 0, 0, 0]}},
            {"id": "Gap", "type": "Spacer", "parent": "Row", "bbox_intent": [100, 15, 20, 10], "style": {"size": [20, 10]}, "slot": {"kind": "horizontal_box", "size_rule": "auto"}},
            {"id": "B", "type": "TextBlock", "parent": "Row", "bbox_intent": [120, 0, 40, 40], "slot": {"kind": "horizontal_box", "size_rule": "auto", "padding": [6, 0, 0, 0], "v_align": "center"}}]}
    s = row()
    a, gap, b = (next(w for w in s["widgets"] if w["id"] == k) for k in ("A", "Gap", "B"))
    out = style._shift_text(a, 5, 0, s)                                                        # 오른쪽으로 → 다음 이웃(Spacer)에서
    assert out["shift"] == [5.0, 0.0] and a["slot"]["padding"] == [5.0, 0, 0, 0] and gap["style"]["size"] == [15.0, 10]
    assert gap["bbox_intent"] == [105.0, 15.0, 15.0, 10.0] and a["bbox_intent"][0] == 5.0
    out = style._shift_text(b, -4, 3, s)                                                       # 왼쪽으로 → 앞 이웃(Spacer)에서, 세로는 가운데라 ±1.5
    assert out["shift"] == [-4.0, 3.0] and b["slot"]["padding"] == [6, 1.5, 4.0, -1.5] and gap["style"]["size"] == [11.0, 10]
    s2 = row()
    a2 = s2["widgets"][1]
    next(w for w in s2["widgets"] if w["id"] == "Gap")["style"]["size"] = [3, 10]
    out = style._shift_text(a2, 5, 0, s2)                                                      # 이웃에 여유 없음 → 그 축은 안 옮김
    assert "shift" not in out and out["skipped"] and a2["slot"]["padding"] == [0, 0, 0, 0]
    out = style._shift_text(a2, -3, 0, s2)                                                     # 상자 맨 앞 → 자기 양쪽 ±
    assert out["shift"] == [-3.0, 0.0] and a2["slot"]["padding"] == [-3.0, 0, 3.0, 0]


def _bars(d, x0, y0, n, step, w=8, h=40):
    for i in range(n):
        d.rectangle([x0 + i * step, y0, x0 + i * step + w - 1, y0 + h - 1], fill=GOLD)


def test_text_fit_matches_spacing_and_centre_without_moving_siblings(tmp_path):
    spec = {"root": "Root", "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Banner", "type": "Border", "parent": "Root", "bbox_intent": [50, 40, 300, 120],
         "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [50, 40], "size": [300, 120]}},
        {"id": "Row", "type": "HorizontalBox", "parent": "Banner", "bbox_intent": [70, 40, 260, 120],
         "slot": {"kind": "border", "padding": [20, 0, 20, 0], "h_align": "fill", "v_align": "center"}},
        {"id": "Label", "type": "TextBlock", "parent": "Row", "bbox_intent": [70, 70, 200, 60], "font": {"size": 40}, "justification": "left",
         "slot": {"kind": "horizontal_box", "size_rule": "fill", "padding": [0, 0, 0, 0], "v_align": "center"}, "text": {"source": "static", "value": "ABCDE"}},
        {"id": "Tag", "type": "TextBlock", "parent": "Root", "bbox_intent": [60, 170, 100, 26], "font": {"size": 20},
         "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [60, 170], "size": [100, 26]}, "text": {"source": "static", "value": "X"}}]}
    ref, ren = Image.new("RGB", (400, 200), (20, 15, 10)), Image.new("RGB", (400, 200), (20, 15, 10))
    _bars(ImageDraw.Draw(ref), 80, 80, 5, 30)              # 컨셉: 폭 128 · y 80 ~ 120
    _bars(ImageDraw.Draw(ren), 80, 75, 5, 26)              # 렌더: 폭 112(자간 좁음) · 5 px 위
    _bars(ImageDraw.Draw(ref), 70, 175, 1, 0, w=10, h=16)  # 'X' 컨셉
    _bars(ImageDraw.Draw(ren), 74, 175, 1, 0, w=10, h=16)  # 'X' 렌더 4 px 오른쪽
    ref.save(tmp_path / "reference.png")
    ren.save(tmp_path / "render.png")
    after, recs = style.text_fit(spec, tmp_path / "reference.png", tmp_path / "render.png", CFG)
    by = {w["id"]: w for w in after["widgets"]}
    lab = next(r for r in recs if r.get("widget") == "Label")
    # 글자 사이 (128 − 112) / 4 = 4 px → 자간 ⌈4 × 1000 / 40⌉ = 100, 왼쪽 정렬 채움 칸이라 오른쪽으로 자라 중심 차 0 → 세로만 +5
    # 세로 가운데 정렬은 오프셋 = … + 위 여백 − 아래 여백(LayoutUtils.h:664)이라 ±2.5 가 5 px
    assert lab["letter_spacing"] == [0.0, 100] and by["Label"]["font"]["letter_spacing"] == 100 and lab["center_d"] == [0.0, 5.0]
    assert by["Label"]["slot"]["padding"] == [0.0, 2.5, 0.0, -2.5] and by["Label"]["bbox_intent"] == [70.0, 75.0, 200.0, 60.0]
    assert by["Row"] == spec["widgets"][2] and by["Banner"] == spec["widgets"][1]          # 형제 · 부모 그대로
    tag = next(r for r in recs if r.get("widget") == "Tag")
    assert tag["shift"] == [-4.0, 0.0] and by["Tag"]["slot"]["position"] == [56.0, 170.0] and "letter_spacing" not in tag
    assert style.text_fit_changed(recs) == ["Label", "Tag"] and spec["widgets"][3]["slot"]["padding"] == [0, 0, 0, 0]   # 입력은 그대로
    # 렌더 획이 측정 상자 끝에 닿으면(이웃 · 선) 믿지 않는다 · 크기가 다르면 크기 판 몫
    _bars(ImageDraw.Draw(ren), 84, 178, 1, 0, w=14, h=10)    # 'X' 오른쪽에 붙은 덩어리가 측정 상자(x 64 ~ 86) 끝까지
    ren.save(tmp_path / "render2.png")
    _, recs2 = style.text_fit(spec, tmp_path / "reference.png", tmp_path / "render2.png", CFG)
    tag2 = next(r for r in recs2 if r.get("widget") == "Tag")
    assert tag2.get("skipped") and "shift" not in tag2                                         # 넓혀 다시 재도 믿을 수 없으면 건너뜀
    _, recs3 = style.text_fit(spec, tmp_path / "reference.png", tmp_path / "reference.png", CFG)
    assert style.text_fit_changed(recs3) == []                                                # 같으면 아무것도 안 바꾼다
    # 글자 모양이 좁아서 생긴 폭 차이(틈은 같음)는 자간으로 메우지 않는다 — [실측 G 끝 run 1] '4.2' 가 '4 . 2' 로 벌어졌던 것
    thin = Image.new("RGB", (400, 200), (20, 15, 10))
    _bars(ImageDraw.Draw(thin), 80, 80, 5, 27, w=5)          # 틈 22 px 그대로 · 획만 8 → 5 px(폭 128 → 113)
    thin.save(tmp_path / "thin.png")
    _, recs4 = style.text_fit(spec, tmp_path / "reference.png", tmp_path / "thin.png", CFG)
    lab4 = next(r for r in recs4 if r.get("widget") == "Label")
    assert lab4["w_ratio"] < 0.9 and lab4["gap_cols"] == [88, 88] and "letter_spacing" not in lab4
    # analyze 상자가 글자보다 짧아도(컨셉 획이 잘림) 넓혀 다시 재 전체 획을 잡는다 — [실측 G 끝 run 3] 배너 라벨 222 → 275 px
    cut = json.loads(json.dumps(spec))
    next(w for w in cut["widgets"] if w["id"] == "Label")["bbox_intent"] = [70, 70, 100, 60]   # 막대 80 ~ 208 중 170 까지만
    _, recs5 = style.text_fit(cut, tmp_path / "reference.png", tmp_path / "render.png", CFG)
    lab5 = next(r for r in recs5 if r.get("widget") == "Label")
    assert lab5["concept_ink"] == [80, 80, 128, 40] and lab5["concept_box_grown"] >= 1 and lab5["letter_spacing"] == [0.0, 100]
    # 굵기(크기 판) — 컨셉 획이 렌더보다 크게 가늘면(밀도 비 < 1/1.22) bold → regular, 그 판에서 위치 · 자간은 안 건드림 — [실측 G 끝 run 4] '오의 불가' 0.706
    heavy = Image.new("RGB", (400, 200), (20, 15, 10))
    _bars(ImageDraw.Draw(heavy), 78, 80, 5, 30, w=12)        # 같은 자리 · 같은 높이, 획만 8 → 12 px(밀도 1.5 배)
    _bars(ImageDraw.Draw(heavy), 70, 175, 1, 0, w=10, h=16)
    heavy.save(tmp_path / "heavy.png")
    after6, recs6 = style.text_fit(spec, tmp_path / "reference.png", tmp_path / "heavy.png", CFG, mode="size")
    lab6 = next(r for r in recs6 if r.get("widget") == "Label")
    assert lab6["weight"][:2] == ["bold", "regular"] and lab6["weight"][2] < 0.8 and "letter_spacing" not in lab6 and "shift" not in lab6
    assert next(w for w in after6["widgets"] if w["id"] == "Label")["font"]["weight"] == "regular" and style.text_fit_changed(recs6) == ["Label"]
    assert "size" not in lab6                                                                   # 높이가 같으면 크기 그대로
    assert "weight" not in next(r for r in recs if r.get("widget") == "Label")                  # 위치 판은 굵기를 안 본다
    _, recs7 = style.text_fit(spec, tmp_path / "reference.png", tmp_path / "heavy.png", CFG)
    assert "weight" not in next(r for r in recs7 if r.get("widget") == "Label")
    small = Image.new("RGB", (2, 2))
    small.save(tmp_path / "tiny.png")
    assert style.text_fit(spec, tmp_path / "reference.png", tmp_path / "tiny.png", CFG)[1][0]["skipped"].startswith("reference")
    # 렌더 첫 글자가 측정 상자(x 68 ~ 220) 왼쪽 끝에 걸쳐 잘려도(text_ink 는 끝에 닿은 덩어리를 지운다) 그쪽을 넓혀 다시 잰다
    # [실측 G 크기 끝 run] 크기 판이 배너 라벨을 가운데 중심으로 키우자 '체' 가 측정에서 빠졌다(렌더 폭 225 — 실제 약 257)
    cut_r = Image.new("RGB", (400, 200), (20, 15, 10))
    _bars(ImageDraw.Draw(cut_r), 64, 80, 5, 30)              # 컨셉과 같은 모양 · 16 px 왼쪽 — 첫 막대 64 ~ 71 이 상자 끝 68 에 걸침
    cut_r.save(tmp_path / "cut_render.png")
    _, recs8 = style.text_fit(spec, tmp_path / "reference.png", tmp_path / "cut_render.png", CFG)
    lab8 = next(r for r in recs8 if r.get("widget") == "Label")
    assert lab8["widened"] == 1 and lab8["render_ink"] == [64, 80, 128, 40] and lab8["center_d"] == [16.0, 0.0] and "letter_spacing" not in lab8


def _row_spec() -> dict:
    """가로 상자 안 채움 칸 · 왼쪽 정렬 라벨 + 바로 옆 auto 칸 숫자(앞 여백 −4 — 이웃 규칙으로는 공간을 못 가져옴)."""
    return {"root": "Root", "profile": "hud", "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Row", "type": "HorizontalBox", "parent": "Root", "bbox_intent": [50, 50, 300, 60],
         "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [50, 50], "size": [300, 60]}},
        {"id": "Label", "type": "TextBlock", "parent": "Row", "bbox_intent": [50, 50, 200, 60], "font": {"size": 40, "family": NOTO},
         "justification": "left", "slot": {"kind": "horizontal_box", "size_rule": "fill", "h_align": "left", "v_align": "center", "padding": [0, 0, 0, 0]},
         "text": {"source": "static", "value": "ABCDE"}},
        {"id": "Count", "type": "TextBlock", "parent": "Row", "bbox_intent": [294, 50, 52, 60], "font": {"size": 40, "family": NOTO},
         "slot": {"kind": "horizontal_box", "size_rule": "auto", "v_align": "center", "padding": [-4, 0, -4, 0]}, "text": {"source": "static", "value": "3"}}]}


def test_text_fit_place_moves_along_a_box_inside_its_own_slot_when_no_overlap_is_predicted(tmp_path):
    """위치 판 — 상자 주축 이동은 직전 렌더 geometry 로 형제 겹침을 예측해(overlap 게이트 규칙) 겹치지 않으면 자기 양쪽 padding 으로(칸 자리 그대로),
    겹치면 예전처럼 이웃에서 가져온다. [실측 G 크기 끝 run] 크기 판 뒤 '3' 의 앞 여백 −4 라 배너 라벨을 못 옮겨 중심 차 25 px 가 남았다."""
    ref, ren = Image.new("RGB", (400, 200), (20, 15, 10)), Image.new("RGB", (400, 200), (20, 15, 10))
    _bars(ImageDraw.Draw(ref), 90, 60, 5, 30)               # 라벨 컨셉 90 ~ 217
    _bars(ImageDraw.Draw(ren), 80, 60, 5, 30)               # 렌더 10 px 왼쪽
    for im in (ref, ren):
        _bars(ImageDraw.Draw(im), 302, 60, 1, 0, w=14)      # '3' 같은 자리
    ref.save(tmp_path / "reference.png")
    ren.save(tmp_path / "render.png")
    rendered = {"Root": [0, 0, 400, 200], "Row": [50, 50, 300, 60], "Label": [50, 50, 180, 60], "Count": [294, 50, 52, 60]}
    after, recs = style.text_fit(_row_spec(), tmp_path / "reference.png", tmp_path / "render.png", CFG, rendered)
    by, lab = {w["id"]: w for w in after["widgets"]}, next(r for r in recs if r.get("widget") == "Label")
    assert lab["shift"] == [10.0, 0.0] and lab["own_padding"] and by["Label"]["slot"]["padding"] == [10.0, 0, -10.0, 0]
    assert by["Count"]["slot"]["padding"] == [-4, 0, -4, 0] and "shift" not in next(r for r in recs if r.get("widget") == "Count")
    # 라벨 위젯이 칸 끝까지 차 있으면(렌더 폭 240 → 오른쪽 끝 290) 10 px 옮기면 '3' 과 겹친다(예측) → 이웃 규칙 → 여유 없음 → 그 축은 안 옮김
    rendered["Label"] = [50, 50, 240, 60]
    after2, recs2 = style.text_fit(_row_spec(), tmp_path / "reference.png", tmp_path / "render.png", CFG, rendered)
    lab2 = next(r for r in recs2 if r.get("widget") == "Label")
    assert "shift" not in lab2 and "own_padding" not in lab2 and next(w for w in after2["widgets"] if w["id"] == "Label")["slot"]["padding"] == [0, 0, 0, 0]


def test_text_fit_place_leaves_a_canvas_move_that_would_overlap_a_region(tmp_path):
    """[실측 G2 파티 HUD] 캔버스 직계 '0 %' 를 위로 옮기자 옆 영역과 겹쳐(0.086) 위치 판 전체가 버려졌다 — 겹침이 예측되는 축은 안 옮긴다."""
    canvas = lambda x, y, w, h: {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [x, y], "size": [w, h]}   # noqa: E731
    spec = {"root": "Root", "profile": "hud", "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Bar", "type": "Border", "parent": "Root", "bbox_intent": [40, 60, 320, 30], "slot": canvas(40, 60, 320, 30)},
        {"id": "Pct", "type": "TextBlock", "parent": "Root", "bbox_intent": [150, 92, 100, 50], "font": {"size": 30, "family": NOTO},
         "slot": canvas(150, 92, 100, 50), "text": {"source": "static", "value": "AB"}}]}
    ref, ren = Image.new("RGB", (400, 200), (20, 15, 10)), Image.new("RGB", (400, 200), (20, 15, 10))
    _bars(ImageDraw.Draw(ref), 180, 98, 2, 30, w=10, h=24)       # 컨셉 6 px 위 · 8 px 오른쪽
    _bars(ImageDraw.Draw(ren), 172, 104, 2, 30, w=10, h=24)
    ref.save(tmp_path / "reference.png")
    ren.save(tmp_path / "render.png")
    rendered = {"Root": [0, 0, 400, 200], "Bar": [40, 60, 320, 30], "Pct": [150, 92, 100, 50]}
    after, recs = style.text_fit(spec, tmp_path / "reference.png", tmp_path / "render.png", CFG, rendered)
    pct = next(r for r in recs if r.get("widget") == "Pct")
    # 위로 6 px 면 Bar(아래 끝 90)와 겹침 4 × 100 / (100 × 50) = 0.08 > 0.04 → 세로는 버리고 가로 8 px 만
    assert pct["center_d"] == [8.0, -6.0] and pct["shift"] == [8.0, 0.0] and "axis_dropped" in pct
    assert next(w for w in after["widgets"] if w["id"] == "Pct")["slot"]["position"] == [158.0, 92]


NOTO = "/Game/UI/Fonts/NotoSerifKR/F_NotoSerifKR.F_NotoSerifKR"     # 줄 높이 표 22 → 43 · 26 → 51 · 30 → 58


def _stack_spec(parent_type: str) -> dict:
    """패널 안 세로로 맞닿은 글자 둘 — 'Title'(22, 줄 상자 43) 바로 아래 'Big'(24, 줄 상자 47).
    parent_type VerticalBox = 형제 겹침 검사 대상 · Overlay = 쌓기 부모(검사 안 함 — profiles/hud.yaml stacking_parents)."""
    vbox = parent_type == "VerticalBox"

    def slot(top):
        return ({"kind": "vertical_box", "size_rule": "auto", "h_align": "fill", "v_align": "center"} if vbox
                else {"kind": "overlay", "h_align": "fill", "v_align": "top", "padding": [0, top, 0, 0]})
    return {"root": "Root", "profile": "hud", "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Panel", "type": "Border", "parent": "Root", "bbox_intent": [50, 10, 300, 180],
         "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [50, 10], "size": [300, 180]}},
        {"id": "Box", "type": parent_type, "parent": "Panel", "bbox_intent": [50, 20, 300, 170],
         "slot": {"kind": "border", "padding": [0, 10, 0, 0], "h_align": "fill", "v_align": "fill"}},
        {"id": "Title", "type": "TextBlock", "parent": "Box", "bbox_intent": [50, 20, 300, 43], "font": {"size": 22, "family": NOTO},
         "justification": "center", "slot": slot(0), "text": {"source": "static", "value": "AB"}},
        {"id": "Big", "type": "TextBlock", "parent": "Box", "bbox_intent": [50, 63, 300, 47], "font": {"size": 24, "family": NOTO},
         "justification": "center", "slot": slot(43), "text": {"source": "static", "value": "CD"}}]}


def test_text_fit_size_pass_resizes_from_the_height_ratio_and_stops_before_a_sibling_overlap(tmp_path):
    """크기 판 — 새 크기 = round(크기 ÷ 높이 비), 상자는 가운데 중심으로 커지고(follow_text_boxes) 그 판에서 위치 · 자간은 안 건드린다.
    [실측 G 굵기 끝 run] 외형 라운드가 버려지자 analyze 크기가 남음('4.2' 높이 비 0.80) · VerticalBox 체인 패널에서 '4.2' 52 → 65 가 형제와 겹쳐 라운드가 버려짐."""
    ref, ren = Image.new("RGB", (400, 200), (20, 15, 10)), Image.new("RGB", (400, 200), (20, 15, 10))
    for im in (ref, ren):
        _bars(ImageDraw.Draw(im), 170, 30, 2, 40, w=10, h=20)       # 'Title' — 컨셉 · 렌더 같음(높이 비 1.0)
    _bars(ImageDraw.Draw(ref), 160, 66, 2, 50, w=14, h=40)          # 'Big' 컨셉 높이 40
    _bars(ImageDraw.Draw(ren), 163, 70, 2, 46, w=12, h=32)          # 'Big' 렌더 높이 32 → 높이 비 0.8 → 24 ÷ 0.8 = 30
    ref.save(tmp_path / "reference.png")
    ren.save(tmp_path / "render.png")
    rendered = {"Root": [0, 0, 400, 200], "Panel": [50, 10, 300, 180], "Box": [50, 20, 300, 170], "Title": [50, 20, 300, 43], "Big": [50, 63, 300, 47]}
    # 쌓기 부모(Overlay) — 겹침 검사 대상이 아니라 컨셉 높이까지 그대로
    spec = _stack_spec("Overlay")
    after, recs = style.text_fit(spec, tmp_path / "reference.png", tmp_path / "render.png", CFG, rendered, mode="size")
    by, big = {w["id"]: w for w in after["widgets"]}, next(r for r in recs if r.get("widget") == "Big")
    assert big["size"] == [24, 30, 0.8] and by["Big"]["font"]["size"] == 30 and "size_capped" not in big
    assert not {"shift", "letter_spacing", "weight"} & set(big) and "size" not in next(r for r in recs if r.get("widget") == "Title")
    # 줄 상자 47 → 58: 위 정렬 overlay 는 위 여백 −5.5 · 아래 −5.5 로 가운데 유지, bbox_intent = 렌더 상자를 가운데 기준으로 키운 것
    assert by["Big"]["slot"]["padding"] == [0, 37.5, 0, -5.5] and by["Big"]["bbox_intent"] == [50.0, 57.5, 300.0, 58.0]
    assert style.text_fit_changed(recs) == ["Big"] and spec["widgets"][4]["font"]["size"] == 24                     # 입력은 그대로
    assert [f["widget"] for f in next(r for r in recs if "text_boxes_followed" in r)["text_boxes_followed"]] == ["Big"]
    # 형제 겹침 검사 부모(VerticalBox) — 26 부터 줄 상자가 위 글자와 0.04 넘게 겹친다(예측) → 25 에서 멈춤
    after2, recs2 = style.text_fit(_stack_spec("VerticalBox"), tmp_path / "reference.png", tmp_path / "render.png", CFG, rendered, mode="size")
    big2 = next(r for r in recs2 if r.get("widget") == "Big")
    assert big2["size"] == [24, 25, 0.8] and "capped at 25" in big2["size_capped"] and big2["overlap_check"].startswith("predicted")
    assert next(w for w in after2["widgets"] if w["id"] == "Big")["slot"]["padding"] == [0, -1.0, 0, -1.0]
    # 렌더 geometry 가 없으면 예측 없이 맞춤(겹치면 게이트가 그 판을 버린다)
    _, recs3 = style.text_fit(_stack_spec("VerticalBox"), tmp_path / "reference.png", tmp_path / "render.png", CFG, mode="size")
    assert next(r for r in recs3 if r.get("widget") == "Big")["overlap_check"].startswith("skipped")
    # 위치 판은 높이 비가 0.88 ~ 1.12 밖인 글자를 건너뛴다(크기 판 몫)
    _, recs4 = style.text_fit(spec, tmp_path / "reference.png", tmp_path / "render.png", CFG, rendered)
    assert "size pass" in next(r for r in recs4 if r.get("widget") == "Big")["skipped"]
    # 높이 비가 0.75 ~ 1.33 밖이면 측정을 믿지 않는다 — [실측 G 굵기 끝 run] '2/4' 0.38(획이 패널 밖으로 잘림)
    tiny = Image.new("RGB", (400, 200), (20, 15, 10))
    _bars(ImageDraw.Draw(tiny), 170, 30, 2, 40, w=10, h=20)
    _bars(ImageDraw.Draw(tiny), 163, 78, 2, 46, w=12, h=16)
    tiny.save(tmp_path / "half.png")
    _, recs5 = style.text_fit(spec, tmp_path / "reference.png", tmp_path / "half.png", CFG, rendered, mode="size")
    big5 = next(r for r in recs5 if r.get("widget") == "Big")
    assert big5["h_ratio"] == 0.4 and "not trusted" in big5["skipped"] and "size" not in big5
    with pytest.raises(ValueError):
        style.text_fit(spec, tmp_path / "reference.png", tmp_path / "render.png", CFG, mode="both")
