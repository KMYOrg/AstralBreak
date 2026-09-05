#include "AstralHeroCameraComponent.h"

#include "AstralLogChannels.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Character/Hero/Components/AstralTargetingComponent.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"

UAstralHeroCameraComponent::UAstralHeroCameraComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// 락온 중에만 틱 — OnTargetingChanged가 켜고 끈다. 락온을 한 번도 안 켠 세션에선 틱하지 않는다
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = false;

	// 로컬 표현 — 서버로 가지 않는다 (타겟 전달은 5단계 TargetData)
	SetIsReplicatedByDefault(false);
}

void UAstralHeroCameraComponent::InitializeCamera(USpringArmComponent* InCameraBoom, UCameraComponent* InFollowCamera, UAstralTargetingComponent* InTargeting)
{
	CameraBoom = InCameraBoom;
	FollowCamera = InFollowCamera;
	Targeting = InTargeting;
}

void UAstralHeroCameraComponent::BeginPlay()
{
	Super::BeginPlay();

	if (Targeting)
	{
		Targeting->OnTargetingChanged.AddDynamic(this, &ThisClass::HandleTargetingChanged);
	}
	else
	{
		UE_LOG(LogAstral, Warning, TEXT("[HeroCamera] %s: TargetingComponent 미주입 — InitializeCamera를 소유 폰이 호출해야 한다"), *GetNameSafe(GetOwner()));
	}

	HandleTargetingChanged();
}

void UAstralHeroCameraComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (Targeting)
	{
		Targeting->OnTargetingChanged.RemoveDynamic(this, &ThisClass::HandleTargetingChanged);
	}

	Super::EndPlay(EndPlayReason);
}

void UAstralHeroCameraComponent::HandleTargetingChanged()
{
	const bool bLocked = IsTrackingTarget();
	SetComponentTickEnabled(bLocked);

#if !UE_BUILD_SHIPPING
	// 락온 시작·타겟 교체마다 반감기 측정을 새로 시작
	if (bLocked)
	{
		ResetDebugStats();
	}
#endif
}

bool UAstralHeroCameraComponent::IsTrackingTarget() const
{
	return Targeting
		&& Targeting->GetMode() == EAstralTargetingMode::HardLocked
		&& Targeting->GetEffectiveTarget().IsSet();
}

void UAstralHeroCameraComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	const APawn* Pawn = GetPawn<APawn>();
	if (!Pawn || !Pawn->IsLocallyControlled())
	{
		return;
	}

	// 유효성 재검사 — 타겟 액터 파괴 후 TargetingComponent의 ClearLock 이벤트가 오기까지의 한 프레임을 건너뛴다
	if (!IsTrackingTarget())
	{
		return;
	}

	UpdateLockOnCamera(DeltaTime);
}

void UAstralHeroCameraComponent::UpdateLockOnCamera(float DeltaTime)
{
	APlayerController* PC = GetController<APlayerController>();
	if (!PC)
	{
		return;
	}

	// 조준 원점 = 카메라 POV (Phase 2 확정 — 헤더 주석), 조준점 = 캡슐 중심 (발밑을 보면 카메라가 내려앉는다)
	FVector ViewLocation;
	FRotator ViewRotation;
	PC->GetPlayerViewPoint(ViewLocation, ViewRotation);

	const FVector AimLocation = Targeting->GetEffectiveTarget().GetAimLocation();

#if !UE_BUILD_SHIPPING
	UpdateDebugStats(DeltaTime, PC, ViewLocation, ViewRotation, AimLocation);
#endif

	const FVector ToTarget = AimLocation - ViewLocation;
	if (ToTarget.IsNearlyZero())
	{
		return;
	}

	const FRotator Desired = ToTarget.Rotation();
	// 정규화 필수 — 카메라 매니저가 클램프한 컨트롤 Pitch는 0~360으로 저장된다 (아래 20° = 340)
	const FRotator Current = PC->GetControlRotation().GetNormalized();
	FRotator New = Current;

	// Yaw — 항상 보조 (최단 경로 보간)
	New.Yaw = FMath::RInterpTo(Current, Desired, DeltaTime, Params.YawInterpSpeed).Yaw;

	// Pitch — 부분 자유. 임계 안이면 플레이어 입력 그대로, 밖이면 타겟이 임계 안으로 들어오는 경계까지만 보간
	const float PitchDelta = FMath::FindDeltaAngleDegrees(Current.Pitch, Desired.Pitch);
	if (FMath::Abs(PitchDelta) > Params.PitchAssistThreshold)
	{
		// Pitch 한계는 카메라 매니저의 값 — 여기 상수 사본을 두면 한계를 바꿀 때 조용히 어긋난다
		const APlayerCameraManager* PCM = PC->PlayerCameraManager;
		const float MinPitch = PCM ? PCM->ViewPitchMin : -89.0f;
		const float MaxPitch = PCM ? PCM->ViewPitchMax :  89.0f;

		const float BoundaryPitch = Desired.Pitch - FMath::Sign(PitchDelta) * Params.PitchAssistThreshold;
		New.Pitch = FMath::Clamp(FMath::FInterpTo(Current.Pitch, BoundaryPitch, DeltaTime, Params.PitchInterpSpeed), MinPitch, MaxPitch);
	}

	New.Roll = 0.0f;
	PC->SetControlRotation(New);
}

#if !UE_BUILD_SHIPPING
void UAstralHeroCameraComponent::ResetDebugStats()
{
	DebugStats = FAstralLockOnCameraDebugStats();

	// 초기 Yaw 오차는 지금 당장 — 첫 틱을 기다리면 한 프레임 보정된 값이 기준이 된다
	const APlayerController* PC = GetController<APlayerController>();
	if (PC && Targeting)
	{
		FVector ViewLocation;
		FRotator ViewRotation;
		PC->GetPlayerViewPoint(ViewLocation, ViewRotation);

		const FVector ToTarget2D = (Targeting->GetEffectiveTarget().GetAimLocation() - ViewLocation).GetSafeNormal2D();
		if (!ToTarget2D.IsNearlyZero())
		{
			DebugStats.InitialYawErrorDeg = FMath::FindDeltaAngleDegrees(ViewRotation.Yaw, ToTarget2D.Rotation().Yaw);
		}
	}
}

void UAstralHeroCameraComponent::UpdateDebugStats(float DeltaTime, const APlayerController* PC, const FVector& ViewLocation, const FRotator& ViewRotation, const FVector& AimLocation)
{
	DebugStats.ElapsedSinceLock += DeltaTime;

	if (const APawn* Pawn = GetPawn<APawn>())
	{
		DebugStats.Distance = FVector::Dist(Pawn->GetActorLocation(), AimLocation);
	}

	// 플레이어가 보는 중심 편차 — 실제 카메라 시선 기준
	const FVector ToTarget = AimLocation - ViewLocation;
	if (!ToTarget.IsNearlyZero())
	{
		const FRotator ToTargetRot = ToTarget.Rotation();
		DebugStats.YawErrorDeg = FMath::FindDeltaAngleDegrees(ViewRotation.Yaw, ToTargetRot.Yaw);
		DebugStats.PitchErrorDeg = FMath::FindDeltaAngleDegrees(ViewRotation.Pitch, ToTargetRot.Pitch);
	}

	// 화면 투영 — 중심 0, [-1, 1]
	FVector2D ScreenPos;
	int32 ViewportX = 0;
	int32 ViewportY = 0;
	PC->GetViewportSize(ViewportX, ViewportY);
	DebugStats.bOnScreen = PC->ProjectWorldLocationToScreen(AimLocation, ScreenPos, /*bPlayerViewportRelative=*/true) && ViewportX > 0 && ViewportY > 0;
	if (DebugStats.bOnScreen)
	{
		DebugStats.ScreenOffset.X = (ScreenPos.X / ViewportX) * 2.0f - 1.0f;
		DebugStats.ScreenOffset.Y = (ScreenPos.Y / ViewportY) * 2.0f - 1.0f;
	}

	// 반감기 — |오차|가 초기값의 절반 아래로 처음 내려간 시각. 초기 오차가 작으면(이미 정면) 의미 없음
	if (DebugStats.YawHalfLifeSeconds < 0.f && FMath::Abs(DebugStats.InitialYawErrorDeg) > 1.0f
		&& FMath::Abs(DebugStats.YawErrorDeg) <= FMath::Abs(DebugStats.InitialYawErrorDeg) * 0.5f)
	{
		DebugStats.YawHalfLifeSeconds = DebugStats.ElapsedSinceLock;
	}
}
#endif
