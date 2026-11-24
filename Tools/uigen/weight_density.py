"""글꼴 굵기별 획 밀도 재기 (1b 후속 L-2) — pipeline.yaml `fonts.weight_density` 표의 측정 방법. 에디터 · LLM · codex 없음, 파일을 쓰지 않는다.

PIL 로 한글 · 숫자 11 낱말을 24 · 36 · 56 px 로 그려 기하 평균을 내고 그 family 의 regular 로 나눈 비(소수 3 자리)를 JSON 으로 찍는다.
  eff  획 픽셀 / 획 상자의 잉크 있는 열 — 표에 적는 값. 빈 열(낱말 · 글자 사이 틈)을 빼야 자간이 굵기 판정을 안 바꾼다
  box  획 픽셀 / 획 상자 전체 — 예전 정의(비교용)

    Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/weight_density.py

글꼴 파일은 `work/_fonts/<family>/`(git 무시). 글꼴이나 굵기를 더하면 FAMILIES 에 넣고 다시 재서 eff 를 표에 옮긴다.
"""
from __future__ import annotations

import json
import math
import pathlib

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONTS = pathlib.Path(__file__).resolve().parent / "work" / "_fonts"
FAMILIES = {"pretendard": {"regular": "Pretendard-Regular.ttf", "medium": "Pretendard-Medium.ttf", "semibold": "Pretendard-SemiBold.ttf",
                           "bold": "Pretendard-Bold.ttf", "extrabold": "Pretendard-ExtraBold.ttf"},
            "notoserifkr": {"regular": "NotoSerifKR-Regular.otf", "semibold": "NotoSerifKR-SemiBold.otf", "bold": "NotoSerifKR-Bold.otf",
                            "black": "NotoSerifKR-Black.otf"}}
WORDS = ["체인 버스트", "오의 불가", "체인", "돌진 공격", "어빌리티", "링크 어택", "회피", "점프", "4.2", "2/4", "100"]
SIZES = (24, 36, 56)
INK_MIN = 127


def density(path: pathlib.Path, word: str, px: int) -> tuple[float, float]:
    """(획 상자 전체 밀도, 빈 열 뺀 밀도)."""
    font = ImageFont.truetype(str(path), px)
    im = Image.new("L", (px * len(word) + 40, px * 2), 0)
    ImageDraw.Draw(im).text((20, px // 3), word, fill=255, font=font)
    m = np.asarray(im) > INK_MIN
    ys, xs = np.nonzero(m)
    sub = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return float(sub.mean()), float(sub[:, sub.any(axis=0)].mean())


def measure() -> dict:
    out = {}
    for fam, weights in FAMILIES.items():
        rows = {}
        for name, file in weights.items():
            pairs = [density(FONTS / fam / file, word, px) for word in WORDS for px in SIZES]
            rows[name] = tuple(math.exp(sum(math.log(p[i]) for p in pairs) / len(pairs)) for i in (0, 1))
        box0, eff0 = rows["regular"]
        out[fam] = {k: {"box": round(box / box0, 3), "eff": round(eff / eff0, 3)} for k, (box, eff) in rows.items()}
    return out


if __name__ == "__main__":
    print(json.dumps(measure(), ensure_ascii=False, indent=1))
