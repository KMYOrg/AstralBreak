"""AI 애니 생성 Phase 9-5a · 9-5b — 다양한 스켈레톤(U8-a · U8-b · U8-d = U7-c · U8-c) 에디터 통합 테스트 (지침서 §14 Phase 9 '9-5a' · '9-5b' · 로드맵 §10 · §6).

    D:/UE5Projects/AstralBreak/Tools/mcp/.venv/Scripts/python.exe -X utf8 -B -u D:/UE5Projects/AstralBreak/Tools/mcp/anim_gen_phase9_5_test.py [--only ...] [--targets ...]

뜬 에디터(AnimGraphMcp)를 쓴다. 대상 = Vesper(기준 — 지난 통합과 같은 값이어야 한다) + 표준 2(IdaFaber 남성 · UE5 Manny) + 비표준 Narmaya(9-5b — 템플릿 없음 ·
수동 체인 대상 리그 · 루트 스케일 100). 표준 대상은 지난 실행과 출력이 정확히 같아야 한다(same_output). 새 애셋은
/Game/Animation/Test/AIAnimation/P95Run<시각>/ 에만 쓴다(Job 캡처는 Tools/mcp/results/capture/<job>/). 대상 스켈레톤 · 메시 · 무기 · 장비 DA · 운영 애니는
읽기만 한다. 섹션:
  hashes   — (맨 앞) 대상 스켈레톤 · 메시 · 무기 · 장비 DA · 운영 낫 Attack2 SHA-256 · Content/ git 상태 · 미저장 수
  targets  — 대상마다 inspect_skeleton(details · 손가락 체인 제안): 메시 짝 · 본 수 · 무기 소켓 · 템플릿 체인 · 측정 본 원천(selection_bones) ·
             팔 · 다리 치수 · scale · 정면 · 손 본 기준 회전(무기 부착을 옮길 수 있는지)
  combined — 대상마다 phase8_4 합본과 같은 Job 2 건(저장된 Kimodo BVH → fix.ops 다리 → 리타깃 → timing → body_fit → 검증 → 캡처, 낫은 부착) —
             판정 항목은 phase8_4 combined 와 같다(접지 고정 · 미끄러짐 · 바닥 · 다리끼리 · 위팔 마무리 · 매끈화 · 캡처) + 다리 모델 예측 vs 실측 +
             대상별 기준값(정점 목표 · 매끈화 기준 · 한계 · 시간 보정 배율 = Vesper) · Vesper 출력 = 지난 실행(프로필 위치 · 회전 정확히 같음)
  existing — 대상마다 운영 Vesper 낫 Attack2 → 그 대상(리타깃) + fix.body(낫 파지 띠 · 무기) — 8-4b 기준 1 ~ 5(Job 기록으로). Vesper 는 리타깃 없음
  rtg      — 리타기터 구성별 다리 모델(U7-c): 다리만 Job(BVH → fix.ops 다리 → 리타깃, match_existing) 예측(fix.source 대상 모델) vs 실측(fix.target) 두 발 디딘
             발 좌우 비 · 접지 미끄러짐 · 다리 op + ops default · 재사용 리타기터는 계획 거부(FIX_LEGS_NEEDS_MATCH_EXISTING), 임포트 경로의 재사용은 위험만:
             같은 소스로 만든 RTG 는 실행 성공 · 다른 소스 RTG 는 실행 때 INCOMPATIBLE_MESH(C++ 는 본 이름으로 잰다)
  facing   — (9-5b, 대상 쪽 정면 맞춤) SB(+X 정면 · 템플릿 없음 · 루트 스케일 100 · 머리 분리 메시)에 운영 Attack2(리타기터 facing_yaw_deg) · 저장된 BVH(blender 가 대상
             정면으로 돌림) — 리타깃 · 캡처만(fix.body 없음), 골반 이동 방향 = Vesper 를 정면 차만큼 돌린 것
  dirty    — (맨 뒤) 해시 불변 · 미저장 수 그대로 · Content/ 변경은 실행 폴더뿐
판정 항목 미달은 실패 수에 넣지 않고 [miss] 로 찍어 state criteria 에 남긴다(U8 결과 표 — Vesper 대비 새 미달의 원인 분류는 보고서). 실패(FAIL)는
시험 무결성(해시 · 미저장 · 실행 폴더 밖 변경 · 시험 코드 예외)만. 요약은 Tools/mcp/anim_gen_phase9_5_state.json. 수치 · 캡처는 판정 근거일 뿐(§16-9).
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
STATE_DIR = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P95Run{STAMP}"
os.environ["ANIM_GEN_STATE_DIR"] = str(STATE_DIR)

from anim_gen import body_model as bmod  # noqa: E402
from anim_gen import bvh as bvh_mod  # noqa: E402
from anim_gen import motion_metrics as mm  # noqa: E402
from anim_gen import weapon as wp  # noqa: E402
from anim_gen.editor import EditorClient, package_path  # noqa: E402
from anim_gen.providers.builtin import RetargetPipe, pelvis_arg  # noqa: E402
from anim_gen.service import Service  # noqa: E402
from anim_gen.store import Store  # noqa: E402

VESPER = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
MESH = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
CM = "/Game/Assets/CombatMasterAnimBundle/Demo/Characters"
# Narmaya(pl1400) 수동 체인 — Phase 1 픽스처와 같은 값(+X 가 왼쪽). 이름 = 소스 체인 → 정확 매핑. 손가락은 finger_chain_suggestion 을 더한다
NARMAYA_CHAINS = [
    {"name": "Root", "start": "pl1400", "end": "pl1400"},
    {"name": "Spine", "start": "_001", "end": "_0031"},
    {"name": "Neck", "start": "_0041", "end": "_0041"},
    {"name": "Head", "start": "_0051", "end": "_0051"},
    {"name": "LeftClavicle", "start": "_00a", "end": "_00a"},
    {"name": "LeftArm", "start": "_00b", "end": "_00d", "goal": "LeftHandIK"},
    {"name": "RightClavicle", "start": "_006", "end": "_006"},
    {"name": "RightArm", "start": "_007", "end": "_009", "goal": "RightHandIK"},
    {"name": "LeftLeg", "start": "_012", "end": "_015", "goal": "LeftFootIK"},
    {"name": "RightLeg", "start": "_00e", "end": "_011", "goal": "RightFootIK"},
]
SB_ROOT = "CH_P_EVE_01_Body_LOD0_Skeleton"
SB_CHAINS = [
    {"name": "Root", "start": SB_ROOT, "end": SB_ROOT},
    {"name": "Spine", "start": "Bip001-Spine", "end": "Bip001-Spine2"},
    {"name": "Neck", "start": "Bip001-Neck", "end": "Bip001-Neck"},
    {"name": "Head", "start": "Bip001-Head", "end": "Bip001-Head"},
    {"name": "LeftClavicle", "start": "Bip001-L-Clavicle", "end": "Bip001-L-Clavicle"},
    {"name": "LeftArm", "start": "Bip001-L-UpperArm", "end": "Bip001-L-Hand", "goal": "LeftHandIK"},
    {"name": "RightClavicle", "start": "Bip001-R-Clavicle", "end": "Bip001-R-Clavicle"},
    {"name": "RightArm", "start": "Bip001-R-UpperArm", "end": "Bip001-R-Hand", "goal": "RightHandIK"},
    {"name": "LeftLeg", "start": "Bip001-L-Thigh", "end": "Bip001-L-Toe0", "goal": "LeftFootIK"},
    {"name": "RightLeg", "start": "Bip001-R-Thigh", "end": "Bip001-R-Toe0", "goal": "RightFootIK"},
]
# 대상 — 키 → 스켈레톤 · 메시 · Hero 이름(애셋 이름 AS_<Hero>_<계열>_…). chains · pelvis = 템플릿이 없는 대상의 수동 체인(요청 retarget.existing_target_rig — 실행 폴더에 만든다)
TARGETS = {
    "vesper": {"skeleton": VESPER, "mesh": MESH, "hero": "Vesper"},
    "ida_m": {"skeleton": "/Game/Assets/IdaFaber/Meshes/Boy/SKEL_UE5_M", "mesh": "/Game/Assets/IdaFaber/Meshes/Boy/SK_StreetDemon_M_01", "hero": "IdaM"},
    "manny": {"skeleton": f"{CM}/Manny_UE5/Meshes/SK_Mannequin", "mesh": f"{CM}/Manny_UE5/Meshes/SKM_Manny_Simple", "hero": "Manny"},
    "narmaya": {"skeleton": "/Game/Assets/Narmaya/pl1400_Skeleton", "mesh": "/Game/Assets/Narmaya/pl1400_Mesh", "hero": "Narmaya", "pelvis": "_000", "chains": NARMAYA_CHAINS},
}
# 정면 맞춤 전용 — combined · existing · rtg 는 돌지 않는다(머리가 분리 메시라 fix.body 를 안 한다)
FACING_TARGETS = {
    "sb": {"skeleton": f"/Game/Assets/SB/{SB_ROOT}", "mesh": "/Game/Assets/SB/CH_P_EVE_01_Body_LOD0", "hero": "SB", "pelvis": "Bip001-Pelvis", "chains": SB_CHAINS, "facing": "+X"},
}
ALL_TARGETS = {**TARGETS, **FACING_TARGETS}
WEAPON = "/Game/Equipment/Weapon/Mesh/SKM_Hero_Sickle"
WEAPON_DATA = ["/Game/Equipment/Weapon/DA_EF_Sickle", "/Game/Equipment/Weapon/Definition/DA_WD_Sickle1"]
WEAPON_ATTACH_JSON = ROOT / "Tools" / "mcp" / "results" / "p84_weapon_attach.json"
P84_STATE = ROOT / "Tools" / "mcp" / "anim_gen_phase8_4_state.json"
T = "/Game/Animation/Test/AIAnimation"
H = "/Game/Animation/Hero/Vesper"
OP_ATTACK2 = f"{H}/Sickle/Actions/AS_Vesper_Sickle_Attack2"
EXISTING_RTG = f"{H}/Retarget/RTG_KatanaToH"   # rtg — 소스가 다른 기존 리타기터(재사용 계획만)
RUN = f"{T}/P95Run{STAMP}"
STATE_FILE = ROOT / "Tools" / "mcp" / "anim_gen_phase9_5_state.json"
LOCAL_AI = ROOT / "Saved" / "AnimGen" / "Import" / "LocalAI"
# phase8_4 합본과 같은 저장된 Kimodo BVH — 이름 → (BVH, 계열)
COMBINED = {"scythe_pick": (LOCAL_AI / "job_20261026_192555_f991aa" / "A1" / "kimodo_03.bvh", "Sickle"),
            "sword_pick": (LOCAL_AI / "job_20261026_180741_c0f5be" / "A1" / "kimodo_00.bvh", "Sword")}
COMBINED_OPS = [{"op": "stance_width"}, {"op": "foot_lock"}]
COMBINED_SLIDE_MAX = 1.0       # 9-4d U6 기준 1 — 합본 접지 미끄러짐 p95(cm/s)
LEG_RATIO_TOL = 0.05           # 두 발 디딘 발 좌우 비(body_fit 전 · 후)
FLOOR_TOL_CM = 0.1
MODEL_RATIO_TOL = 0.1          # 8-3 — 다리 모델 예측 vs 대상 실측 두 발 디딘 발 좌우 비
MODEL_SLIDE_TOL = 1.0          # 8-3 — 접지 미끄러짐 p95(cm/s)
FACING_PLANE_TOL_DEG = 10.0    # 9-5b — 골반 이동 방향 vs Vesper + 정면 차
FACING_SIZE_TOL = 5.0          # 9-5b — 골반 높이 · 이동 거리 / scale vs Vesper(기준 스케일 복원 · 펠비스 부모가 원점이 아닌 SB)
ARM_TARGET = ("hand", "forearm")
UPPER_PCT_TOL, UPPER_DEPTH_TOL_CM = 1.0, 0.5
KEEP_ROT_DEG = 10.0
SOURCE_ARM_CM = 55.85          # phase8_4 sickle_grip — 소스(SOMA) 팔 길이(파지 띠 허용 × 대상 / 소스)
FAILS: list[str] = []
MISSES: list[dict] = []
STATE: dict = {"run": RUN, "state_dir": STATE_DIR.as_posix()}
EDITOR = EditorClient(call=lambda tool, params, timeout=None: bridge.call(tool, params, timeout=timeout or bridge.COMPILE_TIMEOUT))
SERVICE = Service(store=Store(STATE_DIR), editor=EDITOR)
ACTIVE: list[str] = list(TARGETS)


def check(cond: bool, msg: str) -> bool:
    print(("[ ok ] " if cond else "[FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)
    return cond


def crit(target: str, key: str, name: str, ok: bool, msg: str) -> bool:
    """판정 항목 하나 — 미달은 [miss](실패 수 밖, state criteria · misses 에 남긴다)."""
    STATE.setdefault("criteria", {}).setdefault(target, {}).setdefault(key, {})[name] = "ok" if ok else "miss"
    print(("[ ok ] " if ok else "[miss] ") + f"{target} {key} {name}: {msg}")
    if not ok:
        MISSES.append({"target": target, "key": key, "criterion": name, "message": msg})
    return ok


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:3000]}")
        FAILS.append(what)
        raise SystemExit(finish())
    return env["result"]


def editor(tool: str, **params) -> dict:
    return bridge.call(tool, params, timeout=bridge.COMPILE_TIMEOUT)


def dirty_count() -> int:
    return must(editor("get_editor_status"), "status")["dirty_package_count"]


def sha256(path: str) -> str:
    return hashlib.sha256((ROOT / "Content" / (path.removeprefix("/Game/") + ".uasset")).read_bytes()).hexdigest()


def content_changes() -> list[str]:
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", "Content"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8").stdout
    return sorted(line[3:].strip().strip('"') for line in out.splitlines() if line.strip())


def previous() -> dict:
    return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.is_file() else {}


def camel(key: str) -> str:
    return "".join(w.title() for w in key.split("_"))


def guarded(key: str, fn) -> None:
    """한 단위 — 시험 코드 예외는 실패로 남기고 다음으로(긴 실행이 한 곳에서 멈추지 않게)."""
    try:
        fn()
    except SystemExit:
        raise
    except Exception as err:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        check(False, f"{key}: test error {type(err).__name__}: {err}")


def run_job(req: dict, what: str) -> tuple[dict, dict]:
    """계획 → 실행 → 끝까지 기다림. (계획 후보 요약, Job) — 계획에 후보가 없거나 Job 이 실패해도 돌려준다(U8 결과 표의 칸)."""
    env = SERVICE.plan_motion_generation(request=req)
    if not env.get("ok"):
        err = env.get("error") or {}
        print(f"   {what}: plan refused {json.dumps(err, ensure_ascii=False)[:1500]}")
        return {"candidates": 0, "plan_error": {k: err.get(k) for k in ("code", "message")} | {"details": str(err.get("details"))[:600]}}, {}
    plan = env["result"]
    if not plan["candidates"]:
        print(f"   {what}: no executable plan — excluded {json.dumps(plan['excluded'], ensure_ascii=False)[:1500]}")
        return {"candidates": 0, "excluded": plan["excluded"]}, {}
    cand = plan["candidates"][0]
    summary = {"candidates": len(plan["candidates"]), "steps": [s["step"] for s in cand.get("steps") or []], "risks": cand.get("risks"),
               "expected_limitations": [lm["code"] for lm in cand.get("expected_limitations") or []]}
    t0 = time.time()
    env = SERVICE.generate_motion(plan_id=plan["plan_id"], save=True)
    job = env["result"] if env["ok"] else env["error"]["details"]["job"]
    while job["status"] == "RUNNING" and time.time() - t0 < 1200:
        time.sleep(2.0)
        env = SERVICE.get_generation_status(job_id=job["job_id"])
        job = env["result"] if env["ok"] else env["error"]["details"].get("job", job)
    job["_seconds"] = round(time.time() - t0, 1)
    print(f"   {what}: job {job['job_id']} {job['status']} ({job['_seconds']} s)")
    if job["status"] != "SUCCEEDED":
        print(f"   error: {json.dumps(job.get('error'), ensure_ascii=False)[:2000]}")
    return summary, job


def job_record(summary: dict, job: dict) -> dict:
    """Job 의 표 칸 — 상태 · 오류 · 사슬 · 위험 · 한계 · 경고 코드."""
    if not job:
        return {"status": "NOT_PLANNED", "plan": summary}
    warns = sorted({d.get("code") for d in job.get("diagnostics") or [] if d.get("level") in ("warning", "error")} - {None})
    return {"job": job["job_id"], "status": job["status"], "seconds": job.get("_seconds"), "chain": job.get("chain"), "plan": summary,
            "error": {k: (job.get("error") or {}).get(k) for k in ("cause", "reason", "message")} if job.get("error") else None,
            "limitations": [lm["code"] for lm in job.get("limitations") or []], "warnings": warns, "assets": job.get("generated_assets")}


# ---- 대상 사실 ----
_INFO: dict[str, dict] = {}


def info(key: str) -> dict:
    """inspect_skeleton(skeleton + 메시, details · 손가락 체인 제안) + selection_bones(파이프라인과 같은 측정 본 원천) + 대상 리그(수동 체인 대상)."""
    if key not in _INFO:
        tgt = ALL_TARGETS[key]
        env = editor("inspect_skeleton", skeleton=tgt["skeleton"], skeletal_mesh=tgt["mesh"], details=True, suggest_finger_chains=True)
        if not env.get("ok"):
            # 메시 · 스켈레톤이 맞지 않으면 스켈레톤만으로(메시 짝은 targets 표에 미달로)
            print(f"   {key}: inspect with mesh failed {json.dumps(env.get('error'), ensure_ascii=False)[:400]} — skeleton only")
            env = editor("inspect_skeleton", skeleton=tgt["skeleton"], details=True, suggest_finger_chains=True)
        res = must(env, f"inspect {key}")
        rig = None
        if tgt.get("chains"):
            fingers = (res.get("finger_chain_suggestion") or {}).get("chains") or []
            made = must(editor("create_ik_rig", skeletal_mesh=tgt["mesh"], asset_path=f"{RUN}/Rig/IK_{tgt['hero']}", mode="manual", pelvis=tgt["pelvis"],
                               chains=tgt["chains"] + fingers, save=True), f"{key} manual rig")
            rig = {"rig": package_path(made["asset_path"]), "mesh": tgt["mesh"]}
            print(f"   {key}: manual rig {rig['rig']} — pelvis {made.get('pelvis')} · chains {len(made.get('chains') or [])}")
        diags: list[dict] = []
        bones = RetargetPipe.selection_bones(EDITOR, tgt["skeleton"], diags, "e0", rig)
        _INFO[key] = {"inspect": res, "bones": bones, "bone_diags": diags, "rig": rig}
    return _INFO[key]


def rig_args(key: str) -> dict:
    """요청 retarget 의 대상 리그 — 표준 대상은 키가 없다(파이프가 자동 캐릭터라이즈, 지난 실행과 같은 요청)."""
    rig = info(key)["rig"]
    return {"existing_target_rig": rig["rig"]} if rig else {}


def rest_of(res: dict) -> dict:
    return {b["name"]: b.get("ref_component") or {} for b in res.get("bones") or []}


def scale_of(target: str) -> float:
    """기준 크기 = 골반 기준 포즈 높이 / 100(파이프라인 scale 과 같은 뜻)."""
    pelvis = ((info(target)["bones"].get("leg_dims") or {}).get("rest") or {}).get("pelvis")
    return pelvis[2] / 100.0 if pelvis else 1.0


def uasset(path: str) -> bool:
    return (ROOT / "Content" / (path.removeprefix("/Game/") + ".uasset")).is_file()


def sickle_grip(key: str) -> dict:
    """phase8_4 와 같은 낫 파지 띠 — 간격 60 cm(무기 자루) ± GRIP_TOL × 대상 팔 길이 / 소스 팔 길이."""
    arm = (info(key)["bones"].get("arm_dims") or {}).get("arm_cm") or 47.66
    return {"spacing_cm": 60.0, "tolerance_cm": round(mm.GRIP_TOL_CM * arm / SOURCE_ARM_CM, 2)}


def tr(d: dict):
    return (tuple(d["quat_xyzw"]), tuple(d["location"]), tuple(d["scale"]))


def rotator(q) -> list[float]:
    """UE FQuat::Rotator — [pitch, yaw, roll]° (phase8_4 와 같은 식)."""
    x, y, z, w = q
    sing = z * x - w * y
    yaw = math.degrees(math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z)))
    if sing < -0.4999995:
        return [-90.0, yaw, ((-yaw - 2.0 * math.degrees(math.atan2(x, w))) + 180.0) % 360.0 - 180.0]
    if sing > 0.4999995:
        return [90.0, yaw, ((yaw - 2.0 * math.degrees(math.atan2(x, w))) + 180.0) % 360.0 - 180.0]
    return [math.degrees(math.asin(2.0 * sing)), yaw, math.degrees(math.atan2(-2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y)))]


def offset_of(t) -> dict:
    return {"location": [round(v, 4) for v in t[1]], "rotation": [round(v, 4) for v in rotator(t[0])], "scale": [round(v, 4) for v in t[2]]}


def sickle_attach(key: str) -> dict:
    """낫 부착 — 무기 메시 = AttachOffset · AttachTransform · 소켓(WeaponHandR) · hand_r(phase8_4 sickle_attachment 와 같은 식). 대상에 그 소켓이 없으면
    소켓의 손 본 상대 변환(Vesper 값)을 offset 에 합쳐 손 본에 직접 붙인다 — 운영 애셋(소켓 · DA)은 바꾸지 않는다(결정 ③)."""
    att = json.loads(WEAPON_ATTACH_JSON.read_text(encoding="utf-8"))
    family = att["family"]["actors_to_spawn"][0]
    offset = bmod.compose(tr(att["definition"]["attach_offset"]), tr(family["attach_transform"]))
    socket = att["socket"]["name"]
    names = {s.get("name") for s in info(key)["inspect"].get("sockets") or []}
    if socket in names:
        return {"socket": socket, "offset": offset_of(offset), "from": "socket"}
    in_hand = bmod.compose(offset, tr(att["socket"]["relative"]))
    if not ALL_TARGETS[key].get("chains"):
        return {"bone": att["socket"]["bone"], "offset": offset_of(in_hand), "from": "bone + Vesper socket"}
    # 손 본 축이 다른 대상(9-5b) — 무기를 Vesper 손 틀 기준으로 옮겨 대상 손 틀에 붙이고(위치 = 손 크기 비), 대상 손 본 공간으로(부모 스케일이 있으면 그대로 나뉜다)
    vb, tb = info("vesper")["bones"], info(key)["bones"]
    vf, vsize = hand_frame("vesper")
    tf, tsize = hand_frame(key)
    vhand = rest_transform("vesper", vb["hand_r"])
    q, t, s = bmod.relative(bmod.compose(in_hand, vhand), vf)
    placed = bmod.compose((q, tuple(v * tsize / vsize for v in t), s), tf)
    return {"bone": tb["hand_r"], "offset": offset_of(bmod.relative(placed, rest_transform(key, tb["hand_r"]))), "from": "hand frame + Vesper socket"}


def rest_transform(key: str, bone: str) -> tuple:
    r = rest_of(info(key)["inspect"])[bone]
    return (wp.quat_from_rotator(r["r"]), tuple(float(v) for v in r["t"]), tuple(float(v) for v in r.get("s") or (1.0, 1.0, 1.0)))


def hand_frame(key: str) -> tuple:
    """오른손 기하 틀(컴포넌트, 스케일 없음) — X = 손목 → 중지 뿌리, Y = 소지 뿌리 → 검지 뿌리(X 에 수직), 원점 = 손목 + 손 크기(손목 ↔ 중지 뿌리 cm). 본 축과 무관하다."""
    res = info(key)["inspect"]
    chains = {c["name"]: c["start"] for c in (res.get("finger_chain_suggestion") or {}).get("chains") or []}
    rest = rest_of(res)
    pos = lambda b: tuple(float(v) for v in rest[b]["t"])  # noqa: E731
    wrist = pos(info(key)["bones"]["hand_r"])
    middle, index, pinky = pos(chains["RightMiddle"]), pos(chains["RightIndex"]), pos(chains["RightPinky"])
    size = bmod._norm(bmod._sub(middle, wrist))
    x = bmod._scale(bmod._sub(middle, wrist), 1.0 / size)
    across = bmod._sub(index, pinky)
    y = bmod._sub(across, bmod._scale(x, bmod._dot(across, x)))
    y = bmod._scale(y, 1.0 / bmod._norm(y))
    return (quat_from_axes(x, y, bmod._cross(x, y)), wrist, (1.0, 1.0, 1.0)), size


def quat_from_axes(x, y, z) -> tuple:
    """정규 직교 축(열 = x, y, z) → 쿼터니언 (x, y, z, w)."""
    m00, m10, m20, m01, m11, m21, m02, m12, m22 = *x, *y, *z
    w = math.sqrt(max(0.0, 1.0 + m00 + m11 + m22)) / 2.0
    qx = math.sqrt(max(0.0, 1.0 + m00 - m11 - m22)) / 2.0
    qy = math.sqrt(max(0.0, 1.0 - m00 + m11 - m22)) / 2.0
    qz = math.sqrt(max(0.0, 1.0 - m00 - m11 + m22)) / 2.0
    return bmod.qnormalize((math.copysign(qx, m21 - m12), math.copysign(qy, m02 - m20), math.copysign(qz, m10 - m01), w))


def sickle_weapon(key: str) -> dict:
    """phase8_4 sickle_weapon 과 같은 요청 weapon(왼손 손잡이 = E0 제안 선분 · 끝 TraceEnd) — 부착만 대상별."""
    seg = json.loads(P84_STATE.read_text(encoding="utf-8"))["e0"]["grip_proposal"]["segment"]
    att = sickle_attach(key)
    return {"mesh": WEAPON, "attach": {k: v for k, v in att.items() if k != "from"}, "lead_hand": "right",
            "grips": [{"hand": "left", "segment": {"from": seg["from"], "to": seg["to"]}, "rotation_tol_deg": 10.0}], "tip": {"socket": "TraceEnd"}}


def hashed() -> list[str]:
    keys = ACTIVE + (list(FACING_TARGETS) if "facing" in (STATE.get("sections") or []) else [])
    return sorted({p for k in keys for p in (ALL_TARGETS[k]["skeleton"], ALL_TARGETS[k]["mesh"])} | {WEAPON, OP_ATTACK2, EXISTING_RTG} | set(WEAPON_DATA))


# ---- 섹션 ----
def section_hashes() -> None:
    print("== target skeletons · meshes · weapon · DA · operational Attack2 hashes · content · dirty (before)")
    STATE["hashes"] = {p: sha256(p) for p in hashed()}
    STATE["content_before"] = content_changes()
    STATE["dirty_before"] = dirty_count()
    print(f"   {len(STATE['hashes'])} files hashed · Content changes before {len(STATE['content_before'])} · dirty {STATE['dirty_before']}")


def section_targets() -> None:
    print("== targets: inspect_skeleton (mesh pair · bones · sockets · template chains · measured bones · dims · scale · facing · hand rest)")
    out = STATE.setdefault("targets", {})
    for key in ACTIVE:
        def one(key=key):
            i = info(key)
            res, bones = i["inspect"], i["bones"]
            tgt = ALL_TARGETS[key]
            tm = res.get("template_match") or {}
            rest = rest_of(res)
            leg = bones.get("leg_dims") or {}
            pelvis_z = ((leg.get("rest") or {}).get("pelvis") or [None, None, None])[2]
            facing = RetargetPipe.skeleton_facing(res, tgt.get("chains"))
            fingers = (res.get("finger_chain_suggestion") or {}).get("chains") or []
            row = {"skeleton": tgt["skeleton"], "mesh": res.get("mesh"), "mesh_source": res.get("mesh_source"), "meshes": len(res.get("meshes") or []),
                   "mesh_paired": (res.get("mesh") or "").split(".")[0] == tgt["mesh"], "bone_count": res.get("bone_count"), "root": res.get("root_bone"),
                   "sockets": sorted(s.get("name") for s in res.get("sockets") or []),
                   "template": {k: tm.get(k) for k in ("used", "name", "percent", "pelvis")} | {"chains": [c.get("name") for c in tm.get("chains") or []]},
                   "bones_from": bones.get("from"), "bone_diags": [d.get("code") for d in i["bone_diags"]],
                   "roles": {k: bones.get(k) for k in ("hand_l", "hand_r", "elbow_l", "elbow_r", "shoulder_l", "shoulder_r", "hip_l", "hip_r", "foot_l", "foot_r",
                                                       mm.HEAD_ROLE)},
                   "arm_dims": bones.get("arm_dims"), "leg_dims": {k: v for k, v in leg.items() if k != "rest"}, "pelvis_rest_z_cm": pelvis_z,
                   "scale": round(pelvis_z / 100.0, 4) if pelvis_z else None, "facing": facing, "finger_chains": len(fingers),
                   "hand_r_rest": rest.get(bones.get("hand_r") or "hand_r"), "ik_rigs": len(res.get("ik_rigs") or []),
                   "retargeters": len(res.get("retargeters") or []), "animation_count": res.get("animation_count"), "sickle_attach": sickle_attach(key)}
            out[key] = row
            print(f"   {key}: mesh {row['mesh']} ({row['mesh_source']}, paired {row['mesh_paired']}) · bones {row['bone_count']} · template {row['template']} · "
                  f"measured bones from {row['bones_from']} {row['bone_diags']} · arm {row['arm_dims']} · legs {row['leg_dims']} · scale {row['scale']} · "
                  f"facing {facing} · finger chains {row['finger_chains']} · sickle attach {row['sickle_attach']['from']}")
            crit(key, "targets", "mesh_pair", row["mesh_paired"], f"mesh {row['mesh']} is the given {tgt['mesh']}")
            if tgt.get("chains"):
                crit(key, "targets", "rig_chains", not tm.get("used") and bones.get("from") == "ik_rig" and bones.get("pelvis") == tgt["pelvis"],
                     f"no template · measured bones from {row['bones_from']} · pelvis {bones.get('pelvis')} · feet {row['roles']['foot_l']} {row['roles']['foot_r']}")
            else:
                crit(key, "targets", "template", bool(tm.get("used")) and bones.get("from") == "template_chains",
                     f"template chains {row['template']['chains']} · measured bones from {row['bones_from']}")
            crit(key, "targets", "facing", facing.get("axis") == tgt.get("facing", "+Y"), f"rest pose faces {facing.get('axis')} (want {tgt.get('facing', '+Y')})")
            crit(key, "targets", "dims", bool(bones.get("arm_dims")) and bool(leg.get("leg_cm")) and bool(pelvis_z), "arm · leg dims and pelvis height measured")
        guarded(f"targets_{key}", one)


def fit_body(key: str, family: str) -> dict:
    return {"grip": sickle_grip(key)} if family == "Sickle" else {}


def summarize_body(rec: dict) -> dict:
    keys = ("target_pen_pct_max", "target_depth_max", "head_neck", "hands_pen_pct_max", "hands_depth_max", "upper_arm", "head_near", "grip",
            "swing_peak_cm_s", "attack_width", "cross_pct", "zigzag_max", "feet", "status")
    return {w: {k: (rec.get(w) or {}).get(k) for k in keys} for w in ("before", "after")}


def legs_model(job: dict) -> dict | None:
    """다리 보정 대상 모델 예측(fix.source legs — 소스에서 푼 대상 쪽 예측) vs 리타깃 뒤 실측(fix.target) — 8-3 기준."""
    fix = job.get("fix") or {}
    src = next((a for a in fix.get("source") or [] if a.get("op") == "legs"), None)
    tgt = fix.get("target")
    if not src or not tgt:
        return None
    pa, ta = src.get("after") or {}, tgt
    pr, tr_ = (pa.get("ratio") or {}).get("planted_max"), (ta.get("ratio") or {}).get("planted_max")
    ps, ts = pa.get("slide_p95") or {}, ta.get("slide_p95") or {}
    return {"space": src.get("space"), "scale": src.get("scale"), "ik": src.get("ik"), "predicted": {"planted_max": pr, "slide_p95": ps},
            "measured": {"planted_max": tr_, "slide_p95": ts}, "target_dims": src.get("target_dims"),
            "ratio_diff": None if pr is None or tr_ is None else round(abs(pr - tr_), 3),
            "slide_diff": {s: None if ps.get(s) is None or ts.get(s) is None else round(abs(ps[s] - ts[s]), 2) for s in "lr"}}


def profile_tracks(target: str, asset: str) -> dict:
    """프로필 위치 · 회전(본 전부 — select 측정 본 + 다리) — 출력 비교용."""
    tgt = TARGETS[target]
    names = sorted(set(RetargetPipe.profile_bones(info(target)["bones"])) | {"thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r", "ball_l", "ball_r", "pelvis"})
    env = editor("validate_animation", assets=[asset], skeleton=tgt["skeleton"], profile_bones=names, profile_positions=True, profile_rotations=True)
    if not env.get("ok"):
        raise RuntimeError(f"profile {asset}: {json.dumps(env.get('error'), ensure_ascii=False)[:800]}")
    prof = env["result"]["assets"][0]["numeric"]["profile"]
    return {"position_cm": prof["position_cm"], "rotations": prof.get("rotations")}


def judge_same_output(target: str, key: str, asset: str | None, last: str | None) -> None:
    """표준 대상은 비표준 지원(9-5b)이 바꾸지 않는다 — 지난 실행의 같은 Job 출력과 프로필이 정확히 같아야 한다. 대상 리그 대상은 지난 값이 없다."""
    if ALL_TARGETS[target].get("chains"):
        return
    if not asset or not last or not uasset(last):
        print(f"   {target} {key}: previous output {last} is gone — skipping the identity check")
        return
    a, b = profile_tracks(target, asset), profile_tracks(target, last)
    crit(target, key, "same_output", a == b, f"{asset} profile (positions · rotations, {len(a['position_cm'])} bones) identical to {last}")


def judge_style(target: str, key: str, job: dict, rec: dict, row: dict, *, timed: bool) -> None:
    """대상별 기준값(9-5a) — 기준 몸은 흔적이 없다(계획 · Job 비트 같음), 다른 대상은 옮긴 값 · 몸 비율 · 시간 보정이 있으면 한계."""
    tm, sm = (job.get("timing") or {}), rec.get("smooth_speed") or {}
    lims = row["limitations"]
    if target == "vesper":
        crit(target, key, "style_none", "target_peak" not in tm and "speed_ref_cm" not in sm and "TARGET_STYLE_FROM_REFERENCE" not in lims,
             f"reference body — no moved values (timing {tm.get('target_peak')} · smooth {sm.get('speed_ref_cm')})")
        return
    want = round(info(target)["bones"]["arm_dims"]["arm_cm"] / scale_of(target) / (info("vesper")["bones"]["arm_dims"]["arm_cm"] / scale_of("vesper")), 4)
    tp = tm.get("target_peak") or {}
    ok_peak = not timed or (tp.get("from") == "body_ratio" and abs(tp.get("factor", 0.0) - want) <= 1e-3 and abs(tp.get("value", 0.0) - 1200.0 * want) <= 1.0)
    crit(target, key, "style_moved", ok_peak and abs(sm.get("factor", 0.0) - want) <= 1e-3 and ("TARGET_STYLE_FROM_REFERENCE" in lims) == timed,
         f"body ratio {want} — peak {tp} · smooth ref {sm.get('speed_ref_cm')} (× {sm.get('factor')}) · TARGET_STYLE_FROM_REFERENCE {'TARGET_STYLE_FROM_REFERENCE' in lims}")


def judge_model(target: str, key: str, lm: dict | None) -> None:
    if not lm:
        crit(target, key, "u7c_model", False, "no fix.source legs / fix.target in the Job")
        return
    slide_ok = all(v is None or v <= MODEL_SLIDE_TOL for v in lm["slide_diff"].values())
    crit(target, key, "u7c_model", lm["space"] == "target_model" and lm["ratio_diff"] is not None and lm["ratio_diff"] <= MODEL_RATIO_TOL and slide_ok,
         f"leg model ({lm['space']}, scale {lm['scale']}) predicted planted ratio {lm['predicted']['planted_max']} vs measured {lm['measured']['planted_max']} "
         f"(Δ {lm['ratio_diff']} ≤ {MODEL_RATIO_TOL}) · slide p95 predicted {lm['predicted']['slide_p95']} vs measured {lm['measured']['slide_p95']} "
         f"(Δ {lm['slide_diff']} ≤ {MODEL_SLIDE_TOL})")


def measure(target: str, asset: str, extra: list[str], legs: bool = False, ik_rig: str | None = None) -> dict:
    """validate_animation 한 번 — select 측정 본 + extra profile 위치 (+ legs body_clearance — 9-4d 다리끼리)."""
    tgt = TARGETS[target]
    names = sorted(set(RetargetPipe.profile_bones(info(target)["bones"])) | set(extra))
    spec = {}
    if legs:
        spec = {"body_clearance": {"mesh": tgt["mesh"], **({"ik_rig": ik_rig} if ik_rig else {}), "map_rule": bmod.MAP_RULE, "legs": True}}
    env = editor("validate_animation", assets=[asset], skeleton=tgt["skeleton"], profile_bones=names, profile_positions=True, **pelvis_arg(info(target)["bones"]), **spec)
    if not env.get("ok"):
        # 대상 하나의 측정 실패는 그 단위의 시험 오류(guarded) — 실행 전체를 멈추지 않는다
        raise RuntimeError(f"measure {asset}: {json.dumps(env.get('error'), ensure_ascii=False)[:800]}")
    return env["result"]["assets"][0]


def floor_of(item: dict, feet: dict, leg_cm: float, floor: dict | None = None) -> dict:
    """phase8_4 floor_of 와 같은 정의 — feet = {('foot'|'ball', side): 본}."""
    prof = item["numeric"]["profile"]
    pos, times = prof["position_cm"], prof["times"]
    cont = {k: mm.detect_contacts(pos[b], times, 2, leg_cm) for k, b in feet.items() if pos.get(b)}
    out = {}
    for j in ("foot", "ball"):
        hs = [pos[feet[(j, s)]][k][2] for s in "lr" if (j, s) in cont for k in range(len(times)) if cont[(j, s)][k]]
        level = (floor or {}).get(j, {}).get("floor") if floor else (min(hs) if hs else None)
        air = [pos[feet[(j, s)]][k][2] for s in "lr" if (j, s) in cont for k in range(len(times))
               if not (cont.get(("foot", s)) or [False] * len(times))[k] and not (cont.get(("ball", s)) or [False] * len(times))[k]]
        out[j] = {"floor": round(level, 3) if level is not None else None, "air_margin": round(min(air) - level, 3) if level is not None and air else None}
    return out


def floor_and_legs(target: str, key: str, rec: dict, ik_rig: str | None) -> dict:
    """9-4d 기준 2 — 바닥(공중 프레임 발목 · 발볼 ≥ min(접지 최저, 원래) − 0.1) · 다리끼리(C++ legs — 새 관통 없음). 발볼 본 = Job legs.balls."""
    b = info(target)["bones"]
    balls = (rec.get("legs") or {}).get("balls") or {}
    feet = {("foot", s): b[f"foot_{s}"] for s in "lr"} | {("ball", s): (balls.get(s) or {}).get("bone") for s in "lr" if (balls.get(s) or {}).get("bone")}
    leg_cm = (b.get("leg_dims") or {}).get("leg_cm") or 90.0
    bf = measure(target, rec["source"], [v for v in feet.values()], legs=True, ik_rig=ik_rig)
    af = measure(target, rec["asset"], [v for v in feet.values()], legs=True, ik_rig=ik_rig)
    fb = floor_of(bf, feet, leg_cm)
    fa = floor_of(af, feet, leg_cm, fb)
    ok = all(fa[j]["air_margin"] is None or fb[j]["air_margin"] is None or fa[j]["air_margin"] >= min(fb[j]["air_margin"], 0.0) - FLOOR_TOL_CM
             for j in ("foot", "ball"))
    crit(target, key, "d2_floor", ok, f"floor ankle {fb['foot']} → {fa['foot']} · ball {fb['ball']} → {fa['ball']}")
    pairs = lambda item: ((item["body_clearance"].get("parts") or {}).get("legs") or {}).get("pairs") or []  # noqa: E731
    lb = {"pen_pct_max": max((p["frames_over_penetration_pct"] for p in pairs(bf)), default=0.0), "pairs": len(pairs(bf))}
    la = {"pen_pct_max": max((p["frames_over_penetration_pct"] for p in pairs(af)), default=0.0), "pairs": len(pairs(af))}
    crit(target, key, "d2_legs", la["pen_pct_max"] <= lb["pen_pct_max"] + 1e-9 and la["pairs"] > 0, f"legs ↔ other leg pen % {lb} → {la}")
    return {"floor": {"before": fb, "after": fa}, "leg_pairs": {"before": lb, "after": la}}


def section_combined() -> None:
    print("== combined (U8-a): per target the phase8_4 combined Job — saved Kimodo BVH → fix.ops legs → retarget → timing → body_fit → validate → capture")
    out = STATE.setdefault("combined", {})
    last = previous().get("combined") or {}
    for target in ACTIVE:
        for key, (bvh, family) in COMBINED.items():
            def one(target=target, key=key, bvh=bvh, family=family):
                if not check(bvh.is_file(), f"{key}: saved Kimodo BVH exists ({bvh.name})"):
                    return
                tgt = TARGETS[target]
                sickle = family == "Sickle"
                req = {"target_skeleton": tgt["skeleton"], "target_mesh": tgt["mesh"], "hero": tgt["hero"], "family": family,
                       "animation_name": f"AS_{tgt['hero']}_{family}_P95{camel(key)}Combined", "description": "Phase 9-5a 통합 — 다른 대상 합본",
                       "motion_category": "weapon_action", "loop": False, "frame_rate": 30, "output_path": RUN, "provider": "blender",
                       "motion_file": {"path": bvh.as_posix()}, "retarget": {"body_clearance": "measure", **rig_args(target)},
                       "fix": {"ops": COMBINED_OPS, "timing": True, "body": fit_body(target, family)},
                       "review": {"capture": {"count": 6, "sequence": True}}, **({"weapon": sickle_weapon(target)} if sickle else {})}
                before_dirty = dirty_count()
                summary, job = run_job(req, f"{target} {key} combined")
                row = job_record(summary, job)
                out.setdefault(target, {})[key] = row
                check(dirty_count() == before_dirty, f"{target} {key} combined: job left no dirty package ({before_dirty})")
                if not crit(target, key, "job", job.get("status") == "SUCCEEDED", f"status {row['status']} · error {row.get('error')} · plan {summary}"):
                    return
                rec = (job.get("fix") or {}).get("body") or {}
                legs = rec.get("legs") or {}
                lims = row["limitations"]
                cap = (job.get("review") or {}).get("capture") or {}
                tm = job.get("timing") or {}
                lm = legs_model(job)
                ik_rig = (info(target)["rig"] or {}).get("rig") or f"{RUN}/Work/{job['job_id']}/A1/IK_Target"
                ik_rig = ik_rig if uasset(ik_rig) else None   # 없으면 C++ 가 메시 자동 캐릭터라이즈로 체인을 찾는다
                row.update({"asset": rec.get("asset"), "source": rec.get("source"), "body": summarize_body(rec), "legs": legs,
                            "smooth_speed": rec.get("smooth_speed"), "upper_arm_finish": rec.get("upper_arm"), "converge": rec.get("converge"),
                            "grip": {k: (rec.get("grip") or {}).get(k) for k in ("mode", "lead", "band_cm", "runs_s", "frames", "keep")},
                            "remains": rec.get("remains"), "timing": {k: tm.get(k) for k in ("applied", "rate", "length", "cut", "before", "after", "target_peak")},
                            "legs_model": lm, "review_capture": {k: cap.get(k) for k in ("ok", "sheet", "dir", "facing", "reason")} |
                            {"attachments": len(cap.get("attachments") or []), "animation": (cap.get("animation") or {}).get("path")}})
                crit(target, key, "chain", row["chain"] == ["blender", "retarget", "direct_key", "body_fit", "review"] and bool(rec.get("asset")),
                     f"chain {row['chain']} · asset {rec.get('asset')}")
                crit(target, key, "limitations", {"FIX_ON_SOURCE_SKELETON", "TIMING_CHANGED_LENGTH", "BODY_FIT_APPROXIMATE", "LEGS_PATH_REDESIGNED"} <= set(lims),
                     f"limitations {lims}")
                crit(target, key, "legs_auto", bool(legs.get("swing_path", {}).get("on")) and bool(legs.get("windows")),
                     f"legs auto → on ({legs.get('swing_path')}) · windows {[(w['side'], w['frames'], w['zigzag_model']) for w in legs.get('windows') or []]}")
                sm = rec.get("smooth_speed") or {}
                crit(target, key, "smooth_speed", bool(sm.get("on")) and sm.get("frames", 0) > 0, f"smooth_speed {sm}")
                up = rec.get("upper_arm") or {}
                torso = ("pelvis", "belly", "chest")
                up_b = max((v["depth_max"] for k, v in ((rec.get("before") or {}).get("upper_arm") or {}).items() if k.split("|")[2] in torso), default=0.0)
                up_a = max((v["depth_max"] for k, v in ((rec.get("after") or {}).get("upper_arm") or {}).items() if k.split("|")[2] in torso), default=0.0)
                deep_in = up_b > 1.1 * (up.get("cap_cm") or 4.0) + 1.0
                crit(target, key, "upper_cap", up.get("mode") == "cap" and (not deep_in or up_a < up_b - 1.0),
                     f"upper arm ↔ torso {up_b} → {up_a} cm · cap {up.get('cap_cm')} · frames {up.get('frames')}")
                crit(target, key, "capture", bool(cap.get("ok") or cap.get("sheet")) and (not sickle or len(cap.get("attachments") or []) == 1),
                     f"review.capture {cap.get('ok')} · sheet {cap.get('sheet')} · attachments {len(cap.get('attachments') or [])}")
                pins = legs.get("pins") or {}
                crit(target, key, "pins_hold", bool(pins.get("on")) and "LEGS_PINS_HELD" in lims and (legs.get("hold") or {}).get("pin_error_cm_max", 1.0) <= 0.05,
                     f"pins {pins} · hold {legs.get('hold')}")
                fb, fa = (rec.get("before") or {}).get("feet") or {}, (rec.get("after") or {}).get("feet") or {}
                slide = lambda f, s: ((f.get("slide_p95") or {}).get(s) or 0.0)  # noqa: E731
                crit(target, key, "d1_slide", all(slide(fa, s) <= COMBINED_SLIDE_MAX for s in "lr")
                     and abs((fa.get("planted_ratio_max") or 0.0) - (fb.get("planted_ratio_max") or 0.0)) <= LEG_RATIO_TOL,
                     f"contact slide p95 {fb.get('slide_p95')} → {fa.get('slide_p95')} cm/s (≤ {COMBINED_SLIDE_MAX}) · planted ratio "
                     f"{fb.get('planted_ratio_max')} → {fa.get('planted_ratio_max')}")
                a = rec.get("after") or {}
                scale = scale_of(target)
                row["ik_rig"] = ik_rig
                crit(target, key, "c1_body", (a.get("target_pen_pct_max") or 0.0) <= 2.0 and (a.get("target_depth_max") or 0.0) <= 2.0 * scale,
                     f"hand/forearm ↔ body {(rec.get('before') or {}).get('target_pen_pct_max')}% → {a.get('target_pen_pct_max')}% · depth "
                     f"{a.get('target_depth_max')} cm (≤ {2.0 * scale:.2f})")
                crit(target, key, "c1_head", ((a.get("head_neck") or {}).get("pen_pct") or 0.0) == 0.0, f"head/neck {a.get('head_neck')}")
                row.update(floor_and_legs(target, key, rec, ik_rig))
                judge_model(target, key, lm)
                judge_style(target, key, job, rec, row, timed=True)
                # 같은 회전 → 같은 시간 보정: 정점 목표를 몸 비율로 옮기면 배율이 Vesper 와 같다(같은 실행에 Vesper 가 있을 때)
                base = (out.get("vesper") or {}).get(key) or {}
                if target != "vesper" and (base.get("timing") or {}).get("rate"):
                    crit(target, key, "same_rate", abs((tm.get("rate") or 0.0) - base["timing"]["rate"]) <= 0.02, f"time-warp rate {tm.get('rate')} vs Vesper {base['timing']['rate']}")
                judge_same_output(target, key, rec.get("asset"), ((last.get(target) or {}).get(key) or {}).get("asset"))
            guarded(f"combined_{target}_{key}", one)


def judge_fit(target: str, key: str, rec: dict) -> None:
    """8-4b 기준 1 ~ 5 의 Job 기록 판(phase8_4 judge 의 C++ 전 · 후 요약 몫 — 손목 굽힘 · keep 실측 · 루프는 빼고)."""
    b, a = rec.get("before") or {}, rec.get("after") or {}
    scale = scale_of(target)
    pen = 2.0 * scale
    hands = {w: {k: v for k, v in (s.get("hands") or {}).items() if k.split("|")[1] in ARM_TARGET} for w, s in (("before", b), ("after", a))}
    hmax = {w: (max((v["pen_pct"] for v in h.values()), default=0.0), max((v["depth_max"] for v in h.values()), default=0.0)) for w, h in hands.items()}
    worse = [k for k, v in (a.get("upper_arm") or {}).items()
             if v["pen_pct"] > ((b.get("upper_arm") or {}).get(k) or {}).get("pen_pct", 0.0) + UPPER_PCT_TOL
             or v["depth_max"] > ((b.get("upper_arm") or {}).get(k) or {}).get("depth_max", 0.0) + UPPER_DEPTH_TOL_CM]
    grip = rec.get("grip") or {}
    keep = grip.get("keep") or {}
    near = (a.get("head_near") or {}).get("near_pct")
    ratio = lambda x, y: None if not x or y is None else round(y / x - 1.0, 4)  # noqa: E731
    sw, wd = ratio(b.get("swing_peak_cm_s"), a.get("swing_peak_cm_s")), ratio(b.get("attack_width"), a.get("attack_width"))
    zb, za = b.get("zigzag_max"), a.get("zigzag_max")
    fb, fa = b.get("feet") or {}, a.get("feet") or {}
    slide = lambda f, s: ((f.get("slide_p95") or {}).get(s) or 0.0)  # noqa: E731
    pva = rec.get("predicted_vs_after") or {}
    crit(target, key, "c1_body", (a.get("target_pen_pct_max") or 0.0) <= 2.0 and (a.get("target_depth_max") or 0.0) <= pen,
         f"hand/forearm ↔ body {b.get('target_pen_pct_max')}% · {b.get('target_depth_max')} → {a.get('target_pen_pct_max')}% · {a.get('target_depth_max')} cm (≤ {pen:.2f})")
    crit(target, key, "c1_hands", hmax["after"][0] <= 2.0 and hmax["after"][1] <= pen, f"hand/forearm ↔ other hand {hmax['before']} → {hmax['after']}")
    crit(target, key, "c1_head", ((a.get("head_neck") or {}).get("pen_pct") or 0.0) == 0.0, f"head/neck {b.get('head_neck')} → {a.get('head_neck')}")
    crit(target, key, "c1_head_near", near is None or near <= 5.0, f"hand-head near {(b.get('head_near') or {}).get('near_pct')} → {near}% (≤ 5%)")
    crit(target, key, "c1_upper", not worse, f"upper-arm pairs no worse — worse {worse}")
    crit(target, key, "c2_keep", not grip.get("frames") or (keep.get("pos_cm_max") or 0.0) <= scale,
         f"grip frames {grip.get('frames')} · keep p95 {keep.get('pos_cm_p95')} / max {keep.get('pos_cm_max')} cm (≤ {scale:.2f})")
    crit(target, key, "c2_keep_rot", not grip.get("frames") or (keep.get("deg_max") or 0.0) <= KEEP_ROT_DEG, f"keep rotation max {keep.get('deg_max')}° (≤ {KEEP_ROT_DEG})")
    crit(target, key, "c3_feet", not fb or (all(slide(fa, s) <= slide(fb, s) + 0.5 for s in "lr")
                                         and abs((fa.get("planted_ratio_max") or 0.0) - (fb.get("planted_ratio_max") or 0.0)) <= 0.05),
         f"feet slide p95 {fb.get('slide_p95')} → {fa.get('slide_p95')} · planted ratio {fb.get('planted_ratio_max')} → {fa.get('planted_ratio_max')}")
    moved = rec.get("joints_moved_cm") or {}
    crit(target, key, "c4_outside", (moved.get("outside_max") or 0.0) <= 0.1, f"joints outside the correction {moved}")
    crit(target, key, "c4_swing", sw is None or abs(sw) <= 0.05, f"swing peak {b.get('swing_peak_cm_s')} → {a.get('swing_peak_cm_s')} ({sw})")
    crit(target, key, "c4_width", wd is None or abs(wd) <= 0.05, f"attack width {b.get('attack_width')} → {a.get('attack_width')} ({wd})")
    crit(target, key, "c4_zigzag", zb is None or za is None or za <= max(zb * 1.1, zb + 0.3), f"zigzag {zb} → {za}")
    crit(target, key, "c4_cross", b.get("cross_pct") is None or (a.get("cross_pct") or 0.0) <= b["cross_pct"], f"crossed % {b.get('cross_pct')} → {a.get('cross_pct')}")
    crit(target, key, "c5", pva.get("ok", False), f"model prediction vs C++ — off {[k for k, v in (pva.get('pairs') or {}).items() if not v.get('ok')]}")


def section_existing() -> None:
    print("== existing (U8-a): operational Vesper sickle Attack2 → each target (retarget) + fix.body (sickle band · weapon) — criteria 1–5 from the Job record")
    out = STATE.setdefault("existing", {})
    last = previous().get("existing") or {}
    for target in ACTIVE:
        def one(target=target):
            tgt = TARGETS[target]
            req = {"target_skeleton": tgt["skeleton"], "target_mesh": tgt["mesh"], "hero": tgt["hero"], "family": "Sickle",
                   "animation_name": f"AS_{tgt['hero']}_Sickle_P95OpAttack2Fit", "description": "Phase 9-5a 통합 — 운영 Vesper 애니를 다른 대상으로 + fix.body",
                   "motion_category": "weapon_action", "loop": None, "output_path": RUN, "provider": "existing_motion", "reference_animations": [OP_ATTACK2],
                   "fix": {"body": fit_body(target, "Sickle")}, "weapon": sickle_weapon(target), "review": {"capture": {"count": 6, "sequence": True}}}
            if tgt["skeleton"] != VESPER:
                req["retarget"] = {"source_mesh": MESH, **rig_args(target)}
            before_dirty = dirty_count()
            summary, job = run_job(req, f"{target} existing Attack2")
            row = job_record(summary, job)
            out[target] = row
            check(dirty_count() == before_dirty, f"{target} existing: job left no dirty package ({before_dirty})")
            if not crit(target, "existing", "job", job.get("status") == "SUCCEEDED", f"status {row['status']} · error {row.get('error')} · plan {summary}"):
                return
            rec = (job.get("fix") or {}).get("body") or {}
            cap = (job.get("review") or {}).get("capture") or {}
            row.update({"asset": rec.get("asset"), "source": rec.get("source"), "body": summarize_body(rec), "legs": rec.get("legs"),
                        "grip": {k: (rec.get("grip") or {}).get(k) for k in ("mode", "lead", "band_cm", "runs_s", "frames", "keep")}, "remains": rec.get("remains"),
                        "joints_moved_cm": rec.get("joints_moved_cm"), "predicted_vs_after_ok": (rec.get("predicted_vs_after") or {}).get("ok"),
                        "retarget": {k: ((job.get("retarget") or {}).get(k)) for k in ("facing", "retargeter")} if job.get("retarget") else None,
                        "review_capture": {k: cap.get(k) for k in ("ok", "sheet", "dir", "facing", "reason")} | {"attachments": len(cap.get("attachments") or [])}})
            chain = row["chain"] or []
            crit(target, "existing", "chain", ("retarget" in chain) == (tgt["skeleton"] != VESPER) and "body_fit" in chain and bool(rec.get("asset")),
                 f"chain {chain} (retarget only for another skeleton) · asset {rec.get('asset')}")
            crit(target, "existing", "capture", bool(cap.get("ok") or cap.get("sheet")) and len(cap.get("attachments") or []) == 1,
                 f"review.capture {cap.get('ok')} · attachments {len(cap.get('attachments') or [])}")
            judge_fit(target, "existing", rec)
            judge_style(target, "existing", job, rec, row, timed=False)
            judge_same_output(target, "existing", rec.get("asset"), (last.get(target) or {}).get("asset"))
        guarded(f"existing_{target}", one)


def legs_request(target: str, name: str, retarget: dict, fix_ops: list[dict]) -> dict:
    bvh, family = COMBINED["scythe_pick"]
    tgt = TARGETS[target]
    return {"target_skeleton": tgt["skeleton"], "target_mesh": tgt["mesh"], "hero": tgt["hero"], "family": family, "animation_name": f"AS_{tgt['hero']}_{family}_P95{name}",
            "description": "Phase 9-5a 통합 — 리타기터 구성", "motion_category": "weapon_action", "loop": False, "frame_rate": 30, "output_path": RUN, "provider": "blender",
            "motion_file": {"path": bvh.as_posix()}, "retarget": {"body_clearance": "measure", **rig_args(target), **retarget}, "fix": {"ops": fix_ops}}


def refused(target: str, key: str, req: dict, reason: str) -> dict:
    """계획 거부 — 후보 0 · 제외 이유 · 아무것도 만들지 않는다."""
    p = must(SERVICE.plan_motion_generation(request=req), f"plan {key}")
    ex = (p["excluded"] or [{}])[0]
    crit(target, key, "plan_refused", not p["candidates"] and ex.get("reason") == reason, f"candidates {len(p['candidates'])} · excluded {ex.get('cause')} / {ex.get('reason')} (want {reason})")
    return {"candidates": len(p["candidates"]), "excluded": {k: ex.get(k) for k in ("cause", "reason", "message")}}


def section_rtg() -> None:
    print("== rtg (U7-c · U8-d): legs model on the retargeter the job builds · other configurations refused or flagged at plan · reuse measured")
    out = STATE.setdefault("rtg", {})
    for target in ACTIVE:
        def one(target=target):
            summary, job = run_job(legs_request(target, "LegsMatchExisting", {}, COMBINED_OPS), f"{target} legs match_existing")
            row = job_record(summary, job)
            res = out.setdefault(target, {})
            res["match_existing"] = row
            if not crit(target, "rtg_match_existing", "job", job.get("status") == "SUCCEEDED", f"status {row['status']} · error {row.get('error')}"):
                return
            row["legs_model"] = legs_model(job)
            judge_model(target, "rtg_match_existing", row["legs_model"])
            before, content = dirty_count(), content_changes()
            res["ops_default"] = refused(target, "rtg_ops_default", legs_request(target, "LegsOpsDefault", {"ops": "default"}, COMBINED_OPS), "FIX_LEGS_NEEDS_MATCH_EXISTING")
            res["reuse_legs"] = refused(target, "rtg_reuse_legs", legs_request(target, "LegsReuse", {"existing_retargeter": EXISTING_RTG}, COMBINED_OPS), "FIX_LEGS_NEEDS_MATCH_EXISTING")
            check(dirty_count() == before and content_changes() == content, f"{target}: refused plans made nothing (dirty {before} · Content unchanged)")
            # 임포트 경로 재사용(다리 op 없음) — 위험만. 같은 소스로 만든 RTG 는 호환(C++ 는 본 이름으로 잰다) → 실행 성공
            own = f"{RUN}/Work/{job['job_id']}/A1/RTG_Retarget"
            s2, j2 = run_job(legs_request(target, "ReuseSameSource", {"existing_retargeter": own}, []), f"{target} reuse same source")
            r2 = job_record(s2, j2)
            res["reuse_same_source"] = r2
            crit(target, "rtg_reuse_same", "job", j2.get("status") == "SUCCEEDED" and "RETARGET_REUSE_SOURCE_UNCHECKED" in (s2.get("risks") or []),
                 f"status {r2['status']} · risks {s2.get('risks')} · error {r2.get('error')}")
        guarded(f"rtg_{target}", one)
    # 소스가 다른 RTG(운영 Katana → Vesper)를 임포트 경로에 주면 계획은 위험만, 실행 때 C++ 가 거부한다(애셋 · 미저장 없음)
    def foreign():
        before = dirty_count()
        summary, job = run_job(legs_request("vesper", "ReuseForeign", {"existing_retargeter": EXISTING_RTG}, []), "vesper reuse foreign RTG")
        row = job_record(summary, job)
        out.setdefault("vesper", {})["reuse_foreign"] = row
        crit("vesper", "rtg_reuse_foreign", "run_refused", job.get("status") == "FAILED" and "RETARGET_REUSE_SOURCE_UNCHECKED" in (summary.get("risks") or []),
             f"status {row['status']} · risks {summary.get('risks')} · error {row.get('error')}")
        check(dirty_count() == before, f"foreign RTG run left no dirty package ({before})")
    guarded("rtg_foreign", foreign)


def pelvis_motion(target: str, asset: str) -> dict:
    """골반 수평 이동(첫 → 끝)의 방향(°, atan2(y, x)) · 거리 · 첫 프레임 높이(cm) — 정면 맞춤과 크기 복원을 전후 동작으로 잰다. 거리 · 높이는 scale 로 나눠 몸 크기를 뺀다."""
    pelvis = info(target)["bones"].get("pelvis") or "pelvis"
    tgt = ALL_TARGETS[target]
    env = editor("validate_animation", assets=[asset], skeleton=tgt["skeleton"], profile_bones=[pelvis], profile_positions=True, **pelvis_arg(info(target)["bones"]))
    if not env.get("ok"):
        raise RuntimeError(f"pelvis {asset}: {json.dumps(env.get('error'), ensure_ascii=False)[:800]}")
    track = env["result"]["assets"][0]["numeric"]["profile"]["position_cm"][pelvis]
    dx, dy = track[-1][0] - track[0][0], track[-1][1] - track[0][1]
    return {"heading": math.degrees(math.atan2(dy, dx)), "travel": math.hypot(dx, dy) / scale_of(target), "height": track[0][2] / scale_of(target)}


def section_facing() -> None:
    print("== facing (U8-c): SB (+X) — retargeter facing_yaw_deg (Attack2) · blender turns the BVH (motion_file) — retarget · capture only")
    out = STATE.setdefault("facing", {})
    for target, tgt in FACING_TARGETS.items():
        def one(target=target, tgt=tgt):
            i = info(target)
            base = {"target_skeleton": tgt["skeleton"], "target_mesh": tgt["mesh"], "hero": tgt["hero"], "family": "Sickle", "description": "Phase 9-5b 통합 — 대상 쪽 정면 맞춤",
                    "motion_category": "weapon_action", "output_path": RUN, "review": {"capture": {"count": 6, "sequence": True}}}
            bvh, _ = COMBINED["scythe_pick"]
            jobs = {"attack2": {**base, "animation_name": f"AS_{tgt['hero']}_Sickle_P95OpAttack2", "loop": None, "provider": "existing_motion", "reference_animations": [OP_ATTACK2],
                                "retarget": {"source_mesh": MESH, **rig_args(target)}},
                    "bvh": {**base, "animation_name": f"AS_{tgt['hero']}_Sickle_P95Scythe", "loop": False, "frame_rate": 30, "provider": "blender", "motion_file": {"path": bvh.as_posix()},
                            "retarget": {"body_clearance": "measure", **rig_args(target)}}}
            res = out.setdefault(target, {"bones": {k: i["bones"].get(k) for k in ("pelvis", "hand_l", "hand_r", "foot_l", "foot_r", "from")}})
            for key, req in jobs.items():
                before_dirty = dirty_count()
                summary, job = run_job(req, f"{target} {key}")
                row = job_record(summary, job)
                res[key] = row
                check(dirty_count() == before_dirty, f"{target} {key}: job left no dirty package ({before_dirty})")
                if not crit(target, f"facing_{key}", "job", job.get("status") == "SUCCEEDED", f"status {row['status']} · error {row.get('error')} · plan {summary}"):
                    continue
                cap = (job.get("review") or {}).get("capture") or {}
                row["review_capture"] = {k: cap.get(k) for k in ("ok", "sheet", "dir", "facing", "reason")} | {"animation": (cap.get("animation") or {}).get("path")}
                crit(target, f"facing_{key}", "capture", bool(cap.get("ok") or cap.get("sheet")) and cap.get("facing") == tgt["facing"], f"capture {cap.get('sheet')} · facing {cap.get('facing')}")
                if key == "attack2":
                    crit(target, "facing_attack2", "aligned", "FACING_ALIGNED" in row["limitations"], f"limitations {row['limitations']}")
                    asset = (row["assets"] or [None])[-1]
                    if asset:
                        got, ref = pelvis_motion(target, asset), pelvis_motion("vesper", OP_ATTACK2)
                        yaw = bvh_mod.ue_yaw_deg("+Y", tgt["facing"])
                        diff = (got["heading"] - ref["heading"] - yaw + 180.0) % 360.0 - 180.0
                        row["pelvis_motion"] = {"target": got, "vesper": ref, "yaw_deg": yaw, "diff_deg": round(diff, 1)}
                        crit(target, "facing_attack2", "plane", abs(diff) <= FACING_PLANE_TOL_DEG, f"pelvis travel {row['pelvis_motion']} (≤ {FACING_PLANE_TOL_DEG}°)")
                        crit(target, "facing_attack2", "size", abs(got["height"] - ref["height"]) <= FACING_SIZE_TOL and abs(got["travel"] - ref["travel"]) <= FACING_SIZE_TOL,
                             f"pelvis height / scale {round(got['height'], 1)} vs Vesper {round(ref['height'], 1)} · travel / scale {round(got['travel'], 1)} vs {round(ref['travel'], 1)} (≤ {FACING_SIZE_TOL})")
        guarded(f"facing_{target}", one)


def section_dirty() -> None:
    print("== hashes · content · dirty (after)")
    if "hashes" in STATE:
        changed = [p for p, h in STATE["hashes"].items() if sha256(p) != h]
        check(not changed, f"skeletons · meshes · weapon · DA · Attack2 .uasset SHA-256 unchanged ({len(STATE['hashes'])} files, changed {changed})")
    if "dirty_before" in STATE:
        check(dirty_count() == STATE["dirty_before"], f"unsaved packages unchanged ({STATE['dirty_before']})")
    if "content_before" in STATE:
        new = [p for p in content_changes() if p not in STATE["content_before"]]
        outside = [p for p in new if not p.startswith("Content/" + RUN.removeprefix("/Game/") + "/")]
        print(f"   new Content changes {len(new)} (outside the run folder: {outside})")
        check(not outside, "Content/ changes are only this run's folder")
        STATE["content_new"] = len(new)


SECTIONS = {"hashes": section_hashes, "targets": section_targets, "combined": section_combined, "existing": section_existing, "rtg": section_rtg,
            "facing": section_facing, "dirty": section_dirty}


def finish() -> int:
    # 섹션 · 대상 단위로 합친다 — 앞 실행의 다른 섹션 · 대상은 남긴다. 이번 실행은 runs[] 에도
    merged = previous()
    runs = (merged.get("runs") or []) + [{"run": RUN, "sections": STATE.get("sections"), "targets": ACTIVE, "misses": len(MISSES), "fails": len(FAILS)}]
    for key in ("targets", "combined", "existing", "rtg", "facing", "criteria"):
        if isinstance(STATE.get(key), dict):
            base = merged.get(key) or {}
            STATE[key] = {**base, **{k: ({**(base.get(k) or {}), **v} if isinstance(v, dict) and isinstance(base.get(k), dict) and key == "criteria" else v)
                                     for k, v in STATE[key].items()}}
    STATE["misses_by_run"] = {**(merged.get("misses_by_run") or {}), RUN: MISSES}
    merged.update({k: v for k, v in STATE.items() if k not in ("run", "state_dir")})
    merged.update(runs=runs)
    STATE_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"state -> {STATE_FILE.as_posix()}")
    print(f"\n{len(MISSES)} miss(es) (criteria — recorded, not failures)")
    for m in MISSES:
        print(f"  - {m['target']} {m['key']} {m['criterion']}: {m['message'][:240]}")
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print("  - " + f)
    print("PASS" if not FAILS else "FAIL")
    return 0 if not FAILS else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(SECTIONS), help="comma separated: " + ",".join(SECTIONS))
    ap.add_argument("--targets", default=",".join(TARGETS), help="comma separated: " + ",".join(TARGETS))
    args = ap.parse_args()
    ACTIVE[:] = [t.strip() for t in args.targets.split(",") if t.strip()]
    unknown = [t for t in ACTIVE if t not in ALL_TARGETS]
    if unknown:
        print(f"unknown targets {unknown}")
        return 2
    t0 = time.time()
    STATE["sections"] = [s.strip() for s in args.only.split(",")]
    for name in STATE["sections"]:
        SECTIONS[name]()
    STATE["seconds"] = round(time.time() - t0, 1)
    return finish()


if __name__ == "__main__":
    sys.exit(main())
