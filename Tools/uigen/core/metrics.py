"""지표 JSONL (설계 §4-5) — metrics/uigen.jsonl 한 줄 = 에셋 하나 또는 run 하나. Phase 1 부터 쓰고 집계는 Phase 2.

줄 필드: record(run | asset) · ts · run_id · asset_id · kind · backend · ok · duration_s · retries · verify · style_sim_anchor
(run 줄은 + status · failed_gates · phase · fault)
(+ codex: codex_version, comfy: workflow_sha256 · model_sha256 · lora_sha256[] · seed — 해당 백엔드가 생길 때).
style_sim_anchor 등 Phase 2 보정 전 지표는 값이 없으면 null 로 남긴다(기록만 — 게이트 아님).
"""
from __future__ import annotations

import datetime as _dt
import json
import pathlib


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def append(path: str | pathlib.Path, record: dict) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"ts": now_iso(), **record}, ensure_ascii=False, sort_keys=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(line + "\n")


def read(path: str | pathlib.Path) -> list[dict]:
    path = pathlib.Path(path)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_record(run_id: str, status: str, attempt: int, duration_s: float, verify: str | None = None, **extra) -> dict:
    """run 한 줄 — status = run 결과(pass · fail · incomplete · error), verify = 마지막 verify 의 게이트 결과(pass · fail, 돌지 않았으면 null),
    retries = verify 시도 수 - 1."""
    return {"record": "run", "run_id": run_id, "status": status, "ok": status == "pass", "verify": verify,
            "retries": max(0, attempt - 1) if attempt else 0, "duration_s": round(duration_s, 3), **extra}


def asset_record(run_id: str, asset: dict, verify: str | None, retries: int = 0) -> dict:
    """manifest 의 에셋 하나 → 줄. duration_s 는 gen.jsonl 에서, retries 는 그 에셋을 다시 만든 횟수(gen.jsonl 줄 수 - 1)."""
    return {"record": "asset", "run_id": run_id, "asset_id": asset["asset_id"], "kind": asset.get("kind"), "backend": asset.get("backend"),
            "ok": bool(asset.get("ok", True)), "duration_s": asset.get("duration_s"), "retries": retries, "verify": verify,
            "style_sim_anchor": None}
