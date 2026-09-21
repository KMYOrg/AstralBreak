#pragma once

#include "CoreMinimal.h"
#include "AstralGA_Hero_BasicAttack_Ranged.h"
#include "AstralGA_Hero_BasicAttack_Projectile.generated.h"

/**
 * 투사체 발사 방식 — 무기 변형(RangedWeaponDefinition)의 ProjectileClass를 Deferred 스폰.
 * 판정·수급은 투사체(AAstralProjectile)가 명중 시점에 수행 (서버).
 * 조준·게이트·흐름·발사선 확정은 베이스 소유 — 이 클래스는 확정된 Shot으로 생성만 한다 (타겟·카메라를 다시 조회하지 않는다).
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_BasicAttack_Projectile : public UAstralGA_Hero_BasicAttack_Ranged
{
	GENERATED_BODY()

protected:
	//~UAstralGA_Hero_BasicAttack_Ranged
	virtual void ExecuteRangedAttack(const FAstralRangedShot& Shot) override;
	/** 투사체 CDO의 판정 스피어 반경·Block 오브젝트 타입 — 검사 형상과 스폰 형상을 같은 출처에서 */
	virtual TOptional<FAstralMuzzleClearance> GetMuzzleClearance() const override;
	//~End UAstralGA_Hero_BasicAttack_Ranged
};
