#include "AstralRangedWeaponActor.h"

#include "AstralRangedWeaponDefinition.h"
#include "Components/SkeletalMeshComponent.h"

TSubclassOf<AAstralProjectile> AAstralRangedWeaponActor::GetProjectileClass() const
{
	const UAstralRangedWeaponDefinition* RangedDef = Cast<UAstralRangedWeaponDefinition>(GetAppliedDefinition());
	return RangedDef ? RangedDef->ProjectileClass : nullptr;
}

FVector AAstralRangedWeaponActor::GetMuzzleLocation() const
{
	USkeletalMeshComponent* Mesh = GetMeshComponent();
	if (Mesh && Mesh->DoesSocketExist(MuzzleSocket))
	{
		return Mesh->GetSocketLocation(MuzzleSocket);
	}
	return GetTraceStartLocation();
}
