"""1b 후속 J-b — 자동 차이 진단(gen/diagnose) · appearance 게이트. 합성 run 폴더(작은 캔버스)로 — 에디터 없음."""
from __future__ import annotations

import json

import numpy as np
from PIL import Image

from gen import backdrop
from gen import diagnose

W, H = 240, 140
PANEL = [20, 30, 200, 80]
TEXT = [60, 50, 90, 40]
BAND = (40, 110, 200)


def _glyph(img, x, y, color=(250, 250, 250)):
    """'ㅌ'처럼 생긴 굵은 획 몇 개(글자 대역)."""
    for k in range(3):
        img[y + k * 12:y + k * 12 + 6, x:x + 60] = color
    img[y:y + 30, x:x + 6] = color


def _run(tmp_path, *, text_dx=0, hole=False, hidden_glow=False, split=False):
    rd = tmp_path / "run"
    (rd / "assets" / "final").mkdir(parents=True)
    col = np.zeros((H, W, 3), np.uint8)
    alpha = np.zeros((H, W), np.uint8)
    x, y, w, h = PANEL
    col[y:y + h, x:x + w] = BAND
    alpha[y:y + h, x:x + w] = 230
    tex = np.dstack([col[y:y + h, x:x + w], alpha[y:y + h, x:x + w]]).copy()     # 글자 없는 패널 텍스처(구멍 메운 것)
    _glyph(col, 75, 55)
    alpha[55:85, 75:135] = np.maximum(alpha[55:85, 75:135], 230)
    Image.fromarray(col).save(rd / "reference_color.png")
    Image.fromarray(alpha, "L").save(rd / "reference_alpha.png")
    Image.fromarray((col * (alpha[..., None] / 255.0)).astype(np.uint8)).save(rd / "reference.png")
    if hole:
        tex[30:45, 140:170, 3] = 0
    widgets = [{"id": "Root", "type": "CanvasPanel"},
               {"id": "Panel", "type": "Image", "parent": "Root", "bbox_intent": PANEL, "slot": {"kind": "canvas", "z": 1},
                "style": {"brush": {"draw_as": "image", "asset": "panel"}}},
               {"id": "Label", "type": "TextBlock", "parent": "Root", "bbox_intent": TEXT, "slot": {"kind": "canvas", "z": 2},
                "font": {"color": "#FAFAFAFF", "size": 24}, "text": {"value": "T"}}]
    assets = [{"asset_id": "panel", "file": "assets/final/panel.png"}]
    boxes = [{"id": "Root", "x": 0, "y": 0, "w": W, "h": H}, {"id": "Panel", "x": x, "y": y, "w": w, "h": h},
             {"id": "Label", "x": TEXT[0], "y": TEXT[1], "w": TEXT[2], "h": TEXT[3]}]
    if split:                                    # 패널을 두 텍스처로 가운데에서 나눔(경계 = 절취선 후보)
        tex_l, tex_r = tex[:, :100].copy(), tex[:, 100:].copy()
        widgets[1] = {**widgets[1], "bbox_intent": [x, y, 100, h], "style": {"brush": {"draw_as": "image", "asset": "left"}}}
        widgets.insert(2, {"id": "PanelR", "type": "Image", "parent": "Root", "bbox_intent": [x + 100, y, 100, h], "slot": {"kind": "canvas", "z": 1},
                           "style": {"brush": {"draw_as": "image", "asset": "right"}}})
        boxes[1] = {"id": "Panel", "x": x, "y": y, "w": 100, "h": h}
        boxes.insert(2, {"id": "PanelR", "x": x + 100, "y": y, "w": 100, "h": h})
        Image.fromarray(tex_l, "RGBA").save(rd / "assets" / "final" / "left.png")
        Image.fromarray(tex_r, "RGBA").save(rd / "assets" / "final" / "right.png")
        assets = [{"asset_id": "left", "file": "assets/final/left.png"}, {"asset_id": "right", "file": "assets/final/right.png"}]
    else:
        Image.fromarray(tex, "RGBA").save(rd / "assets" / "final" / "panel.png")
    if hidden_glow:                              # 시작 때 숨은 빛 — 컨셉에는 없다(force_visible 렌더에만)
        g = np.zeros((40, 40, 4), np.uint8)
        g[..., :3], g[..., 3] = (255, 220, 120), 160
        Image.fromarray(g, "RGBA").save(rd / "assets" / "final" / "glow.png")
        assets.append({"asset_id": "glow", "file": "assets/final/glow.png"})
        widgets.append({"id": "Glow", "type": "Image", "parent": "Root", "bbox_intent": [170, 35, 40, 40], "visibility": "collapsed",
                        "slot": {"kind": "canvas", "z": 1}, "binding": {"kind": "flag", "data": "g"}, "style": {"brush": {"draw_as": "image", "asset": "glow"}}})
        boxes.append({"id": "Glow", "x": 170, "y": 35, "w": 40, "h": 40})
    spec = {"canvas": [W, H], "root": "Root", "widgets": widgets}
    (rd / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (rd / "geometry.json").write_text(json.dumps({"canvas": [W, H], "geometry": {f"{W}x{H}": boxes}}), encoding="utf-8")
    (rd / "manifest.json").write_text(json.dumps({"assets": assets}), encoding="utf-8")
    (rd / "normalize.json").write_text(json.dumps({"background": {"kind": "transparent"}}), encoding="utf-8")
    texs = {a["asset_id"]: backdrop._load(rd / a["file"]) for a in assets}
    ren, _, _ = backdrop.compose(spec, boxes, texs, [W, H], (0, 0, 0))
    ren = ren.astype(np.uint8)
    _glyph(ren, 75 + text_dx, 55)                # 엔진 글자 대역
    Image.fromarray(ren).save(rd / "render.png")
    return rd


def test_clean_render_has_no_defect(tmp_path):
    rec = diagnose.diagnose(_run(tmp_path), tmp_path / "out")
    assert rec["summary"]["defects"] == 0, rec["defects"]
    t = rec["texts"][0]
    assert t["widget"] == "Label" and t["causes"] == [] and abs(t["h_ratio"] - 1) < 0.05 and t["center_d"] == [0.0, 0.0]
    g = diagnose.gate(rec)
    assert g["name"] == "appearance" and g["pass"] and g["value"] == 0
    assert (tmp_path / "out" / "diagnosis.json").is_file()


def test_shifted_text_is_a_fixable_position_defect(tmp_path):
    rec = diagnose.diagnose(_run(tmp_path, text_dx=9), tmp_path / "out")
    d = [x for x in rec["defects"] if x["stage"] == "text"]
    assert len(d) == 1 and "position" in d[0]["causes"] and d[0]["fixable"] and d[0]["widgets"] == ["Label"]
    assert not diagnose.gate(rec)["pass"] and (tmp_path / "out" / "defects.png").is_file()


def test_texture_hole_is_classified_at_the_texture_stage(tmp_path):
    rec = diagnose.diagnose(_run(tmp_path, hole=True), tmp_path / "out")
    tex = [x for x in rec["defects"] if x["stage"] == "texture"]
    assert tex and tex[0]["cause"].startswith(("hole", "missing")) and not tex[0]["fixable"]
    x, y, w, h = tex[0]["box"]
    assert 150 <= x + w / 2 <= 200 and 55 <= y + h / 2 <= 80          # 구멍 자리(패널 140 ~ 170, 30 ~ 45 + 패널 원점)


def test_hidden_state_not_in_the_concept_is_left_out(tmp_path):
    rec = diagnose.diagnose(_run(tmp_path, hidden_glow=True), tmp_path / "out")
    st = rec["hidden_states"][0]
    assert st["widget"] == "Glow" and st["drawn_in_concept"] is False and rec["summary"]["hidden_not_drawn"] == ["Glow"]
    assert rec["summary"]["defects"] == 0, rec["defects"]


def test_zoom_seams_count_split_textures_only(tmp_path):
    rd = _run(tmp_path, split=True)
    rec = diagnose.diagnose(rd, tmp_path / "out")
    assert rec["seams"]["zone_px"] > 0 and rec["seams"]["layers"] == 2
    one = diagnose.diagnose(_run(tmp_path / "b"), tmp_path / "out_b")
    assert one["seams"]["zone_px"] == 0


def test_skips_without_reference_or_with_a_wrong_size_render(tmp_path):
    rd = _run(tmp_path)
    Image.fromarray(np.zeros((2, 2, 3), np.uint8)).save(rd / "render.png")
    rec = diagnose.diagnose(rd)
    assert "cannot compare" in rec["skipped"] and diagnose.gate(rec)["pass"] and diagnose.gate(rec)["skipped"]
    (rd / "reference.png").unlink()
    assert "hand spec" in diagnose.diagnose(rd)["skipped"]


def test_glow_joined_blob_is_split_between_text_boxes_and_text_causes():
    """1b 후속 J — 빛 번짐이 이웃 두 글자를 한 덩어리로 이으면 빛 여백 뺀 상자(cores)로 픽셀마다 나눈다(한쪽 '누락' 이 안 됨)."""
    import sys
    H, W = 60, 200
    d = np.zeros((H, W), np.float32)
    d[20:40, 20:90] = 200.0
    d[20:40, 110:180] = 200.0
    d[25:35, 88:112] = 120.0                                                   # 빛 번짐 다리
    box = lambda x, y, w, h: diagnose._box_mask((H, W), [x, y, w, h])         # noqa: E731
    owns = {"A": box(10, 10, 100, 40), "B": box(100, 10, 90, 40)}             # 빛 여백으로 넓힌 상자 — 서로 겹침
    zones = {k: diagnose._dilate(v, 6) for k, v in owns.items()}
    cores = {"A": box(20, 20, 70, 20), "B": box(110, 20, 70, 20)}
    out = diagnose.assign_glyphs(d, zones, owns, cores)
    assert out["A"][30, 50] and out["B"][30, 150] and not out["A"][30, 150] and not out["B"][30, 50]
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    import run_pipeline
    res = {"gates": [{"name": "appearance", "details": {"defects": [{"stage": "text", "widgets": ["A"], "causes": ["size", "position"]},
                                                                    {"stage": "texture", "widgets": ["P"], "cause": "hole"}]}}]}
    assert run_pipeline._text_causes(res) == {"A": {"size", "position"}} and run_pipeline._text_causes(None) == {}


def test_stroke_only_inside_overlapping_cores_goes_whole_to_its_connected_body():
    """진단 거짓 양성 E1 고침 — 빛 여백으로 넓은 아래 글자(B) core 가 위 글자(A) 아래와 겹치고, A 의 받침 획이 그 겹친 자리 안에만 있으면
    픽셀마다 상자 거리로 가르지 않고 통째로 이어진 본체(가까운 A 의 다른 획) 쪽 [실측 R20261118_175104 '체인' ㄴ 받침 ↔ '4.2']."""
    H, W = 120, 200
    d = np.zeros((H, W), np.float32)
    d[10:30, 40:60] = 200.0                                                    # A 본체(자기 구역)
    d[34:38, 40:80] = 200.0                                                    # A 받침 — 두 core 가 겹친 자리 안에만, 본체와 5 px
    d[60:100, 30:150] = 200.0                                                  # B 본체(멀리 아래)
    box = lambda x, y, w, h: diagnose._box_mask((H, W), [x, y, w, h])         # noqa: E731
    cores = {"A": box(30, 5, 60, 36), "B": box(20, 32, 150, 80)}
    owns = {"A": box(30, 5, 60, 36), "B": box(13, 25, 164, 94)}
    zones = {k: diagnose._dilate(v, 6) for k, v in owns.items()}
    out = diagnose.assign_glyphs(d, zones, owns, cores)
    assert out["A"][36, 42] and out["A"][36, 78] and not out["B"][36, 78]       # 예전엔 오른쪽 끝이 B 몫(상자 중심 거리)
    assert out["A"][20, 50] and out["B"][80, 90] and not out["A"][80, 90]


def test_glyph_filter_drops_long_lines_and_far_specks():
    own = np.zeros((60, 200), bool)
    own[10:50, 40:120] = True
    m = np.zeros((60, 200), bool)
    m[20:40, 50:56] = True                       # 세로획
    m[20:26, 50:100] = True                      # 가로획
    m[45:47, 0:200] = True                       # 상자보다 긴 가는 선(띠 가장자리)
    m[25:30, 185:190] = True                     # 멀리 떨어진 장식 조각
    out = diagnose._filter_glyph_parts(m, own)
    assert out[30, 52] and out[22, 90] and not out[46, 10] and not out[27, 187]
