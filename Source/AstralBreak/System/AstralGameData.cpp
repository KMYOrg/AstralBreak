#include "AstralGameData.h"

#include "System/AstralAssetManager.h"

UAstralGameData::UAstralGameData()
{
}

const UAstralGameData& UAstralGameData::Get()
{
	return UAstralAssetManager::Get().GetGameData();
}
