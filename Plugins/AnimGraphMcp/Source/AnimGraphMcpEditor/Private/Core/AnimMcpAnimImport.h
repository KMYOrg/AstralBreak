#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class USkeleton;
struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * FBX 임포트 (AI 애니 생성 Phase 1 — Docs/AIAnimation/ArchitectureAudit.md §1 · §10 import_animation_file).
 *
 * 엔진 경로 (5.7.4 소스):
 *   UInterchangeManager::ImportAsset(ContentPath, SourceData, FImportAssetParameters, OutObjects) — bRunSynchronous=true 로 작업을 호출 스레드에서
 *   끝까지 돌린다(InterchangeManager.cpp:1705-1712). 파이프라인은 프로젝트 기본 콘텐츠 스택(FBX = "Assets" → DefaultAssetsPipeline)을 **트랜지언트로
 *   복제**해 OverridePipelines 로 넘긴다 — 원본은 엔진 플러그인 콘텐츠라 수정하면 엔진 애셋이 더티가 된다. 매니저는 넘긴 경로를 TryLoad 해
 *   다시 복제한다(GeneratePipelineInstance, :958-1003). 스택의 파이프라인은 전부 UInterchangeGenericAssetsPipeline 이어야 한다(설정을 보증할 수 없는
 *   파이프라인은 거부).
 *   항상 끄는 것: bAddCurveMetadataToSkeleton(기본 true — 기존 스켈레톤에 커브 메타데이터를 더하고 더티로 만든다, Skeleton.cpp:1826-1846) ·
 *   재질 · 텍스처 · 피직스 애셋 · 스태틱 메시. bReplaceExisting=false · bIsAutomated=true(모달 없음).
 *   skeleton 을 주면 bImportOnlyAnimations + Skeleton(애니만), 없으면 메시·스켈레톤·애니를 새로.
 * 대상 폴더는 **비어 있어야** 한다 — FBX 하나에서 생길 이름(메시·스켈레톤·테이크)을 미리 알 수 없어서, 덮어쓰기·재임포트 전환·이름 바꿈이 일어날
 * 여지를 원천 차단한다(InterchangeManager.cpp:1914-2002 는 같은 이름 애셋이 있으면 재임포트로 바꾸거나 대화상자를 띄운다).
 */
namespace AnimMcpAnimImport
{
	struct FParams
	{
		/** 정규화된 절대 경로 (AnimMcpGeneration::ResolveImportSource 통과) */
		FString File;
		/** 끝 '/' 없는 폴더 */
		FString DestPath;
		USkeleton* Skeleton = nullptr;
		/** 0 = Interchange 자동(원본에 가장 맞는 레이트) */
		int32 SampleRate = 0;
		/** 비면 파일 이름 */
		FString Name;
		bool bSave = false;
	};

	/** 결과 {imported[], animations[{asset, skeleton, frame_rate, frames, length}], skeleton, mesh, source_frame_rate, pipelines[], seconds, saved} */
	TSharedPtr<FJsonObject> Import(const FParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError);
}
