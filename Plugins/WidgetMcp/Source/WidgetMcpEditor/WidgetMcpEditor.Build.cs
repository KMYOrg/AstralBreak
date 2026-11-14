using UnrealBuildTool;

/**
 * UI 자동 생성 기능 플러그인 (Docs/Design/ui-autogen-pipeline.md §6).
 * Tool: import_ui_textures · create_widget_blueprint · preview/apply_widget_spec · apply_widget_patch · export_widget_spec ·
 *       compile_widget_blueprint · list_bind_widgets · render_widget · save_widget_run · discard_run_packages (Phase 1a).
 * Private/Spike 는 Phase 0 스파이크(A6 · A7) 기록으로 남긴다.
 */
public class WidgetMcpEditor : ModuleRules
{
	public WidgetMcpEditor(ReadOnlyTargetRules Target) : base(Target)
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
			// 공용 코어 — 브리지 · 봉투 · 쓰기 가드 · Tool 등록
			"EditorMcpCore",
			// FKismetEditorUtilities(컴파일) · FCompilerResultsLog · FBlueprintEditorUtils · UPackageTools · UEditorAssetSubsystem
			"UnrealEd",
			// UWidgetBlueprint · UWidgetBlueprintFactory · UWidgetTree 편집 · FWidgetBlueprintEditorUtils(BindWidget 판정)
			"UMGEditor",
			// UUserWidget · UCanvasPanel · UTextBlock … · FWidgetRenderer
			"UMG",
			"Slate",
			"SlateCore",
			"Json",
			// FImageView (PNG 저장)
			"ImageCore",
			"RenderCore",
			"AssetRegistry",
			// 텍스처 임포트 — UInterchangeManager · 파이프라인(UInterchangeGenericTexturePipeline 은 Interchange 플러그인)
			"InterchangeCore",
			"InterchangeEngine",
			"InterchangePipelines",
		});
	}
}
