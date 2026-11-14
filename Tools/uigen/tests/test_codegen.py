"""codegen (1a-3) — 템플릿 출력 · 계약 해시 · 소유 규칙 · 빌드 실패 원복. 에디터 · UBT 는 FakeToolchain."""
from __future__ import annotations

import json
import pathlib
import subprocess
import types

import pytest
from conftest import FakeToolchain, fixture_brief, fixture_spec, widget

from core import config, cppgen, schema
from core import ue
from core.run import Run
from stages import StageError, codegen

CLASS = "/Script/AstralBreak.AstralCombatHUDWidget"
_n = {"i": 0}


def make_run(tmp_path, spec=None, brief=None) -> Run:
    _n["i"] += 1
    run = Run(f"R20261114_12{_n['i'] % 10000:04d}_CombatHUD", tmp_path / "work", config.load_pipeline(), tmp_path / "metrics.jsonl")
    run.create()
    run.write_json("brief.json", brief or fixture_brief())
    run.write_json("spec.json", spec or fixture_spec())
    return run


def opts(module_root):
    return types.SimpleNamespace(module_root=str(module_root))


def paths(module_root):
    return cppgen.target_paths(module_root, "UI", config.load_screens()["CombatHUD"])


def contract_of(spec):
    bindings, _ = cppgen.merge(cppgen.binding_entries(spec), None)
    doc = cppgen.contract_doc("CombatHUD", config.load_screens()["CombatHUD"], config.load_pipeline()["codegen"], bindings)
    return doc, cppgen.contract_hash(doc)


@pytest.fixture
def mod(tmp_path):
    root = tmp_path / "Source" / "AstralBreak"
    root.mkdir(parents=True)
    (root / "AstralBreak.h").write_text("#pragma once\n", encoding="utf-8")
    return root


def first_run(tmp_path, mod, spec=None):
    tc = FakeToolchain(mod)
    run = make_run(tmp_path, spec)
    codegen.run(run, opts(mod), toolchain=tc)
    return run, tc


# ---------------------------------------------------------------------------------------------------------------------
# 템플릿 · 계약

def test_render_fixture_setters_and_bindings():
    doc, chash = contract_of(fixture_spec())
    texts = cppgen.render(doc, chash)
    h, cpp = texts["view_base_h"], texts["view_base_cpp"]
    assert h.splitlines()[0].startswith(cppgen.MARKER) and cpp.splitlines()[0].startswith(cppgen.MARKER)
    assert h.splitlines()[1] == cppgen.HASH_PREFIX + chash
    assert "UCLASS(Abstract)\nclass ASTRALBREAK_API UAstralCombatHUDViewBase : public UUserWidget" in h
    assert h.count("UPROPERTY(meta = (BindWidget))") == 8 and "meta = (BindWidgetOptional)" not in h
    for decl in ("void SetUltGauge(float Percent);", "void SetUltReadyVisible(bool bVisible);", "void SetChainPanelVisible(bool bVisible);",
                 "void SetChainRemaining(float Value);", "void SetChainCount(const FText& InText);", "void SetBurstBannerVisible(bool bVisible);",
                 "void SetBurstCount(int32 Value);", "void SetUltBlockedVisible(bool bVisible);"):
        assert decl in h, decl
    for prop in ("TObjectPtr<UProgressBar> UltGauge;", "TObjectPtr<UImage> UltReadyGlow;", "TObjectPtr<UBorder> ChainPanel;",
                 "TObjectPtr<UTextBlock> ChainTimerText;", "TObjectPtr<UBorder> BurstBanner;", "TObjectPtr<UTextBlock> UltBlockedText;"):
        assert prop in h, prop
    assert "SetMinimumFractionalDigits(1).SetMaximumFractionalDigits(1)" in cpp          # chain_remaining "0.0"
    assert "Options.SetUseGrouping(false);\n\t\tBurstCountText->SetText" in cpp           # burst_count "0" → int32
    assert "UltGauge->SetPercent(FMath::Clamp(Percent, 0.0f, 1.0f));" in cpp
    assert "ESlateVisibility::SelfHitTestInvisible : ESlateVisibility::Collapsed" in cpp
    for inc in ("Components/Border.h", "Components/Image.h", "Components/ProgressBar.h", "Components/TextBlock.h"):
        assert f'#include "{inc}"' in cpp
    assert "namespace" not in cpp and "Texture2D" not in cpp                             # 익명 네임스페이스 금지 · image 바인딩 없음
    assert '#include "UI/HUD/AutoGen/AstralCombatHUDViewBase.h"' in texts["widget_h"]
    assert "class ASTRALBREAK_API UAstralCombatHUDWidget : public UAstralCombatHUDViewBase" in texts["widget_h"]
    assert "UCLASS()\n" in texts["widget_h"]                                              # 스텁은 Abstract 아님(WBP 부모)
    assert cppgen.render(doc, chash) == texts                                            # 결정적


def test_contract_line_round_trips_and_validates():
    doc, chash = contract_of(fixture_spec())
    line = next(ln for ln in cppgen.render(doc, chash)["view_base_h"].splitlines() if ln.startswith(cppgen.CONTRACT_PREFIX))
    back = json.loads(line[len(cppgen.CONTRACT_PREFIX):])
    assert back == doc and cppgen.contract_hash(back) == chash
    assert schema.errors("codegen", {"schema_version": 1, "run_id": "R", "screen": "CombatHUD", "class": CLASS, "contract_hash": chash,
                                     "contract": doc, "changes": {"added": [], "demoted": [], "changed": [], "restored": []},
                                     "skipped": True, "reason": "contract_unchanged", "files": [], "editor": {}, "build": {"ran": False}}) == []


def test_hash_ignores_widget_order_but_follows_bindings():
    _, h0 = contract_of(fixture_spec())
    s = fixture_spec()
    s["widgets"] = [s["widgets"][0]] + list(reversed(s["widgets"][1:]))
    assert contract_of(s)[1] == h0
    s = fixture_spec()
    widget(s, "UltGauge")["slot"]["padding"] = [1, 1, 1, 1]                               # 배치만 바뀜 → 계약 그대로
    assert contract_of(s)[1] == h0
    s = fixture_spec()
    widget(s, "BurstCountText")["binding"]["format"] = "0.0"
    assert contract_of(s)[1] != h0


def test_number_format_and_image_setters():
    e_int = {"name": "N", "widget_class": "TextBlock", "data": "n", "kind": "number", "format": "0", "optional": False}
    e_f2 = {**e_int, "name": "F", "data": "f", "format": "0.00"}
    img = {"name": "Icon", "widget_class": "Image", "data": "hero_icon", "kind": "image", "optional": False}
    bindings, _ = cppgen.merge([e_f2, img, e_int], None)
    doc = cppgen.contract_doc("CombatHUD", config.load_screens()["CombatHUD"], config.load_pipeline()["codegen"], bindings)
    texts = cppgen.render(doc, cppgen.contract_hash(doc))
    assert "void SetN(int32 Value);" in texts["view_base_h"] and "void SetF(float Value);" in texts["view_base_h"]
    assert "SetMinimumFractionalDigits(2).SetMaximumFractionalDigits(2)" in texts["view_base_cpp"]
    assert "void SetHeroIcon(UTexture2D* Texture);" in texts["view_base_h"] and "class UTexture2D;" in texts["view_base_h"]
    assert '#include "Engine/Texture2D.h"' in texts["view_base_cpp"] and "Icon->SetBrushFromTexture(Texture, false);" in texts["view_base_cpp"]


def test_merge_rules():
    new = cppgen.binding_entries(fixture_spec())
    prev, _ = cppgen.merge(new, None)
    # 빠짐 → optional, setter 유지
    out, ch = cppgen.merge([e for e in new if e["name"] != "UltBlockedText"], prev)
    ub = next(e for e in out if e["name"] == "UltBlockedText")
    assert ub["optional"] is True and ub["setter"] == "SetUltBlockedVisible" and ch["demoted"] == ["UltBlockedText"]
    # 다시 들어옴 → restored
    out2, ch2 = cppgen.merge(new, out)
    assert ch2["restored"] == ["UltBlockedText"] and all(not e["optional"] for e in out2)
    # 클래스 바뀜 → 거부
    retyped = [dict(e, widget_class="Border") if e["name"] == "UltReadyGlow" else e for e in new]
    with pytest.raises(cppgen.ContractError) as ei:
        cppgen.merge(retyped, prev)
    assert ei.value.code == "BINDING_RETYPE"
    # kind 바뀜(같은 클래스) → changed, setter 바뀜
    rekind = [dict(e, kind="text", format=None) if e["name"] == "BurstCountText" else e for e in new]
    rekind = [{k: v for k, v in e.items() if v is not None} for e in rekind]
    out3, ch3 = cppgen.merge(rekind, prev)
    assert ch3["changed"] == ["BurstCountText"] and next(e for e in out3 if e["name"] == "BurstCountText")["setter"] == "SetBurstCount"
    # 위젯 이름만 바꿈(같은 data) → 옛 이름은 optional · setter 없음, 새 이름이 SetUltGauge
    renamed = [dict(e, name="UltMeter") if e["name"] == "UltGauge" else e for e in new]
    out4, _ = cppgen.merge(renamed, prev)
    old, nu = (next(e for e in out4 if e["name"] == n) for n in ("UltGauge", "UltMeter"))
    assert old["optional"] and old["setter"] is None and nu["setter"] == "SetUltGauge"
    # setter 이름 충돌
    clash = new + [{"name": "Extra", "widget_class": "TextBlock", "data": "ult_ready_visible", "kind": "text", "optional": False}]
    with pytest.raises(cppgen.ContractError) as ei:
        cppgen.merge(clash, None)
    assert ei.value.code == "SETTER_COLLISION"


# ---------------------------------------------------------------------------------------------------------------------
# 단계 — 생성 · 빌드 · 재기동 · 건너뜀

def test_first_run_writes_builds_restarts(tmp_path, mod):
    run, tc = first_run(tmp_path, mod)
    p = paths(mod)
    assert all(p[k].is_file() for k in p)
    raw = p["view_base_h"].read_bytes()
    assert b"\r\n" in raw and not raw.startswith(b"\xef\xbb\xbf")                       # CRLF · BOM 없음
    assert tc.calls == ["status", "quit", "wait_exit", "processes", "build", "launch", "wait_bridge", "list"]
    rec = json.loads(run.path("codegen.json").read_text(encoding="utf-8"))
    schema.require("codegen", rec)
    assert rec["skipped"] is False and rec["reason"] == "new" and rec["previous_hash"] is None
    assert {f["role"]: f["action"] for f in rec["files"]} == {"view_base_h": "created", "view_base_cpp": "created",
                                                              "widget_h": "created", "widget_cpp": "created"}
    assert rec["build"]["ran"] and rec["build"]["ok"] and rec["build"]["result_line"] == "Result: Succeeded"
    assert rec["verify"]["match"] is True and len(rec["verify"]["bindings"]) == 8
    assert rec["editor"]["was_running"] is True and rec["editor"]["launched_pid"] == 5151
    assert sorted(rec["changes"]["added"]) == sorted(fixture_brief()["binding_contract"]["bindings"])
    assert cppgen.read_generated(p["view_base_h"])["hash"] == rec["contract_hash"]


def test_same_spec_skips_build_and_restart(tmp_path, mod):
    _, tc = first_run(tmp_path, mod)
    before = {k: v.read_bytes() for k, v in paths(mod).items()}
    run2 = make_run(tmp_path)
    tc.calls.clear()
    assert codegen.run(run2, opts(mod), toolchain=tc).startswith("skipped")
    assert tc.calls == ["status", "list"]                                                 # 떠 있는 에디터의 리플렉션만 확인
    rec = json.loads(run2.path("codegen.json").read_text(encoding="utf-8"))
    assert rec["skipped"] is True and rec["reason"] == "contract_unchanged" and rec["build"] == {"ran": False}
    assert rec["verify"]["match"] is True
    assert {k: v.read_bytes() for k, v in paths(mod).items()} == before
    # 에디터가 없으면 리플렉션도 건너뛴다
    tc.running = False
    tc.calls.clear()
    run3 = make_run(tmp_path)
    assert "editor not running" in codegen.run(run3, opts(mod), toolchain=tc)
    assert tc.calls == ["status"]


def test_stale_binary_rebuilds_without_rewriting(tmp_path, mod):
    _, tc = first_run(tmp_path, mod)
    tc.binary = []                                                                        # 소스는 그대로인데 에디터 바이너리가 낡음
    tc.calls.clear()
    run2 = make_run(tmp_path)
    codegen.run(run2, opts(mod), toolchain=tc)
    rec = json.loads(run2.path("codegen.json").read_text(encoding="utf-8"))
    assert rec["skipped"] is False and rec["reason"] == "stale_binary" and rec["stale_diff"]
    assert "build" in tc.calls and rec["verify"]["match"] is True
    assert {f["role"]: f["action"] for f in rec["files"]}["view_base_h"] == "unchanged"


# ---------------------------------------------------------------------------------------------------------------------
# 소유 규칙

def test_unmarked_autogen_file_refused(tmp_path, mod):
    p = paths(mod)
    p["view_base_h"].parent.mkdir(parents=True)
    p["view_base_h"].write_text("// 사람이 표식을 지운 파일\n#pragma once\n", encoding="utf-8")
    tc = FakeToolchain(mod)
    with pytest.raises(StageError) as ei:
        codegen.run(make_run(tmp_path), opts(mod), toolchain=tc)
    assert ei.value.code == "CODEGEN_NOT_OWNED"
    assert tc.calls == [] and not p["view_base_cpp"].exists() and not p["widget_h"].exists()
    assert p["view_base_h"].read_text(encoding="utf-8").startswith("// 사람이")


def test_stub_is_kept_when_contract_changes(tmp_path, mod):
    _, tc = first_run(tmp_path, mod)
    p = paths(mod)
    human = p["widget_h"].read_text(encoding="utf-8").replace("GENERATED_BODY()", "GENERATED_BODY()\n\tvoid HumanCode();")
    p["widget_h"].write_text(human, encoding="utf-8")
    s = fixture_spec()
    widget(s, "ChainTitleText")["binding"] = {"data": "chain_title", "kind": "text"}
    b = fixture_brief()
    b["binding_contract"]["bindings"].append("ChainTitleText")
    run2 = make_run(tmp_path, s, b)
    codegen.run(run2, opts(mod), toolchain=tc)
    assert p["widget_h"].read_text(encoding="utf-8") == human
    rec = json.loads(run2.path("codegen.json").read_text(encoding="utf-8"))
    acts = {f["role"]: f["action"] for f in rec["files"]}
    assert acts == {"view_base_h": "overwritten", "view_base_cpp": "overwritten", "widget_h": "kept", "widget_cpp": "kept"}
    assert rec["reason"] == "contract_changed" and rec["changes"]["added"] == ["ChainTitleText"]
    assert "void SetChainTitle(const FText& InText);" in p["view_base_h"].read_text(encoding="utf-8")
    assert (run2.dir / "codegen" / "backup").is_dir()                                     # 덮어쓰기 전 사본


def test_removed_binding_becomes_optional(tmp_path, mod):
    _, tc = first_run(tmp_path, mod)
    s = fixture_spec()
    widget(s, "UltBlockedText").pop("binding")
    b = fixture_brief()
    b["binding_contract"]["bindings"].remove("UltBlockedText")
    run2 = make_run(tmp_path, s, b)
    codegen.run(run2, opts(mod), toolchain=tc)
    h = paths(mod)["view_base_h"].read_text(encoding="utf-8")
    assert "UPROPERTY(meta = (BindWidgetOptional))\n\tTObjectPtr<UTextBlock> UltBlockedText;" in h
    assert "void SetUltBlockedVisible(bool bVisible);" in h                               # 사람 코드가 부르던 setter 는 남는다
    rec = json.loads(run2.path("codegen.json").read_text(encoding="utf-8"))
    assert rec["changes"]["demoted"] == ["UltBlockedText"] and rec["verify"]["match"] is True
    assert next(x for x in rec["verify"]["bindings"] if x["name"] == "UltBlockedText")["optional"] is True
    # 같은 spec 을 다시 → 합친 계약이 그대로라 건너뜀
    run3 = make_run(tmp_path, s, b)
    assert codegen.run(run3, opts(mod), toolchain=tc).startswith("skipped")


def test_retype_refused_without_writes(tmp_path, mod):
    _, tc = first_run(tmp_path, mod)
    before = {k: v.read_bytes() for k, v in paths(mod).items()}
    s = fixture_spec()
    widget(s, "UltReadyGlow")["type"] = "Border"
    widget(s, "UltReadyGlow")["style"] = {"brush": {"draw_as": "image", "asset": "ult_glow"}}
    tc.calls.clear()
    with pytest.raises(StageError) as ei:
        codegen.run(make_run(tmp_path, s), opts(mod), toolchain=tc)
    assert ei.value.code == "BINDING_RETYPE" and tc.calls == []
    assert {k: v.read_bytes() for k, v in paths(mod).items()} == before


def test_build_failure_restores_overwritten_files(tmp_path, mod):
    _, tc = first_run(tmp_path, mod)
    before = {k: v.read_bytes() for k, v in paths(mod).items()}
    s = fixture_spec()
    widget(s, "ChainTitleText")["binding"] = {"data": "chain_title", "kind": "text"}
    b = fixture_brief()
    b["binding_contract"]["bindings"].append("ChainTitleText")
    tc.build_ok = False
    tc.calls.clear()
    run2 = make_run(tmp_path, s, b)
    with pytest.raises(StageError) as ei:
        codegen.run(run2, opts(mod), toolchain=tc)
    assert ei.value.code == "BUILD_FAILED" and "launch" not in tc.calls
    assert {k: v.read_bytes() for k, v in paths(mod).items()} == before                   # 원복
    rec = json.loads(run2.path("codegen.json").read_text(encoding="utf-8"))
    assert {r["restored"] for r in rec["restored"]} == {"from_backup"} and len(rec["restored"]) == 2
    assert all(pathlib.Path(r["failed_copy"]).is_file() for r in rec["restored"])         # 실패한 판은 codegen/failed/ 에
    assert "SetChainTitle" in pathlib.Path(rec["restored"][0]["failed_copy"]).read_text(encoding="utf-8")
    assert rec["error"]["code"] == "BUILD_FAILED" and rec["build"]["ok"] is False


def test_build_failure_on_first_run_removes_new_files(tmp_path, mod):
    tc = FakeToolchain(mod, build_ok=False)
    run = make_run(tmp_path)
    with pytest.raises(StageError):
        codegen.run(run, opts(mod), toolchain=tc)
    assert not (mod / "UI").exists()                                                      # 새로 만든 파일 · 빈 폴더까지 원복
    rec = json.loads(run.path("codegen.json").read_text(encoding="utf-8"))
    assert {r["restored"] for r in rec["restored"]} == {"moved_to_failed"} and len(rec["restored"]) == 4
    assert all(pathlib.Path(r["failed_copy"]).is_file() for r in rec["restored"])


def test_quit_refused_writes_nothing(tmp_path, mod):
    tc = FakeToolchain(mod, quit_error="1 unsaved package(s) are outside discard_only_under")
    run = make_run(tmp_path)
    with pytest.raises(StageError) as ei:
        codegen.run(run, opts(mod), toolchain=tc)
    assert ei.value.code == "QUIT_REFUSED" and not (mod / "UI").exists()
    assert "build" not in tc.calls


def test_header_name_taken_and_corrupt_header(tmp_path, mod):
    other = mod / "Elsewhere" / "AstralCombatHUDWidget.h"
    other.parent.mkdir()
    other.write_text("#pragma once\n", encoding="utf-8")
    with pytest.raises(StageError) as ei:
        codegen.run(make_run(tmp_path), opts(mod), toolchain=FakeToolchain(mod))
    assert ei.value.code == "HEADER_NAME_TAKEN"
    other.rename(other.with_suffix(".txt"))
    first_run(tmp_path, mod)
    h = paths(mod)["view_base_h"]
    h.write_text(h.read_text(encoding="utf-8").replace('"UltGauge"', '"UltGaugeX"', 1), encoding="utf-8")
    with pytest.raises(StageError) as ei:
        codegen.run(make_run(tmp_path), opts(mod), toolchain=FakeToolchain(mod))
    assert ei.value.code == "CODEGEN_HEADER_CORRUPT"


def test_screen_config_rules():
    assert cppgen.validate_screen("X", {"feature": "HUD", "view_base": "XBase", "widget": "XWidget"})
    assert cppgen.validate_screen("X", {"feature": "../HUD", "view_base": "XViewBase", "widget": "XWidget"})
    assert not cppgen.validate_screen("CombatHUD", config.load_screens()["CombatHUD"])


# ---------------------------------------------------------------------------------------------------------------------
# 도구 사슬 — 빌드 로그 · tasklist 해석 (프로세스는 가짜)

def test_toolchain_build_reads_result_line(tmp_path, monkeypatch):
    cfg = config.load_pipeline()

    def fake_run(cmd, stdout=None, **kw):
        stdout.write(b"Building AstralBreakEditor...\r\nfoo.cpp(3): error C2065: 'x': undeclared identifier\r\nResult: Failed (OtherCompilationError)\r\n")
        return subprocess.CompletedProcess(cmd, 6)

    monkeypatch.setattr(ue.subprocess, "run", fake_run)
    out = ue.Toolchain(cfg, log=lambda m: None).build(tmp_path / "b.log")
    assert out["ok"] is False and out["result_line"] == "Result: Failed (OtherCompilationError)" and out["errors"]
    assert out["command"][1:4] == ["AstralBreakEditor", "Win64", "DebugGame"] and "-NoHotReload" in out["command"]

    def ok_run(cmd, stdout=None, **kw):
        stdout.write(b"Result: Succeeded\r\nTotal execution time: 12.3 seconds\r\n")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(ue.subprocess, "run", ok_run)
    assert ue.Toolchain(cfg, log=lambda m: None).build(tmp_path / "c.log")["ok"] is True


def test_toolchain_editor_processes_parses_tasklist(monkeypatch):
    out = '"UnrealEditor-Win64-DebugGame.exe","31337","Console","1","2,345,678 K"\r\n'
    monkeypatch.setattr(ue.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=out))
    assert ue.Toolchain(config.load_pipeline()).editor_processes() == [{"image": "UnrealEditor-Win64-DebugGame.exe", "pid": 31337}]
    none = "INFO: No tasks are running which match the specified criteria.\r\n"
    monkeypatch.setattr(ue.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=none))
    assert ue.Toolchain(config.load_pipeline()).editor_processes() == []
