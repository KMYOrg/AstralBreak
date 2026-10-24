"""blender Provider (지침서 §14 Phase 4) — Blender 서브프로세스는 가짜 실행기 · 가짜 시계로 대신한다(진짜 Blender 를 띄우지 않는다).

실행 파일 없음 · 성공(비동기 poll) · 실패(report 오류 · 보고 없이 종료 · FBX 없음) · 타임아웃 · 취소 · 서버 재시작 · 파일 변경 ·
폴백 기록 · 라우터 순서 · 요청 검증.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import types

import pytest

from anim_gen.providers.blender import SCRIPT, BlenderProvider
from anim_gen.service import Service
from anim_gen.store import Store
from conftest import AIM_IDLE, OUT, VESPER_MESH, make_bvh, request

FINAL = f"{OUT}/AS_Vesper_Mocap_WalkP4"


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeProc:
    """Blender 프로세스 자리. complete() 가 bvh_to_fbx.py 처럼 report · FBX · 로그를 쓴다."""

    def __init__(self, cmd, kwargs, pid):
        self.cmd, self.kwargs, self.pid = cmd, kwargs, pid
        self.returncode = None
        self.killed = False
        self.polls = 0
        self.args = json.loads(pathlib.Path(cmd[-1]).read_text(encoding="utf-8"))

    def poll(self):
        self.polls += 1
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode

    def complete(self, kind: str = "ok") -> None:
        report = {"ok": True, "blender": "4.4.1", "bones": 11, "roots": ["Hips"], "rest_height_cm": 183.0, "ground_lift_cm": 98.0,
                  "facing": {"axis": "+Y"}, "rotate_z_deg": self.args["rotate_z_deg"], "root_path": {"bone": "Hips"},
                  "frames": {"start": 0, "end": self.args["last"] - self.args["first"], "keys": self.args["last"] - self.args["first"] + 1,
                             "fps": self.args["fps"]}, "fbx_bytes": 1234, "seconds": 0.6}
        code = 0
        if kind == "error":
            report, code = {"ok": False, "blender": "4.4.1", "error": {"code": "BVH_IMPORT_FAILED", "message": "import_anim.bvh returned ['CANCELLED']"}}, 2
        log = pathlib.Path(self.args["report"]).with_name("blender.log")
        log.write_text("Blender 4.4.1\nread BVH\nbvh_to_fbx: done\n", encoding="utf-8")
        if kind != "crash":
            pathlib.Path(self.args["report"]).write_text(json.dumps(report), encoding="utf-8")
        else:
            code = 3
        if kind == "ok":
            pathlib.Path(self.args["fbx"]).write_bytes(b"fbx")
        self.returncode = code


class FakeLauncher:
    def __init__(self):
        self.procs: list[FakeProc] = []

    def __call__(self, cmd, **kwargs):
        proc = FakeProc(cmd, kwargs, pid=4000 + len(self.procs))
        self.procs.append(proc)
        return proc

    @property
    def last(self) -> FakeProc:
        return self.procs[-1]


@pytest.fixture
def bl(make_service, fake, tmp_path, monkeypatch):
    """가짜 Blender 실행 파일 · ImportSourceRoots(tmp) · Vesper(+Y)와 반대(-Y)를 보는 걷기 BVH."""
    roots = tmp_path / "Import"
    (roots / "Sources").mkdir(parents=True)
    fake.import_roots = [roots.as_posix() + "/"]
    exe = tmp_path / "Blender" / "blender.exe"
    exe.parent.mkdir()
    exe.write_text("fake", encoding="utf-8")
    clip = roots / "Sources" / "walk.bvh"
    clip.write_text(make_bvh(toe=(0.0, -8.0, -12.0), frames=121), encoding="utf-8")
    launcher, clock = FakeLauncher(), FakeClock()

    def make(**replace):
        service, registry = make_service(blender=lambda reg: BlenderProvider(reg.get("blender").manifest, popen=launcher, clock=clock), **replace)
        assert service.set_generation_policy(patch={"paths": {"blender_executable": exe.as_posix()}})["ok"]
        return service, registry

    service, registry = make()
    return types.SimpleNamespace(service=service, registry=registry, make=make, launcher=launcher, clock=clock, exe=exe, clip=clip, roots=roots,
                                 fake=fake, tmp=tmp_path)


def bvh_request(bl, **overrides) -> dict:
    base = {"animation_name": "AS_Vesper_Mocap_WalkP4", "family": "Mocap", "motion_category": "locomotion", "loop": False, "search": ...,
            "edits": ..., "target_mesh": VESPER_MESH, "motion_file": {"path": bl.clip.as_posix()}, "description": "CMU 류 BVH 걷기"}
    base.update(overrides)
    return request(**base)


def plan(bl, **overrides) -> dict:
    env = bl.service.plan_motion_generation(request=bvh_request(bl, **overrides))
    assert env["ok"], env["error"]
    return env["result"]


def generate(bl, **overrides) -> tuple[dict, dict]:
    p = plan(bl, **overrides)
    return p, bl.service.generate_motion(plan_id=p["plan_id"], save=True)


def status(bl, job_id: str, service=None) -> dict:
    return (service or bl.service).get_generation_status(job_id=job_id)


# ---- 계획 ----
def test_plan_pins_bvh_unit_facing_and_runs_nothing(bl):
    p = plan(bl)
    assert p["order"][0] == "blender" and p["executable"]
    cand = p["candidates"][0]
    assert cand["provider"] == "blender" and cand["chain"] == ["blender", "retarget"]
    convert, imp, retarget, validate = cand["steps"]
    r = convert["resolved"]
    assert r["bvh"]["joint_count"] == 11 and r["bvh"]["joints"][1] == {"name": "LeftUpLeg", "parent": "Hips"}
    assert r["unit"]["mode"] == "auto:cm" and r["fps"] == {"source": 120.0, "output": 120.0, "snapped": True}
    assert r["range"] == {"first": 0, "last": 120, "frames": 121, "duration": 1.0, "aligned_to": None, "trimmed_frames": 0, "unaligned": False}
    assert r["sample_rate"] is None and imp["inputs"]["sample_rate"] is None  # frame_rate 요청 없음 → 소스 rate 그대로
    assert (r["facing"]["source"], r["facing"]["target"], r["facing"]["rotate_z_deg"]) == ("-Y", "+Y", 180.0)
    assert len(r["sha256"]) == 64 and r["name"] == "BVH_walk"
    assert imp["step"] == "import" and retarget["inputs"]["source_mesh_source"] == "import" and validate["step"] == "validate"
    assert "SOURCE_CHAINS_UNVERIFIED" in cand["risks"] and "measured" not in convert and "expected_limitations" not in convert
    assert not bl.launcher.procs and not bl.fake.writes


def test_without_motion_file_the_phase3_order_is_unchanged(bl):
    env = bl.service.plan_motion_generation(request=request())
    assert "blender" not in env["result"]["order"]
    p = plan(bl, motion_file=..., provider="blender")
    assert {e["provider"]: (e["cause"], e["reason"]) for e in p["excluded"]}["blender"] == ("UNSUPPORTED_REQUEST", "MISSING_INPUT")


def test_executable_missing_is_provider_unavailable(bl):
    bl.service.set_generation_policy(patch={"paths": {"blender_executable": (bl.tmp / "nope.exe").as_posix()}})
    p = plan(bl, provider="blender")
    assert not p["executable"] and p["excluded"][0]["cause"] == "PROVIDER_UNAVAILABLE" and p["excluded"][0]["reason"] == "NOT_INSTALLED"
    env = bl.service.generate_motion(plan_id=p["plan_id"])
    assert env["error"]["code"] == "PROVIDER_UNAVAILABLE" and not bl.launcher.procs


def test_executable_gone_at_run_is_skipped_and_recorded(bl):
    p = plan(bl, search={"query": "rifle aim idle"})
    bl.exe.unlink()
    job = bl.service.generate_motion(plan_id=p["plan_id"])["result"]
    assert job["status"] == "SUCCEEDED" and job["provider"] == "existing_motion" and not bl.launcher.procs
    [h] = job["fallback_history"]
    assert h["skipped"] and (h["provider"], h["cause"], h["reason"]) == ("blender", "PROVIDER_UNAVAILABLE", "NOT_INSTALLED")
    assert "FALLBACK_USED" in {lim["code"] for lim in job["limitations"]}


@pytest.mark.parametrize("make_file, reason", [
    (lambda d: d / "Sources" / "clip.fbx", "UNSUPPORTED_FORMAT"),
    (lambda d: d / "Sources" / "missing.bvh", "FILE_NOT_FOUND"),
    (lambda d: d / "Sources" / "broken.bvh", "BAD_MOTION_FILE"),
])
def test_bad_motion_files_are_excluded(bl, make_file, reason):
    path = make_file(bl.roots)
    if path.name != "missing.bvh":
        path.write_text("HIERARCHY\nROOT A\n{\n", encoding="utf-8")
    p = plan(bl, motion_file={"path": path.as_posix()})
    assert {e["provider"]: e["reason"] for e in p["excluded"]}["blender"] == reason


def test_motion_file_outside_import_roots_is_refused(bl):
    outside = bl.tmp / "elsewhere.bvh"
    outside.write_text(make_bvh(), encoding="utf-8")
    env = bl.service.plan_motion_generation(request=bvh_request(bl, motion_file={"path": outside.as_posix()}))
    assert env["error"]["code"] == "IMPORT_SOURCE_NOT_ALLOWED" and env["error"]["details"]["reason"] == "OUTSIDE_IMPORT_ROOTS"


def test_range_is_aligned_to_the_requested_frame_rate(bl):
    """경계에 안 맞는 길이는 Interchange 가 반 프레임까지 늘리거나 줄인다(LENGTH_SNAPPED) → 끝을 당겨 소스 프레임 그대로 그 rate 로 임포트."""
    clip = bl.roots / "Sources" / "odd.bvh"
    clip.write_text(make_bvh(toe=(0.0, -8.0, -12.0), frames=123), encoding="utf-8")  # 122 구간 → 30 fps 로 30.5 프레임
    p = plan(bl, motion_file={"path": clip.as_posix()}, frame_rate=30)
    convert, imp = p["candidates"][0]["steps"][:2]
    rng = convert["resolved"]["range"]
    assert (rng["last"], rng["trimmed_frames"], rng["aligned_to"]) == (120, 2, 30) and imp["inputs"]["sample_rate"] == 30
    assert "RANGE_ALIGNED" in {d["code"] for d in p["diagnostics"]}
    bl.service.generate_motion(plan_id=p["plan_id"])
    assert bl.launcher.last.args["last"] == 120


def test_unaligned_source_rate_is_not_resampled(bl):
    clip = bl.roots / "Sources" / "odd_rate.bvh"
    clip.write_text(make_bvh(frames=50, frame_time=1 / 47.3), encoding="utf-8")
    p = plan(bl, motion_file={"path": clip.as_posix()}, frame_rate=30)
    cand = p["candidates"][0]
    assert cand["steps"][1]["inputs"]["sample_rate"] is None and cand["steps"][0]["resolved"]["range"]["unaligned"]
    assert "FRAME_RATE_MISMATCH" in {lim["code"] for lim in cand["expected_limitations"]}


def test_scale_normalized_is_an_expected_limitation(bl):
    small = bl.roots / "Sources" / "cmu_like.bvh"
    small.write_text(make_bvh(scale=30 / 183, frames=5), encoding="utf-8")
    cand = plan(bl, motion_file={"path": small.as_posix()})["candidates"][0]
    lims = {lim["code"]: lim for lim in cand["expected_limitations"]}
    assert lims["SCALE_NORMALIZED"]["source"] == "provider" and lims["SCALE_NORMALIZED"]["cm_per_unit"] == pytest.approx(170 / 30, rel=1e-4)


# ---- 실행 ----
def test_success_runs_async_then_imports_and_retargets(bl, monkeypatch):
    monkeypatch.setenv("MESHY_API_KEY", "sk-SENTINEL-BLENDER")
    _, env = generate(bl, frame_rate=30)
    job = env["result"]
    assert env["ok"] and job["status"] == "RUNNING" and job["stage"] == "convert"
    proc = bl.launcher.last
    exe, *flags = proc.cmd
    assert exe == bl.exe.as_posix() and flags[:5] == ["-b", "--factory-startup", "--python-exit-code", "3", "-P"]
    assert flags[5] == str(SCRIPT) and flags[6] == "--" and flags[7].endswith("args.json")
    kw = proc.kwargs
    assert kw["stdin"] is subprocess.DEVNULL and kw["stderr"] is subprocess.STDOUT and kw["stdout"] is not None  # MCP stdio 를 상속하지 않는다
    assert "MESHY_API_KEY" not in kw["env"] and "PATH" in {k.upper() for k in kw["env"]}
    if os.name == "nt":
        assert kw["creationflags"] == subprocess.CREATE_NO_WINDOW
    out = pathlib.Path(proc.args["fbx"]).parent
    assert out == bl.roots / "Blender" / job["job_id"] / "A1" and proc.args["fbx"].endswith("BVH_walk.fbx")
    assert (proc.args["cm_per_unit"], proc.args["rotate_z_deg"], proc.args["first"], proc.args["last"], proc.args["fps"]) == (1.0, 180.0, 0, 120, 120.0)
    assert "sk-SENTINEL-BLENDER" not in json.dumps(job)

    assert status(bl, job["job_id"])["result"]["status"] == "RUNNING"  # 아직 안 끝났다
    proc.complete("ok")
    env = status(bl, job["job_id"])
    job = env["result"]
    assert env["ok"] and job["status"] == "SUCCEEDED", job.get("error")
    assert [e["to"] for e in job["events"]] == ["QUEUED", "RUNNING", "SUCCEEDED"]
    assert job["generated_assets"] == [FINAL] and any(a.endswith("/Import/Mock_Anim") for a in job["intermediate_assets"])
    [(_, imp)] = [(t, p) for t, p in bl.fake.calls if t == "import_animation_file"]
    assert imp["file"] == proc.args["fbx"] and imp["sample_rate"] == 30 and imp["dest_path"].endswith(f"/Work/{job['job_id']}/A1/Import")
    assert job["cursor"]["values"]["converted"]["bones"] == 11
    assert "BLENDER_CONVERTED" in {d["code"] for d in job["diagnostics"]}
    codes = [lim["code"] for lim in job["limitations"]]
    assert len(codes) == len(set(codes))


def test_import_length_snap_reaches_the_job(bl):
    """import_animation_file 의 LENGTH_SNAPPED(경계에 안 맞는 길이를 가까운 프레임으로) 가 Job diagnostics 에 tool · step 과 함께 남는다."""
    bl.fake.diags["import_animation_file"] = [{"level": "warning", "code": "LENGTH_SNAPPED", "message": "snapped", "track": "Scene"}]
    _, env = generate(bl, frame_rate=30)
    bl.launcher.last.complete("ok")
    job = status(bl, env["result"]["job_id"])["result"]
    assert job["status"] == "SUCCEEDED", job.get("error")
    [d] = [d for d in job["diagnostics"] if d["code"] == "LENGTH_SNAPPED"]
    assert (d["tool"], d["step"], d["track"]) == ("import_animation_file", "import", "Scene")


def test_blender_error_falls_back_and_records_what_is_missing(bl):
    _, env = generate(bl, search={"query": "rifle aim idle"})
    bl.launcher.last.complete("error")
    job = status(bl, env["result"]["job_id"])["result"]
    assert job["status"] == "SUCCEEDED" and job["provider"] == "existing_motion" and job["reused_assets"] == [AIM_IDLE]
    [h] = job["fallback_history"]
    assert (h["provider"], h["step"], h["cause"], h["reason"]) == ("blender", "convert", "GENERATION_FAILED", "BVH_IMPORT_FAILED")
    assert "blender.log" in h["message"]
    used = {lim["code"]: lim for lim in job["limitations"]}["FALLBACK_USED"]
    assert used["from"] == "blender" and "walk.bvh" in used["missing"]


@pytest.mark.parametrize("kind, reason", [("crash", "BLENDER_EXIT_3"), ("no_fbx", "NO_OUTPUT")])
def test_exit_without_report_or_fbx_fails(bl, kind, reason):
    _, env = generate(bl, provider="blender")
    bl.launcher.last.complete(kind)
    env = status(bl, env["result"]["job_id"])
    job = env["result"]
    assert job["status"] == "FAILED" and job["error"]["code"] == "GENERATION_FAILED" and job["error"]["reason"] == reason
    assert not bl.fake.writes  # 변환이 실패하면 import 이후는 돌지 않는다


def test_timeout_stops_the_process(bl):
    bl.service.set_generation_policy(patch={"execution": {"subprocess_timeout_seconds": 20}})
    _, env = generate(bl, provider="blender")
    proc = bl.launcher.last
    bl.clock.t += 19
    assert status(bl, env["result"]["job_id"])["result"]["status"] == "RUNNING" and not proc.killed
    bl.clock.t += 2
    job = status(bl, env["result"]["job_id"])["result"]
    assert proc.killed and job["status"] == "FAILED" and job["error"]["reason"] == "TIMEOUT"
    assert "20s" in job["error"]["message"]


def test_cancel_stops_the_process_and_polls_no_more(bl):
    _, env = generate(bl)
    proc = bl.launcher.last
    env = bl.service.cancel_generation(job_id=env["result"]["job_id"])
    job = env["result"]
    assert job["status"] == "CANCELLED" and job["result_ignored"] and proc.killed
    assert job["cancel_effect"] == {"stopped": True, "pid": proc.pid}
    assert {"RESULT_IGNORED", "PROCESS_STOPPED"} <= {d["code"] for d in env["diagnostics"]}
    polls = proc.polls
    assert status(bl, job["job_id"])["result"]["status"] == "CANCELLED" and proc.polls == polls


def test_restart_continues_from_the_report_file(bl, fake, state_dir):
    _, env = generate(bl)
    job_id = env["result"]["job_id"]
    old = bl.launcher.last

    def restarted() -> Service:
        registry = bl.registry.__class__()
        registry.replace(BlenderProvider(registry.get("blender").manifest, popen=bl.launcher, clock=bl.clock))
        return Service(store=Store(state_dir), registry=registry, editor=fake.client())

    assert status(bl, job_id, restarted())["result"]["status"] == "RUNNING"  # 핸들이 없고 report 도 없다 — 기한 전이면 기다린다
    old.complete("ok")  # 프로세스는 서버 밖에서 끝났다
    job = status(bl, job_id, restarted())["result"]
    assert job["status"] == "SUCCEEDED" and job["generated_assets"] == [FINAL]


def test_restart_after_the_deadline_without_report_is_a_timeout(bl, fake, state_dir):
    _, env = generate(bl, provider="blender")
    registry = bl.registry.__class__()
    registry.replace(BlenderProvider(registry.get("blender").manifest, popen=bl.launcher, clock=bl.clock))
    service = Service(store=Store(state_dir), registry=registry, editor=fake.client())
    bl.clock.t += 301
    job = status(bl, env["result"]["job_id"], service)["result"]
    assert job["status"] == "FAILED" and job["error"]["reason"] == "TIMEOUT" and "not tracked" in job["error"]["message"]
    assert not bl.launcher.last.killed  # 핸들이 없으면 멈추지 못한다(그렇다고 적는다)


def test_file_changed_after_planning_stops_without_fallback(bl):
    p = plan(bl, search={"query": "rifle aim idle"})
    bl.clip.write_text(make_bvh(toe=(0.0, -8.0, 12.0), frames=121), encoding="utf-8")
    env = bl.service.generate_motion(plan_id=p["plan_id"])
    assert env["error"]["code"] == "UNSUPPORTED_REQUEST" and env["error"]["details"]["reason"] == "FILE_CHANGED"
    assert not bl.launcher.procs and bl.fake.count("validate_animation") == 0  # existing_motion 으로 넘어가지 않았다


def test_plan_without_editor_resolves_facing_at_run(bl):
    bl.fake.up = False
    p = plan(bl)
    convert = p["candidates"][0]["steps"][0]
    assert not convert["resolved"]["facing"]["resolved"] and {"IMPORT_ROOTS_UNCHECKED", "FACING_UNRESOLVED_AT_PLAN"} <= set(p["candidates"][0]["risks"])
    bl.fake.up = True
    bl.service.generate_motion(plan_id=p["plan_id"])
    assert bl.launcher.last.args["rotate_z_deg"] == 180.0


def test_unmeasured_facing_is_an_expected_limitation(bl):
    """발끝이 축 사이(45°)면 정면을 모른다 — 돌리지 않고 FACING_UNKNOWN. detail 키는 limitation() 의 source 인자와 겹치지 않는다."""
    skew = bl.roots / "Sources" / "skew.bvh"
    skew.write_text(make_bvh(toe=(12.0, -8.0, 12.0), frames=5), encoding="utf-8")
    cand = plan(bl, motion_file={"path": skew.as_posix()})["candidates"][0]
    facing = cand["steps"][0]["resolved"]["facing"]
    assert facing["source"] is None and facing["source_detail"]["reason"] == "OFF_AXIS" and facing["rotate_z_deg"] == 0.0
    lim = {lim["code"]: lim for lim in cand["expected_limitations"]}["FACING_UNKNOWN"]
    assert (lim["source"], lim["source_axis"], lim["target_axis"]) == ("provider", None, "+Y")


def test_facing_keep_and_explicit_axis(bl):
    assert plan(bl, motion_file={"path": bl.clip.as_posix(), "facing": "keep"})["candidates"][0]["steps"][0]["resolved"]["facing"]["rotate_z_deg"] == 0.0
    r = plan(bl, motion_file={"path": bl.clip.as_posix(), "facing": "+X"})["candidates"][0]["steps"][0]["resolved"]["facing"]
    assert (r["target"], r["target_from"], r["rotate_z_deg"]) == ("+X", "request", -90.0)  # UE -Y → +X = Blender +Y → +X (시계 방향)


@pytest.mark.parametrize("motion_file, field", [
    ({"path": "relative/walk.bvh"}, "motion_file.path"),
    ({"path": "D:/x.bvh", "unit": "feet"}, "motion_file.unit"),
    ({"path": "D:/x.bvh", "facing": "north"}, "motion_file.facing"),
    ({"path": "D:/x.bvh", "range": {"start": "0"}}, "motion_file.range"),
    ({"path": "D:/x.bvh", "axis_up": "-Z", "axis_forward": "Z"}, "motion_file.axis_forward"),
    ({"path": "D:/x.bvh", "scale": 2}, "motion_file.scale"),
])
def test_motion_file_validation(bl, motion_file, field):
    env = bl.service.plan_motion_generation(request=bvh_request(bl, motion_file=motion_file))
    assert env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["field"] == field


def test_motion_file_as_a_plain_path(bl):
    p = plan(bl, motion_file=bl.clip.as_posix())
    assert p["request"]["motion_file"] == {"path": bl.clip.as_posix(), "unit": "auto", "facing": "auto", "range": None, "axis_forward": "-Z",
                                           "axis_up": "Y"}


def test_timeout_policy_key_is_validated(bl):
    env = bl.service.set_generation_policy(patch={"execution": {"subprocess_timeout_seconds": 5}})
    assert env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["reason"] == "BAD_VALUE"
    assert bl.service.get_generation_policy()["result"]["effective"]["execution"]["subprocess_timeout_seconds"] == 300
