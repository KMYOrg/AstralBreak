#pragma once

#include "CoreMinimal.h"
#include "Abilities/Tasks/AbilityTask.h"
#include "AstralAbilityTask_WeaponTrace.generated.h"

class AAstralWeaponActor;
class UGameplayAbility;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FAstralWeaponTraceHitDelegate, const FHitResult&, HitResult);

/**
 * 무기 소켓 구간 연속 트레이스 — 트레이스 밴드(WeaponTrace.Begin~End) 동안 매 틱:
 * 칼날(TraceStart~TraceEnd)을 N점 샘플링해 각 점을 이전 프레임 → 현재 프레임으로 스피어 스윕.
 * 스윙 궤적의 프레임 사이를 메워 단발 스윕의 터널링(얇은 검날 한 프레임 검사 → 적중률 급락)을 방지한다.
 *
 * ⚠️ 서버 전용 — 데미지는 서버 권위이므로 어빌리티가 HasAuthority일 때만 생성할 것.
 * 구간 내 같은 타겟은 1회만 발화 (TSet 중복 방지, 태스크 수명 = 밴드 1개).
 */
UCLASS()
class ASTRALBREAK_API UAstralAbilityTask_WeaponTrace : public UAbilityTask
{
	GENERATED_BODY()

public:
	UAstralAbilityTask_WeaponTrace(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	static UAstralAbilityTask_WeaponTrace* WeaponTrace(UGameplayAbility* OwningAbility, AAstralWeaponActor* InWeaponActor, float InTraceRadius = 25.f, int32 InNumBladeSamples = 3);

	/** 어빌리티의 SourceObject(EquipmentInstance)에서 무기 액터를 얻는다 — 실패 시 nullptr */
	static AAstralWeaponActor* FindWeaponActorFromAbility(const UGameplayAbility* Ability);

	/** 타겟 1기당 1회 발화 (구간 내 중복 없음) */
	UPROPERTY(BlueprintAssignable)
	FAstralWeaponTraceHitDelegate OnHitTarget;

	//~UAbilityTask
	virtual void Activate() override;
	virtual void TickTask(float DeltaTime) override;
	//~End UAbilityTask

protected:
	virtual void OnDestroy(bool bInOwnerFinished) override;

	/** 칼날을 따라 NumBladeSamples개 지점 계산 (밑동→끝 균등 분할) */
	void SampleBladePositions(TArray<FVector>& OutPositions) const;

	UPROPERTY()
	TObjectPtr<AAstralWeaponActor> WeaponActor;

	float TraceRadius = 25.f;
	int32 NumBladeSamples = 3;

	/** 이전 틱의 샘플 위치들 — 첫 틱은 스윕 없이 기준만 잡는다 */
	TArray<FVector> PrevSamplePositions;
	bool bHasPrevSamples = false;

	/** 이번 밴드에서 이미 맞은 타겟들 */
	TSet<TWeakObjectPtr<AActor>> HitActors;
};
