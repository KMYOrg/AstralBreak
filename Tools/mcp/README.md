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

## Tool (40개)

AI 애니 생성 연결 · 승격(Phase 7) `promote_animation`(후보 `GenerationOutputPaths` → 정식 `[AnimGraphMcp] PromotionPaths` — 엔진 AssetTools rename, 리디렉터 0 · 참조자 자동 수정 · 저장. **`dry_run` → 사용자 확인 → `confirm`**, 후보 밖 참조자는 `allow_referencers` 로 명시) · 기존 쓰기 Tool 6개(`create_anim_montage` · `set_montage_sections` · `create_blendspace` · `set_sequence_additive` · `duplicate_animation_blueprint` · `apply_graph_operations`)의 옵트인 `generation_guard`(기본 false = 기존 동작 그대로 · true = 허용 목록 안 · 덮어쓰기 거부 · 전역 더티 비교 — 운영 AnimBP 는 가드가 거부한다).

AI 애니 생성 리타깃 기반(Phase 1, `Docs/AIAnimation/`) `inspect_skeleton` · `import_animation_file` · `create_ik_rig` · `create_ik_retargeter` · `retarget_animations` · `validate_animation` — 출력·임포트 경로는 `[AnimGraphMcp] GenerationOutputPaths` · `ImportSourceRoots`(`get_editor_status.generation`)만, 덮어쓰기 없음, 허용 목록 밖이 새로 더티면 `UNEXPECTED_DIRTY`. 흐름: `inspect_skeleton`(소스·대상, `compare_to`) → `import_animation_file`(FBX) → `create_ik_rig`(auto, 실패면 `details.bones` 로 수동 체인 제안 → 사용자 확인 → manual) → `create_ik_retargeter` → `retarget_animations {dry_run}` → 같은 호출 `save:true`. 소스와 대상이 보는 방향이 다르면(예: SB +X ↔ Vesper +Y) `create_ik_retargeter {facing_yaw_deg: 90}` — FK 체인은 전역 회전 델타라 그대로면 동작이 다른 평면으로 휜다(대상 루트 반대 회전 + Additive Pose op 로 되돌림, 결과 `facing_alignment`). anim-gen-mcp 는 이 값을 계획 때 재서 넣는다(`retarget.source_facing`).

AI 애니 생성 기존 모션 재사용·변형(Phase 2) `search_animations`(레지스트리 태그 + 수동 태그 `Config/AnimGraphMcp/AnimationTags.json`, 이름 토큰) · `preview_animation_edits` · `apply_animation_edits`(op 8종 `trim` · `retime` · `time_warp`(8-3 후속 — 매끈한 시각 사상 + antialias) · `hold_pose` · `concat` · `mirror` · `offset_bone` · `rotate_root`, 원본은 읽기만 · 결과는 새 애셋) — `validate_animation` 에 요청 충족 `expect` · `seams` · `profile_bones`(+ `profile_positions` 면 같은 시각의 컴포넌트 위치). 흐름: `search_animations` → (다른 스켈레톤이면 Phase 1 리타깃) → `validate_animation {profile_bones:["hand_r"]}` 로 구간 찾기 → `preview_animation_edits` → `apply_animation_edits {save:true}` → Persona 에서 사람이 확인.

조회 `get_editor_status` · `get_anim_blueprint_info` · `get_anim_graph_structure` · `list_animation_assets` — 생성/저장 `create_animation_blueprint` · `create_blendspace`(`aim_offset` 로 AimOffset) · `create_anim_layer_interface` · `implement_anim_layer_interface` · `save_animation_blueprint` · `duplicate_animation_blueprint` · `delete_animation_blueprint` — 레이어 `set_layer_inputs`(값 파라미터) · `add_anim_layers` · `remove_anim_layers`(구현 ABP 자동 동기화) — 편집 `preview_graph_operations` · `apply_graph_operations`(op 20종, `set_layer_instance_class` 포함) · `compile_animation_blueprint` — 변수·업데이트 함수 `add_blueprint_variable` · `remove_blueprint_variable` · `set_update_function`(ThreadSafeUpdateAnimation 을 스펙에서 생성) — 몽타주 `create_anim_montage` · `set_montage_slots` · `set_montage_sections` · `add_skeleton_slot`(노티파이는 `Tools/lib/ab_montage.py`) — 콘텐츠 선행 `reassign_skeleton`(같은 본 이름의 중복 스켈레톤 통합, 참조 애셋 동반) · `set_sequence_additive`(AimOffset 샘플 기준 포즈) — 검증 `run_automation_tests` · `poll_automation_tests` · `run_anim_scenario`(PIE 에서 상태머신 현재 상태·슬롯 활성 확인) — 프로세스 `quit_editor`.

실전 적용 스크립트: `reassign_hero_skeleton.py`(히어로 애셋 40개 스켈레톤 통합, 1회성) · `build_hero_combat.py`(히어로 전투 ABP — Lyra 식 레이어 · 근접/원거리 · 조준 strafe, 설계는 `.claude/plans/hero-combat-abp.md`) · `build_hero_turninplace.py`(제자리 회전 — 베이스 RotateRootBone + 공급자 조준 Idle 상태머신 IdleTurn, 제자리 패치·멱등, `--verify-only`; build_hero_combat 이 끝에 호출). PIE 실측은 `Tools/scripts/pie_turn_probe_run.py`(에디터 밖에서 `pie_aim_probe.py` 단계를 순서대로 — 조준 → 컨트롤러·액터 Yaw +90 → 틱마다 RootYawOffset 등 기록).

각 Tool 의 입력과 op 사전은 `server.py` 의 docstring(= Claude 가 보는 설명)과 플러그인 README 에 있다. 새 Tool 은 Claude Code 세션을 다시 시작해야 MCP 목록에 보인다.

전형적인 흐름: `get_anim_blueprint_info` 로 `revision`·`variables` 확인 → `get_anim_graph_structure` 로 Guid 파악 → `preview_graph_operations` → `apply_graph_operations {expected_revision, compile:true, save:true}` → `run_automation_tests {"filter": "AnimGraphMcp.Smoke"}` → `run_anim_scenario {asset_path, set_variables, expect}` + `poll_automation_tests` 로 "Speed 300 → Run" 같은 런타임 동작 확인(테스트가 PIE 를 열고 닫는다 — 에디터에서 PIE 를 켜 두지 말 것).

## anim-gen-mcp (AI 애니 생성 — 정책 · 라우터 · 폴백 · Job)

두 번째 MCP 서버 `Tools/mcp/anim_gen/server.py`(`.mcp.json` 의 `anim-gen-mcp`). 로직은 여기에만 있고 에디터 조작은 `anim_graph_mcp/bridge.py` 로 위 플러그인 Tool 을 부른다. 설계·시그니처는 `Docs/AIAnimation/DevelopmentGuide.md` §3.4 · §5 · §6 · §7 · §9 · §14 Phase 3.

- Tool 9개: `list_motion_providers`(Provider 6 + 파이프 `retarget` · `package` · `anim_bp` · `review`) · `get/set_generation_policy` · `plan_motion_generation`(실행 안 함 — 읽기 전용 에디터 호출로 소스·메시·미리보기를 계획에 고정) · `estimate_generation_cost` · `approve_generation`(계획 × 유료 Provider 하나, 횟수 · 금액 상한) · `generate_motion` · `get_generation_status`(비동기 단계 poll) · `cancel_generation`.
- 흐름: Claude Code 가 자연어를 구조화된 요청(§9)으로 바꾼다 → `plan_motion_generation` → 사용자에게 계획을 보여 준다 → (유료면 `estimate_generation_cost` → 사용자 동의 → `approve_generation`) → `generate_motion {save}` → 결과의 `limitations[]` 를 사용자에게 알린다.
- 실제 Provider: `existing_motion`(검색·참조) · `direct_key`(`apply_animation_edits`) · `retarget` 파이프(IK Rig ×2 · RTG `match_existing` · `retarget_animations`) · `blender`(Phase 4 — 요청 `motion_file`(BVH, ini `ImportSourceRoots` 아래)을 headless Blender 서브프로세스로 FBX 로 바꿔 retarget 파이프로. 실행 파일은 정책 `paths.blender_executable`, 스크립트 `anim_gen/blender/bvh_to_fbx.py`, `generate_motion` 은 `RUNNING` 을 돌려주고 `get_generation_status` 가 poll) · `local_ai`(Phase 5 — NVIDIA Kimodo, 전용 venv 서브프로세스 → BVH → `blender` → retarget, 정책 `paths.kimodo_*`) · `external.meshy`(Phase 6 — Meshy Text-to-Motion, **유료**: 정책 `billing.paid_api_enabled` + `external.meshy.usd_per_credit`(사용자 요금제의 크레딧당 USD) + `approve_generation` 이 있어야 호출한다. 키는 환경 변수 `MESHY_API_KEY` 만, 요청은 헤더 없이 `<state>/external/meshy_requests.jsonl` 에 기록). `control_rig` 은 매니페스트(`anim_gen/providers.json`)와 비활성 자리만.
- 생성 품질(Phase 8-1 — 지침서 §14 Phase 8): 요청 플래그 `constraints.two_hand_weapon_grip` · `foot_contact` 를 `local_ai` 가 **2차 생성 제약**으로 바꾼다(같은 seed 로 1차 → `anim_gen/local_ai/refine.py` 가 1차 결과로 양손 파지 목표(축 = 1차 두 손목 방향 · 간격, `meet` = 두 손목을 팔이 닿는 곳으로) · 1차 접지 발 · 1차 루트를 계산 → 2차, Kimodo 일반 end-effector · root2d. 손 회전은 1차 손목 굽힘 유지(keep), 2차 출력은 시간 스무딩 σ 1프레임 — 값은 계획 `refine.smooth_sigma_frames`). `generation.candidates`(1 ~ 6 — seed, seed+1, …)는 한 Kimodo 실행으로 만들고, 플래그를 바꿨거나 후보가 둘 이상이면 사슬에 **select 단계**(retarget 파이프 — 후보 전부 같은 RTG 로 `<work>/Candidates/Cand_*` 리타깃 → `validate_animation profile_positions · body_clearance` → `anim_gen/motion_metrics.py` 지표(양손 간격 · 발 좌우 비 · 휘두름 정점 · 궤적 폭 · 관통 · 깨짐 · 팔 꼬임 · 손-머리 근접, 기록만: 손 들기 · 떨림 · 비파지 관통) → `anim_gen/selection.py` 점수로 하나 → 최종 리타깃은 그 후보만)가 낀다. Job `selection` 에 후보별 수치 · 벌점 · 순위 · 근거(같은 기록으로 다시 계산하면 같은 선택), 한계 `SELECTED_BY_NUMBERS`(수치 선별 — 시각 판정은 사람). 파지 플래그면 `retarget.body_clearance` 기본이 `measure`(위팔 보정이 양손을 벌리지 않게, 모든 Provider). 자루 무기 간격은 `generation.refine.grip.target_spacing_cm`(대상 메시 기준 — Vesper 낫 ≈ 60) 또는 `spacing_cm`(생성 골격 기준)으로 하나만 준다: 계획이 두 골격의 기준 포즈 어깨 관절 폭 · 팔 길이로 간격 사상(`motion_metrics.gap_map` — 대상 = 대상 어깨 폭 + 팔 길이 비 × (생성 − 생성 어깨 폭))을 한 번 풀어 generate 규칙(생성 간격 · 소스 띠)과 select(대상 띠 = 대상 간격 ± 13 cm × 팔 길이 비)가 같은 값을 쓴다(한계 `GRIP_SPACING_MAPPED`, 계획에 에디터 필요).
- 포장 · AnimBP 연결(Phase 7 — 지침서 §12): 요청 `package{additive?, montage?, blendspace?}` 는 검증 뒤 `package_*` 단계(출력은 `output_path`, 모든 쓰기에 `generation_guard`), `integrate_anim_bp: true` + `anim_bp{asset_path, operations[], scenario?, smoke}` 일 때만 `anim_bp_test`(복제본 `<work>/<ABP>_Test_<job>` 에 적용 · 컴파일 · 스모크 · `run_anim_scenario` — 비동기라 `RUNNING` 후 poll) · `anim_bp_prepare`(운영 AnimBP 는 revision · `preview_graph_operations` 읽기만). 자리표시 `$asset` · `$montage` · `$blendspace`. Job 결과 `package` · `anim_bp{test, operational, apply_payload}` · `promotion{assets[{source, dest}]}`(이름 규칙 제안 — 이동은 `promote_animation`). **운영 AnimBP 적용은 anim_gen 이 하지 않는다** — 사용자 승인 뒤 승격 → 바인딩을 정식 경로로 → `apply_graph_operations(expected_revision)`. 실패는 `INTEGRATION_FAILED`(폴백 없음, 만든 시퀀스는 남긴다).
- 대상 메시 캡처(Phase 8-2 — 지침서 §14 Phase 8 '8-2'): 요청 `review.capture`(true 또는 `{times? | count?, views?, mesh?, sequence?, compare?}`)면 검증 뒤(포장 앞) 파이프 `review` 의 capture 단계가 플러그인 `capture_animation` 으로 최종 시퀀스를 **대상 메시**(Vesper)에 입혀 찍는다 — 모든 경로(생성 · 재사용 · 편집), 애셋 0. 카메라 · 셀 규칙은 Blender 소스 골격 렌더(`review.render`)와 같고, render 가 있으면 그 시각을 행으로 쓰고 같은 시각의 소스 골격 프레임을 비교 칸으로 붙인다(`compare.png`). 연속 프레임은 `anim_gen/apng.py` 가 APNG 한 장(`animation.png`)으로 잇는다(표준 라이브러리 — 설치 없음). 출력은 ini `CaptureOutputRoots`(`Tools/mcp/results/capture/<job_id>/A<시도>/` — Saved 밖이라 채팅에 SendUserFile 로 보일 수 있다), Job `review.capture{sheet, compare_sheet, animation, frames, camera, …}`. 캡처 실패는 한계 `REVIEW_NOT_CAPTURED`(생성 성공 유지), 항상 한계 `REVIEW_CAPTURE_PREVIEW_ONLY`(무기 · 물리 · AnimBP 레이어 없음 — 판정은 사람).
- 자동 보정(Phase 8-3 — 지침서 §14 Phase 8 '8-3'): 요청 `fix.timing`(true 또는 `{target_peak_cm_s, max_rate, recovery_rate, swing{…}, still{…}}`)이면 리타깃 뒤(재사용이면 그 애셋) **대상 시퀀스**에서 `direct_key` 의 timing 단계가 손목 속도로 휘두름 구간을 찾아 `apply_animation_edits` `trim`(정지 머리 0.2초 · 꼬리 0.3초만 남김) 하나와 `time_warp` 하나(배율 곡선 — 핵심 ×r = 목표 정점 1,200 ÷ 정점 · 상한 2.0, 앞뒤는 출력 시각에 선형인 램프 · 복귀 ×1.5, 속도 단차 없음, `antialias` 1.0 — 8-3 후속)로 새 애셋을 만든다 — 순수 `anim_gen/timing.py`, 대상 스켈레톤의 기존 애셋이면 계획이 op · 결과 길이까지 미리 보인다. Job `timing{windows, ops, warp, before, after}`, 한계 `TIMING_CHANGED_LENGTH`. 요청 `fix.ops` 는 Blender 변환 단계(리타깃 전 소스 골격)의 보정 op 사전(`anim_gen/fix_ops.py` — smooth · stance_width · foot_lock, 실행 `anim_gen/blender/fix_legs.py` · 순수 `anim_gen/foot_fix.py`): 발 간격 · 발 고정은 **리타깃된 다리의 모델**(골반 = 소스 × 대상/소스 골반 높이 · 회전 변화, 다리 뼈 = 소스 방향 · 대상 길이 — 리타기터 Pelvis Motion · FK 와 같은 계산) 안에서 한 번에 풀어 대상 발이 고정된다(Job `fix.source` = Blender 보고 · `fix.target` = 리타깃 뒤 실측). `stance_width` 의 `keep_knee_bend`(기본 참 — 8-3 후속)는 좁힌 만큼 골반을 올려 엉덩 → 발목 거리를 원래대로 둔다(무릎이 더 굽지 않게, 상체는 골반과 함께 오른다). 저장된 Kimodo BVH(SOMA77)를 `motion_file` 로 주면 local_ai 와 같은 리타깃 기본값이 채워져 다시 생성하지 않고 보정만 다시 할 수 있다.
- 정책: `anim_gen/policy.default.json`(추적) ← `Saved/AnimGen/policy.json`(로컬). 출력 경로는 정책에 없고 ini `GenerationOutputPaths` 만 기준. API 키는 환경 변수만(값은 어디에도 기록하지 않는다).
- 상태: `Saved/AnimGen/{plans, jobs, approvals}/` · `ledger.jsonl`(유료 제출 예약·확정, 멱등 키 `(plan_id, attempt)`). `ANIM_GEN_STATE_DIR` 로 바꾼다. 중간 애셋은 `<output_path>/Work/<job_id>/A<시도>/`.
- 새 서버는 Claude Code 세션을 다시 시작해야 목록에 보인다.

테스트 — Mock 단계(에디터 없음, §15 D · E 포함)와 에디터 통합:

```
Tools/mcp/.venv/Scripts/python.exe -m pip install -r Tools/mcp/requirements-dev.txt
Tools/mcp/.venv/Scripts/python.exe -m pytest Tools/mcp/anim_gen/tests -q
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase3_test.py [--only plan,generate]
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase4_test.py [--bvh <path>|synthetic] [--only plan,generate]
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase5_test.py [--only plan,generate]
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase6_test.py [--only hashes,state,blocked,dirty]
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase7_test.py [--only hashes,plan,chain_bs,...]
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase8_1_test.py [--only hashes,plan,recompute,refine,lead,select,scythe,dirty]
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase8_2_test.py [--only hashes,automation,tool,guard,existing,chain,dirty]
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase8_3_test.py [--only hashes,automation,plan,baseline,timing,legs,smooth,combined,capture,dirty]
PYTHONIOENCODING=utf-8 MSYS_NO_PATHCONV=1 Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen_phase8_4_test.py [--only hashes,automation,model,e0,plan,clearance,targets,existing,dirty]
```

`anim_gen_phase8_4_test.py`(8-4a — 대상 쪽 보정 기반)는 뜬 에디터로 비교 대상 16개(8-1 · 8-3 결과 · 운영 Vesper)에 섹션 hashes · baseline(**코드 바꾸기 전 빌드에서 한 번** — 기본 `body_clearance` 를 state 에 찍는다, 기본 `--only` 에서 빠져 있다) · automation(`AnimGraphMcp.Generation.{BodyClearance, Edit, Capture, Geometry}`) · model(기본 결과 = baseline · `parts all` 소견 자리 · head_near 방향 · Python `body_model` 재현 = C++ · `bone_deltas` · `profile_rotations`) · e0(낫 부착값 · 자루 선 · 운영 낫 왼손 파지 선분 제안 · '전' 수치 · 사건 · 낫 붙인 '전' 캡처 · 풀이 시간 예측) · dirty 를 돌린다. 낫 부착값(DA)은 에디터 시작 스크립트 `Tools/mcp/e0_weapon_attach.py`(`-ExecutePythonScript` — 읽기 전용, keep-alive)가 `Tools/mcp/results/p84_weapon_attach.json` 으로 쓴 것을 읽는다. 애셋 `/Game/Animation/Test/AIAnimation/P84Run<시각>/`(bone_deltas 시험), 캡처 `Tools/mcp/results/capture/P84Run<시각>/<이름>/before/`. 요약 `anim_gen_phase8_4_state.json`(섹션 단위로 갱신). 8-4b(한 풀이 `fix.body`)는 섹션 plan(기존 애셋 + 표준 지시 T1 이 목표를 풀어 보임 · 생성 경로 local_ai · blender 의 retarget(measure) → timing → body_fit 순서 · 오류 4종 — 아무것도 안 만든다) · clearance(비교 대상 8개를 기존 애셋 경로 Job 으로 — 기준 1 ~ 5 · 스트레스 7 · 사용자 Persona 자리 전후 · 전후 캡처(낫 부착 · 후 \| 전 시트 · APNG)) · targets(T1 ~ T4 — 목표 오차 · `SEAM_JUMP` · 목표 없는 같은 대상 Job 과의 구간 ± ease 밖 차 · T3 발 · T4 막힘, `clearance` 뒤에) · existing(운영 Vesper 4개 — 새 애셋)를 더했다. Job 하나 20 ~ 200초(풀이 — 순수 Python). 인계 노트에 미리 적은 기준 위험은 `[known]` 으로 찍고 state `known_misses` 에 남긴다(실패 수 밖 — 보고에 따로). 캡처는 `<이름>/{before, after}/`(after 에 `compare.png`).

`anim_gen_phase8_3_test.py` 는 뜬 에디터 + 실제 Blender 로 시험 대상 4개(8-1 검 · 낫 선택 2개 · 칼 시험)에 섹션 hashes · automation(`AnimGraphMcp.Generation.Capture` — 비교 칸 루트) · plan(애셋 · 더티 · Blender 0) · baseline(그 애셋을 만든 Job 의 Kimodo BVH 를 fix 없이 다시 = 기존 애셋 ≤ 0.1 cm) · timing(기존 애셋 + `fix.timing`) · legs(BVH + stance_width · foot_lock — Vesper 발 좌우 비 · 접지 미끄러짐 · 무릎 굽힘 · 골반 상승 · 골반 기준 상체 불변 · 모델 예측 = 실측) · smooth · combined(BVH + 다리 + timing + capture 한 Job) · quality(8-3 후속 — 원본 · 다리 · 시간 · 합본의 떨림 · 무릎 · 관통 · 손목 · 손-머리 · 꼬임) · capture(전 · 후 캡처 — 후 행 = warp(전 행), 비교 칸 = 전 프레임, APNG 둘) · dirty 를 돌린다. 애셋 `/Game/Animation/Test/AIAnimation/P83Run<시각>/`, 캡처 `Tools/mcp/results/capture/P83Run<시각>/<대상>/{before, after}/`. 요약 `anim_gen_phase8_3_state.json`.

`anim_gen_phase8_2_test.py` 는 뜬 에디터로 섹션 hashes(시험 대상 · 스켈레톤 · 메시 SHA-256 · Tool 41 · `capture_output_roots`) · automation(`AnimGraphMcp.Generation.Capture`) · tool(칼 시험 애셋 직접 캡처 두 번 — 같은 픽셀 · 잘림 없음 · 행마다 포즈 다름 · APNG) · guard(루트 밖 · 루트 자체 · 비지 않은 폴더 · 루트 밖 비교 이미지 · 잘못된 정면 → 거부, 파일 · 더티 0) · existing(8-1 검 · 낫 선택 · 칼 시험을 원래 Job 의 Blender 소스 골격 프레임과 비교 시트로 — 프레임 경로는 이름 규칙으로만 만든다) · chain(CMU 01_01 0 ~ 3초 BVH → blender render → 리타깃 → capture Job) · dirty 를 돌린다. 이미지는 `Tools/mcp/results/capture/P82Run<시각>/` · `<job_id>/`, 생성 애셋은 chain 의 `/Game/Animation/Test/AIAnimation/P82Run<시각>/` 뿐. 요약 `anim_gen_phase8_2_state.json`.

`anim_gen_phase8_1_test.py` 는 뜬 에디터 + 실제 Kimodo · Blender 로 섹션 hashes · exp1(E1 — 기준 Kimodo 칼 시험과 같은 seed 를 `measure` 로 만들어 유지 애셋(`resolve`)과 손목 간격 · 위팔 · 관통 비교) · plan(Kimodo 안 띄움) · refine(E2 ① meet 1후보) · lead(E2') · select(E2 ② 4후보 — 후보마다 떨림 · 보조 손목 굽힘 · 궤적 폭 · 접지 발 미끄러짐도 출력) · recompute(애셋 0 — 수정 전 기록 Job `job_20261026_154723_c49a83` 의 후보를 지금 측정 · 점수로 다시 고름) · regrip(애셋 0 — 낫 기록 Job `job_20261026_192555_f991aa` 후보를 새 파지 띠로 다시 잼) · scythe(Vesper 낫 기준 — 같은 seed 4개 · 대상 기준 간격 60 cm(생성 ≈ 75) · 운영 낫 애니 4개와 같은 측정으로 비교, 꼬임 · 머리 · 관통 상한) · e3(프롬프트만 바꿈) · dirty 를 돌린다. Kimodo 1건 ≈ RAM 15 GB — 섹션을 순서대로 한 건씩. 출력 `/Game/Animation/Test/AIAnimation/P81Run<시각>/`, 기준 유지 애셋 `KimodoSword1025_185815/AS_Vesper_Sword_KimodoSlash` 는 SHA-256 불변 확인. 요약 `anim_gen_phase8_1_state.json`(섹션 단위로 갱신 — 앞 실행의 다른 섹션은 남는다).

`anim_gen_phase7_test.py` 는 섹션 hashes · plan · chain_bs(예시 B — 리타임 → BS1D → `ABP_McpRuntimeTest` 복제본 Run 상태 · Speed 전이) · chain_montage(예시 C — 반동 concat → additive · UpperBody 루프 몽타주 → `ABP_Hero_Combat` 복제본 + 운영 미리보기) · independent(유지한 Kimodo 칼 애셋 재사용 → DefaultSlot 몽타주) · guard · apply_mech · promote · dirty. 출력 `/Game/Animation/Test/AIAnimation/P7Run<시각>/`, **승격 실제 이동은 `/Game/Animation/Hero/Vesper/_P7PromoteTest/P7Run<시각>/` 에만**(추적 안 되는 새 폴더 — 끝나면 정리 목록을 보고 휴지통으로). 운영 AnimBP 4개 · 스켈레톤은 읽기 · 미리보기만, 전후 SHA-256 비교. 요약 `anim_gen_phase7_state.json`.

`anim_gen_phase6_test.py` 의 기본 섹션은 외부 호출이 없다(`blocked` — 승인 없음 · `FREE_ONLY` · 유료 끔 · 환율 없음이면 요청 로그 0줄). 유료 1건(`real`)은 `--real --usd-per-credit <값>` 을 주고, 키를 그 셸에만 설정한 터미널에서 실행하면 계획 · 견적(보낼 본문 · 크레딧 · USD)을 보여 주고 plan_id 를 직접 입력해야 승인한다.

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
