"""run 문맥 — run_id · 작업 폴더 · 잠금 · 단계 기록 (설계 §2-1 · §2-2).

한 번에 run 하나(work/.lock) — 브리지 · 에디터가 하나이고, 에디터가 둘 뜨면 UNAUTHORIZED 가 난다.
잠금 파일의 pid 가 살아 있으면 거절하고, 죽었으면(이전 run 이 비정상 종료) 넘겨받고 기록한다.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import re
import time

from core import metrics
from core.proc import pid_alive

RUN_ID_RE = re.compile(r"^R\d{8}_\d{6}_[A-Za-z0-9]+$")


class RunError(Exception):
    def __init__(self, code: str, message: str, **details):
        self.code = code
        self.details = details
        super().__init__(f"{code}: {message}")


class LockBusy(RunError):
    pass


def new_run_id(screen_id: str, now: _dt.datetime | None = None) -> str:
    now = now or _dt.datetime.now()
    return f"R{now:%Y%m%d_%H%M%S}_{screen_id}"


class RunLock:
    def __init__(self, work_root: pathlib.Path, run_id: str):
        self.path = pathlib.Path(work_root) / ".lock"
        self.run_id = run_id
        self.taken_over: dict | None = None
        self._held = False

    def __enter__(self) -> "RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = json.dumps({"pid": os.getpid(), "run_id": self.run_id, "started": metrics.now_iso()})
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    held = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    held = {}
                if pid_alive(int(held.get("pid", 0) or 0)):
                    raise LockBusy("RUN_LOCKED", f"another uigen run holds {self.path}: {held}", holder=held)
                self.taken_over = held
                self.path.unlink(missing_ok=True)   # 죽은 run 의 잠금 — 넘겨받는다
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
            self._held = True
            return self
        raise LockBusy("RUN_LOCKED", f"could not take {self.path}")

    def __exit__(self, *exc) -> None:
        if self._held:
            try:
                held = json.loads(self.path.read_text(encoding="utf-8"))
                if held.get("pid") == os.getpid() and held.get("run_id") == self.run_id:
                    self.path.unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
            self._held = False


class Run:
    """work/<run_id>/ 와 run.json(단계 기록)."""

    def __init__(self, run_id: str, work_root: pathlib.Path, cfg: dict, metrics_path: pathlib.Path):
        if not RUN_ID_RE.match(run_id):
            raise RunError("BAD_RUN_ID", f"'{run_id}' is not R<yyyymmdd>_<hhmmss>_<ScreenId>")
        self.run_id = run_id
        self.work_root = pathlib.Path(work_root)
        self.dir = self.work_root / run_id
        self.cfg = cfg
        self.metrics_path = pathlib.Path(metrics_path)
        self.started = time.monotonic()
        self.record = {"run_id": run_id, "started": metrics.now_iso(), "stages": [], "status": "running"}
        self._stage_t0: dict[str, float] = {}

    def create(self) -> None:
        if self.dir.exists() and any(self.dir.iterdir()):
            raise RunError("RUN_EXISTS", f"{self.dir} already has files — run ids are never reused")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.save_record()

    def path(self, *parts: str) -> pathlib.Path:
        return self.dir.joinpath(*parts)

    def write_json(self, rel: str, obj) -> pathlib.Path:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        return p

    def read_json(self, rel: str):
        return json.loads(self.path(rel).read_text(encoding="utf-8"))

    def append_jsonl(self, rel: str, record: dict) -> None:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"ts": metrics.now_iso(), **record}, ensure_ascii=False, sort_keys=True) + "\n")

    def log(self, message: str) -> None:
        line = f"[{_dt.datetime.now():%H:%M:%S}] {message}"
        print(line, flush=True)
        with open(self.path("run.log"), "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")

    def stage_begin(self, name: str) -> None:
        self._stage_t0[name] = time.monotonic()
        self.log(f"stage {name}: start")

    def stage_end(self, name: str, status: str, detail: str = "", **extra) -> float:
        dur = round(time.monotonic() - self._stage_t0.pop(name, time.monotonic()), 3)
        self.record["stages"].append({"name": name, "status": status, "duration_s": dur, **({"detail": detail} if detail else {}), **extra})
        self.save_record()
        self.log(f"stage {name}: {status}{f' — {detail}' if detail else ''} ({dur:.2f}s)")
        return dur

    def durations(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for s in self.record["stages"]:
            out[s["name"]] = round(out.get(s["name"], 0.0) + s["duration_s"], 3)
        return out

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def save_record(self) -> None:
        self.write_json("run.json", self.record)
