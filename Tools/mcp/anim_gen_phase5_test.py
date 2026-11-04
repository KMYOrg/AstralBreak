"""AI 애니 생성 Phase 5 — local_ai Provider(Kimodo 텍스트 → 모션 → Blender → 리타깃) 실제 Kimodo · Blender · 에디터 통합 테스트
(Docs/AIAnimation/DevelopmentGuide.md §14 Phase 5).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase5_test.py [--only ...]

뜬 에디터(AnimGraphMcp 플러그인) · 정책의 Kimodo venv(paths.kimodo_python · kimodo_hf_cache) · Blender(paths.blender_executable)를 쓴다.
anim_gen 은 같은 프로세스의 Service 로 부르고, 상태는 Saved/AnimGen/TestRuns/P5Run<시각>/ 에 격리한다. Mock 단계(설치 없음 · 실패 ·
타임아웃 · 제약 형식 · 루트 트랙)는 pytest(test_local_ai.py). Kimodo 1건은 약 40초 · RAM 약 15 GB(텍스트 인코더 CPU) — 섹션은 순서대로
한 건씩만 돌린다(generate · constraint 가 각 1건, cancel 은 띄운 직후 멈춘다).
섹션:
  hashes     — (맨 앞) 대상 스켈레톤 · 메시 .uasset SHA-256 · Content/ git 상태 · 미저장 패키지 수
  state      — list_motion_providers: local_ai 구현 · 설치 · 사용 가능 · license ok, 사슬에 쓰는 blender 도 사용 가능
  plan       — 사슬 local_ai → blender → retarget, 계획에 프롬프트 · 프레임 · seed · 모델 커밋 · 예상 BVH 규약 · SOMA 체인 고정.
               거부(프롬프트 없음 · 10초 초과 · 제약 시각 밖 · 루트 밖 NPZ · 보정 op). 계획은 Kimodo 를 띄우지 않고 애셋 0 · 더티 0
  generate   — 완료 기준: 프롬프트 → Kimodo(seed 고정) → BVH → Blender(+ 프레임 렌더 비교) → import → SOMA 수동 체인 IK Rig →
               RTG match_existing(per_bone) → 팔-몸통 관통 보정 → Vesper AS_ 저장 + validate_animation(소스 대비 · 손가락 · 관통)
  constraint — root_path(3초에 앞 400 cm · 왼쪽 180°) → Kimodo 루트 트랙과 Vesper 결과 루트의 위치 · 회전
  cancel     — 실제 Kimodo 를 띄운 직후 cancel_generation → 프로세스 종료 · report 없음
  dirty      — (맨 뒤) 해시 불변 · 미저장 수 그대로 · Content/ 변경은 이번 실행 폴더뿐
요약은 Tools/mcp/anim_gen_phase5_state.json.
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
STATE_DIR = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P5Run{STAMP}"
os.environ["ANIM_GEN_STATE_DIR"] = str(STATE_DIR)

from anim_gen.providers import local_ai  # noqa: E402
from anim_gen.service import Service  # noqa: E402
from anim_gen.store import Store  # noqa: E402

VESPER = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
VESPER_MESH_01 = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
RUN = f"/Game/Animation/Test/AIAnimation/P5Run{STAMP}"
HASHED = [VESPER, VESPER_MESH_01]
PROMPT = "A person walks forward, turns around and walks back."
SEED = 20261025
DURATION = 6.0
# root_path: 3초(= 클립 끝 프레임 90)에 앞 400 cm · 왼쪽으로 180° — 끝 프레임이라 결과 애셋의 처음 → 끝 루트 이동 · Yaw 로 바로 잰다
CONSTRAINT_T = 3.0
CONSTRAINT_POINT = {"t": CONSTRAINT_T, "forward_cm": 400.0, "left_cm": 0.0, "yaw_deg": 180.0}
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


def import_root() -> pathlib.Path:
    return pathlib.Path(must(editor("get_editor_status"), "status")["generation"]["import_source_roots"][0])


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


def pid_alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, errors="replace").stdout
    return any(line.split()[1:2] == [str(pid)] for line in out.splitlines() if line.strip())


def base_request(**overrides) -> dict:
    req = {"target_skeleton": VESPER, "target_mesh": VESPER_MESH_01, "hero": "Vesper", "family": "Kimodo",
           "animation_name": "AS_Vesper_Kimodo_WalkTurnBackP5", "description": "앞으로 걷다 돌아서 되돌아 걷기 (Kimodo)",
           "motion_category": "locomotion", "loop": False, "frame_rate": 30, "duration_seconds": DURATION, "prompt": PROMPT,
           "generation": {"seed": SEED}, "review": {"render": {"count": 4}}, "output_path": RUN}
    req.update(overrides)
    return {k: v for k, v in req.items() if v is not ...}


def wait_job(job: dict, limit: float = 600.0) -> tuple[dict, float]:
    t0 = time.time()
    while job["status"] == "RUNNING" and time.time() - t0 < limit:
        time.sleep(1.0)
        env = SERVICE.get_generation_status(job_id=job["job_id"])
        job = env["result"] if env["ok"] else env["error"]["details"].get("job", job)
    return job, round(time.time() - t0, 2)


def step_of(cand: dict, name: str) -> dict:
    return next(s for s in cand["steps"] if s["step"] == name)


def bvh_root_rows(path: pathlib.Path) -> list[list[float]]:
    """Kimodo BVH(루트 트랙 적용 뒤)의 Root 채널 — Xposition(왼쪽) Yposition Zposition(앞) Zrotation Yrotation(θ, 왼쪽 +) Xrotation."""
    lines = path.read_text(encoding="utf-8").splitlines()
    motion = next(i for i, line in enumerate(lines) if line.strip() == "MOTION")
    return [[float(v) for v in line.split()[:6]] for line in lines[motion + 3:] if line.strip()]


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
    return {"source_anim": next((a for a in inter if "/Import/Motion/" in a), None),
            "source_skeleton": next((a for a in inter if a.endswith("_Skeleton")), None),
            "ik_target": f"{work}/IK_Target" if f"{work}/IK_Target" in inter else None,
            "retargeter": job["cursor"]["values"].get("retargeter")}


def validate_result(final: str, assets: dict, profile: bool = True) -> dict:
    params = {"assets": [final], "sources": [assets["source_anim"]], "skeleton": VESPER, "source_pelvis": local_ai.SOMA_PELVIS,
              "source_feet": local_ai.SOMA_FEET, "fingers": {"retargeter": assets["retargeter"]},
              "body_clearance": {"mesh": VESPER_MESH_01, **({"ik_rig": assets["ik_target"]} if assets["ik_target"] else {})}}
    if profile:
        params.update(profile_bones=["root", "thigh_l", "thigh_r"], profile_positions=True)
    return must(editor("validate_animation", **params), "validate result")["assets"][0]


def issue_codes(obj: dict | None) -> list[str]:
    return [i.get("code") for i in (obj or {}).get("issues", []) if i.get("level") == "warning"]


# ---- 섹션 ----
def section_hashes() -> None:
    print("== target hashes · content · dirty (before)")
    STATE["hashes"] = {p: sha256(p) for p in HASHED}
    STATE["content_before"] = content_changes()
    STATE["dirty_before"] = dirty_count()
    print(f"   {len(HASHED)} assets hashed · Content changes before: {len(STATE['content_before'])} · dirty {STATE['dirty_before']}")


def section_state() -> None:
    print("== local_ai provider state")
    providers = {p["name"]: p for p in must(SERVICE.list_motion_providers(), "providers")["providers"]}
    state = providers["local_ai"]["state"]
    print(f"   {state.get('install_note')} · license {state.get('license')}")
    check(state["implemented"] and state["installed"] and state["available"], "local_ai implemented · installed · available (policy paths.kimodo_*)")
    check(state.get("license") == "ok" and providers["local_ai"]["capabilities"]["license"] == "ok", "local_ai license ok (Kimodo-SOMA-RP-v1.2)")
    check(providers["blender"]["state"]["available"], "blender (the BVH → FBX step of the chain) available")
    python, cache = local_ai.KimodoProvider.paths(SERVICE.policy())
    post = local_ai.KimodoProvider.postprocess_available(python)
    commit = local_ai.KimodoProvider.model_commit(cache)
    check(bool(commit) and len(commit) == 40, f"offline cache pins the model commit ({commit})")
    print(f"   motion_correction (foot-skate post-process) installed: {post}")
    STATE["state"] = {"install_note": state.get("install_note"), "license": state.get("license"), "postprocess_available": post, "model_commit": commit}


def section_plan() -> None:
    print("== plan (no Kimodo, no assets)")
    roots = import_root()
    local_dir = roots / "LocalAI"
    before_runs = sorted(p.name for p in local_dir.iterdir()) if local_dir.is_dir() else []
    before = dirty_count()
    plan = must(SERVICE.plan_motion_generation(request=base_request()), "plan")
    [cand] = plan["candidates"]
    gen, conv, imp, rt = (step_of(cand, s) for s in ("generate", "convert", "import", "retarget"))
    g = gen["inputs"]
    print(f"   order {plan['order']} · chain {cand['chain']} · excluded {[(e['provider'], e['cause'], e['reason']) for e in plan['excluded']]}")
    print(f"   generate: frames {g['frames']} @ {g['fps']} · seed {g['seed']} · samples {g['samples']} · steps {g['steps']} · postprocess {g['postprocess']} · "
          f"commit {g['model_commit']} · risks {cand['risks']}")
    check(cand["provider"] == "local_ai" and cand["chain"] == ["local_ai", "blender", "retarget"], "auto route: local_ai → blender → retarget (existing_motion has no source hint)")
    ex = {e["provider"]: e for e in plan["excluded"]}
    check(ex.get("existing_motion", {}).get("reason") == "NO_SOURCE_HINT" and ex.get("external.meshy", {}).get("cause") == "APPROVAL_REQUIRED",
          "excluded: existing_motion NO_SOURCE_HINT · external.meshy APPROVAL_REQUIRED (paid blocked)")
    check(g["prompt"] == PROMPT and g["model"] == local_ai.MODEL and g["model_commit"] == STATE.get("state", {}).get("model_commit", g["model_commit"]),
          "prompt · model · model commit pinned")
    check(g["frames"] == int(round(DURATION * 30)) + 1 and g["fps"] == 30.0 and g["seed"] == SEED and g["samples"] == 1 and g["constraints"] == [],
          f"length {DURATION}s = {g['frames']} frames @ 30 · seed {SEED} · 1 sample pinned")
    exp = conv["expected"]
    check(conv["provider"] == "blender" and conv["inputs"]["from_step"] == "generate" and conv["resolved"] is None
          and exp == {"unit": "cm", "facing": "+Y", "joints": 78, "fps": 30.0, "frames": g["frames"]} and "CONVERT_RESOLVED_AT_RUN" in cand["risks"],
          f"convert step expects the Kimodo BVH (cm · +Y · 78 joints · 30 fps) and resolves it at run time")
    review = conv["inputs"]["review"]
    check(review and review["times"] == [0.0, 2.0, 4.0, 6.0] and review["views"] == ["front", "side"],
          f"review.render count 4 spread over the expected {DURATION}s clip: {review and review['times']}")
    check(imp["inputs"]["sample_rate"] is None, "no resample (Kimodo 30 fps = request 30)")
    r = rt["inputs"]
    check(r["source_pelvis"] == "Hips" and len(r["source_chains"]) == 27 and r["source_feet"] == local_ai.SOMA_FEET
          and r["defaults_from"]["provider"] == "local_ai", f"retarget filled from the provider: pelvis Hips · {len(r['source_chains'])} SOMA chains (9 body + 18 hand) · feet")
    check(r["ops"] == "match_existing" and r["align_mode"] == "per_bone" and r["body_clearance"] == "resolve" and r["facing"]["mode"] == "converted",
          "retarget: match_existing · align per_bone · body_clearance resolve · facing converted by blender")
    lims = [lim["code"] for lim in cand["expected_limitations"]]
    check({"FINGERS_STATIC", "REVIEW_IS_SOURCE_SKELETON"} <= set(lims) and "TEXT_ENCODER_CPU" in cand["risks"],
          f"expected limitations {lims} · risk TEXT_ENCODER_CPU")
    # seed 없이 → 지금 골라 고정 (보이는 것이 실행되는 것)
    env = SERVICE.plan_motion_generation(request=base_request(generation={}, animation_name="AS_Vesper_Kimodo_SeedP5"))
    seeded = must(env, "plan seedless")
    pinned = step_of(seeded["candidates"][0], "generate")["inputs"]["seed"]
    check(isinstance(pinned, int) and any(d["code"] == "SEED_PINNED" for d in env["diagnostics"]), f"no seed → SEED_PINNED {pinned}")

    def excluded(req: dict) -> dict:
        p = must(SERVICE.plan_motion_generation(request=req), "plan reject")
        return next((e for e in p["excluded"] if e["provider"] == "local_ai"), {}) if not p["candidates"] else {}

    e = excluded(base_request(prompt=None, animation_name="AS_Vesper_Kimodo_NoPromptP5"))
    check(e.get("reason") == "MISSING_INPUT", f"no prompt → local_ai excluded {e.get('cause')} {e.get('reason')}")
    e = excluded(base_request(duration_seconds=12.0, animation_name="AS_Vesper_Kimodo_LongP5", review=None))
    check(e.get("reason") == "DURATION_OVER_MAX", f"12 s > 10 s → {e.get('reason')}")
    e = excluded(base_request(generation={"seed": SEED, "constraints": [{"type": "root_path", "points": [{"t": 7.0, "forward_cm": 100, "left_cm": 0}]}]},
                              animation_name="AS_Vesper_Kimodo_LateP5"))
    check(e.get("reason") == "CONSTRAINT_OUT_OF_RANGE", f"constraint at 7 s of a 6 s clip → {e.get('reason')}")
    # Phase 8-3 — 사전이 채워졌다(smooth · stance_width · foot_lock): 기대된 변화로 사전 밖 op 를 막는지 본다
    e = excluded(base_request(fix={"ops": [{"op": "teleport"}]}, animation_name="AS_Vesper_Kimodo_FixP5"))
    check(e.get("reason") == "UNSUPPORTED_FIX_OP", f"fix op outside the dictionary → {e.get('reason')}")
    outside = STATE_DIR / "outside.npz"
    env = SERVICE.plan_motion_generation(request=base_request(
        generation={"seed": SEED, "constraints": [{"type": "keep_pose", "npz": outside.as_posix(), "times": [0.0]}]}, animation_name="AS_Vesper_Kimodo_NpzP5"))
    check(not env["ok"] and env["error"]["code"] == "IMPORT_SOURCE_NOT_ALLOWED", "keep_pose NPZ outside ImportSourceRoots → IMPORT_SOURCE_NOT_ALLOWED")
    after_runs = sorted(p.name for p in local_dir.iterdir()) if local_dir.is_dir() else []
    check(after_runs == before_runs, "planning started no Kimodo run (LocalAI output folders unchanged)")
    check(dirty_count() == before and not uasset(f"{RUN}/x").parent.exists(), f"planning left no asset and the dirty count unchanged ({before})")
    STATE["plan"] = {"plan_id": plan["plan_id"], "order": plan["order"], "chain": cand["chain"], "excluded": [(e["provider"], e["cause"], e["reason"]) for e in plan["excluded"]],
                     "generate_inputs": {k: g[k] for k in ("model", "model_commit", "prompt", "duration_seconds", "frames", "fps", "seed", "samples", "steps", "postprocess")},
                     "convert_expected": exp, "review": review, "retarget": {k: r[k] for k in ("source_pelvis", "ops", "align_mode", "body_clearance")},
                     "risks": cand["risks"], "expected_limitations": lims, "seed_pinned": pinned}


def section_generate() -> None:
    print("== generate (criterion: prompt → Kimodo → Blender → Vesper AS_ + validate_animation)")
    req = base_request()
    plan, job, seconds = run_job(req, "generate")
    final = f"{RUN}/{req['animation_name']}"
    check(job["status"] == "SUCCEEDED" and [e["to"] for e in job["events"]] == ["QUEUED", "RUNNING", "SUCCEEDED"], f"job QUEUED → RUNNING → SUCCEEDED ({seconds}s)")
    if job["status"] != "SUCCEEDED":
        STATE["generate"] = {"job_id": job["job_id"], "status": job["status"], "error": job.get("error"), "seconds": seconds}
        return
    values = job["cursor"]["values"]
    gen = values["generated"]
    picked = gen["samples"][gen["pick"]]
    bvh_file = pathlib.Path(picked["bvh"])
    kroot = picked.get("root") or {}
    print(f"   Kimodo {gen['model']} · {gen['seconds']} · postprocess {gen['postprocess']} · root {kroot}")
    check(bvh_file.is_file() and pathlib.Path(picked["npz"]).is_file() and picked["frames"] == plan["candidates"][0]["steps"][0]["inputs"]["frames"],
          f"Kimodo wrote BVH + NPZ ({picked['frames']} frames): {bvh_file.as_posix()}")
    check((gen["model"] or {}).get("commit") == STATE.get("plan", {}).get("generate_inputs", {}).get("model_commit", (gen["model"] or {}).get("commit")),
          "report model commit = planned commit")
    rows = bvh_root_rows(bvh_file)
    k_yaw = rows[-1][4] - rows[0][4]
    check(kroot.get("root_travel_cm", 0) > 100, f"Kimodo root track travels {kroot.get('root_travel_cm')} cm (root wrapper no longer static)")
    check(150.0 <= abs(k_yaw) <= 210.0, f"Kimodo root heading turns {k_yaw:.1f}° (≈ ±180 — 'turns around')")
    conv = values["converted"]
    print(f"   Blender {conv['blender']}: {conv['bones']} bones · facing {conv['facing']} · lift {conv['ground_lift_cm']} cm · {conv['frames']} · {conv['seconds']}s")
    check(conv["bones"] == 78 and conv["facing"] == "+Y", "converted skeleton: 78 bones (Root wrapper + SOMA77) facing +Y")
    check(job["generated_assets"] == [final] and exists(final) and uasset(final).is_file(), f"{final} saved")
    assets = job_assets(job)
    src = must(editor("inspect_skeleton", skeleton=assets["source_skeleton"]), "inspect source")
    check(src["bone_count"] == 78 and src["root_bone"] == "Root", f"imported source skeleton {assets['source_skeleton']}: {src['bone_count']} bones, root {src['root_bone']}")
    # 프레임 렌더 비교
    review = job.get("review") or {}
    frames = [pathlib.Path(f["path"]) for f in review.get("frames") or []]
    sheet = pathlib.Path(review["sheet"]) if review.get("sheet") else None
    png = all(p.is_file() and p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" for p in frames + ([sheet] if sheet else []))
    check(len(frames) == 8 and sheet is not None and png, f"review: {len(frames)} frame PNGs (4 times × front/side) + sheet {sheet and sheet.as_posix()} "
          f"{(review.get('layout') or {}).get('size')}")
    # 손가락 안전망 · 관통 보정 · 내장 검증
    codes = [d["code"] for d in job["diagnostics"]]
    finger_diag = [c for c in codes if c.startswith("FINGER")]
    check(not finger_diag, f"no finger safety-net warning in the job diagnostics ({finger_diag})")
    clearance = values.get("body_clearance") or []
    arms = [(a["upper_arm"], a.get("corrected_frames_pct"), a.get("deg_max")) for item in clearance for a in item.get("arms", [])]
    before = {a["upper_arm"]: a["frames_over_penetration_pct"] for item in clearance for a in (item.get("before") or {}).get("arms", [])}
    after = {a["upper_arm"]: a["frames_over_penetration_pct"] for item in clearance for a in (item.get("after") or {}).get("arms", [])}
    print(f"   body clearance: modified {[i.get('modified') for i in clearance]} · corrected {arms} · penetration % {before} → {after}")
    check(bool(clearance) and all(v == 0 for v in after.values()) and "BODY_PENETRATION_REMAINS" not in codes,
          "retarget body_clearance resolve ran — no arm left penetrating (after = 0%)")
    check(job["validation"]["status"] in ("PASSED", "PASSED_WITH_WARNINGS") and "VALIDATED_WITH_SOURCE_PELVIS" in codes,
          f"built-in validation (revalidated with source pelvis Hips) {job['validation']['status']}")
    v = validate_result(final, assets)
    n = v["numeric"]
    fing = v.get("fingers") or {}
    body = v.get("body_clearance") or {}
    print(f"   validate vs source: {v['status']} · {n['frames']} frames @ {n['frame_rate']} · {n['length']}s · root travel {n['root_travel_cm']} cm · "
          f"displacement {n['root_displacement_cm']} cm · yaw {n['root_yaw_delta_deg']}° · relative {json.dumps(v.get('relative', {}), ensure_ascii=False)[:500]}")
    print(f"   fingers: unmapped {len(fing.get('unmapped') or [])} · order broken {[h.get('order_broken_pct') for h in fing.get('hands', [])]} · warnings {issue_codes(fing)}")
    print(f"   body clearance: {[(a['upper_arm'], a['frames_over_penetration_pct'], a['depth_max']) for a in body.get('arms', [])]} · warnings {issue_codes(body)}")
    check(v["status"] in ("PASSED", "PASSED_WITH_WARNINGS"), f"validate_animation {v['status']}")
    check(abs(n["frame_rate"] - 30) < 0.01 and abs(n["length"] - DURATION) < 1 / 30 + 1e-6, f"30 fps · length {n['length']}s = requested {DURATION}s")
    check(n["root_travel_cm"] > 100, f"Vesper root moves ({n['root_travel_cm']} cm)")
    check(150.0 <= abs(n["root_yaw_delta_deg"]) <= 210.0, f"Vesper root yaw turns {n['root_yaw_delta_deg']}° (≈ ±180)")
    check(not issue_codes(fing) and all((h.get("order_broken_pct") or 0) == 0 for h in fing.get("hands", [])), "fingers: no safety-net warning · finger order kept")
    check(not issue_codes(body), "body clearance: no BODY_PENETRATION on the saved result")
    lims = [lim["code"] for lim in job["limitations"]]
    check({"FINGERS_STATIC", "REVIEW_IS_SOURCE_SKELETON"} <= set(lims), f"job limitations {lims}")
    STATE["generate"] = {"job_id": job["job_id"], "asset": final, "seconds": seconds, "kimodo": {"model": gen["model"], "seconds": gen["seconds"],
                         "postprocess": gen["postprocess"], "root": kroot, "bvh": bvh_file.as_posix(), "heading_delta_deg": round(k_yaw, 2)},
                         "converted": conv, "assets": assets, "review": {"frames": [p.as_posix() for p in frames], "sheet": sheet and sheet.as_posix(),
                         "size": (review.get("layout") or {}).get("size"), "seconds": review.get("seconds")},
                         "body_clearance": {"arms": arms, "before": before, "after": after},
                         "validation_builtin": job["validation"]["status"], "limitations": lims, "diagnostic_codes": sorted(set(codes)),
                         "validate": {"status": v["status"], "numeric": {k: n.get(k) for k in ("frames", "frame_rate", "length", "root_travel_cm",
                                      "root_displacement_cm", "root_yaw_delta_deg", "max_deg_per_frame", "pelvis_height_cm")},
                                      "relative": v.get("relative"), "structural": v.get("structural"),
                                      "fingers": {"warnings": issue_codes(fing), "order_broken_pct": [h.get("order_broken_pct") for h in fing.get("hands", [])]},
                                      "body_clearance": [(a["upper_arm"], a["frames_over_penetration_pct"], a["depth_max"]) for a in body.get("arms", [])]}}


def section_constraint() -> None:
    print(f"== constraint root_path ({CONSTRAINT_POINT}) — the clip ends at t = {CONSTRAINT_T}s")
    req = base_request(animation_name="AS_Vesper_Kimodo_RootPathP5", prompt="A person walks forward and turns around.", duration_seconds=CONSTRAINT_T,
                       generation={"seed": SEED, "constraints": [{"type": "root_path", "points": [CONSTRAINT_POINT]}]}, review=None)
    plan, job, seconds = run_job(req, "constraint")
    spec = plan["candidates"][0]["steps"][0]["inputs"]["constraints"]
    end = int(round(CONSTRAINT_T * 30))
    item = spec[0]["items"][0] if spec and spec[0]["items"] else {}
    check(item.get("type") == "root2d" and item.get("frame_indices") == [end] and item.get("smooth_root_2d") == [[0.0, 4.0]]
          and item.get("global_root_heading") and abs(item["global_root_heading"][0][0] + 1) < 1e-9,
          f"plan pins Kimodo root2d at frame {end}: (left, forward) = (0, 4.0 m), heading (cos, sin) = {item.get('global_root_heading')}")
    check(job["status"] == "SUCCEEDED", f"constraint job {job['status']} ({seconds}s)")
    if job["status"] != "SUCCEEDED":
        STATE["constraint"] = {"job_id": job["job_id"], "status": job["status"], "error": job.get("error")}
        return
    values = job["cursor"]["values"]
    picked = values["generated"]["samples"][values["generated"]["pick"]]
    rows = bvh_root_rows(pathlib.Path(picked["bvh"]))
    first, last = rows[0], rows[end]
    k_fwd, k_left, k_yaw = last[2] - first[2], last[0] - first[0], last[4] - first[4]
    print(f"   Kimodo root at frame {end}: forward {last[2]:.1f} · left {last[0]:.1f} cm (from frame 0: {k_fwd:.1f} · {k_left:.1f}) · heading {last[4]:.1f}° "
          f"(Δ {k_yaw:.1f}) · report {picked.get('root')}")
    check(abs(last[2] - 400.0) <= 30.0 and abs(last[0]) <= 30.0, f"Kimodo root reaches the point: forward {last[2]:.1f} cm (400 ± 30) · left {last[0]:.1f} cm (0 ± 30)")
    check(abs(abs(last[4]) - 180.0) <= 20.0, f"Kimodo heading at {CONSTRAINT_T}s = {last[4]:.1f}° (|·| = 180 ± 20 — cos/sin of 180° does not fix the turn side)")
    final = job["generated_assets"][0]
    assets = job_assets(job)
    v = validate_result(final, assets)
    n = v["numeric"]
    prof = n.get("profile") or {}
    pos = (prof.get("position_cm") or {}).get("root") or []
    times = prof.get("times") or []
    # profile 위치는 구간 끝 시각(프레임 1 부터)이라 프레임 1 → 끝 이동으로 비교한다(Kimodo 도 같은 프레임). 앞 = UE +Y, 왼쪽 = UE +X
    end_pos = pos[-1] if pos else [None, None, None]
    src_v = must(editor("validate_animation", assets=[assets["source_anim"]], skeleton=assets["source_skeleton"], pelvis=local_ai.SOMA_PELVIS,
                        profile_bones=["Root"], profile_positions=True), "validate source")["assets"][0]
    sp = ((src_v["numeric"].get("profile") or {}).get("position_cm") or {}).get("Root") or []
    sp_end = sp[-1] if sp else [None, None, None]
    scale = (n.get("pelvis_height_cm") or 0) / (src_v["numeric"].get("pelvis_height_cm") or 1)
    k_fwd1, k_left1 = rows[end][2] - rows[1][2], rows[end][0] - rows[1][0]
    fwd, left = (end_pos[1] - pos[0][1], end_pos[0] - pos[0][0]) if pos else (None, None)
    ratio = fwd / k_fwd1 if pos and abs(k_fwd1) > 1e-6 else None
    print(f"   Vesper root at {times[-1] if times else '?'}s: {end_pos} (forward = +Y, left = +X) · frame 1 → end {fwd} · {left} cm vs Kimodo {k_fwd1:.1f} · "
          f"{k_left1:.1f} (ratio {ratio}) · displacement {n['root_displacement_cm']} · yaw Δ {n['root_yaw_delta_deg']}° · imported source Root {sp_end} · "
          f"pelvis height ratio {scale:.3f}")
    check(bool(pos) and abs(times[-1] - CONSTRAINT_T) < 1e-3 and abs(fwd - k_fwd1) <= max(25.0, 0.15 * abs(k_fwd1)) and abs(left - k_left1) <= 25.0,
          f"Vesper root follows the Kimodo root: forward {fwd} vs {k_fwd1:.1f} · left {left} vs {k_left1:.1f} cm (frame 1 → {end})")
    check(abs(abs(n["root_yaw_delta_deg"]) - abs(k_yaw)) <= 5.0, f"Vesper root yaw Δ {n['root_yaw_delta_deg']}° = Kimodo |{k_yaw:.1f}|° ± 5")
    turn = "left" if k_yaw > 0 else "right"
    check(v["status"] in ("PASSED", "PASSED_WITH_WARNINGS"), f"validate_animation {v['status']} (Kimodo turned {turn})")
    STATE["constraint"] = {"job_id": job["job_id"], "asset": final, "seconds": seconds, "point": CONSTRAINT_POINT, "kimodo_spec": item,
                           "kimodo_root_end": {"forward_cm": round(last[2], 2), "left_cm": round(last[0], 2), "heading_deg": round(last[4], 2)},
                           "kimodo_root_delta": {"forward_cm": round(k_fwd, 2), "left_cm": round(k_left, 2), "yaw_deg": round(k_yaw, 2), "turn": turn},
                           "vesper_root_end": end_pos, "vesper_frame1_to_end_cm": {"forward": fwd, "left": left}, "travel_ratio": ratio and round(ratio, 4),
                           "vesper_displacement_cm": n["root_displacement_cm"], "vesper_yaw_delta_deg": n["root_yaw_delta_deg"],
                           "source_root_end": sp_end, "pelvis_height_ratio": round(scale, 4), "validate": v["status"]}


def section_cancel() -> None:
    print("== cancel stops the real Kimodo process")
    req = base_request(animation_name="AS_Vesper_Kimodo_CancelP5", review=None)
    plan = must(SERVICE.plan_motion_generation(request=req), "plan cancel")
    job = must(SERVICE.generate_motion(plan_id=plan["plan_id"]), "generate cancel")
    handle = job["pending"]["handle"]
    pid = handle["pid"]
    alive = pid_alive(pid)
    time.sleep(2.0)  # torch import 중 — 실제로 떠 있는 프로세스를 멈춘다
    job = must(SERVICE.cancel_generation(job_id=job["job_id"]), "cancel")
    time.sleep(1.0)
    print(f"   pid {pid} alive before cancel {alive} · cancel_effect {job.get('cancel_effect')}")
    check(alive and job["status"] == "CANCELLED" and (job.get("cancel_effect") or {}).get("stopped") is True, "CANCELLED and the Kimodo process was stopped")
    check(not pid_alive(pid), f"pid {pid} is gone")
    out_dir = pathlib.Path(handle["dir"])
    check(not pathlib.Path(handle["report"]).exists() and not list(out_dir.glob("*.bvh")), "no report · no BVH written after the stop")
    check(SERVICE.get_generation_status(job_id=job["job_id"])["result"]["status"] == "CANCELLED", "status stays CANCELLED (no further poll)")
    STATE["cancel"] = {"job_id": job["job_id"], "pid": pid, "effect": job.get("cancel_effect")}


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


SECTIONS = {"hashes": section_hashes, "state": section_state, "plan": section_plan, "generate": section_generate, "constraint": section_constraint,
            "cancel": section_cancel, "dirty": section_dirty}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(SECTIONS), help="comma separated: " + ",".join(SECTIONS))
    args = ap.parse_args()
    t0 = time.time()
    for name in args.only.split(","):
        SECTIONS[name.strip()]()
    STATE["seconds"] = round(time.time() - t0, 1)
    out = ROOT / "Tools" / "mcp" / "anim_gen_phase5_state.json"
    out.write_text(json.dumps(STATE, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"state -> {out.as_posix()}")
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print("  - " + f)
    print("PASS" if not FAILS else "FAIL")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
