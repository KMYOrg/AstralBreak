#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

struct FAnimMcpContext;
struct FAnimMcpError;

/**
 * search_animations — 기존 모션 메타데이터 검색 (AI 애니 생성 Phase 2 — Docs/AIAnimation/DevelopmentGuide.md §14 Phase 2).
 * 인덱스 = AssetRegistry 태그(로드 없음: SequenceLength · bEnableRootMotion · AdditiveAnimType · Skeleton · "Number of Frames" ·
 * "Source Frame Rate") + 수동 태그 파일([AnimGraphMcp] AnimationTagFiles, JSON {"tags": {"<애셋 또는 '/'로 끝나는 폴더>": [..]}}).
 * bLoop 은 레지스트리 태그가 아니다(AnimSequenceBase.h) — loop 필터와 details 만 애셋을 로드하고, 로드 수는 max_loads 로 묶는다.
 * 이름 검색은 단순 토큰 일치: 이름을 '_' · CamelCase · 숫자 경계로 쪼개 소문자 토큰으로 만들고, 질의 토큰마다 이름 또는 폴더 토큰에
 * 같거나(이름 3 · 폴더 1.5) 접두로 맞아야(이름 2 · 폴더 1) 한다. 하나라도 안 맞으면 제외. 자동 태깅은 이후 단계.
 */
namespace AnimMcpAnimSearch
{
	struct FQuery
	{
		/** 소문자 질의 토큰 */
		TArray<FString> Tokens;
		/** 스켈레톤 오브젝트 경로 (빈 = 전부) */
		FString Skeleton;
		FString PathPrefix = TEXT("/Game");
		/** AnimSequence | AnimMontage | AnimComposite | all (AnimSequenceBase 하위 전부) */
		FString Class = TEXT("AnimSequence");
		TOptional<double> MinLength;
		TOptional<double> MaxLength;
		TOptional<bool> bRootMotion;
		TOptional<bool> bAdditive;
		TOptional<bool> bLoop;
		/** 소문자 수동 태그 — 전부 있어야 한다 */
		TArray<FString> Tags;
		int32 Limit = 50;
		bool bDetails = false;
		int32 MaxLoads = 300;
	};

	/** 이름 → 소문자 토큰 ("AS_Vesper_Rifle_TurnLeft_90" → as, vesper, rifle, turn, left, 90) */
	TArray<FString> Tokenize(const FString& Text);

	TSharedPtr<FJsonObject> Search(const FQuery& Query, FAnimMcpContext& Context, FAnimMcpError& OutError);
}
