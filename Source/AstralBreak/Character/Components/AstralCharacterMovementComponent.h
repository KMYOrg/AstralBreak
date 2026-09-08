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

	/**
	 * anim 루트모션(공격 몽타주) 중 폰과 부딪히면 표면을 따라 미끄러지지 않고 멈춘다.
	 * 근접 공격의 전진 루트모션이 적 캡슐을 밀며 슬라이드하면 캐릭터가 적 주위를 도는 궤도가 생겨 방향 보정(락온 4단계)이 무의미해진다.
	 * 벽·지형에서는 기존대로 슬라이드. 클라·서버가 같은 규칙이라 예측 정합 유지
	 */
	virtual float SlideAlongSurface(const FVector& Delta, float Time, const FVector& Normal, FHitResult& Hit, bool bHandleImpact) override;

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
