#include "AstralCharacter_Hero.h"

#include "Camera/CameraComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Components/AstralHeroComponent.h"
#include "Character/Components/AstralLoadoutComponent.h"
#include "Character/Hero/Components/AstralHeroCameraComponent.h"
#include "Character/Hero/Components/AstralHeroMovementComponent.h"
#include "Character/Hero/Components/AstralTargetingComponent.h"
#include "Player/AstralPlayerState.h"

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

	LoadoutComponent = CreateDefaultSubobject<UAstralLoadoutComponent>(TEXT("LoadoutComponent"));
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

AAstralPlayerState* AAstralCharacter_Hero::GetAstralPlayerState() const
{
	return CastChecked<AAstralPlayerState>(GetPlayerState(), ECastCheckedType::NullAllowed);
}

void AAstralCharacter_Hero::OnAbilitySystemInitialized()
{
	// 베이스: Health → Movement → Equipment 정책 주입 → 초기 스타일 시드
	Super::OnAbilitySystemInitialized();
	
	if (LoadoutComponent)
	{
		LoadoutComponent->HandleAbilitySystemInitialized();
	}
}

void AAstralCharacter_Hero::OnAbilitySystemUninitialized()
{
	if (LoadoutComponent)
	{
		LoadoutComponent->HandleAbilitySystemUninitialized();
	}

	Super::OnAbilitySystemUninitialized();
}
