#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemComponent.h"
#include "NativeGameplayTags.h"
#include "AstralAbilitySystemComponent.generated.h"

UE_DECLARE_GAMEPLAY_TAG_EXTERN(TAG_Gameplay_AbilityInputBlocked);

UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralAbilitySystemComponent : public UAbilitySystemComponent
{
	GENERATED_BODY()

public:

	UAstralAbilitySystemComponent(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
	
	virtual void InitAbilityActorInfo(AActor* InOwnerActor, AActor* InAvatarActor) override;
	
	/** 현재 전투 스타일 — 보유 중인 State.CombatStyle 자식 태그. 없으면 빈 태그 (읽기 단일 경로) */
	FGameplayTag GetCombatStyle() const;

	/** 서버 — 전투 스타일 설정 (이 함수 외 설정 금지). 부모 태그 검증 + 보유 스타일 일괄 해제 */
	void SetCombatStyle(FGameplayTag NewStyle);

	void AbilityInputTagPressed(const FGameplayTag& InputTag);
	void AbilityInputTagReleased(const FGameplayTag& InputTag);
	
	void ProcessAbilityInput(float DeltaTime, bool bGamePaused);
	void ClearAbilityInput();

	void TryActivateAbilitiesOnSpawn();
	
protected:
	
	virtual void AbilitySpecInputPressed(FGameplayAbilitySpec& Spec) override;
	virtual void AbilitySpecInputReleased(FGameplayAbilitySpec& Spec) override;
	
protected:

	TArray<FGameplayAbilitySpecHandle> InputPressedSpecHandles;
	TArray<FGameplayAbilitySpecHandle> InputReleasedSpecHandles;
	TArray<FGameplayAbilitySpecHandle> InputHeldSpecHandles;
	
};
