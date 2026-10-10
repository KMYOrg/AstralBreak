#pragma once

#include "CoreMinimal.h"
#include "Combat/AstralFacingTypes.h"

/**
 * Facing 서버 월드 검증 — 원격 폰의 서버 인스턴스가 클라 제안을 승인할지 결정한다.
 * 활성화 수명·워프 설치를 모른다. 순수 경계(거리·방위)는 AstralFacing::ValidateBearing, 월드 판정(CanDamage)은 여기
 */
namespace AstralFacingValidation
{
	/**
	 * TargetActor 유효 · 자기 자신 아님 · CanDamage · 거리 · 방위.
	 * 서버 방위는 검증에만 쓴다 — 재계산하면 클라와 미세하게 달라져 발산이 되살아난다
	 */
	ASTRALBREAK_API EAstralFacingRejectReason ValidateProposal(const AActor* Avatar, const FAstralFacingProposal& Proposal);
}
