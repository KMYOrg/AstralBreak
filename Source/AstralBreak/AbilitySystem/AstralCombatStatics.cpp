#include "AstralCombatStatics.h"

#include "AbilitySystemBlueprintLibrary.h"
#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "AbilitySystem/Effects/AstralSetByCallerGameplayTags.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerState.h"
#include "GameplayEffect.h"
#include "GameplayEffectExtension.h"
#include "System/AstralGameData.h"

namespace
{
	// 정면 판정 반각 — 120° 콘. M5에서 공격별 세분화가 필요해지면 데이터화
	constexpr float FrontalHalfAngleDeg = 60.f;
}

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

int32 UAstralCombatStatics::ApplyDamageSweep(UAbilitySystemComponent* SourceASC, AActor* Avatar, float BaseDamage, float TraceStartOffset, float TraceDistance, float TraceRadius, float EffectLevel)
{
	if (!SourceASC || !Avatar)
	{
		return 0;
	}

	// 데미지 파이프라인 GE는 전역 단일 — GameData에서 해석 (호출자별 중복 지정 제거)
	const TSubclassOf<UGameplayEffect> DamageEffectClass = UAstralGameData::Get().DamageGameplayEffect_SetByCaller.LoadSynchronous();
	if (!DamageEffectClass)
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

bool UAstralCombatStatics::ResolveIncomingDamage(FGameplayEffectModCallbackData& Data)
{
	UAbilitySystemComponent& TargetASC = Data.Target;

	const bool bParrying = TargetASC.HasMatchingGameplayTag(AstralGameplayTags::State_Defense_Parrying);
	const bool bGuarding = TargetASC.HasMatchingGameplayTag(AstralGameplayTags::State_Defense_Guarding);
	if (!bParrying && !bGuarding)
	{
		return true;
	}

	// 가드 불가 데미지
	FGameplayTagContainer SpecAssetTags;
	Data.EffectSpec.GetAllAssetTags(SpecAssetTags);
	if (SpecAssetTags.HasTag(AstralGameplayTags::Damage_Type_Unblockable))
	{
		return true;
	}

	// 위치·전방은 반드시 AvatarActor — 히어로의 HealthSet 오너는 PlayerState
	AActor* DefenderAvatar = TargetASC.GetAvatarActor();
	AActor* Attacker = Data.EffectSpec.GetEffectContext().GetOriginalInstigator();
	if (!DefenderAvatar || !Attacker)
	{
		return true;
	}

	// 정면 판정 (2D — 높이차 무시)
	const FVector ToAttacker = (Attacker->GetActorLocation() - DefenderAvatar->GetActorLocation()).GetSafeNormal2D();
	const FVector DefenderForward = DefenderAvatar->GetActorForwardVector().GetSafeNormal2D();
	if (FVector::DotProduct(DefenderForward, ToAttacker) < FMath::Cos(FMath::DegreesToRadians(FrontalHalfAngleDeg)))
	{
		return true;
	}

	if (bParrying)
	{
		// 완전 무효 + 양측 통지 — 보상(표식/오의)은 방어 GA가 Parried 수신 후 처리, 경직은 공격 GA가 Staggered 수신 후 처리
		FGameplayEventData ParriedPayload;
		ParriedPayload.Instigator = Attacker;
		ParriedPayload.Target = DefenderAvatar;
		ParriedPayload.EventMagnitude = Data.EvaluatedData.Magnitude;
		UAbilitySystemBlueprintLibrary::SendGameplayEventToActor(DefenderAvatar, AstralGameplayTags::GameplayEvent_Parried, ParriedPayload);

		FGameplayEventData StaggeredPayload;
		StaggeredPayload.Instigator = DefenderAvatar;
		StaggeredPayload.Target = Attacker;
		UAbilitySystemBlueprintLibrary::SendGameplayEventToActor(Attacker, AstralGameplayTags::GameplayEvent_Staggered, StaggeredPayload);

		return false;
	}

	// 가드 — GuardDamageMultiplier 감쇄 (히어로 전용 ResourceSet, 없으면 안전 기본값)
	float GuardMultiplier = 0.5f;
	if (TargetASC.HasAttributeSetForAttribute(UAstralHeroResourceSet::GetGuardDamageMultiplierAttribute()))
	{
		GuardMultiplier = TargetASC.GetNumericAttribute(UAstralHeroResourceSet::GetGuardDamageMultiplierAttribute());
	}

	const float OriginalMagnitude = Data.EvaluatedData.Magnitude;
	Data.EvaluatedData.Magnitude = OriginalMagnitude * GuardMultiplier;

	FGameplayEventData GuardedPayload;
	GuardedPayload.Instigator = Attacker;
	GuardedPayload.Target = DefenderAvatar;
	GuardedPayload.EventMagnitude = OriginalMagnitude - Data.EvaluatedData.Magnitude; // 막은 양 — 가드 스태미나 소모의 기준
	UAbilitySystemBlueprintLibrary::SendGameplayEventToActor(DefenderAvatar, AstralGameplayTags::GameplayEvent_Guarded, GuardedPayload);

	return true;
}
