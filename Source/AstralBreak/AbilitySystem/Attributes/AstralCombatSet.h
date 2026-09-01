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
	ATTRIBUTE_ACCESSORS(UAstralCombatSet, MoveSpeedMultiplier);

protected:

	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	UFUNCTION()
	void OnRep_OutgoingDamageMultiplier(const FGameplayAttributeData& OldValue);

	UFUNCTION()
	void OnRep_MoveSpeedMultiplier(const FGameplayAttributeData& OldValue);

	virtual void PreAttributeBaseChange(const FGameplayAttribute& Attribute, float& NewValue) const override;
	virtual void PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue) override;

	void ClampAttribute(const FGameplayAttribute& Attribute, float& NewValue) const;
	
private:
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Combat", ReplicatedUsing = OnRep_OutgoingDamageMultiplier, meta = (AllowPrivateAccess = true))
	FGameplayAttributeData OutgoingDamageMultiplier;

	/**
	 * Hero·Enemy 공용 세트에 두는 이유: M3 슬로우·M5 보스 가속 같은 이동 디버프가 양쪽에서 같은 노브를 쓴다.
	 * M7 "EX: 이동속도 +10%"가 얹힐 자리. 이동 관련 Attribute가 2개 이상이 되면 UAstralMovementSet으로 분리
	 */
	UPROPERTY(BlueprintReadOnly, Category = "Astral|Combat", ReplicatedUsing = OnRep_MoveSpeedMultiplier, meta = (AllowPrivateAccess = true))
	FGameplayAttributeData MoveSpeedMultiplier;
};
