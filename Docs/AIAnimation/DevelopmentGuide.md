# AI 애니메이션 생성 자동화 — 개발 지침서

작성일: 2026-10-23 (원본: "AI Animation Generation Automation — Claude Code 최종 개발 지침서")  
개정 1: 2026-10-23 — 기존 AnimGraphMcp 코드 · UE 5.7.4 엔진 소스 · 외부 서비스 문서와 대조한 검토 반영.  
개정 2: 2026-10-23 — Phase 0 감사(에디터 읽기 전용 실측) 결과 반영. 히어로 스켈레톤 경로 정정, 일괄 리타깃·Interchange 위험 설정, 수치 검증을 상대 비교로 전환.  
개정 3: 2026-10-23 — 문서 검토 18건 반영. 생성 흐름의 원본 제자리 수정 분기 제거, 임포트의 스켈레톤 부작용 차단, 전역 더티 검사, 명시적 재사용, 설정 단일 기준.  
개정 4: 2026-10-23 — Phase 1 구현·실측 결과 반영(§14 Phase 1 결과, 부록 B). 상한 50, 물려받은 회전 튐, `match_existing` = 에디터 자동 리타깃 레시피.  
개정 5: 2026-10-23 — Phase 2 착수 전 엔진 소스 대조. 키 작성 순서·프레임레이트 제약, 복제 경로, 미러, 레지스트리 태그, Phase 2 Tool 시그니처·op 의미·원자성 정의. 같은 날 Phase 2 결과(§14 Phase 2 결과 · 부록 B) 반영.  
상태: Phase 1 · Phase 2 구현·검증 완료(§14). 다음 = Phase 3.  
관련 문서: [AnimGraphMcp README](../../Plugins/AnimGraphMcp/README.md) · [Phase 0 감사](ArchitectureAudit.md)

| 항목 | 내용 |
| :--- | :--- |
| 환경 | Windows 11 · UE 5.7.4 소스 빌드 · C++ · Python 3.13 · Claude Code · MCP |
| 구조 | Multi-Provider + 규칙 기반 라우터 + 폴백 + 공통 리타깃 처리 + 기존 AnimBP MCP 연결 |
| 기본 정책 | Free-First · 유료 API는 명시 승인 · 비파괴 · Editor 전용 |

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
| Blender | 4.4, `C:\Program Files\Blender Foundation\Blender 4.4\` (PATH에 없음) |
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
- 오류 코드는 기존 체계(HTTP 상태 + 코드)에 추가한다. 예: `IMPORT_FAILED` · `IKRIG_AUTO_FAILED` · `RETARGET_FAILED` · `VALIDATION_FAILED` · `OUTPUT_PATH_NOT_ALLOWED` · `UNEXPECTED_DIRTY` · `PROVIDER_UNAVAILABLE` · `APPROVAL_REQUIRED` · `BUDGET_EXCEEDED` · `LICENSE_RESTRICTED`.

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
  - 필드: id, provider, 현재 단계, 비용(추정/실제), 결과 파일, 오류 코드, retry_count, fallback_history, approval_id
- **취소:** 취소가 Provider 실행의 즉시 중단을 뜻하지 않는다. 외부 작업은 "결과 무시"로 처리하고, 이미 발생한 비용은 장부에 남긴다.

---

## 4. Provider

| Provider | 하는 일 | Phase | 기본 상태 |
| :--- | :--- | :---: | :--- |
| `retarget` (파이프) | 공통 처리 계층 — 모든 Provider 결과가 지난다 | 1 | 활성 |
| `existing_motion` | 메타데이터 인덱스로 검색 → 리타깃 → 편집 | 2 | 활성 (주 경로) |
| `direct_key` | `IAnimationDataController`로 키 작성: 리타임 · 트림 · 미러 · 본 오프셋 · 루트 Yaw · 포즈 유지 · 구간 연결 | 2 | 활성 |
| `blender` | headless(`blender -b -P`)로 BVH → FBX 변환, 아마추어 편집, FBX 내보내기 | 4 | 실행 파일 감지 시 활성 |
| `local_ai` | 라이선스 게이트를 통과한 모델만 | 5 | 비활성 |
| `external.meshy` | text-to-motion → FBX → 리타깃 | 6 | 비활성 (유료, 승인 필수) |
| `control_rig` | 손·무기 파지, 발 고정 같은 제약 보정 베이크 | 8 | 비활성 |

- **Motion Primitive** 개념은 유지하되 Phase 2에서는 `direct_key` 편집 op(`retime` · `trim` · `mirror` · `offset_bone` · `rotate_root` · `hold_pose` · `concat`(+ `reverse` 옵션))로 한정한다.
- **Phase 2와 Phase 3의 경계:** Phase 2는 Provider가 부를 에디터 Tool(`search_animations` · `preview/apply_animation_edits`)만 만든다. `existing_motion` · `direct_key`를 Provider로 등록하는 것은 `anim_gen`(Phase 3)이다. `StepForward` · `JumpArc` 같은 전신 Primitive로 새 전신 모션을 짓는 것은 Phase 8 실험 항목이고, 품질 기대치가 낮다는 점을 결과에 명시한다.
- **Capability**는 원본 목록(입력 유형, 신규 생성 지원, 수정 지원, 커스텀 스켈레톤 지원, 출력 포맷, 최대 길이, GPU 필요, 네트워크 필요, 유료 여부, 비용 추정 가능 여부, 라이선스 상태, 설치·인증 상태)을 Provider 매니페스트 데이터로 둔다.

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

---

## 6. 비용·실행 정책

원본의 세 모드(`FREE_ONLY` · `FREE_FIRST`(기본) · `QUALITY_FIRST`)와 의미를 유지한다. 바뀌는 점:

- **정책 파일:** 기본값 `Tools/mcp/anim_gen/policy.default.json`(추적) + 로컬 덮어쓰기 `Saved/AnimGen/policy.json`(추적 안 함).
- **API 키:** 환경 변수(`MESHY_API_KEY` 등)로만 받는다. 저장소, Tool 인자, 로그, Job 기록에 키를 남기지 않는다.
- **승인:** `approve_generation(plan_id, max_cost_usd, max_attempts)`. 승인 범위는 한 계획의 지정 Provider 호출 횟수(재시도 포함) + 금액 상한이다. 범위를 넘는 재시도는 새 승인이 필요하다.
- **중복 과금 방지:** 유료 제출은 `(plan_id, attempt)`를 멱등 키로 쓴다. 같은 키로 다시 요청하면 기존 Job을 돌려준다.
- **비용을 확인할 수 없는 유료 요청은 실행하지 않는다.** 금액을 임의로 계산해 확정하지 않는다.
- **정책 파일에 두지 않는 것:** 출력 경로(ini `GenerationOutputPaths`가 유일한 기준)와 덮어쓰기 허용(C++가 항상 금지 — 정책으로 켤 수 없다).

```jsonc
{
  "mode": "FREE_FIRST",
  "billing": { "paid_api_enabled": false, "require_explicit_approval": true, "max_cost_per_job_usd": 0, "max_total_cost_usd": 0 },
  "execution": { "max_generation_attempts": 3, "allow_fallback": true, "preserve_intermediate_results": true },
  "paths": {
    "blender_executable": "C:/Program Files/Blender Foundation/Blender 4.4/blender.exe"
  }
}
```

---

## 7. 폴백

원본의 실패 원인 분류를 유지하고 `APPROVAL_REQUIRED`를 추가한다.

```text
PROVIDER_UNAVAILABLE · AUTHENTICATION_FAILED · APPROVAL_REQUIRED · BUDGET_EXCEEDED · RATE_LIMITED · LICENSE_RESTRICTED
UNSUPPORTED_REQUEST · GENERATION_FAILED · IMPORT_FAILED · RETARGET_FAILED · VALIDATION_FAILED · QUALITY_INSUFFICIENT
```

다른 Provider로 넘어가려면 아래를 모두 만족해야 한다(원본 유지):

- 비용 정책을 위반하지 않는다.
- 그 Provider가 요청을 처리할 수 있다.
- 라이선스상 쓸 수 있다.
- 리타깃이 가능하다.
- 최대 시도 횟수를 넘지 않았다.

이미 만든 유효한 결과는 후보로 보존한다(`preserve_intermediate_results`). **폴백 결과는 `limitations[]`에 원 요청 대비 무엇이 빠졌는지 반드시 적고**, 원 요청을 완전히 충족한 결과로 보고하지 않는다.

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
  "target_mesh": null,                       // 리타깃 대상 메시 (생략 시 스켈레톤의 첫 메시)
  "hero": "Vesper",                          // 이름 토큰
  "family": "Sickle",                        // 이름 토큰
  "animation_name": "AS_Vesper_Sickle_SpinSlash",
  "description": "낫을 양손으로 잡고 회전하며 3번 베는 공격",
  "motion_category": "combat",
  "duration_seconds": 3.0,
  "frame_rate": 30,
  "loop": false,
  "root_motion_mode": "auto",
  "reference_animations": [],                // 기존 모션 힌트 (선택)
  "constraints": { "two_hand_weapon_grip": true, "foot_contact": true, "smooth_start_end": true },
  "generation_policy": "FREE_FIRST",
  "provider": "auto",
  "integrate_anim_bp": false,
  "output_path": "/Game/Animation/Generated/Vesper"
}
```

Provider가 지원하지 않는 제약은 후처리로 해결 가능한지 따지고, 해결할 수 없으면 무시하지 않고 `limitations[]`에 기록한다.

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
| 요청 충족 | 길이·루프 조건 · 요청한 순서(세그먼트 경계) · 제약 충족. Phase 2: `expect{length, loop, root_yaw_delta}` 불일치 → `FAILED`(`EXPECT_*`), `seams[]`(이음매 시각)의 회전 변화가 앞 · 뒤 4프레임 중앙값 중 큰 쪽의 `seam_ratio_max`(3.0)배 초과 → 경고 `SEAM_JUMP`. 구간을 고르는 측정용 `profile_bones[]`(프레임별 본 선속도) | 2 · 8 |
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

완료 기준:

- 에디터 없이 도는 pytest: `FREE_ONLY`에서 유료 경로 차단(Mock Provider), Provider 실패 Mock 시 폴백 기록, Job 상태 전이.
- 에디터 통합 1건.

### Phase 4 — Blender Provider (선택)

headless 실행, BVH → FBX, 결과는 Phase 1 처리로 넘긴다.

완료 기준: 공개 BVH 1건 → `SKEL_UE5_F` `AS_` 애셋.

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

1. 한 번에 한 Phase만 진행한다(Phase 0 · 1 완료, 현재 **Phase 2**). 다음 Phase는 사용자 승인 후 착수한다.
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
| 얼굴 방향이 다른 스켈레톤(Narmaya 발끝 +Y, Vesper −Y 쪽) 리타깃 품질 | Phase 2 — `match_existing` 이면 자동 검증 `PASSED`(각속도 비 1.09, 최대 12°/프레임). **사람의 시각 확인은 남음** — 테스트 산출물은 정리했으므로 `anim_gen_phase2_test.py --only appendix` 로 다시 만들어 본다 |
| ~~오래된 버전으로 저장된 마켓 애셋에 "Number of Frames" · "Source Frame Rate" 레지스트리 태그가 있는지~~ | Phase 2 확인 — 마켓 시퀀스 1,237개 전부 있음 |
| Blender · Meshy 출력의 단위·축 | Phase 4 (Blender) · Phase 6 (Meshy) |
| Meshy 길이 범위 · 가격 · 결과 파일 만료 · 데이터 정책 | Phase 6 |
| 공개 Text-to-Motion 모델의 학습 데이터 라이선스 | Phase 5 |
