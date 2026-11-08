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
			// AI 애니 생성 Phase 7 — promote_animation (IAssetTools::RenameAssets · FixupReferencers)
			"AssetTools",
			// AI 애니 생성 Phase 8-2 — capture_animation 의 이미지 버퍼(FImage — 비교 칸 PNG 읽기 · 형식 변환)
			"ImageCore",

			// StateTree 자동화 (Docs/StateTree) — 애셋 · 스키마 · 컴파일 · ViewModel
			"StateTreeModule",
			"StateTreeEditorModule",
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
