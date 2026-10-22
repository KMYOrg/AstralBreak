#pragma once

#include "CoreMinimal.h"

/**
 * 최종 조준 보정(순수 계산) — AimOffset·로코모션이 만든 포즈에서 총열(총구 +X)이 조준점을 향하도록 남은 각을 척추 체인에 나눠 돌린다.
 * 체인 본마다(뿌리 → 끝, 각자 자기 피벗 기준) 같은 축의 회전을 가중치 비율로 나누므로 총열 방향은 합(= 전체 보정)만큼 돈다.
 * 피벗이 서로 달라 총구 위치가 조금 움직이고(가까운 조준점이면 그만큼 방향이 바뀐다 — 시차) 몇 번 반복해 수렴시킨다.
 * 컴포넌트 공간 트랜스폼만 다루고 월드·UObject 를 모른다 — Automation 테스트 AstralBreak.AimCorrection.* 로 고정한다.
 * 그래프 쪽은 FAnimNode_AstralAimCorrection(베이스 ABP 루트, RotateRootBone 뒤).
 */
struct FAstralAimCorrectionInput
{
	/** 체인 본의 컴포넌트 공간 트랜스폼 — 뿌리 → 끝 순서. 앞 본이 뒤 본과 WeaponBone 의 조상이어야 한다 */
	TArrayView<const FTransform> Chain;

	/** 체인 본별 가중치 — 음수는 0, 합으로 정규화 (Chain 과 같은 개수) */
	TArrayView<const float> Weights;

	/** 무기가 붙은 본(hand_r)의 컴포넌트 공간 트랜스폼 — 체인 모든 본의 자손 */
	FTransform WeaponBone = FTransform::Identity;

	/** 총구 — WeaponBone 공간. +X = 총열 */
	FTransform MuzzleInWeaponBone = FTransform::Identity;

	/** 조준점 (컴포넌트 공간) */
	FVector Target = FVector::ZeroVector;

	/** 전체 보정 최대각(도) — 넘는 오차는 이만큼만 줄인다 */
	float MaxAngleDegrees = 30.f;

	/** 시차 수렴 반복 수 (1 이상) */
	int32 Iterations = 3;
};

struct FAstralAimCorrectionResult
{
	/** 보정된 체인 본 트랜스폼 (컴포넌트 공간, 입력 순서) */
	TArray<FTransform, TInlineAllocator<4>> Chain;

	/** 전체 보정 회전 (컴포넌트 공간) — 총열 방향이 이만큼 돈다 */
	FQuat Correction = FQuat::Identity;

	/** 보정 전·후 총열 ↔ 총구→조준점 각(도) */
	float InitialErrorDegrees = 0.f;
	float ResidualErrorDegrees = 0.f;

	/** 입력이 유효해 계산했는가 (체인 없음·가중치 0·조준점이 총구와 겹침이면 false — 포즈를 건드리지 않는다) */
	bool bValid = false;
};

namespace AstralAimCorrection
{
	ASTRALBREAK_API FAstralAimCorrectionResult Solve(const FAstralAimCorrectionInput& Input);
}
