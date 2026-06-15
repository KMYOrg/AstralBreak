#pragma once

#include "CoreMinimal.h"
#include "Character/Components/AstralCharacterMovementComponent.h"
#include "AstralHeroMovementComponent.generated.h"

/**
 * Hero 전용 CharacterMovementComponent.
 * 공용 이동 기능(GroundInfo 등)은 베이스 UAstralCharacterMovementComponent에 있고,
 * 여기엔 Hero 고유 이동(스프린트/회피 튜닝 등)을 추가한다. 현재는 베이스와 동일.
 */
UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralHeroMovementComponent : public UAstralCharacterMovementComponent
{
	GENERATED_BODY()

public:
	UAstralHeroMovementComponent(const FObjectInitializer& ObjectInitializer);
};
