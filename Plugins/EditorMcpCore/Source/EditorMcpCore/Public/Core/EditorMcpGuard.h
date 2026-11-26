#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonValue.h"

class UPackage;
struct FAnimMcpError;

/**
 * 쓰기 Tool 공통 가드의 기능 독립 부분 (2026-11-14 플러그인 분리 — AnimGraphMcp 의 AnimMcpGeneration 에서 떼어 냄).
 *
 *   쓰기 허용 경로   패키지 경로 접두 목록(예: GenerationOutputPaths · WidgetOutputPaths)과 '/' 경계 비교.
 *   전역 더티 비교   쓰기 전에 에디터 전체의 더티 패키지 스냅샷을 찍고, 끝에서 새로 더티가 된 패키지를 허용 목록 안 / 밖으로 가른다.
 *                    애셋별 검사가 아니라 전역 집합 차이라서 모르는 부작용(임포트가 기존 스켈레톤을 고치는 것 등)도 같은 자리에서 잡힌다.
 *
 * 목록 자체(어느 ini 키인가)와 오류 문구는 기능 쪽이 정한다 — AnimGraphMcp 는 AnimMcpGeneration, WidgetMcp 는 자기 설정.
 */
namespace EditorMcpGuard
{
	/** "/Game/A" · "/Game/A/" → "/Game/A/" (빈 문자열은 그대로) */
	EDITORMCPCORE_API FString NormalizePrefix(const FString& Raw);

	/**
	 * 마운트 루트 자체("/Game/")가 아닌 유효한 폴더 접두인가 — 루트는 허용 목록이 아니라 '전부 허용' 이 되므로 받지 않는다.
	 * (주의) FPackageName::IsValidLongPackageName("/Game") 만으로는 루트가 통과한다 — 5.7.4 실측. AnimGraphMcp 의 생성 경로 설정은
	 * 분리 전 판정을 그대로 쓴다(동작 불변 원칙 — 후속 과제)
	 */
	EDITORMCPCORE_API bool IsValidPrefix(const FString& NormalizedPrefix);

	/** 프로젝트 기준 상대 또는 절대 디스크 경로 → "D:/Proj/X/" ('/' 구분, '/' 로 끝남). 빈 문자열은 그대로 */
	EDITORMCPCORE_API FString NormalizeDirectory(const FString& Raw);

	/** 폴더 경로 정규화 — "/Game/A/" · "/Game/A" → "/Game/A" (끝 '/' 없음) */
	EDITORMCPCORE_API FString NormalizeFolderPath(const FString& Path);

	/** 애셋("/Game/A/B" · "/Game/A/B.B") 또는 폴더 경로가 Prefixes(정규화 접두) 중 하나 안인가 — "/Game/A/TestX" 는 "/Game/A/Test/" 에 걸리지 않는다 */
	EDITORMCPCORE_API bool IsUnderAnyPrefix(const FString& Path, const TArray<FString>& Prefixes);

	/** 더티 비교 대상 — 루트 패키지 중 트랜지언트 · 스크립트 · PIE · 읽기 전용 루트(/Temp 등)가 아닌 것 (맵 포함) */
	EDITORMCPCORE_API bool IsTrackedPackage(const UPackage* Package);

	/** 지금 더티인 추적 대상 패키지 이름 */
	EDITORMCPCORE_API void CollectDirtyPackages(TSet<FName>& Out);

	/**
	 * 전역 더티 패키지 스냅샷. 만들 때 찍고, GetNewlyDirty 로 그 뒤 새로 더티가 된 것을 가른다.
	 * 호출 전부터 더티였던 패키지는 비교에서 빠진다(남의 미저장 편집 — 이 호출이 더 바꿨는지는 알 수 없다).
	 */
	class EDITORMCPCORE_API FDirtySnapshot
	{
	public:
		FDirtySnapshot();

		/**
		 * 새로 더티가 된 패키지 — AllowedPrefixes 안(또는 ExtraAllowed 에 이름이 정확히 있음) / 밖 (이름 순)
		 */
		void GetNewlyDirty(const TArray<FString>& AllowedPrefixes, TArray<FString>& OutAllowed, TArray<FString>& OutUnexpected, const TSet<FName>* ExtraAllowed = nullptr) const;

		const TSet<FName>& GetDirtyBefore() const { return DirtyBefore; }

	private:
		TSet<FName> DirtyBefore;
	};

	/** 문자열 배열 → JSON 배열 */
	EDITORMCPCORE_API TArray<TSharedPtr<FJsonValue>> ToJsonArray(const TArray<FString>& Values);
}
