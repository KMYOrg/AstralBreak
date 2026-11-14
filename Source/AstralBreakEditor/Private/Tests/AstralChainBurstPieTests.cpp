// M4 단위 B + B 다듬기 체인 버스트 시험 — 한 프로세스 멀티 PIE 4인 (설계 Docs/Design/m4-ult-chain.md §3 · §3 끝 'B 다듬기' · §6)
//
// 리슨 서버 · Dedicated 를 PIE 로 띄워 CombatTestMap 에서 네 사람이 한 명씩 차례로 오의를 쓴다. 한 세션 안에서 1명 → 2명(+ 헛친 한 명) → 3명 → 4명 순서다.
// 입력은 각자 자기 자리의 ASC 에 입력 태그(InputTag.Ult)로 넣고 — 실제 예측 발동 · 서버 RPC 를 탄다 — 서버의 체인 컴포넌트와 자리마다 복제된 상태를 직접 본다.
//
//   C1  한 명만 맞힌다 → 오의가 끝난 시각에 체인이 열리고, 마감 + 유예 뒤 조용히 닫힌다 — 버스트 없음
//   C2  맞힘 → 헛침 → 맞힘. 헛친 사람은 최대치 × MissRefundRatio 를 돌려받고 체인 · 팀 게이지가 없으며, 멈춘 타이머가 남아 있던 시간으로 다시 돈다.
//       버스트는 맞힌 2명. 둘째 참가자의 ChainBurstDamageMultiplier 를 2.0 으로 올려 '자기 몫에만 곱' 을 적 HP 로 잰다
//   C3  3명 — 버스트 3명
//   C4  4명 — 넷째가 끝난 시각에 전원이 차 바로 닫히고 버스트가 나간다
//   오의마다 — 쓰는 동안: 체인 상태에 시전자 · 나머지는 차단 태그(서버 · 자기 자리) · 열린 체인의 타이머 멈춤 · 팀 게이지 아직 없음.
//              끝난 뒤(맞힘): 차단 해제 · 그 시각으로 등록(마감 = 끝난 시각 + 윈도우) · 본인 0 · 나머지 + TeamUltGain
//   공통 — 버스트로는 게이지가 차지 않는다, 복제된 상태가 자리마다 서버와 같다
//
// 적은 시험이 서버에서 직접 세운다: AI 컨트롤러를 떼고(제자리에 선다) HP 를 크게 올린다. 히어로 넷이 적을 둘러싸고 적을 본다 —
// 맞혀야 체인에 들기 때문이다. 적 HP 감소 = 맞힌 오의의 피해 + 버스트 피해이고, 헛치는 사람만 적을 등진다.
// 값(윈도우 · 유예 · 피해 · 배수 · 반환 비율)은 컴포넌트 · 어빌리티의 프로퍼티이고 전부 잠정이다 — 시험은 프로퍼티 · 서버 보고에서 읽어 규칙만 본다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AstralPieTestHelpers.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Abilities/Hero/Combat/AstralGA_Hero_Ult.h"
#include "AbilitySystem/Attributes/AstralCombatSet.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Character/Enemy/AstralCombatCharacter.h"
#include "Character/Enemy/AstralEnemySpawnSubsystem.h"
#include "Engine/GameInstance.h"
#include "GameFramework/Controller.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerState.h"
#include "GameModes/AstralChainBurstComponent.h"
#include "GameplayTagContainer.h"
#include "Player/AstralPlayerController.h"

namespace AstralChainBurstPie
{
	using namespace AstralPieTest;

	const TCHAR* const MapPath = TEXT("/Game/Maps/CombatTestMap");
	const TCHAR* const MapName = TEXT("CombatTestMap");
	const TCHAR* const EnemyClassPath = TEXT("/Game/Characters/Enemy/BP_Enemy_Melee.BP_Enemy_Melee_C");

	// 태그는 런타임 모듈이 내보내지 않는다 — 이름으로 찾는다
	const TCHAR* const UltInputTagName = TEXT("InputTag.Ult");
	const TCHAR* const UltActiveTagName = TEXT("State.Ult.Active");
	const TCHAR* const UltBlockedTagName = TEXT("State.Ult.Blocked");

	// CombatTestMap 좌표 — 맵의 더미(x < 0)와 떨어진 자리. 적을 가운데 두고 히어로 넷이 250 cm 거리에서 적을 본다(오의 스윕 = 앞 50 ~ 450, 반경 150)
	constexpr int32 NumPlayers = 4;
	const FVector EnemyLocation(1100.0, 250.0, 92.0);
	const FVector HeroLocations[NumPlayers] = { FVector(1350.0, 250.0, 92.0), FVector(850.0, 250.0, 92.0), FVector(1100.0, 500.0, 92.0), FVector(1100.0, 0.0, 92.0) };
	const float HeroFacingYaws[NumPlayers] = { 180.f, 0.f, -90.f, 90.f };
	constexpr float SturdyHealth = 100000.f;
	constexpr float BoostedMultiplier = 2.f;

	/** 체인 안의 오의 한 번 — 누가(Ids 의 인덱스), 맞히는가 */
	struct FUltStep
	{
		int32 UserIndex = 0;
		bool bHit = true;
	};

	struct FContext : FContextBase
	{
		bool bDedicated = false;

		/** PlayerId 오름차순 — 리슨에서는 [0] 이 호스트다 */
		TArray<int32> Ids;

		TWeakObjectPtr<AAstralCombatCharacter> Enemy;
		float MaxGauge = 0.f;

		/** 오의 어빌리티의 잠정값 */
		float UltBaseDamage = 0.f;
		float MissRefundRatio = 0.f;

		// ─── 체인 하나를 도는 동안의 값 ───
		int32 ChainIdBefore = 0;
		int32 BurstIdBefore = 0;
		float EnemyHealthBefore = 0.f;
		TArray<int32> Expected;

		/** 이 체인에서 맞힌 오의들이 적에게 넣었어야 할 피해의 합 */
		float ExpectedUltDamage = 0.f;

		/** 마지막으로 본 마감(서버 시각) — 조용히 닫힘 · 버스트까지 걸린 시간의 기준 */
		double LastDeadline = 0.0;

		// ─── 오의 한 번을 도는 동안의 값 ───
		TMap<int32, float> Gauges;
		FAstralChainState StateBeforeCast;
		float RemainingBeforeCast = 0.f;
		float PausedRemaining = 0.f;
		float EnemyHealthBeforeCast = 0.f;

		/** 인원 → 서버가 보고한 총 피해 (인원이 늘수록 커야 한다) */
		TMap<int32, float> TotalByCount;
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

	/** 서버가 보는 그 플레이어의 ASC */
	UAbilitySystemComponent* ServerASC(int32 PlayerId)
	{
		const AAstralCharacter* Pawn = PawnIn(FindServerWorld(), PlayerId);
		return Pawn ? Pawn->GetAbilitySystemComponent() : nullptr;
	}

	/** 그 플레이어 자기 자리의 ASC — 입력을 넣는 곳 (리슨 호스트는 서버의 것과 같다) */
	UAstralAbilitySystemComponent* SeatASC(int32 PlayerId)
	{
		const AAstralPlayerController* PC = Cast<AAstralPlayerController>(GetLocalPC(FindSeatWorld(PlayerId)));
		return PC ? PC->GetAstralAbilitySystemComponent() : nullptr;
	}

	float AttributeOf(const UAbilitySystemComponent* ASC, const FGameplayAttribute& Attribute, float Fallback = -1.f)
	{
		return (ASC && ASC->HasAttributeSetForAttribute(Attribute)) ? ASC->GetNumericAttribute(Attribute) : Fallback;
	}

	float GaugeOf(const UAbilitySystemComponent* ASC)
	{
		return AttributeOf(ASC, UAstralHeroResourceSet::GetUltGaugeAttribute());
	}

	bool HasTag(const UAbilitySystemComponent* ASC, const TCHAR* TagName)
	{
		return ASC && ASC->HasMatchingGameplayTag(FGameplayTag::RequestGameplayTag(TagName));
	}

	UAstralChainBurstComponent* ChainIn(const UWorld* World)
	{
		return World ? UAstralChainBurstComponent::FindChainBurstComponent(World) : nullptr;
	}

	UAstralChainBurstComponent* ServerChain()
	{
		return ChainIn(FindServerWorld());
	}

	FAstralChainState ServerState()
	{
		const UAstralChainBurstComponent* Chain = ServerChain();
		return Chain ? Chain->GetChainState() : FAstralChainState();
	}

	double ServerNow()
	{
		const UWorld* ServerWorld = FindServerWorld();
		const AGameStateBase* GameState = ServerWorld ? ServerWorld->GetGameState() : nullptr;
		return GameState ? GameState->GetServerWorldTimeSeconds() : 0.0;
	}

	/** 컴포넌트의 잠정값 — 프로퍼티가 protected 라 이름으로 읽는다 */
	float FloatProperty(const UObject* Object, const TCHAR* Name)
	{
		const FFloatProperty* Property = Object ? FindFProperty<FFloatProperty>(Object->GetClass(), Name) : nullptr;
		return Property ? Property->GetPropertyValue_InContainer(Object) : 0.f;
	}

	/** 부여된 오의 어빌리티(BP 의 CDO)의 잠정값. 없으면 -1 */
	float UltAbilityFloat(const UAbilitySystemComponent* ASC, const TCHAR* Name)
	{
		if (ASC)
		{
			for (const FGameplayAbilitySpec& Spec : ASC->GetActivatableAbilities())
			{
				const UGameplayAbility* Ability = Spec.Ability;
				if (Ability && Ability->IsA(UAstralGA_Hero_Ult::StaticClass()))
				{
					const FFloatProperty* Property = FindFProperty<FFloatProperty>(Ability->GetClass(), Name);
					return Property ? Property->GetPropertyValue_InContainer(Ability) : -1.f;
				}
			}
		}
		return -1.f;
	}

	/** 그 사람의 오의 한 방이 적에게 넣는 피해 = 오의 기본 피해 × 자기 OutgoingDamageMultiplier × 적 IncomingDamageMultiplier */
	float UltDamageBy(const FContext& Ctx, int32 PlayerId)
	{
		const float Outgoing = AttributeOf(ServerASC(PlayerId), UAstralCombatSet::GetOutgoingDamageMultiplierAttribute(), 1.f);
		const float Incoming = Ctx.Enemy.IsValid() ? AttributeOf(Ctx.Enemy->GetAbilitySystemComponent(), UAstralHealthSet::GetIncomingDamageMultiplierAttribute(), 1.f) : 1.f;
		return Ctx.UltBaseDamage * Outgoing * Incoming;
	}

	/** 복제된 체인 상태가 모든 클라이언트 자리에서 서버와 같은가 */
	bool ClientsMatchServer()
	{
		const UAstralChainBurstComponent* Server = ServerChain();
		if (!Server)
		{
			return false;
		}
		for (const UWorld* SeatWorld : GetSeatWorlds())
		{
			if (SeatWorld->GetNetMode() != NM_Client)
			{
				continue;
			}
			const UAstralChainBurstComponent* Client = ChainIn(SeatWorld);
			if (!Client || Client->GetChainState() != Server->GetChainState())
			{
				return false;
			}
		}
		return true;
	}

	FString Describe(const FContext& Ctx)
	{
		const UAstralChainBurstComponent* Server = ServerChain();
		FString Gauges;
		for (const int32 PlayerId : Ctx.Ids)
		{
			const UAbilitySystemComponent* ASC = ServerASC(PlayerId);
			Gauges += FString::Printf(TEXT(" %d:%.0f%s%s"), PlayerId, GaugeOf(ASC), HasTag(ASC, UltActiveTagName) ? TEXT("*") : TEXT(""), HasTag(ASC, UltBlockedTagName) ? TEXT("x") : TEXT(""));
		}
		int32 NumMatching = 0;
		int32 NumClients = 0;
		for (const UWorld* SeatWorld : GetSeatWorlds())
		{
			if (SeatWorld->GetNetMode() == NM_Client)
			{
				++NumClients;
				const UAstralChainBurstComponent* Client = ChainIn(SeatWorld);
				NumMatching += (Server && Client && Client->GetChainState() == Server->GetChainState()) ? 1 : 0;
			}
		}
		return FString::Printf(TEXT("server map '%s' t %.2f, chain [%s], clients matching %d/%d, gauges(*ult xblocked)%s, enemy hp %.1f"),
			*MapOf(FindServerWorld()), ServerNow(), Server ? *Server->GetDebugString() : TEXT("no component"), NumMatching, NumClients, *Gauges,
			HealthOf(Ctx.Enemy.Get()));
	}

	void Wait(const TSharedRef<FContext>& Ctx, const FString& What, double TimeoutSeconds, TFunction<bool()> Condition)
	{
		WaitUntil(Ctx, *What, TimeoutSeconds, MoveTemp(Condition), [Ctx]() { return Describe(*Ctx); });
	}

	void SnapshotGauges(FContext& Ctx)
	{
		Ctx.Gauges.Reset();
		for (const int32 PlayerId : Ctx.Ids)
		{
			Ctx.Gauges.Add(PlayerId, GaugeOf(ServerASC(PlayerId)));
		}
	}

	// ─── 조작 ───

	/**
	 * 몸 · 시점을 돌린다 — 서버의 폰과 자기 자리의 폰 · 컨트롤 회전을 함께.
	 * 스윕은 서버가 보는 아바타의 정면이다. 서 있는 폰의 방향은 서버가 자기 쪽에서 따로 갖고 있어서, 자기 자리에서만 돌리면 서버의 폰은 그대로다
	 * (실측 — 클라이언트에서만 돌린 '헛치는 사람' 이 서버에서는 적을 맞혔다)
	 */
	void Face(const TSharedRef<FContext>& Ctx, int32 Index, bool bAway)
	{
		Do(Ctx, [Ctx, Index, bAway]()
		{
			const FRotator Facing(0.0, HeroFacingYaws[Index] + (bAway ? 180.f : 0.f), 0.0);
			if (AAstralCharacter* ServerPawn = PawnIn(FindServerWorld(), Ctx->Ids[Index]))
			{
				ServerPawn->SetActorRotation(Facing);
			}
			UWorld* SeatWorld = FindSeatWorld(Ctx->Ids[Index]);
			AAstralCharacter* SeatPawn = PawnIn(SeatWorld, Ctx->Ids[Index]);
			APlayerController* PC = GetLocalPC(SeatWorld);
			if (SeatPawn && PC)
			{
				SeatPawn->SetActorRotation(Facing);
				PC->SetControlRotation(Facing);
			}
		});
	}

	/** 서버에서 자리를 다시 잡고 모두 적을 본다 — 오의의 루트 모션으로 밀린 만큼을 체인마다 되돌린다 */
	void PlaceHeroes(const TSharedRef<FContext>& Ctx)
	{
		Do(Ctx, [Ctx]()
		{
			UWorld* ServerWorld = FindServerWorld();
			for (int32 Index = 0; Index < Ctx->Ids.Num(); ++Index)
			{
				if (AAstralCharacter* ServerPawn = PawnIn(ServerWorld, Ctx->Ids[Index]))
				{
					ServerPawn->TeleportTo(HeroLocations[Index], FRotator(0.0, HeroFacingYaws[Index], 0.0));
				}
			}
		});
		for (int32 Index = 0; Index < NumPlayers; ++Index)
		{
			Face(Ctx, Index, /*bAway=*/false);
		}
		Hold(Ctx, 0.7);
	}

	/** 자기 자리의 디버그 명령으로 채운다 — 클라이언트는 Exec → 서버 RPC, 리슨 호스트는 바로 */
	void Fill(const TSharedRef<FContext>& Ctx, int32 Index)
	{
		Do(Ctx, [Ctx, Index]()
		{
			const int32 PlayerId = Ctx->Ids[Index];
			AAstralCharacter* SeatPawn = PawnIn(FindSeatWorld(PlayerId), PlayerId);
			if (!Ctx->Test->TestNotNull(TEXT("hero pawn on its own seat"), SeatPawn))
			{
				Ctx->bAborted = true;
				return;
			}
			SeatPawn->FillUlt();
		});
		Wait(Ctx, TEXT("FillUlt fills the gauge on the server and on the user's seat"), 10.0, [Ctx, Index]()
		{
			const int32 PlayerId = Ctx->Ids[Index];
			return FMath::IsNearlyEqual(GaugeOf(ServerASC(PlayerId)), Ctx->MaxGauge, 0.01f) && FMath::IsNearlyEqual(GaugeOf(SeatASC(PlayerId)), Ctx->MaxGauge, 0.01f);
		});
	}

	/** 자기 자리에서 오의 입력을 눌렀다 뗀다 */
	void PressUlt(const TSharedRef<FContext>& Ctx, int32 Index)
	{
		Do(Ctx, [Ctx, Index]()
		{
			UAstralAbilitySystemComponent* ASC = SeatASC(Ctx->Ids[Index]);
			if (!Ctx->Test->TestNotNull(TEXT("user's ASC on its own seat"), ASC))
			{
				Ctx->bAborted = true;
				return;
			}
			ASC->AbilityInputTagPressed(FGameplayTag::RequestGameplayTag(UltInputTagName));
		});
		Hold(Ctx, 0.1);
		Do(Ctx, [Ctx, Index]()
		{
			if (UAstralAbilitySystemComponent* ASC = SeatASC(Ctx->Ids[Index]))
			{
				ASC->AbilityInputTagReleased(FGameplayTag::RequestGameplayTag(UltInputTagName));
			}
		});
	}

	// ─── 단계 ───

	void EnqueueSetup(const TSharedRef<FContext>& Ctx)
	{
		RequestPie(Ctx, MapPath, Ctx->bDedicated ? PIE_Client : PIE_ListenServer, NumPlayers);
		Wait(Ctx, TEXT("every player has a living pawn on the server and on its own seat"), 240.0, []()
		{
			const UWorld* ServerWorld = FindServerWorld();
			const AGameStateBase* GameState = ServerWorld ? ServerWorld->GetGameState() : nullptr;
			if (!ServerWorld || !ServerWorld->HasBegunPlay() || MapOf(ServerWorld) != MapName || !GameState || GameState->PlayerArray.Num() != NumPlayers)
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

			for (const UWorld* SeatWorld : GetSeatWorlds())
			{
				Ctx->Ids.Add(LocalPlayerIdIn(SeatWorld));
			}
			Ctx->Ids.Sort();

			// 체인 컴포넌트 — 레이드 GameState(BP_AstralGameState_Raid 의 부모)가 서버와 모든 자리에 갖고 있어야 한다
			const UAstralChainBurstComponent* Chain = ServerChain();
			if (!Test.TestNotNull(TEXT("chain component on the server's game state"), Chain))
			{
				Ctx->bAborted = true;
				return;
			}
			for (const UWorld* SeatWorld : GetSeatWorlds())
			{
				Test.TestNotNull(TEXT("chain component on every seat's game state"), ChainIn(SeatWorld));
			}
			Test.TestEqual(TEXT("no chain yet"), static_cast<int32>(Chain->GetChainState().Phase), static_cast<int32>(EAstralChainPhase::None));
			Test.TestEqual(TEXT("chain id starts at 0"), Chain->GetChainState().ChainId, 0);
			Test.TestEqual(TEXT("nobody is casting yet"), Chain->GetChainState().CastingPlayerId, 0);

			const UAbilitySystemComponent* FirstASC = ServerASC(Ctx->Ids[0]);
			Ctx->MaxGauge = AttributeOf(FirstASC, UAstralHeroResourceSet::GetMaxUltGaugeAttribute(), 0.f);
			Ctx->UltBaseDamage = UltAbilityFloat(FirstASC, TEXT("BaseDamage"));
			Ctx->MissRefundRatio = UltAbilityFloat(FirstASC, TEXT("MissRefundRatio"));
			Test.TestTrue(TEXT("the hero has an ult gauge with a positive max"), Ctx->MaxGauge > 0.f);
			Test.TestTrue(TEXT("the ult ability has a positive base damage"), Ctx->UltBaseDamage > 0.f);
			Test.TestTrue(TEXT("the ult ability has a miss refund ratio between 0 and 1"), Ctx->MissRefundRatio > 0.f && Ctx->MissRefundRatio < 1.f);

			// 적 — 서버에서 직접 세운다. 컨트롤러를 떼면 트리가 멈추고 제자리에 선다(팀은 폰 자신이 답한다)
			UClass* EnemyClass = StaticLoadClass(APawn::StaticClass(), nullptr, EnemyClassPath, nullptr, LOAD_NoWarn);
			UAstralEnemySpawnSubsystem* SpawnSubsystem = ServerWorld->GetSubsystem<UAstralEnemySpawnSubsystem>();
			if (!Test.TestNotNull(TEXT("enemy class"), EnemyClass) || !Test.TestNotNull(TEXT("enemy spawn subsystem on the server"), SpawnSubsystem))
			{
				Ctx->bAborted = true;
				return;
			}
			AAstralCombatCharacter* Enemy = Cast<AAstralCombatCharacter>(SpawnSubsystem->SpawnEnemy(EnemyClass, FTransform(FRotator::ZeroRotator, EnemyLocation)));
			if (!Test.TestNotNull(TEXT("enemy spawned on the server"), Enemy))
			{
				Ctx->bAborted = true;
				return;
			}
			if (AController* Controller = Enemy->GetController())
			{
				Controller->UnPossess();
			}
			Ctx->Enemy = Enemy;

			Note(Test, FString::Printf(TEXT("setup: %s, ids %d %d %d %d, max gauge %.0f, ult damage %.0f, miss refund %.2f, window %.2f grace %.2f team gain %.1f radius %.0f"),
				Ctx->bDedicated ? TEXT("dedicated") : TEXT("listen"), Ctx->Ids[0], Ctx->Ids[1], Ctx->Ids[2], Ctx->Ids[3], Ctx->MaxGauge, Ctx->UltBaseDamage, Ctx->MissRefundRatio,
				FloatProperty(Chain, TEXT("WindowSeconds")), FloatProperty(Chain, TEXT("GraceSeconds")), FloatProperty(Chain, TEXT("TeamUltGain")), FloatProperty(Chain, TEXT("BurstRadius"))));
		});

		Wait(Ctx, TEXT("the enemy's health set is ready on the server"), 30.0, [Ctx]() { return Ctx->Enemy.IsValid() && HealthOf(Ctx->Enemy.Get()) > 0.f; });
		Do(Ctx, [Ctx]()
		{
			UAbilitySystemComponent* EnemyASC = Ctx->Enemy->GetAbilitySystemComponent();
			if (!Ctx->Test->TestNotNull(TEXT("enemy ASC"), EnemyASC))
			{
				Ctx->bAborted = true;
				return;
			}
			EnemyASC->SetNumericAttributeBase(UAstralHealthSet::GetMaxHealthAttribute(), SturdyHealth);
			EnemyASC->SetNumericAttributeBase(UAstralHealthSet::GetHealthAttribute(), SturdyHealth);
		});
		PlaceHeroes(Ctx);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const float Radius = FloatProperty(ServerChain(), TEXT("BurstRadius"));
			Test.TestEqual(TEXT("the enemy is sturdy"), HealthOf(Ctx->Enemy.Get()), SturdyHealth);
			Test.TestNull(TEXT("the enemy has no controller"), Ctx->Enemy->GetController());
			for (const int32 PlayerId : Ctx->Ids)
			{
				const AAstralCharacter* Pawn = PawnIn(FindServerWorld(), PlayerId);
				const float Distance = Pawn ? FVector::Dist(Pawn->GetActorLocation(), Ctx->Enemy->GetActorLocation()) : -1.f;
				Test.TestTrue(TEXT("the enemy is inside the burst radius of every hero"), Distance > 0.f && Distance < Radius);
				Test.TestTrue(TEXT("every hero faces the enemy"), Pawn && FVector::DotProduct(Pawn->GetActorForwardVector(), (Ctx->Enemy->GetActorLocation() - Pawn->GetActorLocation()).GetSafeNormal2D()) > 0.9);
			}
		});
	}

	/**
	 * 오의 한 번 — 누르고, 쓰는 동안의 규칙(차단 · 타이머 멈춤 · 팀 게이지 없음)과 끝난 뒤의 공통 규칙(차단 해제)을 본다.
	 * 체인 등록 쪽의 기대는 부른 쪽(EnqueueChain)이 본다. 헛치는 오의의 끝난 뒤 규칙(반환 · 등록 없음 · 타이머 재개)은 여기서 본다
	 */
	void EnqueueCast(const TSharedRef<FContext>& Ctx, const FString& Label, const FUltStep& Step)
	{
		const int32 UserIndex = Step.UserIndex;
		const bool bHit = Step.bHit;

		if (!bHit)
		{
			// 적을 등진다 — 스윕에 아무도 걸리지 않는다
			Face(Ctx, UserIndex, /*bAway=*/true);
			Hold(Ctx, 0.4);
		}

		// 앞사람의 오의가 끝나 차단이 자기 자리에서 풀려야 누를 수 있다(예측 발동이 차단 태그를 본다)
		Wait(Ctx, FString::Printf(TEXT("%s: nobody is casting and player index %d is unblocked on its own seat"), *Label, UserIndex), 10.0, [Ctx, UserIndex]()
		{
			const int32 UserId = Ctx->Ids[UserIndex];
			return ServerState().CastingPlayerId == 0 && !HasTag(SeatASC(UserId), UltBlockedTagName) && !HasTag(ServerASC(UserId), UltBlockedTagName)
				&& FMath::IsNearlyEqual(GaugeOf(SeatASC(UserId)), Ctx->MaxGauge, 0.01f);
		});
		Do(Ctx, [Ctx, Label, UserIndex, bHit]()
		{
			SnapshotGauges(*Ctx);
			Ctx->StateBeforeCast = ServerState();
			Ctx->RemainingBeforeCast = ServerChain()->GetRemainingSeconds();
			Ctx->EnemyHealthBeforeCast = HealthOf(Ctx->Enemy.Get());

			// 누르기 직전 서버가 보는 방향 — 맞히는 사람은 적을 보고, 헛치는 사람은 적을 등진다 (스윕은 서버 아바타의 정면이다)
			const AAstralCharacter* ServerPawn = PawnIn(FindServerWorld(), Ctx->Ids[UserIndex]);
			const double Dot = (ServerPawn && Ctx->Enemy.IsValid()) ? FVector::DotProduct(ServerPawn->GetActorForwardVector(), (Ctx->Enemy->GetActorLocation() - ServerPawn->GetActorLocation()).GetSafeNormal2D()) : 0.0;
			if (!Ctx->Test->TestTrue(*FString::Printf(TEXT("%s: on the server, player index %d %s the enemy before pressing (dot %.2f)"), *Label, UserIndex, bHit ? TEXT("faces") : TEXT("has its back to"), Dot), bHit ? Dot > 0.9 : Dot < -0.9))
			{
				Ctx->bAborted = true;
			}
		});
		PressUlt(Ctx, UserIndex);
		Wait(Ctx, FString::Printf(TEXT("%s: the server sees player index %d casting"), *Label, UserIndex), 5.0, [Ctx, UserIndex]()
		{
			return ServerState().CastingPlayerId == Ctx->Ids[UserIndex];
		});

		// ─── 쓰는 동안 ───
		Do(Ctx, [Ctx, Label, UserIndex]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const FAstralChainState State = ServerState();
			const FAstralChainState& Before = Ctx->StateBeforeCast;
			const int32 UserId = Ctx->Ids[UserIndex];

			Test.TestTrue(*FString::Printf(TEXT("%s: the user's ult is active on the server"), *Label), HasTag(ServerASC(UserId), UltActiveTagName));
			Test.TestFalse(*FString::Printf(TEXT("%s: the user is not blocked by its own ult"), *Label), HasTag(ServerASC(UserId), UltBlockedTagName));

			// ① 등록은 끝날 때다 — 쓰는 동안 체인의 참가자 · 번호는 그대로이고, 열려 있던 체인의 타이머는 멈춘다
			Test.TestEqual(*FString::Printf(TEXT("%s: no chain entry while casting (chain id)"), *Label), State.ChainId, Before.ChainId);
			Test.TestEqual(*FString::Printf(TEXT("%s: no chain entry while casting (participants)"), *Label), State.ParticipantIds, Before.ParticipantIds);
			if (Before.Phase == EAstralChainPhase::Open)
			{
				Test.TestTrue(*FString::Printf(TEXT("%s: the open chain's timer is paused while casting"), *Label), State.bTimerPaused);
				Test.TestTrue(*FString::Printf(TEXT("%s: the paused time is what was left when the ult started (%.2f, was %.2f just before)"), *Label, State.PausedRemainingSeconds, Ctx->RemainingBeforeCast),
					State.PausedRemainingSeconds <= Ctx->RemainingBeforeCast + 0.01f && State.PausedRemainingSeconds > Ctx->RemainingBeforeCast - 1.0f);
				Ctx->PausedRemaining = State.PausedRemainingSeconds;
			}
			else
			{
				Test.TestFalse(*FString::Printf(TEXT("%s: nothing to pause without an open chain"), *Label), State.bTimerPaused);
				Ctx->PausedRemaining = 0.f;
			}

			// ② 나머지는 차단된다(서버). ③ 팀 게이지는 아직 없다 — 맞힌 오의가 끝날 때 나간다
			for (const int32 PlayerId : Ctx->Ids)
			{
				const UAbilitySystemComponent* ASC = ServerASC(PlayerId);
				if (PlayerId == UserId)
				{
					Test.TestTrue(*FString::Printf(TEXT("%s: the user spent the whole gauge"), *Label), FMath::IsNearlyZero(GaugeOf(ASC), 0.01f));
				}
				else
				{
					Test.TestTrue(*FString::Printf(TEXT("%s: teammate %d is blocked on the server while the user casts"), *Label, PlayerId), HasTag(ASC, UltBlockedTagName));
					Test.TestTrue(*FString::Printf(TEXT("%s: teammate %d gets no team gauge while the user casts"), *Label, PlayerId), FMath::IsNearlyEqual(GaugeOf(ASC), Ctx->Gauges.FindRef(PlayerId), 0.01f));
				}
			}
		});

		// 차단은 복제되는 효과다 — 각자 자기 자리에서도 보이고, 체인 상태(시전자 · 멈춤)도 클라이언트마다 서버와 같다
		Wait(Ctx, FString::Printf(TEXT("%s: while casting, every teammate sees the block on its own seat and every client matches the server"), *Label), 3.0, [Ctx, UserIndex]()
		{
			const int32 UserId = Ctx->Ids[UserIndex];
			if (ServerState().CastingPlayerId != UserId || !ClientsMatchServer())
			{
				return false;
			}
			for (const int32 PlayerId : Ctx->Ids)
			{
				if (PlayerId != UserId && !HasTag(SeatASC(PlayerId), UltBlockedTagName))
				{
					return false;
				}
			}
			return true;
		});

		Wait(Ctx, FString::Printf(TEXT("%s: the ult of player index %d ends on the server"), *Label, UserIndex), 15.0, [Ctx, UserIndex]()
		{
			return ServerState().CastingPlayerId == 0 && !HasTag(ServerASC(Ctx->Ids[UserIndex]), UltActiveTagName);
		});

		// ─── 끝난 뒤 ───
		Do(Ctx, [Ctx, Label, UserIndex, bHit]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const FAstralChainState State = ServerState();
			const FAstralChainState& Before = Ctx->StateBeforeCast;
			const int32 UserId = Ctx->Ids[UserIndex];

			for (const int32 PlayerId : Ctx->Ids)
			{
				Test.TestFalse(*FString::Printf(TEXT("%s: player %d is unblocked on the server after the ult"), *Label, PlayerId), HasTag(ServerASC(PlayerId), UltBlockedTagName));
			}

			if (bHit)
			{
				return; // 등록 · 팀 게이지 · 적 HP 는 EnqueueChain 이 본다
			}

			// ③ 못 맞힌 오의 — 최대치 × 비율을 돌려받고, 체인 · 팀 게이지가 없다
			const float Refunded = Ctx->MaxGauge * Ctx->MissRefundRatio;
			FString GaugeLine;
			for (const int32 PlayerId : Ctx->Ids)
			{
				const float Was = Ctx->Gauges.FindRef(PlayerId);
				const float Now = GaugeOf(ServerASC(PlayerId));
				if (PlayerId == UserId)
				{
					Test.TestTrue(*FString::Printf(TEXT("%s: the missed ult refunds max x ratio (%.1f, want %.1f)"), *Label, Now, Refunded), FMath::IsNearlyEqual(Now, Refunded, 0.01f));
				}
				else
				{
					Test.TestTrue(*FString::Printf(TEXT("%s: teammate %d gets no team gauge from a missed ult"), *Label, PlayerId), FMath::IsNearlyEqual(Now, Was, 0.01f));
				}
				GaugeLine += FString::Printf(TEXT(" %d:%.0f->%.0f"), PlayerId, Was, Now);
			}
			Test.TestEqual(*FString::Printf(TEXT("%s: the missed ult is not in the chain (chain id)"), *Label), State.ChainId, Before.ChainId);
			Test.TestEqual(*FString::Printf(TEXT("%s: the missed ult is not in the chain (participants)"), *Label), State.ParticipantIds, Before.ParticipantIds);
			Test.TestEqual(*FString::Printf(TEXT("%s: the missed ult did not touch the enemy"), *Label), HealthOf(Ctx->Enemy.Get()), Ctx->EnemyHealthBeforeCast);

			// ① 멈춰 둔 타이머가 남아 있던 시간으로 다시 돈다 (마감을 새로 재지 않는다)
			if (Before.Phase == EAstralChainPhase::Open)
			{
				const float Remaining = ServerChain()->GetRemainingSeconds();
				Test.TestEqual(*FString::Printf(TEXT("%s: the chain is still open after the missed ult"), *Label), static_cast<int32>(State.Phase), static_cast<int32>(EAstralChainPhase::Open));
				Test.TestFalse(*FString::Printf(TEXT("%s: the timer runs again after the missed ult"), *Label), State.bTimerPaused);
				Test.TestTrue(*FString::Printf(TEXT("%s: the timer resumes with what was left (%.2f now, %.2f when paused)"), *Label, Remaining, Ctx->PausedRemaining),
					Remaining <= Ctx->PausedRemaining + 0.01f && Remaining > Ctx->PausedRemaining - 0.5f);
				Ctx->LastDeadline = State.DeadlineServerTime;
				Note(Test, FString::Printf(TEXT("%s: missed by %d at t %.2f — [%s], paused with %.2f s, resumed with %.2f s, gauges%s"),
					*Label, UserId, ServerNow(), *ServerChain()->GetDebugString(), Ctx->PausedRemaining, Remaining, *GaugeLine));
			}
			else
			{
				Note(Test, FString::Printf(TEXT("%s: missed by %d at t %.2f — [%s], gauges%s"), *Label, UserId, ServerNow(), *ServerChain()->GetDebugString(), *GaugeLine));
			}
		});

		if (!bHit)
		{
			Face(Ctx, UserIndex, /*bAway=*/false);
		}
	}

	/**
	 * 체인 하나 — Steps 의 순서로 한 명씩 오의를 쓴다. 맞힌 사람만 체인에 든다.
	 * BoostIndex 가 있으면 그 사람의 ChainBurstDamageMultiplier 를 올린 채로 돈다
	 */
	void EnqueueChain(const TSharedRef<FContext>& Ctx, const FString& Label, const TArray<FUltStep>& Steps, int32 BoostIndex = INDEX_NONE)
	{
		int32 NumHits = 0;
		for (const FUltStep& Step : Steps)
		{
			NumHits += Step.bHit ? 1 : 0;
		}
		const bool bFull = (NumHits == NumPlayers);

		PlaceHeroes(Ctx);
		for (const FUltStep& Step : Steps)
		{
			Fill(Ctx, Step.UserIndex);
		}

		if (BoostIndex != INDEX_NONE)
		{
			Do(Ctx, [Ctx, BoostIndex]()
			{
				if (UAbilitySystemComponent* ASC = ServerASC(Ctx->Ids[BoostIndex]))
				{
					ASC->SetNumericAttributeBase(UAstralHeroResourceSet::GetChainBurstDamageMultiplierAttribute(), BoostedMultiplier);
				}
			});
			Wait(Ctx, TEXT("the boosted chain burst multiplier replicates to its owner's seat"), 10.0, [Ctx, BoostIndex]()
			{
				return FMath::IsNearlyEqual(AttributeOf(SeatASC(Ctx->Ids[BoostIndex]), UAstralHeroResourceSet::GetChainBurstDamageMultiplierAttribute()), BoostedMultiplier, 0.001f);
			});
		}

		Do(Ctx, [Ctx, Label]()
		{
			const FAstralChainState State = ServerState();
			Ctx->Test->TestEqual(*FString::Printf(TEXT("%s: no chain before the first ult"), *Label), static_cast<int32>(State.Phase), static_cast<int32>(EAstralChainPhase::None));
			Ctx->ChainIdBefore = State.ChainId;
			Ctx->BurstIdBefore = State.LastBurstChainId;
			Ctx->EnemyHealthBefore = HealthOf(Ctx->Enemy.Get());
			Ctx->ExpectedUltDamage = 0.f;
			Ctx->LastDeadline = 0.0;
			Ctx->Expected.Reset();
		});

		int32 HitOrder = 0;
		for (const FUltStep& Step : Steps)
		{
			EnqueueCast(Ctx, Label, Step);
			if (!Step.bHit)
			{
				continue;
			}

			// ─── 맞힌 오의가 끝난 뒤 — 그 시각으로 등록, 팀 게이지 ───
			++HitOrder;
			const int32 UserIndex = Step.UserIndex;
			const bool bLastOfFull = bFull && (HitOrder == NumHits);
			Do(Ctx, [Ctx, Label, UserIndex, HitOrder, bLastOfFull]()
			{
				FAutomationTestBase& Test = *Ctx->Test;
				const UAstralChainBurstComponent* Chain = ServerChain();
				const FAstralChainState State = ServerState();
				const int32 UserId = Ctx->Ids[UserIndex];
				const float Window = FloatProperty(Chain, TEXT("WindowSeconds"));
				Ctx->Expected.Add(UserId);
				Ctx->ExpectedUltDamage += UltDamageBy(*Ctx, UserId);

				Test.TestEqual(*FString::Printf(TEXT("%s: the hit ult is in this chain (chain id)"), *Label), State.ChainId, Ctx->ChainIdBefore + 1);
				if (bLastOfFull)
				{
					// 규칙 4 · 6 — 전원이 찼다: 바로 닫히고 버스트는 다음 틱이다. 이 시점에는 '버스트' 단계이거나 이미 나간 뒤다
					const bool bBurstPhase = State.Phase == EAstralChainPhase::Burst && State.ParticipantIds == Ctx->Expected;
					const bool bAlreadyOut = State.LastBurstChainId == Ctx->ChainIdBefore + 1;
					Test.TestTrue(*FString::Printf(TEXT("%s: the full chain closes when the last ult ends"), *Label), bBurstPhase || bAlreadyOut);
					Ctx->LastDeadline = ServerNow(); // 닫힌 시각의 근사 — 버스트까지 걸린 시간을 재는 기준
				}
				else
				{
					Test.TestEqual(*FString::Printf(TEXT("%s: participants in the order their ults ended"), *Label), State.ParticipantIds, Ctx->Expected);
					Test.TestEqual(*FString::Printf(TEXT("%s: the chain is open after hit %d"), *Label, HitOrder), static_cast<int32>(State.Phase), static_cast<int32>(EAstralChainPhase::Open));
					Test.TestFalse(*FString::Printf(TEXT("%s: the timer runs after hit %d"), *Label, HitOrder), State.bTimerPaused);

					// ① 마감 = 오의가 끝난 시각 + 윈도우 — 방금 끝났으므로 남은 시간이 윈도우에 가깝다(연출이 창을 깎지 않는다)
					const double Left = State.DeadlineServerTime - ServerNow();
					Test.TestTrue(*FString::Printf(TEXT("%s: the deadline is the end of the ult + window (%.2f s left of %.2f)"), *Label, Left, Window), Left <= Window + 0.01 && Left > Window - 0.5);
					Test.TestTrue(*FString::Printf(TEXT("%s: the deadline moves forward with hit %d"), *Label, HitOrder), State.DeadlineServerTime > Ctx->LastDeadline);
					Ctx->LastDeadline = State.DeadlineServerTime;

					// 이 오의의 피해가 적에게 들어갔다
					Test.TestTrue(*FString::Printf(TEXT("%s: the ult damaged the enemy"), *Label), FMath::IsNearlyEqual(Ctx->EnemyHealthBeforeCast - HealthOf(Ctx->Enemy.Get()), UltDamageBy(*Ctx, UserId), 0.5f));
				}

				// 팀 게이지 — 본인은 0(맞힌 오의는 돌려받지 않는다), 나머지는 + TeamUltGain × 자기 UltGainMultiplier (최대치까지)
				const float TeamGain = FloatProperty(Chain, TEXT("TeamUltGain"));
				FString GaugeLine;
				for (const int32 PlayerId : Ctx->Ids)
				{
					const UAbilitySystemComponent* ASC = ServerASC(PlayerId);
					const float Was = Ctx->Gauges.FindRef(PlayerId);
					const float Now = GaugeOf(ASC);
					if (PlayerId == UserId)
					{
						Test.TestTrue(*FString::Printf(TEXT("%s: an ult that hit keeps the gauge at 0"), *Label), FMath::IsNearlyZero(Now, 0.01f));
					}
					else
					{
						const float Want = FMath::Min(Was + TeamGain * AttributeOf(ASC, UAstralHeroResourceSet::GetUltGainMultiplierAttribute(), 1.f), Ctx->MaxGauge);
						Test.TestTrue(*FString::Printf(TEXT("%s: teammate %d gains the team ult gauge when the hit ult ends (%.1f -> %.1f, want %.1f)"), *Label, PlayerId, Was, Now, Want), FMath::IsNearlyEqual(Now, Want, 0.01f));
					}
					GaugeLine += FString::Printf(TEXT(" %d:%.0f->%.0f"), PlayerId, Was, Now);
				}
				Note(Test, FString::Printf(TEXT("%s: hit %d by %d ended at t %.2f — [%s], gauges%s"), *Label, HitOrder, UserId, ServerNow(), *Chain->GetDebugString(), *GaugeLine));

				// 버스트로 게이지가 차는지 볼 기준 — 마지막으로 맞힌 오의 직후의 값
				SnapshotGauges(*Ctx);
			});
		}

		if (NumHits < 2)
		{
			// C1 — 조용히 닫힌다
			Wait(Ctx, FString::Printf(TEXT("%s: the lone chain closes"), *Label), 20.0, []() { return ServerState().Phase == EAstralChainPhase::None; });
			Do(Ctx, [Ctx, Label]()
			{
				FAutomationTestBase& Test = *Ctx->Test;
				const FAstralChainState State = ServerState();
				const float Grace = FloatProperty(ServerChain(), TEXT("GraceSeconds"));
				const float Dealt = Ctx->EnemyHealthBefore - HealthOf(Ctx->Enemy.Get());
				Test.TestTrue(*FString::Printf(TEXT("%s: not closed before deadline + grace"), *Label), ServerNow() >= Ctx->LastDeadline + Grace);
				Test.TestEqual(*FString::Printf(TEXT("%s: no burst for one participant"), *Label), State.LastBurstChainId, Ctx->BurstIdBefore);
				Test.TestEqual(*FString::Printf(TEXT("%s: participants cleared"), *Label), State.ParticipantIds.Num(), 0);
				Test.TestTrue(*FString::Printf(TEXT("%s: the enemy lost only the ult's damage (%.1f, want %.1f)"), *Label, Dealt, Ctx->ExpectedUltDamage), FMath::IsNearlyEqual(Dealt, Ctx->ExpectedUltDamage, 0.5f));
				Note(Test, FString::Printf(TEXT("%s: closed quietly %.2f s after the deadline — [%s], enemy hp %.1f -> %.1f (ult only)"),
					*Label, ServerNow() - Ctx->LastDeadline, *ServerChain()->GetDebugString(), Ctx->EnemyHealthBefore, HealthOf(Ctx->Enemy.Get())));
			});
		}
		else
		{
			Wait(Ctx, FString::Printf(TEXT("%s: the burst goes out"), *Label), 25.0, [Ctx]() { return ServerState().LastBurstChainId == Ctx->ChainIdBefore + 1; });
			Do(Ctx, [Ctx, Label, NumHits, bFull]()
			{
				FAutomationTestBase& Test = *Ctx->Test;
				const UAstralChainBurstComponent* Chain = ServerChain();
				const FAstralChainState State = ServerState();
				const FAstralChainBurstReport& Report = Chain->GetLastBurstReport();

				Test.TestEqual(*FString::Printf(TEXT("%s: burst count = the players who hit"), *Label), State.LastBurstCount, NumHits);
				Test.TestEqual(*FString::Printf(TEXT("%s: phase none after the burst"), *Label), static_cast<int32>(State.Phase), static_cast<int32>(EAstralChainPhase::None));
				Test.TestEqual(*FString::Printf(TEXT("%s: participants cleared"), *Label), State.ParticipantIds.Num(), 0);
				Test.TestEqual(*FString::Printf(TEXT("%s: server report chain id"), *Label), Report.ChainId, Ctx->ChainIdBefore + 1);
				Test.TestEqual(*FString::Printf(TEXT("%s: server report count"), *Label), Report.Count, NumHits);
				Test.TestEqual(*FString::Printf(TEXT("%s: every participant contributed"), *Label), Report.NumContributors, NumHits);
				Test.TestTrue(*FString::Printf(TEXT("%s: the burst hit the enemy"), *Label), Report.NumTargets >= 1);

				if (!bFull)
				{
					// 규칙 7 — 마감 + 유예 전에는 닫지 않는다
					Test.TestTrue(*FString::Printf(TEXT("%s: not closed before deadline + grace"), *Label), ServerNow() >= Ctx->LastDeadline + FloatProperty(Chain, TEXT("GraceSeconds")));
				}

				// 버스트 피해 — 자기 몫 = 총 피해 / 인원 × 자기 ChainBurstDamageMultiplier × 자기 OutgoingDamageMultiplier
				float ExpectedBurst = 0.f;
				FString Shares;
				const float EnemyIncoming = AttributeOf(Ctx->Enemy->GetAbilitySystemComponent(), UAstralHealthSet::GetIncomingDamageMultiplierAttribute(), 1.f);
				for (const int32 PlayerId : Ctx->Expected)
				{
					const UAbilitySystemComponent* ASC = ServerASC(PlayerId);
					// 규칙 6 — 닫힐 때 연출 중인 참가자가 없다
					Test.TestFalse(*FString::Printf(TEXT("%s: no participant's ult is playing at the burst"), *Label), HasTag(ASC, UltActiveTagName));

					const float Personal = AttributeOf(ASC, UAstralHeroResourceSet::GetChainBurstDamageMultiplierAttribute(), 1.f);
					const float Outgoing = AttributeOf(ASC, UAstralCombatSet::GetOutgoingDamageMultiplierAttribute(), 1.f);
					const float Share = Report.TotalDamage / NumHits * Personal * Outgoing * EnemyIncoming;
					ExpectedBurst += Share;
					Shares += FString::Printf(TEXT(" %d:%.1f(x%.2f out x%.2f)"), PlayerId, Share, Personal, Outgoing);
				}

				// 적이 이 체인에서 잃은 HP = 맞힌 오의들의 피해 + 버스트
				const float Dealt = Ctx->EnemyHealthBefore - HealthOf(Ctx->Enemy.Get());
				const float Expected = Ctx->ExpectedUltDamage + ExpectedBurst;
				Test.TestTrue(*FString::Printf(TEXT("%s: enemy health loss %.1f = ults %.1f + burst shares %.1f"), *Label, Dealt, Ctx->ExpectedUltDamage, ExpectedBurst), FMath::IsNearlyEqual(Dealt, Expected, 0.5f));

				// 버스트 피해로는 오의 게이지가 차지 않는다
				for (const int32 PlayerId : Ctx->Ids)
				{
					Test.TestTrue(*FString::Printf(TEXT("%s: the burst does not change player %d's ult gauge"), *Label, PlayerId), FMath::IsNearlyEqual(GaugeOf(ServerASC(PlayerId)), Ctx->Gauges.FindRef(PlayerId), 0.01f));
				}

				Ctx->TotalByCount.Add(NumHits, Report.TotalDamage);
				Note(Test, FString::Printf(TEXT("%s: burst x%d at t %.2f (%.2f s after %s) — total %.1f, targets %d, enemy hp %.1f -> %.1f (dealt %.1f = ults %.1f + burst %.1f), shares%s"),
					*Label, NumHits, ServerNow(), ServerNow() - Ctx->LastDeadline, bFull ? TEXT("the last ult ended") : TEXT("the deadline"), Report.TotalDamage, Report.NumTargets,
					Ctx->EnemyHealthBefore, HealthOf(Ctx->Enemy.Get()), Dealt, Ctx->ExpectedUltDamage, ExpectedBurst, *Shares));
			});
		}

		Wait(Ctx, FString::Printf(TEXT("%s: the final chain state on every client matches the server"), *Label), 5.0, []()
		{
			return ServerState().Phase == EAstralChainPhase::None && ClientsMatchServer();
		});

		if (BoostIndex != INDEX_NONE)
		{
			Do(Ctx, [Ctx, BoostIndex]()
			{
				if (UAbilitySystemComponent* ASC = ServerASC(Ctx->Ids[BoostIndex]))
				{
					ASC->SetNumericAttributeBase(UAstralHeroResourceSet::GetChainBurstDamageMultiplierAttribute(), 1.f);
				}
			});
		}
	}

	void EnqueueAll(FAutomationTestBase& Test, bool bDedicated)
	{
		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;
		Ctx->bDedicated = bDedicated;

		EnqueueSetup(Ctx);
		EnqueueChain(Ctx, TEXT("C1 solo"), { { 1, true } });
		EnqueueChain(Ctx, TEXT("C2 two"), { { 0, true }, { 1, false }, { 2, true } }, /*BoostIndex=*/2);
		EnqueueChain(Ctx, TEXT("C3 three"), { { 1, true }, { 2, true }, { 3, true } });
		EnqueueChain(Ctx, TEXT("C4 four"), { { 3, true }, { 2, true }, { 1, true }, { 0, true } });

		Do(Ctx, [Ctx]()
		{
			// 인원이 늘수록 총 피해가 커진다 (배수 값 자체는 잠정)
			const float Two = Ctx->TotalByCount.FindRef(2);
			const float Three = Ctx->TotalByCount.FindRef(3);
			const float Four = Ctx->TotalByCount.FindRef(4);
			Ctx->Test->TestTrue(TEXT("the total burst damage grows with the head count"), Two > 0.f && Three > Two && Four > Three);
			Note(*Ctx->Test, FString::Printf(TEXT("totals: x2 %.1f, x3 %.1f, x4 %.1f"), Two, Three, Four));
		});
		EndPie(Ctx);
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralChainBurstListenPieTest, "AstralBreak.Net.ChainBurst.ListenPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralChainBurstListenPieTest::RunTest(const FString& Parameters)
{
	AstralChainBurstPie::EnqueueAll(*this, /*bDedicated=*/false);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralChainBurstDedicatedPieTest, "AstralBreak.Net.ChainBurst.DedicatedPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralChainBurstDedicatedPieTest::RunTest(const FString& Parameters)
{
	AstralChainBurstPie::EnqueueAll(*this, /*bDedicated=*/true);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
