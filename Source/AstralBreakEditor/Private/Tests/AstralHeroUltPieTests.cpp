// M4 단위 A 오의 시험 — 한 프로세스 멀티 PIE (설계 Docs/Design/m4-ult-chain.md §6 단위 A)
//
// 리슨 서버 · Dedicated 를 PIE 로 띄워 CombatTestMap 에서 클라이언트 자리의 히어로가 오의를 쓴다.
// 입력은 클라이언트 ASC 의 입력 태그(InputTag.Ult)로 넣고 — 실제 예측 발동 · 서버 RPC 를 탄다 — 서버 ASC 와 클라이언트 ASC 를 직접 본다.
//
//   U1  게이지가 가득이 아니면 발동하지 않는다
//   U2  FillUlt(클라이언트 Exec → 서버 RPC)로 게이지가 최대가 되고 클라이언트에 온다
//   U3  발동 — 서버에 오의 중 · 무적 태그, 게이지 0(클라이언트에도), 오의 중 피해 무효, 끝난 뒤에는 피해가 들어간다
//   U4  차단 태그가 있으면 게이지가 가득이어도 발동하지 않는다. 풀면 발동한다
//   U5  오의가 앞의 적에게 피해를 준다 (U4 끝의 발동으로 본다)
//
// 값(피해 · 스윕 범위 · 몽타주)은 GA_Hero_Ult BP 의 것이고 전부 잠정이다 — 이 시험은 값이 아니라 규칙을 본다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AstralPieTestHelpers.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Character/Enemy/AstralCombatCharacter.h"
#include "Engine/GameInstance.h"
#include "EngineUtils.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerState.h"
#include "GameplayTagContainer.h"
#include "Player/AstralPlayerController.h"

namespace AstralHeroUltPie
{
	using namespace AstralPieTest;

	const TCHAR* const MapPath = TEXT("/Game/Maps/CombatTestMap");
	const TCHAR* const MapName = TEXT("CombatTestMap");
	const TCHAR* const EnemyClassPrefix = TEXT("BP_Enemy_Melee");

	// 태그는 런타임 모듈이 내보내지 않는다 — 이름으로 찾는다
	const TCHAR* const UltInputTagName = TEXT("InputTag.Ult");
	const TCHAR* const UltActiveTagName = TEXT("State.Ult.Active");
	const TCHAR* const UltBlockedTagName = TEXT("State.Ult.Blocked");
	const TCHAR* const InvulnerableTagName = TEXT("State.Invulnerable");

	// CombatTestMap 좌표 — 맵의 더미(x < 0)와 떨어진 NavMesh 위 (AstralEnemyCombatPieTests 와 같은 자리)
	const FVector UserLocation(1100.0, -400.0, 92.0);
	const FVector OtherLocation(1100.0, 900.0, 92.0);
	constexpr float EnemySpawnDistance = 250.f;

	struct FContext : FContextBase
	{
		bool bDedicated = false;
		int32 NumPlayers = 2;

		/** 오의를 쓰는 사람 = 클라이언트 자리의 플레이어. 입력 · 디버그 명령이 실제 넷 드라이버를 탄다 */
		int32 UserId = 0;
		int32 OtherId = 0;

		TWeakObjectPtr<AAstralCombatCharacter> Enemy;
		float EnemyHealthBefore = 0.f;
		float MaxGauge = 0.f;
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

	/** 서버가 보는 오의 사용자의 ASC */
	UAbilitySystemComponent* ServerASC(const FContext& Ctx)
	{
		const AAstralCharacter* Pawn = PawnIn(FindServerWorld(), Ctx.UserId);
		return Pawn ? Pawn->GetAbilitySystemComponent() : nullptr;
	}

	/** 오의 사용자 자기 자리(클라이언트)의 ASC — 입력을 넣는 곳 */
	UAstralAbilitySystemComponent* SeatASC(const FContext& Ctx)
	{
		const AAstralPlayerController* PC = Cast<AAstralPlayerController>(GetLocalPC(FindSeatWorld(Ctx.UserId)));
		return PC ? PC->GetAstralAbilitySystemComponent() : nullptr;
	}

	float GaugeOf(const UAbilitySystemComponent* ASC)
	{
		return ASC ? ASC->GetNumericAttribute(UAstralHeroResourceSet::GetUltGaugeAttribute()) : -1.f;
	}

	bool HasTag(const UAbilitySystemComponent* ASC, const TCHAR* TagName)
	{
		return ASC && ASC->HasMatchingGameplayTag(FGameplayTag::RequestGameplayTag(TagName));
	}

	FString Describe(const FContext& Ctx)
	{
		const UWorld* ServerWorld = FindServerWorld();
		const UAbilitySystemComponent* Server = ServerASC(Ctx);
		return FString::Printf(TEXT("server map '%s', seats %d, user %d hp %.0f, gauge server %.1f seat %.1f, server tags active %d invulnerable %d blocked %d, enemy %s hp %.0f"),
			*MapOf(ServerWorld), GetSeatWorlds().Num(), Ctx.UserId, HealthOf(PawnIn(ServerWorld, Ctx.UserId)),
			GaugeOf(Server), GaugeOf(SeatASC(Ctx)),
			HasTag(Server, UltActiveTagName) ? 1 : 0, HasTag(Server, InvulnerableTagName) ? 1 : 0, HasTag(Server, UltBlockedTagName) ? 1 : 0,
			Ctx.Enemy.IsValid() ? *Ctx.Enemy->GetName() : TEXT("none"), HealthOf(Ctx.Enemy.Get()));
	}

	void Wait(const TSharedRef<FContext>& Ctx, const TCHAR* What, double TimeoutSeconds, TFunction<bool()> Condition)
	{
		WaitUntil(Ctx, What, TimeoutSeconds, MoveTemp(Condition), [Ctx]() { return Describe(*Ctx); });
	}

	/** 클라이언트 자리에서 오의 입력을 눌렀다 뗀다 */
	void PressUlt(const TSharedRef<FContext>& Ctx)
	{
		Do(Ctx, [Ctx]()
		{
			UAstralAbilitySystemComponent* ASC = SeatASC(*Ctx);
			if (!Ctx->Test->TestNotNull(TEXT("user's ASC on its own seat"), ASC))
			{
				Ctx->bAborted = true;
				return;
			}
			ASC->AbilityInputTagPressed(FGameplayTag::RequestGameplayTag(UltInputTagName));
		});
		Hold(Ctx, 0.1);
		Do(Ctx, [Ctx]()
		{
			if (UAstralAbilitySystemComponent* ASC = SeatASC(*Ctx))
			{
				ASC->AbilityInputTagReleased(FGameplayTag::RequestGameplayTag(UltInputTagName));
			}
		});
	}

	// ─── 단계 ───

	void EnqueueSetup(const TSharedRef<FContext>& Ctx)
	{
		RequestPie(Ctx, MapPath, Ctx->bDedicated ? PIE_Client : PIE_ListenServer, Ctx->NumPlayers);
		Wait(Ctx, TEXT("every player has a living pawn on the server and on its own seat"), 240.0, [Ctx]()
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
		});

		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			Test.TestEqual(TEXT("server net mode"), static_cast<int32>(ServerWorld->GetNetMode()), static_cast<int32>(Ctx->bDedicated ? NM_DedicatedServer : NM_ListenServer));

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
			Ctx->UserId = ClientIds[0];
			for (const int32 PlayerId : AllIds)
			{
				if (PlayerId != Ctx->UserId)
				{
					Ctx->OtherId = PlayerId;
				}
			}

			AAstralCharacter* UserPawn = PawnIn(ServerWorld, Ctx->UserId);
			AAstralCharacter* OtherPawn = PawnIn(ServerWorld, Ctx->OtherId);
			if (!Test.TestNotNull(TEXT("user hero pawn"), UserPawn) || !Test.TestNotNull(TEXT("other hero pawn"), OtherPawn))
			{
				Ctx->bAborted = true;
				return;
			}

			// 서버에서 자리를 잡는다. 둘 다 +X 를 본다 — 적은 나중에 사용자의 정면에 나온다
			UserPawn->TeleportTo(UserLocation, FRotator::ZeroRotator);
			OtherPawn->TeleportTo(OtherLocation, FRotator::ZeroRotator);

			const UAbilitySystemComponent* Server = ServerASC(*Ctx);
			Ctx->MaxGauge = Server ? Server->GetNumericAttribute(UAstralHeroResourceSet::GetMaxUltGaugeAttribute()) : 0.f;
			Test.TestTrue(TEXT("the hero has an ult gauge with a positive max"), Ctx->MaxGauge > 0.f);
			Note(Test, FString::Printf(TEXT("setup: %s, user id %d, other id %d, max gauge %.0f, gauge %.1f"),
				Ctx->bDedicated ? TEXT("dedicated") : TEXT("listen"), Ctx->UserId, Ctx->OtherId, Ctx->MaxGauge, GaugeOf(Server)));
		});
		Hold(Ctx, 1.0);
	}

	void EnqueueNotFull(const TSharedRef<FContext>& Ctx)
	{
		// U1 — 게이지가 가득이 아니면 발동하지 않는다
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestTrue(TEXT("U1: the gauge starts below max"), GaugeOf(ServerASC(*Ctx)) < Ctx->MaxGauge);
		});
		PressUlt(Ctx);
		Hold(Ctx, 0.7);
		Do(Ctx, [Ctx]()
		{
			const UAbilitySystemComponent* Server = ServerASC(*Ctx);
			Ctx->Test->TestFalse(TEXT("U1: no ult on the server without a full gauge"), HasTag(Server, UltActiveTagName));
			Ctx->Test->TestFalse(TEXT("U1: no ult on the user's seat without a full gauge"), HasTag(SeatASC(*Ctx), UltActiveTagName));
		});
	}

	void EnqueueFill(const TSharedRef<FContext>& Ctx, const TCHAR* Label)
	{
		// 클라이언트의 디버그 명령 — Exec → 서버 RPC
		Do(Ctx, [Ctx]()
		{
			AAstralCharacter* ClientPawn = PawnIn(FindSeatWorld(Ctx->UserId), Ctx->UserId);
			if (!Ctx->Test->TestNotNull(TEXT("user hero pawn on its own client"), ClientPawn))
			{
				Ctx->bAborted = true;
				return;
			}
			Ctx->Test->TestFalse(TEXT("FillUlt is called on a client (no authority)"), ClientPawn->HasAuthority());
			ClientPawn->FillUlt();
		});
		Wait(Ctx, Label, 10.0, [Ctx]()
		{
			return FMath::IsNearlyEqual(GaugeOf(ServerASC(*Ctx)), Ctx->MaxGauge, 0.01f) && FMath::IsNearlyEqual(GaugeOf(SeatASC(*Ctx)), Ctx->MaxGauge, 0.01f);
		});
	}

	void EnqueueUlt(const TSharedRef<FContext>& Ctx)
	{
		// U2 — 채운다
		EnqueueFill(Ctx, TEXT("U2: FillUlt fills the gauge on the server and it replicates to the user's seat"));

		// U3 — 발동
		PressUlt(Ctx);
		Wait(Ctx, TEXT("U3: the ult is active on the server"), 5.0, [Ctx]() { return HasTag(ServerASC(*Ctx), UltActiveTagName); });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			const UAbilitySystemComponent* Server = ServerASC(*Ctx);
			AAstralCharacter* ServerPawn = PawnIn(ServerWorld, Ctx->UserId);

			Test.TestTrue(TEXT("U3: invulnerable while the ult is active"), HasTag(Server, InvulnerableTagName));
			Test.TestTrue(TEXT("U3: the ult spends the whole gauge on the server"), FMath::IsNearlyZero(GaugeOf(Server), 0.01f));

			// 오의 중 피해 — 서버에서 정식 데미지 파이프라인으로 넣는다. 한 호출 안에서 끝나므로 앞뒤 값을 그대로 비교한다
			const float Before = HealthOf(ServerPawn);
			ServerPawn->DamageSelf(30.f);
			Test.TestEqual(TEXT("U3: damage during the ult is ignored"), HealthOf(ServerPawn), Before);
			Note(Test, FString::Printf(TEXT("U3: active — server gauge %.1f, hp %.0f -> %.0f after 30 damage"), GaugeOf(Server), Before, HealthOf(ServerPawn)));
		});
		Wait(Ctx, TEXT("U3: the spent gauge replicates to the user's seat"), 5.0, [Ctx]() { return FMath::IsNearlyZero(GaugeOf(SeatASC(*Ctx)), 0.01f); });
		Wait(Ctx, TEXT("U3: the ult ends on the server and on the user's seat"), 15.0, [Ctx]()
		{
			return !HasTag(ServerASC(*Ctx), UltActiveTagName) && !HasTag(SeatASC(*Ctx), UltActiveTagName);
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			AAstralCharacter* ServerPawn = PawnIn(FindServerWorld(), Ctx->UserId);
			Test.TestFalse(TEXT("U3: not invulnerable after the ult"), HasTag(ServerASC(*Ctx), InvulnerableTagName));

			const float Before = HealthOf(ServerPawn);
			ServerPawn->DamageSelf(10.f);
			Test.TestTrue(TEXT("U3: damage after the ult lands"), HealthOf(ServerPawn) < Before);
			Note(Test, FString::Printf(TEXT("U3: ended — hp %.0f -> %.0f after 10 damage"), Before, HealthOf(ServerPawn)));
		});
	}

	void EnqueueBlockedThenHit(const TSharedRef<FContext>& Ctx)
	{
		// U4 — 차단 태그. 클라이언트의 디버그 명령이 자기 쪽과 서버 양쪽에 건다
		Do(Ctx, [Ctx]()
		{
			if (AAstralCharacter* ClientPawn = PawnIn(FindSeatWorld(Ctx->UserId), Ctx->UserId))
			{
				ClientPawn->SetUltBlocked(true);
			}
		});
		Wait(Ctx, TEXT("U4: the block tag is on the server and on the user's seat"), 5.0, [Ctx]()
		{
			return HasTag(ServerASC(*Ctx), UltBlockedTagName) && HasTag(SeatASC(*Ctx), UltBlockedTagName);
		});
		EnqueueFill(Ctx, TEXT("U4: the gauge is full again"));
		PressUlt(Ctx);
		Hold(Ctx, 0.7);
		Do(Ctx, [Ctx]()
		{
			const UAbilitySystemComponent* Server = ServerASC(*Ctx);
			Ctx->Test->TestFalse(TEXT("U4: a blocked ult does not start on the server"), HasTag(Server, UltActiveTagName));
			Ctx->Test->TestFalse(TEXT("U4: a blocked ult does not start on the user's seat"), HasTag(SeatASC(*Ctx), UltActiveTagName));
			Ctx->Test->TestTrue(TEXT("U4: a blocked ult keeps the gauge"), FMath::IsNearlyEqual(GaugeOf(Server), Ctx->MaxGauge, 0.01f));
		});

		// 적을 사용자 정면에 부른 뒤 차단을 푼다 — 풀린 뒤의 발동이 U4 의 뒷부분이자 U5 다
		Do(Ctx, [Ctx]()
		{
			AAstralCharacter* ClientPawn = PawnIn(FindSeatWorld(Ctx->UserId), Ctx->UserId);
			if (!ClientPawn)
			{
				return;
			}
			Ctx->Test->TestEqual(TEXT("U5: no enemy before SpawnEnemy"), EnemiesIn(FindServerWorld()).Num(), 0);
			ClientPawn->SpawnEnemy(FString(), EnemySpawnDistance);
			ClientPawn->SetUltBlocked(false);
		});
		Wait(Ctx, TEXT("U5: the enemy is on the server and the block tag is gone"), 30.0, [Ctx]()
		{
			const TArray<AAstralCombatCharacter*> ServerEnemies = EnemiesIn(FindServerWorld());
			if (ServerEnemies.Num() != 1 || HasTag(ServerASC(*Ctx), UltBlockedTagName) || HasTag(SeatASC(*Ctx), UltBlockedTagName))
			{
				return false;
			}
			Ctx->Enemy = ServerEnemies[0];
			return true;
		});
		Do(Ctx, [Ctx]()
		{
			Ctx->EnemyHealthBefore = HealthOf(Ctx->Enemy.Get());

			// 클라이언트 쪽 몸 · 시점을 적 쪽으로 — 스윕은 서버가 보는 아바타의 정면이고, 그 방향은 클라이언트의 이동이 정한다
			AAstralCharacter* ClientPawn = PawnIn(FindSeatWorld(Ctx->UserId), Ctx->UserId);
			APlayerController* PC = GetLocalPC(FindSeatWorld(Ctx->UserId));
			if (ClientPawn && PC && Ctx->Enemy.IsValid())
			{
				const FRotator Facing = (Ctx->Enemy->GetActorLocation() - ClientPawn->GetActorLocation()).GetSafeNormal2D().Rotation();
				ClientPawn->SetActorRotation(Facing);
				PC->SetControlRotation(Facing);
			}
		});
		Hold(Ctx, 0.3);
		PressUlt(Ctx);
		Wait(Ctx, TEXT("U4: once unblocked the ult starts on the server"), 5.0, [Ctx]() { return HasTag(ServerASC(*Ctx), UltActiveTagName); });
		Wait(Ctx, TEXT("U5: the ult ends"), 15.0, [Ctx]() { return !HasTag(ServerASC(*Ctx), UltActiveTagName); });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const bool bGone = !Ctx->Enemy.IsValid();
			const float EnemyHealth = bGone ? 0.f : HealthOf(Ctx->Enemy.Get());
			Test.TestTrue(TEXT("U5: the ult damaged the enemy in front"), bGone || IsDead(Ctx->Enemy.Get()) || EnemyHealth < Ctx->EnemyHealthBefore);
			Note(Test, FString::Printf(TEXT("U5: enemy hp %.0f -> %.0f%s"), Ctx->EnemyHealthBefore, EnemyHealth, (bGone || IsDead(Ctx->Enemy.Get())) ? TEXT(" (dead)") : TEXT("")));
		});
	}

	void EnqueueAll(FAutomationTestBase& Test, bool bDedicated)
	{
		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;
		Ctx->bDedicated = bDedicated;

		EnqueueSetup(Ctx);
		EnqueueNotFull(Ctx);
		EnqueueUlt(Ctx);
		EnqueueBlockedThenHit(Ctx);
		EndPie(Ctx);
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralHeroUltListenPieTest, "AstralBreak.Net.HeroUlt.ListenPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralHeroUltListenPieTest::RunTest(const FString& Parameters)
{
	AstralHeroUltPie::EnqueueAll(*this, /*bDedicated=*/false);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralHeroUltDedicatedPieTest, "AstralBreak.Net.HeroUlt.DedicatedPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralHeroUltDedicatedPieTest::RunTest(const FString& Parameters)
{
	AstralHeroUltPie::EnqueueAll(*this, /*bDedicated=*/true);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
