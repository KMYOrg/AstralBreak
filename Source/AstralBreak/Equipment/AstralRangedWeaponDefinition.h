#pragma once

#include "CoreMinimal.h"
#include "AstralWeaponDefinition.h"
#include "Templates/SubclassOf.h"
#include "AstralRangedWeaponDefinition.generated.h"

class AAstralProjectile;

/**
 * 원거리 무기 변형 데이터 — 근접과의 데이터 이질성(투사체 등) 분리 (만능 클래스화 방지, §2-D 원칙).
 * ID = "AstralRangedWeaponDefinition:애셋명" (ID 타입 = 구체 클래스명) — DefaultGame.ini에 별도 스캔 룰.
 * 소비는 AAstralRangedWeaponActor가 pull (자기 정체성 캐스팅).
 */
UCLASS(BlueprintType, Const, Meta = (DisplayName = "Astral Ranged Weapon Definition"))
class ASTRALBREAK_API UAstralRangedWeaponDefinition : public UAstralWeaponDefinition
{
	GENERATED_BODY()

public:
	/** 이 변형의 투사체 — 무기 액터가 pull 캐시, 원거리 GA가 액터에서 읽는다 (서버 전용 소비라 복제 불필요) */
	UPROPERTY(EditDefaultsOnly, Category = "Weapon|Ranged")
	TSubclassOf<AAstralProjectile> ProjectileClass;
};
