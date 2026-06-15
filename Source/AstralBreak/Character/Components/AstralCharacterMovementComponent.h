#pragma once

#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "AstralCharacterMovementComponent.generated.h"

USTRUCT(BlueprintType)
struct FAstralCharacterGroundInfo
{
	GENERATED_BODY()

	FAstralCharacterGroundInfo()
		: LastUpdateFrame(0)
		, GroundDistance(0.0f)
	{}

	uint64 LastUpdateFrame;

	UPROPERTY(BlueprintReadOnly)
	FHitResult GroundHitResult;

	UPROPERTY(BlueprintReadOnly)
	float GroundDistance;
};

UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralCharacterMovementComponent : public UCharacterMovementComponent
{
	GENERATED_BODY()

public:
	UAstralCharacterMovementComponent(const FObjectInitializer& ObjectInitializer);

	/** 프레임당 1회 캐싱되는 발밑 지면 정보 반환 (Game Thread 전용 — 내부에서 World trace 수행) */
	UFUNCTION(BlueprintCallable, Category = "Astral|CharacterMovement")
	const FAstralCharacterGroundInfo& GetGroundInfo();

protected:
	FAstralCharacterGroundInfo CachedGroundInfo;
};
