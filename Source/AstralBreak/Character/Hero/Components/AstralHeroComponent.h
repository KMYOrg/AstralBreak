// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Components/GameFrameworkInitStateInterface.h"
#include "Components/PawnComponent.h"
#include "Input/AstralInputConfig.h"

#include "AstralHeroComponent.generated.h"

struct FInputActionValue;

UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralHeroComponent : public UPawnComponent, public IGameFrameworkInitStateInterface
{
	GENERATED_BODY()

public:

	UAstralHeroComponent(const FObjectInitializer& ObjectInitializer);

	UFUNCTION(BlueprintPure, Category = "Astral|Hero")
	static UAstralHeroComponent* FindHeroComponent(const AActor* Actor) { return (Actor ? Actor->FindComponentByClass<UAstralHeroComponent>() : nullptr); }
	
	void AddAdditionalInputConfig(const UAstralInputConfig* InputConfig);
	void RemoveAdditionalInputConfig(const UAstralInputConfig* InputConfig);

	/** True if this is controlled by a real player and has progressed far enough in initialization where additional input bindings can be added */
	bool IsReadyToBindInputs() const;
	
	/** The name of the extension event sent via UGameFrameworkComponentManager when ability inputs are ready to bind */
	static const FName NAME_BindInputsNow;

	static const FName NAME_ActorFeatureName;

	//~ Begin IGameFrameworkInitStateInterface interface
	virtual FName GetFeatureName() const override { return NAME_ActorFeatureName; }
	virtual bool CanChangeInitState(UGameFrameworkComponentManager* Manager, FGameplayTag CurrentState, FGameplayTag DesiredState) const override;
	virtual void HandleChangeInitState(UGameFrameworkComponentManager* Manager, FGameplayTag CurrentState, FGameplayTag DesiredState) override;
	virtual void OnActorInitStateChanged(const FActorInitStateChangedParams& Params) override;
	virtual void CheckDefaultInitialization() override;
	//~ End IGameFrameworkInitStateInterface interface

protected:

	virtual void OnRegister() override;
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	virtual void InitializePlayerInput(UInputComponent* PlayerInputComponent);

	/**
	 * 락온 카메라 추적 — ControlRotation을 타겟 방향으로 보간한다.
	 * 컨트롤 회전이 곧 카메라(SpringArm bUsePawnControlRotation)이자 이동 기저(Input_Move)라 별도 카메라 계층이 없다.
	 * Yaw는 항상 보조, Pitch는 플레이어 입력 유지 — 목표와의 차이가 PitchAssistThreshold를 넘을 때만 경계까지 보간.
	 * 락온이 아니면 CameraLag 복귀만 하고 빠진다 → 해제 시 기존 동작으로 자동 복귀
	 */
	void UpdateLockOnCamera(float DeltaTime);

	bool IsHardLocked() const;

	void Input_AbilityInputTagPressed(FGameplayTag InputTag);
	void Input_AbilityInputTagReleased(FGameplayTag InputTag);

	void Input_Move(const FInputActionValue& InputActionValue);
	void Input_LookMouse(const FInputActionValue& InputActionValue);
	void Input_LookStick(const FInputActionValue& InputActionValue);

	/** 락온 토글 — 네이티브 바인딩 (Started 1회). 선정·해제는 TargetingComponent가 소유 */
	void Input_LockOn(const FInputActionValue& InputActionValue);

protected:

	/** 락온 카메라 — 컨트롤 회전 보간 속도 (RInterpTo). 튜닝값, 추후 테스트로 조정 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|LockOn Camera", Meta = (ClampMin = "0.0"))
	float LockCameraInterpSpeed = 8.0f;

	/** 락온 카메라 — Pitch 개입 임계 (도). 목표 Pitch와의 차이가 이 값을 넘을 때만 경계까지 보정 (타겟이 화면 밖으로 나갈 때만) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|LockOn Camera", Meta = (ClampMin = "0.0", ClampMax = "89.0"))
	float PitchAssistThreshold = 15.0f;

	/** 락온 중 SpringArm CameraLagSpeed — 락온 보간 + 랙 보간 이중 겹침으로 흐물거리는 것 방지 (높을수록 랙 약함) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|LockOn Camera", Meta = (ClampMin = "0.0"))
	float LockCameraLagSpeed = 25.0f;

	/** True when player input bindings have been applied, will never be true for non - players */
	bool bReadyToBindInputs;

private:
	/** 락온 진입 시 캐시한 원래 CameraLagSpeed */
	float DefaultCameraLagSpeed = 0.0f;
	bool bLockCameraLagApplied = false;
};
