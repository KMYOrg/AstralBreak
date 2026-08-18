// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/GameInstance.h"
#include "AstralGameInstance.generated.h"

/**
 * 
 */
UCLASS()
class ASTRALBREAK_API UAstralGameInstance : public UGameInstance
{
	GENERATED_BODY()
	
public:
	UAstralGameInstance(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
	
protected:

	virtual void Init() override;
	virtual void Shutdown() override;
};
