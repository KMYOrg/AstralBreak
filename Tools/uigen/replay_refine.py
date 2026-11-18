"""오프라인 refine 재실행 (1b 후속 I) — 오리기 규칙을 고친 뒤 여러 배치(지난 run)로 한꺼번에 확인한다. 에디터 · LLM · codex 없음.

run 폴더에서 refine 직전 spec(`specs/000.json` — 넘침 장식 없음. 최종 spec 은 글자 맞춤으로 글자 상자가 바뀌어 다른 결과가 난다)과 normalize · analyze
산출물(reference*.png · gen.jsonl · assets/raw)만 사본으로 옮겨 `refine.run` 만 다시 돌리고, spec bbox_intent 상자로 `backdrop.compose`(회색 #808080)
해서 잰다.

    Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/replay_refine.py <out_dir> <run_dir> [<run_dir> ...]
    (+ --final: 최종 spec.json · refine.json 으로 — 글자 맞춤 뒤 글자 상자 조건 · --layer: 1b 후속 J-a 정적 판 단계를 먼저)

출력 <out_dir>/<run_id>/ (out_dir 는 work 밖 스크래치 권장 — run 하나에 수십 MB):
  replay.png(컨셉 회색 | 합성 회색 | 차이 — 빨강 = 구멍 · 파랑 = 이중) · per_texture.png(오리는 텍스처마다 혼자) · owners.png(픽셀마다 가장 큰 알파를 준
  텍스처 색) · assets/final · spec.json · refine.json, <out_dir>/summary.json.
지표(한 줄 JSON — ⓐ 는 컨셉 알파가 정답, ⓑ 는 언믹싱 추정): 회색 ΔE00 평균 · p95 · 알파 MAE(글자 상자 + 6 px 밖) · 컨셉에 없는 알파 절벽 ·
구멍(컨셉 알파 − 덮임 > 0.25, 20 px 넘는 덩어리 수 · px) · 이중(덮임 − 컨셉 알파 > 0.15) · 확대 절취선(`zoom_seams` — 나눈 텍스처를 3 배로 따로
늘려 겹친 그림이 컨셉 한 장을 늘린 그림보다 20 넘게 어두운 픽셀 수 · 평균 · 최대).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
import types

UIGEN = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(UIGEN))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from core import color, config  # noqa: E402
from core.run import Run  # noqa: E402
from gen import backdrop  # noqa: E402
from gen import diagnose  # noqa: E402
from stages import refine  # noqa: E402

COPY = ["gen.jsonl", "normalize.json", "inputs.json", "brief.json", "analyze/derived.json", "layer.json"]   # layer.json — J-a 판 run(specs/000 에 이미 판)
GRAY = np.asarray(backdrop.GRAY, float)
HOLE = 0.25
DOUBLE = 0.15
MIN_BLOB = 20
PALETTE = [(230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200), (245, 130, 48), (145, 30, 180), (70, 240, 240), (240, 50, 230),
           (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255), (170, 110, 40), (255, 250, 200), (128, 0, 0), (170, 255, 195)]


def copy_run(src: pathlib.Path, out: pathlib.Path, final_spec: bool) -> pathlib.Path:
    dst = out / src.name
    if dst.exists() and any(dst.iterdir()):
        raise SystemExit(f"replay_refine: {dst} already has files — use a new out_dir")
    dst.mkdir(parents=True, exist_ok=True)
    for rel in COPY:
        p = src / rel
        if p.is_file():
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst / rel)
    if final_spec:                                         # 넘침 장식은 refine 기록으로 걷는다
        shutil.copy2(src / "spec.json", dst / "spec.json")
        shutil.copy2(src / "refine.json", dst / "refine.json")
    else:
        shutil.copy2(src / "specs" / "000.json", dst / "spec.json")
    for p in src.glob("reference*.png"):
        shutil.copy2(p, dst / p.name)
    for p in src.glob("layer/*.png"):                      # J-a 판 마스크
        (dst / "layer").mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst / "layer" / p.name)
    (dst / "assets" / "raw").mkdir(parents=True, exist_ok=True)
    for p in (src / "assets" / "raw").glob("*.png"):
        shutil.copy2(p, dst / "assets" / "raw" / p.name)
    return dst


def boxes_from_spec(spec: dict) -> list[dict]:
    cw, ch = (float(v) for v in spec.get("canvas", [1920, 1080]))
    out = []
    for w in spec.get("widgets", []):
        bb = w.get("bbox_intent") or [0, 0, cw, ch]           # 루트 캔버스 등 상자 없는 위젯 = 화면 전체
        out.append({"id": w["id"], "x": float(bb[0]), "y": float(bb[1]), "w": float(bb[2]), "h": float(bb[3]), "visible": True})
    return out


def blobs(m: np.ndarray) -> tuple[int, int]:
    import cv2
    n, _, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    big = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= MIN_BLOB]
    return len(big), int(sum(st[i, cv2.CC_STAT_AREA] for i in big))


ZOOM_PICTURE = False        # --zoom-picture: <run>/zoom.png(컨셉 한 장 확대 | 나눈 텍스처 확대 — 크다)
ZOOM = diagnose.ZOOM        # 확대 모사는 파이프라인 진단(gen/diagnose.zoom_seams — 1b 후속 J-b 에서 옮김)과 같은 함수
zoom_seams = diagnose.zoom_seams


def replay(src: pathlib.Path, out: pathlib.Path, final_spec: bool = False, with_layer: bool = False) -> dict:
    dst = copy_run(src, out, final_spec)
    run = Run(src.name, out, config.load_pipeline(), out / "metrics.jsonl")
    layer_detail = None
    if with_layer:                                       # 1b 후속 J-a — 기능 단위 레이어(정적 판)를 먼저
        from stages import layer
        layer_detail = layer.run(run, types.SimpleNamespace())
    detail = refine.run(run, types.SimpleNamespace(attempt=99, only_assets=None))
    spec = json.loads((dst / "spec.json").read_text(encoding="utf-8"))
    canvas = spec.get("canvas") or [1920, 1080]
    W, H = int(canvas[0]), int(canvas[1])
    boxes = boxes_from_spec(spec)
    manifest = json.loads((dst / "manifest.json").read_text(encoding="utf-8"))
    textures = {a["asset_id"]: backdrop._load(dst / a["file"]) for a in manifest["assets"] if (dst / a["file"]).is_file()}
    tmask = backdrop.text_mask(spec, boxes, canvas)
    gray, cov, info = backdrop.compose(spec, boxes, textures, canvas, backdrop.GRAY)
    rc = backdrop._load(dst / "reference_color.png")[..., :3]
    with Image.open(dst / "reference_alpha.png") as im:
        ra = np.asarray(im.convert("L"), float) / 255.0
    cg = rc * ra[..., None] + GRAY[None, None] * (1 - ra[..., None])
    m = ~tmask & ((cov > backdrop.VISIBLE) | (ra > backdrop.VISIBLE))
    de = color.delta_e00(color.srgb_to_lab(gray[m]), color.srgb_to_lab(cg[m]))
    cl = backdrop._cliffs(cov) & (backdrop._ref_grad(ra) < backdrop.CLIFF_REF) & ~tmask
    rec = {"run": src.name, "kind": json.loads((dst / "normalize.json").read_text(encoding="utf-8")).get("background", {}).get("kind"),
           "gray_de00_mean": round(float(de.mean()), 3), "gray_de00_p95": round(float(np.percentile(de, 95)), 3),
           "alpha_mae": round(float(np.abs(cov[m] - ra[m]).mean()), 4), "cliffs_compose_only": int(cl.sum()),
           "holes": blobs((ra - cov > HOLE) & ~tmask), "doubles": blobs((cov - ra > DOUBLE) & ~tmask), "missing": info["missing"]}
    # 그림 1 — 컨셉 회색 | 합성 회색 | 차이
    diff = np.full((H, W, 3), 255.0)
    d = cov - ra
    diff[..., 1] -= np.clip(np.abs(d) * 4, 0, 1) * 255
    diff[..., 0] -= np.clip(d * 4, 0, 1) * 255           # 이중 → 파랑
    diff[..., 2] -= np.clip(-d * 4, 0, 1) * 255          # 구멍 → 빨강
    diff[tmask] = diff[tmask] * 0.85
    sep = np.full((H, 8, 3), 255.0)
    side = np.concatenate([np.clip(cg, 0, 255), sep, gray, sep, np.clip(diff, 0, 255)], axis=1).round().astype(np.uint8)
    Image.fromarray(side).resize((side.shape[1] // 2, H // 2), Image.Resampling.LANCZOS).save(dst / "replay.png")
    # 그림 2 · 3 — 오리는 텍스처마다 혼자 · 소유 지도
    logs = json.loads((dst / "refine.json").read_text(encoding="utf-8"))["passes"][-1]["assets"]
    covs = {}
    for aid in [lg["asset_id"] for lg in logs if lg.get("source_mode") == "extract"]:
        g1, c1, _ = backdrop.compose(spec, boxes, {aid: textures[aid]}, canvas, backdrop.GRAY)
        if c1.max() > 0.02:
            covs[aid] = (g1, c1)
    if covs:
        ys, xs = np.nonzero(np.max([c for _, c in covs.values()], axis=0) > 0.02)
        y0, y1, x0, x1 = max(0, ys.min() - 8), min(H, ys.max() + 9), max(0, xs.min() - 8), min(W, xs.max() + 9)
        tiles = [g1[y0:y1, x0:x1] for g1, _ in covs.values()]
        th, tw = tiles[0].shape[:2]
        cols, rows = 2, (len(tiles) + 1) // 2
        sheet = np.full((rows * (th + 6), cols * (tw + 6), 3), 255.0)
        for i, t in enumerate(tiles):
            r, c = divmod(i, cols)
            sheet[r * (th + 6):r * (th + 6) + th, c * (tw + 6):c * (tw + 6) + tw] = t
        Image.fromarray(sheet.round().astype(np.uint8)).resize((sheet.shape[1] // 2, sheet.shape[0] // 2), Image.Resampling.LANCZOS).save(dst / "per_texture.png")
        stack = np.stack([c for _, c in covs.values()])
        top, amax = stack.argmax(axis=0), stack.max(axis=0)
        own = np.ones((H, W, 3)) * GRAY
        for i in range(len(covs)):
            sel = (top == i) & (amax > 0.02)
            own[sel] = np.asarray(PALETTE[i % len(PALETTE)], float) * amax[sel, None] + GRAY * (1 - amax[sel, None])
        Image.fromarray(own[y0:y1, x0:x1].round().astype(np.uint8)).save(dst / "owners.png")
        rec["textures"] = list(covs)                         # per_texture.png 순서(왼쪽 → 오른쪽, 위 → 아래) = owners.png 색 순서(PALETTE)
        rec["zoom_seams"] = zoom_seams(spec, boxes, textures, rc, ra, [x0, y0, x1, y1], tmask, picture=dst / "zoom.png" if ZOOM_PICTURE else None)
    rec["refine"] = detail[:200]
    if layer_detail is not None:
        rec["layer"] = layer_detail[:300]
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="offline refine replay on copies of past runs — grey-backdrop metrics and pictures")
    ap.add_argument("out_dir")
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--final", action="store_true", help="use the final spec.json · refine.json (text boxes after text_fit)")
    ap.add_argument("--layer", action="store_true", help="run the J-a layer stage (static plates) before refine")
    ap.add_argument("--zoom-picture", action="store_true", help=f"also save <run>/zoom.png ({ZOOM}x magnified: one concept | split textures)")
    opts = ap.parse_args(argv)
    global ZOOM_PICTURE
    ZOOM_PICTURE = opts.zoom_picture
    out = pathlib.Path(opts.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    recs = []
    for r in opts.runs:
        rec = replay(pathlib.Path(r), out, opts.final, opts.layer)
        recs.append(rec)
        print(json.dumps({k: v for k, v in rec.items() if k not in ("textures", "refine")}, ensure_ascii=False), flush=True)
    (out / "summary.json").write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
