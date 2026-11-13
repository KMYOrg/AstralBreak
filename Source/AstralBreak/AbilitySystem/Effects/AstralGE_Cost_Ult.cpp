#include "AstralGE_Cost_Ult.h"

#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"

UAstralGE_Cost_Ult::UAstralGE_Cost_Ult()
{
	DurationPolicy = EGameplayEffectDurationType::Instant;

	// 비용 = 소스의 MaxUltGauge × −1. 스냅샷하지 않는다 — 검사 · 적용 시점의 최대치를 읽는다.
	// 소스 캡처는 스펙 생성 때 이펙트 컨텍스트의 인스티게이터 ASC 에서 일어나므로(비용 검사가 만드는 임시 스펙 포함) 검사 시점에도 값이 잡힌다
	FAttributeBasedFloat Cost;
	Cost.Coefficient = FScalableFloat(-1.f);
	Cost.BackingAttribute = FGameplayEffectAttributeCaptureDefinition(UAstralHeroResourceSet::GetMaxUltGaugeAttribute(), EGameplayEffectAttributeCaptureSource::Source, /*bSnapshot=*/false);
	Cost.AttributeCalculationType = EAttributeBasedFloatCalculationType::AttributeMagnitude;

	FGameplayModifierInfo Modifier;
	Modifier.Attribute = UAstralHeroResourceSet::GetUltGaugeAttribute();
	Modifier.ModifierOp = EGameplayModOp::Additive;
	Modifier.ModifierMagnitude = FGameplayEffectModifierMagnitude(Cost);
	Modifiers.Add(Modifier);
}
