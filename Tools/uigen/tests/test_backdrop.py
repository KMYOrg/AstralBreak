"""1b 후속 H3 — 회색 바탕 위 확인(gen/backdrop): 그리는 순서 · 합성 · 합성기 검산 · '어둡고 불투명' · 알파 절벽 · make_concept --transparent."""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
from PIL import Image

from gen import backdrop

NAVY = (20, 26, 60)


def _spec(asset_alpha_note: str = "") -> dict:
    return {"schema_version": 1, "canvas": [200, 100], "root": "Root", "assets": [], "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Top", "type": "Image", "parent": "Root", "slot": {"kind": "canvas", "z": 2}, "style": {"brush": {"draw_as": "image", "asset": "top"}}},
        {"id": "Swirl", "type": "Image", "parent": "Root", "slot": {"kind": "canvas", "z": 1}, "style": {"brush": {"draw_as": "image", "asset": "swirl"}}},
        {"id": "Hidden", "type": "Image", "parent": "Root", "slot": {"kind": "canvas", "z": 3}, "style": {"brush": {"draw_as": "image", "asset": "top"}}},
        {"id": "Label", "type": "TextBlock", "parent": "Root", "slot": {"kind": "canvas", "z": 4}},
    ]}


def _boxes() -> list[dict]:
    return [{"id": "Root", "x": 0, "y": 0, "w": 200, "h": 100, "visible": True},
            {"id": "Top", "x": 20, "y": 20, "w": 40, "h": 40, "visible": True},
            {"id": "Swirl", "x": 10, "y": 10, "w": 120, "h": 60, "visible": True},
            {"id": "Hidden", "x": 150, "y": 10, "w": 40, "h": 40, "visible": False},
            {"id": "Label", "x": 140, "y": 60, "w": 50, "h": 30, "visible": True}]


def _tex(rgb, a, w, h) -> np.ndarray:
    t = np.zeros((h, w, 4), float)
    t[..., :3], t[..., 3] = rgb, a * 255
    return t


def test_paint_order_follows_canvas_z_then_spec_order():
    assert [w["id"] for w in backdrop.paint_order(_spec())] == ["Root", "Swirl", "Top", "Hidden", "Label"]


def test_compose_shows_the_backdrop_through_translucent_dark_texture_and_skips_text_and_hidden():
    tex = {"swirl": _tex(NAVY, 0.3, 120, 60), "top": _tex((240, 200, 80), 1.0, 40, 40)}
    gray, cov, info = backdrop.compose(_spec(), _boxes(), tex, [200, 100])
    assert np.allclose(gray[15, 100], np.asarray(NAVY) * 0.3 + 128 * 0.7) and abs(cov[15, 100] - 0.3) < 1e-6   # 회색이 비침
    assert np.allclose(gray[30, 30], (240, 200, 80))                                                        # z 2 가 위
    assert np.allclose(gray[20, 170], 128) and info["text_skipped"] == ["Label"]                           # 숨은 위젯 · 글자 없음
    black, _, _ = backdrop.compose(_spec(), _boxes(), tex, [200, 100], (0, 0, 0))
    assert np.allclose(black[15, 100], np.asarray(NAVY) * 0.3)
    assert backdrop.text_mask(_spec(), _boxes(), [200, 100])[70, 150]


def test_nine_slice_keeps_corner_pixels():
    t = _tex((10, 10, 10), 1.0, 20, 20)
    t[:4, :4, :3] = 250
    out = backdrop._nine_slice(t, 80, 40, [0.2, 0.2, 0.2, 0.2], None)
    assert out.shape == (40, 80, 4) and out[1, 1, 0] == 250 and out[20, 40, 0] == 10


def _run(tmp: pathlib.Path, smudge: bool) -> pathlib.Path:
    """ⓐ 컨셉(어두운 반투명 소용돌이 0.3 · 띠 끝 알파가 서서히 0) — smudge 면 텍스처를 H2 처럼 불투명 · 딱 자름."""
    swirl = _tex(NAVY, 0.3, 120, 60)
    swirl[:, 80:, 3] = np.linspace(0.3, 0.0, 40)[None] * 255
    if smudge:
        swirl[..., 3] = np.where(swirl[..., 3] > 0.15 * 255, 255, 0)
    top = _tex((240, 200, 80), 1.0, 40, 40)
    spec = _spec()
    (tmp / "assets" / "final").mkdir(parents=True)
    for name, t in (("swirl", swirl), ("top", top)):
        Image.fromarray(t.round().astype(np.uint8), "RGBA").save(tmp / "assets" / "final" / f"{name}.png")
    (tmp / "spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (tmp / "geometry.json").write_text(json.dumps({"canvas": [200, 100], "geometry": {"200x100": _boxes()}}), encoding="utf-8")
    (tmp / "manifest.json").write_text(json.dumps({"assets": [{"asset_id": "swirl", "file": "assets/final/swirl.png"},
                                                              {"asset_id": "top", "file": "assets/final/top.png"}]}), encoding="utf-8")
    (tmp / "normalize.json").write_text(json.dumps({"background": {"kind": "transparent"}}), encoding="utf-8")
    textures = {"swirl": backdrop._load(tmp / "assets/final/swirl.png"), "top": backdrop._load(tmp / "assets/final/top.png")}
    black, _, _ = backdrop.compose(spec, _boxes(), textures, [200, 100], (0, 0, 0))
    Image.fromarray(black.round().astype(np.uint8)).save(tmp / "render.png")
    # 컨셉 = 깨끗한 텍스처를 같은 자리에(곧은 색 · 알파)
    truth = {"swirl": _tex(NAVY, 0.3, 120, 60), "top": top}
    truth["swirl"][:, 80:, 3] = np.linspace(0.3, 0.0, 40)[None] * 255
    _, ra, _ = backdrop.compose(spec, _boxes(), truth, [200, 100], (0, 0, 0))
    col = np.zeros((100, 200, 3))
    col[10:70, 10:130] = NAVY
    col[20:60, 20:60] = (240, 200, 80)
    Image.fromarray(col.astype(np.uint8)).save(tmp / "reference_color.png")
    Image.fromarray((ra * 255).round().astype(np.uint8), "L").save(tmp / "reference_alpha.png")
    return tmp


def test_check_finds_the_dark_opaque_smudge_and_cut_band_end_only_on_gray(tmp_path):
    good = backdrop.check(_run(tmp_path / "good", smudge=False))
    assert good["compositor"]["mean_abs"] <= 0.5 and good["truth"] == "concept_alpha"
    assert good["gray_de00"]["mean"] < 1.0 and good["alpha_cliffs"]["compose_only"] == 0
    assert (tmp_path / "good" / "assets" / "compare" / "backdrop.png").is_file()
    bad = backdrop.check(_run(tmp_path / "bad", smudge=True))
    assert bad["compositor"]["mean_abs"] <= 0.5                       # 검정 위 렌더와는 맞는다(검정에선 못 봄)
    assert bad["gray_de00"]["mean"] > 5 * max(good["gray_de00"]["mean"], 0.5)
    assert bad["dark_opaque"]["compose"]["opaque_ratio"] > 0.9 > (bad["dark_opaque"]["concept"]["opaque_ratio"] or 0)
    assert bad["alpha_cliffs"]["compose_only"] > 40                   # 띠 끝 딱 자름
    assert bad["dark_opaque_textures"]["swirl"]["opaque_ratio"] == 1.0


def _facets(xs, ys) -> np.ndarray:
    s = 0.6 * np.sin(2 * np.pi * xs / 14.0) + 0.4 * np.sin(2 * np.pi * ys / 9.0 + xs / 7.0)
    return np.dstack([30 + 15 * s, 50 + 25 * s, 120 + 30 * s])


def test_text_free_fill_matches_the_concept_alpha_level_when_codex_drew_the_board_more_opaque():
    """[실측 H3 R20261117_090812 — 투명 컨셉] 판의 띠가 더 불투명(글자 둘레 0.85 ~ 0.94 ↔ 0.98 ~ 0.99)해 글자 자리만 진한 사각 패치 → 둘레 비로 맞춘다."""
    from gen import cutout
    H, W, P = 90, 400, cutout.NOTEXT_SHIFT
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    band = _facets(xx, yy)
    a0 = np.clip(0.25 + 0.7 * xx / W, 0, 1)                        # 왼쪽으로 옅어지는 띠
    rgb, a = band.copy(), a0.copy()
    bars = np.zeros((H, W), bool)
    for k in range(5):
        bars[25:70, 120 + 30 * k:128 + 30 * k] = True
    rgb[bars], a[bars] = 250.0, 1.0
    texts = [{"id": "L", "box": [100, 15, 180, 65], "glow": 0}]
    jy, jx = np.mgrid[0:H + 2 * P, 0:W + 2 * P].astype(float)
    nt_a = np.clip((0.25 + 0.7 * (jx - P) / W) * 1.3, 0, 1)        # 판은 30 % 더 불투명
    out, oa, rec = cutout.compose(rgb, a, texts, fill_from=(_facets(jx - P, jy - P), nt_a))
    assert rec["notext"]["used"] and rec["notext"]["alpha_gain_applied"] and rec["notext"]["alpha_gain"] < 0.85
    assert np.abs(oa[bars] - a0[bars]).mean() < 0.03                # 글자 자리 알파 = 컨셉 띠 수준
    same = cutout.compose(rgb, a, texts, fill_from=(_facets(jx - P, jy - P), np.clip(0.25 + 0.7 * (jx - P) / W, 0, 1)))[2]
    assert same["notext"]["alpha_gain_applied"] is False            # 알파가 같으면 손대지 않음


def test_text_free_alignment_uses_the_stroke_ring_when_the_text_box_covers_the_badge():
    """[실측 H3 R20261117_090812] E 키 글자 상자가 배지보다 커 글자 사각형 구멍이 배지 전체 → 둘레 0 px 로 판을 못 써 inpaint 방사 무늬 → 획 둘레로 잰다."""
    from gen import cutout
    S, P = 70, cutout.NOTEXT_SHIFT
    yy, xx = np.mgrid[0:S, 0:S].astype(float)
    disc = np.hypot(xx - 34.5, yy - 34.5) < 33
    base = np.dstack([60 + 40 * (yy / S), 64 + 40 * (yy / S), 72 + 40 * (yy / S)])
    rgb, a = base.copy(), disc.astype(float)
    glyph = np.zeros((S, S), bool)
    glyph[18:52, 24:30] = glyph[18:23, 24:46] = glyph[33:37, 24:42] = glyph[47:52, 24:46] = True
    rgb[glyph] = 250.0
    texts = [{"id": "E", "box": [-4, -4, S + 8, S + 8], "glow": 0}]
    jy, jx = np.mgrid[0:S + 2 * P, 0:S + 2 * P].astype(float)
    nb = np.dstack([60 + 40 * ((jy - P) / S), 64 + 40 * ((jy - P) / S), 72 + 40 * ((jy - P) / S)])
    na = (np.hypot(jx - P - 34.5, jy - P - 34.5) < 33).astype(float)
    out, oa, rec = cutout.compose(rgb, a, texts, fill_from=(nb, na))
    assert rec["notext"]["used"] and rec["notext"]["ring_from"] == "strokes" and rec["notext"]["diff"] < 2.0
    assert np.abs(out[glyph] - base[glyph]).max(axis=1).mean() < 4.0   # 글자 자리 = 원판(방사 무늬 아님)


def test_two_overhangs_do_not_both_take_the_translucent_gap_between_them(tmp_path):
    """[실측 H3 R20261117_092636 — 투명 컨셉 회색 바탕] 위 · 아래 띠의 넘침이 두 띠 사이 반투명 소용돌이를 둘 다 가져가 두 번 쌓였다 → 먼저 차지한 쪽 몫."""
    import types

    from core import config
    from core.run import Run
    from stages import generate, normalize, refine
    run = Run("R20261117_100000_ProbeGap", tmp_path / "work", config.load_pipeline(), tmp_path / "m.jsonl")
    run.create()
    rgba = np.zeros((1080, 1920, 4), np.uint8)
    for y0 in (300, 440):
        rgba[y0:y0 + 100, 400:700] = (*NAVY, 255)
        rgba[y0:y0 + 3, 400:700] = rgba[y0 + 97:y0 + 100, 400:700] = (232, 181, 74, 255)
    rgba[400:440, 420:680] = (*NAVY, 77)                                          # 두 띠 사이 반투명(0.3) — 둘 다에 이어짐
    Image.fromarray(rgba, "RGBA").save(tmp_path / "concept.png")
    fit = normalize._fit_reference(tmp_path / "concept.png", run.path("reference.png"), [1920, 1080])
    assert fit["background"]["kind"] == "transparent"
    run.write_json("normalize.json", {"schema_version": 1, "mode": "concept", **fit})
    canvas = lambda x, y, w, h: {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [x, y], "size": [w, h]}   # noqa: E731
    spec = {"schema_version": 1, "canvas": [1920, 1080], "profile": "hud", "root": "Root", "widgets": [{"id": "Root", "type": "CanvasPanel"}],
            "assets": []}
    for name, y0 in (("Top", 300), ("Bottom", 440)):
        spec["widgets"].append({"id": name, "type": "Image", "parent": "Root", "slot": canvas(400, y0, 300, 100), "bbox_intent": [400, y0, 300, 100],
                                "style": {"brush": {"draw_as": "image", "asset": name.lower()}}})
        spec["assets"].append({"asset_id": name.lower(), "kind": "panel_bg", "provenance": "codex", "source_mode": "extract", "size": [300, 100],
                               "prompt": "a navy band", "ref_bbox": [400, y0, 300, 100]})
    run.write_json("spec.json", spec)
    generate.run(run, types.SimpleNamespace(attempt=1))
    refine.run(run, types.SimpleNamespace(attempt=1))
    logs = {a["asset_id"]: a["cut"]["overhang"] for a in run.read_json("refine.json")["passes"][0]["assets"]}
    assert logs["top"]["used"] and logs["bottom"].get("blocked_claimed_px", 0) > 0
    out = run.read_json("spec.json")
    boxes = [{"id": w["id"], "x": w["bbox_intent"][0], "y": w["bbox_intent"][1], "w": w["bbox_intent"][2], "h": w["bbox_intent"][3], "visible": True}
             for w in out["widgets"] if w.get("bbox_intent")] + [{"id": "Root", "x": 0, "y": 0, "w": 1920, "h": 1080, "visible": True}]
    tex = {a["asset_id"]: backdrop._load(run.path(a["file"])) for a in run.read_json("manifest.json")["assets"]}
    _, cov, _ = backdrop.compose(out, boxes, tex, [1920, 1080])
    assert abs(float(cov[405:435, 450:650].mean()) - 0.3) < 0.03                 # 한 번만(두 번이면 0.51)


def test_a_texture_drawn_above_clears_the_text_and_badge_of_a_region_below_but_not_its_own_children():
    """[실측 H3 R20261117_094157] 엠블럼 영역(z 2)이 T 배지(띠 영역 z 1 의 자식)를 통째로 품어 엔진 'T' 를 가렸다 → 아래 영역의 글자 · 오린 이미지 자리는 비움.
    위에 그려지는 자기 자식(엠블럼 속 아이콘)은 같은 픽셀로 덮으므로 그대로(비우면 네모 구멍)."""
    from stages import refine
    canvas = lambda x, y, w, h, z: {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [x, y], "size": [w, h], "z": z}   # noqa: E731
    img = lambda aid: {"brush": {"draw_as": "image", "asset": aid}}   # noqa: E731
    spec = {"schema_version": 1, "canvas": [400, 300], "root": "Root", "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Emblem", "type": "Image", "parent": "Root", "slot": canvas(0, 0, 300, 300, 2), "bbox_intent": [0, 0, 300, 300], "style": img("emblem")},
        {"id": "Band", "type": "Image", "parent": "Root", "slot": canvas(200, 20, 200, 60, 1), "bbox_intent": [200, 20, 200, 60], "style": img("band")},
        {"id": "BadgeT", "type": "Image", "parent": "Root", "slot": canvas(210, 25, 50, 50, 1), "bbox_intent": [210, 25, 50, 50], "style": img("badge")},
        {"id": "TText", "type": "TextBlock", "parent": "Root", "slot": canvas(222, 30, 26, 40, 1), "bbox_intent": [222, 30, 26, 40]},
        {"id": "Icon", "type": "Image", "parent": "Root", "slot": canvas(100, 100, 60, 60, 3), "bbox_intent": [100, 100, 60, 60], "style": img("icon")}],
        "assets": [{"asset_id": a, "kind": "ornament", "provenance": "codex", "source_mode": "extract", "size": [10, 10]} for a in ("emblem", "band", "badge", "icon")]}
    alpha = np.ones((300, 400))
    a, n, ids = refine._drop_covered_below(np.ones((300, 300)), spec, "emblem", [0, 0, 300, 300], [0, 0, 300, 300], alpha)
    assert set(ids) == {"BadgeT", "TText"} and a[50, 235] == 0 and a[130, 130] == 1      # 아래 배지 · 글자 자리만, 위 아이콘은 그대로
    assert n == int((a == 0).sum()) and a[150, 50] == 1                                 # 띠는 일부만 담겨(포함 관계 아님) 기존 겹침 규칙 몫


def test_frame_drop_does_not_erase_a_glyph_of_another_region_crossing_this_region_edge():
    """[실측 H3 R20261117_095249] 엠블럼 영역 상자 오른쪽 끝이 '어빌리티' 첫 글자를 지나가 '어' 가 엠블럼 테두리선으로 빠져 크기 판이 건너뜀."""
    from stages import style
    img = np.zeros((100, 400, 3))
    img[:, :] = (20, 30, 60)
    img[30:60, 190:206] = (60, 220, 240)                        # B 영역 글자 획 — A 영역 오른쪽 끝(x 200)을 지나감
    spec = {"root": "Root", "widgets": [{"id": "Root", "type": "CanvasPanel"},
                                         {"id": "A", "type": "Image", "parent": "Root", "bbox_intent": [0, 0, 200, 100]},
                                         {"id": "B", "type": "Overlay", "parent": "Root", "bbox_intent": [150, 0, 250, 100]},
                                         {"id": "T", "type": "TextBlock", "parent": "B", "bbox_intent": [185, 20, 60, 50]}]}
    assert not style._frame_drop(img, spec)[40:50, 190:200].any()
    spec["widgets"][3]["parent"] = "A"                            # 자기 영역 글자면 예전처럼 테두리선으로 뺀다
    assert style._frame_drop(img, spec)[40:50, 190:200].any()


def test_overlapping_cut_widgets_split_the_overlap_the_same_way_from_both_sides():
    """[실측 H3 R20261117_095249] 점프 띠 끝 ↔ 엠블럼 겹친 자리 소용돌이(0.6)를 둘 다 그림 → (1b 후속 I) run 에서 한 번 만든 소유 지도를 두 위젯이
    같이 쓴다: 반투명은 가까운 물체 주인, 겹친 자리는 정확히 한쪽만."""
    from stages import refine
    full = np.zeros((200, 240))
    full[10:30, 40:140] = 0.6                                   # 반투명 띠 — A · B 상자에 걸침
    full[32:38, 50:230] = 0.95                                  # 불투명 막대 — 대부분 B 쪽
    spec = {"root": "Root", "widgets": [{"id": "Root", "type": "CanvasPanel"},
                                         {"id": "A", "type": "Image", "parent": "Root", "bbox_intent": [0, 0, 100, 40], "style": {"brush": {"asset": "a"}}},
                                         {"id": "B", "type": "Image", "parent": "Root", "bbox_intent": [60, 0, 140, 200], "style": {"brush": {"asset": "b"}}}],
            "assets": [{"asset_id": "a", "source_mode": "extract"}, {"asset_id": "b", "source_mode": "extract"}]}
    own = refine.cut_ownership(spec, full)
    drop_a, held_a = refine._owner_masks(own, spec, "a", [0, 0, 240, 200])
    drop_b, held_b = refine._owner_masks(own, spec, "b", [0, 0, 240, 200])
    O = np.zeros_like(full, bool)
    O[0:40, 60:100] = True
    vis = O & (full > 0)
    assert vis.any() and (held_a[vis] ^ held_b[vis]).all()      # 겹친 자리는 정확히 한쪽만
    assert np.array_equal(drop_a[vis], held_b[vis]) and np.array_equal(drop_b[vis], held_a[vis])


def test_render_text_mask_is_the_difference_from_the_text_free_composite(tmp_path):
    """[실측 H3 R20261117_112216] 렌더 획 측정이 두 톤 띠 밝은 윗면까지 글자로 잡아 '돌진 공격' · '점프' 크기 판이 건너뜀 → 렌더 ↔ 글자 없는 합성 차 = 엔진 글자."""
    from stages import style
    rd = _run(tmp_path / "r", smudge=False)
    ren = np.asarray(Image.open(rd / "render.png").convert("RGB")).astype(float)
    ren[66:84, 146:184] = (250, 250, 210)                         # Label 상자 [140, 60, 50, 30] 안 엔진 글자(합성엔 없음)
    texts = [{"bbox_intent": [140, 60, 50, 30]}]
    m = style._render_text_mask(rd / "render.png", ren, json.loads((rd / "spec.json").read_text(encoding="utf-8")), texts)
    assert m is not None and m[75, 160] and not m[40, 80] and not m[30, 30]   # 글자 자리만 — 띠 · 아이콘은 아님
    bad = ren.copy()
    bad[:, :, 2] = 255                                            # 합성이 렌더를 못 따라가면 쓰지 않는다
    assert style._render_text_mask(rd / "render.png", bad, json.loads((rd / "spec.json").read_text(encoding="utf-8")), texts) is None


def test_make_concept_transparent_rules_and_text_free_keeps_alpha(tmp_path, monkeypatch):
    import make_concept
    fake = [sys.executable, "-X", "utf8", "-B", str(pathlib.Path(__file__).with_name("fake_codex.py"))]
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_CODEX_LOG", str(log))
    out = tmp_path / "fixture"
    out.mkdir()
    (out / "concept_prompt.md").write_text("a HUD concept", encoding="utf-8")
    assert make_concept.main(["--out-dir", str(out), "--work-root", str(tmp_path / "w0"), "--flat", "--transparent"], cli=fake) == make_concept.EXIT_FAIL
    assert not log.exists()                                                                # 둘 다면 codex 를 부르지 않음
    code = make_concept.main(["--out-dir", str(out), "--work-root", str(tmp_path / "w1"), "--with-text", "--transparent"], cli=fake)
    call = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert "genuinely transparent background" in call["argv"][1] and "#000000" not in call["argv"][1]
    meta = json.loads((out / "concept.json").read_text(encoding="utf-8"))
    assert meta["transparent_background"] is True
    # 가짜 codex 그림에 투명 픽셀이 없으면 실패(no_alpha)로 알리고 그림은 남긴다
    assert code == (make_concept.EXIT_OK if (meta.get("transparent_ratio") or 0) > 0 and meta.get("has_alpha_channel") else make_concept.EXIT_FAIL)
    assert (out / "concept.png").is_file()
    edited = tmp_path / "edited"
    edited.mkdir()
    (edited / "concept_prompt.md").write_text("UI only", encoding="utf-8")
    make_concept.main(["--out-dir", str(edited), "--work-root", str(tmp_path / "w2"), "--edit", str(out / "concept.png"), "--transparent"], cli=fake)
    call = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert "Remove the game scene completely" in call["argv"][1] and "genuinely transparent background" in call["argv"][1]
    # 글자 없는 판 — 원본이 알파 PNG 면 알파를 지키라고 덧붙인다
    free = tmp_path / "free"
    free.mkdir()
    Image.fromarray(np.zeros((8, 8, 4), np.uint8), "RGBA").save(free / "concept.png")
    make_concept.main(["--out-dir", str(free), "--work-root", str(tmp_path / "w3"), "--text-free"], cli=fake)
    call = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert "Remove every piece of text" in call["argv"][1] and "transparent background (PNG alpha)" in call["argv"][1]
    free2 = tmp_path / "free2"
    free2.mkdir()
    Image.fromarray(np.zeros((8, 8, 3), np.uint8), "RGB").save(free2 / "concept.png")
    make_concept.main(["--out-dir", str(free2), "--work-root", str(tmp_path / "w4"), "--text-free"], cli=fake)
    call = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert "PNG alpha" not in call["argv"][1]
