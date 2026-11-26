"""승격 기록 · 원천 묶음 · 사본 · 되돌리기 (Phase 4 — 설계 §11 'Phase 4 설계' ⑤ ~ ⑦). 에디터 없이 파일만 다룬다.

  promoted/<ScreenId>/promotion.json   승격 기록의 단일 원천 — run · 부모 · 승격본 파일마다 SHA256 · 원천 묶음 해시 · 쌓인 수정(edits[])
  promoted/<ScreenId>/source/          원천 묶음 — 다시 짓고 다시 진단하는 데 필요한 최소 파일(run 폴더가 없어져도 이어서 고친다)
  work/_promoted/<ScreenId>/<시각>/     재승격 · 되돌리기 앞의 사본(content/ · promoted/) + journal.json

사람이 고쳤는지 = 파일 SHA256 + 파일 목록(하나라도 다르면 거절 — 강제 옵션 없음). 묶음의 JSON 은 정규(정렬) JSON 해시라 다른 체크아웃의 줄바꿈에 흔들리지 않는다.
지우는 것은 기록에 있고 해시가 그대로이며 사본 해시까지 확인한 파일뿐이다(이번 재승격이 새로 만든 파일은 되돌릴 때 지운다).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import pathlib
import shutil

from core import config
from core import metrics
from core import schema
from core import spec as spec_mod

# 원천 묶음 — run 폴더에서 옮기는 것(실측: 이것만으로 다시 지은 WBP · 다시 한 진단이 기록과 같다). edit.json 은 수정 run 에만 있다.
SOURCE_PATTERNS = ("spec.json", "specs/000.json", "brief.json", "inputs.json", "normalize.json", "manifest.json", "refine.json", "layer.json", "layer/*.png",
                   "gen.jsonl", "codegen.json", "lineage.json", "edit.json", "geometry.json", "diagnosis.json", "assets/final/*.png", "reference.png",
                   "reference_color.png", "reference_alpha.png", "reference_art_*.png", "reference_notext_*.png")
REQUIRED_SOURCE = ("spec.json", "brief.json", "manifest.json", "lineage.json")
# 일지 상태 — 끝난 것: done(바뀜) · reverted(실패해서 되돌림) · recovered(recover 로 되돌림)
CLOSED = ("done", "reverted", "recovered")


class PromotionError(Exception):
    def __init__(self, code: str, message: str, **details):
        self.code = code
        self.details = details
        super().__init__(f"{code}: {message}")


# ---------------------------------------------------------------------------------------------------------------------
# 해시 · 목록

def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_hash(path) -> tuple[str, str]:
    """(kind, sha256) — json · jsonl 은 정규 JSON, 그 밖은 파일 그대로."""
    path = pathlib.Path(path)
    try:
        if path.suffix == ".json":
            return "json", hashlib.sha256(spec_mod.canonical_json(json.loads(path.read_text(encoding="utf-8"))).encode("utf-8")).hexdigest()
        if path.suffix == ".jsonl":
            rows = [spec_mod.canonical_json(json.loads(x)) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
            return "jsonl", hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()
    except ValueError as exc:
        raise PromotionError("SOURCE_UNREADABLE", f"{path}: {exc}") from exc
    return "binary", sha256_file(path)


def list_files(folder) -> dict[str, dict]:
    """폴더 아래 모든 파일 — {상대 경로: {sha256, size}}. 폴더가 없으면 빈 것."""
    folder = pathlib.Path(folder)
    if not folder.is_dir():
        return {}
    return {p.relative_to(folder).as_posix(): {"sha256": sha256_file(p), "size": p.stat().st_size} for p in sorted(folder.rglob("*")) if p.is_file()}


def diff_files(recorded: dict, actual: dict) -> dict | None:
    """기록 ↔ 지금 — 같으면 None, 아니면 {changed, missing, added}."""
    d = {"changed": sorted(k for k in recorded if k in actual and recorded[k]["sha256"] != actual[k]["sha256"]),
         "missing": sorted(k for k in recorded if k not in actual), "added": sorted(k for k in actual if k not in recorded)}
    return d if any(d.values()) else None


def source_files(folder) -> list[str]:
    """run 폴더 · 묶음 폴더에서 원천 묶음에 드는 파일의 상대 경로."""
    folder = pathlib.Path(folder)
    out = {p.relative_to(folder).as_posix() for pat in SOURCE_PATTERNS for p in folder.glob(pat) if p.is_file()}
    return sorted(out)


def hash_source(folder) -> dict[str, dict]:
    folder = pathlib.Path(folder)
    out = {}
    for rel in source_files(folder):
        kind, h = canonical_hash(folder / rel)
        out[rel] = {"kind": kind, "sha256": h, **({"size": (folder / rel).stat().st_size} if kind == "binary" else {})}
    return out


def write_json(path, obj) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _copy(src: pathlib.Path, dst: pathlib.Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def _prune_empty(folder: pathlib.Path) -> None:
    """빈 하위 폴더만 지운다(폴더 자체는 남긴다)."""
    for d in sorted((p for p in folder.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        try:
            d.rmdir()
        except OSError:
            pass


# ---------------------------------------------------------------------------------------------------------------------
# 쌓인 수정 — 부모 이어짐

def is_child(promotion: dict, edit_doc: dict | None) -> tuple[bool, str]:
    """이 수정 run 이 지금 승격본에서 나왔나 — 쌓인 수정이 지금 기록으로 시작하고 그다음 줄의 부모가 지금 승격본."""
    if not edit_doc:
        return False, "not an edit run (a full run starts from the concept — the edits piled on the promoted screen would be lost)"
    mine, theirs = promotion["edits"], edit_doc.get("edits") or []
    if theirs[:len(mine)] != mine:
        return False, "its edit history does not start with the promoted screen's edits"
    if len(theirs) <= len(mine):
        return False, "it adds no edit to the promoted screen"
    nxt = theirs[len(mine)]
    if nxt["parent_run_id"] != promotion["run_id"]:
        return False, f"its edit '{nxt['run_id']}' starts from {nxt['parent_run_id']}, the promoted screen is {promotion['run_id']}"
    return True, f"{len(theirs) - len(mine)} edit(s) on top of {promotion['run_id']}"


# ---------------------------------------------------------------------------------------------------------------------

class Store:
    """승격 기록 · 묶음 · 사본이 있는 곳. 시험은 임시 폴더를 준다."""

    def __init__(self, promoted_root=None, content_root=None, work_root=None):
        self.promoted_root = pathlib.Path(promoted_root or config.UIGEN_DIR / "promoted")
        self.content_root = pathlib.Path(content_root or config.REPO_ROOT / "Content")
        self.work_root = pathlib.Path(work_root or config.repo_path(config.load_pipeline()["paths"]["work_root"]))

    # -- 자리 ----------------------------------------------------------------------------------------------------------

    def screen_dir(self, screen: str) -> pathlib.Path:
        return self.promoted_root / screen

    def record_path(self, screen: str) -> pathlib.Path:
        return self.screen_dir(screen) / "promotion.json"

    def source_dir(self, screen: str) -> pathlib.Path:
        return self.screen_dir(screen) / "source"

    def content_dir(self, dest: str) -> pathlib.Path:
        if not dest.startswith("/Game/") or ".." in dest:
            raise PromotionError("BAD_DEST", f"'{dest}' is not a /Game/ folder")
        return self.content_root / dest.removeprefix("/Game/")

    def run_dir(self, run_id: str) -> pathlib.Path:
        return self.work_root / run_id

    def backup_root(self, screen: str) -> pathlib.Path:
        return self.work_root / "_promoted" / screen

    def screens(self) -> list[str]:
        return sorted(p.parent.name for p in self.promoted_root.glob("*/promotion.json"))

    # -- 읽기 · 확인 ---------------------------------------------------------------------------------------------------

    def load(self, screen: str) -> dict | None:
        p = self.record_path(screen)
        if not p.is_file():
            return None
        rec = json.loads(p.read_text(encoding="utf-8"))
        schema.require("promotion", rec)
        return rec

    def require(self, screen: str) -> dict:
        rec = self.load(screen)
        if rec is None:
            raise PromotionError("NOT_PROMOTED", f"'{screen}' has no promotion record ({self.record_path(screen)}) — promote_screen.py record first")
        return rec

    def check_files(self, rec: dict) -> dict | None:
        """승격본 폴더 ↔ 기록(None = 그대로) — 사람이 고쳤는지의 판정."""
        return diff_files(rec["files"], list_files(self.content_dir(rec["dest"])))

    def check_source(self, rec: dict) -> dict | None:
        src = self.source_dir(rec["screen_id"])
        return diff_files(rec["source"], hash_source(src))

    def unfinished(self, screen: str) -> list[pathlib.Path]:
        out = []
        for p in sorted(self.backup_root(screen).glob("*/journal.json")):
            if json.loads(p.read_text(encoding="utf-8"))["state"] not in CLOSED:
                out.append(p.parent)
        return out

    # -- 쓰기 ----------------------------------------------------------------------------------------------------------

    def copy_source(self, run_dir, screen: str) -> dict[str, dict]:
        """run 폴더 → 원천 묶음(지금 묶음 폴더는 비어 있어야 한다 — replace_source 가 비운다). → 해시 목록."""
        run_dir, dst = pathlib.Path(run_dir), self.source_dir(screen)
        missing = [r for r in REQUIRED_SOURCE if not (run_dir / r).is_file()]
        if missing:
            raise PromotionError("SOURCE_INCOMPLETE", f"{run_dir} has no {missing}")
        want = hash_source(run_dir)
        for rel in want:
            _copy(run_dir / rel, dst / rel)
        got = hash_source(dst)
        if diff_files(want, got):
            raise PromotionError("SOURCE_COPY", f"the bundle copy differs from {run_dir}: {diff_files(want, got)}")
        return got

    def make_record(self, screen: str, run_dir, dest: str, source: dict, verified: dict, edits: list, revision: str | None,
                    parent_run_id: str | None, replaced_edits: list | None = None) -> dict:
        run_dir = pathlib.Path(run_dir)
        lineage = json.loads((run_dir / "lineage.json").read_text(encoding="utf-8"))
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        brief = json.loads((run_dir / "brief.json").read_text(encoding="utf-8"))
        cells: dict[str, dict] = {}                          # 이 화면이 놓은 칸 — 검증한 칸의 run 까지(Phase 3-3)
        for c in brief.get("cells") or []:
            cells.setdefault(c["cell"], {"cell": c["cell"], "class": c["class"], "run_id": c["run_id"], "widgets": []})["widgets"].append(c["widget"])
        rec = {"schema_version": 1, "screen_id": screen, "run_id": lineage["run_id"], "parent_run_id": parent_run_id, "dest": dest,
               "wbp": f"{dest}/{lineage['wbp'].rsplit('/', 1)[1]}",
               "textures": {a["asset_id"]: f"{dest}/{a['ue_path'].rsplit('/', 1)[1]}" for a in manifest["assets"] if a.get("ue_path")},
               "files": list_files(self.content_dir(dest)), "revision": revision, "run_revision": lineage.get("revision"),
               "contract_hash": lineage.get("contract_hash"), "source": source, "edits": edits,
               **({"cells": [cells[k] for k in sorted(cells)]} if cells else {}),
               **({"replaced_edits": replaced_edits} if replaced_edits else {}), "verified": verified, "recorded_at": metrics.now_iso()}
        schema.require("promotion", rec)
        return rec

    # -- 사본 · 일지 ---------------------------------------------------------------------------------------------------

    def begin(self, kind: str, rec: dict, **extra) -> "Journal":
        """지금 승격본 · 기록 · 묶음을 사본으로 — 해시 확인까지. kind = apply | revert."""
        screen = rec["screen_id"]
        stamp = f"{_dt.datetime.now():%Y%m%d_%H%M%S}"
        folder, n = self.backup_root(screen) / stamp, 1
        while folder.exists():
            n += 1
            folder = self.backup_root(screen) / f"{stamp}_{n}"
        folder.mkdir(parents=True)
        j = Journal(self, folder, {"schema_version": 1, "kind": kind, "screen_id": screen, "dest": rec["dest"], "from_run_id": rec["run_id"],
                                   "files": rec["files"], "created": [], "state": "copying", "steps": [], **extra})
        j.step("copying")
        content = self.content_dir(rec["dest"])
        for rel in rec["files"]:
            _copy(content / rel, folder / "content" / rel)
        for p in sorted(self.screen_dir(screen).rglob("*")):
            if p.is_file():
                _copy(p, folder / "promoted" / p.relative_to(self.screen_dir(screen)))
        bad = diff_files(rec["files"], list_files(folder / "content"))
        if bad:
            raise PromotionError("BACKUP_BAD", f"the backup does not match the record: {bad}")
        j.data["promoted_files"] = list_files(folder / "promoted")
        j.step("copied")
        return j

    def clear(self, rec: dict) -> None:
        """승격본 폴더를 비운다 — 기록에 있는 파일만, 지금도 기록 그대로일 때만. 밖의 파일이 있으면 거절."""
        bad = self.check_files(rec)
        if bad:
            raise PromotionError("PROMOTED_CHANGED", f"{rec['dest']} differs from the promotion record: {bad}", diff=bad)
        content = self.content_dir(rec["dest"])
        for rel in rec["files"]:
            os.remove(content / rel)
        _prune_empty(content)
        left = list_files(content)
        if left:
            raise PromotionError("NOT_EMPTY", f"{content} still has {sorted(left)[:5]}")

    def replace_source(self, screen: str, run_dir) -> dict[str, dict]:
        """묶음을 새 run 의 것으로 — 옛 묶음 파일은 지운다(사본이 있을 때만 부른다)."""
        src = self.source_dir(screen)
        for rel in list_files(src):
            os.remove(src / rel)
        _prune_empty(src)
        return self.copy_source(run_dir, screen)

    def restore(self, journal: "Journal") -> dict:
        """사본 그대로 되돌린다 — 승격본 폴더 · 기록 · 묶음. 승격본 폴더에 사본에도 · 이번에 만든 것에도 없는 파일이 있으면 거절(아무것도 안 바꿈)."""
        d = journal.data
        content, backup = self.content_dir(d["dest"]), journal.folder / "content"
        kept = list_files(backup)
        bad = diff_files(d["files"], kept)
        if bad:
            raise PromotionError("BACKUP_BAD", f"the backup {backup} does not match its journal: {bad}", diff=bad)
        now = list_files(content)
        unknown = sorted(set(now) - set(kept) - set(d.get("created") or []))
        if unknown:
            raise PromotionError("UNKNOWN_FILES", f"{content} has file(s) neither in the backup nor made by this promotion: {unknown[:8]} — look at them first")
        for rel in sorted(set(now) - set(kept)):
            os.remove(content / rel)
        for rel, meta in kept.items():
            if (now.get(rel) or {}).get("sha256") != meta["sha256"]:
                _copy(backup / rel, content / rel)
        _prune_empty(content)
        after = diff_files(d["files"], list_files(content))
        if after:
            raise PromotionError("RESTORE_BAD", f"after restoring, {content} still differs: {after}", diff=after)
        screen_dir, pb = self.screen_dir(d["screen_id"]), journal.folder / "promoted"
        want = list_files(pb)
        if diff_files(d["promoted_files"], want):
            raise PromotionError("BACKUP_BAD", f"the record backup {pb} does not match its journal")
        have = list_files(screen_dir)
        for rel in sorted(set(have) - set(want)):
            os.remove(screen_dir / rel)
        for rel, meta in want.items():
            if (have.get(rel) or {}).get("sha256") != meta["sha256"]:
                _copy(pb / rel, screen_dir / rel)
        _prune_empty(screen_dir)
        if diff_files(want, list_files(screen_dir)):
            raise PromotionError("RESTORE_BAD", f"after restoring, {screen_dir} still differs from the backup")
        return {"files": len(kept), "record_files": len(want)}

    def last_apply(self, screen: str, run_id: str) -> "Journal | None":
        """지금 승격본(run_id)을 만든, 아직 되돌리지 않은 마지막 재승격."""
        for p in sorted(self.backup_root(screen).glob("*/journal.json"), reverse=True):
            j = Journal.open(self, p.parent)
            if j.data["kind"] == "apply" and j.data["state"] == "done" and j.data.get("run_id") == run_id and not j.data.get("reverted_by"):
                return j
        return None


class Journal:
    """재승격 · 되돌리기 한 번의 일지 — 어느 단계에서 끊겨도 recover 가 사본으로 되돌린다."""

    def __init__(self, store: Store, folder: pathlib.Path, data: dict):
        self.store, self.folder, self.data = store, pathlib.Path(folder), data

    @classmethod
    def open(cls, store: Store, folder) -> "Journal":
        return cls(store, folder, json.loads((pathlib.Path(folder) / "journal.json").read_text(encoding="utf-8")))

    def step(self, state: str, **extra) -> None:
        self.data["state"] = state
        self.data["steps"].append({"ts": metrics.now_iso(), "state": state, **extra})
        self.save()

    def save(self) -> None:
        write_json(self.folder / "journal.json", self.data)
