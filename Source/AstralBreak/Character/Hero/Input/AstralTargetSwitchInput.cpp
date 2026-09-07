#include "AstralTargetSwitchInput.h"

FAstralTargetSwitchResult FAstralTargetSwitchInputProcessor::ConsumeStick(float AxisX, const FAstralTargetSwitchInputParams& Params)
{
	const float Engage = Params.StickEngageThreshold;
	const float Release = FMath::Min(Params.StickReleaseThreshold, Engage);

	switch (StickPhase)
	{
	case EAstralStickSwitchPhase::Neutral:
		if (AxisX >= Engage)
		{
			StickPhase = EAstralStickSwitchPhase::LatchedRight;
			return EAstralTargetSwitchDirection::Right;
		}
		if (AxisX <= -Engage)
		{
			StickPhase = EAstralStickSwitchPhase::LatchedLeft;
			return EAstralTargetSwitchDirection::Left;
		}
		break;

	case EAstralStickSwitchPhase::LatchedRight:
		if (FMath::Abs(AxisX) <= Release)
		{
			StickPhase = EAstralStickSwitchPhase::Neutral;
		}
		else if (AxisX <= -Engage)
		{
			StickPhase = EAstralStickSwitchPhase::LatchedLeft;
			return EAstralTargetSwitchDirection::Left;
		}
		break;

	case EAstralStickSwitchPhase::LatchedLeft:
		if (FMath::Abs(AxisX) <= Release)
		{
			StickPhase = EAstralStickSwitchPhase::Neutral;
		}
		else if (AxisX >= Engage)
		{
			StickPhase = EAstralStickSwitchPhase::LatchedRight;
			return EAstralTargetSwitchDirection::Right;
		}
		break;
	}

	return FAstralTargetSwitchResult();
}

void FAstralTargetSwitchInputProcessor::CompleteStick()
{
	StickPhase = EAstralStickSwitchPhase::Neutral;
}

FAstralTargetSwitchResult FAstralTargetSwitchInputProcessor::ConsumeMouse(float DeltaX, double Now, const FAstralTargetSwitchInputParams& Params)
{
	// 입력 공백 — 마지막 입력 이후 경과. 첫 입력이면 무한대(= 공백 있음)
	const double Gap = (LastMouseInputTime < 0.0) ? TNumericLimits<double>::Max() : (Now - LastMouseInputTime);
	const bool bPaused = (Gap >= Params.MouseRearmPause);

	// 전환 후에는 마우스가 RearmPause 이상 멈춘 뒤의 첫 입력에서만 다시 
	if (MousePhase == EAstralMouseSwitchPhase::WaitingForPause)
	{
		LastMouseInputTime = Now;
		if (!bPaused)
		{
			return FAstralTargetSwitchResult();   // 폐기
		}
		MousePhase = EAstralMouseSwitchPhase::Armed;
	}

	// 누적 창 — 기준은 첫 입력. 창이 없거나, 공백 뒤 첫 입력이거나, 창이 만료됐으면 새 창.
	const bool bNewWindow = (MousePhase == EAstralMouseSwitchPhase::Armed) || bPaused || ((Now - MouseWindowStartTime) > Params.MouseAccumulationWindow);
	if (bNewWindow)
	{
		MouseAccumulation = 0.f;
		MouseWindowStartTime = Now;
		MousePhase = EAstralMouseSwitchPhase::Accumulating;
	}

	LastMouseInputTime = Now;
	MouseAccumulation += DeltaX;

	// 임계 — 0 이하는 비활성
	if (Params.MouseAccumulationThreshold > 0.f && FMath::Abs(MouseAccumulation) >= Params.MouseAccumulationThreshold)
	{
		const EAstralTargetSwitchDirection Direction = (MouseAccumulation > 0.f) ? EAstralTargetSwitchDirection::Right : EAstralTargetSwitchDirection::Left;
		MouseAccumulation = 0.f;
		MouseWindowStartTime = -1.0;
		MousePhase = EAstralMouseSwitchPhase::WaitingForPause;   // 멈출 때까지 잠근다
		return Direction;
	}

	return FAstralTargetSwitchResult();
}

void FAstralTargetSwitchInputProcessor::Reset()
{
	StickPhase = EAstralStickSwitchPhase::Neutral;
	MousePhase = EAstralMouseSwitchPhase::Armed;   // 재락온 직후 첫 플릭이 이전 세션의 잠금에 먹히지 않게
	MouseAccumulation = 0.f;
	MouseWindowStartTime = -1.0;
	LastMouseInputTime = -1.0;
}

#if !UE_BUILD_SHIPPING
FAstralTargetSwitchInputDebugSnapshot FAstralTargetSwitchInputProcessor::MakeDebugSnapshot(double Now, const FAstralTargetSwitchInputParams& Params) const
{
	FAstralTargetSwitchInputDebugSnapshot Snapshot;
	Snapshot.StickPhase = StickPhase;
	Snapshot.MousePhase = MousePhase;
	Snapshot.MouseAccumulation = MouseAccumulation;
	Snapshot.WindowAge = (MouseWindowStartTime < 0.0) ? -1.f : static_cast<float>(Now - MouseWindowStartTime);
	Snapshot.IdleAge = (LastMouseInputTime < 0.0) ? -1.f : static_cast<float>(Now - LastMouseInputTime);
	Snapshot.AccumulationThreshold = Params.MouseAccumulationThreshold;
	return Snapshot;
}
#endif
