#pragma once

#include "CoreMinimal.h"
#include "Combat/AstralInputFacingTypes.h"
#include "RootMotionModifier.h"
#include "AstralRootMotionModifier_InputFacing.generated.h"

/**
 * 입력 회전 Modifier — 창 안에서 현재 move의 이동 입력 방향으로 rotation-only 보정.
 * 발견·수명은 엔진(UMotionWarpingComponent::UpdateWithContext → UAnimNotifyState_MotionWarping::OnBecomeRelevant → AddModifierFromTemplate)이 관리하고,
 * 재실행 문맥(PreviousPosition·CurrentPosition·PlayRate)도 기본 Update가 채운다. Update는 재정의하지 않는다 (필요성이 입증되기 전까지).
 * 누적 상태 없음 — 매 평가 보정된 현재 자세에서 다시 계산한다. 무입력·억제는 원본을 그대로 돌려주고 Disabled로 바꾸지 않는다 (같은 창에서 재입력 가능)
 */
UCLASS(Meta = (DisplayName = "Astral Input Facing"))
class ASTRALBREAK_API UAstralRootMotionModifier_InputFacing : public URootMotionModifier
{
	GENERATED_BODY()

public:
	UAstralRootMotionModifier_InputFacing(const FObjectInitializer& ObjectInitializer);

	//~URootMotionModifier
	virtual FTransform ProcessRootMotion(const FTransform& InRootMotion, float DeltaSeconds) override;
	//~End URootMotionModifier

	const FAstralInputFacingSettings& GetSettings() const { return Settings; }

protected:
	/** 튜닝 값 — NotifyState의 RootMotionModifier 아래에서 편집 */
	UPROPERTY(EditAnywhere, Category = "Astral|InputFacing", Meta = (ShowOnlyInnerProperties))
	FAstralInputFacingSettings Settings;
};
