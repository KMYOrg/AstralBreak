#include "AstralGE_RangedAimHold.h"

#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Effects/AstralSetByCallerGameplayTags.h"
#include "GameplayEffectComponents/TargetTagsGameplayEffectComponent.h"

UAstralGE_RangedAimHold::UAstralGE_RangedAimHold()
{
	DurationPolicy = EGameplayEffectDurationType::HasDuration;

	// 지속 시간은 호출자(GA) 주입 — 스펙마다 SetSetByCallerMagnitude(SetByCaller.Duration, 초)
	FSetByCallerFloat Duration;
	Duration.DataTag = AstralGameplayTags::SetByCaller_Duration;
	DurationMagnitude = FGameplayEffectModifierMagnitude(Duration);

	// 스택 1 · 재적용은 지속 시간만 갱신 (새 스펙의 Duration 사용) · 만료 시 전체 제거.
	// StackingType 은 5.7 에서 deprecated(private 예정)지만 런타임 setter 가 없다(SetStackingType 은 WITH_EDITOR) — 엔진 자체도 같은 pragma 로 쓴다
	PRAGMA_DISABLE_DEPRECATION_WARNINGS
	StackingType = EGameplayEffectStackingType::AggregateByTarget;
	PRAGMA_ENABLE_DEPRECATION_WARNINGS
	StackLimitCount = 1;
	StackDurationRefreshPolicy = EGameplayEffectStackingDurationPolicy::RefreshOnSuccessfulApplication;
	StackExpirationPolicy = EGameplayEffectStackingExpirationPolicy::ClearEntireStack;

	// 부여 태그 — 네이티브 GE 는 PostLoad/BP 컴파일을 거치지 않으므로 생성자에서 컴포넌트를 만들고 직접 적용한다
	// (UGameplayEffect::PostInitProperties 가 "GEComponents 에 들어 있는 기본 서브오브젝트" 를 요구 — GameplayEffect.cpp:200-215).
	// SetAndApplyTargetTagChanges 가 InheritableGrantedTagsContainer 를 채우고 오너의 CachedGrantedTags 에 반영한다
	UTargetTagsGameplayEffectComponent* TargetTags = CreateDefaultSubobject<UTargetTagsGameplayEffectComponent>(TEXT("TargetTags"));
	FInheritedTagContainer GrantedTags;
	GrantedTags.Added.AddTag(AstralGameplayTags::State_Ranged_Aiming);
	TargetTags->SetAndApplyTargetTagChanges(GrantedTags);
	GEComponents.Add(TargetTags);
}
