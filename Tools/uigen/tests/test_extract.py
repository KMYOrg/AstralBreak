"""1b 후속 A — 컨셉에서 따오기(source_mode: extract): 입력 조각 · 되자르기 · 안쪽 알파 · 9-slice 축별 추정 · analyze 검사 · 스키마 ·
계약 해시 · 왕복 영향 없음 · generate(가짜 codex 편집 틀) · refine(충실도 기록 · 나란히 그림)."""
from __future__ import annotations

import json
import pathlib
import sys
import types

import pytest
from conftest import fixture_brief, fixture_spec, widget
from PIL import Image, ImageDraw

from core import config, cppgen, schema
from core import spec as spec_mod
from core.run import Run
from gen import codex
from gen import postprocess as pp
from stages import StageError, analyze, generate, refine

FAKE_CODEX = [sys.executable, "-X", "utf8", "-B", str(pathlib.Path(__file__).with_name("fake_codex.py"))]
CFG = config.load_pipeline()
CFG_G = {**CFG, "extract": {**CFG["extract"], "cutout": False}}     # 1b 후속 H 앞의 따오기(codex 편집 + 옮겨 심기) — cutout 을 끈 판
GOLD, DARK, SCENE = (232, 181, 74, 255), (30, 20, 40, 255), (40, 30, 60)
FRAME = [1600, 150, 280, 120]                 # reference 안 패널 자리
REF_BBOX = [1598, 148, 284, 124]


def draw_frame(d: ImageDraw.ImageDraw, x, y, w, h, border):
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=DARK)
    for i in range(border):
        d.rectangle([x + i, y + i, x + w - 1 - i, y + h - 1 - i], outline=GOLD)


def extract_spec() -> dict:
    spec = fixture_spec()
    a = next(x for x in spec["assets"] if x["asset_id"] == "chain_panel_bg")
    a.update(provenance="codex", source_mode="extract", prompt="a rectangular panel with a thin gold border", ref_bbox=list(REF_BBOX))
    a.pop("procedural", None)
    widget(spec, "ChainPanel")["bbox_intent"] = list(REF_BBOX)       # 따온 텍스처는 이 위젯 상자로 되자른다(1:1)
    return spec


def make_run(tmp_path, spec, cfg=None) -> Run:
    run = Run("R20261115_140000_CombatHUD", tmp_path / "work", cfg or CFG, tmp_path / "m.jsonl")
    run.create()
    run.write_json("spec.json", spec)
    run.write_json("brief.json", fixture_brief())
    ref = Image.new("RGB", (1920, 1080), SCENE)
    draw_frame(ImageDraw.Draw(ref), *FRAME, border=4)
    ref.save(run.path("reference.png"))
    return run


# ---- 입력 조각 · 되자르기 ------------------------------------------------------------------------------------------------

def test_extract_region_widens_thin_elements_with_real_pixels():
    region, element, ok = pp.extract_region([546, 912, 828, 64], (1920, 1080))
    assert region == [538, 798, 844, 282] and ok                    # [실측 A-1] 게이지 — 위로 밀어 넣어 3:1(2.993)
    assert element == [0, 106, 844, 80]
    region, element, ok = pp.extract_region([1543, 168, 338, 202], (1920, 1080))
    assert region == [1535, 160, 354, 218] and element == [0, 0, 354, 218] and ok      # 1.6:1 — 그대로
    region, element, ok = pp.extract_region([10, 100, 20, 900], (1920, 1080))           # 세로로 긴 것 — 가로를 넓힘(왼쪽 가장자리)
    assert region[0] == 0 and region[3] / region[2] <= 3.0 + 1e-6 and ok
    assert element[0] + element[2] <= region[2] and element[1] + element[3] <= region[3]


def test_extract_input_erases_text_inside_the_widened_region(tmp_path):
    ref = tmp_path / "ref.png"
    img = Image.new("RGB", (1920, 1080), SCENE)
    d = ImageDraw.Draw(img)
    draw_frame(d, 546, 912, 828, 64, 3)
    d.rectangle([860, 854, 1060, 897], fill=(255, 255, 255))                           # 게이지 위 '오의 불가' 자리
    img.save(ref)
    info = pp.extract_input(ref, [546, 912, 828, 64], [[860, 854, 200, 43]], tmp_path / "in.png")
    assert info["region"] == [538, 798, 844, 282] and info["text_boxes_erased"] == 1 and info["aspect"] <= 3.0
    out = Image.open(tmp_path / "in.png")
    assert out.size == (844, 282) and max(out.getpixel((960 - 538, 875 - 798))) < 200


def test_crop_back_maps_the_element_box_from_the_edited_canvas():
    region, element = [100, 50, 300, 100], [20, 30, 260, 40]
    im = Image.new("RGBA", (600, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle([40, 60, 40 + 520 - 1, 60 + 80 - 1], fill=(255, 0, 0, 255))
    out, info = pp.crop_back(im, region, element)
    assert info["scale"] == [2.0, 2.0] and info["canvas_aspect_change_pct"] == 0.0
    assert out.size == ((260 + 4) * 2, (40 + 4) * 2)
    assert out.getpixel((out.width // 2, out.height // 2)) == (255, 0, 0, 255) and out.getpixel((1, 1))[3] == 0


def test_interior_fill_makes_only_the_inside_see_through():
    im = Image.new("RGBA", (300, 120), (0, 0, 0, 0))
    draw_frame(ImageDraw.Draw(im), 4, 4, 292, 112, 6)
    out, info = pp.interior_fill(im, 0.9)
    assert info["flattened"] and 0.5 < info["changed_ratio"] < 0.95 and info["holes_before"] == 0.0
    assert out.getpixel((150, 60))[3] in (229, 230) and out.getpixel((6, 60))[3] >= 250 and out.getpixel((1, 1))[3] == 0   # 금테는 그대로(번짐 1.5 px)


def test_interior_fill_keeps_a_dark_edge_band_when_the_frame_touches_the_texture_edge():
    """[실측 B run] 따온 텍스처는 위젯 상자로 바짝 자르므로 프레임이 그림 가장자리에 닿는다 — 가장자리의 어두운 띠를 안쪽으로 칠하면 안 된다."""
    im = Image.new("RGBA", (300, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 299, 119], fill=DARK)                       # 가장자리까지 어두운 바탕(그림자 띠)
    for i in range(2, 7):
        d.rectangle([i, i, 299 - i, 119 - i], outline=GOLD)
    out, _ = pp.interior_fill(im, 0.9)
    assert out.getpixel((0, 60))[3] == 255 and out.getpixel((1, 60))[3] == 255 and out.getpixel((150, 60))[3] in (229, 230)


def test_interior_fill_closes_holes_left_where_text_was():
    """[실측 A run] 편집이 글자 자리를 구멍(알파 6 ~ 19)으로 남긴 판 — 평탄화가 대표색 · 알파 0.9 로 메운다. flatten 을 끄면 알파 배수만."""
    im = Image.new("RGBA", (300, 120), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    draw_frame(d, 4, 4, 292, 112, 6)
    d.rectangle([90, 40, 210, 80], fill=(0, 0, 0, 12))
    out, info = pp.interior_fill(im, 0.9)
    assert info["holes_before"] > 0.1 and info["fill_color"] == "#1E1428"
    assert out.getpixel((150, 60)) [:3] == DARK[:3] and out.getpixel((150, 60))[3] in (229, 230)
    off, info2 = pp.interior_fill(im, 0.9, flatten=False)
    assert not info2["flattened"] and off.getpixel((150, 60))[3] <= 12


# ---- 9-slice 추정(축별 · 가운데 표식 건너뜀 · 얇은 모서리 장식) ------------------------------------------------------------

def ornate_frame(w=400, h=200) -> Image.Image:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    draw_frame(d, 2, 2, w - 4, h - 4, 4)
    for cx, sx in ((8, 1), (w - 9, -1)):                     # 모서리 장식: 가로 60 px · 세로 40 px 의 3 px 선
        for cy, sy in ((8, 1), (h - 9, -1)):
            d.rectangle([min(cx, cx + sx * 60), cy - 1, max(cx, cx + sx * 60), cy + 1], fill=GOLD)
            d.rectangle([cx - 1, min(cy, cy + sy * 40), cx + 1, max(cy, cy + sy * 40)], fill=GOLD)
    d.polygon([(w // 2 - 1, 0), (w // 2 + 1, 0), (w // 2 + 1, 8), (w // 2 - 1, 8)], fill=GOLD)      # 위 가운데 표식(3 px)
    d.polygon([(0, h // 2 - 1), (8, h // 2 - 1), (8, h // 2 + 1), (0, h // 2 + 1)], fill=GOLD)      # 왼쪽 가운데 표식
    return im


def test_nine_slice_covers_thin_corner_ornaments_and_skips_center_marks():
    m = pp.estimate_nine_slice(ornate_frame())
    assert m is not None and None not in m
    assert m[0] >= 68 / 400 - 0.01 and m[2] >= 68 / 400 - 0.01          # 장식 끝 x = 8 + 60
    assert m[1] >= 48 / 200 - 0.01 and m[3] >= 48 / 200 - 0.01          # 장식 끝 y = 8 + 40
    assert max(m) < 0.3


def test_old_center_reference_failure_is_gone():
    """옛 방식은 가운데 열이 표식이면 띠가 0 이 됐다 — 같은 그림에서 새 방식은 추정한다."""
    im = ornate_frame()
    assert pp.estimate_nine_slice(im)[0] is not None


def test_nine_slice_skips_a_wider_mark_near_the_center_only():
    """[실측 A run] 변 가운데 표식이 2 % 보다 넓은 판(2.9 · 3.3 %, 가운데에서 몇 px 비켜남) — 가운데 ±5 % 안에서 시작한 끊김은 4 % 까지 건너뛴다."""
    im = ornate_frame()
    d = ImageDraw.Draw(im)
    d.rectangle([200 - 6, 0, 200 + 6, 10], fill=GOLD)               # 위 가운데 13 px(3.3 %)
    d.rectangle([0, 104, 10, 110], fill=GOLD)                        # 왼쪽 — 가운데(100)에서 4 px 아래, 7 px(3.5 %)
    m = pp.estimate_nine_slice(im)
    assert m is not None and None not in m and max(m) < 0.3
    d.rectangle([60, 120, 340, 132], fill=GOLD)                      # 가운데에서 먼 굵은 가로 띠(6 %) — 세로 띠가 거기서 끊긴다
    assert pp.estimate_nine_slice(im)[3] > 0.3


# ---- analyze 검사 · 스키마 · 계약 · 왕복 ----------------------------------------------------------------------------------

def _mode_errors(spec):
    return [e for e in analyze.check(spec, fixture_brief()) if e.startswith(("ASSET_SOURCE_MODE", "ASSET_REF_BBOX"))]


def test_analyze_check_source_mode_rules():
    spec = extract_spec()
    assert _mode_errors(spec) == []
    a = next(x for x in spec["assets"] if x["asset_id"] == "chain_panel_bg")
    a.pop("ref_bbox")
    assert any("source_mode extract" in e for e in _mode_errors(spec))
    proc = fixture_spec()
    next(x for x in proc["assets"] if x["asset_id"] == "ult_frame")["source_mode"] = "extract"
    assert any(e.startswith("ASSET_SOURCE_MODE") for e in _mode_errors(proc))


def test_spec_schema_accepts_source_mode_only_from_the_enum():
    spec = extract_spec()
    assert schema.errors("spec", spec) == []
    next(x for x in spec["assets"] if x["asset_id"] == "chain_panel_bg")["source_mode"] = "copy"
    assert schema.errors("spec", spec)


def test_source_mode_does_not_touch_contract_or_roundtrip():
    base, ext = fixture_spec(), extract_spec()
    base_a = next(x for x in base["assets"] if x["asset_id"] == "chain_panel_bg")
    base_a.update(provenance="codex", prompt="p", ref_bbox=list(REF_BBOX))
    base_a.pop("procedural", None)
    assert cppgen.binding_entries(base) == cppgen.binding_entries(ext)
    assert spec_mod.roundtrip_view(base) == spec_mod.roundtrip_view(ext)
    assert next(x for x in spec_mod.normalize(ext)["assets"] if x["asset_id"] == "chain_panel_bg")["source_mode"] == "extract"


# ---- generate(가짜 codex) · refine --------------------------------------------------------------------------------------

@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    log = tmp_path / "codex_log.jsonl"
    monkeypatch.setenv("FAKE_CODEX_LOG", str(log))
    for k in ("FAKE_CODEX_MODE", "FAKE_CODEX_LOGIN", "FAKE_CODEX_VERSION"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(codex, "default_cli", lambda cdx: FAKE_CODEX)
    return log


def test_generate_extract_uses_the_edit_wrapper_and_records_the_box(tmp_path, fake_codex):
    run = make_run(tmp_path, extract_spec())
    generate.run(run, types.SimpleNamespace(attempt=1))
    call = [json.loads(x) for x in fake_codex.read_text(encoding="utf-8").splitlines()][0]
    prompt = call["argv"][1]
    assert "EDIT the attached image" in prompt and "Preserve invariants aggressively" in prompt and "references only" not in prompt
    assert "a rectangular panel with a thin gold border" in prompt and "Keep the same framing" in prompt and "flat color" in prompt
    assert call["argv"][-1].replace("\\", "/").endswith("gen/chain_panel_bg/001/input.png")
    rec = next(json.loads(x) for x in run.path("gen.jsonl").read_text(encoding="utf-8").splitlines() if '"chain_panel_bg"' in x)
    region, element, _ = pp.extract_region(REF_BBOX, (1920, 1080))
    assert rec["source_mode"] == "extract" and rec["extract"]["region"] == region and rec["extract"]["element"] == element
    assert json.loads(run.path("codex_calls.jsonl").read_text(encoding="utf-8").splitlines()[0])["mode"] == "edit"


def test_generate_extract_without_ref_bbox_stops(tmp_path, fake_codex):
    spec = extract_spec()
    next(x for x in spec["assets"] if x["asset_id"] == "chain_panel_bg").pop("ref_bbox")
    run = make_run(tmp_path, spec)
    with pytest.raises(StageError) as e:
        generate.run(run, types.SimpleNamespace(attempt=1))
    assert e.value.code == "EXTRACT_NO_REFERENCE" and not fake_codex.exists()


def test_refine_extract_crops_back_adds_interior_alpha_and_records_fidelity(tmp_path):
    from core import png
    from gen import procedural
    import run_pipeline
    spec = extract_spec()
    run = make_run(tmp_path, spec, CFG_G)
    for a in spec["assets"]:
        if a["provenance"] == "procedural":
            w, h, rgba = procedural.render(a)
            png.write_rgba(run.path("assets", "raw", f"{a['asset_id']}.png"), w, h, rgba)
            run.append_jsonl("gen.jsonl", {"asset_id": a["asset_id"], "backend": "procedural", "ok": True})
    region, element, _ = pp.extract_region(REF_BBOX, (1920, 1080))
    raw = Image.new("RGBA", (region[2] * 2, region[3] * 2), (0, 0, 0, 0))             # 편집 결과: 같은 구도 · 2배 · 장면 투명
    draw_frame(ImageDraw.Draw(raw), (FRAME[0] - region[0]) * 2, (FRAME[1] - region[1]) * 2, FRAME[2] * 2, FRAME[3] * 2, 8)
    raw.save(run.path("assets", "raw", "chain_panel_bg.png"))
    run.append_jsonl("gen.jsonl", {"asset_id": "chain_panel_bg", "backend": "codex", "ok": True, "source_mode": "extract",
                                   "extract": {"region": region, "element": element}})
    detail = refine.run(run, types.SimpleNamespace(attempt=1))
    assert "extracted from the concept: ['chain_panel_bg']" in detail
    log = next(a for a in run.read_json("refine.json")["passes"][0]["assets"] if a["asset_id"] == "chain_panel_bg")
    cp = log["concept_pixels"]                                                            # 1b 후속 G — 안쪽 한 색 대신 컨셉 픽셀 옮겨 심기
    assert log["source_mode"] == "extract" and log["crop_back"]["scale"] == [2.0, 2.0] and cp["applied"] and cp["interior_ratio"] > 0.3
    assert "interior" not in log and cp["silhouette_iou"] > 0.95 and cp["registration"]["shift_px"] == [0, 0]
    assert log["crop_back"]["target_box"] == REF_BBOX and log["trim_bbox"].startswith("skipped")          # 위젯 상자 그대로 · trim 없음
    f = log["fidelity"]
    assert f["framing"]["center_offset_px"] == [pytest.approx(0, abs=1.5), pytest.approx(0, abs=1.5)] and f["framing"]["iou"] > 0.95
    assert abs(f["aspect"]["error_pct"]) < 2 and f["shape_iou"] > 0.95 and f["line_f1"]["f1"] > 0.8
    assert f["delta_e00"]["lines"] < 3 and f["delta_e00"]["interior"] < 5                 # 안쪽 90 % 를 장면 위에 얹어도 가까움
    assert run.path(f["compare"]).is_file()
    m = {a["asset_id"]: a for a in run.read_json("manifest.json")["assets"]}["chain_panel_bg"]
    assert m["size"] == [320, 160] and m["ocr_text"] == ""
    summary = run_pipeline._extract_fidelity_summary(run)
    assert set(summary) == {"chain_panel_bg"} and summary["chain_panel_bg"]["shape_iou"] == f["shape_iou"]
    brush = widget(run.read_json("spec.json"), "ChainPanel")["style"]["brush"]
    assert brush == {"draw_as": "image", "asset": "chain_panel_bg"}                       # 크기 고정(점 앵커) → box 대신 image, margin 없음
    bu = run.read_json("refine.json")["passes"][0]["brush_updates"]
    assert bu == [{"widget": "ChainPanel", "key": "brush", "asset": "chain_panel_bg", "old": {"draw_as": "box", "margin": log["margin"]["used"]},
                   "new": {"draw_as": "image"}}]
    assert "fixed-size brushes drawn as image: ['ChainPanel']" in detail
    Image.open(run.path("reference.png")).convert("RGBA").save(run.path("render.png"))     # 렌더 = 컨셉이면 이식 지표가 만점
    rendered = run_pipeline._extract_fidelity_summary(run)["chain_panel_bg"]["render"]
    assert len(rendered) == 1 and rendered[0]["widget"] == "ChainPanel" and rendered[0]["draw_as"] == "image"
    assert rendered[0]["line_f1"]["f1"] == 1.0 and rendered[0]["delta_e00"]["lines"] == 0.0 and run.path(rendered[0]["compare"]).is_file()


def test_extract_brush_stays_box_when_the_region_stretches():
    spec = extract_spec()
    widget(spec, "ChainPanel")["slot"]["anchors"] = [0.8, 0, 1, 0]                       # 늘림 앵커 — 해상도마다 폭이 바뀐다
    assert not refine.fixed_size(spec, "ChainPanel") and refine.fixed_size(extract_spec(), "ChainPanel")
    assert refine._extract_brushes_to_image(spec, {"chain_panel_bg"}) == []
    assert widget(spec, "ChainPanel")["style"]["brush"]["draw_as"] == "box"
    child = next(w for w in extract_spec()["widgets"] if w.get("parent") == "ChainPanel")
    assert refine.fixed_size(extract_spec(), child["id"])                                  # 고정 영역 안의 자식도 고정


def test_render_vs_concept_sees_box_distortion():
    """같은 그림이면 장식선 F1 1 · ΔE 0, 9-slice 로 모서리가 커지고 가운데가 눌린 렌더는 낮게 나온다."""
    from gen import fidelity
    concept = Image.new("RGB", (300, 120), SCENE)
    draw_frame(ImageDraw.Draw(concept), 10, 10, 280, 100, 4)
    same, _ = fidelity.render_vs_concept(concept, concept)
    assert same["line_f1"]["f1"] == 1.0 and same["delta_e00"]["lines"] == 0.0 and same["shape_iou"] == 1.0
    squashed = Image.new("RGB", (300, 120), (0, 0, 0))
    draw_frame(ImageDraw.Draw(squashed), 10, 30, 280, 60, 8)                                  # 높이가 눌리고 테두리가 두 배
    bad, sheet = fidelity.render_vs_concept(concept, squashed)
    assert bad["line_f1"]["f1"] < 0.6 and bad["shape_iou"] < 0.7 and sheet.size[0] >= 300
