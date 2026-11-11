#pragma once

#include "CoreMinimal.h"
#include "GameplayAbilitySpecHandle.h"
#include "GameplayTagContainer.h"
#include "StateTreeTaskBase.h"
#include "AstralStateTreeTask_ActivateAbility.generated.h"

class AActor;
class UAbilitySystemComponent;

/** 한 번의 발동이 어떻게 끝났는지 — 종료 통지(람다)와 Task 가 함께 본다 */
struct FAstralAbilityRunState
{
	/** 발동 호출이 아직 돌아오지 않았다 — 이 안에서 끝나면 EnterState 가 결과를 직접 돌려준다 */
	bool bInEnterState = true;
	bool bEnded = false;
	bool bWasCancelled = false;
};

USTRUCT()
struct FAstralStateTreeTask_ActivateAbilityInstanceData
{
	GENERATED_BODY()

	/** 어빌리티를 가진 폰 */
	UPROPERTY(EditAnywhere, Category = Context)
	TObjectPtr<AActor> Actor = nullptr;

	/** 발동할 어빌리티의 asset tag — 이 태그를 가진 스펙 중 첫 번째를 발동한다 */
	UPROPERTY(EditAnywhere, Category = Parameter, Meta = (Categories = "Ability"))
	FGameplayTag AbilityTag;

	/** 이벤트 데이터의 Target 으로 어빌리티에 넘긴다. 묶지 않아도 된다 */
	UPROPERTY(EditAnywhere, Category = Input, Meta = (Optional))
	TObjectPtr<AActor> TargetActor = nullptr;

	TWeakObjectPtr<UAbilitySystemComponent> AbilitySystem;
	FGameplayAbilitySpecHandle AbilityHandle;
	FDelegateHandle AbilityEndedHandle;
	TSharedPtr<FAstralAbilityRunState> RunState;
};

/**
 * 어빌리티 하나를 발동하고 끝날 때까지 기다린다 (Docs/Design/m3-enemy-ai.md §8 ③).
 *
 * 들어올 때: 폰의 ASC 에서 AbilityTag 로 스펙을 찾아 종료 통지(OnAbilityEnded)를 구독한 뒤, TargetActor 를 실은 이벤트 데이터로 그 스펙을 발동한다
 *            (TriggerAbilityFromGameplayEvent — 스펙을 직접 지정하므로 어느 것이 켜졌는지 알고, 타깃을 실을 수 있다).
 *            스펙이 없거나 발동이 거부되면 실패. 발동 호출 안에서 이미 끝났으면 그 결과를 바로 돌려준다.
 * 끝날 때:   종료 통지에서 핸들을 대조해 끝낸다 — 취소면 실패, 아니면 성공. 틱하지 않는다.
 * 나갈 때:   구독을 풀고, 이 발동이 아직 살아 있으면 취소한다. 사망 때는 GA_Death 가 먼저 취소하므로 아무 일도 하지 않는다 — 몇 번 불려도 같다.
 */
USTRUCT(meta = (DisplayName = "Astral Activate Ability", Category = "Astral|AI"))
struct ASTRALBREAK_API FAstralStateTreeTask_ActivateAbility : public FStateTreeTaskCommonBase
{
	GENERATED_BODY()

	using FInstanceDataType = FAstralStateTreeTask_ActivateAbilityInstanceData;

	FAstralStateTreeTask_ActivateAbility();

	virtual const UStruct* GetInstanceDataType() const override { return FInstanceDataType::StaticStruct(); }
	virtual EStateTreeRunStatus EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const override;
	virtual void ExitState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const override;
};
