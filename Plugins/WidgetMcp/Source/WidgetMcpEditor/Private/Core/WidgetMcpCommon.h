#pragma once

#include "CoreMinimal.h"
#include "Core/EditorMcpGuard.h"
#include "EditorMcp.h"

class FConfigFile;

/**
 * WidgetMcp 공용 — 설정([WidgetMcp] ini) · 오류 · JSON 값 변환 · 정규 JSON · revision · 경로 가드 (설계 §6 · §9).
 *
 * 설정 키 (Config/DefaultEngine.ini [WidgetMcp]):
 *   +WidgetOutputPaths=/Game/_AutoGen/         쓰기 Tool 이 애셋을 만들 · 바꿀 · 저장 · 폐기할 수 있는 유일한 패키지 경로 접두
 *   +WidgetImportSourceRoots=Tools/uigen/work/ import_ui_textures 가 읽을 수 있는 디스크 폴더
 *   +WidgetRenderOutputRoots=Tools/uigen/work/ render_widget 이 PNG 를 쓰는 디스크 폴더(그 아래 새 · 빈 하위 폴더만)
 * 목록이 비면 그 Tool 은 아무 데도 쓰지 · 읽지 않는다.
 */
namespace WidgetMcp
{
	inline const TCHAR* const Section = TEXT("WidgetMcp");
	inline const TCHAR* const RootIdDefault = TEXT("Root");

	struct FSettings
	{
		TArray<FString> OutputPaths;     // "/Game/_AutoGen/" (정규화 접두)
		TArray<FString> ImportRoots;     // "D:/Proj/Tools/uigen/work/"
		TArray<FString> RenderRoots;
		TArray<FString> Warnings;
	};

	FSettings LoadSettings();
	FSettings LoadSettingsFromFile(const FConfigFile& File);
	TSharedRef<FJsonObject> SettingsToJson(const FSettings& Settings);

	// ---- 오류 ---------------------------------------------------------------------------------------------------
	FEditorMcpError MakeMcpError(const TCHAR* Code, const FString& Message, const TCHAR* Reason = nullptr, TSharedPtr<FJsonObject> Details = nullptr);

	// ---- JSON 값 -------------------------------------------------------------------------------------------------
	double Round3(double V);
	TSharedPtr<FJsonValue> Num(double V);
	TSharedPtr<FJsonValue> Vec2(const FVector2D& V);
	TSharedPtr<FJsonValue> Margin4(const FMargin& M);
	bool ReadNumber(const FJsonObject& Obj, const TCHAR* Key, double& Out);
	bool ReadVec2(const FJsonObject& Obj, const TCHAR* Key, FVector2D& Out);
	bool ReadMargin(const FJsonObject& Obj, const TCHAR* Key, FMargin& Out);
	bool ReadVec4(const FJsonObject& Obj, const TCHAR* Key, FVector4& Out);

	/** '#RRGGBB' · '#RRGGBBAA'(sRGB) ↔ FLinearColor. 출력은 항상 '#RRGGBBAA' 대문자 */
	bool ParseHexColor(const FString& Hex, FLinearColor& Out);
	FString ToHexColor(const FLinearColor& Color);

	/** 키를 정렬하고 수를 소수 셋째 자리로 맞춘 JSON — revision · 비교용 */
	FString CanonicalJson(const TSharedPtr<FJsonValue>& Value);
	FString CanonicalJson(const TSharedRef<FJsonObject>& Object);
	FString Sha1Revision(const FString& Text);
	/** 두 JSON 의 차이(경로: a != b) — 앞의 Limit 개 */
	void DiffJson(const TSharedPtr<FJsonValue>& A, const TSharedPtr<FJsonValue>& B, const FString& Path, TArray<FString>& Out, int32 Limit = 40);

	TArray<TSharedPtr<FJsonValue>> StringArray(const TArray<FString>& Values);

	// ---- 경로 가드 ------------------------------------------------------------------------------------------------
	/** "/Game/A/B" · "/Game/A/B.B" → "/Game/A/B" */
	FString ToPackagePath(const FString& AssetPath);
	bool PackageExists(const FString& PackagePath);
	/** 쓰기 대상 애셋(패키지) 경로가 WidgetOutputPaths 안이고 유효한가 */
	bool CheckOutputAsset(const FSettings& Settings, const FString& AssetPath, const TCHAR* Field, FEditorMcpError& OutError);
	/** run 폴더("/Game/_AutoGen/<run_id>") — 허용 접두 바로 그 자체가 아니라 그 아래 폴더여야 한다 */
	bool CheckRunFolder(const FSettings& Settings, const FString& Folder, const TCHAR* Field, FEditorMcpError& OutError);
	/** 디스크 경로가 Roots(정규화 폴더) 안인가 — 절대 경로로 풀어 OutFull */
	bool CheckDiskPath(const TArray<FString>& Roots, const FString& Path, const TCHAR* Field, const TCHAR* ConfigKey, FString& OutFull, FEditorMcpError& OutError);

	/** 쓰기 Tool 공통 — 호출 전 전역 더티 스냅샷, 끝에서 WidgetOutputPaths 밖 새 더티면 UNEXPECTED_DIRTY */
	struct FWriteGuard
	{
		EditorMcpGuard::FDirtySnapshot Snapshot;

		/** 통과면 true + OutNewlyDirty(허용 안 새 더티) */
		bool Finish(const FSettings& Settings, FEditorMcpError& OutError, TArray<FString>& OutNewlyDirty) const;
	};
}
