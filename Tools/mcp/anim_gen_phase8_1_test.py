"""AI 애니 생성 Phase 8-1 — 생성 품질(제약 변환 · 후보 선별 · 관통-파지) 실제 Kimodo · Blender · 에디터 통합 테스트
(Docs/AIAnimation/DevelopmentGuide.md §14 Phase 8).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase8_1_test.py [--only ...]

뜬 에디터(AnimGraphMcp 플러그인) · 정책의 Kimodo venv · Blender 를 쓴다. anim_gen 은 같은 프로세스의 Service 로 부르고, 상태는
Saved/AnimGen/TestRuns/P81Run<시각>/ 에 격리한다. 기준 = Kimodo 칼 휘두르기 시험(2026-10-25, seed 20261025 — 사용자 판정 "다리가 많이 벌어지고
베기가 흐느적") 의 유지 애셋 KimodoSword1025_185815/AS_Vesper_Sword_KimodoSlash(body_clearance resolve). Kimodo 1건 ≈ RAM 15 GB — 섹션은 순서대로
한 건씩만 돌린다.
섹션:
  hashes — (맨 앞) 유지 애셋 · 대상 스켈레톤 · 메시 .uasset SHA-256 · Content/ git 상태 · 미저장 패키지 수
  exp1   — 첫 실험 E1: 기준 시험과 같은 요청 + retarget.body_clearance measure → 유지 애셋(resolve)과 같은 profile 로 손목 간격 · 왼 손목 이동 ·
           위팔 방향 차 · 관통을 비교해 "보정이 파지를 깼다 / 파지 없음" 을 판정하고, 관통이 기록의 보정 전 값과 같으면 같은 seed 결정성도 확인
  plan   — 플래그 · 후보 계획: 2차 생성 규칙 · seed 목록 · 기한 · select 단계 · 한계 교체 · 관통 measure — Kimodo 안 띄움 · 애셋 0 · 더티 0.
           플래그 · 후보가 없으면 사슬 · 관통 기본값이 개정 10 과 같다
  refine — E2 ①: 같은 프롬프트 + two_hand_weapon_grip · foot_contact · meet, 후보 1(seed 20261025) → 소스(1 → 2차)와 Vesper 양쪽 파지 · 접지 발 ·
           비파지 관통 상한 · 최종 = 잰 후보
  lead   — E2': ① 과 같은 seed, grip.target lead (비교용)
  select — E2 ②: 후보 4(seed 20261025 ~ 28) → 전부 Vesper 리타깃 · 측정 → 점수로 하나, 기록한 수치로 다시 계산하면 같은 선택.
           수정안 A · B · C(2026-10-26 Persona 소견 후) 뒤로는 후보마다 떨림(소스 2차 스무딩 전 → 후 · Vesper) · 보조 손목 굽힘(소스 1 → 2차 ·
           Vesper) · 궤적 폭 · 접지 발 미끄러짐도 출력한다
  recompute — (애셋 0) 기록 Job job_20261026_154723_c49a83(수정 전 E2 ②)의 후보 4개를 지금 제품 측정(candidate_metrics) · 점수(selection)로 다시
           잰다 — 새 점수식이 seed 20261025 를 고르는지
  regrip — (애셋 0) 낫 기록 Job job_20261026_192555_f991aa(생성 간격 60 — 버전 4 띠 × pelvis scale 로 FAIL 2)의 후보 4개를 버전 5 파지 띠(간격 사상
           — 대상 = 대상 어깨 관절 폭 + 팔 길이 비 × (생성 − 생성 어깨 폭))로 다시 잰다: 고른 후보가 띠 안 ≥ 80 % · 사상이 Vesper 간격 p50 을 맞히는지
  scythe — 낫 기준(Vesper 근접 무기 = 낫): 같은 seed 4개 · 프롬프트 'long-handled scythe' · 대상 기준 간격 60 cm(target_spacing_cm — 운영 낫 애니
           양손 구간 p50 54.8 ~ 66.2 의 가운데 아래쪽, 생성 ≈ 75 cm) → Vesper 파지 띠 60 ± 13 × 팔 길이 비, 운영 낫 애니 4개를 같은 측정으로 비교
           (손목 간격 · 양손 구간 · 궤적 폭 · 손 겹침 · 꼬임 · 머리 근접 · 관통). SOMA 치수 상수가 이 실행 BVH 기준 포즈와 같은지 · 사상이 Vesper 간격을
           맞히는지도 본다.
           정정(2026-10-26 밤 — 지난 실행은 손 뒤바뀜 85 ~ 93 % · 머리 박힘 · 몸 관통 75 % 를 PASS 로 넘겼다): 고른 후보(Vesper · 소스 2차)의
           꼬임 · 손-머리 근접 · 관통이 운영 낫 애니 기준 상한(SCYTHE_LIMITS) 안이어야 하고, 운영 애니 자신도 그 상한 안이어야 한다(상한이 과하지 않다).
           2차 목표가 1차보다 손을 더 뒤바꾸지 않는지(refine 통계)도 본다
  e3     — (선택) 프롬프트만 바꿈("…feet shoulder-width apart") · 플래그 없이 같은 seed — 넓은 다리가 프롬프트 탓인지 발 좌우 비로
  dirty  — (맨 뒤) 해시 불변 · 미저장 수 그대로 · Content/ 변경은 이번 실행 폴더뿐
요약은 Tools/mcp/anim_gen_phase8_1_state.json(섹션 단위로 덮어쓴다 — 앞 실행의 다른 섹션은 남는다).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import pathlib
import subprocess
import sys
import time

from anim_graph_mcp import bridge

STAMP = time.strftime("%m%d_%H%M%S")
ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P81Run{STAMP}"
os.environ["ANIM_GEN_STATE_DIR"] = str(STATE_DIR)

from anim_gen import motion_metrics, selection  # noqa: E402
from anim_gen.editor import EditorClient  # noqa: E402
from anim_gen.providers import local_ai  # noqa: E402
from anim_gen.providers.builtin import RetargetPipe  # noqa: E402
from anim_gen.service import Service  # noqa: E402
from anim_gen.store import Store  # noqa: E402

VESPER = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
VESPER_MESH_01 = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
RUN = f"/Game/Animation/Test/AIAnimation/P81Run{STAMP}"
# 기준 시험(유지 — 지우지 않는다)
BASE_RUN = "/Game/Animation/Test/AIAnimation/KimodoSword1025_185815"
BASE_ASSET = f"{BASE_RUN}/AS_Vesper_Sword_KimodoSlash"
BASE_WORK = f"{BASE_RUN}/Work/job_20261025_185816_3461c1/A1"
BASE_RECORD = {"penetration_pct": 39.7, "depth_max": 3.5, "kimodo_root": {"root_travel_cm": 105.66, "root_displacement_cm": 72.4, "heading_delta_deg": 0.41}}
HASHED = [BASE_ASSET, VESPER, VESPER_MESH_01]
PROMPT = ("A person holds a sword with both hands, raises it over the right shoulder, slashes diagonally down to the left, "
          "then returns to a fighting stance.")
SEED = 20261025
DURATION = 4.0
# 측정 본(Vesper) — 손목 · 위팔 · 아래팔 · 발 · 넓적다리(엉덩 관절)
PROFILE_BONES = ["hand_l", "hand_r", "upperarm_l", "lowerarm_l", "foot_l", "foot_r", "thigh_l", "thigh_r"]
GRIP_CM = 20.0   # 양손 파지 = 손목 간격 ≤ 20 cm × scale (플러그인 AnimMcpBodyClearance GripCm 과 같은 기준)
FLAGS = {"two_hand_weapon_grip": True, "foot_contact": True}
GRIP_REACHED_PCT = 80.0   # 완료 기준 ① — 파지 구간 손목 간격 ≤ 20 cm × scale 프레임 ≥ 80 %
FOOT_HOLD_MAX_CM = 5.0    # 완료 기준 ① — 접지 발 위치가 1차와 같다(키 프레임 최대 차)
E3_PROMPT = ("A person holds a sword with both hands, raises it over the right shoulder, slashes diagonally down to the left, "
             "then returns to a ready stance with feet shoulder-width apart.")
# 수정 전 E2 ② 기록(유지 — Persona 비교용) · Vesper 손목 굽힘 측정 본(아래팔 · 손목 · 중지 첫 마디 — motion_metrics.wrist_bend)
OLD_SELECT_RUN = "P81Run1026_154722"
OLD_SELECT_JOB = "job_20261026_154723_c49a83"
WRIST_BONES = {"elbow_l": "lowerarm_l", "hand_l": "hand_l", "finger_l": "middle_01_l", "elbow_r": "lowerarm_r", "hand_r": "hand_r", "finger_r": "middle_01_r"}
WRIST_BEND_MARGIN_DEG = 30.0   # B 확인 — 2차 보조 손목 굽힘 최대 ≤ 1차 최대 + 30°(수정 전 2차는 1차 22.8 → 111.5°)
# 낫 기준 보정 — Vesper 근접 무기는 낫(로드아웃 WD_Sickle1). 운영 낫 애니 양손 구간 손목 간격 50 ~ 78 cm(p50 55 ~ 66) → 요청 간격 60 cm
SCYTHE_PROMPT = ("A person holds a long-handled scythe with both hands, raises it over the right shoulder, slashes diagonally down to the left, "
                 "then returns to a fighting stance.")
# 대상(Vesper) 기준 요청 간격 — 운영 낫 양손 구간 p50 54.8 / 54.9 / 63.3 / 66.2 의 가운데 아래쪽. 계획이 간격 사상으로 생성 간격(≈ 75.2)을 정한다.
# 대가(기록 1차 NPZ 에 solve_grip, 생성 없음): 생성 60 → 75.2 에서 목표 이동 p50 0 ~ 19.6 → 0 ~ 33.2 · 최대 28.0 → 47.3 cm, 도달 비(전) 최대 1.42 →
# 1.67, 손 뒤바뀜 그대로 — 꼬임 · 머리 · 관통 상한 검사로 깨짐을 잡는다
SCYTHE_TARGET_SPACING_CM = 60.0
SCYTHE_JOB_RUN, SCYTHE_JOB = "P81Run1026_192547", "job_20261026_192555_f991aa"   # 낫 정정 기록(생성 간격 60 · 버전 4 띠 FAIL 2) — regrip
MAP_TOLERANCE_CM = 3.0   # 간격 사상이 Vesper 손목 간격 p50 을 이만큼 안으로 맞혀야 한다(기록 오차 ≤ 1.1 cm, 파지선이 세로로 서면 생성 75 에서 최대 4.3)
SICKLE_REFS = [f"/Game/Animation/Hero/Vesper/Sickle/Actions/AS_Vesper_Sickle_{n}" for n in ("Attack1", "Attack2", "Attack3", "Finisher1")]
# 낫 결과 상한(운영 낫 애니 4개 Vesper 측정 2026-10-26 밤: 꼬임 0 ~ 16.3 % · 머리 10 cm 안 0 % · 관통 0 ~ 34.4 %) — 꼬임 · 머리는 선별 벌점이 시작되는
# 값(selection.THRESHOLDS — 단일 원천), 관통은 운영 최대 + 5 % 반올림
SCYTHE_LIMITS = {"cross_pct": selection.THRESHOLDS["cross_pct_base"], "head_pct": selection.THRESHOLDS["head_pct_base"], "penetration_pct": 40.0}
FAILS: list[str] = []
STATE: dict = {"run": RUN, "state_dir": STATE_DIR.as_posix()}
SERVICE = Service(store=Store(STATE_DIR))


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


def base_request(**overrides) -> dict:
    """기준 시험의 요청(Plan 기록 그대로) — 이름 · 출력 경로만 이 실행 것."""
    req = {"target_skeleton": VESPER, "target_mesh": VESPER_MESH_01, "hero": "Vesper", "family": "Sword",
           "animation_name": "AS_Vesper_Sword_KimodoSlashP81", "description": "양손으로 칼을 들어 대각선으로 베고 전투 자세로 돌아온다 (Kimodo 시험)",
           "motion_category": "weapon_action", "loop": False, "frame_rate": 30, "duration_seconds": DURATION, "prompt": PROMPT, "provider": "local_ai",
           "generation": {"seed": SEED, "samples": 1, "steps": 100, "postprocess": "auto"}, "retarget": {"align_mode": "per_bone"},
           "review": {"render": {"count": 6}}, "output_path": RUN}
    req.update(overrides)
    return {k: v for k, v in req.items() if v is not ...}


def wait_job(job: dict, limit: float = 900.0) -> tuple[dict, float]:
    t0 = time.time()
    while job["status"] == "RUNNING" and time.time() - t0 < limit:
        time.sleep(1.0)
        env = SERVICE.get_generation_status(job_id=job["job_id"])
        job = env["result"] if env["ok"] else env["error"]["details"].get("job", job)
    return job, round(time.time() - t0, 2)


def run_job(req: dict, label: str) -> tuple[dict, dict, float]:
    plan = must(SERVICE.plan_motion_generation(request=req), f"plan {label}")
    t0 = time.time()
    job = must(SERVICE.generate_motion(plan_id=plan["plan_id"], save=True), f"generate {label}")
    check(job["status"] == "RUNNING" and (job.get("pending") or {}).get("provider") == "local_ai",
          f"{label}: generate_motion returns RUNNING with a Kimodo handle (pid {((job.get('pending') or {}).get('handle') or {}).get('pid')})")
    job, _ = wait_job(job)
    seconds = round(time.time() - t0, 2)
    if job["status"] != "SUCCEEDED":
        print(f"[FAIL] {label} job {job['status']}: {json.dumps(job.get('error'), ensure_ascii=False)[:2000]}")
        print(f"   fallback_history {json.dumps(job.get('fallback_history'), ensure_ascii=False)[:2000]}")
    return plan, job, seconds


def job_assets(job: dict) -> dict:
    inter = job["intermediate_assets"]
    work = job["work_path"]
    sel = job.get("selection") or {}
    # 후보가 여럿이면 소스 = 고른 후보의 임포트 애니(Import/Motion/C<번호>/), 아니면 Import/Motion/ 의 애니
    picked = next((c["source"] for c in sel.get("candidates") or [] if c["index"] == (sel.get("picked") or {}).get("index")), None)
    return {"source_anim": picked or next((a for a in inter if "/Import/Motion/" in a), None),
            "ik_target": f"{work}/IK_Target" if f"{work}/IK_Target" in inter else None,
            "retargeter": job["cursor"]["values"].get("retargeter")}


def profile(asset: str, source: str, ik_target: str, retargeter: str) -> dict:
    """validate_animation — profile(위치 · 속도) · 관통 · 손가락. 소스 대비 상대 검사도 같이(소스 골반 Hips)."""
    params = {"assets": [asset], "sources": [source], "skeleton": VESPER, "source_pelvis": local_ai.SOMA_PELVIS, "source_feet": local_ai.SOMA_FEET,
              "profile_bones": PROFILE_BONES, "profile_positions": True, "fingers": {"retargeter": retargeter},
              "body_clearance": {"mesh": VESPER_MESH_01, "ik_rig": ik_target}}
    return must(editor("validate_animation", **params), f"validate {asset.rsplit('/', 1)[1]}")["assets"][0]


# ---- 측정 (리스트 수학 — 이 섹션은 제품 코드 motion_metrics 보다 먼저 쓴다) ----
def sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def norm(v) -> float:
    return math.sqrt(sum(x * x for x in v))


def angle_deg(a, b) -> float:
    na, nb = norm(a), norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.0
    c = max(-1.0, min(1.0, sum(a[i] * b[i] for i in range(3)) / (na * nb)))
    return math.degrees(math.acos(c))


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def r2(x):
    return None if x is None else round(x, 2)


def stance_ratio(pos: dict) -> list[float]:
    """발 좌우 간격 / 엉덩 관절 폭 — 엉덩 축(thigh_l − thigh_r) 수평 방향에 발 간격을 투영(UE z-up)."""
    out = []
    for fl, fr, hl, hr in zip(pos["foot_l"], pos["foot_r"], pos["thigh_l"], pos["thigh_r"]):
        axis = [hl[0] - hr[0], hl[1] - hr[1]]
        width = math.hypot(*axis)
        if width < 1e-6:
            continue
        d = [fl[0] - fr[0], fl[1] - fr[1]]
        out.append(abs(d[0] * axis[0] + d[1] * axis[1]) / width / width)
    return out


def arms(item: dict) -> dict:
    return {a["upper_arm"]: {"penetration_pct": a["frames_over_penetration_pct"], "contact_pct": a["frames_over_contact_pct"],
                             "depth_p50": a["depth_p50"], "depth_max": a["depth_max"], "worst": a.get("worst")}
            for a in ((item.get("body_clearance") or {}).get("arms") or [])}


def summarize(v: dict) -> dict:
    n = v["numeric"]
    pos = (n.get("profile") or {}).get("position_cm") or {}
    scale = (n.get("pelvis_height_cm") or 100.0) / 100.0
    gap = [norm(sub(a, b)) for a, b in zip(pos.get("hand_l", []), pos.get("hand_r", []))]
    thr = GRIP_CM * scale
    stance = stance_ratio(pos) if all(b in pos for b in ("foot_l", "foot_r", "thigh_l", "thigh_r")) else []
    return {"status": v["status"], "frames": n.get("frames"), "pelvis_height_cm": n.get("pelvis_height_cm"), "scale": round(scale, 4),
            "grip_threshold_cm": round(thr, 2), "gap_cm": {"min": r2(min(gap) if gap else None), "p10": r2(pct(gap, 0.1)), "p50": r2(pct(gap, 0.5)),
                                                          "max": r2(max(gap) if gap else None)},
            "grip_pct": round(100.0 * sum(g <= thr for g in gap) / len(gap), 1) if gap else None,
            "stance_ratio": {"p50": r2(pct(stance, 0.5)), "p90": r2(pct(stance, 0.9))}, "arms": arms(v),
            "max_deg_per_frame": n.get("max_deg_per_frame"), "warnings": [i["code"] for i in v.get("issues", []) if i.get("level") == "warning"]}


# ---- 섹션 ----
def section_hashes() -> None:
    print("== hashes · content · dirty (before)")
    STATE["hashes"] = {p: sha256(p) for p in HASHED}
    STATE["content_before"] = content_changes()
    STATE["dirty_before"] = dirty_count()
    print(f"   {len(HASHED)} assets hashed · Content changes before: {len(STATE['content_before'])} · dirty {STATE['dirty_before']}")


def section_exp1() -> None:
    print("== exp1 — same seed, body_clearance measure vs the kept resolve asset")
    req = base_request(animation_name="AS_Vesper_Sword_KimodoSlashMeasure", retarget={"align_mode": "per_bone", "body_clearance": "measure"})
    plan, job, seconds = run_job(req, "exp1")
    rt = next(s for s in plan["candidates"][0]["steps"] if s["step"] == "retarget")
    check(rt["inputs"]["body_clearance"] == "measure", "plan: retarget body_clearance measure (request)")
    check(job["status"] == "SUCCEEDED", f"exp1 job {job['status']} ({seconds}s)")
    if job["status"] != "SUCCEEDED":
        STATE["exp1"] = {"job_id": job["job_id"], "status": job["status"], "error": job.get("error")}
        return
    values = job["cursor"]["values"]
    picked = values["generated"]["samples"][values["generated"]["pick"]]
    kroot = picked.get("root") or {}
    same_root = all(abs((kroot.get(k) or 0) - v) <= 0.05 for k, v in BASE_RECORD["kimodo_root"].items())
    print(f"   Kimodo root {kroot} · reference {BASE_RECORD['kimodo_root']} · seconds {values['generated']['seconds']}")
    check(same_root, "same seed → same Kimodo root track as the reference (±0.05)")
    measure = job["generated_assets"][0]
    assets = job_assets(job)
    clearance_items = values.get("body_clearance") or []
    check(not any(i.get("modified") for i in clearance_items), "measure: retarget did not modify the upper arms")
    vm = profile(measure, assets["source_anim"], assets["ik_target"], assets["retargeter"])
    vr = profile(BASE_ASSET, f"{BASE_WORK}/Import/Motion/BVH_kimodo_00", f"{BASE_WORK}/IK_Target", f"{BASE_WORK}/RTG_Retarget")
    sm, sr = summarize(vm), summarize(vr)
    pm = vm["numeric"]["profile"]["position_cm"]
    pr = vr["numeric"]["profile"]["position_cm"]
    thr = sm["grip_threshold_cm"]
    gm = [norm(sub(a, b)) for a, b in zip(pm["hand_l"], pm["hand_r"])]
    gr = [norm(sub(a, b)) for a, b in zip(pr["hand_l"], pr["hand_r"])]
    broken = sum(1 for a, b in zip(gm, gr) if a <= thr < b)
    widened = [b - a for a, b in zip(gm, gr)]
    move_l = [norm(sub(a, b)) for a, b in zip(pr["hand_l"], pm["hand_l"])]
    move_r = [norm(sub(a, b)) for a, b in zip(pr["hand_r"], pm["hand_r"])]
    upper = [angle_deg(sub(b2, a2), sub(b1, a1)) for a1, b1, a2, b2 in zip(pm["upperarm_l"], pm["lowerarm_l"], pr["upperarm_l"], pr["lowerarm_l"])]
    feet = [max(norm(sub(a, b)), norm(sub(c, d))) for a, b, c, d in zip(pr["foot_l"], pm["foot_l"], pr["foot_r"], pm["foot_r"])]
    pen_m = sm["arms"].get("upperarm_l", {})
    deterministic = abs((pen_m.get("penetration_pct") or 0) - BASE_RECORD["penetration_pct"]) <= 0.1 and abs((pen_m.get("depth_max") or 0) - BASE_RECORD["depth_max"]) <= 0.05
    verdict = "CLEARANCE_BROKE_GRIP" if broken else "NO_GRIP_CLEARANCE_WIDENED"
    print(f"   measure : gap {sm['gap_cm']} · grip ≤ {thr} cm {sm['grip_pct']}% · stance {sm['stance_ratio']} · arms {[(k, a['penetration_pct'], a['depth_max']) for k, a in sm['arms'].items()]} · {sm['status']}")
    print(f"   resolve : gap {sr['gap_cm']} · grip {sr['grip_pct']}% · stance {sr['stance_ratio']} · arms {[(k, a['penetration_pct'], a['depth_max']) for k, a in sr['arms'].items()]} · {sr['status']}")
    print(f"   resolve − measure: left wrist moved p50 {r2(pct(move_l, 0.5))} · max {r2(max(move_l))} cm · right wrist max {r2(max(move_r))} cm · "
          f"upper arm direction p50 {r2(pct(upper, 0.5))} · max {r2(max(upper))}° · gap widened p50 {r2(pct(widened, 0.5))} · max {r2(max(widened))} cm · "
          f"feet moved max {r2(max(feet))} cm · grip frames broken {broken}")
    check(len(gm) == len(gr) and len(gm) > 0, f"both profiles sampled the same {len(gm)} times")
    check(deterministic, f"measure penetration {pen_m.get('penetration_pct')}% · depth {pen_m.get('depth_max')} cm = recorded pre-correction "
          f"{BASE_RECORD['penetration_pct']}% · {BASE_RECORD['depth_max']} cm (same-seed determinism)")
    check(max(move_r) <= 0.5 and max(feet) <= 0.5, "resolve changed only the left arm (right wrist · feet unchanged ≤ 0.5 cm)")
    print(f"   verdict: {verdict} — " + ("clearance pushed hands that were within grip distance apart" if broken
                                         else f"no frame was within {thr} cm in measure — there was no grip to break; the correction only widened the hands"))
    STATE["exp1"] = {"job_id": job["job_id"], "asset": measure, "reference": BASE_ASSET, "seconds": seconds, "kimodo_root": kroot,
                     "kimodo_seconds": values["generated"]["seconds"], "same_kimodo_root": same_root, "deterministic_penetration": deterministic,
                     "measure": sm, "resolve": sr,
                     "resolve_minus_measure": {"left_wrist_moved_cm": {"p50": r2(pct(move_l, 0.5)), "max": r2(max(move_l))},
                                               "right_wrist_moved_cm_max": r2(max(move_r)), "feet_moved_cm_max": r2(max(feet)),
                                               "upper_arm_dir_deg": {"p50": r2(pct(upper, 0.5)), "max": r2(max(upper))},
                                               "gap_widened_cm": {"p50": r2(pct(widened, 0.5)), "max": r2(max(widened)), "min": r2(min(widened))},
                                               "grip_frames_broken": broken},
                     "verdict": verdict, "limitations": [lim["code"] for lim in job["limitations"]]}


def import_root() -> pathlib.Path:
    return pathlib.Path(must(editor("get_editor_status"), "status")["generation"]["import_source_roots"][0])


def steps_of(cand: dict) -> dict:
    return {s["step"]: s for s in cand["steps"]}


def flagged(**generation) -> dict:
    return {"seed": SEED, "samples": 1, "steps": 100, "postprocess": "auto", **generation}


def section_plan() -> None:
    print("== plan — flags · candidates (no Kimodo, no assets)")
    local_dir = import_root() / "LocalAI"
    before_runs = sorted(p.name for p in local_dir.iterdir()) if local_dir.is_dir() else []
    before = dirty_count()
    p = must(SERVICE.plan_motion_generation(request=base_request(animation_name="AS_Vesper_Sword_KimodoSlashPlanP81", constraints=FLAGS,
                                                                 generation=flagged(candidates=4))), "plan flags")
    [cand] = p["candidates"]
    s = steps_of(cand)
    g = s["generate"]["inputs"]
    rules = {r["flag"]: r for r in g["refine"]["rules"]}
    lims = {lim["code"] for lim in cand["expected_limitations"]}
    print(f"   steps {[x['step'] for x in cand['steps']]} · seeds {g['seeds']} · passes {g['refine']['passes']} · diffusions {g['diffusions']} · timeout {g['timeout_s']}s")
    print(f"   rules {json.dumps(g['refine']['rules'], ensure_ascii=False)[:900]}")
    print(f"   select {json.dumps({k: v for k, v in s['select']['inputs'].items() if k != 'candidates'}, ensure_ascii=False)[:600]}")
    print(f"   limitations {sorted(lims)} · risks {cand['risks']}")
    check([x["step"] for x in cand["steps"]] == ["generate", "convert", "import", "select", "retarget", "validate"], "chain gains a select step before retarget")
    check(g["seeds"] == [SEED + i for i in range(4)] and g["refine"]["passes"] == 2 and g["diffusions"] == 8, "4 seed candidates × 2 passes pinned")
    check(rules["two_hand_weapon_grip"]["target"] == "meet" and rules["two_hand_weapon_grip"]["kimodo"] == ["end-effector[LeftHand, RightHand]"]
          and rules["foot_contact"]["kimodo"] == ["end-effector[LeftFoot]", "end-effector[RightFoot]"] and rules[None]["kimodo"] == ["root2d"],
          "rules: grip → end-effector both wrists (meet), foot_contact → foot end-effectors, root2d keeps pass 1")
    check(g["timeout_s"] == 300 + 25 * 7 and g["postprocess"] is True, f"Kimodo deadline {g['timeout_s']}s = 300 + 25 × 7 · post-process on")
    check(g["refine"]["smooth_sigma_frames"] == 1.0, "pass-2 output smoothing σ 1 frame pinned in the plan (refine.plan — the runner only reads it)")
    bones = s["select"]["inputs"]["bones"]
    check({k: bones[k] for k in motion_metrics.ROLES}
          == {"hand_l": "hand_l", "hand_r": "hand_r", "hip_l": "thigh_l", "hip_r": "thigh_r", "foot_l": "foot_l", "foot_r": "foot_r",
              "shoulder_l": "upperarm_l", "shoulder_r": "upperarm_r", "elbow_l": "lowerarm_l", "elbow_r": "lowerarm_r"},
          f"selection bones (from {bones['from']}) = Vesper wrists · hip joints · ankles · shoulders (arm chain start) · elbows (wrist parent)")
    check({"attack", "cross", "head"} <= set(s["select"]["inputs"]["weights"]) and s["select"]["inputs"]["metric_version"] == 5,
          "select weights include attack (hand path width) · cross (wrists crossed) · head (hands in the head) · metric version 5")
    check(bones.get("head") == "head", f"head bone from the template Head chain: {bones.get('head')}")
    check(bones.get("arm_dims") == {"shoulder_width_cm": 23.96, "arm_cm": 47.66} and s["select"]["inputs"]["grip_spacing"] is None,
          f"target arm dims from the reference pose (shoulder joints · upper + fore arm) {bones.get('arm_dims')} · no polearm band for a sword hilt")
    check(rules["two_hand_weapon_grip"]["axis"].startswith("pass-1 lead wrist → support wrist"), f"grip axis rule: {rules['two_hand_weapon_grip']['axis']}")
    check(bool(bones.get("hand_tree_l")) and bool(bones.get("hand_tree_r")), f"hand trees for the hand-contact record ({len(bones.get('hand_tree_l') or [])} + "
          f"{len(bones.get('hand_tree_r') or [])} bone pairs below the wrists)")
    check(s["retarget"]["inputs"]["body_clearance"] == "measure" and s["retarget"]["inputs"]["body_clearance_from"] == "grip_flag",
          "body_clearance measure from the grip flag")
    check({"GRIP_POSITION_ONLY", "SELECTED_BY_NUMBERS", "BODY_CLEARANCE_MEASURED_FOR_GRIP"} <= lims and not {"GRIP_NOT_VALIDATED", "FOOT_CONTACT_NOT_ENFORCED"} & lims,
          "limitations: GRIP_POSITION_ONLY · SELECTED_BY_NUMBERS · BODY_CLEARANCE_MEASURED_FOR_GRIP (no GRIP_NOT_VALIDATED / FOOT_CONTACT_NOT_ENFORCED)")
    base = must(SERVICE.plan_motion_generation(request=base_request(animation_name="AS_Vesper_Sword_KimodoSlashBaseP81")), "plan baseline")
    bc = base["candidates"][0]
    bs = steps_of(bc)
    blims = {lim["code"] for lim in bc["expected_limitations"]}
    check([x["step"] for x in bc["steps"]] == ["generate", "convert", "import", "retarget", "validate"] and "seeds" not in bs["generate"]["inputs"]
          and bs["retarget"]["inputs"]["body_clearance"] == "resolve" and "GRIP_NOT_VALIDATED" in blims and "SELECTED_BY_NUMBERS" not in blims,
          "no flags · no candidates → revision 10 chain, body_clearance resolve, GRIP_NOT_VALIDATED")
    after_runs = sorted(p.name for p in local_dir.iterdir()) if local_dir.is_dir() else []
    check(after_runs == before_runs, "planning started no Kimodo run")
    check(dirty_count() == before and not uasset(f"{RUN}/x").parent.exists(), f"planning left no asset and the dirty count unchanged ({before})")
    STATE["plan"] = {"steps": [x["step"] for x in cand["steps"]], "seeds": g["seeds"], "refine": g["refine"], "timeout_s": g["timeout_s"],
                     "select_inputs": {k: v for k, v in s["select"]["inputs"].items() if k != "candidates"}, "limitations": sorted(lims), "risks": cand["risks"],
                     "baseline_steps": [x["step"] for x in bc["steps"]], "baseline_body_clearance": bs["retarget"]["inputs"]["body_clearance"]}


def _jit(m: dict | None) -> list | None:
    j = (m or {}).get("jitter")
    return None if not j else [j.get("start"), j.get("middle"), j.get("end")]


def _bend(m: dict | None, side: str = "l") -> list | None:
    b = ((m or {}).get("wrist_bend") or {}).get(side)
    return None if not b else [b.get("p50"), b.get("p95"), b.get("max")]


def _slide(m: dict | None) -> list | None:
    s = (m or {}).get("foot_slide")
    return None if not s else [(s.get("l") or {}).get("p95"), (s.get("r") or {}).get("p95")]


def vesper_metrics(m: dict) -> dict:
    """Job selection 후보 metrics(제품 candidate_metrics) → 보고용 원 수치."""
    attack = m.get("attack") or {}
    return {"grip_pct": (m.get("grip") or {}).get("grip_pct"), "gap_p50": ((m.get("grip") or {}).get("gap_cm") or {}).get("p50"),
            "stance_p90": ((m.get("stance") or {}).get("lateral_ratio") or {}).get("p90"),
            "swing_peak": (m.get("swing") or {}).get("peak_cm_s"), "penetration_pct": (m.get("clearance") or {}).get("penetration_pct"),
            "non_grip_penetration_pct_max": (m.get("non_grip") or {}).get("non_grip_penetration_pct_max"),
            "worst_in_grip": (m.get("non_grip") or {}).get("worst_in_grip"),
            "width": attack.get("width_arm_ratio"), "width_mid": attack.get("width_mid_arm_ratio"), "raise": attack.get("raise_arm_ratio"),
            "arm_cm": attack.get("arm_cm"), "jitter": _jit(m), "hand_contact": m.get("hand_contact"),
            "gap_p90": ((m.get("grip") or {}).get("gap_cm") or {}).get("p90"), "band": (m.get("grip") or {}).get("band_cm"),
            "max_deg_per_frame": (m.get("breakage") or {}).get("max_deg_per_frame"),
            "warnings": (m.get("breakage") or {}).get("all_warnings", (m.get("breakage") or {}).get("warnings")),
            "scored_warnings": (m.get("breakage") or {}).get("scored_warnings"),
            "cross_pct": (m.get("cross") or {}).get("crossed_pct"), "swapped_pct": (m.get("cross") or {}).get("swapped_pct"),
            "cross_depth_max": ((m.get("cross") or {}).get("depth_cm") or {}).get("max"),
            "head_pct": (m.get("head") or {}).get("near_pct"), "head_min_cm": (m.get("head") or {}).get("min_cm"),
            "arm": (m.get("clearance") or {}).get("arm"), "depth_max": (m.get("clearance") or {}).get("depth_max")}


def candidate_table(sel: dict, generated: dict) -> list[dict]:
    """Job selection + Kimodo 소스 수치 → 보고용 행(후보마다 원 수치 · 벌점 · 점수 · 순위)."""
    src = {c["index"]: c for c in generated.get("candidates") or []}
    rows = []
    for c in sel["candidates"]:
        s2 = (src.get(c["index"]) or {}).get("source_metrics") or {}
        last = s2.get("pass2") or s2.get("pass1") or {}
        refine = (src.get(c["index"]) or {}).get("refine") or {}
        rows.append({"index": c["index"], "seed": c["seed"], "asset": c["asset"], "status": c["status"], "rank": c["rank"], "score": c["score"],
                     "penalties": c["penalties"], "excluded": c.get("excluded"), "clearance_basis": c.get("clearance_basis"),
                     "vesper": vesper_metrics(c["metrics"]),
                     "source": {"grip_pct_pass1": ((s2.get("pass1") or {}).get("grip") or {}).get("grip_pct"), "grip_pct": (last.get("grip") or {}).get("grip_pct"),
                                "gap_p50": ((last.get("grip") or {}).get("gap_cm") or {}).get("p50"),
                                "gap_max": ((last.get("grip") or {}).get("gap_cm") or {}).get("max"),
                                "stance_p90": ((last.get("stance") or {}).get("lateral_ratio") or {}).get("p90"),
                                "swing_peak_pass1": ((s2.get("pass1") or {}).get("swing") or {}).get("peak_cm_s"),
                                "swing_peak_unsmoothed": ((s2.get("pass2_unsmoothed") or {}).get("swing") or {}).get("peak_cm_s"),
                                "swing_peak": (last.get("swing") or {}).get("peak_cm_s"),
                                "jitter_pass1": _jit(s2.get("pass1")), "jitter_unsmoothed": _jit(s2.get("pass2_unsmoothed")), "jitter": _jit(last),
                                "bend_l_pass1": _bend(s2.get("pass1")), "bend_l": _bend(last), "bend_r": _bend(last, "r"),
                                "width_pass1": ((s2.get("pass1") or {}).get("attack") or {}).get("width_arm_ratio"),
                                "width": (last.get("attack") or {}).get("width_arm_ratio"), "raise": (last.get("attack") or {}).get("raise_arm_ratio"),
                                "slide_pass1": _slide(s2.get("pass1")), "slide_unsmoothed": _slide(s2.get("pass2_unsmoothed")), "slide": _slide(last),
                                "cross_pct_pass1": ((s2.get("pass1") or {}).get("cross") or {}).get("crossed_pct"),
                                "cross_pct": (last.get("cross") or {}).get("crossed_pct"), "swapped_pct": (last.get("cross") or {}).get("swapped_pct"),
                                "head_pct_pass1": ((s2.get("pass1") or {}).get("head") or {}).get("near_pct"),
                                "head_pct": (last.get("head") or {}).get("near_pct"), "head_min_cm": (last.get("head") or {}).get("min_cm"),
                                "target_crossed_pct": ((refine.get("grip") or {}).get("stats") or {}).get("crossed_pct"),
                                "target_axis_from": ((refine.get("grip") or {}).get("stats") or {}).get("axis_from"),
                                "target_moved_cm": ((refine.get("grip") or {}).get("stats") or {}).get("moved_cm"),
                                "follow": refine.get("follow"), "smooth": refine.get("smooth"),
                                "hand_rule": (refine.get("grip") or {}).get("hand_rule"),
                                "target_stats": {k: ((refine.get("grip") or {}).get("stats") or {}).get(k) for k in ("hand_align_deg", "support_wrist_bend_deg")}}})
    return rows


def print_table(rows: list[dict]) -> None:
    print("   idx seed      rank score  | Vesper grip% gap50 stance90 swing pen% nongrip≤ width | source grip% (p1→p2) gap50 stance90 swing")
    for r in rows:
        v, s = r["vesper"], r["source"]
        print(f"   {r['index']:3d} {r['seed']} {str(r['rank']):>4} {str(r['score']):>6} | {v['grip_pct']!s:>6} {v['gap_p50']!s:>6} {v['stance_p90']!s:>6} "
              f"{v['swing_peak']!s:>6} {v['penetration_pct']!s:>5} {v['non_grip_penetration_pct_max']!s:>6} {v['width']!s:>5} | {s['grip_pct_pass1']!s:>5}→{s['grip_pct']!s:<5} "
              f"{s['gap_p50']!s:>6} {s['stance_p90']!s:>6} {s['swing_peak']!s:>6} {r['status']}")
        print(f"        penalties {r['penalties']} · scored warnings {v['scored_warnings']} · all {v['warnings']} · max {v['max_deg_per_frame']}°/frame · "
              f"grip band {v['band']} · gap p90 {v['gap_p90']} · hand contact {v['hand_contact']}")
        print(f"        source jitter p1 {s['jitter_pass1']} → p2 raw {s['jitter_unsmoothed']} → σ1 {s['jitter']} · Vesper {v['jitter']} | support wrist bend "
              f"p1 {s['bend_l_pass1']} → p2 {s['bend_l']} (lead {s['bend_r']}) · rule {s['hand_rule']} · targets {s['target_stats']}")
        print(f"        width p1 {s['width_pass1']} → p2 {s['width']} (Vesper {v['width']}, raise {v['raise']}) · swing p1 {s['swing_peak_pass1']} → raw "
              f"{s['swing_peak_unsmoothed']} → σ1 {s['swing_peak']} · foot slide p95 p1 {s['slide_pass1']} → raw {s['slide_unsmoothed']} → σ1 {s['slide']} · "
              f"smooth {s['smooth']}")
        print(f"        cross% (> {selection.THRESHOLDS['cross_cm']:g} cm) source p1 {s['cross_pct_pass1']} → p2 {s['cross_pct']} (swapped {s['swapped_pct']}) · "
              f"Vesper {v['cross_pct']} (swapped {v['swapped_pct']}, depth max {v['cross_depth_max']}) | head% (< {selection.THRESHOLDS['head_near_cm']:g} cm) "
              f"source p1 {s['head_pct_pass1']} → p2 {s['head_pct']} (min {s['head_min_cm']}) · Vesper {v['head_pct']} (min {v['head_min_cm']}) | "
              f"pen {v['penetration_pct']}% ({v['arm']}, depth {v['depth_max']}) · basis {r['clearance_basis']} | targets axis {s['target_axis_from']} · "
              f"crossed {s['target_crossed_pct']} · moved {s['target_moved_cm']}")


def vesper_wrists(assets: list[str]) -> dict:
    """Vesper 손목 굽힘(motion_metrics.wrist_bend — 아래팔 → 손목 vs 손목 → 중지 첫 마디) — 애셋마다 {l, r}. 측정만(validate_animation)."""
    bones = sorted(set(WRIST_BONES.values()))
    res = must(editor("validate_animation", assets=assets, skeleton=VESPER, profile_bones=bones, profile_positions=True), "validate wrists")
    out = {}
    for a, item in zip(assets, res["assets"]):
        pos = ((item.get("numeric") or {}).get("profile") or {}).get("position_cm") or {}
        out[a] = {s: motion_metrics.wrist_bend(pos.get(WRIST_BONES[f"elbow_{s}"], []), pos.get(WRIST_BONES[f"hand_{s}"], []),
                                               pos.get(WRIST_BONES[f"finger_{s}"], [])) for s in ("l", "r")}
    return out


def run_refine(label: str, name: str, generation: dict, prompt: str = PROMPT, constraints: dict | None = FLAGS, **overrides) -> dict | None:
    req = base_request(animation_name=name, prompt=prompt, constraints=constraints or {}, generation=generation, **overrides)
    plan, job, seconds = run_job(req, label)
    check(job["status"] == "SUCCEEDED", f"{label} job {job['status']} ({seconds}s)")
    if job["status"] != "SUCCEEDED":
        STATE[label] = {"job_id": job["job_id"], "status": job["status"], "error": job.get("error"), "history": job.get("fallback_history")}
        return None
    values = job["cursor"]["values"]
    return {"plan": plan, "job": job, "seconds": seconds, "values": values, "generated": values["generated"], "selection": job.get("selection"),
            "final": job["generated_assets"][0], "assets": job_assets(job)}


def check_refined(label: str, r: dict) -> dict:
    """완료 기준 ① — 소스(1 → 2차) · Vesper 파지, 접지 발, 관통 measure, 최종 = 잰 후보."""
    sel, gen, job = r["selection"], r["generated"], r["job"]
    picked = sel["picked"]
    chosen = next(c for c in sel["candidates"] if c["index"] == picked["index"])
    src = next(c for c in gen["candidates"] if c["index"] == picked["index"])
    m1, m2 = src["source_metrics"]["pass1"], src["source_metrics"]["pass2"]
    follow = src["refine"]["follow"]
    vg = chosen["metrics"]["grip"]
    print(f"   Kimodo {gen['seconds']} · source grip {m1['grip']['grip_pct']}% (gap p50 {m1['grip']['gap_cm']['p50']}) → {m2['grip']['grip_pct']}% "
          f"(gap p50 {m2['grip']['gap_cm']['p50']}) · follow {json.dumps(follow, ensure_ascii=False)}")
    print(f"   source stance p90 {m1['stance']['lateral_ratio']['p90']} → {m2['stance']['lateral_ratio']['p90']} · swing {m1['swing']['peak_cm_s']} → "
          f"{m2['swing']['peak_cm_s']} cm/s · refine grip {json.dumps(src['refine']['grip'], ensure_ascii=False)[:400]}")
    print(f"   Vesper grip {vg['grip_pct']}% (≤ {vg['threshold_cm']} cm, gap {vg['gap_cm']}) · stance {chosen['metrics']['stance']['lateral_ratio']} · "
          f"swing {chosen['metrics']['swing']} · clearance {chosen['metrics'].get('clearance')} · non-grip {chosen['metrics'].get('non_grip')}")
    check(m2["grip"]["grip_pct"] >= GRIP_REACHED_PCT > m1["grip"]["grip_pct"],
          f"{label}: source wrist gap ≤ 20 cm {m1['grip']['grip_pct']}% → {m2['grip']['grip_pct']}% (≥ {GRIP_REACHED_PCT:g})")
    holds = [follow.get(k, {}).get("max") for k in ("foot_hold_left_cm", "foot_hold_right_cm")]
    check(all(h is not None and h <= FOOT_HOLD_MAX_CM for h in holds), f"{label}: contact feet stay where pass 1 put them (max {holds} cm ≤ {FOOT_HOLD_MAX_CM:g})")
    check(vg["grip_pct"] >= GRIP_REACHED_PCT, f"{label}: Vesper wrist gap ≤ 20 cm × scale on {vg['grip_pct']}% of frames (≥ {GRIP_REACHED_PCT:g})")
    rt = steps_of(r["plan"]["candidates"][0])["retarget"]["inputs"]
    clearance = r["values"].get("body_clearance") or []
    check(rt["body_clearance"] == "measure" and not any(i.get("modified") for i in clearance), f"{label}: body_clearance measure — upper arms untouched")
    # 최종 = 잰 후보(같은 RTG · 같은 관통 모드 → 같은 애니)
    v = profile(r["final"], r["assets"]["source_anim"], r["assets"]["ik_target"], r["assets"]["retargeter"])
    sf = summarize(v)
    check(abs((sf["gap_cm"]["p50"] or 0) - (vg["gap_cm"]["p50"] or 0)) <= 0.1 and abs((sf["grip_pct"] or 0) - (vg["grip_pct"] or 0)) <= 0.1,
          f"{label}: final asset = the measured candidate (gap p50 {sf['gap_cm']['p50']} vs {vg['gap_cm']['p50']} cm)")
    check(v["status"] in ("PASSED", "PASSED_WITH_WARNINGS"), f"{label}: validate_animation {v['status']} · warnings {sf['warnings']}")
    return {"job_id": job["job_id"], "asset": r["final"], "seconds": r["seconds"], "kimodo_seconds": gen["seconds"], "source": {"pass1": m1, "pass2": m2},
            "follow": follow, "refine": src["refine"], "vesper": chosen["metrics"], "final_check": sf, "selection_picked": picked,
            "limitations": [lim["code"] for lim in job["limitations"]], "review": (job.get("review") or {}).get("sheet")}


def section_refine() -> None:
    print("== refine — E2 ①: flags · meet · 1 candidate (seed 20261025)")
    r = run_refine("refine", "AS_Vesper_Sword_KimodoSlashMeet", flagged())
    if r:
        STATE["refine"] = check_refined("refine", r)


def section_lead() -> None:
    print("== lead — E2': flags · lead · same seed")
    r = run_refine("lead", "AS_Vesper_Sword_KimodoSlashLead", flagged(refine={"grip": {"target": "lead"}}))
    if r:
        src = next(c for c in r["generated"]["candidates"] if c["index"] == 0)
        print(f"   lead: source grip {src['source_metrics']['pass2']['grip']} · follow {src['refine']['follow']}")
        chosen = r["selection"]["candidates"][0]
        STATE["lead"] = {"job_id": r["job"]["job_id"], "asset": r["final"], "seconds": r["seconds"], "source": src["source_metrics"], "refine": src["refine"],
                         "vesper": chosen["metrics"], "limitations": [lim["code"] for lim in r["job"]["limitations"]]}
        check(chosen["metrics"]["grip"]["grip_pct"] is not None, f"lead: Vesper grip {chosen['metrics']['grip']['grip_pct']}% recorded (comparison only)")


def section_select() -> None:
    print("== select — E2 ②: 4 candidates (seeds 20261025 ~ 28)")
    r = run_refine("select", "AS_Vesper_Sword_KimodoSlashPick", flagged(candidates=4))
    if not r:
        return
    sel = r["selection"]
    rows = candidate_table(sel, r["generated"])
    print_table(rows)
    print(f"   picked {sel['picked']}")
    check(len(sel["candidates"]) == 4 and sel["picked"] is not None, "4 candidates retargeted · measured · one picked")
    again = selection.rank([{k: c[k] for k in ("index", "seed", "status", "metrics")} for c in sel["candidates"]], sel["weights"],
                           grip_on=sel["grip_on"], swing_on=sel["swing_on"])
    check(again["picked"] == sel["picked"], "recomputing the recorded numbers picks the same candidate")
    # 수정안 A · B — 후보마다 스무딩이 돌았고(FK 대응 0) 떨림이 줄었는가, 보조 손목 굽힘이 1차 수준인가(소스). Vesper 손목은 따로 잰다
    wrists = vesper_wrists([x["asset"] for x in rows])
    for x in rows:
        s = x["source"]
        x["vesper"]["bend"] = wrists.get(x["asset"])
        print(f"   #{x['index']} Vesper wrist bend L {x['vesper']['bend']['l']} · R {x['vesper']['bend']['r']}")
        sm = s["smooth"] or {}
        check(sm.get("sigma_frames") == 1.0 and (sm.get("fk_check_m") or 0) <= 1e-3 and s["jitter"] and s["jitter_unsmoothed"]
              and max(s["jitter"]) < max(s["jitter_unsmoothed"]),
              f"#{x['index']} A: pass 2 smoothed σ {sm.get('sigma_frames')} (FK {sm.get('fk_check_m')} m) — source zigzag p95 {s['jitter_unsmoothed']} → {s['jitter']}")
        check(s["hand_rule"] == "keep" and s["bend_l"] and s["bend_l_pass1"] and s["bend_l"][2] <= s["bend_l_pass1"][2] + WRIST_BEND_MARGIN_DEG,
              f"#{x['index']} B: support wrist bend max pass 1 {s['bend_l_pass1'] and s['bend_l_pass1'][2]}° → pass 2 {s['bend_l'] and s['bend_l'][2]}° "
              f"(≤ +{WRIST_BEND_MARGIN_DEG:g}°, rule {s['hand_rule']})")
    out = check_refined("select", r)
    order = sorted((x for x in rows if x["rank"]), key=lambda x: x["rank"])
    STATE["select"] = {**out, "table": rows, "picked": sel["picked"], "weights": sel["weights"], "thresholds": sel["thresholds"],
                       "best_width_arm_ratio": sel.get("best_width_arm_ratio"), "top2": [x["asset"] for x in order[:2]],
                       "kimodo_seconds": r["generated"]["seconds"]}


def section_recompute() -> None:
    print(f"== recompute — recorded {OLD_SELECT_JOB} candidates with the current measurement · score (no assets)")
    job_file = ROOT / "Saved" / "AnimGen" / "TestRuns" / OLD_SELECT_RUN / "jobs" / f"{OLD_SELECT_JOB}.json"
    old = json.loads(job_file.read_text(encoding="utf-8"))
    osel = old["selection"]
    work = old["work_path"]
    ik_target = f"{work}/IK_Target" if f"{work}/IK_Target" in old["intermediate_assets"] else None
    diags: list[dict] = []
    client = EditorClient()
    bones = {**RetargetPipe.selection_bones(client, VESPER, diags), "from": "template_chains"}
    for d in diags:
        print(f"   diag[{d['level']}] {d['code']}: {d['message'][:200]}")
    cands = sorted(osel["candidates"], key=lambda c: c["index"])
    params = {"assets": [c["asset"] for c in cands], "sources": [c["source"] for c in cands], "skeleton": VESPER,
              "profile_bones": RetargetPipe.profile_bones(bones), "profile_positions": True, "fingers": {"retargeter": osel["retargeter"]},
              "source_pelvis": local_ai.SOMA_PELVIS, "source_feet": local_ai.SOMA_FEET, "body_clearance": {"mesh": VESPER_MESH_01, "ik_rig": ik_target}}
    before = dirty_count()
    items = must(editor("validate_animation", **params), "validate recorded candidates")["assets"]
    plan_file = ROOT / "Saved" / "AnimGen" / "TestRuns" / OLD_SELECT_RUN / "plans" / f"{old['plan_id']}.json"
    old_plan = json.loads(plan_file.read_text(encoding="utf-8"))
    window = next(s for s in old_plan["candidates"][0]["steps"] if s["step"] == "select")["inputs"]["grip_window_s"]
    rows = [{"index": c["index"], "seed": c["seed"], "source": c["source"], "asset": c["asset"], "status": item.get("status", "PASSED"),
             "metrics": RetargetPipe.candidate_metrics(item, bones, window, None)} for c, item in zip(cands, items)]
    ranked = selection.rank(rows, None, grip_on=True, swing_on=True)
    wrists = vesper_wrists([c["asset"] for c in cands])
    table = []
    for c, o in zip(sorted(ranked["candidates"], key=lambda c: c["index"]), cands):
        v = vesper_metrics(c["metrics"])
        v["bend"] = wrists.get(c["asset"])
        table.append({"index": c["index"], "seed": c["seed"], "status": c["status"], "rank": c["rank"], "score": c["score"], "penalties": c["penalties"],
                      "clearance_basis": c.get("clearance_basis"), "vesper": v, "old": {"rank": o["rank"], "score": o["score"], "penalties": o["penalties"]}})
        print(f"   #{c['index']} seed {c['seed']} rank {c['rank']} score {c['score']} (was {o['rank']} · {o['score']}) · width {v['width']} · raise {v['raise']} · "
              f"swing {v['swing_peak']} · stance {v['stance_p90']} · pen {v['penetration_pct']} (non-grip ≤ {v['non_grip_penetration_pct_max']}) · "
              f"jitter {v['jitter']} · bend L {v['bend']['l']} · cross {v['cross_pct']} · head {v['head_pct']} · scored warnings {v['scored_warnings']} · "
              f"all {v['warnings']}")
        print(f"        penalties {c['penalties']}")
    print(f"   picked {ranked['picked']}")
    check(ranked["picked"]["seed"] == 20261025, f"new score picks seed {ranked['picked']['seed']} from the recorded candidates (was {osel['picked']['seed']}; "
          "expected 20261025 — the spike's recomputation)")
    check(dirty_count() == before, "measuring the recorded candidates left the dirty count unchanged")
    STATE["recompute"] = {"job_id": OLD_SELECT_JOB, "bones": bones, "weights": ranked["weights"], "thresholds": ranked["thresholds"],
                          "best_width_arm_ratio": ranked["best_width_arm_ratio"], "picked": ranked["picked"], "old_picked": osel["picked"], "table": table}


def steady_gap(gap: list[float]) -> list[float]:
    """양손이 자루를 쥔 구간 근사 — 간격 15 ~ 80 cm 에서 프레임마다 3 cm 미만으로만 변하는 가장 긴 연속 구간의 간격들."""
    best, cur = [], []
    for i in range(1, len(gap)):
        if 15.0 <= gap[i] <= 80.0 and abs(gap[i] - gap[i - 1]) < 3.0:
            cur.append(gap[i])
            if len(cur) > len(best):
                best = list(cur)
        else:
            cur = []
    return best


def sickle_reference(bones: dict, ik_target: str | None, grip: dict) -> dict:
    """Vesper 운영 낫 애니 — 같은 측정(candidate_metrics · 계획의 대상 띠)으로 손목 간격 · 양손 구간 · 궤적 폭 · 손 겹침 · 꼬임 · 머리 근접 · 관통(비교
    기준 — 관통은 이 실행의 대상 리그 · 메시로)."""
    params = {"assets": SICKLE_REFS, "skeleton": VESPER, "profile_bones": RetargetPipe.profile_bones(bones), "profile_positions": True}
    params.update({"body_clearance": {"mesh": VESPER_MESH_01, "ik_rig": ik_target}} if ik_target else {"checks": ["numeric"]})
    items = must(editor("validate_animation", **params), "validate sickle references")["assets"]
    out = {}
    for asset, item in zip(SICKLE_REFS, items):
        m = RetargetPipe.candidate_metrics(item, bones, None, None, grip["target_cm"], grip["tolerance_cm"]["target"])
        pos = item["numeric"]["profile"]["position_cm"]
        gap = [norm(sub(a, b)) for a, b in zip(pos[bones["hand_l"]], pos[bones["hand_r"]])]
        steady = steady_gap(gap)
        v = vesper_metrics(m)
        out[asset.rsplit("/", 1)[1]] = {"length": item["numeric"].get("length"), "gap_p50": r2(pct(gap, 0.5)), "gap_min_max": [r2(min(gap)), r2(max(gap))],
                                        "steady_pct": round(100.0 * len(steady) / len(gap), 1),
                                        "steady_gap": [r2(min(steady)), r2(pct(steady, 0.5)), r2(max(steady))] if steady else None,
                                        "grip_band_pct": (m.get("grip") or {}).get("grip_pct"), "width": v["width"], "width_mid": v["width_mid"],
                                        "raise": v["raise"], "swing_peak": v["swing_peak"], "hand_contact": v["hand_contact"],
                                        "cross_pct": v["cross_pct"], "swapped_pct": v["swapped_pct"], "head_pct": v["head_pct"], "head_min_cm": v["head_min_cm"],
                                        "penetration_pct": v["penetration_pct"], "status": item.get("status")}
    return out


def within_limits(v: dict) -> list[str]:
    """SCYTHE_LIMITS 를 넘는 항목 — 값이 없으면 그것도 넘는 것으로 본다(못 재면 통과시키지 않는다)."""
    keys = {"cross_pct": "cross_pct", "head_pct": "head_pct", "penetration_pct": "penetration_pct"}
    return [f"{k} {v.get(src)} > {SCYTHE_LIMITS[k]:g}" for k, src in keys.items() if v.get(src) is None or v[src] > SCYTHE_LIMITS[k]]


def bvh_rest_arms(path: str) -> dict | None:
    """Kimodo BVH(표준 T 포즈) 계층 오프셋 → 기준 포즈 어깨 관절 폭 · 팔 길이(motion_metrics.arm_dims) — local_ai.SOMA_ARMS 상수 확인용."""
    pos, stack, pending = {}, [], None
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith(("ROOT", "JOINT")):
            pending = s.split()[1]
        elif s.startswith("End Site"):
            pending = "<end>"
        elif s == "{":
            stack.append(pending)
            pending = None
        elif s == "}":
            stack.pop()
        elif s.startswith("OFFSET") and stack and stack[-1] != "<end>":
            parent = next((n for n in reversed(stack[:-1]) if n != "<end>"), None)
            off = [float(x) for x in s.split()[1:4]]
            pos[stack[-1]] = [off[i] + (pos[parent][i] if parent else 0.0) for i in range(3)]
        elif s.startswith("MOTION"):
            break
    roles = {"shoulder_l": "LeftArm", "shoulder_r": "RightArm", "elbow_l": "LeftForeArm", "elbow_r": "RightForeArm", "hand_l": "LeftHand", "hand_r": "RightHand"}
    return motion_metrics.arm_dims(pos, roles)


def map_rows(rows: list[dict], grip: dict) -> list[dict]:
    """후보마다 간격 사상 예측(소스 2차 손목 간격 p50 → 대상) vs Vesper 실측 p50 — 사상이 리타깃을 맞히는가."""
    out = []
    for x in rows:
        src, ves = x["source"]["gap_p50"], x["vesper"]["gap_p50"]
        pred = None if src is None else round(motion_metrics.map_gap(grip["map"], src), 2)
        out.append({"index": x["index"], "seed": x["seed"], "source_p50": src, "predicted_p50": pred, "vesper_p50": ves,
                    "error_cm": None if pred is None or ves is None else round(pred - ves, 2), "ratio": None if not src or ves is None else round(ves / src, 4)})
    return out


def section_regrip() -> None:
    print(f"== regrip — recorded {SCYTHE_JOB} (generation spacing 60 · version-4 band × pelvis scale FAILED) with the version-5 band (no assets)")
    base = ROOT / "Saved" / "AnimGen" / "TestRuns" / SCYTHE_JOB_RUN
    old = json.loads((base / "jobs" / f"{SCYTHE_JOB}.json").read_text(encoding="utf-8"))
    osel = old["selection"]
    old_plan = json.loads((base / "plans" / f"{old['plan_id']}.json").read_text(encoding="utf-8"))
    inputs = next(s for s in old_plan["candidates"][0]["steps"] if s["step"] == "select")["inputs"]
    work = old["work_path"]
    ik_target = f"{work}/IK_Target" if f"{work}/IK_Target" in old["intermediate_assets"] else None
    diags: list[dict] = []
    bones = {**RetargetPipe.selection_bones(EditorClient(), VESPER, diags), "from": "template_chains"}
    for d in diags:
        print(f"   diag[{d['level']}] {d['code']}: {d['message'][:200]}")
    grip = motion_metrics.grip_spacing(motion_metrics.gap_map(local_ai.SOMA_ARMS, bones["arm_dims"]), source_cm=inputs["grip_spacing_cm"])
    print(f"   recorded generation spacing {inputs['grip_spacing_cm']} cm · arm dims SOMA {local_ai.SOMA_ARMS} → Vesper {bones['arm_dims']} · map {grip['map']} → "
          f"Vesper band {grip['target_band_cm']} (version 4: {(osel['candidates'][0]['metrics']['grip'] or {}).get('band_cm')})")
    cands = sorted(osel["candidates"], key=lambda c: c["index"])
    params = {"assets": [c["asset"] for c in cands], "sources": [c["source"] for c in cands], "skeleton": VESPER,
              "profile_bones": RetargetPipe.profile_bones(bones), "profile_positions": True, "fingers": {"retargeter": osel["retargeter"]},
              "source_pelvis": local_ai.SOMA_PELVIS, "source_feet": local_ai.SOMA_FEET, "body_clearance": {"mesh": VESPER_MESH_01, "ik_rig": ik_target}}
    before = dirty_count()
    items = must(editor("validate_animation", **params), "validate recorded scythe candidates")["assets"]
    rows = [{"index": c["index"], "seed": c["seed"], "source": c["source"], "asset": c["asset"], "status": item.get("status", "PASSED"),
             "metrics": RetargetPipe.candidate_metrics(item, bones, inputs["grip_window_s"], None, grip["target_cm"], grip["tolerance_cm"]["target"])}
            for c, item in zip(cands, items)]
    ranked = selection.rank(rows, osel["weights"], grip_on=True, swing_on=True)
    table = candidate_table({**ranked, "candidates": sorted(ranked["candidates"], key=lambda c: c["index"])}, old["cursor"]["values"]["generated"])
    mapped = {m["index"]: m for m in map_rows(table, grip)}
    for x, o in zip(table, cands):
        v, mp = x["vesper"], mapped[x["index"]]
        x["old"] = {"rank": o["rank"], "score": o["score"], "grip_pct": (o["metrics"].get("grip") or {}).get("grip_pct"), "penalties": o["penalties"]}
        x["map"] = mp
        print(f"   #{x['index']} seed {x['seed']} rank {x['rank']} score {x['score']} (was {o['rank']} · {o['score']}) · Vesper grip {x['old']['grip_pct']} → "
              f"{v['grip_pct']}% in {v['band']} · gap p50 {v['gap_p50']} (source {mp['source_p50']} → map {mp['predicted_p50']}, error {mp['error_cm']}, ratio "
              f"{mp['ratio']}) · cross {v['cross_pct']} · head {v['head_pct']} · pen {v['penetration_pct']} · limits {within_limits(v) or 'ok'}")
        print(f"        penalties {x['penalties']} (was {o['penalties']})")
        check(mp["error_cm"] is not None and abs(mp["error_cm"]) <= MAP_TOLERANCE_CM,
              f"#{x['index']} gap map predicts the Vesper wrist gap p50 within {MAP_TOLERANCE_CM:g} cm ({mp['predicted_p50']} vs {mp['vesper_p50']})")
    picked = next(x for x in table if x["index"] == ranked["picked"]["index"])
    print(f"   picked {ranked['picked']} (was seed {osel['picked']['seed']})")
    check(picked["vesper"]["grip_pct"] is not None and picked["vesper"]["grip_pct"] >= GRIP_REACHED_PCT,
          f"picked seed {picked['seed']}: Vesper wrist gap within the version-5 band {picked['vesper']['band']} on {picked['vesper']['grip_pct']}% "
          f"(≥ {GRIP_REACHED_PCT:g} — no GRIP_NOT_REACHED; version 4 had {picked['old']['grip_pct']}%)")
    over = within_limits(picked["vesper"])
    check(not over, f"picked seed {picked['seed']} stays within the scythe limits {SCYTHE_LIMITS} {over}")
    check(dirty_count() == before, "measuring the recorded candidates left the dirty count unchanged")
    STATE["regrip"] = {"job_id": SCYTHE_JOB, "grip_spacing": grip, "bones_arm_dims": bones["arm_dims"], "soma_arms": local_ai.SOMA_ARMS,
                       "picked": ranked["picked"], "old_picked": osel["picked"], "weights": ranked["weights"], "table": table}


def section_scythe() -> None:
    print(f"== scythe — Vesper's weapon basis: '{SCYTHE_PROMPT[:60]}…' · target spacing {SCYTHE_TARGET_SPACING_CM:g} cm · 4 candidates (seeds 20261025 ~ 28)")
    r = run_refine("scythe", "AS_Vesper_Sickle_KimodoSlashPick", flagged(candidates=4, refine={"grip": {"target_spacing_cm": SCYTHE_TARGET_SPACING_CM}}),
                   prompt=SCYTHE_PROMPT, family="Sickle", description="양손으로 낫을 들어 대각선으로 베고 전투 자세로 돌아온다 (Kimodo 시험 — 낫 기준)")
    if not r:
        return
    s = steps_of(r["plan"]["candidates"][0])
    rule = next(x for x in s["generate"]["inputs"]["refine"]["rules"] if x["flag"] == "two_hand_weapon_grip")
    grip = s["select"]["inputs"]["grip_spacing"] or {}
    print(f"   grip spacing {json.dumps(grip, ensure_ascii=False)} · rule {rule['spacing_from']}")
    check(rule.get("target_spacing_cm") == SCYTHE_TARGET_SPACING_CM and grip.get("target_cm") == SCYTHE_TARGET_SPACING_CM
          and rule["spacing_cm"] == grip.get("source_cm") and rule.get("band_cm") == grip.get("source_band_cm") and rule.get("spacing_map") == grip.get("map")
          and rule["spacing_from"].startswith("request target_spacing_cm"),
          f"plan: target spacing {SCYTHE_TARGET_SPACING_CM:g} cm → generation {rule['spacing_cm']} cm (map {grip.get('map')}) — the generate rule and the "
          f"select band {grip.get('target_band_cm')} are one value")
    soma = bvh_rest_arms(r["generated"]["candidates"][0]["bvh"])
    check(soma is not None and all(abs(soma[k] - local_ai.SOMA_ARMS[k]) <= 0.01 for k in soma),
          f"SOMA_ARMS constant {local_ai.SOMA_ARMS} = this run's Kimodo BVH reference pose {soma}")
    sel = r["selection"]
    rows = candidate_table(sel, r["generated"])
    print_table(rows)
    print(f"   picked {sel['picked']}")
    again = selection.rank([{k: c[k] for k in ("index", "seed", "status", "metrics")} for c in sel["candidates"]], sel["weights"],
                           grip_on=sel["grip_on"], swing_on=sel["swing_on"])
    check(len(sel["candidates"]) == 4 and again["picked"] == sel["picked"], "4 candidates measured · recomputing the record picks the same")
    wrists = vesper_wrists([x["asset"] for x in rows])
    gen = {c["index"]: c for c in r["generated"]["candidates"]}
    for x in rows:
        sx, vx = x["source"], x["vesper"]
        vx["bend"] = wrists.get(x["asset"])
        follow = (sx["follow"] or {}).get("grip_target_error_cm") or {}
        print(f"   #{x['index']} Vesper wrist bend L {vx['bend']['l']} · R {vx['bend']['r']} · grip target error {follow} · refine grip stats "
              f"{((gen[x['index']].get('refine') or {}).get('grip') or {}).get('stats')}")
        check(sx["grip_pct"] is not None and sx["grip_pct"] >= GRIP_REACHED_PCT,
              f"#{x['index']} source wrist gap within the generation band {grip.get('source_band_cm')} on {sx['grip_pct']}% (≥ {GRIP_REACHED_PCT:g}) — "
              f"gap p50 {sx['gap_p50']}")
        check((sx["smooth"] or {}).get("sigma_frames") == 1.0 and sx["jitter"] and max(sx["jitter"]) < max(sx["jitter_unsmoothed"]),
              f"#{x['index']} A: smoothed — source zigzag {sx['jitter_unsmoothed']} → {sx['jitter']}")
        # 축 정정 — 2차 목표가 1차보다 손을 뒤바꾸지 않는다(처음 축은 1차 0 ~ 5 % → 목표 85 ~ 93 %)
        tc = sx["target_crossed_pct"] or {}
        check(tc.get("targets") is not None and tc["targets"] <= (tc.get("pass1") or 0.0) + 5.0 and (sx["target_axis_from"] or {}).get("wrist_line"),
              f"#{x['index']} grip targets on the pass-1 wrist line {sx['target_axis_from']} — crossed (shoulder axis) pass 1 {tc.get('pass1')} → "
              f"targets {tc.get('targets')}% (≤ +5)")
    mapped = map_rows(rows, grip)
    for mp in mapped:
        print(f"   #{mp['index']} gap map: source p50 {mp['source_p50']} → predicted {mp['predicted_p50']} vs Vesper {mp['vesper_p50']} (error {mp['error_cm']}, "
              f"ratio {mp['ratio']})")
        check(mp["error_cm"] is not None and abs(mp["error_cm"]) <= MAP_TOLERANCE_CM,
              f"#{mp['index']} gap map predicts the Vesper wrist gap p50 within {MAP_TOLERANCE_CM:g} cm ({mp['predicted_p50']} vs {mp['vesper_p50']})")
    picked = next(x for x in rows if x["index"] == sel["picked"]["index"])
    ref = sickle_reference(sel["bones"], r["assets"]["ik_target"], grip)
    for name, v in ref.items():
        print(f"   ref {name}: {v}")
        over = within_limits(v)
        check(not over, f"operating {name} is within the scythe limits {SCYTHE_LIMITS} (the limits are not too strict) {over}")
    steady = [v["steady_gap"][1] for v in ref.values() if v["steady_gap"]]
    pv = picked["vesper"]
    check(pv["grip_pct"] is not None and pv["grip_pct"] >= GRIP_REACHED_PCT, f"picked: Vesper wrist gap within the band {pv['band']} on {pv['grip_pct']}% "
          f"(gap p50 {pv['gap_p50']} cm · operating sickle two-hand segments p50 {steady})")
    check(pv["hand_contact"] is not None, f"picked: hand contact recorded {pv['hand_contact']}")
    # 정정 — 꼬임 · 손-머리 근접 · 관통이 운영 낫 기준 상한 안(지난 실행: Vesper 꼬임 91.7 · 머리 41.7 · 관통 75.2 % 를 PASS 로 넘겼다)
    over = within_limits(pv)
    check(not over, f"picked (seed {picked['seed']}): Vesper cross {pv['cross_pct']}% · head {pv['head_pct']}% (min {pv['head_min_cm']} cm) · penetration "
          f"{pv['penetration_pct']}% within {SCYTHE_LIMITS} {over}")
    ps = picked["source"]
    check(ps["cross_pct"] is not None and ps["cross_pct"] <= SCYTHE_LIMITS["cross_pct"] and ps["head_pct"] is not None and ps["head_pct"] <= SCYTHE_LIMITS["head_pct"],
          f"picked: source pass 2 cross {ps['cross_pct']}% · head {ps['head_pct']}% within the limits")
    clean = [x["seed"] for x in rows if not within_limits(x["vesper"])]
    print(f"   candidates within the limits: {clean} of {[x['seed'] for x in rows]}")
    # 최종 = 잰 후보
    v = profile(r["final"], r["assets"]["source_anim"], r["assets"]["ik_target"], r["assets"]["retargeter"])
    sf = summarize(v)
    check(abs((sf["gap_cm"]["p50"] or 0) - (pv["gap_p50"] or 0)) <= 0.1, f"final asset = the measured candidate (gap p50 {sf['gap_cm']['p50']} vs {pv['gap_p50']} cm)")
    check(v["status"] in ("PASSED", "PASSED_WITH_WARNINGS"), f"final validate_animation {v['status']} · warnings {sf['warnings']}")
    lims = [lim["code"] for lim in r["job"]["limitations"]]
    check("GRIP_NOT_REACHED" not in lims, f"no GRIP_NOT_REACHED (limitations {lims})")
    order = sorted((x for x in rows if x["rank"]), key=lambda x: x["rank"])
    STATE["scythe"] = {"job_id": r["job"]["job_id"], "asset": r["final"], "seconds": r["seconds"], "kimodo_seconds": r["generated"]["seconds"],
                       "prompt": SCYTHE_PROMPT, "target_spacing_cm": SCYTHE_TARGET_SPACING_CM, "grip_spacing": grip, "soma_bvh_arms": soma, "gap_map": mapped,
                       "table": rows, "picked": sel["picked"], "weights": sel["weights"],
                       "thresholds": sel["thresholds"], "best_width_arm_ratio": sel.get("best_width_arm_ratio"), "top": [x["asset"] for x in order[:3]],
                       "reference": ref, "limitations": lims, "final_check": sf, "limits": SCYTHE_LIMITS, "within_limits": clean}


def section_e3() -> None:
    print("== e3 — prompt only ('feet shoulder-width apart'), no flags, same seed")
    r = run_refine("e3", "AS_Vesper_Sword_KimodoSlashStance", flagged(), prompt=E3_PROMPT, constraints={})
    if not r:
        return
    v = profile(r["final"], r["assets"]["source_anim"], r["assets"]["ik_target"], r["assets"]["retargeter"])
    s = summarize(v)
    try:
        previous = json.loads((ROOT / "Tools" / "mcp" / "anim_gen_phase8_1_state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    ref = (STATE.get("exp1") or previous.get("exp1") or {}).get("resolve") or {}
    print(f"   e3 Vesper stance {s['stance_ratio']} vs reference {ref.get('stance_ratio')} · gap {s['gap_cm']} · arms {s['arms']}")
    STATE["e3"] = {"job_id": r["job"]["job_id"], "asset": r["final"], "seconds": r["seconds"], "vesper": s, "reference_stance": ref.get("stance_ratio")}
    check(s["stance_ratio"]["p90"] is not None, f"e3: stance ratio p90 {s['stance_ratio']['p90']} recorded")


def section_dirty() -> None:
    print("== hashes · content · dirty (after)")
    if "hashes" in STATE:
        changed = [p for p, h in STATE["hashes"].items() if sha256(p) != h]
        check(not changed, f"kept reference asset · target skeleton · mesh .uasset SHA-256 unchanged ({len(STATE['hashes'])} files) {changed}")
    if "dirty_before" in STATE:
        check(dirty_count() == STATE["dirty_before"], f"unsaved packages unchanged ({STATE['dirty_before']}) — every write was saved")
    if "content_before" in STATE:
        new = [p for p in content_changes() if p not in STATE["content_before"]]
        run_dir = "Content/" + RUN.removeprefix("/Game/") + "/"
        outside = [p for p in new if not p.startswith(run_dir)]
        print(f"   new Content changes {len(new)} (outside this run's folder: {outside})")
        check(not outside, "Content/ changes are only this run's folder")
        STATE["content_new"] = new


SECTIONS = {"hashes": section_hashes, "exp1": section_exp1, "plan": section_plan, "refine": section_refine, "lead": section_lead,
            "select": section_select, "recompute": section_recompute, "regrip": section_regrip, "scythe": section_scythe, "e3": section_e3,
            "dirty": section_dirty}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(SECTIONS), help="comma separated: " + ",".join(SECTIONS))
    args = ap.parse_args()
    t0 = time.time()
    names = [n.strip() for n in args.only.split(",")]
    for name in names:
        SECTIONS[name]()
    STATE["seconds"] = round(time.time() - t0, 1)
    out = ROOT / "Tools" / "mcp" / "anim_gen_phase8_1_state.json"
    try:
        merged = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        merged = {}
    merged.setdefault("runs", {})[STAMP] = {"sections": names, "failures": len(FAILS), "seconds": STATE["seconds"], "run": RUN}
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
