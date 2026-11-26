#include "AstralGameMode.h"

#include "AstralGameState.h"
#include "AstralLogChannels.h"
#include "Player/AstralPlayerController.h"
#include "Player/AstralPlayerState.h"
#include "Character/AstralPawnData.h"
#include "Character/Components/AstralPawnExtensionComponent.h"
#include "Character/Hero/AstralCharacter_Hero.h"

AAstralGameMode::AAstralGameMode(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	GameStateClass = AAstralGameState::StaticClass();
	PlayerControllerClass = AAstralPlayerController::StaticClass();
	PlayerStateClass = AAstralPlayerState::StaticClass();
	DefaultPawnClass = AAstralCharacter_Hero::StaticClass();

	// Hub↔Raid 이동 — seamless (Project Settings에 TransitionMap 지정 필요).
	bUseSeamlessTravel = true;
}

const UAstralPawnData* AAstralGameMode::GetPawnDataForController(const AController* InController) const
{
	if (DefaultPawnData)
	{
		return DefaultPawnData;
	}
	
	return nullptr;
}

UClass* AAstralGameMode::GetDefaultPawnClassForController_Implementation(AController* InController)
{
	if (const UAstralPawnData* PawnData = GetPawnDataForController(InController))
	{
		if (PawnData->PawnClass)
		{
			return PawnData->PawnClass;
		}
	}

	return Super::GetDefaultPawnClassForController_Implementation(InController);
}

APawn* AAstralGameMode::SpawnDefaultPawnAtTransform_Implementation(AController* NewPlayer, const FTransform& SpawnTransform)
{
	FActorSpawnParameters SpawnInfo;
	SpawnInfo.Instigator = GetInstigator();
	SpawnInfo.ObjectFlags |= RF_Transient;
	SpawnInfo.bDeferConstruction = true;
	SpawnInfo.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn;
    
	if (UClass* PawnClass = GetDefaultPawnClassForController(NewPlayer))
	{
		if (APawn* SpawnedPawn = GetWorld()->SpawnActor<APawn>(PawnClass, SpawnTransform, SpawnInfo))
		{
			// PawnExtensionComponent에 PawnData 설정
			if (UAstralPawnExtensionComponent* PawnExtComp = UAstralPawnExtensionComponent::FindPawnExtensionComponent(SpawnedPawn))
			{
				if (const UAstralPawnData* PawnData = GetPawnDataForController(NewPlayer))
				{
					PawnExtComp->SetPawnData(PawnData);
				}
				else
				{
					UE_LOG(LogAstral, Error, TEXT("Game mode was unable to set PawnData on the spawned pawn [%s]."), *GetNameSafe(SpawnedPawn));
				}
			}
            
			SpawnedPawn->FinishSpawning(SpawnTransform);
			return SpawnedPawn;
		}
		else
		{
			UE_LOG(LogAstral, Error, TEXT("Game mode was unable to spawn Pawn of class [%s] at [%s]."), *GetNameSafe(PawnClass), *SpawnTransform.ToHumanReadableString());
		}
	}
	else
	{
		UE_LOG(LogAstral, Error, TEXT("Game mode was unable to spawn Pawn due to NULL pawn class."));
	}

	return nullptr;
}

void AAstralGameMode::HandleStartingNewPlayer_Implementation(APlayerController* NewPlayer)
{
	// TODO: M1 마일스톤 시점에서 Experience 로드 유무 체크로 변경
	if (NewPlayer)
	{
		if (AAstralPlayerState* AstralPS = NewPlayer->GetPlayerState<AAstralPlayerState>())
		{
			if (const UAstralPawnData* PawnData = GetPawnDataForController(NewPlayer))
			{
				AstralPS->SetPawnData(PawnData);
			}
			else
			{
				UE_LOG(LogAstral, Error, TEXT("[GameMode] HandleStartingNewPlayer: No PawnData for [%s]."), *GetNameSafe(NewPlayer));
			}
		}
	}
	Super::HandleStartingNewPlayer_Implementation(NewPlayer);
}

void AAstralGameMode::HandleSeamlessTravelPlayer(AController*& C)
{
	UE_LOG(LogAstral, Log, TEXT("[GameMode] HandleSeamlessTravelPlayer: %s (검증 A — seamless 경로 확인용)"), *GetNameSafe(C));

	Super::HandleSeamlessTravelPlayer(C);

	// seamless 경로는 HandleStartingNewPlayer를 타지 않으므로 PawnData 배선을 여기서 보강.
	// 재생성된 PlayerState는 PawnData가 비어 있다 — 이미 설정됐다면(다른 경로가 처리) 건드리지 않는다
	if (C)
	{
		if (AAstralPlayerState* AstralPS = C->GetPlayerState<AAstralPlayerState>())
		{
			if (!AstralPS->GetPawnData<UAstralPawnData>())
			{
				if (const UAstralPawnData* PawnData = GetPawnDataForController(C))
				{
					UE_LOG(LogAstral, Log, TEXT("[GameMode] SeamlessTravel 경로에서 SetPawnData 배선: %s"), *GetNameSafe(PawnData));
					AstralPS->SetPawnData(PawnData);
				}
				else
				{
					UE_LOG(LogAstral, Error, TEXT("[GameMode] HandleSeamlessTravelPlayer: No PawnData for [%s]."), *GetNameSafe(C));
				}
			}
		}
	}
}

void AAstralGameMode::InitGameState()
{
	Super::InitGameState();

	// TODO : M1 마일스톤(Experience 로드 콜백 함수 바인딩)
}
