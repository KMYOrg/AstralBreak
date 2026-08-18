#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AstralGA_Hero_SwitchCombatStyle.generated.h"

/**
 * 전투 스타일 전환 — 입력 InputTag.SwitchCombatStyle.
 * 상태를 직접 들지 않는다: 서버 인스턴스가 UAstralCombatStatics::ApplyCombatStyle로 의도만 전달.
 * 전환 규칙은 StyleCycle 데이터 — 현재 스타일의 다음 유효 후보(장비 보유)로 순환.
 * 히어로별 BP에서 구성하므로 이 GA는 스타일 집합을 모른다. 전환 없는 히어로는 이 GA를 부여받지 않는다.
 * 공격 중 전환은 ActivationBlockedTags(Ability.Attack)로 차단 — 콤보 도중 무기가 바뀌면
 * 트레이스 대상이 뒤바뀌므로. 즉시 종료 (몽타주 없음 — 연출은 이후).
 * 오너 클라 체감은 태그 복제 RTT/2만큼 지연 — 예측 토글은 M4.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_SwitchCombatStyle : public UAstralGA_Hero_Base
{
	GENERATED_BODY()

public:
	UAstralGA_Hero_SwitchCombatStyle(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;

protected:
	/** 순환할 스타일 목록 (State.CombatStyle.*) — 현재 보유 스타일의 다음 항목으로 전환. 비어 있으면 no-op */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|CombatStyle", Meta = (Categories = "State.CombatStyle"))
	TArray<FGameplayTag> StyleCycle;
};
