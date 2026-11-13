#include "AstralEnemySpawnSubsystem.h"

#include "AstralLogChannels.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"

bool UAstralEnemySpawnSubsystem::ShouldCreateSubsystem(UObject* Outer) const
{
	if (!Super::ShouldCreateSubsystem(Outer))
	{
		return false;
	}

	// 서버 · Standalone 만. 이 시점(InitWorld)의 넷 모드는 시임리스 이동이면 넘겨받은 넷 드라이버, 접속 중이면 대기 중인 접속, PIE 면 시작할 때의 모드에서 나온다
	const UWorld* World = Cast<UWorld>(Outer);
	return World && World->GetNetMode() != NM_Client;
}

bool UAstralEnemySpawnSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

APawn* UAstralEnemySpawnSubsystem::SpawnEnemy(TSubclassOf<APawn> EnemyClass, const FTransform& SpawnTransform)
{
	UWorld* World = GetWorld();
	if (!World || !EnemyClass)
	{
		UE_LOG(LogAstral, Warning, TEXT("EnemySpawnSubsystem: 적 클래스가 없어 스폰하지 못함"));
		return nullptr;
	}

	// 풀링을 넣을 자리 ① — 지금은 매번 새로 만든다
	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
	APawn* Enemy = World->SpawnActor<APawn>(EnemyClass.Get(), SpawnTransform, SpawnParams);

	// 안전망(§1-4) — AutoPossessAI 가 꺼진 적 BP 도 컨트롤러 없이 서 있지 않게
	if (Enemy && !Enemy->GetController())
	{
		Enemy->SpawnDefaultController();
	}
	return Enemy;
}

void UAstralEnemySpawnSubsystem::ReleaseEnemy(APawn* Enemy, float Delay)
{
	if (!IsValid(Enemy))
	{
		return;
	}

	// 풀링을 넣을 자리 ② — 지금은 없앤다. 죽은 폰을 다시 내주지 않는다
	if (Delay > 0.0f)
	{
		Enemy->SetLifeSpan(Delay);
	}
	else
	{
		Enemy->Destroy();
	}
}
