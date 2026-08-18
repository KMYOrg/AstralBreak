#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Templates/SubclassOf.h"
#include "AstralCharacterDefinition.generated.h"

class UAnimInstance;
class UAstralPawnData;
class USkeletalMesh;

/**
 * 캐릭터 선택 정의 — 무기 Definition과 동일 패턴 (ID = "AstralCharacterDefinition:애셋명", ini 스캔).
 * 로비에서는 외형(Mesh/AnimBP)만 소비하고, 전투 구성은 도착지 GameMode가 결정한다.
 */
UCLASS(BlueprintType, Const, Meta = (DisplayName = "Astral Character Definition"))
class ASTRALBREAK_API UAstralCharacterDefinition : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	/** 외형 메시 — 로비/던전 공통 */
	UPROPERTY(EditDefaultsOnly, Category = "Character")
	TSoftObjectPtr<USkeletalMesh> Mesh;

	/** 외형 AnimBP — 미지정이면 교체 안 함 */
	UPROPERTY(EditDefaultsOnly, Category = "Character")
	TSubclassOf<UAnimInstance> AnimInstanceClass;

	/**
	 * 이 캐릭터의 전투 구성(도착지에서 해석) — 필드만 확보, MVP 미배선 (캐릭터 1종은 GameMode 상수로 충분).
	 * 멀티 히어로 시 Raid GameMode의 GetPawnDataForController가 CharacterId→여기를 해석한다
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Character")
	TObjectPtr<const UAstralPawnData> CombatPawnData;
};
