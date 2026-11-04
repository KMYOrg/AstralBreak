"""SOMA77 — Kimodo(local_ai) 출력 골격의 상수 한 곳 (Phase 8-3 에 providers/local_ai.py 에서 옮겼다 — 그 모듈은 다시 내보낸다).

local_ai 의 리타깃 기본값(골반 · 체인 · 발)과 blender 경로가 SOMA BVH 를 알아볼 때(motion_file 로 저장된 Kimodo BVH 를 다시 변환 · 보정 — Phase 8-3)
같은 값을 쓴다.
"""
from __future__ import annotations

SOMA_PELVIS = "Hips"
SOMA_FEET = ["LeftFoot", "RightFoot"]
# 생성 골격의 어깨 관절 폭 · 팔 길이(motion_metrics.arm_dims 정의) — 자루 무기 간격 사상(gap_map)의 소스 쪽. SOMA77 은 고정 골격이라 상수:
# Kimodo BVH 표준 T 포즈 오프셋(기록 Job job_20261026_192555_f991aa kimodo_00.bvh, 2026-10-26)에서 LeftArm ↔ RightArm 32.96 cm,
# LeftArm → LeftForeArm 28.74 + → LeftHand 27.09 · 오른팔 28.74 + 27.13(평균 55.85 — NPZ 관절 위치의 위팔 길이와 0.05 cm 안). 대상 쪽은 계획이 잰다
SOMA_ARMS = {"shoulder_width_cm": 32.96, "arm_cm": 55.85}


def _soma_hand_chains(side: str) -> list[dict]:
    """SOMA77 손가락은 Hand{F}1(손목에서 2.9~4.0 cm, 메타카팔) → 2 · 3 · 4 → End(끝점), 엄지는 Thumb1~3 → End. 대상에 손가락 체인이
    없으면 자동 정렬이 꺼진 op 의 퍼지 매핑을 따라 손가락을 꺾었고(2026-10-24), 자동 캐릭터라이즈는 SOMA 를 Mixamo 로 잡아 Index1~3
    (메타카팔부터 한 마디 밀림)을 손가락으로 맞춘다. 같은 체인을 범용 제안기(create_ik_rig finger_chain_suggestion)도 낸다."""
    chains = [{"name": f"{side}Thumb", "start": f"{side}HandThumb1", "end": f"{side}HandThumb3"}]
    for finger in ("Index", "Middle", "Ring", "Pinky"):
        chains += [{"name": f"{side}{finger}Metacarpal", "start": f"{side}Hand{finger}1", "end": f"{side}Hand{finger}1"},
                   {"name": f"{side}{finger}", "start": f"{side}Hand{finger}2", "end": f"{side}Hand{finger}4"}]
    return chains


# Vesper 자동 IK Rig 의 표준 체인 이름(FCharacterizationStandard) — 스파이크에서 수동 체인 PASSED(각속도 p99 비 0.98). 손은 _soma_hand_chains
SOMA_CHAINS = [
    {"name": "Spine", "start": "Spine1", "end": "Chest"},
    {"name": "Neck", "start": "Neck1", "end": "Neck2"},
    {"name": "Head", "start": "Head", "end": "Head"},
    {"name": "LeftClavicle", "start": "LeftShoulder", "end": "LeftShoulder"},
    {"name": "LeftArm", "start": "LeftArm", "end": "LeftHand", "goal": "LeftHandIK"},
    {"name": "RightClavicle", "start": "RightShoulder", "end": "RightShoulder"},
    {"name": "RightArm", "start": "RightArm", "end": "RightHand", "goal": "RightHandIK"},
    {"name": "LeftLeg", "start": "LeftLeg", "end": "LeftToeBase", "goal": "LeftFootIK"},
    {"name": "RightLeg", "start": "RightLeg", "end": "RightToeBase", "goal": "RightFootIK"},
] + _soma_hand_chains("Left") + _soma_hand_chains("Right")

# SOMA BVH 판정 — 리타깃 기본값이 가리키는 관절(골반 · 발 · 체인 시작 · 끝)이 모두 있어야 한다(이름만 — 관절 수는 BVH 판 마다 다를 수 있다)
REQUIRED_JOINTS = frozenset([SOMA_PELVIS, *SOMA_FEET, *(c["start"] for c in SOMA_CHAINS), *(c["end"] for c in SOMA_CHAINS)])


def retarget_defaults() -> dict:
    return {"source_pelvis": SOMA_PELVIS, "source_chains": SOMA_CHAINS, "source_feet": SOMA_FEET}


def is_soma(joint_names) -> bool:
    return REQUIRED_JOINTS <= set(joint_names)
