#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AstralGA_Hero_Ult.generated.h"

class UAnimMontage;

/**
 * 오의 — 오의 게이지를 통째로 써서 내는 개인 궁극기 (설계 Docs/Design/m4-ult-chain.md §2).
 *  - 비용: UAstralGE_Cost_Ult (게이지가 가득일 때만 통과 · 전부 소비). 표준 CommitAbility 경로
 *  - 켜져 있는 동안 무적(State.Invulnerable) · 다른 공격 / 방어 / 회피 차단. 발동하면 진행 중인 것을 취소한다
 *  - 전투 스타일에 묶지 않는다 — 판정은 무기 트레이스가 아니라 몽타주의 HitEventTag 시점에 전방 스윕 한 번(서버)
 *  - State.Ult.Blocked 가 있으면 발동하지 않는다 (M5 Burst Aura 가 얹힐 자리 — §4)
 *  - 서버에서 체인 컴포넌트에 두 번 알린다 (§3 끝 'B 다듬기'): 비용 확정 직후 시전 시작(NotifyUltStarted — 남의 오의 차단 · 체인 타이머 멈춤),
 *    끝날 때 시전 종료(NotifyUltEnded — 맞혔으면 그 시각으로 체인 등록). 레이드 GameState 가 없는 맵에서는 알릴 곳이 없다
 *  - 못 맞힌 오의(스윕에 적 0 — 판정 전에 끊긴 것 포함)는 끝날 때 최대치 × MissRefundRatio 를 돌려받는다
 * 오의 적중으로는 게이지가 차지 않는다 (UltGainOnHit 을 쓰지 않는다). 못 맞혔을 때의 반환이 유일한 예외이고 수급 경로를 타지 않는다.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_Ult : public UAstralGA_Hero_Base
{
	GENERATED_BODY()

public:
	UAstralGA_Hero_Ult(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	UFUNCTION()
	void OnMontageCompleted();

	UFUNCTION()
	void OnMontageInterrupted();

	/** 몽타주의 타격 노티파이 — 서버에서 전방 스윕 한 번 */
	UFUNCTION()
	void OnHitEvent(FGameplayEventData Payload);

protected:
	/** 오의 모션 — HitEventTag 를 보내는 노티파이가 하나 있어야 한다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ult")
	TObjectPtr<UAnimMontage> UltMontage;

	/** 타격 시점 이벤트 — 몽타주의 노티파이가 보내는 태그. 활성화마다 처음 한 번만 받는다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ult", Meta = (Categories = "GameplayEvent"))
	FGameplayTag HitEventTag;

	/** 오의 피해 — 스윕에 걸린 적 각각에게 (잠정) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ult", Meta = (ClampMin = "0.0"))
	float BaseDamage = 200.f;

	/** 스윕 시작 — 아바타 위치에서 정면으로 이만큼 앞 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ult|Trace", Meta = (ClampMin = "0.0"))
	float TraceStartOffset = 50.f;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ult|Trace", Meta = (ClampMin = "0.0"))
	float TraceDistance = 400.f;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ult|Trace", Meta = (ClampMin = "1.0"))
	float TraceRadius = 150.f;

	/** 못 맞힌 오의가 끝날 때 돌려받는 게이지 — 최대치에 대한 비율 (잠정). 0 이면 돌려주지 않는다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ult", Meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float MissRefundRatio = 0.8f;

private:
	/** 이 활성화가 비용을 실제로 썼는가 — 종료 처리(반환 · 체인 통지)를 한 번만 하게 한다 */
	bool bCastCommitted = false;

	/** 서버 — 이 활성화의 스윕에 적이 한 명이라도 걸렸는가 */
	bool bHitAny = false;
};
