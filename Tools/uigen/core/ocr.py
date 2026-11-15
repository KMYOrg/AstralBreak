"""구운 글자 검출 — RapidOCR 검출 모델만 (설계 §7 refine · §8-1 '구운 글자', 1b-3 사용자 승인 설치).

[실측 1b-3] rapidocr 3.10.0 은 PP-OCRv6 det/rec small 을 휠 안에 갖고 있다. 설정 기본 Cls(PP-OCRv4)는 번들에 없어 모델 경로를 모두 명시하고
use_cls · use_rec 를 끈다 — 검출 상자(언어 무관)로만 판정한다(중국어 인식 모델은 한글을 못 읽는다). 실행 중 내려받기가 일어나면 실패로 본다.
투명 픽셀은 회색(#808080) 바탕에 합성해 본다(cv2 가 알파를 버리면 투명 부분이 검정 · 쓰레기 색이 된다).
"""
from __future__ import annotations

import functools
import pathlib

ENGINE_NAME = "rapidocr 3.10.0 det PP-OCRv6_det_small"
# [실측 1b-5] codex 금색 장식(끝 캡 · 가운데 장식 · 모서리)의 오검출 점수 0.527 ~ 0.645(7상자) ↔ 진짜 글자 0.704 ~ 0.908(컨셉 속 한글 · 숫자,
# 합성 영문 0.79 · 0.86). 0.5 였을 때 글자 없는 에셋을 두 번씩 다시 만들었다 → 0.7(잠정 — Phase 2 보정). 인식(중국어)은 한글도 장식도 못 읽어 판정에 안 쓴다.
DEFAULT_MIN_SCORE = 0.7
DEFAULT_MIN_AREA_PX = 60


class OcrError(Exception):
    pass


@functools.lru_cache(maxsize=1)
def _engine():
    try:
        import rapidocr
        from rapidocr import RapidOCR
    except ImportError as exc:   # pragma: no cover — requirements.txt
        raise OcrError(f"rapidocr is not installed: {exc}") from exc
    models = pathlib.Path(rapidocr.__file__).parent / "models"
    files = {"Det": models / "PP-OCRv6_det_small.onnx", "Rec": models / "PP-OCRv6_rec_small.onnx", "Cls": models / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"}
    missing = [str(p) for p in files.values() if not p.is_file()]
    if missing:
        raise OcrError(f"bundled OCR models are missing (no runtime download allowed): {missing}")
    params = {"Global.use_cls": False, "Global.use_rec": False, "Global.log_level": "error"}
    params.update({f"{k}.model_path": str(v) for k, v in files.items()})
    return RapidOCR(params=params)


def _rgb_over_gray(rgba):
    """PIL RGBA → numpy RGB(회색 바탕 합성, BGR 순서 — rapidocr 가 cv2 배열을 받는다)."""
    import numpy as np
    from PIL import Image
    bg = Image.new("RGBA", rgba.size, (128, 128, 128, 255))
    rgb = Image.alpha_composite(bg, rgba.convert("RGBA")).convert("RGB")
    return np.asarray(rgb)[:, :, ::-1].copy()


def detect(image, *, min_score: float = DEFAULT_MIN_SCORE, min_area_px: int = DEFAULT_MIN_AREA_PX) -> dict:
    """image = 경로 또는 PIL 이미지. → {boxes:[{box:[x, y, w, h], score}], count, max_score, engine}."""
    from PIL import Image
    im = Image.open(image) if isinstance(image, (str, pathlib.Path)) else image
    arr = _rgb_over_gray(im)
    out = _engine()(arr, use_det=True, use_cls=False, use_rec=False)
    boxes = []
    raw_boxes = getattr(out, "boxes", None)
    raw_scores = getattr(out, "scores", None)
    if raw_boxes is not None:
        for i, b in enumerate(list(raw_boxes)):
            xs, ys = [float(p[0]) for p in b], [float(p[1]) for p in b]
            x, y, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
            score = float(raw_scores[i]) if raw_scores is not None and i < len(raw_scores) else 1.0
            if score >= min_score and w * h >= min_area_px:
                boxes.append({"box": [round(x), round(y), round(w), round(h)], "score": round(score, 3)})
    return {"engine": ENGINE_NAME, "count": len(boxes), "max_score": max((b["score"] for b in boxes), default=0.0), "boxes": boxes[:20],
            "min_score": min_score, "min_area_px": min_area_px}
