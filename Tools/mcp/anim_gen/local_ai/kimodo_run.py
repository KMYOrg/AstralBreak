"""Kimodo 텍스트 → 모션 생성 — anim-gen-mcp local_ai Provider 가 Kimodo 전용 venv 의 python 으로 띄운다 (지침서 §14 Phase 5).

    <Kimodo venv>/Scripts/python.exe -I kimodo_run.py <args.json>

서버가 import 하지 않는다(torch · kimodo 는 이 venv 에만 있다). 프롬프트 · 프레임 수 · seed · 제약은 Provider 가 정해 args.json 에
넣고, 여기서는 적용만 한다. 결과는 샘플마다 NPZ + BVH(표준 T 포즈 SOMA77 · cm · 루트 트랙)와 report.json(임시 파일 → os.replace) —
실패해도 쓴다. 종료 코드 0 = 성공, 2 = 알려진 실패(report 에 코드), 3 = 잡지 못한 예외.

설정 근거(Phase 5 스파이크):
- 실행은 오프라인(HF_HUB_OFFLINE · LOCAL_CACHE) · 텍스트 인코더는 CPU(TEXT_ENCODER_DEVICE) — 환경 변수는 Provider 가 준다.
- BVH 기본 기준 포즈(BONES-SEED)는 회전 0 이 서 있는 자세가 아니라 anim_gen/bvh.py 의 단위 · 정면 측정이 틀린다 → 표준 T 포즈.
- Root 래퍼가 원점에 고정이라 리타깃 루트 모션이 0 이다 → root_track 이 모델의 바닥 궤적 · 방향을 Root 에 넣는다.

Phase 8-1 후보 · 2차 생성(args.candidates_mode): seeds 마다 seed_everything → 1차(요청 제약) → [refine.passes 2 면 1차 결과를 SOMA30 FK 로 다시
풀어 refine.py 로 자동 제약(양손 · 발 일반 end-effector · root2d)을 만들고 같은 seed 로 2차(요청 + 자동) → 계획의 smooth_sigma_frames 로 2차
출력 시간 스무딩(로컬 회전 · 루트 → 77 관절 FK)] → 후보 하나. 모델은 한 번만 적재한다. 후보마다 소스 수치(motion_metrics — 1 · 2차, 스무딩 전
2차도)와 제약 추종(목표 손목 · 접지 발 위치 차)을 report 에 남긴다. NPZ · BVH · 소스 수치는 스무딩 뒤 값이다.

Phase 9-3 키 포즈(args.key_pose_file — 생성 앞 key_pose 단계가 대상 애셋을 SOMA 로 되돌려 만든 관절 회전 · 엉덩 위치): origin 배치 항목은 1차부터
제약, pass1 배치 항목은 1차(키 없이)의 그 프레임 엉덩 xz · 방향에 두고 같은 seed 로 2차(파지 · 발 2차가 있으면 그 2차에 함께). 키 추종(관절 위치 ·
손발 회전) · 키 둘레 떨림을 report 에 남긴다(anim_gen/key_pose.py — 배치 · 지표는 순수 Python). Phase 9-3b: 계획의 key_pose_hold(키 · 파지가 묶지 않은
손)가 있으면 그 2차에서 그 손을 1차 손에 묶는다(hold_constraints).
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


def names77_of(skeleton):
    """SOMA77 관절 이름 순서 — 모델 골격이 SOMA30 이면 그 77 판(키 포즈 local_joints_rot 의 관절 축)."""
    return list((skeleton.somaskel77 if hasattr(skeleton, "somaskel77") else skeleton).bone_order_names)


def with_smooth_root(item):
    """키마다 바닥 루트(smooth_xz) — 원천 엉덩 궤적(hips_track)을 Kimodo 와 같은 매끈화(get_smooth_root_pos, 엉덩에서 6 cm 여유)로. 키 제약은 그 프레임의
    바닥 루트도 묶는다 — 비우면 Kimodo 가 엉덩 xz 로 채워 그 프레임만 바닥 루트 = 엉덩(이웃은 몇 cm 떨어짐)이 되어 경로가 꺾인다."""
    track = item.get("hips_track") or {}
    if not track.get("m"):
        return list(item["keys"])
    import torch
    from kimodo.motion_rep.smooth_root import get_smooth_root_pos
    smooth = get_smooth_root_pos(torch.tensor(track["m"], dtype=torch.float32)).cpu().numpy()
    out = []
    for k in item["keys"]:
        i = k["source_frame"] - track["first"]
        out.append({**k, "smooth_xz": [float(smooth[i, 0]), float(smooth[i, 2])]} if 0 <= i < len(smooth) else dict(k))
    return out


def key_pose_items(specs, key_pose, skeleton):
    """Phase 9-3 — key_pose 명세 + key_pose 단계 파일 → (origin 배치 Kimodo dict 목록, 배치 기록, pass1 에 둘 (명세, 파일 항목)). 파일의 관절 회전은
    SOMA77 이름별 — 모델 골격의 77 순서로 다시 줄 세운다(빠진 관절이 있으면 멈춘다)."""
    from anim_gen import key_pose as kp
    names77 = names77_of(skeleton)
    missing = sorted(set(names77) - set(key_pose.get("joints") or []))
    if missing:
        raise RunError("KEY_POSE_JOINTS_MISSING", f"key_pose file has no rotations for {missing[:8]} — not a SOMA77 profile")
    by_source = {item["source"]: item for item in key_pose.get("items") or []}
    items, records, deferred = [], [], []
    for spec in specs:
        item = by_source.get(spec["source"])
        if item is None or len(item["keys"]) != len(spec["frame_indices"]):
            raise RunError("BAD_CONSTRAINT", f"{spec['source']}: key_pose file has no matching item ({len((item or {}).get('keys') or [])} keys, "
                           f"planned {len(spec['frame_indices'])})")
        item = {**item, "keys": with_smooth_root(item)}
        if spec["placement"] == "origin":
            placed, rec = kp.place(item["keys"], None)
            items.append(kp.constraint(spec["part"], placed, names77))
            records.append({"source": spec["source"], "part": spec["part"], "placement": "origin", **rec})
        else:
            deferred.append((spec, item))
    return items, records, deferred


def place_on_pass1(deferred, single1, skeleton):
    """pass1 배치 — 1차(같은 seed · 키 없이)의 그 키 프레임 엉덩 xz · 방향(Kimodo heading 식)에 항목의 첫 키를 둔다."""
    from anim_gen import key_pose as kp
    names77 = names77_of(skeleton)
    posed = single1["posed_joints"]
    hips, left, right = names77.index(kp.HIPS), names77.index(kp.LEFT_HIP), names77.index(kp.RIGHT_HIP)
    items, records = [], []
    for spec, item in deferred:
        f = min(spec["frame_indices"])
        # 기준점 = 1차의 그 프레임 바닥 루트(키에 바닥 루트가 있을 때 — kp.place 와 같은 기준) 또는 엉덩 xz
        smooth = all(k.get("smooth_xz") for k in item["keys"]) and "smooth_root_pos" in single1
        xz = [float(single1["smooth_root_pos"][f, 0]), float(single1["smooth_root_pos"][f, 2])] if smooth else [float(posed[f, hips, 0]), float(posed[f, hips, 2])]
        target = {"xz": xz, "heading_rad": kp.heading(posed[f, left].tolist(), posed[f, right].tolist())}
        placed, rec = kp.place(item["keys"], target)
        items.append(kp.constraint(spec["part"], placed, names77))
        records.append({"source": spec["source"], "part": spec["part"], "placement": "pass1", **rec,
                        "target": {"xz_m": [round(x, 4) for x in target["xz"]], "heading_deg": round(target["heading_rad"] * 57.29577951308232, 2)}})
    return items, records


def key_follow(single, placed_items, parts, skeleton, device, pass1=None):
    """키 포즈 추종(cm · °) — 제약 프레임에서 생성 관절 위치 ↔ 제약 자세 FK(77, 같은 골격) · 손발 end-effector 는 전역 회전 차, 키 둘레 ± 10 프레임
    떨림(지그재그 p95 — 8-1 지표와 같은 정의), 2 패스면 같은 창의 1차 떨림(기준). parts = 항목마다 요청 part(full · right_hand …)."""
    import numpy as np
    import torch
    from anim_gen import key_pose as kp
    from kimodo.geometry import axis_angle_to_matrix
    names77 = names77_of(skeleton)
    skel77 = skeleton.somaskel77 if hasattr(skeleton, "somaskel77") else skeleton
    posed = single["posed_joints"]
    out = []
    for item, part in zip(placed_items, parts):
        frames = item["frame_indices"]
        local = axis_angle_to_matrix(torch.tensor(item["local_joints_rot"], dtype=torch.float32, device=device))
        g, p, _ = skel77.fk(local, torch.tensor(item["root_positions"], dtype=torch.float32, device=device))
        g, p = g.cpu().numpy(), p.cpu().numpy()
        joints = [names77.index(n) for n in kp.PART_JOINTS[part]]
        pos = [float(np.linalg.norm(posed[f, j] - p[k, j]) * 100.0) for k, f in enumerate(frames) for j in joints]
        rec = {"part": part, "type": item["type"], "frames": frames, "keys": len(frames), "position_cm": kp.spread(pos)}
        rjoints = [names77.index(n) for n in kp.PART_ROTATIONS.get(part, [])]
        if rjoints:
            rel = [g[k, j].T @ single["global_rot_mats"][f, j] for k, f in enumerate(frames) for j in rjoints]
            rec["rotation_deg"] = kp.spread([float(np.degrees(np.arccos(np.clip((np.trace(m) - 1.0) / 2.0, -1.0, 1.0)))) for m in rel])
        body = [names77.index(n) for n in kp.BODY_JOINTS]
        rec["jitter_p95"] = kp.key_jitter([(posed[:, j] * 100.0).tolist() for j in body], frames)
        if pass1 is not None:
            rec["jitter_pass1_p95"] = kp.key_jitter([(pass1["posed_joints"][:, j] * 100.0).tolist() for j in body], frames)
        out.append(rec)
    return out


def hold_constraints(single1, model, hands, pinned_items, step, device, around=None, window=None):
    """Phase 9-3b — 키 2차에서 키가 묶지 않은 손(계획 hold_free_hands)을 1차 손(SOMA30 FK 위치 · 회전)에 step 프레임마다 일반 end-effector 로 묶는다.
    E0(2026-11-02): 오른손 · 발 키만 준 2차가 자유 왼손목 비틀기를 1차 −105° 에서 −128° 로 키웠다(0.86초 손목 꺾임 — 스무딩과 무관) → 키가 키운 몫만
    막는다(1차의 비틀기는 생성 특성). around · window = 키 프레임 ± 프레임 안만(없으면 클립 전체). 요청 · 키 제약이 그 손을 이미 묶은 프레임은
    건너뛴다(refine.pinned)."""
    import torch
    from anim_gen.local_ai import refine
    from kimodo.constraints import EndEffectorConstraintSet
    skel30 = model.skeleton
    local77 = torch.from_numpy(single1["local_rot_mats"].astype("float32")).to(device)
    root = torch.from_numpy(single1["root_positions"].astype("float32")).to(device)
    rot30, pos30, _ = skel30.fk(skel30.from_SOMASkeleton77(local77), root)
    smooth2d = torch.from_numpy(single1["smooth_root_pos"][:, [0, 2]].astype("float32")).to(device)
    pin = refine.pinned(pinned_items)
    frames = int(pos30.shape[0])
    out, info = [], {}
    for part in hands:
        joint = refine.SIDES[part.split("_")[0]] + "Hand"
        idx = [f for f in refine.keyframes(0, frames - 1, step) if f not in pin[part]
               and (not around or window is None or min(abs(f - k) for k in around) <= window)]
        info[part] = {"joint": joint, "frames": idx}
        if idx:
            index = torch.tensor(idx, dtype=torch.long).to(device)
            out.append(EndEffectorConstraintSet(skel30, index.cpu(), pos30[index], rot30[index], smooth2d[index], joint_names=[joint]))
    return out, info


def hold_follow(single1, single2, info, names77):
    """묶은 손이 1차를 얼마나 지켰나(cm) — 묶은 프레임의 손목 위치 차."""
    import numpy as np
    out = {}
    for part, rec in info.items():
        idx = rec["frames"]
        if idx:
            j = names77.index(rec["joint"])
            d = np.linalg.norm(single2["posed_joints"][idx, j] - single1["posed_joints"][idx, j], axis=1) * 100.0
            out[part] = {"keyframes": len(idx), "p50": round(float(np.median(d)), 2), "max": round(float(d.max()), 2)}
    return out


def build_constraints(specs, skeleton, frames, key_pose=None):
    """Provider 명세 → Kimodo 제약 dict 목록 → load_constraints_lst (SOMA 77 ↔ 30 변환은 Kimodo 로더가 한다). Phase 9-3 key_pose: origin 배치 항목은
    여기서 dict 로, pass1 항목은 (명세, 파일 항목)으로 돌려준다(1차 뒤 place_on_pass1). → (제약 목록, 수, dict 목록, key_pose 기록)."""
    import numpy as np
    import torch
    from kimodo.constraints import load_constraints_lst
    from kimodo.geometry import matrix_to_axis_angle

    items = []
    keys = {"records": [], "deferred": [], "placed": []}
    key_specs = [s for s in specs if s["kind"] == "key_pose"]
    if key_specs:
        if key_pose is None:
            raise RunError("BAD_CONSTRAINT", "key_pose constraints planned but the key_pose step left no file")
        placed, keys["records"], keys["deferred"] = key_pose_items(key_specs, key_pose, skeleton)
        keys["placed"] = placed
    for spec in specs:
        if spec["kind"] == "key_pose":
            continue
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
    items += keys["placed"]
    for item in items + [kp_item for _, kp_item in keys["deferred"]]:
        frame_list = item["frame_indices"] if "frame_indices" in item else [k["frame"] for k in item["keys"]]
        if max(frame_list) >= frames:
            raise RunError("CONSTRAINT_OUT_OF_RANGE", f"a {item['type']} constraint uses frame {max(frame_list)} of {frames}")
    return (load_constraints_lst(items, skeleton) if items else []), len(items), items, keys


# SOMA77 → motion_metrics 역할(손목 · 엉덩 관절 · 발목 · 어깨 · 팔꿈치 · 중지 첫 마디 · 머리). SOMA 의 LeftLeg 는 넓적다리 = 엉덩 관절 위치,
# LeftArm 은 위팔 = 어깨 관절(Vesper 템플릿 체인 LeftArm 시작과 같은 자리), {Side}HandMiddle2 는 너클(Middle1 은 메타카팔 — Vesper middle_01 과 같은 마디),
# Head 는 Neck2 의 자식(두개 바닥 — Vesper 템플릿 체인 Head 시작과 같은 자리)
METRIC_JOINTS = {"hand_l": "LeftHand", "hand_r": "RightHand", "hip_l": "LeftLeg", "hip_r": "RightLeg", "foot_l": "LeftFoot", "foot_r": "RightFoot",
                 "shoulder_l": "LeftArm", "shoulder_r": "RightArm", "elbow_l": "LeftForeArm", "elbow_r": "RightForeArm",
                 "finger_l": "LeftHandMiddle2", "finger_r": "RightHandMiddle2", "head": "Head"}
HAND_PREFIXES = ("LeftHand", "RightHand")   # 손-머리 근접의 손 점 = 손목 아래 SOMA 손 관절 전부(Vesper 쪽은 손 본 자손)
ARM_JOINTS = [f"{s}{j}" for s in ("Left", "Right") for j in ("Arm", "ForeArm", "Hand", "HandMiddleEnd", "HandThumbEnd")]
KNUCKLES = [f"{s}Hand{f}2" for s in ("Left", "Right") for f in ("Index", "Pinky")]
SMOOTH_FK_TOLERANCE_M = 0.01   # 스무딩 FK 대응 검사 — 스무딩 전 로컬 회전으로 푼 위치가 모델 출력과 이만큼 넘게 다르면 멈춘다


def source_metrics(single, names77, fps, window, spacing_cm=None):
    """한 샘플(77 관절 출력)의 소스 수치 — m · y-up → cm, scale 1(Kimodo 사람 크기). 접지 발 미끄러짐은 모델 접지 라벨(앞 절반 = 왼발)로.
    spacing_cm = 요청 파지 간격(자루 무기 — 파지 판정 띠)."""
    from anim_gen import motion_metrics
    joints = single["posed_joints"]
    tracks = {role: (joints[:, names77.index(name)] * 100.0).tolist() for role, name in METRIC_JOINTS.items()}
    hand_points = [(joints[:, i] * 100.0).tolist() for i, n in enumerate(names77) if n.startswith(HAND_PREFIXES) and n not in HAND_PREFIXES]
    times = [i / fps for i in range(joints.shape[0])]
    out = motion_metrics.measure(tracks, times, up=1, scale=1.0, window=window, spacing_cm=spacing_cm, hand_points=hand_points)
    contacts = single.get("foot_contacts")
    if contacts is not None and len(contacts.shape) == 2 and contacts.shape[1] >= 2:
        half = contacts.shape[1] // 2
        flags = {"l": contacts[:, :half].astype(bool).any(axis=1).tolist(), "r": contacts[:, half:].astype(bool).any(axis=1).tolist()}
        out["foot_slide"] = {s: motion_metrics.contact_slide(tracks[f"foot_{s}"], flags[s], times, up=1) for s in ("l", "r")}
    return out


def call_inputs(args):
    """Kimodo 호출의 (프롬프트 목록, 프레임 목록, 전이 프레임). Phase 9-2 segments 면 세그먼트마다(multi_prompt — 순서대로 잇는다), 아니면
    프롬프트 하나(개정 10 그대로 — 같은 호출)."""
    if args.get("prompts"):
        if len(args["prompts"]) != len(args["segment_frames"]) or sum(args["segment_frames"]) != args["frames"]:
            raise RunError("BAD_SEGMENTS", f"{len(args['prompts'])} prompts / segment frames {args['segment_frames']} do not make {args['frames']} frames")
        return list(args["prompts"]), list(args["segment_frames"]), int(args["transition_frames"])
    return [args["prompt"]], [args["frames"]], 5


def source_seams(single, names77, fps, boundaries_s, root_idx):
    """Phase 9-2 — 소스 이음매 수치(segments.py 정의): 경계마다 관절 로컬 회전 평균 변화의 단계 비(C++ SEAM_JUMP 와 같은 식) + 손목 · 발목 ·
    골반(루트 관절) · 바닥 루트(smooth_root_pos) 속도 앞뒤 비 · 속도 변화 비. cm · scale 1."""
    import numpy as np
    from anim_gen import motion_metrics, segments
    rots = single["local_rot_mats"]
    rel = np.einsum("tjab,tjac->tjbc", rots[:-1], rots[1:])          # R_t^T · R_{t+1}
    cos = np.clip((np.trace(rel, axis1=-2, axis2=-1) - 1.0) * 0.5, -1.0, 1.0)
    steps = np.degrees(np.arccos(cos)).mean(axis=1).tolist()          # steps[i] = 프레임 i → i+1
    joints = single["posed_joints"] * 100.0
    n = int(joints.shape[0])
    times = [i / fps for i in range(n)]
    tracks = {"hand_l": joints[:, names77.index("LeftHand")], "hand_r": joints[:, names77.index("RightHand")],
              "foot_l": joints[:, names77.index("LeftFoot")], "foot_r": joints[:, names77.index("RightFoot")], "pelvis": joints[:, root_idx]}
    root = single["smooth_root_pos"] * 100.0
    tracks["root"] = np.stack([root[:, 0], np.zeros(n), root[:, 2]], axis=1)
    speeds = {role: motion_metrics.speeds(tr.tolist(), times)[1:] for role, tr in tracks.items()}
    rows = segments.speed_seams(times[1:], speeds, boundaries_s, 1.0)
    for row, t in zip(rows, boundaries_s):
        row["rotation_step_ratio"] = segments.step_ratio(steps, int(round(t * fps)))
    return {"seams": rows, "rotation_step_ratio_max": segments.worst(rows, "rotation_step_ratio"),
            "speed_step_ratio_max": segments.worst(rows, "speed_step_ratio_max")}


def segment_follow(single1, single2, starts, names77):
    """Phase 9-2 — 같은 seed 의 2차가 세그먼트마다 1차를 얼마나 재현하는가(cm): 몸(엉덩 · 발목 · 어깨 · 머리 — 파지 제약이 옮기는 손 · 팔꿈치 제외) ·
    손목 위치 차 p50 · p95 · 최대, 바닥 루트 xz 차. starts = 세그먼트 시작 프레임."""
    import numpy as np
    names = list(names77)
    n = int(single1["posed_joints"].shape[0])
    body = [names.index(METRIC_JOINTS[r]) for r in ("hip_l", "hip_r", "foot_l", "foot_r", "shoulder_l", "shoulder_r", "head")]
    hands = [names.index("LeftHand"), names.index("RightHand")]
    p1, p2 = single1["posed_joints"] * 100.0, single2["posed_joints"] * 100.0
    r1, r2 = single1["smooth_root_pos"][:, [0, 2]] * 100.0, single2["smooth_root_pos"][:, [0, 2]] * 100.0
    bounds = list(starts) + [n]
    out = []

    def spread(d):
        return {"p50": round(float(np.percentile(d, 50)), 2), "p95": round(float(np.percentile(d, 95)), 2), "max": round(float(d.max()), 2)}
    for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
        out.append({"index": i, "frames": [a, b - 1], "body_cm": spread(np.linalg.norm(p2[a:b, body] - p1[a:b, body], axis=-1).ravel()),
                    "hands_cm": spread(np.linalg.norm(p2[a:b, hands] - p1[a:b, hands], axis=-1).ravel()),
                    "root_xz_cm": spread(np.linalg.norm(r2[a:b] - r1[a:b], axis=-1))})
    return out


def smooth_output(single, skeleton, sigma, device):
    """2차 출력 시간 스무딩 — σ 는 계획(refine.plan 의 smooth_sigma_frames)이 정한 값을 그대로 쓴다. 로컬 회전(쿼터니언 부호 연속) · 루트 위치에
    가우시안(refine.smooth_rotations · smooth_series) → 77 관절 FK 로 전역 회전 · 관절 위치를 다시 만든다. smooth_root_pos · heading(이미 매끈한
    루트 — root_track 이 쓴다) · 접지 라벨은 그대로. 스무딩 전 로컬 회전으로 푼 위치가 모델 출력과 같은지(fk_check_m) 먼저 본다."""
    import numpy as np
    import torch
    from anim_gen.local_ai import refine

    def fk(local, root):
        g, p, _ = skeleton.fk(torch.as_tensor(np.asarray(local), dtype=torch.float32, device=device),
                              torch.as_tensor(np.asarray(root), dtype=torch.float32, device=device))
        return g.cpu().numpy(), p.cpu().numpy()
    _, check = fk(single["local_rot_mats"], single["root_positions"])
    fk_diff = float(np.abs(check - single["posed_joints"]).max())
    if fk_diff > SMOOTH_FK_TOLERANCE_M:
        raise RunError("SMOOTH_FK_MISMATCH", f"pass-2 local rotations do not rebuild the model's joints (max {fk_diff:.4f} m) — smoothing would move "
                       "the pose; plan with generation.refine.mode off or report this")
    local = refine.smooth_rotations(single["local_rot_mats"].tolist(), sigma)
    root = refine.smooth_series(single["root_positions"].tolist(), sigma)
    glob, posed = fk(local, root)
    out = dict(single)
    out.update(local_rot_mats=np.asarray(local, dtype=single["local_rot_mats"].dtype), root_positions=np.asarray(root, dtype=single["root_positions"].dtype),
               global_rot_mats=glob.astype(single["global_rot_mats"].dtype), posed_joints=posed.astype(single["posed_joints"].dtype))
    moved = np.linalg.norm(out["posed_joints"] - single["posed_joints"], axis=-1) * 100.0
    return out, {"sigma_frames": sigma, "fk_check_m": round(fk_diff, 6),
                 "joint_moved_cm": {"p95": round(float(np.percentile(moved, 95)), 2), "max": round(float(moved.max()), 2)}}


def refine_constraints(single1, model, requested_items, cfg, device):
    """1차 결과 → 자동 제약 목록 · 기록. 1차 77 관절 로컬 회전을 SOMA30 으로 줄여 FK 로 다시 푼다(모델 골격 = 확산 · 후처리가 쓰는 관절).

    손 · 발은 일반 end-effector(EndEffectorConstraintSet, joint_names 지정)로 넣는다 — 확산 조건만 걸리고 후처리는 그 프레임을 고정하지 않는다
    (마스크는 left-hand 같은 클래스 이름만 본다). 스파이크(2026-10-26, seed 20261025): 후처리가 손을 고정하면 처음 · 끝 12프레임이 1차 손 간격으로
    되돌아가고(순간 이동 810 cm/s) 매 프레임 고정은 전 구간이 깨진다. 후처리 발 고정은 목표 루트 xz 를 매끈한 루트로 바꿔 계산해(postprocess
    extract_input_motion_from_constraints) 발이 미끄러진다(p95 34 ~ 45 cm/s). 일반 EE 면 파지 100% · 손 목표 p50 2.5 cm · 발 위치 1차 ± 2.6 cm ·
    접지 미끄러짐 p95 3 cm/s(후처리의 표준 접지 정리가 그대로 돈다). root2d 는 후처리가 루트 여유(root_margin 4 cm) 안으로 맞춘다."""
    import numpy as np
    import torch
    from anim_gen.local_ai import refine
    from kimodo.constraints import EndEffectorConstraintSet, Root2DConstraintSet

    skel30 = model.skeleton
    names30, names77 = list(skel30.bone_order_names), list(skel30.somaskel77.bone_order_names)
    local77 = torch.from_numpy(single1["local_rot_mats"].astype("float32")).to(device)
    root = torch.from_numpy(single1["root_positions"].astype("float32")).to(device)
    rot30, pos30, _ = skel30.fk(skel30.from_SOMASkeleton77(local77), root)
    pos77 = single1["posed_joints"]
    # 30 ↔ 77 대응 확인(스파이크): 공통 이름의 위치가 같아야 한다 — *End 잎 관절은 77 이 손가락 사슬 끝이라 뺀다
    shared = [n for n in names30 if not n.endswith("End")]
    fk_diff = float(max(np.abs(pos30[:, names30.index(n)].cpu().numpy() - pos77[:, names77.index(n)]).max() for n in shared))
    frames = int(pos77.shape[0])
    step = cfg["keyframe_step"]
    pin = refine.pinned(requested_items)
    smooth2d = torch.from_numpy(single1["smooth_root_pos"][:, [0, 2]].astype("float32")).to(device)
    heading = torch.from_numpy(single1["global_root_heading"].astype("float32")).to(device)
    pos, rot = pos30.clone(), rot30.clone()
    out, info = [], {"fk_check_m": round(fk_diff, 6), "constraints": [], "pinned_skipped": {}}

    def add(joints, idx, p, r):
        index = torch.tensor(idx, dtype=torch.long)
        out.append(EndEffectorConstraintSet(skel30, index, p[index.to(device)], r[index.to(device)], smooth2d[index.to(device)], joint_names=joints))
        info["constraints"].append({"type": "end-effector", "joint_names": joints, "frames": len(idx), "first": idx[0], "last": idx[-1]})

    rules = {r["flag"] or "root": r for r in cfg["rules"]}
    if "two_hand_weapon_grip" in rules:
        rule = rules["two_hand_weapon_grip"]
        grip_frames = refine.keyframes(rule["frames"]["from"], rule["frames"]["to"], step)
        skip = pin["left_hand"] | pin["right_hand"]
        info["pinned_skipped"]["grip"] = len([f for f in grip_frames if f in skip])
        grip_frames = [f for f in grip_frames if f not in skip]
        if grip_frames:
            pose = {"pos": {n: pos30[:, names30.index(n)].cpu().tolist() for n in ARM_JOINTS},
                    "rot": {n: rot30[:, names30.index(n)].cpu().tolist() for n in ARM_JOINTS}}
            if rule.get("handle"):
                # Phase 9-3b — 운영 부착 자루 규칙: 보조 손바닥 = 손목 · 중지 너클 중점(9-1 handle 기록 · weapon.resolve 와 같은 점)
                palms = {s: ((pos77[:, names77.index(f"{s}Hand")] + pos77[:, names77.index(f"{s}HandMiddle2")]) * 0.5).tolist() for s in ("Left", "Right")}
                g = refine.solve_handle_grip(pose, palms, grip_frames, lead=rule["lead_hand"], target=rule["target"], spacing_cm=rule["spacing_cm"],
                                             handle=rule["handle"], unit_cm=100.0)
            else:
                knuckles = {n: pos77[:, names77.index(n)].tolist() for n in KNUCKLES}
                g = refine.solve_grip(pose, knuckles, grip_frames, lead=rule["lead_hand"], target=rule["target"], spacing_cm=rule["spacing_cm"], unit_cm=100.0)
            for f, changes in g["frames"].items():
                for name, v in changes.items():
                    i = names30.index(name)
                    pos[f, i] = torch.tensor(v["pos"], dtype=pos.dtype, device=device)
                    rot[f, i] = torch.tensor(v["rot"], dtype=rot.dtype, device=device)
            add(["LeftHand", "RightHand"], grip_frames, pos, rot)
            info["grip"] = {k: g[k] for k in ("lead", "support", "target", "hand_rule", "spacing_cm", "knuckle_cm", "stats")}
            if g.get("handle_frame"):
                info["grip"]["handle_frame"] = g["handle_frame"]
                info["grip"]["window"] = [rule["frames"]["from"], rule["frames"]["to"]]
            info["grip"]["frames"] = grip_frames
            info["grip"]["targets"] = {str(f): {k: [round(x * 100.0, 3) for x in v] for k, v in t.items()} for f, t in g["targets"].items()}
    if "foot_contact" in rules:
        contacts = single1["foot_contacts"].astype(bool)   # 77 출력 6열 [L 뒤꿈치 · L 발끝 · L 발끝 끝 · R …] (output_to_SOMASkeleton77)
        info["foot"] = {}
        for side, cols, joint, part in (("left", slice(0, 3), "LeftFoot", "left_foot"), ("right", slice(3, 6), "RightFoot", "right_foot")):
            idx = refine.foot_frames(contacts[:, cols].any(axis=1).tolist(), step, skip=pin[part])
            info["foot"][side] = {"frames": idx, "contact_pct": round(100.0 * float(contacts[:, cols].any(axis=1).mean()), 1)}
            if idx:
                add([joint], idx, pos30, rot30)
    if "root" in rules:
        idx = [f for f in refine.keyframes(0, frames - 1, step) if f not in pin["root"]]
        if idx:
            index = torch.tensor(idx, dtype=torch.long)
            out.append(Root2DConstraintSet(skel30, index, smooth2d[index.to(device)], global_root_heading=heading[index.to(device)]))
            info["constraints"].append({"type": "root2d", "frames": len(idx), "first": idx[0], "last": idx[-1]})
    return out, info


def handle_metrics(single, grip, names77):
    """한 샘플의 자루 지표(cm · °) — 주 손 전역 회전 · 손목으로 붙인 자루(handle_frame — 손 공간 방향 · 오프셋) ↔ 보조 손바닥(손목 · 중지 너클 중점)."""
    import numpy as np
    hf = grip["handle_frame"]
    lead, sup = grip["lead"], grip["support"]
    li, si, sm = names77.index(f"{lead}Hand"), names77.index(f"{sup}Hand"), names77.index(f"{sup}HandMiddle2")
    lo, hi = grip["window"]
    h, o = np.array(hf["dir"]), np.array(hf["offset"])
    dist, ang = [], []
    for f in range(lo, hi + 1):
        g, w = single["global_rot_mats"][f, li], single["posed_joints"][f, li]
        d = g @ h
        a = w + g @ o
        palm = (single["posed_joints"][f, si] + single["posed_joints"][f, sm]) * 0.5
        rel = palm - a
        dist.append(float(np.linalg.norm(rel - d * float(rel @ d))) * 100.0)
        v = palm - w
        ang.append(float(np.degrees(np.arctan2(np.linalg.norm(np.cross(v, d)), abs(float(v @ d))))))
    return {"palm_line_cm": {"p50": round(float(np.median(dist)), 2), "max": round(max(dist), 2)},
            "angle_deg": {"p50": round(float(np.median(ang)), 2), "max": round(max(ang), 2)}, "frames": len(dist)}


def follow(single1, single2, info, names77):
    """2차가 제약을 따랐는가(cm) — 목표 손목(파지 키 프레임) · 접지 발목(1차와 같은 위치) · 루트."""
    import numpy as np
    pos1, pos2 = single1["posed_joints"] * 100.0, single2["posed_joints"] * 100.0
    out = {}
    grip = info.get("grip")
    if grip:
        errs = {"lead": [], "support": []}
        for f, t in grip["targets"].items():
            for role, side in (("lead", grip["lead"]), ("support", grip["support"])):
                errs[role].append(float(np.linalg.norm(pos2[int(f), names77.index(f"{side}Hand")] - np.array(t[role]))))
        out["grip_target_error_cm"] = {k: {"p50": round(float(np.median(v)), 2), "max": round(float(max(v)), 2)} for k, v in errs.items() if v}
        if grip.get("handle_frame"):
            # Phase 9-3b — 소스 쪽 자루 지표(파지 구간 모든 프레임): 보조 손바닥 ↔ 주 손에 붙인 자루 선 거리 · 두 손 선 ∠ 자루(9-1 handle 과 같은 정의)
            out["handle"] = {"pass1": handle_metrics(single1, grip, names77), "pass2": handle_metrics(single2, grip, names77)}
    for side, name in (("left", "LeftFoot"), ("right", "RightFoot")):
        idx = ((info.get("foot") or {}).get(side) or {}).get("frames") or []
        if idx:
            d = np.linalg.norm(pos2[idx, names77.index(name)] - pos1[idx, names77.index(name)], axis=1)
            out[f"foot_hold_{side}_cm"] = {"p50": round(float(np.median(d)), 2), "max": round(float(d.max()), 2)}
    r1, r2 = single1["smooth_root_pos"][:, [0, 2]] * 100.0, single2["smooth_root_pos"][:, [0, 2]] * 100.0
    out["root_xz_diff_cm"] = {"p50": round(float(np.median(np.linalg.norm(r2 - r1, axis=1))), 2), "max": round(float(np.linalg.norm(r2 - r1, axis=1).max()), 2)}
    return out


def run(args, report):
    sys.path.insert(0, args["package_dir"])
    from anim_gen.local_ai import root_track

    t0 = time.time()
    import torch
    from kimodo import load_model
    from kimodo.constraints import load_constraints_lst
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
    key_pose = json.loads(pathlib.Path(args["key_pose_file"]).read_text(encoding="utf-8")) if args.get("key_pose_file") else None
    constraint_lst, n_constraints, requested_items, keys = build_constraints(args["constraints"], model.skeleton, args["frames"], key_pose)
    report["constraints"] = n_constraints
    if key_pose is not None:
        # Phase 9-3 — origin 배치는 지금(1차부터), pass1 배치는 1차 뒤 2차에서
        report["key_pose"] = {"file": args["key_pose_file"], "origin": keys["records"], "pass1_items": [s["source"] for s, _ in keys["deferred"]]}

    skeleton = model.skeleton
    if isinstance(skeleton, SOMASkeleton30):
        skeleton = skeleton.somaskel77.to(device)  # 출력은 모델 안에서 이미 77 관절로 바뀌었다
    out_dir = pathlib.Path(args["out_dir"])
    prompts, frame_list, transition = call_inputs(args)
    boundaries = args.get("boundaries_s")
    if args.get("prompts"):
        report["segments"] = {"count": len(prompts), "frames": frame_list, "transition_frames": transition, "boundaries_s": boundaries}
    names77 = list(skeleton.bone_order_names)

    def generate(seed, constraints):
        seed_everything(seed)
        return model(prompts, frame_list, constraint_lst=constraints, num_denoising_steps=args["steps"],
                     num_samples=args["samples"], multi_prompt=True, num_transition_frames=transition, post_processing=postprocess, return_numpy=True)

    def seams(single):
        return source_seams(single, names77, float(model.fps), boundaries, skeleton.root_idx)

    def pick(output, i):
        n = int(output["posed_joints"].shape[0])
        return {k: (v[i] if hasattr(v, "shape") and len(v.shape) > 0 and v.shape[0] == n else v) for k, v in output.items()}

    export_s = [0.0]

    def export(single, stem):
        t = time.time()
        try:
            return _export(single, stem)
        finally:
            export_s[0] += time.time() - t

    def _export(single, stem):
        save_kimodo_npz(str(stem.with_suffix(".npz")), single)
        joints_pos = torch.from_numpy(single["posed_joints"]).to(device)
        local = global_rots_to_local_rots(torch.from_numpy(single["global_rot_mats"]).to(device), skeleton)
        text = motion_to_bvh(local, joints_pos[:, skeleton.root_idx, :], skeleton=skeleton, fps=model.fps, standard_tpose=True)
        stats = None
        if args["root_track"]:
            xz = [(float(p[0]) * 100.0, float(p[2]) * 100.0) for p in single["smooth_root_pos"]]
            try:
                text, stats = root_track.apply_root_track(text, xz, root_track.heading_deg(single["global_root_heading"].tolist()))
            except root_track.RootTrackError as err:
                raise RunError(err.code, f"root track: {err.message}") from None
        stem.with_suffix(".bvh").write_text(text, encoding="utf-8")
        return {"npz": stem.with_suffix(".npz").as_posix(), "bvh": stem.with_suffix(".bvh").as_posix(), "frames": int(single["posed_joints"].shape[0]),
                "root": stats}

    def key_sets(single1):
        """pass1 배치 키 → (Kimodo 제약 집합, dict, 배치 기록). 배치할 키가 없으면 빈 값."""
        if not keys["deferred"]:
            return [], [], []
        dicts, recs = place_on_pass1(keys["deferred"], single1, skeleton)
        return load_constraints_lst(dicts, model.skeleton), dicts, recs

    def key_record(single, placed, recs, pass1=None):
        records = keys["records"] + recs
        return {"placements": records, "follow": key_follow(single, keys["placed"] + placed, [r["part"] for r in records], skeleton, device, pass1)}

    hold_plan = args.get("key_pose_hold") or {}

    def hold_sets(single1, pinned_items):
        """Phase 9-3b — 키 2차의 자유 손 고정(계획 hold_free_hands). 없으면 빈 값."""
        if not hold_plan.get("hands"):
            return [], None
        return hold_constraints(single1, model, hold_plan["hands"], pinned_items, int(hold_plan.get("keyframe_step") or 3), device,
                                around=hold_plan.get("around_frames"), window=hold_plan.get("window_frames"))

    def hold_record(single1, single2, info):
        return None if info is None else {"hands": {p: {"joint": r["joint"], "keyframes": len(r["frames"])} for p, r in info.items()},
                                          "follow_cm": hold_follow(single1, single2, info, names77)}

    gen_seconds = []
    if not args.get("candidates_mode"):
        # 개정 10 그대로 — seed 하나 · samples 개 샘플
        t = time.time()
        output = generate(args["seed"], constraint_lst)
        first, placed, recs, held = None, [], [], None
        if keys["deferred"]:
            # Phase 9-3 — pass1 배치 키: 키 없이 만든 1차의 루트 · 방향에 두고 같은 seed 로 2차(샘플 1 — 계획이 막는다)
            if args["samples"] != 1:
                raise RunError("KEY_POSE_WITH_SAMPLES", "key poses placed on pass 1 generate one sample — plan with generation.samples 1")
            first = pick(output, 0)
            save_kimodo_npz(str((out_dir / f"{args['stem']}_00_pass1.npz")), first)
            sets, placed, recs = key_sets(first)
            hold, held = hold_sets(first, requested_items + placed)
            output = generate(args["seed"], list(constraint_lst) + sets + hold)
        gen_seconds.append(round(time.time() - t, 2))
        n = int(output["posed_joints"].shape[0])
        key_sigma = args.get("key_pose_smooth") if key_pose is not None else None
        for i in range(n):
            single = pick(output, i)
            ksmooth = None
            if key_sigma:
                # Phase 9-3 — 키 둘레 떨림 → 8-1 수정안 A 와 같은 σ 스무딩(계획 값)
                single, ksmooth = smooth_output(single, skeleton, key_sigma, device)
            entry = {"index": i, **export(single, out_dir / f"{args['stem']}_{i:02d}")}
            if boundaries:
                entry["segments"] = seams(single)
            if key_pose is not None:
                entry["key_pose"] = key_record(single, placed, recs, first)
                entry["key_pose"]["smooth"] = ksmooth
                if held is not None:
                    entry["key_pose"]["hold"] = hold_record(first, single, held)
                if first is not None:
                    entry["pass1_npz"] = (out_dir / f"{args['stem']}_00_pass1.npz").as_posix()
            report["samples"].append(entry)
    else:
        # Phase 8-1 — seed 마다 후보 하나(1차 → [자동 제약 → 2차])
        refine_cfg = args.get("refine") or {"passes": 1, "rules": []}
        if refine_cfg["passes"] == 2 and args["samples"] != 1:
            raise RunError("REFINE_WITH_SAMPLES", "refine (two passes) generates one sample per seed — plan with generation.samples 1")
        window = tuple(args.get("metric_window") or (None, None))
        spacing = next((r.get("spacing_cm") for r in refine_cfg["rules"] if r.get("flag") == "two_hand_weapon_grip"), None)

        def measure(single):
            return source_metrics(single, names77, float(model.fps), window, spacing)
        for ci, seed in enumerate(args["seeds"]):
            stem = out_dir / f"{args['stem']}_{ci:02d}"
            t = time.time()
            first = pick(generate(seed, constraint_lst), 0)
            entry = {"index": ci, "seed": seed, "metrics": {"pass1": measure(first)}}
            final = first
            placed, recs, held = [], [], None
            if refine_cfg["passes"] == 2:
                save_kimodo_npz(str(stem.with_name(stem.name + "_pass1.npz")), first)
                sets, placed, recs = key_sets(first)
                auto, info = refine_constraints(first, model, requested_items + placed, refine_cfg, device)
                hold, held = hold_sets(first, requested_items + placed) if sets else ([], None)
                second = pick(generate(seed, list(constraint_lst) + sets + auto + hold), 0)
                sigma = refine_cfg.get("smooth_sigma_frames")
                if sigma:
                    entry["metrics"]["pass2_unsmoothed"] = measure(second)
                    second, info["smooth"] = smooth_output(second, skeleton, sigma, device)
                entry["metrics"]["pass2"] = measure(second)
                info["follow"] = follow(first, second, info, names77)
                entry["refine"] = info
                entry["pass1_npz"] = stem.with_name(stem.name + "_pass1.npz").as_posix()
                final = second
            elif keys["deferred"]:
                # Phase 9-3 — 키만 2 패스(파지 · 발 자동 제약 없음): 1차 루트 · 방향에 키를 두고 같은 seed 2차, 스무딩 없음
                save_kimodo_npz(str(stem.with_name(stem.name + "_pass1.npz")), first)
                sets, placed, recs = key_sets(first)
                hold, held = hold_sets(first, requested_items + placed)
                final = pick(generate(seed, list(constraint_lst) + sets + hold), 0)
                entry["metrics"]["pass2"] = measure(final)
                entry["pass1_npz"] = stem.with_name(stem.name + "_pass1.npz").as_posix()
            if key_pose is not None:
                two_pass = final is not first
                ksmooth = None
                key_sigma = args.get("key_pose_smooth")
                if key_sigma and not (refine_cfg["passes"] == 2 and refine_cfg.get("smooth_sigma_frames")):
                    # Phase 9-3 — 키 둘레 떨림 → σ 스무딩(파지 · 발 2차가 이미 스무딩했으면 한 번만)
                    entry["metrics"]["key_unsmoothed"] = measure(final)
                    final, ksmooth = smooth_output(final, skeleton, key_sigma, device)
                    entry["metrics"]["key_smoothed"] = measure(final)
                entry["key_pose"] = key_record(final, placed, recs, first if two_pass else None)
                entry["key_pose"]["smooth"] = ksmooth
                if held is not None:
                    entry["key_pose"]["hold"] = hold_record(first, final, held)
            if boundaries:
                entry["segments"] = seams(final)
                if final is not first:
                    entry["segments"]["pass1"] = seams(first)
                    entry["segments"]["follow"] = segment_follow(first, final, [0] + [int(round(b * float(model.fps))) for b in boundaries], names77)
            gen_seconds.append(round(time.time() - t, 2))
            report["samples"].append({**entry, **export(final, stem)})
    report["postprocess"] = {"requested": postprocess, "applied": postprocess}
    report["seconds"] = {"import": round(t1 - t0, 2), "load": round(t2 - t1, 2), "generate": round(sum(gen_seconds), 2), "export": round(export_s[0], 2),
                         "total": round(time.time() - t0, 2)}
    if args.get("candidates_mode"):
        report["seconds"]["per_candidate"] = gen_seconds


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
