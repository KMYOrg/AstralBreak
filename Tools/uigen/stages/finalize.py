"""finalize — run 패키지 저장 또는 폐기 (설계 §2-2 finalize · 결정 5).

통과: save_widget_run(/Game/_AutoGen/<run_id>) → Content/_AutoGen/<run_id>/ (git 무시) + lineage.json.
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
    doc = {"schema_version": 1, "run_id": run.run_id, "parent_run_id": None, "status": outcome, "created": metrics.now_iso(),
           "screen_id": run.read_json("brief.json")["screen_id"], "wbp": state["wbp"]["asset_path"], "parent_class": state["wbp"].get("parent_class"),
           "revision": state.get("revision"), "contract_hash": codegen.get("contract_hash"),
           "spec": {"file": extra.get("spec_file") or "spec.json", "sha256": hashlib.sha256(spec_bytes).hexdigest()},
           "attempts": extra.get("attempts", len(state.get("attempts", []))), "fault": extra.get("fault"), "patches": extra.get("patches", []),
           "textures": {a["asset_id"]: a.get("ue_path") for a in manifest["assets"]}, "saved": saved}
    schema.require("lineage", doc)
    run.write_json("lineage.json", doc)
    return doc


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
            res = tc.call("save_widget_run", {"run_path": rpath})
            saved = sorted(res.get("saved", []) + res.get("already_saved", []))
            lineage = _lineage(run, state, outcome, saved, extra) if state.get("wbp") else None
            return {"action": "saved", "run_path": rpath, "saved": res.get("saved", []), "already_saved": res.get("already_saved", []),
                    "content_dir": f"Content/{rpath.removeprefix('/Game/')}/", "lineage": "lineage.json" if lineage else None,
                    **({"kept_failed": True} if outcome != "pass" else {})}
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
