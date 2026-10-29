#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"

class UAnimSequence;
class UIKRigDefinition;
class USkeletalMesh;
struct FAnimMcpError;

/**
 * 팔-몸통 관통 측정 (validate_animation body_clearance) — 리타깃 결과에서 손 · 아래팔이 허리 · 골반 · 넓적다리를 뚫는지 대상 메시로 잰다.
 *
 * 실측 근거 (2026-10-25, CMU 01_01 · Kimodo SOMA · UE4 HK → Vesper, per_bone · 축 중립): 위팔 방향은 소스와 같고(매핑 정확) 차이는 체형이다 —
 * 어깨 관절 반폭 CMU 21.5 · Vesper 12.0 cm, 엉덩 관절 반폭 8.8 · 9.1 cm. 같은 팔 각도면 손목이 엉덩 관절 바깥으로 지나는 거리가 p50 20.8 → 8.3 cm,
 * 아래팔 · 손과 넓적다리 · 엉덩 축 사이 최소 거리가 14.4 → 7.1 cm(왼) · 11.0 → 4.8 cm(오른)로 준다. 관절만으로는 몸 부피(옷 · 벨트 · 파우치)를 모르니 메시로 잰다.
 *
 * 몸 근사 = 대상 메시 LOD0 의 스킨 정점(편집용 임포트 모델 — 위치 · 법선 · 영향 본 · 가중치)을 프레임마다 선형 블렌드 스키닝:
 *   팔(좌우) = 팔꿈치 본(아래팔)과 그 자손(트위스트 · 손 · 손가락)에 가장 크게 묶인 정점.
 *   몸 = 펠비스 · 척추(두 위팔의 공통 조상) · 넓적다리와 그 짧은 보조 본(트위스트 · 가슴 · 벨트 — 다른 체인이 시작하는 본에서 멈춘다)에 묶인 정점.
 *        3마디 이상 이어진 매달린 가지(코트 자락 · 머리카락 — 게임에서 물리로 흔들리는 경우가 많다)는 secondary 로 따로 세고 상태에 넣지 않는다.
 *   팔 · 다리 · 척추 판정은 이름 없이 체인과 기하로 — 체인 원천: 인자 직접 지정 > IK Rig(리타기터의 대상 리그 · ik_rig) > 메시 자동 캐릭터라이즈.
 *   뼈 2개 이상 · 같은 수인 체인 쌍이 두 시작 관절의 수직이등분면에 비춰 본마다 겹치면 거울 짝(좌우축이 수평), 펠비스보다 위에서 시작하는 가장 뿌리 쪽 짝 = 팔,
 *   아래 = 다리. 팔 체인 [0] = 위팔 · [1] = 팔꿈치 · [2] = 손목, 다리 체인 [0] = 넓적다리 · [1] = 무릎.
 * 판정 = 반경 지도: 프레임마다 몸통 축(두 엉덩 관절 중점 → 척추 끝) · 넓적다리 축(엉덩 → 무릎) 둘레를 (축 위치 t × 각도 10°) 칸으로 나눠 칸마다
 *   몸 정점의 최대 반경(넓적다리와 그 보조 본 정점은 넓적다리 축, 나머지는 몸통 축). 팔 정점 깊이 = 그 칸 반경 − 축까지 거리(+ 안쪽), 프레임 깊이 = 그 팔의 최대.
 *   축 둘레로 별 모양이라는 가정이다 — 옷 · 벨트 · 파우치의 바깥 면이 반경이 되고, 깊이 박힌 점도 깊이 · 바깥 방향이 정해진다. (처음 쓴 '가장 가까운
 *   몸 정점 법선' 판정은 깊이 박힌 점에서 법선이 사방으로 흩어져 보정 방향이 엉키고 탐색 반경보다 깊은 점을 놓쳤다 — 2026-10-25 CMU 보정 p50 20~30°.)
 *   접촉(contact_cm, 기본 1 cm)까지는 손이 몸에 닿는 정상 동작으로 보고, 관통(penetration_cm, 기본 2 cm)을 넘는 프레임이 있으면 경고 BODY_PENETRATION.
 *   기본 거리값은 대상 펠비스 기준 높이 / 100 cm 배(사람 크기가 아닌 캐릭터). 팔 정점은 팔 본 선분에서 7 cm 안만(손에 붙은 무기 본은 빠진다).
 * 한계: 두 팔 · 두 다리 인간형. 축 둘레 오목한 곳(같은 칸 안에서 안쪽으로 파인 면)은 바깥 면으로 메워 본다. 소스 메시는 쓰지 않는다.
 *
 * 보정 (retarget_animations body_clearance resolve) — 관통한 프레임에서만 필요한 만큼 위팔을 어깨 관절 둘레로 돌린다(팔꿈치 · 손목 · 손가락 로컬 회전은
 * 그대로라 팔 모양 유지). 대상 리타깃 포즈 고정 오프셋(모든 프레임 · 위로 든 팔과 앞 파지도 벌어짐)이나 IK + 소스 간격 유지(팔꿈치 각 최대 62° 변화 —
 * 소스 체형 복사)보다 변화가 작다(관절 시뮬 CMU: 고정 오프셋 8.6/11.2° 전 프레임 vs 최소 회전 p50 5.1/8.6°, HK 17.5% 프레임만).
 *   프레임마다: 팔 정점 중 반경 지도 깊이 + margin > 0 인 점의 목표 이동 (깊이 + margin) · (축에서 바깥 방향)을 어깨 회전 ω 로 최소제곱
 *   (Σ(|r|²I − rrᵀ) + λI) ω = Σ r × d, 한 걸음 ≤ 8°, 남은 깊이 ≤ 0.05 cm 까지 반복 → 부모(쇄골) 공간 회전 벡터로.
 *   시간: 크기 기준 팽창(±0.13초) → 가우시안(σ = 반경/2) — 팽창 반경 ≥ 블러 반경이라 같은 방향이면 보정량이 줄지 않는다. 다시 검사해 남은 관통은
 *   그 프레임 원래 값에 더하고 다시 부드럽게(최대 3회). 상한 max_deg 를 넘으면 자르고 경고 BODY_CLEARANCE_LIMIT. 위팔 트랙만 쓴다.
 *   두 손목이 20 cm × scale 안인데 보정이 둘의 상대 위치를 1 cm × scale 넘게 바꾸면 경고 CLEARANCE_GRIP_CHANGED(양손 파지를 풀지는 않는다 — v1).
 *
 * 부위 쌍 (Phase 8-4a — 옵트인, 주지 않으면 위 결과 그대로): 팔 부위(손 = 손목 본과 자손 · 아래팔 = 팔꿈치 본과 트위스트 · 위팔 = 위팔 본과 트위스트,
 *   어깨 관절에서 위팔 길이 × 0.4 안은 뺀다 — 몸통에 붙은 삼각근) × 몸 부위(몸통 칸 pelvis · belly · chest = 몸통 축 t 를 기준 포즈 척추 마디
 *   (펠비스 위 첫째 · 둘째)의 t 로 나눈 것 — 본 → 자식 구간의 스킨 가중치 영역과 같다 · 넓적다리 좌우 · head_neck = 새 축(중앙선 체인의 가장 낮은 본
 *   → 머리 꼭대기 — 기준 포즈에서 축선 5 cm × scale 안 머리 정점의 최대 투영(정수리 — 뿔 · 큰 머리카락 끝 제외, 축 근처 정점이 없으면 머리 정점
 *   전체의 최대 투영), 지도는 t −0.1 ~ 1.0(정수리 위 뿔 줄기는 밖), 3마디+ 가지(머리카락 본)는 뺀다)). 쌍마다 프레임 깊이 = 그 팔 부위 점이 그 몸 부위 지도에서 가장
 *   깊은 값(같은 반경 지도 · 이웃 규칙). legs = 넓적다리 · 종아리 점 ↔ 반대 다리 넓적다리(t ≥ 0.2 칸 — 사타구니 쪽은 서 있기만 해도 닿는다) · 종아리
 *   (무릎 → 발목, 새 축). per_frame = 쌍별 프레임 깊이(부호 있음 — 음수는 틈). model = Python 풀이(anim_gen/body_model.py)용 몸 모델 — 측정이 쓰는
 *   점 전부(기준 위치 · 영향 본 · 가중치) · 프레임별 포즈(측정과 같은 메시 기준 샘플) · 프레임별 반경 지도(int16 0.01 cm · float32 축, base64).
 *   좌우 이름(l · r)은 이름 없이 정면 기하(발 영역)로 정한다.
 *
 * 손끼리 (Phase 8-4b — 옵트인 hands): 팔마다 반경 지도 둘 — 손(손목 → 손 끝, 손 끝 = 기준 포즈 손 점의 무게중심 방향 최대 투영 · 손목 로컬로 따라간다) ·
 *   아래팔(팔꿈치 → 손목). 지도 점 = 그 팔의 손 · 아래팔 측정 점(몸 지도와 같은 FRadialAxis 규칙). 반대 팔의 손 · 아래팔 · 위팔 점이 묻는다 → 12 쌍
 *   (body_part hand_<반대> · forearm_<반대>). 두 손을 모아 쥐면 맞닿음(contact_cm)까지는 정상, 관통(penetration_cm) 넘으면 경고 HAND_PENETRATION.
 *   (Vesper 검 선택 f0 — 사용자 Persona 에서 손끼리 통과, 8-4a 측정에는 없던 자리.) 쥔 주먹은 축 둘레 별 모양에 가깝지만 오목한 손바닥 면은 바깥 면으로 메운다.
 */
namespace AnimMcpBodyClearance
{
	struct FSpec
	{
		/** 대상 메시 — 없으면 애니 스켈레톤의 프리뷰 메시 */
		USkeletalMesh* Mesh = nullptr;
		/** 체인 원천 — 없으면 메시 자동 캐릭터라이즈 */
		const UIKRigDefinition* Rig = nullptr;
		/** 직접 지정: 위팔 두 개(팔꿈치 = 자손이 가장 많은 자식). 몸 본은 주면 그 본들만(자손으로 넓히지 않는다) */
		TArray<FName> UpperArms;
		TArray<FName> BodyBones;
		bool bIncludeSecondary = false;
		TOptional<double> ContactCm;
		TOptional<double> PenetrationCm;
		/** Phase 8-4a 옵트인 — parts "all"(부위 쌍 · 경고 BODY_PENETRATION_PARTS) · legs(다리끼리 · LEG_PENETRATION) · per_frame · model{stride} */
		bool bAllParts = false;
		bool bLegs = false;
		bool bPerFrame = false;
		bool bModel = false;
		int32 ModelStride = 1;
		/** Phase 8-4b 옵트인 — 손끼리(parts.hands · 경고 HAND_PENETRATION · per_frame · model 지도 hand_l/r · forearm_l/r) */
		bool bHands = false;

		bool NeedsParts() const { return bAllParts || bLegs || bPerFrame || bModel || bHands; }
	};

	/**
	 * body_clearance 인자 — true 또는 {mesh?, ik_rig?, upper_arms?[], body_bones?[], include_secondary?, contact_cm?, penetration_cm?,
	 * parts? ("arms" | "all"), legs?, hands?, per_frame?, model? (true | {stride 1..10})}.
	 * ExtraKeys 는 호출자가 따로 읽는 키(오류로 보지 않는다). 형식 오류 · 못 읽는 애셋은 BAD_REQUEST / ASSET_NOT_FOUND
	 */
	bool ParseSpec(const TSharedPtr<FJsonValue>& Value, const TCHAR* Field, const TArray<FString>& ExtraKeys, FSpec& Out, bool& bOutEnabled, FAnimMcpError& OutError);

	/**
	 * 측정. {mesh, chains_from, scale, contact_cm, penetration_cm, arms[{upper_arm, elbow, points, frames_over_contact_pct, frames_over_penetration_pct,
	 * depth_p50, depth_p95, depth_max, worst{frame, time, arm_bone, body_bone}, body_bones_hit[{bone, frames}]}], body{core_roots[], core_points,
	 * secondary_branches[], secondary_points}, secondary_arms[]?(include_secondary), parts?{…, legs?{…}, hands?{hand_bins, forearm_bins, t_range{hand, forearm},
	 * tip_local_cm{l, r}, points{"l.hand" …}, pairs[]}}, per_frame?{…}, model?{…}, issues[], seconds}
	 * | {skipped_reason, issues[]}. parts · per_frame · model 은 Spec 이 요청할 때만(NeedsParts) — 그 밖의 필드 · 값은 요청과 무관하게 같다.
	 * bOutWarning = 경고(BODY_PENETRATION · parts all 이면 BODY_PENETRATION_PARTS · legs 면 LEG_PENETRATION · hands 면 HAND_PENETRATION) 있음
	 */
	TSharedRef<FJsonObject> Measure(const UAnimSequence* Sequence, const FSpec& Spec, bool& bOutWarning);

	enum class EMode : uint8
	{
		Off,
		Measure,
		Resolve,
	};

	struct FResolveOptions
	{
		/** 몸 표면에서 띄울 여유 (cm) — 미지정이면 0.5 × scale */
		TOptional<double> MarginCm;
		/** 프레임 보정 상한 (°) */
		double MaxDeg = 30.0;
	};

	/**
	 * retarget_animations body_clearance — "off" | "measure" | "resolve" | {mode? (기본 resolve), margin_cm?, max_deg?, + ParseSpec 키}.
	 * 없으면 Off. per_frame · model 은 validate_animation 전용(BAD_REQUEST)
	 */
	bool ParseMode(const TSharedPtr<FJsonValue>& Value, const TCHAR* Field, EMode& OutMode, FSpec& OutSpec, FResolveOptions& OutOptions, FAnimMcpError& OutError);

	/**
	 * 보정 — 시퀀스의 위팔 트랙을 고친다(호출자가 더티 · 저장을 맡는다). {mesh, margin_cm, max_deg, arms[{upper_arm, corrected_frames_pct, deg_p50 (보정 프레임),
	 * deg_p95, deg_max, deg_per_s_max, clamped_frames}], grip_changed_frames, before{} (Measure), after{} (Measure), issues[], seconds} | {skipped_reason, issues[]}.
	 * bOutWarning = 경고(BODY_CLEARANCE_LIMIT · CLEARANCE_GRIP_CHANGED · 보정 뒤에도 남은 BODY_PENETRATION) 있음
	 */
	TSharedRef<FJsonObject> Resolve(UAnimSequence* Sequence, const FSpec& Spec, const FResolveOptions& Options, bool& bOutWarning);

	// ---- 계산부 (단위 테스트 AnimGraphMcp.Generation.BodyClearance) ----

	/** 피벗 기준 점 Arms(r) 를 Targets(d) 만큼 옮기는 최소제곱 회전 벡터(라디안 · 축) — (Σ(|r|²I − rrᵀ) + λI) ω = Σ r × d, λ = Regularization × tr/3 */
	FVector SolveRotation(const TArray<FVector>& Offsets, const TArray<FVector>& Displacements, double Regularization);

	/** 회전 벡터 열 — 크기 기준 팽창(±Radius 키) → 성분별 가우시안(σ = Radius / 2, ±Radius 절단) */
	TArray<FVector> SmoothRotationVectors(const TArray<FVector>& Vectors, int32 Radius);

	/** 반경 지도 각도 칸 수(10°) */
	constexpr int32 AngleBins = 36;

	/**
	 * 축 하나의 반경 지도 — 축 A → A + Dir · Length 둘레를 (축 위치 t × 각도) 칸으로 나눠 칸마다 몸 정점의 최대 반경과 그 정점(Who).
	 * 각도 기준 = 축에 수직인 X(Lateral 을 축에 직교화) · Y = Dir × X. anim_gen/body_model.py 가 같은 규칙으로 읽는다(Locate · Radius)
	 */
	struct FRadialAxis
	{
		bool bValid = false;
		FVector A = FVector::ZeroVector;
		FVector Dir = FVector::ZeroVector;
		double Length = 0.0;
		FVector X = FVector::ZeroVector;
		FVector Y = FVector::ZeroVector;
		double TMin = 0.0, TMax = 1.0;
		int32 TBins = 1;
		TArray<double> MaxRadius;
		TArray<int32> Who;

		void Init(const FVector& InA, const FVector& InB, const FVector& Lateral, double InTMin, double InTMax, int32 InTBins);
		/** 점의 (t 칸, 각도 칸, 축 위 가장 가까운 점에서의 반경 벡터) — 축이 없거나 t 가 범위 밖이면 false */
		bool Locate(const FVector& P, int32& OutT, int32& OutAngle, FVector& OutRadial) const;
		void Add(const FVector& P, int32 Index);
		/** 칸 반경 — 빈 칸이면 이웃 3x3 의 최대(각도는 감아 돈다, t 는 자른다). 없으면 −1 */
		double Radius(int32 T, int32 Angle, int32& OutWho) const;
		/** t 칸 가운데의 t */
		double BinCenter(int32 T) const { return TMin + (T + 0.5) / TBins * (TMax - TMin); }
	};

	/**
	 * 손끼리(8-4b) — 한 팔의 반경 지도 둘: 손(손목 → 손 끝, t −0.15 ~ 1.05 · 12 칸) · 아래팔(팔꿈치 → 손목, t −0.1 ~ 1.05 · 14 칸).
	 * Init 뒤 그 팔의 손 점은 Hand, 아래팔 점은 Forearm 에 Add — 반대 팔의 점이 Locate · Radius 로 묻는다(몸 지도와 같은 규칙)
	 */
	struct FArmAxes
	{
		FRadialAxis Hand;
		FRadialAxis Forearm;

		void Init(const FVector& Elbow, const FVector& Wrist, const FVector& HandTip, const FVector& Lateral);
	};

	/**
	 * 손 끝(컴포넌트 공간) — 손목에서 손 점 무게중심 방향으로 가장 멀리 나간 투영(손가락 끝). 무게중심이 손목과 거의 겹치면 아래팔 방향(팔꿈치 → 손목).
	 * 손 점이 없으면 손목 그대로(축 없음)
	 */
	FVector HandTip(const TArray<FVector>& HandPoints, const FVector& Elbow, const FVector& Wrist);

	/** 몸통 축 위치 t → 칸 이름 — pelvis(t < BellyT) · belly(t < ChestT) · chest */
	const TCHAR* TorsoPart(double T, double BellyT, double ChestT);

	/** 모델 내보내기 — int16 LE(값 / Unit 반올림 · ±32767 로 자름, 값 < 0 = 빈 칸 −32768) · float32 LE 를 base64 로 */
	constexpr int16 EmptyRadiusI16 = -32768;
	FString EncodeI16(const TArray<double>& Values, double Unit);
	FString EncodeF32(const TArray<double>& Values);
}
