"""AI 애니 생성 Phase 8-2 — 대상 메시 캡처 에디터 통합 테스트 (Docs/AIAnimation/DevelopmentGuide.md §14 Phase 8 '8-2' · §15 I).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase8_2_test.py [--only ...]

뜬 에디터(AnimGraphMcp 플러그인 — capture_animation)를 쓴다. anim_gen 은 같은 프로세스의 Service 로 부르고, 상태는 Saved/AnimGen/TestRuns/P82Run<시각>/ 에
격리한다. 캡처 이미지는 ini CaptureOutputRoots(Tools/mcp/results/capture/ — Saved 밖이라 채팅에 보일 수 있다) 아래 P82Run<시각>/ 과 Job 폴더에,
생성 애셋(chain)은 /Game/Animation/Test/AIAnimation/P82Run<시각>/ 에만 쓴다. 시험 대상 애셋(8-1 결과 · KimodoSword1025)은 읽기만 한다.
섹션:
  hashes     — (맨 앞) 시험 대상 3개 · 스켈레톤 · 메시 .uasset SHA-256 · Content/ git 상태 · 미저장 수 · Tool 41개 · capture_output_roots
  automation — C++ 단위 테스트 AnimGraphMcp.Generation.Capture(카메라 맞춤 = Blender 수식 · 시트 축소 · 출력 폴더 규칙)
  tool       — KimodoSlash 직접 캡처 ×2(같은 입력): 파일 · 행 × 뷰 · 시트 · 연속 프레임 → APNG · 잘림 없음 · 행마다 포즈가 바뀜 · 같은 픽셀 · 더티 0
  guard      — 루트 밖 · 루트 자체 · 비지 않은 폴더 · 루트 밖 비교 이미지 · 잘못된 정면 · 없는 애셋 → 거부, 파일 · 더티 0
  existing   — 8-1 검 선택(P81Run1026_180733) · 낫 선택(P81Run1026_205832) · KimodoSword1025 를 원래 Job 의 Blender 소스 골격 프레임과 비교 시트로 +
               APNG — 소스 프레임 경로는 이름 규칙(<ImportSourceRoots>/Blender/<job>/A1/frames[/cNN]/<view>_<frame>.png)으로만 만든다
  chain      — anim_gen Job: CMU 01_01 BVH(0 ~ 3초) → blender(render count 4) → 리타깃 → capture(같은 행 · 비교 칸 · APNG) → Job review.capture
  dirty      — (맨 뒤) 해시 불변 · 미저장 수 그대로 · Content/ 변경은 chain 실행 폴더뿐
요약은 Tools/mcp/anim_gen_phase8_2_state.json. 캡처는 판정 근거일 뿐 — 품질 합격은 사람이 본다(§16-9).
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
STATE_DIR = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P82Run{STAMP}"
os.environ["ANIM_GEN_STATE_DIR"] = str(STATE_DIR)

from anim_gen import apng  # noqa: E402
from anim_gen.service import Service  # noqa: E402
from anim_gen.store import Store  # noqa: E402

VESPER = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
MESH = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
RUN = f"/Game/Animation/Test/AIAnimation/P82Run{STAMP}"
CAPTURE_ROOT = ROOT / "Tools" / "mcp" / "results" / "capture"
OUT = CAPTURE_ROOT / f"P82Run{STAMP}"
BLENDER = ROOT / "Saved" / "AnimGen" / "Import" / "Blender"
KIMODO = "/Game/Animation/Test/AIAnimation/KimodoSword1025_185815/AS_Vesper_Sword_KimodoSlash"
SWORD = "/Game/Animation/Test/AIAnimation/P81Run1026_180733/AS_Vesper_Sword_KimodoSlashPick"
SCYTHE = "/Game/Animation/Test/AIAnimation/P81Run1026_205832/AS_Vesper_Sickle_KimodoSlashPick"
# 시험 대상 → 그 애셋을 만든 Job 의 Blender 소스 골격 프레임 폴더(8-1 기록: 검 = seed 20261025 후보 0, 낫 = seed 20261028 후보 3)
TARGETS = {
    "kimodo_sword_1025": (KIMODO, BLENDER / "job_20261025_185816_3461c1" / "A1" / "frames"),
    "p81_sword_pick": (SWORD, BLENDER / "job_20261026_180741_c0f5be" / "A1" / "frames" / "c00"),
    "p81_scythe_pick": (SCYTHE, BLENDER / "job_20261026_205840_56d522" / "A1" / "frames" / "c03"),
}
HASHED = [KIMODO, SWORD, SCYTHE, VESPER, MESH]
CMU_BVH = ROOT / "Saved" / "AnimGen" / "Import" / "Sources" / "CMU_01_01" / "01_01.bvh"
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
STATE: dict = {"run": RUN, "out": OUT.as_posix(), "state_dir": STATE_DIR.as_posix(), "captures": {}}
SERVICE = Service(store=Store(STATE_DIR))


def check(cond: bool, msg: str) -> bool:
    print(("[ ok ] " if cond else "[FAIL] ") + msg)
    if not cond:
        FAILS.append(msg)
    return cond


def must(env: dict, what: str) -> dict:
    if not env.get("ok"):
        print(f"[FAIL] {what}: {json.dumps(env.get('error'), ensure_ascii=False)[:3000]}")
        FAILS.append(what)
        raise SystemExit(finish())
    for d in env.get("diagnostics", []):
        print(f"   diag[{d['level']}] {d['code']}: {d['message'][:200]}")
    return env["result"]


def editor(tool: str, **params) -> dict:
    return bridge.call(tool, params, timeout=bridge.COMPILE_TIMEOUT)


def code_of(env: dict) -> tuple[str | None, str | None]:
    err = env.get("error") or {}
    return err.get("code"), (err.get("details") or {}).get("reason")


def dirty_count() -> int:
    return must(editor("get_editor_status"), "status")["dirty_package_count"]


def sha256(path: str) -> str:
    return hashlib.sha256((ROOT / "Content" / (path.removeprefix("/Game/") + ".uasset")).read_bytes()).hexdigest()


def content_changes() -> list[str]:
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", "Content"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8").stdout
    return sorted(line[3:].strip().strip('"') for line in out.splitlines() if line.strip())


def asset_info(path: str) -> dict:
    folder, name = path.rsplit("/", 1)
    items = must(editor("search_animations", query=name, path_prefix=folder, limit=20), f"search {name}")["items"]
    return next(i for i in items if i["name"] == name)


def spread(count: int, duration: float) -> list[float]:
    return [round(i * duration / (count - 1), 4) for i in range(count)] if count > 1 else [0.0]


def capture(name: str, asset: str, **params) -> tuple[dict, dict]:
    """capture_animation 한 번 — (봉투, 결과). 결과가 있으면 연속 프레임을 APNG 로 잇는다."""
    args = {"asset": asset, "mesh": MESH, "facing": "+Y", "output_dir": (OUT / name).as_posix(), "label": "Vesper", **params}
    env = editor("capture_animation", **args)
    res = env.get("result") or {}
    seq = res.get("sequence") or {}
    if seq.get("frames"):
        res["animation"] = apng.assemble(seq["frames"], OUT / name / "animation.png", float(seq["fps"]))
    return env, res


def summary(res: dict) -> dict:
    return {"sheet": res.get("sheet"), "compare": (res.get("compare") or {}).get("path"), "animation": (res.get("animation") or {}).get("path"),
            "animation_frames": (res.get("animation") or {}).get("frames"), "animation_bytes": (res.get("animation") or {}).get("bytes"),
            "frames": len(res.get("frames") or []), "seconds": res.get("seconds"), "camera": res.get("camera"), "bounds": res.get("bounds"),
            "edge_cells": res.get("cells_touching_edge"), "sheet_size": (res.get("layout") or {}).get("size")}


def pose_varies(res: dict) -> bool:
    centers = [tuple(r["pose_center"]) for r in (res.get("layout") or {}).get("rows") or []]
    return len(set(centers)) == len(centers) and len(centers) > 1


# ---- 섹션 ----
def section_hashes() -> None:
    print("== targets · skeleton · mesh hashes · content · dirty · tools (before)")
    STATE["hashes"] = {p: sha256(p) for p in HASHED}
    STATE["content_before"] = content_changes()
    STATE["dirty_before"] = dirty_count()
    st = must(editor("get_editor_status"), "status")
    names = {t["name"] for t in st["tools"]}
    check("capture_animation" in names and len(st["tools"]) == 41, f"41 tools incl. capture_animation ({len(st['tools'])})")
    roots = st["generation"].get("capture_output_roots")
    check(roots == [CAPTURE_ROOT.as_posix() + "/"], f"capture_output_roots {roots}")
    print(f"   {len(HASHED)} files hashed · Content changes before {len(STATE['content_before'])} · dirty {STATE['dirty_before']}")


def section_automation() -> None:
    print("== C++ unit test AnimGraphMcp.Generation.Capture")
    res = must(editor("run_automation_tests", filter="AnimGraphMcp.Generation.Capture", timeout=120), "run_automation_tests")
    while not res.get("done"):
        time.sleep(2.0)
        res = must(editor("poll_automation_tests", job_id=res["job_id"]), "poll tests")
    check(res.get("total") == 1 and res.get("passed") == 1 and not res.get("failed"), f"AnimGraphMcp.Generation.Capture passed ({res.get('passed')}/{res.get('total')})")
    for t in res.get("tests") or []:
        for e in t.get("errors") or []:
            print(f"   error: {e}")


def section_tool() -> None:
    print("== direct capture: KimodoSlash x2 (same input)")
    before = dirty_count()
    params = {"count": 6, "sequence": {"fps": 15}}
    env, res = capture("tool_a", KIMODO, **params)
    if not check(env.get("ok"), f"capture ok {code_of(env)}"):
        print(json.dumps(env.get("error"), ensure_ascii=False)[:2000])
        return
    frames = res["frames"]
    check(len(frames) == 12 and all(pathlib.Path(f["path"]).is_file() for f in frames), f"6 rows x 2 views written ({len(frames)})")
    check(pathlib.Path(res["sheet"]).is_file() and res["layout"]["size"][1] <= 3000, f"sheet {res['layout']['size']}")
    check([r["frame"] for r in res["layout"]["rows"]] == [0, 24, 48, 72, 96, 120], f"rows = frames {[r['frame'] for r in res['layout']['rows']]}")
    check(res["camera"]["front"]["look"] == [0, -1, 0] and res["camera"]["front"]["right"] == [1, 0, 0] and res["camera"]["side"]["right"] == [0, 1, 0],
          "camera axes: front from +Y (body left on screen right) · side from the body's right (front on screen right)")
    check(res["cells_touching_edge"] == 0, f"no cell cuts the mesh ({res['cells_touching_edge']})")
    check(pose_varies(res), "the pose changes from row to row (pose_center)")
    seq = res["sequence"] or {}
    check(seq.get("count") == 61 and not seq.get("truncated"), f"sequence 4 s at 15 fps = 61 frames ({seq.get('count')})")
    info = apng.inspect(res["animation"]["path"])
    check(info["frames"] == 61 and info["sequence_ok"] and info["fdat"] >= 60, f"APNG {info} · {res['animation']['bytes']} bytes")
    check(dirty_count() == before, f"no package dirtied ({before})")
    env2, res2 = capture("tool_b", KIMODO, **params)
    same = env2.get("ok") and [f["sha1"] for f in res2["frames"]] == [f["sha1"] for f in frames]
    check(bool(same), "same input → same pixels (SHA-1 of every cell)")
    STATE["tool"] = {**summary(res), "deterministic": bool(same), "seconds_b": res2.get("seconds"), "prepare_seconds": res["render"]["prepare_seconds"]}
    print(f"   {res['seconds']}s (prepare {res['render']['prepare_seconds']}s · sequence {seq.get('seconds')}s) · 2nd {res2.get('seconds')}s")


def section_guard() -> None:
    print("== guard: refusals write nothing and dirty nothing")
    before = dirty_count()
    cases = [
        ("outside root", {"output_dir": (ROOT / "Tools" / "mcp" / "results" / f"p82_outside_{STAMP}").as_posix()}, ("OUTPUT_PATH_NOT_ALLOWED", "CAPTURE_ROOT")),
        ("root itself", {"output_dir": CAPTURE_ROOT.as_posix()}, ("OUTPUT_PATH_NOT_ALLOWED", "CAPTURE_ROOT")),
        ("relative", {"output_dir": "Tools/mcp/results/capture/x"}, ("BAD_REQUEST", "RELATIVE_PATH")),
        ("bad facing", {"facing": "up"}, ("BAD_REQUEST", "BAD_FIELD")),
        ("compare outside import roots", {"compare": {"rows": [[(ROOT / "README.md").as_posix()]], }, "count": 1}, ("IMPORT_SOURCE_NOT_ALLOWED", None)),
        ("times and count", {"times": [0.0], "count": 2}, ("BAD_REQUEST", "CONFLICTING_FIELDS")),
    ]
    if (OUT / "tool_a").is_dir():
        cases.append(("not empty", {"output_dir": (OUT / "tool_a").as_posix()}, ("BAD_REQUEST", "OUTPUT_DIR_NOT_EMPTY")))
    for what, over, want in cases:
        args = {"asset": KIMODO, "mesh": MESH, "facing": "+Y", "output_dir": (OUT / f"guard_{what.replace(' ', '_')}").as_posix(), **over}
        env = editor("capture_animation", **args)
        got = code_of(env)
        check(not env.get("ok") and got[0] == want[0] and (want[1] is None or got[1] == want[1]), f"{what} → {got}")
        made = pathlib.Path(args["output_dir"])
        if what not in ("not empty", "root itself") and not made.is_absolute():
            continue
        if what not in ("not empty", "root itself"):
            check(not made.exists(), f"{what}: nothing written")
    env = editor("capture_animation", asset=KIMODO + "_Missing", mesh=MESH, facing="+Y", output_dir=(OUT / "guard_missing").as_posix())
    check(code_of(env)[0] == "ASSET_NOT_FOUND", f"missing asset → {code_of(env)}")
    check(dirty_count() == before, "refusals dirtied nothing")


def section_existing() -> None:
    print("== 8-1 results + KimodoSword1025 vs their source-skeleton frames")
    before = dirty_count()
    for name, (asset, frames_dir) in TARGETS.items():
        info = asset_info(asset)
        fps = info.get("frame_rate") or 30.0
        times = spread(6, float(info["length"]))
        rows = [[(frames_dir / f"{view}_{round(t * fps):05d}.png").as_posix() for view in ("front", "side")] for t in times]
        env, res = capture(name, asset, times=times, sequence={"fps": 15}, compare={"label": "source skeleton", "rows": rows})
        if not check(env.get("ok"), f"{name}: capture with compare ok {code_of(env)}"):
            print(json.dumps(env.get("error"), ensure_ascii=False)[:1500])
            continue
        check(pathlib.Path((res.get("compare") or {}).get("path", "")).is_file(), f"{name}: compare.png written {res['compare'] and res['compare']['size']}")
        check(res["cells_touching_edge"] == 0 and pose_varies(res), f"{name}: no cut cell · the pose changes")
        check(res["animation"]["frames"] == res["sequence"]["count"], f"{name}: APNG {res['animation']['frames']} frames · {res['animation']['bytes']} bytes")
        STATE["captures"][name] = {"asset": asset, "length": info["length"], **summary(res)}
    check(dirty_count() == before, "captures dirtied nothing")


def section_chain() -> None:
    print("== anim_gen job: BVH → blender render → retarget → capture (same rows · compare · APNG)")
    if not CMU_BVH.is_file():
        check(False, f"no CMU BVH at {CMU_BVH} (Phase 4 fixture)")
        return
    req = {"target_skeleton": VESPER, "target_mesh": MESH, "hero": "Vesper", "family": "Mocap", "animation_name": "AS_Vesper_Mocap_JumpCaptureP82",
           "description": "Phase 8-2 통합 — CMU 01_01 0~3초", "motion_category": "locomotion", "loop": False, "frame_rate": 30,
           "motion_file": {"path": CMU_BVH.as_posix(), "range": {"start": 0.0084, "end": 3.0}}, "provider": "blender", "output_path": RUN,
           "retarget": {"source_pelvis": "Hips", "source_chains": CMU_CHAINS},
           "review": {"render": {"count": 4}, "capture": {}}}
    plan = must(SERVICE.plan_motion_generation(request=req), "plan chain")
    cand = plan["candidates"][0]
    steps = [s["step"] for s in cand["steps"]]
    cap_step = cand["steps"][-1]
    check(steps[-2:] == ["validate", "capture"] and cap_step["inputs"]["rows_from"] == "render" and cap_step["inputs"]["compare"]
          and cap_step["inputs"]["facing"] == "+Y", f"plan steps {steps} · capture inputs rows_from/compare/facing")
    check("REVIEW_CAPTURE_PREVIEW_ONLY" in [lm["code"] for lm in cand["expected_limitations"]], "plan limitation REVIEW_CAPTURE_PREVIEW_ONLY")
    t0 = time.time()
    env = SERVICE.generate_motion(plan_id=plan["plan_id"], save=True)
    job = env["result"] if env["ok"] else env["error"]["details"]["job"]
    while job["status"] == "RUNNING" and time.time() - t0 < 600:
        time.sleep(2.0)
        env = SERVICE.get_generation_status(job_id=job["job_id"])
        job = env["result"] if env["ok"] else env["error"]["details"].get("job", job)
    seconds = round(time.time() - t0, 1)
    if not check(job["status"] == "SUCCEEDED", f"job SUCCEEDED ({seconds}s)"):
        print(json.dumps(job.get("error"), ensure_ascii=False)[:2000])
        return
    review = job.get("review") or {}
    cap = review.get("capture") or {}
    check(review.get("shows") == "source_skeleton" and cap.get("ok") and cap.get("shows") == "target_mesh", "job review = source render + capture")
    check(cap.get("rows_from") == "render" and len(cap.get("frames") or []) == 8, f"capture rows follow the render ({cap.get('rows_from')}, {len(cap.get('frames') or [])} cells)")
    # 행은 시각으로 맞는다 — 프레임 번호는 각자의 fps(소스 BVH 120 · 애셋 30)라 다르다. 시각 차는 애셋 반 프레임 안
    render_times = sorted({(f["row"], f["time"]) for f in review.get("frames") or []})
    capture_times = sorted({(f["row"], f["time"]) for f in cap.get("frames") or []})
    snapped = [abs(f["frame_time"] - f["time"]) for f in cap.get("frames") or []]
    check(render_times == capture_times and max(snapped) <= 0.5 / 30 + 1e-6, f"same row times {render_times} (capture snap ≤ {max(snapped):.4f}s)")
    check(bool(cap.get("compare_sheet")) and pathlib.Path(cap["compare_sheet"]).is_file(), "compare sheet written")
    anim = cap.get("animation") or {}
    check(bool(anim) and apng.inspect(anim["path"])["frames"] == (cap.get("sequence") or {}).get("count"), f"APNG {anim.get('frames')} frames")
    check(pathlib.Path(cap.get("dir", "")).as_posix() == (CAPTURE_ROOT / job["job_id"] / "A1").as_posix(), f"capture dir {cap.get('dir')}")
    STATE["chain"] = {"job_id": job["job_id"], "seconds": seconds, "asset": (job.get("generated_assets") or [None])[0], "sheet": cap.get("sheet"),
                      "compare": cap.get("compare_sheet"), "animation": anim.get("path"), "render_sheet": review.get("sheet"),
                      "limitations": [lm["code"] for lm in job["limitations"]]}


def section_dirty() -> None:
    print("== hashes · content · dirty (after)")
    if "hashes" in STATE:
        changed = [p for p, h in STATE["hashes"].items() if sha256(p) != h]
        check(not changed, f"targets · skeleton · mesh .uasset SHA-256 unchanged ({len(STATE['hashes'])} files, changed {changed})")
    if "dirty_before" in STATE:
        check(dirty_count() == STATE["dirty_before"], f"unsaved packages unchanged ({STATE['dirty_before']})")
    if "content_before" in STATE:
        new = [p for p in content_changes() if p not in STATE["content_before"]]
        outside = [p for p in new if not p.startswith("Content/" + RUN.removeprefix("/Game/") + "/")]
        print(f"   new Content changes {len(new)} (outside the run folder: {outside})")
        check(not outside, "Content/ changes are only this run's folder (captures create no assets)")
        STATE["content_new"] = new


SECTIONS = {"hashes": section_hashes, "automation": section_automation, "tool": section_tool, "guard": section_guard,
            "existing": section_existing, "chain": section_chain, "dirty": section_dirty}


def finish() -> int:
    out = ROOT / "Tools" / "mcp" / "anim_gen_phase8_2_state.json"
    out.write_text(json.dumps(STATE, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"state -> {out.as_posix()}")
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print("  - " + f)
    print("PASS" if not FAILS else "FAIL")
    return 0 if not FAILS else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(SECTIONS), help="comma separated: " + ",".join(SECTIONS))
    args = ap.parse_args()
    t0 = time.time()
    for name in args.only.split(","):
        SECTIONS[name.strip()]()
    STATE["seconds"] = round(time.time() - t0, 1)
    return finish()


if __name__ == "__main__":
    sys.exit(main())
