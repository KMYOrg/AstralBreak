// 단위 B 어그로 네트워크 시험 — 한 프로세스 멀티 PIE (설계 Docs/Design/m3-enemy-ai.md §9 검증 계획 B0 · B3 ~ B6)
//
// 리슨 서버 · Dedicated 를 PIE 로 띄워 CombatTestMap 에서 적 한 마리(BP_Enemy_Melee)를 서버에서 부르고,
// 서버 월드의 컨트롤러 · 위협 컴포넌트를 직접 본다. 추첨 값은 컴포넌트의 시험용 고정 값으로 정한다.
//
//   B2  피해 기록이 없으면 가장 가까운 플레이어 (월드에서)
//   B3  추격 중 다른 사람이 때리면 바로 그 사람으로 · 공격 중에 맞으면 그 공격이 끝난 뒤
//   B4  유지 시간 안에는 판단 지점이 와도 안 바뀌고, 지나면 다시 뽑는다
//   B5  Hostility 를 올린 사람이 뽑힌다 · 0 이면 안 뽑힌다 · 대조: DamageWeight 0 이면 때린 사람이 뽑히지 않는다
//   B6  닿을 수 없는 타깃 → 제외 → 다른 사람 · 제외가 풀리면 다시 후보 (공중에 띄운 히어로 — 경로 끝을 NavMesh 에 내릴 수 없는 경우)
//   B0-1 클라이언트 히어로의 실제 공격이 OnDamaged 에 싣는 Instigator
//
// 다른 히어로가 준 피해는 서버에서 UAstralCombatStatics::ApplyAttackHit(실제 무기 판정이 쓰는 함수)로 넣는다 — 클라이언트의 실제 입력은 B0-1 한 번이다.
// 시간은 서버 월드 시간으로 잰다. 조회 함수는 AstralEnemyCombatPieTests.cpp 의 것과 같은 모양이다(파일마다 따로 둔다).

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AstralPieTestHelpers.h"

#include "AI/AstralThreatComponent.h"
#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Character/Enemy/AstralCombatCharacter.h"
#include "Character/Enemy/AstralEnemyController.h"
#include "Components/StateTreeAIComponent.h"
#include "Engine/GameInstance.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerState.h"
#include "GameplayAbilitySpec.h"
#include "GameplayTagContainer.h"
#include "Player/AstralPlayerController.h"

namespace AstralEnemyAggroPie
{
	using namespace AstralPieTest;

	const TCHAR* const MapPath = TEXT("/Game/Maps/CombatTestMap");
	const TCHAR* const MapName = TEXT("CombatTestMap");
	const TCHAR* const EnemyClassPrefix = TEXT("BP_Enemy_Melee");

	// 태그는 런타임 모듈이 내보내지 않는다 — 이름으로 찾는다
	const TCHAR* const TelegraphTagName = TEXT("State.Telegraphing");
	const TCHAR* const MeleeAbilityTagName = TEXT("Ability.Enemy.Attack.Melee");
	const TCHAR* const BasicAttackInputTagName = TEXT("InputTag.Attack.Basic");

	// GA_Enemy_MeleeAttack · ST_Enemy_Melee 의 값(잠정) — 바꾸면 여기도 바꾼다. 위협 값(유지 시간 등)은 컴포넌트에서 읽는다
	constexpr float AttackDamage = 15.f;
	constexpr double TelegraphSeconds = 1.0;
	constexpr double RecoverySeconds = 1.0;

	/** 표본이 프레임 단위라 생기는 오차 + 상태 전환 프레임 */
	constexpr double TimingSlack = 0.35;

	/** 시험이 서버에서 넣는 다른 히어로의 피해 — 적(HP 100)이 죽지 않게 작게 */
	constexpr float ProbeDamage = 1.f;

	// CombatTestMap 좌표 — AstralEnemyCombatPieTests.cpp 와 같은 자리
	const FVector NearHeroLocation(1100.0, -400.0, 92.0);
	const FVector FarHeroLocation(1100.0, 900.0, 92.0);
	constexpr float EnemySpawnDistance = 600.f;

	/** 닿을 수 없는 자리 — 이만큼 띄우면 경로 끝을 NavMesh 에 내릴 수 없다 */
	constexpr double UnreachableHeight = 3000.0;

	struct FDamageSeen
	{
		TWeakObjectPtr<AActor> Instigator;
		FString InstigatorClass;
		float Damage = 0.f;
	};

	struct FContext : FContextBase
	{
		bool bDedicated = false;
		int32 NumPlayers = 2;

		/** 가까운 쪽 = 클라이언트 자리의 플레이어(실제 공격 입력을 넣는다), 먼 쪽 = 나머지 */
		int32 NearId = 0;
		int32 FarId = 0;

		TWeakObjectPtr<AAstralCombatCharacter> Enemy;
		FVector EnemySpawnLocation = FVector::ZeroVector;

		// 매 프레임 표본 — 예고 태그와 공격 어빌리티의 오르내림
		bool bTelegraphing = false;
		bool bAttackActive = false;
		TArray<double> TelegraphStartTimes;
		TArray<double> TelegraphEndTimes;
		TArray<double> AttackEndTimes;

		/** 적의 HealthSet::OnDamaged 가 실은 값 — 시험이 직접 구독한다 */
		TArray<FDamageSeen> DamageSeen;

		// 단계 사이에 넘기는 값
		double MarkTime = 0.0;
		double HoldStartTime = 0.0;
		double SwitchTime = 0.0;
		double RequestTime = 0.0;
		double ExcludedTime = 0.0;
		int32 MarkTelegraphStarts = 0;
		int32 MarkTelegraphEnds = 0;
		int32 MarkDamageSeen = 0;
		float NearHealthBefore = 0.f;
		float EnemyHealthBefore = 0.f;
	};

	// ─── 조회 ───

	APlayerController* GetLocalPC(const UWorld* World)
	{
		const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
		return GameInstance ? GameInstance->GetFirstLocalPlayerController(World) : nullptr;
	}

	/** 로컬 컨트롤러가 있는 PIE 월드 — 리슨: 호스트 + 클라이언트들, Dedicated: 클라이언트들 */
	TArray<UWorld*> GetSeatWorlds()
	{
		TArray<UWorld*> Out;
		for (UWorld* World : GetPieWorlds())
		{
			const ENetMode NetMode = World->GetNetMode();
			if (NetMode == NM_ListenServer || NetMode == NM_Client)
			{
				Out.Add(World);
			}
		}
		return Out;
	}

	int32 LocalPlayerIdIn(const UWorld* World)
	{
		const APlayerController* PC = GetLocalPC(World);
		return (PC && PC->PlayerState) ? PC->PlayerState->GetPlayerId() : 0;
	}

	UWorld* FindSeatWorld(int32 PlayerId)
	{
		for (UWorld* World : GetSeatWorlds())
		{
			if (LocalPlayerIdIn(World) == PlayerId)
			{
				return World;
			}
		}
		return nullptr;
	}

	/** 이 월드가 보는 그 플레이어의 폰 */
	AAstralCharacter* PawnIn(const UWorld* World, int32 PlayerId)
	{
		const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;
		if (!GameState)
		{
			return nullptr;
		}
		for (const APlayerState* PlayerState : GameState->PlayerArray)
		{
			if (PlayerState && PlayerState->GetPlayerId() == PlayerId)
			{
				return Cast<AAstralCharacter>(PlayerState->GetPawn());
			}
		}
		return nullptr;
	}

	AAstralCharacter* ServerPawn(int32 PlayerId)
	{
		return PawnIn(FindServerWorld(), PlayerId);
	}

	float HealthOf(const AActor* Actor)
	{
		const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(Actor);
		return HealthComponent ? HealthComponent->GetHealth() : -1.f;
	}

	bool IsDead(const AActor* Actor)
	{
		const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(Actor);
		return HealthComponent && HealthComponent->IsDeadOrDying();
	}

	TArray<AAstralCombatCharacter*> EnemiesIn(UWorld* World)
	{
		TArray<AAstralCombatCharacter*> Out;
		if (World)
		{
			for (TActorIterator<AAstralCombatCharacter> It(World); It; ++It)
			{
				if (It->GetClass()->GetName().StartsWith(EnemyClassPrefix))
				{
					Out.Add(*It);
				}
			}
		}
		return Out;
	}

	AAstralEnemyController* EnemyController(const FContext& Ctx)
	{
		return Ctx.Enemy.IsValid() ? Cast<AAstralEnemyController>(Ctx.Enemy->GetController()) : nullptr;
	}

	UAstralThreatComponent* Threat(const FContext& Ctx)
	{
		const AAstralEnemyController* Controller = EnemyController(Ctx);
		return Controller ? Controller->GetThreatComponent() : nullptr;
	}

	AActor* TargetOf(const FContext& Ctx)
	{
		const AAstralEnemyController* Controller = EnemyController(Ctx);
		return Controller ? Controller->GetCurrentTarget() : nullptr;
	}

	bool EnemyHasTag(const FContext& Ctx, const TCHAR* TagName)
	{
		const UAbilitySystemComponent* ASC = Ctx.Enemy.IsValid() ? Ctx.Enemy->GetAbilitySystemComponent() : nullptr;
		return ASC && ASC->HasMatchingGameplayTag(FGameplayTag::RequestGameplayTag(TagName));
	}

	bool EnemyAttackActive(const FContext& Ctx)
	{
		const UAbilitySystemComponent* ASC = Ctx.Enemy.IsValid() ? Ctx.Enemy->GetAbilitySystemComponent() : nullptr;
		if (!ASC)
		{
			return false;
		}
		TArray<FGameplayAbilitySpec*> Specs;
		ASC->GetActivatableGameplayAbilitySpecsByAllMatchingTags(FGameplayTagContainer(FGameplayTag::RequestGameplayTag(MeleeAbilityTagName)), Specs, false);
		return Specs.Num() > 0 && Specs[0] && Specs[0]->IsActive();
	}

	double ServerTime()
	{
		const UWorld* World = FindServerWorld();
		return World ? World->GetTimeSeconds() : 0.0;
	}

	double EnemyDistanceTo(const FContext& Ctx, const AActor* Other)
	{
		return (Ctx.Enemy.IsValid() && Other) ? FVector::Dist2D(Ctx.Enemy->GetActorLocation(), Other->GetActorLocation()) : -1.0;
	}

	// ─── 추첨 값 — 컨트롤러가 후보를 모으는 순서(PlayerArray)에서 그 플레이어가 몇 번째인가로 정한다 ───

	int32 CandidateIndexOf(int32 PlayerId)
	{
		const UWorld* ServerWorld = FindServerWorld();
		const AGameStateBase* GameState = ServerWorld ? ServerWorld->GetGameState() : nullptr;
		int32 Index = 0;
		if (GameState)
		{
			for (const APlayerState* PlayerState : GameState->PlayerArray)
			{
				if (!PlayerState || PlayerState->IsABot() || !PlayerState->GetPawn())
				{
					continue;
				}
				if (PlayerState->GetPlayerId() == PlayerId)
				{
					return Index;
				}
				++Index;
			}
		}
		return INDEX_NONE;
	}

	/** 후보 둘 중 이 플레이어가 뽑히는 끝 값 — 가중치가 0 보다 크기만 하면 뽑힌다 */
	float RollPick(int32 PlayerId)
	{
		return CandidateIndexOf(PlayerId) == 0 ? 0.f : 0.999f;
	}

	/**
	 * 혼자 때린 사람이 '피해 가중 덕분에만' 뽑히는 값 — 가중치 300 : 100(피해 가중 2)이면 때린 사람, 100 : 100(피해 가중 0)이면 나머지.
	 * 때린 사람이 앞이면 구간이 [0, 0.75) → [0, 0.5), 뒤면 [0.25, 1) → [0.5, 1) 이다
	 */
	float RollBand(int32 HitterId)
	{
		return CandidateIndexOf(HitterId) == 0 ? 0.6f : 0.4f;
	}

	// ─── 서버에서 값을 바꾸는 것 ───

	UAbilitySystemComponent* ServerAscOf(int32 PlayerId)
	{
		return UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(ServerPawn(PlayerId));
	}

	/** 그 히어로가 적을 때린 것으로 — 실제 무기 판정이 쓰는 함수를 서버에서 부른다 */
	bool HeroHitsEnemy(const FContext& Ctx, int32 PlayerId, float Damage)
	{
		AAstralCharacter* Hero = ServerPawn(PlayerId);
		UAbilitySystemComponent* ASC = ServerAscOf(PlayerId);
		if (!Hero || !ASC || !Ctx.Enemy.IsValid())
		{
			return false;
		}
		const FHitResult Hit(Ctx.Enemy.Get(), nullptr, Ctx.Enemy->GetActorLocation(), FVector::UpVector);
		return UAstralCombatStatics::ApplyAttackHit(ASC, Hero, nullptr, Hit, Damage);
	}

	void RefillHealth(int32 PlayerId)
	{
		if (UAbilitySystemComponent* ASC = ServerAscOf(PlayerId))
		{
			ASC->SetNumericAttributeBase(UAstralHealthSet::GetHealthAttribute(), ASC->GetNumericAttribute(UAstralHealthSet::GetMaxHealthAttribute()));
		}
	}

	void SetHostility(int32 PlayerId, float Value)
	{
		if (UAbilitySystemComponent* ASC = ServerAscOf(PlayerId))
		{
			ASC->SetNumericAttributeBase(UAstralHeroResourceSet::GetHostilityAttribute(), Value);
		}
	}

	float HostilityOf(int32 PlayerId)
	{
		const UAbilitySystemComponent* ASC = ServerAscOf(PlayerId);
		return ASC ? ASC->GetNumericAttribute(UAstralHeroResourceSet::GetHostilityAttribute()) : -1.f;
	}

	/** 유지 시간을 끄고 고정 값으로 한 번 뽑는다 — 컨트롤러의 실제 경로(AcquireTarget)를 그대로 탄다 */
	AActor* DrawNow(const FContext& Ctx, float Roll)
	{
		AAstralEnemyController* Controller = EnemyController(Ctx);
		UAstralThreatComponent* ThreatComponent = Threat(Ctx);
		if (!Controller || !ThreatComponent)
		{
			return nullptr;
		}
		const float SavedHoldTime = ThreatComponent->HoldTime;
		ThreatComponent->HoldTime = 0.f;
		ThreatComponent->SetRollOverrideForTest(Roll);
		Controller->AcquireTarget();
		ThreatComponent->HoldTime = SavedHoldTime;
		return Controller->GetCurrentTarget();
	}

	// ─── 표본 ───

	/** 매 프레임 — 대기 조건이 부른다 */
	void Sample(FContext& Ctx)
	{
		if (!Ctx.Enemy.IsValid())
		{
			return;
		}
		const double Now = ServerTime();

		const bool bTelegraphing = EnemyHasTag(Ctx, TelegraphTagName);
		if (bTelegraphing != Ctx.bTelegraphing)
		{
			(bTelegraphing ? Ctx.TelegraphStartTimes : Ctx.TelegraphEndTimes).Add(Now);
			Ctx.bTelegraphing = bTelegraphing;
		}

		const bool bAttackActive = EnemyAttackActive(Ctx);
		if (bAttackActive != Ctx.bAttackActive)
		{
			if (!bAttackActive)
			{
				Ctx.AttackEndTimes.Add(Now);
			}
			Ctx.bAttackActive = bAttackActive;
		}
	}

	FString Describe(const FContext& Ctx)
	{
		const AAstralEnemyController* Controller = EnemyController(Ctx);
		const UAstralThreatComponent* ThreatComponent = Threat(Ctx);
		const AAstralCharacter* NearPawn = ServerPawn(Ctx.NearId);
		const AAstralCharacter* FarPawn = ServerPawn(Ctx.FarId);
		return FString::Printf(TEXT("t %.2f, near id %d hp %.0f at %s, far id %d hp %.0f at %s, enemy hp %.0f at %s speed %.0f, target %s, tree running %d, retarget pending %d, recent damage near %.1f far %.1f, excluded near %d far %d, telegraph starts %d ends %d"),
			ServerTime(),
			Ctx.NearId, HealthOf(NearPawn), NearPawn ? *NearPawn->GetActorLocation().ToCompactString() : TEXT("-"),
			Ctx.FarId, HealthOf(FarPawn), FarPawn ? *FarPawn->GetActorLocation().ToCompactString() : TEXT("-"),
			HealthOf(Ctx.Enemy.Get()), Ctx.Enemy.IsValid() ? *Ctx.Enemy->GetActorLocation().ToCompactString() : TEXT("-"),
			Ctx.Enemy.IsValid() ? Ctx.Enemy->GetVelocity().Size2D() : 0.0,
			*GetNameSafe(TargetOf(Ctx)),
			(Controller && Controller->GetStateTreeComponent()->IsRunning()) ? 1 : 0,
			(ThreatComponent && ThreatComponent->IsRetargetPending()) ? 1 : 0,
			ThreatComponent ? ThreatComponent->GetRecentDamage(NearPawn) : -1.f, ThreatComponent ? ThreatComponent->GetRecentDamage(FarPawn) : -1.f,
			(ThreatComponent && ThreatComponent->IsExcluded(NearPawn)) ? 1 : 0, (ThreatComponent && ThreatComponent->IsExcluded(FarPawn)) ? 1 : 0,
			Ctx.TelegraphStartTimes.Num(), Ctx.TelegraphEndTimes.Num());
	}

	/** 표본을 뜨며 조건을 기다린다 */
	void WaitSampling(const TSharedRef<FContext>& Ctx, const TCHAR* What, double TimeoutSeconds, TFunction<bool()> Condition)
	{
		WaitUntil(Ctx, What, TimeoutSeconds, [Ctx, Condition = MoveTemp(Condition)]()
		{
			Sample(*Ctx);
			return Condition();
		}, [Ctx]() { return Describe(*Ctx); });
	}

	/** 서버 시간으로 Seconds 동안 표본만 뜬다 */
	void Observe(const TSharedRef<FContext>& Ctx, double Seconds)
	{
		TSharedRef<double> StartTime = MakeShared<double>(-1.0);
		Step([Ctx, Seconds, StartTime]() -> bool
		{
			if (Ctx->bAborted)
			{
				return true;
			}
			if (*StartTime < 0.0)
			{
				*StartTime = ServerTime();
			}
			Sample(*Ctx);
			return ServerTime() - *StartTime >= Seconds;
		});
	}

	// ─── 단계 ───

	void EnqueueSetup(const TSharedRef<FContext>& Ctx)
	{
		RequestPie(Ctx, MapPath, Ctx->bDedicated ? PIE_Client : PIE_ListenServer, Ctx->NumPlayers);
		WaitUntil(Ctx, TEXT("every player has a living pawn on the server and on its own seat"), 240.0, [Ctx]()
		{
			const UWorld* ServerWorld = FindServerWorld();
			const AGameStateBase* GameState = ServerWorld ? ServerWorld->GetGameState() : nullptr;
			if (!ServerWorld || !ServerWorld->HasBegunPlay() || MapOf(ServerWorld) != MapName || !GameState || GameState->PlayerArray.Num() != Ctx->NumPlayers)
			{
				return false;
			}
			for (const APlayerState* PlayerState : GameState->PlayerArray)
			{
				if (!PlayerState || PlayerState->GetPlayerId() == 0 || HealthOf(PlayerState->GetPawn()) <= 0.f)
				{
					return false;
				}
			}
			const TArray<UWorld*> SeatWorlds = GetSeatWorlds();
			if (SeatWorlds.Num() != Ctx->NumPlayers)
			{
				return false;
			}
			for (const UWorld* SeatWorld : SeatWorlds)
			{
				const int32 MyId = LocalPlayerIdIn(SeatWorld);
				if (MyId == 0 || HealthOf(PawnIn(SeatWorld, MyId)) <= 0.f)
				{
					return false;
				}
			}
			return true;
		}, [Ctx]() { return Describe(*Ctx); });

		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			Test.TestEqual(TEXT("server net mode"), static_cast<int32>(ServerWorld->GetNetMode()), static_cast<int32>(Ctx->bDedicated ? NM_DedicatedServer : NM_ListenServer));

			// 가까운 쪽은 반드시 클라이언트 자리 — 실제 공격 입력(B0-1)이 넷 드라이버를 탄다
			TArray<int32> ClientIds;
			TArray<int32> AllIds;
			for (const UWorld* SeatWorld : GetSeatWorlds())
			{
				AllIds.Add(LocalPlayerIdIn(SeatWorld));
				if (SeatWorld->GetNetMode() == NM_Client)
				{
					ClientIds.Add(LocalPlayerIdIn(SeatWorld));
				}
			}
			ClientIds.Sort();
			if (!Test.TestTrue(TEXT("a client seat exists"), ClientIds.Num() > 0))
			{
				Ctx->bAborted = true;
				return;
			}
			Ctx->NearId = ClientIds[0];
			for (const int32 PlayerId : AllIds)
			{
				if (PlayerId != Ctx->NearId)
				{
					Ctx->FarId = PlayerId;
				}
			}

			AAstralCharacter* NearPawn = ServerPawn(Ctx->NearId);
			AAstralCharacter* FarPawn = ServerPawn(Ctx->FarId);
			if (!Test.TestNotNull(TEXT("near hero pawn"), NearPawn) || !Test.TestNotNull(TEXT("far hero pawn"), FarPawn))
			{
				Ctx->bAborted = true;
				return;
			}

			// 서버에서 자리를 잡는다. 둘 다 +X 를 본다 — 적은 가까운 쪽의 정면에 나온다
			NearPawn->TeleportTo(NearHeroLocation, FRotator::ZeroRotator);
			FarPawn->TeleportTo(FarHeroLocation, FRotator::ZeroRotator);
			Test.TestEqual(TEXT("no enemy before SpawnEnemy"), EnemiesIn(ServerWorld).Num(), 0);
			Test.TestEqual(TEXT("B5: Hostility starts at 100 (near)"), HostilityOf(Ctx->NearId), 100.f);
			Test.TestEqual(TEXT("B5: Hostility starts at 100 (far)"), HostilityOf(Ctx->FarId), 100.f);
		});
		Hold(Ctx, 1.0);

		// 서버에서 바로 부른다 — 스폰 · 빙의 · 트리 시작이 이 호출 안에서 끝난다
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			AAstralCharacter* NearPawn = ServerPawn(Ctx->NearId);
			if (!Test.TestNotNull(TEXT("near hero pawn on the server"), NearPawn))
			{
				Ctx->bAborted = true;
				return;
			}
			NearPawn->SpawnEnemy(FString(), EnemySpawnDistance);

			const TArray<AAstralCombatCharacter*> ServerEnemies = EnemiesIn(ServerWorld);
			if (!Test.TestEqual(TEXT("SpawnEnemy: one enemy on the server"), ServerEnemies.Num(), 1))
			{
				Ctx->bAborted = true;
				return;
			}
			Ctx->Enemy = ServerEnemies[0];
			Ctx->EnemySpawnLocation = Ctx->Enemy->GetActorLocation();

			UAstralThreatComponent* ThreatComponent = Threat(*Ctx);
			const UAbilitySystemComponent* EnemyASC = Ctx->Enemy->GetAbilitySystemComponent();
			const UAstralHealthSet* HealthSet = EnemyASC ? EnemyASC->GetSet<UAstralHealthSet>() : nullptr;
			if (!Test.TestNotNull(TEXT("the enemy's controller has a threat component"), ThreatComponent) || !Test.TestNotNull(TEXT("the enemy's health set"), HealthSet))
			{
				Ctx->bAborted = true;
				return;
			}

			// B0-1 — 컨트롤러가 구독하는 것과 같은 델리게이트를 시험도 구독해 Instigator 를 그대로 적는다
			HealthSet->OnDamaged.AddLambda([WeakCtx = TWeakPtr<FContext>(Ctx)](AActor* Instigator, AActor* /*Causer*/, const FGameplayEffectSpec* /*Spec*/, float Damage, float /*OldValue*/, float /*NewValue*/)
			{
				if (const TSharedPtr<FContext> Pinned = WeakCtx.Pin())
				{
					FDamageSeen& Seen = Pinned->DamageSeen.AddDefaulted_GetRef();
					Seen.Instigator = Instigator;
					Seen.InstigatorClass = Instigator ? Instigator->GetClass()->GetName() : FString(TEXT("null"));
					Seen.Damage = Damage;
				}
			});

			Note(Test, FString::Printf(TEXT("setup: %s, near id %d (candidate %d), far id %d (candidate %d), enemy at %s, threat values: weight %.1f window %.0f hold %.0f cooldown %.0f exclude %.0f"),
				Ctx->bDedicated ? TEXT("dedicated") : TEXT("listen"), Ctx->NearId, CandidateIndexOf(Ctx->NearId), Ctx->FarId, CandidateIndexOf(Ctx->FarId),
				*Ctx->EnemySpawnLocation.ToCompactString(),
				ThreatComponent->DamageWeight, ThreatComponent->DamageWindow, ThreatComponent->HoldTime, ThreatComponent->RetargetCooldown, ThreatComponent->ExcludeTime));
		});
	}

	void EnqueueChaseRetarget(const TSharedRef<FContext>& Ctx)
	{
		// B2(월드) — 기록이 없으면 가장 가까운 플레이어. 추격이 시작된 뒤(40 cm 이동)까지 기다려 이벤트가 Chase 에서 받아지게 한다
		WaitSampling(Ctx, TEXT("B2: with no damage recorded the enemy targets the nearest player and starts chasing it"), 15.0, [Ctx]()
		{
			return Ctx->Enemy.IsValid() && TargetOf(*Ctx) == ServerPawn(Ctx->NearId)
				&& FVector::Dist2D(Ctx->Enemy->GetActorLocation(), Ctx->EnemySpawnLocation) >= 40.0;
		});

		// B3 — 추격 중에 먼 쪽이 때린다. 추첨 값은 '피해 가중 덕분에만 때린 사람이 뽑히는' 값이다
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UAstralThreatComponent* ThreatComponent = Threat(*Ctx);
			const AAstralCharacter* NearPawn = ServerPawn(Ctx->NearId);
			const AAstralCharacter* FarPawn = ServerPawn(Ctx->FarId);

			Test.TestTrue(TEXT("B3 precondition: the enemy is still chasing (not yet in reach of the near hero)"), EnemyDistanceTo(*Ctx, NearPawn) > 300.0);
			Test.TestEqual(TEXT("B3 precondition: no telegraph yet"), Ctx->TelegraphStartTimes.Num(), 0);
			Test.TestEqual(TEXT("B2: nothing recorded before the first hit (near)"), ThreatComponent->GetRecentDamage(NearPawn), 0.f);
			Test.TestEqual(TEXT("B2: nothing recorded before the first hit (far)"), ThreatComponent->GetRecentDamage(FarPawn), 0.f);

			ThreatComponent->SetRollOverrideForTest(RollBand(Ctx->FarId));
			Test.TestTrue(TEXT("B3: the far hero's hit is applied"), HeroHitsEnemy(*Ctx, Ctx->FarId, ProbeDamage));
			Test.TestTrue(TEXT("B3: the hit is recorded for the far hero"), ThreatComponent->GetRecentDamage(FarPawn) > 0.f);
			Test.TestTrue(TEXT("B3: a hit from someone other than the target requests a retarget"), ThreatComponent->IsRetargetPending());

			Ctx->MarkTime = ServerTime();
			Ctx->RequestTime = Ctx->MarkTime;
			Note(Test, FString::Printf(TEXT("B3: far hero hit the chasing enemy for %.2f (recorded %.2f) when it was %.0f from the near hero"),
				ProbeDamage, ThreatComponent->GetRecentDamage(FarPawn), EnemyDistanceTo(*Ctx, NearPawn)));
		});
		WaitSampling(Ctx, TEXT("B3: hit mid-chase by the other player, the enemy retargets to it"), 5.0, [Ctx]()
		{
			return TargetOf(*Ctx) == ServerPawn(Ctx->FarId);
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UAstralThreatComponent* ThreatComponent = Threat(*Ctx);
			const double Seconds = ServerTime() - Ctx->MarkTime;
			Note(Test, FString::Printf(TEXT("B3: retargeted to the far hero %.3f s after its hit, enemy %.0f from the near hero, telegraphs so far %d"),
				Seconds, EnemyDistanceTo(*Ctx, ServerPawn(Ctx->NearId)), Ctx->TelegraphStartTimes.Num()));
			Test.TestTrue(TEXT("B3: the retarget happens right away (Chase takes the Retarget event)"), Seconds <= 0.5);
			Test.TestEqual(TEXT("B3: it happened mid-chase, before any attack"), Ctx->TelegraphStartTimes.Num(), 0);
			Test.TestFalse(TEXT("B3: the request is consumed by the draw"), ThreatComponent->IsRetargetPending());

			// B4 — 유지 시간 안의 판단 지점이 다시 뽑는다면 가까운 쪽이 나오게 해 둔다
			Ctx->HoldStartTime = ServerTime();
			ThreatComponent->SetRollOverrideForTest(RollPick(Ctx->NearId));
		});
	}

	void EnqueueHold(const TSharedRef<FContext>& Ctx)
	{
		// B4 — 유지 시간 안에는 공격 사이클이 끝나 Acquire 가 와도 그대로, 지나면 다시 뽑는다(고정 값 → 가까운 쪽)
		WaitSampling(Ctx, TEXT("B4: once the hold time is over the enemy draws again"), 20.0, [Ctx]()
		{
			if (TargetOf(*Ctx) != ServerPawn(Ctx->FarId))
			{
				Ctx->SwitchTime = ServerTime();
				return true;
			}
			return false;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const UAstralThreatComponent* ThreatComponent = Threat(*Ctx);
			const double HoldTime = ThreatComponent->HoldTime;
			const double Held = Ctx->SwitchTime - Ctx->HoldStartTime;

			// 유지 시간 안에 판단 지점(공격 종료 + 회복)이 적어도 한 번 있었는가 — 없었다면 '안 바뀜' 은 아무것도 말하지 않는다
			int32 NumDecisionsInsideHold = 0;
			for (const double AttackEnd : Ctx->AttackEndTimes)
			{
				if (AttackEnd >= Ctx->HoldStartTime && AttackEnd + RecoverySeconds + 0.15 < Ctx->HoldStartTime + HoldTime)
				{
					++NumDecisionsInsideHold;
				}
			}

			Note(Test, FString::Printf(TEXT("B4: target held %.2f s (HoldTime %.1f s), decision points inside the hold %d, then drew %s; far hero hp %.0f"),
				Held, HoldTime, NumDecisionsInsideHold, *GetNameSafe(TargetOf(*Ctx)), HealthOf(ServerPawn(Ctx->FarId))));
			Test.TestTrue(TEXT("B4: at least one decision point fell inside the hold time"), NumDecisionsInsideHold >= 1);
			Test.TestTrue(TEXT("B4: the target does not change inside the hold time"), Held >= HoldTime - 0.2);
			Test.TestTrue(TEXT("B4: the first decision point after the hold time draws again"), Held <= HoldTime + TelegraphSeconds + RecoverySeconds + 0.5);
			Test.TestTrue(TEXT("B4: the fixed roll drew the near hero"), TargetOf(*Ctx) == ServerPawn(Ctx->NearId));

			Ctx->MarkTelegraphStarts = Ctx->TelegraphStartTimes.Num();
			RefillHealth(Ctx->NearId);
			RefillHealth(Ctx->FarId);
		});
	}

	void EnqueueAttackRetarget(const TSharedRef<FContext>& Ctx)
	{
		// B3 — 공격 중에 다른 사람이 때리면 그 공격은 끝까지 가고, 회복 뒤의 Acquire 가 유지 시간을 무시하고 다시 뽑는다
		WaitSampling(Ctx, TEXT("B3: the enemy reaches the near hero and starts a telegraph"), 20.0, [Ctx]()
		{
			return Ctx->TelegraphStartTimes.Num() > Ctx->MarkTelegraphStarts && Ctx->bTelegraphing && TargetOf(*Ctx) == ServerPawn(Ctx->NearId);
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UAstralThreatComponent* ThreatComponent = Threat(*Ctx);

			Ctx->NearHealthBefore = HealthOf(ServerPawn(Ctx->NearId));
			Ctx->MarkTelegraphEnds = Ctx->TelegraphEndTimes.Num();
			ThreatComponent->SetRollOverrideForTest(RollPick(Ctx->FarId));
			Test.TestTrue(TEXT("B3: the far hero's hit during the attack is applied"), HeroHitsEnemy(*Ctx, Ctx->FarId, ProbeDamage));
			Test.TestTrue(TEXT("B3: the hit during the attack requests a retarget"), ThreatComponent->IsRetargetPending());
			Ctx->RequestTime = ServerTime();
		});
		WaitSampling(Ctx, TEXT("B3: the attack in progress runs to its sweep"), 6.0, [Ctx]()
		{
			return Ctx->TelegraphEndTimes.Num() > Ctx->MarkTelegraphEnds;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const AAstralCharacter* NearPawn = ServerPawn(Ctx->NearId);
			Test.TestTrue(TEXT("B3: the target is unchanged while the attack runs"), TargetOf(*Ctx) == NearPawn);
			Test.TestTrue(TEXT("B3: the request stays pending during the attack"), Threat(*Ctx)->IsRetargetPending());
			Test.TestTrue(TEXT("B3: the attack in progress still lands on the original target"), FMath::IsNearlyEqual(Ctx->NearHealthBefore - HealthOf(NearPawn), AttackDamage, 0.01f));
			Ctx->MarkTime = Ctx->TelegraphEndTimes.Last();
		});
		WaitSampling(Ctx, TEXT("B3: after that attack's recovery the enemy draws again (-> far)"), 6.0, [Ctx]()
		{
			return TargetOf(*Ctx) == ServerPawn(Ctx->FarId);
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const UAstralThreatComponent* ThreatComponent = Threat(*Ctx);
			const double AfterSweep = ServerTime() - Ctx->MarkTime;
			const double SinceAcquired = ServerTime() - Ctx->SwitchTime;
			Note(Test, FString::Printf(TEXT("B3: hit during the attack — retargeted %.2f s after the sweep (Recovery %.1f s), %.2f s after the previous target was drawn (HoldTime %.1f s)"),
				AfterSweep, RecoverySeconds, SinceAcquired, ThreatComponent->HoldTime));
			Test.TestTrue(TEXT("B3: the retarget waits for the attack and its recovery"), FMath::Abs(AfterSweep - RecoverySeconds) <= TimingSlack);
			Test.TestTrue(TEXT("B3: the draw ignored the hold time (it had not run out)"), SinceAcquired < ThreatComponent->HoldTime - 0.2);
			Test.TestFalse(TEXT("B3: the request is consumed by the draw"), ThreatComponent->IsRetargetPending());
		});
	}

	void EnqueueDraws(const TSharedRef<FContext>& Ctx)
	{
		// B5 · 대조 — 한 프레임 안에서 컨트롤러의 AcquireTarget 을 고정 값으로 여러 번 부른다. 끝은 트리가 쫓는 쪽(먼 쪽)으로 맞춰 둔다
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UAstralThreatComponent* ThreatComponent = Threat(*Ctx);
			AAstralCharacter* NearPawn = ServerPawn(Ctx->NearId);
			AAstralCharacter* FarPawn = ServerPawn(Ctx->FarId);

			const float RecentNear = ThreatComponent->GetRecentDamage(NearPawn);
			const float RecentFar = ThreatComponent->GetRecentDamage(FarPawn);
			Test.TestEqual(TEXT("draws precondition: the near hero has not hit the enemy"), RecentNear, 0.f);
			Test.TestTrue(TEXT("draws precondition: the far hero is the only hitter"), RecentFar > 0.f);

			// 대조(다시 빌드하지 않는 1건) — 같은 추첨 값에서 피해 가중이 있으면 때린 사람, 0 이면 나머지
			const float Band = RollBand(Ctx->FarId);
			const float SavedDamageWeight = ThreatComponent->DamageWeight;
			const AActor* WithWeight = DrawNow(*Ctx, Band);
			ThreatComponent->DamageWeight = 0.f;
			const AActor* WithoutWeight = DrawNow(*Ctx, Band);
			ThreatComponent->DamageWeight = SavedDamageWeight;
			Test.TestTrue(TEXT("B3: with the damage weight the hitter is drawn"), WithWeight == FarPawn);
			Test.TestTrue(TEXT("control: with DamageWeight 0 the same roll does not draw the hitter"), WithoutWeight == NearPawn);

			// B5 — 적대심. 0.5 는 적대심이 같을 때 때린 사람 구간이고, 가까운 쪽을 900 으로 올리면 그쪽 구간이 된다
			const AActor* EqualHostility = DrawNow(*Ctx, 0.5f);
			SetHostility(Ctx->NearId, 900.f);
			const float Raised = HostilityOf(Ctx->NearId);
			const AActor* RaisedHostility = DrawNow(*Ctx, 0.5f);
			Test.TestTrue(TEXT("B5: equal Hostility, roll 0.5 -> the hitter"), EqualHostility == FarPawn);
			Test.TestEqual(TEXT("B5: the server sets Hostility"), Raised, 900.f);
			Test.TestTrue(TEXT("B5: raised Hostility, same roll -> the hero with more Hostility"), RaisedHostility == NearPawn);

			// 0 미만은 0 으로 잘리고, 0 이면 어떤 값으로도 안 뽑힌다
			SetHostility(Ctx->NearId, -50.f);
			const float Clamped = HostilityOf(Ctx->NearId);
			const AActor* ZeroForced = DrawNow(*Ctx, RollPick(Ctx->NearId));
			const AActor* ZeroMiddle = DrawNow(*Ctx, 0.5f);
			Test.TestEqual(TEXT("B5: Hostility below 0 is clamped to 0"), Clamped, 0.f);
			Test.TestTrue(TEXT("B5: Hostility 0 is never drawn (roll forced toward it)"), ZeroForced == FarPawn);
			Test.TestTrue(TEXT("B5: Hostility 0 is never drawn (roll 0.5)"), ZeroMiddle == FarPawn);
			SetHostility(Ctx->NearId, 100.f);

			// 트리는 먼 쪽을 쫓는 중이다 — 값도 그쪽으로 돌려 둔다
			const AActor* Final = DrawNow(*Ctx, RollPick(Ctx->FarId));
			Test.TestTrue(TEXT("draws: left on the far hero (what the tree is chasing)"), Final == FarPawn);

			Note(Test, FString::Printf(TEXT("draws: recent damage near %.2f far %.2f, band roll %.2f -> weight 2: %s, weight 0: %s; roll 0.5 -> Hostility 100/100: %s, 900/100: %s; Hostility -50 reads %.0f -> forced %s, 0.5 %s"),
				RecentNear, RecentFar, Band, *GetNameSafe(WithWeight), *GetNameSafe(WithoutWeight),
				*GetNameSafe(EqualHostility), *GetNameSafe(RaisedHostility), Clamped, *GetNameSafe(ZeroForced), *GetNameSafe(ZeroMiddle)));

			// 재추첨 간격 — 방금(공격 중) 받은 요청에서 RetargetCooldown 이 안 지났다. 가까운 쪽이 때려도 기록만 되고 요청은 서지 않는다
			const double SinceRequest = ServerTime() - Ctx->RequestTime;
			Test.TestTrue(TEXT("cooldown precondition: still inside RetargetCooldown"), SinceRequest < ThreatComponent->RetargetCooldown - 0.2);
			Test.TestTrue(TEXT("cooldown: the near hero's hit is applied"), HeroHitsEnemy(*Ctx, Ctx->NearId, ProbeDamage));
			Test.TestTrue(TEXT("cooldown: the hit is still recorded"), ThreatComponent->GetRecentDamage(NearPawn) > 0.f);
			Test.TestFalse(TEXT("cooldown: a second request inside RetargetCooldown is not taken"), ThreatComponent->IsRetargetPending());
			Note(Test, FString::Printf(TEXT("cooldown: near hero hit %.2f s after the last accepted request (RetargetCooldown %.1f s) — pending %d"),
				SinceRequest, ThreatComponent->RetargetCooldown, ThreatComponent->IsRetargetPending() ? 1 : 0));

			Ctx->MarkTelegraphStarts = Ctx->TelegraphStartTimes.Num();
		});
	}

	void EnqueueUnreachable(const TSharedRef<FContext>& Ctx)
	{
		// B6 — 적이 먼 쪽 옆에 서서 예고하는 동안 그 히어로를 공중에 띄운다. 다음 Chase 의 MoveTo 가 들어오자마자 실패해야 한다
		WaitSampling(Ctx, TEXT("B6: the enemy reaches the far hero and starts a telegraph"), 20.0, [Ctx]()
		{
			return Ctx->TelegraphStartTimes.Num() > Ctx->MarkTelegraphStarts && Ctx->bTelegraphing && TargetOf(*Ctx) == ServerPawn(Ctx->FarId);
		});
		Do(Ctx, [Ctx]()
		{
			AAstralCharacter* FarPawn = ServerPawn(Ctx->FarId);
			RefillHealth(Ctx->NearId);
			RefillHealth(Ctx->FarId);

			// 이동을 끄는 것은 텔레포트 뒤다 — 텔레포트는 바닥이 없으면 이동 모드를 낙하로 바꾼다(UCharacterMovementComponent::OnTeleported)
			FarPawn->TeleportTo(FarHeroLocation + FVector(0.0, 0.0, UnreachableHeight), FRotator::ZeroRotator, /*bIsATest=*/false, /*bNoCheck=*/true);
			FarPawn->GetCharacterMovement()->StopMovementImmediately();
			FarPawn->GetCharacterMovement()->DisableMovement();

			// 고정 값은 띄운 쪽을 가리킨다 — 그래도 제외 중에는 뽑히지 않아야 한다
			Threat(*Ctx)->SetRollOverrideForTest(RollPick(Ctx->FarId));
			Ctx->MarkTime = ServerTime();
		});
		WaitSampling(Ctx, TEXT("B6: chasing the unreachable target fails, it is excluded and the enemy targets the other player"), 12.0, [Ctx]()
		{
			const UAstralThreatComponent* ThreatComponent = Threat(*Ctx);
			return ThreatComponent && ThreatComponent->IsExcluded(ServerPawn(Ctx->FarId)) && TargetOf(*Ctx) == ServerPawn(Ctx->NearId);
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			AAstralCharacter* NearPawn = ServerPawn(Ctx->NearId);
			AAstralCharacter* FarPawn = ServerPawn(Ctx->FarId);
			Ctx->ExcludedTime = ServerTime();

			Test.TestTrue(TEXT("B6 precondition: the far hero stayed in the air"), FarPawn->GetActorLocation().Z >= FarHeroLocation.Z + UnreachableHeight - 200.0);
			Note(Test, FString::Printf(TEXT("B6: far hero lifted to z %.0f — excluded and retargeted to the near hero %.2f s later"), FarPawn->GetActorLocation().Z, Ctx->ExcludedTime - Ctx->MarkTime));

			// 제외 중에는 그쪽을 가리키는 값으로 뽑아도 안 나온다
			const AActor* WhileExcluded = DrawNow(*Ctx, RollPick(Ctx->FarId));
			Test.TestTrue(TEXT("B6: an excluded target is not drawn even with the roll forced toward it"), WhileExcluded == NearPawn);

			// 내려놓는다 — 제외가 풀린 뒤에는 닿을 수 있는 후보다
			FarPawn->TeleportTo(FarHeroLocation, FRotator::ZeroRotator, /*bIsATest=*/false, /*bNoCheck=*/true);
			FarPawn->GetCharacterMovement()->SetMovementMode(MOVE_Falling);
		});

		// 제외 시간이 지날 때까지 — 그동안 타깃은 유지 시간 안이라 그대로다
		Step([Ctx]() -> bool
		{
			if (Ctx->bAborted)
			{
				return true;
			}
			Sample(*Ctx);
			const UAstralThreatComponent* ThreatComponent = Threat(*Ctx);
			return !ThreatComponent || ServerTime() >= Ctx->ExcludedTime + ThreatComponent->ExcludeTime + 0.3;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const UAstralThreatComponent* ThreatComponent = Threat(*Ctx);
			AAstralCharacter* NearPawn = ServerPawn(Ctx->NearId);
			AAstralCharacter* FarPawn = ServerPawn(Ctx->FarId);
			if (!Test.TestNotNull(TEXT("B6: threat component after the exclusion time"), ThreatComponent))
			{
				Ctx->bAborted = true;
				return;
			}

			Test.TestFalse(TEXT("B6: the exclusion runs out after ExcludeTime"), ThreatComponent->IsExcluded(FarPawn));
			const AActor* AfterExclusion = DrawNow(*Ctx, RollPick(Ctx->FarId));
			Test.TestTrue(TEXT("B6: once the exclusion is over the target is a candidate again"), AfterExclusion == FarPawn);
			Note(Test, FString::Printf(TEXT("B6: %.2f s after the exclusion (ExcludeTime %.1f s) the forced roll draws %s"),
				ServerTime() - Ctx->ExcludedTime, ThreatComponent->ExcludeTime, *GetNameSafe(AfterExclusion)));

			// 트리는 가까운 쪽 옆에 있다 — 값도 그쪽으로 돌려 둔다 (B0-1 의 실제 공격이 서 있는 적을 친다)
			const AActor* Final = DrawNow(*Ctx, RollPick(Ctx->NearId));
			Test.TestTrue(TEXT("B6: left on the near hero (what the tree is attacking)"), Final == NearPawn);
			RefillHealth(Ctx->NearId);
			RefillHealth(Ctx->FarId);
		});
	}

	void EnqueueHeroAttack(const TSharedRef<FContext>& Ctx)
	{
		// B0-1 — 클라이언트 히어로의 실제 공격 입력. 적은 가까운 쪽을 타깃으로 그 옆에 서 있다
		WaitSampling(Ctx, TEXT("B0-1: the enemy stands next to the near hero"), 15.0, [Ctx]()
		{
			const double Distance = EnemyDistanceTo(*Ctx, ServerPawn(Ctx->NearId));
			return Ctx->Enemy.IsValid() && Ctx->Enemy->GetVelocity().Size2D() < 1.0 && Distance >= 0.0 && Distance <= 330.0;
		});
		Do(Ctx, [Ctx]()
		{
			AAstralCharacter* NearPawn = ServerPawn(Ctx->NearId);
			if (!NearPawn || !Ctx->Enemy.IsValid())
			{
				return;
			}
			// 적 바로 앞으로 붙인다 — 근접 무기가 닿는 거리. 서버의 몸 방향은 적을 향한다
			const FVector EnemyLocation = Ctx->Enemy->GetActorLocation();
			const FVector ToHero = (NearPawn->GetActorLocation() - EnemyLocation).GetSafeNormal2D();
			const FVector Location = EnemyLocation + ToHero * 110.0;
			NearPawn->TeleportTo(FVector(Location.X, Location.Y, NearPawn->GetActorLocation().Z), (-ToHero).Rotation());
			Ctx->EnemyHealthBefore = HealthOf(Ctx->Enemy.Get());
			Ctx->MarkDamageSeen = Ctx->DamageSeen.Num();
		});
		Observe(Ctx, 0.7);
		Do(Ctx, [Ctx]()
		{
			UWorld* SeatWorld = FindSeatWorld(Ctx->NearId);
			AAstralPlayerController* PC = Cast<AAstralPlayerController>(GetLocalPC(SeatWorld));
			UAstralAbilitySystemComponent* ASC = PC ? PC->GetAstralAbilitySystemComponent() : nullptr;
			APawn* ClientPawn = PC ? PC->GetPawn() : nullptr;
			if (!Ctx->Test->TestTrue(TEXT("B0-1: client controller, pawn and ASC"), ASC && ClientPawn && Ctx->Enemy.IsValid()))
			{
				Ctx->bAborted = true;
				return;
			}
			Ctx->Test->TestFalse(TEXT("B0-1: the attack input is given on a client (no authority)"), ClientPawn->HasAuthority());

			// 클라이언트 쪽 몸 · 시점도 적을 향하게 — 공격 방향 제안은 클라이언트가 만든다
			const FRotator Facing = (Ctx->Enemy->GetActorLocation() - ClientPawn->GetActorLocation()).GetSafeNormal2D().Rotation();
			ClientPawn->SetActorRotation(Facing);
			PC->SetControlRotation(Facing);
			ASC->AbilityInputTagPressed(FGameplayTag::RequestGameplayTag(BasicAttackInputTagName));
		});
		Observe(Ctx, 0.1);
		Do(Ctx, [Ctx]()
		{
			if (const AAstralPlayerController* PC = Cast<AAstralPlayerController>(GetLocalPC(FindSeatWorld(Ctx->NearId))))
			{
				if (UAstralAbilitySystemComponent* ASC = PC->GetAstralAbilitySystemComponent())
				{
					ASC->AbilityInputTagReleased(FGameplayTag::RequestGameplayTag(BasicAttackInputTagName));
				}
			}
		});
		WaitSampling(Ctx, TEXT("B0-1: the client hero's attack input damages the enemy on the server"), 8.0, [Ctx]()
		{
			return Ctx->DamageSeen.Num() > Ctx->MarkDamageSeen;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const UAstralThreatComponent* ThreatComponent = Threat(*Ctx);
			const AAstralCharacter* NearPawn = ServerPawn(Ctx->NearId);
			const FDamageSeen& Seen = Ctx->DamageSeen[Ctx->MarkDamageSeen];
			const AActor* Instigator = Seen.Instigator.Get();

			Note(Test, FString::Printf(TEXT("B0-1: %s — OnDamaged Instigator = %s (class %s, pawn %d, player state %d, controller %d), damage %.1f, enemy hp %.1f -> %.1f, recorded for the near hero %.1f"),
				Ctx->bDedicated ? TEXT("dedicated") : TEXT("listen"), *GetNameSafe(Instigator), *Seen.InstigatorClass,
				Cast<APawn>(Instigator) ? 1 : 0, Cast<APlayerState>(Instigator) ? 1 : 0, Cast<AController>(Instigator) ? 1 : 0,
				Seen.Damage, Ctx->EnemyHealthBefore, HealthOf(Ctx->Enemy.Get()), ThreatComponent->GetRecentDamage(NearPawn)));
			Test.TestTrue(TEXT("B0-1: the Instigator of a hero's hit is the hero's pawn"), Instigator == NearPawn);
			Test.TestTrue(TEXT("B0-1: the controller recorded the client hero's hit"), ThreatComponent->GetRecentDamage(NearPawn) >= Seen.Damage - 0.01f);
			Test.TestFalse(TEXT("B3: a hit from the current target does not request a retarget"), ThreatComponent->IsRetargetPending());
		});

		// 공격 몽타주가 끝날 때까지 둔다 — 도중에 PIE 를 내리면 몽타주의 종료 노티파이가 풀린 ASC 로 이벤트를 보내 오류 로그가 남는다
		Observe(Ctx, 5.0);
	}

	void EnqueueEnemyDeath(const TSharedRef<FContext>& Ctx)
	{
		// 사망 — 구독을 풀고 기록을 비운다. 자기 자신이 준 피해(DamageSelf)는 위협이 아니다
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const AAstralEnemyController* Controller = EnemyController(*Ctx);
			const UAstralThreatComponent* ThreatComponent = Threat(*Ctx);
			const AAstralCharacter* NearPawn = ServerPawn(Ctx->NearId);
			const AAstralCharacter* FarPawn = ServerPawn(Ctx->FarId);
			if (!Test.TestTrue(TEXT("death: enemy alive before the kill"), Ctx->Enemy.IsValid() && !IsDead(Ctx->Enemy.Get()) && Controller && ThreatComponent))
			{
				Ctx->bAborted = true;
				return;
			}
			Test.TestTrue(TEXT("death precondition: something is recorded before the kill"), ThreatComponent->GetRecentDamage(NearPawn) > 0.f);

			Ctx->MarkDamageSeen = Ctx->DamageSeen.Num();
			Ctx->Enemy->DamageSelf(100000.f);

			Test.TestTrue(TEXT("death: enemy is dying"), IsDead(Ctx->Enemy.Get()));
			Test.TestTrue(TEXT("death: the killing damage came from the enemy itself"), Ctx->DamageSeen.Num() > Ctx->MarkDamageSeen && Ctx->DamageSeen.Last().Instigator.Get() == Ctx->Enemy.Get());
			Test.TestEqual(TEXT("death: the threat record is cleared (near)"), ThreatComponent->GetRecentDamage(NearPawn), 0.f);
			Test.TestEqual(TEXT("death: the threat record is cleared (far)"), ThreatComponent->GetRecentDamage(FarPawn), 0.f);
			Test.TestFalse(TEXT("death: no retarget request left"), ThreatComponent->IsRetargetPending());
			Test.TestNull(TEXT("death: a dead enemy holds no target"), Controller->GetCurrentTarget());
			Note(Test, FString::Printf(TEXT("death: OnDamaged events seen in this run %d"), Ctx->DamageSeen.Num()));
		});
	}

	void EnqueueAggro(FAutomationTestBase& Test, bool bDedicated)
	{
		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;
		Ctx->bDedicated = bDedicated;

		// PIE 시작 때 엔진이 내는 경고 — NavMesh 등록 전에 군중 매니저가 만들어진다. 이 시험과 무관하다
		Test.AddExpectedMessage(TEXT("Unable to find RecastNavMesh instance while trying to create UCrowdManager instance"), ELogVerbosity::Warning, EAutomationExpectedMessageFlags::Contains, -1, /*IsRegex=*/false);

		EnqueueSetup(Ctx);
		EnqueueChaseRetarget(Ctx);
		EnqueueHold(Ctx);
		EnqueueAttackRetarget(Ctx);
		EnqueueDraws(Ctx);
		EnqueueUnreachable(Ctx);
		EnqueueHeroAttack(Ctx);
		EnqueueEnemyDeath(Ctx);
		EndPie(Ctx);
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemyAggroListenPieTest, "AstralBreak.Net.EnemyAggro.ListenPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralEnemyAggroListenPieTest::RunTest(const FString& Parameters)
{
	AstralEnemyAggroPie::EnqueueAggro(*this, /*bDedicated=*/false);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemyAggroDedicatedPieTest, "AstralBreak.Net.EnemyAggro.DedicatedPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralEnemyAggroDedicatedPieTest::RunTest(const FString& Parameters)
{
	AstralEnemyAggroPie::EnqueueAggro(*this, /*bDedicated=*/true);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
