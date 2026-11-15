"""1b 후속 D — 역할별 폰트(font.role → family) · 글자 효과 어휘(outline · shadow · letter_spacing · gradient) 정규화 ·
글자색 · 세로 그라데이션을 컨셉에서 결정적으로(derive_text_fills) · fix 프롬프트 줄 높이 표."""
from __future__ import annotations

import copy

from conftest import fixture_brief, fixture_spec, widget
from PIL import Image, ImageDraw

from core import config, schema
from core import spec as spec_mod
from gen import fidelity
from stages import analyze, fix

TITLE = "/Game/UI/Fonts/NotoSerifKR/F_NotoSerifKR.F_NotoSerifKR"
BODY = "/Game/UI/Fonts/Pretendard/F_Pretendard.F_Pretendard"
CFG = {"fonts": {"default_family": BODY, "line_height": {16: 26, 30: 49},
                 "roles": {"title": {"family": TITLE, "line_height": {16: 31, 30: 57}}}}}


def test_font_roles_from_config():
    roles = config.font_roles(CFG)
    assert roles["body"]["family"] == BODY and roles["title"]["family"] == TITLE and roles["title"]["line_height"][30] == 57
    assert config.font_roles(CFG, "/Game/Other.Other")["body"]["family"] == "/Game/Other.Other"     # 요청 폰트가 body 를 덮는다
    assert "title" not in config.font_roles({"fonts": {"default_family": BODY, "roles": {"title": {"family": None}}}})
    assert config.line_height_text({30: 49, 16: 26}) == "16→26, 30→49"


def test_apply_contract_maps_roles_to_families_and_drops_role():
    raw = fixture_spec()
    widget(raw, "BurstLabelText")["font"]["role"] = "title"
    widget(raw, "ChainCountText")["font"]["role"] = "body"
    widget(raw, "ChainTimerText")["font"]["role"] = "nope"          # 모르는 역할 → body
    for w in raw["widgets"]:
        if w["type"] == "TextBlock":
            w["font"].pop("family", None)
    spec = analyze.apply_contract(raw, fixture_brief(), config.font_roles(CFG))
    assert widget(spec, "BurstLabelText")["font"]["family"] == TITLE
    assert widget(spec, "ChainCountText")["font"]["family"] == BODY and widget(spec, "ChainTimerText")["font"]["family"] == BODY
    assert not any("role" in (w.get("font") or {}) for w in spec["widgets"])
    assert schema.errors("spec", spec) == [] and not [e for e in spec_mod.validate_semantics(spec) if e.startswith("FONT_ROLE")]


def test_unresolved_role_is_a_semantic_error():
    spec = fixture_spec()
    widget(spec, "BurstLabelText")["font"]["role"] = "title"
    assert any(e.startswith("FONT_ROLE: 'BurstLabelText'") for e in spec_mod.validate_semantics(spec))


def test_prompt_lists_font_roles_with_line_heights():
    text = analyze.font_lines(CFG, {"font": None})
    assert "`body` = F_Pretendard" in text and "`title` = F_NotoSerifKR" in text and "30→57" in text and "omit font.family" in text
    assert "glyph height" in text and "line box" in text
    assert "engine default" in analyze.font_lines({"fonts": {}}, {"font": None})


def test_effects_normalize_away_when_default_and_keep_otherwise():
    f = spec_mod.normalize_font_effects({"size": 20, "letter_spacing": 0, "outline": {"size": 0, "color": "#FF0000"},
                                         "shadow": {"offset": [2, 2], "color": "#00000000"}})
    assert set(f) == {"size"}
    f = spec_mod.normalize_font_effects(spec_mod._canon({"letter_spacing": 80, "outline": {"size": 2}, "shadow": {"color": "#000000b0"},
                                                         "gradient": {"top_color": "#ffe9a8", "bottom_color": "#C8902E"}}))
    assert f["outline"] == {"size": 2, "color": "#000000FF"} and f["shadow"] == {"offset": [1, 1], "color": "#000000B0"}
    assert f["letter_spacing"] == 80 and f["gradient"] == {"top_color": "#FFE9A8FF", "bottom_color": "#C8902EFF"}


def test_roundtrip_view_carries_effects_and_old_specs_are_unchanged():
    spec = fixture_spec()
    before = spec_mod.roundtrip_view(spec)
    assert not any(k in widget(before, "BurstLabelText")["font"] for k in spec_mod.FONT_EFFECT_KEYS)     # 효과 없는 spec 의 정규형은 예전 그대로
    spec2 = copy.deepcopy(spec)
    widget(spec2, "BurstLabelText")["font"].update(outline={"size": 2, "color": "#1A0E05"}, letter_spacing=60)
    after = spec_mod.roundtrip_view(spec2)
    assert widget(after, "BurstLabelText")["font"]["outline"] == {"size": 2, "color": "#1A0E05FF"}
    assert schema.errors("spec", spec2) == []


def _concept(tmp_path, top, bottom, box=(780, 111, 240, 42), bg=(25, 15, 10)):
    """어두운 바탕에 세로 그라데이션 획 4개 — 글자 대역."""
    im = Image.new("RGB", (1920, 1080), bg)
    px = im.load()
    x, y, w, h = box
    for k in range(4):
        sx = x + 20 + k * 50
        for yy in range(y + 6, y + h - 6):
            a = (yy - (y + 6)) / max(1, (h - 13))
            c = tuple(int(round(top[i] + (bottom[i] - top[i]) * a)) for i in range(3))
            for xx in range(sx, sx + 8):
                px[xx, yy] = c
    p = tmp_path / "reference.png"
    im.save(p)
    return p


# --- 1b 후속 F — 글자 빛(derive_text_glow) · 외형 라운드 글자 상자 따라가기 --------------------------------------------------------
TITLE_SDF = "/Game/UI/Fonts/NotoSerifKR/F_NotoSerifKR_SDF.F_NotoSerifKR_SDF"


def _glow_concept(tmp_path, halo=True, box=(780, 111, 240, 42), name="glow.png"):
    """어두운 보라 바탕에 크림색 획 4개 + (halo) 획 둘레 8 px 로 사라지는 주황 빛 — '4.2' 처럼."""
    import cv2
    import numpy as np
    img = np.zeros((1080, 1920, 3), float) + np.array([28, 20, 32])
    m = np.zeros((1080, 1920), np.uint8)
    x, y, w, h = box
    for k in range(4):
        m[y + 6:y + h - 6, x + 20 + k * 50:x + 28 + k * 50] = 1
    if halo:
        d = cv2.distanceTransform((1 - m).astype(np.uint8), cv2.DIST_L2, 5)
        a = np.where((d > 0) & (d < 8), 0.35 * np.clip(1 - d / 8, 0, 1) ** 1.5, 0.0)[..., None]
        img = img * (1 - a) + np.array([255, 140, 20]) * a
    img[m.astype(bool)] = (245, 232, 200)
    p = tmp_path / name
    Image.fromarray(img.round().astype(np.uint8)).save(p)
    return p


def _glow_cfg(sdf=True):
    cfg = copy.deepcopy(CFG)
    if sdf:
        cfg["fonts"]["roles"]["title"]["sdf_family"] = TITLE_SDF
    return cfg


def test_derive_text_glow_finds_a_soft_glow_and_switches_to_the_sdf_font(tmp_path):
    cfg = _glow_cfg()
    spec = analyze.apply_contract(fixture_spec(), fixture_brief(), config.font_roles(cfg))
    t = widget(spec, "BurstLabelText")
    t["font"].update(family=TITLE, outline={"size": 2, "color": "#000000FF"})
    t["slot"] = {"kind": "horizontal_box", "padding": [4, 0, 4, 0]}
    old_box = list(t["bbox_intent"])
    recs = analyze.derive_text_glow(spec, _glow_concept(tmp_path), config.font_roles(cfg), 8.0)
    rec = next(r for r in recs if r["widget"] == "BurstLabelText")
    g = t["font"]["glow"]
    s = g["size"]
    # 빛(외곽선 층)은 상자를 사방 s 키운다 — 글자가 제자리에 있게 bbox_intent 를 넓히고 padding 을 줄인다(형제 자리 그대로)
    assert t["bbox_intent"] == [old_box[0] - s, old_box[1] - s, old_box[2] + 2 * s, old_box[3] + 2 * s]
    assert t["slot"]["padding"] == [4 - s, -s, 4 - s, -s] and rec["layout"]["how"] == "slot padding"
    r, gg, b = (int(g["color"][i:i + 2], 16) for i in (1, 3, 5))
    assert 6 <= g["size"] <= 10 and r > gg > b and 0.15 <= int(g["color"][7:9], 16) / 255 <= 1.0 and rec["peak"] >= 8
    assert t["font"]["family"] == TITLE_SDF and "outline" not in t["font"] and rec["outline_dropped"]["size"] == 2
    assert schema.errors("spec", spec) == [] and not [e for e in spec_mod.validate_semantics(spec) if e.startswith("FONT_GLOW")]
    assert "SDF" in fix._line_height_note({**cfg}, spec) or TITLE_SDF in fix._line_height_note(cfg, spec)


def test_derive_text_glow_none_without_a_halo_or_an_sdf_font(tmp_path):
    cfg = _glow_cfg()
    spec = analyze.apply_contract(fixture_spec(), fixture_brief(), config.font_roles(cfg))
    t = widget(spec, "BurstLabelText")
    t["font"].update(family=TITLE, glow={"size": 5, "color": "#FFFFFF80"})          # LLM 이 넣은 빛은 쓰지 않는다
    rec = next(r for r in analyze.derive_text_glow(spec, _glow_concept(tmp_path, halo=False), config.font_roles(cfg), 8.0) if r["widget"] == "BurstLabelText")
    assert rec["glow"] is None and rec["llm_glow_dropped"]["size"] == 5 and "glow" not in t["font"] and t["font"]["family"] == TITLE
    spec2 = analyze.apply_contract(fixture_spec(), fixture_brief(), config.font_roles(CFG))
    widget(spec2, "BurstLabelText")["font"]["family"] = TITLE
    rec2 = next(r for r in analyze.derive_text_glow(spec2, _glow_concept(tmp_path, name="g2.png"), config.font_roles(CFG), 8.0) if r["widget"] == "BurstLabelText")
    assert "no SDF font" in rec2["skipped"] and "glow" not in widget(spec2, "BurstLabelText")["font"]


def test_style_round_text_box_follows_the_font_size():
    from stages import style
    before = analyze.apply_contract(fixture_spec(), fixture_brief())
    t0 = widget(before, "BurstLabelText")
    t0["font"].update(family=TITLE, size=30)
    t0["bbox_intent"] = [780, 111, 240, 60]

    def shrink(slot, rendered=None):
        t0["slot"] = slot
        after = copy.deepcopy(before)
        widget(after, "BurstLabelText")["font"]["size"] = 16
        recs = style.follow_text_boxes(before, after, CFG, rendered)
        return recs, widget(after, "BurstLabelText")["bbox_intent"], widget(after, "BurstLabelText")["slot"]
    dw, dh = 240 * (16 / 30 - 1), 60 * (31 / 57 - 1)              # 줄어드는 폭 · 높이(음수)
    recs, (x, y, w, h), slot = shrink({"kind": "overlay", "h_align": "center", "v_align": "top"})       # 두 축 다 글자가 길이를 정함
    assert len(recs) == 1 and recs[0]["line_height"] == [57.0, 31.0] and recs[0]["from"] == "bbox_intent"
    assert abs(w - (240 + dw)) < 0.11 and abs(h - (60 + dh)) < 0.11 and abs(x + w / 2 - 900) < 0.11 and abs(y + h / 2 - 141) < 0.11   # 가운데 그대로
    assert all(abs(a - b) < 0.11 for a, b in zip(slot["padding"], [-dw / 2, -dh / 2, -dw / 2, -dh / 2]))    # 슬롯이 차지하는 자리 그대로
    # 캔버스 고정 크기 — 상자 크기는 그대로, 글자는 위쪽 기준이라 줄 높이 변화의 절반만큼 옮겨 가운데 유지(줄면 아래로 13)
    recs, box, slot = shrink({"kind": "canvas", "position": [780, 111], "size": [240, 60]})
    assert box == [780, 124.0, 240, 60] and slot["position"] == [780, 124.0] and "fixes this text's box size" in recs[0]["skipped"]
    # 세로 채움 · 가로 채움(overlay fill) — 위 padding 으로 가운데 유지
    recs, box, slot = shrink({"kind": "overlay", "h_align": "fill", "v_align": "fill", "padding": [0, 40, 0, 0]})
    assert slot["padding"] == [0, 53.0, 0, 0] and box == [780, 124.0, 240, 47.0] and recs[0]["shift_up"]["by"] == -13.0
    recs, (x, y, w, h), slot = shrink({"kind": "horizontal_box", "size_rule": "fill", "v_align": "top"})  # 가로 채움 — 세로만
    assert (x, w) == (780, 240) and abs(y + h / 2 - 141) < 0.11 and slot["padding"][0] == 0 and abs(slot["padding"][1] + dh / 2) < 0.11
    recs, (x, y, w, h), slot = shrink({"kind": "canvas", "auto_size": True, "alignment": [1, 0], "position": [1020, 111]})
    assert abs(slot["position"][0] - (1020 + dw * 0.5)) < 0.11 and abs(slot["position"][1] - (111 - dh * 0.5)) < 0.11 and abs(x + w - slot["position"][0]) < 0.11
    # 직전 통과 렌더 상자가 있으면 그것을 기준으로(analyze 상자가 글자보다 넓을 때 — 실측 F 끝 run 2 체인 제목 104 vs 57 px)
    recs, (x, y, w, h), _ = shrink({"kind": "overlay", "h_align": "center", "v_align": "top"}, {"BurstLabelText": [860, 115, 80, 56]})
    assert recs[0]["from"] == "render" and abs(w - 80 * 16 / 30) < 0.11 and abs(x + w / 2 - 900) < 0.11 and abs(h - 56 * 31 / 57) < 0.11
    # 자간 · 외곽선만 바뀌어도(크기 그대로) — [실측 F 끝 run 3] 자간 133 → 280 · 크기 38 · '체인 버스트' 6 글자 → 폭 +25
    t0["font"].update(size=38, letter_spacing=133)
    t0["text"] = {"source": "static", "value": "체인 버스트"}
    t0["slot"] = {"kind": "horizontal_box", "size_rule": "auto", "v_align": "center", "padding": [0, 0, 0, 0]}
    after = copy.deepcopy(before)
    widget(after, "BurstLabelText")["font"].update(letter_spacing=280, outline={"size": 2, "color": "#000000FF"})
    recs = style.follow_text_boxes(before, after, CFG, {"BurstLabelText": [783.5, 134.5, 284, 75]})
    a = widget(after, "BurstLabelText")
    assert recs[0]["letter_spacing_px"] == [5, 10] and recs[0]["grow"] == [25.0 + 4, 4.0]
    assert a["slot"]["padding"] == [-14.5, -2.0, -14.5, -2.0] and a["bbox_intent"] == [769.0, 132.5, 313.0, 79.0]
    assert style.follow_text_boxes(before, copy.deepcopy(before), CFG) == []                 # 크기 · 폰트 그대로면 안 바꾼다
    assert style._line_height(_glow_cfg(), TITLE_SDF, 30) == 57.0                            # SDF 사본은 같은 줄 높이 표


def test_text_ink_drops_tall_thin_frame_lines():
    """1b 후속 F [실측 끝 run 3] — 넓은 글자 상자에 걸친 패널 세로선(상자 높이 전체 · 가늘다)은 획이 아니다."""
    import numpy as np
    a = np.zeros((60, 200, 3)) + 30
    a[18:42, 80:86] = 230                      # 획 둘(줄 상자의 40 %)
    a[18:42, 110:116] = 230
    a[:, 3:5] = 220                            # 세로 테두리선 — 가장자리에 닿지 않음
    a[:, 193:195] = 220
    box = fidelity.ink_box(fidelity.text_ink(a))
    assert box[0] >= 78 and box[0] + box[2] <= 118 and box[3] <= 26


def test_derive_text_fills_finds_a_vertical_gradient(tmp_path):
    spec = analyze.apply_contract(fixture_spec(), fixture_brief())
    widget(spec, "BurstLabelText")["font"]["color"] = "#FFFFFFCC"
    recs = analyze.derive_text_fills(spec, _concept(tmp_path, (255, 236, 170), (190, 130, 40)))
    rec = next(r for r in recs if r["widget"] == "BurstLabelText")
    f = widget(spec, "BurstLabelText")["font"]
    assert rec["top_bottom_de00"] >= analyze.TEXT_GRADIENT_MIN_DE and f["color"] == "#FFFFFFCC"      # 틴트 없음 · 알파 유지
    top, bottom = spec_mod.parse_color(f["gradient"]["top_color"]), spec_mod.parse_color(f["gradient"]["bottom_color"])
    assert top[0] > 240 and top[2] > 140 and bottom[2] < 80
    assert schema.errors("spec", spec) == []


def test_derive_text_fills_solid_color_and_skips_empty_boxes(tmp_path):
    spec = analyze.apply_contract(fixture_spec(), fixture_brief())
    widget(spec, "BurstLabelText")["font"]["gradient"] = {"top_color": "#FFFFFF", "bottom_color": "#000000"}
    recs = analyze.derive_text_fills(spec, _concept(tmp_path, (230, 60, 40), (230, 60, 40)))
    f = widget(spec, "BurstLabelText")["font"]
    assert "gradient" not in f and f["color"].startswith("#E63C28")
    other = next(r for r in recs if r["widget"] == "ChainTitleText")
    assert other.get("skipped") == "no glyph pixels found"           # 그 상자에는 획이 없다(한 색 바탕)


def test_text_ink_takes_the_minority_side():
    im = Image.new("RGB", (60, 30), (240, 240, 240))
    ImageDraw.Draw(im).rectangle([10, 8, 30, 20], fill=(20, 20, 20))
    import numpy as np
    ink = fidelity.text_ink(np.asarray(im))
    assert ink is not None and ink[14, 20] and not ink[2, 2]
    assert fidelity.text_ink(np.full((30, 60, 3), 128, np.uint8)) is None


def test_fix_line_height_note_per_font_family(monkeypatch):
    spec = fixture_spec()
    for w in spec["widgets"]:
        if w["type"] == "TextBlock":
            w["font"]["family"] = BODY
    widget(spec, "BurstLabelText")["font"]["family"] = TITLE
    note = fix._line_height_note(CFG, spec)
    assert "role body" in note and "role title" in note and "30->57" in note and "engine default" not in note
    widget(spec, "ChainCountText")["font"]["family"] = None
    assert "engine default" in fix._line_height_note(CFG, spec)
