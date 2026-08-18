#include "AstralEquipmentManagerComponent.h"

#include "AbilitySystemGlobals.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
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

	// 어빌리티/스탯 부여 — Full 정책만 (VisualOnly=로비는 액터 표시만 = 로비 전투 불가의 실차단 지점).
	// SourceObject = Instance (GA가 GetCurrentSourceObject()로 자기 무기를 얻는다)
	const UAstralEquipmentManagerComponent* Manager = Cast<UAstralEquipmentManagerComponent>(OwnerComponent);
	if (Manager && Manager->GetEquipmentPolicy() == EAstralEquipmentPolicy::Full)
	{
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
			// EquipItemById의 ASC 가드로 도달 불가 — 다른 진입점이 생길 때를 위한 안전망으로 유지
			UE_LOG(LogAstral, Warning, TEXT("EquipmentList::AddEntry — ASC 없음 (%s). 어빌리티/스탯 부여 생략"), *GetNameSafe(OwnerComponent->GetOwner()));
		}
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

	// 정책 차단 — None(관전 등)은 장착 자체가 없다
	if (EquipmentPolicy == EAstralEquipmentPolicy::None)
	{
		return nullptr;
	}

	// ASC 준비 전 장착 금지 — 부여 없는 반쪽 장착이 생기고 HasAnyEquipment 가드를 오염시켜
	// 이후 정상 초기화 경로까지 막는다. public이라 디버그 exec·CombatCharacter 경로에서도 직접 불리므로
	// 가드는 여기(최하단 진입점)가 맞다
	if (!UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(GetOwner()))
	{
		UE_LOG(LogAstral, Warning, TEXT("EquipItemById: ASC 준비 전 — 장착 거부 (%s, %s). 초기화 완료 후 재시도된다"), *GetNameSafe(GetOwner()), *ItemId.ToString());
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
		Instance->SpawnEquipmentActors(ItemDef->EquipmentFamily->ActorsToSpawn, ItemDef, ComputeAttachState(ItemDef->EquipmentFamily));
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

bool UAstralEquipmentManagerComponent::IsFamilyActive(const UAstralEquipmentFamily* Family) const
{
	if (!Family || !Family->CombatStyle.IsValid())
	{
		// 스타일 무관 장비(방어구 등)는 항상 활성
		return true;
	}

	const UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(GetOwner());
	return ASC ? ASC->HasMatchingGameplayTag(Family->CombatStyle) : true;
}

EAstralEquipmentAttachState UAstralEquipmentManagerComponent::ComputeAttachState(const UAstralEquipmentFamily* Family) const
{
	// VisualOnly(로비)는 전부 홀스터. Full은 활성 스타일만 손 — 비활성 스타일 무기는 등에 걸린다
	if (EquipmentPolicy != EAstralEquipmentPolicy::Full)
	{
		return EAstralEquipmentAttachState::Holstered;
	}
	return IsFamilyActive(Family) ? EAstralEquipmentAttachState::Held : EAstralEquipmentAttachState::Holstered;
}

void UAstralEquipmentManagerComponent::RefreshEquipmentAttachState()
{
	if (!GetOwner() || !GetOwner()->HasAuthority())
	{
		return;
	}

	for (const FAstralAppliedEquipmentEntry& Entry : EquipmentList.Entries)
	{
		if (Entry.Instance)
		{
			Entry.Instance->SetActorsAttachState(ComputeAttachState(Entry.EquipmentFamily));
		}
	}
}

bool UAstralEquipmentManagerComponent::HasEquipmentForStyle(const FGameplayTag& StyleTag) const
{
	if (!StyleTag.IsValid())
	{
		return false;
	}

	for (const FAstralAppliedEquipmentEntry& Entry : EquipmentList.Entries)
	{
		if (Entry.EquipmentFamily && Entry.EquipmentFamily->CombatStyle == StyleTag)
		{
			return true;
		}
	}
	return false;
}

FGameplayTag UAstralEquipmentManagerComponent::ResolveStyleWithEquipment(FGameplayTag Desired) const
{
	if (Desired.IsValid() && HasEquipmentForStyle(Desired))
	{
		return Desired;
	}

	const FGameplayTag Fallback = FindFirstEquippedStyle();
	return Fallback.IsValid() ? Fallback : Desired;
}

bool UAstralEquipmentManagerComponent::MatchesEquippedItems(const TArray<FPrimaryAssetId>& ItemIds) const
{
	// 집합 비교
	const TSet<FPrimaryAssetId> UniqueIds(ItemIds);
	if (UniqueIds.Num() != EquipmentList.Entries.Num())
	{
		return false;
	}

	for (const FAstralAppliedEquipmentEntry& Entry : EquipmentList.Entries)
	{
		if (!UniqueIds.Contains(Entry.ItemId))
		{
			return false;
		}
	}
	return true;
}

FGameplayTag UAstralEquipmentManagerComponent::FindFirstEquippedStyle() const
{
	for (const FAstralAppliedEquipmentEntry& Entry : EquipmentList.Entries)
	{
		if (Entry.EquipmentFamily && Entry.EquipmentFamily->CombatStyle.IsValid())
		{
			return Entry.EquipmentFamily->CombatStyle;
		}
	}
	return FGameplayTag();
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

void UAstralEquipmentManagerComponent::InitializeWithAbilitySystem(UAstralAbilitySystemComponent* InASC, EAstralEquipmentPolicy InPolicy)
{
	EquipmentPolicy = InPolicy;

	if (BoundASC == InASC)
	{
		return;
	}

	UninitializeFromAbilitySystem();
	BoundASC = InASC;

	if (BoundASC)
	{
		// 부모 태그 구독이 자식(State.CombatStyle.*) 변경에 반응 — 엔진 GatherTagChangeDelegates가
		// GetGameplayTagParents()를 순회하며 부모 등록 델리게이트를 발동한다 (GameplayEffectTypes.cpp:818 확인).
		// AnyCountChange 필수 — NewOrRemoved는 "해제→설정" 쓰기 순서(1→0→1)에 우연히 의존한다
		CombatStyleChangedHandle = BoundASC->RegisterGameplayTagEvent(AstralGameplayTags::State_CombatStyle, EGameplayTagEventType::AnyCountChange)
			.AddUObject(this, &ThisClass::HandleCombatStyleChanged);
	}
}

void UAstralEquipmentManagerComponent::UninitializeFromAbilitySystem()
{
	if (BoundASC && CombatStyleChangedHandle.IsValid())
	{
		BoundASC->RegisterGameplayTagEvent(AstralGameplayTags::State_CombatStyle, EGameplayTagEventType::AnyCountChange).Remove(CombatStyleChangedHandle);
	}
	CombatStyleChangedHandle.Reset();
	BoundASC = nullptr;
}

void UAstralEquipmentManagerComponent::HandleCombatStyleChanged(const FGameplayTag Tag, int32 NewCount)
{
	// 전환 1회에 2번 발동(해제+설정) — 같은 프레임이라 중간 상태가 클라에 복제x
	RefreshEquipmentAttachState();
}

void UAstralEquipmentManagerComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	UnequipAll();
	UninitializeFromAbilitySystem();

	Super::EndPlay(EndPlayReason);
}

void UAstralEquipmentManagerComponent::ReadyForReplication()
{
	Super::ReadyForReplication();

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
