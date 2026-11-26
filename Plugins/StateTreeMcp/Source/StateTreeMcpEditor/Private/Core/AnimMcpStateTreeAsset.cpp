#include "AnimMcpStateTreeAsset.h"

#include "AnimMcpLog.h"
#include "AssetToolsModule.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetProtection.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/EditorMcpSettings.h"
#include "Editor.h"
#include "Editor/Transactor.h"
#include "IAssetTools.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/PackageName.h"
#include "Modules/ModuleManager.h"
#include "PackageTools.h"
#include "PropertyBindingBinding.h"
#include "StateTree.h"
#include "StateTreeCompilerLog.h"
#include "StateTreeEditingSubsystem.h"
#include "StateTreeEditorData.h"
#include "StateTreeEditorPropertyBindings.h"
#include "StateTreeFactory.h"
#include "StateTreeSchema.h"
#include "StateTreeState.h"
#include "StateTreeViewModel.h"
#include "Subsystems/AssetEditorSubsystem.h"
#include "Subsystems/EditorAssetSubsystem.h"
#include "UObject/Package.h"
#include "UObject/UnrealType.h"

namespace AnimMcpStateTreeAsset
{
	namespace
	{
		/** 2026-11-14 플러그인 분리 — StateTreeEditPaths 는 [EditorMcp] 와 옛 [AnimGraphMcp] 를 둘 다 읽는다(Core/EditorMcpSettings) */
		const TCHAR* const EditPathsKey = TEXT("StateTreeEditPaths");

		/** 프로퍼티가 protected 이고 FClassProperty::MetaClass 도 private 이라 기대 기반 클래스는 이 표로 고른다(§2-2) */
		struct FSchemaClassProperty
		{
			const TCHAR* Name;
			const TCHAR* BaseClassPath;
		};
		const FSchemaClassProperty SchemaClassProperties[] =
		{
			{ TEXT("ContextActorClass"), TEXT("/Script/Engine.Actor") },
			{ TEXT("AIControllerClass"), TEXT("/Script/AIModule.AIController") },
		};

		/** 파생 구조체로 protected Messages 를 읽는다(§2-5) */
		struct FCompileLogReader : public FStateTreeCompilerLog
		{
			const TArray<FStateTreeCompilerLogMessage>& GetMessages() const { return Messages; }
		};

		FString SeverityName(const int32 Severity)
		{
			switch (Severity)
			{
			case EMessageSeverity::Error: return TEXT("error");
			case EMessageSeverity::PerformanceWarning:
			case EMessageSeverity::Warning: return TEXT("warning");
			default: return TEXT("info");
			}
		}

		TArray<TSharedPtr<FJsonValue>> MessagesToJson(const FCompileLogReader& Log)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			for (const FStateTreeCompilerLogMessage& Message : Log.GetMessages())
			{
				TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
				Obj->SetStringField(TEXT("severity"), SeverityName(Message.Severity));
				Obj->SetStringField(TEXT("state_id"), Message.State ? Message.State->ID.ToString() : FString());
				Obj->SetStringField(TEXT("state_path"), Message.State ? Message.State->GetPath() : FString());
				Obj->SetStringField(TEXT("item_id"), Message.Item.ID.ToString());
				Obj->SetStringField(TEXT("item_name"), Message.Item.Name.ToString());
				Obj->SetStringField(TEXT("message"), Message.Message);
				Out.Add(MakeShared<FJsonValueObject>(Obj));
			}
			return Out;
		}

		/** 컴파일이 조용히 지운 것을 찾기 위한 지문 */
		struct FSnapshot
		{
			/** "대상 구조체:경로" → "소스 구조체:경로" */
			TMap<FString, FString> Bindings;
			/** 노드 ID → 타입 경로 */
			TMap<FGuid, FString> Nodes;
		};

		void AddNodes(const TArray<FStateTreeEditorNode>& Nodes, FSnapshot& Out)
		{
			for (const FStateTreeEditorNode& Node : Nodes)
			{
				Out.Nodes.Add(Node.ID, GetPathNameSafe(Node.Node.GetScriptStruct()));
			}
		}

		FString PathKey(const FPropertyBindingPath& Path)
		{
			return Path.GetStructID().ToString() + TEXT(":") + Path.ToString();
		}

		FSnapshot TakeSnapshot(const UStateTreeEditorData& Data)
		{
			FSnapshot Out;
			AddNodes(Data.Evaluators, Out);
			AddNodes(Data.GlobalTasks, Out);
			Data.VisitHierarchy([&Out](UStateTreeState& State, UStateTreeState* /*Parent*/)
			{
				AddNodes(State.EnterConditions, Out);
				AddNodes(State.Tasks, Out);
				AddNodes(State.Considerations, Out);
				for (const FStateTreeTransition& Transition : State.Transitions)
				{
					AddNodes(Transition.Conditions, Out);
				}
				return EStateTreeVisitor::Continue;
			});
			Data.GetPropertyEditorBindings()->ForEachBinding([&Out](const FPropertyBindingBinding& Binding)
			{
				Out.Bindings.Add(PathKey(Binding.GetTargetPath()), PathKey(Binding.GetSourcePath()));
			});
			return Out;
		}

		TArray<TSharedPtr<FJsonValue>> DiffSnapshots(const FSnapshot& Before, const FSnapshot& After)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			for (const TPair<FString, FString>& Pair : Before.Bindings)
			{
				if (!After.Bindings.Contains(Pair.Key))
				{
					TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
					Obj->SetStringField(TEXT("kind"), TEXT("binding_removed"));
					Obj->SetStringField(TEXT("target"), Pair.Key);
					Obj->SetStringField(TEXT("source"), Pair.Value);
					Out.Add(MakeShared<FJsonValueObject>(Obj));
				}
			}
			for (const TPair<FGuid, FString>& Pair : Before.Nodes)
			{
				if (!After.Nodes.Contains(Pair.Key))
				{
					TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
					Obj->SetStringField(TEXT("kind"), TEXT("node_removed"));
					Obj->SetStringField(TEXT("id"), Pair.Key.ToString());
					Obj->SetStringField(TEXT("type"), Pair.Value);
					Out.Add(MakeShared<FJsonValueObject>(Obj));
				}
			}
			return Out;
		}

		UClass* FindClassByPath(const FString& Path)
		{
			// 짧은 이름은 찾지 않는다 — 전체 경로만 받는다
			if (!Path.StartsWith(TEXT("/")) || !Path.Contains(TEXT(".")))
			{
				return nullptr;
			}
			UClass* Class = FindObject<UClass>(nullptr, *Path);
			return Class ? Class : LoadObject<UClass>(nullptr, *Path, nullptr, LOAD_NoWarn | LOAD_Quiet);
		}

		struct FSchemaValue
		{
			FClassProperty* Property = nullptr;
			UClass* Value = nullptr;
		};

		bool ResolveSchemaProperties(const UClass& SchemaClass, const TSharedPtr<FJsonObject>& SchemaProperties, TArray<FSchemaValue>& Out, FAnimMcpError& OutError)
		{
			if (!SchemaProperties.IsValid())
			{
				return true;
			}
			for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : SchemaProperties->Values)
			{
				const FSchemaClassProperty* Rule = nullptr;
				for (const FSchemaClassProperty& Candidate : SchemaClassProperties)
				{
					if (Pair.Key == Candidate.Name)
					{
						Rule = &Candidate;
						break;
					}
				}
				FClassProperty* Property = Rule ? CastField<FClassProperty>(SchemaClass.FindPropertyByName(FName(*Pair.Key))) : nullptr;
				if (!Property)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, FString::Printf(TEXT("schema_properties.%s is not supported on %s (allowed: ContextActorClass, AIControllerClass)"), *Pair.Key, *SchemaClass.GetName()));
					return false;
				}
				FString ClassPath;
				if (!Pair.Value.IsValid() || !Pair.Value->TryGetString(ClassPath))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("schema_properties.%s expects a class path string"), *Pair.Key));
					return false;
				}
				UClass* Value = FindClassByPath(ClassPath);
				if (!Value)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotFound, FString::Printf(TEXT("schema_properties.%s: class '%s' not found (use a full path such as /Script/AstralBreak.AstralCombatCharacter)"), *Pair.Key, *ClassPath));
					return false;
				}
				const UClass* RequiredBase = FindClassByPath(Rule->BaseClassPath);
				if (!RequiredBase || !Value->IsChildOf(RequiredBase))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotAllowed, FString::Printf(TEXT("schema_properties.%s: '%s' is not a %s"), *Pair.Key, *ClassPath, Rule->BaseClassPath));
					return false;
				}
				FSchemaValue Entry;
				Entry.Property = Property;
				Entry.Value = Value;
				Out.Add(Entry);
			}
			return true;
		}

		/** §2-2 — 값 쓰기 뒤 PostEditChangeChainProperty 를 불러야 ContextDataDescs 가 갱신된다 */
		void WriteSchemaProperty(UStateTreeSchema& Schema, const FSchemaValue& Entry)
		{
			Schema.Modify();
			Entry.Property->SetObjectPropertyValue_InContainer(&Schema, Entry.Value);
			FEditPropertyChain Chain;
			Chain.AddHead(Entry.Property);
			Chain.SetActiveMemberPropertyNode(Entry.Property);
			FPropertyChangedEvent Event(Entry.Property, EPropertyChangeType::ValueSet);
			FPropertyChangedChainEvent ChainEvent(Chain, Event);
			UObject& AsObject = Schema;
			AsObject.PostEditChangeChainProperty(ChainEvent);
		}

		bool ValidateNewAssetPath(const FString& Package, FAnimMcpError& OutError)
		{
			FText Reason;
			if (!FPackageName::IsValidLongPackageName(Package, /*bIncludeReadOnlyRoots*/ false, &Reason))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Invalid asset_path '%s': %s"), *Package, *Reason.ToString()));
				return false;
			}
			const FString Name = FPackageName::GetShortName(Package);
			if (!FName::IsValidXName(Name, INVALID_OBJECTNAME_CHARACTERS INVALID_LONGPACKAGE_CHARACTERS, &Reason))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Invalid asset name '%s': %s"), *Name, *Reason.ToString()));
				return false;
			}
			return true;
		}
	}

	const TArray<FString>& GetEditPaths()
	{
		static const TArray<FString> Paths = []()
		{
			const TArray<FString> Raw = EditorMcpSettings::GetArray(EditPathsKey);
			TArray<FString> Out;
			for (const FString& Entry : Raw)
			{
				FString Path = Entry.TrimStartAndEnd();
				if (!Path.StartsWith(TEXT("/")))
				{
					Path = TEXT("/") + Path;
				}
				if (!Path.EndsWith(TEXT("/")))
				{
					Path += TEXT("/");
				}
				if (Path.Len() > 1)
				{
					Out.AddUnique(Path);
				}
			}
			UE_LOG(LogAnimGraphMcp, Log, TEXT("StateTree edit paths: %d ([%s] + [%s] in %s)"), Out.Num(), EditorMcpSettings::Section, EditorMcpSettings::LegacySection, *GEngineIni);
			return Out;
		}();
		return Paths;
	}

	bool EnsureWritable(const FString& AssetPath, FAnimMcpError& OutError)
	{
		const FString Package = AnimMcpAssetResolver::ToPackagePath(AssetPath);
		const bool bAllowed = !Package.Contains(TEXT("..")) && GetEditPaths().ContainsByPredicate([&Package](const FString& Prefix)
		{
			return Package.StartsWith(Prefix, ESearchCase::IgnoreCase);
		});
		if (!bAllowed)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("asset_path"), Package);
			TArray<TSharedPtr<FJsonValue>> Allowed;
			for (const FString& Prefix : GetEditPaths())
			{
				Allowed.Add(MakeShared<FJsonValueString>(Prefix));
			}
			Details->SetArrayField(TEXT("allowed"), Allowed);
			Details->SetStringField(TEXT("config"), EditorMcpSettings::Describe(EditPathsKey));
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::OutputPathNotAllowed, FString::Printf(TEXT("'%s' is outside StateTreeEditPaths ([%s] or legacy [%s])"), *Package, EditorMcpSettings::Section, EditorMcpSettings::LegacySection), Details);
			return false;
		}
		return AnimMcpAssetProtection::EnsureNotProtected(AssetPath, TEXT("edit"), OutError);
	}

	bool EnsureNotInPie(FAnimMcpError& OutError)
	{
		if (GEditor && (GEditor->PlayWorld != nullptr || GEditor->IsPlaySessionInProgress()))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PieActive, TEXT("PIE is active — end the play session before changing a StateTree"));
			return false;
		}
		return true;
	}

	bool EnsureNoActiveTransaction(FAnimMcpError& OutError)
	{
		if (GEditor && GEditor->Trans && GEditor->Trans->IsActive())
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TransactionActive, TEXT("An editor transaction is open (a drag or another tool?) — retry when it ends"));
			return false;
		}
		return true;
	}

	UStateTree* Load(const FString& AssetPath, FAnimMcpError& OutError)
	{
		return Cast<UStateTree>(AnimMcpAssetResolver::LoadAssetOfClass(AssetPath, UStateTree::StaticClass(), OutError));
	}

	UStateTreeEditorData* GetEditorData(const UStateTree* Tree)
	{
		return Tree ? Cast<UStateTreeEditorData>(Tree->EditorData) : nullptr;
	}

	FString GetRevision(const UStateTree& Tree)
	{
		return FString::Printf(TEXT("%08x"), UStateTreeEditingSubsystem::CalculateStateTreeHash(&Tree));
	}

	FString GetCompileState(const UStateTree& Tree)
	{
		if (Tree.LastCompiledEditorDataHash == 0)
		{
			return TEXT("failed");
		}
		if (Tree.LastCompiledEditorDataHash != UStateTreeEditingSubsystem::CalculateStateTreeHash(&Tree))
		{
			return TEXT("stale");
		}
		return Tree.IsReadyToRun() ? TEXT("up_to_date") : TEXT("failed");
	}

	UStateTree* Create(const FString& AssetPath, const FString& SchemaClassPath, const TSharedPtr<FJsonObject>& SchemaProperties, const bool bSave, FAnimMcpError& OutError)
	{
		const FString Package = AnimMcpAssetResolver::ToPackagePath(AssetPath);
		const FString ObjectPath = AnimMcpAssetResolver::NormalizeObjectPath(AssetPath);
		if (!ValidateNewAssetPath(Package, OutError) || !EnsureWritable(AssetPath, OutError))
		{
			return nullptr;
		}
		if (AnimMcpAssetResolver::AssetExists(ObjectPath) || FindObject<UObject>(nullptr, *ObjectPath))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetExists, FString::Printf(TEXT("'%s' already exists — create_state_tree never overwrites"), *Package));
			return nullptr;
		}

		UClass* SchemaClass = FindClassByPath(SchemaClassPath);
		if (!SchemaClass)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotFound, FString::Printf(TEXT("schema_class '%s' not found (use a full path such as %s)"), *SchemaClassPath, DefaultSchemaClass));
			return nullptr;
		}
		if (!SchemaClass->IsChildOf(UStateTreeSchema::StaticClass()) || SchemaClass->HasAnyClassFlags(CLASS_Abstract))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::TypeNotAllowed, FString::Printf(TEXT("schema_class '%s' is not a concrete UStateTreeSchema"), *SchemaClassPath));
			return nullptr;
		}
		TArray<FSchemaValue> SchemaValues;
		if (!ResolveSchemaProperties(*SchemaClass, SchemaProperties, SchemaValues, OutError))
		{
			return nullptr;
		}

		UStateTreeFactory* Factory = NewObject<UStateTreeFactory>();
		Factory->SetSchemaClass(TObjectPtr<UClass>(SchemaClass));
		IAssetTools& AssetTools = FModuleManager::LoadModuleChecked<FAssetToolsModule>(TEXT("AssetTools")).Get();
		UStateTree* Tree = Cast<UStateTree>(AssetTools.CreateAsset(FPackageName::GetShortName(Package), FPackageName::GetLongPackagePath(Package), UStateTree::StaticClass(), Factory));
		UStateTreeEditorData* Data = GetEditorData(Tree);
		if (!Data || !Data->Schema)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("IAssetTools::CreateAsset failed for '%s'"), *Package));
			return nullptr;
		}

		for (const FSchemaValue& Entry : SchemaValues)
		{
			WriteSchemaProperty(*Data->Schema, Entry);
		}
		// 스키마 값은 재컴파일해야 컴파일 산출물에 들어간다(§2-2)
		if (SchemaValues.Num() > 0)
		{
			FCompileResult Compiled = Compile(*Tree);
			if (!Compiled.bOk)
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetArrayField(TEXT("messages"), Compiled.Messages);
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::CompileFailed, FString::Printf(TEXT("'%s' was created but does not compile with the given schema_properties — not saved"), *Package), Details);
				return nullptr;
			}
		}
		if (bSave && !Save(*Tree, OutError))
		{
			return nullptr;
		}
		return Tree;
	}

	TSharedRef<FJsonObject> FCompileResult::ToJson() const
	{
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetBoolField(TEXT("ran"), true);
		Obj->SetBoolField(TEXT("ok"), bOk);
		Obj->SetArrayField(TEXT("messages"), Messages);
		Obj->SetArrayField(TEXT("fixups"), Fixups);
		return Obj;
	}

	FCompileResult Compile(UStateTree& Tree)
	{
		FCompileResult Result;
		const FSnapshot Before = TakeSnapshot(*GetEditorData(&Tree));
		FCompileLogReader Log;
		Result.bOk = UStateTreeEditingSubsystem::CompileStateTree(&Tree, Log);
		Result.Messages = MessagesToJson(Log);
		// 실패 경로에서도 EditorData 는 살아 있다 — ResetCompiled 는 컴파일 결과만 지운다
		Result.Fixups = DiffSnapshots(Before, TakeSnapshot(*GetEditorData(&Tree)));
		return Result;
	}

	FBaseline CaptureBaseline(const UStateTree& Tree)
	{
		FBaseline Baseline;
		Baseline.ObjectPath = Tree.GetPathName();
		Baseline.Hash = UStateTreeEditingSubsystem::CalculateStateTreeHash(&Tree);
		Baseline.CompiledHash = Tree.LastCompiledEditorDataHash;
		Baseline.bReady = Tree.IsReadyToRun();
		Baseline.bDirty = Tree.GetPackage()->IsDirty();
		Baseline.EffectiveQueue = GEditor->Trans->GetQueueLength() - GEditor->Trans->GetUndoCount();
		return Baseline;
	}

	TSharedRef<FJsonObject> FRollback::ToJson() const
	{
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetBoolField(TEXT("verified"), bVerified);
		Obj->SetStringField(TEXT("method"), Method);
		Obj->SetBoolField(TEXT("undo_history_cleared"), bUndoHistoryCleared);
		Obj->SetBoolField(TEXT("editor_reopened"), bEditorReopened);
		Obj->SetStringField(TEXT("revision"), Revision);
		return Obj;
	}

	FRollback ReloadFromDisk(const FString& ObjectPath, const uint32 ExpectedHash, const bool bCheckHash)
	{
		FRollback Result;
		Result.Method = TEXT("reload");

		UStateTree* Tree = FindObject<UStateTree>(nullptr, *ObjectPath);
		UAssetEditorSubsystem* AssetEditors = GEditor->GetEditorSubsystem<UAssetEditorSubsystem>();
		Result.bEditorReopened = Tree && AssetEditors && AssetEditors->FindEditorsForAsset(Tree).Num() > 0;

		bool bReloaded = false;
		if (Tree)
		{
			const TArray<UPackage*> Packages = { Tree->GetPackage() };
			FText ReloadError;
			bReloaded = UPackageTools::ReloadPackages(Packages, ReloadError, UPackageTools::EReloadPackagesInteractionMode::AssumePositive);
			if (!bReloaded)
			{
				UE_LOG(LogAnimGraphMcp, Error, TEXT("ReloadPackages failed for %s: %s"), *ObjectPath, *ReloadError.ToString());
			}
			Result.bUndoHistoryCleared = true;
		}

		// 옛 포인터는 무효다 — 경로로 다시 찾는다
		Tree = nullptr;
		UStateTree* Reloaded = LoadObject<UStateTree>(nullptr, *ObjectPath);
		if (Reloaded)
		{
			Result.Revision = GetRevision(*Reloaded);
			Result.bVerified = bReloaded && (!bCheckHash || UStateTreeEditingSubsystem::CalculateStateTreeHash(Reloaded) == ExpectedHash);
		}
		return Result;
	}

	FRollback Recover(const FBaseline& Baseline)
	{
		UStateTree* Tree = FindObject<UStateTree>(nullptr, *Baseline.ObjectPath);
		if (!Tree)
		{
			FRollback Lost;
			Lost.Method = TEXT("none");
			return Lost;
		}

		const auto Unchanged = [&Baseline](const UStateTree& Candidate)
		{
			return UStateTreeEditingSubsystem::CalculateStateTreeHash(&Candidate) == Baseline.Hash
				&& Candidate.IsReadyToRun() == Baseline.bReady;
		};

		// 1단 — 우리 트랜잭션이 맨 위에 있을 때만. 확인 없이 Undo 하면 사용자의 앞선 작업이 되돌아간다(E5e).
		// 리비전보다 먼저 본다: 컴파일이 불량 바인딩을 지우면 리비전은 적용 전과 같아져도 트랜잭션은 큐에 남는다
		const int32 EffectiveQueue = GEditor->Trans->GetQueueLength() - GEditor->Trans->GetUndoCount();
		if (EffectiveQueue == Baseline.EffectiveQueue + 1)
		{
			if (GEditor->UndoTransaction(/*bCanRedo*/ false))
			{
				Compile(*Tree);
				if (Unchanged(*Tree))
				{
					FRollback Result;
					Result.bVerified = true;
					Result.Method = TEXT("undo");
					Result.Revision = GetRevision(*Tree);
					return Result;
				}
				UE_LOG(LogAnimGraphMcp, Warning, TEXT("Undo did not restore %s (revision %s) — falling back to reload"), *Baseline.ObjectPath, *GetRevision(*Tree));
			}
		}
		// 2단 — 트랜잭션이 없고 데이터도 그대로다. 실제 변경이 없으면 엔진이 트랜잭션을 버린다. 재로드는 Undo 기록만 잃는다.
		// Modify 는 값이 그대로여도 패키지를 더티로 만들므로 적용 전 표시로 돌린다
		else if (Unchanged(*Tree) && Tree->LastCompiledEditorDataHash == Baseline.CompiledHash)
		{
			if (!Baseline.bDirty)
			{
				Tree->GetPackage()->SetDirtyFlag(false);
			}
			FRollback Result;
			Result.bVerified = true;
			Result.Method = TEXT("none");
			Result.Revision = GetRevision(*Tree);
			return Result;
		}

		// 3단 — 그 밖의 모든 경우
		Tree = nullptr;
		return ReloadFromDisk(Baseline.ObjectPath, Baseline.Hash, /*bCheckHash*/ true);
	}

	bool Save(UStateTree& Tree, FAnimMcpError& OutError)
	{
		UEditorAssetSubsystem* Assets = GEditor->GetEditorSubsystem<UEditorAssetSubsystem>();
		if (!Assets || !Assets->SaveLoadedAsset(&Tree, /*bOnlyIfIsDirty*/ false))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::SaveFailed, FString::Printf(TEXT("Saving '%s' failed"), *Tree.GetPathName()));
			return false;
		}
		return true;
	}

	void NotifyEditors(UStateTree& Tree)
	{
		UStateTreeEditingSubsystem* Subsystem = GEditor->GetEditorSubsystem<UStateTreeEditingSubsystem>();
		if (TSharedPtr<FStateTreeViewModel> ViewModel = Subsystem ? Subsystem->FindViewModel(&Tree) : nullptr)
		{
			ViewModel->NotifyAssetChangedExternally();
		}
	}
}
