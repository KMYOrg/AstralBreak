#include "AstralGA_Hero_BasicAttack_Ranged.h"

#include "AbilitySystemComponent.h"
#include "Abilities/Tasks/AbilityTask_PlayMontageAndWait.h"
#include "Abilities/Tasks/AbilityTask_WaitGameplayEvent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAttackMontageValidation.h"
#include "AbilitySystem/Facing/AstralFacingDebug.h"
#include "AbilitySystem/Facing/AstralFacingSession.h"
#include "AbilitySystem/Tasks/AstralAbilityTask_AttackTraceWindows.h"
#include "Animation/AnimMontage.h"
#include "AstralLogChannels.h"
#include "Combat/AstralCombatTypes.h"
#include "Combat/AstralTargetHandle.h"
#include "Combat/AstralTargetingStatics.h"
#include "Engine/World.h"
#include "Equipment/AstralRangedWeaponActor.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"

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

FAstralRangedActivationData UAstralGA_Hero_BasicAttack_Ranged::CaptureActivationData(const AActor* Avatar, const FGameplayAbilityActorInfo& ActorInfo) const
{
	FAstralRangedActivationData Data;
	if (!Avatar)
	{
		return Data;
	}

	// 시작 몸 방향 — 근접과 같은 제안 (Source·TargetActor·양자화 Yaw). LockOn이면 TargetActor가 이 공격의 고정 타겟
	Data.BodyFacing = CaptureFacingProposal(Avatar, 0);

	// 폴백 조준점 — 공격 시작에 조준한 월드 지점. 발사 순간 총구에서 이 점을 향하므로 캡처 원점과 총구의 오프셋이 오차로 남지 않는다
	TOptional<FVector> AimPoint;
	if (Data.IsLockOn())
	{
		FAstralTargetHandle Handle;
		Handle.TargetActor = Data.BodyFacing.TargetActor;
		Handle.TargetPointId = Data.BodyFacing.TargetPointId;
		AimPoint = Handle.GetAimLocation();
	}
	else if (const APlayerController* PC = ActorInfo.PlayerController.Get())
	{
		// 자유 조준 — 로컬 카메라 레이의 원거리 지점 (트레이스 없음. 정식 조준점은 발사 시점 ComputeAimTarget). 원격 서버는 이 훅을 타지 않는다
		FVector CameraLocation;
		FRotator CameraRotation;
		PC->GetPlayerViewPoint(CameraLocation, CameraRotation);
		AimPoint = CameraLocation + CameraRotation.Vector() * AimTraceRange;
	}
	if (!AimPoint.IsSet() || AimPoint->ContainsNaN())
	{
		AimPoint = Avatar->GetActorLocation() + Avatar->GetActorForwardVector() * AimTraceRange;
	}

	Data.FallbackAimPoint = *AimPoint;
	return Data;
}

EAstralInputActivationPreparation UAstralGA_Hero_BasicAttack_Ranged::MakeActivationEventData(const FGameplayAbilityActorInfo& ActorInfo, FGameplayEventData& OutEventData) const
{
	const AActor* Avatar = ActorInfo.AvatarActor.Get();
	if (!Avatar)
	{
		return EAstralInputActivationPreparation::Failed;
	}

	OutEventData.Instigator = Avatar;
	OutEventData.Target = Avatar;

	// 디버그 — Stage 0 송신 생략: 이벤트 경로는 유지하되 페이로드만 비운다 (서버 Missing · 카메라 폴백)
	if (!AstralFacingDebug::ShouldDropSend(0))
	{
		// 타겟 없음(자유 조준)은 유효한 None이며 실패가 아니다
		OutEventData.TargetData = FGameplayAbilityTargetData_AstralRangedActivation::MakeHandle(CaptureActivationData(Avatar, ActorInfo));
		ASTRAL_FACING_STAT(Prepared);
	}
	return EAstralInputActivationPreparation::WithEventData;
}

void UAstralGA_Hero_BasicAttack_Ranged::ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData)
{
	Super::ActivateAbility(Handle, ActorInfo, ActivationInfo, TriggerEventData);

	if (!CommitAbility(Handle, ActorInfo, ActivationInfo))
	{
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/true);
		return;
	}

	ResetShotState();

#if !UE_BUILD_SHIPPING
	if (!bMontageValidated && FireMontage)
	{
		bMontageValidated = true;
		// 발사 노티파이(정확히 1개 · 0초 아님) → 그 시각이 Facing 밴드의 경계
		const TOptional<float> FireTime = AstralAttackMontage::ValidateFireNotify(FireMontage, AstralGameplayTags::GameplayEvent_Ranged_Fire, GetName());
		AstralAttackMontage::ValidateFacingWarpBand(FireMontage, FacingWarpTargetName, FireTime, GetName());
	}
#endif

	// 초기 데이터 — 활성화 이벤트에서. 로컬은 이벤트 밖 활성화에 한해 라이브 캡처 폴백, 원격 폰의 서버 인스턴스는 폴백하지 않는다
	const AActor* Avatar = ActorInfo ? ActorInfo->AvatarActor.Get() : nullptr;
	const bool bRemoteServer = ActorInfo && ActorInfo->IsNetAuthority() && !ActorInfo->IsLocallyControlled();

	FAstralRangedActivationData Data;
	bool bHasData = TriggerEventData && FGameplayAbilityTargetData_AstralRangedActivation::Extract(TriggerEventData->TargetData, Data);
	if (!bHasData && !bRemoteServer && Avatar && ActorInfo)
	{
		Data = CaptureActivationData(Avatar, *ActorInfo);
		bHasData = true;
	}

	if (bHasData)
	{
		PinnedAimMode = Data.IsLockOn() ? EAstralRangedAimMode::LockOn : EAstralRangedAimMode::FreeAim;
		PinnedTarget = Data.BodyFacing.TargetActor;
		PinnedTargetPointId = Data.BodyFacing.TargetPointId;
		FallbackAimPoint = FVector(Data.FallbackAimPoint);
	}
	else
	{
		// 페이로드 누락·손상 — 타겟 소멸과 구분해 진단. 승인 가능한 폴백도 없으므로 카메라 기반 자유 조준으로
		UE_LOG(LogAstralAbilitySystem, Warning, TEXT("[Ranged] %s: 활성화 페이로드 누락 — 자유 조준(카메라) 경로로 폴백"), *GetName());
	}

	// 시작 몸 방향 — 단발 FacingSession. 서버 검증·확정은 세션, 워프 설치는 여기
	TOptional<FAstralFacingProposal> StageZero;
	if (bHasData)
	{
		StageZero = Data.BodyFacing;
	}
	BeginFacingSession(Handle, ActorInfo, ActivationInfo, StageZero);
	ApplyFacingResolution(FacingSession->AdvanceStage(0, TOptional<FAstralFacingProposal>()));

	// 몽타주 미지정이면 즉발 — 같은 발사 처리 함수 (조준·중복·장애물 정책이 갈라지지 않도록)
	if (!FireMontage)
	{
		ProcessFire();
		EndAbility(Handle, ActorInfo, ActivationInfo, /*bReplicateEndAbility=*/true, /*bWasCancelled=*/false);
		return;
	}

	// 발사 이벤트 대기 — 몽타주 재생 전에 등록. 1회 수신 + bHasExecutedShot/bHasPresentedShot 가드
	if (UAbilityTask_WaitGameplayEvent* FireEventTask = UAbilityTask_WaitGameplayEvent::WaitGameplayEvent(this, AstralGameplayTags::GameplayEvent_Ranged_Fire, nullptr, /*OnlyTriggerOnce=*/true, /*OnlyMatchExact=*/true))
	{
		FireEventTask->EventReceived.AddDynamic(this, &ThisClass::OnFireEventReceived);
		FireEventTask->ReadyForActivation();
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

void UAstralGA_Hero_BasicAttack_Ranged::BeginFacingSession(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const TOptional<FAstralFacingProposal>& StageZero)
{
	constexpr int32 NumStages = 1;
	const FAstralFacingSessionContext Context = FAstralFacingSessionContext::FromActorInfo(*ActorInfo, Handle, ActivationInfo, NumStages);

	FacingSession = NewObject<UAstralFacingSession>(this);
	FacingSession->Begin(Context, StageZero);
}

void UAstralGA_Hero_BasicAttack_Ranged::ApplyFacingResolution(const FAstralFacingStageResolution& Resolution)
{
	if (!FacingWarpTargetName.IsNone())
	{
		if (Resolution.ShouldWarp())
		{
			FAstralFacingWarpCommand Command;
			Command.WarpTargetName = FacingWarpTargetName;
			Command.DesiredFacing = FRotator(0.f, Resolution.GetWarpYaw(), 0.f);
			SetFacingWarp(Command);
		}
		else
		{
			ClearFacingWarp(FacingWarpTargetName);
		}
	}

	// 서버가 거부한 타겟(아군·시체·자기 자신·범위 밖)은 발사 시점 조준점으로도 쓰지 않는다 — 폴백 방향으로
	if (Resolution.Decision == EAstralFacingDecision::NoWarp_Rejected && PinnedTarget.IsValid())
	{
		UE_LOG(LogAstralAbilitySystem, Log, TEXT("[Ranged] %s: 고정 타겟 %s 서버 거부(%s) — 발사는 폴백 방향"), *GetName(), *GetNameSafe(PinnedTarget.Get()), AstralFacing::ToString(Resolution.Reason));
		PinnedTarget = nullptr;
	}

	AstralFacingDebug::LogStageDecision(this, FacingSession, Resolution, FacingWarpTargetName);
}

//////////////////////////////////////////////////////////////////////////
// 발사

void UAstralGA_Hero_BasicAttack_Ranged::OnFireEventReceived(FGameplayEventData EventData)
{
	if (!IsActive())
	{
		return;
	}

	// 출처가 몽타주로 식별되면 이 활성화의 FireMontage여야 한다 — 이전 활성화의 잔여 이벤트 차단
	if (const UAnimMontage* SourceMontage = Cast<UAnimMontage>(EventData.OptionalObject.Get()); SourceMontage && FireMontage && SourceMontage != FireMontage)
	{
		return;
	}

	ProcessFire();
}

void UAstralGA_Hero_BasicAttack_Ranged::ProcessFire()
{
	const FGameplayAbilityActorInfo* ActorInfo = GetCurrentActorInfo();
	if (!ActorInfo || !IsActive())
	{
		return;
	}

	if (ActorInfo->IsNetAuthority())
	{
		// 서버 실행 가드 — 총구 차단으로 소모돼도 되돌리지 않는다
		if (!bHasExecutedShot)
		{
			bHasExecutedShot = true;

			if (const TOptional<FAstralRangedShot> Shot = ResolveShot())
			{
				ExecuteRangedAttack(*Shot);
			}

			// 서버 경로 연출 — 리슨 호스트도 여기서 1회 (예측 실행 생략: 권위는 멀티캐스트 수신 시 큐를 실행한다)
			PresentShot();
		}
	}
	else if (ActorInfo->IsLocallyControlled())
	{
		// 소유 클라 — 예측 연출만. 판정 투사체 생성·서버 발사 요청은 하지 않는다. 서버 거부보다 먼저 보일 수 있다
		PresentShot();
	}
}

TOptional<FAstralRangedShot> UAstralGA_Hero_BasicAttack_Ranged::ResolveShot() const
{
	TOptional<FAstralRangedShot> Result;

	const AAstralRangedWeaponActor* WeaponActor = GetRangedWeaponActor();
	const AActor* Avatar = GetAvatarActorFromActorInfo();
	const UWorld* World = Avatar ? Avatar->GetWorld() : nullptr;
	if (!WeaponActor || !Avatar || !World)
	{
		return Result;
	}

	const FVector MuzzleLocation = WeaponActor->GetMuzzleLocation();
	FVector Direction = FVector::ZeroVector;
	const TCHAR* Source = TEXT("-");

	// 폴백 — 공격 시작에 조준한 지점을 현재 총구에서 향한다 (방향을 평행 이동하면 총구 오프셋만큼 근거리 타겟을 비켜 간다)
	const FVector FallbackDirection = FallbackAimPoint.IsSet() ? (*FallbackAimPoint - MuzzleLocation).GetSafeNormal() : FVector::ZeroVector;

	if (PinnedAimMode == EAstralRangedAimMode::LockOn)
	{
		// 고정 타겟 A의 발사 시점 조준점 — 유효·CanDamage·거리·허용각 통과 시. 아니면 최초 조준점 그대로 (새 타겟·카메라로 바꾸지 않는다)
		const AActor* Target = PinnedTarget.Get();
		bool bUseTarget = Target && UAstralCombatStatics::CanDamage(Avatar, Target);
		FVector AimLocation = FVector::ZeroVector;
		EAstralFireAssistResult Assist = EAstralFireAssistResult::Ok;
		if (bUseTarget)
		{
			FAstralTargetHandle Handle;
			Handle.TargetActor = PinnedTarget;
			Handle.TargetPointId = PinnedTargetPointId;
			AimLocation = Handle.GetAimLocation();

			FAstralFireAssistParams Params;
			Params.MaxRange = LockOnFireRange;
			Params.MaxAssistYaw = MaxFireAssistYaw;
			Params.MinDistanceForYawCheck = FireAssistMinDistance;

			const float BodyYaw = Avatar->GetActorRotation().Yaw;
			const float BearingYaw = AstralTargeting::ComputeFacingYaw(Avatar->GetActorLocation(), AimLocation, BodyYaw);
			Assist = AstralRangedAttack::CheckFireAssist(FVector::Dist2D(Avatar->GetActorLocation(), AimLocation), BodyYaw, BearingYaw, Params);
			bUseTarget = (Assist == EAstralFireAssistResult::Ok);
		}

		if (bUseTarget)
		{
			Direction = (AimLocation - MuzzleLocation).GetSafeNormal();
			Source = TEXT("LockOnTarget");
		}
		else
		{
			Direction = FallbackDirection;
			Source = TEXT("FallbackAimPoint");
		}

		UE_LOG(LogAstralAbilitySystem, Log, TEXT("[Ranged] %s: Fire Mode=LockOn Target=%s Assist=%s Source=%s"),
			*GetName(), *GetNameSafe(Target), AstralRangedAttack::ToString(Assist), Source);
	}
	else
	{
		// 자유 조준 — 발사 시점 카메라 레이 (기존 전방 보정 포함). 해석 불가면 최초 조준점
		FVector AimMuzzle;
		FVector TargetPoint;
		if (ComputeAimTarget(WeaponActor, AimMuzzle, TargetPoint))
		{
			Direction = (TargetPoint - MuzzleLocation).GetSafeNormal();
			Source = TEXT("Camera");
		}
		else
		{
			Direction = FallbackDirection;
			Source = TEXT("FallbackAimPoint");
		}

		UE_LOG(LogAstralAbilitySystem, Verbose, TEXT("[Ranged] %s: Fire Mode=FreeAim Source=%s"), *GetName(), Source);
	}

	if (Direction.ContainsNaN() || Direction.IsNearlyZero())
	{
		UE_LOG(LogAstralAbilitySystem, Warning, TEXT("[Ranged] %s: 발사 방향 없음 (Source=%s) — 발사 소모"), *GetName(), Source);
		return Result;
	}

	// 총구 여유 — 벽 너머/벽 내부 총구에서는 생성하지 않는다. 위치를 벽 밖으로 옮기지도 않는다
	if (const TOptional<FAstralMuzzleClearance> Clearance = GetMuzzleClearance())
	{
		if (!IsMuzzleClear(World, Avatar, WeaponActor, MuzzleLocation, *Clearance))
		{
			UE_LOG(LogAstralAbilitySystem, Log, TEXT("[Ranged] %s: 총구 차단 — 발사 소모, 투사체 없음"), *GetName());
			return Result;
		}
	}

	FAstralRangedShot Shot;
	Shot.MuzzleLocation = MuzzleLocation;
	Shot.FireDirection = Direction.GetSafeNormal();
	Result = Shot;
	return Result;
}

bool UAstralGA_Hero_BasicAttack_Ranged::IsMuzzleClear(const UWorld* World, const AActor* Avatar, const AActor* WeaponActor, const FVector& MuzzleLocation, const FAstralMuzzleClearance& Clearance) const
{
	if (!World || !Avatar || Clearance.Radius <= 0.f || !Clearance.Blockers.IsValid())
	{
		return true;
	}

	// 기준점 = 아바타 위치(캡슐 중심) → 총구. 발사자·소유 무기는 제외, 실제 투사체 반경·차단 오브젝트 타입으로
	FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(AstralMuzzleClearance), /*bTraceComplex=*/false, Avatar);
	if (WeaponActor)
	{
		QueryParams.AddIgnoredActor(WeaponActor);
	}

	const bool bBlocked = World->SweepTestByObjectType(Avatar->GetActorLocation(), MuzzleLocation, FQuat::Identity, Clearance.Blockers, FCollisionShape::MakeSphere(Clearance.Radius), QueryParams);
	return !bBlocked;
}

void UAstralGA_Hero_BasicAttack_Ranged::PresentShot()
{
	if (bHasPresentedShot)
	{
		return;
	}
	bHasPresentedShot = true;

	if (!FireCueTag.IsValid())
	{
		return; // 6A — 연출 애셋 없음. 훅 자리만
	}

	UAbilitySystemComponent* ASC = GetAbilitySystemComponentFromActorInfo();
	AActor* Avatar = GetAvatarActorFromActorInfo();
	if (!ASC || !Avatar)
	{
		return;
	}

	FGameplayCueParameters Params;
	Params.Instigator = Avatar;
	Params.EffectCauser = GetRangedWeaponActor();
	if (const AAstralRangedWeaponActor* WeaponActor = GetRangedWeaponActor())
	{
		Params.Location = WeaponActor->GetMuzzleLocation();
	}
	Params.AbilityLevel = GetAbilityLevel();

	if (ASC->IsOwnerActorAuthoritative())
	{
		// 서버 — 활성화 예측 키(클라가 만든 키)를 실어 멀티캐스트. 소유자는 자기 키를 알아보고 건너뛰고(IsLocalClientKey), 관찰자만 재생.
		// 키 지정 창은 권위에서만 동작한다 (FScopedPredictionWindow 키 버전은 IsNetSimulating이면 no-op)
		FScopedPredictionWindow ScopedPrediction(ASC, CurrentActivationInfo.GetActivationPredictionKey());
		ASC->ExecuteGameplayCue(FireCueTag, Params);
	}
	else
	{
		// 소유 클라 — 로컬 즉시 실행. 예측 키 부기 없이 1회성 Executed 큐만 (서버 멀티캐스트는 위 키 대조로 걸러진다)
		ASC->InvokeGameplayCueEvent(FireCueTag, EGameplayCueEvent::Executed, Params);
	}
}

//////////////////////////////////////////////////////////////////////////
// 조회·정리

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

void UAstralGA_Hero_BasicAttack_Ranged::ResetShotState()
{
	PinnedAimMode = EAstralRangedAimMode::FreeAim;
	PinnedTarget = nullptr;
	PinnedTargetPointId = NAME_None;
	FallbackAimPoint.Reset();
	bHasExecutedShot = false;
	bHasPresentedShot = false;
}

void UAstralGA_Hero_BasicAttack_Ranged::EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled)
{
	// 이 활성화의 세션만 종료 — 키 불일치는 정상 경로가 아니다 (엔진이 대조해 넘긴다). 관측용 ensure
	if (FacingSession)
	{
		if (FacingSession->MatchesActivation(Handle, ActivationInfo.GetActivationPredictionKey()))
		{
			FacingSession->End();
			FacingSession = nullptr;
		}
		else
		{
			ensureMsgf(false, TEXT("[Facing] %s: EndAbility 활성화 키 불일치 (Key=%d, Session=%d) — 세션 유지"),
				*GetName(), ActivationInfo.GetActivationPredictionKey().Current, FacingSession->GetActivationKey().Current);
		}
	}

	ClearFacingWarp(FacingWarpTargetName);

	// 발사 이벤트 대기·몽타주 태스크는 어빌리티와 함께 끝난다 — 발사 전 취소면 투사체 없음. 공격별 상태는 다음 활성화에 남기지 않는다
	ResetShotState();

	Super::EndAbility(Handle, ActorInfo, ActivationInfo, bReplicateEndAbility, bWasCancelled);
}
