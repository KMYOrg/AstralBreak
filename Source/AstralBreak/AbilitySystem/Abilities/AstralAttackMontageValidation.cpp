#include "AstralAttackMontageValidation.h"

#if !UE_BUILD_SHIPPING

#include "AnimNotifyState_MotionWarping.h"
#include "Animation/AnimMontage.h"
#include "Animation/Notifies/AstralAnimNotifyState_GameplayEventWindow.h"
#include "AstralLogChannels.h"
#include "RootMotionModifier.h"

namespace AstralAttackMontage
{
	void ValidateFacingWarpBand(const UAnimMontage* Montage, FName ExpectedWarpTargetName, const FGameplayTag& TraceBeginEventTag, const FString& Context)
	{
		if (!Montage)
		{
			return;
		}

		const FString Prefix = FString::Printf(TEXT("[FacingWarp] %s (%s)"), *Context, *Montage->GetName());

		// 워프 밴드 수집 + 가장 이른 WeaponTrace 밴드 시작
		TArray<const FAnimNotifyEvent*> WarpBands;
		float EarliestTraceBegin = TNumericLimits<float>::Max();

		for (const FAnimNotifyEvent& Event : Montage->Notifies)
		{
			if (Cast<UAnimNotifyState_MotionWarping>(Event.NotifyStateClass))
			{
				WarpBands.Add(&Event);
				continue;
			}

			if (const UAstralAnimNotifyState_GameplayEventWindow* Band = Cast<UAstralAnimNotifyState_GameplayEventWindow>(Event.NotifyStateClass))
			{
				if (TraceBeginEventTag.IsValid() && Band->GetBeginEventTag() == TraceBeginEventTag)
				{
					EarliestTraceBegin = FMath::Min(EarliestTraceBegin, Event.GetTriggerTime());
				}
			}
		}

		if (WarpBands.Num() == 0)
		{
			if (!ExpectedWarpTargetName.IsNone())
			{
				UE_LOG(LogAstralAbilitySystem, Warning, TEXT("%s: MotionWarping 밴드가 없다 — 이 몽타주는 방향 보정 없이 재생된다 (워프 타겟 '%s'는 설치만 되고 소비되지 않는다)"), *Prefix, *ExpectedWarpTargetName.ToString());
			}
			return;
		}

		if (ExpectedWarpTargetName.IsNone())
		{
			UE_LOG(LogAstralAbilitySystem, Warning, TEXT("%s: MotionWarping 밴드는 있는데 GA 데이터의 FacingWarpTargetName이 비어 있다 — 워프 타겟이 설치되지 않아 밴드가 무효"), *Prefix);
		}

		if (WarpBands.Num() > 1)
		{
			UE_LOG(LogAstralAbilitySystem, Error, TEXT("%s: MotionWarping 밴드가 %d개 — 몽타주당 1개여야 한다"), *Prefix, WarpBands.Num());
		}

		// 워프 훅(ProcessRootMotionPreConvertToWorld)은 루트모션이 추출될 때만 불린다
		if (!Montage->HasRootMotion())
		{
			UE_LOG(LogAstralAbilitySystem, Warning, TEXT("%s: 몽타주에 루트모션이 없다 — MotionWarping 밴드가 아무 일도 하지 않는다"), *Prefix);
		}

		for (const FAnimNotifyEvent* Event : WarpBands)
		{
			const UAnimNotifyState_MotionWarping* Notify = Cast<UAnimNotifyState_MotionWarping>(Event->NotifyStateClass);
			const URootMotionModifier_Warp* Modifier = Notify ? Cast<URootMotionModifier_Warp>(Notify->RootMotionModifier) : nullptr;
			if (!Modifier)
			{
				UE_LOG(LogAstralAbilitySystem, Error, TEXT("%s: MotionWarping 밴드의 RootMotionModifier가 없거나 Warp 계열이 아니다"), *Prefix);
				continue;
			}

			if (!ExpectedWarpTargetName.IsNone() && Modifier->WarpTargetName != ExpectedWarpTargetName)
			{
				UE_LOG(LogAstralAbilitySystem, Error, TEXT("%s: 워프 타겟 이름 불일치 — 노티파이 '%s' vs GA 데이터 '%s'"), *Prefix, *Modifier->WarpTargetName.ToString(), *ExpectedWarpTargetName.ToString());
			}

			if (!Modifier->bWarpRotation)
			{
				UE_LOG(LogAstralAbilitySystem, Error, TEXT("%s: bWarpRotation이 꺼져 있다 — 방향 보정이 일어나지 않는다"), *Prefix);
			}

			if (Modifier->bWarpTranslation)
			{
				UE_LOG(LogAstralAbilitySystem, Error, TEXT("%s: bWarpTranslation이 켜져 있다 — 워프 타겟 위치가 아바타 현재 위치라 전진 루트모션이 제자리로 수렴한다. 반드시 끌 것"), *Prefix);
			}

			const float BandStart = Event->GetTriggerTime();
			const float BandEnd = Event->GetEndTriggerTime();
			if (BandStart >= BandEnd)
			{
				UE_LOG(LogAstralAbilitySystem, Error, TEXT("%s: 워프 밴드 길이가 0 이하 (%.3f ~ %.3f)"), *Prefix, BandStart, BandEnd);
			}

			if (EarliestTraceBegin < TNumericLimits<float>::Max() && BandEnd > EarliestTraceBegin + KINDA_SMALL_NUMBER)
			{
				UE_LOG(LogAstralAbilitySystem, Warning, TEXT("%s: 워프 밴드 종료(%.3f)가 WeaponTrace 시작(%.3f)보다 늦다 — 루트모션 변위가 로컬 공간이라 전진이 곡선으로 휜다. 밴드를 선딜 안에 끝낼 것"), *Prefix, BandEnd, EarliestTraceBegin);
			}
		}
	}
}

#endif // !UE_BUILD_SHIPPING
