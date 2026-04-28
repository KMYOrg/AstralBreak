#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemComponent.h"
#include "AstralAttributeSet.h"
#include "AstralCombatSet.generated.h"

/**
 * 
 */
UCLASS()
class ASTRALBREAK_API UAstralCombatSet : public UAstralAttributeSet
{
	GENERATED_BODY()
	
public:
	UAstralCombatSet();

	ATTRIBUTE_ACCESSORS(UAstralCombatSet, OutgoingDamageMultiplier);

protected:
	
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	
	UFUNCTION()
	void OnRep_OutgoingDamageMultiplier(const FGameplayAttributeData& OldValue);

	virtual void PreAttributeBaseChange(const FGameplayAttribute& Attribute, float& NewValue) const override;
	virtual void PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue) override;

	void ClampAttribute(const FGameplayAttribute& Attribute, float& NewValue) const;
	
private:
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Combat", ReplicatedUsing = OnRep_OutgoingDamageMultiplier, meta = (AllowPrivateAccess = true))
	FGameplayAttributeData OutgoingDamageMultiplier;
};
