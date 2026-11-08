#pragma once

#include "CoreMinimal.h"
#include "AIController.h"
#include "AstralEnemyController.generated.h"

class UStateTreeAIComponent;

/**
 * 적 AI 컨트롤러 — StateTree 의 시작 · 정지를 폰의 생명주기에 맞춘다 (Docs/Design/m3-enemy-ai.md §1).
 * 트리는 C++ 에 고정하지 않고 파생 BP 의 StateTreeComponent 참조로 지정한다.
 * Perception · 어그로 · 팀 동기화 · 스폰은 M3 본 작업에서 붙는다.
 *
 * 시작: 폰의 전투 준비 완료 신호를 받아 시작한다. 엔진 자동 시작은 둘 다 끈다 —
 * 컴포넌트 자동 시작은 런타임 스폰에서 컨트롤러 BeginPlay 가 Possess 보다 먼저라 컨텍스트 Actor 가 없고,
 * bStartAILogicOnPossess 는 APawn::PostInitializeComponents 안이라 어빌리티 부여보다 앞선다.
 *
 * 정지: 사망 시작에서 멈추고, 그 밖의 모든 제거 경로는 OnUnPossess 가 받는다.
 * AAIController::OnUnPossess 는 폰을 비운 뒤 StopLogic 을 불러 컨텍스트 검사가 실패한다 — 그러면 ExitState 가 불리지 않고 트리는 실행 중으로 남는다.
 */
UCLASS()
class ASTRALBREAK_API AAstralEnemyController : public AAIController
{
	GENERATED_BODY()

public:
	AAstralEnemyController(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	UStateTreeAIComponent* GetStateTreeComponent() const { return StateTreeComponent; }

protected:
	//~ AController
	virtual void OnPossess(APawn* InPawn) override;
	virtual void OnUnPossess() override;
	//~ End AController

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|AI")
	TObjectPtr<UStateTreeAIComponent> StateTreeComponent;

private:
	/** 시작 지점은 이 함수 하나 — 폰이 살아 있고 트리가 돌고 있지 않을 때만. StartLogic 은 실행 중인 트리를 재시작한다 */
	void TryStartLogic();

	UFUNCTION()
	void HandlePawnDeathStarted(AActor* OwningActor);
};
