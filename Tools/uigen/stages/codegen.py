"""codegen — spec 의 바인딩 계약 → C++ 생성 베이스(매번) + 스텁(한 번) → UBT 빌드 → 에디터 재기동 (설계 §2-2 · §3-3).

출력: Source/<module>/<ui_dir>/<feature>/AutoGen/<ViewBase>.h/.cpp · <feature>/<Widget>.h/.cpp(없을 때만) ·
      work/<run_id>/codegen.json(계약 해시 · 쓴 파일 · skipped · 빌드 · 검증) · codegen/build.log · codegen/editor.log

소유 규칙(§3-3):
  1. AutoGen 파일은 첫 줄 표식이 있을 때만 덮어쓴다 — 표식 없는 파일이 있으면 아무것도 쓰지 않고 거부(CODEGEN_NOT_OWNED).
     스텁은 없을 때만 만든다(있으면 내용이 무엇이든 손대지 않는다).
  2. 바인딩은 추가만 — spec 에서 빠진 것은 BindWidgetOptional 로 남는다(core/cppgen.merge).
  3. 쓰기부터 빌드 성공 전까지 실패하면 이번에 쓴 파일을 되돌린다: 덮어쓴 파일은 codegen/backup/ 에서 복원, 새로 만든 파일은
     codegen/failed/ 로 옮긴다(실패한 판도 거기 남는다). 빌드가 성공한 뒤의 실패(기동 · 브리지 · 계약 불일치)는 되돌리지 않는다 —
     바이너리가 이미 새 코드라 소스가 그것과 같아야 한다.
  4. 클래스 이름이 정체성 — screens.yaml 의 이름을 그대로 쓴다. 5. 헤더 이름은 모듈 안에서 겹치면 안 된다(ViewBase/Widget 접미사 ·
     같은 이름 헤더가 다른 곳에 있으면 거부). 생성 cpp 에는 익명 네임스페이스가 없다(템플릿).
끝 조건: 계약 해시가 기존 생성 헤더와 같으면(스텁도 있으면) 쓰기 · 빌드 · 재기동을 건너뛴다(skipped). 에디터가 떠 있으면 그 클래스의
리플렉션(list_bind_widgets)이 계약과 같은지만 보고, 다르면(바이너리가 낡음) 빌드 · 재기동한다.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import time

from core import config
from core import cppgen
from core import metrics
from core import schema
from core.ue import Toolchain, ToolchainError
from stages import StageError

STUB_KEYS = ("widget_h", "widget_cpp")
AUTOGEN_KEYS = ("view_base_h", "view_base_cpp")


def default_toolchain(run) -> Toolchain:
    return Toolchain(run.cfg, log=run.log)


# ---------------------------------------------------------------------------------------------------------------------
# 쓰기 · 되돌리기

class SourceWriter:
    """C++ 파일 쓰기 기록 — 실패하면 restore() 가 이번에 쓴 것만 되돌린다. 줄 끝은 CRLF(저장소 작업 트리와 같게), UTF-8(BOM 없음)."""

    def __init__(self, run_dir: pathlib.Path, base: pathlib.Path):
        cg = pathlib.Path(run_dir) / "codegen"
        self.backup_root = _fresh(cg, "backup")
        self.failed_root = _fresh(cg, "failed")
        self.base = pathlib.Path(base)
        self.written: list[dict] = []
        self.created_dirs: list[pathlib.Path] = []

    def rel(self, path: pathlib.Path) -> str:
        try:
            return pathlib.Path(path).resolve().relative_to(self.base.resolve()).as_posix()
        except ValueError:
            return pathlib.Path(*pathlib.Path(path).resolve().parts[1:]).as_posix()

    def write(self, path: pathlib.Path, text: str) -> str:
        path = pathlib.Path(path)
        data = text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
        if path.exists():
            if path.read_bytes() == data:
                return "unchanged"
            dst = self.backup_root / self.rel(path)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)
            action = "overwritten"
        else:
            missing = []
            d = path.parent
            while not d.exists():
                missing.append(d)
                d = d.parent
            for d in reversed(missing):
                d.mkdir()
                self.created_dirs.append(d)
            action = "created"
        path.write_bytes(data)
        self.written.append({"path": path, "action": action})
        return action

    def restore(self) -> list[dict]:
        out = []
        for entry in reversed(self.written):
            path, rel = entry["path"], self.rel(entry["path"])
            failed = self.failed_root / rel
            failed.parent.mkdir(parents=True, exist_ok=True)
            if entry["action"] == "overwritten":
                shutil.copy2(path, failed)
                shutil.copy2(self.backup_root / rel, path)
                out.append({"path": rel, "restored": "from_backup", "failed_copy": failed.as_posix()})
            else:
                os.replace(path, failed)
                out.append({"path": rel, "restored": "moved_to_failed", "failed_copy": failed.as_posix()})
        for d in reversed(self.created_dirs):
            try:
                d.rmdir()   # 이번에 만든 빈 폴더만
            except OSError:
                pass
        self.written.clear()
        return out


def _fresh(parent: pathlib.Path, name: str) -> pathlib.Path:
    """parent/name 이 이미 있으면 name_2, name_3 … — 같은 run 안의 두 번째 codegen(재시도)이 앞의 기록을 덮지 않게."""
    p, n = parent / name, 1
    while p.exists():
        n += 1
        p = parent / f"{name}_{n}"
    return p


def _sha256(path: pathlib.Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


# ---------------------------------------------------------------------------------------------------------------------
# 단계

def _module_root(run, opts) -> pathlib.Path:
    override = getattr(opts, "module_root", None)
    return pathlib.Path(override) if override else config.repo_path(run.cfg["codegen"]["module_root"])


def _check_header_names(module_root: pathlib.Path, paths: dict[str, pathlib.Path]) -> None:
    """UHT — 헤더 파일 이름은 모듈 안에서 하나여야 한다(§3-3 규칙 5)."""
    wanted = {paths[k].name: paths[k].resolve() for k in ("view_base_h", "widget_h")}
    if not module_root.is_dir():
        return
    for p in module_root.rglob("*.h"):
        target = wanted.get(p.name)
        if target is not None and p.resolve() != target:
            raise StageError("HEADER_NAME_TAKEN", f"{p.as_posix()} already uses the header name {p.name} — UHT needs unique header names per module",
                             existing=p.as_posix())


def _stop_editor(tc, rec: dict, run) -> None:
    status = tc.editor_status()
    rec["was_running"] = status is not None
    if status is not None:
        run.log("codegen: quitting the editor (discard only under /Game/_AutoGen/)")
        q = tc.quit_editor()
        pid = int(q.get("process_id") or status.get("process_id") or 0) or None
        rec["quit"] = {"process_id": pid, "discarded_packages": q.get("discarded_packages", [])}
        rec["exit_s"] = tc.wait_exit(pid)
    left = tc.editor_processes()
    if left:
        raise StageError("EDITOR_STILL_RUNNING", f"UnrealEditor process(es) still running: {left} — the build would fight over the DLLs; quit them first",
                         processes=left)


def _restart_and_verify(tc, run, class_path: str, bindings: list[dict], rec: dict) -> None:
    t0 = time.monotonic()
    pid = tc.launch_editor(run.path("codegen", "editor.log"))
    rec["editor"]["launched_pid"] = pid
    rec["editor"]["bridge_s"] = tc.wait_bridge(pid)
    rec["editor"]["restart_s"] = round(time.monotonic() - t0, 1)
    live = tc.list_bind_widgets(class_path)
    diff = cppgen.contract_diff(bindings, live)
    rec["verify"] = {"class": class_path, "bindings": live, "match": not diff, "diff": diff}
    if diff:
        raise StageError("CONTRACT_MISMATCH", f"{class_path} after the build does not match the contract: " + "; ".join(diff[:6]), diff=diff)


def _write_record(run, rec: dict) -> None:
    rec["finished"] = metrics.now_iso()
    schema.require("codegen", rec)
    run.write_json("codegen.json", rec)


def run(run, opts, toolchain=None) -> str:
    t_start = time.monotonic()
    cfg = run.cfg
    cg = cfg.get("codegen")
    if not isinstance(cg, dict):
        raise StageError("CONFIG", "pipeline.yaml: 'codegen' section is missing")
    spec = run.read_json("spec.json")
    brief = run.read_json("brief.json")
    screen_id = brief["screen_id"]
    screens = config.load_screens()
    screen = screens.get(screen_id)
    if not isinstance(screen, dict):
        raise StageError("SCREEN_UNKNOWN", f"screens.yaml has no screen '{screen_id}'")
    errs = cppgen.validate_screen(screen_id, screen)
    if errs:
        raise StageError("SCREEN_CONFIG", "; ".join(errs), errors=errs)
    contract_class = (brief.get("binding_contract") or {}).get("class")
    if contract_class and contract_class != f"U{screen['widget']}":
        raise StageError("CONTRACT_CLASS", f"brief.binding_contract.class '{contract_class}' != screens.yaml '{screen_id}.widget' U{screen['widget']}")

    module_root = _module_root(run, opts)
    paths = cppgen.target_paths(module_root, cg["ui_dir"], screen)
    _check_header_names(module_root, paths)
    existing = {k: cppgen.read_generated(p) for k, p in paths.items()}
    for key in AUTOGEN_KEYS:
        e = existing[key]
        if e["exists"] and not e["owned"]:
            raise StageError("CODEGEN_NOT_OWNED", f"{paths[key].as_posix()} has no '{cppgen.MARKER}' first line — it belongs to a person now; "
                             "uigen will not overwrite it (put the marker back or move the file to take it over)", path=paths[key].as_posix())
        if e["owned"] and e["corrupt"]:
            raise StageError("CODEGEN_HEADER_CORRUPT", f"{paths[key].as_posix()}: {e['corrupt']}", path=paths[key].as_posix())
    prev_h = existing["view_base_h"]
    prev_contract = prev_h["contract"] if prev_h["owned"] else None
    if prev_h["owned"] and prev_contract is None:
        raise StageError("CODEGEN_HEADER_CORRUPT", f"{paths['view_base_h'].as_posix()}: no contract line — cannot tell which bindings already exist")

    try:
        bindings, changes = cppgen.merge(cppgen.binding_entries(spec), prev_contract["bindings"] if prev_contract else None)
    except cppgen.ContractError as exc:
        raise StageError(exc.code, str(exc).split(": ", 1)[-1], **exc.details) from exc
    doc = cppgen.contract_doc(screen_id, screen, cg, bindings)
    chash = cppgen.contract_hash(doc)
    texts = cppgen.render(doc, chash)
    class_path = f"/Script/{cg['module']}.{screen['widget']}"
    # 기록 · backup 의 상대 경로 기준 — 저장소 안이면 저장소 루트(Source/AstralBreak/UI/…), 밖(시험 임시 폴더)이면 모듈의 두 단계 위
    in_repo = module_root.resolve().is_relative_to(config.REPO_ROOT.resolve())
    writer = SourceWriter(run.dir, config.REPO_ROOT if in_repo else module_root.resolve().parent.parent)

    rec = {"schema_version": 1, "run_id": run.run_id, "screen": screen_id, "class": class_path,
           "contract_hash": chash, "previous_hash": prev_h["hash"] if prev_h["owned"] else None, "contract": doc,
           "changes": changes, "skipped": False, "reason": "", "files": [],
           "editor": {"was_running": None}, "build": {"ran": False}, "verify": None, "restored": [], "started": metrics.now_iso()}
    same = (all(existing[k]["owned"] and existing[k]["hash"] == chash for k in AUTOGEN_KEYS)
            and all(existing[k]["exists"] for k in STUB_KEYS))
    rec["reason"] = "contract_unchanged" if same else ("new" if prev_contract is None else "contract_changed")
    tc = toolchain or default_toolchain(run)

    def file_rows(actions: dict[str, str]) -> list[dict]:
        return [{"role": k, "path": writer.rel(paths[k]), "action": actions.get(k, "unchanged"), "sha256": _sha256(paths[k])} for k in paths]

    try:
        if same:
            status = tc.editor_status()
            rec["editor"]["was_running"] = status is not None
            if status is None:
                rec.update(skipped=True, reason="contract_unchanged", files=file_rows({}))
                rec["verify"] = {"class": class_path, "match": None, "note": "editor not running — class reflection not checked"}
                rec["durations_s"] = {"codegen": round(time.monotonic() - t_start, 3)}
                _write_record(run, rec)
                return f"skipped — contract {chash[:17]}… unchanged (editor not running)"
            try:
                live = tc.list_bind_widgets(class_path)
                diff = cppgen.contract_diff(bindings, live)
            except ToolchainError as exc:   # 클래스가 바이너리에 없다(소스만 있고 빌드 안 됨) → 낡은 바이너리로 본다
                if (exc.details.get("error") or {}).get("code") != "TYPE_NOT_FOUND":
                    raise
                live, diff = [], [f"{class_path} does not load in the running editor"]
            if not diff:
                rec.update(skipped=True, reason="contract_unchanged", files=file_rows({}))
                rec["verify"] = {"class": class_path, "bindings": live, "match": True, "diff": []}
                rec["durations_s"] = {"codegen": round(time.monotonic() - t_start, 3)}
                _write_record(run, rec)
                return f"skipped — contract {chash[:17]}… unchanged, {class_path} matches ({len(live)} bindings)"
            rec["reason"] = "stale_binary"
            rec["stale_diff"] = diff
            run.log(f"codegen: contract unchanged but the running editor's class differs ({'; '.join(diff[:3])}) — rebuilding")
    except ToolchainError as exc:
        rec["error"] = {"code": exc.code, "message": str(exc)}
        _write_record(run, rec)
        raise StageError(exc.code, str(exc).split(": ", 1)[-1], **exc.details) from exc

    actions: dict[str, str] = {}
    try:
        _stop_editor(tc, rec["editor"], run)
        for key in (*AUTOGEN_KEYS, *STUB_KEYS):
            if key in STUB_KEYS and existing[key]["exists"]:
                actions[key] = "kept"   # 스텁은 사람 소유 — 있으면 손대지 않는다
                continue
            actions[key] = writer.write(paths[key], texts[key])
        run.log("codegen: " + ", ".join(f"{paths[k].name} {a}" for k, a in actions.items()))
        build = tc.build(run.path("codegen", "build.log"))
        rec["build"] = {"ran": True, **{k: v for k, v in build.items() if k != "command"}, "command": " ".join(map(str, build.get("command", []))),
                        "log": "codegen/build.log"}
        if not build["ok"]:
            raise StageError("BUILD_FAILED", f"{build.get('result_line') or 'no Result line'} (exit {build.get('exit_code')}) — "
                             + ("; ".join(build.get("errors", [])[:3]) or "see codegen/build.log"), errors=build.get("errors", []))
    except BaseException as exc:   # 빌드 성공 전의 모든 실패(사람의 Ctrl+C 포함) — 쓴 파일을 되돌린다(소유 규칙 3)
        rec["restored"] = writer.restore()
        rec["files"] = file_rows({k: f"{a} → restored" for k, a in actions.items() if a in ("created", "overwritten")})
        rec["error"] = {"code": getattr(exc, "code", type(exc).__name__), "message": str(exc) or type(exc).__name__}
        rec["durations_s"] = {"codegen": round(time.monotonic() - t_start, 3)}
        _write_record(run, rec)
        if isinstance(exc, StageError) or not isinstance(exc, (ToolchainError, OSError)):
            raise
        raise StageError(getattr(exc, "code", "CODEGEN_IO"), str(exc), **getattr(exc, "details", {})) from exc

    rec["files"] = file_rows(actions)
    try:
        _restart_and_verify(tc, run, class_path, bindings, rec)
    except (StageError, ToolchainError) as exc:
        rec["error"] = {"code": exc.code, "message": str(exc)}
        rec["durations_s"] = {"codegen": round(time.monotonic() - t_start, 3), "build": rec["build"].get("duration_s")}
        _write_record(run, rec)
        if isinstance(exc, StageError):
            raise
        raise StageError(exc.code, str(exc).split(": ", 1)[-1], **exc.details) from exc
    rec["durations_s"] = {"codegen": round(time.monotonic() - t_start, 3), "build": rec["build"].get("duration_s"),
                          "restart": rec["editor"].get("restart_s")}
    _write_record(run, rec)
    wrote = sum(1 for a in actions.values() if a in ("created", "overwritten"))
    return (f"{rec['reason']} — contract {chash[:17]}… ({len(bindings)} bindings, +{len(changes['added'])} added, {len(changes['demoted'])} demoted), "
            f"{wrote} file(s) written, build {rec['build'].get('duration_s')}s, {class_path} matches")
