"""컨셉아트 1장 만들기 (Phase 1b 준비 — 설계 §11 '1b 착수 때 정한 것'). codex built-in image_gen 으로 화면 컨셉을 만들어 fixture 로 둔다.

**기본 = L-2(L-2 기본 전환, 11-23):** 글자 없는 원본 아트 concept.png(진짜 알파 · 글자 칸은 비움 — 사람이 승인하는 픽셀 정답)를 먼저 만들고, 그 아트에 글자만
얹은 참고판 concept_text_ref.png 를 만든다. 글자를 그리는 컨셉은 --with-text 로 따로 고른다.

    Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/make_concept.py --out-dir Tools/uigen/fixtures/<화면>
    (+ --prompt-file <md> · --force(있는 concept.png 를 덮음) · --max-calls N(기본 — 원본 아트 + 참고판 3, 그 밖 1)
     · --only art = 원본 아트까지만(후보를 여러 장 보고 고를 때 — inputs 없어도 됨, 상한 2) · --only text_ref = 고른 concept.png 에 참고판만(상한 1)
     · --only text_ref --draw <layout.yaml> = codex 없이 참고판을 엔진과 같은 글꼴 파일(Pretendard TTF)로 그림(글자 값은 inputs, 자리 · 크기 · 굵기 · 색은 yaml)
     · --inputs <yaml>(참고판 글자 — 기본 <out-dir>/inputs.yaml)
     · --style-ref <png>(여러 번 — 느낌 · 색 · 재질만 참고로 첨부, 배치 · 요소는 프롬프트대로. 우리가 만든 그림(옆 concept.json 의 generator 가 codex)이거나
       --style-ref-from-user 로 사용자가 준 그림이라고 밝힌 것만 · work/_probe 의 상용 게임 화면은 거절)
     · --cut-from <sheet.png> --keep x,y,w,h(여러 번, 1920 폭 기준 px) = codex 없이 승인한 시안에서 그 상자들만 픽셀 그대로 오려 원본 아트로
     · --with-text = 글자까지 그린 컨셉 1장(L-1 길 — 외부 컨셉 흉내 · 시험용). 아래 --flat · --transparent 의 새 그림은 이것과 함께만
     · --flat(1b 후속 H — UI 만 · 단색 검정 배경 · 장면 없음 · 가장 큰 크기: 컨셉 픽셀을 오려 쓰기 좋은 컨셉)
     · --edit <concept.png>(1b 후속 H — 그 컨셉을 프롬프트대로 codex 편집해 새 컨셉으로 — '컨셉을 ~식으로 바꿔 줘')
     · --transparent(1b 후속 H3 — UI 만 · 진짜 알파 투명 배경: normalize ⓐ 가 알파를 그대로 쓴다, --flat 과 함께 못 씀)
     · --text-free(1b 후속 H2 — concept.png 에서 글자만 지운 concept_notext.png, 원본이 투명이면 알파를 지키라고 덧붙임)
     · --text-free-first(1b 후속 L-2 — 지금 기본과 같은 길의 옛 이름))
원본 아트에 글자가 보이면(gen/concept_route — 모호 포함) 1 회 다시 → 그래도면 text_free_first.status text_drawn 으로 남겨 normalize 가 L-1 로 물러난다.

출력: <out-dir>/concept.png · concept.json(출처 — codex 버전 · thread_id · 프롬프트 sha256 · 크기 · 시각), 호출 기록 · 이벤트 원문은
work/_concept/<시각>/ (git 무시). codex 호출은 한 번에 하나(work/.codex.lock) · ChatGPT 로그인 확인 · stdin 닫음 · API 키 환경 변수 제거(gen/codex.py).
종료 코드: 0 = 생성 · 1 = 실패 · 3 = 한도(나중에 다시).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from core import config  # noqa: E402
from gen import codex  # noqa: E402

EXIT_OK, EXIT_FAIL, EXIT_QUOTA = 0, 1, 3
# 1b 후속 H — 매핑용 컨셉(설계 H '컨셉 생성 · 편집'): UI 만 · 단색 검정 배경(빛이 있어도 배경색 언믹싱이 쉬운 검정) · 장면 없음 · 가장 큰 크기.
# normalize 가 테두리 한 색으로 ⓑ flat 을 판정하고 알파를 언믹싱한다(gen/cutout). codex built-in image_gen 의 가장 큰 16:9 = 1672 × 941 [실측 1b-2]
FLAT_RULES = (
    "\n\nOutput rules for a UI-only concept (the pipeline cuts every element out of this picture, so the background must be empty):\n"
    "- Draw ONLY the UI elements listed above, on a solid pure black background (#000000) that fills the whole canvas edge to edge.\n"
    "- No game scene, no characters, no environment, no sky, no vignette, no gradient, texture, noise or pattern in the background.\n"
    "- Soft glows and translucent parts fade directly into the black. Keep elements apart from the canvas edges.\n"
    "- Use the largest 16:9 landscape image size you can produce, with crisp thin lines and ornaments.\n"
)
EDIT_PURPOSE = "keep the UI layout, sizes and positions of every element; change only what the request asks"
# 1b 후속 H — 합성 스크린샷(ⓒ)을 UI 만 컨셉으로 바꾸기(--edit --flat): 오리기는 장면 위 반투명 UI 를 장면과 가를 수 없고(잔상) 원본 해상도보다
# 선명해질 수 없다(흐림) [실측 H 끝 run — 조작 안내 807 × 353 → 2.38 배]. codex 가 화면 전체를 한 번 다시 그려 장면을 지우고 선명하게 — 그 뒤는 결정적 매핑.
FLAT_EDIT_RULES = (
    "\n\nOutput rules (the pipeline cuts every UI element out of the result, so the background must be empty):\n"
    "- Remove the game scene completely: floor, walls, characters, props, lighting and shadows. Replace all of it with a solid pure black background "
    "(#000000) edge to edge, with no gradient, vignette, texture or noise.\n"
    "- Keep every UI element exactly where it is, with the same size, shape, outline, ornaments, inner patterns, colors and text, and keep the same framing "
    "and aspect ratio of the picture (do not crop, zoom, re-center or rotate).\n"
    "- Where a UI band or panel is translucent, show it as it would look over black (its own colors and pattern fading into black) — never keep the scene "
    "showing through it.\n"
    "- Redraw everything crisp and sharp at the highest resolution you can, with clean thin lines.\n"
)
# 1b 후속 H3 — 진짜 알파 컨셉(--transparent): 검정 배경 컨셉은 '어둡고 반투명한 장식'과 '어둡고 불투명한 칠'을 가를 수 없어(검정 위에선 같은 픽셀)
# flat_unmix 가 엠블럼 뒤 문양을 불투명 얼룩으로 · 서서히 옅어지는 띠 끝을 들쭉날쭉 잘랐다 [실측 H2 끝 run R20261116_212649 — WBP 디자이너 회색 바탕].
# built-in image_gen 은 투명 배경 요청에 진짜 알파를 낸다(SKILL.md 'Transparent image requests' · 1b-5 에셋 3장 실측) → normalize ⓐ transparent(알파 그대로).
TRANSPARENT_NOTE = (
    "- Output a PNG with a genuinely transparent background (a real alpha channel): every pixel that is not part of the UI is fully transparent — "
    "not black, not white, not gray, and never a painted checkerboard.\n"
    "- Translucent parts stay translucent in the alpha channel: a translucent band, panel or swirl pattern keeps its own colors with partial opacity, "
    "and soft glows fade out through alpha, so the UI blends correctly over any background. Never bake a backdrop color into them.\n"
)
TRANSPARENT_RULES = (
    "\n\nOutput rules for a UI-only concept (the pipeline cuts every element out of this picture, so the background must be empty):\n"
    "- Draw ONLY the UI elements listed above. No game scene, no characters, no environment, no sky, no vignette, no backdrop of any kind.\n"
    + TRANSPARENT_NOTE +
    "- Keep elements apart from the canvas edges.\n"
    "- Use the largest 16:9 landscape image size you can produce, with crisp thin lines and ornaments.\n"
)
TRANSPARENT_EDIT_RULES = (
    "\n\nOutput rules (the pipeline cuts every UI element out of the result, so the background must be empty):\n"
    "- Remove the game scene completely: floor, walls, characters, props, lighting and shadows. Nothing of the scene may remain, not even "
    "showing through translucent UI.\n"
    + TRANSPARENT_NOTE +
    "- Keep every UI element exactly where it is, with the same size, shape, outline, ornaments, inner patterns, colors and text, and keep the same framing "
    "and aspect ratio of the picture (do not crop, zoom, re-center or rotate).\n"
    "- Redraw everything crisp and sharp at the highest resolution you can, with clean thin lines.\n"
)
TEXT_FREE_TRANSPARENT = (
    "The attached image has a transparent background (PNG alpha). Keep the result genuinely transparent with the same alpha everywhere outside the text: "
    "no background color, no checkerboard, translucent parts equally translucent.\n"
)


# 1b 후속 H — 글자 없는 판(--text-free): 글자에 가려진 자리는 컨셉에 없는 정보라 결정적 메우기(줄 보간 · inpaint)는 띠의 사선 무늬 · 배지 광택 ·
# 장식을 되살리지 못한다 [실측 H — UI 만 컨셉 run 글자 자리 패치]. codex 가 같은 컨셉에서 글자만 지운 판을 그리고, refine 은 글자 구멍 픽셀만 그 판에서 가져온다.
TEXT_FREE_PROMPT = (
    "Remove every piece of text from the attached UI image: all words, labels, numbers, and the letters on the round key badges.\n"
    "Where text was, continue exactly what lies underneath it — the band's facets, gradient and pattern, the badge's metal disc and bevel, "
    "ornaments and glow — as if the text had never been drawn.\n"
    "Change nothing else: keep every element, line, color, position and size identical, the same background, the same framing and aspect ratio, "
    "and the same sharpness and resolution.\n"
)
TEXT_FREE_PURPOSE = "keep every UI element, line, color, position and size identical; only remove the text"

# 1b 후속 L-2 — 글자 없는 원본 아트(--text-free-first): 진짜 알파 UI 만 + 글자 칸은 비워 둠(칸 자리 설명은 프롬프트 파일 — 좌표 없음).
# 이 아트가 사람이 승인하는 픽셀 정답이고, 글자 스타일은 이어지는 참고판(codex 편집 — gen/text_ref)에서 잰다.
NO_TEXT_RULES = (
    "- Draw NO text at all: no letters, digits, numbers, words, labels, captions, symbols, runes, pseudo-text or watermark anywhere in the image. "
    "The game writes every text and number itself later.\n"
    "- Every place where a text or number will go stays an empty slot: show only the element's own surface there (the panel's fill, the banner's "
    "surface, or empty transparent space). Do not draw placeholder boxes, lines or frames for the slots.\n"
)
TEXT_FREE_FIRST_RULES = TRANSPARENT_RULES + NO_TEXT_RULES
TEXT_FREE_RETRY = ("\n\nThe previous image still contained letters or numbers. Draw the same UI again with absolutely no text of any kind — "
                   "every text slot stays empty.\n")
TEXT_FREE_FIRST_CALLS = 3      # 원본 아트 · (글자가 보이면) 한 번 더 · 참고판


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="make one screen concept image with codex built-in image_gen (Phase 1b input)")
    ap.add_argument("--out-dir", required=True, help="fixture folder — concept_prompt.md is read from here unless --prompt-file")
    ap.add_argument("--prompt-file", help="prompt text (default <out-dir>/concept_prompt.md)")
    ap.add_argument("--flat", action="store_true", help="1b 후속 H — UI only on a solid black background (for cutting the concept pixels)")
    ap.add_argument("--transparent", action="store_true",
                    help="1b 후속 H3 — UI only on a genuinely transparent background (real alpha — normalize keeps it as is); with --text-free keeps the alpha")
    ap.add_argument("--edit", help="1b 후속 H — edit this concept image with the prompt (concept change) instead of drawing a new one")
    ap.add_argument("--text-free", action="store_true", help="1b 후속 H — from <out-dir>/concept.png make concept_notext.png (codex removes the text only)")
    ap.add_argument("--with-text", action="store_true", help="draw the concept WITH its texts (L-1 — external-like / test input) instead of the L-2 default")
    ap.add_argument("--text-free-first", action="store_true",
                    help="1b 후속 L-2 — the default path by its old name: text-free original art (concept.png, real alpha, empty text slots) and then the "
                         "text reference (concept_text_ref.png — codex adds only the inputs texts)")
    ap.add_argument("--only", choices=("art", "text_ref"),
                    help="'art' stops after the text-free art (candidates — no inputs needed), "
                         "'text_ref' adds the text reference to the existing <out-dir>/concept.png")
    ap.add_argument("--style-ref", action="append", default=[],
                    help="attach this picture as a style reference only (mood · palette · material — repeatable): our own generated concepts, "
                         "or a picture the user gave (--style-ref-from-user)")
    ap.add_argument("--style-ref-from-user", action="store_true", help="the --style-ref pictures were given by the user")
    ap.add_argument("--cut-from", help="no codex — cut the --keep boxes out of this approved text-free sheet, pixel for pixel, as the original art")
    ap.add_argument("--keep", action="append", default=[], help="with --cut-from: x,y,w,h box to keep (px at 1920 wide, repeatable)")
    ap.add_argument("--draw", help="with --only text_ref: no codex — draw the inputs texts with the engine's own font files at the places this layout yaml gives")
    ap.add_argument("--inputs", help="1b 후속 L-2 — inputs.yaml for the text reference texts (default <out-dir>/inputs.yaml)")
    ap.add_argument("--force", action="store_true", help="replace an existing concept.png")
    ap.add_argument("--max-calls", type=int, default=None, help="codex calls allowed in this invocation (default: 3 for the art + text reference, 2 with --only art, else 1)")
    ap.add_argument("--config", help="pipeline.yaml to use")
    ap.add_argument("--work-root", help="override paths.work_root")
    return ap.parse_args(argv)


def _rel(p: pathlib.Path) -> str:
    """저장소 기준 상대 경로(커밋되는 concept.json 에 로컬 절대 경로를 남기지 않게)."""
    try:
        return pathlib.Path(p).resolve().relative_to(config.REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return pathlib.Path(p).name


def _mode_error(opts) -> str | None:
    """옵션이 서로 모순이면 이유(아니면 None) — 새 그림은 L-2 가 기본이고, 글자를 그리는 길(--with-text)은 따로 고른다."""
    editing = bool(opts.edit or opts.text_free)
    l2_only = [n for n, v in (("--text-free-first", opts.text_free_first), ("--only", opts.only)) if v]
    if opts.cut_from:
        if editing or opts.with_text or opts.flat or opts.transparent or opts.style_ref or opts.only:
            return "--cut-from only cuts an approved sheet (no codex) — not with the drawing / editing options"
        return None if opts.keep else "--cut-from needs at least one --keep x,y,w,h"
    if opts.keep:
        return "--keep needs --cut-from"
    if opts.draw and opts.only != "text_ref":
        return "--draw needs --only text_ref"
    if l2_only and (opts.with_text or opts.flat or editing):
        return f"{' / '.join(l2_only)} draws a new text-free transparent art — not with --with-text / --flat / --edit / --text-free"
    if (opts.flat or opts.transparent) and not editing and not opts.with_text and not opts.text_free_first:
        return ("a new concept is text-free by default (L-2 — already UI only with real alpha); "
                "--flat / --transparent draw a concept with its texts, so add --with-text")
    if opts.style_ref and (editing or opts.only == "text_ref"):
        return "--style-ref is only for a new drawing"
    if opts.style_ref_from_user and not opts.style_ref:
        return "--style-ref-from-user needs --style-ref"
    return None


STYLE_REF_PURPOSE = ("overall mood, palette, material and finish only — the layout and the elements come from the request; "
                     "do not copy their elements, shapes, texts or logos")
STYLE_REF_BG = (38, 37, 42)      # 투명 그림은 이 어두운 중립 바탕에 얹어 붙인다(알파를 무시하고 보면 투명 자리의 잡색이 보인다 — 후보 2 실측)


def style_refs(opts, out: pathlib.Path) -> tuple[list[pathlib.Path], list[dict]]:
    """--style-ref → (붙일 사본, 기록). 우리가 만든 그림(옆 concept.json 의 generator 가 codex · sha256 같음)이거나 사용자가 준 그림(--style-ref-from-user)만.
    work/_probe(상용 게임 화면)는 언제나 거절. 어긋나면 ValueError."""
    from PIL import Image
    paths, recs = [], []
    for i, p in enumerate(opts.style_ref):
        src = pathlib.Path(p)
        if not src.is_file():
            raise ValueError(f"--style-ref {src} does not exist")
        if "_probe" in src.resolve().parts:
            raise ValueError(f"--style-ref {src}: pictures under work/_probe (commercial game screens) are never attached")
        raw = src.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        source = "user" if opts.style_ref_from_user else None
        if source is None:
            try:
                side = json.loads(src.with_name("concept.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                side = {}
            if "codex" in str(side.get("generator", "")) and side.get("sha256") == sha:
                source = "ours"
        if source is None:
            raise ValueError(f"--style-ref {src}: not a picture we generated (no matching concept.json) — pass --style-ref-from-user if the user gave it")
        dst = out / f"style_ref_{i + 1}.png"
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            rgba = im.convert("RGBA")
            Image.alpha_composite(Image.new("RGBA", im.size, (*STYLE_REF_BG, 255)), rgba).convert("RGB").save(dst, format="PNG")
        paths.append(dst)
        recs.append({"file": _rel(src), "sha256": sha, "source": source})
    return paths, recs


def _cut_from(opts) -> int:
    """승인한 글자 없는 시안(한 장에 여러 화면 요소)에서 --keep 상자 안 픽셀만 그대로 남긴 원본 아트(밖은 투명 — codex 없음). 상자 가장자리에 걸린 요소가
    잘리면 안 되므로, 상자 안팎으로 이어진 보이는 픽셀이 있으면 거절한다. 상자 좌표는 1920 폭 기준."""
    import numpy as np
    from PIL import Image
    src, out_dir = pathlib.Path(opts.cut_from), pathlib.Path(opts.out_dir)
    dest = out_dir / "concept.png"
    if dest.exists() and not opts.force:
        print(f"make_concept: {dest} already exists — pass --force to replace it", file=sys.stderr)
        return EXIT_FAIL
    try:
        boxes = [[float(v) for v in k.split(",")] for k in opts.keep]
        if any(len(b) != 4 for b in boxes):
            raise ValueError("--keep takes x,y,w,h")
        with Image.open(src) as im:
            if "A" not in im.getbands():
                raise ValueError(f"{src} has no alpha channel — a text-free transparent sheet is needed")
            arr = np.asarray(im.convert("RGBA")).copy()
    except (OSError, ValueError) as exc:
        print(f"make_concept: {exc}", file=sys.stderr)
        return EXIT_FAIL
    H, W = arr.shape[:2]
    k = W / 1920.0
    keep = np.zeros((H, W), bool)
    for x, y, w, h in boxes:
        keep[max(0, round(y * k)):min(H, round((y + h) * k)), max(0, round(x * k)):min(W, round((x + w) * k))] = True
    vis = arr[..., 3] > CUT_VISIBLE
    cut = 0                                               # 상자 경계를 가로지르는 보이는 픽셀(안 · 밖 이웃이 둘 다 보임)
    for ax in (0, 1):
        a, b = (slice(None, -1), slice(1, None))
        s0 = (a, slice(None)) if ax == 0 else (slice(None), a)
        s1 = (b, slice(None)) if ax == 0 else (slice(None), b)
        cut += int((vis[s0] & vis[s1] & (keep[s0] != keep[s1])).sum())
    if cut:
        print(f"make_concept: the --keep boxes cut through {cut} visible pixel pair(s) (alpha > {CUT_VISIBLE}) — widen the boxes", file=sys.stderr)
        return EXIT_FAIL
    arr[~keep] = 0
    out_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(dest, format="PNG")
    boxes_txt = _ocr_boxes(dest)
    status = "ok" if not boxes_txt else "text_drawn"
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    try:
        side = json.loads(src.with_name("concept.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        side = {}
    meta = {"schema_version": 1, "kind": "concept", "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "generator": "codex built-in image_gen (cut from an approved sheet)",
            "thread_id": side.get("thread_id"), "prompt_sha256": None, "flat_background": False, "transparent_background": True,
            "transparent_ratio": round(float((arr[..., 3] == 0).mean()), 4), "edited_from": None, "file": dest.name, "sha256": sha, "size": [W, H],
            "has_alpha_channel": True, "cut_from": {"file": _rel(src), "sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "keep_1920": boxes},
            "text_free_first": {"status": status, "attempts": [{"attempt": 0, "file": _rel(dest), "ocr_boxes": boxes_txt, "sha256": sha}], "text_ref": None},
            "note": "L-2 original text-free art — the pixels of the approved sheet, only this screen's elements kept"}
    (out_dir / "concept.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"status": "cut" if status == "ok" else status, "art": dest.as_posix(), "kept_px": int((vis & keep).sum()),
                      "dropped_px": int((vis & ~keep).sum()), "art_text_boxes": boxes_txt, "codex_calls": 0}, ensure_ascii=False))
    return EXIT_OK if status == "ok" else EXIT_FAIL


FONT_DIR = config.UIGEN_DIR / "work" / "_fonts" / "pretendard"      # 엔진 폰트(F_Pretendard_W)를 임포트한 원본 TTF


def _draw_text_ref(opts) -> int:
    """메인 HUD(11-24) 결정 8 — 원본 아트에 글자만 그린 참고판(codex 0): 자리 · 크기 · 굵기 · 색 = --draw yaml(texts: [...]), 글자 값 = inputs, 글꼴 = 엔진과 같은 TTF."""
    from PIL import Image

    from gen import text_ref
    out_dir = pathlib.Path(opts.out_dir)
    inputs_path = pathlib.Path(opts.inputs) if opts.inputs else out_dir / "inputs.yaml"
    dest, ref_dest, meta_path = out_dir / "concept.png", out_dir / "concept_text_ref.png", out_dir / "concept.json"
    if ref_dest.exists() and not opts.force:
        print(f"make_concept: {ref_dest} already exists — pass --force to replace it", file=sys.stderr)
        return EXIT_FAIL
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if (meta.get("text_free_first") or {}).get("status") != "ok" or hashlib.sha256(dest.read_bytes()).hexdigest() != meta.get("sha256"):
            raise ValueError(f"--only text_ref needs the text-free art that {meta_path} records (text_free_first.status ok, same sha256)")
        layout = config.load_yaml(pathlib.Path(opts.draw))["texts"]
        with Image.open(dest) as im:
            art = im.convert("RGBA")
        items = text_ref.text_items(config.load_yaml(inputs_path))
        pic, drawn = text_ref.draw_items(art, layout, items, FONT_DIR)
    except (OSError, ValueError, KeyError, TypeError, config.ConfigError) as exc:
        print(f"make_concept: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_FAIL
    pic.save(ref_dest, format="PNG")
    rmeta = {"schema_version": 1, "kind": "concept_text_ref", "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "generator": "drawn with the engine font files (no codex)",
             "edited_from": dest.name, "thread_id": None, "texts": items, "layout_file": _rel(pathlib.Path(opts.draw)), "drawn": drawn, "file": ref_dest.name,
             "sha256": hashlib.sha256(ref_dest.read_bytes()).hexdigest(), "size": list(pic.size), "has_alpha_channel": True,
             "note": "the same art with only the texts drawn on it (Pretendard TTF) — glyph style reference"}
    (out_dir / "concept_text_ref.json").write_text(json.dumps(rmeta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    rmeta["check"] = text_ref.check_files(dest, ref_dest)
    (out_dir / "concept_text_ref.json").write_text(json.dumps(rmeta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    meta["text_free_first"]["text_ref"] = ref_dest.name
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ok = bool(rmeta["check"].get("used"))
    print(json.dumps({"status": "ok" if ok else "no_text_ref", "art": dest.as_posix(), "text_ref": ref_dest.as_posix(), "drawn": len(drawn), "codex_calls": 0,
                      "check": {k: rmeta["check"].get(k) for k in ("used", "reason", "shift_px", "glyph_px", "paste_px")}}, ensure_ascii=False))
    return EXIT_OK if ok else EXIT_FAIL


CUT_VISIBLE = 8                  # 시안의 거의 투명한 잡티(알파 ≤ 8/255)는 상자 경계를 가로질러도 요소가 아니다


def main(argv=None, *, cli: list[str] | None = None) -> int:
    opts = parse_args(argv)
    if opts.flat and opts.transparent:
        print("make_concept: --flat and --transparent are exclusive (black background vs real alpha)", file=sys.stderr)
        return EXIT_FAIL
    why = _mode_error(opts)
    if why:
        print(f"make_concept: {why}", file=sys.stderr)
        return EXIT_FAIL
    if opts.cut_from:
        return _cut_from(opts)
    if opts.draw:
        return _draw_text_ref(opts)
    cfg = config.load_pipeline(opts.config)
    if not (opts.with_text or opts.edit or opts.text_free):          # L-2 기본 전환 — 새 그림은 글자 없이가 기본
        return _text_free_first(opts, cfg, cli)
    if opts.max_calls is None:
        opts.max_calls = 1
    out_dir = pathlib.Path(opts.out_dir)
    prompt_file = pathlib.Path(opts.prompt_file) if opts.prompt_file else out_dir / "concept_prompt.md"
    dest = out_dir / ("concept_notext.png" if opts.text_free else "concept.png")
    if dest.exists() and not opts.force:
        print(f"make_concept: {dest} already exists — pass --force to replace it", file=sys.stderr)
        return EXIT_FAIL
    edit_src = pathlib.Path(opts.edit) if opts.edit else None
    purpose = EDIT_PURPOSE
    if opts.text_free:
        edit_src = edit_src or out_dir / "concept.png"     # 글자 없는 판 — 그 컨셉에서 글자만 지운다(프롬프트 파일 안 씀)
        prompt, purpose = TEXT_FREE_PROMPT.strip(), TEXT_FREE_PURPOSE
        if opts.transparent or _has_alpha(edit_src):
            prompt += "\n" + TEXT_FREE_TRANSPARENT.strip()       # 투명 컨셉의 판 — 알파를 지킨다(normalize 는 판에 알파가 없으면 컨셉 알파를 쓴다)
            opts.transparent = True
        prompt_file = pathlib.Path("(built-in TEXT_FREE_PROMPT)")
    else:
        try:
            prompt = prompt_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            print(f"make_concept: {prompt_file}: {exc}", file=sys.stderr)
            return EXIT_FAIL
        if opts.flat:
            prompt += FLAT_EDIT_RULES if edit_src is not None else FLAT_RULES
        elif opts.transparent:
            prompt += TRANSPARENT_EDIT_RULES if edit_src is not None else TRANSPARENT_RULES
    if edit_src is not None and not edit_src.is_file():
        print(f"make_concept: --edit {edit_src} does not exist", file=sys.stderr)
        return EXIT_FAIL
    work_root = pathlib.Path(opts.work_root) if opts.work_root else codex.work_root(cfg)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    gen_dir = work_root / "_concept" / stamp
    budget = codex.CallBudget(gen_dir / "codex_calls.jsonl", opts.max_calls, int(codex.codex_cfg(cfg).get("suspect_quota_after_failures", 2)))
    tmp = gen_dir / "concept.png"
    try:
        s_paths, s_recs = style_refs(opts, gen_dir) if opts.style_ref else ([], [])
    except ValueError as exc:
        print(f"make_concept: {exc}", file=sys.stderr)
        return EXIT_FAIL
    try:
        with codex.CodexLock(work_root, f"make_concept:{stamp}"):
            info = codex.preflight(cfg, cli=cli)
            if edit_src is not None:
                rec = codex.generate(prompt, tmp, gen_dir / "call_001", cfg, budget=budget, refs=[edit_src], ref_purpose=purpose,
                                     meta={"purpose": "concept_text_free" if opts.text_free else "concept_edit"}, cli=cli, edit=True)
            else:
                rec = codex.generate(prompt, tmp, gen_dir / "call_001", cfg, budget=budget, meta={"purpose": "concept"}, cli=cli,
                                     **({"refs": s_paths, "ref_purpose": STYLE_REF_PURPOSE} if s_paths else {}))
    except codex.CodexQuota as exc:
        print(json.dumps({"status": "quota", "code": exc.code, "message": str(exc), "gen_dir": gen_dir.as_posix()}, ensure_ascii=False))
        return EXIT_QUOTA
    except codex.CodexError as exc:
        print(json.dumps({"status": "fail", "code": exc.code, "message": str(exc), "gen_dir": gen_dir.as_posix()}, ensure_ascii=False))
        return EXIT_FAIL
    out_dir.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(tmp.read_bytes())
    meta = {"schema_version": 1, "kind": "concept", "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "generator": "codex built-in image_gen",
            "codex_version": info["version"], "thread_id": rec.get("thread_id"), "found_by": rec.get("found_by"),
            "prompt_file": prompt_file.name, "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "flat_background": bool(opts.flat), "transparent_background": bool(opts.transparent),
            "transparent_ratio": rec.get("transparent_ratio"), "edited_from": _rel(edit_src) if edit_src is not None else None,
            "file": dest.name, "sha256": rec["sha256"], "size": rec["size"], "has_alpha_channel": rec.get("has_alpha_channel"),
            "duration_s": rec.get("duration_s"), "usage": rec.get("usage"), "commands": rec.get("commands"), "record": _rel(gen_dir),
            **({"style_refs": s_recs} if s_recs else {}),
            "note": "AI-generated stand-in for a hand-made concept (Phase 1b) — replace concept.png with a person's art and rerun"}
    if opts.text_free:
        meta.update(kind="concept_text_free", note="the same concept with its text removed by codex — inputs concept_notext; refine fills the text holes from it")
    (out_dir / ("concept_notext.json" if opts.text_free else "concept.json")).write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n",
                                                                                         encoding="utf-8")
    # 투명을 요청했는데 알파 없이(또는 투명 픽셀 없이) 왔으면 그림은 남기되(호출은 이미 씀) 실패로 알린다 — normalize auto 는 ⓑ · ⓒ 로 판정한다
    no_alpha = opts.transparent and not (rec.get("has_alpha_channel") and (rec.get("transparent_ratio") or 0) > 0)
    print(json.dumps({"status": "no_alpha" if no_alpha else "ok", "file": dest.as_posix(), "size": rec["size"], "thread_id": rec.get("thread_id"),
                      "has_alpha_channel": rec.get("has_alpha_channel"), "transparent_ratio": rec.get("transparent_ratio"),
                      "duration_s": rec.get("duration_s")}, ensure_ascii=False))
    return EXIT_FAIL if no_alpha else EXIT_OK


def _ocr_boxes(path: pathlib.Path) -> list[dict]:
    """원본 아트에 그려진 글자로 볼 상자(gen/concept_route — 두 배율에서 같은 자리에 다시 잡힌 점수, 모호 포함). 검출 한 번(0.7)은 장식을 글자로 잡았다
    [실측 11-23 '검은 날' 시안 — 빈 동그라미 칸 둘 0.76]."""
    from gen import concept_route
    return concept_route.text_boxes(path)


def _text_free_first(opts, cfg: dict, cli) -> int:
    """1b 후속 L-2 ① ② — 글자 없는 원본 아트(concept.png) → 그 아트에 글자만 얹은 참고판(concept_text_ref.png). 결과는 inputs
    `concept_source: generated_textfree` · `concept_text_ref` 로 쓴다(normalize 가 정합 · 검사 — 여기 검사는 기록 · 알림용)."""
    from gen import text_ref
    out_dir = pathlib.Path(opts.out_dir)
    prompt_file = pathlib.Path(opts.prompt_file) if opts.prompt_file else out_dir / "concept_prompt.md"
    inputs_path = pathlib.Path(opts.inputs) if opts.inputs else out_dir / "inputs.yaml"
    dest, ref_dest = out_dir / "concept.png", out_dir / "concept_text_ref.png"
    want_art, want_ref = opts.only != "text_ref", opts.only != "art"
    blocked = [p for p, w in ((dest, want_art), (ref_dest, want_ref)) if w and p.exists()]
    if blocked and not opts.force:
        print(f"make_concept: {' or '.join(str(p) for p in blocked)} already exists — pass --force to replace them", file=sys.stderr)
        return EXIT_FAIL
    meta_path = out_dir / "concept.json"
    meta, items, ref_prompt, art_prompt = None, [], "", ""
    try:
        if want_art:
            art_prompt = prompt_file.read_text(encoding="utf-8").strip() + TEXT_FREE_FIRST_RULES
        else:                                           # 이미 있는(사람이 고른) 원본 아트에 참고판만
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            tff = meta.get("text_free_first") or {}
            if tff.get("status") != "ok" or hashlib.sha256(dest.read_bytes()).hexdigest() != meta.get("sha256"):
                print(f"make_concept: --only text_ref needs the text-free art that {meta_path} records (text_free_first.status ok, same sha256)", file=sys.stderr)
                return EXIT_FAIL
        if want_ref:
            inputs = config.load_yaml(inputs_path)
            items = text_ref.text_items(inputs)
            ref_prompt = text_ref.text_ref_prompt(inputs)
    except (OSError, ValueError, config.ConfigError) as exc:
        print(f"make_concept: {exc}", file=sys.stderr)
        return EXIT_FAIL
    if want_ref and not items:
        print(f"make_concept: {inputs_path} has no static_text / text · number sample to put on the text reference", file=sys.stderr)
        return EXIT_FAIL
    work_root = pathlib.Path(opts.work_root) if opts.work_root else codex.work_root(cfg)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    gen_dir = work_root / "_concept" / stamp
    max_calls = opts.max_calls if opts.max_calls is not None else TEXT_FREE_FIRST_CALLS - (0 if want_art and want_ref else 1 if want_art else 2)
    budget = codex.CallBudget(gen_dir / "codex_calls.jsonl", max_calls, int(codex.codex_cfg(cfg).get("suspect_quota_after_failures", 2)))
    attempts, art_rec, ref_rec, ref_check, ref_error, status = [], None, None, None, None, "ok"
    try:
        s_paths, s_recs = style_refs(opts, gen_dir) if want_art and opts.style_ref else ([], [])
    except ValueError as exc:
        print(f"make_concept: {exc}", file=sys.stderr)
        return EXIT_FAIL
    try:
        with codex.CodexLock(work_root, f"make_concept:{stamp}"):
            info = codex.preflight(cfg, cli=cli)
            for k in (1, 2) if want_art else ():
                if k == 2 and budget.used() >= max_calls:
                    break                                     # 상한 — 첫 그림을 남기고 text_drawn 으로 알린다(호출은 이미 썼다)
                tmp = gen_dir / f"art_{k}.png"
                art_rec = codex.generate(art_prompt + (TEXT_FREE_RETRY if k == 2 else ""), tmp, gen_dir / f"call_art_{k}", cfg, budget=budget,
                                         meta={"purpose": "concept_text_free_first", "attempt": k}, cli=cli,
                                         **({"refs": s_paths, "ref_purpose": STYLE_REF_PURPOSE} if s_paths else {}))
                boxes = _ocr_boxes(tmp)
                attempts.append({"attempt": k, "file": _rel(tmp), "ocr_boxes": boxes, "sha256": art_rec.get("sha256"),
                                 "transparent_ratio": art_rec.get("transparent_ratio"), "thread_id": art_rec.get("thread_id")})
                if not boxes:
                    break
            if want_art:
                status = "ok" if not attempts[-1]["ocr_boxes"] else "text_drawn"
                out_dir.mkdir(parents=True, exist_ok=True)
                dest.write_bytes((gen_dir / f"art_{len(attempts)}.png").read_bytes())
            if status == "ok" and want_ref:
                try:
                    tmp_ref = gen_dir / "text_ref.png"
                    ref_rec = codex.generate(ref_prompt, tmp_ref, gen_dir / "call_text_ref", cfg, budget=budget, refs=[dest],
                                             ref_purpose=text_ref.TEXT_REF_PURPOSE, meta={"purpose": "concept_text_ref"}, cli=cli, edit=True)
                    ref_dest.write_bytes(tmp_ref.read_bytes())
                    ref_check = text_ref.check_files(dest, ref_dest)
                except codex.CodexQuota:
                    raise
                except codex.CodexError as exc:
                    ref_error = f"{exc.code}: {str(exc)[:200]}"
    except codex.CodexQuota as exc:
        print(json.dumps({"status": "quota", "code": exc.code, "message": str(exc), "gen_dir": gen_dir.as_posix()}, ensure_ascii=False))
        return EXIT_QUOTA
    except codex.CodexError as exc:
        print(json.dumps({"status": "fail", "code": exc.code, "message": str(exc), "gen_dir": gen_dir.as_posix()}, ensure_ascii=False))
        return EXIT_FAIL
    if want_art:
        meta = {"schema_version": 1, "kind": "concept", "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "generator": "codex built-in image_gen",
                "codex_version": info["version"], "thread_id": art_rec.get("thread_id"), "found_by": art_rec.get("found_by"),
                "prompt_file": prompt_file.name, "prompt_sha256": hashlib.sha256(art_prompt.encode("utf-8")).hexdigest(),
                "flat_background": False, "transparent_background": True, "transparent_ratio": art_rec.get("transparent_ratio"), "edited_from": None,
                "file": dest.name, "sha256": art_rec["sha256"], "size": art_rec["size"], "has_alpha_channel": art_rec.get("has_alpha_channel"),
                "duration_s": art_rec.get("duration_s"), "usage": art_rec.get("usage"), "record": _rel(gen_dir),
                **({"style_refs": s_recs} if s_recs else {}),
                "text_free_first": {"status": status, "attempts": attempts, "text_ref": None,
                                    **({"fallback": "codex drew text on both tries — normalize treats this concept as a concept with text (L-1)"}
                                       if status != "ok" else {})},
                "note": "L-2 original text-free art (the approved pixel truth) — the text reference concept_text_ref.png only gives the text style"}
    if ref_rec:
        meta["text_free_first"]["text_ref"] = ref_dest.name
    if want_art or ref_rec:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if ref_rec:
        rmeta = {"schema_version": 1, "kind": "concept_text_ref", "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "generator": "codex built-in image_gen",
                 "edited_from": dest.name, "thread_id": ref_rec.get("thread_id"), "texts": items,
                 "prompt_sha256": hashlib.sha256(ref_prompt.encode("utf-8")).hexdigest(), "file": ref_dest.name, "sha256": ref_rec["sha256"],
                 "size": ref_rec["size"], "has_alpha_channel": ref_rec.get("has_alpha_channel"), "transparent_ratio": ref_rec.get("transparent_ratio"),
                 "duration_s": ref_rec.get("duration_s"), "check": ref_check,
                 "note": "the same art with only the texts added by codex — glyph style reference (background pixels are not the truth)"}
        (out_dir / "concept_text_ref.json").write_text(json.dumps(rmeta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    summary = {"status": status if status != "ok" else "art_only" if not want_ref else "ok" if ref_rec and (ref_check or {}).get("used") else "no_text_ref",
               "art": dest.as_posix(), "attempts": len(attempts), "art_text_boxes": [len(a["ocr_boxes"]) for a in attempts],
               "text_ref": ref_dest.as_posix() if ref_rec else None, "text_ref_error": ref_error,
               "text_ref_check": {k: (ref_check or {}).get(k) for k in ("used", "reason", "shift_px", "checks", "glyph_px", "paste_px")} if ref_check else None,
               "codex_calls": len(attempts) + (1 if (ref_rec or ref_error) else 0)}
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_OK


def _has_alpha(path: pathlib.Path | None) -> bool:
    """PNG 에 알파 채널이 있는가(IHDR 색 형식 4 · 6 또는 tRNS) — 글자 없는 판이 원본 컨셉의 투명 배경을 지키게."""
    if path is None or not path.is_file():
        return False
    data = path.read_bytes()[:64 * 1024]
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return False
    return data[25] in (4, 6) or b"tRNS" in data


if __name__ == "__main__":
    sys.exit(main())
