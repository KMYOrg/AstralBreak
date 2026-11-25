"""승격본 기록 · 재승격 · 되돌리기 (Phase 4 — 설계 §11 'Phase 4 설계' ⑤ ~ ⑦). **사람이 확인하고 부르는 명령** — 무인 파이프라인은 부르지 않는다.

    promote_screen.py status [<ScreenId> …]                 승격본 · 원천 묶음이 기록 그대로인가(에디터 없음). 다른 것이 있으면 종료 코드 1
    promote_screen.py record <ScreenId> --run <run_id>      이미 승격된 run 을 기록(소급) — 역추출 · 렌더가 run 기록과 바이트까지 같을 때만
    promote_screen.py plan <ScreenId> --run <run_id>        재승격해도 되는지만 본다(에디터 없음 · 바꾸지 않음)
    promote_screen.py apply <ScreenId> --run <run_id> --yes 재승격 — 에디터를 끈 채 부른다. 옛 파일 · 기록을 사본으로 두고 바꾼 뒤 확인, 어디서 실패하든 되돌린다
    promote_screen.py revert <ScreenId> --yes               마지막 재승격을 되돌린다(사본 그대로 — 바이트 같음, 에디터 불필요)
    promote_screen.py recover <ScreenId>                    중간에 끊긴 재승격 · 되돌리기를 사본으로 되돌린다

안전 규칙: '/Game/_AutoGen/<run_id>/ 아래에만 생성 · 기존 애셋 덮어쓰기 금지'는 파이프라인에 그대로다. 예외는 이 명령 하나 — 자기가 기록한 파일이 **그대로일 때만**
(파일 SHA256 + 파일 목록, 하나라도 다르면 거절 · 강제 옵션 없음), 해시를 확인한 사본을 남긴 뒤 바꾼다. 엔진 쪽 promote_widget 은 지금처럼 빈 폴더에만 쓴다.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from core import config  # noqa: E402
from core import cppgen  # noqa: E402
from core import metrics  # noqa: E402
from core import promotion as promo  # noqa: E402
from core import schema  # noqa: E402
from core.run import LockBusy, RunLock  # noqa: E402
from core.ue import Toolchain, ToolchainError  # noqa: E402
from stages import StageError, edit  # noqa: E402

EXIT_OK, EXIT_FAIL = 0, 1
READY_TRIES, READY_WAIT_S = 18, 10.0        # promote_widget dry_run — 레지스트리가 아직 읽는 중이면 기다린다
GONE_TRIES, GONE_WAIT_S = 120, 5.0          # 에디터 프로세스가 목록에서 사라질 때까지 — 종료 코드를 낸 뒤에도 정리에 몇 분 걸린 적이 있다 [실측 11-25 시험 60개 뒤 약 6분]


def make_toolchain(cfg: dict) -> Toolchain:
    return Toolchain(cfg, log=lambda m: print(m, flush=True))


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="uigen — promotion records, in-place re-promotion and revert (a person confirms and runs it)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, screen="one", run=False, yes=False, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument("screen", nargs="*" if screen == "many" else None)
        if run:
            p.add_argument("--run", required=True, help="run id under work/")
        if yes:
            p.add_argument("--yes", action="store_true", help="a person confirmed this change")
        p.add_argument("--promoted-root")
        p.add_argument("--content-root")
        p.add_argument("--work-root")
        p.add_argument("--module-root")
        return p

    add("status", "many")
    add("record", run=True)
    add("plan", run=True).add_argument("--unrelated", action="store_true", help="the run is not a child of the promoted screen — its piled edits are lost")
    add("apply", run=True, yes=True).add_argument("--unrelated", action="store_true", help="the run is not a child of the promoted screen — its piled edits are lost")
    add("revert", yes=True)
    add("recover")
    return ap.parse_args(argv)


def say(message: str) -> None:
    print(message, flush=True)


def make_store(opts, cfg: dict) -> promo.Store:
    return promo.Store(opts.promoted_root, opts.content_root, opts.work_root or config.repo_path(cfg["paths"]["work_root"]))


def dest_of(screen: str) -> str:
    sc = config.load_screens().get(screen)
    if not isinstance(sc, dict) or not sc.get("promote_path"):
        raise promo.PromotionError("SCREEN_UNKNOWN", f"screens.yaml has no promote_path for '{screen}'")
    return f"{sc['promote_path'].rstrip('/')}/{screen}"


# ---------------------------------------------------------------------------------------------------------------------
# 확인(에디터 없음)

def require_editor_off(tc) -> None:
    procs = tc.editor_processes()
    if procs or tc.editor_status() is not None:
        raise promo.PromotionError("EDITOR_RUNNING", f"close the editor first ({procs or 'bridge answers'}) — the promoted files are replaced on disk", processes=procs)


def require_no_unfinished(store: promo.Store, screen: str) -> None:
    left = store.unfinished(screen)
    if left:
        raise promo.PromotionError("PROMOTION_UNFINISHED", f"an unfinished promotion is left in {left[0].as_posix()} — promote_screen.py recover {screen}")


def generated_contract(cfg: dict, opts, screen: str) -> str | None:
    """지금 생성 C++ 의 계약 해시(검증 화면 · 손으로 쓴 부모를 쓰는 칸은 생성 C++ 가 없어 None)."""
    sc = config.load_screens()[screen]
    if sc.get("probe") or cppgen.hand_written(sc):
        return None
    root = pathlib.Path(opts.module_root) if opts.module_root else config.repo_path(cfg["codegen"]["module_root"])
    return cppgen.read_generated(cppgen.target_paths(root, cfg["codegen"]["ui_dir"], sc)["view_base_h"])["hash"]


def read_run(store: promo.Store, cfg: dict, opts, screen: str, run_id: str) -> dict:
    """승격할 run — 통과 · 저장됨 · 계약 = 지금 생성 C++. {dir, lineage, manifest, spec, brief, attempt, edit, files}."""
    rd = store.run_dir(run_id)
    docs = {}
    for f in ("lineage.json", "report.json", "manifest.json", "spec.json", "brief.json"):
        if not (rd / f).is_file():
            raise promo.PromotionError("RUN_INCOMPLETE", f"{rd.as_posix()} has no {f}")
        docs[f] = json.loads((rd / f).read_text(encoding="utf-8"))
    lin, rep = docs["lineage.json"], docs["report.json"]
    if lin["screen_id"] != screen or docs["brief.json"]["screen_id"] != screen:
        raise promo.PromotionError("WRONG_SCREEN", f"{run_id} is a run of '{lin['screen_id']}', not '{screen}'")
    if lin["status"] != "pass" or rep["status"] != "pass" or (rep.get("finalize") or {}).get("action") != "saved":
        raise promo.PromotionError("RUN_NOT_PASSED", f"{run_id} did not pass and save (lineage {lin['status']}, report {rep['status']}, "
                                   f"finalize {(rep.get('finalize') or {}).get('action')})")
    saved_dir = store.content_root / lin["wbp"].rsplit("/", 1)[0].removeprefix("/Game/")
    files = promo.list_files(saved_dir)
    want = sorted(f"{p.rsplit('/', 1)[1]}.uasset" for p in lin["saved"])
    if sorted(files) != want:
        raise promo.PromotionError("RUN_FILES", f"{saved_dir} holds {sorted(files)[:4]}…, the lineage saved {want[:4]}…")
    now = generated_contract(cfg, opts, screen)
    if now is not None and lin.get("contract_hash") != now:
        raise promo.PromotionError("CONTRACT_CHANGED", f"{run_id} was built for contract {lin.get('contract_hash')}, the generated C++ is {now}")
    ed = json.loads((rd / "edit.json").read_text(encoding="utf-8")) if (rd / "edit.json").is_file() else None
    return {"dir": rd, "lineage": lin, "manifest": docs["manifest.json"], "spec": docs["spec.json"], "brief": docs["brief.json"], "attempt": int(lin["attempts"]),
            "edit": ed, "files": sorted(files), "run_path": lin["wbp"].rsplit("/", 1)[0]}


def check_apply(store: promo.Store, cfg: dict, opts, screen: str) -> tuple[dict, dict, list]:
    """재승격 조건 전부(에디터 없음) → (기록, run, 사라질 수정)."""
    require_no_unfinished(store, screen)
    rec = store.require(screen)
    bad = store.check_files(rec)
    if bad:
        raise promo.PromotionError("PROMOTED_CHANGED", f"{rec['dest']} differs from its promotion record — {bad}. Someone changed the promoted files; nothing was touched",
                                   diff=bad)
    bad = store.check_source(rec)
    if bad:
        raise promo.PromotionError("SOURCE_CHANGED", f"the source bundle of '{screen}' differs from its promotion record — {bad}", diff=bad)
    run = read_run(store, cfg, opts, screen, opts.run)
    if opts.run == rec["run_id"]:
        raise promo.PromotionError("ALREADY_PROMOTED", f"{opts.run} is the promoted run already")
    ok, why = promo.is_child(rec, run["edit"])
    lost: list = []
    if ok:
        say(f"parent: {why}")
    elif not opts.unrelated:
        raise promo.PromotionError("NOT_A_CHILD", f"{opts.run} does not continue the promoted screen: {why}. A full run replaces it only with --unrelated "
                                   f"(edits that would be lost: {[e['run_id'] for e in rec['edits']] or 'none'})")
    else:
        lost = rec["edits"]
        say(f"unrelated run ({why}) — edits that will be lost: {[(e['run_id'], e.get('note')) for e in lost] or 'none'}")
    names = {f"{p.rsplit('/', 1)[1]}.uasset" for p in run["lineage"]["saved"]}
    say(f"files: {len(rec['files'])} now, {len(names)} after; added {sorted(names - set(rec['files']))}, gone {sorted(set(rec['files']) - names)}")
    return rec, run, lost


# ---------------------------------------------------------------------------------------------------------------------
# 에디터

def compare(tc, cfg: dict, run: dict, wbp: str, textures: dict, out: pathlib.Path) -> dict:
    """승격본 WBP ↔ run 의 최종 spec · 마지막 시도의 그림 전부."""
    reqs = edit.recorded_requests(run["dir"], run["attempt"], cfg)
    return edit.compare_wbp(tc, cfg, run["spec"], run["brief"], wbp, textures, reqs, edit.attempt_images(run["dir"], run["attempt"]), out)


def verdict(res: dict) -> str:
    r = res["renders"]
    return (f"roundtrip {'same' if res['roundtrip_equal'] else 'DIFFERENT ' + str(res['diffs'][:3])}, pictures {r['same_pixels']}/{r['n']} same "
            f"({r['same_bytes']} to the byte){', different ' + str(sorted(r['different'])[:5]) if r['different'] else ''}, unsupported {len(res['unsupported'])}")


def verified_record(res: dict) -> dict:
    r = res["renders"]
    return {"roundtrip_equal": res["roundtrip_equal"], "pictures": r["n"], "same_pixels": r["same_pixels"], "same_bytes": r["same_bytes"],
            "unsupported": len(res["unsupported"])}


def start_editor(tc, log_dir: pathlib.Path) -> int:
    pid = tc.launch_editor(log_dir / "editor.log")
    tc.wait_bridge(pid)
    return pid


def stop_editor(tc) -> None:
    st = tc.editor_status()
    if st is None:
        return
    q = tc.quit_editor()
    tc.wait_exit(int(q.get("process_id") or st.get("process_id") or 0) or None)
    for _ in range(GONE_TRIES):                 # 브리지 · 종료 코드만으로는 모자란다 — 파일을 바꾸기 전에 프로세스가 없어야 한다
        if not tc.editor_processes():
            return
        time.sleep(GONE_WAIT_S)
    raise ToolchainError("EXIT_TIMEOUT", f"the editor process is still listed: {tc.editor_processes()}")


def promote(tc, run_path: str, dest: str) -> dict:
    """promote_widget — dry_run 이 통과할 때까지 기다린 뒤(레지스트리 읽는 중) 한 번. 엔진이 빈 폴더에만 쓴다."""
    for k in range(READY_TRIES):
        try:
            tc.call("promote_widget", {"run_path": run_path, "dest_path": dest, "dry_run": True})
            break
        except ToolchainError as exc:
            if k == READY_TRIES - 1:
                raise
            say(f"promote_widget is not ready yet ({exc}) — waiting")
            time.sleep(READY_WAIT_S)
    return tc.call("promote_widget", {"run_path": run_path, "dest_path": dest, "confirm": True}, timeout=300.0)


# ---------------------------------------------------------------------------------------------------------------------
# 명령

def cmd_status(opts, cfg, store) -> int:
    bad_any = False
    screens = opts.screen or store.screens()
    for screen in screens:
        rec = store.load(screen)
        if rec is None:
            say(f"{screen}: no promotion record")
            bad_any = True
            continue
        files, src = store.check_files(rec), store.check_source(rec)
        left = store.unfinished(screen)
        now = generated_contract(cfg, opts, screen)
        say(f"{screen}: {rec['run_id']} (parent {rec['parent_run_id']}, {len(rec['edits'])} edit(s)) -> {rec['dest']}")
        say(f"  promoted files {len(rec['files'])}: {'as recorded' if not files else 'CHANGED ' + json.dumps(files, ensure_ascii=False)}")
        say(f"  source bundle {len(rec['source'])}: {'as recorded' if not src else 'CHANGED ' + json.dumps(src, ensure_ascii=False)}")
        what = "no generated C++ (hand-written parent)" if now is None else "matches the generated C++" if now == rec["contract_hash"] else f"DIFFERS ({rec['contract_hash']} != {now})"
        say(f"  contract: {what}")
        if left:
            say(f"  UNFINISHED promotion: {[p.name for p in left]}")
        bad_any = bad_any or bool(files or src or left) or now not in (None, rec["contract_hash"])
    if not screens:
        say("no promotion records")
    return EXIT_FAIL if bad_any else EXIT_OK


def cmd_record(opts, cfg, store) -> int:
    screen = opts.screen
    if store.load(screen) is not None:
        raise promo.PromotionError("ALREADY_RECORDED", f"{store.record_path(screen)} exists — record is only for a screen promoted before the records existed")
    left = promo.list_files(store.source_dir(screen))
    if left:
        raise promo.PromotionError("SOURCE_LEFT", f"{store.source_dir(screen)} holds {len(left)} file(s) without a record — look at them first")
    run = read_run(store, cfg, opts, screen, opts.run)
    if run["edit"]:
        raise promo.PromotionError("EDIT_RUN", f"{opts.run} is an edit run — it is promoted with apply, not recorded afterwards")
    dest = dest_of(screen)
    have = sorted(promo.list_files(store.content_dir(dest)))
    if have != run["files"]:
        raise promo.PromotionError("PROMOTED_FILES", f"{store.content_dir(dest)} holds {have[:5]}…, the run saved {run['files'][:5]}…")
    wbp = f"{dest}/{run['lineage']['wbp'].rsplit('/', 1)[1]}"
    textures = {a["asset_id"]: f"{dest}/{a['ue_path'].rsplit('/', 1)[1]}" for a in run["manifest"]["assets"]}
    tc = make_toolchain(cfg)
    out = store.backup_root(screen) / f"record_{time.strftime('%Y%m%d_%H%M%S')}"
    started = tc.editor_status() is None
    if started:
        require_editor_off(tc)
        start_editor(tc, out)
    try:
        res = compare(tc, cfg, run, wbp, textures, out / "promoted")
    finally:
        if started:
            stop_editor(tc)
    say(f"promoted <-> run: {verdict(res)}")
    r = res["renders"]
    if not res["roundtrip_equal"] or r["different"] or r["same_bytes"] != r["n"] or res["unsupported"]:
        raise promo.PromotionError("NOT_THE_RUN", f"{dest} is not {opts.run} to the byte — nothing was recorded")
    source = store.copy_source(run["dir"], screen)
    rec = store.make_record(screen, run["dir"], dest, source, verified_record(res), [], res["revision"], run["lineage"].get("parent_run_id"))
    promo.write_json(store.record_path(screen), rec)
    size = sum(p.stat().st_size for p in store.source_dir(screen).rglob("*") if p.is_file())
    say(f"recorded: {store.record_path(screen).as_posix()} — {len(rec['files'])} promoted file(s), bundle {len(source)} file(s) {size / 1048576:.2f} MB")
    return EXIT_OK


def cmd_plan(opts, cfg, store) -> int:
    rec, run, lost = check_apply(store, cfg, opts, opts.screen)
    for e in (run["edit"] or {}).get("edits", [])[len(rec["edits"]) if not lost else 0:]:
        ops = [f"{o['op']} {o['widget']['id'] if o['op'] == 'add_widget' else o['widget']}{'.' + o['path'] + ' = ' + json.dumps(o['value'], ensure_ascii=False) if o['op'] == 'set' else ''}"
               for o in e["patch"]["ops"]]
        say(f"edit {e['run_id']}: {'; '.join(ops)}{' — ' + e['note'] if e.get('note') else ''}")
    for n in (run["edit"] or {}).get("source_notes") or []:
        say(f"stale source: {n.get('file')}{':' + str(n['line']) if n.get('line') else ''} {n['widget']} {n['path']} {n['source_value']} -> {n['edited_value']}")
    if run["edit"]:
        say(f"look first: {(run['dir'] / 'edit.png').as_posix()} · {(run['dir'] / 'compare.png').as_posix()}")
    say(f"plan ok: {rec['run_id']} -> {opts.run} in {rec['dest']} (apply needs --yes and the editor closed)")
    return EXIT_OK


def cmd_apply(opts, cfg, store) -> int:
    screen = opts.screen
    if not opts.yes:
        raise promo.PromotionError("MISSING_YES", "apply replaces promoted assets — pass --yes after a person looked at edit.png / compare.png (plan shows what would change)")
    tc = make_toolchain(cfg)
    require_editor_off(tc)
    rec, run, lost = check_apply(store, cfg, opts, screen)
    j = store.begin("apply", rec, run_id=opts.run, unrelated=bool(opts.unrelated))
    say(f"backup: {j.folder.as_posix()} ({len(rec['files'])} promoted + {len(j.data['promoted_files'])} record file(s), hashes checked)")
    try:
        j.data["created"] = list(run["files"])              # 되돌릴 때 지워도 되는 것 — 이번 재승격이 만들 파일
        j.save()
        store.clear(rec)
        j.step("cleared")
        start_editor(tc, j.folder)
        j.step("promoting")
        done = promote(tc, run["run_path"], rec["dest"])
        j.step("promoted", packages=len(done.get("copied") or []))
        wbp = f"{rec['dest']}/{run['lineage']['wbp'].rsplit('/', 1)[1]}"
        textures = {a["asset_id"]: f"{rec['dest']}/{a['ue_path'].rsplit('/', 1)[1]}" for a in run["manifest"]["assets"]}
        res = compare(tc, cfg, run, wbp, textures, j.folder / "check")
        say(f"promoted <-> run: {verdict(res)}")
        if not res["roundtrip_equal"] or res["renders"]["different"] or res["unsupported"]:
            raise promo.PromotionError("NOT_THE_RUN", f"the promoted copy is not {opts.run}: {verdict(res)}")
        stop_editor(tc)
        j.step("verified")
        have = sorted(promo.list_files(store.content_dir(rec["dest"])))
        if have != run["files"]:
            raise promo.PromotionError("PROMOTED_FILES", f"{rec['dest']} holds {have}, the run saved {run['files']}")
        source = store.replace_source(screen, run["dir"])
        edits = (run["edit"] or {}).get("edits") or []
        new = store.make_record(screen, run["dir"], rec["dest"], source, verified_record(res), edits, res["revision"],
                                (run["edit"] or {}).get("parent_run_id"), lost or rec.get("replaced_edits"))
        promo.write_json(store.record_path(screen), new)
        j.data["new_files"] = new["files"]
        j.step("done")
    except BaseException as exc:
        say(f"apply failed ({type(exc).__name__}: {exc}) — putting the old files back")
        j.data["error"] = f"{type(exc).__name__}: {exc}"[:500]
        j.save()
        try:
            stop_editor(tc)
            store.restore(j)
            j.step("reverted")
            say(f"reverted: {rec['dest']} is as recorded again")
        except Exception as back:  # noqa: BLE001 — 되돌리기까지 실패하면 일지를 열린 채 두고 recover 로
            j.step("failed", error=f"{type(back).__name__}: {back}"[:500])
            say(f"the old files are NOT back ({type(back).__name__}: {back}) — close the editor and run: promote_screen.py recover {screen}")
        raise
    say(f"done: {screen} is now {opts.run} (was {rec['run_id']}) — revert: promote_screen.py revert {screen} --yes")
    return EXIT_OK


def cmd_revert(opts, cfg, store) -> int:
    screen = opts.screen
    if not opts.yes:
        raise promo.PromotionError("MISSING_YES", "revert replaces promoted assets — pass --yes after a person confirmed it")
    tc = make_toolchain(cfg)
    require_editor_off(tc)
    require_no_unfinished(store, screen)
    rec = store.require(screen)
    bad = store.check_files(rec) or store.check_source(rec)
    if bad:
        raise promo.PromotionError("PROMOTED_CHANGED", f"{rec['dest']} or its source bundle differs from the record — {bad}; nothing was touched", diff=bad)
    last = store.last_apply(screen, rec["run_id"])
    if last is None:
        raise promo.PromotionError("NOTHING_TO_REVERT", f"no re-promotion backup made {rec['run_id']}")
    j = store.begin("revert", rec, run_id=last.data["from_run_id"], reverts=last.folder.name)
    try:
        j.data["created"] = sorted(last.data["files"])
        j.save()
        back = promo.Journal(store, last.folder, {**last.data, "created": sorted(rec["files"])})
        res = store.restore(back)
        j.step("done")
    except BaseException as exc:
        j.data["error"] = f"{type(exc).__name__}: {exc}"[:500]
        j.save()
        try:
            store.restore(j)
            j.step("reverted")
        except Exception as again:  # noqa: BLE001
            j.step("failed", error=f"{type(again).__name__}: {again}"[:500])
            say(f"revert failed half way ({again}) — run: promote_screen.py recover {screen}")
        raise
    last.data["reverted_by"] = j.folder.name
    last.save()
    say(f"reverted: {screen} is {last.data['from_run_id']} again ({res['files']} file(s), hashes as recorded) — {rec['run_id']} kept in {j.folder.as_posix()}")
    return EXIT_OK


def cmd_recover(opts, cfg, store) -> int:
    screen = opts.screen
    left = store.unfinished(screen)
    if not left:
        say(f"{screen}: nothing to recover")
        return EXIT_OK
    require_editor_off(make_toolchain(cfg))
    for folder in left:
        j = promo.Journal.open(store, folder)
        if j.data["state"] == "copying":                 # 사본을 다 못 만들었다 — 아직 아무것도 바꾸지 않은 때
            rec = store.require(screen)
            if store.check_files(rec) or store.check_source(rec):
                raise promo.PromotionError("RECOVER_UNSURE", f"{folder} stopped while copying, but the promoted files differ from the record")
        else:
            store.restore(j)
        j.step("recovered")
        say(f"recovered: {screen} from {folder.name} (state was {j.data['steps'][-2]['state']})")
    return EXIT_OK


COMMANDS = {"status": cmd_status, "record": cmd_record, "plan": cmd_plan, "apply": cmd_apply, "revert": cmd_revert, "recover": cmd_recover}


def main(argv=None) -> int:
    opts = parse_args(argv)
    cfg = config.load_pipeline()
    try:
        store = make_store(opts, cfg)
        if opts.cmd in ("status", "plan"):
            return COMMANDS[opts.cmd](opts, cfg, store)
        with RunLock(store.work_root, f"promote_{opts.cmd}_{opts.screen}"):
            say(f"[{metrics.now_iso()}] {opts.cmd} {opts.screen}")
            return COMMANDS[opts.cmd](opts, cfg, store)
    except (promo.PromotionError, StageError, ToolchainError, LockBusy, schema.SchemaError, config.ConfigError) as exc:
        print(f"promote_screen: {exc}", file=sys.stderr, flush=True)
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
