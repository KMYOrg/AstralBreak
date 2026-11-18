"""1b 후속 L 다음 — 외부 · 단색 입력 검증 틀: E1 획에 붙은 잔상(diagnose.glyph_residue) · 오프라인 비교 묶음(regress_set)."""
from __future__ import annotations

import numpy as np

from gen import diagnose as dg

BG = np.array([40.0, 22.0, 52.0])
INK = np.array([237.0, 232.0, 216.0])


def _scene():
    """어두운 패널 위 크림색 가로획(컨셉 '4' 발) — 렌더 획은 더 짧고(글꼴 모양 차) 엔진 빛이 둘레에, 텍스처는 컨셉 획 오른쪽 끝을 남김(잔상)."""
    H, W = 60, 80
    ref = np.tile(BG, (H, W, 1))
    concept = np.zeros((H, W), bool)
    concept[24:30, 20:52] = True
    ref[concept] = INK
    comp = np.tile(BG, (H, W, 1))
    comp[26:30, 46:52] = INK * 0.9 + BG * 0.1                 # 메움이 덜 덮은 획 끝(잔상)
    render = comp.copy()
    rcore = np.zeros((H, W), bool)
    rcore[24:30, 20:40] = True
    ring = dg._dilate(rcore, 4) & ~dg._dilate(rcore, 2)        # 엔진 빛(렌더 후보 밖까지 번짐) — 텍스처엔 없음
    render[ring] = np.minimum(255, render[ring] + 60)
    render[rcore] = INK
    gm = {"T": {"concept": concept, "concept_cand": dg._dilate(concept, 1), "render": rcore, "render_cand": dg._dilate(rcore, 1),
                "own": dg._box_mask((H, W), [18, 20, 40, 14]), "zone": dg._box_mask((H, W), [10, 10, 60, 34])}}
    return ref, comp, render, gm, np.tile(BG, (H, W, 1))


def test_glyph_residue_finds_texture_leftover_but_not_engine_effects():
    ref, comp, render, gm, plate = _scene()
    texts = [{"id": "T", "type": "TextBlock", "font": {"glow": {"size": 3}}}]
    out = dg.glyph_residue(ref, comp, gm, texts, plate, render=render)
    blobs = out["T"]["blobs"]
    assert len(blobs) == 1
    x, y, w, h = blobs[0]["box"]
    assert 45 <= x <= 47 and x + w >= 51 and blobs[0]["area"] >= 6 and blobs[0]["mean_de"] > 20
    # 엔진 빛(렌더만 다름 — 텍스처는 바탕 그대로)과 렌더 획이 안 덮은 깨끗한 컨셉 획 자리(41 ~ 45)는 잔상이 아니다
    assert not any(b["box"][0] < 44 for b in blobs)


def test_concept_contrast_flags_background_measured_as_glyph():
    """컨셉 '획'이 둘레 바탕과 같은 색이면(번진 상자 틈을 글자로 잼) 측정 실패 — 비교하지 않고 E6 unmeasured."""
    H, W = 50, 80
    ref = np.zeros((H, W, 3))
    glyph = np.zeros((H, W), bool)
    glyph[15:35, 20:24] = glyph[15:19, 20:50] = True
    ref[glyph] = INK
    assert dg.concept_contrast(glyph, dg._dilate(glyph, 1), ref) > 60
    gap = dg._box_mask((H, W), [10, 10, 50, 30]) & ~dg._dilate(glyph, 2)        # 바탕(검정) 틈을 '획'으로 잡은 것
    assert dg.concept_contrast(gap, gap, ref) < dg.CONCEPT_CONTRAST_MIN
    masks = {"concept": gap, "concept_cand": gap, "render": gap, "render_cand": gap}
    rec = dg.compare_text({"id": "T", "font": {}}, masks, ref, ref, ref, dg.settings(None))
    assert rec["causes"] == ["unmeasured"] and rec["codes"] == ["E6"] and rec["unmeasured"]["concept_contrast"] < 10


def test_regress_set_defect_diff_and_set():
    """비교 묶음 — 같은 오류 번호 · 위젯 · 겹친 상자(글자 결함은 위젯만)면 같은 결함, 나머지는 새 · 사라짐. 고정 입력 이름은 겹치지 않고 보호 입력이 있다."""
    import regress_set as rs
    old = [{"code": "E1", "stage": "texture", "widgets": ["A"], "box": [10, 10, 5, 5]},
           {"code": "E6", "stage": "text", "widgets": ["T"], "box": [0, 0, 20, 10]},
           {"code": "E9", "stage": "text", "widgets": ["U"], "box": [50, 0, 20, 10]}]
    new = [{"code": "E1", "stage": "texture", "widgets": ["A"], "box": [12, 12, 5, 5]},
           {"code": "E6", "stage": "text", "widgets": ["T"], "box": [3, 2, 20, 10]},
           {"code": "E1", "stage": "texture", "widgets": ["A"], "box": [100, 100, 5, 5]}]
    d = rs.diff_defects(old, new)
    assert len(d["kept"]) == 2 and [x["code"] for x in d["gone"]] == ["E9"] and [x["box"] for x in d["new"]] == [[100, 100, 5, 5]]
    assert rs._num_diff([1.0, 2.0], [1.0, 2.6], 0.5) and not rs._num_diff(0.95, 0.952, 0.005) and rs._num_diff(["size"], [], 0.5)
    names = [e["name"] for e in rs.SET]
    assert len(names) == len(set(names)) and any(e.get("protect") for e in rs.SET)


def test_glyph_residue_clean_texture_and_texture_only_mode():
    ref, comp, render, gm, plate = _scene()
    texts = [{"id": "T", "type": "TextBlock"}]
    clean = np.tile(BG, comp.shape[:2] + (1,))
    rend_clean = render.copy()
    rend_clean[26:30, 46:52] = BG
    assert dg.glyph_residue(ref, clean, gm, texts, plate, render=rend_clean)["T"]["blobs"] == []
    # 렌더가 잔상을 덮으면(렌더 획이 거기까지) 안 보인다 — 렌더 후보 밖만 본다
    gm2 = {"T": dict(gm["T"], render=dg._dilate(gm["T"]["concept"], 0), render_cand=dg._dilate(gm["T"]["concept"], 1))}
    assert dg.glyph_residue(ref, comp, gm2, texts, plate, render=render)["T"]["blobs"] == []
    # 렌더 없이(오프라인 replay — 텍스처 합성만) — 자리는 컨셉 획 전체
    only = dg.glyph_residue(ref, comp, gm, texts, plate, render=None)["T"]
    assert only["blobs"] and only["zone_px"] > dg.glyph_residue(ref, comp, gm, texts, plate, render=render)["T"]["zone_px"]
    # 판이 그 자리에 같은 밝은 구조물을 그렸으면(판이 지킨 구조선) 잔상이 아니다
    plate2 = plate.copy()
    plate2[26:30, 46:52] = comp[26:30, 46:52]
    assert dg.glyph_residue(ref, comp, gm, texts, plate2, render=render)["T"]["blobs"] == []
