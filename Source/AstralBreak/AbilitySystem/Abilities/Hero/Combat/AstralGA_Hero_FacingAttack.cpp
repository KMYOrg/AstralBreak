#include "AstralGA_Hero_FacingAttack.h"

#include "AbilitySystem/Facing/AstralFacingDebug.h"
#include "AbilitySystem/Facing/AstralFacingSession.h"
#include "Combat/AstralCombatTypes.h"

UAstralGA_Hero_FacingAttack::UAstralGA_Hero_FacingAttack(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

EAstralInputActivationPreparation UAstralGA_Hero_FacingAttack::MakeActivationEventData(const FGameplayAbilityActorInfo& ActorInfo, FGameplayEventData& OutEventData) const
{
	const AActor* Avatar = ActorInfo.AvatarActor.Get();
	if (!Avatar)
	{
		return EAstralInputActivationPreparation::Failed;
	}

	OutEventData.Instigator = Avatar;
	OutEventData.Target = Avatar;

	// 디버그 — Stage 0 송신 생략: 이벤트 경로는 유지하되 페이로드만 비운다
	if (!AstralFacingDebug::ShouldDropSend(0))
	{
		OutEventData.TargetData = FGameplayAbilityTargetData_AstralFacing::MakeHandle(CaptureFacingProposal(Avatar, 0));
		ASTRAL_FACING_STAT(Prepared);
	}
	return EAstralInputActivationPreparation::WithEventData;
}

void UAstralGA_Hero_FacingAttack::BeginFacing(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	BeginFacingSession(Handle, ActorInfo, ActivationInfo, TriggerEventData);
	ApplyFacingResolution(FacingSession->AdvanceStage(0, TOptional<FAstralFacingProposal>()));
}

void UAstralGA_Hero_FacingAttack::BeginFacingSession(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	constexpr int32 NumStages = 1;
	const FAstralFacingSessionContext Context = FAstralFacingSessionContext::FromActorInfo(*ActorInfo, Handle, ActivationInfo, NumStages);

	TOptional<FAstralFacingProposal> StageZero;
	FAstralFacingProposal Extracted;
	if (TriggerEventData && FGameplayAbilityTargetData_AstralFacing::ExtractProposal(TriggerEventData->TargetData, NumStages, Extracted))
	{
		StageZero = Extracted;
	}
	else if (Context.Role != EAstralFacingSessionRole::RemoteServer)
	{
		// 로컬 폴백 — 이벤트 경로 밖의 활성화. 원격 서버는 폴백하지 않는다 (승인 스냅샷만)
		StageZero = CaptureFacingProposal(ActorInfo->AvatarActor.Get(), 0);
	}

	FacingSession = NewObject<UAstralFacingSession>(this);
	FacingSession->Begin(Context, StageZero);
}

void UAstralGA_Hero_FacingAttack::ApplyFacingResolution(const FAstralFacingStageResolution& Resolution)
{
	// Set 또는 Clear 정확히 하나 — 이름이 비어도 Clear로 Facing 소유 없음을 전달한다 (입력 회전 소유권 슬롯)
	if (!FacingWarpTargetName.IsNone() && Resolution.ShouldWarp())
	{
		FAstralFacingWarpCommand Command;
		Command.WarpTargetName = FacingWarpTargetName;
		Command.DesiredFacing = FRotator(0.f, Resolution.GetWarpYaw(), 0.f);
		SetFacingWarp(Command);
	}
	else
	{
		ClearFacingWarp(FacingWarpTargetName);
	}

	AstralFacingDebug::LogStageDecision(this, FacingSession, Resolution, FacingWarpTargetName);
}

void UAstralGA_Hero_FacingAttack::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	// 이 활성화의 세션만 종료 — 키 불일치는 정상 경로가 아니다 (엔진이 대조해 넘긴다). 관측용 ensure
	if (FacingSession)
	{
		if (FacingSession->MatchesActivation(Handle, ActivationInfo.GetActivationPredictionKey()))
		{
			FacingSession->End();
			FacingSession = nullptr;
		}
		else
		{
			ensureMsgf(false, TEXT("[Facing] %s: EndAbility 활성화 키 불일치 (Key=%d, Session=%d) — 세션 유지"),
				*GetName(), ActivationInfo.GetActivationPredictionKey().Current, FacingSession->GetActivationKey().Current);
		}
	}

	// 워프 타겟 해제 — 이름 지정 (다른 시스템의 타겟은 건드리지 않는다)
	ClearFacingWarp(FacingWarpTargetName);

	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}
