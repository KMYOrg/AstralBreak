# StateTree 자동화 Phase 0 — 타당성 실험 결과

작성일: 2026-11-04 · 대상: UE 5.7.4 · 기준 문서: [DevelopmentGuide.md](DevelopmentGuide.md) · 엔진 근거: [APIResearch.md](APIResearch.md)

## 결론

Phase 1 은 바로 착수할 수 있다. 복구 방식은 'Undo + 재컴파일, 안 되면 재로드' 2단으로 확정했다(§4). 다만 시작 전에 사용자가 정할 것이 둘 있다(§6 D-5 · D-6). D-7 은 해결했다.

| # | 실험 | 판정 | 한 줄 |
| :---: | :--- | :--- | :--- |
| E1 | 생성 · 컴파일 | **통과** | 창 없이 생성 · 컴파일 · 저장 |
| E2 | 스키마 클래스 설정 | **통과** | 프로젝트 클래스가 바인딩 후보에 나온다. 메뉴 노출은 별도 규칙 |
| E3 | 구조체 경로로 노드 추가 | **통과** | `MoveTo` · `CompareDistance` 트리 컴파일 |
| E4 | 바인딩 정상 · 오타 | **통과** | 사전 검증이 전부 잡는다. 조용한 삭제 재현, 규칙은 교정본보다 좁다 |
| E5 | 재로드 복구 | **통과** | 닫힘 · 열림 모두 복원. 단 Undo 버퍼 전체 소실 → **1안을 Undo 복구로 변경** |
| E6 | 재시작 왕복 | **통과** | 리비전 · 파일 · GUID · 컨텍스트 클래스 동일 |
| E7 | 열린 편집기 외부 수정 | **자동 판정 통과 · 화면은 사람 확인 필요** | 뷰 행 수 · Undo · Redo 확인 |

크래시 1회 · 회귀 실패 1회가 있었고 원인은 둘 다 확정했다(§3). 보고서에 숨긴 실패는 없다.

## 1. 환경

- 시험 코드: `Plugins/AnimGraphMcp/Source/AnimGraphMcpEditor/Private/Tests/AnimMcpStateTreeFeasibilityTests.cpp` — `AnimGraphMcp.StateTree.Phase0.*` 13개 (Phase 1 에서 `AnimMcpStateTreeTests.cpp` 로 대체하고 지웠다 — [Phase1Report.md](Phase1Report.md))
- 빌드: `AstralBreakEditor Win64` Development · DebugGame 둘 다 성공(최종 코드 기준)
- 실행: `UnrealEditor-Win64-DebugGame.exe -log -unattended` + `run_automation_tests`. 측정값은 결과의 `observed` 로 받았다. 실행은 DebugGame 만이고 Development 는 빌드까지다
- 최종 회귀: 재시작 직후 한 세션에서 E6b · E1 · E2 · E3 · E4 · E5a · E5b · E5c · E5d · E5e · E6a · E7 12개 통과, 이어서 새 세션에서 E7b 통과. `ensure_count` 전부 0
- 러너 수정 뒤 회귀(2026-11-04): `AnimGraphMcp.Smoke` 26 · `AnimGraphMcp.Runtime` 1 · `AnimGraphMcp.Runner` 4 · Phase 0 13개 통과. E6b 와 E7b 는 E6a 뒤 재시작한 세션에서 돌렸다
- 시험 애셋은 `/Game/AI/Test/` 에만 만들었다. 운영 콘텐츠 · `Source/AstralBreak` 변경 없음
- `Config/DefaultEngine.ini` 의 `+StateTreeEditPaths` 는 넣지 않았다. Phase 0 에는 읽는 코드가 없다 — Phase 1 에서 읽는 코드와 함께 넣는다

## 2. 실험별 결과

### E1 — `CreateAsset` + `SetSchemaClass`

**입력:** `/Script/GameplayStateTreeModule.StateTreeAIComponentSchema` 를 경로로 찾아 팩토리에 넣고 `IAssetTools::CreateAsset`. `FApp::IsUnattended()=true` 확인.

| 측정 | 값 |
| :--- | :--- |
| 생성 시간 | 0.002초 |
| 창 | 없음 (테스트가 동기로 끝남) |
| 컴파일 상태 | `IsReadyToRun=true`, 리비전 = 컴파일 해시 |
| 생성 직후 패키지 | 더티 — 저장은 따로 해야 한다 |
| 같은 이름 재생성 | `nullptr` + `Error` 로그, 기존 애셋 유지 |
| 스키마 없는 팩토리 | `nullptr`, 빈 패키지가 메모리에 남음 |

**판정: 통과.** 대화형 실행의 덮어쓰기 창 경로는 돌리지 않았다(소스만 확인). Tool 은 `CreateAsset` 전에 존재 · 스키마 · 이름을 직접 확인한다.

### E2 — 스키마 클래스

**입력:** `ContextActorClass = AAstralCombatCharacter`, `AIControllerClass = ADetourCrowdAIController`(프로젝트에 AIController 가 아직 없어 엔진 파생 클래스로 대체). 프로퍼티 쓰기 + `PostEditChangeChainProperty`.

| 측정 | 값 |
| :--- | :--- |
| 기본 Desc | `Pawn` · `AIController` |
| 알림 없이 값만 쓴 대조군 | Desc 는 `Pawn` 그대로 |
| 알림 뒤 Desc | 프로젝트 클래스 · 지정 컨트롤러 |
| `GetBindableStructs` 후보 | `Parameters`, `Actor:AstralCombatCharacter`, `AIController:DetourCrowdAIController` |
| 프로젝트 프로퍼티 11개 | 경로 해석 11개 전부 성공, 엔진 메뉴 노출 3개(`AllowPrivateAccess` 컴포넌트) |
| `Actor.bTelegraphAttackEnabled` → `bLeft` 바인딩 | 사전 검증 `OK`(`ui_bindable=false`), 컴파일 성공, 손실 없음 |
| 컴파일 산출물 컨텍스트 | 프로젝트 클래스 반영 |
| 잘못된 클래스(`AIControllerClass` 에 Actor) | 도구 쪽 검사로 거부 |

**판정: 통과.** 단서: 프로젝트 프로퍼티는 '후보에 나온다'와 '메뉴에서 고를 수 있다'가 다르다. §6 D-6.

### E3 — 구조체 경로로 네이티브 노드

**입력:** `FindObject` 로 구조체를 찾고 §2-3 절차로 Idle(Delay) · Chase(MoveTo) · 거리 조건 전환을 구성.

| 측정 | 값 |
| :--- | :--- |
| AI 스키마 허용 Task · Condition | 5개 · 13개 (`MoveTo` · `Delay` · `CompareDistance` 포함) |
| `MoveTo` 허용 | AI 스키마 예, Component 스키마 아니오 |
| 컴파일 | 성공, 메시지 0, 노드 · 바인딩 손실 0 |
| 컴파일된 상태 수 | 3 |
| 구조체 ID 12개 | 중복 없음 |

**판정: 통과.** `FStateTreeDelayTask` 는 Private 헤더라 `AddTask<T>` 로는 쓸 수 없었을 노드다 — 경로 방식이 더 넓다.

### E4 — 바인딩

**입력:** 케이스마다 새 트리를 만들어 사전 검증을 돌린 뒤, 검증을 무시하고 강제로 바인딩을 넣어 컴파일했다.

| 케이스 | 사전 검증 | 컴파일 | 바인딩 | 비고 |
| :--- | :--- | :--- | :--- | :--- |
| 정상 — 루트 파라미터 | `OK` | 성공 | 2 → 2 | |
| 정상 — 같은 상태의 Task 인스턴스 | `OK` | 성공 | 2 → 2 | |
| 프로모션 float → double | `OK` | 성공 | 2 → 2 | 거부하면 안 됨 |
| **소스 오타 · 비필수 대상** | `BAD_SOURCE_PATH` | **성공** | **2 → 1** | 메시지 · 로그 0. §2-4 재현 |
| **소스 오타 · 필수 Input** | `BAD_SOURCE_PATH` | 실패 | **1 → 0** | 메시지는 '바인딩 없음' — 오타를 말하지 않음 |
| 컨텍스트 소스 오타 | `BAD_SOURCE_PATH` | 실패 | 2 → 2 | 조용히 지워지지 **않음** — 교정본과 다름 |
| **대상 오타** | `BAD_TARGET_PATH` | **성공** | **2 → 1** | 메시지 · 로그 0 |
| 범위 밖 소스 | `BINDING_OUT_OF_SCOPE` | 실패 | 2 → 2 | |
| 타입 불일치 bool → FVector | `INCOMPATIBLE_TYPES` | 실패 | 2 → 2 | |
| `Actor.RootComponent.RelativeLocation` | `OK`(`ui_bindable=false`) | 성공 | 2 → 2 | 메뉴에 없는 경로 |
| Property Function `Get Actor Location` | `OK` | 성공 | 2 → 2 | 메뉴에 있는 경로 |

**판정: 통과.** 사전 검증이 모든 불량을 잡았고, 조용한 삭제가 재현됐다. 교정본 §2-4 는 세 가지가 틀려서 고쳤다: ① 컨텍스트 소스 오타는 지워지지 않고 컴파일 오류다. ② 대상 오타도 지워진다. ③ 삭제 로그는 `Log` 등급이 아니라 기본 설정에서 **아예 안 남는다.**

### E5 — 복구 (가장 중요)

**입력:** 저장된 트리에 필수 Input 미연결 조건을 넣어 컴파일 실패 → `ResetCompiled` 피해를 만든 뒤 복구했다.

피해 상태는 모든 경우 같았다: `IsReadyToRun=false`, 컴파일 해시 0, 컴파일된 상태 0, 패키지 더티, 디스크 파일 MD5 불변.

| 측정 | E5a 재로드 · 편집기 닫힘 | E5b 재로드 · 편집기 열림 | E5c Undo · 닫힘 | E5d Undo · 열림 |
| :--- | :--- | :--- | :--- | :--- |
| 리비전 복원 | ✓ | ✓ | ✓ | ✓ |
| 컴파일 해시 · 실행 가능 복원 | ✓ | ✓ | ✓(재컴파일 1회) | ✓(재컴파일 1회) |
| 패키지 깨끗 | ✓ | ✓ | ✓ | ✓ |
| 디스크 불변 | ✓ | ✓ | 시험 안 함 | ✓ |
| 소요 시간 | 0.16초 | 0.33 ~ 0.36초 | 측정 안 함 | 0.012 ~ 0.017초 |
| 객체 | 교체, 옛 포인터 무효 | 교체, 옛 포인터 무효 | 유지 | 유지 |
| 편집기 | — | 닫혔다가 다시 열림(1개) | — | 그대로 |
| 뷰모델 | — | 새 객체, 새 애셋을 가리킴 | — | 그대로 |
| 트리 뷰 행 | — | 3행 유지 | — | 3행 |
| **Undo 큐** | 측정 안 함 | **1 → 0** | 0 → 0 | **1 → 1** |
| 사용자의 앞선 Undo | — | 소실 | — | 정상 실행 |
| 크래시 · ensure | 0 | 0 | 0 | 0 |

**E5e 복구 판정 시험:**

- 컴파일은 성공했지만 바인딩이 줄어든 경우도 Undo + 재컴파일로 리비전이 돌아왔다. `ValidateStateTree` 의 삭제가 `Data->Modify()` 스냅샷으로 복원된다.
- `Modify` 를 빠뜨린 트랜잭션은 **엔진이 큐에서 버린다.** 큐 1 → 1, 맨 위는 `E5e user edit`. 이 상태에서 Undo 하면 사용자의 앞선 편집이 되돌아간다.
- 그 경우 재로드로 넘어가면 리비전이 복원된다. 대가로 큐가 0 이 된다. 다른 애셋의 메모리 편집 내용 자체는 남는다.

**판정: 통과 — 재로드 복구는 동작한다.** 보상 저널 대안은 필요 없다.

다만 **1안은 재로드에서 Undo 로 바꾼다.** 재로드가 실패해서가 아니라, 재로드의 대가가 측정해 보니 커서다. Claude 의 배치 하나가 실패할 때마다 사용자의 Undo 기록이 **모든 애셋에 걸쳐** 사라지고, 열린 창이 닫혔다 열리면 안 된다. Undo 경로는 그 대가가 없다. 약점은 `Modify` 누락에 취약하다는 것인데, 큐 확인과 리비전 비교로 탐지되고 재로드가 받아 준다. 그래서 2단으로 확정한다(§4).

### E6 — 저장 → 재시작 → 재로드

**입력:** 프로젝트 클래스 스키마 · 바인딩 2개 · Property Function 1개 트리. 기준값을 파일에 쓰고 재시작 뒤 첫 로드에서 대조했다.

| 측정 | 결과 |
| :--- | :--- |
| 첫 로드 전 메모리에 없음 | 확인 |
| 리비전 | 동일 (`ec1c101b`, 앞선 회차 `d51a60e9`) |
| 컴파일 해시 · 파일 MD5 | 동일 |
| 바인딩 3 · 노드 3 · 컴파일 상태 3 | 동일 |
| 상태 GUID · 루트 파라미터 GUID | 동일 |
| 컨텍스트 클래스 | `PostLoad` 로 복원 |
| `CompileIfChanged` | 더티 없음, 값 불변 |
| 재컴파일 | 성공, 리비전 불변 |

**판정: 통과.** 정상 종료 뒤 재시작과 크래시 뒤 재시작 둘 다 확인했다.

### E7 — 열린 편집기 외부 수정

**입력:** 편집기를 연 채 트랜잭션 + Builder 로 상태 추가 → `FindViewModel` → `NotifyAssetChangedExternally`. 트리 뷰 행은 위젯 트리에서 `SStateTreeViewRow` 타입 이름으로 셌다(Private 헤더 포함 없음).

| 단계 | 행 수 | 반응 시간 | 리비전 |
| :--- | :---: | :---: | :--- |
| 시작 | 3 | | |
| 외부 추가 + 알림 | 4, 새 상태 이름 표시 | 0.02초 | 변경 |
| Undo | 3 | 0.03초 | 원래 값 |
| Redo | 4 | 0.03초 | 추가 값 |
| 컴파일 | | 알림 1회 | |
| 컴파일 뒤 Undo | 3 | 0.03초 | 원래 값, `stale` |

알림 1회당 `OnAssetChanged` 1회, Undo 도 1회. `compile_state` 판정에 필요한 `stale` 이 실제로 나타났다(리비전 ≠ 컴파일 해시, 컴파일 산출물은 4상태 유지).

**E7b:** 창을 최소화하고 외부 수정 → 행 0 유지, 알림은 도착. 복원하면 즉시 4행.

**판정: 자동으로 잴 수 있는 것은 통과.** 실제 화면은 사람 확인이 필요하다(§7).

## 3. 진행 중 생긴 실패

### E7 첫 실행 — 에디터 크래시

증상: `Assertion failed: GIsAutomationTesting` (`AutomationTest.cpp:715`) ← `AnimMcpAutomationRunner.cpp:99` ← `FTSTicker`. StateTree 호출 스택 없음.

원인: **기존 러너의 경합 버그.** 엔진 Automation 워커가 프레임마다 러너보다 먼저 돌면서, latent 큐가 비어 있으면 스스로 `StopTest` 를 부른다(APIResearch §13). latent 명령이 러너 호출에서 끝나면 그 다음 프레임에 워커가 먼저 끝내 버리고, 러너는 `check` 에 걸린다. 세션당 한 번, latent 명령이 끝나는 호출 위치에 따라 난다. 지금까지 안 드러난 것은 시간 대기로 끝나는 명령이 우연히 워커 호출에서 끝났기 때문이다.

조치: 러너 수정은 Phase 0 승인 범위 밖이라 처음에는 시험 쪽에서 피했다(`FWorkerSafeLatentCommand` — 종료를 프레임 첫 호출로 미룸). 이후 러너를 고치고 우회 코드를 지웠다(§6 D-7).

### 첫 회귀 — E5d · E7 의 뷰 판정 실패

증상: 데이터 · 알림 · Undo 판정은 전부 통과. 위젯 행 판정만 실패, 행 0 이 6초간 유지.

경위: 같은 순서로 재시작 뒤 다시 돌리니 12개 전부 통과했다. 창 상태를 기록하도록 시험을 고친 뒤에도 재현되지 않았다.

원인: E7b 로 재현했다. 뷰는 알림을 받으면 행을 즉시 지우고 페인트 때 다시 만든다. 창이 그려지지 않으면 행 0 이 유지되고, 복원하면 바로 돌아온다.

**확정한 것은 '창이 그려지지 않으면 이 증상이 난다'까지다.** 그 실패 순간에 창이 실제로 최소화돼 있었는지는 창 상태 기록을 넣기 전이라 증거가 없다. 멈춤 버그가 아니라는 것은 E7b 로 확인했다.

추가로, 초기 시험의 '없어졌다' 판정은 행 0 인 순간에도 통과하는 약한 판정이었다. 행 수까지 맞아야 통과하도록 고친 뒤의 값이 §2 표다.

### 빌드

첫 빌드에서 `StateTreeEditorSchema.h` 포함 누락 1건을 고쳤다. `FClassProperty::MetaClass` 가 private 이라 이름 표로 바꿨다.

## 4. 확정 설계

### 복구 (교정본 §5 6단계 교체)

```text
적용 전:  더티면 거부 · revision_before 기록 · QueueBefore = Trans->GetQueueLength()
적용:     FScopedTransaction { Data->Modify(); 바꾸는 상태 Modify(); Builder API }  ← 컴파일 전에 닫는다
컴파일:   트랜잭션 밖에서. 전후 바인딩 · 노드 수 비교
실패 또는 fixups:
  1단 Undo    Queue == QueueBefore + 1 이면 UndoTransaction(false) → CompileStateTree
              → 리비전 == revision_before && IsReadyToRun 이면 끝 (rollback.method = "undo")
  2단 재로드  그 밖의 모든 경우 → ReloadPackages(AssumePositive) → 포인터 전부 다시 찾기
              → 리비전 == revision_before 이면 끝 (rollback.method = "reload", undo_history_cleared = true)
  둘 다 실패  rollback_verified = false 로 보고. 애셋 상태를 지어내지 않는다
```

이 순서가 성립하는 근거:

- 큐 확인이 없으면 사용자 작업을 되돌린다 — E5e 실측. 생략 금지.
- 재로드 경로는 GC 가 돌아 모든 raw 포인터가 무효다 — `State*` · `FStateTreeEditorNode*` 를 들고 넘어가면 안 된다.
- 트랜잭션을 연 채 재로드하면 안 된다 — `UTransBuffer::Reset` 이 취소하고 버퍼를 비운다.
- 컴파일을 트랜잭션 밖에 두어야 성공 시 컴파일 결과가 Undo 에 묶이지 않는다. 사용자가 나중에 Undo 하면 `stale` 로 보인다(E7) — 정상 동작이다.

`revert_state_tree` 는 Undo 대상이 없으므로 재로드만 쓴다. 응답에 `undo_history_cleared` · `editor_reopened` 를 싣는다.

### 생성

`create_state_tree` 순서: 경로 · 이름 형식 → 허용 경로 → 존재 확인(`ALREADY_EXISTS`) → 스키마 클래스(`UStateTreeSchema` 파생 · 비추상) → `CreateAsset` → `schema_properties` 설정 + 알림 → 재컴파일 → 저장.

`schema_properties` 의 기대 기반 클래스는 Tool 안의 이름 표로 둔다(`ContextActorClass` → `AActor`, `AIControllerClass` → `/Script/AIModule.AIController`).

### 사전 검증

시험 코드 `PreflightBinding` 을 그대로 옮긴다. 판단 순서: 범위 → 소스 경로 → 대상 경로 → 메뉴 노출 → 타입.

| 코드 | 조건 |
| :--- | :--- |
| `BINDING_OUT_OF_SCOPE` | 소스가 `GetBindableStructs` 에 없음 |
| `BAD_SOURCE_PATH` | 값 뷰가 있으면 `ResolveIndirectionsWithValue`, 없으면 `ResolveIndirections` 실패 |
| `BAD_TARGET_PATH` | 대상 경로 해석 실패 또는 빈 경로 |
| `INCOMPATIBLE_TYPES` | `GetPropertyCompatibility == Incompatible`. 빈 소스 경로는 `IsChildOf` |

### `compile_state`

| 값 | 조건 |
| :--- | :--- |
| `up_to_date` | `IsReadyToRun` 이고 리비전 == 컴파일 해시 |
| `stale` | 컴파일 해시 ≠ 0 이고 리비전 ≠ 컴파일 해시 |
| `failed` | 컴파일 해시 == 0 |

## 5. 교정본에서 바꾼 것

| 절 | 무엇을 | 왜 |
| :--- | :--- | :--- |
| 머리말 | 상태를 'Phase 0 완료'로 | |
| §2-1 | 의존성에 `PropertyBindingUtilsEditor` 추가 | `IsPropertyBindable` export |
| §2-2 | 사전 확인 필요 · `MetaClass` private 추가 | E1 · 컴파일 오류 |
| §2-3 | 경로 방식 실측 · Private 헤더 노드 | E3 |
| §2-4 | 삭제 규칙 네 갈래로 정정, 로그 없음, 로드 시 컴파일 추가 | E4 · E5 |
| §2-7 | 메뉴 규칙 · 빈 경로 · Property Function 추가 | E2 · E4 |
| §2-9 | 트리 뷰 동작 · 페인트 의존 추가 | E7 · E7b |
| §3 | 의존성 · ini 시점 | |
| §4 | `create_state_tree` 오류 · 롤백 응답 형식 | §4 |
| §5 | 6단계를 2단 복구로 교체, 보상 저널 대안 삭제 | E5 · E5e |
| §7 | Phase 0 완료 표시 · 결과 링크 | |
| §8 | 필수 항목 3개 추가 | E5e · E4 · E2 |
| §9 | 금지 사항 추가 | E5e |
| §10 | D-5 ~ D-7 추가 | §6 |

## 6. 정할 것

| # | 내용 | 추천 |
| :---: | :--- | :--- |
| D-5 | **Phase 1 완료 기준의 빈틈.** `Idle → Chase → Attack` 을 내장 노드로 만들려면 `CompareDistance.Source`(필수 FVector)에 뭔가 묶어야 하는데, 지금 op 목록은 파라미터 추가도 Property Function 도 없다. `Actor.RootComponent...` 경로는 컴파일은 되지만 메뉴에 없는 경로다 | `bind_property_function { function, output, target }` op 하나를 Phase 1 에 추가. 공개 API 로 되고(E4) 재시작 왕복도 확인됐다(E6). 입력은 기존 `bind_property` 로 묶는다. Property Function 은 §7 Phase 3 항목이었으니 범위 변경이다 |
| D-6 | 메뉴에 없는 프로퍼티(`ui_bindable=false`)를 도구가 묶어도 되는가. 컴파일은 되지만 사용자가 에디터에서 같은 바인딩을 다시 만들 수 없고, 런타임 복사는 미확인이다 | 거부(`NOT_BINDABLE`). M3 C++ 에서 필요한 프로퍼티에 `AllowPrivateAccess` 를 달거나 Evaluator 출력으로 낸다. Phase 1 완료 기준 '사용자가 에디터에서 수동 편집 가능'과 맞는다 |
| D-7 | `AnimMcpAutomationRunner` 경합 수정 시점 | **해결(2026-11-04).** 러너가 `ExecuteLatentCommands` 뒤 `IsLatentCommandQueueEmpty()` 를 보고 같은 호출에서 끝낸다(APIResearch §13). 표지 명령 방식은 `Update` 안에서 넣은 명령이 표지 뒤에 붙어 버려지므로 쓰지 않았다. 회귀 시험 `AnimGraphMcp.Runner.*` |

## 7. 미해결 · 사람 확인

**사람 눈 확인이 필요한 것** — 위젯 행 수로는 알 수 없다. Phase 0 시험 애셋은 정리했으므로 Phase 1 이 만든 애셋으로 확인한다:

1. 재로드 복구로 편집기가 닫혔다 열릴 때 탭 위치 · 레이아웃 · 선택 상태가 어떻게 보이는지 (이제 2단 경로에서만 일어남)
2. 외부 수정 뒤 트리 뷰가 화면에서 정상으로 보이는지 — 들여쓰기 · 작업 아이콘 · 전환 표시
3. **상태를 선택해 디테일 패널을 띄워 둔 채** 외부 수정 · Undo 로 그 상태가 사라질 때 — 시험은 선택 없이 돌렸다
4. 도구가 만든 애셋을 열어 Property Function 바인딩이 일반 바인딩처럼 보이고 손으로 고칠 수 있는지

**돌려 보지 않은 것:**

- 런타임: PIE 실행이 없다. protected 프로퍼티 · `RootComponent` 경로 · Property Function 의 런타임 복사는 컴파일까지만 확인했다
- 대화형 덮어쓰기 창 경로 — 소스만
- 재로드 대상을 참조하는 다른 애셋이 있을 때 — 소스만. 참조 애셋 편집기까지 닫혔다 열린다
- 큰 맵에서의 재로드 비용 — 빈 맵에 가까운 조건의 0.16 ~ 0.36초다
- 컴파일을 트랜잭션 안에서 돌리는 경로 — 밖에서만 시험했다
- 복제 · `PreBeginPIE` 동작은 §2 의 소스 근거 그대로이고 실행하지 않았다
- `E2` 의 AI 컨트롤러는 엔진 파생 클래스로 시험했다. 프로젝트 AIController 는 M3 에서 생긴다

**알려진 한계:** 로드 시 조용한 바인딩 삭제(APIResearch §5)는 도구가 막을 수 없다. C++ 프로퍼티 이름을 바꾸면 그 애셋을 로드하는 순간 바인딩이 사라지고 더티 표시도 없다. Phase 1 은 `inspect_state_tree` 로 보이는 것 이상을 보장하지 못한다.

## 8. Phase 1 에서 달라질 것

**API · 구현**

- `Build.cs` 의존성은 이미 들어갔다(`Slate` · `SlateCore` 는 시험용 — Phase 1 시험이 위젯을 안 보면 뺀다)
- `[AnimGraphMcp] +StateTreeEditPaths=/Game/AI/` 와 이를 읽는 코드를 함께 추가
- `AnimMcpStateTreeFeasibilityTests.cpp` 의 함수를 `Core/` 로 옮기고, Phase 0 시험은 §8 필수 항목으로 대체
- 노드 타입 이름은 전체 경로(`/Script/Module.Struct`)가 기준 — `list_state_tree_node_types` 가 이 값을 돌려준다

**데이터 모델**

```jsonc
// apply_state_tree_operations 실패 응답의 error.details
{
  "stage": "compile",                 // preflight · apply · compile · fixups · save
  "messages": [ /* §2-5 */ ],
  "fixups": [ { "kind": "binding_removed", "target": "..." } ],
  "rollback": {
    "verified": true,
    "method": "undo",                 // undo · reload
    "undo_history_cleared": false,    // reload 면 true
    "editor_reopened": false,         // reload 이고 편집기가 열려 있었으면 true
    "revision": "28ac8ef9"
  }
}
```

- `rollback_verified` 단일 값을 위 객체로 넓힌다
- `compile_state` 는 §4 표 세 값
- 사전 검증 오류 코드 네 개 + D-6 결정 시 `NOT_BINDABLE`
- D-5 결정 시 op `bind_property_function`
