"""1b 후속 H — 컨셉 픽셀 직접 오리기(gen/cutout): 배경 판정 · 단색 배경 언믹싱 · GrabCut · 넘침 · 가려진 자리 메우기 · normalize 층 ·
generate 오리기만(codex 없음) · refine 오리기 경로 + 넘침 장식 Image(다시 다듬기 때 걷고 새로) · analyze codex 상한 · 장식선 끊김 지표 · make_concept 옵션."""
from __future__ import annotations

import json
import pathlib
import sys
import types

import numpy as np
import pytest
from conftest import fixture_brief, fixture_spec
from PIL import Image, ImageDraw

from core import color, config
from core import spec as spec_mod
from core.run import Run
from gen import cutout, fidelity
from stages import analyze, generate, normalize, refine

CFG = config.load_pipeline()
GOLD, NAVY, BLUE = (232, 181, 74), (20, 26, 52), (60, 140, 230)


def _L(rgb) -> float:
    return float(color.srgb_to_lab(np.asarray(rgb, float).reshape(1, 3))[0, 0])


# ---- 배경 판정 · 언믹싱 -----------------------------------------------------------------------------------------------

def test_classify_picks_transparent_flat_or_scene_and_honours_the_request():
    flat = np.zeros((200, 300, 3), np.uint8)
    flat[60:140, 80:220] = GOLD
    assert cutout.classify(flat)["kind"] == "flat" and cutout.classify(flat)["key_color"] == "#000000"
    scene = np.random.default_rng(0).integers(0, 255, (200, 300, 3)).astype(np.uint8)
    assert cutout.classify(scene)["kind"] == "scene"
    rgba = np.dstack([flat, np.where(flat[..., 0] > 0, 255, 0).astype(np.uint8)])
    rec = cutout.classify(rgba)
    assert rec["kind"] == "transparent" and rec["alpha_ratio"] > 0.5
    forced = cutout.classify(scene, "flat")
    assert forced["kind"] == "flat" and forced["auto"] == "scene" and forced["source"] == "inputs"
    with pytest.raises(cutout.CutoutError, match="no alpha"):
        cutout.classify(flat, "transparent")


def test_flat_unmix_keeps_panels_opaque_and_unmixes_glow_on_black():
    im = Image.new("RGB", (200, 120), (0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([40, 30, 159, 89], fill=NAVY)                     # 어두운 안쪽(키와 차 52 < SOLID) — 금테 윤곽 안이라 불투명
    for i in range(3):
        d.rectangle([40 + i, 30 + i, 159 - i, 89 - i], outline=GOLD)
    arr = np.asarray(im).copy()
    for x in range(170, 200):                                     # 패널과 떨어진 파란 빛 — 밖으로 옅어짐(검정과 섞인 반투명)
        k = 1 - (x - 170) / 30
        arr[50:70, x] = (np.array(BLUE) * k).astype(np.uint8)
    arr[55:65, 95:105] = 0                                        # 윤곽 안이지만 키 그대로인 구멍 — 배경이 비치는 자리
    col, a, rec = cutout.flat_unmix(arr, [0, 0, 0])
    assert a[60, 60] == 1.0 and a[31, 100] == 1.0 and a[60, 100] == 0.0 and a[5, 5] == 0.0
    g = a[60, 194]                                                # 빛 바깥(키와 차 < SOLID) — 반투명, 색은 밝기를 되살린 파랑
    assert 0.05 < g < 0.4 and col[60, 194, 2] > 200 and col[60, 194, 2] > 1.4 * col[60, 194, 1]
    assert a[60, 171] == 1.0                                      # 빛 심(SOLID 이상)은 윤곽 안 — 불투명(검정 렌더에선 같다 · 한계로 기록)
    assert np.allclose(col[60, 60], NAVY, atol=1) and rec["translucent_ratio"] > 0


def test_guided_filter_softens_only_the_edge_and_grabcut_finds_a_banner_on_a_scene():
    rng = np.random.default_rng(1)
    scene = np.zeros((160, 320, 3), np.uint8)
    for y in range(160):                                          # 나뭇결 같은 갈색 줄무늬
        scene[y] = (110 + 30 * np.sin(y / 3.0), 70 + 15 * np.sin(y / 3.0), 40)
    scene = np.clip(scene.astype(int) + rng.integers(-8, 8, scene.shape), 0, 255).astype(np.uint8)
    im = Image.fromarray(scene)
    d = ImageDraw.Draw(im)
    d.polygon([(60, 50), (230, 50), (260, 80), (230, 110), (60, 110)], fill=(40, 90, 200))   # 오른쪽이 뾰족한 파란 띠
    d.line([(60, 50), (230, 50), (260, 80), (230, 110), (60, 110), (60, 50)], fill=(150, 220, 255), width=2)
    rgb = np.asarray(im)
    box = [50, 40, 270, 120]                                      # 위젯 상자(조각 좌표) — 둘레 50 px 가 장면
    a, rec = cutout.grabcut_alpha(rgb, box)
    assert a[80, 120] > 0.9 and a[80, 255] > 0.5 and a[45, 255] < 0.1 and a[10, 10] == 0.0 and rec["in_box_ratio"] > 0.5
    a2, _ = cutout.grabcut_alpha(rgb, box)
    assert np.array_equal(a, a2)                                  # RNG 씨앗 고정 — 같은 입력 → 같은 알파
    soft = cutout.guided_filter(np.full((20, 20), 0.5), np.pad(np.ones((10, 20)), ((0, 10), (0, 0))))
    assert soft[2, 10] > 0.95 and soft[17, 10] < 0.05            # 안내가 평평하면 가장자리 밖은 그대로
    with pytest.raises(cutout.CutoutError):
        cutout.grabcut_alpha(np.zeros((40, 40, 3), np.uint8), [0, 0, 40, 40])   # 상자 밖에 배경 시료가 없다


def test_overhang_keeps_connected_spill_outside_other_widgets():
    a = np.zeros((100, 300))
    a[30:70, 50:200] = 1.0                                        # 위젯 상자 50 ~ 200
    a[45:55, 200:280] = 1.0                                       # 오른쪽으로 이어진 띠 끝 장식
    a[5:15, 5:30] = 1.0                                           # 떨어진 덩어리(다른 요소) — 안 가져옴
    blocked = np.zeros((100, 300), bool)
    blocked[:, 260:] = True                                       # 이웃 글자 위젯 자리
    keep, rec = cutout.overhang(a, [50, 30, 200, 70], blocked)
    assert rec["used"] and keep[50, 230] and not keep[50, 265] and not keep[10, 10] and rec["box"] == [50, 30, 260, 70]
    keep2, rec2 = cutout.overhang(a, [50, 30, 200, 70], np.ones((100, 300), bool))
    assert not rec2["used"] and not keep2.any()


def test_compose_fills_text_with_rgba_and_sets_the_interior_alpha():
    rgb = np.zeros((120, 300, 3))
    rgb[:] = NAVY
    for i in range(3):
        rgb[i, :], rgb[-1 - i, :], rgb[:, i], rgb[:, -1 - i] = GOLD, GOLD, GOLD, GOLD
    a = np.ones((120, 300))
    for k in range(4):                                            # 글자 막대(ⓑ 에서는 불투명 전경)
        rgb[40:80, 110 + 20 * k:118 + 20 * k] = (250, 250, 250)
    out, oa, rec = cutout.compose(rgb, a, texts=[{"id": "T", "box": [100, 30, 100, 60], "glow": 0}], interior_alpha=0.9)
    assert abs(_L(out[60, 113]) - _L(NAVY)) < 3 and abs(oa[60, 60] - 0.9) < 1e-6 and oa[1, 150] == 1.0
    assert rec["texts"][0]["hole_px"] > 0 and rec["interior_ratio"] > 0.5
    img = cutout.to_image(out, oa, (600, 240))
    assert img.size == (600, 240) and np.asarray(img)[120, 120, 3] == 229


def test_compose_clears_text_on_a_two_tone_band_and_keeps_a_badge_covered_by_its_number():
    """[실측 H 오프라인 — G2 조작 안내] 위 밝은 청록 · 아래 짙은 파랑 띠 위 흰 글자: 띠 전체가 장식선 판정이라 구멍이 안 뚫렸고(frame_keep),
    text_ink 는 획 아래 절반만 잡았다(탑햇) · 안쪽 알파를 메우기 전 색으로 갈라 유령 글자가 남았다. [파티 HUD] 숫자가 54 px 배지를 거의 다 덮었다."""
    rgb = np.zeros((90, 400, 3))
    rgb[:45] = (90, 210, 235)
    rgb[45:] = (30, 60, 160)
    for k in range(5):                                            # 흰 글자 막대(두 톤에 걸침)
        rgb[25:70, 120 + 30 * k:128 + 30 * k] = (250, 250, 250)
    a = np.ones((90, 400))
    out, oa, rec = cutout.compose(rgb, a, texts=[{"id": "L", "box": [100, 15, 180, 65], "glow": 0}], interior_alpha=0.9, lock_lines=True,
                                  hole_alpha="alpha")
    assert abs(_L(out[35, 124]) - _L((90, 210, 235))) < 4 and abs(_L(out[60, 124]) - _L((30, 60, 160))) < 4     # 위 · 아래 모두 띠 색
    assert abs(oa[35, 124] - oa[35, 104]) < 1e-6 and abs(oa[60, 124] - oa[60, 104]) < 1e-6                     # 알파에 글자 모양이 없다
    badge = np.zeros((60, 54, 3))
    badge[:] = (150, 150, 155)
    badge[:3], badge[-3:], badge[:, :3], badge[:, -3:] = 230, 230, 230, 230
    badge[10:50, 12:22] = 250                                     # 숫자 '1' · '0' 이 배지 거의 전부
    badge[10:50, 28:44] = 250
    badge[18:42, 32:40] = 150
    out, oa, rec = cutout.compose(badge, np.ones((60, 54)), texts=[{"id": "N", "box": [-11, -8, 76, 77], "glow": 13}], hole_alpha="alpha",
                                  whole_text_boxes=True)
    assert rec.get("whole_text_boxes_skipped") and rec["fill"].startswith("inpaint") and oa.min() > 0.9   # 배지는 남는다(빈 그림 · 회색 사각형 아님)
    assert np.allclose(out[1, 27], 230, atol=2)                                                             # 베벨 테두리 그대로


def _facets(xs, ys) -> np.ndarray:
    """띠의 사선 · 면 무늬 흉내(어두운 남색 — 장식선 판정 밖). 좌표 배열 → 색 HxWx3."""
    s = 0.6 * np.sin(2 * np.pi * xs / 14.0) + 0.4 * np.sin(2 * np.pi * ys / 9.0 + xs / 7.0)
    return np.dstack([30 + 15 * s, 50 + 25 * s, 120 + 30 * s])


def test_compose_fills_text_holes_from_the_text_free_concept_and_falls_back_when_it_does_not_match():
    """[실측 H — UI 만 컨셉 run R173820] 글자 사각형 자리를 줄 보간으로 메워 띠의 사선 무늬가 그 자리만 평평한 패치였다 → 글자 없는 판 픽셀로."""
    H, W, P = 90, 400, cutout.NOTEXT_SHIFT
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    band = _facets(xx, yy)
    rgb, a = band.copy(), np.full((H, W), 0.7)                    # ⓑ 반투명 띠(알파 0.7) 위 불투명 흰 글자
    bars = np.zeros((H, W), bool)
    for k in range(5):
        bars[25:70, 120 + 30 * k:128 + 30 * k] = True
    rgb[bars], a[bars] = 250.0, 1.0
    texts = [{"id": "L", "box": [100, 15, 180, 65], "glow": 0}]
    dx, dy = 2, -1                                                # 판이 (2, -1) 어긋나 있다 — 요소마다 다시 맞춘다
    jy, jx = np.mgrid[0:H + 2 * P, 0:W + 2 * P].astype(float)
    nt = (_facets(jx - P - dx, jy - P - dy), np.full((H + 2 * P, W + 2 * P), 0.7))
    out, oa, rec = cutout.compose(rgb, a, texts, fill_from=nt)
    assert rec["notext"]["used"] and rec["notext"]["shift"] == [dx, dy] and rec["notext"]["diff"] < 1.0
    err = np.abs(out[bars] - band[bars]).mean()
    assert err < 2.0 and np.abs(oa[bars] - 0.7).max() < 0.02      # 글자 자리 = 띠 무늬 · 띠 알파(글자 모양이 없다)
    out0, _, rec0 = cutout.compose(rgb, a, texts)
    assert "notext" not in rec0 and np.abs(out0[bars] - band[bars]).mean() > 3 * err   # 줄 보간은 무늬를 못 되살린다
    noise = np.random.default_rng(3).uniform(0, 255, (H + 2 * P, W + 2 * P, 3))
    out2, oa2, rec2 = cutout.compose(rgb, a, texts, fill_from=(noise, nt[1]))
    assert not rec2["notext"]["used"] and "ring difference" in rec2["notext"]["reason"]
    assert np.array_equal(out2, out0)                             # 어긋난 판은 안 쓰고 예전 메우기 그대로
    _, _, rec3 = cutout.compose(rgb, a, texts, fill_from=nt, fill_skip=[[0, 0, W, H]])
    assert not rec3["notext"]["used"] and rec3["notext"]["glyph_px"] == 0   # 게이지 막대 자리는 판을 안 쓴다
    with pytest.raises(cutout.CutoutError, match="grown by"):
        cutout.compose(rgb, a, texts, fill_from=(band, a))


def test_text_holes_skip_corner_ornaments_joined_to_the_frame_when_the_text_box_spans_the_panel(tmp_path):
    """[실측 H2 끝 run — 단색 전투 HUD R184545] analyze 가 체인 패널 글자 상자를 패널 폭 전체로 잡자 금색 모서리 장식이 글자 획으로 잡혀(ink 13 ~ 306)
    줄 보간이 장식을 가로로 번지게 했고 OCR 이 그 줄을 글자로 봐 baked_text 가 4 번 실패했다 → 테두리 장식선에 닿고 글자 상자 가운데 절반 밖인 덩어리는 뺀다.
    (그 run 의 컨셉 · 체인 패널 텍스처 상자 · 글자 상자 그대로)"""
    from gen import concept_pixels as cp
    concept = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "m4_combat_hud_flat" / "concept.png"
    normalize._fit_reference(concept, tmp_path / "reference.png", [1920, 1080])
    x, y, w, h = 1550, 141, 318, 162
    col = np.asarray(Image.open(tmp_path / "reference_color.png"), float)[y:y + h, x:x + w]
    a = np.asarray(Image.open(tmp_path / "reference_alpha.png"), float)[y:y + h, x:x + w] / 255.0
    shape = fidelity.fill_shape(a > 0.5)[0]
    edge = max(2.0, cutout.EDGE_FRAC * min(w, h))
    fl = cutout.frame_keep_near_edge(cutout.frame_keep(col, shape, edge), fidelity.fill_shape(a > cutout.SOURCE_ALPHA)[0] | shape)
    texts = [{"id": "ChainTitleText", "box": [0, 10, 318, 43], "glow": 0}]
    off, r0 = cp.text_holes(col, texts, fl, ring=cp.edge_ring(shape, edge))
    on, r1 = cp.text_holes(col, texts, fl, ring=cp.edge_ring(shape, edge), drop_frame_touch=True)
    assert r0[0]["ink_box"][0] < 30 and off[:, :60].any()                                   # 예전: 왼쪽 모서리 장식까지 구멍
    assert r1[0]["frame_pieces_dropped"] >= 2 and not on[:, :60].any() and not on[:, -60:].any()   # 모서리 장식은 구멍이 아님
    assert 100 < r1[0]["ink_box"][0] < 140 and on[:, 140:190].any()                          # '체인' 획은 그대로 구멍


def test_small_cut_icons_do_not_block_neighbours_and_do_not_overhang():
    """[실측 H 끝 run 2차 — 조작 안내] 마우스 키 아이콘(96 px)이 띠 넘침을 네모나게 끊었고, 아이콘 자신은 상자 모서리까지 불투명한 네모 조각이었다."""
    icon = {"id": "Key", "type": "Image", "parent": "Root", "bbox_intent": [500, 300, 96, 96], "style": {"brush": {"draw_as": "image", "asset": "key"}},
            "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [500, 300], "size": [96, 96]}}
    band = {"id": "Band", "type": "Image", "parent": "Root", "bbox_intent": [100, 300, 400, 96], "style": {"brush": {"draw_as": "image", "asset": "band"}},
            "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [100, 300], "size": [400, 96]}}
    spec = {"root": "Root", "widgets": [{"id": "Root", "type": "CanvasPanel"}, band, icon],
            "assets": [{"asset_id": "key", "source_mode": "extract"}, {"asset_id": "band", "source_mode": "extract"}]}
    assert refine._small_cut_icon(spec, icon) and not refine._small_cut_icon(spec, band)
    assert not refine._blocked_mask(spec, "band", band["bbox_intent"], [60, 260, 640, 436]).any()      # 아이콘 상자는 띠 넘침을 막지 않는다
    assert any("small icon" in w for w in refine.overhang_blockers(spec, "key", icon["bbox_intent"]))   # 아이콘은 넘치지 않는다


def _banner_emblem():
    """배너 띠(상자 [20, 60, 340, 140] — 띠는 상자보다 위아래 3 px 큼, 오른쪽 끝 뾰족) · 엠블럼(상자 [240, 20, 460, 300] — 배너 끝을 덮음,
    배너 아래 바탕은 알파 0.84 로 완만하게 이어짐, 둥근 몸통은 배너 끝과 가는 연결선(3 px)으로만 붙음). [실측 I 오프라인 — 조작 안내 R120813]"""
    H, W = 320, 480
    a = np.zeros((H, W))
    a[57:143, 20:300] = 0.99                                      # 띠 몸통(상자 밖 위아래 3 px 삐짐)
    for x in range(300, 340):                                     # 뾰족한 끝
        h = int(43 * (340 - x) / 40)
        a[100 - h:100 + h, x] = 0.99
    yy, xx = np.mgrid[0:H, 0:W]
    a[(yy - 100) ** 2 + (xx - 400) ** 2 < 50 ** 2] = 0.99        # 엠블럼 둥근 몸통(배너 끝과 안 닿음)
    a[99:102, 338:352] = 0.99                                     # 끝 ↔ 몸통 가는 연결선
    for i, y in enumerate(range(143, 160)):                       # 띠 아래 엠블럼 바탕 — 알파가 10 여 px 에 걸쳐 0.99 → 0.84
        a[y, 240:400] = max(0.84, 0.99 - 0.015 * i)
    a[160:260, 240:400] = 0.84
    widgets = [{"id": "Root", "type": "CanvasPanel"},
               {"id": "Emb", "type": "Image", "parent": "Root", "bbox_intent": [240, 20, 220, 280], "style": {"brush": {"asset": "emb"}},
                "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [240, 20], "size": [220, 280]}},
               {"id": "Band", "type": "Image", "parent": "Root", "bbox_intent": [20, 60, 320, 80], "style": {"brush": {"asset": "band"}},
                "slot": {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [20, 60], "size": [320, 80]}}]
    spec = {"root": "Root", "canvas": [W, H], "widgets": widgets,
            "assets": [{"asset_id": "emb", "source_mode": "extract"}, {"asset_id": "band", "source_mode": "extract"}]}
    return spec, a


def test_overlap_owner_is_split_by_objects_not_by_box_edges():
    """[실측 I — 조작 안내 R20261117_120813] 예전 '겹친 자리 둘레에서 어느 쪽이 많나' 판정은 배너 끝(뾰족한 끝 · 끝 장식)을 엠블럼 상자 경계부터
    엠블럼 텍스처에 넘겼다 → 물체 속(알파가 고른 자리)의 가장 넓은 길: 배너 몸통에 이어진 끝은 배너 몫, 가는 연결선 너머 엠블럼 몸통은 엠블럼 몫,
    배너 아래 완만한 알파 계단(0.99 → 0.84)이 띠와 바탕을 가르고, 상자 밖으로 삐진 띠 테두리 줄은 (넘칠 수 있는) 배너 몫."""
    spec, a = _banner_emblem()
    own = refine.cut_ownership(spec, a, ring_ok={"Band", "Emb"})
    assert own is not None and own["ids"] == ["Emb", "Band"]
    o = own["owner"]
    tip = (a[60:140, 240:340] > refine.OWN_VISIBLE)
    assert (o[60:140, 240:340][tip] == 1).all()                   # 배너 끝(엠블럼 상자 안 · 뾰족한 끝까지) — 띠 위아래 끝줄까지
    assert (o[58, 250:300] == 1).all() and (o[141, 250:300] == 1).all()   # 상자 밖 삐진 테두리 줄(엠블럼 상자 안)도 배너
    assert (o[70:130, 370:430] != 1).all() and (o[200:250, 260:380] != 1).all()   # 연결선 너머 엠블럼 몸통 · 배너 아래 바탕은 배너 몫이 아니다
    con = own["contested"] & (a > refine.OWN_VISIBLE)
    assert (o[con] >= 0).all()                                    # 보이는 겨루는 자리는 모두 주인이 있다
    # 두 에셋의 몫이 정확히 나뉜다 — 한쪽이 비운 자리는 다른 쪽이 갖는다
    sb = [0, 0, 480, 320]
    drop_b, held_b = refine._owner_masks(own, spec, "band", sb)
    drop_e, held_e = refine._owner_masks(own, spec, "emb", sb)
    assert not (held_b & held_e).any() and (held_b | held_e)[con].all()
    assert np.array_equal(drop_b & con, held_e & con) and np.array_equal(drop_e & con, held_b & con)


def test_overlap_owner_tie_goes_to_the_smaller_box_and_nested_boxes_are_left_alone():
    """[실측 I — 조작 안내 점프 띠] 띠 끝이 엠블럼 몸통과 목 없이 두껍게 붙어 두 길의 병목이 같았고, 동점을 씨앗 깊이로 가르자 엠블럼(거리 99.6)이
    띠 위쪽 반을 가져갔다 → 동점은 작은 상자. 포함 관계(띠 위 배지)는 겨루지 않는다."""
    spec, a = _banner_emblem()
    a[57:143, 300:420] = 0.99                                     # 끝과 엠블럼 몸통이 띠 두께 그대로 붙음(목 없음)
    own = refine.cut_ownership(spec, a)
    assert (own["owner"][60:140, 250:330] == 1).all()             # 배너 상자 안 붙은 자리 = 배너(작은 상자)
    spec["widgets"].append({"id": "Badge", "type": "Image", "parent": "Root", "bbox_intent": [250, 70, 140, 60], "style": {"brush": {"asset": "badge"}}})
    spec["assets"].append({"asset_id": "badge", "source_mode": "extract"})
    own2 = refine.cut_ownership(spec, a)
    assert own2["pairs"] == [["Emb", "Band"], ["Band", "Badge"]]   # 배지는 엠블럼 상자 안(포함) — 엠블럼과는 겨루지 않음


def test_semi_swirl_next_to_a_banner_tip_goes_to_the_backdrop_owner():
    """[실측 I — 조작 안내 R20261117_135820] 배너 끝 둘레 소용돌이(알파 0.16 ~ 0.45)가 '가장 가까운 자기 픽셀' 규칙으로 바로 옆 배너 끝 몸통에 가
    엠블럼이 배너 상자 끝에서 세로 직선으로 잘렸다 → 물체 속이 아닌 픽셀은 겨루지 않는 자기 반투명 픽셀이 가까운 쪽 먼저(4 px 안 테두리는 그대로 배너)."""
    spec, a = _banner_emblem()
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    swirl = (a == 0) & (xx >= 300) & (xx < 380) & (yy >= 30) & (yy < 170)      # 배너 끝 둘레 · 엠블럼 상자 안 반투명 소용돌이(엠블럼 쪽으로 이어짐)
    a[swirl] = 0.3 + 0.1 * np.sin(xx[swirl] / 5.0)
    own = refine.cut_ownership(spec, a, ring_ok={"Band", "Emb"})
    o = own["owner"]
    assert (o[62:72, 325:338] == 0).all()                         # 띠 상자 안 · 뾰족한 끝 위쪽(끝 몸통에서 15 px 넘게)의 소용돌이 = 엠블럼
    tip = (a[60:140, 240:330] > 0.9)
    assert (o[60:140, 240:330][tip] == 1).all()                   # 띠 몸통 · 끝은 그대로 배너


def test_opaque_bleed_and_transparent_colour_fill_close_the_zoom_seam():
    """[실측 I — 디자이너 확대] 겹침 없이 나눈 두 텍스처를 엔진이 따로 늘리면 경계에서 둘 다 옅어지고 투명 픽셀의 검정이 섞여 검은 절취선 →
    남의 불투명 몫 2 px 은 같이 그림(반투명은 안 함) · 투명 픽셀 색은 가장 가까운 보이는 색(알파 그대로)."""
    a = np.zeros((20, 20))
    a[:, :10] = 0.99                                              # 내 몫(왼쪽) · 남의 몫(오른쪽 불투명) · 아래 줄은 반투명
    a[:, 10:] = 0.99
    a[15:, 10:] = 0.5
    drop = np.zeros((20, 20), bool)
    drop[:, 10:] = True
    bleed = refine._opaque_bleed(drop, a)
    assert bleed[:15, 10:12].all() and not bleed[:, 13:].any() and not bleed[15:].any()
    rgba = np.zeros((4, 6, 4), np.uint8)
    rgba[:, :2] = (200, 100, 50, 255)
    out = cutout.bleed_transparent_rgb(rgba)
    assert (out[:, 2:, :3] == (200, 100, 50)).all() and (out[:, 2:, 3] == 0).all() and (out[:, :2] == rgba[:, :2]).all()
    img = cutout.to_image(np.full((4, 6, 3), 90.0), (np.arange(6)[None, :].repeat(4, 0) < 3).astype(float), (6, 4))
    px = np.asarray(img)
    assert (px[:, 3:, 3] == 0).all() and (px[:, 3:, :3] == 90).all()


def test_hole_across_the_element_is_not_cleared_as_outside():
    """[실측 I 오프라인 — 조작 안내 회피 띠] 글자 사각형이 띠를 위아래로 끝까지 가르자 '구멍 뺀 실루엣'이 두 조각이 돼 그 사이가 윤곽 밖으로
    비워졌다 → 같은 줄에서 구멍 양쪽 바로 옆이 요소 픽셀이면 요소 안. 패널 밖으로 나온 글자 자리는 그대로 비운다."""
    col = np.zeros((60, 200, 3))
    col[:, :] = (40, 80, 160)
    a = np.zeros((60, 200))
    a[10:50, 10:190] = 1.0
    hole = np.zeros((60, 200), bool)
    hole[5:55, 80:120] = True                                     # 띠를 위아래로 끝까지 가르는 구멍(띠 밖 위아래 5 px 포함)
    base = (a > 0.05) & ~hole
    br = cutout._bridged(base, hole)
    assert br[10:50, 80:120].all() and not br[5:10, 80:120].any() and not br[50:55, 80:120].any()
    col[12:48, 88:93] = (250, 250, 250)                          # 띠 높이를 거의 다 쓰는 흰 글자 획 두 개
    col[12:48, 106:111] = (250, 250, 250)
    texts = [{"id": "T", "box": [80, 5, 40, 50], "glow": 0}]
    _, out_a, rec = cutout.compose(col, a, texts=texts)
    assert out_a[30, 100] > 0.9                                    # 가운데가 비지 않는다
    assert out_a[7, 100] == 0.0                                    # 띠 밖(위)은 그대로 투명


def test_text_fit_measures_concept_glyphs_from_the_text_free_difference(tmp_path):
    """[실측 H2 R184042] 밝기로 가른 컨셉 획에 옆 아이콘 · 장식이 섞여 크기 판이 'T' 를 40 → 63 으로 키웠다 → 글자 없는 판과 다른 픽셀만 글자로,
    codex 가 다시 그린 원판 차(수십)는 오츠 문턱이 뺀다 · 크기 판 신뢰 범위 0.7 ~ 1.4(G2 '4.2' 0.742 는 통과)."""
    from stages import style
    ref = np.zeros((200, 300, 3))
    ref[40:160, 40:260] = (90, 100, 115)                          # 띠
    ref[70:130, 60:110] = (215, 220, 230)                         # 글자 옆 밝은 아이콘(글자 아님 — 판에도 있음)
    ref[75:125, 150:160], ref[75:85, 130:180] = 250, 250         # 'T'
    nt = ref.copy()
    nt[75:125, 150:160], nt[75:85, 130:180] = (90, 100, 115), (90, 100, 115)
    nt[40:160, 40:260] += 30                                      # codex 가 띠를 조금 다르게 다시 그림(차 30)
    nt[70:130, 60:110] = (215, 220, 230)
    Image.fromarray(ref.astype(np.uint8)).save(tmp_path / "reference.png")
    Image.fromarray(np.clip(nt, 0, 255).astype(np.uint8)).save(tmp_path / "reference_notext_color.png")
    Image.fromarray(np.full((200, 300), 255, np.uint8)).save(tmp_path / "reference_notext_alpha.png")
    texts = [{"id": "T", "type": "TextBlock", "bbox_intent": [55, 70, 140, 60]}]
    m = style._notext_text_mask(tmp_path / "reference.png", ref, texts)
    assert m[100, 155] and m[80, 175] and not m[100, 85] and not m[150, 200]   # 획만 — 아이콘 · 다시 그린 띠는 아님
    assert style._notext_text_mask(tmp_path / "nowhere" / "reference.png", ref, texts) is None
    lo, hi = style.TEXT_FIT_TRUST_H
    assert not lo <= 0.632 <= hi and lo <= 0.742 <= hi


def test_text_ink_keeps_wide_bold_strokes_and_single_glyph_bars_but_drops_frame_lines():
    """[실측 H2 R20261116_202833] '칠해진 픽셀이 폭의 60 %' 줄을 테두리선으로 지워 크고 굵은 '회피' 의 가로획 줄이 사라졌다(58 → 29 px) ·
    좁은 상자의 'T' 가로획도 지워졌다 → 끊김 없는 한 조각이 폭의 85 % 이상인 줄만 테두리선."""
    img = np.full((70, 120, 3), 30.0)
    img[10:16, 6:56], img[10:16, 62:114] = 240, 240               # 두 글자의 굵은 가로획(합 102 px > 60 % · 한 조각 52 px)
    img[16:60, 20:30], img[16:60, 80:90] = 240, 240               # 세로획
    ink = fidelity.text_ink(img)
    assert fidelity.ink_box(ink)[1] <= 10 and fidelity.ink_box(ink)[3] >= 49                  # 위 가로획까지 글자
    t = np.full((60, 50, 3), 30.0)
    t[10:17, 8:42], t[17:52, 21:29] = 240, 240                    # 'T'(가로획 34 px = 폭 68 %)
    assert fidelity.ink_box(fidelity.text_ink(t))[2] >= 30
    framed = img.copy()
    framed[64:67, :] = 200                                        # 상자를 가로지르는 테두리선
    assert fidelity.ink_box(fidelity.text_ink(framed))[1] + fidelity.ink_box(fidelity.text_ink(framed))[3] <= 61


def test_runtime_boxes_are_the_inside_of_a_frame_not_the_portrait_under_a_badge():
    portrait = {"id": "P", "type": "Image", "bbox_intent": [400, 20, 205, 255], "binding": {"data": "portrait", "kind": "image"}}
    assert refine.runtime_boxes({"widgets": [portrait]}, [386, 210, 72, 72]) == []                          # 큰 초상화 위 배지 — 속 아님
    assert refine.runtime_boxes({"widgets": [portrait]}, [390, 10, 225, 275]) == [[10.0, 10.0, 205.0, 255.0]]   # 초상화 테두리 — 속


# ---- normalize · generate · refine (단색 배경 — codex 없음) -----------------------------------------------------------------

PANEL = [400, 300, 300, 120]


def _flat_concept(path: pathlib.Path):
    """검정 배경 컨셉 1920×1080: 금테 패널 + 오른쪽 띠 끝 장식(위젯 상자 밖 x 700 ~ 734, 검색 여유 36 px 안) + 안쪽 글자 + 오른쪽 이웃 글자(x 725 ~)."""
    im = Image.new("RGB", (1920, 1080), (0, 0, 0))
    d = ImageDraw.Draw(im)
    x, y, w, h = PANEL
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=NAVY)
    for i in range(3):
        d.rectangle([x + i, y + i, x + w - 1 - i, y + h - 1 - i], outline=GOLD)
    d.polygon([(699, 340), (734, 360), (699, 380)], fill=GOLD)                       # 띠 끝 장식(상자 밖으로)
    for k in range(4):
        d.rectangle([480 + 22 * k, 340, 490 + 22 * k, 380], fill=(250, 240, 220))  # 안쪽 글자
    d.rectangle([745, 345, 800, 375], fill=(255, 255, 255))                        # 이웃 글자
    im.save(path)


def _flat_spec() -> dict:
    canvas = lambda x, y, w, h: {"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0], "position": [x, y], "size": [w, h]}   # noqa: E731
    return {"schema_version": 1, "canvas": [1920, 1080], "profile": "hud", "root": "Root", "widgets": [
        {"id": "Root", "type": "CanvasPanel"},
        {"id": "Panel", "type": "Border", "parent": "Root", "slot": canvas(*PANEL), "bbox_intent": list(PANEL),
         "style": {"brush": {"draw_as": "image", "asset": "panel_tex"}}},
        {"id": "Label", "type": "TextBlock", "parent": "Panel", "slot": {"kind": "border", "padding": [70, 20, 70, 20]},
         "bbox_intent": [470, 320, 160, 80], "text": {"source": "static", "value": "ABCD"}, "font": {"size": 30}},
        {"id": "Side", "type": "TextBlock", "parent": "Root", "slot": canvas(725, 340, 100, 40), "bbox_intent": [725, 340, 100, 40],
         "text": {"source": "static", "value": "X"}, "font": {"size": 24}}],
        "assets": [{"asset_id": "panel_tex", "kind": "panel_bg", "provenance": "codex", "source_mode": "extract", "size": [300, 120],
                    "prompt": "a navy panel with a thin gold border and a pointed gold tip on the right", "ref_bbox": [398, 298, 304, 124]}]}


def _flat_run(tmp_path) -> Run:
    run = Run("R20261116_150000_ProbeFlat", tmp_path / "work", CFG, tmp_path / "m.jsonl")
    run.create()
    _flat_concept(tmp_path / "concept.png")
    fit = normalize._fit_reference(tmp_path / "concept.png", run.path("reference.png"), [1920, 1080])
    run.write_json("normalize.json", {"schema_version": 1, "mode": "concept", **fit})
    run.write_json("spec.json", _flat_spec())
    return run


def test_normalize_writes_alpha_and_color_layers_for_a_flat_concept_only(tmp_path):
    run = _flat_run(tmp_path)
    bg = run.read_json("normalize.json")["background"]
    assert bg["kind"] == "flat" and bg["alpha"] == "reference_alpha.png" and bg["key_color"] == "#000000"
    a = np.asarray(Image.open(run.path("reference_alpha.png")))
    c = np.asarray(Image.open(run.path("reference_color.png")))
    assert a[360, 550] == 255 and a[50, 50] == 0 and a[360, 720] == 255 and tuple(c[360, 450]) == NAVY
    scene = tmp_path / "scene.png"
    Image.fromarray(np.random.default_rng(2).integers(0, 255, (540, 960, 3)).astype(np.uint8)).save(scene)
    fit = normalize._fit_reference(scene, tmp_path / "s" / "reference.png", [1920, 1080])
    assert fit["background"]["kind"] == "scene" and not (tmp_path / "s" / "reference_alpha.png").exists()
    with pytest.raises(ValueError, match="no alpha"):
        normalize._fit_reference(scene, tmp_path / "s2" / "reference.png", [1920, 1080], "transparent")


def test_generate_cuts_flat_and_small_elements_without_codex(tmp_path):
    run = _flat_run(tmp_path)
    asset = _flat_spec()["assets"][0]
    assert generate.cut_only_reason(run, asset).startswith("background flat")
    detail = generate.run(run, types.SimpleNamespace(attempt=1))     # 가짜 codex 도 없음 — codex 를 부르면 conftest 가 막는다
    rec = json.loads(run.path("gen.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert rec["backend"] == "concept_cut" and rec["extract"]["cut"] and "concept_cut" in detail and not run.path("codex_calls.jsonl").exists()
    run.write_json("normalize.json", {"background": {"kind": "scene"}})
    assert generate.cut_only_reason(run, asset) is None
    assert generate.cut_only_reason(run, {**asset, "ref_bbox": [0, 0, 200, 50]}).startswith("small element")
    off = Run("R20261116_150001_ProbeFlat", tmp_path / "work", {**CFG, "extract": {**CFG["extract"], "cutout": False}}, tmp_path / "m.jsonl")
    off.create()
    assert generate.cut_only_reason(off, {**asset, "ref_bbox": [0, 0, 20, 20]}) is None


def test_refine_cuts_concept_pixels_draws_the_overhang_and_rebuilds_it_on_a_redo(tmp_path):
    run = _flat_run(tmp_path)
    generate.run(run, types.SimpleNamespace(attempt=1))
    detail = refine.run(run, types.SimpleNamespace(attempt=1))
    log = run.read_json("refine.json")["passes"][0]["assets"][0]
    cut = log["cut"]
    assert cut["alpha_from"] == "reference_alpha" and cut["overhang"]["used"] and "overhang decorations: ['PanelOverhang']" in detail
    assert log["crop_back"]["texture_box"] == [400, 300, 321, 120]                 # 이웃 글자 자리(x 725 ~)의 BLOCK_PAD 4 px 앞에서 멈춤
    spec = run.read_json("spec.json")
    by = {w["id"]: w for w in spec["widgets"]}
    deco = by["PanelOverhang"]
    assert deco["type"] == "Image" and deco["parent"] == "Root" and deco["bbox_intent"] == [400.0, 300.0, 321.0, 120.0]
    assert deco["slot"]["position"] == [400.0, 300.0] and deco["slot"]["size"] == [321.0, 120.0]
    assert by["Panel"]["style"]["brush"] == {"draw_as": "none", "asset": "panel_tex"}
    assert [w["id"] for w in spec["widgets"]].index("PanelOverhang") < [w["id"] for w in spec["widgets"]].index("Panel")   # 주인 영역 아래
    assert ["Panel", "PanelOverhang"] in spec["allow_overlap"] and spec["assets"][0]["size"] == [321, 120]
    assert spec_mod.validate_semantics(spec) == []
    tex = np.asarray(Image.open(run.path("assets", "final", "panel_tex.png"))).astype(float)
    assert tex.shape[:2] == (120, 321) and tex[60, 312, 3] > 200 and tex[5, 312, 3] == 0      # 띠 끝 장식 · 그 위 빈 자리
    assert tex[60, 100, 3] == 255 and abs(_L(tex[60, 85, :3]) - _L(NAVY)) < 4                # ⓑ 는 안쪽 알파 없음(컨셉 투명도 그대로) · 글자 자리는 패널 색
    assert np.allclose(tex[1, 150, :3], GOLD, atol=2) and tex[1, 150, 3] == 255             # 금테는 컨셉 색 그대로
    m = {a["asset_id"]: a for a in run.read_json("manifest.json")["assets"]}["panel_tex"]
    assert m["backend"] == "concept_cut" and m["size"] == [321, 120] and m["ocr_text"] == ""
    # 다시 다듬기(외형 라운드의 replace 등) — 지난 장식을 걷고 같은 것을 새로(에셋 크기도 원래 기준에서)
    refine.run(run, types.SimpleNamespace(attempt=2, only_assets=["panel_tex"]))
    again = run.read_json("spec.json")
    assert again == spec and run.read_json("refine.json")["passes"][1]["overhang_dropped"][0]["removed"] == ["PanelOverhang"]


def _flat_notext(concept: pathlib.Path, path: pathlib.Path, dx: int, dy: int):
    """같은 단색 컨셉에서 글자만 뺀 판(codex --text-free 흉내)을 (dx, dy) 옮겨 그린다 — 검정 배경이라 굴려도 된다."""
    im = Image.new("RGB", (1920, 1080), (0, 0, 0))
    d = ImageDraw.Draw(im)
    x, y, w, h = PANEL
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=NAVY)
    for i in range(3):
        d.rectangle([x + i, y + i, x + w - 1 - i, y + h - 1 - i], outline=GOLD)
    d.polygon([(699, 340), (734, 360), (699, 380)], fill=GOLD)
    Image.fromarray(np.roll(np.asarray(im), (dy, dx), axis=(0, 1))).save(path)


def test_normalize_aligns_the_text_free_concept_and_refine_fills_text_from_it(tmp_path):
    run = _flat_run(tmp_path)
    _flat_notext(tmp_path / "concept.png", tmp_path / "notext.png", 3, -2)
    fit = normalize._fit_reference(tmp_path / "concept.png", run.path("reference.png"), [1920, 1080], notext=tmp_path / "notext.png")
    nt = fit["background"]["notext"]
    assert nt["used"] and np.allclose(np.abs(nt["shift_px"]), [3, 2], atol=0.3)
    na = np.asarray(Image.open(run.path("reference_notext_alpha.png")))
    nc = np.asarray(Image.open(run.path("reference_notext_color.png"))).astype(float)
    assert na[296, 450] < 20 and na[302, 450] > 235 and np.allclose(nc[301, 450], GOLD, atol=12)   # 컨셉 자리로 되돌려짐(위 테두리 y 300)
    assert np.allclose(nc[360, 485], NAVY, atol=4)                                                   # 글자 자리 = 패널 색(글자 없음)
    run.write_json("normalize.json", {"schema_version": 1, "mode": "concept", **fit})
    generate.run(run, types.SimpleNamespace(attempt=1))
    refine.run(run, types.SimpleNamespace(attempt=1))
    log0 = run.read_json("refine.json")["passes"][0]["assets"][0]
    # 1b 후속 J — 판이 있으면 글자마다 '판과 다른 글자 획'만 판 픽셀로(refine._plate_item_fill — 사각 구멍 compose 는 못 맞춘 글자만)
    gf = log0["cut"]["glyph_fill"][0]
    assert gf["used"] and gf["shift"] == [0, 0] and gf["diff"] < 3 and not (log0["compose"].get("notext") or {}).get("used")
    far = tmp_path / "far.png"
    _flat_notext(tmp_path / "concept.png", far, 40, 0)
    fit2 = normalize._fit_reference(tmp_path / "concept.png", tmp_path / "f" / "reference.png", [1920, 1080], notext=far)
    assert not fit2["background"]["notext"]["used"] and not (tmp_path / "f" / "reference_notext_color.png").exists()


def test_refine_treats_a_mark_also_in_the_text_free_concept_as_decoration(tmp_path, monkeypatch):
    """[실측 H2 오프라인 — '링크 어택' 띠] 컨셉에 원래 있던 옅은 사선을 OCR 이 글자로 잡아 판 없이 다시 하자 줄 보간 패치로 돌아갔다 →
    판 조각에도 같은 자국이 있으면 그림 장식(다시 하기 없음 · ocr_text 비움)."""
    from core import ocr
    run = _flat_run(tmp_path)
    _flat_notext(tmp_path / "concept.png", tmp_path / "notext.png", 0, 0)
    fit = normalize._fit_reference(tmp_path / "concept.png", run.path("reference.png"), [1920, 1080], notext=tmp_path / "notext.png")
    run.write_json("normalize.json", {"schema_version": 1, "mode": "concept", **fit})
    calls = []

    def fake_detect(image, **kw):
        calls.append(image)
        return {"engine": "fake", "count": 1, "max_score": 0.8, "boxes": [{"box": [80, 30, 60, 50], "score": 0.8}], "min_score": 0.7, "min_area_px": 60}
    monkeypatch.setattr(ocr, "detect", fake_detect)
    generate.run(run, types.SimpleNamespace(attempt=1))
    refine.run(run, types.SimpleNamespace(attempt=1))
    log = run.read_json("refine.json")["passes"][0]["assets"][0]
    # 텍스처 · 판 조각 한 번씩 — 굽기마다(글자 지우기 마감: 지울 글자가 있으면 방법마다 lama · harmonic · off 셋을 굽고 refine 끝에 고른다)
    # 글자 지우기 다음 V7 — 컨셉 OCR 한 번(refine_concept_ocr.json) · V6 — 판에도 있는 자국은 잔여물이 아니라 반복 보강 없음
    erasing = bool((log["cut"].get("text_erase") or {}).get("texts"))
    builds = 1 + len(set(refine.erase_methods(run.cfg)) - {"lama"}) + 1 if erasing else 1     # lama 첫 판 + 나머지 후보 + off
    assert "text_marks_first" not in log["cut"] and log["cut"]["glyph_fill"][0]["used"] and len(calls) == 2 * builds + (1 if erasing else 0)
    assert not (((log["cut"].get("text_erase") or {}).get("gate") or {}).get("retries"))
    assert log["ocr_decor"]["boxes"][0]["in_text_free_concept"] and log["ocr_decor"]["boxes"][0]["box"] == [480.0, 330.0, 60.0, 50.0]
    assert {a["asset_id"]: a for a in run.read_json("manifest.json")["assets"]}["panel_tex"]["ocr_text"] == ""


def test_normalize_run_resolves_concept_notext_next_to_the_inputs(tmp_path):
    import yaml
    from stages import StageError
    data = yaml.safe_load((pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "m4_combat_hud_concept" / "inputs.yaml").read_text(encoding="utf-8"))
    (tmp_path / "in").mkdir()
    _flat_concept(tmp_path / "in" / "concept.png")
    _flat_notext(tmp_path / "in" / "concept.png", tmp_path / "in" / "concept_notext.png", 0, 0)
    data.update(concept="concept.png", concept_notext="concept_notext.png")
    inputs = tmp_path / "in" / "inputs.yaml"
    inputs.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    run = Run("R20261116_150003_CombatHUD", tmp_path / "work", CFG, tmp_path / "m.jsonl")
    run.create()
    detail = normalize.run(run, types.SimpleNamespace(inputs=str(inputs), concept=None, spec_dir=None))
    assert run.read_json("normalize.json")["background"]["notext"]["used"] and "text-free concept aligned" in detail
    col, al = refine._notext_layers(run, "flat")
    assert col.shape == (1080, 1920, 3) and al.shape == (1080, 1920) and refine._notext_layers(run, "scene")[1] is None
    data["concept_notext"] = "nope.png"
    inputs.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    with pytest.raises(StageError, match="concept_notext"):
        normalize.run(run, types.SimpleNamespace(inputs=str(inputs), concept=None, spec_dir=None))


def test_refine_skips_the_overhang_for_a_widget_that_can_collapse(tmp_path):
    run = _flat_run(tmp_path)
    spec = _flat_spec()
    next(w for w in spec["widgets"] if w["id"] == "Panel")["visibility"] = "collapsed"
    run.write_json("spec.json", spec)
    generate.run(run, types.SimpleNamespace(attempt=1))
    refine.run(run, types.SimpleNamespace(attempt=1))
    log = run.read_json("refine.json")["passes"][0]["assets"][0]
    assert not log["cut"]["overhang"]["used"] and "collapsed at runtime" in log["cut"]["overhang"]["blocked_by"][0]
    assert "PanelOverhang" not in {w["id"] for w in run.read_json("spec.json")["widgets"]}
    assert np.asarray(Image.open(run.path("assets", "final", "panel_tex.png"))).shape[:2] == (120, 300)


# ---- refine (합성 스크린샷 — codex 실루엣 시드) -----------------------------------------------------------------------------

def test_refine_cuts_a_banner_from_a_scene_with_the_codex_silhouette_as_seed(tmp_path):
    from gen import postprocess as pp
    run = Run("R20261116_150002_ProbeScene", tmp_path / "work", CFG, tmp_path / "m.jsonl")
    run.create()
    ref = np.zeros((1080, 1920, 3), np.uint8)
    for y in range(1080):
        ref[y] = (110 + 30 * np.sin(y / 3.0), 70 + 15 * np.sin(y / 3.0), 40)
    im = Image.fromarray(ref)
    d = ImageDraw.Draw(im)
    poly = [(410, 310), (660, 310), (690, 360), (660, 410), (410, 410)]
    d.polygon(poly, fill=(40, 90, 200))
    d.line(poly + [poly[0]], fill=(150, 220, 255), width=3)
    im.save(run.path("reference.png"))
    run.write_json("normalize.json", {"background": {"kind": "scene"}})
    spec = _flat_spec()
    spec["widgets"] = [w for w in spec["widgets"] if w["id"] != "Side"]
    spec["widgets"][1].update(bbox_intent=[400, 300, 300, 120], slot={"kind": "canvas", "anchors": [0, 0, 0, 0], "alignment": [0, 0],
                                                                       "position": [400, 300], "size": [300, 120]})
    run.write_json("spec.json", spec)
    region, element, _ = pp.extract_region([398, 298, 304, 124], (1920, 1080))
    raw = Image.new("RGBA", (region[2] * 2, region[3] * 2), (0, 0, 0, 0))              # codex 편집 흉내: 같은 구도 · 2배 · 모양만 대충
    ImageDraw.Draw(raw).polygon([((x - region[0]) * 2 + 6, (y - region[1]) * 2) for x, y in poly], fill=(30, 80, 180, 255))
    run.path("assets", "raw").mkdir(parents=True, exist_ok=True)
    raw.save(run.path("assets", "raw", "panel_tex.png"))
    run.append_jsonl("gen.jsonl", {"asset_id": "panel_tex", "backend": "codex", "ok": True, "source_mode": "extract",
                                   "extract": {"region": region, "element": element}})
    refine.run(run, types.SimpleNamespace(attempt=1))
    log = run.read_json("refine.json")["passes"][0]["assets"][0]
    cut = log["cut"]
    assert cut["alpha_from"].startswith("grabcut (codex") and "scene_mixed" in cut and "interior" not in log and "concept_pixels" not in log
    tex = np.asarray(Image.open(run.path("assets", "final", "panel_tex.png"))).astype(float)
    assert tex[60, 100, 3] > 200 and tex[3, 295, 3] < 30 and tex[60, 287, 3] > 128          # 띠 안 · 뾰족 끝 밖 장면 · 끝 근처
    assert np.allclose(tex[11, 150, :3], (150, 220, 255), atol=40)                         # 테두리 선은 컨셉 색(codex 색 아님)
    first = run.path("assets", "final", "panel_tex.png").read_bytes()
    refine.run(run, types.SimpleNamespace(attempt=2, only_assets=["panel_tex"]))
    assert run.path("assets", "final", "panel_tex.png").read_bytes() == first             # 결정적


# ---- analyze · 지표 · make_concept ---------------------------------------------------------------------------------------

def test_analyze_codex_cap_counts_generate_assets_only():
    spec = fixture_spec()
    for i in range(8):
        spec["assets"].append({"asset_id": f"cut_{i}", "kind": "ornament", "provenance": "codex", "source_mode": "extract", "size": [64, 64],
                               "prompt": "an ornament", "ref_bbox": [10 + i * 70, 10, 64, 64]})
    assert not any(e.startswith("ASSET_CODEX_COUNT") for e in analyze.check(spec, fixture_brief()))
    for a in spec["assets"][-7:]:
        a["source_mode"] = "generate"
    assert any(e.startswith("ASSET_CODEX_COUNT") for e in analyze.check(spec, fixture_brief()))


def test_line_breaks_counts_gaps_that_the_ring_f1_hides():
    c = np.zeros((60, 400, 3), np.uint8)
    c[10:13, 10:390] = GOLD
    r = c.copy()
    r[10:13, 100:110] = 0                                                                   # 두 군데 끊김
    r[10:13, 250:262] = 0
    br = fidelity.line_breaks(fidelity.line_mask(c), fidelity.line_mask(r))
    assert br["gaps"] == 2 and br["concept_pieces"] == 1 and br["render_pieces"] == 3
    rec, _ = fidelity.render_vs_concept(c, r)
    assert rec["line_breaks"]["gaps"] == 2 and fidelity.report_summary({"regions": {"A": rec}})["region_line_gaps"] == 2


def test_make_concept_flat_rules_and_edit_mode(tmp_path, monkeypatch):
    import make_concept
    fake = [sys.executable, "-X", "utf8", "-B", str(pathlib.Path(__file__).with_name("fake_codex.py"))]
    log = tmp_path / "log.jsonl"
    monkeypatch.setenv("FAKE_CODEX_LOG", str(log))
    out = tmp_path / "fixture"
    out.mkdir()
    (out / "concept_prompt.md").write_text("a HUD concept", encoding="utf-8")
    assert make_concept.main(["--out-dir", str(out), "--work-root", str(tmp_path / "work"), "--with-text", "--flat"], cli=fake) == make_concept.EXIT_OK
    call = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert "solid pure black background (#000000)" in call["argv"][1] and json.loads((out / "concept.json").read_text(encoding="utf-8"))["flat_background"]
    src = out / "concept.png"
    edited = tmp_path / "edited"
    edited.mkdir()
    (edited / "concept_prompt.md").write_text("make the frames silver", encoding="utf-8")
    assert make_concept.main(["--out-dir", str(edited), "--work-root", str(tmp_path / "work2"), "--edit", str(src), "--flat"], cli=fake) == make_concept.EXIT_OK
    call = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert "EDIT the attached image" in call["argv"][1] and call["argv"][-1].replace("\\", "/").endswith("fixture/concept.png")
    assert "Remove the game scene completely" in call["argv"][1] and "16:9" not in call["argv"][1]     # 합성 스크린샷 → UI 만(구도 유지)
    assert json.loads((edited / "concept.json").read_text(encoding="utf-8"))["edited_from"] == "concept.png"   # 저장소 밖이면 이름만
    calls = len(log.read_text(encoding="utf-8").splitlines())
    assert make_concept.main(["--out-dir", str(edited), "--work-root", str(tmp_path / "work3"), "--edit", str(tmp_path / "nope.png"), "--force"],
                             cli=fake) == make_concept.EXIT_FAIL
    assert len(log.read_text(encoding="utf-8").splitlines()) == calls                    # 편집할 그림이 없으면 codex 를 부르지 않는다
    # 글자 없는 판 — <out-dir>/concept.png 를 내장 프롬프트로 편집(concept_prompt.md 안 씀), concept_notext.png · .json
    free = tmp_path / "free"
    free.mkdir()
    (free / "concept.png").write_bytes(src.read_bytes())
    assert make_concept.main(["--out-dir", str(free), "--work-root", str(tmp_path / "work4"), "--text-free"], cli=fake) == make_concept.EXIT_OK
    call = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert "EDIT the attached image" in call["argv"][1] and "Remove every piece of text" in call["argv"][1]
    assert call["argv"][-1].replace("\\", "/").endswith("free/concept.png") and (free / "concept_notext.png").is_file()
    meta = json.loads((free / "concept_notext.json").read_text(encoding="utf-8"))
    assert meta["kind"] == "concept_text_free" and meta["file"] == "concept_notext.png" and (free / "concept.png").read_bytes() == src.read_bytes()
