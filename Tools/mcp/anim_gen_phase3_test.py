"""AI 애니 생성 Phase 3 — anim-gen-mcp(정책 · 라우터 · 폴백 · Job) 에디터 통합 테스트 (Docs/AIAnimation/DevelopmentGuide.md §14 Phase 3).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase3_test.py [--only plan,generate,...]

뜬 에디터(AnimGraphMcp 플러그인)에 붙는다. anim_gen 은 같은 프로세스에서 Service 로 부르고(mcp 섹션만 stdio 서버를 띄운다),
상태는 Saved/AnimGen/TestRuns/P3Run<시각>/ 에 격리한다(실제 Saved/AnimGen 은 건드리지 않는다). Mock 단계는 pytest
(Tools/mcp/anim_gen/tests) 가 맡는다 — 여기서는 실제 Provider(existing_motion · direct_key · retarget)만 돈다.
섹션:
  hashes   — (맨 앞) 원본 .uasset SHA-256 · Content/ git 상태 · 미저장 패키지 수 기록
  mcp      — stdio 로 anim-gen-mcp 서버를 띄워 Tool 9개 · list_motion_providers · plan_motion_generation 봉투
  plan     — 실제 에디터로 계획: 소스·미리보기 고정, 제외 사유, 허용 목록 밖 출력 거부, FREE_ONLY, 계획은 애셋 0개
  generate — 완료 기준 "에디터 통합 1건": idle 요청 → existing_motion(검색) → direct_key(상체 offset_bone) → 저장 · 검증 · 같은 계획 = 같은 Job
  retarget — weapon_action 요청 + UE4 마네킹 HK 참조 → retarget 파이프(IK Rig ×2 · RTG match_existing · retarget_animations) → Vesper 저장
  reuse    — 편집 없는 같은 스켈레톤 요청 → 기존 애셋 재사용, 애셋 0개
  dirty    — (맨 뒤) 원본 해시 불변 · 미저장 패키지 수 그대로 · Content/ 변경은 이번 실행 폴더뿐
결과 애셋은 /Game/Animation/Test/AIAnimation/P3Run<시각>/ 에 저장한다(사람이 Persona 에서 볼 수 있게). 요약은 Tools/mcp/anim_gen_phase3_state.json.
"""
from __future__ import annotations

import argparse
import asyncio
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
STATE_DIR = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P3Run{STAMP}"
os.environ["ANIM_GEN_STATE_DIR"] = str(STATE_DIR)

from anim_gen.service import Service  # noqa: E402
from anim_gen.store import Store  # noqa: E402

VESPER = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
VESPER_MESH_01 = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
HERO = "/Game/Animation/Hero/Vesper"
AIM_IDLE = f"{HERO}/Rifle/Aim/AS_Vesper_Rifle_AimIdle"
KATANA_SLASH1 = "/Game/Assets/CombatMasterAnimBundle/Animations/HandsomeKatanaAnims/Mannequin_UE4/RootMotion/Attack/Katana_Attack_Slash1"
UE4_HK = "/Game/Assets/CombatMasterAnimBundle/Demo/Characters/Mannequin_UE4/Meshes/SK_Mannequin_Skeleton_HK"
SOURCES = [AIM_IDLE, KATANA_SLASH1]
RUN = f"/Game/Animation/Test/AIAnimation/P3Run{STAMP}"
UPPER_TWIST = [{"op": "offset_bone", "targets": [{"bone": b, "rotation": {"pitch": 0, "yaw": 15, "roll": 0}} for b in ("spine_01", "spine_02", "spine_03")],
                "space": "component", "blend_in": 0.3, "blend_out": 0.3}]
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
        print(f"   diag[{d['level']}] {d['code']}: {d['message'][:160]}")
    return env["result"]


def editor(tool: str, **params) -> dict:
    return bridge.call(tool, params, timeout=bridge.COMPILE_TIMEOUT)


def dirty_count() -> int:
    return must(editor("get_editor_status"), "status")["dirty_package_count"]


def uasset(path: str) -> pathlib.Path:
    return ROOT / "Content" / (path.removeprefix("/Game/") + ".uasset")


def sha256(path: str) -> str:
    return hashlib.sha256(uasset(path).read_bytes()).hexdigest()


def content_changes() -> list[str]:
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", "Content"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8").stdout
    return sorted(line[3:].strip().strip('"') for line in out.splitlines() if line.strip())


def base_request(**overrides) -> dict:
    req = {"target_skeleton": VESPER, "hero": "Vesper", "family": "Rifle", "animation_name": "AS_Vesper_Rifle_AimIdle_TwistP3",
           "description": "조준 대기에서 상체를 왼쪽으로 45° 비튼 자세 (spine_01~03 각 15°)", "motion_category": "idle", "loop": True,
           "duration_seconds": 1.333, "frame_rate": 30, "search": {"query": "rifle aim idle", "path_prefix": f"{HERO}/Rifle"},
           "edits": {"operations": UPPER_TWIST}, "output_path": RUN}
    req.update(overrides)
    return {k: v for k, v in req.items() if v is not ...}


def exists(path: str) -> bool:
    name = path.rsplit("/", 1)[1]
    items = must(editor("search_animations", query=name, path_prefix=path.rsplit("/", 1)[0], **{"class": "all"}), "exists")["items"]
    return any(i["name"] == name for i in items)


# ---- 섹션 ----
def section_hashes() -> None:
    print("== source hashes · content · dirty (before)")
    STATE["source_hashes"] = {p: sha256(p) for p in SOURCES}
    STATE["content_before"] = content_changes()
    STATE["dirty_before"] = dirty_count()
    print(f"   {len(SOURCES)} sources hashed · Content changes before: {len(STATE['content_before'])} · dirty {STATE['dirty_before']}")


def section_mcp() -> None:
    print("== anim-gen-mcp over stdio")
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    def payload(result) -> dict:
        sc = getattr(result, "structured_content", None)
        if sc:
            return sc.get("result", sc) if isinstance(sc, dict) and set(sc.keys()) == {"result"} else sc
        for block in result.content or []:
            if getattr(block, "type", "") == "text":
                return json.loads(block.text)
        return {}

    async def run() -> dict:
        params = StdioServerParameters(command=str(ROOT / "Tools" / "mcp" / ".venv" / "Scripts" / "python.exe"),
                                       args=[str(ROOT / "Tools" / "mcp" / "anim_gen" / "server.py")], cwd=str(ROOT),
                                       env={**os.environ, "ANIM_GEN_STATE_DIR": str(STATE_DIR / "stdio")})
        out: dict = {}
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                out["server"] = init.server_info.name
                out["tools"] = sorted(t.name for t in (await session.list_tools()).tools)
                out["providers"] = payload(await session.call_tool("list_motion_providers", {}))
                out["plan"] = payload(await session.call_tool("plan_motion_generation", {"request": base_request(animation_name="AS_Vesper_Rifle_AimIdle_StdioP3")}))
        return out

    out = asyncio.run(run())
    check(out["server"] == "anim-gen-mcp", f"server name {out['server']}")
    check(len(out["tools"]) == 9, f"9 tools: {out['tools']}")
    # Phase 7 — 파이프 package · anim_bp 가 더해져 9개, Phase 8-2 — 파이프 review 가 더해져 10개(Provider 6 + 파이프 retarget · package · anim_bp · review)
    check(out["providers"].get("ok") and len(out["providers"]["result"]["providers"]) == 10, "list_motion_providers envelope ok (10 = 6 providers + 4 pipes)")
    plan = out["plan"]
    check(plan.get("ok") and plan["result"]["executable"], "plan_motion_generation over stdio is executable (editor reached through bridge.py)")
    STATE["mcp"] = {"tools": out["tools"], "plan_ok": plan.get("ok")}


def section_plan() -> None:
    print("== plan (read-only)")
    before = dirty_count()
    env = SERVICE.plan_motion_generation(request=base_request())
    plan = must(env, "plan idle")
    [cand] = plan["candidates"]
    resolve, edit = cand["steps"][0], cand["steps"][1]
    print(f"   picked {resolve['resolved']['source']} (alternatives {[a['source'].rsplit('/', 1)[1] for a in resolve['alternatives']]})")
    check(resolve["resolved"]["source"] == AIM_IDLE and resolve["resolved"]["skeleton"] == VESPER, "search pins AS_Vesper_Rifle_AimIdle on Vesper")
    check(cand["chain"] == ["existing_motion", "direct_key"] and edit["preview"] is not None, "chain existing_motion → direct_key, edits previewed")
    would = edit["preview"]["would_create"]
    check(would["allowed"] is True and would["exists"] is False, f"preview would_create allowed={would['allowed']} exists={would['exists']}")
    ex = {e["provider"]: (e["cause"], e["reason"]) for e in plan["excluded"]}
    # local_ai 는 Phase 5 부터 구현 — 이 요청엔 prompt 가 없어 MISSING_INPUT(Kimodo 가 없는 PC 면 NOT_INSTALLED)
    check(set(ex) == {"local_ai", "external.meshy"} and ex["external.meshy"] == ("APPROVAL_REQUIRED", "PAID_API_DISABLED")
          and ex["local_ai"] in (("UNSUPPORTED_REQUEST", "MISSING_INPUT"), ("PROVIDER_UNAVAILABLE", "NOT_INSTALLED")), f"excluded {ex}")
    env = SERVICE.plan_motion_generation(request=base_request(output_path=f"{HERO}/Generated"))
    check(not env["ok"] and env["error"]["code"] == "OUTPUT_PATH_NOT_ALLOWED", "output_path outside GenerationOutputPaths -> OUTPUT_PATH_NOT_ALLOWED")
    must(SERVICE.set_generation_policy(patch={"mode": "FREE_ONLY"}), "FREE_ONLY")
    plan_free = must(SERVICE.plan_motion_generation(request=base_request()), "plan FREE_ONLY")
    check({e["provider"]: e["reason"] for e in plan_free["excluded"]}.get("external.meshy") == "POLICY_FREE_ONLY", "FREE_ONLY -> meshy excluded POLICY_FREE_ONLY")
    must(SERVICE.set_generation_policy(reset=True), "reset policy")
    check(dirty_count() == before, f"planning left the dirty count unchanged ({before})")
    check(not exists(f"{RUN}/AS_Vesper_Rifle_AimIdle_TwistP3"), "planning created no asset")
    STATE["plan"] = {"plan_id": plan["plan_id"], "picked": resolve["resolved"]["source"], "risks": cand["risks"],
                     "expected_limitations": [lim["code"] for lim in cand["expected_limitations"]]}


def section_generate() -> None:
    print("== generate (criterion: one editor integration — existing_motion + direct_key)")
    plan = must(SERVICE.plan_motion_generation(request=base_request()), "plan")
    t0 = time.time()
    env = SERVICE.generate_motion(plan_id=plan["plan_id"], save=True)
    job = must(env, "generate_motion")
    seconds = round(time.time() - t0, 2)
    final = f"{RUN}/AS_Vesper_Rifle_AimIdle_TwistP3"
    check(job["status"] == "SUCCEEDED" and [e["to"] for e in job["events"]] == ["QUEUED", "RUNNING", "SUCCEEDED"], "job QUEUED → RUNNING → SUCCEEDED")
    check(job["generated_assets"] == [final] and job["provider"] == "existing_motion", f"generated {job['generated_assets']}")
    check(job["validation"]["status"] == "PASSED", f"built-in validation {job['validation']['status']}")
    check(exists(final), "the asset exists in the editor (saved)")
    check(uasset(final).is_file(), f"{uasset(final).relative_to(ROOT).as_posix()} written to disk")
    v = must(editor("validate_animation", assets=[final], sources=[AIM_IDLE], skeleton=VESPER), "validate result")["assets"][0]
    print(f"   validate vs source: status {v['status']} · length {v['numeric']['length']} · relative {json.dumps(v.get('relative', {}), ensure_ascii=False)[:300]}")
    check(v["status"] != "FAILED" and abs(v["numeric"]["length"] - 1.3333) < 0.04, "result validates and keeps the source length")
    codes = [lim["code"] for lim in job["limitations"]]
    print(f"   limitations {codes} · {seconds}s")
    check(all({"code", "message", "source"} <= set(lim) for lim in job["limitations"]), "limitations are {code, message, source}")
    again = SERVICE.generate_motion(plan_id=plan["plan_id"], save=True)
    check(again["ok"] and again["result"]["job_id"] == job["job_id"], "same plan -> same job (no second asset)")
    job_file = STATE_DIR / "jobs" / f"{job['job_id']}.json"
    check(job_file.is_file(), f"job record {job_file.relative_to(ROOT).as_posix()}")
    STATE["generate"] = {"job_id": job["job_id"], "asset": final, "seconds": seconds, "limitations": codes, "validation": job["validation"]["status"]}


def section_retarget() -> None:
    print("== retarget pipe (weapon_action + UE4 HK reference → Vesper)")
    req = base_request(family="Katana", animation_name="AS_Vesper_Katana_Slash1P3", motion_category="weapon_action", loop=False,
                       duration_seconds=..., frame_rate=..., search=..., edits=..., reference_animations=[KATANA_SLASH1],
                       target_mesh=VESPER_MESH_01, constraints={"two_hand_weapon_grip": True},
                       description="UE4 마네킹 HK 카타나 베기 1을 Vesper 로 리타깃")
    plan = must(SERVICE.plan_motion_generation(request=req), "plan retarget")
    [cand] = plan["candidates"]
    rt = cand["steps"][1]
    print(f"   source mesh {rt['inputs']['source_mesh']} ({rt['inputs']['source_mesh_source']}) · risks {cand['risks']}")
    check(cand["chain"] == ["existing_motion", "retarget"] and cand["steps"][0]["resolved"]["skeleton"] == UE4_HK, "chain existing_motion → retarget from the HK skeleton")
    check(bool(rt["inputs"]["source_mesh"]) and rt["inputs"]["ops"] == "match_existing", "source mesh pinned in the plan, ops match_existing")
    # Phase 8-1 기대된 변화 — two_hand_weapon_grip 이면 관통은 재기만(위팔 보정이 양손을 벌리지 않게, 지침서 개정 11)
    check(rt["inputs"]["body_clearance"] == "measure" and rt["inputs"]["body_clearance_from"] == "grip_flag"
          and "BODY_CLEARANCE_MEASURED_FOR_GRIP" in [lim["code"] for lim in cand["expected_limitations"]],
          "grip flag → body_clearance measure (Phase 8-1 expected change)")
    t0 = time.time()
    job = must(SERVICE.generate_motion(plan_id=plan["plan_id"], save=True), "generate retarget")
    seconds = round(time.time() - t0, 2)
    final = f"{RUN}/AS_Vesper_Katana_Slash1P3"
    check(job["status"] == "SUCCEEDED" and job["generated_assets"] == [final], f"generated {job['generated_assets']}")
    work = f"{RUN}/Work/{job['job_id']}/A1"
    check(sorted(job["intermediate_assets"]) == sorted([f"{work}/IK_Source", f"{work}/IK_Target", f"{work}/RTG_Retarget"]), f"intermediates {job['intermediate_assets']}")
    check(job["validation"]["status"] in ("PASSED", "PASSED_WITH_WARNINGS"), f"retarget validation {job['validation']['status']}")
    check("GRIP_NOT_VALIDATED" in [lim["code"] for lim in job["limitations"]], "weapon_action result carries GRIP_NOT_VALIDATED")
    check(exists(final) and uasset(final).is_file(), "retargeted asset saved")
    STATE["retarget"] = {"job_id": job["job_id"], "asset": final, "source_mesh": rt["inputs"]["source_mesh"], "seconds": seconds,
                         "validation": job["validation"]["status"], "limitations": [lim["code"] for lim in job["limitations"]],
                         "body_clearance": rt["inputs"]["body_clearance"]}


def section_reuse() -> None:
    print("== reuse (same skeleton, no edits)")
    before = dirty_count()
    plan = must(SERVICE.plan_motion_generation(request=base_request(animation_name="AS_Vesper_Rifle_AimIdle_ReuseP3", edits=...)), "plan reuse")
    job = must(SERVICE.generate_motion(plan_id=plan["plan_id"], save=True), "generate reuse")
    check(job["reused_assets"] == [AIM_IDLE] and job["generated_assets"] == [], f"reused {job['reused_assets']}")
    check("REUSED_EXISTING" in [lim["code"] for lim in job["limitations"]], "limitation REUSED_EXISTING")
    check(not exists(f"{RUN}/AS_Vesper_Rifle_AimIdle_ReuseP3") and dirty_count() == before, "nothing created or dirtied")


def section_dirty() -> None:
    print("== source hashes · content · dirty (after)")
    if "source_hashes" in STATE:
        changed = [p for p, h in STATE["source_hashes"].items() if sha256(p) != h]
        check(not changed, f"source .uasset SHA-256 unchanged ({len(STATE['source_hashes'])} files)")
    if "dirty_before" in STATE:
        check(dirty_count() == STATE["dirty_before"], f"unsaved packages unchanged ({STATE['dirty_before']}) — every write was saved")
    if "content_before" in STATE:
        new = [p for p in content_changes() if p not in STATE["content_before"]]
        run_dir = "Content/" + RUN.removeprefix("/Game/") + "/"
        outside = [p for p in new if not p.startswith(run_dir)]
        print(f"   new Content changes {len(new)} (outside this run's folder: {outside})")
        check(not outside, "Content/ changes are only this run's folder")
        STATE["content_new"] = new


SECTIONS = {"hashes": section_hashes, "mcp": section_mcp, "plan": section_plan, "generate": section_generate, "retarget": section_retarget,
            "reuse": section_reuse, "dirty": section_dirty}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(SECTIONS), help="comma separated: " + ",".join(SECTIONS))
    args = ap.parse_args()
    t0 = time.time()
    for name in args.only.split(","):
        SECTIONS[name.strip()]()
    STATE["seconds"] = round(time.time() - t0, 1)
    out = ROOT / "Tools" / "mcp" / "anim_gen_phase3_state.json"
    out.write_text(json.dumps(STATE, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"state -> {out.as_posix()}")
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print("  - " + f)
    print("PASS" if not FAILS else "FAIL")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
