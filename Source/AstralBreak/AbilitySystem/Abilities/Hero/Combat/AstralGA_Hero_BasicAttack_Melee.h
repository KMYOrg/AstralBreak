#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AstralGA_Hero_BasicAttack_Melee.generated.h"

class AAstralWeaponActor;
class UAnimMontage;
class UAbilityTask_PlayMontageAndWait;
class UAstralAbilityTask_WeaponTrace;

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

/** 콤보 스테이지의 몽타주 타임라인 구간 — 서버 입력 게이트의 판정 기준 */
enum class EAstralComboWindowPhase : uint8
{
	/** 스테이지 시작 ~ 윈도우 열림 전 */
	PreWindow,
	/** 윈도우 중 (ComboWindowOpen ~ ComboBranch) */
	WindowOpen,
	/** branch 이후 ~ 몽타주 끝 — 원격 지각 입력은 여기서도 수용된다 (관용 게이트) */
	PostWindow
};

enum class EAstralComboInputState : uint8
{
	None,
	/** 조기 도착 보류 — PreWindow에서만 존재 가능, 윈도우 열림 시 Buffered로 자동 승격 */
	DeferredUntilWindow,
	/** 다음 분기(branch / 몽타주 끝)에서 소비 확정 */
	Buffered
};

/** 콤보 스테이지 1개의 논리 상태 기계 — 윈도우 타임라인 × 입력 수용 상태 */
struct FAstralComboStageState
{
	/** 새 스테이지 시작 — 두 상태 동시 리셋. 보류분 이월 금지 (이월되면 branch 직후 스팸이 다음 스테이지 입력을 선점) */
	void BeginStage();

	/** 윈도우 열림 (PreWindow에서만 합법) — 보류분을 버퍼로 승격. 위반 = 노티파이 설정 오류 (ensure + false) */
	bool OpenWindow();

	/** 윈도우 닫힘 = branch 시점 (WindowOpen에서만 합법). 위반 = 노티파이 설정 오류 (ensure + false) */
	bool CloseWindow();

	/** 로컬(예측 클라/호스트) 입력 — 윈도우 중에만 버퍼. */
	void ReceiveLocalInput();

	/** 원격 입력(서버 인스턴스) — 클라 검증을 신뢰하지 않고 서버 자신의 타임라인 구간으로 3분기 */
	void ReceiveRemoteInput();

	/** 버퍼 소비 — Buffered일 때만 true. Deferred는 소비 불가 (윈도우 전 진행을 소비 규칙 자체가 차단) */
	bool ConsumeBufferedInput();

	bool IsWindowOpen() const { return WindowPhase == EAstralComboWindowPhase::WindowOpen; }
	bool HasBufferedInput() const { return InputState == EAstralComboInputState::Buffered; }

private:
	EAstralComboWindowPhase WindowPhase = EAstralComboWindowPhase::PreWindow;
	EAstralComboInputState InputState = EAstralComboInputState::None;
};

/**
 * 근접 기본 공격 — 콤보 체인 (단계별 몽타주 방식).
 *
 * 구조: ComboStages 배열의 각 단계가 자기 몽타주를 재생하며,
 *  - 몽타주마다 GameplayEventWindow NotifyState(Begin=ComboWindowOpen, End=ComboBranch) 밴드 1개로 입력 유효 구간을 표시
 *  - 윈도우 열림 이후의 재입력만 버퍼 (이전 선입력/연타는 폐기 — 조작감 오염 방지)
 *  - 윈도우 끝(ComboBranch) 시점에 버퍼가 있으면 다음 단계 몽타주를 재생, 없으면 현재 몽타주가 끝까지 재생되고 종료
 *  - 각 몽타주의 트레이스 밴드(WeaponTrace.Begin~End)에서 무기 소켓 연속 스윕 판정 (AbilityTask_WeaponTrace, 서버 권위)
 *  - 무기는 SourceObject(EquipmentInstance) 경유 — 이 GA 자체가 무기 장비의 AbilitySet으로 부여된다
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

	/** 트레이스 밴드 시작 — authority에서 무기 트레이스 태스크 시작 */
	UFUNCTION()
	void OnWeaponTraceBegin(FGameplayEventData EventData);

	/** 트레이스 밴드 끝 — 태스크 종료 */
	UFUNCTION()
	void OnWeaponTraceEnd(FGameplayEventData EventData);

	/** 무기 적중 (타겟당 1회) — Damage GE + 수급 (단계 데이터 기반, MarkGain은 밴드당 1회) */
	UFUNCTION()
	void OnWeaponHit(const FHitResult& HitResult);

	void StopWeaponTrace();

	/** 입력 윈도우 열림 — 상태 전이(OpenWindow, 보류분 승격 포함) + 로컬은 재입력 무장 시작 */
	UFUNCTION()
	void OnComboWindowOpened(FGameplayEventData EventData);

	/** 입력 윈도우 끝(분기 시점) — 상태 전이(CloseWindow) + 버퍼가 있으면 다음 단계 재생 */
	// TODO: 해당 시점 후 ~ 해당 시점 전 까지 입력 들어오면 콤보 진행되도록 개선
	UFUNCTION()
	void OnComboBranchReceived(FGameplayEventData EventData);

	/** 재입력 감지 — 수용/보류 판정은 FAstralComboStageState의 Receive{Local,Remote}Input이 담당 */
	UFUNCTION()
	void OnComboInputPressed(float TimeWaited);

	/**
	 * 재입력 대기 무장/해제.
	 * 클라 태스크(WaitInputPress)는 소비 시에만 서버로 입력 RPC를 보내므로,
	 * 로컬(예측 클라/호스트)은 윈도우 구간에만 무장 → 윈도우 안에서 검증된 입력만 서버에 도착한다.
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

	/** 기준 데미지 — 단계별 실데미지는 × DamageMultiplier (Damage GE는 GameData 전역) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Combo")
	float BaseDamage = 25.f;

	/** 무기 트레이스 스피어 반경 — 적중률이 낮으면 반경/밴드 구간을 넓힐 것 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Combo|Trace")
	float WeaponTraceRadius = 25.f;

private:
	/** 현재 콤보 단계 (0-based) */
	int32 ComboIndex = 0;

	/** 현재 스테이지의 윈도우/입력 상태 기계 */
	FAstralComboStageState ComboStageState;

	/** 현재 스테이지의 몽타주 태스크 — 전환 시 EndTask로 정리 */
	UPROPERTY(Transient)
	TObjectPtr<UAbilityTask_PlayMontageAndWait> ActiveMontageTask;

	/** 현재 무장된 재입력 대기 태스크 (1회 발화) */
	UPROPERTY(Transient)
	TObjectPtr<class UAbilityTask_WaitInputPress> ComboInputTask;

	/** 진행 중인 무기 트레이스 태스크 (밴드 1개 수명, 서버 전용) */
	UPROPERTY(Transient)
	TObjectPtr<UAstralAbilityTask_WeaponTrace> WeaponTraceTask;

	/** 이번 밴드의 무기 액터 (밴드 시작 시 SourceObject 경유 확보) */
	UPROPERTY(Transient)
	TObjectPtr<AAstralWeaponActor> ActiveWeaponActor;

	/** 이번 밴드에서 표식 수급을 이미 했는지 (밴드당 1회 게이트) */
	bool bMarkGainedThisBand = false;
};
