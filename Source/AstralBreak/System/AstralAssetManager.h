// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Engine/AssetManager.h"
#include "Engine/DataAsset.h"
#include "AstralAssetManager.generated.h"

class UAstralGameData;

/**
 * 초기 로드 / PrimaryAssest 관리 훅 제공.
 * 전역 GameData류는 GameDataMap + GetOrLoadTypedGameData 템플릿으로 관리 (Lyra 미러) —
 * 추후 ItemData/UIData 등 타입 추가 시 Path 프로퍼티 + Get 함수만 늘리면 된다.
 */
UCLASS(Config = Game)
class ASTRALBREAK_API UAstralAssetManager : public UAssetManager
{
	GENERATED_BODY()

public:
	UAstralAssetManager();

	static UAstralAssetManager& Get();

	/** 전역 GameData — StartInitialLoading/PreBeginPIE에서 선로드, 미로드 상태 첫 접근 시 블로킹 로드 */
	const UAstralGameData& GetGameData();

protected:
	template <typename GameDataClass>
	const GameDataClass& GetOrLoadTypedGameData(const TSoftObjectPtr<GameDataClass>& DataPath)
	{
		if (TObjectPtr<UPrimaryDataAsset> const* pResult = GameDataMap.Find(GameDataClass::StaticClass()))
		{
			return *CastChecked<GameDataClass>(*pResult);
		}

		// 필요 시 블로킹 로드
		return *CastChecked<const GameDataClass>(LoadGameDataOfClass(GameDataClass::StaticClass(), DataPath, GameDataClass::StaticClass()->GetFName()));
	}

	/** GameData 로드 공통 경로 — 에디터는 동기 로드, 쿠킹 빌드는 AssetManager 핸들(프라이머리 애셋 룰) 경유. 실패는 Fatal */
	UPrimaryDataAsset* LoadGameDataOfClass(TSubclassOf<UPrimaryDataAsset> DataClass, const TSoftObjectPtr<UPrimaryDataAsset>& DataClassPath, FPrimaryAssetType PrimaryAssetType);

	//~ Begin UAssetManager Interface
	virtual void StartInitialLoading() override;
#if WITH_EDITOR
	// PIE 진입 전에 GameData 로드/실패 확정 — 부팅 시 미생성이던 애셋을 재시작 없이 반영하고,
	// 실패를 전투 중 lazy load 시점이 아니라 PIE 시작 전에 드러낸다
	virtual void PreBeginPIE(bool bStartSimulate) override;
#endif
	//~ End UAssetManager Interface

	/** 전역 GameData 애셋 경로 — DefaultGame.ini [/Script/AstralBreak.AstralAssetManager]에서 지정 */
	UPROPERTY(Config)
	TSoftObjectPtr<UAstralGameData> AstralGameDataPath;

	/** 로드된 GameData 캐시 (타입별 1개, 하드 참조로 GC 보호) */
	UPROPERTY(Transient)
	TMap<TObjectPtr<UClass>, TObjectPtr<UPrimaryDataAsset>> GameDataMap;
};
