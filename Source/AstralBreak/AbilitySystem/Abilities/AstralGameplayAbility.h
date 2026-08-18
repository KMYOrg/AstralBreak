#pragma once

#include "CoreMinimal.h"
#include "Abilities/GameplayAbility.h"
#include "AstralGameplayAbility.generated.h"

class AAstralCharacter;
class AAstralPlayerController;

/** GA 활성화 정책 */
UENUM(BlueprintType)
enum class EAstralAbilityActivationPolicy : uint8
{
	/** 입력 Trigger 시점에 한 번 발동 */
	OnInputTriggered,
	/** 입력 유지되는 동안 활성화(뗄 때 EndAbility) */
	WhileInputActive,
	/** Pawn에 부여되는 즉시 발동(패시브) */
	OnSpawn,
	/** 수동 발동(다른 GA가 TriggerAbility 호출) */
	Manual
};

UCLASS()
class ASTRALBREAK_API UAstralGameplayAbility : public UGameplayAbility
{
	GENERATED_BODY()
	friend class UAstralAbilitySystemComponent;
	
public:
	UAstralGameplayAbility(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
	
	UFUNCTION(BlueprintCallable, Category = "Astral|Ability")
	UAstralAbilitySystemComponent* GetAstralAbilitySystemComponentFromActorInfo() const;

	UFUNCTION(BlueprintCallable, Category = "Astral|Ability")
	AAstralPlayerController* GetAstralPlayerControllerFromActorInfo() const;

	UFUNCTION(BlueprintCallable, Category = "Astral|Ability")
	AController* GetControllerFromActorInfo() const;

	UFUNCTION(BlueprintCallable, Category = "Astral|Ability")
	AAstralCharacter* GetAstralCharacterFromActorInfo() const;
	
	EAstralAbilityActivationPolicy GetActivationPolicy() const { return ActivationPolicy; }
	
	void TryActivateAbilityOnSpawn(const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilitySpec& Spec) const;
	
protected:
	
	//~UGameplayAbility interface
	virtual bool CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const override;
	virtual void OnGiveAbility(const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilitySpec& Spec) override;
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;
	virtual bool CheckCost(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, OUT FGameplayTagContainer* OptionalRelevantTags = nullptr) const override;
	virtual void ApplyCost(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) const override;
	//~End of UGameplayAbility interface

protected:
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Astral|Ability Activation")
	EAstralAbilityActivationPolicy ActivationPolicy = EAstralAbilityActivationPolicy::OnInputTriggered;
};
