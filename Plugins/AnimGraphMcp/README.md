# AnimGraph MCP Bridge (`Plugins/AnimGraphMcp`)

실행 중인 Unreal Editor 안에서 Animation Blueprint 를 **생성·조회·편집·컴파일·검증**하게 해 주는 에디터 전용 C++ 플러그인입니다. 바깥의 MCP 서버(`Tools/mcp/anim_graph_mcp/server.py`)가 HTTP/JSON 으로 이 플러그인을 부르고, Claude Code 같은 AI 에이전트는 MCP Tool 로 그 서버를 부릅니다.

```text
AI Agent ─ stdio MCP ─▶ Tools/mcp/anim_graph_mcp/server.py ─ HTTP/JSON 127.0.0.1:18765 ─▶ Plugins/AnimGraphMcp (에디터, 게임 스레드) ─▶ UAnimBlueprint
```

- 엔진: **UE 5.7.4**(소스 빌드에서 검증). 모듈 1개 `AnimGraphMcpEditor`(Type Editor). 프로젝트 코드에 의존하지 않습니다.
- 그래프 조회·편집은 전부 C++ 입니다(Python 래퍼는 `UEdGraph::Nodes`·핀을 노출하지 않음). MCP 서버는 얇은 프록시이고 그래프 로직이 없습니다.
- 수신은 `127.0.0.1` 만, 기동 때마다 바뀌는 토큰으로 보호합니다.

## 설치

1. `Plugins/AnimGraphMcp` 를 프로젝트의 `Plugins/` 아래에 둡니다. 프로젝트는 **C++ 프로젝트**여야 합니다(에디터 모듈을 빌드해야 하므로 `Source/*.Target.cs` 가 필요).
2. `.uproject` 의 `Plugins` 에 등록합니다.
   ```json
   { "Name": "AnimGraphMcp", "Enabled": true }
   ```
3. 에디터 타깃을 빌드합니다(사용하는 구성마다).
   ```
   Engine/Build/BatchFiles/Build.bat <Project>Editor Win64 Development -Project=<path>/<Project>.uproject -WaitMutex -NoHotReload
   ```
4. Python 쪽: `Tools/mcp/` 를 복사하고 venv 를 만듭니다. 프로젝트 루트 `.mcp.json` 이 Claude Code 에 서버를 등록합니다. (자세한 절차는 `Tools/mcp/README.md`)

## 설정 — `Config/DefaultEngine.ini`

```ini
[AnimGraphMcp]
Port=18765                 ; 기본값. 커맨드라인 -AnimGraphMcpPort=18766 으로 인스턴스별 오버라이드
bRequireToken=True         ; Saved/AnimGraphMcp/token 을 헤더 X-AnimMcp-Token 으로 요구 (get_editor_status 만 면제)
bAutoStart=True            ; 에디터 기동 시 리스너 시작. 콘솔 AnimGraphMcp.Start / Stop / Status
+ProtectedAssets=/Game/Characters/Hero/ABP_Hero    ; 삭제·덮어쓰기 거부 (패키지 또는 오브젝트 경로, 정확히 일치)
+ProtectedPaths=/Game/ThirdParty/                   ; 삭제·덮어쓰기 거부 (패키지 경로 접두)
+SmokeTestPaths=/Game/Animation                     ; 스모크 테스트가 여는 AnimBP 경로 (생략 시 /Game/Animation)
```

보호 목록은 **파괴 연산만** 막습니다(`delete_animation_blueprint`, `create/duplicate_animation_blueprint` 의 `overwrite`). 조회·편집·저장은 막지 않습니다.

## 통신 규약

`POST http://127.0.0.1:<Port>/v1/<tool>` · 본문 JSON · 응답은 항상 봉투 하나:

```json
{ "ok": true,  "tool": "get_editor_status", "request_id": "…", "result": { … }, "error": null, "diagnostics": [] }
{ "ok": false, "tool": "…", "request_id": "…", "result": null, "error": { "code": "ASSET_NOT_FOUND", "message": "…", "details": { … } }, "diagnostics": [] }
```

- `request_id` 를 보내면 같은 `(tool, request_id)` 재전송은 캐시된 봉투를 돌려주고 핸들러를 다시 실행하지 않습니다(256개 보관).
- `diagnostics[]` 는 성공 응답에도 붙는 경고(`{level, code, message}`).
- 긴 작업은 동기입니다(에디터 프레임을 잡습니다). 클라이언트 타임아웃은 기본 60초, 컴파일을 포함하면 180초를 권장합니다.

## Tool (27개)

Python 함수명 = 라우트명. 입력은 JSON 본문의 필드입니다.

| Tool | 입력 | 하는 일 |
| :--- | :--- | :--- |
| `get_editor_status` | — | 토큰 면제. 엔진·프로젝트·PIE·포트·Tool 목록·`process_id`·보호 목록·`dirty_package_count` |
| `get_anim_blueprint_info` | `asset_path` | `revision`, `parent_class`, `target_skeleton`, `graphs[]`, `variables[]`(규칙 `var`·`bind_pin` 대상; BP 변수는 `declaration`), `linked_anim_layers[]`, `implemented_interfaces[]`, `layers[]`, `update_function`, `skeleton_blend_profiles[]`, `skeleton_slot_groups[{group, slots[]}]` |
| `get_anim_graph_structure` | `asset_path, graph_guid?, depth=1` | 그래프 트리·노드·핀·연결·허용 목록 프로퍼티·바인딩·`state_machines[]` 뷰. `depth 0` = 그 그래프만, `-1` = 전부 |
| `list_animation_assets` | `skeleton?, asset_class=all, path_prefix=/Game, limit=200, details=false` | AnimSequence·BlendSpace·AnimMontage·AnimComposite 목록. `details` 면 로드해서 BlendSpace → `blendspace{}`(축·샘플·`aim_offset`), AnimMontage → `montage{}`(슬롯·섹션·`skeleton_slot_groups`), AnimSequence → `additive_type`·`additive_valid`·`ref_pose_type`·`ref_pose_sequence`·`length` |
| `create_animation_blueprint` | `asset_path, skeleton, parent_class, preview_mesh?, overwrite=false` | 루트 AnimGraph 만 있는 ABP 생성. `overwrite` 는 기존 애셋 삭제 |
| `duplicate_animation_blueprint` | `source_path, dest_path, overwrite=false, preserve_node_guids=true, save=false` | 노드 Guid 를 보존한 복제 |
| `delete_animation_blueprint` | `asset_path, confirm(true 필수), force=false` | AnimBP 만. 다른 애셋이 참조하면 `force` 없이는 `ASSET_REFERENCED` |
| `create_blendspace` | `asset_path, skeleton, dimensions 1\|2, axes[{name,min,max,grid=4,snap,wrap}], samples?[{animation, value}], aim_offset=false, preview_mesh?, overwrite, save` | BlendSpace1D / BlendSpace 생성, `aim_offset` 면 AimOffsetBlendSpace1D / AimOffsetBlendSpace(샘플은 Mesh Space additive 만 — `ADDITIVE_TYPE`). 샘플은 생성 전 전부 검증(범위·중복·스켈레톤·additive 일치·기준 포즈 유무 `ADDITIVE_INVALID`) |
| `create_anim_montage` | `asset_path, animation, slot?=DefaultSlot, blend_in?, blend_out?, preview_mesh?, overwrite, save` | AnimSequence 하나로 몽타주 생성(트랙 1·세그먼트 1·섹션 `Default`@0). 스켈레톤·길이는 시퀀스를 따름. 슬롯은 스켈레톤에 등록돼 있어야 함(`SLOT_NOT_IN_SKELETON`). 노티파이는 범위 밖 |
| `set_montage_slots` | `asset_path, slots[{index?, slot} \| "name"], save` | 슬롯 트랙 이름 변경(전부 검증 뒤 적용). 스켈레톤에 없는 이름 거부(`SLOT_NOT_IN_SKELETON`, details 에 `slot_groups`), 트랙 이름 중복 거부(`DUPLICATE_SLOT`). 노티파이·섹션은 트랙 인덱스로 링크돼 유지. 같은 이름 = `unchanged` |
| `set_montage_sections` | `asset_path, sections[{name, start, next?}], save` | 섹션 목록 **전체 교체**(시작 시간 순 정렬). `next` 생략/null = 섹션 끝에서 정지, 자기 이름 = 루프. 이름 중복·길이 밖·없는 next·빈 목록 거부. 같은 목록 재적용 = `unchanged`. 첫 섹션이 0 이 아니면 경고 `NO_SECTION_AT_ZERO` |
| `add_skeleton_slot` | `skeleton, slot, group?=DefaultGroup, confirm(true 필수), save` | 스켈레톤에 슬롯 등록(그룹 없으면 생성, 다른 그룹에 있으면 이동). 슬롯·그룹은 같은 이름 공간(`SLOT_IS_GROUP`·`GROUP_IS_SLOT`). 응답 `added, moved_from, group_created, unchanged, slot_groups[]`. `save` 없으면 에디터 종료 시 사라짐 |
| `create_anim_layer_interface` | `asset_path, layers[{name, group?, input_poses?["Name" \| {name, inputs?[{name, type}]}]}], overwrite, save` | Anim Layer Interface 애셋 + 레이어 그래프(+ 값 파라미터 `inputs`). 항상 컴파일 |
| `implement_anim_layer_interface` | `asset_path, interface, compile=true, save` | ABP 가 인터페이스 구현 → 레이어 그래프(Root + 입력 포즈 + 값 핀) 자동 생성 |
| `set_layer_inputs` | `asset_path, layer, input_pose?, inputs[{name, type}], compile=true, save, conform_implementers=true` | 레이어의 Input Pose 노드 값 파라미터 **전체 교체**(인터페이스 레이어·ABP 자체 레이어만; 구현 그래프는 `NOT_EDITABLE`). 입력 포즈 없는 레이어는 `NO_INPUT_POSE`. 같은 목록 = `unchanged`. 인터페이스면 참조 ABP 를 conform·컴파일 → `implementers[]` |
| `add_anim_layers` | `asset_path, layers[…], compile=true, save, conform_implementers=true` | 인터페이스 레이어 또는 ABP 자체 레이어 그래프 추가(이름 충돌 전부 선검증) |
| `remove_anim_layers` | `asset_path, layers[names], force=false, compile=true, save, conform_implementers=true` | 레이어 그래프 삭제. 인터페이스면 참조 ABP 의 채워진 구현 그래프·LinkedAnimLayer 노드 사용을 `usage[]` 로 보고하고 `force` 없이는 `LAYER_IN_USE_BY` |
| `preview_graph_operations` | `asset_path, operations[]` | 그래프 불변. `valid`, `planned[{index, op, ok, error?, note?}]` |
| `apply_graph_operations` | `asset_path, operations[], expected_revision?, compile=false, save=false` | 전체 사전 검증 → 트랜잭션 → 실패 시 롤백(`rollback_verified`). 응답 `refs`, `revision_before/after`, `operations[]`, `compile`, `saved` |
| `compile_animation_blueprint` | `asset_path, save_on_success=false` | `num_errors`, `num_warnings`, `messages[{level, text, node_guid, graph_guid}]` |
| `save_animation_blueprint` | `asset_path` | 강제 저장 |
| `run_automation_tests` | `filter(필수), timeout=120, dry_run=false` | 에디터 안에서 Automation 테스트 실행(`FAutomationTestFramework` 직접 구동). 지연 명령이 없으면 동기 완료(`done=true`), 아니면 `job_id` 로 poll |
| `poll_automation_tests` | `job_id` | 진행·결과 `{total, completed, passed, failed, done, ok, running?, tests[{name, state, duration, errors[], warnings[]}]}` |
| `add_blueprint_variable` | `asset_path, name, type, default?, category?, instance_editable, compile, save` | BP 멤버 변수 추가. `type` = bool·float·int·int64·name·string·text·byte·vector·vector2d·rotator·transform·linearcolor·`object:<클래스>`·`class:<클래스>`·`struct:<구조체>`·`enum:<열거형>`. 추가 즉시 규칙 `var`·VariableGet·`bind_pin`·`set_update_function` 이 쓴다 |
| `remove_blueprint_variable` | `asset_path, name, force, compile, save` | 이 BP 가 선언한 변수만. 참조 중이면 `VARIABLE_IN_USE`, `force` 면 참조 노드도 삭제 |
| `set_update_function` | `asset_path, assignments[{variable, value}] \| remove, compile=true, save` | `BlueprintThreadSafeUpdateAnimation` 오버라이드를 스펙에서 **전체 재생성**(Entry → VariableSet 사슬, 값은 규칙 AST). 멱등(`applied.unchanged`), 사람 편집 감지(`update_function.modified`). 변수는 BlueprintVisible ∧ 읽기 전용 아님 |
| `quit_editor` | `save_dirty=false, discard_dirty=false` | 더티 패키지가 있으면 둘 중 하나 없이는 `DIRTY_PACKAGES` 로 거부. `save_dirty` 는 콘텐츠만 저장(맵 제외). 응답 `process_id` |

새 Tool 은 Claude Code **세션을 다시 시작해야** MCP 목록에 보입니다(HTTP 로는 바로 호출 가능).

## op 사전 (20종) — `preview_graph_operations` / `apply_graph_operations` 의 `operations[]`

노드 참조: `{"node": "<guid>"}` · `{"ref": "<같은 배치 앞 add_* 의 ref>"}` · `"<guid>"` · `{"result_of": {node|ref}}`(상태의 StateResult 노드). 핀은 이름. `add_node.graph`: 생략 = 루트 AnimGraph · `"<graph_guid>"` · `{node|ref}`(상태 → 그 포즈 그래프).

| op | 입력 | 비고 |
| :--- | :--- | :--- |
| `add_node` | `ref?, graph?, class, pos?, asset?, enum?, properties?{}` | `UAnimGraphNode_Base` 파생 클래스 이름(`AnimGraphNode_SequencePlayer` 등). `enum` 은 BlendListByEnum |
| `add_node` (변수) | `class:"K2Node_VariableGet", variable` | AnimInstance 의 BlueprintVisible 변수. AnimGraph·상태 포즈 그래프만 |
| `add_node` (레이어) | `class:"AnimGraphNode_LinkedAnimLayer", layer` | 구현한 인터페이스 레이어 또는 자체 레이어. 한 레이어는 ABP 당 노드 하나(`LAYER_IN_USE`) |
| `connect` | `from:{node\|ref\|result_of, pin}, to:{…}` | 스키마 검증 후 연결. 포즈 출력 핀은 단일 연결 |
| `disconnect` | `from, to?` | `to` 없으면 `from` 의 링크 전부 |
| `remove_node` | `node\|ref` | Root·Result·Entry 거부. 상태·conduit·alias 를 지우면 연결 전이 연쇄 삭제 |
| `set_property` | `node\|ref, property, value` | **허용 목록**(아래) 프로퍼티만. 구조체는 USTRUCT 멤버 이름 JSON, enum 은 이름 |
| `set_asset` | `node\|ref, asset` | 애셋 플레이어의 애셋 교체 |
| `expose_pin` | `node\|ref, property, visible=true` | 프로퍼티를 핀으로 노출/숨김 |
| `bind_pin` | `node\|ref, property, path:[...]\|"A.B"` | 노출 핀을 AnimInstance 프로퍼티/BlueprintPure 함수 경로에 바인딩. 핀에 링크가 있으면 `PIN_LINKED` |
| `unbind_pin` | `node\|ref, property` | 바인딩 제거 |
| `add_blend_pose` | `node\|ref, entry?` | LayeredBoneBlend / BlendListByEnum(`entry` 필수) 포즈 추가 |
| `add_state` | `ref?, sm:{node\|ref}\|graph, name?, pos?` | 포즈 그래프(BoundGraph + StateResult) 자동. 응답 `bound_graph_guid` |
| `add_transition` | `ref?, from, to, properties?, rule?` | 끝점은 상태·conduit·alias. 대상 alias 는 단일 상태·global 아님 |
| `set_entry_state` | `sm\|graph, state` | Entry → 상태 |
| `set_transition_rule` | `node\|ref, rule` | 규칙 AST(아래) → 규칙 그래프 재생성. 멱등, 사람 편집 감지(`rule_modified`) |
| `add_conduit` | `ref?, sm\|graph, name?, pos?, rule?` | 규칙 그래프 자동 |
| `add_state_alias` | `ref?, sm\|graph, name?, pos?, states[]\|global:true` | 대상은 같은 상태머신의 실제 상태만 |
| `set_alias_states` | `node\|ref, states\|global` | |
| `rename_node` | `node\|ref, name` | 상태·conduit·alias·상태머신. 엔진 이름 검증기 통과 필요 |
| `set_linked_layer` | `node\|ref, layer` | 레이어 재지정. 입력 포즈 핀에 링크가 있으면 `PINS_LINKED`(먼저 `disconnect`) |
| `set_layer_instance_class` | `node\|ref, instance_class: 경로 \| null` | 인터페이스 레이어 노드를 다른 구현 ABP 인스턴스로(Lyra 무기별 공급자). AnimBP 애셋 경로 또는 `_C` 클래스. `SELF_LAYER`·`NOT_IMPLEMENTING`·`SELF_CLASS`·`INCOMPATIBLE`·`PINS_LINKED`(링크된 값 핀). null = 자기 구현으로 복귀 |

`expose_pin` 은 LinkedAnimLayer/LinkedAnimGraph 노드의 **값 파라미터 핀**(조회 `optional_pins[].custom=true`)도 켜고 끕니다. 켠 핀에 `connect` 로 값을 넣습니다(`bind_pin` 은 범위 밖).

**`set_property` 허용 목록** (노드의 `properties` 조회가 곧 목록입니다): SequencePlayer `bLoopAnimation, PlayRate, StartPosition, PlayRateBasis, GroupName, GroupRole, Method, bStartFromMatchingPose` · BlendSpacePlayer·AimOffset(RotationOffsetBlendSpace) `bLoop, PlayRate, StartPosition, X, Y, bResetPlayTimeWhenBlendSpaceChanges, GroupName, GroupRole, Method` + AimOffset `Alpha, LODThreshold, AlphaInputType, bAlphaBoolEnabled, AlphaCurveName, AlphaScaleBias, AlphaScaleBiasClamp, AlphaBoolBlend` · SequenceEvaluator `ExplicitTime, bUseExplicitFrame, ExplicitFrame, bShouldLoop, bTeleportToExplicitTime, ReinitializationBehavior, StartPosition, GroupName, GroupRole, Method` · ApplyAdditive · TwoBoneIK · ModifyBone(공통 `Alpha, LODThreshold, AlphaInputType, bAlphaBoolEnabled, AlphaCurveName, AlphaScaleBias, AlphaScaleBiasClamp, AlphaBoolBlend`) · TwoBoneIK `IKBone, EffectorLocation, EffectorLocationSpace, EffectorTarget, JointTargetLocation, JointTargetLocationSpace, JointTarget, bAllowStretching, StartStretchRatio, MaxStretchScale, bTakeRotationFromEffectorSpace, bMaintainEffectorRelRot, bAllowTwist, TwistAxis` · ModifyBone `BoneToModify, Translation, Rotation, Scale, TranslationMode, RotationMode, ScaleMode, TranslationSpace, RotationSpace, ScaleSpace` · Mirror `bMirror, MirrorDataTable, BlendTime, bResetChild, bBoneMirroring, bCurveMirroring, bAttributeMirroring` · Inertialization `DefaultBlendProfile, FilteredCurves, FilteredBones, bResetOnBecomingRelevant, bForwardRequestsThroughSkippedCachedPoseNodes` · Slot `SlotName, bAlwaysUpdateSourcePose` · SaveCachedPose `CacheName` · UseCachedPose `SaveCachedPoseNode`(노드 참조) · LayeredBoneBlend `bMeshSpaceRotationBlend, bMeshSpaceScaleBlend, bBlendRootMotionBasedOnRootBone, LODThreshold, BlendMode, LayerSetup, BlendMasks, CurveBlendOption, bRootSpaceRotationBlend` · BlendList `BlendTime[], TransitionType, BlendType, ChildUpateMode, CustomBlendCurve, BlendProfile` · BlendListByEnum `BoundEnum` · 전이 `CrossfadeDuration, PriorityOrder, BlendMode, Bidirectional, bDisabled, bAutomaticRuleBasedOnSequencePlayerInState, AutomaticRuleTriggerTime` · 상태 `bAlwaysResetOnEntry`. 목록 밖 프로퍼티는 `PROPERTY_NOT_ALLOWED`.

값 표현: 본 `{"BoneName": "hand_r"}`(TargetSkeleton 에 있어야 함, `BONE_NOT_FOUND`) · 벡터 `{"X","Y","Z"}` · 로테이터 `{"Pitch","Yaw","Roll"}` · 중첩 구조체 `{"bUseSocket": false, "BoneReference": {"BoneName": "hand_l"}}` · enum 이름 `"BCS_ComponentSpace"` · 오브젝트 참조는 애셋 경로 문자열(`null` 로 비움; BlendProfile·MirrorDataTable 은 같은 스켈레톤이어야 함, `SKELETON_MISMATCH`; 스켈레톤의 프로파일은 `get_anim_blueprint_info.skeleton_blend_profiles[]`) · `BlendMasks` 는 `BlendMode` 가 `BlendMask` 일 때 포즈마다 마스크 프로파일 경로 또는 `null`.

**규칙 AST** (`set_transition_rule` · `add_transition.rule` · `add_conduit.rule`):

```jsonc
{"var": "bIsFalling"}                                                        // AnimInstance 의 BlueprintVisible 프로퍼티
{"not": R} · {"and": [R, …]} · {"or": [R, …]}
{"compare": {"op": ">=", "left": {"var": "Speed"}, "right": {"literal": 20.0}}} // 연산 × 타입 → KismetMathLibrary. 한쪽은 non-literal
{"call": {"function": "FMax", "class"?: "/Script/…", "args": {"A": R, "B": R}}} // BlueprintPure ∧ ThreadSafe ∧ 소유 ∈ {AnimInstance 사슬, UKismetMathLibrary}
{"literal": true}                                                            // 최상위면 Result 핀 기본값(노드 없음)
{"automatic": true, "trigger_time"?: -1.0}                                   // 전이만: 시퀀스 길이 기반 자동 규칙
{"access": "GetOwningComponent.ComponentVelocity"}                           // Property Access 노드 — AnimInstance 에서 시작하는 프로퍼티/pure 함수 경로(엔진이 해석·스레드 안전 판정)
{"param": "DeltaTime"}                                                       // set_update_function 안에서만: 함수 입력 파라미터
```

벡터·구조체처럼 비교할 수 없는 값도 `access`/`call` 로 흘러 `call` 인자나 `set_update_function` 의 대입 값이 됩니다(예: `{"call": {"function": "VSize", "args": {"A": {"access": "GetOwningComponent.ComponentVelocity"}}}}`). 정규화한 원문과 그래프 해시를 규칙 그래프의 주석 노드에 기록합니다. 조회 응답의 `rule_source` 가 그것이고, 해시가 다르면 사람이 손으로 바꾼 것(`rule_modified`)입니다.

**업데이트 함수** (`set_update_function`): `{"assignments": [{"variable": "Speed", "value": {"call": {"function": "VSize", "args": {"A": {"access": "GetOwningComponent.ComponentVelocity"}}}}}, {"variable": "bIsMoving", "value": {"compare": {"op": ">", "left": {"var": "Speed"}, "right": {"literal": 1.0}}}}]}` — 실행 순서대로 변수에 대입하는 `BlueprintThreadSafeUpdateAnimation` 함수 그래프가 만들어집니다. 스레드 안전하지 않은 호출은 컴파일 경고로 드러나고 멀티스레드 업데이트가 꺼집니다.

## 안전 장치

- **Preview / Apply 분리** — 같은 입력으로 `preview` 는 검증만 합니다.
- **배치 원자성** — 적용 전 전체 사전 검증(하나라도 실패면 무변경) → `FScopedTransaction` 안에서 순차 적용 → 실패 시 op 별 되돌리기 저널을 역순 실행 → `revision_after == revision_before` 로 복구를 검증(`rollback_verified`). 에디터 Undo 에 의존하지 않습니다.
- **충돌 감지** — `expected_revision` 이 다르면 `REVISION_MISMATCH`, 무변경. `revision` 은 그래프·노드·핀·연결·프로퍼티·바인딩의 결정적 SHA1 입니다.
- **저장은 명시적** — `save` 기본 false, 컴파일 오류가 있으면 저장하지 않습니다.
- **파괴 연산 보호** — 보호 목록, `confirm`, 참조 검사(`force`), 더티 검사(`save_dirty`/`discard_dirty`).

## 오류 코드

| HTTP | 코드 |
| :---: | :--- |
| 400 | `BAD_REQUEST`(`details.reason`/`field`) · `CONNECTION_REJECTED` · `PROPERTY_NOT_ALLOWED` · `COMPILE_FAILED` · `SAVE_FAILED` |
| 401 | `UNAUTHORIZED` |
| 403 | `ASSET_PROTECTED` |
| 404 | `TOOL_NOT_FOUND` · `ASSET_NOT_FOUND` · `GRAPH_NOT_FOUND` · `NODE_NOT_FOUND` · `PIN_NOT_FOUND` |
| 409 | `ASSET_EXISTS` · `REVISION_MISMATCH` · `ASSET_REFERENCED` · `DIRTY_PACKAGES` |
| 500 | `INTERNAL` |

배치 실패의 원인은 사전 검증이면 `details.planned[i].error`, 적용 중이면 `details.cause` 와 `details.applied[i].error` 에 있습니다. Python 클라이언트는 전송 오류를 `EDITOR_GONE` · `TIMEOUT` · `TRANSPORT` · `BAD_RESPONSE` 로 같은 봉투 모양에 넣습니다.

## 검증 — 스모크 테스트

`run_automation_tests {"filter": "AnimGraphMcp.Smoke"}` 는 `SmokeTestPaths` 아래 **모든 AnimBP 를 애셋마다 테스트 하나**로 엽니다(`AnimGraphMcp.Smoke.AnimBlueprint.<이름>`): 컴파일 0 에러 · 루트 Output Pose 연결 · 빈 상태(StateResult 미연결) · 끊긴 UseCachedPose · 무효 Linked Anim Layer. 레이어 제공자 ABP(인터페이스 구현만 하고 루트를 쓰지 않는 Lyra 식)의 빈 루트와 빈 레이어 구현은 **경고**입니다.

같은 경로의 **모든 AnimMontage** 도 애셋마다 하나(`AnimGraphMcp.Smoke.AnimMontage.<이름>`): 슬롯이 스켈레톤에 등록됨(오류) · 섹션 존재·시작 시간 범위·Next 존재(오류) · 첫 섹션 0 시작(경고) · 호환 스켈레톤의 AnimBP 에 그 이름의 Slot 노드가 있음(경고 — 없으면 어느 그래프에서도 재생되지 않을 수 있음). 프로젝트 자체 Automation 테스트도 같은 Tool 로 돌릴 수 있습니다.

## 제약 (설계상 범위 밖)

- **임의의 EventGraph 편집은 다루지 않습니다.** BP 변수 추가와 `BlueprintThreadSafeUpdateAnimation` 의 "변수 ← 식" 대입 사슬까지가 범위이고, 분기·루프·이벤트·임의 K2 노드는 만들지 않습니다. 복잡한 상태 판정은 C++ AnimInstance 에 두는 것을 권합니다.
- 전이 규칙의 `call` 은 화이트리스트 함수만, `set_property` 는 허용 목록 프로퍼티만입니다. 허용 목록 밖 노드(Control Rig·PoseDriver·RigidBody·AnimDynamics·Motion Matching 등)는 생성·연결은 되지만 세부 설정은 못 합니다. 필요하면 `Core/AnimMcpPropertyRules.cpp` 의 표에 한 줄씩 더합니다.
- Linked Anim Layer 의 값 파라미터는 **Input Pose 노드에 붙습니다**(엔진 구조) — 입력 포즈 없는 레이어는 값 파라미터를 가질 수 없습니다. 자식 Animation Blueprint 가 부모의 레이어를 오버라이드하는 그래프 생성은 범위 밖입니다. 인터페이스 변경 뒤 구현 ABP 동기화는 AssetRegistry 참조자(디스크에 저장된 ABP) 기준입니다.
- 생성하는 콘텐츠 애셋은 BlendSpace·AimOffset·몽타주(시퀀스 1개, 슬롯·섹션)입니다. **노티파이**(프로젝트별 클래스)·몽타주 다중 세그먼트·블렌드 프로파일·싱크 마커는 범위 밖입니다. 스켈레톤 편집은 슬롯 등록(`add_skeleton_slot`, `confirm` 필수)뿐입니다.
- 검증은 구조 검사까지입니다. 실제 포즈는 PIE 에서 사람이 봅니다.
- 한 포트에 에디터 하나. PIE 중이거나 모달 작업(`GIsSlowTask`) 중에는 Automation 테스트가 시작되지 않습니다.
- `/Game/...` 인자를 Git Bash 에서 넘길 때는 `MSYS_NO_PATHCONV=1`.

## 소스 구조

```text
Source/AnimGraphMcpEditor/Private/
  AnimGraphMcpEditorModule.cpp     설정 로드 · Dispatcher/Bridge 조립 · Tool 등록 · 콘솔 명령
  Bridge/   AnimMcpHttpBridge       엔진 HTTPServer 라우트(tool 당 1개) · 토큰 전처리 · 응답
            AnimMcpDispatcher       JSON 파싱 → request_id 캐시 → 핸들러 → 봉투
            AnimMcpTypes            오류 코드 · 파라미터 헬퍼 · 진단
  Core/     AnimMcpAssetResolver    경로 정규화 · 존재 확인 · 로드
            AnimMcpGraphInspector   (읽기 전용) 구조 조회 · revision
            AnimMcpGraphMutator     (쓰기 기계) 노드·핀·속성·상태머신 조작
            AnimMcpOperations       배치 정책: 참조 해석 · 사전 검증 · 트랜잭션 · 되돌리기 저널
            AnimMcpTransitionRule   규칙 AST → K2 그래프 · 주석 원문/해시
            AnimMcpPropertyRules    set_property 허용 목록 · JSON ↔ ImportText
            AnimMcpPropertyBinding  핀 Property Binding(리플렉션 · IPropertyAccessEditor)
            AnimMcpAnimLayer        레이어 인터페이스 생성 · 구현 · 레이어 노드 · 값 파라미터 · InstanceClass · 레이어 추가/삭제 · 구현 ABP 동기화
            AnimMcpBlendSpaceFactory  BlendSpace 1D/2D 생성
            AnimMcpBlueprintFactory ABP 생성   AnimMcpCompiler  컴파일·저장
            AnimMcpAssetProtection  보호 목록   AnimMcpAssetOps  삭제·복제·참조자
            AnimMcpAutomationRunner FAutomationTestFramework 구동 · 잡
            AnimMcpPropertyAccessNode  UK2Node_PropertyAccess 리플렉션(엔진 플러그인의 비공개 노드)
            AnimMcpVariables        BP 멤버 변수 추가·삭제 · 타입 문자열
            AnimMcpUpdateFunction   BlueprintThreadSafeUpdateAnimation 함수 그래프 생성·재생성
            AnimMcpMontage          몽타주 생성(시퀀스 1개) · 슬롯 이름 · 섹션 전체 교체 · 스켈레톤 슬롯 등록 · 조회
  Tests/    AnimMcpSmokeTests.cpp    AnimGraphMcp.Smoke.AnimBlueprint · AnimGraphMcp.Smoke.AnimMontage
  Tools/    AnimMcpTools_*.cpp       Tool 핸들러(얇음; Montage = 몽타주·스켈레톤 슬롯 4종)
```

규칙: Inspector 는 쓰지 않고, Mutator 는 트랜잭션 밖에서 호출되지 않습니다. 같은 `FJsonObject` 를 두 컨테이너에 넣지 않습니다(순환 → 직렬화 무한 재귀).
