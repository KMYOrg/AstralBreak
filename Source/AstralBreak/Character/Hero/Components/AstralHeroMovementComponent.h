#pragma once

#include "CoreMinimal.h"
#include "Character/Components/AstralCharacterMovementComponent.h"
#include "AstralHeroMovementComponent.generated.h"

/**
 * Hero 전용 CharacterMovementComponent.
 * 공용 이동 기능(GroundInfo 등)은 베이스 UAstralCharacterMovementComponent에 있고,
 * 여기엔 Hero 고유 이동(스프린트/회피 튜닝 등)을 추가한다.
 */
UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralHeroMovementComponent : public UAstralCharacterMovementComponent
{
	GENERATED_BODY()

public:
	UAstralHeroMovementComponent(const FObjectInitializer& ObjectInitializer);
	
	virtual float GetMaxSpeed() const override;

	/** Sprint GA에서 호출. 추후 compressed flag 예측 도입 시 이 플래그가 SavedMove 직렬화 대상 */
	void SetSprinting(bool bNewSprinting) { bWantsToSprint = bNewSprinting; }

	UFUNCTION(BlueprintPure, Category = "Astral|HeroMovement")
	bool IsSprinting() const { return bWantsToSprint; }

protected:

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Astral|HeroMovement")
	float SprintSpeed = 800.0f;

	bool bWantsToSprint = false;
};
