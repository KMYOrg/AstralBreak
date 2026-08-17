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
#include "Character/AstralCharacterDefinition.h"
#include "Character/AstralPawnData.h"
#include "Equipment/AstralEquipmentManagerComponent.h"
#include "GameModes/AstralGameState.h"
#include "GameplayEffect.h"
#include "Player/AstralPlayerState.h"
#include "System/AstralAssetManager.h"
#include "System/AstralGameData.h"
#include "System/AstralPartySubsystem.h"


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
	
	AAstralPlayerState* AstralPS = GetAstralPlayerState();
	if (BoundLoadoutPlayerState.Get() != AstralPS)
	{
		UnbindLoadoutChanged();
		BoundLoadoutPlayerState = AstralPS;

		if (AstralPS)
		{
			LoadoutChangedHandle = AstralPS->OnLoadoutChanged.AddUObject(this, &ThisClass::HandleLoadoutChanged);
		}
	}

	ApplyLoadout(/*bReapplyEquipment=*/false);
}

void AAstralCharacter::ApplyLoadout(bool bReapplyEquipment)
{
	// 순서 계약 — 외형이 항상 먼저 (장비 액터는 GetMesh() 소켓 부착이라 메시 교체 후 장착해야 한다)
	RefreshAppearanceFromLoadout();

	if (HasAuthority())
	{
		RestoreEquipmentFromLoadout(bReapplyEquipment);
	}
}

void AAstralCharacter::HandleLoadoutChanged()
{
	ApplyLoadout(/*bReapplyEquipment=*/true);
}

void AAstralCharacter::UnbindLoadoutChanged()
{
	if (AAstralPlayerState* BoundPS = BoundLoadoutPlayerState.Get(); BoundPS && LoadoutChangedHandle.IsValid())
	{
		BoundPS->OnLoadoutChanged.Remove(LoadoutChangedHandle);
	}
	LoadoutChangedHandle.Reset();
	BoundLoadoutPlayerState.Reset();
}

void AAstralCharacter::RefreshAppearanceFromLoadout()
{
	const AAstralPlayerState* AstralPS = GetAstralPlayerState();
	if (!AstralPS || !AstralPS->GetLoadout().CharacterId.IsValid())
	{
		return;
	}

	const FSoftObjectPath DefinitionPath = UAstralAssetManager::Get().GetPrimaryAssetPath(AstralPS->GetLoadout().CharacterId);
	const UAstralCharacterDefinition* CharacterDef = Cast<UAstralCharacterDefinition>(DefinitionPath.TryLoad());
	if (!CharacterDef)
	{
		UE_LOG(LogAstral, Warning, TEXT("RefreshAppearance: CharacterDefinition 해석 실패 %s"), *AstralPS->GetLoadout().CharacterId.ToString());
		return;
	}

	USkeletalMeshComponent* MeshComp = GetMesh();
	if (!MeshComp || CharacterDef->Mesh.IsNull())
	{
		return;
	}

	// 이미 같은 메시면 스킵 (OnRep·빙의·PS 도착 등 여러 지점에서 호출된다)
	USkeletalMesh* TargetMesh = CharacterDef->Mesh.LoadSynchronous();
	if (TargetMesh && MeshComp->GetSkeletalMeshAsset() != TargetMesh)
	{
		MeshComp->SetSkeletalMesh(TargetMesh);
		if (CharacterDef->AnimInstanceClass)
		{
			MeshComp->SetAnimInstanceClass(CharacterDef->AnimInstanceClass);
		}
	}
}

void AAstralCharacter::RestoreEquipmentFromLoadout(bool bReapply)
{
	if (!HasAuthority() || !EquipmentManagerComponent)
	{
		return;
	}

	// ASC 준비 전이면 장착 금지 — 부여 없는 반쪽 장착이 생기고, 그게 HasAnyEquipment 가드를 오염시켜
	// 이후 정상 경로(OnAbilitySystemInitialized의 SetCombatStyle+장착)까지 막는다 (seamless 도착 직후
	// 로드아웃 재발신이 InitState 완료보다 빠른 케이스). 초기화 완료 시 이 함수가 다시 불린다
	if (!GetAbilitySystemComponent())
	{
		return;
	}

	// None(관전 등)이면 3단 해석 비용 자체를 아낀다. VisualOnly(로비)는 통과 — 홀스터 표시용 장착
	// (부여 차단은 AddEntry의 정책 게이트 = 로비 전투 불가의 실차단 지점)
	if (EquipmentManagerComponent->GetEquipmentPolicy() == EAstralEquipmentPolicy::None)
	{
		return;
	}

	const UAstralPawnData* PawnData = PawnExtComponent ? PawnExtComponent->GetPawnData<UAstralPawnData>() : nullptr;
	if (!PawnData)
	{
		return;
	}

	if (!bReapply && EquipmentManagerComponent->HasAnyEquipment())
	{
		return;
	}

	// 3단 소스 해석 — PlayerState 우선. 캐시를 앞에 두면 "PS 갱신 → 재적용 → 아직 안 갱신된 캐시 조회"로
	// 레이드 중 로드아웃 변경이 이전 값으로 되돌아간다 (호출 순서 의존 버그). 캐시의 존재 이유는
	// travel 직후 PS.Loadout이 빈 창을 메우는 폴백이므로 2단이 맞다.
	const TArray<FPrimaryAssetId>* EquipmentIds = nullptr;
	LastLoadoutSource = EAstralLoadoutSource::None;

	const AAstralPlayerState* AstralPS = GetAstralPlayerState();
	if (AstralPS)
	{
		if (AstralPS->GetLoadout().Equipment.Num() > 0)
		{
			EquipmentIds = &AstralPS->GetLoadout().Equipment;
			LastLoadoutSource = EAstralLoadoutSource::PlayerState;
		}
		if (!EquipmentIds)
		{
			if (const UAstralPartySubsystem* Party = GetGameInstance() ? GetGameInstance()->GetSubsystem<UAstralPartySubsystem>() : nullptr)
			{
				if (const FAstralPlayerLoadout* Cached = Party->FindLoadout(AstralPS->GetUniqueId()); Cached && Cached->Equipment.Num() > 0)
				{
					EquipmentIds = &Cached->Equipment;
					LastLoadoutSource = EAstralLoadoutSource::PartyCache;
				}
			}
		}
	}
	if (!EquipmentIds)
	{
		if (EquipmentManagerComponent->GetEquipmentPolicy() != EAstralEquipmentPolicy::Full)
		{
			// 소스 없음 — 재적용 경로면 기존 표시를 걷어낸다 (로드아웃이 비워진 경우)
			if (bReapply)
			{
				EquipmentManagerComponent->UnequipAll();
			}
			return;
		}
		EquipmentIds = &PawnData->DefaultEquipment;
		LastLoadoutSource = EAstralLoadoutSource::PawnDataFallback;
	}

	if (bReapply)
	{
		// 동일 장착이면 통째로 no-op — 정상 도착 경로(ASC 초기화 장착 → 클라 재발신 도착)에서 매번
		// 무기 액터 Destroy/Respawn이 클라에 복제되고 진행 중 GA가 취소되는 것을 막는다.
		// LastLoadoutSource 기록 뒤라 디버그 위젯은 실제 소스를 보여준다
		if (EquipmentManagerComponent->MatchesEquippedItems(*EquipmentIds))
		{
			return;
		}
		EquipmentManagerComponent->UnequipAll();
	}

	for (const FPrimaryAssetId& ItemId : *EquipmentIds)
	{
		EquipmentManagerComponent->EquipItemById(ItemId);
	}

	// 스타일↔장비 정합 — 현재 스타일 유지 시도, 현 스타일 장비가 없으면(총만 든 로드아웃 등) 장비 있는 쪽으로 폴백
	if (UAstralAbilitySystemComponent* AstralASC = GetAstralAbilitySystemComponent())
	{
		UAstralCombatStatics::ApplyCombatStyle(this, AstralASC->GetCombatStyle());
	}
}

void AAstralCharacter::OnAbilitySystemUninitialized()
{
	UnbindLoadoutChanged();

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
	UnbindLoadoutChanged();

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

