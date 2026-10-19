#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UAnimBlueprint;
struct FAnimMcpContext;
struct FAnimMcpError;

/** 컴파일·저장 — FCompilerResultsLog 의 토큰 메시지를 노드 Guid 로 매핑해 JSON 으로 */
namespace AnimMcpCompiler
{
	/** result: ok, num_errors, num_warnings, status, messages[{level, text, node_guid, graph_guid}] */
	TSharedRef<FJsonObject> Compile(UAnimBlueprint* Blueprint, FAnimMcpContext& Context);

	/** UEditorAssetSubsystem::SaveLoadedAsset(…, bOnlyIfIsDirty=false) — 더티 여부와 무관하게 강제 저장 */
	bool Save(UAnimBlueprint* Blueprint, FAnimMcpError& OutError);
}
