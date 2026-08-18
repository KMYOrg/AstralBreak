#pragma once

#include "CoreMinimal.h"
#include "AstralWeaponActor.h"
#include "AstralRangedWeaponActor.generated.h"

class AAstralProjectile;

/**
 * 원거리 무기 액터 — 발사 원점(Muzzle)과 투사체 pull 캐시를 담당.
 */
UCLASS()
class ASTRALBREAK_API AAstralRangedWeaponActor : public AAstralWeaponActor
{
	GENERATED_BODY()

public:
	/** 발사 원점 — MuzzleSocket 미존재 시 TraceStart 소켓 폴백 */
	FVector GetMuzzleLocation() const;

	/** 변형의 투사체 — 정의(AppliedDefinition) 캐스팅으로 유도 (서버 전용, 값 미러 없음) */
	TSubclassOf<AAstralProjectile> GetProjectileClass() const;

protected:
	/** 투사체 발사 원점 소켓 (무기 메시에 배치) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Weapon|Ranged")
	FName MuzzleSocket = TEXT("Muzzle");
};
