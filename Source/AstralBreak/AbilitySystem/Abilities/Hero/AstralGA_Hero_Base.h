// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/AstralGameplayAbility.h"
#include "AstralGA_Hero_Base.generated.h"

class UGameplayEffect;
struct FAstralAttackTraceHit;

/**
 *
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_Base : public UAstralGameplayAbility
{
	GENERATED_BODY()
public:
	UAstralGA_Hero_Base(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	// 아래 인자 축약 헬퍼들은 로직 공유가 아니라 인자 나열 축소 — GA가 이미 아는 값
	// (ASC·Avatar·Level·Current* 핸들 3종)을 적중 처리마다 다시 쓰지 않게 한다

	/** 공격 적중 1건에 데미지 적용 */
	bool ApplyAttackHit(const FAstralAttackTraceHit& Hit, float Damage) const;

	/** ApplyUltGain — 현재 활성화 버전 */
	void ApplyUltGain(float Amount) const;

	/** ApplyMarkGain — 현재 활성화 버전 */
	void ApplyMarkGain(float Amount) const;

	/**
	 * 스태미나 소모 시점(Sprint 종료 / Dodge 커밋 / 방어 종료 등)에 GameData의 RegenBlock GE를 오너에 적용
	 * 서버 권위에서만 적용 — 회복 GE의 periodic 틱 자체가 서버 실행
	 */
	void ApplyRegenBlockEffect(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) const;

	/**
	 * GameData의 UltGain GE를 SetByCaller.UltGain=Amount로 자신에게 적용 - 적중·패링 성공 등 모든 어빌리티발 수급 지점
	 */
	void ApplyUltGain(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, float Amount) const;

	/** GameData의 MarkGain GE를 SetByCaller.MarkGain=Amount로 자신에게 적용 — 콤보 피니셔/패링 보상 수급 지점 */
	void ApplyMarkGain(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, float Amount) const;

	/**
	 * SetByCaller GE 공통 적용 (서버 권위 전용, Amount≈0이면 무시).
	 * 수급(양수)과 소모(음수 — 가드 피격 스태미나 드레인 등) 양쪽에서 사용 — 부호는 호출자 책임
	 */
	void ApplySetByCallerEffect(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, TSubclassOf<UGameplayEffect> EffectClass, const FGameplayTag& SetByCallerTag, float Amount) const;

protected:
	// 공유 GE 참조(RegenBlock/UltGain/MarkGain 등)는 UAstralGameData 소유 — GA에는 수치 노브만 남긴다

	/** 적중 1회(타겟 1기)당 오의 수급량 — 0이면 수급 없음. 광역 다중 적중 시 타겟 수 비례 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ult", Meta = (ClampMin = "0.0"))
	float UltGainOnHit = 0.0f;
};
