#include "AnimMcpHttpBridge.h"

#include "AnimMcpDispatcher.h"
#include "AnimMcpLog.h"
#include "HttpPath.h"
#include "HttpRequestHandler.h"
#include "HttpServerConstants.h"
#include "HttpServerModule.h"
#include "HttpServerRequest.h"
#include "HttpServerResponse.h"
#include "IHttpRouter.h"
#include "IPAddress.h"
#include "Misc/FileHelper.h"
#include "Misc/Guid.h"
#include "Misc/Paths.h"

namespace
{
	const TCHAR* const RoutePrefix = TEXT("/v1/");
	const TCHAR* const TokenHeader = TEXT("X-AnimMcp-Token");
	const FName StatusToolName(TEXT("get_editor_status"));
}

FAnimMcpHttpBridge::~FAnimMcpHttpBridge()
{
	Stop();
}

FString FAnimMcpHttpBridge::GetDefaultTokenFilePath()
{
	return FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("AnimGraphMcp"), TEXT("token")));
}

bool FAnimMcpHttpBridge::Start(uint32 InPort, bool bInRequireToken, TSharedRef<FAnimMcpDispatcher> InDispatcher)
{
	check(IsInGameThread());
	if (IsRunning())
	{
		UE_LOG(LogAnimGraphMcp, Warning, TEXT("Bridge already running on port %u"), Port);
		return true;
	}

	Port = InPort;
	bRequireToken = bInRequireToken;
	Dispatcher = InDispatcher;

	// 토큰 — 프로세스마다 새로 생성. 로컬 전용 채널이지만 다른 로컬 프로세스의 무단 호출을 막는다
	Token = FGuid::NewGuid().ToString(EGuidFormats::Digits);
	TokenFilePath = GetDefaultTokenFilePath();
	if (!FFileHelper::SaveStringToFile(Token, *TokenFilePath))
	{
		UE_LOG(LogAnimGraphMcp, Error, TEXT("Failed to write token file %s"), *TokenFilePath);
		if (bRequireToken)
		{
			return false;
		}
	}

	// 리스너 활성 플래그를 먼저 켠다 — 꺼진 상태에서 GetHttpRouter 를 부르면 바인드 실패를 알 수 없다 (HttpServerModule.cpp:158-179)
	FHttpServerModule& HttpServer = FHttpServerModule::Get();
	HttpServer.StartAllListeners();
	Router = HttpServer.GetHttpRouter(Port, /*bFailOnBindFailure*/ true);
	if (!Router.IsValid())
	{
		UE_LOG(LogAnimGraphMcp, Error, TEXT("Failed to bind HTTP listener on port %u (in use?)"), Port);
		return false;
	}

	PreprocessorHandle = Router->RegisterRequestPreprocessor(FHttpRequestHandler::CreateRaw(this, &FAnimMcpHttpBridge::PreprocessRequest));

	for (const FName ToolName : Dispatcher->GetToolNames())
	{
		const FHttpPath Path(FString(RoutePrefix) + ToolName.ToString());
		FHttpRouteHandle Handle = Router->BindRoute(Path, EHttpServerRequestVerbs::VERB_POST | EHttpServerRequestVerbs::VERB_GET,
			FHttpRequestHandler::CreateLambda([this, ToolName](const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
			{
				return HandleToolRequest(ToolName, Request, OnComplete);
			}));
		if (Handle.IsValid())
		{
			RouteHandles.Add(Handle);
		}
		else
		{
			UE_LOG(LogAnimGraphMcp, Error, TEXT("Failed to bind route %s"), *Path.GetPath());
		}
	}

	UE_LOG(LogAnimGraphMcp, Display, TEXT("AnimGraphMcp bridge listening on http://127.0.0.1:%u%s<tool> — %d tools, token %s (%s)"),
		Port, RoutePrefix, RouteHandles.Num(), bRequireToken ? TEXT("required") : TEXT("not required"), *TokenFilePath);
	return true;
}

void FAnimMcpHttpBridge::Stop()
{
	if (!Router.IsValid())
	{
		return;
	}

	for (const FHttpRouteHandle& Handle : RouteHandles)
	{
		Router->UnbindRoute(Handle);
	}
	RouteHandles.Empty();

	if (PreprocessorHandle.IsValid())
	{
		Router->UnregisterRequestPreprocessor(PreprocessorHandle);
		PreprocessorHandle.Reset();
	}

	Router.Reset();
	Dispatcher.Reset();

	if (!TokenFilePath.IsEmpty())
	{
		IFileManager::Get().Delete(*TokenFilePath, /*RequireExists*/ false, /*EvenReadOnly*/ false, /*Quiet*/ true);
	}

	UE_LOG(LogAnimGraphMcp, Display, TEXT("AnimGraphMcp bridge stopped (port %u)"), Port);
}

FString FAnimMcpHttpBridge::RequestToolName(const FHttpServerRequest& Request)
{
	FString Path = Request.RelativePath.GetPath();
	// 라우트 핸들러에는 라우트 상대 경로("/")가, 전처리기에는 전체 경로("/v1/<tool>")가 온다 — 둘 다 처리
	if (Path.StartsWith(RoutePrefix))
	{
		Path.RightChopInline(FCString::Strlen(RoutePrefix));
	}
	Path.RemoveFromStart(TEXT("/"));
	Path.RemoveFromEnd(TEXT("/"));
	return Path;
}

bool FAnimMcpHttpBridge::IsAuthorized(const FHttpServerRequest& Request) const
{
	if (!bRequireToken)
	{
		return true;
	}
	if (const TArray<FString>* Values = Request.Headers.Find(TokenHeader))
	{
		for (const FString& Value : *Values)
		{
			if (Value.Equals(Token, ESearchCase::CaseSensitive))
			{
				return true;
			}
		}
	}
	return false;
}

bool FAnimMcpHttpBridge::PreprocessRequest(const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
	const FString& FullPath = Request.RelativePath.GetPath();
	if (!FullPath.StartsWith(RoutePrefix))
	{
		return false; // 우리 라우트가 아니다 — 통과 (같은 포트를 쓰는 다른 바인딩용)
	}

	const FString ToolName = RequestToolName(Request);
	if (ToolName == StatusToolName.ToString())
	{
		return false; // 상태 조회는 토큰 면제 — 헬스체크용
	}

	if (!IsAuthorized(Request))
	{
		const FString Peer = Request.PeerAddress.IsValid() ? Request.PeerAddress->ToString(false) : TEXT("?");
		UE_LOG(LogAnimGraphMcp, Warning, TEXT("Rejected unauthorized request to %s from %s"), *FullPath, *Peer);

		const FAnimMcpError Error = FAnimMcpError::Make(AnimMcpErrorCodes::Unauthorized, FString::Printf(TEXT("Missing or invalid %s header"), TokenHeader));
		int32 Status = 401;
		const FString Body = FAnimMcpDispatcher::MakeEnvelope(FName(*ToolName), FString(), nullptr, &Error, nullptr, Status);
		Respond(OnComplete, Body, Status);
		return true; // 처리 완료 — 라우트 핸들러로 가지 않는다
	}

	return false;
}

bool FAnimMcpHttpBridge::HandleToolRequest(FName Tool, const FHttpServerRequest& Request, const FHttpResultCallback& OnComplete)
{
	if (!ensureMsgf(IsInGameThread(), TEXT("HTTP handler invoked off the game thread")))
	{
		const FAnimMcpError Error = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("Handler invoked off the game thread"));
		int32 Status = 500;
		Respond(OnComplete, FAnimMcpDispatcher::MakeEnvelope(Tool, FString(), nullptr, &Error, nullptr, Status), Status);
		return true;
	}

	if (Request.Verb != EHttpServerRequestVerbs::VERB_POST)
	{
		const FAnimMcpError Error = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("Use POST with a JSON body"));
		int32 Status = 405;
		Respond(OnComplete, FAnimMcpDispatcher::MakeEnvelope(Tool, FString(), nullptr, &Error, nullptr, Status), Status);
		return true;
	}

	if (!Dispatcher.IsValid())
	{
		const FAnimMcpError Error = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("Dispatcher not available"));
		int32 Status = 500;
		Respond(OnComplete, FAnimMcpDispatcher::MakeEnvelope(Tool, FString(), nullptr, &Error, nullptr, Status), Status);
		return true;
	}

	int32 Status = 200;
	const FString Envelope = Dispatcher->Dispatch(Tool, BodyToString(Request), Status);
	Respond(OnComplete, Envelope, Status);
	return true;
}

void FAnimMcpHttpBridge::Respond(const FHttpResultCallback& OnComplete, const FString& JsonBody, int32 HttpStatus)
{
	TUniquePtr<FHttpServerResponse> Response = FHttpServerResponse::Create(JsonBody, TEXT("application/json; charset=utf-8"));
	Response->Code = static_cast<EHttpServerResponseCodes>(HttpStatus);
	OnComplete(MoveTemp(Response));
}

FString FAnimMcpHttpBridge::BodyToString(const FHttpServerRequest& Request)
{
	if (Request.Body.Num() == 0)
	{
		return FString();
	}
	const FUTF8ToTCHAR Converter(reinterpret_cast<const ANSICHAR*>(Request.Body.GetData()), Request.Body.Num());
	return FString(Converter.Length(), Converter.Get());
}
