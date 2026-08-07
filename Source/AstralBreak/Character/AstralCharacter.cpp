#include "AstralCharacter.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
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
#include "Equipment/AstralEquipmentManagerComponent.h"
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
}

void AAstralCharacter::OnAbilitySystemInitialized()
{
	UAstralAbilitySystemComponent* AstralASC = GetAstralAbilitySystemComponent();
	check(AstralASC);

	HealthComponent->InitializeWithAbilitySystem(AstralASC);

	// 기본 장비 장착 (서버) — 장착 소스는 PawnData 플레이스홀더, M1에서 로드아웃 페이로드 복원으로 교체.
	// 재초기화 경로에서 중복 장착 방지 (리스폰/재빙의 시 어빌리티 누적 차단)
	if (HasAuthority() && EquipmentManagerComponent && !EquipmentManagerComponent->HasAnyEquipment())
	{
		if (const UAstralPawnData* PawnData = PawnExtComponent->GetPawnData<UAstralPawnData>())
		{
			// 초기 스타일은 장착 루프보다 먼저 — 스폰 시점의 손/홀스터 소켓 결정이 이 상태를 읽는다.
			// 빈 태그 = 스타일 시스템 미사용 폰
			if (PawnData->InitialCombatStyle.IsValid())
			{
				SetCombatStyle(PawnData->InitialCombatStyle);
			}

			for (const FPrimaryAssetId& WeaponId : PawnData->DefaultEquipment)
			{
				EquipmentManagerComponent->EquipItemById(WeaponId);
			}
		}
	}
}

void AAstralCharacter::SetCombatStyle(FGameplayTag NewStyle)
{
	if (!HasAuthority())
	{
		return;
	}

	UAbilitySystemComponent* ASC = GetAbilitySystemComponent();
	if (!ASC)
	{
		return;
	}

	// 부모 자체(State.CombatStyle)는 상태로 쓰지 않는다 — 자식만 유효
	if (!NewStyle.MatchesTag(AstralGameplayTags::State_CombatStyle) || NewStyle == AstralGameplayTags::State_CombatStyle)
	{
		UE_LOG(LogAstral, Warning, TEXT("SetCombatStyle: %s 는 State.CombatStyle 자식 태그가 아님 — 무시"), *NewStyle.ToString());
		return;
	}

	// 서버 전용 쓰기 + TagAndCountToAll — ReplicatedLooseTags 경유로 전 커넥션·후참가 복제.
	// 보유 중인 스타일 태그를 전부 내리고 새 태그만 올린다 — 스타일 집합을 코드가 모르므로(히어로별 데이터 정의)
	// 부모 태그 질의로 일괄 해제. 리스폰 시 ASC(PlayerState)에 잔존한 이전 폰의 태그도 이 경로로 자동 정정.
	FGameplayTagContainer OwnedTags;
	ASC->GetOwnedGameplayTags(OwnedTags);
	for (auto TagIt = OwnedTags.CreateConstIterator(); TagIt; ++TagIt)
	{
		const FGameplayTag& OwnedTag = *TagIt;
		if (OwnedTag != NewStyle && OwnedTag != AstralGameplayTags::State_CombatStyle && OwnedTag.MatchesTag(AstralGameplayTags::State_CombatStyle))
		{
			ASC->SetLooseGameplayTagCount(OwnedTag, 0, EGameplayTagReplicationState::TagAndCountToAll);
		}
	}
	ASC->SetLooseGameplayTagCount(NewStyle, 1, EGameplayTagReplicationState::TagAndCountToAll);

	if (EquipmentManagerComponent)
	{
		EquipmentManagerComponent->RefreshEquipmentActiveState();
	}
}

void AAstralCharacter::OnAbilitySystemUninitialized()
{
	// 장비 회수 — ASC(PlayerState)가 폰보다 오래 살므로, ASC 분리 전에 부여분을 걷지 않으면 어빌리티가 누적된다
	if (EquipmentManagerComponent)
	{
		EquipmentManagerComponent->UnequipAll();
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

