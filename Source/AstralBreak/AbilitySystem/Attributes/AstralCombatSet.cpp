#include "AstralCombatSet.h"

#include "Net/UnrealNetwork.h"

UAstralCombatSet::UAstralCombatSet()
{
	InitOutgoingDamageMultiplier(1.f);
	InitMoveSpeedMultiplier(1.f);
}

void UAstralCombatSet::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME_CONDITION_NOTIFY(UAstralCombatSet, OutgoingDamageMultiplier, COND_None, REPNOTIFY_Always);
	DOREPLIFETIME_CONDITION_NOTIFY(UAstralCombatSet, MoveSpeedMultiplier, COND_None, REPNOTIFY_Always);
}

void UAstralCombatSet::OnRep_OutgoingDamageMultiplier(const FGameplayAttributeData& OldValue)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UAstralCombatSet, OutgoingDamageMultiplier, OldValue);
}

void UAstralCombatSet::OnRep_MoveSpeedMultiplier(const FGameplayAttributeData& OldValue)
{
	GAMEPLAYATTRIBUTE_REPNOTIFY(UAstralCombatSet, MoveSpeedMultiplier, OldValue);
}

void UAstralCombatSet::PreAttributeBaseChange(const FGameplayAttribute& Attribute, float& NewValue) const
{
	ClampAttribute(Attribute, NewValue);
}

void UAstralCombatSet::PreAttributeChange(const FGameplayAttribute& Attribute, float& NewValue)
{
	ClampAttribute(Attribute, NewValue);
}

void UAstralCombatSet::ClampAttribute(const FGameplayAttribute& Attribute, float& NewValue) const
{
	if (Attribute == GetOutgoingDamageMultiplierAttribute() || Attribute == GetMoveSpeedMultiplierAttribute())
	{
		NewValue = FMath::Max(NewValue, 0.f);
	}
}