"""key_pose 단계 (Phase 9-3 · U3-a/b — 지침서 §14 '9-3'): 생성 앞, 대상(Vesper) 애셋의 키 자세 → Kimodo 제약 파일.

계획(local_ai.plan_generate 가 부른다): 원천 애셋(대상 스켈레톤 · 길이 · fps → 원천 프레임), Kimodo 설치본의 표준 T 포즈 BVH(SHA-256 고정),
blender 실행 파일 · target_mesh 를 확인하고 단계를 고정한다 — 애셋을 만들지 않는다.

실행(retarget 파이프 — RetargetPipe.run 이 넘긴다, 사용자 결정 ① 'Job 마다 Work 에'):
  T 포즈 BVH(2 프레임으로) → Blender(bvh_to_fbx — 생성 Job 과 같은 변환 · 정면 규칙, 동기) → 기준 포즈 FBX 임포트(<work>/KeyPose/Import)
  → IK Rig 2(SOMA 수동 체인 · 대상 자동 — 생성 리타깃과 같은 규칙) → 역리타기터(대상 → SOMA, 요청 ops · align_mode)
  → 원천마다 retarget_animations → apply_animation_edits(hold_pose 한 프레임 — profile 은 프레임 0 을 내지 않는다, 길면 trim 먼저)
  → validate_animation profile(SOMA 78 본 컴포넌트 회전 · 위치) → anim_gen/key_pose.convert → <ImportSourceRoots>/LocalAI/<job>/A<n>/KeyPose/key_pose.json.
배치(origin · pass1)는 Kimodo 실행 스크립트가 한다(pass1 은 1차 생성 결과가 있어야 한다).
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import time

from .. import bvh, key_pose as kp
from ..editor import EditorCallError, asset_name, package_path
from ..envelope import diag, limitation
from ..fallback import from_editor_error
from ..soma import SOMA_CHAINS, SOMA_PELVIS
from ..weapon import quat_from_rotator
from .base import PlanBlocked, PlanContext, RunContext, StepFailed, StepResult
from .blender import PACKAGE_DIR, PROXY_MESH, SCRIPT, BlenderProvider
from .subprocess_step import child_env, file_sha256, import_roots, launch, read_json

TOOL = ("blender(SOMA T pose) → import_animation_file → create_ik_rig ×2 → create_ik_retargeter(target → SOMA) → retarget_animations → "
        "apply_animation_edits(hold_pose) → validate_animation(profile_rotations · positions)")
FPS_FALLBACK = 30.0


def _source_info(editor, asset: str, where: str) -> dict:
    try:
        item = editor.require("validate_animation", assets=[asset], checks=["numeric"])["assets"][0]
    except EditorCallError as err:
        raise PlanBlocked("UNSUPPORTED_REQUEST", err.code if err.code == "ASSET_NOT_FOUND" else "KEY_POSE_SOURCE_UNREADABLE",
                          f"{where}.asset {asset}: {err}") from None
    n = item.get("numeric") or {}
    return {"skeleton": package_path(item.get("skeleton")), "frame_rate": float(n.get("frame_rate") or FPS_FALLBACK),
            "frames": int(n.get("frames") or round(float(n.get("length") or 0.0) * float(n.get("frame_rate") or FPS_FALLBACK)) + 1),
            "length": n.get("length")}


def source_frames(spec: dict, info: dict, where: str) -> list[int]:
    fps = info["frame_rate"]
    out = [int(round(t * fps)) for t in spec["times"]]
    late = [t for t, f in zip(spec["times"], out) if f >= info["frames"]]
    if late:
        raise kp.KeyPoseError("CONSTRAINT_OUT_OF_RANGE", f"{where}.times {late} are past the end of {asset_name(spec['asset'])} "
                              f"({info['frames']} frames at {fps:g} fps)", frames=info["frames"])
    return out


def plan(request: dict, specs: list[dict], pctx: PlanContext, kimodo_python: pathlib.Path | None) -> tuple[dict, list[str], list[dict]]:
    """key_pose 명세(constraints.convert) → (key_pose 단계, 위험, 예상 한계). 막히면 PlanBlocked(이 후보를 뺀다)."""
    if not request["target_mesh"]:
        raise PlanBlocked("UNSUPPORTED_REQUEST", "MISSING_INPUT", "generation.constraints key_pose retargets the target asset back to SOMA — "
                          "target_mesh is required", missing=["target_mesh"])
    seen: dict[int, list[tuple[str, str]]] = {}
    for spec in specs:
        for f in spec["frame_indices"]:
            # 같은 프레임의 다른 부위(손 + 발)는 된다 — 전신은 모든 부위와, 같은 부위는 서로 겹친다
            clash = next((src for part, src in seen.get(f, []) if "full" in (part, spec["part"]) or part == spec["part"]), None)
            if clash:
                raise PlanBlocked("UNSUPPORTED_REQUEST", "DUPLICATE_FRAME", f"{spec['source']} and {clash} both pin {spec['part']} at generated frame {f}",
                                  frame=f)
            seen.setdefault(f, []).append((spec["part"], spec["source"]))
    tpose = kp.tpose_path(kimodo_python)
    if tpose is None:
        raise PlanBlocked("PROVIDER_UNAVAILABLE", "KEY_POSE_TPOSE_MISSING", f"the Kimodo package (from {kimodo_python}) has no "
                          f"{'/'.join(kp.TPOSE_FILE)} — the SOMA skeleton for the reverse retarget is built from it")
    exe = BlenderProvider.executable(pctx.policy)
    if pctx.policy is not None and not (exe and pathlib.Path(exe).is_file()):
        raise PlanBlocked("PROVIDER_UNAVAILABLE", "DEPENDS_ON_BLENDER", f"key_pose converts the SOMA T pose with Blender — blender_executable not found: {exe}")
    risks, items = [], []
    target = package_path(request["target_skeleton"])
    cache: dict[str, dict] = {}
    for spec in specs:
        item = {k: spec[k] for k in ("source", "asset", "part", "type", "times", "frame_indices", "placement")}
        if pctx.editor_ok:
            info = cache.get(spec["asset"]) or _source_info(pctx.editor, spec["asset"], spec["source"])
            cache[spec["asset"]] = info
            if info["skeleton"] and info["skeleton"] != target:
                raise PlanBlocked("UNSUPPORTED_REQUEST", "SAMPLE_SKELETON_MISMATCH", f"{spec['source']}.asset is on {info['skeleton']} — key poses come "
                                  f"from the target skeleton {target} (retarget the source onto it first)", skeleton=info["skeleton"])
            try:
                item["source_frames"] = source_frames(spec, info, spec["source"])
            except kp.KeyPoseError as err:
                raise PlanBlocked("UNSUPPORTED_REQUEST", err.code, err.message, **err.details) from None
            item.update(source_fps=info["frame_rate"], source_total_frames=info["frames"])
        items.append(item)
    if not pctx.editor_ok:
        risks.append("KEY_POSE_SOURCES_AT_RUN")
    rt = request["retarget"]
    step = {"step": "key_pose", "provider": "retarget", "tool": TOOL,
            "inputs": {"items": items, "tpose": {"path": tpose.as_posix(), "sha256": file_sha256(tpose)}, "target_mesh": request["target_mesh"],
                       "existing_target_rig": rt.get("existing_target_rig"), "source_pelvis": SOMA_PELVIS,
                       "source_chains": rt.get("source_chains") or SOMA_CHAINS, "ops": rt.get("ops", "match_existing"),
                       "align_mode": rt.get("align_mode", "per_bone"), "work": "<work>/KeyPose",
                       "output": "<ImportSourceRoots[0]>/LocalAI/<job>/A<n>/KeyPose/key_pose.json"}}
    placements = {i["source"]: i["placement"] for i in items}
    lims = [limitation("KEY_POSE_RETARGETED", "키 포즈는 대상 애셋 자세를 SOMA 로 되돌린(역리타깃) 관절 회전이다 — 위치는 SOMA 체형(팔 55.9 vs 대상 47.7 cm)"
                       "이라 대상과 다르고, 손가락은 Kimodo 30 관절 밖(고정 손 포즈)이다. 리타깃 왕복의 고정 편향(척추 Interpolated ≈ 3° · 팔 ≈ 1.7°, "
                       "E0)이 남는다", "provider", items=len(items)),
            limitation("KEY_POSE_PLACED", "Kimodo 제약은 그 프레임의 바닥 루트 · 방향까지 묶는다 — 항목마다 첫 키를 " + ", ".join(
                f"{src} {'원점 · 정면 +Z' if p == 'origin' else '1차(같은 seed · 키 없이)의 그 프레임 바닥 루트 · 방향'}" for src, p in placements.items())
                       + " 에 두고 키 사이 상대 궤적은 원천 그대로(강체 한 번)", "provider", placements=placements),
            limitation("KEY_POSE_SMOOTHED", "키 조건이 키 둘레를 진동시킨다(8-1 수정안 A 와 같은 원인 — 9-3 실측 성긴 전신 키에서 손 속도 톱니) → 최종 출력에 σ 1 프레임 "
                       "시간 스무딩: 키 프레임 자세가 제약에서 조금 벗어난다(실측 p50 0.2 ~ 1.0 · 최대 0.7 ~ 4.5 cm), 손 정점 몇 % 낮아진다", "provider")]
    return step, risks + ["KEY_POSE_RESOLVED_AT_RUN"], lims


# ---- 실행 ----
def run_blender(ctx: RunContext, bvh_path: pathlib.Path, out_dir: pathlib.Path) -> pathlib.Path:
    """T 포즈 BVH → 기준 포즈 FBX(생성 Job 의 convert 단계와 같은 bvh_to_fbx 인자 · 정면 규칙) — 동기(2 프레임, 수 초). 테스트는 이 함수를 바꾼다."""
    exe = BlenderProvider.executable(ctx.policy)
    if not exe or not pathlib.Path(exe).is_file():
        raise StepFailed("PROVIDER_UNAVAILABLE", "NOT_INSTALLED", f"blender_executable not found: {exe}")
    try:
        info = bvh.read(bvh_path)
        segs = bvh.rest_segments(info, "-Z", "Y")
        unit = bvh.resolve_unit("cm", bvh.height(segs))
    except bvh.BvhError as err:
        raise StepFailed("UNSUPPORTED_REQUEST", "BAD_TPOSE", f"{bvh_path.name}: {err.message}") from None
    facing = BlenderProvider.facing("auto", segs, ctx.request["target_skeleton"], ctx.editor)
    paths = {name: out_dir / f for name, f in (("fbx", "SOMA_TPose.fbx"), ("rest_fbx", "SOMA_TPose_Rest.fbx"), ("report", "blender_report.json"),
                                                ("log", "blender.log"), ("args", "blender_args.json"))}
    paths["report"].unlink(missing_ok=True)
    args = {"bvh": bvh_path.as_posix(), "fbx": paths["fbx"].as_posix(), "rest_fbx": paths["rest_fbx"].as_posix(), "report": paths["report"].as_posix(),
            "cm_per_unit": unit["cm_per_unit"], "axis_forward": "-Z", "axis_up": "Y", "rotate_z_deg": facing["rotate_z_deg"], "first": 0, "last": 1,
            "fps": info.fps, "proxy_mesh": PROXY_MESH, "fix": [], "review": None, "package_dir": PACKAGE_DIR.as_posix()}
    paths["args"].write_text(json.dumps(args, ensure_ascii=False, indent=1), encoding="utf-8")
    cmd = [exe, "-b", "--factory-startup", "--python-exit-code", "3", "-P", str(SCRIPT), "--", str(paths["args"])]
    kwargs = {"stdin": subprocess.DEVNULL, "stderr": subprocess.STDOUT, "cwd": str(out_dir), "env": child_env()}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    timeout = BlenderProvider.timeout_s(ctx.policy)
    with paths["log"].open("wb") as log:
        try:
            proc = launch(cmd, stdout=log, **kwargs)
        except OSError as exc:
            raise StepFailed("PROVIDER_UNAVAILABLE", "LAUNCH_FAILED", f"could not start Blender: {exc}") from None
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise StepFailed("GENERATION_FAILED", "TIMEOUT", f"Blender (SOMA T pose) ran over {timeout:.0f}s and was stopped") from None
    report = read_json(paths["report"].as_posix())
    if not report or not report.get("ok") or not paths["rest_fbx"].is_file():
        error = (report or {}).get("error") or {"code": f"BLENDER_EXIT_{code}", "message": "no report"}
        raise StepFailed("GENERATION_FAILED", error.get("code"), f"bvh_to_fbx (SOMA T pose): {error.get('message')} (log: {paths['log'].as_posix()})")
    return paths["rest_fbx"]


def _write_json(path: pathlib.Path, data: dict) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def run(ctx: RunContext) -> StepResult:
    editor, inputs = ctx.editor, ctx.step["inputs"]
    t0 = time.time()
    settings = editor.status()
    if settings is None:
        raise StepFailed("PROVIDER_UNAVAILABLE", "EDITOR", "Editor unreachable — key_pose retargets in the editor", fatal=True)
    tpose = pathlib.Path(inputs["tpose"]["path"])
    if not tpose.is_file() or file_sha256(tpose) != inputs["tpose"]["sha256"]:
        raise StepFailed("UNSUPPORTED_REQUEST", "FILE_CHANGED", f"{tpose.as_posix()} changed after planning — plan again", fatal=True)
    out_dir = import_roots(settings)[0] / "LocalAI" / ctx.job_id / f"A{ctx.attempt}" / "KeyPose"
    out_dir.mkdir(parents=True, exist_ok=True)
    bvh_path = out_dir / "SOMA_TPose.bvh"
    try:
        bvh_path.write_text(kp.two_frame_bvh(tpose.read_text(encoding="utf-8")), encoding="utf-8")
    except kp.KeyPoseError as err:
        raise StepFailed("UNSUPPORTED_REQUEST", err.code, err.message, fatal=True) from None
    rest_fbx = run_blender(ctx, bvh_path, out_dir)
    t_blender = time.time()
    work = f"{ctx.work_path}/KeyPose"
    target_mesh = inputs["target_mesh"]
    created: list[str] = []
    diagnostics: list[dict] = []
    items_out, json_items, retargeted = [], [], {}
    try:
        imp = editor.require("import_animation_file", file=rest_fbx.as_posix(), dest_path=f"{work}/Import", save=ctx.save)
        created += [package_path(p) for p in imp.get("imported", [])]
        soma_mesh, soma_skel = package_path(imp.get("mesh")), package_path(imp.get("skeleton"))
        r = editor.require("create_ik_rig", skeletal_mesh=soma_mesh, asset_path=f"{work}/IK_Soma", mode="manual", pelvis=inputs["source_pelvis"],
                           chains=inputs["source_chains"], save=ctx.save)
        soma_rig = package_path(r["asset_path"])
        created.append(soma_rig)
        target_rig = inputs.get("existing_target_rig")
        if not target_rig:
            r = editor.require("create_ik_rig", skeletal_mesh=target_mesh, asset_path=f"{work}/IK_Target", save=ctx.save)
            target_rig = package_path(r["asset_path"])
            created.append(target_rig)
        r = editor.require("create_ik_retargeter", source_rig=target_rig, target_rig=soma_rig, source_mesh=target_mesh, target_mesh=soma_mesh,
                           asset_path=f"{work}/RTG_KeyPose", ops=inputs["ops"], align_mode=inputs["align_mode"], save=ctx.save)
        retargeter = package_path(r["asset_path"])
        created.append(retargeter)
        info = editor.require("inspect_skeleton", skeleton=soma_skel, details=True)
        bones = [b["name"] for b in info.get("bones") or []]
        parents = {b["name"]: b.get("parent") for b in info.get("bones") or []}
        ref = {b["name"]: quat_from_rotator(b["ref_component"]["r"]) for b in info.get("bones") or [] if (b.get("ref_component") or {}).get("r")}
        missing = [b for b in (kp.HIPS, kp.LEFT_HIP, kp.RIGHT_HIP) if b not in ref]
        if missing:
            raise StepFailed("RETARGET_FAILED", "KEY_POSE_JOINTS_MISSING", f"the SOMA skeleton {soma_skel} has no reference pose for {missing}", created=created)
        target = package_path(ctx.request["target_skeleton"])
        for k, item in enumerate(inputs["items"]):
            asset = item["asset"]
            src = _source_info_run(editor, asset, item["source"])
            if src["skeleton"] and src["skeleton"] != target:
                raise StepFailed("UNSUPPORTED_REQUEST", "SAMPLE_SKELETON_MISMATCH", f"{item['source']}.asset is on {src['skeleton']}, not {target}",
                                 created=created)
            try:
                frames = item.get("source_frames") or source_frames(item, src, item["source"])
            except kp.KeyPoseError as err:
                raise StepFailed("UNSUPPORTED_REQUEST", err.code, err.message, created=created) from None
            if asset not in retargeted:
                res = editor.require("retarget_animations", retargeter=retargeter, assets=[asset], source_mesh=target_mesh, target_mesh=soma_mesh,
                                     output_path=work, name_rule={"prefix": f"KP{len(retargeted)}_"}, include_referenced=False, validate=False,
                                     fingers=False, save=ctx.save)
                soma_anim = package_path(((res.get("generated") or [{}])[0]).get("asset"))
                if not soma_anim:
                    raise StepFailed("RETARGET_FAILED", "NOTHING_GENERATED", f"reverse retarget of {asset} generated nothing", created=created)
                created.append(soma_anim)
                retargeted[asset] = {"soma": soma_anim, "frames": set(), "items": []}
            retargeted[asset]["frames"] |= set(frames)
            retargeted[asset]["items"].append((k, frames))
            retargeted[asset]["src"] = src
        for asset, rec in retargeted.items():
            ops, first = kp.edit_ops(sorted(rec["frames"]), rec["src"]["frame_rate"], rec["src"]["frames"])
            held = f"{rec['soma']}_Hold"
            editor.require("apply_animation_edits", source=rec["soma"], asset_path=held, operations=ops, validate=False, save=ctx.save)
            created.append(held)
            prof_item = editor.require("validate_animation", assets=[held], checks=["numeric"], profile_bones=bones, profile_positions=True,
                                       profile_rotations=True)["assets"][0]
            prof = (prof_item.get("numeric") or {}).get("profile") or {}
            if prof.get("frames_per_sample", 1) != 1:
                raise StepFailed("RETARGET_FAILED", "KEY_POSE_PROFILE_BUCKETED", f"{held}: profile grouped {prof.get('frames_per_sample')} frames per sample",
                                 created=created)
            rot, pos = prof.get("rotations") or {}, prof.get("position_cm") or {}
            rec.update(held=held, first=first, ops=ops)
            # 원천 엉덩 궤적(표본 i = 원천 프레임 first + i) — 러너가 Kimodo 의 바닥 루트 매끈화(get_smooth_root_pos)로 키의 smooth_root_2d 를 만든다
            track = {"first": first, "m": [[round(x, 6) for x in kp.ue_to_kimodo_point(p)] for p in pos.get(kp.HIPS) or []]}
            for k, frames in rec["items"]:
                item = inputs["items"][k]
                keys = []
                for f_gen, f_src, t_src in zip(item["frame_indices"], frames, item["times"]):
                    i = f_src - first
                    if not all(i < len(rot.get(b) or []) for b in (kp.HIPS, kp.LEFT_HIP, kp.RIGHT_HIP)):
                        raise StepFailed("RETARGET_FAILED", "KEY_POSE_PROFILE_SHORT", f"{held}: no profile sample for source frame {f_src}", created=created)
                    try:
                        c = kp.convert({b: rot[b][i] for b in rot}, {b: pos[b][i] for b in pos}, ref, parents)
                    except kp.KeyPoseError as err:
                        raise StepFailed("RETARGET_FAILED", err.code, err.message, created=created) from None
                    keys.append({"frame": f_gen, "source_frame": f_src, "source_s": t_src, **c})
                json_items.append({"source": item["source"], "asset": asset, "part": item["part"], "type": item["type"], "placement": item["placement"],
                                   "keys": keys, "hips_track": track})
                items_out.append({"source": item["source"], "asset": asset, "soma_asset": rec["soma"], "held_asset": held, "part": item["part"],
                                  "placement": item["placement"], "edit_ops": ops,
                                  "keys": [{"frame": key["frame"], "source_frame": key["source_frame"], "source_s": key["source_s"],
                                            "heading_deg": round(key["heading_rad"] * 57.29577951308232, 2), "hips_m": key["hips_m"]} for key in keys]})
    except EditorCallError as err:
        raise from_editor_error("key_pose", err, created=created)
    path = out_dir / "key_pose.json"
    _write_json(path, {"version": 1, "fps": FPS_FALLBACK, "skeleton": soma_skel, "retargeter": retargeter,
                       "joints": [b for b in bones if b != kp.ROOT_WRAPPER], "parents": parents, "items": json_items})
    diagnostics.append(diag("info", "KEY_POSE_CONVERTED", f"{sum(len(i['keys']) for i in json_items)} key(s) from {len(retargeted)} asset(s) reversed "
                            f"onto SOMA ({retargeter}) → {path.as_posix()}", file=path.as_posix()))
    record = {"file": path.as_posix(), "sha256": file_sha256(path), "skeleton": soma_skel, "mesh": soma_mesh, "retargeter": retargeter,
              "rigs": {"soma": soma_rig, "target": target_rig}, "items": items_out,
              "seconds": {"blender": round(t_blender - t0, 2), "total": round(time.time() - t0, 2)}}
    return StepResult(values={"key_pose": record}, created=created, diagnostics=diagnostics)


def _source_info_run(editor, asset: str, where: str) -> dict:
    try:
        return _source_info(editor, asset, where)
    except PlanBlocked as blocked:
        raise StepFailed(blocked.cause, blocked.reason, blocked.message) from None
