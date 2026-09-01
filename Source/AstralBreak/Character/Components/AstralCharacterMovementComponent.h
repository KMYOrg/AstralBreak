#pragma once

#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameplayEffectTypes.h"
#include "AstralCharacterMovementComponent.generated.h"

class UAstralAbilitySystemComponent;

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

	/** 모드별 최대 속도 × MoveSpeedMultiplier — 슬로우/가속이 걷기·질주(파생에서 승계) 전부에 일괄 적용 */
	virtual float GetMaxSpeed() const override;

	void InitializeWithAbilitySystem(UAstralAbilitySystemComponent* InASC);
	void UninitializeFromAbilitySystem();

	UAstralAbilitySystemComponent* GetBoundAbilitySystem() const { return BoundASC; }

	float GetMoveSpeedMultiplier() const { return CachedMoveSpeedMultiplier; }
	float GetScaledMaxWalkSpeed() const { return MaxWalkSpeed * CachedMoveSpeedMultiplier; }

protected:

	virtual void OnUnregister() override;

	virtual void OnAbilitySystemBound();
	virtual void OnAbilitySystemUnbound();

	void HandleMoveSpeedMultiplierChanged(const FOnAttributeChangeData& Data);

	UPROPERTY(Transient)
	TObjectPtr<UAstralAbilitySystemComponent> BoundASC;
	
	float CachedMoveSpeedMultiplier = 1.0f;

	FDelegateHandle MoveSpeedMultiplierChangedHandle;

	FAstralCharacterGroundInfo CachedGroundInfo;
};
