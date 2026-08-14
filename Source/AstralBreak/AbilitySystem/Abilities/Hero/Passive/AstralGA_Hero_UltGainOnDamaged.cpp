#include "AstralGA_Hero_UltGainOnDamaged.h"

#include "AbilitySystem/AstralEventGameplayTags.h"

UAstralGA_Hero_UltGainOnDamaged::UAstralGA_Hero_UltGainOnDamaged(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::ServerOnly;
	ActivationPolicy = EAstralAbilityActivationPolicy::Manual;
	
	if (HasAnyFlags(RF_ClassDefaultObject))
	{
		// GameplayEvent.Damaged 수신 시 자동 트리거 (HealthSet::PostGameplayEffectExecute가 발송)
		FAbilityTriggerData TriggerData;
		TriggerData.TriggerTag = AstralGameplayTags::GameplayEvent_Damaged;
		TriggerData.TriggerSource = EGameplayAbilityTriggerSource::GameplayEvent;
		AbilityTriggers.Add(TriggerData);
	}
}

void UAstralGA_Hero_UltGainOnDamaged::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	if (TriggerEventData)
	{
		// ApplyUltGain은 서버 권위 체크 내장 + Amount<=0 무시
		ApplyUltGain(Handle, ActorInfo, ActivationInfo, TriggerEventData->EventMagnitude * GainRatio);
	}

	// 즉시 종료 — 비동기 작업 금지 (다단 히트 수급 씹힘 방지)
	EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
}
