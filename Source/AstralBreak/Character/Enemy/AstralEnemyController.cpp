#include "AstralEnemyController.h"

#include "AstralCombatCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Components/StateTreeAIComponent.h"

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

	if (AAstralCombatCharacter* CombatCharacter = Cast<AAstralCombatCharacter>(GetPawn()))
	{
		CombatCharacter->OnCombatReady_Unregister(this);
		CombatCharacter->GetHealthComponent()->OnDeathStarted.RemoveDynamic(this, &ThisClass::HandlePawnDeathStarted);
	}

	Super::OnUnPossess();
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
}
