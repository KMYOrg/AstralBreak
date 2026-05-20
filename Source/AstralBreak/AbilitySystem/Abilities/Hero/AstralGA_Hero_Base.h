// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/AstralGameplayAbility.h"
#include "AstralGA_Hero_Base.generated.h"

/**
 * 
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_Base : public UAstralGameplayAbility
{
	GENERATED_BODY()
public:
	UAstralGA_Hero_Base(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
};
