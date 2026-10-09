#include "AstralRootMotionModifier_InputFacing.h"

#include "AstralLogChannels.h"
#include "Character/Hero/AstralCharacter_Hero.h"
#include "Character/Hero/Components/AstralHeroMovementComponent.h"
#include "GameFramework/Character.h"
#include "MotionWarpingAdapter.h"

UAstralRootMotionModifier_InputFacing::UAstralRootMotionModifier_InputFacing(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

bool UAstralRootMotionModifier_InputFacing::ResolveSample(const AActor* Actor, const UAstralHeroMovementComponent* HeroMC, FAstralInputFacingSample& OutSample, bool& bOutSuppressed) const
{
	bOutSuppressed = false;

	if (Actor->GetLocalRole() == ROLE_SimulatedProxy)
	{
		// 관찰자 — 서버가 승인한 표현 샘플. 자기 창(몽타주·시작 시각)과 맞지 않거나 비활성이면 추정하지 않는다 (오래된 샘플 차단)
		const AAstralCharacter_Hero* Hero = Cast<AAstralCharacter_Hero>(Actor);
		if (!Hero)
		{
			return false;
		}
		const FAstralInputFacingPresentation& Presentation = Hero->GetInputFacingPresentation();
		if (!Presentation.bActive || !Presentation.MatchesWindow(Animation.Get(), StartTime))
		{
			return false;
		}
		OutSample = Presentation.ToSample();
		return true;
	}

	// 소유자·서버 — 읽기 접점은 하나. 로컬 예측·서버 실행·보정 재실행이 같은 move 샘플을 본다
	if (!HeroMC->GetInputFacingSampleForCurrentMove(OutSample))
	{
		return false;
	}

	// 억제 = 샘플 플래그(클라의 록온 선택·예측 소유권) ∨ 이 머신의 라이브 소유권 슬롯(서버 자체 판단).
	// 재실행(bClientUpdating)은 저장된 샘플 플래그만 — 현재 슬롯을 과거 move에 적용하지 않는다
	const ACharacter* Character = CastChecked<ACharacter>(Actor);
	bOutSuppressed = OutSample.bSuppressInputFacing || (!Character->bClientUpdating && HeroMC->IsFacingOwnerActive());
	return true;
}

void UAstralRootMotionModifier_InputFacing::WritePresentation(const AActor* Actor, const FAstralInputFacingSample& Sample, bool bActive) const
{
	if (!Actor->HasAuthority())
	{
		return;
	}
	if (AAstralCharacter_Hero* Hero = const_cast<AAstralCharacter_Hero*>(Cast<AAstralCharacter_Hero>(Actor)))
	{
		Hero->SetInputFacingPresentation(FAstralInputFacingPresentation::Make(Animation.Get(), StartTime, Sample, bActive));
	}
}

void UAstralRootMotionModifier_InputFacing::OnStateChanged(ERootMotionModifierState LastState)
{
	Super::OnStateChanged(LastState);

	// 창 종료·몽타주 교체·취소 — 서버의 표현 샘플을 비활성으로. 다음 창은 자기 문맥(몽타주·시작 시각)으로 다시 켠다
	const ERootMotionModifierState NewState = GetState();
	if (LastState == ERootMotionModifierState::Active && (NewState == ERootMotionModifierState::MarkedForRemoval || NewState == ERootMotionModifierState::Disabled))
	{
		if (const AActor* Actor = GetActorOwner())
		{
			WritePresentation(Actor, FAstralInputFacingSample(), false);
		}
	}
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

	FAstralInputFacingSample Sample;
	bool bSuppressed = false;
	if (!ResolveSample(Actor, HeroMC, Sample, bSuppressed))
	{
		return InRootMotion;
	}

	const bool bUsableInput = !bSuppressed && Sample.HasInput() && Sample.GetInputMagnitude() >= Settings.InputThreshold;

	// 서버 — 매 평가 관찰자에게 알린다. 무입력·억제도 "비활성"으로 전달해 관찰자가 오래된 샘플로 계속 돌지 않게 한다
	if (Actor->GetLocalRole() != ROLE_SimulatedProxy)
	{
		WritePresentation(Actor, Sample, bUsableInput);
	}

	if (!bUsableInput)
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
