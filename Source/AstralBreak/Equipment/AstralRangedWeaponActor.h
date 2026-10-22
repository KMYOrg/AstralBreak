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

	/**
	 * 총구 소켓(+X = 총열)을 부착된 캐릭터 메시의 ReferenceBone 공간으로 환산 — 손(Held)에 붙어 있고 MuzzleSocket 이 있을 때만 true.
	 * 무기는 손 본에 붙은 강체라 자세와 무관한 상수 — 장비 매니저가 부착·외형이 바뀔 때 AnimInstance 에 넣고, 최종 조준 보정이 이 축을 조준점으로 돌린다
	 */
	bool GetMuzzleInReferenceBone(FName ReferenceBone, FTransform& OutMuzzle) const { return GetSocketInReferenceBone(MuzzleSocket, ReferenceBone, OutMuzzle); }

	/** 변형의 투사체 — 정의(AppliedDefinition) 캐스팅으로 유도 (서버 전용, 값 미러 없음) */
	TSubclassOf<AAstralProjectile> GetProjectileClass() const;

protected:
	/** 투사체 발사 원점 소켓 (무기 메시에 배치) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Weapon|Ranged")
	FName MuzzleSocket = TEXT("Muzzle");
};
