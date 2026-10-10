#include "AstralGA_Hero_Dodge.h"

#include "Abilities/Tasks/AbilityTask_ApplyRootMotionConstantForce.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Animation/AnimMontage.h"
#include "AstralLogChannels.h"
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralCharacterMovementComponent.h"
#include "Combat/AstralDodgeTypes.h"
#include "Combat/AstralFacingTypes.h"
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

FVector UAstralGA_Hero_Dodge::CaptureDodgeDirection(const AActor* Avatar) const
{
	FAstralDodgeDirectionInput Input;
	Input.bBackstepWhenIdle = bDodgeBackwardWhenIdle;

	const ACharacter* Character = Cast<ACharacter>(Avatar);
	if (Character)
	{
		if (const UCharacterMovementComponent* CMC = Character->GetCharacterMovement())
		{
			Input.HorizontalInput = CMC->GetCurrentAcceleration();
		}
		Input.AvatarLocation = Character->GetActorLocation();
		Input.AvatarForward = Character->GetActorForwardVector();
	}

	const FAstralTargetHandle Target = ResolveEffectiveTarget(Avatar);
	if (Target.IsSet())
	{
		Input.bHasLockTarget = true;
		Input.TargetLocation = Target.GetAimLocation();
	}

	return AstralDodge::ResolveDirection(Input);
}

EAstralInputActivationPreparation UAstralGA_Hero_Dodge::MakeActivationEventData(const FGameplayAbilityActorInfo& ActorInfo, FGameplayEventData& OutEventData) const
{
	const AActor* Avatar = ActorInfo.AvatarActor.Get();
	if (!Avatar)
	{
		return EAstralInputActivationPreparation::Failed;
	}

	const FVector Direction = CaptureDodgeDirection(Avatar);
	if (Direction.ContainsNaN() || Direction.IsNearlyZero())
	{
		return EAstralInputActivationPreparation::Failed;
	}

	FAstralDodgeActivationData Data;
	Data.QuantizedYaw = AstralFacing::QuantizeYaw(Direction.Rotation().Yaw);

	OutEventData.Instigator = Avatar;
	OutEventData.Target = Avatar;
	OutEventData.TargetData = FGameplayAbilityTargetData_AstralDodge::MakeHandle(Data);
	return EAstralInputActivationPreparation::WithEventData;
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

	// 방향 — 활성화 이벤트의 양자화 Yaw를 양쪽이 같은 값으로 복원. 서버는 자기 입력·타겟으로 다시 결정하지 않는다
	FVector Direction = FVector::ZeroVector;
	FAstralDodgeActivationData Data;
	if (TriggerEventData && FGameplayAbilityTargetData_AstralDodge::Extract(TriggerEventData->TargetData, Data))
	{
		Direction = Data.GetDirection();
	}
	else if (ActorInfo->IsLocallyControlled())
	{
		// 로컬 폴백 — 이벤트 경로 밖의 활성화(디버그 훅·다른 호출자)
		Direction = CaptureDodgeDirection(Character);
	}
	else
	{
		// 원격 폰의 서버 인스턴스에 페이로드 누락 — 기존 규칙(서버 가속도 → 백스텝)으로 폴백하고 진단. 정상 경로에서 찍히면 이벤트 경로가 깨진 것
		Direction = CaptureDodgeDirection(Character);
		UE_LOG(LogAstralAbilitySystem, Warning, TEXT("[Dodge] %s: 활성화 페이로드 누락 — 서버 로컬 규칙으로 방향 폴백 (클라와 어긋날 수 있다)"), *GetName());
	}

	Direction.Z = 0.f;
	if (!Direction.Normalize())
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
		return;
	}

	const float Strength = DodgeDistance / FMath::Max(DodgeDuration, 0.01f);

	// 종료 클램프 기준은 배율 적용된 걷기 속도 — MaxWalkSpeed를 직접 읽으면 슬로우/가속 중 회피 직후 속도가 어긋난다
	const UAstralCharacterMovementComponent* AstralCMC = Cast<UAstralCharacterMovementComponent>(CMC);
	const float EndClampSpeed = AstralCMC ? AstralCMC->GetScaledMaxWalkSpeed() : CMC->MaxWalkSpeed;

	// 종료 시 잔여 속도를 걷기 속도로 클램프 — 유지 모드면 대시 속도(예: 2500cm/s)가 이월되어 슬링샷 발생.
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
