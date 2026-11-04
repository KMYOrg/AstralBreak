#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Misc/Optional.h"

struct FAnimMcpContext;
struct FAnimMcpError;
struct FAnimMcpRequest;

/**
 * AI 애니 생성 Tool 공통 가드 (Docs/AIAnimation/ArchitectureAudit.md §10 공통 규칙).
 * 설정은 프로젝트 DefaultEngine.ini 의 [AnimGraphMcp] 섹션 — 출력·임포트 경로의 유일한 기준:
 *   +GenerationOutputPaths=/Game/Animation/Generated/   (패키지 경로 접두 — 생성 Tool 은 이 밖에 애셋을 만들거나 저장하지 않는다)
 *   +ImportSourceRoots=Saved/AnimGen/Import/            (프로젝트 기준 상대 또는 절대 디스크 경로 — import_animation_file 은 이 아래 파일만 읽는다)
 *   MaxRetargetAssetsPerCall=20
 *   +AnimationTagFiles=Config/AnimGraphMcp/AnimationTags.json   (프로젝트 기준 상대 또는 절대 — search_animations 의 수동 태그, Phase 2)
 *   +PromotionPaths=/Game/Animation/Hero/               (패키지 경로 접두 — promote_animation 의 정식 경로 허용 목록, Phase 7)
 *   +CaptureOutputRoots=Tools/mcp/results/capture/      (프로젝트 기준 상대 또는 절대 디스크 경로 — capture_animation 이 이미지를 쓰는 폴더, Phase 8-2)
 * 목록이 비어 있으면 쓰기·임포트·승격·캡처를 전부 거부한다(플러그인은 프로젝트 경로를 기본값으로 갖지 않는다).
 * 원본 보호는 애셋별 검사가 아니라 에디터 전체의 더티 패키지 집합 차이로 본다(FDirtyGuard) — 모르는 부작용
 * (임포트가 기존 스켈레톤에 커브 메타데이터를 더하는 것 등)도 같은 한 곳에서 잡힌다.
 */
namespace AnimMcpGeneration
{
	struct FSettings
	{
		/** 정규화된 패키지 경로 접두 ("/Game/A/" — 항상 '/' 로 끝난다) */
		TArray<FString> OutputPaths;
		/** 정규화된 절대 디스크 경로 ("D:/Proj/Saved/AnimGen/Import/" — '/' 구분, '/' 로 끝난다) */
		TArray<FString> ImportSourceRoots;
		int32 MaxRetargetAssetsPerCall = 20;
		/** 정규화된 절대 디스크 경로 ('/' 구분) — 없으면 수동 태그 없음 */
		TArray<FString> AnimationTagFiles;
		/** 승격(promote_animation) 대상 접두 — OutputPaths 와 겹치는 항목은 뺀다 (NormalizePromotionPaths) */
		TArray<FString> PromotionPaths;
		/** 캡처(capture_animation) 이미지 출력 루트 — ImportSourceRoots 와 같은 정규화 ("D:/Proj/Tools/mcp/results/capture/") */
		TArray<FString> CaptureOutputRoots;
	};

	/** 첫 조회 때 1회 로드 (에디터 기동 중 ini 변경은 반영하지 않는다 — 보호 목록과 같은 규칙) */
	const FSettings& GetSettings();

	/** get_editor_status 용 {output_paths[], import_source_roots[], max_retarget_assets_per_call, animation_tag_files[], promotion_paths[], capture_output_roots[]} */
	TSharedRef<FJsonObject> DescribeSettings();

	/**
	 * PromotionPaths 원문 → 정규화된 접두. 마운트 루트("/Game/")와 OutputPaths 와 겹치는 항목(어느 한쪽이 다른 쪽 안)은 뺀다 —
	 * 승격은 후보 경로 → 정식 경로 이동이라 두 목록이 겹치면 "후보 밖으로 옮겼다" 가 성립하지 않는다. 뺀 항목은 OutIgnored(사유 포함)
	 */
	TArray<FString> NormalizePromotionPaths(const TArray<FString>& Raw, const TArray<FString>& OutputPaths, TArray<FString>* OutIgnored = nullptr);

	/** 애셋 경로("/Game/A/B" · "/Game/A/B.B")가 Prefixes(정규화 접두) 중 하나 안인가 — IsOutputPathAllowed 와 같은 '/' 경계 규칙 */
	bool IsUnderAnyPrefix(const FString& Path, const TArray<FString>& Prefixes);

	/** 애셋 경로가 PromotionPaths 안인가 */
	bool IsPromotionPathAllowed(const FString& Path);

	/** 폴더 경로 정규화 — "/Game/A/" · "/Game/A" → "/Game/A" (끝 '/' 없음 — 엔진 FNameDuplicationRule::FolderPath 규약) */
	FString NormalizeFolderPath(const FString& Path);

	/** 폴더("/Game/A" · "/Game/A/") 또는 애셋("/Game/A/B" · "/Game/A/B.B") 경로가 허용 목록 안인가 */
	bool IsOutputPathAllowed(const FString& Path);

	/** 유효한 패키지 경로가 아니면 BAD_REQUEST, 허용 목록 밖이면 OUTPUT_PATH_NOT_ALLOWED. Field 는 details.field */
	bool EnsureOutputPathAllowed(const FString& Path, const TCHAR* Field, FAnimMcpError& OutError);

	/**
	 * 임포트 원본 파일 검사 — 절대 경로 · 허용 루트 아래 · 존재. 통과하면 OutAbsolute 에 정규화한 경로('/' 구분).
	 * 상대 경로·없는 파일은 BAD_REQUEST(details.reason RELATIVE_PATH · FILE_NOT_FOUND), 루트 밖은 IMPORT_SOURCE_NOT_ALLOWED.
	 * 루트 검사를 존재 검사보다 먼저 한다 — 루트 밖 파일의 존재 여부를 알려 주지 않는다.
	 */
	bool ResolveImportSource(const FString& File, FString& OutAbsolute, FAnimMcpError& OutError);

	/**
	 * 캡처 출력 폴더 검사 (Phase 8-2) — 절대 경로 · CaptureOutputRoots 아래(루트 자체는 아님) · 없거나 빈 폴더. 통과하면 OutAbsolute 에 '/' 구분 · 끝 '/' 없는 경로.
	 * 상대 경로는 BAD_REQUEST(RELATIVE_PATH), 루트 밖 · 루트 자체는 OUTPUT_PATH_NOT_ALLOWED(reason CAPTURE_ROOT), 파일이거나 비어 있지 않으면 BAD_REQUEST(OUTPUT_DIR_NOT_EMPTY).
	 * 폴더를 만들지는 않는다(호출자가 쓰기 직전에).
	 */
	bool ResolveCaptureDir(const FString& Dir, FString& OutAbsolute, FAnimMcpError& OutError);

	/**
	 * capture_animation 비교 칸 이미지 검사 (Phase 8-3) — 절대 경로 · 존재 · ImportSourceRoots 또는 CaptureOutputRoots 아래(앞선 캡처 결과를 비교 칸으로 —
	 * 보정 전 · 후 비교 시트). 루트 밖이면 IMPORT_SOURCE_NOT_ALLOWED(details.allowed 에 두 루트 목록), 나머지 오류는 ResolveImportSource 와 같다.
	 */
	bool ResolveCompareImage(const FString& File, FString& OutAbsolute, FAnimMcpError& OutError);

	/**
	 * 전역 더티 패키지 스냅샷 — 쓰기 Tool 은 작업 전에 만들고 끝에서 Check(또는 FinishWrite) 한다.
	 * 대상: 루트 패키지 중 트랜지언트·스크립트·PIE·읽기 전용 루트(/Temp 등)가 아닌 것 (맵 포함).
	 * 호출 전부터 더티였던 패키지는 비교에서 빠진다(남의 미저장 편집 — 이 호출이 더 바꿨는지는 알 수 없다).
	 */
	class FDirtyGuard
	{
	public:
		FDirtyGuard();

		/**
		 * 생성 이후 새로 더티가 된 패키지 이름 — 허용 목록 안 / 밖 (이름 순).
		 * ExtraAllowed(패키지 이름, 정확히 일치)는 허용 목록 밖이어도 허용 쪽으로 센다 — 승격의 정식 경로 · 명시한 참조자 (Phase 7)
		 */
		void GetNewlyDirty(TArray<FString>& OutAllowed, TArray<FString>& OutUnexpected, const TSet<FName>* ExtraAllowed = nullptr) const;

		/** 허용 목록(∪ ExtraAllowed) 밖이 새로 더티면 UNEXPECTED_DIRTY(details.unexpected[] · details.allowed[]) 를 채우고 false */
		bool Check(FAnimMcpError& OutError, const TSet<FName>* ExtraAllowed = nullptr) const;

	private:
		TSet<FName> DirtyBefore;
	};

	/**
	 * 기존 쓰기 Tool 의 옵트인 생성 가드 (Phase 7 — 요청 generation_guard=true. 기본 false = 기존 동작 그대로).
	 * 대상: create_anim_montage · set_montage_sections · create_blendspace · set_sequence_additive · duplicate_animation_blueprint ·
	 * apply_graph_operations. 켜면 생성 Tool 과 같은 규칙을 받는다 — 쓰는 애셋이 GenerationOutputPaths 안(OUTPUT_PATH_NOT_ALLOWED) ·
	 * overwrite 거부 · 호출 전후 전역 더티 비교(UNEXPECTED_DIRTY — 저장 전에 검사, 실패면 저장 안 함) · 결과에 guard{enabled, newly_dirty[]}.
	 * 가드 규칙의 원천은 이 한 곳이다 — anim_gen 은 포장 · 연결 단계에서 켜기만 한다(규칙을 따로 두지 않는다).
	 * 쓰는 순서: 핸들러 첫 줄에서 만든다(더티 스냅샷) → CheckPath · RefuseOverwrite → 작업 → 저장 직전 Check → Describe.
	 */
	class FWriteGuard
	{
	public:
		explicit FWriteGuard(const FAnimMcpRequest& Request);

		bool IsEnabled() const { return bEnabled; }

		/** 켜져 있으면 Path(애셋 · 폴더)가 허용 목록 안인지(EnsureOutputPathAllowed). 꺼져 있으면 항상 true */
		bool CheckPath(const FString& Path, const TCHAR* Field, FAnimMcpError& OutError) const;

		/** 켜져 있고 bOverwrite 면 BAD_REQUEST(reason OVERWRITE_NOT_ALLOWED) — 생성 가드는 덮어쓰지 않는다 */
		bool RefuseOverwrite(bool bOverwrite, FAnimMcpError& OutError) const;

		/** 저장 직전에 부른다. 켜져 있으면 전역 더티 비교 — 허용 목록 밖이 새로 더티면 UNEXPECTED_DIRTY 로 false(저장하지 말 것) */
		bool Check(FAnimMcpError& OutError);

		/** 켜져 있으면 Result 에 guard{enabled, newly_dirty[]} (Check 뒤의 허용 목록 안 새 더티). 꺼져 있으면 아무것도 넣지 않는다 */
		void Describe(const TSharedRef<FJsonObject>& Result) const;

	private:
		bool bEnabled = false;
		TOptional<FDirtyGuard> Dirty;
		TArray<FString> NewlyDirty;
	};

	/**
	 * 쓰기 Tool 공통 마무리. Guard.Check 실패면 아무것도 저장하지 않고 false(UNEXPECTED_DIRTY — 만든 애셋은 메모리에 미저장으로 남는다).
	 * 통과하고 bSave 면 Assets 를 강제 저장한다. 허용 목록 밖 애셋은 저장하지 않고 OUTPUT_PATH_NOT_ALLOWED,
	 * 저장 실패는 SAVE_FAILED(details.failed[]) — 요청한 저장이 끝나지 않았으면 ok 가 아니다.
	 */
	bool FinishWrite(const FDirtyGuard& Guard, const TArray<UObject*>& Assets, bool bSave, FAnimMcpContext& Context, FAnimMcpError& OutError, bool& bOutSaved);

	/**
	 * 새 애셋 객체 — 허용 목록 검사 · 이미 있으면 ASSET_EXISTS(생성 Tool 은 덮어쓰지 않는다 — 메모리에만 남은 같은 이름 객체도 거부) ·
	 * CreatePackage → NewObject(RF_Public|RF_Standalone|RF_Transactional) → AssetCreated → MarkPackageDirty (AnimMcpMontage::CreateMontage 와 같은 순서).
	 * 내용은 호출자가 채운다. Field 는 오류 details.field
	 */
	UObject* CreateAssetObject(UClass* Class, const FString& AssetPath, const TCHAR* Field, FAnimMcpError& OutError);

	/**
	 * 기존 애셋의 복제본 — CreateAssetObject 와 같은 검사(허용 목록 · ASSET_EXISTS) 뒤 StaticDuplicateObject → AssetCreated → MarkPackageDirty.
	 * IAssetTools::DuplicateAsset 을 쓰지 않는다: 소스 컨트롤이 켜져 있으면 즉시 저장하고(save=false 규약 위반) 이름이 겹치면 모달을 띄운다
	 * (AssetTools.cpp PerformDuplicateAsset · CanCreateAsset). 원본은 읽기만 한다
	 */
	UObject* DuplicateAssetObject(UObject* Source, const FString& AssetPath, const TCHAR* Field, FAnimMcpError& OutError);

	/** 문자열 배열 → JSON 배열 */
	TArray<TSharedPtr<FJsonValue>> ToJsonArray(const TArray<FString>& Values);
}
