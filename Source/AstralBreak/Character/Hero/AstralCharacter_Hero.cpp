#include "AstralCharacter_Hero.h"

#include "Camera/CameraComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Components/AstralHeroComponent.h"
#include "Character/Hero/Components/AstralHeroCameraComponent.h"
#include "Character/Hero/Components/AstralHeroMovementComponent.h"
#include "Character/Hero/Components/AstralTargetingComponent.h"

AAstralCharacter_Hero::AAstralCharacter_Hero(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer.SetDefaultSubobjectClass<UAstralHeroMovementComponent>(ACharacter::CharacterMovementComponentName))
{
	// SpringArm
	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	CameraBoom->SetupAttachment(RootComponent);
	CameraBoom->TargetArmLength = 400.0f;
	CameraBoom->SocketOffset = FVector(0.0f, 40.0f, 60.0f);
	CameraBoom->bUsePawnControlRotation = true; // 마우스가 카메라 제어
	CameraBoom->bEnableCameraLag = true;
	CameraBoom->CameraLagSpeed = 10.0f;
	CameraBoom->bDoCollisionTest = true;

	// FollowCamera
	FollowCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FollowCamera"));
	FollowCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
	FollowCamera->bUsePawnControlRotation = false; // SpringArm이 회전 제어, 카메라는 팔 끝 고정

	TargetingComponent = CreateDefaultSubobject<UAstralTargetingComponent>(TEXT("TargetingComponent"));
	HeroCameraComponent = CreateDefaultSubobject<UAstralHeroCameraComponent>(TEXT("HeroCameraComponent"));
}

void AAstralCharacter_Hero::PostInitializeComponents()
{
	Super::PostInitializeComponents();

	if (HeroCameraComponent)
	{
		HeroCameraComponent->InitializeCamera(CameraBoom, FollowCamera, TargetingComponent);
	}
}
