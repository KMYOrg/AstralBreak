using UnrealBuildTool;

/**
 * StateTree 저작 기능 플러그인 (2026-11-14 AnimGraphMcp 에서 분리, Docs/StateTree) — create · inspect · list_*_types · list_*_sources ·
 * preview · apply · compile · revert · run_state_tree_scenario. 브리지 · 봉투 · 자동 시험 러너 · 보호 목록은 EditorMcpCore.
 */
public class StateTreeMcpEditor : ModuleRules
{
	public StateTreeMcpEditor(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			// 시험 Evaluator · 프로브 Task USTRUCT 의 기반(FStateTreeEvaluatorCommonBase · FStateTreeTaskCommonBase)
			"StateTreeModule",
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			// 공용 코어 — 디스패처 · 봉투 · 자동 시험 러너 · 보호 목록 · 설정([EditorMcp]/[AnimGraphMcp]) · 값 변환 · Tool 등록
			"EditorMcpCore",

			// 트랜잭션 · 저장 · 애셋 편집기 (FScopedTransaction · UEditorAssetSubsystem · UAssetEditorSubsystem · PackageTools)
			"UnrealEd",
			"Json",
			"AssetRegistry",
			// create_state_tree — IAssetTools · UStateTreeFactory
			"AssetTools",

			// StateTree 에디터 — 에디터 데이터 · 스키마 · 컴파일 · ViewModel · 노드 클래스 캐시
			"StateTreeEditorModule",
			// AI 스키마 · MoveTo 등 게임플레이 노드 · StateTreeAIComponent
			"GameplayStateTreeModule",
			// run_state_tree_scenario — AAIController 로 폰 · 인스턴스를 찾는다
			"AIModule",
			// FPropertyBindingPath · GetPropertyCompatibility · IsPropertyBindable(에디터 쪽)
			"PropertyBindingUtils",
			"PropertyBindingUtilsEditor",
			// 상태 Tag · 전환 RequiredEvent
			"GameplayTags",
			// 시험 프로브 Task — 첫 상태에서 ASC · 부여 어빌리티를 본다
			"GameplayAbilities",
		});
	}
}
