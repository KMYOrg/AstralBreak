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

	/** 기본 장비 — 로드아웃 3단 소스의 폴백. 전투 문맥(Full 정책) 전용 — 로비를 거치지 않는 단독 테스트 맵용 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Equipment", Meta = (AllowedTypes = "AstralWeaponDefinition,AstralRangedWeaponDefinition"))
	TArray<FPrimaryAssetId> DefaultEquipment;

	// 문맥(Hub/Raid) 축은 여기 없다 — 장착 정책은 AAstralGameState.EquipmentPolicy(월드 속성)로 승격 (E-1).
	// PawnData는 히어로 축만 남아 히어로 × 문맥 곱집합이 해소된다

	/**
	 * 시작 전투 스타일 — 빈 태그 = 이 폰은 스타일 시스템 미사용 (스타일 태그를 아예 세팅하지 않음).
	 * 스타일을 쓰는 히어로만 지정 (근/원 전환 히어로 = Melee 등). 히어로별 스타일 집합은 데이터가 정의
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Equipment", Meta = (Categories = "State.CombatStyle"))
	FGameplayTag InitialCombatStyle;
};
