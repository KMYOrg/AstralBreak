#include "AstralAssetManager.h"

#include "AbilitySystemGlobals.h"

UAstralAssetManager::UAstralAssetManager()
{
}

UAstralAssetManager& UAstralAssetManager::Get()
{
	check(GEngine);
	UAstralAssetManager* Singleton = Cast<UAstralAssetManager>(GEngine->AssetManager);
	if (Singleton)
	{
		return *Singleton;
	}

	UE_LOG(LogTemp, Fatal, TEXT("Invalid AssetManagerClassName in DefaultEngine.ini. Must be UAstralAssetManager or derived."));
	return *NewObject<UAstralAssetManager>();
}

void UAstralAssetManager::StartInitialLoading()
{
	Super::StartInitialLoading();

}