"""uigen 진입점 — UI 자동 생성 파이프라인 오케스트레이터 (설계 Docs/Design/ui-autogen-pipeline.md §2).

순서 · 재시도 · 분기 · 상한 · 잠금은 이 코드가 정한다. 실행 중 사람에게 묻지 않는다.

Phase 1a(손 spec):
    Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/run_pipeline.py --spec-dir Tools/uigen/fixtures/m4_combat_hud
    (+ --inject-fault offscreen|overlap|drift — normalize 뒤 spec 을 깨뜨려 재시도 경로를 돈다 · --keep-failed — 실패해도 저장)

단계: normalize → (inject_fault) → analyze → codegen → generate → refine → [build → verify → (fix → 분기)]… → finalize.
  - 시도 k 는 specs/00k.json 을 쓰고, 실패하면 fix 가 patches/00k.json 을 낸다. patch op 종류로 돌아갈 단계를 정한다(core.patch.branch_for):
    build(배치 · 슬롯 · 스타일 · 텍스트) · generate(에셋 — 그 에셋만 → refine → build) · codegen(바인딩 → 재기동 → build).
  - 상한: 재시도 limits.retries(N = 3 — 시도는 최대 N + 1 번). 두 번 연속 실패 게이트 집합이 줄지 않으면(진부분집합이 아니면) 조기 종료,
    fix 가 고칠 것을 못 내면(NO_FIX) 바로 종료.
  - finalize: 통과면 run 패키지 저장 + lineage.json, 실패 · 오류면 폐기(--keep-failed 면 저장). --until 로 멈추면 하지 않는다(에디터에 남음).
끝에는 성공 · 실패 · 미완 모두 report.json 과 지표 JSONL(metrics/uigen.jsonl — run 한 줄 + 에셋마다 한 줄)을 남긴다.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import traceback
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from core import config  # noqa: E402
from core import metrics  # noqa: E402
from core import patch as patch_mod  # noqa: E402
from core import schema  # noqa: E402
from core.run import LockBusy, Run, RunError, RunLock, new_run_id  # noqa: E402
from stages import StageError  # noqa: E402
from stages import build, codegen, fault, finalize, fix, generate, normalize, refine, verify  # noqa: E402

STAGES = ("normalize", "analyze", "codegen", "generate", "refine", "build", "verify", "finalize")

EXIT_PASS, EXIT_FAIL, EXIT_INCOMPLETE = 0, 1, 2


class StopAt(Exception):
    """--until 에 닿음."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="uigen — concept/spec → WBP prototype (Phase 1a: hand spec)")
    ap.add_argument("--spec-dir", required=True, help="hand spec folder holding brief.json + spec.json (Phase 1a)")
    ap.add_argument("--until", choices=STAGES, help="stop after this stage (first attempt for build / verify; no finalize)")
    ap.add_argument("--run-id", help="override the run id (R<yyyymmdd>_<hhmmss>_<ScreenId>)")
    ap.add_argument("--config", help="pipeline.yaml to use (default Tools/uigen/config/pipeline.yaml)")
    ap.add_argument("--work-root", help="override paths.work_root")
    ap.add_argument("--metrics", help="override paths.metrics (JSONL)")
    ap.add_argument("--module-root", help="override codegen.module_root (C++ module folder — tests write into a temp copy)")
    ap.add_argument("--inject-fault", choices=sorted(fault.FAULTS), help="break the spec after normalize to exercise the retry path (1a-4)")
    ap.add_argument("--keep-failed", action="store_true", help="save the run packages even when verify fails")
    return ap.parse_args(argv)


def _codegen_summary(run: Run) -> dict | None:
    """report.json 의 codegen 요약 — 계약 해시 · 건너뜀 · 빌드 결과 (자세한 것은 codegen.json)."""
    if not run.path("codegen.json").is_file():
        return None
    cg = run.read_json("codegen.json")
    b = cg.get("build") or {}
    return {"contract_hash": cg["contract_hash"], "skipped": cg["skipped"], "reason": cg["reason"], "bindings": len(cg["contract"]["bindings"]),
            "build": {"ran": b.get("ran", False), "ok": b.get("ok"), "result_line": b.get("result_line")},
            "verify_match": (cg.get("verify") or {}).get("match"), **({"error": cg["error"]} if cg.get("error") else {})}


def _screen_id(spec_dir: pathlib.Path) -> str:
    try:
        return json.loads((spec_dir / "brief.json").read_text(encoding="utf-8"))["screen_id"]
    except (OSError, ValueError, KeyError) as exc:
        raise RunError("INPUT_UNREADABLE", f"{spec_dir / 'brief.json'}: {exc}") from exc


def _gen_log(run: Run) -> tuple[dict[str, dict], dict[str, int]]:
    """에셋마다 마지막 gen.jsonl 줄 · 성공 횟수."""
    last: dict[str, dict] = {}
    made: dict[str, int] = {}
    p = run.path("gen.jsonl")
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            last[rec["asset_id"]] = rec
            if rec.get("ok"):
                made[rec["asset_id"]] = made.get(rec["asset_id"], 0) + 1
    return last, made


def write_metrics(run: Run, status: str, attempt: int, verify_status: str | None = None, failed_gates: list[str] | None = None,
                  fault_name: str | None = None) -> None:
    """지표 JSONL — run 한 줄 + manifest 의 에셋마다 한 줄 (설계 §4-5). verify = 마지막 verify 의 게이트 결과(돌지 않았으면 null)."""
    metrics.append(run.metrics_path, metrics.run_record(run.run_id, status, attempt, run.elapsed(), verify=verify_status, phase=run.cfg.get("phase"),
                                                        failed_gates=failed_gates or [], fault=fault_name))
    if run.path("manifest.json").is_file():
        last, made = _gen_log(run)
        for a in run.read_json("manifest.json")["assets"]:
            g = last.get(a["asset_id"], {})
            metrics.append(run.metrics_path, metrics.asset_record(run.run_id, {**a, "ok": g.get("ok", True), "duration_s": g.get("duration_s")},
                                                                   verify=verify_status, retries=max(0, made.get(a["asset_id"], 1) - 1)))


def _opts(opts: argparse.Namespace, **extra) -> types.SimpleNamespace:
    return types.SimpleNamespace(**{**vars(opts), **extra})


def _simple(run: Run, name: str, fn):
    run.stage_begin(name)
    detail = fn()
    run.stage_end(name, "ok", detail if isinstance(detail, str) else "")
    return detail


def _until(opts, name: str) -> None:
    if opts.until == name and name != "finalize":
        raise StopAt(name)


def _pipeline(run: Run, opts: argparse.Namespace, ctx: dict) -> str:
    """'pass' | 'fail' (게이트 · 재시도 끝). 단계 실패는 StageError, --until 은 StopAt."""
    limits = run.cfg["limits"]
    retries, patience = int(limits["retries"]), int(limits.get("early_stop_no_progress", 2))
    _simple(run, "normalize", lambda: normalize.run(run, opts))
    if opts.inject_fault:
        run.stage_begin("inject_fault")
        detail, ctx["fault"] = fault.inject(run, opts.inject_fault)
        run.stage_end("inject_fault", "ok", detail)
    _until(opts, "normalize")
    run.stage_begin("analyze")
    run.stage_end("analyze", "skipped", "hand_spec — spec is given (Phase 1a)")
    _until(opts, "analyze")
    for name, mod in (("codegen", codegen), ("generate", generate), ("refine", refine)):
        _simple(run, name, lambda mod=mod: mod.run(run, _opts(opts, attempt=1)))
        _until(opts, name)

    prev_failed: set[str] | None = None
    no_progress = 0
    for attempt in range(1, retries + 2):
        aopts = _opts(opts, attempt=attempt)
        spec_file = f"specs/{attempt:03d}.json"
        run.write_json(spec_file, run.read_json("spec.json"))
        row = {"attempt": attempt, "spec": spec_file, "pass": False, "failed": [], "patch": None, "branch": None, "stop": None, "build": None}
        ctx["attempts"].append(row)
        row["build"] = _simple(run, "build", lambda: build.run(run, aopts))
        _until(opts, "build")
        run.stage_begin("verify")
        res = verify.run(run, aopts)
        ctx["last"] = res
        row.update({"pass": res["pass"], "failed": res["failed"], "duration_s": res["duration_s"]})
        run.stage_end("verify", "ok" if res["pass"] else "fail", verify.summary(res))
        _until(opts, "verify")
        if res["pass"]:
            return "pass"
        failed = set(res["failed"])
        if prev_failed is not None:
            no_progress = 0 if failed < prev_failed else no_progress + 1
        prev_failed = failed
        if attempt > retries:
            row["stop"] = "RETRY_LIMIT"
            ctx["message"] = f"verify failed after {attempt} attempt(s) (retry limit {retries}) — {', '.join(res['failed'])}"
            return "fail"
        if no_progress >= patience:
            row["stop"] = "NO_PROGRESS"
            ctx["message"] = (f"verify failed after {attempt} attempt(s) — the failing gate set did not shrink {no_progress} time(s) in a row: "
                              f"{', '.join(res['failed'])}")
            return "fail"
        run.stage_begin("fix")
        prop = fix.propose(run, attempt, res)
        ctx["fixes"].extend({"attempt": attempt, **f} for f in prop["fixes"])
        if prop["patch"] is None:
            row["stop"] = "NO_FIX"
            ctx["message"] = f"verify failed at attempt {attempt} and the fixer has no op for: {', '.join(res['failed'])}"
            run.stage_end("fix", "fail", ctx["message"], code="NO_FIX")
            return "fail"
        try:
            fixed = patch_mod.apply_patch(run.read_json("spec.json"), prop["patch"])
        except patch_mod.PatchError as exc:
            raise StageError("FIX_PATCH_INVALID", f"{prop['patch_file']}: {exc}", **exc.details) from exc
        run.write_json("spec.json", fixed)
        row.update(patch=prop["patch_file"], branch=prop["branch"])
        run.stage_end("fix", "ok", f"{len(prop['patch']['ops'])} op(s) → back to {prop['branch']} ({prop['patch_file']})")
        nopts = _opts(opts, attempt=attempt + 1, only_assets=prop["assets"])
        if prop["branch"] == "codegen":
            _simple(run, "codegen", lambda: codegen.run(run, nopts))
            if run.path("codegen.json").is_file():   # codegen.json 은 마지막 codegen 으로 덮인다 — 시도별 사본
                dst = run.path("attempts", f"{attempt + 1:03d}", "codegen.json")
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(run.path("codegen.json"), dst)
        elif prop["branch"] == "generate":
            _simple(run, "generate", lambda: generate.run(run, nopts))
            _simple(run, "refine", lambda: refine.run(run, nopts))
    return "fail"   # pragma: no cover — 루프 안에서 끝난다


def _finalize(run: Run, opts, ctx: dict, outcome: str) -> None:
    if not run.path("build.json").is_file():   # build 전에 끝남 — 에디터에 이번 run 의 것이 없다(단계 기록도 남기지 않는다)
        ctx["finalize"] = {"action": "none", "reason": "nothing was built in the editor"}
        return
    run.stage_begin("finalize")
    patches = sorted(p.relative_to(run.dir).as_posix() for p in run.path("patches").glob("*.json")) if run.path("patches").is_dir() else []
    extra = {"spec_file": ctx["attempts"][-1]["spec"] if ctx["attempts"] else "spec.json", "attempts": len(ctx["attempts"]),
             "fault": (ctx["fault"] or {}).get("name"), "patches": patches}
    try:
        res = finalize.run(run, opts, outcome, extra)
        ctx["finalize"] = res
        run.stage_end("finalize", "ok", finalize.summary(res))
    except StageError as exc:
        ctx["finalize"] = {"action": "error", "error": {"code": exc.code, "message": str(exc)}}
        run.stage_end("finalize", "fail", str(exc), code=exc.code)
        if ctx["status"] == "pass":
            ctx["status"], ctx["message"] = "fail", f"finalize failed: {exc}"
    except Exception as exc:  # noqa: BLE001 — 기록은 남긴다
        ctx["finalize"] = {"action": "error", "error": {"code": type(exc).__name__, "message": str(exc)}}
        run.log(traceback.format_exc())
        run.stage_end("finalize", "error", str(exc))
        if ctx["status"] == "pass":
            ctx["status"], ctx["message"] = "error", f"finalize failed: {exc}"


def execute(opts: argparse.Namespace) -> int:
    cfg = config.load_pipeline(opts.config)
    spec_dir = pathlib.Path(opts.spec_dir)
    work_root = pathlib.Path(opts.work_root) if opts.work_root else config.repo_path(cfg["paths"]["work_root"])
    metrics_path = pathlib.Path(opts.metrics) if opts.metrics else config.repo_path(cfg["paths"]["metrics"])
    run_id = opts.run_id or new_run_id(_screen_id(spec_dir))
    run = Run(run_id, work_root, cfg, metrics_path)
    with RunLock(work_root, run_id) as lock:
        run.create()
        if lock.taken_over:
            run.log(f"took over a stale lock from a dead run: {lock.taken_over}")
        run.log(f"run {run_id} — phase {cfg.get('phase')} — work {run.dir.as_posix()}"
                + (f" — inject fault '{opts.inject_fault}'" if opts.inject_fault else ""))
        ctx: dict = {"status": "incomplete", "message": "", "attempts": [], "last": None, "fault": None, "finalize": None, "fixes": []}
        outcome = None
        try:
            outcome = _pipeline(run, opts, ctx)
            ctx["status"] = outcome
        except StopAt as stop:
            ctx["status"], ctx["message"] = "incomplete", f"stopped after '{stop}' (--until)"
        except StageError as exc:
            ctx["status"], ctx["message"] = "fail", str(exc)
            run.stage_end(_current_stage(run), "fail", str(exc), code=exc.code)
            outcome = "fail"
        except KeyboardInterrupt:   # 사람이 멈춤 — 기록은 남긴다(codegen 은 빌드 전이면 이미 원복했다)
            ctx["status"], ctx["message"] = "error", "interrupted"
            run.stage_end(_current_stage(run), "error", ctx["message"])
            outcome = "fail"
        except Exception as exc:  # noqa: BLE001 — 끝까지 기록을 남긴다
            ctx["status"], ctx["message"] = "error", f"{type(exc).__name__}: {exc}"
            run.log(traceback.format_exc())
            run.stage_end(_current_stage(run), "error", ctx["message"])
            outcome = "fail"
        if outcome is not None:
            _finalize(run, opts, ctx, "pass" if outcome == "pass" else "fail")
        last = ctx["last"]
        artifacts = dict((last or {}).get("artifacts") or {})
        if (ctx["finalize"] or {}).get("lineage"):
            artifacts["lineage"] = "lineage.json"
        report = {"schema_version": 1, "run_id": run_id, "parent_run_id": None, "status": ctx["status"], "attempt": len(ctx["attempts"]),
                  "gates": last["gates"] if last else [], "recorded": {"placement_inner": (last or {}).get("notes", {}).get("placement_inner", [])} if last else {},
                  "fixes": ctx["fixes"], "unsupported": last["unsupported"] if last else [], "durations_s": run.durations(),
                  "attempts": ctx["attempts"], "roundtrip": last["roundtrip"] if last else None, "fault": ctx["fault"], "finalize": ctx["finalize"],
                  "artifacts": artifacts, "verify": ("pass" if last["pass"] else "fail") if last else None, "message": ctx["message"]}
        summary = _codegen_summary(run)
        if summary:
            report["codegen"] = summary
        schema.require("report", report)
        run.write_json("report.json", report)
        status, message = ctx["status"], ctx["message"]
        run.record.update(status=status, message=message, finished=metrics.now_iso())
        run.save_record()
        write_metrics(run, status, len(ctx["attempts"]), report["verify"], (last or {}).get("failed"), (ctx["fault"] or {}).get("name"))
        run.log(f"run {run_id}: {status}{f' — {message}' if message else ''}")
        print(json.dumps({"run_id": run_id, "status": status, "attempts": len(ctx["attempts"]), "dir": run.dir.as_posix(), "message": message},
                         ensure_ascii=False))
    return {"pass": EXIT_PASS, "incomplete": EXIT_INCOMPLETE}.get(status, EXIT_FAIL)


def _current_stage(run: Run) -> str:
    """시작했지만 아직 기록되지 않은 단계 이름."""
    started = list(run._stage_t0)  # noqa: SLF001
    return started[-1] if started else "run"


def main(argv: list[str] | None = None) -> int:
    opts = parse_args(argv)
    try:
        return execute(opts)
    except LockBusy as exc:
        print(f"uigen: {exc}", file=sys.stderr)
        return EXIT_FAIL
    except (RunError, config.ConfigError) as exc:
        print(f"uigen: {exc}", file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
