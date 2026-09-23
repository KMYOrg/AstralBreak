#include "AstralInputFacingTypes.h"

#include "Combat/AstralFacingTypes.h"

//////////////////////////////////////////////////////////////////////////
// FAstralInputFacingSettings

bool FAstralInputFacingSettings::IsValid() const
{
	return FMath::IsFinite(RotationSpeed) && RotationSpeed >= 0.f
		&& FMath::IsFinite(InputThreshold) && InputThreshold >= 0.f && InputThreshold <= 1.f
		&& FMath::IsFinite(OppositeTurnAcceptanceDegrees) && OppositeTurnAcceptanceDegrees >= 0.f && OppositeTurnAcceptanceDegrees <= 10.f;
}

//////////////////////////////////////////////////////////////////////////
// FAstralInputFacingSample

float FAstralInputFacingSample::GetInputYaw() const
{
	return AstralFacing::DequantizeYaw(WorldInputYaw);
}

float FAstralInputFacingSample::GetInputMagnitude() const
{
	return AstralInputFacing::DequantizeMagnitude(InputMagnitude);
}

void FAstralInputFacingSample::NormalizeNone()
{
	if (InputMagnitude == 0)
	{
		WorldInputYaw = 0;
		bPositiveTurn = AstralInputFacing::DefaultPositiveTurn;
	}
}

bool FAstralInputFacingSample::operator==(const FAstralInputFacingSample& Other) const
{
	return WorldInputYaw == Other.WorldInputYaw
		&& InputMagnitude == Other.InputMagnitude
		&& bSuppressInputFacing == Other.bSuppressInputFacing
		&& bPositiveTurn == Other.bPositiveTurn;
}

void FAstralInputFacingSample::SerializeBits(FArchive& Ar)
{
	Ar.SerializeBits(&WorldInputYaw, 16);
	Ar.SerializeBits(&InputMagnitude, 8);

	uint8 Flags = (bSuppressInputFacing ? 1 : 0) | (bPositiveTurn ? 2 : 0);
	Ar.SerializeBits(&Flags, 2);

	if (Ar.IsLoading())
	{
		bSuppressInputFacing = (Flags & 1) != 0;
		bPositiveTurn = (Flags & 2) != 0;
		NormalizeNone();
	}
}

FString FAstralInputFacingSample::ToString() const
{
	return FString::Printf(TEXT("InputFacing(Yaw=%.1f Mag=%.2f Suppress=%d Sign=%c)"),
		GetInputYaw(), GetInputMagnitude(), bSuppressInputFacing ? 1 : 0, bPositiveTurn ? TEXT('+') : TEXT('-'));
}

//////////////////////////////////////////////////////////////////////////
// AstralInputFacing — 순수 함수

namespace AstralInputFacing
{
	uint8 QuantizeMagnitude(float Magnitude01)
	{
		if (!FMath::IsFinite(Magnitude01))
		{
			return 0;
		}
		const float Clamped = FMath::Clamp(Magnitude01, 0.f, 1.f);
		return static_cast<uint8>(FMath::RoundToInt(Clamped * 255.f));
	}

	float DequantizeMagnitude(uint8 Quantized)
	{
		return static_cast<float>(Quantized) / 255.f;
	}

	bool ChooseTurnSign(float CurrentYaw, float TargetYaw)
	{
		const float Error = FMath::FindDeltaAngleDegrees(CurrentYaw, TargetYaw);
		if (FMath::IsNearlyEqual(FMath::Abs(Error), 180.f, UE_KINDA_SMALL_NUMBER))
		{
			return DefaultPositiveTurn;
		}
		return Error >= 0.f;
	}

	FAstralInputFacingSample MakeSample(const FVector& WorldInput, float CurrentActorYaw, bool bSuppress)
	{
		FAstralInputFacingSample Sample;
		Sample.bSuppressInputFacing = bSuppress;

		const FVector Horizontal(WorldInput.X, WorldInput.Y, 0.f);
		const float Magnitude = Horizontal.Size();
		if (!FMath::IsFinite(Magnitude) || Magnitude <= UE_KINDA_SMALL_NUMBER)
		{
			Sample.NormalizeNone();
			return Sample;
		}

		// 대각 입력은 크기가 1을 넘는다 — 1로 클램프 (방향은 유지)
		Sample.InputMagnitude = QuantizeMagnitude(Magnitude);
		if (Sample.InputMagnitude == 0)
		{
			Sample.NormalizeNone();
			return Sample;
		}

		Sample.WorldInputYaw = AstralFacing::QuantizeYaw(Horizontal.Rotation().Yaw);
		// 부호는 복원값 기준 — 서버·재실행이 보는 것과 같은 목표로 고른다
		Sample.bPositiveTurn = ChooseTurnSign(CurrentActorYaw, Sample.GetInputYaw());
		return Sample;
	}

	float ComputeTurnDelta(float SignedError, bool bPositiveTurn, float MaxStep, float OppositeAcceptanceDegrees)
	{
		if (!FMath::IsFinite(SignedError) || !FMath::IsFinite(MaxStep) || MaxStep <= 0.f)
		{
			return 0.f;
		}

		const float Error = FRotator::NormalizeAxis(SignedError);
		const float AbsError = FMath::Abs(Error);
		if (AbsError <= UE_KINDA_SMALL_NUMBER)
		{
			return 0.f;
		}

		const float Sign = bPositiveTurn ? 1.f : -1.f;
		const float AlongSubmittedSign = Error * Sign;

		// 폭 밖에서 제출 부호가 최단각과 다르면 0 — 서버가 부호를 바꿔 감추지 않는다
		const bool bOppositeAcceptance = AbsError >= 180.f - OppositeAcceptanceDegrees;
		if (!bOppositeAcceptance && AlongSubmittedSign < 0.f)
		{
			return 0.f;
		}

		// 수용 폭 안에서 부호가 반대면 그 방향 거리는 360 - |Error| (예: -179에 + → 181)
		const float RemainingAlongSign = (AlongSubmittedSign >= 0.f) ? AlongSubmittedSign : (360.f + AlongSubmittedSign);
		return Sign * FMath::Min(RemainingAlongSign, MaxStep);
	}

	float ComputeActiveSeconds(float PreviousPosition, float CurrentPosition, float WindowStart, float WindowEnd, float PlayRate, float DeltaSeconds)
	{
		if (!FMath::IsFinite(PlayRate) || PlayRate <= 0.f || !FMath::IsFinite(DeltaSeconds) || DeltaSeconds <= 0.f)
		{
			return 0.f;
		}
		if (CurrentPosition < PreviousPosition || WindowEnd <= WindowStart)
		{
			return 0.f;
		}

		const float Overlap = FMath::Min(CurrentPosition, WindowEnd) - FMath::Max(PreviousPosition, WindowStart);
		if (Overlap <= 0.f)
		{
			return 0.f;
		}

		return FMath::Clamp(Overlap / PlayRate, 0.f, DeltaSeconds);
	}

	FQuat PredictActorRotation(const FQuat& ActorQuat, const FQuat& MeshRelativeQuat, const FQuat& LocalRootMotionRotation)
	{
		// USkeletalMeshComponent::ConvertLocalRootMotionToWorld
		// UCharacterMovementComponent::PerformMovement: NewActor = DeltaWorld · OldActor
		const FQuat MeshToWorld = ActorQuat * MeshRelativeQuat;
		const FQuat DeltaWorld = MeshToWorld * LocalRootMotionRotation * MeshToWorld.Inverse();
		return (DeltaWorld * ActorQuat).GetNormalized();
	}

	FQuat ComposeLocalRotation(const FQuat& ActorQuat, const FQuat& MeshRelativeQuat, const FQuat& LocalRootMotionRotation, float AdditionalWorldYawDegrees)
	{
		if (FMath::IsNearlyZero(AdditionalWorldYawDegrees))
		{
			return LocalRootMotionRotation;
		}

		const FQuat MeshToWorld = ActorQuat * MeshRelativeQuat;
		const FQuat AddWorld(FVector::UpVector, FMath::DegreesToRadians(AdditionalWorldYawDegrees));
		// C · L' · C⁻¹ = Add · (C · L · C⁻¹)  →  L' = C⁻¹ · Add · C · L
		return (MeshToWorld.Inverse() * AddWorld * MeshToWorld * LocalRootMotionRotation).GetNormalized();
	}
}
