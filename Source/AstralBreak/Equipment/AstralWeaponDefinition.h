#pragma once

#include "CoreMinimal.h"
#include "AstralItemDefinition.h"
#include "AstralWeaponDefinition.generated.h"

class USkeletalMesh;

/** 무기 변형 메시 정보 */
USTRUCT(BlueprintType)
struct FAstralWeaponMeshInfo
{
	GENERATED_BODY()

	UPROPERTY(EditDefaultsOnly, Category = "Weapon")
	TSoftObjectPtr<USkeletalMesh> Mesh;

	/** 메시 피벗 보정 */
	UPROPERTY(EditDefaultsOnly, Category = "Weapon")
	FTransform MeshOffset;
};

/**
 * 무기 변형 데이터 — 변형당 1개.
 * ID = "AstralWeaponDefinition:애셋명" — DefaultGame.ini 스캔(/Game/Equipment), M1 페이로드에 실리는 ID.
 * 메시는 무기 액터가 OnEquipmentDataApplied에서 꺼내 적용한다 (pull — 트레이스 소켓은 이 메시에 있어야 함).f
 */
UCLASS(BlueprintType, Const, Meta = (DisplayName = "Astral Weapon Definition"))
class ASTRALBREAK_API UAstralWeaponDefinition : public UAstralItemDefinition
{
	GENERATED_BODY()

public:
	/** 변형 메시 + 피벗 보정 */
	UPROPERTY(EditDefaultsOnly, Category = "Weapon")
	FAstralWeaponMeshInfo MeshInfo;
};
