#pragma once

#include "CoreMinimal.h"
#include "Engine/HitResult.h"
#include "AstralCombatTypes.generated.h"

/** 무기 트레이스 적중 1건 — AttackTraceWindows 태스크가 생산, GA의 ApplyAttackHit가 소비 */
USTRUCT(BlueprintType)
struct FAstralAttackTraceHit
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly, Category = "Astral|Attack")
	FHitResult HitResult;

	/** 밴드 시작 시 해석된 무기 — 데미지 GE의 EffectCauser로 쓸 것 */
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Attack")
	TObjectPtr<AActor> EffectCauser = nullptr;

	/** 밴드 경계 식별자 (활성화 내 1부터 증가) — "밴드당 1회" 게이트는 이 값 비교로 */
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Attack")
	int32 WindowSerial = 0;
};

/**
 * 공격 방향 보정 명령 — Motion Warping 워프 타겟 1개의 로컬 실행 계약.
 */
USTRUCT()
struct FAstralFacingWarpCommand
{
	GENERATED_BODY()

	/** 몽타주 MotionWarping 노티파이가 참조하는 워프 타겟 이름 — 어빌리티별로 고유 */
	UPROPERTY()
	FName WarpTargetName = NAME_None;

	/** 스냅샷 — 이미 클램프된 최종 방향. 밴드 중 재계산 금지 */
	UPROPERTY()
	FRotator DesiredFacing = FRotator::ZeroRotator;
};
