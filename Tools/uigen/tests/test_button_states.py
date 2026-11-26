"""Phase 3-2 — 버튼 상태: 공용 테마의 식(gen/theme) · 상태 검사(gen/state_check.button_states). 먼저 **일부러 틀린 값**(올림 ↔ 누름 바꿈 · 비활성 빠짐 ·
여백 밀림 · 덮어쓰기가 안 먹음 …)이 오류로 잡히는지 본다 — 잡지 못하는 검사의 '통과'는 뜻이 없다. 에디터 없음(엔진 렌더 = 합성 + 글자를 손으로 그린 그림)."""
from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from core import button
from gen import backdrop, cells, state_check, theme
from gen import diagnose as dg

W, H = 240, 72
LABEL = [84, 22, 72, 28]


def art() -> np.ndarray:
    """먹색 판(알파 235) + 금선 테두리 + 왼쪽 끝 사선(투명) — HxWx4 uint8."""
    c = np.zeros((H, W, 4), np.uint8)
    yy, xx = np.mgrid[0:H, 0:W]
    body = (xx >= 8 + yy // 4) & (xx < W - 8) & (yy >= 6) & (yy < H - 6)
    c[body] = (22, 21, 24, 235)
    c[body, 0] += (xx[body] * 14 // W).astype(np.uint8)
    edge = body & ((yy < 8) | (yy >= H - 8) | (xx >= W - 10))
    c[edge] = (205, 190, 150, 255)
    return c


def scene():
    """버튼 칸 하나 — (spec, boxes, textures). 상태 그림 = 테마의 식."""
    t = theme.load("blade")
    base = art()
    tex = {"button_art": base.astype(float)}
    states = {}
    for b in button.DERIVED:
        aid = button.derived_asset_id("button_art", b)
        tex[aid] = theme.state(base, b, t).astype(float)
        states[b] = aid
    spec = {"schema_version": 1, "canvas": [W, H], "profile": "cell", "root": "Root",
            "widgets": [{"id": "Root", "type": "CanvasPanel"},
                        {"id": "ButtonArt", "type": "Image", "parent": "Root", "slot": {"kind": "canvas"}, "style": {"brush": {"draw_as": "image", "asset": "button_art"}}},
                        {"id": "ButtonLabel", "type": "TextBlock", "parent": "Root", "slot": {"kind": "canvas", "z": 1}, "font": {"size": 18, "color": "#ECE5D6FF"}}],
            "assets": [{"asset_id": "button_art", "size": [W, H], "provenance": "codex"}]
            + [{"asset_id": a, "size": [W, H], "provenance": "derived", "derived": {"from": "button_art", "brush": b}} for b, a in states.items()],
            "button": {"art": "ButtonArt", "states": states, "theme": {"id": "blade", "sha256": t["sha256"]}, "pressed_offset": [0, 1]}}
    boxes = [{"id": "Root", "x": 0, "y": 0, "w": W, "h": H, "visible": True}, {"id": "ButtonArt", "x": 0, "y": 0, "w": W, "h": H, "visible": True},
             {"id": "ButtonLabel", "x": LABEL[0], "y": LABEL[1], "w": LABEL[2], "h": LABEL[3], "visible": True}]
    return spec, boxes, tex


def strokes() -> np.ndarray:
    m = np.zeros((H, W), bool)
    for x in range(LABEL[0] + 4, LABEL[0] + LABEL[2] - 6, 12):
        m[LABEL[1] + 5:LABEL[1] + 23, x:x + 4] = True
        m[LABEL[1] + 12:LABEL[1] + 15, x:x + 9] = True
    return m


def picture(spec, boxes, tex, asset: str, shift=(0, 0), color=(236, 229, 214), label=True, box_shift=(0, 0)) -> np.ndarray:
    """엔진 렌더 흉내 — 그 에셋을 버튼 자리에 그리고 글자를 얹는다."""
    sp = {**spec, "widgets": [{**w, "style": {"brush": {"draw_as": "image", "asset": asset}}} if w["id"] == "ButtonArt" else w for w in spec["widgets"]]}
    bx = [{**b, "x": b["x"] + box_shift[0], "y": b["y"] + box_shift[1]} if b["id"] == "ButtonArt" else b for b in boxes]
    img = backdrop.compose(sp, bx, tex, [W, H], (0, 0, 0))[0].copy()
    if label:
        img[np.roll(strokes(), (shift[1], shift[0]), (0, 1))] = color
    return img


def engine(spec, boxes, tex, wrong: dict | None = None):
    """상태 이름 → 그림. wrong = {상태: 그림 또는 예외}."""
    used = button.brush_assets(spec)

    def draw(name):
        b = name.split("_", 2)[2]
        w = (wrong or {}).get(b)
        if isinstance(w, Exception):
            raise w
        if w is not None:
            return w
        return picture(spec, boxes, tex, used[b], shift=(0, 1) if b.endswith("pressed") else (0, 0), color=(110, 108, 104) if b == "disabled" else (236, 229, 214))
    return draw


def check(wrong=None, s=None):
    spec, boxes, tex = scene()
    base = picture(spec, boxes, tex, "button_art")
    w = wrong(spec, boxes, tex) if callable(wrong) else wrong
    r = state_check.button_states(spec, boxes, tex, [W, H], s or dg.settings(None), base, render_state=engine(spec, boxes, tex, w))
    return r, {(f["check"], f.get("brush")) for f in r["findings"]}


# ---------------------------------------------------------------------------------------------------------------------
# 테마의 식

def test_theme_states_keep_the_alpha_and_differ_from_each_other():
    t = theme.load("blade")
    base = art()
    out = {b: theme.state(base, b, t) for b in button.BRUSHES}
    assert (out[button.BASE] == base).all()
    for b in button.DERIVED:
        want = base[..., 3] if b != "disabled" else np.round(base[..., 3] * 0.5)
        assert np.abs(out[b][..., 3].astype(float) - want).max() <= 1, b          # 윤곽은 상태마다 같다(비활성만 × 0.5)
    solid = base[..., 3] > 128
    lum = {b: float((out[b][..., :3].astype(float) @ theme.LUM)[solid].mean()) for b in button.BRUSHES}
    assert lum["normal_pressed"] < lum["normal_base"] < lum["normal_hovered"] and lum["normal_base"] < lum["selected_base"]
    assert np.ptp(out["disabled"][..., :3].astype(int), axis=-1).max() == 0        # 무채색


def test_theme_errors_are_not_filled_in(tmp_path):
    t = theme.load("blade")
    with pytest.raises(theme.ThemeError, match="not a button state"):
        theme.state(art(), "hovered", t)
    p = tmp_path / "theme_blade.yaml"
    raw = theme.path_of("blade").read_text(encoding="utf-8")
    p.write_text(raw.replace("  accent:", "  accent_x:"), encoding="utf-8")
    with pytest.raises(theme.ThemeError, match="accent"):
        theme.load("blade", p)
    p.write_text(raw.replace("id: blade", "id: other"), encoding="utf-8")
    with pytest.raises(theme.ThemeError, match="id 'other'"):
        theme.load("blade", p)


def test_theme_hash_ignores_comments_and_line_endings(tmp_path):
    raw = theme.path_of("blade").read_text(encoding="utf-8")
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    a.write_bytes(raw.replace("\r\n", "\n").encode("utf-8"))
    b.write_bytes(("# more\n" + raw.replace("\r\n", "\n")).replace("\n", "\r\n").encode("utf-8"))
    assert theme.load("blade", a)["sha256"] == theme.load("blade", b)["sha256"] == theme.load("blade")["sha256"]
    b.write_text(raw.replace("plate: 0.5", "plate: 0.6"), encoding="utf-8")
    assert theme.load("blade", b)["sha256"] != theme.load("blade")["sha256"]


def test_derive_writes_the_same_picture_twice(tmp_path):
    Image.fromarray(art(), "RGBA").save(tmp_path / "base.png")
    t = theme.load("blade")
    size, alpha = theme.derive(tmp_path / "base.png", tmp_path / "a.png", "normal_hovered", t)
    theme.derive(tmp_path / "base.png", tmp_path / "b.png", "normal_hovered", t)
    assert size == [W, H] and alpha and (tmp_path / "a.png").read_bytes() == (tmp_path / "b.png").read_bytes()


# ---------------------------------------------------------------------------------------------------------------------
# 상태 검사 — 옳은 렌더는 깨끗하고, 틀린 값은 잡힌다

def test_correct_states_are_clean():
    r, f = check()
    assert f == set(), r["findings"]
    rec = r["buttons"][0]
    assert r["renderer"] == "engine" and rec["widget"] == "ButtonArt" and set(rec["states"]) == set(button.BRUSHES)
    assert len(rec["distinct"]) == 21 and min(rec["distinct"].values()) >= 2.0      # 상태 일곱의 모든 쌍
    assert rec["states"]["normal_pressed"]["text_shift"] == [0, 1] and rec["states"]["normal_hovered"]["text_shift"] == [0, 0]
    assert set(r["images"]["ButtonArt"]) == set(r["gray"]["ButtonArt"]) == set(button.BRUSHES)


def test_wrong_hovered_and_pressed_swapped():
    def wrong(spec, boxes, tex):
        u = button.brush_assets(spec)
        return {"normal_hovered": picture(spec, boxes, tex, u["normal_pressed"]), "normal_pressed": picture(spec, boxes, tex, u["normal_hovered"], shift=(0, 1))}
    _, f = check(wrong)
    assert ("button_state", "normal_hovered") in f and ("button_state", "normal_pressed") in f


def test_wrong_disabled_brush_missing():
    """비활성 브러시가 비어 아무것도 안 그린다(글자만) · 엔진이 기본 그림을 그대로 그린다 — 둘 다."""
    def empty(spec, boxes, tex):
        img = np.zeros((H, W, 3))
        img[strokes()] = (110, 108, 104)
        return {"disabled": img}
    _, f = check(empty)
    assert ("button_state", "disabled") in f
    _, f = check(lambda spec, boxes, tex: {"disabled": picture(spec, boxes, tex, "button_art")})
    assert ("button_state", "disabled") in f


@pytest.mark.parametrize("shift", [(3, 0), (0, 3), (-3, 2)])
def test_wrong_margin_shifted(shift):
    def wrong(spec, boxes, tex):
        return {"normal_hovered": picture(spec, boxes, tex, button.brush_assets(spec)["normal_hovered"], box_shift=shift)}
    _, f = check(wrong)
    assert ("button_state", "normal_hovered") in f


def test_wrong_override_not_taken_is_an_error_not_a_composite():
    """덮어쓰기가 안 먹으면 render_widget 이 오류를 낸다 — 검사는 합성으로 물러나지 않고 오류로 적는다. 오류 없이 기본 그림이 나와도 잡힌다."""
    from core.ue import ToolchainError
    _, f = check({"selected_pressed": ToolchainError("OVERRIDE_NOT_APPLIED", "render_widget: button 'selected_pressed' did not take", error={}, tool="render_widget")})
    assert ("button_render", "selected_pressed") in f
    for b in button.DERIVED:
        _, f = check(lambda spec, boxes, tex, b=b: {b: picture(spec, boxes, tex, "button_art", shift=(0, 1) if b.endswith("pressed") else (0, 0))})
        assert ("button_state", b) in f, b


def test_wrong_label_hidden_moved_or_too_faint():
    u = "button_art_normal_hovered"
    _, f = check(lambda spec, boxes, tex: {"normal_hovered": picture(spec, boxes, tex, u, label=False)})
    assert ("button_text", "normal_hovered") in f
    _, f = check(lambda spec, boxes, tex: {"normal_hovered": picture(spec, boxes, tex, u, shift=(2, 0))})
    assert ("button_text_moved", "normal_hovered") in f
    _, f = check(lambda spec, boxes, tex: {"normal_pressed": picture(spec, boxes, tex, "button_art_normal_pressed")})      # 눌러도 글자가 안 움직임
    assert ("button_text_moved", "normal_pressed") in f
    _, f = check(lambda spec, boxes, tex: {"disabled": picture(spec, boxes, tex, "button_art_disabled", color=(30, 29, 29))})
    assert ("button_text", "disabled") in f


def test_wrong_something_outside_the_button_changes():
    """버튼 밖(다른 요소 자리)이 상태에 따라 바뀌면 잡힌다 — 화면에 놓인 버튼을 흉내 내 캔버스를 넓힌다."""
    spec, boxes, tex = scene()
    big = [W + 80, H]
    used = button.brush_assets(spec)

    def wide(img):
        out = np.zeros((H, W + 80, 3))
        out[:, :W] = img
        return out
    boxes = [{**b, "w": W + 80} if b["id"] == "Root" else b for b in boxes]

    def draw(name):
        b = name.split("_", 2)[2]
        img = wide(engine(spec, [x if x["id"] != "Root" else {**x, "w": W} for x in boxes], tex)(name))
        if b == "normal_hovered":
            img[20:50, W + 20:W + 60] = (200, 180, 90)
        return img
    r = state_check.button_states(spec, boxes, tex, big, dg.settings(None), wide(picture(spec, boxes, tex, "button_art")), render_state=draw)
    assert {(f["check"], f["brush"]) for f in r["findings"]} == {("button_outside", "normal_hovered")}
    assert len(used) == 7


def test_same_looking_states_are_errors_offline_too():
    """엔진이 없어도(회귀 묶음 · 정답 묶음) 상태끼리 같으면 잡는다 — 안쪽 판정은 합성끼리라 뜻이 없어 통과로 세지 않는다(renderer composite)."""
    spec, boxes, tex = scene()
    tex["button_art_selected_base"] = tex["button_art"].copy()
    r = state_check.button_states(spec, boxes, tex, [W, H], dg.settings(None), picture(spec, boxes, tex, "button_art", label=False))
    assert r["renderer"] == "composite" and {(f["check"], f["brush"]) for f in r["findings"]} == {("button_same", "selected_base")}


def test_states_that_differ_only_in_alpha_are_distinct_on_gray():
    """검정 바탕에서는 누름 ↔ 비활성이 거의 같다(투명도 차이가 숨는다) — 회색 바탕 합성이 가른다."""
    spec, boxes, tex = scene()
    tex["button_art_disabled"] = tex["button_art_normal_pressed"].copy()
    tex["button_art_disabled"][..., 3] *= 0.5
    base = picture(spec, boxes, tex, "button_art", label=False)
    r = state_check.button_states(spec, boxes, tex, [W, H], dg.settings(None), base)
    rec = r["buttons"][0]
    assert rec["distinct_black"]["normal_pressed / disabled"] < rec["distinct"]["normal_pressed / disabled"] and rec["distinct"]["normal_pressed / disabled"] > 10
    assert r["findings"] == []


def test_state_requests_lists_every_button_state_once():
    spec, boxes, tex = scene()
    reqs = state_check.state_requests(spec, spec, [], boxes, tex)
    names = {state_check.button_name("ButtonArt", b): {".": button.OVERRIDES[b]} for b in button.DERIVED}
    assert {k: v for k, v in reqs.items() if k.startswith("state_ButtonArt_")} == names
    assert button.OVERRIDES["disabled"] == {"enabled": False} and button.OVERRIDES["selected_pressed"] == {"button": "selected_pressed"}
    assert not any(k.startswith("state_ButtonArt_") for k in state_check.state_requests(spec, spec, [], boxes, tex, checks=False))
    plain = {**spec, "button": None}
    assert state_check.button_targets(plain, boxes, tex) == []


# ---------------------------------------------------------------------------------------------------------------------
# 화면에 놓인 버튼 칸 — 칸은 자기 묶음에서 합성한 그림 한 장(상태마다 한 장)

CLS = "/Game/UI/Common/ButtonLarge/WBP_ButtonLarge.WBP_ButtonLarge_C"


@pytest.fixture
def promoted(tmp_path, monkeypatch):
    """승격 묶음 하나(promoted/ButtonLarge) — (폴더, spec, 텍스처)."""
    spec, boxes, tex = scene()
    d = tmp_path / "promoted" / "ButtonLarge"
    (d / "source" / "assets" / "final").mkdir(parents=True)
    for aid, t in tex.items():
        Image.fromarray(t.astype(np.uint8), "RGBA").save(d / "source" / "assets" / "final" / f"{aid}.png")
    (d / "promotion.json").write_text(json.dumps({"screen_id": "ButtonLarge", "wbp": CLS.rsplit("_C", 1)[0]}), encoding="utf-8")
    (d / "source" / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (d / "source" / "geometry.json").write_text(json.dumps({"geometry": {f"{W}x{H}": boxes}}), encoding="utf-8")
    (d / "source" / "manifest.json").write_text(json.dumps({"assets": [{"asset_id": a, "file": f"assets/final/{a}.png"} for a in tex]}), encoding="utf-8")
    monkeypatch.setattr(cells, "ROOT", tmp_path / "promoted")
    return d, spec, tex


def screen():
    spec = {"canvas": [400, 200], "root": "Root", "assets": [], "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Ready", "type": "UserWidget", "class": CLS, "parent": "Root", "slot": {"kind": "canvas"}, "props": {"ButtonText": "준비"}}]}
    boxes = [{"id": "Root", "x": 0, "y": 0, "w": 400, "h": 200, "visible": True}, {"id": "Ready", "x": 100, "y": 60, "w": W, "h": H, "visible": True}]
    return spec, boxes


def test_a_placed_cell_is_composed_from_its_own_pictures(promoted):
    _, cell, tex = promoted
    spec, boxes = screen()
    textures = cells.attach(spec, {})
    assert set(textures) == {cells.key(CLS, b) for b in button.BRUSHES}
    img, cov, info = backdrop.compose(spec, boxes, textures, [400, 200], (128, 128, 128))
    own = backdrop.compose(cell, [boxes[0], {"id": "ButtonArt", "x": 100, "y": 60, "w": W, "h": H, "visible": True}], tex, [400, 200], (128, 128, 128))[0]
    assert np.abs(img - own).max() < 1.0 and not info.get("missing")
    t = cells.text_boxes(spec, boxes)
    assert t == [("Ready", [100 + LABEL[0], 60 + LABEL[1], LABEL[2], LABEL[3]])]


def test_the_label_box_of_a_placed_cell_is_the_drawn_one(promoted):
    """놓은 화면이 글자를 정한다 — 칸 혼자 그린 보기 글자보다 길면 그 자리도 길다(안쪽 판정이 글자를 '틀린 그림'으로 세지 않게) [실측 '봉인된 유적' ΔE 74]."""
    spec, boxes = screen()
    boxes.append({"id": "Ready/ButtonLabel", "type": "TextBlock", "parent": "Ready", "x": 140, "y": 80, "w": 160, "h": 30, "visible": True})
    assert cells.text_boxes(spec, boxes) == [("Ready", [140.0, 80.0, 160.0, 30.0])]
    boxes[-1]["visible"] = False
    assert cells.text_boxes(spec, boxes) == []


def test_an_unknown_cell_is_missing_not_silent(promoted):
    spec, boxes = screen()
    spec["widgets"][1]["class"] = "/Game/UI/Common/Nope/WBP_Nope.WBP_Nope_C"
    textures = cells.attach(spec, {})
    assert textures == {}
    info = backdrop.compose(spec, boxes, textures, [400, 200], (0, 0, 0))[2]
    assert info["missing"]


def test_a_placed_button_is_checked_under_its_own_name(promoted):
    """놓인 버튼 — 덮어쓰기 열쇠 = 칸 이름, 틀린 상태는 잡히고 다른 자리는 안 바뀌어야 한다."""
    _, cell, _ = promoted
    spec, boxes = screen()
    textures = cells.attach(spec, {})
    reqs = state_check.state_requests(spec, spec, [], boxes, textures)
    assert reqs["state_Ready_normal_hovered"] == {"Ready": {"button": "hovered"}} and reqs["state_Ready_disabled"] == {"Ready": {"enabled": False}}

    def put(b, text=True, shift=(0, 0)):
        sp, tx = spec, {**textures, cells.key(CLS): textures[cells.key(CLS, b)]}
        img = backdrop.compose(sp, boxes, tx, [400, 200], (0, 0, 0))[0].copy()
        m = np.zeros((200, 400), bool)
        m[60:60 + H, 100:100 + W] = np.roll(strokes(), (shift[1], shift[0]), (0, 1))
        if text:
            img[m] = (236, 229, 214) if b != "disabled" else (110, 108, 104)
        return img
    r = state_check.button_states(spec, boxes, textures, [400, 200], dg.settings(None), put(button.BASE),
                                  render_state=lambda n: put(n.split("_", 2)[2], shift=(0, 1) if n.endswith("pressed") else (0, 0)))
    assert r["findings"] == [], r["findings"]
    r = state_check.button_states(spec, boxes, textures, [400, 200], dg.settings(None), put(button.BASE),
                                  render_state=lambda n: put("normal_pressed" if n.endswith("normal_hovered") else n.split("_", 2)[2], shift=(0, 1) if n.endswith("pressed") else (0, 0)))
    assert ("button_state", "normal_hovered") in {(f["check"], f["brush"]) for f in r["findings"]}
    assert r["findings"][0]["widgets"] == ["Ready"]


def test_two_placed_buttons_of_one_cell_change_only_themselves(promoted):
    """같은 칸을 둘 놓은 화면(HubReady 준비 · 출정) — 한 버튼의 상태 합성은 그 버튼만 바꾼다(엔진 덮어쓰기는 위젯 하나에만). 예전(클래스 열쇠를 바꿈)은
    다른 버튼까지 바뀌어, 에디터 없는 재진단에서 '버튼 밖이 바뀜'(button_outside)으로 셌다 [실측 HubReady 16 건]."""
    spec = {"canvas": [600, 200], "root": "Root", "assets": [], "widgets": [{"id": "Root", "type": "CanvasPanel"}]
            + [{"id": i, "type": "UserWidget", "class": CLS, "parent": "Root", "slot": {"kind": "canvas"}} for i in ("Ready", "Launch")]}
    boxes = [{"id": "Root", "x": 0, "y": 0, "w": 600, "h": 200, "visible": True},
             {"id": "Ready", "x": 20, "y": 60, "w": W, "h": H, "visible": True}, {"id": "Launch", "x": 320, "y": 60, "w": W, "h": H, "visible": True}]
    textures = cells.attach(spec, {})
    base = backdrop.compose(spec, boxes, textures, [600, 200], (0, 0, 0))[0]
    targets = {t["id"]: t for t in state_check.button_targets(spec, boxes, textures)}
    assert set(targets) == {"Ready", "Launch"}
    for wid, own in (("Ready", boxes[1]), ("Launch", boxes[2])):
        mine = dg._box_mask((200, 600), [own["x"], own["y"], own["w"], own["h"]])
        for b in button.DERIVED:
            sp, tx = targets[wid]["state"](b)
            diff = np.abs(backdrop.compose(sp, boxes, tx, [600, 200], (0, 0, 0))[0] - base)
            assert diff[~mine].max() < 1e-6, (wid, b)                                   # 다른 버튼 · 바탕은 그대로
        sp, tx = targets[wid]["state"]("normal_hovered")
        assert np.abs(backdrop.compose(sp, boxes, tx, [600, 200], (0, 0, 0))[0] - base)[mine].max() > 1.0     # 그 버튼은 바뀐다
    r = state_check.button_states(spec, boxes, textures, [600, 200], dg.settings(None), base)          # 오프라인 — 합성끼리
    assert r["findings"] == [], r["findings"]


def test_compare_picture_gets_a_row_per_button_state():
    spec, boxes, tex = scene()
    r, _ = check()
    band = {"off": {}, "gauges": {}, "buttons": r["images"], "buttons_gray": r["gray"], "buttons_renderer": "engine", "button_boxes": {"ButtonArt": [0, 0, W, H]}}
    rows = dg._band_rows(band, 1900)
    assert len(rows) == len(button.BRUSHES)
    missing = {**band, "buttons": {"ButtonArt": {k: v for k, v in r["images"]["ButtonArt"].items() if k != "disabled"}}}
    assert len(dg._band_rows(missing, 1900)) == len(button.BRUSHES)                 # 못 그린 상태도 칸은 남는다('NOT RENDERED')
