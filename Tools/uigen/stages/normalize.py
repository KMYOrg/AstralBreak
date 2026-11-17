"""normalize — 입력을 brief · spec 으로 (설계 §2-2).

1a(hand_spec): 손으로 쓴 brief.json · spec.json 이 든 폴더를 받아 검사하고 run 폴더로 복사한다. analyze 는 건너뛴다(spec 이 이미 있다).
1b(concept): inputs.yaml(schemas/inputs) + 컨셉 PNG → reference.png(기준 해상도로 맞춤) · brief.json. spec 은 analyze 가 만든다.
  - 맞추기: 비율 차이 ≤ 1 % 면 늘림(stretch), 넘으면 가운데 맞춤 + 검은 띠(letterbox) — normalize.json 에 변환을 남긴다.
  - (1b 후속 H) 배경 판정 ⓐ transparent · ⓑ flat · ⓒ scene(inputs concept_background, 기본 auto) — ⓐ ⓑ 는 reference_alpha.png ·
    reference_color.png 를 남기고 refine 의 오리기가 그 알파 · 색을 쓴다(gen/cutout). normalize.json background 에 판정 기록.
  - (1b 후속 H2) inputs concept_notext(같은 컨셉에서 글자만 지운 판 — make_concept --text-free)가 있으면 같은 배경 처리 · 배치로 맞추고 위상 상관으로
    정합해 reference_notext_color.png · reference_notext_alpha.png 를 남긴다(refine 이 글자 구멍만 채우고, 글자 맞춤이 컨셉 획을 잰다).
  - brief: 계약(바인딩 위젯 이름 · 위젯 타입 · 데이터 · 고정 글자)은 inputs 가 정한 그대로, 폰트 기본값은 pipeline.yaml fonts.default_family.
text · multi_ref 는 Phase 3.

검사: 스키마 · spec 의미 검사 · brief ↔ spec 맞물림(필수 요소 · 바인딩 계약 · 동적 데이터 · 고정 글자). 하나라도 어긋나면 run 을 시작하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import pathlib

from core import config
from core import schema
from core import spec as spec_mod
from gen import concept_convert
from stages import StageError

ASPECT_STRETCH_MAX = 0.01   # 비율 차이가 이보다 작으면 늘린다(컨셉 1672×941 → 1920×1080 은 0.06 %)


def _load(path: pathlib.Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StageError("INPUT_UNREADABLE", f"{path}: {exc}") from exc


def check_brief_vs_spec(brief: dict, spec: dict) -> list[str]:
    errs: list[str] = []
    index = spec_mod.widget_index(spec)
    if brief["screen_type"] != spec["profile"]:
        errs.append(f"PROFILE: brief.screen_type '{brief['screen_type']}' != spec.profile '{spec['profile']}'")
    if list(brief["resolution"]) != [int(v) for v in spec["canvas"]]:
        errs.append(f"CANVAS: brief.resolution {brief['resolution']} != spec.canvas {spec['canvas']}")
    for el in brief["required_elements"]:
        if el["id"] not in index:
            errs.append(f"REQUIRED_MISSING: '{el['id']}' ({el.get('desc', el['kind'])}) is not in the spec")
    bound = spec_mod.bound_widgets(spec)
    contract = brief.get("binding_contract")
    if contract and set(contract["bindings"]) != set(bound):
        errs.append(f"CONTRACT: binding_contract {sorted(contract['bindings'])} != spec bindings {sorted(bound)}")
    for d in brief["dynamic_data"]:
        b = bound.get(d["widget"])
        if not b:
            errs.append(f"DATA_UNBOUND: dynamic_data '{d['id']}' → '{d['widget']}' has no binding in the spec")
            continue
        if b["data"] != d["id"] or b["kind"] != d["type"]:
            errs.append(f"DATA_MISMATCH: '{d['widget']}' binding {b['data']}/{b['kind']} != brief {d['id']}/{d['type']}")
        if d["type"] == "number" and d.get("format") != b.get("format"):
            errs.append(f"DATA_FORMAT: '{d['widget']}' format {b.get('format')} != brief {d.get('format')}")
    data_ids = {d["id"] for d in brief["dynamic_data"]}
    for wid, b in bound.items():
        if b["data"] not in data_ids:
            errs.append(f"BINDING_NOT_IN_BRIEF: '{wid}' binds '{b['data']}' which brief.dynamic_data does not list")
    for st in brief.get("static_text", []):
        w = index.get(st["widget"])
        if not w or w.get("type") != "TextBlock":
            errs.append(f"STATIC_TEXT: '{st['widget']}' is not a TextBlock in the spec")
        elif (w.get("text") or {}).get("value") != st["value"]:
            errs.append(f"STATIC_TEXT: '{st['widget']}' text {(w.get('text') or {}).get('value')!r} != brief {st['value']!r}")
    for d in brief["dynamic_data"]:   # concept 모드 — 바인딩 위젯 타입은 요청이 고정한다(codegen 계약)
        w = index.get(d["widget"])
        if d.get("widget_type") and w and w.get("type") != d["widget_type"]:
            errs.append(f"WIDGET_TYPE: '{d['widget']}' is a {w.get('type')} in the spec, the request fixes {d['widget_type']} (BindWidget contract)")
    return errs


def run(run, opts) -> str:
    if getattr(opts, "inputs", None):
        return run_concept(run, opts)
    return run_hand_spec(run, opts)


def _inputs_errors(inputs: dict) -> list[str]:
    """스키마로 못 보는 inputs 의 맞물림 — 계약이 스스로 모순되면 run 을 시작하지 않는다."""
    errs: list[str] = []
    data = inputs["data"]
    for key in ("id", "widget"):
        vals = [d[key] for d in data]
        dup = sorted({v for v in vals if vals.count(v) > 1})
        if dup:
            errs.append(f"DATA_DUPLICATE: data[].{key} {dup}")
    req = [e["id"] for e in inputs["required_elements"]]
    if len(set(req)) != len(req):
        errs.append("REQUIRED_DUPLICATE: required_elements[].id")
    by_widget = {d["widget"]: d for d in data}
    for d in data:
        okay = spec_mod.BINDING_WIDGET_TYPES.get(d["type"])
        if okay is not None and d["widget_type"] not in okay:
            errs.append(f"DATA_WIDGET_TYPE: '{d['widget']}' {d['widget_type']} cannot take a '{d['type']}' binding")
        if d.get("format") and d["type"] != "number":
            errs.append(f"DATA_FORMAT: '{d['id']}' format is only for number data")
        if d["type"] == "number" and not d.get("format"):
            errs.append(f"DATA_FORMAT: number data '{d['id']}' needs format ('0' or '0.0…')")
    for st in inputs.get("static_text", []):
        d = by_widget.get(st["widget"])
        if d and (d["widget_type"] != "TextBlock" or d["type"] in ("text", "number")):
            errs.append(f"STATIC_TEXT_CONFLICT: '{st['widget']}' is static text but data '{d['id']}' makes it a {d['widget_type']}/{d['type']}")
    return errs


def _fit_reference(src: pathlib.Path, dst: pathlib.Path, size: list[int], background: str | None = "auto", notext: pathlib.Path | None = None) -> dict:
    """컨셉 → 기준 해상도 RGB PNG. 비율 차이 ≤ 1 % 면 늘리고, 넘으면 가운데 맞춤 + 검은 띠.
    (1b 후속 H) 배경 판정(gen/cutout.classify — ⓐ transparent · ⓑ flat · ⓒ scene, inputs concept_background 가 auto 가 아니면 그것)을 하고,
    ⓐ ⓑ 는 dst 옆에 reference_alpha.png(L — 알파) · reference_color.png(RGB — 곧은 색: ⓐ 는 PNG 색, ⓑ 는 배경색 언믹싱)를 남긴다.
    그때 reference.png 는 곧은 색을 검정 위에 얹은 것(렌더 바탕이 검정 — ⓑ 키가 검정이면 원본과 같다). 띠 자리는 알파 0."""
    import numpy as np
    from PIL import Image   # rapidocr 와 함께 설치(1b-3) — normalize(concept) 만 쓴다
    from gen import cutout
    with Image.open(src) as im:
        src_arr = np.asarray(im.convert("RGBA") if ("A" in im.getbands() or "transparency" in im.info) else im.convert("RGB"))
    sh, sw = src_arr.shape[:2]
    try:
        bg = cutout.classify(src_arr, background)
    except cutout.CutoutError as exc:
        raise ValueError(str(exc)) from exc
    tw, th = int(size[0]), int(size[1])
    diff = abs((sw / sh) / (tw / th) - 1.0)
    if diff <= ASPECT_STRETCH_MAX:
        mode, scale, offset, (nw, nh) = "stretch", [tw / sw, th / sh], [0, 0], (tw, th)
    else:
        s = min(tw / sw, th / sh)
        nw, nh = max(1, round(sw * s)), max(1, round(sh * s))
        offset = [(tw - nw) // 2, (th - nh) // 2]
        mode, scale = "letterbox", [s, s]

    def place(ch: np.ndarray) -> np.ndarray:
        """한 채널(float) → 기준 해상도(LANCZOS, 띠 자리 0)."""
        r = np.asarray(Image.fromarray(ch.astype(np.float32), "F").resize((nw, nh), Image.Resampling.LANCZOS), float)
        out = np.zeros((th, tw), float)
        out[offset[1]:offset[1] + nh, offset[0]:offset[0] + nw] = r
        return out
    rec = {"kind": bg["kind"], "auto": bg["auto"], "source": bg["source"], "alpha_ratio": bg["alpha_ratio"], "ring_px": bg["ring_px"],
           "ring_uniform": bg["ring_uniform"], "key_color": bg["key_color"], "alpha": None, "color": None}
    dst.parent.mkdir(parents=True, exist_ok=True)
    if bg["kind"] == "scene":
        with Image.open(src) as im:
            im = im.convert("RGB")
            if mode == "stretch":
                out = im.resize((tw, th), Image.Resampling.LANCZOS)
            else:
                out = Image.new("RGB", (tw, th), (0, 0, 0))
                out.paste(im.resize((nw, nh), Image.Resampling.LANCZOS), tuple(offset))
        out.save(dst, format="PNG")
    else:
        if bg["kind"] == "transparent":
            col = src_arr[..., :3].astype(float)
            alpha = src_arr[..., 3].astype(float) / 255.0
        else:
            col, alpha, unmix = cutout.flat_unmix(src_arr[..., :3], bg["key"])
            rec["unmix"] = unmix
        a = np.clip(place(alpha), 0.0, 1.0)
        pm = np.dstack([place(col[..., i] * alpha) for i in range(3)])
        straight = np.where(a[..., None] > 1e-4, pm / np.maximum(a, 1e-4)[..., None], 0.0)
        straight = np.clip(straight, 0, 255)
        Image.fromarray(np.clip(straight * a[..., None], 0, 255).round().astype(np.uint8), "RGB").save(dst, format="PNG")
        Image.fromarray((a * 255).round().astype(np.uint8), "L").save(dst.with_name("reference_alpha.png"), format="PNG")
        Image.fromarray(straight.round().astype(np.uint8), "RGB").save(dst.with_name("reference_color.png"), format="PNG")
        rec.update(alpha="reference_alpha.png", color="reference_color.png", opaque_ratio=round(float((a > 0.98).mean()), 4),
                   transparent_ratio=round(float((a < 0.02).mean()), 4))
    if notext is not None:
        rec["notext"] = _fit_notext(notext, dst, src_arr, bg, place, (tw, th))
    return {"src_size": [sw, sh], "dst_size": [tw, th], "mode": mode, "aspect_diff": round(diff, 5),
            "scale": [round(v, 6) for v in scale], "offset": offset, "background": rec}


NOTEXT_MAX_SHIFT = 12      # 글자 없는 판 정합 — 위상 상관 이동이 이보다 크면 같은 그림으로 보지 않는다(px)


def _fit_notext(src: pathlib.Path, dst: pathlib.Path, concept_arr, bg: dict, place, size) -> dict:
    """1b 후속 H — 글자 없는 판(make_concept --text-free)을 컨셉과 같은 배치 · 같은 배경 처리로 맞추고(컨셉 원본 크기로 먼저 늘림) 위상 상관으로
    컨셉에 정합해 dst 옆에 reference_notext_color.png(곧은 색) · reference_notext_alpha.png 를 남긴다. codex 편집은 그림 전체를 다시 그려
    몇 px 어긋날 수 있다 — refine 이 요소마다 한 번 더 맞추고 글자 구멍 픽셀만 쓴다."""
    import cv2
    import numpy as np
    from PIL import Image
    from gen import cutout
    sh, sw = concept_arr.shape[:2]
    with Image.open(src) as im:
        has_a = "A" in im.getbands()
        src_size = list(im.size)
        arr = np.asarray((im.convert("RGBA") if has_a else im.convert("RGB")).resize((sw, sh), Image.Resampling.LANCZOS))
    tw, th = size
    if bg["kind"] == "flat":
        col, alpha, _ = cutout.flat_unmix(arr[..., :3], bg["key"])
    elif bg["kind"] == "transparent":
        col = arr[..., :3].astype(float)
        alpha = arr[..., 3].astype(float) / 255.0 if has_a else concept_arr[..., 3].astype(float) / 255.0
    else:
        col, alpha = arr[..., :3].astype(float), np.ones((sh, sw))
    a = np.clip(place(alpha), 0.0, 1.0)
    pm = np.dstack([place(col[..., i] * alpha) for i in range(3)])
    straight = np.clip(np.where(a[..., None] > 1e-4, pm / np.maximum(a, 1e-4)[..., None], 0.0), 0, 255)
    with Image.open(dst) as ref:
        ref_l = np.asarray(ref.convert("L"), np.float32)
    nt_l = np.asarray(Image.fromarray(np.clip(straight * a[..., None], 0, 255).astype(np.uint8), "RGB").convert("L"), np.float32)
    win = cv2.createHanningWindow((tw, th), cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(ref_l, nt_l, win)
    rec = {"src": src.name, "src_size": src_size, "shift_px": [round(float(dx), 2), round(float(dy), 2)],
           "response": round(float(response), 4)}
    if max(abs(dx), abs(dy)) > NOTEXT_MAX_SHIFT:
        rec["used"] = False
        rec["reason"] = f"phase correlation shift {rec['shift_px']} > {NOTEXT_MAX_SHIFT} px — not the same picture"
        return rec
    M = np.float32([[1, 0, -dx], [0, 1, -dy]])
    warp = lambda ch: cv2.warpAffine(ch.astype(np.float32), M, (tw, th), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)   # noqa: E731
    straight = np.dstack([warp(straight[..., i]) for i in range(3)])
    a = np.clip(warp(a), 0.0, 1.0)
    Image.fromarray(np.clip(straight, 0, 255).round().astype(np.uint8), "RGB").save(dst.with_name("reference_notext_color.png"), format="PNG")
    Image.fromarray((a * 255).round().astype(np.uint8), "L").save(dst.with_name("reference_notext_alpha.png"), format="PNG")
    rec.update(used=True, color="reference_notext_color.png", alpha="reference_notext_alpha.png")
    return rec


def run_concept(run, opts) -> str:
    src = pathlib.Path(opts.inputs)
    try:
        inputs = config.load_yaml(src)
    except config.ConfigError as exc:
        raise StageError("INPUT_UNREADABLE", str(exc)) from exc
    errs = schema.errors("inputs", inputs)
    if errs:
        raise StageError("SCHEMA", "inputs.yaml: " + "; ".join(errs[:8]), kind="inputs", errors=errs)
    errs = _inputs_errors(inputs)
    if errs:
        raise StageError("INPUTS_INVALID", "; ".join(errs[:8]), errors=errs)
    concept = pathlib.Path(opts.concept) if getattr(opts, "concept", None) else pathlib.Path(inputs["concept"])
    if not concept.is_absolute():
        concept = (pathlib.Path.cwd() if getattr(opts, "concept", None) else src.parent) / concept
    if not concept.is_file():
        raise StageError("INPUT_UNREADABLE", f"concept image {concept} does not exist")
    screens = config.load_screens()
    screen = screens.get(inputs["screen_id"])
    if not screen:
        raise StageError("SCREEN_UNKNOWN", f"screen_id '{inputs['screen_id']}' is not in screens.yaml")
    resolution = list(inputs.get("resolution") or [1920, 1080])
    # 글자 없는 판(1b 후속 H — make_concept --text-free) — inputs.yaml 기준 상대 경로. 컨셉을 명령줄로 바꿨으면 그 컨셉의 판이 아니라 쓰지 않는다
    notext, notext_skip = None, None
    if inputs.get("concept_notext"):
        if getattr(opts, "concept", None):
            notext_skip = "the concept was given on the command line — concept_notext belongs to the inputs concept"
        else:
            notext = pathlib.Path(inputs["concept_notext"])
            if not notext.is_absolute():
                notext = src.parent / notext
            if not notext.is_file():
                raise StageError("INPUT_UNREADABLE", f"concept_notext image {notext} does not exist")
    # 1b 후속 I — 합성 스크린샷(ⓒ · force 면 ⓑ 도)은 codex 편집으로 'UI 만 · 진짜 알파' 컨셉 + 글자 없는 판으로 바꿔 ⓐ 로 잇는다(gen/concept_convert).
    # 실패 · 검사 탈락이면 원본 그대로(예전 경로) — 사유는 normalize.json background.convert
    background = inputs.get("concept_background", "auto")
    original = concept
    conv = None
    mode = inputs.get("concept_convert") or concept_convert.settings(run.cfg)["default"]
    try:
        src_kind = concept_convert.source_kind(concept, background)
    except Exception as exc:  # noqa: BLE001 — 판정 실패는 _fit_reference 가 같은 오류로 다시 알린다
        src_kind = {"kind": None, "error": str(exc)[:200]}
    if src_kind.get("kind") and concept_convert.wanted(mode, src_kind["kind"]):
        conv = concept_convert.convert(run, concept, inputs, mode, src_kind["kind"], cli=getattr(opts, "codex_cli", None))
        if conv.get("used"):
            concept = run.path(conv["concept_file"])
            background = "transparent"
            if notext is not None or notext_skip:
                notext_skip = None
                conv["inputs_notext_ignored"] = "the inputs concept_notext belongs to the original concept — the converted text-free concept replaces it"
            nt = conv.get("notext") or {}
            notext = run.path(nt["file"]) if nt.get("used") else None
    elif mode != "off":
        conv = {"used": False, "mode": mode, "source_kind": src_kind.get("kind"),
                "reason": "the concept already has real alpha" if src_kind.get("kind") == "transparent"
                else f"concept_convert {mode} does not convert a {src_kind.get('kind')} concept"}
    try:
        fit = _fit_reference(concept, run.path("reference.png"), resolution, background, notext=notext)
    except (OSError, ValueError) as exc:
        raise StageError("INPUT_UNREADABLE", f"{concept}: {exc}") from exc
    if notext_skip:
        fit["background"]["notext"] = {"used": False, "reason": notext_skip}
    if conv is not None:
        fit["background"]["convert"] = conv
    font = inputs.get("font") or (run.cfg.get("fonts") or {}).get("default_family")
    dynamic = []
    for d in inputs["data"]:
        e = {k: d[k] for k in ("id", "type", "widget", "widget_type") }
        for k in ("format", "sample", "desc"):
            if k in d:
                e[k] = d[k]
        dynamic.append(e)
    brief = {"schema_version": 1, "run_id": run.run_id, "mode": "concept", "screen_type": inputs["screen_type"], "screen_id": inputs["screen_id"],
             "resolution": resolution, "language": inputs.get("language", "ko"), "font": font, "text": inputs.get("text", ""),
             "required_elements": inputs["required_elements"], "dynamic_data": dynamic, "static_text": inputs.get("static_text", []),
             "style_keywords": inputs.get("style_keywords", []),
             "references": [{"path": "reference.png", "role": "layout", "role_source": "user"}], "conflicts": [],
             "binding_contract": {"class": "UUserWidget" if screen.get("probe") else f"U{screen['widget']}",
                                  "source": "existing" if screen.get("probe") else "new", "bindings": [d["widget"] for d in inputs["data"]]}}
    schema.require("brief", brief)
    run.write_json("brief.json", brief)
    run.write_json("inputs.json", inputs)
    raw = concept.read_bytes()
    run.write_json("normalize.json", {"schema_version": 1, "mode": "concept", "inputs": src.as_posix(), "concept": concept.as_posix(),
                                      "concept_sha256": hashlib.sha256(raw).hexdigest(), "reference": "reference.png",
                                      **({"original_concept": original.as_posix()} if concept != original else {}), **fit})
    bg = fit["background"]
    nt = bg.get("notext")
    nt_txt = "" if not nt else (f" — text-free concept aligned (shift {nt['shift_px']})" if nt.get("used") else f" — text-free concept not used ({nt.get('reason')})")
    cv = bg.get("convert") or {}
    cv_txt = ""
    if cv.get("used"):
        cv_txt = (f" — converted from a {cv['source_kind']} concept to UI-only real alpha "
                  f"({'cache' if (cv.get('concept') or {}).get('cached') else 'codex'}, codex calls {cv.get('codex_calls', 0)})")
    elif cv.get("fallback"):
        cv_txt = f" — conversion fell back: {cv['fallback']}"
    return (f"concept {concept.name} {fit['src_size'][0]}x{fit['src_size'][1]} → reference {resolution[0]}x{resolution[1]} ({fit['mode']}) — "
            f"background {bg['kind']} ({bg['source']}{', key ' + bg['key_color'] if bg['kind'] == 'flat' else ''}){cv_txt}{nt_txt} — "
            f"{len(dynamic)} bindings, {len(brief['static_text'])} static texts, font {font or 'engine default'}")


def run_hand_spec(run, opts) -> str:
    src = pathlib.Path(opts.spec_dir)
    brief, spec = _load(src / "brief.json"), _load(src / "spec.json")
    for kind, obj in (("brief", brief), ("spec", spec)):
        errs = schema.errors(kind, obj)
        if errs:
            raise StageError("SCHEMA", f"{kind}.json: " + "; ".join(errs[:8]), kind=kind, errors=errs)
    if brief["mode"] != "hand_spec":
        raise StageError("MODE", f"brief.mode '{brief['mode']}' — Phase 1a runs hand_spec only")
    errs = spec_mod.validate_semantics(spec)
    if errs:
        raise StageError("SPEC_INVALID", "; ".join(errs[:8]), errors=errs)
    errs = check_brief_vs_spec(brief, spec)
    if errs:
        raise StageError("BRIEF_SPEC_MISMATCH", "; ".join(errs[:8]), errors=errs)
    brief = {**brief, "run_id": run.run_id}
    run.write_json("brief.json", brief)
    run.write_json("spec.json", spec)
    run.write_json("specs/000.json", spec)
    return f"hand_spec from {src.as_posix()} — {len(spec['widgets'])} widgets, {len(spec.get('assets', []))} assets, {len(spec_mod.bound_widgets(spec))} bindings"
