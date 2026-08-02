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

	/** 폰 종속(무기 무관) 어빌리티 — Jump/Sprint/Dodge/Defend/Death. 무기 종속 GA는 장비 쪽 AbilitySet으로 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Abilities")
	TArray<TObjectPtr<const UAstralAbilitySet>> AbilitySets;

	/** 기본 장비 (플레이스홀더) — M1에서 이 소스가 로드아웃 페이로드 복원으로 교체된다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Equipment", Meta = (AllowedTypes = "AstralWeaponDefinition"))
	TArray<FPrimaryAssetId> DefaultEquipment;
};
