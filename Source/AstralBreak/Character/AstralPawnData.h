// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/AstralAbilitySet.h"
#include "Engine/DataAsset.h"
#include "GameplayTagContainer.h"
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
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Equipment", Meta = (AllowedTypes = "AstralWeaponDefinition,AstralRangedWeaponDefinition"))
	TArray<FPrimaryAssetId> DefaultEquipment;

	/**
	 * 시작 전투 스타일 — 빈 태그 = 이 폰은 스타일 시스템 미사용 (스타일 태그를 아예 세팅하지 않음).
	 * 스타일을 쓰는 히어로만 지정 (근/원 전환 히어로 = Melee 등). 히어로별 스타일 집합은 데이터가 정의
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Equipment", Meta = (Categories = "State.CombatStyle"))
	FGameplayTag InitialCombatStyle;
};
