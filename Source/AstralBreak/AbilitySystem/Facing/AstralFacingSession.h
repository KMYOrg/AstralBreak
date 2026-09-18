#pragma once

#include "CoreMinimal.h"
#include "Combat/AstralFacingTypes.h"
#include "GameplayAbilitySpecHandle.h"
#include "GameplayPrediction.h"
#include "UObject/Object.h"
#include "AstralFacingSession.generated.h"

class UAbilitySystemComponent;
struct FGameplayAbilityActorInfo;
struct FGameplayAbilityActivationInfo;

/** 세션 역할 — 방향 출처가 갈린다. 시뮬 프록시는 세션을 만들지 않는다 (GA 자체가 돌지 않는다) */
enum class EAstralFacingSessionRole : uint8
{
	/** 원격 클라(자율 프록시) — 자기 캡처, Stage 1~N을 서버로 송신 */
	AutonomousProxy,
	/** 리슨 호스트 · Standalone — 자기 캡처, 송신 없음 */
	LocalAuthority,
	/** 원격 폰의 서버 인스턴스 — 승인한 TargetData만. 로컬 TargetingComponent 조회 금지 */
	RemoteServer,
};

/** Begin에 넘기는 활성화 문맥 — Begin 이후 바뀌지 않는다. 공격 GA 포인터·워프 이름은 없다 */
struct FAstralFacingSessionContext
{
	TWeakObjectPtr<UAbilitySystemComponent> ASC;
	TWeakObjectPtr<AActor> Avatar;
	FGameplayAbilitySpecHandle SpecHandle;
	/** 원래 ActivationPredictionKey — TargetData 캐시·델리게이트·종료 대조의 키 */
	FPredictionKey ActivationKey;
	int32 NumStages = 0;
	EAstralFacingSessionRole Role = EAstralFacingSessionRole::LocalAuthority;

	/** ActorInfo에서 역할을 유도 — 권위 ∧ 비로컬 = RemoteServer, 권위 = LocalAuthority, 그 외 = AutonomousProxy */
	ASTRALBREAK_API static FAstralFacingSessionContext FromActorInfo(const FGameplayAbilityActorInfo& ActorInfo, FGameplayAbilitySpecHandle InSpecHandle, const FGameplayAbilityActivationInfo& ActivationInfo, int32 InNumStages);
};

/** 단계 확정 결과 — 그 단계에서 다시 바뀌지 않는다. WarpTargetName은 없다 (이름·설치는 GA 몫) */
struct FAstralFacingStageResolution
{
	int32 StageIndex = INDEX_NONE;
	EAstralFacingDecision Decision = EAstralFacingDecision::NoWarp_Missing;
	EAstralFacingRejectReason Reason = EAstralFacingRejectReason::None;
	/** Warp가 아니면 이 Yaw를 실행에 쓰지 않는다 */
	TOptional<FAstralFacingProposal> Proposal;

	bool ShouldWarp() const { return Decision == EAstralFacingDecision::Warp; }

	/** 승인된 양자화 Yaw의 복원값 — 로컬·서버가 같은 값을 쓴다. Warp일 때만 유효 */
	float GetWarpYaw() const { return Proposal.IsSet() ? AstralFacing::DequantizeYaw(Proposal->QuantizedDesiredYaw) : 0.f; }
};

/**
 * 활성화별 Facing 네트워크 세션 — 수신 구독·GAS 캐시 소비·단계 보관·후속 송신·역할별 확정.
 * 공격 GA(근접 콤보·피니셔)가 CommitAbility 뒤 활성화마다 NewObject로 만들고 EndAbility에서 End를 부른다.
 * 활성화마다 별도 객체라 늦은 콜백·늦은 종료가 새 활성화를 건드리는 문제를 구조로 막는다 (InstancedPerActor 인스턴스는 활성화 간 재사용).
 * 모르는 것: Hero 클래스 · TargetingComponent · ComboStages · MotionWarpingComponent. Tick·복제 없음
 */
UCLASS()
class ASTRALBREAK_API UAstralFacingSession : public UObject
{
	GENERATED_BODY()

public:
	/**
	 * 활성화 시작 — 문맥 고정, Stage 0을 보관함에, RemoteServer면 Stage 1~N 수신기 등록 + 등록 전 도착분 회수.
	 * StageZero 미설정 = Stage 0 미수신 (AdvanceStage(0)이 NoWarp_Missing). 두 번 부르면 false
	 */
	bool Begin(const FAstralFacingSessionContext& InContext, const TOptional<FAstralFacingProposal>& StageZero);

	/**
	 * 단계 경계에서 정확히 1회 — 전진·송신·확정을 원자적으로 소유한다 (그래서 Resolve가 아니라 Advance).
	 *  - 로컬 Stage 0: Begin에 전달한 값. LocalProposal 무시
	 *  - 로컬 Stage 1~N: LocalProposal 사용. AutonomousProxy만 서버로 송신
	 *  - RemoteServer: 보관함에서만. LocalProposal이 오면 진단 후 무시
	 * 같은 단계를 다시 부르면 이전 결과를 돌려주고 재송신·재결정하지 않는다. 워프 설치·제거·몽타주 재생은 하지 않는다
	 */
	FAstralFacingStageResolution AdvanceStage(int32 StageIndex, const TOptional<FAstralFacingProposal>& LocalProposal);

	/** 비활성 표시 → 자기 델리게이트 해제 → 자기 키 캐시 소비 → 보관함 정리. 멱등 — 종료 뒤 콜백은 아무것도 소비·설치하지 않는다 */
	void End();

	/** EndAbility가 받은 활성화가 이 세션의 것인가 — 엔진이 키를 대조해 넘기므로 불일치는 관측 대상이지 정상 경로가 아니다 */
	bool MatchesActivation(FGameplayAbilitySpecHandle Handle, const FPredictionKey& Key) const;

	bool IsActive() const { return bActive; }
	EAstralFacingSessionRole GetRole() const { return Context.Role; }
	const FPredictionKey& GetActivationKey() const { return Context.ActivationKey; }
	/** 진단 — 보관함의 현재 단계 (RemoteServer에서만 의미) */
	int32 GetInboxStage() const { return Inbox.GetCurrentStage(); }

protected:
	//~UObject
	/** 안전망 — End 없이 버려진 세션의 잔여 구독 해제. 정리를 여기에 맡기지 않는다 (EndAbility가 End를 명시적으로 부른다) */
	virtual void BeginDestroy() override;
	//~End UObject

private:
	/** Stage 1~N 송신 (AutonomousProxy) — 활성화 키로 캐시되며 서버 수신기가 같은 키로 듣는다 */
	void SendStageProposal(const FAstralFacingProposal& Proposal);

	/** RemoteServer 수신 — 저장한 ASC·키만 쓴다. 세션 활성 확인 → 핸들 복사 → 캐시 소비 → 구조 검증 → 보관함 분류 */
	void HandleTargetDataReceived(const FGameplayAbilityTargetDataHandle& DataHandle, FGameplayTag ApplicationTag);

	void UnsubscribeTargetData();

private:
	FAstralFacingSessionContext Context;
	FAstralFacingStageInbox Inbox;
	FDelegateHandle TargetDataDelegateHandle;
	bool bActive = false;

	/** 마지막 확정 — 같은 단계 중복 호출에 돌려준다 */
	FAstralFacingStageResolution LastResolution;
};
