"""refine — raw 를 검사 · 정리해 assets/final/ 과 manifest.json 으로 (설계 §2-2 · §7 'refine').

1a(procedural): 크기 일치 · 알파(HUD 위에 얹는 종류는 투명 픽셀이 있어야 한다) · 9-slice margin(spec 값, 없으면 모양에서 계산) ·
압축(spec → 종류별 기본 → 전체 기본). 배경 제거 · 여백 자르기 · OCR(구운 글자)은 생성 이미지가 들어오는 1b — procedural 은 글자를
그리지 않으므로 ocr 은 '해당 없음' 으로 적는다(게이트에서도 건너뛴 이유를 남긴다).
"""
from __future__ import annotations

import hashlib
import json
import shutil

from core import config
from core import png
from core import schema
from gen import procedural
from stages import StageError

NEEDS_ALPHA = {"frame", "panel_bg", "ornament", "icon"}
OCR_NOT_APPLICABLE = "n/a — procedural 에셋은 글자를 그리지 않는다(Phase 1a). OCR 은 생성 이미지가 들어오는 1b 부터"


def run(run, opts) -> str:
    spec = run.read_json("spec.json")
    backends = {}
    gp = run.path("gen.jsonl")
    if gp.is_file():
        for line in gp.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            if rec.get("ok"):
                backends[rec["asset_id"]] = rec["backend"]
    previous = {}
    if run.path("manifest.json").is_file():
        previous = {a["asset_id"]: a for a in run.read_json("manifest.json")["assets"]}
    only = set(getattr(opts, "only_assets", None) or [])
    entries = []
    for asset in spec.get("assets", []):
        aid = asset["asset_id"]
        if only and aid not in only and aid in previous:
            entries.append(previous[aid])
            continue
        raw = run.path("assets", "raw", f"{aid}.png")
        if not raw.is_file():
            raise StageError("RAW_MISSING", f"{raw} was not generated", asset=aid)
        w, h, rgba = png.read_rgba(raw)
        if [w, h] != [int(v) for v in asset["size"]]:
            raise StageError("SIZE_MISMATCH", f"'{aid}' is {w}x{h}, spec says {asset['size']}", asset=aid)
        has_alpha = any(rgba[i] < 255 for i in range(3, len(rgba), 4))
        if asset.get("kind") in NEEDS_ALPHA and not has_alpha:
            raise StageError("NO_ALPHA", f"'{aid}' ({asset['kind']}) is fully opaque — HUD assets need a transparent background", asset=aid)
        margin = None
        if asset.get("nine_slice"):
            margin = asset.get("margin") or procedural.nine_slice_margin(asset)
            if margin is None:
                raise StageError("NO_MARGIN", f"'{aid}' is nine_slice but has no margin and none can be derived", asset=aid)
        final = run.path("assets", "final", f"{aid}.png")
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(raw, final)
        entries.append({
            "asset_id": aid,
            "kind": asset["kind"],
            "file": f"assets/final/{aid}.png",
            "sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
            "size": [w, h],
            "alpha": has_alpha,
            "nine_slice_margin": margin,
            "ocr_text": None,
            "ocr": OCR_NOT_APPLICABLE if backends.get(aid, asset["provenance"]) == "procedural" else "pending",
            "provenance": asset["provenance"],
            "backend": backends.get(aid, asset["provenance"]),
            "procedural": asset.get("procedural") or {},
            "prompt": asset.get("prompt"),
            "anchor": bool(asset.get("anchor", False)),
            "ue_path": None,
            "compression": config.compression_for(asset, run.cfg),
        })
    manifest = {"schema_version": 1, "run_id": run.run_id, "assets": entries}
    schema.require("manifest", manifest)
    run.write_json("manifest.json", manifest)
    comp = ", ".join(f"{e['asset_id']}={e['compression']}" for e in entries)
    return f"{len(entries)} asset(s) in manifest ({comp})" if entries else "no assets"
