# AI Animation Blueprint Automation
## 개발 지침서 (개정 3판) — Phase 6 착수용 핸드오프

> 작성 2026-10-16 · 브랜치 `feat/ai_auto_ABP` · 기준 엔진 UE 5.7.4 소스 빌드 (`D:/UnrealSource/UnrealEngine-5.7.4-release`)
> Phase 5 까지 구현·커밋된 상태에서 **Phase 6(고급·안정화)** 을 6-1 ~ 6-6 으로 나눠 착수하기 위한 문서다.
> 설계 근거·API 검증표·각 Phase 결과는 [animbp-automation-phase1.md](animbp-automation-phase1.md)(§B · §C · §F · "Phase 2/2.5/3/4/5 결과"), 환경·아키텍처·op 사전·작업 규칙은 [animbp-automation-handoff-phase5.md](animbp-automation-handoff-phase5.md)(§2 · §4 · §8 · §9 · §10 · §16) 에 있다. **이 문서는 두 문서를 대체하지 않고 Phase 6 범위만 더한다.** 구조를 재논의하기 전에 phase1 문서를 먼저 읽는다.

---

### 1. 현재 상태 (Phase 5 종료, 2026-10-16)

| 목표(최초 지침서) | 상태 | 비고 |
| :--- | :---: | :--- |
| AnimBP 생성·조회 | ✅ | |
| AnimGraph · State Machine 구조 분석 | ✅ | alias·conduit 는 **조회만** (`kind`) |
| 노드 생성·수정·삭제 · 핀 연결 | ✅ | op 12종 + VariableGet 노드 · LayerSetup (Phase 5) |
| State Machine · State · Transition 구성 | ✅ 6-1 (2026-10-16) | alias · conduit · rename · 같은 배치 `graph:{ref}`·`result_of`. 결과는 phase1 문서 "Phase 6-1 결과" |
| Transition Rule | ✅ | JSON AST, 멱등 |
| AnimSequence · BlendSpace · Montage 연결 | 🔶 | 할당·교체 가능. **BlendSpace 생성 미구현** |
| C++ AnimInstance 연동 | ✅ | 변수 조회 · 규칙 `var`/`call` · VariableGet 노드 |
| 컴파일 · 저장 · 롤백 | ✅ | 런타임(PIE/Automation) 검증은 없음 |
| 다른 프로젝트에서 재사용 | 🔶 | 플러그인은 프로젝트 비의존이지만 **타 프로젝트 재현 미검증** |

Tool 9개 · op 12종(`add_node`·`connect`·`disconnect`·`remove_node`·`set_property`·`set_asset`·`expose_pin`·`add_blend_pose`·`add_state`·`add_transition`·`set_entry_state`·`set_transition_rule`). 테스트 `phase3_test.py`·`phase4_test.py`(B2 포함)·`phase5_test.py` 전부 PASS, `phase5_build_hero.py` 가 `ABP_Hero_McpBuild` 를 도구만으로 생성. 운영 애셋 `ABP_Hero_Base` 에는 UpperBody 레이어가 적용돼 있다(revision `3c146b5f…`, 사용자 PIE 확인·커밋 완료).

**Phase 6 의 목표**: 위 표의 🔶 를 전부 ✅ 로 만든다. 완료 조건은 두 가지로 요약된다 — ① `phase5_build_hero.py` 가 운영 애셋과 **구조상 1:1**(alias·conduit·이름 포함) 인 AnimBP 를 만든다, ② 다른 UE 5.7 프로젝트에 플러그인 폴더를 복사하는 것만으로 생성→편집→컴파일→저장이 재현된다.

---

### 2. 세부 단계와 의존

```text
6-1 상태머신 완성 ──┐
6-2 애셋 수명      ──┼──▶ 6-5 검증 자동화 ──▶ 6-6 범용화 검증
6-3 BlendSpace 생성 ─┤
6-4 바인딩·레이어   ──┘
```

6-1 ~ 6-4 는 서로 독립이라 순서를 바꿔도 되지만, **6-1 → 6-2 → 6-3 → 6-4** 를 권장한다 (조사 없이 바로 코드로 갈 수 있는 것부터, 눈에 보이는 결과(운영 애셋 1:1 재현)가 먼저 나오게). 6-5 는 앞 단계의 테스트를 묶으므로 뒤에, 6-6 은 전부 끝난 뒤.

각 단계의 공통 완료 기준: Development · DebugGame 빌드 성공(경고 0) · 해당 단계 테스트 PASS · `phase3/4/5_test.py` 회귀 PASS · 에디터 재시작 후 `--recheck` 일치 · phase1 문서에 "Phase 6-N 결과" 절 · 사용자 커밋.

---

### 3. 6-1 상태머신 완성 — Alias · Conduit · 이름 변경 · 같은 배치 ref 그래프

**목표**: 운영 애셋 `Locomotions` 상태머신(상태 5 · alias 4 · conduit 2 · 전이 12) 을 도구로 재현한다. 완료 시 `phase5_build_hero.py` 의 Jump 를 단순화 전이가 아니라 운영과 같은 alias/conduit 구조로 바꾸고, 비교 문서 §4 "의도한 차이" 의 1·2 번이 사라진다.

**3-1. op 추가**

| op | 입력 | 동작 · 롤백 |
| :--- | :--- | :--- |
| `add_conduit` | `ref?, sm:{node\|ref} \| graph, name?, pos?` | `FGraphNodeCreator<UAnimStateConduitNode>` → Finalize(BoundGraph = 전이 그래프 자동 생성 — `UAnimStateConduitNode::PostPlacedNewNode` ❓ 확인) → `OnRenameNode`. 응답 `bound_graph_guid`(규칙 그래프). 롤백 `DestroyNode` |
| `add_state_alias` | `ref?, sm \| graph, name?, pos?, states:[{node\|ref}] \| "global": true` | `FGraphNodeCreator<UAnimStateAliasNode>` → Finalize → `GetAliasedStates()` 에 대상 추가(`TSet<TWeakObjectPtr<UAnimStateNodeBase>>`, AnimStateAliasNode.h:61-62) 또는 `bGlobalAlias=true`(:33) → `OnRenameNode`. 롤백 `DestroyNode` |
| `set_alias_states` | `node\|ref, states:[...] \| global` | 기존 alias 의 대상 교체. 롤백 = 이전 집합 복원 |
| `rename_node` | `node\|ref, name` | 상태·conduit·alias: `UAnimStateNodeBase::OnRenameNode`(AnimStateNodeBase.h:30, 엔진 이름 검증기 `FNameValidatorFactory::MakeValidator` 선행 — Phase 4 `ValidateStateName` 재사용). 상태머신: `UAnimGraphNode_StateMachineBase` 의 `EditorStateMachineGraph` 이름 변경 경로 ❓(`OnRenameNode` 가 `FBlueprintEditorUtils::RenameGraph` 를 부르는지 확인). 롤백 = 이전 이름 |
| `set_conduit_rule` | 없음 — `set_transition_rule` 이 conduit 의 BoundGraph 도 받도록 **확장** | conduit 규칙 그래프는 `UAnimationTransitionGraph` 와 같은 클래스인지 ❓ (운영 덤프: conduit `bound_graph_guid` 가 `AnimationTransitionGraph` 로 보고됨 — Inspector 가 이미 TransitionResult 를 찾는다) |

전이 끝점 검증(`ValidateTransitionEndpoints`) 은 alias·conduit 를 허용해야 한다 (운영: `JumpSources(alias) → JumpSelector(conduit)`, `EndInAir(conduit) → IdleAlias(alias)`). alias 는 **출력 전용**(들어오는 전이는 `bGlobalAlias` 아닌 경우도 ❓ — 운영 `IdleAlias`·`MoveAlias` 는 In 핀이 연결돼 있으므로 양방향 가능으로 보임, 소스로 확인). `remove_node` 의 전이 연쇄는 alias·conduit 에도 그대로.

**3-2. 같은 배치 ref 그래프**: `add_node`·`connect` 의 `graph` 에 `{"ref": "<상태 ref>"}` 허용 → 그 상태의 BoundGraph. `ResolveAddNode` 에서 `graph` 가 객체면 ref 표에서 상태 노드를 찾아 `GetBoundGraph()`. Preview 단계에서 미생성 ref 면 `DeferredNote`. conduit 의 그래프는 규칙 그래프이므로 **거부**(규칙은 `set_transition_rule` 로).

**3-3. Inspector**: `state_machines[].states[]` 에 alias 의 `aliased_states[]`·`global`, conduit 의 `rule_source`·`rule_generated`(전이와 같은 필드). 상태머신 이름은 이미 `name`.

**3-4. 엔진 소스 확인 항목 (❓ → 코드 전에 경로를 남긴다)**
- `Editor/AnimGraph/Private/AnimStateAliasNode.cpp` — `PostPlacedNewNode`(이름 자동 생성), `AllocateDefaultPins`(In/Out 핀 이름), `RebuildAliasedStateNodeReferences`, `ValidateNodeDuringCompilation`(대상 0개·자기 상태머신 밖 상태 거부 규칙).
- `Editor/AnimGraph/Private/AnimStateConduitNode.cpp` — `PostPlacedNewNode` 가 BoundGraph(`UAnimationTransitionGraph`?) 를 만드는지, Result 노드 클래스.
- `Editor/AnimGraph/Private/AnimationStateMachineSchema.cpp` — `CanCreateConnection` 의 alias/conduit 규칙(어느 방향이 허용되는가), `CreateConnections`.
- `Editor/AnimGraph/Private/AnimGraphNode_StateMachineBase.cpp` — `OnRenameNode` → 그래프 이름 변경 경로, `MakeNameValidator`.

**3-5. 테스트**: `phase6_1_test.py` — conduit 1 · alias 2(지정·global) · 이름 변경(상태·상태머신, 중복 거부) · 같은 배치 `graph:{ref}` 로 상태 내부 채우기 · alias→conduit→상태 전이 · conduit 규칙 · 거부(상태머신 밖 상태 alias, 빈 alias, conduit 에 add_node, 이름 중복) · 롤백 · `--recheck`. `phase5_build_hero.py` 를 운영 구조로 갱신하고 비교 문서가 "의도한 차이 1·2 없음" 을 출력.

---

### 4. 6-2 애셋 수명 — duplicate · delete · quit_editor

**Tool 추가 3개** (세션 재시작 전까지 HTTP 테스트):

| Tool | 입력 | 구현 |
| :--- | :--- | :--- |
| `duplicate_animation_blueprint` | `source_path, dest_path, overwrite=false` | `UEditorAssetSubsystem::DuplicateAsset(Source, Dest)` (EditorAssetSubsystem.h:185). dest 존재 시 `ASSET_EXISTS`, `overwrite` 면 `DeleteAsset`(:155) 후. 응답 = `get_anim_blueprint_info` + `duplicated:true`. 복제본의 revision 이 원본과 같은지(노드 Guid 가 보존되는지) 실측 ❓ — 다르면 비교 문서에 명시 |
| `delete_animation_blueprint` | `asset_path, confirm:true` | `DeleteAsset`. `confirm` 없으면 거부. 운영 애셋 경로 보호 목록(ini `[AnimGraphMcp] ProtectedAssets=`) ❓ 설계 결정 |
| `quit_editor` | `save_dirty=false` | `RequestEngineExit(TEXT("AnimGraphMcp quit_editor"))` (CoreGlobals.h:417). 응답을 먼저 쓰고 다음 틱에 종료(핸들러 안에서 바로 부르면 응답이 안 나갈 수 있음 — `FTSTicker` 1회 지연 ❓). 더티 패키지가 있으면 `save_dirty` 에 따라 저장 또는 경고 진단 |

`Tools/mcp/wait_for_bridge.py` 의 짝으로 `wait_for_exit.py`(프로세스 종료 폴링) 를 두고, 핸드오프 §16-5 의 `taskkill` 절차를 이것으로 대체한다. 테스트: `phase6_2_test.py` — 복제→편집→저장→재조회, 삭제 보호, quit 뒤 프로세스 소멸.

---

### 5. 6-3 BlendSpace 생성 — `create_blendspace`

**입력** `asset_path, skeleton, dimensions:1|2, axes:[{name, min, max, grid}], samples:[{animation, value:[x,y?]}], overwrite=false`.

**엔진 API (확인됨)**: `UBlendSpaceFactory1D`/`UBlendSpaceFactoryNew`(`TargetSkeleton`, `FactoryCreateNew`; BlendSpaceFactory1D.h:18-36, BlendSpaceFactoryNew.h:18-36) — AnimBP 때처럼 팩토리를 직접 쓰지 않고 `FactoryCreateNew` 가 하는 일을 재현(모달 회피). `UBlendSpace::AddSample(UAnimSequence*, const FVector&)`(BlendSpace.h:618) · `EditSampleValue`(:623) · `DeleteSample`(:632) · `ValidateSampleData`(:614) — 전부 `WITH_EDITOR`. 축은 `FBlendParameter{DisplayName, Min, Max, GridNum}`(:113-130) 이 `BlendParameters[3]`(:907) 에 있다 — **공개 setter 가 없어 보임** ❓ `Editor/UnrealEd/Private/Factories/BlendSpaceFactory*.cpp` 와 `Editor/Persona`(BlendSpace 에디터) 가 축을 어떻게 쓰는지 확인(리플렉션 `ImportText` 로 `BlendParameters` 를 쓰는 방법 포함). 샘플 애니는 같은 스켈레톤이어야 한다(`ValidateSampleData`).

**Inspector**: `list_animation_assets` 응답에 BlendSpace 의 축·샘플 요약을 더한다(`get_blendspace_info` 별도 Tool 은 두지 않는다 — Tool 수 최소 원칙).

**테스트**: `phase6_3_test.py` — `BS_Hero_Locomotion1D` 와 같은 축(`Speed` 0~?·grid)·샘플로 `/Game/Animation/Test/BS_McpTest` 생성 → `BlendSpacePlayer` 에 `set_asset` → 컴파일 0 에러 → 원본과 축·샘플 비교 → 거부(스켈레톤 불일치, 축 범위 밖 샘플, 2D 에 1D 입력).

---

### 6. 6-4 바인딩 · 레이어 — Property Binding 쓰기 · Linked Anim Layer

**6-4a Property Binding**: `bind_pin {node|ref, property, path:["Speed"] | ["Function"]}` · `unbind_pin`. 구조는 `FAnimGraphNodePropertyBinding`(AnimGraphNode_Base.h:138-185: `PinType`, `PropertyName`, `PropertyPath[]`, `ContextId`, `Type: Property|Function`, `bIsBound`) 이 노드의 `PropertyBindings`(TMap ❓ 이름 확인) 에 들어간다. **쓰기 경로는 에디터 UI(`SPropertyBinding`/`FAnimGraphNodeBindingExtension`) 가 어떻게 채우는지** 확인 필요 ❓ — `Editor/AnimGraph/Private/AnimGraphNodeBinding*.cpp`, `AnimBlueprintExtension_PropertyAccess`. 컴파일러가 바인딩을 Property Access 라이브러리로 바꾸므로, 생성 뒤 컴파일 0 에러와 PIE 값 반영을 모두 봐야 한다. 완료 기준: `Speed→X` 를 VariableGet 노드 없이 바인딩으로 걸어 컴파일 0 에러 + Inspector `optional_pins[].bound=true` + revision 에 바인딩 포함(지금은 보존만).

**6-4b Linked Anim Layer**: `add_node class:"AnimGraphNode_LinkedAnimLayer"` + `set_property Layer`(`SetLayerName`/`GetLayerName`, AnimGraphNode_LinkedAnimLayer.h:57-60) · 레이어 인터페이스 함수 그래프 생성(`FBlueprintEditorUtils::AddFunctionGraph` + AnimLayer 메타 ❓) · 인터페이스 구현(`FBlueprintEditorUtils::ImplementNewInterface` ❓). 운영 애셋은 Linked Layer 0 이므로 **Lyra 식 레이어 분리를 쓸지 사용자 결정 뒤** 범위 확정. 쓰지 않기로 하면 6-4b 는 조회(이미 `linked_anim_layers[]`) 로 종료.

**테스트**: `phase6_4_test.py` — 바인딩 생성·해제·롤백·재시작 왕복, (6-4b 진행 시) 레이어 인터페이스 1개·Linked Layer 노드 1개.

---

### 7. 6-5 검증 자동화 — 런타임 검증 · 통합 러너

- **런타임 검증 Tool `run_automation_tests`** `{filter, timeout}` — 기존 `Tools/scripts/run_automation_tests.py`(에디터 콘솔 `Automation RunTests <filter>`, 결과는 로그 폴링) 를 플러그인 안으로: `FAutomationTestFramework` 로 큐잉하고 완료 델리게이트로 결과 수집 ❓(`IAutomationControllerModule` vs `FAutomationTestFramework::Get().RunTest` — 소스 확인). 동기 블로킹이 길면 `start`/`poll` 2단계.
- **AnimBP 런타임 스모크**: 도구가 만든 AnimBP 를 `UAnimInstance` 로 띄워 `Speed` 등을 넣고 포즈가 바뀌는지 보는 Automation 테스트(프로젝트 `Source/AstralBreak/Tests/` 에 C++ 테스트 1개) — 컴파일만으로 못 잡는 오류(빈 상태, 끊긴 캐시) 를 잡는다.
- **통합 러너 `Tools/mcp/run_all.py`**: 에디터 기동(`wait_for_bridge`) → phase3/4/5/6-N 순차 → 저장 → `quit_editor` → 재기동 → 전부 `--recheck` → `quit_editor`. 결과를 `Tools/mcp/results/<date>.json` 에. CI 성격이라 **에디터 2회 기동(약 2×1분)** 이 든다.

---

### 8. 6-6 범용화 검증 — 두 번째 프로젝트 재현

1. **프로젝트 의존 제거 점검**: 플러그인 소스에서 `AstralBreak`·`/Game/Animation/Hero`·`AstralAnimInstance` 문자열 grep → 0 건이어야 한다(테스트 스크립트는 제외). `.mcp.json`·`Tools/mcp` 의 경로가 프로젝트 루트 상대인지 확인(`bridge.PROJECT_DIR` 은 환경변수로 덮어쓸 수 있음).
2. **두 번째 프로젝트**(사용자 결정 §9-2): 빈 UE 5.7.4 C++ 프로젝트에 `Plugins/AnimGraphMcp` 폴더 복사 + `Tools/mcp` 복사 + `.mcp.json` → 빌드 → `smoke_test.py` → Phase 2.5 시나리오(생성→노드→연결→컴파일→저장→재조회) 재현. 스켈레톤은 엔진 마네킹(`/Engine/...` 또는 템플릿 콘텐츠).
3. **문서**: `Tools/mcp/README.md` 를 설치·설정·Tool 목록·op 사전·오류 코드·알려진 제약(Linked Layer·Alias 범위 등) 으로 갱신. 플러그인 `README`(`Plugins/AnimGraphMcp/README.md`) 신설 — 다른 프로젝트 기준 설명.

완료 기준: 두 번째 프로젝트에서 Phase 2.5 재현 PASS + README 만 보고 설치 가능.

---

### 9. 구현 전 사용자와 확정할 것

1. **6-1 alias 방향** — 소스 확인 결과 alias 가 In 전이를 못 받으면 운영의 `IdleAlias`/`MoveAlias` 를 어떻게 다룰지(운영이 실제로 쓰는 방식을 따른다).
2. **6-6 두 번째 프로젝트** — 새 빈 프로젝트(권장, `D:/UE5Projects/AnimMcpSandbox`) vs 기존 프로젝트.
3. **6-4b Linked Layer** — 이 프로젝트가 Lyra 식 레이어 분리를 쓸 계획인지. 아니면 조회로 종료.
4. **6-2 삭제 보호** — 운영 애셋 보호 목록을 ini 로 둘지, `delete` Tool 자체를 두지 않을지.
5. **6-3 축 설정** — 공개 API 가 없으면 리플렉션 `ImportText` 로 `BlendParameters` 를 쓰는 것을 허용할지(허용 목록 원칙과의 균형).

분석·조사·실측은 묻지 않고 진행하고, 위 5개와 조사 결과로 범위가 바뀌는 지점만 코드 전에 묻는다.

---

### 10. 작업 규칙 (phase5 핸드오프 §16 그대로 + 추가)

- §16 전부 유지: Read/Grep 도구 · 엔진 API 는 소스 경로 · 빌드 두 구성(에디터 내리고) · 에디터는 내가 기동·종료 · Git Bash 접두(`MSYS_NO_PATHCONV=1` 은 **`tasklist //FI` 와 충돌** — 같은 셸에서 쓰지 말 것, Phase 5 실측) · `FJsonObject` 공유 금지 · 운영 애셋 `ABP_Hero_Base` 는 읽기만(변경은 사용자 승인 배치만) · 커밋은 사용자 · 새 Tool 은 재시작 전 HTTP 테스트.
- Phase 5 추가 함정: `ExportText_Direct(Delta=null)` 는 0 값을 비운다 → 조회·롤백 저장은 `ExportTextItem_Direct` · 사전 검증은 같은 배치 `add_blend_pose` 를 `PendingBlendPoses` 로 더한다 · 기존 노드의 없는 핀은 사전 검증에서 걸리므로 롤백 테스트는 같은 배치 ref 노드로 · 상체 슬롯은 전신 슬롯 **출력** 뒤에(나란히 두면 몽타주 상체가 덮인다).
- 단계마다 끝나면: phase1 문서 "Phase 6-N 결과" 절 · 이 문서 §1 표 갱신 · 메모리 `project_animbp-automation.md` 갱신 · 변경 파일 목록 + 커밋 메시지 초안.

---

### 11. 산출물 (전체)

- 코드: op 5종(6-1) · Tool 4~5개(6-2 · 6-3 · 6-5) · 바인딩 op 2종(6-4a) · (선택) Linked Layer · `run_all.py` · `wait_for_exit.py`.
- 테스트: `phase6_1_test.py` ~ `phase6_4_test.py` · 런타임 스모크 C++ 테스트 1개 · `run_all.py`.
- 애셋: `ABP_Hero_McpBuild` 가 운영과 1:1 · `BS_McpTest` · 두 번째 프로젝트의 재현 산출.
- 문서: phase1 "Phase 6-1 ~ 6-6 결과" · `Tools/mcp/README.md` · `Plugins/AnimGraphMcp/README.md` · 비교 문서 갱신.

---

### 진행 상황

| 단계 | 상태 |
| :--- | :---: |
| 6-1 상태머신 완성 | ✅ 2026-10-16 — §9-1 은 소스로 해소(전이 대상 alias 는 단일 상태·global 아님). 미커밋 |
| 6-2 애셋 수명 | ⬜ 다음 — §9-4 삭제 보호 확정 뒤 |
| 6-3 ~ 6-6 | ⬜ |

### 최종 지시 (새 세션용 — Phase 6-1 부터; 6-1 완료 뒤에는 6-2 를 같은 틀로)

Phase 6-1(상태머신 완성) 을 수행한다. 먼저 이 문서 전체와 phase1 문서 "Phase 4 결과"·"Phase 5 결과", phase5 핸드오프 §8·§9·§16 을 읽고, 코드 `Core/AnimMcpGraphMutator.cpp`(`AddState`·`AddTransition`·`ValidateTransitionEndpoints`·`CollectLinkedTransitions`) · `Core/AnimMcpOperations.cpp`(`ResolveAddNode`·`Validate`·`ApplyAddState`) · `Core/AnimMcpGraphInspector.cpp`(`state_machines` 뷰) 를 훑는다. 그다음 §3-4 의 엔진 소스 4개를 읽어 alias/conduit 의 생성·연결·이름 규칙을 확정하고(경로를 남긴다), §9-1 이 갈리면 사용자에게 묻는다. 구현 → 두 구성 빌드 → `phase6_1_test.py` + 회귀 → 에디터 재시작 재조회 → `phase5_build_hero.py` 를 운영 구조로 갱신해 비교 문서 §4 의 1·2 가 사라지는 것을 확인 → phase1 문서 "Phase 6-1 결과"·이 문서 §1·메모리 갱신 → 변경 파일 목록과 커밋 메시지 초안 제시. 운영 애셋은 읽기만 한다.
