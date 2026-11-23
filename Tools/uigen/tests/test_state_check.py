"""1b 후속 L 다음 — 상태 렌더 검증(gen/state_check · 진단 연결 · F1 숨는 글자 메움 · F2 채움 번짐): 합성 그림으로 — 에디터 없음.
[실측 R20261119_091634 — '오의 불가' 자리 판 회색 상자 · 게이지 100 % 끝 어두운 사각형]"""
from __future__ import annotations

import json

import numpy as np
from PIL import Image

from gen import backdrop
from gen import diagnose as dg
from gen import state_check

RED = (220, 70, 40)
GOLD = (230, 180, 70)


def _tex(rgb, a, w, h) -> np.ndarray:
    t = np.zeros((h, w, 4), float)
    t[..., :3], t[..., 3] = rgb, a * 255
    return t


# ---------------------------------------------------------------------------------------------------------------------
# S1 숨김 흔적

CW, CH = 300, 160
WARN = [100, 40, 100, 40]          # 시작 때 숨는 글자 상자(빛 4)


def _hidden_scene(residue: bool):
    """판 = 투명 + 자리를 가로지르는 금선(y 84 ~ 86) + 선 가운데 작은 장식(컨셉에도 있음) [+ 글자 자리 어두운 반투명 상자(잔상)].
    컨셉 = 같은 판 + 붉은 글자 획(y 52 ~ 70)."""
    plate = np.zeros((CH, CW, 4), float)
    plate[84:87, 20:280, :3], plate[84:87, 20:280, 3] = GOLD, 255
    plate[81:84, 148:153, :3], plate[81:84, 148:153, 3] = GOLD, 255
    concept = plate.copy()
    glyph = np.zeros((CH, CW), bool)
    for x0 in range(115, 185, 18):
        glyph[52:70, x0:x0 + 8] = True
    concept[glyph, :3], concept[glyph, 3] = RED, 255
    if residue:
        plate[50:80, 110:190, :3], plate[50:80, 110:190, 3] = (30, 25, 20), 0.5 * 255
    spec = {"canvas": [CW, CH], "root": "Root", "assets": [], "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Plate", "type": "Image", "parent": "Root", "slot": {"kind": "canvas", "z": 0}, "style": {"brush": {"draw_as": "image", "asset": "plate"}}},
        {"id": "Warn", "type": "TextBlock", "parent": "Root", "visibility": "collapsed", "slot": {"kind": "canvas", "z": 1},
         "font": {"color": "#DC4628FF", "glow": {"size": 4, "color": "#FF3F153D"}}}]}
    boxes = [{"id": "Root", "x": 0, "y": 0, "w": CW, "h": CH, "visible": True}, {"id": "Plate", "x": 0, "y": 0, "w": CW, "h": CH, "visible": True},
             {"id": "Warn", "x": WARN[0], "y": WARN[1], "w": WARN[2], "h": WARN[3], "visible": True}]
    return spec, boxes, {"plate": plate}, concept, glyph


def test_hidden_trace_finds_the_blob_left_where_a_hidden_text_was():
    spec, boxes, tex, concept, glyph = _hidden_scene(residue=True)
    states = [{"widget": "Warn", "subtree": ["Warn"], "drawn_in_concept": True}]
    r = state_check.hidden_trace(spec, boxes, tex, [CW, CH], concept[..., :3], concept[..., 3] / 255.0, states, {"Warn": glyph}, dg.settings(None))
    f = r["findings"]
    assert f and f[0]["check"] == "hidden_trace" and f[0]["code"] == "E8" and f[0]["widgets"][0] == "Warn"
    assert {"gray", "white"} <= set(f[0]["backgrounds"]) and r["renderer"] == "composite"
    x, y, w, h = f[0]["box"]
    assert 100 <= x + w / 2 <= 200 and 45 <= y + h / 2 <= 85


def test_hidden_trace_keeps_a_crossing_line_and_concept_structure():
    """자리를 가로지르는 금선(띠) · 컨셉에 있는 선 가운데 장식(글자 · 빛 자리 밖)은 흔적이 아니다."""
    spec, boxes, tex, concept, glyph = _hidden_scene(residue=False)
    states = [{"widget": "Warn", "subtree": ["Warn"], "drawn_in_concept": True}]
    r = state_check.hidden_trace(spec, boxes, tex, [CW, CH], concept[..., :3], concept[..., 3] / 255.0, states, {"Warn": glyph}, dg.settings(None))
    assert r["findings"] == [], r["findings"]
    assert r["roots"][0]["widget"] == "Warn" and r["roots"][0]["blobs"] == 0
    # 컨셉이 그 상태를 안 그린 숨은 위젯은 본 진단 몫(건너뜀)
    r2 = state_check.hidden_trace(spec, boxes, tex, [CW, CH], concept[..., :3], concept[..., 3] / 255.0,
                                  [{"widget": "Warn", "subtree": ["Warn"], "drawn_in_concept": False}], {}, dg.settings(None))
    assert r2["findings"] == [] and "skipped" in r2["roots"][0]


# ---------------------------------------------------------------------------------------------------------------------
# S2 게이지 끝

GW, GH = 300, 100
FRAME = [40, 30, 230, 40]
TRACK = [50, 35, 190, 30]          # 트랙 x 50 ~ 239, 끝 장식 x 240 ~ 262


def _gauge_scene(spill: int):
    frame = np.zeros((40, 230, 4), float)
    frame[5:35, 10:200, :3], frame[5:35, 10:200, 3] = (30, 22, 18), 255       # 빈 트랙
    frame[2:38, 200:222, :3], frame[2:38, 200:222, 3] = GOLD, 255              # 끝 장식
    body, end_in = 120, 5
    seg = body + spill
    fill = np.zeros((30, seg, 4), float)
    fill[:, :body, :3], fill[:, :body, 3] = (250, 200, 90), 255
    fill[:, body - end_in - 1:body, :3] = (255, 240, 200)                       # 진행 끝 테두리
    if spill:
        fill[:, body:, :3], fill[:, body:, 3] = (34, 26, 20), 255                # 예전 — 번짐 열 = 컨셉 픽셀(어두운 빈 트랙) 불투명
    gw = TRACK[2] + spill
    margin = [round(10 / seg, 4), 0.0, round((end_in + spill + 1) / seg, 4), 0.0]
    proc = {"shape": "concept_fill", "frame_box": FRAME, "track": [10, 5, 199, 34], "body_end": 10 + body - 1, "spill": spill, "texture": "concept"}
    spec = {"canvas": [GW, GH], "root": "Root", "assets": [{"asset_id": "fill", "procedural": proc}], "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Frame", "type": "Image", "parent": "Root", "slot": {"kind": "canvas", "z": 0}, "style": {"brush": {"draw_as": "image", "asset": "frame"}}},
        {"id": "Gauge", "type": "ProgressBar", "parent": "Root", "slot": {"kind": "canvas", "z": 1},
         "style": {"background": {"draw_as": "none"}, "fill": {"draw_as": "box", "asset": "fill", "margin": margin}, "percent": round(seg / gw, 4),
                   "bar_fill_type": "left_to_right", "bar_fill_style": "scale"}}]}
    boxes = [{"id": "Root", "x": 0, "y": 0, "w": GW, "h": GH, "visible": True}, {"id": "Frame", "x": FRAME[0], "y": FRAME[1], "w": FRAME[2], "h": FRAME[3], "visible": True},
             {"id": "Gauge", "x": TRACK[0], "y": TRACK[1], "w": gw, "h": TRACK[3], "visible": True}]
    return spec, boxes, {"frame": frame, "fill": fill}


def test_gauge_states_catch_the_fill_spill_painting_past_the_track_end():
    spec, boxes, tex = _gauge_scene(spill=24)
    base = backdrop.compose(spec, boxes, tex, [GW, GH], (0, 0, 0))[0]
    r = state_check.gauge_states(spec, boxes, tex, [GW, GH], dg.settings(None), base)
    g = r["gauges"][0]
    assert g["track"] == TRACK and g["track_from"] == "concept_fill track"
    f = [x for x in r["findings"] if x["check"] == "gauge_outside"]
    assert f and all(x["percent"] == 1.0 for x in f) and f[0]["widgets"] == ["Gauge"]
    x, y, w, h = f[0]["box"]
    assert x >= 235 and x + w <= 275 and x + w / 2 > 245                        # 트랙 끝(239) 뒤 끝 장식 자리(7 × 7 창이 모서리 3 px 걸침)
    assert g["states"]["0"]["outside_px"] == 0 and g["end_unchanged_frac"] == 0.0


def test_gauge_states_pass_a_fill_without_spill():
    spec, boxes, tex = _gauge_scene(spill=0)
    base = backdrop.compose(spec, boxes, tex, [GW, GH], (0, 0, 0))[0]
    r = state_check.gauge_states(spec, boxes, tex, [GW, GH], dg.settings(None), base)
    assert r["findings"] == [], r["findings"]
    # 엔진 렌더 함수가 0 에서 채움을 남기면 잡는다(합성은 0 이면 안 그림)
    def render_pct(wid, p):
        img = backdrop.compose(state_check._with_percent(spec, wid, max(p, 0.3)), boxes, tex, [GW, GH], (0, 0, 0))[0]
        return img
    r2 = state_check.gauge_states(spec, boxes, tex, [GW, GH], dg.settings(None), base, render_pct=render_pct)
    assert any(x["check"] == "gauge_zero_fill" for x in r2["findings"]) and r2["gauges"][0]["renderer"][0.0] == "engine"


def test_end_glow_zone_only_for_a_dropped_spill():
    spec = {"widgets": [{"id": "G", "type": "ProgressBar", "style": {"fill": {"asset": "f"}}}], "assets": [
        {"asset_id": "f", "procedural": {"shape": "concept_fill", "frame_box": [10, 10, 300, 40], "track": [5, 4, 280, 35], "body_end": 150,
                                          "spill": 0, "spill_measured": 20}}]}
    z = state_check.end_glow_zones(spec, (100, 400))
    assert len(z) == 1 and z[0]["widgets"] == ["G"] and z[0]["box"] == [10 + 147, 14, 20 + 8 + 3 + 1, 32]
    spec["assets"][0]["procedural"]["spill"] = 20
    assert state_check.end_glow_zones(spec, (100, 400)) == []


# ---------------------------------------------------------------------------------------------------------------------
# F1 — 시작 때 숨는 글자 자리 판 메움(refine._hidden_text_fill)

def _plate_scene():
    """판 조각(120 × 300): 투명 바탕 · 붉은 글자 + 빛(숨는 글자 상자 [100, 30, 100, 50] 안) · 상자 아래 가로 빛 띠(알파 0.12, 85 ~ 91) · 밝은 테두리선(92 ~ 94) ·
    어둡고 불투명한 트랙(95 ~)."""
    h, w = 120, 300
    col = np.zeros((h, w, 3))
    a = np.zeros((h, w))
    col[95:], a[95:] = (30, 22, 18), 1.0
    col[92:95], a[92:95] = GOLD, 1.0
    col[85:92], a[85:92] = (230, 170, 90), 0.12
    for x0 in range(110, 190, 20):
        col[38:72, x0 - 4:x0 + 12], a[38:72, x0 - 4:x0 + 12] = RED, 0.6                 # 빛
        col[42:68, x0:x0 + 8], a[42:68, x0:x0 + 8] = RED, 1.0                          # 획
    return col, a


def test_hidden_text_fill_clears_the_whole_spot_and_keeps_the_crossing_structure():
    from stages import refine
    col, a = _plate_scene()
    item = {"id": "Warn", "box": [100.0, 30.0, 100.0, 50.0], "glow": 4.0, "colors": [list(RED)], "hidden": True}
    c2, a2 = col.copy(), a.copy()
    r = refine._hidden_text_fill(c2, a2, item, orig=(col.copy(), a.copy()), others=[], mask=a > 0.02)
    assert r["used"] and r["fill"] == "hidden_text" and r["evidence_from"] == "spec text colour"
    assert a2[40:72, 105:195].max() < 0.05                                              # 글자 · 빛 자리 → 둘레처럼 투명(예전 길은 아래 트랙 알파를 끌어옴)
    assert (a2[92:] == a[92:]).all() and (c2[92:] == col[92:]).all()                   # 테두리선 · 트랙 그대로
    assert abs(a2[87, 150] - 0.12) < 0.03                                               # 자리를 가로지르는 빛 띠는 이어짐
    assert (a2[:, :80] == a[:, :80]).all() and (a2[:, 230:] == a[:, 230:]).all()       # 자리 밖 그대로
    # 컨셉이 그 글자를 안 그렸으면 고치지 않음(예전 길로)
    col0, a0 = col.copy(), a.copy()
    col0[30:85, 90:210], a0[30:85, 90:210] = 0, 0
    r2 = refine._hidden_text_fill(col0.copy(), a0.copy(), item, orig=(col0, a0), others=[], mask=a0 > 0.02)
    assert not r2["used"] and "not drawn" in r2["reason"]


def test_harmonic_fill_matches_the_boundary_and_follows_rows():
    from stages import refine
    v = np.zeros((20, 40, 1))
    v[:, 0], v[:, -1] = 10.0, 30.0
    hole = np.zeros((20, 40), bool)
    hole[:, 1:-1] = True
    u = refine._harmonic_fill(v, hole, wy=0.05)
    assert np.allclose(u[10, :, 0], np.linspace(10, 30, 40), atol=0.2)                  # 줄마다 양끝 사이 선형
    assert (u[~hole] == v[~hole]).all()


# ---------------------------------------------------------------------------------------------------------------------
# 진단 연결 — 기록만(record) · 오류(error)

def _diag_run(tmp_path):
    spec, boxes, tex, concept, glyph = _hidden_scene(residue=True)
    rd = tmp_path / "run"
    (rd / "assets" / "final").mkdir(parents=True)
    Image.fromarray(tex["plate"].round().astype(np.uint8), "RGBA").save(rd / "assets" / "final" / "plate.png")
    Image.fromarray(concept[..., :3].astype(np.uint8)).save(rd / "reference_color.png")
    Image.fromarray(concept[..., 3].astype(np.uint8), "L").save(rd / "reference_alpha.png")
    Image.fromarray((concept[..., :3] * concept[..., 3:] / 255.0).astype(np.uint8)).save(rd / "reference.png")
    for w in spec["widgets"]:
        b = next(b for b in boxes if b["id"] == w["id"])
        if w["id"] != "Root":
            w["bbox_intent"] = [b["x"], b["y"], b["w"], b["h"]]
    spec["widgets"][2]["text"] = {"value": "W"}
    (rd / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (rd / "geometry.json").write_text(json.dumps({"canvas": [CW, CH], "geometry": {f"{CW}x{CH}": boxes}}), encoding="utf-8")
    (rd / "manifest.json").write_text(json.dumps({"assets": [{"asset_id": "plate", "file": "assets/final/plate.png"}]}), encoding="utf-8")
    (rd / "normalize.json").write_text(json.dumps({"background": {"kind": "transparent"}}), encoding="utf-8")
    ren = backdrop.compose(spec, boxes, {"plate": backdrop._load(rd / "assets" / "final" / "plate.png")}, [CW, CH], (0, 0, 0))[0]
    ren[glyph] = RED                                                              # 엔진 글자(컨셉 상태 — 켬)
    Image.fromarray(ren.astype(np.uint8)).save(rd / "render.png")
    return rd


def test_diagnose_records_state_checks_and_raises_them_only_in_error_mode(tmp_path):
    rd = _diag_run(tmp_path)
    rec = dg.diagnose(rd, None, {"appearance": {"state_checks": "record"}}, pictures=False)
    sc = rec["state_checks"]
    assert sc["mode"] == "record" and any(f["check"] == "hidden_trace" and "Warn" in f["widgets"] for f in sc["findings"])
    assert not any(d.get("check") == "hidden_trace" for d in rec["defects"])
    rec2 = dg.diagnose(rd, tmp_path / "out", {"appearance": {"state_checks": "error"}}, pictures=True)
    e8 = [d for d in rec2["defects"] if d.get("check") == "hidden_trace"]
    assert e8 and e8[0]["code"] == "E8" and rec2["summary"]["by_code"].get("E8", 0) >= 1 and not dg.gate(rec2)["pass"]
    assert rec2["summary"]["errors"] == len(rec2["defects"]) and [d["n"] for d in rec2["defects"]] == list(range(1, len(rec2["defects"]) + 1))
    assert (tmp_path / "out" / "compare.png").is_file()
    with Image.open(tmp_path / "out" / "compare.png") as im:
        assert im.height > CH                                                    # 상태 띠가 붙음


def test_golden_matches_record_only_state_findings():
    import golden
    item = {"name": "x", "run": "r", "codes": ["E8"], "widgets": ["Warn"], "checks": ["hidden_trace"]}
    rec = {"defects": [], "state_checks": {"mode": "record", "findings": [{"code": "E8", "check": "hidden_trace", "widgets": ["Warn"], "box": [1, 2, 3, 4]}]}}
    assert golden.matches(item, rec)
    assert not golden.matches({**item, "checks": ["gauge_outside"]}, rec)
    assert golden.matches({"name": "p", "run": "r", "expect": "clean_run"}, rec) == []           # 기록만인 발견은 보호 run 을 깨지 않음
    # 오류로 오른 상태 검사 결함(check 키)은 보호 판정에서 빼고 따로(그 run 자기 텍스처의 같은 종류 결함 — 회귀 아님), 다른 결함은 그대로 깨짐
    rec_e = {"defects": [{"n": 1, "code": "E8", "check": "gauge_outside", "widgets": ["G"]}], "state_checks": {"mode": "error", "findings": []}}
    assert golden.matches({"expect": "clean_run"}, rec_e) == []
    rec_e["defects"].append({"n": 2, "code": "E1", "stage": "texture", "widgets": ["A"]})
    assert len(golden.matches({"expect": "clean_run"}, rec_e)) == 1
    assert golden.summary_line([{"expect": "clean_run", "ok": True, "state_hits": [{"check": "gauge_outside"}]}]).endswith("(their own textures — listed)")
    assert dg.settings(None)["state_checks"] == "error"
