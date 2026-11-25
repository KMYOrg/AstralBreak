"""실행 기록 집계(Phase 2 — 설계 §11 'Phase 2 설계' ④) — 지표 JSONL 과 남은 run 폴더를 읽어 글 리포트(마크다운) 하나를 쓴다. 읽기만 하고, 같은 기록이면 같은 글이 나온다.

    Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/summarize.py                      # → Docs/Design/ui-autogen-report.md
    Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/summarize.py --out <파일> | --out -   # - = 화면에

읽는 것: metrics/uigen.jsonl(run 한 줄 + 에셋마다 한 줄) · work/R*/report.json · llm.jsonl · attempts/*/gates.json(묶음 렌더 기록).
리포트에는 run id · 화면 이름 · 게이트 이름 · 수만 넣는다 — 경로 · 계정 · 토큰 · LLM 이 쓴 글은 넣지 않는다.
시험 run 과 게임 화면 run 을 섞은 통과율을 내지 않는다: 화면 이름(CombatHUD)만으로 둘을 가를 수 없고(11-23 앞의 CombatHUD run 은 대부분 파이프라인을 만들던 시험),
남은 run 폴더는 정리하고 남은 것이라 표본이 고르지 않다.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from core import config  # noqa: E402
from core import metrics  # noqa: E402

OUT = "Docs/Design/ui-autogen-report.md"
# 게임에 승격한 run — 지표에는 승격 여부가 없어 설계 문서(§11 표 '→ M4 C' · 'L-2 기본 전환 결과' · '전투 HUD 동작 결과' · '메인 HUD 결과' · 'Phase 3-2 결과')에서 옮겼다
PROMOTED = {"R20261119_091634_CombatHUD": "첫 승격(L-1) — 뒤에 바뀜", "R20261123_172628_CombatHUD": "L-2 '검은 날' — 뒤에 바뀜",
            "R20261123_194019_CombatHUD": "고리 · 키 안내 — 지금 승격본", "R20261124_130129_StatusHUD": "내 상태 · 동료 — 지금 승격본",
            "R20261125_160008_ButtonLarge": "공용 큰 버튼 칸 — 지금 승격본", "R20261125_160033_ButtonSmall": "공용 작은 버튼 칸 — 지금 승격본",
            "R20261125_211554_HubMemberRow": "허브 파티 줄 칸 — 지금 승격본"}
ROUND_SPLIT = "20261118"       # 글자 · 픽셀을 결정적으로 맞추게 된 뒤(K · L) — 외형 라운드 표를 앞뒤로 나눈다
GAME_FROM = "20261123"         # 게임에 쓰는 컨셉('검은 날')이 생긴 날 — 이때부터의 CombatHUD · StatusHUD run 만 '게임 화면 run' 표에


def screen_of(run_id: str) -> str:
    return run_id.split("_", 2)[2]


def is_probe(run_id: str) -> bool:
    return screen_of(run_id).startswith("Probe")


def day_of(run_id: str) -> str:
    d = run_id[1:9]
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def outcome(r: dict) -> str:
    """run 한 줄의 결과 — 초기 줄에는 status 가 없다(verify 로)."""
    s = r.get("status") or ("pass" if r.get("ok") else str(r.get("verify")))
    return s if s in ("pass", "fail") else "그 밖"


def _read(p: pathlib.Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _jsonl(p: pathlib.Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.is_file() else []


def load(metrics_path: pathlib.Path, work: pathlib.Path) -> dict:
    rows = metrics.read(metrics_path)
    reports = {}
    for p in sorted(work.glob("R*/report.json")):
        rep = _read(p)
        if rep is None:
            continue
        batch = [((_read(g) or {}).get("notes") or {}).get("state_renders") for g in sorted((p.parent / "attempts").glob("*/gates.json"))]
        reports[p.parent.name] = {"report": rep, "llm": _jsonl(p.parent / "llm.jsonl"), "batch": [b for b in batch if b]}
    # 이어서 고치기 run(Phase 4 — edit_of)은 컨셉에서 만드는 run 이 아니고 일부러 막히는 시험도 섞여 따로 센다
    edits = [r for r in rows if r["record"] == "run" and r.get("edit_of")]
    skip = {r["run_id"] for r in edits} | {k for k, d in reports.items() if d["report"].get("parent_run_id")}
    return {"runs": [r for r in rows if r["record"] == "run" and not r.get("edit_of")], "assets": [r for r in rows if r["record"] == "asset"],
            "reports": {k: d for k, d in reports.items() if k not in skip}, "edits": edits}


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def num(v, digits: int = 0) -> str:
    return "—" if v is None else f"{v:,.{digits}f}"


def table(head: list[str], rows: list[list], align: str) -> list[str]:
    marks = {"l": ":---", "r": "---:"}
    return ["| " + " | ".join(head) + " |", "| " + " | ".join(marks[a] for a in align) + " |"] + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def run_info(rid: str, d: dict) -> dict:
    """남은 run 하나 — 시간 · verify · LLM · 진단."""
    rep = d["report"]
    durs = rep.get("durations_s") or {}
    ver = [a["duration_s"] for a in rep.get("attempts") or [] if a.get("duration_s")]
    rec = rep.get("recorded") or {}
    diag = (rec.get("diagnosis") or {}).get("summary") or {}
    style = rec.get("style_review") or {}
    total = sum(durs.values())
    return {"run": rid, "status": rep.get("status"), "attempts": len(rep.get("attempts") or []), "total": total, "verify": sum(ver), "verifies": len(ver),
            "verify_one": med(ver), "share": sum(ver) / total if total else None, "errors": diag.get("errors"), "approx": diag.get("approx"),
            "gates": rep.get("gates") or [], "route": (rec.get("concept_route") or {}).get("route"), "rounds": style.get("rounds") or [],
            "rounds_allowed": style.get("rounds_allowed"), "llm_calls": len(d["llm"]), "llm_usd": sum(x.get("cost_usd") or 0 for x in d["llm"]),
            "llm_s": sum(x.get("duration_s") or 0 for x in d["llm"]), "batch": len(d["batch"]) > 0 and all((b.get("batch") or 0) > 0 for b in d["batch"])}


def build(data: dict) -> str:
    runs, assets, reports = data["runs"], data["assets"], data["reports"]
    info = {rid: run_info(rid, d) for rid, d in reports.items()}
    out: list[str] = []
    add = out.append
    first, last = (min(r["ts"] for r in runs)[:10], max(r["ts"] for r in runs)[:10]) if runs else ("—", "—")
    add("# UI 자동 생성 파이프라인(uigen) 실행 기록 집계")
    add("")
    add(f"기록 범위 {first} ~ {last} · 만든 것 = `Tools/uigen/summarize.py`(기록을 읽어 세기만 한다 — 같은 기록이면 같은 글) · 설계 = [ui-autogen-pipeline.md](ui-autogen-pipeline.md)")
    add("")
    add("컨셉아트 한 장을 받아 에셋 → C++ 바인딩 → WBP → 렌더 검증까지 사람 개입 없이 도는 파이프라인의 실행 기록이다. LLM 은 배치 분석 · 실패 원인 설명 · 정정안(과 지금은 끈 외형 검토)에만 쓰고, "
        "합격은 규칙 · 수치 게이트가 정한다.")
    add("")
    add("**읽을 때 주의**")
    add("")
    add(f"- 지표 줄은 run {len(runs)}개 전부지만, run 폴더는 정리하고 **{len(reports)}개만 남았다**(실패 · 중간 run 을 많이 지움). 3 ~ 7 절은 남은 것의 값이고 **전체 통과율이 아니다**.")
    n_combat = sum(1 for r in runs if screen_of(r["run_id"]) == "CombatHUD" and r["run_id"][1:9] < GAME_FROM)
    add(f"- `CombatHUD` run 중 {GAME_FROM[:4]}-{GAME_FROM[4:6]}-{GAME_FROM[6:]} 앞의 {n_combat}개는 대부분 파이프라인을 만들던 시험이다(시험 컨셉 · 일부러 깨뜨린 run 포함). 화면 이름만으로 게임 run 과 "
        "가를 수 없어 통과율을 내지 않는다. `Probe…` 는 검증 전용 화면이다.")
    no_status = sum(1 for r in runs if not r.get("status"))
    add(f"- 초기 {no_status}줄에는 run 결과(status)가 없어 '그 밖'으로 셌다. 일부러 결함을 넣은 run 은 {sum(1 for r in runs if r.get('fault'))}개다.")
    if data.get("edits"):
        ec = collections.Counter(outcome(r) for r in data["edits"])
        add(f"- 이어서 고치기 run {len(data['edits'])}개(통과 {ec['pass']} · 실패 {ec['fail']} · 그 밖 {ec['그 밖']})는 아래 표에 넣지 않았다 — 컨셉에서 만드는 run 이 아니고, 막히는지 본 시험이 섞여 있다.")
    add("- 'USD' 는 API 정가로 환산한 값이다 — 구독 계정이라 과금이 아니다. 시간은 한 대의 PC 에서 잰 값이고 다른 작업과 겹쳤을 수 있다.")
    add("")

    # 1
    add("## 1. 날짜 × 화면")
    add("")
    by: dict = collections.defaultdict(lambda: {"game": collections.Counter(), "probe": collections.Counter(), "dur": []})
    for r in runs:
        b = by[day_of(r["run_id"])]
        b["probe" if is_probe(r["run_id"]) else "game"][outcome(r)] += 1
        b["dur"].append(r.get("duration_s"))

    def cell(c):
        return f"{c['pass']} · {c['fail']} · {c['그 밖']}" if c else "—"
    rows = [[d, cell(b["game"]), cell(b["probe"]), sum(b["game"].values()) + sum(b["probe"].values()), num((med(b["dur"]) or 0) / 60, 1),
             num(sum(x or 0 for x in b["dur"]) / 3600, 1)] for d, b in sorted(by.items())]
    tg, tp = collections.Counter(), collections.Counter()
    for b in by.values():
        tg.update(b["game"])
        tp.update(b["probe"])
    rows.append(["**합**", cell(tg), cell(tp), len(runs), num((med([r.get("duration_s") for r in runs]) or 0) / 60, 1), num(sum(r.get("duration_s") or 0 for r in runs) / 3600, 1)])
    out += table(["날짜", "게임 화면 이름(통과 · 실패 · 그 밖)", "검증 화면(통과 · 실패 · 그 밖)", "run", "run 시간 중앙값(분)", "합(시간)"], rows, "lllrrr")
    add("")
    fg = collections.Counter(g for r in runs for g in r.get("failed_gates") or [])
    add("마지막 verify 에서 실패한 게이트(run 수): " + (" · ".join(f"`{k}` {v}" for k, v in fg.most_common()) or "없음"))
    add("")

    # 2
    add("## 2. 에셋 출처")
    add("")
    backs = [b for b, _ in collections.Counter(a["backend"] for a in assets).most_common()]
    ab: dict = collections.defaultdict(collections.Counter)
    for a in assets:
        ab[day_of(a["run_id"])][a["backend"]] += 1
    rows = [[d, *[num(c[b]) if c[b] else "—" for b in backs], sum(c.values())] for d, c in sorted(ab.items())]
    rows.append(["**합**", *[num(sum(c[b] for c in ab.values())) for b in backs], len(assets)])
    out += table(["날짜", *[f"`{b}`" for b in backs], "합"], rows, "l" + "r" * (len(backs) + 1))
    add("")
    cdx = [d for d, c in sorted(ab.items()) if c["codex"]]
    add("`codex` = 이미지 생성 모델이 만든 것, `concept_cut` = 컨셉 픽셀을 그대로 오린 것, `concept_plate` = 정적 장식을 한 장으로 오린 판, `procedural` = 코드로 그린 것. "
        + (f"run 안에서 `codex` 로 만든 에셋은 {cdx[-1]} 이 마지막이다 — 그 뒤로 이미지 생성은 컨셉을 만들 때만 쓴다." if cdx else ""))
    add("")

    # 3
    add(f"## 3. 걸린 시간 — 남은 run {len(info)}개")
    add("")
    tb: dict = collections.defaultdict(list)
    for rid, i in info.items():
        tb[day_of(rid)].append(i)
    rows = []
    for d, xs in sorted(tb.items()):
        rows.append([d, len(xs), num(med([x["total"] for x in xs])), num(med([x["verifies"] for x in xs]), 1), num(med([x["verify_one"] for x in xs]), 1),
                     f"{100 * sum(x['verify'] for x in xs) / max(1e-9, sum(x['total'] for x in xs)):.0f} %", num(med([x["llm_s"] for x in xs]))])
    out += table(["날짜", "run", "run 시간 중앙값(초)", "verify 횟수 중앙값", "verify 1번 중앙값(초)", "verify 비중", "LLM 시간 중앙값(초)"], rows, "lrrrrrr")
    add("")
    add("verify 비중 = 그날 남은 run 의 verify 시간 합 ÷ run 시간 합. 11-18 뒤로 검사(상태 렌더 · 글자 밑 흔적 · 접힌 위젯 빛 · 원형 · 막대)를 차례로 더했고, 11-24 에 상태 렌더를 한 묶음으로 바꿨다(설계 문서 §11).")
    add("")

    # 4
    add(f"## 4. LLM 호출 — 남은 run {len(info)}개")
    add("")
    st: dict = collections.defaultdict(lambda: {"n": 0, "usd": 0.0, "s": 0.0, "runs": set()})
    for rid, d in reports.items():
        for x in d["llm"]:
            s = st[x.get("stage")]
            s["n"] += 1
            s["usd"] += x.get("cost_usd") or 0
            s["s"] += x.get("duration_s") or 0
            s["runs"].add(rid)
    what = {"analyze": "컨셉 → 배치 spec", "verifier": "실패 게이트 설명", "fix": "정정 patch", "style_verifier": "외형 검토(끔)", "style_fix": "외형 patch(끔)"}
    rows = [[f"`{k}`", what.get(k, ""), v["n"], len(v["runs"]), num(v["usd"], 2), num(v["s"] / max(1, v["n"]), 1)] for k, v in sorted(st.items(), key=lambda kv: -kv[1]["usd"])]
    rows.append(["**합**", "", sum(v["n"] for v in st.values()), len([1 for d in reports.values() if d["llm"]]), num(sum(v["usd"] for v in st.values()), 2), ""])
    out += table(["단계", "하는 일", "호출", "run", "환산 USD", "호출당 초"], rows, "llrrrr")
    add("")
    with_llm = [i for i in info.values() if i["llm_calls"]]
    add(f"LLM 을 쓴 run {len(with_llm)}개의 run 당 중앙값: 호출 {num(med([i['llm_calls'] for i in with_llm]), 1)} · 환산 {num(med([i['llm_usd'] for i in with_llm]), 2)} USD · "
        f"{num(med([i['llm_s'] for i in with_llm]))}초.")
    add("")

    # 5
    add("## 5. LLM 외형 검토 라운드")
    add("")
    names = {"no_ops": "지적 없음 · 고칠 것 없음", "reverted": "되돌림(게이트 · 진단이 나빠짐)", "accepted": "받아들임"}
    sides = {f"{ROUND_SPLIT[4:6]}-{ROUND_SPLIT[6:]} 앞": lambda r: r[1:9] < ROUND_SPLIT, f"{ROUND_SPLIT[4:6]}-{ROUND_SPLIT[6:]} 부터": lambda r: r[1:9] >= ROUND_SPLIT}
    rows = []
    for label, cond in sides.items():
        rr = [x for rid, i in info.items() if cond(rid) for x in i["rounds"]]
        c = collections.Counter(x.get("action") for x in rr)
        rows.append([label, len(rr), *[c[k] for k in names], len(rr) - sum(c[k] for k in names), num(sum(x.get("cost_usd") or 0 for x in rr), 2)])
    out += table(["기간", "라운드", *names.values(), "그 밖", "환산 USD"], rows, "lrrrrrr")
    add("")
    acc = [rid for rid, i in info.items() if rid[1:9] >= ROUND_SPLIT and any(x.get("action") == "accepted" for x in i["rounds"])]
    add("글자는 결정적 맞춤이, 픽셀은 오리기가 맡은 뒤로 라운드가 더한 것이 거의 없어 기본으로 껐다(`style_review.rounds: 0`)."
        + (f" 받아들인 {len(acc)}건의 화면 · run 결과 = " + " · ".join(f"{screen_of(r)}{'(검증 화면)' if is_probe(r) else ''} {info[r]['status']}" for r in acc) + "." if acc else ""))
    add("")

    # 6
    add("## 6. 게임 화면 run — 남은 것(" + f"{GAME_FROM[:4]}-{GAME_FROM[4:6]}-{GAME_FROM[6:]} 부터)")
    add("")

    def game_row(rid, i):
        done = sum(1 for g in i["gates"] if g.get("pass"))
        return [f"`{rid}`", i["route"] or "—", i["status"], f"{done}/{len(i['gates'])}", num(i["errors"]), num(i["approx"]), i["attempts"], num(i["total"]),
                f"{num(i['verify'])}({i['verifies']}번)", num(i["verify_one"], 1), "묶음" if i["batch"] else "한 장씩", num(i["rounds_allowed"]),
                f"{i['llm_calls']} · {num(i['llm_usd'], 2)}"]
    head = ["run", "길", "결과", "게이트", "오류", "근사", "시도", "run(초)", "verify(초)", "verify 1번(초)", "상태 렌더", "외형 라운드", "LLM 호출 · 환산 USD"]
    rows = [game_row(rid, i) for rid, i in sorted(info.items()) if rid[1:9] >= GAME_FROM and not is_probe(rid)]
    out += table(head, rows, "lllrrrrrrrlrr")
    add("")
    add("'오류' = 외형 진단이 찾은 국소 결함(0 이어야 통과), '근사' = 가장 가까운 선택을 골랐는데 남은 표현 차이(굵기 · 획 모양 등 — 기록만). run(초) = 단계 시간의 합. "
        "상태 렌더 '한 장씩' = 호출마다 글꼴 준비 2초를 기다리던 때, '묶음' = 한 호출로 모두 그린 때(설계 문서 §11 Phase 2).")
    add("")

    # 7
    add("## 7. 게임에 승격한 run")
    add("")
    rows = []
    for rid, note in PROMOTED.items():
        i = info.get(rid)
        a_ = collections.Counter(a["backend"] for a in assets if a["run_id"] == rid)
        rows.append([f"`{rid}`", note, (i or {}).get("status", "기록 없음"), num((i or {}).get("errors")), num((i or {}).get("approx")), num((i or {}).get("total")),
                     num((i or {}).get("llm_usd"), 2), " · ".join(f"{k} {v}" for k, v in sorted(a_.items())) or "—"])
    out += table(["run", "무엇", "결과", "오류", "근사", "run(초)", "환산 USD", "에셋"], rows, "lllrrrrl")
    add("")
    add("승격은 사람이 그림과 게임 안을 보고 정했다(눈 확인 기록은 설계 문서).")
    add("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="uigen run history summary (markdown)")
    ap.add_argument("--out", default=OUT, help="output markdown (repo-relative or absolute), '-' = stdout")
    ap.add_argument("--metrics", help="override paths.metrics")
    ap.add_argument("--work-root", help="override paths.work_root")
    o = ap.parse_args(argv)
    cfg = config.load_pipeline()
    m = pathlib.Path(o.metrics) if o.metrics else config.repo_path(cfg["paths"]["metrics"])
    w = pathlib.Path(o.work_root) if o.work_root else config.repo_path(cfg["paths"]["work_root"])
    text = build(load(m, w))
    if o.out == "-":
        print(text)
    else:
        p = config.repo_path(o.out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {o.out} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
