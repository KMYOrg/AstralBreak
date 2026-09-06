// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Components/GameFrameworkInitStateInterface.h"
#include "Components/PawnComponent.h"
#include "Input/AstralInputConfig.h"

#include "AstralHeroComponent.generated.h"

struct FInputActionValue;

UENUM()
enum class EAstralTargetCycleInput : uint8
{
	Neutral,
	LatchedLeft,
	LatchedRight
};

/** 타겟 전환 입력 튜닝값 — 스틱(정규화 축)과 마우스(delta 누적)는 단위가 달라 임계도 따로다 */
USTRUCT(BlueprintType)
struct FAstralTargetSwitchInputParams
{
	GENERATED_BODY()

	/** 스틱 — latch 걸림 (|X| 이상). 반대쪽 직접 전이(LatchedRight 중 X ≤ −Engage)도 이 값 */
	UPROPERTY(EditDefaultsOnly, Category = "Target Switch", Meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float StickEngageThreshold = 0.6f;

	/** 스틱 — latch 해제 (|X| 이하). Completed 전에 반대로 꺾는 경로를 덮는다. Engage보다 작아야 한다 */
	UPROPERTY(EditDefaultsOnly, Category = "Target Switch", Meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float StickReleaseThreshold = 0.3f;

	/**
	 * 마우스 — 부호 있는 누적 delta 임계. 0 이하 = 마우스 전환 비활성 (누적·위젯 표시는 계속된다).
	 * 감도·DPI 종속이라 추정값을 적지 않는다 — 첫 플레이에서 위젯의 mouseAccum을 보고 실측 확정
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Target Switch", Meta = (ClampMin = "0.0"))
	float MouseAccumulationThreshold = 0.f;

	/**
	 * 마우스 — 누적 창 (초). 창의 기준은 첫 입력: 첫 입력부터 이 시간 안에 임계를 넘겨야 전환.
	 * (마지막 입력 기준 감쇠는 끊김 없는 느린 드래그를 못 걸러 결국 임계에 닿는다 — 플릭은 수십 ms 안에 쌓이므로 창이 짧아야 구분된다)
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Target Switch", Meta = (ClampMin = "0.0"))
	float MouseAccumulationWindow = 0.15f;

	/**
	 * 마우스 — 전환 후 재전환에 필요한 입력 공백 (초).
	 * 전환 직후엔 마우스가 이 시간 이상 멈출 때까지 입력을 버린다
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Target Switch", Meta = (ClampMin = "0.0"))
	float MouseRearmPause = 0.15f;
};

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

	// 디버그 관측 — 타겟 전환 입력 기계 (위젯 [LockOn] 섹션, MouseAccumulationThreshold 실측용)
	EAstralTargetCycleInput GetTargetCycleInputState() const { return CycleInputState; }
	float GetMouseSwitchAccumulation() const { return MouseSwitchAccumulation; }
	/** 현재 누적 창의 첫 입력 후 경과 (초). 창 없음 = −1 */
	float GetMouseSwitchWindowAge() const;
	/** 마지막 마우스 전환 입력 후 경과 (초). 입력 없음 = −1 */
	float GetMouseSwitchAccumulationAge() const;
	/** false = 전환 직후, MouseRearmPause 이상의 입력 공백을 기다리는 중 (그동안 입력 폐기) */
	bool IsMouseSwitchArmed() const { return bMouseSwitchArmed; }
	const FAstralTargetSwitchInputParams& GetTargetSwitchParams() const { return TargetSwitchParams; }

protected:

	virtual void OnRegister() override;
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

	virtual void InitializePlayerInput(UInputComponent* PlayerInputComponent);

	bool IsHardLocked() const;

	void Input_AbilityInputTagPressed(FGameplayTag InputTag);
	void Input_AbilityInputTagReleased(FGameplayTag InputTag);

	void Input_Move(const FInputActionValue& InputActionValue);

	void Input_LookMouse(const FInputActionValue& InputActionValue);
	void Input_LookStick(const FInputActionValue& InputActionValue);
	
	void Input_LookStickCompleted(const FInputActionValue& InputActionValue);

	/** 락온 토글 — 네이티브 바인딩 (Started 1회). 선정·해제는 TargetingComponent가 소유 */
	void Input_LockOn(const FInputActionValue& InputActionValue);

	/** 스틱 전환 — latch 전이표 (Neutral / LatchedLeft / LatchedRight, 반대쪽 직접 전이 인정) */
	void HandleStickTargetSwitch(float AxisX);

	/** 마우스 전환 — 첫 입력 기준 누적 창 + 전환 후 멈춤 재무장. 임계 0 이하면 누적만 하고 전환하지 않는다 */
	void HandleMouseTargetSwitch(float DeltaX);

	/** latch · 마우스 누적 창 · 재무장 상태 전부 초기화 — 락온 세션 경계(Input_LockOn)와 락온 밖 Look 입력에서 */
	void ResetTargetSwitchInputState();

	/** 전환 요청 — TargetingComponent::CycleTarget (후보 없으면 no-op) */
	void RequestCycleTarget(float Direction);

protected:

	/** True when player input bindings have been applied, will never be true for non - players */
	bool bReadyToBindInputs;

	UPROPERTY(EditDefaultsOnly, Category = "Astral|Target Switch", Meta = (ShowOnlyInnerProperties))
	FAstralTargetSwitchInputParams TargetSwitchParams;

private:
	EAstralTargetCycleInput CycleInputState = EAstralTargetCycleInput::Neutral;

	/** 마우스 부호 있는 누적 delta (우 +) — 현재 창 안의 합 */
	float MouseSwitchAccumulation = 0.f;

	/** 현재 누적 창의 첫 입력 시각 (월드 초). 음수 = 창 없음 */
	double MouseSwitchWindowStartTime = -1.0;

	/** 마지막 마우스 전환 입력 시각 (월드 초). 음수 = 없음. 입력 공백(재무장·새 창) 판정의 기준 */
	double LastMouseSwitchInputTime = -1.0;

	/** false = 전환 직후. MouseRearmPause 이상 멈춘 뒤의 첫 입력에서 true로 */
	bool bMouseSwitchArmed = true;
};
