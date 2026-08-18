#pragma once

#include "CoreMinimal.h"
#include "Components/GameFrameworkComponent.h"
#include "GameplayEffectTypes.h"
#include "AstralHealthComponent.generated.h"

class UAstralAbilitySystemComponent;
class UAstralHealthSet;
struct FGameplayEffectSpec;

/** 사망 상태 기계 */
UENUM(BlueprintType)
enum class EAstralDeathState : uint8
{
	NotDead = 0,
	DeathStarted,
	DeathFinished
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FAstralHealth_DeathEvent, AActor*, OwningActor);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_ThreeParams(FAstralHealth_AttributeChanged, UAstralHealthComponent*, HealthComponent, float, OldValue, float, NewValue);

/**
 * 책임은 상태 기계뿐 — DeathState 전이, State.Death 태그 부여, 어빌리티 취소, 델리게이트
 * 물리 반응(콜리전/이동/래그돌)은 소유 액터가 OnDeathStarted/OnDeathFinished를 구독해 처리
 * Hero: ASC가 PlayerState 소유 → PawnExtensionComponent의 Init/Uninit 경로에서 연결.
 * CombatCharacter(더미/몬스터): 자기 ASC → PostInitializeComponents에서 직접 연결.
 */
UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralHealthComponent : public UGameFrameworkComponent
{
	GENERATED_BODY()

public:
	UAstralHealthComponent(const FObjectInitializer& ObjectInitializer);

	UFUNCTION(BlueprintPure, Category = "Astral|Health")
	static UAstralHealthComponent* FindHealthComponent(const AActor* Actor) { return (Actor ? Actor->FindComponentByClass<UAstralHealthComponent>() : nullptr); }

	void InitializeWithAbilitySystem(UAstralAbilitySystemComponent* InASC);
	void UninitializeFromAbilitySystem();

	UFUNCTION(BlueprintPure, Category = "Astral|Health")
	float GetHealth() const;

	UFUNCTION(BlueprintPure, Category = "Astral|Health")
	float GetMaxHealth() const;

	UFUNCTION(BlueprintPure, Category = "Astral|Health")
	float GetHealthNormalized() const;

	UFUNCTION(BlueprintPure, Category = "Astral|Health")
	EAstralDeathState GetDeathState() const { return DeathState; }

	UFUNCTION(BlueprintPure, Category = "Astral|Health")
	bool IsDeadOrDying() const { return DeathState != EAstralDeathState::NotDead; }

	/** 사망 시작 — 서버에서 OnOutOfHealth로 진입, 클라는 OnRep 리플레이로 동기화 */
	virtual void StartDeath();

	/** 사망 완료 — 소유 액터가 연출(몽타주/타이머) 종료 시점에 호출 */
	virtual void FinishDeath();

	/** 사망 상태 해제 (서버 권위) — 디버그 부활(ReviveSelf)·추후 M6 리스폰용. 태그 정리 + OnDeathReset 발사 */
	virtual void ResetDeathState();

public:
	/** HP 변경 (클라/서버 모두 발화 — HP바 등 UI 구독용) */
	UPROPERTY(BlueprintAssignable)
	FAstralHealth_AttributeChanged OnHealthChanged;

	UPROPERTY(BlueprintAssignable)
	FAstralHealth_DeathEvent OnDeathStarted;

	UPROPERTY(BlueprintAssignable)
	FAstralHealth_DeathEvent OnDeathFinished;

	/** 사망 상태가 해제될 때 (부활/리스폰) — 액터가 콜리전/이동 복구를 구독 */
	UPROPERTY(BlueprintAssignable)
	FAstralHealth_DeathEvent OnDeathReset;

protected:
	virtual void OnUnregister() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;

	void HandleHealthAttributeChanged(const FOnAttributeChangeData& Data);
	void HandleOutOfHealth(AActor* DamageInstigator, AActor* DamageCauser, const FGameplayEffectSpec* DamageEffectSpec, float DamageMagnitude, float OldValue, float NewValue);

	UFUNCTION()
	void OnRep_DeathState(EAstralDeathState OldDeathState);

protected:
	UPROPERTY(ReplicatedUsing = OnRep_DeathState)
	EAstralDeathState DeathState;

	UPROPERTY(Transient)
	TObjectPtr<UAstralAbilitySystemComponent> AbilitySystemComponent;

	UPROPERTY(Transient)
	TObjectPtr<const UAstralHealthSet> HealthSet;

private:
	FDelegateHandle HealthChangedDelegateHandle;
};
