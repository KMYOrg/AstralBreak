#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "StateTreeTaskBase.h"
#include "AstralStateTreeTask_WaitTagRemoved.generated.h"

class AActor;
class UAbilitySystemComponent;

USTRUCT()
struct FAstralStateTreeTask_WaitTagRemovedInstanceData
{
	GENERATED_BODY()

	/** 태그를 가진 폰 */
	UPROPERTY(EditAnywhere, Category = Context)
	TObjectPtr<AActor> Actor = nullptr;

	/** 이 태그가 폰의 ASC 에서 떨어질 때까지 기다린다 */
	UPROPERTY(EditAnywhere, Category = Parameter)
	FGameplayTag Tag;

	TWeakObjectPtr<UAbilitySystemComponent> AbilitySystem;
	FDelegateHandle TagChangedHandle;
};

/**
 * 폰의 ASC 에서 태그가 떨어질 때까지 기다린다 (Docs/Design/m3-enemy-ai.md §10 C2 ⑦ — Stagger 상태의 '경직 대기').
 *
 * 들어올 때: 태그가 없으면 바로 성공. 있으면 GAS 의 태그 이벤트(0 ↔ 1 이상)를 구독하고 Running.
 * 끝날 때:   태그 수가 0 이 되는 통지에서 성공으로 끝낸다. 틱하지 않는다 — 시간이 아니라 태그의 주인(피격 반응 · 경직 GA)이 길이를 정한다.
 * 나갈 때:   구독을 푼다 — 몇 번 불려도 같다.
 * ASC 가 없거나 태그가 비어 있으면 실패.
 */
USTRUCT(meta = (DisplayName = "Astral Wait Tag Removed", Category = "Astral|AI"))
struct ASTRALBREAK_API FAstralStateTreeTask_WaitTagRemoved : public FStateTreeTaskCommonBase
{
	GENERATED_BODY()

	using FInstanceDataType = FAstralStateTreeTask_WaitTagRemovedInstanceData;

	FAstralStateTreeTask_WaitTagRemoved();

	virtual const UStruct* GetInstanceDataType() const override { return FInstanceDataType::StaticStruct(); }
	virtual EStateTreeRunStatus EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const override;
	virtual void ExitState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const override;
};
