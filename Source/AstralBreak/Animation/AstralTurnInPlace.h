#pragma once

#include "CoreMinimal.h"
#include "Kismet/KismetMathLibrary.h"
#include "AstralTurnInPlace.generated.h"

/**
 * 제자리 회전(TurnInPlace) — Lyra ABP_Mannequin_Base 의 RootYawOffset 기계를 순수 함수로 옮긴 것.
 * 원리: 폰(액터)이 컨트롤러 Yaw 를 따라 돌면 메시도 같이 돌아 발이 미끄러진다. 서 있는 동안은 액터가 돈 만큼 루트 본을
 * 반대로 돌려(RootYawOffset) 발을 땅에 붙여 두고, 오프셋이 임계를 넘으면 턴 클립을 재생해 그 클립이 돌린 만큼
 * 오프셋을 되돌린다(클립의 RemainingTurnYaw 커브). 움직이면 스프링으로 0 에 수렴시킨다.
 * 조준 중에만 쓰는 것은 호출자(AnimInstance)의 정책 — 여기는 bAccumulate 입력으로만 받는다.
 * 월드·UObject 의존이 없어 Automation 테스트(AstralBreak.TurnInPlace.*)로 고정한다.
 */

/** 턴 클립 선택 — 공급자 ABP 의 BlendListByEnum 이 이 값으로 4개 클립 중 하나를 고른다 */
UENUM(BlueprintType)
enum class EAstralTurnInPlaceKind : uint8
{
	None,
	Left90,
	Left180,
	Right90,
	Right180,
};

USTRUCT(BlueprintType)
struct FAstralTurnInPlaceSettings
{
	GENERATED_BODY()

	/**
	 * 오프셋 클램프(±도). 너무 크면 AimOffset 이 등 뒤를 조준해 척추가 꼬인다 (Lyra #3). 180 미만이어야 한다 — 누적은 정규화 없이 이 범위에서
	 * 잘라 ±180 을 넘으며 부호가 뒤집히는(240° 점프) 일을 막는다.
	 * 조준 중 상체가 되돌려야 할 각(AimYaw = −오프셋)이 AimOffset Yaw 범위(±90) + 최종 조준 보정 최대각(30)을 넘지 않게 120 — 넘으면 빠른 플릭에서
	 * 총열이 그 차이만큼 탄도와 어긋났다(2026-10-22 실측: 150 일 때 |AimYaw| 144 에서 24.7°). 대가로 그보다 빠른 회전은 발이 미끄러진다(Lyra 정지 클램프도 이 수준).
	 * Turn180Threshold 보다 작으면 180 클립은 선택되지 않고 90 클립이 이어진다 — 180 클립을 쓰려면 이 값과 AO 범위·보정 최대각을 함께 올린다
	 */
	UPROPERTY(EditAnywhere, Category = "TurnInPlace", Meta = (ClampMin = "0.0", ClampMax = "179.0"))
	float RootYawOffsetClamp = 120.f;

	/** |오프셋| 이 이 값을 넘으면 턴 클립 요청 */
	UPROPERTY(EditAnywhere, Category = "TurnInPlace", Meta = (ClampMin = "0.0", ClampMax = "180.0"))
	float TurnThreshold = 50.f;

	/** |오프셋| 이 이 값 이상이면 180 클립, 아니면 90 클립 */
	UPROPERTY(EditAnywhere, Category = "TurnInPlace", Meta = (ClampMin = "0.0", ClampMax = "180.0"))
	float Turn180Threshold = 135.f;

	/** 이동 중 오프셋을 0 으로 되돌리는 스프링 (Lyra: 80 / 1.0) */
	UPROPERTY(EditAnywhere, Category = "TurnInPlace", Meta = (ClampMin = "0.0"))
	float BlendOutStiffness = 80.f;

	UPROPERTY(EditAnywhere, Category = "TurnInPlace", Meta = (ClampMin = "0.0"))
	float BlendOutCriticalDamping = 1.f;

	/**
	 * 턴 클립이 "활성" 으로 보이는 TurnYawWeight 커브 최소값. Lyra 처럼 사실상 0 — RemainingTurnYaw 를 TurnYawWeight 로 나누는 가중 해제가
	 * 블렌드 인 첫 프레임부터 온전한 각을 주므로, 임계를 올리면 그만큼 보정 없이 회전이 새어 발이 미끄러진다.
	 * 클립↔클립 전이는 관성(Inertialization) 블렌드여야 한다 — 표준 크로스페이드면 두 클립의 커브가 가중 합산되어 가짜 델타가 생긴다
	 */
	UPROPERTY(EditAnywhere, Category = "TurnInPlace", Meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float AnimActiveWeightThreshold = 0.001f;

	/** 가중 해제한 RemainingTurnYaw 가 이 값(도) 이하이면 회전 구간 종료 → Recovery */
	UPROPERTY(EditAnywhere, Category = "TurnInPlace", Meta = (ClampMin = "0.0"))
	float RotationFinishedTolerance = 1.f;

	/**
	 * 새 클립 시작 감지 — 남은 각의 크기가 지난 프레임보다 이만큼(도) 이상 커지거나 부호가 바뀌면 "클립이 바뀌었다" 고 보고 그 프레임의 델타를 버린다.
	 * Lyra 의 "이전 값이 0 이면 건너뜀" 은 Recovery → Rotation 즉시 재진입(연속 회전)에서 이전 값이 0.3 같은 꼬리값이라 실패해
	 * 새 클립의 첫 값(90·−180)과의 차이를 통째로 오프셋에 넣었다
	 */
	UPROPERTY(EditAnywhere, Category = "TurnInPlace", Meta = (ClampMin = "0.0"))
	float NewClipTolerance = 2.f;

	/**
	 * 회전 구간이 끝난 뒤 이 시간(초)이 지나야 다음 턴을 요청한다 (Recovery → Rotation 재진입 게이트).
	 * 관성 시간(0.2)보다 길고 스텝 끝 무렵인 값. 기다리는 동안 오프셋은 계속 쌓이고(발 고정) 상체는 AimOffset(AimYaw = −오프셋)으로 카메라를 따른다.
	 * 0 이면 Lyra 처럼 즉시 재진입
	 */
	UPROPERTY(EditAnywhere, Category = "TurnInPlace", Meta = (ClampMin = "0.0"))
	float ReentryMinRecoveryTime = 0.3f;
};

/** 프레임 입력 — AnimInstance 가 게임 스레드 스냅샷·커브에서 채운다 */
struct FAstralTurnInPlaceInput
{
	float DeltaSeconds = 0.f;
	/** 액터 Yaw 의 이번 프레임 변화량(정규화, 도) */
	float YawDeltaSinceLastUpdate = 0.f;
	/** 발을 붙여 둘 조건 — 조준 중 ∧ 지상 ∧ 정지 ∧ 몽타주 없음 (정책은 호출자) */
	bool bAccumulate = false;
	/** 턴 클립 커브 (Lyra TurnYawAnimModifier 가 구운 TurnYawWeight · RemainingTurnYaw) */
	float TurnYawWeightCurve = 0.f;
	float RemainingTurnYawCurve = 0.f;
};

/** 프레임마다 Update 로 전진하는 상태. 출력은 AnimInstance 가 UPROPERTY 로 복사한다 */
struct FAstralTurnInPlaceState
{
	/** 루트 본에 줄 Yaw(도). RotateRootBone.Yaw ← 이것, AimYaw ← −이것 */
	float RootYawOffset = 0.f;

	/** 가중 해제한 RemainingTurnYaw (클립 비활성이면 0) */
	float TurnYawCurveValue = 0.f;
	float PreviousTurnYawCurveValue = 0.f;

	/** 턴 클립이 활성인 동안 누적한 시간 — Recovery 상태의 SequencePlayer StartPosition (회전 구간이 끝난 지점부터 이어서) */
	float TurnAnimTime = 0.f;
	bool bTurnAnimActive = false;

	/** 마지막 회전 구간(클립 활성 ∧ 미완료)이 끝난 뒤 흐른 시간 — 재진입 게이트. 회전 이력이 없으면 충분히 큰 값 */
	float TimeSinceRotation = NoRotationYet;

	/**
	 * |오프셋| > TurnThreshold ∧ 누적 중 ∧ 회전 구간 밖 ∧ 재진입 게이트 통과 — Idle → TurnInPlaceRotation · Recovery → Rotation 전이 조건.
	 * 회전 구간 안에선 항상 false — 상태머신은 그 동안 이 값을 보지 않고, 여기서 상승 에지가 나면 클립이 상태 안에서 바뀐다
	 */
	bool bWantsTurn = false;
	/** 클립 활성 ∧ |TurnYawCurveValue| ≤ 허용 — Rotation → Recovery 전이 조건 */
	bool bRotationFinished = false;
	/** bWantsTurn 의 상승 에지(= Rotation 진입)에서 고른 클립. 회전 중 바뀌지 않고, Recovery 도 같은 클립을 쓴다 */
	EAstralTurnInPlaceKind Kind = EAstralTurnInPlaceKind::None;

	FFloatSpringState BlendOutSpring;

	static constexpr float NoRotationYet = 1.0e4f;

	/** 턴 클립의 회전 구간 안인가 (커브 활성 ∧ 남은 각 > 허용) — Rotation 상태와 같은 구간 */
	bool IsInRotation() const { return bTurnAnimActive && !bRotationFinished; }

	void Reset();

	/** 한 프레임 전진 (Lyra 순서: 커브 처리 → 누적/복귀 → 클램프 → 요청 판정) */
	void Update(const FAstralTurnInPlaceSettings& Settings, const FAstralTurnInPlaceInput& Input);

	/**
	 * 오프셋 부호·크기로 클립 선택. 오프셋 < 0 = 메시가 액터보다 왼쪽을 보고 있다(액터가 오른쪽으로 돌았다) → 메시를 오른쪽으로
	 * 돌리는 Right 클립. 클립의 RemainingTurnYaw 커브 부호가 실제 회전 부호와 같다는 전제(TurnYawAnimModifier) —
	 * Update 가 그 커브 델타를 오프셋에서 빼므로 올바른 클립이면 오프셋이 0 으로 수렴한다
	 */
	static EAstralTurnInPlaceKind SelectKind(float InRootYawOffset, const FAstralTurnInPlaceSettings& Settings);
};
