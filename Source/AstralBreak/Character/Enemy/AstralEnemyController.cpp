#include "AstralEnemyController.h"

#include "AI/AstralEnemyTargeting.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AstralCombatCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Components/StateTreeAIComponent.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerState.h"

AAstralEnemyController::AAstralEnemyController(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	StateTreeComponent = CreateDefaultSubobject<UStateTreeAIComponent>(TEXT("StateTreeComponent"));
	StateTreeComponent->SetStartLogicAutomatically(false);

	// OnPossess 는 APawn::PostInitializeComponents 안에서 돌아 어빌리티 부여보다 앞선다 — 시작은 폰의 준비 완료 신호로 한다
	bStartAILogicOnPossess = false;
}

void AAstralEnemyController::OnPossess(APawn* InPawn)
{
	Super::OnPossess(InPawn);

	// 엔진이 무효 폰을 거부하면 빙의되지 않은 채 돌아온다
	if (!InPawn || GetPawn() != InPawn)
	{
		return;
	}

	AAstralCombatCharacter* CombatCharacter = Cast<AAstralCombatCharacter>(InPawn);
	if (!CombatCharacter)
	{
		// 부여 단계가 없는 폰 — 엔진 Possess 시작과 같다
		TryStartLogic();
		return;
	}

	CombatCharacter->GetHealthComponent()->OnDeathStarted.AddUniqueDynamic(this, &ThisClass::HandlePawnDeathStarted);
	CombatCharacter->OnCombatReady_RegisterAndCall(FSimpleMulticastDelegate::FDelegate::CreateUObject(this, &ThisClass::TryStartLogic));
}

void AAstralEnemyController::OnUnPossess()
{
	// Super 는 폰을 비운 뒤 StopLogic 을 불러 컨텍스트 검사가 실패한다 — 폰이 있을 때 먼저 멈춘다. 뒤따르는 호출은 실행 중이 아니므로 바로 돌아온다
	StateTreeComponent->StopLogic(TEXT("UnPossess"));

	// 트리가 멈춘 뒤라 이벤트 없이 구독만 푼다
	SetCurrentTarget(nullptr);

	if (AAstralCombatCharacter* CombatCharacter = Cast<AAstralCombatCharacter>(GetPawn()))
	{
		CombatCharacter->OnCombatReady_Unregister(this);
		CombatCharacter->GetHealthComponent()->OnDeathStarted.RemoveDynamic(this, &ThisClass::HandlePawnDeathStarted);
	}

	Super::OnUnPossess();
}

bool AAstralEnemyController::AcquireTarget()
{
	const APawn* MyPawn = GetPawn();
	const UWorld* World = GetWorld();
	const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;
	if (!MyPawn || !GameState)
	{
		SetCurrentTarget(nullptr);
		return false;
	}

	// 수집 — 플레이어의 폰. 봇(AI 가 가진 PlayerState)은 뺀다. 사망 판정은 구독하는 것과 같은 원천(HealthComponent)으로 한다
	TArray<APawn*> Pawns;
	TArray<FAstralEnemyTargetCandidate> Candidates;
	for (const APlayerState* CandidateState : GameState->PlayerArray)
	{
		APawn* PlayerPawn = (CandidateState && !CandidateState->IsABot()) ? CandidateState->GetPawn() : nullptr;
		if (!PlayerPawn)
		{
			continue;
		}

		const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(PlayerPawn);

		FAstralEnemyTargetCandidate Candidate;
		Candidate.Location = PlayerPawn->GetActorLocation();
		Candidate.bDeadOrDying = HealthComponent && HealthComponent->IsDeadOrDying();

		Pawns.Add(PlayerPawn);
		Candidates.Add(Candidate);
	}

	const int32 TargetIndex = AstralEnemyTargeting::SelectNearestIndex(MyPawn->GetActorLocation(), Candidates);
	SetCurrentTarget(Pawns.IsValidIndex(TargetIndex) ? Pawns[TargetIndex] : nullptr);
	return CurrentTarget != nullptr;
}

void AAstralEnemyController::SetCurrentTarget(AActor* NewTarget)
{
	if (CurrentTarget == NewTarget)
	{
		return;
	}

	if (AActor* OldTarget = CurrentTarget)
	{
		OldTarget->OnDestroyed.RemoveDynamic(this, &ThisClass::HandleTargetDestroyed);
		if (UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(OldTarget))
		{
			HealthComponent->OnDeathStarted.RemoveDynamic(this, &ThisClass::HandleTargetDeathStarted);
		}
	}

	CurrentTarget = NewTarget;

	if (NewTarget)
	{
		// 접속 종료는 폰 파괴로 온다
		NewTarget->OnDestroyed.AddUniqueDynamic(this, &ThisClass::HandleTargetDestroyed);
		if (UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(NewTarget))
		{
			HealthComponent->OnDeathStarted.AddUniqueDynamic(this, &ThisClass::HandleTargetDeathStarted);
		}
	}
}

void AAstralEnemyController::HandleTargetLost(const AActor* LostActor)
{
	// 이미 다른 타깃으로 넘어간 뒤에 온 통지는 버린다
	if (!LostActor || LostActor != CurrentTarget.Get())
	{
		return;
	}

	SetCurrentTarget(nullptr);

	// 다시 고르는 것은 트리의 몫이다 — Chase 의 TargetLost 전환이 Acquire 로 보낸다. 공격 중이면 공격은 끝까지 가고 그 뒤 Acquire 가 고른다
	if (StateTreeComponent->IsRunning())
	{
		StateTreeComponent->SendStateTreeEvent(AstralGameplayTags::AIEvent_TargetLost);
	}
}

void AAstralEnemyController::HandleTargetDeathStarted(AActor* OwningActor)
{
	HandleTargetLost(OwningActor);
}

void AAstralEnemyController::HandleTargetDestroyed(AActor* DestroyedActor)
{
	HandleTargetLost(DestroyedActor);
}

void AAstralEnemyController::TryStartLogic()
{
	const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(GetPawn());
	if (!GetPawn() || (HealthComponent && HealthComponent->IsDeadOrDying()) || StateTreeComponent->IsRunning())
	{
		return;
	}

	StateTreeComponent->StartLogic();
}

void AAstralEnemyController::HandlePawnDeathStarted(AActor* OwningActor)
{
	// GA 는 GA_Death 가 StartDeath 전에 취소했고, 콜리전 · 이동은 폰이 끈다 — 구독 순서에 기대지 않는다
	StateTreeComponent->StopLogic(TEXT("PawnDeathStarted"));

	// 트리 작업의 이동은 ExitState 가 취소한다. 트리 밖에서 시작된 이동까지 끊는다
	StopMovement();

	// 죽은 적은 타깃을 쥐지 않는다 (구독 정리)
	SetCurrentTarget(nullptr);
}
