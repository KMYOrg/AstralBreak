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
	ApplyCameraProfile(false);

	if (Targeting)
	{
		Targeting->OnTargetingChanged.RemoveDynamic(this, &ThisClass::HandleTargetingChanged);
	}

	Super::EndPlay(EndPlayReason);
}

void UAstralHeroCameraComponent::HandleTargetingChanged()
{
	const bool bLocked = IsTrackingTarget();
	ApplyCameraProfile(bLocked);
	SetComponentTickEnabled(bLocked);
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

void UAstralHeroCameraComponent::ApplyCameraProfile(bool bLockOn)
{
	if (!CameraBoom)
	{
		return;
	}

	if (bLockOn && !bLockOnProfileApplied)
	{
		DefaultCameraLagSpeed = CameraBoom->CameraLagSpeed;
		CameraBoom->CameraLagSpeed = LockCameraLagSpeed;
		bLockOnProfileApplied = true;
	}
	else if (!bLockOn && bLockOnProfileApplied)
	{
		CameraBoom->CameraLagSpeed = DefaultCameraLagSpeed;
		bLockOnProfileApplied = false;
	}
}

void UAstralHeroCameraComponent::UpdateLockOnCamera(float DeltaTime)
{
	APlayerController* PC = GetController<APlayerController>();
	if (!PC)
	{
		return;
	}

	// 조준 원점 = 카메라 POV. 조준점은 캡슐 중심 (발밑을 보면 카메라가 내려앉는다)
	FVector ViewLocation;
	FRotator ViewRotation;
	PC->GetPlayerViewPoint(ViewLocation, ViewRotation);

	const FVector ToTarget = Targeting->GetEffectiveTarget().GetAimLocation() - ViewLocation;
	if (ToTarget.IsNearlyZero())
	{
		return;
	}

	const FRotator Desired = ToTarget.Rotation();
	const FRotator Current = PC->GetControlRotation().GetNormalized();
	FRotator New = Current;

	// Yaw — 항상 보조 (최단 경로 보간)
	New.Yaw = FMath::RInterpTo(Current, Desired, DeltaTime, Params.YawInterpSpeed).Yaw;

	// Pitch — 부분 자유. 임계 안이면 플레이어 입력 그대로, 밖이면 타겟이 임계 안으로 들어오는 경계까지만 보간
	const float PitchDelta = FMath::FindDeltaAngleDegrees(Current.Pitch, Desired.Pitch);
	if (FMath::Abs(PitchDelta) > Params.PitchAssistThreshold)
	{
		// Pitch 한계는 카메라 매니저의 값 — 여기 상수 사본을 두면 한계를 바꿀 때 조용히 어긋난다 (refactor §5)
		const APlayerCameraManager* PCM = PC->PlayerCameraManager;
		const float MinPitch = PCM ? PCM->ViewPitchMin : -89.0f;
		const float MaxPitch = PCM ? PCM->ViewPitchMax :  89.0f;

		const float BoundaryPitch = Desired.Pitch - FMath::Sign(PitchDelta) * Params.PitchAssistThreshold;
		New.Pitch = FMath::Clamp(FMath::FInterpTo(Current.Pitch, BoundaryPitch, DeltaTime, Params.PitchInterpSpeed), MinPitch, MaxPitch);
	}

	New.Roll = 0.0f;
	PC->SetControlRotation(New);
}
