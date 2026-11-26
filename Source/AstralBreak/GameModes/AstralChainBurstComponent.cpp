#include "AstralChainBurstComponent.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "AbilitySystem/Effects/AstralGE_UltBlocked.h"
#include "AstralLogChannels.h"
#include "Engine/Engine.h"
#include "Engine/OverlapResult.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerState.h"
#include "GameplayEffect.h"
#include "Net/UnrealNetwork.h"
#include "TimerManager.h"

UAstralChainBurstComponent::UAstralChainBurstComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	PrimaryComponentTick.bCanEverTick = false;
	SetIsReplicatedByDefault(true);

	UltBlockEffectClass = UAstralGE_UltBlocked::StaticClass();
}

UAstralChainBurstComponent* UAstralChainBurstComponent::FindChainBurstComponent(const UObject* WorldContextObject)
{
	const UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContextObject, EGetWorldErrorMode::ReturnNull) : nullptr;
	const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;
	return GameState ? GameState->FindComponentByClass<UAstralChainBurstComponent>() : nullptr;
}

void UAstralChainBurstComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(UAstralChainBurstComponent, ChainState);
}

void UAstralChainBurstComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	RemoveUltBlock();
	if (const UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(CloseTimerHandle);
		World->GetTimerManager().ClearTimer(CastTimeoutHandle);
	}

	Super::EndPlay(EndPlayReason);
}

void UAstralChainBurstComponent::NotifyUltStarted(UAbilitySystemComponent* UserASC)
{
	const AActor* Owner = GetOwner();
	if (!Owner || !Owner->HasAuthority() || !UserASC)
	{
		return;
	}

	// 히어로의 ASC 는 PlayerState 가 갖는다 — 참가자는 PlayerId 로 센다
	const APlayerState* User = Cast<APlayerState>(UserASC->GetOwnerActor());
	if (!User)
	{
		return;
	}

	if (CastingPlayerId != 0)
	{
		// 차단이 걸려 있어 정상 경로로는 오지 않는다(시전 도중 들어와 차단을 받지 못한 사람 등).
		// 앞 시전의 차단 · 멈춤은 그대로 두고 이 시전은 조율하지 않는다 — 끝날 때 맞혔으면 등록은 된다
		UE_LOG(LogAstral, Warning, TEXT("[Chain] player %d started an ult while player %d is casting — not coordinated"), User->GetPlayerId(), CastingPlayerId);
		return;
	}

	const double Now = GetServerTime();
	CastingPlayerId = User->GetPlayerId();

	// 연출 중에는 마감이 오지 않는다 — 열린 체인이 있으면 타이머를 멈춘다(마감 + 유예가 이미 지났으면 여기서 닫힌다)
	const bool bPaused = Tracker.Pause(Now, MakeRules());

	// 한 번에 한 명 — 나머지 히어로의 오의를 막는다
	ApplyUltBlock(User);

	// 쓰는 사람이 나가면 종료 통지가 오지 않는다 — 상한을 둔다
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().SetTimer(CastTimeoutHandle, this, &ThisClass::OnCastTimeout, CastTimeout, false);
	}

	UE_LOG(LogAstral, Log, TEXT("[Chain] ult started by player %d at %.2f — %d blocked, chain #%d %s"),
		CastingPlayerId, Now, UltBlocks.Num(), Tracker.GetChainId(),
		bPaused ? *FString::Printf(TEXT("paused with %.2f s left"), Tracker.GetPausedRemaining()) : TEXT("not open"));

	HandleTrackerChanged();
}

void UAstralChainBurstComponent::NotifyUltEnded(UAbilitySystemComponent* UserASC, bool bHit)
{
	const AActor* Owner = GetOwner();
	if (!Owner || !Owner->HasAuthority() || !UserASC)
	{
		return;
	}

	const APlayerState* User = Cast<APlayerState>(UserASC->GetOwnerActor());
	if (!User)
	{
		return;
	}

	const int32 UserId = User->GetPlayerId();
	const double Now = GetServerTime();

	// 상한이 먼저 났거나 조율되지 않은 시전이면 걷을 것이 없다 — 그래도 맞혔으면 등록은 한다
	const bool bWasCaster = (CastingPlayerId == UserId);
	if (bWasCaster)
	{
		EndCast();
	}

	if (bHit)
	{
		// 등록 시각 = 오의가 끝난 시각. 멈춰 있던 타이머는 Register 가 되돌린 뒤 판정한다
		const EAstralChainRegisterResult Result = Tracker.Register(UserId, Now, CountAliveParty(), MakeRules());

		static const TCHAR* const ResultNames[] = { TEXT("opened"), TEXT("joined"), TEXT("duplicate"), TEXT("queued for next") };
		UE_LOG(LogAstral, Log, TEXT("[Chain] ult by player %d hit, ended at %.2f -> %s (chain #%d, %d participants)"),
			UserId, Now, ResultNames[static_cast<int32>(Result)], Tracker.GetChainId(), Tracker.GetParticipants().Num());

		// 팀 게이지는 체인 참가 여부와 무관하다 — 맞힌 오의가 끝날 때마다 준다(타이머가 도는 그때 찬다)
		GrantTeamUltGain(User);
	}
	else
	{
		// 못 맞힌 오의 — 등록도 팀 게이지도 없다. 멈춰 둔 타이머만 남아 있던 시간으로 다시 돈다
		if (bWasCaster)
		{
			Tracker.Resume(Now);
		}
		UE_LOG(LogAstral, Log, TEXT("[Chain] ult by player %d missed, ended at %.2f — no chain entry"), UserId, Now);
	}

	HandleTrackerChanged();
}

float UAstralChainBurstComponent::GetRemainingSeconds() const
{
	if (ChainState.Phase != EAstralChainPhase::Open)
	{
		return 0.f;
	}
	if (ChainState.bTimerPaused)
	{
		return FMath::Max(ChainState.PausedRemainingSeconds, 0.f);
	}
	return static_cast<float>(FMath::Max(ChainState.DeadlineServerTime - GetServerTime(), 0.0));
}

APlayerState* UAstralChainBurstComponent::FindPlayerState(int32 PlayerId) const
{
	if (const AGameStateBase* GameState = GetGameState<AGameStateBase>())
	{
		for (APlayerState* PlayerState : GameState->PlayerArray)
		{
			if (PlayerState && PlayerState->GetPlayerId() == PlayerId)
			{
				return PlayerState;
			}
		}
	}
	return nullptr;
}

FString UAstralChainBurstComponent::GetDebugString() const
{
	static const TCHAR* const PhaseNames[] = { TEXT("None"), TEXT("Open"), TEXT("Burst") };

	TStringBuilder<256> Out;
	Out.Appendf(TEXT("Chain #%d %s %d/%d"), ChainState.ChainId, PhaseNames[static_cast<int32>(ChainState.Phase)], ChainState.ParticipantIds.Num(), MaxParticipants);
	if (!ChainState.ParticipantIds.IsEmpty())
	{
		Out.Append(TEXT(" ["));
		for (int32 Index = 0; Index < ChainState.ParticipantIds.Num(); ++Index)
		{
			Out.Appendf(TEXT("%s%d"), Index > 0 ? TEXT(" ") : TEXT(""), ChainState.ParticipantIds[Index]);
		}
		Out.Append(TEXT("]"));
	}
	if (ChainState.Phase == EAstralChainPhase::Open)
	{
		Out.Appendf(TEXT(" %.1fs%s"), GetRemainingSeconds(), ChainState.bTimerPaused ? TEXT(" (paused)") : TEXT(""));
	}
	if (ChainState.CastingPlayerId != 0)
	{
		Out.Appendf(TEXT(" | Casting %d"), ChainState.CastingPlayerId);
	}
	if (ChainState.LastBurstChainId > 0)
	{
		Out.Appendf(TEXT(" | LastBurst #%d x%d"), ChainState.LastBurstChainId, ChainState.LastBurstCount);
	}
	return Out.ToString();
}

void UAstralChainBurstComponent::OnRep_ChainState(const FAstralChainState& OldState)
{
	OnChainStateChanged.Broadcast(ChainState, OldState);
}

FAstralChainRules UAstralChainBurstComponent::MakeRules() const
{
	FAstralChainRules Rules;
	Rules.WindowSeconds = WindowSeconds;
	Rules.GraceSeconds = GraceSeconds;
	Rules.MaxParticipants = MaxParticipants;
	return Rules;
}

double UAstralChainBurstComponent::GetServerTime() const
{
	const AGameStateBase* GameState = GetGameState<AGameStateBase>();
	return GameState ? GameState->GetServerWorldTimeSeconds() : 0.0;
}

int32 UAstralChainBurstComponent::CountAliveParty() const
{
	int32 Count = 0;
	if (const AGameStateBase* GameState = GetGameState<AGameStateBase>())
	{
		for (const APlayerState* PlayerState : GameState->PlayerArray)
		{
			if (!PlayerState || PlayerState->IsABot() || PlayerState->IsOnlyASpectator())
			{
				continue;
			}
			const APawn* Pawn = PlayerState->GetPawn();
			if (Pawn && !UAstralCombatStatics::IsDeadOrDying(Pawn))
			{
				++Count;
			}
		}
	}
	return Count;
}

void UAstralChainBurstComponent::GrantTeamUltGain(const APlayerState* User) const
{
	const AGameStateBase* GameState = GetGameState<AGameStateBase>();
	if (!GameState || TeamUltGain <= 0.f)
	{
		return;
	}

	for (APlayerState* PlayerState : GameState->PlayerArray)
	{
		if (!PlayerState || PlayerState == User)
		{
			continue;
		}
		const APawn* Pawn = PlayerState->GetPawn();
		if (!Pawn || UAstralCombatStatics::IsDeadOrDying(Pawn))
		{
			continue;
		}
		// 기존 수급 경로 — UltGainMultiplier 가 받는 쪽에서 곱해진다. 히어로 자원 세트가 없는 ASC 에는 닿을 속성이 없어 아무 일도 없다
		UAstralCombatStatics::ApplyUltGainToSelf(UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(PlayerState), TeamUltGain);
	}
}

void UAstralChainBurstComponent::HandleTrackerChanged()
{
	const bool bOpen = (Tracker.GetPhase() == EAstralChainPhase::Open);
	const bool bPaused = bOpen && Tracker.IsPaused();

	FAstralChainState NewState;
	NewState.ChainId = Tracker.GetChainId();
	NewState.Phase = Tracker.GetPhase();
	NewState.ParticipantIds = Tracker.GetParticipants();
	NewState.DeadlineServerTime = (bOpen && !bPaused) ? Tracker.GetDeadline() : 0.0;
	NewState.CastingPlayerId = CastingPlayerId;
	NewState.bTimerPaused = bPaused;
	NewState.PausedRemainingSeconds = bPaused ? static_cast<float>(Tracker.GetPausedRemaining()) : 0.f;
	NewState.LastBurstChainId = Tracker.GetLastBurstChainId();
	NewState.LastBurstCount = Tracker.GetLastBurstCount();

	if (NewState != ChainState)
	{
		const FAstralChainState OldState = MoveTemp(ChainState);
		ChainState = MoveTemp(NewState);
		if (AActor* Owner = GetOwner())
		{
			Owner->ForceNetUpdate();
		}
		OnChainStateChanged.Broadcast(ChainState, OldState);
	}

	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	FTimerManager& TimerManager = World->GetTimerManager();

	// 규칙 6 — 등록은 오의 끝에 일어나고 연출 중에는 타이머가 멈추므로, 닫히는 순간 연출 중인 참가자가 없다. 버스트는 닫힌 직후에 나간다.
	// 다음 틱으로 미루는 것은 부른 쪽의 호출 스택(오의 종료) 안에서 다른 대상에게 피해를 넣지 않으려는 것이다
	if (Tracker.GetPhase() == EAstralChainPhase::Burst && !bBurstScheduled)
	{
		bBurstScheduled = true;
		TimerManager.SetTimerForNextTick(this, &ThisClass::FireBurst);
	}

	// 마감 타이머 — 열려 있고 멈춰 있지 않은 동안만. 등록 · 재개가 올 때마다 다시 건다
	TimerManager.ClearTimer(CloseTimerHandle);
	if (bOpen && !bPaused)
	{
		// 판정은 '마감 + 유예를 넘긴 뒤' 라 조금 더 기다린다. 그래도 일렀으면 OnCloseTimer 가 다시 건다
		const float Delay = static_cast<float>(FMath::Max(Tracker.GetCloseTime(MakeRules()) - GetServerTime(), 0.0)) + 0.01f;
		TimerManager.SetTimer(CloseTimerHandle, this, &ThisClass::OnCloseTimer, Delay, false);
	}
}

void UAstralChainBurstComponent::OnCloseTimer()
{
	Tracker.Advance(GetServerTime(), MakeRules());
	HandleTrackerChanged();
}

void UAstralChainBurstComponent::ApplyUltBlock(const APlayerState* Caster)
{
	const AGameStateBase* GameState = GetGameState<AGameStateBase>();
	const UGameplayEffect* BlockEffect = UltBlockEffectClass ? UltBlockEffectClass->GetDefaultObject<UGameplayEffect>() : nullptr;
	if (!GameState || !BlockEffect)
	{
		return;
	}

	// 지금 있는 나머지 전원에게 건다(죽은 사람 포함 — 풀릴 때 같이 풀린다). 시전 도중 들어온 사람에게는 걸리지 않는다
	for (APlayerState* PlayerState : GameState->PlayerArray)
	{
		if (!PlayerState || PlayerState == Caster)
		{
			continue;
		}
		UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(PlayerState);
		if (!ASC)
		{
			continue;
		}
		const FActiveGameplayEffectHandle Handle = ASC->ApplyGameplayEffectToSelf(BlockEffect, 1.f, ASC->MakeEffectContext());
		if (Handle.IsValid())
		{
			FUltBlockEntry& Entry = UltBlocks.AddDefaulted_GetRef();
			Entry.ASC = ASC;
			Entry.Handle = Handle;
		}
	}
}

void UAstralChainBurstComponent::RemoveUltBlock()
{
	for (const FUltBlockEntry& Entry : UltBlocks)
	{
		if (UAbilitySystemComponent* ASC = Entry.ASC.Get())
		{
			ASC->RemoveActiveGameplayEffect(Entry.Handle);
		}
	}
	UltBlocks.Reset();
}

void UAstralChainBurstComponent::EndCast()
{
	RemoveUltBlock();
	CastingPlayerId = 0;
	if (const UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(CastTimeoutHandle);
	}
}

void UAstralChainBurstComponent::OnCastTimeout()
{
	if (CastingPlayerId == 0)
	{
		return;
	}

	// 종료 통지가 오지 않았다(쓰는 사람이 나갔다) — 못 맞힌 것처럼 걷는다. 그 오의가 뒤늦게 맞힌 채 끝나면 NotifyUltEnded 가 그때 등록한다
	UE_LOG(LogAstral, Warning, TEXT("[Chain] no end notice from player %d after %.1f s — unblocking and resuming the timer"), CastingPlayerId, CastTimeout);
	EndCast();
	Tracker.Resume(GetServerTime());
	HandleTrackerChanged();
}

void UAstralChainBurstComponent::FireBurst()
{
	bBurstScheduled = false;
	if (Tracker.GetPhase() != EAstralChainPhase::Burst)
	{
		return;
	}

	const TArray<int32> ParticipantIds = Tracker.GetParticipants();
	LastBurstReport = FAstralChainBurstReport();
	LastBurstReport.ChainId = Tracker.GetChainId();
	LastBurstReport.Count = ParticipantIds.Num();
	ApplyBurstDamage(ParticipantIds);

	UE_LOG(LogAstral, Log, TEXT("[Chain] burst #%d x%d — total %.1f, %d contributors, %d targets"),
		LastBurstReport.ChainId, LastBurstReport.Count, LastBurstReport.TotalDamage, LastBurstReport.NumContributors, LastBurstReport.NumTargets);

	// 대기한 오의가 있으면 여기서 다음 체인이 열린다 (그 체인이 곧바로 Burst 가 되면 HandleTrackerChanged 가 다시 예약한다)
	Tracker.FinishBurst(GetServerTime(), CountAliveParty(), MakeRules());
	HandleTrackerChanged();
}

void UAstralChainBurstComponent::ApplyBurstDamage(const TArray<int32>& ParticipantIds)
{
	UWorld* World = GetWorld();
	const int32 Count = ParticipantIds.Num();
	if (!World || Count <= 0)
	{
		return;
	}

	// 인원 배수 — [0] = 2명
	float CountMultiplier = 1.f;
	if (!BurstDamageMultipliers.IsEmpty())
	{
		CountMultiplier = BurstDamageMultipliers[FMath::Clamp(Count - 2, 0, BurstDamageMultipliers.Num() - 1)];
	}
	const float TotalDamage = BurstBaseDamage * CountMultiplier;
	LastBurstReport.TotalDamage = TotalDamage;

	// 피해를 넣을 사람 — 죽었거나 나간 참가자는 인원(배수)에는 남고, 그 몫은 남은 사람이 나눈다
	struct FContributor
	{
		UAbilitySystemComponent* ASC = nullptr;
		AActor* Avatar = nullptr;
	};
	TArray<FContributor, TInlineAllocator<4>> Contributors;
	for (const int32 ParticipantId : ParticipantIds)
	{
		UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(FindPlayerState(ParticipantId));
		AActor* Avatar = ASC ? ASC->GetAvatarActor() : nullptr;
		if (Avatar && !UAstralCombatStatics::IsDeadOrDying(Avatar))
		{
			Contributors.Add({ ASC, Avatar });
		}
	}
	LastBurstReport.NumContributors = Contributors.Num();
	if (Contributors.IsEmpty())
	{
		return;
	}

	// 중심 — 마지막 참가자. 그 사람이 없으면 남은 사람 가운데 가장 늦게 들어온 사람
	const FVector Center = Contributors.Last().Avatar->GetActorLocation();
	const float Share = TotalDamage / Contributors.Num();

	TArray<FOverlapResult> Overlaps;
	const FCollisionQueryParams Params(SCENE_QUERY_STAT(AstralChain_Burst), false);
	World->OverlapMultiByChannel(Overlaps, Center, FQuat::Identity, ECC_Pawn, FCollisionShape::MakeSphere(BurstRadius), Params);

	TSet<AActor*> Visited;
	for (const FOverlapResult& Overlap : Overlaps)
	{
		AActor* Target = Overlap.GetActor();
		if (!Target || Visited.Contains(Target))
		{
			continue;
		}
		Visited.Add(Target);

		const FVector TargetLocation = Target->GetActorLocation();
		const FHitResult Hit(Target, Overlap.GetComponent(), TargetLocation, (Center - TargetLocation).GetSafeNormal());

		// 각자의 ASC 를 가해자로 — OutgoingDamageMultiplier · 위협이 사람별로 계산되고, ChainBurstDamageMultiplier 는 자기 몫에만 곱해진다.
		// 피아 · 사망 필터는 ApplyAttackHit 이 한다. 적중 수급(오의 게이지)은 어빌리티가 따로 부르는 것이라 이 경로로는 차지 않는다
		bool bDamaged = false;
		for (const FContributor& Contributor : Contributors)
		{
			float PersonalMultiplier = 1.f;
			if (Contributor.ASC->HasAttributeSetForAttribute(UAstralHeroResourceSet::GetChainBurstDamageMultiplierAttribute()))
			{
				PersonalMultiplier = Contributor.ASC->GetNumericAttribute(UAstralHeroResourceSet::GetChainBurstDamageMultiplierAttribute());
			}
			bDamaged |= UAstralCombatStatics::ApplyAttackHit(Contributor.ASC, Contributor.Avatar, nullptr, Hit, Share * PersonalMultiplier);
		}
		LastBurstReport.NumTargets += bDamaged ? 1 : 0;
	}
}
