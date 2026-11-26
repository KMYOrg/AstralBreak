"""1b 후속 I — 'UI 만 · 진짜 알파' 컨셉 자동 변환(gen/concept_convert · normalize): codex 편집 2 회 · 캐시(다시 돌리면 codex 0) · 상한 ·
검사 탈락 / 한도 때 예전 경로로 물러남 · 출처 기록 · normalize 가 ⓐ 로 잇기."""
from __future__ import annotations

import pathlib
import sys
import types

import numpy as np
import pytest
import yaml
from PIL import Image

from core import config
from core.run import Run
from gen import codex, concept_convert
from stages import normalize

FAKE = [sys.executable, "-X", "utf8", "-B", str(pathlib.Path(__file__).with_name("fake_codex.py"))]
INPUTS = {"text": "조작 안내 — 가운데 다이아몬드", "required_elements": [{"id": "Dash", "kind": "text", "desc": "돌진 공격 띠"}, {"id": "Emb"}],
          "static_text": [{"widget": "DashLabelText", "value": "돌진 공격"}]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(codex, "work_root", lambda cfg: tmp_path / "work")
    return tmp_path


def _scene(path: pathlib.Path, size=(160, 80)):
    rng = np.random.default_rng(7)
    arr = rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)          # 장면(테두리가 한 색이 아님 — ⓒ)
    Image.fromarray(arr).save(path)


def _run(tmp: pathlib.Path, name: str) -> Run:
    run = Run(name, tmp / "work", config.load_pipeline(), tmp / "m.jsonl")
    run.create()
    return run


def test_convert_scene_concept_twice_uses_the_cache(env, monkeypatch):
    src = env / "scene.png"
    _scene(src)
    assert concept_convert.source_kind(src, "auto")["kind"] == "scene"
    assert concept_convert.wanted("auto", "scene") and not concept_convert.wanted("auto", "flat") and concept_convert.wanted("force", "flat")
    assert not concept_convert.wanted("off", "scene") and not concept_convert.wanted("force", "transparent")
    run = _run(env, "R20261117_150000_ProbeControlGuide")
    rec = concept_convert.convert(run, src, INPUTS, "auto", "scene", cli=FAKE)
    assert rec["used"] and rec["codex_calls"] == 2 and rec["notext"]["used"] and not rec["concept"]["cached"]
    assert run.path("convert", "concept.png").is_file() and run.path("convert", "concept_notext.png").is_file()
    assert len(run.path("codex_calls.jsonl").read_text(encoding="utf-8").splitlines()) == 2          # run 전체 상한 장부에도 센다
    prompt = run.path("convert", "call_concept", "prompt.txt").read_text(encoding="utf-8")
    assert '"돌진 공격"' in prompt and "genuinely transparent background" in prompt and "in-game screenshot" in prompt
    assert rec["concept"]["checks"]["aspect_diff"] == 0.0 and rec["concept"]["checks"]["transparent_ratio"] == 0.25
    assert run.read_json("convert/convert.json")["used"]
    # 같은 원본 · 같은 프롬프트로 다시 — codex 를 부르지 않는다(가짜 codex 를 막아도 통과)
    run2 = _run(env, "R20261117_150100_ProbeControlGuide")
    rec2 = concept_convert.convert(run2, src, INPUTS, "auto", "scene", cli=["no-such-codex"])
    assert rec2["used"] and rec2["codex_calls"] == 0 and rec2["concept"]["cached"] and rec2["notext"]["cached"]
    assert rec2["cache_dir"] == rec["cache_dir"] and not run2.path("codex_calls.jsonl").is_file()
    # 프롬프트(화면 설명)가 바뀌면 다른 캐시 — 다시 받는다
    rec3 = concept_convert.convert(_run(env, "R20261117_150200_ProbeControlGuide"), src, {**INPUTS, "text": "다른 설명"}, "auto", "scene", cli=FAKE)
    assert rec3["codex_calls"] == 2 and rec3["cache_dir"] != rec["cache_dir"]


def test_flat_concept_gets_only_an_element_free_plate_once(env, monkeypatch):
    """1b 후속 J-a — ⓑ 단색 컨셉은 변환하지 않고 요소 없는 판만 codex 1 회(검정 배경 유지 프롬프트) — 두 번째는 캐시."""
    src = env / "flat.png"
    arr = np.zeros((80, 160, 3), np.uint8)
    arr[20:60, 30:130] = (200, 150, 60)
    Image.fromarray(arr).save(src)
    run = _run(env, "R20261117_153000_CombatHUD")
    rec = concept_convert.plate_only(run, src, {**INPUTS, "data": [{"id": "g", "type": "progress", "widget": "Dash"}]}, cli=FAKE)
    assert rec["used"] and rec["codex_calls"] == 1 and run.path("convert", "concept_notext.png").is_file() and not rec["plate"]["cached"]
    prompt = run.path("convert", "call_plate", "prompt.txt").read_text(encoding="utf-8")
    assert "solid black background" in prompt and "empty the gauge" in prompt and "transparent background (PNG alpha)" not in prompt
    rec2 = concept_convert.plate_only(_run(env, "R20261117_153100_CombatHUD"), src, {**INPUTS, "data": [{"id": "g", "type": "progress", "widget": "Dash"}]},
                                      cli=["no-such-codex"])
    assert rec2["used"] and rec2["codex_calls"] == 0 and rec2["plate"]["cached"] and rec2["cache_dir"] == rec["cache_dir"]


def test_convert_rejects_a_result_without_transparency_and_keeps_the_rejection(env, monkeypatch):
    src = env / "scene.png"
    _scene(src)
    monkeypatch.setenv("FAKE_CODEX_MODE", "opaque")
    rec = concept_convert.convert(_run(env, "R20261117_151000_ProbeControlGuide"), src, INPUTS, "auto", "scene", cli=FAKE)
    assert not rec["used"] and rec["codex_calls"] == 1 and "transparent ratio 0.0" in rec["fallback"]
    rec2 = concept_convert.convert(_run(env, "R20261117_151100_ProbeControlGuide"), src, INPUTS, "auto", "scene", cli=FAKE)
    assert not rec2["used"] and rec2["codex_calls"] == 0 and rec2["concept"]["cached"]       # 떨어진 결과도 다시 부르지 않는다


def test_convert_quota_falls_back_without_caching(env, monkeypatch):
    src = env / "scene.png"
    _scene(src)
    monkeypatch.setenv("FAKE_CODEX_MODE", "quota")
    rec = concept_convert.convert(_run(env, "R20261117_152000_ProbeControlGuide"), src, INPUTS, "auto", "scene", cli=FAKE)
    assert not rec["used"] and "CODEX_QUOTA" in rec["fallback"] and rec["concept"] is None
    monkeypatch.setenv("FAKE_CODEX_MODE", "ok")
    rec2 = concept_convert.convert(_run(env, "R20261117_152100_ProbeControlGuide"), src, INPUTS, "auto", "scene", cli=FAKE)
    assert rec2["used"] and rec2["codex_calls"] == 2                                            # 한도는 남기지 않는다 — 다음에 다시


def test_convert_respects_the_call_cap(env, monkeypatch):
    src = env / "scene.png"
    _scene(src)
    run = _run(env, "R20261117_153000_ProbeControlGuide")
    run.cfg = {**run.cfg, "concept_convert": {**run.cfg.get("concept_convert", {}), "max_calls": 1}}
    rec = concept_convert.convert(run, src, INPUTS, "auto", "scene", cli=FAKE)
    assert rec["used"] and rec["codex_calls"] == 1 and not rec["notext"]["used"] and "CONVERT_CALL_LIMIT" in rec["notext"]["reason"]


def test_normalize_converts_a_scene_concept_and_falls_back_when_off(env):
    data = yaml.safe_load((pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "m4_combat_hud_concept" / "inputs.yaml").read_text(encoding="utf-8"))
    (env / "in").mkdir()
    _scene(env / "in" / "concept.png", (192, 108))
    data.update(concept="concept.png", concept_convert="auto")
    data.pop("concept_notext", None)
    inputs = env / "in" / "inputs.yaml"
    inputs.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    run = _run(env, "R20261117_154000_CombatHUD")
    # 가짜 codex 그림(8 × 4)은 2:1 — 원본 16:9 와 비율이 달라 버려지고 예전 경로로 물러난다
    detail = normalize.run(run, types.SimpleNamespace(inputs=str(inputs), concept=None, spec_dir=None, codex_cli=FAKE))
    norm = run.read_json("normalize.json")
    assert norm["background"]["kind"] == "scene" and not norm["background"]["convert"]["used"] and "aspect differs" in norm["background"]["convert"]["fallback"]
    assert "conversion fell back" in detail
    # 2:1 원본이면 변환 컨셉으로 ⓐ — reference_alpha · 원본 기록 · 글자 없는 판
    _scene(env / "in" / "concept.png", (160, 80))
    data["resolution"] = [1920, 960]
    inputs.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    run2 = _run(env, "R20261117_154100_CombatHUD")
    detail2 = normalize.run(run2, types.SimpleNamespace(inputs=str(inputs), concept=None, spec_dir=None, codex_cli=FAKE))
    norm2 = run2.read_json("normalize.json")
    assert norm2["background"]["kind"] == "transparent" and norm2["background"]["convert"]["used"] and norm2["original_concept"].endswith("in/concept.png")
    assert run2.path("reference_alpha.png").is_file() and norm2["background"]["notext"]["used"] and "converted from a scene concept" in detail2
    # off 면 변환 기록 없이 예전 경로
    data["concept_convert"] = "off"
    inputs.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    run3 = _run(env, "R20261117_154200_CombatHUD")
    normalize.run(run3, types.SimpleNamespace(inputs=str(inputs), concept=None, spec_dir=None, codex_cli=["no-such-codex"]))
    assert run3.read_json("normalize.json")["background"]["kind"] == "scene" and "convert" not in run3.read_json("normalize.json")["background"]
