#include "AstralTargetingComponent.h"

#include "AbilitySystem/AstralCombatStatics.h"
#include "AstralLogChannels.h"
#include "Character/Components/AstralHealthComponent.h"
#include "CollisionQueryParams.h"
#include "DrawDebugHelpers.h"
#include "Engine/OverlapResult.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"

UAstralTargetingComponent::UAstralTargetingComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;

	// 로컬 전용 — 선정은 클라가, 서버 전달은 5단계의 TargetData (설계 §8)
	SetIsReplicatedByDefault(false);
}

void UAstralTargetingComponent::BeginPlay()
{
	Super::BeginPlay();

	// 내 사망 → 해제. HealthComponent 델리게이트는 컴포넌트 수명이라 1회 바인딩
	BoundHealthComponent = UAstralHealthComponent::FindHealthComponent(GetOwner());
	if (BoundHealthComponent)
	{
		BoundHealthComponent->OnDeathStarted.AddDynamic(this, &ThisClass::HandleOwnerDeathStarted);
	}
}

void UAstralTargetingComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	// Travel 시 TargetActor가 다른 레벨의 액터를 가리키지 않도록 정리
	ClearLock();
	DebugCandidates.Reset();
	DebugBestCandidate = nullptr;

	if (BoundHealthComponent)
	{
		BoundHealthComponent->OnDeathStarted.RemoveDynamic(this, &ThisClass::HandleOwnerDeathStarted);
		BoundHealthComponent = nullptr;
	}

	Super::EndPlay(EndPlayReason);
}

void UAstralTargetingComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	// 선정 주체는 로컬 제어 폰뿐 (리슨 호스트 포함). 원격 폰의 서버 인스턴스·시뮬 프록시는 아무것도 하지 않는다
	const APawn* Pawn = GetPawn<APawn>();
	if (!Pawn || !Pawn->IsLocallyControlled())
	{
		return;
	}

	// 매 프레임 — 약한 참조 유효성 (타겟 액터 소멸은 주기를 기다리지 않는다)
	if (Mode == EAstralTargetingMode::HardLocked && !HardLockTarget.IsSet())
	{
		ClearLock();
	}

	// 주기 — 유지 조건 (거리·LOS·CanDamage)
	MaintainAccumulator += DeltaTime;
	if (MaintainAccumulator >= MaintainInterval)
	{
		const float Interval = MaintainAccumulator;
		MaintainAccumulator = 0.f;

		if (Mode == EAstralTargetingMode::HardLocked)
		{
			CheckMaintainConditions(Interval);
		}

#if !UE_BUILD_SHIPPING
		if (bEnableDebug)
		{
			RefreshDebugCandidates();
		}
#endif
	}

#if !UE_BUILD_SHIPPING
	if (bEnableDebug)
	{
		DrawDebug();
	}
#endif
}

bool UAstralTargetingComponent::TryLockOn()
{
	if (Mode == EAstralTargetingMode::HardLocked)
	{
		// 다른 타겟은 3단계 CycleTarget의 몫
		return true;
	}

	TArray<FAstralTargetCandidate> Candidates;
	GatherCandidates(Candidates);

	const int32 BestIndex = AstralTargeting::SelectBestCandidate(Candidates, INDEX_NONE, Params);
	if (BestIndex == INDEX_NONE)
	{
		UE_LOG(LogAstral, Verbose, TEXT("[Targeting] TryLockOn: 후보 없음 (%s)"), *GetNameSafe(GetOwner()));
		return false;
	}

	FAstralTargetHandle NewTarget;
	NewTarget.TargetActor = Candidates[BestIndex].Actor;
	NewTarget.TargetPointId = NAME_None;

	LosLostTime = 0.f;
	MaintainAccumulator = 0.f;

	CommitTargetingState(EAstralTargetingMode::HardLocked, NewTarget);

#if !UE_BUILD_SHIPPING
	DebugCandidates = MoveTemp(Candidates);
	DebugBestCandidate = HardLockTarget.TargetActor;
#endif

	return true;
}

void UAstralTargetingComponent::ClearLock()
{
	LosLostTime = 0.f;

	// 자동 전환 없음 — 다음 후보로 넘어가지 않는다
	CommitTargetingState(EAstralTargetingMode::Idle, FAstralTargetHandle());
}

void UAstralTargetingComponent::ToggleLockOn()
{
	if (Mode == EAstralTargetingMode::HardLocked)
	{
		ClearLock();
	}
	else
	{
		TryLockOn();
	}
}

const FAstralTargetHandle& UAstralTargetingComponent::GetEffectiveTarget() const
{
	static const FAstralTargetHandle EmptyHandle;
	return (Mode == EAstralTargetingMode::HardLocked) ? HardLockTarget : EmptyHandle;
}

void UAstralTargetingComponent::CommitTargetingState(EAstralTargetingMode NewMode, const FAstralTargetHandle& NewTarget)
{
	const bool bModeChanged = (Mode != NewMode);
	const bool bTargetChanged = (HardLockTarget.TargetActor != NewTarget.TargetActor) || (HardLockTarget.TargetPointId != NewTarget.TargetPointId);
	if (!bModeChanged && !bTargetChanged)
	{
		return;
	}

	UE_LOG(LogAstral, Verbose, TEXT("[Targeting] %s: mode %d -> %d, target %s -> %s"), *GetNameSafe(GetOwner()),
		static_cast<int32>(Mode), static_cast<int32>(NewMode), *GetNameSafe(HardLockTarget.TargetActor.Get()), *GetNameSafe(NewTarget.TargetActor.Get()));

	Mode = NewMode;
	HardLockTarget = NewTarget;

	OnTargetingChanged.Broadcast();
}

bool UAstralTargetingComponent::GetViewPoint(FVector& OutLocation, FRotator& OutRotation) const
{
	const APlayerController* PC = GetController<APlayerController>();
	if (!PC)
	{
		return false;
	}

	PC->GetPlayerViewPoint(OutLocation, OutRotation);
	return true;
}

void UAstralTargetingComponent::GatherCandidates(TArray<FAstralTargetCandidate>& OutCandidates) const
{
	OutCandidates.Reset();

	const APawn* Pawn = GetPawn<APawn>();
	UWorld* World = Pawn ? Pawn->GetWorld() : nullptr;
	if (!World)
	{
		return;
	}

	FVector ViewLocation;
	FRotator ViewRotation;
	if (!GetViewPoint(ViewLocation, ViewRotation))
	{
		return;
	}

	const FVector SelfLocation = Pawn->GetActorLocation();

	// 1차 수집 — Pawn 오브젝트 타입 스피어 오버랩 (GetAllActorsOfClass 금지)
	TArray<FOverlapResult> Overlaps;
	FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(AstralTargeting_Gather), false);
	QueryParams.AddIgnoredActor(Pawn);
	World->OverlapMultiByObjectType(Overlaps, SelfLocation, FQuat::Identity, FCollisionObjectQueryParams(ECC_Pawn), FCollisionShape::MakeSphere(Params.AcquireRange), QueryParams);

	const AActor* CurrentTarget = HardLockTarget.TargetActor.Get();
	TSet<const AActor*> Seen;

	for (const FOverlapResult& Overlap : Overlaps)
	{
		AActor* Actor = Overlap.GetActor();
		if (!Actor || Seen.Contains(Actor))
		{
			continue;
		}
		Seen.Add(Actor);

		// 팀·사망 필터 — 데미지 조건과 동일 (아군/중립/사망 대상은 후보가 아니다)
		if (!UAstralCombatStatics::CanDamage(Pawn, Actor))
		{
			continue;
		}

		FAstralTargetHandle Handle;
		Handle.TargetActor = Actor;
		const FVector AimLocation = Handle.GetAimLocation();

		const float Distance = FVector::Dist(SelfLocation, AimLocation);
		const float YawDeg = AstralTargeting::ComputeYawDeg(ViewLocation, ViewRotation.Yaw, AimLocation);
		if (!AstralTargeting::PassesAcquireFilter(Distance, YawDeg, Params))
		{
			continue;
		}

		if (!HasLineOfSight(Actor, AimLocation))
		{
			continue;
		}

		FAstralTargetCandidate& Candidate = OutCandidates.AddDefaulted_GetRef();
		Candidate.Actor = Actor;
		Candidate.Distance = Distance;
		Candidate.YawDeg = YawDeg;
		Candidate.bIsCurrentTarget = (Actor == CurrentTarget);
		Candidate.Score = AstralTargeting::ScoreCandidate(Distance, YawDeg, Candidate.bIsCurrentTarget, Params);
	}

	OutCandidates.Sort([](const FAstralTargetCandidate& A, const FAstralTargetCandidate& B)
	{
		return A.Score > B.Score;
	});
}

bool UAstralTargetingComponent::HasLineOfSight(const AActor* Target, const FVector& AimLocation) const
{
	const APawn* Pawn = GetPawn<APawn>();
	UWorld* World = Pawn ? Pawn->GetWorld() : nullptr;
	if (!World || !Target)
	{
		return false;
	}

	FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(AstralTargeting_LOS), false);
	QueryParams.AddIgnoredActor(Pawn);

	FHitResult Hit;
	const bool bBlocked = World->LineTraceSingleByChannel(Hit, Pawn->GetActorLocation(), AimLocation, ECC_Visibility, QueryParams);

	// 캡슐(Pawn 프로파일)은 Visibility를 무시하고 메시는 막는다 — 타겟 자신에 막힌 것은 가시
	// TODO: 전용 채널로 trace 예정
	return !bBlocked || (Hit.GetActor() == Target);
}

void UAstralTargetingComponent::CheckMaintainConditions(float Interval)
{
	const APawn* Pawn = GetPawn<APawn>();
	const AActor* Target = HardLockTarget.TargetActor.Get();
	if (!Pawn || !Target)
	{
		ClearLock();
		return;
	}

	// 사망·팀 변경 — 데미지 조건이 깨지면 락온도 깨진다
	if (!UAstralCombatStatics::CanDamage(Pawn, Target))
	{
		ClearLock();
		return;
	}

	const FVector AimLocation = HardLockTarget.GetAimLocation();
	if (FVector::Dist(Pawn->GetActorLocation(), AimLocation) > Params.MaintainRange)
	{
		ClearLock();
		return;
	}

	// LOS — 유예 누적. 기둥 뒤를 스치는 정도는 풀리지 않는다
	if (HasLineOfSight(Target, AimLocation))
	{
		LosLostTime = 0.f;
	}
	else
	{
		LosLostTime += Interval;
		if (LosLostTime >= Params.LosGraceTime)
		{
			ClearLock();
		}
	}
}

void UAstralTargetingComponent::HandleOwnerDeathStarted(AActor* OwningActor)
{
	ClearLock();
}

#if !UE_BUILD_SHIPPING
void UAstralTargetingComponent::RefreshDebugCandidates()
{
	GatherCandidates(DebugCandidates);

	int32 CurrentIndex = INDEX_NONE;
	for (int32 Index = 0; Index < DebugCandidates.Num(); ++Index)
	{
		if (DebugCandidates[Index].bIsCurrentTarget)
		{
			CurrentIndex = Index;
			break;
		}
	}

	// "지금 선정한다면" — 히스테리시스 포함. HardLocked 중엔 표시만 하고 적용하지 않는다 (자동 전환 금지)
	const int32 BestIndex = AstralTargeting::SelectBestCandidate(DebugCandidates, CurrentIndex, Params);
	if (BestIndex != INDEX_NONE)
	{
		DebugBestCandidate = DebugCandidates[BestIndex].Actor;
	}
	else
	{
		DebugBestCandidate = nullptr;
	}
}

void UAstralTargetingComponent::DrawDebug() const
{
#if ENABLE_DRAW_DEBUG
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	const AActor* Best = DebugBestCandidate.Get();
	for (const FAstralTargetCandidate& Candidate : DebugCandidates)
	{
		const AActor* Actor = Candidate.Actor.Get();
		if (!Actor || Candidate.bIsCurrentTarget)
		{
			continue;
		}

		// 후보 = 회색, 지금 뽑힐 후보 = 노랑
		const FColor Color = (Actor == Best) ? FColor::Yellow : FColor(128, 128, 128);
		DrawDebugSphere(World, Actor->GetActorLocation(), 20.f, 8, Color, false, -1.f, 0, 1.f);
	}

	// 선택 타겟 = 초록 스피어 + 폰에서 선
	if (Mode == EAstralTargetingMode::HardLocked && HardLockTarget.IsSet())
	{
		const FVector AimLocation = HardLockTarget.GetAimLocation();
		const FColor Color = (LosLostTime > 0.f) ? FColor::Orange : FColor::Green;
		DrawDebugSphere(World, AimLocation, 40.f, 12, Color, false, -1.f, 0, 2.f);

		if (const APawn* Pawn = GetPawn<APawn>())
		{
			DrawDebugLine(World, Pawn->GetActorLocation(), AimLocation, Color, false, -1.f, 0, 1.f);
		}
	}
#endif
}
#endif
