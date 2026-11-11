#include "AstralThreatComponent.h"

#include "Engine/World.h"
#include "GameFramework/Pawn.h"

UAstralThreatComponent::UAstralThreatComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	PrimaryComponentTick.bCanEverTick = false;
}

bool UAstralThreatComponent::RecordDamage(const APawn* Attacker, float Damage, const AActor* CurrentTarget)
{
	if (!Attacker || Damage <= 0.f)
	{
		return false;
	}

	const double Now = GetNow();

	// 이 가해자의 창 밖 기록은 여기서도 버린다 — SelectTarget 을 부르지 않는 트리에서 쌓이지 않게
	TArray<FAstralEnemyDamageEntry>& Entries = DamageLog.FindOrAdd(Attacker);
	Entries.RemoveAll([this, Now](const FAstralEnemyDamageEntry& Entry) { return !AstralEnemyTargeting::IsWithinDuration(Entry.Time, Now, DamageWindow); });

	FAstralEnemyDamageEntry& NewEntry = Entries.AddDefaulted_GetRef();
	NewEntry.Time = Now;
	NewEntry.Damage = Damage;

	// 현재 타깃에게 맞은 것은 다시 뽑을 이유가 아니다. 타깃이 없으면 트리가 이미 고르는 중이다
	if (!CurrentTarget || Attacker == CurrentTarget)
	{
		return false;
	}

	// 두 사람이 번갈아 때릴 때 추격 방향이 프레임마다 뒤집히지 않게 한다
	if (AstralEnemyTargeting::IsWithinDuration(LastRetargetRequestTime, Now, RetargetCooldown))
	{
		return false;
	}

	bRetargetPending = true;
	LastRetargetRequestTime = Now;
	return true;
}

int32 UAstralThreatComponent::SelectTarget(const FVector& Origin, TConstArrayView<FAstralThreatCandidateInfo> Candidates, const AActor* CurrentTarget)
{
	const double Now = GetNow();
	PruneExpired(Now);

	TArray<FAstralEnemyThreatCandidate, TInlineAllocator<8>> ThreatCandidates;
	ThreatCandidates.Reserve(Candidates.Num());
	int32 CurrentIndex = INDEX_NONE;
	for (int32 Index = 0; Index < Candidates.Num(); ++Index)
	{
		const FAstralThreatCandidateInfo& Info = Candidates[Index];

		FAstralEnemyThreatCandidate& Candidate = ThreatCandidates.AddDefaulted_GetRef();
		Candidate.Location = Info.Location;
		Candidate.bDeadOrDying = Info.bDeadOrDying;
		Candidate.bExcluded = IsExcluded(Info.Pawn);
		Candidate.Hostility = Info.Hostility;
		Candidate.RecentDamage = GetRecentDamage(Info.Pawn);

		if (Info.Pawn && Info.Pawn == CurrentTarget)
		{
			CurrentIndex = Index;
		}
	}

	// '다시 뽑기' 요청은 이번 판단이 소비한다 — 서 있었으면 유지 시간을 무시한다
	const bool bRetargetRequested = bRetargetPending;
	bRetargetPending = false;

	const bool bHoldCurrent = !bRetargetRequested
		&& ThreatCandidates.IsValidIndex(CurrentIndex)
		&& AstralEnemyTargeting::IsThreatEligible(ThreatCandidates[CurrentIndex])
		&& AstralEnemyTargeting::IsWithinDuration(TargetAcquiredTime, Now, HoldTime);
	if (bHoldCurrent)
	{
		return CurrentIndex;
	}

	// 같은 사람이 다시 뽑혀도 유지 시간은 새로 센다
	const int32 SelectedIndex = AstralEnemyTargeting::SelectThreatIndex(Origin, ThreatCandidates, DamageWeight, DrawRoll());
	TargetAcquiredTime = (SelectedIndex != INDEX_NONE) ? Now : -1.0;
	return SelectedIndex;
}

void UAstralThreatComponent::ExcludeTarget(const AActor* Target)
{
	if (Target)
	{
		ExcludedAt.Add(Target, GetNow());
	}
}

void UAstralThreatComponent::Reset()
{
	DamageLog.Reset();
	ExcludedAt.Reset();
	TargetAcquiredTime = -1.0;
	LastRetargetRequestTime = -1.0;
	bRetargetPending = false;
}

float UAstralThreatComponent::GetRecentDamage(const AActor* Attacker) const
{
	const TArray<FAstralEnemyDamageEntry>* Entries = Attacker ? DamageLog.Find(Attacker) : nullptr;
	return Entries ? AstralEnemyTargeting::SumDamageInWindow(*Entries, GetNow(), DamageWindow) : 0.f;
}

bool UAstralThreatComponent::IsExcluded(const AActor* Target) const
{
	const double* ExcludedTime = Target ? ExcludedAt.Find(Target) : nullptr;
	return ExcludedTime && AstralEnemyTargeting::IsWithinDuration(*ExcludedTime, GetNow(), ExcludeTime);
}

double UAstralThreatComponent::GetNow() const
{
	const UWorld* World = GetWorld();
	return World ? World->GetTimeSeconds() : 0.0;
}

float UAstralThreatComponent::DrawRoll() const
{
#if !UE_BUILD_SHIPPING
	if (RollOverrideForTest >= 0.f)
	{
		return RollOverrideForTest;
	}
#endif
	return FMath::FRand();
}

void UAstralThreatComponent::PruneExpired(double Now)
{
	for (auto It = DamageLog.CreateIterator(); It; ++It)
	{
		TArray<FAstralEnemyDamageEntry>& Entries = It.Value();
		Entries.RemoveAll([this, Now](const FAstralEnemyDamageEntry& Entry) { return !AstralEnemyTargeting::IsWithinDuration(Entry.Time, Now, DamageWindow); });
		if (!It.Key().IsValid() || Entries.IsEmpty())
		{
			It.RemoveCurrent();
		}
	}

	for (auto It = ExcludedAt.CreateIterator(); It; ++It)
	{
		if (!It.Key().IsValid() || !AstralEnemyTargeting::IsWithinDuration(It.Value(), Now, ExcludeTime))
		{
			It.RemoveCurrent();
		}
	}
}
