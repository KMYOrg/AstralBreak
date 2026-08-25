#include "AstralGA_Hero_Dodge.h"

#include "Abilities/Tasks/AbilityTask_ApplyRootMotionConstantForce.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Animation/AnimMontage.h"
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralCharacterMovementComponent.h"
#include "GameFramework/CharacterMovementComponent.h"

UAstralGA_Hero_Dodge::UAstralGA_Hero_Dodge(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	
}

bool UAstralGA_Hero_Dodge::CanActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayTagContainer* SourceTags, const FGameplayTagContainer* TargetTags, FGameplayTagContainer* OptionalRelevantTags) const
{
	if (!ActorInfo || !ActorInfo->AvatarActor.IsValid())
	{
		return false;
	}

	// 지상 전용 — 공중 회피는 추후 재검토
	const AAstralCharacter* Character = Cast<AAstralCharacter>(ActorInfo->AvatarActor.Get());
	const UCharacterMovementComponent* CMC = Character ? Character->GetCharacterMovement() : nullptr;
	if (!CMC || !CMC->IsMovingOnGround())
	{
		return false;
	}

	return Super::CanActivateAbility(Handle, ActorInfo, SourceTags, TargetTags, OptionalRelevantTags);
}

void UAstralGA_Hero_Dodge::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	// 비용(GE_Cost_Dodge) 게이트 + 소비 — CheckCost/ApplyCost 표준 경로
	if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
		return;
	}

	ApplyRegenBlockEffect(Handle, ActorInfo, ActivationInfo);

	const AAstralCharacter* Character = GetAstralCharacterFromActorInfo();
	const UCharacterMovementComponent* CMC = Character ? Character->GetCharacterMovement() : nullptr;
	if (!CMC)
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
		return;
	}

	// 대시 방향: 이동 입력(가속도) 방향, 없으면 백스텝(-Forward) 또는 전방
	FVector Direction = CMC->GetCurrentAcceleration();
	Direction.Z = 0.0f;
	if (!Direction.Normalize())
	{
		Direction = bDodgeBackwardWhenIdle ? -Character->GetActorForwardVector() : Character->GetActorForwardVector();
		Direction.Z = 0.0f;
		Direction.Normalize();
	}

	const float Strength = DodgeDistance / FMath::Max(DodgeDuration, 0.01f);

	// 종료 클램프 기준은 배율 적용된 걷기 속도 — MaxWalkSpeed를 직접 읽으면 슬로우/가속 중 회피 직후 속도가 어긋난다
	const UAstralCharacterMovementComponent* AstralCMC = Cast<UAstralCharacterMovementComponent>(CMC);
	const float EndClampSpeed = AstralCMC ? AstralCMC->GetScaledMaxWalkSpeed() : CMC->MaxWalkSpeed;

	// 종료 시 잔여 속도를 걷기 속도로 클램프 — 유지 모드면 대시 속도(예: 2500cm/s)가 이월되어 슬링샷 발생
	UAbilityTask_ApplyRootMotionConstantForce* DashTask = UAbilityTask_ApplyRootMotionConstantForce::ApplyRootMotionConstantForce(
		this,
		NAME_None,
		Direction,
		Strength,
		DodgeDuration,
		/*bIsAdditive=*/false,
		/*StrengthOverTime=*/nullptr,
		ERootMotionFinishVelocityMode::ClampVelocity,
		/*SetVelocityOnFinish=*/FVector::ZeroVector,
		/*ClampVelocityOnFinish=*/EndClampSpeed,
		/*bEnableGravity=*/false);
	DashTask->OnFinish.AddDynamic(this, &UAstralGA_Hero_Dodge::OnDashFinished);
	DashTask->ReadyForActivation();

	// (선택) 몽타주 병행 — 종료는 대시 Duration이 지배, 어빌리티 종료 시 몽타주도 정지(bStopWhenAbilityEnds 기본값)
	if (DodgeMontage)
	{
		if (UAbilityTask_PlayMontageAndWait* MontageTask = UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this, NAME_None, DodgeMontage))
		{
			MontageTask->ReadyForActivation();
		}
	}
}

void UAstralGA_Hero_Dodge::OnDashFinished()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
}
