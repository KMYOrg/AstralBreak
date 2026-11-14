# Widget MCP (`Plugins/WidgetMcp`)

UI 자동 생성 파이프라인(설계 [ui-autogen-pipeline.md](../../Docs/Design/ui-autogen-pipeline.md))의 에디터 쪽 기능 플러그인입니다. 공용 코어 [`EditorMcpCore`](../EditorMcpCore/README.md) 브리지에 Tool 을 등록합니다.

**상태: Phase 0 뼈대.** Tool 은 아직 없습니다 — 코어에 기능 이름(`get_editor_status.features[]` 의 `WidgetMcp`)과 `widget` 상태 필드만 등록합니다. 정식 Tool(`import_ui_textures` · `create_widget_blueprint` · `preview/apply_widget_spec` · `apply_widget_patch` · `export_widget_spec` · `compile_widget_blueprint` · `save_widget_run` · `render_widget` · `list_bind_widgets` · `discard_run_packages`)은 설계 §6 대로 Phase 1a 에서 붙습니다.

- 모듈 `WidgetMcpEditor`(Type Editor). 의존: `EditorMcpCore` · `UMG` · `UMGEditor` · `Slate` · `ImageCore`.
- `Private/Spike/` — Phase 0 스파이크(설계 §12-1 A6 · A7): 손 spec → `UWidgetBlueprintFactory`(대화창 없이) → `ConstructWidget` + `OnVariableAdded` → 컴파일 → `FWidgetRenderer` 3회 → PNG · `GetPaintSpaceGeometry`. Automation `WidgetMcp.Spike.BuildRender` 가 돌리고 결과(`draw_1~3.png` · `report.json`)를 `Tools/mcp/results/widget_spike/<시각>/`(git 무시, Saved 밖)에 씁니다. 애셋은 `/Game/_AutoGen/Spike/` 에 **메모리에만** 만들고 저장하지 않습니다(에디터를 끌 때 discard).
