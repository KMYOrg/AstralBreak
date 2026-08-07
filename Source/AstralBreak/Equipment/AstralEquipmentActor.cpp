#include "AstralEquipmentActor.h"

#include "Components/SceneComponent.h"

AAstralEquipmentActor::AAstralEquipmentActor()
{
	PrimaryActorTick.bCanEverTick = false;

	bReplicates = true;

	RootSceneComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(RootSceneComponent);
}

void AAstralEquipmentActor::OnEquipmentDataApplied_Implementation(const UAstralItemDefinition* Definition)
{
	// 정의 원본 캐시 — 파생은 값을 미러링하지 말고 GetAppliedDefinition() 캐스팅으로 읽는다
	AppliedDefinition = Definition;
}
