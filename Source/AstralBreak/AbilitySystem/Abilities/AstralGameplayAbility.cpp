#include "AstralGameplayAbility.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Tasks/AstralAbilityTask_AttackTraceWindows.h"
#include "AstralLogChannels.h"
#include "Character/AstralCharacter.h"
#include "Combat/AstralCombatTypes.h"
#include "MotionWarpingComponent.h"
#include "Player/AstralPlayerController.h"
#include "System/AstralGameData.h"

namespace
{
	UMotionWarpingComponent* FindMotionWarpingComponent(const FGameplayAbilityActorInfo* ActorInfo)
	{
		const AActor* Avatar = ActorInfo ? ActorInfo->AvatarActor.Get() : nullptr;
		return Avatar ? Avatar->FindComponentByClass<UMotionWarpingComponent>() : nullptr;
	}
}

UAstralGameplayAbility::UAstralGameplayAbility(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	ReplicationPolicy = EGameplayAbilityReplicationPolicy::ReplicateNo;
	InstancingPolicy = EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::LocalPredicted;
	NetSecurityPolicy = EGameplayAbilityNetSecurityPolicy::ClientOrServer;

	ActivationPolicy = EAstralAbilityActivationPolicy::OnInputTriggered;

	// 사망 중 전면 차단 (부모 태그라 Dying/Dead 모두 매칭).
	// 죽어서도 써야 하는 예외(자가 부활 등)는 해당 서브클래스에서 ActivationBlockedTags.RemoveTag로 opt-out
	ActivationBlockedTags.AddTag(AstralGameplayTags::State_Death);
}

bool UAstralGameplayAbility::ApplyAttackHit(const FAstralAttackTraceHit& Hit, float Damage) const
{
	return UAstralCombatStatics::ApplyAttackHit(GetAbilitySystemComponentFromActorInfo(), GetAvatarActorFromActorInfo(), Hit.EffectCauser, Hit.HitResult, Damage, GetAbilityLevel());
}

void UAstralGameplayAbility::ApplySetByCallerEffect(const FAstralSetByCallerEffect& Effect, float Amount) const
{
	if (FMath::IsNearlyZero(Amount) || !CurrentActorInfo || !CurrentActorInfo->IsNetAuthority())
	{
		return;
	}

	const TSubclassOf<UGameplayEffect> EffectClass = Effect.Effect.LoadSynchronous();
	if (!EffectClass || !Effect.SetByCallerTag.IsValid())
	{
		return;
	}

	const FGameplayEffectSpecHandle SpecHandle = MakeOutgoingGameplayEffectSpec(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, EffectClass, GetAbilityLevel());
	if (SpecHandle.IsValid())
	{
		SpecHandle.Data->SetSetByCallerMagnitude(Effect.SetByCallerTag, Amount);
		ApplyGameplayEffectSpecToOwner(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, SpecHandle);
	}
}

void UAstralGameplayAbility::SetFacingWarp(const FAstralFacingWarpCommand& Command) const
{
	if (!CurrentActorInfo || Command.WarpTargetName.IsNone())
	{
		return;
	}

	// 4단계 게이트 — (Standalone, 리슨 호스트 캐릭터). 5단계에서 제거
	const bool bWarpAuthorized = CurrentActorInfo->IsLocallyControlled() && CurrentActorInfo->IsNetAuthority();
	if (!bWarpAuthorized)
	{
		return;
	}

	AActor* Avatar = CurrentActorInfo->AvatarActor.Get();
	UMotionWarpingComponent* MotionWarping = FindMotionWarpingComponent(CurrentActorInfo);
	if (!Avatar || !MotionWarping)
	{
		UE_LOG(LogAstralAbilitySystem, Warning, TEXT("[FacingWarp] %s: 아바타 %s에 MotionWarpingComponent 없음 — 워프 생략"), *GetNameSafe(this), *GetNameSafe(Avatar));
		return;
	}

	// 엔진은 WarpTargets를 COND_SimulatedOnly로 복제하므로 이것이 시뮬 프록시에도 전파된다 (자율 프록시 제외)
	MotionWarping->AddOrUpdateWarpTargetFromLocationAndRotation(Command.WarpTargetName, Avatar->GetActorLocation(), Command.DesiredFacing);
}

void UAstralGameplayAbility::ClearFacingWarp(FName WarpTargetName) const
{
	if (WarpTargetName.IsNone())
	{
		return;
	}

	if (UMotionWarpingComponent* MotionWarping = FindMotionWarpingComponent(CurrentActorInfo))
	{
		MotionWarping->RemoveWarpTarget(WarpTargetName);
	}
}

void UAstralGameplayAbility::ClearFacingWarps(const TArray<FName>& WarpTargetNames) const
{
	if (WarpTargetNames.Num() == 0)
	{
		return;
	}

	if (UMotionWarpingComponent* MotionWarping = FindMotionWarpingComponent(CurrentActorInfo))
	{
		MotionWarping->RemoveWarpTargets(WarpTargetNames);
	}
}

UAstralAbilitySystemComponent* UAstralGameplayAbility::GetAstralAbilitySystemComponentFromActorInfo() const
{
	return (CurrentActorInfo ? Cast<UAstralAbilitySystemComponent>(CurrentActorInfo->AbilitySystemComponent.Get()) : nullptr);
}

AAstralPlayerController* UAstralGameplayAbility::GetAstralPlayerControllerFromActorInfo() const
{
	return (CurrentActorInfo ? Cast<AAstralPlayerController>(CurrentActorInfo->PlayerController.Get()) : nullptr);
}

AController* UAstralGameplayAbility::GetControllerFromActorInfo() const
{
	if (!CurrentActorInfo)
	{
		return nullptr;
	}
	if (AController* PC = CurrentActorInfo->PlayerController.Get())
	{
		return PC;
	}
	AActor* TestActor = CurrentActorInfo->OwnerActor.Get();
	while (TestActor)
	{
		if (AController* C = Cast<AController>(TestActor))
		{
			return C;
		}
		if (APawn* P = Cast<APawn>(TestActor))
		{
			return P->GetController();
		}
		TestActor = TestActor->GetOwner();
	}
	return nullptr;
}

AAstralCharacter* UAstralGameplayAbility::GetAstralCharacterFromActorInfo() const
{
	return (CurrentActorInfo ? Cast<AAstralCharacter>(CurrentActorInfo->AvatarActor.Get()) : nullptr);
}

bool UAstralGameplayAbility::CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const
{
	if (!ActorInfo || !ActorInfo->AbilitySystemComponent.IsValid())
	{
		return false;
	}

	if (!Super::CanActivateAbility(Handle, ActorInfo, SourceTags, TargetTags, OptionalRelevantTags))
	{
		return false;
	}
	
	// TODO: ActivationGroup 시스템 도입
	
	return true;
}

void UAstralGameplayAbility::OnGiveAbility(const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilitySpec& Spec)
{
	Super::OnGiveAbility(ActorInfo, Spec);
	
	TryActivateAbilityOnSpawn(ActorInfo, Spec);
}

void UAstralGameplayAbility::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);
}

void UAstralGameplayAbility::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}

bool UAstralGameplayAbility::CheckCost(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, FGameplayTagContainer* OptionalRelevantTags) const
{
	if (!Super::CheckCost(Handle, ActorInfo, OptionalRelevantTags) || !ActorInfo)
	{
		return false;
	}
	
	// TODO: 커스텀 AdditionalCosts 조건들 추가 가능
	
	return true;
}

void UAstralGameplayAbility::ApplyCost(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) const
{
	Super::ApplyCost(Handle, ActorInfo, ActivationInfo);
	
	// TODO: 커스텀 AdditionalCosts별 ApplyCost 수행
}

void UAstralGameplayAbility::TryActivateAbilityOnSpawn(const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilitySpec& Spec) const
{
	if (ActorInfo && !Spec.IsActive() && (ActivationPolicy == EAstralAbilityActivationPolicy::OnSpawn))
	{
		UAbilitySystemComponent* ASC = ActorInfo->AbilitySystemComponent.Get();
		const AActor* AvatarActor = ActorInfo->AvatarActor.Get();

		// If avatar actor is torn off or about to die, don't try to activate until we get the new one
		if (ASC && AvatarActor && !AvatarActor->GetTearOff() && (AvatarActor->GetLifeSpan() <= 0.0f))
		{
			const bool bIsLocalExecution = (NetExecutionPolicy == EGameplayAbilityNetExecutionPolicy::LocalPredicted) || (NetExecutionPolicy == EGameplayAbilityNetExecutionPolicy::LocalOnly);
			const bool bIsServerExecution = (NetExecutionPolicy == EGameplayAbilityNetExecutionPolicy::ServerOnly) || (NetExecutionPolicy == EGameplayAbilityNetExecutionPolicy::ServerInitiated);

			const bool bClientShouldActivate = ActorInfo->IsLocallyControlled() && bIsLocalExecution;
			const bool bServerShouldActivate = ActorInfo->IsNetAuthority() && bIsServerExecution;

			if (bClientShouldActivate || bServerShouldActivate)
			{
				ASC->TryActivateAbility(Spec.Handle);
			}
		}
	}
}
