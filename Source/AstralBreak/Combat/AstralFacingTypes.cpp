#include "AstralFacingTypes.h"

#include "GameFramework/Actor.h"

//////////////////////////////////////////////////////////////////////////
// AstralFacing — 순수 함수

namespace AstralFacing
{
	uint16 QuantizeYaw(float YawDegrees)
	{
		// [-180, 180) → [0, 65536). 180은 -180으로 접힌다 (NormalizeAxis는 (-180, 180]을 돌려주므로 180만 별도 처리)
		float Normalized = FRotator::NormalizeAxis(YawDegrees);
		if (Normalized >= 180.f)
		{
			Normalized = -180.f;
		}
		const float Scaled = (Normalized + 180.f) / 360.f * 65536.f;
		const int32 Rounded = FMath::RoundToInt(Scaled);
		return static_cast<uint16>(Rounded & 0xFFFF);
	}

	float DequantizeYaw(uint16 Quantized)
	{
		return FRotator::NormalizeAxis(static_cast<float>(Quantized) / 65536.f * 360.f - 180.f);
	}

	EAstralFacingRejectReason ValidateBearing(float Distance2D, float ServerBearingYaw, float SubmittedYaw)
	{
		if (Distance2D > ValidateRange)
		{
			return EAstralFacingRejectReason::OutOfRange;
		}

		// 접촉 거리에서는 방위가 프레임마다 크게 흔들린다 — 각도 검사 생략
		if (Distance2D >= BearingCheckMinDistance)
		{
			const float Error = FMath::Abs(FMath::FindDeltaAngleDegrees(ServerBearingYaw, SubmittedYaw));
			if (Error > MaxTargetBearingError)
			{
				return EAstralFacingRejectReason::BearingMismatch;
			}
		}

		return EAstralFacingRejectReason::None;
	}

	const TCHAR* ToString(EAstralFacingSource Value)
	{
		switch (Value)
		{
		case EAstralFacingSource::None:   return TEXT("None");
		case EAstralFacingSource::LockOn: return TEXT("LockOn");
		}
		return TEXT("?");
	}

	const TCHAR* ToString(EAstralFacingDecision Value)
	{
		switch (Value)
		{
		case EAstralFacingDecision::Warp:                return TEXT("Warp");
		case EAstralFacingDecision::NoWarp_ExplicitNone: return TEXT("NoWarp_ExplicitNone");
		case EAstralFacingDecision::NoWarp_Missing:      return TEXT("NoWarp_Missing");
		case EAstralFacingDecision::NoWarp_Rejected:     return TEXT("NoWarp_Rejected");
		}
		return TEXT("?");
	}

	const TCHAR* ToString(EAstralFacingRejectReason Value)
	{
		switch (Value)
		{
		case EAstralFacingRejectReason::None:            return TEXT("None");
		case EAstralFacingRejectReason::InvalidTarget:   return TEXT("InvalidTarget");
		case EAstralFacingRejectReason::SelfTarget:      return TEXT("SelfTarget");
		case EAstralFacingRejectReason::CannotDamage:    return TEXT("CannotDamage");
		case EAstralFacingRejectReason::OutOfRange:      return TEXT("OutOfRange");
		case EAstralFacingRejectReason::BearingMismatch: return TEXT("BearingMismatch");
		}
		return TEXT("?");
	}

	const TCHAR* ToString(EAstralFacingReceiveResult Value)
	{
		switch (Value)
		{
		case EAstralFacingReceiveResult::StoredCurrent:       return TEXT("StoredCurrent");
		case EAstralFacingReceiveResult::StoredNext:          return TEXT("StoredNext");
		case EAstralFacingReceiveResult::DuplicateIgnored:    return TEXT("DuplicateIgnored");
		case EAstralFacingReceiveResult::ConflictIgnored:     return TEXT("ConflictIgnored");
		case EAstralFacingReceiveResult::DiscardedPast:       return TEXT("DiscardedPast");
		case EAstralFacingReceiveResult::DiscardedResolved:   return TEXT("DiscardedResolved");
		case EAstralFacingReceiveResult::DiscardedTooFar:     return TEXT("DiscardedTooFar");
		case EAstralFacingReceiveResult::DiscardedOutOfRange: return TEXT("DiscardedOutOfRange");
		}
		return TEXT("?");
	}
}

//////////////////////////////////////////////////////////////////////////
// FAstralFacingProposal

void FAstralFacingProposal::NormalizeNone()
{
	if (Source == EAstralFacingSource::None)
	{
		TargetActor = nullptr;
		TargetPointId = NAME_None;
		QuantizedDesiredYaw = 0;
	}
}

FAstralFacingProposal FAstralFacingProposal::MakeNone(uint8 InStageIndex)
{
	FAstralFacingProposal Proposal;
	Proposal.StageIndex = InStageIndex;
	return Proposal;
}

bool FAstralFacingProposal::operator==(const FAstralFacingProposal& Other) const
{
	return Source == Other.Source
		&& StageIndex == Other.StageIndex
		&& QuantizedDesiredYaw == Other.QuantizedDesiredYaw
		&& TargetPointId == Other.TargetPointId
		&& TargetActor.Get() == Other.TargetActor.Get();
}

//////////////////////////////////////////////////////////////////////////
// FGameplayAbilityTargetData_AstralFacing

TArray<TWeakObjectPtr<AActor>> FGameplayAbilityTargetData_AstralFacing::GetActors() const
{
	TArray<TWeakObjectPtr<AActor>> Actors;
	if (Proposal.TargetActor.IsValid())
	{
		Actors.Add(Proposal.TargetActor);
	}
	return Actors;
}

FString FGameplayAbilityTargetData_AstralFacing::ToString() const
{
	return FString::Printf(TEXT("AstralFacing(Stage=%d Source=%s Target=%s Yaw=%u)"),
		Proposal.StageIndex, AstralFacing::ToString(Proposal.Source), *GetNameSafe(Proposal.TargetActor.Get()), Proposal.QuantizedDesiredYaw);
}

void FAstralFacingProposal::NetSerializeFields(FArchive& Ar, UPackageMap* Map)
{
	uint8 SourceByte = static_cast<uint8>(Source);
	Ar << SourceByte;
	Ar << StageIndex;
	Ar << QuantizedDesiredYaw;

	// Actor — UPackageMap 경로. 메모리 아카이브(테스트)에서는 UObject 직렬화가 no-op이라 bHasActor로 방어
	uint8 bHasActor = TargetActor.IsValid() ? 1 : 0;
	Ar << bHasActor;
	if (bHasActor)
	{
		UObject* ActorObject = TargetActor.Get();
		Ar << ActorObject;
		if (Ar.IsLoading())
		{
			TargetActor = Cast<AActor>(ActorObject);
		}
	}
	else if (Ar.IsLoading())
	{
		TargetActor = nullptr;
	}

	// TargetPointId — MVP는 항상 NAME_None. FName은 아카이브 종류에 따라 직렬화가 다르므로 문자열로 (드문 경로)
	uint8 bHasPointId = TargetPointId.IsNone() ? 0 : 1;
	Ar << bHasPointId;
	if (bHasPointId)
	{
		FString PointIdString = Ar.IsSaving() ? TargetPointId.ToString() : FString();
		Ar << PointIdString;
		if (Ar.IsLoading())
		{
			TargetPointId = FName(*PointIdString);
		}
	}
	else if (Ar.IsLoading())
	{
		TargetPointId = NAME_None;
	}

	if (Ar.IsLoading())
	{
		Source = (SourceByte <= static_cast<uint8>(EAstralFacingSource::LockOn)) ? static_cast<EAstralFacingSource>(SourceByte) : EAstralFacingSource::None;
		NormalizeNone();
	}
}

bool FGameplayAbilityTargetData_AstralFacing::NetSerialize(FArchive& Ar, UPackageMap* Map, bool& bOutSuccess)
{
	Proposal.NetSerializeFields(Ar, Map);
	bOutSuccess = true;
	return true;
}

bool FGameplayAbilityTargetData_AstralFacing::ExtractProposal(const FGameplayAbilityTargetDataHandle& Handle, int32 NumStages, FAstralFacingProposal& OutProposal)
{
	// 페이로드는 정확히 1개, 예상 ScriptStruct만
	if (Handle.Num() != 1)
	{
		return false;
	}

	const FGameplayAbilityTargetData* Data = Handle.Get(0);
	if (!Data || Data->GetScriptStruct() != FGameplayAbilityTargetData_AstralFacing::StaticStruct())
	{
		return false;
	}

	FAstralFacingProposal Proposal = static_cast<const FGameplayAbilityTargetData_AstralFacing*>(Data)->Proposal;

	if (Proposal.Source > EAstralFacingSource::LockOn)
	{
		return false;
	}
	if (static_cast<int32>(Proposal.StageIndex) >= NumStages)
	{
		return false;
	}
	// M5 전까지 부위 조준 없음
	if (!Proposal.TargetPointId.IsNone())
	{
		return false;
	}

	Proposal.NormalizeNone();
	OutProposal = Proposal;
	return true;
}

FGameplayAbilityTargetDataHandle FGameplayAbilityTargetData_AstralFacing::MakeHandle(const FAstralFacingProposal& Proposal)
{
	FGameplayAbilityTargetDataHandle Handle;
	Handle.Add(new FGameplayAbilityTargetData_AstralFacing(Proposal));
	return Handle;
}

//////////////////////////////////////////////////////////////////////////
// FAstralFacingStageInbox

void FAstralFacingStageInbox::Reset(int32 InNumStages)
{
	NumStages = FMath::Max(InNumStages, 0);
	CurrentStage = 0;
	bCurrentResolved = false;
	Current.Reset();
	Next.Reset();
}

EAstralFacingReceiveResult FAstralFacingStageInbox::Receive(const FAstralFacingProposal& Proposal)
{
	const int32 Stage = Proposal.StageIndex;

	if (Stage >= NumStages)
	{
		return EAstralFacingReceiveResult::DiscardedOutOfRange;
	}
	if (Stage < CurrentStage)
	{
		return EAstralFacingReceiveResult::DiscardedPast;
	}

	if (Stage == CurrentStage)
	{
		if (bCurrentResolved)
		{
			return EAstralFacingReceiveResult::DiscardedResolved;
		}
		if (Current.IsSet())
		{
			return (*Current == Proposal) ? EAstralFacingReceiveResult::DuplicateIgnored : EAstralFacingReceiveResult::ConflictIgnored;
		}
		Current = Proposal;
		return EAstralFacingReceiveResult::StoredCurrent;
	}

	if (Stage == CurrentStage + 1)
	{
		if (Next.IsSet())
		{
			return (*Next == Proposal) ? EAstralFacingReceiveResult::DuplicateIgnored : EAstralFacingReceiveResult::ConflictIgnored;
		}
		Next = Proposal;
		return EAstralFacingReceiveResult::StoredNext;
	}

	return EAstralFacingReceiveResult::DiscardedTooFar;
}

bool FAstralFacingStageInbox::BeginStage(int32 StageIndex)
{
	// 첫 단계 — Reset 직후 그대로
	if (StageIndex == CurrentStage && !bCurrentResolved)
	{
		return true;
	}

	if (StageIndex == CurrentStage + 1)
	{
		Current = Next;
		Next.Reset();
		CurrentStage = StageIndex;
		bCurrentResolved = false;
		return true;
	}

	// 불일치(건너뜀·역행) — 감추지 않는다. 슬롯을 비우고 새 단계로
	CurrentStage = StageIndex;
	bCurrentResolved = false;
	Current.Reset();
	Next.Reset();
	return false;
}

TOptional<FAstralFacingProposal> FAstralFacingStageInbox::TakeCurrent()
{
	bCurrentResolved = true;
	TOptional<FAstralFacingProposal> Result = Current;
	Current.Reset();
	return Result;
}
