using UnrealBuildTool;

// 에디터 전용(UncookedOnly) 모듈 — 런타임 애님 노드(AstralBreak 의 FAnimNode_*)를 AnimBP 그래프에 놓는 UAnimGraphNode_* 만 둔다.
// 쿠킹된 게임에는 들어가지 않는다 (엔진 AnimGraph 모듈과 같은 구성)
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
		});
	}
}
