#include "AstralCombatCharacter.h"

#include "AbilitySystem/AstralAbilitySet.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Attributes/AstralCombatSet.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "Character/Components/AstralPawnExtensionComponent.h"
#include "DrawDebugHelpers.h"
#include "Equipment/AstralEquipmentManagerComponent.h"
#include "Net/UnrealNetwork.h"

AAstralCombatCharacter::AAstralCombatCharacter(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	AbilitySystemComponent = CreateDefaultSubobject<UAstralAbilitySystemComponent>(TEXT("AbilitySystemComponent"));
	AbilitySystemComponent->SetIsReplicated(true);
	AbilitySystemComponent->SetReplicationMode(EGameplayEffectReplicationMode::Minimal);

	HealthSet = CreateDefaultSubobject<UAstralHealthSet>(TEXT("HealthSet"));
	CombatSet = CreateDefaultSubobject<UAstralCombatSet>(TEXT("CombatSet"));
}

UAbilitySystemComponent* AAstralCombatCharacter::GetAbilitySystemComponent() const
{
	return AbilitySystemComponent;
}

void AAstralCombatCharacter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AAstralCombatCharacter, TeamId);
}

void AAstralCombatCharacter::PostInitializeComponents()
{
	Super::PostInitializeComponents();

	// 자기 ASC를 아바타 결합 — 전 머신. InitAbilityActorInfo(this, this) + OnAbilitySystemInitialized 브로드캐스트로
	// 베이스가 Health·Movement·Equipment(정책, 서버)를 Hero와 같은 경로로 결합
	check(AbilitySystemComponent);
	PawnExtComponent->InitializeAbilitySystem(AbilitySystemComponent, this);
}

void AAstralCombatCharacter::BeginPlay()
{
	Super::BeginPlay();

	if (HasAuthority())
	{
		for (const UAstralAbilitySet* AbilitySet : AbilitySets)
		{
			if (AbilitySet)
			{
				AbilitySet->GiveToAbilitySystem(AbilitySystemComponent, nullptr, this);
			}
		}

		// 기본 장비 — 회수는 베이스의 OnAbilitySystemUninitialized + 컴포넌트 EndPlay가 보장
		if (EquipmentManagerComponent && !EquipmentManagerComponent->HasAnyEquipment())
		{
			for (const FPrimaryAssetId& WeaponId : DefaultEquipment)
			{
				EquipmentManagerComponent->EquipItemById(WeaponId);
			}
		}
	}
}

void AAstralCombatCharacter::MulticastDrawTelegraphDebug_Implementation(float Duration, float TraceStartOffset, float TraceDistance, float TraceRadius)
{
#if ENABLE_DRAW_DEBUG
	// GA_Enemy_TelegraphAttack의 ApplyDamageSweep와 동일 볼륨 — 발동 시점 기준 1회 표시 (MVP)
	const FVector Forward = GetActorForwardVector();
	const FVector Start   = GetActorLocation() + Forward * TraceStartOffset;
	const FVector End     = Start + Forward * TraceDistance;

	DrawDebugCapsule(GetWorld(), (Start + End) * 0.5f, (TraceDistance * 0.5f) + TraceRadius, TraceRadius, FRotationMatrix::MakeFromZ(Forward).ToQuat(), FColor::Red, false, Duration);
#endif
}

void AAstralCombatCharacter::HandleDeathFinished(AActor* OwningActor)
{
	Super::HandleDeathFinished(OwningActor);

	if (HasAuthority())
	{
		// 복제 액터라 서버 LifeSpan 만료 시 클라에서도 함께 제거됨
		SetLifeSpan(DestroyAfterDeathDelay);
	}
}
