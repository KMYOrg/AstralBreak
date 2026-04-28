#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemComponent.h"
#include "AstralAttributeSet.h"
#include "AstralHealthSet.generated.h"

UCLASS()
class ASTRALBREAK_API UAstralHealthSet : public UAstralAttributeSet
{
	GENERATED_BODY()
	
public:
    UAstralHealthSet();

    ATTRIBUTE_ACCESSORS(UAstralHealthSet, Health);
    ATTRIBUTE_ACCESSORS(UAstralHealthSet, MaxHealth);
    ATTRIBUTE_ACCESSORS(UAstralHealthSet, IncomingDamageMultiplier);
    ATTRIBUTE_ACCESSORS(UAstralHealthSet, Damage);
    ATTRIBUTE_ACCESSORS(UAstralHealthSet, Healing);

    mutable FAstralAttributeEvent OnDamaged;
    mutable FAstralAttributeEvent OnHealed;
    mutable FAstralAttributeEvent OnOutOfHealth;

protected:
    
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    
    UFUNCTION() void OnRep_Health(const FGameplayAttributeData& Old);
    UFUNCTION() void OnRep_MaxHealth(const FGameplayAttributeData& Old);
    UFUNCTION() void OnRep_IncomingDamageMultiplier(const FGameplayAttributeData& Old);

    virtual void PreAttributeChange(const FGameplayAttribute& Attr, float& NewValue) override;
    virtual void PostAttributeChange(const FGameplayAttribute& Attr, float OldValue, float NewValue) override;
    virtual void PreAttributeBaseChange(const FGameplayAttribute& Attr, float& NewValue) const override;
    virtual void PostGameplayEffectExecute(const FGameplayEffectModCallbackData& Data) override;
    virtual bool PreGameplayEffectExecute(FGameplayEffectModCallbackData& Data) override;

    void ClampAttribute(const FGameplayAttribute& Attr, float& NewValue) const;

private:
    UPROPERTY(BlueprintReadOnly, ReplicatedUsing=OnRep_Health, Category="Astral|Health", meta=(AllowPrivateAccess))
    FGameplayAttributeData Health;

    UPROPERTY(BlueprintReadOnly, ReplicatedUsing=OnRep_MaxHealth, Category="Astral|Health", meta=(AllowPrivateAccess))
    FGameplayAttributeData MaxHealth;

    UPROPERTY(BlueprintReadOnly, ReplicatedUsing=OnRep_IncomingDamageMultiplier, Category="Astral|Health", meta=(AllowPrivateAccess))
    FGameplayAttributeData IncomingDamageMultiplier;

    UPROPERTY(BlueprintReadOnly, Category="Astral|Health", meta=(AllowPrivateAccess))
    FGameplayAttributeData Damage;   // meta — non-replicated

    UPROPERTY(BlueprintReadOnly, Category="Astral|Health", meta=(AllowPrivateAccess))
    FGameplayAttributeData Healing;  // meta — non-replicated

    bool bOutOfHealth = false;
};
