"""1b 후속 B — 게이지 채움 · 배경을 컨셉에서 결정적으로(derive_gauge_fills) · procedural gradient_bar · 꺼진 flag 초기 접힘 ·
flag 위젯 상자 패널 금지(FLAG_IN_BOX) · 게이지 렌더 지표."""
from __future__ import annotations

import pytest
from conftest import fixture_brief, fixture_spec, widget
from PIL import Image, ImageDraw

from core import schema
from gen import fidelity, procedural
from stages import analyze

BOX = [742, 982, 436, 24]             # 손 spec UltGauge bbox_intent
TOP, BOTTOM, EMPTY = (250, 200, 90), (180, 120, 40), (30, 20, 15)


def concept(tmp_path, percent=0.7):
    im = Image.new("RGB", (1920, 1080), (60, 50, 70))
    d = ImageDraw.Draw(im)
    x, y, w, h = BOX
    split = x + int(round(percent * w))
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=EMPTY)
    d.rectangle([x, y, split - 1, y + h // 2 - 1], fill=TOP)
    d.rectangle([x, y + h // 2, split - 1, y + h - 1], fill=BOTTOM)
    p = tmp_path / "reference.png"
    im.save(p)
    return p


def gauge_spec(with_extract_frame=False):
    spec = analyze.apply_contract(fixture_spec(), fixture_brief())
    if with_extract_frame:
        spec["assets"].append({"asset_id": "ult_gauge_frame", "kind": "frame", "provenance": "codex", "source_mode": "extract", "size": [920, 88],
                               "prompt": "gauge frame", "ref_bbox": [730, 972, 460, 44]})
        i = next(k for k, w in enumerate(spec["widgets"]) if w["id"] == "UltGauge")
        spec["widgets"].insert(i, {"id": "UltGaugeFrame", "type": "Image", "parent": "UltArea", "slot": {"kind": "overlay", "h_align": "fill", "v_align": "fill"},
                                   "bbox_intent": [730, 972, 460, 44], "style": {"brush": {"draw_as": "image", "asset": "ult_gauge_frame"}}})
    return spec


def test_gradient_bar_interpolates_stops_top_to_bottom():
    w, h, rgba = procedural.render({"asset_id": "f", "size": [4, 10], "procedural": {"shape": "gradient_bar", "stops": ["#FF0000FF", "#0000FFFF"]}})
    top, bottom = rgba[0:4], rgba[(9 * 4) * 4:(9 * 4) * 4 + 4]
    assert (w, h) == (4, 10) and top[0] > 230 and top[2] < 25 and bottom[2] > 230 and bottom[0] < 25 and rgba[4:8] == top    # 가로는 같은 색
    with pytest.raises(procedural.ProceduralError):
        procedural.render({"asset_id": "f", "size": [4, 4], "procedural": {"shape": "gradient_bar", "stops": ["#FFFFFFFF"]}})


def test_derive_samples_the_filled_rows_and_the_empty_color(tmp_path):
    spec = gauge_spec()
    recs = analyze.derive_gauge_fills(spec, concept(tmp_path))
    rec = next(r for r in recs if r["widget"] == "UltGauge")
    assert rec["fill_asset"] == "ult_gauge_fill" and rec["stops"] == 24 and rec["background_from"].startswith("concept empty part")
    a = next(x for x in spec["assets"] if x["asset_id"] == "ult_gauge_fill")
    stops = a["procedural"]["stops"]
    assert a["provenance"] == "procedural" and a["size"] == [64, 24] and stops[0] == "#FAC85AFF" and stops[-1] == "#B47828FF"
    st = widget(spec, "UltGauge")["style"]
    assert st["fill"] == {"draw_as": "image", "asset": "ult_gauge_fill"} and st["background"]["color"] == "#1E140FFF" and st["background"]["draw_as"] == "rounded_box"
    assert schema.errors("spec", spec) == []


def test_derive_leaves_the_track_to_an_extracted_frame_underneath(tmp_path):
    spec = gauge_spec(with_extract_frame=True)
    rec = analyze.derive_gauge_fills(spec, concept(tmp_path))[0]
    assert widget(spec, "UltGauge")["style"]["background"] == {"draw_as": "none"} and "UltGaugeFrame" in rec["background_from"]


def test_derive_right_to_left_and_skips(tmp_path):
    spec = gauge_spec()
    st = widget(spec, "UltGauge")["style"]
    st["bar_fill_type"] = "right_to_left"
    rec = analyze.derive_gauge_fills(spec, concept(tmp_path, percent=0.7))[0]
    x, _, w, _ = BOX
    assert rec["sampled"][0] >= x + round(0.3 * w)                      # 오른쪽 70 % 에서 뽑음
    spec2 = gauge_spec()
    widget(spec2, "UltGauge")["style"]["percent"] = 0.02
    assert "too small" in analyze.derive_gauge_fills(spec2, concept(tmp_path))[0]["skipped"]


def test_sample_off_flags_start_collapsed():
    spec = analyze.apply_contract(fixture_spec(), fixture_brief())
    assert widget(spec, "UltReadyGlow")["visibility"] == "collapsed" and widget(spec, "BurstBanner")["visibility"] == "collapsed"
    assert widget(spec, "UltBlockedText")["visibility"] == "collapsed" and "visibility" not in widget(spec, "ChainPanel")     # 샘플 true


def test_flag_widget_inside_a_box_panel_is_rejected():
    spec = analyze.apply_contract(fixture_spec(), fixture_brief())
    assert not [e for e in analyze.check(spec, fixture_brief()) if e.startswith("FLAG_IN_BOX")]
    w = widget(spec, "UltBlockedText")
    w["parent"], w["slot"] = "ChainBox", {"kind": "vertical_box"}
    errs = [e for e in analyze.check(spec, fixture_brief()) if e.startswith("FLAG_IN_BOX")]
    assert len(errs) == 1 and "'UltBlockedText'" in errs[0] and "VerticalBox 'ChainBox'" in errs[0]


# --- 1b 후속 F — 채움 모양을 컨셉에서 그대로(gen/concept_fill) -----------------------------------------------------------------
FRAME = [730, 972, 460, 44]           # gauge_spec(with_extract_frame=True) 의 UltGaugeFrame · UltArea 상자
LINE, TRACK, BAND, RIM = (210, 170, 70), (35, 28, 24), (95, 65, 30), (255, 235, 160)
BODY_TOP, BODY_BOTTOM = (250, 200, 90), (190, 130, 40)
END = 330                             # 컨셉 채움 끝(프레임 상자 기준 x) — 샘플 0.7 보다 조금 길다(실제 컨셉처럼)


def framed_concept(tmp_path, flip=False, name="framed.png"):
    """프레임 선(위 4-5 · 아래 38-39 줄, 왼쪽 '<' 캡 · 오른쪽 세로선 x 440) + 어두운 트랙 + '<' 끝 몸통(줄 10 ~ 33, 1 px 밝은 테두리) +
    몸통 쪽 띠(줄 6-9 · 34-37)만 밝음 + 진행 끝 뒤 10 px 번짐. flip 이면 프레임 상자 안에서 좌우를 뒤집는다(right_to_left)."""
    ox, oy, ow, oh = FRAME
    im = Image.new("RGB", (ow, oh), (40, 34, 44))
    d = ImageDraw.Draw(im)
    d.rectangle([10, 6, 439, 37], fill=TRACK)
    d.rectangle([20, 6, END, 9], fill=BAND)
    d.rectangle([20, 34, END, 37], fill=BAND)
    for k in range(1, 11):                                    # 번짐 — 알파 0.4 → 0
        a = 0.4 * (1 - k / 11)
        d.line([(END + k, 6), (END + k, 37)], fill=tuple(int(t + a * (f - t)) for t, f in zip(TRACK, BODY_BOTTOM)))
    for y in range(10, 34):                                   # 몸통 — 위 → 아래 그라데이션, 왼쪽 끝 '<'
        t = (y - 10) / 23
        c = tuple(int(a + (b - a) * t) for a, b in zip(BODY_TOP, BODY_BOTTOM))
        x0 = 24 + int(round(abs(y - 21.5) * 8 / 11.5))
        d.line([(x0, y), (END, y)], fill=c)
        d.point((x0, y), fill=RIM)
    d.line([(32, 10), (END, 10)], fill=RIM)
    d.line([(32, 33), (END, 33)], fill=RIM)
    d.line([(END, 10), (END, 33)], fill=RIM)
    d.rectangle([20, 4, 440, 5], fill=LINE)
    d.rectangle([20, 38, 440, 39], fill=LINE)
    d.line([(20, 4), (8, 22), (20, 39)], fill=LINE, width=2)
    d.rectangle([440, 4, 441, 39], fill=LINE)
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    full = Image.new("RGB", (1920, 1080), (60, 50, 70))
    full.paste(im, (ox, oy))
    p = tmp_path / name
    full.save(p)
    return p


def _ref(path):
    import numpy as np
    return np.asarray(Image.open(path).convert("RGB"))


def test_concept_fill_measures_the_track_and_draws_the_shape(tmp_path):
    from gen import concept_fill
    ref = _ref(framed_concept(tmp_path))
    m = concept_fill.measure(ref, FRAME, BOX, 0.7, end="scale")
    p = m["params"]
    left, top, right, bot = p["track"]
    assert (top, bot, right) == (6, 37, 439) and p["body_end"] == END and 18 <= left <= 20 and 8 <= p["spill"] <= 10
    assert m["record"]["band"] == [4, 4] and abs(m["record"]["concept_percent"] - (END - left + 1) / (right - left + 1)) < 1e-3
    x, y, w, h = m["widget_box"]
    assert (x, y, h) == (FRAME[0] + left, FRAME[1] + 6, 32) and w == right - left + 1 + p["spill"]
    # 1b 후속 J — 채움 텍스처 = 컨셉의 채워진 구간(왼쪽 끝 ~ 진행 끝 + 번짐) 그대로, 양끝 margin 은 그 폭 기준, 미리보기 진행률 = 구간 ÷ 막대 폭
    seg = END - left + 1 + p["spill"]
    assert p["texture"] == "concept" and m["texture_size"] == [seg, 32] and m["percent"] == round(seg / w, 4)
    assert m["margin"][0] == round(p["lead"] / seg, 4) and m["margin"][2] == round((p["end_in"] + p["spill"] + 1) / seg, 4)
    tex = concept_fill.render(ref, p)
    assert tex.shape == (32, seg, 4)
    crop = ref[FRAME[1] + 6:FRAME[1] + 38, FRAME[0] + left:FRAME[0] + left + seg].astype(float)
    mid = 120 - left
    assert tex[16, mid, 3] == 255 and (tex[16, mid, :3] == crop[16, mid]).all()          # 몸통 = 컨셉 픽셀 그대로
    assert tex[1, mid, 3] == 255 and (tex[1, mid, :3] == crop[1, mid]).all()             # 위 띠(밝아진 트랙)까지
    assert tex[16, 26 - left, 3] == 255 and tex[16, 26 - left, 0] > 200                  # '<' 끝 안쪽 몸통
    assert tex[16, seg - 1, 3] == 255 and (tex[16, seg - 1, :3] == crop[16, seg - 1]).all()   # 번짐 끝까지 컨셉 픽셀(아래 판은 빈 트랙)
    w2, h2, raw = concept_fill.render_bytes(tmp_path / "framed.png", p)
    assert (w2, h2) == (seg, 32) and raw == concept_fill.render_bytes(tmp_path / "framed.png", p)[2]      # 같은 값 → 같은 바이트
    old = {k: v for k, v in p.items() if k != "texture"}                                 # 예전 spec(texture 없음)은 예전 그림
    assert concept_fill.render(ref, old).shape == (32, w, 4)


def test_concept_fill_full_bar_takes_the_whole_track_with_both_end_shapes(tmp_path):
    """1b 후속 J — 가득 찬 게이지(1.0): 빈 부분 없이 둘레 어두운 띠로 문턱 → 트랙 전체 1:1 조각, 양끝 모양(lead · rlead) 고정 margin, 미리보기 1.0.
    둘레에 밝은 선이 없으면 막대 자체가 트랙(파티 HUD — 프레임 상자가 막대 위 5 px 에서 끊겨도 FULL_PAD 로 넓혀 잰다)."""
    import numpy as np
    from gen import concept_fill
    ox, oy, ow, oh = 600, 180, 920, 38
    im = Image.new("RGB", (1920, 1080), (8, 10, 14))
    d = ImageDraw.Draw(im)
    for y in range(185, 214):                                      # 화살 '<' '>' 양끝 막대, 위 · 아래 밝은 테두리
        k = round(abs(y - 199) * 18 / 14)
        d.line([(625 + k, y), (1527 - k, y)], fill=(170, 245, 75) if y < 199 else (70, 225, 40))
    d.line([(643, 185), (1509, 185)], fill=(220, 255, 210))
    d.line([(643, 213), (1509, 213)], fill=(220, 255, 210))
    p = tmp_path / "full.png"
    im.save(p)
    ref = _ref(p)
    m = concept_fill.measure(ref, [ox, oy, ow, oh], [634, 186, 884, 26], 1.0, end="scale")
    pr = m["params"]
    x, y, w, h = m["widget_box"]
    assert pr["full"] and m["percent"] == 1.0 and m["record"]["track_from"].startswith("body rows")
    assert abs(x - 624) <= 1 and abs(y - 185) <= 1 and abs((x + w) - 1529) <= 1 and abs((y + h) - 214) <= 1
    assert 10 <= pr["lead"] <= 40 and 10 <= pr["rlead"] <= 40 and m["margin"] == [round(pr["lead"] / w, 4), 0.0, round(pr["rlead"] / w, 4), 0.0]
    tex = concept_fill.render(ref, pr)
    assert tex.shape == (h, w, 4) and (tex[..., 3] == 255).mean() > 0.95                  # 트랙 전체를 덮는다(아래 판 = 빈 트랙)
    crop = ref[y:y + h, x:x + w].astype(float)
    assert np.abs(tex[..., :3] - crop).max() < 1                                           # 컨셉 픽셀 그대로(화살 끝 포함)
    hole, _ = concept_fill.track_hole(ref, pr)
    assert hole.sum() == (tex[..., 3] > 0).sum()
    with pytest.raises(concept_fill.ConceptFillError):
        concept_fill.unfilled_track(ref, pr)                                                # 빈 트랙 색은 못 뽑음 — 판은 요소 없는 판으로


def test_derive_shape_mode_puts_the_bar_on_the_measured_track(tmp_path):
    from core import spec as spec_mod
    ref = framed_concept(tmp_path)
    spec = gauge_spec(with_extract_frame=True)
    rec = next(r for r in analyze.derive_gauge_fills(spec, ref, {"mode": "shape", "end": "scale"}) if r["widget"] == "UltGauge")
    g = widget(spec, "UltGauge")
    a = next(x for x in spec["assets"] if x["asset_id"] == rec["fill_asset"])
    x, y, w, h = rec["widget_box"]
    assert rec["shape"] == "concept_fill" and g["bbox_intent"] == [x, y, w, h] and rec["old_bbox"] == BOX
    assert g["slot"]["padding"] == [x - FRAME[0], 6, FRAME[0] + FRAME[2] - x - w, 6] and g["slot"]["h_align"] == "fill"
    assert g["style"]["bar_fill_style"] == "scale" and g["style"]["fill"]["draw_as"] == "box" and g["style"]["fill"]["margin"] == a["margin"]
    assert g["style"]["background"] == {"draw_as": "none"} and a["nine_slice"] is True and a["size"][1] == h
    # 1b 후속 J — 텍스처 = 컨셉 채움 구간 폭, 미리보기 진행률 = 그 폭 ÷ 막대 폭(입력 sample 은 기록)
    assert g["style"]["percent"] == rec["preview_percent"] and abs(a["size"][0] - g["style"]["percent"] * w) < 1 and rec["sample_percent"] == 0.7
    assert a["procedural"]["shape"] == "concept_fill" and a["source"].startswith("concept fill")
    assert schema.errors("spec", spec) == [] and spec_mod.validate_semantics(spec) == []
    assert procedural.render(a, reference=ref)[:2] == tuple(a["size"])
    with pytest.raises(procedural.ProceduralError):
        procedural.render(a)                                    # reference 없으면 못 그린다
    norm = spec_mod.normalize(spec)
    assert spec_mod.widget_index(norm)["UltGauge"]["style"]["bar_fill_style"] == "scale"


def test_derive_shape_mask_end_and_fallback(tmp_path):
    ref = framed_concept(tmp_path)
    spec = gauge_spec(with_extract_frame=True)
    rec = analyze.derive_gauge_fills(spec, ref, {"mode": "shape", "end": "mask"})[0]
    g = widget(spec, "UltGauge")
    assert g["style"]["fill"]["draw_as"] == "image" and "bar_fill_style" not in g["style"] and rec["spill"] == 0
    assert rec["widget_box"][2] == g["bbox_intent"][2] and "margin" not in next(x for x in spec["assets"] if x["asset_id"] == rec["fill_asset"])
    # 프레임 선이 없는 컨셉(B 의 합성 그림) — 트랙을 못 재 B 방식으로 물러난다
    spec2 = gauge_spec(with_extract_frame=True)
    rec2 = analyze.derive_gauge_fills(spec2, concept(tmp_path), {"mode": "shape"})[0]
    assert "frame line" in rec2["shape_fallback"] and rec2["stops"] and widget(spec2, "UltGauge")["style"]["fill"]["draw_as"] == "image"
    # mode stops = 예전(B) 그대로
    spec3 = gauge_spec(with_extract_frame=True)
    rec3 = analyze.derive_gauge_fills(spec3, ref, {"mode": "stops"})[0]
    assert "shape" not in rec3 and "shape_fallback" not in rec3 and rec3["stops"]


def test_derive_shape_right_to_left_mirrors(tmp_path):
    from gen import concept_fill
    ref = framed_concept(tmp_path, flip=True, name="flipped.png")
    spec = gauge_spec(with_extract_frame=True)
    g = widget(spec, "UltGauge")
    g["style"]["bar_fill_type"] = "right_to_left"
    g["bbox_intent"] = [FRAME[0] + FRAME[2] - (BOX[0] - FRAME[0]) - BOX[2], BOX[1], BOX[2], BOX[3]]
    rec = analyze.derive_gauge_fills(spec, ref, {"mode": "shape", "end": "scale"})[0]
    straight = concept_fill.measure(_ref(framed_concept(tmp_path)), FRAME, BOX, 0.7, end="scale")
    x, y, w, h = rec["widget_box"]
    sx, _, sw, _ = straight["widget_box"]
    assert (w, h) == (sw, straight["widget_box"][3]) and x == FRAME[0] + FRAME[2] - (sx - FRAME[0]) - sw
    m = g["style"]["fill"]["margin"]
    assert m[0] == straight["margin"][2] and m[2] == straight["margin"][0]          # 왼쪽 끝 모양이 오른쪽 여백으로
    a = next(x for x in spec["assets"] if x["asset_id"] == rec["fill_asset"])
    tex = concept_fill.render(_ref(ref), a["procedural"])
    flat = concept_fill.render(_ref(framed_concept(tmp_path)), straight["params"])
    assert (tex[:, ::-1] == flat).all()


def test_unfilled_track_paints_the_baked_fill_with_the_empty_track(tmp_path):
    """1b 후속 G2 — 게이지 프레임 옮겨 심기: 트랙 전체(채움 · 띠 · 번짐 포함)를 줄마다 빈 트랙 색으로, 프레임 선 · '<' 캡은 그대로."""
    import numpy as np
    from gen import concept_fill
    ox, oy, ow, oh = FRAME
    for flip in (False, True):
        ref = _ref(framed_concept(tmp_path, flip=flip, name=f"framed_{flip}.png"))
        bar = [ox + ow - (BOX[0] - ox) - BOX[2], BOX[1], BOX[2], BOX[3]] if flip else BOX
        p = concept_fill.measure(ref, FRAME, bar, 0.7, "right_to_left" if flip else "left_to_right", end="scale")["params"]
        hole, out = concept_fill.unfilled_track(ref, p)
        crop = ref[oy:oy + oh, ox:ox + ow].astype(float)
        X = (lambda x: ow - 1 - x) if flip else (lambda x: x)      # noqa: E731
        for x, y in ((120, 20), (120, 7), (120, 36), (END + 5, 20), (40, 21), (25, 7), (400, 20)):   # 몸통 · 띠 · 번짐 · '<' 안쪽 · 빈 트랙
            assert hole[y, X(x)] and np.abs(out[y, X(x)] - np.array(TRACK)).max() <= 2, (flip, x, y)
        for x, y in ((120, 4), (120, 39), (9, 21), (441, 20)):     # 위 · 아래 프레임 선 · '<' 캡 · 오른쪽 세로선
            assert not hole[y, X(x)] and (out[y, X(x)] == crop[y, X(x)]).all(), (flip, x, y)


def test_hidden_codex_glow_becomes_a_procedural_soft_glow(tmp_path):
    """1b 후속 G2 — 컨셉에 안 보이는 빛을 codex 로 새로 그리면 run 마다 다르다 [실측 G 크기 끝 run 2] → procedural soft_glow(색 = 그 자리 컨셉)."""
    ref = concept(tmp_path)
    spec, brief = gauge_spec(), fixture_brief()
    glow_w = widget(spec, "UltReadyGlow")
    aid = glow_w["style"]["brush"]["asset"]
    spec["assets"] = [a for a in spec["assets"] if a["asset_id"] != aid] + [
        {"asset_id": aid, "kind": "ornament", "provenance": "codex", "source_mode": "generate", "size": [1024, 106], "ref_bbox": BOX,
         "prompt": "a soft warm golden horizontal glow halo, no text"}]
    recs = analyze.derive_hidden_glows(spec, brief, ref)
    a = next(x for x in spec["assets"] if x["asset_id"] == aid)
    assert [r["asset"] for r in recs] == [aid] and a["provenance"] == "procedural" and "prompt" not in a and "source_mode" not in a
    p = a["procedural"]
    assert p["shape"] == "soft_glow" and p["falloff"] == 0.6 and p["color"].endswith("CC") and a["size"] == [round(glow_w["bbox_intent"][2]), round(glow_w["bbox_intent"][3])]
    r, g, b = (int(p["color"][i:i + 2], 16) for i in (1, 3, 5))
    assert r > g > b and r >= 180                                                   # 채움 금색(TOP · BOTTOM 쪽)
    schema.require("spec", spec)                                                    # 스키마에 맞는 procedural 에셋
    # LLM 이 procedural soft_glow 를 골라도 같은 값으로(알파 · 색이 run 마다 달랐다 — [실측 G2] #FFC45A 알파 1.0)
    spec3 = gauge_spec()
    spec3["assets"] = [x for x in spec3["assets"] if x["asset_id"] != aid] + [
        {"asset_id": aid, "kind": "ornament", "provenance": "procedural", "size": [800, 60], "procedural": {"shape": "soft_glow", "color": "#FFC45A", "falloff": 0.5}}]
    analyze.derive_hidden_glows(spec3, brief, ref)
    assert next(x for x in spec3["assets"] if x["asset_id"] == aid)["procedural"] == p
    # 빛이 아닌 숨은 이미지 · 아이콘은 그대로
    spec2 = gauge_spec()
    spec2["assets"] = [x for x in spec2["assets"] if x["asset_id"] != aid] + [
        {"asset_id": aid, "kind": "icon", "provenance": "codex", "source_mode": "generate", "size": [64, 64], "prompt": "a glowing star icon"}]
    assert analyze.derive_hidden_glows(spec2, brief, ref) == []


def test_gauge_shape_metric(tmp_path):
    ref = framed_concept(tmp_path)
    box = [FRAME[0] + 19, FRAME[1] + 6, 421, 32]
    same = fidelity.gauge_shape(ref, ref, box, 0.7)
    assert same["iou"] == 1.0 and same["tip_dx"] == 0 and same["rows_concept"] == same["rows_render"]
    flat = Image.open(ref).convert("RGB")
    ImageDraw.Draw(flat).rectangle([BOX[0], BOX[1], BOX[0] + int(0.7 * BOX[2]), BOX[1] + BOX[3] - 1], fill=(242, 181, 68))   # B 의 사각 채움
    p = tmp_path / "rect.png"
    flat.save(p)
    got = fidelity.gauge_shape(ref, p, box, 0.7)
    assert got["iou"] < 0.97 and got["tip_dx"] != 0


def test_check_rejects_llm_concept_fill_and_glow_outline_clash():
    from core import spec as spec_mod
    spec = gauge_spec()
    spec["assets"].append({"asset_id": "x_fill", "kind": "fill", "provenance": "procedural", "size": [8, 8], "procedural": {"shape": "concept_fill"}})
    widget(spec, "UltGauge")["style"]["fill"] = {"draw_as": "image", "asset": "x_fill"}
    assert [e for e in analyze.check(spec, fixture_brief()) if "concept_fill is made by the pipeline" in e]
    t = next(w for w in spec["widgets"] if w["type"] == "TextBlock")
    t["font"] = {**(t.get("font") or {}), "glow": {"size": 6, "color": "#FFB04880"}, "outline": {"size": 2, "color": "#000000FF"}}
    assert [e for e in spec_mod.validate_semantics(spec) if e.startswith("FONT_GLOW_OUTLINE")]
    f = spec_mod.normalize_font_effects({"glow": {"size": 0, "color": "#FFFFFFFF"}})
    assert "glow" not in f and spec_mod.normalize_font_effects({"glow": {"size": 4}})["glow"] == {"color": "#FFFFFFFF", "size": 4}


def test_gauge_vs_concept_rows(tmp_path):
    ref = concept(tmp_path)
    same = fidelity.gauge_vs_concept(ref, ref, BOX, 0.7)
    assert same["filled"]["rows"]["mean"] == 0.0 and same["empty"]["representative"] == 0.0
    flat = Image.open(ref).convert("RGB")
    ImageDraw.Draw(flat).rectangle([BOX[0], BOX[1], BOX[0] + int(0.7 * BOX[2]) - 1, BOX[1] + BOX[3] - 1], fill=(242, 181, 68))     # 단색 채움
    p = tmp_path / "flat.png"
    flat.save(p)
    assert fidelity.gauge_vs_concept(ref, p, BOX, 0.7)["filled"]["rows"]["max"] > 8
