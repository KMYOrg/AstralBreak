#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * promote_animation (AI 애니 생성 Phase 7) — 후보 경로([AnimGraphMcp] GenerationOutputPaths)의 애니 애셋을 정식 경로(PromotionPaths)로 옮긴다.
 *
 * 엔진 IAssetTools::RenameAssets(대화상자 없는 경로, AssetRenameManager.cpp:138-152) 한 번으로 옮긴다. 엔진은 참조자를 고치고
 * 새 패키지 · 참조 패키지를 **자동 저장**한다(PerformAssetRename :1978-1995 — PromptForCheckoutAndSave 프롬프트 없음) — 그래서 사후 더티
 * 비교만으로는 막을 수 없다 → 사전 검사(참조자 · 맵 · 이미 더티 · 보호) + confirm, 후보 경로 밖 참조자는 allow_referencers 로 명시해야 한다.
 * 리디렉터는 참조자가 맵 · 못 읽음 · 컬렉션 · 읽기 전용 · SCC 비로컬일 때만 남는다(:994 · :1032 · :1068 · :1291 · :1322) — 남으면
 * FixupReferencers + 삭제, 그래도 남으면 PROMOTE_FAILED REDIRECTOR_LEFT. 호출 동안만 GIsRunningUnattendedScript — 모달은 기본값을 돌려준다
 * (MessageDialog.cpp:172): 네이티브 CDO 참조 경고(OkCancel 기본 Cancel) → rename 중단 → CDO_REFERENCED.
 * 이름 규칙은 모른다(지침서 §3.1-4) — dest 는 호출자가 전체 애셋 경로로 준다(anim_gen Job 의 promotion 제안).
 */
namespace AnimMcpPromote
{
	struct FItem
	{
		FString Source;
		FString Dest;
	};

	struct FRequest
	{
		TArray<FItem> Items;
		bool bDryRun = false;
		bool bConfirm = false;
		/** 후보 경로 밖에서도 엔진이 고쳐 저장해도 되는 참조자 — 패키지 경로로 정규화 */
		TArray<FString> AllowReferencers;
	};

	/** {assets[{source, dest}], dry_run?, confirm?, allow_referencers?[]} — 형식만 본다 */
	bool ParseRequest(const TSharedRef<FJsonObject>& Params, FRequest& Out, FAnimMcpError& OutError);

	/**
	 * dest 규칙 — 전체 애셋 경로 · 유효 · GenerationOutputPaths 밖(DEST_IS_CANDIDATE_PATH) · PromotionPaths 안(OUTSIDE_PROMOTION_PATHS) ·
	 * 보호 목록 아님(ASSET_PROTECTED) · 없음(리디렉터 · 디스크 파일 · 메모리 객체 포함, ASSET_EXISTS). 통과하면 OutObjectPath("/Game/A/B.B")
	 */
	bool ValidateDest(const FString& Dest, const FString& Field, FString& OutObjectPath, FAnimMcpError& OutError);

	/**
	 * 경로를 뺀 내용 해시(SHA-1 16진) — 승격 전후 비교용. 시퀀스 = 데이터 모델 GUID(IAnimationDataModel::GenerateGuid) + additive · 루프 ·
	 * 루트 모션 · 노티파이 수, 몽타주 · 컴포짓 = 길이 · 블렌드 · 슬롯 · 세그먼트(참조 애셋은 클래스 · 길이만) · 섹션, BlendSpace = 클래스 · 축 · 샘플 값
	 */
	FString ContentHash(const UObject* Asset);

	/** 검사(dry_run 도 같은 검사) → (dry_run 이 아니면) 엔진 rename → 사후 검증. 결과 {dry_run, planned[], moved[], fixed_referencers[], saved_packages[], redirectors, removed_files[]} */
	TSharedPtr<FJsonObject> Run(const FRequest& Request, FAnimMcpContext& Context, FAnimMcpError& OutError);
}
