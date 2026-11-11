// 단위 A 가 기대는 엔진 동작 확인 — Standalone PIE (설계 Docs/Design/m3-enemy-ai.md §8 검증 계획 A0-2 ~ A0-4)
//
//   A0-2  MoveTo.TargetActor 에 묶인 타깃이 움직이면 적이 따라간다
//   A0-3  타깃을 바꾸고 Chase 를 다시 들어오면 새 타깃을 쫓는다 (+ 대조: 다시 들어오지 않으면 처음 타깃 그대로)
//   A0-4  §8 ⑤ 의 이동 값에서 추격 중에는 가는 방향을, 포커스 중에는 타깃을 본다. 포커스를 지우면 멈춘다
//         (+ 대조: 베이스 이동 기본값의 폰은 포커스를 걸어도 돌지 않는다)
//
// 트리는 /Game/AI/Test/ST_A0_Chase (state-tree-mcp 저작):
//   Idle(영구 대기) -GameplayEvent.Damaged→ Chase(MoveTo, TargetActor ← AIController.CurrentTarget, AcceptableRadius 150) → Idle
// 폰 · 컨트롤러는 네이티브 클래스를 그대로 스폰하고 ⑤ 의 이동 값을 인스턴스에 준다 — 시험 BP 가 필요 없다.
// 타깃은 컨트롤러 없는 폰이다(캡슐이 있어야 도달 판정이 실제 플레이어와 같다 — 높이 · 반경이 판정에 든다).
// 엔진을 올렸을 때 이 전제가 깨지면 여기서 먼저 떨어진다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AstralPieTestHelpers.h"

#include "AIController.h"
#include "Character/Enemy/AstralCombatCharacter.h"
#include "Character/Enemy/AstralEnemyController.h"
#include "Components/StateTreeAIComponent.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameplayTagContainer.h"
#include "NavMesh/NavMeshBoundsVolume.h"
#include "Navigation/PathFollowingComponent.h"
#include "NavigationData.h"
#include "NavigationSystem.h"
#include "StateTree.h"

namespace AstralEnemyAssumptionsPie
{
	using namespace AstralPieTest;

	const TCHAR* const MapPath = TEXT("/Game/Maps/CombatTestMap");
	const TCHAR* const MapName = TEXT("CombatTestMap");
	const TCHAR* const TreePath = TEXT("/Game/AI/Test/ST_A0_Chase.ST_A0_Chase");
	const TCHAR* const ChaseEventTag = TEXT("GameplayEvent.Damaged");

	// 트리 · §8 ⑤ 와 같은 값
	constexpr float AcceptableRadius = 150.f;
	constexpr float YawRateDegPerSec = 360.f;

	/** 폰 캡슐 반경 — 도달 판정에 양쪽 반경이 더해진다(bReachTestIncludesAgentRadius · GoalRadius 기본값 참) */
	constexpr float CapsuleRadius = 34.f;

	/** 멈추는 거리(중심 간, 2D)의 기대값과 허용 폭 */
	constexpr float ExpectedStopDistance = AcceptableRadius + CapsuleRadius * 2.f;
	constexpr float StopDistanceTolerance = 60.f;

	/** 방향이 바뀐 뒤 이만큼은 회전 중으로 보고 추격 방향 표본에서 뺀다 (180° / 360°/s + 가속 여유) */
	constexpr double TurnSettleSeconds = 0.9;

	// CombatTestMap 좌표 — NavMesh 위(설치 때 투영으로 확인한다). 맵의 더미 · 히어로 시작점과 떨어진 곳
	const FVector EnemyStart(1100.0, -700.0, 120.0);
	const FVector TargetAStart(1180.0, 500.0, 90.0);
	const FVector TargetAMoved(1100.0, -600.0, 90.0);
	const FVector TargetBLocation(1700.0, 100.0, 90.0);
	const FVector ControlPawnLocation(1180.0, 900.0, 90.0);

	struct FContext : FContextBase
	{
		TWeakObjectPtr<AAstralCombatCharacter> Enemy;
		TWeakObjectPtr<AAstralEnemyController> Controller;
		TWeakObjectPtr<AActor> TargetA;
		TWeakObjectPtr<AActor> TargetB;

		/** 대조용 — 베이스 이동 기본값 그대로인 폰 */
		TWeakObjectPtr<AAstralCombatCharacter> ControlPawn;
		TWeakObjectPtr<AAIController> ControlController;

		/** 단계 시작 때의 값 */
		FVector PhaseStartLocation = FVector::ZeroVector;
		double PhaseStartWorldTime = 0.0;
		double LastDisturbanceWorldTime = 0.0;
		float YawAtPhaseStart = 0.f;

		/** 추격 중 '몸 방향 − 속도 방향' 표본 (도, 절대값) */
		TArray<float> ChaseYawErrors;
		int32 ChaseSamplesWithFocusActor = 0;
		int32 MaxPathPoints = 0;
		float MaxSpeed = 0.f;
		bool bSawMoving = false;
	};

	float Dist2D(const AActor* A, const AActor* B)
	{
		return (A && B) ? static_cast<float>(FVector::Dist2D(A->GetActorLocation(), B->GetActorLocation())) : TNumericLimits<float>::Max();
	}

	float Dist2D(const AActor* A, const FVector& B)
	{
		return A ? static_cast<float>(FVector::Dist2D(A->GetActorLocation(), B)) : TNumericLimits<float>::Max();
	}

	float YawTo(const AActor* From, const AActor* To)
	{
		return static_cast<float>((To->GetActorLocation() - From->GetActorLocation()).GetSafeNormal2D().Rotation().Yaw);
	}

	float YawError(const AActor* Actor, float DesiredYaw)
	{
		return FMath::Abs(FMath::FindDeltaAngleDegrees(static_cast<float>(Actor->GetActorRotation().Yaw), DesiredYaw));
	}

	bool StoppedAtAcceptableRadius(float Distance)
	{
		return FMath::Abs(Distance - ExpectedStopDistance) <= StopDistanceTolerance;
	}

	EPathFollowingStatus::Type MoveStatus(const FContext& Ctx)
	{
		const UPathFollowingComponent* PathFollowing = Ctx.Controller.IsValid() ? Ctx.Controller->GetPathFollowingComponent() : nullptr;
		return PathFollowing ? PathFollowing->GetStatus() : EPathFollowingStatus::Idle;
	}

	void SendChaseEvent(const FContext& Ctx)
	{
		Ctx.Controller->GetStateTreeComponent()->SendStateTreeEvent(FGameplayTag::RequestGameplayTag(ChaseEventTag));
	}

	void MoveActorTo(AActor* Actor, const FVector& Location)
	{
		Actor->SetActorLocation(Location, /*bSweep=*/false, nullptr, ETeleportType::TeleportPhysics);
	}

	/** 컨트롤러 없이 서 있는 폰 — 타깃 · 대조용 */
	AAstralCombatCharacter* SpawnStandingPawn(UWorld* World, const FVector& Location)
	{
		const FTransform SpawnTransform(FRotator::ZeroRotator, Location);
		AAstralCombatCharacter* Pawn = World->SpawnActorDeferred<AAstralCombatCharacter>(AAstralCombatCharacter::StaticClass(), SpawnTransform, nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
		if (Pawn)
		{
			Pawn->AutoPossessAI = EAutoPossessAI::Disabled;
			Pawn->FinishSpawning(SpawnTransform);
		}
		return Pawn;
	}

	void BeginPhase(FContext& Ctx)
	{
		Ctx.PhaseStartLocation = Ctx.Enemy->GetActorLocation();
		Ctx.PhaseStartWorldTime = Ctx.Enemy->GetWorld()->GetTimeSeconds();
		Ctx.LastDisturbanceWorldTime = Ctx.PhaseStartWorldTime;
		Ctx.YawAtPhaseStart = static_cast<float>(Ctx.Enemy->GetActorRotation().Yaw);
		Ctx.bSawMoving = false;
	}

	double PhaseAge(const FContext& Ctx)
	{
		return Ctx.Enemy->GetWorld()->GetTimeSeconds() - Ctx.PhaseStartWorldTime;
	}

	/** 추격 중 매 프레임 — 몸 방향과 속도 방향의 차이, 포커스 종류, 경로 꼭짓점 수 */
	void SampleChase(FContext& Ctx)
	{
		const AAstralCombatCharacter* Enemy = Ctx.Enemy.Get();
		const AAstralEnemyController* Controller = Ctx.Controller.Get();
		if (!Enemy || !Controller || MoveStatus(Ctx) != EPathFollowingStatus::Moving)
		{
			return;
		}
		Ctx.bSawMoving = true;

		if (const UPathFollowingComponent* PathFollowing = Controller->GetPathFollowingComponent(); PathFollowing && PathFollowing->HasValidPath())
		{
			Ctx.MaxPathPoints = FMath::Max(Ctx.MaxPathPoints, PathFollowing->GetPath()->GetPathPoints().Num());
		}

		const FVector Velocity = Enemy->GetVelocity();
		Ctx.MaxSpeed = FMath::Max(Ctx.MaxSpeed, static_cast<float>(Velocity.Size2D()));
		const double Now = Enemy->GetWorld()->GetTimeSeconds();
		if (Velocity.Size2D() < 200.0 || Now - Ctx.LastDisturbanceWorldTime < TurnSettleSeconds)
		{
			return;
		}

		Ctx.ChaseYawErrors.Add(YawError(Enemy, static_cast<float>(Velocity.GetSafeNormal2D().Rotation().Yaw)));
		if (Controller->GetFocusActor() != nullptr)
		{
			++Ctx.ChaseSamplesWithFocusActor;
		}
	}

	/** 이동이 시작됐다가 끝났다 */
	bool ChaseFinished(FContext& Ctx)
	{
		SampleChase(Ctx);
		return Ctx.bSawMoving && MoveStatus(Ctx) == EPathFollowingStatus::Idle;
	}

	FString DescribeEnemy(const FContext& Ctx)
	{
		const AAstralCombatCharacter* Enemy = Ctx.Enemy.Get();
		return Enemy
			? FString::Printf(TEXT("enemy at %s, move status %d, saw moving %d, tree running %d"), *Enemy->GetActorLocation().ToCompactString(), static_cast<int32>(MoveStatus(Ctx)), Ctx.bSawMoving ? 1 : 0,
				(Ctx.Controller.IsValid() && Ctx.Controller->GetStateTreeComponent()->IsRunning()) ? 1 : 0)
			: FString(TEXT("enemy gone"));
	}

	void EnqueueSetup(const TSharedRef<FContext>& Ctx)
	{
		RequestPie(Ctx, MapPath, PIE_Standalone, 1);
		WaitUntil(Ctx, TEXT("Standalone PIE world with a player pawn"), 240.0, []()
		{
			const UWorld* World = FindAuthorityWorld();
			const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
			return World && World->HasBegunPlay() && MapOf(World) == MapName && PC && PC->GetPawn();
		});

		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* World = FindAuthorityWorld();

			// 맵 정보 — 좌표 상수를 고칠 때 볼 것
			for (TActorIterator<ACharacter> It(World); It; ++It)
			{
				Note(Test, FString::Printf(TEXT("map: character %s at %s"), *It->GetName(), *It->GetActorLocation().ToCompactString()));
			}
			for (TActorIterator<ANavMeshBoundsVolume> It(World); It; ++It)
			{
				const FBox Bounds = It->GetComponentsBoundingBox(true);
				Note(Test, FString::Printf(TEXT("map: nav bounds %s .. %s"), *Bounds.Min.ToCompactString(), *Bounds.Max.ToCompactString()));
			}

			UNavigationSystemV1* NavSystem = UNavigationSystemV1::GetCurrent(World);
			if (!Test.TestNotNull(TEXT("navigation system"), NavSystem))
			{
				Ctx->bAborted = true;
				return;
			}
			for (const FVector& Point : { EnemyStart, TargetAStart, TargetAMoved, TargetBLocation })
			{
				FNavLocation Projected;
				const bool bOnNav = NavSystem->ProjectPointToNavigation(Point, Projected, FVector(50.0, 50.0, 250.0));
				if (!Test.TestTrue(*FString::Printf(TEXT("test point %s is on the NavMesh"), *Point.ToCompactString()), bOnNav))
				{
					Ctx->bAborted = true;
				}
			}

			UStateTree* Tree = LoadObject<UStateTree>(nullptr, TreePath);
			if (!Test.TestNotNull(TEXT("ST_A0_Chase (author it with state-tree-mcp — see the file header)"), Tree) || Ctx->bAborted)
			{
				Ctx->bAborted = true;
				return;
			}

			Ctx->TargetA = SpawnStandingPawn(World, TargetAStart);
			Ctx->TargetB = SpawnStandingPawn(World, TargetBLocation);

			// 폰 — §8 ⑤ 의 이동 값. 컨트롤러는 트리를 준 뒤 빙의시킨다(준비 신호가 먼저인 순서 — §1 V3)
			const FTransform SpawnTransform(FRotator::ZeroRotator, EnemyStart);
			AAstralCombatCharacter* Enemy = World->SpawnActorDeferred<AAstralCombatCharacter>(AAstralCombatCharacter::StaticClass(), SpawnTransform, nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
			if (!Test.TestNotNull(TEXT("enemy pawn"), Enemy) || !Test.TestTrue(TEXT("target pawns"), Ctx->TargetA.IsValid() && Ctx->TargetB.IsValid()))
			{
				Ctx->bAborted = true;
				return;
			}
			Enemy->AutoPossessAI = EAutoPossessAI::Disabled;
			UCharacterMovementComponent* Movement = Enemy->GetCharacterMovement();
			Movement->bOrientRotationToMovement = false;
			Movement->bUseControllerDesiredRotation = true;
			Movement->RotationRate = FRotator(0.0, YawRateDegPerSec, 0.0);
			Enemy->FinishSpawning(SpawnTransform);

			FActorSpawnParameters SpawnParams;
			SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			AAstralEnemyController* Controller = World->SpawnActor<AAstralEnemyController>(AAstralEnemyController::StaticClass(), EnemyStart, FRotator::ZeroRotator, SpawnParams);
			if (!Test.TestNotNull(TEXT("enemy controller"), Controller))
			{
				Ctx->bAborted = true;
				return;
			}
			Controller->GetStateTreeComponent()->SetStateTree(Tree);
			Controller->Possess(Enemy);

			Ctx->Enemy = Enemy;
			Ctx->Controller = Controller;
			Test.TestTrue(TEXT("tree started on possess"), Controller->GetStateTreeComponent()->IsRunning());
			Test.TestNull(TEXT("no target yet"), Controller->GetCurrentTarget());
		});

		// 착지 · 트리 첫 틱
		Hold(Ctx, 1.0);
	}

	void EnqueueFollowMovingTarget(const TSharedRef<FContext>& Ctx)
	{
		// A0-2 — 타깃 A 를 쫓는 중에 A 를 뒤쪽으로 옮긴다
		Do(Ctx, [Ctx]()
		{
			BeginPhase(*Ctx);
			Ctx->Controller->SetCurrentTarget(Ctx->TargetA.Get());
			SendChaseEvent(*Ctx);
		});
		WaitUntil(Ctx, TEXT("A0-2: enemy travelled 500 toward target A"), 15.0, [Ctx]()
		{
			SampleChase(*Ctx);
			return Ctx->Enemy.IsValid() && Dist2D(Ctx->Enemy.Get(), Ctx->PhaseStartLocation) >= 500.f;
		}, [Ctx]() { return DescribeEnemy(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			Note(*Ctx->Test, FString::Printf(TEXT("A0-2: target A moved %s -> %s at t=%.2f s while the enemy was at %s"),
				*TargetAStart.ToCompactString(), *TargetAMoved.ToCompactString(), PhaseAge(*Ctx), *Ctx->Enemy->GetActorLocation().ToCompactString()));
			MoveActorTo(Ctx->TargetA.Get(), TargetAMoved);
			Ctx->LastDisturbanceWorldTime = Ctx->Enemy->GetWorld()->GetTimeSeconds();
		});
		WaitUntil(Ctx, TEXT("A0-2: chase finished after the target moved"), 20.0, [Ctx]() { return ChaseFinished(*Ctx); }, [Ctx]() { return DescribeEnemy(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const float ToMoved = Dist2D(Ctx->Enemy.Get(), TargetAMoved);
			const float ToOriginal = Dist2D(Ctx->Enemy.Get(), TargetAStart);
			Note(Test, FString::Printf(TEXT("A0-2: ended at %s after %.2f s — %.0f from the moved target (expected %.0f = AcceptableRadius + both capsule radii), %.0f from its original place, top speed %.0f"),
				*Ctx->Enemy->GetActorLocation().ToCompactString(), PhaseAge(*Ctx), ToMoved, ExpectedStopDistance, ToOriginal, Ctx->MaxSpeed));
			Test.TestTrue(TEXT("A0-2: enemy stopped at the acceptable radius of the moved target"), StoppedAtAcceptableRadius(ToMoved));
			Test.TestTrue(TEXT("A0-2: enemy did not end at the target's original place"), ToOriginal > 500.f);
		});
	}

	void EnqueueRetarget(const TSharedRef<FContext>& Ctx)
	{
		// A0-3 — 타깃을 B 로 바꾸고 Chase 를 다시 들어온다
		Hold(Ctx, 0.5);
		Do(Ctx, [Ctx]()
		{
			BeginPhase(*Ctx);
			Ctx->Controller->SetCurrentTarget(Ctx->TargetB.Get());
			SendChaseEvent(*Ctx);
		});
		WaitUntil(Ctx, TEXT("A0-3: chase finished after retargeting to B"), 20.0, [Ctx]() { return ChaseFinished(*Ctx); }, [Ctx]() { return DescribeEnemy(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const float ToB = Dist2D(Ctx->Enemy.Get(), Ctx->TargetB.Get());
			const float ToA = Dist2D(Ctx->Enemy.Get(), Ctx->TargetA.Get());
			Note(Test, FString::Printf(TEXT("A0-3: ended at %s after %.2f s — %.0f from B, %.0f from A"), *Ctx->Enemy->GetActorLocation().ToCompactString(), PhaseAge(*Ctx), ToB, ToA));
			Test.TestTrue(TEXT("A0-3: enemy stopped at the acceptable radius of the new target B"), StoppedAtAcceptableRadius(ToB));
			Test.TestTrue(TEXT("A0-3: enemy left the old target A"), ToA > 400.f);
		});

		// 대조 — 추격 중에 값만 바꾸고 다시 들어오지 않으면 처음 타깃을 끝까지 쫓는다 (MoveTo 는 들어올 때만 읽는다)
		Hold(Ctx, 0.5);
		Do(Ctx, [Ctx]()
		{
			BeginPhase(*Ctx);
			Ctx->Controller->SetCurrentTarget(Ctx->TargetA.Get());
			SendChaseEvent(*Ctx);
		});
		WaitUntil(Ctx, TEXT("A0-3 control: enemy travelled 200 toward A"), 15.0, [Ctx]()
		{
			SampleChase(*Ctx);
			return Ctx->Enemy.IsValid() && Dist2D(Ctx->Enemy.Get(), Ctx->PhaseStartLocation) >= 200.f;
		}, [Ctx]() { return DescribeEnemy(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			Ctx->Controller->SetCurrentTarget(Ctx->TargetB.Get());
		});
		WaitUntil(Ctx, TEXT("A0-3 control: chase finished"), 20.0, [Ctx]() { return ChaseFinished(*Ctx); }, [Ctx]() { return DescribeEnemy(*Ctx); });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const float ToA = Dist2D(Ctx->Enemy.Get(), Ctx->TargetA.Get());
			const float ToB = Dist2D(Ctx->Enemy.Get(), Ctx->TargetB.Get());
			Note(Test, FString::Printf(TEXT("A0-3 control: value changed to B mid-chase without re-entering — ended %.0f from A, %.0f from B"), ToA, ToB));
			Test.TestTrue(TEXT("A0-3 control: without re-entering Chase the enemy keeps its first target (MoveTo reads the binding on enter only)"), StoppedAtAcceptableRadius(ToA) && ToB > 400.f);
		});
	}

	void EnqueueChaseFacingVerdict(const TSharedRef<FContext>& Ctx)
	{
		// A0-4 (추격) — 위 세 번의 추격에서 모은 표본
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			TArray<float> Errors = Ctx->ChaseYawErrors;
			Errors.Sort();
			if (!Test.TestTrue(TEXT("A0-4: collected chase facing samples"), Errors.Num() >= 30))
			{
				return;
			}
			const float Median = Errors[Errors.Num() / 2];
			const float P95 = Errors[FMath::Min(Errors.Num() - 1, (Errors.Num() * 95) / 100)];
			Note(Test, FString::Printf(TEXT("A0-4: chase facing — %d samples, |body yaw - velocity yaw| median %.1f deg, p95 %.1f deg, max %.1f deg, samples with a focus actor %d, max path points %d"),
				Errors.Num(), Median, P95, Errors.Last(), Ctx->ChaseSamplesWithFocusActor, Ctx->MaxPathPoints));
			Test.TestTrue(TEXT("A0-4: while chasing the body faces the way it moves"), Median <= 5.f && P95 <= 15.f);
			Test.TestEqual(TEXT("A0-4: while chasing the focus is a move-direction point, not an actor"), Ctx->ChaseSamplesWithFocusActor, 0);
		});
	}

	/** 타깃 A 를 적 기준 RelativeYaw 방향 400 cm 로 옮긴다 */
	void PlaceTargetAround(FContext& Ctx, float RelativeYaw)
	{
		const FVector Direction = FRotator(0.0, Ctx.Enemy->GetActorRotation().Yaw + RelativeYaw, 0.0).Vector();
		MoveActorTo(Ctx.TargetA.Get(), Ctx.Enemy->GetActorLocation() + Direction * 400.0);
	}

	void EnqueueFocusTurn(const TSharedRef<FContext>& Ctx, const TCHAR* Label, float RelativeYaw, bool bSetFocus)
	{
		Do(Ctx, [Ctx, RelativeYaw, bSetFocus]()
		{
			PlaceTargetAround(*Ctx, RelativeYaw);
			if (bSetFocus)
			{
				Ctx->Controller->SetFocus(Ctx->TargetA.Get(), EAIFocusPriority::Gameplay);
			}
			BeginPhase(*Ctx);
		});
		WaitUntil(Ctx, *FString::Printf(TEXT("A0-4: %s — body faces the focused target"), Label), 6.0, [Ctx]()
		{
			return Ctx->Enemy.IsValid() && Ctx->TargetA.IsValid() && YawError(Ctx->Enemy.Get(), YawTo(Ctx->Enemy.Get(), Ctx->TargetA.Get())) <= 2.f;
		}, [Ctx]()
		{
			return Ctx->Enemy.IsValid() && Ctx->TargetA.IsValid()
				? FString::Printf(TEXT("yaw error %.1f deg"), YawError(Ctx->Enemy.Get(), YawTo(Ctx->Enemy.Get(), Ctx->TargetA.Get())))
				: FString(TEXT("actor gone"));
		});
		Do(Ctx, [Ctx, Label = FString(Label), RelativeYaw]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const double Elapsed = PhaseAge(*Ctx);
			const double Expected = FMath::Abs(RelativeYaw) / YawRateDegPerSec;
			Note(Test, FString::Printf(TEXT("A0-4: %s — turned %.0f deg in %.3f s of game time (%.0f deg/s, expected %.3f s at %.0f deg/s)"),
				*Label, FMath::Abs(RelativeYaw), Elapsed, Elapsed > 0.0 ? FMath::Abs(RelativeYaw) / Elapsed : 0.0, Expected, YawRateDegPerSec));
			Test.TestTrue(*FString::Printf(TEXT("A0-4: %s — turn time matches the yaw rate (not a snap, not slower)"), *Label), Elapsed >= Expected * 0.7 && Elapsed <= Expected + 0.25);
			Test.TestTrue(*FString::Printf(TEXT("A0-4: %s — focus actor is the target"), *Label), Ctx->Controller->GetFocusActor() == Ctx->TargetA.Get());
		});
	}

	void EnqueueFocus(const TSharedRef<FContext>& Ctx)
	{
		// A0-4 (포커스) — 서 있는 적에게 Gameplay 포커스를 걸고, 타깃을 옮기고, 포커스를 지운다
		Hold(Ctx, 0.5);
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestEqual(TEXT("A0-4: enemy is standing before the focus test"), static_cast<int32>(MoveStatus(*Ctx)), static_cast<int32>(EPathFollowingStatus::Idle));
			Ctx->Test->TestNull(TEXT("A0-4: no focus actor before SetFocus"), Ctx->Controller->GetFocusActor());
		});
		EnqueueFocusTurn(Ctx, TEXT("SetFocus, target 90 deg to the side"), 90.f, /*bSetFocus=*/true);
		EnqueueFocusTurn(Ctx, TEXT("focused target jumps behind (180 deg)"), 180.f, /*bSetFocus=*/false);

		Do(Ctx, [Ctx]()
		{
			Ctx->Controller->ClearFocus(EAIFocusPriority::Gameplay);
			BeginPhase(*Ctx);
			PlaceTargetAround(*Ctx, 90.f);
		});
		Hold(Ctx, 1.0);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const float Turned = YawError(Ctx->Enemy.Get(), Ctx->YawAtPhaseStart);
			Note(Test, FString::Printf(TEXT("A0-4: after ClearFocus the target moved 90 deg to the side — body turned %.2f deg in 1 s"), Turned));
			Test.TestTrue(TEXT("A0-4: after ClearFocus the body stops turning"), Turned <= 1.f);
			Test.TestNull(TEXT("A0-4: no focus actor after ClearFocus"), Ctx->Controller->GetFocusActor());
		});

		// 대조 — 베이스 기본값(bOrientRotationToMovement = true)의 폰은 포커스를 걸어도 돌지 않는다. ⑤ 의 값이 필요한 이유다
		Do(Ctx, [Ctx]()
		{
			UWorld* World = Ctx->Enemy->GetWorld();
			FActorSpawnParameters SpawnParams;
			SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;

			AAstralCombatCharacter* ControlPawn = SpawnStandingPawn(World, ControlPawnLocation);
			AAIController* ControlController = World->SpawnActor<AAIController>(AAIController::StaticClass(), ControlPawnLocation, FRotator::ZeroRotator, SpawnParams);
			if (!Ctx->Test->TestTrue(TEXT("A0-4 control: control pawn and controller"), ControlPawn && ControlController))
			{
				return;
			}
			ControlController->Possess(ControlPawn);

			Ctx->ControlPawn = ControlPawn;
			Ctx->ControlController = ControlController;
			MoveActorTo(Ctx->TargetB.Get(), ControlPawn->GetActorLocation() + FVector(0.0, 400.0, 0.0)); // 폰은 +X 를 본다 — 타깃은 90° 옆
			ControlController->SetFocus(Ctx->TargetB.Get(), EAIFocusPriority::Gameplay);
		});
		Hold(Ctx, 1.0);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			if (!Test.TestTrue(TEXT("A0-4 control: control pawn alive"), Ctx->ControlPawn.IsValid() && Ctx->ControlController.IsValid()))
			{
				return;
			}
			const float Turned = YawError(Ctx->ControlPawn.Get(), 0.f);
			Note(Test, FString::Printf(TEXT("A0-4 control: base movement defaults, focus on a target 90 deg to the side — body turned %.2f deg in 1 s (focus actor set: %d)"),
				Turned, Ctx->ControlController->GetFocusActor() == Ctx->TargetB.Get() ? 1 : 0));
			Test.TestTrue(TEXT("A0-4 control: with the base movement defaults focus does not turn the body"), Turned <= 1.f);
		});
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralEnemyAssumptionsPieTest, "AstralBreak.Enemy.Assumptions.ChaseAndFocusPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralEnemyAssumptionsPieTest::RunTest(const FString& Parameters)
{
	using namespace AstralEnemyAssumptionsPie;

	TSharedRef<FContext> Ctx = MakeShared<FContext>();
	Ctx->Test = this;

	// PIE 시작 때 엔진이 내는 경고 — NavMesh 등록 전에 군중 매니저가 만들어진다. 이 시험과 무관하다
	AddExpectedMessage(TEXT("Unable to find RecastNavMesh instance while trying to create UCrowdManager instance"), ELogVerbosity::Warning, EAutomationExpectedMessageFlags::Contains, -1, /*IsRegex=*/false);

	EnqueueSetup(Ctx);
	EnqueueFollowMovingTarget(Ctx);
	EnqueueRetarget(Ctx);
	EnqueueChaseFacingVerdict(Ctx);
	EnqueueFocus(Ctx);
	AstralPieTest::EndPie(Ctx);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
