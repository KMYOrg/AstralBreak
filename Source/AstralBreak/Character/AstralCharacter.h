#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "GameFramework/Character.h"
#include "AstralCharacter.generated.h"

class UAstralAbilitySystemComponent;
class UAstralHealthComponent;
class UAstralPawnExtensionComponent;
class AAstralPlayerState;

UCLASS()
class ASTRALBREAK_API AAstralCharacter : public ACharacter, public IAbilitySystemInterface
{
	GENERATED_BODY()

public:
	AAstralCharacter(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	//~ IAbilitySystemInterface
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;
	//~ End IAbilitySystemInterface

	UFUNCTION(BlueprintCallable, Category = "Astral|Character")
	AAstralPlayerState* GetAstralPlayerState() const;

	UFUNCTION(BlueprintCallable, Category = "Astral|Character")
	UAstralAbilitySystemComponent* GetAstralAbilitySystemComponent() const;

	UFUNCTION(BlueprintPure, Category = "Astral|Character")
	UAstralHealthComponent* GetHealthComponent() const { return HealthComponent; }

	/** 디버그 — 콘솔에서 `DamageSelf 50`. 데미지 파이프라인(GE_Damage_Base)을 그대로 태워 사망/수급 경로 검증용 */
	UFUNCTION(Exec)
	void DamageSelf(float Amount = 25.0f);

protected:
	UFUNCTION(Server, Reliable)
	void ServerDamageSelf(float Amount);

protected:
	//~ AActor
	virtual void PreInitializeComponents() override;
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	//~ End AActor

	//~ APawn
	virtual void PossessedBy(AController* NewController) override;
	virtual void UnPossessed() override;
	virtual void OnRep_Controller() override;
	virtual void OnRep_PlayerState() override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	//~ End APawn


protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Components", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralPawnExtensionComponent> PawnExtComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Components", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralHealthComponent> HealthComponent;
};
