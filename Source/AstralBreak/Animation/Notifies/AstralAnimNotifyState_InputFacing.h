#pragma once

#include "CoreMinimal.h"
#include "AnimNotifyState_MotionWarping.h"
#include "AstralAnimNotifyState_InputFacing.generated.h"

class UAstralRootMotionModifier_InputFacing;

/**
 * 입력 회전 창 — 비록온 상태에서 이 구간 동안 이동 입력 방향으로 몸을 돌린다.
 * 저작 마커일 뿐이다: Begin/End/Tick 발화에 의존하지 않고 엔진 MotionWarping이 몽타주 위치(PreviousPosition)로 발견해 Modifier를 만든다.
 * 그래서 보정 재실행에서 노티파이가 다시 불리지 않아도 동작한다.
 * 허용 여부·시간 범위는 이 노티파이의 배치가 결정한다 — 튜닝 값은 RootMotionModifier 아래에서 편집
 */
UCLASS(Meta = (DisplayName = "Astral Input Facing Window"))
class ASTRALBREAK_API UAstralAnimNotifyState_InputFacing : public UAnimNotifyState_MotionWarping
{
	GENERATED_BODY()

public:
	UAstralAnimNotifyState_InputFacing(const FObjectInitializer& ObjectInitializer);

	/** 저작 검증용 — 템플릿이 전용 타입이 아니면 null */
	const UAstralRootMotionModifier_InputFacing* GetInputFacingModifier() const;

	virtual FString GetNotifyName_Implementation() const override;
};
