"""1b 후속 A — 공용 ΔE00(core/color.py). C(외형 검토 라운드)도 같은 함수를 쓴다."""
from __future__ import annotations

import numpy as np
import pytest

from core import color

# Sharma, Wu, Dalal (2005) "The CIEDE2000 color-difference formula" 시험 쌍 중 11개 (Lab1, Lab2, ΔE00)
SHARMA = [
    ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
    ((50.0, 3.1571, -77.2803), (50.0, 0.0, -82.7485), 2.8615),
    ((50.0, 2.8361, -74.0200), (50.0, 0.0, -82.7485), 3.4412),
    ((50.0, -1.3802, -84.2814), (50.0, 0.0, -82.7485), 1.0000),
    ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
    ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
    ((50.0, 2.5, 0.0), (61.0, -5.0, 29.0), 22.8977),
    ((50.0, 2.5, 0.0), (56.0, -27.0, -3.0), 31.9030),
    ((50.0, 2.5, 0.0), (58.0, 24.0, 15.0), 19.4535),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
]


@pytest.mark.parametrize("lab1,lab2,want", SHARMA)
def test_ciede2000_matches_sharma_pairs(lab1, lab2, want):
    assert float(color.delta_e00(np.array(lab1), np.array(lab2))) == pytest.approx(want, abs=1e-4)
    assert float(color.delta_e00(np.array(lab2), np.array(lab1))) == pytest.approx(want, abs=1e-4)     # 대칭


def test_srgb_to_lab_anchor_points():
    lab = color.srgb_to_lab(np.array([[255, 255, 255], [0, 0, 0], [128, 128, 128]]))
    assert lab[0] == pytest.approx([100.0, 0.0, 0.0], abs=0.02)
    assert lab[1] == pytest.approx([0.0, 0.0, 0.0], abs=1e-6)
    assert lab[2][0] == pytest.approx(53.59, abs=0.05) and abs(lab[2][1]) < 0.02 and abs(lab[2][2]) < 0.02


def test_region_delta_e_representative_and_pixel():
    a = np.zeros((10, 10, 3), np.uint8)
    a[:] = (232, 181, 74)
    b = a.copy()
    b[:, 5:] = (30, 20, 12)
    m = np.zeros((10, 10), bool)
    m[:, :5] = True
    same = color.region_delta_e(a, b, m)
    assert same["representative"] == 0.0 and same["pixel"] == {"mean": 0.0, "p95": 0.0} and same["n_a"] == 50
    whole = color.region_delta_e(a, b, np.ones((10, 10), bool))
    assert whole["pixel"]["p95"] > 50 and whole["representative"] is not None
    # 다른 격자(크기) — 대표색만
    other = color.region_delta_e(a, b[:5, :5], m, np.ones((5, 5), bool))
    assert other["pixel"] is None and other["representative"] == 0.0
    assert color.region_delta_e(a, b, np.zeros((10, 10), bool))["representative"] is None
