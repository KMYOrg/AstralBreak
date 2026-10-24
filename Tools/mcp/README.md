# AnimGraph MCP

Claude Code ↔ (stdio MCP) ↔ `Tools/mcp/anim_graph_mcp/server.py` ↔ (HTTP/JSON, 127.0.0.1:18765) ↔ `Plugins/AnimGraphMcp` (에디터 C++)

플러그인 쪽 전체 참조(Tool 30개 · op 20종 · 오류 코드 · 제약 · 소스 구조)는 [`Plugins/AnimGraphMcp/README.md`](../../Plugins/AnimGraphMcp/README.md). 설계·API 근거는 `.claude/plans/animbp-automation-phase1.md`.

## 설치 (1회)

```
python -m venv Tools/mcp/.venv
Tools/mcp/.venv/Scripts/python.exe -m pip install -r Tools/mcp/requirements.txt
```

프로젝트 루트의 `.mcp.json` 이 Claude Code 에 서버 `anim-graph-mcp` 를 등록한다:

```json
{ "mcpServers": { "anim-graph-mcp": {
    "command": "Tools/mcp/.venv/Scripts/python.exe",
    "args": ["Tools/mcp/anim_graph_mcp/server.py"],
    "env": { "ANIMGRAPH_MCP_PORT": "18765" } } } }
```

에디터는 `Plugins/AnimGraphMcp` 가 활성화된 상태로 떠 있어야 한다. 다른 프로젝트에 옮길 때는 `Plugins/AnimGraphMcp` + `Tools/mcp`(venv 제외) + `.mcp.json` 을 복사하고 `.uproject` 에 플러그인을 등록한 뒤 에디터 타깃을 빌드한다. 토큰 파일 위치는 `<프로젝트>/Saved/AnimGraphMcp/token` 이고 `bridge.py` 가 자기 위치에서 프로젝트 루트를 찾는다(`ANIMGRAPH_MCP_PROJECT_DIR` 로 오버라이드).

## 설정

`Config/DefaultEngine.ini` (없으면 기본값):

```
[AnimGraphMcp]
Port=18765
bRequireToken=True
bAutoStart=True
+ProtectedAssets=/Game/Animation/Hero/ABP_Hero_Base   ; 삭제·덮어쓰기 거부 — 패키지 또는 오브젝트 경로, 정확히 일치
+ProtectedPaths=/Game/Assets/                          ; 삭제·덮어쓰기 거부 — 패키지 경로 접두
+SmokeTestPaths=/Game/Animation                        ; 스모크 테스트가 여는 AnimBP 경로
```

에디터 콘솔: `AnimGraphMcp.Start` / `AnimGraphMcp.Stop` / `AnimGraphMcp.Status`. 커맨드라인 `-AnimGraphMcpPort=18766` 으로 인스턴스별 포트 오버라이드. 토큰은 에디터가 기동할 때 `Saved/AnimGraphMcp/token` 에 쓴다. `get_editor_status` 만 토큰 면제.

## Tool (39개)

AI 애니 생성 리타깃 기반(Phase 1, `Docs/AIAnimation/`) `inspect_skeleton` · `import_animation_file` · `create_ik_rig` · `create_ik_retargeter` · `retarget_animations` · `validate_animation` — 출력·임포트 경로는 `[AnimGraphMcp] GenerationOutputPaths` · `ImportSourceRoots`(`get_editor_status.generation`)만, 덮어쓰기 없음, 허용 목록 밖이 새로 더티면 `UNEXPECTED_DIRTY`. 흐름: `inspect_skeleton`(소스·대상, `compare_to`) → `import_animation_file`(FBX) → `create_ik_rig`(auto, 실패면 `details.bones` 로 수동 체인 제안 → 사용자 확인 → manual) → `create_ik_retargeter` → `retarget_animations {dry_run}` → 같은 호출 `save:true`. 소스와 대상이 보는 방향이 다르면(예: SB +X ↔ Vesper +Y) `create_ik_retargeter {facing_yaw_deg: 90}` — FK 체인은 전역 회전 델타라 그대로면 동작이 다른 평면으로 휜다(대상 루트 반대 회전 + Additive Pose op 로 되돌림, 결과 `facing_alignment`). anim-gen-mcp 는 이 값을 계획 때 재서 넣는다(`retarget.source_facing`).

AI 애니 생성 기존 모션 재사용·변형(Phase 2) `search_animations`(레지스트리 태그 + 수동 태그 `Config/AnimGraphMcp/AnimationTags.json`, 이름 토큰) · `preview_animation_edits` · `apply_animation_edits`(op 7종 `trim` · `retime` · `hold_pose` · `concat` · `mirror` · `offset_bone` · `rotate_root`, 원본은 읽기만 · 결과는 새 애셋) — `validate_animation` 에 요청 충족 `expect` · `seams` · `profile_bones`(+ `profile_positions` 면 같은 시각의 컴포넌트 위치). 흐름: `search_animations` → (다른 스켈레톤이면 Phase 1 리타깃) → `validate_animation {profile_bones:["hand_r"]}` 로 구간 찾기 → `preview_animation_edits` → `apply_animation_edits {save:true}` → Persona 에서 사람이 확인.

조회 `get_editor_status` · `get_anim_blueprint_info` · `get_anim_graph_structure` · `list_animation_assets` — 생성/저장 `create_animation_blueprint` · `create_blendspace`(`aim_offset` 로 AimOffset) · `create_anim_layer_interface` · `implement_anim_layer_interface` · `save_animation_blueprint` · `duplicate_animation_blueprint` · `delete_animation_blueprint` — 레이어 `set_layer_inputs`(값 파라미터) · `add_anim_layers` · `remove_anim_layers`(구현 ABP 자동 동기화) — 편집 `preview_graph_operations` · `apply_graph_operations`(op 20종, `set_layer_instance_class` 포함) · `compile_animation_blueprint` — 변수·업데이트 함수 `add_blueprint_variable` · `remove_blueprint_variable` · `set_update_function`(ThreadSafeUpdateAnimation 을 스펙에서 생성) — 몽타주 `create_anim_montage` · `set_montage_slots` · `set_montage_sections` · `add_skeleton_slot`(노티파이는 `Tools/lib/ab_montage.py`) — 콘텐츠 선행 `reassign_skeleton`(같은 본 이름의 중복 스켈레톤 통합, 참조 애셋 동반) · `set_sequence_additive`(AimOffset 샘플 기준 포즈) — 검증 `run_automation_tests` · `poll_automation_tests` · `run_anim_scenario`(PIE 에서 상태머신 현재 상태·슬롯 활성 확인) — 프로세스 `quit_editor`.

실전 적용 스크립트: `reassign_hero_skeleton.py`(히어로 애셋 40개 스켈레톤 통합, 1회성) · `build_hero_combat.py`(히어로 전투 ABP — Lyra 식 레이어 · 근접/원거리 · 조준 strafe, 설계는 `.claude/plans/hero-combat-abp.md`) · `build_hero_turninplace.py`(제자리 회전 — 베이스 RotateRootBone + 공급자 조준 Idle 상태머신 IdleTurn, 제자리 패치·멱등, `--verify-only`; build_hero_combat 이 끝에 호출). PIE 실측은 `Tools/scripts/pie_turn_probe_run.py`(에디터 밖에서 `pie_aim_probe.py` 단계를 순서대로 — 조준 → 컨트롤러·액터 Yaw +90 → 틱마다 RootYawOffset 등 기록).

각 Tool 의 입력과 op 사전은 `server.py` 의 docstring(= Claude 가 보는 설명)과 플러그인 README 에 있다. 새 Tool 은 Claude Code 세션을 다시 시작해야 MCP 목록에 보인다.

전형적인 흐름: `get_anim_blueprint_info` 로 `revision`·`variables` 확인 → `get_anim_graph_structure` 로 Guid 파악 → `preview_graph_operations` → `apply_graph_operations {expected_revision, compile:true, save:true}` → `run_automation_tests {"filter": "AnimGraphMcp.Smoke"}` → `run_anim_scenario {asset_path, set_variables, expect}` + `poll_automation_tests` 로 "Speed 300 → Run" 같은 런타임 동작 확인(테스트가 PIE 를 열고 닫는다 — 에디터에서 PIE 를 켜 두지 말 것).

## anim-gen-mcp (AI 애니 생성 — 정책 · 라우터 · 폴백 · Job)

두 번째 MCP 서버 `Tools/mcp/anim_gen/server.py`(`.mcp.json` 의 `anim-gen-mcp`). 로직은 여기에만 있고 에디터 조작은 `anim_graph_mcp/bridge.py` 로 위 플러그인 Tool 을 부른다. 설계·시그니처는 `Docs/AIAnimation/DevelopmentGuide.md` §3.4 · §5 · §6 · §7 · §9 · §14 Phase 3.

- Tool 9개: `list_motion_providers` · `get/set_generation_policy` · `plan_motion_generation`(실행 안 함 — 읽기 전용 에디터 호출로 소스·메시·미리보기를 계획에 고정) · `estimate_generation_cost` · `approve_generation`(계획 × 유료 Provider 하나, 횟수 · 금액 상한) · `generate_motion` · `get_generation_status`(비동기 단계 poll) · `cancel_generation`.
- 흐름: Claude Code 가 자연어를 구조화된 요청(§9)으로 바꾼다 → `plan_motion_generation` → 사용자에게 계획을 보여 준다 → (유료면 `estimate_generation_cost` → 사용자 동의 → `approve_generation`) → `generate_motion {save}` → 결과의 `limitations[]` 를 사용자에게 알린다.
- 실제 Provider: `existing_motion`(검색·참조) · `direct_key`(`apply_animation_edits`) · `retarget` 파이프(IK Rig ×2 · RTG `match_existing` · `retarget_animations`) · `blender`(Phase 4 — 요청 `motion_file`(BVH, ini `ImportSourceRoots` 아래)을 headless Blender 서브프로세스로 FBX 로 바꿔 retarget 파이프로. 실행 파일은 정책 `paths.blender_executable`, 스크립트 `anim_gen/blender/bvh_to_fbx.py`, `generate_motion` 은 `RUNNING` 을 돌려주고 `get_generation_status` 가 poll). `local_ai` · `external.meshy` · `control_rig` 은 매니페스트(`anim_gen/providers.json`)와 비활성 자리만.
- 정책: `anim_gen/policy.default.json`(추적) ← `Saved/AnimGen/policy.json`(로컬). 출력 경로는 정책에 없고 ini `GenerationOutputPaths` 만 기준. API 키는 환경 변수만(값은 어디에도 기록하지 않는다).
- 상태: `Saved/AnimGen/{plans, jobs, approvals}/` · `ledger.jsonl`(유료 제출 예약·확정, 멱등 키 `(plan_id, attempt)`). `ANIM_GEN_STATE_DIR` 로 바꾼다. 중간 애셋은 `<output_path>/Work/<job_id>/A<시도>/`.
- 새 서버는 Claude Code 세션을 다시 시작해야 목록에 보인다.

테스트 — Mock 단계(에디터 없음, §15 D · E 포함)와 에디터 통합:

```
Tools/mcp/.venv/Scripts/python.exe -m pip install -r Tools/mcp/requirements-dev.txt
Tools/mcp/.venv/Scripts/python.exe -m pytest Tools/mcp/anim_gen/tests -q
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase3_test.py [--only plan,generate]
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase4_test.py [--bvh <path>|synthetic] [--only plan,generate]
```

`anim_gen_phase3_test.py` 는 뜬 에디터에 붙어 섹션 hashes · mcp(stdio 로 서버 기동) · plan · generate(완료 기준 1건) · retarget · reuse · dirty 를 돌린다. 애셋은 `/Game/Animation/Test/AIAnimation/P3Run<시각>/`(저장), 상태는 `Saved/AnimGen/TestRuns/P3Run<시각>/`, 요약은 `anim_gen_phase3_state.json`.

`anim_gen_phase4_test.py` 는 뜬 에디터 + 정책의 실제 Blender 로 섹션 hashes · blender · plan · generate(BVH → Vesper `AS_` 저장 · 임포트 스켈레톤 측정 · `validate_animation`) · auto(체인 없이) · cancel(실제 프로세스 종료) · dirty 를 돌린다. 기본 BVH 는 `Saved/AnimGen/Import/Sources/CMU_01_01/01_01.bvh`(CMU 모캡, 별도로 받는다), `--bvh synthetic` 은 합성 BVH. 요약은 `anim_gen_phase4_state.json`.

## 수동 확인 · 테스트

```
Tools/mcp/.venv/Scripts/python.exe Tools/mcp/smoke_test.py /Game/Animation/Hero/ABP_Hero_Base
```

전체 회귀는 `run_all.py` 하나로 — 에디터 기동 → 단계 테스트(`phase3/4/5/6_1/6_3/6_4/6_4b/7_1/7_2/7_3/7_4/7_5/7_6/6_5/6_2_test.py`) → 종료 → 재기동 → 각 `--recheck` → 종료, 결과 `Tools/mcp/results/<date>.json`:

```
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/run_all.py [--attach] [--only phase6_5_test] [--skip-recheck]
```

AI 애니 생성 Tool 은 `anim_gen_phase1_test.py`(뜬 에디터에 붙어 섹션 inspect · guard · import · rig · validate · retarget · regression · dirty, `--only` 로 골라 실행 · 요약 `anim_gen_phase1_state.json`) — 테스트 애셋은 `/Game/Animation/Test/AIAnimation/Run<시각>/`(완료 기준 1 의 왕복 결과만 저장), FBX 픽스처는 `Saved/AnimGen/Import/`(`Tools/scripts/anim_gen_export_fixture.py` 가 자동 생성). `run_all.py` 에는 넣지 않았다(저장되는 왕복 애셋이 실행마다 쌓인다). Phase 2 는 `anim_gen_phase2_test.py`(섹션 hashes · search · unit · preview · guard · upper · ready · variant · mirror · notify · appendix · regression · dirty · 요약 `anim_gen_phase2_state.json`) — 애셋은 `/Game/Animation/Test/AIAnimation/P2Run<시각>/`(완료 기준 3건 · Narmaya 리타깃만 저장).

Git Bash 에서 `/Game/...` 인자는 `MSYS_NO_PATHCONV=1`, 한글 출력은 `PYTHONIOENCODING=utf-8`. 개별 스크립트와 기동·종료 폴링(`wait_for_bridge.py` · `wait_for_exit.py`)은 `.claude/plans/animbp-automation-handoff-phase6-2.md` §8 참조. 테스트 애셋은 `/Game/Animation/Test/` 아래(덮어쓰기 대상).

## 응답 봉투

```json
{ "ok": true, "tool": "get_editor_status", "request_id": "…", "result": {…}, "error": null, "diagnostics": [] }
{ "ok": false, "tool": "…", "request_id": "…", "result": null, "error": { "code": "ASSET_NOT_FOUND", "message": "…" }, "diagnostics": [] }
```

같은 `(tool, request_id)` 재전송은 캐시된 봉투를 돌려주고 핸들러를 다시 실행하지 않는다. 전송 오류는 `bridge.py` 가 `EDITOR_GONE` · `TIMEOUT` · `TRANSPORT` · `BAD_RESPONSE` 로 같은 모양에 넣는다.
