#include "AstralCharacter.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Effects/AstralSetByCallerGameplayTags.h"
#include "Character/Components/AstralCharacterMovementComponent.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Components/AstralPawnExtensionComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameplayEffect.h"
#include "Player/AstralPlayerState.h"


AAstralCharacter::AAstralCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer.SetDefaultSubobjectClass<UAstralCharacterMovementComponent>(ACharacter::CharacterMovementComponentName))
{
	PrimaryActorTick.bCanEverTick = false;
	PrimaryActorTick.bStartWithTickEnabled = false;

	bReplicates = true;
	SetReplicatingMovement(true);

	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw   = false;
	bUseControllerRotationRoll  = false;

	UCharacterMovementComponent* AstralMoveComp = GetCharacterMovement();
	AstralMoveComp->bOrientRotationToMovement = true;

	PawnExtComponent = CreateDefaultSubobject<UAstralPawnExtensionComponent>(TEXT("PawnExtComponent"));

	HealthComponent = CreateDefaultSubobject<UAstralHealthComponent>(TEXT("HealthComponent"));
}

void AAstralCharacter::PreInitializeComponents()
{
	Super::PreInitializeComponents();
}

void AAstralCharacter::BeginPlay()
{
	Super::BeginPlay();
}

void AAstralCharacter::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	Super::EndPlay(EndPlayReason);
}

void AAstralCharacter::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);

	// 서버 경로: Possess 시점 Init State 시작
	PawnExtComponent->HandleControllerChanged();
}

void AAstralCharacter::UnPossessed()
{
	Super::UnPossessed();
	
	PawnExtComponent->HandleControllerChanged();
}

void AAstralCharacter::OnRep_Controller()
{
	Super::OnRep_Controller();

	PawnExtComponent->HandleControllerChanged();
}

void AAstralCharacter::OnRep_PlayerState()
{
	Super::OnRep_PlayerState();

	PawnExtComponent->HandlePlayerStateReplicated();
}

void AAstralCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	PawnExtComponent->SetupPlayerInputComponent();
}

UAbilitySystemComponent* AAstralCharacter::GetAbilitySystemComponent() const
{
	if (PawnExtComponent == nullptr)
	{
		return nullptr;
	}

	return PawnExtComponent->GetAstralAbilitySystemComponent();
}

AAstralPlayerState* AAstralCharacter::GetAstralPlayerState() const
{
	return CastChecked<AAstralPlayerState>(GetPlayerState(), ECastCheckedType::NullAllowed);
}

UAstralAbilitySystemComponent* AAstralCharacter::GetAstralAbilitySystemComponent() const
{
	return Cast<UAstralAbilitySystemComponent>(GetAbilitySystemComponent());
}

void AAstralCharacter::DamageSelf(float Amount)
{
#if !UE_BUILD_SHIPPING
	if (HasAuthority())
	{
		ServerDamageSelf_Implementation(Amount);
	}
	else
	{
		ServerDamageSelf(Amount);
	}
#endif
}

void AAstralCharacter::ServerDamageSelf_Implementation(float Amount)
{
#if !UE_BUILD_SHIPPING
	UAbilitySystemComponent* ASC = GetAbilitySystemComponent();
	if (!ASC || Amount <= 0.0f)
	{
		return;
	}

	// 디버그 전용이라 콘텐츠 경로 하드코딩 허용 — 정식 데미지 파이프라인(GE_Damage_Base + SetByCaller.Damage)을 그대로 태운다
	static const FSoftClassPath DebugDamageEffectPath(TEXT("/Game/AbilitySystem/Effects/Damage/GE_Damage_Base.GE_Damage_Base_C"));
	UClass* DamageEffectClass = DebugDamageEffectPath.TryLoadClass<UGameplayEffect>();
	if (!DamageEffectClass)
	{
		return;
	}

	FGameplayEffectContextHandle Context = ASC->MakeEffectContext();
	Context.AddInstigator(this, this);

	const FGameplayEffectSpecHandle SpecHandle = ASC->MakeOutgoingSpec(DamageEffectClass, 1.0f, Context);
	if (SpecHandle.IsValid())
	{
		SpecHandle.Data->SetSetByCallerMagnitude(AstralGameplayTags::SetByCaller_Damage, Amount);
		ASC->ApplyGameplayEffectSpecToSelf(*SpecHandle.Data.Get());
	}
#endif
}

