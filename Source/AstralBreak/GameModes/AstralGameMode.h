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

	/** 레이드 목적지 검증 — RaidMapNames 와 정확히(대소문자 포함) 일치하는 이름만 참. 옵션(?...)이 붙은 문자열은 거짓 */
	bool IsRaidMapAllowed(const FString& MapName) const;

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

	/**
	 * 레이드 목적지 허용 목록 (SelectRaid) — 클라이언트가 보낸 이름이 그대로 ServerTravel 주소가 되므로 여기 있는 것만 받는다.
	 * 정식 퀘스트 구조(M6)가 생기면 그쪽으로 옮긴다
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Travel")
	TArray<FString> RaidMapNames = { TEXT("RaidMap") };
};
