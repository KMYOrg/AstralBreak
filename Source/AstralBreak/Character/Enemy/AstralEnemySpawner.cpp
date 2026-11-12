#include "AstralEnemySpawner.h"

#include "AstralLogChannels.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Character/Enemy/AstralEnemySpawnSubsystem.h"
#include "Components/BoxComponent.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerState.h"
#include "NavigationSystem.h"

namespace AstralEnemySpawnerPrivate
{
	/** 스폰 지점을 NavMesh 에 내릴 때 찾는 범위 (cm) */
	const FVector NavProjectExtent(100.0, 100.0, 300.0);

	/** 발동시키는 폰 — 플레이어의 폰. 적 컨트롤러가 타깃 후보를 모으는 기준과 같다(봇 제외) */
	bool IsSpawnerTriggerPawn(const AActor* Actor)
	{
		const APawn* Pawn = Cast<APawn>(Actor);
		const APlayerState* PlayerState = Pawn ? Pawn->GetPlayerState() : nullptr;
		return PlayerState && !PlayerState->IsABot();
	}
}

AAstralEnemySpawner::AAstralEnemySpawner(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	PrimaryActorTick.bCanEverTick = false;
	PrimaryActorTick.bStartWithTickEnabled = false;

	// 서버 전용 — 복제하지 않고, 레벨에 놓인 것도 클라이언트에는 로드하지 않는다
	bReplicates = false;
	bNetLoadOnClient = false;

	TriggerBox = CreateDefaultSubobject<UBoxComponent>(TEXT("TriggerBox"));
	TriggerBox->SetBoxExtent(FVector(400.0f, 400.0f, 150.0f));
	TriggerBox->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	TriggerBox->SetCollisionObjectType(ECC_WorldDynamic);
	TriggerBox->SetCollisionResponseToAllChannels(ECR_Ignore);
	TriggerBox->SetCollisionResponseToChannel(ECC_Pawn, ECR_Overlap);
	TriggerBox->SetGenerateOverlapEvents(true);
	TriggerBox->SetCanEverAffectNavigation(false);
	SetRootComponent(TriggerBox);
}

void AAstralEnemySpawner::BeginPlay()
{
	Super::BeginPlay();

	// 복제하지 않는 액터는 클라이언트에서도 HasAuthority 가 참이다 — 넷 모드로 가른다
	if (GetNetMode() == NM_Client)
	{
		TriggerBox->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		return;
	}

	if (bActivateOnBeginPlay)
	{
		Activate();
		return;
	}

	// 크기 0 = 상자 없음. Activate 로만 발동한다
	if (TriggerBox->GetUnscaledBoxExtent().IsNearlyZero())
	{
		TriggerBox->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		return;
	}

	TriggerBox->OnComponentBeginOverlap.AddDynamic(this, &ThisClass::HandleTriggerBeginOverlap);

	// 구독 전에 이미 들어와 있던 플레이어 — 한 번 보는 것이고 그 뒤는 이벤트만 받는다
	TArray<AActor*> OverlappingPawns;
	TriggerBox->GetOverlappingActors(OverlappingPawns, APawn::StaticClass());
	for (const AActor* OverlappingPawn : OverlappingPawns)
	{
		if (AstralEnemySpawnerPrivate::IsSpawnerTriggerPawn(OverlappingPawn))
		{
			Activate();
			break;
		}
	}
}

void AAstralEnemySpawner::HandleTriggerBeginOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	if (AstralEnemySpawnerPrivate::IsSpawnerTriggerPawn(OtherActor))
	{
		Activate();
	}
}

void AAstralEnemySpawner::Activate()
{
	UWorld* World = GetWorld();
	if (bActivated || !World || World->GetNetMode() == NM_Client)
	{
		return;
	}
	bActivated = true;

	// 한 번뿐이다 — 상자는 더 쓸 일이 없다
	TriggerBox->OnComponentBeginOverlap.RemoveDynamic(this, &ThisClass::HandleTriggerBeginOverlap);
	TriggerBox->SetCollisionEnabled(ECollisionEnabled::NoCollision);

	UAstralEnemySpawnSubsystem* SpawnSubsystem = World->GetSubsystem<UAstralEnemySpawnSubsystem>();
	if (!SpawnSubsystem || !EnemyClass)
	{
		UE_LOG(LogAstral, Warning, TEXT("EnemySpawner %s: 적 클래스 또는 스폰 서브시스템이 없어 아무것도 내지 못함"), *GetName());
		return;
	}

	const UNavigationSystemV1* NavSystem = FNavigationSystem::GetCurrent<UNavigationSystemV1>(World);
	const FTransform SpawnerTransform = GetActorTransform();
	const FQuat SpawnRotation = FRotator(0.0, GetActorRotation().Yaw, 0.0).Quaternion();
	const float HalfHeight = EnemyClass.GetDefaultObject()->GetDefaultHalfHeight();

	for (int32 PointIndex = 0; PointIndex < SpawnPoints.Num(); ++PointIndex)
	{
		const FVector WorldPoint = SpawnerTransform.TransformPosition(SpawnPoints[PointIndex]);

		FNavLocation NavLocation;
		if (!NavSystem || !NavSystem->ProjectPointToNavigation(WorldPoint, NavLocation, AstralEnemySpawnerPrivate::NavProjectExtent))
		{
			UE_LOG(LogAstral, Warning, TEXT("EnemySpawner %s: 지점 %d (%s) 을 NavMesh 에 내리지 못해 건너뜀"), *GetName(), PointIndex, *WorldPoint.ToCompactString());
			continue;
		}

		APawn* Enemy = SpawnSubsystem->SpawnEnemy(EnemyClass, FTransform(SpawnRotation, NavLocation.Location + FVector(0.0, 0.0, HalfHeight)));
		if (!Enemy)
		{
			continue;
		}

		AliveEnemies.Add(Enemy);
		if (UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(Enemy))
		{
			HealthComponent->OnDeathStarted.AddDynamic(this, &ThisClass::HandleEnemyDeathStarted);
		}
		// 사망이 아닌 제거(직접 Destroy 등)도 센다
		Enemy->OnDestroyed.AddDynamic(this, &ThisClass::HandleEnemyDestroyed);
	}

	UE_LOG(LogAstral, Log, TEXT("EnemySpawner %s activated: spawned %d of %d (%s)"), *GetName(), AliveEnemies.Num(), SpawnPoints.Num(), *GetNameSafe(EnemyClass.Get()));
	if (AliveEnemies.IsEmpty())
	{
		UE_LOG(LogAstral, Warning, TEXT("EnemySpawner %s: 낸 적이 없다 — OnCleared 는 나지 않는다"), *GetName());
	}
}

void AAstralEnemySpawner::HandleEnemyDeathStarted(AActor* OwningActor)
{
	HandleEnemyGone(OwningActor);
}

void AAstralEnemySpawner::HandleEnemyDestroyed(AActor* DestroyedActor)
{
	HandleEnemyGone(DestroyedActor);
}

void AAstralEnemySpawner::HandleEnemyGone(AActor* Enemy)
{
	// 사망 시작 뒤의 파괴는 여기서 걸러진다 — 이미 목록에 없다
	const int32 NumRemoved = AliveEnemies.RemoveAll([Enemy](const TObjectPtr<APawn>& AliveEnemy) { return AliveEnemy.Get() == Enemy; });
	if (NumRemoved == 0)
	{
		return;
	}

	if (Enemy)
	{
		if (UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(Enemy))
		{
			HealthComponent->OnDeathStarted.RemoveDynamic(this, &ThisClass::HandleEnemyDeathStarted);
		}
		Enemy->OnDestroyed.RemoveDynamic(this, &ThisClass::HandleEnemyDestroyed);
	}

	if (AliveEnemies.IsEmpty())
	{
		UE_LOG(LogAstral, Log, TEXT("EnemySpawner %s cleared"), *GetName());
		OnCleared.Broadcast(this);
	}
}
