#include "AstralGA_Hero_BasicAttack_Melee.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Effects/AstralSetByCallerGameplayTags.h"
#include "Animation/AnimMontage.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"

UAstralGA_Hero_BasicAttack_Melee::UAstralGA_Hero_BasicAttack_Melee(const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer)
{
    InstancingPolicy   = EGameplayAbilityInstancingPolicy::InstancedPerActor;
    NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::LocalPredicted;

    // 모드 분기 패턴 — Melee 모드일 때만 활성
    ActivationRequiredTags.AddTag(AstralGameplayTags::State_CombatStyle_Melee);

    // 활성 시 부여 (디버그/UI 등)
    ActivationOwnedTags.AddTag(AstralGameplayTags::Ability_Attack_Basic_Melee);
}

void UAstralGA_Hero_BasicAttack_Melee::ActivateAbility(const FGameplayAbilitySpecHandle Handle,const FGameplayAbilityActorInfo* ActorInfo,const FGameplayAbilityActivationInfo ActivationInfo,const FGameplayEventData* TriggerEventData)
{
    Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

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

    if (UAbilityTask_PlayMontageAndWait* MontageTask = UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this, NAME_None, AttackMontage, 1.f, NAME_None, false, 1.f))
    {
        MontageTask->OnCompleted.AddDynamic(this, &ThisClass::OnMontageCompleted);
        MontageTask->OnBlendOut.AddDynamic(this, &ThisClass::OnMontageCompleted);
        MontageTask->OnInterrupted.AddDynamic(this, &ThisClass::OnMontageInterrupted);
        MontageTask->OnCancelled.AddDynamic(this, &ThisClass::OnMontageInterrupted);
        MontageTask->ReadyForActivation();
    }
    if (UAbilityTask_WaitGameplayEvent* HitEventTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, AstralGameplayTags::GameplayEvent_Hit, nullptr, false, true))
    {
        HitEventTask->EventReceived.AddDynamic(this, &ThisClass::OnHitEventReceived);
        HitEventTask->ReadyForActivation();
    }
}

void UAstralGA_Hero_BasicAttack_Melee::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
    Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}

void UAstralGA_Hero_BasicAttack_Melee::OnMontageCompleted()
{
    EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, false);
}

void UAstralGA_Hero_BasicAttack_Melee::OnMontageInterrupted()
{
    EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, true, true);
}

void UAstralGA_Hero_BasicAttack_Melee::OnHitEventReceived(FGameplayEventData EventData)
{
    // 서버 측 권위만 판정 + GE 적용
    // TODO: 클라이언트 측 vfx효과를 위해 부분적 서버 권위 실행
    if (!HasAuthority(&CurrentActivationInfo))
    {
        return;
    }
    PerformHitDetection();
}

void UAstralGA_Hero_BasicAttack_Melee::PerformHitDetection()
{
    APawn* Avatar = Cast<APawn>(GetAvatarActorFromActorInfo());
    if (!Avatar)
    {
        return;
    }
    
    UWorld* World = Avatar->GetWorld();
    if (!World)
    {
        return;
    }
    
    UAbilitySystemComponent* SourceASC = GetAbilitySystemComponentFromActorInfo();
    if (!SourceASC || !DamageEffectClass)
    {
        return;
    }
    
    // Sphere Trace — 캐릭터 정면
    const FVector Forward = Avatar->GetActorForwardVector();
    const FVector Start   = Avatar->GetActorLocation() + Forward * TraceStartOffset;
    const FVector End     = Start + Forward * TraceDistance;

    TArray<FHitResult> Hits;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(BasicAttackMelee_Trace), false);
    Params.AddIgnoredActor(Avatar);
    World->SweepMultiByChannel(Hits, Start, End, FQuat::Identity,ECC_Pawn, FCollisionShape::MakeSphere(TraceRadius), Params);

    // 중복 타겟 방지
    TSet<AActor*> Damaged;
    const FGameplayTag DamageTag = AstralGameplayTags::SetByCaller_Damage;

    for (const FHitResult& Hit : Hits)
    {
        AActor* TargetActor = Hit.GetActor();
        if (!TargetActor || Damaged.Contains(TargetActor))
        {
            continue;
        }
        // 피아 필터 — Hostile만 허용 (아군/중립/사망 대상 오폭 차단)
        if (!UAstralCombatStatics::CanDamage(Avatar, TargetActor))
        {
            continue;
        }
        UAbilitySystemComponent* TargetASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(TargetActor);
        if (!TargetASC)
        {
            continue;
        }
        FGameplayEffectContextHandle Context = SourceASC->MakeEffectContext();
        // TODO: 추후 avatar를 무기로 변경
        Context.AddInstigator(Avatar, Avatar);
        Context.AddHitResult(Hit);

        FGameplayEffectSpecHandle SpecHandle = SourceASC->MakeOutgoingSpec(DamageEffectClass, GetAbilityLevel(), Context);

        if (SpecHandle.IsValid())
        {
            SpecHandle.Data->SetSetByCallerMagnitude(DamageTag, BaseDamage);
            SourceASC->ApplyGameplayEffectSpecToTarget(*SpecHandle.Data.Get(), TargetASC);
            Damaged.Add(TargetActor);

            // 가한 피해 → 오의 수급 (적중 타겟 1기당 UltGainOnHit)
            ApplyUltGain(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, UltGainOnHit);
        }
    }
}