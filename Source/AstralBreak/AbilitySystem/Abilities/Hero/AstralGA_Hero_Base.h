// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/AstralGameplayAbility.h"
#include "Combat/AstralFacingTypes.h"
#include "Combat/AstralTargetHandle.h"
#include "AstralGA_Hero_Base.generated.h"

/**
 * 히어로 전용 GA 베이스 — "히어로 전용 무언가를 아는" 바인딩 층.
 *  - 자원 바인딩: AstralHeroResourceSet(오의·표식·스태미나) 대상 헬퍼
 *  - 타게팅 바인딩: UAstralTargetingComponent(히어로 전용 컴포넌트) 조회 + Facing 전달·수신·확정 세션
 * 기계(GE 적용·워프 타겟 수명)는 UAstralGameplayAbility, 정책(언제·어느 단계·어느 이름)은 개별 GA
 */
UCLASS()
class ASTRALBREAK_API UAstralGA_Hero_Base : public UAstralGameplayAbility
{
	GENERATED_BODY()
public:
	UAstralGA_Hero_Base(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	/** Facing 제안을 활성화 이벤트에 싣는다 — UsesFacingWarp()가 true인 GA만. 호스트·클라 공통 경로 */
	virtual bool MakeActivationEventData(const FGameplayAbilityActorInfo& ActorInfo, FGameplayEventData& OutEventData) const override;

protected:
	// 타게팅 바인딩 층

	/** 하드 락 타겟 — 없으면 빈 핸들 */
	FAstralTargetHandle ResolveEffectiveTarget() const;

	/** 아바타 → AimLocation 방향의 facing (yaw만). 스냅샷 — 호출 시점 값이며 밴드 중 재계산하지 않는다. */
	FRotator ComputeFacingToward(const FVector& AimLocation) const;

	// 역할별 방향 출처: 자율 프록시·호스트 = 자기 캡처(양자화 왕복값) / 원격 폰의 서버 인스턴스 = 승인한 TargetData만 / 시뮬 프록시 = 없음

	/** 이 GA가 Facing 워프를 쓰는가 — false면 세션 함수는 전부 no-op */
	virtual bool UsesFacingWarp() const { return false; }

	/** 단계 수 (StageIndex 범위) — 콤보는 ComboStages.Num(), 단발은 1 */
	virtual int32 GetFacingStageCount() const { return 1; }

	/**
	 * ActivateAbility에서 1회 — 세션 키 저장, Stage 0을 TriggerEventData에서 보관함에 넣고,
	 * 원격 폰의 서버 인스턴스는 Stage 1~N 수신기를 등록한다 (등록 전 도착분은 CallReplicatedTargetDataDelegatesIfSet로 회수)
	 */
	void BeginFacingSession(const FGameplayEventData* TriggerEventData);

	/**
	 * 단계 시작의 단일 확정 지점 — 몽타주 재생 요청 직전 1회. 확정 후 그 단계에서 다시 바꾸지 않는다.
	 * Warp면 SetFacingWarp, NoWarp면 자기 이름을 제거한다(이전 활성화의 잔여). 로컬은 Stage 1~N을 여기서 캡처·송신
	 */
	EAstralFacingDecision ResolveFacingForStage(int32 StageIndex, FName WarpTargetName);

	/** EndAbility에서 — 수신기 해제·GAS 캐시 소비·보관함 초기화. 늦은 콜백이 새 활성화를 건드리지 않도록 키를 대조한다 */
	void EndFacingSession();

private:
	/** 아바타 → 락온 타겟 조준점 yaw를 양자화한 제안. 타겟 없음 = None */
	FAstralFacingProposal CaptureFacingProposal(const AActor* Avatar, int32 StageIndex) const;

	/** 서버 월드 검증 (원격 폰의 서버 인스턴스만) — TargetActor 유효·자기 자신 아님·CanDamage·거리·방위. 서버 방위는 검증에만 쓴다 */
	EAstralFacingRejectReason ValidateFacingProposal(const FAstralFacingProposal& Proposal) const;

	void HandleFacingTargetDataReceived(const FGameplayAbilityTargetDataHandle& DataHandle, FGameplayTag ApplicationTag);

	/** 원격 폰의 서버 인스턴스인가 (권위 ∧ 비로컬) — 승인 경로 */
	bool IsRemoteServerInstance() const;

	void LogFacingDecision(int32 StageIndex, FName WarpTargetName, const FAstralFacingProposal* Proposal, EAstralFacingDecision Decision, EAstralFacingRejectReason Reason) const;

private:
	FAstralFacingStageInbox FacingInbox;
	FDelegateHandle FacingTargetDataDelegateHandle;
	FGameplayAbilitySpecHandle FacingSessionSpecHandle;
	FPredictionKey FacingSessionKey;
	bool bFacingSessionActive = false;

protected:
	// 자원 바인딩 층
	// GE를 어떻게 적용하는가(기계)는 베이스의 ApplySetByCallerEffect, 언제·얼마나(정책)는 개별 GA 소유

	/** 오의 수급 — GameData UltGain GE (SetByCaller.UltGain). 적중·패링 성공 등 모든 어빌리티발 수급 지점 */
	void ApplyUltGain(float Amount) const;

	/** 표식 수급 — GameData MarkGain GE (SetByCaller.MarkGain). 콤보 피니셔/패링 보상 수급 지점 */
	void ApplyMarkGain(float Amount) const;

	/** 스태미나 소모 — 양수 Drain을 받아 음수로 주입 (GameData StaminaDrain GE). 가드 피격 등 가변 소모 지점 */
	void ApplyStaminaDrain(float Amount) const;

	/**
	 * 스태미나 소모 시점(Sprint 종료 / Dodge 커밋 / 방어 종료 등)에 GameData의 RegenBlock GE를 오너에 적용
	 * 서버 권위에서만 적용 — 회복 GE의 periodic 틱 자체가 서버 실행
	 */
	void ApplyRegenBlockEffect(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) const;

protected:
	// 공유 GE 참조(RegenBlock/UltGain/MarkGain 등)는 UAstralGameData 소유 — GA에는 수치 노브만 남긴다

	/** 적중 1회(타겟 1기)당 오의 수급량 — 0이면 수급 없음. 광역 다중 적중 시 타겟 수 비례 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ult", Meta = (ClampMin = "0.0"))
	float UltGainOnHit = 0.0f;
};
