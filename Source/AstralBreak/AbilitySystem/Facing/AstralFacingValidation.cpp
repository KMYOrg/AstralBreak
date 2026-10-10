#include "AstralFacingValidation.h"

#include "AbilitySystem/AstralCombatStatics.h"
#include "Combat/AstralTargetingStatics.h"
#include "GameFramework/Actor.h"

namespace AstralFacingValidation
{
	EAstralFacingRejectReason ValidateProposal(const AActor* Avatar, const FAstralFacingProposal& Proposal)
	{
		const AActor* Target = Proposal.TargetActor.Get();
		if (!Avatar || !Target)
		{
			return EAstralFacingRejectReason::InvalidTarget;
		}
		if (Target == Avatar)
		{
			return EAstralFacingRejectReason::SelfTarget;
		}
		// 락온과 같은 게임플레이 판정 (아군·시체 락온 차단). 충돌 정책의 AreHostile과는 다른 축
		if (!UAstralCombatStatics::CanDamage(Avatar, Target))
		{
			return EAstralFacingRejectReason::CannotDamage;
		}

		const float Distance2D = FVector::Dist2D(Avatar->GetActorLocation(), Target->GetActorLocation());
		const float ServerBearing = AstralTargeting::ComputeFacingYaw(Avatar->GetActorLocation(), Target->GetActorLocation(), Avatar->GetActorRotation().Yaw);
		return AstralFacing::ValidateBearing(Distance2D, ServerBearing, AstralFacing::DequantizeYaw(Proposal.QuantizedDesiredYaw));
	}
}
