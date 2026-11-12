#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Templates/SubclassOf.h"
#include "AstralEnemySpawnSubsystem.generated.h"

class APawn;

/**
 * 적 스폰 · 제거의 이음매 — 서버 전용 (Docs/Design/m3-enemy-ai.md §11 ①).
 * 적을 내보내는 곳(스포너 · 디버그 명령)과 치우는 곳(사망 완료)이 전부 여기를 거친다.
 *
 * 풀링은 없다. 안쪽은 SpawnActor · LifeSpan 그대로다 — 풀링을 넣을 때는 이 두 함수의 안쪽만 바꾼다.
 * 그때의 제약: 죽은(또는 죽는 중인) 폰을 다시 내주지 않는다. 재사용하려면 ASC · 트리 · 위협 기록 · 사망 상태를 되돌리는 경로가 먼저 있어야 하고,
 * 사망 중인 폰은 다시 빙의하지 않는다(§1-3 · §1-8).
 *
 * 클라이언트 월드에는 만들지 않는다 — 클라이언트에서 GetSubsystem 은 null 이다.
 */
UCLASS()
class ASTRALBREAK_API UAstralEnemySpawnSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	//~ USubsystem
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	//~ End USubsystem

	/**
	 * 적 하나를 내보낸다. 컨트롤러는 적 BP 의 AutoPossessAI 가 붙이고, 없으면 여기서 기본 컨트롤러를 붙인다.
	 * 자리가 막혀 있으면 밀어서라도 낸다(AdjustIfPossibleButAlwaysSpawn). 실패하면 null
	 */
	APawn* SpawnEnemy(TSubclassOf<APawn> EnemyClass, const FTransform& SpawnTransform);

	/** 죽은 적을 치운다 — Delay 초 뒤 제거, 0 이하면 바로. 복제 액터라 클라이언트에서도 함께 사라진다 */
	void ReleaseEnemy(APawn* Enemy, float Delay);

protected:
	//~ UWorldSubsystem
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	//~ End UWorldSubsystem
};
