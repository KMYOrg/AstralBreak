# Widget MCP (`Plugins/WidgetMcp`)

UI 자동 생성 파이프라인(설계 [ui-autogen-pipeline.md](../../Docs/Design/ui-autogen-pipeline.md))의 에디터 쪽 기능 플러그인입니다. 공용 코어 [`EditorMcpCore`](../EditorMcpCore/README.md) 브리지에 Tool 을 등록합니다. 파이프라인(`Tools/uigen`)은 같은 엔드포인트를 HTTP 로 직접 부르고, 사람 · Claude 가 대화로 쓸 때는 `Tools/mcp/widget_mcp/server.py`(MCP 창구)를 씁니다.

**상태: Phase 1a 완료 (Tool 11개 — 1a-2 에서 추가, 11-15 끝 검증: `WidgetMcp.*` 5/5 · Development `-DisableAdaptiveUnity` 빌드 · 렌더 색 사람 눈 확인 통과) · 1b-3 에서 `import_font_family` 추가(Tool 12개). Phase 1b 끝 검증(11-15): `WidgetMcp.*` 6/6 · Development `-DisableAdaptiveUnity` 빌드. Phase 3-2(11-25): 칸(`UserWidget`) 어휘 · `create_button_style` · 버튼 상태 덮어쓰기.** 모듈 `WidgetMcpEditor`(Type Editor). 의존: `EditorMcpCore` · `UMG` · `UMGEditor` · `UnrealEd` · `Interchange*` · `AssetRegistry` · `CommonUI`(버튼 스타일).

## 설정 (`Config/DefaultEngine.ini [WidgetMcp]`)

```ini
[WidgetMcp]
+WidgetOutputPaths=/Game/_AutoGen/          ; 쓰기 Tool 의 유일한 패키지 경로 — run 마다 /Game/_AutoGen/<run_id>/ (git 무시)
+WidgetImportSourceRoots=Tools/uigen/work/  ; import_ui_textures 가 읽는 디스크 폴더
+WidgetRenderOutputRoots=Tools/uigen/work/  ; render_widget 이 PNG 를 쓰는 디스크 폴더 (새 · 빈 하위 폴더만)
+WidgetFontOutputPaths=/Game/UI/Fonts/      ; import_font_family 만 — 프로젝트 폰트(커밋 대상, 저장까지). 그 아래 하위 폴더만
+WidgetPromotionPaths=/Game/UI/HUD/         ; (· /Game/UI/Common/ · /Game/UI/Screens/) promote_widget 의 대상 · 놓을 수 있는 칸(UserWidget class) · 버튼 스타일(defaults.Style)이 있는 곳. 그 아래 하위 폴더만
+WidgetInstanceProperties=ButtonText        ; 놓인 칸마다 spec props 로 바꿀 수 있는 속성 이름(EditAnywhere 글자) — 여기 없는 것은 거절
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
| `render_widget` | 오프스크린 렌더(감마 보정 PNG) + 같은 그리기의 geometry · 탐침 색. `states[{name, overrides}]` = 여러 상태를 한 호출로(상태마다 새 인스턴스 · 글꼴 준비 대기 한 번 · geometry 없음). 덮어쓰기(`overrides`)의 열쇠 = 위젯 이름 · `.`(이 위젯 자신) · `칸/안쪽 위젯`, 값 = `visible` · `percent` · `text` · `enabled` · `button`(hovered · pressed · selected · selected_hovered · selected_pressed — 실제 Slate 이벤트로). **그 상태가 되지 않으면 오류 `OVERRIDE_NOT_APPLIED`**(그리기 앞 · 뒤로 확인 — 기본 그림을 돌려주지 않는다). 버튼 칸은 `desired_size` 도 돌려준다 | 출력은 렌더 루트 아래 새 · 빈 폴더(묶음은 `<output_dir>/<이름>/` 마다) |
| `create_button_style` | 버튼 스타일 애셋(부모 = `UCommonButtonStyle` 또는 자식 — `UCommonButtonBase` 는 클래스 기본값의 브러시만 읽는다) — 상태 그림 일곱 + 최소 크기 + 부모가 더한 값(`props`). WBP 는 spec `defaults.Style` 로 이것을 쓴다(같은 run 폴더 또는 승격 경로의 것만) | 일곱 다 있고 빈 브러시가 없어야(`BRUSH_MISSING` · `BRUSH_EMPTY` — `Disabled` 가 비면 Slate 가 기본 그림을 흐리게 그린다) · `replace` 는 같은 run 이 만든 것만 |
| `save_widget_run` · `discard_run_packages` | run 폴더 저장(finalize) · 저장 안 한 run 패키지 폐기 | run 폴더(접두 아래 하위 폴더)만 · 폐기는 디스크에 저장된 적 없는 것만 |
| `import_font_family` | 폰트 파일(TTF/OTF) → `UFontFace` 여러 개 + 컴포지트 `UFont` `F_<family>`(Runtime 캐시, 타입페이스 = spec 굵기 이름 Regular · Bold · Light · Italic · Bold Italic) → 저장(기본) | `WidgetFontOutputPaths` 아래 하위 폴더만 · 원본은 `WidgetImportSourceRoots` 안 · 덮어쓰기 거부(하나라도 있으면 아무것도 안 만듦) · 전역 더티 비교(밖이 더티면 만든 것을 내림) · 엔진 `UFontFileImportFactory` 순서(대화창 없이) |

**칸(`UserWidget`, Phase 3-2):** `{type: UserWidget, class: <승격된 WBP 의 패키지 경로>, props: {ButtonText: "…"}}` — 승격 경로의 WBP 클래스만(`CELL_CLASS`), 허용된 속성만, 자식 없음. 칸 안의 위젯은 그 칸의 것이라 spec 에 없고 역추출도 하지 않는다.

**spec 규칙**은 `Tools/uigen/core/spec.py` 와 같습니다 — 슬롯 kind 는 부모 타입이 정하고, 생략한 스칼라는 5.7.4 UMG 생성자 기본값, 생략한 브러시는 그 위젯 클래스 CDO. 파이프라인은 정규화한 spec 을 보내므로 표와 엔진 값이 어긋나도 왕복은 깨지지 않습니다.

**렌더 색(설계 §12-1 A6-색):** `FWidgetRenderer(gamma=true)` + 타깃(B8G8R8A8 · SRGB=0) 조합은 sRGB 를 한 번 더 건다 — 읽은 8비트 값에 채널마다 sRGB→선형 LUT 를 1회 적용한 PNG 를 쓴다(알파 255, 검은 바탕).

## 자동 시험

`run_automation_tests {filter:"WidgetMcp."}` — `WidgetMcp.Tools.ImportTextures` · `.BuildRoundTrip` · `.Render` · `.Guard` · `.ImportFont`(엔진 Roboto 두 파일 → run 폴더, 저장 안 함) · `.ButtonCell`(버튼 스타일 만들기 · 거절 · 상태 일곱 렌더 색 · 칸 놓기 · 안 먹는 덮어쓰기) + Phase 0 스파이크 `WidgetMcp.Spike.BuildRender`. 애셋은 `/Game/_AutoGen/_WidgetMcpTest_*` 에 메모리로만 만들고 끝에 폐기, PNG 입력 · 렌더는 `Tools/uigen/work/_widgetmcp_tests/`(git 무시). 시험 전용 부모 클래스 `UWidgetMcpTestHud`(Gauge 필수 · Label 선택 BindWidget)는 드롭다운에서 숨겨 둔다.

`Private/Spike/` — Phase 0 스파이크(A6 · A7) 기록.
