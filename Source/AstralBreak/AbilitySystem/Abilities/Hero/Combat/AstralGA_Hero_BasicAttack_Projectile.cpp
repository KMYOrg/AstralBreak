#include "AstralGA_Hero_BasicAttack_Projectile.h"

#include "Combat/AstralProjectile.h"
#include "Engine/World.h"
#include "Equipment/AstralRangedWeaponActor.h"
#include "GameFramework/Pawn.h"

void UAstralGA_Hero_BasicAttack_Projectile::ExecuteRangedAttack()
{
	// 무기 미장착 / 원거리 무기가 아님 / 투사체 미지정 변형 — 발사 없음
	AAstralRangedWeaponActor* WeaponActor = GetRangedWeaponActor();
	const TSubclassOf<AAstralProjectile> ProjectileClass = WeaponActor ? WeaponActor->GetProjectileClass() : nullptr;
	if (!ProjectileClass)
	{
		return;
	}

	FVector MuzzleLocation;
	FVector TargetPoint;
	if (!ComputeAimTarget(WeaponActor, MuzzleLocation, TargetPoint))
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

	const FVector FireDirection = (TargetPoint - MuzzleLocation).GetSafeNormal();
	if (FireDirection.IsNearlyZero())
	{
		return;
	}

	// Deferred 스폰 — 페이로드 주입 후 FinishSpawning (초기 번치 원자성 계약)
	const FTransform SpawnTransform(FireDirection.Rotation(), MuzzleLocation);
	AAstralProjectile* Projectile = World->SpawnActorDeferred<AAstralProjectile>(ProjectileClass, SpawnTransform, AvatarPawn, AvatarPawn, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	if (!Projectile)
	{
		return;
	}

	// UltGainOnHit은 베이스 노브 재사용 (근접은 트레이스 적중당, 원거리는 투사체 명중당 — 동일 의미)
	Projectile->InitializeProjectile(GetAbilitySystemComponentFromActorInfo(), Avatar, WeaponActor, BaseDamage, MarkGainOnHit, UltGainOnHit);
	Projectile->FinishSpawning(SpawnTransform);
}
