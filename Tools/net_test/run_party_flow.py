"""파티 흐름 네트워크 시험 — 별도 프로세스 구성 실행기 (설계 Docs/Design/m3-enemy-ai.md §7-2)

서버 1 + 클라이언트 N 을 에디터 실행 파일의 -game / -server 로 띄우고, 프로세스마다 도는
UAstralPartyFlowTestController(-gauntlet=AstralPartyFlowTest)의 표준 출력으로 판정한다.

    python -X utf8 -B Tools/net_test/run_party_flow.py listen
    python -X utf8 -B Tools/net_test/run_party_flow.py dedicated
    python -X utf8 -B Tools/net_test/run_party_flow.py dedicated --scenario leader_leaves
    python -X utf8 -B Tools/net_test/run_party_flow.py dedicated --scenario raid_clear --players 4

    listen      2단계 — 리슨 서버(호스트 = 플레이어 1) + 클라이언트 (players - 1)
    dedicated   3단계 — Dedicated 서버 + 클라이언트 players

    raid_clear  허브 → RaidMap → 구역 진입 → 수호병 3 → 전투 → 처치 → 전멸 → 허브 복귀 (설계 §12 E2, 판정 = raid_clear_checks)

체인 버스트 (설계 Docs/Design/m4-ult-chain.md §6 '단위 E 설계', 컨트롤러 = UAstralChainBurstTestController)

    python -X utf8 -B Tools/net_test/run_party_flow.py dedicated --scenario chain_burst --players 4
    python -X utf8 -B Tools/net_test/run_party_flow.py listen --scenario chain_burst
    python -X utf8 -B Tools/net_test/run_party_flow.py dedicated --scenario chain_deadline

    chain_burst     허브 → RaidMap → 동료 HUD → 수호병을 둘러싸고 한 명씩 이어 쓴다 → 버스트 → 둘째 사람이 나간다 → 동료 줄이 당겨진다 (판정 = chain_burst_checks)
    chain_deadline  CombatTestMap, 클라이언트마다 다른 왕복 지연(--rtts) — 함께 누르기 1판 + 사람마다 마감에 누르기 1판 (판정 = chain_deadline_checks)

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
SCENARIO_ARGS = {"flow": "Flow", "leader_leaves": "LeaderLeaves", "enemy_combat": "EnemyCombat", "raid_clear": "RaidClear",
                 "chain_burst": "ChainBurst", "chain_deadline": "ChainDeadline"}
START_MAPS = {"flow": "HubMap", "leader_leaves": "HubMap", "enemy_combat": "CombatTestMap", "raid_clear": "HubMap",
              "chain_burst": "HubMap", "chain_deadline": "CombatTestMap"}
CHAIN_SCENARIOS = ("chain_burst", "chain_deadline")
DEFAULT_PLAYERS = {"leader_leaves": 3, "chain_deadline": 4}
ENEMY_ATTACK_DAMAGE = 15.0  # GA_Enemy_MeleeAttack.BaseDamage (잠정) — 바꾸면 여기도 바꾼다
HERO_MAX_HEALTH = 100.0

# 레이드 전멸(raid_clear) — 거부 확인은 하지 않는다(flow 가 한다): 서버에 거부 로그가 없어야 한다
RAID_GUARDIANS = 3  # RaidMap 의 EnemySpawner_Guardian_01 스폰 지점 수 (잠정) — 컨트롤러의 RaidGuardianCount 와 같이 바꾼다
RAID_CLEAR_COUNTS = [
    ("rejected_requests", r"방장이 아님|허용 목록에 없는 맵|전원 준비 아님", lambda n: 0),
    ("seamless_travel_player", r"HandleSeamlessTravelPlayer: ", lambda n: 2 * n),
]

# 체인 버스트(chain_burst) — 허브 → 레이드 한 번만 이동한다(복귀 없음)
CHAIN_BURST_COUNTS = [
    ("rejected_requests", r"방장이 아님|허용 목록에 없는 맵|전원 준비 아님", lambda n: 0),
    ("seamless_travel_player", r"HandleSeamlessTravelPlayer: ", lambda n: n),
]
MAX_PARTICIPANTS = 4  # UAstralChainBurstComponent.MaxParticipants (잠정) — HUD 의 'N/4'

# 체인 마감(chain_deadline) — 클라이언트마다의 왕복 지연(ms, 잠정). 보내는 쪽 · 받는 쪽에 절반씩 건다
DEFAULT_RTTS = "50,100,200,300"
REQUIRED_RTT_MS = 100  # 이 지연까지는 마감 직전에 누른 오의가 참가로 인정돼야 한다 (잠정 기준)


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


def raid_clear_checks(procs: list[Proc], players: int) -> list[dict]:
    """E2 — 스폰 · 전투 · 제거 · 이동을 프로세스마다 같게 본다. 처치는 서버의 DamageSelf 다(히어로의 공격이 아니다)."""
    checks: list[dict] = []

    def fields(proc: Proc, kind: str) -> list[dict[str, str]]:
        return [f for f in (mark_fields(line, kind) for line in proc.marks) if f is not None]

    def one(kind: str, key: str) -> dict[str, str | None]:
        """프로세스마다 그 줄이 정확히 하나일 때 그 값, 아니면 None."""
        out: dict[str, str | None] = {}
        for proc in procs:
            found = fields(proc, kind)
            out[proc.name] = found[0].get(key) if len(found) == 1 else None
        return out

    def expect(check: str, expected, actual, ok: bool) -> None:
        checks.append({"check": check, "expected": expected, "actual": actual, "ok": ok})

    guardians = str(RAID_GUARDIANS)
    arrived = one("ARRIVED", "enemies")
    expect("no enemy on arrival, on every process", "0", arrived, all(value == "0" for value in arrived.values()))

    entered = [(proc.name, f.get("activated")) for proc in procs for f in fields(proc, "ENTER")]
    expect("the server moved the heroes into the zone and the spawner activated", [("server", "1")], entered, entered == [("server", "1")])

    pawns = one("GUARDIANS", "pawns")
    expect(f"{guardians} guardian pawns on every process", guardians, pawns, all(value == guardians for value in pawns.values()))
    controllers = one("GUARDIANS", "controllers")
    expect("guardian controllers only on the server", f"server {guardians}, clients 0", controllers,
           all(value == (guardians if name == "server" else "0") for name, value in controllers.items()))
    trees = [f.get("trees") for f in fields(procs[0], "GUARDIANS")]
    expect("server: every guardian's StateTree is running", [guardians], trees, trees == [guardians])

    hits = {proc.name: len(fields(proc, "HIT")) for proc in procs}
    expect("every process saw a hero lose health", 1, hits, all(count == 1 for count in hits.values()))

    cleared = [(proc.name, f.get("activated"), f.get("alive"), f.get("cleared")) for proc in procs for f in fields(proc, "CLEARED")]
    expect("the server killed the guardians: spawner activated, 0 alive, OnCleared once", [("server", "1", "0", "1")], cleared,
           cleared == [("server", "1", "0", "1")])

    heroes = one("HEROES", "hp")
    tables = sorted({value for value in heroes.values() if value is not None})
    expect("same hero health on the server and every client after the fight", "one table", heroes,
           len(tables) == 1 and all(value is not None for value in heroes.values()))
    health = [float(entry.split(":")[1]) for entry in tables[0].split(",")] if len(tables) == 1 else []
    expect("every hero has a health value, at least one below the maximum", f"{players} values, min < {HERO_MAX_HEALTH}", health,
           len(health) == players and all(value >= 0.0 for value in health) and min(health) < HERO_MAX_HEALTH)

    gone = {proc.name: len(fields(proc, "GONE")) for proc in procs}
    expect("guardian pawns gone on every process", 1, gone, all(count == 1 for count in gone.values()))
    destroyed = [(f.get("destroyed"), f.get("seconds")) for f in fields(procs[0], "GONE")]
    expect("server: every guardian destroyed (seconds after the kill is informational)", guardians, destroyed,
           len(destroyed) == 1 and destroyed[0][0] == guardians)

    returns = [proc.name for proc in procs for _ in fields(proc, "RETURN")]
    expect("the leader asked to return once", 1, returns, len(returns) == 1)
    return checks


def chain_fields(procs: list[Proc], kind: str) -> dict[str, list[dict[str, str]]]:
    """프로세스 이름 → 그 종류의 줄들(k/v 사전)."""
    return {proc.name: [f for f in (mark_fields(line, kind) for line in proc.marks) if f is not None] for proc in procs}


def my_ids(procs: list[Proc]) -> dict[str, int]:
    """프로세스 이름 → 내 PlayerId (Dedicated 서버는 빠진다)."""
    out: dict[str, int] = {}
    for proc in procs:
        for line in proc.marks:
            base = mark_fields(line, "BASE")
            if base and base.get("role") != "server":
                out[proc.name] = int(base["my"])
    return out


def chain_burst_checks(procs: list[Proc], players: int) -> list[dict]:
    """E ① — 4인(또는 2인)이 이어 쓴 체인 버스트를 모든 프로세스가 같게 본다 · 동료 HUD 의 줄이 채워지고 당겨진다."""
    checks: list[dict] = []

    def expect(check: str, expected, actual, ok: bool) -> None:
        checks.append({"check": check, "expected": expected, "actual": actual, "ok": ok})

    ids = my_ids(procs)
    order = sorted(ids.values())
    if len(order) != players:
        expect("every player has an id", players, ids, False)
        return checks
    leaver = order[1]
    seats = {name: my for name, my in ids.items()}
    remaining = {name: my for name, my in seats.items() if my != leaver}

    setup = chain_fields(procs, "SETUP")["server"]
    expect("server: guardians placed, every hero faces the target", (str(RAID_GUARDIANS), str(players)),
           [(f.get("enemies"), f.get("facing")) for f in setup], [(f.get("enemies"), f.get("facing")) for f in setup] == [(str(RAID_GUARDIANS), str(players))])

    # ─── 동료 HUD ───
    rows = chain_fields(procs, "HUDROWS")

    def ally_ids(my: int, where: str, name: str) -> list[int]:
        found = [f["rows"] for f in rows[name] if f.get("where") == where]
        if len(found) != 1:
            return [-1]
        return [int(cell.split(":")[0]) for cell in found[0].split("|")[2:] if cell != "-"]

    arrived = {name: ally_ids(my, "arrived", name) for name, my in seats.items()}
    expect("ally rows after seamless travel: everyone else in PlayerId order (the controller checked name, hp, ult and visibility)",
           "the other players", arrived, all(arrived[name] == [i for i in order if i != my] for name, my in seats.items()))
    left = {name: ally_ids(my, "left", name) for name, my in remaining.items()}
    expect(f"ally rows after player {leaver} left: pulled up, last row closed", "the other players without the leaver", left,
           all(left[name] == [i for i in order if i not in (my, leaver)] for name, my in remaining.items()))

    # ─── 체인 ───
    casts = [(int(f["id"]), f["joined"]) for f in chain_fields(procs, "CAST")["server"]]
    expect("server: one cast per player, in order (the first opens, the rest join a paused chain)",
           [(i, "0" if n == 0 else "1") for n, i in enumerate(order)], casts, casts == [(i, "0" if n == 0 else "1") for n, i in enumerate(order)])

    chain = chain_fields(procs, "CHAIN")
    lists = {name: [f["ids"] for f in found if f.get("id") == "1" and f.get("ids") != "-"] for name, found in chain.items()}
    # 프로세스마다 본 참가자 목록의 흐름 — 복제가 중간을 건너뛸 수 있어 '앞에서부터의 부분 목록' 이기만 하면 된다. 마지막 직전(전원 - 1)까지는 모두가 봐야 한다
    prefixes = [",".join(str(i) for i in order[:n]) for n in range(1, players + 1)]
    expect("every process saw the participants grow in cast order", prefixes[:players - 1], {name: list(dict.fromkeys(v)) for name, v in lists.items()},
           all(all(entry in prefixes for entry in v) and set(prefixes[:players - 1]) <= set(v) for v in lists.values()))

    bursts = {name: [(f.get("id"), f.get("x"), f.get("hp")) for f in found] for name, found in chain_fields(procs, "BURST").items()}
    values = sorted({value for found in bursts.values() for value in found})
    expect(f"every process: burst #1 x{players} and the same guardian health", f"one (1, {players}, hp list)", bursts,
           all(len(found) == 1 for found in bursts.values()) and len(values) == 1 and values[0][0] == "1" and values[0][1] == str(players)
           and len(values[0][2].split(",")) == RAID_GUARDIANS)

    report = chain_fields(procs, "BURST_REPORT")["server"]
    ok = len(report) == 1
    if ok:
        f = report[0]
        ok = (f["x"] == f["contributors"] == str(players) and f["targets"] == str(RAID_GUARDIANS)
              and abs(float(f["target_loss"]) - float(f["expected_loss"])) <= 0.5)
    expect("server: contributors = head count, every guardian hit, target loss = ults + burst",
           (str(players), str(RAID_GUARDIANS), "expected_loss"), report, ok)

    # ─── 자리 ───
    seen = chain_fields(procs, "SEEN")
    blocked = {name: [f.get("blocked_while") for f in seen[name]] for name in seats}
    expect("every seat saw its own block tag while each of the others was casting", "the other players", blocked,
           all(v == [",".join(str(i) for i in order if i != seats[name])] for name, v in blocked.items()))
    own = {name: [f.get("blocked_by_own") for f in seen[name]] for name in seats}
    expect("nobody was blocked by its own ult", "0", own, all(v == ["0"] for v in own.values()))
    counts = [f"{n}/{MAX_PARTICIPANTS}" for n in range(1, players)]
    shown = {name: [(f.get("counts"), f.get("banner")) for f in seen[name]] for name in seats}
    expect("combat HUD on every seat: chain counts and the burst banner", (",".join(counts), str(players)), shown,
           all(v == [(",".join(counts), str(players))] for v in shown.values()))

    leaving = [name for name, found in chain_fields(procs, "LEAVING").items() for _ in found]
    expect("the second player left once", [name for name, my in seats.items() if my == leaver], leaving, leaving == [name for name, my in seats.items() if my == leaver])
    return checks


def chain_deadline_checks(procs: list[Proc], players: int, rtts: dict[str, int]) -> tuple[list[dict], list[dict]]:
    """E ② — (판정, 마감 실측 표). rtts = 프로세스 이름 → 건 왕복 지연(ms)."""
    checks: list[dict] = []

    def expect(check: str, expected, actual, ok: bool) -> None:
        checks.append({"check": check, "expected": expected, "actual": actual, "ok": ok})

    ids = my_ids(procs)
    order = sorted(ids.values())
    if len(order) != players:
        expect("every player has an id", players, ids, False)
        return checks, []
    name_of = {my: name for name, my in ids.items()}

    lag = {name: [(f.get("out"), f.get("in_min"), f.get("in_max")) for f in found] for name, found in chain_fields(procs, "LAG").items() if name in rtts}
    wanted = {name: [(str(rtt // 2),) * 3] for name, rtt in rtts.items()}
    expect("packet emulation is applied on every client", wanted, lag, lag == wanted)

    setup = chain_fields(procs, "SETUP")["server"]
    grace = float(setup[0]["grace"]) if len(setup) == 1 else -1.0
    expect("server: setup line", 1, len(setup), len(setup) == 1)

    presses = {name: {f["serial"]: f for f in found} for name, found in chain_fields(procs, "PRESS").items()}
    outcomes = {name: {f["serial"]: f for f in found} for name, found in chain_fields(procs, "OUTCOME").items()}

    # ─── 경합 ───
    race = chain_fields(procs, "RACE")["server"]
    if len(race) == 1:
        f = race[0]
        racers = [int(i) for i in f["racers"].split(",")]
        casters = [int(i) for i in f["casters"].split(",") if i != "-"]
        expect("race: three players pressed together, the server let exactly one cast", "one of the racers", casters, len(casters) == 1 and casters[0] in racers)
        winner = casters[0] if casters else 0
        losers = [i for i in racers if i != winner]
        expect("race: no loser's ult ever ran on the server", str(winner), f["active"], f["active"] == str(winner))
        gauges = dict((int(cell.split(":")[0]), float(cell.split(":")[1])) for cell in f["min_gauge"].split(","))
        expect("race: the losers' gauge on the server stayed full", {i: 100.0 for i in losers}, {i: gauges.get(i) for i in losers},
               all(gauges.get(i) == 100.0 for i in losers))
        race_press = {i: presses[name_of[i]].get(f["serial"], {}) for i in racers}
        race_out = {i: outcomes[name_of[i]].get(f["serial"], {}) for i in racers}
        raced = [i for i in losers if race_press[i].get("blocked") == "0" and race_out[i].get("predicted") == "1"]
        expect("race: at least one loser pressed before the block arrived and predicted the ult (otherwise there was no race)", "1 or 2 of the losers", raced, len(raced) >= 1)
        rolled = {i: (race_out[i].get("won"), race_out[i].get("active"), race_out[i].get("gauge")) for i in losers}
        expect("race: the losers rolled back on their own seat (not casting, gauge full)", "('0', '0', '100.0')", rolled,
               all(race_out[i].get("pressed") == "0" or value == ("0", "0", "100.0") for i, value in rolled.items()))
        expect("race: the winner's own outcome", "('1', '0')", (race_out.get(winner, {}).get("won"), race_out.get(winner, {}).get("active")),
               (race_out.get(winner, {}).get("won"), race_out.get(winner, {}).get("active")) == ("1", "0"))
    else:
        expect("race: one RACE line from the server", 1, len(race), False)

    bursts = {name: [(f.get("id"), f.get("x")) for f in found] for name, found in chain_fields(procs, "BURST").items()}
    expect("race: the losers could cast afterwards — burst #1 x4 on every process", ("1", "4"), bursts, all(found == [("1", "4")] for found in bursts.values()))

    # ─── 마감 ───
    rounds = chain_fields(procs, "ROUND")["server"]
    casts = {f["serial"]: f for f in chain_fields(procs, "CAST")["server"]}
    expect("deadline: one round per player", order, [int(f["tester"]) for f in rounds], [int(f["tester"]) for f in rounds] == order)
    table: list[dict] = []
    for f in rounds:
        tester = int(f["tester"])
        name = name_of[tester]
        press = next((p for p in presses[name].values() if p["kind"] == "last"), None)
        cast = casts.get(press["serial"]) if press else None
        if not press or not cast or int(cast["id"]) != tester:
            expect(f"deadline: player {tester} pressed and the server saw it", tester, (press, cast), False)
            continue
        screen_left, left, joined = float(press["screen_left"]), float(cast["left"]), cast["joined"] == "1"
        rtt = rtts.get(name, 0)
        burst_here = f["burst_id"] == f["chain"] and f["burst_x"] == "2"
        table.append({"proc": name, "player": tester, "rtt_ms": rtt, "ping_ms": float(press["ping"]), "screen_left": screen_left, "server_left": left,
                      "late": round(screen_left - left, 3), "joined": joined, "burst": burst_here, "chain_after": int(f["chain_after"]) - int(f["chain"])})
        expect(f"deadline: player {tester} (rtt {rtt} ms) — the server's verdict matches the arrival time (joined iff left >= -{grace:g})",
               left >= -grace, joined, joined == (left >= -grace))
        expect(f"deadline: player {tester} — joined => burst x2 of that chain, otherwise a new chain and no burst",
               (True, 0) if joined else (False, 1), (burst_here, int(f["chain_after"]) - int(f["chain"])),
               (burst_here, int(f["chain_after"]) - int(f["chain"])) == ((True, 0) if joined else (False, 1)))
        if rtt <= REQUIRED_RTT_MS:
            expect(f"deadline: player {tester} — a last-moment press at rtt {rtt} ms is accepted", True, joined, joined)
    return checks, table


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
    parser.add_argument("--players", type=int, default=None, help="사람 수 (기본: leader_leaves 3 · chain_deadline 4 · 나머지 2)")
    parser.add_argument("--rtts", default=DEFAULT_RTTS, help="chain_deadline — 클라이언트마다의 왕복 지연(ms, 쉼표로). 절반은 보낼 때, 절반은 받을 때 건다")
    parser.add_argument("--config", choices=sorted(EXE_NAMES), default="DebugGame")
    parser.add_argument("--engine", type=Path, default=DEFAULT_ENGINE)
    parser.add_argument("--port", type=int, default=17777)
    parser.add_argument("--timeout", type=float, default=420.0, help="전체 제한 시간(초)")
    parser.add_argument("--startup-timeout", type=float, default=240.0, help="서버가 READY 를 찍을 때까지(초)")
    args = parser.parse_args()

    players = args.players or DEFAULT_PLAYERS.get(args.scenario, 2)
    rtts = [int(value) for value in args.rtts.split(",")] if args.scenario == "chain_deadline" else []
    if args.scenario == "chain_deadline" and (args.mode != "dedicated" or players != 4 or len(rtts) != players):
        parser.error("chain_deadline 은 dedicated 4인에서만 돈다 (--rtts 도 4개)")
    if args.scenario == "chain_burst" and players > 4:
        parser.error("chain_burst 의 players 는 4 이하")
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
    # 체인 시나리오는 매 프레임 본다 — 남은 시간 0.05초에 누르고 한 왕복짜리 되돌림을 봐야 한다
    chain = args.scenario in CHAIN_SCENARIOS
    common = [
        "-gauntlet=AstralChainBurstTest" if chain else "-gauntlet=AstralPartyFlowTest", f"-gauntlet.tickrate={0 if chain else 0.2}",
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
                if rtts:
                    half = rtts[index] // 2  # 엔진 패킷 흉내 — 이 클라이언트의 보냄 · 받음에만 (서버는 그대로)
                    extra += [f"-PktLag={half}", f"-PktIncomingLagMin={half}", f"-PktIncomingLagMax={half}"]
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
    for name, pattern, expected_fn in {"flow": FLOW_COUNTS, "leader_leaves": LEADER_LEAVES_COUNTS, "raid_clear": RAID_CLEAR_COUNTS,
                                       "chain_burst": CHAIN_BURST_COUNTS}.get(args.scenario, []):
        expected = expected_fn(players)
        actual = len(re.findall(pattern, server_text))
        checks.append({"check": f"server log: {name}", "expected": expected, "actual": actual, "ok": actual == expected})
    if args.scenario == "enemy_combat":
        checks += enemy_combat_checks(procs)
    if args.scenario == "raid_clear" and procs:
        checks += raid_clear_checks(procs, players)
    deadline_table: list[dict] = []
    try:
        if args.scenario == "chain_burst" and procs:
            checks += chain_burst_checks(procs, players)
        if args.scenario == "chain_deadline" and procs:
            found, deadline_table = chain_deadline_checks(procs, players, {f"client{i + 1}": rtt for i, rtt in enumerate(rtts)})
            checks += found
    except (KeyError, ValueError, IndexError) as error:  # 중간에 끊긴 실행 — 줄이 모자라다. 위의 RESULT 검사가 이미 실패다
        checks.append({"check": "chain marks are complete", "expected": "all lines", "actual": repr(error), "ok": False})
    hard_travel = len(re.findall(r"Seamless travel is disabled", server_text))
    checks.append({"check": "server log: no hard-travel fallback", "expected": 0, "actual": hard_travel, "ok": hard_travel == 0})
    if failure:
        checks.append({"check": "run", "expected": "completed", "actual": failure, "ok": False})

    ok = all(check["ok"] for check in checks)
    summary = {
        "ok": ok, "mode": args.mode, "scenario": args.scenario, "players": players, "config": args.config,
        "elapsed_sec": round(time.time() - started, 1), "out_dir": str(out_dir),
        "checks": checks, "deadline": deadline_table,
        "exit_codes": {proc.name: proc.popen.returncode for proc in procs},
        "marks": {proc.name: [line[line.index(MARK):] for line in proc.marks] for proc in procs},
    }
    (out_dir / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    for check in checks:
        print(f"  {'ok  ' if check['ok'] else 'FAIL'} {check['check']}: expected {check['expected']}, got {check['actual']}")
    if deadline_table:
        print("\n  deadline (late = screen_left - server_left):")
        for row in sorted(deadline_table, key=lambda row: row["rtt_ms"]):
            print(f"    rtt {row['rtt_ms']:>3} ms  ping {row['ping_ms']:6.1f}  screen {row['screen_left']:.3f}  server {row['server_left']:+.3f}  late {row['late']:.3f}  joined {row['joined']}  ({row['proc']})")
    print(f"\n{'PASS' if ok else 'FAIL'} {args.mode}/{args.scenario} players={players} ({summary['elapsed_sec']}s) -> {out_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
