# AI 애니메이션 생성 자동화 — 개발 지침서

작성일: 2026-10-23 (원본: "AI Animation Generation Automation — Claude Code 최종 개발 지침서")  
개정 1: 2026-10-23 — 기존 AnimGraphMcp 코드 · UE 5.7.4 엔진 소스 · 외부 서비스 문서와 대조한 검토 반영.  
개정 2: 2026-10-23 — Phase 0 감사(에디터 읽기 전용 실측) 결과 반영. 히어로 스켈레톤 경로 정정, 일괄 리타깃·Interchange 위험 설정, 수치 검증을 상대 비교로 전환.  
개정 3: 2026-10-23 — 문서 검토 18건 반영. 생성 흐름의 원본 제자리 수정 분기 제거, 임포트의 스켈레톤 부작용 차단, 전역 더티 검사, 명시적 재사용, 설정 단일 기준.  
개정 4: 2026-10-23 — Phase 1 구현·실측 결과 반영(§14 Phase 1 결과, 부록 B). 상한 50, 물려받은 회전 튐, `match_existing` = 에디터 자동 리타깃 레시피.  
개정 5: 2026-10-23 — Phase 2 착수 전 엔진 소스 대조. 키 작성 순서·프레임레이트 제약, 복제 경로, 미러, 레지스트리 태그, Phase 2 Tool 시그니처·op 의미·원자성 정의. 같은 날 Phase 2 결과(§14 Phase 2 결과 · 부록 B) 반영.  
개정 6: 2026-10-23 — Phase 3 착수 전 확정안. 요청 스키마(§9) 필드·메시 명시, 모드별 라우터 순서표(§5), 승인·장부·멱등 규칙(§6), 폴백 분류·중단 코드(§7), Job 실행 모델(§3.4), `limitations[]` 모양(§3.2), Provider 매니페스트(§4), Phase 3 Tool 시그니처(§14).  
개정 7: 2026-10-24 — Phase 4(Blender Provider) 착수 전 엔진·Blender 소스 대조와 실측. 메시 없는 FBX는 스켈레톤을 못 만든다(더미 스킨 메시), BVH 기준 포즈 바닥 맞춤, 정면 방향 맞춤(FK 전역 델타), `motion_file` 요청 필드, 서브프로세스 타임아웃 정책 키, Vesper 정면 정정(+Y).  
개정 7 보강: 2026-10-24 — 리타깃 파이프(existing_motion · 생성 임포트)의 정면 맞춤. 소스 12개 스켈레톤 정면 실측(SB만 +X), 리타깃 포즈는 소스 현재 포즈에 걸리지 않음(소스 쪽 회전으로는 불가) → 대상 루트 반대 회전 + Additive Pose op(`create_ik_retargeter facing_yaw_deg`), 요청 `retarget.source_facing`, 계획 위험 `FACING_DIFFERS` · 한계 `FACING_ALIGNED`, `validate_animation profile_positions`.  
개정 7 보강 2: 2026-10-24 — `import_animation_file` 리샘플 경계 스냅. `bSnapToClosestFrameBoundary` 를 항상 켜서 경계에 안 맞는 길이도 임포트하고, 맞춘 트랙은 `warning LENGTH_SNAPPED` 로 알린다(§2.3 · 부록 B). 생성 잡은 단계 안 에디터 Tool 진단을 `tool` · `step` 과 함께 Job `diagnostics` 에 남긴다(§3.4).  
상태: Phase 1 · 2 · 3 · 4 구현·검증 완료(§14). 다음 = Phase 6(Meshy) 또는 Phase 5 조사 — 사용자 승인 후.  
관련 문서: [AnimGraphMcp README](../../Plugins/AnimGraphMcp/README.md) · [Phase 0 감사](ArchitectureAudit.md)

| 항목 | 내용 |
| :--- | :--- |
| 환경 | Windows 11 · UE 5.7.4 소스 빌드 · C++ · Python 3.13 · Claude Code · MCP |
| 구조 | Multi-Provider + 규칙 기반 라우터 + 폴백 + 공통 리타깃 처리 + 기존 AnimBP MCP 연결 |
| 기본 정책 | Free-First · 유료 API는 명시 승인 · 비파괴 · Editor 전용 |

---

## 개정 7 변경 요약 (Phase 4 — Blender Provider)

| 항목 | 개정 6 | 개정 7 (소스 대조 · 실측) | 위치 |
| :--- | :--- | :--- | :--- |
| 아마추어만 있는 FBX | 미확인 | Interchange는 스킨 메시가 없으면 새 스켈레톤을 만들지 않고 애니도 건너뛴다 → Blender가 본마다 가중치 1.0 기둥 메시(더미 스킨)를 붙인다 | §2.3 · §14 |
| BVH 단위·축 | 부록 B 미확인 | 단위 정보 없음 → `motion_file.unit`(auto = 기준 포즈 키가 사람 키가 되는 표준 단위, 없으면 170cm 정규화 + `SCALE_NORMALIZED`). 축 BVH(Y-up) → Blender → FBX → Interchange = UE `(x, z_bvh, y_bvh)`. 장면 1 BU = 1 cm로 노드 스케일 1 | §2.3 · §10 |
| BVH 기준 포즈 높이 | — | 루트 OFFSET 0이면 골반이 바닥 높이 → 리타기터 Pelvis Motion op가 높이를 1로 두고 이동을 키운다 → 기준 포즈를 바닥에 맞추고 루트 위치 키에서 같은 만큼 뺀다 | §2.3 · §10 |
| 정면 방향 | 언급 없음 | FK 체인 op는 전역 회전 델타 → 소스·대상 정면이 다르면 동작이 다른 평면으로 휜다. Blender 단계에서 대상 정면으로 돌린다(`motion_file.facing`). 보강: retarget 파이프(existing_motion · 생성 임포트)는 리타기터가 맞춘다 — 대상 루트 반대 회전 + Additive Pose op(`facing_yaw_deg`), 요청 `retarget.source_facing` | §2.3 · §9 · §10 · 부록 B |
| 요청 | 파일 입력 없음 | `motion_file{path, unit, facing, range, axis_forward, axis_up}` — 있으면 라우터가 `blender`를 맨 앞에 둔다 | §5 · §9 |
| 정책 | — | `execution.subprocess_timeout_seconds`(기본 300, 10~3600) | §6 |
| Job | 취소 = 결과 무시 | 로컬 서브프로세스는 실제로 종료(`cancel_effect`). 외부 API는 그대로 결과 무시 | §3.4 |
| Vesper 정면 | 부록 B "Vesper −Y 쪽" | **+Y** — 기준 포즈 `ball_l` y 8.3 > `foot_l` y −3.5(발목 → 볼 = +Y), UE 마네킹과 같은 축 | 부록 B |
| 임포트 리샘플 | `sample_rate` 를 주면 Interchange 가 굽는다 | 길이가 그 rate 의 프레임 경계에 맞지 않으면 Interchange 가 애니를 **건너뛴다**(`bSnapToClosestFrameBoundary` 기본 false — CMU 01_01 22.925초 × 30 실측). blender 는 굽기 범위 끝을 경계에 맞춘다(120 → 30 은 최대 3 소스 프레임). 보강 2: `import_animation_file` 이 `bSnapToClosestFrameBoundary` 를 항상 켜서 가까운 프레임에 맞추고 `LENGTH_SNAPPED` 를 남긴다 — 다른 FBX(Meshy 등)도 임포트된다 | §2.3 · §14 · 부록 B |

---

## 개정 6 변경 요약 (Phase 3 착수 전 확정안)

| 항목 | 개정 5 | 개정 6 | 위치 |
| :--- | :--- | :--- | :--- |
| `target_mesh` | "생략 시 스켈레톤의 첫 메시" | 리타깃 단계가 생기면 **필수**(§10 "메시는 명시"와 충돌 해소). 소스 메시는 계획이 고정해 보여 준다 | §9 |
| `motion_category` | 예시 `"combat"` | enum `idle` · `locomotion` · `weapon_action` · `full_body_new` (§5 행과 1:1) | §9 · §5 |
| 요청 필드 | 원본 필드만 | + `search` · `edits` · `retarget`. `save`는 요청이 아니라 `generate_motion` 인자. `generation_policy`는 정책이 `FREE_ONLY`면 벗어날 수 없다 | §9 |
| 오류·한계 | 코드 예시 | + `COST_UNKNOWN`. `limitations[]` 항목 = `{code, message, source}`. 폴백하지 않는 가드 코드 명시 | §3.2 · §7 |
| Job | 상태 6종 · 필드 | + `plan_id` · `attempt` · `idempotency_key` · `events[]`. 에디터 Provider는 `generate_motion` 안에서 동기, 비동기 Provider는 `get_generation_status` poll 로 진행(백그라운드 스레드 없음) | §3.4 |
| 라우터 | 행 3개 · 순서 하나 | 모드별 순서표, `provider` 지정 시 폴백 끔, 같은 스켈레톤·편집 없음이면 재사용(복제 안 함) | §5 |
| 승인 | `approve_generation(plan_id, max_cost_usd, max_attempts)` | + `provider?`. 상한 검사식, 승인 → 대기 Job `QUEUED`, 실제 금액 미확정 기록, `require_explicit_approval`은 `true`만 | §6 |
| Capability | 목록 | `Tools/mcp/anim_gen/providers.json` 필드 이름 | §4 |
| Phase 3 Tool | 이름만 | 입력·결과 시그니처 | §14 |

---

## 개정 5 변경 요약 (Phase 2 착수 전 엔진 대조)

| 항목 | 개정 4 | 개정 5 (엔진 소스 확인) | 위치 |
| :--- | :--- | :--- | :--- |
| 키 직접 작성 | `SetFrameRate` · `SetNumberOfFrames` · `AddBoneCurve` · `SetBoneTrackKeys` | 길이를 바꾸면 엔진이 노티파이·싱크 마커를 옮긴다 → 비우고 다시 넣는다. 데이터가 있는 모델의 `SetFrameRate`는 배수·약수만 → 출력 fps = 주 소스. 프레임 수 = 키 수 − 1 | §2.3 |
| 원시 키 읽기 | 미기재 | `GetBoneAnimationTracks`는 5.2부터 deprecated → `GetBoneTrackTransforms`. 원시 키에는 트랜스폼 커브가 없다 | §2.3 |
| 애셋 복제 | 미기재 | `IAssetTools::DuplicateAsset`은 소스 컨트롤이 켜져 있으면 즉시 저장하고 이름 충돌 시 모달 → 공통 가드 안에서 `StaticDuplicateObject` | §2.3 |
| 미러 | 미기재 | `FAnimationRuntime::MirrorPose`는 `FCompactPose` + `FBoneContainer`가 필요 → 같은 수식을 스켈레톤 인덱스로. 짝은 프로젝트 Animation 설정 규칙 또는 MirrorDataTable | §2.3 |
| 검색 인덱스 | "루프" 포함 | `bLoop`은 레지스트리 태그가 아니다 → 루프 판정은 로드가 필요(상한) | §2.3 · §14 |
| 원자성 | "`apply_graph_operations`의 사전 검증·원자성 패턴" | 편집은 항상 새 애셋을 만든다 → 모든 op를 메모리 버퍼에서 끝까지 계산한 뒤에만 애셋을 만든다(그래프 op의 보상 롤백과 다르다) | §3.3 · §14 |
| op 사전 | 7개 | 7개 유지 + `concat.reverse` 옵션. `validate_animation`에 `expect` · `seams` · `profile_bones` | §4 · §13 · §14 |

---

## 개정 4 변경 요약 (Phase 1 실측 반영)

| 항목 | 개정 3 | 개정 4 (실측) | 위치 |
| :--- | :--- | :--- | :--- |
| 동기 Interchange 임포트를 브리지에서 | 미확인 | 정상 — 메시째 1.3초, 애니만 0.2초. 잡 패턴 불필요 | §14 · 부록 B |
| `MaxRetargetAssetsPerCall` | 20 (잠정) | **50** — 20개·1,317프레임 리타깃·검증·저장 3.0초 | §3.4 · §14 |
| 절대 수치: 한 프레임 회전 > 90° | 항상 `FAILED` | 소스가 없을 때만 `FAILED`. 소스에도 있는 튐(소스 최대 + 10° 이내)은 경고 `ROTATION_JUMP_INHERITED` — 30fps 마켓 공격이 93~109°/프레임 | §13 |
| `ops: match_existing` | "기존 RTG 의 op 7개에 맞춤" | 에디터 "Retarget Animations" 자동 생성 레시피 그대로(정확 매핑 · 타깃 포즈 자동 정렬 · Run IK Rig 끔 · 루트 모션 op · Pin Bones). 기존 RTG 가 이 경로의 산출물 — 결과 본별 차 0° | §10 · §14 |
| `retarget_animations` 결과 `seconds_per_asset[]` | 애셋별 배열 | 평균값 + `frames` · `ms_per_frame` — 엔진이 애셋을 단계별로 묶어 처리해 애셋 하나만의 시간은 잴 수 없다 | 감사 §10 |

---

## 개정 3 변경 요약 (문서 검토 반영)

| 항목 | 개정 2 | 개정 3 | 위치 |
| :--- | :--- | :--- | :--- |
| 같은 리그일 때 | `same_rig`면 `reassign_skeleton`으로 끝 | 생성 흐름은 항상 복제(`retarget_animations`). `same_rig`는 참고 정보. `reassign_skeleton`은 제자리 이동이라 원래 용도에만 | §10 |
| 임포트 부작용 | 미기재 | `bAddCurveMetadataToSkeleton=false` 고정(기본 `true`면 기존 스켈레톤이 더티). 메시째 임포트 시 재질·텍스처·피직스·스태틱 메시 끔 | §2.3 · §10 |
| 원본 보호 검사 | 소스 패키지 더티 확인 | 호출 전후 **전역 더티 집합 차이** — 허용 목록 밖이 새로 더티면 저장 안 하고 `UNEXPECTED_DIRTY` | §3.1-7 |
| 기존 IK Rig·RTG 재사용 | `reuse_existing=true` (암묵) | `existing_rig` / `existing_retargeter`를 줄 때만. 소스·대상 메시 필수 | §10 · 감사 §10 |
| 출력 경로 설정 | ini + `policy.json` 두 곳 | ini 하나. `get_editor_status`가 내보내고 `policy.json`에서 `candidate_root`·`allow_asset_overwrite` 삭제 | §3.1-6 · §6 |
| 문서 정합 | — | `ok` 조건 · 예시 경고 코드 · 의존 목록 · `inspect_skeleton` 필드 · 검증 범위 · `reassign_skeleton` 설명 · Phase 1 완료 기준 1·2·4 · 스모크 경로 | 해당 절 |

---

## 개정 2 변경 요약 (Phase 0 감사 반영)

| 항목 | 개정 1 | 개정 2 | 근거 (감사 문서) |
| :--- | :--- | :--- | :--- |
| 히어로 스켈레톤 | `/Game/IdaFaber/Meshes/Girl/SKEL_UE5_F` | `/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F` (애니 71개 · `ABP_Hero_Combat` 대상). 옛 경로는 애니 0개인 사본 | 요약 |
| 자동 매핑 실패 | "부분 실패면 수동" | 비표준 스켈레톤은 **전부 실패**(엔진이 템플릿 일치 때만 동작) → 수동 체인이 정상 경로 | §2 |
| 재할당 vs 리타깃 판정 | 미기재 | 본 이름 겹침이 아니라 **기준 포즈 차**로 판정. UE4 마네킹은 이름이 전부 겹쳐도 포즈가 10~40° 다르다 | §8 |
| 일괄 리타깃 | 출력 폴더만 지정 | + `bOverwriteExistingFiles` 금지(다른 애셋 참조 교체 + 강제 삭제), AnimBlueprint 입력 거부 | §3 |
| Interchange | 설정 키 미확인 | `bImportOnlyAnimations` + `Skeleton`, **`bReplaceExisting=false`**, 기본 파이프라인은 임시 복제, 임포트 파일은 허용 루트 아래만 | §1 |
| 수치 검증 | 절대 임계값 | **소스 대비 상대 비교** + 명백한 깨짐(NaN · 90°/프레임 초과)만 절대값 | §5 |
| 골든 비교 | 품질 기준 | 회귀 기준. 기존 RTG가 기본 자동 구성(수동 조정 흔적 없음) | §4 |
| 포즈 샘플링 API | `GetAnimPoseAtTimeIntervals` | C++ 전용(UFUNCTION 아님). 검증은 C++에서 — Python은 본 읽기만 샘플링의 5배 | §5.1 |
| Phase 1 Tool | 이름만 | 입력·결과 시그니처 확정 + 설정 키 4개 | §10 |

---

## 개정 1 변경 요약 (원본 대비)

| 항목 | 원본 | 개정 1 | 근거 |
| :--- | :--- | :--- | :--- |
| 결과 형식 | `{success, job_id, provider, ...}` 독자 형식 | 기존 봉투 `{ok, tool, request_id, result, error, diagnostics}` 유지, 생성 관련 필드는 `result` 안 | 클라이언트 분기를 하나로 유지 (§3.2) |
| 로직 위치 | "기존 MCP 비동기 모델에 맞춘다"(미지정) | C++ = UObject 조작·수치 검증만(기존 플러그인에 Tool 추가). 정책·라우터·Job·외부 호출 = 새 Python 패키지 `anim_gen`(별도 MCP 서버). 기존 `server.py`는 얇은 프록시 유지 | 브리지는 게임 스레드 동기, `server.py`는 로직 없는 설계 (§2.1) |
| 자연어 해석 | Orchestrator 계층의 Request Analysis | **Claude Code(에이전트) 자신**이 한다. 서버는 구조화된 요청만 받는다. `create_animation_from_prompt` 폐기 | 서버 안에 LLM 호출을 두지 않는다 |
| Phase 순서 | 기반 → 절차 생성 → 라우터 → 로컬 AI → 외부 → AnimBP → 품질 | 리타깃 기반 → 기존 모션 재사용·변형 → 라우터·정책 → Blender → 로컬 AI → 외부 → AnimBP·승격 → 품질 | 라우터는 고를 Provider가 2개 이상 생긴 뒤에야 의미가 있다 |
| 절차 생성 수단 | Control Rig 우선 | `IAnimationDataController` 직접 키 작성 우선. Control Rig 베이크는 손·발 제약 보정에만 (Phase 8) | Control Rig 베이크는 World + LevelSequence + 바인딩이 필요 (§2.3) |
| 전신 신규 생성 | Phase 2 절차 생성의 목표 | Phase 2 범위 밖. Phase 2 = 기존 모션 변형 + 부분 신체 편집 | 원본도 "복잡한 전신 공격은 Phase 2 필수 조건 아님" |
| 중복 Tool | montage·blendspace·기존 모션 목록 신규 | 기존 `create_anim_montage` · `create_blendspace` · `list_animation_assets` 재사용 | §3.3 |
| Job 시스템 | 신규 | 에디터 작업은 기존 Automation 잡 패턴(`job_id` + poll) 재사용, Provider 작업은 `anim_gen` | §3.4 |
| 일괄 리타깃 출력 경로 | 미지정 | Python 정적 함수 대신 C++에서 배치 컨텍스트로 출력 폴더 지정 | 정적 `DuplicateAndRetarget`에는 폴더 인자가 없어 `/Game` 루트에 쓴다 (§2.3) |
| BVH | "변환 또는 Import 경로" | 엔진 임포터 없음 → Blender 경유만 (Phase 4) | §2.3 |
| 외부 Provider | Meshy · SayMotion | Meshy 먼저, SayMotion 보류 | SayMotion API는 검증 파트너 한정 (§2.4) |
| 출력 경로·이름 | `/Game/GeneratedAnimations`, `AN_` 접두 | 후보 영역 `/Game/Animation/Generated/<영웅>/`, 이름은 프로젝트 규칙 `AS_<영웅>_<계열>_<동작>`. 정식 경로 이동은 사용자 확인 후 (Phase 7) | 애셋 명명 규칙 (2026-10-22) |
| 쓰기 경로 통제 | "원본을 덮어쓰지 않는다" | 새 Tool은 **허용 목록**(`GenerationOutputPaths`) 밖에 쓰지 않는다 | 기존 보호 목록은 파괴 연산만 막는다 (§3.1) |
| 예시 C (사격 + Strafe) | 생성 대상 | `ABP_Hero_Combat`에 이미 구현(조준 strafe · AimOffset · 레이어 블렌드). 생성 대상은 상체 사격 루프·반동 같은 개별 시퀀스뿐 | §1.1 |

---

## 1. 목적

자연어 지시로 현재 UE 캐릭터의 스켈레톤에 연결 가능한 애니메이션 애셋을 만들고, 저장하고, 검증하는 범용 파이프라인을 만든다. 원본의 핵심 목표 8개를 유지한다.

1. 특정 캐릭터·스켈레톤에 종속되지 않는다.
2. 특정 무기·애니메이션 종류에 종속되지 않는다.
3. 외부 유료 AI 없이 동작하는 기본 경로가 있다.
4. 필요할 때 외부 AI를 Provider로 추가할 수 있다.
5. 비용·성능·품질을 따져 경로를 고른다.
6. 실패하면 허용된 다른 경로로 넘어간다.
7. 기존 AnimBP MCP와 연결된다.
8. 실제 UE 애셋을 생성·저장·검증한다.

> 파이프라인을 구현할 수 있다는 것과 모든 자연어 요청을 높은 품질로 생성할 수 있다는 것은 별개다. 지원하지 않는 동작과 품질 한계는 결과의 `limitations[]`에 명시한다.

### 1.1 원본 예시의 현실적인 경로

| 예시 | 현실적인 경로 | Phase |
| :--- | :--- | :---: |
| A. 낫 양손 회전 3연 베기, 3초 | 기존 모션(Vesper Sickle 액션 · `/Game/Assets` 근접 팩) 검색 → 리타깃 → 리타임·연결. 맞는 모션이 없으면 외부 AI 초안(승인 시) + 보정 | 1 · 2 · 6 |
| B. 낫 Idle·Walk·Run·Jump·Dodge | 기존 로코모션 리타깃 + 무기 상체 오버레이(기존 ABP 구조) | 1 · 2 · 7 |
| C. 사격 중 상체 고정 + 8방향 strafe | 이미 `ABP_Hero_Combat`에 있음. 새로 만들 것은 상체 사격 루프·반동 시퀀스 | 2 · 7 |
| D. 첫 타격 빠르게, 마지막 타격 180° 회전 | 리타임(구간별 재생 속도) + 루트 Yaw 편집 | 2 |

---

## 2. 확인된 전제 (2026-10-23)

이 절의 내용은 코드·엔진 소스·공식 문서로 확인한 것이다. 확인하지 못한 것은 부록 B에 따로 둔다.

### 2.1 기존 AnimGraphMcp

```text
Claude Code ─ stdio MCP ─▶ Tools/mcp/anim_graph_mcp/server.py (얇은 프록시)
            ─ HTTP 127.0.0.1:18765 + 기동별 토큰 ─▶ Plugins/AnimGraphMcp (AnimGraphMcpEditor, 게임 스레드)
```

- **응답 봉투:** `{ok, tool, request_id, result, error, diagnostics}`. 같은 `(tool, request_id)` 재전송은 캐시된 응답을 돌려준다(256개).
- **실행 모델:** 동기 실행이다(클라이언트 타임아웃 60초, 컴파일 포함 180초). 비동기는 `run_automation_tests` / `run_anim_scenario`의 `job_id` + `poll_automation_tests`뿐이다.
- **보호:** `ProtectedAssets` / `ProtectedPaths`는 **파괴 연산만** 막는다. 현재 설정은 `/Game/Animation/Hero/ABP_Hero_Base`와 `/Game/Assets/`.
- **범용성:** 플러그인은 프로젝트 코드에 의존하지 않는다.
- **애니 관련 기존 Tool:** `list_animation_assets` · `create_anim_montage` · `set_montage_slots` · `set_montage_sections` · `create_blendspace`(AimOffset 포함) · `reassign_skeleton`(애셋을 **제자리에서** 다른 스켈레톤으로 옮김. 본 이름만 검사하고 기준 포즈 차는 검사하지 않음 — 감사 §8) · `set_sequence_additive` · `add_skeleton_slot` · `run_anim_scenario` · `run_automation_tests`.
- **공백:** README가 IK Retargeter 리타깃을 "범위 밖"으로 명시한다. **이번 작업이 메울 실제 공백은 IK 리타깃과 스켈레톤 조회다.**

### 2.2 프로젝트 애셋과 환경

| 항목 | 값 |
| :--- | :--- |
| 히어로 스켈레톤 | Vesper `/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F` (172본, UE5 마네킹 본 이름, 프리뷰 `SK_StreetDemon_F_01`). `/Game/IdaFaber/...`는 기준 포즈가 같은 옛 사본(애니 0개) |
| 기존 수동 리타깃 애셋 | `/Game/Animation/Hero/Vesper/Retarget/`: `IK_AutoGenerated{Source,Target,Kat,SourceHandS,TargetHandS,TargetKat}` · `RTG_HSwordToH` · `RTG_KatanaToH` · `RTG_AutoGeneratedHandS` → **Phase 1 회귀 비교 기준**. `IK_AutoGeneratedTarget`·`RTG_HSwordToH`는 옛 사본을 가리킨다 |
| 본 이름 비호환 스켈레톤 | Narmaya `pl1400_Skeleton`(343본), SB `CH_P_EVE_01_Body`(300본). Vesper와 공유하는 본 이름이 0개 → 커스텀 스켈레톤 테스트 대상 |
| 기존 모션 소스 | `/Game/Assets/` 마켓 키트(uasset 3,169개). CombatMasterAnimBundle은 스타일마다 UE4 마네킹(68본)·UE5 Manny(161본) 스켈레톤을 따로 가지며, 모두 Vesper로 오려면 IK 리타깃이 필요하다 |
| 명명 규칙 | `/Game/Animation/Hero/<영웅>/<계열>/<용도>/` · `AS_<영웅>_<계열>_<동작>` · 몽타주 `AM_` · 타입 폴더 금지 (`.claude/plans/anim-asset-naming.md`) |
| 테스트 산출물 위치 | `/Game/Animation/Test/` |
| Blender | 4.4.1, `C:\Program Files\Blender Foundation\Blender 4.4\` (PATH에 없음 — 정책 `paths.blender_executable`). `-b --factory-startup` 기동 약 2.9초, BVH 1건 변환 0.6~2초 |
| GPU | RTX 3080 Ti 12GB |
| MCP Python | `Tools/mcp/.venv` Python 3.13.1, `mcp` 2.x |

### 2.3 UE 5.7.4 API (엔진 소스 확인)

| 용도 | API | 위치 (Engine/…) | 비고 |
| :--- | :--- | :--- | :--- |
| IK Rig 자동 생성 | `UIKRigController::SetSkeletalMesh` · `ApplyAutoGeneratedRetargetDefinition` · `ApplyAutoFBIK` · `SetRetargetRoot` · `AddRetargetChain` | `Plugins/Animation/IKRig/Source/IKRigEditor/Public/RigEditor/IKRigController.h` | BlueprintCallable. 자동 캐릭터라이즈는 **알려진 템플릿 계층(UE5 마네킹 등)과 일치할 때만** 동작하고(`bUsedTemplate` 거짓이면 아무것도 안 하고 `false`), 비표준 스켈레톤(Narmaya·SB)은 체인 0개로 전부 실패한다 → 체인 수동 정의가 정상 경로. 템플릿 이름·매칭률은 C++ 전용(`GetAutoCharacterizer`) |
| 리타기터 구성 | `UIKRetargeterController::SetIKRig` · `SetPreviewMesh` · `AddDefaultOps` · `AssignIKRigToAllOps` · `AutoMapChains` · `AutoAlignAllBones` · `CreateRetargetPose` | `…/IKRigEditor/Public/RetargetEditor/IKRetargeterController.h` | BlueprintCallable. 5.6+ op 스택 구조 |
| 일괄 리타깃 | `UIKRetargetBatchOperation::DuplicateAndRetarget` (정적) · `RunRetarget(FIKRetargetBatchOperationContext&)` | `…/RetargetEditor/IKRetargetBatchOperation.h` | **정적 함수는 출력 폴더 인자가 없다.** 컨텍스트의 `NameRule.FolderPath` 기본값이 `/Game`이라 결과가 `/Game` 루트에 생긴다(`EditorAnimUtils.h:27`). C++에서 컨텍스트를 직접 채워 `RunRetarget`을 부른다. 한 번의 동기 호출(`FScopedSlowTask`, 취소 시 삭제 확인 모달). **`bOverwriteExistingFiles=true`는 다른 애셋의 참조를 새 애셋으로 바꾸고 기존 애셋을 강제 삭제한다 — 금지.** AnimBlueprint 입력은 부모 ABP까지 복제·재컴파일하므로 거부. 소스 애셋은 바뀌지 않고, 결과는 저장되지 않은 채 더티로 남는다 |
| 키 직접 작성 | `IAnimationDataController::OpenBracket`/`CloseBracket` · `RemoveAllBoneTracks` · `SetNumberOfFrames` · `AddBoneCurve` · `SetBoneTrackKeys` · `RemoveAllCurvesOfType` · `AddCurve` · `SetCurveKeys` · `SetFrameRate` | `Source/Runtime/Engine/Classes/Animation/AnimData/IAnimationDataController.h` · 구현 `Plugins/Animation/AnimationData/Source/AnimationData/Private/AnimSequencerController.cpp` | BlueprintCallable. 엔진 일괄 리타깃과 같은 순서(`IKRetargetBatchOperation.cpp:394-513`, `bShouldTransact=false`). **프레임 수 = 키 수 − 1.** `SetNumberOfFrames`는 길이 변경 알림을 내고 시퀀스가 노티파이·싱크 마커를 옮긴다(`AnimSequenceBase.cpp:1275`) → 비운 뒤 길이를 바꾸고 직접 다시 넣는다. 데이터가 있는 모델의 `SetFrameRate`는 현재 값의 배수·약수만 받는다(`AnimSequencerController.cpp:287`) → 출력 fps는 주 소스를 따른다 |
| 원시 키 읽기 | `IAnimationDataModel::GetBoneTrackTransforms(Name, Out)` · `GetFloatCurves` · `GetTransformCurves` | `…/AnimData/IAnimationDataModel.h` | `GetBoneAnimationTracks`는 5.2부터 deprecated. 원시 본 키에는 **트랜스폼 커브(additive 레이어)가 없다** — 평가 포즈에만 더해진다 |
| 애셋 복제 | `StaticDuplicateObject` (공통 가드 안) | `Source/Runtime/CoreUObject/Public/UObject/UObjectGlobals.h` | `IAssetTools::DuplicateAsset`은 소스 컨트롤이 켜져 있으면 **즉시 저장**하고, 이름이 겹치면 **모달**을 띄운다(`AssetTools.cpp` `PerformDuplicateAsset`·`CanCreateAsset`) → 생성 Tool은 쓰지 않는다 |
| 미러 | `FAnimationRuntime::MirrorVector` · `MirrorQuat` · `UMirrorDataTable::GetSettingsMirrorName` · `FillMirrorBoneIndexes` | `Source/Runtime/Engine/Public/AnimationRuntime.h` · `…/Classes/Animation/MirrorDataTable.h` | `MirrorPose`는 `FCompactPose` + `FBoneContainer`가 필요해 같은 수식(`AnimationRuntime.cpp` `MirrorPose`)을 스켈레톤 본 인덱스로 옮긴다. 짝은 프로젝트 Animation 설정의 미러 규칙(기본 축 X) 또는 주어진 MirrorDataTable |
| 검색 인덱스 | AssetRegistry 태그 | `…/Animation/AnimSequence.h` · `AnimSequenceBase.h` · `AnimationAsset.h`의 `AssetRegistrySearchable` | 태그: `SequenceLength` · `bEnableRootMotion` · `AdditiveAnimType` · `Skeleton` · "Number of Frames" · "Source Frame Rate" · 노티파이·커브 이름. **`bLoop`은 태그가 아니다** → 루프 판정은 로드가 필요 |
| 포즈 샘플링 (검증) | `UAnimPoseExtensions::GetAnimPoseAtTime` · `GetAnimPoseAtFrame` (+ C++ 전용 `GetAnimPoseAtTimeIntervals`) | `Source/Editor/AnimationBlueprintLibrary/Public/AnimPose.h` | 에디터 전용. 172본 1프레임 0.15~0.19ms(실측). Python에서 본을 읽으면 그 5배라 검증 계산은 C++ |
| Control Rig 베이크 | `UControlRigSequencerEditorLibrary::BakeToControlRig` · `ExportAnimSequenceFromSequencer` (Python 이름 `ControlRigSequencerLibrary`) | `Plugins/Animation/ControlRig/Source/ControlRigEditor/Public/ControlRigSequencerEditorLibrary.h` | World + LevelSequence + 바인딩 필요 — 무겁다 |
| FBX 임포트 | Interchange (cvar `Interchange.FeatureFlags.Import.FBX` = `true` 실측). `UInterchangeManager::ImportAsset` + `FImportAssetParameters` · 애니만: `bImportOnlyAnimations` + `Skeleton` | `Source/Runtime/Interchange/Engine/Public/InterchangeManager.h` · `Plugins/Interchange/Runtime/Source/Pipelines/Public/InterchangeGenericAssetsPipelineSharedSettings.h` | **`bReplaceExisting` 기본값 `true` → 반드시 `false`**, `bIsAutomated=true`. **`bAddCurveMetadataToSkeleton`(기본 `true`)도 `false`** — 켜져 있으면 모프·머티리얼 커브가 기존 스켈레톤에 메타데이터를 더하고 더티로 만든다(`Skeleton.cpp:1826-1846`). 기본 파이프라인(`/Interchange/Pipelines/DefaultAssetsPipeline`)은 엔진 콘텐츠라 임시 복제본을 `OverridePipelines`로 넘긴다 |
| BVH 임포트 | **없음** | — | Blender 경유 (Phase 4) |
| 메시 없는 FBX (개정 7) | `UInterchangeGenericMeshPipeline` · `UInterchangeGenericAnimationPipeline` | `Plugins/Interchange/Runtime/Source/Pipelines/Private/InterchangeGenericSkeletalMeshPipeline.cpp:181-314` · `InterchangeGenericAnimationPipeline.cpp:642-694, 850` | 스켈레톤 팩토리 노드는 **스킨 메시마다** 만든다. 애니 파이프라인은 기존 스켈레톤을 지정했을 때만 관절에서 만들고, 아니면 애니를 건너뛴다("USkeleton cannot be created without a valid skeletal mesh") → 새 스켈레톤이 필요한 BVH 변환은 더미 스킨 메시를 붙인다 |
| FBX 축·단위 (개정 7) | `FFbxConvert::ConvertScene` | `Plugins/Interchange/Runtime/Source/Parsers/Fbx/Private/FbxConvert.cpp:84-122` | 번역기 기본 `bConvertScene` · `bConvertSceneUnit` = true → Z-up(앞 −Y) 오른손 + cm 로 바꾼 뒤 왼손으로 뒤집는다. Blender 기본 내보내기(−Z 앞 · Y 위)와 합치면 Blender `(x, y, z)` → UE `(x, −y, z)` (실측) |
| Blender 아마추어 널 (개정 7) | FBX 번역기 루트 본 찾기 | `…/Parsers/Fbx/Private/FbxScene.cpp:780-790` | 루트 본의 부모가 장면 루트 아래 이름 `armature`(대소문자 무시) 널이면 뼈에서 뺀다 → 객체 이름을 `Armature`로 두면 루트 본 = BVH 루트 |
| FK 체인 리타깃 (개정 7) | `FChainDecoderFK` | `Plugins/Animation/IKRig/Source/IKRig/Private/Retargeter/RetargetOps/FKChainsOp.cpp:343-350` | 회전 = (소스 현재 × 소스 기준⁻¹) × 대상 기준 — **전역** 델타. 소스와 대상의 정면이 다르면 같은 세계 축으로 돌아 동작이 다른 평면으로 휜다 → 소스를 대상 정면으로 맞춘다 |
| 리타깃 포즈의 범위 (개정 7 보강) | `FIKRetargetProcessor::RunRetargeter` · `FResolvedRetargetPoseSet::AddOrUpdateRetargetPose` | `…/Retargeter/IKRetargetProcessor.cpp:24-88, 1268-1316` · `…/RetargetOps/PelvisMotionOp.cpp:304-306, 325` | 리타깃 포즈는 기준(소스 기준 · 대상 기준)만 바꾸고 **소스 현재 포즈는 그대로 op 에 들어간다**. 펠비스 위치도 소스 정규화 위치 × 대상 높이(회전 없음). 그래서 소스 리타깃 포즈 루트를 돌리면 몸 기준 동작 평면은 맞아도 **결과 전체가 소스 정면을 본다**(출력 = 회전⁻¹ × 원하는 결과) — 소스 쪽 포즈 회전만으로는 맞출 수 없다 |
| 정면 맞춤 (개정 7 보강) | `FIKRetargetAdditivePoseOp` · `UIKRetargeterController::AutoAlignBones` · `FIKRetargetRootMotionOp` `GlobalOffset` | `…/RetargetOps/RetargetPoseOp.cpp:66-128` · `IKRigEditor/Private/RetargetEditor/IKRetargeterController.cpp:1346-1386` · `…/RetargetOps/RootMotionGeneratorOp.cpp:160, 281-312` | 대상 리타깃 포즈의 스켈레톤 루트(본 0, 펠비스 아님)를 −yaw → 모든 op 가 "대상이 소스 정면을 보는" 같은 좌표계에서 푼다. Additive Pose op(대상 포즈의 로컬 델타를 출력에 곱하고 자식을 따라 돌림)를 Root Motion op 앞에 두어 루트를 +yaw 로 되돌린다 — 루트가 원점이라 펠비스 이동도 돈다, 루트 트랙은 기준 포즈. Root Motion op 가 소스 루트를 복사하면 `GlobalOffset` 에 +yaw. `AutoAlignAllBones` 는 포즈를 먼저 **전부 리셋**하므로 루트를 돌린 뒤 리셋 없는 `AutoAlignBones(빈 목록 = 전부)` |
| 임포트 리샘플 (개정 7 · 보강 2) | `UInterchangeGenericAnimationPipeline::CreateAnimSequenceFactoryNode` 의 길이 검사 · `UInterchangeManager::ImportAssetWithResult` | `…/Pipelines/Private/InterchangeGenericAnimationPipeline.cpp:714-807` · `…/Pipelines/Public/InterchangeGenericAnimationPipeline.h:85` · `Source/Runtime/Interchange/Engine/Private/InterchangeManager.cpp:1720-1726` · `…/Tasks/InterchangeTaskPipeline.cpp:42` | 길이가 굽는 rate 의 프레임 경계에 맞지 않으면 애니 파이프라인 프로퍼티 `bSnapToClosestFrameBoundary`(기본 false)가 꺼져 있을 때 오류 메시지만 남기고 **애니 팩토리 노드를 건너뛴다**(커스텀 `CustomBoneAnimationSampleRate` 든 소스 rate 든 같은 검사). 켜면 시작·끝을 가까운 프레임으로 반올림하고 경고(원문 키 `Info_ImportLengthSnap`)를 남긴다. **`import_animation_file` 은 항상 켠다**(경계에 맞는 길이엔 영향 없음). 파이프라인 메시지는 임포트 결과 컨테이너로 가므로 `ImportAssetWithResult`(동기, `ImportAsset` 과 같은 경로)로 받아 그 경고를 찾아 `warning LENGTH_SNAPPED {track}` 로 낸다. 문구는 에디터 언어로 바뀌므로 `FTextInspector::GetHistoricFormatData` 로 원문 형식의 키를 비교한다. 실측: CMU 01_01 전체(2,752키 · 22.925초 = 30 fps 687.75프레임) → 689키 · 22.9333초 + `LENGTH_SNAPPED`. 대조군(blender 가 경계에 맞춘 2,749키 FBX → 30 fps 688키 · 같은 2,752키 파일을 소스 rate 120 으로)은 진단 없음. blender 는 계속 범위를 맞춰 넣는다(반 프레임 늘림·줄임 없음) |
| 골반 이동 (개정 7) | `FIKRetargetPelvisMotionOp` | `…/RetargetOps/PelvisMotionOp.cpp:183-196, 223` | 소스 골반 기준 높이가 0에 가까우면 오류 로그 후 높이 1 로 두고 이동 배율 = 대상 높이 / 1 → 기준 포즈를 바닥에 맞춘다 |
| Blender FBX 단위 (개정 7) | `io_scene_fbx` `export_fbx_bin.py` | `Blender 4.4/4.4/scripts/addons_core/io_scene_fbx/export_fbx_bin.py:3453-3463` · `fbx_utils.py:216` | 단위 계수 = 100 × `scale_length`, `FBX_SCALE_NONE`이면 그만큼 노드에 곱한다 → 장면 `scale_length` 0.01(1 BU = 1 cm)이면 노드 스케일 1 · `UnitScaleFactor` 1 |
| Blender BVH 임포터 (개정 7) | `io_anim_bvh` `import_bvh.py` | `…/addons_core/io_anim_bvh/import_bvh.py:213-224, 545-560, 577-580, 646-647, 785` | End Site는 본이 아니라 꼬리. 축 변환은 객체 회전 → 회전만 적용. 위치 키 = 기준 포즈 로컬 공간(회전 적용 시 루트 이동도 같이 돈다). `frame_start=0`을 줘도 첫 키가 1(실측) · 장면 길이는 늘리기만 한다 → 변환 스크립트가 실제 첫 키 기준으로 옮기고 범위를 직접 맞춘다. `Armature.transform` 뒤에는 데이터 태그 + `view_layer.update()`가 있어야 포즈 평가가 새 기준 포즈를 쓴다(실측) |
| IKRig 플러그인 | `EnabledByDefault: true` | `Plugins/Animation/IKRig/IKRig.uplugin` | 플러그인 의존 선언만 추가하면 된다 |

### 2.4 외부 Provider와 라이선스

| 대상 | 확인 결과 | 결정 |
| :--- | :--- | :--- |
| HY-Motion 1.0 | "Tencent HY-MOTION 1.0 Community License". Territory = 전 세계에서 **EU · UK · 한국 제외**. 월간 사용자 100만 초과 시 별도 라이선스 | 별도 적법 라이선스 없이 설치·활성화 금지 |
| 공개 Text-to-Motion 모델 (MDM · MoMask · T2M-GPT 등) | 코드 라이선스와 별개로 학습 데이터(HumanML3D ← AMASS)의 비상업 조건 가능성 — **미확인** | Phase 5에서 모델별 조사 |
| Meshy Text-to-Motion | `POST /openapi/v1/text-to-motion`(`prompt`, `duration`, `mode`) → task id, `GET …/:id` 폴링, `…/:id/stream` SSE, Bearer 키. 입력이 텍스트뿐이라 캐릭터 데이터를 전송하지 않는다. 출력은 Meshy 리그라 리타깃이 필수 | 첫 외부 어댑터 (Phase 6). 길이 범위·가격은 그때 공식 문서로 확인 |
| DeepMotion SayMotion | REST API 있음. 검증 파트너 한정, base URL은 요청해야 받음 | 보류 |

---

## 3. 통합 원칙

### 3.1 배치

```text
Claude Code — 자연어 해석·분해·계획 (에이전트 자신)
  │ MCP
  ├─▶ anim-graph-mcp  (기존, 얇은 프록시 — Tool 하나 = 라우트 하나)
  │       └─ HTTP ─▶ AnimGraphMcpEditor (C++, 게임 스레드)
  │                   ├─ 기존: AnimBP · 몽타주 · BlendSpace · 스켈레톤 슬롯·재할당
  │                   └─ 신규: 스켈레톤 조회 · 임포트 · IK Rig · 리타기터 · 리타깃 · 키 편집 · 검증
  │
  └─▶ anim-gen-mcp    (신규, Phase 3 — Tools/mcp/anim_gen/)
          ├─ 정책 · 비용 장부 · 승인 · Provider 레지스트리 · 라우터 · 폴백 · Job 저장소
          ├─ Provider: existing_motion · direct_key · blender · local_ai · external.meshy
          └─ 에디터 조작은 bridge.py 로 위 플러그인 Tool 을 부른다 (HTTP 재구현 금지)
```

1. **C++는 UObject·애셋 조작과 수치 검증만 한다.** 네트워크 호출, 서브프로세스, 대기를 넣지 않는다.
2. **`anim_graph_mcp/server.py`에는 로직을 넣지 않는다.** Phase 1~2의 새 에디터 Tool도 프록시 함수만 추가한다.
3. **상태(정책·Job·승인·비용 장부)는 `anim_gen`만 가진다.** 저장 위치는 `Saved/AnimGen/`(추적 안 함).
4. **플러그인은 프로젝트를 모른다.** 영웅 이름, 출력 경로, 명명 규칙은 인자로 받고, 기본값은 `[AnimGraphMcp]` ini에 둔다.
5. **엔진 의존성 추가**(IKRig · IKRigEditor · InterchangeCore · InterchangeEngine · InterchangePipelines · AnimationBlueprintLibrary — 감사 §6)는 `AnimGraphMcpEditor.Build.cs`와 `AnimGraphMcp.uplugin`의 `Plugins`에 선언한다.
6. **쓰기 경로 허용 목록:** 새 쓰기 Tool은 `[AnimGraphMcp] +GenerationOutputPaths=`(기본 `/Game/Animation/Generated/`, `/Game/Animation/Test/`) 밖에 애셋을 만들지 않는다(`OUTPUT_PATH_NOT_ALLOWED`). 기존 Tool과 기존 보호 목록의 동작은 바꾸지 않는다.
   - 허용 목록과 임포트 허용 루트의 **유일한 기준은 이 ini**다. `get_editor_status`가 내보내고 `anim_gen`은 그것을 읽는다(따로 두지 않는다).
   - 생성 경로는 스모크 경로(`SmokeTestPaths=/Game/Animation`) 안에 있어 생성된 몽타주도 스모크 검사를 받는다. 의도된 동작이고, 승격 전 "Slot 노드 없음" 경고는 정상이다.
7. **원본 비파괴:** 소스 애셋은 읽기만 한다. 각 쓰기 Tool은 호출 전후 **에디터 전체의 더티 패키지 집합 차이**를 본다. 새로 더티가 된 패키지 중 허용 목록 밖이 하나라도 있으면 아무것도 저장하지 않고 `UNEXPECTED_DIRTY`(목록 포함)로 실패한다. 애셋마다 따로 검사하지 않고 한 곳에서 보므로, 모르는 부작용(예: 임포트가 스켈레톤에 커브 메타데이터를 더함)도 잡힌다.

### 3.2 결과 형식

봉투는 기존 것을 그대로 쓰고, 생성 관련 필드는 `result` 안에 둔다.

```jsonc
{
  "ok": true, "tool": "retarget_animations", "request_id": "…",
  "result": {
    "job_id": null,                      // 비동기일 때만
    "provider": "retarget",              // anim-gen-mcp 경유 시 Provider 이름
    "generated_assets": ["/Game/Animation/Generated/Vesper/AS_Vesper_Sickle_SpinSlash"],
    "validation": { "status": "NEEDS_REVIEW", "structural": [], "numeric": [], "needs_review": [] },
    "limitations": [],                   // 원 요청 대비 빠진 것 — 폴백 결과면 필수
    "fallback_history": []
  },
  "error": null,
  "diagnostics": [{ "level": "warning", "code": "UNMAPPED_TARGET_CHAINS", "message": "…" }]
}
```

- 경고는 `diagnostics[]`에 둔다.
- 요청한 작업(생성 · 검증, `save`를 요청했으면 저장까지)이 실제로 끝나기 전에는 `ok: true`를 반환하지 않는다. `save=false`(기본)면 저장되지 않은 더티 애셋이 정상 결과다.
- 오류 코드는 기존 체계(HTTP 상태 + 코드)에 추가한다. 예: `IMPORT_FAILED` · `IKRIG_AUTO_FAILED` · `RETARGET_FAILED` · `VALIDATION_FAILED` · `OUTPUT_PATH_NOT_ALLOWED` · `UNEXPECTED_DIRTY` · `PROVIDER_UNAVAILABLE` · `APPROVAL_REQUIRED` · `BUDGET_EXCEEDED` · `COST_UNKNOWN` · `LICENSE_RESTRICTED`. 세부 사유는 기존 Tool처럼 `error.details.reason`에 둔다.
- `limitations[]` 항목은 `{code, message, source}`다(`source` = `router` · `provider` · `direct_key` · `validation` · `fallback`). C++ Tool이 돌려주는 문자열 한계(예: 미러의 `MIRROR_CURVES_UNCHANGED`)는 `anim_gen`이 같은 모양으로 감싼다.

### 3.3 원본 Tool 목록 대응

| 원본 Tool | 처리 | Phase |
| :--- | :--- | :---: |
| `inspect_skeleton` | 신규 (C++) | 1 |
| `inspect_character` | `inspect_skeleton`의 `skeletal_mesh` 인자로 흡수 | 1 |
| `import_motion_file` | 신규 `import_animation_file` (FBX만. BVH는 Blender로 FBX 변환 후) | 1 |
| `create_ik_retargeter` | 신규 `create_ik_rig` + `create_ik_retargeter` | 1 |
| `retarget_motion` | 신규 `retarget_animations` | 1 |
| `validate_generated_animation` | 신규 `validate_animation` (Phase 1은 구조 + 절대·상대 수치 + 회귀 비교) | 1 · 8 |
| `list_existing_motions` | 기존 `list_animation_assets`. 메타데이터 검색은 신규 `search_animations` | 2 |
| `modify_existing_motion` · `create_animation_sequence` | 신규 `preview_animation_edits` / `apply_animation_edits` (op 사전, 기존 `apply_graph_operations`의 전체 사전 검증 패턴). 원자성은 "모든 op를 메모리 버퍼에서 끝까지 계산한 뒤에만 새 애셋을 만든다" — 항상 새 애셋이라 그래프 op 같은 보상 롤백은 없다 | 2 |
| `generate_procedural_motion` | 별도 Tool 아님 — `direct_key` Provider 내부 | 2 |
| `create_animation_montage` | 기존 `create_anim_montage` | — |
| `create_animation_blendspace` | 기존 `create_blendspace` | — |
| `list_motion_providers` · `get/set_generation_policy` · `plan_motion_generation` · `estimate_generation_cost` · `generate_motion` · `get_generation_status` · `cancel_generation` | anim-gen-mcp + 신규 `approve_generation` | 3 |
| `apply_motion_constraints` · `preview_generated_animation` | 보류 | 8 |
| `create_animation_from_prompt` | **폐기.** 자연어 분해는 Claude Code가 하고 `plan_motion_generation`에 구조화된 요청을 넘긴다 | — |

### 3.4 Job

- **에디터 작업:** 기본은 동기다. 일괄 리타깃은 엔진이 한 번의 동기 호출로 처리하므로, 요청당 애셋 수 상한(입력 + 동반 참조 **50** — Phase 1 실측: 20개·1,317프레임을 리타깃·검증·저장까지 3.0초, 애셋당 300프레임이어도 50개 약 35초) + 180초 타임아웃으로 한다. 상한을 넘는 일괄 처리가 실제로 필요해지면 `AnimMcpAutomationRunner`의 `job_id` + poll 패턴으로 애셋 단위 틱 분할을 추가한다.
- **Provider 작업**(외부 API · Blender · 로컬 AI)은 `anim_gen`의 Job 저장소가 맡는다.
  - 상태: `QUEUED` · `RUNNING` · `WAITING_FOR_APPROVAL` · `SUCCEEDED` · `FAILED` · `CANCELLED`
  - 필드: id, plan_id, provider, 현재 단계, 비용(추정/실제), 결과 파일, 오류 코드, attempt · retry_count, fallback_history, approval_id, idempotency_key, events[](상태 전이 기록), diagnostics[]
  - diagnostics(개정 7 보강 2): `anim_gen` 자신의 진단과 함께 **단계 안 에디터 Tool 이 봉투로 돌려준 진단**(`LENGTH_SNAPPED` · `UNMAPPED_TARGET_CHAINS` 등)을 항목마다 `tool` · `step` 을 붙여 남긴다. 단계가 실패해도 남긴다. 실행기가 단계마다 `EditorClient.collect()`(스레드별)로 감싸 모으므로 Provider 는 따로 넘기지 않는다. 계획 시점 호출의 진단은 계획 `diagnostics` 쪽이다
  - 전이: `QUEUED → RUNNING | WAITING_FOR_APPROVAL | CANCELLED`, `RUNNING → SUCCEEDED | FAILED | WAITING_FOR_APPROVAL | CANCELLED`, `WAITING_FOR_APPROVAL → QUEUED(승인) | CANCELLED`. 종료 3종(`SUCCEEDED` · `FAILED` · `CANCELLED`) 뒤 전이는 없다.
  - 실행 모델(Phase 3): 에디터 Provider(`existing_motion` · `direct_key` · `retarget`)는 `generate_motion` 호출 안에서 동기로 끝난다. 비동기 Provider(외부 · Blender · 로컬 AI)는 백그라운드 스레드 없이 `get_generation_status`가 poll 할 때 진행한다.
  - 로컬 서브프로세스(개정 7 — `blender`): `generate_motion`이 프로세스를 띄우고 `RUNNING`을 돌려준다. poll 이 끝남(report 파일)을 보면 같은 호출 안에서 import → retarget → 검증까지 동기로 잇는다. 자식은 stdin을 막고 출력을 로그 파일로 보낸다(MCP stdio 보호), 키·토큰 이름의 환경 변수는 넘기지 않는다. 기한(`execution.subprocess_timeout_seconds`)을 넘기면 끝내고 `GENERATION_FAILED`(`TIMEOUT`). 서버가 다시 뜨면 프로세스 핸들이 없어 report 파일로만 판정하고, 기한까지 report가 없으면 멈추지 못한 채 `TIMEOUT`으로 적는다.
  - 같은 계획으로 `generate_motion`을 다시 부르면 기존 Job을 돌려준다. 실패·취소된 Job은 `retry=true`일 때만 새 Job을 만든다.
  - 저장 위치: `Saved/AnimGen/{policy.json, plans/, jobs/, approvals/, ledger.jsonl}`(`ANIM_GEN_STATE_DIR`로 바꿀 수 있다 — 테스트 격리용). 서버 프로세스 하나를 전제한다.
- **취소:** 취소가 Provider 실행의 즉시 중단을 뜻하지 않는다. 외부 작업은 "결과 무시"로 처리하고, 이미 발생한 비용은 장부에 남긴다. 로컬 서브프로세스(`blender`)는 실제로 종료하고 Job에 `cancel_effect{stopped, pid}`를 남긴다(개정 7).

---

## 4. Provider

| Provider | 하는 일 | Phase | 기본 상태 |
| :--- | :--- | :---: | :--- |
| `retarget` (파이프) | 공통 처리 계층 — 모든 Provider 결과가 지난다 | 1 | 활성 |
| `existing_motion` | 메타데이터 인덱스로 검색 → 리타깃 → 편집 | 2 | 활성 (주 경로) |
| `direct_key` | `IAnimationDataController`로 키 작성: 리타임 · 트림 · 미러 · 본 오프셋 · 루트 Yaw · 포즈 유지 · 구간 연결 | 2 | 활성 |
| `blender` | `motion_file`(BVH)을 headless(`blender -b --factory-startup -P anim_gen/blender/bvh_to_fbx.py`)로 FBX로 바꿔 retarget 파이프로 넘긴다 — 더미 스킨 메시 · 대상 정면 · 바닥 맞춤 · 범위 · fps. FBX 입력·아마추어 편집은 이후 | 4 | 실행 파일(정책 `paths.blender_executable`)이 있으면 활성 |
| `local_ai` | 라이선스 게이트를 통과한 모델만 | 5 | 비활성 |
| `external.meshy` | text-to-motion → FBX → 리타깃 | 6 | 비활성 (유료, 승인 필수) |
| `control_rig` | 손·무기 파지, 발 고정 같은 제약 보정 베이크 | 8 | 비활성 |

- **Motion Primitive** 개념은 유지하되 Phase 2에서는 `direct_key` 편집 op(`retime` · `trim` · `mirror` · `offset_bone` · `rotate_root` · `hold_pose` · `concat`(+ `reverse` 옵션))로 한정한다.
- **Phase 2와 Phase 3의 경계:** Phase 2는 Provider가 부를 에디터 Tool(`search_animations` · `preview/apply_animation_edits`)만 만든다. `existing_motion` · `direct_key`를 Provider로 등록하는 것은 `anim_gen`(Phase 3)이다. `StepForward` · `JumpArc` 같은 전신 Primitive로 새 전신 모션을 짓는 것은 Phase 8 실험 항목이고, 품질 기대치가 낮다는 점을 결과에 명시한다.
- **Capability**는 원본 목록(입력 유형, 신규 생성 지원, 수정 지원, 커스텀 스켈레톤 지원, 출력 포맷, 최대 길이, GPU 필요, 네트워크 필요, 유료 여부, 비용 추정 가능 여부, 라이선스 상태, 설치·인증 상태)을 Provider 매니페스트 데이터로 둔다.
  - 파일: `Tools/mcp/anim_gen/providers.json`(추적). 필드: `input_types[]` · `supports_new_generation` · `supports_modification` · `supports_custom_skeleton` · `output_formats[]` · `max_duration_seconds` · `requires_gpu` · `requires_network` · `paid` · `cost_estimable` · `license` · `auth_env`(환경 변수 **이름**만).
  - 설치·인증 상태는 매니페스트에 적지 않고 실행 시 계산한다: `state{implemented, installed, auth{env, present}, available, unavailable_reason}`. 키 값은 어디에도 내보내지 않는다.

---

## 5. 라우터

- **Phase 3 MVP는 규칙 표**다(요청 유형 × 가용 Provider × 정책). 점수 기반 선택은 실제로 동작하는 Provider가 3개 이상이 된 뒤에 검토한다.
- **입력:** 구조화된 요청(§9) + `inspect_skeleton` 결과 + Provider 가용성 + 정책.
- **출력:** 후보 계획 목록. 각 계획은 단계 사슬 · 예상 비용 · 위험 · 예상 한계를 갖는다. `plan_motion_generation`은 실행하지 않는다.

| 요청 유형 | 규칙 |
| :--- | :--- |
| 일반 이동·대기 | `existing_motion` → (없으면) `local_ai`(활성일 때) → 정책이 허용할 때만 `external` |
| 손 위치가 중요한 무기 동작 | `existing_motion` + `direct_key` 편집 → 파지 오차를 검증으로 보고 → 보정(Phase 8) |
| 새 복합 전신 동작 | `local_ai`(활성일 때) → `external`(허용·승인 시) → 결과 후처리 → 품질이 부족하면 세그먼트 방식(Phase 8) 제안 |

외부 AI가 가장 적합해도 정책이 막으면 호출하지 않는다.

**모드별 순서 (개정 6 — `Tools/mcp/anim_gen/router.py`의 규칙 표):** `existing` = `existing_motion`, `meshy` = `external.meshy`.

| `motion_category` | `FREE_ONLY` | `FREE_FIRST` (기본) | `QUALITY_FIRST` | 붙는 한계 |
| :--- | :--- | :--- | :--- | :--- |
| `idle` · `locomotion` | existing → local_ai | existing → local_ai → meshy | existing → meshy → local_ai | — |
| `weapon_action` | existing → local_ai | existing → local_ai → meshy | existing → meshy → local_ai | 모든 후보 `GRIP_NOT_VALIDATED`(파지 검증·보정은 Phase 8), AI 후보 `DRAFT_NEEDS_CLEANUP` |
| `full_body_new` | local_ai → existing(근사) | local_ai → meshy → existing(근사) | meshy → local_ai → existing(근사) | 근사 후보 `NOT_NEW_MOTION` + 제안 `SEGMENTED_PLAN`(Phase 8) |

- **단계 전개:** existing = 소스 결정(`reference_animations` 또는 `search_animations`) → [소스 스켈레톤 ≠ 대상이면 `retarget`] → [`edits`가 있으면 `direct_key`] → 검증. AI Provider = 생성 → `import_animation_file` → `retarget` → [`direct_key`] → 검증.
- **재사용:** 소스가 대상 스켈레톤에 있고 `edits`가 없으면 복제하지 않는다 — `reused_assets` + 한계 `REUSED_EXISTING`.
- **`provider` 지정:** 그 Provider의 후보만 만들고 폴백을 끈다(원 요청이 Provider를 고른 것이므로).
- **`motion_file` (개정 7):** 있으면 `blender`를 모드 순서 맨 앞에 둔다(요청이 소스를 준 것). 없으면 위 표 그대로이고 `blender`는 후보·제외 목록에 나오지 않는다. 사슬 = 변환(blender) → `import_animation_file`(`sample_rate` = 요청 `frame_rate`) → `retarget` → [`direct_key`] → 검증.
- **계획 단계 제외(`excluded[]`):** `PROVIDER_UNAVAILABLE`(`NOT_IMPLEMENTED` 등) · `LICENSE_RESTRICTED` · `AUTHENTICATION_FAILED`(`API_KEY_MISSING`) · `APPROVAL_REQUIRED`(`POLICY_FREE_ONLY` · `PAID_API_DISABLED`) · `COST_UNKNOWN` · `UNSUPPORTED_REQUEST`(Capability 밖, 예: 최대 길이 초과).
- **계획은 실행하지 않는다:** 읽기 전용 에디터 호출(`get_editor_status` · `inspect_skeleton` · `search_animations`)로 고른 소스·소스 메시를 계획에 고정해 보여 주고, 출력 경로를 ini 허용 목록으로 미리 검사한다. 에디터가 없으면 단계를 미해결로 둔 계획만 만든다.
- 중간 애셋(IK Rig · 리타기터 · 리타깃 중간본)은 `<output_path>/Work/<job_id>/`에 만들고 결과와 같은 `save`를 따른다. 지우지 않는다(정리는 사용자 확인 후).

---

## 6. 비용·실행 정책

원본의 세 모드(`FREE_ONLY` · `FREE_FIRST`(기본) · `QUALITY_FIRST`)와 의미를 유지한다. 바뀌는 점:

- **정책 파일:** 기본값 `Tools/mcp/anim_gen/policy.default.json`(추적) + 로컬 덮어쓰기 `Saved/AnimGen/policy.json`(추적 안 함).
- **API 키:** 환경 변수(`MESHY_API_KEY` 등)로만 받는다. 저장소, Tool 인자, 로그, Job 기록에 키를 남기지 않는다.
- **승인:** `approve_generation(plan_id, max_cost_usd, max_attempts, provider?)`. 승인 범위는 한 계획의 지정 Provider 호출 횟수(재시도 포함) + 금액 상한이다. 범위를 넘는 재시도는 새 승인이 필요하다.
  - 검사: 추정 ≤ `max_cost_usd` ≤ `max_cost_per_job_usd`, 그리고 지출 + 예약 + `max_cost_usd` ≤ `max_total_cost_usd` → 아니면 `BUDGET_EXCEEDED`. `FREE_ONLY` · `paid_api_enabled=false`면 승인하지 않는다(`BAD_REQUEST` `POLICY_FREE_ONLY` · `PAID_API_DISABLED`). 비용 미확인이면 `COST_UNKNOWN`.
  - 승인하면 그 계획의 `WAITING_FOR_APPROVAL` Job이 `QUEUED`가 된다. 실행은 다음 `generate_motion` 호출에서 한다(승인이 실행을 일으키지 않는다).
- **중복 과금 방지:** 유료 제출은 `(plan_id, attempt)`를 멱등 키로 쓴다. 같은 키로 다시 요청하면 기존 Job을 돌려준다. 제출 직전 장부(`Saved/AnimGen/ledger.jsonl`)에 예약을 적고, 같은 키가 이미 있으면 제출하지 않는다.
- **비용을 확인할 수 없는 유료 요청은 실행하지 않는다.** 금액을 임의로 계산해 확정하지 않는다. Provider가 실제 금액을 알려 주지 않으면 `actual_usd: null`(미확정)로 두고 추정액을 예약으로 남긴다.
- **정책 파일에 두지 않는 것:** 출력 경로(ini `GenerationOutputPaths`가 유일한 기준)와 덮어쓰기 허용(C++가 항상 금지 — 정책으로 켤 수 없다). `set_generation_policy`는 이런 키(`output_path*` · `candidate_root` · `allow_asset_overwrite`)와 키·토큰 이름의 키를 `BAD_REQUEST FORBIDDEN_KEY`로 거부하고, `require_explicit_approval`은 `true`만 받는다.
- **병합 순서:** `policy.default.json` ← `Saved/AnimGen/policy.json`(딥 머지) ← 요청의 `generation_policy`(정책이 `FREE_ONLY`면 벗어날 수 없다 — 진단 `POLICY_CLAMPED`). 실행 시점의 정책으로 다시 검사한다.

```jsonc
{
  "mode": "FREE_FIRST",
  "billing": { "paid_api_enabled": false, "require_explicit_approval": true, "max_cost_per_job_usd": 0, "max_total_cost_usd": 0 },
  "execution": { "max_generation_attempts": 3, "allow_fallback": true, "preserve_intermediate_results": true, "subprocess_timeout_seconds": 300 },  // 타임아웃: 개정 7
  "paths": {
    "blender_executable": "C:/Program Files/Blender Foundation/Blender 4.4/blender.exe"
  }
}
```

---

## 7. 폴백

원본의 실패 원인 분류를 유지하고 `APPROVAL_REQUIRED`를 추가한다.

```text
PROVIDER_UNAVAILABLE · AUTHENTICATION_FAILED · APPROVAL_REQUIRED · BUDGET_EXCEEDED · COST_UNKNOWN · RATE_LIMITED · LICENSE_RESTRICTED
UNSUPPORTED_REQUEST · GENERATION_FAILED · IMPORT_FAILED · RETARGET_FAILED · VALIDATION_FAILED · QUALITY_INSUFFICIENT
```

에디터 Tool 오류는 다음처럼 분류한다(개정 6):

| 상황 | 원인 | 다음 |
| :--- | :--- | :--- |
| `EDITOR_GONE` · `TIMEOUT` · `TRANSPORT` | `PROVIDER_UNAVAILABLE` (`EDITOR`) | **중단** — 모든 경로가 리타깃·저장에 에디터를 쓴다 |
| 검색 0건 · 참조 애셋 없음 | `UNSUPPORTED_REQUEST` (`NO_MATCH`) | 다음 후보 |
| `edits`의 `BAD_REQUEST` | `UNSUPPORTED_REQUEST` (`BAD_OPERATIONS`) | 다음 후보 |
| `IKRIG_AUTO_FAILED` · `RETARGET_FAILED` · `RIG_MISMATCH` | `RETARGET_FAILED` (`details.bones` 보존 — 수동 체인 제안용) | 다음 후보 |
| `VALIDATION_FAILED` · `EXPECT_*` | `VALIDATION_FAILED` | 다음 후보 |
| `UNEXPECTED_DIRTY` · `OUTPUT_PATH_NOT_ALLOWED` · `ASSET_EXISTS` · `ASSET_PROTECTED` · `IMPORT_SOURCE_NOT_ALLOWED` | 그대로 | **중단** — 가드·요청 문제라 다른 Provider도 같다 |
| Provider `RATE_LIMITED` | 그대로 | 같은 후보 재시도 |
| 유료 단계: 승인 없음 · 상한 초과 · 비용 미확인 | `APPROVAL_REQUIRED` · `BUDGET_EXCEEDED` · `COST_UNKNOWN` | 뒤에 무료 후보가 있으면 그쪽, 없으면 승인 대기(`APPROVAL_REQUIRED`) 또는 `FAILED` |

시도 수 = 후보 실행 횟수(재시도 포함)이고 `max_generation_attempts`를 넘지 않는다. 유료 후보는 승인의 `max_attempts`도 따른다.

다른 Provider로 넘어가려면 아래를 모두 만족해야 한다(원본 유지):

- 비용 정책을 위반하지 않는다.
- 그 Provider가 요청을 처리할 수 있다.
- 라이선스상 쓸 수 있다.
- 리타깃이 가능하다.
- 최대 시도 횟수를 넘지 않았다.

이미 만든 유효한 결과는 후보로 보존한다(`preserve_intermediate_results` — Job의 `preserved_candidates[]`). **폴백 결과는 `limitations[]`에 원 요청 대비 무엇이 빠졌는지 반드시 적고**(`FALLBACK_USED{from, cause, missing}` + 그 후보의 예상 한계), 원 요청을 완전히 충족한 결과로 보고하지 않는다.

---

## 8. 스켈레톤 조회 — `inspect_skeleton` (Phase 1)

- **입력·결과의 기준은 감사 §10**이고, 이 절은 그 요약이다.
- **입력:** `skeleton` 또는 `skeletal_mesh`, `details=false`, `compare_to?`(비교할 스켈레톤).
- **출력:** 측정값만 담고 추정으로 채우지 않는다.

| 필드 | 내용 |
| :--- | :--- |
| `skeleton_path` · `meshes[]` | 스켈레톤과 그것을 쓰는 메시 |
| `bone_count` · `root_bone` | |
| `bones[]` | 이름 · 부모 · 기준 포즈(로컬/컴포넌트). 기본은 요약, `details`면 전체 |
| `virtual_bones[]` · `sockets[]` | 스켈레톤 소켓 + 메시 소켓 |
| `slot_groups[]` · `curve_count` | |
| `ik_rigs[]` · `retargeters[]` | 이 스켈레톤(메시)을 참조하는 애셋 (AssetRegistry) — `existing_rig` / `existing_retargeter` 후보 |
| `animation_count` | |
| `template_match` | 자동 캐릭터라이저의 템플릿 사용 여부 · 이름 · 매칭률 (판정 아닌 측정값) |
| `compare` | `compare_to`가 있을 때: 공통 본 수 · 상대에 없는 본 · 기준 포즈 회전 차 · 본 길이 비 · 판정(`same_rig` \| `needs_ik_retarget` \| `no_common_bones`) |

원본 초안의 `compatible_skeletons[]`(엔진 호환 목록은 이름 기준이라 판정 근거가 못 됨, 감사 §8)와 `pose_measure`(A/T 포즈 측정)는 Phase 1 범위에서 뺐다.

무기 파지점은 스켈레톤이 아니라 무기 메시 소켓과 장비 데이터에 있다(예: 라이플 `LeftHandIK` 소켓, `DA_EF_Rifle.AttachSocket = hand_r`). 인스펙터는 무기 정보를 추정하지 않는다. 필요하면 요청이 무기 메시를 인자로 준다.

---

## 9. 생성 요청 스키마

내부 요청 스키마와 외부 Provider API 스키마를 분리한다(원본 유지). 원본 대비 이름·경로·힌트 필드를 조정했다.

```jsonc
{
  "target_skeleton": "/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F",
  "target_mesh": "/Game/Assets/IdaFaber/Meshes/Girl/SK_StreetDemon_F_01", // 리타깃 단계가 있으면 필수 (개정 6)
  "hero": "Vesper",                          // 이름 토큰
  "family": "Sickle",                        // 이름 토큰
  "animation_name": "AS_Vesper_Sickle_SpinSlash",
  "description": "낫을 양손으로 잡고 회전하며 3번 베는 공격",   // 기록만 — 서버는 해석하지 않는다
  "motion_category": "weapon_action",        // idle | locomotion | weapon_action | full_body_new (개정 6)
  "duration_seconds": 3.0,
  "frame_rate": 30,
  "loop": false,
  "root_motion_mode": "auto",
  "reference_animations": [],                // 주면 검색 대신 이 소스를 쓴다 (선택)
  "search": { "query": "sickle attack", "path_prefix": "/Game", "min_length": null, "max_length": null },  // 개정 6
  "edits": { "source": null, "operations": [] },                // 개정 6 — Phase 2 op 사전 그대로
  "retarget": { "source_mesh": null, "existing_retargeter": null, "source_facing": "auto" }, // 개정 6 — 재사용은 명시할 때만 · 개정 7 보강 source_facing
  "constraints": { "two_hand_weapon_grip": true, "foot_contact": true, "smooth_start_end": true },
  "generation_policy": "FREE_FIRST",
  "provider": "auto",
  "integrate_anim_bp": false,
  "output_path": "/Game/Animation/Generated/Vesper",
  "motion_file": null                        // 개정 7 — BVH 경로 또는 {path, unit, facing, range, axis_forward, axis_up}
}
```

Provider가 지원하지 않는 제약은 후처리로 해결 가능한지 따지고, 해결할 수 없으면 무시하지 않고 `limitations[]`에 기록한다.

**개정 6 — 필드 규칙 (`Tools/mcp/anim_gen/request.py`):**

| 필드 | 규칙 |
| :--- | :--- |
| `target_skeleton` · `animation_name` · `output_path` · `motion_category` | 필수. `output_path`는 `get_editor_status.generation.output_paths` 안이어야 한다(계획 단계에서 미리 검사, 최종 기준은 C++) |
| `target_mesh` | 리타깃 단계가 생기는 후보에는 필수 — 없으면 그 후보를 `MISSING_INPUT`으로 막는다. 스켈레톤의 첫 메시를 암묵적으로 고르지 않는다(§10) |
| `reference_animations[]` · `search{query, path_prefix, asset_class, min_length, max_length, root_motion, loop, tags, limit}` | existing_motion의 소스. 참조가 있으면 검색하지 않는다 |
| `edits{source?, operations[]}` | `direct_key` 단계(Phase 2 op 사전). `source`를 생략하면 앞 단계 결과 |
| `retarget{source_mesh?, existing_source_rig?, existing_target_rig?, existing_retargeter?, source_pelvis?, source_chains?, source_facing?}` | 리타깃 파이프 입력. `source_mesh`를 생략하면 소스 스켈레톤의 프리뷰 메시를 계획에 고정해 보여 주고 위험 `SOURCE_MESH_IMPLICIT`을 단다. `source_facing`(개정 7 보강): 소스가 보는 UE 축 — `auto`(기본, 소스 기준 포즈로 잼) · `keep`(맞추지 않음) · `+X` · `−X` · `+Y` · `−Y`. 대상 정면과 다르면 계획에 위험 `FACING_DIFFERS` + 한계 `FACING_ALIGNED`(§10), 못 재면 `FACING_UNKNOWN`(맞추지 않음), 소스를 계획 때 모르면(생성 임포트 · 에디터 없음) `FACING_UNRESOLVED_AT_PLAN` 후 실행 때 잰다 |
| `generation_policy` | 정책 모드를 요청 단위로 바꾼다. 정책이 `FREE_ONLY`면 벗어날 수 없다(`POLICY_CLAMPED`) |
| `provider` | `auto` 또는 Provider 이름 — 이름이면 폴백을 끈다(§5) |
| `duration_seconds` · `frame_rate` · `loop` · `constraints` · `integrate_anim_bp` | 결과와 다르면 한계로 기록: `DURATION_MISMATCH` · `FRAME_RATE_MISMATCH`(출력 fps = 주 소스, §2.3) · `LOOP_MISMATCH` · `GRIP_NOT_VALIDATED` · `FOOT_CONTACT_NOT_ENFORCED` · `CONSTRAINT_UNSUPPORTED` · `ANIM_BP_NOT_INTEGRATED`(Phase 7). 길이·fps·루프는 결과를 측정해 적는다(계획 단계 값은 예상). `loop`는 `direct_key` 결과의 `bLoop`로도 쓰인다(내장 검증 `expect`가 쓴 값을 확인) |
| `save` | 요청에 두지 않는다 — `generate_motion(plan_id, save)` 인자 |
| `motion_file` (개정 7) | 문자열이면 `path`. `path`: 절대 경로, ini `ImportSourceRoots` 아래만(밖이면 계획 전체가 `IMPORT_SOURCE_NOT_ALLOWED`), `.bvh`만. `unit`: `auto`(기본) · `cm` · `m` · `mm` · `inch` · 숫자(cm/파일 단위). `facing`: `auto`(대상 스켈레톤 정면에 맞춤, 기본) · `keep` · `+X` · `−X` · `+Y` · `−Y`(UE 축). `range{start, end}`(초, 굽기 범위 — 요청 `frame_rate` 가 있으면 끝을 그 rate 의 프레임 경계로 당긴다, 진단 `RANGE_ALIGNED`. 정수 fps 가 아니라 맞출 수 없으면 리샘플하지 않는다). `axis_forward`(`-Z`) · `axis_up`(`Y`) — Blender BVH 임포터와 같은 뜻. 계획이 BVH 헤더(관절 계층 — 수동 체인 제안용) · 단위 · 회전 · 범위 · fps · 파일 SHA-256 을 고정하고, 실행 때 파일이 바뀌었으면 `FILE_CHANGED`로 멈춘다 |

---

## 10. 공통 리타깃 처리 (Phase 1 핵심)

```text
FBX 파일 또는 프로젝트 안의 기존 시퀀스
  → import_animation_file   Interchange 로 후보 스테이징 폴더에 임포트 — 메시·스켈레톤째 새로(skeleton 미지정) 또는 기존 스켈레톤에 애니만. 커브 메타데이터 추가 끔
  → inspect_skeleton        소스 · 타깃 (compare_to 로 리그 차이 측정 — 참고 정보)
  → create_ik_rig           existing_rig 를 주면 재사용 → 아니면 자동 캐릭터라이즈 → 실패(IKRIG_AUTO_FAILED + 본 계층)면 chains 인자로 수동 정의
  → create_ik_retargeter    existing_retargeter 를 주면 재사용 → 아니면 AddDefaultOps(또는 기존 RTG 구성 match_existing) → AutoMapChains → (선택) AutoAlignAllBones
  → retarget_animations     FIKRetargetBatchOperationContext(NameRule.FolderPath = 후보 경로, 이름 규칙, 덮어쓰기 false) → RunRetarget
  → validate_animation      소스 대비 상대 비교
```

- **생성 흐름은 항상 복제한다:** `same_rig`여도 `reassign_skeleton`을 쓰지 않는다. 그 Tool은 애셋을 제자리에서 옮겨 원본이 바뀐다. 같은 리그 사이 리타깃은 사실상 항등 변환이므로 `retarget_animations`(복제 후 작업)로 그대로 처리한다. `reassign_skeleton`은 원래 용도(본 이름이 같은 중복 스켈레톤 정리, `confirm` 필수)에만 쓴다.
- **리그 판정은 이름이 아니라 기준 포즈 차로 한다:** UE4 마네킹은 본 이름이 전부 Vesper에 있지만 기준 포즈가 10~40° 다르고 본 길이가 최대 3.6배 달라, 이름만 보면 같은 리그로 오판한다. `same_rig`는 기준 포즈 회전 최대 < 1° ∧ 길이 비 0.99~1.01(감사 §8)이고, 라우터·보고용 참고 정보다.

- 리타깃은 Provider와 독립적으로 동작한다(원본 유지).
- **좌표·스케일:** FBX 단위·축은 Interchange 설정이, 비율 차이는 리타기터 op가 처리한다. Blender·Meshy 출력의 단위(m/cm)와 축은 각 Provider Phase(4·6)에서 확인한다.
  - Blender(개정 7, 실측): 장면 1 BU = 1 cm + 임포트 배율 = cm/단위 → 노드 스케일 1 · FBX 단위 cm. BVH(Y-up, 앞 −Z 기본) → UE `(x, z, y)`, 즉 BVH +Z 정면 · +X 왼쪽 = UE 마네킹·Vesper와 같은 +Y 정면 · +X 왼쪽. 루트 본 = BVH 루트(`Armature` 널 제외).
  - **정면:** FK 체인이 전역 델타라 소스와 대상의 정면을 맞춰야 한다. 정면은 발 영역(바닥 + 키 × 15%)의 부모 → 자식 수평 벡터 합으로 잰다(좌우 대칭 IK 본은 상쇄). 바닥 · 꼭대기는 p5 ~ p95 폭보다 더 떨어진 외톨이 본을 빼고 정한다(SB 의 FX 본 z −2217cm). 스켈레톤 소스는 좌우 체인(`Left*` / `Right*` 쌍의 시작 본) 위치 차로 교차 확인하고, 둘이 다르면 모른다고 본다(`FEET_LATERAL_DISAGREE`). BVH는 Blender에서 대상 정면으로 돌려 적용한다.
  - **정면 맞춤 (개정 7 보강):** retarget 파이프는 계획 때 소스 · 대상 정면을 재 `steps[].inputs.facing{source, target, yaw_deg}`에 고정하고, 다르면 `create_ik_retargeter(facing_yaw_deg = 소스 → 대상 +Z 회전)`으로 리타기터에서 맞춘다: ① 대상 리타깃 포즈의 스켈레톤 루트 −yaw(자동 정렬 앞) ② 복원 포즈 `FacingRestore` + Additive Pose op(Root Motion op 바로 앞) ③ Root Motion op 가 소스 루트 복사면 `GlobalOffset` +yaw (§2.3). 결과 `facing_alignment{yaw_deg, target_root, restore_pose, op, op_index, enabled, consistent}`는 애셋에서 읽는다. 대상 루트가 펠비스면 펠비스 이동이 돌지 않아 `FACING_NEEDS_ROOT`로 거부, 기존 리타기터 재사용은 바꾸지 않고 `FACING_NOT_ALIGNED` 한계(Tool 진단 `FACING_MISMATCH_EXISTING`). 루트 회전이 기준 대비 Yaw 만일 때 정확하다. 리타기터 에디터 프리뷰의 대상 리타깃 포즈는 돌아가 보인다(출력은 대상 정면).
  - **기준 포즈 높이:** 소스 골반이 바닥 높이면 Pelvis Motion op 가 이동을 키운다 → BVH 기준 포즈는 가장 낮은 점을 z = 0 으로 올리고 루트 위치 키에서 같은 만큼 뺀다(애니의 월드 위치는 그대로).
- **루트 모션:** 루트·골반 처리는 리타기터의 Pelvis Motion · Root Motion op 설정을 따른다. 5.7 `AddDefaultOps`는 op 5개(Pelvis Motion · FK Chains · Run IK Rig + IK Chains · Root Motion · Curve Remap)이고, 기존 RTG는 여기에 Pin Bones를 더하고 Run IK Rig를 끈 7개 구성이다(감사 §4).
- **일괄 리타깃 안전 설정:** `bOverwriteExistingFiles`는 항상 `false`(같은 이름이 있으면 실행 전에 `ASSET_EXISTS`), 입력은 Sequence·Montage·BlendSpace만(AnimBlueprint 거부), 저장은 `save` 명시 시에만.
- **재사용과 메시는 명시한다:** 기존 IK Rig·RTG는 `existing_rig` / `existing_retargeter`로 줄 때만 쓰고, 소스·대상 메시는 필수 인자다. Vesper 스켈레톤에는 메시가 46개 있고, 기존 타깃 IK Rig는 `SK_StreetDemon_F_02`에, `ABP_Hero_Combat` 프리뷰는 `F_01`에 묶여 있어 암묵적으로 고르면 결과가 달라진다.
- **임포트 부작용 차단:** `bAddCurveMetadataToSkeleton=false` · `bReplaceExisting=false` · `bIsAutomated=true`. 메시째 임포트할 때는 `bImportMaterials` · `bImportTextures` · `bCreatePhysicsAsset` · `bImportStaticMeshes`를 끈다(리타깃 소스에는 스켈레탈 메시·스켈레톤·애니만 필요).
- **자동 매핑 실패 처리:** 자동 캐릭터라이즈는 템플릿이 맞지 않으면 체인 0개로 전부 실패한다. `create_ik_rig`는 이때 `IKRIG_AUTO_FAILED`와 함께 본 이름·부모 목록을 돌려주고, Claude Code가 그것으로 `chains[{name, start, end, goal?}]`를 제안 → 사용자 확인 → `mode: manual`로 다시 부른다. 수동 정의가 잘못되면(본 없음·조상 관계 아님) 해당 체인 목록과 함께 `BAD_REQUEST`.

---

## 11. 복합 애니메이션 (Phase 8)

원본의 세그먼트 계획(Dash → Takeoff → Airborne Rotation → Attack → Landing → Recovery)을 유지한다. 각 세그먼트는 길이, 시작·끝 포즈, 루트 모션, 접촉·무기·타이밍 제약을 가진다. 세그먼트별 Provider가 다를 수 있다. 연결부의 포즈·속도 연속성은 `validate_animation`의 수치 항목으로 검증한다. 분해했다고 자연스러운 연결이 보장되지는 않는다.

---

## 12. AnimBP 연결과 승격 (Phase 7)

- **기존 Tool만 쓴다:** `create_anim_montage` · `set_montage_slots` · `set_montage_sections` · `create_blendspace` · `apply_graph_operations` · `implement_anim_layer_interface` 등.
- **애셋만 요청하면 AnimBP를 수정하지 않는다**(원본 유지).
- **승격(`promote_animation`):** 후보 경로 → 정식 경로(`/Game/Animation/Hero/<영웅>/<계열>/<용도>/`) 이동. 사용자 확인 후 AssetTools rename으로 하고 리디렉터를 남기지 않는다(2026-10-22 애셋 정리와 같은 방식).
- **사격 + Strafe(예시 C):** 하체 strafe, 상체 조준·레이어 블렌드, AimOffset, 왼손 IK, 조준 보정은 이미 `ABP_Hero_Combat` 계열에 있다. 생성할 것은 상체 사격 루프·반동 시퀀스이고, 연결은 기존 레이어 구조에 애셋을 끼우는 일이다.
- 이동 로직, 락온 방향, 사격 지속 시간 같은 게임플레이 상태는 기존 C++/GAS가 기준이다(원본 유지).

---

## 13. 검증 — `validate_animation`

| 구분 | 항목 | Phase |
| :--- | :--- | :---: |
| 구조 | 애셋 존재·저장 · 타깃 스켈레톤 일치 · 길이·프레임 수·프레임레이트 · 모든 트랙 본이 스켈레톤에 있음 · NaN·비정상 스케일 | 1 |
| 수치 — 절대 | 명백한 깨짐만: NaN · 비정상 스케일 · 한 프레임 회전 > 90°(기존 히어로 애니 관측 최대 약 70°) → `FAILED`. 단 소스가 주어졌고 소스도 그만큼 튀면(소스 최대 + 10° 이내) 리타깃이 만든 깨짐이 아니므로 경고 `ROTATION_JUMP_INHERITED` — 30fps 마켓 공격은 손·손가락이 93~109°/프레임(Phase 1 실측) | 1 |
| 수치 — 상대 | 리타깃 결과 vs 소스: 체인별 각속도 p99 비율 · 착지 발 수평 속도 p50 비율(다리 길이 비 보정) · 루트 이동 거리 비율(펠비스 높이 비 보정) · 루프 경계 차 / 프레임당 중앙값 비율. 허용 범위 밖이면 `PASSED_WITH_WARNINGS`. 허용 비율 초기값은 Phase 1 첫 결과로 정한다 | 1 |
| 회귀 비교 | 같은 소스를 기존 RTG로 리타깃한 결과와 본별 각 차이 — "Tool 결과 = 에디터 수동 절차 결과" 확인 (Phase 1 테스트 전용) | 1 |
| 요청 충족 | 길이·루프 조건 · 요청한 순서(세그먼트 경계) · 제약 충족. Phase 2: `expect{length, loop, root_yaw_delta}` 불일치 → `FAILED`(`EXPECT_*`), `seams[]`(이음매 시각)의 회전 변화가 앞 · 뒤 4프레임 중앙값 중 큰 쪽의 `seam_ratio_max`(3.0)배 초과 → 경고 `SEAM_JUMP`. 구간을 고르는 측정용 `profile_bones[]`(프레임별 본 선속도) — 개정 7 보강 `profile_positions`면 같은 시각의 컴포넌트 공간 위치도(동작 평면 비교) | 2 · 8 |
| 제약 | 양손 파지 오차 · 무기 궤적 이상 | 8 |
| 시각 | 항상 `needs_review[]`에 남긴다(사람이 Persona/PIE에서 확인). 프리뷰 프레임 캡처는 Phase 8 | 1 · 8 |

- 절대 임계값을 쓰지 않는 이유: 정상 공격 모션의 각속도 p99가 약 2,000°/s(손가락 최대 3,762°/s)이고, 높이 기준 발 미끄러짐은 정상 Walk 루프에서도 수백 cm/s로 튄다(감사 §5.2). 검증 계산은 C++에서 한다.
- 상태: `PASSED` · `PASSED_WITH_WARNINGS` · `NEEDS_REVIEW` · `FAILED`. 구조 검증 통과가 동작 품질을 뜻하지 않는다(원본 유지).

---

## 14. Phase와 완료 기준

### Phase 0 — 감사 (문서만, 코드 변경 없음) — 완료 2026-10-23

산출물: [ArchitectureAudit.md](ArchitectureAudit.md). 7항 중 6항 확인, 7번(리타깃 소요 시간)은 읽기 전용으로 측정할 수 없어 Phase 1 완료 기준 1번에서 실측한다.

확인 항목:

1. Interchange로 ① 애니만 기존 스켈레톤에, ② 메시 + 스켈레톤 + 애니를 함께 임포트하는 C++ 경로와 파이프라인 설정 키.
2. 자동 캐릭터라이즈를 Vesper · Narmaya · SB · UE4 마네킹 스켈레톤에 돌린 결과(템플릿 이름 · 매칭률 · 빠진 체인). 메모리 안에서만 실행하고 저장하지 않는다.
3. `FIKRetargetBatchOperationContext`로 출력 폴더·이름 규칙·참조 애셋 동반(`bIncludeReferencedAssets`)·덮어쓰기가 어떻게 동작하는지.
4. 기존 수동 `RTG_*`·`IK_AutoGenerated*`의 op 스택과 체인 매핑 덤프 → 회귀 비교 기준 정의.
5. 포즈 샘플링 비용과 기존 히어로 애니의 수치 기준선(각속도·발 미끄러짐).
6. 플러그인 의존성 추가의 영향(빌드, 모듈 로딩, 에디터 기동 시간).
7. 일괄 리타깃 소요 시간 측정 → 요청당 애셋 수 상한.

완료 기준: 위 7항의 결과 + Phase 1 Tool 시그니처 확정안. **사용자 승인 후 Phase 1.**

### Phase 1 — 리타깃 기반

- **Tool:** `inspect_skeleton` · `import_animation_file` · `create_ik_rig` · `create_ik_retargeter` · `retarget_animations` · `validate_animation` (C++ 플러그인 + `server.py` 프록시). 입력·결과 시그니처는 감사 §10
- **설정:** `+GenerationOutputPaths=` · `+ImportSourceRoots=` · `MaxRetargetAssetsPerCall=50`(Phase 1 실측으로 확정, 처음 잠정값 20)
- **의존:** `AnimGraphMcpEditor.Build.cs`에 IKRig · IKRigEditor · InterchangeCore · InterchangeEngine · InterchangePipelines · AnimationBlueprintLibrary, `.uplugin`에 IKRig · Interchange 플러그인

완료 기준:

1. **FBX 왕복:** 마켓 UE4 마네킹 계열 애니 1개를 프리뷰 메시째 FBX로 내보낸다(`Saved/AnimGen/Import/`) → 메시·스켈레톤·애니를 허용 경로에 **새로** 임포트(재질·텍스처·피직스 끔) → 새 소스 IK Rig 자동 생성 → `/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F`(대상 메시 `SK_StreetDemon_F_01`)로 리타깃 → 후보 경로에 `AS_` 저장 → `validate_animation`이 `PASSED` 또는 `PASSED_WITH_WARNINGS`. 애셋당 소요 시간을 기록해 `MaxRetargetAssetsPerCall`을 확정한다.
2. **회귀 비교 (FBX 없이):** 기존 RTG의 소스 스켈레톤(`SK_Mannequin_HK` 또는 `HS1`) 애니 1개를 ① 기존 `RTG_KatanaToH` / `RTG_AutoGeneratedHandS`와 ② Tool이 새로 만든 IK Rig·RTG(`ops: match_existing`, 같은 대상 메시 `SK_StreetDemon_F_02`)로 각각 리타깃해 본별 각 차이를 기록한다.
3. 본 이름 비호환 스켈레톤(Narmaya 또는 SB) 1건: 자동 매핑 실패 → 본 계층 응답 → 수동 체인으로 IK Rig 생성까지 성공하거나, 실패 이유를 코드로 반환한다.
4. 허용 목록 밖 Content 패키지가 바뀌지 않았다 — 전역 더티 집합 차이에 허용 목록 밖 항목 0, `git status`의 `Content/` 변경은 허용 경로뿐. (`Saved/` 아래 FBX 쓰기는 테스트 입력이라 제외.)
5. Development · DebugGame 에디터 빌드 경고 0, 기존 Smoke · 런타임 테스트 회귀 없음.

**결과 (2026-10-23, `Tools/mcp/anim_gen_phase1_test.py` 전체 통과 — 요약 `anim_gen_phase1_state.json`):**

| # | 기준 | 결과 |
| :---: | :--- | :--- |
| 1 | FBX 왕복 | ✅ `Katana_Attack_Slash1`(UE4 마네킹 HK, 58프레임) + 프리뷰 메시 → `Saved/AnimGen/Import/` FBX → 메시·스켈레톤·애니 **3개만** 새로 임포트(1.3초, 재질·피직스 0, 재임포트 스켈레톤은 원본과 `same_rig` 0.002°) → 자동 IK Rig ×2 → RTG(`match_existing`) → `SK_StreetDemon_F_01` 로 `AS_Vesper_Katana_Attack_Slash1` 저장 → `PASSED_WITH_WARNINGS`(경고 = 소스에도 있는 109°/프레임 손가락 튐). 상대 비: 각속도 p99 0.933 · 공통 본 0.998 · 착지 발(펠비스 보정) 1.169 · 루트 이동 1.000 · 길이 차 0. 시간: 리타깃 1.6~2.4ms/프레임, 20개 일괄 0.6~1.4초, 검증·저장 포함 3.0초 → 상한 50 |
| 2 | 회귀 비교 | ✅ Tool 이 새로 만든 IK Rig 2개(HK · `F_02`)가 기존 `IK_AutoGeneratedKat`·`IK_AutoGeneratedTargetKat` 와 체인·펠비스·골·솔버까지 같고, `match_existing` RTG 가 `RTG_KatanaToH` 와 op 7개·매핑 28·핀 본 7·루트 모션·자동 정렬 타깃 포즈(34본, 최대 20.234°)까지 같다. 같은 소스 리타깃 결과 **본별 회전 차 0° · 위치 차 0cm**(172본 × 58프레임) |
| 3 | 비호환 스켈레톤 | ✅ Narmaya: auto → `IKRIG_AUTO_FAILED` + 본 343개 계층(애셋 생성 0) → 잘못된 체인 `BAD_CHAINS` → 수동 체인(펠비스 `_000`, 10체인, 골 4) IK Rig 생성 → Vesper RTG 에서 10체인 이름 매핑. 체인 값은 테스트 픽스처로 쓴 제안값이다(기준 포즈 위치로 +X = 왼쪽 판별, 사용자 확인 전) |
| 4 | 허용 목록 밖 무변경 | ✅ 모든 쓰기 호출이 전역 더티 검사 통과(`UNEXPECTED_DIRTY` 0). 실행 끝 미저장 패키지 33개 전부 `GenerationOutputPaths` 안. `/Game/Assets` 스켈레톤에 애니만 임포트해도 그 스켈레톤 더티 아님. `git status` 의 `Content/` 변경은 `Content/Animation/Test/AIAnimation/` 뿐. 가드가 실제로 잡는지는 C++ 단위 테스트(`AnimGraphMcp.Generation.Guard`, 메모리 패키지)로 확인 |
| 5 | 빌드·회귀 | ✅ Development·DebugGame 경고 0. `AnimGraphMcp.Smoke` 26/26 · `AstralBreak.*` 31/31 · 런타임 시나리오(`ABP_McpRuntimeTest` Idle·Run+UpperBody) 2/2. `run_all.py`(저장·재기동 포함 전체 단계 테스트)는 돌리지 않았다 — 운영 애셋을 재저장하는 단계가 있어 기준 4 확인과 섞이지 않게 |

실측으로 바뀐 사실은 감사 문서 §12.

### Phase 2 — 기존 모션 재사용·변형

- `search_animations`: 메타데이터 인덱스(이름 토큰 · 길이 · 루프 · 루트 모션 · 스켈레톤 · 수동 태그). 단순 이름 검색에서 시작하고 자동 태깅은 이후.
- `preview_animation_edits` / `apply_animation_edits`: op 사전(`retime` · `trim` · `mirror` · `offset_bone` · `rotate_root` · `hold_pose` · `concat`), 전체 사전 검증 → 원자 적용.

**시그니처 (개정 5 — 착수 전 확정안):**

| Tool | 입력 | 결과 (`result`) |
| :--- | :--- | :--- |
| `search_animations` | `query?`(이름 토큰 — `_` · CamelCase · 숫자 경계로 쪼개고, 모든 토큰이 이름·폴더 토큰에 접두 일치), `skeleton?`, `path_prefix="/Game"`, `class=AnimSequence\|AnimMontage\|all`, `min_length?`/`max_length?`, `root_motion?`, `additive?`, `loop?`, `tags?[]`, `limit=50`, `details=false`, `max_loads=300` | `total` · `returned` · `truncated` · `items[{asset_path, name, class, skeleton, length, frames, frame_rate, root_motion, additive_type, loop\|null, tags[], score, matched[]}]`. `details`면 노티파이 · 싱크 마커 · 커브 이름 · 루트 이동량·Yaw 변화. `loop` 필터·`details`만 후보를 로드하고 `max_loads` 초과는 `BAD_REQUEST LOAD_LIMIT` |
| `preview_animation_edits` | `source`(AnimSequence — 복제 기준), `operations[]`, `asset_path?`, `loop?`, `root_motion?` | `valid` · `planned[{index, op, ok, error?, range, length_before, length_after}]` · 결과 프레임·길이 · 노티파이 유지/제외 · `seams[]` · `would_create`. 애셋을 만들지 않는다 |
| `apply_animation_edits` | 위 + `asset_path`(필수), `validate=true`, `thresholds?`, `save=false` | 버퍼 계산 실패면 `BAD_REQUEST`(details.planned, 애셋 0개) → 주 소스 복제(허용 목록 · `ASSET_EXISTS`) → 본 트랙·커브·노티파이·싱크 마커 재작성 → 검증(`FAILED`면 저장 안 함, `VALIDATION_FAILED` — Phase 1처럼 미저장으로 남는다) → 전역 더티 검사 → 저장 |

op (시간은 초, 각 op 직전 타임라인 기준. `start`/`end` 생략 = 처음/끝):

| op | 인자 | 동작 |
| :--- | :--- | :--- |
| `trim` | `start?`, `end?` | 구간만 남긴다 |
| `retime` | `start?`, `end?`, `rate` \| `duration` | 구간 재생 속도(1.5 = 1.5배 빠르게). 전체를 재샘플 |
| `hold_pose` | `at`, `duration` | `at`의 포즈를 `duration` 동안 정지 삽입(`at` = 끝이면 연장) |
| `concat` | `asset?`(생략 = 원래 `source`), `start?`, `end?`, `reverse=false`, `blend=0`, `align_root=true` | 같은 스켈레톤 구간을 뒤에 붙인다. `blend`초 크로스페이드, 붙는 구간의 루트를 현재 끝 루트의 위치·Yaw에 맞춘다 |
| `mirror` | `axis="x"`, `mirror_table?` | 전체 좌우 반전 |
| `offset_bone` | `targets[{bone, rotation?{pitch,yaw,roll}, translation?}]`, `space=component\|local`, `start?`, `end?`, `blend_in=0.2`, `blend_out=0.2` | 본 회전·이동 오프셋(상체 회전) |
| `rotate_root` | `yaw`, `start?`, `end?`, `ease=smooth\|linear` | 구간 동안 루트 Yaw 0 → `yaw`, 이후 유지. 루트 이동 증분도 같은 Yaw로 회전 |

- 내장 검증은 상대 비교를 끈다(길이·재생 속도가 바뀌어 프레임 대조가 무의미). 대신 `expect`(길이 · 루프) + `seams` + 물려받은 튐 기준 = 소스의 한 프레임 최대 회전 × 최대 재생 속도.
- 원시 키를 읽으므로 소스의 트랜스폼 커브·본 속성은 결과에 없다(경고 `TRANSFORM_CURVES_DROPPED` · `ATTRIBUTES_DROPPED`). 역재생·잘린 구간의 노티파이는 빠진다(`NOTIFIES_DROPPED`).
- 수동 태그: `[AnimGraphMcp] +AnimationTagFiles=`(프로젝트 기준 상대 경로, JSON — 키는 애셋 경로 또는 `/`로 끝나는 폴더 접두). 애셋 메타데이터에는 쓰지 않는다. 쓰기 Tool은 없다(파일 편집).

완료 기준: 외부 AI 없이 "단순 상체 회전" · "공격 준비·복귀" · "기존 공격 변형(예시 D)" 3건을 새 애셋으로 생성·검증한다. 원본은 바뀌지 않는다.

**결과 (2026-10-23, `Tools/mcp/anim_gen_phase2_test.py` 전체 통과 — 요약 `anim_gen_phase2_state.json`):** 타격 구간은 하드코딩하지 않고 `validate_animation profile_bones["hand_r","hand_l"]`(손 속도가 최대의 50% 이상인 구간, 0.1초 안은 하나로)으로 테스트가 찾는다.

| # | 기준 | 결과 |
| :---: | :--- | :--- |
| 1 | 단순 상체 회전 | ✅ `AS_Vesper_Rifle_AimIdle`(1.33초) → `offset_bone` spine_01~03 각 Yaw 15°(컴포넌트 축), 블렌드 0.3초 → `AS_Vesper_Rifle_AimIdle_TwistL` 저장. `PASSED` · 길이 그대로 · 소스 대비 본별 회전 차 최대 45.0°(p50 30°) · 양 끝 포즈 원본과 같음(경계 0.03°) · 골반·발 속도 차 0.000 cm/s |
| 2 | 공격 준비·복귀 (테스트 A) | ✅ `AS_Vesper_Sickle_Attack3` 첫 타격 0.48초 → `trim` 0~0.433 → `hold_pose` 0.3초 → `concat` 같은 구간 `reverse` → `AS_Vesper_Sickle_AttackReadyReturn` 1.167초 저장. `PASSED` · 첫·끝 포즈 같음(경계 0°, 루트 0.06cm) · 이음매 비 1.23 · 1.25 |
| 3 | 기존 공격 변형 — 예시 D (테스트 B) | ✅ `AS_Vesper_Sickle_Finisher1`(2.4초, 타격 0.20~0.37 · 0.63~0.83초) → `rotate_root` 180°(0.583~0.883) + `retime` 첫 타격 ×1.5 → `AS_Vesper_Sickle_Finisher1_FastSpin` 2.3초 저장. 내장 검증 `PASSED_WITH_WARNINGS`(경고 = `upperarm_twist_01_r` 113.6°/프레임, 기준 소스 82.0° × 1.5 = 123.1° 안 → `ROTATION_JUMP_INHERITED`) · `validate_animation expect{길이 2.311±1프레임 · 루트 Yaw +180 · 루프 아님}` `PASSED` · 첫 타격 손 속도 정점 0.267 → 0.233초 |
| — | 원본 무변경 | ✅ 소스 4개 .uasset SHA-256 실행 전후 동일 · 원본 패키지 더티 0 · 실행 끝 미저장 패키지 48개 전부 `GenerationOutputPaths` 안 · 검색·미리보기는 더티 0 → 0 |
| — | 그 밖 | `search_animations` 13항목(토큰 · 필터 · 태그 · `loop` 로드 20/57 · `LOAD_LIMIT` · `details`) · 미리보기 거부(파싱 오류 5건 한 번에 · `OUT_OF_RANGE` 뒤 `skipped` · `SKELETON_MISMATCH` · `NOT_A_SEQUENCE`) · 적용 거부(`OUTPUT_PATH_NOT_ALLOWED` · 실패 op 면 애셋 0 · `ASSET_EXISTS`) · 미러(좌우 손·발 속도 반올림 0.1 안에서 같음, 루트 Yaw −90 → +90, `MIRROR_CURVES_UNCHANGED`) · 노티파이(×2 리타임 + 트림: 0.5125 · 0.775 → 0.156 · 0.288, 잘린 것은 `NOTIFIES_DROPPED`) · C++ 단위 테스트 `AnimGraphMcp.Generation.Edit` · `Guard` 2/2 |
| — | 빌드·회귀 | Development · DebugGame 경고 0 · `AnimGraphMcp.Smoke` 26/26 · `AstralBreak.*` 31/31 · 런타임 시나리오 2/2 · Phase 1 통합 테스트(`anim_gen_phase1_test.py`) 8섹션 다시 실행 PASS(실패 0 — `validate_animation` 확장 뒤에도 소스 없는 109° 튐은 그대로 `FAILED`) · Phase 2 확인 62건 |

실측으로 바뀐 사실은 감사 문서 §13(미러의 짝 없는 본 · 이음매 비 · 빨라진 동작의 튐 기준 · 리타기터 레시피 차이).

### Phase 3 — anim-gen-mcp: 정책 · 라우터 · 폴백 · Job

- Provider 레지스트리, 규칙 표 라우터, 정책 3모드, `approve_generation`, Job 저장소.
- 실제로 붙이는 Provider: `retarget`(파이프) · `existing_motion` · `direct_key`(Phase 1·2 Tool 조합). `blender` · `local_ai` · `external.meshy` · `control_rig`는 매니페스트와 비활성 자리(`NOT_IMPLEMENTED`)만.
- 별도 MCP 서버 `anim-gen-mcp`(`Tools/mcp/anim_gen/server.py`, `.mcp.json`). 에디터 조작은 `anim_graph_mcp/bridge.py`를 재사용한다.

**시그니처 (개정 6 — 착수 전 확정안):** 모두 같은 봉투를 쓴다.

| Tool | 입력 | 결과 (`result`) |
| :--- | :--- | :--- |
| `list_motion_providers` | `include_inactive=true` | `providers[{name, role(provider\|pipe), phase, capabilities{…}, state{implemented, installed, auth{env, present}, license, available, unavailable_reason}}]` |
| `get_generation_policy` | — | `effective` · `sources{default, local, local_exists}` · `ledger{spent_usd, reserved_usd}` |
| `set_generation_policy` | `patch{}`, `reset=false` | `effective` — 로컬 파일만 쓴다. 모르는 키 · 금지 키 → `BAD_REQUEST` |
| `plan_motion_generation` | `request{}`(§9) | `plan_id` · `executable` · `request`(정규화) · `policy{mode, effective_mode, paid_allowed}` · `candidates[{index, provider, chain[], steps[{step, tool, inputs, resolved}], paid, cost_known, estimated_cost_usd, needs_approval, risks[], expected_limitations[]}]` · `excluded[{provider, cause, reason}]`. 실행하지 않는다 |
| `estimate_generation_cost` | `plan_id` | 후보별 `{provider, paid, cost_known, estimate_usd, basis, verdict: free\|needs_approval\|approved\|blocked, reason}` · `ledger` · `caps{max_cost_per_job_usd, max_total_cost_usd, remaining_usd}` |
| `approve_generation` | `plan_id`, `max_cost_usd`, `max_attempts=1`, `provider?` | `approval_id` · 범위 · `resumed_job_id?`. 거부: `PLAN_NOT_FOUND` · `BAD_REQUEST`(`NO_PAID_STEP` · `POLICY_FREE_ONLY` · `PAID_API_DISABLED` · `AMBIGUOUS_PROVIDER`) · `COST_UNKNOWN` · `BUDGET_EXCEEDED`(`ESTIMATE_OVER_APPROVAL` · `MAX_COST_PER_JOB` · `MAX_TOTAL`) |
| `generate_motion` | `plan_id`, `save=false`, `retry=false` | Job: `job_id, status, provider, chain, generated_assets[], reused_assets[], validation, limitations[], fallback_history[], cost{estimated_usd, actual_usd}`. `SUCCEEDED`일 때만 `ok: true`(비동기 제출은 `ok: true` + `RUNNING`). 승인 대기는 `APPROVAL_REQUIRED`(`details.job`) |
| `get_generation_status` | `job_id?` \| `plan_id?`, `limit=20` | Job 또는 최근 목록. 비동기 단계는 여기서 poll |
| `cancel_generation` | `job_id` | `CANCELLED`(진행 중 외부 단계는 `result_ignored`, 비용은 장부에 남음). 종료된 Job → `BAD_REQUEST ALREADY_TERMINAL` |

완료 기준:

- 에디터 없이 도는 pytest: `FREE_ONLY`에서 유료 경로 차단(Mock Provider), Provider 실패 Mock 시 폴백 기록, Job 상태 전이. §15 테스트 D · E(Mock 단계) 포함.
- 에디터 통합 1건: `existing_motion` 또는 `direct_key` 경로로 실제 애셋 생성까지(`Tools/mcp/anim_gen_phase3_test.py`).
- Phase 1 · 2 통합 테스트 회귀 없음.

**결과 (2026-10-23, pytest 119건 통과 · `Tools/mcp/anim_gen_phase3_test.py` 확인 34건 PASS — 요약 `anim_gen_phase3_state.json`):** C++ 변경 없음. Mock 단계는 FakeEditor(플러그인 봉투·허용 목록·덮어쓰기 없음 흉내) + `local_ai` · `external.meshy` 자리에 끼운 Mock Provider 로 실제 규칙 표를 돌리고, 진짜 브리지·HTTP 호출은 막아 둔다.

| # | 기준 | 결과 |
| :---: | :--- | :--- |
| 1 | pytest — `FREE_ONLY` 유료 차단 (테스트 E Mock) | ✅ `test_cost.py` 17건. `FREE_ONLY` → 계획 제외 `APPROVAL_REQUIRED`(`POLICY_FREE_ONLY`) · `generate_motion` 도 같은 코드 · 승인 거부. 기본 정책은 `PAID_API_DISABLED`. 승인 없음 → `WAITING_FOR_APPROVAL`. 상한 3종 `BUDGET_EXCEEDED`. 비용 미확인 → `COST_UNKNOWN`(승인 거부 · 실행 시 건너뛰기). 승인 뒤 제출 1회, 같은 계획 재호출은 그대로 1회, 재시도는 새 승인 + 키 `plan#2`. 장부에 핸들이 있으면 이어 쓰고, 핸들 없는 예약은 다시 제출하지 않고 `GENERATION_FAILED`(`SUBMISSION_UNCERTAIN`)로 끝낸다. 실제 금액 미확정은 예약으로 남는다. API 키 값은 상태 파일·응답 어디에도 없다. 모든 경우 Mock 외부 호출 수를 확인 |
| 2 | pytest — Provider 실패 시 폴백 기록 (테스트 D Mock) | ✅ `test_fallback.py` 10건. `local_ai` Mock `GENERATION_FAILED` → `existing_motion` 근사 성공, `fallback_history` 1건 + `FALLBACK_USED{from, cause, missing}` + `NOT_NEW_MOTION`. 실행 시점에 비활성이 된 후보는 건너뛰고 기록. 가드 오류(`UNEXPECTED_DIRTY`) · 에디터 끊김은 폴백 없이 중단. `IKRIG_AUTO_FAILED` → `RETARGET_FAILED`(본 계층 보존). 검증 실패가 남긴 이름은 다음 시도가 `_Try<N>` + `OUTPUT_RENAMED`. `RATE_LIMITED`는 같은 후보 재시도. 시도 수 상한 · `allow_fallback=false` · Provider 지정이면 폴백하지 않는다 |
| 3 | pytest — Job 상태 전이 | ✅ `test_jobs.py` 48건. 6×6 전이 표 전부(허용 9 · 금지 27), 상태는 `transition`으로만, 같은 초에 만든 Job · 승인도 생성 순서. 성공 · 실패 · `retry` · 재사용 · 취소(대기 · 비동기 실행 중 → 결과 무시 · 비용 유지) · 서버 재시작 뒤 파일에서 이어 poll · 에디터 없이 만든 계획을 실행 시 해결. 그 밖에 정책 17 · 라우터·요청 24 · 서버 3 |
| 4 | 에디터 통합 1건 | ✅ `generate`: `idle` 요청 + 검색 `rifle aim idle` → 계획이 `AS_Vesper_Rifle_AimIdle`을 고정 → `direct_key` `offset_bone`(spine_01~03 각 Yaw 15°) → `/Game/Animation/Test/AIAnimation/P3Run…/AS_Vesper_Rifle_AimIdle_TwistP3` 저장. `QUEUED → RUNNING → SUCCEEDED` 0.6초, 내장 검증 `PASSED`, 소스 대비 본별 회전 차 p50 30° · 최대 45°(Phase 2 기준 1과 같은 값) · 길이 그대로. 같은 계획 재호출 = 같은 Job |
| — | 그 밖 (통합) | `mcp`: stdio 로 서버를 띄워 Tool 9개 · 계획 봉투(에디터는 `bridge.py` 경유). `plan`: 미리보기 고정 · 제외 사유 · 허용 목록 밖 `OUTPUT_PATH_NOT_ALLOWED` · `FREE_ONLY` · 계획은 애셋 0 · 더티 0. `retarget`: UE4 HK `Katana_Attack_Slash1` 참조 → 소스 메시(스켈레톤 프리뷰 `SK_Mannequin_HK`)를 계획에 고정 → IK Rig ×2 · RTG `match_existing` · 리타깃 → `AS_Vesper_Katana_Slash1P3` 저장 2.2초, `PASSED_WITH_WARNINGS`, `GRIP_NOT_VALIDATED`. `reuse`: 애셋 0. `dirty`: 원본 SHA-256 불변 · 미저장 0 → 0 · `Content/` 변경은 이번 실행 폴더뿐 |
| — | 회귀 | ✅ C++ 변경이 없어 빌드는 생략. 같은 에디터에서 `anim_gen_phase1_test.py` 확인 113건 · `anim_gen_phase2_test.py` 확인 62건 모두 실패 0(그 안의 `AnimGraphMcp.Smoke` 26/26 · `AstralBreak.*` 31/31 · 런타임 시나리오 통과). Phase 3 테스트가 저장한 IK Rig 가 `inspect_skeleton.ik_rigs` 후보 목록에 보인다(정리 전까지 — 재사용은 명시할 때만이라 동작 영향 없음) |

통합 테스트에서 고친 것: 요청 유형(`weapon_action`)과 제약(`two_hand_weapon_grip`)이 `GRIP_NOT_VALIDATED`를 두 번 냈다 → 같은 코드는 하나로(처리 못 하는 제약 `CONSTRAINT_UNSUPPORTED`만 제약마다). 마지막 통합 실행 뒤에 고쳤고, 같은 요청의 읽기 전용 계획으로 하나만 남는 것을 에디터에서 다시 확인했다. 그 뒤 pytest 반복 실행에서 간헐 실패 1건: 같은 초에 만든 Job 두 개(실패 → `retry`)의 "최신"을 초 단위 시각 + 무작위 id 로 정해 이전 `FAILED` Job 이 돌아왔다 → 프로세스 안에서 단조 증가하는 나노초 순서(`created_ns`)로 정렬(Job · 승인). 회귀 테스트 추가 후 해당 테스트 20회 · 전체 3회 연속 통과.

### Phase 4 — Blender Provider (선택)

headless 실행, BVH → FBX, 결과는 Phase 1 처리로 넘긴다. C++ 변경 없음(플러그인 Tool 그대로).

**구성 (개정 7):**

| 파일 | 내용 |
| :--- | :--- |
| `Tools/mcp/anim_gen/bvh.py` | BVH 헤더·데이터 행 검사 · 기준 포즈 · 단위 추정 · 정면(발 영역 벡터 합, 외톨이 본 제외 · 좌우 체인 교차 확인 `lateral_facing` · UE Yaw `ue_yaw_deg`) · 축 변환 · 범위. 순수 Python — 계획 단계와 pytest 가 Blender 없이 쓴다 |
| `Tools/mcp/anim_gen/providers/blender.py` | `BlenderProvider`: `installed`(정책 경로) · `plan_convert`(헤더 · 단위 · 회전 · 범위 · fps · SHA-256 고정, Blender 를 띄우지 않음) · `run`(Popen → pending) · `poll`(report · 기한) · `cancel`(종료) |
| `Tools/mcp/anim_gen/blender/bvh_to_fbx.py` | Blender 안에서 도는 스크립트 — args.json 을 받아 적용만 한다. report.json 은 실패해도 쓴다(종료 코드 0 / 2 알려진 실패 / 3 예외) |
| 그 밖 | `router`(motion_file 이면 blender 맨 앞 · 변환 사슬) · `request`(`motion_file`) · `policy`(`subprocess_timeout_seconds`) · `executor`(실행 컨텍스트에 정책 · 같은 한계 하나로) · `service`(취소 시 `Provider.cancel`) · `builtin`(import `sample_rate`) · `fallback`(motion_file 폴백 문구) · `providers.json` |

변환 산출물: `<ImportSourceRoots[0]>/Blender/<job_id>/A<n>/{args.json, BVH_<파일>.fbx, report.json, blender.log}`. UE 이름(Phase 1 규칙): 메시 `BVH_<파일>` · `_Skeleton` · `_Anim` → `<output_path>/Work/<job_id>/A<n>/Import/`.

**Blender 설정:** 실행 `blender -b --factory-startup --python-exit-code 3 -P bvh_to_fbx.py -- args.json`(stdin 막음 · 출력은 `blender.log` · `CREATE_NO_WINDOW` · 키 이름 환경 변수 제외). 장면 METRIC `scale_length` 0.01. BVH 임포트 `global_scale` = cm/단위 · `rotate_mode` NATIVE · `use_fps_scale` false · fps 갱신(±0.05 안이면 정수로 맞춤). 범위 = 요청 `range`, 요청 `frame_rate` 가 있으면 끝을 그 rate 의 프레임 경계로(임포트 `sample_rate`). 정면 Z 회전 → 회전만 적용. 바닥 맞춤(가장 낮은 점 z = 0, 루트 위치 키 보정). 객체 이름 `Armature`. 본마다 기둥 8정점(폭 = max(0.5 cm, 길이 8%), 그 본 가중치 1.0). FBX: `ARMATURE`+`MESH` · `apply_unit_scale` · `FBX_SCALE_NONE` · −Z/Y · `add_leaf_bones` false · `use_armature_deform_only` false · `use_mesh_modifiers` false · NLA·모든 액션 끔 · 시작·끝 키 강제 · 키 간소화 0.

완료 기준:

1. 공개 BVH 1건 → `/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F`(대상 메시 `SK_StreetDemon_F_01`) `AS_` 애셋 저장 + `validate_animation` 결과.
2. 에디터 없이 도는 pytest: Blender 서브프로세스 Mock — 실행 파일 없음 · 실패 · 타임아웃 · 취소 · 폴백 기록.
3. 실제 Blender 통합 1건(`Tools/mcp/anim_gen_phase4_test.py`).
4. 기존 pytest · Phase 1 · 2 · 3 통합 테스트 회귀 없음.

**결과 (2026-10-24, `Tools/mcp/anim_gen_phase4_test.py` CMU 01_01 전 섹션 PASS — 요약 `anim_gen_phase4_state.json`):** 공개 BVH = CMU Graphics Lab 피험자 01 · 테이크 01 "playground — forward jumps, turn around"(cgspeed BVH 변환, assimp 저장소 테스트 모델, 2,070,355 B, 사용자 승인 다운로드 → `Saved/AnimGen/Import/Sources/CMU_01_01/`). CMU 조건: 상업 제품 포함 사용 가능 · 데이터 재판매 금지 · 출판 시 인용 요청.

| # | 기준 | 결과 |
| :---: | :--- | :--- |
| 1 | 공개 BVH → Vesper `AS_` + 검증 | ✅ 관절 31 · 2,752프레임 @ 120 fps(22.9초). 계획: 단위 모름 → 키 170 cm 정규화(cm/단위 6.627, `SCALE_NORMALIZED`), 소스 정면 +Y(편차 0.06°) = Vesper +Y → 회전 0, 30 fps 경계로 끝 3프레임 당김. 실행: Blender 4.4~5.5초(바닥 맞춤 108 cm · 루트 −115 → +255 cm 앞으로) → 임포트(본 31 · 루트 `Hips` · 스케일 1 · 최저 0 · 골반 108 cm · +Y) → 수동 체인 9개(골반 `Hips`) IK Rig + Vesper 자동 IK Rig + RTG `match_existing` → **`/Game/Animation/Test/AIAnimation/P4Run1024_003026/AS_Vesper_Mocap_ForwardJumpP4` 저장**(688프레임 @ 30 fps), 작업 전체 9.8초. `validate_animation`(임포트 소스 대비): **`PASSED_WITH_WARNINGS`** — 경고 1건 `ROTATION_JUMP_INHERITED`(프레임 1, 179.8° — 소스도 같음), 상대 비 각속도 p99 0.833 · 골반 높이 0.975 · 착지 발 1.513 · 루트 이동 1.299 · 길이 차 0(모두 허용 범위). 원인 = cgspeed CMU BVH 의 0번 프레임이 회전 거의 없는 기준 포즈(73채널 중 4개만 0 아님) → `motion_file.range.start` = 1프레임이면 **`PASSED`**(최대 50.4°/프레임, 구조 경고 0 — `…ForwardJumpP4Trim`). 체인 없이 자동 IK Rig 도 **HumanIK / Motionbuilder 템플릿 64%** 로 성공(`PASSED_WITH_WARNINGS`) |
| 2 | pytest (Mock) | ✅ 189건(기존 119 + `test_bvh.py` 40 + `test_blender.py` 30). 실행 파일 없음(계획 제외 · 명시 Provider · 실행 시점 사라짐 → 건너뛰기 + 폴백 기록) · 성공(명령줄 · stdin 막음 · 키 환경 변수 제외 · args · 출력 위치 · import `sample_rate`) · report 오류 → 폴백 `FALLBACK_USED`(motion_file 이름) · 보고 없이 종료 `BLENDER_EXIT_3` · FBX 없음 `NO_OUTPUT` · 타임아웃(프로세스 종료) · 취소(종료 · 이후 poll 없음) · 서버 재시작(report 로 이어짐 / 기한 지나면 `TIMEOUT`) · 파일 변경 `FILE_CHANGED`(폴백 없음) · 루트 밖 · 형식 · 깨진 BVH · 범위 정렬 · 정수 아닌 fps · 요청 검증 · 정책 키 |
| 3 | 실제 Blender 통합 | ✅ CMU · 합성 BVH(`--bvh synthetic`) 모두 전 섹션 PASS. 실제 프로세스 취소 종료(report 없음) · 대상 스켈레톤 · 메시 .uasset SHA-256 불변 · 미저장 패키지 수 그대로 · `Content/` 변경은 실행 폴더뿐 |
| 4 | 회귀 | ✅ 같은 에디터에서 `anim_gen_phase1_test.py` · `phase2` · `phase3` 실패 0(범위 정렬 수정 뒤 `phase3` 다시 실행). C++ 변경 없음 — 빌드 생략 |

통합 테스트에서 고친 것: 처음 CMU 실행은 `IMPORT_FAILED NO_ANIMATION` — Interchange 가 30 fps 리샘플에서 경계에 안 맞는 길이(687.75프레임)의 애니를 건너뛰었다(§2.3). blender 가 굽기 범위 끝을 요청 rate 의 경계로 당기게 하고(`bvh.align_to_rate`), 맞출 수 없는 정수 아닌 fps 는 리샘플하지 않는다. 그 밖에 스파이크에서 고친 것: Blender BVH 임포터 첫 키 1(프레임 정렬), `Armature.transform` 뒤 포즈 평가 갱신, 기준 포즈 바닥 맞춤(감사 §14).

### Phase 5 — 로컬 AI (선택, 라이선스 게이트)

조사 문서 `Docs/AIAnimation/LocalModelSurvey.md`를 쓴다. 모델별로 코드 라이선스 · 가중치 라이선스 · 학습 데이터 조건 · 지역 제한 · VRAM · Windows 호환 · 출력 리그를 정리한다.

완료 기준: 적법하고 호환되는 모델이 있으면 생성 → `AS_`까지 실행한다. 없으면 조사 문서 + Provider 비활성 유지가 정상 완료다.

### Phase 6 — 외부 AI (Meshy)

어댑터, 비용 추정(공식 가격을 확인할 수 없으면 승인 단계에서 "미확인"으로 차단), 결과 다운로드·만료 처리, 폴백 통합.

완료 기준:

- 승인된 경우에만 1건을 생성하고, Phase 1 처리를 거쳐 검증한다.
- 승인이 없거나 `FREE_ONLY`이면 외부 호출 0회(요청 로그로 확인).

### Phase 7 — AnimBP 연결 · 승격

기존 Tool 조합 + `promote_animation`.

완료 기준: 생성 → 몽타주/BlendSpace → (요청 시) ABP 연결을 독립 또는 연속으로 실행한다.

### Phase 8 — 품질 · 세그먼트

세그먼트 생성·연결, 손 IK·무기 파지 보정(`control_rig`), 프리뷰 프레임 캡처, 다양한 스켈레톤.

---

## 15. 테스트 시나리오

| 원본 | 개정 | Phase | 종류 |
| :--- | :--- | :---: | :--- |
| A 무료 기본 동작 | 기존 공격에서 트림·편집으로 공격 준비·복귀 생성 | 2 | 에디터 통합 |
| B 기존 모션 수정 | 그대로 + 원본 패키지 해시 불변 확인 | 2 | 에디터 통합 |
| C 커스텀 스켈레톤 | Narmaya 또는 SB ↔ `SKEL_UE5_F`, 수동 체인 폴백 포함 | 1 | 에디터 통합 |
| D 폴백 | Mock Provider 실패 → 다른 Provider · 경로 기록 | 3 | Mock (pytest) |
| E 비용 통제 | `FREE_ONLY` + 유료 요청 → `APPROVAL_REQUIRED`/`BUDGET_EXCEEDED`, 외부 호출 0 | 3 · 6 | Mock → 실제 어댑터 |
| F AnimBP 연결 | 명시 요청 시에만 기존 AnimBP MCP로 연결 | 7 | 에디터 통합 |
| (신규) G 회귀 비교 | Tool이 만든 리타기터 결과 vs 기존 RTG 결과 | 1 | 에디터 통합 |

- Mock 테스트와 실제 에디터 통합 테스트를 구분한다(원본 유지).
- Python 통합 테스트는 `Tools/mcp/`의 기존 방식(`phaseN_test.py` + `*_state.json`)을 따른다.

---

## 16. 원칙과 금지 사항

원본 12개:

1. 기존 AnimBP MCP를 불필요하게 다시 쓰지 않는다.
2. 기존 스켈레톤과 원본 애니메이션을 기본적으로 수정하지 않는다.
3. UE 5.7.4에서 확인하지 않은 API를 가정하지 않는다. §2.3 표에 없는 API는 헤더를 확인한 뒤 표에 추가하고 쓴다.
4. 로컬 모델의 라이선스와 지역 제한을 무시하지 않는다.
5. 승인되지 않은 외부 유료 API를 호출하지 않는다.
6. 무료 폴백이 원 요청과 같은 품질을 보장한다고 주장하지 않는다.
7. 특정 AI Provider를 필수 의존성으로 만들지 않는다.
8. 스켈레톤 정보만으로 무기 제약을 다 파악할 수 있다고 가정하지 않는다.
9. 애셋 생성 성공과 시각 품질 검증 성공을 혼동하지 않는다.
10. 에디터 전용 제작 기능을 런타임 모듈에 넣지 않는다.
11. 외부 서비스에 캐릭터 데이터나 애셋을 보낼 때는 그 서비스의 데이터 정책을 확인한다.
12. 미완성 기능이나 Mock 동작을 실제 구현 완료로 보고하지 않는다.

추가:

13. 기존 응답 봉투와 오류 체계를 깨지 않는다.
14. 게임 스레드에서 네트워크 호출·서브프로세스·대기를 하지 않는다.
15. `anim_graph_mcp/server.py`에 로직을 넣지 않는다(프록시만).
16. API 키를 저장소·로그·Tool 인자·Job 기록에 남기지 않는다(환경 변수만).
17. 생성물은 허용 목록 경로에만 쓴다. 정식 경로 이동은 사용자 확인 후.
18. 플러그인에 프로젝트 고유 이름·경로를 하드코딩하지 않는다.

---

## 17. Claude Code 작업 지시

1. 한 번에 한 Phase만 진행한다(Phase 0 · 1 · 2 · 3 · 4 완료). 다음 Phase는 사용자 승인 후 착수한다.
2. 각 Phase는 코드 편집 전에 Tool 시그니처 · 커밋 단위 · 구현 순서를 보여 주고 **사용자 확인을 받는다.** 문서와 엔진 API가 어긋나면 문서 수정안을 함께 낸다.
3. 에디터 확인용 애셋은 `/Game/Animation/Test/AIAnimation/`에 만들고, 끝나면 정리 목록을 보고한다.
4. 순서: 구현 → 정적 검증(두 구성 빌드 · Python 문법) → 에디터 통합 테스트(`Tools/mcp/anim_gen_phaseN_test.py`) → 결과 기록.
5. 보고에 포함할 것(원본 유지): 수정·추가된 파일 · 새 MCP Tool · 구현된 기능 · 실제 테스트 여부 · 실패·미검증 사항 · 기존 AnimBP MCP에 미친 영향 · 후속 Phase 작업. 여기에 **그 Phase 완료 기준 각각의 충족 여부**를 더한다.

---

## 부록 A. 출처

- 엔진 소스: `D:/UnrealSource/UnrealEngine-5.7.4-release/Engine/` 아래, §2.3 표의 경로
- 기존 플러그인: [Plugins/AnimGraphMcp/README.md](../../Plugins/AnimGraphMcp/README.md) · `Tools/mcp/anim_graph_mcp/server.py` · `bridge.py`
- HY-Motion 1.0 라이선스: <https://raw.githubusercontent.com/Tencent-Hunyuan/HY-Motion-1.0/master/License.txt> · <https://huggingface.co/tencent/HY-Motion-1.0>
- Meshy Text-to-Motion API: <https://docs.meshy.ai/vi/api/text-to-motion>
- DeepMotion SayMotion REST API: <https://github.com/DeepMotion/SayMotion-REST-API> · <https://deepmotion.com/post/saymotion-api-now-available-for-free-trials>

## 부록 B. 미확인 항목

| 항목 | 확인 시점 |
| :--- | :--- |
| ~~Interchange로 애니만 기존 스켈레톤에 임포트하는 파이프라인 설정 키~~ | Phase 0 확인 (감사 §1) |
| ~~비표준 스켈레톤(Narmaya · SB)에 대한 자동 캐릭터라이즈 결과~~ | Phase 0 확인 — 전부 실패 (감사 §2) |
| ~~5.7 리타기터 기본 op 목록~~ | Phase 0 확인 — `AddDefaultOps` 5개, 기존 RTG는 Pin Bones 추가 7개 (감사 §4) |
| ~~임포트가 기존 스켈레톤을 수정하는지~~ | 문서 검토에서 확인 — 커브 메타데이터 추가 시 더티, `bAddCurveMetadataToSkeleton=false`로 차단 |
| ~~동기 Interchange 임포트를 게임 스레드 HTTP 핸들러에서 대기해도 되는지~~ | Phase 1 확인 — 정상(메시째 1.3초) |
| ~~일괄 리타깃 애셋당 소요 시간~~ | Phase 1 확인 — 1.6~2.4ms/프레임, 상한 50 |
| ~~상대 검증 허용 비율 초기값~~ | Phase 2 확인 — 3계열 9건(UE4 HK · HS1 · UE5 Manny)이 모두 초기값 안(공통 본 각속도 p99 비 1.00~1.05 · 착지 발 0.94~2.26 · 루트 1.00) → 유지 (감사 §13) |
| ~~루트 op 기본값과 Run IK Rig 활성 여부의 품질 차이~~ | Phase 2 측정 — `default`(Run IK Rig 켬)는 IK 본·손 위치를 바꾼다(본별 회전 차 p50 6.6° · p99 98.7°), Narmaya 에서는 179°/프레임 뒤집힘으로 `FAILED`. 생성 흐름은 `match_existing` 이 기준 (감사 §13) |
| 얼굴 방향이 다른 스켈레톤(Narmaya) 리타깃 품질 | Phase 2 — `match_existing` 이면 자동 검증 `PASSED`(각속도 비 1.09, 최대 12°/프레임). **사람의 시각 확인은 남음** — 테스트 산출물은 정리했으므로 `anim_gen_phase2_test.py --only appendix` 로 다시 만들어 본다. 개정 7: Vesper 정면은 −Y 가 아니라 **+Y**(기준 포즈 `foot_l` → `ball_l`)로 정정. **개정 7 보강(2026-10-24) — 해결:** 소스 스켈레톤 12개 실측 — Vesper · IdaFaber M · UE4 마네킹 4 · UE5 Manny 2 · Greystone · Narmaya `pl1400`/`fp1400` = +Y, **SB `CH_P_EVE_01_Body` 만 +X**(3ds Max Biped, 왼쪽 −Y. 예전 `bvh.facing` 은 FX 본 z −2217cm 때문에 발 선분 0개 → 외톨이 제외로 해결). **Narmaya 는 Vesper 와 정면이 같다**(발 `_014` → `_015` +Y, 왼팔 +X) — "Narmaya ↔ Vesper 정면 차이"는 Vesper −Y 오기에서 나온 것. 소스 리타깃 포즈 루트 회전은 소스 현재 포즈에 걸리지 않아 결과가 소스 정면을 보므로(§2.3) 리타기터 대상 쪽에서 맞춘다(§10 `facing_yaw_deg`). SB `Evefin`(10.4초) → Vesper 손 궤적(펠비스 기준, 각자 몸 좌표): 맞춤 전 주축 각 85° · 44°, 소스의 앞뒤가 Vesper 의 좌우로 감(소스 앞 ↔ 대상 왼쪽 상관 0.98 · 0.97 — 세계 방향을 그대로 따름) → 맞춤 후 주축 각 15° · 13°, 몸 좌표 앞 · 왼쪽 상관 0.96 ~ 0.996, 출력 정면 +Y · 루트 원점 유지(정면이 같은 Narmaya 기준선 7 ~ 8°). 자동 검증은 맞춤 전후 둘 다 `PASSED`(각속도 비 0.896) — **평면 오류는 상대 비율 검증으로 안 보인다**. 계획은 SB 에 위험 `FACING_DIFFERS` + 한계 `FACING_ALIGNED`(yaw +90), Narmaya 는 정면 위험 없음. **사람의 시각 확인은 남음** — `/Game/Animation/Test/AIAnimation/FacingRun1024_012108/{Before,After}/AS_Facing_Evefin`(저장) |
| ~~오래된 버전으로 저장된 마켓 애셋에 "Number of Frames" · "Source Frame Rate" 레지스트리 태그가 있는지~~ | Phase 2 확인 — 마켓 시퀀스 1,237개 전부 있음 |
| ~~Blender 출력의 단위·축~~ · Meshy 출력의 단위·축 | Blender — Phase 4 확인(§2.3 · §10). Meshy — Phase 6 |
| ~~`import_animation_file` + `sample_rate` 의 경계 안 맞는 길이~~ | Phase 4 발견(Interchange 가 애니를 건너뛰어 `IMPORT_FAILED NO_ANIMATION`) → 개정 7 보강 2 해결 — `ConfigurePipeline` 이 `bSnapToClosestFrameBoundary` 를 항상 켜고, 맞춘 트랙은 `warning LENGTH_SNAPPED`. 경계 안 맞는 CMU 01_01 FBX `sample_rate=30` → 689키 · 22.9333초(§2.3). 다른 FBX(Meshy 등)도 같은 경로로 임포트된다. blender 의 범위 정렬(`bvh.align_to_rate`)은 그대로 둔다(반 프레임 늘림·줄임 없이 소스 프레임 그대로 — `RANGE_ALIGNED` 문구도 이에 맞춰 정정). 생성 잡도 이 진단을 받는다 — 실행기가 단계 안 에디터 진단을 `tool` · `step` 과 함께 Job `diagnostics` 에 남긴다(§3.4) |
| cgspeed CMU BVH 의 0번 프레임 | Phase 4 확인 — 회전 거의 없는 기준 포즈(T 비슷)라 1번 프레임에 최대 179.8° 튐(`ROTATION_JUMP_INHERITED`). `motion_file.range.start` = 1프레임으로 뺀다. 다른 CMU 클립도 같은 형식일 것(미확인) |
| Meshy 길이 범위 · 가격 · 결과 파일 만료 · 데이터 정책 | Phase 6 |
| 공개 Text-to-Motion 모델의 학습 데이터 라이선스 | Phase 5 |
