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

void UAstralEquipmentInstance::SpawnEquipmentActors(const TArray<FAstralEquipmentActorToSpawn>& ActorsToSpawn, const UAstralItemDefinition* Definition, bool bActive)
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

		// 비활성 스타일 장비는 숨김 스폰 — FinishSpawning 전 세팅으로 초기 번치에 bHidden 동봉
		NewActor->SetActorHiddenInGame(!bActive);

		NewActor->SetActorRelativeTransform(SpawnInfo.AttachTransform);
		NewActor->AttachToComponent(AttachTarget, FAttachmentTransformRules::KeepRelativeTransform, SpawnInfo.AttachSocket);
		NewActor->FinishSpawning(FTransform::Identity, /*bIsDefaultTransform=*/true);

		SpawnedActors.Add(NewActor);
	}
}

void UAstralEquipmentInstance::SetActorsActive(bool bActive)
{
	APawn* OwningPawn = GetPawn();
	if (!OwningPawn || !OwningPawn->HasAuthority())
	{
		return;
	}

	for (AActor* Actor : SpawnedActors)
	{
		if (Actor)
		{
			Actor->SetActorHiddenInGame(!bActive);
		}
	}
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
}

void UAstralEquipmentInstance::OnEquipped()
{
	K2_OnEquipped();
}

void UAstralEquipmentInstance::OnUnequipped()
{
	K2_OnUnequipped();
}
