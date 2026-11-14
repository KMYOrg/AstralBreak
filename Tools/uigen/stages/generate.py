"""generate — spec.assets[] 를 백엔드로 만든다 (설계 §2-2 · §7). 1a 는 procedural 만.

출력: assets/raw/<asset_id>.png · gen.jsonl(에셋마다 한 줄 — backend · ok · duration_s · sha256 · attempt).
재시도에서 replace_asset 로 돌아오면 opts.only 의 에셋만 다시 만든다.
"""
from __future__ import annotations

import hashlib
import time

from core import config
from core import png
from gen import procedural
from gen.router import RouteError, choose_backend
from stages import StageError

BACKENDS = {"procedural": procedural.render}


def run(run, opts) -> str:
    spec = run.read_json("spec.json")
    routing = config.load_routing()
    allowed = list(run.cfg["backends"]["allowed"])
    only = set(getattr(opts, "only_assets", None) or [])
    attempt = int(getattr(opts, "attempt", 0) or 0)
    made = []
    for asset in spec.get("assets", []):
        aid = asset["asset_id"]
        if only and aid not in only:
            continue
        t0 = time.monotonic()
        try:
            backend = choose_backend(asset, routing, allowed)
            render = BACKENDS.get(backend)
            if render is None:
                raise StageError("BACKEND_MISSING", f"backend '{backend}' is allowed but not implemented in Phase 1a", asset=aid)
            w, h, rgba = render(asset)
            path = png.write_rgba(run.path("assets", "raw", f"{aid}.png"), w, h, rgba)
        except (RouteError, procedural.ProceduralError) as exc:
            run.append_jsonl("gen.jsonl", {"asset_id": aid, "kind": asset.get("kind"), "ok": False, "error": str(exc), "attempt": attempt,
                                           "duration_s": round(time.monotonic() - t0, 3)})
            raise StageError(getattr(exc, "code", "PROCEDURAL"), str(exc), asset=aid) from exc
        dur = round(time.monotonic() - t0, 3)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        run.append_jsonl("gen.jsonl", {"asset_id": aid, "kind": asset.get("kind"), "backend": backend, "ok": True, "duration_s": dur,
                                       "sha256": sha, "size": [w, h], "attempt": attempt})
        made.append(f"{aid}({backend} {w}x{h})")
    return f"{len(made)} asset(s): " + ", ".join(made) if made else "no assets"
