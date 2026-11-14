#include "EditorMcpCoreModule.h"

#include "AnimMcpLog.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpHttpBridge.h"
#include "Core/EditorMcpSettings.h"
#include "HAL/IConsoleManager.h"
#include "Misc/CommandLine.h"
#include "Misc/CoreDelegates.h"
#include "Tools/EditorMcpTools.h"

DEFINE_LOG_CATEGORY(LogAnimGraphMcp);

/**
 * 에디터 전용 코어 모듈 (2026-11-14 플러그인 분리 — 분리 전 AnimGraphMcp 모듈이 하던 브리지 수명 관리).
 * 설정은 DefaultEngine.ini 의 [EditorMcp] (없으면 옛 [AnimGraphMcp]):
 *   Port=18765   bRequireToken=True   bAutoStart=True   +ProtectedAssets=…   +ProtectedPaths=…
 * 커맨드라인 -AnimGraphMcpPort=18766 (인스턴스별 포트 — 이름 그대로). 토큰 파일 Saved/AnimGraphMcp/token (위치 그대로).
 * 콘솔: EditorMcp.Start / Stop / Status, 옛 이름 AnimGraphMcp.Start / Stop / Status 도 같은 동작.
 */
class FEditorMcpCoreModule : public IEditorMcpCoreModule
{
public:
	static constexpr const TCHAR* CoreFeature = TEXT("EditorMcpCore");

	virtual void StartupModule() override
	{
		if (!GIsEditor || IsRunningCommandlet())
		{
			return;
		}

		LoadConfig();
		RegisterConsoleCommands();

		if (bAutoStart)
		{
			// 소켓·에디터 서브시스템이 준비된 뒤에 리스너를 연다. 기능 플러그인(Default 단계)은 그 전에 등록을 마친다
			if (GEngine && GEngine->IsInitialized())
			{
				StartBridge();
			}
			else
			{
				PostEngineInitHandle = FCoreDelegates::OnPostEngineInit.AddRaw(this, &FEditorMcpCoreModule::StartBridge);
			}
		}
	}

	virtual void ShutdownModule() override
	{
		if (PostEngineInitHandle.IsValid())
		{
			FCoreDelegates::OnPostEngineInit.Remove(PostEngineInitHandle);
			PostEngineInitHandle.Reset();
		}
		StopBridge();
		ConsoleCommands.Empty();
		Registrars.Empty();
		StatusSections.Empty();
	}

	// IEditorMcpCoreModule

	virtual void RegisterTools(FName Feature, FRegisterToolsFn Register) override
	{
		check(IsInGameThread());
		if (Feature.IsNone() || !Register)
		{
			return;
		}
		if (FRegistrar* Existing = Registrars.FindByPredicate([Feature](const FRegistrar& R) { return R.Feature == Feature; }))
		{
			Existing->Register = MoveTemp(Register);
		}
		else
		{
			Registrars.Add({ Feature, MoveTemp(Register) });
		}

		// 브리지가 이미 떠 있으면(늦게 로드된 기능 · 같은 기능 재등록) 그 자리에서 반영
		if (Dispatcher.IsValid())
		{
			Dispatcher->RemoveFeature(Feature);
			ApplyRegistrar(*Registrars.FindByPredicate([Feature](const FRegistrar& R) { return R.Feature == Feature; }));
			if (Bridge.IsValid())
			{
				Bridge->SyncRoutes();
			}
			UE_LOG(LogAnimGraphMcp, Log, TEXT("EditorMcp feature %s registered while running — %d tools"), *Feature.ToString(), Dispatcher->CountFeatureTools(Feature));
		}
	}

	virtual void UnregisterTools(FName Feature) override
	{
		check(IsInGameThread());
		Registrars.RemoveAll([Feature](const FRegistrar& R) { return R.Feature == Feature; });
		StatusSections.RemoveAll([Feature](const FStatusSection& S) { return S.Feature == Feature; });
		if (Dispatcher.IsValid())
		{
			const TArray<FName> Removed = Dispatcher->RemoveFeature(Feature);
			if (Bridge.IsValid())
			{
				Bridge->SyncRoutes();
			}
			if (Removed.Num() > 0)
			{
				UE_LOG(LogAnimGraphMcp, Log, TEXT("EditorMcp feature %s unregistered — %d tools removed"), *Feature.ToString(), Removed.Num());
			}
		}
	}

	virtual void RegisterStatusSection(FName Feature, FDescribeStatusFn Describe) override
	{
		check(IsInGameThread());
		if (Feature.IsNone() || !Describe)
		{
			return;
		}
		if (FStatusSection* Existing = StatusSections.FindByPredicate([Feature](const FStatusSection& S) { return S.Feature == Feature; }))
		{
			Existing->Describe = MoveTemp(Describe);
		}
		else
		{
			StatusSections.Add({ Feature, MoveTemp(Describe) });
		}
	}

	virtual TArray<FName> GetFeatures() const override
	{
		TArray<FName> Out;
		for (const FRegistrar& R : Registrars) { Out.Add(R.Feature); }
		return Out;
	}

	virtual bool IsBridgeRunning() const override
	{
		return Bridge.IsValid() && Bridge->IsRunning();
	}

private:
	struct FRegistrar
	{
		FName Feature;
		FRegisterToolsFn Register;
	};

	struct FStatusSection
	{
		FName Feature;
		FDescribeStatusFn Describe;
	};

	void LoadConfig()
	{
		Port = 18765;
		bRequireToken = true;
		bAutoStart = true;

		int32 ConfigPort = 0;
		if (EditorMcpSettings::GetInt(TEXT("Port"), ConfigPort) && ConfigPort > 0 && ConfigPort < 65536)
		{
			Port = static_cast<uint32>(ConfigPort);
		}
		EditorMcpSettings::GetBool(TEXT("bRequireToken"), bRequireToken);
		EditorMcpSettings::GetBool(TEXT("bAutoStart"), bAutoStart);

		// 커맨드라인 오버라이드 (여러 에디터 인스턴스를 띄울 때) — -AnimGraphMcpPort=18766 (이름은 분리 전 그대로)
		int32 CmdPort = 0;
		if (FParse::Value(FCommandLine::Get(), TEXT("AnimGraphMcpPort="), CmdPort) && CmdPort > 0 && CmdPort < 65536)
		{
			Port = static_cast<uint32>(CmdPort);
		}
	}

	void RegisterConsoleCommands()
	{
		// 새 이름 EditorMcp.* + 옛 이름 AnimGraphMcp.* (같은 동작)
		const TCHAR* const Prefixes[] = { TEXT("EditorMcp"), TEXT("AnimGraphMcp") };
		for (const TCHAR* Prefix : Prefixes)
		{
			ConsoleCommands.Add(MakeUnique<FAutoConsoleCommand>(*FString::Printf(TEXT("%s.Start"), Prefix), TEXT("Start the editor MCP HTTP bridge (EditorMcpCore)"),
				FConsoleCommandDelegate::CreateRaw(this, &FEditorMcpCoreModule::StartBridge)));
			ConsoleCommands.Add(MakeUnique<FAutoConsoleCommand>(*FString::Printf(TEXT("%s.Stop"), Prefix), TEXT("Stop the editor MCP HTTP bridge (EditorMcpCore)"),
				FConsoleCommandDelegate::CreateRaw(this, &FEditorMcpCoreModule::StopBridge)));
			ConsoleCommands.Add(MakeUnique<FAutoConsoleCommand>(*FString::Printf(TEXT("%s.Status"), Prefix), TEXT("Log the editor MCP HTTP bridge status (EditorMcpCore)"),
				FConsoleCommandDelegate::CreateRaw(this, &FEditorMcpCoreModule::LogStatus)));
		}
	}

	void ApplyRegistrar(const FRegistrar& Registrar)
	{
		Dispatcher->BeginFeature(Registrar.Feature);
		Registrar.Register(*Dispatcher);
		Dispatcher->EndFeature();
	}

	void DescribeFeatures(const TSharedRef<FJsonObject>& Result) const
	{
		for (const FStatusSection& Section : StatusSections)
		{
			Section.Describe(Result);
		}
		TArray<TSharedPtr<FJsonValue>> Features;
		auto AddFeature = [this, &Features](FName Feature)
		{
			TSharedRef<FJsonObject> F = AnimMcpJson::MakeObject();
			F->SetStringField(TEXT("name"), Feature.ToString());
			F->SetNumberField(TEXT("tools"), Dispatcher.IsValid() ? Dispatcher->CountFeatureTools(Feature) : 0);
			Features.Add(MakeShared<FJsonValueObject>(F));
		};
		AddFeature(CoreFeature);
		for (const FRegistrar& R : Registrars)
		{
			AddFeature(R.Feature);
		}
		Result->SetArrayField(TEXT("features"), Features);
	}

	void StartBridge()
	{
		if (Bridge.IsValid() && Bridge->IsRunning())
		{
			UE_LOG(LogAnimGraphMcp, Log, TEXT("Bridge already running on port %u"), Bridge->GetPort());
			return;
		}

		Dispatcher = MakeShared<FAnimMcpDispatcher>();
		Bridge = MakeShared<FAnimMcpHttpBridge>();

		// 코어 Tool — get_editor_status · quit_editor · run/poll_automation_tests
		Dispatcher->BeginFeature(CoreFeature);
		EditorMcpTools::RegisterStatusTools(*Dispatcher, Bridge, [this](const TSharedRef<FJsonObject>& Result) { DescribeFeatures(Result); });
		EditorMcpTools::RegisterEditorTools(*Dispatcher);
		EditorMcpTools::RegisterAutomationTools(*Dispatcher);
		Dispatcher->EndFeature();

		// 기능 플러그인 Tool — 등록 순
		for (const FRegistrar& Registrar : Registrars)
		{
			ApplyRegistrar(Registrar);
		}

		if (!Bridge->Start(Port, bRequireToken, Dispatcher.ToSharedRef()))
		{
			UE_LOG(LogAnimGraphMcp, Error, TEXT("EditorMcp bridge failed to start on port %u. Use EditorMcp.Start to retry or set [EditorMcp] Port in DefaultEngine.ini"), Port);
			Bridge.Reset();
			Dispatcher.Reset();
			return;
		}
		for (const FRegistrar& Registrar : Registrars)
		{
			UE_LOG(LogAnimGraphMcp, Log, TEXT("  feature %s: %d tools"), *Registrar.Feature.ToString(), Dispatcher->CountFeatureTools(Registrar.Feature));
		}
	}

	void StopBridge()
	{
		if (Bridge.IsValid())
		{
			Bridge->Stop();
			Bridge.Reset();
		}
		Dispatcher.Reset();
	}

	void LogStatus()
	{
		if (Bridge.IsValid() && Bridge->IsRunning())
		{
			TArray<FString> Names;
			for (const FRegistrar& R : Registrars) { Names.Add(R.Feature.ToString()); }
			UE_LOG(LogAnimGraphMcp, Display, TEXT("Running: http://127.0.0.1:%u/v1/<tool>, %d tools, token %s, features [%s]"), Bridge->GetPort(),
				Dispatcher.IsValid() ? Dispatcher->GetToolNames().Num() : 0, Bridge->IsTokenRequired() ? TEXT("required") : TEXT("not required"),
				*FString::Join(Names, TEXT(", ")));
		}
		else
		{
			UE_LOG(LogAnimGraphMcp, Display, TEXT("Stopped (configured port %u)"), Port);
		}
	}

private:
	TSharedPtr<FAnimMcpDispatcher> Dispatcher;
	TSharedPtr<FAnimMcpHttpBridge> Bridge;
	TArray<TUniquePtr<FAutoConsoleCommand>> ConsoleCommands;
	FDelegateHandle PostEngineInitHandle;
	TArray<FRegistrar> Registrars;
	TArray<FStatusSection> StatusSections;

	uint32 Port = 18765;
	bool bRequireToken = true;
	bool bAutoStart = true;
};

IMPLEMENT_MODULE(FEditorMcpCoreModule, EditorMcpCore)
