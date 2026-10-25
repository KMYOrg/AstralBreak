#pragma once

#include "AnimMcpBodyClearance.h"
#include "AnimMcpFingerChains.h"
#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UAnimSequence;
class USkeleton;
struct FAnimMcpError;

/**
 * 애니메이션 검증 (AI 애니 생성 Phase 1 — Docs/AIAnimation/DevelopmentGuide.md §13 · ArchitectureAudit.md §5 · §10 validate_animation).
 * 측정은 C++ 에서 한다(Python 본 읽기는 샘플링의 5배 — 감사 §5.1). 프레임마다 UAnimPoseExtensions::GetAnimPoseAtFrame
 * (루트 모션을 포즈에 포함 — 일괄 리타깃이 소스를 읽는 방식, IKRetargetBatchOperation.cpp:415-435)으로 컴포넌트 공간 포즈를 얻는다.
 *
 *   구조   — 스켈레톤 있음 · 기대 스켈레톤 일치 · 프레임 ≥ 1 · 모든 본 트랙이 스켈레톤에 있음 · NaN · 비정상 스케일 → 오류면 FAILED
 *   절대   — 명백한 깨짐만: 한 프레임 회전 > max_deg_per_frame(기본 90°, 히어로 애니 관측 최대 약 70°) → FAILED.
 *            단 소스가 있고 소스도 그만큼 튀면(소스 최대 + 10° 이내) 리타깃이 만든 깨짐이 아니므로 경고 ROTATION_JUMP_INHERITED
 *            (30fps 마켓 공격은 손가락이 프레임당 93~109° — Phase 1 실측)
 *            각속도·발 미끄러짐의 절대 임계값은 쓰지 않는다(정상 공격 p99 ≈ 2,000°/s, 정상 Walk 도 발 속도가 튄다 — 감사 §5.2)
 *   상대   — sources 와 같은 순서로:
 *            · 다른 스켈레톤(리타깃 결과 vs 소스): 각속도 p99 비 · 착지 발 수평 속도 p50 비(펠비스 높이 비로 보정) · 루트 이동 거리 비(같은 보정) ·
 *              길이 차 · 루프 경계 비 — 허용 범위 밖이면 PASSED_WITH_WARNINGS
 *            · 같은 스켈레톤(회귀 비교 — 같은 소스를 다른 RTG 로 리타깃한 두 결과): 본별 컴포넌트 공간 회전 차 {p50, p99, max, worst[]}
 *   요청 충족 (Phase 2 — 지침서 §13) — expect{length, loop, root_yaw_delta} 불일치 → EXPECT_* 오류(FAILED).
 *            seams(이음매 시각)의 프레임 간 회전 변화가 주변 창 중앙값의 seam_ratio_max 배를 넘으면 경고 SEAM_JUMP
 *   측정   — profile_bones: 프레임별 컴포넌트 공간 선속도(cm/s) — 타격 구간 같은 시간 범위를 고르는 데 쓴다.
 *            profile_positions 면 같은 시각의 위치(cm)도 — 리타깃 정면 맞춤 전후의 동작 평면 비교
 *   제약   — body_clearance: 손 · 아래팔이 대상 메시의 몸(허리 · 골반 · 넓적다리)을 뚫는 깊이 · 프레임 비율(AnimMcpBodyClearance) → 경고 BODY_PENETRATION
 *   손가락 — fingers: 매핑 안 된 손가락은 기준 포즈 유지 · 매핑된 손가락은 손바닥 쪽 굽힘 · 끝 순서(AnimMcpFingerChains::Check) → 경고 FINGER_*
 *   시각   — 항상 needs_review[] 에 남긴다. 상태는 자동 검사 결과다(PASSED · PASSED_WITH_WARNINGS · NEEDS_REVIEW · FAILED).
 */
namespace AnimMcpAnimValidator
{
	struct FThresholds
	{
		double MaxDegPerFrame = 90.0;
		double AngSpeedP99RatioMin = 0.5;
		double AngSpeedP99RatioMax = 2.0;
		double FootPlantedRatioMax = 3.0;
		double RootTravelRatioMin = 0.67;
		double RootTravelRatioMax = 1.5;
		double LoopBoundaryRatioMax = 3.0;
		/** 착지 판정: 클립 최저 높이 + 이 값 (cm, 감사 §5.2 측정과 같은 규칙) */
		double FootPlantedHeight = 3.0;
		/** 이음매 프레임의 평균 회전 변화 / 주변 창 중앙값 — 이보다 크면 SEAM_JUMP (루프 경계 비와 같은 초기값) */
		double SeamRatioMax = 3.0;
	};

	/** 요청 충족 기대값 (Phase 2). 설정된 것만 검사한다 */
	struct FExpect
	{
		TOptional<double> Length;
		/** 길이 허용 오차 (초). 없으면 한 프레임 */
		TOptional<double> LengthTolerance;
		TOptional<bool> bLoop;
		/** 루트 본의 첫 → 끝 Yaw 변화 (°, 프레임마다 펼쳐 누적 — 방향 포함) */
		TOptional<double> RootYawDelta;
		double RootYawTolerance = 5.0;

		bool IsSet() const { return Length.IsSet() || bLoop.IsSet() || RootYawDelta.IsSet(); }
	};

	/** expect{} — 모르는 키·타입 오류는 BAD_REQUEST */
	bool ParseExpect(const TSharedPtr<FJsonObject>& Object, FExpect& Out, FAnimMcpError& OutError);

	/** thresholds{} — 위 필드의 snake_case 이름. 모르는 키·숫자 아님은 BAD_REQUEST */
	bool ParseThresholds(const TSharedPtr<FJsonObject>& Object, FThresholds& Out, FAnimMcpError& OutError);
	TSharedRef<FJsonObject> ThresholdsToJson(const FThresholds& Thresholds);

	struct FOptions
	{
		bool bStructural = true;
		bool bNumeric = true;
		bool bRelative = true;
		/** 기대 스켈레톤 (없으면 검사 안 함) */
		const USkeleton* ExpectedSkeleton = nullptr;
		/** 발·펠비스 본 — 비우면 이름 foot_l/foot_r · pelvis 를 찾는다(엔진 마네킹 규약). 소스용은 따로 */
		TArray<FName> Feet;
		FName Pelvis;
		TArray<FName> SourceFeet;
		FName SourcePelvis;
		FThresholds Thresholds;
		FExpect Expect;
		/** 이음매 시각 (초) — SEAM_JUMP 검사 */
		TArray<double> Seams;
		/** 프레임별 선속도를 낼 본 */
		TArray<FName> ProfileBones;
		/** profile 에 같은 시각의 컴포넌트 공간 위치(cm)도 낸다 — 손 궤적 같은 동작 평면 비교용 */
		bool bProfilePositions = false;
		/**
		 * 한 프레임 회전 튐의 "물려받은" 기준값(°). 설정되면 소스 샘플 대신 이 값으로 ROTATION_JUMP_INHERITED 를 판정한다 —
		 * apply_animation_edits 가 소스 최대 × 최대 재생 속도를 넘긴다(빠르게 만든 정상 동작이 절대 규칙에 걸리지 않게)
		 */
		TOptional<double> InheritedMaxDegPerFrame;
		/** 설정되면 팔-몸통 관통을 잰다 — 결과 body_clearance{}, 경고는 상태에 반영 */
		TOptional<AnimMcpBodyClearance::FSpec> BodyClearance;
		/** 설정되면 손가락을 검사한다 — 결과 fingers{}, 경고는 상태에 반영 */
		TOptional<AnimMcpFingerChains::FCheckSpec> Fingers;
	};

	/** 애셋 하나 — {asset, source, status, structural[], numeric{}, relative{}, needs_review[], seconds} */
	TSharedRef<FJsonObject> Validate(const UAnimSequence* Asset, const UAnimSequence* Source, const FOptions& Options);

	/** 상태 순위 — 여러 애셋의 종합 상태 (FAILED > NEEDS_REVIEW > PASSED_WITH_WARNINGS > PASSED) */
	FString WorstStatus(const FString& A, const FString& B);

	/**
	 * 이음매 비 — StepMeans[i] = 프레임 i → i+1 의 본 평균 회전(°). 이음매 프레임을 낀 두 변화의 최대 / 앞 4 · 뒤 4 변화 중앙값 중 큰 쪽
	 * (둘 다 거의 정지면 전체 중앙값의 1/4 이 바닥 — 포즈 유지 경계의 "멈춤"은 튐이 아니다). preview_animation_edits 도 같은 정의를 쓴다
	 */
	double SeamStepRatio(const TArray<double>& StepMeans, int32 SeamFrame);

	/** 한 프레임 최대 회전(°, 컴포넌트 공간) — 편집 결과 검증의 "물려받은 튐" 기준 계산용. 샘플 실패면 0 */
	double MaxDegPerFrame(const UAnimSequence* Sequence);
}
