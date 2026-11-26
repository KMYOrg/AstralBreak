#include "AnimMcpLog.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Core/AnimMcpGeneration.h"
#include "EditorMcpCoreModule.h"
#include "Modules/ModuleManager.h"
#include "Tools/AnimMcpTools.h"

/**
 * 애니 기능 플러그인 모듈 — Animation Blueprint · 몽타주 · 리타깃 · 캡처 · 생성 Tool 을 EditorMcpCore 에 등록한다.
 * (2026-11-14 플러그인 분리) HTTP 브리지 · 토큰 · 콘솔 명령 · get_editor_status · quit_editor · Automation 실행은 EditorMcpCore 가 갖는다.
 * 애니 설정은 DefaultEngine.ini 의 [AnimGraphMcp] 섹션 그대로:
 *   +GenerationOutputPaths=/Game/.../   +ImportSourceRoots=Saved/...   MaxRetargetAssetsPerCall=20   +PromotionPaths=/Game/.../   (AI 애니 생성, Core/AnimMcpGeneration)
 *   +SmokeTestPaths=/Game/Animation   +AnimationTagFiles=…   +CaptureOutputRoots=…
 * get_editor_status 의 generation 필드는 여기서 더한다(필드 이름 · 모양은 분리 전과 같다).
 */
class FAnimGraphMcpEditorModule : public IModuleInterface
{
public:
	static constexpr const TCHAR* Feature = TEXT("AnimGraphMcp");

	virtual void StartupModule() override
	{
		IEditorMcpCoreModule& Core = IEditorMcpCoreModule::Get();
		Core.RegisterTools(Feature, [](FAnimMcpDispatcher& Dispatcher)
		{
			AnimMcpTools::RegisterInspectTools(Dispatcher);
			AnimMcpTools::RegisterAssetTools(Dispatcher);
			AnimMcpTools::RegisterGraphTools(Dispatcher);
			AnimMcpTools::RegisterCompileTools(Dispatcher);
			AnimMcpTools::RegisterLayerTools(Dispatcher);
			AnimMcpTools::RegisterAutomationTools(Dispatcher);
			AnimMcpTools::RegisterVariableTools(Dispatcher);
			AnimMcpTools::RegisterMontageTools(Dispatcher);
			AnimMcpTools::RegisterSkeletonTools(Dispatcher);
			AnimMcpTools::RegisterSequenceTools(Dispatcher);
			AnimMcpTools::RegisterImportTools(Dispatcher);
			AnimMcpTools::RegisterRetargetTools(Dispatcher);
			AnimMcpTools::RegisterValidationTools(Dispatcher);
			AnimMcpTools::RegisterEditTools(Dispatcher);
			AnimMcpTools::RegisterSearchTools(Dispatcher);
			AnimMcpTools::RegisterPromoteTools(Dispatcher);
			AnimMcpTools::RegisterCaptureTools(Dispatcher);
			// StateTree Tool 은 2026-11-14 StateTreeMcp 플러그인으로 옮겼다
		});
		Core.RegisterStatusSection(Feature, [](const TSharedRef<FJsonObject>& Result)
		{
			// AI 애니 생성: 출력·임포트 경로의 유일한 기준(ini) — anim_gen 은 이것을 읽는다
			Result->SetObjectField(TEXT("generation"), AnimMcpGeneration::DescribeSettings());
		});
	}

	virtual void ShutdownModule() override
	{
		// 종료 순서상 코어가 먼저 내려가 있을 수 있다 — 다시 로드하지 않는다
		if (IEditorMcpCoreModule* Core = IEditorMcpCoreModule::GetIfLoaded())
		{
			Core->UnregisterTools(Feature);
		}
	}
};

IMPLEMENT_MODULE(FAnimGraphMcpEditorModule, AnimGraphMcpEditor)
