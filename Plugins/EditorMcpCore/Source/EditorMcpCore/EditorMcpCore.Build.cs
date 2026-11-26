using UnrealBuildTool;

/**
 * 에디터 MCP 공용 코어 — HTTP 브리지 · 디스패처 · 봉투 · 토큰 · request_id 캐시 · get_editor_status · 자동 시험 실행 ·
 * 보호 목록 · 쓰기 허용 경로 · 전역 더티 비교. 기능 플러그인(AnimGraphMcp · StateTreeMcp · WidgetMcp)이 모듈 시작 때
 * IEditorMcpCoreModule::RegisterTools 로 Tool 을 등록한다. 프로젝트 코드에 의존하지 않는다.
 */
public class EditorMcpCore : ModuleRules
{
	public EditorMcpCore(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			// 봉투 · 요청 파라미터가 FJsonObject — 공개 헤더(Bridge/AnimMcpTypes.h)에 나온다
			"Json",
			// 공개 헤더 Bridge/AnimMcpHttpBridge.h 의 FHttpRouteHandle
			"HTTPServer",
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			// FEditorFileUtils(더티 패키지) · UEditorAssetSubsystem(quit_editor 저장) · UAssetEditorSubsystem(열린 편집기)
			"UnrealEd",
			// FInternetAddr (요청 PeerAddress 로그)
			"Sockets",
			"AssetRegistry",
			// IPluginManager (get_editor_status 의 플러그인 상태)
			"Projects",
		});
	}
}
