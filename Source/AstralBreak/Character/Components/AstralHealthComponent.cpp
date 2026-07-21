#include "AstralHealthComponent.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AstralLogChannels.h"
#include "GameplayEffectTypes.h"
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

	// 아바타 재사용/재연결 시 이전 사망 상태 잔존 방지 (정리 목적 — 브로드캐스트 없이)
	DeathState = EAstralDeathState::NotDead;
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
#if WITH_SERVER_CODE
	AActor* Owner = GetOwner();
	if (!Owner || !Owner->HasAuthority() || !AbilitySystemComponent)
	{
		return;
	}

	// GameplayEvent.Death 발송 → GA_Death 트리거. StartDeath는 GA_Death가 호출한다
	FGameplayEventData Payload;
	Payload.EventTag = AstralGameplayTags::GameplayEvent_Death;
	Payload.Instigator = DamageInstigator;
	Payload.Target = AbilitySystemComponent->GetAvatarActor();
	Payload.EventMagnitude = DamageMagnitude;
	if (DamageEffectSpec)
	{
		Payload.OptionalObject = DamageEffectSpec->Def;
		Payload.ContextHandle = DamageEffectSpec->GetEffectContext();
		Payload.InstigatorTags = *DamageEffectSpec->CapturedSourceTags.GetAggregatedTags();
		Payload.TargetTags = *DamageEffectSpec->CapturedTargetTags.GetAggregatedTags();
	}

	FScopedPredictionWindow NewScopedWindow(AbilitySystemComponent, true);
	const int32 NumTriggeredAbilities = AbilitySystemComponent->HandleGameplayEvent(Payload.EventTag, &Payload);

	// GA_Death 미부여 폰은 죽음이 시작되지 않음 — 데이터 설정 누락을 즉시 드러낸다
	if (NumTriggeredAbilities <= 0)
	{
		UE_LOG(LogAstral, Warning, TEXT("AstralHealthComponent: [%s] hit 0 HP but no ability handled GameplayEvent.Death — grant GA_Death via an AbilitySet."), *GetNameSafe(Owner));
	}
#endif
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

	// 어빌리티 취소는 GA_Death의 책임 (SurvivesDeath 예외 + 자기 자신 제외를 GA만 알 수 있음)
	if (AbilitySystemComponent)
	{
		AbilitySystemComponent->SetLooseGameplayTagCount(AstralGameplayTags::State_Death_Dying, 1);
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

void UAstralHealthComponent::ResetDeathState()
{
	if (DeathState == EAstralDeathState::NotDead)
	{
		return;
	}

	DeathState = EAstralDeathState::NotDead;

	AActor* Owner = GetOwner();
	check(Owner);

	if (AbilitySystemComponent)
	{
		AbilitySystemComponent->SetLooseGameplayTagCount(AstralGameplayTags::State_Death_Dying, 0);
		AbilitySystemComponent->SetLooseGameplayTagCount(AstralGameplayTags::State_Death_Dead, 0);
	}

	OnDeathReset.Broadcast(Owner);

	Owner->ForceNetUpdate();
}

void UAstralHealthComponent::OnRep_DeathState(EAstralDeathState OldDeathState)
{
	const EAstralDeathState NewDeathState = DeathState;

	// 전이 함수들이 직접 전이를 수행하도록 일단 되돌린 뒤 리플레이 (Lyra 패턴)
	DeathState = OldDeathState;

	if (OldDeathState > NewDeathState)
	{
		if (NewDeathState == EAstralDeathState::NotDead)
		{
			// 부활 (ReviveSelf / 추후 리스폰) — 클라도 태그 정리 + OnDeathReset 리플레이
			ResetDeathState();
			return;
		}

		// NotDead 외의 역행(DeathFinished→DeathStarted 등)은 정상 경로가 아님 — 값만 수용
		UE_LOG(LogAstral, Warning, TEXT("AstralHealthComponent: Unexpected death state regression [%d] -> [%d] for owner [%s]."), (uint8)OldDeathState, (uint8)NewDeathState, *GetNameSafe(GetOwner()));
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
