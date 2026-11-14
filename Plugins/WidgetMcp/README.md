# Widget MCP (`Plugins/WidgetMcp`)

UI 자동 생성 파이프라인(설계 [ui-autogen-pipeline.md](../../Docs/Design/ui-autogen-pipeline.md))의 에디터 쪽 기능 플러그인입니다. 공용 코어 [`EditorMcpCore`](../EditorMcpCore/README.md) 브리지에 Tool 을 등록합니다. 파이프라인(`Tools/uigen`)은 같은 엔드포인트를 HTTP 로 직접 부르고, 사람 · Claude 가 대화로 쓸 때는 `Tools/mcp/widget_mcp/server.py`(MCP 창구)를 씁니다.

**상태: Phase 1a 완료 (Tool 11개 — 1a-2 에서 추가, 11-15 끝 검증: `WidgetMcp.*` 5/5 · Development `-DisableAdaptiveUnity` 빌드 · 렌더 색 사람 눈 확인 통과).** 모듈 `WidgetMcpEditor`(Type Editor). 의존: `EditorMcpCore` · `UMG` · `UMGEditor` · `UnrealEd` · `Interchange*` · `AssetRegistry`.

## 설정 (`Config/DefaultEngine.ini [WidgetMcp]`)

```ini
[WidgetMcp]
+WidgetOutputPaths=/Game/_AutoGen/          ; 쓰기 Tool 의 유일한 패키지 경로 — run 마다 /Game/_AutoGen/<run_id>/ (git 무시)
+WidgetImportSourceRoots=Tools/uigen/work/  ; import_ui_textures 가 읽는 디스크 폴더
+WidgetRenderOutputRoots=Tools/uigen/work/  ; render_widget 이 PNG 를 쓰는 디스크 폴더 (새 · 빈 하위 폴더만)
```

마운트 루트(`/Game/`)는 허용 목록이 될 수 없습니다(경고 후 무시). 목록이 비면 그 Tool 은 아무 데도 쓰지 · 읽지 않습니다. `get_editor_status.widget` 이 정규화된 값과 Tool 목록을 돌려줍니다.

## Tool

| Tool | 하는 일 | 안전장치 |
| :--- | :--- | :--- |
| `import_ui_textures` | PNG → Interchange 동기 임포트 → UI 설정(압축 · `TEXTUREGROUP_UI` · `TMGS_NoMipmaps` · NeverStream · sRGB) → 텍스처 빌드 대기 | 기본 'Textures' 스택의 파이프라인을 트랜지언트로 복제해 **`bAllowNonPowerOfTwo=true`**(기본 false 면 200×50 같은 UI 텍스처를 걸러 냄) · 노멀맵 감지 끔 · 이름 지정. 덮어쓰기 거부 · 전역 더티 비교 |
| `create_widget_blueprint` | 빈 WBP + Canvas 루트(대화창 없는 팩토리는 루트를 안 만든다 — 설계 §12-1 A7) | 부모는 UUserWidget 또는 Abstract 가 아닌 자식(생성 베이스 ViewBase 거부 — 부모는 스텁) |
| `preview_widget_spec` · `apply_widget_spec` | 조정기 — 목표 spec 과의 차이를 op 로 보고 · 전체 사전 검사 · **사본 트리에 적용 → 역추출로 목표와 같은지 확인 → 바꿔 끼우기** → GUID 맵 동기 → 컴파일 | `expected_revision` 필수(`REVISION_MISMATCH`) · 바인딩 위젯 제거/타입 변경 거부(`BINDING_REMOVAL`/`BINDING_TYPE`) · `locked` 위젯 변경 거부 · 실패하면 원본 그대로(`rollback_verified`) |
| `apply_widget_patch` | spec patch(set · add_widget · remove_widget · move)를 지금 트리의 역추출에 적용해 조정기로 | binding · replace_asset 은 파이프라인 몫(`PIPELINE_ONLY`) |
| `export_widget_spec` | WBP → spec + revision(정규 JSON SHA1) + `unsupported[]` + 텍스처 설정 + 바인딩 + GUID 맵 점검 | 어휘 밖 위젯은 locked 로 |
| `compile_widget_blueprint` | 컴파일 + `missing_bindings[]` | |
| `list_bind_widgets` | C++ 클래스(또는 WBP 부모)의 BindWidget 계약 | |
| `render_widget` | 오프스크린 렌더(감마 보정 PNG) + 같은 그리기의 geometry · 탐침 색 | 출력은 렌더 루트 아래 새 · 빈 폴더 |
| `save_widget_run` · `discard_run_packages` | run 폴더 저장(finalize) · 저장 안 한 run 패키지 폐기 | run 폴더(접두 아래 하위 폴더)만 · 폐기는 디스크에 저장된 적 없는 것만 |

**spec 규칙**은 `Tools/uigen/core/spec.py` 와 같습니다 — 슬롯 kind 는 부모 타입이 정하고, 생략한 스칼라는 5.7.4 UMG 생성자 기본값, 생략한 브러시는 그 위젯 클래스 CDO. 파이프라인은 정규화한 spec 을 보내므로 표와 엔진 값이 어긋나도 왕복은 깨지지 않습니다.

**렌더 색(설계 §12-1 A6-색):** `FWidgetRenderer(gamma=true)` + 타깃(B8G8R8A8 · SRGB=0) 조합은 sRGB 를 한 번 더 건다 — 읽은 8비트 값에 채널마다 sRGB→선형 LUT 를 1회 적용한 PNG 를 쓴다(알파 255, 검은 바탕).

## 자동 시험

`run_automation_tests {filter:"WidgetMcp."}` — `WidgetMcp.Tools.ImportTextures` · `.BuildRoundTrip` · `.Render` · `.Guard` + Phase 0 스파이크 `WidgetMcp.Spike.BuildRender`. 애셋은 `/Game/_AutoGen/_WidgetMcpTest_*` 에 메모리로만 만들고 끝에 폐기, PNG 입력 · 렌더는 `Tools/uigen/work/_widgetmcp_tests/`(git 무시). 시험 전용 부모 클래스 `UWidgetMcpTestHud`(Gauge 필수 · Label 선택 BindWidget)는 드롭다운에서 숨겨 둔다.

`Private/Spike/` — Phase 0 스파이크(A6 · A7) 기록.
