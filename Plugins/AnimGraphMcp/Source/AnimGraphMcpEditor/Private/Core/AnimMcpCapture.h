#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * 대상 메시 캡처 (capture_animation — AI 애니 생성 Phase 8-2, Docs/AIAnimation/DevelopmentGuide.md §14 Phase 8 '8-2').
 *
 * 리타깃 결과를 Persona 를 열지 않고 판정하도록 **대상 메시 모습**으로 찍는다 — 같은 저장소의 Blender 소스 골격 렌더
 * (Tools/mcp/anim_gen/blender/review_render.py)와 같은 카메라 · 시트 규칙이라 나란히 비교할 수 있다:
 *   정사영 · 정면 = 몸 앞에서(몸의 왼쪽이 화면 오른쪽) · 측면 = 몸 오른쪽에서(정면이 화면 오른쪽),
 *   전 프레임 포즈 범위(최대 bounds_max_samples 프레임 + 렌더 프레임)에 한 번 맞춰 고정 — 이동 · 높이 변화가 그대로 보인다,
 *   셀 높이 고정 · 폭 = 범위 비율(1/max_aspect ~ max_aspect) · 바닥(z = 0) 항상 보임, 시트 = 행(시각) × 열(뷰), 긴 변 sheet_max_px 안.
 *   범위는 본 점만 쓰는 Blender 와 달리 메시 LOD0 정점을 가장 큰 가중치 본의 로컬 상자로 묶어 프레임마다 옮긴다(머리카락 · 신발이 본 밖).
 *
 * 장면 = 임시 FPreviewScene(트랜지언트 월드) + 스켈레탈 메시(단일 노드 · SetPosition → RefreshBoneTransforms — 엔진 썸네일과 같은 포즈 경로)
 *   + 무광 배경판 · 바닥 판(엔진 LevelColorationUnlitMaterial 의 동적 인스턴스) + 카메라 기준 주광(그림자) · 보조광 · 썸네일 환경 큐브맵.
 *   USceneCaptureComponent2D(정사영, FinalColorLDR, ShowOnly) → 트랜지언트 렌더 타깃 → 픽셀 → PNG. Lumen · 반사 · TAA · 모션 블러 · 블룸 ·
 *   자동 노출을 끄고 노출을 고정해 같은 입력이면 같은 픽셀을 노린다(supersample 배로 그린 뒤 줄여 계단 완화).
 *   애셋을 만들지 않는다 — 호출 전후 전역 더티 집합이 같아야 한다(새 더티가 있으면 UNEXPECTED_DIRTY). 파일은 CaptureOutputRoots 아래 새 폴더에만.
 *
 * 부착물 (attachments — Phase 8-4a): 무기 같은 메시(스켈레탈 = 기준 포즈 · 스태틱)를 소켓 또는 본에 붙여 함께 찍는다 —
 *   AttachToComponent(KeepRelative) + 상대 변환 = offset. 소켓 자식 변환은 포즈 평가가 갱신하고(USkeletalMeshComponent::FinalizeAnimationUpdate —
 *   PhysAnim.cpp:468-485) 포즈마다 UpdateComponentToWorld 로 한 번 더 맞춘 뒤 렌더 상태를 다시 만든다. 범위(카메라)에 부착물 정점 상자도 넣는다.
 *   게임 무기 배치(소켓 × 계열 AttachTransform × 변형 AttachOffset)는 호출자가 offset 하나로 합성해 준다 — 플러그인은 장비 데이터를 모른다.
 *
 * 초점 (focus — Phase 9-5c): 손 · 손가락 · 머리처럼 전신 시트에서 몇 픽셀뿐인 부위를 판정할 때. 전 프레임 고정 대신 지정 본을 따라간다 —
 *   범위 = 지정 본의 정점 상자 꼭짓점(정점이 없는 본은 본 위치), 배율 = 전 프레임 범위의 최대 폭 · 높이 + 여백으로 한 번(FitView 재사용 — 행끼리 cm/px 가 같다),
 *   중심 = 셀마다 그 포즈의 범위 가운데, 시선 방향은 views 그대로. near_cut 이면 카메라를 초점 상자 앞면 바로 앞에 둔다 — 정사영 캡처의 근평면은 카메라 위치라
 *   (SceneCaptureRendering.cpp BuildOrthoMatrix NearPlane 0) 그 앞의 몸은 잘린다(S1 측면 왼손이 가슴 뒤인 프레임 64/120). 잘린 몸도 그림자는 드리우므로 주광 그림자를 끈다.
 *   칸 가장자리에 몸이 닿는 것이 정상이므로 touches_edge 를 재지 않고, 피사체 판정 배경색은 피사체 없는 곳에서 따로 잰다. focus 가 없으면 이 경로는 전혀 지나지 않는다.
 */
namespace AnimMcpCapture
{
	/** 한 뷰의 화면 축 범위 — u = 점 · 화면 오른쪽, v = 점 · 위(Z), d = 점 · 시선 */
	struct FRange
	{
		double UMin = TNumericLimits<double>::Max();
		double UMax = TNumericLimits<double>::Lowest();
		double VMin = TNumericLimits<double>::Max();
		double VMax = TNumericLimits<double>::Lowest();
		double DMin = TNumericLimits<double>::Max();
		double DMax = TNumericLimits<double>::Lowest();

		void Add(double U, double V, double D)
		{
			UMin = FMath::Min(UMin, U); UMax = FMath::Max(UMax, U);
			VMin = FMath::Min(VMin, V); VMax = FMath::Max(VMax, V);
			DMin = FMath::Min(DMin, D); DMax = FMath::Max(DMax, D);
		}
		bool IsValid() const { return UMin <= UMax; }
	};

	/** 정사영 맞춤 — review_render.py frame_view 와 같은 수식(셀 높이 고정 · 폭 = 범위 비율 · 바닥 z = 0 포함) */
	struct FViewFit
	{
		/** 화면 축 중심 (u, v) */
		double CenterU = 0.0;
		double CenterV = 0.0;
		/** 긴 쪽 보이는 크기(Blender ortho_scale) · 보이는 폭 · 높이 (cm) */
		double Scale = 0.0;
		double ExtentW = 0.0;
		double ExtentH = 0.0;
		/** 셀 픽셀 */
		int32 Width = 0;
		int32 Height = 0;
		/** 시선 축 범위 (카메라 · 배경판 자리) */
		double DMin = 0.0;
		double DMax = 0.0;
		/** 있으면 카메라를 이 시선 축 깊이에 둔다 — 그 앞은 잘린다 (focus near_cut). 없으면 DMin 앞으로 충분히 물러난다 */
		TOptional<double> NearCutD;
	};

	FViewFit FitView(const FRange& Range, double Margin, int32 CellHeight, double MaxAspect);

	/** capture_animation focus 인자 — 본 이름 · 여백(cm) · 앞 자르기 */
	struct FFocus
	{
		TArray<FName> Bones;
		double MarginCm = 4.0;
		bool bNearCut = true;
	};

	/** focus {bones[1..MaxBones], margin_cm?, near_cut?} → FFocus. 본 존재는 메시를 읽은 뒤에. 형식 오류면 false + 이유 */
	bool ParseFocus(const TSharedPtr<FJsonObject>& Object, FFocus& Out, FString& OutWhy);

	/** 초점 배율 — 전 프레임 초점 범위의 최대 폭 · 높이 + 양쪽 여백을 FitView 로 (v 를 0 부터 주어 바닥 포함 규칙이 걸리지 않는다). 중심은 FollowFocus 가 셀마다 */
	FViewFit FitFocus(double MaxW, double MaxH, double MarginCm, int32 CellHeight, double MaxAspect);

	/** 한 포즈의 초점 범위(Now)로 따라가기 — 배율 · 셀 크기는 Fit 그대로, 중심 · 앞 자름 깊이만 바꾼다 */
	FViewFit FollowFocus(const FViewFit& Fit, const FRange& Now, const FFocus& Focus);

	/** 시트 축소 비율 — 긴 변이 SheetMaxPx 안 (review_render.py 와 같은 규칙: 간격 포함, 1 이하) */
	double SheetScale(const TArray<int32>& ColumnWidths, int32 CellHeight, int32 Rows, int32 Gap, double SheetMaxPx);

	/** Count 개 시각을 클립에 고르게 — 첫 · 끝 포함, 소수 넷째 자리 (anim_gen blender.spread 와 같다) */
	TArray<double> Spread(int32 Count, double Duration);

	/** 범위 샘플 프레임 — 상한 Cap 개를 고르게 + 끝 + Extra, 정렬 · 중복 없음 (review_render.py sample_frames) */
	TArray<int32> SampleFrames(int32 First, int32 Last, int32 Cap, const TArray<int32>& Extra);

	/** attachments[].offset {location?[x,y,z], rotation?[pitch, yaw, roll], scale?[x,y,z]} → 상대 변환. 형식 오류면 false + 이유 */
	bool ParseOffset(const TSharedPtr<FJsonObject>& Object, FTransform& Out, FString& OutWhy);

	/** capture_animation 본체 — 인자 해석 · 장면 · 범위 · 행 캡처 · 시트 · 비교 시트 · 연속 프레임 · 가드 */
	TSharedPtr<FJsonObject> Capture(FAnimMcpContext& Context, FAnimMcpError& OutError);
}
