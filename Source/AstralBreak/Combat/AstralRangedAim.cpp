#include "AstralRangedAim.h"

#include "Engine/World.h"
#include "GameFramework/Controller.h"

bool AstralRangedAim::ComputeCameraAimPoint(const AController* Controller, const AActor* Avatar, const AActor* IgnoreActor, const FVector& MuzzleLocation, float TraceRange, FCameraAimPoint& Out)
{
	if (!Controller)
	{
		return false;
	}

	FVector CameraLocation;
	FRotator CameraRotation;
	Controller->GetPlayerViewPoint(CameraLocation, CameraRotation);
	return ComputeAimPointAlongView(CameraLocation, CameraRotation.Vector(), Avatar, IgnoreActor, MuzzleLocation, TraceRange, Out);
}

bool AstralRangedAim::ComputeAimPointAlongView(const FVector& ViewLocation, const FVector& ViewDirection, const AActor* Avatar, const AActor* IgnoreActor, const FVector& MuzzleLocation, float TraceRange, FCameraAimPoint& Out)
{
	const UWorld* World = Avatar ? Avatar->GetWorld() : nullptr;
	Out.Direction = ViewDirection.GetSafeNormal();
	if (!World || Out.Direction.IsZero())
	{
		return false;
	}

	// 트레이스 시작 = 카메라 레이 위 총구 투영점 — 카메라~캐릭터 사이(등 뒤) 오브젝트 오폭 방지
	const float MuzzleProjection = FMath::Max(FVector::DotProduct(MuzzleLocation - ViewLocation, Out.Direction), 0.f);
	Out.TraceStart = ViewLocation + Out.Direction * MuzzleProjection;
	const FVector TraceEnd = Out.TraceStart + Out.Direction * TraceRange;
	Out.TargetPoint = TraceEnd;

	FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(AstralRangedAim), /*bTraceComplex=*/false, Avatar);
	if (IgnoreActor)
	{
		QueryParams.AddIgnoredActor(IgnoreActor);
	}

	FHitResult AimHit;
	if (World->LineTraceSingleByChannel(AimHit, Out.TraceStart, TraceEnd, ECC_Visibility, QueryParams))
	{
		Out.TargetPoint = AimHit.ImpactPoint;
	}

	// 조준점이 총구 뒤/측면(극근접 지형 등)이면 카메라 레이 방향의 원거리 지점으로 보정 — 발사선의 전방 보장
	if (FVector::DotProduct((Out.TargetPoint - MuzzleLocation).GetSafeNormal(), Out.Direction) <= 0.f)
	{
		Out.TargetPoint = MuzzleLocation + Out.Direction * TraceRange;
	}
	return true;
}
