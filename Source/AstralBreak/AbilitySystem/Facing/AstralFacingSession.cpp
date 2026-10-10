#include "AstralFacingSession.h"

#include "Abilities/GameplayAbilityTypes.h"
#include "AbilitySystemComponent.h"
#include "AbilitySystem/Facing/AstralFacingDebug.h"
#include "AbilitySystem/Facing/AstralFacingValidation.h"
#include "AstralLogChannels.h"

//////////////////////////////////////////////////////////////////////////
// FAstralFacingSessionContext

FAstralFacingSessionContext FAstralFacingSessionContext::FromActorInfo(const FGameplayAbilityActorInfo& ActorInfo, FGameplayAbilitySpecHandle InSpecHandle, const FGameplayAbilityActivationInfo& ActivationInfo, int32 InNumStages)
{
	FAstralFacingSessionContext Context;
	Context.ASC = ActorInfo.AbilitySystemComponent;
	Context.Avatar = ActorInfo.AvatarActor;
	Context.SpecHandle = InSpecHandle;
	Context.ActivationKey = ActivationInfo.GetActivationPredictionKey();
	Context.NumStages = InNumStages;

	const bool bAuthority = ActorInfo.IsNetAuthority();
	const bool bLocal = ActorInfo.IsLocallyControlled();
	Context.Role = (bAuthority && !bLocal) ? EAstralFacingSessionRole::RemoteServer
	             : (bAuthority ? EAstralFacingSessionRole::LocalAuthority : EAstralFacingSessionRole::AutonomousProxy);
	return Context;
}

//////////////////////////////////////////////////////////////////////////
// UAstralFacingSession

bool UAstralFacingSession::Begin(const FAstralFacingSessionContext& InContext, const TOptional<FAstralFacingProposal>& StageZero)
{
	if (!ensureMsgf(!bActive, TEXT("[Facing] 세션 Begin 중복 — 활성화마다 새 객체를 만들어야 한다")))
	{
		return false;
	}
	if (InContext.NumStages <= 0)
	{
		return false;
	}

	Context = InContext;
	Inbox.Reset(Context.NumStages);
	LastResolution = FAstralFacingStageResolution();
	bActive = true;

	// Stage 0 — 활성화 이벤트 페이로드. 로컬도 같은 값을 읽어 서버와 같은 양자화 값을 쓴다
	if (StageZero.IsSet())
	{
		const EAstralFacingReceiveResult Result = Inbox.Receive(*StageZero);
		UE_LOG(LogAstralAbilitySystem, Verbose, TEXT("[Facing] Key=%d Stage0 from event: %s"), Context.ActivationKey.Current, AstralFacing::ToString(Result));
	}

	// 원격 폰의 서버 인스턴스 — Stage 1~N 수신기. 등록 전 도착분(활성화 직후 캐시)도 회수
	if (Context.Role == EAstralFacingSessionRole::RemoteServer)
	{
		if (UAbilitySystemComponent* ASC = Context.ASC.Get())
		{
			TargetDataDelegateHandle = ASC->AbilityTargetDataSetDelegate(Context.SpecHandle, Context.ActivationKey)
				.AddUObject(this, &ThisClass::HandleTargetDataReceived);
			ASC->CallReplicatedTargetDataDelegatesIfSet(Context.SpecHandle, Context.ActivationKey);
		}
		else
		{
			UE_LOG(LogAstralAbilitySystem, Warning, TEXT("[Facing] Key=%d RemoteServer 세션에 ASC 없음 — Stage 1~N 수신 불가"), Context.ActivationKey.Current);
		}
	}

	return true;
}

FAstralFacingStageResolution UAstralFacingSession::AdvanceStage(int32 StageIndex, const TOptional<FAstralFacingProposal>& LocalProposal)
{
	FAstralFacingStageResolution Result;
	Result.StageIndex = StageIndex;

	if (!bActive)
	{
		return Result; // NoWarp_Missing
	}

	// 한 단계에서 정확히 1회 — 중복 호출은 이전 결과. 재송신·재결정 없음
	if (StageIndex == LastResolution.StageIndex)
	{
		ASTRAL_FACING_STAT(DuplicateAdvance);
		UE_LOG(LogAstralAbilitySystem, Verbose, TEXT("[Facing] Key=%d Stage=%d AdvanceStage 중복 — 이전 결과 반환"), Context.ActivationKey.Current, StageIndex);
		return LastResolution;
	}

	TOptional<FAstralFacingProposal> Proposal;

	if (Context.Role == EAstralFacingSessionRole::RemoteServer)
	{
		// 승인 경로 — 보관함에서만
		if (LocalProposal.IsSet())
		{
			UE_LOG(LogAstralAbilitySystem, Warning, TEXT("[Facing] Key=%d Stage=%d RemoteServer에 로컬 제안이 전달됨 — 무시 (서버는 승인 스냅샷만 쓴다)"), Context.ActivationKey.Current, StageIndex);
		}
		if (!Inbox.BeginStage(StageIndex))
		{
			ASTRAL_FACING_STAT(StageMismatch);
			UE_LOG(LogAstralAbilitySystem, Warning, TEXT("[Facing] Key=%d 단계 불일치 — 보관함 %d → 요청 %d (슬롯 초기화)"), Context.ActivationKey.Current, Inbox.GetCurrentStage(), StageIndex);
		}
		Proposal = Inbox.TakeCurrent();
	}
	else if (StageIndex == 0)
	{
		// Begin에 전달한 값 — 서버와 같은 양자화 값
		Inbox.BeginStage(0);
		Proposal = Inbox.TakeCurrent();
	}
	else
	{
		// Stage 1~N — GA가 단계 시작 직전 캡처해 넘긴 값 (예약 입력 시점 캡처는 조작감을 내준다 — 채택하지 않음)
		Proposal = LocalProposal;
		if (Proposal.IsSet() && Context.Role == EAstralFacingSessionRole::AutonomousProxy)
		{
			SendStageProposal(*Proposal);
		}
	}

	// 확정 — 이 단계에서 다시 바꾸지 않는다
	Result.Proposal = Proposal;
	if (!Proposal.IsSet())
	{
		Result.Decision = EAstralFacingDecision::NoWarp_Missing;
		ASTRAL_FACING_STAT(Missing);
	}
	else if (Proposal->IsNone())
	{
		Result.Decision = EAstralFacingDecision::NoWarp_ExplicitNone;
		ASTRAL_FACING_STAT(ExplicitNone);
	}
	else
	{
		// 월드 검증은 원격 입력에만 — 호스트·자율 프록시는 자기 캡처를 그대로 쓴다
		Result.Reason = (Context.Role == EAstralFacingSessionRole::RemoteServer)
			? AstralFacingValidation::ValidateProposal(Context.Avatar.Get(), *Proposal)
			: EAstralFacingRejectReason::None;

		if (Result.Reason == EAstralFacingRejectReason::None)
		{
			// 승인이면 클라 uint16을 그대로 — 서버 clamp는 양쪽 누구도 갖지 않은 제3의 방향을 만든다
			Result.Decision = EAstralFacingDecision::Warp;
			ASTRAL_FACING_STAT(Approved);
		}
		else
		{
			Result.Decision = EAstralFacingDecision::NoWarp_Rejected;
			ASTRAL_FACING_STAT(Rejected);
		}
	}

	LastResolution = Result;
	return Result;
}

void UAstralFacingSession::SendStageProposal(const FAstralFacingProposal& Proposal)
{
	UAbilitySystemComponent* ASC = Context.ASC.Get();
	if (!ASC || AstralFacingDebug::ShouldDropSend(Proposal.StageIndex))
	{
		return;
	}

	const FGameplayAbilityTargetDataHandle SendHandle = FGameplayAbilityTargetData_AstralFacing::MakeHandle(Proposal);
	FScopedPredictionWindow ScopedPrediction(ASC);
	ASC->CallServerSetReplicatedTargetData(Context.SpecHandle, Context.ActivationKey, SendHandle, FGameplayTag(), ASC->ScopedPredictionKey);
	ASTRAL_FACING_STAT(TargetDataSendAttempts);

	if (AstralFacingDebug::ShouldDuplicateSend())
	{
		ASC->CallServerSetReplicatedTargetData(Context.SpecHandle, Context.ActivationKey, SendHandle, FGameplayTag(), ASC->ScopedPredictionKey);
		ASTRAL_FACING_STAT(TargetDataSendAttempts);
	}
}

void UAstralFacingSession::HandleTargetDataReceived(const FGameplayAbilityTargetDataHandle& DataHandle, FGameplayTag ApplicationTag)
{
	// 핸들을 먼저 로컬 복사 — 캐시 소비 후에도 데이터를 쓸 수 있게
	const FGameplayAbilityTargetDataHandle LocalHandle = DataHandle;
	if (UAbilitySystemComponent* ASC = Context.ASC.Get())
	{
		ASC->ConsumeClientReplicatedTargetData(Context.SpecHandle, Context.ActivationKey);
	}

	ASTRAL_FACING_STAT(Received);

	if (!bActive)
	{
		ASTRAL_FACING_STAT(AfterSession);
		UE_LOG(LogAstralAbilitySystem, Verbose, TEXT("[Facing] Key=%d 세션 종료 후 수신 — 폐기"), Context.ActivationKey.Current);
		return;
	}

	FAstralFacingProposal Proposal;
	if (!FGameplayAbilityTargetData_AstralFacing::ExtractProposal(LocalHandle, Context.NumStages, Proposal))
	{
		ASTRAL_FACING_STAT(Rejected);
		UE_LOG(LogAstralAbilitySystem, Warning, TEXT("[Facing] Key=%d 구조 검증 실패 (payload=%d) — 폐기"), Context.ActivationKey.Current, LocalHandle.Num());
		return;
	}

	const EAstralFacingReceiveResult Result = Inbox.Receive(Proposal);
	switch (Result)
	{
	case EAstralFacingReceiveResult::StoredNext:       ASTRAL_FACING_STAT(StoredEarly); break;
	case EAstralFacingReceiveResult::DuplicateIgnored: ASTRAL_FACING_STAT(Duplicate); break;
	case EAstralFacingReceiveResult::ConflictIgnored:  ASTRAL_FACING_STAT(Conflict); break;
	default: break;
	}

	UE_LOG(LogAstralAbilitySystem, Log, TEXT("[Facing] Role=Server Key=%d Stage=%d Source=%s Yaw=%u ServerStage=%d Receive=%s"),
		Context.ActivationKey.Current, Proposal.StageIndex, AstralFacing::ToString(Proposal.Source), Proposal.QuantizedDesiredYaw,
		Inbox.GetCurrentStage(), AstralFacing::ToString(Result));
}

void UAstralFacingSession::End()
{
	if (!bActive)
	{
		return;
	}
	bActive = false;

	UnsubscribeTargetData();

	// 이 활성화의 pending/캐시 소비 — 다음 활성화가 이전 키 데이터를 보지 않도록. 다른 키는 건드리지 않는다
	if (UAbilitySystemComponent* ASC = Context.ASC.Get())
	{
		ASC->ConsumeClientReplicatedTargetData(Context.SpecHandle, Context.ActivationKey);
	}

	Inbox.Reset(0);
}

void UAstralFacingSession::UnsubscribeTargetData()
{
	if (!TargetDataDelegateHandle.IsValid())
	{
		return;
	}
	if (UAbilitySystemComponent* ASC = Context.ASC.Get())
	{
		ASC->AbilityTargetDataSetDelegate(Context.SpecHandle, Context.ActivationKey).Remove(TargetDataDelegateHandle);
	}
	TargetDataDelegateHandle.Reset();
}

bool UAstralFacingSession::MatchesActivation(FGameplayAbilitySpecHandle Handle, const FPredictionKey& Key) const
{
	return Context.SpecHandle == Handle && Context.ActivationKey == Key;
}

void UAstralFacingSession::BeginDestroy()
{
	// End 없이 버려진 경우의 안전망 — ASC가 아직 살아 있으면 잔여 구독만 해제
	bActive = false;
	UnsubscribeTargetData();

	Super::BeginDestroy();
}
