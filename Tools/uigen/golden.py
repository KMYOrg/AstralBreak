"""정답 묶음(골든 세트, 1b 후속 K-b) — 사용자가 사람 눈으로 찾은 결함을 run 사본 + 위젯 + 기대 분류로 모아, 진단(gen/diagnose)이 늘 그 분류로 잡는지 본다.
문턱 · 측정을 바꾸면 이 묶음으로 다시 잰다(몇 장에 맞추는 보정을 끊는다). 외부 화면이 섞여 git 무시 work/_golden/ — 시험은 없으면 건너뛴다.

  python golden.py snapshot   # work/ 의 원본 run 에서 진단에 필요한 파일만 work/_golden/<run>/ 로 복사(이미 있으면 건너뜀) + golden.json
  python golden.py check      # 묶음 전부 진단 → 항목마다 잡힘 / 놓침, '오류 아님' 항목(expect none)은 깨끗함 / 거짓 양성
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
    if item.get("state_extra"):
        extra = set((rec.get("state") or {}).get("force_visible_extra") or [])
        return [{"state": sorted(extra)}] if set(item["state_extra"]) <= extra else []
    out = []
    for d in rec.get("defects") or []:
        if not set(item.get("widgets") or []) & set(d.get("widgets") or []):
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
        none = it.get("expect") == "none"
        res.append({"name": it["name"], "run": it["run"], "expect": "none" if none else "defect", "caught": bool(hit),
                    "ok": not hit if none else bool(hit), "hits": hit[:3]})
    return res


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    if sys.argv[1:] == ["snapshot"]:
        print("copied:", snapshot())
    elif sys.argv[1:] == ["check"]:
        rs = check()
        for r in rs:
            tag = ("clean  " if r["ok"] else "FALSE+ ") if r["expect"] == "none" else ("caught " if r["ok"] else "MISSED ")
            print(tag + r["name"], r["hits"][:1])
        det, non = [r for r in rs if r["expect"] == "defect"], [r for r in rs if r["expect"] == "none"]
        print(f"{sum(r['ok'] for r in det)}/{len(det)} caught · {sum(r['ok'] for r in non)}/{len(non)} clean")
    else:
        print(__doc__)
