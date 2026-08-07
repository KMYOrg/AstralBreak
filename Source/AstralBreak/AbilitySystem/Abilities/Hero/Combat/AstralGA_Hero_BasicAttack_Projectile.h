#pragma once

#include "CoreMinimal.h"
#include "AstralGA_Hero_BasicAttack_Ranged.h"
#include "AstralGA_Hero_BasicAttack_Projectile.generated.h"

/**
 * 투사체 발사 방식 — 무기 변형(RangedWeaponDefinition)의 ProjectileClass를 Deferred 스폰.
 * 판정·수급은 투사체(AAstralProjectile)가 명중 시점에 수행 (서버).
 * 조준·게이트·흐름은 베이스 소유 — 이 클래스는 발사 방식만 구현.
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_BasicAttack_Projectile : public UAstralGA_Hero_BasicAttack_Ranged
{
	GENERATED_BODY()

protected:
	virtual void ExecuteRangedAttack() override;
};
