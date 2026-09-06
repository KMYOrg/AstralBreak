#include "AstralHeroComponent.h"

#include "AstralGameplayTags.h"
#include "Components/GameFrameworkComponentDelegates.h"
#include "Logging/MessageLog.h"
#include "AstralLogChannels.h"
#include "EnhancedInputSubsystems.h"
#include "Player/AstralPlayerController.h"
#include "Player/AstralPlayerState.h"
#include "Player/AstralLocalPlayer.h"
#include "Character/Components/AstralPawnExtensionComponent.h"
#include "Character/AstralPawnData.h"
#include "Character/AstralCharacter.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "Input/AstralInputConfig.h"
#include "Input/AstralInputComponent.h"
#include "Components/GameFrameworkComponentManager.h"
#include "UserSettings/EnhancedInputUserSettings.h"
#include "InputMappingContext.h"
#include "Character/Hero/AstralPawnData_Hero.h"
#include "Character/Hero/Components/AstralTargetingComponent.h"
#include "Input/AstralInputGameplayTags.h"
#include "Misc/UObjectToken.h"

namespace AstralHero
{
	static const float LookYawRate = 300.0f;
	static const float LookPitchRate = 165.0f;
}

const FName UAstralHeroComponent::NAME_BindInputsNow("BindInputsNow");
const FName UAstralHeroComponent::NAME_ActorFeatureName("Hero");

UAstralHeroComponent::UAstralHeroComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	bReadyToBindInputs = false;
	
	PrimaryComponentTick.bCanEverTick = false;
}

void UAstralHeroComponent::OnRegister()
{
	Super::OnRegister();

	if (!GetPawn<APawn>())
	{
		UE_LOG(LogAstral, Error, TEXT("[UAstralHeroComponent::OnRegister] This component has been added to a blueprint whose base class is not a Pawn. To use this component, it MUST be placed on a Pawn Blueprint."));

#if WITH_EDITOR
		if (GIsEditor)
		{
			static const FText Message = NSLOCTEXT("UAstralHeroComponent", "NotOnPawnError", "has been added to a blueprint whose base class is not a Pawn. To use this component, it MUST be placed on a Pawn Blueprint. This will cause a crash if you PIE!");
			static const FName HeroMessageLogName = TEXT("UAstralHeroComponent");
			
			FMessageLog(HeroMessageLogName).Error()
				->AddToken(FUObjectToken::Create(this, FText::FromString(GetNameSafe(this))))
				->AddToken(FTextToken::Create(Message));
				
			FMessageLog(HeroMessageLogName).Open();
		}
#endif
	}
	else
	{
		// Register with the init state system early, this will only work if this is a game world
		RegisterInitStateFeature();
	}
}

bool UAstralHeroComponent::CanChangeInitState(UGameFrameworkComponentManager* Manager, FGameplayTag CurrentState, FGameplayTag DesiredState) const
{
	check(Manager);

	APawn* Pawn = GetPawn<APawn>();

	if (!CurrentState.IsValid() && DesiredState == AstralGameplayTags::InitState_Spawned)
	{
		if (Pawn)
		{
			return true;
		}
	}
	else if (CurrentState == AstralGameplayTags::InitState_Spawned && DesiredState == AstralGameplayTags::InitState_DataAvailable)
	{
		if (!GetPlayerState<AAstralPlayerState>())
		{
			return false;
		}

		// If we're authority or autonomous, we need to wait for a controller with registered ownership of the player state.
		if (Pawn->GetLocalRole() != ROLE_SimulatedProxy)
		{
			AController* Controller = GetController<AController>();

			const bool bHasControllerPairedWithPS = (Controller != nullptr) && \
				(Controller->PlayerState != nullptr) && \
				(Controller->PlayerState->GetOwner() == Controller);

			if (!bHasControllerPairedWithPS)
			{
				return false;
			}
		}

		const bool bIsLocallyControlled = Pawn->IsLocallyControlled();

		if (bIsLocallyControlled)
		{
			AAstralPlayerController* AstralPC = GetController<AAstralPlayerController>();

			// The input component and local player is required when locally controlled.
			if (!Pawn->InputComponent || !AstralPC || !AstralPC->GetLocalPlayer())
			{
				return false;
			}
		}

		return true;
	}
	else if (CurrentState == AstralGameplayTags::InitState_DataAvailable && DesiredState == AstralGameplayTags::InitState_DataInitialized)
	{
		AAstralPlayerState* AstralPS = GetPlayerState<AAstralPlayerState>();

		return AstralPS && Manager->HasFeatureReachedInitState(Pawn, UAstralPawnExtensionComponent::NAME_ActorFeatureName, AstralGameplayTags::InitState_DataInitialized);
	}
	else if (CurrentState == AstralGameplayTags::InitState_DataInitialized && DesiredState == AstralGameplayTags::InitState_GameplayReady)
	{
		// TODO add ability initialization checks?
		return true;
	}

	return false;
}

void UAstralHeroComponent::HandleChangeInitState(UGameFrameworkComponentManager* Manager, FGameplayTag CurrentState, FGameplayTag DesiredState)
{
	if (CurrentState == AstralGameplayTags::InitState_DataAvailable && DesiredState == AstralGameplayTags::InitState_DataInitialized)
	{
		APawn* Pawn = GetPawn<APawn>();
		AAstralPlayerState* AstralPS = GetPlayerState<AAstralPlayerState>();
		if (!ensure(Pawn && AstralPS))
		{
			return;
		}

		const UAstralPawnData* PawnData = nullptr;

		if (UAstralPawnExtensionComponent* PawnExtComp = UAstralPawnExtensionComponent::FindPawnExtensionComponent(Pawn))
		{
			PawnData = PawnExtComp->GetPawnData<UAstralPawnData>();
			PawnExtComp->InitializeAbilitySystem(AstralPS->GetAstralAbilitySystemComponent(), AstralPS);
		}

		if (AAstralPlayerController* AstralPC = GetController<AAstralPlayerController>())
		{
			if (Pawn->InputComponent != nullptr)
			{
				InitializePlayerInput(Pawn->InputComponent);
			}
		}
	}
}

void UAstralHeroComponent::OnActorInitStateChanged(const FActorInitStateChangedParams& Params)
{
	if (Params.FeatureName == UAstralPawnExtensionComponent::NAME_ActorFeatureName)
	{
		if (Params.FeatureState == AstralGameplayTags::InitState_DataInitialized)
		{
			CheckDefaultInitialization();
		}
	}
}

void UAstralHeroComponent::CheckDefaultInitialization()
{
	static const TArray<FGameplayTag> StateChain = { AstralGameplayTags::InitState_Spawned, AstralGameplayTags::InitState_DataAvailable, AstralGameplayTags::InitState_DataInitialized, AstralGameplayTags::InitState_GameplayReady };

	ContinueInitStateChain(StateChain);
}

void UAstralHeroComponent::BeginPlay()
{
	Super::BeginPlay();

	BindOnActorInitStateChanged(UAstralPawnExtensionComponent::NAME_ActorFeatureName, FGameplayTag(), false);

	ensure(TryToChangeInitState(AstralGameplayTags::InitState_Spawned));
	CheckDefaultInitialization();
}

void UAstralHeroComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	UnregisterInitStateFeature();

	Super::EndPlay(EndPlayReason);
}

bool UAstralHeroComponent::IsHardLocked() const
{
	const UAstralTargetingComponent* Targeting = UAstralTargetingComponent::FindTargetingComponent(GetPawn<APawn>());
	return Targeting && Targeting->GetMode() == EAstralTargetingMode::HardLocked && Targeting->GetEffectiveTarget().IsSet();
}

void UAstralHeroComponent::InitializePlayerInput(UInputComponent* PlayerInputComponent)
{
	check(PlayerInputComponent);

	const APawn* Pawn = GetPawn<APawn>();
	if (!Pawn)
	{
		return;
	}

	const APlayerController* PC = GetController<APlayerController>();
	check(PC);

	const UAstralLocalPlayer* LP = Cast<UAstralLocalPlayer>(PC->GetLocalPlayer());
	check(LP);

	UEnhancedInputLocalPlayerSubsystem* Subsystem = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>();
	check(Subsystem);

	Subsystem->ClearAllMappings();

	if (const UAstralPawnExtensionComponent* PawnExtComp = UAstralPawnExtensionComponent::FindPawnExtensionComponent(Pawn))
	{
		if (const UAstralPawnData_Hero* PawnData = PawnExtComp->GetPawnData<UAstralPawnData_Hero>())
		{
			if (const UAstralInputConfig* InputConfig = PawnData->InputConfig)
			{
				for (const FInputMappingContextAndPriority& Mapping : InputConfig->InputMappingContexts)
				{
					if (UInputMappingContext* IMC = Mapping.InputMapping.LoadSynchronous())
					{
						if (Mapping.bRegisterWithSettings)
						{
							if (UEnhancedInputUserSettings* Settings = Subsystem->GetUserSettings())
							{
								Settings->RegisterInputMappingContext(IMC);
							}
							
							FModifyContextOptions Options = {};
							Options.bIgnoreAllPressedKeysUntilRelease = false;
							// Actually add the config to the local player							
							Subsystem->AddMappingContext(IMC, Mapping.Priority, Options);
						}
					}
				}
				
				UAstralInputComponent* AstralIC = Cast<UAstralInputComponent>(PlayerInputComponent);
				if (ensureMsgf(AstralIC, TEXT("Unexpected Input Component class! The Gameplay Abilities will not be bound to their inputs. Change the input component to UAstralInputComponent or a subclass of it.")))
				{
					AstralIC->AddInputMappings(InputConfig, Subsystem);

					TArray<uint32> BindHandles;
					AstralIC->BindAbilityActions(InputConfig, this, &ThisClass::Input_AbilityInputTagPressed, &ThisClass::Input_AbilityInputTagReleased, /*out*/ BindHandles);

					AstralIC->BindNativeAction(InputConfig, AstralGameplayTags::InputTag_Move, ETriggerEvent::Triggered, this, &ThisClass::Input_Move, /*bLogIfNotFound=*/ false);
					AstralIC->BindNativeAction(InputConfig, AstralGameplayTags::InputTag_Look_Mouse, ETriggerEvent::Triggered, this, &ThisClass::Input_LookMouse, /*bLogIfNotFound=*/ false);
					AstralIC->BindNativeAction(InputConfig, AstralGameplayTags::InputTag_Look_Stick, ETriggerEvent::Triggered, this, &ThisClass::Input_LookStick, /*bLogIfNotFound=*/ false);
					AstralIC->BindNativeAction(InputConfig, AstralGameplayTags::InputTag_Look_Stick, ETriggerEvent::Completed, this, &ThisClass::Input_LookStickCompleted, /*bLogIfNotFound=*/ false);
					AstralIC->BindNativeAction(InputConfig, AstralGameplayTags::InputTag_LockOn, ETriggerEvent::Started, this, &ThisClass::Input_LockOn, /*bLogIfNotFound=*/ false);
				}
			}
		}
	}

	if (ensure(!bReadyToBindInputs))
	{
		bReadyToBindInputs = true;
	}
 
	UGameFrameworkComponentManager::SendGameFrameworkComponentExtensionEvent(const_cast<APlayerController*>(PC), NAME_BindInputsNow);
	UGameFrameworkComponentManager::SendGameFrameworkComponentExtensionEvent(const_cast<APawn*>(Pawn), NAME_BindInputsNow);
}

void UAstralHeroComponent::AddAdditionalInputConfig(const UAstralInputConfig* InputConfig)
{
	TArray<uint32> BindHandles;

	const APawn* Pawn = GetPawn<APawn>();
	if (!Pawn)
	{
		return;
	}
	
	const APlayerController* PC = GetController<APlayerController>();
	check(PC);

	const ULocalPlayer* LP = PC->GetLocalPlayer();
	check(LP);

	UEnhancedInputLocalPlayerSubsystem* Subsystem = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>();
	check(Subsystem);

	if (const UAstralPawnExtensionComponent* PawnExtComp = UAstralPawnExtensionComponent::FindPawnExtensionComponent(Pawn))
	{
		UAstralInputComponent* AstralIC = Pawn->FindComponentByClass<UAstralInputComponent>();
		if (ensureMsgf(AstralIC, TEXT("Unexpected Input Component class! The Gameplay Abilities will not be bound to their inputs. Change the input component to UAstralInputComponent or a subclass of it.")))
		{
			AstralIC->BindAbilityActions(InputConfig, this, &ThisClass::Input_AbilityInputTagPressed, &ThisClass::Input_AbilityInputTagReleased, /*out*/ BindHandles);
		}
	}
}

void UAstralHeroComponent::RemoveAdditionalInputConfig(const UAstralInputConfig* InputConfig)
{
	//@TODO: Implement me!
}

bool UAstralHeroComponent::IsReadyToBindInputs() const
{
	return bReadyToBindInputs;
}

void UAstralHeroComponent::Input_AbilityInputTagPressed(FGameplayTag InputTag)
{
	if (const APawn* Pawn = GetPawn<APawn>())
	{
		if (const UAstralPawnExtensionComponent* PawnExtComp = UAstralPawnExtensionComponent::FindPawnExtensionComponent(Pawn))
		{
			if (UAstralAbilitySystemComponent* AstralASC = PawnExtComp->GetAstralAbilitySystemComponent())
			{
				AstralASC->AbilityInputTagPressed(InputTag);
			}
		}	
	}
}

void UAstralHeroComponent::Input_AbilityInputTagReleased(FGameplayTag InputTag)
{
	const APawn* Pawn = GetPawn<APawn>();
	if (!Pawn)
	{
		return;
	}

	if (const UAstralPawnExtensionComponent* PawnExtComp = UAstralPawnExtensionComponent::FindPawnExtensionComponent(Pawn))
	{
		if (UAstralAbilitySystemComponent* AstralASC = PawnExtComp->GetAstralAbilitySystemComponent())
		{
			AstralASC->AbilityInputTagReleased(InputTag);
		}
	}
}

void UAstralHeroComponent::Input_Move(const FInputActionValue& InputActionValue)
{
	APawn* Pawn = GetPawn<APawn>();
	AController* Controller = Pawn ? Pawn->GetController() : nullptr;
	
	if (Controller)
	{
		const FVector2D Value = InputActionValue.Get<FVector2D>();
		const FRotator MovementRotation(0.0f, Controller->GetControlRotation().Yaw, 0.0f);

		if (Value.X != 0.0f)
		{
			const FVector MovementDirection = MovementRotation.RotateVector(FVector::RightVector);
			Pawn->AddMovementInput(MovementDirection, Value.X);
		}

		if (Value.Y != 0.0f)
		{
			const FVector MovementDirection = MovementRotation.RotateVector(FVector::ForwardVector);
			Pawn->AddMovementInput(MovementDirection, Value.Y);
		}
	}
}

void UAstralHeroComponent::Input_LookMouse(const FInputActionValue& InputActionValue)
{
	APawn* Pawn = GetPawn<APawn>();

	if (!Pawn)
	{
		return;
	}
	
	const FVector2D Value = InputActionValue.Get<FVector2D>();

	// 락온 게이트 — Yaw는 카메라 추적이 소유. 락온 중 Yaw 입력은 타겟 전환(누적·감쇠·쿨다운)으로 라우팅, Pitch는 통과.
	// 락온 밖에서는 전환 입력 상태를 방어적으로 비운다 (세션 경계 리셋은 Input_LockOn이 확실히)
	const bool bHardLocked = IsHardLocked();
	if (!bHardLocked)
	{
		ResetTargetSwitchInputState();
	}

	if (Value.X != 0.0f)
	{
		if (bHardLocked)
		{
			HandleMouseTargetSwitch(Value.X);
		}
		else
		{
			Pawn->AddControllerYawInput(Value.X);
		}
	}

	if (Value.Y != 0.0f)
	{
		// TODO: Settings 시스템 도입 시 +Value.Y로 적용
		double AimInversionValue = -Value.Y;
		Pawn->AddControllerPitchInput(AimInversionValue);
	}
}

void UAstralHeroComponent::Input_LookStick(const FInputActionValue& InputActionValue)
{
	APawn* Pawn = GetPawn<APawn>();

	if (!Pawn)
	{
		return;
	}
	
	const FVector2D Value = InputActionValue.Get<FVector2D>();

	const UWorld* World = GetWorld();
	check(World);

	// 락온 게이트 — 마우스와 동일 (Yaw는 전환 latch로, Pitch 통과). X가 0이어도 latch 전이표(해제 임계)에 넣는다
	const bool bHardLocked = IsHardLocked();
	if (!bHardLocked)
	{
		ResetTargetSwitchInputState();
	}

	if (bHardLocked)
	{
		HandleStickTargetSwitch(Value.X);
	}
	else if (Value.X != 0.0f)
	{
		Pawn->AddControllerYawInput(Value.X * AstralHero::LookYawRate * World->GetDeltaSeconds());
	}

	if (Value.Y != 0.0f)
	{
		// TODO: Settings 시스템 도입 시 +Value.Y로 적용
		Pawn->AddControllerPitchInput(-Value.Y * AstralHero::LookPitchRate * World->GetDeltaSeconds());
	}
}

void UAstralHeroComponent::Input_LookStickCompleted(const FInputActionValue& InputActionValue)
{
	// 스틱을 완전히 놓음 — 어느 latch 상태에서든 Neutral.
	CycleInputState = EAstralTargetCycleInput::Neutral;
}

void UAstralHeroComponent::Input_LockOn(const FInputActionValue& InputActionValue)
{
	// 세션 경계 — 이전 락온의 latch·누적·쿨다운이 다음 락온의 첫 전환을 먹지 않게 (타이밍이 아니라 상태 전이에 건다)
	ResetTargetSwitchInputState();

	// 입력은 전이 요청만 — 후보 선정·상태는 TargetingComponent가 소유
	if (UAstralTargetingComponent* Targeting = UAstralTargetingComponent::FindTargetingComponent(GetPawn<APawn>()))
	{
		Targeting->ToggleLockOn();
	}
}

void UAstralHeroComponent::HandleStickTargetSwitch(float AxisX)
{
	const float Engage = TargetSwitchParams.StickEngageThreshold;
	const float Release = FMath::Min(TargetSwitchParams.StickReleaseThreshold, Engage);

	switch (CycleInputState)
	{
	case EAstralTargetCycleInput::Neutral:
		if (AxisX >= Engage)
		{
			CycleInputState = EAstralTargetCycleInput::LatchedRight;
			RequestCycleTarget(+1.f);
		}
		else if (AxisX <= -Engage)
		{
			CycleInputState = EAstralTargetCycleInput::LatchedLeft;
			RequestCycleTarget(-1.f);
		}
		break;

	case EAstralTargetCycleInput::LatchedRight:
		if (FMath::Abs(AxisX) <= Release)
		{
			CycleInputState = EAstralTargetCycleInput::Neutral;
		}
		else if (AxisX <= -Engage)
		{
			CycleInputState = EAstralTargetCycleInput::LatchedLeft;
			RequestCycleTarget(-1.f);
		}
		break;

	case EAstralTargetCycleInput::LatchedLeft:
		if (FMath::Abs(AxisX) <= Release)
		{
			CycleInputState = EAstralTargetCycleInput::Neutral;
		}
		else if (AxisX >= Engage)
		{
			CycleInputState = EAstralTargetCycleInput::LatchedRight;
			RequestCycleTarget(+1.f);
		}
		break;
	}
}

void UAstralHeroComponent::HandleMouseTargetSwitch(float DeltaX)
{
	const UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	const double Now = World->GetTimeSeconds();
	const FAstralTargetSwitchInputParams& P = TargetSwitchParams;

	// 입력 공백 — 마지막 입력 이후 경과.
	const double Gap = (LastMouseSwitchInputTime < 0.0) ? TNumericLimits<double>::Max() : (Now - LastMouseSwitchInputTime);
	const bool bPaused = (Gap >= P.MouseRearmPause);

	// 재전환 — 전환 후에는 마우스가 RearmPause 이상 멈춘 뒤의 첫 입력에서만 다시
	if (!bMouseSwitchArmed && bPaused)
	{
		bMouseSwitchArmed = true;
	}

	// 누적 창 — 기준은 첫 입력. 공백 뒤 첫 입력이거나 창이 만료됐으면 새 창.
	// (마지막 입력 기준 감쇠는 끊김 없는 느린 드래그를 못 걸러 결국 임계에 닿는다)
	const bool bWindowExpired = (MouseSwitchWindowStartTime < 0.0) || bPaused || ((Now - MouseSwitchWindowStartTime) > P.MouseAccumulationWindow);
	if (bWindowExpired)
	{
		MouseSwitchAccumulation = 0.f;
		MouseSwitchWindowStartTime = Now;
	}

	LastMouseSwitchInputTime = Now;

	// 입력 폐기 (누적하지 않는다)
	if (!bMouseSwitchArmed)
	{
		MouseSwitchAccumulation = 0.f;
		return;
	}

	MouseSwitchAccumulation += DeltaX;

	// 임계 — 0 이하는 비활성 (누적·위젯 표시는 유지, 실측으로 값을 정한 뒤 켜진다)
	if (P.MouseAccumulationThreshold > 0.f && FMath::Abs(MouseSwitchAccumulation) >= P.MouseAccumulationThreshold)
	{
		RequestCycleTarget(FMath::Sign(MouseSwitchAccumulation));
		MouseSwitchAccumulation = 0.f;
		MouseSwitchWindowStartTime = -1.0;
		bMouseSwitchArmed = false;   // 멈출 때까지 잠근다
	}
}

void UAstralHeroComponent::ResetTargetSwitchInputState()
{
	CycleInputState = EAstralTargetCycleInput::Neutral;
	MouseSwitchAccumulation = 0.f;
	MouseSwitchWindowStartTime = -1.0;
	LastMouseSwitchInputTime = -1.0;
	bMouseSwitchArmed = true;
}

void UAstralHeroComponent::RequestCycleTarget(float Direction)
{
	if (UAstralTargetingComponent* Targeting = UAstralTargetingComponent::FindTargetingComponent(GetPawn<APawn>()))
	{
		Targeting->CycleTarget(Direction);
	}
}

float UAstralHeroComponent::GetMouseSwitchAccumulationAge() const
{
	const UWorld* World = GetWorld();
	if (!World || LastMouseSwitchInputTime < 0.0)
	{
		return -1.f;
	}
	return static_cast<float>(World->GetTimeSeconds() - LastMouseSwitchInputTime);
}

float UAstralHeroComponent::GetMouseSwitchWindowAge() const
{
	const UWorld* World = GetWorld();
	if (!World || MouseSwitchWindowStartTime < 0.0)
	{
		return -1.f;
	}
	return static_cast<float>(World->GetTimeSeconds() - MouseSwitchWindowStartTime);
}

