#pragma once

#include "CoreMinimal.h"
#include "AnimMcpTypes.h"

/**
 * Tool 이름 → 핸들러 테이블 + 공통 응답 봉투 + request_id 멱등 캐시.
 * 전송 계층(HTTP)을 모른다 — 문자열 본문을 받아 문자열 봉투를 돌려준다. 게임 스레드 전용.
 *
 * (2026-11-14 플러그인 분리) Tool 마다 소유 기능(Feature)을 기억한다 — 코어가 BeginFeature/EndFeature 사이에 기능 플러그인의
 * 등록 함수를 돌리고, 기능이 내려갈 때 RemoveFeature 로 그 기능의 Tool 만 뺀다. 시험처럼 기능 없이 쓰면 소유는 NAME_None.
 */
class EDITORMCPCORE_API FAnimMcpDispatcher
{
public:
	struct FToolEntry
	{
		FAnimMcpHandler Handler;
		FString Description;
		FName Feature;
	};

	void RegisterTool(FName Name, const FString& Description, FAnimMcpHandler Handler);
	bool HasTool(FName Name) const { return Tools.Contains(Name); }
	TArray<FName> GetToolNames() const;
	const FString* GetToolDescription(FName Name) const;

	/** 이 뒤로 RegisterTool 되는 Tool 의 소유 기능. EndFeature 까지 */
	void BeginFeature(FName Feature) { CurrentFeature = Feature; }
	void EndFeature() { CurrentFeature = NAME_None; }

	/** 소유 기능. 없는 Tool 이면 NAME_None */
	FName GetToolFeature(FName Name) const;

	/** 그 기능의 Tool 수 */
	int32 CountFeatureTools(FName Feature) const;

	/** 그 기능의 Tool 을 지우고 request_id 캐시를 비운다(지운 Tool 의 캐시 봉투가 남지 않게). 지운 이름을 돌려준다 */
	TArray<FName> RemoveFeature(FName Feature);

	/**
	 * 본문(JSON 객체, 선택 필드 request_id) → envelope JSON.
	 * 같은 (tool, request_id) 재호출은 캐시된 봉투를 그대로 돌려주고 핸들러를 다시 실행하지 않는다.
	 */
	FString Dispatch(FName Tool, const FString& BodyJson, int32& OutHttpStatus);

	/** envelope 생성 — 전송 계층이 핸들러 밖 오류(인증·메서드)를 같은 모양으로 돌려줄 때도 쓴다 */
	static FString MakeEnvelope(FName Tool, const FString& RequestId, TSharedPtr<FJsonObject> Result, const FAnimMcpError* Error, const TArray<TSharedPtr<FJsonValue>>* Diagnostics, int32& OutHttpStatus);

	void ClearRequestCache();

private:
	TMap<FName, FToolEntry> Tools;
	FName CurrentFeature;

	struct FCachedResponse
	{
		FString Envelope;
		int32 HttpStatus = 200;
	};
	TMap<FString, FCachedResponse> RequestCache;
	TArray<FString> RequestCacheOrder;
	static constexpr int32 MaxCachedRequests = 256;
};
