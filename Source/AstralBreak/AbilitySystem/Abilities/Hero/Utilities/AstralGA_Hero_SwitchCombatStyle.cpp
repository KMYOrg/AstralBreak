#include "AstralGA_Hero_SwitchCombatStyle.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "Character/AstralCharacter.h"

UAstralGA_Hero_SwitchCombatStyle::UAstralGA_Hero_SwitchCombatStyle(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	InstancingPolicy   = EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::LocalPredicted;

	// 공격 중 전환 차단 (ActivationOwnedTags 부모 매칭). 방어 중 전환은 허용 — 방어는 스타일 게이트가 없다
	ActivationBlockedTags.AddTag(AstralGameplayTags::Ability_Attack);
}

void UAstralGA_Hero_SwitchCombatStyle::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	// 커밋 — 기본은 비용/쿨다운 없음(즉시 전환 기획). 연타 억제가 필요해지면 BP에서 Cooldown GE 지정 (표준 경로)
	if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
		return;
	}

	// 상태 쓰기는 서버 인스턴스만 — 클라 인스턴스는 발동 사실만 예측 (태그는 복제로 도착)
	if (ActorInfo && ActorInfo->IsNetAuthority() && StyleCycle.Num() > 0)
	{
		if (AAstralCharacter* Character = GetAstralCharacterFromActorInfo())
		{
			const UAbilitySystemComponent* ASC = ActorInfo->AbilitySystemComponent.Get();

			// 현재 스타일의 다음 항목으로 순환 — 미발견(INDEX_NONE)이면 첫 항목으로 (초기 미지정 폰 안전망)
			int32 CurrentIndex = INDEX_NONE;
			if (ASC)
			{
				for (int32 Index = 0; Index < StyleCycle.Num(); ++Index)
				{
					if (ASC->HasMatchingGameplayTag(StyleCycle[Index]))
					{
						CurrentIndex = Index;
						break;
					}
				}
			}

			Character->SetCombatStyle(StyleCycle[(CurrentIndex + 1) % StyleCycle.Num()]);
		}
	}

	EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
}
