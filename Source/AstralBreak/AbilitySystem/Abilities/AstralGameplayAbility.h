#pragma once

#include "CoreMinimal.h"
#include "Abilities/GameplayAbility.h"
#include "AstralGameplayAbility.generated.h"

class AAstralCharacter;
class AAstralPlayerController;
class UGameplayEffect;
struct FAstralAttackTraceHit;
struct FAstralFacingWarpCommand;
struct FAstralSetByCallerEffect;

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
	// 인자 축약 헬퍼 계층: GA 컨텍스트(ASC·Avatar·Level·현재 활성화 핸들)로 GE를 "어떻게" 적용하는가만 안다.

	/** 공격 적중 1건에 데미지 적용 */
	bool ApplyAttackHit(const FAstralAttackTraceHit& Hit, float Damage) const;
	
	/**
	 * (GE, 태그) 쌍은 GameData의 FAstralSetByCallerEffect로만 받는다 — 잘못된 쌍 표현 불가.
	 * GA 컨텍스트(어빌리티·SourceObject·레벨)이 스펙 컨텍스트에 실린다
	 * 스태미나류를 예측 적용으로 바꾸게 되면 이 경로가 그 개조 지점 (현재는 양쪽 다 서버 권위 전용)
	 */
	void ApplySetByCallerEffect(const FAstralSetByCallerEffect& Effect, float Amount) const;

	/**
	 * 공격 방향 보정 — 아바타의 UMotionWarpingComponent에 워프 타겟을 지정
	 * 방향 소스 결정·클램프·설치 시점은 개별 GA(정책), 밴드 수명은 엔진 UAnimNotifyState_MotionWarping.
	 */
	void SetFacingWarp(const FAstralFacingWarpCommand& Command) const;

	/** 이름을 지정해 해제 — RemoveAllWarpTargets는 다른 시스템의 타겟까지 지운다 */
	void ClearFacingWarp(FName WarpTargetName) const;

	/** 여러 이름 일괄 해제 (콤보 스테이지별 타겟을 EndAbility에서 한 번에) */
	void ClearFacingWarps(const TArray<FName>& WarpTargetNames) const;

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
