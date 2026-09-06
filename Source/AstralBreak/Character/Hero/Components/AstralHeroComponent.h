// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Character/Hero/Input/AstralTargetSwitchInput.h"
#include "Components/GameFrameworkInitStateInterface.h"
#include "Components/PawnComponent.h"
#include "Input/AstralInputConfig.h"

#include "AstralHeroComponent.generated.h"

class UAstralTargetingComponent;
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

#if !UE_BUILD_SHIPPING
	/** 디버그 관측 — 타겟 전환 입력 기계 (위젯 [LockOn] 섹션, MouseAccumulationThreshold 실측용) */
	FAstralTargetSwitchInputDebugSnapshot GetTargetSwitchInputDebugSnapshot() const;
#endif

protected:

	virtual void OnRegister() override;
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

#if WITH_EDITOR
	/** 임계 정합을 데이터에서 — Release ≤ Engage (런타임 보정 대신 편집 시 정규화) */
	virtual void PostEditChangeProperty(FPropertyChangedEvent& PropertyChangedEvent) override;
#endif

	virtual void InitializePlayerInput(UInputComponent* PlayerInputComponent);

	/** 타게팅 컴포넌트 — BeginPlay에서 1회 해석해 캐시 (BP 소유 컴포넌트라 폰 측 주입이 불가) */
	UAstralTargetingComponent* GetTargeting() const;

	bool IsHardLocked() const;

	void Input_AbilityInputTagPressed(FGameplayTag InputTag);
	void Input_AbilityInputTagReleased(FGameplayTag InputTag);

	void Input_Move(const FInputActionValue& InputActionValue);

	/** Look — 락온 밖은 그대로 / 락온 중 Yaw는 타겟 변경 프로세서로, Pitch는 통과 */
	void Input_LookMouse(const FInputActionValue& InputActionValue);
	void Input_LookStick(const FInputActionValue& InputActionValue);

	/** 스틱 Completed (값 0 복귀, 1회) — latch 해제 전용 */
	void Input_LookStickCompleted(const FInputActionValue& InputActionValue);

	/** 락온 토글 — 네이티브 바인딩 (Started 1회). 선정·해제는 TargetingComponent가 소유 */
	void Input_LockOn(const FInputActionValue& InputActionValue);

	/** 타겟 변경 처리 결과 → TargetingComponent::CycleTarget. 미설정이면 아무 일도 안 한다 */
	void ApplyTargetSwitch(const FAstralTargetSwitchResult& Result);

protected:

	/** True when player input bindings have been applied, will never be true for non - players */
	bool bReadyToBindInputs;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Target Switch", Meta = (ShowOnlyInnerProperties))
	FAstralTargetSwitchInputParams TargetSwitchParams;

private:
	
	FAstralTargetSwitchInputProcessor TargetSwitchInput;

	UPROPERTY(Transient)
	TObjectPtr<UAstralTargetingComponent> CachedTargeting;
};
