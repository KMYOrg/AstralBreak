# AnimGraph MCP Bridge (`Plugins/AnimGraphMcp`)

실행 중인 Unreal Editor 안에서 Animation Blueprint 를 **생성·조회·편집·컴파일·검증**하고, 애니메이션을 다른 스켈레톤으로 **임포트·IK 리타깃·측정**하게 해 주는 에디터 전용 C++ 플러그인입니다. 바깥의 MCP 서버(`Tools/mcp/anim_graph_mcp/server.py`)가 HTTP/JSON 으로 이 플러그인을 부르고, Claude Code 같은 AI 에이전트는 MCP Tool 로 그 서버를 부릅니다.

```text
AI Agent ─ stdio MCP ─▶ Tools/mcp/anim_graph_mcp/server.py ─ HTTP/JSON 127.0.0.1:18765 ─▶ Plugins/AnimGraphMcp (에디터, 게임 스레드) ─▶ UAnimBlueprint
```

- 엔진: **UE 5.7.4**(소스 빌드에서 검증). 모듈 1개 `AnimGraphMcpEditor`(Type Editor). 프로젝트 코드에 의존하지 않습니다. 의존 플러그인 `IKRig` · `Interchange`(`.uplugin` 에 선언, 엔진 기본 활성).
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
+GenerationOutputPaths=/Game/Animation/Generated/   ; AI 애니 생성 Tool 의 쓰기 허용 목록 (패키지 경로 접두)
+ImportSourceRoots=Saved/AnimGen/Import/            ; import_animation_file 이 읽는 디스크 폴더 (프로젝트 기준 상대 또는 절대)
MaxRetargetAssetsPerCall=50                         ; retarget_animations 요청당 애셋 수 상한(입력 + 동반 참조). 실측 20개 리타깃·검증·저장 3초
+AnimationTagFiles=Config/AnimGraphMcp/AnimationTags.json  ; search_animations 수동 태그 JSON (프로젝트 기준 상대 또는 절대)
```

(UE ini 는 줄 끝 `;` 주석을 값으로 읽습니다 — 위 주석은 설명용이고 실제 ini 에서는 주석을 따로 줄에 둡니다.)

보호 목록은 **파괴 연산만** 막습니다(`delete_animation_blueprint`, `create/duplicate_animation_blueprint` 의 `overwrite`). 조회·편집·저장은 막지 않습니다.

생성 경로 설정은 출력·임포트 경로의 **유일한 기준**입니다. 목록이 비어 있으면 생성 Tool 은 아무 데도 쓰지 않고 임포트도 받지 않습니다. 생성 Tool 은 호출 전후 에디터 전체의 더티 패키지 집합을 비교해, 허용 목록 밖 패키지가 새로 더티가 되면 아무것도 저장하지 않고 `UNEXPECTED_DIRTY` 로 실패합니다. `get_editor_status.generation` 이 정규화된 값(`output_paths[]` · 절대 경로 `import_source_roots[]` · `max_retarget_assets_per_call` · `animation_tag_files[]`)을 돌려줍니다.

## 통신 규약

`POST http://127.0.0.1:<Port>/v1/<tool>` · 본문 JSON · 응답은 항상 봉투 하나:

```json
{ "ok": true,  "tool": "get_editor_status", "request_id": "…", "result": { … }, "error": null, "diagnostics": [] }
{ "ok": false, "tool": "…", "request_id": "…", "result": null, "error": { "code": "ASSET_NOT_FOUND", "message": "…", "details": { … } }, "diagnostics": [] }
```

- `request_id` 를 보내면 같은 `(tool, request_id)` 재전송은 캐시된 봉투를 돌려주고 핸들러를 다시 실행하지 않습니다(256개 보관).
- `diagnostics[]` 는 성공 응답에도 붙는 경고(`{level, code, message}`).
- 긴 작업은 동기입니다(에디터 프레임을 잡습니다). 클라이언트 타임아웃은 기본 60초, 컴파일을 포함하면 180초를 권장합니다.

## Tool (39개)

Python 함수명 = 라우트명. 입력은 JSON 본문의 필드입니다.

| Tool | 입력 | 하는 일 |
| :--- | :--- | :--- |
| `get_editor_status` | — | 토큰 면제. 엔진·프로젝트·PIE·포트·Tool 목록·`process_id`·보호 목록·`dirty_package_count` |
| `get_anim_blueprint_info` | `asset_path` | `revision`, `parent_class`, `target_skeleton`, `graphs[]`, `variables[]`(규칙 `var`·`bind_pin` 대상; BP 변수는 `declaration`), `linked_anim_layers[]`, `implemented_interfaces[]`, `layers[]`, `update_function`, `skeleton_blend_profiles[]`, `skeleton_slot_groups[{group, slots[]}]` |
| `get_anim_graph_structure` | `asset_path, graph_guid?, depth=1` | 그래프 트리·노드·핀·연결·허용 목록 프로퍼티·바인딩·`state_machines[]` 뷰. `depth 0` = 그 그래프만, `-1` = 전부 |
| | | `state_machines[].transitions[]` 는 `from/to · priority_order · crossfade_duration · blend_mode · logic_type`(`TLT_StandardBlend \| TLT_Inertialization \| TLT_Custom`, revision 해시 밖) `· bidirectional · disabled · automatic · rule_*` |
| `list_animation_assets` | `skeleton?, asset_class=all, path_prefix=/Game, limit=200, details=false` | AnimSequence·BlendSpace·AnimMontage·AnimComposite 목록. `details` 면 로드해서 BlendSpace → `blendspace{}`(축·샘플·`aim_offset`), AnimMontage → `montage{}`(슬롯·섹션·`skeleton_slot_groups`), AnimSequence → `additive_type`·`additive_valid`·`ref_pose_type`·`ref_pose_sequence`·`length` |
| `create_animation_blueprint` | `asset_path, skeleton, parent_class, preview_mesh?, overwrite=false` | 루트 AnimGraph 만 있는 ABP 생성. `overwrite` 는 기존 애셋 삭제 |
| `duplicate_animation_blueprint` | `source_path, dest_path, overwrite=false, preserve_node_guids=true, save=false` | 노드 Guid 를 보존한 복제 |
| `delete_animation_blueprint` | `asset_path, confirm(true 필수), force=false` | AnimBP 만. 다른 애셋이 참조하면(AssetRegistry + 메모리 참조자) `force` 없이는 `ASSET_REFERENCED` |
| `create_blendspace` | `asset_path, skeleton, dimensions 1\|2, axes[{name,min,max,grid=4,snap,wrap}], samples?[{animation, value}], aim_offset=false, preview_mesh?, overwrite, save` | BlendSpace1D / BlendSpace 생성, `aim_offset` 면 AimOffsetBlendSpace1D / AimOffsetBlendSpace(샘플은 Mesh Space additive 만 — `ADDITIVE_TYPE`). 샘플은 생성 전 전부 검증(범위·중복·스켈레톤·additive 일치·기준 포즈 유무 `ADDITIVE_INVALID`) |
| `create_anim_montage` | `asset_path, animation, slot?=DefaultSlot, blend_in?, blend_out?, preview_mesh?, overwrite, save` | AnimSequence 하나로 몽타주 생성(트랙 1·세그먼트 1·섹션 `Default`@0). 스켈레톤·길이는 시퀀스를 따름. 슬롯은 스켈레톤에 등록돼 있어야 함(`SLOT_NOT_IN_SKELETON`). 노티파이는 범위 밖 |
| `set_montage_slots` | `asset_path, slots[{index?, slot} \| "name"], save` | 슬롯 트랙 이름 변경(전부 검증 뒤 적용). 스켈레톤에 없는 이름 거부(`SLOT_NOT_IN_SKELETON`, details 에 `slot_groups`), 트랙 이름 중복 거부(`DUPLICATE_SLOT`). 노티파이·섹션은 트랙 인덱스로 링크돼 유지. 같은 이름 = `unchanged` |
| `set_montage_sections` | `asset_path, sections[{name, start, next?}], save` | 섹션 목록 **전체 교체**(시작 시간 순 정렬). `next` 생략/null = 섹션 끝에서 정지, 자기 이름 = 루프. 이름 중복·길이 밖·없는 next·빈 목록 거부. 같은 목록 재적용 = `unchanged`. 첫 섹션이 0 이 아니면 경고 `NO_SECTION_AT_ZERO` |
| `reassign_skeleton` | `skeleton(대상), assets?[경로] \| (from_skeleton + path_prefix?=/Game), confirm(true 필수; dry_run 제외), dry_run?, allow_missing_bones?, convert_spaces?, save?=true` | 애니 애셋(시퀀스·몽타주·BlendSpace·AimOffset·컴포짓)을 다른 스켈레톤으로 **제자리** 이동 — 같은 캐릭터를 두 번 임포트해 본 이름이 같은 스켈레톤이 둘이 된 경우(ABP 는 자기 스켈레톤의 애셋만 참조할 수 있다). 엔진의 "retarget to another skeleton" 경로(본 트랙 이름 재매핑·커브 이름 복사). **참조 애셋(몽타주 세그먼트·BlendSpace 샘플·additive 기준 포즈)은 엔진이 항상 같이 옮긴다** → `dry_run` 의 `referred[]` 를 먼저 본다. 시퀀스 본 트랙이 대상 스켈레톤에 없으면 `BONES_MISSING`(details.assets[].missing_bones) 거부. 이미 대상이면 `skipped(already_on_target)`. 커브 이름 복사로 대상 스켈레톤이 더티가 되면 저장하되, 호출 전부터 더티였으면(남의 미저장 편집) 저장하지 않고 `SKELETON_DIRTY_NOT_SAVED` 경고. 응답 `{total, referred[], planned[] \| changed_assets[], referred_changed[], failed[], skipped[], changed, saved, skeleton_saved}` |
| `set_sequence_additive` | `asset_path(AnimSequence), additive_type?(None\|LocalSpaceBase\|RotationOffsetMeshSpace), ref_pose_type?(None\|RefPose\|AnimScaled\|AnimFrame\|LocalAnimFrame), ref_pose_sequence?(경로 \| null), ref_frame_index?, save` | 디테일 패널의 Additive Settings — AimOffset 샘플(Mesh Space additive + 기준 포즈)을 만들기 전 단계. 생략 = 유지, 같은 값 = `unchanged`. 다른 스켈레톤 기준 포즈는 `SKELETON_MISMATCH`(엔진은 조용히 null 로 만든다). 응답에 `additive_valid` |
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
| `poll_automation_tests` | `job_id` | 진행·결과 `{total, completed, passed, failed, done, ok, running?, tests[{name, state, duration, errors[], warnings[], observed?}]}` |
| `run_anim_scenario` | `asset_path, mesh?, map?, set_variables?{name: value}, montage?, wait_frames=10, expect?{state_machines{머신: 상태}, slots_active[]}, timeout=120` | **PIE 런타임 검증** — Automation 테스트 `AnimGraphMcp.Runtime.AnimBlueprint` 를 시나리오 JSON 과 함께 잡으로 시작: PIE 시작 → SkeletalMeshActor 스폰 + ABP 할당 → 변수 세팅(리플렉션) → 몽타주 재생 → N 프레임 → 모든 상태머신의 현재 상태·슬롯 활성 관측 → 기대값 비교 → PIE 종료. 기대값(상태머신·상태 이름)·변수 이름은 컴파일된 클래스로 **PIE 전에 검증**(`STATE_MACHINE_NOT_FOUND`·`STATE_NOT_FOUND`·`VARIABLE_NOT_FOUND`·`NO_PREVIEW_MESH`·`SKELETON_MISMATCH`·`PIE_ACTIVE`). 항상 비동기 → `poll_automation_tests`; 테스트 결과에 `observed{state_machines{이름: {state, elapsed}}, slots{이름: bool}, montage_playing, montage_length, variables_applied, frames_waited}`. 타임아웃이면 러너가 PIE 를 닫는다 |
| `add_blueprint_variable` | `asset_path, name, type, default?, category?, instance_editable, compile, save` | BP 멤버 변수 추가. `type` = bool·float·int·int64·name·string·text·byte·vector·vector2d·rotator·transform·linearcolor·`object:<클래스>`·`class:<클래스>`·`struct:<구조체>`·`enum:<열거형>`. 추가 즉시 규칙 `var`·VariableGet·`bind_pin`·`set_update_function` 이 쓴다 |
| `remove_blueprint_variable` | `asset_path, name, force, compile, save` | 이 BP 가 선언한 변수만. 참조 중이면 `VARIABLE_IN_USE`, `force` 면 참조 노드도 삭제 |
| `set_update_function` | `asset_path, assignments[{variable, value}] \| remove, compile=true, save` | `BlueprintThreadSafeUpdateAnimation` 오버라이드를 스펙에서 **전체 재생성**(Entry → VariableSet 사슬, 값은 규칙 AST). 멱등(`applied.unchanged`), 사람 편집 감지(`update_function.modified`). 변수는 BlueprintVisible ∧ 읽기 전용 아님 |
| `quit_editor` | `save_dirty=false, discard_dirty=false` | 더티 패키지가 있으면 둘 중 하나 없이는 `DIRTY_PACKAGES` 로 거부. `save_dirty` 는 콘텐츠만 저장(맵 제외). 응답 `process_id` |

**AI 애니 생성 — 리타깃 기반 (6개, [Docs/AIAnimation](../../Docs/AIAnimation/DevelopmentGuide.md) Phase 1).** 쓰기 Tool 은 `GenerationOutputPaths` 밖에 만들거나 저장하지 않고, 덮어쓰지 않으며(`ASSET_EXISTS`), 호출 전후 전역 더티 집합을 비교해 허용 목록 밖이 새로 더티면 저장하지 않고 `UNEXPECTED_DIRTY` 로 실패합니다. `save` 기본 false. 기존 IK Rig·리타기터 재사용은 `existing_*` 를 줄 때만, 메시는 항상 명시합니다.

| Tool | 입력 | 하는 일 |
| :--- | :--- | :--- |
| `inspect_skeleton` | `skeleton? \| skeletal_mesh?, details=false, compare_to?` | 읽기 전용. `meshes[]`·`animation_count`(레지스트리) · `bones[{name, parent}]`(details: 기준 로컬/컴포넌트 `{t, r, s?}`) · `virtual_bones[]` · `sockets[]`(스켈레톤+메시) · `slot_groups[]` · `curve_count` · `ik_rigs[]`(프리뷰 메시 기준)·`retargeters[]`(그 리그의 참조자, `roles`) · `template_match{used, name, percent, pelvis, chains[]}`(IK Rig 자동 캐릭터라이저 — `used=false` 면 자동 IK Rig 불가) · `compare{common, missing_in_other[], ref_rot_diff_deg{p50,max,max_bone}, bone_length_ratio{p50,min,max}, verdict}`. **리그 판정은 이름이 아니라 기준 포즈**(UE4 마네킹은 68본 이름이 전부 UE5 계열에 있어도 10~40° 다르다) — `same_rig` = 회전 최대 < 1° ∧ 길이 비 0.99~1.01, 참고 정보. 본 이름 비교는 엔진처럼 FName(대소문자 무시) |
| `import_animation_file` | `file, dest_path, skeleton?, sample_rate=0, name?, save` | Interchange FBX 임포트(동기 — 게임 스레드에서 끝까지). `file` 은 `ImportSourceRoots` 아래 절대 경로만(`IMPORT_SOURCE_NOT_ALLOWED` · `RELATIVE_PATH` · `FILE_NOT_FOUND` · `UNSUPPORTED_FORMAT`), `dest_path` 는 허용 목록 안의 **빈 폴더**(`ASSET_EXISTS` reason `DEST_NOT_EMPTY`). `skeleton` 이면 그 스켈레톤에 애니만, 없으면 메시·새 스켈레톤·애니. 커브 메타데이터의 스켈레톤 추가·재질·텍스처·피직스·스태틱 메시는 항상 끔, 덮어쓰기·대화상자 없음. 프로젝트 기본 파이프라인 스택을 트랜지언트로 복제해 씀(파이프라인 애셋 무변경) |
| `create_ik_rig` | `skeletal_mesh, asset_path \| existing_rig, mode=auto\|manual, pelvis?, chains?[{name, start, end, goal?}], fbik=true, save` | 에디터 자동 리타깃과 같은 경로(SetSkeletalMesh → 자동 리타깃 정의 → 자동 FBIK). 템플릿과 맞지 않는 메시는 애셋을 만들기 **전에** `IKRIG_AUTO_FAILED` + `details.bones[{name, parent}]` → `mode: manual` 로 다시. 수동 체인은 전부 사전 검증(`BAD_CHAINS`: `BONE_NOT_FOUND`·`END_NOT_BELOW_START`·`DUPLICATE_NAME/GOAL`, 펠비스 필수). `existing_rig` 는 호환(`INCOMPATIBLE_MESH`)만 보고 쓰지 않음 |
| `create_ik_retargeter` | `source_rig, target_rig, source_mesh, target_mesh, asset_path \| existing_retargeter, ops=default\|match_existing, auto_align=false, save` | `default` = 엔진 기본 op + 모든 op 정확한 이름 매핑. `match_existing` = 에디터 "Retarget Animations" 자동 생성 레시피(FK 매핑 Exact · 타깃 포즈 자동 정렬 · Run IK Rig 끔 · 루트 모션 op · Pin Bones) — 이 레시피로 만든 기존 RTG 와 필드·결과가 같음(Phase 1 회귀 비교: 본별 차 0°). 응답 `ops[]`·`chain_mapping{}`·`unmapped_target_chains[]`(경고)·`pin_bones[]`·`root_motion{}`·`retarget_poses{}`. `existing_retargeter` 는 리그 일치(`RIG_MISMATCH`)만 보고 쓰지 않음 |
| `retarget_animations` | `retargeter, assets[], source_mesh, target_mesh, output_path, name_rule?{prefix, suffix, replace_from, replace_to}, include_referenced=true, dry_run, validate=true, thresholds?, save` | 엔진 일괄 "Duplicate and Retarget" 을 출력 폴더 지정으로(`FIKRetargetBatchOperationContext` + `RunRetarget`, 덮어쓰기 항상 끔). 입력은 시퀀스·몽타주·BlendSpace(소스 메시 스켈레톤), AnimBlueprint 는 `ANIM_BLUEPRINT_NOT_ALLOWED`. 출력 이름을 엔진 규칙으로 **먼저** 계산해 기존 애셋 `ASSET_EXISTS` · 배치 내 충돌 `NAME_COLLISION_IN_BATCH` · 상한(`MaxRetargetAssetsPerCall`) `LIMIT` 을 실행 전에 거부. `validate` 면 생성 시퀀스마다 `validate_animation`(소스 대비), FAILED 면 저장 없이 `VALIDATION_FAILED`. 엔진 진행 창이 뜬다(사람이 취소하면 삭제 확인 모달) |
| `validate_animation` | `assets[], sources?[], skeleton?, checks?, thresholds?, feet?, pelvis?, source_feet?, source_pelvis?, expect?, seams?[], profile_bones?[]` | 읽기 전용 측정(C++, 프레임별 컴포넌트 공간 포즈). 구조(스켈레톤·트랙 본·NaN·스케일) · 절대(한 프레임 회전 > 90° — 소스에도 있는 튐은 경고 `ROTATION_JUMP_INHERITED`) · 상대(다른 스켈레톤 소스: 각속도 p99 비·착지 발 속도 비·루트 이동 비(펠비스 높이로 보정)·길이·루프 경계 / 같은 스켈레톤 소스: 본별 회전·위치 차 — 회귀 비교) · **요청 충족**(Phase 2: `expect{length, length_tolerance, loop, root_yaw_delta, root_yaw_tolerance}` 불일치 → `EXPECT_*` 오류, `seams[]`(초) 에서 포즈 변화가 앞뒤 창 중앙값의 `seam_ratio_max`(3.0)배 초과 → 경고 `SEAM_JUMP`) · `profile_bones` → `numeric.profile{times[], speed_cm_s{본: []}}`(타격 구간 찾기). 절대 속도 임계값은 쓰지 않음(정상 공격 p99 ≈ 2,000°/s). 상태 `PASSED`·`PASSED_WITH_WARNINGS`·`NEEDS_REVIEW`·`FAILED`, `needs_review[]` 에 시각 확인 항상 포함 |

**AI 애니 생성 — 기존 모션 재사용·변형 (3개, Phase 2).** 원본은 읽기만 하고 결과는 항상 새 애셋입니다(Phase 1 공통 가드 그대로 — 허용 목록 · `ASSET_EXISTS` · 전역 더티 검사).

| Tool | 입력 | 하는 일 |
| :--- | :--- | :--- |
| `search_animations` | `query?, skeleton?, path_prefix=/Game, class=AnimSequence\|AnimMontage\|AnimComposite\|all, min_length?, max_length?, root_motion?, additive?, loop?, tags?[], limit=50, details=false, max_loads=300` | 읽기 전용 메타데이터 검색. 인덱스 = AssetRegistry 태그(로드 없음: 길이 · 프레임 · fps · 루트 모션 · additive · 스켈레톤) + 수동 태그 파일(`AnimationTagFiles`, `{"tags": {"<애셋 또는 폴더/>": [..]}}`). 이름 토큰(`_`·CamelCase·숫자 경계) 접두 일치, 점수순. `bLoop` 은 레지스트리 태그가 아니라 `loop` 필터·`details` 만 로드(`max_loads` 초과 `LOAD_LIMIT`). `details` = 루프 · 노티파이 · 싱크 마커 · 커브 · 루트 이동량·Yaw |
| `preview_animation_edits` | `source, operations[], asset_path?, loop?, root_motion?` | 애셋을 만들지 않고 메모리 버퍼에서 끝까지 계산. 파싱 오류는 모든 op 에 한 번에, 실행 오류는 첫 op 에서 멈추고 나머지 `skipped`. `planned[{range, length_before/after, note}]` · 결과 프레임·길이·커브·루트 Yaw · 노티파이 유지/제외 · `seams[{step_ratio, jump}]` · `would_create{allowed, exists}` |
| `apply_animation_edits` | `source, asset_path, operations[], loop?, root_motion?, validate=true, thresholds?, save` | 버퍼 계산 성공 뒤에만 주 소스를 **복제**(`StaticDuplicateObject` — 루트 모션·압축·additive 설정·커브 메타 승계)하고 본 트랙·float 커브를 다시 씀(노티파이·싱크 마커는 먼저 비우고 새 시각으로 다시 건다 — 잘린·역재생 구간 것은 `NOTIFIES_DROPPED`). 출력 fps = 주 소스. 내장 검증 = 구조 · 한 프레임 회전(소스 최대 × 최대 재생 속도 안은 `ROTATION_JUMP_INHERITED`) · 쓰기 충실도 `expect`(길이·루프·루트 Yaw) · `seams`. FAILED 면 저장 없이 `VALIDATION_FAILED`(애셋은 미저장으로 남음). 소스의 트랜스폼 커브·본 속성은 옮기지 않음(경고) |

키 편집 op (시간은 초, 각 op 직전 타임라인 기준, 구간은 가장 가까운 프레임으로):

| op | 입력 | 비고 |
| :--- | :--- | :--- |
| `trim` | `start?, end?` | 구간만 남김 |
| `retime` | `start?, end?, rate \| duration` | 구간 재생 속도(1.5 = 1.5배 빠르게). 전체 재샘플(회전 slerp) |
| `hold_pose` | `at, duration` | 그 시각 포즈를 정지 삽입. `at` = 끝이면 연장 |
| `concat` | `asset?(생략 = 원래 source), start?, end?, reverse=false, blend=0, align_root=true` | 같은 스켈레톤만(`SKELETON_MISMATCH` — 먼저 리타깃). `blend=0` 이면 붙는 첫 키가 현재 끝 키와 겹친다(한 동작을 자른 두 구간을 이으면 원래대로). 한쪽에만 있는 커브는 0 (`CURVE_FILLED`) |
| `mirror` | `axis=x, mirror_table?` | 엔진 `MirrorPose` 수식. 짝 = 프로젝트 Animation 설정 미러 규칙 또는 MirrorDataTable, **짝 없는 본은 자기 자신으로 반전**(엔진 5.7 `FillMirrorBoneIndexes` 는 짝 없는 본을 반전하지 않는다). 커브는 반전하지 않음(`MIRROR_CURVES_UNCHANGED`) |
| `offset_bone` | `targets[{bone, rotation?{pitch,yaw,roll}, translation?[x,y,z]}], space=component\|local, start?, end?, blend_in=0.2, blend_out=0.2` | component = 컴포넌트 축으로 본 위치를 축으로 회전(자식이 따라옴), local = 본 자신의 축 · 이동은 부모 공간 |
| `rotate_root` | `yaw, start?, end?, ease=smooth\|linear` | 구간 동안 루트 Yaw 0 → yaw, 이후 유지. 루트 이동 증분도 그 시점 Yaw 로 돌려 다시 쌓음 |

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

**`set_property` 허용 목록** (노드의 `properties` 조회가 곧 목록입니다): SequencePlayer `bLoopAnimation, PlayRate, StartPosition, PlayRateBasis, GroupName, GroupRole, Method, bStartFromMatchingPose, bIgnoreForRelevancyTest`(자동 전이의 관련 플레이어 선정 제외 — BlendSpacePlayer 도 같다) · BlendSpacePlayer·AimOffset(RotationOffsetBlendSpace) `bLoop, PlayRate, StartPosition, X, Y, bResetPlayTimeWhenBlendSpaceChanges, GroupName, GroupRole, Method` + AimOffset `Alpha, LODThreshold, AlphaInputType, bAlphaBoolEnabled, AlphaCurveName, AlphaScaleBias, AlphaScaleBiasClamp, AlphaBoolBlend` · SequenceEvaluator `ExplicitTime, bUseExplicitFrame, ExplicitFrame, bShouldLoop, bTeleportToExplicitTime, ReinitializationBehavior, StartPosition, GroupName, GroupRole, Method` · ApplyAdditive · TwoBoneIK · ModifyBone(공통 `Alpha, LODThreshold, AlphaInputType, bAlphaBoolEnabled, AlphaCurveName, AlphaScaleBias, AlphaScaleBiasClamp, AlphaBoolBlend`) · TwoBoneIK `IKBone, EffectorLocation, EffectorLocationSpace, EffectorTarget, JointTargetLocation, JointTargetLocationSpace, JointTarget, bAllowStretching, StartStretchRatio, MaxStretchScale, bTakeRotationFromEffectorSpace, bMaintainEffectorRelRot, bAllowTwist, TwistAxis` · ModifyBone `BoneToModify, Translation, Rotation, Scale, TranslationMode, RotationMode, ScaleMode, TranslationSpace, RotationSpace, ScaleSpace` · CopyBone `SourceBone, TargetBone, bCopyTranslation, bCopyRotation, bCopyScale, ControlSpace`(2026-10-21, 왼손 IK 체인) · Mirror `bMirror, MirrorDataTable, BlendTime, bResetChild, bBoneMirroring, bCurveMirroring, bAttributeMirroring` · Inertialization `DefaultBlendProfile, FilteredCurves, FilteredBones, bResetOnBecomingRelevant, bForwardRequestsThroughSkippedCachedPoseNodes` · Slot `SlotName, bAlwaysUpdateSourcePose` · SaveCachedPose `CacheName` · UseCachedPose `SaveCachedPoseNode`(노드 참조) · LayeredBoneBlend `bMeshSpaceRotationBlend, bMeshSpaceScaleBlend, bBlendRootMotionBasedOnRootBone, LODThreshold, BlendMode, LayerSetup, BlendMasks, CurveBlendOption, bRootSpaceRotationBlend` · BlendList `BlendTime[], TransitionType, BlendType, ChildUpateMode, CustomBlendCurve, BlendProfile` · BlendListByEnum `BoundEnum` · 전이 `CrossfadeDuration, PriorityOrder, BlendMode, Bidirectional, bDisabled, bAutomaticRuleBasedOnSequencePlayerInState, AutomaticRuleTriggerTime, LogicType`(`TLT_StandardBlend | TLT_Inertialization | TLT_Custom` — 관성 블렌드는 하류에 Inertialization 노드가 있어야 하며, 링크된 레이어 안의 상태머신이면 베이스 그래프의 노드가 받는다) · 상태 `bAlwaysResetOnEntry`. 목록 밖 프로퍼티는 `PROPERTY_NOT_ALLOWED`.

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
| 400 | `BAD_REQUEST`(`details.reason`/`field`) · `CONNECTION_REJECTED` · `PROPERTY_NOT_ALLOWED` · `COMPILE_FAILED` · `SAVE_FAILED` · `IMPORT_FAILED` · `IKRIG_AUTO_FAILED` · `RETARGET_FAILED` · `VALIDATION_FAILED` |
| 401 | `UNAUTHORIZED` |
| 403 | `ASSET_PROTECTED` · `OUTPUT_PATH_NOT_ALLOWED` · `IMPORT_SOURCE_NOT_ALLOWED` |
| 404 | `TOOL_NOT_FOUND` · `ASSET_NOT_FOUND` · `GRAPH_NOT_FOUND` · `NODE_NOT_FOUND` · `PIN_NOT_FOUND` |
| 409 | `ASSET_EXISTS` · `REVISION_MISMATCH` · `ASSET_REFERENCED` · `DIRTY_PACKAGES` · `UNEXPECTED_DIRTY`(`details.unexpected[]`) |
| 500 | `INTERNAL` |

배치 실패의 원인은 사전 검증이면 `details.planned[i].error`, 적용 중이면 `details.cause` 와 `details.applied[i].error` 에 있습니다. Python 클라이언트는 전송 오류를 `EDITOR_GONE` · `TIMEOUT` · `TRANSPORT` · `BAD_RESPONSE` 로 같은 봉투 모양에 넣습니다.

## 검증 — 스모크 테스트

`run_automation_tests {"filter": "AnimGraphMcp.Smoke"}` 는 `SmokeTestPaths` 아래 **모든 AnimBP 를 애셋마다 테스트 하나**로 엽니다(`AnimGraphMcp.Smoke.AnimBlueprint.<이름>`): 컴파일 0 에러 · 루트 Output Pose 연결 · 빈 상태(StateResult 미연결) · 끊긴 UseCachedPose · 무효 Linked Anim Layer. 레이어 제공자 ABP(인터페이스 구현만 하고 루트를 쓰지 않는 Lyra 식)의 빈 루트와 빈 레이어 구현은 **경고**입니다.

같은 경로의 **모든 AnimMontage** 도 애셋마다 하나(`AnimGraphMcp.Smoke.AnimMontage.<이름>`): 슬롯이 스켈레톤에 등록됨(오류) · 섹션 존재·시작 시간 범위·Next 존재(오류) · 첫 섹션 0 시작(경고) · 호환 스켈레톤의 AnimBP 에 그 이름의 Slot 노드가 있음(경고 — 없으면 어느 그래프에서도 재생되지 않을 수 있음). 프로젝트 자체 Automation 테스트도 같은 Tool 로 돌릴 수 있습니다.

## 검증 — 런타임 시나리오 (PIE)

`run_anim_scenario` 는 "구조가 말이 되는가" 다음의 "실제로 그 상태로 가는가" 를 봅니다. 예:

```jsonc
{ "asset_path": "/Game/Characters/Enemy/ABP_Grunt", "mesh": "/Game/Characters/Enemy/SK_Grunt",
  "set_variables": { "Speed": 300, "bIsAttacking": true }, "montage": "/Game/Characters/Enemy/AM_Grunt_Attack",
  "wait_frames": 10, "expect": { "state_machines": { "Locomotion": "Run" }, "slots_active": ["UpperBody"] } }
```

- 테스트(`AnimGraphMcp.Runtime.AnimBlueprint`)가 **PIE 를 직접 엽니다** — 바깥에서 PIE 를 켜 두면 `PIE_ACTIVE` 로 거부됩니다(`StartTestByName` 이 PIE 중에는 시작하지 않음). `map` 을 주면 그 맵으로, 없으면 에디터에 열린 월드로 PIE 를 돌립니다.
- 변수는 스폰 직후 한 번 리플렉션으로 씁니다. **매 프레임 변수를 다시 계산하는 네이티브 AnimInstance(폰 속도 → Speed 등)는 값을 덮어쓰므로**, 변수로 몰고 가는 시나리오는 BP 변수(`add_blueprint_variable`)나 부모 `UAnimInstance` 로 만든 ABP 에서 씁니다. 운영 ABP 는 변수 없이 "진입 상태" 만 보는 식으로 씁니다.
- 슬롯 활성은 몽타주가 재생 중일 때만 참이 됩니다(`montage` 없이 `slots_active` 를 기대하면 `NO_MONTAGE` 경고). 몽타주가 슬롯을 가중치 1 로 덮는 동안 슬롯 노드는 **Source(그 뒤의 상태머신)를 갱신하지 않습니다**(`bAlwaysUpdateSourcePose` 가 꺼진 기본값) — 전신 슬롯 뒤의 상태 전이를 몽타주 중에 보려면 그 Slot 노드에 `set_property bAlwaysUpdateSourcePose=true`.
- 메시 호환 검사는 엔진이 AnimInstance 를 만들지 말지 보는 기준 그대로(`USkeleton::IsCompatibleMesh`, 본 이름 집합)라 본 이름이 같은 다른 스켈레톤(UE5 마네킹 계열)도 통과합니다.
- 관측은 테스트 결과의 `observed` 에 남고, 기대값과 다르면 `errors[]` 에 "expected 'Run' but it is in 'Idle' after 10 frames" 식으로 적힙니다. 실제 포즈(본 트랜스폼)는 범위 밖입니다.

## 제약 (설계상 범위 밖)

- **임의의 EventGraph 편집은 다루지 않습니다.** BP 변수 추가와 `BlueprintThreadSafeUpdateAnimation` 의 "변수 ← 식" 대입 사슬까지가 범위이고, 분기·루프·이벤트·임의 K2 노드는 만들지 않습니다. 복잡한 상태 판정은 C++ AnimInstance 에 두는 것을 권합니다.
- 전이 규칙의 `call` 은 화이트리스트 함수만, `set_property` 는 허용 목록 프로퍼티만입니다. 허용 목록 밖 노드(Control Rig·PoseDriver·RigidBody·AnimDynamics·Motion Matching 등)는 생성·연결은 되지만 세부 설정은 못 합니다. 필요하면 `Core/AnimMcpPropertyRules.cpp` 의 표에 한 줄씩 더합니다.
- Linked Anim Layer 의 값 파라미터는 **Input Pose 노드에 붙습니다**(엔진 구조) — 입력 포즈 없는 레이어는 값 파라미터를 가질 수 없습니다. 자식 Animation Blueprint 가 부모의 레이어를 오버라이드하는 그래프 생성은 범위 밖입니다. 인터페이스 변경 뒤 구현 ABP 동기화는 AssetRegistry 참조자(디스크에 저장된 ABP) 기준입니다.
- 생성하는 콘텐츠 애셋은 BlendSpace·AimOffset·몽타주(시퀀스 1개, 슬롯·섹션)입니다. **노티파이**(프로젝트별 클래스)·몽타주 다중 세그먼트·블렌드 프로파일·싱크 마커는 범위 밖입니다. 스켈레톤 편집은 슬롯 등록(`add_skeleton_slot`, `confirm` 필수)과 애셋의 스켈레톤 재할당(`reassign_skeleton` — 본 이름이 같은 스켈레톤 사이, **제자리**)뿐입니다. 본·기준 포즈가 다른 스켈레톤으로는 IK 리타깃(`create_ik_rig` → `create_ik_retargeter` → `retarget_animations`, 항상 복제)을 씁니다. 시퀀스 키 편집은 원본을 바꾸지 않고 새 애셋으로만 합니다(`apply_animation_edits` — op 7종, 원시 키 기준이라 트랜스폼 커브·본 속성은 옮기지 않음). 제자리 편집은 additive 설정(`set_sequence_additive`)뿐입니다.
- 검증은 구조 검사(스모크)·상태머신 현재 상태·슬롯 활성(런타임 시나리오)·시퀀스 수치(`validate_animation`)까지입니다. 수치 통과가 동작 품질을 뜻하지 않습니다 — 애니메이션 품질은 Persona/PIE 에서 사람이 봅니다.
- IK 리타깃은 FK 체인 매핑이 **정확한 이름**입니다(엔진 fuzzy 매핑은 발가락을 손가락에 붙이기도 함). 템플릿이 없는 스켈레톤은 수동 체인 이름을 대상 리그의 체인 이름과 맞춥니다. 리타깃 포즈 수동 편집·IK op 세부 설정은 범위 밖입니다.
- 한 포트에 에디터 하나. PIE 중이거나 모달 작업(`GIsSlowTask`) 중에는 Automation 테스트가 시작되지 않습니다(런타임 시나리오는 테스트가 PIE 를 열고 닫습니다).
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
            AnimMcpAssetProtection  보호 목록   AnimMcpAssetOps  삭제·복제·참조자(레지스트리 · 삭제 거부는 메모리 참조자까지)
            AnimMcpAutomationRunner FAutomationTestFramework 구동 · 잡
            AnimMcpPropertyAccessNode  UK2Node_PropertyAccess 리플렉션(엔진 플러그인의 비공개 노드)
            AnimMcpVariables        BP 멤버 변수 추가·삭제 · 타입 문자열
            AnimMcpUpdateFunction   BlueprintThreadSafeUpdateAnimation 함수 그래프 생성·재생성
            AnimMcpMontage          몽타주 생성(시퀀스 1개) · 슬롯 이름 · 섹션 전체 교체 · 스켈레톤 슬롯 등록 · 조회
            AnimMcpRuntimeScenario  런타임 시나리오 계약 — 테스트 명령 "<클래스> <JSON>" · 관측 슬롯(테스트 → 러너 → observed)
            AnimMcpGeneration       AI 애니 생성 공통 가드: [AnimGraphMcp] 생성 경로 설정 · 출력/임포트 경로 검사 · 전역 더티 집합 비교(FDirtyGuard) ·
                                    새 애셋 객체 · 복제본(덮어쓰기 없음) · FinishWrite(검사 → 저장)
            AnimMcpSkeletonInspector  스켈레톤 조회 · 기준 포즈 비교 · 템플릿 캐릭터라이즈(트랜지언트 IK Rig)
            AnimMcpAnimImport       Interchange FBX 임포트(파이프라인 트랜지언트 복제·안전 설정)
            AnimMcpRetargetAssets   IK Rig · 리타기터 생성(에디터 자동 리타깃 레시피) · 조회
            AnimMcpBatchRetarget    일괄 리타깃(계획 → RunRetarget → 계획대로 생겼는지 → 검증 → 저장)
            AnimMcpAnimValidator    시퀀스 측정(구조 · 절대 · 상대 · 회귀 · 요청 충족 · 프로파일)   AnimMcpStats  백분위 · 반올림
            AnimMcpAnimSearch       search_animations — 레지스트리 태그 · 이름 토큰 · 수동 태그 파일 · 필요할 때만 로드
            AnimMcpAnimEditOps      키 편집 계산부(UObject 없음 — 리그 · 버퍼 · op 7종 · 출처 · 이음매) — 단위 테스트 대상
            AnimMcpAnimEdit         preview/apply_animation_edits — 파싱 · 원시 키 읽기 · 버퍼 계산 · 복제 · 재작성 · 노티파이 이동 · 검증
  Tests/    AnimMcpSmokeTests.cpp    AnimGraphMcp.Smoke.AnimBlueprint · AnimGraphMcp.Smoke.AnimMontage
            AnimMcpRuntimeTests.cpp  AnimGraphMcp.Runtime.AnimBlueprint — PIE 시작·스폰·변수·몽타주·N 프레임·관측·비교·PIE 종료(지연 명령 7단계)
            AnimMcpGenerationTests.cpp  AnimGraphMcp.Generation.Guard — 경로 '/' 경계 · 임포트 원본 · 허용 목록 밖 새 더티 → UNEXPECTED_DIRTY(메모리 패키지)
            AnimMcpEditTests.cpp     AnimGraphMcp.Generation.Edit — 합성 리그로 op 수학(길이 · 키 대응 · 이음매 · 미러 두 번 = 원래 · 컴포넌트 축 회전)
  Tools/    AnimMcpTools_*.cpp       Tool 핸들러(얇음; Montage = 몽타주·스켈레톤 슬롯 4종 · Automation = run/poll + run_anim_scenario 사전 검증 ·
                                     Skeleton = reassign_skeleton(EditorAnimUtils::RetargetAnimations 제자리) + inspect_skeleton · Sequence = set_sequence_additive ·
                                     Import = import_animation_file · Retarget = create_ik_rig · create_ik_retargeter · retarget_animations ·
                                     Validate = validate_animation · Search = search_animations · Edit = preview/apply_animation_edits)
```

AI 애니 생성 Tool 통합 테스트: `Tools/mcp/anim_gen_phase1_test.py`(섹션 inspect · guard · import · rig · validate · retarget · regression · dirty, 결과 요약 `anim_gen_phase1_state.json`) · `Tools/mcp/anim_gen_phase2_test.py`(섹션 hashes · search · unit · preview · guard · upper · ready · variant · mirror · notify · appendix · regression · dirty, 결과 요약 `anim_gen_phase2_state.json`). FBX 픽스처는 `Tools/scripts/anim_gen_export_fixture.py` 가 만든다.

규칙: Inspector 는 쓰지 않고, Mutator 는 트랜잭션 밖에서 호출되지 않습니다. 같은 `FJsonObject` 를 두 컨테이너에 넣지 않습니다(순환 → 직렬화 무한 재귀).
