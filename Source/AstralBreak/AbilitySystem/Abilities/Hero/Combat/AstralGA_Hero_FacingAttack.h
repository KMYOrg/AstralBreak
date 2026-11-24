#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "AstralGA_Hero_FacingAttack.generated.h"

class UAstralFacingSession;
struct FAstralFacingStageResolution;

/**
 * 발동 때 락온 타겟 쪽으로 한 번 도는 단발 공격의 공통 층 — 강화 공격(MarkFinisher) · 오의(Ult).
 *  - 입력 활성화에 방향 제안을 싣고(MakeActivationEventData), 활성화마다 1단계짜리 UAstralFacingSession 을 만들어 확정하고, 워프 타겟을 설치 · 해제한다
 *  - 파생은 CommitAbility 뒤 · 몽타주 재생 요청 전에 BeginFacing 을 부른다. 종료는 EndAbility 가 한다 — 파생의 EndAbility 는 Super 를 부르기만 하면 된다
 *  - 락온 타겟이 없으면 돌지 않는다(제안 None). 이름을 비우면 이 층은 아무것도 설치하지 않는다
 * 콤보(단계가 여럿)와 원거리 사격(싣는 데이터가 다르다)은 이 층을 쓰지 않는다.
 */
UCLASS(Abstract)
class ASTRALBREAK_API UAstralGA_Hero_FacingAttack : public UAstralGA_Hero_Base
{
	GENERATED_BODY()

public:
	UAstralGA_Hero_FacingAttack(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

protected:
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	//~UAstralGameplayAbility — 입력 활성화에 Stage 0 Facing 제안을 싣는다. 단발이라 Stage 0뿐
	virtual EAstralInputActivationPreparation MakeActivationEventData(const FGameplayAbilityActorInfo& ActorInfo, FGameplayEventData& OutEventData) const override;
	//~End UAstralGameplayAbility

	/** 방향 확정 — 발동 시 1회 (Stage 0). 제안은 활성화 이벤트에서, 서버는 승인 후 설치. 몽타주 재생 요청보다 먼저 부른다 */
	void BeginFacing(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData);

private:
	/** 활성화마다 새 Facing 세션 (NumStages = 1) — Stage 0은 TriggerEventData에서, 로컬은 이벤트 밖 활성화에 한해 라이브 캡처 폴백 */
	void BeginFacingSession(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData);

	/** 확정 결과 → 워프 설치/제거 (FacingWarpTargetName) */
	void ApplyFacingResolution(const FAstralFacingStageResolution& Resolution);

protected:
	/** 워프 타겟 이름 — 몽타주의 MotionWarping 노티파이와 일치해야 한다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Facing")
	FName FacingWarpTargetName;

private:
	/** Facing 네트워크 세션 — 활성화마다 새 객체. EndAbility가 키를 대조해 End */
	UPROPERTY(Transient)
	TObjectPtr<UAstralFacingSession> FacingSession;
};
