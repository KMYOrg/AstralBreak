#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"

/**
 * 오류 코드 — Python MCP 서버와 공유하는 계약. 문자열 그대로 envelope.error.code 에 실린다.
 * (Phase 1 보고서 §C-5)
 */
namespace AnimMcpErrorCodes
{
	inline const TCHAR* const BadRequest         = TEXT("BAD_REQUEST");
	inline const TCHAR* const Unauthorized       = TEXT("UNAUTHORIZED");
	inline const TCHAR* const ToolNotFound       = TEXT("TOOL_NOT_FOUND");
	inline const TCHAR* const AssetNotFound      = TEXT("ASSET_NOT_FOUND");
	inline const TCHAR* const AssetExists        = TEXT("ASSET_EXISTS");
	inline const TCHAR* const GraphNotFound      = TEXT("GRAPH_NOT_FOUND");
	inline const TCHAR* const NodeNotFound       = TEXT("NODE_NOT_FOUND");
	inline const TCHAR* const PinNotFound        = TEXT("PIN_NOT_FOUND");
	inline const TCHAR* const RevisionMismatch   = TEXT("REVISION_MISMATCH");
	inline const TCHAR* const ConnectionRejected = TEXT("CONNECTION_REJECTED");
	inline const TCHAR* const PropertyNotAllowed = TEXT("PROPERTY_NOT_ALLOWED");
	inline const TCHAR* const CompileFailed      = TEXT("COMPILE_FAILED");
	inline const TCHAR* const SaveFailed         = TEXT("SAVE_FAILED");
	inline const TCHAR* const Internal           = TEXT("INTERNAL");
}

/** 핸들러가 채우는 오류. Code 가 비어 있으면 성공 */
struct FAnimMcpError
{
	FString Code;
	FString Message;
	TSharedPtr<FJsonObject> Details;

	bool IsSet() const { return !Code.IsEmpty(); }

	static FAnimMcpError Make(const TCHAR* InCode, const FString& InMessage, TSharedPtr<FJsonObject> InDetails = nullptr)
	{
		FAnimMcpError E;
		E.Code = InCode;
		E.Message = InMessage;
		E.Details = InDetails;
		return E;
	}

	/** 코드 → HTTP 상태. envelope 는 항상 JSON 이므로 상태 코드는 분류용 */
	int32 ToHttpStatus() const;

	TSharedRef<FJsonObject> ToJson() const;
};

/** 디스패처가 핸들러에 넘기는 요청 문맥 */
struct FAnimMcpRequest
{
	FName Tool;
	FString RequestId;
	/** 본문 최상위 객체 (request_id 포함). 핸들러는 여기서 파라미터를 읽는다 */
	TSharedRef<FJsonObject> Params;

	FAnimMcpRequest(FName InTool, const FString& InRequestId, TSharedRef<FJsonObject> InParams)
		: Tool(InTool), RequestId(InRequestId), Params(InParams) {}

	// 파라미터 읽기 헬퍼 — 누락/타입 불일치는 BAD_REQUEST 로 통일
	bool GetRequiredString(const TCHAR* Key, FString& Out, FAnimMcpError& OutError) const;
	FString GetOptionalString(const TCHAR* Key, const FString& Default = FString()) const;
	bool GetOptionalBool(const TCHAR* Key, bool Default) const;
	double GetOptionalNumber(const TCHAR* Key, double Default) const;
};

/** 핸들러 실행 문맥 — 진단 누적 */
struct FAnimMcpContext
{
	const FAnimMcpRequest& Request;
	TArray<TSharedPtr<FJsonValue>> Diagnostics;

	explicit FAnimMcpContext(const FAnimMcpRequest& InRequest) : Request(InRequest) {}

	void AddDiagnostic(const TCHAR* Level, const TCHAR* Code, const FString& Message, TSharedPtr<FJsonObject> Extra = nullptr);
};

/** Tool 핸들러 — 성공 시 result 객체 반환(null 허용), 실패 시 OutError 설정 */
using FAnimMcpHandler = TFunction<TSharedPtr<FJsonObject>(FAnimMcpContext& Context, FAnimMcpError& OutError)>;

/** JSON 직렬화 헬퍼 */
namespace AnimMcpJson
{
	FString ToString(const TSharedRef<FJsonObject>& Object, bool bPretty = false);
	bool Parse(const FString& Text, TSharedPtr<FJsonObject>& OutObject, FString& OutParseError);
	TSharedRef<FJsonObject> MakeObject();
	TSharedPtr<FJsonValue> StringOrNull(const FString& Value);
	TSharedPtr<FJsonValue> ObjectPathOrNull(const UObject* Object);
}
