// Fill out your copyright notice in the Description page of Project Settings.


#include "AstralGameInstance.h"

#include "AstralGameplayTags.h"
#include "Components/GameFrameworkComponentManager.h"

UAstralGameInstance::UAstralGameInstance(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

void UAstralGameInstance::Init()
{
	Super::Init();
	
	UGameFrameworkComponentManager* ComponentManager = GetSubsystem<UGameFrameworkComponentManager>(this);

	if (ensure(ComponentManager))
	{
		ComponentManager->RegisterInitState(AstralGameplayTags::InitState_Spawned, false, FGameplayTag());
		ComponentManager->RegisterInitState(AstralGameplayTags::InitState_DataAvailable, false, AstralGameplayTags::InitState_Spawned);
		ComponentManager->RegisterInitState(AstralGameplayTags::InitState_DataInitialized, false, AstralGameplayTags::InitState_DataAvailable);
		ComponentManager->RegisterInitState(AstralGameplayTags::InitState_GameplayReady, false, AstralGameplayTags::InitState_DataInitialized);
	}
}

void UAstralGameInstance::Shutdown()
{
	Super::Shutdown();
}
