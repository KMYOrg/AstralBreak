#pragma once

#include "CoreMinimal.h"
#include "Abilities/Tasks/AbilityTask.h"
#include "Combat/AstralCombatTypes.h"
#include "GameplayTagContainer.h"
#include "AstralAbilityTask_AttackTraceWindows.generated.h"

class AAstralWeaponActor;
class UGameplayAbility;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FAstralAttackTraceHitDelegate, const FAstralAttackTraceHit&, Hit);

UCLASS()
class ASTRALBREAK_API UAstralAbilityTask_AttackTraceWindows : public UAbilityTask
{
	GENERATED_BODY()

public:
	UAstralAbilityTask_AttackTraceWindows(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	static UAstralAbilityTask_AttackTraceWindows* WaitAttackTraceWindows(UGameplayAbility* OwningAbility, float InTraceRadius, FGameplayTag InBeginEventTag, FGameplayTag InEndEventTag, int32 InNumBladeSamples = 3);

	/** 어빌리티의 SourceObject(EquipmentInstance)에서 무기 액터를 얻는다 */
	static AAstralWeaponActor* FindWeaponActorFromAbility(const UGameplayAbility* Ability);

	/** 타겟 1기당 1회 발화 (밴드 내 중복 없음, authority 전용) */
	UPROPERTY(BlueprintAssignable)
	FAstralAttackTraceHitDelegate OnHitTarget;

	//~UAbilityTask
	virtual void Activate() override;
	virtual void TickTask(float DeltaTime) override;
	//~End UAbilityTask

protected:
	virtual void OnDestroy(bool bInOwnerFinished) override;

	/** 밴드 타임라인 상태 — bool 대신 명시 상태 (Waiting = 밴드 밖) */
	enum class EWindowState : uint8
	{
		Waiting,
		Tracing
	};

	/** 밴드 Begin — Serial 증가 · 무기 해석 · 스윕 상태 초기화. 겹침(중복 Begin)은 새 밴드 시작으로 흡수 */
	void HandleBeginEvent(const FGameplayEventData* Payload);

	/** 밴드 End — 상태 정리 */
	void HandleEndEvent(const FGameplayEventData* Payload);

	/** 밴드 상태 일괄 리셋 — Begin(겹침 방어)·End 공용 */
	void ResetBandState();

	/** 칼날을 따라 NumBladeSamples개 지점 계산 (밑동→끝 균등 분할) */
	void SampleBladePositions(TArray<FVector>& OutPositions) const;

	bool IsAuthority() const;

protected:
	FGameplayTag BeginEventTag;
	FGameplayTag EndEventTag;

	float TraceRadius = 25.f;
	int32 NumBladeSamples = 3;

	EWindowState State = EWindowState::Waiting;

	/** 밴드 경계 식별자 — Begin마다 증가 (첫 밴드 = 1). GA 쪽 리셋값(0)과 충돌하지 않는다 */
	int32 WindowSerial = 0;

	/** 이번 밴드의 무기 — Begin마다 재해석 (밴드 사이 장비 교체/해제 반영) */
	UPROPERTY()
	TObjectPtr<AAstralWeaponActor> CurrentWeaponActor;

	/** 이전 틱의 샘플 위치들 — 밴드 첫 틱은 스윕 없이 기준만 잡는다 */
	TArray<FVector> PrevSamplePositions;
	bool bHasPrevSamples = false;

	/** 이번 밴드에서 이미 맞은 타겟들 */
	TSet<TWeakObjectPtr<AActor>> HitActors;

	FDelegateHandle BeginEventHandle;
	FDelegateHandle EndEventHandle;
};
