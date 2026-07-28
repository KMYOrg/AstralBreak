#include "AstralAssetManager.h"

#include "AbilitySystemGlobals.h"
#include "AstralLogChannels.h"
#include "Engine/StreamableManager.h"
#include "Misc/App.h"
#include "System/AstralGameData.h"

#if WITH_EDITOR
#include "Misc/ScopedSlowTask.h"
#endif

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

	UE_LOG(LogAstral, Fatal, TEXT("Invalid AssetManagerClassName in DefaultEngine.ini. Must be UAstralAssetManager or derived."));
	return *NewObject<UAstralAssetManager>();
}

const UAstralGameData& UAstralAssetManager::GetGameData()
{
	return GetOrLoadTypedGameData<UAstralGameData>(AstralGameDataPath);
}

UPrimaryDataAsset* UAstralAssetManager::LoadGameDataOfClass(TSubclassOf<UPrimaryDataAsset> DataClass, const TSoftObjectPtr<UPrimaryDataAsset>& DataClassPath, FPrimaryAssetType PrimaryAssetType)
{
	UPrimaryDataAsset* Asset = nullptr;

	DECLARE_SCOPE_CYCLE_COUNTER(TEXT("Loading GameData Object"), STAT_GameData, STATGROUP_LoadTime);
	if (!DataClassPath.IsNull())
	{
#if WITH_EDITOR
		FScopedSlowTask SlowTask(0, FText::Format(NSLOCTEXT("AstralEditor", "BeginLoadingGameDataTask", "Loading GameData {0}"), FText::FromName(DataClass->GetFName())));
		SlowTask.MakeDialog(false, true);
#endif
		UE_LOG(LogAstral, Log, TEXT("Loading GameData: %s ..."), *DataClassPath.ToString());
		SCOPE_LOG_TIME_IN_SECONDS(TEXT("    ... GameData loaded!"), nullptr);

		// 에디터: 애셋 레지스트리 스캔 타이밍과 무관하게 동기 로드가 안전.
		// 쿠킹 빌드: AssetManager 핸들 경로 — 프라이머리 애셋 룰/번들과 함께 로드
		if (GIsEditor)
		{
			Asset = DataClassPath.LoadSynchronous();
			LoadPrimaryAssetsWithType(PrimaryAssetType);
		}
		else
		{
			TSharedPtr<FStreamableHandle> Handle = LoadPrimaryAssetsWithType(PrimaryAssetType);
			if (Handle.IsValid())
			{
				Handle->WaitUntilComplete(0.0f, false);
				Asset = Cast<UPrimaryDataAsset>(Handle->GetLoadedAsset());
			}
		}
	}

	if (Asset)
	{
		GameDataMap.Add(DataClass, Asset);
	}
	else
	{
		UE_LOG(LogAstral, Fatal, TEXT("Failed to load GameData asset at %s. Type %s. This is not recoverable and likely means you do not have the correct data to run %s."),
			*DataClassPath.ToString(), *PrimaryAssetType.ToString(), FApp::GetProjectName());
	}

	return Asset;
}

void UAstralAssetManager::StartInitialLoading()
{
	Super::StartInitialLoading();

#if WITH_EDITOR
	// 에디터 부팅은 관대하게 — 최초 셋업(애셋 미생성) 상태에서 Fatal로 에디터가 못 뜨는 것을 방지.
	// 미비 상태는 경고만 남기고, PIE 진입 시점(PreBeginPIE → GetGameData)의 Fatal이 최종 안전망
	if (AstralGameDataPath.IsNull() || AstralGameDataPath.LoadSynchronous() == nullptr)
	{
		UE_LOG(LogAstral, Warning, TEXT("AstralGameData 선로드 실패: %s — DA_AstralGameData 애셋을 생성/배치하세요"), *AstralGameDataPath.ToString());
		return;
	}
#endif

	GetGameData();
}

#if WITH_EDITOR
void UAstralAssetManager::PreBeginPIE(bool bStartSimulate)
{
	Super::PreBeginPIE(bStartSimulate);

	// 부팅 이후 생성/이동된 애셋 반영 + 미비 상태를 PIE 진입 전에 확정
	GetGameData();
}
#endif
