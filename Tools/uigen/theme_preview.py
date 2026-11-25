"""공용 테마 미리보기(Phase 3-2) — 버튼 기본 그림에 테마의 식(gen/theme)을 적용한 상태 일곱을 게임 바탕 · 밝은 바탕 위에 글자와 함께 그린다(codex 0 · 에디터 0).
테마 값은 눈으로 고르는 값이라 **사람이 이 그림을 보고 승인한 뒤** 칸을 돌린다.

    Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/theme_preview.py --theme blade --out Tools/uigen/work/_theme/<이름>.png \\
        --art <기본 그림 png> --crop x,y,w,h --scale 1.1483 --label 준비 --pt 24 [--art … --crop … --label … --pt …]

--crop(그림 px)은 시안에서 그 버튼 자리, --scale 은 그림 px → 1920 폭 px(시안 폭 1672 이면 1920 / 1672). 글자는 Pretendard TTF(work/_fonts) — 엔진 글꼴과 같은 파일.
실제 엔진 렌더는 run 의 compare.png 버튼 칸에서 본다(여기는 같은 식을 이미지로만 그린 것).
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np

UIGEN = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(UIGEN))

from core import button, config  # noqa: E402
from gen import text_ref, theme  # noqa: E402

FONT_DIR = config.UIGEN_DIR / "work" / "_fonts" / "pretendard"
NAMES = {"normal_base": "기본", "normal_hovered": "올림 · 초점", "normal_pressed": "누름", "selected_base": "선택", "selected_hovered": "선택 + 올림",
         "selected_pressed": "선택 + 누름", "disabled": "비활성"}
PAD, HEAD, NAME_W = 26, 46, 170


def scene(w: int, h: int, kind: str) -> np.ndarray:
    """바탕 — game: 어두운 하늘 · 흙 흉내(잡티 조금), light: 밝은 하늘. 해마다 같은 그림(씨앗 고정)."""
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    x = np.linspace(0, 1, w, dtype=np.float32)[None, :, None]
    top, bottom = ((np.array([58, 70, 92]), np.array([46, 40, 34])) if kind == "game" else (np.array([206, 218, 230]), np.array([226, 214, 190])))
    img = top * (1 - y) + bottom * y + (x - 0.5) * 24
    rng = np.random.default_rng(7)
    import cv2
    n = cv2.resize(rng.normal(0, 1, (max(2, h // 24), max(2, w // 24))).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)[..., None]
    return np.clip(img + n * (9 if kind == "game" else 5), 0, 255).astype(np.float32)


def put_label(img, box, text: str, pt: int, weight: str, t: dict, offset, gray: bool):
    from PIL import Image, ImageDraw, ImageFont
    pic = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
    font = ImageFont.truetype(str(FONT_DIR / text_ref.FONT_FILES[weight]), pt * text_ref.PX_PER_PT)
    layer = Image.new("RGBA", pic.size, (0, 0, 0, 0))
    x, y, w, h = box
    o = t["text"]["outline"]
    ImageDraw.Draw(layer).text((x + w / 2 + offset[0], y + h / 2 + offset[1]), text, font=font, anchor="mm", fill=t["text"]["color"],
                               stroke_width=int(o["size"]), stroke_fill=o["color"])
    if gray:                                                   # 비활성 — Slate 가 글자를 무채색 · 흐리게(엔진 값은 run 에서 잰다)
        a = np.asarray(layer).astype(np.float32)
        a[..., :3] = (a[..., :3] @ theme.LUM)[..., None]
        a[..., 3] *= 0.45
        layer = Image.fromarray(a.astype(np.uint8), "RGBA")
    pic.alpha_composite(layer)
    return np.asarray(pic.convert("RGB")).astype(np.float32)


def sheet(arts: list[dict], t: dict) -> np.ndarray:
    """arts = [{rgba(HxWx4 uint8 — 1920 폭 px), label, pt, weight}] → 상태(줄) × 그림 · 바탕(칸)."""
    from PIL import Image, ImageDraw, ImageFont
    cols = [(a, kind) for a in arts for kind in ("game", "light")]
    rh = max(a["rgba"].shape[0] for a in arts) + 2 * PAD
    widths = [a["rgba"].shape[1] + 2 * PAD for a, _ in cols]
    W, H = NAME_W + sum(widths), HEAD + rh * len(button.BRUSHES)
    out = np.full((H, W, 3), 24, np.float32)
    x = NAME_W
    for (a, kind), cw in zip(cols, widths):
        out[HEAD:, x:x + cw] = scene(cw, H - HEAD, kind)
        for i, b in enumerate(button.BRUSHES):
            s = theme.state(a["rgba"], b, t).astype(np.float32)
            h, w = s.shape[:2]
            x0, y0 = x + PAD, HEAD + rh * i + (rh - h) // 2
            al = s[..., 3:] / 255.0
            out[y0:y0 + h, x0:x0 + w] = s[..., :3] * al + out[y0:y0 + h, x0:x0 + w] * (1 - al)
            out = put_label(out, (x0, y0, w, h), a["label"], a["pt"], a["weight"], t, t["text"]["pressed_offset"] if b.endswith("pressed") else (0, 0), b == "disabled")
        x += cw
    pic = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(pic)
    f = ImageFont.truetype(str(FONT_DIR / text_ref.FONT_FILES["medium"]), 20)
    for i, b in enumerate(button.BRUSHES):
        d.text((16, HEAD + rh * i + rh / 2), NAMES[b], font=f, fill=(230, 230, 230), anchor="lm")
    x = NAME_W
    for (a, kind), cw in zip(cols, widths):
        d.text((x + cw / 2, HEAD / 2), "게임 바탕" if kind == "game" else "밝은 바탕", font=f, fill=(230, 230, 230), anchor="mm")
        x += cw
    return np.asarray(pic)


def load_art(path, crop: str | None, scale: float) -> np.ndarray:
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGBA")
        if crop:
            x, y, w, h = (int(v) for v in crop.split(","))
            im = im.crop((x, y, x + w, y + h))
        arr = np.asarray(im).astype(np.float32)
    h, w = int(round(arr.shape[0] * scale)), int(round(arr.shape[1] * scale))
    a = arr[..., 3] / 255.0
    ch = [np.asarray(Image.fromarray(c.astype(np.float32), "F").resize((w, h), Image.Resampling.LANCZOS)) for c in (*(arr[..., i] * a for i in range(3)), a)]
    al = np.clip(ch[3], 0, 1)
    rgb = np.dstack([np.where(al > 1e-4, c / np.maximum(al, 1e-4), 0) for c in ch[:3]])
    return np.clip(np.round(np.dstack([rgb, al * 255])), 0, 255).astype(np.uint8)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--theme", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--art", action="append", default=[], required=True)
    ap.add_argument("--crop", action="append", default=[])
    ap.add_argument("--label", action="append", default=[])
    ap.add_argument("--pt", action="append", type=int, default=[])
    ap.add_argument("--weight", action="append", default=[])
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--force", action="store_true")
    o = ap.parse_args(argv)
    n = len(o.art)
    out = pathlib.Path(o.out)
    if any(v and len(v) != n for v in (o.crop, o.label, o.pt, o.weight)):
        print("theme_preview: give --crop / --label / --pt / --weight once per --art (or not at all)", file=sys.stderr)
        return 1
    if out.exists() and not o.force:
        print(f"theme_preview: {out} already exists — pass --force to replace it", file=sys.stderr)
        return 1
    try:
        t = theme.load(o.theme)
        arts = [{"rgba": load_art(o.art[i], o.crop[i] if o.crop else None, o.scale), "label": o.label[i] if o.label else "글자",
                 "pt": o.pt[i] if o.pt else 20, "weight": o.weight[i] if o.weight else "semibold"} for i in range(n)]
    except (OSError, ValueError, KeyError) as exc:
        print(f"theme_preview: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    from PIL import Image
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(sheet(arts, t)).save(out)
    print(f"{out.as_posix()} — theme {t['id']} {t['sha256'][:8]}, {n} picture(s) x {len(button.BRUSHES)} states")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
