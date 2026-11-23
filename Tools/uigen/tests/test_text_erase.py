"""1b 후속 L 다음 — L-1 글자 완전 지우기 · 게이지 끝 모양: S4 글자 밑 흔적 · S2 보강 끝 모양 · G1 지울 범위 · G2 인페인팅 창 · G3 끝 모양 — 합성 그림, 에디터 · 모델 없음.
[실측 R20261119_144231 — 체인 패널 '4.2' 빛 윤곽 · 게이지 100 % 오른쪽 끝이 끝 장식 호를 덮음]"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from gen import concept_fill
from gen import diagnose as dg
from gen import inpaint
from gen import state_check

PANEL = (40, 30, 50)
GLYPH = (250, 235, 200)
W, H = 260, 140


def _glyph_mask():
    m = np.zeros((H, W), bool)
    m[50:90, 100:108] = True            # 세로 획
    m[50:58, 100:140] = True            # 가로 획
    m[82:90, 100:140] = True
    return m


def _scene(trace: str):
    """불투명 패널 판 + 빛 든 밝은 글자 컨셉. trace = 'ring'(텍스처에 빛 바깥 윤곽) · 'clean' · 'line'(가는 가로선만)."""
    g = _glyph_mask()
    import cv2
    dist = cv2.distanceTransform((~g).astype(np.uint8), cv2.DIST_L2, 5)
    panel = np.zeros((H, W, 4), float)
    panel[20:120, 20:240, :3], panel[20:120, 20:240, 3] = PANEL, 255
    concept = panel.copy()
    glow = np.clip(1 - dist / 9.0, 0, 1)[..., None] * (np.array([140, 90, 30.0]) * (concept[..., 3:] > 0))
    concept[..., :3] = np.clip(concept[..., :3] + glow, 0, 255)
    concept[g, :3] = GLYPH
    tex = panel.copy()
    if trace == "ring":
        ring = (dist > 5) & (dist <= 7) & (panel[..., 3] > 0)
        tex[ring, :3] = np.clip(np.asarray(PANEL, float) + np.array([40, 26, 8.0]), 0, 255)
    elif trace == "line":
        tex[92:94, 96:150, :3] = np.asarray(PANEL, float) + 40
    spec = {"canvas": [W, H], "root": "Root", "assets": [], "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Panel", "type": "Image", "parent": "Root", "slot": {"kind": "canvas", "z": 0}, "style": {"brush": {"draw_as": "image", "asset": "panel"}}},
        {"id": "Timer", "type": "TextBlock", "parent": "Root", "slot": {"kind": "canvas", "z": 1}, "text": {"source": "dynamic", "data": "t", "sample": "4.2"},
         "font": {"color": "#FAEBC8FF", "glow": {"size": 9, "color": "#FF9F3F80"}}}]}
    boxes = [{"id": "Root", "x": 0, "y": 0, "w": W, "h": H, "visible": True}, {"id": "Panel", "x": 0, "y": 0, "w": W, "h": H, "visible": True},
             {"id": "Timer", "x": 88, "y": 38, "w": 66, "h": 64, "visible": True}]
    return spec, boxes, {"panel": tex}, concept, g, panel


def _trace(trace: str, settings=None):
    from gen import backdrop
    spec, boxes, tex, concept, g, panel = _scene(trace)
    gm = {"Timer": {"concept": g, "concept_cand": dg._dilate(g, 1)}}
    s = settings or dg.settings(None)
    imgs = {k: backdrop.compose(spec, boxes, tex, [W, H], bg)[0] for k, bg in (("black", (0, 0, 0)), ("gray", backdrop.GRAY), ("white", (255, 255, 255)))}
    plate = (panel[..., :3], panel[..., 3] / 255.0)
    return state_check.text_trace(spec, boxes, [W, H], concept[..., :3], concept[..., 3] / 255.0, plate, gm, s, imgs)


def test_text_trace_finds_the_glow_outline_left_under_an_empty_text():
    r = _trace("ring")
    f = [x for x in r["findings"] if x["check"] == "text_trace"]
    assert f and f[0]["code"] == "E8" and f[0]["widgets"][0] == "Timer"
    assert {"black", "gray", "white"} <= set(f[0]["backgrounds"])
    t = next(t for t in r["texts"] if t["widget"] == "Timer")
    assert t["glow_tail"] >= 5 and t["local_max"]["gray"] > 5.0
    # 글자 지우기 마감 — 가는 고리는 가는 선(text_contour)으로도 잡힌다(골격 길이 · 두께)
    c = [x for x in r["findings"] if x["check"] == "text_contour"]
    assert c and c[0]["length"] >= state_check.CONTOUR_LEN and c[0]["thick"] <= state_check.CONTOUR_THICK


def test_text_contour_catches_a_thin_outline_the_3x3_mean_misses():
    """[실측 R20261119_190059 '4' 안쪽 윤곽 — 3 × 3 국소 3.1 < 5] 1 px 고리는 text_trace 가 못 보고 가는 선이 잡는다."""
    spec, boxes, tex, concept, g, panel = _scene("clean")
    import cv2
    dist = cv2.distanceTransform((~g).astype(np.uint8), cv2.DIST_L2, 5)
    ring1 = (dist > 3.5) & (dist <= 4.5) & (panel[..., 3] > 0)
    tex["panel"][ring1, :3] = np.clip(np.asarray(PANEL, float) + np.array([14, 9, 3.0]), 0, 255)
    from gen import backdrop
    gm = {"Timer": {"concept": g, "concept_cand": dg._dilate(g, 1)}}
    imgs = {k: backdrop.compose(spec, boxes, tex, [W, H], bg)[0] for k, bg in (("black", (0, 0, 0)), ("gray", backdrop.GRAY), ("white", (255, 255, 255)))}
    r = state_check.text_trace(spec, boxes, [W, H], concept[..., :3], concept[..., 3] / 255.0, (panel[..., :3], panel[..., 3] / 255.0), gm,
                               dg.settings(None), imgs)
    assert not [x for x in r["findings"] if x["check"] == "text_trace"]
    assert [x for x in r["findings"] if x["check"] == "text_contour"]


def test_text_trace_tone_matched_plate_does_not_explain_a_darker_plate_patch():
    """[실측 R20261119_190059 배너] 판 그대로 설명은 텍스처가 둘레와 색조가 다른 판 픽셀을 글자 자리에 붙인 얼룩까지 설명했다 → 둘레에 색조 맞춘 판."""
    spec, boxes, tex, concept, g, panel = _scene("clean")
    plate_dark = panel.copy()
    plate_dark[..., :3] = np.clip(plate_dark[..., :3] - 18, 0, 255)                 # codex 판 — 전체가 어두움
    patch = dg._dilate(g, 3) & (panel[..., 3] > 0)
    tex["panel"][patch, :3] = plate_dark[patch, :3]                                     # 텍스처 = 글자 자리만 판(좁은 메움)
    from gen import backdrop
    gm = {"Timer": {"concept": g, "concept_cand": dg._dilate(g, 1)}}
    imgs = {k: backdrop.compose(spec, boxes, tex, [W, H], bg)[0] for k, bg in (("black", (0, 0, 0)), ("gray", backdrop.GRAY), ("white", (255, 255, 255)))}
    r = state_check.text_trace(spec, boxes, [W, H], concept[..., :3], concept[..., 3] / 255.0, (plate_dark[..., :3], plate_dark[..., 3] / 255.0), gm,
                               dg.settings(None), imgs)
    assert [x for x in r["findings"] if x["check"] in ("text_trace", "text_contour")]


def test_text_trace_hidden_texture_group_is_judged_with_that_widget_shown():
    """S4 숨는 묶음 — 텍스처째 숨는 위젯(배너) 아래 글자는 그 위젯만 켠 글자 없는 상태로(결함에 state)."""
    from gen import backdrop
    spec, boxes, tex, concept, g, panel = _scene("ring")
    for w in spec["widgets"]:
        if w["id"] == "Panel":
            w["visibility"] = "collapsed"
        if w["id"] == "Timer":
            w["parent"] = "Panel"
    groups = state_check.texture_groups(spec, tex)
    assert groups == [{"root": "Panel", "texts": {"Timer"}}]
    for g_ in groups:
        g_["images"] = {k: backdrop.compose(spec, boxes, tex, [W, H], bg)[0] for k, bg in (("black", (0, 0, 0)), ("gray", backdrop.GRAY), ("white", (255, 255, 255)))}
        g_["render"] = None
    off = {k: np.zeros((H, W, 3)) for k in ("black", "gray", "white")}
    gm = {"Timer": {"concept": g, "concept_cand": dg._dilate(g, 1)}}
    r = state_check.text_trace(spec, boxes, [W, H], concept[..., :3], concept[..., 3] / 255.0, (panel[..., :3], panel[..., 3] / 255.0), gm,
                               dg.settings(None), off, groups=groups)
    f = [x for x in r["findings"] if x["check"] == "text_trace"]
    assert f and f[0].get("state") == "Panel" and r["groups"][0]["root"] == "Panel"
    assert next(t for t in r["texts"] if t["widget"] == "Timer").get("state") == "Panel"


def test_text_trace_clean_texture_and_thin_line_are_not_traces():
    r = _trace("clean")
    assert r["findings"] == [] and next(t for t in r["texts"] if t["widget"] == "Timer")["local_max"]["gray"] < 2.0
    # 2 px 가로선 = 구조선(기록만) — 글자 지우기 다음 V2 부터는 판에도 있는 선일 때만(이 그림의 판엔 없음 → error 면 결함, test_text_erase_next) — 기록 모드로 예전 뜻
    r2 = _trace("line", {**dg.settings(None), "text_line_plate": "record", "text_lift_mode": "record"})
    assert r2["findings"] == [] and r2.get("line_like")


def test_value_trace_ring_ignores_the_new_glyph():
    """[실측 R20261120_001224 L-2] 값 바뀜 검사 둘레 고리에 새로 그린 글자('9.7')가 섞이면 둘레 설명 · 판 색조 맞춤이 그 밝은 쪽으로 끌려 깨끗한 바탕을 흔적으로 봤다."""
    from gen import backdrop
    spec, boxes, tex, concept, g, panel = _scene("clean")
    gm = {"Timer": {"concept": g, "concept_cand": dg._dilate(g, 1)}}
    imgs = {k: backdrop.compose(spec, boxes, tex, [W, H], bg)[0] for k, bg in (("black", (0, 0, 0)), ("gray", backdrop.GRAY), ("white", (255, 255, 255)))}
    notext = imgs["black"].copy()
    values = notext.copy()
    new = np.zeros((H, W), bool)
    new[46:94, 112:150] = True                          # 다른 값 글자 — 옛 자리 옆으로 걸침
    values[new] = GLYPH
    r = state_check.text_trace(spec, boxes, [W, H], concept[..., :3], concept[..., 3] / 255.0, (panel[..., :3], panel[..., 3] / 255.0), gm,
                               dg.settings(None), imgs, renderer="engine", render_values=values, render_notext=notext)
    assert not [x for x in r["findings"] if x["check"] in ("text_value_trace", "text_value_contour")]
    assert r.get("values") == {"Timer": "9.7"}


def test_value_overrides_change_every_digit_and_skip_start_hidden_texts():
    spec = {"widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "A", "type": "TextBlock", "parent": "Root", "text": {"source": "dynamic", "sample": "4.2"}},
        {"id": "B", "type": "TextBlock", "parent": "Root", "text": {"source": "dynamic", "sample": "2/4"}},
        {"id": "C", "type": "TextBlock", "parent": "Root", "text": {"source": "static", "value": "체인"}},
        {"id": "D", "type": "TextBlock", "parent": "Root", "visibility": "collapsed", "text": {"source": "dynamic", "sample": "3"}}]}
    assert state_check.value_overrides(spec) == {"A": {"text": "9.7"}, "B": {"text": "7/9"}}


# ---------------------------------------------------------------------------------------------------------------------
# G3 게이지 끝 모양

FRAME = [730, 972, 460, 44]
BOX = [742, 982, 436, 24]
LINE, TRACK, BAND, RIM = (210, 170, 70), (35, 28, 24), (95, 65, 30), (255, 235, 160)


def _arc_off(y: int) -> int:
    return int(round(12 * ((y - 21.5) / 16.0) ** 2))


def _arc_concept(tmp_path, arc: bool):
    """test_gauge.framed_concept 와 같은 게이지 + (arc) 오른쪽 끝 장식 안쪽 호 — 트랙 줄 6 ~ 37 에서 x = 437 − 깊이(줄)에 2 px 금선, 그 오른쪽은 어두운 트랙."""
    ox, oy, ow, oh = FRAME
    im = Image.new("RGB", (ow, oh), (40, 34, 44))
    d = ImageDraw.Draw(im)
    d.rectangle([10, 6, 439, 37], fill=TRACK)
    end = 330
    d.rectangle([20, 6, end, 9], fill=BAND)
    d.rectangle([20, 34, end, 37], fill=BAND)
    for y in range(10, 34):
        x0 = 24 + int(round(abs(y - 21.5) * 8 / 11.5))
        d.line([(x0, y), (end, y)], fill=(230, 170, 70))
    d.line([(end, 10), (end, 33)], fill=RIM)
    d.rectangle([20, 4, 440, 5], fill=LINE)
    d.rectangle([20, 38, 440, 39], fill=LINE)
    d.line([(20, 4), (8, 22), (20, 39)], fill=LINE, width=2)
    d.rectangle([440, 4, 441, 39], fill=LINE)
    if arc:
        for y in range(6, 38):
            x = 437 - _arc_off(y)
            d.line([(x, y), (x + 1, y)], fill=LINE)
            d.line([(x + 2, y), (439, y)], fill=TRACK)
            d.line([(x + 1, y), (440, y)], fill=LINE) if _arc_off(y) == 0 else None
    full = Image.new("RGB", (1920, 1080), (60, 50, 70))
    full.paste(im, (ox, oy))
    p = tmp_path / ("arc.png" if arc else "straight.png")
    full.save(p)
    return np.asarray(Image.open(p).convert("RGB"))


def test_end_arc_keeps_a_straight_fill_end_and_measures_an_end_cap(tmp_path):
    """글자 지우기 마감 H4 (나)(사용자 결정 11-19) — 채움 끝은 곧게(G3 호 여백 되돌림 · 근사 gauge_end_shape 없음), 끝 장식 호는 끝 덮개로."""
    ref = _arc_concept(tmp_path, arc=True)
    m = concept_fill.measure(ref, FRAME, BOX, 0.7, end="scale")
    p = m["params"]
    es = m.get("end_cap")
    assert "end_shape" not in p and es and es["depth"] >= 8
    seg = m["texture_size"][0]
    assert m["margin"][2] == round((concept_fill.END_IN + 1) / seg, 4)         # 오른쪽 고정 여백 = 진행 끝 테두리(곧은 끝)
    tex = concept_fill.render(ref, p)
    assert (tex[:, seg - 1, 3] == 255).sum() >= tex.shape[0] - 2               # 끝 열이 줄마다 잘리지 않음(계단 없음)
    zones = state_check.end_shape_zones({"assets": [{"asset_id": "f", "procedural": {**p, "shape": "concept_fill"}}], "widgets": []}, (1080, 1920))
    assert zones == []
    # 끝 덮개 — 호 바깥(맨 윗줄 끝)은 불투명, 가운데 줄 안쪽(빈 트랙 hole)은 투명, 상자 = 트랙 끝 열
    cap = concept_fill.render_end_cap(ref, {**p, "end_cap": es})
    c0, c1 = concept_fill.end_cap_cols(p, es)
    left, top, right, bot = p["track"]
    assert cap.shape[:2] == (bot - top + 1, c1 - c0 + 1) and c1 == right
    assert cap[0, -1, 3] == 255 and cap[(bot - top) // 2, 0, 3] == 0
    box = concept_fill.end_cap_box(p, es)
    assert box[0] == FRAME[0] + c0 and box[2] == c1 - c0 + 1


def test_add_end_cap_puts_one_image_right_after_the_gauge(tmp_path):
    from stages import analyze
    ref = _arc_concept(tmp_path, arc=True)
    m = concept_fill.measure(ref, FRAME, BOX, 0.7, end="scale")
    spec = {"widgets": [{"id": "Root", "type": "CanvasPanel"},
                        {"id": "Area", "type": "Overlay", "parent": "Root", "bbox_intent": FRAME, "slot": {"kind": "canvas"}},
                        {"id": "Gauge", "type": "ProgressBar", "parent": "Area", "bbox_intent": m["widget_box"], "binding": {"kind": "progress"}},
                        {"id": "Label", "type": "TextBlock", "parent": "Area", "bbox_intent": FRAME}], "assets": []}
    w = spec["widgets"][2]
    rec = analyze._add_end_cap(spec, w, spec["widgets"][1], m, set())
    ids = [x["id"] for x in spec["widgets"]]
    assert ids.index("GaugeEndCap") == ids.index("Gauge") + 1 and rec["asset"] == "gauge_end_cap"
    cap = spec["widgets"][ids.index("GaugeEndCap")]
    assert cap["type"] == "Image" and cap["slot"]["kind"] == "overlay" and cap["style"]["brush"]["asset"] == "gauge_end_cap"
    px, py, pw, ph = FRAME
    x, y, bw, bh = cap["bbox_intent"]
    assert cap["slot"]["padding"] == [x - px, y - py, px + pw - x - bw, py + ph - y - bh]
    assert spec["assets"][0]["procedural"]["shape"] == "concept_end_cap"
    w["binding"] = {"kind": "flag"}
    assert "skipped" in analyze._add_end_cap(spec, w, spec["widgets"][1], m, set())


def test_straight_end_keeps_the_old_margin(tmp_path):
    ref = _arc_concept(tmp_path, arc=False)
    m = concept_fill.measure(ref, FRAME, BOX, 0.7, end="scale")
    assert "end_shape" not in m["params"] and m["margin"][2] == round((concept_fill.END_IN + 1) / m["texture_size"][0], 4)
    assert "end_cap" not in m                                                  # 호 없는 곧은 끝 — 덮개 없음


# ---------------------------------------------------------------------------------------------------------------------
# G1 지울 범위 · G2 인페인팅 창

def test_erase_zone_reaches_the_glow_tail_but_keeps_other_glyphs():
    from stages import refine
    spec, boxes, tex, concept, g, panel = _scene("clean")
    cw, aw = concept[..., :3], concept[..., 3] / 255.0
    nc, na = panel[..., :3], panel[..., 3] / 255.0
    narrow = dg._dilate(g, 3)
    own = dg._box_mask((H, W), [88, 38, 66, 64])
    other = np.zeros((H, W), bool)
    other[60:70, 150:156] = True                                               # 이웃 글자 획(지킴)
    new, rec = refine._erase_zone(cw, aw, nc, na, g, narrow, own, 9.0, dg._dilate(other, 2))
    assert rec["erase_added_px"] > 100 and rec["erase_tail"] >= 6
    assert not (new & other).any() and (new & ~narrow).any()


def test_erase_ok_keeps_the_old_fill_when_the_erased_one_scores_worse():
    """글자 지우기 마감 — 게이트와 같은 점수(S4 · 결함 수 · 가는 선 · 밝힌 검정)로 예전 판보다 나빠지면 안 받는다."""
    from stages import refine
    n = {"local": 6.6, "lift": 15.6, "contour": 0, "findings": 1}
    assert refine._erase_ok({"local": 2.2, "lift": 4.0, "contour": 0, "findings": 0}, n)
    assert not refine._erase_ok({"local": 26.9, "lift": 63.9, "contour": 0, "findings": 1}, n)
    clean = {"local": 1.5, "lift": 4.5, "contour": 0, "findings": 0}
    assert refine._erase_ok({"local": 1.6, "lift": 3.4, "contour": 0, "findings": 0}, clean)            # 바닥(3.0) 아래 차이는 같음
    assert not refine._erase_ok({"local": 1.6, "lift": 3.4, "contour": 60, "findings": 0}, clean)       # 가는 선이 새로 생김
    assert not refine._erase_ok({"local": 1.6, "lift": 8.0, "contour": 0, "findings": 0}, clean)        # 밝힌 검정이 나빠짐
    assert not refine._erase_ok(None, clean)


def test_crossing_and_enclosed_masks():
    from stages import refine
    m = np.zeros((40, 60), bool)
    m[20, 5:55] = True                     # 자리를 가로지르는 선
    m[10:13, 28:31] = True                 # 자리 안에 갇힌 점(판이 덜 지운 글자 흔적)
    reach = np.zeros((40, 60), bool)
    reach[5:35, 15:45] = True
    keep = refine._crossing(m, reach)
    assert keep[20, 30] and not keep[11, 29]
    hole = np.zeros((40, 60), bool)
    hole[5:25, 10:30] = True
    hole[12:15, 18:21] = False             # 획 속 · 'ㅇ' 속처럼 갇힌 칠 안 된 픽셀
    filled = refine._fill_enclosed(hole)
    assert filled[13, 19] and not filled[30, 50]


def test_same_hidden_group_erases_banner_texts_only_when_their_texture_hides_too():
    from stages import refine
    spec = {"widgets": [{"id": "Root", "type": "CanvasPanel"},
                        {"id": "Banner", "type": "Border", "parent": "Root", "visibility": "collapsed", "style": {"brush": {"asset": "banner"}}},
                        {"id": "Count", "type": "TextBlock", "parent": "Banner"},
                        {"id": "Plate", "type": "Image", "parent": "Root", "style": {"brush": {"asset": "plate"}}},
                        {"id": "Blocked", "type": "TextBlock", "parent": "Root", "visibility": "collapsed"}], "assets": []}
    assert refine._same_hidden_group(spec, "Count", "banner")
    assert not refine._same_hidden_group(spec, "Blocked", "plate")        # 글자만 숨고 판은 보임('오의 불가') — F1 몫
    assert not refine._same_hidden_group(spec, "Count", "plate")


def test_inpaint_patch_places_the_window_and_returns_none_without_model(monkeypatch):
    full = np.full((300, 420, 3), 80.0)
    full[60:70, 110:130] = 250.0           # 글자(마스크 자리)
    mask = np.zeros((40, 60), bool)
    mask[10:20, 10:30] = True
    seen = {}

    def fake(rgb, m):
        seen["shape"], seen["px"], seen["max_in_mask"] = rgb.shape, int(m.sum()), float(np.asarray(rgb)[m].max())
        out = np.asarray(rgb, np.float32).copy()
        out[m] = 200.0
        return out
    monkeypatch.setattr(inpaint, "run512", fake)
    r = inpaint.patch(full, 100, 50, mask)
    # 작은 텍스처는 거울 채움으로 512 창 — 마스크도 같이 거울(거울에 비친 글자 사본도 가림), 마스크 자리 입력은 지움
    assert seen["shape"] == (512, 512, 3) and seen["px"] >= int(mask.sum()) and seen["max_in_mask"] == 0.0
    assert r.shape == (40, 60, 3) and (r[mask] == 200).all()
    monkeypatch.undo()
    inpaint.configure("work/_models/__missing__.onnx")
    assert inpaint.run512(np.zeros((512, 512, 3)), np.zeros((512, 512), bool)) is None and "missing" in inpaint.status()["error"]
