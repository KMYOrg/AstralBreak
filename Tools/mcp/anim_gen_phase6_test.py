"""AI 애니 생성 Phase 6 — external.meshy(Meshy Text-to-Motion) 실제 어댑터 · 에디터 통합 테스트 (Docs/AIAnimation/DevelopmentGuide.md §14 Phase 6).

    PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase6_test.py [--only ...]
    # 유료 1건 (완료 기준 ①) — 키는 이 명령을 실행하는 셸에만: PowerShell  $env:MESHY_API_KEY = "<키>"  (채팅 · 파일에 쓰지 않는다)
    Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase6_test.py --only hashes,state,blocked,real,dirty --real --usd-per-credit 0.02

뜬 에디터(AnimGraphMcp 플러그인)를 쓴다. anim_gen 은 같은 프로세스의 Service 로 부르고, 상태는 Saved/AnimGen/TestRuns/P6Run<시각>/ 에 격리한다
(사용자의 Saved/AnimGen/policy.json · 장부는 건드리지 않는다). Mock 단계(키 없음 · 인증 실패 · Rate Limit · 생성 실패 · 결과 만료 · 취소 ·
재제출 멱등 · 장부)는 pytest(test_meshy.py).
섹션:
  hashes   — (맨 앞) 대상 스켈레톤 · 메시 .uasset SHA-256 · Content/ git 상태 · 미저장 패키지 수
  state    — list_motion_providers: external.meshy 구현 · license ok · 공식 크레딧 가격 · 키는 있는지만(값 없음)
  blocked  — 완료 기준 ②: 외부 호출 0회. 기본 정책(유료 끔) · FREE_ONLY · 환율 없음(COST_UNKNOWN) · 유료 켬 + 승인 없음 → 계획 · 실행 ·
             승인 거부. 키가 없으면 더미 키(카나리 — 실수로 보내면 401)를 이 프로세스에만 넣는다. 확인 = 요청 로그
             (<state>/external/meshy_requests.jsonl) 없음 · 장부 비어 있음 · Meshy 결과 폴더 없음
  real     — 완료 기준 ①(유료 — --real 일 때만): 계획 · 견적(보낼 본문 · 크레딧 · USD)을 출력하고 터미널에서 plan_id 를 직접 입력해야
             승인한다(그 밖 입력 · 비대화형이면 호출 0으로 끝). 잔액 → 제출 → poll → 다운로드 → import → 자동 IK Rig → RTG match_existing
             (per_bone) → Vesper AS_ 저장 + validate_animation(소스 대비). Meshy 리그(본 · 루트 · 템플릿 · 정면)를 상태에 기록
  dirty    — (맨 뒤) 해시 불변 · 미저장 수 그대로 · Content/ 변경은 이번 실행 폴더뿐
요약은 Tools/mcp/anim_gen_phase6_state.json.
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
STATE_DIR = ROOT / "Saved" / "AnimGen" / "TestRuns" / f"P6Run{STAMP}"
os.environ["ANIM_GEN_STATE_DIR"] = str(STATE_DIR)

from anim_gen.providers import meshy  # noqa: E402
from anim_gen.service import Service  # noqa: E402
from anim_gen.store import Store  # noqa: E402

VESPER = "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"
VESPER_MESH_01 = "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01"
RUN = f"/Game/Animation/Test/AIAnimation/P6Run{STAMP}"
HASHED = [VESPER, VESPER_MESH_01]
PROMPT = "A person performs a spinning roundhouse kick, then returns to a fighting stance."
DURATION = 4.0
DUMMY_KEY = "msy_DUMMY-canary-not-a-real-key"
FAILS: list[str] = []
STATE: dict = {"run": RUN, "state_dir": STATE_DIR.as_posix()}
SERVICE = Service(store=Store(STATE_DIR))
ARGS = argparse.Namespace()


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
        print(f"   diag[{d['level']}] {d['code']}: {d['message'][:200]}")
    return env["result"]


def editor(tool: str, **params) -> dict:
    return bridge.call(tool, params, timeout=bridge.COMPILE_TIMEOUT)


def dirty_count() -> int:
    return must(editor("get_editor_status"), "status")["dirty_package_count"]


def import_root() -> pathlib.Path:
    raw = pathlib.Path(must(editor("get_editor_status"), "status")["generation"]["import_source_roots"][0])
    return raw if raw.is_absolute() else ROOT / raw


def uasset(path: str) -> pathlib.Path:
    return ROOT / "Content" / (path.removeprefix("/Game/") + ".uasset")


def sha256(path: str) -> str:
    return hashlib.sha256(uasset(path).read_bytes()).hexdigest()


def content_changes() -> list[str]:
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", "Content"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8").stdout
    return sorted(line[3:].strip().strip('"') for line in out.splitlines() if line.strip())


def request_log(state_dir: pathlib.Path) -> list[dict]:
    path = state_dir / "external" / meshy.LOG_NAME
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def base_request(**overrides) -> dict:
    req = {"target_skeleton": VESPER, "target_mesh": VESPER_MESH_01, "hero": "Vesper", "family": "Meshy",
           "animation_name": "AS_Vesper_Meshy_SpinKickP6", "description": "돌려차기 후 전투 자세로 복귀 (Meshy)",
           "motion_category": "full_body_new", "loop": False, "frame_rate": 30, "duration_seconds": DURATION, "prompt": PROMPT,
           "provider": "external.meshy", "output_path": RUN}
    req.update(overrides)
    return {k: v for k, v in req.items() if v is not ...}


def wait_job(service: Service, job: dict, limit: float = 1200.0) -> tuple[dict, float]:
    t0 = time.time()
    last = None
    while job["status"] == "RUNNING" and time.time() - t0 < limit:
        time.sleep(3.0)
        env = service.get_generation_status(job_id=job["job_id"])
        job = env["result"] if env["ok"] else env["error"]["details"].get("job", job)
        note = (job.get("stage"), job["status"])
        if note != last:
            print(f"   {round(time.time() - t0)}s · stage {job.get('stage')} · {job['status']}")
            last = note
    return job, round(time.time() - t0, 2)


# ---- 섹션 ----
def section_hashes() -> None:
    print("== target hashes · content · dirty (before)")
    STATE["hashes"] = {p: sha256(p) for p in HASHED}
    STATE["content_before"] = content_changes()
    STATE["dirty_before"] = dirty_count()
    print(f"   {len(HASHED)} assets hashed · Content changes before: {len(STATE['content_before'])} · dirty {STATE['dirty_before']}")


def section_state() -> None:
    print("== external.meshy provider state")
    providers = {p["name"]: p for p in must(SERVICE.list_motion_providers(), "providers")["providers"]}
    p = providers["external.meshy"]
    state, caps = p["state"], p["capabilities"]
    print(f"   key {state['auth']} · license {state['license']} · pricing {p['pricing']} · credits {caps['pricing']['credits']}")
    check(state["implemented"] and caps["license"] == "ok", "external.meshy implemented · license ok (Meshy terms accepted 2026-10-25)")
    check(caps["paid"] and caps["requires_network"] and caps["output_formats"] == ["fbx", "bvh"] and caps["max_duration_seconds"] == 10,
          "manifest: paid · network · fbx (prime) / bvh (swift) · ≤ 10 s")
    check(caps["pricing"]["credits"] == {"prime": 10, "swift": 3} and caps["model"]["duration"] == {"min": 2, "max": 10, "step": 0.5},
          "official credit prices (prime 10 · swift 3) and duration 2-10 s / 0.5 s")
    check(p["pricing"] == "unconfirmed", "money value unconfirmed by default (policy external.meshy.usd_per_credit null)")
    check(DUMMY_KEY not in json.dumps(p) and (os.environ.get("MESHY_API_KEY") or "§") not in json.dumps(p), "no key value in the listing")
    STATE["state"] = {"auth": state["auth"], "available": state["available"], "unavailable_reason": state["unavailable_reason"],
                      "pricing": p["pricing"], "credits": caps["pricing"]["credits"]}


def section_blocked() -> None:
    print("== blocked (criterion: no approval or FREE_ONLY → zero external calls, checked by the request log)")
    real_key = bool(os.environ.get("MESHY_API_KEY"))
    if not real_key:
        os.environ["MESHY_API_KEY"] = DUMMY_KEY  # 이 프로세스에만 — 실수로 보내면 Meshy 가 401 로 거절하고 요청 로그에 남는다
    state_dir = STATE_DIR / "Blocked"
    svc = Service(store=Store(state_dir))
    roots = import_root()
    meshy_dir = roots / "Meshy"
    before_dirs = sorted(p.name for p in meshy_dir.iterdir()) if meshy_dir.is_dir() else []
    results = {}

    def case(name: str, patch: dict, expect_cause: str, expect_reason: str | None) -> None:
        must(svc.set_generation_policy(patch=patch, reset=True), f"policy {name}")
        plan = must(svc.plan_motion_generation(request=base_request(animation_name=f"AS_Vesper_Meshy_Blocked{name}P6")), f"plan {name}")
        ex = {e["provider"]: e for e in plan["excluded"]}.get("external.meshy", {})
        env = svc.generate_motion(plan_id=plan["plan_id"])
        appr = svc.approve_generation(plan_id=plan["plan_id"], max_cost_usd=1.0)
        reason = (env.get("error") or {}).get("details", {}).get("reason")
        print(f"   {name}: excluded {ex.get('cause')} {str(ex.get('reason'))[:60]} · generate {(env.get('error') or {}).get('code')} {reason} · "
              f"approve {(appr.get('error') or {}).get('code')} {(appr.get('error') or {}).get('details', {}).get('reason')}")
        check(not plan["executable"] and ex.get("cause") == expect_cause and (expect_reason is None or ex.get("reason") == expect_reason),
              f"{name}: plan excludes external.meshy {expect_cause} {expect_reason or ''}")
        check(not env["ok"] and not appr["ok"], f"{name}: generate_motion and approve_generation refuse")
        results[name] = {"excluded": (ex.get("cause"), ex.get("reason")), "generate": (env["error"]["code"], reason),
                         "approve": (appr["error"]["code"], appr["error"].get("details", {}).get("reason"))}

    case("PaidDisabled", {}, "APPROVAL_REQUIRED", "PAID_API_DISABLED")
    case("FreeOnly", {"mode": "FREE_ONLY", "billing": {"paid_api_enabled": True, "max_cost_per_job_usd": 1, "max_total_cost_usd": 1},
                      "external": {"meshy": {"usd_per_credit": 0.02}}}, "APPROVAL_REQUIRED", "POLICY_FREE_ONLY")
    case("RateUnset", {"billing": {"paid_api_enabled": True, "max_cost_per_job_usd": 1, "max_total_cost_usd": 1}}, "COST_UNKNOWN", None)
    # 유료 켬 + 환율 — 후보가 되지만 승인이 없다 → 대기, 호출 0
    must(svc.set_generation_policy(patch={"billing": {"paid_api_enabled": True, "max_cost_per_job_usd": 1, "max_total_cost_usd": 1},
                                          "external": {"meshy": {"usd_per_credit": 0.02}}}, reset=True), "policy NoApproval")
    plan = must(svc.plan_motion_generation(request=base_request(animation_name="AS_Vesper_Meshy_BlockedNoApprovalP6")), "plan NoApproval")
    cand = plan["candidates"][0] if plan["candidates"] else {}
    est = must(svc.estimate_generation_cost(plan_id=plan["plan_id"]), "estimate")["candidates"][0]
    print(f"   NoApproval: body {cand['steps'][0]['inputs']['request_body']} · {est['credits']} credits · ${est['estimate_usd']} · verdict {est['verdict']}")
    check(cand.get("provider") == "external.meshy" and est["verdict"] == "needs_approval" and est["credits"] == 10 and est["estimate_usd"] == 0.2,
          "NoApproval: candidate with a pinned body · 10 credits × $0.02 = $0.20 · needs_approval")
    env = svc.generate_motion(plan_id=plan["plan_id"])
    job = env["error"]["details"]["job"] if not env["ok"] else env["result"]
    check(job["status"] == "WAITING_FOR_APPROVAL" and env["error"]["details"]["reason"] == "NO_APPROVAL", "NoApproval: job WAITING_FOR_APPROVAL (NO_APPROVAL)")
    status = must(svc.get_generation_status(job_id=job["job_id"]), "status")
    check(status["status"] == "WAITING_FOR_APPROVAL", "NoApproval: polling a waiting job calls nothing")
    must(svc.cancel_generation(job_id=job["job_id"]), "cancel waiting job")
    results["NoApproval"] = {"estimate": {k: est[k] for k in ("credits", "estimate_usd", "verdict", "basis")}, "job": job["status"]}
    log = request_log(state_dir)
    after_dirs = sorted(p.name for p in meshy_dir.iterdir()) if meshy_dir.is_dir() else []
    check(log == [] and not (state_dir / "external").exists(), f"request log: 0 Meshy requests ({state_dir.as_posix()}/external absent)")
    check(svc.store.ledger_entries() == [], "ledger: no reserve / submit / charge")
    check(after_dirs == before_dirs, "no Meshy result folder was created")
    if not real_key:
        del os.environ["MESHY_API_KEY"]
    STATE["blocked"] = {"cases": results, "request_log_lines": len(log), "ledger_entries": len(svc.store.ledger_entries()), "dummy_key": not real_key}


def section_real() -> None:
    print("== real (criterion ①: one approved Meshy generation → import → retarget → Vesper AS_ + validate)")
    if not ARGS.real:
        print("   skipped — pass --real (a paid call needs your approval in this terminal)")
        STATE["real"] = {"skipped": "no --real"}
        return
    if not os.environ.get("MESHY_API_KEY"):
        check(False, "MESHY_API_KEY is not set in this shell — set it here (not in chat or a file) and run again")
        return
    if not ARGS.usd_per_credit:
        check(False, "--usd-per-credit is required — your Meshy plan's USD per credit (e.g. Pro: plan price / 1,000 credits)")
        return
    mode = ARGS.mode
    credits = {"prime": 10, "swift": 3}[mode]
    estimate = round(credits * ARGS.usd_per_credit, 4)
    cap = ARGS.max_usd or estimate
    must(SERVICE.set_generation_policy(patch={"billing": {"paid_api_enabled": True, "max_cost_per_job_usd": cap, "max_total_cost_usd": cap},
                                              "external": {"meshy": {"usd_per_credit": ARGS.usd_per_credit}}}), "policy (this run's state dir only)")
    req = base_request(prompt=ARGS.prompt, duration_seconds=ARGS.duration, animation_name=ARGS.name,
                       generation={"options": {"external.meshy": {"mode": mode}}})
    plan = must(SERVICE.plan_motion_generation(request=req), "plan")
    if not plan["candidates"]:
        check(False, f"no Meshy candidate: {json.dumps(plan['excluded'], ensure_ascii=False)[:1500]}")
        return
    cand = plan["candidates"][0]
    body = cand["steps"][0]["inputs"]["request_body"]
    est = must(SERVICE.estimate_generation_cost(plan_id=plan["plan_id"]), "estimate")["candidates"][0]
    print()
    print("  ┌ Meshy 유료 호출 승인 요청 ─────────────────────────────")
    print(f"  │ 보낼 본문   {json.dumps(body, ensure_ascii=False)}")
    print(f"  │ 비용        {est['credits']} 크레딧 × ${ARGS.usd_per_credit:g} = ${est['estimate_usd']}  (상한 ${cap})")
    print(f"  │ 근거        {est['basis']}")
    print(f"  │ 사슬        {' → '.join(cand['chain'])} → {RUN}/{req['animation_name']}")
    print(f"  │ 위험        {cand['risks']}")
    print(f"  │ 예상 한계   {[lim['code'] for lim in cand['expected_limitations']]}")
    print(f"  │ 보내지 않는 것: 캐릭터 · 스켈레톤 · 애셋 (프롬프트 · 길이 · 모드만)")
    print("  └────────────────────────────────────────────────────────")
    try:
        typed = input(f"  승인하려면 plan_id 를 그대로 입력하세요 ({plan['plan_id']}), 그 밖은 취소: ").strip()
    except EOFError:
        typed = ""
    if typed != plan["plan_id"]:
        print("   취소 — Meshy 에 아무것도 보내지 않았습니다")
        check(request_log(STATE_DIR) == [], "declined: 0 Meshy requests")
        STATE["real"] = {"declined": True, "plan_id": plan["plan_id"]}
        return
    approval = must(SERVICE.approve_generation(plan_id=plan["plan_id"], max_cost_usd=cap, max_attempts=1), "approve")
    t0 = time.time()
    env = SERVICE.generate_motion(plan_id=plan["plan_id"], save=True)
    job = env["result"] if env["ok"] else (env["error"].get("details") or {}).get("job")
    if job is None:
        check(False, f"generate_motion: {json.dumps(env.get('error'), ensure_ascii=False)[:1500]}")
        STATE["real"] = {"plan_id": plan["plan_id"], "error": env.get("error"), "request_log": request_log(STATE_DIR)}
        return
    handle = (job.get("pending") or {}).get("handle") or {}
    check(job["status"] == "RUNNING" and bool(handle.get("task_id")),
          f"submitted: task {handle.get('task_id')} · balance before {handle.get('balance_before')} · status {job['status']}")
    job, waited = wait_job(SERVICE, job)
    seconds = round(time.time() - t0, 2)
    gen = next((d.get("task") for d in job.get("diagnostics", []) if d.get("code") == "MESHY_GENERATED"), None)
    out = {"plan_id": plan["plan_id"], "approval_id": approval["approval_id"], "body": body, "estimate": {k: est.get(k) for k in ("credits", "estimate_usd", "basis")},
           "job_id": job["job_id"], "status": job["status"], "seconds": seconds, "meshy": gen, "cost": job.get("cost"),
           "ledger": SERVICE.store.ledger_totals(), "error": job.get("error"), "fallback_history": job.get("fallback_history"),
           "limitations": [lim["code"] for lim in job.get("limitations", [])],
           "diagnostics": [{k: d.get(k) for k in ("level", "code", "message", "tool", "step")} for d in job.get("diagnostics", [])]}
    STATE["real"] = out
    print(f"   job {job['status']} in {seconds}s · cost {job.get('cost')} · ledger {out['ledger']}")
    if gen:
        print(f"   Meshy: task {gen['task_id']} · {gen['format']} {gen['bytes']} B · {gen['duration_ms']} ms · {gen['consumed_credits']} credits · "
              f"{gen['seconds']}s on Meshy · {gen['file']}")
    check(bool(gen) and pathlib.Path(gen["file"]).is_file() and gen["file"].startswith(import_root().as_posix()),
          "result downloaded under ImportSourceRoots/Meshy/<job>/A1")
    log = request_log(STATE_DIR)
    out["request_log"] = [{k: e.get(k) for k in ("method", "endpoint", "status", "ms", "host")} for e in log]
    check(sum(1 for e in log if e["method"] == "POST") == 1, f"exactly one submission (request log: {[(e['method'], e['endpoint'], e['status']) for e in log]})")
    key = os.environ.get("MESHY_API_KEY") or "§"
    leaked = [f.as_posix() for root in (STATE_DIR, import_root() / "Meshy" / job["job_id"]) for f in root.rglob("*") if f.is_file()
              and key in f.read_text(encoding="utf-8", errors="replace")]
    check(not leaked, f"the key value is in no state / log / result file ({leaked})")
    # 소스(임포트한 Meshy 클립) — 리그를 기록한다
    work = job.get("work_path")
    imported = must(editor("search_animations", path_prefix=f"{work}/Import", **{"class": "AnimSequence"}), "imported anims")["items"] if work else []
    source = imported[0] if imported else None
    if source:
        skel = must(editor("inspect_skeleton", skeleton=source["skeleton"].split(".")[0], details=True), "inspect Meshy skeleton")
        out["rig"] = {"skeleton": skel.get("skeleton_path"), "bone_count": skel.get("bone_count"), "root_bone": skel.get("root_bone"),
                      "bones": [{"name": b["name"], "parent": b.get("parent")} for b in skel.get("bones", [])],
                      "template_match": skel.get("template_match"), "source_anim": source["asset_path"], "length": source.get("length"),
                      "frame_rate": source.get("frame_rate"), "facing": ((job.get("cursor") or {}).get("values") or {}).get("facing")}
        print(f"   Meshy rig: {skel.get('bone_count')} bones · root {skel.get('root_bone')} · template {skel.get('template_match')} · "
              f"facing {out['rig']['facing']} · source {source.get('length')}s @ {source.get('frame_rate')}")
    if job["status"] != "SUCCEEDED":
        check(False, f"job {job['status']}: {json.dumps(job.get('error'), ensure_ascii=False)[:1500]}")
        bones = ((job.get("error") or {}).get("editor_error") or {}).get("details", {}).get("bones")
        if bones:
            print(f"   source bones for manual chains: {[b.get('name') for b in bones][:80]}")
        return
    final = job["generated_assets"][0]
    check(final == f"{RUN}/{req['animation_name']}", f"saved {final}")
    v = must(editor("validate_animation", assets=[final], skeleton=VESPER, **({"sources": [source["asset_path"]]} if source else {})),
             "validate result")["assets"][0]
    numeric = v.get("numeric") or {}
    rel = v.get("relative") or {}
    out["validation"] = {"status": v["status"], "numeric": {k: numeric.get(k) for k in ("length", "frames", "frame_rate", "max_rotation_step_deg")},
                         "relative": rel, "issues": [i.get("code") for i in v.get("issues", [])]}
    print(f"   validate {v['status']} · {numeric.get('frames')} frames @ {numeric.get('frame_rate')} · {numeric.get('length')}s · issues {out['validation']['issues']}")
    check(v["status"] in ("PASSED", "PASSED_WITH_WARNINGS"), f"validate_animation against the Meshy source: {v['status']}")
    check(uasset(final).is_file(), "AS_ saved to disk")


def section_dirty() -> None:
    print("== target hashes · content · dirty (after)")
    if "hashes" in STATE:
        changed = [p for p, h in STATE["hashes"].items() if sha256(p) != h]
        check(not changed, f"target skeleton · mesh .uasset SHA-256 unchanged ({len(STATE['hashes'])} files)")
    if "dirty_before" in STATE:
        check(dirty_count() == STATE["dirty_before"], f"unsaved packages unchanged ({STATE['dirty_before']}) — every write was saved")
    if "content_before" in STATE:
        new = [p for p in content_changes() if p not in STATE["content_before"]]
        run_dir = "Content/" + RUN.removeprefix("/Game/") + "/"
        outside = [p for p in new if not p.startswith(run_dir)]
        print(f"   new Content changes {len(new)} (outside this run's folder: {outside})")
        check(not outside, "Content/ changes are only this run's folder")
        STATE["content_new"] = new


SECTIONS = {"hashes": section_hashes, "state": section_state, "blocked": section_blocked, "real": section_real, "dirty": section_dirty}


def main() -> int:
    global ARGS
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="hashes,state,blocked,dirty", help="comma separated: " + ",".join(SECTIONS))
    ap.add_argument("--real", action="store_true", help="allow the paid section (it still asks for the plan_id in this terminal)")
    ap.add_argument("--usd-per-credit", type=float, default=None, help="your Meshy plan's USD per credit")
    ap.add_argument("--max-usd", type=float, default=None, help="approval cap (default = the estimate)")
    ap.add_argument("--mode", choices=("prime", "swift"), default="prime")
    ap.add_argument("--prompt", default=PROMPT)
    ap.add_argument("--duration", type=float, default=DURATION)
    ap.add_argument("--name", default="AS_Vesper_Meshy_SpinKickP6")
    ARGS = ap.parse_args()
    t0 = time.time()
    for name in ARGS.only.split(","):
        SECTIONS[name.strip()]()
    STATE["seconds"] = round(time.time() - t0, 1)
    out = ROOT / "Tools" / "mcp" / "anim_gen_phase6_state.json"
    out.write_text(json.dumps(STATE, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"state -> {out.as_posix()}")
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print("  - " + f)
    print("PASS" if not FAILS else "FAIL")
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
