#include "AstralRootMotionModifier_InputFacing.h"

#include "AstralLogChannels.h"
#include "Character/Hero/Components/AstralHeroMovementComponent.h"
#include "GameFramework/Character.h"
#include "MotionWarpingAdapter.h"

UAstralRootMotionModifier_InputFacing::UAstralRootMotionModifier_InputFacing(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

FTransform UAstralRootMotionModifier_InputFacing::ProcessRootMotion(const FTransform& InRootMotion, float DeltaSeconds)
{
	using namespace AstralInputFacing;

	const UMotionWarpingBaseAdapter* Adapter = GetOwnerAdapter();
	const AActor* Actor = Adapter ? Adapter->GetActor() : nullptr;
	const ACharacter* Character = Cast<ACharacter>(Actor);
	const UAstralHeroMovementComponent* HeroMC = Character ? Cast<UAstralHeroMovementComponent>(Character->GetCharacterMovement()) : nullptr;
	if (!HeroMC || !Settings.IsValid())
	{
		return InRootMotion;
	}

	// 읽기 접점은 하나 — 로컬 예측·서버 실행·보정 재실행이 같은 move 샘플을 본다. 설치된 샘플이 없으면(시뮬 프록시 등) 보정 없음
	FAstralInputFacingSample Sample;
	if (!HeroMC->GetInputFacingSampleForCurrentMove(Sample))
	{
		return InRootMotion;
	}
	if (Sample.bSuppressInputFacing || !Sample.HasInput() || Sample.GetInputMagnitude() < Settings.InputThreshold)
	{
		return InRootMotion;
	}

	const float ActiveSeconds = ComputeActiveSeconds(PreviousPosition, CurrentPosition, StartTime, EndTime, PlayRate, DeltaSeconds);
	const float MaxStep = Settings.RotationSpeed * ActiveSeconds;
	if (MaxStep <= 0.f)
	{
		return InRootMotion;
	}

	// 원본 루트모션 회전을 적용한 예상 자세에서 목표까지 — 원본 회전과 추가 회전이 중복되지 않는다
	const FQuat ActorQuat = Actor->GetActorQuat();
	const FQuat MeshRelative = Adapter->GetBaseVisualRotationOffset();
	const FQuat PredictedActor = PredictActorRotation(ActorQuat, MeshRelative, InRootMotion.GetRotation());
	const float SignedError = FMath::FindDeltaAngleDegrees(PredictedActor.Rotator().Yaw, Sample.GetInputYaw());
	const float TurnDelta = ComputeTurnDelta(SignedError, Sample.bPositiveTurn, MaxStep, Settings.OppositeTurnAcceptanceDegrees);
	if (FMath::IsNearlyZero(TurnDelta))
	{
		return InRootMotion;
	}

	UE_LOG(LogAstral, VeryVerbose, TEXT("[InputFacing] %s %s Window=[%.3f %.3f] Pos=[%.3f %.3f] Active=%.4fs Error=%.1f Turn=%.2f"),
		*GetNameSafe(Actor), *Sample.ToString(), StartTime, EndTime, PreviousPosition, CurrentPosition, ActiveSeconds, SignedError, TurnDelta);

	// Translation·Scale 보존, 회전만 합성. SetActorRotation은 부르지 않는다 — CMC가 이동 뒤 루트모션 회전을 적용한다
	FTransform FinalRootMotion = InRootMotion;
	FinalRootMotion.SetRotation(ComposeLocalRotation(ActorQuat, MeshRelative, InRootMotion.GetRotation(), TurnDelta));
	return FinalRootMotion;
}
