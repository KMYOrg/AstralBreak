#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
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

	/** 계열의 파지 자세 — 액터(씬 루트) 트랜스폼. 변형별 피벗 보정은 MeshOffset(변형 데이터)이 담당 */
	UPROPERTY(EditDefaultsOnly, Category = "Equipment")
	FTransform AttachTransform;
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

	/** 장착 시 스폰·부착할 액터들 (보통 무기 액터 1개) */
	UPROPERTY(EditDefaultsOnly, Category = "Equipment", Meta = (TitleProperty = "ActorToSpawn"))
	TArray<FAstralEquipmentActorToSpawn> ActorsToSpawn;

	/** 장착 시 부여할 어빌리티 세트 (계열 종속 GA — 근접 콤보/피니셔 등). 해제 시 자동 회수 */
	UPROPERTY(EditDefaultsOnly, Category = "Equipment")
	TArray<TObjectPtr<const UAstralAbilitySet>> AbilitySetsToGrant;
};
