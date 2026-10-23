#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * AI 애니 생성 Tool 공통 가드 (Docs/AIAnimation/ArchitectureAudit.md §10 공통 규칙).
 * 설정은 프로젝트 DefaultEngine.ini 의 [AnimGraphMcp] 섹션 — 출력·임포트 경로의 유일한 기준:
 *   +GenerationOutputPaths=/Game/Animation/Generated/   (패키지 경로 접두 — 생성 Tool 은 이 밖에 애셋을 만들거나 저장하지 않는다)
 *   +ImportSourceRoots=Saved/AnimGen/Import/            (프로젝트 기준 상대 또는 절대 디스크 경로 — import_animation_file 은 이 아래 파일만 읽는다)
 *   MaxRetargetAssetsPerCall=20
 *   +AnimationTagFiles=Config/AnimGraphMcp/AnimationTags.json   (프로젝트 기준 상대 또는 절대 — search_animations 의 수동 태그, Phase 2)
 * 목록이 비어 있으면 쓰기·임포트를 전부 거부한다(플러그인은 프로젝트 경로를 기본값으로 갖지 않는다).
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
	};

	/** 첫 조회 때 1회 로드 (에디터 기동 중 ini 변경은 반영하지 않는다 — 보호 목록과 같은 규칙) */
	const FSettings& GetSettings();

	/** get_editor_status 용 {output_paths[], import_source_roots[], max_retarget_assets_per_call} */
	TSharedRef<FJsonObject> DescribeSettings();

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
	 * 전역 더티 패키지 스냅샷 — 쓰기 Tool 은 작업 전에 만들고 끝에서 Check(또는 FinishWrite) 한다.
	 * 대상: 루트 패키지 중 트랜지언트·스크립트·PIE·읽기 전용 루트(/Temp 등)가 아닌 것 (맵 포함).
	 * 호출 전부터 더티였던 패키지는 비교에서 빠진다(남의 미저장 편집 — 이 호출이 더 바꿨는지는 알 수 없다).
	 */
	class FDirtyGuard
	{
	public:
		FDirtyGuard();

		/** 생성 이후 새로 더티가 된 패키지 이름 — 허용 목록 안 / 밖 (이름 순) */
		void GetNewlyDirty(TArray<FString>& OutAllowed, TArray<FString>& OutUnexpected) const;

		/** 허용 목록 밖이 새로 더티면 UNEXPECTED_DIRTY(details.unexpected[] · details.allowed[]) 를 채우고 false */
		bool Check(FAnimMcpError& OutError) const;

	private:
		TSet<FName> DirtyBefore;
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
