#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "Character/AstralPawnData.h"
#include "Input/AstralInputConfig.h"
#include "AstralPawnData_Hero.generated.h"

/**
 * 
 */
UCLASS(BlueprintType, Const, Meta = (DisplayName = "Astral Pawn Data (Hero)"))
class ASTRALBREAK_API UAstralPawnData_Hero : public UAstralPawnData
{
	GENERATED_BODY()
	
public:
	UAstralPawnData_Hero(const FObjectInitializer& ObjectInitializer);
	
public:
	// 영웅 식별 태그(게임 로직 식별 / 페이로드 직렬화 / DB 매칭에 사용)
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Astral|Identity", Meta = (Categories = "Hero"))
	FGameplayTag HeroTag;
	
	//Ability Input Tag 바인딩 설정, InputAction ↔ GameplayTag 매핑 정의
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Astral|Input")
	TObjectPtr<const UAstralInputConfig> InputConfig;

};
