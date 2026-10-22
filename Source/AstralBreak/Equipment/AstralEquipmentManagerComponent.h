#pragma once

#include "CoreMinimal.h"
#include "Components/PawnComponent.h"
#include "Net/Serialization/FastArraySerializer.h"
#include "AbilitySystem/AstralAbilitySet.h"
#include "Equipment/AstralEquipmentTypes.h"
#include "UObject/PrimaryAssetId.h"
#include "AstralEquipmentManagerComponent.generated.h"

class AAstralRangedWeaponActor;
class UAnimInstance;
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

	/** 클라 — 복제 수신 뒤(추가·변경·제거 반영 후) 소유 매니저의 Anim Layer 링크 갱신. 서버는 Equip/Unequip 이 직접 갱신한다 */
	void PostReplicatedReceive(const FFastArraySerializer::FPostReplicatedReceiveParameters& Parameters);

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

	static UAstralEquipmentManagerComponent* FindEquipmentManager(const AActor* Actor) { return (Actor ? Actor->FindComponentByClass<UAstralEquipmentManagerComponent>() : nullptr); }

	/**
	 * 전 머신 — ASC 결합. 소유 폰이 ASC 준비 시점에 호출(OnAbilitySystemInitialized).
	 * State.CombatStyle 태그 변경을 구독해 부착 상태(서버)와 Linked Anim Layer(전 머신)를 스스로 갱신하고, 결합 시점에 레이어를 한 번 맞춘다
	 * (클라는 장비 복제가 ASC 결합보다 먼저 온다 — 그때는 레이어를 걸지 않고 여기서 건다)
	 */
	void InitializeWithAbilitySystem(UAstralAbilitySystemComponent* InASC);

	void UninitializeFromAbilitySystem();

	/** 서버 — 장착 정책 주입. 소유 폰이 초기 스타일 시드·로드아웃 적용보다 먼저 호출 (정책을 읽는 곳은 전부 서버 권위 경로) */
	void SetEquipmentPolicy(EAstralEquipmentPolicy InPolicy) { EquipmentPolicy = InPolicy; }

	EAstralEquipmentPolicy GetEquipmentPolicy() const { return EquipmentPolicy; }

	/** 서버 — 장착: 어빌리티/스탯 부여(Full 정책만) + 액터 스폰·부착. 같은 ID 재장착은 기존 인스턴스 반환 (멱등) */
	UAstralEquipmentInstance* EquipItemById(const FPrimaryAssetId& ItemId);

	/** 서버 — 해제: 부여분 회수 + 액터 정리 */
	void UnequipItem(UAstralEquipmentInstance* Instance);

	/** 서버 — 전체 해제 (멱등) — EndPlay/ASC 해제 안전망 */
	void UnequipAll();

	/**
	 * 서버 — 전 장비 부착 상태 갱신: 정책×스타일로 산출 (Full+활성 스타일=손, 그 외=홀스터).
	 * 활성 여부는 ASC의 State.CombatStyle.* 태그를 질의 (상태는 ASC 소유 — 이 컴포넌트는 무상태).
	 * 호출은 State.CombatStyle 태그 구독(InitializeWithAbilitySystem)이 자동으로
	 */
	void RefreshEquipmentAttachState();

	/**
	 * 전 머신 — 활성 계열의 AnimLayerClass 를 캐릭터 메시에 LinkAnimClassLayers (없으면 베이스 ABP 기본 구현으로 복귀).
	 * 트리거: ASC 결합 · 스타일 태그 변경(HandleCombatStyleChanged) · 서버 장착/해제 · 클라 장비 복제 수신 · 외형 AnimBP 교체(LoadoutComponent).
	 * ASC 결합 전에는 활성 계열을 판정할 수 없으므로 아무것도 걸지 않는다(결합 시 다시 불린다). 끝에 무기 애니 데이터도 맞춘다(AnimBP 교체 대비)
	 */
	void RefreshAnimLayers();

	/**
	 * 전 머신 — 손에 든 무기의 애니 데이터(양손 무기의 왼손 파지점 · 원거리 무기의 총구)를 메인 AnimInstance 에 넣는다(없으면 비운다).
	 * 둘 다 무기 메시 소켓을 손 본 공간으로 환산한 상수라 매 프레임 조회하지 않는다. 무기는 부착 기준으로 찾는다 — 클라는 인스턴스의
	 * 스폰 목록이 비어 있고 액터가 각자 복제되기 때문. 트리거: RefreshAnimLayers · 장비 액터의 부착/외형 변경(NotifyPresentationChanged). 멱등
	 */
	void RefreshWeaponAnimData();

	/** 전 머신 — 손(Held)에 든 원거리 무기. RefreshWeaponAnimData 와 같은 규칙(부착 기준 — 클라는 스폰 목록이 비어 있다). 없으면 nullptr */
	AAstralRangedWeaponActor* GetHeldRangedWeapon() const;

	/** 해당 스타일과 일치하는 계열 장비 보유 여부 — 스타일 무관(빈 태그) 계열은 제외 (태그 비교만 = 종류-무지 유지) */
	bool HasEquipmentForStyle(const FGameplayTag& StyleTag) const;

	/** 장착 중인 계열들의 첫 유효 스타일 태그 — 없으면 빈 태그. 스타일↔장비 정합의 폴백 대상 */
	FGameplayTag FindFirstEquippedStyle() const;

	/**
	 * 스타일 유효성 정책 (단일 지점) — Desired가 장비 보유 조건을 만족하면 그대로, 아니면 장비 있는 첫
	 * 스타일로 폴백. 스타일 장비가 아예 없으면 Desired 그대로 반환 (스타일 종속 GA가 곧 장비 부여분이라 무해).
	 * ⚠️ 전환 GA의 사이클 후보 필터를 대체하지 않는다 — 순환 시맨틱(다음 유효 후보)과 폴백 시맨틱은 다른 규칙
	 */
	FGameplayTag ResolveStyleWithEquipment(FGameplayTag Desired) const;

	/**
	 * 현재 장착 ID 집합이 목록과 정확히 일치하는지 — 재적용 경로의 no-op 판정용
	 * (동일 로드아웃 재발신 시 Destroy/Respawn 복제·GA 취소 방지). 집합 비교 — 순서·중복 무시
	 */
	bool MatchesEquippedItems(const TArray<FPrimaryAssetId>& ItemIds) const;

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

	/** 부착 상태 산출 — 정책×스타일 결정표: Full+활성=Held, 나머지 전부 Holstered (VisualOnly는 항상 홀스터) */
	EAstralEquipmentAttachState ComputeAttachState(const UAstralEquipmentFamily* Family) const;

	/** State.CombatStyle(부모) 태그 카운트 변경 핸들러 — 전환 1회에 2번 발동(해제+설정) */
	void HandleCombatStyleChanged(const FGameplayTag Tag, int32 NewCount);

	//~UActorComponent
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void ReadyForReplication() override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	//~End UActorComponent

	UPROPERTY(Replicated)
	FAstralEquipmentList EquipmentList;

	/** 장착 정책 — 서버 전용 (소유 폰이 GameState CDO 값을 주입). 기본 Full = 미주입 폰(적 등) 호환 */
	EAstralEquipmentPolicy EquipmentPolicy = EAstralEquipmentPolicy::Full;

	UPROPERTY(Transient)
	TObjectPtr<UAstralAbilitySystemComponent> BoundASC;

	UPROPERTY(Transient)
	TSubclassOf<UAnimInstance> LinkedAnimLayerClass;

	FDelegateHandle CombatStyleChangedHandle;
};
