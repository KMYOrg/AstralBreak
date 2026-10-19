#include "AnimMcpDispatcher.h"

#include "AnimMcpLog.h"

void FAnimMcpDispatcher::RegisterTool(FName Name, const FString& Description, FAnimMcpHandler Handler)
{
	check(IsInGameThread());
	ensureMsgf(!Tools.Contains(Name), TEXT("AnimGraphMcp tool '%s' registered twice"), *Name.ToString());
	FToolEntry& Entry = Tools.FindOrAdd(Name);
	Entry.Handler = MoveTemp(Handler);
	Entry.Description = Description;
}

TArray<FName> FAnimMcpDispatcher::GetToolNames() const
{
	TArray<FName> Names;
	Tools.GetKeys(Names);
	Names.Sort(FNameLexicalLess());
	return Names;
}

const FString* FAnimMcpDispatcher::GetToolDescription(FName Name) const
{
	const FToolEntry* Entry = Tools.Find(Name);
	return Entry ? &Entry->Description : nullptr;
}

FString FAnimMcpDispatcher::MakeEnvelope(FName Tool, const FString& RequestId, TSharedPtr<FJsonObject> Result, const FAnimMcpError* Error, const TArray<TSharedPtr<FJsonValue>>* Diagnostics, int32& OutHttpStatus)
{
	const bool bOk = (Error == nullptr) || !Error->IsSet();

	TSharedRef<FJsonObject> Envelope = AnimMcpJson::MakeObject();
	Envelope->SetBoolField(TEXT("ok"), bOk);
	Envelope->SetStringField(TEXT("tool"), Tool.ToString());
	Envelope->SetField(TEXT("request_id"), AnimMcpJson::StringOrNull(RequestId));

	if (bOk)
	{
		Envelope->SetObjectField(TEXT("result"), Result.IsValid() ? Result : AnimMcpJson::MakeObject().ToSharedPtr());
		Envelope->SetField(TEXT("error"), MakeShared<FJsonValueNull>());
		OutHttpStatus = 200;
	}
	else
	{
		Envelope->SetField(TEXT("result"), MakeShared<FJsonValueNull>());
		Envelope->SetObjectField(TEXT("error"), Error->ToJson());
		OutHttpStatus = Error->ToHttpStatus();
	}

	Envelope->SetArrayField(TEXT("diagnostics"), Diagnostics ? *Diagnostics : TArray<TSharedPtr<FJsonValue>>());
	return AnimMcpJson::ToString(Envelope);
}

FString FAnimMcpDispatcher::Dispatch(FName Tool, const FString& BodyJson, int32& OutHttpStatus)
{
	// 설계 전제를 가정이 아니라 검증으로 — HTTP 핸들러는 게임 스레드 티커에서 불려야 한다
	if (!ensureMsgf(IsInGameThread(), TEXT("AnimGraphMcp dispatch off the game thread")))
	{
		const FAnimMcpError Error = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("Dispatch invoked off the game thread"));
		return MakeEnvelope(Tool, FString(), nullptr, &Error, nullptr, OutHttpStatus);
	}

	const FToolEntry* Entry = Tools.Find(Tool);
	if (!Entry)
	{
		const FAnimMcpError Error = FAnimMcpError::Make(AnimMcpErrorCodes::ToolNotFound, FString::Printf(TEXT("Unknown tool '%s'"), *Tool.ToString()));
		return MakeEnvelope(Tool, FString(), nullptr, &Error, nullptr, OutHttpStatus);
	}

	// 본문 파싱 — 빈 본문은 빈 객체로 취급 (파라미터 없는 tool)
	TSharedPtr<FJsonObject> Params;
	if (BodyJson.TrimStartAndEnd().IsEmpty())
	{
		Params = AnimMcpJson::MakeObject();
	}
	else
	{
		FString ParseError;
		if (!AnimMcpJson::Parse(BodyJson, Params, ParseError))
		{
			const FAnimMcpError Error = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Invalid JSON body: %s"), *ParseError));
			return MakeEnvelope(Tool, FString(), nullptr, &Error, nullptr, OutHttpStatus);
		}
	}

	FString RequestId;
	Params->TryGetStringField(TEXT("request_id"), RequestId);

	// 멱등 캐시 — 같은 요청의 재전송은 재실행하지 않는다
	const FString CacheKey = RequestId.IsEmpty() ? FString() : (Tool.ToString() + TEXT("|") + RequestId);
	if (!CacheKey.IsEmpty())
	{
		if (const FCachedResponse* Cached = RequestCache.Find(CacheKey))
		{
			UE_LOG(LogAnimGraphMcp, Verbose, TEXT("Replaying cached response for %s"), *CacheKey);
			OutHttpStatus = Cached->HttpStatus;
			return Cached->Envelope;
		}
	}

	const FAnimMcpRequest Request(Tool, RequestId, Params.ToSharedRef());
	FAnimMcpContext Context(Request);
	FAnimMcpError Error;
	TSharedPtr<FJsonObject> Result;

	{
		const double StartSeconds = FPlatformTime::Seconds();
		Result = Entry->Handler(Context, Error);
		const double ElapsedMs = (FPlatformTime::Seconds() - StartSeconds) * 1000.0;
		UE_LOG(LogAnimGraphMcp, Log, TEXT("%s%s %s (%.1f ms)"), *Tool.ToString(),
			RequestId.IsEmpty() ? TEXT("") : *FString::Printf(TEXT("[%s]"), *RequestId),
			Error.IsSet() ? *FString::Printf(TEXT("FAILED %s: %s"), *Error.Code, *Error.Message) : TEXT("ok"),
			ElapsedMs);
	}

	const FString Envelope = MakeEnvelope(Tool, RequestId, Result, &Error, &Context.Diagnostics, OutHttpStatus);

	if (!CacheKey.IsEmpty())
	{
		if (RequestCacheOrder.Num() >= MaxCachedRequests)
		{
			RequestCache.Remove(RequestCacheOrder[0]);
			RequestCacheOrder.RemoveAt(0);
		}
		FCachedResponse& Cached = RequestCache.Add(CacheKey);
		Cached.Envelope = Envelope;
		Cached.HttpStatus = OutHttpStatus;
		RequestCacheOrder.Add(CacheKey);
	}

	return Envelope;
}

void FAnimMcpDispatcher::ClearRequestCache()
{
	RequestCache.Empty();
	RequestCacheOrder.Empty();
}
