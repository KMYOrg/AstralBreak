"""build — spec · manifest → /Game/_AutoGen/<run_id>/ 의 텍스처 · WBP (설계 §2-2 build · §6). 저장하지 않는다(finalize 몫).

순서: 에디터 확인(없으면 core.ue.Toolchain 으로 기동 → 브리지 + settle) → import_ui_textures(manifest 의 ue_path 가 비어 있는 에셋만 —
첫 시도는 전부, generate 로 다시 만든 에셋은 refine 이 ue_path 를 비운다) → create_widget_blueprint(첫 시도에만, 부모 = 스텁) →
apply_widget_spec(정규화 spec {root, widgets, locked} + assets 맵 + expected_revision).

텍스처 이름은 T_<asset_id>, 같은 에디터 세션에서 다시 임포트하면 T_<asset_id>_2 … (임포트는 덮어쓰기를 거부한다).
에디터 세션(get_editor_status.process_id)이 지난 build 와 다르면(codegen 재기동 — quit 이 저장 안 한 run 패키지를 버렸다) 처음부터 다시 만든다
(설계 §2-2 '저장 안 한 run 패키지를 버리고 spec + manifest 에서 다시 빌드').

출력: build.json — 지금 상태(wbp · revision · session · 텍스처 이름) + 시도마다 한 줄(op · revision 전후 · 컴파일 요약).
실패하면 배치 무변경(조정기가 원자적) · StageError — finalize 가 run 패키지를 폐기한다.
"""
from __future__ import annotations

import collections
import time

from core import config
from core import metrics
from core import schema
from core import spec as spec_mod
from core.ue import ToolchainError
from stages import StageError, toolchain_error, ue_toolchain


def run_path(run) -> str:
    return f"{run.cfg['paths']['ue_run_root'].rstrip('/')}/{run.run_id}"


def wbp_name(screen_id: str, screen: dict) -> str:
    return screen.get("wbp") or f"WBP_{screen_id}"


def package_of(asset_path: str) -> str:
    """/Game/a/T_x.T_x → /Game/a/T_x"""
    return asset_path.split(".", 1)[0]


def _new_state(run) -> dict:
    return {"schema_version": 1, "run_id": run.run_id, "run_path": run_path(run), "session": None, "wbp": None, "revision": None,
            "textures": {}, "names_used": [], "attempts": []}


def load_state(run) -> dict:
    return run.read_json("build.json") if run.path("build.json").is_file() else _new_state(run)


def save_state(run, state: dict) -> None:
    schema.require("build", state)
    run.write_json("build.json", state)


def ensure_editor(tc, run, rec: dict, attempt: int) -> dict:
    """떠 있는 에디터의 상태 — 없으면 띄우고 브리지 + settle 을 기다린다."""
    status = tc.editor_status()
    if status is None:
        run.log("build: no editor running — launching it")
        t0 = time.monotonic()
        pid = tc.launch_editor(run.path("build", f"editor_{attempt:03d}.log"))
        rec["launched_pid"] = pid
        rec["bridge_s"] = tc.wait_bridge(pid)
        rec["launch_s"] = round(time.monotonic() - t0, 1)
        status = tc.editor_status()
        if status is None:
            raise StageError("EDITOR_GONE", "the editor bridge answered once and then went away")
    rec["process_id"] = status.get("process_id")
    return status


def _texture_name(aid: str, used: set[str]) -> str:
    name, n = f"T_{aid}", 1
    while name in used:
        n += 1
        name = f"T_{aid}_{n}"
    return name


def _compile_summary(c: dict | None) -> dict | None:
    if not c:
        return None
    if c.get("ran") is False:   # 부모에 필수 바인딩이 있으면 빈 캔버스는 컴파일하지 않는다(apply 가 컴파일)
        return {"ran": False, "reason": c.get("reason")}
    return {"ran": True, "ok": c.get("ok"), "status": c.get("status"), "errors": c.get("errors"), "warnings": c.get("warnings"),
            "missing_bindings": [m.get("name") for m in c.get("missing_bindings", [])]}


def run(run, opts, toolchain=None) -> str:
    t_start = time.monotonic()
    attempt = int(getattr(opts, "attempt", 1) or 1)
    cfg = run.cfg
    spec = run.read_json("spec.json")
    brief = run.read_json("brief.json")
    manifest = run.read_json("manifest.json")
    screen_id = brief["screen_id"]
    screen = config.load_screens().get(screen_id)
    if not isinstance(screen, dict):
        raise StageError("SCREEN_UNKNOWN", f"screens.yaml has no screen '{screen_id}'")
    parent_class = f"/Script/{cfg['codegen']['module']}.{screen['widget']}"
    rpath = run_path(run)
    wbp_path = f"{rpath}/{wbp_name(screen_id, screen)}"
    tex_cfg = cfg["textures"]
    tc = toolchain or ue_toolchain(run)

    state = load_state(run)
    entry: dict = {"attempt": attempt, "started": metrics.now_iso(), "editor": {}, "ops": []}
    state["attempts"].append(entry)
    try:
        status = ensure_editor(tc, run, entry["editor"], attempt)
        session = status.get("process_id")
        if state["session"] is not None and state["session"] != session:
            entry["reset"] = (f"editor session changed ({state['session']} → {session}) — the unsaved run packages are gone; "
                              "building from spec + manifest again")
            run.log(f"build: {entry['reset']}")
            state.update(wbp=None, revision=None, textures={}, names_used=[])
            for a in manifest["assets"]:
                a["ue_path"] = None
        state["session"] = session

        # -- 텍스처 ------------------------------------------------------------------------------------------------------
        used = set(state["names_used"])
        todo = [a for a in manifest["assets"] if not a.get("ue_path")]
        if todo:
            requests = []
            for a in todo:
                name = _texture_name(a["asset_id"], used)
                used.add(name)
                requests.append({"file": run.path(a["file"]).resolve().as_posix(), "name": name, "compression": a["compression"],
                                 "lod_group": tex_cfg["lod_group"], "mip_gen": tex_cfg["mip_gen"], "never_stream": bool(tex_cfg["never_stream"]),
                                 "srgb": bool(tex_cfg["srgb"])})
            res = tc.call("import_ui_textures", {"dest_path": rpath, "textures": requests})
            got = {t["name"]: t for t in res.get("textures", [])}
            imported = []
            for a, req in zip(todo, requests):
                t = got.get(req["name"])
                if t is None:
                    raise StageError("IMPORT_INCOMPLETE", f"import_ui_textures did not return '{req['name']}'", asset=a["asset_id"])
                a["ue_path"] = package_of(t["asset_path"])
                state["textures"][a["asset_id"]] = {"name": req["name"], "ue_path": a["ue_path"], "sha256": a["sha256"], "attempt": attempt}
                imported.append({"asset_id": a["asset_id"], "ue_path": a["ue_path"], "compression": t.get("compression"),
                                 "size": t.get("size"), "seconds": t.get("seconds")})
            state["names_used"] = sorted(used)
            schema.require("manifest", manifest)
            run.write_json("manifest.json", manifest)
            entry["ops"].append("import")
            entry["imported"] = imported

        # -- WBP 생성 (첫 시도 · 세션이 바뀐 뒤) ------------------------------------------------------------------------
        if not state["wbp"]:
            res = tc.call("create_widget_blueprint", {"asset_path": wbp_path, "parent_class": parent_class, "root_id": spec["root"]})
            state["wbp"] = {"asset_path": wbp_path, "object_path": res.get("asset_path"), "parent_class": res.get("parent_class"),
                            "created_attempt": attempt}
            state["revision"] = res["revision"]
            entry["ops"].append("create")
            entry["create"] = {"revision": res["revision"], "root": res.get("root"), "compile": _compile_summary(res.get("compile")),
                               "parent_bindings": len(res.get("bindings") or []),
                               "required_bindings": sum(1 for b in res.get("bindings") or [] if not b.get("optional"))}

        # -- 조정기 -------------------------------------------------------------------------------------------------------
        norm = spec_mod.normalize(spec)
        target = {"root": norm["root"], "widgets": norm["widgets"], "locked": norm["locked"]}
        assets = {a["asset_id"]: a["ue_path"] for a in manifest["assets"]}
        res = tc.call("apply_widget_spec", {"asset_path": wbp_path, "spec": target, "assets": assets, "expected_revision": state["revision"]})
        ops = res.get("ops") or []
        state["revision"] = res["revision_after"]
        entry["ops"].append("apply")
        entry["apply"] = {"ops": len(ops), "op_kinds": dict(collections.Counter(o.get("op") for o in ops)),
                          "changed_widgets": sorted({o.get("widget") for o in ops if o.get("widget")}),
                          "revision_before": res.get("revision_before"), "revision_after": res["revision_after"],
                          "verified": res.get("verified"), "compile": _compile_summary(res.get("compile"))}
    except ToolchainError as exc:
        entry["error"] = {"code": exc.code, "message": str(exc)}
        _finish(run, state, entry, t_start)
        raise toolchain_error(exc, "build: ") from exc
    except StageError as exc:
        entry["error"] = {"code": exc.code, "message": str(exc)}
        _finish(run, state, entry, t_start)
        raise
    _finish(run, state, entry, t_start)
    imported = len(entry.get("imported", []))
    created = "create + " if "create" in entry["ops"] else ""
    return (f"attempt {attempt}: {created}apply {entry['apply']['ops']} op(s) → {state['revision'][:17]}…"
            f"{f', imported {imported} texture(s)' if imported else ''}{' (session reset)' if entry.get('reset') else ''}")


def _finish(run, state: dict, entry: dict, t_start: float) -> None:
    entry["duration_s"] = round(time.monotonic() - t_start, 3)
    entry["finished"] = metrics.now_iso()
    save_state(run, state)
