#include "AnimMcpCompiler.h"

#include "AnimMcpLog.h"
#include "Animation/AnimBlueprint.h"
#include "Bridge/AnimMcpTypes.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "Editor.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Logging/TokenizedMessage.h"
#include "Misc/UObjectToken.h"
#include "Subsystems/EditorAssetSubsystem.h"

namespace AnimMcpCompiler
{
	namespace
	{
		const TCHAR* SeverityToString(EMessageSeverity::Type Severity)
		{
			switch (Severity)
			{
			case EMessageSeverity::Error: return TEXT("error");
			case EMessageSeverity::PerformanceWarning:
			case EMessageSeverity::Warning: return TEXT("warning");
			default: return TEXT("info");
			}
		}
	}

	TSharedRef<FJsonObject> Compile(UAnimBlueprint* Blueprint, FAnimMcpContext& Context)
	{
		check(IsInGameThread() && Blueprint);

		FCompilerResultsLog Log;
		Log.SetSourcePath(Blueprint->GetPathName());
		FKismetEditorUtilities::CompileBlueprint(Blueprint, EBlueprintCompileOptions::None, &Log);

		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetBoolField(TEXT("ok"), Log.NumErrors == 0);
		Result->SetNumberField(TEXT("num_errors"), Log.NumErrors);
		Result->SetNumberField(TEXT("num_warnings"), Log.NumWarnings);
		Result->SetStringField(TEXT("status"), StaticEnum<EBlueprintStatus>()->GetNameStringByValue(static_cast<int64>(Blueprint->Status)));

		TArray<TSharedPtr<FJsonValue>> Messages;
		for (const TSharedRef<FTokenizedMessage>& Message : Log.Messages)
		{
			TSharedRef<FJsonObject> M = AnimMcpJson::MakeObject();
			M->SetStringField(TEXT("level"), SeverityToString(Message->GetSeverity()));
			M->SetStringField(TEXT("text"), Message->ToText().ToString());

			// 메시지 토큰 중 노드 참조를 Guid 로 — 첫 노드만 (메시지 하나가 보통 노드 하나를 가리킨다)
			FString NodeGuid, GraphGuid, ObjectPath;
			for (const TSharedRef<IMessageToken>& Token : Message->GetMessageTokens())
			{
				if (Token->GetType() != EMessageToken::Object)
				{
					continue;
				}
				const TSharedRef<FUObjectToken> ObjectToken = StaticCastSharedRef<FUObjectToken>(Token);
				UObject* Object = ObjectToken->GetObject().Get();
				if (!Object)
				{
					continue;
				}
				if (UEdGraphNode* Node = Cast<UEdGraphNode>(Object))
				{
					NodeGuid = Node->NodeGuid.ToString();
					if (UEdGraph* Graph = Node->GetGraph())
					{
						GraphGuid = Graph->GraphGuid.ToString();
					}
					break;
				}
				if (ObjectPath.IsEmpty())
				{
					ObjectPath = Object->GetPathName();
				}
			}
			M->SetField(TEXT("node_guid"), AnimMcpJson::StringOrNull(NodeGuid));
			M->SetField(TEXT("graph_guid"), AnimMcpJson::StringOrNull(GraphGuid));
			M->SetField(TEXT("object"), AnimMcpJson::StringOrNull(ObjectPath));
			Messages.Add(MakeShared<FJsonValueObject>(M));
		}
		Result->SetArrayField(TEXT("messages"), Messages);

		UE_LOG(LogAnimGraphMcp, Log, TEXT("Compiled %s: %d errors, %d warnings"), *Blueprint->GetPathName(), Log.NumErrors, Log.NumWarnings);
		return Result;
	}

	bool Save(UAnimBlueprint* Blueprint, FAnimMcpError& OutError)
	{
		check(IsInGameThread() && Blueprint);
		UEditorAssetSubsystem* AssetSubsystem = GEditor ? GEditor->GetEditorSubsystem<UEditorAssetSubsystem>() : nullptr;
		if (!AssetSubsystem)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("EditorAssetSubsystem unavailable"));
			return false;
		}
		if (!AssetSubsystem->SaveLoadedAsset(Blueprint, /*bOnlyIfIsDirty*/ false))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::SaveFailed, FString::Printf(TEXT("SaveLoadedAsset failed for %s (read-only file? source control?)"), *Blueprint->GetPathName()));
			return false;
		}
		UE_LOG(LogAnimGraphMcp, Log, TEXT("Saved %s"), *Blueprint->GetPathName());
		return true;
	}
}
