#include "AstralGA_Hero_BasicAttack_Melee.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "Abilities/Tasks/AbilityTask_WaitInputPress.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "Animation/AnimMontage.h"
#include "GameFramework/Pawn.h"

UAstralGA_Hero_BasicAttack_Melee::UAstralGA_Hero_BasicAttack_Melee(const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer)
{
    InstancingPolicy   = EGameplayAbilityInstancingPolicy::InstancedPerActor;
    NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::LocalPredicted;

    // 모드 분기 패턴 — Melee 모드일 때만 활성 (B2 원거리 GA가 같은 패턴을 미러링)
    ActivationRequiredTags.AddTag(AstralGameplayTags::State_CombatStyle_Melee);

    // 활성 시 부여 (디버그/UI 등)
    ActivationOwnedTags.AddTag(AstralGameplayTags::Ability_Attack_Basic_Melee);
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

    ComboIndex = 0;
    bComboWindowOpen = false;
    bComboInputBuffered = false;

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

    // 히트 노티파이 — 단계마다 반복 수신
    if (UAbilityTask_WaitGameplayEvent* HitEventTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, AstralGameplayTags::GameplayEvent_Hit, nullptr, false, true))
    {
        HitEventTask->EventReceived.AddDynamic(this, &ThisClass::OnHitEventReceived);
        HitEventTask->ReadyForActivation();
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

void UAstralGA_Hero_BasicAttack_Melee::PlayComboStage(int32 StageIndex)
{
    if (!ComboStages.IsValidIndex(StageIndex) || !ComboStages[StageIndex].Montage)
    {
        EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, false);
        return;
    }

    // 이전 스테이지 태스크를 먼저 정리 — 새 몽타주 재생이 이전 태스크의 OnInterrupted(→EndAbility)로 이어지는 것 방지.
    // EndTask는 OnDestroy(AbilityEnded=false) 경로라 몽타주 자체는 멈추지 않고, 새 재생이 자연 블렌드로 교체한다
    if (ActiveMontageTask)
    {
        ActiveMontageTask->EndTask();
        ActiveMontageTask = nullptr;
    }

    const FAstralComboStageData& Stage = ComboStages[StageIndex];

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
    const bool bLocal = IsLocallyControlledAvatar();

    ComboInputTask = nullptr; // 1회성 태스크

    // 로컬: 윈도우 게이트 적용
    // 원격 폰의 서버 인스턴스: 도착한 입력은 클라가 윈도우 안에서 검증한 것
    if (bComboWindowOpen || !bLocal)
    {
        bComboInputBuffered = true;
    }

    // 서버 인스턴스는 상시 수신 유지
    if (!bLocal)
    {
        ArmComboInput();
    }
}

void UAstralGA_Hero_BasicAttack_Melee::OnComboWindowOpened(FGameplayEventData EventData)
{
    bComboWindowOpen = true;

    if (IsLocallyControlledAvatar())
    {
        bComboInputBuffered = false;
        ArmComboInput();
    }
}

void UAstralGA_Hero_BasicAttack_Melee::OnComboBranchReceived(FGameplayEventData EventData)
{
    bComboWindowOpen = false;

    // 로컬: 윈도우가 닫혔으니 해제 (닫힌 구간의 입력이 서버로 새는 것 차단)
    if (IsLocallyControlledAvatar())
    {
        DisarmComboInput();
    }

    TryAdvanceCombo();
}

bool UAstralGA_Hero_BasicAttack_Melee::TryAdvanceCombo()
{
    if (!bComboInputBuffered || (ComboIndex + 1) >= ComboStages.Num())
    {
        return false;
    }

    ++ComboIndex;
    bComboInputBuffered = false;

    // 클라(예측)/서버(권위) 각자 다음 단계 재생 — 시뮬 프록시는 몽타주 복제로 동기화
    PlayComboStage(ComboIndex);
    return true;
}

void UAstralGA_Hero_BasicAttack_Melee::OnHitEventReceived(FGameplayEventData EventData)
{
    // 서버 측 권위만 판정 + GE 적용
    // TODO: 클라이언트 측 vfx효과를 위해 부분적 서버 권위 실행
    if (!HasAuthority(&CurrentActivationInfo))
    {
        return;
    }

    if (!ComboStages.IsValidIndex(ComboIndex))
    {
        return;
    }

    const FAstralComboStageData& Stage = ComboStages[ComboIndex];

    APawn* Avatar = Cast<APawn>(GetAvatarActorFromActorInfo());
    UAbilitySystemComponent* SourceASC = GetAbilitySystemComponentFromActorInfo();

    const float StageDamage = BaseDamage * Stage.DamageMultiplier;
    const int32 NumTargetsHit = UAstralCombatStatics::ApplyDamageSweep(SourceASC, Avatar, DamageEffectClass, StageDamage, TraceStartOffset, TraceDistance, TraceRadius, GetAbilityLevel());
    if (NumTargetsHit > 0)
    {
        // 가한 피해 → 오의 수급 (적중 타겟 수 비례)
        ApplyUltGain(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, UltGainOnHit * NumTargetsHit);

        // 단계 데이터 기반 표식 수급 (적중 여부당 1회 — 보통 피니셔 단계에만 설정)
        ApplyMarkGain(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, Stage.MarkGain);
    }
}

void UAstralGA_Hero_BasicAttack_Melee::OnMontageCompleted()
{
    // 밴드 끝이 블렌드아웃과 겹치면 큐잉된 ComboBranch 이벤트가 어빌리티 종료 후 도착해 유실된다.
    // 윈도우가 열린 채 몽타주가 끝났다면 여기서 분기 기회를 한 번 더 준다 (밴드 배치에 강건하게)
    if (bComboWindowOpen)
    {
        bComboWindowOpen = false;

        if (IsLocallyControlledAvatar())
        {
            DisarmComboInput();
        }

        if (TryAdvanceCombo())
        {
            return;
        }
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
    bComboWindowOpen = false;
    bComboInputBuffered = false;
    ActiveMontageTask = nullptr;
    ComboInputTask = nullptr;

    Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}
