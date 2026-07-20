#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Attributes/AstralAttributeSet.h"
#include "AbilitySystemComponent.h"
#include "AstralHeroResourceSet.generated.h"

/**
 * 
 */
UCLASS()
class ASTRALBREAK_API UAstralHeroResourceSet : public UAstralAttributeSet
{
	GENERATED_BODY()

public:
    UAstralHeroResourceSet();

    ATTRIBUTE_ACCESSORS(UAstralHeroResourceSet, Stamina);
    ATTRIBUTE_ACCESSORS(UAstralHeroResourceSet, MaxStamina);
    ATTRIBUTE_ACCESSORS(UAstralHeroResourceSet, StaminaCostMultiplier);
    ATTRIBUTE_ACCESSORS(UAstralHeroResourceSet, StaminaRecoveryMultiplier);

    ATTRIBUTE_ACCESSORS(UAstralHeroResourceSet, UltGauge);
    ATTRIBUTE_ACCESSORS(UAstralHeroResourceSet, MaxUltGauge);
    ATTRIBUTE_ACCESSORS(UAstralHeroResourceSet, UltGainMultiplier);
    ATTRIBUTE_ACCESSORS(UAstralHeroResourceSet, BreakContributionMultiplier);
    ATTRIBUTE_ACCESSORS(UAstralHeroResourceSet, UltGain);

    mutable FAstralAttributeEvent OnUltFilled;

protected:
    
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    
    UFUNCTION() void OnRep_Stamina(const FGameplayAttributeData& OldValue);
    UFUNCTION() void OnRep_MaxStamina(const FGameplayAttributeData& OldValue);
    UFUNCTION() void OnRep_StaminaCostMultiplier(const FGameplayAttributeData& OldValue);
    UFUNCTION() void OnRep_StaminaRecoveryMultiplier(const FGameplayAttributeData& OldValue);

    UFUNCTION() void OnRep_UltGauge(const FGameplayAttributeData& OldValue);
    UFUNCTION() void OnRep_MaxUltGauge(const FGameplayAttributeData& OldValue);
    UFUNCTION() void OnRep_UltGainMultiplier(const FGameplayAttributeData& OldValue);
    UFUNCTION() void OnRep_BreakContributionMultiplier(const FGameplayAttributeData& OldValue);

    virtual void PreAttributeBaseChange(const FGameplayAttribute& Attribute, float& NewValue) const override;
    virtual void PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue) override;
    virtual void PostAttributeChange(const FGameplayAttribute& Attribute, float OldValue, float NewValue) override;

    /** UltGain meta 처리 — UltGauge += UltGain × UltGainMultiplier (HealthSet의 Damage 처리와 대칭) */
    virtual void PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data) override;

    void ClampAttribute(const FGameplayAttribute& Attribute, float& NewValue) const;

private:
    UPROPERTY(BlueprintReadOnly, Category = "Astral|Stamina", ReplicatedUsing = OnRep_Stamina, meta = (AllowPrivateAccess = true))
    FGameplayAttributeData Stamina;

    UPROPERTY(BlueprintReadOnly, Category = "Astral|Stamina", ReplicatedUsing = OnRep_MaxStamina, meta = (AllowPrivateAccess = true))
    FGameplayAttributeData MaxStamina;

    UPROPERTY(BlueprintReadOnly, Category = "Astral|Stamina", ReplicatedUsing = OnRep_StaminaCostMultiplier, meta = (AllowPrivateAccess = true))
    FGameplayAttributeData StaminaCostMultiplier;

    UPROPERTY(BlueprintReadOnly, Category = "Astral|Stamina", ReplicatedUsing = OnRep_StaminaRecoveryMultiplier, meta = (AllowPrivateAccess = true))
    FGameplayAttributeData StaminaRecoveryMultiplier;

    UPROPERTY(BlueprintReadOnly, Category = "Astral|Ult", ReplicatedUsing = OnRep_UltGauge, meta = (AllowPrivateAccess = true))
    FGameplayAttributeData UltGauge;

    UPROPERTY(BlueprintReadOnly, Category = "Astral|Ult", ReplicatedUsing = OnRep_MaxUltGauge, meta = (AllowPrivateAccess = true))
    FGameplayAttributeData MaxUltGauge;

    UPROPERTY(BlueprintReadOnly, Category = "Astral|Ult", ReplicatedUsing = OnRep_UltGainMultiplier, meta = (AllowPrivateAccess = true))
    FGameplayAttributeData UltGainMultiplier;

    UPROPERTY(BlueprintReadOnly, Category = "Astral|Ult", ReplicatedUsing = OnRep_BreakContributionMultiplier, meta = (AllowPrivateAccess = true))
    FGameplayAttributeData BreakContributionMultiplier;

    /** 오의 수급 meta — GE_UltGain(SetByCaller.UltGain)의 착지점. 비복제, 처리 후 0 리셋 */
    UPROPERTY(BlueprintReadOnly, Category = "Astral|Ult", meta = (AllowPrivateAccess = true))
    FGameplayAttributeData UltGain;

    // 서버 전용 — OnUltFilled 1회 발사 게이트
    bool bUltFilled;
};
