"""normalize — 입력을 brief · spec 으로 (설계 §2-2).

1a(hand_spec): 손으로 쓴 brief.json · spec.json 이 든 폴더를 받아 검사하고 run 폴더로 복사한다. analyze 는 건너뛴다(spec 이 이미 있다).
1b(concept): inputs.yaml(schemas/inputs) + 컨셉 PNG → reference.png(기준 해상도로 맞춤) · brief.json. spec 은 analyze 가 만든다.
  - 맞추기: 비율 차이 ≤ 1 % 면 늘림(stretch), 넘으면 가운데 맞춤 + 검은 띠(letterbox) — normalize.json 에 변환을 남긴다.
  - (1b 후속 H) 배경 판정 ⓐ transparent · ⓑ flat · ⓒ scene(inputs concept_background, 기본 auto) — ⓐ ⓑ 는 reference_alpha.png ·
    reference_color.png 를 남기고 refine 의 오리기가 그 알파 · 색을 쓴다(gen/cutout). normalize.json background 에 판정 기록.
  - (1b 후속 H2) inputs concept_notext(같은 컨셉에서 글자만 지운 판 — make_concept --text-free)가 있으면 같은 배경 처리 · 배치로 맞추고 위상 상관으로
    정합해 reference_notext_color.png · reference_notext_alpha.png 를 남긴다(refine 이 글자 구멍만 채우고, 글자 맞춤이 컨셉 획을 잰다).
  - (1b 후속 L-2) concept_source generated_textfree(make_concept --text-free-first — 글자 없이 그린 원본 아트): 원본 아트 = 아트(reference_art_*) ·
    글자 없는 판(reference_notext_*), inputs concept_text_ref(글자 참고판)를 원본 아트에 정합해 글자 획만 옮겨 붙인 그림 = reference*(gen/text_ref).
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


def concept_source(inputs: dict, concept_path) -> dict:
    """1b 후속 K-a → L-2 — {value: generated | external | generated_textfree, from}. inputs concept_source 가 먼저, 없으면 컨셉 옆 concept.json(make_concept
    출처 기록): codex 가 새로 그렸고(edited_from 없음) → generated, 편집(외부 그림 바꾸기) · 기록 없음 → external, `--text-free-first` 원본 아트 → generated_textfree.
    L-2 인데 codex 가 두 번 다 글자를 그렸으면(make_concept 기록 text_free_first.status text_drawn) 글자 든 컨셉 — generated(L-1 길)로 물러난다."""
    v = inputs.get("concept_source")
    side = pathlib.Path(concept_path).with_name("concept.json")
    try:
        rec = json.loads(side.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rec = None
    tff = (rec or {}).get("text_free_first") or {}
    if v == "generated_textfree" or (v is None and tff):
        if tff.get("status") == "text_drawn":
            return {"value": "generated", "from": f"{side.name} (text-free first fell back)",
                    "textfree_fallback": "codex drew text into the text-free art on both tries — the concept is treated as a concept with text (L-1)"}
        return {"value": "generated_textfree", "from": "inputs" if v else f"{side.name} (text-free first)"}
    if v in ("generated", "external"):
        return {"value": v, "from": "inputs"}
    if rec is None:
        return {"value": "external", "from": "no concept.json next to the concept"}
    if rec.get("kind") == "concept" and "codex" in str(rec.get("generator", "")) and not rec.get("edited_from"):
        return {"value": "generated", "from": f"{side.name} (codex generated)"}
    return {"value": "external", "from": f"{side.name} (edited from {rec.get('edited_from')})" if rec.get("edited_from") else side.name}


def _fit_reference(src: pathlib.Path, dst: pathlib.Path, size: list[int], background: str | None = "auto", notext: pathlib.Path | None = None,
                   textfree_art: bool = False, text_ref: pathlib.Path | None = None, text_ref_skip: str | None = None) -> dict:
    """컨셉 → 기준 해상도 RGB PNG. 비율 차이 ≤ 1 % 면 늘리고, 넘으면 가운데 맞춤 + 검은 띠.
    (1b 후속 H) 배경 판정(gen/cutout.classify — ⓐ transparent · ⓑ flat · ⓒ scene, inputs concept_background 가 auto 가 아니면 그것)을 하고,
    ⓐ ⓑ 는 dst 옆에 reference_alpha.png(L — 알파) · reference_color.png(RGB — 곧은 색: ⓐ 는 PNG 색, ⓑ 는 배경색 언믹싱)를 남긴다.
    그때 reference.png 는 곧은 색을 검정 위에 얹은 것(렌더 바탕이 검정 — ⓑ 키가 검정이면 원본과 같다). 띠 자리는 알파 0.
    (1b 후속 L-2) textfree_art = 컨셉이 글자 없이 그린 원본 아트 — ⓐ ⓑ 면 _fit_text_ref 가 원본 아트를 아트 · 글자 없는 판 파일로 남기고, 글자 참고판이
    있으면 정합해 reference* 를 '원본 아트 + 참고판 글자'로 바꾼다(background.textfree)."""
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
    if textfree_art and bg["kind"] != "scene":
        rec["textfree"] = _fit_text_ref(text_ref, dst, src_arr, bg, place, (tw, th), skip=text_ref_skip)
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


# 1b 후속 L-2 — 원본 아트(글자 없이 그린 그림 — 사람이 승인한 픽셀 정답)의 파일 이름. 아트 · 글자 없는 판이 같은 그림이다
ART_FILES = ("reference_art_color.png", "reference_art_alpha.png")
NOTEXT_FILES = ("reference_notext_color.png", "reference_notext_alpha.png")
TEXTREF_FILES = ("reference_textref_color.png", "reference_textref_alpha.png", "reference_textref_paste.png")


def _fit_text_ref(src: pathlib.Path | None, dst: pathlib.Path, concept_arr, bg: dict, place, size, skip: str | None = None) -> dict:
    """1b 후속 L-2 ④ — 원본 아트(지금 dst 옆 reference_color · reference_alpha)를 아트 · 글자 없는 판 파일로 남기고, 글자 참고판(make_concept
    --text-free-first 의 codex 편집)이 있으면 컨셉과 같은 배치 · 배경 처리로 맞춘 뒤 원본 아트에 정합해(gen/text_ref.merge — 참고판을 옮김) 참고판
    글자 획만 원본 아트 위에 옮겨 붙인 그림으로 reference* 를 바꾼다. 검사(이동 · 글자 상자 · 칸 밖 차이)에 떨어지면 reference* = 원본 아트 그대로
    (글자는 사양 — analyze 가 어휘에서). → {"text_ref": 기록, "art": [색, 알파], "notext": [색, 알파]}."""
    import shutil

    import numpy as np
    from PIL import Image
    from gen import cutout, text_ref
    rc, ra = dst.with_name("reference_color.png"), dst.with_name("reference_alpha.png")
    for (s_, d_) in ((rc, ART_FILES[0]), (ra, ART_FILES[1]), (rc, NOTEXT_FILES[0]), (ra, NOTEXT_FILES[1])):
        shutil.copyfile(s_, dst.with_name(d_))
    out = {"art": list(ART_FILES), "notext": list(NOTEXT_FILES)}
    if src is None:
        out["text_ref"] = {"used": False, "reason": skip or "no concept_text_ref — texts come from the spec (analyze picks them from the vocabulary)"}
        return out
    sh, sw = concept_arr.shape[:2]
    with Image.open(src) as im:
        has_a = "A" in im.getbands()
        src_size = list(im.size)
        arr = np.asarray((im.convert("RGBA") if has_a else im.convert("RGB")).resize((sw, sh), Image.Resampling.LANCZOS))
    if bg["kind"] == "flat":
        col, alpha, _ = cutout.flat_unmix(arr[..., :3], bg["key"])
    else:
        col = arr[..., :3].astype(float)
        alpha = arr[..., 3].astype(float) / 255.0 if has_a else concept_arr[..., 3].astype(float) / 255.0
    t_a = np.clip(place(alpha), 0.0, 1.0)
    pm = np.dstack([place(col[..., i] * alpha) for i in range(3)])
    t_col = np.clip(np.where(t_a[..., None] > 1e-4, pm / np.maximum(t_a, 1e-4)[..., None], 0.0), 0, 255)
    with Image.open(rc) as c, Image.open(ra) as a:
        a_col, a_a = np.asarray(c.convert("RGB"), float), np.asarray(a.convert("L"), float) / 255.0
    c_col, c_a, (tw_col, tw_a), rec = text_ref.merge(a_col, a_a, t_col, t_a)
    rec = {"src": src.name, "src_size": src_size, **rec}
    paste = rec.pop("paste", None)
    Image.fromarray(np.clip(tw_col, 0, 255).round().astype(np.uint8), "RGB").save(dst.with_name(TEXTREF_FILES[0]), format="PNG")
    Image.fromarray((np.clip(tw_a, 0, 1) * 255).round().astype(np.uint8), "L").save(dst.with_name(TEXTREF_FILES[1]), format="PNG")
    rec["aligned"] = list(TEXTREF_FILES[:2])
    if rec.get("used"):
        Image.fromarray((paste * 255).astype(np.uint8), "L").save(dst.with_name(TEXTREF_FILES[2]), format="PNG")
        rec["paste_mask"] = TEXTREF_FILES[2]
        Image.fromarray(np.clip(c_col * c_a[..., None], 0, 255).round().astype(np.uint8), "RGB").save(dst, format="PNG")
        Image.fromarray((np.clip(c_a, 0, 1) * 255).round().astype(np.uint8), "L").save(ra, format="PNG")
        Image.fromarray(np.clip(c_col, 0, 255).round().astype(np.uint8), "RGB").save(rc, format="PNG")
    out["text_ref"] = rec
    return out


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
    # 1b 후속 K-a → L-2 — 컨셉 출처(inputs concept_source 가 없으면 컨셉 옆 concept.json — make_concept 출처). generated_textfree = 원본 아트(L-2)
    src_rec = concept_source(inputs, concept)
    l2 = src_rec["value"] == "generated_textfree"
    text_ref, text_ref_skip = None, None
    if l2 and inputs.get("concept_text_ref"):
        if getattr(opts, "concept", None):
            text_ref_skip = "the concept was given on the command line — concept_text_ref belongs to the inputs concept"
        else:
            text_ref = pathlib.Path(inputs["concept_text_ref"])
            if not text_ref.is_absolute():
                text_ref = src.parent / text_ref
            if not text_ref.is_file():
                # 참고판이 없으면(만들기 실패 등) 글자는 사양으로 — 설계 L-2 가드 '실패면 참고판 없이 사양'
                text_ref, text_ref_skip = None, f"concept_text_ref image {inputs['concept_text_ref']} does not exist — texts come from the spec"
    # 글자 없는 판(1b 후속 H — make_concept --text-free) — inputs.yaml 기준 상대 경로. 컨셉을 명령줄로 바꿨으면 그 컨셉의 판이 아니라 쓰지 않는다
    notext, notext_skip = None, None
    if inputs.get("concept_notext") and l2:
        notext_skip = "L-2 — the original art is the text-free plate (concept_notext is not used)"
    elif inputs.get("concept_notext"):
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
        # 1b 후속 J-a — ⓑ 단색 컨셉에 글자 없는 판이 없으면 요소 없는 판만 codex 로 한 번(캐시) — 글자 자리를 줄 보간 대신 판 획으로
        if src_kind.get("kind") == "flat" and notext is None and not notext_skip and not l2 and concept_convert.settings(run.cfg).get("plate_for_flat", True):
            plate = concept_convert.plate_only(run, concept, inputs, cli=getattr(opts, "codex_cli", None))
            conv["plate_only"] = plate
            if plate.get("used"):
                notext = run.path(plate["file"])
    try:
        fit = _fit_reference(concept, run.path("reference.png"), resolution, background, notext=notext, textfree_art=l2, text_ref=text_ref,
                             text_ref_skip=text_ref_skip)
    except (OSError, ValueError) as exc:
        raise StageError("INPUT_UNREADABLE", f"{concept}: {exc}") from exc
    if notext_skip:
        fit["background"]["notext"] = {"used": False, "reason": notext_skip}
    if conv is not None:
        fit["background"]["convert"] = conv
    # 1b 후속 K-a → L-1 — 컨셉 출처. 정답 = 사람이 승인한 그림: 글자 든 컨셉(generated · external)이면 아트 = 컨셉 픽셀, codex 가 다시 그린 글자 없는 판은
    # 글자 획 아래(정답 없는 자리)에만(외부 컨셉 길과 하나). 원본 생성 아트(L-2 generated_textfree — 글자 없이 그린 그림이 승인한 정답)만 아트 모드(role original).
    fit["background"]["concept_source"] = src_rec
    nt0 = fit["background"].get("notext") or {}
    if src_rec["value"] == "generated_textfree":
        tf = fit["background"].pop("textfree", None)
        if tf and fit["background"]["kind"] in ("transparent", "flat"):
            # L-2 — 아트 = 원본 아트(전 화면 픽셀 정답 — 게이지 채움 · 런타임 그림까지 그린 그림: K 의 '요소 없는 판'이 아님 → element_free False),
            # 글자 없는 판 = 같은 원본 아트(글자를 그린 적 없음 → 투명 위 글자 잔상 지우기 안 함 text_residue False), 레퍼런스 = 원본 아트 + 참고판 글자
            tr = tf["text_ref"]
            fit["background"]["text_ref"] = tr
            fit["background"]["notext"] = {"used": True, "role": "original_art", "color": tf["notext"][0], "alpha": tf["notext"][1], "shift_px": [0.0, 0.0],
                                           "text_residue": False, **({"inputs_notext_ignored": notext_skip} if notext_skip else {})}
            fit["background"]["art"] = {"used": True, "role": "original", "color": tf["art"][0], "alpha": tf["art"][1], "element_free": False,
                                        "text_residue": False, "text_ref_used": bool(tr.get("used"))}
        else:
            fit["background"]["art"] = {"used": False, "reason": f"background {fit['background']['kind']} — the original art needs the concept alpha"}
    elif src_rec["value"] == "generated":
        fit["background"]["art"] = {"used": False, "reason": "L-1 — the approved picture is the concept with text: art = concept pixels, the redrawn "
                                    "text-free plate only under glyphs" + ("" if nt0.get("used") else " (no text-free plate aligned)")}
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
             "required_elements": inputs["required_elements"], "dynamic_data": dynamic,
             "static_text": [{"widget": s["widget"], "value": s["value"]} for s in inputs.get("static_text", [])],   # desc(L-2 참고판 칸 설명)는 brief 밖
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
    if (bg.get("art") or {}).get("role") == "original":
        tr = bg.get("text_ref") or {}
        nt_txt = (" — L-2 original text-free art" + (f", text reference aligned (shift {tr.get('shift_px')}, glyph pixels {tr.get('paste_px')})"
                                                     if tr.get("used") else f", no text reference ({tr.get('reason')})"))
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
