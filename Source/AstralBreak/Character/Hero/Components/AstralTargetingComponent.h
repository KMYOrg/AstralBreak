#pragma once

#include "CoreMinimal.h"
#include "Components/PawnComponent.h"
#include "Combat/AstralTargetHandle.h"
#include "Combat/AstralTargetingStatics.h"
#include "AstralTargetingComponent.generated.h"

class UAstralHealthComponent;

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FAstralTargetingChangedDelegate);

/** 타게팅 모드. M2.5는 Idle ↔ HardLocked 전이만 — SoftTracking(어택 어시스트)은 자리만 확보 */
UENUM(BlueprintType)
enum class EAstralTargetingMode : uint8
{
	Idle,
	/** 공격 1회 동안의 자동 보조 — 이후 단계 (현재 전이 없음) */
	SoftTracking,
	/** 락온 버튼 토글 — 해제할 때까지 유지 */
	HardLocked
};

/**
 * 락온 타게팅 — 후보 탐색 · 점수 · 상태 기계 [히어로 전용 · 로컬 전용].
 * 갱신 주기 (3층):
 *   매 프레임         — 약한 참조 유효성 (타겟 액터 소멸 즉시 해제)
 *   MaintainInterval  — 유지 조건: CanDamage(사망·팀) · MaintainRange · LOS 유예
 *   락온 입력 시      — 전체 후보 수집 + 점수
 * 네트워크: 복제 없음. 선정은 로컬 클라(리슨 호스트 포함)가 하고 서버는 5단계에서 검증만 한다.
 */
UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralTargetingComponent : public UPawnComponent
{
	GENERATED_BODY()

public:
	UAstralTargetingComponent(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	UFUNCTION(BlueprintPure, Category = "Astral|Targeting")
	static UAstralTargetingComponent* FindTargetingComponent(const AActor* Actor) { return (Actor ? Actor->FindComponentByClass<UAstralTargetingComponent>() : nullptr); }

	/** Idle → HardLocked. 후보 수집·점수 → 최선 후보. 후보가 없으면 no-op(false). 이미 HardLocked면 유지(true) */
	bool TryLockOn();

	/** HardLocked → Idle. 다음 후보로 자동 전환하지 않는다 */
	void ClearLock();

	/** 락온 입력(토글) — 상태 차트의 "락온 입력" 전이: HardLocked면 해제, 아니면 획득 시도 */
	void ToggleLockOn();

	/**
	 * Direction 부호 쪽(현재 타겟 기준 최단 각)으로 가장 가까운 후보로 전환.
	 * 후보 집합은 획득 필터 그대로(AcquireRange·MaxAcquireYaw·LOS·CanDamage) — 카메라 뒤·벽 뒤·사거리 밖으로는 전환되지 않는다.
	 */
	bool CycleTarget(float Direction);

	UFUNCTION(BlueprintPure, Category = "Astral|Targeting")
	EAstralTargetingMode GetMode() const { return Mode; }

	/** 현재 유효 타겟 — 하드 락 우선 (SoftTracking 도입 시 폴백이 여기 붙는다). 없으면 빈 핸들 */
	const FAstralTargetHandle& GetEffectiveTarget() const;

	/** 디버그 — 마지막 수집의 후보 (점수 내림차순). 비Shipping에선 MaintainInterval마다 갱신 */
	const TArray<FAstralTargetCandidate>& GetDebugCandidates() const { return DebugCandidates; }

	/** 디버그 — 히스테리시스를 적용해 "지금 선정한다면" 뽑힐 후보. HardLocked 중에도 자동 적용되지 않는다 */
	const AActor* GetDebugBestCandidate() const { return DebugBestCandidate.Get(); }

	/** 디버그 — LOS 상실 누적 (초). LosGraceTime 도달 시 해제 */
	float GetLosLostTime() const { return LosLostTime; }
	
	UPROPERTY(BlueprintAssignable, Category = "Astral|Targeting")
	FAstralTargetingChangedDelegate OnTargetingChanged;

protected:
	//~UActorComponent
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
	//~End UActorComponent

	/** 후보 수집 + 점수 — 오버랩(Pawn 오브젝트) ∧ CanDamage ∧ 획득 각도 ∧ LOS. 점수 내림차순 정렬 */
	void GatherCandidates(TArray<FAstralTargetCandidate>& OutCandidates) const;

	/** 유지 조건 검사 (MaintainInterval 주기) — 하나라도 깨지면 ClearLock */
	void CheckMaintainConditions(float Interval);

	/** 폰 캡슐 중심 → 조준점 AstralTargetLOS 채널 트레이스 (월드 지오메트리만 가린다). 타겟 자신에 막히는 것은 가시로 본다 */
	bool HasLineOfSight(const AActor* Target, const FVector& AimLocation) const;

	/** 로컬 뷰포인트 — 로컬 제어 PlayerController가 없으면 false */
	bool GetViewPoint(FVector& OutLocation, FRotator& OutRotation) const;

	/** 내 사망 → 해제 (HealthComponent::OnDeathStarted) */
	UFUNCTION()
	void HandleOwnerDeathStarted(AActor* OwningActor);

	void CommitTargetingState(EAstralTargetingMode NewMode, const FAstralTargetHandle& NewTarget);

#if !UE_BUILD_SHIPPING
	/** 디버그 후보 갱신 — 정식 선정 경로가 아니다 (위젯 표시·가중치 튜닝용) */
	void RefreshDebugCandidates();

	void DrawDebug() const;
#endif

protected:
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Targeting", Meta = (ShowOnlyInnerProperties))
	FAstralTargetingParams Params;

	/** 유지 조건 검사 주기 (초) — 거리·LOS·CanDamage는 매 프레임 볼 필요가 없다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Targeting", Meta = (ClampMin = "0.02"))
	float MaintainInterval = 0.15f;

	/** 디버그 — 후보 주기 갱신 + 드로잉 (비Shipping 전용, Shipping에선 무시) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Targeting|Debug")
	bool bEnableDebug = true;

private:
	EAstralTargetingMode Mode = EAstralTargetingMode::Idle;

	UPROPERTY(Transient)
	FAstralTargetHandle HardLockTarget;

	/** 유지 검사 누적 시간 — 타겟이 바뀌면 CommitTargetingState가 리셋 */
	float MaintainAccumulator = 0.f;

	/** LOS 상실 누적 (초) — 회복 시 0. 타겟이 바뀌면 CommitTargetingState가 리셋 */
	float LosLostTime = 0.f;

	UPROPERTY(Transient)
	TArray<FAstralTargetCandidate> DebugCandidates;

	UPROPERTY(Transient)
	TWeakObjectPtr<AActor> DebugBestCandidate;

	UPROPERTY(Transient)
	TObjectPtr<UAstralHealthComponent> BoundHealthComponent;
};
