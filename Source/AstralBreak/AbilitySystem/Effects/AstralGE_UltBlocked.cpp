#include "AstralGE_UltBlocked.h"

#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "GameplayEffectComponents/TargetTagsGameplayEffectComponent.h"

UAstralGE_UltBlocked::UAstralGE_UltBlocked()
{
	DurationPolicy = EGameplayEffectDurationType::Infinite;

	// 부여 태그 — 네이티브 GE 는 생성자에서 컴포넌트를 만들고 직접 적용한다 (UAstralGE_RangedAimHold 와 같은 방법)
	UTargetTagsGameplayEffectComponent* TargetTags = CreateDefaultSubobject<UTargetTagsGameplayEffectComponent>(TEXT("TargetTags"));
	FInheritedTagContainer GrantedTags;
	GrantedTags.Added.AddTag(AstralGameplayTags::State_Ult_Blocked);
	TargetTags->SetAndApplyTargetTagChanges(GrantedTags);
	GEComponents.Add(TargetTags);
}
