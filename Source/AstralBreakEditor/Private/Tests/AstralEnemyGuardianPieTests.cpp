// 단위 C1 · C2 수호병 네트워크 시험 — 한 프로세스 멀티 PIE (설계 Docs/Design/m3-enemy-ai.md §10 C2 검증 계획 C2-0 · H1 ~ H5, C1 의 G1 · G2 · G4 를 이어 본다)
//
// 리슨 서버 · Dedicated 를 PIE 로 띄워 CombatTestMap 에서 수호병(BP_Enemy_Guardian)을 클라이언트의 디버그 명령으로 부르고,
// 서버 월드와 각 클라이언트 월드의 폰 · 어빌리티 · 태그 · 몽타주 재생 상태를 직접 본다.
//
// 앞 절반 — 트리를 돌린 채 (무작위 선택과 경직 전환은 트리의 일이다)
//   G1 · G2   메시 · ABP · 추격 속도 (C1 에서 이어 본다)
//   H4        피격 반응: 맞으면 클라이언트에서 몽타주 재생 · 간격 안의 두 번째는 반응 없음
//   C2-0b     Root 의 Staggered 전환이 Chase · Attack(패링 — 공격이 취소로 끝나는 같은 틱) · Recovery 에서 와도 Stagger 로 간다
//             — 행동으로 본다: 태그가 붙어 있는 동안 멈춰 서고(추격 중), 공격을 시작하지 않는다
//   H5        트리가 두 공격을 다 쓴다 (C2-0a)
//   H3        경직: 패링 뒤 StaggerDuration 동안 공격 없음 → 끝나면 다시 공격한다
// 뒤 절반 — 트리를 멈추고(StopLogic) 서버에서 공격 어빌리티를 직접 발동한다 (방어 규칙은 무작위에 기대지 않는다)
//   H1        연타: 타격 노티파이마다 피해 · 가드하면 감쇄 · 패링하면 0 + 남은 타격 없음
//   H2        강공격: 가드해도 전액 · 패링하면 0
//   H3        경직 동안 받는 피해 배율(약점 노출 GE) · 끝나면 배율이 돌아온다
//   H4        공격 중에는 피격 반응 없음
//   G4        사망: 공격 중에 죽이면 몽타주가 멈추고 폰이 사라진다
//
// 기대값(피해 · 타격 시각 · 경직 길이 · 간격 · 배율)은 수호병의 어빌리티 CDO · 몽타주 · GE 에서 읽는다 — 잠정값을 바꿔도 시험은 그대로다.
// 방어는 히어로의 방어 태그를 서버에서 직접 세운다(히어로의 실제 입력은 쓰지 않는다). 히어로의 체력은 시험이 채워 준다(트리를 오래 돌려도 죽지 않게).
// PIE 는 적이 사라진 뒤에 내린다 — 재생 중인 몽타주가 없다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AstralPieTestHelpers.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Abilities/Enemy/AstralGA_Enemy_HitReact.h"
#include "AbilitySystem/Abilities/Enemy/AstralGA_Enemy_MeleeAttack.h"
#include "AbilitySystem/Abilities/Enemy/AstralGA_Enemy_Stagger.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
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
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerState.h"
#include "GameplayAbilitySpec.h"
#include "GameplayEffect.h"
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
	const TCHAR* const ParryTagName = TEXT("State.Defense.Parrying");
	const TCHAR* const GuardTagName = TEXT("State.Defense.Guarding");
	const TCHAR* const ComboAbilityTagName = TEXT("Ability.Enemy.Attack.Combo");
	const TCHAR* const HeavyAbilityTagName = TEXT("Ability.Enemy.Attack.Heavy");
	const TCHAR* const StaggeredTagName = TEXT("State.Enemy.Staggered");
	const TCHAR* const AttackingTagName = TEXT("State.Enemy.Attacking");
	const TCHAR* const UnguardableTagName = TEXT("Damage.Type.Unguardable");

	// ST_Enemy_Guardian 의 값(잠정) — 바꾸면 여기도 바꾼다
	constexpr double RecoverySeconds = 1.0;

	/** 표본이 프레임 단위라 생기는 오차 + 상태 전환 프레임 */
	constexpr double TimingSlack = 0.35;


	// CombatTestMap 좌표 — AstralEnemyCombatPieTests 와 같은 자리(맵의 더미와 떨어진 NavMesh 위)
	const FVector NearHeroLocation(1100.0, -400.0, 92.0);
	const FVector FarHeroLocation(1100.0, 900.0, 92.0);
	constexpr float EnemySpawnDistance = 600.f;

	/** 공격 어빌리티 하나의 기대값 — CDO 와 몽타주에서 읽는다 */
	struct FAttackData
	{
		const TCHAR* TagName = nullptr;
		TWeakObjectPtr<UAnimMontage> Montage;
		float Damage = 0.f;
		bool bUnguardable = false;
		/** 발동 → 각 타격 노티파이 (준비 · 휘두름 재생 속도 반영) */
		TArray<double> HitSeconds;
	};

	struct FContext : FContextBase
	{
		bool bDedicated = false;
		int32 NumPlayers = 2;

		/** 가까운 쪽 = 클라이언트 자리의 플레이어(적을 부른다), 먼 쪽 = 나머지 */
		int32 NearId = 0;
		int32 FarId = 0;

		TWeakObjectPtr<AAstralCombatCharacter> Enemy;

		// 수호병의 어빌리티 CDO · 몽타주 · GE 에서 읽은 기대값
		FAttackData Combo;
		FAttackData Heavy;
		TArray<TWeakObjectPtr<UAnimMontage>> ReactMontages;
		TWeakObjectPtr<UAnimMontage> StaggerMontage;
		double ReactInterval = 0.0;
		double StaggerSeconds = 0.0;
		float ExposedMultiplier = 1.f;
		/** Recovery 에 들어간 뒤 이만큼 지나 때린다 — 움찔이 Recovery 의 끝(= 다음 공격)을 넘겨야 '전환이 먹었다' 를 가를 수 있다. 움찔 몽타주 길이에서 정한다 */
		double RecoveryPokeDelay = 0.75;

		// 매 프레임 표본 — 서버
		bool bAttackActive = false;
		bool bStaggered = false;
		bool bReacting = false;
		/** 마지막으로 피격 반응 어빌리티가 켜진 시각 */
		double LastReactStart = -1000.0;
		float LastNearHealth = -1.f;
		int32 ComboStarts = 0;
		int32 HeavyStarts = 0;
		FString AttackSequence;
		TArray<double> AttackStartTimes;
		TArray<double> AttackEndTimes;
		TArray<double> StaggerOnTimes;
		TArray<double> StaggerOffTimes;
		int32 AttackStartsWhileStaggered = 0;
		/** 지금(또는 마지막) 행동 불가 구간에서 본 가장 느린 이동 속도 */
		float MinSpeedInStagger = 0.f;
		TArray<double> HitTimes;
		TArray<float> HitAmounts;

		/** 트리를 돌리는 동안 가까운 히어로의 체력을 채운다 */
		bool bKeepHeroAlive = true;

		// 매 프레임 표본 — 클라이언트 월드별
		TMap<const UWorld*, float> ClientMaxSpeed;
		TMap<const UWorld*, TSet<const UAnimMontage*>> ClientSeenMontages;

		// 단계 사이에 넘기는 값
		float NearHealthBefore = 0.f;
		double MarkTime = 0.0;
		int32 MarkCount = 0;
		double FirstReactTime = 0.0;
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

	UAbilitySystemComponent* EnemyASC(const FContext& Ctx)
	{
		return Ctx.Enemy.IsValid() ? Ctx.Enemy->GetAbilitySystemComponent() : nullptr;
	}

	bool EnemyHasTag(const FContext& Ctx, const TCHAR* TagName)
	{
		const UAbilitySystemComponent* ASC = EnemyASC(Ctx);
		return ASC && ASC->HasMatchingGameplayTag(FGameplayTag::RequestGameplayTag(TagName));
	}

	const FGameplayAbilitySpec* SpecByTag(const FContext& Ctx, const TCHAR* AbilityTagName)
	{
		const UAbilitySystemComponent* ASC = EnemyASC(Ctx);
		if (!ASC)
		{
			return nullptr;
		}
		TArray<FGameplayAbilitySpec*> Specs;
		ASC->GetActivatableGameplayAbilitySpecsByAllMatchingTags(FGameplayTagContainer(FGameplayTag::RequestGameplayTag(AbilityTagName)), Specs, false);
		return Specs.Num() > 0 ? Specs[0] : nullptr;
	}

	template <typename AbilityType>
	const FGameplayAbilitySpec* SpecByClass(const FContext& Ctx)
	{
		if (const UAbilitySystemComponent* ASC = EnemyASC(Ctx))
		{
			for (const FGameplayAbilitySpec& Spec : ASC->GetActivatableAbilities())
			{
				if (Spec.Ability && Spec.Ability->IsA<AbilityType>())
				{
					return &Spec;
				}
			}
		}
		return nullptr;
	}

	bool IsSpecActive(const FGameplayAbilitySpec* Spec)
	{
		return Spec && Spec->IsActive();
	}

	bool AnyAttackActive(const FContext& Ctx)
	{
		return IsSpecActive(SpecByTag(Ctx, ComboAbilityTagName)) || IsSpecActive(SpecByTag(Ctx, HeavyAbilityTagName));
	}

	UAstralAbilitySystemComponent* NearHeroASC(const FContext& Ctx)
	{
		const AAstralCharacter* Pawn = PawnIn(FindServerWorld(), Ctx.NearId);
		const AAstralPlayerController* PC = Pawn ? Cast<AAstralPlayerController>(Pawn->GetController()) : nullptr;
		return PC ? PC->GetAstralAbilitySystemComponent() : nullptr;
	}

	void SetHeroTag(const FContext& Ctx, const TCHAR* TagName, bool bOn)
	{
		if (UAstralAbilitySystemComponent* ASC = NearHeroASC(Ctx))
		{
			ASC->SetLooseGameplayTagCount(FGameplayTag::RequestGameplayTag(TagName), bOn ? 1 : 0);
		}
	}

	/** 가까운 히어로의 체력을 최대로 — 서버에서 속성 값을 직접 쓴다. 다음 표본이 '맞았다' 로 읽지 않게 기준도 올린다 */
	void HealHero(FContext& Ctx)
	{
		if (UAstralAbilitySystemComponent* ASC = NearHeroASC(Ctx))
		{
			ASC->SetNumericAttributeBase(UAstralHealthSet::GetHealthAttribute(), ASC->GetNumericAttribute(UAstralHealthSet::GetMaxHealthAttribute()));
			Ctx.LastNearHealth = HealthOf(PawnIn(FindServerWorld(), Ctx.NearId));
		}
	}

	float EnemyIncomingMultiplier(const FContext& Ctx)
	{
		const UAbilitySystemComponent* ASC = EnemyASC(Ctx);
		return ASC ? ASC->GetNumericAttribute(UAstralHealthSet::GetIncomingDamageMultiplierAttribute()) : 0.f;
	}

	bool MontagePlayingIn(const UAnimMontage* Montage, UWorld* World)
	{
		const UAstralEnemyAnimInstance* Anim = GuardianAnimIn(World);
		return Anim && Montage && Anim->Montage_IsPlaying(Montage);
	}

	int32 NumClientsThatSaw(const FContext& Ctx, const TArray<TWeakObjectPtr<UAnimMontage>>& Montages)
	{
		int32 Count = 0;
		for (const TPair<const UWorld*, TSet<const UAnimMontage*>>& Seen : Ctx.ClientSeenMontages)
		{
			for (const TWeakObjectPtr<UAnimMontage>& Montage : Montages)
			{
				if (Montage.IsValid() && Seen.Value.Contains(Montage.Get()))
				{
					++Count;
					break;
				}
			}
		}
		return Count;
	}

	double ServerTime()
	{
		const UWorld* World = FindServerWorld();
		return World ? World->GetTimeSeconds() : 0.0;
	}

	/** 서버에서 공격 어빌리티를 직접 발동한다 — 트리의 ActivateAbility Task 와 같은 호출(스펙 지정 + 타깃을 실은 이벤트 데이터) */
	bool ActivateAttack(const FContext& Ctx, const TCHAR* AbilityTagName)
	{
		UAbilitySystemComponent* ASC = EnemyASC(Ctx);
		const FGameplayAbilitySpec* Spec = SpecByTag(Ctx, AbilityTagName);
		if (!ASC || !Spec)
		{
			return false;
		}
		const FGameplayTag AbilityTag = FGameplayTag::RequestGameplayTag(AbilityTagName);
		FGameplayEventData Payload;
		Payload.EventTag = AbilityTag;
		Payload.Instigator = Ctx.Enemy.Get();
		Payload.Target = PawnIn(FindServerWorld(), Ctx.NearId);
		return ASC->TriggerAbilityFromGameplayEvent(Spec->Handle, ASC->AbilityActorInfo.Get(), AbilityTag, &Payload, *ASC);
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

		const bool bStaggered = EnemyHasTag(Ctx, StaggeredTagName);
		if (bStaggered != Ctx.bStaggered)
		{
			(bStaggered ? Ctx.StaggerOnTimes : Ctx.StaggerOffTimes).Add(Now);
			if (bStaggered)
			{
				Ctx.MinSpeedInStagger = TNumericLimits<float>::Max();
			}
			Ctx.bStaggered = bStaggered;
		}
		if (bStaggered)
		{
			Ctx.MinSpeedInStagger = FMath::Min(Ctx.MinSpeedInStagger, static_cast<float>(Ctx.Enemy->GetVelocity().Size2D()));
		}

		const bool bReacting = IsSpecActive(SpecByClass<UAstralGA_Enemy_HitReact>(Ctx));
		if (bReacting && !Ctx.bReacting)
		{
			Ctx.LastReactStart = Now;
		}
		Ctx.bReacting = bReacting;

		const bool bCombo = IsSpecActive(SpecByTag(Ctx, ComboAbilityTagName));
		const bool bAttackActive = bCombo || IsSpecActive(SpecByTag(Ctx, HeavyAbilityTagName));
		if (bAttackActive != Ctx.bAttackActive)
		{
			if (bAttackActive)
			{
				Ctx.AttackStartTimes.Add(Now);
				Ctx.AttackSequence.AppendChar(bCombo ? TEXT('C') : TEXT('H'));
				++(bCombo ? Ctx.ComboStarts : Ctx.HeavyStarts);
				if (bStaggered)
				{
					++Ctx.AttackStartsWhileStaggered;
				}
			}
			else
			{
				Ctx.AttackEndTimes.Add(Now);
			}
			Ctx.bAttackActive = bAttackActive;
		}

		const float NearHealth = HealthOf(PawnIn(ServerWorld, Ctx.NearId));
		if (Ctx.LastNearHealth >= 0.f && NearHealth < Ctx.LastNearHealth)
		{
			Ctx.HitTimes.Add(Now);
			Ctx.HitAmounts.Add(Ctx.LastNearHealth - NearHealth);
		}
		Ctx.LastNearHealth = NearHealth;
		if (Ctx.bKeepHeroAlive && NearHealth > 0.f && NearHealth < 60.f)
		{
			HealHero(Ctx);
		}

		for (UWorld* ClientWorld : GetClientWorlds())
		{
			if (const UAstralEnemyAnimInstance* Anim = GuardianAnimIn(ClientWorld))
			{
				float& MaxSpeed = Ctx.ClientMaxSpeed.FindOrAdd(ClientWorld, 0.f);
				MaxSpeed = FMath::Max(MaxSpeed, Anim->GetGroundSpeed());

				if (const UAnimMontage* Montage = Anim->GetCurrentActiveMontage())
				{
					Ctx.ClientSeenMontages.FindOrAdd(ClientWorld).Add(Montage);
				}
			}
		}
	}

	FString Describe(const FContext& Ctx)
	{
		const UWorld* ServerWorld = FindServerWorld();
		const AAstralEnemyController* Controller = EnemyController(Ctx);
		return FString::Printf(TEXT("server map '%s', seats %d, near hp %.0f, enemy %s hp %.0f at %s speed %.0f, target %s, tree running %d, attacks '%s' (ends %d, active %d), staggered tag on %d off %d (now %d), attack starts while staggered %d, hits %d"),
			*MapOf(ServerWorld), GetSeatWorlds().Num(),
			HealthOf(PawnIn(ServerWorld, Ctx.NearId)),
			Ctx.Enemy.IsValid() ? *Ctx.Enemy->GetName() : TEXT("none"), HealthOf(Ctx.Enemy.Get()),
			Ctx.Enemy.IsValid() ? *Ctx.Enemy->GetActorLocation().ToCompactString() : TEXT("-"),
			Ctx.Enemy.IsValid() ? Ctx.Enemy->GetVelocity().Size2D() : 0.0,
			Controller ? *GetNameSafe(Controller->GetCurrentTarget()) : TEXT("-"),
			(Controller && Controller->GetStateTreeComponent()->IsRunning()) ? 1 : 0,
			*Ctx.AttackSequence, Ctx.AttackEndTimes.Num(), AnyAttackActive(Ctx) ? 1 : 0,
			Ctx.StaggerOnTimes.Num(), Ctx.StaggerOffTimes.Num(), EnemyHasTag(Ctx, StaggeredTagName) ? 1 : 0,
			Ctx.AttackStartsWhileStaggered, Ctx.HitTimes.Num());
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

	/** 서버 시간으로 Seconds() 동안 표본만 뜬다 — 길이는 그 단계가 돌 때 읽는다(앞 단계가 정한 값을 쓸 수 있다) */
	void Observe(const TSharedRef<FContext>& Ctx, TFunction<double()> Seconds)
	{
		TSharedRef<double> StartTime = MakeShared<double>(-1.0);
		Step([Ctx, Seconds = MoveTemp(Seconds), StartTime]() -> bool
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
			return ServerTime() - *StartTime >= Seconds();
		});
	}

	void Observe(const TSharedRef<FContext>& Ctx, double Seconds)
	{
		Observe(Ctx, [Seconds]() { return Seconds; });
	}

	/** 공격 어빌리티 하나의 기대값을 CDO 와 몽타주에서 읽는다 */
	bool ReadAttackData(FAutomationTestBase& Test, const FContext& Ctx, const TCHAR* AbilityTagName, FAttackData& Out)
	{
		const FGameplayAbilitySpec* Spec = SpecByTag(Ctx, AbilityTagName);
		const UAstralGA_Enemy_MeleeAttack* Ability = Spec ? Cast<UAstralGA_Enemy_MeleeAttack>(Spec->Ability) : nullptr;
		UAnimMontage* Montage = Ability ? Ability->GetAttackMontage() : nullptr;
		if (!Test.TestTrue(FString::Printf(TEXT("the guardian has an attack ability tagged %s"), AbilityTagName), Ability != nullptr) || !Test.TestTrue(FString::Printf(TEXT("%s uses a montage"), AbilityTagName), Montage != nullptr))
		{
			return false;
		}

		Out.TagName = AbilityTagName;
		Out.Montage = Montage;
		Out.Damage = Ability->GetBaseDamage();
		Out.bUnguardable = Ability->GetDamageTags().HasTag(FGameplayTag::RequestGameplayTag(UnguardableTagName));
		for (const FAnimNotifyEvent& NotifyEvent : Montage->Notifies)
		{
			const UAstralAnimNotify_GameplayEvent* HitNotify = Cast<UAstralAnimNotify_GameplayEvent>(NotifyEvent.Notify);
			if (HitNotify && HitNotify->GetEventTag() == Ability->GetHitEventTag())
			{
				Out.HitSeconds.Add(Ability->GetSecondsAtMontageTime(NotifyEvent.GetTriggerTime()));
			}
		}
		Out.HitSeconds.Sort();
		if (!Test.TestTrue(FString::Printf(TEXT("%s's montage has a hit notify"), AbilityTagName), Out.HitSeconds.Num() > 0))
		{
			return false;
		}

		FString Hits;
		for (const double Seconds : Out.HitSeconds)
		{
			Hits += FString::Printf(TEXT("%s%.2f"), Hits.IsEmpty() ? TEXT("") : TEXT(" / "), Seconds);
		}
		Note(Test, FString::Printf(TEXT("data %s: montage %s (%.2f s), prepare rate %.2f, swing rate %.2f, damage %.1f per hit, unguardable %d, stagger recovery %.1f, hits at %s s after the start"),
			AbilityTagName, *Montage->GetName(), Montage->GetPlayLength(), Ability->GetMontagePlayRate(), Ability->GetSwingPlayRate(), Out.Damage, Out.bUnguardable ? 1 : 0, Ability->GetStaggerRecovery(), *Hits));
		return true;
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

			// 서버에서 자리를 잡는다. 둘 다 +X 를 본다 — 적은 가까운 쪽의 정면에 나온다(방어의 정면 판정은 방어자의 전방 기준). 적은 옮기지 않는다
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

		// 기대값 — 수호병의 어빌리티 CDO · 몽타주 · GE 에서 읽는다
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			if (!ReadAttackData(Test, *Ctx, ComboAbilityTagName, Ctx->Combo) || !ReadAttackData(Test, *Ctx, HeavyAbilityTagName, Ctx->Heavy))
			{
				Ctx->bAborted = true;
				return;
			}

			const FGameplayAbilitySpec* ReactSpec = SpecByClass<UAstralGA_Enemy_HitReact>(*Ctx);
			const FGameplayAbilitySpec* StaggerSpec = SpecByClass<UAstralGA_Enemy_Stagger>(*Ctx);
			const UAstralGA_Enemy_HitReact* React = ReactSpec ? Cast<UAstralGA_Enemy_HitReact>(ReactSpec->Ability) : nullptr;
			const UAstralGA_Enemy_Stagger* Stagger = StaggerSpec ? Cast<UAstralGA_Enemy_Stagger>(StaggerSpec->Ability) : nullptr;
			if (!Test.TestNotNull(TEXT("the guardian has a hit react ability"), React) || !Test.TestNotNull(TEXT("the guardian has a stagger ability"), Stagger))
			{
				Ctx->bAborted = true;
				return;
			}

			Ctx->ReactMontages = { React->GetFrontMontage(), React->GetBackMontage(), React->GetLeftMontage(), React->GetRightMontage() };
			Ctx->ReactInterval = React->GetMinInterval();
			Ctx->StaggerMontage = Stagger->GetStaggerMontage();
			Ctx->StaggerSeconds = Stagger->GetStaggerDuration();
			if (const UGameplayEffect* Exposed = Stagger->GetExposedEffectClass().GetDefaultObject())
			{
				for (const FGameplayModifierInfo& Modifier : Exposed->Modifiers)
				{
					if (Modifier.Attribute == UAstralHealthSet::GetIncomingDamageMultiplierAttribute())
					{
						Modifier.ModifierMagnitude.GetStaticMagnitudeIfPossible(1.f, Ctx->ExposedMultiplier);
					}
				}
			}
			Test.TestTrue(TEXT("the hit react ability has its four montages"), React->GetFrontMontage() && React->GetBackMontage() && React->GetLeftMontage() && React->GetRightMontage());
			if (const UAnimMontage* Front = React->GetFrontMontage())
			{
				// 자기 자신이 준 피해(DamageSelf)에는 앞 몽타주로 움찔한다. 어빌리티는 블렌드 아웃이 시작될 때 끝난다
				const double ReactSeconds = Front->GetPlayLength() - Front->BlendOut.GetBlendTime();
				Ctx->RecoveryPokeDelay = FMath::Clamp(RecoverySeconds - 0.5 * ReactSeconds, 0.2, RecoverySeconds - 0.15);
			}
			Test.TestTrue(TEXT("the stagger ability has a montage and an exposed effect that raises incoming damage"), Ctx->StaggerMontage.IsValid() && Ctx->ExposedMultiplier > 1.f);
			Note(Test, FString::Printf(TEXT("data hit react: interval %.1f s, front montage %s (%.2f s) | stagger: %.1f s, montage %s (%.2f s), exposed effect x%.2f incoming damage"),
				Ctx->ReactInterval, *GetNameSafe(React->GetFrontMontage()), React->GetFrontMontage() ? React->GetFrontMontage()->GetPlayLength() : 0.f,
				Ctx->StaggerSeconds, *GetNameSafe(Stagger->GetStaggerMontage()), Stagger->GetStaggerMontage() ? Stagger->GetStaggerMontage()->GetPlayLength() : 0.f, Ctx->ExposedMultiplier));
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
			}

			UWorld* ServerWorld = FindServerWorld();
			const AAstralEnemyController* Controller = EnemyController(*Ctx);
			Note(Test, FString::Printf(TEXT("G1: controller %s"), Controller ? *Controller->GetClass()->GetName() : TEXT("none")));
			Test.TestEqual(TEXT("one enemy controller on the server"), NumEnemyControllersIn(ServerWorld), 1);
			for (UWorld* ClientWorld : GetClientWorlds())
			{
				Test.TestEqual(TEXT("no enemy controller on a client"), NumEnemyControllersIn(ClientWorld), 0);
			}
		});
	}

	void EnqueueChaseHitReact(const TSharedRef<FContext>& Ctx)
	{
		// C2-0b(Chase) · H4 — 달려오는 중에 때린다: 움찔하고(클라이언트도 본다), 그동안 멈춰 선다(= 트리가 Chase 를 나갔다)
		WaitSampling(Ctx, TEXT("the guardian runs toward the near hero"), 15.0, [Ctx]()
		{
			return Ctx->Enemy.IsValid() && Ctx->Enemy->GetVelocity().Size2D() > 150.0 && !AnyAttackActive(*Ctx);
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const float Before = HealthOf(Ctx->Enemy.Get());
			Ctx->MarkCount = Ctx->StaggerOnTimes.Num();
			Ctx->FirstReactTime = ServerTime();

			Ctx->Enemy->DamageSelf(1.f);

			Test.TestTrue(TEXT("H4: a hit while chasing starts the hit react (State.Enemy.Staggered goes up inside the damage call)"), EnemyHasTag(*Ctx, StaggeredTagName) && IsSpecActive(SpecByClass<UAstralGA_Enemy_HitReact>(*Ctx)));
			Test.TestTrue(TEXT("H3 baseline: an unexposed guardian takes the damage as is"), FMath::IsNearlyEqual(Before - HealthOf(Ctx->Enemy.Get()), 1.f, 0.01f));
		});
		WaitSampling(Ctx, TEXT("H4: the hit react ends (State.Enemy.Staggered drops)"), 6.0, [Ctx]()
		{
			return Ctx->StaggerOnTimes.Num() > Ctx->MarkCount && Ctx->StaggerOffTimes.Num() == Ctx->StaggerOnTimes.Num();
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const double Lasted = Ctx->StaggerOffTimes.Last() - Ctx->StaggerOnTimes.Last();
			const double Distance = FVector::Dist2D(Ctx->Enemy->GetActorLocation(), PawnIn(FindServerWorld(), Ctx->NearId)->GetActorLocation());
			const int32 NumClients = GetClientWorlds().Num();
			Note(Test, FString::Printf(TEXT("H4 / C2-0b (Chase): hit react lasted %.2f s, slowest speed during it %.0f cm/s (running %.0f), %.0f cm from the hero when it ended, %d of %d client(s) saw a hit react montage"),
				Lasted, Ctx->MinSpeedInStagger, Ctx->Enemy->GetCharacterMovement() ? Ctx->Enemy->GetCharacterMovement()->GetMaxSpeed() : 0.f, Distance, NumClientsThatSaw(*Ctx, Ctx->ReactMontages), NumClients));

			Test.TestTrue(TEXT("C2-0b (Chase): the guardian stops while it is staggered — the tree left Chase for Stagger"), Ctx->MinSpeedInStagger < 30.f);
			Test.TestEqual(TEXT("H4: every client played the hit react montage"), NumClientsThatSaw(*Ctx, Ctx->ReactMontages), NumClients);

			// 간격 안의 두 번째 — 반응 없음
			const double SinceFirst = ServerTime() - Ctx->FirstReactTime;
			Ctx->Enemy->DamageSelf(1.f);
			Test.TestTrue(TEXT("H4: the second hit comes inside the interval"), SinceFirst < Ctx->ReactInterval);
			Test.TestFalse(TEXT("H4: a second hit inside the interval does not start another hit react"), EnemyHasTag(*Ctx, StaggeredTagName));
			Note(Test, FString::Printf(TEXT("H4: second hit %.2f s after the first (interval %.1f s) — no react"), SinceFirst, Ctx->ReactInterval));

			// G2 — 추격 중 클라이언트 AnimInstance 의 속도
			Test.TestEqual(TEXT("G2: every client's anim instance was sampled during the chase"), Ctx->ClientMaxSpeed.Num(), NumClients);
			for (const TPair<const UWorld*, float>& Speed : Ctx->ClientMaxSpeed)
			{
				Test.TestTrue(TEXT("G2: the client's anim instance saw a ground speed above 0 during the chase"), Speed.Value > 10.f);
			}
		});
	}

	void EnqueueTreeAttacks(const TSharedRef<FContext>& Ctx)
	{
		// H5 (C2-0a) — 트리가 두 공격을 다 고른다. 히어로의 체력은 표본이 채운다
		WaitSampling(Ctx, TEXT("H5 (C2-0a): the tree has used both the combo and the heavy attack"), 120.0, [Ctx]()
		{
			return Ctx->ComboStarts >= 1 && Ctx->HeavyStarts >= 1;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const AAstralCharacter* NearPawn = PawnIn(FindServerWorld(), Ctx->NearId);
			Note(Test, FString::Printf(TEXT("H5 (C2-0a): attack order so far '%s' (C = combo, H = heavy), %d hit(s) on the hero, guardian stands %.0f cm from the hero"),
				*Ctx->AttackSequence, Ctx->HitTimes.Num(), FVector::Dist2D(Ctx->Enemy->GetActorLocation(), NearPawn->GetActorLocation())));
			Test.TestTrue(TEXT("H5: the tree's attacks reach the hero"), Ctx->HitTimes.Num() > 0);
			Ctx->MarkCount = Ctx->AttackStartTimes.Num();
		});

		// C2-0b(Attack) · H3 — 트리가 시작한 공격을 패링한다: 경직 GA 가 공격을 취소하고(Task 실패 → Recovery 전환 후보) 같은 틱에 Staggered 이벤트가 온다
		WaitSampling(Ctx, TEXT("the tree starts another attack (to be parried)"), 20.0, [Ctx]() { return Ctx->AttackStartTimes.Num() > Ctx->MarkCount; });
		Do(Ctx, [Ctx]()
		{
			SetHeroTag(*Ctx, ParryTagName, true);
			Ctx->NearHealthBefore = HealthOf(PawnIn(FindServerWorld(), Ctx->NearId));
			Ctx->MarkCount = Ctx->StaggerOnTimes.Num();
		});
		WaitSampling(Ctx, TEXT("H3: the parried attack staggers the guardian (State.Enemy.Staggered goes up)"), 10.0, [Ctx]() { return Ctx->StaggerOnTimes.Num() > Ctx->MarkCount; });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			SetHeroTag(*Ctx, ParryTagName, false);
			Test.TestEqual(TEXT("H3: the parried hit does no damage"), HealthOf(PawnIn(FindServerWorld(), Ctx->NearId)), Ctx->NearHealthBefore);
			Test.TestTrue(TEXT("H3: the stagger ability is active and the attack is cancelled"), IsSpecActive(SpecByClass<UAstralGA_Enemy_Stagger>(*Ctx)) && !AnyAttackActive(*Ctx));
			Ctx->MarkCount = Ctx->AttackStartTimes.Num();
			Ctx->MarkTime = Ctx->StaggerOnTimes.Last();
		});
		WaitSampling(Ctx, TEXT("H3: the stagger ends and the tree attacks again"), 15.0, [Ctx]()
		{
			return Ctx->StaggerOffTimes.Num() == Ctx->StaggerOnTimes.Num() && Ctx->AttackStartTimes.Num() > Ctx->MarkCount;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const double Staggered = Ctx->StaggerOffTimes.Last() - Ctx->MarkTime;
			const double NextAttack = Ctx->AttackStartTimes.Last() - Ctx->MarkTime;
			Note(Test, FString::Printf(TEXT("H3 / C2-0b (Attack): parried by the tree's attack '%c' — staggered %.2f s (StaggerDuration %.1f), next attack %.2f s after the parry (Recovery alone would be %.1f s), attack starts while staggered %d, %d of %d client(s) saw the stagger montage"),
				Ctx->AttackSequence.Len() >= 2 ? Ctx->AttackSequence[Ctx->AttackSequence.Len() - 2] : TEXT('?'), Staggered, Ctx->StaggerSeconds, NextAttack, RecoverySeconds,
				Ctx->AttackStartsWhileStaggered, NumClientsThatSaw(*Ctx, { Ctx->StaggerMontage }), GetClientWorlds().Num()));
			Test.TestTrue(TEXT("H3: the stagger lasts StaggerDuration"), FMath::Abs(Staggered - Ctx->StaggerSeconds) <= TimingSlack);
			Test.TestEqual(TEXT("C2-0b (Attack): no attack starts while the guardian is staggered — the event transition beat the failed attack's Recovery"), Ctx->AttackStartsWhileStaggered, 0);
			Test.TestTrue(TEXT("H3: the next attack comes only after the stagger"), NextAttack >= Ctx->StaggerSeconds - 0.1);
			Test.TestTrue(TEXT("H3: once the stagger ends the tree goes back to the target and attacks without another Recovery"), NextAttack <= Ctx->StaggerSeconds + RecoverySeconds - 0.2);
			Test.TestEqual(TEXT("H3: every client played the stagger montage"), NumClientsThatSaw(*Ctx, { Ctx->StaggerMontage }), GetClientWorlds().Num());
			Ctx->MarkCount = Ctx->AttackEndTimes.Num();
		});

		// C2-0b(Recovery) — 막지 않은 공격이 끝난 뒤 Recovery 중에 때린다: 움찔이 Recovery 의 끝을 넘기므로, 전환이 안 먹으면 태그가 붙은 채 공격이 시작된다
		WaitSampling(Ctx, TEXT("the unparried attack ends (Recovery begins)"), 15.0, [Ctx]() { return Ctx->AttackEndTimes.Num() > Ctx->MarkCount; });
		Observe(Ctx, [Ctx]() { return Ctx->RecoveryPokeDelay; });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			Ctx->MarkCount = Ctx->StaggerOnTimes.Num();
			Ctx->MarkTime = ServerTime();
			const bool bAttackBefore = AnyAttackActive(*Ctx);

			Ctx->Enemy->DamageSelf(1.f);

			Test.TestFalse(TEXT("C2-0b (Recovery): the guardian is between attacks when hit"), bAttackBefore);
			Test.TestTrue(TEXT("C2-0b (Recovery): the hit starts a hit react"), EnemyHasTag(*Ctx, StaggeredTagName));
		});
		WaitSampling(Ctx, TEXT("C2-0b (Recovery): the hit react ends and the tree attacks again"), 15.0, [Ctx]()
		{
			return Ctx->StaggerOnTimes.Num() > Ctx->MarkCount && Ctx->StaggerOffTimes.Num() == Ctx->StaggerOnTimes.Num() && Ctx->bAttackActive;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const double ReactEnd = Ctx->StaggerOffTimes.Last() - Ctx->MarkTime;
			const double NextAttack = Ctx->AttackStartTimes.Last() - Ctx->MarkTime;
			const double RecoveryLeft = RecoverySeconds - Ctx->RecoveryPokeDelay;
			Note(Test, FString::Printf(TEXT("C2-0b (Recovery): hit %.2f s into Recovery (%.2f s left) — hit react ended %.2f s later, next attack %.2f s later, attack starts while staggered %d"),
				Ctx->RecoveryPokeDelay, RecoveryLeft, ReactEnd, NextAttack, Ctx->AttackStartsWhileStaggered));
			Test.TestTrue(TEXT("C2-0b (Recovery): the hit react outlasts the rest of Recovery (otherwise this case decides nothing)"), ReactEnd > RecoveryLeft + 0.1);
			Test.TestEqual(TEXT("C2-0b (Recovery): no attack starts while the guardian is staggered — the tree left Recovery for Stagger"), Ctx->AttackStartsWhileStaggered, 0);
			Test.TestTrue(TEXT("C2-0b (Recovery): the next attack waits for the hit react"), NextAttack >= ReactEnd - 0.05);
		});
	}

	/** 트리 없이 공격 하나를 직접 발동한다. HeroTagName — 그 공격 동안 히어로에 세울 방어 태그(없으면 null) */
	void EnqueueDirectAttack(const TSharedRef<FContext>& Ctx, const TCHAR* AbilityTagName, const TCHAR* HeroTagName)
	{
		WaitSampling(Ctx, TEXT("the guardian is idle before a direct attack"), 15.0, [Ctx]() { return !AnyAttackActive(*Ctx) && !EnemyHasTag(*Ctx, StaggeredTagName); });
		Do(Ctx, [Ctx, AbilityTagName, HeroTagName]()
		{
			SetHeroTag(*Ctx, ParryTagName, false);
			SetHeroTag(*Ctx, GuardTagName, false);
			if (HeroTagName)
			{
				SetHeroTag(*Ctx, HeroTagName, true);
			}
			HealHero(*Ctx);
			Ctx->HitTimes.Reset();
			Ctx->HitAmounts.Reset();
			Ctx->NearHealthBefore = HealthOf(PawnIn(FindServerWorld(), Ctx->NearId));
			Ctx->MarkCount = Ctx->StaggerOnTimes.Num();
			Ctx->MarkTime = ServerTime();
			if (!Ctx->Test->TestTrue(FString::Printf(TEXT("direct activation of %s"), AbilityTagName), ActivateAttack(*Ctx, AbilityTagName)))
			{
				Ctx->bAborted = true;
			}
			Sample(*Ctx);
		});
	}

	/** 직접 발동한 공격이 막히지 않고 끝났다 — 타격 수 · 타격마다의 피해 · 시각 */
	void VerifyDirectHits(FContext& Ctx, const TCHAR* Label, const FAttackData& Data, float DamageScale)
	{
		FAutomationTestBase& Test = *Ctx.Test;
		FString Hits;
		bool bAmountsOk = Ctx.HitAmounts.Num() == Data.HitSeconds.Num();
		bool bTimesOk = bAmountsOk;
		for (int32 Index = 0; Index < Ctx.HitAmounts.Num(); ++Index)
		{
			const double After = Ctx.HitTimes[Index] - Ctx.MarkTime;
			Hits += FString::Printf(TEXT("%s%.1f at %.2f s"), Hits.IsEmpty() ? TEXT("") : TEXT(", "), Ctx.HitAmounts[Index], After);
			bAmountsOk &= FMath::IsNearlyEqual(Ctx.HitAmounts[Index], Data.Damage * DamageScale, 0.05f);
			bTimesOk &= Data.HitSeconds.IsValidIndex(Index) && FMath::Abs(After - Data.HitSeconds[Index]) <= TimingSlack;
		}
		Note(Test, FString::Printf(TEXT("%s: %d hit(s) — %s (expected %d x %.1f)"), Label, Ctx.HitAmounts.Num(), *Hits, Data.HitSeconds.Num(), Data.Damage * DamageScale));
		Test.TestEqual(FString::Printf(TEXT("%s: one hit per hit notify"), Label), Ctx.HitAmounts.Num(), Data.HitSeconds.Num());
		Test.TestTrue(FString::Printf(TEXT("%s: every hit deals the expected damage"), Label), bAmountsOk);
		Test.TestTrue(FString::Printf(TEXT("%s: every hit lands at its notify's time"), Label), bTimesOk);
	}

	void EnqueueDefenseRules(const TSharedRef<FContext>& Ctx)
	{
		// 트리를 멈춘다 — 여기서부터는 무작위가 없다. 나가는 상태의 Task 가 진행 중인 공격을 취소한다
		Do(Ctx, [Ctx]()
		{
			AAstralEnemyController* Controller = EnemyController(*Ctx);
			if (!Ctx->Test->TestNotNull(TEXT("guardian controller"), Controller))
			{
				Ctx->bAborted = true;
				return;
			}
			Controller->GetStateTreeComponent()->StopLogic(TEXT("AstralEnemyGuardianPie"));
			Controller->StopMovement();
			Ctx->bKeepHeroAlive = false;
			Ctx->Test->TestFalse(TEXT("the tree is stopped for the direct attacks"), Controller->GetStateTreeComponent()->IsRunning());
		});

		// H1 — 연타, 막지 않음
		EnqueueDirectAttack(Ctx, ComboAbilityTagName, nullptr);
		WaitSampling(Ctx, TEXT("H1: the combo ends"), 15.0, [Ctx]() { return !AnyAttackActive(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			VerifyDirectHits(*Ctx, TEXT("H1 combo, no defense"), Ctx->Combo, 1.f);
			Ctx->Test->TestEqual(TEXT("H1: every client played the combo montage"), NumClientsThatSaw(*Ctx, { Ctx->Combo.Montage }), GetClientWorlds().Num());
		});

		// H1 — 연타, 가드: 타격마다 감쇄
		EnqueueDirectAttack(Ctx, ComboAbilityTagName, GuardTagName);
		WaitSampling(Ctx, TEXT("H1: the guarded combo ends"), 15.0, [Ctx]() { return !AnyAttackActive(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			float GuardMultiplier = 0.5f;
			const UAstralAbilitySystemComponent* HeroASC = NearHeroASC(*Ctx);
			if (HeroASC && HeroASC->HasAttributeSetForAttribute(UAstralHeroResourceSet::GetGuardDamageMultiplierAttribute()))
			{
				GuardMultiplier = HeroASC->GetNumericAttribute(UAstralHeroResourceSet::GetGuardDamageMultiplierAttribute());
			}
			Ctx->Test->TestTrue(TEXT("H1: the hero's guard reduces damage"), GuardMultiplier < 1.f);
			VerifyDirectHits(*Ctx, *FString::Printf(TEXT("H1 combo, guarded (x%.2f)"), GuardMultiplier), Ctx->Combo, GuardMultiplier);
			SetHeroTag(*Ctx, GuardTagName, false);
		});

		// H1 · H3 — 연타, 패링: 피해 0 · 남은 타격 없음 · 경직 동안 약점 노출
		EnqueueDirectAttack(Ctx, ComboAbilityTagName, ParryTagName);
		WaitSampling(Ctx, TEXT("H1: the parried combo staggers the guardian"), 10.0, [Ctx]() { return Ctx->StaggerOnTimes.Num() > Ctx->MarkCount; });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			SetHeroTag(*Ctx, ParryTagName, false);
			Test.TestTrue(TEXT("H1: the parry cancels the combo"), !AnyAttackActive(*Ctx) && !MontagePlayingIn(Ctx->Combo.Montage.Get(), FindServerWorld()));

			// 약점 노출 — 경직 중에 받는 피해. 경직 중이라 움찔하지 않는다
			const float Multiplier = EnemyIncomingMultiplier(*Ctx);
			const float Before = HealthOf(Ctx->Enemy.Get());
			Ctx->Enemy->DamageSelf(10.f);
			const float Taken = Before - HealthOf(Ctx->Enemy.Get());
			Note(Test, FString::Printf(TEXT("H3: staggered %.2f s after the combo started (first hit notify %.2f s) — incoming damage multiplier %.2f (effect x%.2f), 10 damage took %.1f"),
				Ctx->StaggerOnTimes.Last() - Ctx->MarkTime, Ctx->Combo.HitSeconds[0], Multiplier, Ctx->ExposedMultiplier, Taken));
			Test.TestTrue(TEXT("H3: the exposed effect raises the staggered guardian's incoming damage multiplier"), FMath::IsNearlyEqual(Multiplier, Ctx->ExposedMultiplier, 0.01f));
			Test.TestTrue(TEXT("H3: a staggered guardian takes multiplied damage"), FMath::IsNearlyEqual(Taken, 10.f * Ctx->ExposedMultiplier, 0.05f));
			Test.TestFalse(TEXT("H3: a hit during the stagger does not start a hit react"), IsSpecActive(SpecByClass<UAstralGA_Enemy_HitReact>(*Ctx)));
		});
		WaitSampling(Ctx, TEXT("H3: the stagger ends"), 10.0, [Ctx]() { return Ctx->StaggerOffTimes.Num() == Ctx->StaggerOnTimes.Num(); });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const double Staggered = Ctx->StaggerOffTimes.Last() - Ctx->StaggerOnTimes.Last();
			Note(Test, FString::Printf(TEXT("H1 combo, parried: %d hit(s) on the hero, staggered %.2f s, multiplier after the stagger %.2f"), Ctx->HitAmounts.Num(), Staggered, EnemyIncomingMultiplier(*Ctx)));
			Test.TestEqual(TEXT("H1: a parried combo never lowers the hero's health — the remaining hits are gone"), Ctx->HitAmounts.Num(), 0);
			Test.TestEqual(TEXT("H1: the hero's health is unchanged"), HealthOf(PawnIn(FindServerWorld(), Ctx->NearId)), Ctx->NearHealthBefore);
			Test.TestTrue(TEXT("H3: the stagger lasts StaggerDuration"), FMath::Abs(Staggered - Ctx->StaggerSeconds) <= TimingSlack);
			Test.TestTrue(TEXT("H3: the multiplier is back to 1 after the stagger"), FMath::IsNearlyEqual(EnemyIncomingMultiplier(*Ctx), 1.f, 0.01f));
		});

		// H2 — 강공격, 가드: 전액. 도중에 수호병을 때려도 움찔하지 않는다(H4: 공격 중 — 마지막 움찔에서 간격이 지난 뒤라야 태그가 막은 것이 된다)
		EnqueueDirectAttack(Ctx, HeavyAbilityTagName, GuardTagName);
		Observe(Ctx, 0.3);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const bool bAttackingTag = EnemyHasTag(*Ctx, AttackingTagName);
			const double SinceReact = ServerTime() - Ctx->LastReactStart;

			Ctx->Enemy->DamageSelf(1.f);

			Note(Test, FString::Printf(TEXT("H4: hit 0.3 s into the heavy attack, %.2f s after the last hit react (interval %.1f s) — hit react started %d, attack still active %d"),
				SinceReact, Ctx->ReactInterval, IsSpecActive(SpecByClass<UAstralGA_Enemy_HitReact>(*Ctx)) ? 1 : 0, AnyAttackActive(*Ctx) ? 1 : 0));
			Test.TestTrue(TEXT("H4: the attack carries State.Enemy.Attacking"), bAttackingTag);
			Test.TestTrue(TEXT("H4: the interval since the last hit react has passed (so the tag is what blocks)"), SinceReact >= Ctx->ReactInterval);
			Test.TestTrue(TEXT("H4: a hit during an attack does not start a hit react — the attack goes on"), !EnemyHasTag(*Ctx, StaggeredTagName) && AnyAttackActive(*Ctx));
		});
		WaitSampling(Ctx, TEXT("H2: the guarded heavy attack ends"), 15.0, [Ctx]() { return !AnyAttackActive(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestTrue(TEXT("H2: the heavy attack's damage is tagged unguardable"), Ctx->Heavy.bUnguardable);
			VerifyDirectHits(*Ctx, TEXT("H2 heavy, guarded (unguardable — full damage)"), Ctx->Heavy, 1.f);
			Ctx->Test->TestEqual(TEXT("H2: every client played the heavy montage"), NumClientsThatSaw(*Ctx, { Ctx->Heavy.Montage }), GetClientWorlds().Num());
			SetHeroTag(*Ctx, GuardTagName, false);
		});

		// H2 — 강공격, 패링: 피해 0 · 경직
		EnqueueDirectAttack(Ctx, HeavyAbilityTagName, ParryTagName);
		WaitSampling(Ctx, TEXT("H2: the parried heavy attack staggers the guardian"), 10.0, [Ctx]() { return Ctx->StaggerOnTimes.Num() > Ctx->MarkCount; });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			SetHeroTag(*Ctx, ParryTagName, false);
			Note(Test, FString::Printf(TEXT("H2 heavy, parried: %d hit(s) on the hero, staggered %.2f s after the start (hit notify %.2f s)"), Ctx->HitAmounts.Num(), Ctx->StaggerOnTimes.Last() - Ctx->MarkTime, Ctx->Heavy.HitSeconds[0]));
			Test.TestEqual(TEXT("H2: a parried heavy attack does no damage"), HealthOf(PawnIn(FindServerWorld(), Ctx->NearId)), Ctx->NearHealthBefore);
			Test.TestTrue(TEXT("H2: the parry staggers the guardian and cancels the attack"), IsSpecActive(SpecByClass<UAstralGA_Enemy_Stagger>(*Ctx)) && !AnyAttackActive(*Ctx));
		});
	}

	void EnqueueDeath(const TSharedRef<FContext>& Ctx)
	{
		// G4 — 공격의 준비 동작 중에 죽인다: 몽타주가 멈추고, 모든 머신의 AnimInstance 가 사망을 보고, 폰이 사라진다
		EnqueueDirectAttack(Ctx, HeavyAbilityTagName, nullptr);
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
			const bool bMontageBefore = MontagePlayingIn(Ctx->Heavy.Montage.Get(), ServerWorld);

			Ctx->Enemy->DamageSelf(100000.f);

			Test.TestTrue(TEXT("G4: guardian is dying"), IsDead(Ctx->Enemy.Get()));
			Test.TestTrue(TEXT("G4: the guardian was mid-attack when killed"), bMontageBefore);
			Test.TestFalse(TEXT("G4: death cancels the attack and stops its montage on the server"), MontagePlayingIn(Ctx->Heavy.Montage.Get(), ServerWorld) || AnyAttackActive(*Ctx));
			Test.TestFalse(TEXT("G4: the killing blow does not start a hit react"), EnemyHasTag(*Ctx, StaggeredTagName));
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
		EnqueueChaseHitReact(Ctx);
		EnqueueTreeAttacks(Ctx);
		EnqueueDefenseRules(Ctx);
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
