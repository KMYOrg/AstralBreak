#include "AstralGA_Hero_BasicAttack_Melee.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "Abilities/Tasks/AbilityTask_WaitInputPress.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAttackMontageValidation.h"
#include "Animation/AnimMontage.h"
#include "Animation/Notifies/AstralAnimNotifyState_GameplayEventWindow.h"
#include "AstralLogChannels.h"
#include "Combat/AstralCombatTypes.h"
#include "GameFramework/Pawn.h"

//////////////////////////////////////////////////////////////////////////
// FAstralComboStageState

void FAstralComboStageState::BeginStage()
{
	WindowPhase = EAstralComboWindowPhase::PreWindow;
	InputState = EAstralComboInputState::None;
}

bool FAstralComboStageState::OpenWindow()
{
	if (!ensureMsgf(WindowPhase == EAstralComboWindowPhase::PreWindow,
			TEXT("콤보 윈도우는 PreWindow에서만 열릴 수 있다 — 몽타주에 ComboWindowOpen 노티파이가 중복 배치됐는지 확인")))
	{
		return false;
	}

	WindowPhase = EAstralComboWindowPhase::WindowOpen;

	// 조기 도착 보류분 승격 — 변조 스팸도 여기서야 유효해지므로 "윈도우 열림 시점에 누른 것"과 동일 (타이밍 이득 0)
	if (InputState == EAstralComboInputState::DeferredUntilWindow)
	{
		InputState = EAstralComboInputState::Buffered;
	}

	return true;
}

bool FAstralComboStageState::CloseWindow()
{
	// 잔여 branch가 도착할 수 있다. 그건 상태 위반이 아니다.
	// 밴드 저작 오류 검출은 런타임 순서 추론이 아니라 ValidateComboStageMontages(데이터 검증)가 담당
	if (WindowPhase != EAstralComboWindowPhase::WindowOpen)
	{
		return false;
	}

	WindowPhase = EAstralComboWindowPhase::PostWindow;
	return true;
}

void FAstralComboStageState::ReceiveLocalInput()
{
	if (WindowPhase == EAstralComboWindowPhase::WindowOpen)
	{
		InputState = EAstralComboInputState::Buffered;
	}
}

void FAstralComboStageState::ReceiveRemoteInput()
{
	// 서버 몽타주는 클라보다 ~RTT/2 늦게 시작하므로 평시 도착은 WindowOpen 안 — Pre/Post 분기는 지터/변조 케이스
	switch (WindowPhase)
	{
	case EAstralComboWindowPhase::PreWindow:
		InputState = EAstralComboInputState::DeferredUntilWindow;
		break;

	case EAstralComboWindowPhase::WindowOpen:
	case EAstralComboWindowPhase::PostWindow:
		InputState = EAstralComboInputState::Buffered;
		break;
	}
}

bool FAstralComboStageState::ConsumeBufferedInput()
{
	if (InputState != EAstralComboInputState::Buffered)
	{
		return false;
	}

	InputState = EAstralComboInputState::None;
	return true;
}

//////////////////////////////////////////////////////////////////////////
// UAstralGA_Hero_BasicAttack_Melee

UAstralGA_Hero_BasicAttack_Melee::UAstralGA_Hero_BasicAttack_Melee(const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer)
{
    InstancingPolicy   = EGameplayAbilityInstancingPolicy::InstancedPerActor;
    NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::LocalPredicted;

    // 모드 분기 패턴 — Melee 모드일 때만 활성 (B2 원거리 GA가 같은 패턴을 미러링)
    ActivationRequiredTags.AddTag(AstralGameplayTags::State_CombatStyle_Melee);

    // 활성 시 부여 (디버그/UI 등)
    ActivationOwnedTags.AddTag(AstralGameplayTags::Ability_Attack_Basic_Melee);

    // asset tag — CancelAbilities/BlockAbilitiesWithTag 매칭 기준 (ActivationOwnedTags와 별개)
    FGameplayTagContainer AssetTags;
    AssetTags.AddTag(AstralGameplayTags::Ability_Attack_Basic_Melee);
    SetAssetTags(AssetTags);

    // 상호배타: 공격 중 다른 공격 차단 (콤보↔강화 몽타주 겹침 방지), 공격 발동 시 방어 캔슬 (최신 입력 우선)
    BlockAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Attack);
    CancelAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Defense);
}

void UAstralGA_Hero_BasicAttack_Melee::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
    Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

    if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
    {
        EndAbility(Handle, ActorInfo, ActivationInfo, true, true);
        return;
    }

    if (ComboStages.Num() == 0 || !ComboStages[0].Montage)
    {
        EndAbility(Handle, ActorInfo, ActivationInfo, true, false);
        return;
    }

#if !UE_BUILD_SHIPPING
    ValidateComboStageMontages();
#endif

    ComboIndex = 0;

    PlayComboStage(0);

    // 입력 윈도우 열림 노티파이 — 단계마다 반복 수신 (태스크는 어빌리티 수명)
    if (UAbilityTask_WaitGameplayEvent* WindowOpenTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, AstralGameplayTags::GameplayEvent_ComboWindowOpen, nullptr, false, true))
    {
        WindowOpenTask->EventReceived.AddDynamic(this, &ThisClass::OnComboWindowOpened);
        WindowOpenTask->ReadyForActivation();
    }

    // 입력 윈도우 끝(분기 시점) 노티파이 — 단계마다 반복 수신
    if (UAbilityTask_WaitGameplayEvent* BranchEventTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, AstralGameplayTags::GameplayEvent_ComboBranch, nullptr, false, true))
    {
        BranchEventTask->EventReceived.AddDynamic(this, &ThisClass::OnComboBranchReceived);
        BranchEventTask->ReadyForActivation();
    }

    // 무기 트레이스 — 밴드(Begin/End) 반복 수신·무기 해석·겹침 방어는 태스크가 소유, GA는 적중 정책만
    TraceTask = UAstralAbilityTask_AttackTraceWindows::WaitAttackTraceWindows(this, WeaponTraceRadius, AstralGameplayTags::GameplayEvent_WeaponTrace_Begin, AstralGameplayTags::GameplayEvent_WeaponTrace_End);
    if (TraceTask)
    {
        TraceTask->OnHitTarget.AddDynamic(this, &ThisClass::OnAttackTraceHit);
        TraceTask->ReadyForActivation();
    }

    // 원격 폰의 서버 인스턴스만 상시 — 로컬은 윈도우 열림(OnComboWindowOpened) 시점에 
    if (!IsLocallyControlledAvatar())
    {
        ArmComboInput();
    }
}

bool UAstralGA_Hero_BasicAttack_Melee::IsLocallyControlledAvatar() const
{
    const FGameplayAbilityActorInfo* ActorInfo = GetCurrentActorInfo();
    return ActorInfo && ActorInfo->IsLocallyControlled();
}

#if !UE_BUILD_SHIPPING
void UAstralGA_Hero_BasicAttack_Melee::ValidateComboStageMontages()
{
    if (bComboStagesValidated)
    {
        return;
    }
    bComboStagesValidated = true;

    // 워프 타겟 이름 중복 — 같은 이름이면 스테이지 경계에서 이전 타겟이 덮여 리플레이 안전성(이름 분리)이 깨진다
    TSet<FName> SeenWarpNames;

    for (int32 Index = 0; Index < ComboStages.Num(); ++Index)
    {
        const FAstralComboStageData& StageData = ComboStages[Index];
        const UAnimMontage* Montage = StageData.Montage.Get();
        if (!Montage)
        {
            continue;
        }

        if (!StageData.FacingWarpTargetName.IsNone())
        {
            bool bAlreadySeen = false;
            SeenWarpNames.Add(StageData.FacingWarpTargetName, &bAlreadySeen);
            if (bAlreadySeen)
            {
                UE_LOG(LogAstralAbilitySystem, Error, TEXT("[Combo] %s (스테이지 %d): 워프 타겟 이름 '%s'가 다른 스테이지와 중복 — 스테이지별로 고유해야 한다"),
                    *GetName(), Index, *StageData.FacingWarpTargetName.ToString());
            }
        }

        AstralAttackMontage::ValidateFacingWarpBand(Montage, StageData.FacingWarpTargetName, AstralGameplayTags::GameplayEvent_WeaponTrace_Begin,
            FString::Printf(TEXT("%s 스테이지 %d"), *GetName(), Index));

        int32 BranchBandCount = 0;

        for (const FAnimNotifyEvent& Event : Montage->Notifies)
        {
            const UAstralAnimNotifyState_GameplayEventWindow* Band = Cast<UAstralAnimNotifyState_GameplayEventWindow>(Event.NotifyStateClass);
            if (!Band || Band->GetEndEventTag() != AstralGameplayTags::GameplayEvent_ComboBranch)
            {
                continue;
            }

            ++BranchBandCount;

            // 구 CloseWindow ensure가 잡으려던 것 — branch만 있고 여는 쪽이 없는 밴드
            if (Band->GetBeginEventTag() != AstralGameplayTags::GameplayEvent_ComboWindowOpen)
            {
                UE_LOG(LogAstralAbilitySystem, Error,
                    TEXT("[Combo] %s (스테이지 %d): ComboBranch 밴드의 Begin 태그가 ComboWindowOpen이 아니다 (현재 '%s') — 윈도우가 열리지 않아 분기가 동작하지 않는다"),
                    *Montage->GetName(), Index, *Band->GetBeginEventTag().ToString());
            }
        }

        // 구 OpenWindow ensure가 잡으려던 것 — 밴드 중복 배치
        if (BranchBandCount > 1)
        {
            UE_LOG(LogAstralAbilitySystem, Error,
                TEXT("[Combo] %s (스테이지 %d): 입력 윈도우 밴드가 %d개 — 스테이지당 1개여야 한다"),
                *Montage->GetName(), Index, BranchBandCount);
        }
        else if (BranchBandCount == 0 && (Index + 1) < ComboStages.Num())
        {
            UE_LOG(LogAstralAbilitySystem, Warning,
                TEXT("[Combo] %s (스테이지 %d): 입력 윈도우 밴드가 없다 — 이 단계에서 다음 단계로 진행할 수 없다"),
                *Montage->GetName(), Index);
        }
    }
}
#endif

bool UAstralGA_Hero_BasicAttack_Melee::IsStaleStageEvent(const FGameplayEventData& EventData) const
{
    // 출처가 몽타주로 식별되지 않으면(미지정 / 노티파이가 몽타주 아닌 시퀀스에 배치된 경우) 판정하지 않는다
    const UAnimMontage* SourceMontage = Cast<UAnimMontage>(EventData.OptionalObject.Get());
    if (!SourceMontage)
    {
        return false;
    }

    if (ComboStages.IsValidIndex(ComboIndex) && ComboStages[ComboIndex].Montage.Get() == SourceMontage)
    {
        return false;
    }

    // 다른 스테이지의 몽타주로 확정될 때만 stale — 모르는 애님은 통과시킨다
    for (const FAstralComboStageData& Stage : ComboStages)
    {
        if (Stage.Montage.Get() == SourceMontage)
        {
            return true;
        }
    }

    return false;
}

void UAstralGA_Hero_BasicAttack_Melee::PlayComboStage(int32 StageIndex)
{
    if (!ComboStages.IsValidIndex(StageIndex) || !ComboStages[StageIndex].Montage)
    {
        EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, false);
        return;
    }

    // 새 스테이지 = 상태 기계 리셋 (보류분 이월 금지는 BeginStage가 보장)
    ComboStageState.BeginStage();

    // 이전 스테이지 태스크를 먼저 정리 — 새 몽타주 재생이 이전 태스크의 OnInterrupted(→EndAbility)로 이어지는 것 방지.
    // EndTask는 OnDestroy(AbilityEnded=false) 경로라 몽타주 자체는 멈추지 않고, 새 재생이 자연 블렌드로 교체한다
    if (ActiveMontageTask)
    {
        ActiveMontageTask->EndTask();
        ActiveMontageTask = nullptr;
    }

    const FAstralComboStageData& Stage = ComboStages[StageIndex];

    // 방향 보정 — 이전 스테이지 타겟은 EndAbility까지 지우지 않는다 — 스테이지 경계를 걸친 리플레이가 올바른 타겟을 찾도록 (5단계)
    InstallStageFacingWarp(Stage);

    ActiveMontageTask = UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this, NAME_None, Stage.Montage, Stage.PlayRate, NAME_None, /*bStopWhenAbilityEnds=*/true, 1.f);
    if (ActiveMontageTask)
    {
        ActiveMontageTask->OnCompleted.AddDynamic(this, &ThisClass::OnMontageCompleted);
        ActiveMontageTask->OnBlendOut.AddDynamic(this, &ThisClass::OnMontageCompleted);
        ActiveMontageTask->OnInterrupted.AddDynamic(this, &ThisClass::OnMontageInterrupted);
        ActiveMontageTask->OnCancelled.AddDynamic(this, &ThisClass::OnMontageInterrupted);
        ActiveMontageTask->ReadyForActivation();
    }
}

void UAstralGA_Hero_BasicAttack_Melee::InstallStageFacingWarp(const FAstralComboStageData& Stage)
{
    if (Stage.FacingWarpTargetName.IsNone())
    {
        return;
    }

    // 방향 소스 분기는 GA의 정책 — 락온 우선. 타겟 없음 = 워프 없음 (7단계에서 이동 입력 방향이 붙는다)
    const FAstralTargetHandle Target = ResolveEffectiveTarget();
    if (!Target.IsSet())
    {
        return;
    }

    FAstralFacingWarpCommand Command;
    Command.WarpTargetName = Stage.FacingWarpTargetName;
    Command.DesiredFacing = ComputeClampedFacing(Target.GetAimLocation(), Stage.MaxAssistYaw);
    SetFacingWarp(Command);
}

void UAstralGA_Hero_BasicAttack_Melee::ArmComboInput()
{
    if (ComboInputTask)
    {
        return;
    }

    // ASC의 AbilitySpecInputPressed가 활성 어빌리티에 InputPressed 복제 이벤트를 쏘는 경로 —
    // 로컬은 즉시, 원격 폰의 서버 인스턴스는 클라 태스크의 ServerSetReplicatedEvent RPC로 발화
    ComboInputTask = UAbilityTask_WaitInputPress::WaitInputPress(this, /*bTestAlreadyPressed=*/false);
    if (ComboInputTask)
    {
        ComboInputTask->OnPress.AddDynamic(this, &ThisClass::OnComboInputPressed);
        ComboInputTask->ReadyForActivation();
    }
}

void UAstralGA_Hero_BasicAttack_Melee::DisarmComboInput()
{
    if (ComboInputTask)
    {
        ComboInputTask->EndTask();
        ComboInputTask = nullptr;
    }
}

void UAstralGA_Hero_BasicAttack_Melee::OnComboInputPressed(float TimeWaited)
{
    ComboInputTask = nullptr; // 1회성 태스크

    // 수용/보류 판정은 상태 기계가 소유
    if (IsLocallyControlledAvatar())
    {
        ComboStageState.ReceiveLocalInput();
    }
    else
    {
        ComboStageState.ReceiveRemoteInput();

        // 서버 인스턴스는 상시 수신 유지
        ArmComboInput();
    }
}

void UAstralGA_Hero_BasicAttack_Melee::OnComboWindowOpened(FGameplayEventData EventData)
{
    if (!ComboStageState.OpenWindow())
    {
        return;
    }

    // 로컬 선입력 폐기는 별도 리셋 불필요 — 무장이 윈도우 한정 + 스테이지 시작 시 BeginStage가 전체 리셋
    if (IsLocallyControlledAvatar())
    {
        ArmComboInput();
    }
}

void UAstralGA_Hero_BasicAttack_Melee::OnComboBranchReceived(FGameplayEventData EventData)
{
    if (IsStaleStageEvent(EventData))
    {
        return;
    }

    if (!ComboStageState.CloseWindow())
    {
        return;
    }

    // 로컬: 윈도우가 닫혔으니 해제 (닫힌 구간의 입력이 서버로 새는 것 차단)
    if (IsLocallyControlledAvatar())
    {
        DisarmComboInput();
    }

    TryAdvanceCombo();
}

bool UAstralGA_Hero_BasicAttack_Melee::TryAdvanceCombo()
{
    if ((ComboIndex + 1) >= ComboStages.Num())
    {
        return false;
    }

    if (!ComboStageState.ConsumeBufferedInput())
    {
        return false;
    }

    ++ComboIndex;

    // 클라(예측)/서버(권위) 각자 다음 단계 재생 — 시뮬 프록시는 몽타주 복제로 동기화
    PlayComboStage(ComboIndex);
    return true;
}

void UAstralGA_Hero_BasicAttack_Melee::OnAttackTraceHit(const FAstralAttackTraceHit& Hit)
{
    if (!ComboStages.IsValidIndex(ComboIndex))
    {
        return;
    }

    const FAstralComboStageData& Stage = ComboStages[ComboIndex];

    if (!ApplyAttackHit(Hit, BaseDamage * Stage.DamageMultiplier))
    {
        return;
    }

    // 가한 피해 → 오의 수급 (타겟 1기당 — 태스크가 밴드 내 중복을 걸러준다)
    ApplyUltGain(UltGainOnHit);

    // 단계 데이터 기반 표식 수급 — 밴드당 1회 (첫 적중 시, WindowSerial 비교)
    if (LastMarkRewardWindow != Hit.WindowSerial && Stage.MarkGain > 0.f)
    {
        LastMarkRewardWindow = Hit.WindowSerial;
        ApplyMarkGain(Stage.MarkGain);
    }
}

void UAstralGA_Hero_BasicAttack_Melee::OnMontageCompleted()
{
    // TODO: 공격 취소 등의 행위로 인해 취소된 경우에 대한 검증 필요
    
    // 밴드 끝이 블렌드아웃과 겹치면 큐잉된 ComboBranch 이벤트가 어빌리티 종료 후 도착해 유실된다.
    // 윈도우가 열린 채 몽타주가 끝났다면 여기서 닫고 분기 기회를 한 번 더 준다
    if (ComboStageState.IsWindowOpen())
    {
        ComboStageState.CloseWindow();

        if (IsLocallyControlledAvatar())
        {
            DisarmComboInput();
        }

        if (TryAdvanceCombo())
        {
            return;
        }
    }
    // 지각 수용분 — 서버 윈도우(branch)가 닫힌 뒤 도착해 버퍼된 원격 입력의 마지막 분기 기회.
    // 클라는 자기 윈도우에서 이미 예측 진행했으므로, 서버가 여기서 따라가지 않으면 디싱크가 확정된다
    else if (!IsLocallyControlledAvatar() && TryAdvanceCombo())
    {
        return;
    }

    EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, false);
}

void UAstralGA_Hero_BasicAttack_Melee::OnMontageInterrupted()
{
    EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, true);
}

void UAstralGA_Hero_BasicAttack_Melee::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
    ComboIndex = 0;
    ComboStageState.BeginStage();
    LastMarkRewardWindow = 0;
    ActiveMontageTask = nullptr;
    ComboInputTask = nullptr;
    TraceTask = nullptr;

    // 스테이지별 워프 타겟 일괄 해제 — 이름 지정 (RemoveAllWarpTargets는 다른 시스템의 타겟까지 지운다)
    TArray<FName> WarpNames;
    for (const FAstralComboStageData& Stage : ComboStages)
    {
        if (!Stage.FacingWarpTargetName.IsNone())
        {
            WarpNames.AddUnique(Stage.FacingWarpTargetName);
        }
    }
    ClearFacingWarps(WarpNames);

    Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}
