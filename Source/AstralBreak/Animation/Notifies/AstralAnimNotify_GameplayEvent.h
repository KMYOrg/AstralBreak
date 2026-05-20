#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimNotifies/AnimNotify.h"
#include "Abilities/GameplayAbilityTypes.h"
#include "AstralAnimNotify_GameplayEvent.generated.h"


/**
 * 
 */
UCLASS()
class ASTRALBREAK_API UAstralAnimNotify_GameplayEvent : public UAnimNotify
{
	GENERATED_BODY()
	
public:
	UAstralAnimNotify_GameplayEvent(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
	
public:
	virtual void Notify(USkeletalMeshComponent* MeshComp, UAnimSequenceBase* Animation, const FAnimNotifyEventReference& EventReference) override;

protected:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Astral|GameplayEvent")
	FGameplayTag EventTag;
	
	UPROPERTY(EditAnywhere, Category = "Astral|GameplayEvent")
	FGameplayEventData EventData;
};
