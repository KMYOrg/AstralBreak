"""local_ai Provider (지침서 §14 Phase 5) — Kimodo · Blender 서브프로세스는 가짜 실행기 · 가짜 시계로 대신한다(모델을 띄우지 않는다).

계획(사슬 · 고정 값 · 제외 사유) · 실행(오프라인 환경 · 인자 · 샘플 고르기 · blender 변환 이어 가기 · SOMA 체인 · 소스 골반 재검증) ·
실패(report 오류 → 폴백 · 타임아웃 · 취소 · 파일 변경) · 제약 변환 · 루트 트랙 계산 · 요청 검증.
"""
from __future__ import annotations

import json
import math
import pathlib
import random
import types

import pytest

from anim_gen.local_ai import constraints as kc
from anim_gen.local_ai import root_track as rt
from anim_gen.providers.blender import BlenderProvider
from anim_gen.providers.local_ai import REQUIRED_REPOS, RUNNER, SOMA_CHAINS, KimodoProvider
from conftest import AIM_IDLE, OUT, VESPER_MESH, err, request
from test_blender import FakeClock, FakeProc

FINAL = f"{OUT}/AS_Vesper_Kimodo_WalkTurn"
_ROT = "CHANNELS 3 Zrotation Yrotation Xrotation"
_SIX = "CHANNELS 6 Xposition Yposition Zposition Zrotation Yrotation Xrotation"


def soma_bvh(frames: int = 181, joints: int = 78, toe_z: float = 12.0) -> str:
    """Kimodo 표준 T 포즈 BVH 와 같은 뼈대 — ROOT Root(원점) → Hips(위치 6채널) → 다리 · 척추, 관절 수를 joints 로 채운다(cm, +Z 정면)."""
    def leg(side: str, x: float) -> str:
        return (f"JOINT {side}Leg\n{{\nOFFSET {x} -5 0\n{_ROT}\nJOINT {side}Shin\n{{\nOFFSET 0 -45 0\n{_ROT}\nJOINT {side}Foot\n{{\nOFFSET 0 -45 0\n"
                f"{_ROT}\nJOINT {side}ToeBase\n{{\nOFFSET 0 -5 {toe_z}\n{_ROT}\n}}\n}}\n}}\n}}\n")
    fixed = 2 + 8 + 2  # Root · Hips · 다리 4×2 · Spine1 · Head
    filler = "".join(f"JOINT Extra{i}\n{{\nOFFSET 0 0.1 0\n{_ROT}\n" for i in range(joints - fixed)) + "}\n" * (joints - fixed)
    body = (f"HIERARCHY\nROOT Root\n{{\nOFFSET 0 0 0\n{_SIX}\nJOINT Hips\n{{\nOFFSET 0 100 0\n{_SIX}\n" + leg("Left", 10) + leg("Right", -10)
            + f"JOINT Spine1\n{{\nOFFSET 0 10 0\n{_ROT}\nJOINT Head\n{{\nOFFSET 0 60 0\n{_ROT}\n{filler}}}\n}}\n}}\n}}\n")
    channels = 12 + 3 * (joints - 2)
    row = " ".join(["0"] * channels)
    return f"{body}MOTION\nFrames: {frames}\nFrame Time: 0.03333333\n" + "\n".join([row] * frames) + "\n"


class KimodoProc(FakeProc):
    """Kimodo 실행 스크립트 자리. complete() 가 kimodo_run.py 처럼 샘플 NPZ · BVH · report · 로그를 쓴다."""

    bvh_text = None  # 테스트가 바꾸면 그 BVH 를 쓴다

    def complete(self, kind: str = "ok") -> None:
        out = pathlib.Path(self.args["out_dir"])
        (out / "kimodo.log").write_text("Using device: cuda:0\nkimodo_run: done\n", encoding="utf-8")
        samples = []
        seeds = self.args.get("seeds") if self.args.get("candidates_mode") else None
        for i in range(len(seeds) if seeds else self.args["samples"]):
            stem = out / f"{self.args['stem']}_{i:02d}"
            stem.with_suffix(".npz").write_bytes(b"npz")
            if kind != "no_bvh":
                stem.with_suffix(".bvh").write_text(self.bvh_text or soma_bvh(self.args["frames"]), encoding="utf-8")
            sample = {"index": i, "npz": stem.with_suffix(".npz").as_posix(), "bvh": stem.with_suffix(".bvh").as_posix(),
                      "frames": self.args["frames"], "root": {"root_travel_cm": 900.0, "heading_delta_deg": 179.0}}
            if seeds:
                # kimodo_run 후보 경로 — 소스 수치(1 · 2차) · 제약 추종
                two = self.args["refine"]["passes"] == 2
                m1 = {"version": 1, "grip": {"grip_pct": 0.0, "gap_cm": {"p50": 64.6}}, "stance": {"lateral_ratio": {"p90": 4.81}}, "swing": {"peak_cm_s": 542.8}}
                sample.update(seed=seeds[i], metrics={"pass1": m1, **({"pass2": {**m1, "grip": {"grip_pct": 100.0, "gap_cm": {"p50": 7.6}}}} if two else {})})
                if two:
                    flags = self.args["refine"]["flags"]
                    sample["pass1_npz"] = stem.with_name(stem.name + "_pass1.npz").as_posix()
                    sample["refine"] = {"fk_check_m": 0.0, "constraints": [{"type": "end-effector", "joint_names": ["LeftHand", "RightHand"], "frames": 41}],
                                        "follow": {"grip_target_error_cm": {"lead": {"p50": 2.5, "max": 6.4}}, "foot_hold_left_cm": {"p50": 2.6, "max": 3.0}},
                                        **({"grip": {"target": "meet", "spacing_cm": 6.96, "stats": {"moved_cm": {"p50": 31.2}}}}
                                           if "two_hand_weapon_grip" in flags else {}),
                                        **({"foot": {"left": {"frames": [0, 3], "contact_pct": 86.8}}} if "foot_contact" in flags else {})}
            samples.append(sample)
        report = {"ok": True, "samples": samples, "warnings": [], "device": {"gpu": "Fake 3080 Ti"}, "postprocess": {"applied": self.args["postprocess"]},
                  "model": {"name": self.args["model"], "commit": "abc"}, "seconds": {"total": 33.0}}
        code = 0
        if kind == "error":
            report, code = {"ok": False, "samples": [], "warnings": [], "error": {"code": "CONSTRAINT_OUT_OF_RANGE", "message": "frame 999"}}, 2
        if kind != "crash":
            pathlib.Path(self.args["report"]).write_text(json.dumps(report), encoding="utf-8")
        else:
            code = 3
        self.returncode = code


class Launcher:
    def __init__(self):
        self.procs: list[FakeProc] = []

    def __call__(self, cmd, **kwargs):
        cls = KimodoProc if str(RUNNER) in cmd else FakeProc
        proc = cls(cmd, kwargs, pid=5000 + len(self.procs))
        self.procs.append(proc)
        return proc

    def of(self, cls) -> list[FakeProc]:
        return [p for p in self.procs if type(p) is cls]


@pytest.fixture
def ka(make_service, fake, tmp_path):
    """가짜 Kimodo venv(python · motion_correction) · 오프라인 캐시(refs/main) · 가짜 Blender · ImportSourceRoots(tmp)."""
    roots = tmp_path / "Import"
    (roots / "Sources").mkdir(parents=True)
    fake.import_roots = [roots.as_posix() + "/"]
    venv = tmp_path / "Kimodo" / ".venv"
    python = venv / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("fake", encoding="utf-8")
    mc = venv / "Lib" / "site-packages" / "motion_correction"
    mc.mkdir(parents=True)
    (mc / "__init__.py").write_text("", encoding="utf-8")
    (mc / "_motion_correction.cp313-win_amd64.pyd").write_bytes(b"pyd")
    cache = tmp_path / "Kimodo" / "hf_cache"
    for repo in REQUIRED_REPOS:
        ref = cache / ("models--" + repo.replace("/", "--")) / "refs" / "main"
        ref.parent.mkdir(parents=True)
        ref.write_text("0e3c890" if repo.startswith("nvidia") else "c0ffee", encoding="utf-8")
    exe = tmp_path / "Blender" / "blender.exe"
    exe.parent.mkdir()
    exe.write_text("fake", encoding="utf-8")
    launcher, clock = Launcher(), FakeClock()

    def make(**replace):
        service, registry = make_service(
            blender=lambda reg: BlenderProvider(reg.get("blender").manifest, popen=launcher, clock=clock),
            local_ai=lambda reg: KimodoProvider(reg.get("local_ai").manifest, popen=launcher, clock=clock), **replace)
        env = service.set_generation_policy(patch={"paths": {"blender_executable": exe.as_posix(), "kimodo_python": python.as_posix(),
                                                             "kimodo_hf_cache": cache.as_posix()}})
        assert env["ok"], env
        return service, registry

    service, registry = make()
    return types.SimpleNamespace(service=service, registry=registry, launcher=launcher, clock=clock, roots=roots, fake=fake, tmp=tmp_path,
                                 python=python, cache=cache, exe=exe, mc=mc)


def ai_request(**overrides) -> dict:
    base = {"animation_name": "AS_Vesper_Kimodo_WalkTurn", "family": "Kimodo", "motion_category": "full_body_new", "loop": False, "search": ...,
            "edits": ..., "target_mesh": VESPER_MESH, "description": "걷다가 돌아서 되돌아온다", "duration_seconds": 6.0, "frame_rate": 30,
            "prompt": "A person walks forward, turns around and walks back.", "generation": {"seed": 7}}
    base.update(overrides)
    return request(**base)


def plan(ka, **overrides) -> dict:
    env = ka.service.plan_motion_generation(request=ai_request(**overrides))
    assert env["ok"], env["error"]
    return env["result"]


def run_to_end(ka, p: dict, kimodo: str = "ok", blender: str = "ok", save: bool = True) -> dict:
    env = ka.service.generate_motion(plan_id=p["plan_id"], save=save)
    job = env["result"] if env["ok"] else env["error"]["details"]["job"]
    if job["status"] != "RUNNING":
        return job
    ka.launcher.of(KimodoProc)[-1].complete(kimodo)
    job = status(ka, job["job_id"])
    if job["status"] == "RUNNING" and job["stage"] == "convert":
        ka.launcher.of(FakeProc)[-1].complete(blender)
        job = status(ka, job["job_id"])
    return job


def status(ka, job_id: str) -> dict:
    env = ka.service.get_generation_status(job_id=job_id)
    return env["result"] if env["ok"] else env["error"]["details"].get("job", env["error"])


# ---- 계획 ----
def test_plan_chains_generate_convert_import_retarget_and_runs_nothing(ka):
    p = plan(ka)
    assert p["order"][0] == "local_ai" and p["executable"]
    cand = p["candidates"][0]
    assert cand["provider"] == "local_ai" and cand["chain"] == ["local_ai", "blender", "retarget"]
    gen, convert, imp, retarget, validate = cand["steps"]
    g = gen["inputs"]
    assert (g["model"], g["model_commit"], g["frames"], g["fps"], g["seed"], g["samples"], g["pick"], g["steps"], g["postprocess"]) == \
        ("kimodo-soma-rp-v1.2", "0e3c890", 181, 30.0, 7, 1, 0, 100, True)  # 6초 = 180 구간 + 1 프레임
    assert convert["inputs"]["from_step"] == "generate" and convert["inputs"]["unit"] == "cm" and convert["resolved"] is None
    assert convert["expected"] == {"unit": "cm", "facing": "+Y", "joints": 78, "fps": 30.0, "frames": 181}
    assert imp["inputs"]["sample_rate"] is None  # 생성 fps(30) = 요청 → 리샘플 안 함
    ri = retarget["inputs"]
    assert ri["source_pelvis"] == "Hips" and ri["source_chains"] == SOMA_CHAINS and ri["source_feet"] == ["LeftFoot", "RightFoot"]
    assert ri["defaults_from"] == {"provider": "local_ai", "keys": ["source_pelvis", "source_chains", "source_feet"]}
    assert ri["facing"]["mode"] == "converted" and validate["step"] == "validate"
    assert {"TEXT_ENCODER_CPU", "CONVERT_RESOLVED_AT_RUN"} <= set(cand["risks"])
    codes = {lim["code"] for lim in cand["expected_limitations"]}
    assert "FINGERS_STATIC" in codes and "POSTPROCESS_OFF" not in codes and "DURATION_MISMATCH" not in codes
    assert not ka.launcher.procs and not ka.fake.writes


def test_soma_chains_map_every_finger_by_standard_name():
    """손 체인 18개 — 엔진 표준 이름(FCharacterizationStandard)으로 엄지 Thumb1~3 · 메타카팔 Hand{F}1 · 손가락 Hand{F}2~4, End 와 IK 골은 없다."""
    by_name = {c["name"]: c for c in SOMA_CHAINS}
    assert len(SOMA_CHAINS) == len(by_name) == 9 + 18
    for side in ("Left", "Right"):
        assert (by_name[f"{side}Thumb"]["start"], by_name[f"{side}Thumb"]["end"]) == (f"{side}HandThumb1", f"{side}HandThumb3")
        for finger in ("Index", "Middle", "Ring", "Pinky"):
            mc, chain = by_name[f"{side}{finger}Metacarpal"], by_name[f"{side}{finger}"]
            assert mc["start"] == mc["end"] == f"{side}Hand{finger}1"
            assert (chain["start"], chain["end"]) == (f"{side}Hand{finger}2", f"{side}Hand{finger}4")
    assert not any("End" in c["start"] + c["end"] or c.get("goal") for c in SOMA_CHAINS[9:])


def test_request_chains_override_the_provider_defaults(ka):
    mine = [{"name": "LeftLeg", "start": "LeftLeg", "end": "LeftFoot"}]
    ri = plan(ka, retarget={"source_chains": mine})["candidates"][0]["steps"][3]["inputs"]
    assert ri["source_chains"] == mine and ri["source_pelvis"] == "Hips" and ri["defaults_from"]["keys"] == ["source_pelvis", "source_feet"]


def test_seed_is_pinned_when_absent(ka):
    p = plan(ka, generation={})
    seed = p["candidates"][0]["steps"][0]["inputs"]["seed"]
    assert isinstance(seed, int) and "SEED_PINNED" in {d["code"] for d in p["diagnostics"]}


def test_frame_rate_other_than_30_resamples_from_the_run_values(ka):
    p = plan(ka, frame_rate=60)
    assert p["candidates"][0]["steps"][2]["inputs"]["sample_rate"] == 60
    job = run_to_end(ka, p)
    assert job["status"] == "SUCCEEDED", job.get("error")
    rest, imp = [q for t, q in ka.fake.calls if t == "import_animation_file"]  # 기준 포즈 FBX → 그 스켈레톤에 동작
    assert imp["sample_rate"] == 60 and imp["skeleton"] and rest["file"].endswith("_Rest.fbx")


@pytest.mark.parametrize("overrides, cause, reason", [
    ({"prompt": None}, "UNSUPPORTED_REQUEST", "MISSING_INPUT"),
    ({"duration_seconds": 12.0}, "UNSUPPORTED_REQUEST", "DURATION_OVER_MAX"),
    ({"generation": {"postprocess": "on"}}, "UNSUPPORTED_REQUEST", "POSTPROCESS_UNAVAILABLE"),
    ({"generation": {"constraints": [{"type": "root_path", "points": [{"t": 7.0, "forward_cm": 0, "left_cm": 0}]}]}},
     "UNSUPPORTED_REQUEST", "CONSTRAINT_OUT_OF_RANGE"),
])
def test_local_ai_exclusions(ka, overrides, cause, reason):
    if reason == "POSTPROCESS_UNAVAILABLE":
        for f in ka.mc.iterdir():
            f.unlink()
    p = plan(ka, **overrides)
    assert {e["provider"]: (e["cause"], e["reason"]) for e in p["excluded"]}["local_ai"] == (cause, reason)


def test_not_installed_and_blender_dependency(ka):
    (ka.cache / "models--meta-llama--Meta-Llama-3-8B-Instruct" / "refs" / "main").unlink()
    ex = {e["provider"]: e for e in plan(ka)["excluded"]}["local_ai"]
    assert (ex["cause"], ex["reason"]) == ("PROVIDER_UNAVAILABLE", "NOT_INSTALLED") and "Meta-Llama-3-8B-Instruct" in ex["state"]["install_note"]
    (ka.cache / "models--meta-llama--Meta-Llama-3-8B-Instruct" / "refs" / "main").write_text("c0ffee", encoding="utf-8")
    ka.exe.unlink()
    ex = {e["provider"]: e for e in plan(ka)["excluded"]}["local_ai"]
    assert (ex["cause"], ex["reason"]) == ("PROVIDER_UNAVAILABLE", "DEPENDS_ON_BLENDER")


def test_postprocess_off_is_an_expected_limitation(ka):
    cand = plan(ka, generation={"postprocess": "off"})["candidates"][0]
    assert cand["steps"][0]["inputs"]["postprocess"] is False and "POSTPROCESS_OFF" in {lim["code"] for lim in cand["expected_limitations"]}


# ---- 실행 ----
def test_success_runs_kimodo_offline_then_blender_then_retargets(ka, monkeypatch):
    monkeypatch.setenv("MESHY_API_KEY", "sk-SENTINEL-KIMODO")
    monkeypatch.setenv("HF_TOKEN", "hf_SENTINEL")
    p = plan(ka, generation={"seed": 7, "constraints": [{"type": "root_path", "points": [{"t": 0, "forward_cm": 0, "left_cm": 0},
                                                                                         {"t": 3.0, "forward_cm": 400, "left_cm": 0, "yaw_deg": 180}]}]})
    env = ka.service.generate_motion(plan_id=p["plan_id"], save=True)
    job = env["result"]
    assert env["ok"] and job["status"] == "RUNNING" and job["stage"] == "generate"
    [proc] = ka.launcher.of(KimodoProc)
    assert proc.cmd[:3] == [str(ka.python), "-I", str(RUNNER)] and proc.cmd[3].endswith("args.json")
    environ = proc.kwargs["env"]
    assert (environ["HF_HUB_OFFLINE"], environ["LOCAL_CACHE"], environ["TEXT_ENCODER_DEVICE"], environ["TEXT_ENCODER_MODE"]) == ("1", "true", "cpu", "local")
    assert environ["HF_HUB_CACHE"] == str(ka.cache) and "MESHY_API_KEY" not in environ and "HF_TOKEN" not in environ
    a = proc.args
    assert (a["prompt"], a["frames"], a["seed"], a["samples"], a["root_track"], a["postprocess"]) == (p["request"]["prompt"], 181, 7, 1, True, True)
    [c] = a["constraints"]
    assert c["kind"] == "kimodo" and [i["frame_indices"] for i in c["items"]] == [[0], [90]]
    assert c["items"][1]["global_root_heading"][0] == pytest.approx([-1.0, 0.0], abs=1e-9) and c["items"][1]["smooth_root_2d"] == [[0.0, 4.0]]
    assert pathlib.Path(a["out_dir"]) == ka.roots / "LocalAI" / job["job_id"] / "A1"
    assert status(ka, job["job_id"])["status"] == "RUNNING" and not ka.launcher.of(FakeProc)  # 아직 생성 중

    proc.complete("ok")
    job = status(ka, job["job_id"])
    assert job["status"] == "RUNNING" and job["stage"] == "convert"
    [blender] = ka.launcher.of(FakeProc)
    assert blender.args["bvh"] == f"{a['out_dir']}/kimodo_00.bvh" and blender.args["cm_per_unit"] == 1.0 and blender.args["rotate_z_deg"] == 0.0
    blender.complete("ok")
    job = status(ka, job["job_id"])
    assert job["status"] == "SUCCEEDED", job.get("error")
    assert job["chain"] == ["local_ai", "blender", "retarget"] and job["generated_assets"] == [FINAL]
    [(_, rig)] = [(t, q) for t, q in ka.fake.calls if t == "create_ik_rig" and q["asset_path"].endswith("IK_Source")]
    assert rig["mode"] == "manual" and rig["pelvis"] == "Hips" and rig["chains"] == SOMA_CHAINS
    [(_, val)] = [(t, q) for t, q in ka.fake.calls if t == "validate_animation"]
    assert val["source_pelvis"] == "Hips" and val["source_feet"] == ["LeftFoot", "RightFoot"] and val["sources"][0].endswith("/Import/Motion/Mock_Anim")
    # 재검증도 팔-몸통 관통을 잰다 — 보정(retarget_animations resolve)과 같은 대상 메시 · 대상 IK Rig
    assert val["body_clearance"]["mesh"] == VESPER_MESH and val["body_clearance"]["ik_rig"].endswith("/IK_Target")
    # 손가락 검사도 내장 검증과 같은 리타기터 매핑으로 (매핑 안 된 손가락 = 기준 포즈 · 굽힘 방향 · 끝 순서)
    assert val["fingers"]["retargeter"].endswith("/RTG_Retarget")
    [(_, rt)] = [(t, q) for t, q in ka.fake.calls if t == "retarget_animations"]
    assert rt["body_clearance"] == "resolve"
    codes = {d["code"] for d in job["diagnostics"]}
    assert {"KIMODO_GENERATED", "BLENDER_CONVERTED", "VALIDATED_WITH_SOURCE_PELVIS", "BODY_CLEARANCE_RESOLVED"} <= codes and "GENERATED_BVH_UNEXPECTED" not in codes
    assert "FINGERS_STATIC" in {lim["code"] for lim in job["limitations"]}
    generated = job["cursor"]["values"]["generated"]
    assert generated["pick"] == 0 and generated["root"]["root_travel_cm"] == 900.0
    assert "sk-SENTINEL-KIMODO" not in json.dumps(job) and "hf_SENTINEL" not in json.dumps(job)


def test_samples_and_pick(ka):
    job = run_to_end(ka, plan(ka, generation={"seed": 1, "samples": 3, "pick": 2}))
    assert job["status"] == "SUCCEEDED", job.get("error")
    assert ka.launcher.of(FakeProc)[-1].args["bvh"].endswith("kimodo_02.bvh")
    [d] = [d for d in job["diagnostics"] if d["code"] == "KIMODO_GENERATED"]
    assert [f["index"] for f in d["files"]] == [0, 1, 2]


def test_unexpected_bvh_layout_is_a_warning(ka):
    KimodoProc.bvh_text = soma_bvh(181, joints=20)
    try:
        job = run_to_end(ka, plan(ka))
    finally:
        KimodoProc.bvh_text = None
    assert job["status"] == "SUCCEEDED"
    [d] = [d for d in job["diagnostics"] if d["code"] == "GENERATED_BVH_UNEXPECTED"]
    assert "20 joints (expected 78)" in d["message"]


def test_kimodo_error_falls_back_and_records_it(ka):
    job = run_to_end(ka, plan(ka, search={"query": "rifle aim idle"}), kimodo="error")
    assert job["status"] == "SUCCEEDED" and job["provider"] == "existing_motion" and job["reused_assets"] == [AIM_IDLE]
    [h] = job["fallback_history"]
    assert (h["provider"], h["step"], h["cause"], h["reason"]) == ("local_ai", "generate", "GENERATION_FAILED", "CONSTRAINT_OUT_OF_RANGE")
    assert "kimodo.log" in h["message"] and not ka.launcher.of(FakeProc)
    used = {lim["code"]: lim for lim in job["limitations"]}
    assert used["FALLBACK_USED"]["from"] == "local_ai" and "NOT_NEW_MOTION" in used


@pytest.mark.parametrize("kind, reason", [("crash", "KIMODO_EXIT_3"), ("no_bvh", "NO_OUTPUT")])
def test_exit_without_report_or_bvh_fails(ka, kind, reason):
    job = run_to_end(ka, plan(ka, provider="local_ai"), kimodo=kind)
    assert job["status"] == "FAILED" and job["error"]["reason"] == reason and not ka.fake.writes


def test_timeout_and_cancel_stop_the_process(ka):
    ka.service.set_generation_policy(patch={"execution": {"subprocess_timeout_seconds": 60}})
    env = ka.service.generate_motion(plan_id=plan(ka, provider="local_ai")["plan_id"])
    proc = ka.launcher.of(KimodoProc)[-1]
    ka.clock.t += 61
    job = status(ka, env["result"]["job_id"])
    assert proc.killed and job["status"] == "FAILED" and job["error"]["reason"] == "TIMEOUT" and "Kimodo ran over 60s" in job["error"]["message"]
    env = ka.service.generate_motion(plan_id=plan(ka, animation_name="AS_Vesper_Kimodo_WalkTurnB")["plan_id"])
    proc = ka.launcher.of(KimodoProc)[-1]
    job = ka.service.cancel_generation(job_id=env["result"]["job_id"])["result"]
    assert job["status"] == "CANCELLED" and proc.killed and job["cancel_effect"] == {"stopped": True, "pid": proc.pid}


# ---- 제약 파일 ----
def test_keep_pose_file_is_pinned_and_checked(ka):
    npz = ka.roots / "Sources" / "prev.npz"
    npz.write_bytes(b"npz-1")
    p = plan(ka, generation={"seed": 3, "constraints": [{"type": "keep_pose", "npz": npz.as_posix(), "times": [1.0, 0.0, 1.0], "part": "right_hand"}]})
    gen = p["candidates"][0]["steps"][0]["inputs"]
    assert gen["constraints"] == [{"kind": "keep_pose", "source": "generation.constraints[0]", "npz": npz.as_posix(), "type": "right-hand",
                                   "frame_indices": [0, 30]}]
    assert gen["constraint_files"][0]["path"] == npz.as_posix() and len(gen["constraint_files"][0]["sha256"]) == 64
    npz.write_bytes(b"npz-2")
    env = ka.service.generate_motion(plan_id=p["plan_id"])
    assert env["error"]["code"] == "UNSUPPORTED_REQUEST" and env["error"]["details"]["reason"] == "FILE_CHANGED" and not ka.launcher.procs


def test_constraint_file_outside_import_roots_is_refused(ka):
    outside = ka.tmp / "elsewhere.npz"
    outside.write_bytes(b"npz")
    env = ka.service.plan_motion_generation(request=ai_request(generation={"constraints": [{"type": "keep_pose", "npz": outside.as_posix(),
                                                                                           "times": [0]}]}))
    assert env["error"]["code"] == "IMPORT_SOURCE_NOT_ALLOWED"


@pytest.mark.parametrize("content, reason", [
    ("not json", "BAD_RAW_CONSTRAINTS"),
    (json.dumps([{"type": "teleport", "frame_indices": [0]}]), "BAD_RAW_CONSTRAINTS"),
    (json.dumps([{"type": "root2d", "frame_indices": [0, 500], "smooth_root_2d": [[0, 0], [1, 1]]}]), "CONSTRAINT_OUT_OF_RANGE"),
])
def test_kimodo_raw_is_checked_at_plan(ka, content, reason):
    raw = ka.roots / "Sources" / "constraints.json"
    raw.write_text(content, encoding="utf-8")
    p = plan(ka, generation={"constraints": [{"type": "kimodo_raw", "path": raw.as_posix()}]})
    assert {e["provider"]: e["reason"] for e in p["excluded"]}["local_ai"] == reason


@pytest.mark.parametrize("generation, field", [
    ({"temperature": 1}, "generation.temperature"),
    ({"samples": 5}, "generation.samples"),
    ({"samples": 2, "pick": 2}, "generation.pick"),
    ({"postprocess": "maybe"}, "generation.postprocess"),
    ({"constraints": [{"type": "root_path", "points": [{"t": -1, "forward_cm": 0, "left_cm": 0}]}]}, "generation.constraints[0].points[0]"),
    ({"constraints": [{"type": "keep_pose", "npz": "prev.npz", "times": [0]}]}, "generation.constraints[0].npz"),
    ({"constraints": [{"type": "keep_pose", "npz": "D:/x.npz", "times": [0], "part": "tail"}]}, "generation.constraints[0].part"),
    ({"constraints": [{"type": "magic"}]}, "generation.constraints[0]"),
])
def test_generation_validation(ka, generation, field):
    env = ka.service.plan_motion_generation(request=ai_request(generation=generation))
    assert env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["field"] == field


def test_prompt_validation(ka):
    env = ka.service.plan_motion_generation(request=ai_request(prompt="x" * 501))
    assert env["error"]["details"]["field"] == "prompt"


def test_revalidation_failure_keeps_the_retarget_validation(ka):
    ka.fake.fail["validate_animation"] = [err("TIMEOUT_INTERNAL")]
    job = run_to_end(ka, plan(ka))
    assert job["status"] == "SUCCEEDED" and job["validation"]["status"] == "PASSED_WITH_WARNINGS"
    assert "REVALIDATE_FAILED" in {d["code"] for d in job["diagnostics"]}


# ---- 순수 모듈 ----
def test_root_path_conversion_is_character_relative():
    items = kc.root_path_items([{"t": 1.0, "forward_cm": 200, "left_cm": -50}, {"t": 0, "forward_cm": 0, "left_cm": 0},
                                {"t": 2.0, "forward_cm": 300, "left_cm": 100, "yaw_deg": 90}], 30.0, 91, "c")
    plain, turned = items
    assert plain == {"type": "root2d", "frame_indices": [0, 30], "smooth_root_2d": [[0.0, 0.0], [-0.5, 2.0]]}
    assert turned["frame_indices"] == [60] and turned["smooth_root_2d"] == [[1.0, 3.0]]
    assert turned["global_root_heading"][0] == pytest.approx([0.0, 1.0], abs=1e-9)  # 왼쪽으로 90° = θ +90° → (cos, sin) = (0, 1)
    with pytest.raises(kc.ConstraintError) as e:
        kc.root_path_items([{"t": 0, "forward_cm": 0, "left_cm": 0}, {"t": 0.01, "forward_cm": 1, "left_cm": 0}], 30.0, 10, "c")
    assert e.value.reason == "DUPLICATE_FRAME"


def test_euler_round_trip():
    rnd = random.Random(5)
    for _ in range(200):
        z, y, x = rnd.uniform(-179, 179), rnd.uniform(-85, 85), rnd.uniform(-179, 179)
        back = rt.euler_zyx_to_matrix(*rt.matrix_to_euler_zyx(rt.euler_zyx_to_matrix(z, y, x)))
        want = rt.euler_zyx_to_matrix(z, y, x)
        assert all(abs(back[i][j] - want[i][j]) < 1e-9 for i in range(3) for j in range(3))


def test_heading_is_unwrapped():
    pairs = [[math.cos(math.radians(a)), math.sin(math.radians(a))] for a in (170, -170, -100)]
    assert rt.heading_deg(pairs) == pytest.approx([170.0, 190.0, 260.0])


def _rows(text: str) -> list[list[float]]:
    lines = text.split("MOTION")[1].strip().splitlines()[2:]
    return [list(map(float, ln.split())) for ln in lines]


def test_root_track_keeps_the_world_pose():
    """Root 에 궤적 · 방향을 넣어도 Hips 의 전역 위치 · 회전은 그대로다(Root ∘ Hips′ = 원래 Hips)."""
    frames = 4
    text = soma_bvh(frames, joints=14)
    head, _, _ = text.partition("MOTION")
    rnd = random.Random(9)
    world = []
    rows = []
    for _ in range(frames):
        pos, rot = [rnd.uniform(-50, 50), rnd.uniform(80, 100), rnd.uniform(-50, 300)], [rnd.uniform(-30, 30) for _ in range(3)]
        world.append((pos, rot))
        rows.append(" ".join(["0"] * 6 + [f"{v:.6f}" for v in pos + rot] + ["1.5"] * (3 * 12)))
    text = f"{head}MOTION\nFrames: {frames}\nFrame Time: 0.03333333\n" + "\n".join(rows) + "\n"
    xz = [(world[i][0][0] + 1.0, world[i][0][2] - 2.0) for i in range(frames)]
    heading = [0.0, 45.0, 120.0, 181.0]
    out, stats = rt.apply_root_track(text, xz, heading)
    assert stats["frames"] == frames and stats["heading_delta_deg"] == 181.0 and stats["root_travel_cm"] > 0
    for i, row in enumerate(_rows(out)):
        assert row[0:6] == pytest.approx([xz[i][0], 0.0, xz[i][1], 0.0, heading[i], 0.0], abs=1e-6)
        assert row[12:] == [1.5] * 36  # 나머지 관절 채널은 그대로
        root_rot = rt.euler_zyx_to_matrix(row[3], row[4], row[5])
        pos = [row[k] + v for k, v in enumerate(rt.apply(root_rot, row[6:9]))]
        rot = rt.matmul(root_rot, rt.euler_zyx_to_matrix(*row[9:12]))
        want = rt.euler_zyx_to_matrix(*world[i][1])
        assert pos == pytest.approx(world[i][0], abs=1e-4)
        assert all(abs(rot[r][c] - want[r][c]) < 1e-5 for r in range(3) for c in range(3))


def test_root_track_rejects_other_layouts():
    from conftest import make_bvh
    with pytest.raises(rt.RootTrackError) as e:
        rt.apply_root_track(make_bvh(frames=2), [(0, 0)] * 2, [0, 0])
    assert e.value.code == "UNEXPECTED_HIERARCHY"
    with pytest.raises(rt.RootTrackError) as e:
        rt.apply_root_track(soma_bvh(3, joints=14), [(0, 0)] * 2, [0, 0])
    assert e.value.code == "FRAME_COUNT_MISMATCH"


def test_policy_paths_are_validated(ka):
    env = ka.service.set_generation_policy(patch={"paths": {"kimodo_python": 3}})
    assert env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["reason"] == "BAD_VALUE"
