#pragma once

#include "CoreMinimal.h"
#include "GameplayEffectTypes.h"
#include "Animation/AnimInstance.h"
#include "Animation/AstralTurnInPlace.h"
#include "AstralAnimInstance.generated.h"

class APawn;
class USkeletalMeshComponent;
class UAbilitySystemComponent;
class UCharacterMovementComponent;
class UAstralCharacterMovementComponent;

struct FAstralAnimSnapshot
{
	/** 월드 속도 (수평/수직 포함) */
	FVector WorldVelocity = FVector::ZeroVector;

	/** 월드 가속도 (이동 입력 의도) */
	FVector WorldAcceleration = FVector::ZeroVector;

	/** 액터 회전 (LocalVelocity/MovementDirection 계산용) */
	FRotator ActorRotation = FRotator::ZeroRotator;

	/** 공중 여부 (MovementMode == Falling). 상승/하강 구분은 WorldVelocity.Z로 ThreadSafe에서 계산 */
	bool bIsInAir = false;

	/** 지면 이동 여부 (MovementMode == Walking/NavWalking). IsMovingOnGround() */
	bool bIsOnGround = false;

	/** 발밑 지면까지 거리 */
	float GroundDistance = 0.0f;

	/** 조준 기준 회전 — APawn::GetBaseAimRotation (소유자는 컨트롤 회전, 시뮬 프록시는 RemoteViewPitch + 액터 Yaw) */
	FRotator BaseAimRotation = FRotator::ZeroRotator;

	/** ASC 태그 State.Ranged.Aiming (게임 스레드에서 읽어 스냅샷). 전투 스타일은 AnimInstance 가 알 필요 없다 — 무기별 그래프는 장비 매니저의 레이어 링크가 고른다 */
	bool bAiming = false;

	/** 액터 Yaw 의 이번 프레임 변화량(정규화) — 제자리 회전의 누적 입력 */
	float YawDeltaSinceLastUpdate = 0.f;

	/** 전신 몽타주(FullBodyMontageSlot) 재생 중 — 제자리 회전 누적 금지. 상체 슬롯 몽타주(사격)는 허용 — Lyra 처럼 조준 사격 중에도 발을 붙여 둔다 */
	bool bFullBodyMontagePlaying = false;

	/** 왼손 파지점 (WeaponReferenceBone 공간) — 장비 매니저가 게임 스레드에서 넣은 값의 사본 */
	bool bHasLeftHandGrip = false;
	FTransform LeftHandGrip = FTransform::Identity;

	/** 총구 (WeaponReferenceBone 공간, +X = 총열) — 장비 매니저가 넣은 값의 사본 */
	bool bHasMuzzle = false;
	FTransform Muzzle = FTransform::Identity;

	/** 최종 조준 보정 조준점 (컴포넌트 공간) — 조준 중 ∧ 총구 있음일 때만 계산 */
	bool bHasAimTarget = false;
	FVector AimTarget = FVector::ZeroVector;
};


UCLASS()
class ASTRALBREAK_API UAstralAnimInstance : public UAnimInstance
{
	GENERATED_BODY()
	
public:

	UAstralAnimInstance(const FObjectInitializer& ObjectInitializer);

	virtual void InitializeWithAbilitySystem(UAbilitySystemComponent* ASC);

	/**
	 * 메시의 메인 AnimInstance (Lyra GetMainAnimBPThreadSafe 역할). 링크된 레이어 공급자 ABP 가 Property Access 경로
	 * `GetMainAnimInstance.RootYawOffset` 처럼 베이스의 값을 읽는다 — 제자리 회전·조준값은 베이스 하나가 계산하고 공급자는 읽기만.
	 * 메인 자신이면 this. 포인터는 게임 스레드(NativeUpdateAnimation)에서 캐시하고, 링크 인스턴스의 스레드 안전 업데이트는
	 * 메인 그래프 순회 중 같은 스레드에서 메인의 ThreadSafe 업데이트 뒤에 돌므로 같은 프레임 값을 본다
	 */
	UFUNCTION(BlueprintPure, Category = "Astral|Animation", Meta = (BlueprintThreadSafe))
	UAstralAnimInstance* GetMainAnimInstance() const;

	/**
	 * 왼손 파지점 — 손에 든 양손 무기의 파지 소켓을 WeaponReferenceBone(오른손) 공간으로 환산한 트랜스폼. 무기는 손 본에 붙은 강체라 자세와 무관한 상수다.
	 * 장비 매니저가 무기 부착·외형·AnimBP 가 바뀔 때 메인 인스턴스에 넣는다(게임 스레드 이벤트 — 매 프레임 조회 없음). 스냅샷을 거쳐 스레드 안전 업데이트가
	 * bHasLeftHandGrip · LeftHandGripLocation/Rotation 으로 노출하고, 공급자 레이어의 왼손 IK 가 GetMainAnimInstance 경로로 읽는다
	 */
	void SetLeftHandGrip(const FTransform& GripInReferenceBoneSpace);
	void ClearLeftHandGrip();

	/**
	 * 총구 — 손에 든 원거리 무기의 총구 소켓(+X = 총열)을 WeaponReferenceBone 공간으로 환산한 트랜스폼. 왼손 파지점과 같은 경로·같은 수명(장비 매니저 이벤트).
	 * 베이스 그래프의 최종 조준 보정 노드(FAnimNode_AstralAimCorrection)가 이 축을 조준점으로 돌린다. 근접 무기·맨손이면 Clear
	 */
	void SetMuzzle(const FTransform& MuzzleInReferenceBoneSpace);
	void ClearMuzzle();

	FName GetWeaponReferenceBone() const { return WeaponReferenceBone; }

protected:
	//~ UAnimInstance
	virtual void NativeInitializeAnimation() override;
	virtual void NativeUpdateAnimation(float DeltaSeconds) override;
	virtual void NativeThreadSafeUpdateAnimation(float DeltaSeconds) override;
	//~ End UAnimInstance

protected:
	UPROPERTY(EditDefaultsOnly, Category = "GameplayTags")
	FGameplayTagBlueprintPropertyMap GameplayTagPropertyMap;
	
	// 수평 속도 (cm/s). Velocity.Size2D()
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	float Speed = 0.0f;

	// 수평 가속도 크기. 이동 입력 세기
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	float Acceleration = 0.0f;

	// 캐릭터 forward 대비 velocity 각도 (-180~180). strafe/락온 대비. Phase 1은 사실상 0
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	float MovementDirection = 0.0f;

	// 지면 여부 (Walking/NavWalking). IsMovingOnGround()
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	bool bIsOnGround = false;

	// 공중 여부 (상승/하강 모두 포함). State Machine의 지상↔공중 전환에 사용
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	bool bIsInAir = false;

	// 상승 중 (공중 && Z > 0). 점프로 올라가는 구간
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	bool bIsJumping = false;

	// 하강 중 (공중 && 상승 아님). 떨어지는 구간
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	bool bIsFalling = false;

	// 이동 입력 존재 여부 (가속도 기반)
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	bool bHasMovementInput = false;

	// 발밑 지면까지 거리 (착지 예측용)
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Locomotion")
	float GroundDistance = 0.0f;

	// ---- 조준 (ASC 태그 스냅샷) — 무기 종류·스타일은 여기 두지 않는다 (무기별 그래프 = 장비 계열의 AnimLayerClass 링크) ----

	// 사격 자세 유지 중 (State.Ranged.Aiming — 원거리 GA가 발사마다 갱신하는 지속 GE). 조준 로코모션(strafe)·AimOffset 알파.
	// 태그는 메인 인스턴스만 읽는다(ASC 결합은 메인만) — 링크된 공급자 인스턴스의 값도 메인 것이라 공급자 그래프는 자기 bIsAiming 을 그대로 바인딩한다
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Combat")
	bool bIsAiming = false;

	// 조준 방향 − 몸 방향 Yaw (-180~180), 제자리 회전 오프셋을 뺀 값 (메시가 루트에서 돌아간 만큼 상체가 되돌려 조준). AimOffset X.
	// 오프셋은 항상 메인 인스턴스의 것 — 링크된 공급자 인스턴스의 AimYaw 도 같은 값이라 공급자 그래프는 자기 AimYaw 를 그대로 바인딩한다
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Combat")
	float AimYaw = 0.0f;

	// 조준 Pitch (-180~180, 보통 ±90 안). AimOffset Y
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|Combat")
	float AimPitch = 0.0f;

	// ---- 제자리 회전 (Lyra TurnInPlace — 계산은 FAstralTurnInPlaceState, 정책은 여기) ----

	/** 튜닝값 — ABP 클래스 기본값에서 조정 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|TurnInPlace")
	FAstralTurnInPlaceSettings TurnInPlaceSettings;

	/** 이 속도(cm/s) 미만이고 이동 입력이 없을 때만 발을 붙여 둔다(오프셋 누적). 조준 중 ∧ 지상 ∧ 전신 몽타주 없음 도 함께 본다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|TurnInPlace", Meta = (ClampMin = "0.0"))
	float TurnInPlaceAccumulateMaxSpeed = 10.f;

	/** 전신 몽타주 슬롯 — 이 슬롯에 몽타주 가중치가 있으면 누적하지 않는다 (루트를 돌리면 전신 몽타주가 틀어진다). 상체 슬롯(UpperBody)의 사격 몽타주는 무시 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|TurnInPlace")
	FName FullBodyMontageSlot = TEXT("DefaultSlot");

	/**
	 * 조준 진입(State.Ranged.Aiming 상승 에지) 뒤 이 시간(초) 동안은 누적하지 않는다 — 메시가 액터와 함께 돈다(피벗).
	 * 비조준에서 사격하면 몸이 조준 회전 속도(HeroMovementComponent::AimingRotationRate)로 카메라 쪽으로 도는데, 그 회전까지 발을 붙여 상쇄하면
	 * 하체가 등진 채 남고 AimOffset(±90)이 총을 크로스헤어까지 못 돌린다. 180° ÷ 조준 회전 속도보다 길어야 한다. 복제 태그 기준이라 모든 머신이 같은 규칙
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|TurnInPlace", Meta = (ClampMin = "0.0"))
	float AimEntryPivotTime = 0.3f;

	// 루트 본 Yaw 오프셋(도) — 베이스 루트 그래프의 RotateRootBone.Yaw. 조준 중 서 있으면 액터 회전을 상쇄, 아니면 0
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|TurnInPlace")
	float RootYawOffset = 0.0f;

	// |오프셋| > 임계 ∧ 누적 중 — Idle → TurnInPlaceRotation (공급자 ABP 의 Idle 상태머신 전이 규칙)
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|TurnInPlace")
	bool bWantsTurnInPlace = false;

	// 턴 클립의 회전 구간이 끝남 — TurnInPlaceRotation → TurnInPlaceRecovery
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|TurnInPlace")
	bool bTurnInPlaceRotationFinished = false;

	// 재생할 턴 클립 — 공급자 ABP 의 BlendListByEnum 이 고른다
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|TurnInPlace")
	EAstralTurnInPlaceKind TurnInPlaceKind = EAstralTurnInPlaceKind::None;

	// 턴 클립이 활성인 동안 흐른 시간 — Recovery 상태 SequencePlayer 의 StartPosition (회전이 끝난 지점부터 이어서)
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|TurnInPlace")
	float TurnInPlaceAnimTime = 0.0f;

	// 디버그 — 가중 해제한 RemainingTurnYaw
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|TurnInPlace")
	float TurnYawCurveValue = 0.0f;

	// 디버그 — 스레드 안전 업데이트가 읽은 지난 프레임 커브 원값 (TurnYawWeight · RemainingTurnYaw). PIE 프로브가 전파·타이밍을 본다
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|TurnInPlace")
	float TurnInPlaceDebugWeight = 0.0f;

	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|TurnInPlace")
	float TurnInPlaceDebugRemaining = 0.0f;

	// 디버그 — 이번 프레임 누적 모드였는지 (조준 ∧ 지상 ∧ 정지 ∧ 전신 몽타주 없음)
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|TurnInPlace")
	bool bTurnInPlaceAccumulating = false;

	/**
	 * 손에 든 무기가 붙는 본 — 왼손 파지점·총구를 이 본 공간으로 받는다. 공급자 레이어가 ik_hand_gun 에 복사하는 본(CopyBone 원본)·
	 * 베이스 조준 보정 노드의 WeaponBone 과 같아야 한다 (무기 계열의 손 부착 소켓도 이 본 — DA_EF_Rifle.AttachSocket = hand_r)
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Weapon")
	FName WeaponReferenceBone = TEXT("hand_r");

	// ---- 왼손 IK (양손 무기 파지점 — 값은 무기 메시 소켓이 정하고 장비 매니저가 넣는다) ----

	// 왼손 IK 목표가 있다(양손 무기를 손에 듦) — LeftHandIKAlpha 의 상한
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|LeftHandIK")
	bool bHasLeftHandGrip = false;

	// 파지점 위치·회전 (기준 본 공간) — 공급자 레이어 ModifyBone(ik_hand_l, 부모 본 공간 Replace)
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|LeftHandIK")
	FVector LeftHandGripLocation = FVector::ZeroVector;

	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|LeftHandIK")
	FRotator LeftHandGripRotation = FRotator::ZeroRotator;

	/** 애니메이션 커브 — 1 이면 그 클립의 왼손은 총을 쥐고 있지 않다(점프·낙하·착지 클립, 장전 몽타주). Lyra 명명. 무기 무관 클립에 넣어도 파지점이 없으면 무해 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|LeftHandIK")
	FName LeftHandIKDisableCurve = TEXT("DisableLHandIK");

	/** 왼손 IK 알파가 목표를 따라가는 시간(초, 0 → 1 전체) — 커브는 상태머신 크로스페이드로 이미 부드럽고, 이 보간은 조준 진입·해제 같은 계단을 메운다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|LeftHandIK", Meta = (ClampMin = "0.0"))
	float LeftHandIKBlendTime = 0.15f;

	// 왼손 IK 알파(0~1) = 파지점 있음 × (1 − DisableLHandIK × (1 − AimPoseAlpha)) 를 LeftHandIKBlendTime 에 걸쳐 따라간 값.
	// 클립이 "왼손이 비었다" 고 표시하면 놓고, 조준 오버레이가 상체를 두 손 조준 자세로 덮는 만큼 그 표시를 지운다(조준 점프는 잡는다).
	// 공급자 Aim_UpperBody 의 TwoBoneIK 알파 · 왼손 손가락(쥔 모양) 블렌드 가중치. 메인이 계산(커브는 메인의 최종 포즈), 링크 인스턴스는 복사
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|LeftHandIK")
	float LeftHandIKAlpha = 0.0f;

	// ---- 무기 포즈 오버레이 (공급자 레이어 Locomotion_WeaponOverlay — 베이스 상태머신 출력 뒤·슬롯 앞, 상태와 무관하게 한 곳) ----

	/** 조준 오버레이 가중치가 조준 진입·해제를 따라가는 시간(초) — 공급자 Idle/Move 의 조준 BlendListByBool(0.2초)과 맞춘다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|WeaponOverlay", Meta = (ClampMin = "0.0"))
	float AimPoseBlendTime = 0.2f;

	// 조준 오버레이 가중치(0~1) — bIsAiming 을 AimPoseBlendTime 에 걸쳐 따라간 값. 공급자 오버레이 레이어가 무기의 조준 상체 포즈를 이 가중치로 덮는다
	// (점프·낙하처럼 무기와 무관한 클립 위에서도 AimOffset 기준 포즈가 된다). 메인이 계산, 링크 인스턴스는 복사 — 공급자 그래프는 자기 값을 읽는다
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|WeaponOverlay")
	float AimPoseAlpha = 0.0f;

	// 손이 무기를 떠난 정도(0~1) = DisableLHandIK × (1 − AimPoseAlpha) 를 LeftHandIKBlendTime 에 걸쳐 따라간 값 — 왼손 IK 를 끄는 것과 같은 신호.
	// 무기 무관 클립(점프·낙하·착지)이 상체를 쥐고 있을 때 공급자 오버레이가 무기 든 팔을 그 무기의 휴대 자세로 덮는 가중치(라이플 = 오른팔 Rifle_Idle).
	// 파지점과 무관(근접은 오버레이가 통과라 읽지 않는다). 메인이 계산, 링크 인스턴스는 복사
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|WeaponOverlay")
	float HandsFreeAlpha = 0.0f;

	// ---- 최종 조준 보정 (베이스 루트 RotateRootBone 뒤 AstralAimCorrection 노드 — AO 가 남긴 총열 오차를 척추로 마저 돌린다) ----

	/**
	 * 조준점이 트레이스 시작(카메라 레이 위 총구 투영점)에서 이보다 가까우면 이 거리로 민다 — 벽에 붙어 코앞을 조준할 때 시차 보정으로 상체가 크게 꺾이지 않게.
	 * 이 거리 안쪽 표적만큼 총열이 실제 탄도와 어긋난다(투사체는 여전히 실제 조준점으로 간다 — ResolveShot). 1m 표적의 보정은 ~18° 로 최대 보정각(노드 30°) 안
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|AimCorrection", Meta = (ClampMin = "0.0"))
	float AimCorrectionMinDistance = 50.f;

	/**
	 * 조준점 거리 보간 속도(1/s, 0 = 즉시) — 역거리(시차 각)로 보간한다. 크로스헤어가 가까운 벽과 먼 배경의 경계를 넘을 때 시차 보정이 한 프레임에 튀지 않게.
	 * 방향(카메라)은 즉시 따른다
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|AimCorrection", Meta = (ClampMin = "0.0"))
	float AimCorrectionDistanceInterpSpeed = 12.f;

	// 보정 켬 — 조준 중 ∧ 총구 있음 ∧ 조준점 있음. 노드 알파(bool)
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|AimCorrection")
	bool bAimCorrectionActive = false;

	// 조준점 (컴포넌트 공간) — 로컬·서버의 플레이어는 발사와 같은 카메라 조준점(AstralRangedAim), 시뮬 프록시는 서버가 복제한 그 점
	// (AAstralCharacter_Hero::ObservedAimTarget), AI·복제 전은 BaseAimRotation 방향의 먼 점
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|AimCorrection")
	FVector AimCorrectionTarget = FVector::ZeroVector;

	// 총구 (WeaponReferenceBone 공간, +X = 총열)
	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|AimCorrection")
	FVector MuzzleLocation = FVector::ZeroVector;

	UPROPERTY(BlueprintReadOnly, Transient, Category = "Astral|AimCorrection")
	FRotator MuzzleRotation = FRotator::ZeroRotator;

private:
	/** 최종 조준 보정 조준점(월드 → 컴포넌트 공간)을 구한다 — 게임 스레드(NativeUpdateAnimation), 메인 인스턴스 ∧ 조준 중 ∧ 총구 있음일 때만 */
	bool ComputeAimCorrectionTarget(const USkeletalMeshComponent& Mesh, float DeltaSeconds, FVector& OutTargetComponentSpace);

	/** 게임 스레드 쪽 파지점·총구 — Set/Clear 는 애님 워커와 겹칠 수 있는 게임 스레드 이벤트라 직접 노출하지 않고 NativeUpdateAnimation 이 스냅샷으로 옮긴다 */
	TOptional<FTransform> PendingLeftHandGrip;
	TOptional<FTransform> PendingMuzzle;

	/** 보간 중인 조준점 거리의 역수 (트레이스 시작 기준, 1/cm — 시차 각에 비례). 음수 = 다음 계산에서 바로 맞춘다(조준 진입·총구 교체) */
	float SmoothedAimInverseDistance = -1.f;

	FAstralAnimSnapshot Snapshot;
	FAstralTurnInPlaceState TurnInPlace;

	/** 액터 Yaw 추적 — 첫 프레임·폰 교체 뒤에는 델타 0 */
	float PreviousActorYaw = 0.f;
	bool bHasPreviousActorYaw = false;

	/** 조준 진입 피벗 창 — 남은 시간, 직전 프레임 조준 여부 (스레드 안전 업데이트에서만 쓴다) */
	float AimEntryPivotRemaining = 0.f;
	bool bWasAimingLastUpdate = false;

	/** 메시의 메인 AnimInstance (게임 스레드 캐시). 메인 자신이면 this */
	UPROPERTY(Transient)
	TObjectPtr<UAstralAnimInstance> MainAnimInstance;

	/** 태그 조회용 — InitializeWithAbilitySystem 에서 결합(메인 인스턴스만). 게임 스레드에서만 읽는다 */
	TWeakObjectPtr<UAbilitySystemComponent> BoundASC;

	UPROPERTY(Transient)
	TObjectPtr<APawn> OwningPawn;

	UPROPERTY(Transient)
	TObjectPtr<UAstralCharacterMovementComponent> AstralMovementComponent;
};
