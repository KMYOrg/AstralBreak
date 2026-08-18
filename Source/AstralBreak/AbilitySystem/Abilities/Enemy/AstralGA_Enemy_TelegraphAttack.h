#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/AstralGameplayAbility.h"
#include "AstralGA_Enemy_TelegraphAttack.generated.h"

class UAbilityTask_WaitDelay;
class UGameplayEffect;

/**
 * 예고(텔레그래프) 공격 — 더미/몬스터 공용 (M3 "패링 가능한 강공격 → 약점 노출"의 원형).
 *
 * OnSpawn 부여 즉시 활성 → 내부 루프:
 *   대기(AttackInterval) → [토글 확인] → 텔레그래프(State.Telegraphing + DrawDebug, TelegraphDuration) → ApplyDamageSweep → 반복.
 * 패링당하면(GameplayEvent.Staggered 수신) 진행 중 사이클 중단 + StaggerRecovery 경직 후 재개.
 *
 * ServerOnly — AI/더미 공격은 예측 불필요, 판정·타이밍 전부 서버 권위.
 * 텔레그래프 가시화는 MVP DrawDebug (원프로세스 검증용) — 정식은 GameplayCue로 교체 예정.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Enemy_TelegraphAttack : public UAstralGameplayAbility
{
	GENERATED_BODY()

public:
	UAstralGA_Enemy_TelegraphAttack(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	/** 사이클 시작 — AttackInterval 대기 후 텔레그래프 진입 */
	void StartCycle();

	UFUNCTION()
	void OnIntervalElapsed();

	UFUNCTION()
	void OnTelegraphElapsed();

	/** 패링당함 — 진행 중 사이클 취소 + 경직 후 재개 */
	UFUNCTION()
	void OnStaggered(FGameplayEventData EventData);

	UFUNCTION()
	void OnStaggerRecovered();

	/** 텔레그래프 구간 정리 (루즈 태그 해제) — 멱등 */
	void ClearTelegraph();

protected:
	/** 공격 데미지 (Damage GE는 GameData 전역) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Telegraph")
	float BaseDamage = 15.f;

	/** 공격 사이클 주기 — 판정 후 다음 텔레그래프까지 대기 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Telegraph", Meta = (ClampMin = "0.1"))
	float AttackInterval = 3.0f;

	/** 예고 시간 — 이 구간이 패링/가드 반응 윈도우 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Telegraph", Meta = (ClampMin = "0.1"))
	float TelegraphDuration = 1.0f;

	/** 패링당한 후 경직 시간 — 루프 재개까지 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Telegraph", Meta = (ClampMin = "0.0"))
	float StaggerRecovery = 2.0f;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Telegraph|Trace")
	float TraceRadius = 80.f;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Telegraph|Trace")
	float TraceDistance = 200.f;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Telegraph|Trace")
	float TraceStartOffset = 50.f;

private:
	/** 진행 중인 대기 태스크 (interval/telegraph/stagger 중 하나) — 스태거 중단 시 EndTask로 정리 */
	UPROPERTY(Transient)
	TObjectPtr<UAbilityTask_WaitDelay> ActiveDelayTask;

	/** 텔레그래프 구간 진행 중인지 (루즈 태그 정리 게이트) */
	bool bTelegraphing = false;
};
