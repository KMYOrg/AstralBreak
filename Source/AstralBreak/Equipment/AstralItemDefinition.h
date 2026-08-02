#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "AstralItemDefinition.generated.h"

class UAstralAbilitySet;
class UAstralEquipmentFamily;

/**
 * 장비 가능 아이템 정의의 공통 베이스 — FPrimaryAssetId 해석 결과의 공통 타입 (진입점).
 * "무엇을 물려받는가(계열)"와 "고유 능력치(StatSet)"만 알고, 종류별 데이터(무기 메시 등)는 파생이 든다.
 * 새 장비 종류 = 이 클래스 파생 + AAstralEquipmentActor 파생 + ini 스캔 룰 1줄.
 */
UCLASS(Abstract, BlueprintType, Const)
class ASTRALBREAK_API UAstralItemDefinition : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	/** 소속 계열 — 스폰 액터 구성·부여 어빌리티는 계열이 결정 (N개 변형이 공유) */
	UPROPERTY(EditDefaultsOnly, Category = "Item")
	TObjectPtr<const UAstralEquipmentFamily> EquipmentFamily;

	/** 스탯 GE를 담은 AbilitySet. 무기/방어구 공통이므로 베이스 소유. */
	UPROPERTY(EditDefaultsOnly, Category = "Item")
	TObjectPtr<const UAstralAbilitySet> StatSet;
};
