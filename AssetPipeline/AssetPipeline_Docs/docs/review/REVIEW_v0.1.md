# Architecture v0.1 검토 (초안)

작성일: 2026-11-26 · 상태: 초안 — 사용자 승인 전, 확정된 것 없음
대상: `AssetPipeline_Docs/` 의 CLAUDE.md · START_PROMPT.md · docs 00 ~ 14

**후속 문서:** [REUSE_ANALYSIS_AND_PLAN.md](REUSE_ANALYSIS_AND_PLAN.md) 가 이 문서의 §7 ~ §10(개선 방향 · ADR · PoC · MVP)을 대체한다 — 사용자가 전달한 목표(통합 에이전트 제작 파이프라인 · Blender 는 주 제작 환경)와 참조 사례 소스 분석을 반영했다. 표의 'tree' 값은 커밋 SHA 다.

표기: **[확인]** = 오늘 원문 · 코드 · 소스를 직접 읽음 / **[기록]** = 이 프로젝트의 앞선 조사 문서에 적힌 것(오늘 다시 읽지 않음) / **[추정]** = 내 판단 / **[미확인]** = 읽지 못했거나 실행하지 않음.

---

## 0. 검토 방법과 한계

- 설계 문서는 통합본 `MASTER_DESIGN.md` 와 분할본 15개(`docs/00` ~ `14`)를 모두 읽었다. 본문은 같았다. 다른 곳은 통합본에 실린 CLAUDE.md 사본 한 문장뿐이다(첫 규칙 뒤의 "사용자 승인 전 대규모 구현 · 설치 · 유료 호출 · 에셋 변경 금지"가 실제 CLAUDE.md 에는 없다 — START_PROMPT.md 끝에는 같은 취지가 있다).
- 저장소 20곳은 GitHub API 의 저장소 정보(설명 · 라이선스 · 생성일 · 마지막 push · 별 수)와 README · LICENSE 원문으로 확인했다. 파일 목록은 6곳만 받았다.
- **커밋 SHA 는 AssetForge 하나만 확인했다.** 나머지는 비인증 API 한도(시간당 60회)에 걸려 받지 못했다. 표의 'tree' 값은 커밋이 아니라 HEAD 트리 SHA 다.
- 어떤 저장소도 내려받거나 실행하지 않았다. 설치 · 가입 · 유료 호출 0건.
- 기존 구현체는 `Tools/mcp/anim_gen/`(라우터 · 실행기 · 서비스 · 매니페스트 · 요청 정규화)과 `Docs/AIAnimation/` 지침서 · 조사 문서 2종을 읽었다. Provider 구현 안쪽과 C++ 본문은 읽지 않았다.

---

## 1. v0.1 요약

**목표.** Claude Code 가 전문 AI 와 Blender 로 Mesh · Rig · Animation 을 만들고, 검증하고, 실패하면 복구하는 재현 가능한 오프라인 제작 파이프라인. 첫 대상 AstralBreak(UE 5.7.4), 독립 저장소.

**요구사항 15개(FR-01 ~ 15)** 를 넷으로 묶으면:

| 묶음 | FR | 내용 |
| :--- | :--- | :--- |
| 메시 · 리그 | 01 ~ 03 | Tripo GLB · 기존 FBX 입력, 전처리, 자동 리깅, pose test |
| 모션 원천 4경로 | 05 ~ 08 | AI 레퍼런스 영상 → 모션 추출 + Vision 의미 분석 / Text-to-Motion / 기존 모션 수정 / 절차적 · 직접 키 |
| 작업 공간 · 품질 | 04 · 09 · 10 · 11 · 14 · 15 | Blender 직접 제어(MCP + headless), 리타깃, QA 게이트, 체크포인트 · 롤백 · 폴백, 사람 승인, 출처 기록 |
| 엔진 | 12 · 13 | UE 임포트, Montage · Notify · Motion Warping · 전투 메타데이터 |

**구조.** Claude = 계획 · 판단(Control plane), Python Core = 실행 · 상태 · 복구(Execution plane). Core 는 DAG 계획 · SQLite 상태 · Provider 레지스트리 · 체크포인트 · 예산. 모션 4경로는 공통 포맷(JSON + NPZ, Z-up · +Y 정면 · m · 쿼터니언)으로 모은 뒤 리타깃 → IK · 타이밍 · 루트 보정 → QA → FBX → UE 스테이징 → 명시적 publish.

**로드맵.** Phase 0 기술 검증 → 1 Core → 2 Blender → 3 Mesh/Rig → 4 기존 애니 → 5 Video → 6 Text → 7 자동 QA → 8 UE 게임플레이 → 9 확장. MVP = 1 ~ 4.

---

## 2. 출처 검증 (2026-11-26 열람)

### 2.1 구현 사례 후보 (R)

| ID | 저장소 | 라이선스 | 생성 → 마지막 push | ★ | 확인한 것 | 재사용 판정 |
| :--- | :--- | :--- | :--- | ---: | :--- | :--- |
| R01 | HErkanuzun/AssetForge | AGPL-3.0 + 상업 이중 | 11-01 → 11-24 · 커밋 `158bb96fc5` (v0.6.0, 11-10) | 6 | [확인] Electron(TypeScript) 데스크톱 앱. Meshy → **NVIDIA Kimodo** → headless Blender → UE Python Remote Execution. 발 접지에서 접지로 루프 자르기, 이웃 클립 자세에 맞춘 전환, 모션 QA(발 미끄러짐 · 바닥 관통 · 떨림) 뒤 seed 바꿔 재시도 | **아이디어만.** AGPL 이라 코드를 옮기면 우리 쪽에 의무가 온다. 모션 원천이 우리와 같은 Kimodo 다 |
| R02 | rotembab/claude-blender-integration | MIT | 10-21 → 11-06 · tree `67b1ddb75d` | 2 | [확인] Blender 애드온(소켓 서버) + MCP 서버 + 스킬 · 플레이북. `checkpoint` · `list_checkpoints` · `rollback` · `capture_views` · `rig_template` · `rigify_*` · `bind_mesh` · `rig_report` · `pose_test` · `keyframe` · `procedural_cycle` · `export_model` · `reimport_check` · `run_python`. README 스스로 "UniRig 연결은 실제 설치본에서 돌려 보지 않았다"고 적음 | **1순위 재사용 후보**(MIT). 단 리타깃 · IK 파지 · F-Curve 편집 Tool 은 목록에 없다 — 직접 구현 |
| R03 | Guilherme-M-Mateus/keyframe-coach | MIT | 10-20 → 10-21 · tree `9d21312d49` | 10 | [확인] 스킬 1개 + 참고 문서 3 + `scripts/audit.py`. **"공식 MCP for Blender"(`mcp__blender__*`)를 쓰고 옛 서드파티(ahujasid) Tool 은 쓰지 말라**고 적음. headless 한 스크립트로 재빌드 → audit → 렌더 | 스킬 문서 · audit 규칙을 지식으로 재사용 가능 |
| R04 | sambena/autorig-workbench | GPL-3.0 | 09-22 → 10-19 · tree `80a127582a` | 2 | [확인] headless Blender 자동 리깅 + 감사(PASS/CHECK/FAIL). **알파.** README: 25개 시험 중 6 PASS · 3 CHECK, "생성 메시는 대부분 아직 FAIL". Blender 5.2 에서 시험. Mesh2Motion(MIT · CC0) 골격 템플릿 사용. `autorig/core/generators/tripo.py` · `rig_quality.py` · `fbx_inspect.py` | 별도 프로세스 도구로만(GPL). 품질이 스스로 밝힌 대로 낮다 |
| R05 | Scenario Fully Rigged / Uthana | 상용 | 블로그 04-29 · 갱신 10-26 | — | [확인] 블로그 글 존재. 영상 · 텍스트 → 모션, 올린 캐릭터에 자동 리타깃, FBX · GLB 출력이라고 **주장**. 약관 · 가격 · API 는 [미확인] | 클라우드 후보. 캐릭터 메시를 올려야 한다 |
| R06 | wa-ys/HY-Motion-Pipeline | GPL-3.0 | 09-23 (push 1회) | 2 | [확인] HY-Motion + GVHMR 을 ComfyUI 로 묶은 Windows 앱. **README 가 직접 경고: HY-Motion 은 한국 제외, GVHMR · SMPL-X 는 비상업 전용** | 못 쓴다(§5.1) |
| R07 | SUPERpowerGT/3DCharacterAutomationPipeline | **없음** | 2025-11-06 (push 1회) | 1 | [확인] 라이선스 파일 없음 → 재사용 권리 없음 | 참고만 |
| R08 | flora6907/character-animation-pipeline | **없음** | 04-16 (push 1회) | 2 | [확인] InstantMesh + RigAnything + AnyTop/MDM, Modal 클라우드. MDM 은 AMASS 계열 [기록] | 참고만 |
| R09 | AiverReaver/blender-unreal-pipeline-skill | MIT | 10-20 (push 1회) · tree `b590525b58` | 1 | [확인] 스킬 + 명령 6개. `scripts/fbx_inspect.py` · `validate_blender.py` · `export_fbx_template.py` · `ue_import.py`, FBX 시험 픽스처 6개. **Blender 5.2.2 LTS · UE 5.8.3 에서 측정**(우리는 4.4 · 5.7.4) | FBX 게이트 · 축 · 단위 규칙 재사용 가능. 버전 차이는 재측정 |
| R10 | AKASubaz/ComfyUI-Video2MotionCapture | GPL-3.0 | 02-17 → 02-18 | 129 | [확인] "WIP". GVHMR 기반, SMPL 모델 약 3.5 GB 내려받음 | 못 쓴다(GVHMR · SMPL) |
| R11 | facebookresearch/actionmesh | 사용자 정의(NOASSERTION) | 01-21 → 10-07 | 450 | [확인] 저장소 존재. 라이선스 원문 [미확인] | 설계대로 연구 후보 |
| R12 · R13 | 사례 글 · Viggle | — | — | — | [미확인] 열지 않음 | — |

R01 ~ R04 · R09 는 모두 **2026-09 ~ 11 에 만들어진 별 1 ~ 10개짜리 개인 저장소**다. '검증된 사례'가 아니라 '같은 시기에 비슷한 것을 시도한 사람들'로 읽어야 한다.

### 2.2 기술 후보 (T)

| ID | 대상 | 확인한 것 | 판정 |
| :--- | :--- | :--- | :--- |
| T04 | ahujasid/mcp-for-blender | [확인] MIT · 35,866★ · push 11-18. **서드파티**(README 첫머리에 명시). AI 가 Blender Python 을 직접 써서 실행. 텔레메트리 절이 있다 | 쓸 수 있으나 임의 코드 실행 · 텔레메트리 설정 확인 필요 |
| T04 | bpy-dev/blender-mcp | [확인] GPL-3.0 · 100★. "Blender Lab 의 Blender MCP 의 수정 배포판" — 저장된 `.blend` 를 서브프로세스에서 다루는 Tool 추가 | 원본(Blender Lab)은 [미확인]. **정정:** R03 이 말한 "official MCP for Blender" 는 ahujasid 서버였다(Tool 이름 일치) — 상세는 [REUSE_ANALYSIS_AND_PLAN.md](REUSE_ANALYSIS_AND_PLAN.md) §2.9 |
| T06 · T07 | Tripo API | [확인] Auto Rig 문서. 기본 URL `openapi.tripo3d.com/v3`, `v3.0-20260909` 가 인간형 권장, `spec: unreal`(UE 마네킹 본 이름), `out_format: fbx`, 응답 예시 `credits_consumed: 25`. Rig Check · Animation Retarget 엔드포인트가 따로 있다 | 리깅 1순위 후보. 가격 · 약관은 오늘 [미확인] |
| T08 | VAST-AI-Research/UniRig | [확인] MIT(코드) · 2,369★. 추론 VRAM 8 GB 이상. `spconv` · `torch_scatter` · `flash_attn` 설치 필요(README 가 flash_attn 설치 오류를 예고). 체크포인트는 Articulation-XL2.0 학습 | Windows 설치가 위험. 가중치 · 데이터 라이선스 [미확인] |
| T09 | Wan-Video/Wan2.2 · ComfyUI | [확인] Apache-2.0 / GPL-3.0. README 실행 예시에 "80 GB VRAM" · "24 GB VRAM(RTX 4090)" 표기 | 12 GB 에서 도는지는 [미확인] — 양자화 · 오프로드 구성 실측 필요 |
| T11 | zju3dv/GVHMR | [확인] LICENSE 원문: "educational, research and non-profit purposes only … prohibited for commercial use" | **상업 불가**(§5.1) |
| T12 | DeepMotion REST API | [확인] 저장소 존재 · 라이선스 없음 · push 04-23. [기록] 출력은 DeepMotion 소유, 유료만 상업, 게임은 '바이너리로만' | 보류 |
| T13 | Tencent HY-Motion 1.0 | [확인] License.txt 원문: Territory = "worldwide … excluding the European Union, United Kingdom and **South Korea**". [기록] VRAM 최소 24 ~ 26 GB | **사용 불가**(지역 + VRAM) |
| T14 | scenario-labs/skills | [확인] MIT · 4,035★ · push 11-26 | Scenario 를 쓰기로 하면 재사용 |
| T15 | harlynkingm/Video-to-3D-Animation | [확인] Apache-2.0 · 6★. SAM3 + GVHMR + 4DHOI, SMPL-X 출력 | GVHMR · SMPL-X 의존 → 불가 |
| T16 ~ T20 | UE Python API | [확인] 5.7.4 소스에 `UAssetImportTask`(UnrealEd) · `UAnimMontageFactory`(UnrealEd) · `UAnimationBlueprintLibrary`(Editor/AnimationBlueprintLibrary) · `UIKRetargetBatchOperation`(Plugins/Animation/IKRig) 존재. 문서 페이지는 열지 않음 | 존재 확인. 다만 기존 C++ 플러그인이 이미 같은 일을 한다(§3) |
| T01 ~ T03 · T05 · T10 | Claude Code · MCP · bpy · Rigify · FFmpeg 문서 | [미확인] 열지 않음 | — |

---

## 3. 기존 구현체와의 대응

v0.1 은 기존 구현을 한 번도 언급하지 않는다(11번 문서: "AstralBreak 소스는 직접 검사하지 않았다"). 그런데 Core 와 UE 연동의 큰 부분이 이미 있다.

### 3.1 이미 있는 것 → 재사용

| v0.1 모듈 | 기존 구현 | 근거 경로 | 차이 |
| :--- | :--- | :--- | :--- |
| Planner (DAG) | 규칙 표 라우터, 후보별 단계 사슬 | `Tools/mcp/anim_gen/router.py` | 선형 사슬(DAG 아님). 계획은 실행하지 않고 고정값을 보여 줌 |
| Executor | Job 실행기, cursor 로 재개 | `anim_gen/executor.py` | 백그라운드 스레드 없이 poll 로 이어 감 |
| Registry / Selector | 매니페스트 + 실행 시 가용성 계산 | `anim_gen/registry.py` · `providers.json` · `providers/base.py` `state()` | 라이선스 · 유료 · VRAM 필드가 이미 있다 |
| State Manager | JSON 파일 저장소 + 상태 전이 | `anim_gen/store.py` | SQLite 아님. 프로세스 하나 전제 |
| Provider 계약 | `plan_*` / `run` / `poll` / `cancel` | `anim_gen/providers/base.py` | v0.1 의 submit / get_status / collect / cancel 과 사실상 같다 |
| Recovery (retry · fallback) | 원인 분류표 → 다음 후보 · 재시도 · 중단 | `anim_gen/fallback.py` · `executor.py` | **롤백 · 스냅샷은 없다** |
| Budget | 승인 · 장부 · `(plan_id, attempt)` 멱등 키 | `executor.py` `_paid_step` · `service.py` `approve_generation` | 제출이 불확실하면 재제출하지 않는 것까지 구현됨 |
| Headless Blender | 서브프로세스 Provider | `providers/blender.py` · `subprocess_step.py` · `blender/*.py` | BVH → FBX 변환 · 다리 보정 · 렌더뿐. 작업 공간으로 쓰지는 않음 |
| Text-to-Motion | Kimodo 로컬 | `providers/local_ai.py` · `local_ai/kimodo_run.py` | HY-Motion 자리에 이미 적법한 대체가 돌고 있다 |
| 기존 모션 수정 | 검색 + 키 편집 op | `providers/builtin.py` · C++ `apply_animation_edits` | trim · retime · time_warp · hold_pose · concat · mirror · offset_bone · rotate_root · bone_deltas |
| Grip · Foot · Timing | 대상 쪽 한 풀이 | `body_fit.py`(4,227줄) · `foot_fix.py` · `weapon.py` · `timing.py` | UE 대상 시퀀스에서 자체 풀이기로 푼다 |
| Validation | C++ 수치 검증 + Python 지표 · 선별 | `validate_animation` · `motion_metrics.py` · `selection.py` | 기준값이 운영 애니 실측에서 나왔다 |
| 시각 확인 | 대상 메시 캡처 · 소스 골격 렌더 | `providers/review.py` · `capture_animation` | 판정은 사람 |
| UE 임포트 · 리타깃 · 몽타주 | C++ 에디터 플러그인 Tool 41개 | `Plugins/AnimGraphMcp` · `anim_graph_mcp/server.py` | v0.1 의 새 플러그인 `AssetPipelineEditor` 와 역할이 겹친다 |
| Staging → publish | 출력 허용 목록 + 승격 경로 + `promote_animation` | ini `GenerationOutputPaths` · `PromotionPaths` | ADR-07 은 이미 구현돼 있다 |
| 원본 불변 | 덮어쓰기 금지 + 전역 더티 비교 | C++ `AnimMcpGeneration::FWriteGuard` | — |

### 3.2 없는 것 → 직접 구현

| v0.1 요소 | 기존 상태 | 재사용 후보 |
| :--- | :--- | :--- |
| 메시 확보 · 전처리 (FR-01 · 02) | 없음. `import_animation_file` 은 재질 · 텍스처를 끈다 | Tripo API, R09 FBX 게이트 |
| 자동 리깅 (FR-03) | 없음 | Tripo Auto Rig(`spec: unreal`), R02 `rig_template` · `pose_test` |
| Blender 직접 제어 MCP (FR-04) | 없음 | R02(MIT) 또는 공식 Blender MCP |
| 레퍼런스 영상 생성 (FR-05) | 없음 | 미정 — 12 GB 로컬 실측 필요 |
| Video-to-Motion (FR-06) | 조사만(`VideoPoseSurvey.md`), 채택 안 함 | GEM-X(조건부) — §5.1 |
| Vision 의미 분석 | 없음 | 별도 모델 불필요 — Claude 가 프레임 시트를 직접 읽는다 |
| 공통 모션 포맷 | 없음(BVH · FBX · AnimSequence 를 그대로 넘김) | Kimodo NPZ 가 v0.1 스키마와 거의 같다 |
| 파일 스냅샷 · 롤백 | 없음 | R02 `checkpoint` / `rollback` |
| 산출물 해시 · 출처 기록 (FR-15) | 부분(seed · 모델 커밋 · 제약 파일 SHA 는 계획에 고정) | 직접 구현 |
| Notify · 전투 메타데이터 (FR-13) | 몽타주 · 섹션까지. 노티파이는 별도 스킬 | 직접 구현 |
| UE → FBX 내보내기 | 없음(Tool 41개에 export 없음) | 직접 구현(작다) |

---

## 4. 방식 비교

| 축 | 기존 (anim_gen) | v0.1 | 평가 |
| :--- | :--- | :--- | :--- |
| 범위 | 애니메이션만 | 메시 · 리그 · 애니 · 게임플레이 메타 | v0.1 이 넓다. 메시 · 리그는 완전히 새 트랙 |
| 모션 원천 | 기존 모션(주) · Kimodo · Meshy | + AI 영상 → 모션 추출, + 절차적 · 직접 키 | 원천이 늘지만 이름 붙은 도구 셋이 못 쓰는 것이다(§5.1) |
| 작업 공간 | **UE 에디터**(대상 시퀀스) | **Blender**(중립 리그) → 마지막에 UE | 가장 큰 구조 차이 |
| 보정 방법 | 자체 풀이기(가우스-뉴턴)가 대상 메시 반경 지도로 관통 · 파지 · 발을 한 번에 | Blender IK 제약 · F-Curve + Claude 가 MCP 로 직접 수정 | v0.1 이 고치기 쉽고 눈에 보인다. 대신 재현성 위험(§4.2) |
| 중간 데이터 | BVH → FBX → AnimSequence | 공통 NPZ + JSON(phase · 제약 · confidence) | v0.1 이 낫다 — 원천을 바꿔도 뒤 단계가 같다 |
| 상태 | JSON 파일 · cursor 재개 | SQLite · 체크포인트 · 롤백 | 재개는 이미 됨. 롤백이 새것 |
| 중간 산출물 위치 | UE Content 안 `Work/<job>/` | 저장소 밖 workspace(후보 · 승인 분리) | v0.1 이 낫다 — 게임 콘텐츠를 더럽히지 않는다 |
| 품질 판정 | 수치 검증 + 캡처, **판정은 사람** | 하드 게이트 + 레퍼런스 비교 + Claude 진단 → 수정 루프 | 방향은 낫다. 기준값은 전부 미측정 제안 |
| 폴백 | Provider 순서표 | + 리깅 방식 전환 · 부분 보정 | 같은 틀 |
| 비용 통제 | 승인 · 장부 · 멱등 키 구현됨 | 같은 것을 다시 설계 | 재사용하면 된다 |
| 에이전트 구성 | 한 세션 + Tool | Master + 역할 6 + 스킬 11 | v0.1 도 MVP 는 스킬만으로 시작한다고 적음 |

### 4.1 좋아질 것

1. **모션 원천이 Kimodo 하나에 묶이지 않는다.** [추정] 기존의 품질 문제는 대부분 원천에서 온다 — Kimodo 가 낸 무기 동작의 흐느적거림 · 파지 · 발 튐을 뒤에서 4천 줄짜리 풀이기로 고치는 구조다. 공통 포맷이 있으면 원천을 바꿔 끼우는 비용이 내려간다.
2. **레퍼런스가 생긴다.** 지금은 '무엇이 정답인지'가 프롬프트 문장뿐이다. 영상 · 키 포즈 · phase 타이밍이 명세로 들어오면 QA 가 '레퍼런스 대비'를 잴 수 있다.
3. **중간 결과가 Content 밖으로 나간다.** 시험 애셋 · 캡처를 손으로 치우는 일(수백 MB 단위였다)이 구조적으로 줄어든다.
4. **해시 · 출처 기록.** 어떤 입력 · 설정 · 도구 버전으로 나온 결과인지 사후에 따질 수 있다.
5. **파일 스냅샷 롤백.** 지금은 실패하면 새 이름(`_Try2`)으로 다시 만들 뿐 이전 상태로 돌아가지 못한다.
6. **전투 메타데이터가 애니와 함께 나온다.** phase 구간이 노티파이 창으로 이어지면 '생성 애니가 게임에 0개 반영'인 지금 상태를 넘을 길이 생긴다.

### 4.2 좋아지지 않거나 나빠질 수 있는 것

1. **영상 → 모션이 품질을 올린다는 근거가 없다.** [기록] 앞선 조사: 영상 복원의 떨림 · 발 미끄러짐은 전체 클립에 그대로 들어오고, 손가락은 어느 모델도 내지 못하며, 무기를 든 영상 · 빠른 휘두름 품질은 공개 자료가 없다. AI 생성 영상은 여기에 신체 왜곡이 더해진다. v0.1 도 "초기에 실측"이라고 적었고, 그게 맞다 — PoC-1 이 통과하기 전에는 이 경로를 전제로 아무것도 짓지 않는다.
2. **Claude 의 MCP 직접 수정은 재현성과 반대 방향이다.** 대화 중에 `run_python` 으로 고친 본 · 키는 다시 만들 수 없다. 수정을 '기록된 연산'으로만 허용하고 headless 재실행이 같은 결과를 내는지 검사하지 않으면, 재현성은 지금보다 나빠진다(ADR-09 후보).
3. **비결정 원천이 늘어난다.** AI 영상 생성 · 클라우드 모션 서비스는 모델 버전을 고정할 수 없다. 기존은 seed · 모델 커밋을 계획에 고정한다.
4. **QA 기준값(발 2 cm · 관통 1 cm · 파지 2 cm · 85점)은 숫자만 있다.** 기존은 운영 애니를 재서 정한 기준이 있다. 새 숫자를 쓰면 판정이 흔들린다.
5. **작업 공간을 Blender 로 옮기면 기존 풀이기의 근거가 사라진다.** `body_fit` 은 UE 대상 메시의 반경 지도로 관통을 잰다. Blender 에서 같은 일을 하려면 대상 메시를 Blender 로 내보내 같은 측정을 다시 만들어야 한다.

---

## 5. 실현 가능성 · 위험

### 5.1 라이선스 — 가장 큰 문제

v0.1 의 구조도에 모션 Provider 로 적힌 셋(`GVHMR / DeepMotion / HY-Motion`)이 모두 막혀 있다. 이 프로젝트가 이미 두 번 조사해 같은 결론을 냈고(`LocalModelSurvey.md` 10-24 · `VideoPoseSurvey.md` 11-04), 오늘 두 원문을 다시 읽어 확인했다.

| 도구 | 상태 | 근거 |
| :--- | :--- | :--- |
| GVHMR | 상업 불가. 포트폴리오 이용은 사용자 판단 | [확인] LICENSE. [기록] 추론에 SMPL-X 를 사용자가 직접 등록 · 동의하고 받아야 한다 |
| HY-Motion 1.0 | **한국에서 사용 불가** | [확인] License.txt Territory. 목적과 무관 |
| DeepMotion | 보류 | [기록] 출력 소유는 DeepMotion, 공개 저장소의 `.uasset` 이 '바이너리로만'에 걸릴 수 있다 |
| WHAM · 4D-Humans · TRAM | 상업 불가 | [기록] 코드는 MIT 지만 SMPL 파일이 막는다 |
| Tripo | 유료여야 출력을 소유 | [기록] 약관 §5.2.1 — 무료 출력은 Tripo 소유. 오늘 재확인 안 함 |

쓸 수 있는 후보:

| 용도 | 후보 | 상태 |
| :--- | :--- | :--- |
| Text-to-Motion | **Kimodo SOMA-RP v1.2** | 이미 설치 · 가동 중. 적법 [기록] |
| Video-to-Motion (로컬) | **GEM-X** (NVIDIA) | [기록] SOMA 77 관절 = Kimodo 와 같은 골격. 조건 둘이 열려 있다 — 체크포인트가 SAM 3D Body 초기화(V-1), 기본 사람 검출기가 비상업 승인 데이터 학습(V-2). Windows 설치 문서 없음 · 12 GB 미측정 · BVH 내보내기 없음 |
| Video-to-Motion (클라우드) | Uthana(Scenario) · Rokoko · Plask | 약관 · 가격 [미확인] 또는 [기록] 보류 |

### 5.2 이 PC (RTX 3080 Ti 12 GB · RAM 64 GB · Windows 11) [기록]

| 항목 | 판단 |
| :--- | :--- |
| Kimodo | 가동 중(텍스트 인코더 CPU, VRAM 3 GB 미만) |
| UniRig | VRAM 8 GB 는 들어간다. `spconv` · `flash_attn` Windows 설치가 관건 [미확인]. 스크립트가 bash 라 Git Bash 필요(R02 README) |
| Wan2.2 로컬 | README 수치는 24 GB · 80 GB. 12 GB 는 양자화 · 오프로드 구성으로만 가능성 [미확인] |
| GEM-X | 체크포인트 3.5 GB × 2, 12 GB 수치 없음 [기록] |
| 에디터와 동시 실행 | 안 된다고 보고 설계한다 — 에디터를 내리고 모델을 돌리는 순서 |
| Blender | 설치본은 **4.4**. R03 · R04 · R09 는 5.2 계열에서 시험했다. Action API 가 버전마다 달라 실측 필요 |

### 5.3 유료 API

기본값은 지금 정책 그대로 **0원**(`policy.default.json`: `paid_api_enabled false`). Tripo 는 캐릭터 1개에 생성 10 ~ 20 + 리그 25 크레딧 [확인: 리그 25 / 기록: 1 크레딧 = $0.01]. 영상 생성 · 클라우드 모캡 가격은 [미확인].

### 5.4 보안

- Blender MCP 는 본질이 임의 Python 실행이다(R02 `run_python`, T04 `execute_code`). 최소한 workspace 경로 밖 쓰기 거부 · 네트워크 호출 금지 · 내려받은 `.blend` 의 자동 실행 스크립트 끄기를 Core 가 강제해야 한다.
- T04(ahujasid)는 텔레메트리 설정이 있다 — 쓰게 되면 꺼 둘지 확인.
- 내려받는 체크포인트의 pickle(GEM-X `vitpose.pth` [기록])은 공식 저장소 파일만, 전용 환경에서.
- 클라우드 모션 서비스는 영상(사용자 신체) 또는 캐릭터 메시를 밖으로 보낸다.

### 5.5 UE 5.7.4 · AstralBreak [확인]

- `MotionWarping` · `GameplayAbilities` 플러그인이 켜져 있다.
- 노티파이 클래스는 셋: `UAstralAnimNotify_GameplayEvent` · `UAstralAnimNotifyState_GameplayEventWindow` · `UAstralAnimNotifyState_RootMotionPawnCollisionPolicy`. **v0.1 예시의 `WeaponTrace` · `MotionWarping` NotifyState 는 없다** — 이 프로젝트는 GameplayEvent 태그 창 방식이다. 전투 메타데이터는 '클래스 이름'이 아니라 '태그 + 구간'으로 설계해야 한다.
- 대상 스켈레톤은 `SKEL_UE5_F`(IdaFaber), 운영 캐릭터 Vesper 는 이미 리깅돼 있다. 새 리그의 캐릭터를 들이면 기존 애니 전부 리타깃 + AnimBP 호환 확인이 따라온다.

### 5.6 사용자가 확인해 줄 것

1. 겪은 '품질 · 재현성 문제'가 §4.1 · §4.2 의 진단과 맞는지 — 특히 재현성이 어느 지점에서 깨졌는지.
2. 이용 목적 — 포트폴리오 한정이면 GVHMR 을 '평가 전용'으로 써 볼지(SMPL-X 등록은 사용자가 직접).
3. GEM-X 조건 V-1(라이플 캐릭터와 SAM License 총기 문구) · V-2(검출기)를 받아들일지.
4. Tripo 유료 사용 여부와 상한.
5. Blender 를 4.4 로 둘지 올릴지.
6. 시험 영상 — 직접 찍은 영상이 있는지.

---

## 6. 과도한 설계 · 빠진 것

### 6.1 줄일 것

| 항목 | 이유 |
| :--- | :--- |
| 독립 저장소 + 새 UE 플러그인 `AssetPipelineEditor` | 같은 일을 하는 `AnimGraphMcp`(Tool 41) · 가드가 있다. 새로 짓지 말고 빠진 Tool 만 더한다 |
| DAG Planner | 실제 흐름은 선형 사슬 + 조건부 단계다. 지금 라우터로 충분하다 |
| SQLite + 레코드 8종 | 지금 JSON 저장소가 재개 · 멱등 · 장부를 이미 한다. 병렬 실행이 필요해질 때 |
| 에이전트 6 · 스킬 11 | 스킬 2 ~ 3개로 시작 |
| Blender Tool 31개 목록 | PoC 에 필요한 것은 10개 안팎(조회 · 본 · 키 · IK · 베이크 · 렌더 · 체크포인트 · 내보내기) |
| Vision LLM Provider 어댑터 | Claude 가 프레임 시트를 직접 읽는다 |
| 체형 표의 사족 · 드래곤 | Phase 9 로 |
| QA 점수 가중 평균(30/20/30/20) | 하드 게이트 + 실측 기준이면 된다 |

### 6.2 빠진 것

1. **기존 구현체와 그 실측 기준.** 재사용 대상이자 회귀 비교 기준인데 문서에 없다.
2. **PoC 대상의 정체.** 'Knight.glb + 대검'은 AstralBreak 에 없다. 메시 · 리그 트랙과 애니 트랙은 서로 독립이라 따로 검증해야 한다 — 애니 PoC 는 Vesper 로 하면 리깅 실패가 애니 평가를 막지 않는다.
3. **정답이 있는 시험.** 추출 품질을 '눈으로' 볼 계획뿐이다. 운영 애니를 영상으로 렌더해 넣으면 정답을 아는 시험이 된다(§9 PoC-1).
4. **손가락.** 어떤 모션 모델도 내지 않는다. 기존은 쥔 모양을 샘플에서 옮긴다(`pose_from`).
5. **무기.** 영상에서 3D 무기 자세를 복원하는 대신, 손 소켓에 붙은 무기 + 반대 손 IK 가 기본이어야 한다. 기존 `weapon.py` 가 이 방식이다.
6. **MCP 수정의 기록 · 재실행 규칙**(§4.2-2).
7. **공식 Blender MCP 의 존재**와 Blender 버전 결정.
8. **VRAM 순서 규칙**(에디터와 모델을 함께 띄우지 않는다).
9. **UE → FBX 내보내기와 왕복 정합 시험.** Blender 를 작업 공간으로 쓰면 반드시 필요하다.
10. **메시 임포트 경로**(재질 · 텍스처 포함).

---

## 7. 개선 방향 — v0.2 제안

**한 줄:** 새로 짓지 않고, 기존 `anim_gen` 을 실행 평면으로 두고 v0.1 에서 실제로 새로운 넷만 더한다.

```text
                  ┌─ 기존 유지 ─────────────────────────────────────────────┐
요청 ─▶ 계획(router) ─▶ Job(executor · 폴백 · 장부) ─▶ UE(AnimGraphMcp) ─▶ 승격
                  └────────────────────────────────────────────────────────┘
        ▲ 더할 것
        ├─ ① 공통 모션 포맷 + 산출물 저장소 (해시 · 출처 · 후보/승인 분리, Content 밖)
        ├─ ② 레퍼런스 입력 (영상 → 키 포즈 · phase 타이밍 → Kimodo 제약)
        ├─ ③ Blender 작업 단계 (기록된 연산만, headless 재실행 검사)
        └─ ④ 메시 · 리그 트랙 (독립 — 결과가 '새 대상 스켈레톤'으로 합류)
```

1. **공통 포맷은 SOMA 77 을 첫 프로필로.** Kimodo 와 GEM-X 가 같은 골격을 내고, 이 골격에서 Vesper 로 가는 리타깃 기본값(수동 체인 27개)이 이미 있다. v0.1 의 NPZ 스키마(로컬 회전 · 루트 · 접지 · confidence)는 Kimodo NPZ 와 거의 같아 변환이 얇다.
2. **영상은 먼저 '참고'로, 전체 클립 모캡은 PoC 통과 뒤에.** 영상에서 키 포즈 몇 프레임과 phase 타이밍만 뽑아 Kimodo 의 `key_pose` 제약(기존 9-3 경로)에 넣으면, 영상 복원의 떨림 · 미끄러짐이 결과에 들어오지 않는다. 품질 근거가 가장 단단한 조합이다 [추정].
3. **Blender 수정은 연산 목록으로만.** Claude 는 `run_python` 대신 이름 있는 연산(본 회전 · 키 삽입 · IK 목표 · 구간 리타임)을 내고, Core 가 그 목록을 저장한다. 같은 목록을 headless 로 다시 돌려 결과가 같은지 검사한다. 탐색용 자유 실행은 후보에만 허용하고 승인본은 연산 목록에서만 만든다.
4. **보정 위치는 PoC 뒤에 정한다.** Blender IK 로 옮길지, 기존 `body_fit` 을 유지할지는 PoC-2 · 3 수치로 결정한다. 미리 옮기지 않는다.
5. **메시 · 리그는 별도 트랙.** Tripo(`spec: unreal`, FBX) → 메시 임포트 Tool(신규) → 기존 IK Rig · 리타깃 · 캡처. 애니 트랙과 일정이 엮이지 않는다.
6. **기준은 기존 실측에서.** QA 기준값을 새로 정하지 않고, 운영 애니 · 기존 Job 의 지표를 출발점으로 둔다.

---

## 8. ADR 후보

| ADR | v0.1 | 제안 | 대안 | 근거 |
| :--- | :--- | :--- | :--- | :--- |
| 01 저장소 | 독립 저장소 + 새 UE 플러그인 | **수정** — AstralBreak 저장소 안 모듈로 시작, UE 쪽은 `AnimGraphMcp` 확장 | 독립 저장소(나중에 분리) | §3.1 — 겹치는 구현이 이미 있다 |
| 02 Control / Execution 분리 | 권장 | 수용 | — | 기존도 같은 구조 |
| 03 MCP + headless | 권장 | 수용, 단 ADR-09 조건 | headless 만 | §4.2-2 |
| 04 불변 산출물 · SQLite | 제안 | **부분 수용** — 산출물 저장소 · 해시는 지금, SQLite 는 보류 | 전부 지금 | §6.1 |
| 05 Provider + 공통 스키마 | 제안 | 수용, 첫 프로필 = SOMA 77 | 자체 canonical humanoid | §7-1 |
| 06 하드 게이트 + 사람 검토 | 권장 | 수용, 기준값은 기존 실측에서 | 문서의 제안값 | §4.2-4 |
| 07 UE 스테이징 · publish | 권장 | **이미 구현됨** — 재사용 | — | §3.1 |
| 08 PoC = 인간형 1 + 공격 1 | 권장 | 수용, 캐릭터 = Vesper · 공격 = 운영 공격 1개 | Knight + 대검 | §6.2-2 |
| **09 (신규)** MCP 수정의 재현성 | — | 승인본은 기록된 연산 목록에서만 생성, headless 재실행 일치 검사 | 자유 실행 허용 | §4.2-2 |
| **10 (신규)** 라이선스 게이트 | 위험 표에 한 줄 | 매니페스트의 `license` 가 ok 가 아니면 계획에서 제외(기존 동작). GVHMR · HY-Motion · DeepMotion 을 구조도에서 내린다 | 포트폴리오 예외 | §5.1 |
| **11 (신규)** 영상의 역할 | 전체 클립 모캡 | 키 포즈 · 타이밍 참고가 기본, 전체 클립은 PoC-1 통과 시 | 처음부터 전체 클립 | §4.2-1 |
| **12 (신규)** 보정 위치 | Blender | PoC-2 · 3 뒤 결정 | 지금 Blender 로 확정 | §4.2-5 |

상태는 전부 Proposed.

---

## 9. PoC 계획 — Vesper + 공격 1개

**대상.** 캐릭터 = Vesper(`SKEL_UE5_F`). 공격 = 운영 중인 공격 1개(사용자 지정 — 낫 또는 양손 무기 공격 권장). 이 클립이 '정답'이다.

**비용 상한.** PoC-0 ~ 3 은 0원. PoC-4 만 유료이고 상한을 사용자가 정한다(제안 $5).

| 순서 | 무엇을 | 성공 | 실패하면 |
| :--- | :--- | :--- | :--- |
| **PoC-0 기준선** | 같은 공격을 지금 파이프라인(Kimodo + 보정)으로 만들고 지표를 고정한다. 정답 클립과의 차이(관절 위치 · 손 속도 정점 시각 · 발 미끄러짐 · 손목 떨림)를 잰다 | 숫자가 나온다 — 뒤 PoC 의 비교 기준 | — |
| **PoC-1 영상 → 모션** (가장 먼저) | ① 정답 클립을 `capture_animation` 으로 고정 카메라 영상으로 렌더 → 추출기 → SOMA BVH → 기존 리타깃 → 정답과 비교 ② 실제 영상 1개 ③ AI 생성 영상 1개(구할 수 있으면) | ①에서 리타깃 뒤 관절 위치 p95 와 발 미끄러짐이 PoC-0 기준선보다 낫고, 휘두름 정점 시각 오차 ±2 프레임 | 전체 클립 경로를 내리고 ADR-11 대로 '키 포즈 · 타이밍 참고'만 남긴다 |
| **PoC-1b 키 포즈 참고** | PoC-1 출력에서 키 포즈 3 ~ 5개 + phase 시각만 뽑아 Kimodo `key_pose` 제약으로 생성 | PoC-0 보다 정답에 가깝다 | 영상 경로 전체 보류 |
| **PoC-2 Blender 제어** | Vesper 를 Blender 4.4 로 가져와 MCP 로 본 1개 · 키 1개 수정 → 렌더 확인 → 롤백 → 같은 연산을 headless 로 재실행 | 재실행 결과가 MCP 결과와 같다(관절 회전 차 0.01° 이내), 롤백 뒤 파일 해시가 원래와 같다, workspace 밖 쓰기가 거부된다 | Blender 는 headless 변환 용도로만 유지(지금과 같음) |
| **PoC-3 왕복 정합** | UE 애니 → FBX → Blender → 무편집 → FBX → UE 임포트 → 원본과 비교 | 관절 위치 0.1 cm · 회전 0.1° 이내, 루트 이동 · 길이 · fps 보존 | 축 · 단위 변환을 고칠 때까지 Blender 작업 단계 보류 |
| **PoC-4 메시 · 리그** (선택 · 유료) | Tripo 인간형 1개 → Auto Rig(`spec: unreal`, FBX) → 재질 포함 임포트 → IK Rig → Vesper 공격 리타깃 → 캡처 | 임포트 성공 · 주요 관절 pose test 통과 · 리타깃 검증 통과 | 메시 트랙 보류, 기존 캐릭터만 |

**PoC-1 의 추출기는 사용자 결정이 필요하다:** GEM-X(약 8 GB 내려받기 + 전용 환경, 조건 V-1 · V-2) / GVHMR(평가 전용 — 비상업, SMPL-X 등록) / 클라우드 무료 체험(영상 업로드 · 약관 확인). ①번 입력은 우리 렌더라 영상 권리 문제가 없다.

**검증 구분.** 표의 숫자는 자동 검사다. 각 PoC 끝에 캡처 시트를 사람이 본다. 게임 내 재생은 PoC 범위 밖이다.

---

## 10. MVP 계획

PoC 결과에 따라 갈리지만 뼈대는 같다. 단계마다 기존 pytest + 통합 하네스(`anim_gen_phase*_test.py`) 방식을 그대로 쓴다.

| 단계 | 내용 | 재사용 | 신규 | 시험 |
| :--- | :--- | :--- | :--- | :--- |
| M1 산출물 저장소 · 공통 포맷 | workspace(source / candidates / approved), 해시 · 출처 manifest, SOMA NPZ ↔ BVH | `store.py` · Kimodo NPZ · `bvh.py` | 포맷 검증 · 변환기 | NPZ 왕복, 축 · 단위 golden, 루트 이중 적용 없음 |
| M2 UE 왕복 | UE → FBX 내보내기 Tool, 왕복 검사 | `import_animation_file` · `validate_animation` | export Tool | PoC-3 을 회귀 시험으로 |
| M3 Blender 작업 단계 | 연산 목록 실행기(headless) + MCP(같은 연산), 스냅샷 · 롤백 | `subprocess_step.py` · R02(MIT) | 연산 사전 · 재실행 검사 | 실패 주입 → 원본 해시 유지, 재실행 일치 |
| M4 레퍼런스 입력 | 영상 전처리(FFmpeg) → 추출 Provider → 키 포즈 · phase | `key_pose.py` · `local_ai` · `review.py` | 추출 Provider, phase 추출 | 정답 렌더 시험(PoC-1 ①)을 회귀로 |
| M5 QA 게이트 | 기존 지표를 게이트로 승격, 레퍼런스 대비 지표 | `motion_metrics.py` · `selection.py` | 게이트 정책 · 보고서 | 일부러 망가뜨린 픽스처(발 미끄러짐 · 길이 · 파지) 탐지, 오탐 · 미탐 기록 |
| M6 전투 메타데이터 | phase → 몽타주 섹션 · GameplayEvent 창 | `package`(몽타주) · `astral-ue-montage` 스킬 | 메타 → 노티파이 매핑 | PIE 에서 태그 발생 시각 검사 |
| M7 메시 · 리그 | PoC-4 통과 시 | IK Rig · 리타깃 · 캡처 | 메시 임포트 Tool · Tripo Provider | pose test, 리타깃 검증 |

M1 → M2 는 PoC 결과와 무관하게 필요하다. M3 는 PoC-2 · 3, M4 는 PoC-1, M7 은 PoC-4 가 통과해야 연다.

---

## 11. 미확인 목록

| 항목 | 이유 |
| :--- | :--- |
| R02 ~ R04 · R09 · T04 · T08 의 커밋 SHA | API 한도. 채택 시점에 고정 |
| 모든 후보의 실제 실행 · Windows 동작 · VRAM | 내려받지 않았다 |
| 공식 Blender MCP 의 저장소 · Tool 스키마 · 지원 버전 | 간접 언급(R03 · bpy-dev)만 봤다 |
| R05 Uthana 의 약관 · 가격 · API · 출력 권리 | 블로그 글만 읽었다 |
| R11 ActionMesh · UniRig 가중치의 라이선스 원문 | 열지 않았다 |
| R12 · R13 · T01 ~ T03 · T05 · T10 · T14(Viggle) | 열지 않았다 |
| Tripo 가격 · 약관의 현재 내용 | 리그 문서만 읽었다. 기본 URL 이 앞선 기록(`tripo3d.ai`)과 다르다(`tripo3d.com`) |
| Wan2.2 가 12 GB 에서 도는 구성 | README 의 24 GB · 80 GB 표기만 봤다 |
| GEM-X 의 현재 상태 | 11-04 조사 기록을 그대로 썼다 |
| 사용자가 겪은 품질 · 재현성 문제의 구체적 내용 | §4 의 진단은 코드 구조와 기록에서 추정했다 |
