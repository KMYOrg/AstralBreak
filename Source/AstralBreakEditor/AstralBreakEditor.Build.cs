using UnrealBuildTool;

// 에디터 · 미쿠킹 전용(UncookedOnly) 모듈 — 쿠킹된 게임에는 들어가지 않는다 (엔진 AnimGraph 모듈과 같은 구성).
//   - 런타임 애님 노드(AstralBreak 의 FAnimNode_*)를 AnimBP 그래프에 놓는 UAnimGraphNode_*
//   - 네트워크 단계 자동 시험 (Private/Tests — 멀티 PIE 시험 + 별도 프로세스용 Gauntlet 컨트롤러, 설계 m3-enemy-ai.md §7-2).
//     UncookedOnly 는 에디터 실행 파일의 -game · -server 에서도 올라가므로 런타임 모듈을 건드리지 않고 둘 수 있다
public class AstralBreakEditor : ModuleRules
{
	public AstralBreakEditor(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"AnimGraph",
			"AnimGraphRuntime",
			"AstralBreak",
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"BlueprintGraph",
			"UnrealEd",
			"Gauntlet",

			// 적 AI 시험 (Private/Tests — 엔진 전제 확인 · 전투 멀티 PIE, 설계 m3-enemy-ai.md §8)
			"AIModule",
			"GameplayAbilities",
			"GameplayTags",
			"GameplayTasks",
			"GameplayStateTreeModule",
			"NavigationSystem",
			"StateTreeModule",
		});
	}
}
