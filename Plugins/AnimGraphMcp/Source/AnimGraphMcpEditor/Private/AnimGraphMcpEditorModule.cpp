#include "AnimMcpLog.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpHttpBridge.h"
#include "HAL/IConsoleManager.h"
#include "Misc/CommandLine.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/CoreDelegates.h"
#include "Modules/ModuleManager.h"
#include "Tools/AnimMcpTools.h"

DEFINE_LOG_CATEGORY(LogAnimGraphMcp);

/**
 * 에디터 전용 모듈. 설정은 프로젝트 DefaultEngine.ini 의 [AnimGraphMcp] 섹션 (없으면 기본값):
 *   Port=18765
 *   bRequireToken=True
 *   bAutoStart=True
 *   +ProtectedAssets=/Game/...   +ProtectedPaths=/Game/.../   (Phase 6-2 삭제·덮어쓰기 보호, Core/AnimMcpAssetProtection)
 *   +GenerationOutputPaths=/Game/.../   +ImportSourceRoots=Saved/...   MaxRetargetAssetsPerCall=20   +PromotionPaths=/Game/.../   (AI 애니 생성, Core/AnimMcpGeneration)
 * 콘솔: AnimGraphMcp.Start / AnimGraphMcp.Stop / AnimGraphMcp.Status
 */
class FAnimGraphMcpEditorModule : public IModuleInterface
{
public:
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
			// 소켓·에디터 서브시스템이 준비된 뒤에 리스너를 연다
			if (GEngine && GEngine->IsInitialized())
			{
				StartBridge();
			}
			else
			{
				PostEngineInitHandle = FCoreDelegates::OnPostEngineInit.AddRaw(this, &FAnimGraphMcpEditorModule::StartBridge);
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
	}

private:
	void LoadConfig()
	{
		Port = 18765;
		bRequireToken = true;
		bAutoStart = true;

		int32 ConfigPort = 0;
		if (GConfig->GetInt(TEXT("AnimGraphMcp"), TEXT("Port"), ConfigPort, GEngineIni) && ConfigPort > 0 && ConfigPort < 65536)
		{
			Port = static_cast<uint32>(ConfigPort);
		}
		GConfig->GetBool(TEXT("AnimGraphMcp"), TEXT("bRequireToken"), bRequireToken, GEngineIni);
		GConfig->GetBool(TEXT("AnimGraphMcp"), TEXT("bAutoStart"), bAutoStart, GEngineIni);

		// 커맨드라인 오버라이드 (여러 에디터 인스턴스를 띄울 때) — -AnimGraphMcpPort=18766
		int32 CmdPort = 0;
		if (FParse::Value(FCommandLine::Get(), TEXT("AnimGraphMcpPort="), CmdPort) && CmdPort > 0 && CmdPort < 65536)
		{
			Port = static_cast<uint32>(CmdPort);
		}
	}

	void RegisterConsoleCommands()
	{
		ConsoleCommands.Add(MakeUnique<FAutoConsoleCommand>(TEXT("AnimGraphMcp.Start"), TEXT("Start the AnimGraph MCP HTTP bridge"),
			FConsoleCommandDelegate::CreateRaw(this, &FAnimGraphMcpEditorModule::StartBridge)));
		ConsoleCommands.Add(MakeUnique<FAutoConsoleCommand>(TEXT("AnimGraphMcp.Stop"), TEXT("Stop the AnimGraph MCP HTTP bridge"),
			FConsoleCommandDelegate::CreateRaw(this, &FAnimGraphMcpEditorModule::StopBridge)));
		ConsoleCommands.Add(MakeUnique<FAutoConsoleCommand>(TEXT("AnimGraphMcp.Status"), TEXT("Log the AnimGraph MCP bridge status"),
			FConsoleCommandDelegate::CreateRaw(this, &FAnimGraphMcpEditorModule::LogStatus)));
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

		AnimMcpTools::RegisterStatusTools(*Dispatcher, Bridge);
		AnimMcpTools::RegisterInspectTools(*Dispatcher);
		AnimMcpTools::RegisterAssetTools(*Dispatcher);
		AnimMcpTools::RegisterGraphTools(*Dispatcher);
		AnimMcpTools::RegisterCompileTools(*Dispatcher);
		AnimMcpTools::RegisterEditorTools(*Dispatcher);
		AnimMcpTools::RegisterLayerTools(*Dispatcher);
		AnimMcpTools::RegisterAutomationTools(*Dispatcher);
		AnimMcpTools::RegisterVariableTools(*Dispatcher);
		AnimMcpTools::RegisterMontageTools(*Dispatcher);
		AnimMcpTools::RegisterSkeletonTools(*Dispatcher);
		AnimMcpTools::RegisterSequenceTools(*Dispatcher);
		AnimMcpTools::RegisterImportTools(*Dispatcher);
		AnimMcpTools::RegisterRetargetTools(*Dispatcher);
		AnimMcpTools::RegisterValidationTools(*Dispatcher);
		AnimMcpTools::RegisterEditTools(*Dispatcher);
		AnimMcpTools::RegisterSearchTools(*Dispatcher);
		AnimMcpTools::RegisterPromoteTools(*Dispatcher);

		if (!Bridge->Start(Port, bRequireToken, Dispatcher.ToSharedRef()))
		{
			UE_LOG(LogAnimGraphMcp, Error, TEXT("AnimGraphMcp bridge failed to start on port %u. Use AnimGraphMcp.Start to retry or set [AnimGraphMcp] Port in DefaultEngine.ini"), Port);
			Bridge.Reset();
			Dispatcher.Reset();
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
			UE_LOG(LogAnimGraphMcp, Display, TEXT("Running: http://127.0.0.1:%u/v1/<tool>, %d tools, token %s"), Bridge->GetPort(),
				Dispatcher.IsValid() ? Dispatcher->GetToolNames().Num() : 0, Bridge->IsTokenRequired() ? TEXT("required") : TEXT("not required"));
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

	uint32 Port = 18765;
	bool bRequireToken = true;
	bool bAutoStart = true;
};

IMPLEMENT_MODULE(FAnimGraphMcpEditorModule, AnimGraphMcpEditor)
