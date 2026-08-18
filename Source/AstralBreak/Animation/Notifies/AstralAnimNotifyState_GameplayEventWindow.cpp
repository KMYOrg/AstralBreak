#include "AstralAnimNotifyState_GameplayEventWindow.h"

#include "AbilitySystemBlueprintLibrary.h"

UAstralAnimNotifyState_GameplayEventWindow::UAstralAnimNotifyState_GameplayEventWindow(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
#if WITH_EDITORONLY_DATA
	bShouldFireInEditor = false;
#endif
	// 브랜칭 포인트가 아닌 일반(큐잉) 노티파이 — 몽타주 틱 "도중"이 아니라 업데이트 종료 후 안전 시점에 발화.
	// 이 이벤트 핸들러(콤보 분기)가 새 몽타주를 재생하므로, 브랜칭 포인트로 두면 몽타주 틱 재진입으로 Montage_Play가 실패한다
	bIsNativeBranchingPoint = false;
}

void UAstralAnimNotifyState_GameplayEventWindow::NotifyBegin(USkeletalMeshComponent* MeshComp, UAnimSequenceBase* Animation, float TotalDuration, const FAnimNotifyEventReference& EventReference)
{
	Super::NotifyBegin(MeshComp, Animation, TotalDuration, EventReference);

	if (MeshComp && BeginEventTag.IsValid())
	{
		UAbilitySystemBlueprintLibrary::SendGameplayEventToActor(MeshComp->GetOwner(), BeginEventTag, EventData);
	}
}

void UAstralAnimNotifyState_GameplayEventWindow::NotifyEnd(USkeletalMeshComponent* MeshComp, UAnimSequenceBase* Animation, const FAnimNotifyEventReference& EventReference)
{
	Super::NotifyEnd(MeshComp, Animation, EventReference);

	if (MeshComp && EndEventTag.IsValid())
	{
		UAbilitySystemBlueprintLibrary::SendGameplayEventToActor(MeshComp->GetOwner(), EndEventTag, EventData);
	}
}
