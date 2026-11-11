"""파티 흐름 네트워크 시험 — 별도 프로세스 구성 실행기 (설계 Docs/Design/m3-enemy-ai.md §7-2)

서버 1 + 클라이언트 N 을 에디터 실행 파일의 -game / -server 로 띄우고, 프로세스마다 도는
UAstralPartyFlowTestController(-gauntlet=AstralPartyFlowTest)의 표준 출력으로 판정한다.

    python -X utf8 -B Tools/net_test/run_party_flow.py listen
    python -X utf8 -B Tools/net_test/run_party_flow.py dedicated
    python -X utf8 -B Tools/net_test/run_party_flow.py dedicated --scenario leader_leaves

    listen      2단계 — 리슨 서버(호스트 = 플레이어 1) + 클라이언트 (players - 1)
    dedicated   3단계 — Dedicated 서버 + 클라이언트 players

판정
    1. 모든 프로세스가 `ASTRAL_NETTEST RESULT PASS` 를 한 번 찍는다 (FAIL 이 하나라도 있으면 실패)
    2. 서버 출력의 거부 로그가 정해진 횟수만큼 나온다 (방장이 아닌 요청 · 허용 밖 맵 · 준비 전 시작)
    3. 흐름 시나리오: 서버가 시임리스 이동을 사람 수 x 2 번 처리한다

출력은 Tools/mcp/results/net_test/<시각>_<구성>_<시나리오>/ (git 제외)에 프로세스별 로그와 result.json 으로 남는다.
먼저 Development 또는 DebugGame 에디터 구성이 빌드돼 있어야 한다. 에디터는 내려 두는 것을 권한다(프로세스 3 ~ 4개가 뜬다).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
UPROJECT = REPO / "AstralBreak.uproject"
DEFAULT_ENGINE = Path("D:/UnrealSource/UnrealEngine-5.7.4-release")
EXE_NAMES = {"DebugGame": "UnrealEditor-Win64-DebugGame.exe", "Development": "UnrealEditor.exe"}

MARK = "ASTRAL_NETTEST"
READY = f"{MARK} READY"
RESULT = re.compile(rf"{MARK} RESULT (PASS|FAIL)(.*)")

# 서버 출력에서 세는 줄 — (이름, 정규식, 기대 횟수 함수(players))
REJECT_NOT_LEADER = r"Server{rpc}: 방장이 아님"
FLOW_COUNTS = [
    ("select_not_leader", REJECT_NOT_LEADER.format(rpc="SelectRaid"), lambda n: n - 1),
    ("start_not_leader", REJECT_NOT_LEADER.format(rpc="StartRaid"), lambda n: n - 1),
    ("return_not_leader", REJECT_NOT_LEADER.format(rpc="ReturnToHub"), lambda n: n - 1),
    ("select_map_not_allowed", r"ServerSelectRaid: 허용 목록에 없는 맵", lambda n: 2),
    ("start_not_all_ready", r"ServerStartRaid: 전원 준비 아님", lambda n: 1),
    ("seamless_travel_player", r"HandleSeamlessTravelPlayer: ", lambda n: 2 * n),
]
LEADER_LEAVES_COUNTS = [
    ("select_not_leader", REJECT_NOT_LEADER.format(rpc="SelectRaid"), lambda n: n - 2),
]

# 적 전투(enemy_combat) — 서버 로그가 아니라 프로세스마다 찍는 표지 줄로 판정한다 (enemy_combat_checks)
SCENARIO_ARGS = {"flow": "Flow", "leader_leaves": "LeaderLeaves", "enemy_combat": "EnemyCombat"}
START_MAPS = {"flow": "HubMap", "leader_leaves": "HubMap", "enemy_combat": "CombatTestMap"}
ENEMY_ATTACK_DAMAGE = 15.0  # GA_Enemy_MeleeAttack.BaseDamage (잠정) — 바꾸면 여기도 바꾼다
HERO_MAX_HEALTH = 100.0


class Proc:
    def __init__(self, name: str, args: list[str], log_path: Path):
        self.name = name
        self.log_path = log_path
        self._file = open(log_path, "wb")
        self.popen = subprocess.Popen(args, stdout=self._file, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=str(REPO))
        self._offset = 0
        self._tail = ""
        self.marks: list[str] = []

    def poll_marks(self) -> list[str]:
        """새로 찍힌 ASTRAL_NETTEST 줄만 돌려준다."""
        with open(self.log_path, "rb") as f:
            f.seek(self._offset)
            chunk = f.read()
        self._offset += len(chunk)
        text = self._tail + chunk.decode("utf-8", errors="replace")
        lines = text.split("\n")
        self._tail = lines.pop()
        new = [line.strip() for line in lines if MARK in line]
        self.marks += new
        return new

    def results(self) -> list[str]:
        return [m.group(1) for m in (RESULT.search(line) for line in self.marks) if m]

    def alive(self) -> bool:
        return self.popen.poll() is None

    def stop(self) -> None:
        if self.alive():
            self.popen.kill()
            try:
                self.popen.wait(timeout=20)
            except subprocess.TimeoutExpired:
                pass
        self._file.close()

    def text(self) -> str:
        return self.log_path.read_text(encoding="utf-8", errors="replace")


def mark_fields(line: str, kind: str) -> dict[str, str] | None:
    """`ASTRAL_NETTEST <kind> k=v k=v` 줄이면 k/v 사전, 아니면 None."""
    head = f"{MARK} {kind} "
    if head not in line:
        return None
    return dict(token.split("=", 1) for token in line[line.index(head) + len(head):].split() if "=" in token)


def enemy_combat_checks(procs: list[Proc]) -> list[dict]:
    """A9 — 적의 공격이 서버에서 HP 를 깎고 같은 값이 모든 프로세스에 온다(HIT) · 적이 죽으면 어디서나 사라진다(GONE)."""
    checks: list[dict] = []

    def fields(proc: Proc, kind: str) -> list[dict[str, str]]:
        return [f for f in (mark_fields(line, kind) for line in proc.marks) if f is not None]

    spawn_requests = [(proc.name, f) for proc in procs for f in fields(proc, "SPAWN_REQUEST")]
    checks.append({"check": "one SpawnEnemy request, from a client", "expected": 1, "actual": [name for name, _ in spawn_requests],
                   "ok": len(spawn_requests) == 1 and spawn_requests[0][0].startswith("client")})

    hits = {proc.name: fields(proc, "HIT") for proc in procs}
    seen = sorted({(f.get("victim"), f.get("hp")) for per_proc in hits.values() for f in per_proc})
    expected_hp = f"{HERO_MAX_HEALTH - ENEMY_ATTACK_DAMAGE:.1f}"
    checks.append({"check": "every process saw the hit", "expected": 1, "actual": {name: len(v) for name, v in hits.items()},
                   "ok": all(len(v) == 1 for v in hits.values())})
    checks.append({"check": "same victim and health on the server and every client", "expected": f"one (victim, {expected_hp})", "actual": seen,
                   "ok": len(seen) == 1 and seen[0][1] == expected_hp})
    server_hit = hits.get("server") or [{}]
    checks.append({"check": "server: the enemy's target is the hero it hit", "expected": "1", "actual": server_hit[0].get("target_is_victim"),
                   "ok": server_hit[0].get("target_is_victim") == "1"})

    enemy_seen = {proc.name: fields(proc, "ENEMY") for proc in procs}
    controllers = {name: (v[0].get("controller") if v else None) for name, v in enemy_seen.items()}
    checks.append({"check": "enemy pawn on every process, controller only on the server", "expected": "server 1, clients 0", "actual": controllers,
                   "ok": all(value == ("1" if name == "server" else "0") for name, value in controllers.items())})

    kills = [proc.name for proc in procs for _ in fields(proc, "KILL")]
    checks.append({"check": "the server killed the enemy once", "expected": ["server"], "actual": kills, "ok": kills == ["server"]})
    gone = {proc.name: sum(1 for line in proc.marks if f"{MARK} GONE " in line) for proc in procs}
    checks.append({"check": "enemy pawn gone on every process", "expected": 1, "actual": gone, "ok": all(count == 1 for count in gone.values())})
    return checks


def editor_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq UnrealEditor*", "/NH", "/FO", "CSV"], capture_output=True, text=True,
                             encoding="oem", errors="replace", timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "UnrealEditor" in (out or "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=["listen", "dedicated"])
    parser.add_argument("--scenario", choices=sorted(SCENARIO_ARGS), default="flow")
    parser.add_argument("--players", type=int, default=None, help="사람 수 (기본: flow · enemy_combat 2, leader_leaves 3)")
    parser.add_argument("--config", choices=sorted(EXE_NAMES), default="DebugGame")
    parser.add_argument("--engine", type=Path, default=DEFAULT_ENGINE)
    parser.add_argument("--port", type=int, default=17777)
    parser.add_argument("--timeout", type=float, default=420.0, help="전체 제한 시간(초)")
    parser.add_argument("--startup-timeout", type=float, default=240.0, help="서버가 READY 를 찍을 때까지(초)")
    args = parser.parse_args()

    players = args.players or (3 if args.scenario == "leader_leaves" else 2)
    if args.scenario == "leader_leaves" and args.mode != "dedicated":
        parser.error("leader_leaves 는 dedicated 에서만 돈다 (리슨 호스트는 나갈 수 없다)")
    if players < 2 or (args.scenario == "leader_leaves" and players < 3):
        parser.error("players 는 2 이상 (leader_leaves 는 3 이상)")

    exe = args.engine / "Engine" / "Binaries" / "Win64" / EXE_NAMES[args.config]
    if not exe.is_file():
        parser.error(f"에디터 실행 파일이 없다: {exe}")
    if editor_running():
        print("WARNING: UnrealEditor 프로세스가 이미 떠 있다 — 메모리가 빠듯하면 내리고 다시 돌릴 것", flush=True)

    out_dir = REPO / "Tools" / "mcp" / "results" / "net_test" / f"{datetime.now():%m%d_%H%M%S}_{args.mode}_{args.scenario}"
    out_dir.mkdir(parents=True, exist_ok=True)

    scenario_arg = SCENARIO_ARGS[args.scenario]
    start_map = START_MAPS[args.scenario]
    common = [
        "-gauntlet=AstralPartyFlowTest", "-gauntlet.tickrate=0.2",
        f"-AstralPartyPlayers={players}", f"-AstralPartyScenario={scenario_arg}", f"-AstralPartyTimeout={args.timeout - 30:.0f}",
        "-unattended", "-nosplash", "-nosound", "-nullrhi", "-NoLoadingScreen",
        "-stdout", "-FullStdOutLogOutput", "-UTF8Output",
    ]
    base = [str(exe), str(UPROJECT)]
    if args.mode == "listen":
        server_args = base + [f"{start_map}?listen", "-game", f"-port={args.port}"] + common
        num_clients = players - 1
    else:
        server_args = base + [start_map, "-server", f"-port={args.port}"] + common
        num_clients = players
    client_args = base + [f"127.0.0.1:{args.port}", "-game"] + common

    procs: list[Proc] = []
    started = time.time()
    failure: str | None = None

    def pump() -> None:
        for proc in procs:
            for line in proc.poll_marks():
                print(f"[{time.time() - started:6.1f}s {proc.name}] {line[line.index(MARK):]}", flush=True)

    try:
        server = Proc("server", server_args, out_dir / "server.log")
        procs.append(server)
        print(f"server started (pid {server.popen.pid}) — waiting for READY", flush=True)
        while not any(READY in line for line in server.marks):
            pump()
            if not server.alive():
                failure = "server exited before READY"
                break
            if time.time() - started > args.startup_timeout:
                failure = "server did not reach READY in time"
                break
            time.sleep(1.0)

        if not failure:
            for index in range(num_clients):
                # 적 전투 — 첫 클라이언트만 SpawnEnemy 를 부른다
                extra = ["-AstralEnemySpawner"] if args.scenario == "enemy_combat" and index == 0 else []
                client = Proc(f"client{index + 1}", client_args + extra, out_dir / f"client{index + 1}.log")
                procs.append(client)
                print(f"client{index + 1} started (pid {client.popen.pid})", flush=True)

            # 전원이 결과를 찍고 내려갈 때까지
            failed_at: float | None = None
            while True:
                pump()
                if all(not proc.alive() for proc in procs):
                    break
                if any("FAIL" in proc.results() for proc in procs):
                    # 하나가 실패하면 나머지는 제한 시간까지 기다릴 뿐이다 — 로그가 마저 나올 시간만 주고 끝낸다
                    failed_at = failed_at or time.time()
                    if time.time() - failed_at > 10.0:
                        break
                if all(proc.results() for proc in procs) and all(not proc.alive() for proc in procs[1:]):
                    # 클라이언트는 다 내려갔고 서버만 남았다 — 서버는 스스로 내려가지만 오래 붙들지 않는다
                    deadline = time.time() + 45.0
                    while server.alive() and time.time() < deadline:
                        time.sleep(1.0)
                    break
                if time.time() - started > args.timeout:
                    failure = "timed out"
                    break
                time.sleep(1.0)
    finally:
        pump()
        for proc in procs:
            proc.stop()
        pump()

    # ─── 판정 ───
    checks: list[dict] = []
    for proc in procs:
        results = proc.results()
        checks.append({"check": f"{proc.name}: RESULT", "expected": ["PASS"], "actual": results, "ok": results == ["PASS"]})
    if len(procs) != 1 + num_clients:
        checks.append({"check": "all processes started", "expected": 1 + num_clients, "actual": len(procs), "ok": False})

    server_text = procs[0].text() if procs else ""
    for name, pattern, expected_fn in {"flow": FLOW_COUNTS, "leader_leaves": LEADER_LEAVES_COUNTS}.get(args.scenario, []):
        expected = expected_fn(players)
        actual = len(re.findall(pattern, server_text))
        checks.append({"check": f"server log: {name}", "expected": expected, "actual": actual, "ok": actual == expected})
    if args.scenario == "enemy_combat":
        checks += enemy_combat_checks(procs)
    hard_travel = len(re.findall(r"Seamless travel is disabled", server_text))
    checks.append({"check": "server log: no hard-travel fallback", "expected": 0, "actual": hard_travel, "ok": hard_travel == 0})
    if failure:
        checks.append({"check": "run", "expected": "completed", "actual": failure, "ok": False})

    ok = all(check["ok"] for check in checks)
    summary = {
        "ok": ok, "mode": args.mode, "scenario": args.scenario, "players": players, "config": args.config,
        "elapsed_sec": round(time.time() - started, 1), "out_dir": str(out_dir),
        "checks": checks,
        "exit_codes": {proc.name: proc.popen.returncode for proc in procs},
        "marks": {proc.name: [line[line.index(MARK):] for line in proc.marks] for proc in procs},
    }
    (out_dir / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    for check in checks:
        print(f"  {'ok  ' if check['ok'] else 'FAIL'} {check['check']}: expected {check['expected']}, got {check['actual']}")
    print(f"\n{'PASS' if ok else 'FAIL'} {args.mode}/{args.scenario} players={players} ({summary['elapsed_sec']}s) -> {out_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
