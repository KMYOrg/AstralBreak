#pragma once

#include "CoreMinimal.h"
#include "Combat/AstralTargetingStatics.h"
#include "AstralTargetSwitchInput.generated.h"

UENUM()
enum class EAstralStickSwitchPhase : uint8
{
	Neutral,
	LatchedLeft,
	LatchedRight
};

/**
 * 마우스 타겟 전환 페이즈 — 마우스에는 중립이 없어 "짧은 창 안에 충분히 움직임 = 한 번 젖힘"으로 정의
 */
UENUM()
enum class EAstralMouseSwitchPhase : uint8
{
	/** 전환 가능, 창 없음 */
	Armed,
	/** 창 열림 — 첫 입력 시각 기준으로 누적 중 */
	Accumulating,
	/** 전환 직후 — RearmPause 이상 멈출 때까지 입력 폐기 */
	WaitingForPause
};

/** 타겟 전환 입력 튜닝값 — 스틱(정규화 축)과 마우스(delta 누적)는 단위가 달라 임계도 따로다. 소유·편집은 HeroComponent(BP) */
USTRUCT(BlueprintType)
struct FAstralTargetSwitchInputParams
{
	GENERATED_BODY()

	/** 스틱 — latch 걸림 (|X| 이상). 반대쪽 직접 전이(LatchedRight 중 X ≤ −Engage)도 이 값 */
	UPROPERTY(EditDefaultsOnly, Category = "Target Switch", Meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float StickEngageThreshold = 0.6f;

	/** 스틱 — latch 해제 (|X| 이하). Completed 전에 반대로 꺾는 경로를 덮는다. Engage보다 작아야 한다 */
	UPROPERTY(EditDefaultsOnly, Category = "Target Switch", Meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float StickReleaseThreshold = 0.3f;

	/**  마우스 — 부호 있는 누적 delta 임계. 0 이하 = 마우스 전환 비활성 (누적·위젯 표시는 계속된다). */
	UPROPERTY(EditDefaultsOnly, Category = "Target Switch", Meta = (ClampMin = "0.0"))
	float MouseAccumulationThreshold = 0.f;

	/** 마우스 — 첫 입력부터 이 시간 안에 임계를 넘겨야 전환. */
	UPROPERTY(EditDefaultsOnly, Category = "Target Switch", Meta = (ClampMin = "0.0"))
	float MouseAccumulationWindow = 0.15f;

	/** 마우스 — 전환 후 재 타게팅에 필요한 입력 공백 */
	UPROPERTY(EditDefaultsOnly, Category = "Target Switch", Meta = (ClampMin = "0.0"))
	float MouseRearmPause = 0.15f;
};

/** 전환 결과 — 미설정 = 이번 입력으로는 전환하지 않는다 */
using FAstralTargetSwitchResult = TOptional<EAstralTargetSwitchDirection>;

#if !UE_BUILD_SHIPPING
/** 디버그 관측 — 위젯이 읽기만 한다. 상태 소유자(Processor)가 생산 */
struct FAstralTargetSwitchInputDebugSnapshot
{
	EAstralStickSwitchPhase StickPhase = EAstralStickSwitchPhase::Neutral;
	EAstralMouseSwitchPhase MousePhase = EAstralMouseSwitchPhase::Armed;

	/** 현재 창 안의 부호 있는 누적 (우 +) */
	float MouseAccumulation = 0.f;

	/** 현재 창의 첫 입력 후 경과 (초). 창 없음 = −1 */
	float WindowAge = -1.f;

	/** 마지막 마우스 입력 후 경과 (초). 없음 = −1 */
	float IdleAge = -1.f;

	/** 임계 (0 이하 = 비활성) — 위젯이 Params를 따로 볼 필요 없게 */
	float AccumulationThreshold = 0.f;
};
#endif

struct ASTRALBREAK_API FAstralTargetSwitchInputProcessor
{
	/** 스틱 X (정규화, 우 +). Triggered마다 호출 — X가 0이어도 부른다 (해제 임계 판정) */
	FAstralTargetSwitchResult ConsumeStick(float AxisX, const FAstralTargetSwitchInputParams& Params);

	/** 스틱 Completed (값 0 복귀, 1회) — 어느 latch 상태에서든 Neutral */
	void CompleteStick();

	/** 마우스 X 델타 (우 +). Now = 월드 초 */
	FAstralTargetSwitchResult ConsumeMouse(float DeltaX, double Now, const FAstralTargetSwitchInputParams& Params);

	/** latch · 누적 창 · 재무장 전부 초기화 — 락온 세션 경계와 락온 밖 Look 입력에서 */
	void Reset();

#if !UE_BUILD_SHIPPING
	FAstralTargetSwitchInputDebugSnapshot MakeDebugSnapshot(double Now, const FAstralTargetSwitchInputParams& Params) const;
#endif

private:
	EAstralStickSwitchPhase StickPhase = EAstralStickSwitchPhase::Neutral;

	EAstralMouseSwitchPhase MousePhase = EAstralMouseSwitchPhase::Armed;

	/** 마우스 부호 있는 누적 delta (우 +) — 현재 창 안의 합 */
	float MouseAccumulation = 0.f;

	/** 현재 누적 창의 첫 입력 시각 (월드 초). 음수 = 창 없음 */
	double MouseWindowStartTime = -1.0;

	/** 마지막 마우스 입력 시각 (월드 초). 음수 = 없음. 입력 공백 판정의 기준 */
	double LastMouseInputTime = -1.0;
};
