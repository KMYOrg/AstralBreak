#include "AstralHeroResourceSet.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "GameplayEffectExtension.h"
#include "Net/UnrealNetwork.h"

UAstralHeroResourceSet::UAstralHeroResourceSet()
    : bUltFilled(false)
{
    InitStamina(100.f);
    InitMaxStamina(100.f);
    InitStaminaCostMultiplier(1.f);
    InitStaminaRecoveryMultiplier(1.f);

    InitUltGauge(0.f);
    InitMaxUltGauge(100.f);
    InitUltGainMultiplier(1.f);
    InitBreakContributionMultiplier(1.f);
}

void UAstralHeroResourceSet::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);

    DOREPLIFETIME_CONDITION_NOTIFY(UAstralHeroResourceSet, Stamina,                    COND_None, REPNOTIFY_Always);
    DOREPLIFETIME_CONDITION_NOTIFY(UAstralHeroResourceSet, MaxStamina,                 COND_None, REPNOTIFY_Always);
    DOREPLIFETIME_CONDITION_NOTIFY(UAstralHeroResourceSet, StaminaCostMultiplier,      COND_None, REPNOTIFY_Always);
    DOREPLIFETIME_CONDITION_NOTIFY(UAstralHeroResourceSet, StaminaRecoveryMultiplier,  COND_None, REPNOTIFY_Always);

    DOREPLIFETIME_CONDITION_NOTIFY(UAstralHeroResourceSet, UltGauge,                   COND_None, REPNOTIFY_Always);
    DOREPLIFETIME_CONDITION_NOTIFY(UAstralHeroResourceSet, MaxUltGauge,                COND_None, REPNOTIFY_Always);
    DOREPLIFETIME_CONDITION_NOTIFY(UAstralHeroResourceSet, UltGainMultiplier,          COND_None, REPNOTIFY_Always);
    DOREPLIFETIME_CONDITION_NOTIFY(UAstralHeroResourceSet, BreakContributionMultiplier,COND_None, REPNOTIFY_Always);
}

#define DEFINE_ONREP(Name) \
    void UAstralHeroResourceSet::OnRep_##Name(const FGameplayAttributeData& OldValue) \
    { \
        GAMEPLAYATTRIBUTE_REPNOTIFY(UAstralHeroResourceSet, Name, OldValue); \
    }

DEFINE_ONREP(Stamina)
DEFINE_ONREP(MaxStamina)
DEFINE_ONREP(StaminaCostMultiplier)
DEFINE_ONREP(StaminaRecoveryMultiplier)
DEFINE_ONREP(UltGauge)
DEFINE_ONREP(MaxUltGauge)
DEFINE_ONREP(UltGainMultiplier)
DEFINE_ONREP(BreakContributionMultiplier)
// TODO: 

#undef DEFINE_ONREP

void UAstralHeroResourceSet::PreAttributeBaseChange(const FGameplayAttribute& Attribute, float& NewValue) const
{
    ClampAttribute(Attribute, NewValue);
}

void UAstralHeroResourceSet::PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue)
{
    ClampAttribute(Attribute, NewValue);
}

void UAstralHeroResourceSet::PostAttributeChange(const FGameplayAttribute& Attribute, float OldValue, float NewValue)
{
    Super::PostAttributeChange(Attribute, OldValue, NewValue);

    UAstralAbilitySystemComponent* ASC = GetAstralAbilitySystemComponent();

    // Max* 가 줄어들었을 때 현재값 클램프
    if (Attribute == GetMaxStaminaAttribute())
    {
        if (GetStamina() > NewValue && ASC)
        {
            ASC->ApplyModToAttribute(GetStaminaAttribute(), EGameplayModOp::Override, NewValue);
        }
    }
    else if (Attribute == GetMaxUltGaugeAttribute())
    {
        if (GetUltGauge() > NewValue && ASC)
        {
            ASC->ApplyModToAttribute(GetUltGaugeAttribute(), EGameplayModOp::Override, NewValue);
        }
    }
    
    // OnUltFilled — 가득 찬 순간 1회. 소비하여 Max 미만이 되면 게이트 리셋
    if (Attribute == GetUltGaugeAttribute())
    {
        const float Max = GetMaxUltGauge();
        if (!bUltFilled && NewValue >= Max && Max > 0.f)
        {
            OnUltFilled.Broadcast(nullptr, nullptr, nullptr, NewValue, OldValue, NewValue);
            bUltFilled = true;
        }
        else if (bUltFilled && NewValue < Max)
        {
            bUltFilled = false;
        }
    }
}

void UAstralHeroResourceSet::PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data)
{
    Super::PostGameplayEffectExecute(Data);

    if (Data.EvaluatedData.Attribute == GetUltGainAttribute())
    {
        const float LocalUltGain = GetUltGain();
        SetUltGain(0.f);

        // 사망 상태에선 수급 차단
        if (Data.Target.HasMatchingGameplayTag(AstralGameplayTags::State_Death))
        {
            return;
        }

        if (LocalUltGain > 0.f)
        {
            // Multiplier 레이어는 여기 한 곳에서만 곱한다 (M7 룬이 UltGainMultiplier만 건드리면 되는 구조)
            const float NewUltGauge = GetUltGauge() + (LocalUltGain * GetUltGainMultiplier());
            SetUltGauge(FMath::Clamp(NewUltGauge, 0.f, GetMaxUltGauge()));
            // OnUltFilled 1회 게이트는 PostAttributeChange에서 발화
        }
    }
}

void UAstralHeroResourceSet::ClampAttribute(const FGameplayAttribute& Attribute, float& NewValue) const
{
    if (Attribute == GetStaminaAttribute())
    {
        NewValue = FMath::Clamp(NewValue, 0.f, GetMaxStamina());
    }
    else if (Attribute == GetMaxStaminaAttribute())
    {
        NewValue = FMath::Max(NewValue, 1.f);
    }
    else if (Attribute == GetUltGaugeAttribute())
    {
        NewValue = FMath::Clamp(NewValue, 0.f, GetMaxUltGauge());
    }
    else if (Attribute == GetMaxUltGaugeAttribute())
    {
        NewValue = FMath::Max(NewValue, 1.f);
    }
    else if (Attribute == GetStaminaCostMultiplierAttribute()
          || Attribute == GetStaminaRecoveryMultiplierAttribute()
          || Attribute == GetUltGainMultiplierAttribute()
          || Attribute == GetBreakContributionMultiplierAttribute())
    {
        NewValue = FMath::Max(NewValue, 0.f);
    }
}