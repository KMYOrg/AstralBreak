#include "AstralEquipmentInstance.h"

#include "AstralEquipmentActor.h"
#include "AstralEquipmentFamily.h"
#include "GameFramework/Character.h"
#include "GameFramework/Pawn.h"

UWorld* UAstralEquipmentInstance::GetWorld() const
{
	if (const APawn* OwningPawn = GetPawn())
	{
		return OwningPawn->GetWorld();
	}
	return nullptr;
}

APawn* UAstralEquipmentInstance::GetPawn() const
{
	return Cast<APawn>(GetOuter());
}

void UAstralEquipmentInstance::SpawnEquipmentActors(const TArray<FAstralEquipmentActorToSpawn>& ActorsToSpawn, const UAstralItemDefinition* Definition, EAstralEquipmentAttachState InitialState)
{
	APawn* OwningPawn = GetPawn();
	if (!OwningPawn || !OwningPawn->HasAuthority())
	{
		return;
	}

	USceneComponent* AttachTarget = OwningPawn->GetRootComponent();
	if (const ACharacter* Character = Cast<ACharacter>(OwningPawn))
	{
		AttachTarget = Character->GetMesh();
	}

	for (const FAstralEquipmentActorToSpawn& SpawnInfo : ActorsToSpawn)
	{
		if (!SpawnInfo.ActorToSpawn)
		{
			continue;
		}

		AActor* NewActor = GetWorld()->SpawnActorDeferred<AActor>(SpawnInfo.ActorToSpawn, FTransform::Identity, OwningPawn, OwningPawn);
		if (!NewActor)
		{
			continue;
		}

		// 종류별 데이터 적용
		if (AAstralEquipmentActor* EquipmentActor = Cast<AAstralEquipmentActor>(NewActor))
		{
			EquipmentActor->OnEquipmentDataApplied(Definition);
		}

		// 초기 부착 상태는 FinishSpawning 전 확정 — 초기 번치에 bHidden·부착 동봉 (원자성)
		ApplyAttachState(NewActor, SpawnInfo, InitialState, AttachTarget);
		NewActor->FinishSpawning(FTransform::Identity, /*bIsDefaultTransform=*/true);

		SpawnedActors.Add(NewActor);
		SpawnedActorInfos.Add(SpawnInfo);
	}
}

void UAstralEquipmentInstance::SetActorsAttachState(EAstralEquipmentAttachState State)
{
	APawn* OwningPawn = GetPawn();
	if (!OwningPawn || !OwningPawn->HasAuthority())
	{
		return;
	}

	USceneComponent* AttachTarget = OwningPawn->GetRootComponent();
	if (const ACharacter* Character = Cast<ACharacter>(OwningPawn))
	{
		AttachTarget = Character->GetMesh();
	}
	if (!AttachTarget)
	{
		return;
	}

	for (int32 Index = 0; Index < SpawnedActors.Num(); ++Index)
	{
		AActor* Actor = SpawnedActors[Index];
		if (Actor && SpawnedActorInfos.IsValidIndex(Index))
		{
			ApplyAttachState(Actor, SpawnedActorInfos[Index], State, AttachTarget);
		}
	}
}

void UAstralEquipmentInstance::ApplyAttachState(AActor* Actor, const FAstralEquipmentActorToSpawn& SpawnInfo, EAstralEquipmentAttachState State, USceneComponent* AttachTarget) const
{
	const bool bHeld = (State == EAstralEquipmentAttachState::Held);
	const bool bHasHolster = !SpawnInfo.HolsterSocket.IsNone();

	// 홀스터 소켓 미지정 계열의 홀스터 상태 = 숨김 (기존 동작 보존 — 회귀 없음). bHidden은 복제 프로퍼티
	Actor->SetActorHiddenInGame(!bHeld && !bHasHolster);

	const FName Socket = (bHeld || !bHasHolster) ? SpawnInfo.AttachSocket : SpawnInfo.HolsterSocket;
	const FTransform& RelativeTransform = (bHeld || !bHasHolster) ? SpawnInfo.AttachTransform : SpawnInfo.HolsterTransform;

	// 부착 → 상대 트랜스폼 순서 — 재부착(전환) 경로에서도 결정적
	Actor->AttachToComponent(AttachTarget, FAttachmentTransformRules::KeepRelativeTransform, Socket);
	Actor->SetActorRelativeTransform(RelativeTransform);
}

void UAstralEquipmentInstance::DestroyEquipmentActors()
{
	for (AActor* Actor : SpawnedActors)
	{
		if (Actor)
		{
			Actor->Destroy();
		}
	}
	SpawnedActors.Reset();
	SpawnedActorInfos.Reset();
}

void UAstralEquipmentInstance::OnEquipped()
{
	K2_OnEquipped();
}

void UAstralEquipmentInstance::OnUnequipped()
{
	K2_OnUnequipped();
}
