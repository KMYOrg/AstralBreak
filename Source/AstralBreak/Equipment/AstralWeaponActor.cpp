#include "AstralWeaponActor.h"

#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Net/UnrealNetwork.h"

AAstralWeaponActor::AAstralWeaponActor()
{
	MeshComponent = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("MeshComponent"));
	MeshComponent->SetupAttachment(RootSceneComponent);

	// 시각 전용 — 판정은 소켓 스윕(WeaponTrace 태스크)이 하므로 콜리전 불필요 (폰 이동 간섭 방지)
	MeshComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	MeshComponent->SetGenerateOverlapEvents(false);
}

void AAstralWeaponActor::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AAstralWeaponActor, MeshInfo);
}

void AAstralWeaponActor::BeginPlay()
{
	Super::BeginPlay();

	// 초기 번치에 MeshInfo가 동봉되어 도착한 경우의 안전망 — 이후 변경은 OnRep이 처리
	ApplyMeshInfo();
}

void AAstralWeaponActor::OnEquipmentDataApplied_Implementation(const UAstralItemDefinition* Definition)
{
	Super::OnEquipmentDataApplied_Implementation(Definition);

	if (const UAstralWeaponDefinition* WeaponDef = Cast<UAstralWeaponDefinition>(Definition))
	{
		SetMeshInfo(WeaponDef->MeshInfo);
	}
}

void AAstralWeaponActor::SetMeshInfo(const FAstralWeaponMeshInfo& InMeshInfo)
{
	MeshInfo = InMeshInfo;
	ApplyMeshInfo();
}

void AAstralWeaponActor::OnRep_MeshInfo()
{
	ApplyMeshInfo();
}

void AAstralWeaponActor::ApplyMeshInfo()
{
	if (!MeshComponent)
	{
		return;
	}

	if (!MeshInfo.Mesh.IsNull())
	{
		MeshComponent->SetSkeletalMesh(MeshInfo.Mesh.LoadSynchronous());
	}
	// 피벗 보정 — 액터 부착 자세(계열 AttachTransform)와 독립
	MeshComponent->SetRelativeTransform(MeshInfo.MeshOffset);
}

FVector AAstralWeaponActor::GetTraceStartLocation() const
{
	return MeshComponent ? MeshComponent->GetSocketLocation(TraceStartSocket) : GetActorLocation();
}

FVector AAstralWeaponActor::GetTraceEndLocation() const
{
	return MeshComponent ? MeshComponent->GetSocketLocation(TraceEndSocket) : GetActorLocation();
}
