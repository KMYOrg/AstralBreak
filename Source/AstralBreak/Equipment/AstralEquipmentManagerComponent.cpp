#include "AstralEquipmentManagerComponent.h"

#include "AbilitySystemGlobals.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AstralEquipmentFamily.h"
#include "AstralEquipmentInstance.h"
#include "AstralItemDefinition.h"
#include "AstralLogChannels.h"
#include "AstralRangedWeaponActor.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "Animation/AnimInstance.h"
#include "Animation/AstralAnimInstance.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/Character.h"
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

void FAstralEquipmentList::PostReplicatedReceive(const FFastArraySerializer::FPostReplicatedReceiveParameters& Parameters)
{
	// 클라는 장착 엔트리를 콜백 없이 받는다(인스턴스 훅은 서버 전용) — 레이어 링크만 여기서 따라간다
	if (UAstralEquipmentManagerComponent* Manager = Cast<UAstralEquipmentManagerComponent>(OwnerComponent))
	{
		Manager->RefreshAnimLayers();
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
		RefreshAnimLayers();
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
	RefreshAnimLayers();
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

void UAstralEquipmentManagerComponent::RefreshAnimLayers()
{
	const ACharacter* Character = Cast<ACharacter>(GetOwner());
	USkeletalMeshComponent* Mesh = Character ? Character->GetMesh() : nullptr;
	if (!Mesh)
	{
		return;
	}

	// 활성 계열 중 공급자를 가진 첫 장비 — 스타일 하나에 무기 하나가 전제(스타일↔장비 정합).
	// ASC 결합 전(클라는 장비 복제가 PlayerState·ASC 보다 먼저 온다)에는 스타일을 모른다 — IsFamilyActive 가 "전부 활성" 으로 답해
	// 첫 공급자(Rifle)가 걸렸다(2026-10-20 멀티 PIE: 낫 스타일인데 클라에서 라이플 자세). 결합 시 InitializeWithAbilitySystem 이 다시 부른다
	TSubclassOf<UAnimInstance> Desired;
	if (BoundASC)
	{
		for (const FAstralAppliedEquipmentEntry& Entry : EquipmentList.Entries)
		{
			if (Entry.EquipmentFamily && Entry.EquipmentFamily->AnimLayerClass && IsFamilyActive(Entry.EquipmentFamily))
			{
				Desired = Entry.EquipmentFamily->AnimLayerClass;
				break;
			}
		}
	}

	// no-op 판정 — 같은 클래스가 실제로 링크돼 있을 때만. 메시/AnimBP 교체로 링크가 사라졌으면 다시 건다
	const bool bStillLinked = Desired && Mesh->GetAnimInstance() && Mesh->GetLinkedAnimLayerInstanceByClass(Desired) != nullptr;
	if (Desired != LinkedAnimLayerClass || (Desired && !bStillLinked))
	{
		if (!Mesh->GetAnimInstance())
		{
			// AnimBP 가 아직 없다(외형 교체 전) — 교체 시 LoadoutComponent 가 다시 부른다
			LinkedAnimLayerClass = nullptr;
			return;
		}

		if (LinkedAnimLayerClass && LinkedAnimLayerClass != Desired)
		{
			Mesh->UnlinkAnimClassLayers(LinkedAnimLayerClass);
		}
		if (Desired)
		{
			Mesh->LinkAnimClassLayers(Desired);
		}
		LinkedAnimLayerClass = Desired;
	}

	// 링크가 그대로여도 AnimBP 가 바뀌었을 수 있다 — 새 메인 인스턴스엔 파지점·총구가 없다
	RefreshWeaponAnimData();
}

void UAstralEquipmentManagerComponent::RefreshWeaponAnimData()
{
	ACharacter* Character = Cast<ACharacter>(GetOwner());
	USkeletalMeshComponent* Mesh = Character ? Character->GetMesh() : nullptr;
	UAstralAnimInstance* AnimInstance = Mesh ? Cast<UAstralAnimInstance>(Mesh->GetAnimInstance()) : nullptr;
	if (!AnimInstance)
	{
		return;
	}

	// 손에 든 무기 — 스타일 하나에 손에 든 무기 하나(나머지는 홀스터)라 첫 유효 값이 곧 그것이다. 홀스터 무기는 Held 가 아니라 둘 다 false
	const FName ReferenceBone = AnimInstance->GetWeaponReferenceBone();
	bool bHasGrip = false;
	bool bHasMuzzle = false;
	TArray<AActor*> AttachedActors;
	Character->GetAttachedActors(AttachedActors);
	for (const AActor* Actor : AttachedActors)
	{
		const AAstralWeaponActor* Weapon = Cast<AAstralWeaponActor>(Actor);
		if (!Weapon)
		{
			continue;
		}

		FTransform Grip;
		if (!bHasGrip && Weapon->GetLeftHandGrip(ReferenceBone, Grip))
		{
			AnimInstance->SetLeftHandGrip(Grip);
			bHasGrip = true;
		}

		const AAstralRangedWeaponActor* RangedWeapon = Cast<AAstralRangedWeaponActor>(Weapon);
		FTransform Muzzle;
		if (!bHasMuzzle && RangedWeapon && RangedWeapon->GetMuzzleInReferenceBone(ReferenceBone, Muzzle))
		{
			AnimInstance->SetMuzzle(Muzzle);
			bHasMuzzle = true;
		}
	}

	if (!bHasGrip)
	{
		AnimInstance->ClearLeftHandGrip();
	}
	if (!bHasMuzzle)
	{
		AnimInstance->ClearMuzzle();
	}
}

AAstralRangedWeaponActor* UAstralEquipmentManagerComponent::GetHeldRangedWeapon() const
{
	const AActor* Owner = GetOwner();
	if (!Owner)
	{
		return nullptr;
	}

	TArray<AActor*> AttachedActors;
	Owner->GetAttachedActors(AttachedActors);
	for (AActor* Actor : AttachedActors)
	{
		AAstralRangedWeaponActor* Weapon = Cast<AAstralRangedWeaponActor>(Actor);
		if (Weapon && Weapon->GetAttachState() == EAstralEquipmentAttachState::Held)
		{
			return Weapon;
		}
	}
	return nullptr;
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

void UAstralEquipmentManagerComponent::InitializeWithAbilitySystem(UAstralAbilitySystemComponent* InASC)
{
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

		// 클라는 장비 복제가 ASC 결합보다 먼저 올 수 있다 — 결합 시점에 현재 스타일 기준으로 한 번 맞춘다
		RefreshAnimLayers();
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
	// 레이어 링크는 전 머신 — 해제 발동(카운트 0)에서 공급자가 잠깐 풀리고 설정 발동에서 다시 걸린다 (같은 프레임, 포즈 평가 전)
	RefreshAnimLayers();
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
