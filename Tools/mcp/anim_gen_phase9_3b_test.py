"""AI 애니 생성 Phase 9-3b — 손 키 손목 · 낫 생성 파지 규칙 · 키 포즈 활용(U3-c) 실제 Kimodo · Blender · 에디터 통합 테스트
(Docs/AIAnimation/DevelopmentGuide.md §14 Phase 9 '9-3' · FollowUpRoadmap.md §5 U3).

    D:/UE5Projects/AstralBreak/Tools/mcp/.venv/Scripts/python.exe -X utf8 -B -u D:/UE5Projects/AstralBreak/Tools/mcp/anim_gen_phase9_3b_test.py [--only ...]

뜬 에디터(AnimGraphMcp 플러그인) · 정책의 Kimodo venv · Blender 를 쓴다. anim_gen 은 같은 프로세스의 Service 로 부르고, 상태는
Saved/AnimGen/TestRuns/P93bRun<시각>/ 에, 새 애셋은 /Game/Animation/Test/AIAnimation/P93bRun<시각>/ 에만, 캡처는 Tools/mcp/results/capture/P93bRun<시각>/.
Kimodo 1건 ≈ RAM 15 GB — 생성 섹션은 순서대로 한 건씩.
섹션:
  hashes   — (맨 앞) 대상 스켈레톤 · 메시 · 원천 운영 애니 .uasset SHA-256 · Content/ git 상태 · 미저장 패키지 수
  ee       — 운영 낫 Attack1 정점의 오른손 · 왼발 · 오른발 end-effector 키(생성 1.2초 · pass1, 같은 seed — Kimodo 는 결정적). 9-3b 부터 이 계획이
             자유 손 고정을 기본으로 넣어 9-3a 값(14.35°)이 아니라 9-3b 채택값(오른손 회전 5.86°)을 재현한다
  e0wrist  — ⓪ E0(제품 코드 무변경): ee 의 Kimodo 실행을 같은 인자로 다시 돌려(스무딩 함수만 감싸 스무딩 전 출력을 남긴다) 1차 · 스무딩 전 · 후의
             프레임별 오른 손목 굽힘(아래팔 ↔ 손 — motion_metrics.bends 정의) · 비틀기 · 손 각속도 · 키 손 회전과의 차, 키 프레임 아래팔 차
  vwrist   — ⓪ E0: ee 최종 Vesper 의 프레임별 오른 손목 굽힘(lowerarm_r → hand_r → middle_01_r) · 운영 Attack1 정점의 굽힘(기준)
  dirty    — (맨 뒤) 해시 불변 · 미저장 수 그대로 · Content/ 변경은 이번 실행 폴더뿐
⓪ E0 섹션(ee · e0wrist · e0twist · vwrist · e0capture · eehold — 9-3b 착수 전 진단)은 기본 --only 에서 빠진다(명시할 때만, phase8_4 baseline 과 같은 방식).
생성 섹션의 seed 는 --seed(기본 20261025). 요약은 Tools/mcp/anim_gen_phase9_3b_state.json(섹션 단위로 덮어쓴다).
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
STATE_DIR = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P93bRun{STAMP}"
os.environ["ANIM_GEN_STATE_DIR"] = str(STATE_DIR)

from anim_gen import motion_metrics, timing  # noqa: E402
from anim_gen.providers import local_ai  # noqa: E402
from anim_gen.providers.subprocess_step import child_env  # noqa: E402
from anim_gen.service import Service  # noqa: E402
from anim_gen.store import Store  # noqa: E402

VESPER = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
VESPER_MESH_01 = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
ATTACK1 = "/Game/Animation/Hero/Vesper/Sickle/Actions/AS_Vesper_Sickle_Attack1"
RUN = f"/Game/Animation/Test/AIAnimation/P93bRun{STAMP}"
OUT = ROOT / "Tools" / "mcp" / "results" / "capture" / f"P93bRun{STAMP}"
HASHED = [VESPER, VESPER_MESH_01, ATTACK1]
SEED = 20261025
DURATION = 3.0
AT = 1.2               # 키를 둘 생성 시각(9-3a 와 같다)
SCYTHE_PROMPT = ("A person holds a long-handled scythe with both hands, raises it over the right shoulder, slashes diagonally down to the left, "
                 "then returns to a fighting stance.")  # 8-1 낫 기준 프롬프트
BODY = ["hand_l", "hand_r", "thigh_l", "thigh_r", "foot_l", "foot_r", "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "head"]
WRIST_R = ["lowerarm_r", "hand_r", "middle_01_r"]   # Vesper 오른 손목 굽힘(아래팔 → 손 → 가운데 손가락 뿌리)
# ⓪ E0 섹션 — 기본 --only 에서 뺀다(진단은 끝남). 기대값은 지금 기본(키 2차 자유 손 고정)에 맞춘다 — 지침서 §14 '9-3b' ⓪ 표
E0_SECTIONS = ("ee", "e0wrist", "e0twist", "vwrist", "e0capture", "eehold")
EE_HAND_ROT_DEG = 5.86      # ee 오른손 키 회전 p50 — 채택(키 ± 15 프레임 묶음) 행
TWIST_DIP_9_3A_DEG = -91.0  # 묶음 없는 9-3a ee 의 왼손목 비틀기 이탈(f15 ~ 35, 1차 f10 기준) — ee 도 이제 묶이므로 고정 효과는 이 기록과 비교
FAILS: list[str] = []
STATE: dict = {"run": RUN, "state_dir": STATE_DIR.as_posix(), "out": OUT.as_posix()}
SERVICE = Service(store=Store(STATE_DIR))
PACKAGE_DIR = ROOT / "Tools" / "mcp"
# ⓪ E0 — ee 의 Kimodo 실행을 같은 인자(args.json)로 다시: 스무딩 함수만 감싸 스무딩 전 출력을 NPZ 로 남기고(나머지는 러너 그대로 — 결정적), 1차 ·
# 스무딩 전 · 후의 프레임별 오른 손목을 잰다. 키 손 회전 = 러너와 같은 배치(place_on_pass1)로 다시 푼 키 자세의 FK
E0_SCRIPT = r"""
import json, math, pathlib, sys
import numpy as np
args = json.loads(sys.argv[1])
sys.path.insert(0, args["package_dir"])
from anim_gen.local_ai import kimodo_run as kr
out = pathlib.Path(args["out_dir"])
out.mkdir(parents=True, exist_ok=True)
run_args = json.loads(pathlib.Path(args["args"]).read_text(encoding="utf-8"))
run_args.update(out_dir=out.as_posix(), report=(out / "report.json").as_posix())
(out / "args.json").write_text(json.dumps(run_args, ensure_ascii=False, indent=1), encoding="utf-8")
orig = kr.smooth_output
def keep_unsmoothed(single, skeleton, sigma, device):
    np.savez(out / "unsmoothed.npz", **{k: v for k, v in single.items() if hasattr(v, "shape")})
    return orig(single, skeleton, sigma, device)
kr.smooth_output = keep_unsmoothed
sys.argv = ["kimodo_run.py", str(out / "args.json")]
try:
    kr.main()
except SystemExit:
    pass
report = json.loads((out / "report.json").read_text(encoding="utf-8"))
if not report.get("ok"):
    print(json.dumps({"error": report.get("error")}))
    sys.exit(0)
import torch
from anim_gen import key_pose as kp
from kimodo.geometry import axis_angle_to_matrix
from kimodo.skeleton.registry import build_skeleton
sk = build_skeleton(77)
names = list(sk.bone_order_names)
FA, HA, MI = names.index("RightForeArm"), names.index("RightHand"), names.index("RightHandMiddle2")
sample = report["samples"][0]
smooth = dict(np.load(sample["npz"]))
pass1 = dict(np.load(sample["pass1_npz"]))
unsm = dict(np.load(out / "unsmoothed.npz"))
key_file = json.loads(pathlib.Path(run_args["key_pose_file"]).read_text(encoding="utf-8"))
spec = next(s for s in run_args["constraints"] if s["kind"] == "key_pose" and s["part"] == "right_hand")
item = next(i for i in key_file["items"] if i["source"] == spec["source"])
item = {**item, "keys": kr.with_smooth_root(item)}
placed, recs = kr.place_on_pass1([(spec, item)], pass1, sk)
local = axis_angle_to_matrix(torch.tensor(placed[0]["local_joints_rot"], dtype=torch.float32))
kg, kpos, _ = sk.fk(local, torch.tensor(placed[0]["root_positions"], dtype=torch.float32))
kg, kpos = kg.numpy()[0], kpos.numpy()[0]
kf = spec["frame_indices"][0]
def ang(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.degrees(np.arccos(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0)))) if na > 1e-9 and nb > 1e-9 else None
def rot_ang(a, b):
    return float(np.degrees(np.arccos(np.clip((np.trace(a.T @ b) - 1.0) / 2.0, -1.0, 1.0))))
# 비틀기 축 = T 포즈(전역 회전 0)의 아래팔 → 손 방향 — 손목 로컬 회전(아래팔 기준)을 그 축 둘레 비틀기 · 나머지 굽힘으로 나눈다
_, tpos, _ = sk.fk(torch.eye(3).repeat(1, len(names), 1, 1), torch.zeros(1, 3))
axis = tpos.numpy()[0, HA] - tpos.numpy()[0, FA]
axis = axis / np.linalg.norm(axis)
def twist_swing(m):
    import math as _m
    w = _m.sqrt(max(0.0, 1.0 + m[0, 0] + m[1, 1] + m[2, 2])) / 2.0
    if w < 1e-6:
        return None, None
    v = np.array([m[2, 1] - m[1, 2], m[0, 2] - m[2, 0], m[1, 0] - m[0, 1]]) / (4.0 * w)
    p = float(np.dot(v, axis))
    twist = 2.0 * _m.degrees(_m.atan2(p, w))
    total = 2.0 * _m.degrees(_m.acos(min(1.0, w)))
    swing = 2.0 * _m.degrees(_m.acos(min(1.0, _m.sqrt(w * w + p * p))))
    return round(twist, 2), round(swing, 2)
def series(d):
    P, G = d["posed_joints"], d["global_rot_mats"]
    n = P.shape[0]
    rows = []
    for f in range(n):
        tw, sw = twist_swing(G[f, FA].T @ G[f, HA])
        rows.append({"f": f, "bend": ang(P[f, HA] - P[f, FA], P[f, MI] - P[f, HA]), "twist": tw, "swing": sw,
                     "hand_speed": rot_ang(G[f, HA], G[f + 1, HA]) if f + 1 < n else None,
                     "fore_speed": rot_ang(G[f, FA], G[f + 1, FA]) if f + 1 < n else None,
                     "to_key_rot": rot_ang(G[f, HA], kg[HA])})
    return rows
res = {"key_frame": kf, "placement": recs[0], "variants": {}}
for name, d in (("pass1", pass1), ("unsmoothed", unsm), ("smoothed", smooth)):
    rows = series(d)
    bends = [r["bend"] for r in rows if r["bend"] is not None]
    peak = max(rows, key=lambda r: r["bend"] or 0.0)
    gen_fore = d["posed_joints"][kf, HA] - d["posed_joints"][kf, FA]
    res["variants"][name] = {"rows": rows, "bend_peak": {"f": peak["f"], "bend": round(peak["bend"], 2)},
                             "bend_p50": round(float(np.median(bends)), 2),
                             "key_frame": {"bend": round(rows[kf]["bend"], 2), "hand_rot_to_key": round(rows[kf]["to_key_rot"], 2),
                                           "forearm_dir_to_key_deg": round(ang(gen_fore, kpos[HA] - kpos[FA]), 2),
                                           "bend_if_key_hand_on_this_forearm": round(ang(gen_fore, kg[HA] @ (tpos.numpy()[0, MI] - tpos.numpy()[0, HA])), 2)}}
res["key_pose"] = {"bend": round(ang(kpos[HA] - kpos[FA], kpos[MI] - kpos[HA]), 2), "twist_swing": twist_swing(kg[FA].T @ kg[HA])}
# 결정성 — 다시 돌린 최종이 ee 기록 NPZ 와 같은가(관절 위치 최대 차 cm)
res["rerun_vs_record_cm"] = round(float(np.abs(smooth["posed_joints"] - np.load(args["record_npz"])["posed_joints"]).max()) * 100.0, 4)
print(json.dumps(res))
"""


# ⓪ E0 후속 — 양 손목(굽힘 · 아래팔 축 비틀기)을 1차 · 스무딩 전 · 후 NPZ 에서(생성 없음). 비틀기는 앞 프레임에 이어 펼친다(±180° 경계를 넘어도 연속)
TWIST_SCRIPT = r"""
import json, math, sys
import numpy as np
import torch
args = json.loads(sys.argv[1])
from kimodo.skeleton.registry import build_skeleton
sk = build_skeleton(77)
names = list(sk.bone_order_names)
_, tpos, _ = sk.fk(torch.eye(3).repeat(1, len(names), 1, 1), torch.zeros(1, 3))
tpos = tpos.numpy()[0]
def ang(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.degrees(np.arccos(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))))
def twist(m, axis):
    w = math.sqrt(max(0.0, 1.0 + m[0, 0] + m[1, 1] + m[2, 2])) / 2.0
    v = np.array([m[2, 1] - m[1, 2], m[0, 2] - m[2, 0], m[1, 0] - m[0, 1]]) / max(4.0 * w, 1e-9)
    return math.degrees(2.0 * math.atan2(float(np.dot(v, axis)), w))
out = {}
for name, path in args["npz"].items():
    d = np.load(path)
    P, G = d["posed_joints"], d["global_rot_mats"]
    rec = {}
    for side in ("Left", "Right"):
        fa, ha, mi = names.index(side + "ForeArm"), names.index(side + "Hand"), names.index(side + "HandMiddle2")
        axis = tpos[ha] - tpos[fa]
        axis = axis / np.linalg.norm(axis)
        bends, tw = [], []
        for f in range(P.shape[0]):
            bends.append(round(ang(P[f, ha] - P[f, fa], P[f, mi] - P[f, ha]), 2))
            t = twist(G[f, fa].T @ G[f, ha], axis)
            if tw:
                while t - tw[-1] > 180.0:
                    t -= 360.0
                while t - tw[-1] < -180.0:
                    t += 360.0
            tw.append(round(t, 2))
        speed = [round(abs(tw[f + 1] - tw[f]), 2) for f in range(len(tw) - 1)]
        rec[side] = {"bend": bends, "twist": tw, "twist_range": [min(tw), max(tw)], "twist_speed_max": max(speed),
                     "twist_speed_argmax": int(np.argmax(speed)), "bend_max": max(bends), "bend_argmax": int(np.argmax(bends))}
    out[name] = rec
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
           "description": f"9-3b 시험 {name}", "motion_category": "weapon_action", "loop": False, "frame_rate": 30, "duration_seconds": DURATION,
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


def kimodo(script: str, args: dict, timeout: float = 600.0, model: bool = False) -> dict | None:
    """Kimodo venv 스크립트 — model 이면 러너와 같은 오프라인 환경(모델 적재)."""
    python, cache = local_ai.KimodoProvider.paths(SERVICE.policy())
    env = child_env({**local_ai._OFFLINE_ENV, "HF_HUB_CACHE": str(cache)}) if model else None
    out = subprocess.run([str(python), "-I", "-c", script, json.dumps(args)], capture_output=True, text=True, encoding="utf-8", timeout=timeout, env=env)
    if out.returncode != 0:
        print(f"[FAIL] Kimodo venv script: {out.stderr[-2000:]}")
        FAILS.append("Kimodo venv script")
        return None
    return json.loads(out.stdout.strip().splitlines()[-1])


def previous() -> dict:
    saved = ROOT / "Tools" / "mcp" / "anim_gen_phase9_3b_state.json"
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


def strike() -> float:
    s = STATE.get("strike_s") or previous().get("strike_s")
    if s is None:
        s = strike_time()[0]
        STATE["strike_s"] = s
    return s


def follow_of(job: dict) -> tuple[list[dict], dict]:
    gen = job["cursor"]["values"]["generated"]
    sample = (gen.get("candidates") or gen["samples"])[0]
    return (sample.get("key_pose") or {}).get("follow") or [], sample


def _twist(q_lower, q_hand, axis_c) -> float:
    """손목 비틀기(°) — 아래팔 기준 손 상대 회전의 '아래팔 → 손' 축 둘레 성분(컴포넌트 축을 아래팔 공간으로)."""
    from anim_gen import body_model as bm
    rel = bm.qmul(bm.qconj(q_lower), q_hand)
    a = bm.qrot(bm.qconj(q_lower), axis_c)
    n = math.sqrt(sum(x * x for x in a)) or 1.0
    p = sum(rel[i] * a[i] / n for i in range(3))
    return math.degrees(2.0 * math.atan2(p, rel[3])) if rel[3] >= 0 else math.degrees(2.0 * math.atan2(-p, -rel[3]))


def vesper_bends(asset: str) -> list[dict]:
    """Vesper 프레임별 양 손목 굽힘(°) · 비틀기(°) — profile 표본 i = 프레임 i + 1(프레임 0 은 내지 않는다)."""
    bones = [f"{b}_{s}" for s in "lr" for b in ("lowerarm", "hand", "middle_01")]
    item = must(editor("validate_animation", assets=[asset], skeleton=VESPER, profile_bones=bones, profile_positions=True, profile_rotations=True),
                f"profile {asset.rsplit('/', 1)[1]}")["assets"][0]
    p = item["numeric"]["profile"]
    pos, rot = p["position_cm"], p.get("rotations") or {}
    out = [{"t": round(t, 4)} for t in p["times"]]
    for s in "lr":
        b = motion_metrics.bends(pos[f"lowerarm_{s}"], pos[f"hand_{s}"], pos[f"middle_01_{s}"])
        for i, v in enumerate(b):
            out[i][f"bend_{s}"] = None if v is None else round(v, 2)
            if rot.get(f"hand_{s}") and rot.get(f"lowerarm_{s}"):
                axis = [pos[f"hand_{s}"][i][k] - pos[f"lowerarm_{s}"][i][k] for k in range(3)]
                out[i][f"twist_{s}"] = round(_twist(rot[f"lowerarm_{s}"][i], rot[f"hand_{s}"][i], axis), 2)
    return out


# ---- 섹션 ----
def section_hashes() -> None:
    print("== hashes · content · dirty (before)")
    STATE["hashes"] = {p: sha256(p) for p in HASHED}
    STATE["content_before"] = content_changes()
    STATE["dirty_before"] = dirty_count()
    print(f"   {len(HASHED)} assets hashed · Content changes before: {len(STATE['content_before'])} · dirty {STATE['dirty_before']}")


def section_ee() -> None:
    t_star = strike()
    print(f"== ee — right hand · left foot · right foot end-effector keys at {AT}s from the Attack1 strike ({t_star}s) — free hand held (9-3b default)")
    req = gen_request("AS_Vesper_Sickle_KeyHandFeet", SCYTHE_PROMPT, "Sickle",
                      [{"type": "key_pose", "asset": ATTACK1, "times": [t_star], "at": [AT], "part": part} for part in ("right_hand", "left_foot", "right_foot")])
    _, job, seconds = run_job(req, "ee")
    if job["status"] != "SUCCEEDED":
        return
    follow, sample = follow_of(job)
    for row in follow:
        print(f"   {row['part']} × {row['keys']} @ {row['frames']}: position {row['position_cm']} cm · rotation {row.get('rotation_deg')}° · jitter {row['jitter_p95']}")
    STATE["ee"] = {"job_id": job["job_id"], "final": job["generated_assets"][0], "seconds": seconds, "follow": follow,
                   "placements": (sample.get("key_pose") or {}).get("placements"), "smooth": (sample.get("key_pose") or {}).get("smooth"),
                   "npz": sample.get("npz"), "pass1_npz": sample.get("pass1_npz"), "args": (pathlib.Path(sample["npz"]).parent / "args.json").as_posix()}
    hand = next((r for r in follow if r["part"] == "right_hand"), None)
    check(hand is not None and abs(hand["rotation_deg"]["p50"] - EE_HAND_ROT_DEG) < 0.5,
          f"ee reproduces the 9-3b record (right-hand rotation {(hand or {}).get('rotation_deg')}° vs {EE_HAND_ROT_DEG}° — free hand held)")


def section_e0wrist() -> None:
    ee = STATE.get("ee") or previous().get("ee")
    if not ee:
        check(False, "e0wrist needs the ee run")
        return
    print(f"== e0wrist — rerun {ee['job_id']}'s Kimodo call (same args — keeps the unsmoothed output) · per-frame right wrist")
    res = kimodo(E0_SCRIPT, {"args": ee["args"], "out_dir": (STATE_DIR / "e0wrist").as_posix(), "package_dir": PACKAGE_DIR.as_posix(),
                             "record_npz": ee["npz"]}, timeout=900.0, model=True)
    if not res or res.get("error"):
        check(False, f"e0wrist rerun {res}")
        return
    check(res["rerun_vs_record_cm"] <= 0.05, f"the rerun reproduces the ee record (max joint diff {res['rerun_vs_record_cm']} cm)")
    kf = res["key_frame"]
    print(f"   key frame {kf} · placement {res['placement']} · key pose bend {res['key_pose']['bend']}° · twist/swing {res['key_pose']['twist_swing']}")
    for name, v in res["variants"].items():
        print(f"   {name:10s} bend peak f{v['bend_peak']['f']} {v['bend_peak']['bend']}° · p50 {v['bend_p50']}° · at key {v['key_frame']}")
    print("   f   | bend p1 · unsm · sm | twist/swing unsm | hand speed unsm · sm (°/f) | fore speed unsm | to-key rot unsm · sm")
    rows = {n: v["rows"] for n, v in res["variants"].items()}
    for f in range(max(0, kf - 22), min(len(rows["smoothed"]), kf + 12)):
        p1, us, sm = rows["pass1"][f], rows["unsmoothed"][f], rows["smoothed"][f]
        print(f"   {f:3d} | {p1['bend']:6.1f} · {us['bend']:6.1f} · {sm['bend']:6.1f} | {us['twist']} / {us['swing']} | "
              f"{us['hand_speed'] or 0:5.1f} · {sm['hand_speed'] or 0:5.1f} | {us['fore_speed'] or 0:5.1f} | {us['to_key_rot']:6.1f} · {sm['to_key_rot']:6.1f}")
    STATE["e0wrist"] = res


def e0_unsmoothed() -> str | None:
    """앞 실행 중 e0wrist 를 돈 실행의 스무딩 전 NPZ(Saved/AnimGen/TestRuns/P93bRun<시각>/e0wrist/unsmoothed.npz)."""
    runs = (STATE.get("runs") or previous().get("runs") or {})
    for stamp in sorted(runs, reverse=True):
        if "e0wrist" in runs[stamp]["sections"] and runs[stamp]["failures"] == 0:
            path = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P93bRun{stamp}" / "e0wrist" / "unsmoothed.npz"
            return path.as_posix()
    return (STATE_DIR / "e0wrist" / "unsmoothed.npz").as_posix() if "e0wrist" in STATE else None


def section_e0twist() -> None:
    ee = STATE.get("ee") or previous().get("ee")
    unsm = e0_unsmoothed()
    if not ee or not unsm:
        check(False, "e0twist needs the ee and e0wrist runs")
        return
    print("== e0twist — both wrists (bend · forearm-axis twist, unwrapped) on the SOMA output: pass 1 · unsmoothed · smoothed")
    res = kimodo(TWIST_SCRIPT, {"npz": {"pass1": ee["pass1_npz"], "unsmoothed": unsm, "smoothed": ee["npz"]}})
    if not res:
        return
    for name, rec in res.items():
        for side, r in rec.items():
            print(f"   {name:10s} {side:5s} bend max {r['bend_max']}° @ f{r['bend_argmax']} · twist range {r['twist_range']} · twist speed max "
                  f"{r['twist_speed_max']}°/f @ f{r['twist_speed_argmax']}")
    print("   f   | Left twist p1 · unsm · sm | Left bend p1 · sm | Right twist p1 · sm")
    for f in range(10, 50):
        L, R = {n: res[n]["Left"] for n in res}, {n: res[n]["Right"] for n in res}
        print(f"   {f:3d} | {L['pass1']['twist'][f]:7.1f} · {L['unsmoothed']['twist'][f]:7.1f} · {L['smoothed']['twist'][f]:7.1f} | "
              f"{L['pass1']['bend'][f]:5.1f} · {L['smoothed']['bend'][f]:5.1f} | {R['pass1']['twist'][f]:7.1f} · {R['smoothed']['twist'][f]:7.1f}")
    STATE["e0twist"] = res


def operating_twist() -> dict:
    """운영 낫 4 클립의 Vesper 양 손목 굽힘 최대 · 비틀기 범위(기준)."""
    out = {}
    for name in ("Attack1", "Attack2", "Attack3", "Finisher1"):
        rows = vesper_bends(f"/Game/Animation/Hero/Vesper/Sickle/Actions/AS_Vesper_Sickle_{name}")
        rec = {}
        for s in "lr":
            tw = [r.get(f"twist_{s}") for r in rows if r.get(f"twist_{s}") is not None]
            un = []
            for t in tw:
                if un:
                    while t - un[-1] > 180.0:
                        t -= 360.0
                    while t - un[-1] < -180.0:
                        t += 360.0
                un.append(t)
            rec[s] = {"bend_max": max(r.get(f"bend_{s}") or 0.0 for r in rows), "twist_range": [round(min(un), 1), round(max(un), 1)] if un else None,
                      "twist_speed_max": round(max((abs(b - a) for a, b in zip(un, un[1:])), default=0.0), 2)}
        out[name] = rec
    return out


def section_vwrist() -> None:
    ee = STATE.get("ee") or previous().get("ee")
    if not ee:
        check(False, "vwrist needs the ee run")
        return
    t_star = strike()
    print(f"== vwrist — Vesper right wrist bend per frame: {ee['final'].rsplit('/', 1)[1]} · Attack1 strike ({t_star}s)")
    rows = vesper_bends(ee["final"])
    att = vesper_bends(ATTACK1)
    a_star = min(att, key=lambda r: abs(r["t"] - t_star))
    peaks = {s: max(rows, key=lambda r: r.get(f"bend_{s}") or 0.0) for s in "lr"}
    a_max = {s: max(r.get(f"bend_{s}") or 0.0 for r in att) for s in "lr"}
    print(f"   ee peaks {peaks} · Attack1 strike {a_star} · Attack1 max {a_max}")
    print("     t      | bend l · r | twist l · r")
    for r in rows:
        if 0.4 <= r["t"] <= 1.6:
            print(f"     {r['t']:.3f}s | {r.get('bend_l')} · {r.get('bend_r')} | {r.get('twist_l')} · {r.get('twist_r')}")
    ops = operating_twist()
    for name, rec in ops.items():
        print(f"   operating {name}: {rec}")
    STATE["vwrist"] = {"ee": rows, "ee_peaks": peaks, "attack1_strike": a_star, "attack1_max": a_max, "operating": ops}


def section_eehold() -> None:
    """⓪ 수정 확인 — ee 와 같은 요청(같은 seed)을 9-3b 자유 손 고정(키 2차가 왼손을 1차에 묶는다)으로 다시: 왼손목 비틀기(SOMA · Vesper) · 오른손 키 추종 ·
    0.6 ~ 1.6초 비교 캡처(고정 | ee). 9-3b 부터 ee 도 같은 계획이라 묶음 없는 값은 9-3a 기록과 비교한다."""
    ee = STATE.get("ee") or previous().get("ee")
    t_star = strike()
    print(f"== eehold — ee with the free (left) hand held to pass 1 in the keyed pass")
    req = gen_request("AS_Vesper_Sickle_KeyHandFeetHold", SCYTHE_PROMPT, "Sickle",
                      [{"type": "key_pose", "asset": ATTACK1, "times": [t_star], "at": [AT], "part": part} for part in ("right_hand", "left_foot", "right_foot")])
    plan, job, seconds = run_job(req, "eehold")
    if job["status"] != "SUCCEEDED":
        return
    gen_in = next(s for s in plan["candidates"][0]["steps"] if s["step"] == "generate")["inputs"]
    hold_plan = gen_in["key_pose"].get("hold_free_hands")
    check(bool(hold_plan) and hold_plan["hands"] == ["left_hand"], f"plan holds the free hand {hold_plan}")
    follow, sample = follow_of(job)
    hold = (sample.get("key_pose") or {}).get("hold")
    for row in follow:
        print(f"   {row['part']} × {row['keys']}: position {row['position_cm']} cm · rotation {row.get('rotation_deg')}° · jitter {row['jitter_p95']}")
    print(f"   hold {hold}")
    rec = {"job_id": job["job_id"], "final": job["generated_assets"][0], "seconds": seconds, "follow": follow, "hold": hold,
           "npz": sample.get("npz"), "pass1_npz": sample.get("pass1_npz")}
    tw = kimodo(TWIST_SCRIPT, {"npz": {"pass1": rec["pass1_npz"], "hold": rec["npz"], "before": ee["npz"]}}) if ee else None
    if tw:
        for name in tw:
            L = tw[name]["Left"]
            print(f"   {name:7s} Left twist range {L['twist_range']} · speed max {L['twist_speed_max']}°/f @ f{L['twist_speed_argmax']} · bend max {L['bend_max']}° · "
                  f"Right bend max {tw[name]['Right']['bend_max']}° @ f{tw[name]['Right']['bend_argmax']}")
        base = tw["pass1"]["Left"]["twist"][10]
        dip = {n: round(min(tw[n]["Left"]["twist"][15:36]) - base, 1) for n in tw}
        print(f"   left twist dip f15 ~ f35 (vs pass-1 f10 {base}°): {dip}")
        rec["twist"] = {n: {s: {k: v for k, v in r.items() if k not in ("bend", "twist")} for s, r in tw[n].items()} for n in tw}
        rec["twist_dip"] = dip
        # ee 도 9-3b 부터 같은 계획(자유 손 고정)이라 before = hold — 묶음 없는 값은 9-3a 기록(TWIST_DIP_9_3A_DEG)과 비교한다
        check(dip["hold"] >= TWIST_DIP_9_3A_DEG + 10.0,
              f"holding the free hand cuts the keyed left-wrist twist dip {TWIST_DIP_9_3A_DEG}° (9-3a record) → {dip['hold']}° (pass 1 {dip['pass1']}° · ee {dip['before']}°)")
    rows = vesper_bends(rec["final"])
    rec["vesper"] = {"left_twist_range": [min(r["twist_l"] for r in rows if r.get("twist_l") is not None), max(r["twist_l"] for r in rows if r.get("twist_l") is not None)],
                     "bend_r_at_key": next((r["bend_r"] for r in rows if abs(r["t"] - AT) < 1e-3), None)}
    print(f"   Vesper {rec['vesper']}")
    hand = next((r for r in follow if r["part"] == "right_hand"), None)
    check(hand is not None and hand["position_cm"]["p50"] <= 5.0, f"the right-hand key still follows (position {(hand or {}).get('position_cm')} cm)")
    if ee:
        before = dirty_count()
        times = [0.6, 0.767, 0.867, 0.933, 1.033, 1.2, 1.4, 1.6]
        b = capture(OUT / "eehold_before", ee["final"], "ee (held — 9-3b default)", times=times)
        rows_b: dict[int, list[str]] = {}
        for f in sorted(b["frames"], key=lambda f: (f["row"], f["view"] != "front")):
            rows_b.setdefault(f["row"], []).append(f["path"])
        c = capture(OUT / "eehold", rec["final"], "9-3b ee (free hand held)", times=times, sequence={"fps": 30, "start": 0.5, "end": 1.7},
                    compare={"label": "ee", "rows": [rows_b[r] for r in sorted(rows_b)]})
        rec["capture"] = {"compare": (c.get("compare") or {}).get("path"), "apng": (c.get("animation") or {}).get("path"), "times": times}
        print(f"   capture {rec['capture']}")
        check(dirty_count() == before, f"captures dirtied nothing ({before})")
    STATE["eehold"] = rec


# ---- ① 낫 생성 파지 규칙 · ② Attack1 키 선택 · ③ fix.body 결과 키 재생성 ----
GRIP_FLAGS = {"two_hand_weapon_grip": True, "foot_contact": True}
SICKLE_SEED = 20261101          # 9-1 낫 새 생성과 같은 seed 후보(20261101 ~ 04) — 대조 = 9-1 기록과 같은 경로
SCYTHE_DURATION = 4.0           # 8-1 기준 시험 길이
SCYTHE_TARGET_SPACING_CM = 60.0
SWORD_PROMPT = ("A person holds a sword with both hands, raises it over the right shoulder, slashes diagonally down to the left, "
                "then returns to a fighting stance.")   # 8-1 표준 프롬프트
WEAPON_MESH = "/Game/Equipment/Weapon/Mesh/SKM_Hero_Sickle"
HANDLE_LIMITS = {"angle_p50_deg": 20.0, "dist_p50_cm": 10.0}   # 로드맵 §5 U3 기준 3(사용자 결정 ④ 시작값)
LOCAL_AI_DIR = ROOT / "Saved" / "AnimGen" / "Import" / "LocalAI"
FIXBODY_BVH = LOCAL_AI_DIR / "job_20261026_192555_f991aa" / "A1" / "kimodo_03.bvh"   # 8-4 합본 낫(scythe_pick)과 같은 저장 Kimodo BVH
FIXBODY_KEY_STEP_S = 0.5


def sickle_weapon_request() -> dict:
    """Vesper 낫 요청 weapon — 8-1 통합 시험과 같은 값(부착 = DA_WD_Sickle1 AttachOffset · 소켓 WeaponHandR, 보조 손 = 8-4 E0 선분)."""
    att = json.loads((ROOT / "Tools" / "mcp" / "results" / "p84_weapon_attach.json").read_text(encoding="utf-8"))
    ao = att["definition"]["attach_offset"]
    seg = json.loads((ROOT / "Tools" / "mcp" / "anim_gen_phase8_4_state.json").read_text(encoding="utf-8"))["e0"]["grip_proposal"]["segment"]
    return {"mesh": WEAPON_MESH, "attach": {"socket": att["socket"]["name"], "offset": {"location": ao["location"], "rotation": ao["rotation_pyr"], "scale": ao["scale"]}},
            "lead_hand": "right", "grips": [{"hand": "left", "segment": {"from": seg["from"], "to": seg["to"]}}]}


def refine_request(name: str, prompt: str, family: str, *, grip: dict | None = None, constraints: list[dict] | None = None, weapon: bool = True) -> dict:
    """8-1 기준 시험(후보 4 · 파지 + 발 2차) — 낫은 대상 간격 60 · 요청 weapon(select handle 기록 · 무기 부착 캡처)."""
    refine = {"grip": {**({"target_spacing_cm": SCYTHE_TARGET_SPACING_CM} if family == "Sickle" else {}), **(grip or {})}}
    req = gen_request(name, prompt, family, constraints, duration_seconds=SCYTHE_DURATION, retarget={"align_mode": "per_bone"},
                      review={"capture": {"count": 8, "sequence": {"fps": 15}}})
    req["constraints"] = dict(GRIP_FLAGS)
    req["generation"].update(seed=SICKLE_SEED, candidates=4, refine=refine)
    if family == "Sickle" and weapon:
        req["weapon"] = sickle_weapon_request()
    return req


def candidates_of(job: dict) -> list[dict]:
    """select 후보별 Vesper 기록(자루 · 손목 · 파지 · 휘두름 · 관통) + 소스 쪽 자루 지표 · 규칙 통계."""
    sel = job.get("selection") or {}
    gen = {c["index"]: c for c in (job["cursor"]["values"]["generated"].get("candidates") or [])}
    out = []
    for c in sorted(sel.get("candidates") or [], key=lambda c: c["index"]):
        m = c["metrics"]
        g = gen.get(c["index"]) or {}
        rf = g.get("refine") or {}
        out.append({"index": c["index"], "seed": c["seed"], "rank": c["rank"], "score": c["score"], "handle": m.get("handle"), "wrist": m.get("wrist"),
                    "grip_pct": (m.get("grip") or {}).get("grip_pct"), "gap_p50": ((m.get("grip") or {}).get("gap_cm") or {}).get("p50"),
                    "swing_peak": (m.get("swing") or {}).get("peak_cm_s"), "penetration_pct": (m.get("clearance") or {}).get("penetration_pct"),
                    "source_handle": (rf.get("follow") or {}).get("handle"), "rule": ((rf.get("grip") or {}).get("stats") or {}).get("handle"),
                    "grip_target_error_cm": (rf.get("follow") or {}).get("grip_target_error_cm"), "key_pose": g.get("key_pose")})
    return out


def show_candidates(label: str, rows: list[dict], picked: dict | None) -> None:
    print(f"   {label}: picked {picked}")
    for r in rows:
        h = r["handle"] or {}
        print(f"     #{r['index']} seed {r['seed']} rank {r['rank']} · handle ∠ {h.get('grip_angle_p50')}° · palm ↔ handle {h.get('grip_dist_p50')} cm · "
              f"grip {r['grip_pct']}% (gap {r['gap_p50']}) · wrist {(r['wrist'] or {}).get('p50')}° over {(r['wrist'] or {}).get('over_pct')}% · "
              f"swing {r['swing_peak']} · pen {r['penetration_pct']}% · source {r['source_handle']}")
        if r["rule"]:
            print(f"        rule {r['rule']}")


def run_refine(key: str, req: dict) -> dict | None:
    plan, job, seconds = run_job(req, key)
    if job["status"] != "SUCCEEDED":
        return None
    rows = candidates_of(job)
    picked = (job.get("selection") or {}).get("picked")
    show_candidates(key, rows, picked)
    cap = (job.get("review") or {}).get("capture") or {}
    rec = {"job_id": job["job_id"], "final": job["generated_assets"][0], "seconds": seconds, "picked": picked, "candidates": rows,
           "hand_basis": job.get("hand_basis"), "capture": {k: cap.get(k) for k in ("sheet", "animation", "attachments") if cap.get(k)},
           "plan_rule": next((r for r in next(s for s in plan["candidates"][0]["steps"] if s["step"] == "generate")["inputs"]["refine"]["rules"]
                              if r["flag"] == "two_hand_weapon_grip"), None)}
    print(f"   capture {rec['capture']} · hand basis {rec['hand_basis']}")
    return rec


def section_scythe() -> None:
    """① 대조 — 9-1 낫 새 생성과 같은 요청(지금 규칙: 자루 축 = 1차 두 손목 선)."""
    print(f"== scythe — control: scythe prompt · {SCYTHE_DURATION}s · seeds {SICKLE_SEED} ~ +3 · grip (wrist line) + foot · weapon recorded")
    rec = run_refine("scythe", refine_request("AS_Vesper_Sickle_HandleCtl", SCYTHE_PROMPT, "Sickle"))
    if rec:
        STATE["scythe"] = rec


def section_handle() -> None:
    """① 운영 부착 자루 규칙(grip.handle weapon) — 같은 seed · 같은 요청에 규칙만. 기준(로드맵 §5 U3-3): 고른 후보 ∠ p50 ≤ 20° · 손바닥 ↔ 자루 p50 ≤ 10 cm."""
    print("== handle — the same request with generation.refine.grip.handle weapon (the attached handle)")
    rec = run_refine("handle", refine_request("AS_Vesper_Sickle_Handle", SCYTHE_PROMPT, "Sickle", grip={"handle": "weapon"}))
    if not rec:
        return
    check(bool(rec["hand_basis"]) and rec["hand_basis"]["spread_deg"] <= 0.5, f"hand basis measured {rec['hand_basis']}")
    pick = next((r for r in rec["candidates"] if r["index"] == (rec["picked"] or {}).get("index")), None)
    h = (pick or {}).get("handle") or {}
    check(h.get("grip_angle_p50") is not None and h["grip_angle_p50"] <= HANDLE_LIMITS["angle_p50_deg"],
          f"picked: two-hand line ∠ attached handle p50 {h.get('grip_angle_p50')}° ≤ {HANDLE_LIMITS['angle_p50_deg']:g}°")
    check(h.get("grip_dist_p50") is not None and h["grip_dist_p50"] <= HANDLE_LIMITS["dist_p50_cm"],
          f"picked: support palm ↔ handle p50 {h.get('grip_dist_p50')} cm ≤ {HANDLE_LIMITS['dist_p50_cm']:g} cm")
    ctl = STATE.get("scythe") or previous().get("scythe")
    if ctl:
        med = lambda rows, k: sorted((r["handle"] or {}).get(k) or 0.0 for r in rows)[len(rows) // 2]  # noqa: E731
        print(f"   candidates median ∠ {med(ctl['candidates'], 'grip_angle_p50')} → {med(rec['candidates'], 'grip_angle_p50')}° · palm ↔ handle "
              f"{med(ctl['candidates'], 'grip_dist_p50')} → {med(rec['candidates'], 'grip_dist_p50')} cm")
    STATE["handle"] = rec


def section_key2() -> None:
    """② Attack1 정점 자세를 전신 키 하나로(생성 1.2초 · pass1) 검 · 낫 선택 다시 생성 — 대조 = 같은 seed 키 없음(scythe · sword)."""
    t_star = strike()
    key = [{"type": "key_pose", "asset": ATTACK1, "times": [t_star], "at": [AT]}]
    out = STATE.setdefault("key2", {})
    for fam, prompt, name in (("Sickle", SCYTHE_PROMPT, "AS_Vesper_Sickle_KeySelect"), ("Sword", SWORD_PROMPT, "AS_Vesper_Sword_KeySelect")):
        print(f"== key2 — {fam}: candidates + grip/foot refine + Attack1 strike full key at {AT}s")
        rec = run_refine(f"key2 {fam}", refine_request(name, prompt, fam, constraints=key))
        if not rec:
            continue
        rec["vesper_pose"] = pose_distance_at(rec["final"], AT, ATTACK1, t_star)
        print(f"   picked Vesper pose at {AT}s ↔ Attack1 strike {rec['vesper_pose']}")
        out[fam] = rec


def section_sword() -> None:
    """② 대조(검) — 8-1 표준 검 프롬프트 · 같은 seed · 후보 4 · 파지 + 발 2차, 키 없음."""
    print(f"== sword — control: sword prompt · seeds {SICKLE_SEED} ~ +3 · grip + foot (no key)")
    rec = run_refine("sword", refine_request("AS_Vesper_Sword_KeySelectCtl", SWORD_PROMPT, "Sword"))
    if rec:
        rec["vesper_pose"] = pose_distance_at(rec["final"], AT, ATTACK1, strike())
        STATE["sword"] = rec


POSE_BONES = ["pelvis", "spine_03", "head", "upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r", "thigh_l", "calf_l", "foot_l",
              "thigh_r", "calf_r", "foot_r"]


def pose_at(asset: str, t: float) -> dict:
    p = profile(asset, POSE_BONES)["profile"]
    i = min(range(len(p["times"])), key=lambda k: abs(p["times"][k] - t))
    return {"time": p["times"][i], "pos": {b: p["position_cm"][b][i] for b in POSE_BONES if b in p["position_cm"]}}


def pose_distance(a: dict, b: dict) -> dict:
    """두 Vesper 자세의 차(cm) — 골반을 맞추고 엉덩 축 수평 방향을 b 에 맞춘 뒤 본별 거리(9-3a 와 같은 정의)."""
    def rel(pose):
        c = pose["pos"]["pelvis"]
        return {k: [v[0] - c[0], v[1] - c[1], v[2] - c[2]] for k, v in pose["pos"].items()}
    ra, rb = rel(a), rel(b)
    ha = math.atan2(ra["thigh_r"][1] - ra["thigh_l"][1], ra["thigh_r"][0] - ra["thigh_l"][0])
    hb = math.atan2(rb["thigh_r"][1] - rb["thigh_l"][1], rb["thigh_r"][0] - rb["thigh_l"][0])
    c, s = math.cos(hb - ha), math.sin(hb - ha)
    d = {k: round(math.dist([ra[k][0] * c - ra[k][1] * s, ra[k][0] * s + ra[k][1] * c, ra[k][2]], rb[k]), 2) for k in ra if k in rb and k != "pelvis"}
    vals = sorted(d.values())
    return {"p50": round(vals[len(vals) // 2], 2), "max": round(vals[-1], 2), "per_bone": d}


def pose_distance_at(asset: str, t: float, ref: str, t_ref: float) -> dict:
    return pose_distance(pose_at(asset, t), pose_at(ref, t_ref))


def measure_assets(assets: list[str], weapon: bool = True) -> list[dict]:
    """select 와 같은 측정(candidate_metrics — 지표 버전 6, body_clearance parts · per_frame · 자루 기록)을 대상 애셋에 직접."""
    from anim_gen import weapon as weapon_mod
    from anim_gen.editor import EditorClient
    from anim_gen.providers.builtin import RetargetPipe
    diags: list[dict] = []
    client = EditorClient()
    bones = RetargetPipe.selection_bones(client, VESPER, diags)
    hands, resolved = RetargetPipe.select_hands(client, {"weapon": weapon_mod.normalize(sickle_weapon_request())} if weapon else {}, VESPER_MESH_01, diags)
    bones.update(hands)
    grip = motion_metrics.grip_spacing(motion_metrics.gap_map(local_ai.SOMA_ARMS, bones["arm_dims"]), target_cm=SCYTHE_TARGET_SPACING_CM)
    items = must(editor("validate_animation", assets=assets, skeleton=VESPER, profile_bones=RetargetPipe.profile_bones(bones), profile_positions=True,
                        profile_rotations=True, body_clearance={"mesh": VESPER_MESH_01, "parts": "all", "per_frame": True}), "measure")["assets"]
    out = []
    for a, item in zip(assets, items):
        m = RetargetPipe.candidate_metrics(item, bones, None, None, grip["target_cm"], grip["tolerance_cm"]["target"], support="l", weapon=resolved)
        out.append({"asset": a, "grip_pct": (m.get("grip") or {}).get("grip_pct"), "gap_p50": ((m.get("grip") or {}).get("gap_cm") or {}).get("p50"),
                    "penetration_pct": (m.get("clearance") or {}).get("penetration_pct"), "head_deep_pct": (m.get("head_deep") or {}).get("deep_pct"),
                    "cross_pct": (m.get("cross") or {}).get("crossed_pct"), "wrist": m.get("wrist"), "handle": m.get("handle"),
                    "swing_peak": (m.get("swing") or {}).get("peak_cm_s"), "length": (item.get("numeric") or {}).get("length")})
    return out


def section_fixbody() -> None:
    """③ 대상 쪽에서 고친 자세(8-4 합본 낫 — fix.ops · timing · body_fit)를 0.5초 간격 전신 키(origin)로 다시 생성 — 고친 것이 생성에 남는가:
    A(보정 전 · 후) vs B(키 재생성, 대상 쪽 보정 없음)의 관통 · 머리목 · 파지 · 손목 · 자루 + 키 사이 자세 차."""
    if not check(FIXBODY_BVH.is_file(), f"fixbody: saved Kimodo BVH exists ({FIXBODY_BVH.name})"):
        return
    print("== fixbody — A: 8-4 combined sickle (BVH → fix.ops → retarget → timing → body_fit) · B: Kimodo with A's poses as full-body keys every 0.5 s")
    from anim_gen.editor import EditorClient
    from anim_gen.providers.builtin import RetargetPipe
    arm = (RetargetPipe.selection_bones(EditorClient(), VESPER, []).get("arm_dims") or {}).get("arm_cm", 47.66) / local_ai.SOMA_ARMS["arm_cm"]
    req_a = {"target_skeleton": VESPER, "target_mesh": VESPER_MESH_01, "hero": "Vesper", "family": "Sickle", "animation_name": "AS_Vesper_Sickle_FixBodyA",
             "description": "9-3b ③ — 8-4 합본 낫(대상 쪽 보정)", "motion_category": "weapon_action", "loop": False, "frame_rate": 30, "output_path": RUN,
             "provider": "blender", "motion_file": {"path": FIXBODY_BVH.as_posix()}, "retarget": {"body_clearance": "measure"},
             "fix": {"ops": [{"op": "stance_width"}, {"op": "foot_lock"}], "timing": True,
                     "body": {"grip": {"spacing_cm": 60.0, "tolerance_cm": round(motion_metrics.GRIP_TOL_CM * arm, 2)}}},
             "weapon": sickle_weapon_request()}
    _, job_a, sec_a = run_job(req_a, "fixbody A")
    if job_a["status"] != "SUCCEEDED":
        return
    body = (job_a.get("fix") or {}).get("body") or {}
    a_final, a_before = job_a["generated_assets"][0], body.get("source")
    length = float(measure_assets([a_final])[0]["length"] or 0.0)
    times = [round(i * FIXBODY_KEY_STEP_S, 4) for i in range(int(length / FIXBODY_KEY_STEP_S + 1e-6) + 1)]
    print(f"   A {a_final} (before body_fit {a_before}) · length {length}s · keys {times}")
    req_b = gen_request("AS_Vesper_Sickle_FixBodyB", SCYTHE_PROMPT, "Sickle", [{"type": "key_pose", "asset": a_final, "times": times}],
                        duration_seconds=round(length, 4), retarget={"align_mode": "per_bone", "body_clearance": "measure"})
    req_b["weapon"] = sickle_weapon_request()
    _, job_b, sec_b = run_job(req_b, "fixbody B")
    if job_b["status"] != "SUCCEEDED":
        return
    b_final = job_b["generated_assets"][0]
    follow, _ = follow_of(job_b)
    print(f"   B {b_final} · key follow {[(r['part'], r['keys'], r['position_cm']) for r in follow]}")
    rows = measure_assets([a for a in (a_before, a_final, b_final) if a])
    for r in rows:
        print(f"   {r['asset'].rsplit('/', 1)[1]}: pen {r['penetration_pct']}% · head_deep {r['head_deep_pct']}% · cross {r['cross_pct']}% · grip {r['grip_pct']}% "
              f"(gap {r['gap_p50']}) · wrist {(r['wrist'] or {}).get('p50')}°/{(r['wrist'] or {}).get('over_pct')}% · handle {r['handle']} · swing {r['swing_peak']}")
    mids = [round(t + FIXBODY_KEY_STEP_S / 2, 4) for t in times if t + FIXBODY_KEY_STEP_S / 2 < length]
    at_keys = [pose_distance_at(b_final, t, a_final, t)["p50"] for t in times[1:]]
    between = [pose_distance_at(b_final, t, a_final, t)["p50"] for t in mids]
    print(f"   B ↔ A pose p50 at keys {at_keys} · between keys {between}")
    before = dirty_count()
    times_cap = [round(length * i / 7, 3) for i in range(8)]
    ca = capture(OUT / "fixbody_a", a_final, "A — 8-4 combined (target-side fix)", times=times_cap, attachments=[{"mesh": WEAPON_MESH, "socket": "WeaponHandR",
                 "offset": sickle_weapon_request()["attach"]["offset"]}])
    rows_a: dict[int, list[str]] = {}
    for f in sorted(ca["frames"], key=lambda f: (f["row"], f["view"] != "front")):
        rows_a.setdefault(f["row"], []).append(f["path"])
    cb = capture(OUT / "fixbody_b", b_final, "B — regenerated from A's poses (keys 0.5 s)", times=times_cap, sequence={"fps": 15},
                 attachments=[{"mesh": WEAPON_MESH, "socket": "WeaponHandR", "offset": sickle_weapon_request()["attach"]["offset"]}],
                 compare={"label": "A (fixed)", "rows": [rows_a[r] for r in sorted(rows_a)]})
    check(dirty_count() == before, f"captures dirtied nothing ({before})")
    STATE["fixbody"] = {"a": {"job_id": job_a["job_id"], "final": a_final, "before": a_before, "seconds": sec_a}, "b": {"job_id": job_b["job_id"], "final": b_final,
                        "seconds": sec_b, "follow": follow}, "keys_s": times, "metrics": rows, "pose_at_keys_p50": at_keys, "pose_between_p50": between,
                        "capture": {"compare": (cb.get("compare") or {}).get("path"), "apng": (cb.get("animation") or {}).get("path")}}


def section_posectl() -> None:
    """② 대조의 Vesper 1.2초 자세 ↔ Attack1 정점(scythe · sword 최종, 생성 없음)."""
    prev = previous()
    t_star = strike()
    out = {}
    for key in ("scythe", "sword"):
        rec = STATE.get(key) or prev.get(key)
        if rec:
            out[key] = pose_distance_at(rec["final"], AT, ATTACK1, t_star)
            print(f"   {key} (no key) Vesper pose at {AT}s ↔ Attack1 strike p50 {out[key]['p50']} · max {out[key]['max']} cm")
    STATE["posectl"] = out


def capture(out: pathlib.Path, asset: str, label: str, **params) -> dict:
    from anim_gen import apng
    env = editor("capture_animation", asset=asset, mesh=VESPER_MESH_01, facing="+Y", output_dir=out.as_posix(), label=label, **params)
    res = must(env, f"capture {asset}")
    seq = res.get("sequence") or {}
    if seq.get("frames"):
        res["animation"] = apng.assemble(seq["frames"], out / "animation.png", float(seq["fps"]))
    return res


def section_e0capture() -> None:
    """⓪ E0 — ee 의 0.6 ~ 1.2초(사용자 판정 0.86초 둘레) 8 시각 시트 · 30 fps APNG — 어느 손목이 꺾여 보이는지."""
    ee = STATE.get("ee") or previous().get("ee")
    if not ee:
        check(False, "e0capture needs the ee run")
        return
    before = dirty_count()
    times = [0.6, 0.7, 0.767, 0.833, 0.867, 0.933, 1.033, 1.2]
    c = capture(OUT / "e0_ee", ee["final"], "ee (hand · feet keys) 0.6 ~ 1.2 s", times=times, sequence={"fps": 30, "start": 0.5, "end": 1.4})
    print(f"   sheet {c.get('sheet')} · apng {(c.get('animation') or {}).get('path')}")
    check(dirty_count() == before, f"capture dirtied nothing ({before})")
    STATE["e0capture"] = {"sheet": c.get("sheet"), "apng": (c.get("animation") or {}).get("path"), "times": times}


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


SECTIONS = {"hashes": section_hashes, "ee": section_ee, "e0wrist": section_e0wrist, "e0twist": section_e0twist, "vwrist": section_vwrist,
            "e0capture": section_e0capture, "eehold": section_eehold, "scythe": section_scythe, "handle": section_handle, "sword": section_sword,
            "key2": section_key2, "fixbody": section_fixbody, "posectl": section_posectl, "dirty": section_dirty}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(s for s in SECTIONS if s not in E0_SECTIONS), help="comma separated: " + ",".join(SECTIONS))
    ap.add_argument("--seed", type=int, default=SEED, help=f"seed (default {SEED})")
    args = ap.parse_args()
    globals().update(SEED=args.seed)
    STATE.update(seed=args.seed)
    t0 = time.time()
    names = [n.strip() for n in args.only.split(",")]
    for name in names:
        SECTIONS[name]()
    STATE["seconds"] = round(time.time() - t0, 1)
    out = ROOT / "Tools" / "mcp" / "anim_gen_phase9_3b_state.json"
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
