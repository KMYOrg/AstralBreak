#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AstralGA_Hero_Defend.generated.h"

class UGameplayEffect;

/**
 * 방어 — 가드/패링 통합 단일 GA (탭=패링, 홀드=가드). 입력 InputTag.Defense 하나.
 *
 * 타이밍: 발동 → 진입 비용 커밋 → State.Defense.Parrying (ParryWindow)
 *   → 입력 유지 시 State.Defense.Guarding → 릴리즈로 종료.
 * 탭(윈도우 내 릴리즈)이어도 패링 윈도우는 끝까지 유지 — 탭 짧기에 따라 윈도우가 잘리지 않는다.
 * 판정은 방어자 HealthSet 경유 CombatStatics::ResolveIncomingDamage(서버)가 하고,
 * 이 GA는 결과 이벤트(Parried/Guarded)를 받아 보상(표식·오의)/비용(스태미나 드레인)만 처리한다.
 *
 * 상호배타 = 공격 우선:
 *  - 방어는 공격을 끊지 않는다. 공격(콤보 의사 포함) 활성 중엔 CanActivateAbility가 발동을 거부하고,
 *    가드 키가 유지되면 WhileInputActive의 매 프레임 재시도가 공격 종료 프레임에 자동으로 가드에 진입시킨다.
 *  - 공격 눌림은 방어를 끊는다 (공격 GA의 CancelAbilitiesWithTag=Ability.Defense).
 *  - 공격 직후 이어지는 진입도 일반 진입과 완전히 동일 (비용·패링 포함) — 특수 처리 없음.
 *    "공격 직후" 판별은 로컬 CanActivate 루프에서만 가능해 클라/서버 인스턴스가 다른 경로를 타는
 *    디싱크를 만들므로 하지 않는다. 홀드 패링 낚시는 매 진입 비용이 억제한다.
 *
 * 페이즈 태그는 루즈 태그(활성 중 변경 가능) — 클라(체감)/서버(판정) 인스턴스 각자 부여, 판정은 서버 타이밍.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_Defend : public UAstralGA_Hero_Base
{
	GENERATED_BODY()

public:
	UAstralGA_Hero_Defend(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	virtual bool CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const override;
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	UFUNCTION()
	void OnParryWindowEnded();

	UFUNCTION()
	void OnInputReleased(float TimeHeld);

	/** 패링 성공 (서버) — 표식·오의 보상 */
	UFUNCTION()
	void OnParried(FGameplayEventData EventData);

	/** 가드 성공 (서버) — 막은 양 비례 스태미나 소모 (고갈 시 델리게이트가 가드 브레이크) */
	UFUNCTION()
	void OnGuarded(FGameplayEventData EventData);

	/** 가드 브레이크 감시 — 스태미나 0 도달 시 종료 (Sprint 패턴) */
	void OnStaminaChanged(const FOnAttributeChangeData& Data);

	void EnterGuard();

	/** 페이즈 루즈 태그 부여/해제 — 멱등 */
	void SetDefensePhaseTag(const FGameplayTag& Tag, bool bEnabled) const;

protected:
	/** 패링 판정 윈도우 (발동 직후) — M7 트리 항목이 없으므로 attribute화하지 않음 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Defense", Meta = (ClampMin = "0.05"))
	float ParryWindow = 0.2f;

	/** 막은 데미지 1당 스태미나 소모 비율 (드레인 GE는 GameData 전역) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Defense", Meta = (ClampMin = "0.0"))
	float GuardHitStaminaRatio = 0.5f;

	/** 패링 성공 보상 — 표식 수급량 (설계상 표식의 주 축적원) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Defense", Meta = (ClampMin = "0.0"))
	float ParryMarkGain = 1.0f;

	/** 패링 성공 보상 — 오의 수급량 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Defense", Meta = (ClampMin = "0.0"))
	float ParryUltGain = 10.0f;

	/** 재발동 스태미나 임계 — 가드 브레이크 직후 홀드 유지 시 매 프레임 재활성 플리커 차단 (Sprint 미러) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Defense", Meta = (ClampMin = "0.0"))
	float ReactivationStaminaThreshold = 15.0f;

private:
	/** 패링 윈도우 진행 중인지 */
	bool bParryPhase = false;

	/** 패링 윈도우 중 릴리즈됨 — 윈도우 완주 후 종료 (탭 패링) */
	bool bReleasedDuringParry = false;

	/** 실제 방어가 시작됐는지 — 커밋 실패 종료에는 RegenBlock을 걸지 않음 */
	bool bDefenseStarted = false;

	FDelegateHandle StaminaChangedDelegateHandle;
};
