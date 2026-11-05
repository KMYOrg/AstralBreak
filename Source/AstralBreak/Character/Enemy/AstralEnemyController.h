#pragma once

#include "CoreMinimal.h"
#include "AIController.h"
#include "AstralEnemyController.generated.h"

class UStateTreeAIComponent;

/**
 * 적 AI 컨트롤러 뼈대 — StateTree 를 Possess 시점에 시작하는 데까지만 책임진다.
 * 트리는 C++ 에 고정하지 않고 파생 BP 의 StateTreeComponent 참조로 지정한다.
 * Perception · 어그로 · 팀 동기화 · 스폰은 M3 본 작업에서 붙는다 (Docs/StateTree/Phase2Report.md)
 *
 * 컴포넌트 자동 시작을 끄는 이유: 런타임 스폰은 APawn::PostInitializeComponents → SpawnDefaultController 순서라
 * 컨트롤러 BeginPlay(자동 시작 지점)가 Possess 보다 먼저 돌고, 그때는 AIOwner->GetPawn() 이 없어 컨텍스트 Actor 를 채우지 못한다.
 * Possess 뒤에 시작하면 런타임 스폰과 레벨 배치가 같은 경로를 탄다.
 */
UCLASS()
class ASTRALBREAK_API AAstralEnemyController : public AAIController
{
	GENERATED_BODY()

public:
	AAstralEnemyController(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	UStateTreeAIComponent* GetStateTreeComponent() const { return StateTreeComponent; }

protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|AI")
	TObjectPtr<UStateTreeAIComponent> StateTreeComponent;
};
