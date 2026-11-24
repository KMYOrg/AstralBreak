"""Phase 2(11-24 — 설계 §11 'Phase 2 설계') — verify 시간 줄이기가 판정을 바꾸지 않는다: ΔE00 을 필요한 픽셀에서만 잰 값 = 전 화면으로 잰 옛 식,
상태 렌더 요청 목록(state_requests)이 진단이 쓰는 렌더 전부, 묶음 렌더(verify.StateRenders) = 한 장씩 · 실패하면 한 장씩. 에디터 없음."""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest
from PIL import Image
from test_state_check import CH, CW, _diag_run

from core import color
from core.ue import ToolchainError
from gen import backdrop, state_check
from gen import diagnose as dg
from stages import verify

RNG = np.random.default_rng(11)


def _pair(h=90, w=130, same: float = 0.6, ints: bool = True):
    """같은 픽셀이 same 비율인 두 그림(정수 PNG 값 또는 합성의 실수 값)."""
    a = RNG.integers(0, 256, (h, w, 3)).astype(float) if ints else RNG.random((h, w, 3)) * 255
    b = np.where(RNG.random((h, w, 1)) < same, a, RNG.integers(0, 256, (h, w, 3)).astype(float))
    return a, b


def _old_delta_e(a, b):
    return color.delta_e00(color.srgb_to_lab(a), color.srgb_to_lab(b)).astype(np.float32)


def _old_shift_min(a, b, box, r=dg.SHIFT_TOL):
    x0, y0, x1, y1 = box
    H, W = np.shape(a)[:2]
    la = color.srgb_to_lab(np.asarray(a, float)[y0:y1, x0:x1])
    best = None
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            ys = np.clip(np.arange(y0, y1) + dy, 0, H - 1)
            xs = np.clip(np.arange(x0, x1) + dx, 0, W - 1)
            d = color.delta_e00(la, color.srgb_to_lab(np.asarray(b, float)[np.ix_(ys, xs)]))
            best = d if best is None else np.minimum(best, d)
    return np.asarray(best, np.float32)


@pytest.mark.parametrize("ints", [True, False])
def test_delta_e_equals_the_full_frame_formula(ints):
    a, b = _pair(ints=ints)
    new = dg.delta_e(a, b)
    assert new.dtype == np.float32 and np.allclose(new, _old_delta_e(a, b), rtol=1e-6, atol=1e-6)
    assert (new[(a == b).all(axis=-1)] == 0).all()                                 # 같은 픽셀은 정확히 0(옛 식도 0)
    assert (_old_delta_e(a, b)[(a == b).all(axis=-1)] == 0).all()
    m = RNG.random(a.shape[:2]) < 0.3
    w = dg.delta_e(a, b, where=m)
    assert (w[m] == new[m]).all() and (w[~m] == 0).all()
    assert (dg.delta_e(a.astype(np.uint8), b.astype(np.uint8))[..., None].shape[:2] == a.shape[:2])
    if ints:
        assert np.allclose(dg.delta_e(a.astype(np.uint8), b), new, atol=1e-6)      # 정수 렌더 ↔ 실수 합성
    assert dg.delta_e(a[m], b[m]).shape == (int(m.sum()),)                         # 픽셀 목록(N, 3)도 그대로


def test_shift_min_equals_the_old_loop_at_the_frame_edge_too():
    a, b = _pair(40, 56)
    b = np.roll(b, 1, axis=1)
    for box in ((5, 4, 30, 28), (0, 0, 20, 12), (40, 30, 56, 40)):
        new, old = dg._shift_min_de(a, b, box), _old_shift_min(a, b, box)
        assert new.shape == old.shape and np.allclose(new, old, atol=1e-5)
        z = RNG.random(new.shape) < 0.4
        part = dg._shift_min_de(a, b, box, where=z)
        assert (part[z] == new[z]).all() and (part[~z] == 0).all()


def test_explain_diff_is_the_same_inside_the_zone():
    """설명 지도 — 자리(zone) 안만 재도 옛 전 상자 계산과 같다(자리 밖은 둘 다 0)."""
    img, concept = _pair(60, 80, same=0.5)
    zone = np.zeros((60, 80), bool)
    zone[20:40, 25:60] = True
    ring = dg._dilate(zone, 6) & ~zone
    foot = np.zeros_like(zone)
    foot[28:32, 30:50] = True
    got = state_check.explain_diff(img, concept, zone, ring, foot)
    f = np.asarray(img, np.float32)
    lab = color.srgb_to_lab(f)
    d = np.full(zone.shape, 1e9, np.float32)
    est, ok = state_check._near_estimate(f, ring)
    d = np.where(ok, np.minimum(d, color.delta_e00(lab, color.srgb_to_lab(est)).astype(np.float32)), d)
    for ax in (0, 1):
        est, ok = state_check._band_estimate(f, zone, ring, ax)
        d = np.where(ok, np.minimum(d, color.delta_e00(lab, color.srgb_to_lab(est)).astype(np.float32)), d)
    med = np.broadcast_to(np.median(f[ring], axis=0), f.shape)
    d = np.minimum(d, color.delta_e00(lab, color.srgb_to_lab(np.asarray(med, np.float32))).astype(np.float32))
    d = np.where(~foot, np.minimum(d, color.delta_e00(lab, color.srgb_to_lab(np.asarray(concept, np.float32))).astype(np.float32)), d)
    assert np.allclose(got, np.where(zone, d, 0.0), atol=1e-5) and (got[~zone] == 0).all()


# ---------------------------------------------------------------------------------------------------------------------
# 상태 렌더 묶음

def _engine(rd: pathlib.Path, out: pathlib.Path):
    """합성으로 흉내 낸 엔진 렌더 — overrides 의 visible 만 본다."""
    spec = json.loads((rd / "spec.json").read_text(encoding="utf-8"))
    boxes = json.loads((rd / "geometry.json").read_text(encoding="utf-8"))["geometry"][f"{CW}x{CH}"]
    tex = {"plate": backdrop._load(rd / "assets" / "final" / "plate.png")}
    calls: list[tuple[str, dict]] = []

    def draw(overrides, name="state"):
        calls.append((name, overrides))
        img = backdrop.compose(dg._without(spec, {w for w, o in overrides.items() if o.get("visible") is False}), boxes, tex, [CW, CH], (0, 0, 0))[0]
        p = out / f"{name}_{len(calls)}.png"
        out.mkdir(parents=True, exist_ok=True)
        Image.fromarray(img.astype(np.uint8)).save(p)
        return str(p)
    draw.calls = calls
    return draw


def test_diagnose_uses_only_the_requested_states_and_prefetch_changes_nothing(tmp_path):
    rd = _diag_run(tmp_path)
    plain = _engine(rd, tmp_path / "plain")
    rec = dg.diagnose(rd, None, {"appearance": {"state_checks": "error"}}, pictures=False, render_state=plain)
    batch = _engine(rd, tmp_path / "batch")

    class Pre:
        def __init__(self):
            self.reqs, self.used = {}, []

        def prefetch(self, reqs):
            self.reqs = {n: (ov, batch(ov, n)) for n, ov in reqs.items()}

        def __call__(self, overrides, name="state"):
            assert name in self.reqs and self.reqs[name][0] == overrides            # 묶음 밖 · 다른 값의 렌더를 부르지 않는다
            self.used.append(name)
            return self.reqs[name][1]
    pre = Pre()
    rec2 = dg.diagnose(rd, None, {"appearance": {"state_checks": "error"}}, pictures=False, render_state=pre)
    drop = ("state",)
    a, b = ({k: v for k, v in r.items() if k not in drop} for r in (rec, rec2))
    assert json.dumps(a, sort_keys=True, default=float) == json.dumps(b, sort_keys=True, default=float)
    assert set(pre.used) == set(pre.reqs) == {n for n, _ in plain.calls} and {"state", "state_off", "state_notext"} <= set(pre.reqs)
    off = dg.diagnose(rd, None, {"appearance": {"state_checks": "off"}}, pictures=False, render_state=(p2 := Pre()))
    assert list(p2.reqs) == ["state"] and "state_checks" not in off


def test_state_requests_cover_gauges_bars_rings_and_hidden_groups():
    spec = {"canvas": [400, 200], "root": "Root", "assets": [{"asset_id": "bar", "source_mode": "extract"}], "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Gauge", "type": "ProgressBar", "parent": "Root", "style": {"percent": 0.7, "fill": {"draw_as": "image", "asset": "g"}}},
        {"id": "Up", "type": "ProgressBar", "parent": "Root", "style": {"percent": 0.7, "bar_fill_type": "bottom_to_top", "fill": {"draw_as": "image", "asset": "g"}}},
        {"id": "Bar", "type": "ProgressBar", "parent": "Root", "style": {"percent": 1.0, "fill": {"draw_as": "image", "asset": "bar"},
                                                                         "background": {"draw_as": "image", "asset": "bar", "color": "#404144CC"}}},
        {"id": "Empty", "type": "ProgressBar", "parent": "Root", "style": {"percent": 0.7, "fill": {"draw_as": "none"}}},
        {"id": "Ring", "type": "Image", "parent": "Root", "style": {"percent": 1.0, "brush": {"draw_as": "image", "asset": "ring", "wipe": {"mode": "clockwise"}}}},
        {"id": "NoTex", "type": "Image", "parent": "Root", "style": {"brush": {"draw_as": "image", "asset": "gone", "wipe": {"mode": "clockwise"}}}},
        {"id": "Value", "type": "TextBlock", "parent": "Root", "text": {"source": "dynamic", "sample": "42"}},
        {"id": "Banner", "type": "Image", "parent": "Root", "visibility": "collapsed", "style": {"brush": {"draw_as": "image", "asset": "banner"}}},
        {"id": "BannerText", "type": "TextBlock", "parent": "Banner", "text": {"source": "static", "value": "B"}},
    ]}
    boxes = [{"id": w["id"], "x": 0, "y": 0, "w": 100, "h": 40, "visible": True} for w in spec["widgets"]]
    tex = {k: np.zeros((8, 8, 4)) for k in ("g", "bar", "ring", "banner")}
    states = [{"widget": "Banner", "subtree": ["Banner", "BannerText"], "drawn_in_concept": True}]
    r = state_check.state_requests(spec, spec, states, boxes, tex)
    assert r["state"] == {"Banner": {"visible": True}} and r["state_off"] == {"Banner": {"visible": False}}
    assert {n for n in r if n.startswith("state_Gauge_")} == {"state_Gauge_000", "state_Gauge_005", "state_Gauge_100"}
    assert {n for n in r if n.startswith("state_Bar_")} == {state_check.percent_name("Bar", p) for p in state_check.BAR_STATES}
    assert {n for n in r if n.startswith("state_Ring_")} == {state_check.percent_name("Ring", p) for p in state_check.RADIAL_STATES}
    assert r["state_Ring_040"] == {"Banner": {"visible": True}, "Ring": {"percent": 0.4}}
    assert not [n for n in r if n.startswith(("state_Up_", "state_Empty_", "state_NoTex_"))]      # 세로 · 채움 없음 · 텍스처 없음
    assert r["state_notext"]["Value"] == {"text": ""} and r["state_notext"]["Banner"] == {"visible": False}
    assert "BannerText" not in r["state_notext"]                                                     # 접힌 글자는 S1 몫
    assert r["state_values"] == {"Banner": {"visible": False}, "Value": {"text": "97"}}
    assert r["state_notext_Banner"] == {"Banner": {"visible": True}, "Value": {"text": ""}, "BannerText": {"text": ""}}
    assert list(state_check.state_requests(spec, spec, states, boxes, tex, checks=False)) == ["state"]


class _Tc:
    """render_widget 만 아는 가짜 — states 를 받거나(new) 모르거나(old) 도중에 실패한다(broken)."""

    def __init__(self, mode: str):
        self.mode, self.calls = mode, []

    def call(self, tool, params=None, timeout=180.0):
        self.calls.append(params)
        out = pathlib.Path(params["output_dir"])
        if "states" in params:
            if self.mode == "old":
                raise ToolchainError("OUTPUT_DIR_NOT_EMPTY", "output_dir is not empty")
            res = []
            for st in params["states"]:
                if self.mode == "broken" and st["name"] == "b":
                    raise ToolchainError("READBACK", "ReadPixels failed")
                d = out / st["name"]
                assert not (d.is_dir() and any(d.iterdir()))
                d.mkdir(parents=True)
                (d / f"{st['name']}_4x4.png").write_text(json.dumps(st["overrides"]), encoding="utf-8")
                res.append({"name": st["name"], "renders": [{"png": str(d / f"{st['name']}_4x4.png")}]})
            return {"states": res, "seconds": 2.1}
        if out.is_dir() and any(out.iterdir()):
            raise ToolchainError("OUTPUT_DIR_NOT_EMPTY", str(out))
        out.mkdir(parents=True)
        p = out / f"{params['prefix']}_4x4.png"
        p.write_text(json.dumps(params["overrides"]), encoding="utf-8")
        return {"renders": [{"png": str(p)}]}


REQS = {"a": {"X": {"percent": 0.1}}, "b": {"X": {"percent": 0.2}}}


def test_state_renders_batch_hits_and_falls_back_one_by_one(tmp_path):
    (tmp_path / "new").mkdir()
    tc = _Tc("new")
    sr = verify.StateRenders(tc, "/Game/W", tmp_path / "new", [4, 4])
    sr.prefetch(REQS)
    assert sr.record["batch"] == 2 and len(tc.calls) == 1 and tc.calls[0]["states"][1] == {"name": "b", "overrides": REQS["b"]}
    assert pathlib.Path(sr(REQS["a"], "a")) == tmp_path / "new" / "a" / "a_4x4.png" and sr.record["single"] == 0   # 폴더 · 이름은 한 장씩 부를 때와 같다
    assert json.loads(pathlib.Path(sr({"X": {"percent": 0.9}}, "a")).read_text(encoding="utf-8")) == {"X": {"percent": 0.9}}   # 값이 다르면 새로 그린다
    assert sr.record["single"] == 1
    for mode in ("old", "broken"):
        (tmp_path / mode / "render").mkdir(parents=True)
        (tmp_path / mode / "render" / "x.png").write_text("x", encoding="utf-8")
        tc = _Tc(mode)
        sr = verify.StateRenders(tc, "/Game/W", tmp_path / mode, [4, 4])
        sr.prefetch(REQS)
        assert sr.record["batch"] == 0 and sr.record["error"]
        for n, ov in REQS.items():                                                   # 묶음이 도중에 남긴 폴더가 있어도 그린다
            assert json.loads(pathlib.Path(sr(ov, n)).read_text(encoding="utf-8")) == ov
        assert sr.record["single"] == 2
