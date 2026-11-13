// 단위 A 전투 네트워크 시험 — 한 프로세스 멀티 PIE (설계 Docs/Design/m3-enemy-ai.md §8 검증 계획 A4 ~ A8)
//
// 리슨 서버 · Dedicated 를 PIE 로 띄워 CombatTestMap 에서 적 한 마리(BP_Enemy_Melee)를 클라이언트의 디버그 명령(SpawnEnemy → 서버 RPC)으로 부르고,
// 서버 월드의 적 · 컨트롤러와 각 클라이언트 월드의 복제 상태를 직접 본다.
//
//   A4  가장 가까운 플레이어를 쫓아와 예고 뒤 때린다 — 서버 HP 가 줄고 같은 값이 클라이언트에 온다
//   A7  패링(방어 태그를 서버에서 직접 세운다)하면 피해 0 · 적은 경직 동안 다음 공격을 하지 않는다
//   A8  클라이언트 히어로의 실제 공격 입력으로 적이 피해를 받는다 (시도 — 안 되면 오류로 남기고 뒤 단계는 계속한다)
//   A5  타깃이 죽으면 다른 플레이어로 넘어간다 · 전원이 죽으면 공격하지 않는다
//   A6  적 HP 0 → 서버 · 클라이언트에서 폰이 사라진다
//
// 시간은 서버 월드 시간으로 잰다. 공격 주기는 매 프레임 표본으로 본다(예고 태그 · 공격 어빌리티 활성 여부의 오르내림).
// 별도 프로세스 구성은 AstralPartyFlowTestController 의 EnemyCombat 시나리오 + Tools/net_test/run_party_flow.py 가 맡는다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AstralPieTestHelpers.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Character/Enemy/AstralCombatCharacter.h"
#include "Character/Enemy/AstralEnemyController.h"
#include "Components/StateTreeAIComponent.h"
#include "Engine/GameInstance.h"
#include "EngineUtils.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerState.h"
#include "GameplayAbilitySpec.h"
#include "GameplayTagContainer.h"
#include "Player/AstralPlayerController.h"

namespace AstralEnemyCombatPie
{
	using namespace AstralPieTest;

	const TCHAR* const MapPath = TEXT("/Game/Maps/CombatTestMap");
	const TCHAR* const MapName = TEXT("CombatTestMap");
	const TCHAR* const EnemyClassPrefix = TEXT("BP_Enemy_Melee");

	// 태그는 런타임 모듈이 내보내지 않는다 — 이름으로 찾는다
	const TCHAR* const TelegraphTagName = TEXT("State.Telegraphing");
	const TCHAR* const ParryTagName = TEXT("State.Defense.Parrying");
	const TCHAR* const MeleeAbilityTagName = TEXT("Ability.Enemy.Attack.Melee");
	const TCHAR* const BasicAttackInputTagName = TEXT("InputTag.Attack.Basic");

	// GA_Enemy_MeleeAttack · ST_Enemy_Melee 의 값(잠정) — 바꾸면 여기도 바꾼다
	constexpr float AttackDamage = 15.f;
	constexpr double TelegraphSeconds = 1.0;
	constexpr double StaggerSeconds = 2.0;
	constexpr double RecoverySeconds = 1.0;

	/** 표본이 프레임 단위라 생기는 오차 + 상태 전환 프레임 */
	constexpr double TimingSlack = 0.35;

	// CombatTestMap 좌표 — 맵의 더미(x < 0)와 떨어진 NavMesh 위
	const FVector NearHeroLocation(1100.0, -400.0, 92.0);
	const FVector FarHeroLocation(1100.0, 900.0, 92.0);
	constexpr float EnemySpawnDistance = 600.f;

	struct FContext : FContextBase
	{
		bool bDedicated = false;
		int32 NumPlayers = 2;

		/** 가까운 쪽 = 클라이언트 자리의 플레이어(적을 부르고 실제 공격 입력을 넣는다), 먼 쪽 = 나머지 */
		int32 NearId = 0;
		int32 FarId = 0;

		TWeakObjectPtr<AAstralCombatCharacter> Enemy;

		// 매 프레임 표본 — 예고 태그와 공격 어빌리티의 오르내림
		bool bTelegraphing = false;
		bool bAttackActive = false;
		TArray<double> TelegraphStartTimes;
		TArray<double> TelegraphEndTimes;
		TArray<double> AttackEndTimes;

		// 단계 사이에 넘기는 값
		float NearHealthBefore = 0.f;
		float FarHealthBefore = 0.f;
		float EnemyHealthBefore = 0.f;
		int32 MarkTelegraphStarts = 0;
		double MarkTime = 0.0;
		FVector MarkLocation = FVector::ZeroVector;
		bool bHeroAttackLanded = false;
		bool bSawAttackWhileEveryoneDead = false;
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

	/** 이 월드가 보는 그 플레이어의 폰 (클라이언트 월드에서는 복제된 폰) */
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

	int32 NumEnemyControllersIn(UWorld* World)
	{
		int32 Count = 0;
		if (World)
		{
			for (TActorIterator<AAstralEnemyController> It(World); It; ++It)
			{
				++Count;
			}
		}
		return Count;
	}

	AAstralEnemyController* EnemyController(const FContext& Ctx)
	{
		return Ctx.Enemy.IsValid() ? Cast<AAstralEnemyController>(Ctx.Enemy->GetController()) : nullptr;
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
		const UWorld* ServerWorld = FindServerWorld();
		const AAstralEnemyController* Controller = EnemyController(Ctx);
		return FString::Printf(TEXT("server map '%s', seats %d, near hp %.0f, far hp %.0f, enemy %s hp %.0f at %s, target %s, tree running %d, telegraph starts %d ends %d, attack ends %d"),
			*MapOf(ServerWorld), GetSeatWorlds().Num(),
			HealthOf(PawnIn(ServerWorld, Ctx.NearId)), HealthOf(PawnIn(ServerWorld, Ctx.FarId)),
			Ctx.Enemy.IsValid() ? *Ctx.Enemy->GetName() : TEXT("none"), HealthOf(Ctx.Enemy.Get()),
			Ctx.Enemy.IsValid() ? *Ctx.Enemy->GetActorLocation().ToCompactString() : TEXT("-"),
			Controller ? *GetNameSafe(Controller->GetCurrentTarget()) : TEXT("-"),
			(Controller && Controller->GetStateTreeComponent()->IsRunning()) ? 1 : 0,
			Ctx.TelegraphStartTimes.Num(), Ctx.TelegraphEndTimes.Num(), Ctx.AttackEndTimes.Num());
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
	void Observe(const TSharedRef<FContext>& Ctx, double Seconds, TFunction<void()> EachFrame = nullptr)
	{
		TSharedRef<double> StartTime = MakeShared<double>(-1.0);
		Step([Ctx, Seconds, StartTime, EachFrame = MoveTemp(EachFrame)]() -> bool
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
			if (EachFrame)
			{
				EachFrame();
			}
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

			// 가까운 쪽은 반드시 클라이언트 자리 — 적을 부르는 RPC 와 공격 입력이 실제 넷 드라이버를 탄다
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

			AAstralCharacter* NearPawn = PawnIn(ServerWorld, Ctx->NearId);
			AAstralCharacter* FarPawn = PawnIn(ServerWorld, Ctx->FarId);
			if (!Test.TestNotNull(TEXT("near hero pawn"), NearPawn) || !Test.TestNotNull(TEXT("far hero pawn"), FarPawn))
			{
				Ctx->bAborted = true;
				return;
			}

			// 서버에서 자리를 잡는다. 둘 다 +X 를 본다 — 적은 가까운 쪽의 정면에 나온다
			NearPawn->TeleportTo(NearHeroLocation, FRotator::ZeroRotator);
			FarPawn->TeleportTo(FarHeroLocation, FRotator::ZeroRotator);
			Test.TestEqual(TEXT("no enemy before SpawnEnemy"), EnemiesIn(ServerWorld).Num(), 0);
		});
		Hold(Ctx, 1.0);

		// 클라이언트의 디버그 명령 — Exec → 서버 RPC
		Do(Ctx, [Ctx]()
		{
			AAstralCharacter* ClientPawn = PawnIn(FindSeatWorld(Ctx->NearId), Ctx->NearId);
			if (!Ctx->Test->TestNotNull(TEXT("near hero pawn on its own client"), ClientPawn))
			{
				Ctx->bAborted = true;
				return;
			}
			Ctx->Test->TestFalse(TEXT("SpawnEnemy is called on a client (no authority)"), ClientPawn->HasAuthority());
			ClientPawn->SpawnEnemy(FString(), EnemySpawnDistance);
		});
		WaitUntil(Ctx, TEXT("SpawnEnemy: enemy on the server with a running tree, replicated to every client"), 30.0, [Ctx]()
		{
			const TArray<AAstralCombatCharacter*> ServerEnemies = EnemiesIn(FindServerWorld());
			if (ServerEnemies.Num() != 1)
			{
				return false;
			}
			Ctx->Enemy = ServerEnemies[0];
			const AAstralEnemyController* Controller = EnemyController(*Ctx);
			if (!Controller || !Controller->GetStateTreeComponent()->IsRunning())
			{
				return false;
			}
			for (UWorld* World : GetPieWorlds())
			{
				if (World->GetNetMode() == NM_Client && EnemiesIn(World).Num() != 1)
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
			const FVector Expected = NearHeroLocation + FVector(EnemySpawnDistance, 0.0, 0.0);
			Test.TestTrue(TEXT("SpawnEnemy: enemy appears in front of the caller"), FVector::Dist2D(Ctx->Enemy->GetActorLocation(), Expected) <= 250.0);
			Test.TestEqual(TEXT("one enemy controller on the server"), NumEnemyControllersIn(ServerWorld), 1);
			for (UWorld* World : GetPieWorlds())
			{
				if (World->GetNetMode() == NM_Client)
				{
					Test.TestEqual(TEXT("no enemy controller on a client"), NumEnemyControllersIn(World), 0);
				}
			}
			Ctx->NearHealthBefore = HealthOf(PawnIn(ServerWorld, Ctx->NearId));
			Ctx->FarHealthBefore = HealthOf(PawnIn(ServerWorld, Ctx->FarId));
			Ctx->EnemyHealthBefore = HealthOf(Ctx->Enemy.Get());
			Note(Test, FString::Printf(TEXT("setup: %s, near id %d hp %.0f, far id %d hp %.0f, enemy hp %.0f at %s"),
				Ctx->bDedicated ? TEXT("dedicated") : TEXT("listen"), Ctx->NearId, Ctx->NearHealthBefore, Ctx->FarId, Ctx->FarHealthBefore, Ctx->EnemyHealthBefore,
				*Ctx->Enemy->GetActorLocation().ToCompactString()));
		});
	}

	void EnqueueChaseAndHit(const TSharedRef<FContext>& Ctx)
	{
		// A4 — 가장 가까운 플레이어를 쫓아와 예고 뒤 때린다
		WaitSampling(Ctx, TEXT("A4: the enemy's attack lowers the near hero's health on the server"), 25.0, [Ctx]()
		{
			return HealthOf(PawnIn(FindServerWorld(), Ctx->NearId)) < Ctx->NearHealthBefore;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			const AAstralCharacter* NearPawn = PawnIn(ServerWorld, Ctx->NearId);
			const float Damage = Ctx->NearHealthBefore - HealthOf(NearPawn);
			const AAstralEnemyController* Controller = EnemyController(*Ctx);

			Test.TestTrue(TEXT("A4: damage equals the attack's BaseDamage"), FMath::IsNearlyEqual(Damage, AttackDamage, 0.01f));
			Test.TestEqual(TEXT("A4: the far hero was not hit"), HealthOf(PawnIn(ServerWorld, Ctx->FarId)), Ctx->FarHealthBefore);
			Test.TestTrue(TEXT("A4: the target is the nearest player"), Controller && Controller->GetCurrentTarget() == NearPawn);
			Test.TestTrue(TEXT("A4: the enemy moved to the hero"), FVector::Dist2D(Ctx->Enemy->GetActorLocation(), NearPawn->GetActorLocation()) <= 330.0);

			const bool bSawTelegraph = Ctx->TelegraphStartTimes.Num() == 1 && Ctx->TelegraphEndTimes.Num() == 1;
			if (Test.TestTrue(TEXT("A4: one telegraph before the hit"), bSawTelegraph))
			{
				const double Telegraph = Ctx->TelegraphEndTimes[0] - Ctx->TelegraphStartTimes[0];
				Note(Test, FString::Printf(TEXT("A4: hit for %.1f after a %.2f s telegraph, enemy stopped %.0f from the hero, telegraph started %.2f s after the enemy spawned"),
					Damage, Telegraph, FVector::Dist2D(Ctx->Enemy->GetActorLocation(), NearPawn->GetActorLocation()),
					Ctx->TelegraphStartTimes[0] - Ctx->Enemy->CreationTime));
				Test.TestTrue(TEXT("A4: telegraph lasts TelegraphDuration"), FMath::Abs(Telegraph - TelegraphSeconds) <= TimingSlack);
			}
			Test.TestEqual(TEXT("A4: the attack ended with the hit (no stagger)"), Ctx->AttackEndTimes.Num(), 1);
		});
		WaitUntil(Ctx, TEXT("A4: every client sees the same health as the server"), 10.0, [Ctx]()
		{
			const float ServerHealth = HealthOf(PawnIn(FindServerWorld(), Ctx->NearId));
			for (const UWorld* SeatWorld : GetSeatWorlds())
			{
				if (!FMath::IsNearlyEqual(HealthOf(PawnIn(SeatWorld, Ctx->NearId)), ServerHealth, 0.01f))
				{
					return false;
				}
			}
			return true;
		}, [Ctx]()
		{
			FString Seen;
			for (const UWorld* SeatWorld : GetSeatWorlds())
			{
				Seen += FString::Printf(TEXT(" seat %d sees %.1f"), LocalPlayerIdIn(SeatWorld), HealthOf(PawnIn(SeatWorld, Ctx->NearId)));
			}
			return FString::Printf(TEXT("server %.1f,%s"), HealthOf(PawnIn(FindServerWorld(), Ctx->NearId)), *Seen);
		});

		// 패링 없는 주기의 기준값 — 판정 뒤 다음 예고까지 = 회복 시간
		WaitSampling(Ctx, TEXT("A4: the next telegraph starts"), 15.0, [Ctx]() { return Ctx->TelegraphStartTimes.Num() >= 2; });
		Do(Ctx, [Ctx]()
		{
			const double Gap = Ctx->TelegraphStartTimes[1] - Ctx->TelegraphEndTimes[0];
			Note(*Ctx->Test, FString::Printf(TEXT("A4: unparried cycle — next telegraph %.2f s after the hit (Recovery %.1f s)"), Gap, RecoverySeconds));
			Ctx->Test->TestTrue(TEXT("A4: unparried cycle waits only the recovery time"), FMath::Abs(Gap - RecoverySeconds) <= TimingSlack);
		});
	}

	void EnqueueParry(const TSharedRef<FContext>& Ctx)
	{
		// A7 — 두 번째 예고 중에 방어 태그를 서버에서 직접 세운다. 정면 판정은 방어자의 전방 기준이다(가까운 히어로는 +X = 적 쪽을 본다)
		Do(Ctx, [Ctx]()
		{
			UWorld* ServerWorld = FindServerWorld();
			const AAstralPlayerController* PC = PawnIn(ServerWorld, Ctx->NearId) ? Cast<AAstralPlayerController>(PawnIn(ServerWorld, Ctx->NearId)->GetController()) : nullptr;
			UAstralAbilitySystemComponent* ASC = PC ? PC->GetAstralAbilitySystemComponent() : nullptr;
			if (!Ctx->Test->TestNotNull(TEXT("A7: near hero's ASC on the server"), ASC))
			{
				Ctx->bAborted = true;
				return;
			}
			ASC->SetLooseGameplayTagCount(FGameplayTag::RequestGameplayTag(ParryTagName), 1);
			Ctx->NearHealthBefore = HealthOf(PawnIn(ServerWorld, Ctx->NearId));
		});
		WaitSampling(Ctx, TEXT("A7: the parried sweep lands (second telegraph ends)"), 10.0, [Ctx]() { return Ctx->TelegraphEndTimes.Num() >= 2; });
		Do(Ctx, [Ctx]()
		{
			UWorld* ServerWorld = FindServerWorld();
			Ctx->Test->TestEqual(TEXT("A7: a parried attack does no damage"), HealthOf(PawnIn(ServerWorld, Ctx->NearId)), Ctx->NearHealthBefore);
			Ctx->Test->TestTrue(TEXT("A7: the attack ability is still active right after the parried sweep (staggered)"), EnemyAttackActive(*Ctx));

			// 다음 공격은 막지 않는다
			if (const AAstralPlayerController* PC = Cast<AAstralPlayerController>(PawnIn(ServerWorld, Ctx->NearId)->GetController()))
			{
				PC->GetAstralAbilitySystemComponent()->SetLooseGameplayTagCount(FGameplayTag::RequestGameplayTag(ParryTagName), 0);
			}
		});
		WaitSampling(Ctx, TEXT("A7: the staggered attack ends and the next telegraph starts"), 15.0, [Ctx]() { return Ctx->AttackEndTimes.Num() >= 2 && Ctx->TelegraphStartTimes.Num() >= 3; });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const double Sweep = Ctx->TelegraphEndTimes[1];
			const double StaggerHeld = Ctx->AttackEndTimes[1] - Sweep;
			const double NextTelegraph = Ctx->TelegraphStartTimes[2] - Sweep;
			const double UnparriedHeld = Ctx->AttackEndTimes[0] - Ctx->TelegraphEndTimes[0];
			Note(Test, FString::Printf(TEXT("A7: parried — ability stayed active %.2f s after the sweep (StaggerRecovery %.1f s; unparried %.2f s), next telegraph %.2f s after the sweep (unparried %.2f s)"),
				StaggerHeld, StaggerSeconds, UnparriedHeld, NextTelegraph, Ctx->TelegraphStartTimes[1] - Ctx->TelegraphEndTimes[0]));
			Test.TestTrue(TEXT("A7: the staggered attack holds for StaggerRecovery"), FMath::Abs(StaggerHeld - StaggerSeconds) <= TimingSlack);
			Test.TestTrue(TEXT("A7: no new attack during the stagger"), NextTelegraph >= StaggerSeconds + RecoverySeconds - TimingSlack);
			Test.TestTrue(TEXT("A7: the unparried attack ended at its sweep"), UnparriedHeld <= TimingSlack);
		});
	}

	void EnqueueHeroAttack(const TSharedRef<FContext>& Ctx)
	{
		// A8 — 클라이언트 히어로의 실제 공격 입력. 무인 PIE 에서 안 될 수 있다 — 안 되면 오류만 남기고 뒤 단계는 계속한다
		Do(Ctx, [Ctx]()
		{
			UWorld* ServerWorld = FindServerWorld();
			AAstralCharacter* NearPawn = PawnIn(ServerWorld, Ctx->NearId);
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
		});
		Observe(Ctx, 0.7);
		Do(Ctx, [Ctx]()
		{
			UWorld* SeatWorld = FindSeatWorld(Ctx->NearId);
			AAstralPlayerController* PC = Cast<AAstralPlayerController>(GetLocalPC(SeatWorld));
			UAstralAbilitySystemComponent* ASC = PC ? PC->GetAstralAbilitySystemComponent() : nullptr;
			APawn* ClientPawn = PC ? PC->GetPawn() : nullptr;
			if (!Ctx->Test->TestTrue(TEXT("A8: client controller, pawn and ASC"), ASC && ClientPawn && Ctx->Enemy.IsValid()))
			{
				return;
			}
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
		Observe(Ctx, 6.0, [Ctx]()
		{
			if (Ctx->Enemy.IsValid() && HealthOf(Ctx->Enemy.Get()) < Ctx->EnemyHealthBefore)
			{
				Ctx->bHeroAttackLanded = true;
			}
		});
		Do(Ctx, [Ctx]()
		{
			const float Health = HealthOf(Ctx->Enemy.Get());
			Note(*Ctx->Test, FString::Printf(TEXT("A8: client basic-attack input — enemy hp %.1f -> %.1f on the server"), Ctx->EnemyHealthBefore, Health));
			Ctx->Test->TestTrue(TEXT("A8: the client hero's attack input damages the enemy on the server"), Ctx->bHeroAttackLanded);
		});
	}

	void EnqueueTargetDeath(const TSharedRef<FContext>& Ctx)
	{
		// A5 — 타깃이 죽으면 다른 플레이어로 넘어간다
		Do(Ctx, [Ctx]()
		{
			UWorld* ServerWorld = FindServerWorld();
			Ctx->FarHealthBefore = HealthOf(PawnIn(ServerWorld, Ctx->FarId));
			if (AAstralCharacter* NearPawn = PawnIn(ServerWorld, Ctx->NearId))
			{
				NearPawn->DamageSelf(100000.f);
			}
		});
		WaitSampling(Ctx, TEXT("A5: after its target died the enemy targets the other player"), 15.0, [Ctx]()
		{
			const AAstralEnemyController* Controller = EnemyController(*Ctx);
			const UWorld* ServerWorld = FindServerWorld();
			return Controller && IsDead(PawnIn(ServerWorld, Ctx->NearId)) && Controller->GetCurrentTarget() == PawnIn(ServerWorld, Ctx->FarId);
		});

		// 추격 중에 그 타깃마저 죽는다(전원 사망) — TargetLost 이벤트가 Chase 를 끊어야 한다. 끊지 않으면 시체까지 걸어간다
		Do(Ctx, [Ctx]() { Ctx->MarkLocation = Ctx->Enemy->GetActorLocation(); });
		WaitSampling(Ctx, TEXT("A5: the enemy is chasing the other player (moved 300, still far from it)"), 15.0, [Ctx]()
		{
			const AAstralCharacter* FarPawn = PawnIn(FindServerWorld(), Ctx->FarId);
			return FarPawn && FVector::Dist2D(Ctx->Enemy->GetActorLocation(), Ctx->MarkLocation) >= 300.0
				&& FVector::Dist2D(Ctx->Enemy->GetActorLocation(), FarPawn->GetActorLocation()) >= 600.0;
		});
		Do(Ctx, [Ctx]()
		{
			UWorld* ServerWorld = FindServerWorld();
			AAstralCharacter* FarPawn = PawnIn(ServerWorld, Ctx->FarId);
			const AAstralEnemyController* Controller = EnemyController(*Ctx);

			FarPawn->DamageSelf(100000.f);
			Ctx->Test->TestNull(TEXT("A5: the target is cleared in the same call its death starts"), Controller ? Controller->GetCurrentTarget() : nullptr);
			Ctx->MarkLocation = Ctx->Enemy->GetActorLocation();
			Ctx->MarkTime = ServerTime();
		});
		WaitSampling(Ctx, TEXT("A5: the chase stops when the target dies (TargetLost)"), 6.0, [Ctx]()
		{
			return Ctx->Enemy->GetVelocity().Size2D() < 1.0;
		});
		Do(Ctx, [Ctx]()
		{
			const AAstralCharacter* FarPawn = PawnIn(FindServerWorld(), Ctx->FarId);
			const double StopSeconds = ServerTime() - Ctx->MarkTime;
			const double Walked = FVector::Dist2D(Ctx->Enemy->GetActorLocation(), Ctx->MarkLocation);
			const double ToCorpse = FVector::Dist2D(Ctx->Enemy->GetActorLocation(), FarPawn->GetActorLocation());
			Note(*Ctx->Test, FString::Printf(TEXT("A5: target died mid-chase — enemy stopped %.2f s later after %.0f more cm, %.0f from the corpse"), StopSeconds, Walked, ToCorpse));
			Ctx->Test->TestTrue(TEXT("A5: the enemy stops right away instead of walking to the corpse"), StopSeconds <= 0.5 && ToCorpse >= 400.0);

			Ctx->MarkTelegraphStarts = Ctx->TelegraphStartTimes.Num();
			Ctx->bSawAttackWhileEveryoneDead = false;
		});
		Observe(Ctx, 4.0, [Ctx]()
		{
			const AAstralEnemyController* Controller = EnemyController(*Ctx);
			if (Ctx->bAttackActive || Ctx->bTelegraphing || (Controller && Controller->GetCurrentTarget() != nullptr))
			{
				Ctx->bSawAttackWhileEveryoneDead = true;
			}
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const AAstralEnemyController* Controller = EnemyController(*Ctx);
			Test.TestFalse(TEXT("A5: no attack and no target for 4 s while everyone is dead"), Ctx->bSawAttackWhileEveryoneDead);
			Test.TestEqual(TEXT("A5: no new telegraph while everyone is dead"), Ctx->TelegraphStartTimes.Num(), Ctx->MarkTelegraphStarts);
			Test.TestTrue(TEXT("A5: the tree keeps running (it retries)"), Controller && Controller->GetStateTreeComponent()->IsRunning());

			// 부활 — 따로 구독하지 않는다. Wait 의 재시도가 다음 Acquire 에서 다시 후보로 잡는다
			AAstralCharacter* FarPawn = PawnIn(FindServerWorld(), Ctx->FarId);
			FarPawn->ReviveSelf();
			Ctx->FarHealthBefore = HealthOf(FarPawn);
			Test.TestFalse(TEXT("A5: the far hero is alive again"), IsDead(FarPawn));
			Ctx->MarkTime = ServerTime();
		});
		WaitSampling(Ctx, TEXT("A5: the revived player becomes the target again"), 5.0, [Ctx]()
		{
			const AAstralEnemyController* Controller = EnemyController(*Ctx);
			return Controller && Controller->GetCurrentTarget() == PawnIn(FindServerWorld(), Ctx->FarId);
		});
		Do(Ctx, [Ctx]()
		{
			const double Seconds = ServerTime() - Ctx->MarkTime;
			Note(*Ctx->Test, FString::Printf(TEXT("A5: revived player targeted %.2f s after the revive (Wait retry 0.5 s)"), Seconds));
			Ctx->Test->TestTrue(TEXT("A5: the retry picks the revived player within one Wait"), Seconds <= 0.5 + TimingSlack);
		});
		WaitSampling(Ctx, TEXT("A5: the enemy reaches and hits the revived player"), 30.0, [Ctx]()
		{
			return HealthOf(PawnIn(FindServerWorld(), Ctx->FarId)) < Ctx->FarHealthBefore;
		});
		Do(Ctx, [Ctx]()
		{
			const AAstralCharacter* FarPawn = PawnIn(FindServerWorld(), Ctx->FarId);
			Note(*Ctx->Test, FString::Printf(TEXT("A5: far hero hp %.1f -> %.1f, enemy %.0f from it"),
				Ctx->FarHealthBefore, HealthOf(FarPawn), FVector::Dist2D(Ctx->Enemy->GetActorLocation(), FarPawn->GetActorLocation())));
			Ctx->Test->TestTrue(TEXT("A5: the hit on the other player is one attack's damage"), FMath::IsNearlyEqual(Ctx->FarHealthBefore - HealthOf(FarPawn), AttackDamage, 0.01f));
		});
	}

	void EnqueueEnemyDeath(const TSharedRef<FContext>& Ctx)
	{
		// A6 — 적 HP 0 → 트리 정지 → 서버 · 클라이언트에서 폰이 사라진다
		Do(Ctx, [Ctx]()
		{
			if (!Ctx->Test->TestTrue(TEXT("A6: enemy alive before the kill"), Ctx->Enemy.IsValid() && !IsDead(Ctx->Enemy.Get())))
			{
				Ctx->bAborted = true;
				return;
			}
			const AAstralEnemyController* Controller = EnemyController(*Ctx);
			Ctx->Enemy->DamageSelf(100000.f);
			Ctx->Test->TestTrue(TEXT("A6: enemy is dying"), IsDead(Ctx->Enemy.Get()));
			Ctx->Test->TestTrue(TEXT("A6: the tree stopped at death"), Controller && !Controller->GetStateTreeComponent()->IsRunning());
			Ctx->Test->TestNull(TEXT("A6: a dead enemy holds no target"), Controller ? Controller->GetCurrentTarget() : nullptr);
			Ctx->MarkTime = ServerTime();
		});
		WaitUntil(Ctx, TEXT("A6: the enemy pawn is gone on the server and on every client"), 30.0, [Ctx]()
		{
			for (UWorld* World : GetPieWorlds())
			{
				if (EnemiesIn(World).Num() != 0)
				{
					return false;
				}
			}
			return true;
		}, [Ctx]() { return Describe(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			Note(*Ctx->Test, FString::Printf(TEXT("A6: enemy removed everywhere %.2f s after its death"), ServerTime() - Ctx->MarkTime));
			Ctx->Test->TestEqual(TEXT("A6: no enemy controller left on the server"), NumEnemyControllersIn(FindServerWorld()), 0);
		});
	}

	void EnqueueCombat(FAutomationTestBase& Test, bool bDedicated)
	{
		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;
		Ctx->bDedicated = bDedicated;

		// PIE 시작 때 엔진이 내는 경고 — NavMesh 등록 전에 군중 매니저가 만들어진다. 이 시험과 무관하다
		Test.AddExpectedMessage(TEXT("Unable to find RecastNavMesh instance while trying to create UCrowdManager instance"), ELogVerbosity::Warning, EAutomationExpectedMessageFlags::Contains, -1, /*IsRegex=*/false);

		EnqueueSetup(Ctx);
		EnqueueChaseAndHit(Ctx);
		EnqueueParry(Ctx);
		EnqueueHeroAttack(Ctx);
		EnqueueTargetDeath(Ctx);
		EnqueueEnemyDeath(Ctx);
		EndPie(Ctx);
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemyCombatListenPieTest, "AstralBreak.Net.EnemyCombat.ListenPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralEnemyCombatListenPieTest::RunTest(const FString& Parameters)
{
	AstralEnemyCombatPie::EnqueueCombat(*this, /*bDedicated=*/false);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemyCombatDedicatedPieTest, "AstralBreak.Net.EnemyCombat.DedicatedPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralEnemyCombatDedicatedPieTest::RunTest(const FString& Parameters)
{
	AstralEnemyCombatPie::EnqueueCombat(*this, /*bDedicated=*/true);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
