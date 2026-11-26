"""1b-5 — codex 생성 연결(가짜 codex) · refine 후처리(배경 · 자르기 · 크기 · 9-slice · OCR) · baked_text → 재생성."""
from __future__ import annotations

import json
import pathlib
import sys
import types

import pytest
from conftest import fixture_brief, fixture_spec, widget
from PIL import Image, ImageDraw, ImageFont

from core import config
from core.run import Run
from gen import codex
from gen import postprocess as pp
from stages import fix, generate, refine

FAKE_CODEX = [sys.executable, "-X", "utf8", "-B", str(pathlib.Path(__file__).with_name("fake_codex.py"))]
CFG = config.load_pipeline()
GOLD, DARK = (232, 181, 74, 255), (30, 20, 12, 230)


def frame_image(w=240, h=80, border=6, bg=None, ornament=False) -> Image.Image:
    im = Image.new("RGBA", (w, h), bg or (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([4, 4, w - 5, h - 5], fill=DARK)
    for i in range(border):
        d.rectangle([4 + i, 4 + i, w - 5 - i, h - 5 - i], outline=GOLD)
    if ornament:
        d.polygon([(w // 2 - 14, 4), (w // 2, 0), (w // 2 + 14, 4), (w // 2, 20)], fill=GOLD)
    return im


def _run(tmp_path, spec: dict, with_reference: bool = True) -> Run:
    run = Run("R20261115_130000_CombatHUD", tmp_path / "work", CFG, tmp_path / "m.jsonl")
    run.create()
    run.write_json("spec.json", spec)
    run.write_json("brief.json", fixture_brief())
    if with_reference:
        ref = Image.new("RGB", (1920, 1080), (40, 30, 60))
        d = ImageDraw.Draw(ref)
        d.rectangle([1612, 140, 1872, 272], fill=(60, 40, 80))
        d.rectangle([1700, 180, 1790, 230], fill=(255, 255, 255))     # '글자' 자리(ChainTimerText 근처)
        ref.save(run.path("reference.png"))
    return run


def codex_spec() -> dict:
    spec = fixture_spec()
    a = spec["assets"][1]          # chain_panel_bg → codex
    a.update(provenance="codex", prompt="ornate dark purple HUD panel with thin gold border", ref_bbox=[1612, 140, 260, 132])
    a.pop("procedural", None)
    return spec


# ---- postprocess ----------------------------------------------------------------------------------------------------

def test_background_removed_trimmed_and_margin_estimated():
    raw = frame_image(bg=(250, 250, 250, 255))                              # 불투명 흰 바탕 위 프레임
    im, info = pp.remove_background(raw)
    assert info["method"] == "border_flood_fill" and info["removed_ratio"] > 0.05 and pp.alpha_stats(im)["has_alpha"]
    im, box = pp.trim(im)
    assert box[0] <= 4 and box[2] >= 230
    im, how = pp.fit(im, [320, 160], stretch=True)
    assert how == "stretch" and im.size == (320, 160)
    m = pp.estimate_nine_slice(im)
    assert m is not None and all(0.01 <= v <= 0.2 for v in m)


def test_margin_estimate_gives_up_on_center_ornament_axis_only():
    """가운데 큰 장식(28 px — 끊김 허용 2 % 보다 넓음)은 가로 늘림을 막는다 → 가로 축만 실패(spec 값), 세로는 추정(1b 후속 A — 축별)."""
    im, _ = pp.trim(frame_image(ornament=True))
    m = pp.estimate_nine_slice(im)
    assert m is not None and m[0] is None and m[2] is None and m[1] is not None and m[3] is not None
    used, source = pp.merge_margin(m, [0.1, 0.2, 0.1, 0.2])
    assert source == "mixed" and used[0] == 0.1 and used[2] == 0.1 and used[1] == m[1]
    assert pp.merge_margin(m, None) == (None, "mixed")


def test_contain_fit_keeps_aspect():
    im, how = pp.fit(frame_image(100, 100), [200, 50], stretch=False)
    assert how == "contain" and im.size == (200, 50) and im.getpixel((0, 25))[3] == 0      # 양옆은 투명


def test_reference_crop_erases_text_boxes(tmp_path):
    ref = tmp_path / "ref.png"
    img = Image.new("RGB", (400, 200), (60, 40, 80))
    ImageDraw.Draw(img).rectangle([150, 80, 250, 120], fill=(255, 255, 255))
    img.save(ref)
    info = pp.reference_crop(ref, [100, 50, 200, 100], [[150, 80, 100, 40], [0, 0, 10, 10]], tmp_path / "out" / "crop.png")
    assert info["text_boxes_erased"] == 1 and info["region"] == [92, 42, 216, 116]
    out = Image.open(tmp_path / "out" / "crop.png")
    assert max(out.getpixel((200 - 92, 100 - 42))) < 200                                # 흰 글자 자리가 주변색으로


def test_reference_crop_erases_only_the_glyphs_and_keeps_a_frame_line_in_the_line_box(tmp_path):
    """1b 후속 G2 — [실측 파티 HUD] 줄 상자 전체를 지우자 그 안으로 내려온 HP 프레임 윗선이 끊겼다 → 글자 획 둘레만 지우고, 런타임 이미지는 상자째."""
    ref = tmp_path / "ref.png"
    img = Image.new("RGB", (400, 200), (40, 30, 50))
    d = ImageDraw.Draw(img)
    for i in range(4):
        d.rectangle([160 + 20 * i, 85, 167 + 20 * i, 110], fill=(255, 255, 255))      # 글자 획
    d.line([(100, 122), (300, 122)], fill=(120, 220, 230), width=2)                     # 줄 상자(80 ~ 125) 아래쪽을 가로지르는 프레임 선
    d.rectangle([20, 60, 80, 140], fill=(200, 120, 90))                                 # 런타임 이미지 자리의 그림
    img.save(ref)
    info = pp.reference_crop(ref, [10, 50, 330, 100], [[150, 80, 100, 45]], tmp_path / "crop.png", image_boxes=[[20, 60, 60, 80]])
    out = Image.open(tmp_path / "crop.png").convert("RGB")
    ox, oy = info["region"][:2]
    assert info["text_boxes_erased"] == 2 and info["erased_by_glyph_ink"] == 1
    assert max(out.getpixel((163 - ox, 98 - oy))) < 200                                 # 글자 획은 지워짐
    assert out.getpixel((200 - ox, 122 - oy))[1] > 180                                  # 프레임 선은 그대로
    assert abs(out.getpixel((50 - ox, 100 - oy))[0] - 200) > 60                         # 런타임 이미지 그림은 상자째 지워짐


# ---- generate(codex) ------------------------------------------------------------------------------------------------

@pytest.fixture
def fake_codex(tmp_path, monkeypatch):
    log = tmp_path / "codex_log.jsonl"
    monkeypatch.setenv("FAKE_CODEX_LOG", str(log))
    for k in ("FAKE_CODEX_MODE", "FAKE_CODEX_LOGIN", "FAKE_CODEX_VERSION"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(codex, "default_cli", lambda cdx: FAKE_CODEX)
    return log


def test_generate_codex_asset_with_cropped_reference(tmp_path, fake_codex):
    run = _run(tmp_path, codex_spec())
    detail = generate.run(run, types.SimpleNamespace(attempt=1))
    assert "chain_panel_bg(codex" in detail and "codex calls this run 1/20" in detail
    recs = [json.loads(x) for x in run.path("gen.jsonl").read_text(encoding="utf-8").splitlines()]
    c = next(r for r in recs if r["asset_id"] == "chain_panel_bg")
    assert c["backend"] == "codex" and c["thread_id"] and c["found_by"] == "thread_id" and c["ref"]["text_boxes_erased"] >= 1
    assert run.path("assets", "raw", "chain_panel_bg.png").is_file() and run.path("gen", "chain_panel_bg", "001", "ref.png").is_file()
    assert run.record["codex_cli"]["version"] == "0.166.0"
    call = [json.loads(x) for x in fake_codex.read_text(encoding="utf-8").splitlines()][0]
    prompt = call["argv"][1]
    assert "ornate dark purple HUD panel" in prompt and "No text" not in prompt and "Absolutely no text" in prompt and "320:160" in prompt
    assert call["argv"][-1].replace("\\", "/").endswith("gen/chain_panel_bg/001/ref.png")
    assert not (tmp_path / "work" / ".codex.lock").exists()                                # 단계가 끝나면 잠금을 푼다


def test_regenerate_adds_the_no_text_note(tmp_path, fake_codex):
    run = _run(tmp_path, codex_spec())
    generate.run(run, types.SimpleNamespace(attempt=2, only_assets=["chain_panel_bg"]))
    prompt = json.loads(fake_codex.read_text(encoding="utf-8").splitlines()[0])["argv"][1]
    assert "previous version contained text-like marks" in prompt


def test_codex_quota_stops_the_stage(tmp_path, fake_codex, monkeypatch):
    from stages import StageError
    monkeypatch.setenv("FAKE_CODEX_MODE", "quota")
    run = _run(tmp_path, codex_spec())
    with pytest.raises(StageError) as e:
        generate.run(run, types.SimpleNamespace(attempt=1))
    assert e.value.code == "CODEX_QUOTA"


# ---- refine(생성 이미지) ----------------------------------------------------------------------------------------------

def _gen_line(run, aid, backend="codex"):
    run.append_jsonl("gen.jsonl", {"asset_id": aid, "backend": backend, "ok": True})


def _procedural_raws(run, spec):
    from core import png
    from gen import procedural
    for a in spec["assets"]:
        if a["provenance"] == "procedural":
            w, h, rgba = procedural.render(a)
            png.write_rgba(run.path("assets", "raw", f"{a['asset_id']}.png"), w, h, rgba)
            _gen_line(run, a["asset_id"], "procedural")


def test_refine_generated_asset_updates_margins(tmp_path):
    spec = codex_spec()
    run = _run(tmp_path, spec)
    _procedural_raws(run, spec)
    frame_image(600, 300, border=10, bg=(255, 255, 255, 255)).save(run.path("assets", "raw", "chain_panel_bg.png"))
    _gen_line(run, "chain_panel_bg")
    detail = refine.run(run, types.SimpleNamespace(attempt=1))
    m = {a["asset_id"]: a for a in run.read_json("manifest.json")["assets"]}["chain_panel_bg"]
    assert m["size"] == [320, 160] and m["alpha"] and m["ocr_text"] == "" and "rapidocr" in m["ocr"]
    log = run.read_json("refine.json")["passes"][0]
    a = next(x for x in log["assets"] if x["asset_id"] == "chain_panel_bg")
    assert a["background"]["method"] == "border_flood_fill" and a["margin"]["source"] == "estimated"
    new_spec = run.read_json("spec.json")
    assert widget(new_spec, "ChainPanel")["style"]["brush"]["margin"] == a["margin"]["estimated"]
    assert any(c["where"] == "ChainPanel.style.brush" for c in log["margin_updates"]) and "margins from the images" in detail


def test_refine_detects_baked_text(tmp_path):
    spec = codex_spec()
    run = _run(tmp_path, spec)
    _procedural_raws(run, spec)
    im = frame_image(640, 320, border=10)
    ImageDraw.Draw(im).text((150, 110), "CHAIN 42", fill=(255, 240, 200, 255), font=ImageFont.load_default(size=72))
    im.save(run.path("assets", "raw", "chain_panel_bg.png"))
    _gen_line(run, "chain_panel_bg")
    refine.run(run, types.SimpleNamespace(attempt=1))
    m = {a["asset_id"]: a for a in run.read_json("manifest.json")["assets"]}["chain_panel_bg"]
    assert m["ocr_text"] and "text-like box" in m["ocr_text"]


def test_baked_text_gate_asks_for_regeneration():
    gates = [{"name": "baked_text", "pass": False, "details": {"found": [{"asset_id": "chain_panel_bg", "text": "2 text-like box(es)"}], "not_checked": []}}]
    fixes, ops = fix.propose_deterministic(fixture_spec(), gates, [])
    assert ops == [{"op": "replace_asset", "asset": "chain_panel_bg", "regenerate": True, "reason": "OCR found text-like marks: 2 text-like box(es)"}]
    assert fixes[0]["gate"] == "baked_text"
