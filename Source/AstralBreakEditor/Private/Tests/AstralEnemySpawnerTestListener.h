#pragma once

#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "AstralEnemySpawnerTestListener.generated.h"

class AAstralEnemySpawner;

/**
 * 스포너 시험용 — AAstralEnemySpawner::OnCleared 가 몇 번 났는지 센다 (설계 Docs/Design/m3-enemy-ai.md §11 S3).
 * OnCleared 는 동적 델리게이트라 받는 쪽이 UFUNCTION 이어야 한다
 */
UCLASS()
class UAstralEnemySpawnerTestListener : public UObject
{
	GENERATED_BODY()

public:
	UFUNCTION()
	void HandleCleared(AAstralEnemySpawner* Spawner) { ++NumCleared; }

	int32 NumCleared = 0;
};
