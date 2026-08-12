#include "AstralLoadoutDisplayComponent.h"

#include "Character/Components/AstralPawnExtensionComponent.h"
#include "Equipment/AstralEquipmentActor.h"
#include "Equipment/AstralEquipmentFamily.h"
#include "Equipment/AstralEquipmentManagerComponent.h"
#include "Equipment/AstralItemDefinition.h"
#include "GameFramework/Character.h"
#include "GameFramework/Pawn.h"
#include "Player/AstralPlayerState.h"

void UAstralLoadoutDisplayComponent::BeginPlay()
{
	Super::BeginPlay();

	// PS 확정 시점(ASC 초기화)에 구독 — RegisterAndCall이라 이미 초기화됐어도 즉시 호출됨
	if (UAstralPawnExtensionComponent* PawnExt = UAstralPawnExtensionComponent::FindPawnExtensionComponent(GetOwner()))
	{
		PawnExt->OnAbilitySystemInitialized_RegisterAndCall(FSimpleMulticastDelegate::FDelegate::CreateUObject(this, &ThisClass::HandleAbilitySystemInitialized));
	}
}

void UAstralLoadoutDisplayComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (AAstralPlayerState* BoundPS = BoundPlayerState.Get(); BoundPS && LoadoutChangedHandle.IsValid())
	{
		BoundPS->OnLoadoutChanged.Remove(LoadoutChangedHandle);
	}
	LoadoutChangedHandle.Reset();
	BoundPlayerState.Reset();

	// 부착 액터는 폰 파괴 시 자동 소멸되지 않는다
	ClearDisplayActors();

	Super::EndPlay(EndPlayReason);
}

void UAstralLoadoutDisplayComponent::HandleAbilitySystemInitialized()
{
	const APawn* OwnerPawn = Cast<APawn>(GetOwner());
	AAstralPlayerState* AstralPS = OwnerPawn ? OwnerPawn->GetPlayerState<AAstralPlayerState>() : nullptr;

	// PS 교체 대응 — 이전 구독 해제 후 재구독
	if (BoundPlayerState.Get() != AstralPS)
	{
		if (AAstralPlayerState* OldPS = BoundPlayerState.Get(); OldPS && LoadoutChangedHandle.IsValid())
		{
			OldPS->OnLoadoutChanged.Remove(LoadoutChangedHandle);
		}
		LoadoutChangedHandle.Reset();
		BoundPlayerState = AstralPS;

		if (AstralPS)
		{
			LoadoutChangedHandle = AstralPS->OnLoadoutChanged.AddUObject(this, &ThisClass::RefreshDisplay);
		}
	}

	// 초기 1회 갱신 — 구독 전에 지나간 로드아웃 도착 커버
	RefreshDisplay();
}

void UAstralLoadoutDisplayComponent::ClearDisplayActors()
{
	for (AActor* DisplayActor : DisplayActors)
	{
		if (DisplayActor)
		{
			DisplayActor->Destroy();
		}
	}
	DisplayActors.Reset();
}

void UAstralLoadoutDisplayComponent::RefreshDisplay()
{
	ClearDisplayActors();

	const APawn* OwnerPawn = Cast<APawn>(GetOwner());
	const AAstralPlayerState* AstralPS = OwnerPawn ? OwnerPawn->GetPlayerState<AAstralPlayerState>() : nullptr;
	if (!AstralPS || AstralPS->GetLoadout().Equipment.Num() == 0 || !GetWorld())
	{
		return;
	}

	USceneComponent* AttachTarget = OwnerPawn->GetRootComponent();
	if (const ACharacter* Character = Cast<ACharacter>(OwnerPawn))
	{
		AttachTarget = Character->GetMesh();
	}
	if (!AttachTarget)
	{
		return;
	}

	for (const FPrimaryAssetId& ItemId : AstralPS->GetLoadout().Equipment)
	{
		const UAstralItemDefinition* ItemDef = UAstralEquipmentManagerComponent::ResolveItemDefinition(ItemId);
		if (!ItemDef || !ItemDef->EquipmentFamily)
		{
			continue;
		}

		for (const FAstralEquipmentActorToSpawn& SpawnInfo : ItemDef->EquipmentFamily->ActorsToSpawn)
		{
			if (!SpawnInfo.ActorToSpawn)
			{
				continue;
			}

			// 로컬 코스메틱 — 비복제·판정 없음·어빌리티 없음. 각 머신이 복제된 Loadout에서 독립적으로 유도
			AActor* DisplayActor = GetWorld()->SpawnActorDeferred<AActor>(SpawnInfo.ActorToSpawn, FTransform::Identity, GetOwner());
			if (!DisplayActor)
			{
				continue;
			}

			DisplayActor->SetReplicates(false);

			if (AAstralEquipmentActor* EquipmentActor = Cast<AAstralEquipmentActor>(DisplayActor))
			{
				// pull 모델 재사용 — 메시/오프셋 적용은 액터가 스스로 (로컬 호출로도 동작)
				EquipmentActor->OnEquipmentDataApplied(ItemDef);
			}

			const FName Socket = SpawnInfo.DisplaySocket.IsNone() ? SpawnInfo.AttachSocket : SpawnInfo.DisplaySocket;
			DisplayActor->SetActorRelativeTransform(SpawnInfo.AttachTransform);
			DisplayActor->AttachToComponent(AttachTarget, FAttachmentTransformRules::KeepRelativeTransform, Socket);
			DisplayActor->FinishSpawning(FTransform::Identity, /*bIsDefaultTransform=*/true);

			DisplayActors.Add(DisplayActor);
		}
	}
}
