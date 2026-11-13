#pragma once

#include "CoreMinimal.h"
#include "AIController.h"
#include "AstralEnemyController.generated.h"

class UAbilitySystemComponent;
class UAstralHealthSet;
class UAstralThreatComponent;
class UStateTreeAIComponent;
struct FGameplayEffectSpec;
struct FGameplayTag;

/**
 * 적 AI 컨트롤러 — StateTree 의 시작 · 정지를 폰의 생명주기에 맞추고, 트리가 읽는 타깃을 쥔다 (Docs/Design/m3-enemy-ai.md §1 · §8 · §9).
 * 트리는 C++ 에 고정하지 않고 파생 BP 의 StateTreeComponent 참조로 지정한다.
 * Perception · 팀 동기화 · 스폰은 뒤 단위에서 붙는다.
 *
 * 시작: 폰의 전투 준비 완료 신호를 받아 시작한다. 엔진 자동 시작은 둘 다 끈다 —
 * 컴포넌트 자동 시작은 런타임 스폰에서 컨트롤러 BeginPlay 가 Possess 보다 먼저라 컨텍스트 Actor 가 없고,
 * bStartAILogicOnPossess 는 APawn::PostInitializeComponents 안이라 어빌리티 부여보다 앞선다.
 *
 * 정지: 사망 시작에서 멈추고, 그 밖의 모든 제거 경로는 OnUnPossess 가 받는다.
 * AAIController::OnUnPossess 는 폰을 비운 뒤 StopLogic 을 불러 컨텍스트 검사가 실패한다 — 그러면 ExitState 가 불리지 않고 트리는 실행 중으로 남는다.
 *
 * 타깃: CurrentTarget 하나가 단일 원천이다. 고르는 시점은 트리의 판단 지점(AcquireTarget Task)이고 매 틱 고르지 않는다.
 * 잃는 것(사망 · 파괴)만 여기서 구독해 값을 비우고 트리에 AI.Event.TargetLost 를 보낸다. 전부 서버 전용 — 복제하지 않는다.
 *
 * 어그로: 누구를 고를지는 ThreatComponent 가 정한다(적대심 가중 추첨 · 유지 시간 · 제외). 이 컨트롤러는 후보를 모아 넘기고,
 * 폰이 받은 피해(UAstralHealthSet::OnDamaged)를 기록에 넣고, 현재 타깃이 아닌 후보에게 맞으면 트리에 AI.Event.Retarget 을 보낸다.
 *
 * 경직(§10 C2 ⑦): 폰 ASC 의 State.Enemy.Staggered 태그 이벤트를 구독해, 붙으면 트리에 AI.Event.Staggered 를 보낸다.
 * 그 태그를 다는 GA 가 없는 적(마네킹)에서는 아무 일도 없다.
 */
UCLASS()
class ASTRALBREAK_API AAstralEnemyController : public AAIController
{
	GENERATED_BODY()

public:
	AAstralEnemyController(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	UStateTreeAIComponent* GetStateTreeComponent() const { return StateTreeComponent; }

	UAstralThreatComponent* GetThreatComponent() const { return ThreatComponent; }

	AActor* GetCurrentTarget() const { return CurrentTarget; }

	/**
	 * 타깃을 고른다 — 플레이어 폰을 후보로 모아 ThreatComponent 에 넘긴다. 골랐으면 true.
	 * 피해 기록이 없으면 가장 가까운 후보(단위 A 규칙), 유지 시간 안이면 현재 타깃 그대로, 아니면 적대심 가중 추첨이다
	 */
	bool AcquireTarget();

	/** 타깃을 쓰는 곳은 이 함수 하나 — 앞 타깃의 구독을 풀고 새 타깃의 사망 · 파괴를 구독한다. 이벤트는 보내지 않는다. 타깃이 바뀌면 공격 자리도 비운다 */
	void SetCurrentTarget(AActor* NewTarget);

	bool HasEngageSlot() const { return bHasEngageSlot; }
	float GetEngageBearing() const { return EngageBearing; }

	/**
	 * 공격 자리를 고른다 (§13 T1 · T2) — 타깃 둘레 고리에서 지금 내가 있는 쪽에 가장 가까우면서,
	 * 같은 타깃을 쥔 다른 적의 자리와 MinSeparationDegrees 이상 떨어진 방위를 잡는다.
	 * 다른 적의 자리는 고르는 이 시점에 읽는다 — 등록부도 구독도 없다. 타깃을 놓았거나 죽은 적은 자리가 비어 있어 저절로 빠진다.
	 * 부르는 쪽은 트리의 Task(FAstralStateTreeTask_EngageSlot)다. 그 Task 를 쓰지 않는 트리의 적은 자리를 잡지 않는다. 타깃이 없으면 false
	 */
	bool SelectEngageSlot(float MinSeparationDegrees);

	/** 자리의 월드 좌표 = 타깃 위치 + 방위 방향 × Radius (높이는 타깃의 것). 타깃이나 자리가 없으면 false */
	bool GetEngageLocation(float Radius, FVector& OutLocation) const;

	/** 타깃에서 내 폰으로 향하는 방위(도) — 타깃이 없거나 겹쳐 있으면 false */
	bool GetBearingFromTarget(float& OutDegrees) const;

public:
	/**
	 * 지금 쫓는 대상 — 트리가 직접 바인딩해 읽는다 (MoveTo.TargetActor · ActivateAbility.TargetActor).
	 * 바인딩 메뉴에 나오려면 CPF_Edit + public 이어야 한다. 값은 SetCurrentTarget 으로만 바꾼다
	 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category = "Astral|AI")
	TObjectPtr<AActor> CurrentTarget;

	/**
	 * 공격 자리 — 타깃 둘레 고리 위의 방위(도, 타깃에서 자리로 향하는 방향의 yaw). bHasEngageSlot 이 참일 때만 뜻이 있다.
	 * 값은 SelectEngageSlot 이 쓰고 SetCurrentTarget 이 비운다. 서버 전용 — 복제하지 않는다
	 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category = "Astral|AI")
	float EngageBearing = 0.f;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Transient, Category = "Astral|AI")
	bool bHasEngageSlot = false;

protected:
	//~ AController
	virtual void OnPossess(APawn* InPawn) override;
	virtual void OnUnPossess() override;
	//~ End AController

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|AI")
	TObjectPtr<UStateTreeAIComponent> StateTreeComponent;

	/** 위협 기록 · 타깃 선정 규칙 — 값(피해 가중 · 유지 시간 등)은 파생 BP 에서 고친다 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|AI")
	TObjectPtr<UAstralThreatComponent> ThreatComponent;

private:
	/** 시작 지점은 이 함수 하나 — 폰이 살아 있고 트리가 돌고 있지 않을 때만. StartLogic 은 실행 중인 트리를 재시작한다 */
	void TryStartLogic();

	/** 쫓던 타깃을 잃었다 — 값을 비우고, 트리가 돌고 있으면 AI.Event.TargetLost 를 보낸다 */
	void HandleTargetLost(const AActor* LostActor);

	/** 폰이 받는 피해 구독 — 빙의 때 걸고 언포제션 · 사망 때 푼다. 폴링 없음 */
	void BindPawnDamaged(const APawn* InPawn);
	void UnbindPawnDamaged();

	/** 폰이 피해를 받았다 — 가해자가 플레이어 폰이면 기록하고, 다시 뽑아야 하면 트리에 AI.Event.Retarget 을 보낸다 */
	void HandlePawnDamaged(AActor* EffectInstigator, AActor* EffectCauser, const FGameplayEffectSpec* EffectSpec, float Damage, float OldValue, float NewValue);

	TWeakObjectPtr<const UAstralHealthSet> BoundHealthSet;
	FDelegateHandle PawnDamagedHandle;

	/** 폰의 행동 불가 태그(State.Enemy.Staggered — 피격 반응 · 경직 GA 가 단다) 구독 — 피해 구독과 같은 자리에서 걸고 푼다. 폴링 없음 */
	void BindPawnStaggered(const APawn* InPawn);
	void UnbindPawnStaggered();

	/** 태그가 붙었다 — 트리에 AI.Event.Staggered 를 보낸다(Root 의 전환이 Stagger 로 보낸다. 그 전환이 없는 트리에서는 버려진다). 떨어지는 것은 트리의 Task 가 직접 듣는다 */
	void HandlePawnStaggeredTagChanged(const FGameplayTag Tag, int32 NewCount);

	TWeakObjectPtr<UAbilitySystemComponent> BoundStaggerAbilitySystem;
	FDelegateHandle PawnStaggeredHandle;

	UFUNCTION()
	void HandlePawnDeathStarted(AActor* OwningActor);

	UFUNCTION()
	void HandleTargetDeathStarted(AActor* OwningActor);

	UFUNCTION()
	void HandleTargetDestroyed(AActor* DestroyedActor);
};
