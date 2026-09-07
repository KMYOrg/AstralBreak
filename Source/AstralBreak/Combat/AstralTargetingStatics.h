#pragma once

#include "CoreMinimal.h"
#include "AstralTargetingStatics.generated.h"

class AActor;

/**
 * 수동 타겟 전환 방향 — 입력(HeroComponent) → 타게팅(CycleTarget) 경계 타입.
 */
UENUM()
enum class EAstralTargetSwitchDirection : uint8
{
	Left,
	Right
};

/**
 * 후보 선정 튜닝값 — 컴포넌트가 EditDefaultsOnly로 노출하고 순수 함수는 이 값만 받는다.
 */
USTRUCT(BlueprintType)
struct FAstralTargetingParams
{
	GENERATED_BODY()

	/** 획득 반경 (cm) — 락온 입력 시 후보 수집 범위 */
	UPROPERTY(EditDefaultsOnly, Category = "Range", Meta = (ClampMin = "0.0"))
	float AcquireRange = 1500.f;

	/** 유지 반경 (cm) — 획득보다 여유를 둬 경계 깜빡임을 막는다 (유지 축 히스테리시스) */
	UPROPERTY(EditDefaultsOnly, Category = "Range", Meta = (ClampMin = "0.0"))
	float MaintainRange = 2000.f;

	/** 획득 각도 반각 (도) — 카메라 뷰 yaw 기준 수평각 */
	UPROPERTY(EditDefaultsOnly, Category = "Range", Meta = (ClampMin = "0.0", ClampMax = "180.0"))
	float MaxAcquireYaw = 75.f;

	/** 화면 중앙 점수 가중치 — 락온 프로필은 이쪽이 우세 (플레이어가 이미 카메라를 돌린 상태 = 화면 중앙이 의도) */
	UPROPERTY(EditDefaultsOnly, Category = "Score", Meta = (ClampMin = "0.0"))
	float ScreenWeight = 0.7f;

	/** 거리 점수 가중치 — 보조 */
	UPROPERTY(EditDefaultsOnly, Category = "Score", Meta = (ClampMin = "0.0"))
	float DistanceWeight = 0.3f;

	/** 현재 타겟 가산점 */
	UPROPERTY(EditDefaultsOnly, Category = "Score", Meta = (ClampMin = "0.0"))
	float CurrentTargetBonus = 0.15f;

	/** 교체 임계 — 새 후보 점수가 현재 점수 + 이 값을 넘어야 교체 */
	UPROPERTY(EditDefaultsOnly, Category = "Score", Meta = (ClampMin = "0.0"))
	float RetargetThreshold = 0.10f;

	/** LOS 상실 유예 (초) — 이 시간 이상 지속될 때만 해제 (즉시 해제하면 기둥 뒤를 지날 때마다 풀린다) */
	UPROPERTY(EditDefaultsOnly, Category = "Maintain", Meta = (ClampMin = "0.0"))
	float LosGraceTime = 0.5f;
};

/** 후보 1기 — 수집 시점의 스냅샷. 선정 입력이자 디버그 위젯 표시 단위 */
USTRUCT()
struct FAstralTargetCandidate
{
	GENERATED_BODY()

	UPROPERTY()
	TWeakObjectPtr<AActor> Actor;

	/** 폰 위치 → 조준점 거리 (cm) */
	UPROPERTY()
	float Distance = 0.f;

	/** 뷰 yaw 기준 수평각 (도, 좌 음수 / 우 양수) */
	UPROPERTY()
	float YawDeg = 0.f;

	UPROPERTY()
	float Score = 0.f;

	UPROPERTY()
	bool bIsCurrentTarget = false;
};

/**
 * 후보 점수·선정 순수 함수
 * 수집(오버랩·팀·LOS)은 UAstralTargetingComponent가 하고, 여기엔 각도·거리 산술과 히스테리시스 규칙만 둔다
 * (Automation 테스트 대상 — 월드 의존을 인자로 받는다).
 */
namespace AstralTargeting
{
	/** 뷰 위치·yaw에서 타겟까지의 수평각 (도, 부호 있음). 타겟이 뷰 위치와 겹치면 0 */
	ASTRALBREAK_API float ComputeYawDeg(const FVector& ViewLocation, float ViewYaw, const FVector& TargetLocation);

	/** 획득 1차 필터 (거리·각도) — 팀·사망·LOS는 호출자가 */
	ASTRALBREAK_API bool PassesAcquireFilter(float Distance, float YawDeg, const FAstralTargetingParams& Params);

	/**
	 * 점수 = ScreenCenter(0~1) × ScreenWeight + Distance(0~1) × DistanceWeight + (현재 타겟이면) CurrentTargetBonus.
	 * ScreenCenter = 1 - |yaw| / MaxAcquireYaw, Distance = 1 - dist / AcquireRange
	 */
	ASTRALBREAK_API float ScoreCandidate(float Distance, float YawDeg, bool bIsCurrentTarget, const FAstralTargetingParams& Params);

	/**
	 * 최선 후보 인덱스 — 히스테리시스 적용.
	 * CurrentIndex가 유효하면 다른 후보는 현재 점수 + RetargetThreshold를 넘어야 교체된다. 후보 없음 = INDEX_NONE.
	 */
	ASTRALBREAK_API int32 SelectBestCandidate(const TArray<FAstralTargetCandidate>& Candidates, int32 CurrentIndex, const FAstralTargetingParams& Params);

	/** 수동 전환 각도 타이브레이커 허용값 (도) — 이 안이면 각도 동률로 보고 Score → Distance로 넘긴다 */
	constexpr float CycleAngleTolerance = 0.5f;

	/**
	 * 수동 전환 후보 — CurrentYawDeg에서 Direction 쪽으로 가장 가까운 후보.
	 * 타이브레이커: |Step| 최소(CycleAngleTolerance) → Score 높음 → Distance 가까움. bIsCurrentTarget 후보는 제외.
	 */
	ASTRALBREAK_API int32 SelectCycleCandidate(const TArray<FAstralTargetCandidate>& Candidates, float CurrentYawDeg, float Direction);

	/** From → To 수평 방향의 절대 yaw (도). 두 점이 수평으로 겹치면 FallbackYaw */
	ASTRALBREAK_API float ComputeFacingYaw(const FVector& From, const FVector& To, float FallbackYaw);

	/**
	 * CurrentYaw에서 DesiredYaw 쪽으로 최대 MaxAssistYaw만큼만 (도, 정규화된 절대 yaw 반환).
	 * ±180 래핑은 최단 부호각으로 처리 — 단순 뺄셈은 경계에서 방향이 뒤집힌다. 초과 시 폴백이 아니라 클램프 (락온 설계 §5)
	 */
	ASTRALBREAK_API float ClampFacingYaw(float CurrentYaw, float DesiredYaw, float MaxAssistYaw);
}
