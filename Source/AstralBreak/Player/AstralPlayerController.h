#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "AstralPlayerController.generated.h"

class UAstralAbilitySystemComponent;
class AAstralPlayerState;
/**
 * 
 */
UCLASS()
class ASTRALBREAK_API AAstralPlayerController : public APlayerController
{
	GENERATED_BODY()
	
public:
	AAstralPlayerController(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
	
	UFUNCTION(BlueprintCallable, Category = "Astral|PlayerController")
	AAstralPlayerState* GetAstralPlayerState() const;

	UFUNCTION(BlueprintCallable, Category = "Astral|PlayerController")
	UAstralAbilitySystemComponent* GetAstralAbilitySystemComponent() const;
	
	//~AActor interface
	virtual void PreInitializeComponents() override;
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	//~End of AActor interface
	
	//~APlayerController interface
	virtual void PostProcessInput(const float DeltaTime, const bool bGamePaused) override;
	//~End of APlayerController interface
};
