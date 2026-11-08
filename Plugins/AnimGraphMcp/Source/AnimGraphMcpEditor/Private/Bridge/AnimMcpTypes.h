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
	// Phase 6-2 애셋 수명
	inline const TCHAR* const AssetProtected     = TEXT("ASSET_PROTECTED");   // 403 — [AnimGraphMcp] ProtectedAssets/ProtectedPaths
	inline const TCHAR* const AssetReferenced    = TEXT("ASSET_REFERENCED");  // 409 — 다른 애셋이 참조 중 (force 없이는 삭제 거부)
	inline const TCHAR* const DirtyPackages      = TEXT("DIRTY_PACKAGES");    // 409 — 저장 안 된 패키지가 있어 quit 거부
	// AI 애니 생성 Phase 1 (Docs/AIAnimation/ArchitectureAudit.md §10)
	inline const TCHAR* const OutputPathNotAllowed   = TEXT("OUTPUT_PATH_NOT_ALLOWED");   // 403 — [AnimGraphMcp] GenerationOutputPaths 밖
	inline const TCHAR* const ImportSourceNotAllowed = TEXT("IMPORT_SOURCE_NOT_ALLOWED"); // 403 — [AnimGraphMcp] ImportSourceRoots 밖 파일
	inline const TCHAR* const UnexpectedDirty        = TEXT("UNEXPECTED_DIRTY");          // 409 — 허용 목록 밖 패키지가 새로 더티가 됨 (저장 안 함)
	inline const TCHAR* const ImportFailed           = TEXT("IMPORT_FAILED");
	inline const TCHAR* const IKRigAutoFailed        = TEXT("IKRIG_AUTO_FAILED");         // 자동 캐릭터라이즈 실패 — details.bones[] 로 수동 체인 정의
	inline const TCHAR* const RetargetFailed         = TEXT("RETARGET_FAILED");
	inline const TCHAR* const ValidationFailed       = TEXT("VALIDATION_FAILED");
	// AI 애니 생성 Phase 7 — promote_animation 의 엔진 rename 실패(details.reason CDO_REFERENCED · REGISTRY_LOADING · ENGINE · REDIRECTOR_LEFT …)
	inline const TCHAR* const PromoteFailed          = TEXT("PROMOTE_FAILED");
	// AI 애니 생성 Phase 8-2 — capture_animation 의 렌더 · 읽기 · 쓰기 실패(details.reason NO_SCENE · RENDER_TARGET · READBACK · WRITE_FAILED · IMAGE_UNREADABLE)
	inline const TCHAR* const CaptureFailed          = TEXT("CAPTURE_FAILED");
	// StateTree 자동화 (Docs/StateTree/DevelopmentGuide.md §4 · §5)
	inline const TCHAR* const AssetDirty             = TEXT("ASSET_DIRTY");          // 409 — 저장 안 된 변경이 있어 적용 거부 (한 번도 저장 안 한 애셋 포함)
	inline const TCHAR* const PieActive              = TEXT("PIE_ACTIVE");           // 409
	inline const TCHAR* const TransactionActive      = TEXT("TRANSACTION_ACTIVE");   // 409 — 사용자 트랜잭션(드래그 등)이 열려 있어 복구할 수 없다
	inline const TCHAR* const StateNotFound          = TEXT("STATE_NOT_FOUND");
	inline const TCHAR* const TypeNotFound           = TEXT("TYPE_NOT_FOUND");       // 노드 · 스키마 · 함수 타입 경로를 찾지 못함
	inline const TCHAR* const TypeNotAllowed         = TEXT("TYPE_NOT_ALLOWED");     // 스키마가 막았거나 기대 기반 타입이 아님
	inline const TCHAR* const AmbiguousName          = TEXT("AMBIGUOUS_NAME");       // details.candidates[] 의 GUID 로 지정
	inline const TCHAR* const NodeReferenced         = TEXT("NODE_REFERENCED");      // 409 — 삭제 대상을 전환 · 바인딩이 참조 중
	inline const TCHAR* const BindingOutOfScope      = TEXT("BINDING_OUT_OF_SCOPE"); // 소스가 GetBindableStructs 에 없음
	inline const TCHAR* const BadSourcePath          = TEXT("BAD_SOURCE_PATH");
	inline const TCHAR* const BadTargetPath          = TEXT("BAD_TARGET_PATH");
	inline const TCHAR* const IncompatibleTypes      = TEXT("INCOMPATIBLE_TYPES");
	inline const TCHAR* const NotBindable            = TEXT("NOT_BINDABLE");         // 엔진 바인딩 메뉴에 없는 프로퍼티 (D-6)
	inline const TCHAR* const CompileFixups          = TEXT("COMPILE_FIXUPS");       // 컴파일은 성공했지만 엔진이 바인딩 · 노드를 조용히 지움
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
