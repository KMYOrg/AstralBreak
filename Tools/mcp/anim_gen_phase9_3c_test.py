"""AI 애니 생성 Phase 9-3c — 섞은 세그먼트(U2-b: 운영 애니 + 생성) 실제 Kimodo · Blender · 에디터 통합 테스트
(Docs/AIAnimation/DevelopmentGuide.md §14 Phase 9 '9-3c' · FollowUpRoadmap.md §4 U2-b).

    D:/UE5Projects/AstralBreak/Tools/mcp/.venv/Scripts/python.exe -X utf8 -B -u D:/UE5Projects/AstralBreak/Tools/mcp/anim_gen_phase9_3c_test.py [--only ...]

뜬 에디터(AnimGraphMcp 플러그인) · 정책의 Kimodo venv · Blender 를 쓴다. anim_gen 은 같은 프로세스의 Service 로 부르고, 상태는
Saved/AnimGen/TestRuns/P93cRun<시각>/ 에, 새 애셋은 /Game/Animation/Test/AIAnimation/P93cRun<시각>/ 에만, 캡처는 Tools/mcp/results/capture/P93cRun<시각>/.
Kimodo 1건 ≈ RAM 15 GB — 생성 섹션은 순서대로 한 건씩.
섹션:
  hashes  — (맨 앞) 대상 스켈레톤 · 메시 · 운영 낫 Attack1 · Attack2 .uasset SHA-256 · Content/ git 상태 · 미저장 패키지 수
  plan    — (Kimodo 안 띄움 · 애셋 0 · 더티 0) M1 · M1c 계획: 사슬(key_pose → … → join → seams) · 생성 덩어리 프레임(겹침 포함) · 이음매 자동 키 ·
            timing 트림 끔 · join · seams 입력, M1c 는 key_pose 단계 없음 · 같은 프레임
  m1      — 표준 시험: [운영 낫 Attack1] → [생성 1.5초 swing] → [운영 낫 Attack2] · 후보 4(seed 20261101 ~ 04) · 파지 + 발 · 대상 간격 60 · fix.timing ·
            fix.body · weapon · 몽타주 섹션 "segments" · 캡처(낫 부착) — 이음매 키(seam_keys true)
  m1c     — 같은 요청 seam_keys false(크로스페이드만 대조)
  sword   — 9-2 남은 것: 검 세그먼트(9-2 와 같은 요청 · seed 20261025 ~ 28 · 보정 없이) + 베기 세그먼트에 Attack1 정점 전신 키(at 1.35초 · pass1)
            → 후보(시간 보정 전) 정점 · 동작 구간을 9-2 기록(세그먼트 196 · 한 프롬프트 294)과 비교
  compare — M1 ↔ M1c 이음매: 회전 단계 비 · 속도 변화 비 · 겹친 구간 자세 차 · 골반 잔차 · 키 추종, 기준값(시작값) 판정
  capture — M1 | M1c 같은 시각 비교 시트(이음매 둘레 8 행, 낫 부착) + APNG
  dirty   — (맨 뒤) 해시 불변 · 미저장 수 그대로 · Content/ 변경은 이번 실행 폴더뿐
요약은 Tools/mcp/anim_gen_phase9_3c_state.json(섹션 단위로 덮어쓴다 — 앞 실행의 다른 섹션은 남는다).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import statistics
import subprocess
import sys
import time

from anim_graph_mcp import bridge

STAMP = time.strftime("%m%d_%H%M%S")
ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P93cRun{STAMP}"
os.environ["ANIM_GEN_STATE_DIR"] = str(STATE_DIR)

from anim_gen import apng, motion_metrics, segments, timing  # noqa: E402
from anim_gen.service import Service  # noqa: E402
from anim_gen.store import Store  # noqa: E402

VESPER = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
VESPER_MESH_01 = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
ATTACK1 = "/Game/Animation/Hero/Vesper/Sickle/Actions/AS_Vesper_Sickle_Attack1"
ATTACK2 = "/Game/Animation/Hero/Vesper/Sickle/Actions/AS_Vesper_Sickle_Attack2"
WEAPON_MESH = "/Game/Equipment/Weapon/Mesh/SKM_Hero_Sickle"
RUN = f"/Game/Animation/Test/AIAnimation/P93cRun{STAMP}"
OUT = ROOT / "Tools" / "mcp" / "results" / "capture" / f"P93cRun{STAMP}"
HASHED = [VESPER, VESPER_MESH_01, ATTACK1, ATTACK2]
SICKLE_SEED = 20261101
SWORD_SEED = 20261025
GRIP_FLAGS = {"two_hand_weapon_grip": True, "foot_contact": True}
SPIN_PROMPT = ("A person holding a long-handled scythe with both hands spins around and slashes it horizontally, then returns to a fighting stance.")
M1_SEGMENTS = [{"source": "existing", "asset": ATTACK1, "name": "Attack1"},
               {"name": "Spin", "prompt": SPIN_PROMPT, "duration_seconds": 1.5, "swing": True},
               {"source": "existing", "asset": ATTACK2, "name": "Attack2"}]
SWORD_SEGMENTS = [   # 9-2 와 같은 표준 시험
    {"name": "Windup", "duration_seconds": 1.0, "prompt": "A person holds a sword with both hands and raises it over the right shoulder."},
    {"name": "Slash", "duration_seconds": 0.7, "swing": True, "prompt": "The person slashes the sword diagonally down to the left with both hands."},
    {"name": "Recover", "duration_seconds": 1.3, "prompt": "The person returns to a fighting stance holding the sword with both hands."}]
ATTACK1_PEAK_S = 0.317   # 9-3a timing.summary — 운영 낫 Attack1 휘두름 정점
SWORD_KEY_AT = 1.35      # 베기 세그먼트 [1.0, 1.7]초 가운데
# 기준값(사용자 결정 9-3c ④ — 시작값, 실측 뒤 확정)
LIMITS = {"rotation_step_ratio": 3.0, "overlap_gap_p50_cm": 2.0, "pelvis_residual_cm": 2.0}
BODY = ["hand_l", "hand_r", "thigh_l", "thigh_r", "foot_l", "foot_r", "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "head"]
SEAM_BONES = {"hand_l": "hand_l", "hand_r": "hand_r", "foot_l": "foot_l", "foot_r": "foot_r", "pelvis": "pelvis", "root": "root"}
FAILS: list[str] = []
STATE: dict = {"run": RUN, "state_dir": STATE_DIR.as_posix(), "out": OUT.as_posix()}
SERVICE = Service(store=Store(STATE_DIR))
STATE_FILE = ROOT / "Tools" / "mcp" / "anim_gen_phase9_3c_state.json"


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


def previous() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def sickle_weapon_request() -> dict:
    """Vesper 낫 요청 weapon — 8-1 · 9-3b 통합 시험과 같은 값(부착 = DA_WD_Sickle1 AttachOffset · 소켓 WeaponHandR, 보조 손 = 8-4 E0 선분)."""
    att = json.loads((ROOT / "Tools" / "mcp" / "results" / "p84_weapon_attach.json").read_text(encoding="utf-8"))
    ao = att["definition"]["attach_offset"]
    seg = json.loads((ROOT / "Tools" / "mcp" / "anim_gen_phase8_4_state.json").read_text(encoding="utf-8"))["e0"]["grip_proposal"]["segment"]
    return {"mesh": WEAPON_MESH, "attach": {"socket": att["socket"]["name"], "offset": {"location": ao["location"], "rotation": ao["rotation_pyr"], "scale": ao["scale"]}},
            "lead_hand": "right", "grips": [{"hand": "left", "segment": {"from": seg["from"], "to": seg["to"]}}]}


def m1_request(seam_keys: bool) -> dict:
    return {"target_skeleton": VESPER, "target_mesh": VESPER_MESH_01, "hero": "Vesper", "family": "Sickle",
            "animation_name": "AS_Vesper_Sickle_MixJoin" + ("" if seam_keys else "Ctl"),
            "description": f"9-3c 표준 시험 M1 — Attack1 → 생성 회전 베기 → Attack2 ({'이음매 키' if seam_keys else '크로스페이드만'})",
            "motion_category": "weapon_action", "loop": False, "provider": "local_ai", "segments": M1_SEGMENTS, "constraints": dict(GRIP_FLAGS),
            "generation": {"seed": SICKLE_SEED, "candidates": 4, "refine": {"grip": {"target_spacing_cm": 60.0}}, "seam_keys": seam_keys},
            "retarget": {"align_mode": "per_bone"}, "fix": {"timing": True, "body": True}, "weapon": sickle_weapon_request(),
            "review": {"capture": {"count": 8, "sequence": {"fps": 15}}}, "package": {"montage": {"sections": "segments"}}, "output_path": RUN}


def sword_request() -> dict:
    key = {"type": "key_pose", "asset": ATTACK1, "times": [ATTACK1_PEAK_S], "at": [SWORD_KEY_AT], "part": "full", "placement": "pass1"}
    return {"target_skeleton": VESPER, "target_mesh": VESPER_MESH_01, "hero": "Vesper", "family": "Sword", "animation_name": "AS_Vesper_Sword_SegSlashKey",
            "description": "9-3c 검 세그먼트 + Attack1 정점 키(9-2 남은 것)", "motion_category": "weapon_action", "loop": False, "frame_rate": 30,
            "provider": "local_ai", "constraints": dict(GRIP_FLAGS), "segments": SWORD_SEGMENTS,
            "generation": {"seed": SWORD_SEED, "candidates": 4, "transition_frames": 5, "constraints": [key]},
            "retarget": {"align_mode": "per_bone"}, "output_path": RUN}


def wait_job(job: dict, limit: float = 2400.0) -> dict:
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
    """Vesper 한 애셋 — timing.summary(휘두름 정점 · 정지 머리 / 꼬리 · 길이) · 동작 구간 비율 · 이음매(C++ 회전 단계 비 + 속도 변화 비) — 9-2 통합과 같은 정의."""
    params = {"assets": [asset], "skeleton": VESPER, "profile_bones": sorted(set(BODY) | set(SEAM_BONES.values())), "profile_positions": True}
    if seam_times:
        params["seams"] = seam_times
    item = must(editor("validate_animation", **params), f"measure {asset.rsplit('/', 1)[1]}")["assets"][0]
    n = item["numeric"]
    prof = n["profile"]
    scale = (n.get("pelvis_height_cm") or 100.0) / 100.0
    summ = timing.summary(prof, hands=("hand_l", "hand_r"), body=BODY, scale=scale, fps=float(n["frame_rate"]), length=float(n["length"]),
                          params=timing.normalize(True))
    sw = motion_metrics.swing(prof["position_cm"]["hand_l"], prof["position_cm"]["hand_r"], prof["times"], scale)
    rows = segments.speed_seams(prof["times"], {r: prof["speed_cm_s"].get(b) for r, b in SEAM_BONES.items() if prof["speed_cm_s"].get(b)},
                                seam_times, scale)
    cpp = {round(s["time"], 4): s.get("step_ratio") for s in ((item.get("request") or {}).get("seams") or [])}
    for row in rows:
        row["rotation_step_ratio"] = cpp.get(row["time"])
    return {"asset": asset, "status": item["status"], "length": summ["length"], "peak_cm_s": summ["peak_cm_s"], "peak_time": summ["peak_time"],
            "head_still_s": summ["head_still_s"], "tail_still_s": summ["tail_still_s"], "active_pct": sw["active_pct"],
            "rotation_step_ratio_max": segments.worst(rows, "rotation_step_ratio"), "speed_step_ratio_max": segments.worst(rows, "speed_step_ratio_max")}


def steps_of(cand: dict) -> dict:
    return {s["step"]: s for s in cand["steps"]}


def _median(values: list) -> float | None:
    v = [x for x in values if x is not None]
    return round(statistics.median(v), 2) if v else None


# ---- 섹션 ----
def section_hashes() -> None:
    print("== hashes · content · dirty (before)")
    STATE["hashes"] = {p: sha256(p) for p in HASHED}
    STATE["content_before"] = content_changes()
    STATE["dirty_before"] = dirty_count()
    print(f"   {len(HASHED)} assets hashed · Content changes before: {len(STATE['content_before'])} · dirty {STATE['dirty_before']}")


def section_plan() -> None:
    print("== plan — M1 · M1c (no Kimodo, no assets)")
    before = dirty_count()
    out = {}
    for keys in (True, False):
        tag = "m1" if keys else "m1c"
        plan = must(SERVICE.plan_motion_generation(request={**m1_request(keys), "provider": "auto"}), f"plan {tag}")
        cand = next((c for c in plan["candidates"] if c["provider"] == "local_ai"), None)
        if not check(cand is not None, f"{tag}: local_ai planned (excluded {[(e['provider'], e['reason']) for e in plan['excluded']]})"):
            continue
        kinds = [s["step"] for s in cand["steps"]]
        steps = steps_of(cand)
        g = steps["generate"]["inputs"]
        m = g["mixed"]
        want_frames = int(round(1.5 * 30)) + 1 + 2 * 4
        check(g["frames"] == want_frames and [s["name"] for s in g["segments"]] == ["Spin"] and m["overlap_frames"] == 4,
              f"{tag}: generated chunk {g['frames']} frames (1.5 s + 2 × 4 overlap) · overlap {m['overlap_frames']}")
        check(kinds.index("join") == kinds.index("seams") - 1 and kinds.index("body_fit") < kinds.index("join") and kinds.index("timing") < kinds.index("join"),
              f"{tag}: chain {kinds}")
        check(steps["timing"]["inputs"].get("seam_trim_off") == ["trim_head", "trim_tail"], f"{tag}: fix.timing keeps both seam ends (no still trim)")
        j = steps["join"]["inputs"]
        check([p["source"] for p in j["pieces"]] == ["existing", "generated", "existing"] and j["align"] == "pelvis" and j["bones"],
              f"{tag}: join pieces · pelvis alignment · bones {j['bones']}")
        excluded = {e["provider"]: e["reason"] for e in plan["excluded"]}
        check(excluded.get("existing_motion") == "SEGMENTS_UNSUPPORTED", f"{tag}: existing_motion excluded ({excluded})")
        rec = {"chain": kinds, "frames": g["frames"], "joined_length_s": m["joined_length_s"], "pieces": m["pieces"], "join_bones": j["bones"]}
        if keys:
            auto = {s["source"]: s for s in g["constraints"] if s.get("seam")}
            check(set(auto) == {"segments[0].seam", "segments[2].seam"} and auto["segments[0].seam"]["frame_indices"] == [0, 1, 2, 3, 4]
                  and auto["segments[2].seam"]["frame_indices"] == list(range(want_frames - 5, want_frames))
                  and auto["segments[0].seam"]["placement"] == "origin" and auto["segments[2].seam"]["placement"] == "pass1",
                  f"{tag}: seam keys {[(k, v['frame_indices'], v['placement']) for k, v in auto.items()]}")
            items = {i["source"]: i for i in steps["key_pose"]["inputs"]["items"]}
            check(items["segments[0].seam"]["source_frames"][-1] == 75 and items["segments[2].seam"]["source_frames"][0] == 0,
                  f"{tag}: key source frames Attack1 {items['segments[0].seam']['source_frames']} · Attack2 {items['segments[2].seam']['source_frames']}")
            check(g["key_pose"]["passes"] == 2 and g["diffusions"] == 4 * 2, f"{tag}: 2 passes · {g['diffusions']} diffusions")
            rec["seam_keys"] = {k: {"frames": v["frame_indices"], "placement": v["placement"], "times": v["times"]} for k, v in auto.items()}
        else:
            check(kinds[0] == "generate" and "key_pose" not in g, f"{tag}: no key_pose step (crossfade only)")
        out[tag] = rec
    check(dirty_count() == before, f"planning dirtied nothing ({before})")
    STATE["plan"] = out


def run_m1(keys: bool) -> None:
    tag = "m1" if keys else "m1c"
    print(f"== {tag} — Attack1 → generated spin (1.5 s) → Attack2 · seeds {SICKLE_SEED} ~ +3 · seam keys {keys}")
    plan, job, seconds = run_job(m1_request(keys), tag)
    rec = {"job_id": job["job_id"], "status": job["status"], "seconds": seconds}
    STATE[tag] = rec
    if job["status"] != "SUCCEEDED":
        rec["error"] = job.get("error")
        return
    values = job["cursor"]["values"]
    gen, sel, join, segs = values["generated"], job.get("selection") or {}, job.get("join") or {}, job.get("segments") or {}
    cap = (job.get("review") or {}).get("capture") or {}
    rec.update(final=job["generated_assets"][0], kimodo_seconds=gen.get("seconds"), picked=sel.get("picked"), join=join, segments=segs,
               timing={k: (job.get("timing") or {}).get(k) for k in ("applied", "rate", "recovery_rate", "cut", "warp", "swing_search_s", "length")},
               limitations=[lim["code"] for lim in job["limitations"]], capture={k: cap.get(k) for k in ("sheet", "animation", "attachments") if cap.get(k)},
               montage=(values.get("package") or {}).get("montage"))
    picked = (sel.get("picked") or {}).get("index", 0)
    gc = next((c for c in gen.get("candidates") or [] if c["index"] == picked), {})
    rec["key_follow"] = (gc.get("key_pose") or {}).get("follow")
    rec["key_placements"] = (gc.get("key_pose") or {}).get("placements")
    rec["final_measure"] = measure(rec["final"], [t for s in join.get("seams") or [] for t in s["window_s"]])
    print(f"   final {rec['final'].rsplit('/', 1)[1]}: length {rec['final_measure']['length']}s · picked {sel.get('picked')} · Kimodo {gen.get('seconds')}")
    for s in join.get("seams") or []:
        print(f"   seam {s['from']} → {s['to']} @ {s['window_s']}: yaw {s['yaw_deg']}° · shift {s['shift_cm']} cm · overlap gap {s['overlap_gap_cm']} · keyed {s['keyed']}")
    for r in segs.get("seams") or []:
        print(f"   {r.get('kind')} {r['time']}s: rotation ×{r.get('rotation_step_ratio')} · speed ×{r.get('speed_step_ratio_max')} · pelvis residual "
              f"{r.get('pelvis_residual_cm')} cm")
    if rec["key_follow"]:
        print(f"   key follow {[(f.get('part'), f.get('frames'), f.get('position_cm')) for f in rec['key_follow']]}")
    mon = rec["montage"] or {}
    check(bool(mon.get("sections")) and [s["name"] for s in mon["sections"]] == ["Attack1", "Spin", "Attack2"],
          f"{tag}: montage sections {[(s['name'], s['start']) for s in mon.get('sections') or []]}")
    check(len(join.get("seams") or []) == 2 and all(abs(s["anchor_s"] - w) < 1e-3 for s, w in zip(join["seams"], [p["joined_start_s"] for p in join["pieces"][1:]])),
          f"{tag}: Job join — 2 seams · pieces {[(p['label'], p['joined_start_s']) for p in join.get('pieces') or []]}")


def section_m1() -> None:
    run_m1(True)


def section_m1c() -> None:
    run_m1(False)


def section_sword() -> None:
    print(f"== sword — 9-2 sword segments + Attack1 peak key at {SWORD_KEY_AT}s · seeds {SWORD_SEED} ~ +3 (no fix)")
    plan, job, seconds = run_job(sword_request(), "sword")
    rec = {"job_id": job["job_id"], "status": job["status"], "seconds": seconds}
    STATE["sword"] = rec
    if job["status"] != "SUCCEEDED":
        rec["error"] = job.get("error")
        return
    values = job["cursor"]["values"]
    gen, sel = values["generated"], job["selection"]
    b = segments.plan_frames([s["duration_seconds"] for s in SWORD_SEGMENTS], 30.0)["boundaries_s"]
    rows = []
    for c in sorted(sel["candidates"], key=lambda c: c["index"]):
        src = next(s for s in gen["candidates"] if s["index"] == c["index"])
        v = measure(c["asset"], b)
        rows.append({"index": c["index"], "seed": c["seed"], "rank": c.get("rank"), "asset": c["asset"], "vesper": v,
                     "key_follow": (src.get("key_pose") or {}).get("follow")})
        print(f"   #{c['index']} seed {c['seed']} rank {c.get('rank')} · active {v['active_pct']}% · peak {v['peak_cm_s']} @ {v['peak_time']}s · seam rot "
              f"×{v['rotation_step_ratio_max']} speed ×{v['speed_step_ratio_max']} · key {[(f.get('position_cm') or {}).get('p50') for f in rows[-1]['key_follow'] or []]}")
    rec.update(final=job["generated_assets"][0], picked=sel["picked"], candidates=rows)
    p92 = json.loads((ROOT / "Tools" / "mcp" / "anim_gen_phase9_2_state.json").read_text(encoding="utf-8"))
    ref = {k: {c["seed"]: c["vesper"] for c in (p92.get(k) or {}).get("candidates") or []} for k in ("sword", "sword1")}
    table = []
    for r in rows:
        s, o = ref["sword"].get(r["seed"]) or {}, ref["sword1"].get(r["seed"]) or {}
        table.append({"seed": r["seed"], "peak_key": r["vesper"]["peak_cm_s"], "peak_seg": s.get("peak_cm_s"), "peak_one": o.get("peak_cm_s"),
                      "active_key": r["vesper"]["active_pct"], "active_seg": s.get("active_pct"), "active_one": o.get("active_pct"),
                      "seam_rot_key": r["vesper"]["rotation_step_ratio_max"], "seam_speed_key": r["vesper"]["speed_step_ratio_max"],
                      "seam_speed_seg": s.get("speed_step_ratio_max")})
    med = {k: _median([t[k] for t in table]) for k in (table[0] if table else {}) if k != "seed"}
    rec["vs_9_2"] = {"rows": table, "median": med}
    print(f"   median vs 9-2 (same seeds, before fix.timing): {json.dumps(med, ensure_ascii=False)}")
    check(all((t["seam_rot_key"] or 0) <= LIMITS["rotation_step_ratio"] for t in table), "sword: key run seam rotation step ≤ 3 on every candidate")


POSE_ROLES = ["pelvis", "thigh_l", "thigh_r", "hand_l", "hand_r", "foot_l", "foot_r", "head", "lowerarm_l", "lowerarm_r"]


def _rel_pose(pos: dict, i: int) -> dict:
    """골반 기준 · 몸 방향(엉덩 관절 선)을 맞춘 상대 위치 — 겹친 구간의 '자세' 차(골반 궤적 · 방향 제외)."""
    c, l, r = pos["pelvis"][i], pos["thigh_l"][i], pos["thigh_r"][i]
    h = -math.atan2(r[1] - l[1], r[0] - l[0])
    ch, sh = math.cos(h), math.sin(h)
    return {b: [(pos[b][i][0] - c[0]) * ch - (pos[b][i][1] - c[1]) * sh, (pos[b][i][0] - c[0]) * sh + (pos[b][i][1] - c[1]) * ch, pos[b][i][2]]
            for b in POSE_ROLES}


def seam_pose(run: str, job_id: str, name: str, overlap: int = 4) -> dict:
    """앞(Attack1 끝 ↔ 생성 처음) · 뒤(생성 끝 ↔ Attack2 처음) 겹친 구간의 골반 기준 자세 차(cm) — 생성 = 대상 쪽 보정 결과(join 직전). 생성 프레임 0 은
    표본이 없어 1 ~ K 만."""
    def prof(asset):
        item = must(editor("validate_animation", assets=[asset], checks=["numeric"], profile_bones=POSE_ROLES, profile_positions=True), "pose")["assets"][0]
        return item["numeric"]["profile"], float(item["numeric"]["length"])

    def near(times, t):
        return min(range(len(times)), key=lambda k: abs(times[k] - t))

    def gap(pa, pg, pairs):
        vals = sorted(math.dist(_rel_pose(pa["position_cm"], near(pa["times"], ta))[b], _rel_pose(pg["position_cm"], near(pg["times"], tg))[b])
                      for ta, tg in pairs for b in POSE_ROLES if b not in ("pelvis", "thigh_l", "thigh_r"))
        return {"p50": round(statistics.median(vals), 2), "max": round(vals[-1], 2)}
    (p1, l1), (p2, _) = prof(ATTACK1), prof(ATTACK2)
    pg, lg = prof(f"{run}/Work/{job_id}/A1/{name}_Body_Fit")
    return {"lead": gap(p1, pg, [(l1 - (overlap - i) / 30, i / 30) for i in range(1, overlap + 1)]),
            "trail": gap(p2, pg, [(i / 30, lg - (overlap - i) / 30) for i in range(1, overlap + 1)])}


def section_compare() -> None:
    print("== compare — M1 (seam keys) ↔ M1c (crossfade only)")
    prev = previous()
    m1, m1c = STATE.get("m1") or prev.get("m1"), STATE.get("m1c") or prev.get("m1c")
    if not check(bool(m1 and m1c and m1.get("join") and m1c.get("join")), "both M1 and M1c ran"):
        return
    out = {"seams": []}
    for a, c in zip(m1["join"]["seams"], m1c["join"]["seams"]):
        ra = [r for r in m1["segments"]["seams"] if r.get("seam") == a["index"]]
        rc = [r for r in m1c["segments"]["seams"] if r.get("seam") == c["index"]]
        row = {"seam": f"{a['from']} → {a['to']}", "overlap_gap_cm": [a["overlap_gap_cm"], c["overlap_gap_cm"]],
               "rotation_step_ratio": [segments.worst(ra, "rotation_step_ratio"), segments.worst(rc, "rotation_step_ratio")],
               "speed_step_ratio": [segments.worst(ra, "speed_step_ratio_max"), segments.worst(rc, "speed_step_ratio_max")],
               "pelvis_residual_cm": [segments.worst(ra, "pelvis_residual_cm"), segments.worst(rc, "pelvis_residual_cm")],
               "yaw_deg": [a["yaw_deg"], c["yaw_deg"]], "shift_cm": [a["shift_cm"], c["shift_cm"]]}
        out["seams"].append(row)
        print(f"   {row['seam']} (keys | crossfade): overlap gap {row['overlap_gap_cm'][0]} | {row['overlap_gap_cm'][1]} · rotation ×{row['rotation_step_ratio']} · "
              f"speed ×{row['speed_step_ratio']} · pelvis residual {row['pelvis_residual_cm']} cm · yaw {row['yaw_deg']} · shift {row['shift_cm']}")
        check((row["rotation_step_ratio"][0] or 0) <= LIMITS["rotation_step_ratio"], f"{row['seam']}: keyed seam rotation step ×{row['rotation_step_ratio'][0]} ≤ 3")
        check(((a["overlap_gap_cm"] or {}).get("p50") or 0) <= LIMITS["overlap_gap_p50_cm"],
              f"{row['seam']}: keyed overlap pose gap p50 {(a['overlap_gap_cm'] or {}).get('p50')} ≤ {LIMITS['overlap_gap_p50_cm']} cm")
        check((row["pelvis_residual_cm"][0] or 0) <= LIMITS["pelvis_residual_cm"], f"{row['seam']}: pelvis residual {row['pelvis_residual_cm'][0]} ≤ 2 cm")
        print(f"   {row['seam']}: speed change keyed {row['speed_step_ratio'][0]} vs crossfade {row['speed_step_ratio'][1]} (record — not worse is the aim)")
    run = (m1.get("final") or "").rsplit("/", 1)[0]
    poses = {tag: seam_pose(run, rec["job_id"], rec["final"].rsplit("/", 1)[1]) for tag, rec in (("m1", m1), ("m1c", m1c))}
    for side, row in zip(("lead", "trail"), out["seams"]):
        row["pose_gap_cm"] = [poses["m1"][side], poses["m1c"][side]]
        print(f"   {row['seam']}: pelvis-relative pose gap (keys | crossfade) {poses['m1'][side]} | {poses['m1c'][side]} (joined-coordinate gap above adds the "
              "pelvis path over the overlap)")
        check(poses["m1"][side]["p50"] <= LIMITS["overlap_gap_p50_cm"], f"{row['seam']}: keyed pelvis-relative pose gap p50 {poses['m1'][side]['p50']} ≤ "
              f"{LIMITS['overlap_gap_p50_cm']} cm")
    out["key_follow"] = m1.get("key_follow")
    out["final"] = {"m1": m1.get("final_measure"), "m1c": m1c.get("final_measure")}
    STATE["compare"] = out


def capture(out: pathlib.Path, asset: str, label: str, **params) -> dict:
    env = editor("capture_animation", asset=asset, mesh=VESPER_MESH_01, facing="+Y", output_dir=out.as_posix(), label=label,
                 attachments=[{"mesh": WEAPON_MESH, "socket": "WeaponHandR", "offset": sickle_weapon_request()["attach"]["offset"]}], **params)
    res = must(env, f"capture {asset}")
    seq = res.get("sequence") or {}
    if seq.get("frames"):
        res["animation"] = apng.assemble(seq["frames"], out / "animation.png", float(seq["fps"]))
    return res


def section_capture() -> None:
    print("== capture — M1 | M1c around the seams (same times, sickle attached) + APNG")
    before = dirty_count()
    prev = previous()
    m1, m1c = STATE.get("m1") or prev.get("m1"), STATE.get("m1c") or prev.get("m1c")
    if not check(bool(m1 and m1c and m1.get("join")), "both M1 and M1c ran"):
        return
    times = []
    for s in m1["join"]["seams"]:
        w = s["window_s"][0]
        times += [round(max(0.0, w - 0.2), 4), round(w, 4), round(s["window_s"][1], 4), round(w + 0.35, 4)]
    cc = capture(OUT / "m1c", m1c["final"], "crossfade only (seam_keys false)", times=times, sequence={"fps": 15})
    rows: dict[int, list[str]] = {}
    for f in sorted(cc["frames"], key=lambda f: (f["row"], f["view"] != "front")):
        rows.setdefault(f["row"], []).append(f["path"])
    c1 = capture(OUT / "m1", m1["final"], "seam keys", times=times, sequence={"fps": 15}, compare={"label": "crossfade only", "rows": [rows[r] for r in sorted(rows)]})
    check(bool(c1.get("compare")) and c1["cells_touching_edge"] == 0, f"compare sheet {(c1.get('compare') or {}).get('path')} · edge cells {c1['cells_touching_edge']}")
    STATE["capture"] = {"times": times, "compare": (c1.get("compare") or {}).get("path"), "m1_apng": (c1.get("animation") or {}).get("path"),
                        "m1c_apng": (cc.get("animation") or {}).get("path"), "m1_job_capture": m1.get("capture"), "m1c_job_capture": m1c.get("capture")}
    print(f"   {json.dumps(STATE['capture'], ensure_ascii=False)}")
    check(dirty_count() == before, f"captures dirtied nothing ({before})")


def section_dirty() -> None:
    print("== hashes · content · dirty (after)")
    if "hashes" in STATE:
        changed = [p for p, h in STATE["hashes"].items() if sha256(p) != h]
        check(not changed, f"target skeleton · mesh · Attack1 · Attack2 .uasset SHA-256 unchanged ({len(STATE['hashes'])} files) {changed}")
    if "dirty_before" in STATE:
        check(dirty_count() == STATE["dirty_before"], f"unsaved packages unchanged ({STATE['dirty_before']}) — every write was saved")
    if "content_before" in STATE:
        new = [p for p in content_changes() if p not in STATE["content_before"]]
        run_dir = "Content/" + RUN.removeprefix("/Game/") + "/"
        outside = [p for p in new if not p.startswith(run_dir)]
        print(f"   new Content changes {len(new)} (outside this run's folder: {outside})")
        check(not outside, "Content/ changes are only this run's folder")
        STATE["content_new"] = len(new)


SECTIONS = {"hashes": section_hashes, "plan": section_plan, "m1": section_m1, "m1c": section_m1c, "sword": section_sword, "compare": section_compare,
            "capture": section_capture, "dirty": section_dirty}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(SECTIONS), help="comma separated: " + ",".join(SECTIONS))
    args = ap.parse_args()
    t0 = time.time()
    names = [n.strip() for n in args.only.split(",")]
    for name in names:
        SECTIONS[name]()
    STATE["seconds"] = round(time.time() - t0, 1)
    merged = previous()
    merged.setdefault("runs", {})[STAMP] = {"sections": names, "failures": len(FAILS), "seconds": STATE["seconds"], "run": RUN}
    merged.update({k: v for k, v in STATE.items() if k not in ("seconds",)})
    STATE_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"state -> {STATE_FILE.as_posix()}")
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print("  - " + f)
    print("PASS" if not FAILS else "FAIL")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
