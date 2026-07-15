#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AstralGA_Hero_Dodge.generated.h"

class UAnimMontage;

/**
 * 회피(대시) 어빌리티 (OnInputTriggered).
 * RootMotionSource(ConstantForce)로 이동 입력 방향 대시 — 전용 애니 없이 동작 (MVP).
 * 비용은 표준 CostGameplayEffect 경로(CommitAbility) 사용
 * i-frame(무적)은 이번 패스 범위 밖 — 도입 시 ActivationOwnedTags + HealthSet 차단으로 확장.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_Dodge : public UAstralGA_Hero_Base
{
	GENERATED_BODY()

public:
	UAstralGA_Hero_Dodge(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	//~UGameplayAbility interface
	virtual bool CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const override;
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	//~End of UGameplayAbility interface

	/** RootMotion 태스크 종료 콜백 */
	UFUNCTION()
	void OnDashFinished();

protected:
	/** 대시 거리 (cm) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Dodge", Meta = (ClampMin = "0.0"))
	float DodgeDistance = 500.0f;

	/** 대시 지속 시간 (초) — Strength = Distance / Duration */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Dodge", Meta = (ClampMin = "0.01"))
	float DodgeDuration = 0.2f;

	/** 이동 입력이 없을 때 백스텝(-Forward)할지 여부. false면 전방 대시 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Dodge")
	bool bDodgeBackwardWhenIdle = true;

	/** (선택) 회피 몽타주 — 지정 시 대시와 병행 재생. MVP는 None */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Dodge")
	TObjectPtr<UAnimMontage> DodgeMontage;
};
