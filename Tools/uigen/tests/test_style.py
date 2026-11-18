"""1b 후속 C — 게이트 통과 뒤 외형 검토 라운드: 가드(허용 경로 · 폰트 · 에셋 교체 상한) · 영역 · 글자 비교(region_report) ·
style_verifier → style_fix(가짜 claude) · 오케스트레이터의 받기 / 버리기(마지막 통과 spec 으로 run 패키지 전부 버리고 다시 build)."""
from __future__ import annotations

import copy
import json

import numpy as np
from conftest import fixture_brief, fixture_spec, widget
from PIL import Image, ImageDraw
from test_fix_llm import fake_llm  # noqa: F401 — pytest fixture
from test_pipeline_retry import fake_ue  # noqa: F401 — pytest fixture
from test_run import RUN_ID, _args

import run_pipeline
from core import config, png
from core.run import Run
from gen import fidelity
from stages import normalize, style

CFG = config.load_pipeline()
TITLE = CFG["fonts"]["roles"]["title"]["family"]


def _cfg(**sr):
    cfg = copy.deepcopy(CFG)
    cfg["style_review"].update(sr)
    return cfg


def test_guard_allows_only_appearance_ops():
    spec, brief = fixture_spec(), fixture_brief()
    ok = [{"op": "set", "widget": "UltGauge", "path": "style.fill.color", "value": "#F2B544"},
          {"op": "set", "widget": "UltGauge", "path": "slot.padding", "value": [12, 8, 12, 8]},
          {"op": "set", "widget": "ChainPanel", "path": "style.brush.color", "value": "#FFFFFFEE"}]
    assert style.guard_style_ops(ok, spec, brief, _cfg(), 5) == []
    bad = [{"op": "set", "widget": "ChainPanel", "path": "slot.position", "value": [0, 0]},
           {"op": "set", "widget": "UltGauge", "path": "bbox_intent", "value": [0, 0, 1, 1]},
           {"op": "move", "widget": "ChainTitleText", "parent": "Root"}]
    errs = style.guard_style_ops(bad, spec, brief, _cfg(), 5)
    assert any("slot.position" in e for e in errs) and any("bbox_intent" in e for e in errs)
    assert any("'move'" in e for e in errs)


def test_guard_rejects_every_text_op():
    """1b 후속 J-c — 글자 스타일(크기 · 굵기 · 외곽선 · 빛 · 색 · 자리)은 결정적 측정만 — 외형 라운드의 글자 위젯 op 는 모두 거절."""
    spec, brief = fixture_spec(), fixture_brief()
    text_ops = [{"op": "set", "widget": "ChainTitleText", "path": "font.color", "value": "#E7AE4F"},
                {"op": "set", "widget": "ChainTitleText", "path": "font.outline", "value": {"size": 2, "color": "#2A1405"}},
                {"op": "set", "widget": "ChainTitleText", "path": "font.family", "value": TITLE},
                {"op": "set", "widget": "ChainTimerText", "path": "font.size", "value": 30},
                {"op": "set", "widget": "ChainTimerText", "path": "slot.padding", "value": [0, 4, 0, 0]}]
    errs = style.guard_style_ops(text_ops, spec, brief, _cfg(), 5)
    assert len(errs) == len(text_ops) and all("text widgets" in e for e in errs)


def test_fit_color_from_core_strokes():
    """1b 후속 J-c — 글자색은 핵심 획 대표색으로: 렌더가 남색이면 컨셉 흰색으로, 컨셉이 위 · 아래로 다르면 그라데이션, 같으면 그대로."""
    ref = np.zeros((40, 60, 3))
    ren = np.zeros((40, 60, 3))
    m = np.zeros((40, 60), bool)
    m[10:30, 10:50] = True
    ref[m] = (245, 245, 235)
    ren[m] = (20, 40, 110)
    f = {"color": "#142C6EFF"}
    rec = style._fit_color(f, ref, ren, m, m)
    assert rec and f["color"] == "#F5F5EBFF" and "gradient" not in f and rec["core_de_before"] > 30
    ref[10:20, 10:50], ref[20:30, 10:50] = (250, 230, 160), (200, 130, 40)        # 금색 세로 그라데이션
    f2 = {"color": "#FFFFFFFF"}
    style._fit_color(f2, ref, ren, m, m)
    assert f2["gradient"] == {"top_color": "#FAE6A0FF", "bottom_color": "#C88228FF"} and f2["color"] == "#FFFFFFFF"
    assert style._fit_color({"color": "#FFFFFFFF"}, ren, ren, m, m) is None                  # 같으면 그대로


def test_guard_limits_asset_redos():
    spec = fixture_spec()
    spec["assets"].append({"asset_id": "chain_panel_frame", "kind": "frame", "provenance": "codex", "size": [64, 64], "prompt": "p"})
    two = [{"op": "replace_asset", "asset": "chain_panel_frame", "regenerate": True, "prompt": "keep the corners"}] * 2
    assert any("at most 1" in e for e in style.guard_style_ops(two, spec, fixture_brief(), _cfg(), 5))
    one = two[:1]
    assert style.guard_style_ops(one, spec, fixture_brief(), _cfg(), 5) == []
    assert any("at most 0" in e for e in style.guard_style_ops(one, spec, fixture_brief(), _cfg(), 0))      # codex 를 다 썼다
    proc = [{"op": "replace_asset", "asset": spec["assets"][0]["asset_id"], "regenerate": True}]
    assert any("only codex assets" in e for e in style.guard_style_ops(proc, spec, fixture_brief(), _cfg(), 5))


def _images(tmp_path, render_text=(230, 175, 80)):
    """영역 ChainPanel 에 금테 · 글자 획(제목) — 렌더는 글자색만 다르게."""
    spec = fixture_spec()
    panel, title = widget(spec, "ChainPanel")["bbox_intent"], widget(spec, "ChainTitleText")["bbox_intent"]
    out = []
    for name, tc in (("reference.png", (230, 175, 80)), ("render.png", render_text)):
        im = Image.new("RGB", (1920, 1080), (20, 14, 24))
        d = ImageDraw.Draw(im)
        x, y, w, h = panel
        d.rectangle([x + 2, y + 2, x + w - 3, y + h - 3], outline=(225, 180, 70), width=3)
        tx, ty, tw, th = title
        for k in range(4):
            d.rectangle([tx + 60 + k * 30, ty + 5, tx + 70 + k * 30, ty + th - 6], fill=tc)
        im.save(tmp_path / name)
        out.append(tmp_path / name)
    return spec, out


def test_region_report_compares_regions_and_text(tmp_path):
    spec, (ref, ren) = _images(tmp_path, render_text=(230, 175, 80))
    rep = fidelity.region_report(ref, ren, spec, tmp_path / "cmp")
    t = rep["texts"]["ChainTitleText"]
    assert t["ink_de00"] < 1 and abs(t["h_ratio"] - 1) < 0.05 and t["region"] == "ChainPanel"
    r = rep["regions"]["ChainPanel"]
    assert r["line_f1"]["f1"] > 0.9 and (tmp_path / "cmp" / r["sheet"]).is_file() and "ChainTitleText" in r["texts"]
    assert rep["summary"]["texts"] >= 1 and rep["summary"]["region_line_f1"] is not None
    spec, (ref, ren) = _images(tmp_path, render_text=(240, 240, 240))
    rep2 = fidelity.region_report(ref, ren, spec, tmp_path / "cmp2")
    assert rep2["texts"]["ChainTitleText"]["ink_de00"] > 15                                  # 금색 ↔ 흰색
    assert "error" in fidelity.region_report(ref, tmp_path / "small.png" if png.write_rgba(tmp_path / "small.png", 2, 2, bytes(16)) else ren, spec, tmp_path / "c3")


FINDING = {"fixes": [{"widget": "UltGauge", "gate": "style", "problem": "fill is pale, the concept is gold", "evidence": "fill ΔE00 18",
                      "suggested_op": {"op": "set", "widget": "UltGauge", "path": "style.fill.color", "value": "#E7AE4F"}}]}
GOLD = {"op": "set", "widget": "UltGauge", "path": "style.fill.color", "value": "#E7AE4F", "reason": "concept fill colour"}
SHRINK = {"op": "set", "widget": "ChainTimerText", "path": "font.size", "value": 15, "reason": "too big"}
# 게이트를 깨는 라운드는 막대를 미는 op 로 흉내 낸다(1b 후속 J-c — 글자 위젯 op 는 가드가 거절)
PUSH = {"op": "set", "widget": "UltGauge", "path": "slot.padding", "value": [12, 40, 12, 0], "reason": "pushes the bar down"}


def _style_run(tmp_path):
    cfg = copy.deepcopy(CFG)
    cfg["fix"]["mode"] = "hybrid"
    run = Run("R20261115_160000_CombatHUD", tmp_path / "work", cfg, tmp_path / "m.jsonl")
    run.create()
    run.write_json("spec.json", fixture_spec())
    run.write_json("brief.json", fixture_brief())
    return run


def test_propose_rejects_layout_ops_then_accepts_the_retry(tmp_path, fake_llm, monkeypatch):  # noqa: F811
    run = _style_run(tmp_path)
    cheat = {"op": "set", "widget": "ChainPanel", "path": "slot.size", "value": [400, 300], "reason": "bigger"}
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUTS", json.dumps([FINDING, {"ops": [cheat]}, {"ops": [GOLD]}]))
    prop = style.propose(run, 1, {"label": "before", "regions": {}, "texts": {}})
    assert prop["patch"]["ops"] == [GOLD] and prop["branch"] == "build" and prop["patch_file"] == "patches/style_001.json"
    calls = [json.loads(x) for x in fake_llm.read_text(encoding="utf-8").splitlines()]
    files = [c["argv"][c["argv"].index("--append-system-prompt-file") + 1].replace("\\", "/").rsplit("/", 1)[-1] for c in calls]
    assert files == ["style_verifier.md", "style_fix.md", "style_fix.md"] and "slot.position" not in calls[1]["argv"][1]
    assert "previous patch was rejected" in calls[2]["argv"][1]


def test_propose_without_findings_gives_no_patch(tmp_path, fake_llm, monkeypatch):  # noqa: F811
    run = _style_run(tmp_path)
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT", json.dumps({"fixes": []}))
    prop = style.propose(run, 1, {"label": "before"})
    assert prop["patch"] is None and prop["error"] == "no style findings"


def _with_reference(monkeypatch):
    """손 spec 파이프라인에 컨셉(reference.png)을 하나 둔다 — 외형 라운드는 컨셉이 있을 때만 돈다(가짜 렌더는 2×2 라 비교는 오류로 기록)."""
    real = normalize.run

    def run_and_reference(run, opts):
        out = real(run, opts)
        png.write_rgba(run.path("reference.png"), 2, 2, bytes([30, 20, 10, 255] * 4))
        return out
    monkeypatch.setattr(normalize, "run", run_and_reference)


def _report(tmp_path):
    return json.loads((tmp_path / "work" / RUN_ID / "report.json").read_text(encoding="utf-8"))


def test_pipeline_style_round_accepted(tmp_path, fake_ue, fake_llm, monkeypatch):  # noqa: F811
    _with_reference(monkeypatch)
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUTS", json.dumps([FINDING, {"ops": [GOLD]}]))
    assert run_pipeline.main(_args(tmp_path, "--fix-mode", "hybrid")) == run_pipeline.EXIT_PASS
    rep = _report(tmp_path)
    sr = rep["recorded"]["style_review"]
    assert sr["rounds"][0]["action"] == "accepted" and rep["attempt"] == 2 and rep["attempts"][1]["style_round"] == 1
    rd = tmp_path / "work" / RUN_ID
    assert widget(json.loads((rd / "spec.json").read_text(encoding="utf-8")), "UltGauge")["style"]["fill"]["color"] == "#E7AE4F"
    assert rep["finalize"]["action"] == "saved" and sr["before"]["regions"] == 0 and sr["final_label"] == "round_001"   # 가짜 렌더 2×2 — 영역 없음


def test_pipeline_style_round_that_breaks_a_gate_is_reverted(tmp_path, fake_ue, fake_llm, monkeypatch):  # noqa: F811
    _with_reference(monkeypatch)
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUTS", json.dumps([FINDING, {"ops": [PUSH]}]))
    assert run_pipeline.main(_args(tmp_path, "--fix-mode", "hybrid")) == run_pipeline.EXIT_PASS
    rep = _report(tmp_path)
    row = rep["recorded"]["style_review"]["rounds"][0]
    assert row["action"] == "reverted" and "iou_leaf" in row["verify"]["failed"] and row["revert"]["to_attempt"] == 1
    assert [a.get("revert", False) for a in rep["attempts"]] == [False, False, True] and rep["attempts"][-1]["pass"]
    rd = tmp_path / "work" / RUN_ID
    final = json.loads((rd / "spec.json").read_text(encoding="utf-8"))
    assert (widget(final, "UltGauge").get("slot") or {}).get("padding") == (widget(fixture_spec(), "UltGauge").get("slot") or {}).get("padding")
    tools = [t for t, _ in fake_ue.editor.log]
    assert "discard_run_packages" in tools and tools.count("create_widget_blueprint") == 2          # 버리고 처음부터 다시 만들었다
    assert tools[-1] == "save_widget_run" and rep["status"] == "pass" and rep["verify"] == "pass"


def test_pipeline_style_round_text_ops_are_rejected(tmp_path, fake_ue, fake_llm, monkeypatch):  # noqa: F811
    """1b 후속 J-c — LLM 이 글자 크기를 바꾸려 해도(두 번) 가드가 거절해 라운드는 op 없이 끝나고 spec 글자는 그대로."""
    _with_reference(monkeypatch)
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUTS", json.dumps([FINDING, {"ops": [SHRINK]}, {"ops": [SHRINK]}]))
    assert run_pipeline.main(_args(tmp_path, "--fix-mode", "hybrid")) == run_pipeline.EXIT_PASS
    row = _report(tmp_path)["recorded"]["style_review"]["rounds"][0]
    assert row["action"] == "no_ops" and "text widgets" in row["reason"]
    final = json.loads((tmp_path / "work" / RUN_ID / "spec.json").read_text(encoding="utf-8"))
    assert widget(final, "ChainTimerText")["font"].get("size") == widget(fixture_spec(), "ChainTimerText")["font"].get("size")


def test_style_round_off_in_deterministic_mode(tmp_path, fake_ue, monkeypatch):  # noqa: F811
    _with_reference(monkeypatch)
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_PASS                    # conftest 기본 = deterministic
    sr = _report(tmp_path)["recorded"]["style_review"]
    assert sr["rounds_allowed"] == 0 and sr["rounds"] == [] and "before" in sr
    # 1b 후속 G — 글자 맞춤은 deterministic 에서도 돈다(가짜 렌더 2×2 라 재지 못하고 건너뜀 — 시도가 늘지 않는다)
    assert sr["text_fit"]["action"] == "nothing_to_fit" and all("skipped" in t for t in sr["text_fit"]["texts"])
    assert _report(tmp_path)["attempt"] == 1


def _fake_text_fit(monkeypatch, path, value, size_path=None, size_value=None):
    """가짜 렌더(2×2)로는 획을 못 재므로 text_fit 결과를 흉내 낸다 — 위치 판은 ChainTimerText 의 path 를 value 로,
    크기 판은 size_path 가 있을 때만 size_value 로(없으면 바꿀 것 없음)."""
    def fit(spec, ref, ren, cfg, rendered=None, mode="place"):
        out = copy.deepcopy(spec)
        p, v = (path, value) if mode == "place" else (size_path, size_value)
        if p is None:
            return out, [{"widget": "ChainTimerText", "skipped": "nothing"}]
        node = widget(out, "ChainTimerText")
        keys = p.split(".")
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = v
        kind = "size" if mode == "size" else ("shift" if p.startswith("slot") else "letter_spacing")
        return out, [{"widget": "ChainTimerText", kind: v}]
    monkeypatch.setattr(style, "text_fit", fit)


def test_pipeline_text_fit_accepted(tmp_path, fake_ue, monkeypatch):  # noqa: F811
    _with_reference(monkeypatch)
    _fake_text_fit(monkeypatch, "font.letter_spacing", 90)
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_PASS
    rep = _report(tmp_path)
    tf = rep["recorded"]["style_review"]["text_fit"]
    assert tf["action"] == "accepted" and tf["changed"] == ["ChainTimerText"] and rep["attempts"][-1]["style_round"] == "text_fit"
    final = json.loads((tmp_path / "work" / RUN_ID / "spec.json").read_text(encoding="utf-8"))
    assert widget(final, "ChainTimerText")["font"]["letter_spacing"] == 90 and rep["finalize"]["action"] == "saved"


def test_pipeline_text_fit_that_breaks_a_gate_is_reverted(tmp_path, fake_ue, monkeypatch):  # noqa: F811
    _with_reference(monkeypatch)
    _fake_text_fit(monkeypatch, "slot.padding", [0, 60, 0, 0])                                # bbox_intent 는 그대로 — iou_leaf 가 깨진다
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_PASS
    rep = _report(tmp_path)
    tf = rep["recorded"]["style_review"]["text_fit"]
    assert tf["action"] == "reverted" and "iou_leaf" in tf["verify"]["failed"]
    assert [a.get("revert", False) for a in rep["attempts"]] == [False, False, True] and rep["attempts"][-1]["pass"]
    final = json.loads((tmp_path / "work" / RUN_ID / "spec.json").read_text(encoding="utf-8"))
    assert (widget(final, "UltGauge").get("slot") or {}).get("padding") == (widget(fixture_spec(), "UltGauge").get("slot") or {}).get("padding")
    assert rep["status"] == "pass" and [t for t, _ in fake_ue.editor.log][-1] == "save_widget_run"


def test_pipeline_text_fit_size_pass_reverted_then_place_pass_still_runs(tmp_path, fake_ue, monkeypatch):  # noqa: F811
    """크기 판 → 위치 판은 판마다 따로 받고 버린다 — 크기 판이 게이트를 깨도(버림) 위치 판은 최신 통과 렌더에서 돈다."""
    _with_reference(monkeypatch)
    _fake_text_fit(monkeypatch, "font.letter_spacing", 90, size_path="slot.padding", size_value=[0, 60, 0, 0])   # 크기 판이 iou_leaf 를 깬다
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_PASS
    rep = _report(tmp_path)
    sr = rep["recorded"]["style_review"]
    assert sr["text_fit_size"]["action"] == "reverted" and "iou_leaf" in sr["text_fit_size"]["verify"]["failed"]
    assert sr["text_fit"]["action"] == "accepted" and sr["text_fit"]["changed"] == ["ChainTimerText"] and sr["final_label"] == "text_fit"
    assert [(a.get("style_round"), a.get("revert", False)) for a in rep["attempts"][1:]] == [("text_fit_size", False), ("text_fit_size", True), ("text_fit", False)]
    final = json.loads((tmp_path / "work" / RUN_ID / "spec.json").read_text(encoding="utf-8"))
    tt = widget(final, "ChainTimerText")
    assert tt["font"]["letter_spacing"] == 90 and (tt.get("slot") or {}).get("padding") == (widget(fixture_spec(), "ChainTimerText").get("slot") or {}).get("padding")
    assert "residual" in sr["text_fit"] and rep["finalize"]["action"] == "saved"


def test_pipeline_text_fit_size_then_place_both_accepted(tmp_path, fake_ue, monkeypatch):  # noqa: F811
    _with_reference(monkeypatch)
    _fake_text_fit(monkeypatch, "font.letter_spacing", 90, size_path="font.color", size_value="#E7AE4F")   # 게이트와 무관한 바꿈으로 크기 판 흉내
    assert run_pipeline.main(_args(tmp_path)) == run_pipeline.EXIT_PASS
    rep = _report(tmp_path)
    sr = rep["recorded"]["style_review"]
    assert sr["text_fit_size"]["action"] == "accepted" and sr["text_fit"]["action"] == "accepted"
    assert [a.get("style_round") for a in rep["attempts"][1:]] == ["text_fit_size", "text_fit"] and rep["attempt"] == 3
    tt = widget(json.loads((tmp_path / "work" / RUN_ID / "spec.json").read_text(encoding="utf-8")), "ChainTimerText")
    assert tt["font"]["color"] == "#E7AE4F" and tt["font"]["letter_spacing"] == 90
