"""대상 메시 캡처(review.capture → 플러그인 capture_animation) · APNG — 지침서 §14 Phase 8 '8-2'.

APNG 조립(재압축 없음 · 프레임 IHDR 일치 · 순번) · 요청 규칙(render 행을 따름 · 충돌) · 계획(모든 경로에 capture 단계 · 루트 없음 = 단계 없음 ·
에디터 없음 = 실행 때 · 포장 앞) · 실행(Job review.capture · APNG · 실패는 한계 · 가드 오류는 중단) · blender 경로의 비교 칸(소스 골격 프레임)과
렌더 실패 시 행 폴백. 에디터는 FakeEditor(작은 진짜 PNG 를 쓴다), Blender 는 test_blender 의 가짜 실행기.
"""
from __future__ import annotations

import pathlib
import struct
import zlib

import pytest

from anim_gen import apng
from anim_gen.providers.blender import REVIEW_RENDER
from conftest import AIM_IDLE, OUT, VESPER_MESH, err, request, write_png
from test_blender import bl, bvh_request, generate, plan, status  # noqa: F401 — bl 는 픽스처


def _codes(items) -> list[str]:
    return [item["code"] for item in items]


def _idat(path: pathlib.Path) -> bytes:
    return b"".join(body for kind, body in apng.read_chunks(path.read_bytes()) if kind == b"IDAT")


@pytest.fixture
def roots(fake, tmp_path):
    root = tmp_path / "Capture"
    root.mkdir()
    fake.capture_roots = [root.as_posix() + "/"]
    return root


def reuse_request(**overrides) -> dict:
    """대상 스켈레톤의 기존 애셋을 그대로(재사용 — 리타깃 · 편집 없음) — 캡처만 시험."""
    base = {"reference_animations": [AIM_IDLE], "search": ..., "edits": ..., "target_mesh": VESPER_MESH, "provider": "existing_motion",
            "review": {"capture": True}}
    base.update(overrides)
    return request(**base)


def plan_of(service, **overrides) -> dict:
    env = service.plan_motion_generation(request=reuse_request(**overrides))
    assert env["ok"], env["error"]
    return env["result"]


def run_job(service, **overrides) -> dict:
    p = plan_of(service, **overrides)
    env = service.generate_motion(plan_id=p["plan_id"], save=False)
    assert env["ok"], env["error"]
    return service.get_generation_status(job_id=env["result"]["job_id"])["result"]


# ---- APNG (순수) ----
def test_apng_joins_frames_without_recompressing(tmp_path):
    frames = [write_png(tmp_path / f"f{k}.png", 10, 4, (k * 40, 10, 20)) for k in range(3)]
    out = apng.assemble(frames, tmp_path / "anim" / "animation.png", 15)
    assert out["frames"] == 3 and out["size"] == [10, 4] and out["delay"] == [1, 15] and pathlib.Path(out["path"]).is_file()
    info = apng.inspect(out["path"])
    assert info == {"frames": 3, "plays": 0, "size": [10, 4], "sequence_ok": True, "fctl": 3, "idat": 1, "fdat": 2}
    # 첫 프레임 IDAT 은 원본 그대로(재압축 없음) — fdAT 는 순번 4바이트 + 같은 데이터
    assert _idat(pathlib.Path(out["path"])) == _idat(frames[0])
    fdats = [body for kind, body in apng.read_chunks(pathlib.Path(out["path"]).read_bytes()) if kind == b"fdAT"]
    assert [struct.unpack(">I", b[:4])[0] for b in fdats] == [2, 4] and fdats[1][4:] == _idat(frames[2])


def test_apng_refuses_bad_input(tmp_path):
    a = write_png(tmp_path / "a.png", 10, 4, (1, 2, 3))
    b = write_png(tmp_path / "b.png", 12, 4, (1, 2, 3))
    with pytest.raises(apng.ApngError) as e:
        apng.assemble([a, b], tmp_path / "x.png", 15)
    assert e.value.code == "FRAME_MISMATCH"
    (tmp_path / "n.png").write_bytes(b"not a png")
    with pytest.raises(apng.ApngError) as e:
        apng.assemble([tmp_path / "n.png"], tmp_path / "x.png", 15)
    assert e.value.code == "NOT_PNG"
    broken = bytearray(a.read_bytes())
    broken[-20] ^= 0xFF  # IDAT 본문 한 바이트 — CRC 불일치
    (tmp_path / "c.png").write_bytes(bytes(broken))
    with pytest.raises(apng.ApngError) as e:
        apng.read_chunks((tmp_path / "c.png").read_bytes())
    assert e.value.code == "BAD_CHUNK"
    for frames, fps, code in (([], 15, "NO_FRAMES"), ([a], 0, "BAD_FPS")):
        with pytest.raises(apng.ApngError) as e:
            apng.assemble(frames, tmp_path / "x.png", fps)
        assert e.value.code == code
    once = apng.assemble([a, a], tmp_path / "once.png", 15)
    with pytest.raises(apng.ApngError) as e:
        apng.assemble([once["path"]], tmp_path / "twice.png", 15)
    assert e.value.code == "ALREADY_ANIMATED"


@pytest.mark.parametrize("fps, expected", [(15, (1, 15)), (30, (1, 30)), (12.5, (2, 25)), (24, (1, 24))])
def test_apng_delay_fraction(fps, expected):
    assert apng.delay(fps) == expected


def test_apng_crc_is_standard(tmp_path):
    body = apng.chunk(b"tEXt", b"k\x00v")
    assert struct.unpack(">I", body[-4:])[0] == zlib.crc32(b"tEXtk\x00v") & 0xFFFFFFFF


# ---- 요청 ----
@pytest.mark.parametrize("review, field, reason", [
    ({"capture": {"times": [0.5], "count": 2}}, "review.capture.times", "CONFLICTING_FIELDS"),
    ({"render": {}, "capture": {"count": 3}}, "review.capture.times", "CONFLICTING_FIELDS"),
    ({"render": {}, "capture": {"times": [0.0]}}, "review.capture.times", "CONFLICTING_FIELDS"),
    ({"capture": {"zoom": 2}}, "review.capture.zoom", "UNKNOWN_FIELD"),
    ({"capture": {"views": ["top"]}}, "review.capture.views", "BAD_FIELD"),
    ({"capture": {"count": 13}}, "review.capture.count", "BAD_FIELD"),
    ({"capture": {"times": [-1]}}, "review.capture.times", "BAD_FIELD"),
    ({"capture": {"sequence": {"fps": 60}}}, "review.capture.sequence", "BAD_FIELD"),
    ({"capture": {"sequence": {"speed": 2}}}, "review.capture.sequence", "BAD_FIELD"),
    ({"capture": {"compare": "yes"}}, "review.capture.compare", "BAD_FIELD"),
    ({"capture": {"mesh": "SK_X"}}, "review.capture.mesh", "BAD_FIELD"),
    ({"capture": False}, "review", "BAD_FIELD"),
    ({"capture": "on"}, "review.capture", "BAD_FIELD"),
])
def test_capture_request_validation(service, review, field, reason):
    env = service.plan_motion_generation(request=reuse_request(review=review))
    assert env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["field"] == field
    assert env["error"]["details"]["reason"] == reason


def test_capture_defaults_and_render_rows(service, roots):
    p = plan_of(service)
    assert p["request"]["review"] == {"capture": {"times": None, "count": 4, "views": ["front", "side"], "mesh": None,
                                                  "sequence": {"fps": 15, "cell_height_px": 320, "max_frames": 150}, "compare": True}}
    p = plan_of(service, review={"render": {"count": 6, "views": ["side"]}, "capture": {"sequence": False}})
    cap = p["request"]["review"]["capture"]
    assert cap["count"] is None and cap["times"] is None and cap["views"] == ["side"] and cap["sequence"] is None
    assert p["request"]["review"]["render"]["count"] == 6  # render 는 개정 8 모양 그대로


# ---- 계획 ----
def test_plan_adds_capture_on_the_reuse_route(service, fake, roots):
    p = plan_of(service)
    [cand] = p["candidates"]
    assert [s["step"] for s in cand["steps"]] == ["resolve_source", "validate", "capture"] and cand["chain"] == ["existing_motion", "review"]
    capture = cand["steps"][-1]
    assert capture["provider"] == "review" and capture["tool"] == "capture_animation"
    inputs = capture["inputs"]
    assert inputs["asset"] == "$asset" and inputs["mesh"] == VESPER_MESH and inputs["facing"] == "+Y" and inputs["rows_from"] == "request"
    assert inputs["count"] == 4 and inputs["times"] is None and not inputs["compare"] and inputs["label"] == "Vesper"
    assert inputs["layout"] == {k: REVIEW_RENDER[k] for k in ("cell_height_px", "max_aspect", "margin", "bounds_max_samples", "sheet_max_px")}
    assert inputs["sequence"] == {"fps": 15, "cell_height_px": 320, "max_frames": 150}
    assert "REVIEW_CAPTURE_PREVIEW_ONLY" in _codes(cand["expected_limitations"]) and not cand["risks"]
    assert fake.count("capture_animation") == 0  # 계획은 찍지 않는다


def test_plan_without_capture_roots_drops_the_step(service):
    p = plan_of(service)  # FakeEditor 기본 = CaptureOutputRoots 비어 있음
    [cand] = p["candidates"]
    assert p["executable"] and [s["step"] for s in cand["steps"]] == ["resolve_source", "validate"]
    [lim] = [lm for lm in cand["expected_limitations"] if lm["code"] == "REVIEW_NOT_CAPTURED"]
    assert lim["reason"] == "CAPTURE_ROOTS_EMPTY"


def test_plan_without_mesh_drops_the_step(service, roots):
    p = plan_of(service, target_mesh=...)
    [cand] = p["candidates"]
    assert "capture" not in [s["step"] for s in cand["steps"]]
    assert [lm["reason"] for lm in cand["expected_limitations"] if lm["code"] == "REVIEW_NOT_CAPTURED"] == ["MISSING_MESH"]


def test_plan_without_editor_resolves_at_run(service, fake, roots):
    fake.up = False
    p = plan_of(service)
    capture = p["candidates"][0]["steps"][-1]
    assert capture["step"] == "capture" and capture["inputs"]["facing"] is None
    assert {"CAPTURE_FACING_RESOLVED_AT_RUN", "CAPTURE_ROOTS_UNCHECKED"} <= set(p["candidates"][0]["risks"])


def test_capture_comes_before_packaging(service, roots):
    p = plan_of(service, package={"montage": {"slot": "UpperBody"}}, edits={"operations": [{"op": "trim", "start": 0, "end": 1}]})
    steps = [s["step"] for s in p["candidates"][0]["steps"]]
    assert steps.index("validate") < steps.index("capture") < steps.index("package_montage")


def test_render_on_a_route_without_conversion(service, roots):
    p = plan_of(service, review={"render": {"count": 3}, "capture": {}})
    cand = p["candidates"][0]
    [lim] = [lm for lm in cand["expected_limitations"] if lm["code"] == "REVIEW_NOT_RENDERED"]
    assert "review.capture" in lim["message"]
    inputs = cand["steps"][-1]["inputs"]
    assert inputs["rows_from"] == "request" and inputs["count"] == 3 and not inputs["compare"] and "CAPTURE_ROWS_NOT_RENDER" in cand["risks"]


def test_without_capture_nothing_changes(service, roots):
    p = plan_of(service, review=...)
    assert [s["step"] for s in p["candidates"][0]["steps"]] == ["resolve_source", "validate"] and p["candidates"][0]["chain"] == ["existing_motion"]
    assert "REVIEW_CAPTURE_PREVIEW_ONLY" not in _codes(p["candidates"][0]["expected_limitations"])


# ---- 실행 ----
def test_capture_runs_and_reaches_the_job(service, fake, roots):
    job = run_job(service)
    assert job["status"] == "SUCCEEDED", job.get("error")
    [(tool, params)] = [(t, q) for t, q in fake.calls if t == "capture_animation"]
    out = roots / job["job_id"] / "A1"
    assert params["asset"] == AIM_IDLE and params["mesh"] == VESPER_MESH and params["facing"] == "+Y" and params["output_dir"] == out.as_posix()
    assert params["count"] == 4 and params["views"] == ["front", "side"] and params["sequence"]["fps"] == 15 and "compare" not in params
    assert params["cell_height_px"] == REVIEW_RENDER["cell_height_px"] and params["label"] == "Vesper"
    cap = job["review"]["capture"]
    assert set(job["review"]) == {"capture"}  # 소스 골격 렌더가 없는 경로 — 맨 위 필드 없음
    assert cap["ok"] and cap["shows"] == "target_mesh" and cap["sheet"] == (out / "sheet.png").as_posix() and pathlib.Path(cap["sheet"]).is_file()
    assert cap["rows_from"] == "request" and cap["compare_sheet"] is None and len(cap["frames"]) == 8
    anim = cap["animation"]
    assert anim["path"] == (out / "animation.png").as_posix() and anim["frames"] == cap["sequence"]["count"] == 21  # 1.3333초 · 15 fps — 끝 프레임까지
    assert apng.inspect(anim["path"])["frames"] == 21
    assert "REVIEW_CAPTURE_PREVIEW_ONLY" in _codes(job["limitations"])
    [d] = [d for d in job["diagnostics"] if d["code"] == "REVIEW_CAPTURED"]
    assert d["sheet"] == cap["sheet"] and d["animation"] == anim["path"]
    assert not fake.writes  # 캡처는 애셋을 만들지 않는다


def test_capture_without_sequence(service, fake, roots):
    job = run_job(service, review={"capture": {"sequence": False, "views": ["side"], "times": [0.0, 1.0]}})
    [(_, params)] = [(t, q) for t, q in fake.calls if t == "capture_animation"]
    assert "sequence" not in params and params["times"] == [0.0, 1.0] and params["views"] == ["side"]
    cap = job["review"]["capture"]
    assert cap["animation"] is None and cap["sequence"] is None and len(cap["frames"]) == 2


def test_capture_failure_is_not_a_generation_failure(service, fake, roots):
    fake.fail["capture_animation"] = [err("CAPTURE_FAILED", "ReadPixels failed", reason="READBACK")]
    job = run_job(service)
    assert job["status"] == "SUCCEEDED" and job["reused_assets"] == [AIM_IDLE]
    cap = job["review"]["capture"]
    assert not cap["ok"] and cap["reason"] == "READBACK" and cap["editor_error"]["code"] == "CAPTURE_FAILED"
    assert "REVIEW_NOT_CAPTURED" in _codes(job["limitations"])


def test_capture_guard_error_stops_the_job(service, fake, roots):
    fake.capture_dirty = ["/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"]
    p = plan_of(service)
    env = service.generate_motion(plan_id=p["plan_id"], save=False)
    assert not env["ok"] and env["error"]["code"] == "UNEXPECTED_DIRTY"
    job = service.get_generation_status(job_id=env["error"]["details"]["job"]["job_id"])["result"]
    assert job["status"] == "FAILED" and job["error"]["code"] == "UNEXPECTED_DIRTY" and len(job["fallback_history"]) <= 1


def test_capture_roots_vanished_at_run(service, fake, roots):
    p = plan_of(service)
    fake.capture_roots = []
    env = service.generate_motion(plan_id=p["plan_id"], save=False)
    job = service.get_generation_status(job_id=env["result"]["job_id"])["result"]
    assert job["status"] == "SUCCEEDED" and job["review"]["capture"]["reason"] == "CAPTURE_ROOTS_EMPTY" and fake.count("capture_animation") == 0


# ---- blender 경로: 소스 골격 렌더와 같은 행 · 비교 칸 ----
@pytest.fixture
def bl_roots(bl, tmp_path):
    root = tmp_path / "CaptureBl"
    root.mkdir()
    bl.fake.capture_roots = [root.as_posix() + "/"]
    return root


def test_blender_route_compares_with_the_source_skeleton(bl, bl_roots):
    p, env = generate(bl, review={"render": {"count": 2}, "capture": {}})
    capture = p["candidates"][0]["steps"][-1]
    assert capture["step"] == "capture" and capture["inputs"]["rows_from"] == "render" and capture["inputs"]["compare"]
    job_id = env["result"]["job_id"]
    bl.launcher.last.complete("ok")
    job = status(bl, job_id)["result"]
    assert job["status"] == "SUCCEEDED", job.get("error")
    review = job["review"]
    assert review["shows"] == "source_skeleton" and review["capture"]["ok"]  # 맨 위 = 소스 골격, capture = Vesper
    [(_, params)] = [(t, q) for t, q in bl.fake.calls if t == "capture_animation"]
    by = {(f["row"], f["view"]): f["path"] for f in review["frames"]}
    assert params["times"] == [0.0, 1.0] and "count" not in params
    assert params["compare"]["rows"] == [[by[(0, "front")], by[(0, "side")]], [by[(1, "front")], by[(1, "side")]]]
    cap = review["capture"]
    assert cap["rows_from"] == "render" and pathlib.Path(cap["compare_sheet"]).is_file()
    assert "REVIEW_IS_SOURCE_SKELETON" in _codes(job["limitations"]) and "REVIEW_CAPTURE_PREVIEW_ONLY" in _codes(job["limitations"])


def test_blender_render_failure_falls_back_to_count(bl, bl_roots):
    _, env = generate(bl, review={"render": {"count": 3}, "capture": {}})
    bl.launcher.last.complete("review_error")
    job = status(bl, env["result"]["job_id"])["result"]
    assert job["status"] == "SUCCEEDED", job.get("error")
    [(_, params)] = [(t, q) for t, q in bl.fake.calls if t == "capture_animation"]
    assert params["count"] == 3 and "compare" not in params and "times" not in params
    assert job["review"]["capture"]["rows_from"] == "request"
    assert "CAPTURE_ROWS_FROM_COUNT" in _codes(job["diagnostics"])


def test_blender_route_with_edits_skips_the_compare(bl, bl_roots):
    p = plan(bl, review={"render": {"count": 2}, "capture": {}}, edits={"operations": [{"op": "trim", "start": 0.0, "end": 0.5}]})
    cand = p["candidates"][0]
    capture = cand["steps"][-1]
    assert capture["step"] == "capture" and capture["inputs"]["rows_from"] == "request" and not capture["inputs"]["compare"]
    assert capture["inputs"]["count"] == 2 and "CAPTURE_COMPARE_SKIPPED_EDITS" in cand["risks"]


def test_output_path_constant_is_shared(service, roots):
    """캡처 셀 상수의 원천은 blender.REVIEW_RENDER 하나 — 두 시트가 같은 셀 규칙."""
    inputs = plan_of(service)["candidates"][0]["steps"][-1]["inputs"]
    assert inputs["layout"]["cell_height_px"] == 512 and inputs["layout"]["sheet_max_px"] == 3000
    assert OUT.startswith("/Game/Animation/Test/")
