"""finalize — run 패키지 저장 또는 폐기 (설계 §2-2 finalize · 결정 5).

통과: save_widget_run(/Game/_AutoGen/<run_id>) → Content/_AutoGen/<run_id>/ (git 무시) + lineage.json.
  (1b 후속 L-2) 저장 직전 컨셉이 그리지 않은 숨은 위젯에 designer_hidden(UMG 'Hide in Designer')을 켜 한 번 더 적용 — 디자이너 미리보기 = 컨셉 상태.
실패: discard_run_packages — 저장 안 한 run 패키지를 버린다. --keep-failed 면 실패해도 저장한다(lineage.status = fail).
build 가 에디터를 건드리지 않았으면(build.json 없음) 할 일이 없다. 에디터 세션이 build 때와 다르면(그사이 재기동) 패키지는 이미 사라졌다.
"""
from __future__ import annotations

import hashlib

from core import metrics
from core import schema
from core.ue import ToolchainError
from stages import toolchain_error, ue_toolchain


def _lineage(run, state: dict, outcome: str, saved: list[str], extra: dict) -> dict:
    spec_bytes = run.path("spec.json").read_bytes()
    manifest = run.read_json("manifest.json") if run.path("manifest.json").is_file() else {"assets": []}
    codegen = run.read_json("codegen.json") if run.path("codegen.json").is_file() else {}
    parent = run.read_json("edit.json")["parent_run_id"] if run.path("edit.json").is_file() else None      # Phase 4 — 이어서 고치기
    doc = {"schema_version": 1, "run_id": run.run_id, "parent_run_id": parent, "status": outcome, "created": metrics.now_iso(),
           "screen_id": run.read_json("brief.json")["screen_id"], "wbp": state["wbp"]["asset_path"], "parent_class": state["wbp"].get("parent_class"),
           "revision": state.get("revision"), "contract_hash": codegen.get("contract_hash"),
           "spec": {"file": extra.get("spec_file") or "spec.json", "sha256": hashlib.sha256(spec_bytes).hexdigest()},
           "attempts": extra.get("attempts", len(state.get("attempts", []))), "fault": extra.get("fault"), "patches": extra.get("patches", []),
           "textures": {a["asset_id"]: a.get("ue_path") for a in manifest["assets"]}, "saved": saved}
    schema.require("lineage", doc)
    run.write_json("lineage.json", doc)
    return doc


def _designer_hidden(run, tc, state: dict) -> dict | None:
    """1b 후속 L-2 사람 눈 — UMG 디자이너는 위젯 Visibility 를 무시하고 모두 보이게 그려(bHiddenInDesigner 만 봄) 컨셉이 그리지 않은 숨은 위젯(게이지
    가득 참 빛 등)이 미리보기에 겹쳤다 [사용자 눈 R20261118_142524 WBP_CombatHUD — 반투명 빈 트랙 뒤로 금빛]. 저장 직전 마지막 진단의 '컨셉이 안 그린
    숨은 위젯'(state.force_visible_extra)에 spec designer_hidden 을 켜 한 번 더 적용한다 — 디자이너 미리보기 = 컨셉 상태(compare.png). 런타임 · 렌더 무관.
    → 기록 또는 None(할 일 없음). 실패해도 저장은 한다(기록만)."""
    from stages import build
    if run.path("edit.json").is_file():          # Phase 4 — 게이트가 본 WBP 그대로 저장한다(부모의 designer_hidden 을 이어받음, 대상 밖 위젯을 안 건드림)
        return {"applied": False, "reason": "edit run — the parent's values are kept"}
    if not run.path("diagnosis.json").is_file() or not run.path("spec.json").is_file():
        return None
    try:
        hide = set((run.read_json("diagnosis.json").get("state") or {}).get("force_visible_extra") or [])
    except (OSError, ValueError):
        return None
    spec = run.read_json("spec.json")
    changed = []
    for w in spec.get("widgets", []):
        want = w["id"] in hide and w.get("visibility") in ("collapsed", "hidden")
        if bool(w.get("designer_hidden")) != want:
            changed.append(w["id"])
        if want:
            w["designer_hidden"] = True
        else:
            w.pop("designer_hidden", None)
    if not changed:
        return {"applied": False, "widgets": sorted(hide), "reason": "already as the concept state"} if hide else None
    schema.require("spec", spec)
    manifest = run.read_json("manifest.json")
    try:
        res = tc.call("apply_widget_spec", {"asset_path": state["wbp"]["asset_path"], "spec": build.editor_target(spec, state),
                                            "assets": {a["asset_id"]: a["ue_path"] for a in manifest["assets"]}, "expected_revision": state["revision"]})
    except ToolchainError as exc:
        return {"applied": False, "widgets": sorted(hide), "error": {"code": exc.code, "message": str(exc)[:300]}}
    run.write_json("spec.json", spec)
    state["revision"] = res["revision_after"]
    build.save_state(run, state)
    return {"applied": True, "widgets": sorted(w["id"] for w in spec["widgets"] if w.get("designer_hidden")), "changed": changed,
            "ops": len(res.get("ops") or []), "verified": res.get("verified")}


def run(run, opts, outcome: str, extra: dict | None = None, toolchain=None) -> dict:
    """outcome = pass | fail. 결과 {action: saved | discarded | none, …} — report.finalize 로 남는다."""
    extra = extra or {}
    if not run.path("build.json").is_file():
        return {"action": "none", "reason": "nothing was built in the editor"}
    state = run.read_json("build.json")
    rpath = state["run_path"]
    tc = toolchain or ue_toolchain(run)
    try:
        status = tc.editor_status()
        if status is None:
            return {"action": "none", "reason": "the editor is not running — its unsaved run packages are already gone", "run_path": rpath}
        if state.get("session") is not None and status.get("process_id") != state["session"]:
            return {"action": "none", "reason": f"editor session changed ({state['session']} → {status.get('process_id')}) — packages already gone",
                    "run_path": rpath}
        keep = bool(getattr(opts, "keep_failed", False))
        if outcome == "pass" or keep:
            designer = _designer_hidden(run, tc, state) if state.get("wbp") else None
            res = tc.call("save_widget_run", {"run_path": rpath})
            saved = sorted(res.get("saved", []) + res.get("already_saved", []))
            lineage = _lineage(run, state, outcome, saved, extra) if state.get("wbp") else None
            return {"action": "saved", "run_path": rpath, "saved": res.get("saved", []), "already_saved": res.get("already_saved", []),
                    "content_dir": f"Content/{rpath.removeprefix('/Game/')}/", "lineage": "lineage.json" if lineage else None,
                    **({"designer_hidden": designer} if designer else {}), **({"kept_failed": True} if outcome != "pass" else {})}
        res = tc.call("discard_run_packages", {"run_path": rpath})
        return {"action": "discarded", "run_path": rpath, "discarded": res.get("discarded", []), "still_dirty": res.get("still_dirty", [])}
    except ToolchainError as exc:
        raise toolchain_error(exc, "finalize: ") from exc


def summary(res: dict) -> str:
    if res["action"] == "saved":
        return f"saved {len(res['saved']) + len(res['already_saved'])} package(s) under {res['run_path']}{' (--keep-failed)' if res.get('kept_failed') else ''}"
    if res["action"] == "discarded":
        return f"discarded {len(res['discarded'])} unsaved package(s) under {res['run_path']}" + (f", still dirty {res['still_dirty']}" if res["still_dirty"] else "")
    return f"nothing to do — {res['reason']}"
