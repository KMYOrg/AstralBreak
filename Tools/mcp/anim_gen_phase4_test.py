"""AI 애니 생성 Phase 4 — blender Provider(BVH → FBX → Phase 1 리타깃) 실제 Blender + 에디터 통합 테스트 (Docs/AIAnimation/DevelopmentGuide.md §14 Phase 4).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase4_test.py [--bvh <path>|synthetic] [--only ...]

뜬 에디터(AnimGraphMcp 플러그인)와 정책의 Blender(paths.blender_executable)를 쓴다. anim_gen 은 같은 프로세스의 Service 로 부르고,
상태는 Saved/AnimGen/TestRuns/P4Run<시각>/ 에 격리한다. Mock 단계(실행 파일 없음 · 실패 · 타임아웃 · 재시작)는 pytest(test_blender.py).
--bvh 기본값은 CMU 01_01(Saved/AnimGen/Import/Sources/CMU_01_01/01_01.bvh — 사용자 승인 다운로드). synthetic 이면 합성 BVH(관절 11개,
앞으로 걷는 루트)를 Sources/Synthetic/ 에 만들어 쓴다(파이프라인 점검용 — 완료 기준은 공개 BVH).
섹션:
  hashes   — (맨 앞) 대상 스켈레톤 · 메시 .uasset SHA-256 · Content/ git 상태 · 미저장 패키지 수
  blender  — list_motion_providers: blender 구현 · 설치 · 사용 가능
  plan     — BVH 헤더 · 단위 · 정면 회전 · 범위가 계획에 고정되고 Blender 를 띄우지 않는다 · 루트 밖 파일 거부
  generate — 완료 기준: BVH → (Blender 서브프로세스, poll) → FBX → import → IK Rig(수동 체인 또는 자동) → RTG match_existing → 리타깃 →
             Vesper(SK_StreetDemon_F_01) AS_ 저장 + validate_animation. 임포트된 소스 스켈레톤(본 수 · 루트 · 스케일 1 · 바닥 · 정면)도 잰다
  trim     — motion_file.range.start 로 BVH 첫 프레임(cgspeed CMU 의 기준 포즈 프레임)을 빼면 한 프레임 튐이 사라지는지
  auto     — 체인 없이(자동 캐릭터라이즈) 같은 BVH — 성공이든 RETARGET_FAILED(본 계층)든 기록
  cancel   — 실제 Blender 를 띄운 직후 cancel_generation → 프로세스 종료 · report 없음
  dirty    — (맨 뒤) 해시 불변 · 미저장 수 그대로 · Content/ 변경은 이번 실행 폴더뿐
요약은 Tools/mcp/anim_gen_phase4_state.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

from anim_graph_mcp import bridge

STAMP = time.strftime("%m%d_%H%M%S")
ROOT = pathlib.Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P4Run{STAMP}"
os.environ["ANIM_GEN_STATE_DIR"] = str(STATE_DIR)

from anim_gen import bvh  # noqa: E402
from anim_gen.service import Service  # noqa: E402
from anim_gen.store import Store  # noqa: E402

VESPER = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
VESPER_MESH_01 = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
CMU_BVH = ROOT / "Saved" / "AnimGen" / "Import" / "Sources" / "CMU_01_01" / "01_01.bvh"
SYNTH_BVH = ROOT / "Saved" / "AnimGen" / "Import" / "Sources" / "Synthetic" / "walk_synth.bvh"
RUN = f"/Game/Animation/Test/AIAnimation/P4Run{STAMP}"
HASHED = [VESPER, VESPER_MESH_01]
# CMU(cgspeed BVH) 관절 → Vesper 자동 IK Rig 의 표준 체인 이름(FCharacterizationStandard). LHipJoint · RHipJoint 는 체인 밖(골반 쪽 보조 본)
CMU_PELVIS = "Hips"
CMU_CHAINS = [
    {"name": "Spine", "start": "LowerBack", "end": "Spine1"},
    {"name": "Neck", "start": "Neck", "end": "Neck1"},
    {"name": "Head", "start": "Head", "end": "Head"},
    {"name": "LeftClavicle", "start": "LeftShoulder", "end": "LeftShoulder"},
    {"name": "LeftArm", "start": "LeftArm", "end": "LeftHand", "goal": "LeftHandIK"},
    {"name": "RightClavicle", "start": "RightShoulder", "end": "RightShoulder"},
    {"name": "RightArm", "start": "RightArm", "end": "RightHand", "goal": "RightHandIK"},
    {"name": "LeftLeg", "start": "LeftUpLeg", "end": "LeftToeBase", "goal": "LeftFootIK"},
    {"name": "RightLeg", "start": "RightUpLeg", "end": "RightToeBase", "goal": "RightFootIK"},
]
FAILS: list[str] = []
STATE: dict = {"run": RUN, "state_dir": STATE_DIR.as_posix()}
SERVICE = Service(store=Store(STATE_DIR))
ARGS = argparse.Namespace(bvh=str(CMU_BVH))


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


def exists(path: str) -> bool:
    name = path.rsplit("/", 1)[1]
    items = must(editor("search_animations", query=name, path_prefix=path.rsplit("/", 1)[0], **{"class": "all"}), "exists")["items"]
    return any(i["name"] == name for i in items)


def bvh_path() -> pathlib.Path:
    if ARGS.bvh != "synthetic":
        return pathlib.Path(ARGS.bvh)
    sys.path.insert(0, str(ROOT / "Tools" / "mcp" / "anim_gen" / "tests"))
    from conftest import make_bvh  # 합성 BVH — pytest 와 같은 사람(관절 11개)
    text = make_bvh(frames=121)
    head, _, _ = text.partition("MOTION")
    rows = "\n".join(" ".join(["0", "98", f"{i * 0.5:.3f}"] + ["0"] * 33) for i in range(121))  # 1초 동안 60cm 앞(+Z)으로
    SYNTH_BVH.parent.mkdir(parents=True, exist_ok=True)
    SYNTH_BVH.write_text(f"{head}MOTION\nFrames: 121\nFrame Time: 0.00833333\n{rows}\n", encoding="utf-8")
    return SYNTH_BVH


def base_request(path: pathlib.Path, **overrides) -> dict:
    joints = {j.name for j in bvh.read(path).joints}
    cmu = {"LowerBack", "LHipJoint"} <= joints
    req = {"target_skeleton": VESPER, "target_mesh": VESPER_MESH_01, "hero": "Vesper", "family": "Mocap",
           "animation_name": "AS_Vesper_Mocap_ForwardJumpP4" if cmu else "AS_Vesper_Mocap_SynthWalkP4",
           "description": f"{path.name} (BVH) → Vesper", "motion_category": "locomotion", "loop": False, "frame_rate": 30,
           "motion_file": {"path": path.as_posix()}, "provider": "blender", "output_path": RUN,
           "retarget": {"source_pelvis": CMU_PELVIS, "source_chains": CMU_CHAINS} if cmu else {}}
    req.update(overrides)
    return {k: v for k, v in req.items() if v is not ...}


def req_rate(path: pathlib.Path) -> int:
    return base_request(path)["frame_rate"]


def wait_job(job: dict, limit: float = 300.0) -> tuple[dict, float]:
    t0 = time.time()
    while job["status"] == "RUNNING" and time.time() - t0 < limit:
        time.sleep(0.5)
        env = SERVICE.get_generation_status(job_id=job["job_id"])
        job = env["result"] if env["ok"] else env["error"]["details"].get("job", job)
    return job, round(time.time() - t0, 2)


# ---- 섹션 ----
def section_hashes() -> None:
    print("== target hashes · content · dirty (before)")
    STATE["hashes"] = {p: sha256(p) for p in HASHED}
    STATE["content_before"] = content_changes()
    STATE["dirty_before"] = dirty_count()
    print(f"   {len(HASHED)} assets hashed · Content changes before: {len(STATE['content_before'])} · dirty {STATE['dirty_before']}")


def section_blender() -> None:
    print("== blender provider state")
    providers = {p["name"]: p for p in must(SERVICE.list_motion_providers(), "providers")["providers"]}
    state = providers["blender"]["state"]
    print(f"   {state['install_note']}")
    check(state["implemented"] and state["installed"] and state["available"], "blender implemented · installed · available (policy paths.blender_executable)")
    STATE["blender"] = {"install_note": state["install_note"]}


def section_plan() -> None:
    print("== plan (no Blender, no assets)")
    path = bvh_path()
    before = dirty_count()
    plan = must(SERVICE.plan_motion_generation(request=base_request(path)), "plan")
    [cand] = plan["candidates"]
    r = cand["steps"][0]["resolved"]
    print(f"   {r['bvh']['joint_count']} joints · root {r['bvh']['root']} · {r['bvh']['frames']} frames @ {r['fps']['source']} fps · unit {r['unit']} · "
          f"facing {r['facing']['source']} → {r['facing']['target']} (rotate {r['facing']['rotate_z_deg']}°) · risks {cand['risks']}")
    check(cand["chain"] == ["blender", "retarget"] and plan["order"] == ["blender"], "chain blender → retarget (provider named)")
    check(r["facing"]["target"] == "+Y" and r["facing"]["target_from"] == VESPER, "target facing measured on the Vesper skeleton (+Y)")
    check(r["facing"]["source"] is not None, f"source facing measured from the BVH feet ({r['facing']['source_detail']})")
    check(len(r["sha256"]) == 64 and r["range"]["frames"] == r["bvh"]["frames"] - r["range"]["trimmed_frames"],
          f"file hash and full range pinned (end aligned to {req_rate(path)} fps: {r['range']['trimmed_frames']} source frame(s) dropped)")
    outside = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P4Run{STAMP}" / "outside.bvh"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    env = SERVICE.plan_motion_generation(request=base_request(path, motion_file={"path": outside.as_posix()}))
    check(not env["ok"] and env["error"]["code"] == "IMPORT_SOURCE_NOT_ALLOWED", "a motion file outside ImportSourceRoots -> IMPORT_SOURCE_NOT_ALLOWED")
    check(not (ROOT / "Saved" / "AnimGen" / "Import" / "Blender").exists() or not any(
        p.name.startswith(plan["plan_id"]) for p in (ROOT / "Saved" / "AnimGen" / "Import" / "Blender").iterdir()), "planning wrote no Blender output")
    check(dirty_count() == before, f"planning left the dirty count unchanged ({before})")
    STATE["plan"] = {"plan_id": plan["plan_id"], "bvh": {k: r["bvh"][k] for k in ("joint_count", "root", "frames", "fps", "duration", "warnings")},
                     "unit": r["unit"], "facing": {k: r["facing"][k] for k in ("source", "target", "rotate_z_deg")}, "risks": cand["risks"],
                     "expected_limitations": [lim["code"] for lim in cand["expected_limitations"]]}


def inspect_source(job: dict) -> dict:
    skel = next(a for a in job["intermediate_assets"] if a.endswith("_Skeleton"))
    r = must(editor("inspect_skeleton", skeleton=skel, details=True), "inspect source")
    seg = bvh.skeleton_segments(r["bones"])
    pos = {b["name"]: b["ref_component"]["t"] for b in r["bones"]}
    return {"skeleton": skel, "bones": r["bone_count"], "root": r["root_bone"], "scaled": [b["name"] for b in r["bones"] if "s" in b["ref_component"]],
            "height_cm": round(bvh.height(seg), 2), "min_z": min(p[2] for p in pos.values()), "root_z": pos[r["root_bone"]][2],
            "facing": bvh.facing(seg)["axis"], "template_match": {k: r["template_match"].get(k) for k in ("used", "name", "percent")}}


def section_generate() -> None:
    print("== generate (criterion: public BVH → Vesper AS_ + validate_animation)")
    path = bvh_path()
    req = base_request(path)
    plan = must(SERVICE.plan_motion_generation(request=req), "plan")
    t0 = time.time()
    job = must(SERVICE.generate_motion(plan_id=plan["plan_id"], save=True), "generate_motion")
    check(job["status"] == "RUNNING" and job["pending"] and job["pending"]["provider"] == "blender", "generate_motion returns RUNNING with a Blender handle")
    job, waited = wait_job(job)
    seconds = round(time.time() - t0, 2)
    if job["status"] != "SUCCEEDED":
        print(f"[FAIL] job {job['status']}: {json.dumps(job.get('error'), ensure_ascii=False)[:2000]}")
        print(f"   fallback_history {json.dumps(job.get('fallback_history'), ensure_ascii=False)[:2000]}")
    final = f"{RUN}/{req['animation_name']}"
    check(job["status"] == "SUCCEEDED" and [e["to"] for e in job["events"]] == ["QUEUED", "RUNNING", "SUCCEEDED"], f"job QUEUED → RUNNING → SUCCEEDED ({seconds}s)")
    if job["status"] != "SUCCEEDED":
        STATE["generate"] = {"job_id": job["job_id"], "status": job["status"], "error": job.get("error")}
        return
    converted = job["cursor"]["values"]["converted"]
    fbx = pathlib.Path(job["cursor"]["values"]["file"])
    print(f"   Blender {converted['blender']}: {converted['bones']} bones · lift {converted['ground_lift_cm']}cm · facing {converted['facing']} · "
          f"{converted['frames']} · {converted['seconds']}s · root path {converted['root_path']}")
    roots = must(editor("get_editor_status"), "status")["generation"]["import_source_roots"]
    check(fbx.is_file() and any(fbx.as_posix().lower().startswith(r.lower()) for r in roots), f"FBX under ImportSourceRoots: {fbx.as_posix()}")
    check(job["generated_assets"] == [final] and exists(final) and uasset(final).is_file(), f"{final} saved")
    src = inspect_source(job)
    print(f"   source skeleton {src}")
    joints = STATE.get("plan", {}).get("bvh", {}).get("joint_count") or len(bvh.read(path).joints)
    check(src["bones"] == joints and src["root"] == bvh.read(path).joints[0].name, f"imported skeleton: {src['bones']} bones = BVH joints, root {src['root']} (Armature null skipped)")
    check(not src["scaled"], "every reference bone has scale 1 (FBX unit 1 · no node scale)")
    check(abs(src["min_z"]) < 0.5 and src["root_z"] > 10, f"reference pose grounded (lowest {src['min_z']}cm, root {src['root_z']}cm above)")
    check(src["facing"] == "+Y", f"imported skeleton faces the target (+Y): {src['facing']}")
    anim = next(a for a in job["intermediate_assets"] if a.endswith("_Anim"))
    v = must(editor("validate_animation", assets=[final], sources=[anim], skeleton=VESPER, source_feet=["LeftFoot", "RightFoot"],
                    source_pelvis=src["root"]), "validate result")["assets"][0]
    n = v["numeric"]
    print(f"   validate vs imported source: {v['status']} · frames {n.get('frames')} @ {n.get('frame_rate')} · length {n.get('length')} · "
          f"relative {json.dumps(v.get('relative', {}), ensure_ascii=False)[:600]}")
    check(v["status"] in ("PASSED", "PASSED_WITH_WARNINGS"), f"validate_animation {v['status']}")
    check(abs((n.get("frame_rate") or 0) - 30) < 0.01, "result resampled to the requested 30 fps (import sample_rate)")
    codes = [lim["code"] for lim in job["limitations"]]
    print(f"   built-in validation {job['validation']['status']} · limitations {codes}")
    STATE["generate"] = {"job_id": job["job_id"], "asset": final, "seconds": seconds, "fbx": fbx.as_posix(), "converted": converted, "source": src,
                         "validation_builtin": job["validation"]["status"], "validate": {"status": v["status"], "numeric": n, "relative": v.get("relative"),
                                                                                          "structural": v.get("structural")},
                         "limitations": codes}


def section_trim() -> None:
    print("== range.start skips the BVH's first frame (cgspeed CMU: frame 0 is a near-zero reference pose)")
    path = bvh_path()
    info = bvh.read(path)
    req = base_request(path, animation_name=base_request(path)["animation_name"] + "Trim",
                       motion_file={"path": path.as_posix(), "range": {"start": info.frame_time * 1.0001}})
    plan = must(SERVICE.plan_motion_generation(request=req), "plan trim")
    rng = plan["candidates"][0]["steps"][0]["resolved"]["range"]
    job, _ = wait_job(must(SERVICE.generate_motion(plan_id=plan["plan_id"], save=True), "generate trim"))
    check(job["status"] == "SUCCEEDED" and rng["first"] == 1, f"trimmed job {job['status']} from BVH frame {rng['first']} to {rng['last']}")
    if job["status"] != "SUCCEEDED":
        return
    final = job["generated_assets"][0]
    v = must(editor("validate_animation", assets=[final], skeleton=VESPER), "validate trim")["assets"][0]
    codes = [s["code"] for s in v["structural"]]
    print(f"   {final}: {v['status']} · max {v['numeric']['max_deg_per_frame']}°/frame at {v['numeric'].get('max_deg_frame')} · structural {codes}")
    check(v["status"] != "FAILED" and v["numeric"]["max_deg_per_frame"] < 90, "without the reference frame the one-frame jump is gone (no source needed)")
    STATE["trim"] = {"asset": final, "range": rng, "status": v["status"], "max_deg_per_frame": v["numeric"]["max_deg_per_frame"], "structural": codes}


def section_auto() -> None:
    print("== auto IK rig (no chains)")
    path = bvh_path()
    req = base_request(path, retarget=..., animation_name=base_request(path)["animation_name"] + "Auto")
    plan = must(SERVICE.plan_motion_generation(request=req), "plan auto")
    job, _ = wait_job(must(SERVICE.generate_motion(plan_id=plan["plan_id"], save=True), "generate auto"))
    if job["status"] == "SUCCEEDED":
        src = inspect_source(job)
        print(f"   auto succeeded with template {src['template_match']} · validation {job['validation']['status']}")
        STATE["auto"] = {"status": "SUCCEEDED", "template_match": src["template_match"], "validation": job["validation"]["status"], "asset": job["generated_assets"]}
    else:
        [h] = job["fallback_history"][-1:]
        bones = ((h.get("editor_error") or {}).get("details") or {}).get("bones") or []
        print(f"   auto failed: {h['cause']} {h['reason']} · bones returned {len(bones)}")
        check(h["cause"] == "RETARGET_FAILED" and len(bones) > 0, "auto failure is RETARGET_FAILED with the bone hierarchy (manual chains next)")
        STATE["auto"] = {"status": job["status"], "cause": h["cause"], "reason": h["reason"], "bones": len(bones)}
    check(True, f"auto IK rig outcome recorded: {STATE['auto']['status']}")


def section_cancel() -> None:
    print("== cancel stops the real Blender process")
    path = bvh_path()
    req = base_request(path, animation_name=base_request(path)["animation_name"] + "Cancel")
    plan = must(SERVICE.plan_motion_generation(request=req), "plan cancel")
    job = must(SERVICE.generate_motion(plan_id=plan["plan_id"]), "generate cancel")
    report = pathlib.Path(job["pending"]["handle"]["report"])
    env = SERVICE.cancel_generation(job_id=job["job_id"])
    job = must(env, "cancel")
    time.sleep(1.0)
    print(f"   cancel_effect {job.get('cancel_effect')}")
    check(job["status"] == "CANCELLED" and (job.get("cancel_effect") or {}).get("stopped") is True, "CANCELLED and the Blender process was stopped")
    check(not report.exists(), "no report written after the stop")
    check(SERVICE.get_generation_status(job_id=job["job_id"])["result"]["status"] == "CANCELLED", "status stays CANCELLED (no further poll)")
    STATE["cancel"] = {"job_id": job["job_id"], "effect": job.get("cancel_effect")}


def section_dirty() -> None:
    print("== target hashes · content · dirty (after)")
    if "hashes" in STATE:
        changed = [p for p, h in STATE["hashes"].items() if sha256(p) != h]
        check(not changed, f"target skeleton · mesh .uasset SHA-256 unchanged ({len(STATE['hashes'])} files)")
    if "dirty_before" in STATE:
        check(dirty_count() == STATE["dirty_before"], f"unsaved packages unchanged ({STATE['dirty_before']}) — every write was saved")
    if "content_before" in STATE:
        new = [p for p in content_changes() if p not in STATE["content_before"]]
        run_dir = "Content/" + RUN.removeprefix("/Game/") + "/"
        outside = [p for p in new if not p.startswith(run_dir)]
        print(f"   new Content changes {len(new)} (outside this run's folder: {outside})")
        check(not outside, "Content/ changes are only this run's folder")
        STATE["content_new"] = new


SECTIONS = {"hashes": section_hashes, "blender": section_blender, "plan": section_plan, "generate": section_generate, "trim": section_trim,
            "auto": section_auto, "cancel": section_cancel, "dirty": section_dirty}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bvh", default=str(CMU_BVH), help="BVH path under ImportSourceRoots, or 'synthetic'")
    ap.add_argument("--only", default=",".join(SECTIONS), help="comma separated: " + ",".join(SECTIONS))
    args = ap.parse_args()
    ARGS.bvh = args.bvh
    STATE["bvh"] = args.bvh
    if args.bvh != "synthetic" and not pathlib.Path(args.bvh).is_file():
        print(f"[FAIL] no BVH at {args.bvh} — download it first (see the module docstring) or pass --bvh synthetic")
        return 2
    t0 = time.time()
    for name in args.only.split(","):
        SECTIONS[name.strip()]()
    STATE["seconds"] = round(time.time() - t0, 1)
    out = ROOT / "Tools" / "mcp" / ("anim_gen_phase4_state.json" if args.bvh != "synthetic" else "anim_gen_phase4_synthetic_state.json")
    out.write_text(json.dumps(STATE, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"state -> {out.as_posix()}")
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print("  - " + f)
    print("PASS" if not FAILS else "FAIL")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
