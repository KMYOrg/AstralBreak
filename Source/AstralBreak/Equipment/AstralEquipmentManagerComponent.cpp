#include "AstralEquipmentManagerComponent.h"

#include "AbilitySystemGlobals.h"
#include "AstralEquipmentFamily.h"
#include "AstralEquipmentInstance.h"
#include "AstralItemDefinition.h"
#include "AstralLogChannels.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "Net/UnrealNetwork.h"
#include "System/AstralAssetManager.h"

UAstralAbilitySystemComponent* FAstralEquipmentList::GetAbilitySystemComponent() const
{
	const AActor* OwningActor = OwnerComponent ? OwnerComponent->GetOwner() : nullptr;
	return Cast<UAstralAbilitySystemComponent>(UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(OwningActor));
}

UAstralEquipmentInstance* FAstralEquipmentList::AddEntry(const FPrimaryAssetId& ItemId, const UAstralItemDefinition* ItemDef)
{
	check(ItemDef && ItemDef->EquipmentFamily && OwnerComponent);
	check(OwnerComponent->GetOwner()->HasAuthority());

	const UAstralEquipmentFamily* Family = ItemDef->EquipmentFamily;

	TSubclassOf<UAstralEquipmentInstance> InstanceType = Family->InstanceType;
	if (!InstanceType)
	{
		InstanceType = UAstralEquipmentInstance::StaticClass();
	}

	FAstralAppliedEquipmentEntry& NewEntry = Entries.AddDefaulted_GetRef();
	NewEntry.ItemId = ItemId;
	NewEntry.EquipmentFamily = Family;
	// Outer = 폰 — 인스턴스의 GetPawn()/GetWorld() 경로이자 서브오브젝트 복제 소유자
	NewEntry.Instance = NewObject<UAstralEquipmentInstance>(OwnerComponent->GetOwner(), InstanceType);

	// 어빌리티/스탯 부여 — SourceObject = Instance (GA가 GetCurrentSourceObject()로 자기 무기를 얻는다)
	if (UAstralAbilitySystemComponent* ASC = GetAbilitySystemComponent())
	{
		for (const UAstralAbilitySet* AbilitySet : Family->AbilitySetsToGrant)
		{
			if (AbilitySet)
			{
				AbilitySet->GiveToAbilitySystem(ASC, &NewEntry.GrantedHandles, NewEntry.Instance);
			}
		}

		// 변형 능력치 — 같은 부여/회수 기계 재사용
		if (ItemDef->StatSet)
		{
			ItemDef->StatSet->GiveToAbilitySystem(ASC, &NewEntry.GrantedHandles, NewEntry.Instance);
		}
	}
	else
	{
		UE_LOG(LogAstral, Warning, TEXT("EquipmentList::AddEntry — ASC 없음 (%s). 어빌리티/스탯 부여 생략"), *GetNameSafe(OwnerComponent->GetOwner()));
	}

	MarkItemDirty(NewEntry);
	return NewEntry.Instance;
}

void FAstralEquipmentList::RemoveEntry(UAstralEquipmentInstance* Instance)
{
	for (auto EntryIt = Entries.CreateIterator(); EntryIt; ++EntryIt)
	{
		FAstralAppliedEquipmentEntry& Entry = *EntryIt;
		if (Entry.Instance == Instance)
		{
			// ASC가 이미 해체된 경로(EndPlay 등)에서도 안전 — 핸들 회수만 생략됨 (ASC 자체가 소멸)
			if (UAstralAbilitySystemComponent* ASC = GetAbilitySystemComponent())
			{
				Entry.GrantedHandles.TakeFromAbilitySystem(ASC);
			}

			EntryIt.RemoveCurrent();
			MarkArrayDirty();
			return;
		}
	}
}

UAstralEquipmentManagerComponent::UAstralEquipmentManagerComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
	, EquipmentList(this)
{
	PrimaryComponentTick.bCanEverTick = false;

	SetIsReplicatedByDefault(true);
	bReplicateUsingRegisteredSubObjectList = true;
}

void UAstralEquipmentManagerComponent::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(UAstralEquipmentManagerComponent, EquipmentList);
}

const UAstralItemDefinition* UAstralEquipmentManagerComponent::ResolveItemDefinition(const FPrimaryAssetId& ItemId)
{
	if (!ItemId.IsValid())
	{
		return nullptr;
	}

	// 프라이머리 애셋 스캔(DefaultGame.ini /Game/Equipment) 기반 해석 — 페이로드(M1)에 실리는 ID와 동일 경로.
	// ID 타입은 구체 클래스명(AstralWeaponDefinition 등)이고, 여기서는 베이스로만 다룬다
	const FSoftObjectPath AssetPath = UAstralAssetManager::Get().GetPrimaryAssetPath(ItemId);
	const UAstralItemDefinition* ItemDef = Cast<UAstralItemDefinition>(AssetPath.TryLoad());

	if (!ItemDef)
	{
		UE_LOG(LogAstral, Warning, TEXT("ResolveItemDefinition 실패: %s — 스캔 룰(/Game/Equipment)과 애셋 존재 확인"), *ItemId.ToString());
	}
	return ItemDef;
}

UAstralEquipmentInstance* UAstralEquipmentManagerComponent::EquipItemById(const FPrimaryAssetId& ItemId)
{
	if (!GetOwner() || !GetOwner()->HasAuthority())
	{
		return nullptr;
	}

	// 중복 장착 가드
	for (const FAstralAppliedEquipmentEntry& Entry : EquipmentList.Entries)
	{
		if (Entry.ItemId == ItemId)
		{
			return Entry.Instance;
		}
	}

	const UAstralItemDefinition* ItemDef = ResolveItemDefinition(ItemId);
	if (!ItemDef || !ItemDef->EquipmentFamily)
	{
		return nullptr;
	}

	UAstralEquipmentInstance* Instance = EquipmentList.AddEntry(ItemId, ItemDef);
	if (Instance)
	{
		Instance->SpawnEquipmentActors(ItemDef->EquipmentFamily->ActorsToSpawn, ItemDef);
		Instance->OnEquipped();

		if (IsUsingRegisteredSubObjectList() && IsReadyForReplication())
		{
			AddReplicatedSubObject(Instance);
		}
	}
	return Instance;
}

void UAstralEquipmentManagerComponent::UnequipItem(UAstralEquipmentInstance* Instance)
{
	if (!Instance || !GetOwner() || !GetOwner()->HasAuthority())
	{
		return;
	}

	if (IsUsingRegisteredSubObjectList())
	{
		RemoveReplicatedSubObject(Instance);
	}

	Instance->OnUnequipped();
	Instance->DestroyEquipmentActors();
	EquipmentList.RemoveEntry(Instance);
}

void UAstralEquipmentManagerComponent::UnequipAll()
{
	if (!GetOwner() || !GetOwner()->HasAuthority())
	{
		return;
	}

	for (int32 Index = EquipmentList.Entries.Num() - 1; Index >= 0; --Index)
	{
		if (UAstralEquipmentInstance* Instance = EquipmentList.Entries[Index].Instance)
		{
			UnequipItem(Instance);
		}
		else
		{
			EquipmentList.Entries.RemoveAt(Index);
			EquipmentList.MarkArrayDirty();
		}
	}
}

UAstralEquipmentInstance* UAstralEquipmentManagerComponent::GetFirstInstanceOfType(TSubclassOf<UAstralEquipmentInstance> InstanceType) const
{
	for (const FAstralAppliedEquipmentEntry& Entry : EquipmentList.Entries)
	{
		if (Entry.Instance && Entry.Instance->IsA(InstanceType))
		{
			return Entry.Instance;
		}
	}
	return nullptr;
}

void UAstralEquipmentManagerComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	// 어빌리티 누수 안전망 — OnAbilitySystemUninitialized 경로가 먼저 비웠으면 no-op (멱등)
	UnequipAll();

	Super::EndPlay(EndPlayReason);
}

void UAstralEquipmentManagerComponent::ReadyForReplication()
{
	Super::ReadyForReplication();

	// 복제 준비 전에 장착된 인스턴스들 등록
	if (IsUsingRegisteredSubObjectList())
	{
		for (const FAstralAppliedEquipmentEntry& Entry : EquipmentList.Entries)
		{
			if (Entry.Instance)
			{
				AddReplicatedSubObject(Entry.Instance);
			}
		}
	}
}
