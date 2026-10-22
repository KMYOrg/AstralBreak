#include "AstralTurnInPlace.h"

void FAstralTurnInPlaceState::Reset()
{
	RootYawOffset = 0.f;
	TurnYawCurveValue = 0.f;
	PreviousTurnYawCurveValue = 0.f;
	TurnAnimTime = 0.f;
	bTurnAnimActive = false;
	TimeSinceRotation = NoRotationYet;
	bWantsTurn = false;
	bRotationFinished = false;
	Kind = EAstralTurnInPlaceKind::None;
	BlendOutSpring.Reset();
}

EAstralTurnInPlaceKind FAstralTurnInPlaceState::SelectKind(float InRootYawOffset, const FAstralTurnInPlaceSettings& Settings)
{
	const bool bFull = FMath::Abs(InRootYawOffset) >= Settings.Turn180Threshold;
	if (InRootYawOffset < 0.f)
	{
		return bFull ? EAstralTurnInPlaceKind::Right180 : EAstralTurnInPlaceKind::Right90;
	}
	return bFull ? EAstralTurnInPlaceKind::Left180 : EAstralTurnInPlaceKind::Left90;
}

void FAstralTurnInPlaceState::Update(const FAstralTurnInPlaceSettings& Settings, const FAstralTurnInPlaceInput& Input)
{
	// ---- 1. 턴 클립 커브 (Lyra #5 ProcessTurnYawCurve) ----
	// TurnYawWeight 는 턴 클립 안에서 1 이므로 GetCurveValue 가 돌려주는 값이 곧 클립의 현재 가중치 —
	// 그것으로 RemainingTurnYaw 를 "가중 해제" 해야 블렌드 중에도 온전한 남은 각도가 나온다
	const bool bWasActive = bTurnAnimActive;
	bTurnAnimActive = Input.TurnYawWeightCurve > Settings.AnimActiveWeightThreshold;
	if (!bTurnAnimActive)
	{
		TurnYawCurveValue = 0.f;
		PreviousTurnYawCurveValue = 0.f;
		TurnAnimTime = 0.f;
		bRotationFinished = false;
	}
	else
	{
		PreviousTurnYawCurveValue = TurnYawCurveValue;
		TurnYawCurveValue = Input.RemainingTurnYawCurve / Input.TurnYawWeightCurve;

		// 클립이 막 시작한 프레임의 델타는 가짜다 — "0 → 90"(Lyra: 이전 값 0) 뿐 아니라 연속 회전으로 Recovery → Rotation 에 즉시 재진입하면
		// 이전 값이 꼬리값(0.3)이고 새 값이 90·−180 이라 "남은 각이 커진다/부호가 바뀐다" 로 드러난다. 클립 안에서 남은 각은 단조 감소만 하므로
		// 크기가 허용치 이상 커지거나 부호가 바뀌면 새 클립으로 보고 건너뛴다 (관성 전이라 가중치 1 → 가중 해제 값이 곧 클립 값)
		const bool bFirstFrame = PreviousTurnYawCurveValue == 0.f;
		const bool bGrew = FMath::Abs(TurnYawCurveValue) > FMath::Abs(PreviousTurnYawCurveValue) + Settings.NewClipTolerance;
		const bool bFlipped = !bFirstFrame && TurnYawCurveValue != 0.f && FMath::Sign(TurnYawCurveValue) != FMath::Sign(PreviousTurnYawCurveValue);
		if (!bFirstFrame && !bGrew && !bFlipped)
		{
			RootYawOffset -= (TurnYawCurveValue - PreviousTurnYawCurveValue);
		}

		// 클립 시간 — 새 클립이면 처음부터. 연속 재진입에선 커브 가중치가 0 까지 안 내려가(관성 블렌드) 활성이 끊기지 않으므로 활성 여부만으론 리셋되지 않는다
		// (2026-10-20 PIE: 세 번째 클립의 Recovery 가 StartPosition 1.22초 = 회전 구간을 한참 지난 자세에서 시작 → 발 순간 이동)
		TurnAnimTime = (bWasActive && !bGrew && !bFlipped) ? TurnAnimTime + Input.DeltaSeconds : 0.f;
		bRotationFinished = FMath::Abs(TurnYawCurveValue) <= Settings.RotationFinishedTolerance;
	}
	// 재진입 게이트 시계 — 회전 구간 동안 0, 끝나면(Recovery·Idle) 흐른다
	TimeSinceRotation = IsInRotation() ? 0.f : FMath::Min(TimeSinceRotation + Input.DeltaSeconds, NoRotationYet);

	// ---- 2. 누적 / 복귀 (Lyra #2 UpdateRootYawOffset) ----
	if (Input.bAccumulate)
	{
		// 발을 붙여 둔다 — 액터가 돈 만큼 루트를 반대로. 델타만 정규화하고 합은 정규화하지 않는다 — 클램프(<180)가 범위를 지키므로
		// ±180 을 넘으며 부호가 뒤집히는 일(120 → −120 = 240° 점프)이 없다. 빠른 마우스 회전에서 "메시가 휙" 의 또 다른 원인이었다
		RootYawOffset = FMath::Clamp(RootYawOffset - FRotator::NormalizeAxis(Input.YawDeltaSinceLastUpdate), -Settings.RootYawOffsetClamp, Settings.RootYawOffsetClamp);
		BlendOutSpring.Reset();
	}
	else
	{
		// 움직이거나 조준이 풀리면 스프링으로 0 에 수렴 (오프셋이 작으면 그냥 0 — 스프링 잔진동 방지)
		if (FMath::Abs(RootYawOffset) < 0.05f)
		{
			RootYawOffset = 0.f;
			BlendOutSpring.Reset();
		}
		else
		{
			RootYawOffset = UKismetMathLibrary::FloatSpringInterp(RootYawOffset, 0.f, BlendOutSpring, Settings.BlendOutStiffness, Settings.BlendOutCriticalDamping,
				Input.DeltaSeconds, /*Mass*/ 1.f, /*TargetVelocityAmount*/ 0.5f);
		}
	}

	// ---- 3. 클램프 (Lyra #3) — 정규화 없이. 커브 델타가 범위를 넘겨도 잘라낼 뿐 뒤집지 않는다
	RootYawOffset = FMath::Clamp(RootYawOffset, -Settings.RootYawOffsetClamp, Settings.RootYawOffsetClamp);

	// ---- 4. 턴 요청 · 클립 선택 (Lyra #6 — 상태머신 전이 조건) ----
	// 회전 구간 안에선 요청하지 않는다 — 상태머신이 Rotation 에 있는 동안 상승 에지가 나면 Kind 가 바뀌어 BlendListByEnum 이 상태 안에서 클립을 갈아 끼운다
	// (회전 중 반대로 돌려 오프셋이 임계 아래로 내려갔다 반대편으로 넘는 경우). 회전이 끝난 뒤엔 ReentryMinRecoveryTime 동안 발이 자리 잡기를 기다린다
	const bool bWasWanting = bWantsTurn;
	const bool bCanStartTurn = !IsInRotation() && TimeSinceRotation >= Settings.ReentryMinRecoveryTime;
	bWantsTurn = Input.bAccumulate && bCanStartTurn && FMath::Abs(RootYawOffset) > Settings.TurnThreshold;
	if (bWantsTurn && !bWasWanting)
	{
		// 상승 에지 = Rotation 진입에서만 고정 — 게이트 동안 더 쌓인 오프셋으로 고르므로 기다린 만큼 180 클립이 선택될 수 있다. Recovery 는 같은 클립을 이어 재생한다
		Kind = SelectKind(RootYawOffset, Settings);
	}
}
