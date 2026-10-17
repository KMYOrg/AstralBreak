"""통합 러너 (Phase 6-5) — 에디터 기동 → 단계 테스트 전부 → quit → 재기동 → --recheck 전부 → quit. 결과는 Tools/mcp/results/<date>.json.

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/run_all.py [--engine D:/UnrealSource/UnrealEngine-5.7.4-release]
        [--project D:/UE5Projects/AstralBreak/AstralBreak.uproject] [--only phase6_5_test,phase6_2_test] [--skip-recheck] [--attach]

--attach 는 이미 떠 있는 에디터를 쓰고(기동·종료 안 함, recheck 생략) 단계 테스트만 돈다.
에디터 종료는 quit_editor(discard_dirty — 테스트가 저장할 것은 각자 저장했다) + wait_for_exit. 실패한 단계가 있어도 끝까지 돌고 종료 코드 1.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time

from anim_graph_mcp import bridge
from wait_for_exit import wait_for_exit

ROOT = pathlib.Path(__file__).resolve().parents[2]
PY = pathlib.Path(sys.executable)
MCP = ROOT / "Tools" / "mcp"

# 순서 중요 — 같은 ABP_McpTest 를 덮어쓰는 3·4·6-1 은 recheck 대상(6-1)을 마지막에, 6-2 는 끝에 quit 한다 (여기서는 --no-quit 으로 막고 러너가 종료)
PHASES = ["phase3_test", "phase4_test", "phase5_test", "phase6_1_test", "phase6_3_test", "phase6_4_test", "phase6_4b_test", "phase7_1_test", "phase7_2_test", "phase6_5_test", "phase6_2_test"]
# recheck 는 6-2(ABP_McpDup 정리) 뒤에 6-5 스모크를 돌려 애셋 수가 1차와 같게 한다
RECHECKS = ["phase5_test", "phase6_1_test", "phase6_3_test", "phase6_4_test", "phase6_4b_test", "phase7_1_test", "phase7_2_test", "phase6_2_test", "phase6_5_test"]


def run_script(name: str, extra: list[str]) -> dict:
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8", MSYS_NO_PATHCONV="1")
    proc = subprocess.run([str(PY), str(MCP / f"{name}.py"), *extra], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = proc.stdout + proc.stderr
    fails = [l for l in out.splitlines() if l.startswith("[FAIL]")]
    verdict = "PASS" if proc.returncode == 0 and "PASS" in out.splitlines()[-1:] else "FAIL"
    print(f"  {name} {' '.join(extra)}: {verdict} ({time.time() - t0:.0f}s){(' · ' + '; '.join(f[:120] for f in fails[:3])) if fails else ''}", flush=True)
    return {"name": name, "args": extra, "returncode": proc.returncode, "verdict": verdict, "seconds": round(time.time() - t0, 1), "fails": fails, "tail": out.splitlines()[-15:]}


def launch(engine: str, project: str) -> int:
    exe = pathlib.Path(engine) / "Engine" / "Binaries" / "Win64" / "UnrealEditor.exe"
    if not exe.exists():
        raise SystemExit(f"UnrealEditor.exe not found: {exe}")
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    proc = subprocess.Popen([str(exe), project], creationflags=flags, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  launched editor pid {proc.pid}", flush=True)
    deadline = time.time() + 600
    while time.time() < deadline:
        env = bridge.call("get_editor_status", timeout=5.0)
        if env.get("ok"):
            pid = int(env["result"].get("process_id") or proc.pid)
            print(f"  bridge ready (pid {pid}, tools {len(env['result'].get('tools', []))}); settling 25s", flush=True)
            time.sleep(25)
            return pid
        time.sleep(10)
    raise SystemExit("BRIDGE_TIMEOUT")


def quit_editor(pid: int) -> bool:
    r = bridge.call("quit_editor", {"discard_dirty": True}, timeout=180)
    if not r.get("ok"):
        print(f"  quit_editor failed: {r.get('error')}", flush=True)
        return False
    return wait_for_exit(pid, timeout=180.0, interval=5.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default=os.environ.get("UE_ENGINE_ROOT", "D:/UnrealSource/UnrealEngine-5.7.4-release"))
    ap.add_argument("--project", default=str(ROOT / "AstralBreak.uproject"))
    ap.add_argument("--only", default="")
    ap.add_argument("--skip-recheck", action="store_true")
    ap.add_argument("--attach", action="store_true")
    args = ap.parse_args()

    phases = [p for p in args.only.split(",") if p] or PHASES
    rechecks = [p for p in RECHECKS if p in phases] if args.only else RECHECKS
    results = {"started": dt.datetime.now().isoformat(timespec="seconds"), "engine": args.engine, "project": args.project, "phases": [], "rechecks": []}
    ok = True

    if args.attach:
        st = bridge.call("get_editor_status")
        if not st.get("ok"):
            raise SystemExit("--attach: no editor bridge reachable")
        pid = int(st["result"].get("process_id") or 0)
    else:
        if bridge.call("get_editor_status", timeout=3.0).get("ok"):
            raise SystemExit("An editor bridge is already up on this port — close it or use --attach")
        print("== launch", flush=True)
        pid = launch(args.engine, args.project)

    print("== phases", flush=True)
    for p in phases:
        extra = ["--no-quit"] if p == "phase6_2_test" else []
        r = run_script(p, extra)
        results["phases"].append(r)
        ok &= r["verdict"] == "PASS"

    if not args.attach:
        print("== quit", flush=True)
        if not quit_editor(pid):
            ok = False
            results["quit1"] = "FAIL"
        if not args.skip_recheck:
            print("== relaunch", flush=True)
            pid = launch(args.engine, args.project)
            print("== rechecks", flush=True)
            for p in rechecks:
                extra = ["--recheck"] + (["--no-quit"] if p == "phase6_2_test" else [])
                r = run_script(p, extra)
                results["rechecks"].append(r)
                ok &= r["verdict"] == "PASS"
            print("== quit", flush=True)
            if not quit_editor(pid):
                ok = False
                results["quit2"] = "FAIL"

    results["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    results["ok"] = ok
    out_dir = MCP / "results"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"{dt.datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n{'ALL PASS' if ok else 'FAILURES'} → {out}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
