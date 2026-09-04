#pragma once

#include "CoreMinimal.h"
#include "Components/PawnComponent.h"
#include "AstralHeroCameraComponent.generated.h"

class UAstralTargetingComponent;
class UCameraComponent;
class USpringArmComponent;

/**
 * 락온 카메라 튜닝값 (lockon-camera-refactor §2).
 */
USTRUCT(BlueprintType)
struct FAstralLockOnCameraParams
{
	GENERATED_BODY()

	/** Yaw 보조 보간 속도 — 항상 작동. 움직이는 타겟을 놓치지 않으려면 빨라야 한다 */
	UPROPERTY(EditDefaultsOnly, Category = "LockOn Camera", Meta = (ClampMin = "0.0"))
	float YawInterpSpeed = 8.0f;

	/** Pitch 보조 보간 속도 — 임계 밖에서만 작동 */
	UPROPERTY(EditDefaultsOnly, Category = "LockOn Camera", Meta = (ClampMin = "0.0"))
	float PitchInterpSpeed = 5.0f;

	/** Pitch 개입 임계 (도) — 목표와의 차이가 이 값을 넘을 때만 경계까지 보정 (타겟이 화면 밖으로 나갈 때만) */
	UPROPERTY(EditDefaultsOnly, Category = "LockOn Camera", Meta = (ClampMin = "0.0", ClampMax = "89.0"))
	float PitchAssistThreshold = 15.0f;
};

/**
 * 히어로 카메라 — "타깃을 화면에 어떻게 유지하는가" [히어로 전용 · 로컬 전용].
 * 타겟 액터 소멸은 TargetingComponent의 매 프레임 약한 참조 검사가 ClearLock → 이벤트로 이어지고
 * 그 사이 한 프레임은 틱 초입 재검사가 건너뛴다
 */
UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralHeroCameraComponent : public UPawnComponent
{
	GENERATED_BODY()

public:
	UAstralHeroCameraComponent(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	void InitializeCamera(USpringArmComponent* InCameraBoom, UCameraComponent* InFollowCamera, UAstralTargetingComponent* InTargeting);

	/** 락온 카메라 프로필이 SpringArm에 적용된 상태인가 (디버그·검증용) */
	bool IsLockOnProfileApplied() const { return bLockOnProfileApplied; }

protected:
	//~UActorComponent
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
	//~End UActorComponent

	/** 타게팅 변경 이벤트 — 프로필 적용/복구 + 틱 on/off */
	UFUNCTION()
	void HandleTargetingChanged();

	/** 하드 락 + 유효 타겟인가 — 틱 초입 재검사와 이벤트 핸들러가 공유 */
	bool IsTrackingTarget() const;

	/** ControlRotation 보조 보간 — Yaw는 항상, Pitch는 임계 밖에서만 경계까지. */
	void UpdateLockOnCamera(float DeltaTime);

	/** SpringArm 프로필 적용/복구 — 현재는 CameraLagSpeed 하나 */
	void ApplyCameraProfile(bool bLockOn);

protected:
	UPROPERTY(EditDefaultsOnly, Category = "Astral|LockOn Camera", Meta = (ShowOnlyInnerProperties))
	FAstralLockOnCameraParams Params;

	/** 락온 중 SpringArm CameraLagSpeed — 느슨한 멤버로 둔다 (Phase 2 조준 원점 결정 후 승격 또는 삭제). */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|LockOn Camera", Meta = (ClampMin = "0.0"))
	float LockCameraLagSpeed = 25.0f;

private:
	UPROPERTY(Transient)
	TObjectPtr<USpringArmComponent> CameraBoom;

	UPROPERTY(Transient)
	TObjectPtr<UCameraComponent> FollowCamera;

	UPROPERTY(Transient)
	TObjectPtr<UAstralTargetingComponent> Targeting;
	
	float DefaultCameraLagSpeed = 0.0f;
	bool bLockOnProfileApplied = false;
};
