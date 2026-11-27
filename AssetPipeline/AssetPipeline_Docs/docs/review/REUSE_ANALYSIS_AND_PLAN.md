# 참조 사례 소스 분석 · 재사용 전략 · 개선 아키텍처 · PoC 계획 (초안)

작성일: 2026-11-26 · 상태: 초안 — 확정된 것 없음, 구현 · 설치 · 내려받기 · 유료 호출 0건
앞 문서: [REVIEW_v0.1.md](REVIEW_v0.1.md). 이 문서가 그 문서의 §7 ~ §10(개선 방향 · ADR · PoC · MVP)을 대체한다.
후속 문서: [ARCHITECTURE_v0.2_DRAFT.md](ARCHITECTURE_v0.2_DRAFT.md) 가 이 문서의 §4(아키텍처) · §5(PoC)를 갱신한다 — 자율 제작 루프 · 신규 키프레임 · 영상 4경로 · 메시/리그 자율 개선 · Traceability Matrix · 첫 PoC 작업 계획.

표기: **[확인]** = 오늘 소스 · 원문을 직접 읽음 / **[기록]** = 앞선 조사 문서 / **[추정]** / **[미확인]**

---

## 0. 방법과 한계

- 소스는 `raw.githubusercontent.com` 에서 파일 단위로 읽었다. 저장소를 내려받지 않았고 **어떤 코드도 실행하지 않았다.** '구현 수준' 판정은 코드 · 테스트 · README 의 자기 진술을 읽은 결과이지 동작 확인이 아니다.
- 저장소마다 전체가 아니라 재사용 판단에 걸리는 파일을 골라 읽었다(읽은 파일은 §2 에 적음).
- 커밋은 오늘 HEAD 기준이다. 채택할 때 그 커밋으로 고정한다.
- 정정: 앞 문서 표의 'tree' 값은 커밋 SHA 였다(HEAD 조회가 커밋 SHA 를 돌려줌 — 오늘 저장소 페이지 제목으로 대조).

---

## 1. 전달받은 방향 (설계 전제로 반영)

1. 목적은 애니 파이프라인 개선이 아니라 **Claude Code 가 여러 제작 도구 · AI 모델을 제어해 3D 에셋을 제작 · 수정 · 검증 · 복구하는 통합 에이전트 제작 파이프라인**이다. 메시 → 리깅 → 애니 → 게임플레이 데이터까지 전부 범위다.
2. **Blender 는 Claude 가 직접 제어하는 주 제작 환경**이다. MCP 직접 수정 · 상태 조회 · 렌더 · 시각 검사 · 복구는 핵심 요구사항이다.
3. 다만 리타깃 · IK · 모션 처리의 실행 위치는 고정하지 않는다. Blender 와 UE 를 정확성 · 효율 · 재현성으로 비교해 작업마다 고른다.
4. 기존 UE 풀이기는 없애지 않고 **비교 기준이자 Provider 후보**로 둔다.
5. Provider · Blender 버전 · Tripo 유료 · 실행 위치 · 스키마 · QA 기준값 · UE 풀이기 범위는 미확정 — 구현체 분석과 PoC 로 정한다.

---

## 2. 저장소별 소스 분석

### 2.1 Claude Blender Integration — `rotembab/claude-blender-integration` @ `67b1ddb75d` · MIT

읽은 파일: `addon/claude_blender/{server,protocol}.py`, `handlers/{core,rig,animate,export,look,util,topology}.py`, `server/src/claude_blender_mcp/{app,connection,tools_character,tools_build}.py`, `blender_manifest.toml`, `tests/blender/*`

| 항목 | 내용 [확인] |
| :--- | :--- |
| 구조 | Blender 애드온이 127.0.0.1:9877 TCP 서버를 열고, 네트워크는 백그라운드 스레드 · 명령은 `bpy.app.timers` 로 메인 스레드 큐에서 실행(`server.py` 167줄). MCP 서버는 별도 프로세스. `protocol.py` 는 bpy 를 import 하지 않아 양쪽이 공유 |
| Blender 버전 | `blender_version_min = "4.2.0"`. `animate.py` `fcurves()` 가 4.2(평면)와 4.4+(슬롯 액션)를 모두 처리 → **설치본 4.4 로 쓸 수 있다** |
| 체크포인트 | `core.py` `checkpoint()` = `save_as_mainfile(copy=True)` 로 임시 폴더(`<temp>/claude_blender_checkpoints/<pid>/`)에 `.blend` 사본. 목록은 **프로세스 메모리**(`_checkpoints`), 개수 상한. `rollback()` = `open_mainfile` |
| 직접 실행 | `run_python(code)` = `exec()` 그대로. 격리 · 경로 제한 없음. 소켓에 인증 토큰이 보이지 않는다(로컬 바인딩뿐) |
| 리그 | `rig_template`(자체 22본 인간형, 정면 −Y — UE 본 이름 아님) · `edit_bones` · `rigify_metarig/generate` · `bind_mesh`(본 히트/엔벨로프) · `rig_report`(가중치 없는 정점 · 영향 4 초과 · 합 ≠ 1 · 가중치 없는 변형 본) · `limit_weights` · `pose_test`(스트레스 자세 렌더) |
| 애니 | `keyframe`(오브젝트 · 포즈 본 키 삽입, 보간 지정) · `procedural_cycle`(걷기 · 달리기 · 대기) · `push_to_nla` · 프레임 도구 |
| 내보내기 | `export_model`(FBX 프리셋 unity/unreal/godot, glTF, OBJ) · `reimport_check`(임시 씬에 다시 가져와 본 · 클립 · 스케일 대조) |
| 보기 | `capture_views`(고정 각도 solid/wireframe/x-ray, 본은 초록 도형) · `mesh_report` |
| 테스트 | Blender 안에서 도는 pytest 4 파일(체크포인트 · 롤백, 리그 → 바인드 → 포즈 테스트, 키프레임, 내보내기 → 재임포트, 소켓 종단) + CI |
| 자기 진술 | UniRig 연결은 "실제 설치본에서 돌려 보지 않았다". image-to-3D 는 실험 |

**없는 것:** F-Curve 핸들 편집, IK 제약 생성, 리타깃, 베이크, 정점 단위 가중치 수정, 연산 기록, 영속 체크포인트.

**판정:** 구조 · 프로토콜 · 조회 · 캡처 · 리그 검사 · 키프레임 · 내보내기는 그대로 쓸 수 있는 수준. 체크포인트는 세션 안에서만 유효(Blender 가 죽으면 목록이 사라진다)하고 해시 · manifest 가 없어 우리 요구(FR-11 · 15)에는 감싸야 한다.

### 2.2 Keyframe Coach — `Guilherme-M-Mateus/keyframe-coach` @ `9d21312d49` · MIT

읽은 파일: `skills/keyframe-coach/SKILL.md`, `scripts/audit.py`(180줄), `tests/test_audit.py`(152줄), `references/*.md`

- 실체는 **스킬 문서 + 감사 스크립트 하나**다. [확인]
- `audit(arm, engine, loop, feet, in_place)` 가 보는 것: 루프 이음매(값 · 접선 속도), 선형/상수 보간 키, **쿼터니언 뒤집힘**, 스케일 키(엔진별 누락 경고), 모든 본이 같은 프레임에 키(겹침 없음), 좌우 쌍둥이 키, 제약이 걸린 본(베이크 필요), 발 검사.
- 베이크된 데이터(1 ~ 2 프레임마다 키)에는 "겹침 · 쌍둥이 검사 안 함"이라고 스스로 건너뛴다 → **손으로 키 잡은 애니용**이다. 모캡 · 생성 모션에는 일부만 유효.
- 4.4 슬롯 액션 처리 포함. headless 한 줄 실행 방식(재빌드 → audit → 렌더)과 "이미지는 컨텍스트에 남으니 한 장 시트로" 규칙이 실용적이다.
- SKILL.md 가 말하는 "official MCP for Blender" 의 Tool 이름(`get_addon_status` · `get_scene_info` · `execute_blender_code` · `look`)은 **ahujasid/mcp-for-blender 의 현재 Tool 과 같다**(§2.9). 별도의 공식 서버를 뜻하지 않는다.

### 2.3 Blender Unreal Pipeline Skill — `AiverReaver/blender-unreal-pipeline-skill` @ `b590525b58` · MIT

읽은 파일: `scripts/{fbx_inspect,validate_blender,export_fbx_template,ue_import}.py`, `references/{rigging-animation,coordinates-units}.md`, `tests/test_fbx_inspect.py`

| 파일 | 내용 [확인] |
| :--- | :--- |
| `fbx_inspect.py` (153줄) | **Blender 없이** 바이너리 FBX 를 읽는 순수 Python. `UnitScaleFactor ≠ 1`, 노드 `Lcl Scaling ≠ 1`, 충돌 메시 이름, `_end` 잎 본, **UE 가 만들 본 목록 예측**을 검사하고 PASS/FAIL |
| `validate_blender.py` (146줄) | 내보내기 전 읽기 전용 검사(단위 · 변환 · UV · 재질 · 리그 이름). headless 종료 코드 지원 |
| `export_fbx_template.py` (58줄) | UE 용 FBX 내보내기 설정 고정(`FBX_SCALE_ALL`, −Z/Y, 씬 단위 0.01 강제 등), skeletal / static / anim 세 종류 |
| `ue_import.py` (92줄) | UE Python 레거시 FBX 임포트. **파일 스스로 "이 조사 환경에서 실행하지 않았다"고 적음** |
| `references/rigging-animation.md` | **아마추어 오브젝트 이름이 UE 루트 본을 결정한다** — `Armature` 면 버려지고, 다른 이름이면 그 오브젝트가 루트 본이 된다(`root` 본이 있으면 `root1` 로 중복). 근거 번호가 달려 있다 |
| 시험 | FBX 픽스처 6개(cm / m, 스케일 옵션별) + pytest |

측정 환경은 Blender 5.2.2 LTS · UE 5.8.3 — 우리(4.4 · 5.7.4)에서 다시 재야 한다.

### 2.4 AssetForge — `HErkanuzun/AssetForge` @ `158bb96fc5` (v0.6.0) · AGPL-3.0 + 상업 이중

읽은 파일(20개 · 5,546줄): `resources/kimodo/{forge_motion,forge_kimodo_server}.py`, `resources/python/{blender_anim,blender_process,forge_skeleton,forge_assembly,ue_import,ue_animsys}.py`, `src/shared/{motionQa,bvh}.ts`, `src/main/engine/{runner,graph,executors}.ts`, `src/main/{providers/meshy,integrations/kimodo,integrations/blender,integrations/ue,security,anim/motion,agent/mcpServer}.ts`

| 부분 | 내용 [확인] |
| :--- | :--- |
| 오케스트레이션 | Electron(TypeScript). `graph.ts` 위상 정렬 + `runner.ts` QA 되먹임 루프 + `executors.ts`(1,290줄) 노드별 실행 |
| 모션 | **Kimodo 를 HTTP 서버로 띄워**(`forge_kimodo_server.py`) 자세 제약 · 경로 제약 · 다중 텍스트를 넘긴다 — 우리 `local_ai` 와 같은 모델 · 같은 제약 종류 |
| 클립 가공 | `forge_motion.py`: 왼발 접지에서 왼발 접지로 가장 비슷한 창을 찾아 루프를 자르고(`find_loop`) 이음매를 클립 전체에 펴서 닫는다(`close_loop`). 실제 속도 · 방향 · 회전 측정, 접지 시각을 싱크 마커로 |
| Blender | `blender_anim.py`(114줄): BVH 임포트 → **SOMA 본 이름을 Manny 이름으로 바꾸기만 함**(`forge_skeleton.to_manny`) → 루트 모션 → 프록시 메시 → FBX. 리타깃은 UE 에서(`ue_import.py` 의 `ensure_ik_rig` · `make_retargeter`). 주석: "Unreal Interchange 가 소수 fps(30.00003)를 거부해 정수로 고정" |
| 모션 QA | `motionQa.ts`(254줄): BVH FK → 발 미끄러짐(m/s) · 바닥 관통 · 떨림(m/s³) · 튐. **한계값이 Kimodo 데모 실측 범위로 보정돼 있다**(미끄러짐 경고 0.45 · 실패 0.8 m/s, 관통 3 · 8 cm, 떨림 600 · 1200, 튐 0.2 m). 실패하면 프롬프트에 문장을 덧붙이고 seed 를 바꿔 재시도 |
| 없는 것 | 무기 파지 · 손 · 관통 보정, 영상 경로, 체크포인트 · 롤백 |

**판정:** 우리와 같은 Kimodo → Blender → UE 경로를 다른 사람이 구현한 것이다. 라이선스(AGPL)와 언어(TS)로 코드를 옮길 수 없지만 **수치와 방식은 참고 가치가 크다** — 특히 QA 한계값의 보정 범위와 루프 자르기. 보정 깊이는 기존 `anim_gen` 이 더 깊다(수동 체인 27 · 파지 · 관통).

### 2.5 AutoRig Workbench — `sambena/autorig-workbench` @ `80a127582a` · GPL-3.0

읽은 파일(22개 · 10,145줄): `autorig/core/{rig_quality,deformation,retargeter,tripo_glb,fbx_inspect,humanoid_fit,weight_transfer,mesh_prep,mesh_doctor,foot_contact,clip_quality,quality_score,blender,exporter,skeletons}.py`, `core/generators/tripo.py`, `steps/{audit,m2m_rig,rerig_humanoid,retarget,tripo_clips,export}.py`, `docs/QUALITY.md`, `CREDITS.md`

| 부분 | 내용 [확인] |
| :--- | :--- |
| 규모 | 큰 저장소(전체 553 파일). `steps/m2m_rig.py` 하나가 2,732줄 |
| 리깅 방식 | Mesh2Motion 의 골격 템플릿 9종을 메시에 맞춘다. 본 이름은 Mesh2Motion 또는 Mixamo — **UE 마네킹 이름이 아니다** |
| 성숙도 | 알파. `blender.py` `TESTED_MAJOR_MINOR = (5, 2)`. README: 25개 중 6 PASS · 3 CHECK, "생성 메시는 대부분 아직 FAIL" |
| 품질 점수 | `docs/QUALITY.md`: 변형 지표가 정의 · 보정돼 있다 — 원본 표면 대비 거리(키의 %), 3배 넘게 늘어난 엣지(‰), 찌그러진 엣지, **팔이 몸통 안으로 들어간 정점 %**, 다리 교차, 발 미끄러짐, 뜸 · 가라앉음. 모델 16개에 대해 눈 판정과 점수를 나란히 적은 보정표 |
| Tripo | `generators/tripo.py`(138줄): v3 API(`openapi.tripo3d.com/v3`), 모델 `v3.1-20260211`, 가격 text 10 · image 20 · 텍스처 +10 ~ 30 크레딧(2026-10-18 확인이라고 적음), 실패 태스크 환불, 잔액 조회 무료 |
| Tripo 결함 | `tripo_glb.py`(216줄): **Tripo GLB 에 실제로 있던 결함 둘을 고친다** — JSON 의 NaN(Blender 임포터가 거부), 리깅된 동물의 관절이 전부 원점(기준 포즈가 inverse bind 에만 있음) |

**판정:** 리깅 결과물 자체는 쓰기 이르다. 그러나 **리그 품질 지표의 정의와 Tripo 출력의 실전 결함 목록**은 우리가 다시 발견하는 데 시간을 쓸 내용이다.

### 2.6 3DCharacterAutomationPipeline — `SUPERpowerGT/…` @ `a26517f377` · 라이선스 없음

읽은 파일: 스크립트 5개 전부(538줄)

- `prepare_for_mixamo.py`(179) → `auto_rigify_bind.py`(176) → `apply_anim_to_rigged.py`(100) → `clean_anim_fbx.py`(51), `watch_and_process.py`(32). 단계마다 `blender -b -P` 한 줄. [확인]
- `bpy.ops.import_scene.obj` 를 쓴다 — 4.x 에서 없어진 연산자라 설치본에서 그대로는 돌지 않는다. [확인: 코드 / 추정: 동작]
- 라이선스가 없어 코드를 쓸 권리가 없다. '단계별 headless 스크립트' 구조는 우리 `blender/*.py` 가 이미 같은 형태다.

### 2.7 Character Animation Pipeline — `flora6907/…` @ `2bce3f8b36` · 라이선스 없음

읽은 파일: README, `character-pipeline/stages/{retarget,rigging,motion}.py`

- Modal 클라우드(A10G)에서 InstantMesh → RigAnything + (AnyTop 또는 MDM) → 자체 FK/IK 리타깃(83줄) → GLB. [확인]
- 라이선스 없음 + MDM 은 AMASS 계열 [기록] + 클라우드 GPU 전제 → 쓸 수 없다.
- 기록해 둘 것 하나: **AnyTop** 은 골격 위상을 조건으로 받아 임의 골격에 모션을 만든다(자유 텍스트 프롬프트는 안 됨). 크리처 단계(Phase 9)의 조사 후보. 라이선스 [미확인].

### 2.8 HY-Motion-Pipeline — `wa-ys/…` @ `0bad4ea49b` · GPL-3.0

읽은 파일: README, `blender/{hym_retarget,gvhmr_to_smplh_fbx,hymotion_to_unity}.py`

- `hym_retarget.py`(883줄, "Blender 5.x headless"): SMPL-H 애니를 Mixamo · UE4/UE5 · Biped · Unity 리그로 옮기고, **손은 모델이 못 내므로 손 자세 프리셋**(편 손 · 주먹 · 가리킴 · 쥠, 열고 닫기 주기)을 덧입힌다(`build_hand_rig` · `apply_hand`). [확인]
- 모델 둘 다 우리가 못 쓴다 — README 스스로 경고(HY-Motion 한국 제외, GVHMR · SMPL-X 비상업). [확인]
- 손 자세를 프리셋으로 덧입히는 방식은 기존 `pose_from`(샘플에서 쥔 모양 전이)과 같은 문제의 다른 답이다.

### 2.9 Blender MCP 계열

| 저장소 | 커밋 · 라이선스 | 내용 [확인] |
| :--- | :--- | :--- |
| `ahujasid/mcp-for-blender` | `a5a8acf2c6` · MIT · 35.9k★ | Tool 9개. 핵심은 `execute_blender_code`(임의 Python) + `look`(뷰포트 · 카메라 · 다각도 시트 · **애니메이션 프레임 스트립**) + `get_scene_info`. `generate_3d`(Tripo · Meshy 등). 서드파티임을 명시. **기본으로 익명 사용 기록을 보낸다**(설치 ID · Tool 이름 · 성공 여부 · 버전 · OS) — 끌 수 있음 |
| `bpy-dev/blender-mcp` | `2965cde777` · GPL-3.0 · 100★ | "Blender Lab 의 Blender MCP 의 수정 배포판". **저장된 `.blend` 를 새 서브프로세스에서 다루는 `_for_cli` Tool**, 실행 중인 Blender API 조회, 타임아웃 · 출력 상한("OS 샌드박스는 아니다"라고 명시) |
| Blender Lab 의 원본 MCP | — | bpy-dev 가 원본으로 지목. 저장소 · 라이선스 [미확인] |

**정정:** 앞 문서에서 "공식 Blender MCP 가 따로 있다(R03 도 같은 말)"고 썼는데, R03 이 말한 것은 ahujasid 의 서버였다. 별도 원본은 bpy-dev 가 말하는 Blender Lab 쪽이고 아직 확인하지 못했다.

### 2.10 서비스 — Scenario · Viggle · Tripo

| 서비스 | 확인한 것 | 미확인 |
| :--- | :--- | :--- |
| Scenario 'Fully Rigged' | [확인] 공개 사례의 실제 순서: Meshy 로 부위별 생성 → **Blender 에서 조립** → Scenario 의 3D 모델로 리깅 → Seedance 로 영상 생성 → **Viggle Video to Motion 3D** 로 골격 애니 → 리타깃. 시연 동작은 손 흔들기 · 스트레칭 · 대화 제스처 — **전투 동작은 없다** | 가격 · 약관 · 출력 권리 |
| Scenario skills (`scenario-labs/skills` @ `3c4d18cd0b`, MIT) | [확인] `scenario-video-to-motion` · `scenario-blender` 스킬과, Blender · Unreal 등을 모는 'expert tools' 스킬 묶음이 있다 | 스킬 본문 |
| Viggle | [확인] REST API(크레딧당 $0.01 · 처음 100 무료), MCP 서버 셋(그중 PINOC: 텍스트 · 영상 → FBX/GLB 모션). 자사 격투 게임에 썼다고 주장 | 약관 · 입력 학습 사용 · 출력 권리 · 전투 품질 |
| Tripo | [확인] Auto Rig: `v3.0-20260909`, `spec: unreal`, FBX, 25 크레딧, Rig Check · Animation Retarget 엔드포인트 | 약관 현재본 |

Scenario 사례가 영상 → 모션에 쓰는 것이 Viggle 이므로, 설계의 'Scenario / Viggle' 은 사실상 **Viggle 하나의 추출기**다.

---

## 3. 분류

기준: **Reuse** 그대로 쓴다 / **Adapt** 가져와 고친다 / **Reference** 코드는 안 가져오고 방식 · 수치만 / **Replace** 설계가 지목한 것을 다른 것으로 / **Implement** 직접 구현 / **Reject** 쓰지 않는다.

라이선스 원칙: MIT 는 고지를 붙여 가져올 수 있다. GPL · AGPL 코드는 우리 저장소에 섞지 않고, 쓴다면 별도 프로세스 도구로만 쓴다. 라이선스 없는 코드는 가져오지 않는다. (Blender 안에서 `bpy` 를 쓰는 우리 스크립트의 배포 조건은 채택 전에 Blender 재단 안내로 확인한다 [미확인].)

### 3.1 외부 사례

| 대상 | 분류 | 무엇을 | 근거 |
| :--- | :--- | :--- | :--- |
| Claude Blender Integration — 애드온 소켓 서버 · 프로토콜 · MCP 서버 | **Adapt** | Blender MCP 의 뼈대. 연산 기록 · 토큰 · 경로 제한을 더한다 | §2.1 — MIT, 테스트 있음, 4.4 지원 |
| 〃 — `capture_views` · `mesh_report` · `rig_report` · `pose_test` · `bind_mesh` · `edit_bones` · `keyframe` · `export_model` · `reimport_check` | **Reuse** | 그대로 | §2.1 |
| 〃 — `checkpoint` / `rollback` | **Adapt** | 사본 저장 방식은 쓰고, workspace 저장 · 해시 · manifest · 프로세스 밖 목록을 더한다 | 목록이 메모리에만 있다 |
| 〃 — `run_python` | **Adapt** | 탐색용으로만. 승인본은 기록된 연산에서만 만든다 | 격리 없음 |
| 〃 — `rig_template` · UniRig 연결 | **Reference** | — | 본 이름이 UE 가 아니다 · 미실행 |
| Keyframe Coach — `audit.py` | **Reuse** | Blender 쪽 애니 감사(쿼터니언 뒤집힘 · 루프 이음매 · 스케일 키 · 제약 베이크) | §2.2 — MIT, 테스트 있음 |
| 〃 — SKILL.md · references | **Adapt** | 우리 스킬의 지식 문서로 | Tool 이름이 ahujasid 기준 |
| Blender Unreal Pipeline Skill — `fbx_inspect.py` + FBX 픽스처 | **Reuse** | FBX 게이트(Blender 불필요) | §2.3 — MIT |
| 〃 — `export_fbx_template.py` · `validate_blender.py` · references | **Adapt** | 내보내기 설정 · 사전 검사 · 아마추어 이름 규칙. 4.4 · 5.7.4 에서 재측정 | 측정 환경이 5.2.2 · 5.8.3 |
| 〃 — `ue_import.py` | **Reject** | — | 미실행 + 우리 C++ 임포트가 있다 |
| AssetForge — 오케스트레이션 · Provider · UE 연동 코드 | **Reject** | — | AGPL · TypeScript · 기존 `anim_gen` 과 중복 |
| 〃 — 모션 QA 한계값 · 루프 자르기 · 소수 fps 함정 · 접지 싱크 마커 | **Reference** | 수치와 방식 | §2.4 |
| AutoRig Workbench — 리깅 본체 | **Reference** | (PoC-6 뒤 폴백 리거로 별도 프로세스 사용을 다시 판단) | 알파 · GPL · 5.2 시험 · UE 본 이름 아님 |
| 〃 — `docs/QUALITY.md` 지표 · `tripo_glb.py` 결함 목록 · `generators/tripo.py` 가격표 | **Reference** | 리그 QA 지표 정의, Tripo 출력 결함, 엔드포인트 | §2.5 |
| 3DCharacterAutomationPipeline | **Reject** | — | 라이선스 없음 · 옛 API · 기존에 같은 구조 |
| Character Animation Pipeline | **Reject** | (AnyTop 만 Phase 9 조사 후보로 기록) | 라이선스 없음 · AMASS · 클라우드 GPU |
| HY-Motion-Pipeline — 모델 | **Reject** | — | 한국 제외 · 비상업 |
| 〃 — 손 자세 프리셋 방식 | **Reference** | — | GPL |
| ComfyUI-Video2MotionCapture | **Reject** | — | GVHMR · SMPL |
| ahujasid/mcp-for-blender | **Reference** | `look` 의 프레임 스트립 방식. PoC-1 에서 대안으로 비교 | 구조화 Tool 이 적고 코드 실행 중심 · 기본 사용 기록 전송 |
| bpy-dev/blender-mcp | **Reference** | 저장 파일을 새 서브프로세스에서 다루는 방식 | GPL |
| Scenario skills | **Reference** | Scenario 를 쓰기로 하면 Reuse | 본문 미확인 |

### 3.2 설계가 지목한 도구

| 설계의 지목 | 분류 | 대체 · 조건 |
| :--- | :--- | :--- |
| HY-Motion (Text-to-Motion) | **Replace** | Kimodo(가동 중) |
| GVHMR (Video-to-Motion, 로컬) | **Replace** | GEM-X(조건부 · 미측정). GVHMR 은 사용자가 정하면 '평가 전용' |
| DeepMotion (클라우드) | **Replace** | Viggle 을 PoC-5 후보로(약관 확인 뒤) |
| Tripo 메시 · Auto Rig | **Reuse** (API) | 유료 결정 뒤. `spec: unreal` |
| UniRig · Rigify | Reuse 후보 | PoC-6 의 폴백. UniRig 는 Windows 설치 실측이 먼저 |
| ComfyUI + Wan (영상 생성) | 미정 | 12 GB 실측 또는 클라우드(Seedance 등) — PoC-5 |
| SQLite · DAG Planner | 보류 | 병렬 실행이 필요해질 때 |

### 3.3 기존 프로젝트 구성 요소

| 구성 요소 | 분류 | 비고 |
| :--- | :--- | :--- |
| `anim_gen` 뼈대(라우터 · 실행기 · 저장소 · 정책 · 폴백 · 장부) | **Reuse** | 실행 평면. 산출물 저장소 · 체크포인트 기록을 더한다(Adapt) |
| `AnimGraphMcp` (UE 어댑터, Tool 41) | **Reuse** | 빠진 Tool 은 Implement: FBX 내보내기, 재질 포함 메시 임포트, 노티파이 저작 |
| Kimodo Provider · 키 포즈 제약 | **Reuse** | 생성 경로이자 폴백 |
| UE 풀이기(`body_fit` · `timing` · `foot_fix` · `weapon`) | **Reuse** | 비교 기준 + '실행 위치 = UE' Provider |
| `validate_animation` · `motion_metrics` · `selection` | **Reuse** | QA 게이트의 지표 원천 |
| `capture_animation` · `review` | **Reuse** | 시각 검사 + PoC-3 의 정답 영상 렌더 |
| headless Blender Provider | **Adapt** | 변환 전용 → 연산 목록 실행기로 넓힌다 |

### 3.4 직접 구현 (어디에도 없는 것)

1. **연산 기록과 재실행** — MCP 로 한 수정을 연산 목록으로 남기고 headless 로 다시 돌려 같은 결과인지 검사
2. **영속 체크포인트 · 산출물 저장소** — workspace, sha256, manifest, 후보/승인 분리
3. **Blender 쪽 편집 연산** — F-Curve 편집, IK 제약, 무기 파지, 베이크, 정점 가중치 수정
4. **Blender 쪽 리타깃** — 비교용(UE IK Rig 가 기준)
5. **공통 모션 포맷과 변환기**
6. **영상 → 모션 Provider** 와 phase · 키 포즈 추출
7. **실행 위치 비교 하네스** — 같은 입력을 Blender 경로와 UE 경로로 돌려 같은 지표로 비교
8. **UE Tool** — FBX 내보내기, 메시 임포트, 노티파이 · 전투 메타
9. **메시 전처리 · Tripo Provider**

---

## 4. 개선 아키텍처

```text
Claude Code ─ 스킬(제작 지식: Keyframe Coach · Blender→UE 규칙 · 우리 규칙)
   │
   ├─ 파이프라인 MCP  (기존 anim-gen-mcp 확장 — 실행 평면)
   │     계획 · Job · 폴백 · 승인 · 장부        ← 기존
   │     + 산출물 저장소(해시 · 출처) · 체크포인트 기록 · 연산 기록   ← 신규
   │
   ├─ Blender MCP     (Claude Blender Integration 기반 — 주 제작 환경)
   │     조회 · 캡처 · 리그 · 키프레임 · 내보내기 · 체크포인트   ← Reuse / Adapt
   │     + F-Curve · IK · 파지 · 베이크 · 가중치 · 리타깃          ← 신규
   │     같은 연산을 headless 로 재실행(검증 · 일괄 처리)
   │
   └─ UE MCP          (기존 anim-graph-mcp)
         임포트 · IK Rig · 리타깃 · 검증 · 캡처 · 몽타주 · 승격   ← 기존
         + FBX 내보내기 · 메시 임포트 · 노티파이                    ← 신규

모션 원천:  Kimodo(텍스트 · 키 포즈) │ 영상 → 모션(미정) │ 기존 모션 │ Blender 직접 키
              └────────────── 공통 모션 포맷 ──────────────┘
처리 작업:  리타깃 · IK · 파지 · 발 · 타이밍 · 루트
              각 작업 = [Blender 실행] 또는 [UE 실행]  ← 비교 하네스 결과로 작업마다 선택
검증:       수치 게이트(기존 지표) + Blender 감사 + FBX 게이트 + 캡처 시각 검사 + UE 재생
```

원칙 다섯:

1. **실행 위치는 Provider 속성이다.** 같은 작업(예: 파지 보정)에 `blender_ik` 와 `ue_body_fit` 두 Provider 를 두고, 라우터가 고른다. 선택 근거는 비교 하네스의 수치다. 기존 풀이기는 이 구조 안에서 그대로 산다.
2. **Blender 직접 수정은 전부 기록된다.** Claude 는 Tool 로 고치고, Core 가 연산 · 인자 · 전후 해시를 남긴다. `run_python` 은 탐색용 후보에만 쓰고, 승인본은 연산 목록을 headless 로 재실행한 결과여야 한다.
3. **체크포인트는 Core 가 소유한다.** Blender 의 사본 저장을 호출하되, 파일은 Job workspace 에 두고 목록 · 해시는 Core 저장소에 적는다. Blender 가 죽어도 복구 지점이 남는다.
4. **왕복은 게이트를 지난다.** UE ↔ Blender 를 오갈 때마다 FBX 게이트(`fbx_inspect`)와 왕복 정합 검사를 거친다.
5. **기준값은 실측에서.** 기존 운영 애니 지표 + AssetForge 의 Kimodo 보정 범위 + AutoRig 의 리그 지표 정의를 출발점으로 삼고, PoC 수치로 확정한다.

---

## 5. PoC 계획

제안하신 순서에서 **둘만 바꾼다.** 내용은 그대로 둔다.

| 순서 | PoC | 선행 | 비용 · 승인 | 통과 기준(초안) | 여기서 확정되는 것 |
| :---: | :--- | :--- | :--- | :--- | :--- |
| 1 | **PoC-0** 기존 파이프라인 기준선 | — | 0 | 운영 공격 1개 대비 지표가 숫자로 고정된다 | 비교 기준 |
| 2 | **PoC-1** Blender MCP 직접 제어 + 체크포인트/롤백 | — | 0 · 애드온 설치 승인 | 본 · 키 수정 → 캡처 확인 → 롤백 뒤 파일 해시가 원래와 같다 · workspace 밖 쓰기 거부 · 같은 연산의 headless 재실행이 같은 결과 | MCP 기반(2.1 vs 2.9), Blender 4.4 유지 여부 |
| 3 | **PoC-2** UE ↔ Blender 무편집 왕복 | UE FBX 내보내기 Tool | 0 | Vesper + 운영 공격이 왕복 뒤 위치 0.1 cm · 회전 0.1° 이내, 길이 · fps · 루트 보존, FBX 게이트 통과 | 축 · 단위 규약, 아마추어 이름 규칙, 스키마의 좌표계 |
| 4 | **PoC-4** Claude 직접 수정 → 자동 검증 → 복구 · 재시도 | 1 · 2 | 0 | 일부러 망가뜨린 클립(발 미끄러짐 · 파지 이탈 · 쿼터니언 뒤집힘)을 Claude 가 Blender 에서 고쳐 게이트를 통과시킨다 · 실패한 시도는 롤백되고 기록이 남는다 · **같은 과제를 UE 풀이기로도 돌려 수치를 나란히** | 작업별 실행 위치(첫 판정), UE 풀이기 통합 범위 |
| 5 | **PoC-3** 운영 애니 영상 렌더 → 모션 추출 정확도 | 추출기 결정 · 설치 승인 | 0(로컬) | 정답 대비 관절 위치 p95 · 발 미끄러짐이 PoC-0 보다 낫고 휘두름 정점 ±2 프레임 | Motion Provider(영상), 전체 클립 경로를 열지 |
| 6 | **PoC-3b** 추출 키 포즈 · 타이밍 → Kimodo 생성 | 3 | 0 | PoC-0 보다 정답에 가깝다 | 영상의 역할(전체 클립 / 참고) |
| 7 | **PoC-6** Tripo 메시 → 자동 리깅 · 스키닝 · 폴백 | 1 | **유료** · 상한 승인 | 임포트 · pose test · 리그 지표 통과, 실패 시 폴백 리거로 넘어간 기록 | Tripo 유료 · 한도, 폴백 리거 |
| 8 | **PoC-5** 신규 AI 생성 영상 → 모션 | 3 통과 | 유료 가능 | PoC-3 대비 품질 저하 폭이 허용 범위 | 영상 생성 도구, 클라우드 추출기 |
| 9 | **PoC-7** End-to-End 통합 | 전부 | — | 메시 → 리그 → 애니 → UE 재생까지 한 Job, 중간 실패 1회 복구 | 최종 스키마 · QA 기준값 |

**바꾼 것과 이유**

1. **PoC-4 를 PoC-3 앞으로.** PoC-4 는 PoC-1 · 2 만 있으면 되고 비용 · 내려받기 · 라이선스 결정이 없다. PoC-3 는 추출기 결정과 설치(GEM-X 면 약 8 GB)가 걸려 있어 그 결정을 기다리는 동안 핵심 목표(직접 수정 · 검증 · 복구)가 멈춘다. 추출기가 먼저 정해지면 3 을 먼저 해도 된다 — 둘은 서로 의존하지 않는다. PoC-3 의 정답 영상 렌더는 비용이 없으니 PoC-2 직후 미리 만들어 둔다.
2. **PoC-6 을 PoC-5 앞으로.** PoC-5(AI 영상)는 불확실성과 비용이 가장 크고, 실패해도 End-to-End 는 다른 모션 원천으로 닫힌다. PoC-6(메시 · 리그)은 End-to-End 에 반드시 필요하다.

**PoC-1 의 세부 순서.** Vesper 를 Blender 로 가져오려면 PoC-2 의 내보내기가 먼저 필요하다. 그래서 PoC-1 은 임시 리그(애드온의 `rig_template`)로 제어 · 롤백 · 재실행 기제만 검증하고, Vesper 로 하는 실제 수정은 PoC-4 에서 한다.

**시작 전 승인이 필요한 것**

| 항목 | 시점 |
| :--- | :--- |
| 참조 저장소 내려받기(MIT 셋: 2.1 · 2.2 · 2.3) — 격리 폴더에, 실행 전 코드 확인 | PoC-1 전 |
| Blender 4.4 에 애드온 설치 | PoC-1 |
| UE FBX 내보내기 Tool 추가(C++ 소규모) | PoC-2 |
| 영상 추출기 선택 · 내려받기(GEM-X / GVHMR 평가 전용 / 클라우드) | PoC-3 |
| Tripo 유료 사용과 상한 | PoC-6 |

---

## 6. 미확정 사항 — 어디서 정해지나

| 미확정 | 정해지는 곳 | 지금 근거 |
| :--- | :--- | :--- |
| Motion Provider 최종 선택 | PoC-3 · 3b · 5 | Kimodo 는 가동 중. GEM-X 는 조건부 · 미측정. GVHMR 은 비상업 |
| Blender 버전 | PoC-1 · 2 | 재사용 후보 셋(2.1 · 2.2 · 2.3) 모두 4.4 에서 돌 근거가 코드에 있다. 5.x 가 필요한 것은 Reject · Reference 쪽뿐 → **4.4 유지가 기본안** |
| Tripo 유료 · 한도 | PoC-6 전 사용자 결정 | 1 캐릭터 = 생성 10 ~ 50 + 리그 25 크레딧 [확인: 리그 / 2.5 의 가격표] |
| 작업별 실행 위치 | PoC-4 의 나란히 비교 | 구조상 둘 다 Provider 로 둔다 |
| 최종 Motion Schema | PoC-2(좌표계) · PoC-3(confidence · 접지) · PoC-7 | v0.1 스키마 + SOMA 77 첫 프로필 안 |
| QA 기준값 | PoC-0 · 4 · 6 | 기존 실측 + 2.4 의 보정 범위 + 2.5 의 리그 지표 |
| UE 풀이기 유지 · 통합 범위 | PoC-4 | 비교 기준 + Provider 로 유지 |

---

## 7. 미확인

| 항목 | 이유 |
| :--- | :--- |
| 모든 후보의 실제 동작 | 실행하지 않았다 |
| Blender Lab 원본 MCP 의 저장소 · 라이선스 · Tool | bpy-dev 의 언급만 봤다 |
| Scenario skills 본문, Viggle · Scenario · Tripo 약관 | 열지 않았다 |
| AnyTop · UniRig 가중치 · ActionMesh 라이선스 | 열지 않았다 |
| 2.1 의 나머지 핸들러(sculpt · modeling · materials · uv_bake · reference · image_to_3d) | 이름만 봤다 |
| 2.5 의 나머지 파일(전체 553 중 22개 읽음) | 재사용 판단에 걸리는 것만 읽었다 |
| `bpy` 를 쓰는 스크립트의 배포 라이선스 조건 | Blender 재단 안내를 읽지 않았다 |
| 3DCharacterAutomationPipeline 이 4.4 에서 도는지 | 코드의 연산자 이름으로 추정했다 |
