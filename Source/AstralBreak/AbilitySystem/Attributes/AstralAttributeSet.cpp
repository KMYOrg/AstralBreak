#include "AstralAttributeSet.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"

UAstralAttributeSet::UAstralAttributeSet()
{
}

UWorld* UAstralAttributeSet::GetWorld() const
{
	const UObject* Outer = GetOuter();
	check(Outer);

	return Outer->GetWorld();
}

UAstralAbilitySystemComponent* UAstralAttributeSet::GetAstralAbilitySystemComponent() const
{
	return Cast<UAstralAbilitySystemComponent>(GetOwningAbilitySystemComponent());
}

