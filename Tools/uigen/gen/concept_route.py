"""받은 컨셉에 글자가 있는지 OCR 로 보고 길(L-1 · L-2)을 고른다 (L-2 기본 전환, 11-23 — 설계 §11).

검출 한 번(0.7)으로는 못 가른다 — 글자 없는 그림의 장식이 0.72 ~ 0.76 으로 잡힌다 [실측 조작 안내 글자 없는 판 0.76 · 빈 동그라미 칸 둘 0.76].
장식 오검출은 배율을 바꾸면 흔들리고(0.76 → 0.64) 글자는 그대로다(0.85 → 0.83). 그래서 점수 = 원래 크기와 2 배 크기에서 **같은 자리(IoU ≥ 0.3)에 다시 잡힌
상자의 낮은 쪽 점수**, 바탕 셋(회색 · 검정 · 흰 — 투명 그림만)의 최대. 글줄 하나로 보기엔 너무 높은 상자(그림 높이의 MAX_BOX_H 넘음)는 뺀다 — 막대 여러 줄을
한 글자 덩어리로 본 것 [실측 '검은 날' 시안 파티 막대 네 줄 396 × 412 px 0.80]. [실측 11-23] 글자 있는 그림 0.82 ~ 0.89 ↔ 글자 없는 그림 0 ~ 0.69.
  ≥ TEXT_MIN  글자 있음 → L-1     ≤ FREE_MAX  글자 없음 → L-2     그 사이  모호 → L-1
모호를 L-1 로 보내는 까닭: 글자 든 그림을 L-2 로 보내면 텍스처에 구워진 글자가 '정답'이 되어 진단이 못 본다. 반대 오판은 지울 글자가 없을 뿐이다.
"""
from __future__ import annotations

import pathlib

TEXT_MIN = 0.78
FREE_MAX = 0.70
SCALES = (1, 2)
IOU_MIN = 0.3
MAX_BOX_H = 0.2
DET_MIN = 0.4                # 기록 · 짝짓기용 검출 문턱(판정은 위 둘)
BACKDROPS = {"gray": (128, 128, 128), "black": (0, 0, 0), "white": (255, 255, 255)}
MAX_SIDE = 4096              # 2 배로 키운 그림의 긴 변 상한(큰 그림은 덜 키움 — 배율 차만 있으면 된다)


def _iou(a, b) -> float:
    iw = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    ih = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = iw * ih
    return inter / max(1e-6, a[2] * a[3] + b[2] * b[3] - inter)


def _has_alpha(im) -> bool:
    if "A" not in im.getbands() and "transparency" not in im.info:
        return False
    return im.convert("RGBA").getchannel("A").getextrema()[0] < 255


def text_score(image, detect=None) -> dict:
    """image = 경로 또는 PIL 이미지 → {"score", "boxes"(점수 순, 두 배율에서 다시 잡힌 것), "per_backdrop"}."""
    from PIL import Image
    if detect is None:
        from core import ocr
        detect = ocr.detect
    if isinstance(image, (str, pathlib.Path)):
        with Image.open(image) as im0:
            im = im0.convert("RGBA") if _has_alpha(im0) else im0.convert("RGB")
    else:
        im = image
    drops = BACKDROPS if _has_alpha(im) else {"opaque": None}
    boxes, per = [], {}
    for name, bg in drops.items():
        flat = im.convert("RGB") if bg is None else Image.alpha_composite(Image.new("RGBA", im.size, (*bg, 255)), im.convert("RGBA")).convert("RGB")
        found = []
        for k in SCALES:
            f = flat
            if k != 1:
                z = min(float(k), MAX_SIDE / max(flat.size))
                f = flat.resize((max(1, round(flat.width * z)), max(1, round(flat.height * z))), Image.Resampling.LANCZOS)
            sx, sy = f.width / flat.width, f.height / flat.height
            det = detect(f, min_score=DET_MIN, max_boxes=200)
            found.append([{"box": [b["box"][0] / sx, b["box"][1] / sy, b["box"][2] / sx, b["box"][3] / sy], "score": float(b["score"])}
                          for b in det.get("boxes") or []])
        keep = []
        for b in found[0]:
            if b["box"][3] > MAX_BOX_H * flat.height:
                continue
            scores = [b["score"]]
            for other in found[1:]:
                m = [o["score"] for o in other if _iou(b["box"], o["box"]) >= IOU_MIN]
                if not m:
                    scores = []
                    break
                scores.append(max(m))
            if scores:
                keep.append({"box": [round(v) for v in b["box"]], "score": round(min(scores), 3), "scores": [round(v, 3) for v in scores], "backdrop": name})
        per[name] = round(max((b["score"] for b in keep), default=0.0), 3)
        boxes += keep
    boxes.sort(key=lambda b: -b["score"])
    uniq: list[dict] = []
    for b in boxes:                                        # 바탕마다 같은 글자 — 점수 높은 것 하나만
        if not any(_iou(b["box"], u["box"]) >= IOU_MIN for u in uniq):
            uniq.append(b)
    return {"score": max(per.values(), default=0.0), "boxes": uniq[:20], "per_backdrop": per}


def judge(image, detect=None) -> dict:
    """→ text_score + {"decision": text | text_free | ambiguous, "thresholds"}. 판정은 글자 없음 ≤ FREE_MAX < 모호 < TEXT_MIN ≤ 글자 있음."""
    r = text_score(image, detect)
    r["decision"] = "text" if r["score"] >= TEXT_MIN else "text_free" if r["score"] <= FREE_MAX else "ambiguous"
    r["thresholds"] = {"text_min": TEXT_MIN, "free_max": FREE_MAX}
    return r


def text_boxes(image, detect=None) -> list[dict]:
    """글자로 볼 상자(모호 포함 — 글자 없이 그리기 검사 · 길 고르기와 같은 쪽으로 엄격하게)."""
    return [b for b in text_score(image, detect)["boxes"] if b["score"] > FREE_MAX]
