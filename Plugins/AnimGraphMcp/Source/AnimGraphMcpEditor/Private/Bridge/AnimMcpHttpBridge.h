#pragma once

#include "CoreMinimal.h"
#include "HttpRouteHandle.h"

class FAnimMcpDispatcher;
class IHttpRouter;
struct FHttpServerRequest;
typedef TFunction<void(TUniquePtr<struct FHttpServerResponse>&& Response)> FHttpResultCallback;

/**
 * 엔진 내장 HTTPServer 모듈 래퍼 — tool 마다 POST /v1/<tool> 라우트를 바인드하고 본문을 디스패처에 넘긴다.
 * 핸들러는 FHttpServerModule 의 게임 스레드 티커에서 호출된다 (HttpServerModule.h: FTSTickerObjectBase). 바인드 주소는 엔진 기본값 localhost.
 * 토큰: 기동 시 생성해 Saved/AnimGraphMcp/token 에 기록. get_editor_status 를 제외한 모든 라우트가 X-AnimMcp-Token 헤더를 요구한다.
 */
class FAnimMcpHttpBridge
{
public:
	~FAnimMcpHttpBridge();

	bool Start(uint32 InPort, bool bInRequireToken, TSharedRef<FAnimMcpDispatcher> InDispatcher);
	void Stop();

	bool IsRunning() const { return Router.IsValid(); }
	uint32 GetPort() const { return Port; }
	bool IsTokenRequired() const { return bRequireToken; }
	const FString& GetTokenFilePath() const { return TokenFilePath; }

	static FString GetDefaultTokenFilePath();

private:
	bool HandleToolRequest(FName Tool, const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
	bool PreprocessRequest(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete);
	bool IsAuthorized(const FHttpServerRequest& Request) const;

	static void Respond(const FHttpResultCallback& OnComplete, const FString& JsonBody, int32 HttpStatus);
	static FString BodyToString(const FHttpServerRequest& Request);
	static FString RequestToolName(const FHttpServerRequest& Request);

	TSharedPtr<IHttpRouter> Router;
	TArray<FHttpRouteHandle> RouteHandles;
	FDelegateHandle PreprocessorHandle;
	TSharedPtr<FAnimMcpDispatcher> Dispatcher;

	uint32 Port = 0;
	bool bRequireToken = true;
	FString Token;
	FString TokenFilePath;
};
