"""컨셉아트 1장 만들기 (Phase 1b 준비 — 설계 §11 '1b 착수 때 정한 것'). codex built-in image_gen 으로 화면 컨셉을 만들어 fixture 로 둔다.

원래 text 모드(Phase 3)의 목업 단계 성격이다. 1b 는 이 그림을 concept 입력으로 쓰고, 나중에 사람이 그린 컨셉으로 바꿔 같은 파이프라인을 다시 돌린다.

    Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/make_concept.py --out-dir Tools/uigen/fixtures/m4_combat_hud_concept
    (+ --prompt-file <md> · --force(있는 concept.png 를 덮음) · --max-calls N(기본 1)
     · --flat(1b 후속 H — UI 만 · 단색 검정 배경 · 장면 없음 · 가장 큰 크기: 컨셉 픽셀을 오려 쓰기 좋은 컨셉)
     · --edit <concept.png>(1b 후속 H — 그 컨셉을 프롬프트대로 codex 편집해 새 컨셉으로 — '컨셉을 ~식으로 바꿔 줘')
     · --transparent(1b 후속 H3 — UI 만 · 진짜 알파 투명 배경: normalize ⓐ 가 알파를 그대로 쓴다, --flat 과 함께 못 씀)
     · --text-free(1b 후속 H2 — concept.png 에서 글자만 지운 concept_notext.png, 원본이 투명이면 알파를 지키라고 덧붙임))

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


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="make one screen concept image with codex built-in image_gen (Phase 1b input)")
    ap.add_argument("--out-dir", required=True, help="fixture folder — concept_prompt.md is read from here unless --prompt-file")
    ap.add_argument("--prompt-file", help="prompt text (default <out-dir>/concept_prompt.md)")
    ap.add_argument("--flat", action="store_true", help="1b 후속 H — UI only on a solid black background (for cutting the concept pixels)")
    ap.add_argument("--transparent", action="store_true",
                    help="1b 후속 H3 — UI only on a genuinely transparent background (real alpha — normalize keeps it as is); with --text-free keeps the alpha")
    ap.add_argument("--edit", help="1b 후속 H — edit this concept image with the prompt (concept change) instead of drawing a new one")
    ap.add_argument("--text-free", action="store_true", help="1b 후속 H — from <out-dir>/concept.png make concept_notext.png (codex removes the text only)")
    ap.add_argument("--force", action="store_true", help="replace an existing concept.png")
    ap.add_argument("--max-calls", type=int, default=1, help="codex calls allowed in this invocation (default 1 — plan usage)")
    ap.add_argument("--config", help="pipeline.yaml to use")
    ap.add_argument("--work-root", help="override paths.work_root")
    return ap.parse_args(argv)


def _rel(p: pathlib.Path) -> str:
    """저장소 기준 상대 경로(커밋되는 concept.json 에 로컬 절대 경로를 남기지 않게)."""
    try:
        return pathlib.Path(p).resolve().relative_to(config.REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return pathlib.Path(p).name


def main(argv=None, *, cli: list[str] | None = None) -> int:
    opts = parse_args(argv)
    if opts.flat and opts.transparent:
        print("make_concept: --flat and --transparent are exclusive (black background vs real alpha)", file=sys.stderr)
        return EXIT_FAIL
    cfg = config.load_pipeline(opts.config)
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
        with codex.CodexLock(work_root, f"make_concept:{stamp}"):
            info = codex.preflight(cfg, cli=cli)
            if edit_src is not None:
                rec = codex.generate(prompt, tmp, gen_dir / "call_001", cfg, budget=budget, refs=[edit_src], ref_purpose=purpose,
                                     meta={"purpose": "concept_text_free" if opts.text_free else "concept_edit"}, cli=cli, edit=True)
            else:
                rec = codex.generate(prompt, tmp, gen_dir / "call_001", cfg, budget=budget, meta={"purpose": "concept"}, cli=cli)
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
