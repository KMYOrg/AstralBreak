#pragma once

#include "AnimMcpBodyClearance.h"
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
		/**
		 * 팔-몸통 관통 (AnimMcpBodyClearance) — Measure: 검증에 body_clearance(대상 메시 · 리타기터의 대상 IK Rig 체인), Resolve: 그 전에 새 시퀀스의
		 * 위팔 트랙을 고친다(관통한 프레임만 · 최소 어깨 회전)
		 */
		AnimMcpBodyClearance::EMode BodyClearanceMode = AnimMcpBodyClearance::EMode::Off;
		AnimMcpBodyClearance::FSpec BodyClearance;
		AnimMcpBodyClearance::FResolveOptions BodyClearanceOptions;
		/** 검증에 손가락 검사(AnimMcpFingerChains::Check) — 손 · 체인 = 리타기터의 대상 IK Rig, 매핑 = 그 FK op */
		bool bFingers = true;
		bool bSave = false;
	};

	/**
	 * 기준 포즈에 스케일이 있는 대상(게임 추출 · Blender FBX — 루트 스케일 100)의 리타깃 결과 복원. 엔진은 리타깃 포즈의 스케일을 지운 뒤 로컬로 전역을 다시 계산해
	 * (IKRetargetProcessor.cpp:45-50 · 78) 스케일 트랙이 1 이고 본 이동은 기준 로컬(스케일 없는 단위) 그대로라 메시가 기준 스케일 분의 1 로 접힌다. Pelvis Motion op 가 전역으로
	 * 정하는 펠비스만 cm 위치가 맞다 → 본마다 기준 로컬 스케일을 되돌리고, 펠비스는 그 전역 위치가 그대로이게 이동을 다시 구한다.
	 * 로컬 스케일이 모두 1(± 1e-3)이면 false — 스케일 1 대상은 트랙을 건드리지 않는다.
	 */
	bool HasRefScale(const TArray<FTransform>& RefLocal);

	/**
	 * Pelvis Motion op 크기 보정 배 — op 는 초기 높이를 리타깃 포즈에서 읽는다(PelvisMotionOp.cpp:217-224 — 펠비스 위치 · 루트 이동이 다 이 값에 비례). 엔진은 펠비스 로컬만
	 * 스케일을 구운 전역에서 다시 구해(:52-59) 부모가 원점이면 cm 가 맞고(배 1, Narmaya), 부모가 기준 위치에 있으면(SB Bip001) 펠비스도 부모와 함께 접혀 1/스케일 로 작다.
	 * Pelvis = 펠비스 기준 로컬, Chain = 루트 → 펠비스 부모 순의 기준 로컬(스케일 포함). 기준 높이 / 엔진 높이.
	 */
	double PelvisHeightFix(const FTransform& Pelvis, const TArray<FTransform>& Chain);

	/**
	 * 펠비스 새 로컬 이동 — Pelvis = 엔진 출력 로컬 이동, Chain = 루트 → 펠비스 부모 순의 이 키 로컬 변환(엔진 출력 — 스케일 1), Scales = 같은 순의 기준 로컬 스케일,
	 * Height = PelvisHeightFix(복원 전 전역 위치 · 루트 이동에 곱한다). '이동 ÷ 스케일'이 아니라 맞춘 전역 위치를 복원 후 부모 공간으로 옮긴다 — 부모가 원점이 아니어도 맞다.
	 */
	FVector RestoredPelvisLocal(const FVector& Pelvis, const TArray<FTransform>& Chain, const TArray<FVector>& Scales, double Height);

	/**
	 * {planned[] (dry_run) | generated[{source, asset, class}], referred[], seconds, seconds_per_asset, frames, ms_per_frame, body_clearance[]? (resolve · 검증 없는 measure),
	 * validation{}, saved}. 검증 FAILED 면 저장하지 않고 VALIDATION_FAILED(details: generated · validation).
	 */
	TSharedPtr<FJsonObject> Run(const FParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError);
}
