#include "AstralEnemyController.h"

#include "Components/StateTreeAIComponent.h"

AAstralEnemyController::AAstralEnemyController(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	StateTreeComponent = CreateDefaultSubobject<UStateTreeAIComponent>(TEXT("StateTreeComponent"));
	StateTreeComponent->SetStartLogicAutomatically(false);

	// AAIController::PostInitializeComponents 가 BrainComponent 로 찾아 OnPossess 에서 StartLogic 을 부른다
	bStartAILogicOnPossess = true;
}
