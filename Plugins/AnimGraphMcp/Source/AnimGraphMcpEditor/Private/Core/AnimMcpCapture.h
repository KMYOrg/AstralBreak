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
	};

	FViewFit FitView(const FRange& Range, double Margin, int32 CellHeight, double MaxAspect);

	/** 시트 축소 비율 — 긴 변이 SheetMaxPx 안 (review_render.py 와 같은 규칙: 간격 포함, 1 이하) */
	double SheetScale(const TArray<int32>& ColumnWidths, int32 CellHeight, int32 Rows, int32 Gap, double SheetMaxPx);

	/** Count 개 시각을 클립에 고르게 — 첫 · 끝 포함, 소수 넷째 자리 (anim_gen blender.spread 와 같다) */
	TArray<double> Spread(int32 Count, double Duration);

	/** 범위 샘플 프레임 — 상한 Cap 개를 고르게 + 끝 + Extra, 정렬 · 중복 없음 (review_render.py sample_frames) */
	TArray<int32> SampleFrames(int32 First, int32 Last, int32 Cap, const TArray<int32>& Extra);

	/** capture_animation 본체 — 인자 해석 · 장면 · 범위 · 행 캡처 · 시트 · 비교 시트 · 연속 프레임 · 가드 */
	TSharedPtr<FJsonObject> Capture(FAnimMcpContext& Context, FAnimMcpError& OutError);
}
