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
#include "Character/Hero/AstralCharacter_Hero.h"
#include "Character/Hero/AstralPawnData_Hero.h"
#include "Character/Hero/Components/AstralTargetingComponent.h"
#include "GameFramework/SpringArmComponent.h"
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

	// 락온 카메라 추적 — 로컬 제어 폰에서만 실질 동작 (틱 초입에서 걸러낸다)
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
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

void UAstralHeroComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	// 카메라는 로컬 관심사 — 원격 폰의 서버 인스턴스·시뮬 프록시는 아무것도 하지 않는다
	const APawn* Pawn = GetPawn<APawn>();
	if (!Pawn || !Pawn->IsLocallyControlled())
	{
		return;
	}

	UpdateLockOnCamera(DeltaTime);
}

bool UAstralHeroComponent::IsHardLocked() const
{
	const UAstralTargetingComponent* Targeting = UAstralTargetingComponent::FindTargetingComponent(GetPawn<APawn>());
	return Targeting && Targeting->GetMode() == EAstralTargetingMode::HardLocked && Targeting->GetEffectiveTarget().IsSet();
}

void UAstralHeroComponent::UpdateLockOnCamera(float DeltaTime)
{
	AAstralCharacter_Hero* Hero = GetPawn<AAstralCharacter_Hero>();
	APlayerController* PC = GetController<APlayerController>();
	if (!Hero || !PC)
	{
		return;
	}

	const bool bLocked = IsHardLocked();

	// 카메라 랙 전환 — 락온 추적 보간 위에 SpringArm 랙이 겹치면 흐물거린다. 해제 시 원래값 복귀
	if (USpringArmComponent* Boom = Hero->GetCameraBoom())
	{
		if (bLocked && !bLockCameraLagApplied)
		{
			DefaultCameraLagSpeed = Boom->CameraLagSpeed;
			Boom->CameraLagSpeed = LockCameraLagSpeed;
			bLockCameraLagApplied = true;
		}
		else if (!bLocked && bLockCameraLagApplied)
		{
			Boom->CameraLagSpeed = DefaultCameraLagSpeed;
			bLockCameraLagApplied = false;
		}
	}

	if (!bLocked)
	{
		return;
	}

	// 목표 = 카메라(뷰포인트)에서 조준점(캡슐 중심) 방향. 발밑을 보면 카메라가 내려앉으므로 조준점을 쓴다
	const FAstralTargetHandle& Target = Hero->GetTargetingComponent()->GetEffectiveTarget();

	FVector ViewLocation;
	FRotator ViewRotation;
	PC->GetPlayerViewPoint(ViewLocation, ViewRotation);

	const FVector ToTarget = Target.GetAimLocation() - ViewLocation;
	if (ToTarget.IsNearlyZero())
	{
		return;
	}

	const FRotator Desired = ToTarget.Rotation();
	// ⚠️ 정규화 필수 — 카메라 매니저가 클램프한 컨트롤 Pitch는 0~360으로 저장된다 (아래 20° = 340).
	// 정규화 없이 -90~90인 목표와 선형 보간하면 340 → -5 사이를 거꾸로 돌아 카메라가 뒤집힌다
	const FRotator Current = PC->GetControlRotation().GetNormalized();
	FRotator New = Current;

	// Yaw — 항상 보조 (최단 경로 보간)
	New.Yaw = FMath::RInterpTo(Current, Desired, DeltaTime, LockCameraInterpSpeed).Yaw;

	// Pitch — 부분 자유. 임계 안이면 플레이어 입력 그대로, 밖이면 타겟이 임계 안으로 들어오는 경계까지만 보간
	const float PitchDelta = FMath::FindDeltaAngleDegrees(Current.Pitch, Desired.Pitch);
	if (FMath::Abs(PitchDelta) > PitchAssistThreshold)
	{
		const float BoundaryPitch = Desired.Pitch - FMath::Sign(PitchDelta) * PitchAssistThreshold;
		New.Pitch = FMath::Clamp(FMath::FInterpTo(Current.Pitch, BoundaryPitch, DeltaTime, LockCameraInterpSpeed), -89.0f, 89.0f);
	}

	New.Roll = 0.0f;
	PC->SetControlRotation(New);
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

	// 락온 게이트 — Yaw는 카메라 추적이 소유 (입력은 버린다, 3단계에서 타겟 전환으로 라우팅). Pitch는 통과
	if (Value.X != 0.0f && !IsHardLocked())
	{
		Pawn->AddControllerYawInput(Value.X);
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

	// 락온 게이트 — 마우스와 동일 (Yaw 차단, Pitch 통과)
	if (Value.X != 0.0f && !IsHardLocked())
	{
		Pawn->AddControllerYawInput(Value.X * AstralHero::LookYawRate * World->GetDeltaSeconds());
	}

	if (Value.Y != 0.0f)
	{
		// TODO: Settings 시스템 도입 시 +Value.Y로 적용
		Pawn->AddControllerPitchInput(-Value.Y * AstralHero::LookPitchRate * World->GetDeltaSeconds());
	}
}

void UAstralHeroComponent::Input_LockOn(const FInputActionValue& InputActionValue)
{
	// 입력은 전이 요청만 — 후보 선정·상태는 TargetingComponent가 소유
	if (UAstralTargetingComponent* Targeting = UAstralTargetingComponent::FindTargetingComponent(GetPawn<APawn>()))
	{
		Targeting->ToggleLockOn();
	}
}

