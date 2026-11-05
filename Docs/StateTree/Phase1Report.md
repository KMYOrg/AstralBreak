# StateTree 자동화 Phase 1 — 저작 고리 결과

작성일: 2026-11-05 · 대상: UE 5.7.4 · 기준 문서: [DevelopmentGuide.md](DevelopmentGuide.md) · 실측: [Feasibility.md](Feasibility.md) · 엔진 근거: [APIResearch.md](APIResearch.md)

## 결론

Claude 가 StateTree 를 만들고, 읽고, 고치고, 컴파일하고, 실패하면 되돌리는 고리가 동작한다. 내장 노드만으로 `Idle → Chase → Attack` 트리를 배치 한 번에 생성 · 컴파일 · 저장했고, 에디터 재시작 뒤 `inspect` 가 GUID 까지 일치했으며, 잘못된 입력은 전부 오류와 함께 디스크를 바꾸지 않았다.

**자동으로 판정할 수 없는 것이 남았다.** 사용자가 에디터에서 열어 손으로 고칠 수 있는지와 화면 확인 4건은 사람 눈으로만 알 수 있어 통과로 적지 않았다(§5). 런타임 동작은 Phase 2 다 — 트리는 컴파일까지 확인했고 실제로 돌리지는 않았다.

| 완료 기준 (§7) | 판정 |
| :--- | :--- |
| 내장 노드만으로 배치 한 번에 생성 · 컴파일 · 저장 | **통과** |
| 재시작 뒤 `inspect` 일치 | **통과** — 전체 JSON 동일 |
| 잘못된 입력은 오류와 함께 디스크 무변경 | **통과** — 6종, 파일 MD5 동일 |
| 사용자가 에디터에서 열어 수동 편집 가능 | **사용자 눈 확인 대기** |
| Development · DebugGame 빌드 | **통과** — 실행은 DebugGame 만 |

## 1. 구현한 것

**Tool 8개** (`run_state_tree_scenario` 제외): `create_state_tree` · `inspect_state_tree` · `list_state_tree_node_types` · `list_state_tree_bindable_sources` · `preview_state_tree_operations` · `apply_state_tree_operations` · `compile_state_tree` · `revert_state_tree`.

**op 15종**: §4 의 14종 + `bind_property_function`(D-5). 메뉴에 없는 프로퍼티는 `NOT_BINDABLE`(D-6).

| 파일 | 내용 |
| :--- | :--- |
| `Tools/AnimMcpTools_StateTree.cpp` | 핸들러 8개 |
| `Core/AnimMcpStateTreeAsset` | 경로 규칙 · 생성 · 컴파일 측정(`fixups`) · 복구 · 편집기 알림 |
| `Core/AnimMcpStateTreeBindings` | `PreflightBinding` 을 경로 · 타입 · 메뉴와 범위로 나눠 옮겼다 · 소스 후보 |
| `Core/AnimMcpStateTreeInspector` | 애셋 → JSON · 노드 타입 목록 |
| `Core/AnimMcpStateTreeOperations` | 기존 트리의 그림자로 계획 · Preview · Apply |
| `Tests/AnimMcpStateTreeTests.cpp` · `AnimMcpStateTreeTestTypes.h` | 시험 16개 · 시험 전용 Evaluator |
| `Tools/mcp/state_tree_mcp/server.py` | 로직 없음, `bridge.py` 공유, `.mcp.json` 등록 |

그 밖: `+StateTreeEditPaths=/Game/AI/` · `get_editor_status.state_tree_edit_paths` · 오류 코드 13개 · `Build.cs` 에 `GameplayTags` 추가, `Slate` · `SlateCore` 제거 · Phase 0 시험 파일 삭제(휴지통) · 플러그인 · `Tools/mcp` README.

**승인받아 지침서와 달라진 곳:** ① 같은 배치의 노드가 얽힌 바인딩은 범위를 Apply 안에서 바인딩 직전에 판정한다 ② `values` 가 노드 구조체 프로퍼티도 받는다 ③ 삭제 시 바인딩 처리와 `NODE_REFERENCED` ④ `rollback.method = "none"` · 실효 큐 비교 · 실행 가능 여부 비교 · `TRANSACTION_ACTIVE` ⑤ `add_state` 는 `state` · `group` 만.

**구현 중 더 바뀐 곳:** 복구 순서가 '변경 없음 → Undo → 재로드'에서 **'Undo → 변경 없음 → 재로드'** 로 바뀌었다(§4 의 두 번째 결함). 지침서 §5 에 반영했다.

## 2. 확인한 엔진 API

Phase 0 의 [APIResearch.md](APIResearch.md) 에 더해 이번에 소스 또는 실행으로 확인한 것이다.

| 사실 | 근거 | 판정 |
| :--- | :--- | :--- |
| 거리 조건의 `Operator` · `bInvert` 는 인스턴스가 아니라 노드 구조체에 있다 | `StateTreeCommonConditions.h:225` · `:228` | 실측 — 값 읽기 · 쓰기 |
| `Get Actor Location` 의 `Input` 은 `Category = Parameter` 다 — 필수 입력이 아니다 | `StateTreeActorPropertyFunctions.h:14` | 소스 |
| `AddFunctionBinding` 은 함수 노드 GUID 를 스스로 만들고 대상의 기존 바인딩을 지운다 | `StateTreeEditorPropertyBindings.cpp:26` · `:39` | 실측 |
| 함수 바인딩을 지워도 그 함수로 들어가는 입력 바인딩은 남는다 — 직접 지워야 한다 | `RemoveBindings` 는 대상 경로만 본다 | 실측 — `14_PropertyFunction` |
| `FStateTreeEditorPropertyBindings` 는 기반의 `RemoveBindings(조건)` 을 가려서 기반 참조로 불러야 한다 | `StateTreeEditorPropertyBindings.h:107` | 소스 |
| 스키마 게이트 `IsStateTypeAllowed` · `IsStateSelectionAllowed` · `AllowEvaluators` · `AllowEnterConditions` · `AllowMultipleTasks` | `StateTreeSchema.h:60` · `:66` · `:98` ~ `:119` | 소스 |
| AI 스키마가 허용하는 구체 Evaluator 는 엔진에 없다. 허용 조건은 `FStateTreeEvaluatorCommonBase` 파생이다 | `StateTreeComponentSchema.cpp:39` ~ `:43` | 소스 |
| 다른 모듈의 USTRUCT 가 `FStateTreeEvaluatorCommonBase` 를 상속해 링크 · 컴파일 · 재로드된다 — M3 커스텀 노드가 같은 경로를 쓴다 | 시험 Evaluator | 실측 — 런타임 제외 |
| `UTransactor::GetUndoCount` · `IsActive` | `Transactor.h:622` · `:555` | 실측 |
| `UObject::Modify` 는 `bAlwaysMarkDirty` 를 넘겨 패키지를 더티로 만든다. 값이 그대로여도 표시된다 | `Obj.cpp:1577` | 소스 + `11_Recovery` C |
| 컴파일이 불량 바인딩을 지우면 리비전은 적용 전과 같아지는데 트랜잭션은 큐에 남는다 | `07_Fixups` | 실측 |
| 상태 객체 삭제 · 함수 노드 추가/제거가 섞인 배치도 Undo 한 번으로 GUID 까지 복원된다 | `11_Recovery` D | 실측 |
| `-stdout -FullStdOutLogOutput` 를 주면 `Saved` 를 읽지 않고 크래시 호출 스택을 받을 수 있다 | 이번 크래시 진단 | 실측 |

## 3. 테스트 결과

### Automation — `AnimGraphMcp.StateTree.*` 16 / 16 통과

최종 빌드, DebugGame 에디터, `-unattended`. 전체 14.3초.

| 시험 | §8 | 내용 |
| :--- | :---: | :--- |
| `01_Create` | 1 | 빈 트리 · 잘못된 스키마 · 덮어쓰기 · 프로젝트 컨텍스트 클래스 |
| `02_States` | 2 | 부모/자식 · 이름 중복과 GUID 식별 |
| `03_Nodes` | 3 | Task · Enter Condition · Evaluator · Global Task · 값 |
| `04_Transitions` | 4 | 전환 · 대상 삭제 거부 · cascade |
| `05_Bindings` | 5 | 정상 · 오타 · 타입 · 범위 · 같은 배치의 범위 위반 |
| `06_CompileFailure` | 6 | 메시지 추출 · 자동 복구 |
| `07_Fixups` | 7 | 조용한 제거 감지와 복구 |
| `08_Guards` | 8 | 리비전 · 더티 · 경로 · 활성 트랜잭션 |
| `08b_PieRefused` | 8 | 실제 PIE 를 띄워 거부 확인 |
| `09_RoundTrip` | 9 | 재로드 왕복 · GUID 정규화 비교 |
| `10_UniqueIds` | 10 | GUID 중복 없음 |
| `11_Recovery` | 11 | Undo 유지 · 버려진 트랜잭션 · 변경 없음 · 섞인 배치 |
| `12_Preflight` | 12 | 컨텍스트 · 대상 오타, 계획된 노드 포함 |
| `13_NotBindable` | 13 | `NOT_BINDABLE` · 소스 목록 |
| `14_PropertyFunction` | 14 | 함수 바인딩 전 경로 |
| `15_OpenEditor` | 추가 | 열린 편집기 — 알림 · Undo · 재오픈 |

### 완료 기준 — 브리지 경유 스크립트

`create_state_tree` → `preview` → `apply`(`expected_revision`) → `inspect` → 잘못된 입력 6종 → 에디터 재시작 → `inspect` 대조 → 수동 컴파일. 전 항목 통과.

- Preview 는 함수 입력 · 조건 대상 바인딩 2건을 `deferred` 로 표시했고 Apply 가 판정했다.
- 잘못된 입력 6종: `BAD_SOURCE_PATH` · `BAD_TARGET_PATH` · `NOT_BINDABLE` · `TYPE_NOT_FOUND` · `NODE_REFERENCED` · `COMPILE_FAILED`. 마지막은 `rollback{method: undo, verified: true, undo_history_cleared: false}`.
- 재시작 뒤 `inspect` 전체 JSON 이 같았다. 재컴파일해도 리비전이 그대로였고 `fixups` 는 없었다.

### MCP 서버

`.mcp.json` 과 같은 명령으로 stdio 기동: Tool 정확히 8개, op 사전이 Tool 설명에 실렸고, MCP 경유 `inspect_state_tree` 가 성공했다.

### 회귀

`AnimGraphMcp.Runner` 4 · `AnimGraphMcp.Smoke` 26 · `AnimGraphMcp.Generation` 9 · `AnimGraphMcp.Runtime` 1 통과. 단서 두 가지:

- `Runtime` 은 시나리오 없이 돌아 **실제로 검사한 것이 없다**(시험 자체가 경고를 낸다).
- 이 40개는 마지막 빌드 직전 빌드에서 돌렸다. 마지막 빌드의 변경은 시험 파일 `AnimMcpStateTreeTests.cpp` 뿐이다.

### 빌드

`AstralBreakEditor Win64` Development · DebugGame 둘 다 성공(최종 코드 기준). 경고는 컴파일러 버전 안내뿐이다.

## 4. 진행 중 생긴 실패

| # | 증상 | 원인 | 조치 |
| :---: | :--- | :--- | :--- |
| 1 | 첫 시험 실행에서 에디터 크래시 2회, 종료 코드 3 | **시험 코드 버그.** `02_States` 가 임시 `TSharedPtr` 의 배열을 참조로 잡았다. 플러그인 코드 아님. 첫 회는 stdout 이 없어 원인을 못 봐 `-stdout` 으로 재현했다 | 지역 변수로 고침 |
| 2 | `07_Fixups` 실패: `none` 기대 `undo` | **실제 결함.** 컴파일이 불량 바인딩을 지우면 리비전이 적용 전과 같아져 '변경 없음'으로 끝나고, 우리 트랜잭션이 사용자 Undo 큐에 남았다 | 큐를 리비전보다 먼저 본다. 지침서 §5 정정 |
| 3 | `13_NotBindable` 첫 단락 실패 | **시험 가정 오류.** `bCanBeDamaged` 가 메뉴에 없다고 소스 확인 없이 가정했다 | 그 단락 삭제. 실측 근거가 있는 `bTelegraphAttackEnabled` · `RootComponent` 검사는 유지 |
| 4 | 시험 설계 중 발견 | **실제 결함.** `Modify` 를 지연시켜 `set_node_values` 등에서 `Data->Modify()` 가 빠졌고, 그러면 조용한 삭제를 Undo 가 복원하지 못한다 | 첫 변경 때 항상 `Data` 를 함께 `Modify` |
| 5 | 코드 검토 중 발견 | `server.py` 가 등록 뒤 `__doc__` 를 고쳐 op 사전이 Tool 설명에 안 실렸다 | 등록 전에 붙이는 데코레이터로 교체 |

## 5. 미해결

### 사용자 눈 확인 (자동 판정 불가)

애셋: `/Game/AI/Test/ST_P1_Acceptance`

1. 에디터에서 열어 상태 · 작업 · 전환을 손으로 고치고 저장할 수 있는가 — **완료 기준**
2. 재로드로 편집기가 닫혔다 열릴 때 탭 위치 · 레이아웃 · 선택 상태 (Feasibility §7-1)
3. 외부 수정 뒤 트리 뷰가 화면에서 정상인가 — 들여쓰기 · 작업 아이콘 · 전환 표시 (§7-2)
4. 상태를 선택해 디테일 패널을 띄워 둔 채 외부 수정 · Undo 로 그 상태가 사라질 때 (§7-3)
5. `Distance Compare` 의 `Source` 바인딩이 일반 바인딩처럼 보이고 손으로 고칠 수 있는가 (§7-4)

### 돌려 보지 않은 것

- **런타임 전부.** MoveTo · Property Function · 거리 조건의 실제 동작은 Phase 2 다.
- **Apply 의 `COMPILE_FIXUPS` · 저장 실패 분기.** 도구 경로로 불량 바인딩을 넣을 수 없어 Apply 안에서는 닿지 않는다. `Compile` 과 `Recover` 부품은 `07_Fixups` 에서 시험했지만 Apply 의 분기 자체는 실행하지 않았다.
- **대화형 실행.** 모든 시험이 `-unattended` 다. 창이 뜨는 경로는 Tool 이 사전 검사로 피하도록 했지만 실제로 돌려 보지 않았다.
- **Development 구성 실행.** 빌드까지다.
- **재로드 대상을 참조하는 다른 애셋이 있을 때** · 큰 맵에서의 재로드 비용 — Phase 0 과 같다.

### 알려진 한계

- **Preview 통과가 범위 통과를 보장하지 않는다.** 같은 배치의 노드가 얽힌 바인딩은 Apply 가 판정한다. Apply 실패는 Undo 로 복구되니 비용은 작다.
- **`Get Actor Location` 입력을 안 묶어도 컴파일이 성공한다.** `Input` 이 필수가 아니어서 도구도 컴파일러도 잡지 못하고, 런타임에 빈 Actor 로 돈다. M3 에서 주의할 점이다.
- **`compile_state_tree` 의 `fixups` 는 메모리만 바꾸고 더티 표시를 하지 않는다.** 디스크와 어긋난 채 남으므로 보고를 보고 `revert_state_tree` 로 되돌려야 한다.
- 루트 파라미터는 소스로 쓸 수 있지만 만드는 op 가 없다(§7 Phase 3). 쓰려면 에디터에서 만들어야 한다.
- BP 노드와 함수 노드의 값은 쓸 수 없다.
- `list_state_tree_bindable_sources` 는 1단계 프로퍼티만 보여 준다. 중첩 경로는 직접 지정해야 한다.
- 로드 시 조용한 바인딩 삭제는 여전히 도구가 막을 수 없다(Feasibility §7).
- 시험을 돌릴 때마다 `/Game/AI/Test/` 에 애셋이 22개 쌓인다. 자동으로 지우지 않는다.
- 시험 전용 Evaluator 는 USTRUCT 라 `#if` 로 뺄 수 없어 항상 빌드된다. `meta=Hidden` 이라 에디터 선택기에는 안 나온다.

## 6. Phase 2 에서 달라질 것

**API · 구현**

- Tool `run_state_tree_scenario` 추가 — 입력 · 출력은 지침서 §6. `Core/AnimMcpStateTreeRuntime.cpp` 새로 만듦
- `state_tree_mcp/server.py` 에 Tool 1개 추가. 결과는 기존 `poll_automation_tests` 로 받는다
- **최소 AIController 가 필요하다.** 프로젝트에 AIController 가 아직 없다. 시험 코드에 둘지 M3 C++ 를 먼저 쓸지 Phase 2 시작 때 정해야 한다
- 러너는 D-7 수정과 `StartJobWithTests` 필터 설정을 그대로 쓴다
- 이 세션은 `state-tree-mcp` 를 쓰지 못했다. 새 세션부터 MCP 목록에 보인다

**데이터 모델**

Phase 2 는 런타임 관측을 더할 뿐 Phase 1 데이터 모델을 바꿀 이유는 없다. 현재 계약은 다음과 같다.

```jsonc
// apply_state_tree_operations 성공 result
{
  "revision_before": "...", "revision_after": "...",
  "compile_state": "up_to_date",      // up_to_date · stale · failed
  "saved": true, "applied": 12,
  "refs": { "idle": "<GUID>", "self_location": "<엔진이 만든 함수 GUID>" },
  "compile": { "ran": true, "ok": true, "messages": [], "fixups": [] }
}

// 실패 error.details
{
  "stage": "compile",                 // preflight · apply · compile · fixups · save
  "planned": [],                      // preflight 만
  "failed_index": 4,                  // apply 만
  "messages": [ { "severity": "error", "state_id": "...", "state_path": "Root/Chase",
                  "item_id": "...", "item_name": "...", "message": "엔진 원문" } ],
  "fixups": [ { "kind": "binding_removed", "target": "<GUID>:Target", "source": "<GUID>:Path" },
              { "kind": "node_removed", "id": "<GUID>", "type": "/Script/..." } ],
  "revision_before": "...",
  "rollback": { "verified": true, "method": "undo",  // none · undo · reload
                "undo_history_cleared": false, "editor_reopened": false, "revision": "..." }
}

// preview_state_tree_operations result
{ "valid": true, "revision": "...", "compile_state": "up_to_date",
  "planned": [ { "index": 10, "op": "bind_property", "ok": true, "deferred": ["scope"] },
               { "index": 11, "op": "add_task", "skipped": true } ] }
```

Feasibility §8 초안과 달라진 점: `method` 에 `none` 추가, `planned` 의 `deferred` · `skipped` 추가, 코드 `COMPILE_FIXUPS` · `NODE_REFERENCED` · `TRANSACTION_ACTIVE` 등 추가, 존재 오류는 `ALREADY_EXISTS` 가 아니라 기존 `ASSET_EXISTS`.
