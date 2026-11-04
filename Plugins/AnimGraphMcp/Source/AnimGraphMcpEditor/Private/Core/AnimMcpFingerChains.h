#pragma once

#include "AnimMcpSkeletonGeometry.h"
#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"

class UIKRetargeter;
class UIKRigDefinition;
class USkeletalMesh;
class USkeleton;
struct FAnimMcpError;
struct FReferenceSkeleton;

/**
 * 손가락 체인 — 이름 없이 위상 · 기준 포즈 좌표로 손가락을 찾아 표준 체인(FCharacterizationStandard — 엔진 템플릿 20종 공통)으로 제안하고
 * (create_ik_rig · inspect_skeleton), 리타깃 결과의 손가락이 정상인지 검사한다(validate_animation fingers · retarget_animations 검증).
 *
 * 실측 근거 (2026-10-25):
 *   - 손가락 체인이 없는 소스(SOMA 수동 9체인 · CMU)는 대상 손가락이 꺼진 Run IK Rig op 의 퍼지 매핑을 자동 정렬이 따라 꺾였다(검지 MCP 120°,
 *     가운데만 기준 22.3°/31.2°). 자동 캐릭터라이즈는 SOMA77 을 Mixamo 로 잡아 LeftIndex = Index1~3(메타카팔부터 한 마디 밀림)을 맞춘다.
 *   - 손 아래 구조: SOMA77 Hand{F}1(손목에서 2.9~4.0 cm, 메타카팔) → 2~4 → End · 엄지 Thumb1~3 → End, Vesper(UE5) 메타카팔 + 3마디,
 *     UE4 3마디, Narmaya 약지 · 새끼만 메타카팔(0.6 · 0.9 cm), SB(Biped) Finger0~4 3마디 + 무기 · FX 잎 본 · 길이 0 사슬, CMU 손가락 사슬 1개.
 *
 * 제안 — 손: 체인 원천의 팔 짝(AnimMcpSkeletonGeometry::PickLimbs) 끝 본(또는 그 자손 중 손가락 사슬이 가장 많은 본). 팔 체인이 없으면
 *   손가락 사슬이 3개 이상인 본 중 서로 거울인 가장 먼 짝(SB 의 아래팔 · 위팔 후보는 덜 바깥이라 빠진다).
 *   손가락 사슬 = 손의 자식마다 가장 깊은 자식을 따라 잎까지 · 2관절 이상 · 모든 구간 ≥ 0.5 cm × 키/170.
 *   엄지 = 다른 사슬 평균 방향에서 가장 벗어난 사슬(SOMA 15.4° 대 9.1°, Vesper 34.6 대 15.9, Narmaya 51.3 대 29.2) — 차이 < 3° 면 THUMB_AMBIGUOUS.
 *   나머지 = 손 기준틀(손목 → 너클 평균, 너클의 측면 주축을 엄지 쪽으로)에서 엄지 쪽부터 검지 · 가운데 · 약지 · 새끼.
 *   메타카팔 = 첫 관절이 자기 구간 길이보다 손목에 가까움(Vesper 2.3~3.2 대 4.3~4.8 cm, UE4 첫 마디 11~12 대 3.6~4.6).
 *   끝점 = 메타카팔 뒤 3마디 · 엄지 3마디를 넘는 잎 쪽 관절은 체인 밖(SOMA End, Mixamo Index4 — 엔진 템플릿과 같다).
 *   좌우 = 팔 체인 이름(Left* · Right*), 없으면 발 영역 정면의 −90° 쪽이 왼쪽. 좌우 같은 손가락끼리 거울인지도 본다.
 *
 * 검사 (리타깃 결과, 프레임마다 컴포넌트 공간):
 *   - 매핑 안 된 손가락 본(리타기터 FK op 에 소스 체인이 없는 체인 · 체인 밖 본)의 로컬 회전이 대상 메시 기준에서 UnmappedMaxDeg 넘게 벗어나면
 *     FINGER_UNMAPPED_NOT_REFERENCE — 고친 결과 0°, CMU 버그(P4) 최대 52°, SOMA 버그 최대 147°.
 *   - 엄지 아닌 손가락 MCP(메타카팔 또는 손목 → 첫 마디 → 둘째) · PIP(첫 → 둘째 → 셋째) 굽힘을 손바닥 쪽 + 로 — 손바닥은 손 키랄리티(왼손 −(x × lat),
 *     오른손 +(x × lat), x = 손목 → 너클, lat = 검지 너클 − 새끼 너클). Vesper 원본 57개 MCP −37.0~102.0 · PIP 1.5~112.6, HK → Vesper MCP ≥ −19.9,
 *     버그 MCP 120~124 · −109 · PIP −126 · 130.5 → FINGER_BEND_REVERSED(MCP < −60 · PIP < −25) · FINGER_OVERBENT(MCP > 110 · PIP > 130).
 *   - 끝 마디 측면 순서(검지 > 가운데 > 약지 > 새끼)가 깨진 프레임 > 5% 면 FINGER_ORDER_BROKEN — 정상 0%, SOMA 버그 100%.
 */
namespace AnimMcpFingerChains
{
	enum class EFinger : uint8
	{
		Thumb,
		Index,
		Middle,
		Ring,
		Pinky,
	};

	const TCHAR* FingerName(EFinger Finger);

	struct FFinger
	{
		EFinger Finger = EFinger::Thumb;
		/** 메타카팔 본 (엄지 · 메타카팔 없는 손가락은 INDEX_NONE) */
		int32 Metacarpal = INDEX_NONE;
		/** 손가락 마디 — 3마디까지(넘는 잎 쪽 관절은 Tips) */
		TArray<int32> Bones;
		TArray<int32> Tips;
	};

	struct FHand
	{
		int32 Bone = INDEX_NONE;
		/** Left | Right | 빈 문자열(모름) */
		FString Side;
		/** 엄지 → 새끼 순, 있는 것만 */
		TArray<FFinger> Fingers;
		/** 엄지 방향 이탈각 − 다음으로 큰 이탈각 (°) */
		double ThumbMarginDeg = 0.0;
		/** TOO_FEW_FINGER_CHAINS · THUMB_AMBIGUOUS · FINGER_COUNT_<n> */
		TArray<FString> Issues;

		const FFinger* Find(EFinger Finger) const { return Fingers.FindByPredicate([Finger](const FFinger& F) { return F.Finger == Finger; }); }
	};

	struct FHands
	{
		TArray<FHand> Hands;
		/** arm_chains | topology */
		FString HandsFrom;
		/** chain_names | facing | 빈 문자열 */
		FString SideFrom;
		/** NO_HANDS · SIDE_UNKNOWN (없으면 빈 문자열) */
		FString SkippedReason;
	};

	/** 손 · 손가락 위상. Chains = 체인 원천의 체인 — 팔 짝이 있으면 그 끝이 손, 없으면 위상으로 찾는다 */
	FHands FindHands(const AnimMcpSkeletonGeometry::FTree& Tree, const TArray<AnimMcpSkeletonGeometry::FNamedChain>& Chains);

	/** 표준 체인 이름 — {Side}{Finger} · {Side}{Finger}Metacarpal */
	FName StandardChainName(const FString& Side, EFinger Finger, bool bMetacarpal);

	/** 이미 정한 체인(수동 인자 · 템플릿) — 제안과 이름으로 맞대 본다 */
	struct FGivenChain
	{
		FName Name;
		FName Start;
		FName End;
	};

	struct FSuggestion
	{
		/** {hands_from, side_from, chains_from, hands[{side, hand, fingers, thumb_margin_deg, tips_excluded[], issues[]}], chains[{name, start, end}],
		 *   missing[{name, start, end}] (Given 에 그 이름이 없는 제안), differs[{name, given{start, end}, suggested{start, end}}], mirrored[[a, b]], not_mirrored[],
		 *   skipped_reason?} */
		TSharedRef<FJsonObject> Json = MakeShared<FJsonObject>();
		TArray<TSharedPtr<FJsonValue>> Missing;
		TArray<TSharedPtr<FJsonValue>> Differs;
		int32 NumChains = 0;
	};

	/** 체인 원천의 체인 → 맞대 볼 체인(시작 · 끝 본 이름) */
	TArray<FGivenChain> GivenChains(const FReferenceSkeleton& Ref, const AnimMcpSkeletonGeometry::FChainSource& Source);

	/** Source = 손을 찾을 체인 원천(인자 · IK Rig · 캐릭터라이즈), Given = 맞대 볼 체인 */
	FSuggestion Suggest(const FReferenceSkeleton& Ref, const AnimMcpSkeletonGeometry::FTree& Tree, const AnimMcpSkeletonGeometry::FChainSource& Source, const TArray<FGivenChain>& Given);

	// ---- 검사 ----

	constexpr double UnmappedMaxDeg = 2.0;
	constexpr double McpReversedDeg = -60.0;
	constexpr double PipReversedDeg = -25.0;
	constexpr double McpOverbentDeg = 110.0;
	constexpr double PipOverbentDeg = 130.0;
	constexpr double OrderBrokenMaxPct = 5.0;

	struct FCheckSpec
	{
		/** 손 · 체인 원천 — 없으면 리타기터의 대상 IK Rig, 그것도 없으면 스켈레톤 프리뷰 메시 자동 캐릭터라이즈 · 위상 */
		const UIKRigDefinition* Rig = nullptr;
		/** 매핑(FK op) — 없으면 '매핑 안 된 손가락 = 기준 포즈' 검사를 하지 않는다 */
		const UIKRetargeter* Retargeter = nullptr;
		/**
		 * 기준 포즈 · 위상을 읽을 대상 메시 — 없으면 리타기터의 대상 프리뷰 메시, 그것도 없으면 스켈레톤 기준 포즈. 리타깃은 매핑 안 된 본에 대상 메시의
		 * 리타깃 포즈(= 메시 기준)를 쓴다 — 메시 46개가 쓰는 Vesper 스켈레톤의 기준 포즈는 F_01 과 손가락 로컬 회전이 최대 14° 다르다(2026-10-25 실측)
		 */
		const USkeletalMesh* Mesh = nullptr;
	};

	/** fingers 인자 — true 또는 {ik_rig?, retargeter?, mesh?}. 형식 오류 · 못 읽는 애셋은 BAD_REQUEST / ASSET_NOT_FOUND */
	bool ParseSpec(const TSharedPtr<FJsonValue>& Value, const TCHAR* Field, FCheckSpec& Out, bool& bOutEnabled, FAnimMcpError& OutError);

	/**
	 * Bones = 포즈 본 이름(Component 의 열 순서), Component[frame][bone] = 컴포넌트 공간. {topology_from, chains_from, mapping_from, hands[{side, hand,
	 * order_broken_pct, fingers[{finger, chain, metacarpal_chain?, mapped (true | false | null), mcp{min, p50, max}?, pip{…}?}]}], unmapped[{bone, chain, max_deg,
	 * frame}], thresholds{}, issues[]} | {skipped_reason, issues[]}. bOutWarning = 경고 있음
	 */
	TSharedRef<FJsonObject> Check(const USkeleton* Skeleton, const TArray<FName>& Bones, const TArray<TArray<FTransform>>& Component, const FCheckSpec& Spec, bool& bOutWarning);

	/** 손가락 마디 굽힘(°, 손바닥 쪽 +) — Prev → Joint → Next. BendAxis = x × 손바닥 (단위) */
	double SignedBendDeg(const FVector& Prev, const FVector& Joint, const FVector& Next, const FVector& BendAxis);
}
