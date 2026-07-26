#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AstralGA_Hero_BasicAttack_Melee.generated.h"

class UAnimMontage;
class UAbilityTask_PlayMontageAndWait;

/** 콤보 단계 1개의 데이터 — 배열 길이가 곧 콤보 단수 */
USTRUCT(BlueprintType)
struct FAstralComboStageData
{
	GENERATED_BODY()

	/** 이 단계에서 재생할 몽타주 (히트 노티파이 + 입력 윈도우 밴드 포함) */
	UPROPERTY(EditDefaultsOnly)
	TObjectPtr<UAnimMontage> Montage;

	/** 단계 데미지 배율 — 실데미지 = BaseDamage × 이 값 (보통 후반 타가 높음) */
	UPROPERTY(EditDefaultsOnly, Meta = (ClampMin = "0.0"))
	float DamageMultiplier = 1.0f;

	/** 이 단계 적중 시 표식 수급량 — 보통 마지막 단계(피니셔)에만 (플레이스홀더 축적원, B2에서 조정) */
	UPROPERTY(EditDefaultsOnly, Meta = (ClampMin = "0.0"))
	float MarkGain = 0.0f;

	/** 재생 속도 */
	UPROPERTY(EditDefaultsOnly, Meta = (ClampMin = "0.1"))
	float PlayRate = 1.0f;
};

/**
 * 근접 기본 공격 — 콤보 체인 (단계별 몽타주 방식).
 *
 * 구조: ComboStages 배열의 각 단계가 자기 몽타주를 재생하며,
 *  - 몽타주마다 GameplayEventWindow NotifyState(Begin=ComboWindowOpen, End=ComboBranch) 밴드 1개로 입력 유효 구간을 표시
 *  - 윈도우 열림 이후의 재입력만 버퍼 (이전 선입력/연타는 폐기 — 조작감 오염 방지)
 *  - 윈도우 끝(ComboBranch) 시점에 버퍼가 있으면 다음 단계 몽타주를 재생, 없으면 현재 몽타주가 끝까지 재생되고 종료
 *  - 각 몽타주의 GameplayEvent.Hit 노티파이에서 서버 권위 히트 판정 (공용 ApplyDamageSweep)
 *  - 단계별 데미지 배율/표식 수급은 FAstralComboStageData 데이터로 — 추후 무기 데이터로 이 배열이 이동 가능
 *
 * 단계 전환 시 이전 몽타주 태스크를 EndTask로 먼저 정리한다 — 새 재생이 이전 태스크의
 * OnInterrupted(→EndAbility)를 발화시키는 것을 방지 (같은 슬롯의 몽타주 교체는 인터럽트로 취급되므로).
 * 재입력 감지는 WaitInputPress — ASC의 InputPressed 복제 이벤트라 클라/서버 양쪽 동작.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_BasicAttack_Melee : public UAstralGA_Hero_Base
{
	GENERATED_BODY()

public:
	UAstralGA_Hero_BasicAttack_Melee(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	/** StageIndex 단계의 몽타주 재생 — 이전 스테이지 태스크 정리 포함 */
	void PlayComboStage(int32 StageIndex);

	UFUNCTION()
	void OnMontageCompleted();

	UFUNCTION()
	void OnMontageInterrupted();

	/** 히트 노티파이 — 서버 측 적중 판정 + Damage GE + 수급 (단계 데이터 기반) */
	UFUNCTION()
	void OnHitEventReceived(FGameplayEventData EventData);

	/** 입력 윈도우 열림 — 이 시점 이전의 선입력은 폐기하고 버퍼 접수 시작 */
	UFUNCTION()
	void OnComboWindowOpened(FGameplayEventData EventData);

	/** 입력 윈도우 끝(분기 시점) — 버퍼가 있으면 다음 단계 재생 */
	// TODO: 해당 시점 후 ~ 해당 시점 전 까지 입력 들어오면 콤보 진행되도록 개선 
	UFUNCTION()
	void OnComboBranchReceived(FGameplayEventData EventData);

	/** 재입력 감지 — 윈도우가 열려 있을 때만 버퍼 세팅 (실제 분기는 ComboBranch 시점) */
	UFUNCTION()
	void OnComboInputPressed(float TimeWaited);

	/**
	 * 재입력 대기 무장/해제.
	 * 클라 태스크(WaitInputPress)는 소비 시에만 서버로 입력 RPC를 보내므로,
	 * 로컬(예측 클라/호스트)은 윈도우 구간에만 무장 → 윈도우 안에서 검증된 입력만 서버에 도착한다.
	 * 원격 폰의 서버 인스턴스는 상시 무장 + 무게이트 수용 (도착 입력 = 이미 클라 검증됨).
	 */
	void ArmComboInput();
	void DisarmComboInput();

	/** 아바타가 로컬 제어인지 (예측 클라 또는 리슨서버 호스트) */
	bool IsLocallyControlledAvatar() const;

	/** 버퍼가 있고 다음 단계가 존재하면 콤보 전진 — ComboBranch 노티파이와 몽타주 종료 양쪽에서 호출 */
	bool TryAdvanceCombo();

protected:
	/** 콤보 단계 배열 — 원소 수 = 콤보 단수. BP에서 추가/삭제로 단수 조정 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Combo", Meta = (TitleProperty = "Montage"))
	TArray<FAstralComboStageData> ComboStages;

	/** Damage GE 클래스 (BP에서 GE_Damage_Base 지정) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Combo")
	TSubclassOf<UGameplayEffect> DamageEffectClass;

	/** 기준 데미지 — 단계별 실데미지는 × DamageMultiplier */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Combo")
	float BaseDamage = 25.f;

	/** Sphere Trace 반경 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Combo|Trace")
	float TraceRadius = 80.f;

	/** Trace 거리 (캐릭터 정면) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Combo|Trace")
	float TraceDistance = 200.f;

	/** Trace 시작 오프셋 (캐릭터 중심에서 정면) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Combo|Trace")
	float TraceStartOffset = 50.f;

private:
	/** 현재 콤보 단계 (0-based) */
	int32 ComboIndex = 0;

	/** 입력 윈도우(ComboWindowOpen ~ ComboBranch)가 열려 있는지 */
	bool bComboWindowOpen = false;

	/** 윈도우 내 재입력이 들어왔는지 */
	bool bComboInputBuffered = false;

	/** 현재 스테이지의 몽타주 태스크 — 전환 시 EndTask로 정리 */
	UPROPERTY(Transient)
	TObjectPtr<UAbilityTask_PlayMontageAndWait> ActiveMontageTask;

	/** 현재 무장된 재입력 대기 태스크 (1회 발화) */
	UPROPERTY(Transient)
	TObjectPtr<class UAbilityTask_WaitInputPress> ComboInputTask;
};
