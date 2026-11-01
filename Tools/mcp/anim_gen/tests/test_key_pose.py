"""Phase 9-3 키 포즈 · 역리타깃 (지침서 §14 '9-3') — 변환 수식(UE ↔ Kimodo) · 방향 · 배치 · 편집 op · 떨림 · Kimodo 설치본 T 포즈 찾기 ·
요청 검사 · 제약 변환 · 계획(key_pose 단계 · 패스 · 기한 · 막힘) · key_pose 단계 실행(FakeEditor · 가짜 Blender) · Kimodo 인자."""
from __future__ import annotations

import json
import math
import pathlib
import random

import pytest

from anim_gen import key_pose as kp
from anim_gen.body_model import qconj, qmul, qnormalize, qrot
from anim_gen.editor import asset_name
from anim_gen.local_ai import constraints as kc
from anim_gen.providers import key_pose as kp_step
from conftest import AIM_IDLE, KATANA, request
from test_local_ai import KimodoProc, ai_request, ka, soma_bvh, status  # noqa: F401 — ka 는 fixture


def S(v):
    return (v[0], v[2], v[1])


def rand_quat(rng) -> tuple:
    q = (rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))
    return qnormalize(q)


def angle(a, b) -> float:
    d = qnormalize(qmul(qconj(a), b))
    return math.degrees(2.0 * math.acos(min(1.0, abs(d[3]))))


# ---- 수식 ----
def test_axis_map_is_the_reflection_of_the_rotation():
    rng = random.Random(3)
    for _ in range(50):
        q, v = rand_quat(rng), (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))
        got = qrot(kp.ue_to_kimodo_quat(q), S(v))
        want = S(qrot(q, v))
        assert max(abs(a - b) for a, b in zip(got, want)) < 1e-9
    assert kp.ue_to_kimodo_quat(kp.ue_to_kimodo_quat((0.1, 0.2, 0.3, 0.9))) == (0.1, 0.2, 0.3, 0.9)   # 반사 짝은 제 역
    assert kp.ue_to_kimodo_point((10.0, 20.0, 95.0)) == (0.1, 0.95, 0.2)


TREE = {"Root": None, "Hips": "Root", "LeftLeg": "Hips", "RightLeg": "Hips", "Spine1": "Hips", "Head": "Spine1"}
OFFSETS_K = {"LeftLeg": (0.1, -0.05, 0.0), "RightLeg": (-0.1, -0.05, 0.0), "Spine1": (0.0, 0.1, 0.0), "Head": (0.0, 0.6, 0.0)}


def kimodo_pose(rng, hips=(0.3, 0.92, -0.4)):
    """Kimodo 로컬 회전(rotvec) · FK → (로컬, 전역, 위치 m)."""
    local = {b: [rng.uniform(-0.8, 0.8) for _ in range(3)] for b in TREE if b != "Root"}
    glob, pos = {}, {"Hips": hips}
    for b in ("Hips", "LeftLeg", "RightLeg", "Spine1", "Head"):
        p = TREE[b]
        glob[b] = kp.from_rotvec(local[b]) if p == "Root" else qnormalize(qmul(glob[p], kp.from_rotvec(local[b])))
        if p != "Root":
            off = qrot(glob[p], OFFSETS_K[b])
            pos[b] = tuple(pos[p][i] + off[i] for i in range(3))
    return local, glob, pos


def test_convert_recovers_the_kimodo_local_rotations_and_hips():
    rng = random.Random(11)
    local, glob, pos = kimodo_pose(rng)
    ref = {b: rand_quat(rng) for b in TREE}                       # Blender 본 축 — 기준 포즈 컴포넌트 회전은 제각각
    rot_ue = {b: qnormalize(qmul(kp.ue_to_kimodo_quat(glob[b]), ref[b])) for b in glob}   # ΔG_UE = Q_t·Q_ref⁻¹ = S·G·S
    rot_ue["Root"] = rand_quat(rng)                               # 래퍼는 무시된다
    pos_ue = {b: tuple(100.0 * x for x in S(p)) for b, p in pos.items()}
    out = kp.convert(rot_ue, pos_ue, ref, TREE)
    assert set(out["rotvec"]) == set(local)
    for b in local:
        assert angle(kp.from_rotvec(out["rotvec"][b]), kp.from_rotvec(local[b])) < 1e-4, b
    assert max(abs(a - b) for a, b in zip(out["hips_m"], pos["Hips"])) < 1e-6
    assert abs(out["heading_rad"] - kp.heading(pos["LeftLeg"], pos["RightLeg"])) < 1e-6


def test_heading_convention_matches_kimodo():
    left, right = (0.1, 0.9, 0.0), (-0.1, 0.9, 0.0)                  # Kimodo +X = 왼쪽, +Z 정면 → 0
    assert abs(kp.heading(left, right)) < 1e-12
    for phi in (0.3, -1.2, 2.5):
        assert abs(kp.wrap(kp.heading(kp.rotate_y(left, phi), kp.rotate_y(right, phi)) - phi)) < 1e-9


def _fk_heading(key) -> float:
    g = kp.from_rotvec(key["rotvec"]["Hips"])
    h = key["hips_m"]
    leg = lambda side: tuple(h[i] + qrot(g, OFFSETS_K[side])[i] for i in range(3))  # noqa: E731
    return kp.heading(leg("LeftLeg"), leg("RightLeg"))


@pytest.mark.parametrize("target", [None, {"xz": [1.5, -2.0], "heading_rad": 0.7}])
def test_place_puts_the_first_key_on_the_target_and_keeps_the_relative_path(target):
    rng = random.Random(5)
    keys = []
    for frame, hips in ((40, (0.5, 0.9, 0.2)), (10, (0.3, 0.92, -0.4))):
        local, _, pos = kimodo_pose(rng, hips)
        keys.append({"frame": frame, "rotvec": local, "hips_m": list(hips), "heading_rad": kp.heading(pos["LeftLeg"], pos["RightLeg"])})
    placed, rec = kp.place(keys, target)
    assert [k["frame"] for k in placed] == [10, 40] and rec["anchor_frame"] == 10
    want_xz, want_h = (target or {}).get("xz", [0.0, 0.0]), (target or {}).get("heading_rad", 0.0)
    assert abs(placed[0]["hips_m"][0] - want_xz[0]) < 1e-6 and abs(placed[0]["hips_m"][2] - want_xz[1]) < 1e-6
    assert abs(kp.wrap(_fk_heading(placed[0]) - want_h)) < 1e-5
    # 두 키의 상대 궤적 · 높이 · 방향 차는 원천 그대로(강체 한 번)
    src = sorted(keys, key=lambda k: k["frame"])
    d_src = math.dist([src[0]["hips_m"][0], src[0]["hips_m"][2]], [src[1]["hips_m"][0], src[1]["hips_m"][2]])
    d_out = math.dist([placed[0]["hips_m"][0], placed[0]["hips_m"][2]], [placed[1]["hips_m"][0], placed[1]["hips_m"][2]])
    assert abs(d_src - d_out) < 1e-6 and placed[1]["hips_m"][1] == src[1]["hips_m"][1]
    assert abs(kp.wrap((_fk_heading(placed[1]) - _fk_heading(placed[0])) - (src[1]["heading_rad"] - src[0]["heading_rad"]))) < 1e-5
    assert placed[0]["rotvec"]["Spine1"] == src[0]["rotvec"]["Spine1"]


def test_place_anchors_on_the_smooth_root_when_given():
    rng = random.Random(9)
    local, _, pos = kimodo_pose(rng, (0.3, 0.92, -0.4))
    key = {"frame": 0, "rotvec": local, "hips_m": [0.3, 0.92, -0.4], "heading_rad": kp.heading(pos["LeftLeg"], pos["RightLeg"]), "smooth_xz": [0.26, -0.37]}
    placed, rec = kp.place([key], None)
    assert rec["anchor"] == "smooth_root" and placed[0]["smooth_xz"] == [0.0, 0.0]
    # 엉덩은 바닥 루트에서 원래 거리만큼 떨어진 채(돌린 만큼) — Kimodo 정규화(바닥 루트 = 원점)
    assert abs(math.hypot(placed[0]["hips_m"][0], placed[0]["hips_m"][2]) - math.hypot(0.04, -0.03)) < 1e-6
    c = kp.constraint("full", placed, ["Hips"])
    assert c["smooth_root_2d"] == [[0.0, 0.0]]
    assert "smooth_root_2d" not in kp.constraint("full", kp.place([{k: v for k, v in key.items() if k != "smooth_xz"}], None)[0], ["Hips"])


def test_constraint_orders_the_joints_and_zero_fills():
    placed = [{"frame": 3, "rotvec": {"Hips": [0.1, 0, 0], "Spine1": [0, 0.2, 0]}, "hips_m": [0, 0.9, 0]}]
    c = kp.constraint("full", placed, ["Hips", "Jaw", "Spine1"])
    assert c == {"type": "fullbody", "frame_indices": [3], "local_joints_rot": [[[0.1, 0, 0], [0.0, 0.0, 0.0], [0, 0.2, 0]]], "root_positions": [[0, 0.9, 0]]}
    # 손 · 발은 일반 end-effector(후처리가 클래스 이름 마스크로 고정하지 않게 — 8-1)
    assert kp.constraint("right_hand", placed, ["Hips"])["type"] == "end-effector" and kp.constraint("right_hand", placed, ["Hips"])["joint_names"] == ["RightHand"]


def test_two_frame_bvh_and_edit_ops():
    text = soma_bvh(frames=1)
    out = kp.two_frame_bvh(text)
    assert "Frames: 2" in out and out.strip().splitlines()[-1] == out.strip().splitlines()[-2]
    with pytest.raises(kp.KeyPoseError):
        kp.two_frame_bvh("HIERARCHY\nROOT Root\n{\n}\n")
    assert kp.edit_ops([15], 30.0, 41) == ([{"op": "hold_pose", "at": 0.0, "duration": round(1 / 30, 6)}], 0)
    ops, first = kp.edit_ops([250, 290], 30.0, 300)   # 표본 상한(240)을 넘는 원천 — 키 구간만 남긴 뒤 민다
    assert first == 250 and ops[0] == {"op": "trim", "start": round(250 / 30, 6), "end": round(290 / 30, 6)} and ops[1]["op"] == "hold_pose"
    with pytest.raises(kp.KeyPoseError) as e:
        kp.edit_ops([5, 290], 30.0, 300)
    assert e.value.code == "KEY_POSE_SPAN_TOO_LONG"


def test_key_jitter_is_zero_for_smooth_motion():
    smooth = [[i * 1.0, 0.0, 0.0] for i in range(40)]
    zig = [[i * 1.0, (1.0 if i % 2 else -1.0), 0.0] for i in range(40)]
    assert kp.key_jitter([smooth], [20]) == 0.0
    assert kp.key_jitter([zig], [20]) == pytest.approx(4.0)


def make_kimodo_package(venv: pathlib.Path, editable_root: pathlib.Path | None = None) -> pathlib.Path:
    site = venv / "Lib" / "site-packages"
    pkg = (editable_root or site) / "kimodo"
    path = pkg.joinpath(*kp.TPOSE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    path.write_text(soma_bvh(frames=1), encoding="utf-8")
    if editable_root:
        site.mkdir(parents=True, exist_ok=True)
        (site / "__editable___kimodo_1_0_0_finder.py").write_text(f"import sys\nMAPPING: dict[str, str] = {{'kimodo': {str(pkg)!r}}}\n", encoding="utf-8")
    return path


def test_tpose_is_found_in_a_plain_or_editable_install(tmp_path):
    plain = tmp_path / "a" / ".venv"
    want = make_kimodo_package(plain)
    assert kp.tpose_path(plain / "Scripts" / "python.exe") == want
    edit = tmp_path / "b" / ".venv"
    want = make_kimodo_package(edit, editable_root=tmp_path / "b" / "src")
    assert kp.tpose_path(edit / "Scripts" / "python.exe") == want
    assert kp.tpose_path(tmp_path / "none" / "Scripts" / "python.exe") is None


# ---- 요청 · 제약 변환 ----
def _key(**kw) -> dict:
    return {"type": "key_pose", "asset": AIM_IDLE, "times": [0.5], **kw}


def test_request_fills_key_pose_defaults_and_checks_fields(service):
    from anim_gen.request import normalize
    req, _ = normalize(request(prompt="x", generation={"constraints": [_key()]}))
    c = req["generation"]["constraints"][0]
    assert (c["at"], c["part"], c["placement"]) == ([0.5], "full", "auto")
    for bad, field in ((_key(at=[0.1, 0.2]), "at"), (_key(placement="near"), "placement"), (_key(asset="AS_X"), "asset"), (_key(part="head"), "part"),
                       (_key(times=[]), "times")):
        env = service.plan_motion_generation(request=request(prompt="x", generation={"constraints": [bad]}))
        assert not env["ok"] and env["error"]["details"]["field"].endswith(field), bad


def test_constraint_convert_resolves_auto_placement_and_frames():
    specs = kc.convert([_key(times=[0.2, 0.0], at=[1.0, 0.0]), _key(times=[0.5], at=[2.0], placement="origin", part="right_hand")], 30.0, 121)
    assert specs[0]["frame_indices"] == [0, 30] and specs[0]["times"] == [0.0, 0.2] and specs[0]["placement"] == "origin"   # 가장 이른 키가 0
    assert specs[1]["placement"] == "origin" and specs[1]["type"] == "end-effector" and specs[1]["joint_names"] == ["RightHand"]
    assert kc.convert([_key(at=[1.0])], 30.0, 121)[0]["placement"] == "pass1"
    with pytest.raises(kc.ConstraintError) as e:
        kc.convert([_key(times=[0.1, 0.2], at=[1.0, 1.01])], 30.0, 121)
    assert e.value.reason == "DUPLICATE_FRAME"
    with pytest.raises(kc.ConstraintError) as e:
        kc.convert([_key(at=[5.0])], 30.0, 121)
    assert e.value.reason == "CONSTRAINT_OUT_OF_RANGE"


# ---- 계획 ----
@pytest.fixture
def kpa(ka):
    make_kimodo_package(ka.python.parents[1])
    return ka


def plan_with(kpa, constraints, **gen):
    env = kpa.service.plan_motion_generation(request=ai_request(generation={"seed": 7, "constraints": constraints, **gen}))
    assert env["ok"], env["error"]
    return env["result"]


def test_plan_puts_the_key_pose_step_before_generate(kpa):
    p = plan_with(kpa, [_key(at=[1.0])])
    cand = p["candidates"][0]
    steps = [s["step"] for s in cand["steps"]]
    assert steps[:2] == ["key_pose", "generate"] and cand["chain"][0] == "retarget"
    key = cand["steps"][0]["inputs"]
    assert key["items"][0]["source_frames"] == [15] and key["items"][0]["placement"] == "pass1" and key["items"][0]["source_fps"] == 30.0
    assert key["tpose"]["path"].endswith("somaskel77_standard_tpose.bvh") and len(key["tpose"]["sha256"]) == 64
    assert key["align_mode"] == "per_bone" and key["ops"] == "match_existing" and key["source_chains"][0]["name"] == "Spine"
    gen = cand["steps"][1]
    assert "pre_steps" not in gen
    assert gen["inputs"]["key_pose"]["passes"] == 2 and gen["inputs"]["key_pose"]["pass1_items"] == ["generation.constraints[0]"]
    assert gen["inputs"]["key_pose"]["smooth_sigma_frames"] == 1.0   # 키 둘레 떨림 — 8-1 수정안 A 와 같은 σ
    assert gen["inputs"]["timeout_extra_s"] == pytest.approx(25.0)
    codes = {lm["code"] for lm in cand["expected_limitations"]}
    assert {"KEY_POSE_RETARGETED", "KEY_POSE_PLACED", "KEY_POSE_SMOOTHED"} <= codes and "KEY_POSE_RESOLVED_AT_RUN" in cand["risks"]
    # 키가 프레임 0 이면 origin — 한 패스, 기한 그대로
    p0 = plan_with(kpa, [_key(at=[0.0])])
    g0 = p0["candidates"][0]["steps"][1]["inputs"]
    assert g0["key_pose"]["passes"] == 1 and "timeout_extra_s" not in g0


def test_plan_without_key_pose_has_no_key_step(kpa):
    p = plan_with(kpa, [])
    steps = p["candidates"][0]["steps"]
    assert steps[0]["step"] == "generate" and "key_pose" not in steps[0]["inputs"]


def test_key_pose_with_candidates_counts_the_second_pass(kpa):
    p = plan_with(kpa, [_key(at=[1.0])], candidates=3)
    gen = p["candidates"][0]["steps"][1]["inputs"]
    assert gen["diffusions"] == 6 and gen["timeout_extra_s"] == pytest.approx(125.0)


def _excluded(p) -> dict:
    return {e["provider"]: e for e in p["excluded"]}


@pytest.mark.parametrize("constraints, gen, reason", [
    ([_key(asset=KATANA)], {}, "SAMPLE_SKELETON_MISMATCH"),                       # 다른 스켈레톤 — 먼저 리타깃
    ([_key(times=[9.0])], {}, "CONSTRAINT_OUT_OF_RANGE"),                         # 원천 길이(1.33초) 밖
    ([_key(at=[1.0])], {"samples": 2}, "KEY_POSE_WITH_SAMPLES"),
    ([_key(at=[1.0]), _key(times=[0.2], at=[1.0])], {}, "DUPLICATE_FRAME"),       # 두 항목이 같은 생성 프레임
])
def test_plan_blocks_key_pose_it_cannot_run(kpa, constraints, gen, reason):
    p = plan_with(kpa, constraints, **gen)
    assert _excluded(p)["local_ai"]["reason"] == reason


def test_hand_and_foot_keys_may_share_a_frame(kpa):
    p = plan_with(kpa, [_key(at=[1.0], part="right_hand"), _key(at=[1.0], part="left_foot"), _key(at=[1.0], part="right_foot")])
    assert p["executable"] and p["candidates"][0]["steps"][0]["step"] == "key_pose"
    p = plan_with(kpa, [_key(at=[1.0], part="right_hand"), _key(times=[0.2], at=[1.0], part="right_hand")])
    assert _excluded(p)["local_ai"]["reason"] == "DUPLICATE_FRAME"


def test_plan_blocks_without_the_kimodo_t_pose(ka):
    p = plan_with(ka, [_key()])
    assert _excluded(p)["local_ai"]["reason"] == "KEY_POSE_TPOSE_MISSING"


# ---- 실행 ----
SOMA_BONES = [{"name": n, "parent": TREE[n], "ref_component": {"t": [0, 0, 0], "r": [0.0, 0.0, 0.0]}} for n in TREE]


def test_key_pose_step_writes_the_constraint_file_and_kimodo_gets_it(kpa, monkeypatch):
    def fake_blender(ctx, bvh_path, out_dir):
        assert "Frames: 2" in bvh_path.read_text(encoding="utf-8")
        fbx = out_dir / "SOMA_TPose_Rest.fbx"
        fbx.write_bytes(b"fbx")
        return fbx
    monkeypatch.setattr(kp_step, "run_blender", fake_blender)
    kpa.fake.default_bones = SOMA_BONES
    n = 20
    tracks = {b: {"pos": [[0.0, 0.0, 0.0]] * n, "rot": [[0.0, 0.0, 0.0, 1.0]] * n} for b in TREE}
    tracks["Hips"]["pos"] = [[1.0 * i, 2.0, 95.0] for i in range(n)]
    tracks["LeftLeg"]["pos"] = [[10.0, 0.0, 90.0]] * n
    tracks["RightLeg"]["pos"] = [[-10.0, 0.0, 90.0]] * n
    kpa.fake.profiles[f"KP0_{asset_name(AIM_IDLE)}_Hold"] = {"tracks": tracks}
    p = plan_with(kpa, [_key(at=[1.0])])
    env = kpa.service.generate_motion(plan_id=p["plan_id"], save=True)
    job = env["result"]
    assert job["status"] == "RUNNING" and job["stage"] == "generate", job.get("error")
    rec = job["key_pose"]
    path = pathlib.Path(rec["file"])
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["joints"] == [b for b in TREE if b != "Root"] and data["items"][0]["source"] == "generation.constraints[0]"
    track = data["items"][0]["hips_track"]   # 원천 엉덩 궤적(러너가 Kimodo 바닥 루트 매끈화로 smooth_root_2d 를 만든다)
    assert track["first"] == 0 and len(track["m"]) == n and track["m"][15] == [0.15, 0.95, 0.02]
    key = data["items"][0]["keys"][0]
    assert (key["frame"], key["source_frame"]) == (30, 15)
    assert key["hips_m"] == [0.15, 0.95, 0.02]                    # 표본 15(= 원천 프레임 15 — hold 한 프레임) · UE (x, z, y) cm → m
    assert abs(key["heading_rad"]) < 1e-9 and key["rotvec"]["Spine1"] == [0.0, 0.0, 0.0]
    item = rec["items"][0]
    assert item["edit_ops"][0]["op"] == "hold_pose" and item["held_asset"].endswith("_Hold") and item["placement"] == "pass1"
    args = kpa.launcher.of(KimodoProc)[-1].args
    assert args["key_pose_file"] == path.as_posix() and args["key_pose_smooth"] == 1.0
    assert args["constraints"][0]["kind"] == "key_pose" and args["constraints"][0]["placement"] == "pass1"
    # 리그 · 역 RTG 는 Work/KeyPose 에 — 대상 → SOMA
    rtg = next(prm for tool, prm in kpa.fake.calls if tool == "create_ik_retargeter")
    assert rtg["source_mesh"].endswith("SK_StreetDemon_F_01") and "/KeyPose/" in rtg["asset_path"] and rtg["align_mode"] == "per_bone"
    rev = [prm for tool, prm in kpa.fake.calls if tool == "retarget_animations"]
    assert len(rev) == 1 and rev[0]["assets"] == [AIM_IDLE] and rev[0]["validate"] is False and rev[0]["output_path"].endswith("/KeyPose")


def test_key_pose_file_changed_after_the_step_stops_generate(kpa, monkeypatch):
    def fake_blender(ctx, bvh_path, out_dir):
        fbx = out_dir / "SOMA_TPose_Rest.fbx"
        fbx.write_bytes(b"fbx")
        return fbx
    real_run = kp_step.run

    def tamper(ctx):
        result = real_run(ctx)
        pathlib.Path(result.values["key_pose"]["file"]).write_text("{}", encoding="utf-8")
        return result
    monkeypatch.setattr(kp_step, "run_blender", fake_blender)
    monkeypatch.setattr(kp_step, "run", tamper)
    kpa.fake.default_bones = SOMA_BONES
    n = 20
    kpa.fake.profiles[f"KP0_{asset_name(AIM_IDLE)}_Hold"] = {"tracks": {b: {"pos": [[0.0, 0.0, 90.0]] * n, "rot": [[0.0, 0.0, 0.0, 1.0]] * n}
                                                                         for b in TREE}}
    p = plan_with(kpa, [_key(at=[0.0])])
    env = kpa.service.generate_motion(plan_id=p["plan_id"], save=True)
    job = env["result"] if env["ok"] else env["error"]["details"]["job"]
    assert job["status"] == "FAILED" and job["error"]["reason"] == "KEY_POSE_FILE_MISSING"
