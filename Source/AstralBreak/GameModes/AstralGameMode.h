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

	// 멀티 히어로 시 여기서 로드아웃 CharacterId→CombatPawnData 해석 (MVP: 맵 상수)
	UFUNCTION(BlueprintCallable)
	virtual const UAstralPawnData* GetPawnDataForController(const AController* InController) const;

	const FString& GetHubMapName() const { return HubMapName; }

	//~AGameModeBase interface
	virtual UClass* GetDefaultPawnClassForController_Implementation(AController* InController) override;
	virtual APawn* SpawnDefaultPawnAtTransform_Implementation(AController* NewPlayer, const FTransform& SpawnTransform) override;
	virtual void HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer) override;
	virtual void HandleSeamlessTravelPlayer(AController*& C) override;
	virtual void InitGameState() override;
	//~End of AGameModeBase interface

protected:
	// 맵 문맥의 PawnData (Hub/Raid GameMode BP가 각자 지정)
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Pawn")
	TObjectPtr<UAstralPawnData> DefaultPawnData;

	/** 허브 복귀 목적지 (ReturnToHub) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Travel")
	FString HubMapName = TEXT("HubMap");
};
