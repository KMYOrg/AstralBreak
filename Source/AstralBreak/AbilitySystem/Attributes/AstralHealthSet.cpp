#include "AstralHealthSet.h"

#include "GameplayEffectExtension.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "Net/UnrealNetwork.h"


UAstralHealthSet::UAstralHealthSet()
{
    InitHealth(100.f);
    InitMaxHealth(100.f);
    InitIncomingDamageMultiplier(1.f);
}

void UAstralHealthSet::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);

    DOREPLIFETIME_CONDITION_NOTIFY(UAstralHealthSet, Health, COND_None, REPNOTIFY_Always);
    DOREPLIFETIME_CONDITION_NOTIFY(UAstralHealthSet, MaxHealth, COND_None, REPNOTIFY_Always);
    DOREPLIFETIME_CONDITION_NOTIFY(UAstralHealthSet, IncomingDamageMultiplier, COND_None, REPNOTIFY_Always);
}

void UAstralHealthSet::OnRep_Health(const FGameplayAttributeData& OldValue)
{
    GAMEPLAYATTRIBUTE_REPNOTIFY(UAstralHealthSet, Health, OldValue);
}

void UAstralHealthSet::OnRep_MaxHealth(const FGameplayAttributeData& OldValue)
{
    GAMEPLAYATTRIBUTE_REPNOTIFY(UAstralHealthSet, MaxHealth, OldValue);
}

void UAstralHealthSet::OnRep_IncomingDamageMultiplier(const FGameplayAttributeData& OldValue)
{
    GAMEPLAYATTRIBUTE_REPNOTIFY(UAstralHealthSet, IncomingDamageMultiplier, OldValue);
}

void UAstralHealthSet::PreAttributeBaseChange(const FGameplayAttribute& Attribute, float& NewValue) const
{
    ClampAttribute(Attribute, NewValue);
}

void UAstralHealthSet::PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue)
{
    ClampAttribute(Attribute, NewValue);
}

void UAstralHealthSet::PostAttributeChange(const FGameplayAttribute& Attribute, float OldValue, float NewValue)
{
    Super::PostAttributeChange(Attribute, OldValue, NewValue);

    if (Attribute == GetHealthAttribute())
    {
        // 사망 후 회복(부활/힐)되면 out-of-health 게이트 해제
        if (bOutOfHealth && (GetHealth() > 0.f))
        {
            bOutOfHealth = false;
        }
    }
    else if (Attribute == GetMaxHealthAttribute())
    {
        if (GetHealth() > NewValue)
        {
            UAstralAbilitySystemComponent* ASC = GetAstralAbilitySystemComponent();
            if (ASC)
            {
                ASC->ApplyModToAttribute(GetHealthAttribute(), EGameplayModOp::Override, NewValue);
            }
        }
    }
}

void UAstralHealthSet::ClampAttribute(const FGameplayAttribute& Attribute, float& NewValue) const
{
    if (Attribute == GetHealthAttribute())
    {
        NewValue = FMath::Clamp(NewValue, 0.f, GetMaxHealth());
    }
    else if (Attribute == GetMaxHealthAttribute())
    {
        NewValue = FMath::Max(NewValue, 1.f);
    }
    else if (Attribute == GetIncomingDamageMultiplierAttribute())
    {
        NewValue = FMath::Max(NewValue, 0.f);
    }
}

bool UAstralHealthSet::PreGameplayEffectExecute(FGameplayEffectModCallbackData& Data)
{
    if (!Super::PreGameplayEffectExecute(Data))
    {
        return false;
    }

    // 사망 상태에서 추가 데미지 적용 차단 (Damage meta만)
    if (Data.EvaluatedData.Attribute == GetDamageAttribute())
    {
        if (GetHealth() <= 0.f)
        {
            return false;
        }
    }

    return true;
}

void UAstralHealthSet::PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data)
{
    Super::PostGameplayEffectExecute(Data);

    const FGameplayEffectContextHandle& EffectContext = Data.EffectSpec.GetEffectContext();
    AActor* Instigator = EffectContext.GetOriginalInstigator();
    AActor* Causer = EffectContext.GetEffectCauser();

    const float Magnitude  = Data.EvaluatedData.Magnitude;
    const float MinHealth  = 0.f;

    if (Data.EvaluatedData.Attribute == GetDamageAttribute())
    {
        const float LocalDamage = GetDamage();
        SetDamage(0.f);

        if (LocalDamage > 0.f)
        {
            const float OldHealth = GetHealth();
            SetHealth(FMath::Clamp(OldHealth - LocalDamage, MinHealth, GetMaxHealth()));
            OnDamaged.Broadcast(Instigator, Causer, &Data.EffectSpec, LocalDamage, OldHealth, GetHealth());
        }
    }
    else if (Data.EvaluatedData.Attribute == GetHealingAttribute())
    {
        const float LocalHealing = GetHealing();
        SetHealing(0.f);

        if (LocalHealing > 0.f)
        {
            const float OldHealth = GetHealth();
            SetHealth(FMath::Clamp(OldHealth + LocalHealing, MinHealth, GetMaxHealth()));
            OnHealed.Broadcast(Instigator, Causer, &Data.EffectSpec, LocalHealing, OldHealth, GetHealth());
        }
    }
    else if (Data.EvaluatedData.Attribute == GetHealthAttribute())
    {
        // Health Attribute에 직접 GE가 닿은 경우(드물지만)에도 클램프 한 번
        SetHealth(FMath::Clamp(GetHealth(), MinHealth, GetMaxHealth()));
    }

    // Out-of-health 1회 트리거
    if (GetHealth() <= 0.f && !bOutOfHealth)
    {
        OnOutOfHealth.Broadcast(Instigator, Causer, &Data.EffectSpec, Magnitude, GetHealth(), GetHealth());
    }
    
    bOutOfHealth = (GetHealth() <= 0.0f);
}