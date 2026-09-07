// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/AstralGameplayAbility.h"
#include "Combat/AstralTargetHandle.h"
#include "AstralGA_Hero_Base.generated.h"

/**
 * 히어로 전용 GA 베이스 — "히어로 전용 무언가를 아는" 바인딩 층.
 *  - 자원 바인딩: AstralHeroResourceSet(오의·표식·스태미나) 대상 헬퍼
 *  - 타게팅 바인딩: UAstralTargetingComponent(히어로 전용 컴포넌트) 조회
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_Base : public UAstralGameplayAbility
{
	GENERATED_BODY()
public:
	UAstralGA_Hero_Base(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	// 타게팅 바인딩 층

	/** 하드 락 타겟 — 없으면 빈 핸들 */
	FAstralTargetHandle ResolveEffectiveTarget() const;

	/**
	 * 아바타 → AimLocation 방향의 yaw를 현재 아바타 yaw 기준 ±MaxAssistYaw로 클램프한 최종 facing.
	 * 스냅샷 — 호출 시점 값이며 밴드 중 재계산하지 않는다. 초과 시 폴백이 아니라 클램프
	 */
	FRotator ComputeClampedFacing(const FVector& AimLocation, float MaxAssistYaw) const;

protected:
	// 자원 바인딩 층
	// GE를 어떻게 적용하는가(기계)는 베이스의 ApplySetByCallerEffect, 언제·얼마나(정책)는 개별 GA 소유

	/** 오의 수급 — GameData UltGain GE (SetByCaller.UltGain). 적중·패링 성공 등 모든 어빌리티발 수급 지점 */
	void ApplyUltGain(float Amount) const;

	/** 표식 수급 — GameData MarkGain GE (SetByCaller.MarkGain). 콤보 피니셔/패링 보상 수급 지점 */
	void ApplyMarkGain(float Amount) const;

	/** 스태미나 소모 — 양수 Drain을 받아 음수로 주입 (GameData StaminaDrain GE). 가드 피격 등 가변 소모 지점 */
	void ApplyStaminaDrain(float Amount) const;

	/**
	 * 스태미나 소모 시점(Sprint 종료 / Dodge 커밋 / 방어 종료 등)에 GameData의 RegenBlock GE를 오너에 적용
	 * 서버 권위에서만 적용 — 회복 GE의 periodic 틱 자체가 서버 실행
	 */
	void ApplyRegenBlockEffect(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) const;

protected:
	// 공유 GE 참조(RegenBlock/UltGain/MarkGain 등)는 UAstralGameData 소유 — GA에는 수치 노브만 남긴다

	/** 적중 1회(타겟 1기)당 오의 수급량 — 0이면 수급 없음. 광역 다중 적중 시 타겟 수 비례 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ult", Meta = (ClampMin = "0.0"))
	float UltGainOnHit = 0.0f;
};
