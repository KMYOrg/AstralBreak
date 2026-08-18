#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimNotifies/AnimNotifyState.h"
#include "Abilities/GameplayAbilityTypes.h"
#include "AstralAnimNotifyState_GameplayEventWindow.generated.h"

/**
 * 구간(밴드) 시작/끝에 GameplayEvent를 발송하는 범용 NotifyState.
 * 몽타주 에디터에서 구간이 눈에 보여 윈도우 튜닝이 직관적이다.
 * 용도: 콤보 입력 윈도우(Begin=ComboWindowOpen, End=ComboBranch), 추후 패링 윈도우/무기 트레이스 구간 등.
 */
UCLASS()
class ASTRALBREAK_API UAstralAnimNotifyState_GameplayEventWindow : public UAnimNotifyState
{
	GENERATED_BODY()

public:
	UAstralAnimNotifyState_GameplayEventWindow(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	virtual void NotifyBegin(USkeletalMeshComponent* MeshComp, UAnimSequenceBase* Animation, float TotalDuration, const FAnimNotifyEventReference& EventReference) override;
	virtual void NotifyEnd(USkeletalMeshComponent* MeshComp, UAnimSequenceBase* Animation, const FAnimNotifyEventReference& EventReference) override;

protected:
	/** 구간 시작 시 발송할 이벤트 (미지정 시 발송 안 함) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Astral|GameplayEvent")
	FGameplayTag BeginEventTag;

	/** 구간 끝 시 발송할 이벤트 (미지정 시 발송 안 함) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Astral|GameplayEvent")
	FGameplayTag EndEventTag;

	UPROPERTY(EditAnywhere, Category = "Astral|GameplayEvent")
	FGameplayEventData EventData;
};
