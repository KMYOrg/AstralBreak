#include "AstralGA_Hero_BasicAttack_Ranged.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Tasks/AstralAbilityTask_AttackTraceWindows.h"
#include "Animation/AnimMontage.h"
#include "Engine/World.h"
#include "Equipment/AstralRangedWeaponActor.h"
#include "GameFramework/Pawn.h"

UAstralGA_Hero_BasicAttack_Ranged::UAstralGA_Hero_BasicAttack_Ranged(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	InstancingPolicy   = EGameplayAbilityInstancingPolicy::InstancedPerActor;
	NetExecutionPolicy = EGameplayAbilityNetExecutionPolicy::LocalPredicted;

	// 모드 분기 — Ranged 모드일 때만 활성 (발사 방식 무관 공통)
	ActivationRequiredTags.AddTag(AstralGameplayTags::State_CombatStyle_Ranged);

	// 활성 시 부여 (디버그/UI 등)
	ActivationOwnedTags.AddTag(AstralGameplayTags::Ability_Attack_Basic_Ranged);

	// asset tag — CancelAbilities/BlockAbilitiesWithTag 매칭 기준
	FGameplayTagContainer AssetTags;
	AssetTags.AddTag(AstralGameplayTags::Ability_Attack_Basic_Ranged);
	SetAssetTags(AssetTags);

	// 상호배타 — 근접 GA와 동일 정책: 공격 중 다른 공격 차단, 공격 발동 시 방어 캔슬 (최신 입력 우선)
	BlockAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Attack);
	CancelAbilitiesWithTag.AddTag(AstralGameplayTags::Ability_Defense);
}

void UAstralGA_Hero_BasicAttack_Ranged::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
		return;
	}

	// 발사는 서버 권위 — 판정·수급 주체가 서버에만 존재. 방식은 파생의 훅
	if (ActorInfo && ActorInfo->IsNetAuthority())
	{
		ExecuteRangedAttack();
	}

	// 몽타주 미지정이면 즉발 종료 — 연사 속도는 몽타주 길이(또는 이후 쿨다운 GE)가 결정
	if (!FireMontage)
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
		return;
	}

	if (UAbilityTask_PlayMontageAndWait* MontageTask = UAbilityTask_PlayMontageAndWait::CreatePlayMontageAndWaitProxy(this, NAME_None, FireMontage, 1.f, NAME_None, /*bStopWhenAbilityEnds=*/true, 1.f))
	{
		MontageTask->OnCompleted.AddDynamic(this, &ThisClass::OnMontageFinished);
		MontageTask->OnBlendOut.AddDynamic(this, &ThisClass::OnMontageFinished);
		MontageTask->OnInterrupted.AddDynamic(this, &ThisClass::OnMontageFinished);
		MontageTask->OnCancelled.AddDynamic(this, &ThisClass::OnMontageFinished);
		MontageTask->ReadyForActivation();
	}
	else
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
	}
}

AAstralRangedWeaponActor* UAstralGA_Hero_BasicAttack_Ranged::GetRangedWeaponActor() const
{
	return Cast<AAstralRangedWeaponActor>(UAstralAbilityTask_AttackTraceWindows::FindWeaponActorFromAbility(this));
}

bool UAstralGA_Hero_BasicAttack_Ranged::ComputeAimTarget(const AAstralRangedWeaponActor* WeaponActor, FVector& OutMuzzleLocation, FVector& OutTargetPoint) const
{
	const APawn* AvatarPawn = Cast<APawn>(GetAvatarActorFromActorInfo());
	UWorld* World = AvatarPawn ? AvatarPawn->GetWorld() : nullptr;
	AController* Controller = AvatarPawn ? AvatarPawn->GetController() : nullptr;
	if (!WeaponActor || !World || !Controller)
	{
		return false;
	}

	// 조준 기준 = 화면 중앙(카메라) 레이 — 크로스헤어와 탄착 일치.
	// 원격 플레이어의 카메라 POV는 클라가 ServerUpdateCamera로 서버에 보고하는 엔진 표준 경로
	FVector CameraLocation;
	FRotator CameraRotation;
	Controller->GetPlayerViewPoint(CameraLocation, CameraRotation);
	const FVector CameraDirection = CameraRotation.Vector();

	OutMuzzleLocation = WeaponActor->GetMuzzleLocation();

	// 트레이스 시작 = 카메라 레이 위 총구 투영 지점 — 카메라~캐릭터 사이(등 뒤) 오브젝트 오폭 방지
	const float MuzzleProjection = FMath::Max(FVector::DotProduct(OutMuzzleLocation - CameraLocation, CameraDirection), 0.f);
	const FVector TraceStart = CameraLocation + CameraDirection * MuzzleProjection;
	const FVector TraceEnd = TraceStart + CameraDirection * AimTraceRange;
	OutTargetPoint = TraceEnd;

	FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(AstralRangedAim), /*bTraceComplex=*/false, AvatarPawn);
	QueryParams.AddIgnoredActor(WeaponActor);

	FHitResult AimHit;
	if (World->LineTraceSingleByChannel(AimHit, TraceStart, TraceEnd, ECC_Visibility, QueryParams))
	{
		OutTargetPoint = AimHit.ImpactPoint;
	}

	// 조준점이 총구 뒤/측면(극근접 지형 등)이면 카메라 레이 방향의 원거리 지점으로 보정 — 발사선의 전방 보장
	if (FVector::DotProduct((OutTargetPoint - OutMuzzleLocation).GetSafeNormal(), CameraDirection) <= 0.f)
	{
		OutTargetPoint = OutMuzzleLocation + CameraDirection * AimTraceRange;
	}

	return true;
}

void UAstralGA_Hero_BasicAttack_Ranged::OnMontageFinished()
{
	EndAbility(CurrentSpecHandle, CurrentActorInfo, CurrentActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
}
