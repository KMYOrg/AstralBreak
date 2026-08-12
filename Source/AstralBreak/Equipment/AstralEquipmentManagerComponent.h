#pragma once

#include "CoreMinimal.h"
#include "Components/PawnComponent.h"
#include "Net/Serialization/FastArraySerializer.h"
#include "AbilitySystem/AstralAbilitySet.h"
#include "UObject/PrimaryAssetId.h"
#include "AstralEquipmentManagerComponent.generated.h"

class UAstralAbilitySystemComponent;
class UAstralEquipmentFamily;
class UAstralEquipmentInstance;
class UAstralItemDefinition;

/** 장착된 장비 1개 엔트리 */
USTRUCT(BlueprintType)
struct FAstralAppliedEquipmentEntry : public FFastArraySerializerItem
{
	GENERATED_BODY()

private:
	friend struct FAstralEquipmentList;
	friend class UAstralEquipmentManagerComponent;

	/** 이 엔트리를 만든 아이템 ID (중복 장착 가드/디버그) */
	UPROPERTY()
	FPrimaryAssetId ItemId;

	UPROPERTY()
	TObjectPtr<const UAstralEquipmentFamily> EquipmentFamily;

	UPROPERTY()
	TObjectPtr<UAstralEquipmentInstance> Instance = nullptr;

	/** 서버 전용 — 부여한 GA/GE/AttributeSet 회수 핸들 */
	UPROPERTY(NotReplicated)
	FAstralAbilitySet_GrantedHandles GrantedHandles;
};

/** 장비 리스트 — FastArray 복제 */
USTRUCT(BlueprintType)
struct FAstralEquipmentList : public FFastArraySerializer
{
	GENERATED_BODY()

	FAstralEquipmentList() : OwnerComponent(nullptr) {}
	FAstralEquipmentList(UActorComponent* InOwnerComponent) : OwnerComponent(InOwnerComponent) {}

	bool NetDeltaSerialize(FNetDeltaSerializeInfo& DeltaParms)
	{
		return FFastArraySerializer::FastArrayDeltaSerialize<FAstralAppliedEquipmentEntry, FAstralEquipmentList>(Entries, DeltaParms, *this);
	}

	/** 서버 — 엔트리 추가 + 어빌리티/스탯 부여 (SourceObject = Instance) */
	UAstralEquipmentInstance* AddEntry(const FPrimaryAssetId& ItemId, const UAstralItemDefinition* ItemDef);

	/** 서버 — 엔트리 제거 + 부여분 회수 */
	void RemoveEntry(UAstralEquipmentInstance* Instance);

private:
	friend class UAstralEquipmentManagerComponent;

	UAstralAbilitySystemComponent* GetAbilitySystemComponent() const;

	UPROPERTY()
	TArray<FAstralAppliedEquipmentEntry> Entries;

	UPROPERTY(NotReplicated)
	TObjectPtr<UActorComponent> OwnerComponent;
};

template<>
struct TStructOpsTypeTraits<FAstralEquipmentList> : public TStructOpsTypeTraitsBase2<FAstralEquipmentList>
{
	enum { WithNetDeltaSerializer = true };
};

/**
 * 장비 매니저 — 폰 컴포넌트 (Hero·CombatCharacter 공용). 장비 종류를 모른다:
 * ID → UAstralItemDefinition(베이스) 해석 → 계열의 액터 스폰 + 어빌리티/스탯 부여.
 * 종류별 데이터(무기 메시 등)는 스폰된 AAstralEquipmentActor가 정의에서 스스로 꺼낸다 (pull).
 * 새 장비 종류 추가 = 정의 파생 + 액터 파생 + ini 스캔 룰 1줄. 이 컴포넌트는 무변경.
 *
 * 해석(ResolveItemDefinition)은 별도 함수 — M1에서 장착 소스가 PawnData 기본 장비 → 페이로드 복원으로
 * 바뀌어도 이 함수와 EquipItemById는 그대로다.
 *
 * ⚠️ 수명주기: ASC는 PlayerState(히어로), 이 컴포넌트는 Pawn — 폰 파괴/빙의 해제 시 회수가 보장되지 않으면
 * 리스폰마다 어빌리티가 중복 누적된다. EndPlay + 소유 액터의 OnAbilitySystemUninitialized 양쪽에서
 * UnequipAll(멱등)을 호출한다.
 */
UCLASS(BlueprintType, Meta = (BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralEquipmentManagerComponent : public UPawnComponent
{
	GENERATED_BODY()

public:
	UAstralEquipmentManagerComponent(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	/** ID → 아이템 정의 해석 (동기 로드 — 정의 애셋은 소형). M1 페이로드 복원도 이 함수를 쓴다.
	 * 어떤 구체 타입의 ID든(AstralWeaponDefinition:... 등) 스캔되어 있으면 해석된다 */
	static const UAstralItemDefinition* ResolveItemDefinition(const FPrimaryAssetId& ItemId);

	/** 서버 — 장착: 어빌리티/스탯 부여 + 액터 스폰·부착. 같은 ID 재장착은 기존 인스턴스 반환 (멱등) */
	UAstralEquipmentInstance* EquipItemById(const FPrimaryAssetId& ItemId);

	/** 서버 — 해제: 부여분 회수 + 액터 정리 */
	void UnequipItem(UAstralEquipmentInstance* Instance);

	/** 서버 — 전체 해제 (멱등) — EndPlay/ASC 해제 안전망 */
	void UnequipAll();

	/**
	 * 서버 — 활성 스타일 변경에 따른 전 장비 표시/숨김 갱신 (비활성 스타일 장비는 숨김).
	 * 활성 여부는 ASC의 State.CombatStyle.* 태그를 질의 (상태는 ASC 소유 — 이 컴포넌트는 무상태).
	 * AAstralCharacter::SetCombatStyle이 태그 갱신 직후 호출한다
	 */
	void RefreshEquipmentActiveState();

	/** 해당 스타일과 일치하는 계열 장비 보유 여부 — 스타일 무관(빈 태그) 계열은 제외 (태그 비교만 = 종류-무지 유지) */
	bool HasEquipmentForStyle(const FGameplayTag& StyleTag) const;

	/** 장착 중인 계열들의 첫 유효 스타일 태그 — 없으면 빈 태그. 스타일↔장비 정합의 폴백 대상 */
	FGameplayTag FindFirstEquippedStyle() const;

	UFUNCTION(BlueprintPure, Category = "Astral|Equipment")
	UAstralEquipmentInstance* GetFirstInstanceOfType(TSubclassOf<UAstralEquipmentInstance> InstanceType) const;

	template <typename T>
	T* GetFirstInstanceOfType() const
	{
		return Cast<T>(GetFirstInstanceOfType(T::StaticClass()));
	}

	bool HasAnyEquipment() const { return EquipmentList.Entries.Num() > 0; }

protected:
	/** 계열이 현재 활성인가 — CombatStyle 미지정(스타일 무관)이거나 ASC가 해당 스타일 태그 보유 시 true */
	bool IsFamilyActive(const UAstralEquipmentFamily* Family) const;

	//~UActorComponent
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void ReadyForReplication() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	//~End UActorComponent

	UPROPERTY(Replicated)
	FAstralEquipmentList EquipmentList;
};
