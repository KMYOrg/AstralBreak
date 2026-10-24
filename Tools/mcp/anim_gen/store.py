"""상태 저장소 — 계획 · Job(상태 전이) · 승인 · 비용 장부 (지침서 §3.4 · §6).

상태는 anim_gen 만 가진다(§3.1-3). 위치는 Saved/AnimGen/(추적 안 함), ANIM_GEN_STATE_DIR 로 바꿀 수 있다(테스트 격리).
서버 프로세스 하나를 전제한다 — MCP 의 동기 Tool 은 작업 스레드에서 돌기 때문에 프로세스 락으로 읽기-수정-쓰기를 묶고,
파일은 임시 파일 → os.replace 로 바꿔 끼운다.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import threading
import time
import uuid

PROJECT_DIR = pathlib.Path(os.environ.get("ANIMGRAPH_MCP_PROJECT_DIR") or pathlib.Path(__file__).resolve().parents[3])

QUEUED = "QUEUED"
RUNNING = "RUNNING"
WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"
STATES = (QUEUED, RUNNING, WAITING_FOR_APPROVAL, SUCCEEDED, FAILED, CANCELLED)
TERMINAL = frozenset({SUCCEEDED, FAILED, CANCELLED})
# §3.4 전이 표 — 종료 3종 뒤에는 전이가 없다
TRANSITIONS = {
    QUEUED: frozenset({RUNNING, WAITING_FOR_APPROVAL, CANCELLED}),
    RUNNING: frozenset({SUCCEEDED, FAILED, WAITING_FOR_APPROVAL, CANCELLED}),
    WAITING_FOR_APPROVAL: frozenset({QUEUED, CANCELLED}),
}


class InvalidTransition(Exception):
    """허용되지 않은 상태 전이 — 호출자 버그이거나 다른 호출이 먼저 상태를 바꿨다(예: 실행 중 취소)."""

    def __init__(self, job_id: str, current: str, to: str):
        super().__init__(f"{job_id}: {current} -> {to} is not allowed")
        self.job_id = job_id
        self.current = current
        self.to = to


def default_state_dir() -> pathlib.Path:
    env = os.environ.get("ANIM_GEN_STATE_DIR")
    return pathlib.Path(env) if env else PROJECT_DIR / "Saved" / "AnimGen"


def now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    # 콘텐츠 폴더 이름(<output_path>/Work/<job_id>/)에도 쓰므로 영숫자·밑줄만
    return f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


_last_ns = 0
_ns_lock = threading.Lock()


def order_ns() -> int:
    """정렬용 생성 시각 — 같은 초에 만든 Job · 승인도 순서가 정해지게 프로세스 안에서 단조 증가시킨다."""
    global _last_ns
    with _ns_lock:
        _last_ns = max(time.time_ns(), _last_ns + 1)
        return _last_ns


def ledger_key(plan_id: str, attempt: int) -> str:
    """유료 제출 멱등 키 (plan_id, attempt) (§6)."""
    return f"{plan_id}#{attempt}"


class Store:
    def __init__(self, root: str | os.PathLike | None = None):
        self.root = pathlib.Path(root) if root else default_state_dir()
        self._lock = threading.RLock()

    # ---- 파일 ----
    def _dir(self, name: str) -> pathlib.Path:
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _read(path: pathlib.Path) -> dict | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    @staticmethod
    def _write(path: pathlib.Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    # ---- 계획 (만든 뒤 바꾸지 않는다) ----
    def save_plan(self, plan: dict) -> None:
        with self._lock:
            self._write(self._dir("plans") / f"{plan['plan_id']}.json", plan)

    def load_plan(self, plan_id: str) -> dict | None:
        return self._read(self.root / "plans" / f"{plan_id}.json")

    # ---- Job ----
    def create_job(self, job: dict) -> dict:
        with self._lock:
            job.setdefault("status", QUEUED)
            job.setdefault("events", []).append({"at": now_iso(), "from": None, "to": job["status"], "note": "created"})
            job["created_at"] = job["updated_at"] = now_iso()
            job["created_ns"] = order_ns()
            self._write(self._dir("jobs") / f"{job['job_id']}.json", job)
            return job

    def load_job(self, job_id: str) -> dict | None:
        return self._read(self.root / "jobs" / f"{job_id}.json")

    def patch_job(self, job_id: str, **fields) -> dict:
        """상태 이외의 필드를 덮어쓴다. 상태는 transition 으로만 바꾼다."""
        if "status" in fields or "events" in fields:
            raise ValueError("status/events change only through transition()")
        with self._lock:
            job = self.load_job(job_id)
            if job is None:
                raise KeyError(job_id)
            job.update(fields)
            job["updated_at"] = now_iso()
            self._write(self.root / "jobs" / f"{job_id}.json", job)
            return job

    def update_job(self, job_id: str, mutate) -> dict:
        """락 안에서 읽기 → mutate(job) → 쓰기 (목록에 항목을 더할 때 — 다른 스레드의 상태 변경을 덮지 않는다)."""
        with self._lock:
            job = self.load_job(job_id)
            if job is None:
                raise KeyError(job_id)
            status, events = job["status"], list(job["events"])
            mutate(job)
            if job["status"] != status or job["events"] != events:
                raise ValueError("status/events change only through transition()")
            job["updated_at"] = now_iso()
            self._write(self.root / "jobs" / f"{job_id}.json", job)
            return job

    def transition(self, job_id: str, to: str, note: str | None = None, **fields) -> dict:
        with self._lock:
            job = self.load_job(job_id)
            if job is None:
                raise KeyError(job_id)
            current = job["status"]
            if to not in TRANSITIONS.get(current, frozenset()):
                raise InvalidTransition(job_id, current, to)
            job.update(fields)
            job["status"] = to
            job["events"].append({"at": now_iso(), "from": current, "to": to, "note": note})
            job["updated_at"] = now_iso()
            self._write(self.root / "jobs" / f"{job_id}.json", job)
            return job

    def list_jobs(self, plan_id: str | None = None, limit: int = 20) -> list[dict]:
        folder = self.root / "jobs"
        if not folder.exists():
            return []
        jobs = [j for j in (self._read(p) for p in folder.glob("*.json")) if j]
        if plan_id:
            jobs = [j for j in jobs if j.get("plan_id") == plan_id]
        jobs.sort(key=lambda j: (j.get("created_ns", 0), j["job_id"]), reverse=True)
        return jobs[:limit] if limit else jobs

    # ---- 승인 ----
    def save_approval(self, approval: dict) -> None:
        with self._lock:
            approval.setdefault("created_ns", order_ns())
            self._write(self._dir("approvals") / f"{approval['approval_id']}.json", approval)

    def load_approval(self, approval_id: str) -> dict | None:
        return self._read(self.root / "approvals" / f"{approval_id}.json")

    def approvals_for(self, plan_id: str, provider: str | None = None) -> list[dict]:
        folder = self.root / "approvals"
        if not folder.exists():
            return []
        items = [a for a in (self._read(p) for p in folder.glob("*.json")) if a and a["plan_id"] == plan_id]
        if provider:
            items = [a for a in items if a["provider"] == provider]
        return sorted(items, key=lambda a: (a.get("created_ns", 0), a["approval_id"]))

    # ---- 비용 장부 (추가만 한다) ----
    # kind: reserve(제출 직전, 추정액) · submitted(외부 핸들) · charge(실제 금액 확정) · release(과금 없음이 확인됨)
    def ledger_append(self, entry: dict) -> None:
        with self._lock:
            entry = {"at": now_iso(), **entry}
            path = self.root / "ledger.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def ledger_entries(self) -> list[dict]:
        path = self.root / "ledger.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def ledger_by_key(self) -> dict[str, dict]:
        keys: dict[str, dict] = {}
        for e in self.ledger_entries():
            rec = keys.setdefault(e["key"], {"key": e["key"], "reserve": None, "handle": None, "charge": None, "released": False})
            if e["kind"] == "reserve":
                rec["reserve"] = e
            elif e["kind"] == "submitted":
                rec["handle"] = e.get("handle")
            elif e["kind"] == "charge":
                rec["charge"] = e
            elif e["kind"] == "release":
                rec["released"] = True
        return keys

    def ledger_totals(self) -> dict:
        """지출 = 확정 금액 합, 예약 = 확정·해제되지 않은 추정액 합(미확정 금액은 예약으로 남는다 — §6)."""
        spent = reserved = 0.0
        for rec in self.ledger_by_key().values():
            if rec["charge"] is not None:
                spent += float(rec["charge"].get("usd") or 0.0)
            elif not rec["released"] and rec["reserve"] is not None:
                reserved += float(rec["reserve"].get("usd") or 0.0)
        return {"spent_usd": round(spent, 4), "reserved_usd": round(reserved, 4)}

    def paid_attempts(self, plan_id: str) -> int:
        return sum(1 for e in self.ledger_entries() if e["kind"] == "reserve" and e.get("plan_id") == plan_id)
