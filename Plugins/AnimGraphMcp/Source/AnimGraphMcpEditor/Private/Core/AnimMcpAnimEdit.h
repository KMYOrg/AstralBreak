#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UAnimSequence;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * preview_animation_edits / apply_animation_edits (AI 애니 생성 Phase 2 — Docs/AIAnimation/DevelopmentGuide.md §14 Phase 2).
 * 주 소스와 concat 소스의 원시 키를 리그 순서로 읽어(AnimMcpAnimEditOps::FSource) 주 소스 전체를 버퍼로 만들고 op 를 차례로 적용한다.
 * 원자성: 모든 op 를 메모리 버퍼에서 끝까지 계산한 뒤에만 애셋을 만든다 — 하나라도 실패하면 BAD_REQUEST(details.planned), 애셋 0개.
 * (항상 새 애셋이라 apply_graph_operations 같은 보상 롤백은 없다)
 *
 * apply: 주 소스 복제(AnimMcpGeneration::DuplicateAssetObject — 루트 모션·압축·additive 설정, 커브 메타를 물려받는다)
 *   → 노티파이·싱크 마커를 먼저 비운다(SetNumberOfFrames 의 길이 변경 알림이 옮기지 않게 — AnimSequenceBase.cpp:1275)
 *   → 컨트롤러 한 브래킷에서 본 트랙·float 커브를 다시 쓴다(엔진 일괄 리타깃과 같은 순서, bShouldTransact=false)
 *   → 노티파이·싱크 마커를 키의 출처로 새 시각에 옮겨 넣는다(잘린·역재생 구간은 뺀다)
 *   → 검증(validate_animation: expect 길이·루프·루트 Yaw + seams + 물려받은 튐 기준 = 소스 최대 °/프레임 × 최대 재생 속도) — FAILED 면 저장 안 함
 *   → 전역 더티 검사(FinishWrite) → (save) 저장.
 * 원시 키를 읽으므로 소스의 트랜스폼 커브(additive 레이어)·본 속성은 결과에 없다 — 경고 TRANSFORM_CURVES_DROPPED · ATTRIBUTES_DROPPED.
 * 출력 fps = 주 소스(데이터가 있는 모델의 SetFrameRate 는 배수·약수만 받는다 — AnimSequencerController.cpp:287). concat 소스는 그 fps 로 다시 고른다.
 */
namespace AnimMcpAnimEdit
{
	struct FRequest
	{
		UAnimSequence* Source = nullptr;
		/** apply 필수 · preview 선택(would_create 검사) */
		FString AssetPath;
		TArray<TSharedPtr<FJsonValue>> Operations;
		TOptional<bool> bLoop;
		TOptional<bool> bRootMotion;
		bool bValidate = true;
		TSharedPtr<FJsonObject> Thresholds;
		bool bSave = false;
	};

	/** 애셋을 만들지 않는다. result: valid, planned[], result{}, seams[], notifies{}, would_create? */
	TSharedPtr<FJsonObject> Preview(const FRequest& Request, FAnimMcpContext& Context, FAnimMcpError& OutError);

	/** 계산 → 복제 → 재작성 → 검증 → 더티 검사 → 저장. result: asset_path, planned[], validation{}, saved … */
	TSharedPtr<FJsonObject> Apply(const FRequest& Request, FAnimMcpContext& Context, FAnimMcpError& OutError);

	/** Tool 설명에 붙이는 op 사전 */
	extern const TCHAR* const OperationsDoc;
}
