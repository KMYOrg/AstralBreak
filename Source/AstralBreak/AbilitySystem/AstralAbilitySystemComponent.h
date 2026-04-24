#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemComponent.h"
#include "AstralAbilitySystemComponent.generated.h"


UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralAbilitySystemComponent : public UAbilitySystemComponent
{
	GENERATED_BODY()

public:

	UAstralAbilitySystemComponent(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
	
	void ClearAbilityInput();

protected:

	
protected:

	TArray<FGameplayAbilitySpecHandle> InputPressedSpecHandles;
	TArray<FGameplayAbilitySpecHandle> InputReleasedSpecHandles;
	TArray<FGameplayAbilitySpecHandle> InputHeldSpecHandles;
	
};
