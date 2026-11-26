using UnrealBuildTool;

/**
 * UI 자동 생성 기능 플러그인 (Docs/Design/ui-autogen-pipeline.md §6).
 * Tool: import_ui_textures · create_widget_blueprint · preview/apply_widget_spec · apply_widget_patch · export_widget_spec ·
 *       compile_widget_blueprint · list_bind_widgets · render_widget · save_widget_run · discard_run_packages (Phase 1a) ·
 *       import_font_family (Phase 1b-3 — UFontFace · 컴포지트 UFont 는 Engine, UPackageTools · UEditorAssetSubsystem 은 UnrealEd) ·
 *       promote_widget (M4 단위 C 가 Phase 4 의 승격을 최소판으로 앞당김 — IAssetTools::AdvancedCopyPackages 는 AssetTools) ·
 *       create_button_style (Phase 3-2 — CommonButton 의 상태 그림을 담는 스타일 애셋).
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
			// GMaxRHIShaderPlatform — 글자 그라데이션 머티리얼 컴파일 오류 확인(1b 후속 D, WidgetMcpTextMaterials)
			"RHI",
			"AssetRegistry",
			// create_button_style · 버튼 상태 렌더 — UCommonButtonStyle · UCommonButtonBase (uigen Phase 3-2)
			"CommonUI",
			"InputCore",
			// promote_widget — IAssetTools::AdvancedCopyPackages (run 폴더 복사 · 복사본끼리 참조 교체)
			"AssetTools",
			// 텍스처 임포트 — UInterchangeManager · 파이프라인(UInterchangeGenericTexturePipeline 은 Interchange 플러그인)
			"InterchangeCore",
			"InterchangeEngine",
			"InterchangePipelines",
		});
	}
}
