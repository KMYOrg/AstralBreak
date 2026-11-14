using UnrealBuildTool;

/**
 * UI 자동 생성 기능 플러그인 (Docs/Design/ui-autogen-pipeline.md §6) — Phase 0 은 뼈대 + 스파이크(Private/Spike)만.
 * 정식 Tool(import_ui_textures · create_widget_blueprint · apply_widget_spec · export_widget_spec · render_widget …)은 Phase 1a.
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
			// FKismetEditorUtilities(컴파일) · FCompilerResultsLog
			"UnrealEd",
			// UWidgetBlueprint · UWidgetBlueprintFactory · UWidgetTree 편집
			"UMGEditor",
			// UUserWidget · UCanvasPanel · UTextBlock … · FWidgetRenderer
			"UMG",
			"Slate",
			"SlateCore",
			"Json",
			// FImageView (PNG 저장)
			"ImageCore",
			"RenderCore",
		});
	}
}
