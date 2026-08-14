#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AstralGA_Hero_UltGainOnDamaged.generated.h"

/**
 * 피격 오의 수급 — GameplayEvent.Damaged 트리거 (HealthSet이 실차감 확정 직후 발송, 서버 전용).
 * UltGauge += EventMagnitude(클램프 후 실차감량) × GainRatio. Multiplier 레이어는 ResourceSet이 한 곳에서 곱한다.
 * 몽타주·WaitDelay 등 비동기 작업 금지 — InstancedPerActor는 활성 중 재활성이 막히므로
 * 다단 히트에서 수급이 씹힌다. 수급 후 즉시 EndAbility.
 * ⚠️ ActivationBlockedTags의 State.Death를 제거하지 말 것 — 이벤트가 Dying 태그 부착 전에 발송되므로
 * 킬링블로우 수급은 그대로 통과하고, 이 차단은 "사망 후 수급"만 막는다. RemoveTag를 넣으면 오히려 사망 후 수급이 열린다.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_UltGainOnDamaged : public UAstralGA_Hero_Base
{
	GENERATED_BODY()

public:
	UAstralGA_Hero_UltGainOnDamaged(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;

	/** 받은 피해 1당 오의 수급량 (예: 0.5 = 데미지 20 → 게이지 10). 0이면 수급 없음 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ult", Meta = (ClampMin = "0.0"))
	float GainRatio = 0.0f;
};
