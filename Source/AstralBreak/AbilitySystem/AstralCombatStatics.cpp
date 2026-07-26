#include "AstralCombatStatics.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Effects/AstralSetByCallerGameplayTags.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerState.h"
#include "GameplayEffect.h"

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

	// 팀 해석 실패(NoTeam)는 기본 "때릴 수 없음" — 엔진 기본 solver는 A != B를 전부 Hostile로 판정하므로
	// (NoTeam=Neutral이 아님!) GetAttitude 전에 직접 가드해야 한다
	if (SourceTeam == FGenericTeamId::NoTeam || TargetTeam == FGenericTeamId::NoTeam)
	{
		return false;
	}

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

int32 UAstralCombatStatics::ApplyDamageSweep(UAbilitySystemComponent* SourceASC, AActor* Avatar, TSubclassOf<UGameplayEffect> DamageEffectClass, float BaseDamage, float TraceStartOffset, float TraceDistance, float TraceRadius, float EffectLevel)
{
	if (!SourceASC || !Avatar || !DamageEffectClass)
	{
		return 0;
	}

	UWorld* World = Avatar->GetWorld();
	if (!World)
	{
		return 0;
	}

	// Sphere Sweep — 아바타 정면
	const FVector Forward = Avatar->GetActorForwardVector();
	const FVector Start   = Avatar->GetActorLocation() + Forward * TraceStartOffset;
	const FVector End     = Start + Forward * TraceDistance;

	TArray<FHitResult> Hits;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(AstralCombat_DamageSweep), false);
	Params.AddIgnoredActor(Avatar);
	World->SweepMultiByChannel(Hits, Start, End, FQuat::Identity, ECC_Pawn, FCollisionShape::MakeSphere(TraceRadius), Params);

	// 중복 타겟 방지
	TSet<AActor*> Damaged;
	int32 NumTargetsHit = 0;

	for (const FHitResult& Hit : Hits)
	{
		AActor* TargetActor = Hit.GetActor();
		if (!TargetActor || Damaged.Contains(TargetActor))
		{
			continue;
		}
		// 피아 필터 — Hostile만 허용 (아군/중립/사망 대상 오폭 차단)
		if (!CanDamage(Avatar, TargetActor))
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

		const FGameplayEffectSpecHandle SpecHandle = SourceASC->MakeOutgoingSpec(DamageEffectClass, EffectLevel, Context);
		if (SpecHandle.IsValid())
		{
			SpecHandle.Data->SetSetByCallerMagnitude(AstralGameplayTags::SetByCaller_Damage, BaseDamage);
			SourceASC->ApplyGameplayEffectSpecToTarget(*SpecHandle.Data.Get(), TargetASC);
			Damaged.Add(TargetActor);
			++NumTargetsHit;
		}
	}

	return NumTargetsHit;
}
