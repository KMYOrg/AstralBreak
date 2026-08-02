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
	// 기본 구현 없음 — 파생이 자기 정의 타입으로 캐스팅해 필요한 데이터를 적용
}
