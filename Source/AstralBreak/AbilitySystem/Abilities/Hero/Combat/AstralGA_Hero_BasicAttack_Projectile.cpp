#include "AstralGA_Hero_BasicAttack_Projectile.h"

#include "Combat/AstralProjectile.h"
#include "Engine/World.h"
#include "Equipment/AstralRangedWeaponActor.h"
#include "GameFramework/Pawn.h"

void UAstralGA_Hero_BasicAttack_Projectile::ExecuteRangedAttack(const FAstralRangedShot& Shot)
{
	// 무기 미장착 / 원거리 무기가 아님 / 투사체 미지정 변형 — 발사 없음
	AAstralRangedWeaponActor* WeaponActor = GetRangedWeaponActor();
	const TSubclassOf<AAstralProjectile> ProjectileClass = WeaponActor ? WeaponActor->GetProjectileClass() : nullptr;
	if (!ProjectileClass)
	{
		return;
	}

	AActor* Avatar = GetAvatarActorFromActorInfo();
	APawn* AvatarPawn = Cast<APawn>(Avatar);
	UWorld* World = Avatar ? Avatar->GetWorld() : nullptr;
	if (!AvatarPawn || !World)
	{
		return;
	}

	// Shot은 베이스가 확정한 값 — 여기서 조준을 다시 계산하지 않는다
	const FTransform SpawnTransform(Shot.FireDirection.Rotation(), Shot.MuzzleLocation);

	// Deferred 스폰 — 페이로드 주입 후 FinishSpawning (초기 번치 원자성 계약). 총구 여유는 베이스가 이미 검사 완료
	AAstralProjectile* Projectile = World->SpawnActorDeferred<AAstralProjectile>(ProjectileClass, SpawnTransform, AvatarPawn, AvatarPawn, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	if (!Projectile)
	{
		return;
	}

	// UltGainOnHit은 베이스 노브 재사용 (근접은 트레이스 적중당, 원거리는 투사체 명중당 — 동일 의미)
	Projectile->InitializeProjectile(GetAbilitySystemComponentFromActorInfo(), Avatar, WeaponActor, BaseDamage, MarkGainOnHit, UltGainOnHit);
	Projectile->FinishSpawning(SpawnTransform);
}

TOptional<FAstralMuzzleClearance> UAstralGA_Hero_BasicAttack_Projectile::GetMuzzleClearance() const
{
	const AAstralRangedWeaponActor* WeaponActor = GetRangedWeaponActor();
	const TSubclassOf<AAstralProjectile> ProjectileClass = WeaponActor ? WeaponActor->GetProjectileClass() : nullptr;
	const AAstralProjectile* ProjectileCDO = ProjectileClass ? ProjectileClass->GetDefaultObject<AAstralProjectile>() : nullptr;
	if (!ProjectileCDO)
	{
		return TOptional<FAstralMuzzleClearance>();
	}

	FAstralMuzzleClearance Clearance;
	Clearance.Radius = ProjectileCDO->GetCollisionRadius();
	Clearance.Blockers = ProjectileCDO->GetBlockingObjectTypes();
	return Clearance;
}
