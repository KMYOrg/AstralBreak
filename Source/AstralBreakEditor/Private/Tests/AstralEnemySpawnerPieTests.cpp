// 단위 D 스포너 네트워크 시험 — 한 프로세스 멀티 PIE (설계 Docs/Design/m3-enemy-ai.md §11 검증 계획 S1 ~ S5)
//
// ListenPIE · DedicatedPIE — CombatTestMap 에서 시험이 서버에 스포너를 직접 만든다(맵은 고치지 않는다). 두 번 돈다:
//   1회차(상자)  S2 히어로가 상자에 들어가면 발동 · S1 서버에 수호병 3 + 컨트롤러 3, 모든 클라이언트에 폰 3, 다시 들어가도 · Activate 를 불러도 3
//                S4 세 마리가 각자 타깃을 잡고 공격한다, 서로를 때리지 않는다
//                S3 셋을 다 죽여야 OnCleared 1회 · 그 뒤 폰이 모든 머신에서 사라진다(제거 시각을 적는다)
//   2회차(수동)  상자 크기 0 — 히어로가 그 자리에 서도 발동하지 않는다 · Activate 로 발동 · 두 번 불러도 3 · S3
// RaidMapPIE — Dedicated 하나. 실제 흐름(허브 → 선택 → 준비 → 시작 → 시임리스 이동)으로 RaidMap 에 가서
//   S5 도착만 해서는 적 0(맵의 스포너가 발동하지 않음) → 히어로를 맵에 놓인 스포너의 상자로 옮기면 3 → 다 죽이면 OnCleared 1회
//   스포너 · 스폰 서브시스템은 서버에만 있다
//
// 스포너의 좌표 · 수는 시험이 정하지 않는다(RaidMap 은 맵에 놓인 스포너를 찾아 쓴다). 히어로의 체력은 시험이 크게 올린다(세 마리에게 맞아도 안 죽게).
// PIE 는 적이 사라진 뒤에 내린다 — 재생 중인 몽타주가 없다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AstralPieTestHelpers.h"
#include "AstralEnemySpawnerTestListener.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Character/Enemy/AstralCombatCharacter.h"
#include "Character/Enemy/AstralEnemyController.h"
#include "Character/Enemy/AstralEnemySpawner.h"
#include "Character/Enemy/AstralEnemySpawnSubsystem.h"
#include "Components/BoxComponent.h"
#include "Engine/GameInstance.h"
#include "EngineUtils.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerState.h"
#include "GameModes/AstralGameState.h"
#include "GameModes/AstralHubGameState.h"
#include "GameplayTagContainer.h"
#include "Player/AstralPlayerController.h"
#include "UObject/StrongObjectPtr.h"

namespace AstralEnemySpawnerPie
{
	using namespace AstralPieTest;

	const TCHAR* const CombatMapPath = TEXT("/Game/Maps/CombatTestMap");
	const TCHAR* const CombatMapName = TEXT("CombatTestMap");
	const TCHAR* const HubMapPath = TEXT("/Game/Maps/HubMap");
	const TCHAR* const HubMapName = TEXT("HubMap");
	const TCHAR* const RaidMapName = TEXT("RaidMap");
	const TCHAR* const GuardianName = TEXT("BP_Enemy_Guardian");
	const TCHAR* const GuardianClassPath = TEXT("/Game/Characters/Enemy/BP_Enemy_Guardian.BP_Enemy_Guardian_C");

	// 태그는 런타임 모듈이 내보내지 않는다 — 이름으로 찾는다
	const TCHAR* const AttackingTagName = TEXT("State.Enemy.Attacking");

	// CombatTestMap 좌표 — 다른 적 시험과 같은 자리(맵의 더미와 떨어진 열린 바닥)
	const FVector NearHeroStart(1100.0, -400.0, 92.0);
	const FVector FarHeroStart(1100.0, 900.0, 92.0);

	// 시험이 만드는 스포너 — 상자가 루트다. 상자는 가까운 히어로의 +X 쪽 230 cm 앞에서 시작하고, 적은 상자 너머에 나온다
	const FVector TestSpawnerLocation(1450.0, -400.0, 150.0);
	const FVector TestBoxExtent(120.0, 300.0, 150.0);
	const FVector TestSpawnPoints[] = { FVector(300.0, -250.0, -150.0), FVector(450.0, 0.0, -150.0), FVector(300.0, 250.0, -150.0) };
	constexpr int32 NumTestSpawnPoints = UE_ARRAY_COUNT(TestSpawnPoints);

	/** 세 마리에게 맞아도 죽지 않는 체력 */
	constexpr float SturdyHealth = 100000.f;

	struct FContext : FContextBase
	{
		bool bDedicated = false;
		int32 NumPlayers = 2;

		/** 가까운 쪽 = 클라이언트 자리의 플레이어(상자에 들어간다), 먼 쪽 = 나머지 */
		int32 NearId = 0;
		int32 FarId = 0;

		TWeakObjectPtr<AAstralEnemySpawner> Spawner;
		TStrongObjectPtr<UAstralEnemySpawnerTestListener> Listener;
		int32 ExpectedEnemies = 0;

		/** 이번 발동에서 서버가 낸 수호병 */
		TArray<TWeakObjectPtr<AAstralCombatCharacter>> Enemies;
		TArray<bool> bAttacked;
		int32 HeroHits = 0;
		float LastNearHealth = -1.f;
		double MarkTime = 0.0;
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

	TArray<UWorld*> GetClientWorlds()
	{
		TArray<UWorld*> Out;
		for (UWorld* World : GetPieWorlds())
		{
			if (World->GetNetMode() == NM_Client)
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

	AAstralPlayerController* FindSeatPC(int32 PlayerId)
	{
		return Cast<AAstralPlayerController>(GetLocalPC(FindSeatWorld(PlayerId)));
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

	TArray<AAstralCombatCharacter*> GuardiansIn(UWorld* World)
	{
		TArray<AAstralCombatCharacter*> Out;
		if (World)
		{
			for (TActorIterator<AAstralCombatCharacter> It(World); It; ++It)
			{
				if (It->GetClass()->GetName().StartsWith(GuardianName))
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

	TArray<AAstralEnemySpawner*> SpawnersIn(UWorld* World)
	{
		TArray<AAstralEnemySpawner*> Out;
		if (World)
		{
			for (TActorIterator<AAstralEnemySpawner> It(World); It; ++It)
			{
				Out.Add(*It);
			}
		}
		return Out;
	}

	/** 서버에 N, 서버의 적 컨트롤러 N, 모든 클라이언트에 N */
	bool GuardianCountIs(int32 Expected)
	{
		UWorld* ServerWorld = FindServerWorld();
		if (GuardiansIn(ServerWorld).Num() != Expected || NumEnemyControllersIn(ServerWorld) != Expected)
		{
			return false;
		}
		for (UWorld* ClientWorld : GetClientWorlds())
		{
			if (GuardiansIn(ClientWorld).Num() != Expected)
			{
				return false;
			}
		}
		return true;
	}

	double ServerTime()
	{
		const UWorld* World = FindServerWorld();
		return World ? World->GetTimeSeconds() : 0.0;
	}

	int32 NumCleared(const FContext& Ctx)
	{
		return Ctx.Listener.IsValid() ? Ctx.Listener->NumCleared : -1;
	}

	FString Describe(const FContext& Ctx)
	{
		UWorld* ServerWorld = FindServerWorld();
		FString ClientCounts;
		for (UWorld* ClientWorld : GetClientWorlds())
		{
			ClientCounts += FString::Printf(TEXT("%s%d"), ClientCounts.IsEmpty() ? TEXT("") : TEXT("/"), GuardiansIn(ClientWorld).Num());
		}
		return FString::Printf(TEXT("server map '%s', seats %d, guardians on the server %d, on the clients %s, enemy controllers %d, spawner %s (activated %d, alive %d), cleared %d, hero hits %d"),
			*MapOf(ServerWorld), GetSeatWorlds().Num(), GuardiansIn(ServerWorld).Num(), *ClientCounts, NumEnemyControllersIn(ServerWorld),
			*GetNameSafe(Ctx.Spawner.Get()), (Ctx.Spawner.IsValid() && Ctx.Spawner->HasActivated()) ? 1 : 0, Ctx.Spawner.IsValid() ? Ctx.Spawner->GetNumAliveEnemies() : -1,
			NumCleared(Ctx), Ctx.HeroHits);
	}

	/** 서버가 Map 에 있고 모든 플레이어가 서버와 제 자리에서 살아 있는 폰을 갖고 있다 */
	bool AllPlayersHavePawns(const TCHAR* Map, int32 NumPlayers)
	{
		const UWorld* ServerWorld = FindServerWorld();
		const AGameStateBase* GameState = ServerWorld ? ServerWorld->GetGameState() : nullptr;
		if (!ServerWorld || !ServerWorld->HasBegunPlay() || MapOf(ServerWorld) != Map || !GameState || GameState->PlayerArray.Num() != NumPlayers)
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
		if (SeatWorlds.Num() != NumPlayers)
		{
			return false;
		}
		for (const UWorld* SeatWorld : SeatWorlds)
		{
			const int32 MyId = LocalPlayerIdIn(SeatWorld);
			if (MyId == 0 || MapOf(SeatWorld) != Map || HealthOf(PawnIn(SeatWorld, MyId)) <= 0.f)
			{
				return false;
			}
		}
		return true;
	}

	/** 가까운 쪽 = 번호가 가장 작은 클라이언트 자리. 못 정하면 false */
	bool PickNearAndFar(FContext& Ctx)
	{
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
		if (ClientIds.Num() == 0)
		{
			return false;
		}
		Ctx.NearId = ClientIds[0];
		for (const int32 PlayerId : AllIds)
		{
			if (PlayerId != Ctx.NearId)
			{
				Ctx.FarId = PlayerId;
			}
		}
		return true;
	}

	/** 서버에서 히어로의 체력을 크게 올린다 — 속성 값을 직접 쓴다 */
	void MakeHeroSturdy(const AAstralCharacter* Pawn)
	{
		const AAstralPlayerController* PC = Pawn ? Cast<AAstralPlayerController>(Pawn->GetController()) : nullptr;
		if (UAstralAbilitySystemComponent* ASC = PC ? PC->GetAstralAbilitySystemComponent() : nullptr)
		{
			ASC->SetNumericAttributeBase(UAstralHealthSet::GetMaxHealthAttribute(), SturdyHealth);
			ASC->SetNumericAttributeBase(UAstralHealthSet::GetHealthAttribute(), SturdyHealth);
		}
	}

	/** 스포너의 OnCleared 를 세는 리스너를 새로 단다 */
	void ListenTo(FContext& Ctx, AAstralEnemySpawner* Spawner)
	{
		Ctx.Spawner = Spawner;
		Ctx.Listener = TStrongObjectPtr<UAstralEnemySpawnerTestListener>(NewObject<UAstralEnemySpawnerTestListener>(GetTransientPackage()));
		Spawner->OnCleared.AddDynamic(Ctx.Listener.Get(), &UAstralEnemySpawnerTestListener::HandleCleared);
	}

	/** 스포너의 상자 가운데로 히어로를 옮긴다(높이는 히어로의 지금 높이) */
	void MoveHeroIntoBox(const FContext& Ctx)
	{
		AAstralCharacter* NearPawn = PawnIn(FindServerWorld(), Ctx.NearId);
		if (NearPawn && Ctx.Spawner.IsValid())
		{
			const FVector BoxCenter = Ctx.Spawner->GetTriggerBox()->GetComponentLocation();
			NearPawn->TeleportTo(FVector(BoxCenter.X, BoxCenter.Y, NearPawn->GetActorLocation().Z), NearPawn->GetActorRotation());
		}
	}

	/** 매 프레임 — 각 수호병이 공격을 시작했는가, 가까운 히어로가 맞았는가 */
	void SampleCombat(FContext& Ctx)
	{
		const FGameplayTag AttackingTag = FGameplayTag::RequestGameplayTag(AttackingTagName);
		for (int32 Index = 0; Index < Ctx.Enemies.Num(); ++Index)
		{
			const UAbilitySystemComponent* ASC = Ctx.Enemies[Index].IsValid() ? Ctx.Enemies[Index]->GetAbilitySystemComponent() : nullptr;
			if (ASC && ASC->HasMatchingGameplayTag(AttackingTag))
			{
				Ctx.bAttacked[Index] = true;
			}
		}

		const float NearHealth = HealthOf(PawnIn(FindServerWorld(), Ctx.NearId));
		if (Ctx.LastNearHealth >= 0.f && NearHealth < Ctx.LastNearHealth)
		{
			++Ctx.HeroHits;
		}
		Ctx.LastNearHealth = NearHealth;
	}

	// ─── 단계 (발동 뒤 — 두 시험이 같이 쓴다) ───

	/** S1 — 서버에 수호병 N + 컨트롤러 N, 모든 클라이언트에 폰 N. 서버의 수호병을 Ctx.Enemies 에 담는다 */
	void EnqueueWaitSpawned(const TSharedRef<FContext>& Ctx, const TCHAR* Label)
	{
		WaitUntil(Ctx, *FString::Printf(TEXT("%s: the spawner's guardians are on the server with controllers and replicated to every client"), Label), 30.0, [Ctx]()
		{
			return Ctx->Spawner.IsValid() && Ctx->Spawner->HasActivated() && GuardianCountIs(Ctx->ExpectedEnemies);
		}, [Ctx]() { return Describe(*Ctx); });
		Do(Ctx, [Ctx, Label = FString(Label)]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();

			Ctx->Enemies.Reset();
			for (AAstralCombatCharacter* Guardian : GuardiansIn(ServerWorld))
			{
				Ctx->Enemies.Add(Guardian);
			}
			Ctx->bAttacked.Init(false, Ctx->Enemies.Num());
			Ctx->HeroHits = 0;
			Ctx->LastNearHealth = -1.f;

			int32 NumPossessed = 0;
			double MinSpacing = TNumericLimits<double>::Max();
			for (int32 Index = 0; Index < Ctx->Enemies.Num(); ++Index)
			{
				NumPossessed += Cast<AAstralEnemyController>(Ctx->Enemies[Index]->GetController()) ? 1 : 0;
				for (int32 Other = Index + 1; Other < Ctx->Enemies.Num(); ++Other)
				{
					MinSpacing = FMath::Min(MinSpacing, FVector::Dist2D(Ctx->Enemies[Index]->GetActorLocation(), Ctx->Enemies[Other]->GetActorLocation()));
				}
			}
			Test.TestEqual(*FString::Printf(TEXT("%s S1: every guardian is possessed by an enemy controller"), *Label), NumPossessed, Ctx->ExpectedEnemies);
			Test.TestEqual(*FString::Printf(TEXT("%s S1: the spawner counts every guardian alive"), *Label), Ctx->Spawner->GetNumAliveEnemies(), Ctx->ExpectedEnemies);
			Test.TestEqual(*FString::Printf(TEXT("%s S3: OnCleared has not fired while the guardians live"), *Label), NumCleared(*Ctx), 0);
			Note(Test, FString::Printf(TEXT("%s S1: %d guardian(s) on the server, %d enemy controller(s), every one of %d client(s) sees %d, closest pair %.0f cm apart at spawn"),
				*Label, Ctx->Enemies.Num(), NumEnemyControllersIn(ServerWorld), GetClientWorlds().Num(), Ctx->ExpectedEnemies, Ctx->Enemies.Num() > 1 ? MinSpacing : 0.0));
		});
	}

	/** S3 — 하나씩 죽인다: 마지막이 죽기 시작할 때 OnCleared 1회. 그 뒤 모든 머신에서 폰이 사라진다 */
	void EnqueueKillAll(const TSharedRef<FContext>& Ctx, const TCHAR* Label)
	{
		Do(Ctx, [Ctx, Label = FString(Label)]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			if (!Test.TestTrue(*FString::Printf(TEXT("%s S3: spawner and guardians are still there before the kills"), *Label), Ctx->Spawner.IsValid() && Ctx->Enemies.Num() == Ctx->ExpectedEnemies))
			{
				Ctx->bAborted = true;
				return;
			}

			FString ClearedAfterEachKill;
			for (int32 Index = 0; Index < Ctx->Enemies.Num(); ++Index)
			{
				if (!Test.TestTrue(*FString::Printf(TEXT("%s S3: guardian %d is alive before its kill"), *Label, Index), Ctx->Enemies[Index].IsValid()))
				{
					Ctx->bAborted = true;
					return;
				}
				Ctx->Enemies[Index]->DamageSelf(1000000.f);

				const bool bLast = Index == Ctx->Enemies.Num() - 1;
				Test.TestEqual(*FString::Printf(TEXT("%s S3: OnCleared count right after kill %d of %d"), *Label, Index + 1, Ctx->Enemies.Num()), NumCleared(*Ctx), bLast ? 1 : 0);
				Test.TestEqual(*FString::Printf(TEXT("%s S3: alive count right after kill %d"), *Label, Index + 1), Ctx->Spawner->GetNumAliveEnemies(), Ctx->Enemies.Num() - Index - 1);
				ClearedAfterEachKill += FString::Printf(TEXT("%s%d"), ClearedAfterEachKill.IsEmpty() ? TEXT("") : TEXT(" / "), NumCleared(*Ctx));
			}
			Ctx->MarkTime = ServerTime();
			Note(Test, FString::Printf(TEXT("%s S3: OnCleared count after each kill %s"), *Label, *ClearedAfterEachKill));
		});
		WaitUntil(Ctx, *FString::Printf(TEXT("%s S3: the dead guardians are gone on the server and on every client"), Label), 30.0, []()
		{
			return GuardianCountIs(0);
		}, [Ctx]() { return Describe(*Ctx); });
		Do(Ctx, [Ctx, Label = FString(Label)]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const double Seconds = ServerTime() - Ctx->MarkTime;
			Note(Test, FString::Printf(TEXT("%s S3 / D-0a: guardians removed everywhere %.2f s after the last death started, OnCleared fired %d time(s) in total"), *Label, Seconds, NumCleared(*Ctx)));
			// 사망 시작 → 사망 완료 → DestroyAfterDeathDelay. 제거 경로를 서브시스템으로 옮긴 뒤에도 그대로여야 한다(다른 적 시험이 재는 5초)
			Test.TestTrue(*FString::Printf(TEXT("%s D-0a: removal still takes about 5 s after the death started"), *Label), Seconds >= 4.0 && Seconds <= 8.0);
			Test.TestEqual(*FString::Printf(TEXT("%s S3: OnCleared fired exactly once (the later destruction does not fire it again)"), *Label), NumCleared(*Ctx), 1);
		});
	}

	// ─── CombatTestMap — 시험이 만든 스포너 ───

	void EnqueueCombatSetup(const TSharedRef<FContext>& Ctx)
	{
		RequestPie(Ctx, CombatMapPath, Ctx->bDedicated ? PIE_Client : PIE_ListenServer, Ctx->NumPlayers);
		WaitUntil(Ctx, TEXT("every player has a living pawn on the server and on its own seat"), 240.0, [Ctx]()
		{
			return AllPlayersHavePawns(CombatMapName, Ctx->NumPlayers);
		}, [Ctx]() { return Describe(*Ctx); });

		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			Test.TestEqual(TEXT("server net mode"), static_cast<int32>(ServerWorld->GetNetMode()), static_cast<int32>(Ctx->bDedicated ? NM_DedicatedServer : NM_ListenServer));

			if (!Test.TestTrue(TEXT("a client seat exists"), PickNearAndFar(*Ctx)))
			{
				Ctx->bAborted = true;
				return;
			}
			MakeHeroSturdy(PawnIn(ServerWorld, Ctx->NearId));
			MakeHeroSturdy(PawnIn(ServerWorld, Ctx->FarId));

			// 수호병은 아무도 안 때려도 타깃을 추첨하고 서로 나눈다(§13 T3 · T4) — S4 는 가까운 쪽이 맞는 것을 보므로 먼 쪽을 후보에서 뺀다(적대심 0 은 뽑히지 않는다)
			const AAstralCharacter* FarPawn = PawnIn(ServerWorld, Ctx->FarId);
			const AAstralPlayerController* FarPC = FarPawn ? Cast<AAstralPlayerController>(FarPawn->GetController()) : nullptr;
			if (UAstralAbilitySystemComponent* FarASC = FarPC ? FarPC->GetAstralAbilitySystemComponent() : nullptr)
			{
				FarASC->SetNumericAttributeBase(UAstralHeroResourceSet::GetHostilityAttribute(), 0.f);
			}

			// 스폰 서브시스템은 서버에만 있다
			Test.TestNotNull(TEXT("the spawn subsystem exists on the server"), ServerWorld->GetSubsystem<UAstralEnemySpawnSubsystem>());
			for (const UWorld* ClientWorld : GetClientWorlds())
			{
				Test.TestNull(TEXT("no spawn subsystem on a client"), ClientWorld->GetSubsystem<UAstralEnemySpawnSubsystem>());
			}
			Test.TestEqual(TEXT("no guardian before the spawner"), GuardiansIn(ServerWorld).Num(), 0);
		});
	}

	/** 한 회차 — 스포너를 만들고 발동시켜 S1 ~ S4 를 본다. bUseBox: 상자 겹침으로 / 아니면 상자 크기 0 + Activate */
	void EnqueueCombatRound(const TSharedRef<FContext>& Ctx, bool bUseBox)
	{
		const TCHAR* Label = bUseBox ? TEXT("box") : TEXT("manual");

		Do(Ctx, [Ctx, bUseBox, Label]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			AAstralCharacter* NearPawn = PawnIn(ServerWorld, Ctx->NearId);
			AAstralCharacter* FarPawn = PawnIn(ServerWorld, Ctx->FarId);
			UClass* GuardianClass = StaticLoadClass(APawn::StaticClass(), nullptr, GuardianClassPath);
			if (!Test.TestNotNull(TEXT("near hero pawn"), NearPawn) || !Test.TestNotNull(TEXT("far hero pawn"), FarPawn) || !Test.TestNotNull(TEXT("BP_Enemy_Guardian class"), GuardianClass))
			{
				Ctx->bAborted = true;
				return;
			}

			// 둘 다 상자 밖. 가까운 쪽은 상자의 −X 쪽 앞, 먼 쪽은 멀리
			NearPawn->TeleportTo(NearHeroStart, FRotator::ZeroRotator);
			FarPawn->TeleportTo(FarHeroStart, FRotator::ZeroRotator);

			// 스포너를 서버에 만든다 — 값은 BeginPlay 전에 채운다(맵에 놓은 스포너와 같은 순서)
			const FTransform SpawnerTransform(TestSpawnerLocation);
			AAstralEnemySpawner* Spawner = ServerWorld->SpawnActorDeferred<AAstralEnemySpawner>(AAstralEnemySpawner::StaticClass(), SpawnerTransform);
			if (!Test.TestNotNull(TEXT("test spawner"), Spawner))
			{
				Ctx->bAborted = true;
				return;
			}
			Spawner->EnemyClass = GuardianClass;
			Spawner->SpawnPoints.Append(TestSpawnPoints, NumTestSpawnPoints);
			Spawner->GetTriggerBox()->SetBoxExtent(bUseBox ? TestBoxExtent : FVector::ZeroVector, /*bUpdateOverlaps=*/false);
			Spawner->FinishSpawning(SpawnerTransform);

			ListenTo(*Ctx, Spawner);
			Ctx->ExpectedEnemies = NumTestSpawnPoints;
			Ctx->Enemies.Reset();

			Test.TestFalse(*FString::Printf(TEXT("%s: a new spawner has not activated"), Label), Spawner->HasActivated());
			Test.TestFalse(*FString::Printf(TEXT("%s: the spawner does not replicate"), Label), Spawner->GetIsReplicated());

			if (!bUseBox)
			{
				// 상자 크기 0 — 그 자리에 서도 발동하지 않는다
				MoveHeroIntoBox(*Ctx);
			}
		});
		Hold(Ctx, 1.0);
		Do(Ctx, [Ctx, bUseBox, Label]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			if (!Test.TestTrue(TEXT("test spawner is still there"), Ctx->Spawner.IsValid()))
			{
				Ctx->bAborted = true;
				return;
			}
			Test.TestFalse(bUseBox ? TEXT("box S2: a hero standing outside the box does not activate the spawner") : TEXT("manual: a hero standing on a spawner with a zero-size box does not activate it"), Ctx->Spawner->HasActivated());
			Test.TestEqual(*FString::Printf(TEXT("%s: no guardian before activation"), Label), GuardiansIn(FindServerWorld()).Num(), 0);
			for (UWorld* ClientWorld : GetClientWorlds())
			{
				Test.TestEqual(*FString::Printf(TEXT("%s: the spawner is not on a client"), Label), SpawnersIn(ClientWorld).Num(), 0);
			}

			// 발동 — S2: 히어로가 상자에 들어간다(서버가 옮긴다 → 겹침 이벤트) / 수동: Activate
			if (bUseBox)
			{
				MoveHeroIntoBox(*Ctx);
				Test.TestTrue(TEXT("box S2: the spawner activates inside the move that puts the hero in the box (overlap event)"), Ctx->Spawner->HasActivated());
			}
			else
			{
				Ctx->Spawner->Activate();
			}
		});
		EnqueueWaitSpawned(Ctx, Label);

		// 한 번만 — 다시 들어가도, Activate 를 다시 불러도 그대로다
		Do(Ctx, [Ctx, bUseBox]()
		{
			if (bUseBox)
			{
				if (AAstralCharacter* NearPawn = PawnIn(FindServerWorld(), Ctx->NearId))
				{
					NearPawn->TeleportTo(NearHeroStart, FRotator::ZeroRotator);
				}
			}
			else if (Ctx->Spawner.IsValid())
			{
				Ctx->Spawner->Activate();
			}
		});
		Hold(Ctx, 0.5);
		Do(Ctx, [Ctx, bUseBox]()
		{
			if (bUseBox && Ctx->Spawner.IsValid())
			{
				MoveHeroIntoBox(*Ctx);
				Ctx->Spawner->Activate();
			}
		});
		Hold(Ctx, 1.0);
		Do(Ctx, [Ctx, Label]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			Test.TestTrue(*FString::Printf(TEXT("%s S1: activating again (re-entering the box / calling Activate) spawns nothing more"), Label), GuardianCountIs(Ctx->ExpectedEnemies));
			Test.TestEqual(*FString::Printf(TEXT("%s S1: alive count unchanged after the second activation"), Label), Ctx->Spawner.IsValid() ? Ctx->Spawner->GetNumAliveEnemies() : -1, Ctx->ExpectedEnemies);
		});

		// S4 — 세 마리가 각자 타깃을 잡고 공격한다 (상자 회차에서만 본다)
		if (bUseBox)
		{
			WaitUntil(Ctx, TEXT("S4: every guardian has started an attack and the hero has been hit"), 60.0, [Ctx]()
			{
				SampleCombat(*Ctx);
				return Ctx->HeroHits > 0 && !Ctx->bAttacked.Contains(false);
			}, [Ctx]() { return Describe(*Ctx); });
			Do(Ctx, [Ctx]()
			{
				FAutomationTestBase& Test = *Ctx->Test;
				UWorld* ServerWorld = FindServerWorld();
				const AAstralCharacter* NearPawn = PawnIn(ServerWorld, Ctx->NearId);
				const AAstralCharacter* FarPawn = PawnIn(ServerWorld, Ctx->FarId);

				int32 NumWithHeroTarget = 0;
				int32 NumUnhurt = 0;
				double MinSpacing = TNumericLimits<double>::Max();
				FString Targets;
				for (int32 Index = 0; Index < Ctx->Enemies.Num(); ++Index)
				{
					const AAstralCombatCharacter* Guardian = Ctx->Enemies[Index].Get();
					if (!Guardian)
					{
						continue;
					}
					const AAstralEnemyController* Controller = Cast<AAstralEnemyController>(Guardian->GetController());
					const AActor* Target = Controller ? Controller->GetCurrentTarget() : nullptr;
					NumWithHeroTarget += (Target && (Target == NearPawn || Target == FarPawn)) ? 1 : 0;
					Targets += FString::Printf(TEXT("%s%s"), Targets.IsEmpty() ? TEXT("") : TEXT(" / "), Target == NearPawn ? TEXT("near") : (Target == FarPawn ? TEXT("far") : TEXT("none")));

					const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(Guardian);
					NumUnhurt += (HealthComponent && HealthComponent->GetHealth() >= HealthComponent->GetMaxHealth()) ? 1 : 0;

					for (int32 Other = Index + 1; Other < Ctx->Enemies.Num(); ++Other)
					{
						if (Ctx->Enemies[Other].IsValid())
						{
							MinSpacing = FMath::Min(MinSpacing, FVector::Dist2D(Guardian->GetActorLocation(), Ctx->Enemies[Other]->GetActorLocation()));
						}
					}
				}
				Note(Test, FString::Printf(TEXT("S4: targets %s, %d hit(s) on the near hero so far, %d of %d guardian(s) at full health, closest pair %.0f cm apart while attacking"),
					*Targets, Ctx->HeroHits, NumUnhurt, Ctx->Enemies.Num(), MinSpacing));
				Test.TestEqual(TEXT("S4: every guardian targets a hero"), NumWithHeroTarget, Ctx->ExpectedEnemies);
				Test.TestEqual(TEXT("S4: no guardian was hurt by another guardian's attack"), NumUnhurt, Ctx->ExpectedEnemies);
			});
		}

		EnqueueKillAll(Ctx, Label);
		Do(Ctx, [Ctx]()
		{
			// 다음 회차를 위해 치운다
			if (Ctx->Spawner.IsValid())
			{
				Ctx->Spawner->Destroy();
			}
			Ctx->Listener.Reset();
		});
	}

	void EnqueueCombatMap(FAutomationTestBase& Test, bool bDedicated)
	{
		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;
		Ctx->bDedicated = bDedicated;

		// PIE 시작 때 엔진이 내는 경고 — NavMesh 등록 전에 군중 매니저가 만들어진다. 이 시험과 무관하다
		Test.AddExpectedMessage(TEXT("Unable to find RecastNavMesh instance while trying to create UCrowdManager instance"), ELogVerbosity::Warning, EAutomationExpectedMessageFlags::Contains, -1, /*IsRegex=*/false);

		EnqueueCombatSetup(Ctx);
		EnqueueCombatRound(Ctx, /*bUseBox=*/true);
		EnqueueCombatRound(Ctx, /*bUseBox=*/false);
		EndPie(Ctx);
	}

	// ─── RaidMap — 맵에 놓인 스포너, 실제 흐름으로 간다 ───

	int32 LeaderIdIn(const UWorld* World)
	{
		const AAstralGameState* GameState = World ? World->GetGameState<AAstralGameState>() : nullptr;
		const APlayerState* Leader = GameState ? GameState->GetPartyLeader() : nullptr;
		return Leader ? Leader->GetPlayerId() : INDEX_NONE;
	}

	/** 서버와 모든 자리가 허브에 있고 방장이 정해졌다 */
	bool IsSettledInHub(int32 NumPlayers)
	{
		const UWorld* ServerWorld = FindServerWorld();
		const AGameStateBase* GameState = ServerWorld ? ServerWorld->GetGameState() : nullptr;
		if (!ServerWorld || !ServerWorld->HasBegunPlay() || MapOf(ServerWorld) != HubMapName || !GameState || GameState->PlayerArray.Num() != NumPlayers || LeaderIdIn(ServerWorld) == INDEX_NONE)
		{
			return false;
		}
		const TArray<UWorld*> SeatWorlds = GetSeatWorlds();
		if (SeatWorlds.Num() != NumPlayers)
		{
			return false;
		}
		for (const UWorld* SeatWorld : SeatWorlds)
		{
			const AGameStateBase* SeatGameState = SeatWorld->GetGameState();
			if (LocalPlayerIdIn(SeatWorld) == 0 || MapOf(SeatWorld) != HubMapName || !SeatGameState || SeatGameState->PlayerArray.Num() != NumPlayers)
			{
				return false;
			}
		}
		return true;
	}

	void EnqueueRaidMap(FAutomationTestBase& Test)
	{
		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;
		Ctx->bDedicated = true;

		Test.AddExpectedMessage(TEXT("Unable to find RecastNavMesh instance while trying to create UCrowdManager instance"), ELogVerbosity::Warning, EAutomationExpectedMessageFlags::Contains, -1, /*IsRegex=*/false);

		// 허브 → 선택 → 준비 → 시작 (파티 흐름 시험과 같은 RPC, 거부 경우는 보지 않는다)
		RequestPie(Ctx, HubMapPath, PIE_Client, Ctx->NumPlayers);
		WaitUntil(Ctx, TEXT("all players in HubMap"), 240.0, [Ctx]() { return IsSettledInHub(Ctx->NumPlayers); }, [Ctx]() { return Describe(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			AAstralPlayerController* LeaderPC = FindSeatPC(LeaderIdIn(FindServerWorld()));
			if (!Ctx->Test->TestNotNull(TEXT("leader seat"), LeaderPC))
			{
				Ctx->bAborted = true;
				return;
			}
			LeaderPC->ServerSelectRaid(RaidMapName);
		});
		WaitUntil(Ctx, TEXT("SelectedRaid = RaidMap on the server"), 20.0, []()
		{
			const UWorld* ServerWorld = FindServerWorld();
			const AAstralHubGameState* HubGameState = ServerWorld ? ServerWorld->GetGameState<AAstralHubGameState>() : nullptr;
			return HubGameState && HubGameState->GetSelectedRaid().MapName == RaidMapName;
		}, [Ctx]() { return Describe(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			for (const UWorld* SeatWorld : GetSeatWorlds())
			{
				if (AAstralPlayerController* PC = Cast<AAstralPlayerController>(GetLocalPC(SeatWorld)))
				{
					PC->ServerSetReady(true);
				}
			}
		});
		WaitUntil(Ctx, TEXT("everyone ready"), 20.0, []()
		{
			const UWorld* ServerWorld = FindServerWorld();
			const AAstralHubGameState* HubGameState = ServerWorld ? ServerWorld->GetGameState<AAstralHubGameState>() : nullptr;
			return HubGameState && HubGameState->AreAllPlayersReady();
		}, [Ctx]() { return Describe(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			if (AAstralPlayerController* LeaderPC = FindSeatPC(LeaderIdIn(FindServerWorld())))
			{
				LeaderPC->ServerStartRaid();
			}
		});
		WaitUntil(Ctx, TEXT("all players in RaidMap with living pawns"), 180.0, [Ctx]()
		{
			return AllPlayersHavePawns(RaidMapName, Ctx->NumPlayers);
		}, [Ctx]() { return Describe(*Ctx); });

		// S5 앞 절반 — 도착만 해서는 발동하지 않는다
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			Test.TestEqual(TEXT("server is a dedicated server"), static_cast<int32>(ServerWorld->GetNetMode()), static_cast<int32>(NM_DedicatedServer));

			const TArray<AAstralEnemySpawner*> Spawners = SpawnersIn(ServerWorld);
			if (!Test.TestEqual(TEXT("S5: RaidMap has one spawner on the server"), Spawners.Num(), 1) || !Test.TestTrue(TEXT("a client seat exists"), PickNearAndFar(*Ctx)))
			{
				Ctx->bAborted = true;
				return;
			}
			AAstralEnemySpawner* Spawner = Spawners[0];
			ListenTo(*Ctx, Spawner);
			Ctx->ExpectedEnemies = Spawner->SpawnPoints.Num();

			// 서버 전용 — 시임리스 이동으로 온 월드에서도 클라이언트에는 스포너도 서브시스템도 없다
			Test.TestNotNull(TEXT("S5: the spawn subsystem exists on the server after the seamless travel"), ServerWorld->GetSubsystem<UAstralEnemySpawnSubsystem>());
			for (UWorld* ClientWorld : GetClientWorlds())
			{
				Test.TestEqual(TEXT("S5: the map's spawner is not loaded on a client"), SpawnersIn(ClientWorld).Num(), 0);
				Test.TestNull(TEXT("S5: no spawn subsystem on a client after the seamless travel"), ClientWorld->GetSubsystem<UAstralEnemySpawnSubsystem>());
			}

			double NearestHero = TNumericLimits<double>::Max();
			const FBox TriggerBounds = Spawner->GetTriggerBox()->Bounds.GetBox();
			for (const int32 PlayerId : { Ctx->NearId, Ctx->FarId })
			{
				const AAstralCharacter* Pawn = PawnIn(ServerWorld, PlayerId);
				MakeHeroSturdy(Pawn);
				if (Pawn)
				{
					NearestHero = FMath::Min(NearestHero, FMath::Sqrt(TriggerBounds.ComputeSquaredDistanceToPoint(Pawn->GetActorLocation())));
				}
			}
			Note(Test, FString::Printf(TEXT("S5: RaidMap spawner %s at %s, box extent %s, %d spawn point(s), enemy class %s, nearest hero %.0f cm from the box on arrival"),
				*Spawner->GetName(), *Spawner->GetActorLocation().ToCompactString(), *Spawner->GetTriggerBox()->GetScaledBoxExtent().ToCompactString(),
				Spawner->SpawnPoints.Num(), *GetNameSafe(Spawner->EnemyClass.Get()), NearestHero));

			Test.TestTrue(TEXT("S5: the map's spawner spawns guardians"), Ctx->ExpectedEnemies > 0 && Spawner->EnemyClass && Spawner->EnemyClass->GetName().StartsWith(GuardianName));
			Test.TestFalse(TEXT("S5 / D-0b: arriving in RaidMap does not activate the spawner"), Spawner->HasActivated());
		});
		Hold(Ctx, 2.0);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			if (!Test.TestTrue(TEXT("the map's spawner is still there"), Ctx->Spawner.IsValid()))
			{
				Ctx->bAborted = true;
				return;
			}
			Test.TestFalse(TEXT("S5 / D-0b: still not activated 2 s after arrival"), Ctx->Spawner->HasActivated());
			Test.TestTrue(TEXT("S5: no guardian anywhere while the heroes stay at the start"), GuardianCountIs(0));

			// S5 뒤 절반 — 히어로가 구역에 들어선다
			MoveHeroIntoBox(*Ctx);
			Test.TestTrue(TEXT("S5: the spawner activates inside the move that puts the hero in the box (overlap event)"), Ctx->Spawner->HasActivated());
		});
		EnqueueWaitSpawned(Ctx, TEXT("RaidMap"));
		EnqueueKillAll(Ctx, TEXT("RaidMap"));
		Do(Ctx, [Ctx]() { Ctx->Listener.Reset(); });
		EndPie(Ctx);
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemySpawnerListenPieTest, "AstralBreak.Net.EnemySpawner.ListenPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralEnemySpawnerListenPieTest::RunTest(const FString& Parameters)
{
	AstralEnemySpawnerPie::EnqueueCombatMap(*this, /*bDedicated=*/false);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemySpawnerDedicatedPieTest, "AstralBreak.Net.EnemySpawner.DedicatedPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralEnemySpawnerDedicatedPieTest::RunTest(const FString& Parameters)
{
	AstralEnemySpawnerPie::EnqueueCombatMap(*this, /*bDedicated=*/true);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemySpawnerRaidMapPieTest, "AstralBreak.Net.EnemySpawner.RaidMapPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralEnemySpawnerRaidMapPieTest::RunTest(const FString& Parameters)
{
	AstralEnemySpawnerPie::EnqueueRaidMap(*this);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
