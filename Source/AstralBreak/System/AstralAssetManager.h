// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/AssetManager.h"
#include "AstralAssetManager.generated.h"

/**
 * 초기 로드 / PrimaryAssest 관리 훅 제공
 */
UCLASS()
class ASTRALBREAK_API UAstralAssetManager : public UAssetManager
{
	GENERATED_BODY()
	
public:
	UAstralAssetManager();

	static UAstralAssetManager& Get();

protected:
	//~ Begin UAssetManager Interface
	virtual void StartInitialLoading() override;
	//~ End UAssetManager Interface
};
