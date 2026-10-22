#include "AstralAnimInstance.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "Character/Hero/AstralCharacter_Hero.h"
#include "Combat/AstralRangedAim.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Character/Components/AstralCharacterMovementComponent.h"

namespace
{
	float CalculateDirectionAngle(const FVector& Velocity, const FRotator& BaseRotation)
	{
		if (Velocity.IsNearlyZero())
		{
			return 0.0f;
		}

		const FMatrix RotMatrix = FRotationMatrix(BaseRotation);
		const FVector ForwardVector = RotMatrix.GetScaledAxis(EAxis::X);
		const FVector RightVector   = RotMatrix.GetScaledAxis(EAxis::Y);
		const FVector NormalizedVel = Velocity.GetSafeNormal2D();

		const float ForwardCosAngle   = FVector::DotProduct(ForwardVector, NormalizedVel);
		const float ForwardDeltaDegree = FMath::RadiansToDegrees(FMath::Acos(ForwardCosAngle));
		const float RightCosAngle     = FVector::DotProduct(RightVector, NormalizedVel);

		return (RightCosAngle < 0.0f) ? -ForwardDeltaDegree : ForwardDeltaDegree;
	}
}

UAstralAnimInstance::UAstralAnimInstance(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

void UAstralAnimInstance::NativeInitializeAnimation()
{
	Super::NativeInitializeAnimation();

	// Game Thread 전용 객체 캐싱
	OwningPawn = TryGetPawnOwner();
	if (OwningPawn)
	{
		AstralMovementComponent = Cast<UAstralCharacterMovementComponent>(OwningPawn->GetMovementComponent());

		// ASC(태그) 결합은 메인 인스턴스만 — 링크드 인스턴스는 태그 파생 값을 메인에서 복사한다(NativeThreadSafeUpdateAnimation).
		// 메시는 메인 인스턴스를 대입한 뒤 초기화하므로 여기서 GetAnimInstance() == this 로 메인을 가린다
		const USkeletalMeshComponent* Mesh = GetSkelMeshComponent();
		if (Mesh && Mesh->GetAnimInstance() == this)
		{
			if (UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(OwningPawn))
			{
				InitializeWithAbilitySystem(ASC);
			}
		}
	}
}

void UAstralAnimInstance::InitializeWithAbilitySystem(UAbilitySystemComponent* ASC)
{
	check(ASC);

	BoundASC = ASC;
	GameplayTagPropertyMap.Initialize(this, ASC);
}

void UAstralAnimInstance::SetLeftHandGrip(const FTransform& GripInReferenceBoneSpace)
{
	PendingLeftHandGrip = GripInReferenceBoneSpace;
}

void UAstralAnimInstance::ClearLeftHandGrip()
{
	PendingLeftHandGrip.Reset();
}

void UAstralAnimInstance::SetMuzzle(const FTransform& MuzzleInReferenceBoneSpace)
{
	PendingMuzzle = MuzzleInReferenceBoneSpace;
	SmoothedAimInverseDistance = -1.f;
}

void UAstralAnimInstance::ClearMuzzle()
{
	PendingMuzzle.Reset();
	SmoothedAimInverseDistance = -1.f;
}

bool UAstralAnimInstance::ComputeAimCorrectionTarget(const USkeletalMeshComponent& Mesh, float DeltaSeconds, FVector& OutTargetComponentSpace)
{
	// 총구 월드 위치는 지난 프레임 포즈 — 트레이스 시작(카메라 레이 위 투영점)·뒤쪽 판정에만 쓴다. 노드는 이번 프레임 포즈로 총구를 다시 잰다
	const FVector MuzzleWorld = (*PendingMuzzle * Mesh.GetSocketTransform(WeaponReferenceBone)).GetLocation();

	FVector TraceStart;
	FVector Direction;
	float Distance;
	const AAstralCharacter_Hero* Hero = Cast<AAstralCharacter_Hero>(OwningPawn);
	if (const APlayerController* PC = Cast<APlayerController>(OwningPawn->GetController()))
	{
		// 플레이어 — 로컬(호스트·소유 클라)과 서버의 원격 플레이어(ServerUpdateCamera POV). 발사와 같은 함수·같은 조준점
		AstralRangedAim::FCameraAimPoint Aim;
		if (!AstralRangedAim::ComputeCameraAimPoint(PC, OwningPawn, nullptr, MuzzleWorld, AstralRangedAim::DefaultTraceRange, Aim))
		{
			return false;
		}
		TraceStart = Aim.TraceStart;
		Direction = Aim.Direction;
		Distance = FVector::DotProduct(Aim.TargetPoint - Aim.TraceStart, Aim.Direction);
	}
	else if (FVector ObservedTarget; Hero && Hero->GetObservedAimTarget(ObservedTarget))
	{
		// 시뮬 프록시 — 서버가 복제한 조준점(발사와 같은 카메라 조준점). 그 점을 지나는 조준 방향 직선을 카메라 레이로 보고 총구 투영점부터의 거리로
		// 아래 공통 경로(최소 거리·역거리 보간)를 탄다 — 로컬과 같은 정의라 수렴하면 복제된 점 그대로
		const FVector TargetWorld = Mesh.GetComponentTransform().TransformPosition(ObservedTarget);
		Direction = OwningPawn->GetBaseAimRotation().Vector();
		Distance = FVector::DotProduct(TargetWorld - MuzzleWorld, Direction);
		TraceStart = TargetWorld - Direction * Distance;
	}
	else
	{
		// AI·조준점 복제 전 — 카메라가 없다. 조준 회전(시뮬 프록시는 RemoteViewPitch + 액터 Yaw) 방향의 먼 점 — 먼 표적이면 시차는 무시해도 되는 거리
		TraceStart = OwningPawn->GetPawnViewLocation();
		Direction = OwningPawn->GetBaseAimRotation().Vector();
		Distance = AstralRangedAim::DefaultTraceRange;
	}

	// 코앞 조준점은 밀고, 거리는 역수로 보간 — 크로스헤어가 벽 경계를 넘을 때 시차 보정이 튀지 않게(방향은 즉시). 시차 각 ∝ 1/거리라
	// 역수 보간이 각도 기준으로 고르게 수렴한다(거리 그대로 보간하면 100m → 1m 전환이 0.45초 끌렸다 — 2026-10-21 총구 프로브)
	const float DesiredInverseDistance = 1.f / FMath::Max(Distance, FMath::Max(AimCorrectionMinDistance, 1.f));
	SmoothedAimInverseDistance = (SmoothedAimInverseDistance < 0.f || AimCorrectionDistanceInterpSpeed <= 0.f)
		? DesiredInverseDistance
		: FMath::FInterpTo(SmoothedAimInverseDistance, DesiredInverseDistance, DeltaSeconds, AimCorrectionDistanceInterpSpeed);

	OutTargetComponentSpace = Mesh.GetComponentTransform().InverseTransformPosition(TraceStart + Direction / SmoothedAimInverseDistance);
	return true;
}

void UAstralAnimInstance::NativeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeUpdateAnimation(DeltaSeconds);

	if (!OwningPawn || !AstralMovementComponent)
	{
		return;
	}

	Snapshot.WorldVelocity     = AstralMovementComponent->Velocity;
	Snapshot.WorldAcceleration = AstralMovementComponent->GetCurrentAcceleration();
	Snapshot.ActorRotation     = OwningPawn->GetActorRotation();
	Snapshot.bIsInAir          = AstralMovementComponent->IsFalling();
	Snapshot.bIsOnGround       = AstralMovementComponent->IsMovingOnGround();
	Snapshot.GroundDistance    = AstralMovementComponent->GetGroundInfo().GroundDistance;
	Snapshot.BaseAimRotation   = OwningPawn->GetBaseAimRotation();
	// 전신 슬롯의 몽타주 가중치(지난 프레임) — 상체 슬롯(사격)만 도는 몽타주는 제자리 회전을 막지 않는다
	Snapshot.bFullBodyMontagePlaying = GetSlotMontageGlobalWeight(FullBodyMontageSlot) > KINDA_SMALL_NUMBER;

	// 조준 태그 — ASC 는 Mixed 복제라 전 머신이 같은 값을 본다. 결합 전(폰 도착 직후)은 false. 메인 인스턴스만 결합하므로 링크 인스턴스는 여기서 늘 false —
	// 스레드 안전 업데이트가 메인 값으로 덮는다
	const UAbilitySystemComponent* ASC = BoundASC.Get();
	Snapshot.bAiming = ASC && ASC->HasMatchingGameplayTag(AstralGameplayTags::State_Ranged_Aiming);

	// 왼손 파지점·총구 — 장비 매니저가 메인 인스턴스에 넣은 값
	Snapshot.bHasLeftHandGrip = PendingLeftHandGrip.IsSet();
	Snapshot.LeftHandGrip = PendingLeftHandGrip.Get(FTransform::Identity);
	Snapshot.bHasMuzzle = PendingMuzzle.IsSet();
	Snapshot.Muzzle = PendingMuzzle.Get(FTransform::Identity);

	// 최종 조준 보정 조준점 — 조준 중에만(조준이 풀리면 노드 알파가 0.15초에 걸쳐 빠지는 동안 마지막 값을 쓴다). 다음 조준 진입은 보간 없이 바로 맞춘다
	const USkeletalMeshComponent* SkelMesh = GetSkelMeshComponent();
	if (Snapshot.bAiming && Snapshot.bHasMuzzle && SkelMesh)
	{
		Snapshot.bHasAimTarget = ComputeAimCorrectionTarget(*SkelMesh, DeltaSeconds, Snapshot.AimTarget);
	}
	else if (!Snapshot.bAiming)
	{
		SmoothedAimInverseDistance = -1.f;
	}

	// 액터 Yaw 델타 — 제자리 회전 누적 입력. 첫 프레임은 0
	const float ActorYaw = Snapshot.ActorRotation.Yaw;
	Snapshot.YawDeltaSinceLastUpdate = bHasPreviousActorYaw ? FRotator::NormalizeAxis(ActorYaw - PreviousActorYaw) : 0.f;
	PreviousActorYaw = ActorYaw;
	bHasPreviousActorYaw = true;

	// 메인 인스턴스 캐시
	const USkeletalMeshComponent* Mesh = GetSkelMeshComponent();
	MainAnimInstance = Mesh ? Cast<UAstralAnimInstance>(Mesh->GetAnimInstance()) : nullptr;
}

UAstralAnimInstance* UAstralAnimInstance::GetMainAnimInstance() const
{
	return MainAnimInstance ? MainAnimInstance.Get() : const_cast<UAstralAnimInstance*>(this);
}

void UAstralAnimInstance::NativeThreadSafeUpdateAnimation(float DeltaSeconds)
{
	Super::NativeThreadSafeUpdateAnimation(DeltaSeconds);
	
	Speed             = Snapshot.WorldVelocity.Size2D();
	Acceleration      = Snapshot.WorldAcceleration.Size2D();
	bHasMovementInput = Snapshot.WorldAcceleration.SizeSquared() > KINDA_SMALL_NUMBER;
	bIsOnGround       = Snapshot.bIsOnGround;
	bIsInAir          = Snapshot.bIsInAir;
	bIsJumping        = Snapshot.bIsInAir && (Snapshot.WorldVelocity.Z > 0.0f);
	bIsFalling        = Snapshot.bIsInAir && !bIsJumping;
	GroundDistance    = Snapshot.GroundDistance;
	MovementDirection = CalculateDirectionAngle(Snapshot.WorldVelocity, Snapshot.ActorRotation);

	// 조준 여부는 메인 인스턴스의 것 — ASC 는 메인만 결합한다. 링크 인스턴스의 이 함수는 메인 그래프 순회 중 메인의 업데이트 뒤에 돌아 같은 프레임 값이다
	// (게임 스레드 NativeUpdateAnimation 은 링크가 메인보다 먼저 돌아 한 프레임 늦다 — SkeletalMeshComponent::TickAnimation)
	const UAstralAnimInstance* Main = GetMainAnimInstance();
	bIsAiming = (Main == this) ? Snapshot.bAiming : Main->bIsAiming;

	bHasLeftHandGrip     = Snapshot.bHasLeftHandGrip;
	LeftHandGripLocation = Snapshot.LeftHandGrip.GetLocation();
	LeftHandGripRotation = Snapshot.LeftHandGrip.Rotator();

	// 최종 조준 보정 — 총구·조준점은 메인 인스턴스에만 들어온다(링크 인스턴스는 늘 꺼짐 — 노드는 베이스 그래프에 있다)
	MuzzleLocation       = Snapshot.Muzzle.GetLocation();
	MuzzleRotation       = Snapshot.Muzzle.Rotator();
	AimCorrectionTarget  = Snapshot.AimTarget;
	bAimCorrectionActive = bIsAiming && Snapshot.bHasMuzzle && Snapshot.bHasAimTarget;

	// ---- 제자리 회전 — 메인 인스턴스만 계산한다 ---
	// 정책: 조준 중 ∧ 지상 ∧ 정지 ∧ 전신 몽타주 없음 ∧ 조준 진입 피벗 창 밖이면 발을 붙여 두고(누적), 아니면 0 으로 복귀. 조준이 아닌 평상시엔 액터가 이동 방향을 향하므로 항상 0
	if (MainAnimInstance == nullptr || MainAnimInstance == this)
	{
		static const FName NAME_TurnYawWeight(TEXT("TurnYawWeight"));
		static const FName NAME_RemainingTurnYaw(TEXT("RemainingTurnYaw"));

		// 조준 진입 피벗 — 비조준에서 조준으로 넘어온 직후엔 몸이 카메라 쪽으로 빠르게 도는 중이라 발을 붙이지 않는다(메시도 같이 돈다)
		AimEntryPivotRemaining = (Snapshot.bAiming && !bWasAimingLastUpdate) ? AimEntryPivotTime : FMath::Max(AimEntryPivotRemaining - DeltaSeconds, 0.f);
		bWasAimingLastUpdate = Snapshot.bAiming;

		FAstralTurnInPlaceInput Input;
		Input.DeltaSeconds = DeltaSeconds;
		Input.YawDeltaSinceLastUpdate = Snapshot.YawDeltaSinceLastUpdate;
		Input.bAccumulate = Snapshot.bAiming && Snapshot.bIsOnGround && Speed < TurnInPlaceAccumulateMaxSpeed && !bHasMovementInput && !Snapshot.bFullBodyMontagePlaying
			&& AimEntryPivotRemaining <= 0.f;
		// 커브는 지난 프레임 최종 포즈의 것 — 공급자 레이어가 재생하는 턴 클립의 커브가 포즈 링크를 타고 여기까지 온다
		Input.TurnYawWeightCurve = GetCurveValue(NAME_TurnYawWeight);
		Input.RemainingTurnYawCurve = GetCurveValue(NAME_RemainingTurnYaw);
		TurnInPlace.Update(TurnInPlaceSettings, Input);

		RootYawOffset               = TurnInPlace.RootYawOffset;
		bWantsTurnInPlace           = TurnInPlace.bWantsTurn;
		bTurnInPlaceRotationFinished = TurnInPlace.bRotationFinished;
		TurnInPlaceKind             = TurnInPlace.Kind;
		TurnInPlaceAnimTime         = TurnInPlace.TurnAnimTime;
		TurnYawCurveValue           = TurnInPlace.TurnYawCurveValue;
		TurnInPlaceDebugWeight      = Input.TurnYawWeightCurve;
		TurnInPlaceDebugRemaining   = Input.RemainingTurnYawCurve;
		bTurnInPlaceAccumulating    = Input.bAccumulate;
	}

	// 조준 각 = 조준 회전 − 몸 회전 − 루트 오프셋 (AimOffset 입력). 조준 중엔 몸이 컨트롤러 Yaw 를 따르므로 첫 항은 0 근처이고,
	// 루트를 오프셋만큼 돌려 둔 동안은 상체가 그만큼 되돌아 조준해야 총이 카메라 방향을 유지한다 (Lyra #4).
	// 오프셋은 메인 인스턴스의 것 — AimOffset 노드는 링크된 공급자 레이어(Aim_UpperBody)에 있고 공급자는 제자리 회전을 계산하지 않는다(자기 RootYawOffset = 0).
	// 링크 인스턴스의 이 함수는 메인 그래프 순회 중 메인의 ThreadSafe 업데이트 뒤에 같은 스레드에서 돈다 → 같은 프레임 값 (AnimInstanceProxy::UpdateAnimation_WithRoot)
	const FRotator AimDelta = (Snapshot.BaseAimRotation - Snapshot.ActorRotation).GetNormalized();
	AimYaw   = FRotator::NormalizeAxis(AimDelta.Yaw - Main->RootYawOffset);
	AimPitch = AimDelta.Pitch;
}
