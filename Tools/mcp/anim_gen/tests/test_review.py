"""blender 변환 단계의 프레임 렌더 비교(review.render) · 보정 단계 자리(fix) — 지침서 §14 Phase 5 단위 2.

요청 검증 · 기본값 · 시각 펼치기 · fix op 차단(모든 경로) · op 사전 확장점 · args.json 배선 · 가짜 Blender 의 frames → Job.review ·
렌더 실패는 변환 실패가 아님 · 레퍼런스 이미지 루트 · 존재 · 변환 없는 경로의 한계 · 생성(local_ai) 경로. Blender 는 가짜 실행기
(test_blender.FakeProc — args.review 가 있으면 PNG · 시트를 쓴다)로 대신한다.
"""
from __future__ import annotations

import pathlib

import pytest

from anim_gen.providers import blender as blender_mod
from anim_gen.providers.blender import REVIEW_RENDER
from test_blender import bl, bvh_request, generate, plan, status  # noqa: F401 — bl 는 픽스처
from test_local_ai import KimodoProc, ka, run_to_end  # noqa: F401 — ka 는 픽스처
from test_local_ai import plan as ai_plan


def _codes(items) -> list[str]:
    return [item["code"] for item in items]


def _excluded(p: dict) -> dict:
    return {e["provider"]: (e["cause"], e["reason"]) for e in p["excluded"]}


def _ref(bl, name: str = "ref.png") -> pathlib.Path:
    path = bl.roots / "Sources" / name
    path.write_bytes(b"\x89PNG fake")
    return path


# ---- 요청 ----
@pytest.mark.parametrize("review, fix, field", [
    ({}, None, "review"),
    ({"render": {}, "extra": 1}, None, "review"),
    ({"render": {"zoom": 2}}, None, "review.render.zoom"),
    ({"render": {"times": [0.5], "count": 2}}, None, "review.render.times"),
    ({"render": {"times": []}}, None, "review.render.times"),
    ({"render": {"times": [-1]}}, None, "review.render.times"),
    ({"render": {"times": [0.1] * 13}}, None, "review.render.times"),
    ({"render": {"count": 0}}, None, "review.render.count"),
    ({"render": {"count": 13}}, None, "review.render.count"),
    ({"render": {"views": ["top"]}}, None, "review.render.views"),
    ({"render": {"views": ["front", "front"]}}, None, "review.render.views"),
    ({"render": {"views": []}}, None, "review.render.views"),
    ({"render": {"reference_images": ["ref.png"]}}, None, "review.render.reference_images[0]"),
    ({"render": {"reference_images": ["D:/refs/pose.gif"]}}, None, "review.render.reference_images[0]"),
    ({"render": {"reference_images": ["D:/a.png"] * 5}}, None, "review.render.reference_images"),
    (None, {"ops": "foot_lock"}, "fix.ops"),
    (None, {"ops": [{"name": "foot_lock"}]}, "fix.ops"),
    (None, {"opz": []}, "fix.opz"),
    (None, ["foot_lock"], "fix"),
])
def test_review_and_fix_validation(bl, review, fix, field):
    env = bl.service.plan_motion_generation(request=bvh_request(bl, review=review, fix=fix))
    assert env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["field"] == field


def test_defaults_and_count_spread_over_the_clip(bl):
    p = plan(bl, review={"render": {}})
    assert p["request"]["review"] == {"render": {"times": None, "count": 4, "views": ["front", "side"], "reference_images": []}}
    assert p["request"]["fix"] == {"ops": []}
    cand = p["candidates"][0]
    convert = cand["steps"][0]
    # 1.0초 클립(121프레임 @ 120 fps) — 첫 · 끝 프레임 포함 4개
    assert convert["inputs"]["review"] == {"times": [0.0, 0.3333, 0.6667, 1.0], "count": 4, "views": ["front", "side"], "reference_images": []}
    assert convert["inputs"]["fix"] == {"ops": []}
    assert _codes(cand["expected_limitations"]).count("REVIEW_IS_SOURCE_SKELETON") == 1
    assert not bl.launcher.procs


def test_without_review_nothing_changes(bl):
    p = plan(bl)
    assert p["request"]["review"] is None and p["candidates"][0]["steps"][0]["inputs"]["review"] is None
    _, env = generate(bl)
    args = bl.launcher.last.args
    assert args["review"] is None and args["fix"] == []
    bl.launcher.last.complete("ok")
    job = status(bl, env["result"]["job_id"])["result"]
    assert job["status"] == "SUCCEEDED" and job["review"] is None and "review" not in job["cursor"]["values"]
    assert "REVIEW_IS_SOURCE_SKELETON" not in _codes(job["limitations"])


# ---- fix: 자리만 ----
def test_fix_ops_block_every_candidate(bl):
    """op 사전이 비어 있다 — blender 도, 변환 단계가 없는 existing_motion 도 그 op 를 돌릴 곳이 없다."""
    p = plan(bl, search={"query": "rifle aim idle"}, fix={"ops": [{"op": "foot_lock", "bones": ["LeftFoot"]}]})
    assert not p["executable"]
    excluded = _excluded(p)
    assert excluded["blender"] == ("UNSUPPORTED_REQUEST", "UNSUPPORTED_FIX_OP") == excluded["existing_motion"]
    [blender] = [e for e in p["excluded"] if e["provider"] == "blender"]
    assert blender["ops"] == ["foot_lock"] and blender["available"] == []
    assert not [q for t, q in bl.fake.calls if t == "search_animations" and q.get("query") == "rifle aim idle"]  # 소스 검색 전에 막았다
    assert not bl.launcher.procs


def test_fix_dictionary_is_the_extension_point(bl, monkeypatch):
    """Phase 8 은 이름 → 인자 검사(Provider) + 같은 이름의 bvh_to_fbx.py 함수를 끼운다 — 계획이 통과하면 ops 가 그대로 args.json 으로 간다."""
    seen = []
    monkeypatch.setitem(blender_mod.FIX_OPS, "foot_lock", seen.append)
    op = {"op": "foot_lock", "bones": ["LeftFoot"]}
    p, _ = generate(bl, fix={"ops": [op]})
    assert p["executable"] and p["candidates"][0]["steps"][0]["inputs"]["fix"] == {"ops": [op]} and seen == [op]
    assert bl.launcher.last.args["fix"] == [op]


# ---- 실행: args.json · Job ----
def test_review_args_reach_blender(bl):
    ref = _ref(bl)
    _, env = generate(bl, review={"render": {"times": [0.5, 0.0], "views": ["side"], "reference_images": [ref.as_posix()]}})
    job = env["result"]
    args = bl.launcher.last.args
    out = bl.roots / "Blender" / job["job_id"] / "A1"
    assert args["review"] == {"times": [0.5, 0.0], "views": ["side"], "reference_images": [ref.as_posix()], "dir": (out / "frames").as_posix(),
                              **REVIEW_RENDER}
    assert args["fix"] == []


def test_frames_from_blender_reach_the_job(bl):
    _, env = generate(bl, review={"render": {"count": 2}})
    job_id = env["result"]["job_id"]
    bl.launcher.last.complete("ok")
    job = status(bl, job_id)["result"]
    assert job["status"] == "SUCCEEDED", job.get("error")
    review = job["review"]
    frames_dir = bl.roots / "Blender" / job_id / "A1" / "frames"
    assert review["shows"] == "source_skeleton" and review["sheet"] == (frames_dir / "sheet.png").as_posix()
    assert [(f["time"], f["view"]) for f in review["frames"]] == [(0.0, "front"), (0.0, "side"), (1.0, "front"), (1.0, "side")]
    assert all(pathlib.Path(f["path"]).is_file() for f in review["frames"])
    assert job["cursor"]["values"]["review"] == review  # 단계 값(values.review)이 Job 의 review 로 올라온다
    [d] = [d for d in job["diagnostics"] if d["code"] == "BLENDER_REVIEW_RENDERED"]
    assert d["sheet"] == review["sheet"] and len(d["frames"]) == 4 and "timeout 300s" in d["message"]
    assert _codes(job["limitations"]).count("REVIEW_IS_SOURCE_SKELETON") == 1  # 계획의 예상 한계 + 실행 한계 → 하나


def test_render_failure_does_not_fail_the_conversion(bl):
    _, env = generate(bl, provider="blender", review={"render": {}})
    bl.launcher.last.complete("review_error")
    job = status(bl, env["result"]["job_id"])["result"]
    assert job["status"] == "SUCCEEDED" and job["generated_assets"] and job["review"] is None
    [d] = [d for d in job["diagnostics"] if d["code"] == "REVIEW_RENDER_FAILED"]
    assert "REVIEW_EXCEPTION" in d["message"] and "blender.log" in d["message"]
    lim = {lim["code"]: lim for lim in job["limitations"]}["REVIEW_NOT_RENDERED"]
    assert lim["reason"] == "REVIEW_EXCEPTION" and lim["source"] == "provider"


# ---- 레퍼런스 이미지 · 시각 범위 ----
def test_reference_image_outside_import_roots_is_refused(bl):
    outside = bl.tmp / "pose.png"
    outside.write_bytes(b"png")
    env = bl.service.plan_motion_generation(request=bvh_request(bl, review={"render": {"reference_images": [outside.as_posix()]}}))
    assert env["error"]["code"] == "IMPORT_SOURCE_NOT_ALLOWED" and env["error"]["details"]["reason"] == "OUTSIDE_IMPORT_ROOTS"
    assert "reference images" in env["error"]["message"] and not bl.launcher.procs


def test_reference_image_missing_at_plan_or_at_run(bl):
    missing = bl.roots / "Sources" / "nope.jpg"
    p = plan(bl, review={"render": {"reference_images": [missing.as_posix()]}})
    assert _excluded(p)["blender"] == ("UNSUPPORTED_REQUEST", "FILE_NOT_FOUND")
    ref = _ref(bl, "gone.png")
    p = plan(bl, review={"render": {"reference_images": [ref.as_posix()]}})
    ref.unlink()  # 계획 뒤 사라짐 → 시트에서 빼고 알린다(변환은 그대로)
    env = bl.service.generate_motion(plan_id=p["plan_id"])
    assert bl.launcher.last.args["review"]["reference_images"] == []
    bl.launcher.last.complete("ok")
    job = status(bl, env["result"]["job_id"])["result"]
    assert job["status"] == "SUCCEEDED" and "REVIEW_REFERENCE_MISSING" in _codes(job["diagnostics"])
    assert job["review"]["sheet"]


def test_review_time_past_the_end_excludes_blender(bl):
    p = plan(bl, review={"render": {"times": [0.5, 2.0]}})
    excluded = {e["provider"]: e for e in p["excluded"]}["blender"]
    assert (excluded["cause"], excluded["reason"], excluded["duration"]) == ("UNSUPPORTED_REQUEST", "REVIEW_TIME_OUT_OF_RANGE", 1.0)


def test_route_without_convert_records_that_nothing_is_rendered(bl):
    p = plan(bl, motion_file=..., search={"query": "rifle aim idle"}, review={"render": {}})
    cand = p["candidates"][0]
    assert cand["provider"] == "existing_motion" and "REVIEW_NOT_RENDERED" in _codes(cand["expected_limitations"])
    job = bl.service.generate_motion(plan_id=p["plan_id"])["result"]
    assert job["status"] == "SUCCEEDED" and job["review"] is None and "REVIEW_NOT_RENDERED" in _codes(job["limitations"])


# ---- 생성(local_ai) 경로 ----
def test_generated_route_renders_after_the_convert(ka):
    p = ai_plan(ka, review={"render": {"count": 3, "views": ["front"]}})
    cand = p["candidates"][0]
    convert = cand["steps"][1]
    # 계획 땐 생성 규약(181프레임 @ 30 fps = 6초)으로 펼치고, 실행 땐 생성된 BVH 의 길이로 다시 펼친다
    assert convert["inputs"]["review"] == {"times": [0.0, 3.0, 6.0], "count": 3, "views": ["front"], "reference_images": []}
    assert "REVIEW_IS_SOURCE_SKELETON" in _codes(cand["expected_limitations"])
    job = run_to_end(ka, p)
    assert job["status"] == "SUCCEEDED", job.get("error")
    blender = [proc for proc in ka.launcher.procs if not isinstance(proc, KimodoProc)][-1]
    assert blender.args["review"]["times"] == [0.0, 3.0, 6.0] and blender.args["review"]["views"] == ["front"]
    assert job["review"]["sheet"].endswith("/frames/sheet.png") and len(job["review"]["frames"]) == 3
    assert _codes(job["limitations"]).count("REVIEW_IS_SOURCE_SKELETON") == 1


def test_generated_route_blocks_fix_ops(ka):
    p = ai_plan(ka, provider="local_ai", fix={"ops": [{"op": "smooth"}]})
    assert not p["executable"] and _excluded(p)["local_ai"] == ("UNSUPPORTED_REQUEST", "UNSUPPORTED_FIX_OP")
    assert not ka.launcher.procs
