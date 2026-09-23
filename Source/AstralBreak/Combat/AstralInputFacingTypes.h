#pragma once

#include "CoreMinimal.h"
#include "AstralInputFacingTypes.generated.h"

/** 튜닝 값 — 단일 원본은 NotifyState에 인스턴싱된 Modifier 템플릿 (NotifyState 자체에 중복 보관하지 않는다) */
USTRUCT(BlueprintType)
struct ASTRALBREAK_API FAstralInputFacingSettings
{
	GENERATED_BODY()

	/** 실제 경과 시간 기준 추가 회전 속도 (도/초). 목표 각도 제한이 아니다 — 남은 구간이 짧으면 도달을 보장하지 않고 끝에서 스냅하지 않는다 */
	UPROPERTY(EditAnywhere, Category = "Astral|InputFacing", Meta = (ClampMin = "0.0"))
	float RotationSpeed = 720.f;

	/** 정규화 전 0~1 입력 크기 문턱 — 미만이면 무입력으로 본다 */
	UPROPERTY(EditAnywhere, Category = "Astral|InputFacing", Meta = (ClampMin = "0.0", ClampMax = "1.0"))
	float InputThreshold = 0.1f;

	/**
	 * 최단각이 180도에서 이 폭 안이면 제출 부호를 수용한다 (도).
	 * 부호를 새로 고르는 규칙이 아니라 클라가 고른 부호를 서버가 받아들이는 허용 오차 — 없으면 클라 +179.9/서버 -179.9에서 서버가 보정까지 정지한다
	 */
	UPROPERTY(EditAnywhere, Category = "Astral|InputFacing", Meta = (ClampMin = "0.0", ClampMax = "10.0"))
	float OppositeTurnAcceptanceDegrees = 2.f;

	bool IsValid() const;
};

/**
 * move당 입력 샘플 — 논리 26비트 (Yaw 16 · 크기 8 · 억제 1 · 부호 1).
 * 소유 클라가 SetMoveFor에서 확정해 CMC 이동 패킷으로 보내고, 서버·재실행은 그대로 쓴다. 로컬 첫 실행부터 양자화·복원값을 쓴다
 */
struct ASTRALBREAK_API FAstralInputFacingSample
{
	/** 월드 수평 입력 방향 (AstralFacing::QuantizeYaw). 크기 0이면 0으로 정규화 */
	uint16 WorldInputYaw = 0;

	/** 정규화 전 입력 크기 [0,1] → [0,255] */
	uint8 InputMagnitude = 0;

	/** 락온 선택 또는 기존 Facing 소유권 — 입력 회전 억제 요청. 크기와 독립 */
	bool bSuppressInputFacing = false;

	/** 회전 부호 — 소유 클라 한 곳이 고른다. 서버·재실행은 다시 고르지 않는다 */
	bool bPositiveTurn = true;

	bool HasInput() const { return InputMagnitude > 0; }
	float GetInputYaw() const;
	float GetInputMagnitude() const;

	/** 크기 0이면 Yaw·부호를 기본값으로 — 억제 플래그는 유지 */
	void NormalizeNone();

	bool operator==(const FAstralInputFacingSample& Other) const;
	bool operator!=(const FAstralInputFacingSample& Other) const { return !(*this == Other); }

	/** 비트 직렬화 — 저장·로드 공용. 로드 후 NormalizeNone */
	void SerializeBits(FArchive& Ar);

	FString ToString() const;
};

namespace AstralInputFacing
{
	/** 정확한 180도 동률에서 클라가 쓰는 기본 부호 */
	constexpr bool DefaultPositiveTurn = true;

	/** 직렬화 비트 수 — 패킷 비용 계측·테스트 기준 */
	constexpr int64 SampleNumBits = 16 + 8 + 1 + 1;

	ASTRALBREAK_API uint8 QuantizeMagnitude(float Magnitude01);
	ASTRALBREAK_API float DequantizeMagnitude(uint8 Quantized);

	/** 부호 선택 (소유 클라 전용) — CurrentYaw에서 TargetYaw로의 최단각 부호. 정확한 180도는 DefaultPositiveTurn */
	ASTRALBREAK_API bool ChooseTurnSign(float CurrentYaw, float TargetYaw);

	/**
	 * 월드 수평 입력 → 샘플. 대각 크기는 1로 클램프. 부호는 양자화·복원한 목표와 CurrentActorYaw로 고른다.
	 * 크기 0이면 NormalizeNone (억제는 그대로)
	 */
	ASTRALBREAK_API FAstralInputFacingSample MakeSample(const FVector& WorldInput, float CurrentActorYaw, bool bSuppress);

	/**
	 * 이번 평가의 추가 회전량 (도, 부호 포함
	 *  - |SignedError| ≥ 180 - OppositeAcceptanceDegrees: 제출 부호 수용, 그 방향 거리(예: -179에 + → 181)로 제한
	 *  - 그 밖에 제출 부호가 최단각 부호와 다르면 0
	 *  - 나머지: 목표를 넘지 않는 속도 제한 회전
	 * @param SignedError 원본 루트모션을 적용한 예상 Yaw → 목표 Yaw 최단각 (FindDeltaAngleDegrees)
	 * @param MaxStep RotationSpeed × ActiveSeconds
	 */
	ASTRALBREAK_API float ComputeTurnDelta(float SignedError, bool bPositiveTurn, float MaxStep, float OppositeAcceptanceDegrees);

	/**
	 * 이번 평가 구간의 교차 시간 (초) — 애니메이션 시간 교차 / PlayRate, [0, DeltaSeconds]로 제한.
	 * 정방향 연속 재생만 지원 — 역행·PlayRate ≤ 0은 0 (지원하지 않는 시간 점프를 회전으로 환산하지 않는다)
	 */
	ASTRALBREAK_API float ComputeActiveSeconds(float PreviousPosition, float CurrentPosition, float WindowStart, float WindowEnd, float PlayRate, float DeltaSeconds);

	/**
	 * 원본 로컬(메시 공간) 루트모션 회전을 적용한 뒤의 액터 월드 회전 — 엔진 변환(DeltaWorld = C·L·C⁻¹, New = DeltaWorld·Actor)을 그대로 따른다.
	 * @param MeshRelativeQuat 메시의 액터 기준 상대 회전 (UMotionWarpingBaseAdapter::GetBaseVisualRotationOffset)
	 */
	ASTRALBREAK_API FQuat PredictActorRotation(const FQuat& ActorQuat, const FQuat& MeshRelativeQuat, const FQuat& LocalRootMotionRotation);

	/** 추가 월드 Yaw 회전을 로컬 루트모션 회전에 합성 — L' = C⁻¹·Add·C·L. Translation은 호출자가 보존 */
	ASTRALBREAK_API FQuat ComposeLocalRotation(const FQuat& ActorQuat, const FQuat& MeshRelativeQuat, const FQuat& LocalRootMotionRotation, float AdditionalWorldYawDegrees);
}
