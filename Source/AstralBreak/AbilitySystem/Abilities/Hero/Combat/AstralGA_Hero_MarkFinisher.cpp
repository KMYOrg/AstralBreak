#include "AstralGA_Hero_MarkFinisher.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAttackMontageValidation.h"
#include "AbilitySystem/Facing/AstralFacingDebug.h"
#include "AbilitySystem/Facing/AstralFacingSession.h"
#include "Animation/AnimMontage.h"
#include "Combat/AstralCombatTypes.h"

UAstralGA_Hero_MarkFinisher::UAstralGA_Hero_MarkFinisher(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	InstancingPolicy   = EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::LocalPredicted;

	// 모드 분기 — Melee 모드 전용 (BasicAttack과 동일 패턴)
	ActivationRequiredTags.AddTag(AstralGameplayTags::State_CombatStyle_Melee);

	ActivationOwnedTags.AddTag(AstralGameplayTags::Ability_Attack_Empowered);

	// asset tag + 상호배타 (BasicAttack과 동일 패턴)
	FGameplayTagContainer AssetTags;
	AssetTags.AddTag(AstralGameplayTags::Ability_Attack_Empowered);
	SetAssetTags(AssetTags);

	BlockAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Attack);
	CancelAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Defense);
}

void UAstralGA_Hero_MarkFinisher::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	// 비용(GE_Cost_MarkFinisher — MarkStack 소비) 게이트 + 소비. 부족하면 CheckCost가 거부
	if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, true, true);
		return;
	}

	if (!AttackMontage)
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, true, false);
		return;
	}

#if !UE_BUILD_SHIPPING
	if (!bMontageValidated)
	{
		bMontageValidated = true;
		AstralAttackMontage::ValidateFacingWarpBand(AttackMontage, FacingWarpTargetName, AstralGameplayTags::GameplayEvent_WeaponTrace_Begin, GetName());
		AstralAttackMontage::ValidatePawnCollisionBands(AttackMontage, GetName());
	}
#endif

	// 방향 확정 — 발동 시 1회 (Stage 0). 제안은 활성화 이벤트에서, 서버는 승인 후 설치 (5단계). 설치는 몽타주 재생 요청보다 먼저
	BeginFacingSession(Handle, ActorInfo, ActivationInfo, TriggerEventData);
	ApplyFacingResolution(FacingSession->AdvanceStage(0, TOptional<FAstralFacingProposal>()));

	if (UAbilityTask_PlayMontageAndWait* MontageTask = UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this, NAME_None, AttackMontage, 1.f, NAME_None, /*bStopWhenAbilityEnds=*/true, 1.f))
	{
		MontageTask->OnCompleted.AddDynamic(this, &ThisClass::OnMontageCompleted);
		MontageTask->OnBlendOut.AddDynamic(this, &ThisClass::OnMontageCompleted);
		MontageTask->OnInterrupted.AddDynamic(this, &ThisClass::OnMontageInterrupted);
		MontageTask->OnCancelled.AddDynamic(this, &ThisClass::OnMontageInterrupted);
		MontageTask->ReadyForActivation();
	}

	TraceTask = UAstralAbilityTask_AttackTraceWindows::WaitAttackTraceWindows(this, WeaponTraceRadius, AstralGameplayTags::GameplayEvent_WeaponTrace_Begin, AstralGameplayTags::GameplayEvent_WeaponTrace_End);
	if (TraceTask)
	{
		TraceTask->OnHitTarget.AddDynamic(this, &ThisClass::OnAttackTraceHit);
		TraceTask->ReadyForActivation();
	}
}

void UAstralGA_Hero_MarkFinisher::OnAttackTraceHit(const FAstralAttackTraceHit& Hit)
{
	if (ApplyAttackHit(Hit, BaseDamage))
	{
		ApplyUltGain(UltGainOnHit);
	}
}

//////////////////////////////////////////////////////////////////////////
// Facing — 초기 데이터 · 세션 소유 · 결과 적용

EAstralInputActivationPreparation UAstralGA_Hero_MarkFinisher::MakeActivationEventData(const FGameplayAbilityActorInfo& ActorInfo, FGameplayEventData& OutEventData) const
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

void UAstralGA_Hero_MarkFinisher::BeginFacingSession(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
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

void UAstralGA_Hero_MarkFinisher::ApplyFacingResolution(const FAstralFacingStageResolution& Resolution)
{
	if (!FacingWarpTargetName.IsNone())
	{
		if (Resolution.ShouldWarp())
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
	}

	AstralFacingDebug::LogStageDecision(this, FacingSession, Resolution, FacingWarpTargetName);
}

void UAstralGA_Hero_MarkFinisher::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	TraceTask = nullptr;

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

void UAstralGA_Hero_MarkFinisher::OnMontageCompleted()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, false);
}

void UAstralGA_Hero_MarkFinisher::OnMontageInterrupted()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, true);
}
