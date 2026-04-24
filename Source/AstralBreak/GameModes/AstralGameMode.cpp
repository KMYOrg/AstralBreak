// Fill out your copyright notice in the Description page of Project Settings.


#include "AstralGameMode.h"

AAstralGameMode::AAstralGameMode(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	
}

const UAstralPawnData* AAstralGameMode::GetPawnDataForController(const AController* InController) const
{
	return nullptr;
}

UClass* AAstralGameMode::GetDefaultPawnClassForController_Implementation(AController* InController)
{
	return Super::GetDefaultPawnClassForController_Implementation(InController);
}
