#pragma once

#include "CoreMinimal.h"
#include "GameplayEffectTypes.h"
#include "Animation/AnimInstance.h"
#include "AstralAnimInstance.generated.h"

class APawn;
class UAbilitySystemComponent;
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

	/** 조준 기준 회전 — APawn::GetBaseAimRotation (소유자는 컨트롤 회전, 시뮬 프록시는 RemoteViewPitch + 액터 Yaw) */
	FRotator BaseAimRotation = FRotator::ZeroRotator;

	/** ASC 태그 State.Ranged.Aiming (게임 스레드에서 읽어 스냅샷). 전투 스타일은 AnimInstance 가 알 필요 없다 — 무기별 그래프는 장비 매니저의 레이어 링크가 고른다 */
	bool bAiming = false;
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

	// ---- 조준 (ASC 태그 스냅샷) — 무기 종류·스타일은 여기 두지 않는다 (무기별 그래프 = 장비 계열의 AnimLayerClass 링크) ----

	// 사격 자세 유지 중 (State.Ranged.Aiming — 원거리 GA가 발사마다 갱신하는 지속 GE). 조준 로코모션(strafe)·AimOffset 알파
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Combat")
	bool bIsAiming = false;

	// 조준 방향 − 몸 방향 Yaw (-180~180). AimOffset X
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Combat")
	float AimYaw = 0.0f;

	// 조준 Pitch (-180~180, 보통 ±90 안). AimOffset Y
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Combat")
	float AimPitch = 0.0f;

private:
	FAstralAnimSnapshot Snapshot;

	/** 태그 조회용 — InitializeWithAbilitySystem 에서 결합. 게임 스레드에서만 읽는다 */
	TWeakObjectPtr<UAbilitySystemComponent> BoundASC;

	UPROPERTY(Transient)
	TObjectPtr<APawn> OwningPawn;

	UPROPERTY(Transient)
	TObjectPtr<UAstralCharacterMovementComponent> AstralMovementComponent;
};
