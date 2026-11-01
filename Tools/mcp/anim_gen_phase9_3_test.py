"""AI 애니 생성 Phase 9-3a — 키 포즈 · 역리타깃(U3-a · U3-b) 실제 Kimodo · Blender · 에디터 통합 테스트
(Docs/AIAnimation/DevelopmentGuide.md §14 Phase 9 '9-3' · FollowUpRoadmap.md §5 U3).

    D:/UE5Projects/AstralBreak/Tools/mcp/.venv/Scripts/python.exe -X utf8 -B -u D:/UE5Projects/AstralBreak/Tools/mcp/anim_gen_phase9_3_test.py [--only ...]

뜬 에디터(AnimGraphMcp 플러그인) · 정책의 Kimodo venv · Blender 를 쓴다. anim_gen 은 같은 프로세스의 Service 로 부르고, 상태는
Saved/AnimGen/TestRuns/P93Run<시각>/ 에, 새 애셋은 /Game/Animation/Test/AIAnimation/P93Run<시각>/ 에만, 캡처는 Tools/mcp/results/capture/P93Run<시각>/.
Kimodo 1건 ≈ RAM 15 GB — 생성 섹션은 순서대로 한 건씩.
섹션:
  hashes   — (맨 앞) 대상 스켈레톤 · 메시 · 원천 운영 애니 .uasset SHA-256 · Content/ git 상태 · 미저장 패키지 수
  plan     — (Kimodo 안 띄움 · 애셋 0 · 더티 0) key_pose 계획: 사슬 맨 앞 key_pose(원천 프레임 · T 포즈 SHA-256 · 리그 규칙) · 생성 패스 · 기한 · 한계,
             막힘(다른 스켈레톤 SAMPLE_SKELETON_MISMATCH · 원천 길이 밖 CONSTRAINT_OUT_OF_RANGE), key_pose 없는 같은 요청은 그 단계가 없다
  src      — 왕복 원천: 검 8-1 표준 프롬프트 · 3초 · seed · 한 패스(관통 보정 off — 순수 FK) → Vesper(Kimodo NPZ 기록)
  roundtrip — src 의 Vesper 를 모든 프레임 전신 키로(origin) → key_pose 파일(역리타깃 SOMA 로컬 회전 · 엉덩)을 src NPZ 와 비교(Kimodo venv):
             SOMA 몸 관절 로컬 각 · FK 관절 위치 · 엉덩 · 방향(p50 · p95 · 최대, 손가락 · 메타카팔 · 끝 · 눈 · 턱 제외) + 촘촘한 키 생성의 재현
  follow   — 운영 낫 Attack1 의 휘두름 정점 자세를 전신 키 하나로(생성 1.2초 · pass1 배치) — 키 프레임 관절 위치 · 떨림(1차 대비) · Vesper 쪽 자세 유사도
  multi    — 같은 원천 3 키(정점 ± 0.3초 → 0.9 · 1.2 · 1.5초) — 성긴 전신 키의 떨림(8-1 수정안 A 의 교훈)
  ee       — 같은 정점의 오른손 · 왼발 · 오른발 end-effector 키(같은 프레임 — 부위가 겹치지 않는다) — 손발 위치 · 회전 추종
  nokey    — 같은 프롬프트 · seed · 키 없음(= follow 의 1차) — Vesper 쪽 유사도 · 캡처 대조
  jitter   — (생성 없음) follow · multi · ee 최종 NPZ 에 σ 1 · 2 스무딩(전체 · 키 둘레 ± 6 · 12 프레임 창) — 키 오차 · 키 둘레 떨림 · 손 정점(대가)
  capture  — follow | nokey 비교 시트(같은 시각) · Attack1 정점 한 장 · APNG
  dirty    — (맨 뒤) 해시 불변 · 미저장 수 그대로 · Content/ 변경은 이번 실행 폴더뿐
생성 섹션의 seed 는 --seed(기본 20261025 — Kimodo 는 결정적). 요약은 Tools/mcp/anim_gen_phase9_3_state.json(섹션 단위로 덮어쓴다).
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
STATE_DIR = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P93Run{STAMP}"
os.environ["ANIM_GEN_STATE_DIR"] = str(STATE_DIR)

from anim_gen import apng, key_pose as kp, timing  # noqa: E402
from anim_gen.providers import local_ai  # noqa: E402
from anim_gen.service import Service  # noqa: E402
from anim_gen.store import Store  # noqa: E402

VESPER = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
VESPER_MESH_01 = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
ATTACK1 = "/Game/Animation/Hero/Vesper/Sickle/Actions/AS_Vesper_Sickle_Attack1"
KATANA = "/Game/Assets/CombatMasterAnimBundle/Animations/HandsomeKatanaAnims/Mannequin_UE4/RootMotion/Attack/Katana_Attack_Slash1"   # 다른 스켈레톤(UE4) — 막힘 확인
RUN = f"/Game/Animation/Test/AIAnimation/P93Run{STAMP}"
OUT = ROOT / "Tools" / "mcp" / "results" / "capture" / f"P93Run{STAMP}"
HASHED = [VESPER, VESPER_MESH_01, ATTACK1]
SEED = 20261025
DURATION = 3.0
AT = 1.2               # 키를 둘 생성 시각(follow · ee) — 3초 클립의 가운데 앞
MULTI_DT = 0.3
SWORD_PROMPT = ("A person holds a sword with both hands, raises it over the right shoulder, slashes diagonally down to the left, "
                "then returns to a fighting stance.")   # 8-1 표준 프롬프트
SCYTHE_PROMPT = ("A person holds a long-handled scythe with both hands, raises it over the right shoulder, slashes diagonally down to the left, "
                 "then returns to a fighting stance.")  # 8-1 낫 기준 프롬프트
# 기준값(시작값 — 사용자 결정 ④: 실측 뒤 확정해 보고). 왕복: FK 위치 p95 ≤ 2 · 최대 ≤ 5 cm, 로컬 각 p95 ≤ 3°. 추종: 키 프레임 p50 ≤ 3 cm
ROUNDTRIP_LIMITS = {"position_p95_cm": 2.0, "position_max_cm": 5.0, "local_p95_deg": 3.0}
FOLLOW_P50_CM = 3.0
# Vesper 측정 본 — 휘두름 정점(timing.summary) · 자세 유사도(골반 기준 · 엉덩 축 yaw 맞춤)
BODY = ["hand_l", "hand_r", "thigh_l", "thigh_r", "foot_l", "foot_r", "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "head"]
POSE_BONES = ["pelvis", "spine_03", "head", "upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r", "thigh_l", "calf_l", "foot_l",
              "thigh_r", "calf_r", "foot_r"]
FAILS: list[str] = []
STATE: dict = {"run": RUN, "state_dir": STATE_DIR.as_posix(), "out": OUT.as_posix()}
SERVICE = Service(store=Store(STATE_DIR))
PACKAGE_DIR = ROOT / "Tools" / "mcp"
# 왕복 — Kimodo venv(torch · numpy)로 key_pose 파일(역리타깃 SOMA 로컬 회전 · 엉덩)을 원천 NPZ 와 비교, 촘촘한 키 생성의 재현(NPZ ↔ NPZ)
ROUNDTRIP_SCRIPT = r"""
import json, sys
import numpy as np
import torch
args = json.loads(sys.argv[1])
sys.path.insert(0, args["package_dir"])
from anim_gen import key_pose as kp
from kimodo.geometry import axis_angle_to_matrix
from kimodo.skeleton.registry import build_skeleton
sk = build_skeleton(77)
names = list(sk.bone_order_names)
src = np.load(args["npz"])
data = json.loads(open(args["key_pose"], encoding="utf-8").read())
item = next(i for i in data["items"] if i["source"] == args["source"])
frames = [k["source_frame"] for k in item["keys"]]
rot = np.array([[k["rotvec"].get(n, [0.0, 0.0, 0.0]) for n in names] for k in item["keys"]], dtype=np.float32)
hips = np.array([k["hips_m"] for k in item["keys"]], dtype=np.float32)
local = axis_angle_to_matrix(torch.from_numpy(rot))
g, p, _ = sk.fk(local, torch.from_numpy(hips))
local, p = local.numpy(), p.numpy()
L0, P0 = src["local_rot_mats"][frames], src["posed_joints"][frames]
body = [names.index(n) for n in kp.BODY_JOINTS]
hip = names.index("Hips")
def ang(a, b):
    rel = np.einsum("...ji,...jk->...ik", a, b)
    return np.degrees(np.arccos(np.clip((np.trace(rel, axis1=-2, axis2=-1) - 1.0) / 2.0, -1.0, 1.0)))
la = ang(local[:, body], L0[:, body])
pd = np.linalg.norm(p[:, body] - P0[:, body], axis=-1) * 100.0
rel = np.linalg.norm((p[:, body] - p[:, [hip]]) - (P0[:, body] - P0[:, [hip]]), axis=-1) * 100.0
li, ri = names.index("LeftLeg"), names.index("RightLeg")
hd = [abs(kp.wrap(kp.heading(p[k, li].tolist(), p[k, ri].tolist()) - kp.heading(P0[k, li].tolist(), P0[k, ri].tolist()))) * 57.2958 for k in range(len(frames))]
sp = lambda v: kp.spread([float(x) for x in np.ravel(v)])
out = {"keys": len(frames), "local_deg": sp(la), "position_cm": sp(pd), "pose_cm": sp(rel), "hips_cm": sp(pd[:, kp.BODY_JOINTS.index("Hips")]),
       "heading_deg": kp.spread(hd),
       "per_joint": {n: {"local": sp(la[:, j]), "position": sp(pd[:, j])} for j, n in enumerate(kp.BODY_JOINTS)}}
if args.get("rt_npz"):
    rt = np.load(args["rt_npz"])
    d = np.linalg.norm(rt["posed_joints"][:, body] - src["posed_joints"][:, body], axis=-1) * 100.0
    out["reproduce_cm"] = sp(d)
print(json.dumps(out))
"""
# 키 둘레 떨림 가르기(생성 없음) — 최종 NPZ 에 σ 스무딩(전체 · 키 둘레 창)을 걸어 키 오차 · 떨림 · 손 정점(대가)을 잰다. 키 프레임의 최종 자세 = 제약 자세
# (Kimodo 후처리가 FullBody 마스크로 맞춘다)라 그 자세와의 차가 키 오차다
JITTER_SCRIPT = r"""
import json, math, sys
import numpy as np
import torch
args = json.loads(sys.argv[1])
sys.path.insert(0, args["package_dir"])
from anim_gen import key_pose as kp
from anim_gen.local_ai import refine
from kimodo.skeleton.registry import build_skeleton
sk = build_skeleton(77)
names = list(sk.bone_order_names)
body = [names.index(n) for n in kp.BODY_JOINTS]
hands = [names.index("LeftHand"), names.index("RightHand")]
def fk(local, root):
    g, p, _ = sk.fk(torch.tensor(np.asarray(local), dtype=torch.float32), torch.tensor(np.asarray(root), dtype=torch.float32))
    return p.numpy()
def quats(mats):
    return np.array([[refine.quat_from_matrix(m) for m in row] for row in mats])
out = {}
for run in args["runs"]:
    d = np.load(run["npz"])
    L, R, P = d["local_rot_mats"], d["root_positions"], d["posed_joints"]
    keys = run["frames"]
    def metrics(Pv):
        err = np.linalg.norm(Pv[keys][:, body] - P[keys][:, body], axis=-1) * 100.0
        speed = np.linalg.norm(np.diff(Pv[:, hands], axis=0), axis=-1) * 100.0 * 30.0
        return {"jitter_p95": kp.key_jitter([(Pv[:, j] * 100.0).tolist() for j in body], keys), "key_err_cm": kp.spread(err.ravel().tolist()),
                "hand_peak_cm_s": round(float(speed.max()), 1)}
    rec = {"final": metrics(P)}
    if run.get("pass1_npz"):
        rec["pass1"] = metrics(np.load(run["pass1_npz"])["posed_joints"])
    q0 = quats(L)
    for sigma in (1.0, 2.0):
        Ls = refine.smooth_rotations(L.tolist(), sigma)
        Rs = np.asarray(refine.smooth_series(R.tolist(), sigma))
        rec[f"global_s{sigma:g}"] = metrics(fk(Ls, Rs))
        qs = quats(Ls)
        for W in (6, 12):
            n = L.shape[0]
            w = np.zeros(n)
            for k in keys:
                for f in range(n):
                    x = abs(f - k) / W
                    if x < 1.0:
                        w[f] = max(w[f], 1.0 - x * x * (3.0 - 2.0 * x))
            qb = []
            for f in range(n):
                row = []
                for j in range(L.shape[1]):
                    a, b = q0[f, j], qs[f, j]
                    if np.dot(a, b) < 0:
                        b = -b
                    q = (1.0 - w[f]) * a + w[f] * b
                    row.append(refine.matrix_from_quat((q / np.linalg.norm(q)).tolist()))
                qb.append(row)
            Rb = (1.0 - w)[:, None] * R + w[:, None] * Rs
            rec[f"window{W}_s{sigma:g}"] = metrics(fk(qb, Rb))
    out[run["name"]] = rec
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
        print(f"   diag[{d['level']}] {d['code']}: {d['message'][:240]}")
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


def gen_request(name: str, prompt: str, family: str, constraints: list[dict] | None = None, **over) -> dict:
    req = {"target_skeleton": VESPER, "target_mesh": VESPER_MESH_01, "hero": "Vesper", "family": family, "animation_name": name,
           "description": f"9-3 시험 {name}", "motion_category": "weapon_action", "loop": False, "frame_rate": 30, "duration_seconds": DURATION,
           "prompt": prompt, "provider": "local_ai", "generation": {"seed": SEED, "constraints": constraints or []},
           "retarget": {"align_mode": "per_bone", "body_clearance": "off"}, "output_path": RUN}
    req.update(over)
    return req


def wait_job(job: dict, limit: float = 1800.0) -> dict:
    t0 = time.time()
    while job["status"] == "RUNNING" and time.time() - t0 < limit:
        time.sleep(1.0)
        env = SERVICE.get_generation_status(job_id=job["job_id"])
        job = env["result"] if env["ok"] else env["error"]["details"].get("job", job)
    return job


def run_job(req: dict, label: str) -> tuple[dict, dict, float]:
    plan = must(SERVICE.plan_motion_generation(request=req), f"plan {label}")
    check(plan["executable"], f"{label}: plan executable (excluded {[(e['provider'], e['reason']) for e in plan['excluded']]})")
    t0 = time.time()
    job = wait_job(must(SERVICE.generate_motion(plan_id=plan["plan_id"], save=True), f"generate {label}"))
    seconds = round(time.time() - t0, 1)
    check(job["status"] == "SUCCEEDED", f"{label} job {job['status']} ({seconds}s)")
    if job["status"] != "SUCCEEDED":
        print(f"   error {json.dumps(job.get('error'), ensure_ascii=False)[:2000]}")
    return plan, job, seconds


def kimodo(script: str, args: dict) -> dict | None:
    python, _ = local_ai.KimodoProvider.paths(SERVICE.policy())
    out = subprocess.run([str(python), "-I", "-c", script, json.dumps(args)], capture_output=True, text=True, encoding="utf-8", timeout=600)
    if out.returncode != 0:
        print(f"[FAIL] Kimodo venv script: {out.stderr[-2000:]}")
        FAILS.append("Kimodo venv script")
        return None
    return json.loads(out.stdout.strip().splitlines()[-1])


def previous() -> dict:
    saved = ROOT / "Tools" / "mcp" / "anim_gen_phase9_3_state.json"
    return json.loads(saved.read_text(encoding="utf-8")) if saved.is_file() else {}


def profile(asset: str, bones: list[str]) -> dict:
    item = must(editor("validate_animation", assets=[asset], skeleton=VESPER, profile_bones=bones, profile_positions=True), f"profile {asset.rsplit('/', 1)[1]}")
    item = item["assets"][0]
    return {"numeric": item["numeric"], "profile": item["numeric"]["profile"]}


def strike_time() -> tuple[float, float, float]:
    """운영 Attack1 의 휘두름 정점(timing.summary — 시간 보정과 같은 정의)."""
    p = profile(ATTACK1, BODY)
    n = p["numeric"]
    summ = timing.summary(p["profile"], hands=("hand_l", "hand_r"), body=BODY, scale=(n.get("pelvis_height_cm") or 100.0) / 100.0,
                          fps=float(n["frame_rate"]), length=float(n["length"]), params=timing.normalize(True))
    return round(float(summ["peak_time"]), 4), float(n["length"]), float(n["frame_rate"])


def pose_at(asset: str, t: float) -> dict:
    """그 시각의 Vesper 자세(골반 기준 위치 · 엉덩 축 수평 방향) — profile 은 프레임 1 부터라 가장 가까운 표본."""
    p = profile(asset, POSE_BONES)["profile"]
    i = min(range(len(p["times"])), key=lambda k: abs(p["times"][k] - t))
    pos = {b: p["position_cm"][b][i] for b in POSE_BONES if b in p["position_cm"]}
    return {"time": p["times"][i], "pos": pos}


def pose_distance(a: dict, b: dict) -> dict:
    """두 Vesper 자세의 차(cm) — 골반을 맞추고 엉덩 축(thigh_r − thigh_l)의 수평 방향을 b 에 맞춘 뒤 본별 거리."""
    def rel(pose):
        c = pose["pos"]["pelvis"]
        return {k: [v[0] - c[0], v[1] - c[1], v[2] - c[2]] for k, v in pose["pos"].items()}
    ra, rb = rel(a), rel(b)
    ha = math.atan2(ra["thigh_r"][1] - ra["thigh_l"][1], ra["thigh_r"][0] - ra["thigh_l"][0])
    hb = math.atan2(rb["thigh_r"][1] - rb["thigh_l"][1], rb["thigh_r"][0] - rb["thigh_l"][0])
    c, s = math.cos(hb - ha), math.sin(hb - ha)
    d = {}
    for k in ra:
        if k in rb and k != "pelvis":
            x, y, z = ra[k]
            d[k] = round(math.dist([x * c - y * s, x * s + y * c, z], rb[k]), 2)
    return {"per_bone": d, **kp.spread(list(d.values()))}


JITTER_BONES = ["hand_l", "hand_r", "head", "pelvis", "foot_l", "foot_r"]


def vesper_jitter(asset: str, frames: list[int]) -> dict:
    """대상(Vesper) 쪽 키 둘레 ± 10 프레임 지그재그(cm/프레임²) — 본별 최대 · 전체 p95(profile 표본 i = 프레임 i + 1 → 트랙 앞에 첫 표본을 한 번 더)."""
    p = profile(asset, JITTER_BONES)["profile"]["position_cm"]
    out = {}
    values = []
    for b in JITTER_BONES:
        track = [p[b][0]] + p[b]
        z = [v for f in frames for v in kp.zigzag_values(track, f - kp.JITTER_HALF_FRAMES, f + kp.JITTER_HALF_FRAMES)]
        values += z
        out[b] = round(max(z), 3) if z else None
    return {"max_by_bone": out, "p95": kp.spread(values)["p95"] if values else None, "max": round(max(values), 3) if values else None}


def follow_of(job: dict) -> tuple[list[dict], dict]:
    gen = job["cursor"]["values"]["generated"]
    sample = (gen.get("candidates") or gen["samples"])[0]
    return (sample.get("key_pose") or {}).get("follow") or [], sample


# ---- 섹션 ----
def section_hashes() -> None:
    print("== hashes · content · dirty (before)")
    STATE["hashes"] = {p: sha256(p) for p in HASHED}
    STATE["content_before"] = content_changes()
    STATE["dirty_before"] = dirty_count()
    print(f"   {len(HASHED)} assets hashed · Content changes before: {len(STATE['content_before'])} · dirty {STATE['dirty_before']}")


def section_plan() -> None:
    print("== plan — key_pose plans (no Kimodo, no assets)")
    before = dirty_count()
    t_star, length, fps = strike_time()
    req = gen_request("AS_Vesper_Sickle_KeyPlan", SCYTHE_PROMPT, "Sickle", [{"type": "key_pose", "asset": ATTACK1, "times": [t_star], "at": [AT]}])
    plan = must(SERVICE.plan_motion_generation(request=req), "plan key_pose")
    cand = plan["candidates"][0]
    kinds = [s["step"] for s in cand["steps"]]
    key, gen = cand["steps"][0]["inputs"], cand["steps"][1]["inputs"]
    check(kinds[:3] == ["key_pose", "generate", "convert"], f"chain {kinds}")
    check(key["items"][0]["source_frames"] == [int(round(t_star * fps))] and key["items"][0]["placement"] == "pass1" and len(key["tpose"]["sha256"]) == 64,
          f"key_pose pins Attack1 frame {key['items'][0].get('source_frames')} (strike {t_star}s of {length}s @ {fps:g}) · pass1 · T pose {key['tpose']['path']}")
    check(gen["key_pose"]["passes"] == 2 and gen["timeout_extra_s"] == local_ai.DIFFUSION_EXTRA_S, f"generate: 2 passes · +{gen.get('timeout_extra_s')}s")
    check({"KEY_POSE_RETARGETED", "KEY_POSE_PLACED"} <= {lm["code"] for lm in cand["expected_limitations"]}, "limitations KEY_POSE_RETARGETED · KEY_POSE_PLACED")
    plain = must(SERVICE.plan_motion_generation(request=gen_request("AS_Vesper_Sickle_KeyPlan", SCYTHE_PROMPT, "Sickle")), "plan without key_pose")
    check(plain["candidates"][0]["steps"][0]["step"] == "generate" and "key_pose" not in plain["candidates"][0]["steps"][0]["inputs"],
          "the same request without key_pose has no key_pose step")
    late = must(SERVICE.plan_motion_generation(request=gen_request("AS_Vesper_Sickle_KeyPlan", SCYTHE_PROMPT, "Sickle",
                                                                   [{"type": "key_pose", "asset": ATTACK1, "times": [length + 1.0]}])), "plan late")
    check({e["provider"]: e["reason"] for e in late["excluded"]}.get("local_ai") == "CONSTRAINT_OUT_OF_RANGE", "a key past the source end is refused")
    if uasset(KATANA).is_file():
        other = must(SERVICE.plan_motion_generation(request=gen_request("AS_Vesper_Sickle_KeyPlan", SCYTHE_PROMPT, "Sickle",
                                                                        [{"type": "key_pose", "asset": KATANA, "times": [0.5]}])), "plan other skeleton")
        check({e["provider"]: e["reason"] for e in other["excluded"]}.get("local_ai") == "SAMPLE_SKELETON_MISMATCH", "a source on another skeleton is refused")
    check(dirty_count() == before, f"planning dirtied nothing ({before})")
    STATE["plan"] = {"strike_s": t_star, "attack1_length_s": length, "attack1_fps": fps, "chain": kinds, "key_pose": key, "generate_key_pose": gen["key_pose"]}


def section_src() -> None:
    print(f"== src — round-trip source: sword one prompt · {DURATION}s · seed {SEED} · one pass")
    _, job, seconds = run_job(gen_request("AS_Vesper_Sword_KeySrc", SWORD_PROMPT, "Sword"), "src")
    if job["status"] != "SUCCEEDED":
        return
    gen = job["cursor"]["values"]["generated"]
    STATE["src"] = {"job_id": job["job_id"], "final": job["generated_assets"][0], "npz": gen["samples"][0]["npz"], "frames": gen["samples"][0]["frames"],
                    "seconds": seconds, "kimodo_seconds": gen["seconds"]}
    print(f"   {STATE['src']}")


def section_roundtrip() -> None:
    src = STATE.get("src") or previous().get("src")
    if not src:
        check(False, "roundtrip needs src")
        return
    frames = int(src["frames"])
    times = [round(f / 30.0, 6) for f in range(frames)]
    print(f"== roundtrip — every frame of {src['final'].rsplit('/', 1)[1]} as full-body keys ({frames}) → key_pose file vs the source NPZ")
    req = gen_request("AS_Vesper_Sword_KeyRoundTrip", SWORD_PROMPT, "Sword", [{"type": "key_pose", "asset": src["final"], "times": times}])
    _, job, seconds = run_job(req, "roundtrip")
    if job["status"] != "SUCCEEDED":
        return
    rec = job["key_pose"]
    gen = job["cursor"]["values"]["generated"]
    stats = kimodo(ROUNDTRIP_SCRIPT, {"npz": src["npz"], "key_pose": rec["file"], "source": "generation.constraints[0]", "package_dir": PACKAGE_DIR.as_posix(),
                                      "rt_npz": gen["samples"][0]["npz"]})
    follow, sample = follow_of(job)
    STATE["roundtrip"] = {"job_id": job["job_id"], "final": job["generated_assets"][0], "seconds": seconds, "key_pose_seconds": rec["seconds"],
                          "key_pose_file": rec["file"], "stats": stats, "follow": follow, "placements": (sample.get("key_pose") or {}).get("placements")}
    if not stats:
        return
    print(f"   local {stats['local_deg']}° · position {stats['position_cm']} cm · pose (hips-relative) {stats['pose_cm']} · hips {stats['hips_cm']} · "
          f"heading {stats['heading_deg']}° · dense-key regeneration ↔ source {stats.get('reproduce_cm')} cm")
    for name, row in stats["per_joint"].items():
        print(f"     {name:14s} local {row['local']} · position {row['position']}")
    check(stats["keys"] == frames, f"{frames} keys converted")
    lim = ROUNDTRIP_LIMITS
    check(stats["position_cm"]["p95"] <= lim["position_p95_cm"] and stats["position_cm"]["max"] <= lim["position_max_cm"],
          f"round trip FK joint position p95 {stats['position_cm']['p95']} ≤ {lim['position_p95_cm']} · max {stats['position_cm']['max']} ≤ {lim['position_max_cm']} cm")
    check(stats["local_deg"]["p95"] <= lim["local_p95_deg"], f"round trip local rotation p95 {stats['local_deg']['p95']}° ≤ {lim['local_p95_deg']}°")


def run_key_job(name: str, label: str, constraints: list[dict], **generation) -> dict | None:
    req = gen_request(name, SCYTHE_PROMPT, "Sickle", constraints)
    req["generation"].update(generation)
    _, job, seconds = run_job(req, label)
    if job["status"] != "SUCCEEDED":
        return None
    follow, sample = follow_of(job)
    rec = {"job_id": job["job_id"], "final": job["generated_assets"][0], "seconds": seconds, "kimodo_seconds": job["cursor"]["values"]["generated"]["seconds"],
           "key_pose": job.get("key_pose"), "follow": follow, "placements": (sample.get("key_pose") or {}).get("placements"),
           "npz": sample.get("npz"), "pass1_npz": sample.get("pass1_npz")}
    for row in follow:
        print(f"   {row['type']} × {row['keys']} @ frames {row['frames']}: position {row['position_cm']} cm"
              + (f" · rotation {row['rotation_deg']}°" if row.get("rotation_deg") else "") + f" · jitter p95 {row['jitter_p95']} (pass 1 {row.get('jitter_pass1_p95')})")
    for p in rec["placements"] or []:
        print(f"   placed {p['source']} {p['placement']}: yaw {p['yaw_deg']}° · shift {p['shift_m']} m" + (f" · target {p.get('target')}" if p.get("target") else ""))
    frames = sorted({f for row in follow for f in row["frames"]})
    rec["vesper_jitter"] = vesper_jitter(rec["final"], frames)
    print(f"   Vesper jitter around the keys: {rec['vesper_jitter']}")
    return rec


def strike() -> float:
    s = STATE.get("plan") or previous().get("plan")
    return s["strike_s"] if s else strike_time()[0]


def section_follow() -> None:
    t_star = strike()
    print(f"== follow — Attack1 strike pose ({t_star}s) as one full-body key at {AT}s (pass1)")
    rec = run_key_job("AS_Vesper_Sickle_KeyFull", "follow", [{"type": "key_pose", "asset": ATTACK1, "times": [t_star], "at": [AT]}])
    if not rec:
        return
    rec["vesper"] = pose_distance(pose_at(rec["final"], AT), pose_at(ATTACK1, t_star))
    print(f"   Vesper pose at {AT}s ↔ Attack1 strike: {rec['vesper']}")
    full = next((r for r in rec["follow"] if r["type"] == "fullbody"), None)
    check(full is not None and full["position_cm"]["p50"] <= FOLLOW_P50_CM, f"full-body key follow p50 {(full or {}).get('position_cm')} ≤ {FOLLOW_P50_CM} cm")
    STATE["follow"] = rec


def section_multi() -> None:
    t_star = strike()
    times = [round(max(0.0, t_star - MULTI_DT), 4), t_star, round(t_star + MULTI_DT, 4)]
    print(f"== multi — three full-body keys {times}s → {[AT - MULTI_DT, AT, AT + MULTI_DT]}s")
    rec = run_key_job("AS_Vesper_Sickle_KeyMulti", "multi", [{"type": "key_pose", "asset": ATTACK1, "times": times,
                                                                "at": [round(AT - MULTI_DT, 4), AT, round(AT + MULTI_DT, 4)]}])
    if rec:
        STATE["multi"] = rec


def section_multi_nopp() -> None:
    """원인 가르기 — multi 와 같은 키 · seed 를 Kimodo 후처리 없이(후처리는 FullBody 키 프레임을 제약 자세로 강제로 맞춘다)."""
    t_star = strike()
    times = [round(max(0.0, t_star - MULTI_DT), 4), t_star, round(t_star + MULTI_DT, 4)]
    print("== multi_nopp — multi without Kimodo post-processing")
    rec = run_key_job("AS_Vesper_Sickle_KeyMultiNoPP", "multi_nopp", [{"type": "key_pose", "asset": ATTACK1, "times": times,
                                                                        "at": [round(AT - MULTI_DT, 4), AT, round(AT + MULTI_DT, 4)]}],
                      postprocess="off")
    if rec:
        STATE["multi_nopp"] = rec


def section_ee() -> None:
    t_star = strike()
    print(f"== ee — right hand · left foot · right foot end-effector keys at {AT}s from the Attack1 strike")
    rec = run_key_job("AS_Vesper_Sickle_KeyHandFeet", "ee", [{"type": "key_pose", "asset": ATTACK1, "times": [t_star], "at": [AT], "part": part}
                                                             for part in ("right_hand", "left_foot", "right_foot")])
    if not rec:
        return
    rec["vesper"] = pose_distance(pose_at(rec["final"], AT), pose_at(ATTACK1, t_star))
    print(f"   Vesper pose at {AT}s ↔ Attack1 strike: {rec['vesper']}")
    STATE["ee"] = rec


def section_nokey() -> None:
    t_star = strike()
    print("== nokey — same prompt · seed, no keys (= pass 1 of follow)")
    _, job, seconds = run_job(gen_request("AS_Vesper_Sickle_KeyNone", SCYTHE_PROMPT, "Sickle"), "nokey")
    if job["status"] != "SUCCEEDED":
        return
    rec = {"job_id": job["job_id"], "final": job["generated_assets"][0], "seconds": seconds}
    rec["vesper"] = pose_distance(pose_at(rec["final"], AT), pose_at(ATTACK1, t_star))
    rec["vesper_jitter"] = vesper_jitter(rec["final"], [round((AT - MULTI_DT) * 30), round(AT * 30), round((AT + MULTI_DT) * 30)])
    print(f"   Vesper jitter (control, same windows as multi): {rec['vesper_jitter']}")
    print(f"   Vesper pose at {AT}s ↔ Attack1 strike (control): {rec['vesper']}")
    follow = STATE.get("follow") or previous().get("follow")
    if follow and follow.get("vesper"):
        check(follow["vesper"]["p50"] < rec["vesper"]["p50"], f"the key brings the Vesper pose closer to the strike: p50 {rec['vesper']['p50']} → "
              f"{follow['vesper']['p50']} cm")
    STATE["nokey"] = rec


def section_jitter() -> None:
    """키 둘레 떨림 가르기(생성 없음 — Kimodo venv 로 NPZ): follow · multi · ee 최종에 σ 1 · 2 스무딩(전체 · 키 둘레 ± 6 · 12 프레임 창)."""
    prev = previous()
    runs = []
    for key in ("follow", "multi", "multi_nopp", "ee"):
        rec = STATE.get(key) or prev.get(key)
        if rec and rec.get("npz") and rec.get("follow"):
            frames = sorted({f for row in rec["follow"] for f in row["frames"]})
            runs.append({"name": key, "npz": rec["npz"], "pass1_npz": rec.get("pass1_npz"), "frames": frames})
    if not runs:
        check(False, "jitter needs follow / multi / ee runs")
        return
    print(f"== jitter — smoothing variants on {[r['name'] for r in runs]} (no generation)")
    out = kimodo(JITTER_SCRIPT, {"runs": runs, "package_dir": PACKAGE_DIR.as_posix()})
    if not out:
        return
    for name, rec in out.items():
        print(f"   {name}:")
        for variant, m in rec.items():
            print(f"     {variant:14s} jitter p95 {m['jitter_p95']} · key error {m['key_err_cm']} cm · hand peak {m['hand_peak_cm_s']} cm/s")
    STATE["jitter"] = out


def capture(out: pathlib.Path, asset: str, label: str, **params) -> dict:
    env = editor("capture_animation", asset=asset, mesh=VESPER_MESH_01, facing="+Y", output_dir=out.as_posix(), label=label, **params)
    res = must(env, f"capture {asset}")
    seq = res.get("sequence") or {}
    if seq.get("frames"):
        res["animation"] = apng.assemble(seq["frames"], out / "animation.png", float(seq["fps"]))
    return res


def section_capture() -> None:
    print("== captures — follow | nokey (same times) · Attack1 strike")
    before = dirty_count()
    prev = previous()
    follow, nokey = STATE.get("follow") or prev.get("follow"), STATE.get("nokey") or prev.get("nokey")
    if not (follow and nokey):
        check(False, "follow and nokey runs needed for the capture")
        return
    times = [0.0, 0.6, 0.9, AT, 1.5, 2.0, 2.5, DURATION]
    nc = capture(OUT / "nokey", nokey["final"], "no key (pass 1)", times=times, sequence={"fps": 15})
    by_row: dict[int, list[str]] = {}
    for f in sorted(nc["frames"], key=lambda f: (f["row"], f["view"] != "front")):
        by_row.setdefault(f["row"], []).append(f["path"])
    fc = capture(OUT / "follow", follow["final"], f"Attack1 strike key at {AT}s", times=times, sequence={"fps": 15},
                 compare={"label": "no key", "rows": [by_row[r] for r in sorted(by_row)]})
    ac = capture(OUT / "attack1", ATTACK1, "Attack1 (operating) strike", times=[strike()])
    caps = {"compare": (fc.get("compare") or {}).get("path"), "follow_apng": (fc.get("animation") or {}).get("path"),
            "nokey_apng": (nc.get("animation") or {}).get("path"), "attack1_sheet": ac.get("sheet"), "times": times}
    multi, ee = STATE.get("multi") or prev.get("multi"), STATE.get("ee") or prev.get("ee")
    for key, rec in (("multi", multi), ("ee", ee)):
        if rec:
            c = capture(OUT / key, rec["final"], key, times=times, sequence={"fps": 15})
            caps[f"{key}_sheet"], caps[f"{key}_apng"] = c.get("sheet"), (c.get("animation") or {}).get("path")
    check(bool(caps["compare"]) and fc["cells_touching_edge"] == 0, f"follow | nokey compare sheet {caps['compare']}")
    print(f"   {json.dumps(caps, ensure_ascii=False)}")
    check(dirty_count() == before, f"captures dirtied nothing ({before})")
    STATE["capture"] = caps


def section_dirty() -> None:
    print("== hashes · content · dirty (after)")
    if "hashes" in STATE:
        changed = [p for p, h in STATE["hashes"].items() if sha256(p) != h]
        check(not changed, f"target skeleton · mesh · Attack1 .uasset SHA-256 unchanged ({len(STATE['hashes'])} files) {changed}")
    if "dirty_before" in STATE:
        check(dirty_count() == STATE["dirty_before"], f"unsaved packages unchanged ({STATE['dirty_before']}) — every write was saved")
    if "content_before" in STATE:
        new = [p for p in content_changes() if p not in STATE["content_before"]]
        run_dir = "Content/" + RUN.removeprefix("/Game/") + "/"
        outside = [p for p in new if not p.startswith(run_dir)]
        print(f"   new Content changes {len(new)} (outside this run's folder: {outside})")
        check(not outside, "Content/ changes are only this run's folder")
        STATE["content_new"] = len(new)


SECTIONS = {"hashes": section_hashes, "plan": section_plan, "src": section_src, "roundtrip": section_roundtrip, "follow": section_follow,
            "multi": section_multi, "multi_nopp": section_multi_nopp, "ee": section_ee, "nokey": section_nokey, "jitter": section_jitter, "capture": section_capture, "dirty": section_dirty}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(SECTIONS), help="comma separated: " + ",".join(SECTIONS))
    ap.add_argument("--seed", type=int, default=SEED, help=f"seed (default {SEED})")
    args = ap.parse_args()
    globals().update(SEED=args.seed)
    STATE.update(seed=args.seed)
    t0 = time.time()
    names = [n.strip() for n in args.only.split(",")]
    for name in names:
        SECTIONS[name]()
    STATE["seconds"] = round(time.time() - t0, 1)
    out = ROOT / "Tools" / "mcp" / "anim_gen_phase9_3_state.json"
    try:
        merged = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        merged = {}
    merged.setdefault("runs", {})[STAMP] = {"sections": names, "failures": len(FAILS), "seconds": STATE["seconds"], "run": RUN, "seed": args.seed}
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
