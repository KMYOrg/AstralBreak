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
	/** 활성 → 제거/비활성 전이에서 서버 표현 샘플을 비활성으로 — 창 종료·몽타주 교체·취소를 EndNotify 발화 없이 잡는다 */
	virtual void OnStateChanged(ERootMotionModifierState LastState) override;
	//~End URootMotionModifier

	const FAstralInputFacingSettings& GetSettings() const { return Settings; }

protected:
	/**
	 * 역할별 샘플 원천 — 소유자·서버는 CMC의 현재 move 샘플(억제 = 샘플 플래그 ∨ 라이브 소유권 슬롯, 재실행은 샘플 플래그만),
	 * 시뮬 프록시는 Hero의 복제 표현 샘플(자기 창과 일치할 때만). false면 이번 평가 보정 없음
	 */
	bool ResolveSample(const AActor* Actor, const class UAstralHeroMovementComponent* HeroMC, FAstralInputFacingSample& OutSample, bool& bOutSuppressed) const;

	/** 서버(권위 인스턴스)만 — 이번 평가의 샘플·활성 여부를 Hero 표현 프로퍼티에 기록 */
	void WritePresentation(const AActor* Actor, const FAstralInputFacingSample& Sample, bool bActive) const;

protected:
	/** 튜닝 값 — NotifyState의 RootMotionModifier 아래에서 편집 */
	UPROPERTY(EditAnywhere, Category = "Astral|InputFacing", Meta = (ShowOnlyInnerProperties))
	FAstralInputFacingSettings Settings;
};
