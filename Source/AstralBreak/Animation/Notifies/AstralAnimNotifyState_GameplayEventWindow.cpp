#include "AstralAnimNotifyState_GameplayEventWindow.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "Animation/AnimSequenceBase.h"
#include "Components/SkeletalMeshComponent.h"

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

	SendWindowEvent(MeshComp, Animation, BeginEventTag);
}

void UAstralAnimNotifyState_GameplayEventWindow::NotifyEnd(USkeletalMeshComponent* MeshComp, UAnimSequenceBase* Animation, const FAnimNotifyEventReference& EventReference)
{
	Super::NotifyEnd(MeshComp, Animation, EventReference);

	SendWindowEvent(MeshComp, Animation, EndEventTag);
}

void UAstralAnimNotifyState_GameplayEventWindow::SendWindowEvent(USkeletalMeshComponent* MeshComp, UAnimSequenceBase* Animation, const FGameplayTag& EventTag) const
{
	if (!MeshComp || !EventTag.IsValid())
	{
		return;
	}

	// 발신 애님을 실어 보낸다 (진단용) — 몽타주 교체 시 구 몽타주의 잔여 NotifyEnd가
	// (UAnimInstance::TriggerMontageEndedEvent) 새 스테이지에 도착하는 경로가 있어,
	// 로그에서 "어느 몽타주가 보낸 이벤트인가"를 즉시 볼 수 있어야 추적이 된다.
	FGameplayEventData Payload = EventData;
	Payload.OptionalObject = Animation;

	UAbilitySystemBlueprintLibrary::SendGameplayEventToActor(MeshComp->GetOwner(), EventTag, Payload);
}
