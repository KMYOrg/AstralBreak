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
			// 공용 코어 (2026-11-14 플러그인 분리) — 디스패처 · 봉투 · HTTP 브리지 · 토큰 · 자동 시험 러너 · 보호 목록 · 쓰기 가드 · Tool 등록
			"EditorMcpCore",

			// 생성·컴파일·저장·트랜잭션 (FKismetEditorUtilities · FBlueprintEditorUtils · FScopedTransaction · UEditorAssetSubsystem · UAssetEditorSubsystem)
			"UnrealEd",

			// AnimGraph 에디터 노드 (UAnimGraphNode_* · UAnimState* · UAnimation*Graph/Schema)
			"AnimGraph",
			// FAnimNode_* 런타임 구조체
			"AnimGraphRuntime",
			// UK2Node_* · UEdGraphSchema_K2 (Transition Rule 조립)
			"BlueprintGraph",

			"Json",
			"AssetRegistry",

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

			// StateTree 자동화 의존성(StateTree · GameplayStateTree · AIModule · PropertyBindingUtils · GameplayTags · GameplayAbilities)은
			// 2026-11-14 StateTreeMcp 플러그인으로 옮겼다
		});
	}
}
