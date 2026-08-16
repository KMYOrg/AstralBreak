#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "GameplayTagContainer.h"
#include "AstralEquipmentFamily.generated.h"

class AActor;
class UAstralAbilitySet;
class UAstralEquipmentInstance;

/** 장착 시 스폰할 액터 1개의 스펙 */
USTRUCT(BlueprintType)
struct FAstralEquipmentActorToSpawn
{
	GENERATED_BODY()

	UPROPERTY(EditDefaultsOnly, Category = "Equipment")
	TSubclassOf<AActor> ActorToSpawn;

	/** 부착 소켓 (캐릭터 메시 기준, 예: hand_rSocket) */
	UPROPERTY(EditDefaultsOnly, Category = "Equipment")
	FName AttachSocket;

	/** 계열의 파지 자세 — 액터(씬 루트) 트랜스폼. 변형별 자세값은 AttachOffset(변형 데이터)이 담당 */
	UPROPERTY(EditDefaultsOnly, Category = "Equipment")
	FTransform AttachTransform;

	/**
	 * 이 무기의 수납 위치 — 등/허리/옆구리 등 
	 * 비활성 상태(비활성 스타일 / 로비 VisualOnly)에서 이 소켓에 부착된다. 미지정이면 비활성 = 숨김 (기존 동작)
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Equipment")
	FName HolsterSocket;

	/** 수납 자세 — HolsterSocket 기준 상대 트랜스폼 */
	UPROPERTY(EditDefaultsOnly, Category = "Equipment")
	FTransform HolsterTransform;
};

/**
 * 장비 계열(family/archetype) — 계열당 1개, N개 변형(ItemDefinition 파생)이 공유하는 재사용 축.
 * "같은 계열 = 같은 액터 구성·같은 소켓/자세·같은 어빌리티." 변형 차이(메시/스탯)는 변형 데이터가 든다.
 * (구명 UAstralEquipmentDefinition — "장비 공통 데이터"로 오독되어 개명. CoreRedirects로 기존 애셋 호환)
 */
UCLASS(BlueprintType, Const, Meta = (DisplayName = "Astral Equipment Family"))
class ASTRALBREAK_API UAstralEquipmentFamily : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UAstralEquipmentFamily();

	/** 생성할 인스턴스 클래스 — 미지정 시 UAstralEquipmentInstance */
	UPROPERTY(EditDefaultsOnly, Category = "Equipment")
	TSubclassOf<UAstralEquipmentInstance> InstanceType;

	/**
	 * 이 계열이 속한 전투 스타일 (State.CombatStyle.*) — 활성 스타일과 일치할 때만 손 소켓, 불일치면 홀스터.
	 * 빈 태그 = 스타일 무관(항상 활성) — 방어구 등. 계열에 두는 이유: 스타일이 게이트하는 대상이
	 * 계열이 부여하는 어빌리티이므로 (변형에 두면 "낫 변형인데 Ranged 선언" 불일치가 가능해진다)
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Equipment", Meta = (Categories = "State.CombatStyle"))
	FGameplayTag CombatStyle;

	/** 장착 시 스폰·부착할 액터들 (보통 무기 액터 1개) */
	UPROPERTY(EditDefaultsOnly, Category = "Equipment", Meta = (TitleProperty = "ActorToSpawn"))
	TArray<FAstralEquipmentActorToSpawn> ActorsToSpawn;

	/** 장착 시 부여할 어빌리티 세트 (계열 종속 GA — 근접 콤보/피니셔 등). 해제 시 자동 회수 */
	UPROPERTY(EditDefaultsOnly, Category = "Equipment")
	TArray<TObjectPtr<const UAstralAbilitySet>> AbilitySetsToGrant;
};
