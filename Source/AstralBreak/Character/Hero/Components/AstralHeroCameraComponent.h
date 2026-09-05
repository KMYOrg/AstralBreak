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

#if !UE_BUILD_SHIPPING
/** 락온 카메라 관측 — 디버그 위젯이 읽기만 한다. 실제 카메라 POV 기준 오차·화면 투영·수렴 반감기 (보간 속도 튜닝용) */
struct FAstralLockOnCameraDebugStats
{
	/** 폰 캡슐 중심 ↔ 조준점 (cm) */
	float Distance = 0.f;

	/** 실제 카메라 시선 대비 조준점 방위 오차 (도, 부호 있음) */
	float YawErrorDeg = 0.f;
	float PitchErrorDeg = 0.f;

	/** 조준점의 화면 투영 — 중심 0, 정규화 [-1, 1] */
	FVector2D ScreenOffset = FVector2D::ZeroVector;
	bool bOnScreen = false;

	/** 락온(또는 타겟 교체) 시점의 Yaw 오차 — 반감기 기준 */
	float InitialYawErrorDeg = 0.f;

	/** 락온 이후 경과 (초) */
	float ElapsedSinceLock = 0.f;

	/** |Yaw 오차|가 초기값의 절반 아래로 처음 내려간 시각 (초). 미도달 = -1 */
	float YawHalfLifeSeconds = -1.f;
};
#endif

/**
 * 히어로 카메라 — "타깃을 화면에 어떻게 유지하는가" [히어로 전용 · 로컬 전용].
 * 조준 원점은 카메라 POV — 회전 → 카메라 이동 → 목표 재계산의 되먹임으로 유효 보간 속도가 거리에 따라 감쇠하지만
 * (d/(L+d)), Phase 2 측정에서 붐 피벗·명목 위치와 체감 차이가 없어 화면 중앙 정합이 정확한 POV를 유지한다.
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

#if !UE_BUILD_SHIPPING
	const FAstralLockOnCameraDebugStats& GetDebugStats() const { return DebugStats; }
#endif

protected:
	//~UActorComponent
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
	//~End UActorComponent

	/** 타게팅 변경 이벤트 — 틱 on/off (+ 관측 리셋) */
	UFUNCTION()
	void HandleTargetingChanged();

	/** 하드 락 + 유효 타겟인가 — 틱 초입 재검사와 이벤트 핸들러가 공유 */
	bool IsTrackingTarget() const;

	/** ControlRotation 보조 보간 — Yaw는 항상, Pitch는 임계 밖에서만 경계까지. */
	void UpdateLockOnCamera(float DeltaTime);

#if !UE_BUILD_SHIPPING
	/** 락온 시작·타겟 교체 시점 — 초기 Yaw 오차 기록, 반감기 리셋 */
	void ResetDebugStats();

	/** 매 틱 — 실제 카메라 POV 기준 오차·화면 투영·반감기 갱신 */
	void UpdateDebugStats(float DeltaTime, const APlayerController* PC, const FVector& ViewLocation, const FRotator& ViewRotation, const FVector& AimLocation);
#endif

protected:
	UPROPERTY(EditDefaultsOnly, Category = "Astral|LockOn Camera", Meta = (ShowOnlyInnerProperties))
	FAstralLockOnCameraParams Params;

private:
	UPROPERTY(Transient)
	TObjectPtr<USpringArmComponent> CameraBoom;

	UPROPERTY(Transient)
	TObjectPtr<UCameraComponent> FollowCamera;

	UPROPERTY(Transient)
	TObjectPtr<UAstralTargetingComponent> Targeting;

#if !UE_BUILD_SHIPPING
	FAstralLockOnCameraDebugStats DebugStats;
#endif
};
