#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/AstralGameplayAbility.h"
#include "AstralGA_Enemy_HitReact.generated.h"

class UAnimMontage;

/**
 * 적의 피격 반응 — 맞으면 맞은 쪽으로 움찔한다 (Docs/Design/m3-enemy-ai.md §10 C2 ⑤).
 *
 * 발동: GameplayEvent.Damaged (UAstralHealthSet 이 피해 > 0 일 때마다 서버에서 보낸다 — 패링으로 0 이 된 피해에는 오지 않는다).
 * 방향: 이벤트의 Instigator(가해자 폰) 위치를 내 전방 · 우측에 비춰 앞 / 뒤 / 좌 / 우 몽타주 중 하나. 가해자가 없거나 자기 자신이면 앞.
 * 버팀: 발동 차단 태그 — 공격 중(State.Enemy.Attacking) · 행동 불가(State.Enemy.Staggered — 경직 중이거나 이미 움찔하는 중) · 사망.
 * 간격: 한 번 움찔하면 MinInterval 동안 다시 움찔하지 않는다 — 인스턴스(InstancedPerActor)가 마지막 발동 시각을 쥐고 CanActivateAbility 에서 견준다.
 *       쿨다운 GE 를 쓰지 않은 이유: 서버 전용 어빌리티라 클라이언트에 알릴 것이 없고(복제되는 GE · 태그 0), 애셋이 늘지 않는다.
 * 표시: 켜져 있는 동안 State.Enemy.Staggered 를 갖는다(ActivationOwnedTags) — 컨트롤러가 그 태그 이벤트로 트리를 Stagger 상태로 보낸다.
 *
 * ServerOnly. 클라이언트는 ASC 가 복제하는 몽타주로 본다(§10 C1-0b). 몽타주 · 간격은 BP 자식에서 바꾼다.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Enemy_HitReact : public UAstralGameplayAbility
{
	GENERATED_BODY()

public:
	UAstralGA_Enemy_HitReact(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	// 데이터 읽기 — 시험 · 애셋 검증용
	float GetMinInterval() const { return MinInterval; }
	UAnimMontage* GetFrontMontage() const { return FrontMontage; }
	UAnimMontage* GetBackMontage() const { return BackMontage; }
	UAnimMontage* GetLeftMontage() const { return LeftMontage; }
	UAnimMontage* GetRightMontage() const { return RightMontage; }

protected:
	virtual bool CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const override;
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;

	UFUNCTION()
	void OnReactMontageFinished();

	UFUNCTION()
	void OnReactMontageInterrupted();

	/** 가해자 방향의 몽타주. 그 방향 것이 비어 있으면 앞 것 */
	UAnimMontage* SelectReactMontage(const AActor* Attacker) const;

protected:
	/** 가해자가 앞에 있을 때 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|HitReact")
	TObjectPtr<UAnimMontage> FrontMontage;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|HitReact")
	TObjectPtr<UAnimMontage> BackMontage;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|HitReact")
	TObjectPtr<UAnimMontage> LeftMontage;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|HitReact")
	TObjectPtr<UAnimMontage> RightMontage;

	/** 움찔한 뒤 다시 움찔하기까지의 최소 간격(초) — 발동 시각 기준. 여럿이 계속 때려도 이 간격으로만 끊긴다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|HitReact", Meta = (ClampMin = "0.0"))
	float MinInterval = 2.5f;

private:
	/** 마지막 발동 시각(서버 월드 시간). 음수 = 아직 없음 */
	double LastReactTime = -1.0;
};
