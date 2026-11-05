# StateTree 자동화 Phase 2 — 런타임 고리 결과

작성일: 2026-11-05 · 대상: UE 5.7.4 · 기준 문서: [DevelopmentGuide.md](DevelopmentGuide.md) · 앞 단계: [Phase1Report.md](Phase1Report.md)

## 결론

Claude 가 만든 StateTree 가 PIE 에서 실제로 돌아가는지를 Claude 가 확인할 수 있게 됐다. `state-tree-mcp` 로 저작한 내장 노드 트리가 새 컨트롤러 `AAstralEnemyController` 위에서 `Idle → Chase → Attack → Idle` 로 돌았고, 이벤트 전송과 전환을 따로 판정했다. 런타임 스폰 · 레벨 배치 양쪽에서 시작했고, 멀티 PIE 에서는 서버 월드 인스턴스만 관측했다.

**실측이 소스 판단을 확인해 준 곳이 하나, 설계를 바꾼 곳이 하나, M3 에 넘길 문제가 둘 있다.** 자동 시작을 끄는 결정은 대조군으로 확인했다(§3-3). 활성 상태 폴링만으로는 `sent 인데 전환 없음` 이라는 거짓 판정이 나와서 엔진의 상태 진입 횟수를 함께 읽도록 바꿨다(§4 의 7번). 트리가 ASC 초기화 전에 시작하는 것과, 폰이 사라질 때 트리가 깨끗이 멈추지 않는 것은 이번 범위에서 고치지 않고 §6 에 넘긴다.

| 완료 기준 | 판정 | 근거 |
| :--- | :--- | :--- |
| 최소 AIController 가 내장 노드 트리를 PIE 에서 돌리고 타임라인으로 전환 순서 확인 | **통과** | S1 |
| 이벤트 전송과 전환을 따로 판정, 이벤트로 전환 발생 | **통과** | S1 · S2 |
| 런타임 스폰 · 레벨 배치 양쪽에서 트리 시작 | **통과** | S1 · S2b · S4 |
| `MoveTo` · Property Function · 거리 조건의 실제 동작 | **통과** | S1, 함정은 S5 |
| `Get Actor Location` 미연결 함정의 실제 모습 기록 | **기록함** | S5 |
| 멀티 PIE 에서 서버 월드 인스턴스만 관측 | **통과** | S6 |
| Development · DebugGame 빌드 | **통과** | 최종 코드 기준. 실행은 DebugGame 만 |
| 회귀 `StateTree` · `Runner` · `Smoke` · `AstralBreak` | **통과** | 19 · 4 · 26 · 31 |

## 1. 구현한 것

### 최소 AIController (1단계)

`Source/AstralBreak/Character/Enemy/AstralEnemyController.h` · `.cpp`. `AAIController` + `UStateTreeAIComponent` 1개, 컴포넌트 자동 시작 끔, `bStartAILogicOnPossess = true` 가 전부다. 트리는 C++ 에 고정하지 않고 BP 컴포넌트 참조로 지정한다.

`AstralBreak.Build.cs` 에 `StateTreeModule` · `GameplayStateTreeModule` 추가. UBT 가 요구하지 않아 `.uproject` 는 바꾸지 않았다. `AAstralCombatCharacter` · `BP_TargetDummy` 는 건드리지 않았다.

### `run_state_tree_scenario` (2단계)

| 파일 | 내용 |
| :--- | :--- |
| `Core/AnimMcpStateTreeRuntime.h` · `.cpp` | 시나리오 파싱 · 지연 명령 · 관측 · 판정 함수. PIE 시작 → 스폰 → 프레임별 관측 → 판정 → PIE 종료 |
| `Tools/AnimMcpTools_StateTree.cpp` | Tool 핸들러 — 트리 · 클래스 · 상태 이름 · 태그를 PIE 전에 검증 |
| `Tests/AnimMcpStateTreeTests.cpp` | `16_RuntimeScenario` · `17_ScenarioJudge` · `18_ScenarioRefused`, `08b` 에 PIE 거부 1줄 |
| `Tools/mcp/state_tree_mcp/server.py` | Tool 1개 추가 (총 9개) |
| `AnimGraphMcpEditor.Build.cs` | `AIModule` 추가 |

러너는 수정하지 않았다. `run_anim_scenario` 와 같이 `<클래스> <JSON>` 명령 + `AnimMcpRuntimeScenario` 관측 슬롯을 쓴다.

**`16_RuntimeScenario` 는 시나리오가 없으면 경고만 내고 통과하지 않는다.** `AnimGraphMcp.Runtime` 이 그렇게 해서 검사한 것이 없었다. 필터로 직접 돌리면 엔진 클래스만 쓰는 고정물(`AAIController` + 나중에 붙인 컴포넌트 + `ADefaultPawn`)로 대조 이벤트 · 숨은 전환 · 정상 전환을 실제로 돌린다.

**입력**

```jsonc
{ "asset_path": "/Game/AI/Test/ST_P2_Loop",          // 컴포넌트가 참조하는 트리
  "map": "/Game/Maps/CombatTestMap",
  "pawn_class": "/Game/AI/Test/BP_P2_Enemy",          // spawn_location 이 있으면 스폰, 없으면 배치 인스턴스 필터
  "spawn_location": [1200, -800, 120],
  "player_location": [1400, 800, 120],
  "events": [ { "tag": "GameplayEvent.Parried", "after": 0.5, "expect_transition": false, "window": 0.5 },
              { "tag": "GameplayEvent.Damaged", "when_state": "Idle", "expect_state": "Chase" } ],
  "expect_states": ["Idle", "Chase", "Attack", "Idle"],
  "duration": 20, "start_timeout": 10, "clients": 0, "timeout": 140 }
```

**출력** — `poll_automation_tests` 의 `tests[].observed`

```jsonc
{ "finished_because": "expected",        // expected · tree_ended · duration · instance_not_found · tree_not_started · world_lost · pie_not_started
  "started": true, "started_at": 0.017, "frames": 451, "instances_found": 1,
  "worlds": [ { "name": "CombatTestMap", "net_mode": "Standalone", "observed": true, "instances": 1, "pawns": 1 } ],
  "instance": { "owner": "...", "pawn": "...", "source": "spawned", "running": true },
  "timeline": [ { "t": 1.051, "active_states": ["Root", "Chase"], "run_status": "Running", "state_changes": 2, "pawn_location": [1088.6, -720.8, 89.6] } ],
  "events": [ { "tag": "...", "sent": true, "transitioned": true, "state_changes": 1, "expect_state": "Chase", "reached_expected": true,
                "expect_transition": true, "ok": true, "t_sent": 1.034, "t_transition": 1.051, "states_before": [], "states_after": [] } ],
  "expect": { "states": [], "matched": 4, "ok": true },
  "pawn_start": [], "pawn_end": [], "pawn_travel": 1367.1, "player": {},
  "log": [],                             // PIE 시작 뒤 StateTree · Navigation · PathFollowing 경고 이상
  "candidates": {} }                     // 인스턴스를 못 찾았을 때만 — 폰별 컨트롤러 · 컴포넌트별 트리
```

**이벤트는 세 단계로 판정한다:** `sent`(트리가 실행 중이라 큐에 넣는 호출까지 갔다) · `transitioned`(상태 진입 횟수가 늘었다) · `reached_expected`(기대 상태가 활성으로 보였다). `expect_transition: false` 는 무관한 이벤트의 대조 시험이다.

## 2. 확인한 엔진 API

| 사실 | 근거 | 판정 |
| :--- | :--- | :--- |
| 런타임 스폰은 `Pawn::PostInitializeComponents` → `SpawnDefaultController` 라 컨트롤러 `BeginPlay` 가 `Possess` 보다 먼저다 — 자동 시작이면 컨텍스트 Actor 가 없다 | `Pawn.cpp:155` · `:377` · `:382` | 실측 S3 |
| 레벨 배치는 `Possess` 가 `BeginPlay` 보다 먼저라 자동 시작도 된다 | S3 · S4 대조 | 실측 |
| 시작하지 못한 트리의 `GetStateTreeRunStatus` 는 `Unset` 이다. `Failed` 가 아니다 | S3 | 실측 |
| `GetActiveStateNames` 는 `Root` 를 포함한다. 플러그인 모듈에 `WITH_GAMEPLAY_DEBUGGER` 가 따로 설정 없이 들어온다 | S1 | 실측 |
| `FStateTreeExecutionState::StateChangeCount` 는 상태 진입마다 오른다. 컨텍스트의 `GetStateChangeCount` 는 `WITH_STATETREE_DEBUG` 전용이라 실행 상태를 직접 읽는다 | `StateTreeExecutionTypes.h:1218` · `StateTreeExecutionContext.cpp:3394` | 실측 |
| `StateTreeRef` · `InstanceData` 는 protected 이고 getter 가 없다 — 리플렉션으로 읽는다 | `StateTreeComponent.h:173` · `:183` | 실측 |
| `SendStateTreeEvent` 는 `void` 이고 실행 중이 아니면 경고만 남긴다 — `sent` 는 호출 전에 `IsRunning` 으로 본다 | `StateTreeComponent.cpp:574` | 소스 |
| NavMesh 가 없는 맵에서 `MoveTo` 상태는 이름이 보이지 않고 진입 횟수만 2 오른다. 같은 트리가 NavMesh 있는 맵에서는 진입한다. 로그가 없어 실패 이유를 직접 보지는 못했다 | S1 · S2 · `StateTreeMoveToTask.cpp:145` | 실측 + 소스 |
| 전환이 없는 상태가 끝나면 트리는 `Root` 첫 자식으로 돌아간다 — 멈추지 않는다 | S5 | 실측 |
| `RequestPlaySession` 이 `EditorPlaySettings` 를 복제해 쥔다. 인스턴스를 넘겨 네트 모드 · 인원을 지정할 수 있다 | `PlayLevel.cpp:988` ~ `:992` · S6 | 실측 |
| `PreBeginPIE` 가 메모리의 모든 트리를 컴파일한다 — PIE 시작 때 다른 시험의 `ST_P1_Broken` 컴파일 실패 로그가 나왔다 | 지침서 §2-4 | 실측 (소스 판단이었던 것) |
| 언포제션 때 `StopLogic` 의 컨텍스트 검사가 실패한다. `AAIController::OnUnPossess` 가 폰을 먼저 비운 뒤 `CleanupBrainComponent` 를 부르기 때문이다 | `AIController.cpp:526` · `:544`, 시작한 PIE 종료마다 경고 2줄 | 경고는 실측, `ExitState` 미호출은 소스 판단 |
| BP 인스턴스는 CDO 전체가 아니라 컴파일 · 로드 때 만든 목록으로만 기본값을 복사한다 | `BlueprintGeneratedClass.cpp:752` · `:1245` | 실측 (§4 의 5번) |
| 자동 테스트 중에는 CEF 가속 페인트의 `check` 가 실패한다 | `CEFWebBrowserWindowRHIHelper.cpp:95` · `:241` | 실측 (§4 의 8번) |

## 3. 테스트 결과

시험 애셋은 전부 `/Game/AI/Test/` 다. 트리 2개는 `state-tree-mcp` 로 저작했다(§3-5).

| 애셋 | 내용 |
| :--- | :--- |
| `ST_P2_Loop` | `Idle`(Delay 영구) -`GameplayEvent.Damaged`→ `Chase`(MoveTo 고정 목적지, 거리 ≤ 300 이면) → `Attack`(Delay 1초) → `Idle` |
| `ST_P2_NoInput` | 같은 구조. `Get Actor Location` 입력만 묶지 않았다 |
| `BP_P2_Enemy` · `BP_P2_EnemyController` | `AAstralCombatCharacter` · `AAstralEnemyController` 파생, `AutoPossessAI = PlacedInWorldOrSpawned` |
| `*_NoInput` · `*_AutoStart` | 함정용 · 대조군(자동 시작 켬, Possess 시작 끔) |
| `L_P2_Placed` | 레벨 배치 시험맵. 바닥과 배치 폰 2개. **NavMesh 없음** |

### 3-1. 런타임 스폰 — S1 `CombatTestMap`

경로 탐색이 실제로 됐다. 맵을 고칠 필요가 없었다.

| t | 활성 | 진입 횟수 | 폰 위치 | |
| ---: | :--- | ---: | :--- | :--- |
| 0.017 | Idle | 1 | (1200, -800, 120) | 스폰 |
| 0.529 | Idle | 1 | | `Parried` 전송 — 전환 없음 ✓ |
| 1.034 | Idle | 1 | | `Damaged` 전송 |
| 1.051 | Chase | 2 | (1088.6, -720.8, 89.6) | 전환 |
| 3.234 | Attack | 3 | (1178.2, 503, 89.6) | 목적지까지 거리 298 ≤ 300 |
| 4.234 | Idle | 4 | (1178.2, 503, 89.6) | Delay 1.0초 뒤 |

- **MoveTo**: 약 1,227 cm 이동. 같은 트리가 NavMesh 없는 맵(S2)에서는 진입에 실패하므로 `CombatTestMap` 의 NavMesh 로 길을 찾은 것이다.
- **Property Function + 거리 조건**: 전환 지점의 실제 거리가 임계값에 프레임 하나 차이로 붙는다. `Get Actor Location` 이 실제 폰 위치를 낸다는 뜻이다.
- **플레이어 이동**: `BP_Hero_Vesper_C_0` 를 지정 위치로 옮겼다.
- 첫 0.4초 안의 140 cm 이동은 트리와 무관하다. 트리가 시작되지 않은 S3 과 이벤트 없는 S7 에서 같은 값이 나왔다. 그 스폰 지점의 충돌 밀어내기로 보이며 원인은 조사하지 않았다.

### 3-2. 레벨 배치 — S2 · S2b `L_P2_Placed`

`BP_P2_Enemy_C_1` 에서 트리가 시작됐고(`source: placed`), `Parried` 는 전환 없음, `Damaged` 는 진입 횟수 1 → 3 이었다.

- **S2** 는 `expect_state: Chase` 로 돌려 **의도대로 실패**한다. 이 맵에는 NavMesh 가 없어 `MoveTo` 가 진입 때 실패하고 `Chase` 가 보이지 않는다. 오류 문장이 그대로 말해 준다: *"entered 2 state(s), but 'Chase' was never seen active"*.
- **S2b** 는 같은 입력에서 기대 상태 없이 전환만 판정해 통과한다.

### 3-3. 자동 시작 대조군 — 소스 판단 확인

| | 런타임 스폰 | 레벨 배치 |
| :--- | :--- | :--- |
| 자동 시작 끔 + Possess 시작 (`AAstralEnemyController`) | **시작** S1 | **시작** S2b |
| 자동 시작 켬 + Possess 시작 끔 (대조군) | **시작 안 함** S3 | **시작** S4 |

S3 의 관측: `started: false`, `run_status: Unset`, `log` 에 `Could not find context actor of type AstralCombatCharacter` 외 2줄. 이 잡은 대조군이라 실패가 정상이다.

### 3-4. `Get Actor Location` 입력 미연결 — S5

컴파일 · 저장 · 실행 모두 성공하고 경고도 없다. **`Attack` 에 끝내 들어가지 않는다.**

| t | 활성 | 폰 |
| ---: | :--- | :--- |
| 0.017 | Idle | |
| 0.466 | Chase | |
| 3.004 | Idle | (1194.3, 722, 89.6) — 목적지 도착 |

입력이 비면 `Source` 가 `(0, 0, 0)` 으로 고정된다(`StateTreeActorPropertyFunctions.cpp:16`). 조건은 폰이 어디 있든 원점과 목적지 사이 거리(1,445)를 재므로 거짓이고, 폰은 300 범위를 그대로 지나 목적지까지 간 뒤 `MoveTo` 완료로 상태가 끝나 `Idle` 로 돌아간다. **목표가 원점 근처면 반대로 폰 위치와 상관없이 참이 된다**(소스 판단, 실행 안 함). 어느 쪽이든 트리는 멀쩡해 보인다.

### 3-5. MCP 실사용

- 이 세션에서 `state-tree-mcp` 의 Tool 을 직접 호출했다: `create_state_tree` 2 · `list_state_tree_node_types` · `preview` 1 · `apply` 2.
- `preview` 가 잘못된 벡터 값을 `'Destination' expects an object with fields {X, Y, Z}` 로 잡았고, 고친 배치가 두 트리 모두 첫 적용에 컴파일 · 저장됐다. 프로젝트 클래스를 컨텍스트로 준 스키마 값도 그대로 들어갔다.
- 추가한 `run_state_tree_scenario` 는 이 세션의 MCP 목록에 없다(서버가 Tool 추가 전에 떴다). `.mcp.json` 과 같은 명령으로 stdio 기동해 **Tool 9개**, 거부 호출, 실제 시나리오 1회(통과)를 확인했다. 새 세션부터 목록에 보인다.

### 3-6. 멀티 PIE — S6 (`clients: 1`)

| 월드 | 네트 모드 | 관측 | 인스턴스 | 폰 |
| :--- | :--- | :--- | ---: | ---: |
| CombatTestMap | ListenServer | ○ | 1 | 1 |
| CombatTestMap | Client | | **0** | 1 (복제) |

클라이언트에도 폰은 복제되고 AIController · 트리는 없다. 전환 순서는 Standalone 과 같다.

### 3-7. Automation

최종 코드, DebugGame 에디터, `-unattended`, 한 세션.

| 필터 | 결과 |
| :--- | :--- |
| `AnimGraphMcp.StateTree` | **19 / 19** — Phase 1 의 16 + `16_RuntimeScenario` · `17_ScenarioJudge` · `18_ScenarioRefused` |
| `AnimGraphMcp.Runner` | 4 / 4 |
| `AnimGraphMcp.Smoke` | 26 / 26 |
| `AstralBreak.` | 31 / 31 |

`16_RuntimeScenario` 고정물의 관측: `Bounce`(MoveTo 진입 실패) 이벤트에서 활성은 그대로 `Idle` 인데 진입 횟수가 1 → 3 으로 뛰어 `transitioned: true` 였다. 활성 목록만 비교하던 코드라면 실패했을 경우다.

**시간 초과 경로**: `timeout: 3` 시나리오가 `state: timeout` 으로 끝나고 러너가 PIE 를 닫았으며, 뒤이은 시나리오 2개가 로그를 내며 정상으로 돌았다 — 로그 장치가 풀렸다는 뜻이다.

### 3-8. 빌드

`AstralBreakEditor Win64` Development · DebugGame 둘 다 `Result: Succeeded`(최종 코드). 경고는 컴파일러 버전 안내뿐이다.

## 4. 진행 중 생긴 실패

| # | 증상 | 원인 | 조치 |
| :---: | :--- | :--- | :--- |
| 1 | 컴파일 C2445 | `GetPawn()` 이 `TObjectPtr` 를 돌려줘 삼항식이 모호 | `.Get()` |
| 2 | 링크 실패 | `AAIController` 를 쓰는데 플러그인 모듈이 `AIModule` 에 직접 의존하지 않음 | `Build.cs` 추가 |
| 3 | 도구 목록에 새 Tool 없음 | **내 실수.** 빌드 완료 알림만 보고 `Result:` 를 확인하지 않은 채 에디터를 띄워, 에디터가 DLL 을 잠가 링크가 실패했다 | 에디터를 내리고 재빌드. 이후 `Result: Succeeded` 와 프로세스 소멸을 직접 확인했다 |
| 4 | 원격 파이썬이 에디터를 찾지 못함 | 불명. `bRemoteExecution=True` 인데 바인드 주소 3개 · TTL 2종 모두 노드 0. D-4 범위라 더 파지 않았다 | `-ExecutePythonScript` 로 시험 BP 를 만들었다(스크립트 뒤 에디터가 스스로 닫힌다) |
| 5 | 레벨 배치 인스턴스 없음 | **내 스크립트 순서 오류.** 컴파일 뒤에 CDO 를 써서 같은 세션의 배치 인스턴스가 네이티브 기본값을 받았고, 그 값이 CDO 와 달라 맵에 재정의로 저장됐다. 컨트롤러 문제가 아니다 | 값이 든 상태로 재컴파일, 새 세션에서 재배치. 진단을 위해 `candidates` 추가 |
| 6 | S5 가 함정을 보기 전에 끝남 | **설계 오류.** 기대 순서가 없을 때 이벤트가 끝나면 종료하는 `events_done` 이 `duration` 을 무시했다 | 제거. 기대 순서가 없으면 `duration` 까지 본다 |
| 7 | S2 가 `sent 인데 전환 없음` | **거짓 판정.** `Chase` 가 한 프레임 안에 들어갔다 나와 폴링이 못 봤다 | 전환을 활성 목록이 아니라 `StateChangeCount` 로 판정, 기대 상태 도달을 분리, 고정물에 회귀 추가 |
| 8 | 시간 초과 시험 첫 시도에 에디터 크래시 | **엔진 경합.** 기동 직후 살아 있던 CEF 브라우저가 자동 테스트 중 페인트를 받아 `check(BUseSupportedRHIRenderer())` 실패 — 이 함수는 `GIsAutomationTesting` 이면 거짓이다. 호출 스택에 프로젝트 · 플러그인 코드 없음 | 브리지 준비 뒤 30초 기다리니 재현되지 않았다. 재현 조건은 1회 관찰뿐이고 어떤 위젯의 브라우저인지는 모른다 |

## 5. 미해결

### 사용자 눈 확인 (자동 판정 불가)

Phase 1 의 5건([Phase1Report §5](Phase1Report.md))이 그대로 남아 있다. 이번에 더해진 것:

6. 에디터에서 `BP_P2_EnemyController` 를 열어 `StateTreeComponent` 디테일에 `ST_P2_Loop` 참조가 보이고 다른 트리로 바꿀 수 있는가 — 이번 결정의 트리 지정 방식이고, 값은 스크립트로 넣었다.

`BP_P2_Enemy` 에는 메시가 없어 PIE 화면으로는 볼 것이 없다. 이동은 좌표로 판정했다.

### 돌려 보지 않은 것

- **폰 사망 · 파괴 중의 트리.** `StopLogic` 경고는 PIE 종료 때 관측했고, 게임플레이 중 언포제션은 실행하지 않았다.
- **`ExitState` 가 실제로 불리지 않는지**는 소스 판단이다. 경고만 실측했다.
- **Dedicated Server · 클라이언트 2개 이상.** 리슨 서버 + 클라이언트 1 뿐이다.
- **움직이는 목표 추격.** 목적지는 고정 좌표다. 내장 노드만으로 플레이어를 목표로 줄 방법이 없다(§6).
- **Development 구성 실행.** 빌드까지다.
- **대화형 실행.** 전부 `-unattended` 다.
- **`AnimGraphMcp.Runtime` · `Generation` 회귀.** 지시 범위 밖이고 관련 코드는 주석 한 줄 말고 바뀌지 않았다.

### 알려진 한계

- **타임라인은 프레임 표본이다.** 한 프레임 안의 상태는 이름이 없다. `state_changes` 가 2 이상 뛰면 그런 상태가 있었다는 뜻이고, 어떤 상태였는지는 알 수 없다.
- **전환의 원인은 구분하지 않는다.** 이벤트 전송 뒤 창 안에서 다른 이유로 전환해도 `transitioned` 다. 시험 트리는 이벤트 외에 전환 이유가 없는 상태에서 보내야 한다.
- **기대 순서는 사이에 다른 상태가 끼어도 통과한다.** 엄밀한 순서가 필요하면 `timeline` 을 직접 본다.
- 인스턴스가 여럿이면 이름 순 첫 번째만 관측한다. 개수는 `instances_found` 다.
- 시간 초과 잡에는 `observed` 가 없다.
- `log` 는 경고 이상만 싣는다. `MoveTo` 진입 실패는 로그가 없어 여기 나오지 않는다.
- 시험을 돌릴 때마다 `/Game/AI/Test/` 에 `ST_P1_*` 애셋이 쌓인다(Phase 1 과 같다). `16_RuntimeScenario` 몫이 1개 늘었다.
- 시험 BP · `L_P2_Placed` · `ST_P2_*` 는 Phase 1 의 `ST_P1_Acceptance` 처럼 재실행용으로 남긴다. 미추적 상태다.

## 6. M3 본 작업에서 달라질 것

**반드시 정할 것**

1. **트리가 ASC 보다 먼저 시작한다.** `OnPossess` → `StartLogic` 은 `APawn::PostInitializeComponents` 안에서 돈다. `AAstralCombatCharacter::PostInitializeComponents` 는 `Super` 뒤에 ASC 를 결합하고, 어빌리티 · 장비는 `BeginPlay` 에서 준다. 런타임 스폰 · 레벨 배치 모두 **첫 상태의 `EnterState` 시점에 ASC 결합도, 어빌리티도 없다.** Phase 2 트리는 첫 상태가 Delay 라 드러나지 않았다. 첫 상태에서 GA 를 쓰려면 시작을 늦춰야 한다 — `bStartAILogicOnPossess = false` 로 두고 폰 초기화 완료(InitState) 뒤 `StartLogic` 을 부르는 방식을 권한다.
2. **폰이 사라질 때 트리가 깨끗이 멈추지 않는다.** `OnUnPossess` 는 폰을 비운 뒤 `StopLogic` 을 불러 컨텍스트 검사가 실패한다. 그러면 `Stop` 이 돌지 않아 `ExitState` 가 불리지 않는다(소스 판단). GA 를 돌리는 커스텀 Task 가 정리를 `ExitState` 에 두면 사망 때 새게 된다. `AAstralEnemyController::OnUnPossess` 를 오버라이드해 `Super` 전에 `StopLogic` 을 부르면 된다. 뼈대 범위 밖이라 이번에 넣지 않았다.

**구조 쪽**

3. **스폰 시스템은 `AutoPossessAI` 를 확인해야 한다.** `AAstralCombatCharacter` 기본값은 `PlacedInWorld` 라 런타임 스폰하면 컨트롤러가 없다. 시험 BP 만 `PlacedInWorldOrSpawned` 다. 시나리오는 이 경우를 오류로 알려 준다.
4. **목표를 트리에 넣을 경로가 없다.** AI 스키마가 허용하는 구체 Evaluator 가 엔진에 없고, D-6 때문에 메뉴에 없는 프로퍼티도 묶을 수 없다. `UAstralThreatComponent` 의 대상을 내는 커스텀 Evaluator 또는 Task 출력이 필요하다. `MoveTo.TargetActor` 에 묶으면 `bTrackMovingGoal` 기본값으로 대상을 따라가게 돼 있다(소스 판단, 실행 안 함).
5. **`ST_Enemy_Melee` 에는 실패 전환이 필요하다.** `MoveTo` 가 진입에서 실패하면 상태가 보이지도 않고 로그도 없이 첫 상태로 돌아간다. 경로가 없는 플레이어를 만나면 몬스터가 `Idle` 에서 조용히 멈춘 것처럼 보인다. `OnStateFailed` 전환을 넣고, 시나리오에서는 `state_changes` 로 본다.
6. **`MoveTo` 가 끝나면 상태도 끝난다.** 도착 전에 공격으로 넘길 거리 임계값이 `AcceptableRadius` 보다 커야 하고, 아니면 `OnStateCompleted` 전환을 둔다.
7. **`Get Actor Location` 입력을 도구가 잡아 주지 않는다.** S5 처럼 조용하다. `ST_Enemy_Melee` 저작 때 `inspect` 로 입력 바인딩을 확인한다. 필요하면 Apply 에 경고를 더할 수 있다 — 지금은 넣지 않았다.

**운용**

8. **에디터 주기에 30초 대기를 둔다.** §4 의 8번. `CLAUDE.md` 의 에디터 주기에는 이 단계가 없다. 1회 관찰이라 규칙으로 올릴지는 사용자 판단이다.
9. **시험 BP 는 값을 쓴 뒤 컴파일한다.** `ab_blueprint.build_from_spec` 은 이 순서가 맞다. 컴파일 뒤에 CDO 를 쓰면 §4 의 5번이 난다.
10. **원격 파이썬이 지금 동작하지 않는다.** `Tools/scripts/*` 프로브가 이 경로를 쓴다. `-ExecutePythonScript` 는 PIE 를 구동할 수 없으므로 PIE 프로브가 필요해지면 먼저 고쳐야 한다.

**데이터 모델** — Phase 1 데이터 모델은 바뀌지 않았다. 이번에 더해진 계약은 §1 의 입출력이다.
