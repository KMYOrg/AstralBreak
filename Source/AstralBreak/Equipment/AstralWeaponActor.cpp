#include "AstralWeaponActor.h"

#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Net/UnrealNetwork.h"

AAstralWeaponActor::AAstralWeaponActor()
{
	MeshComponent = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("MeshComponent"));
	MeshComponent->SetupAttachment(RootSceneComponent);

	// 시각 전용 — 판정은 소켓 스윕(AttackTraceWindows 태스크)이 하므로 콜리전 불필요 (폰 이동 간섭 방지)
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

void AAstralWeaponActor::HandleAttachStateChanged()
{
	// 상태별 자세값 교체 — 서버는 SetAttachState, 클라는 OnRep_AttachState 경유
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

	// 상태별 자세값 — 홀스터는 저작된 경우에만 독립값, 아니면 손 자세값 폴백 (그립 정렬).
	// MeshInfo·AttachState 어느 쪽 OnRep이 먼저 와도 멱등 — 둘 다 현재값을 읽는다
	const bool bUseHolster = (GetAttachState() == EAstralEquipmentAttachState::Holstered) && MeshInfo.bOverrideHolsterOffset;
	MeshComponent->SetRelativeTransform(bUseHolster ? MeshInfo.HolsterOffset : MeshInfo.AttachOffset);
}

FVector AAstralWeaponActor::GetTraceStartLocation() const
{
	return MeshComponent ? MeshComponent->GetSocketLocation(TraceStartSocket) : GetActorLocation();
}

FVector AAstralWeaponActor::GetTraceEndLocation() const
{
	return MeshComponent ? MeshComponent->GetSocketLocation(TraceEndSocket) : GetActorLocation();
}

