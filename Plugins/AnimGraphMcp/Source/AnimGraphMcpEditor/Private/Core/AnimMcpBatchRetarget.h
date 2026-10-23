#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UAnimationAsset;
class UIKRetargeter;
class USkeletalMesh;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * 일괄 리타깃 (AI 애니 생성 Phase 1 — Docs/AIAnimation/ArchitectureAudit.md §3 · §10 retarget_animations).
 *
 * 엔진 경로 (5.7.4 소스): FIKRetargetBatchOperationContext 를 직접 채워 UIKRetargetBatchOperation::RunRetarget 를 부른다. 정적
 * DuplicateAndRetarget 은 출력 폴더 인자가 없어 /Game 루트에 쓴다(NameRule.FolderPath 기본값, EditorAnimUtils.h:27).
 *   · bOverwriteExistingFiles 는 항상 false — true 면 같은 이름 애셋을 참조 교체(ForceReplaceReferences) 후 강제 삭제한다(IKRetargetBatchOperation.cpp:658-707).
 *   · AnimBlueprint 입력 거부 — 부모 ABP 까지 복제·재컴파일한다(:69-80, :302-335).
 *   · RunRetarget 은 만든 애셋 목록을 돌려주지 않는다(private). 그래서 실행 전에 엔진과 같은 규칙으로 대상 목록(GenerateAssetLists, :33-101)과
 *     출력 이름(FNameDuplicationRule::Rename, EditorAnimUtils.cpp:564-572)을 계산하고, 같은 이름이 있으면 ASSET_EXISTS · 배치 안에서
 *     겹치면 NAME_COLLISION_IN_BATCH 로 실행 전에 거부한다 — 엔진의 숫자 접미사(CreateUniqueAssetName)가 생길 여지가 없어 결과 경로가 결정적이다.
 *   · 소스는 복제본에만 작업한다(소스는 GetAnimPoseAtFrame 으로 읽기만). 결과는 더티로 남고, 저장은 save 일 때만(FinishWrite).
 *   · 진행 창(취소 가능)·토스트·콘텐츠 브라우저 선택 이동이 생긴다. 사람이 취소하면 삭제 확인 모달이 뜬다(엔진 코드 — 끌 수 없다).
 */
namespace AnimMcpBatchRetarget
{
	struct FNameRule
	{
		FString Prefix;
		FString Suffix;
		FString ReplaceFrom;
		FString ReplaceTo;
	};

	struct FParams
	{
		UIKRetargeter* Retargeter = nullptr;
		TArray<UAnimationAsset*> Assets;
		USkeletalMesh* SourceMesh = nullptr;
		USkeletalMesh* TargetMesh = nullptr;
		/** 끝 '/' 없는 폴더 */
		FString OutputPath;
		FNameRule NameRule;
		bool bIncludeReferenced = true;
		bool bDryRun = false;
		bool bValidate = true;
		/** validate 의 thresholds{} (null = 기본) */
		TSharedPtr<FJsonObject> Thresholds;
		bool bSave = false;
	};

	/**
	 * {planned[] (dry_run) | generated[{source, asset, class}], referred[], seconds, seconds_per_asset, frames, ms_per_frame, validation{}, saved}.
	 * 검증 FAILED 면 저장하지 않고 VALIDATION_FAILED(details: generated · validation).
	 */
	TSharedPtr<FJsonObject> Run(const FParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError);
}
