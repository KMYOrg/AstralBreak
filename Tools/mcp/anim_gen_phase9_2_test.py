"""AI 애니 생성 Phase 9-2 — 세그먼트(Kimodo 다중 프롬프트) 실제 Kimodo · Blender · 에디터 통합 테스트
(Docs/AIAnimation/DevelopmentGuide.md §14 Phase 9 '9-2' · FollowUpRoadmap.md §4 U2-a).

    D:/UE5Projects/AstralBreak/Tools/mcp/.venv/Scripts/python.exe -X utf8 -B -u D:/UE5Projects/AstralBreak/Tools/mcp/anim_gen_phase9_2_test.py [--only ...]

뜬 에디터(AnimGraphMcp 플러그인) · 정책의 Kimodo venv · Blender 를 쓴다. anim_gen 은 같은 프로세스의 Service 로 부르고, 상태는
Saved/AnimGen/TestRuns/P92Run<시각>/ 에, 새 애셋은 /Game/Animation/Test/AIAnimation/P92Run<시각>/ 에만, 캡처는 Tools/mcp/results/capture/P92Run<시각>/.
Kimodo 1건 ≈ RAM 15 GB — 생성 섹션은 순서대로 한 건씩.
섹션:
  hashes  — (맨 앞) 대상 스켈레톤 · 메시 .uasset SHA-256 · Content/ git 상태 · 미저장 패키지 수
  plan    — (Kimodo 안 띄움 · 애셋 0 · 더티 0) 두 표준 시험 계획: 사슬에 seams · 세그먼트 프레임 · 경계 · swing 창 · 기한 · 한계 SEGMENT_TRANSITIONS,
            다른 Provider 는 SEGMENTS_UNSUPPORTED, segments 없는 같은 요청은 seams · 창이 없다
  sword   — 검 '준비 → 베기 → 복귀' 3 세그먼트(1.0 · 0.7 · 1.3초, 베기 swing) · 후보 4 · 파지 · 발 · fix.timing · fix.body · 몽타주 섹션 "segments"
  sword1  — 같은 seed · 3.0초 한 프롬프트(8-1 표준 프롬프트) · 같은 fix(몽타주 없음)
  runstop — '달리기 → 멈춤 → 공격' 3 세그먼트(1.5 · 0.8 · 1.2초, 공격 swing) · 후보 4 · 파지 · 발 · fix.timing(swing 창)
  runstop1 — 같은 seed · 3.5초 한 프롬프트 · fix.timing
  sword_long · sword_quick — (판정 뒤 원인 가르기) 검 세그먼트 변형 — 길이 0.7 · 1.0 · 1.3초 · 베기 프롬프트 "quickly … in one fast motion",
            보정 없이(대조 = sword1)
  compare — 표준 시험마다 세그먼트 vs 한 프롬프트(같은 seed 후보끼리, 리타깃 뒤 · 시간 보정 전): 동작 구간 비율 · 휘두름 정점 · 정지 머리 / 꼬리 ·
            이음매(같은 시각 대조) · 같은 seed 1차 ↔ 2차 재현(구간별 전 관절 · 바닥 루트 — Kimodo venv 로 NPZ)
  capture — 고른 후보(세그먼트 | 한 프롬프트 비교 시트) · 세그먼트 최종(시간 보정 · 대상 쪽 보정 뒤) 캡처 + APNG
  dirty   — (맨 뒤) 해시 불변 · 미저장 수 그대로 · Content/ 변경은 이번 실행 폴더뿐
생성 섹션의 seed 는 --seed(기본 20261025 — Kimodo 는 결정적), 세그먼트 전이 프레임은 --transition(기본 5).
요약은 Tools/mcp/anim_gen_phase9_2_state.json(섹션 단위로 덮어쓴다 — 앞 실행의 다른 섹션은 남는다).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import statistics
import subprocess
import sys
import time

from anim_graph_mcp import bridge

STAMP = time.strftime("%m%d_%H%M%S")
ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P92Run{STAMP}"
os.environ["ANIM_GEN_STATE_DIR"] = str(STATE_DIR)

from anim_gen import apng, motion_metrics, segments, timing  # noqa: E402
from anim_gen.providers import local_ai  # noqa: E402
from anim_gen.service import Service  # noqa: E402
from anim_gen.store import Store  # noqa: E402

VESPER = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
VESPER_MESH_01 = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
RUN = f"/Game/Animation/Test/AIAnimation/P92Run{STAMP}"
OUT = ROOT / "Tools" / "mcp" / "results" / "capture" / f"P92Run{STAMP}"
HASHED = [VESPER, VESPER_MESH_01]
SEED = 20261025
TRANSITION = 5
FLAGS = {"two_hand_weapon_grip": True, "foot_contact": True}
# 표준 시험 — 세그먼트(swing = fix.timing 정점 탐색 창) · 같은 동작의 한 프롬프트(같은 길이)
SWORD_SEGMENTS = [
    {"name": "Windup", "duration_seconds": 1.0, "prompt": "A person holds a sword with both hands and raises it over the right shoulder."},
    {"name": "Slash", "duration_seconds": 0.7, "swing": True, "prompt": "The person slashes the sword diagonally down to the left with both hands."},
    {"name": "Recover", "duration_seconds": 1.3, "prompt": "The person returns to a fighting stance holding the sword with both hands."}]
SWORD_ONE = ("A person holds a sword with both hands, raises it over the right shoulder, slashes diagonally down to the left, "
             "then returns to a fighting stance.")   # 8-1 표준 프롬프트
RUN_SEGMENTS = [
    {"name": "Run", "duration_seconds": 1.5, "prompt": "A person runs forward holding a sword with both hands."},
    {"name": "Stop", "duration_seconds": 0.8, "prompt": "The person stops running and plants both feet, holding the sword with both hands."},
    {"name": "Attack", "duration_seconds": 1.2, "swing": True, "prompt": "The person slashes the sword diagonally down to the left with both hands."}]
RUN_ONE = ("A person runs forward holding a sword with both hands, stops and plants both feet, then slashes the sword diagonally down to the left "
           "with both hands.")
TESTS = {"sword": {"segments": SWORD_SEGMENTS, "one": SWORD_ONE, "name": "AS_Vesper_Sword_SegSlash", "fix": {"timing": True, "body": True},
                   "montage": True},
         "runstop": {"segments": RUN_SEGMENTS, "one": RUN_ONE, "name": "AS_Vesper_Sword_SegRunSlash", "fix": {"timing": True}, "montage": False}}
# 판정(검 세그먼트가 느리다) 뒤 원인 가르기 — 길이(베기 0.7 → 1.0초, 준비 1.0 → 0.7초) · 프롬프트(빠르게 · 한 동작으로). 비교는 시간 보정 전 후보라
# 시간 · 대상 쪽 보정 없이(빠르게), 대조 = sword1(같은 seed 한 프롬프트). plan 섹션은 건너뛴다
SWORD_QUICK = "The person quickly slashes the sword diagonally down to the left with both hands in one fast motion."
TESTS.update({
    "sword_long": {"segments": [{**SWORD_SEGMENTS[0], "duration_seconds": 0.7}, {**SWORD_SEGMENTS[1], "duration_seconds": 1.0}, SWORD_SEGMENTS[2]],
                   "one": SWORD_ONE, "one_key": "sword1", "name": "AS_Vesper_Sword_SegSlashLong", "fix": {}, "montage": False, "variant": True},
    "sword_quick": {"segments": [SWORD_SEGMENTS[0], {**SWORD_SEGMENTS[1], "prompt": SWORD_QUICK}, SWORD_SEGMENTS[2]],
                    "one": SWORD_ONE, "one_key": "sword1", "name": "AS_Vesper_Sword_SegSlashQuick", "fix": {}, "montage": False, "variant": True}})
RAN: list[str] = []   # 이 실행에서 생성한 시험 — compare · capture 는 이것만(없으면 전부)
# Vesper 측정 본 — 시간 보정 정지 판정(측정 역할 본 + 머리, timing_bones 와 같은 집합) · 이음매(손목 · 발목 · 골반 · 루트)
BODY = ["hand_l", "hand_r", "thigh_l", "thigh_r", "foot_l", "foot_r", "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "head"]
SEAM_BONES = {"hand_l": "hand_l", "hand_r": "hand_r", "foot_l": "foot_l", "foot_r": "foot_r", "pelvis": "pelvis", "root": "root"}
FAILS: list[str] = []
STATE: dict = {"run": RUN, "state_dir": STATE_DIR.as_posix(), "out": OUT.as_posix()}
SERVICE = Service(store=Store(STATE_DIR))
# 같은 seed 1차 ↔ 2차 재현 — Kimodo venv(numpy)로 NPZ 두 개를 구간별로 비교(cm). 0 = 첫 프레임 ~ 경계 ~ 끝
# 몸 = 엉덩 관절 · 발목 · 어깨 · 머리(kimodo_run.segment_follow 와 같은 집합 — 파지 제약이 옮기는 손 · 팔꿈치 · 손가락 제외), 손 = 손목
FOLLOW_SCRIPT = r"""
import json, sys
import numpy as np
from kimodo.skeleton.definitions import SOMASkeleton77
names = [n for n, _ in SOMASkeleton77.bone_order_names_with_parents]
body = [names.index(n) for n in ("LeftLeg", "RightLeg", "LeftFoot", "RightFoot", "LeftArm", "RightArm", "Head")]
hands = [names.index(n) for n in ("LeftHand", "RightHand")]
args = json.loads(sys.argv[1])
out = []
pct = lambda d, q: round(float(np.percentile(d, q)), 2)
for pair in args["pairs"]:
    a, b = np.load(pair["pass1"]), np.load(pair["final"])
    p1, p2 = a["posed_joints"] * 100.0, b["posed_joints"] * 100.0
    r1, r2 = a["smooth_root_pos"][:, [0, 2]] * 100.0, b["smooth_root_pos"][:, [0, 2]] * 100.0
    n = p1.shape[0]
    bounds = [0] + [int(round(t * args["fps"])) for t in args["windows"]] + [n]
    rows = []
    for s, e in zip(bounds, bounds[1:]):
        d = np.linalg.norm(p2[s:e] - p1[s:e], axis=-1)
        rr = np.linalg.norm(r2[s:e] - r1[s:e], axis=-1)
        rows.append({"frames": [s, e - 1], "joints_p95": pct(d, 95), "body_p50": pct(d[:, body], 50), "body_p95": pct(d[:, body], 95),
                     "hands_p95": pct(d[:, hands], 95), "root_xz_p95": pct(rr, 95), "root_xz_max": round(float(rr.max()), 2)})
    out.append({"seed": pair["seed"], "windows": rows})
print(json.dumps(out))
"""


def check(cond: bool, msg: str) -> bool:
    print(("[ ok ] " if cond else "[FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)
    return cond


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:3000]}")
        sys.exit(1)
    for d in env.get("diagnostics", []):
        print(f"   diag[{d['level']}] {d['code']}: {d['message'][:200]}")
    return env["result"]


def editor(tool: str, **params) -> dict:
    return bridge.call(tool, params, timeout=bridge.COMPILE_TIMEOUT)


def dirty_count() -> int:
    return must(editor("get_editor_status"), "status")["dirty_package_count"]


def uasset(path: str) -> pathlib.Path:
    return ROOT / "Content" / (path.removeprefix("/Game/") + ".uasset")


def sha256(path: str) -> str:
    return hashlib.sha256(uasset(path).read_bytes()).hexdigest()


def content_changes() -> list[str]:
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", "Content"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8").stdout
    return sorted(line[3:].strip().strip('"') for line in out.splitlines() if line.strip())


def request(test: str, segmented: bool, **overrides) -> dict:
    t = TESTS[test]
    req = {"target_skeleton": VESPER, "target_mesh": VESPER_MESH_01, "hero": "Vesper", "family": "Sword",
           "animation_name": t["name"] + ("" if segmented else "One"), "description": f"9-2 표준 시험 {test} ({'세그먼트' if segmented else '한 프롬프트'})",
           "motion_category": "weapon_action", "loop": False, "frame_rate": 30, "provider": "local_ai", "constraints": dict(FLAGS),
           "generation": {"seed": SEED, "candidates": 4, **({"transition_frames": TRANSITION} if segmented else {})},
           "retarget": {"align_mode": "per_bone"}, "fix": dict(t["fix"]), "output_path": RUN}
    if segmented:
        req["segments"] = t["segments"]
        if t["montage"]:
            req["package"] = {"montage": {"sections": "segments"}}
    else:
        req.update(prompt=t["one"], duration_seconds=sum(s["duration_seconds"] for s in t["segments"]))
    req.update(overrides)
    return req


def boundaries(test: str) -> list[float]:
    return segments.plan_frames([s["duration_seconds"] for s in TESTS[test]["segments"]], 30.0)["boundaries_s"]


def wait_job(job: dict, limit: float = 1800.0) -> dict:
    t0 = time.time()
    while job["status"] == "RUNNING" and time.time() - t0 < limit:
        time.sleep(1.0)
        env = SERVICE.get_generation_status(job_id=job["job_id"])
        job = env["result"] if env["ok"] else env["error"]["details"].get("job", job)
    return job


def run_job(req: dict, label: str) -> tuple[dict, dict, float]:
    plan = must(SERVICE.plan_motion_generation(request=req), f"plan {label}")
    t0 = time.time()
    job = wait_job(must(SERVICE.generate_motion(plan_id=plan["plan_id"], save=True), f"generate {label}"))
    seconds = round(time.time() - t0, 1)
    check(job["status"] == "SUCCEEDED", f"{label} job {job['status']} ({seconds}s)")
    if job["status"] != "SUCCEEDED":
        print(f"   error {json.dumps(job.get('error'), ensure_ascii=False)[:2000]}")
    return plan, job, seconds


def measure(asset: str, seam_times: list[float]) -> dict:
    """Vesper 한 애셋 — 시간 보정과 같은 정의(timing.summary: 휘두름 정점 · 정점 시각 · 정지 머리 / 꼬리 · 길이) · 동작 구간 비율(motion_metrics.swing
    active_pct) · 이음매(C++ 회전 단계 비 + 속도 앞뒤 비 · 속도 변화 비 — segments.speed_seams, 이음매가 없는 클립이면 같은 시각 대조군)."""
    params = {"assets": [asset], "skeleton": VESPER, "profile_bones": sorted(set(BODY) | set(SEAM_BONES.values())), "profile_positions": True}
    if seam_times:
        params["seams"] = seam_times
    item = must(editor("validate_animation", **params), f"measure {asset.rsplit('/', 1)[1]}")["assets"][0]
    n = item["numeric"]
    prof = n["profile"]
    scale = (n.get("pelvis_height_cm") or 100.0) / 100.0
    summ = timing.summary(prof, hands=("hand_l", "hand_r"), body=BODY, scale=scale, fps=float(n["frame_rate"]), length=float(n["length"]),
                          params=timing.normalize(True))
    pos = prof["position_cm"]
    sw = motion_metrics.swing(pos["hand_l"], pos["hand_r"], prof["times"], scale)
    rows = segments.speed_seams(prof["times"], {r: prof["speed_cm_s"].get(b) for r, b in SEAM_BONES.items() if prof["speed_cm_s"].get(b)},
                                seam_times, scale)
    cpp = {round(s["time"], 4): s.get("step_ratio") for s in ((item.get("request") or {}).get("seams") or [])}
    for row in rows:
        row["rotation_step_ratio"] = cpp.get(row["time"])
    return {"asset": asset, "status": item["status"], "length": summ["length"], "peak_cm_s": summ["peak_cm_s"], "peak_time": summ["peak_time"],
            "head_still_s": summ["head_still_s"], "tail_still_s": summ["tail_still_s"], "active_pct": sw["active_pct"],
            "rotation_step_ratio_max": segments.worst(rows, "rotation_step_ratio"), "speed_step_ratio_max": segments.worst(rows, "speed_step_ratio_max"),
            "seams": rows}


def follow(pairs: list[dict], windows: list[float]) -> list[dict]:
    python, _ = local_ai.KimodoProvider.paths(SERVICE.policy())
    out = subprocess.run([str(python), "-I", "-c", FOLLOW_SCRIPT, json.dumps({"pairs": pairs, "windows": windows, "fps": 30.0})], capture_output=True,
                         text=True, encoding="utf-8", timeout=300)
    if out.returncode != 0:
        print(f"[FAIL] follow script: {out.stderr[-1500:]}")
        FAILS.append("follow script")
        return []
    return json.loads(out.stdout)


def steps_of(cand: dict) -> dict:
    return {s["step"]: s for s in cand["steps"]}


# ---- 섹션 ----
def section_hashes() -> None:
    print("== hashes · content · dirty (before)")
    STATE["hashes"] = {p: sha256(p) for p in HASHED}
    STATE["content_before"] = content_changes()
    STATE["dirty_before"] = dirty_count()
    print(f"   {len(HASHED)} assets hashed · Content changes before: {len(STATE['content_before'])} · dirty {STATE['dirty_before']}")


def section_plan() -> None:
    print("== plan — segments plans (no Kimodo, no assets)")
    before = dirty_count()
    out = {}
    for test in [t for t in TESTS if not TESTS[t].get("variant")]:
        b = boundaries(test)
        plan = must(SERVICE.plan_motion_generation(request=request(test, True, provider="auto")), f"plan {test}")
        cand = next((c for c in plan["candidates"] if c["provider"] == "local_ai"), None)
        check(cand is not None, f"{test}: local_ai candidate planned")
        if cand is None:
            continue
        steps = steps_of(cand)
        g = steps["generate"]["inputs"]
        kinds = [s["step"] for s in cand["steps"]]
        segs = TESTS[test]["segments"]
        check(g["boundaries_s"] == b and [s["frames"] for s in g["segments"]] == segments.plan_frames([s["duration_seconds"] for s in segs], 30.0)["frames"]
              and g["frames"] == sum(s["frames"] for s in g["segments"]) and g["transition_frames"] == TRANSITION and g["prompt"] is None,
              f"{test}: generate pins {len(segs)} prompts · frames {[s['frames'] for s in g['segments']]} = {g['frames']} · boundaries {g['boundaries_s']}")
        check(kinds.index("seams") == kinds.index("validate") - 1 and "select" in kinds, f"{test}: chain {kinds}")
        check(steps["timing"]["inputs"].get("swing_window_s") == g["swing_window_s"] and g["swing_window_s"],
              f"{test}: fix.timing searches the swing segment {g['swing_window_s']}s")
        check(g["diffusions"] == 4 * 2 * len(segs) and g["timeout_extra_s"] == local_ai.DIFFUSION_EXTRA_S * (g["diffusions"] - 1),
              f"{test}: deadline counts {g['diffusions']} diffusions (+{g['timeout_extra_s']}s)")
        excluded = {e["provider"]: e["reason"] for e in plan["excluded"]}
        # 정책 · 설치로 먼저 빠진 Provider(유료 차단 등)는 그 이유 그대로 — 사슬까지 온 Provider 만 SEGMENTS_UNSUPPORTED
        check(excluded.get("existing_motion") == "SEGMENTS_UNSUPPORTED" and len(plan["candidates"]) == 1 and "SEGMENT_TRANSITIONS" in
              {lim["code"] for lim in cand["expected_limitations"]}, f"{test}: only local_ai plans — excluded {excluded} · SEGMENT_TRANSITIONS")
        one = must(SERVICE.plan_motion_generation(request=request(test, False)), f"plan {test}1")
        osteps = steps_of(one["candidates"][0])
        check("seams" not in osteps and "swing_window_s" not in osteps["timing"]["inputs"] and "segments" not in osteps["generate"]["inputs"],
              f"{test}1 (one prompt): no seams step · no swing window · no segments")
        out[test] = {"boundaries_s": b, "frames": [s["frames"] for s in g["segments"]], "swing_window_s": g["swing_window_s"], "chain": kinds,
                     "diffusions": g["diffusions"], "timeout_extra_s": g["timeout_extra_s"], "seams_inputs": steps["seams"]["inputs"]}
    check(dirty_count() == before, f"planning dirtied nothing ({before})")
    STATE["plan"] = out


def seg_suffix() -> str:
    """전이 프레임이 기본(5)이 아니면 세그먼트 기록 키에 _t<N> — 기본 실행 기록을 덮지 않는다(한 프롬프트 대조는 전이와 무관)."""
    return "" if TRANSITION == segments.TRANSITION_DEFAULT else f"_t{TRANSITION}"


def run_test(test: str, segmented: bool) -> None:
    key = (test + seg_suffix()) if segmented else test + "1"
    RAN.append(test)
    print(f"== {key} — {'segments' if segmented else 'one prompt'} · seeds {SEED} ~ {SEED + 3}")
    plan, job, seconds = run_job(request(test, segmented), key)
    rec = {"job_id": job["job_id"], "status": job["status"], "seconds": seconds}
    STATE[key] = rec
    if job["status"] != "SUCCEEDED":
        rec["error"] = job.get("error")
        return
    values = job["cursor"]["values"]
    gen, sel = values["generated"], job["selection"]
    b = boundaries(test)
    rec.update(final=job["generated_assets"][0], kimodo_seconds=gen["seconds"], picked=sel["picked"], timing=job.get("timing"),
               limitations=[lim["code"] for lim in job["limitations"]], review=job.get("review"))
    cands = []
    for c in sorted(sel["candidates"], key=lambda c: c["index"]):
        src = next(s for s in gen["candidates"] if s["index"] == c["index"])
        m2 = src["source_metrics"].get("pass2") or src["source_metrics"]["pass1"]
        v = measure(c["asset"], b)
        row = {"index": c["index"], "seed": c["seed"], "rank": c.get("rank"), "score": c.get("score"), "asset": c["asset"], "vesper": v,
               "source": {"active_pct": (m2.get("swing") or {}).get("active_pct"), "peak_cm_s": (m2.get("swing") or {}).get("peak_cm_s"),
                          "grip_pct": (m2.get("grip") or {}).get("grip_pct")},
               "npz": src.get("npz"), "pass1_npz": src.get("pass1_npz"), "kimodo_segments": src.get("segments")}
        cands.append(row)
        ks = src.get("segments") or {}
        print(f"   #{c['index']} seed {c['seed']} rank {c.get('rank')} · Vesper active {v['active_pct']}% · peak {v['peak_cm_s']} @ {v['peak_time']}s · still "
              f"head {v['head_still_s']} / tail {v['tail_still_s']}s · seam rot ×{v['rotation_step_ratio_max']} speed ×{v['speed_step_ratio_max']}"
              + (f" · Kimodo seam rot ×{ks.get('rotation_step_ratio_max')} speed ×{ks.get('speed_step_ratio_max')}" if ks else ""))
    rec["candidates"] = cands
    final = measure(rec["final"], (job.get("segments") or {}).get("boundaries_s") or [] if segmented else [])
    rec["final_measure"] = final
    tm = job.get("timing") or {}
    print(f"   final {rec['final'].rsplit('/', 1)[1]}: length {final['length']}s · peak {final['peak_cm_s']} · tail {final['tail_still_s']}s · timing "
          f"{tm.get('applied')} rate {tm.get('rate')} search {tm.get('swing_search_s')} · Kimodo {gen['seconds']}")
    if not segmented:
        return
    segs = job.get("segments") or {}
    rec["segments"] = segs
    check(gen.get("segments", {}).get("boundaries_s") == b and gen["segments"]["transition_frames"] == TRANSITION,
          f"{key}: Kimodo ran {gen.get('segments', {}).get('count')} prompts · boundaries {gen.get('segments', {}).get('boundaries_s')}")
    check(all((r["kimodo_segments"] or {}).get("follow") for r in cands), f"{key}: every candidate records pass 1 ↔ 2 per segment")
    check(segs.get("boundaries_generated_s") == b and segs.get("seams") and len(segs["seams"]) == len(b),
          f"{key}: Job segments — generated {segs.get('boundaries_generated_s')} → final {segs.get('boundaries_s')} ({segs.get('map')})")
    limit = segments.SEAM_RATIO_MAX
    for r in cands:
        v = r["vesper"]
        check((v["rotation_step_ratio_max"] or 0) <= limit, f"{key} #{r['index']}: candidate seam rotation step ×{v['rotation_step_ratio_max']} ≤ {limit:g}")
    check((segs.get("rotation_step_ratio_max") or 0) <= limit, f"{key}: final seam rotation step ×{segs.get('rotation_step_ratio_max')} ≤ {limit:g} (SEAM_JUMP)")
    print(f"   final seam speed change ×{segs.get('speed_step_ratio_max')} (record — candidates "
          f"{[r['vesper']['speed_step_ratio_max'] for r in cands]})")
    if tm.get("applied"):
        win = tm.get("swing_search_s") or []
        check(bool(win) and win[0] - 1e-6 <= (tm.get("signal") or {}).get("peak_time", -1) <= win[1] + 1e-6,
              f"{key}: fix.timing peak {(tm.get('signal') or {}).get('peak_time')}s inside the swing window {win}")
    if TESTS[test]["montage"]:
        mon = (values.get("package") or {}).get("montage") or {}
        want = segs.get("sections") or []
        got = mon.get("sections") or []
        check(bool(want) and [(s["name"], round(s["start"], 3), s.get("next")) for s in got] == [(s["name"], round(s["start"], 3), s.get("next")) for s in want]
              and [s["start"] for s in want[1:]] == [t for t in segs["boundaries_s"] if t > 0][:len(want) - 1],
              f"{key}: montage {mon.get('asset', '?').rsplit('/', 1)[-1]} sections {[(s['name'], s['start'], s.get('next')) for s in got]} at the mapped boundaries")
        rec["montage"] = mon


def section_sword() -> None:
    run_test("sword", True)


def section_sword1() -> None:
    run_test("sword", False)


def section_runstop() -> None:
    run_test("runstop", True)


def section_runstop1() -> None:
    run_test("runstop", False)


def section_sword_long() -> None:
    run_test("sword_long", True)


def section_sword_quick() -> None:
    run_test("sword_quick", True)


def _median(values: list) -> float | None:
    v = [x for x in values if x is not None]
    return round(statistics.median(v), 2) if v else None


def section_compare() -> None:
    print("== compare — segments vs one prompt (same seeds · candidates before fix.timing)")
    saved = ROOT / "Tools" / "mcp" / "anim_gen_phase9_2_state.json"
    previous = json.loads(saved.read_text(encoding="utf-8")) if saved.is_file() else {}
    out = {}
    for test in [t for t in TESTS if not RAN or t in RAN]:
        seg_key, one_key = test + seg_suffix(), TESTS[test].get("one_key", test + "1")
        seg, one = STATE.get(seg_key) or previous.get(seg_key), STATE.get(one_key) or previous.get(one_key)
        if not (seg and one and seg.get("candidates") and one.get("candidates")):
            check(False, f"{test}: both runs needed (sections {test} · {test}1)")
            continue
        b = boundaries(test)
        rows = []
        for s in seg["candidates"]:
            o = next((x for x in one["candidates"] if x["seed"] == s["seed"]), None)
            if o is None:
                continue
            rows.append({"seed": s["seed"], **{f"{k}_{tag}": r["vesper"][k] for tag, r in (("seg", s), ("one", o))
                                                for k in ("active_pct", "peak_cm_s", "peak_time", "head_still_s", "tail_still_s", "rotation_step_ratio_max",
                                                          "speed_step_ratio_max")},
                         "source_active_seg": s["source"]["active_pct"], "source_active_one": o["source"]["active_pct"],
                         "grip_seg": s["source"]["grip_pct"], "grip_one": o["source"]["grip_pct"]})
        for r in rows:
            print(f"   seed {r['seed']}: active {r['active_pct_one']} → {r['active_pct_seg']}% · peak {r['peak_cm_s_one']} → {r['peak_cm_s_seg']} cm/s · tail "
                  f"{r['tail_still_s_one']} → {r['tail_still_s_seg']}s · head {r['head_still_s_one']} → {r['head_still_s_seg']}s · seam rot ×"
                  f"{r['rotation_step_ratio_max_one']} → ×{r['rotation_step_ratio_max_seg']} · speed ×{r['speed_step_ratio_max_one']} → "
                  f"×{r['speed_step_ratio_max_seg']}")
        med = {k: _median([r[k] for r in rows]) for k in (rows[0] if rows else {}) if k != "seed"}
        print(f"   median: {json.dumps(med, ensure_ascii=False)}")
        # 같은 seed 1차 ↔ 2차 재현 — 같은 구간(경계)으로 두 실행 모두
        pairs = lambda run: [{"seed": c["seed"], "pass1": c["pass1_npz"], "final": c["npz"]} for c in run["candidates"] if c.get("pass1_npz")]  # noqa: E731
        fs, fo = follow(pairs(seg), b), follow(pairs(one), b)
        for a, z in zip(fs, fo):
            print(f"   pass 1 ↔ 2 seed {a['seed']}: body p95 segments {[w['body_p95'] for w in a['windows']]} | one {[w['body_p95'] for w in z['windows']]} · "
                  f"hands p95 {[w['hands_p95'] for w in a['windows']]} | {[w['hands_p95'] for w in z['windows']]} · root p95 "
                  f"{[w['root_xz_p95'] for w in a['windows']]} | {[w['root_xz_p95'] for w in z['windows']]} cm")
        for tag, f in (("segments", fs), ("one", fo)):
            med[f"follow_body_p95_{tag}"] = _median([w["body_p95"] for x in f for w in x["windows"]])
            med[f"follow_hands_p95_{tag}"] = _median([w["hands_p95"] for x in f for w in x["windows"]])
            med[f"follow_root_p95_{tag}"] = _median([w["root_xz_p95"] for x in f for w in x["windows"]])
        print(f"   pass 1 ↔ 2 median body {med['follow_body_p95_segments']} | {med['follow_body_p95_one']} · hands {med['follow_hands_p95_segments']} | "
              f"{med['follow_hands_p95_one']} · root {med['follow_root_p95_segments']} | {med['follow_root_p95_one']} cm (segments | one prompt)")
        out[test] = {"boundaries_s": b, "rows": rows, "median": med, "follow_segments": fs, "follow_one": fo,
                     "picked": {"segments": (seg.get("picked") or {}).get("seed"), "one": (one.get("picked") or {}).get("seed")},
                     "final": {"segments": seg.get("final_measure"), "one": one.get("final_measure")}}
        check(len(rows) == len(seg["candidates"]), f"{test}: {len(rows)} same-seed pairs compared")
    STATE["compare" + seg_suffix()] = out


def capture(out: pathlib.Path, asset: str, label: str, **params) -> dict:
    env = editor("capture_animation", asset=asset, mesh=VESPER_MESH_01, facing="+Y", output_dir=out.as_posix(), label=label, **params)
    res = must(env, f"capture {asset}")
    seq = res.get("sequence") or {}
    if seq.get("frames"):
        res["animation"] = apng.assemble(seq["frames"], out / "animation.png", float(seq["fps"]))
    return res


def section_capture() -> None:
    print("== captures — picked candidate segments | one prompt (same times) · segments final (+ APNG)")
    before = dirty_count()
    saved = ROOT / "Tools" / "mcp" / "anim_gen_phase9_2_state.json"
    previous = json.loads(saved.read_text(encoding="utf-8")) if saved.is_file() else {}
    caps = {}
    for test in [t for t in TESTS if not RAN or t in RAN]:
        seg_key, one_key = test + seg_suffix(), TESTS[test].get("one_key", test + "1")
        seg, one = STATE.get(seg_key) or previous.get(seg_key), STATE.get(one_key) or previous.get(one_key)
        if not (seg and one and seg.get("candidates") and one.get("candidates")):
            check(False, f"{test}: both runs needed for the capture")
            continue
        pick = (seg.get("picked") or {}).get("seed")
        s = next(c for c in seg["candidates"] if c["seed"] == pick)
        o = next(c for c in one["candidates"] if c["seed"] == pick)
        length = s["vesper"]["length"]
        times = [round(i * length / 7, 4) for i in range(8)]
        oc = capture(OUT / test / "one", o["asset"], f"one prompt seed {pick}", times=times, sequence={"fps": 15})
        by_row: dict[int, list[str]] = {}
        for f in sorted(oc["frames"], key=lambda f: (f["row"], f["view"] != "front")):
            by_row.setdefault(f["row"], []).append(f["path"])
        sc = capture(OUT / test / "segments", s["asset"], f"segments seed {pick}", times=times, sequence={"fps": 15},
                     compare={"label": "one prompt", "rows": [by_row[r] for r in sorted(by_row)]})
        fc = capture(OUT / test / "final", seg["final"], "segments final", count=8, sequence={"fps": 15})
        check(bool(sc.get("compare")) and sc["cells_touching_edge"] == 0 and fc["cells_touching_edge"] == 0,
              f"{test}: segments | one prompt compare sheet ({(sc.get('compare') or {}).get('size')}) · final sheet · edge cells "
              f"{sc['cells_touching_edge']} / {fc['cells_touching_edge']}")
        caps[test] = {"seed": pick, "times": times, "compare": (sc.get("compare") or {}).get("path"), "segments_apng": (sc.get("animation") or {}).get("path"),
                      "one_apng": (oc.get("animation") or {}).get("path"), "final_sheet": fc["sheet"], "final_apng": (fc.get("animation") or {}).get("path")}
        print(f"   {test}: {json.dumps(caps[test], ensure_ascii=False)}")
    check(dirty_count() == before, f"captures dirtied nothing ({before})")
    STATE["capture" + seg_suffix()] = caps


def section_dirty() -> None:
    print("== hashes · content · dirty (after)")
    if "hashes" in STATE:
        changed = [p for p, h in STATE["hashes"].items() if sha256(p) != h]
        check(not changed, f"target skeleton · mesh .uasset SHA-256 unchanged ({len(STATE['hashes'])} files) {changed}")
    if "dirty_before" in STATE:
        check(dirty_count() == STATE["dirty_before"], f"unsaved packages unchanged ({STATE['dirty_before']}) — every write was saved")
    if "content_before" in STATE:
        new = [p for p in content_changes() if p not in STATE["content_before"]]
        run_dir = "Content/" + RUN.removeprefix("/Game/") + "/"
        outside = [p for p in new if not p.startswith(run_dir)]
        print(f"   new Content changes {len(new)} (outside this run's folder: {outside})")
        check(not outside, "Content/ changes are only this run's folder")
        STATE["content_new"] = len(new)


SECTIONS = {"hashes": section_hashes, "plan": section_plan, "sword": section_sword, "sword1": section_sword1, "runstop": section_runstop, "runstop1": section_runstop1,
            "sword_long": section_sword_long, "sword_quick": section_sword_quick,
            "compare": section_compare, "capture": section_capture, "dirty": section_dirty}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(SECTIONS), help="comma separated: " + ",".join(SECTIONS))
    ap.add_argument("--seed", type=int, default=SEED, help=f"first seed (default {SEED})")
    ap.add_argument("--transition", type=int, default=TRANSITION, help=f"segments transition frames (default {TRANSITION})")
    args = ap.parse_args()
    globals().update(SEED=args.seed, TRANSITION=args.transition)
    STATE.update(seed=args.seed, transition=args.transition)
    t0 = time.time()
    names = [n.strip() for n in args.only.split(",")]
    for name in names:
        SECTIONS[name]()
    STATE["seconds"] = round(time.time() - t0, 1)
    out = ROOT / "Tools" / "mcp" / "anim_gen_phase9_2_state.json"
    try:
        merged = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        merged = {}
    merged.setdefault("runs", {})[STAMP] = {"sections": names, "failures": len(FAILS), "seconds": STATE["seconds"], "run": RUN, "seed": args.seed,
                                            "transition": args.transition}
    merged.update({k: v for k, v in STATE.items() if k not in ("seconds",)})
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"state -> {out.as_posix()}")
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print("  - " + f)
    print("PASS" if not FAILS else "FAIL")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
