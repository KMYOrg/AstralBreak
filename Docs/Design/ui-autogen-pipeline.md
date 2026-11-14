# UI 자동 생성 파이프라인 설계 (컨셉아트 · 텍스트 · 참조 이미지 → WBP)

작성일: 2026-11-14 · 대상: UE 5.7.4 · 기준 커밋: `88a4813` · 원 요구사항: [ui-autogen-requirements.md](ui-autogen-requirements.md) · 관련: [m4-ult-chain.md](m4-ult-chain.md) §5(HUD)
상태: **Phase 0 완료 · 커밋 `6700484`(2026-11-14)** — 플러그인 분리(EditorMcpCore · AnimGraphMcp · StateTreeMcp · WidgetMcp 뼈대) · 빌드 2구성 · 회귀 통과, 가정 A1 ~ A7 결과는 §12-1(A4 · A5 는 사용자 CLI 로그인 뒤 `claude` 2.1.325 로 실측). **Phase 1a 완료(11-15, 미커밋)** — 하위 단계 1a-1 ~ 1a-5 끝, 끝 조건 4개 충족(§11 'Phase 1a 결과 요약' · '1b 로 넘길 것'), 빌드 2구성 · 에디터 1회 · pytest 142 통과, 렌더 색 사람 눈 확인 통과(§12-1 A6-색). 설계 승인(11-14) · §12-2 질문 1 · 2 · 4 · 5 · 6 · 8 결정. 값은 전부 잠정이다.

표기: **[소스]** = 5.7.4 엔진 · 프로젝트 소스에서 확인한 것(파일:줄) · **[실측]** = 이 PC 에서 명령으로 확인한 것 · **[P0]** = Phase 0 스파이크에서 확인할 것 · **[P0 결과]** = Phase 0 에서 확인한 결과(11-14) · **[바이너리]** = 설치된 실행 파일 안의 문자열로 확인(동작은 미실측).

---

## 0. 요약

**무엇을 만드나.** UI 컨셉아트(또는 텍스트 · 참조 이미지 묶음)를 주면, 사람 개입 없이 에셋 생성 → 후처리 → 임포트 → C++ 바인딩 클래스 생성 → WBP 구성 → 렌더 검증(실패 시 재시도)까지 돌고, WBP 프로토타입과 리포트를 남긴다. 만든 화면을 이미지 · 텍스트로 고치는 수정 모드도 있다. UI 종류(메인 HUD · 장비창 · 옵션 등)는 고르는 대상이 아니라 입력(`screen_type`)이다.

**왜 지금.** M4 단위 C(전투 HUD)부터 본격적으로 UI 에셋이 필요하다. **첫 실전 대상은 M4 전투 HUD** 이고, 파이프라인 Phase 1 의 산출물이 곧 M4 단위 C 의 화면 부분이다.

**핵심 결정 (원문과 달라지는 것은 §1 에 근거와 함께)**

1. 플러그인은 **공용 코어 `EditorMcpCore` + 기능별 플러그인**(`AnimGraphMcp` · `WidgetMcp` · 나중에 `StateTreeMcp`)으로 나눈다.
2. 오케스트레이터(Python)가 순서 · 재시도 · 분기를 정하고, **LLM 은 판단이 필요한 곳에만** 쓴다(normalize · analyze · verifier 시각 판정 · fix · 수정 지시 해석). 생성 실행 · 후처리 · 코드 생성 · 빌드 · 규칙/수치 검증은 결정적 코드다.
3. build 는 **spec ↔ WBP 조정기**다 — 첫 빌드도 '빈 WBP 에서의 차이 적용'. 그래서 WBP → spec 역추출이 Phase 1 부터 있다(왕복 검증 도구).
4. C++ 위젯 클래스는 **템플릿 코드 생성**(LLM 아님)으로 만든다 — 생성 베이스(매번 덮어씀) + 스텁(한 번만, 사람 소유) 두 겹, **기능 폴더 + `AutoGen/` 하위**.
5. 결과는 `/Game/_AutoGen/<run_id>/`(git 무시)에만 만들고, **verify 를 통과할 때까지 저장하지 않는다** — 롤백 = 저장 안 한 패키지 폐기. 사람이 고른 것만 `/Game/UI/...` 로 승격해 커밋한다.
6. 합격은 규칙 · 수치로만. 스타일 유사도 · ΔE 는 **Phase 2 보정 전까지 기록만** 한다.
7. Codex 한도에 걸리면 **멈추고 나중에 재개**한다(procedural 이 원래 잘하는 종류만 대체).

**빈칸 채움 (원문 `<…>`)**

| 원문 | 값 | 근거 |
| :--- | :--- | :--- |
| 프로젝트 경로 | `D:/UE5Projects/AstralBreak` | |
| 기존 플러그인 경로 | `Plugins/AnimGraphMcp` + `Tools/mcp/` | |
| GPU / VRAM | RTX 3080 Ti · 12 GB (RAM 64 GB) | [실측] `nvidia-smi` |
| 폰트 | Pretendard 또는 Noto Sans KR (OFL — 게임에 넣어 배포 가능) · 저장소에 폰트 없음 | [실측] · §12 질문 |
| 샘플 컨셉아트 | M4 전투 HUD 컨셉아트 — 사용자 준비 | §12 질문 |

---

## 1. 원 요구사항에서 달라지는 것

| # | 원문 | 이 설계 | 근거 |
| ---: | :--- | :--- | :--- |
| 1 | 플러그인 확장 또는 별도 — 제안 | 공용 코어 + 기능별 플러그인 (§3) | 사용자: "기능별로 나눈 느낌이 나야 한다". 지금 디스패처가 이미 기능별 등록 함수 20개로 나뉘어 있어 옮기기 쉽다 [소스] `AnimGraphMcpEditorModule.cpp:101-123`. 별도 브리지(포트 · 토큰 두 벌)는 안전장치가 따로 놀게 된다 |
| 2 | 단계마다 `claude -p` | LLM 단계(정규화 · 분석 · 시각 판정 · 수정안) + 코드 단계 (§2) | 생성 실행 · 후처리 · 빌드 · 규칙 검사는 판단이 아니라 계산이다. 코드로 두면 재시도가 재현되고, 무인 LLM 이 에디터 쓰기 도구를 쥐지 않으며, 사용량이 준다. '순서는 코드가 정한다'(결정 1)를 더 엄격하게 지키는 쪽이다 |
| 3 | 단계: normalize → analyze → generate → refine → build → verify | **codegen** 을 analyze 와 generate 사이에, 재시도용 **fix** 를 verify 뒤에 둔다 | 결정 5(C++ + BindWidget)를 무인으로 지키려면 바인딩 클래스 생성 · 빌드가 단계로 있어야 한다 |
| 4 | 역할 미지정 이미지는 analyze 가 분류 | **normalize** 가 분류 | multi_ref 는 역할별 정리로 목업(= reference.png)을 만든다 — 분류가 normalize 안에서 끝나야 한다. 원문 안의 순서 모순 |
| 5 | spec → WBP 구성, 부분 적용은 Phase 4 | build = 조정기, 역추출은 Phase 1 | 재시도(fix → patch → build)와 수정 모드가 같은 코드 경로를 쓴다. 역추출은 Phase 1 의 왕복 검증(spec → WBP → spec 일치)으로 쓴다 |
| 6 | 실패하면 run 전체 롤백 | 사전 검증 실패 = 배치 무변경. verify 최종 실패 = 디스크 기록은 남기고 uasset 은 저장 안 함 | 실패 원인을 볼 수 있어야 한다. build 가 결정적이라 uasset 은 spec 에서 몇 초 만에 다시 만든다(`--keep-failed` 로 저장도 가능) |
| 7 | 텍스처 `UserInterface2D` | 같은 값 `TC_EditorIcon` — 5.7.4 에서 표시 이름이 **`Uncompressed (RGBA8)`** 로 바뀌었고 엔진이 BC7 을 권한다 | [소스] `TextureDefines.h:400`. 기본값은 원문대로 두고 종류별로 BC7 을 고를 수 있게 한다(§12 질문) |
| 8 | 9-slice Margin 을 텍스처 설정으로 | 브러시(`FSlateBrush` DrawAs Box/Border) 속성 | refine 이 margin 을 추정해 manifest 에 적고 spec 의 브러시가 쓴다 |
| 9 | verifier 서브에이전트 | 별도 `claude -p` 호출 | 오케스트레이터가 따로 부르면 그 자체로 독립 컨텍스트다 |
| 10 | 단계 출력 검증은 Stop 훅 | `--json-schema` + `--output-format json` 우선, Stop 훅은 여러 파일을 쓰는 단계만 | [실측] `claude` 2.1.177 에 `--json-schema` 있음 |
| 11 | 단계마다 `--max-turns` | `--max-budget-usd` + 프로세스 벽시계 타임아웃 (+ 숨은 `--max-turns` 는 보조로만) | [실측] 2.1.177 help 에 `--max-turns` 없음. [P0 결과 · 실측 2.1.325] 숨은 옵션이고 동작한다 — `--max-turns 1` 에 2턴이 필요한 일을 주면 `subtype:"error_max_turns"` · `is_error:true` · `errors:["Reached maximum number of turns (1)"]` · 종료 코드 1. 상한 수단으로 같이 쓴다 |
| 12 | 수치 지표 전부로 합격 판정 | 스타일 유사도 · ΔE 는 Phase 2 보정 전까지 기록만 | 보정 안 된 임베딩 임계값은 결과를 흔든다 |
| 13 | Phase 1 ~ 6 | Phase 0(플러그인 분리 + 스파이크) 추가, Phase 1 = 1a(손 spec) · 1b(컨셉아트) | §11 |
| 14 | 출처 3종 | `provided` 추가(component 이미지를 그대로 쓰기) | 요청 때 `use: auto/asset/reference` 로 선언 — 실행 중 묻지 않는다 |

---

## 2. 전체 구조

### 2-1. 구성 요소

```text
run_pipeline (Python 오케스트레이터 — 순서 · 재시도 · 분기 · 상한 · 잠금)
 ├─ LLM 단계 ─────▶ claude -p   (UE 도구 없음 · work/<run_id> 파일만 읽고 씀 · JSON 스키마 출력)
 ├─ 코드 단계 ────▶ editor_bridge (HTTP 127.0.0.1:18765) ─▶ UE 에디터: EditorMcpCore + WidgetMcp
 │               ├─▶ generate_ui_asset 라우터 ─▶ procedural / codex exec / ComfyUI(Phase 5) / provided
 │               └─▶ UBT 빌드 (codegen 단계에서만, 에디터 내린 상태)
 └─ 파일 ────────▶ Tools/uigen/work/<run_id>/   (단계 사이 데이터 · git 무시 · Saved 밖)
```

- **MCP 서버(`widget_mcp`)는 사람 · Claude 가 대화로 쓸 때의 창구**다. 파이프라인은 같은 브리지 엔드포인트를 HTTP 로 직접 부른다 — 무인 LLM 단계에는 UE 도구를 주지 않는다.
- 작업 폴더를 `Saved/` 밖에 두는 이유: `Saved/` 아래 이미지는 Read · 파일 전송이 막혀 render.png 를 사람도 verifier 도 못 본다(프로젝트 실측 함정).
- 한 번에 run 하나(`work/.lock`) — 브리지 · 에디터가 하나이고, 에디터가 둘 뜨면 `UNAUTHORIZED` 가 난다.

### 2-2. 단계와 입출력

| 단계 | 주체 | 입력 | 출력 (`work/<run_id>/`) | 실패 시 |
| :--- | :--- | :--- | :--- | :--- |
| normalize | concept = 코드(복사) · text / multi_ref = LLM + codex | 진입점 인자 · inputs.yaml | `reference.png` · `brief.json` · (text) `mockups/` · `selection.json` | 중단 |
| analyze | LLM | reference · brief · 화면 프로필 · (있으면) 기존 바인딩 계약 | `spec.json` | 스키마 위반 → 1회 재요청 후 중단 |
| codegen | 코드 | spec 의 바인딩 목록 | C++ 파일 · `codegen.json`(계약 해시) · 빌드 로그 | 생성 파일 원복 후 중단 |
| generate | 코드 | spec.assets[] · routing.yaml | `assets/raw/` · `gen.jsonl` | 에셋별 폴백 → 한도면 `quota` 로 멈춤 |
| refine | 코드 | raw | `assets/final/` · `manifest.json` | 에셋 재생성 요청(generate) |
| build | 코드(브리지) | spec · manifest | `/Game/_AutoGen/<run_id>/` (저장 안 함) · `build.json`(적용 op · revision) | 배치 무변경 · 중단 |
| verify | 코드 + LLM(fixes 만) | reference · spec · 컴파일된 WBP | `render.png` · `geometry.json` · `report.json` · (실패) `fixes.json` | fix 로 |
| fix | LLM | report · fixes · spec | `patches/NNN.json` (spec patch) | 상한 도달 → finalize(실패) |
| finalize | 코드 | report | 통과: run 패키지 저장 · `lineage.json` 갱신 / 실패: 폐기(`--keep-failed` 면 저장) | — |

**재시도 분기** — fix 가 낸 patch 의 op 종류로 코드가 정한다.

| patch op 종류 | 돌아가는 단계 |
| :--- | :--- |
| 배치 · 슬롯 · 스타일 · 텍스트 | build |
| 에셋 교체 · 재생성 | generate(그 에셋만) → refine → build |
| 바인딩 추가 · 타입 변경 | codegen → (에디터 재기동) → build |

- 상한: 재시도 N = 3(잠정). **두 번 연속 실패 게이트 집합이 줄지 않으면 조기 종료**(같은 자리를 맴도는 것 방지). 가장 나은 시도의 기록은 디스크에 남는다.
- codegen 은 **바인딩 계약 해시가 바뀔 때만** 돈다 — 대부분의 재시도는 빌드 · 재기동이 없다.
- codegen 이 analyze 직후(아직 에디터에 이번 run 의 것이 없을 때)라서 재기동해도 잃는 것이 없다. 재시도 중 재기동이 필요하면 저장 안 한 run 패키지를 버리고 spec + manifest 에서 다시 빌드한다(결정적이라 같은 결과).

### 2-3. 에디터 운용

- 시작 · 대기 · 종료는 CLAUDE.md 의 에디터 주기를 그대로 쓴다(DebugGame 에디터 · `wait_for_bridge.py` · `quit_editor` · `wait_for_exit.py`).
- `quit_editor` 는 더티면 거절한다 — **`/Game/_AutoGen/` 만 더티일 때 discard 를 허용**하도록 그 목록에 더한다.
- codegen 빌드는 실행 중인 에디터 구성(DebugGame)만 한다. 두 구성 빌드는 Phase 검증 때(프로젝트 회귀 방침).
- Phase 5 ComfyUI: 12 GB VRAM 을 에디터와 나누면 부족할 수 있다 — generate 동안 에디터를 내리는 운용을 기본으로 둔다(§7).

---

## 3. 플러그인 · 디렉터리 구조

### 3-1. 플러그인 분리 (Phase 0)

```text
Plugins/
├── EditorMcpCore/   공용 — HTTP 브리지 · 디스패처 · 봉투 · 토큰 · request_id 멱등 캐시
│                    · get_editor_status · 자동 시험 실행 · 보호 목록 · 쓰기 허용 경로 · 전역 더티 비교
│                    · revision(SHA1) · 되돌리기 저널 · PNG 출력 경로 제한
├── AnimGraphMcp/    애니 — AnimBP · 몽타주 · 리타깃 · 캡처 · 생성 (지금 기능 그대로)
├── WidgetMcp/       UI — 텍스처 임포트 · WBP 생성/조정/역추출 · 렌더 · 바인딩 계약 (§6)
└── StateTreeMcp/    AI — StateTree 저작 (Phase 0 에서 같이 옮김 — 사용자 결정 11-14)
```

- **코어로 가는 것의 기준 = StateTree 가 기대는 것.** StateTree 코드(`Core/AnimMcpStateTree*` · `Tools/AnimMcpTools_StateTree.cpp` · `Tests/AnimMcpStateTree*`, 약 6.8K줄)가 include 하는 비-StateTree 헤더는 `AnimMcpAssetProtection` · `AnimMcpAssetResolver` · `AnimMcpPropertyRules` · `AnimMcpRuntimeScenario` · `AnimMcpAutomationRunner` · `Bridge/AnimMcpDispatcher` · `Bridge/AnimMcpTypes` · `AnimMcpLog` 뿐이다 [실측 11-14]. 이것들이 코어에 있으면 StateTree 이전은 거의 기계적이다.
- **모듈 이름:** `EditorMcpCore`(Editor) · `AnimGraphMcpEditor`(그대로) · `StateTreeMcpEditor` · `WidgetMcpEditor`. 콘솔 명령은 `EditorMcp.Start/Stop/Status` + 기존 `AnimGraphMcp.*` 별칭.
- **StateTree 빌드 의존성**(`StateTreeModule` · `StateTreeEditorModule` · `GameplayStateTreeModule` · `AIModule` · `PropertyBindingUtils(Editor)` 등)은 StateTree 와 같이 옮겨 AnimGraphMcp 를 가볍게 한다.
- **자동 시험 이름:** `AnimGraphMcp.StateTree.*` → `StateTreeMcp.*`. 현행 참조 문서(플러그인 README · `Tools/mcp/README.md` · `Docs/StateTree/DevelopmentGuide.md`)는 고치고, 지난 보고서 · M3 설계의 기록은 그대로 둔다.
- `StateTreeEditPaths` 는 `[EditorMcp]` 와 기존 `[AnimGraphMcp]` 둘 다에서 읽고, `get_editor_status.state_tree_edit_paths` 필드는 그대로 둔다.

- **등록 방식:** 코어가 `IEditorMcpCoreModule::Get().RegisterTools(FName Feature, TFunction<void(FEditorMcpDispatcher&)>)`(이름 잠정)를 내보내고, 기능 플러그인이 모듈 시작 때 등록한다. 지금 `FAnimMcpDispatcher::RegisterTool(Name, Description, Handler)` [소스] `AnimMcpDispatcher.h:19` 를 그대로 코어로 옮기는 것이다.
- **옮길 양:** 브리지 735줄 + 자동 시험 실행 335줄 + 보호 목록 171줄 + 생성 가드의 공용 부분 — 대략 2 ~ 3K줄. [실측]
- **호환 유지:** 포트 18765 · 토큰 파일 위치 · `-AnimGraphMcpPort` 그대로. ini 는 새 `[EditorMcp]` 와 기존 `[AnimGraphMcp]` 를 둘 다 읽는다. 기존 Python 클라이언트와 하네스는 수정 없이 돌아야 한다.
- **Python 쪽:** `Tools/mcp/anim_graph_mcp/bridge.py` → `Tools/mcp/editor_bridge/`(공용) + 기능별 서버(`anim_graph_mcp/` · `state_tree_mcp/` · `widget_mcp/`). 지금 `state_tree_mcp/server.py` 가 `from anim_graph_mcp import bridge` 로 공유하는 방식 [소스] 의 일반화다.
- **회귀:** `AnimGraphMcp.*` 자동 시험 · `Tools/mcp` pytest · 통합 하네스 1개 · 빌드 2회(프로젝트 방침).

**[P0 결과] 실제로 나눈 모양 (11-14, 미커밋)**

| 플러그인 · 모듈 | 줄 수 | 내용 |
| :--- | ---: | :--- |
| `EditorMcpCore` · `EditorMcpCore` | 2,985 | 브리지 · 디스패처(기능 소유 `BeginFeature/EndFeature/RemoveFeature`) · 봉투 · 토큰 · 캐시 · 코어 Tool 4개(`get_editor_status` · `quit_editor` · `run/poll_automation_tests`) · 러너 · 시나리오 슬롯 · 보호 목록 · 경로 해석 · 값 변환(`Core/AnimMcpPropertyValues`) · 쓰기 가드 공용부(`Core/EditorMcpGuard` — 접두 · `FDirtySnapshot`) · 설정(`Core/EditorMcpSettings`) · 시험 `EditorMcpCore.*` |
| `AnimGraphMcp` · `AnimGraphMcpEditor` | 31,097 | 애니 Tool 37개 + `generation` 상태 필드. 동작 불변 — `AnimMcpGeneration::FDirtyGuard` 는 코어 스냅샷 + 생성 경로, `AnimMcpPropertyRules` 는 노드 허용 목록만 남기고 코어 값 변환 헤더를 포함 |
| `StateTreeMcp` · `StateTreeMcpEditor` | 6,851 | StateTree Tool 9개 + `state_tree_edit_paths` 상태 필드 · 시험 `StateTreeMcp.*`(20개) |
| `WidgetMcp` · `WidgetMcpEditor` | 666 | 뼈대(기능 이름 · `widget` 상태 필드, Tool 0) + `Private/Spike`(A6 · A7) · 시험 `WidgetMcp.Spike.BuildRender` |

- **등록 API(확정):** `IEditorMcpCoreModule::Get().RegisterTools(FName Feature, TFunction<void(FAnimMcpDispatcher&)>)` · `RegisterStatusSection(FName, TFunction<void(const TSharedRef<FJsonObject>&)>)` · `UnregisterTools(FName)` (종료 경로는 `GetIfLoaded()`). 코어는 `OnPostEngineInit` 에 브리지를 열며 등록 함수를 전부 돌리고, 떠 있는 동안의 등록 · 해제는 `FAnimMcpHttpBridge::SyncRoutes` 로 라우트를 붙이고 뗀다.
- **이름:** 코어 타입은 분리 전 이름(`FAnimMcpDispatcher` · `FAnimMcpError` · `AnimMcpJson` · 로그 `LogAnimGraphMcp`)을 그대로 쓰고 헤더 경로(`Bridge/…` · `Core/…`)도 같게 둬서 AnimGraphMcp · StateTree 코드는 include 몇 줄만 바뀌었다. 새 코드용 별칭은 `EditorMcp.h`(`FEditorMcpDispatcher` 등). 이름 뒤집기는 후속 과제.
- **코어 범위 조정 2건:** ① `AnimMcpPropertyRules` 는 통째가 아니라 **값 변환만** 코어로(노드 허용 표는 AnimGraph 모듈을 끌어오므로 AnimGraphMcp 에 남김) ② `AnimMcpAssetResolver` 의 애니 단축 로더(`LoadAnimBlueprint` 등)는 Engine 타입뿐이라 코어에 그대로 둠.
- **호환 [실측]:** 포트 18765 · `Saved/AnimGraphMcp/token` · 헤더 `X-AnimMcp-Token` · `-AnimGraphMcpPort` · 콘솔 `AnimGraphMcp.*`(별칭) + `EditorMcp.*` · 기동 로그 문구 · `get_editor_status` 필드(`features[]` · `widget` 만 추가, `plugin_version` 은 EditorMcpCore 0.1.0) · Tool 50개 이름 그대로. ini 는 `[EditorMcp]` + `[AnimGraphMcp]`(배열 합침 · 값은 새 섹션 우선). Python `Tools/mcp/editor_bridge/bridge.py` — 옛 `anim_graph_mcp/bridge.py` 는 `sys.modules` 교체로 **같은 모듈 객체**(monkeypatch 호환).
- **옮긴 시험 타입의 애셋 호환:** `Content/AI/Test/ST_M3_Probe` 가 `/Script/AnimGraphMcpEditor.AnimMcpLifecycleProbeTask` 를 저장하고 있어 `DefaultEngine.ini [CoreRedirects]` 에 `StructRedirects` 4줄을 더했다 — [실측] 새 에디터에서 `inspect_state_tree` 가 `/Script/StateTreeMcpEditor.…` 로 풀고 값 · `ready_to_run` 유지.
- **함정 [실측]:** ① 파일이 빠지면 유니티 묶음이 바뀌어 다른 파일의 익명 이름공간이 부딪힌다(`AnimMcpRuntimeTests.cpp` 와 `AnimMcpAutomationRunnerTests.cpp` 의 `Step` — 한쪽 이름 변경). 새 모듈은 `-DisableAdaptiveUnity` 로 한 번 묶어 빌드해 확인했다. ② `FPackageName::IsValidLongPackageName("/Game")` 이 true — '마운트 루트 거부' 판정이 실제로는 막지 못한다. 코어 `EditorMcpGuard::IsValidPrefix` 는 고쳤고, AnimGraphMcp 생성 경로 설정은 동작 불변 원칙으로 그대로(후속). ③ 엔진이 PIE 시작마다 로드된 StateTree 를 전부 `CompileIfChanged` 한다 [소스] `StateTreeCompilerManager.cpp:238-245` — `StateTreeMcp.06_CompileFailure` 의 깨진 트리가 메모리에 남으면 같은 에디터의 이후 PIE 시험이 그 로그로 실패한다(시험 순서 — `AstralBreak.*` 를 먼저 돌린다).

### 3-2. 저장소 디렉터리

```text
Plugins/EditorMcpCore/ · AnimGraphMcp/ · WidgetMcp/
Tools/mcp/editor_bridge/ · widget_mcp/                MCP 창구 (대화용)
Tools/uigen/
├── run_pipeline.py                                   진입점
├── stages/        normalize · analyze · codegen · generate · refine · build · verify · fix · finalize
├── gen/           generate_ui_asset 라우터 · 제공자(procedural · codex · comfy · provided) · 정책 · 기록
├── schemas/       inputs · brief · spec · patch · manifest · report · fixes (JSON Schema)
├── profiles/      화면 종류 프로필 (hud · menu · options · dialog)
├── prompts/       LLM 단계 시스템 프롬프트
├── codegen/       C++ 템플릿
├── config/        pipeline.yaml (상한 · 경로 · 모델) · routing.yaml · screens.yaml (화면 ID → 폴더 · 클래스)
├── claude_ctx/    LLM 단계 작업 디렉터리 (자체 .claude · 짧은 CLAUDE.md)
├── tests/         pytest
├── work/          run 별 산출물 — git 무시
└── metrics/       uigen.jsonl · 집계 리포트 — git 무시(집계 결과는 §12 질문)
Source/AstralBreak/UI/<기능>/ + <기능>/AutoGen/       C++ (§3-3)
Content/_AutoGen/<run_id>/                            run 산출물 — git 무시
Content/UI/<기능>/                                     승격본 — git 커밋
Content/UI/Fonts/                                      프로젝트 폰트
```

`.gitignore` 에 `Tools/uigen/work/` · `Tools/uigen/metrics/` · `Content/_AutoGen/` 를 더한다. `.png` · `.uasset` 은 LFS 대상이다 [실측] `.gitattributes:5,18` — 그래서 run 산출물은 커밋하지 않는다.

### 3-3. C++ 코드 생성 — 생성 베이스 + 스텁 (Generation Gap)

```text
Source/AstralBreak/UI/
├── Debug/                                   기존
└── HUD/
    ├── AstralCombatHUDWidget.h/.cpp         스텁 — 없을 때만 생성, 이후 사람 소유 (M4 C 로직)
    └── AutoGen/
        └── AstralCombatHUDViewBase.h/.cpp   생성 — 매번 덮어씀 (첫 줄 표식)
```

| 파일 | 내용 | 덮어쓰기 |
| :--- | :--- | :--- |
| `UAstral<화면>ViewBase` (`UUserWidget` 자식, Abstract) | 동적 위젯마다 `UPROPERTY(meta=(BindWidget))` + **데이터 종류별 setter** | 매번 — 첫 줄 `// AUTO-GENERATED by uigen` 이 있을 때만 |
| `UAstral<화면>Widget : ViewBase` | 빈 클래스. 게임 시스템 연결(GAS · 체인 컴포넌트)은 여기 | **절대 안 함** — 없을 때만 생성 |
| WBP | 부모 = 스텁 | run 마다 새로 |

**setter 템플릿 (Phase 1 범위)**

| brief 데이터 종류 | 위젯 | 생성되는 함수 |
| :--- | :--- | :--- |
| `text` | TextBlock | `SetX(const FText&)` |
| `number` | TextBlock | `SetX(int32 / float)` — 형식은 brief 의 `format` |
| `progress` | ProgressBar | `SetX(float Percent)` |
| `flag` | 아무 위젯 | `SetXVisible(bool)` |
| `image` | Image | `SetX(UTexture2D*)` |
| `list` | ListView / 반복 하위 WBP | Phase 3 (하위 WBP 생성과 같이) |

이름은 brief 의 데이터 id 에서 나온다. M4 HUD 예(§4-2 의 `dynamic_data`): `SetUltGauge(float)` · `SetUltReadyVisible(bool)` · `SetChainPanelVisible(bool)` · `SetChainRemaining(float)` · `SetChainCount(const FText&)` · `SetBurstBannerVisible(bool)` · `SetBurstCount(int32)` · `SetUltBlockedVisible(bool)`. 스텁(`UAstralCombatHUDWidget`, M4 설계 §5 의 이름)에는 개발 세션이 '속성 변화 통지 → setter 호출' 몇 줄을 쓴다.

**소유 규칙 (codegen 의 안전장치)**

1. 쓰기는 `Source/AstralBreak/UI/*/AutoGen/`(덮어쓰기, 표식 있는 파일만)과 `Source/AstralBreak/UI/*/`(스텁 새로 만들기만)뿐 — 그 밖은 거부. 사람이 표식을 지우면 그 파일은 사람 소유가 된다.
2. **바인딩은 추가만** — 제거 대신 `BindWidgetOptional` 로 낮춘다. 같은 클래스를 쓰는 이전 run 의 WBP 가 계속 컴파일되게 하려는 것이다.
3. 빌드 실패 → 이번에 쓴 파일을 `work/<run_id>/codegen/backup/` 에서 되돌리고 중단.
4. 클래스 이름이 정체성이다 — WBP 가 기억하는 부모 경로는 `/Script/AstralBreak.<클래스>` 로 폴더가 들어가지 않는다. 폴더는 옮겨도 되고, 이름은 `screens.yaml` 에서 처음에 정해 바꾸지 않는다.
5. 헤더 파일 이름은 모듈 안에서 겹치면 안 된다(UHT) — `ViewBase` / `Widget` 접미사로 피한다. 생성 cpp 에는 익명 네임스페이스를 쓰지 않는다(유니티 빌드 충돌 — 프로젝트 실측 함정).
6. 바인딩 계약은 기존 클래스에서 리플렉션으로 읽는다 — `FWidgetBlueprintEditorUtils::IsBindWidgetProperty(Property, bIsOptional)` [소스] `WidgetBlueprintEditorUtils.h:104`.
7. 채택되지 않은 화면의 클래스가 쌓이므로, '승격된 WBP 가 없는 화면' 목록을 보여 주는 정리 도구를 둔다(삭제는 사람이 결정).

---

## 4. 스키마 초안

전부 `schema_version` 을 갖고 `Tools/uigen/schemas/` 의 JSON Schema 로 검사한다. 아래 예시는 M4 HUD 기준이다.

### 4-1. inputs.yaml

```yaml
mode: multi_ref                 # concept | text | multi_ref (진입점 --concept / --text 는 이 파일을 내부에서 만든다)
screen_type: hud                # hud | menu | options | dialog  → profiles/
screen_id: CombatHUD            # screens.yaml 의 키 → C++ 클래스 · 폴더 · 승격 경로
text: "전투 HUD — 오의 게이지 · 체인 패널 · 버스트 배너"
data:                           # 동적 데이터 (생략 시 analyze 가 제안하고 brief 에 근거를 적는다)
  - { id: ult_gauge, type: progress }
  - { id: chain_remaining, type: number, format: "0.0" }
images:
  - { path: ref/hud_concept.png, role: layout }
  - { path: ref/style_gold.png,  role: style }
  - { path: ref/ult_frame.png,   role: component, target: UltGauge, use: auto }   # auto | asset | reference
  - { path: ref/mood.png }       # 역할 생략 → normalize 가 분류하고 brief 에 근거 기록
```

`use` 는 component 역할에만 뜻이 있다(기본 `auto` — 검사(투명 · 글자 없음 · 해상도)를 통과하면 그대로 쓰고, 아니면 참조로 새로 생성 · 리포트에 이유). 나머지 역할은 항상 참조만.

### 4-2. brief.json

```json
{
  "schema_version": 1,
  "run_id": "R20261114_153000_CombatHUD",
  "mode": "concept",
  "screen_type": "hud",
  "screen_id": "CombatHUD",
  "resolution": [1920, 1080],
  "language": "ko",
  "font": "/Game/UI/Fonts/Pretendard",
  "required_elements": [
    { "id": "UltGauge", "kind": "progress", "desc": "오의 게이지, 가득 차면 강조" },
    { "id": "ChainPanel", "kind": "panel", "desc": "체인 남은 시간 · 참가 N/4" },
    { "id": "BurstBanner", "kind": "banner", "desc": "버스트 인원 표시" },
    { "id": "UltBlockedText", "kind": "text", "desc": "'오의 불가'" }
  ],
  "dynamic_data": [
    { "id": "ult_gauge", "type": "progress", "widget": "UltGauge", "sample": 0.7 },
    { "id": "ult_ready", "type": "flag", "widget": "UltReadyGlow", "sample": false },
    { "id": "chain_panel", "type": "flag", "widget": "ChainPanel", "sample": true },
    { "id": "chain_remaining", "type": "number", "widget": "ChainTimerText", "format": "0.0", "sample": 4.2 },
    { "id": "chain_count", "type": "text", "widget": "ChainCountText", "sample": "2/4" },
    { "id": "burst_banner", "type": "flag", "widget": "BurstBanner", "sample": false },
    { "id": "burst_count", "type": "number", "widget": "BurstCountText", "format": "0", "sample": 3 },
    { "id": "ult_blocked", "type": "flag", "widget": "UltBlockedText", "sample": false }
  ],
  "static_text": [ { "widget": "UltBlockedText", "value": "오의 불가" } ],
  "style_keywords": ["dark fantasy", "gold trim", "thin frames"],
  "references": [
    { "path": "reference.png", "role": "layout", "role_source": "user" },
    { "path": "ref/mood.png", "role": "mood", "role_source": "auto", "reason": "색 · 조명만 있고 UI 요소가 없다" }
  ],
  "conflicts": [ { "between": ["text", "style"], "resolved_by": "text", "note": "…" } ],
  "binding_contract": { "class": "UAstralCombatHUDWidget", "source": "new", "bindings": ["UltGauge", "UltReadyGlow", "ChainPanel", "ChainTimerText", "ChainCountText", "BurstBanner", "BurstCountText", "UltBlockedText"] }
}
```

### 4-3. spec.json

(발췌 — 위젯 두 개와 에셋 하나만 보인다)

```json
{
  "schema_version": 1,
  "canvas": [1920, 1080],
  "profile": "hud",
  "root": "Root",
  "widgets": [
    { "id": "Root", "type": "CanvasPanel" },
    { "id": "UltGauge", "type": "ProgressBar", "parent": "Root",
      "slot": { "kind": "canvas", "anchors": [0.5, 1, 0.5, 1], "alignment": [0.5, 1], "position": [0, -64], "size": [420, 28], "z": 1 },
      "bbox_intent": [750, 988, 420, 28],
      "style": { "background": { "asset": "ult_frame", "draw_as": "box", "margin": [0.25, 0.4, 0.25, 0.4] },
                 "fill": { "procedural": { "kind": "rounded_box", "color": "#E8B54A", "radius": 6 } } },
      "binding": { "data": "ult_gauge", "kind": "progress" } },
    { "id": "ChainTimerText", "type": "TextBlock", "parent": "ChainPanel",
      "slot": { "kind": "vertical_box", "padding": [0, 0, 0, 4], "h_align": "center" },
      "bbox_intent": [1640, 120, 120, 36],
      "text": { "source": "dynamic", "data": "chain_remaining" },
      "font": { "size": 28, "weight": "bold", "color": "#FFF3D6" },
      "binding": { "data": "chain_remaining", "kind": "number" } }
  ],
  "assets": [
    { "asset_id": "ult_frame", "kind": "frame", "provenance": "codex", "size": [512, 64], "nine_slice": true,
      "prompt": "ornate thin gold frame for a horizontal gauge, transparent background, no text", "anchor": true }
  ],
  "allow_overlap": [ ["BurstBanner", "ChainPanel"] ],
  "locked": []
}
```

- `id` = WBP 의 위젯 이름(= 바인딩 이름). `bbox_intent` 는 reference 픽셀 좌표 `[x, y, w, h]` — verify 의 IoU 기준. canvas 슬롯의 `anchors` 는 `[min.x, min.y, max.x, max.y]`, `margin` 은 `[left, top, right, bottom]` 비율.
- 슬롯 종류: `canvas`(앵커 · 위치 · 크기) · `overlay` · `vertical_box` · `horizontal_box` · `uniform_grid` · `scroll` · `size_box`. 최상위 영역은 Canvas + 앵커, 영역 안은 박스 계열(프로필이 권장을 정한다).
- 위젯 타입 어휘(Phase 1): CanvasPanel · Overlay · VerticalBox · HorizontalBox · UniformGridPanel · SizeBox · Border · Image · TextBlock · ProgressBar · Button · Spacer. Phase 3 에서 ScrollBox · ListView · Slider · CheckBox · ComboBoxString · 하위 WBP(`repeat`).
- `locked` — 역추출이 지원하지 않는 위젯 · 속성(§6 `export_widget_spec` 의 `unsupported[]`). patch 가 건드리면 **브리지가 거부**한다(LLM 이 지키는 규칙이 아니다).

### 4-4. spec patch

```json
{
  "schema_version": 1,
  "base_revision": "sha1:…",
  "source": "fix",
  "ops": [
    { "op": "set", "widget": "UltGauge", "path": "slot.position", "value": [0, -72], "reason": "IoU 0.61 — 너무 아래" },
    { "op": "replace_asset", "asset": "ult_frame", "regenerate": true, "reason": "OCR 에 글자 검출" },
    { "op": "add_widget", "widget": { "id": "UltReadyGlow", "type": "Image", "parent": "UltGaugeOverlay" }, "index": 1 },
    { "op": "remove_widget", "widget": "OldDecor" },
    { "op": "move", "widget": "ChainCountText", "parent": "ChainPanel", "index": 0 }
  ]
}
```

- `base_revision` 이 지금 WBP 의 revision 과 다르면 `REVISION_MISMATCH` 로 무변경(사람이 그사이 고쳤다는 뜻 — 수정 모드는 다시 역추출부터).
- op 종류가 §2-2 재시도 분기를 정한다. 바인딩 위젯의 `remove_widget` 은 거부된다(바인딩은 추가만).

### 4-5. manifest.json · report.json · 지표 JSONL

```json
{ "assets": [ { "asset_id": "ult_frame", "file": "assets/final/ult_frame.png", "sha256": "…", "size": [512, 64],
    "alpha": true, "nine_slice_margin": [0.25, 0.4, 0.25, 0.4], "ocr_text": "", "provenance": "codex",
    "backend": "codex", "prompt": "…", "anchor": true, "ue_path": "/Game/_AutoGen/R…/T_ult_frame",
    "compression": "TC_EditorIcon" } ] }
```

```json
{ "run_id": "R…", "parent_run_id": null, "status": "pass", "attempt": 2,
  "gates": [ { "name": "iou_leaf_min", "value": 0.78, "threshold": 0.70, "pass": true } ],
  "recorded": { "delta_e_region_mean": 6.1, "style_sim_anchor": 0.82 },
  "fixes": [], "unsupported": [], "durations_s": { "generate": 212.4, "build": 6.1 } }
```

`metrics/uigen.jsonl` 한 줄 = 에셋 하나 또는 run 하나: `run_id · asset_id · kind · backend · ok · duration_s · retries · verify · style_sim_anchor` (+ comfy: `workflow_sha256 · model_sha256 · lora_sha256[] · seed`, codex: `codex_version`). Phase 1 부터 쓰고, 집계는 Phase 2.

---

## 5. 화면 종류 프로필 (`profiles/*.yaml`)

| 항목 | hud | menu (장비 · 인벤토리 · 상점) | options | dialog |
| :--- | :--- | :--- | :--- | :--- |
| 배경 | 없음(투명) | 전체 화면 패널 | 전체 또는 중앙 패널 | 반투명 막 + 중앙 패널 |
| 앵커 | 화면 가장자리 · 세이프존 안 | 영역 단위 | 영역 단위 | 중앙 |
| analyze 주의 | **reference 뒤의 게임 장면과 UI 분리** — 장면을 에셋으로 만들지 않는다 | 반복 슬롯 = 그리드 + 템플릿 | 표준 컨트롤(Slider · CheckBox · ComboBox) | 버튼 행 |
| verify 영역 | UI bbox 합집합만 비교(장면 제외) | 전체 | 전체 | 패널 |
| 작은 요소 | 많음 → 중심점 거리 기준 | 슬롯 아이콘 | 적음 | 적음 |
| Phase | 1 | 2 보정 세트 · 3 | 2 보정 세트 · 3 | 3 |

---

## 6. UE 쪽 도구 — `WidgetMcp`

모든 쓰기 도구는 코어의 공통 가드를 받는다: 쓰기 허용 경로 `WidgetOutputPaths=/Game/_AutoGen/`(밖이면 `OUTPUT_PATH_NOT_ALLOWED`) · 덮어쓰기 거부 · 호출 전후 전역 더티 비교(`UNEXPECTED_DIRTY`) · `save` 기본 false. 지금 생성 Tool 이 쓰는 방식과 같다 [소스] `Plugins/AnimGraphMcp/README.md:49-51`.

| Tool | 하는 일 | 안전장치 · 엔진 근거 |
| :--- | :--- | :--- |
| `import_ui_textures` | PNG 묶음 임포트 + UI 설정: 압축 `TC_EditorIcon`(기본, 종류별 `TC_BC7`) · `TEXTUREGROUP_UI` · `TMGS_NoMipmaps` · `NeverStream` · sRGB | [소스] `TextureDefines.h:46,156,400` · `NeverStream` 은 `UStreamableRenderAsset` 의 비트필드 `StreamableRenderAsset.h:299`. 임포트 경로는 기존 Interchange 사용 — **[1a-2 실측] 동기 · 기본 텍스처 파이프라인 복제 + `bAllowNonPowerOfTwo=true`**(§11 1a-2) |
| `create_ui_material_instances` | UI 도메인 머티리얼 인스턴스(procedural 그라데이션 · 마스크) | Phase 1b |
| `create_widget_blueprint` | 부모 클래스(스텁)로 빈 WBP 생성 | `UWidgetBlueprintFactory`(MinimalAPI — `ParentClass` 프로퍼티 · 가상 `FactoryCreateNew`) [소스] `WidgetBlueprintFactory.h:13-29` · 기본 루트 위젯 [P0 결과] 없음 → Canvas 를 직접 만들고 `OnVariableAdded` (§12-1 A7) |
| `preview_widget_spec` / `apply_widget_spec` | **조정기** — 지금 WBP 와 목표 spec 의 차이를 op 로 계산 → 전체 사전 검증 → 배치 적용(되돌리기 저널) → 컴파일. `expected_revision` 필수 | 위젯 생성 `UWidgetTree::ConstructWidget<T>(Class, Name)` [소스] `WidgetTree.h:102`. **GUID 맵:** 위젯 추가 · 이름 변경 · 제거마다 `UWidgetBlueprint::OnVariableAdded / OnVariableRenamed / OnVariableRemoved` 를 부른다 [소스] `WidgetBlueprint.h:259-261`. 맵이 비어 있는 새 WBP 는 컴파일러가 결정적 GUID 로 채우지만, 비어 있지 않은 WBP 에 그냥 더하면 `ensureAlways` 가 터진다 [소스] `WidgetBlueprintCompiler.cpp:769,794` |
| `apply_widget_patch` | spec patch 를 조정기로 적용(`locked` 거부 · 바인딩 제거 거부) | 위와 같음 |
| `export_widget_spec` | WBP → spec + `unsupported[]` + `revision`(정규화 spec 의 SHA1) | 사람이 고친 것도 그대로 읽는다 |
| `compile_widget_blueprint` · `save_widget_run` | 컴파일(오류 · BindWidget 누락 보고) · run 패키지 일괄 저장 | 저장은 finalize 에서만 |
| `render_widget` | 오프스크린 렌더 → PNG + **같은 그리기에서** 이름 있는 위젯 전부의 geometry | `FWidgetRenderer::DrawWidget(RenderTarget, SWidget, Scale, DrawSize, DeltaTime)` [소스] `Slate/WidgetRenderer.h:75` · `UWidget::GetPaintSpaceGeometry()` [소스] `Widget.h:786`. Scale 을 직접 주므로 DPI 곡선이 끼지 않는다. 폰트 · 텍스처 로딩 때문에 두 번 그린다 [P0 결과 — 에디터 안에서는 첫 그림부터 같았다, 두 번 그리기는 안전장치로 유지] · geometry 오차 0 px · **감마 조합 주의(§12-1 A6-색)**. 출력은 PNG 출력 경로 제한 안 새 폴더만 |
| `list_bind_widgets` | 클래스의 BindWidget 목록(선택 여부 포함) | `IsBindWidgetProperty` [소스] `WidgetBlueprintEditorUtils.h:104` |
| `discard_run_packages` | 저장 안 한 `/Game/_AutoGen/<run_id>/` 패키지 폐기 | 그 경로 밖 거부 |
| `promote_widget` | run 결과를 `/Game/UI/<기능>/` 로 복사(원본 run 은 그대로) | `promote_animation` 과 같은 방식 · Phase 4 |

`get_editor_status` 에 `widget` 섹션(허용 경로 · 폰트 · 렌더 출력 루트)을 더한다.

---

## 7. 이미지 생성 백엔드 — `generate_ui_asset`

```yaml
# Tools/uigen/config/routing.yaml (잠정)
kinds:
  icon:       { primary: codex, fallback: [], anchor: codex, retry_backend: codex }     # Phase 5 에서 comfy A/B
  frame:      { primary: codex, fallback: [procedural], retry_backend: codex }
  panel_bg:   { primary: procedural, fallback: [codex] }
  fill:       { primary: procedural }                                                  # RoundedBox · UI 머티리얼
  ornament:   { primary: codex, fallback: [] }
  mockup:     { primary: codex }                                                       # text / multi_ref 의 목업
limits: { codex_calls_per_run: 20, on_quota: pause }      # pause | fallback_if_listed
```

- **procedural:** RoundedBox 브러시 · UI 머티리얼은 텍스처 없이 spec 의 브러시로 끝난다. SVG 는 Python 에서 래스터화(resvg 계열 의존성 [P0]).
- **codex:** `npm i -g @openai/codex@<고정 버전>` 으로 설치하고 `pipeline.yaml` 에 경로 · 기대 버전을 적는다(매 run 시작 때 `codex --version` 확인).
  - [실측] PATH 에 없다. 앱이 `%LOCALAPPDATA%\OpenAI\Codex\bin\codex.exe`(`0.130.0-alpha.5`, 해시 하위 폴더 포함)를 번들하지만 앱 업데이트 때 경로 · 버전이 바뀐다.
  - 호출: `codex exec -C <work/…/gen/<asset_id>> -s workspace-write --json -o last.txt -i <참조>… "<프롬프트>"` — [실측] 번들 버전에 `-i`(여러 장) · `--json` · `-o` · `-s` · `-C` 있음.
  - 프롬프트는 `$imagegen` **built-in `image_gen` 만**(API 키 경로 금지) · 투명 배경 · 글자 없음을 명시한다. built-in 은 키가 필요 없고 플랜을 쓴다 [실측] `~/.codex/skills/.system/imagegen/SKILL.md:14-15`.
  - **저장 위치를 지정할 수 없다** — 결과가 `$CODEX_HOME/generated_images/...` 에만 생긴다 [실측] 같은 파일 `:33-36`. `--json` 이벤트에서 세션을 찾아 그 파일을 work 로 복사한다 [P0]. 그래서 **codex 호출은 한 번에 하나**(동시에 돌리면 어느 파일이 어느 요청 것인지 모른다).
  - codex 프로세스 환경에는 `OPENAI_API_KEY` 를 넣지 않는다(유료 CLI 폴백 차단). 한도 초과 메시지 형태는 [P0] 에서 채록해 `quota` 판정에 쓴다.
  - **[P0 결과] (11-14, npm `@openai/codex@0.166.0` — 사용자 승인, `codex-cli 0.166.0`)**
    - 로그인: `codex login status` → `Logged in using ChatGPT` — npm 판도 `~/.codex` 로그인을 같이 쓴다(A2 참). `OPENAI_API_KEY` 는 환경에 없음을 확인하고 실행.
    - 1장 생성: `codex exec -C <dir> --skip-git-repo-check -s workspace-write --json -o last.txt "<built-in image_gen 만 · 투명 · 글자 없음 · 생성 뒤 cwd 로 복사>"` — 내장 `image_gen` 이 비대화형에서 돈다(A1 참). 결과 2172×724 RGBA PNG(357 KB), 완전 투명 픽셀 89.9 %, 글자 없음, 프롬프트대로 금색 게이지 프레임(사람 눈 확인).
    - **결과 찾기:** 파일은 `~/.codex/generated_images/<thread_id>/exec-<uuid>.png` — 폴더 이름이 `--json` 첫 이벤트 `thread.started.thread_id` 와 같다. 이벤트 흐름에 image_gen 항목은 따로 나오지 않았다(`agent_message` · `command_execution` 만). → generate 는 `thread_id` 로 폴더를 집고, 없으면 실행 전후 `generated_images` 차이로 대신한다(직렬 실행 전제 그대로).
    - 비용 · 시간: `turn.completed.usage` 입력 91,703(캐시 79,744) · 출력 508 토큰 — 대부분 에이전트가 imagegen `SKILL.md` 를 읽은 몫이다. 프롬프트에 '스킬 문서를 읽지 말 것'을 넣어 줄일 여지.
    - 함정: 출력 맨 앞에 `Reading additional input from stdin...` — stdin 이 열려 있으면 기다릴 수 있으니 오케스트레이터는 stdin 을 닫고(`DEVNULL`) 부른다.
    - **한도(A3) — 재현 안 함.** [바이너리] codex.exe 안에 `usage_limit_reached` · `quota_exceeded` · `usage_not_included` · `rate_limit_exceeded` 식별자와 `Try again at …` 문구가 있다. `quota` 판정은 `--json` 오류 이벤트에서 이 식별자를 찾고, 없으면 연속 실패 횟수로 추정(§12-1 '틀리면' 그대로). 실제 이벤트 모양 · 종료 코드는 한도에 걸렸을 때 채록.
- **comfy (Phase 5):** SDXL급 + 스타일 참조(앵커 이미지). 실행마다 워크플로 JSON · 모델/LoRA 해시 · 시드를 기록. generate 동안 에디터를 내린다(12 GB 공유).
- **provided:** `use: auto/asset` 인 component 이미지 — 같은 refine · 검사를 거치고 출처 · 해시를 기록.
- **구조 재사용:** `Tools/mcp/anim_gen` 의 `router.py` · `fallback.py` · `policy.py` · `store.py` · `selection.py` 와 같은 모양으로 `Tools/uigen/gen/` 을 짓는다(import 로 묶지 않고 구조만 따른다).

**refine (코드):** 배경 제거(투명이 아니면) · 여백 자르기 · 크기 맞춤 · 9-slice margin 추정(가장자리에서 늘려도 되는 균일 띠 검출) · **OCR 로 구운 글자 검출**(결정 6 — 검출되면 재생성) · 알파 검사.

---

## 8. 검증

### 8-1. 합격 게이트 (Phase 1 부터)

| 게이트 | 기준(잠정) |
| :--- | :--- |
| 컴파일 | 오류 0 |
| 바인딩 | 계약의 필수 바인딩 전부 존재 · 타입 일치 |
| 텍스처 설정 | 압축 · 그룹 · 밉 · 스트리밍이 manifest 와 일치 |
| 화면 밖 | 0 — 1920×1080 + 21:9(2560×1080) · 16:10(1920×1200) 두 비율에서도 |
| 의도치 않은 겹침 | 0 — `allow_overlap` 밖에서 형제 위젯 bbox 교차 면적 > 4 % |
| 필수 요소 | brief 의 `required_elements` 전부 존재 |
| 배치 — 영역 | 최상위 영역 IoU ≥ 0.85 |
| 배치 — 말단 | 말단 위젯 IoU ≥ 0.70 · **48 px 미만은 중심점 거리 ≤ 8 px** |
| 구운 글자 | 생성 에셋 OCR 검출 0 |
| 수정 회귀(수정 모드) | patch 밖 위젯의 geometry 차이 ≤ 1 px · 스타일 spec 동일 |
| 왕복(Phase 1a) | spec → WBP → spec 이 정규화 후 같음 |

### 8-2. 기록만 (Phase 2 에서 보정 후 게이트로 올림)

| 지표 | 잠정 목표 | 비고 |
| :--- | :--- | :--- |
| 영역 대표색 ΔE00 | 평균 ≤ 10 | reference vs render, 영역 마스크 |
| 스타일 유사도 | 앵커 / style 이미지 대비 — 보정 뒤 결정 | 모델(CLIP · DINOv2 · 스타일 전용) 선택도 Phase 2 |
| component 유사도 | target 위젯 잘라낸 것 vs component 이미지 | |
| 전체 지각 유사도 | 기록만 | 글자 · 자리표시가 달라 게이트로 부적합 |

### 8-3. LLM verifier

- 별도 `claude -p` — 입력은 reference.png · render.png · spec(위젯 이름) · 실패 게이트 목록, 출력은 `fixes.json`(스키마: 위젯 · 문제 · 근거 · 제안 op). 합격 판정에는 쓰지 않는다.
- fix 단계가 fixes 를 spec patch 로 바꾼다. verifier 와 fix 를 나누는 이유: 보는 눈(비교)과 고치는 손(patch)을 분리해, verifier 가 자기 수정안을 변호하지 않게 한다.

---

## 9. 안전장치 — 요구사항별 구현

| 요구 | 구현 |
| :--- | :--- |
| `/Game/_AutoGen/<run_id>/` 에만 생성 | `WidgetOutputPaths` 허용 목록 + 전역 더티 비교 — 기존 생성 가드 재사용 |
| 기존 에셋 덮어쓰기 · 삭제 금지 | `ProtectedPaths` · 덮어쓰기 거부 · 수정도 새 run 폴더 · 폐기는 저장 안 한 이번 run 패키지만 |
| 사전 검증 + 롤백 | preview / apply 분리 · 배치 원자성(되돌리기 저널 + `rollback_verified`) [소스] `Plugins/AnimGraphMcp/README.md:245-249` · 저장 지연 |
| 조회 뒤 변경 감지 | `expected_revision` = 정규화 spec 의 SHA1 → `REVISION_MISMATCH` |
| C++ 쓰기 | §3-3 소유 규칙 |
| 권한 허용 목록 | `claude -p "<프롬프트>" --permission-mode dontAsk` + `--allowedTools "Read" "Edit(work/<run_id>/**)"`(cwd 기준 상대 경로 — [P0 결과] 실측으로 밖 쓰기 거부 확인, §10-1) · Bash 없음 · `--strict-mcp-config` 로 MCP 없음. `--dangerously-skip-permissions` 금지 |
| 단계 상한 | `--max-budget-usd`(단계별) + 벽시계 타임아웃 + 재시도 N + run 당 codex 호출 상한 |
| Stop 훅 | 여러 파일을 쓰는 단계(normalize-text)만 — 출력 파일 검사, `stop_hook_active` 면 통과, 막을 때 exit 2 |
| 공식 CLI 만 | codex exec 만 · 내부 엔드포인트 호출 없음 · `OPENAI_API_KEY` 비움 · `--dangerously-bypass-approvals-and-sandbox` 금지 |
| 시크릿 | 브리지 토큰 헤더 · 환경 변수를 로그에서 가림 · `~/.codex/auth.json` 은 읽지 않음 |

---

## 10. `claude -p` 운용 · `.claude/` 구성

### 10-1. LLM 단계 호출 틀

```text
claude -p "<단계 지시>"
  --permission-mode dontAsk --allowedTools "<단계별 허용>"
  --strict-mcp-config --mcp-config config/empty_mcp.json
  --setting-sources project --settings claude_ctx/.claude/settings.json
  --output-format json --json-schema schemas/<stage>.json
  --max-budget-usd <단계별> --append-system-prompt-file prompts/<stage>.md
  [--model <pipeline.yaml 의 단계별 값 — 기본은 사용자 기본 모델>]
  (cwd = Tools/uigen/claude_ctx, 벽시계 타임아웃은 오케스트레이터가)
```

- [실측] 2.1.177 에 위 플래그가 모두 있다. `dontAsk` 는 허용 목록 밖을 묻지 않고 거부한다.
- `--bare` 는 훅 · auto-memory · CLAUDE.md 를 끄지만 **OAuth 를 읽지 않아(API 키만) 구독 인증이면 못 쓴다** [실측]. 대신 cwd 를 `claude_ctx/` 로 두고 auto-memory 를 settings 로 끈다(키 `autoMemoryEnabled` — [P0 결과]). 저장소 CLAUDE.md 는 상위 탐색으로 읽히는데 짧아서 감수한다.
- `--json-schema` 결과가 JSON 출력의 어느 필드에 담기는지 — [P0 결과] `structured_output`(아래).
- **[P0 결과] (11-14 — 바이너리는 2.1.177 에서, 런타임은 사용자 로그인 뒤 자동 업데이트된 2.1.325 · haiku 호출 3번, 합계 약 $0.02)**
  - **전제:** 독립 실행 `claude`(`~/.local/bin/claude.exe`)는 데스크톱 앱 인증과 따로 로그인해야 한다(Claude 구독 계정 — Console API 키를 고르면 토큰 과금). 로그인 전에는 `{"type":"result","is_error":true,"result":"Not logged in · Please run /login","total_cost_usd":0}` 을 돌려주고 끝난다(비용 0). 파이프라인 시작 검사에 넣는다. 자동 업데이트로 버전이 바뀌므로 `pipeline.yaml` 에 기대 버전을 적고 run 시작 때 `claude --version` 을 기록한다.
  - `--json-schema` 출력 **[실측]**: `--output-format json` 결과 `{"type":"result","subtype":"success","structured_output":{"answer":"ok","n":3},"result":"{…}"}` — 오케스트레이터는 `structured_output` 을 읽고, 없거나 `is_error` 면 실패 처리. [바이너리] 재시도 · 실패 표식 `structured_output_retries` · `structured_output_failure` 도 있다.
  - `--max-turns` **[실측]**: 동작한다(§1 #11 — `error_max_turns`).
  - auto-memory 끄기: 설정 키 **`autoMemoryEnabled: false`**(설정 스키마 · [바이너리]). 끈 효과 자체는 init 이벤트에 드러나지 않아 동작은 미관측 — 프롬프트 · 결과에 메모리 내용이 섞이는지는 Phase 1b 첫 run 에서 본다.
  - **`--setting-sources project` = cwd [실측]:** cwd(저장소 안 `…/claude_ctx/`)의 `.claude/settings.json` 에 둔 `deny: ["Read(note.txt)"]` 가 걸렸다(`File is in a directory that is denied by your permission settings.`) — 저장소 루트 설정에는 없는 규칙이다. 루트 설정이 **같이** 읽히는지는 이 시험으로 가를 수 없다 → 계획대로 단계 권한은 `--settings` · `--allowedTools` 로 명시하고 루트 설정에 기대지 않는다.
  - **경로 권한 규칙 [실측]:** `--permission-mode dontAsk --allowedTools "Edit(work/**)"` 에서 `Write` 로 `work/inside.txt` 는 써지고 cwd 의 `outside.txt` 는 `Permission to use Write has been denied because Claude Code is running in don't ask mode` 로 막혔다 — **상대 경로는 cwd 기준**이고 `Write` 도 `Edit(path)` 규칙으로 판정된다(설정 스키마의 `Write(path)` 무시와 일치). → 단계 허용은 `--allowedTools "Read" "Edit(work/<run_id>/**)"` 로 충분, PreToolUse 경로 훅은 대비책으로만. 거부 메시지가 '다른 도구로 해 봐도 된다'고 유도하므로 Bash 등은 허용 목록에 넣지 않는다(설계 그대로).
  - **함정 [실측]:** `--allowedTools` 는 값을 여러 개 받는 옵션이라 뒤에 오는 위치 인자(프롬프트)까지 도구 이름으로 삼킨다 → 프롬프트는 `-p "<프롬프트>"` 처럼 맨 앞에 두거나 stdin 으로 준다. `--output-format stream-json` 의 마지막 줄은 결과가 아니라 `system/task_summary` 일 수 있어 `type:"result"` 를 찾아 읽는다.

### 10-2. `.claude/` 구성

| 위치 | 구성 | 용도 |
| :--- | :--- | :--- |
| 저장소 `.claude/skills/` | `ue-umg-authoring` — GUID 맵 · FWidgetRenderer · 텍스처 설정 · BindWidget · UHT 헤더 이름 등 부딪힌 엔진 제약 | 개발 세션(플러그인 구현) |
| 저장소 `.claude/skills/` | `uigen-run` — 파이프라인 돌리는 법 · 리포트 읽는 법 · 에디터 주기 | 개발 · 운용 세션 |
| 저장소 `settings.local.json` | `run_pipeline` · pytest 실행 허용 규칙(CLAUDE.md 의 모양 규칙대로) | 프롬프트 없이 돌게 |
| `Tools/uigen/claude_ctx/.claude/settings.json` | 권한(Bash 거부 · 쓰기 경로 제한) · auto-memory 끔 · Stop 훅 등록 | LLM 단계 |
| `Tools/uigen/claude_ctx/.claude/skills/` | `uigen-spec` — spec 어휘 · 프로필 규칙 · 좌표 규약 | analyze · fix |
| `Tools/uigen/claude_ctx/.claude/hooks/` | `check_outputs.py`(Stop) | normalize-text |
| agents | 두지 않는다 — verifier 는 별도 호출, 서브에이전트는 사용자 요청 때만(프로젝트 방침) | |

기존 스킬 3종(`astral-ue-*`)은 Python 원격 실행에 기대는데, 에디터 안 원격 실행은 지금 불통이다(프로젝트 실측). 파이프라인은 HTTP 브리지만 쓴다.

---

## 11. Phase 계획

| Phase | 내용 | 끝 조건 | 검증 |
| :--- | :--- | :--- | :--- |
| **0** | (a) 플러그인 분리 §3-1 — 코어 추출 → StateTree 이전, WidgetMcp 는 뼈대만(스파이크 코드를 둘 자리) (b) 스파이크: codex 설치 · 1장 생성 · 결과 찾기 · 한도 메시지 / `claude -p` 플래그 · 스키마 출력 필드 · 경로 권한 규칙 · auto-memory 끄기 / 손 spec 으로 WBP 생성 · `ConstructWidget` · 렌더 · geometry / 텍스처 임포트 설정 / 새 WBP 기본 루트 | 기존 회귀 통과 + 스파이크 보고(§12 가정 확정) | 빌드 2회 · `AnimGraphMcp.*` · pytest · 통합 1개 |
| **1a** | 손으로 쓴 M4 HUD spec → codegen → build → verify → 재시도, procedural 에셋만. 역추출 왕복 · JSONL 기록 시작 | 게이트 통과 · 왕복 일치 · codegen 해시 건너뛰기 확인 | pytest + 에디터 1회 실행 |
| **1b** | M4 HUD 컨셉아트 → analyze → codex 에셋 → 끝까지 1회 성공 | 무인 1회 통과 + 리포트 | 실제 run · 사람 눈 확인(화면) |
| → M4 C | 스텁 `UAstralCombatHUDWidget` 에 게이지 · 체인 연결(개발 세션) | M4 설계 §5 화면 동작 | M4 방침 |
| **2** | 집계 스크립트 + 임계값 보정(HUD · 장비창 · 옵션 5 ~ 10장) | 기록 지표 중 게이트로 올릴 것 결정 | 보정 리포트 |
| **3** | text · multi_ref(목업 K장 · 선택) + 리스트 · 표준 컨트롤 · 하위 WBP | 각 모드 1회 통과 | 실제 run |
| **4** | 수정 모드 — 지시 해석 · 주석 스크린샷 → 위젯 매핑(렌더 geometry 로) · lineage · 되돌리기 · 승격 | 수정 회귀 게이트 통과 | 실제 run |
| **5** | ComfyUI 연결 · 아이콘만 codex 와 A/B | A/B 리포트 | 실제 run |
| **6** | 지표 기반 라우팅 규칙(종류별 최소 표본 수 넘을 때만) | 규칙 반영 | 리포트 |

**Phase 1a 하위 단계 (11-14 사용자 승인 — 단계마다 보고 → 승인 뒤 다음)**

| 단계 | 범위 | 단계 검증 | 상태 |
| :--- | :--- | :--- | :--- |
| 1a-1 | `Tools/uigen` 뼈대 · JSON Schema 6종 · 설정 · `profiles/hud` · 손 brief/spec(`fixtures/m4_combat_hud`) · spec 정규화 · 왕복 비교 · patch · procedural PNG · run 잠금 · 지표 JSONL · `.gitignore` 3줄 | pytest | **끝(11-14)** — pytest 76 통과, 손 spec run 이 normalize → generate → refine 까지(나머지는 미구현 표시로 incomplete) |
| 1a-2 | WidgetMcp 도구 — 텍스처 임포트 경로 확인(첫 작업) → create → 조정기 preview/apply · patch → export → compile · list_bind_widgets → render(감마 LUT · 3 해상도) → save · discard, `quit_editor` 선택 인자, `widget_mcp` 창구 | DebugGame 빌드 + `WidgetMcp.*` + 브리지 스모크 | **끝(11-14)** — Tool 11개, `WidgetMcp.*` 5/5, 손 spec 스모크(왕복 차이 0 · bbox 오차 0 px · 3 해상도 화면 밖 0), `quit_editor` 두 경로 확인 |
| 1a-3 | codegen(템플릿 · 계약 해시 · 소유 규칙) · UBT 빌드 · 에디터 재기동 | pytest + 실제 생성 · 빌드 1회 + 같은 spec 건너뜀 | **끝(11-14)** — pytest 96 통과(codegen 20). 실제 run: C++ 4개 생성 → DebugGame 빌드 22.4초(`Result: Succeeded`) → 재기동(브리지 12.4초 + 30초) → `list_bind_widgets` = 계약 8개. 같은 spec 재실행은 codegen `skipped`(0.46초, 빌드 · 재기동 없음). 같은 에디터에서 스텁 부모 WBP 생성 `compile.ran=false` → spec 적용 컴파일 ok · `missing_bindings` 0 · 왕복 일치 → 폐기 |
| 1a-4 | verify 게이트 · 재시도 분기(결정적 fixer) · finalize · report · 지표 | pytest + 깨뜨린 run 1회가 재시도로 통과 | **끝(11-14)** — pytest 142 통과(새 46: 게이트 계산 · fixer · 재시도 분기 · 조기 종료 · 상한 · generate/codegen 분기 · 가짜 claude CLI). 실제 run(DebugGame 에디터 — build 가 기동, 브리지 12.8초 + 30초): 손 spec 첫 시도 게이트 10/10 · 왕복 일치 · `Content/_AutoGen/<run_id>/` 4개 저장 · 지표 줄(`R20261114_235335`). `--inject-fault offscreen`(`R20261114_235343`) · `overlap` · `drift` 모두 시도 1 실패 → 정정 patch 1 op → build → 시도 2 통과 · 저장. 첫 offscreen run 은 컬링 함정(아래)으로 조기 종료 · 폐기 — 고친 뒤 통과 |
| 1a-5 | Phase 끝 검증(빌드 2 · 에디터 1회 · pytest · 색 눈 확인) · 문서 | 끝 조건 4개 | **끝(11-15)** — 빌드: DebugGame `Result: Succeeded`(이미 최신) · Development `-DisableAdaptiveUnity` `Result: Succeeded`(26.6초 · 18 작업 · 적응형 제외 0 — 새 cpp 를 유니티 묶음에 넣어도 충돌 없음). pytest 142 통과. 에디터 1회(DebugGame): `AstralBreak.` 55/55(먼저, 415초) → `EditorMcpCore.` 2/2 · `WidgetMcp.` 5/5 → 정상 run `R20261115_001147` 시도 1 에 게이트 10/10 · 왕복 일치 · codegen `skipped` · 지표 4줄(아래 요약) → `quit_editor` · 소멸 확인. 렌더 색 사람 눈 통과(§12-1) |

1a-1 에서 정한 구체 규칙(설계 초안 §4 를 구체화한 것):
- **spec 브러시 모양:** `{draw_as: image|box|border|rounded_box|none, asset?, color(틴트), margin?(9-slice), image_size?, radius?, outline_color?, outline_width?}` — §4-3 예시의 `fill.procedural{kind: rounded_box}` 대신 `fill: {draw_as: rounded_box, color, radius}`. 텍스처 없는 procedural 채움은 브러시 자체가 담는다.
- **슬롯 kind 는 부모 타입이 정한다** — `canvas` · `overlay` · `vertical_box` · `horizontal_box` · `uniform_grid` · `border` · `size_box` · `button`(Border · SizeBox · Button 의 자식 슬롯도 따로 둔다).
- **정규화 기본값:** 생략한 스칼라 = `core/spec.py` 표(5.7.4 UMG 생성자 기본값 — 예: Border 슬롯 padding (4,2) `BorderSlot.cpp:18`, Overlay 슬롯 Left/Top `OverlaySlot.cpp:15`, 박스 슬롯 Automatic `VerticalBoxSlot.cpp:19`, TextBlock Roboto 24 Bold `TextBlock.cpp:35`), 생략한 브러시 = 엔진 기본 스타일(CDO). 파이프라인은 정규화한(전부 명시한) spec 을 브리지에 보내므로 표와 엔진 값이 어긋나도 파이프라인 왕복은 깨지지 않는다. 브러시 `image_size` 기본 = 그 에셋 크기(9-slice 두께가 이 값에 달려 있다).
- **왕복 투영:** `bbox_intent` · `binding` · `note` 는 WBP 가 담지 않아 뺀다. 글자는 정적/동적 구분 없이 값(동적이면 sample)만. 역추출의 브러시 asset(UE 경로)은 manifest `ue_path` 로 asset_id 에 되돌려 비교.
- **겹침 게이트:** Overlay 자식끼리는 겹치는 것이 정의라 빼고(`profiles/hud.yaml stacking_parents`), '48 px 미만' = min(w, h) < 48.
- **지표 JSONL** 은 성공 · 실패 · 미완 모든 run 끝에 run 한 줄 + manifest 에셋마다 한 줄(1a-1 부터 기록 중).

1a-2 에서 확인 · 정한 것 (11-14):
- **텍스처 임포트 경로 [실측]:** Interchange `ImportAssetWithResult` 는 동기다(`InterchangeManager.cpp:1720-1726`). PNG 는 기본 'Textures' 스택(`/Interchange/Pipelines/DefaultTexturePipeline`, `UInterchangeGenericTexturePipeline`)을 탄다. **함정: 그 파이프라인의 `bAllowNonPowerOfTwo` 기본값이 false** 라 200×50 같은 UI 텍스처를 걸러 낸다(`InterchangeGenericTexturePipeline.h:70`) → 트랜지언트로 복제해 true · 노멀맵 감지 끔 · UDIM 끔 · `AssetName` 지정. 임포트 뒤 압축 · 그룹 · 밉 · NeverStream · sRGB 를 넣고 `PostEditChange` + `FTextureCompilingManager::FinishCompilation`(렌더 전에 빌드를 끝낸다). 손 spec 의 3장: 200×50 · 320×160(BC7) · 256×32 모두 크기 유지 · 설정 manifest 와 일치, 한 장 0.01초.
- **조정기 적용 방식(설계 §6 '되돌리기 저널' 대신):** WidgetTree 를 트랜지언트로 복제해 거기에 적용 → 사본을 역추출해 정규화한 목표와 같은지 확인 → 같을 때만 WBP 의 WidgetTree 와 바꿔 끼우고 GUID 맵을 이름 차이로 맞춘다. 실패하면 원본을 손대지 않아 `rollback_verified`(revision 불변)가 구조로 보장된다. 지운 위젯은 트랜지언트 패키지로 이름을 옮겨 같은 이름을 다시 쓸 수 있게 한다.
- **revision** = (부모 클래스 경로 + 역추출 트리)의 정규 JSON(키 정렬 · 수 소수 셋째 자리) SHA1. 같은 spec 을 다시 적용하면 op 0 · revision 그대로(멱등) [실측].
- **`quit_editor` 선택 인자 `discard_only_under`**(패키지 접두 배열): `discard_dirty` 와 함께 주면 그 밖의 더티가 하나라도 있을 때 `DIRTY_PACKAGES`(details `outside_discard_only_under`)로 거절. 인자가 없으면 기존 동작 그대로. 파이프라인은 `pipeline.yaml editor.quit_discard_only_under: [/Game/_AutoGen/]` 를 넘긴다.
- **생성 때 컴파일:** 부모에 필수 BindWidget 이 있으면(스텁) 빈 캔버스는 컴파일될 수 없으므로 건너뛰고 `compile.ran=false` — apply 가 컴파일한다.
- **렌더 [실측]:** 1920×1080 에서 손 spec 위젯 14개 geometry 가 `bbox_intent` 와 오차 0 px, 2 · 3 해상도(2560×1080 · 1920×1200)에서 화면 밖 0, 그림 1 · 2 픽셀 차이 0. 색 탐침: 배너 `#2A1A0ACC` 를 검은 바탕에 얹은 값 `#221508` 이 그대로 나옴(감마 LUT 확인). 1920×1080 세 장 0.2초.
- **함정 [실측]:** UE 전역 `MakeError`(TValueOrError) 템플릿이 ADL 로 같은 이름의 우리 함수를 이긴다 → `MakeMcpError`. `PI` 는 엔진 매크로라 변수 이름으로 못 쓴다.

1a-3 에서 확인 · 정한 것 (11-14):
- **계약:** 바인딩마다 `{name, widget_class, data, kind, format?, optional, setter}` + 모듈 · 클래스 이름 + 생성기 식별자(버전 + 템플릿 4개 · setter 조각의 해시 — 템플릿이 바뀌어도 다시 생성). 해시 = 정규 JSON 의 SHA1. 생성 헤더 1줄째 표식, 2줄째 해시, 3줄째 계약 JSON(다음 run 의 '추가만' 판정 원천), cpp 는 표식 + 해시. 해시 줄과 계약 줄이 어긋나면 `CODEGEN_HEADER_CORRUPT`.
- **추가만 구체화:** spec 에서 빠진 바인딩은 `BindWidgetOptional` + setter 유지. 같은 이름의 위젯 클래스가 바뀌면 거부(`BINDING_RETYPE` — 옛 WBP 는 이름으로 묶임). data · kind · format 변경은 허용(setter 가 바뀐다 — 스텁이 옛 setter 를 부르면 빌드가 실패해 원복된다). setter 의 정체성은 data id — 같은 data 를 새 바인딩이 쓰면 빠진 쪽은 setter 를 잃는다(위젯 이름을 바꿔도 사람 코드의 `SetX` 가 새 위젯을 움직임). setter 이름 · 위젯 이름 충돌은 거부.
- **setter 세부:** flag 보이기 = `SelfHitTestInvisible`(Button 만 `Visible`) · 숨김 = `Collapsed`. number `0` = `int32` · 자릿수 묶음 없음, `0.0…` = `float` · 소수 자릿수 최소 = 최대. progress 는 0 ~ 1 로 자른다. 전부 `UFUNCTION(BlueprintCallable, Category="uigen|<화면>")` · 선택 바인딩 대비 null 검사. 매개변수 이름이 `UUserWidget` · `UWidget` · `UVisual` 멤버와 겹치지 않음을 엔진 헤더로 확인(가림 경고 = 오류).
- **건너뛰기:** 해시가 같고 스텁이 있으면 건너뛴다. 에디터가 떠 있으면 `list_bind_widgets` 로 리플렉션만 대조하고, 다르면(낡은 바이너리) 쓰기 없이 빌드 · 재기동(`reason: stale_binary`).
- **원복 범위:** 에디터 종료는 쓰기 전에 한다. 쓰기부터 빌드 성공 전까지의 모든 실패(종료 거절 · 남은 에디터 프로세스 · 빌드 실패 · Ctrl+C)는 덮어쓴 파일을 `codegen/backup/` 에서 되돌리고, 새로 만든 파일은 지우는 대신 `codegen/failed/` 로 옮긴다(실패한 판 보존). 빌드가 성공한 뒤의 실패(기동 · 브리지 · 계약 불일치)는 되돌리지 않는다 — 바이너리가 새 코드라 소스가 그것과 같아야 한다.
- **그 밖의 검사:** 헤더 이름 중복(모듈 전체) · `screens.yaml` 이름 규칙(식별자 · ViewBase/Widget 접미사) · brief `binding_contract.class` = `U<Widget>`. 파일은 CRLF · UTF-8(BOM 없음) — 작업 트리(`text: auto` · autocrlf)와 같게.
- **설정 · 기록:** `pipeline.yaml` 에 `codegen` 절(module · api_macro · module_root · ui_dir) · `editor.args` · `build.args`(`-WaitMutex -NoHotReload`). `codegen.json` 스키마 추가(7종), `report.json` 에 codegen 요약, `run_pipeline --module-root`(시험용). 에디터는 떼어 내 기동(DETACHED · 새 프로세스 그룹, 가능하면 job breakaway), 표준 출력은 `codegen/editor.log`.
- **[실측]** 적응형 유니티가 새 cpp 2개를 유니티 묶음에서 뺐다(`[Adaptive Build] Excluded from AstralBreak unity file`) — 묶음 충돌은 1a-5 의 `-DisableAdaptiveUnity` 에서 본다. DDC 가 따뜻하면 브리지 준비가 12초대였다.

1a-4 에서 확인 · 정한 것 (11-14):
- **재시도 루프:** 시도 k 는 `specs/00k.json` 을 쓰고, 실패하면 fix 가 `patches/00k.json`(source fix)을 낸다. `--inject-fault` 의 결함도 같은 patch 모양(`patches/000.json`, source fault)으로 normalize 뒤에 적용한다. 재시도 N = 3 → 시도는 최대 4번. '실패 게이트 집합이 줄었다' = 직전 집합의 진부분집합 — 아니면 무진전, 두 번 연속이면 `NO_PROGRESS` 로 끝. fixer 가 op 를 하나도 못 내면 바로 `NO_FIX`. 끝나면 finalize(실패 = 폐기). **[실측]** 첫 offscreen run 이 아래 컬링 함정으로 시도 3 에서 `NO_PROGRESS` 로 멈추고 run 패키지를 폐기했다(안전장치 동작 확인).
- **build:** 에디터가 없으면 `core.ue.Toolchain` 으로 띄운다(로그 `build/editor_00k.log`). 텍스처는 manifest 의 `ue_path` 가 빈 에셋만 임포트한다(첫 시도는 전부, generate 로 다시 만든 에셋은 refine 이 비운다). 이름은 `T_<asset_id>`, 같은 에디터 세션에서 다시 임포트하면 `T_<asset_id>_2` …(임포트는 덮어쓰기를 거부). `ue_path` = 패키지 경로. WBP 이름은 `screens.yaml` 의 `wbp`(없으면 `WBP_<화면 ID>`), 생성은 첫 시도에만. 에디터 세션(`process_id`)이 지난 build 와 다르면(codegen 재기동이 저장 안 한 패키지를 버림) 처음부터 다시 만든다. `build.json` = 지금 상태(WBP · revision · 세션 · 텍스처 이름) + 시도별 op.
- **verify 게이트 세부:** 기준 해상도 = spec.canvas. 영역 = 루트 Canvas 직계, 말단 = 자식 없는 위젯, 둘 다면 영역(더 엄격), 그 사이(박스)는 기록만(`report.recorded.placement_inner`). 바인딩 = `missing_bindings` 0 + `list_bind_widgets(WBP)` = `codegen.json` 계약. 텍스처 = export `textures[]` ↔ manifest(압축은 manifest, 그룹 · 밉 · 스트리밍 · sRGB 는 `pipeline.yaml textures`), 크기 차이는 기록만. 왕복 = `roundtrip_equal` + GUID 맵 누락 0. 렌더가 안 되면(컴파일 실패 등) 렌더 게이트 넷을 오류와 함께 실패로 남긴다. 사람 눈용 `render_sample.png` 는 brief sample 을 overrides 로(보이기 규칙 그대로) — 게이트와 무관.
- **[실측] 컬링 함정:** Slate 는 그리기(클립) 영역 밖으로 완전히 나간 위젯을 그리지 않는다(패널 자식 컬링). 그 위젯과 자식의 페인트 공간 geometry 는 기본값 `(0, 0, 0, 0)` 으로 남고 `visible` 은 true 다. 처음에는 화면 밖 게이트가 이를 '크기 0' 으로 건너뛰었고(IoU 게이트만 실패), fixer 가 0 을 측정값으로 써서 크기를 두 배로 키웠다. → 그려지지 않은 보이는 위젯 = 화면 밖 실패(`not_painted`), fixer 는 그때 측정값 대신 루트 bbox · 앵커 · 정렬로 `bbox_intent` 자리를 계산한다. 부분적으로 걸친 위젯은 그려지고 실제 좌표가 나온다. 가짜 에디터(pytest)도 같은 컬링을 흉내 낸다.
- **결정적 fixer:** 배치 게이트(offscreen · overlap · iou_region · iou_leaf)에서 실패한 위젯마다 자신 또는 가장 가까운 캔버스 슬롯 조상(영역)을 점 앵커일 때만 고친다 — `position += d + alignment × dsize`, `size += dsize`(d = `bbox_intent` − 측정). 영역이 이미 제자리(≤ 0.5 px)면 안쪽 문제로 보고 op 없음. 겹침은 `bbox_intent` 에서 벗어난 쪽만, 둘 다 제자리면 제안만. 텍스처 설정 불일치 = `replace_asset(regenerate)` → generate 분기(새 이름으로 다시 임포트). compile · bindings · required_elements · roundtrip 은 op 없음(1b LLM 몫).
- **finalize:** 통과 = `save_widget_run` + `lineage.json`(최종 spec 파일 · sha256 · 시도 · 결함 · patch 목록 · 텍스처 · 저장 패키지 · 계약 해시 · revision). 실패 · 오류 = `discard_run_packages`(`--keep-failed` 면 저장 + lineage `status: fail`). build 전에 끝난 run 은 할 일 없음(단계 기록도 없음), `--until` 은 finalize 를 하지 않는다(패키지는 에디터에 저장 안 된 채). 에디터 세션이 바뀌었으면 패키지는 이미 사라진 것으로 본다. 파이프라인은 끝나도 에디터를 내리지 않는다(다음 run 이 재사용).
- **report · 지표:** report 에 `attempts[]`(spec · 실패 게이트 · patch · 분기 · 멈춘 이유) · `fault` · `finalize` · `artifacts` · `verify` 를 더했다(스키마 9종 — `build` · `lineage` 추가). 지표 run 줄 = `status`(run 결과) + `verify`(마지막 verify 의 게이트 결과, 돌지 않았으면 null) + `failed_gates` · `fault` · `retries`(시도 − 1). 에셋 줄의 `retries` = 그 에셋을 다시 만든 횟수.
- **LLM 호출 틀(1b 용, 1a 호출 0):** `core/llm.py` — 프롬프트는 `-p` 바로 뒤, `--allowedTools` 는 맨 뒤, `--json-schema` 는 인라인 JSON(파일 경로가 아님 — 1b 첫 실제 호출에서 확인), `--max-budget-usd` + 숨은 `--max-turns`, cwd `claude_ctx/`, stdin 닫음, 환경에서 `ANTHROPIC_API_KEY` 제거, `--dangerously-skip-permissions` · `--bare` 거부. 단계 출력은 structured_output 으로만 받으므로 허용 도구는 `Read` 하나(§9 표의 `Edit(work/<run_id>/**)` 는 필요 없어 뺐다 — 파일은 오케스트레이터가 쓴다). `claude_ctx/.claude/settings.json`(Bash · 쓰기 · 웹 거부, auto-memory 끔) · `prompts/verifier.md` · `fix.md` · `config/empty_mcp.json`. pytest 는 가짜 CLI 만(실제 CLI 는 conftest 가 막음).
- **손 spec 글자 정렬(선택 항목):** 박스 칸의 글자 5개를 `v_align: center` 로 바꾸고 `bbox_intent` 를 실측 글자 상자로 맞췄다. **[실측]** 엔진 기본 글꼴(Roboto + 한글 대체)의 줄 높이 ≈ 글꼴 크기 × 1.6(16→26 · 18→29 · 26→42 · 30→48), 칸보다 크면 칸 높이(34 → 50). 값은 잠정.

**Phase 1a 결과 요약 (11-15, 1a-5 정상 run `R20261115_001147_CombatHUD` — DebugGame 에디터, 자동 시험 뒤 같은 에디터)**

| 끝 조건 | 판정 | 숫자 |
| :--- | :--- | :--- |
| 게이트 통과 | 충족 | 시도 1 에 10/10 — compile 오류 0 · bindings 누락 0 · texture_settings 불일치 0 · offscreen 0(3 해상도) · overlap 0(기준 0.04) · required_elements 누락 0 · iou_region 최소 1.0(영역 4개 · 중심 0 px) · iou_leaf 최소 1.0(말단 7개 · 중심 0 px) · baked_text 건너뜀(procedural — 통과 + 이유) · roundtrip 0. 결함 주입 3종(1a-4: offscreen · overlap · drift)은 모두 시도 2 통과 |
| 왕복 일치 | 충족 | `roundtrip.equal` true · 차이 0 · GUID 누락 0 · unsupported 0 · 역추출 revision `sha1:fd6614d5…` = build revision |
| codegen 해시 건너뛰기 | 충족 | 계약 `sha1:5ae0d80a…` 같음 → `skipped`(`contract_unchanged`) · 빌드 안 함 · 떠 있는 에디터 리플렉션 대조 일치(바인딩 8개) · 0.63초. (1a-3: 첫 생성 · 빌드 22.4초 · 재기동 → 같은 spec 재실행 0.46초 건너뜀) |
| JSONL 기록 | 충족 | `metrics/uigen.jsonl` 에 run 1줄(`status: pass` · `verify: pass` · `retries` 0 · `failed_gates` [] · 4.15초) + 에셋 3줄(procedural · `retries` 0). 1a 동안 run 12개 · 48줄 |

- run 시간 4.15초 = normalize 0.01 · codegen 0.63 · generate 0.11 · refine 0.02 · build 0.98(텍스처 3장 임포트 · WBP 생성 · apply 13 op) · verify 1.56(렌더 3 해상도 + sample) · finalize 0.82(패키지 4개 저장). 에디터 기동 · 빌드가 없는 경우의 값이다.
- 생성 C++(`Source/AstralBreak/UI/HUD/`)은 1a-3 의 첫 생성 이후 바뀌지 않았다(git 상태 run 전후 같음).
- **증거 run(11-15 정리 뒤 — 사용자 결정):** `R20261115_001147_CombatHUD`(1a-5 정상 · 눈 확인한 WBP) · `R20261114_235343_CombatHUD`(1a-4 offscreen 결함 → 재시도 통과)만 `Tools/uigen/work/` 와 `Content/_AutoGen/` 에 남겼다(둘 다 git 무시). 위 표 · 단계 기록의 다른 run 이름은 기록으로만 남는다(폴더는 휴지통). `metrics/uigen.jsonl` 은 지운 run 의 줄까지 그대로 둔다.

**1b 로 넘길 것 (1a-5 정리)**
- **`claude -p` 첫 실제 호출에서 채록:** `--json-schema` 값 형식(1a 틀은 인라인 JSON) · 결과의 `structured_output` 모양 · `--max-budget-usd` 예산 끊김 메시지 · 종료 코드 — 그 뒤 단계 상한 값(예산 0.5 USD · 턴 8/6 · 300초, 잠정)을 다시 본다.
- **프로젝트 폰트 결정 · 내려받기 승인**(§12-2 4 — Pretendard / Noto Sans KR). 정하면 spec `font.family` 를 채우고 줄 높이(1a 실측 × 1.6 은 엔진 기본 글꼴 값)를 다시 잰다.
- **OCR 엔진 선택** — `baked_text` 게이트는 1a 에서 한 번도 돌지 않았다(procedural 은 글자를 그리지 않음). 생성 이미지가 들어오는 1b 에서 처음 돈다.
- **재시도 codegen 분기의 실제 경로**(정정 patch 가 바인딩을 바꿈 → 에디터 내리기 → 빌드 → 재기동 → 세션이 바뀌어 build 처음부터) — 1a 는 pytest(가짜 도구 사슬)로만 확인했다. 계약을 바꾸는 결함이 생기면(또는 1b LLM fix 가 바인딩 op 를 내면) 실제로 확인한다.
- 원래 1b 몫: 컨셉아트(§12-2 3) · analyze 의 장면 / UI 가르기(A8) · codex 한도 이벤트 모양(A3 — 걸렸을 때 채록).

- M4 단위 E(4인 별도 프로세스 시험)는 UI 와 무관해 에디터가 비는 때 아무 때나. 단위 D(오의 애니)는 별개.
- 감안할 점: M4 C 의 화면은 Phase 0 ~ 1b 가 끝나야 완성된다. 그동안 HUD 는 디버그 위젯이다.

---

## 12. 불확실한 가정 · 질문

### 12-1. Phase 0 에서 확인할 가정

| # | 가정 | 틀리면 | Phase 0 결과 (11-14) |
| ---: | :--- | :--- | :--- |
| A1 | codex built-in `image_gen` 이 `codex exec`(비대화형)에서도 돌고, `--json` 이벤트로 결과 파일을 찾을 수 있다 | 생성 앞뒤로 `generated_images` 폴더 차이를 본다(직렬 실행이라 가능) | **참(조건부) [실측]** — 비대화형에서 돈다. 이벤트에 파일 경로 항목은 없지만 폴더 `generated_images/<thread_id>/` 의 `thread_id` 가 첫 이벤트에 있다 → 그것으로 찾고, 폴더 차이는 대비책(§7) |
| A2 | npm 의 codex 가 `~/.codex` 의 ChatGPT 로그인을 같이 쓴다 | 사용자가 한 번 `codex login` | **참 [실측]** — npm 0.166.0 `codex login status` = `Logged in using ChatGPT` |
| A3 | 한도 초과가 식별 가능한 메시지 · 종료 코드로 온다 | 연속 실패 횟수로 추정 | **미확인(재현 안 함)** — [바이너리] 식별자 `usage_limit_reached` · `quota_exceeded` · `usage_not_included` · `rate_limit_exceeded` · 문구 `Try again at …` 있음. 이벤트 모양 · 종료 코드는 걸렸을 때 채록, 그때까지 '틀리면' 경로를 같이 둔다 |
| A4 | `--json-schema` 결과를 JSON 출력에서 꺼낼 수 있다 · `--max-turns` 존재 여부 | 출력 파일 + Stop 훅 검사로 대신 · 타임아웃만 | **참 [실측 2.1.325]** — 스키마 출력은 결과 `structured_output`(`{"answer":"ok","n":3}`), 숨은 `--max-turns 1` 이 `error_max_turns` 로 끊는다(§10-1) |
| A5 | `--allowedTools` 경로 규칙으로 쓰기를 `work/<run_id>/` 로 묶을 수 있다 · auto-memory 를 settings 로 끌 수 있다 · `--setting-sources project` 의 project 가 저장소 루트가 아니라 cwd(`claude_ctx/`)다 | PreToolUse 훅으로 경로 검사 · 루트 설정이 읽히면 `--settings` 로 덮는 값만 믿는다 | **참(셋 중 둘 실측 · 하나 근거)** — `Edit(work/**)` 가 cwd 기준으로 `work/` 밖 `Write` 를 막는다 [실측] · `--setting-sources project` 의 project 는 cwd 다(cwd 설정의 deny 가 걸림 [실측] — 루트가 같이 읽히는지는 미판별이라 `--settings` 로 명시) · auto-memory 는 `autoMemoryEnabled: false`(설정 스키마 — 효과는 미관측) |
| A6 | `FWidgetRenderer` 두 번 그리기로 폰트 · 텍스처가 다 그려지고, 그 뒤 `GetPaintSpaceGeometry` 가 렌더 좌표와 맞는다 | 그리기 사이 `FlushRenderingCommands` · 폰트 캐시 미리 채움 | **참 + 새 문제 1건 [실측]** — 각 그림 뒤 `FlushRenderingCommands` 로 3회: 1·2·3회 그림이 픽셀 단위로 같다(다른 픽셀 0 — 에디터가 이미 폰트를 올린 상태라 첫 그림부터 완성). geometry 는 캔버스 슬롯(앵커 · 정렬 포함)과 **오차 0 px**. 라틴 · **한글(대체 폰트)** · 트랜지언트 텍스처 모두 그려짐. 단 **색에 감마가 두 번 걸린다**(아래 A6-색) |
| A7 | `UWidgetBlueprintFactory` 를 대화창 없이(`ConfigureProperties` 생략) 써도 루트 위젯이 정해진다 | 만든 뒤 루트를 Canvas 로 교체 | **거짓 [실측 · 소스]** — 이 프로젝트 설정(`bUseWidgetTemplateSelector` false · `DefaultRootWidget` 없음)에서는 루트가 없다(`WidgetBlueprintFactory.cpp:184-200` — 선택기를 끄면 `RootWidgetClass = DefaultRootWidget` 로 덮는다). → build 는 루트가 없으면 `ConstructWidget<UCanvasPanel>` + `RootWidget` 지정 + `OnVariableAdded` (팩토리가 루트를 만들 때와 같은 순서). GUID 맵 8/8 · 컴파일 오류 0 |
| A8 | HUD 컨셉아트에서 analyze 가 장면과 UI 를 안정적으로 가른다 | brief 에 HUD 영역을 손으로 적는 선택 입력 | Phase 1b 로 미룸(컨셉아트 필요) |

**A6-색 [실측]:** `FWidgetRenderer(true)` + `CreateTargetFor(…, true)`(엔진이 RT 를 `SRGB=false` · B8G8R8A8 로 만든다 [소스] `WidgetRenderer.cpp:81-100`) 조합에서 지정색이 sRGB 를 한 번 더 거친 값으로 나온다 — 패널 `#202838` → `#636E81`, 체커 `#282828` → `#6E6E6E`, `#E8B54A` → `#F5DB93`(모두 'sRGB 값을 선형으로 보고 다시 인코딩한 값'과 일치). verify 의 영역 대표색 ΔE(§8-2)가 이 상태로는 뜻이 없으므로 render_widget 은 아래 규칙으로 고친다.

| 탐침 (지정색) | `gamma=true` (RT B8G8R8A8 · SRGB=0) | `gamma=false` (RT B8G8R8A8 · SRGB=1) |
| :--- | :--- | :--- |
| 패널 Border `#202838` | `#636E81` = sRGB 인코딩(지정값) | `#04050A` = sRGB 디코딩(지정값) |
| 체커 텍스처 금 `#E8B54A` | `#F5DB93` | `#CE7611` |
| 체커 텍스처 어둠 `#282828` | `#6E6E6E` | `#050505` |

→ **규칙(실측 3점 일치):** `gamma=true` 로 그리고 읽은 8비트 값에 채널마다 sRGB→선형 변환을 한 번 하면 지정색이 나온다(예 `0x63 → 0x20`). `gamma=false` 는 어두운 쪽이 8비트에서 뭉개지므로(`0x20 → 0x04`) 쓰지 않는다. render_widget(Phase 1a)은 이 보정 LUT 를 적용한 PNG 를 내고, 에디터 디자이너 화면과 같아 보이는지는 Phase 1a 에서 사람 눈으로 한 번 맞춘다.

**[사람 눈 11-15] 통과** — 1a-5 정상 run `R20261115_001147` 의 `render.png`(force_visible · LUT 적용 · 검은 바탕)와 같은 WBP 의 UMG 디자이너(1920×1080)를 사용자가 비교했고, 게이지 금색(`#E8B54A`) · 체인 패널 · 글자색이 같아 보인다고 답했다. 바탕은 다르다(렌더 검정 · 디자이너 격자 — 반투명 배너 `#2A1A0ACC` 만 바탕 차이). → LUT 보정을 확정한다. 영역 대표색 ΔE(§8-2)는 Phase 2 보정 때 이 규칙의 PNG 로 잰다.

스파이크 산출물: `Tools/mcp/results/widget_spike/<시각>/`(draw_1~3.png · report.json, git 무시). 코드는 `Plugins/WidgetMcp/Source/WidgetMcpEditor/Private/Spike/` · 시험 `WidgetMcp.Spike.BuildRender`.

### 12-2. 사용자에게 묻는 것

1. ~~플러그인 이름~~ — **결정(11-14): `EditorMcpCore` / `WidgetMcp`.** 편집 대상 애셋 이름으로 짓는 기존 관례(AnimGraph · StateTree)와 맞고, 코어는 프로젝트 코드에 의존하지 않으므로 일반 이름.
2. ~~StateTree 도구 이전 시점~~ — **결정(11-14): Phase 0 에서 같이 이전.** 분리가 한 번에 끝나고 회귀도 한 번이다(§3-1).
3. **M4 HUD 컨셉아트** — 준비돼 있는지, 경로.
4. ~~폰트~~ — **결정(11-14): 1a 는 엔진 기본 폰트(Roboto + 한글 대체)**, 프로젝트 폰트(Pretendard / Noto Sans KR)는 1b 에서 결정 · 내려받기는 그때 따로 승인. spec `font.family` = null.
5. ~~텍스처 압축 기본값~~ — **결정(11-14): `TC_EditorIcon` 기본 + 큰 배경(`panel_bg`)만 `TC_BC7`** — `pipeline.yaml textures.compression_by_kind`.
6. ~~상한 값~~ — **결정(11-14): 재시도 N = 3** 으로 시작(codex 20 회는 1b 에서 실제로 쓸 때 다시 본다).
7. **집계 리포트 커밋** — `metrics/` 집계 결과(텍스트)를 포트폴리오 증거로 커밋할지. (Phase 2 몫)
8. ~~HUD 요소 목록~~ — **결정(11-14): M4 설계 §5 그대로** — 오의 게이지(+가득 시 강조) · 체인 패널(남은 시간 · 참가 N/4) · 버스트 배너(인원) · '오의 불가'.
**1b 착수 때 물을 것(1a-5 정리, 11-15):** 3(컨셉아트 경로) · 4 후속(프로젝트 폰트 선택 · 내려받기 승인) · OCR 엔진 선택 — 근거는 §11 '1b 로 넘길 것'. 7(집계 리포트 커밋)은 Phase 2.

9. **Phase 1a 진행 방식(11-14 결정):** 브랜치 `feat/M4_Ultimate_Skills` 그대로 · 하위 단계 1a-1 ~ 1a-5(§11) · 재시도 fix 는 **결정적 fixer**(일부러 깨뜨린 spec + 정정 patch, LLM verifier · fix 실제 호출은 1b — 1a 에는 reference.png 가 없어 verifier 가 비교할 대상이 없다) · 설정 YAML 을 위해 venv 에 **PyYAML 6.0.3 설치**(사용자 승인).
