#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "GameFramework/PlayerState.h"
#include "GenericTeamAgentInterface.h"
#include "AstralPlayerState.generated.h"

class UAstralCombatSet;
class UAstralHealthSet;
class UAstralAbilitySystemComponent;
class UAstralPawnData;
class AAstralPlayerController;
struct FGameplayEffectSpec;
/**
 *
 */
UCLASS()
class ASTRALBREAK_API AAstralPlayerState : public APlayerState, public IAbilitySystemInterface, public IGenericTeamAgentInterface
{
	GENERATED_BODY()
	
public:
	AAstralPlayerState(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
	
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	
	UFUNCTION(BlueprintCallable, Category = "Lyra|PlayerState")
	AAstralPlayerController* GetAstralPlayerController() const;

	UFUNCTION(BlueprintCallable, Category = "Lyra|PlayerState")
	UAstralAbilitySystemComponent* GetAstralAbilitySystemComponent() const { return AbilitySystemComponent; }
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;
	
	template <class T>
	const T* GetPawnData() const { return Cast<T>(PawnData); }

	void SetPawnData(const UAstralPawnData* InPawnData);
	
	//~AActor interface
	virtual void PreInitializeComponents() override;
	virtual void PostInitializeComponents() override;
	//~End of AActor interface
	
	//~APlayerState interface
	virtual void Reset() override;
	virtual void ClientInitialize(AController* C) override;
	virtual void CopyProperties(APlayerState* PlayerState) override;
	//~End of APlayerState interface

	//~IGenericTeamAgentInterface (플레이어는 전원 팀 0 — 4인 협동)
	virtual void SetGenericTeamId(const FGenericTeamId& NewTeamID) override { MyTeamID = NewTeamID; }
	virtual FGenericTeamId GetGenericTeamId() const override { return MyTeamID; }
	//~End of IGenericTeamAgentInterface

protected:

	UFUNCTION()
	void OnRep_PawnData();

	/** 받은 피해 → 오의 수급 (서버 권위). HealthSet·ResourceSet이 둘 다 이 ASC에 살아서 구독 위치가 여기 */
	void OnHeroDamaged(AActor* DamageInstigator, AActor* DamageCauser, const FGameplayEffectSpec* DamageEffectSpec, float DamageMagnitude, float OldValue, float NewValue);
	
private:
	
	// TODO: M1 마일스톤
	//void OnExperienceLoaded(const UAstralExperienceDefinition* CurrentExperience);

protected:

	UPROPERTY(ReplicatedUsing = OnRep_PawnData)
	TObjectPtr<const UAstralPawnData> PawnData;

private:

	UPROPERTY(VisibleAnywhere, Category = "Lyra|PlayerState")
	TObjectPtr<UAstralAbilitySystemComponent> AbilitySystemComponent;

	UPROPERTY()
	TObjectPtr<const UAstralHealthSet> HealthSet;

	UPROPERTY()
	TObjectPtr<const UAstralCombatSet> CombatSet;

	FGenericTeamId MyTeamID = FGenericTeamId(0);
};
