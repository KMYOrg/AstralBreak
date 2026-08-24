#include "AstralCharacter.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Effects/AstralSetByCallerGameplayTags.h"
#include "Character/Components/AstralCharacterMovementComponent.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Components/AstralPawnExtensionComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "AstralLogChannels.h"
#include "Character/AstralPawnData.h"
#include "Character/Components/AstralLoadoutComponent.h"
#include "Equipment/AstralEquipmentManagerComponent.h"
#include "GameModes/AstralGameState.h"
#include "GameplayEffect.h"
#include "Player/AstralPlayerState.h"
#include "System/AstralAssetManager.h"
#include "System/AstralGameData.h"


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

	// 비렌더 메시(서버에서 화면 밖 폰)에서도 애님 틱 유지 — 기본값이면 NotifyState Begin/End가 틱마다 재발화하고
	// 히트/콤보 노티파이의 서버 측 타이밍이 깨진다
	// TODO: 최적화 고민 필요
	GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPose;

	PawnExtComponent = CreateDefaultSubobject<UAstralPawnExtensionComponent>(TEXT("PawnExtComponent"));
	PawnExtComponent->OnAbilitySystemInitialized_RegisterAndCall(FSimpleMulticastDelegate::FDelegate::CreateUObject(this, &ThisClass::OnAbilitySystemInitialized));
	PawnExtComponent->OnAbilitySystemUninitialized_Register(FSimpleMulticastDelegate::FDelegate::CreateUObject(this, &ThisClass::OnAbilitySystemUninitialized));

	HealthComponent = CreateDefaultSubobject<UAstralHealthComponent>(TEXT("HealthComponent"));

	EquipmentManagerComponent = CreateDefaultSubobject<UAstralEquipmentManagerComponent>(TEXT("EquipmentManagerComponent"));

	LoadoutComponent = CreateDefaultSubobject<UAstralLoadoutComponent>(TEXT("LoadoutComponent"));
}

void AAstralCharacter::OnAbilitySystemInitialized()
{
	UAstralAbilitySystemComponent* AstralASC = GetAstralAbilitySystemComponent();
	check(AstralASC);

	HealthComponent->InitializeWithAbilitySystem(AstralASC);

	// 이동 컴포넌트 ASC 결합 — 스프린트 승인 게이트(State.Movement.Sprinting 캐시)
	// 오너 클라도 예측 경로에서 서버와 같은 게이트를 써야 한다
	if (UAstralCharacterMovementComponent* AstralMoveComp = Cast<UAstralCharacterMovementComponent>(GetCharacterMovement()))
	{
		AstralMoveComp->InitializeWithAbilitySystem(AstralASC);
	}

	// 장비 컴포넌트 ASC 결합(스타일 태그 구독)
	// InitGameState가 폰 스폰보다 먼저
	if (HasAuthority() && EquipmentManagerComponent)
	{
		EAstralEquipmentPolicy Policy = EAstralEquipmentPolicy::Full;
		if (const AAstralGameState* AstralGS = GetWorld() ? GetWorld()->GetGameState<AAstralGameState>() : nullptr)
		{
			Policy = AstralGS->GetEquipmentPolicy();
		}
		EquipmentManagerComponent->InitializeWithAbilitySystem(AstralASC, Policy);
	}

	// 초기 스타일 시드 (서버, 초기화 전용 — 재적용 경로에서 실행 금지) — 장착보다 먼저
	// 빈 태그 = 스타일 시스템 미사용 폰 (ApplyCombatStyle이 무효 해석 no-op으로 흡수)
	if (HasAuthority() && EquipmentManagerComponent && !EquipmentManagerComponent->HasAnyEquipment())
	{
		if (const UAstralPawnData* PawnData = PawnExtComponent->GetPawnData<UAstralPawnData>())
		{
			UAstralCombatStatics::ApplyCombatStyle(this, PawnData->InitialCombatStyle);
		}
	}
	
	// 로드아웃 초기화 — PS 구독 + 초기 1회 적용
	LoadoutComponent->HandleAbilitySystemInitialized();
}

void AAstralCharacter::OnAbilitySystemUninitialized()
{
	LoadoutComponent->HandleAbilitySystemUninitialized();

	// 이동 컴포넌트 태그 구독 해제 — ASC가 폰보다 오래 살므로 (MC의 OnUnregister 안전망과 중복, 멱등)
	if (UAstralCharacterMovementComponent* AstralMoveComp = Cast<UAstralCharacterMovementComponent>(GetCharacterMovement()))
	{
		AstralMoveComp->UninitializeFromAbilitySystem();
	}

	// 장비 회수 — ASC(PlayerState)가 폰보다 오래 살므로, ASC 분리 전에 부여분을 걷지 않으면 어빌리티가 누적된다
	if (EquipmentManagerComponent)
	{
		EquipmentManagerComponent->UnequipAll();
		EquipmentManagerComponent->UninitializeFromAbilitySystem();
	}

	HealthComponent->UninitializeFromAbilitySystem();
}

void AAstralCharacter::PreInitializeComponents()
{
	Super::PreInitializeComponents();
}

void AAstralCharacter::PostInitializeComponents()
{
	Super::PostInitializeComponents();

	// HealthComponent 델리게이트는 컴포넌트 수명(=액터 수명) — ASC Init/Uninit 주기와 무관하게 1회 바인딩 (더미와 동일 패턴)
	HealthComponent->OnDeathStarted.AddDynamic(this, &ThisClass::HandleDeathStarted);
	HealthComponent->OnDeathReset.AddDynamic(this, &ThisClass::HandleDeathReset);
	// OnDeathFinished: 현재는 dead 유지 — TODO: M6 리스폰/관전
}

void AAstralCharacter::HandleDeathStarted(AActor* OwningActor)
{
	// 게임플레이 필수 반응만 — 몽타주/래그돌/디졸브 연출은 BP(OnDeathStarted)
	if (UCapsuleComponent* Capsule = GetCapsuleComponent())
	{
		Capsule->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}

	if (UCharacterMovementComponent* MoveComp = GetCharacterMovement())
	{
		MoveComp->StopMovementImmediately();
		MoveComp->DisableMovement();
	}
}

void AAstralCharacter::HandleDeathReset(AActor* OwningActor)
{
	if (UCapsuleComponent* Capsule = GetCapsuleComponent())
	{
		Capsule->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	}

	if (UCharacterMovementComponent* MoveComp = GetCharacterMovement())
	{
		MoveComp->SetMovementMode(MOVE_Walking);
	}
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

	// 정식 데미지 파이프라인(GameData의 Damage GE + SetByCaller.Damage)을 그대로 태운다
	const TSubclassOf<UGameplayEffect> DamageEffectClass = UAstralGameData::Get().DamageGameplayEffect_SetByCaller.LoadSynchronous();
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

void AAstralCharacter::EquipWeapon(const FString& WeaponIdString)
{
#if !UE_BUILD_SHIPPING
	FPrimaryAssetId WeaponId = FPrimaryAssetId::FromString(WeaponIdString);
	if (!WeaponId.IsValid())
	{
		// 타입 생략 축약형 — 무기 타입 후보를 순서대로 시도 (스캔 데이터는 클라에도 있음)
		static const FName WeaponTypes[] = { FName(TEXT("AstralWeaponDefinition")), FName(TEXT("AstralRangedWeaponDefinition")) };
		for (const FName& WeaponType : WeaponTypes)
		{
			const FPrimaryAssetId Candidate(WeaponType, FName(*WeaponIdString));
			if (UAstralAssetManager::Get().GetPrimaryAssetPath(Candidate).IsValid())
			{
				WeaponId = Candidate;
				break;
			}
		}
	}

	if (HasAuthority())
	{
		ServerEquipWeapon_Implementation(WeaponId);
	}
	else
	{
		ServerEquipWeapon(WeaponId);
	}
#endif
}

void AAstralCharacter::ServerEquipWeapon_Implementation(FPrimaryAssetId WeaponId)
{
#if !UE_BUILD_SHIPPING
	if (EquipmentManagerComponent)
	{
		// 교체 시맨틱 — 전체 해제 후 장착 (무기 변형 비교 테스트용)
		EquipmentManagerComponent->UnequipAll();
		EquipmentManagerComponent->EquipItemById(WeaponId);

		// 반대 스타일 무기로 교체한 경우 스타일 정합 — 현재 스타일 유지 시도, 무효면 폴백
		if (UAstralAbilitySystemComponent* AstralASC = GetAstralAbilitySystemComponent())
		{
			UAstralCombatStatics::ApplyCombatStyle(this, AstralASC->GetCombatStyle());
		}
	}
#endif
}

void AAstralCharacter::ReviveSelf()
{
#if !UE_BUILD_SHIPPING
	if (HasAuthority())
	{
		ServerReviveSelf_Implementation();
	}
	else
	{
		ServerReviveSelf();
	}
#endif
}

void AAstralCharacter::ServerReviveSelf_Implementation()
{
#if !UE_BUILD_SHIPPING
	UAbilitySystemComponent* ASC = GetAbilitySystemComponent();
	if (!ASC)
	{
		return;
	}
	
	const float MaxHealth = ASC->GetNumericAttribute(UAstralHealthSet::GetMaxHealthAttribute());
	ASC->ApplyModToAttribute(UAstralHealthSet::GetHealthAttribute(), EGameplayModOp::Override, MaxHealth);

	// 사망 상태 해제 → OnDeathReset → HandleDeathReset(콜리전/이동 복구). 클라는 DeathState 역행 OnRep이 리플레이
	HealthComponent->ResetDeathState();
#endif
}

