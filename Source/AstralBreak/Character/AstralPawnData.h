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

	/** 기본 장비 — 로드아웃 3단 소스의 폴백 (로비를 거치지 않는 단독 테스트 맵용) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Equipment", Meta = (AllowedTypes = "AstralWeaponDefinition,AstralRangedWeaponDefinition"))
	TArray<FPrimaryAssetId> DefaultEquipment;

	/**
	 * 장비 복원 여부 — Hub=false(로비 전투 불가: 장착=AbilitySet 부여이므로 장비 진입 자체를 차단), Raid=true.
	 * 원인(장비) 한 곳 차단이 최소 기계 — 부여/발동 차단 대안은 분류 규약·반쪽 장착을 낳는다.
	 * 한계선: "로비 무기 외형 표시" 기획 확정 시 enum/부여 정책 인자로 확장
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Equipment")
	bool bRestoreLoadoutEquipment = true;

	/**
	 * 시작 전투 스타일 — 빈 태그 = 이 폰은 스타일 시스템 미사용 (스타일 태그를 아예 세팅하지 않음).
	 * 스타일을 쓰는 히어로만 지정 (근/원 전환 히어로 = Melee 등). 히어로별 스타일 집합은 데이터가 정의
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Equipment", Meta = (Categories = "State.CombatStyle"))
	FGameplayTag InitialCombatStyle;
};
