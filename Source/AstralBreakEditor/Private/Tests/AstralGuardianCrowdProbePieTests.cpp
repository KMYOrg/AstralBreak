// M3 뒤 다듬기 측정 프로브 — 수호병 여러 마리가 한 타깃에 붙을 때의 움직임을 잰다 (Docs/Design/m3-enemy-ai.md §13 T1 · T2)
//
// 판정이 없다 — 값만 적는다(ASTRAL_PIETEST 줄). 회귀 묶음(`AstralBreak.`)에 걸리지 않게 이름의 뿌리를 따로 둔다: AstralProbe.GuardianCrowd.MeasurePIE
// CombatTestMap · 리슨 서버 · 플레이어 1명. 히어로를 세워 두고 수호병을 정해 둔 배치로 낸 뒤 RunSeconds 동안 매 프레임 잰다. 배치 · 회피 값만 바꿔 여러 번 돈다(재빌드 없이 비교).
//   TL  줄 — 0.25초마다: 수호병별 위치(히어로 기준) · 타깃까지 거리 · 속도 · 경로 추종이 요청한 속도 · 몸 방향과 이동 방향의 각 · 애니가 보는 속도 · 공격 중 · 이동 상태
//   SUM 줄 — 회차 끝: 수호병별 첫 공격 시각 · 이동 거리 · 옆걸음 거리 · 구간별 시간 / 회차 전체의 수호병 사이 거리 · 타깃 둘레 각도

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AstralPieTestHelpers.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "AI/AstralThreatComponent.h"
#include "AI/Navigation/AvoidanceManager.h"
#include "AIController.h"
#include "Animation/AstralEnemyAnimInstance.h"
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Character/Enemy/AstralCombatCharacter.h"
#include "Character/Enemy/AstralEnemyController.h"
#include "Character/Enemy/AstralEnemySpawnSubsystem.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/GameInstance.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerState.h"
#include "GameplayTagContainer.h"
#include "Navigation/PathFollowingComponent.h"
#include "Player/AstralPlayerController.h"

namespace AstralGuardianCrowdProbe
{
	using namespace AstralPieTest;

	const TCHAR* const CombatMapPath = TEXT("/Game/Maps/CombatTestMap");
	const TCHAR* const CombatMapName = TEXT("CombatTestMap");
	const TCHAR* const GuardianName = TEXT("BP_Enemy_Guardian");
	const TCHAR* const GuardianClassPath = TEXT("/Game/Characters/Enemy/BP_Enemy_Guardian.BP_Enemy_Guardian_C");
	const TCHAR* const AttackingTagName = TEXT("State.Enemy.Attacking");

	// CombatTestMap 좌표 — 다른 적 시험과 같은 자리(열린 바닥). 수호병은 히어로의 +X 쪽에서 나온다
	const FVector HeroLocation(1100.0, -400.0, 92.0);
	/** 둘째 히어로(클라이언트)를 세워 두는 곳 — 움직임을 재는 회차에서는 여기 두고 타깃 후보에서 뺀다 */
	const FVector SecondHeroParkLocation(1100.0, 900.0, 92.0);

	constexpr float SturdyHealth = 1000000.f;
	constexpr double RunSeconds = 12.0;
	constexpr double TimelineInterval = 0.25;

	/** ST_Enemy_Guardian 의 Chase(MoveTo) AcceptableRadius — 구간을 가르는 데만 쓴다 */
	constexpr double MoveAcceptableRadius = 75.0;
	/** 엔진 UPathFollowingComponent::MinAgentRadiusPct 기본값 */
	constexpr double AgentRadiusPct = 1.1;

	constexpr double MovingSpeed = 5.0;
	constexpr double SlowSpeed = 150.0;
	constexpr double SidewaysAngle = 30.0;

	struct FRunSpec
	{
		FString Label;
		/** 히어로 기준 수호병 자리 (+X = 히어로 앞) */
		TArray<FVector2D> Offsets;
		bool bUseRvo = true;
		/** UAvoidanceManager::ArtificialRadiusExpansion — 0 이면 그대로 */
		float RadiusExpansion = 0.f;
		/** 히어로가 걷는 구간(회차 시각, 초) — 끝이 시작보다 크면 그동안 +Y 로 걷는다 */
		double HeroMoveStart = 0.0;
		double HeroMoveEnd = 0.0;
		/** 둘째 히어로의 자리(히어로 기준) — 0 이면 멀리 세워 두고 타깃 후보에서 뺀다 */
		FVector2D SecondHeroOffset = FVector2D::ZeroVector;
	};

	struct FTrack
	{
		TWeakObjectPtr<AAstralCombatCharacter> Pawn;
		FVector LastLocation = FVector::ZeroVector;
		bool bHasLast = false;
		bool bWasAttacking = false;

		double FirstReachTime = -1.0;
		double FirstAttackTime = -1.0;
		int32 NumAttacks = 0;

		double PathLength = 0.0;
		double LateralPath = 0.0;
		double BackwardPath = 0.0;
		double AttackMovePath = 0.0;
		double MaxLateralSpeed = 0.0;

		// 구간별 시간 — 공격 중이 아니고 도달 거리 밖일 때
		double FastTime = 0.0;
		double SlowTime = 0.0;
		double BlockedTime = 0.0;
		double SidewaysTime = 0.0;
		/** 경로 추종이 요청한 속도와 실제 속도가 어긋난 시간(방향 20° 이상 또는 크기 60 % 미만) */
		double DeflectedTime = 0.0;
		double AttackTime = 0.0;
		double InRangeIdleTime = 0.0;

		double AnimSpeedErrorSum = 0.0;
		double StepSpeedErrorSum = 0.0;
		int32 NumSamples = 0;

		// 타깃 — 히어로(A) · 둘째 히어로(B)를 쥐고 있던 시간과 바뀐 횟수
		double TimeOnHero = 0.0;
		double TimeOnSecond = 0.0;
		int32 NumTargetSwitches = 0;
		TWeakObjectPtr<const AActor> LastTarget;
	};

	struct FContext : FContextBase
	{
		TArray<FTrack> Tracks;
		FString Label;
		double RunStart = 0.0;
		double LastSampleTime = 0.0;
		double NextTimeline = 0.0;
		double MinPairDistance = TNumericLimits<double>::Max();
		double AllAttackedTime = -1.0;
		double ReachDistance = 0.0;
		float SavedExpansion = 0.f;
		double HeroMoveStart = 0.0;
		double HeroMoveEnd = 0.0;
	};

	// ─── 조회 ───

	/** 재는 대상 히어로 = 리슨 호스트의 폰 (이동 입력을 직접 받는다) */
	AAstralCharacter* HeroIn(const UWorld* World)
	{
		const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
		const APlayerController* LocalPC = GameInstance ? GameInstance->GetFirstLocalPlayerController(World) : nullptr;
		return LocalPC ? Cast<AAstralCharacter>(LocalPC->GetPawn()) : nullptr;
	}

	/** 둘째 히어로 = 접속한 클라이언트의 폰 — 타깃 분포를 잴 때만 후보가 된다 */
	AAstralCharacter* SecondHeroIn(const UWorld* World)
	{
		const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;
		const AAstralCharacter* Hero = HeroIn(World);
		if (!GameState || !Hero)
		{
			return nullptr;
		}
		for (const APlayerState* PlayerState : GameState->PlayerArray)
		{
			AAstralCharacter* Pawn = PlayerState ? Cast<AAstralCharacter>(PlayerState->GetPawn()) : nullptr;
			if (Pawn && Pawn != Hero)
			{
				return Pawn;
			}
		}
		return nullptr;
	}

	UAstralAbilitySystemComponent* HeroAscOf(const AAstralCharacter* Hero)
	{
		const AAstralPlayerController* PC = Hero ? Cast<AAstralPlayerController>(Hero->GetController()) : nullptr;
		return PC ? PC->GetAstralAbilitySystemComponent() : nullptr;
	}

	bool IsAlive(const AAstralCharacter* Hero)
	{
		const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(Hero);
		return Hero && HeroAscOf(Hero) && HealthComponent && HealthComponent->GetHealth() > 0.f;
	}

	bool IsHeroReady()
	{
		const UWorld* ServerWorld = FindServerWorld();
		if (!ServerWorld || !ServerWorld->HasBegunPlay() || MapOf(ServerWorld) != CombatMapName)
		{
			return false;
		}
		return IsAlive(HeroIn(ServerWorld)) && IsAlive(SecondHeroIn(ServerWorld));
	}

	void MakeHeroSturdy(const AAstralCharacter* Hero)
	{
		if (UAstralAbilitySystemComponent* ASC = HeroAscOf(Hero))
		{
			ASC->SetNumericAttributeBase(UAstralHealthSet::GetMaxHealthAttribute(), SturdyHealth);
			ASC->SetNumericAttributeBase(UAstralHealthSet::GetHealthAttribute(), SturdyHealth);
		}
	}

	/** 적대심 — 0 이면 타깃 후보에서 빠진다 */
	void SetHostility(const AAstralCharacter* Hero, float Value)
	{
		if (UAstralAbilitySystemComponent* ASC = HeroAscOf(Hero))
		{
			ASC->SetNumericAttributeBase(UAstralHeroResourceSet::GetHostilityAttribute(), Value);
		}
	}

	/** 둘째 히어로를 놓는다 — Offset 이 0 이면 멀리 세워 두고 후보에서 뺀다, 아니면 히어로 기준 그 자리에 후보로 세운다 */
	void PlaceSecondHero(UWorld* ServerWorld, const FVector2D& Offset)
	{
		AAstralCharacter* Second = SecondHeroIn(ServerWorld);
		if (!Second)
		{
			return;
		}
		MakeHeroSturdy(Second);
		if (Offset.IsNearlyZero())
		{
			Second->TeleportTo(SecondHeroParkLocation, FRotator::ZeroRotator);
			SetHostility(Second, 0.f);
		}
		else
		{
			Second->TeleportTo(FVector(HeroLocation.X + Offset.X, HeroLocation.Y + Offset.Y, HeroLocation.Z), FRotator::ZeroRotator);
			SetHostility(Second, 100.f);
		}
	}

	int32 NumGuardiansIn(UWorld* World)
	{
		int32 Count = 0;
		if (World)
		{
			for (TActorIterator<AAstralCombatCharacter> It(World); It; ++It)
			{
				Count += It->GetClass()->GetName().StartsWith(GuardianName) ? 1 : 0;
			}
		}
		return Count;
	}

	double ServerTime()
	{
		const UWorld* World = FindServerWorld();
		return World ? World->GetTimeSeconds() : 0.0;
	}

	double BearingDegrees(const FVector& From, const FVector& To)
	{
		return FMath::RadiansToDegrees(FMath::Atan2(To.Y - From.Y, To.X - From.X));
	}

	// ─── 측정 ───

	/** 매 프레임 — 구간별 시간 · 거리를 쌓고, 0.25초마다 한 줄을 적는다 */
	void Sample(FContext& Ctx)
	{
		UWorld* ServerWorld = FindServerWorld();
		AAstralCharacter* Hero = HeroIn(ServerWorld);
		if (!ServerWorld || !Hero)
		{
			return;
		}

		const double Now = ServerWorld->GetTimeSeconds();
		const double DeltaTime = Now - Ctx.LastSampleTime;
		const double RunTime = Now - Ctx.RunStart;
		Ctx.LastSampleTime = Now;

		// 움직이는 타깃 — 리슨 호스트의 히어로는 로컬 폰이라 이동 입력을 그대로 받는다
		if (RunTime >= Ctx.HeroMoveStart && RunTime < Ctx.HeroMoveEnd)
		{
			Hero->AddMovementInput(FVector::YAxisVector, 1.f);
		}

		const FVector HeroNow = Hero->GetActorLocation();
		const FGameplayTag AttackingTag = FGameplayTag::RequestGameplayTag(AttackingTagName);
		const bool bTimeline = RunTime >= Ctx.NextTimeline;
		FString Row;
		bool bAllAttacked = Ctx.Tracks.Num() > 0;

		for (int32 Index = 0; Index < Ctx.Tracks.Num(); ++Index)
		{
			FTrack& Track = Ctx.Tracks[Index];
			const AAstralCombatCharacter* Guardian = Track.Pawn.Get();
			if (!Guardian)
			{
				bAllAttacked = false;
				continue;
			}

			const FVector Location = Guardian->GetActorLocation();
			const FVector Velocity = Guardian->GetVelocity();
			const FVector Forward = Guardian->GetActorForwardVector();
			const FVector Right = Guardian->GetActorRightVector();
			const double Speed = Velocity.Size2D();
			const double ForwardSpeed = Velocity | Forward;
			const double LateralSpeed = Velocity | Right;
			const double VelocityAngle = Speed > MovingSpeed ? FMath::RadiansToDegrees(FMath::Atan2(LateralSpeed, ForwardSpeed)) : 0.0;
			const double Distance = FVector::Dist2D(Location, HeroNow);

			const UCharacterMovementComponent* Movement = Guardian->GetCharacterMovement();
			const FVector Requested = Movement ? Movement->GetLastUpdateRequestedVelocity() : FVector::ZeroVector;
			const double RequestedSpeed = Requested.Size2D();

			const UAbilitySystemComponent* ASC = Guardian->GetAbilitySystemComponent();
			const bool bAttacking = ASC && ASC->HasMatchingGameplayTag(AttackingTag);

			const UAstralEnemyAnimInstance* AnimInstance = Guardian->GetMesh() ? Cast<UAstralEnemyAnimInstance>(Guardian->GetMesh()->GetAnimInstance()) : nullptr;
			const double AnimSpeed = AnimInstance ? AnimInstance->GetGroundSpeed() : -1.0;

			const AAIController* Controller = Cast<AAIController>(Guardian->GetController());
			const int32 MoveStatus = Controller ? static_cast<int32>(Controller->GetMoveStatus()) : -1;

			const AAstralEnemyController* EnemyController = Cast<AAstralEnemyController>(Controller);
			const AActor* Target = EnemyController ? EnemyController->GetCurrentTarget() : nullptr;
			const TCHAR* TargetMark = Target == Hero ? TEXT("A") : (Target ? TEXT("B") : TEXT("-"));
			if (Target)
			{
				if (Track.LastTarget.IsValid() && Track.LastTarget.Get() != Target)
				{
					++Track.NumTargetSwitches;
				}
				Track.LastTarget = Target;
				if (Track.bHasLast && DeltaTime > 0.0)
				{
					(Target == Hero ? Track.TimeOnHero : Track.TimeOnSecond) += DeltaTime;
				}
			}

			if (bAttacking && !Track.bWasAttacking)
			{
				++Track.NumAttacks;
				if (Track.FirstAttackTime < 0.0)
				{
					Track.FirstAttackTime = RunTime;
				}
			}
			Track.bWasAttacking = bAttacking;
			bAllAttacked &= Track.FirstAttackTime >= 0.0;

			if (Track.FirstReachTime < 0.0 && Distance <= Ctx.ReachDistance)
			{
				Track.FirstReachTime = RunTime;
			}

			if (Track.bHasLast && DeltaTime > 0.0)
			{
				const double StepLength = FVector::Dist2D(Location, Track.LastLocation);
				Track.PathLength += StepLength;
				Track.LateralPath += FMath::Abs(LateralSpeed) * DeltaTime;
				Track.BackwardPath += ForwardSpeed < 0.0 ? -ForwardSpeed * DeltaTime : 0.0;
				Track.MaxLateralSpeed = FMath::Max(Track.MaxLateralSpeed, FMath::Abs(LateralSpeed));
				Track.StepSpeedErrorSum += FMath::Abs(StepLength / DeltaTime - Speed);
				Track.AnimSpeedErrorSum += AnimSpeed >= 0.0 ? FMath::Abs(AnimSpeed - Speed) : 0.0;
				++Track.NumSamples;

				if (bAttacking)
				{
					Track.AttackTime += DeltaTime;
					Track.AttackMovePath += StepLength;
				}
				else if (Distance > Ctx.ReachDistance + 5.0)
				{
					if (Speed < MovingSpeed)
					{
						Track.BlockedTime += DeltaTime;
					}
					else if (Speed < SlowSpeed)
					{
						Track.SlowTime += DeltaTime;
					}
					else
					{
						Track.FastTime += DeltaTime;
					}
					if (Speed >= MovingSpeed && FMath::Abs(VelocityAngle) > SidewaysAngle)
					{
						Track.SidewaysTime += DeltaTime;
					}
					if (RequestedSpeed > MovingSpeed)
					{
						const double Deflection = Speed > MovingSpeed
							? FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp((Velocity.GetSafeNormal2D() | Requested.GetSafeNormal2D()), -1.0, 1.0)))
							: 180.0;
						if (Deflection > 20.0 || Speed < 0.6 * RequestedSpeed)
						{
							Track.DeflectedTime += DeltaTime;
						}
					}
				}
				else
				{
					Track.InRangeIdleTime += DeltaTime;
				}
			}
			Track.LastLocation = Location;
			Track.bHasLast = true;

			for (int32 Other = Index + 1; Other < Ctx.Tracks.Num(); ++Other)
			{
				if (const AAstralCombatCharacter* OtherGuardian = Ctx.Tracks[Other].Pawn.Get())
				{
					Ctx.MinPairDistance = FMath::Min(Ctx.MinPairDistance, FVector::Dist2D(Location, OtherGuardian->GetActorLocation()));
				}
			}

			if (bTimeline)
			{
				Row += FString::Printf(TEXT(" | g%d p=(%.0f,%.0f) d=%.0f v=%.0f va=%+.0f an=%.0f A%d M%d T%s"),
					Index, Location.X - HeroNow.X, Location.Y - HeroNow.Y, Distance, Speed, VelocityAngle, AnimSpeed, bAttacking ? 1 : 0, MoveStatus, TargetMark);
			}
		}

		if (bAllAttacked && Ctx.AllAttackedTime < 0.0)
		{
			Ctx.AllAttackedTime = RunTime;
		}

		if (bTimeline)
		{
			Ctx.NextTimeline += TimelineInterval;
			Note(*Ctx.Test, FString::Printf(TEXT("TL %s t=%.2f hero=(%.0f,%.0f)%s"), *Ctx.Label, RunTime, HeroNow.X - HeroLocation.X, HeroNow.Y - HeroLocation.Y, *Row));
		}
	}

	void Summarize(FContext& Ctx)
	{
		FAutomationTestBase& Test = *Ctx.Test;
		const AAstralCharacter* Hero = HeroIn(FindServerWorld());
		const FVector HeroNow = Hero ? Hero->GetActorLocation() : HeroLocation;

		FString Pairs;
		FString Bearings;
		for (int32 Index = 0; Index < Ctx.Tracks.Num(); ++Index)
		{
			const FTrack& Track = Ctx.Tracks[Index];
			const AAstralCombatCharacter* Guardian = Track.Pawn.Get();
			if (!Guardian)
			{
				Note(Test, FString::Printf(TEXT("SUM %s g%d: gone before the run ended"), *Ctx.Label, Index));
				continue;
			}

			const FVector Location = Guardian->GetActorLocation();
			const AAstralEnemyController* Controller = Cast<AAstralEnemyController>(Guardian->GetController());
			const double Samples = FMath::Max(Track.NumSamples, 1);
			Note(Test, FString::Printf(TEXT("SUM %s g%d: reach %.2f s, first attack %.2f s, attacks %d, path %.0f cm, lateral %.0f cm, backward %.0f cm, max lateral speed %.0f, moved while attacking %.0f cm, ")
				TEXT("time out of reach fast %.2f / slow %.2f / still %.2f s (sideways %.2f), attacking %.2f s, in reach idle %.2f s, anim speed error %.1f, step speed error %.1f, end distance %.0f cm, end bearing %.0f deg, slot %s, ")
				TEXT("target at the end %s, time on hero A %.2f s / hero B %.2f s, target switches %d"),
				*Ctx.Label, Index, Track.FirstReachTime, Track.FirstAttackTime, Track.NumAttacks, Track.PathLength, Track.LateralPath, Track.BackwardPath, Track.MaxLateralSpeed, Track.AttackMovePath,
				Track.FastTime, Track.SlowTime, Track.BlockedTime, Track.SidewaysTime, Track.AttackTime, Track.InRangeIdleTime,
				Track.AnimSpeedErrorSum / Samples, Track.StepSpeedErrorSum / Samples,
				FVector::Dist2D(Location, HeroNow), BearingDegrees(HeroNow, Location),
				(Controller && Controller->HasEngageSlot()) ? *FString::Printf(TEXT("%.0f deg"), Controller->GetEngageBearing()) : TEXT("none"),
				(Controller && Controller->GetCurrentTarget() == Hero) ? TEXT("A") : ((Controller && Controller->GetCurrentTarget()) ? TEXT("B") : TEXT("none")),
				Track.TimeOnHero, Track.TimeOnSecond, Track.NumTargetSwitches));

			Bearings += FString::Printf(TEXT("%s%.0f"), Bearings.IsEmpty() ? TEXT("") : TEXT(" / "), BearingDegrees(HeroNow, Location));
			for (int32 Other = Index + 1; Other < Ctx.Tracks.Num(); ++Other)
			{
				if (const AAstralCombatCharacter* OtherGuardian = Ctx.Tracks[Other].Pawn.Get())
				{
					Pairs += FString::Printf(TEXT("%s%.0f"), Pairs.IsEmpty() ? TEXT("") : TEXT(" / "), FVector::Dist2D(Location, OtherGuardian->GetActorLocation()));
				}
			}
		}

		Note(Test, FString::Printf(TEXT("SUM %s: all attacked by %.2f s, end pair distances %s cm, closest pair over the run %.0f cm, end bearings %s deg, hero moved %.0f cm"),
			*Ctx.Label, Ctx.AllAttackedTime, Pairs.IsEmpty() ? TEXT("-") : *Pairs, Ctx.Tracks.Num() > 1 ? Ctx.MinPairDistance : 0.0, *Bearings, FVector::Dist2D(HeroNow, HeroLocation)));
	}

	// ─── 단계 ───

	void EnqueueRun(const TSharedRef<FContext>& Ctx, const FRunSpec& Spec)
	{
		Do(Ctx, [Ctx, Spec]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			AAstralCharacter* Hero = HeroIn(ServerWorld);
			UAstralEnemySpawnSubsystem* SpawnSubsystem = ServerWorld ? ServerWorld->GetSubsystem<UAstralEnemySpawnSubsystem>() : nullptr;
			UAvoidanceManager* AvoidanceManager = ServerWorld ? ServerWorld->GetAvoidanceManager() : nullptr;
			UClass* GuardianClass = StaticLoadClass(APawn::StaticClass(), nullptr, GuardianClassPath);
			if (!Test.TestNotNull(TEXT("hero"), Hero) || !Test.TestNotNull(TEXT("spawn subsystem"), SpawnSubsystem) || !Test.TestNotNull(TEXT("avoidance manager"), AvoidanceManager) || !Test.TestNotNull(TEXT("BP_Enemy_Guardian class"), GuardianClass))
			{
				Ctx->bAborted = true;
				return;
			}

			Hero->TeleportTo(HeroLocation, FRotator::ZeroRotator);
			MakeHeroSturdy(Hero);
			SetHostility(Hero, 100.f);
			PlaceSecondHero(ServerWorld, Spec.SecondHeroOffset);

			Ctx->SavedExpansion = AvoidanceManager->ArtificialRadiusExpansion;
			if (Spec.RadiusExpansion > 0.f)
			{
				AvoidanceManager->ArtificialRadiusExpansion = Spec.RadiusExpansion;
			}

			const double HeroRadius = Hero->GetCapsuleComponent()->GetScaledCapsuleRadius();
			const double FloorZ = Hero->GetActorLocation().Z - Hero->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();

			Ctx->Label = Spec.Label;
			Ctx->HeroMoveStart = Spec.HeroMoveStart;
			Ctx->HeroMoveEnd = Spec.HeroMoveEnd;
			Ctx->Tracks.Reset();
			Ctx->MinPairDistance = TNumericLimits<double>::Max();
			Ctx->AllAttackedTime = -1.0;

			double GuardianRadius = 0.0;
			FString Settings;
			for (const FVector2D& Offset : Spec.Offsets)
			{
				const AAstralCombatCharacter* DefaultGuardian = Cast<AAstralCombatCharacter>(GuardianClass->GetDefaultObject());
				const double HalfHeight = DefaultGuardian ? DefaultGuardian->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 100.0;
				const FVector SpawnLocation(HeroLocation.X + Offset.X, HeroLocation.Y + Offset.Y, FloorZ + HalfHeight + 2.0);
				AAstralCombatCharacter* Guardian = Cast<AAstralCombatCharacter>(SpawnSubsystem->SpawnEnemy(GuardianClass, FTransform(FRotator(0.0, 180.0, 0.0), SpawnLocation)));
				if (!Test.TestNotNull(TEXT("spawned guardian"), Guardian))
				{
					Ctx->bAborted = true;
					return;
				}

				UCharacterMovementComponent* Movement = Guardian->GetCharacterMovement();
				if (Settings.IsEmpty())
				{
					Settings = FString::Printf(TEXT("BP values: RVO %d, consideration radius %.0f, weight %.2f, max walk speed %.0f, max acceleration %.0f, braking deceleration %.0f, use acceleration for paths %d, capsule %.0f / %.0f"),
						Movement->bUseRVOAvoidance ? 1 : 0, Movement->AvoidanceConsiderationRadius, Movement->AvoidanceWeight, Movement->MaxWalkSpeed, Movement->GetMaxAcceleration(), Movement->BrakingDecelerationWalking,
						Movement->bRequestedMoveUseAcceleration ? 1 : 0, Guardian->GetCapsuleComponent()->GetScaledCapsuleRadius(), Guardian->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
				}
				GuardianRadius = Guardian->GetCapsuleComponent()->GetScaledCapsuleRadius();
				Movement->SetAvoidanceEnabled(Spec.bUseRvo);

				FTrack& Track = Ctx->Tracks.AddDefaulted_GetRef();
				Track.Pawn = Guardian;
			}

			Ctx->ReachDistance = MoveAcceptableRadius + HeroRadius + GuardianRadius * AgentRadiusPct;
			Ctx->RunStart = ServerWorld->GetTimeSeconds();
			Ctx->LastSampleTime = Ctx->RunStart;
			Ctx->NextTimeline = 0.0;

			Note(Test, FString::Printf(TEXT("RUN %s: %d guardian(s), RVO %s, radius expansion %.2f (manager default %.2f), reach distance %.0f cm (hero radius %.0f), %s"),
				*Spec.Label, Spec.Offsets.Num(), Spec.bUseRvo ? TEXT("on") : TEXT("off"), AvoidanceManager->ArtificialRadiusExpansion, Ctx->SavedExpansion, Ctx->ReachDistance, HeroRadius, *Settings));
		});

		// 실제 시간 제한은 넉넉히 — 프레임이 길어 게임 시간이 느리게 가도 RunSeconds 를 다 잰다
		WaitUntil(Ctx, *FString::Printf(TEXT("%s: measured for the whole run"), *Spec.Label), RunSeconds * 4.0 + 30.0, [Ctx]()
		{
			Sample(*Ctx);
			return ServerTime() - Ctx->RunStart >= RunSeconds;
		});

		Do(Ctx, [Ctx]()
		{
			Summarize(*Ctx);

			for (const FTrack& Track : Ctx->Tracks)
			{
				if (AAstralCombatCharacter* Guardian = Track.Pawn.Get())
				{
					Guardian->Destroy();
				}
			}
			Ctx->Tracks.Reset();

			UWorld* ServerWorld = FindServerWorld();
			if (UAvoidanceManager* AvoidanceManager = ServerWorld ? ServerWorld->GetAvoidanceManager() : nullptr)
			{
				AvoidanceManager->ArtificialRadiusExpansion = Ctx->SavedExpansion;
			}
		});
		WaitUntil(Ctx, *FString::Printf(TEXT("%s: guardians removed"), *Spec.Label), 20.0, []() { return NumGuardiansIn(FindServerWorld()) == 0; });
		// 회피 매니저에 남은 기록이 사라질 때까지(DefaultTimeToLive 1.5초)
		Hold(Ctx, 2.5);
	}

	/**
	 * 타깃 분포 — 수호병을 내자마자(움직이기 전) 타깃을 Rounds 번 다시 뽑아, 히어로 A 를 노린 수호병 수의 분포를 적는다.
	 * 한 번 = 전원의 타깃을 비운 뒤 차례로 AcquireTarget(스폰 직후와 같은 순서 효과). 유지 시간은 0 으로 둔다. 피해 기록은 없다
	 */
	void EnqueueTargetSample(const TSharedRef<FContext>& Ctx, const FString& Label, const TArray<FVector2D>& Offsets, const FVector2D& SecondHeroOffset, int32 Rounds)
	{
		Do(Ctx, [Ctx, Label, Offsets, SecondHeroOffset, Rounds]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			AAstralCharacter* Hero = HeroIn(ServerWorld);
			const AAstralCharacter* Second = SecondHeroIn(ServerWorld);
			UAstralEnemySpawnSubsystem* SpawnSubsystem = ServerWorld ? ServerWorld->GetSubsystem<UAstralEnemySpawnSubsystem>() : nullptr;
			UClass* GuardianClass = StaticLoadClass(APawn::StaticClass(), nullptr, GuardianClassPath);
			if (!Test.TestNotNull(TEXT("hero"), Hero) || !Test.TestNotNull(TEXT("second hero"), Second) || !Test.TestNotNull(TEXT("spawn subsystem"), SpawnSubsystem) || !Test.TestNotNull(TEXT("BP_Enemy_Guardian class"), GuardianClass))
			{
				Ctx->bAborted = true;
				return;
			}

			Hero->TeleportTo(HeroLocation, FRotator::ZeroRotator);
			SetHostility(Hero, 100.f);
			PlaceSecondHero(ServerWorld, SecondHeroOffset);

			const double FloorZ = Hero->GetActorLocation().Z - Hero->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
			TArray<AAstralCombatCharacter*> Guardians;
			TArray<AAstralEnemyController*> Controllers;
			FString Settings;
			FString Distances;
			for (const FVector2D& Offset : Offsets)
			{
				const FVector SpawnLocation(HeroLocation.X + Offset.X, HeroLocation.Y + Offset.Y, FloorZ + 102.0);
				AAstralCombatCharacter* Guardian = Cast<AAstralCombatCharacter>(SpawnSubsystem->SpawnEnemy(GuardianClass, FTransform(FRotator(0.0, 180.0, 0.0), SpawnLocation)));
				AAstralEnemyController* Controller = Guardian ? Cast<AAstralEnemyController>(Guardian->GetController()) : nullptr;
				if (!Test.TestNotNull(TEXT("spawned guardian with an enemy controller"), Controller))
				{
					Ctx->bAborted = true;
					return;
				}

				UAstralThreatComponent* Threat = Controller->GetThreatComponent();
				if (Settings.IsEmpty())
				{
					Settings = FString::Printf(TEXT("draw without damage %d, distance weight %.2f, spread weight %.2f, damage weight %.2f, hold %.1f s"),
						Threat->bDrawWithoutDamage ? 1 : 0, Threat->DistanceWeight, Threat->SpreadWeight, Threat->DamageWeight, Threat->HoldTime);
				}
				Threat->HoldTime = 0.f;

				Distances += FString::Printf(TEXT("%s%.0f/%.0f"), Distances.IsEmpty() ? TEXT("") : TEXT(", "),
					FVector::Dist(Guardian->GetActorLocation(), Hero->GetActorLocation()), FVector::Dist(Guardian->GetActorLocation(), Second->GetActorLocation()));
				Guardians.Add(Guardian);
				Controllers.Add(Controller);
			}

			// 분포 — [히어로 A 를 노린 수호병 수] = 횟수, 그리고 수호병별로 A 를 고른 횟수
			TArray<int32> Pattern;
			Pattern.Init(0, Controllers.Num() + 1);
			TArray<int32> PickedHero;
			PickedHero.Init(0, Controllers.Num());
			int32 NumNoTarget = 0;
			for (int32 Round = 0; Round < Rounds; ++Round)
			{
				for (AAstralEnemyController* Controller : Controllers)
				{
					Controller->SetCurrentTarget(nullptr);
				}
				int32 NumOnHero = 0;
				for (int32 Index = 0; Index < Controllers.Num(); ++Index)
				{
					Controllers[Index]->AcquireTarget();
					const AActor* Target = Controllers[Index]->GetCurrentTarget();
					NumNoTarget += Target ? 0 : 1;
					if (Target == Hero)
					{
						++NumOnHero;
						++PickedHero[Index];
					}
				}
				++Pattern[NumOnHero];
			}

			FString PatternText;
			for (int32 Count = Controllers.Num(); Count >= 0; --Count)
			{
				PatternText += FString::Printf(TEXT("%s%d on A: %.1f %%"), PatternText.IsEmpty() ? TEXT("") : TEXT(", "), Count, 100.0 * Pattern[Count] / FMath::Max(Rounds, 1));
			}
			FString PerGuardian;
			for (int32 Index = 0; Index < PickedHero.Num(); ++Index)
			{
				PerGuardian += FString::Printf(TEXT("%sg%d %.1f %%"), PerGuardian.IsEmpty() ? TEXT("") : TEXT(", "), Index, 100.0 * PickedHero[Index] / FMath::Max(Rounds, 1));
			}
			Note(Test, FString::Printf(TEXT("TARGETS %s: %d guardian(s), %d round(s), BP values: %s; distance to hero A / B per guardian: %s cm; guardians on hero A -> %s; each guardian picked A: %s; draws without a target %d"),
				*Label, Controllers.Num(), Rounds, *Settings, *Distances, *PatternText, *PerGuardian, NumNoTarget));

			for (AAstralCombatCharacter* Guardian : Guardians)
			{
				Guardian->Destroy();
			}
		});
		WaitUntil(Ctx, *FString::Printf(TEXT("%s: guardians removed"), *Label), 20.0, []() { return NumGuardiansIn(FindServerWorld()) == 0; });
		Hold(Ctx, 0.5);
	}

	void EnqueueAll(FAutomationTestBase& Test)
	{
		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;

		// PIE 시작 때 엔진이 내는 경고 — NavMesh 등록 전에 군중 매니저가 만들어진다. 이 프로브와 무관하다
		Test.AddExpectedMessage(TEXT("Unable to find RecastNavMesh instance while trying to create UCrowdManager instance"), ELogVerbosity::Warning, EAutomationExpectedMessageFlags::Contains, -1, /*IsRegex=*/false);

		// 리슨 호스트 = 재는 대상 히어로, 클라이언트 1 = 둘째 히어로(타깃 분포를 잴 때만 후보)
		RequestPie(Ctx, CombatMapPath, PIE_ListenServer, 2);
		WaitUntil(Ctx, TEXT("both heroes have living pawns on the listen server"), 240.0, []() { return IsHeroReady(); });
		Hold(Ctx, 1.0);

		// 배치 — 한 줄(앞이 막힌 경우) · 삼각(RaidMap 스포너의 상대 배치를 줄인 것: 앞 둘이 좌우, 뒤 하나가 가운데)
		const TArray<FVector2D> Single = { FVector2D(600.0, 0.0) };
		const TArray<FVector2D> Column = { FVector2D(400.0, 0.0), FVector2D(600.0, 0.0), FVector2D(800.0, 0.0) };
		const TArray<FVector2D> Triangle = { FVector2D(650.0, -260.0), FVector2D(650.0, 260.0), FVector2D(800.0, 0.0) };

		// 다섯 마리 한 줄 — 고리의 먼 쪽 자리(±120°)까지 차는 경우
		const TArray<FVector2D> Five = { FVector2D(400.0, 0.0), FVector2D(500.0, 0.0), FVector2D(600.0, 0.0), FVector2D(700.0, 0.0), FVector2D(800.0, 0.0) };

		// RVO 끔 — 자리 나눔만으로 서는가
		EnqueueRun(Ctx, { TEXT("single_norvo"), Single, false, 0.f });
		EnqueueRun(Ctx, { TEXT("column_norvo"), Column, false, 0.f });
		EnqueueRun(Ctx, { TEXT("triangle_norvo"), Triangle, false, 0.f });
		EnqueueRun(Ctx, { TEXT("five_norvo"), Five, false, 0.f });
		// 움직이는 타깃 — 셋이 붙은 뒤 히어로가 1.5초 옆으로 걷고 선다. 자리가 타깃을 따라가는지 본다
		EnqueueRun(Ctx, { TEXT("triangle_norvo_move"), Triangle, false, 0.f, 5.0, 6.5 });

		// ─── 타깃(§13 T3 · T4) — 둘째 히어로도 후보다. 피해 기록 없음 ───
		// 두 히어로가 y 로 400 떨어져 서고 수호병은 그 가운데 줄에서 온다 — 수호병마다 두 히어로까지 거리가 같다
		const FVector2D SecondBeside(0.0, 400.0);
		const TArray<FVector2D> MiddleColumn = { FVector2D(400.0, 200.0), FVector2D(600.0, 200.0), FVector2D(800.0, 200.0) };
		// 둘째 히어로가 멀다 — 수호병에서 보아 히어로 A 보다 1.5 ~ 2.4배 먼 자리
		const FVector2D SecondFar(0.0, 900.0);

		EnqueueTargetSample(Ctx, TEXT("solo"), Column, FVector2D::ZeroVector, 300);
		EnqueueTargetSample(Ctx, TEXT("two_equal"), MiddleColumn, SecondBeside, 600);
		EnqueueTargetSample(Ctx, TEXT("two_near_far"), Column, SecondFar, 600);
		EnqueueTargetSample(Ctx, TEXT("two_equal_single"), { FVector2D(600.0, 200.0) }, SecondBeside, 600);
		// 실제 흐름 12초 — 타깃이 나뉜 채 각자 자리로 가서 때리는가, 몇 번 바뀌는가
		FRunSpec TwoHeroes{ TEXT("two_heroes"), MiddleColumn, false, 0.f };
		TwoHeroes.SecondHeroOffset = SecondBeside;
		EnqueueRun(Ctx, TwoHeroes);

		EndPie(Ctx);
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralGuardianCrowdProbePieTest, "AstralProbe.GuardianCrowd.MeasurePIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralGuardianCrowdProbePieTest::RunTest(const FString& Parameters)
{
	AstralGuardianCrowdProbe::EnqueueAll(*this);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
