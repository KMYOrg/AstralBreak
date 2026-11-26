"""Phase 2(11-24) — 실행 기록 집계(summarize.py): 합성 기록으로 세는 값 · 같은 기록이면 같은 글 · 경로 · 계정 · LLM 글이 들어가지 않음."""
from __future__ import annotations

import json
import re

import summarize


def _line(**k):
    return json.dumps({"ts": "2026-11-18T10:00:00+09:00", **k}, ensure_ascii=False)


def _run_dir(work, rid, status, attempts, rounds, verify_s, batch=None, errors=0):
    rd = work / rid
    (rd / "attempts" / "001").mkdir(parents=True)
    rep = {"run_id": rid, "status": status, "durations_s": {"analyze": 40.0, "verify": verify_s}, "gates": [{"name": "compile", "pass": True}, {"name": "appearance", "pass": errors == 0}],
           "attempts": [{"attempt": k + 1, "duration_s": verify_s / attempts} for k in range(attempts)],
           "recorded": {"concept_route": {"route": "L-2"}, "diagnosis": {"summary": {"errors": errors, "approx": 2}},
                        "style_review": {"rounds_allowed": len(rounds), "rounds": rounds}}, "message": "C:/Users/someone/secret — LLM wrote this"}
    (rd / "report.json").write_text(json.dumps(rep), encoding="utf-8")
    (rd / "llm.jsonl").write_text("\n".join([_line(stage="analyze", cost_usd=0.25, duration_s=40.0, note="D:/private/path"),
                                             _line(stage="style_verifier", cost_usd=0.2, duration_s=10.0)]) + "\n", encoding="utf-8")
    (rd / "attempts" / "001" / "gates.json").write_text(json.dumps({"notes": {"state_renders": batch} if batch else {}}), encoding="utf-8")


def _data(tmp_path):
    m = tmp_path / "uigen.jsonl"
    m.write_text("\n".join([
        _line(record="run", run_id="R20261114_100000_CombatHUD", ok=False, verify="incomplete", duration_s=1.0),                               # 초기 줄 — status 없음
        _line(record="run", run_id="R20261118_100000_CombatHUD", status="pass", ok=True, verify="pass", duration_s=600.0, failed_gates=[]),
        _line(record="run", run_id="R20261118_110000_ProbePartyHUD", status="fail", ok=False, verify="fail", duration_s=1200.0, failed_gates=["appearance"]),
        _line(record="run", run_id="R20261124_130129_StatusHUD", status="pass", ok=True, verify="pass", duration_s=840.0, failed_gates=[]),
        _line(record="asset", run_id="R20261114_100000_CombatHUD", asset_id="a", backend="codex", kind="frame", ok=True),
        _line(record="asset", run_id="R20261124_130129_StatusHUD", asset_id="b", backend="concept_cut", kind="ornament", ok=True),
        _line(record="asset", run_id="R20261124_130129_StatusHUD", asset_id="c", backend="concept_plate", kind="ornament", ok=True)]) + "\n", encoding="utf-8")
    work = tmp_path / "work"
    _run_dir(work, "R20261118_110000_ProbePartyHUD", "fail", 4, [{"action": "accepted", "cost_usd": 0.3}], 800.0, errors=3)
    _run_dir(work, "R20261124_130129_StatusHUD", "pass", 3, [{"action": "no_ops", "cost_usd": 0.17}], 600.0, batch={"batch": 60, "single": 0})
    return m, work


def test_summary_counts_what_is_there(tmp_path):
    m, work = _data(tmp_path)
    text = summarize.build(summarize.load(m, work))
    assert "run 4개 전부지만" in text and "**2개만 남았다**" in text and "초기 1줄에는" in text
    assert "| 2026-11-18 | 1 · 0 · 0 | 0 · 1 · 0 | 2 |" in text                         # 게임 화면 이름 · 검증 화면을 따로
    assert "`appearance` 1" in text
    assert "| 2026-11-14 | 1 | — | — | 1 |" in text and "2026-11-14 이 마지막이다" in text  # codex 열이 먼저(같은 수면 나온 순서)
    assert "| `analyze` | 컨셉 → 배치 spec | 2 | 2 | 0.50 | 40.0 |" in text
    assert "| 11-18 부터 | 2 | 1 | 0 | 1 | 0 | 0.47 |" in text and "ProbePartyHUD(검증 화면) fail" in text
    row = next(x for x in text.splitlines() if x.startswith("| `R20261124_130129_StatusHUD` | L-2"))
    assert "| pass | 2/2 | 0 | 2 | 3 | 640 | 600(3번) | 200.0 | 묶음 | 1 |" in row
    assert not [x for x in text.split("## 6.")[1].split("## 7.")[0].splitlines() if "Probe" in x]   # 게임 화면 표에는 검증 화면이 없다
    assert "지금 승격본 | pass | 0 | 2 | 640 | 0.45 | concept_cut 1 · concept_plate 1 |" in text
    assert "기록 없음" in text                                                          # 폴더가 없는 승격 run 도 조용히 빠지지 않는다
    assert "통과율" not in re.sub(r"통과율(이 아니다|을 내지 않는다)", "", text)


def test_summary_is_deterministic_and_leaks_nothing(tmp_path, capsys):
    m, work = _data(tmp_path)
    a, b = (summarize.build(summarize.load(m, work)) for _ in range(2))
    assert a == b
    for bad in (r"[A-Za-z]:[/\\]", r"Users", r"@", r"secret", r"LLM wrote", str(tmp_path.name), r"sk-", r"token"):
        assert not re.search(bad, a, re.IGNORECASE), bad
    out = tmp_path / "r.md"
    assert summarize.main(["--out", str(out), "--metrics", str(m), "--work-root", str(work)]) == 0
    assert out.read_text(encoding="utf-8") == a and str(tmp_path) not in out.read_text(encoding="utf-8")
    assert summarize.main(["--out", "-", "--metrics", str(m), "--work-root", str(work)]) == 0
    assert capsys.readouterr().out.strip().endswith(a.strip())


def test_edit_runs_are_counted_apart(tmp_path):
    """Phase 4 — 이어서 고치기 run 은 표에 안 들어간다(막히는지 본 시험이 섞인다). 없으면 글이 그대로다."""
    m, work = _data(tmp_path)
    before = summarize.build(summarize.load(m, work))
    with open(m, "a", encoding="utf-8") as f:
        f.write(_line(record="run", run_id="R20261124_220000_StatusHUD", status="pass", ok=True, verify="pass", duration_s=60.0, failed_gates=[], edit_of="R20261124_130129_StatusHUD") + "\n")
        f.write(_line(record="run", run_id="R20261124_220100_StatusHUD", status="fail", ok=False, verify="fail", duration_s=50.0, failed_gates=["edit_regression"],
                      edit_of="StatusHUD") + "\n")
    _run_dir(work, "R20261124_220000_StatusHUD", "pass", 2, [], 60.0)
    p = work / "R20261124_220000_StatusHUD" / "report.json"
    p.write_text(json.dumps({**json.loads(p.read_text(encoding="utf-8")), "parent_run_id": "R20261124_130129_StatusHUD"}), encoding="utf-8")
    after = summarize.build(summarize.load(m, work))
    assert "이어서 고치기" not in before
    line = [x for x in after.splitlines() if "이어서 고치기 run 2개(통과 1 · 실패 1 · 그 밖 0)" in x]
    assert len(line) == 1 and [x for x in after.splitlines() if x not in line] == before.splitlines()


def test_summary_of_nothing_still_writes(tmp_path):
    text = summarize.build(summarize.load(tmp_path / "none.jsonl", tmp_path / "work"))
    assert text.startswith("# UI 자동 생성 파이프라인") and "run 0개 전부지만" in text
