// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/AstralAbilitySet.h"
#include "Engine/DataAsset.h"
#include "AstralPawnData.generated.h"

/**
 * 
 */
UCLASS(BlueprintType, Const, Abstract, Meta = (DisplayName = "Astral Pawn Data"))
class ASTRALBREAK_API UAstralPawnData : public UPrimaryDataAsset
{
	GENERATED_BODY()
	
public:
	UAstralPawnData(const FObjectInitializer& ObjectInitializer);

public:
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Pawn")
	TSubclassOf<APawn> PawnClass;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Abilities")
	TArray<TObjectPtr<const UAstralAbilitySet>> AbilitySets;
};
