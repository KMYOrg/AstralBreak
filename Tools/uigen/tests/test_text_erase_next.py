"""1b 후속 L 다음 — 글자 지우기 다음(설계 §11 V1 ~ V8): 검증 A(바꿀 수 있는 자리 밖 RGBA 같음) · 구조선 규칙 좁힘(판에도 있는 선만) · 밝힌 검정 기록 ·
harmonic 경계 잡티 빼기 · 투명 바탕 글자 후보 clear_alpha · '정답 없음' 근거 · 반복 보강 단계 · OCR 상자 범위 · 복잡 배경 판정 · 수동 확인 맞춤 · 회귀 표.
합성 그림, 에디터 · 모델 · OCR 없음."""
from __future__ import annotations

import io
import json

import numpy as np
from PIL import Image

from core import config
from gen import diagnose as dg
from gen import state_check
from stages import refine

CFG = config.load_pipeline()
P = 6


def _pad(x):
    return np.pad(x, ((P, P), (P, P), (0, 0)) if x.ndim == 3 else P, mode="edge")


def _png(rgba) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(np.clip(rgba, 0, 255).astype(np.uint8), "RGBA").save(buf, format="PNG")
    return buf.getvalue()


def _ring_digit(m, x, y, w=18, h=26, t=4):
    m[y:y + h, x:x + t] = m[y:y + h, x + w - t:x + w] = m[y:y + t, x:x + w] = m[y + h - t:y + h, x:x + w] = True


# ---------------------------------------------------------------------------------------------------------------------
# V1 검증 A

def test_blend_band_stops_inside_its_zone_and_put_writes_only_there():
    hole = np.zeros((40, 60), bool)
    hole[15:25, 20:40] = True
    b, zone = refine._blend_band(hole, 2, 1.2)
    assert zone.sum() > hole.sum() and (b[~zone] == 0).all() and (b[hole] == 1).all()
    col, a = np.full((40, 60, 3), 77.3), np.full((40, 60), 0.613)
    before_c, before_a = col.copy(), a.copy()
    refine._put(col, a, (0, 40, 0, 60), zone, np.zeros((40, 60, 3)), np.zeros((40, 60)))
    assert (col[~zone] == before_c[~zone]).all() and (a[~zone] == before_a[~zone]).all()      # 바이트 · 실수 모두 그대로
    assert (a[zone] == 0).all()


def test_outside_changed_counts_only_pixels_outside_both_zones_and_ignores_transparent_rgb():
    base = np.zeros((20, 30, 4))
    base[..., :3], base[..., 3] = (60, 70, 80), 255
    base[:, 25:, 3] = 0                                   # 투명 띠(번짐 색은 견주지 않음)
    zone = np.zeros((20, 30), bool)
    zone[5:10, 5:10] = True
    cand = base.copy()
    cand[6:9, 6:9, :3] = 200                              # 자리 안 — 괜찮음
    cand[:, 26:, :3] = 10                                 # 알파 0 픽셀의 RGB — 안 셈
    assert refine._outside_changed(_png(cand), zone, _png(base), None)["px"] == 0
    cand[15, 15, :3] = 61                                 # 자리 밖 한 픽셀
    r = refine._outside_changed(_png(cand), zone, _png(base), None)
    assert r["px"] == 1 and r["box"] == [15, 15, 1, 1]
    assert refine._outside_changed(_png(cand), zone, _png(base), np.pad(np.ones((1, 1), bool), ((15, 4), (15, 14))))["px"] == 0


def test_plate_item_fill_erase_changes_nothing_outside_the_zone_it_returns():
    """판 정합 길 harmonic 지우기 — 돌려준 바꿀 수 있는 자리(_zone) 밖은 실수 값까지 그대로(V1 의 바탕)."""
    h, w = 120, 160
    panel = np.array([40.0, 20.0, 45.0])
    col, a = np.tile(panel, (h, w, 1)), np.ones((h, w))
    g = np.zeros((h, w), bool)
    for x in (55, 80):
        _ring_digit(g, x, 40)
    col[g] = (235, 225, 200)
    col += np.random.default_rng(3).normal(0, 2.0, col.shape)             # 반올림 차가 남는지 보려고 고르지 않은 바탕
    ntp, ntap = _pad(np.tile(panel, (h, w, 1))), _pad(np.ones((h, w)))
    for method in ("harmonic", "lama"):
        c2, a2 = col.copy(), a.copy()
        r = refine._plate_item_fill(c2, a2, ntp, ntap, {"id": "T", "box": [50, 34, 58, 38], "glow": 0, "colors": [[235, 225, 200]], "erase": True,
                                                       "erase_method": method}, orig=(col.copy(), a.copy()))
        assert r["used"]
        y0, y1, x0, x1, zm = r.pop("_zone")
        full = np.zeros((h, w), bool)
        full[y0:y1, x0:x1] = zm
        assert full[g].all()
        assert (c2[~full] == col[~full]).all() and (a2[~full] == a[~full]).all()


# ---------------------------------------------------------------------------------------------------------------------
# V2 · V3 판정

def _line_scene(plate_has_line: bool):
    from tests.test_text_erase import _scene, W, H
    spec, boxes, tex, concept, g, panel = _scene("line")
    if plate_has_line:
        panel = panel.copy()
        panel[92:94, 96:150, :3] = np.asarray((40, 30, 50), float) + 52           # 판도 같은 자리에 선(더 밝게 — 다시 그린 구조선)
    return spec, boxes, tex, concept, g, panel, W, H


def _line_trace(plate_has_line: bool, mode: str):
    from gen import backdrop
    spec, boxes, tex, concept, g, panel, W, H = _line_scene(plate_has_line)
    gm = {"Timer": {"concept": g, "concept_cand": dg._dilate(g, 1)}}
    s = {**dg.settings(None), "text_line_plate": mode}
    imgs = {k: backdrop.compose(spec, boxes, tex, [W, H], bg)[0] for k, bg in (("black", (0, 0, 0)), ("gray", backdrop.GRAY), ("white", (255, 255, 255)))}
    return state_check.text_trace(spec, boxes, [W, H], concept[..., :3], concept[..., 3] / 255.0, (panel[..., :3], panel[..., 3] / 255.0), gm, s, imgs)


def test_line_not_in_the_text_free_plate_is_a_defect_in_error_mode():
    """[실측 R20261120_005215 파티 HP 숫자 — 막대 윗선 위 빛 자국 22 × 2 가 '구조선'으로 빠졌다] 판에 없는 선은 V2 error 면 결함."""
    rec = _line_trace(False, "record")
    ll = [x for x in rec.get("line_like") or [] if x["check"] == "text_trace"]
    assert ll and ll[0]["in_plate"] is False and not [f for f in rec["findings"] if f["check"] == "text_trace"]
    err = _line_trace(False, "error")
    f = [x for x in err["findings"] if x["check"] == "text_trace"]
    assert f and f[0].get("line_not_in_plate")


def test_line_also_in_the_text_free_plate_stays_record_only():
    rec = _line_trace(True, "error")
    ll = [x for x in rec.get("line_like") or [] if x["check"] == "text_trace"]
    assert all(x["in_plate"] for x in ll)
    assert not [f for f in rec["findings"] if f["check"] == "text_trace" and f.get("line_not_in_plate")]


def test_text_trace_records_the_ring_lightness_for_the_lift_check():
    from tests.test_text_erase import _trace
    r = _trace("ring")
    t = next(t for t in r["texts"] if t["widget"] == "Timer")
    assert t["ring_l"] < state_check.LIFT_DARK_L                          # 어두운 패널
    assert r.get("lift_like") and r["lift_like"][0]["ring_l"] == t["ring_l"]


# ---------------------------------------------------------------------------------------------------------------------
# V4 · V5 지우기

def test_boundary_specks_takes_small_dots_but_not_lines():
    h, w = 60, 80
    cw, aw = np.full((h, w, 3), 30.0), np.ones((h, w))
    hole = np.zeros((h, w), bool)
    hole[20:40, 25:55] = True
    cw[18:20, 30:32] = 2.0                                 # 경계 밖 2 × 2 어두운 점
    cw[42, :] = 120.0                                      # 지울 자리 아래 2 px 의 긴 선(구조물)
    sp = refine._boundary_specks(cw, aw, hole, np.zeros((h, w), bool))
    assert sp[18:20, 30:32].all() and not sp[42].any()


def test_clear_alpha_fill_follows_the_alpha_tail_and_keeps_the_bar():
    """[실측 R20261120_005215 파티 이름 · '0 %'] 투명 바탕 위 빛 글자 — 알파 꼬리(빛 알파)를 끝까지 지우고 상자 밖으로 이어진 막대는 그대로."""
    h, w = 110, 200
    col, a = np.zeros((h, w, 3)), np.zeros((h, w))
    g = np.zeros((h, w), bool)
    for x in (60, 85, 110):
        _ring_digit(g, x, 30)
    import cv2
    dist = cv2.distanceTransform((~g).astype(np.uint8), cv2.DIST_L2, 5)
    glow = np.clip(1 - dist / 14.0, 0, 1) * 0.8
    col[glow > 0], a = (240, 160, 60), np.maximum(a, glow)
    col[g], a[g] = (245, 240, 230), 1.0
    bar = np.zeros((h, w), bool)
    bar[90:100, :] = True
    col[bar], a[bar] = (40, 200, 220), 1.0
    tail, bg_a, _ = refine._alpha_tail(a, g, np.ones((h, w), bool), dg._dilate(bar, 3), 32)
    assert 10 <= tail <= 16 and bg_a < 0.05
    rect = dg._box_mask((h, w), [55, 25, 80, 36], 2)
    c2, a2 = col.copy(), a.copy()
    r = refine._clear_alpha_fill(c2, a2, (0, h, 0, w), col, a, col.copy(), a.copy(), g, rect, None, np.ones((h, w), bool), 6.0, 26.0)
    assert r["used"] and r["erase_method"] == "clear_alpha" and r["alpha_tail"] == tail
    assert float(a2[dg._dilate(g, tail) & ~dg._dilate(bar, 4)].max()) < 0.12        # 글자 · 빛 알파가 남지 않음
    assert (a2[bar] == 1.0).all() and float(np.abs(c2[bar] - (40, 200, 220)).max()) < 1e-6
    # 판이 지울 자리 안에 그린 구조물(가로선)은 판 픽셀 그대로 — 막대 윗선 위 빛 자국 자리 [실측 파티 HP 숫자 반원 자국]
    nt, nta = np.zeros((h, w, 3)), np.zeros((h, w))
    nt[bar], nta[bar] = (40, 200, 220), 1.0
    nt[62:64, :], nta[62:64, :] = (190, 250, 240), 1.0
    c3, a3 = col.copy(), a.copy()
    r3 = refine._clear_alpha_fill(c3, a3, (0, h, 0, w), col, a, col.copy(), a.copy(), g, rect, None, np.ones((h, w), bool), 6.0, 26.0,
                                  plate_pad=(_pad(nt), _pad(nta)))
    assert r3["plate_px"] > 0 and float(a3[62:64, 60:130].min()) > 0.95 and float(a3[dg._dilate(g, 6) & ~dg._dilate(np.pad(np.ones((2, w), bool), ((62, h - 64), (0, 0))), 3)].max()) < 0.12


def test_no_truth_needs_a_structure_under_the_text_that_the_plate_does_not_draw():
    h, w = 80, 120
    cw, aw, na = np.zeros((h, w, 3)), np.zeros((h, w)), np.zeros((h, w))
    g = np.zeros((h, w), bool)
    _ring_digit(g, 40, 20)
    track = np.zeros((h, w), bool)
    track[16:50, :52] = True                               # 글자가 앉은 불투명 트랙(파랑) — 오른쪽 끝(가장자리)이 글자 밑에서 끝남
    cw[track], aw[track] = (40, 90, 160), 0.9
    halo = dg._dilate(g, 5) & ~g
    cw[halo & ~track], aw[halo & ~track] = (240, 160, 60), 0.8      # 주황 빛(트랙 밖)
    cw[g], aw[g] = (250, 240, 220), 1.0
    cross = track | (halo & ~track)
    nt = refine._no_truth(cw, aw, na, g, cross, 4.0, (0, h, 0, w))
    assert nt["no_truth"]["ring_frac"] >= refine.NO_TRUTH_RING and nt["no_truth"]["edge_px"] >= 10 and nt["no_truth"]["px"] > 20   # 판은 거기를 투명하게
    same_de = np.zeros((h, w))
    na[track] = 0.9
    assert refine._no_truth(cw, aw, na, g, cross, 4.0, (0, h, 0, w), plate_de=same_de) == {}             # 판도 같게 그림 — 판이 정답(표시 안 함)
    assert refine._no_truth(cw, aw, np.zeros((h, w)), g, np.zeros((h, w), bool), 4.0, (0, h, 0, w)) == {}  # 구조물 없음
    # 빛 고리만 막대에 이어진 글자(구조물 픽셀이 빛 색) — 근거 없음 [실측 파티 이름]
    cw2, aw2 = np.zeros((h, w, 3)), np.zeros((h, w))
    bar = np.zeros((h, w), bool)
    bar[60:70, :] = True
    glow2 = dg._dilate(g, 14) & ~g
    cw2[glow2], aw2[glow2] = (60, 140, 230), 0.95
    cw2[bar], aw2[bar] = (120, 230, 40), 1.0
    cw2[g], aw2[g] = (240, 245, 250), 1.0
    assert refine._no_truth(cw2, aw2, np.where(bar, 1.0, 0.0), g, glow2 | bar, 6.0, (0, h, 0, w)) == {}


# ---------------------------------------------------------------------------------------------------------------------
# V6 · V7 · V8

def test_plan_method_and_pad_level_widen_the_erase_zone():
    assert refine._plan_method("harmonic@2") == ("harmonic", 2) and refine._plan_method("lama") == ("lama", 0) and refine._plan_method(None) == ("off", 0)
    h, w = 90, 120
    cw, aw = np.full((h, w, 3), 30.0), np.ones((h, w))
    g = np.zeros((h, w), bool)
    _ring_digit(g, 50, 30)
    cw[g] = 220
    own = np.zeros((h, w), bool)
    own[28:58, 48:70] = True
    hole = dg._dilate(g, 3)
    z0, _ = refine._erase_zone(cw, aw, cw.copy() * 0 + 30, aw, g, hole, own, 0.0, np.zeros((h, w), bool))
    z2, r2 = refine._erase_zone(cw, aw, cw.copy() * 0 + 30, aw, g, hole, own, 0.0, np.zeros((h, w), bool), pad_level=2)
    assert z2.sum() > z0.sum() and (z0 & ~z2).sum() == 0 and r2["erase_tail"] >= 2 * refine.ERASE_PAD_STEP


def test_ocr_boxes_for_keeps_only_detections_on_the_text_box():
    boxes = [[100, 50, 40, 20], [400, 50, 30, 20], [95, 45, 15, 12], [95, 45, 10, 8]]
    out = refine._ocr_boxes_for(boxes, [10, 5, 30, 15], (90, 45))
    assert [100 - 90, 50 - 45, 40, 20] in out and [5, 0, 15, 12] in out and len(out) == 2      # 먼 검출 · 살짝 걸친 작은 검출(19 %)은 뺌


def test_background_stats_and_complex_background():
    h, w = 80, 120
    hole = np.zeros((h, w), bool)
    hole[30:50, 40:80] = True
    flat = refine._background_stats(np.full((h, w, 3), 50.0), np.ones((h, w)), hole)
    noisy_c = np.random.default_rng(1).uniform(0, 255, (h, w, 3))
    noisy = refine._background_stats(noisy_c, np.ones((h, w)), hole)
    assert flat["edge_frac"] == 0 and not refine.complex_background(flat, CFG)
    assert refine.complex_background(noisy, CFG) and noisy["l_std"] > 12
    # 띠를 가로지르는 곧은 구조선(막대 윗선)은 결이 아님 [실측 파티 HP 숫자 — 첫 판에서 '복잡']
    lined = np.full((h, w, 3), 10.0)
    lined[52:80, :] = (120, 230, 40)
    lined[52:54, :] = (190, 250, 240)
    ls = refine._background_stats(lined, np.ones((h, w)), hole)
    assert ls["line_px"] > 0 and not refine.complex_background(ls, CFG)


def test_erase_ok_rejects_a_candidate_that_spoils_the_concept_state_background():
    """[실측 R20261122_135359 파티 방패 '10' — lama 가 S4 8.5 → 2.4 인데 두 톤 배지를 다시 그려 컨셉 상태 E1 75] 글자 구역 바탕 결함 픽셀이 늘면 못 받음."""
    off = {"local": 8.5, "findings": 1, "lift": 3.5, "contour": 54, "bg_px": 0}
    assert not refine._erase_ok({"local": 2.4, "findings": 0, "lift": 6.7, "contour": 0, "bg_px": 900}, off)
    assert refine._erase_ok({"local": 2.4, "findings": 0, "lift": 6.7, "contour": 0, "bg_px": 10}, off)
    assert refine._erase_ok({"local": 2.4, "findings": 0, "lift": 6.7, "contour": 0}, off)          # 바탕 지표가 없으면 예전 규칙


def test_gate_reverts_a_neighbour_that_made_an_old_plate_text_worse(monkeypatch):
    """[실측 회귀 o_next_1120 첫 판 — 단색 '2/4'] 예전 판(off)으로 둔 글자가 상자가 겹친 이웃의 지우기 탓에 예전보다 나빠지면 그 이웃을 off 로. V1 자리 밖이 다르면 후보 버림."""
    import types
    sc = {b"off": {"A": {"local": 6.0, "findings": 1, "lift": 9.0, "contour": 0}, "B": {"local": 2.0, "findings": 0, "lift": 3.0, "contour": 0}},
          b"harm": {"A": {"local": 1.0, "findings": 0, "lift": 2.0, "contour": 0}, "B": {"local": 5.0, "findings": 1, "lift": 8.0, "contour": 0}}}
    monkeypatch.setattr(refine, "_decode", lambda b: b)
    monkeypatch.setattr(refine, "_gate_scores", lambda run, spec_c, tex, s, gm=None, cache=None: (sc[tex["T"]], {}))
    monkeypatch.setattr(refine, "_outside_changed", lambda a, za, b, zb: {"px": 0 if a != b"bad" else 5})
    log_h = {"windows": [{"item": "A", "used": True, "erase_method": "harmonic"}, {"item": "B", "used": True}]}
    log_o = {"windows": [{"item": "A", "used": True}, {"item": "B", "used": True}]}
    cands = {"T": {"vars": {"off": ({}, log_o, b"off"), "harmonic": ({}, log_h, b"harm"), "lama": ({}, log_h, b"bad")}, "zones": {}, "texts": ["A", "B"]}}
    spec_c = {"widgets": [{"id": "A", "type": "TextBlock", "bbox_intent": [0, 0, 50, 40]}, {"id": "B", "type": "TextBlock", "bbox_intent": [30, 20, 40, 30]}]}

    def rebuild(aid, plan):
        return {}, (log_h if plan.get("A") not in (None, "off") else log_o), (b"harm" if plan.get("A") not in (None, "off") else b"off"), None
    out = refine._gate_erase_choice(types.SimpleNamespace(cfg={}, path=lambda *a: __import__("pathlib").Path(".")), spec_c, {}, cands, rebuild)["T"]
    assert out["outside"]["lama"]["px"] == 5 and out["scores"]["A"]["harmonic"]["local"] == 1.0
    assert out["plan"] == {"A": "off", "B": "off"} and out["off_worse"][0]["texts"] == ["B"] and out["choice"][2] == b"off"


# ---------------------------------------------------------------------------------------------------------------------
# 수동 확인 · 회귀 표

def test_manual_match_only_turns_findings_inside_the_no_truth_spot():
    spec = {"widgets": [{"id": "Pct", "type": "TextBlock", "font": {"glow": {"size": 7}}}, {"id": "Name", "type": "TextBlock"}]}
    checks = [{"reason": "no_truth", "widget": "Pct", "box": [100, 100, 40, 20], "evidence": {"px": 300}}]
    inside = {"check": "text_trace", "widgets": ["Pct"], "box": [98, 96, 46, 30]}
    outside = {"check": "text_trace", "widgets": ["Pct"], "box": [200, 100, 40, 20]}
    other = {"check": "text_trace", "widgets": ["Name"], "box": [100, 100, 40, 20]}
    gauge = {"check": "gauge_outside", "widgets": ["Pct"], "box": [100, 100, 40, 20]}
    assert dg.manual_match(inside, checks, spec)["reason"] == "no_truth"
    assert dg.manual_match(outside, checks, spec) is None and dg.manual_match(other, checks, spec) is None and dg.manual_match(gauge, checks, spec) is None


def test_gate_summary_reads_the_choice_table_and_outside_counts(tmp_path):
    import regress_set
    doc = {"passes": [{"assets": [{"asset_id": "T_plate", "text_erase": {"gate": {
        "plan": {"A": "harmonic", "B": "off"},
        "scores": {"A": {"off": {"local": 6.5, "findings": 1, "lift": 9.0}}, "B": {"off": {"local": 2.0, "findings": 0, "lift": 3.0}}},
        "verify": [{"scores": {"A": {"local": 1.5, "findings": 0, "lift": 3.0}, "B": {"local": 2.0, "findings": 0, "lift": 3.0}}}]}}}],
        "erase_gate": {"T_plate": {"plan": {"A": "harmonic", "B": "off"}, "outside_changed_px": {"lama": 0, "harmonic": 0, "clear_alpha": 3},
                                   "manual_check": [{"widget": "B", "reason": "complex_background"}]}}}]}
    p = tmp_path / "refine.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    g = regress_set.gate_summary(p)
    assert g["texts"]["A"]["chosen"] == [1.5, 0] and g["worse"] == [] and g["outside_total"] == 3 and g["complex"] == ["B"]
