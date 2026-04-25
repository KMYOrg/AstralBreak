// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameplayEffectTypes.h"
#include "Animation/AnimInstance.h"
#include "AstralAnimInstance.generated.h"

/**
 * 
 */
UCLASS()
class ASTRALBREAK_API UAstralAnimInstance : public UAnimInstance
{
	GENERATED_BODY()
	
public:
	
	UAstralAnimInstance(const FObjectInitializer& ObjectInitializer);
	
	virtual void InitializeWithAbilitySystem(UAbilitySystemComponent* ASC);
	
protected:
	
	virtual void NativeInitializeAnimation() override;
	
protected:
	UPROPERTY(EditDefaultsOnly, Category = "GameplayTags")
	FGameplayTagBlueprintPropertyMap GameplayTagPropertyMap;
};
