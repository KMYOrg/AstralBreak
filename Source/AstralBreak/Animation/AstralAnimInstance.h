#pragma once

#include "CoreMinimal.h"
#include "GameplayEffectTypes.h"
#include "Animation/AnimInstance.h"
#include "AstralAnimInstance.generated.h"

class APawn;
class UCharacterMovementComponent;
class UAstralCharacterMovementComponent;

struct FAstralAnimSnapshot
{
	/** 월드 속도 (수평/수직 포함) */
	FVector WorldVelocity = FVector::ZeroVector;

	/** 월드 가속도 (이동 입력 의도) */
	FVector WorldAcceleration = FVector::ZeroVector;

	/** 액터 회전 (LocalVelocity/MovementDirection 계산용) */
	FRotator ActorRotation = FRotator::ZeroRotator;

	/** 공중 여부 (MovementMode == Falling). 상승/하강 구분은 WorldVelocity.Z로 ThreadSafe에서 계산 */
	bool bIsInAir = false;

	/** 지면 이동 여부 (MovementMode == Walking/NavWalking). IsMovingOnGround() */
	bool bIsOnGround = false;

	/** 발밑 지면까지 거리 */
	float GroundDistance = 0.0f;
};


UCLASS()
class ASTRALBREAK_API UAstralAnimInstance : public UAnimInstance
{
	GENERATED_BODY()
	
public:

	UAstralAnimInstance(const FObjectInitializer& ObjectInitializer);

	virtual void InitializeWithAbilitySystem(UAbilitySystemComponent* ASC);

protected:
	//~ UAnimInstance
	virtual void NativeInitializeAnimation() override;
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;
	virtual void NativeThreadSafeUpdateAnimation(float DeltaSeconds) override;
	//~ End UAnimInstance

protected:
	UPROPERTY(EditDefaultsOnly, Category = "GameplayTags")
	FGameplayTagBlueprintPropertyMap GameplayTagPropertyMap;
	
	// 수평 속도 (cm/s). Velocity.Size2D()
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	float Speed = 0.0f;

	// 수평 가속도 크기. 이동 입력 세기
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	float Acceleration = 0.0f;

	// 캐릭터 forward 대비 velocity 각도 (-180~180). strafe/락온 대비. Phase 1은 사실상 0
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	float MovementDirection = 0.0f;

	// 지면 여부 (Walking/NavWalking). IsMovingOnGround()
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	bool bIsOnGround = false;

	// 공중 여부 (상승/하강 모두 포함). State Machine의 지상↔공중 전환에 사용
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	bool bIsInAir = false;

	// 상승 중 (공중 && Z > 0). 점프로 올라가는 구간
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	bool bIsJumping = false;

	// 하강 중 (공중 && 상승 아님). 떨어지는 구간
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	bool bIsFalling = false;

	// 이동 입력 존재 여부 (가속도 기반)
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	bool bHasMovementInput = false;

	// 발밑 지면까지 거리 (착지 예측용) 
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	float GroundDistance = 0.0f;

private:
	FAstralAnimSnapshot Snapshot;

	UPROPERTY(Transient)
	TObjectPtr<APawn> OwningPawn;

	UPROPERTY(Transient)
	TObjectPtr<UAstralCharacterMovementComponent> AstralMovementComponent;
};
