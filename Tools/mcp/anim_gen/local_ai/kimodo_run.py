"""Kimodo 텍스트 → 모션 생성 — anim-gen-mcp local_ai Provider 가 Kimodo 전용 venv 의 python 으로 띄운다 (지침서 §14 Phase 5).

    <Kimodo venv>/Scripts/python.exe -I kimodo_run.py <args.json>

서버가 import 하지 않는다(torch · kimodo 는 이 venv 에만 있다). 프롬프트 · 프레임 수 · seed · 제약은 Provider 가 정해 args.json 에
넣고, 여기서는 적용만 한다. 결과는 샘플마다 NPZ + BVH(표준 T 포즈 SOMA77 · cm · 루트 트랙)와 report.json(임시 파일 → os.replace) —
실패해도 쓴다. 종료 코드 0 = 성공, 2 = 알려진 실패(report 에 코드), 3 = 잡지 못한 예외.

설정 근거(Phase 5 스파이크):
- 실행은 오프라인(HF_HUB_OFFLINE · LOCAL_CACHE) · 텍스트 인코더는 CPU(TEXT_ENCODER_DEVICE) — 환경 변수는 Provider 가 준다.
- BVH 기본 기준 포즈(BONES-SEED)는 회전 0 이 서 있는 자세가 아니라 anim_gen/bvh.py 의 단위 · 정면 측정이 틀린다 → 표준 T 포즈.
- Root 래퍼가 원점에 고정이라 리타깃 루트 모션이 0 이다 → root_track 이 모델의 바닥 궤적 · 방향을 Root 에 넣는다.
"""
import json
import os
import pathlib
import sys
import time
import traceback


class RunError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def write_json(path, data):
    path = pathlib.Path(path)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def model_commit(repo):
    """오프라인 캐시의 refs/main — 어떤 체크포인트로 만들었는지 report 에 남긴다."""
    cache = os.environ.get("HF_HUB_CACHE")
    ref = pathlib.Path(cache or "") / ("models--" + repo.replace("/", "--")) / "refs" / "main"
    try:
        return ref.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def build_constraints(specs, skeleton, frames):
    """Provider 명세 → Kimodo 제약 dict 목록 → load_constraints_lst (SOMA 77 ↔ 30 변환은 Kimodo 로더가 한다)."""
    import numpy as np
    import torch
    from kimodo.constraints import load_constraints_lst
    from kimodo.geometry import matrix_to_axis_angle

    items = []
    for spec in specs:
        if spec["kind"] == "kimodo":
            items += spec["items"]
        elif spec["kind"] == "raw":
            items += json.loads(pathlib.Path(spec["path"]).read_text(encoding="utf-8"))
        elif spec["kind"] == "keep_pose":
            data = np.load(spec["npz"])
            for key in ("local_rot_mats", "root_positions", "smooth_root_pos"):
                if key not in data.files:
                    raise RunError("BAD_CONSTRAINT", f"{spec['source']}: {spec['npz']} has no '{key}' — not a Kimodo NPZ")
            available = data["local_rot_mats"].shape[0]
            idx = spec["frame_indices"]
            if max(idx) >= available:
                raise RunError("CONSTRAINT_OUT_OF_RANGE", f"{spec['source']}: frame {max(idx)} is past the {available} frames of {spec['npz']}")
            rots = torch.from_numpy(data["local_rot_mats"][idx].astype("float32"))
            items.append({"type": spec["type"], "frame_indices": idx, "local_joints_rot": matrix_to_axis_angle(rots).tolist(),
                          "root_positions": data["root_positions"][idx].tolist(), "smooth_root_2d": data["smooth_root_pos"][idx][:, [0, 2]].tolist()})
        else:
            raise RunError("BAD_CONSTRAINT", f"unknown constraint kind {spec['kind']!r}")
    for item in items:
        if max(item["frame_indices"]) >= frames:
            raise RunError("CONSTRAINT_OUT_OF_RANGE", f"a {item['type']} constraint uses frame {max(item['frame_indices'])} of {frames}")
    return load_constraints_lst(items, skeleton) if items else [], len(items)


def run(args, report):
    sys.path.insert(0, args["package_dir"])
    from anim_gen.local_ai import root_track

    t0 = time.time()
    import torch
    from kimodo import load_model
    from kimodo.exports.bvh import motion_to_bvh
    from kimodo.exports.motion_io import save_kimodo_npz
    from kimodo.skeleton import SOMASkeleton30, global_rots_to_local_rots
    from kimodo.tools import seed_everything

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    report["device"] = {"name": device, "gpu": torch.cuda.get_device_name(0) if device != "cpu" else None, "torch": torch.__version__}
    if device == "cpu":
        report["warnings"].append({"code": "NO_CUDA", "message": "CUDA is not available — generation runs on the CPU (slow)"})
    postprocess = bool(args["postprocess"])
    if postprocess:
        try:
            import motion_correction  # noqa: F401 — Kimodo 후처리(발 미끄러짐)가 쓰는 C++ 확장
        except ImportError as exc:
            raise RunError("POSTPROCESS_UNAVAILABLE", f"motion_correction is not importable ({exc}) — plan with generation.postprocess off") from None
    t1 = time.time()
    model, resolved = load_model(args["model"], device=device, default_family="Kimodo", return_resolved_name=True)
    report["model"] = {"name": resolved, "repo": args["repo"], "commit": model_commit(args["repo"]), "fps": float(model.fps)}
    if abs(float(model.fps) - args["fps"]) > 1e-6:
        raise RunError("FPS_MISMATCH", f"model fps {model.fps} != planned {args['fps']}")
    t2 = time.time()
    constraint_lst, n_constraints = build_constraints(args["constraints"], model.skeleton, args["frames"])
    report["constraints"] = n_constraints
    seed_everything(args["seed"])
    output = model([args["prompt"]], [args["frames"]], constraint_lst=constraint_lst, num_denoising_steps=args["steps"],
                   num_samples=args["samples"], multi_prompt=True, num_transition_frames=5, post_processing=postprocess, return_numpy=True)
    t3 = time.time()

    skeleton = model.skeleton
    if isinstance(skeleton, SOMASkeleton30):
        skeleton = skeleton.somaskel77.to(device)  # 출력은 모델 안에서 이미 77 관절로 바뀌었다
    out_dir = pathlib.Path(args["out_dir"])
    n = int(output["posed_joints"].shape[0])
    for i in range(n):
        stem = out_dir / f"{args['stem']}_{i:02d}"
        single = {k: (v[i] if hasattr(v, "shape") and len(v.shape) > 0 and v.shape[0] == n else v) for k, v in output.items()}
        save_kimodo_npz(str(stem.with_suffix(".npz")), single)
        joints_pos = torch.from_numpy(output["posed_joints"][i]).to(device)
        local = global_rots_to_local_rots(torch.from_numpy(output["global_rot_mats"][i]).to(device), skeleton)
        text = motion_to_bvh(local, joints_pos[:, skeleton.root_idx, :], skeleton=skeleton, fps=model.fps, standard_tpose=True)
        stats = None
        if args["root_track"]:
            smooth = output["smooth_root_pos"][i]
            xz = [(float(p[0]) * 100.0, float(p[2]) * 100.0) for p in smooth]
            try:
                text, stats = root_track.apply_root_track(text, xz, root_track.heading_deg(output["global_root_heading"][i].tolist()))
            except root_track.RootTrackError as err:
                raise RunError(err.code, f"root track: {err.message}") from None
        stem.with_suffix(".bvh").write_text(text, encoding="utf-8")
        report["samples"].append({"index": i, "npz": stem.with_suffix(".npz").as_posix(), "bvh": stem.with_suffix(".bvh").as_posix(),
                                  "frames": int(output["posed_joints"].shape[1]), "root": stats})
    report["postprocess"] = {"requested": postprocess, "applied": postprocess}
    report["seconds"] = {"import": round(t1 - t0, 2), "load": round(t2 - t1, 2), "generate": round(t3 - t2, 2), "export": round(time.time() - t3, 2),
                         "total": round(time.time() - t0, 2)}


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    args = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    report = {"ok": False, "samples": [], "warnings": []}
    code = 0
    try:
        run(args, report)
        report["ok"] = True
    except RunError as err:
        report["error"] = {"code": err.code, "message": str(err)}
        code = 2
    except Exception as exc:  # noqa: BLE001 — report 는 항상 쓴다
        report["error"] = {"code": "INTERNAL", "message": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc(limit=8)}
        code = 3
    finally:
        write_json(args["report"], report)
    print(f"kimodo_run: {'done' if report['ok'] else report['error']['code']}", flush=True)
    sys.exit(code)


if __name__ == "__main__":
    main()
