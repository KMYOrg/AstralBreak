#include "AstralCombatStatics.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerState.h"

bool UAstralCombatStatics::CanDamage(const AActor* SourceActor, const AActor* TargetActor)
{
	if (!SourceActor || !TargetActor || SourceActor == TargetActor)
	{
		return false;
	}

	if (IsDeadOrDying(TargetActor))
	{
		return false;
	}

	const FGenericTeamId SourceTeam = GetTeamId(SourceActor);
	const FGenericTeamId TargetTeam = GetTeamId(TargetActor);

	// 기본 attitude 해석: 같은 팀=Friendly, 다른 팀=Hostile, NoTeam 관여=Neutral
	// Hostile일 때만 허용 — 팀 미상/중립은 기본 "때릴 수 없음"
	return FGenericTeamId::GetAttitude(SourceTeam, TargetTeam) == ETeamAttitude::Hostile;
}

FGenericTeamId UAstralCombatStatics::GetTeamId(const AActor* Actor)
{
	if (!Actor)
	{
		return FGenericTeamId::NoTeam;
	}

	// 1) 액터 본인 (CombatCharacter 등)
	if (const IGenericTeamAgentInterface* TeamAgent = Cast<IGenericTeamAgentInterface>(Actor))
	{
		return TeamAgent->GetGenericTeamId();
	}

	// 2) 폰이면 컨트롤러 → PlayerState 순으로 (Hero는 PlayerState가 구현)
	if (const APawn* Pawn = Cast<APawn>(Actor))
	{
		if (const IGenericTeamAgentInterface* ControllerAgent = Cast<IGenericTeamAgentInterface>(Pawn->GetController()))
		{
			return ControllerAgent->GetGenericTeamId();
		}

		if (const IGenericTeamAgentInterface* PlayerStateAgent = Cast<IGenericTeamAgentInterface>(Pawn->GetPlayerState()))
		{
			return PlayerStateAgent->GetGenericTeamId();
		}
	}

	return FGenericTeamId::NoTeam;
}

int32 UAstralCombatStatics::GetTeamIdAsInt(const AActor* Actor)
{
	return GetTeamId(Actor).GetId();
}

bool UAstralCombatStatics::IsDeadOrDying(const AActor* Actor)
{
	if (const UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Actor))
	{
		return ASC->HasMatchingGameplayTag(AstralGameplayTags::State_Death);
	}

	return false;
}
