#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Templates/SubclassOf.h"
#include "AstralEnemySpawner.generated.h"

class AAstralEnemySpawner;
class APawn;
class UBoxComponent;
class UPrimitiveComponent;
struct FHitResult;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FAstralEnemySpawner_Cleared, AAstralEnemySpawner*, Spawner);

/**
 * 맵에 놓는 적 스포너 — 서버 전용 (Docs/Design/m3-enemy-ai.md §11 ②).
 * 플레이어 폰이 발동 상자에 들어오면 SpawnPoints 마다 EnemyClass 를 하나씩 낸다. 한 번만 발동한다(웨이브 · 재스폰 없음).
 * 낸 적이 전부 죽기 시작하면(또는 사망 아닌 경로로 없어지면) OnCleared 를 한 번 낸다.
 *
 * 스폰은 UAstralEnemySpawnSubsystem 을 거친다. 발동은 겹침 이벤트다 — 거리를 재는 폴링이 없다.
 * 복제하지 않고 클라이언트에는 로드하지도 않는다(bNetLoadOnClient = false). 낸 적은 평소처럼 복제된다.
 * 발동 상자가 루트다 — 스폰 지점은 상자 중심 기준 상대 위치이고, 상자 크기가 0 이면 겹침으로는 발동하지 않는다(Activate 로만).
 */
UCLASS()
class ASTRALBREAK_API AAstralEnemySpawner : public AActor
{
	GENERATED_BODY()

public:
	AAstralEnemySpawner(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	/** 수동 발동 — 서버 전용. 이미 발동했으면 아무 일도 없다 */
	UFUNCTION(BlueprintCallable, Category = "Astral|Spawn")
	void Activate();

	UFUNCTION(BlueprintPure, Category = "Astral|Spawn")
	bool HasActivated() const { return bActivated; }

	/** 낸 적 가운데 아직 죽기 시작하지 않은 수 */
	UFUNCTION(BlueprintPure, Category = "Astral|Spawn")
	int32 GetNumAliveEnemies() const { return AliveEnemies.Num(); }

	UBoxComponent* GetTriggerBox() const { return TriggerBox; }

public:
	/** 낸 적이 전부 죽기 시작했다 — 1회. 적을 하나도 내지 못한 발동에서는 나지 않는다. 받는 쪽은 아직 없다(M6 구역 진행) */
	UPROPERTY(BlueprintAssignable, Category = "Astral|Spawn")
	FAstralEnemySpawner_Cleared OnCleared;

	/** 낼 적 — BP 하나가 메시 · AbilitySet · 컨트롤러를 묶고 있다(적 PawnData 는 없다) */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Astral|Spawn")
	TSubclassOf<APawn> EnemyClass;

	/** 스폰 지점 — 스포너 기준 상대 위치. 지점 하나에 적 하나. 발동할 때 NavMesh 에 내려 붙이고, 못 내리는 지점은 건너뛴다 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Astral|Spawn", Meta = (MakeEditWidget = true))
	TArray<FVector> SpawnPoints;

	/** 시작하자마자 발동 — 상자를 쓰지 않는다 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Astral|Spawn")
	bool bActivateOnBeginPlay = false;

protected:
	//~ AActor
	virtual void BeginPlay() override;
	//~ End AActor

	/** 발동 상자 — 플레이어 폰이 겹치면 발동한다. 크기(BoxExtent)는 인스턴스에서 고친다 */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Spawn")
	TObjectPtr<UBoxComponent> TriggerBox;

private:
	UFUNCTION()
	void HandleTriggerBeginOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

	UFUNCTION()
	void HandleEnemyDeathStarted(AActor* OwningActor);

	UFUNCTION()
	void HandleEnemyDestroyed(AActor* DestroyedActor);

	/** 사망 시작 · 파괴 둘 다 여기로 — 살아 있는 목록에서 빼고, 비면 OnCleared */
	void HandleEnemyGone(AActor* Enemy);

	/** 낸 적 가운데 아직 죽기 시작하지 않은 것 */
	UPROPERTY(Transient)
	TArray<TObjectPtr<APawn>> AliveEnemies;

	bool bActivated = false;
};
