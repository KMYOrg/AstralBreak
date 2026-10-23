using UnrealBuildTool;

public class AnimGraphMcpEditor : ModuleRules
{
	public AnimGraphMcpEditor(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			// 생성·컴파일·저장·트랜잭션 (FKismetEditorUtilities · FBlueprintEditorUtils · FScopedTransaction · UEditorAssetSubsystem · UAssetEditorSubsystem)
			"UnrealEd",

			// AnimGraph 에디터 노드 (UAnimGraphNode_* · UAnimState* · UAnimation*Graph/Schema)
			"AnimGraph",
			// FAnimNode_* 런타임 구조체
			"AnimGraphRuntime",
			// UK2Node_* · UEdGraphSchema_K2 (Transition Rule 조립)
			"BlueprintGraph",

			// 엔진 내장 HTTP 서버 — 게임 스레드 티커로 동작, 기본 바인드 localhost (Runtime/Online/HTTPServer)
			"HTTPServer",
			// FInternetAddr (요청 PeerAddress 로그)
			"Sockets",

			"Json",
			"AssetRegistry",
			// IPluginManager (플러그인 상태 조회)
			"Projects",

			// AI 애니 생성 Phase 1 (Docs/AIAnimation) — IK Rig·리타기터 애셋(UIKRigDefinition · UIKRetargeter · 리타깃 op)
			"IKRig",
			// UIKRigController · UIKRetargeterController · UIKRetargetBatchOperation · 팩토리
			"IKRigEditor",
			// FBX 임포트 — UInterchangeManager · UInterchangeSourceData · 파이프라인 기반 클래스
			"InterchangeCore",
			"InterchangeEngine",
			// UInterchangeGenericAssetsPipeline 과 하위 설정 (Interchange 플러그인)
			"InterchangePipelines",
			// UAnimPoseExtensions — 검증용 프레임 포즈 샘플링 (에디터 전용)
			"AnimationBlueprintLibrary",
		});
	}
}
