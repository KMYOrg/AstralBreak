#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AbilitySystem/Tasks/AstralAbilityTask_AttackTraceWindows.h"
#include "AstralGA_Hero_MarkFinisher.generated.h"

class UAnimMontage;
class UAstralFacingSession;
struct FAstralFacingStageResolution;

/**
 * 고유 자원 강화 공격 — 표식(MarkStack)을 소비하는 강화 근접 일격.
 * 비용은 표준 CostGameplayEffect 경로(BP에서 GE_Cost_MarkFinisher 지정 — MarkStack -N Instant).
 * 판정은 무기 소켓 연속 트레이스 — 밴드(WeaponTrace.Begin~End) 수명은 AttackTraceWindows 태스크가 소유.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_MarkFinisher : public UAstralGA_Hero_Base
{
	GENERATED_BODY()

public:
	UAstralGA_Hero_MarkFinisher(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	//~UAstralGameplayAbility — 입력 활성화에 Stage 0 Facing 제안을 싣는다. 단발이라 Stage 0뿐
	virtual EAstralInputActivationPreparation MakeActivationEventData(const FGameplayAbilityActorInfo& ActorInfo, FGameplayEventData& OutEventData) const override;
	//~End UAstralGameplayAbility

	/** 활성화마다 새 Facing 세션 (NumStages = 1) — Stage 0은 TriggerEventData에서, 로컬은 이벤트 밖 활성화에 한해 라이브 캡처 폴백 */
	void BeginFacingSession(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData);

	/** 확정 결과 → 워프 설치/제거 (FacingWarpTargetName) */
	void ApplyFacingResolution(const FAstralFacingStageResolution& Resolution);

	UFUNCTION()
	void OnMontageCompleted();

	UFUNCTION()
	void OnMontageInterrupted();

	/** 무기 적중 (타겟당 1회, authority) — Damage GE + 오의 수급 */
	UFUNCTION()
	void OnAttackTraceHit(const FAstralAttackTraceHit& Hit);

protected:
	/** 강화 공격 모션 (히트 노티파이 포함) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Empowered")
	TObjectPtr<UAnimMontage> AttackMontage;

	/** 강화 데미지 — 기본 공격보다 높게 (Damage GE는 GameData 전역, SetByCaller.Damage 주입) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Empowered")
	float BaseDamage = 60.f;

	/** 무기 트레이스 스피어 반경 — 강화 일격은 콤보보다 관대하게 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Empowered|Trace")
	float WeaponTraceRadius = 35.f;

	/** 워프 타겟 이름 — AttackMontage의 MotionWarping 노티파이와 일치해야 한다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Empowered|Facing")
	FName FacingWarpTargetName = TEXT("MarkFinisher.Facing");

private:
#if !UE_BUILD_SHIPPING
	/** AttackMontage의 Facing 워프 밴드 저작 검증 (활성화 1회차) */
	bool bMontageValidated = false;
#endif

	/** 트레이스 윈도우 태스크 — 어빌리티 수명 (밴드 수명·무기 해석·겹침 방어는 태스크 소유) */
	UPROPERTY(Transient)
	TObjectPtr<UAstralAbilityTask_AttackTraceWindows> TraceTask;

	/** Facing 네트워크 세션 — 활성화마다 새 객체. EndAbility가 키를 대조해 End */
	UPROPERTY(Transient)
	TObjectPtr<UAstralFacingSession> FacingSession;
};
