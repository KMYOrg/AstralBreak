#include "AstralGA_Hero_SwitchCombatStyle.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "Equipment/AstralEquipmentManagerComponent.h"

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
		AActor* Avatar = ActorInfo->AvatarActor.Get();
		const UAstralAbilitySystemComponent* ASC = Cast<UAstralAbilitySystemComponent>(ActorInfo->AbilitySystemComponent.Get());
		const UAstralEquipmentManagerComponent* EquipmentManager = Avatar ? Avatar->FindComponentByClass<UAstralEquipmentManagerComponent>() : nullptr;

		if (Avatar && ASC)
		{
			// 현재 스타일 인덱스 — 읽기 단일 경로. StyleCycle 밖 스타일 보유 시 INDEX_NONE → 첫 항목부터 탐색
			const int32 CurrentIndex = StyleCycle.Find(ASC->GetCombatStyle());

			// 다음 후보로 순환하되 해당 스타일의 장비가 있는 것만 — 선택적 로드아웃(한 무기만 장착)에서
			// 맨손 스타일로 넘어가는 구멍 방지. 유효 후보가 없으면 no-op (전환 입력 무의미).
			const int32 StartIndex = (CurrentIndex == INDEX_NONE) ? 0 : CurrentIndex + 1;
			const int32 NumCandidates = (CurrentIndex == INDEX_NONE) ? StyleCycle.Num() : StyleCycle.Num() - 1;
			for (int32 Step = 0; Step < NumCandidates; ++Step)
			{
				const FGameplayTag& Candidate = StyleCycle[(StartIndex + Step) % StyleCycle.Num()];
				if (EquipmentManager && EquipmentManager->HasEquipmentForStyle(Candidate))
				{
					UAstralCombatStatics::ApplyCombatStyle(Avatar, Candidate);
					break;
				}
			}
		}
	}

	EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
}
