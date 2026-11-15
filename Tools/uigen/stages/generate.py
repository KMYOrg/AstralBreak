"""generate — spec.assets[] 를 백엔드로 만든다 (설계 §2-2 · §7).

백엔드: procedural(1a) · codex(1b-5 — gen/codex.py, built-in image_gen).
codex 에셋:
  - 처음 쓸 때 run 마다 한 번 `codex.preflight`(버전 · ChatGPT 로그인 — API 키 로그인이면 거부) → run.json codex_cli.
  - 잠금 `work/.codex.lock`(이 단계 동안) · 호출 상한 `limits.codex_calls_per_run`(run 폴더 codex_calls.jsonl — 실패도 센다).
  - 참조(-i): reference.png 에서 asset.ref_bbox(+8 px)를 잘라 gen/<asset_id>/ref.png — 그 안의 TextBlock 자리(bbox_intent)는 inpaint 로 지운다
    (참조의 글자를 베끼지 않게). ref_bbox 가 없으면 참조 없이.
  - 프롬프트 = analyze 의 asset.prompt + 출력 조건(고립된 요소 · 투명 배경 · 글자 없음 · 비율 · 최종 크기). 다시 만들 때(재시도 replace_asset)는
    '앞 판에 글자 같은 자국이 있었다 — 어디에도 글씨를 넣지 말 것'을 더한다.
  - 한도 → CODEX_QUOTA 로 멈춤(on_quota: pause). 그 밖의 codex 실패는 그 코드로 멈춘다(요청한 출처를 몰래 바꾸지 않는다 — router).
  - **source_mode: extract (1b 후속 A)** — 컨셉에 보이는 요소는 새로 그리지 않고 codex **편집**으로 따온다: 입력 = reference 에서 ref_bbox(+pad)를
    자른 것(3:1 보다 길면 실제 화면으로 짧은 변을 넓힘 · 글자 자리 inpaint, `gen/<id>/<시도>/input.png`), 틀 = codex.EDIT_WRAPPER,
    프롬프트 = analyze 의 asset.prompt(요소 이름 + 지울 것) + EXTRACT_RULES. 되자르기용 영역 · 요소 상자를 gen.jsonl `extract` 에 남긴다(refine 이 쓴다).
    extract 가 실패해도 generate 로 바꾸지 않는다(요청한 방식을 몰래 바꾸지 않음).
출력: assets/raw/<asset_id>.png · gen.jsonl(에셋마다 한 줄 — backend · ok · duration_s · sha256 · attempt (+ codex: thread_id · usage · found_by · source_mode · extract)).
재시도에서 replace_asset 로 돌아오면 opts.only_assets 의 에셋만 다시 만든다.
"""
from __future__ import annotations

import contextlib
import hashlib
import time

from core import config
from core import png
from gen import codex
from gen import procedural
from gen.router import RouteError, choose_backend
from stages import StageError

OUTPUT_RULES = (
    "\n\nOutput requirements (the image is used directly as a UI texture):\n"
    "- One isolated {kind} only, centered, filling most of the canvas with a small transparent margin.\n"
    "- Aspect ratio about {w}:{h} (it is resized to {w}x{h} px{stretch}).\n"
    "- Fully transparent background (real alpha channel) — no backdrop, no scene, no characters, no drop shadow beyond the element.\n"
    "- Absolutely no text, letters, numbers or glyph-like marks anywhere{interior}.\n"
)
REGEN_NOTE = "- The previous version contained text-like marks. Keep every area free of writing, runes and symbols that look like letters.\n"
EXTRACT_HEAD = "The attached image is a crop of a game UI mockup centered on one {kind}: {prompt}\nEdit it into a clean UI texture of that {kind}:\n"
EXTRACT_RULES = (
    "- Keep the {kind} exactly as drawn: the same outline, ornaments, line thickness, proportions, position and size in the picture, and the same "
    "colors. Do not redesign, restyle, add, remove, move or resize anything except what this request says to remove.\n"
    "- Make everything outside the {kind} fully transparent (real alpha channel): the scene, background, characters, light, glow and any text around it.\n"
    "{interior}"
    "- No text, numbers or text-like marks anywhere.\n"
    "- Keep the same framing: do not crop, zoom, re-center, rotate or change the aspect ratio of the picture.\n"
)
EXTRACT_INTERIOR = "- Inside it, replace the picture with one flat color matching the current interior, with no smudges, glow blobs or marks.\n"
EXTRACT_PURPOSE = "keep the UI element's exact shape, ornaments, proportions, position, size and colors"


def extract_prompt(asset: dict, regenerate: bool) -> str:
    kind = asset.get("kind", "element")
    interior = EXTRACT_INTERIOR if kind in ("frame", "panel_bg") else ""
    return (EXTRACT_HEAD.format(kind=kind, prompt=(asset.get("prompt") or "").strip()) + EXTRACT_RULES.format(kind=kind, interior=interior)
            + (REGEN_NOTE if regenerate else ""))


def codex_prompt(asset: dict, regenerate: bool) -> str:
    w, h = (int(v) for v in asset["size"])
    rules = OUTPUT_RULES.format(kind=asset.get("kind", "element"), w=w, h=h,
                                stretch=", the middle stretches as a 9-slice" if asset.get("nine_slice") else "",
                                interior="; keep the interior empty" if asset.get("kind") in ("frame", "panel_bg") else "")
    return (asset.get("prompt") or "").strip() + rules + (REGEN_NOTE if regenerate else "")


def _text_boxes(spec: dict) -> list:
    return [w["bbox_intent"] for w in spec.get("widgets", []) if w.get("type") == "TextBlock" and w.get("bbox_intent")]


class _CodexSession:
    """이 단계에서 codex 를 처음 쓸 때 잠금 · 시작 검사 · 호출 상한을 연다."""

    def __init__(self, run, stack: contextlib.ExitStack, cli):
        self.run, self.stack, self.cli = run, stack, cli
        self.ready = False
        self.budget = None

    def open(self):
        if self.ready:
            return
        cfg = self.run.cfg
        try:
            self.stack.enter_context(codex.CodexLock(config.repo_path(cfg["paths"]["work_root"]), self.run.run_id))
            if not self.run.record.get("codex_cli"):
                self.run.record["codex_cli"] = codex.preflight(cfg, cli=self.cli)
        except codex.CodexError as exc:
            raise StageError(exc.code, str(exc).split(": ", 1)[-1]) from exc
        self.budget = codex.CallBudget(self.run.path("codex_calls.jsonl"), int(cfg["limits"]["codex_calls_per_run"]),
                                       int(codex.codex_cfg(cfg).get("suspect_quota_after_failures", 2)))
        self.ready = True


def _render_codex(run, asset: dict, spec: dict, session: _CodexSession, regenerate: bool, attempt: int) -> tuple[int, int, dict]:
    from gen import postprocess as pp
    session.open()
    aid = asset["asset_id"]
    gen_dir = run.path("gen", aid, f"{attempt:03d}")
    refs, ref_info = [], None
    mode = asset.get("source_mode") or "generate"
    extract = None
    if mode == "extract":
        if not (asset.get("ref_bbox") and run.path("reference.png").is_file()):
            raise StageError("EXTRACT_NO_REFERENCE", f"'{aid}' is source_mode extract but has no ref_bbox or there is no reference.png", asset=aid)
        ext = run.cfg.get("extract") or {}
        ref = gen_dir / "input.png"
        ref_info = pp.extract_input(run.path("reference.png"), asset["ref_bbox"], _text_boxes(spec), ref,
                                    pad=int(ext.get("pad", pp.EXTRACT_PAD)), max_aspect=float(ext.get("max_aspect", pp.EXTRACT_MAX_ASPECT)))
        refs.append(ref)
        extract = {"region": ref_info["region"], "element": ref_info["element"], "aspect": ref_info["aspect"],
                   "aspect_within_limit": ref_info["aspect_within_limit"]}
        prompt, purpose = extract_prompt(asset, regenerate), EXTRACT_PURPOSE
    else:
        if asset.get("ref_bbox") and run.path("reference.png").is_file():
            ref = gen_dir / "ref.png"
            ref_info = pp.reference_crop(run.path("reference.png"), asset["ref_bbox"], _text_boxes(spec), ref)
            refs.append(ref)
        prompt, purpose = codex_prompt(asset, regenerate), "the shape, proportions, colors and ornament style of this HUD element"
    raw = run.path("assets", "raw", f"{aid}.png")
    try:
        rec = codex.generate(prompt, raw, gen_dir / "call", run.cfg, budget=session.budget, refs=refs,
                             ref_purpose=purpose, meta={"asset_id": aid, "attempt": attempt}, cli=session.cli, edit=mode == "extract")
    except codex.CodexQuota as exc:
        raise StageError("CODEX_QUOTA", f"codex usage limit while generating '{aid}' — paused (rerun later): {exc}", asset=aid, **exc.details) from exc
    except codex.CodexError as exc:
        raise StageError(exc.code, f"codex failed for '{aid}': {exc}", asset=aid) from exc
    w, h = rec["size"]
    out = {"thread_id": rec.get("thread_id"), "found_by": rec.get("found_by"), "usage": rec.get("usage"), "codex_s": rec.get("duration_s"),
           "ref": ref_info, "regenerate": regenerate, "source_mode": mode}
    if extract:
        out["extract"] = extract
    return w, h, out


def run(run, opts) -> str:
    spec = run.read_json("spec.json")
    routing = config.load_routing()
    allowed = list(run.cfg["backends"]["allowed"])
    only = set(getattr(opts, "only_assets", None) or [])
    attempt = int(getattr(opts, "attempt", 0) or 0)
    made = []
    with contextlib.ExitStack() as stack:
        session = _CodexSession(run, stack, getattr(opts, "codex_cli", None))
        for asset in spec.get("assets", []):
            aid = asset["asset_id"]
            if only and aid not in only:
                continue
            t0 = time.monotonic()
            extra: dict = {}
            try:
                backend = choose_backend(asset, routing, allowed)
                if backend == "procedural":
                    w, h, rgba = procedural.render(asset)
                    path = png.write_rgba(run.path("assets", "raw", f"{aid}.png"), w, h, rgba)
                elif backend == "codex":
                    w, h, extra = _render_codex(run, asset, spec, session, regenerate=bool(only), attempt=attempt)
                    path = run.path("assets", "raw", f"{aid}.png")
                else:
                    raise StageError("BACKEND_MISSING", f"backend '{backend}' is allowed but not implemented yet", asset=aid)
            except (RouteError, procedural.ProceduralError) as exc:
                run.append_jsonl("gen.jsonl", {"asset_id": aid, "kind": asset.get("kind"), "ok": False, "error": str(exc), "attempt": attempt,
                                               "duration_s": round(time.monotonic() - t0, 3)})
                raise StageError(getattr(exc, "code", "PROCEDURAL"), str(exc), asset=aid) from exc
            except StageError as exc:
                run.append_jsonl("gen.jsonl", {"asset_id": aid, "kind": asset.get("kind"), "backend": asset.get("provenance"), "ok": False,
                                               "error": f"{exc.code}: {str(exc)[:300]}", "attempt": attempt, "duration_s": round(time.monotonic() - t0, 3)})
                raise
            dur = round(time.monotonic() - t0, 3)
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            run.append_jsonl("gen.jsonl", {"asset_id": aid, "kind": asset.get("kind"), "backend": backend, "ok": True, "duration_s": dur,
                                           "sha256": sha, "size": [w, h], "attempt": attempt, **extra})
            made.append(f"{aid}({backend} {w}x{h})")
    used = session.budget.used() if session.budget else 0
    tail = f" — codex calls this run {used}/{run.cfg['limits']['codex_calls_per_run']}" if session.budget else ""
    return (f"{len(made)} asset(s): " + ", ".join(made) + tail) if made else "no assets"
