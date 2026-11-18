"""uigen 진입점 — UI 자동 생성 파이프라인 오케스트레이터 (설계 Docs/Design/ui-autogen-pipeline.md §2).

순서 · 재시도 · 분기 · 상한 · 잠금은 이 코드가 정한다. 실행 중 사람에게 묻지 않는다.

Phase 1a(손 spec):
    Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/run_pipeline.py --spec-dir Tools/uigen/fixtures/m4_combat_hud
    (+ --inject-fault offscreen|overlap|drift — normalize 뒤 spec 을 깨뜨려 재시도 경로를 돈다 · --keep-failed — 실패해도 저장)
Phase 1b(컨셉아트):
    Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/run_pipeline.py --inputs Tools/uigen/fixtures/m4_combat_hud_concept/inputs.yaml
    (+ --concept <png> — inputs 의 concept 을 덮음 · --until analyze — 에디터 없이 spec 까지)

단계: (preflight) → normalize → analyze → (inject_fault) → codegen → generate → refine → [build → verify → (fix → 분기)]… → finalize.
  - preflight: LLM 단계가 있는 run(concept 모드 · fix.mode ≠ deterministic)만 — claude 버전 · 로그인 · 구독 인증 확인(core.llm.preflight).
  - hand_spec 은 analyze 를 건너뛰고 결함 주입이 normalize 바로 뒤, concept 은 analyze 뒤.
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
from core import llm  # noqa: E402
from core import metrics  # noqa: E402
from core import patch as patch_mod  # noqa: E402
from core import schema  # noqa: E402
from core.run import LockBusy, Run, RunError, RunLock, new_run_id  # noqa: E402
from stages import StageError  # noqa: E402
from stages import analyze, build, codegen, fault, finalize, fix, generate, layer, normalize, refine, style, verify  # noqa: E402

STAGES = ("normalize", "analyze", "codegen", "generate", "refine", "build", "verify", "finalize")

EXIT_PASS, EXIT_FAIL, EXIT_INCOMPLETE = 0, 1, 2


class StopAt(Exception):
    """--until 에 닿음."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="uigen — concept/spec → WBP prototype (Phase 1a: hand spec · Phase 1b: concept)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--spec-dir", help="hand spec folder holding brief.json + spec.json (Phase 1a)")
    src.add_argument("--inputs", help="inputs.yaml of a concept request (Phase 1b — schemas/inputs.schema.json)")
    ap.add_argument("--concept", help="concept PNG overriding inputs.yaml 'concept' (only with --inputs)")
    ap.add_argument("--until", choices=STAGES, help="stop after this stage (first attempt for build / verify; no finalize)")
    ap.add_argument("--run-id", help="override the run id (R<yyyymmdd>_<hhmmss>_<ScreenId>)")
    ap.add_argument("--config", help="pipeline.yaml to use (default Tools/uigen/config/pipeline.yaml)")
    ap.add_argument("--work-root", help="override paths.work_root")
    ap.add_argument("--metrics", help="override paths.metrics (JSONL)")
    ap.add_argument("--module-root", help="override codegen.module_root (C++ module folder — tests write into a temp copy)")
    ap.add_argument("--inject-fault", choices=sorted(fault.FAULTS), help="break the spec after normalize to exercise the retry path (1a-4)")
    ap.add_argument("--keep-failed", action="store_true", help="save the run packages even when verify fails")
    ap.add_argument("--fix-mode", choices=("deterministic", "hybrid", "llm"), help="override pipeline.yaml fix.mode for this run")
    opts = ap.parse_args(argv)
    if opts.concept and not opts.inputs:
        ap.error("--concept needs --inputs")
    return opts


def _extract_fidelity_summary(run: Run) -> dict | None:
    """refine.json 에서 컨셉에서 따온 에셋(source_mode extract)의 마지막 충실도 — report.recorded.extract_fidelity (기록만, 1b 후속 A)."""
    if not run.path("refine.json").is_file():
        return None
    out = {}
    for p in run.read_json("refine.json").get("passes", []):
        for a in p.get("assets", []):
            f = a.get("fidelity")
            if f is not None:
                out[a["asset_id"]] = {k: f.get(k) for k in ("framing", "aspect", "shape_iou", "line_f1", "delta_e00", "compare", "error") if k in f}
                if a.get("interior"):
                    out[a["asset_id"]]["interior"] = {k: a["interior"].get(k) for k in ("flattened", "changed_ratio", "holes_before", "fill_color")}
    if out and run.path("render.png").is_file() and run.path("reference.png").is_file() and run.path("spec.json").is_file():
        from gen import fidelity
        try:   # 이식 확인 — 마지막 시도의 WBP 렌더(force_visible) ↔ 컨셉, 같은 상자(기록만)
            rendered = fidelity.render_comparisons(run.path("reference.png"), run.path("render.png"), run.read_json("spec.json"), set(out),
                                                   run.path("assets", "compare"))
        except Exception as exc:  # noqa: BLE001 — 기록 지표라 실패해도 리포트는 쓴다
            rendered = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        for aid, recs in rendered.items():
            if aid in out:
                out[aid]["render"] = recs
            elif aid == "error":
                out["_render_error"] = recs
    return out or None


def _backdrop_summary(run: Run) -> dict | None:
    """회색 바탕 위 확인(1b 후속 H3 — gen/backdrop.check) — report.recorded.backdrop + assets/compare/backdrop*.png (기록만).
    렌더는 검정 바탕에 구워 '어둡고 불투명한 칠'과 '투명'을 못 가른다 — 최종 텍스처를 실제 렌더 상자대로 회색 위에 다시 쌓아 본다."""
    if not all(run.path(f).is_file() for f in ("spec.json", "geometry.json", "manifest.json")):
        return None
    from gen import backdrop
    try:
        rec = backdrop.check(run.dir)
    except Exception as exc:  # noqa: BLE001 — 기록 지표
        return {"error": f"{type(exc).__name__}: {exc}"[:300]}
    comp = rec.pop("compose", {}) or {}
    rec["compose"] = {"drawn": len(comp.get("drawn") or []), "missing": comp.get("missing") or []}
    return rec


def _diagnosis_summary(run: Run, last: dict | None) -> dict | None:
    """1b 후속 J-b — 마지막 verify 의 진단(gen/diagnose — run 폴더 diagnosis.json) → report.recorded.diagnosis(결함 · 원인 단계 · 글자 · 그림)."""
    if not last or not run.path("diagnosis.json").is_file():
        return None
    d = run.read_json("diagnosis.json")
    if d.get("attempt") != last.get("attempt"):
        return {"stale": f"diagnosis.json is from attempt {d.get('attempt')}, the last verify is attempt {last.get('attempt')}"}
    seams = d.get("seams") or {}
    return {"attempt": d.get("attempt"), "truth": d.get("truth"), "summary": d.get("summary"), "badness": d.get("badness"), "maps": d.get("maps"),
            "defects": (d.get("defects") or [])[:40], "hidden_states": d.get("hidden_states"),
            "seams": {k: seams.get(k) for k in ("zone_px", "dark_px", "dark_mean", "worst", "layers")} | {"spots": (seams.get("spots") or [])[:10]},
            "texts": [{k: t.get(k) for k in ("widget", "h_ratio", "w_ratio", "center_d", "density_ratio", "color_de", "dark_frac", "halo_frac", "causes",
                                             "record_only")} for t in d.get("texts") or []],
            "conversion": d.get("conversion"), "pictures": [f"attempts/{d.get('attempt'):03d}/diagnosis/{p}" for p in d.get("pictures") or []],
            "settings": d.get("settings")}


def _gauge_fidelity_summary(run: Run) -> dict | None:
    """컨셉에서 채움을 뽑은 게이지(analyze derive_gauge_fills)의 렌더 ↔ 컨셉 — report.recorded.gauge_fidelity (기록만, 1b 후속 B · F 채움 실루엣)."""
    if not (run.path("render.png").is_file() and run.path("reference.png").is_file() and run.path("spec.json").is_file()):
        return None
    from gen import fidelity
    spec = run.read_json("spec.json")
    derived = {a["asset_id"] for a in spec.get("assets", []) if str(a.get("source", "")).startswith(("concept rows", "concept fill"))}
    out = {}
    for w in spec.get("widgets", []):
        st = w.get("style") or {}
        if w.get("type") == "ProgressBar" and (st.get("fill") or {}).get("asset") in derived and w.get("bbox_intent") and isinstance(st.get("percent"), (int, float)):
            try:
                out[w["id"]] = fidelity.gauge_vs_concept(run.path("reference.png"), run.path("render.png"), w["bbox_intent"], st["percent"],
                                                         st.get("bar_fill_type", "left_to_right"))
                out[w["id"]]["background"] = (st.get("background") or {}).get("draw_as")
                out[w["id"]]["shape"] = fidelity.gauge_shape(run.path("reference.png"), run.path("render.png"), w["bbox_intent"], st["percent"],
                                                             st.get("bar_fill_type", "left_to_right"))
            except Exception as exc:  # noqa: BLE001 — 기록 지표
                out[w["id"]] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    return out or None


def _codegen_summary(run: Run) -> dict | None:
    """report.json 의 codegen 요약 — 계약 해시 · 건너뜀 · 빌드 결과 (자세한 것은 codegen.json)."""
    if not run.path("codegen.json").is_file():
        return None
    cg = run.read_json("codegen.json")
    b = cg.get("build") or {}
    return {"contract_hash": cg["contract_hash"], "skipped": cg["skipped"], "reason": cg["reason"], "bindings": len(cg["contract"]["bindings"]),
            "build": {"ran": b.get("ran", False), "ok": b.get("ok"), "result_line": b.get("result_line")},
            "verify_match": (cg.get("verify") or {}).get("match"), **({"error": cg["error"]} if cg.get("error") else {})}


def _screen_id(opts: argparse.Namespace) -> str:
    if opts.inputs:
        try:
            return str(config.load_yaml(opts.inputs)["screen_id"])
        except (config.ConfigError, KeyError) as exc:
            raise RunError("INPUT_UNREADABLE", f"{opts.inputs}: {exc}") from exc
    spec_dir = pathlib.Path(opts.spec_dir)
    try:
        return json.loads((spec_dir / "brief.json").read_text(encoding="utf-8"))["screen_id"]
    except (OSError, ValueError, KeyError) as exc:
        raise RunError("INPUT_UNREADABLE", f"{spec_dir / 'brief.json'}: {exc}") from exc


def _needs_llm(cfg: dict, opts) -> bool:
    """LLM 단계가 있는 run — concept 모드(analyze) 또는 LLM fix."""
    return bool(getattr(opts, "inputs", None)) or (cfg.get("fix") or {}).get("mode", "deterministic") != "deterministic"


def _preflight(run: Run, opts) -> str:
    try:
        info = llm.preflight(run.cfg, cli=getattr(opts, "llm_cli", None))
    except llm.LlmError as exc:
        raise StageError(exc.code, str(exc).split(": ", 1)[-1]) from exc
    run.record["llm_cli"] = info
    warn = "" if info["version_match"] else f" (expected {info['expected_version']})"
    return f"claude {info['version']}{warn} — {info['auth_method']} · {info['subscription']}"


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
    concept = bool(getattr(opts, "inputs", None))

    def inject():
        if opts.inject_fault:
            run.stage_begin("inject_fault")
            detail, ctx["fault"] = fault.inject(run, opts.inject_fault)
            run.stage_end("inject_fault", "ok", detail)

    if _needs_llm(run.cfg, opts):
        _simple(run, "preflight", lambda: _preflight(run, opts))
    _simple(run, "normalize", lambda: normalize.run(run, opts))
    if not concept:
        inject()
    _until(opts, "normalize")
    if concept:
        _simple(run, "analyze", lambda: analyze.run(run, opts))
        inject()
        # 1b 후속 J-a — 기능 단위 레이어(정적 장식은 판 한 장으로, 기능 요소만 따로) — analyze 뒤 결정적 단계
        _simple(run, "layer", lambda: layer.run(run, opts))
        if run.path("layer.json").is_file() and run.read_json("layer.json").get("applied"):
            run.write_json("specs/000.json", run.read_json("spec.json"))
    else:
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
        if _structural_pass(res):
            # 1b 후속 J-b — 구조 게이트가 통과하면 외형 라운드 · 글자 맞춤(결정적 고침)을 돌고, 합격은 마지막 진단이 깨끗할 때만
            _style_review(run, opts, ctx, attempt)
            last = ctx["last"]
            if last["pass"]:
                return "pass"
            ctx["attempts"][-1]["stop"] = "APPEARANCE"
            ctx["message"] = _appearance_message(last)
            return "fail"
        failed = set(verify.structural_failed(res))
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
        prop = fix.propose(run, attempt, _structural_only(res))
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


def _structural_pass(res: dict) -> bool:
    return bool(res.get("structural_pass", res["pass"]))


def _structural_only(res: dict) -> dict:
    """fix 에 넘길 결과 — appearance 는 빼고(외형은 재시도 fixer 가 아니라 외형 라운드 · 글자 맞춤 몫)."""
    return {**res, "failed": verify.structural_failed(res), "gates": [g for g in res["gates"] if g["name"] != verify.APPEARANCE]}


def _appearance(res: dict) -> dict | None:
    return next((g for g in res.get("gates", []) if g["name"] == verify.APPEARANCE), None)


def _appearance_badness(res: dict) -> tuple[int, float]:
    g = _appearance(res)
    if not g or g.get("skipped") or (g.get("details") or {}).get("error"):
        return (0, 0.0) if not g or g.get("skipped") else (10 ** 6, 0.0)
    return int(g.get("value") or 0), float((g.get("details") or {}).get("badness") or 0.0)


def _round_ok(res: dict, before: dict | None) -> bool:
    """외형 라운드 · 글자 맞춤 판을 받을지 — 구조 게이트 통과 + 진단이 나빠지지 않음(결함 수가 줄거나, 같으면 나쁨 정도가 2 % 넘게 늘지 않음)."""
    if not _structural_pass(res):
        return False
    if before is None:
        return True
    a, b = _appearance_badness(res), _appearance_badness(before)
    return a[0] < b[0] or (a[0] == b[0] and a[1] <= b[1] * 1.02 + 1e-6)


def _appearance_message(res: dict) -> str:
    g = _appearance(res) or {}
    d = g.get("details") or {}
    if d.get("error"):
        return f"appearance diagnosis failed: {d['error']}"
    top = "; ".join(f"#{x.get('n')} {x.get('stage')} {'/'.join(x.get('widgets') or [])}: {x.get('cause')}" for x in (d.get("defects") or [])[:6])
    return (f"structural gates pass but the appearance diagnosis found {g.get('value')} local defect(s) {d.get('by_stage')} — not fixed "
            f"deterministically: {top}")


def _style_enabled(run: Run) -> bool:
    sr = run.cfg.get("style_review") or {}
    return int(sr.get("rounds", 0)) > 0 and (run.cfg.get("fix") or {}).get("mode", "deterministic") != "deterministic"


def _style_review(run: Run, opts, ctx: dict, attempt: int) -> None:
    """1b 후속 C — 게이트를 통과한 뒤의 외형 검토 라운드(stages/style.py, 설계 §2-2 '통과 뒤 라운드').
    concept 모드(reference.png 있음)면 영역 · 글자 비교를 늘 기록하고(style/before), 라운드가 켜져 있으면(style_review.rounds · fix.mode ≠ deterministic)
    style_verifier → style_fix → (에셋 교체면 generate → refine) → build → verify. 게이트가 모두 통과하면 그 라운드를 받고,
    하나라도 깨지면 버린다: 마지막 통과 spec · manifest(· 교체한 에셋 파일)로 되돌리고 run 패키지를 전부 버린 뒤(build.reset_run) 처음부터 다시
    build → verify(통과해야 함 — 아니면 STYLE_REVERT_FAILED) — 에디터의 WBP 가 라운드 상태로 저장되지 않게. 합격 판정은 게이트만(결정 6)."""
    if not run.path("reference.png").is_file():
        return
    rounds = int((run.cfg.get("style_review") or {}).get("rounds", 0)) if _style_enabled(run) else 0
    rec: dict = {"rounds_allowed": rounds, "rounds": []}
    ctx["style"] = rec
    ctx["accepted"] = ctx["last"]            # 1b 후속 J-b — 라운드 받기 기준(구조 통과 + 진단이 이것보다 나빠지지 않음)
    run.stage_begin("style_compare")
    rep = style.compare(run, "before")
    rec["before"] = rep.get("summary") or {"error": rep.get("error")}
    run.stage_end("style_compare", "ok", f"before: {json.dumps(rec['before'], ensure_ascii=False)}")
    last_spec, last_attempt = run.read_json("spec.json"), attempt
    for k in range(1, rounds + 1):
        row: dict = {"round": k}
        rec["rounds"].append(row)
        run.stage_begin("style")
        prop = style.propose(run, k, rep, cli=getattr(opts, "llm_cli", None))
        row.update(findings=len(prop["fixes"]), cost_usd=prop.get("cost_usd"), patch=prop["patch_file"], branch=prop["branch"])
        if prop["patch"] is None:
            row.update(action="no_ops", reason=prop.get("error"))
            run.stage_end("style", "ok", f"round {k}: no style ops — {prop.get('error')}")
            break
        try:
            styled = patch_mod.apply_patch(run.read_json("spec.json"), prop["patch"])
        except patch_mod.PatchError as exc:   # propose 가 이미 사본 적용을 했다 — 여기 오면 코드 결함
            row.update(action="invalid", reason=str(exc))
            run.stage_end("style", "fail", str(exc), code="STYLE_PATCH_INVALID")
            break
        # 1b 후속 F — 크기가 바뀐 글자는 자기 가운데를 중심으로만 커지게(padding) + 게이트 기준 상자 = 직전 통과 렌더 상자를 그만큼 키운 것
        followed = style.follow_text_boxes(run.read_json("spec.json"), styled, run.cfg, style.rendered_boxes(run, last_attempt))
        if followed:
            row["text_boxes_followed"] = followed
        backup = style.snapshot(run, k, prop["assets"])
        row["ops"] = len(prop["patch"]["ops"])
        run.write_json("spec.json", styled)
        run.stage_end("style", "ok", f"round {k}: {row['ops']} op(s) → {prop['branch']} ({prop['patch_file']})")
        attempt += 1
        aopts = _opts(opts, attempt=attempt, only_assets=prop["assets"])
        if prop["branch"] == "generate":
            _simple(run, "generate", lambda: generate.run(run, aopts))
            _simple(run, "refine", lambda: refine.run(run, aopts))
            # 1b 후속 G — 다시 따온 에셋이 충실도에서 나빠졌으면 그 에셋만 옛 것으로(라운드의 다른 op 는 그대로)
            guard = style.replace_guard(run, backup, prop["assets"], float((run.cfg.get("style_review") or {}).get("replace_guard_tol", 0.02)))
            if guard:
                row["replace_guard"] = guard
        try:
            res = _style_attempt(run, aopts, ctx, attempt, {"style_round": k, "patch": prop["patch_file"], "branch": prop["branch"]})
        except StageError as exc:
            # 1b 후속 K — 라운드 op 를 build 가 거절하면(왕복 검사 등) run 을 멈추지 않고 그 라운드만 버린다
            # [실측 K R20261118_090350 파티 HUD — LLM 이 초상화 이미지 브러시에 radius 를 넣어 VALIDATION_FAILED 로 run 전체가 멈춤]
            row["build_error"] = {"code": exc.code, "message": str(exc)[:300]}
            res = {"pass": False, "failed": ["build"], "gates": [], "structural_pass": False}
        row["verify"] = {"attempt": attempt, "pass": res["pass"], "failed": res["failed"], "appearance": _appearance_badness(res)}
        if _round_ok(res, ctx.get("accepted")):
            row["action"] = "accepted"
            ctx["accepted"] = res
            last_spec, last_attempt = run.read_json("spec.json"), attempt
            rep = style.compare(run, f"round_{k:03d}")
            row["after"] = rep.get("summary") or {"error": rep.get("error")}
            continue
        row["action"] = "reverted"
        run.stage_begin("style_revert")
        run.write_json("spec.json", last_spec)
        restored = style.restore(run, backup)
        reset = build.reset_run(run)
        run.stage_end("style_revert", "ok", f"round {k} broke {', '.join(res['failed'])} (appearance {_appearance_badness(res)} vs "
                                            f"{_appearance_badness(ctx.get('accepted') or {})}) — back to attempt {last_attempt}'s spec, "
                                            f"restored {len(restored)} file(s), discarded {len(reset['discarded'])} package(s), rebuilding")
        row["revert"] = {"to_attempt": last_attempt, "restored": restored, "discarded": len(reset["discarded"])}
        attempt += 1
        res = _style_attempt(run, _opts(opts, attempt=attempt), ctx, attempt, {"style_round": k, "revert": True})
        if not _structural_pass(res):
            raise StageError("STYLE_REVERT_FAILED", f"rebuilding the last passing spec failed: {', '.join(res['failed'])}")
        ctx["accepted"] = res
        rep = style.compare(run, f"round_{k:03d}_reverted")
        break
    if (run.cfg.get("style_review") or {}).get("text_fit"):
        rep = _text_fit_round(run, opts, ctx, rec, rep, attempt)
    rec["final"] = rep.get("summary") or {"error": rep.get("error")}
    rec["final_label"] = rep.get("label")


TEXT_FIT_PASSES = (("size", "text_fit_size"), ("place", "text_fit"))   # (style.text_fit mode, 기록 키 = 시도 style_round · 비교 라벨)


def _text_fit_round(run: Run, opts, ctx: dict, rec: dict, rep: dict, attempt: int) -> dict:
    """1b 후속 G — 외형 라운드(받든 버리든) 뒤 글자 결정적 맞춤(style.text_fit — LLM 없음), 두 판:
    크기 판(높이 비로 크기 · 굵기 — 형제 겹침 예측으로 상한) → 위치 판(최신 통과 렌더에서 다시 재 자간 · 중심). 판마다 build → verify 해
    통과면 받고, 깨지면 외형 라운드와 같이 그 판만 버린다(마지막 통과 spec · run 패키지 버림 · 다시 build → verify 통과해야 함) — 크기 판이 버려져도
    위치 판은 돈다(한 판에 섞으면 크기 탓 overlap 에 위치 맞춤까지 버려진다). 하나라도 받으면 같은 측정으로 남은 차를 기록. → 마지막 비교 보고."""
    accepted = False
    for mode, key in TEXT_FIT_PASSES:
        rep, attempt, ok = _text_fit_pass(run, opts, ctx, rec, rep, attempt, mode, key)
        accepted = accepted or ok
        if mode == "size" and ok and any(t.get("color") or t.get("outline") for t in (rec.get(key) or {}).get("texts", []) if isinstance(t, dict)):
            # 1b 후속 J-c — 이 판에서 글자색을 고쳤으면 크기 판을 한 번 더: 색이 틀린 렌더 글자는 높이를 못 믿어 크기를 건너뛴다
            # [실측 J R20261117_175018 — 남색 '점프' 높이 비 0.51 → 색만 고침, 다음 렌더에서 0.918]
            rep, attempt, ok = _text_fit_pass(run, opts, ctx, rec, rep, attempt, mode, f"{key}_after_color")
            accepted = accepted or ok
    # 1b 후속 K — 위치 판 뒤 마지막 진단에 고칠 수 있는 글자 결함(크기 · 굵기 · 색 · 외곽선 · 빛)이 남으면 크기 판을 한 번 더(가장 가까운 굵기는 경계 근처에서
    # 렌더마다 갈린다 [실측 K R20261117_234013 '체인 버스트' 밀도 비 위치 판 전 1.07 · 뒤 1.11 — Bold ↔ Black 경계 1.07])
    try:
        last = run.read_json("diagnosis.json")
    except (OSError, ValueError):
        last = {}
    if any(d.get("stage") == "text" and d.get("fixable") and set(d.get("causes") or []) & {"size", "weight", "color", "outline", "glow", "shadow", "glow_strength"}
           for d in last.get("defects") or []):
        rep, attempt, ok = _text_fit_pass(run, opts, ctx, rec, rep, attempt, "size", "text_fit_size_final")
        accepted = accepted or ok
    if accepted:
        row = rec["text_fit"]
        try:   # 같은 측정으로 남은 차(기록만 — 적용하지 않음)
            _, again = style.text_fit(run.read_json("spec.json"), run.path("reference.png"), run.path("render.png"), run.cfg,
                                      style.rendered_boxes(run, attempt), mode="place")
            row["residual"] = [{k: t.get(k) for k in ("widget", "center_d", "h_ratio", "w_ratio", "gap_cols", "ink_density", "skipped")} for t in again if t.get("widget")]
        except Exception as exc:  # noqa: BLE001
            row["residual"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    return rep


def _text_causes(res: dict | None) -> dict[str, set]:
    """마지막 진단의 글자 결함 — 위젯 → 원인 집합."""
    d = ((_appearance(res or {}) or {}).get("details") or {})
    out: dict[str, set] = {}
    for x in d.get("defects") or []:
        if x.get("stage") == "text":
            for wid in x.get("widgets") or []:
                out.setdefault(wid, set()).update(x.get("causes") or [c.strip() for c in str(x.get("cause", "")).split(",") if c.strip()])
    return out


def _text_fit_pass(run: Run, opts, ctx: dict, rec: dict, rep: dict, attempt: int, mode: str, key: str,
                   only: set | None = None) -> tuple[dict, int, bool]:
    """글자 맞춤 한 판 — 마지막 통과 렌더(시도 attempt)에서 재고 고쳐 build → verify. → (비교 보고, 마지막 통과 시도, 받았는지).
    판이 진단을 나쁘게 해 버려지면(1b 후속 J) 그 판에서 글자 결함 원인이 줄어든 글자만 골라 한 번 더(only — `<key>_partial`) — 한 글자 탓에 판 전체가
    버려졌다 [실측 J R20261117_192631 · 201408 파티 HUD — 방패 숫자 · 이름 측정 탓에 HP 숫자 크기까지 버려짐]."""
    row: dict = {"round": key, "mode": mode, **({"only": sorted(only)} if only is not None else {})}
    rec[key] = row
    last_spec = run.read_json("spec.json")
    before_causes = _text_causes(ctx.get("accepted"))
    run.stage_begin(key)
    try:
        fitted, recs = style.text_fit(last_spec, run.path("reference.png"), run.path("render.png"), run.cfg, style.rendered_boxes(run, attempt), mode=mode,
                                      **({"only": only} if only is not None else {}))
    except Exception as exc:  # noqa: BLE001 — 기록 지표에 기대는 보정이라 실패해도 run 은 통과 그대로
        row.update(action="error", reason=f"{type(exc).__name__}: {exc}"[:300])
        run.stage_end(key, "ok", f"text fit ({mode}) skipped — {row['reason']}")
        return rep, attempt, False
    row["texts"] = recs
    changed = style.text_fit_changed(recs)
    if not changed:
        row["action"] = "nothing_to_fit"
        run.stage_end(key, "ok", f"text fit ({mode}): nothing to change")
        return rep, attempt, False
    row["changed"] = changed
    run.write_json("spec.json", fitted)
    run.stage_end(key, "ok", f"text fit ({mode}): {', '.join(changed)} → build")
    attempt += 1
    res = _style_attempt(run, _opts(opts, attempt=attempt), ctx, attempt, {"style_round": key})
    row["verify"] = {"attempt": attempt, "pass": res["pass"], "failed": res["failed"], "appearance": _appearance_badness(res)}
    if _round_ok(res, ctx.get("accepted")):
        row["action"] = "accepted"
        ctx["accepted"] = res
        rep = style.compare(run, key)
        row["after"] = rep.get("summary") or {"error": rep.get("error")}
        return rep, attempt, True
    row["action"] = "reverted"
    # 글자별로 다시 고를 몫 — 이 판에서 원인이 줄어든(없어진 포함) 글자, 새 원인이 생긴 글자는 뺀다
    keep = set()
    struct_failed = [g for g in res.get("gates", []) if not g.get("pass") and g["name"] != verify.APPEARANCE]
    if only is None and len(changed) >= 2 and all(g["name"] == "overlap" for g in struct_failed):
        # 겹침만 깨졌으면 겹친 글자는 빼고 고른다 [실측 J R20261117_195827 — '오의 불가' 크기 탓 overlap 에 다른 글자 셋 크기까지 버려짐]
        involved = {v.get(k) for g in struct_failed for v in ((g.get("details") or {}).get("violations") or []) for k in ("a", "b")}
        after_causes = _text_causes(res)
        for wid in changed:
            b, a = before_causes.get(wid, set()), after_causes.get(wid, set())
            if wid not in involved and a <= b and len(a) < len(b):
                keep.add(wid)
        row["better_texts"] = sorted(keep)
    run.stage_begin("style_revert")
    run.write_json("spec.json", last_spec)
    reset = build.reset_run(run)
    run.stage_end("style_revert", "ok", f"text fit ({mode}) broke {', '.join(res['failed'])} — back to the last passing spec, "
                                        f"discarded {len(reset['discarded'])} package(s), rebuilding")
    attempt += 1
    res = _style_attempt(run, _opts(opts, attempt=attempt), ctx, attempt, {"style_round": key, "revert": True})
    if not _structural_pass(res):
        raise StageError("STYLE_REVERT_FAILED", f"rebuilding the last passing spec after the text fit ({mode}) failed: {', '.join(res['failed'])}")
    ctx["accepted"] = res
    rep = style.compare(run, f"{key}_reverted")
    if keep and keep != set(changed):
        return _text_fit_pass(run, opts, ctx, rec, rep, attempt, mode, f"{key}_partial", only=keep)
    return rep, attempt, False


def _style_attempt(run: Run, aopts, ctx: dict, attempt: int, extra: dict) -> dict:
    """외형 라운드의 build → verify 한 번 — 시도 기록(specs/NNN.json · attempts 줄)은 재시도와 같은 모양."""
    spec_file = f"specs/{attempt:03d}.json"
    run.write_json(spec_file, run.read_json("spec.json"))
    row = {"attempt": attempt, "spec": spec_file, "pass": False, "failed": [], "patch": None, "branch": None, "stop": None, "build": None, **extra}
    ctx["attempts"].append(row)
    row["build"] = _simple(run, "build", lambda: build.run(run, aopts))
    run.stage_begin("verify")
    res = verify.run(run, aopts)
    ctx["last"] = res
    row.update({"pass": res["pass"], "failed": res["failed"], "duration_s": res["duration_s"]})
    run.stage_end("verify", "ok" if res["pass"] else "fail", verify.summary(res))
    return res


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
    if getattr(opts, "fix_mode", None):
        cfg.setdefault("fix", {})["mode"] = opts.fix_mode
    work_root = pathlib.Path(opts.work_root) if opts.work_root else config.repo_path(cfg["paths"]["work_root"])
    metrics_path = pathlib.Path(opts.metrics) if opts.metrics else config.repo_path(cfg["paths"]["metrics"])
    run_id = opts.run_id or new_run_id(_screen_id(opts))
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
        fidelity = _extract_fidelity_summary(run)
        if fidelity:
            report.setdefault("recorded", {})["extract_fidelity"] = fidelity
        gauges = _gauge_fidelity_summary(run)
        if gauges:
            report.setdefault("recorded", {})["gauge_fidelity"] = gauges
        bd = _backdrop_summary(run) if ctx["status"] == "pass" else None
        if bd:
            report.setdefault("recorded", {})["backdrop"] = bd
            if not bd.get("error"):
                report.setdefault("artifacts", {})["backdrop"] = "assets/compare/backdrop.png" if "backdrop.png" in bd.get("images", []) \
                    else "assets/compare/backdrop_gray.png"
        if run.path("normalize.json").is_file():
            cv = (run.read_json("normalize.json").get("background") or {}).get("convert")
            if cv:                                # 1b 후속 I — 'UI 만 · 진짜 알파' 자동 변환 출처(gen/concept_convert)
                report.setdefault("recorded", {})["concept_convert"] = cv
                if cv.get("used"):
                    report.setdefault("artifacts", {})["concept_convert"] = cv.get("concept_file")
        if ctx.get("style"):
            report.setdefault("recorded", {})["style_review"] = ctx["style"]
        dg = _diagnosis_summary(run, last)
        if dg:
            report.setdefault("recorded", {})["diagnosis"] = dg
        summary = _codegen_summary(run)
        if summary:
            report["codegen"] = summary
        if run.path("analyze.json").is_file():
            a = run.read_json("analyze.json")
            report["analyze"] = {k: a.get(k) for k in ("calls", "cost_usd", "duration_s", "model", "retry_reasons", "ok")}
            if run.path("analyze/overlay.png").is_file():
                report["artifacts"]["overlay"] = "analyze/overlay.png"
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
