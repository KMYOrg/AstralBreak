"""1b 후속 I — 'UI 만 · 진짜 알파' 컨셉 자동 변환(normalize 가 부른다).

합성 스크린샷(ⓒ scene — 장면 위 UI)은 결정적으로 UI 와 장면을 가를 수 없고(반투명 잔상) 원본보다 선명해질 수 없다(H 사람 눈). 검정 배경(ⓑ flat)은
'어둡고 반투명'과 '어둡고 불투명'을 못 가른다(H3 회색 바탕). 사람이 `make_concept.py --edit <스크린샷> --transparent` + `--text-free` 로 손으로 하던
변환을 파이프라인 안에서 한다 — codex 편집 2 회(UI 만 투명 컨셉 · 그 컨셉의 글자 없는 판) → normalize 가 ⓐ transparent 로 잇는다(창작 = codex 한 번,
매핑 = 결정적 그대로).

- 켜는 때: inputs `concept_convert`(없으면 pipeline.yaml concept_convert.default) — auto = ⓒ 만 · force = ⓑ 도 · off = 안 함. ⓐ 는 바꾸지 않는다.
- 캐시: work_root/<cache_dir>/<원본 sha256 앞 16>_<프롬프트 sha256 앞 8>/ — 같은 원본 · 같은 프롬프트로 다시 돌리면 codex 를 부르지 않는다.
  검사에 떨어진 결과도 그 자리에 남겨 다시 부르지 않는다(지우면 다시 받는다). codex 오류 · 한도는 남기지 않는다(다음 run 에서 다시).
- 상한: 변환 호출 max_calls(기본 2) — run 전체 상한(limits.codex_calls_per_run · run 폴더 codex_calls.jsonl)도 같이 센다.
- 검사: 알파 채널 · 투명 비율 transparent_ratio 범위 · 원본과 비율 차 aspect_tol 안. 컨셉이 떨어지면 예전 경로(원본 그대로 — ⓒ GrabCut)로 물러나고
  사유를 남긴다(run 은 실패하지 않는다). 글자 없는 판만 떨어지면 ⓐ 로 가되 판 없이(줄 보간).
- 출처: 결과 dict(normalize.json background.convert) · run 폴더 convert/ 사본 · 캐시의 convert.json.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import shutil

from core import config
from gen import codex

SCENE_HEAD = ("The attached image is an in-game screenshot of a game screen with a HUD (user interface) drawn over the game scene. "
              "Turn it into a clean UI-only concept of that HUD on a transparent background.")
FLAT_HEAD = ("The attached image is a UI concept drawn on a solid black background — the black is only a backdrop and not part of the UI. "
             "Turn it into the same UI-only concept on a transparent background.")
CONVERT_PURPOSE = "keep every UI element, ornament, color, text, position and size of the attached screen; only remove what is not UI"


def settings(cfg: dict) -> dict:
    c = dict(cfg.get("concept_convert") or {})
    c.setdefault("default", "auto")
    c.setdefault("max_calls", 2)
    c.setdefault("aspect_tol", 0.03)
    c.setdefault("transparent_ratio", [0.05, 0.95])
    c.setdefault("text_free", True)
    c.setdefault("cache_dir", "_convert")
    return c


def build_prompt(inputs: dict, source_kind: str) -> str:
    """변환 프롬프트 — 화면 설명(inputs text · 필수 요소 · 고정 글자)으로 지킬 요소를 적고, make_concept 의 진짜 알파 편집 규칙을 붙인다."""
    import make_concept
    lines = [SCENE_HEAD if source_kind == "scene" else FLAT_HEAD,
             "Keep the screen exactly in the state it shows: do not add any element, glow, text or icon that is not in the attached image, "
             "do not remove any UI element, and keep gauge levels, numbers and labels as they are.", ""]
    if str(inputs.get("text") or "").strip():
        lines += [f"About this screen (some parts may only appear in other states — draw only what the attached image shows): {inputs['text'].strip()}", ""]
    req = inputs.get("required_elements") or []
    if req:
        lines.append("Names of the HUD elements, to help you recognize them (keep each one that is visible, exactly as it looks):")
        lines += [f"- {e.get('desc') or e.get('id')}" for e in req]
        lines.append("")
    texts = [str(t.get("value")) for t in (inputs.get("static_text") or []) if str(t.get("value") or "").strip()]
    if texts:
        lines.append("Text that may appear in the image — where it is visible, keep it exactly as written: " + ", ".join(f'"{t}"' for t in texts) + ".")
    return "\n".join(lines).strip() + make_concept.TRANSPARENT_EDIT_RULES


def _sha(path: pathlib.Path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def _size(path: pathlib.Path) -> tuple[int, int]:
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def _aspect_ok(a: tuple[int, int], b: tuple[int, int], tol: float) -> tuple[bool, float]:
    d = abs((a[0] / max(1, a[1])) / (b[0] / max(1, b[1])) - 1.0)
    return d <= tol, round(d, 4)


def source_kind(src: pathlib.Path, override: str | None) -> dict:
    """원본 컨셉의 배경 판정(gen/cutout.classify — inputs concept_background 가 auto 가 아니면 그것)."""
    import numpy as np
    from PIL import Image

    from gen import cutout
    with Image.open(src) as im:
        arr = np.asarray(im.convert("RGBA") if im.mode in ("RGBA", "LA", "P") else im.convert("RGB"))
    return cutout.classify(arr, override or "auto")


def wanted(mode: str, kind: str) -> bool:
    return mode != "off" and (kind == "scene" or (kind == "flat" and mode == "force"))


def convert(run, src: pathlib.Path, inputs: dict, mode: str, kind: str, *, cli: list[str] | None = None) -> dict:
    """원본(src — ⓒ · ⓑ) → {"used", "concept"(경로 | None), "notext"(경로 | None), 기록 …}. 실패해도 예외 없이 used False · fallback 사유."""
    cfg = run.cfg
    st = settings(cfg)
    src = pathlib.Path(src)
    src_sha = _sha(src)
    prompt = build_prompt(inputs, kind)
    psha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    root = codex.work_root(cfg) / str(st["cache_dir"])
    cdir = root / f"{src_sha[:16]}_{psha[:8]}"
    rec: dict = {"used": False, "mode": mode, "source_kind": kind, "source": _rel(src), "source_sha256": src_sha, "prompt_sha256": psha,
                 "cache_dir": _rel(cdir), "codex_calls": 0, "fallback": None, "concept": None, "notext": None}
    src_size = _size(src)
    lo, hi = (float(v) for v in st["transparent_ratio"])
    tol = float(st["aspect_tol"])
    cache_file = cdir / "convert.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.is_file() else {}
    budget = codex.CallBudget(run.path("codex_calls.jsonl"), int((cfg.get("limits") or {}).get("codex_calls_per_run", 20)),
                              int(codex.codex_cfg(cfg).get("suspect_quota_after_failures", 2)))
    state = {"lock": None}

    def call(prompt_text: str, ref: pathlib.Path, dest: pathlib.Path, sub: str, purpose: str, meta: dict) -> dict:
        if rec["codex_calls"] >= int(st["max_calls"]):
            raise codex.CodexError("CONVERT_CALL_LIMIT", f"concept_convert.max_calls {st['max_calls']} reached")
        if state["lock"] is None:
            lock = codex.CodexLock(codex.work_root(cfg), f"{run.run_id}:convert")
            lock.__enter__()
            state["lock"] = lock
            if not run.record.get("codex_cli"):
                run.record["codex_cli"] = codex.preflight(cfg, cli=cli)
        rec["codex_calls"] += 1
        return codex.generate(prompt_text, dest, run.path("convert", sub), cfg, budget=budget, refs=[ref], ref_purpose=purpose, meta=meta,
                              cli=cli, edit=True)

    try:
        # ① UI 만 · 진짜 알파 컨셉
        c = cache.get("concept") if cache.get("source_sha256") == src_sha and cache.get("prompt_sha256") == psha else None
        cpath = cdir / "concept.png"
        if c and (not c.get("ok") or (cpath.is_file() and _sha(cpath) == c.get("sha256"))):
            c = {**c, "cached": True}
        else:
            cdir.mkdir(parents=True, exist_ok=True)
            try:
                r = call(prompt, src, cpath, "call_concept", CONVERT_PURPOSE, {"purpose": "concept_convert"})
            except codex.CodexError as exc:
                rec["fallback"] = f"concept conversion failed ({exc.code}: {str(exc)[:160]}) — the original concept is used as before"
                return rec
            ok_aspect, d_aspect = _aspect_ok(tuple(r["size"]), src_size, tol)
            tr = r.get("transparent_ratio")
            checks = {"has_alpha_channel": bool(r.get("has_alpha_channel")), "transparent_ratio": tr, "transparent_ratio_range": [lo, hi],
                      "aspect_diff": d_aspect, "aspect_tol": tol}
            why = None
            if not r.get("has_alpha_channel") or tr is None:
                why = "no alpha channel"
            elif not (lo <= float(tr) <= hi):
                why = f"transparent ratio {tr} outside {lo} ~ {hi}"
            elif not ok_aspect:
                why = f"aspect differs from the original by {d_aspect} (> {tol})"
            c = {"ok": why is None, "reason": why, "sha256": r.get("sha256"), "size": r.get("size"), "thread_id": r.get("thread_id"),
                 "duration_s": r.get("duration_s"), "checks": checks, "cached": False}
            cache = {"schema_version": 1, "source": _rel(src), "source_sha256": src_sha, "prompt_sha256": psha, "prompt": prompt, "concept": c}
            cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        rec["concept"] = {k: v for k, v in c.items()}
        if not c.get("ok"):
            rec["fallback"] = f"converted concept rejected ({c.get('reason')}) — the original concept is used as before (cache {_rel(cdir)})"
            return rec
        out_dir = run.path("convert")
        out_dir.mkdir(parents=True, exist_ok=True)
        run_concept = out_dir / "concept.png"
        shutil.copyfile(cpath, run_concept)
        rec.update(used=True, concept_file="convert/concept.png")
        # ② 같은 컨셉의 글자 없는 판(알파 유지)
        if not st.get("text_free", True):
            rec["notext"] = {"used": False, "reason": "concept_convert.text_free is off"}
            return rec
        import make_concept
        nt_prompt = make_concept.TEXT_FREE_PROMPT.strip() + "\n" + make_concept.TEXT_FREE_TRANSPARENT.strip()
        nsha = hashlib.sha256(nt_prompt.encode("utf-8")).hexdigest()
        n = cache.get("notext") if cache.get("notext", {}).get("from_sha256") == c.get("sha256") and cache.get("notext", {}).get("prompt_sha256") == nsha else None
        npath = cdir / "concept_notext.png"
        if n and (not n.get("ok") or (npath.is_file() and _sha(npath) == n.get("sha256"))):
            n = {**n, "cached": True}
        else:
            try:
                r = call(nt_prompt, cpath, npath, "call_notext", make_concept.TEXT_FREE_PURPOSE, {"purpose": "concept_convert_text_free"})
            except codex.CodexError as exc:
                rec["notext"] = {"used": False, "reason": f"text-free conversion failed ({exc.code}: {str(exc)[:160]}) — text holes are filled as before"}
                return rec
            ok_aspect, d_aspect = _aspect_ok(tuple(r["size"]), tuple(c["size"]), tol)
            n = {"ok": ok_aspect, "reason": None if ok_aspect else f"aspect differs from the converted concept by {d_aspect} (> {tol})",
                 "sha256": r.get("sha256"), "size": r.get("size"), "thread_id": r.get("thread_id"), "duration_s": r.get("duration_s"),
                 "has_alpha_channel": bool(r.get("has_alpha_channel")), "transparent_ratio": r.get("transparent_ratio"),
                 "from_sha256": c.get("sha256"), "prompt_sha256": nsha, "cached": False}
            cache["notext"] = n
            cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        if not n.get("ok"):
            rec["notext"] = {**n, "used": False}
            return rec
        shutil.copyfile(npath, out_dir / "concept_notext.png")
        rec["notext"] = {**n, "used": True, "file": "convert/concept_notext.png"}
        return rec
    finally:
        if state["lock"] is not None:
            state["lock"].__exit__(None, None, None)
        run.write_json("convert/convert.json", rec)


def _rel(p) -> str:
    try:
        return pathlib.Path(p).resolve().relative_to(config.REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return pathlib.Path(p).as_posix()
