"""정답 묶음(골든 세트, 1b 후속 K-b) — 사용자가 사람 눈으로 찾은 결함을 run 사본 + 위젯 + 기대 분류로 모아, 진단(gen/diagnose)이 늘 그 분류로 잡는지 본다.
문턱 · 측정을 바꾸면 이 묶음으로 다시 잰다(몇 장에 맞추는 보정을 끊는다). 외부 화면이 섞여 git 무시 work/_golden/ — 시험은 없으면 건너뛴다.

  python golden.py snapshot   # work/ 의 원본 run 에서 진단에 필요한 파일만 work/_golden/<run>/ 로 복사(이미 있으면 건너뜀) + golden.json
  python golden.py check      # 묶음 전부 진단 → 항목마다 잡힘 / 놓침, '오류 아님' 항목(expect none)은 깨끗함 / 거짓 양성,
                              # 보호 run(expect clean_run — 잘 나온 끝 run 은 run 전체 오류 0 유지)은 유지 / 깨짐
"""
from __future__ import annotations

import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent
WORK = ROOT / "work"
GOLDEN = WORK / "_golden"

# 사용자가 찾은 결함(설계 §11 K-b 목록) — match: widgets 중 하나가 결함 widgets 에 있고 code 가 codes 중 하나(글자는 causes 중 하나)
ITEMS = [
    {"name": "배지 양옆 선", "run": "R20261117_154442_ProbeControlGuide", "codes": ["E1", "E5"], "widgets": ["EKeyBadge", "TKeyBadge"], "found": "11-17 I 후속"},
    {"name": "다이아몬드 이중", "run": "R20261117_154442_ProbeControlGuide", "codes": ["E4"], "widgets": ["SkillDiamondOverhang"], "found": "11-17 I 후속"},
    {"name": "'돌진 공격' 어긋남", "run": "R20261117_154442_ProbeControlGuide", "widgets": ["DashLabelText"], "causes": ["position"], "found": "11-17 I 후속"},
    {"name": "왼쪽 라벨 굵게 + 남색 외곽선", "run": "R20261117_154442_ProbeControlGuide", "widgets": ["AttackLabelText"], "causes": ["weight", "outline"],
     "found": "11-17 I 후속"},
    {"name": "'회피' 작아짐", "run": "R20261117_154442_ProbeControlGuide", "widgets": ["DodgeLabelText"], "causes": ["size"], "found": "11-17 I 후속"},
    {"name": "'어빌리티' 작음", "run": "R20261117_095249_ProbeControlGuide", "widgets": ["AbilityLabelText"], "causes": ["size"], "found": "11-17 H3"},
    {"name": "게이지 끝 조각", "run": "R20261117_134535_CombatHUD", "codes": ["E1"], "widgets": ["UltGauge"], "found": "11-17 J-b 진단"},
    {"name": "0 % 트랙", "run": "R20261117_192631_ProbePartyHUD", "codes": ["E1"], "widgets": ["StaticPlate2", "StaticPlate3", "StaticPlate4"], "found": "11-17 J"},
    {"name": "HP 화살 끝 · 막대 위 구멍", "run": "R20261117_192631_ProbePartyHUD", "codes": ["E1", "E4"], "widgets": ["HpGauge"], "found": "11-17 J"},
    {"name": "이름 자리 구멍", "run": "R20261117_192631_ProbePartyHUD", "codes": ["E1"], "widgets": ["NameText"], "found": "11-17 J"},
    {"name": "'공격' 얼룩", "run": "R20261117_214030_ProbeControlGuide", "codes": ["E1"], "widgets": ["AttackLabelText"], "found": "11-17 밤 J 남은 일 사람 눈"},
    {"name": "'돌진 공격' 빛", "run": "R20261117_214030_ProbeControlGuide", "widgets": ["DashLabelText"], "causes": ["glow"], "found": "11-17 밤 J 남은 일 사람 눈"},
    {"name": "'어빌리티' 굵음", "run": "R20261117_214030_ProbeControlGuide", "widgets": ["AbilityLabelText"], "causes": ["weight"], "found": "11-17 밤 J 남은 일 사람 눈"},
    {"name": "게이지 뒤 금빛(상태)", "run": "R20261117_214505_CombatHUD", "state_extra": ["UltReadyGlow"], "found": "11-17 밤 J 남은 일 사람 눈 — render.png 가 숨은 빛을 켬"},
    {"name": "'오의 불가' 자리 판 잔상 · 상태 오판", "run": "R20261117_235644_CombatHUD", "codes": ["E8", "E4", "E1"], "widgets": ["UltBlockedText", "StaticPlate6"],
     "found": "11-18 K compare.png 눈 확인 — 아트(글자 없는 판)가 투명 위 붉은 글자를 얼룩으로 남겨 렌더에서 글자가 빠짐"},
    {"name": "'2/4' 패널 테두리선 겹침", "run": "R20261118_010950_CombatHUD", "widgets": ["ChainCountText"], "causes": ["unmeasured", "position"],
     "found": "11-18 K compare.png 눈 확인 — 렌더 '2/4' 가 내려가 패널 아래 금선과 겹침, 진단은 '모양 근사'로 넘겼음"},
    # 1b 후속 L-1 — K (가) 가 codex 가 다시 그린 글자 없는 판을 아트 정답으로 삼아 생긴 색 · 빛 차(진단도 판과 비교해 못 봄). 컨셉 비교 진단은 '컨셉보다 불투명'(E4) ·
    # 얼룩(E1)으로 잡는다 [실측 L-1 — 판 ↔ 컨셉 배너 국소 상위 5 % 10.5]
    {"name": "게이지 테두리 둘레 빛", "run": "R20261118_003804_CombatHUD", "codes": ["E1", "E4"], "widgets": ["UltGauge", "StaticPlate6"],
     "found": "11-18 사용자 사람 눈 — K 원래 전투 HUD, 판이 다시 그린 게이지 테두리 빛"},
    {"name": "버스트 배너 · 체인 패널 상자 색", "run": "R20261118_003804_CombatHUD", "codes": ["E1", "E4"], "widgets": ["BurstBanner", "ChainPanel"],
     "found": "11-18 사용자 사람 눈 — K 원래 전투 HUD, 판이 바꾼 배너 · 패널 색조"},
    # 1b 후속 L-2 — 둘 다 빛나면 세기는 근사로만 봤다: 빛 색 알파를 더 낮출 수 있는데 렌더 빛이 더 셈(띠 밝기 30.7 ↔ 42.7) → E9 '가장 가까운 선택 아님'
    {"name": "'오의 불가' 빛 세기", "run": "R20261118_142524_CombatHUD", "widgets": ["UltBlockedText"], "causes": ["glow_strength"],
     "found": "11-18 사용자 판단 — L-2 compare.png, 렌더 빛이 더 세고 붉음"},
    # 오류가 아니어야 하는 자리(expect none) — 진단 거짓 양성이 다시 나지 않게. box 와 겹치는 결함만 센다(같은 글자의 다른 정상 결함과 섞이지 않게)
    {"name": "'체인' ㄴ 받침 바탕 얼룩(거짓 양성)", "run": "R20261118_175104_CombatHUD", "expect": "none", "codes": ["E1"],
     "widgets": ["ChainTitleText", "ChainTimerText"], "box": [1729, 208, 24, 20],
     "found": "11-18 L-1 run — 빛 여백으로 넓은 '4.2' core 가 '체인' 아래와 겹쳐 '인' ㄴ 받침 오른쪽 반이 '4.2' 몫 → 걸러져 바탕 E1 27(실제는 글자 획)"},
    # 1b 후속 L 다음 — 외부 · 단색 입력 사람 눈(11-18 L 끝 run 뒤, 인계 uigen-L2-handoff '사용자 사람 눈 · 결정'). 자리는 각 run compare.png 로 확인
    {"name": "'2/4' '4' 밑 잔상", "run": "R20261118_120715_CombatHUD", "codes": ["E1"], "widgets": ["ChainCountText"], "box": [1723, 282, 13, 10],
     "found": "11-18 사용자 사람 눈 — 단색, 텍스처가 컨셉 '4' 발 오른쪽 끝을 남김(렌더 '4' 가 안 덮음). 진단은 '오류 0' 이었음 — 글자 구역 바탕 검사가 "
              "렌더 획 + 2 px 를 빼 사각지대(국소 최대 9.78) → E1 획에 붙은 잔상(glyph_residue) [1727, 286, 5, 3] 11 px · 평균 ΔE00 31.3"},
    {"name": "'2/4' 아래 금선 위 혹", "run": "R20261118_124503_CombatHUD", "codes": ["E1"], "widgets": ["ChainCountText"], "box": [1675, 295, 13, 9],
     "found": "11-18 사용자 사람 눈 — 단색, refine 판 메우기(same_struct 로 지킨 금선 자리 + 획 3 px 경계)가 남긴 밝은 혹, 글자 구역 바탕 E1 [1677, 297, 9, 5]"},
    {"name": "'2/4' 위치(커져 내려가 금선에 걸림)", "run": "R20261118_124503_CombatHUD", "widgets": ["ChainCountText"], "causes": ["position"],
     "found": "11-18 사용자 사람 눈 — 단색, '2/4' 가 커지고 내려가 패널 아래 금선에 걸림(E6 position — 중심 차 (3.5, 3.0) · 허용 3.3)"},
    {"name": "'0 %' 위치", "run": "R20261118_130201_ProbePartyHUD", "widgets": ["LinkPercentText"], "causes": ["position"],
     "found": "11-18 사용자 사람 눈 — 파티, '0 %' 가 아래로(E6 position — 중심 차 (−1.5, −10.0) · 허용 3.5)"},
    {"name": "'Lv 100' — '100' 검정 · 1.5 배(컨셉 획 측정 실패)", "run": "R20261118_130201_ProbePartyHUD", "widgets": ["LevelText"], "causes": ["unmeasured"],
     "found": "11-18 사용자 사람 눈 'Lv 100 텍스트 아쉬움' — 실측: 'Lv' 위치 차 (+0.5, +2.0) · 허용 3.2(기준 안 — 항목 아님, 사용자 결정), '100' 은 컨셉 획 마스크가 "
              "번진 파란 상자의 어두운 틈을 글자로 재(대비 0.5) 글자 맞춤이 검정 · 40 → 52 로 바꿈, 진단은 색 차 0.37 '같음' → 대비 안전망 E6 unmeasured"},
    # 1b 후속 L 다음 고침 — 이 세션 compare.png 확인(사람 눈 전): 새 analyze 상자에서 판 메우기 글자색 추정이 띠 색으로 잡혀 텍스처에 컨셉 글자가 남고 엔진 글자가
    # 겹침(이중). 진단은 컨셉 획(컨셉 ↔ 텍스처 차)이 비어 건너뛰었다(오류 0) → E1 baked
    {"name": "'돌진 공격' 이중 글자(텍스처에 컨셉 글자 남음)", "run": "R20261119_004119_ProbeControlGuide", "codes": ["E1"], "widgets": ["DashLabelText"],
     "causes": ["baked"], "found": "11-19 L 다음 고침 controls_alpha run compare.png — 진단 오류 0 이었음(컨셉 획 빈 글자 건너뜀)"},
    # 1b 후속 L 다음 — 상태 렌더 검증(gen/state_check): 컨셉 한 상태만 보고 정한 픽셀 주인 · 다른 상태 추측. 진단은 컨셉 상태 하나를 검정 바탕에서만 봐 '오류 0'
    {"name": "'오의 불가' 숨김 흔적(판 회색 둥근 상자 · 어두운 덩어리)", "run": "R20261119_091634_CombatHUD", "codes": ["E8"], "widgets": ["UltBlockedText"],
     "checks": ["hidden_trace"], "found": "11-19 사용자 인게임(M4 C 승격 HUD) — 시작 때 숨는 '오의 불가' 자리 판5 에 남은 메움(아래 게이지 트랙을 원천으로 끌어옴). "
                                          "글자를 켠 컨셉 상태 렌더에선 글자가 덮고, 회색 합성은 글자 상자를 빼 못 봤다"},
    {"name": "게이지 100 % 끝 어두운 사각형(채움 번짐이 트랙 밖)", "run": "R20261119_091634_CombatHUD", "codes": ["E8"], "widgets": ["UltGauge"],
     "checks": ["gauge_outside"], "found": "11-19 사용자 인게임 — concept 채움 번짐 24 px(알파 1, 빈 트랙 색)이 100 % 에서 트랙 끝을 넘어 끝 장식을 덮음(70 % 미리보기는 빈 트랙 위라 같음)"},
    # 1b 후속 L 다음 L-1 글자 완전 지우기 — 사용자 눈(144231 compare.png · 인게임 판단): 좁은 글자 메움 경계 · 컨셉 70 % 진행 끝을 그대로 쓴 채움 오른쪽 여백.
    # 컨셉 상태 렌더에선 엔진 글자 · 빛과 컨셉 진행률이 그 자리를 덮어 진단 '오류 0'
    {"name": "'4.2' 빛 윤곽(글자 밑 흔적)", "run": "R20261119_144231_CombatHUD", "codes": ["E8"], "widgets": ["ChainTimerText"], "checks": ["text_trace"],
     "found": "11-19 사용자 눈 — 체인 패널 텍스처에 '4.2' 빛 바깥 테두리가 주황 윤곽으로(값이 바뀌면 보임). 메움 경계 고리 — 텍스처가 판보다 L 6 넘게 밝은 픽셀 2 466"},
    {"name": "게이지 100 % 오른쪽 끝이 끝 장식 호를 덮음", "run": "R20261119_144231_CombatHUD", "codes": ["E8"], "widgets": ["UltGauge"], "checks": ["gauge_end_cover"],
     "found": "11-19 사용자 눈 — 100 % 오른쪽 끝이 곧은 세로 테두리(컨셉 70 % 진행 끝)로 끝나 끝 장식 안쪽 호를 덮음. S2 는 트랙 상자 밖만 봐 못 봤다"},
    {"name": "'4.2' 획 잔상(투명 위 글자 길로 빠짐)", "run": "R20261119_143110_CombatHUD", "codes": ["E1"], "widgets": ["ChainTimerText"],
     "found": "11-19 상태 렌더 검증 단위 — analyze 가 '4.2' 에 빛 7 · 상자 331 px 를 줘 오리기 글자 메움이 '투명 위 글자' 둘레 메움으로 가 획을 놓침(E1 잔상 8)"},
    # 1b 후속 L 다음 — 글자 지우기 마감: L-1 결과 run 사용자 눈(11-19). S4(3 × 3 > 5)는 가는 윤곽 · 어두운 판의 낮은 대비 흔적을 못 봤다
    {"name": "'4' 옅은 안쪽 윤곽(가는 선)", "run": "R20261119_190059_CombatHUD", "codes": ["E8"], "widgets": ["ChainTimerText"], "checks": ["text_contour"],
     "found": "11-19 사용자 눈 — 빈 값 체인 패널 2 배 확대 '4' 윤곽. 원인 = 판 구조물 지킴(same_struct)이 자리 안에 갇힌 codex 판의 덜 지운 '4' 흔적을 지켜 컨셉 빛 "
              "테두리가 남음(385 px) + 섞임 띠의 판 색. 3 × 3 국소 3.1(문턱 5 아래) → 가는 선 골격 87 px"},
    {"name": "배너 '체인 버스트' · '3' 글자 모양 얼룩(낮은 대비 — 기록 지표)", "run": "R20261119_190059_CombatHUD", "widgets": ["BurstLabelText", "BurstCountText"],
     "lift_min": 4.0, "found": "11-19 사용자 눈 — 배너 텍스처(텍스처째 숨는 위젯)의 좁은 판 메움 경계 · 남은 어두운 외곽 그림자. 어두운 판(L* ≈ 9)이라 ΔE00 1.5 — 게이트 "
                                  "S4 문턱 아래, 밝힌 검정(× 3, 기록만) 4.5 · 깨끗한 L-2 0.5"},
    {"name": "파티 '0 %' 어두운 '0' 테두리 · 구멍", "run": "R20261119_003127_ProbePartyHUD", "codes": ["E8"], "widgets": ["LinkPercentText"],
     "checks": ["text_trace", "text_contour"], "found": "11-19 사용자 눈 — 판 중앙값 메움이 '0' 테두리를 남기고 안쪽을 어둡게 비움(S4 34.7 ~ 50 · 가는 선 283)"},
    # 1b 후속 L 다음 — 글자 지우기 다음(11-20 사용자 눈 — 마감 결과 run): 판정 사각 둘
    {"name": "파티 HP 숫자 막대 윗선 위 빛 자국(판에 없는 선)", "run": "R20261120_005215_ProbePartyHUD", "codes": ["E8"], "widgets": ["HpCurrentText"],
     "checks": ["text_trace"], "found": "11-20 사용자 눈 — 글자 빈 값 파티 텍스처에서 HP 막대 테두리가 깨끗하지 않음. 막대 윗선 약 5 px 위 녹색 빛 반원 22 × 2(7.1)가 "
                                         "'짧은 변 ≤ 2 px = 구조선' 규칙으로 기록만 → V2(판에도 있는 선만 구조선)로 결함"},
    {"name": "L-1 배너 글자 자리 점(harmonic 경계 잡티 — 기록 지표)", "run": "R20261119_235452_CombatHUD", "widgets": ["BurstLabelText"], "lift_min": 3.0,
     "found": "11-20 사용자 눈 — 배너 텍스처 글자 지운 자리 작은 어두운 점들(× 3 밝힘). 엔진 S4 1.6 · 합성 밝힌 검정 3.41(덩어리 < 24 px 라 V3 오류 문턱 아래) — "
              "기록 지표로 지키고 V4(경계 잡티 빼기)로 고침"},
    # 보호 — 지금 잘 나온 끝 run 은 run 전체 오류 0 유지(expect clean_run — 결함 하나라도 나오면 깨짐). 외부 · 단색 입력 규칙을 고치다 L-2 와 그 뒤 고친 것이
    # 다시 꼬이지 않게 [L-1 · L-3 교훈 — 판 메우기 규칙 하나를 고칠 때마다 다른 입력 · 다른 글자에서 새 결함]
    {"name": "보호: L-2 원래 전투 HUD", "run": "R20261118_191532_CombatHUD", "expect": "clean_run",
     "found": "11-18 L-2 확인 run — 오류 0 · 근사 2(진단 거짓 양성 E1 고침 뒤)"},
    {"name": "보호: L-1 원래 전투 HUD", "run": "R20261118_184602_CombatHUD", "expect": "clean_run",
     "found": "11-18 진단 거짓 양성 E1 고침 끝 run — 오류 0 · 근사 0"},
    {"name": "보호: controls_alpha", "run": "R20261118_180405_ProbeControlGuide", "expect": "clean_run",
     "found": "11-18 L-2 회귀 run — 오류 0"},
    {"name": "보호: controls", "run": "R20261118_125054_ProbeControlGuide", "expect": "clean_run",
     "found": "11-18 L-3 끝 run — 지금 코드 오프라인 재진단 오류 0"},
    # 1b 후속 L 다음 고침 끝 run(11-19) — 외부 · 단색 입력이 처음으로 오류 0
    {"name": "보호: 단색 전투 HUD", "run": "R20261119_001742_CombatHUD", "expect": "clean_run", "found": "11-19 L 다음 고침 — 오류 0 · 근사 3"},
    {"name": "보호: 파티 HUD", "run": "R20261119_003127_ProbePartyHUD", "expect": "clean_run", "found": "11-19 L 다음 고침 — 오류 0 · 근사 10"},
    {"name": "보호: 조작 안내 원본", "run": "R20261119_003647_ProbeControlGuide", "expect": "clean_run", "found": "11-19 L 다음 고침 — 오류 0 · 근사 3"},
    {"name": "보호: L-2 원래 전투 HUD(글자 지우기 마감 끝)", "run": "R20261120_004053_CombatHUD", "expect": "clean_run",
     "found": "11-20 글자 지우기 마감 L-2 run — 오류 0 · 근사 3, 끝 덮개(UltGaugeEndCap) 포함"},
]
FILES = ["spec.json", "geometry.json", "manifest.json", "normalize.json", "reference.png", "reference_color.png", "reference_alpha.png", "render.png",
         "refine.json", "specs/000.json"]


def snapshot(items=ITEMS) -> list[str]:
    done = []
    for run in sorted({i["run"] for i in items}):
        src, dst = WORK / run, GOLDEN / run
        if dst.is_dir():
            continue
        if not src.is_dir():
            raise SystemExit(f"source run missing: {src}")
        files = list(FILES)
        norm = json.loads((src / "normalize.json").read_text(encoding="utf-8"))
        nt = (norm.get("background") or {}).get("notext") or {}
        files += [nt[k] for k in ("color", "alpha") if nt.get("used") and nt.get(k)]
        art = (norm.get("background") or {}).get("art") or {}
        files += [art[k] for k in ("color", "alpha") if art.get("used") and art.get(k)]       # 1b 후속 L-2 — 원본 아트(아트 모드 진단)
        man = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
        files += [a["file"] for a in man.get("assets", []) if a.get("file")]
        for f in files:
            if (src / f).is_file():
                (dst / f).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src / f, dst / f)
        done.append(run)
    GOLDEN.mkdir(parents=True, exist_ok=True)
    (GOLDEN / "golden.json").write_text(json.dumps({"schema_version": 1, "items": items}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return done


def _overlap(a, b) -> bool:
    return bool(a and b) and a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def matches(item: dict, rec: dict) -> list[dict]:
    if item.get("expect") == "clean_run":
        # 보호 run — 결함 하나하나가 '걸림'(위젯 · 분류 가리지 않음). 진단을 못 하면(건너뜀) 그것도 깨짐.
        # 1b 후속 L 다음 — 상태 검사(check 키 — S1 숨김 흔적 · S2 게이지 끝)가 오류로 올라 그 run 자기 텍스처에서 찾은 결함은 회귀가 아니라 그 run 에 있던 같은 종류
        # 결함이라 보호 판정에서 빼고 따로 센다(state_protected_hits — check 출력 · summary_line 에 표시)
        if rec.get("skipped"):
            return [{"skipped": rec["skipped"]}]
        return [{k: d.get(k) for k in ("n", "code", "stage", "cause", "box", "widgets")} for d in rec.get("defects") or [] if not d.get("check")]
    if item.get("state_extra"):
        extra = set((rec.get("state") or {}).get("force_visible_extra") or [])
        return [{"state": sorted(extra)}] if set(item["state_extra"]) <= extra else []
    out = []
    # 1b 후속 L 다음 — 상태 검사(S1 · S2)가 기록만(record)일 때도 그 발견으로 잡힘을 본다(오류 모드면 이미 defects 에 있다). 보호 run(위)은 오류만 센다
    sc = rec.get("state_checks") or {}
    if item.get("lift_min") is not None:
        # 글자 지우기 마감 — 게이트 문턱 아래 낮은 대비 흔적: S4 '밝힌 검정'(기록만) 국소 최대가 이 이상이면 잡힘(오류가 아니라 기록 지표로 지킴)
        for t in (sc.get("text_trace") or {}).get("texts") or []:
            v = (t.get("local_max") or {}).get("lift")
            if t.get("widget") in (item.get("widgets") or []) and v is not None and v >= float(item["lift_min"]):
                out.append({"widget": t["widget"], "lift": v, "state": t.get("state")})
        return out
    # 오류 모드에서도 기록만인 새 검사(appearance.state_record_only — record_only 표시)의 발견도 잡힘으로 본다
    extra = [f for f in sc.get("findings") or [] if sc.get("mode") != "error" or f.get("record_only")]
    for d in list(rec.get("defects") or []) + extra:
        if not set(item.get("widgets") or []) & set(d.get("widgets") or []):
            continue
        if item.get("checks") and d.get("check") not in item["checks"]:
            continue
        if item.get("box") and not _overlap(item["box"], d.get("box")):
            continue
        if item.get("causes") and not set(item["causes"]) & set(d.get("causes") or []):
            continue
        if item.get("codes") and d.get("code") not in item["codes"]:
            continue
        out.append({k: d.get(k) for k in ("n", "code", "stage", "cause", "box")})
    return out


def check(cfg=None) -> list[dict]:
    from core import config
    from gen import diagnose
    cfg = cfg or config.load_pipeline()
    doc = json.loads((GOLDEN / "golden.json").read_text(encoding="utf-8"))
    recs, res = {}, []
    for it in doc["items"]:
        if it["run"] not in recs:
            recs[it["run"]] = diagnose.diagnose(GOLDEN / it["run"], None, cfg, pictures=False)
        hit = matches(it, recs[it["run"]])
        exp = it.get("expect") if it.get("expect") in ("none", "clean_run") else "defect"
        row = {"name": it["name"], "run": it["run"], "expect": exp, "caught": bool(hit),
               "ok": bool(hit) if exp == "defect" else not hit, "hits": hit[:3], "n_hits": len(hit)}
        if exp == "clean_run":
            st = [{k: d.get(k) for k in ("check", "widgets", "box", "max_de")} for d in recs[it["run"]].get("defects") or [] if d.get("check")]
            if st:
                row["state_hits"] = st
        res.append(row)
    return res


TAGS = {"defect": ("caught ", "MISSED "), "none": ("clean  ", "FALSE+ "), "clean_run": ("kept0  ", "BROKEN ")}


def summary_line(rs: list[dict]) -> str:
    part = {e: [r for r in rs if r["expect"] == e] for e in TAGS}
    st = [r for r in part["clean_run"] if r.get("state_hits")]
    return (f"{sum(r['ok'] for r in part['defect'])}/{len(part['defect'])} caught · {sum(r['ok'] for r in part['none'])}/{len(part['none'])} clean · "
            f"{sum(r['ok'] for r in part['clean_run'])}/{len(part['clean_run'])} protected(errors 0)"
            + (f" · state-check errors in {len(st)} protected run(s) (their own textures — listed)" if st else ""))


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    if sys.argv[1:] == ["snapshot"]:
        print("copied:", snapshot())
    elif sys.argv[1:] == ["check"]:
        rs = check()
        for r in rs:
            tag = TAGS[r["expect"]][0 if r["ok"] else 1]
            print(tag + r["name"], (f"{r['n_hits']} errors " if r["expect"] == "clean_run" and r["n_hits"] else "") + str(r["hits"][:1])
                  + (f"  state-check {[(h['check'], h['widgets'][:1]) for h in r['state_hits']]}" if r.get("state_hits") else ""))
        print(summary_line(rs))
    else:
        print(__doc__)
