#pragma once

#include "CoreMinimal.h"
#include "ActiveGameplayEffectHandle.h"
#include "AbilitySystem/Abilities/AstralGameplayAbility.h"
#include "AstralGA_Enemy_Stagger.generated.h"

class UAnimMontage;
class UGameplayEffect;

/**
 * 적의 경직 — 패링당하면 비틀거리고 그동안 약점이 드러난다 (Docs/Design/m3-enemy-ai.md §10 C2 ⑥).
 *
 * 발동: GameplayEvent.Staggered (UAstralCombatStatics::ResolveIncomingDamage 가 패링당한 공격자에게 서버에서 보낸다 — 공격 GA 의 스윕 호출 안에서 온다).
 * 하는 일: 진행 중인 공격 어빌리티(Ability.Attack)와 피격 반응(Ability.Enemy.HitReact)을 취소 → 경직 몽타주 재생 →
 *          켜져 있는 동안 State.Enemy.Staggered(ActivationOwnedTags) + 약점 노출 GE(ExposedEffectClass — 끝날 때 뗀다) → StaggerDuration 뒤 종료.
 * 트리: 컨트롤러가 State.Enemy.Staggered 의 태그 이벤트를 받아 트리를 Stagger 상태로 보내고, 그 상태는 태그가 떨어질 때까지 기다린다.
 * 피격 반응보다 우선한다 — 경직 중에는 움찔하지 않는다(피격 반응의 발동 차단 태그).
 *
 * 이 어빌리티가 없는 적(마네킹)은 공격 GA 가 StaggerRecovery 만큼 스스로 머문다 — 둘을 함께 쓸 때는 공격 GA 의 StaggerRecovery 를 0 으로 둔다.
 * ServerOnly. 길이 · 몽타주 · GE 는 BP 자식에서 바꾼다.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Enemy_Stagger : public UAstralGameplayAbility
{
	GENERATED_BODY()

public:
	UAstralGA_Enemy_Stagger(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	// 데이터 읽기 — 시험 · 애셋 검증용
	float GetStaggerDuration() const { return StaggerDuration; }
	UAnimMontage* GetStaggerMontage() const { return StaggerMontage; }
	TSubclassOf<UGameplayEffect> GetExposedEffectClass() const { return ExposedEffectClass; }

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	UFUNCTION()
	void OnStaggerElapsed();

protected:
	/** 경직 시간(초) — 몽타주가 이보다 짧으면 남은 시간은 대기 자세, 길면 끝날 때 끊긴다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Stagger", Meta = (ClampMin = "0.1"))
	float StaggerDuration = 2.0f;

	/** 경직 몽타주(선택) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Stagger")
	TObjectPtr<UAnimMontage> StaggerMontage;

	/** 경직 동안 자신에게 거는 GE(선택) — 약점 노출(받는 피해 배율). 무기한 GE 여야 한다: 이 어빌리티가 걸고 뗀다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Stagger")
	TSubclassOf<UGameplayEffect> ExposedEffectClass;

private:
	FActiveGameplayEffectHandle ExposedEffectHandle;
};
