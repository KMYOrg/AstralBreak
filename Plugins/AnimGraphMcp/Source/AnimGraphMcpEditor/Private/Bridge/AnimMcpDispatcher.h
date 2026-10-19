#pragma once

#include "CoreMinimal.h"
#include "AnimMcpTypes.h"

/**
 * Tool 이름 → 핸들러 테이블 + 공통 응답 봉투 + request_id 멱등 캐시.
 * 전송 계층(HTTP)을 모른다 — 문자열 본문을 받아 문자열 봉투를 돌려준다. 게임 스레드 전용.
 */
class FAnimMcpDispatcher
{
public:
	struct FToolEntry
	{
		FAnimMcpHandler Handler;
		FString Description;
	};

	void RegisterTool(FName Name, const FString& Description, FAnimMcpHandler Handler);
	bool HasTool(FName Name) const { return Tools.Contains(Name); }
	TArray<FName> GetToolNames() const;
	const FString* GetToolDescription(FName Name) const;

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

	struct FCachedResponse
	{
		FString Envelope;
		int32 HttpStatus = 200;
	};
	TMap<FString, FCachedResponse> RequestCache;
	TArray<FString> RequestCacheOrder;
	static constexpr int32 MaxCachedRequests = 256;
};
