#include "AstralHealthComponent.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AstralLogChannels.h"
#include "Net/UnrealNetwork.h"

UAstralHealthComponent::UAstralHealthComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	PrimaryComponentTick.bStartWithTickEnabled = false;
	PrimaryComponentTick.bCanEverTick = false;

	SetIsReplicatedByDefault(true);

	DeathState = EAstralDeathState::NotDead;
	AbilitySystemComponent = nullptr;
	HealthSet = nullptr;
}

void UAstralHealthComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(UAstralHealthComponent, DeathState);
}

void UAstralHealthComponent::OnUnregister()
{
	UninitializeFromAbilitySystem();

	Super::OnUnregister();
}

void UAstralHealthComponent::InitializeWithAbilitySystem(UAstralAbilitySystemComponent* InASC)
{
	AActor* Owner = GetOwner();
	check(Owner);

	if (AbilitySystemComponent == InASC)
	{
		return;
	}

	if (AbilitySystemComponent)
	{
		UninitializeFromAbilitySystem();
	}

	AbilitySystemComponent = InASC;
	if (!AbilitySystemComponent)
	{
		UE_LOG(LogAstral, Error, TEXT("AstralHealthComponent: Cannot initialize health component for owner [%s] with NULL ability system."), *GetNameSafe(Owner));
		return;
	}

	HealthSet = AbilitySystemComponent->GetSet<UAstralHealthSet>();
	if (!HealthSet)
	{
		UE_LOG(LogAstral, Error, TEXT("AstralHealthComponent: Cannot initialize health component for owner [%s] with NULL health set on the ability system."), *GetNameSafe(Owner));
		return;
	}

	// HP 변경은 attribute 델리게이트로 — 복제 수신 시에도 발화하므로 클라 UI가 그대로 구독 가능
	HealthChangedDelegateHandle = AbilitySystemComponent->GetGameplayAttributeValueChangeDelegate(UAstralHealthSet::GetHealthAttribute()).AddUObject(this, &ThisClass::HandleHealthAttributeChanged);

	// 사망 진입은 서버 전용 브로드캐스트 (PostGameplayEffectExecute) — 클라는 DeathState 복제로 동기화
	HealthSet->OnOutOfHealth.AddUObject(this, &ThisClass::HandleOutOfHealth);
}

void UAstralHealthComponent::UninitializeFromAbilitySystem()
{
	if (HealthSet)
	{
		HealthSet->OnOutOfHealth.RemoveAll(this);
	}

	if (AbilitySystemComponent)
	{
		if (HealthChangedDelegateHandle.IsValid())
		{
			AbilitySystemComponent->GetGameplayAttributeValueChangeDelegate(UAstralHealthSet::GetHealthAttribute()).Remove(HealthChangedDelegateHandle);
		}

		AbilitySystemComponent->SetLooseGameplayTagCount(AstralGameplayTags::State_Death_Dying, 0);
		AbilitySystemComponent->SetLooseGameplayTagCount(AstralGameplayTags::State_Death_Dead, 0);
	}

	HealthChangedDelegateHandle.Reset();
	HealthSet = nullptr;
	AbilitySystemComponent = nullptr;
}

float UAstralHealthComponent::GetHealth() const
{
	return (HealthSet ? HealthSet->GetHealth() : 0.0f);
}

float UAstralHealthComponent::GetMaxHealth() const
{
	return (HealthSet ? HealthSet->GetMaxHealth() : 0.0f);
}

float UAstralHealthComponent::GetHealthNormalized() const
{
	const float MaxHealth = GetMaxHealth();
	return (MaxHealth > 0.0f ? (GetHealth() / MaxHealth) : 0.0f);
}

void UAstralHealthComponent::HandleHealthAttributeChanged(const FOnAttributeChangeData& Data)
{
	OnHealthChanged.Broadcast(this, Data.OldValue, Data.NewValue);
}

void UAstralHealthComponent::HandleOutOfHealth(AActor* DamageInstigator, AActor* DamageCauser, const FGameplayEffectSpec* DamageEffectSpec, float DamageMagnitude, float OldValue, float NewValue)
{
	AActor* Owner = GetOwner();
	if (Owner && Owner->HasAuthority())
	{
		StartDeath();
	}
}

void UAstralHealthComponent::StartDeath()
{
	if (DeathState != EAstralDeathState::NotDead)
	{
		return;
	}

	DeathState = EAstralDeathState::DeathStarted;

	AActor* Owner = GetOwner();
	check(Owner);

	if (AbilitySystemComponent)
	{
		AbilitySystemComponent->SetLooseGameplayTagCount(AstralGameplayTags::State_Death_Dying, 1);

		// 진행 중 어빌리티 정리는 서버 권위 — 클라 예측분은 복제로 종료됨
		if (Owner->HasAuthority())
		{
			AbilitySystemComponent->CancelAbilities();
		}
	}

	OnDeathStarted.Broadcast(Owner);

	Owner->ForceNetUpdate();
}

void UAstralHealthComponent::FinishDeath()
{
	if (DeathState != EAstralDeathState::DeathStarted)
	{
		return;
	}

	DeathState = EAstralDeathState::DeathFinished;

	AActor* Owner = GetOwner();
	check(Owner);

	if (AbilitySystemComponent)
	{
		AbilitySystemComponent->SetLooseGameplayTagCount(AstralGameplayTags::State_Death_Dying, 0);
		AbilitySystemComponent->SetLooseGameplayTagCount(AstralGameplayTags::State_Death_Dead, 1);
	}

	OnDeathFinished.Broadcast(Owner);

	Owner->ForceNetUpdate();
}

void UAstralHealthComponent::OnRep_DeathState(EAstralDeathState OldDeathState)
{
	const EAstralDeathState NewDeathState = DeathState;

	// StartDeath/FinishDeath가 전이를 수행하도록 일단 되돌린 뒤 리플레이 (Lyra 패턴)
	DeathState = OldDeathState;

	if (OldDeathState > NewDeathState)
	{
		// 서버가 죽음을 되돌리는 경우는 없음 — 역행은 무시
		UE_LOG(LogAstral, Warning, TEXT("AstralHealthComponent: Predicted past server death state [%d] -> [%d] for owner [%s]."), (uint8)OldDeathState, (uint8)NewDeathState, *GetNameSafe(GetOwner()));
		DeathState = NewDeathState;
		return;
	}

	if (OldDeathState == EAstralDeathState::NotDead)
	{
		if (NewDeathState == EAstralDeathState::DeathStarted)
		{
			StartDeath();
		}
		else if (NewDeathState == EAstralDeathState::DeathFinished)
		{
			StartDeath();
			FinishDeath();
		}
	}
	else if (OldDeathState == EAstralDeathState::DeathStarted)
	{
		if (NewDeathState == EAstralDeathState::DeathFinished)
		{
			FinishDeath();
		}
	}

	ensureMsgf((DeathState == NewDeathState), TEXT("AstralHealthComponent: Death state replication failed to replay [%d] -> [%d] for owner [%s]."), (uint8)OldDeathState, (uint8)NewDeathState, *GetNameSafe(GetOwner()));
}
