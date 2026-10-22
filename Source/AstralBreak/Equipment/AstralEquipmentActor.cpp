#include "AstralEquipmentActor.h"

#include "AstralEquipmentManagerComponent.h"
#include "Components/SceneComponent.h"
#include "Net/UnrealNetwork.h"

AAstralEquipmentActor::AAstralEquipmentActor()
{
	PrimaryActorTick.bCanEverTick = false;

	bReplicates = true;

	RootSceneComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(RootSceneComponent);
}

void AAstralEquipmentActor::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AAstralEquipmentActor, AttachState);
}

void AAstralEquipmentActor::OnEquipmentDataApplied_Implementation(const UAstralItemDefinition* Definition)
{
	// 정의 원본 캐시 — 파생은 값을 미러링하지 말고 GetAppliedDefinition() 캐스팅으로 읽는다
	AppliedDefinition = Definition;
}

void AAstralEquipmentActor::SetAttachState(EAstralEquipmentAttachState InState)
{
	if (!HasAuthority() || AttachState == InState)
	{
		return;
	}

	AttachState = InState;
	HandleAttachStateChanged();
}

void AAstralEquipmentActor::OnRep_AttachState()
{
	HandleAttachStateChanged();
}

void AAstralEquipmentActor::OnRep_AttachmentReplication()
{
	Super::OnRep_AttachmentReplication();

	// 클라 — 부착(소켓)은 AttachState 와 따로 복제된다
	NotifyPresentationChanged();
}

void AAstralEquipmentActor::NotifyPresentationChanged() const
{
	// 아직 붙지 않았으면(클라 부착 복제 전) 건너뛴다 — 부착 복제가 다시 부른다
	if (UAstralEquipmentManagerComponent* Manager = UAstralEquipmentManagerComponent::FindEquipmentManager(GetAttachParentActor()))
	{
		Manager->RefreshWeaponAnimData();
	}
}
