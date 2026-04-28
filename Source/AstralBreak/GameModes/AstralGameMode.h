// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "AstralGameMode.generated.h"

class UAstralPawnData;
/**
 * 
 */
UCLASS()
class ASTRALBREAK_API AAstralGameMode : public AGameModeBase
{
	GENERATED_BODY()
	
public:
	AAstralGameMode(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	// M1에서 오버라이드될 핵심 훅
	UFUNCTION(BlueprintCallable)
	virtual const UAstralPawnData* GetPawnDataForController(const AController* InController) const;

	//~AGameModeBase interface
	virtual UClass* GetDefaultPawnClassForController_Implementation(AController* InController) override;
	virtual APawn* SpawnDefaultPawnAtTransform_Implementation(AController* NewPlayer, const FTransform& SpawnTransform) override;
	virtual void HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer) override;
	virtual void InitGameState() override;
	//~End of AGameModeBase interface

protected:
	// M2에서만 임시로 하드 레퍼런스 PawnData (M1에서는 Experience로 대체)
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Pawn")
	TObjectPtr<UAstralPawnData> DefaultPawnData;
};
