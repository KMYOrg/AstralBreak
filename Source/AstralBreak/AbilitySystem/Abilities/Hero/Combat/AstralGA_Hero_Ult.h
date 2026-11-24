#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/Combat/AstralGA_Hero_FacingAttack.h"
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
 *  - 발동 때 락온 타겟 쪽으로 돈다(UAstralGA_Hero_FacingAttack — 몽타주의 워프 구간이 실제로 돌린다). 락온이 없으면 서 있는 방향
 *  - UltCombatStyle 이 있으면 쓰는 동안 그 스타일의 무기를 들고(서버가 스타일 태그를 바꾼다 — 부착 · 애님 레이어 · 왼손 IK 가 따라온다) 끝나면 되돌린다
 * 오의 적중으로는 게이지가 차지 않는다 (UltGainOnHit 을 쓰지 않는다). 못 맞혔을 때의 반환이 유일한 예외이고 수급 경로를 타지 않는다.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_Ult : public UAstralGA_Hero_FacingAttack
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

	/** 서버 — UltCombatStyle 로 무기를 바꿔 든다. 이미 그 스타일이거나 그 스타일의 장비가 없으면 아무 일도 없다 */
	void BeginUltCombatStyle(const FGameplayAbilityActorInfo* ActorInfo);

	/** 서버 — 바꿔 든 무기를 되돌린다. 그 사이 다른 것이 스타일을 바꿨으면 건드리지 않는다 */
	void EndUltCombatStyle(const FGameplayAbilityActorInfo* ActorInfo);

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

	/** 쓰는 동안 드는 무기의 전투 스타일 (State.CombatStyle 의 자식) — 비우면 들고 있던 무기 그대로 쓴다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ult", Meta = (Categories = "State.CombatStyle"))
	FGameplayTag UltCombatStyle;

private:
#if !UE_BUILD_SHIPPING
	/** UltMontage 의 타격 노티파이 · 워프 구간 · 충돌 구간 저작 검증 (활성화 1회차) */
	bool bMontageValidated = false;
#endif

	/** 서버 — 이 활성화가 바꾸기 전의 전투 스타일. 바꾸지 않았으면 비어 있다 */
	FGameplayTag RestoreCombatStyle;

	/** 이 활성화가 비용을 실제로 썼는가 — 종료 처리(반환 · 체인 통지)를 한 번만 하게 한다 */
	bool bCastCommitted = false;

	/** 서버 — 이 활성화의 스윕에 적이 한 명이라도 걸렸는가 */
	bool bHitAny = false;
};
