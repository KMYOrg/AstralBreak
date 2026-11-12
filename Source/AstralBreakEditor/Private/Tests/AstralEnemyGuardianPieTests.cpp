// 단위 C1 수호병 네트워크 시험 — 한 프로세스 멀티 PIE (설계 Docs/Design/m3-enemy-ai.md §10 C1 검증 계획 C1-0 · G1 ~ G5)
//
// 리슨 서버 · Dedicated 를 PIE 로 띄워 CombatTestMap 에서 수호병(BP_Enemy_Guardian)을 클라이언트의 디버그 명령으로 부르고,
// 서버 월드와 각 클라이언트 월드의 폰 · AnimInstance · 몽타주 재생 상태를 직접 본다.
//
//   G1     서버 · 클라이언트의 수호병 폰에 메시와 ABP(UAstralEnemyAnimInstance)가 붙어 있다
//   G2     추격 중 클라이언트 AnimInstance 의 속도 값이 0 보다 크고, 멈추면 0
//   G3     공격: 클라이언트에서 몽타주가 재생되고(C1-0b), 서버 HP 가 타격 노티파이 시각에 준다(C1-0a — Dedicated 에서도)
//   G5     패링(방어 태그를 서버에서 직접 세운다)하면 피해 0 · 몽타주가 멈추고 · 경직 동안 다음 공격이 없다
//   G4     사망: 공격 중에 죽이면 몽타주가 멈추고, 모든 머신의 AnimInstance 가 사망을 보고, 폰이 사라진다
//
// 기대값(피해 · 타격 시각 · 몽타주 길이 · 경직)은 수호병의 공격 어빌리티 CDO 와 몽타주에서 읽는다 — 잠정값을 바꿔도 시험은 그대로다.
// 조회 함수는 AstralEnemyCombatPieTests.cpp 의 것과 같은 모양이다(그 파일은 마네킹 고정물이라 건드리지 않고 필요한 것만 다시 뒀다).
// PIE 는 적이 사라진 뒤에 내린다 — 재생 중인 몽타주가 없다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AstralPieTestHelpers.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Abilities/Enemy/AstralGA_Enemy_MeleeAttack.h"
#include "Animation/AnimMontage.h"
#include "Animation/AstralEnemyAnimInstance.h"
#include "Animation/Notifies/AstralAnimNotify_GameplayEvent.h"
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Character/Enemy/AstralCombatCharacter.h"
#include "Character/Enemy/AstralEnemyController.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StateTreeAIComponent.h"
#include "Engine/GameInstance.h"
#include "Engine/SkeletalMesh.h"
#include "EngineUtils.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerState.h"
#include "GameplayAbilitySpec.h"
#include "GameplayTagContainer.h"
#include "Player/AstralPlayerController.h"

namespace AstralEnemyGuardianPie
{
	using namespace AstralPieTest;

	const TCHAR* const MapPath = TEXT("/Game/Maps/CombatTestMap");
	const TCHAR* const MapName = TEXT("CombatTestMap");
	const TCHAR* const GuardianName = TEXT("BP_Enemy_Guardian");
	const TCHAR* const GuardianAnimClassPrefix = TEXT("ABP_Enemy_Guardian");
	const TCHAR* const GuardianMeshName = TEXT("SK_SciFi_Beast06_Skin1");

	// 태그는 런타임 모듈이 내보내지 않는다 — 이름으로 찾는다
	const TCHAR* const TelegraphTagName = TEXT("State.Telegraphing");
	const TCHAR* const ParryTagName = TEXT("State.Defense.Parrying");
	const TCHAR* const MeleeAbilityTagName = TEXT("Ability.Enemy.Attack.Melee");

	// ST_Enemy_Melee 의 값(잠정) — 바꾸면 여기도 바꾼다
	constexpr double RecoverySeconds = 1.0;

	/** 표본이 프레임 단위라 생기는 오차 + 상태 전환 프레임 */
	constexpr double TimingSlack = 0.35;

	// CombatTestMap 좌표 — AstralEnemyCombatPieTests 와 같은 자리(맵의 더미와 떨어진 NavMesh 위)
	const FVector NearHeroLocation(1100.0, -400.0, 92.0);
	const FVector FarHeroLocation(1100.0, 900.0, 92.0);
	constexpr float EnemySpawnDistance = 600.f;

	struct FContext : FContextBase
	{
		bool bDedicated = false;
		int32 NumPlayers = 2;

		/** 가까운 쪽 = 클라이언트 자리의 플레이어(적을 부른다), 먼 쪽 = 나머지 */
		int32 NearId = 0;
		int32 FarId = 0;

		TWeakObjectPtr<AAstralCombatCharacter> Enemy;

		// 수호병의 공격 어빌리티 CDO · 몽타주에서 읽은 기대값
		TWeakObjectPtr<UAnimMontage> Montage;
		float AttackDamage = 0.f;
		double HitSeconds = 0.0;      // 몽타주 시작 → 첫 타격 노티파이 (재생 속도 반영)
		double MontageSeconds = 0.0;  // 몽타주 길이 (재생 속도 반영)
		double StaggerSeconds = 0.0;
		int32 NumHitNotifies = 0;

		// 매 프레임 표본 — 서버
		bool bTelegraphing = false;
		bool bAttackActive = false;
		bool bServerMontage = false;
		float LastNearHealth = -1.f;
		TArray<double> TelegraphStartTimes;
		TArray<double> TelegraphEndTimes;
		TArray<double> AttackEndTimes;
		TArray<double> ServerMontageStartTimes;
		TArray<double> HitTimes;

		// 매 프레임 표본 — 클라이언트 월드별
		TMap<const UWorld*, float> ClientMaxSpeed;
		TMap<const UWorld*, double> ClientMontageFirstSeen;

		// 단계 사이에 넘기는 값
		float NearHealthBefore = 0.f;
		float FarHealthBefore = 0.f;
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

	/** 이 월드의 수호병 AnimInstance (없으면 null) */
	UAstralEnemyAnimInstance* GuardianAnimIn(UWorld* World)
	{
		const TArray<AAstralCombatCharacter*> Guardians = GuardiansIn(World);
		const USkeletalMeshComponent* Mesh = Guardians.Num() > 0 ? Guardians[0]->GetMesh() : nullptr;
		return Mesh ? Cast<UAstralEnemyAnimInstance>(Mesh->GetAnimInstance()) : nullptr;
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

	const FGameplayAbilitySpec* AttackSpec(const FContext& Ctx)
	{
		const UAbilitySystemComponent* ASC = Ctx.Enemy.IsValid() ? Ctx.Enemy->GetAbilitySystemComponent() : nullptr;
		if (!ASC)
		{
			return nullptr;
		}
		TArray<FGameplayAbilitySpec*> Specs;
		ASC->GetActivatableGameplayAbilitySpecsByAllMatchingTags(FGameplayTagContainer(FGameplayTag::RequestGameplayTag(MeleeAbilityTagName)), Specs, false);
		return Specs.Num() > 0 ? Specs[0] : nullptr;
	}

	bool EnemyAttackActive(const FContext& Ctx)
	{
		const FGameplayAbilitySpec* Spec = AttackSpec(Ctx);
		return Spec && Spec->IsActive();
	}

	bool MontagePlayingIn(const FContext& Ctx, UWorld* World)
	{
		const UAstralEnemyAnimInstance* Anim = GuardianAnimIn(World);
		return Anim && Ctx.Montage.IsValid() && Anim->Montage_IsPlaying(Ctx.Montage.Get());
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
		UWorld* ServerWorld = FindServerWorld();
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

		const bool bServerMontage = MontagePlayingIn(Ctx, ServerWorld);
		if (bServerMontage != Ctx.bServerMontage)
		{
			if (bServerMontage)
			{
				Ctx.ServerMontageStartTimes.Add(Now);
			}
			Ctx.bServerMontage = bServerMontage;
		}

		const float NearHealth = HealthOf(PawnIn(ServerWorld, Ctx.NearId));
		if (Ctx.LastNearHealth >= 0.f && NearHealth < Ctx.LastNearHealth)
		{
			Ctx.HitTimes.Add(Now);
		}
		Ctx.LastNearHealth = NearHealth;

		for (UWorld* ClientWorld : GetClientWorlds())
		{
			if (const UAstralEnemyAnimInstance* Anim = GuardianAnimIn(ClientWorld))
			{
				float& MaxSpeed = Ctx.ClientMaxSpeed.FindOrAdd(ClientWorld, 0.f);
				MaxSpeed = FMath::Max(MaxSpeed, Anim->GetGroundSpeed());

				if (Ctx.Montage.IsValid() && Anim->Montage_IsPlaying(Ctx.Montage.Get()) && !Ctx.ClientMontageFirstSeen.Contains(ClientWorld))
				{
					Ctx.ClientMontageFirstSeen.Add(ClientWorld, Now);
				}
			}
		}
	}

	FString Describe(const FContext& Ctx)
	{
		const UWorld* ServerWorld = FindServerWorld();
		const AAstralEnemyController* Controller = EnemyController(Ctx);
		return FString::Printf(TEXT("server map '%s', seats %d, near hp %.0f, far hp %.0f, enemy %s hp %.0f at %s, target %s, tree running %d, telegraph starts %d ends %d, attack ends %d, hits %d, server montage starts %d, clients saw montage %d"),
			*MapOf(ServerWorld), GetSeatWorlds().Num(),
			HealthOf(PawnIn(ServerWorld, Ctx.NearId)), HealthOf(PawnIn(ServerWorld, Ctx.FarId)),
			Ctx.Enemy.IsValid() ? *Ctx.Enemy->GetName() : TEXT("none"), HealthOf(Ctx.Enemy.Get()),
			Ctx.Enemy.IsValid() ? *Ctx.Enemy->GetActorLocation().ToCompactString() : TEXT("-"),
			Controller ? *GetNameSafe(Controller->GetCurrentTarget()) : TEXT("-"),
			(Controller && Controller->GetStateTreeComponent()->IsRunning()) ? 1 : 0,
			Ctx.TelegraphStartTimes.Num(), Ctx.TelegraphEndTimes.Num(), Ctx.AttackEndTimes.Num(), Ctx.HitTimes.Num(),
			Ctx.ServerMontageStartTimes.Num(), Ctx.ClientMontageFirstSeen.Num());
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

			// 가까운 쪽은 반드시 클라이언트 자리 — 적을 부르는 RPC 가 실제 넷 드라이버를 탄다
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

			// 서버에서 자리를 잡는다. 둘 다 +X 를 본다 — 적은 가까운 쪽의 정면에 나온다. 적은 옮기지 않는다(스폰 자리에서 스스로 걸어온다)
			NearPawn->TeleportTo(NearHeroLocation, FRotator::ZeroRotator);
			FarPawn->TeleportTo(FarHeroLocation, FRotator::ZeroRotator);
			Test.TestEqual(TEXT("no guardian before SpawnEnemy"), GuardiansIn(ServerWorld).Num(), 0);
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
			ClientPawn->SpawnEnemy(GuardianName, EnemySpawnDistance);
		});
		WaitUntil(Ctx, TEXT("SpawnEnemy BP_Enemy_Guardian: guardian on the server with a running tree, replicated to every client"), 30.0, [Ctx]()
		{
			const TArray<AAstralCombatCharacter*> ServerGuardians = GuardiansIn(FindServerWorld());
			if (ServerGuardians.Num() != 1)
			{
				return false;
			}
			Ctx->Enemy = ServerGuardians[0];
			const AAstralEnemyController* Controller = EnemyController(*Ctx);
			if (!Controller || !Controller->GetStateTreeComponent()->IsRunning())
			{
				return false;
			}
			for (UWorld* ClientWorld : GetClientWorlds())
			{
				if (GuardiansIn(ClientWorld).Num() != 1)
				{
					return false;
				}
			}
			// 표본은 폰이 보이는 첫 프레임부터 뜬다 — 추격 속도를 놓치지 않는다
			Sample(*Ctx);
			return true;
		}, [Ctx]() { return Describe(*Ctx); });

		// 기대값 — 수호병의 공격 어빌리티 CDO 와 몽타주에서 읽는다
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const FGameplayAbilitySpec* Spec = AttackSpec(*Ctx);
			const UAstralGA_Enemy_MeleeAttack* Ability = Spec ? Cast<UAstralGA_Enemy_MeleeAttack>(Spec->Ability) : nullptr;
			UAnimMontage* Montage = Ability ? Ability->GetAttackMontage() : nullptr;
			if (!Test.TestNotNull(TEXT("the guardian's attack ability (Ability.Enemy.Attack.Melee)"), Ability) || !Test.TestNotNull(TEXT("the guardian's attack uses a montage"), Montage))
			{
				Ctx->bAborted = true;
				return;
			}

			const double PlayRate = FMath::Max(Ability->GetMontagePlayRate(), 0.01f);
			double FirstHit = -1.0;
			for (const FAnimNotifyEvent& NotifyEvent : Montage->Notifies)
			{
				const UAstralAnimNotify_GameplayEvent* HitNotify = Cast<UAstralAnimNotify_GameplayEvent>(NotifyEvent.Notify);
				if (HitNotify && HitNotify->GetEventTag() == Ability->GetHitEventTag())
				{
					++Ctx->NumHitNotifies;
					FirstHit = (FirstHit < 0.0) ? NotifyEvent.GetTriggerTime() : FMath::Min<double>(FirstHit, NotifyEvent.GetTriggerTime());
				}
			}
			if (!Test.TestTrue(TEXT("the attack montage has a hit notify"), FirstHit > 0.0))
			{
				Ctx->bAborted = true;
				return;
			}

			Ctx->Montage = Montage;
			Ctx->AttackDamage = Ability->GetBaseDamage();
			Ctx->HitSeconds = FirstHit / PlayRate;
			Ctx->MontageSeconds = Montage->GetPlayLength() / PlayRate;
			Ctx->StaggerSeconds = Ability->GetStaggerRecovery();
			Note(Test, FString::Printf(TEXT("guardian attack data: montage %s length %.2f s, play rate %.2f, %d hit notify(ies), first at %.2f s -> hit expected %.2f s after the start, attack lasts %.2f s, damage %.1f, stagger %.1f s"),
				*Montage->GetName(), Montage->GetPlayLength(), PlayRate, Ctx->NumHitNotifies, FirstHit, Ctx->HitSeconds, Ctx->MontageSeconds, Ctx->AttackDamage, Ctx->StaggerSeconds));
		});

		// G1 — 메시와 ABP 가 모든 머신에 붙어 있다
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			for (UWorld* World : GetPieWorlds())
			{
				const TArray<AAstralCombatCharacter*> Guardians = GuardiansIn(World);
				if (!Test.TestEqual(TEXT("G1: one guardian in every world"), Guardians.Num(), 1))
				{
					continue;
				}
				const AAstralCombatCharacter* Guardian = Guardians[0];
				const USkeletalMeshComponent* Mesh = Guardian->GetMesh();
				const USkeletalMesh* MeshAsset = Mesh ? Mesh->GetSkeletalMeshAsset() : nullptr;
				const UAnimInstance* Anim = Mesh ? Mesh->GetAnimInstance() : nullptr;
				const TCHAR* Where = World->GetNetMode() == NM_Client ? TEXT("client") : (World->GetNetMode() == NM_DedicatedServer ? TEXT("dedicated server") : TEXT("listen server"));

				Test.TestTrue(FString::Printf(TEXT("G1: the guardian's mesh on the %s"), Where), MeshAsset && MeshAsset->GetName() == GuardianMeshName);
				Test.TestTrue(FString::Printf(TEXT("G1: the guardian's anim instance on the %s is ABP_Enemy_Guardian (UAstralEnemyAnimInstance)"), Where),
					Anim && Anim->IsA<UAstralEnemyAnimInstance>() && Anim->GetClass()->GetName().StartsWith(GuardianAnimClassPrefix));
				Note(Test, FString::Printf(TEXT("G1: %s — mesh %s, anim %s, capsule r %.0f hh %.0f, mesh offset z %.0f"), Where, *GetNameSafe(MeshAsset), Anim ? *Anim->GetClass()->GetName() : TEXT("none"),
					Guardian->GetCapsuleComponent()->GetScaledCapsuleRadius(), Guardian->GetCapsuleComponent()->GetScaledCapsuleHalfHeight(), Mesh ? Mesh->GetRelativeLocation().Z : 0.0));
			}

			UWorld* ServerWorld = FindServerWorld();
			Test.TestEqual(TEXT("one enemy controller on the server"), NumEnemyControllersIn(ServerWorld), 1);
			for (UWorld* ClientWorld : GetClientWorlds())
			{
				Test.TestEqual(TEXT("no enemy controller on a client"), NumEnemyControllersIn(ClientWorld), 0);
			}
			Ctx->NearHealthBefore = HealthOf(PawnIn(ServerWorld, Ctx->NearId));
			Ctx->FarHealthBefore = HealthOf(PawnIn(ServerWorld, Ctx->FarId));
		});
	}

	void EnqueueChaseAndHit(const TSharedRef<FContext>& Ctx)
	{
		// G2 · G3 — 쫓아와(클라이언트 AnimInstance 의 속도 > 0) 몽타주로 때린다
		WaitSampling(Ctx, TEXT("G3: the guardian's attack lowers the near hero's health on the server"), 30.0, [Ctx]()
		{
			return Ctx->HitTimes.Num() >= 1;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			const AAstralCharacter* NearPawn = PawnIn(ServerWorld, Ctx->NearId);
			const float Damage = Ctx->NearHealthBefore - HealthOf(NearPawn);
			const int32 NumClients = GetClientWorlds().Num();

			// C1-0a — 서버(Dedicated 포함)에서 몽타주의 노티파이가 불려 피해가 났다
			Test.TestTrue(TEXT("G3 (C1-0a): the montage's hit notify dealt the attack's BaseDamage on the server"), FMath::IsNearlyEqual(Damage, Ctx->AttackDamage, 0.01f));
			Test.TestEqual(TEXT("G3: the far hero was not hit"), HealthOf(PawnIn(ServerWorld, Ctx->FarId)), Ctx->FarHealthBefore);

			const bool bSawTelegraph = Ctx->TelegraphStartTimes.Num() == 1 && Ctx->TelegraphEndTimes.Num() == 1;
			if (Test.TestTrue(TEXT("G3: one telegraph before the hit"), bSawTelegraph))
			{
				const double HitAfter = Ctx->HitTimes[0] - Ctx->TelegraphStartTimes[0];
				Note(Test, FString::Printf(TEXT("G3: hit for %.1f at %.2f s after the attack started (hit notify at %.2f s), telegraph tag dropped %.2f s after the start, guardian stopped %.0f from the hero"),
					Damage, HitAfter, Ctx->HitSeconds, Ctx->TelegraphEndTimes[0] - Ctx->TelegraphStartTimes[0],
					FVector::Dist2D(Ctx->Enemy->GetActorLocation(), NearPawn->GetActorLocation())));
				Test.TestTrue(TEXT("G3: the server's health drops at the hit notify's time"), FMath::Abs(HitAfter - Ctx->HitSeconds) <= TimingSlack);
				Test.TestTrue(TEXT("G3: the telegraph tag drops at the first hit"), FMath::Abs(Ctx->TelegraphEndTimes[0] - Ctx->HitTimes[0]) <= 0.1);
			}

			if (Test.TestEqual(TEXT("G3: the server played the attack montage once"), Ctx->ServerMontageStartTimes.Num(), 1) && Ctx->TelegraphStartTimes.Num() > 0)
			{
				Test.TestTrue(TEXT("G3: the montage starts with the attack"), FMath::Abs(Ctx->ServerMontageStartTimes[0] - Ctx->TelegraphStartTimes[0]) <= 0.1);
			}

			// C1-0b — 서버 전용 어빌리티의 몽타주를 클라이언트가 재생했다
			Test.TestEqual(TEXT("G3 (C1-0b): every client played the server-only ability's montage"), Ctx->ClientMontageFirstSeen.Num(), NumClients);
			for (const TPair<const UWorld*, double>& Seen : Ctx->ClientMontageFirstSeen)
			{
				Note(Test, FString::Printf(TEXT("G3 (C1-0b): a client saw the attack montage playing %.2f s after the server started it"),
					Ctx->ServerMontageStartTimes.Num() > 0 ? Seen.Value - Ctx->ServerMontageStartTimes[0] : -1.0));
			}

			// G2 — 추격 중 클라이언트 AnimInstance 의 속도
			Test.TestEqual(TEXT("G2: every client's anim instance was sampled during the chase"), Ctx->ClientMaxSpeed.Num(), NumClients);
			for (const TPair<const UWorld*, float>& Speed : Ctx->ClientMaxSpeed)
			{
				Note(Test, FString::Printf(TEXT("G2: a client's anim instance reached ground speed %.0f during the chase"), Speed.Value));
				Test.TestTrue(TEXT("G2: the client's anim instance saw a ground speed above 0 during the chase"), Speed.Value > 10.f);
			}
		});
		WaitUntil(Ctx, TEXT("G2: once the guardian stands, every client's anim instance reads ground speed 0"), 5.0, [Ctx]()
		{
			for (UWorld* ClientWorld : GetClientWorlds())
			{
				const UAstralEnemyAnimInstance* Anim = GuardianAnimIn(ClientWorld);
				if (!Anim || Anim->GetGroundSpeed() > 1.f)
				{
					return false;
				}
			}
			return true;
		}, [Ctx]() { return Describe(*Ctx); });
		WaitUntil(Ctx, TEXT("G3: every client sees the same health as the server"), 10.0, [Ctx]()
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
		}, [Ctx]() { return Describe(*Ctx); });

		// 몽타주가 끝나면 어빌리티가 끝난다
		WaitSampling(Ctx, TEXT("G3: the attack ends when its montage ends"), 15.0, [Ctx]() { return Ctx->AttackEndTimes.Num() >= 1; });
		Do(Ctx, [Ctx]()
		{
			if (Ctx->TelegraphStartTimes.Num() < 1)
			{
				return;
			}
			const double Lasted = Ctx->AttackEndTimes[0] - Ctx->TelegraphStartTimes[0];
			Note(*Ctx->Test, FString::Printf(TEXT("G3: the unparried attack lasted %.2f s (montage %.2f s — it ends when the blend-out starts), %d hit(s)"), Lasted, Ctx->MontageSeconds, Ctx->HitTimes.Num()));
			Ctx->Test->TestTrue(TEXT("G3: the attack lasts about the montage's length"), Lasted >= Ctx->HitSeconds - TimingSlack && Lasted <= Ctx->MontageSeconds + TimingSlack && Lasted >= Ctx->MontageSeconds - 0.6 - TimingSlack);
			Ctx->Test->TestEqual(TEXT("G3: one sweep per hit notify"), Ctx->HitTimes.Num(), Ctx->NumHitNotifies);
		});
	}

	void EnqueueParry(const TSharedRef<FContext>& Ctx)
	{
		// G5 — 두 번째 공격의 준비 동작 중에 방어 태그를 서버에서 직접 세운다. 정면 판정은 방어자의 전방 기준이다(가까운 히어로는 +X = 적 쪽을 본다)
		WaitSampling(Ctx, TEXT("G5: the next attack starts"), 15.0, [Ctx]() { return Ctx->TelegraphStartTimes.Num() >= 2; });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			const double Gap = Ctx->TelegraphStartTimes[1] - Ctx->AttackEndTimes[0];
			Note(Test, FString::Printf(TEXT("G5: unparried cycle — next attack %.2f s after the previous one ended (Recovery %.1f s)"), Gap, RecoverySeconds));
			Test.TestTrue(TEXT("G5: the unparried cycle waits only the recovery time"), FMath::Abs(Gap - RecoverySeconds) <= TimingSlack);

			const AAstralPlayerController* PC = PawnIn(ServerWorld, Ctx->NearId) ? Cast<AAstralPlayerController>(PawnIn(ServerWorld, Ctx->NearId)->GetController()) : nullptr;
			UAstralAbilitySystemComponent* ASC = PC ? PC->GetAstralAbilitySystemComponent() : nullptr;
			if (!Test.TestNotNull(TEXT("G5: near hero's ASC on the server"), ASC))
			{
				Ctx->bAborted = true;
				return;
			}
			ASC->SetLooseGameplayTagCount(FGameplayTag::RequestGameplayTag(ParryTagName), 1);
			Ctx->NearHealthBefore = HealthOf(PawnIn(ServerWorld, Ctx->NearId));
		});
		WaitSampling(Ctx, TEXT("G5: the parried sweep lands (second telegraph ends)"), 10.0, [Ctx]() { return Ctx->TelegraphEndTimes.Num() >= 2; });
		Do(Ctx, [Ctx]()
		{
			UWorld* ServerWorld = FindServerWorld();
			Ctx->Test->TestEqual(TEXT("G5: a parried attack does no damage"), HealthOf(PawnIn(ServerWorld, Ctx->NearId)), Ctx->NearHealthBefore);
			Ctx->Test->TestTrue(TEXT("G5: the attack ability is still active right after the parried sweep (staggered)"), EnemyAttackActive(*Ctx));

			// 다음 공격은 막지 않는다
			if (const AAstralPlayerController* PC = Cast<AAstralPlayerController>(PawnIn(ServerWorld, Ctx->NearId)->GetController()))
			{
				PC->GetAstralAbilitySystemComponent()->SetLooseGameplayTagCount(FGameplayTag::RequestGameplayTag(ParryTagName), 0);
			}
		});

		// 패링당하면 몽타주를 멈춘다 — 서버는 바로, 클라이언트는 복제 뒤
		Observe(Ctx, 0.6);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			Test.TestFalse(TEXT("G5: the parried attack's montage stops on the server"), MontagePlayingIn(*Ctx, FindServerWorld()));
			for (UWorld* ClientWorld : GetClientWorlds())
			{
				Test.TestFalse(TEXT("G5: the parried attack's montage stops on the client"), MontagePlayingIn(*Ctx, ClientWorld));
			}
			Test.TestTrue(TEXT("G5: the ability holds while the montage is stopped (stagger)"), EnemyAttackActive(*Ctx));
		});

		WaitSampling(Ctx, TEXT("G5: the staggered attack ends and the next attack starts"), 20.0, [Ctx]() { return Ctx->AttackEndTimes.Num() >= 2 && Ctx->TelegraphStartTimes.Num() >= 3; });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const double Sweep = Ctx->TelegraphEndTimes[1];
			const double StaggerHeld = Ctx->AttackEndTimes[1] - Sweep;
			const double NextAttack = Ctx->TelegraphStartTimes[2] - Sweep;
			Note(Test, FString::Printf(TEXT("G5: parried — hit notify %.2f s after the start, ability stayed active %.2f s after the sweep (StaggerRecovery %.1f s), next attack %.2f s after the sweep, hero hits so far %d"),
				Sweep - Ctx->TelegraphStartTimes[1], StaggerHeld, Ctx->StaggerSeconds, NextAttack, Ctx->HitTimes.Num()));
			Test.TestTrue(TEXT("G5: the staggered attack holds for StaggerRecovery"), FMath::Abs(StaggerHeld - Ctx->StaggerSeconds) <= TimingSlack);
			Test.TestTrue(TEXT("G5: no new attack during the stagger"), NextAttack >= Ctx->StaggerSeconds + RecoverySeconds - TimingSlack);
			Test.TestEqual(TEXT("G5: the parried attack never lowered the hero's health"), Ctx->HitTimes.Num(), Ctx->NumHitNotifies);
		});
	}

	void EnqueueDeath(const TSharedRef<FContext>& Ctx)
	{
		// G4 — 세 번째 공격의 준비 동작 중에 죽인다: 몽타주가 멈추고, 모든 머신의 AnimInstance 가 사망을 보고, 폰이 사라진다
		Observe(Ctx, 0.3);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			if (!Test.TestTrue(TEXT("G4: guardian alive before the kill"), Ctx->Enemy.IsValid() && !IsDead(Ctx->Enemy.Get())))
			{
				Ctx->bAborted = true;
				return;
			}
			const AAstralEnemyController* Controller = EnemyController(*Ctx);
			const bool bMontageBefore = MontagePlayingIn(*Ctx, ServerWorld);
			const UAstralEnemyAnimInstance* ServerAnim = GuardianAnimIn(ServerWorld);
			Test.TestTrue(TEXT("G4: the anim instance reads alive before the kill"), ServerAnim && !ServerAnim->IsDead());

			Ctx->Enemy->DamageSelf(100000.f);

			Test.TestTrue(TEXT("G4: guardian is dying"), IsDead(Ctx->Enemy.Get()));
			Test.TestTrue(TEXT("G4: the tree stopped at death"), Controller && !Controller->GetStateTreeComponent()->IsRunning());
			Test.TestTrue(TEXT("G4: the guardian was mid-attack when killed"), bMontageBefore);
			Test.TestFalse(TEXT("G4: death cancels the attack and stops its montage on the server"), MontagePlayingIn(*Ctx, ServerWorld) || EnemyAttackActive(*Ctx));
			Ctx->MarkTime = ServerTime();
		});
		WaitUntil(Ctx, TEXT("G4: the anim instance reads dead on the server and on every client"), 4.0, [Ctx]()
		{
			for (UWorld* World : GetPieWorlds())
			{
				const UAstralEnemyAnimInstance* Anim = GuardianAnimIn(World);
				if (!Anim || !Anim->IsDead())
				{
					return false;
				}
			}
			return true;
		}, [Ctx]() { return Describe(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			Note(*Ctx->Test, FString::Printf(TEXT("G4: every machine's anim instance read dead %.2f s after the death"), ServerTime() - Ctx->MarkTime));
			for (UWorld* ClientWorld : GetClientWorlds())
			{
				Ctx->Test->TestFalse(TEXT("G4: the attack montage is not playing on the client after the death"), MontagePlayingIn(*Ctx, ClientWorld));
			}
		});
		WaitUntil(Ctx, TEXT("G4: the guardian pawn is gone on the server and on every client"), 30.0, [Ctx]()
		{
			for (UWorld* World : GetPieWorlds())
			{
				if (GuardiansIn(World).Num() != 0)
				{
					return false;
				}
			}
			return true;
		}, [Ctx]() { return Describe(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			Note(*Ctx->Test, FString::Printf(TEXT("G4: guardian removed everywhere %.2f s after its death"), ServerTime() - Ctx->MarkTime));
			Ctx->Test->TestEqual(TEXT("G4: no enemy controller left on the server"), NumEnemyControllersIn(FindServerWorld()), 0);
		});
	}

	void EnqueueGuardian(FAutomationTestBase& Test, bool bDedicated)
	{
		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;
		Ctx->bDedicated = bDedicated;

		// PIE 시작 때 엔진이 내는 경고 — NavMesh 등록 전에 군중 매니저가 만들어진다. 이 시험과 무관하다
		Test.AddExpectedMessage(TEXT("Unable to find RecastNavMesh instance while trying to create UCrowdManager instance"), ELogVerbosity::Warning, EAutomationExpectedMessageFlags::Contains, -1, /*IsRegex=*/false);

		EnqueueSetup(Ctx);
		EnqueueChaseAndHit(Ctx);
		EnqueueParry(Ctx);
		EnqueueDeath(Ctx);
		EndPie(Ctx);
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemyGuardianListenPieTest, "AstralBreak.Net.EnemyGuardian.ListenPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralEnemyGuardianListenPieTest::RunTest(const FString& Parameters)
{
	AstralEnemyGuardianPie::EnqueueGuardian(*this, /*bDedicated=*/false);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemyGuardianDedicatedPieTest, "AstralBreak.Net.EnemyGuardian.DedicatedPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralEnemyGuardianDedicatedPieTest::RunTest(const FString& Parameters)
{
	AstralEnemyGuardianPie::EnqueueGuardian(*this, /*bDedicated=*/true);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
