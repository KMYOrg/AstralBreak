"""정답 묶음(1b 후속 K-b) — 사용자가 사람 눈으로 찾은 결함을 진단이 모두 그 분류로 잡는지. work/_golden/ 이 없으면 건너뛴다(외부 화면 · git 무시)."""
import pytest

import golden


@pytest.mark.skipif(not (golden.GOLDEN / "golden.json").is_file(), reason="work/_golden not present (python golden.py snapshot)")
def test_golden_all_caught():
    res = golden.check()
    missed = [r["name"] for r in res if r["expect"] == "defect" and not r["ok"]]
    assert not missed, f"golden defects missed: {missed}"
    false_pos = [r["name"] for r in res if r["expect"] == "none" and not r["ok"]]
    assert not false_pos, f"golden clean spots flagged: {false_pos}"
    # 1b 후속 L 다음 — 보호 run(지금 잘 나온 끝 run)은 run 전체 오류 0 유지
    broken = [(r["name"], r["n_hits"], r["hits"][:1]) for r in res if r["expect"] == "clean_run" and not r["ok"]]
    assert not broken, f"protected runs now have errors: {broken}"
    assert len(res) == len(golden.ITEMS)


def test_golden_match_rules():
    rec = {"defects": [{"n": 1, "code": "E1", "stage": "texture", "widgets": ["A"], "cause": "smear"},
                       {"n": 2, "code": "E7", "stage": "text", "widgets": ["T"], "causes": ["glow"], "cause": "glow"}],
           "state": {"force_visible_extra": ["G"]}}
    assert golden.matches({"codes": ["E1"], "widgets": ["A"]}, rec)
    assert not golden.matches({"codes": ["E4"], "widgets": ["A"]}, rec)
    assert golden.matches({"widgets": ["T"], "causes": ["glow"]}, rec)
    assert not golden.matches({"widgets": ["T"], "causes": ["size"]}, rec)
    assert golden.matches({"state_extra": ["G"]}, rec) and not golden.matches({"state_extra": ["H"]}, rec)
    # box 를 주면 그 자리와 겹치는 결함만(오류가 아니어야 하는 자리 — expect none)
    rec["defects"][0]["box"] = [100, 100, 8, 6]
    assert golden.matches({"codes": ["E1"], "widgets": ["A"], "box": [95, 95, 10, 10]}, rec)
    assert not golden.matches({"codes": ["E1"], "widgets": ["A"], "box": [120, 95, 10, 10]}, rec)
    assert any(i.get("expect") == "none" for i in golden.ITEMS)
    # 보호 run(expect clean_run) — 결함이 하나라도 있으면 걸림(위젯 · 분류 무관), 진단 건너뜀도 깨짐
    assert golden.matches({"expect": "clean_run"}, rec)
    assert not golden.matches({"expect": "clean_run"}, {"defects": []})
    assert golden.matches({"expect": "clean_run"}, {"skipped": "no render"})
    assert any(i.get("expect") == "clean_run" for i in golden.ITEMS)
    line = golden.summary_line([{"expect": "defect", "ok": True}, {"expect": "none", "ok": True}, {"expect": "clean_run", "ok": False}])
    assert line == "1/1 caught · 1/1 clean · 0/1 protected(errors 0)"
