#include "AstralAttackMontageValidation.h"

#if !UE_BUILD_SHIPPING

#include "AnimNotifyState_MotionWarping.h"
#include "Animation/AnimMontage.h"
#include "Animation/Notifies/AstralAnimNotify_GameplayEvent.h"
#include "Animation/Notifies/AstralAnimNotifyState_GameplayEventWindow.h"
#include "Animation/Notifies/AstralAnimNotifyState_RootMotionPawnCollisionPolicy.h"
#include "AstralLogChannels.h"
#include "RootMotionModifier.h"

namespace AstralAttackMontage
{
	TOptional<float> FindEarliestWindowBegin(const UAnimMontage* Montage, const FGameplayTag& BeginEventTag)
	{
		TOptional<float> Earliest;
		if (!Montage || !BeginEventTag.IsValid())
		{
			return Earliest;
		}

		for (const FAnimNotifyEvent& Event : Montage->Notifies)
		{
			const UAstralAnimNotifyState_GameplayEventWindow* Band = Cast<UAstralAnimNotifyState_GameplayEventWindow>(Event.NotifyStateClass);
			if (Band && Band->GetBeginEventTag() == BeginEventTag)
			{
				const float Begin = Event.GetTriggerTime();
				Earliest = Earliest.IsSet() ? FMath::Min(*Earliest, Begin) : Begin;
			}
		}
		return Earliest;
	}

	TOptional<float> ValidateFireNotify(const UAnimMontage* Montage, const FGameplayTag& FireEventTag, const FString& Context)
	{
		TOptional<float> FireTime;
		if (!Montage)
		{
			return FireTime;
		}

		const FString Prefix = FString::Printf(TEXT("[RangedFire] %s (%s)"), *Context, *Montage->GetName());

		// 단발 노티파이는 NotifyStateClass가 아니라 Notify 쪽 — 밴드 검색과 다른 경로
		int32 Count = 0;
		for (const FAnimNotifyEvent& Event : Montage->Notifies)
		{
			const UAstralAnimNotify_GameplayEvent* Notify = Cast<UAstralAnimNotify_GameplayEvent>(Event.Notify);
			if (!Notify || Notify->GetEventTag() != FireEventTag)
			{
				continue;
			}

			++Count;
			const float TriggerTime = Event.GetTriggerTime();
			if (TriggerTime <= 0.f)
			{
				// 엔진 추출 조건 (Start <= Cur && End > Prev) — 첫 틱은 Prev = 0이라 0초 즉발 노티파이는 걸리지 않는다
				UE_LOG(LogAstralAbilitySystem, Error, TEXT("%s: 발사 노티파이가 %.3f초 — 0초에 두면 첫 틱에 누락된다. 최소 한 프레임 뒤로 옮길 것"), *Prefix, TriggerTime);
				continue;
			}
			FireTime = TriggerTime;
		}

		if (Count == 0)
		{
			UE_LOG(LogAstralAbilitySystem, Error, TEXT("%s: 발사 노티파이('%s')가 없다 — 몽타주가 끝나도 발사되지 않는다"), *Prefix, *FireEventTag.ToString());
		}
		else if (Count > 1)
		{
			UE_LOG(LogAstralAbilitySystem, Error, TEXT("%s: 발사 노티파이가 %d개 — 활성화당 단발이라 1개여야 한다 (첫 발화만 처리된다)"), *Prefix, Count);
			FireTime.Reset();
		}

		return FireTime;
	}

	void ValidateFacingWarpBand(const UAnimMontage* Montage, FName ExpectedWarpTargetName, TOptional<float> BoundaryTime, const FString& Context)
	{
		if (!Montage)
		{
			return;
		}

		const FString Prefix = FString::Printf(TEXT("[FacingWarp] %s (%s)"), *Context, *Montage->GetName());

		// 워프 밴드 수집 — 경계 시각은 호출자가 계산해 넘긴다 (노티파이 종류를 여기서 알 필요가 없다)
		TArray<const FAnimNotifyEvent*> WarpBands;

		for (const FAnimNotifyEvent& Event : Montage->Notifies)
		{
			if (Cast<UAnimNotifyState_MotionWarping>(Event.NotifyStateClass))
			{
				WarpBands.Add(&Event);
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

			if (BoundaryTime.IsSet() && BandEnd > *BoundaryTime + KINDA_SMALL_NUMBER)
			{
				UE_LOG(LogAstralAbilitySystem, Warning, TEXT("%s: 워프 밴드 종료(%.3f)가 경계 시각(%.3f, WeaponTrace 시작 또는 발사 시점)보다 늦다 — 회전이 판정과 겹친다. 밴드를 선딜 안에 끝낼 것"), *Prefix, BandEnd, *BoundaryTime);
			}
		}
	}

	void ValidatePawnCollisionBands(const UAnimMontage* Montage, const FString& Context)
	{
		if (!Montage)
		{
			return;
		}

		const FString Prefix = FString::Printf(TEXT("[PawnCollision] %s (%s)"), *Context, *Montage->GetName());

		struct FBand
		{
			const UAstralAnimNotifyState_RootMotionPawnCollisionPolicy* Notify = nullptr;
			float Start = 0.f;
			float End = 0.f;
		};
		TArray<FBand> Bands;

		for (const FAnimNotifyEvent& Event : Montage->Notifies)
		{
			if (const UAstralAnimNotifyState_RootMotionPawnCollisionPolicy* Notify = Cast<UAstralAnimNotifyState_RootMotionPawnCollisionPolicy>(Event.NotifyStateClass))
			{
				FBand& Band = Bands.AddDefaulted_GetRef();
				Band.Notify = Notify;
				Band.Start = Event.GetTriggerTime();
				Band.End = Event.GetEndTriggerTime();
			}
		}

		if (Bands.Num() == 0)
		{
			UE_LOG(LogAstralAbilitySystem, Warning, TEXT("%s: 폰 충돌 정책 밴드가 없다 — 공격 루트모션이 적 캡슐을 따라 슬라이드해 적 주위를 돈다 (StopOnHit 밴드 권장)"), *Prefix);
			return;
		}

		for (int32 A = 0; A < Bands.Num(); ++A)
		{
			if (Bands[A].Start >= Bands[A].End)
			{
				UE_LOG(LogAstralAbilitySystem, Error, TEXT("%s: 정책 밴드 길이가 0 이하 (%.3f ~ %.3f)"), *Prefix, Bands[A].Start, Bands[A].End);
			}

			for (int32 B = A + 1; B < Bands.Num(); ++B)
			{
				// 같은 인스턴스 두 번 — CMC의 source 키(TObjectKey × InstanceID)가 같아져 End 하나가 둘을 지운다
				if (Bands[A].Notify == Bands[B].Notify)
				{
					UE_LOG(LogAstralAbilitySystem, Error, TEXT("%s: 같은 정책 NotifyState 인스턴스가 두 번 배치됐다 (%.3f~%.3f, %.3f~%.3f) — 각각 별도 노티파이로 둘 것"), *Prefix, Bands[A].Start, Bands[A].End, Bands[B].Start, Bands[B].End);
					continue;
				}

				// 부분 겹침 금지 — 완전 중첩(한쪽이 다른 쪽을 포함) 또는 비겹침(인접 포함)만
				const float OverlapStart = FMath::Max(Bands[A].Start, Bands[B].Start);
				const float OverlapEnd = FMath::Min(Bands[A].End, Bands[B].End);
				const bool bOverlaps = OverlapEnd > OverlapStart + KINDA_SMALL_NUMBER;
				const bool bAContainsB = Bands[A].Start <= Bands[B].Start + KINDA_SMALL_NUMBER && Bands[A].End >= Bands[B].End - KINDA_SMALL_NUMBER;
				const bool bBContainsA = Bands[B].Start <= Bands[A].Start + KINDA_SMALL_NUMBER && Bands[B].End >= Bands[A].End - KINDA_SMALL_NUMBER;
				if (bOverlaps && !bAContainsB && !bBContainsA)
				{
					UE_LOG(LogAstralAbilitySystem, Error, TEXT("%s: 정책 밴드가 부분적으로 겹친다 (%.3f~%.3f vs %.3f~%.3f) — 완전 중첩 또는 인접만 허용"), *Prefix, Bands[A].Start, Bands[A].End, Bands[B].Start, Bands[B].End);
				}
			}
		}
	}
}

#endif // !UE_BUILD_SHIPPING
