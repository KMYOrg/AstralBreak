#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/AstralGameplayAbility.h"
#include "AstralGA_Death.generated.h"

/**
 * HealthComponent가 발송하는 GameplayEvent.Death로 트리거되어:
 *  1) SurvivesDeath 태그 어빌리티를 제외한 전체 취소 (자기 자신도 제외)
 *  2) StartDeath — 사망 상태 기계 진입
 *  3) DeathDuration 대기 후 종료 → EndAbility의 FinishDeath 안전망
 *
 * TODO: 사망 연출은 BP 서브클래스 몫 — 몽타주 도입 시 WaitDelay를 몽타주 종료 콜백으로 교체.
 * Hero/몬스터가 같은 클래스를 쓰고, 폰별 사망 연출은 AbilitySet에서 서브클래스 교체로 커스텀.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Death : public UAstralGameplayAbility
{
	GENERATED_BODY()

public:
	UAstralGA_Death(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	//~UGameplayAbility interface
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;
	//~End of UGameplayAbility interface

	/** 사망 상태 기계 진입 (아직이면) */
	UFUNCTION(BlueprintCallable, Category = "Astral|Ability")
	void StartDeath();

	/** 사망 상태 기계 완료 (진행 중이면) */
	UFUNCTION(BlueprintCallable, Category = "Astral|Ability")
	void FinishDeath();

	/** DeathDuration 경과 — 어빌리티 종료 (EndAbility가 FinishDeath 수행) */
	UFUNCTION()
	void OnDeathDurationElapsed();

protected:
	/** 활성화 시 자동으로 StartDeath 호출. BP 연출이 시작 타이밍을 직접 제어하려면 false */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Death")
	bool bAutoStartDeath = true;

	/** 사망 연출 길이 — StartDeath 후 이 시간이 지나면 종료(FinishDeath). 몽타주 도입 시 콜백으로 대체 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Death", Meta = (ClampMin = "0.0"))
	float DeathDuration = 3.0f;
};
