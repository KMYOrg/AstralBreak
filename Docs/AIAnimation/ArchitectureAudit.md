# AI 애니메이션 생성 자동화 — Phase 0 감사

작성일: 2026-10-23  
개정 1: 2026-10-23 — 문서 검토 반영. 임포트의 스켈레톤 부작용, 생성 흐름에서 재할당 분기 제거, 전역 더티 검사, 명시적 재사용, 용어 통일(골든 → 회귀), 수치 정정.  
개정 2: 2026-10-23 — Phase 1 구현 중 실측으로 바뀐 사실을 §12 에 기록(§4 · §5 · §7 · §8 · §10 · §11 정정).  
개정 3: 2026-10-23 — Phase 2(기존 모션 재사용·변형) 구현 중 확인한 엔진 사실·측정을 §13 에 기록.  
개정 4: 2026-10-24 — Phase 4(Blender Provider) 착수 전 엔진·Blender 소스 대조와 에디터 실측을 §14 에 기록.  
개정 5: 2026-10-25 — Phase 5(로컬 AI · Kimodo) 설치 · 구현 · 리타깃 정렬 수정 · 통합 테스트에서 확인한 엔진 사실과 측정을 §15 에 기록.  
개정 6: 2026-10-25 — Phase 6(외부 AI · Meshy) 공식 문서 대조 · 어댑터 구현 · 차단 통합 테스트에서 확인한 것을 §16 에 기록. 실제 유료 1건은 미실행(사용자 Free 요금제 — Meshy 출력 리그는 미측정).  
개정 7: 2026-10-25 — Phase 7(AnimBP 연결 · 승격) 엔진 소스 대조 · 스파이크 · 통합 테스트에서 확인한 것을 §17 에 기록. 운영 AnimBP 실제 적용은 범위 밖(사용자 결정).  
개정 8: 2026-10-26 — Phase 8-1(생성 품질) 첫 실험 E1 · Kimodo 제약 · 후처리 소스 대조와 스파이크 · 통합 테스트에서 확인한 것을 §18 에 기록. C++ 변경 없음. 같은 날 보강: Persona 소견 후 수정안 A(2차 출력 스무딩) · B(손목 keep) · C(선별 보완)의 원인 · 재생성 실측 3행, 낫 기준 보정(기준 무기 · 궤적 폭 버전 3) 2행.  
상태: Phase 0 산출물 + Phase 1 · 2 · 4 · 5 · 6 · 7 · 8-1 실측 정정.  
관련 문서: [개발 지침서](DevelopmentGuide.md) (이 감사 결과로 개정 2) · [AnimGraphMcp README](../../Plugins/AnimGraphMcp/README.md)

**방법.** 코드 변경 없이 ① UE 5.7.4 엔진 소스 대조, ② 실행 중인 에디터(DebugGame, main `1f8ee47`)에서 Python 원격 실행 3회 + AnimGraphMcp 조회로 측정했다. 에디터 쪽은 **읽기 전용**이었다 — IK Rig는 임시 패키지 객체로만 만들었고 애셋 생성·저장은 0건, 더티 패키지는 측정 전후 모두 0개였다.

---

## 요약

| # | 확인 항목 | 결론 |
| :---: | :--- | :--- |
| 1 | Interchange 임포트 경로 | 가능. `bImportOnlyAnimations` + `Skeleton`으로 애니만 임포트. 단 **`bReplaceExisting`·`bAddCurveMetadataToSkeleton` 기본값이 `true`**라 둘 다 끈다(후자는 기존 스켈레톤을 더티로 만든다). 프로젝트 기본 파이프라인 애셋은 건드리지 말고 임시 복제본을 넘긴다 |
| 2 | 자동 캐릭터라이즈 | UE5 계열(Vesper·UEFN)·UE4 마네킹·Paragon은 성공. **Narmaya·SB는 실패**(`false`, 체인 0, FBIK도 실패) — 템플릿이 맞을 때만 동작하는 엔진 구조라 비표준 스켈레톤은 수동 체인이 필수 |
| 3 | 일괄 리타깃 컨텍스트 | 출력 폴더는 `NameRule.FolderPath`로 지정. **`bOverwriteExistingFiles=true`는 다른 애셋의 참조까지 바꾸고 기존 애셋을 강제 삭제**하므로 금지. 소스 애셋은 바뀌지 않음(복제본에만 작업). 저장은 하지 않음 |
| 4 | 기존 리타깃 애셋 | RTG 3개 모두 같은 구성(7 op, Run IK Rig 비활성, 체인 이름 1:1 매핑, 리타깃 포즈 양쪽 Default). 수동 조정 흔적이 없어 이 RTG와의 비교는 **회귀 기준**이지 품질 기준이 아니다 |
| 5 | 수치 기준선 | 절대 임계값은 쓸 수 없다(공격 모션 각속도 p99 ≈ 2,000°/s, 손가락 최대 3,762°/s). 검증은 **소스 대비 상대 비교**를 기본으로 하고 절대값은 명백한 깨짐(NaN, 90°/프레임 초과)에만 쓴다 |
| 6 | 의존성 영향 | 필요한 플러그인(IKRig · Interchange)은 이미 활성 상태라 에디터 로딩 영향 없음. 영향은 우리 모듈 컴파일 범위뿐 |
| 7 | 리타깃 소요 시간 | 읽기 전용으로는 측정 불가(리타깃 프로세서가 C++ 전용이고 실행하면 애셋이 생긴다). 샘플링 하한만 측정(0.11~0.19ms/프레임). 상한은 잠정 20개, Phase 1 첫 테스트에서 실측 후 확정 |

**지침서 정정(개정 2 반영):** 히어로 스켈레톤 경로가 틀렸다 — 실제는 `/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F`(히어로 애니 71개 · `ABP_Hero_Combat` 대상). 지침서에 적었던 `/Game/IdaFaber/...`는 기준 포즈가 같은 옛 사본이고 애니가 0개다. 그 밖의 정정은 §9.

---

## 1. Interchange FBX 임포트 경로

| 항목 | 확인 결과 | 근거 |
| :--- | :--- | :--- |
| FBX 임포트 담당 | Interchange (cvar `Interchange.FeatureFlags.Import.FBX` = `true`, 에디터 실측) | `InterchangeFbxTranslator.cpp:34` |
| 플러그인 | `Interchange` · `InterchangeEditor` 활성 | 에디터 실측 |
| 기본 파이프라인 스택 | `Assets` = `/Interchange/Pipelines/DefaultAssetsPipeline` | `InterchangeProjectSettings` 실측 |
| 애니만 임포트 | `UInterchangeGenericCommonSkeletalMeshesAndAnimationsProperties::bImportOnlyAnimations` + `Skeleton`(필수 — 없으면 `IsSettingsAreValid` 실패) | `InterchangeGenericAssetsPipelineSharedSettings.h:180-186, 226-232` |
| 메시 + 스켈레톤 + 애니 | `bImportOnlyAnimations=false`, `Skeleton` 비움 → 새 스켈레톤 생성 | 같은 파일 `:184` 주석 |
| 애니 세부 | `UInterchangeGenericAnimationPipeline::bImportAnimations` · `bImportBoneTracks` · 샘플레이트(`bUse30HzToBakeBoneAnimation` · 커스텀 레이트) | `InterchangeGenericAnimationPipeline.h:61-84` |
| 호출 | `UInterchangeManager::ImportAsset(ContentPath, SourceData, FImportAssetParameters, OutObjects)`(동기) · `ImportAssetWithResult` · `ImportAssetAsync` | `InterchangeManager.h:615-649` |
| 매개변수 | `bIsAutomated`(모달 없음) · `OverridePipelines`(`FSoftObjectPath[]`) · `DestinationName` · **`bReplaceExisting = true`(기본)** · `bForceShowDialog` | `InterchangeManager.h:382-420` |
| Python 노출 | `InterchangeManager` · `ImportAssetParameters` · `InterchangeGenericAssetsPipeline` · `InterchangeGenericCommonSkeletalMeshesAndAnimationsProperties` · `InterchangeGenericAnimationPipeline` · `InterchangeSourceData` 전부 있음 | 에디터 실측 |
| FBX 내보내기 (Phase 1 왕복 테스트용) | `AnimSequenceExporterFBX` · `FbxExportOption` · `AssetExportTask` 노출 | 에디터 실측 |

**Phase 1 결정:**

- `bIsAutomated = true`, **`bReplaceExisting = false`**. 같은 이름이 있으면 `ASSET_EXISTS`로 거부한다.
- **`bAddCurveMetadataToSkeleton = false`.** 기본값 `true`면 모프·머티리얼 커브를 임포트할 때 `USkeleton::AccumulateCurveMetaData`가 대상 스켈레톤에 메타데이터를 더하고 `MarkPackageDirty`를 부른다(`InterchangeAnimSequenceFactory.cpp:164-167`, `Skeleton.cpp:1826-1846`). 기존 스켈레톤(예: `/Game/Assets` 아래 히어로·마켓 스켈레톤)에 애니만 임포트하면 그 스켈레톤이 바뀐다. 이 설정과 전역 더티 검사(§10)로 막는다.
- **메시째 임포트**(`skeleton` 미지정)는 `bImportMaterials` · `bImportTextures` · `bCreatePhysicsAsset` · `bImportStaticMeshes`를 끈다(`InterchangeGenericMaterialPipeline.h:76` · `InterchangeGenericTexturePipeline.h:32` · `InterchangeGenericMeshPipeline.h:52, 227`). 리타깃 소스에는 스켈레탈 메시·스켈레톤·애니만 필요하다.
- 파이프라인은 `DefaultAssetsPipeline`을 **임시 패키지에 복제한 인스턴스**를 `OverridePipelines`로 넘긴다. 원본은 엔진 플러그인 콘텐츠라 수정하면 엔진 애셋이 더티가 된다.
- 임포트할 파일은 허용 루트(`[AnimGraphMcp] +ImportSourceRoots=`) 아래만 받는다. 에이전트가 넘긴 임의 경로로 에디터가 디스크를 읽지 않게 한다.
- **미확인:** 동기 `ImportAsset`을 HTTP 핸들러(게임 스레드) 안에서 불렀을 때 완료까지 대기가 정상인지. Python에서는 흔히 쓰는 경로지만 브리지 안에서는 Phase 1 첫 구현에서 확인한다. 문제가 있으면 `ImportAssetAsync` + 기존 잡 패턴(`job_id` + poll)으로 바꾼다.

---

## 2. 자동 캐릭터라이즈

임시 `IKRigDefinition`(디스크 애셋 아님)에 메시를 지정하고 `ApplyAutoGeneratedRetargetDefinition` → `ApplyAutoFBIK`를 실행했다.

| 스켈레톤 | 본 | 결과 | 펠비스 | 체인 | 소요 |
| :--- | ---: | :---: | :--- | ---: | ---: |
| Vesper `/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F` | 172 | 성공 | `pelvis` | 28 (메타카팔 8 포함) | 2.6ms |
| UEFN `SK_UEFN_Mannequin` | 88 | 성공 | `pelvis` | 28 | 1.4ms |
| UE4 마네킹 (CombatMaster `SK_Mannequin_Skeleton_DSAS`·`HS1`) | 68 | 성공 | `pelvis` | 20 (메타카팔 없음, Spine = `spine_01`~`spine_03`) | 1.1ms |
| Paragon `Greystone_Skeleton` | 180 | 성공 | `pelvis` | (체인 이름 미수집) | 2.1ms |
| UE4 마네킹 (`__AoeVFX`) | 68 | 성공 | `pelvis` | (미수집) | 1.1ms |
| **Narmaya** `pl1400_Skeleton` | 343 | **실패** | 없음 | 0 · FBIK도 실패 | 4.8ms |
| **SB** `CH_P_EVE_01_Body_LOD0_Skeleton` | 300 | **실패** | 없음 | 0 · FBIK도 실패 | 4.2ms |

- **엔진 동작:** `ApplyAutoGeneratedRetargetDefinition`은 `FAutoCharacterizeResults::bUsedTemplate`가 거짓이면 아무것도 하지 않고 `false`를 반환한다(`IKRigController.cpp:447-471`). 알려진 템플릿(UE5 마네킹·Fortnite 등, `IKRigAutoCharacterizer.h:328`)과 계층이 맞아야만 동작한다는 뜻이다. 비표준 스켈레톤은 부분 성공도 없다.
- **Python 한계:** 템플릿 이름과 매칭률(`BestTemplateName` · `BestPercentageOfTemplateScore`)은 `GetAutoCharacterizer()`(C++ 전용)로만 얻는다. `FBoneChain`의 시작/끝 본 필드도 Python에서 안 보여 컨트롤러 getter(`GetRetargetChainStartBone` 등)로 읽어야 했다. `inspect_skeleton`·`create_ik_rig`는 C++로 구현해 템플릿 정보를 응답에 넣는다.
- **Phase 1 결정:**
  - `create_ik_rig`는 `mode: auto | manual`을 받는다.
  - auto가 실패하면 `IKRIG_AUTO_FAILED`와 함께 **본 이름 목록과 계층**을 응답에 담는다. Claude Code가 그걸 보고 `chains[]`를 만들어 manual로 다시 부르는 2단계 흐름이 정상 경로다.
  - Narmaya·SB 테스트는 manual 경로 검증이 된다.

---

## 3. 일괄 리타깃 (`UIKRetargetBatchOperation`) 동작

| 동작 | 확인 결과 | 근거 (`IKRetargetBatchOperation.cpp`) |
| :--- | :--- | :--- |
| 출력 위치 | `NameRule.FolderPath`(기본값 `/Game`)에 복제. 정적 `DuplicateAndRetarget`은 폴더 인자가 없어 항상 `/Game` 루트 | `EditorAnimUtils.h:27`, `EditorAnimUtils.cpp:480` |
| 이름 충돌 | 기본: `CreateUniqueAssetName`으로 숫자 접미사 | `EditorAnimUtils.cpp:484` |
| **덮어쓰기** | `bOverwriteExistingFiles=true`면 같은 이름 애셋을 **`ForceReplaceReferences`(다른 애셋이 그걸 참조하던 것까지 새 애셋으로 바꿈) → `ForceDeleteObjects`** | `:658-707` |
| 소스 애셋 | 바뀌지 않음. 준비·변환·추가 플래그 복원은 모두 복제본에만 적용(`AnimationAssetsToRetarget`가 복제본 목록으로 교체됨). 소스는 `GetAnimPoseAtFrame`으로 읽기만 함 | `:202`, `:216-276`, `:375-435` |
| 참조 동반 | `bIncludeReferencedAssets` — 몽타주 세그먼트·프리뷰 포즈, BlendSpace 샘플(`HandleAnimReferenceCollection`). 입력이 AnimBlueprint면 **부모 ABP까지 복제·재컴파일** | `:33-101`, `:302-335` |
| 프레임 변환 | 프레임마다 소스 포즈 샘플(`GetAnimPoseAtFrame`, 루트 모션을 포즈에 포함) → `FIKRetargetProcessor::RunRetargeter` → 로컬 포즈 → `SetBoneTrackKeys` | `:415-511` |
| 커브 | 복제본의 Transform 커브 삭제, 커브 리맵 op 적용 | `:233`, `:526` |
| 진행 창 | `FScopedSlowTask::MakeDialog(취소 버튼)`. 취소하면 `ObjectTools::DeleteObjects(확인창 표시)` — **모달** | `:938-946`, `:776-791` |
| 알림 | 콘텐츠 브라우저 선택 동기화 + 토스트 | `:709-757` |
| 저장 | 하지 않음 — 새 패키지는 더티로 남음 | 파일 전체 |

**Phase 1 결정:**

- `retarget_animations`는 정적 함수 대신 C++에서 `FIKRetargetBatchOperationContext`를 채워 `RunRetarget`을 부른다. `FolderPath`는 허용 목록 안의 출력 경로로 둔다.
- `bOverwriteExistingFiles`는 **항상 `false`**다. 같은 이름이 있으면 실행 전에 `ASSET_EXISTS`로 거부한다(엔진의 숫자 접미사 회피에 맡기지 않는다).
- 입력은 AnimSequence · AnimMontage · BlendSpace만 받는다. AnimBlueprint는 `BAD_REQUEST`로 거부한다(ABP 복제·재컴파일 부작용).
- `dry_run`은 `GenerateAssetLists`와 같은 규칙으로 동반 애셋 목록만 돌려준다.
- 저장은 `save` 인자로 명시할 때만 한다(기존 Tool과 같은 규약).

---

## 4. 기존 리타깃 애셋 (회귀 비교 기준)

| 애셋 | 소스 | 타깃 | 비고 |
| :--- | :--- | :--- | :--- |
| `RTG_HSwordToH` | `IK_AutoGeneratedSource` (UE4 `SK_Mannequin_HS1`, 20 체인) | `IK_AutoGeneratedTarget` (**옛** `/Game/IdaFaber/.../SK_StreetDemon_F_02`, 28 체인) | 타깃 프리뷰도 옛 사본 |
| `RTG_KatanaToH` | `IK_AutoGeneratedKat` (UE4 `SK_Mannequin_HK`) | `IK_AutoGeneratedTargetKat` (`/Game/Assets/IdaFaber/.../SK_StreetDemon_F_02`) | |
| `RTG_AutoGeneratedHandS` | `IK_AutoGeneratedSourceHandS` (UE4 `HS1`) | `IK_AutoGeneratedTargetHandS` (`/Game/Assets/...`) | |

세 RTG의 구성은 똑같다.

- **op 7개:** Pelvis Motion · FK Chains · Run IK Rig(**비활성**, 자식 Retarget IK Goals) · Root Motion · Remap Curves · Pin Bones
- **체인 매핑:** 같은 이름끼리 1:1. 타깃 메타카팔 8개는 소스에 없어 `None`.
- **리타깃 포즈:** 양쪽 `Default Pose`.
- **IK Rig:** 모두 솔버 1개(자동 FBIK).

해석:

- 엔진 `AddDefaultOps`는 op 5개(Pelvis Motion, FK Chains, Run IK Rig + IK Chains, Root Motion, Curve Remap — `IKRetargeterController.cpp:336-350`)다. 기존 RTG에는 **Pin Bones가 더 있고 Run IK Rig가 꺼져 있다.** 사람이 바꾼 것인지 에디터 생성 경로의 기본값인지는 확인하지 못했다. 회귀 비교 전에 `create_ik_retargeter`의 op 구성을 이 7개에 맞추는 옵션(`ops: "match_existing"`)을 둔다.
- 리타깃 포즈 편집 흔적이 없고 체인 매핑도 자동 결과와 같다. 그래서 이 RTG와의 비교는 **"우리 Tool이 에디터 수동 절차와 같은 결과를 내는가"를 보는 회귀 테스트**다. 리타깃 품질 자체는 §5의 상대 지표와 사람의 검수로 본다.
- `IK_AutoGeneratedTarget`·`RTG_HSwordToH`가 옛 `/Game/IdaFaber` 사본을 참조한다(애셋 정리 문서의 남은 숙제와 같은 사실). 회귀 비교는 `/Game/Assets/...`를 가리키는 `RTG_KatanaToH` 또는 `RTG_AutoGeneratedHandS`로 한다.

---

## 5. 포즈 샘플링 비용과 수치 기준선

`/Game/Animation/Hero/Vesper` 아래 AnimSequence 57개 중 단일 프레임인 AimOffset 9개를 뺀 48개를 측정했다. 루트 모션은 포즈에 포함, 컴포넌트 공간 기준.

### 5.1 비용

| 항목 | 값 |
| :--- | :--- |
| `GetAnimPoseAtFrame` 1프레임 (172본) | 0.15~0.19ms (짧은 클립의 첫 호출 0.5~1.9ms) |
| 같은 작업, UE5 Manny 소스 (161본) | 0.11~0.13ms |
| Python에서 본 172개 읽기 (`get_bone_pose` × 172) | 0.69~0.78ms/프레임 — 샘플링의 약 5배 |

→ 검증 계산은 **C++에서** 한다. C++에서는 `GetAnimPoseAtTimeIntervals`(UFUNCTION 아님 — Python 미노출)도 쓸 수 있다.

### 5.2 기준선 (요약)

| 분류 | fps | 각속도 p99 (°/s) | 최대 (°/s, 본) | 착지 발 수평 속도 p50 (cm/s) | 루프 경계 최대 차 |
| :--- | :---: | :--- | :--- | :--- | :--- |
| Idle · AimIdle | 30 | 5~113 | 8~170 (머리카락·옷) | 0.1~0.4 | 0.2~1.8° |
| Walk 루프 10종 | 30 | 313~453 | 638~1,108 (`ball_*`) | 3.7~22 | 6.3~19° |
| Run 루프 10종 | 30 | 611~825 | 813~2,080 (손가락·`ball_*`) | 4.6~38 | 6.6~31° |
| Rifle Jog 8방향 | 30 | 232~370 | 362~918 | 3.6~87 | 5.5~21° |
| Rifle Turn 90/180 (RM) | 30 | 277~549 | 655~867 | 0.8~3.6 | — |
| Rifle 반동 · 장전 | 30 | 155~855 | 375~1,014 (손가락) | 0 | — |
| 점프 계열 7종 | 30 | 79~888 | 170~2,037 | 0~292 | — |
| **Sickle 공격 (RM)** | 60 | **1,641~2,046** | **2,427~3,762** (`hand_r`·손가락) | 5~289 | — |

관찰:

- **절대 각속도 임계값은 쓸 수 없다.** 정상 공격 모션의 p99가 2,000°/s 근처이고 손가락은 3,700°/s를 넘는다. 관측된 프레임당 최대 회전은 약 70°(30fps 런 루프의 `index_03_l`)였다.
- **발 미끄러짐을 높이 임계값(최저 + 3cm)으로 판정하면 잡음이 크다.** 정상 Walk 루프도 최대값이 400~590cm/s까지 튄다(발이 뜨고 닿는 프레임이 섞임). 피벗하는 공격 모션(`Sickle_Attack3`)은 정상인데도 `foot_r` p50이 246cm/s다.
- **루프 경계 차이**(첫·끝 프레임)는 정상 루프에서도 31°까지 나온다. 한 프레임 동안의 정상 움직임이다.
- **데이터 이슈(기존):** `AS_Vesper_Jump_FallLoop`에 스켈레톤에 없는 본(의상 본 `f_adv_skirt_*`, `f_champ_*` 등)을 가리키는 Transform 커브 20개가 있어 샘플링할 때 경고가 난다. 일괄 리타깃은 복제본의 Transform 커브를 지우므로 결과에는 영향이 없다.
- `AS_Vesper_Sickle_Slash1`과 `AS_Vesper_Sickle_Attack1`은 측정 수치가 모두 같고 루트 모션 플래그만 다르다(같은 데이터로 보이지만 출처는 확인하지 않았다).

**Phase 1 검증 설계 (§13 개정):**

| 종류 | 규칙 | 상태 |
| :--- | :--- | :--- |
| 절대 — 명백한 깨짐만 | NaN · 비정상 스케일 · 한 프레임 회전 > 90° (관측 최대 약 70°) | `FAILED` |
| 상대 — 리타깃 결과 vs 소스 | 체인별 각속도 p99 비율, 착지 발 속도 p50 비율(다리 길이 비로 보정), 루트 이동 거리 비율(펠비스 높이 비로 보정) | 허용 범위 밖이면 `PASSED_WITH_WARNINGS` |
| 루프 | 경계 차이 / 프레임당 중앙값 차이 비율 | 비율이 크면 경고 |
| 시각 | 항상 `needs_review` | `NEEDS_REVIEW` |

허용 비율의 초기값은 Phase 1 첫 리타깃 결과(기존 RTG 출력)에서 정한다. 지금 숫자를 정하면 근거 없는 값이 된다.

---

## 6. 의존성 영향

| 추가 의존 모듈 | 소속 | 프로젝트에서 활성 |
| :--- | :--- | :---: |
| `IKRig` (Runtime) · `IKRigEditor` (Editor) | 플러그인 IKRig (`EnabledByDefault: true`) | ✅ (에디터 실측) |
| `InterchangeCore` · `InterchangeEngine` | 엔진 모듈 (`Engine/Source/Runtime/Interchange`) | — (엔진) |
| `InterchangePipelines` | 플러그인 Interchange | ✅ |
| `AnimationBlueprintLibrary` (`UAnimPoseExtensions`) | 엔진 에디터 모듈 | — (엔진) |
| `IAnimationDataController` | `Engine` 모듈 인터페이스 (구현은 AnimationDataController 개발자 모듈, 직접 링크 불필요) | — |

- 필요한 플러그인이 이미 켜져 있어 에디터 로딩 시간·메모리 영향은 없다. 영향은 `AnimGraphMcpEditor` 모듈의 컴파일 범위가 넓어지는 것뿐이다.
- `AnimGraphMcp.uplugin`에 `"Plugins": [{"Name": "IKRig", "Enabled": true}, {"Name": "Interchange", "Enabled": true}]`를 선언해 다른 프로젝트로 옮겨도 의존성이 드러나게 한다.
- **모듈 배치:** Phase 1은 같은 `AnimGraphMcpEditor` 모듈에 Tool 파일을 추가한다. 디스패처 등록 API가 모듈 Private이라 두 번째 모듈을 만들면 공개 API부터 필요하다. 모듈 분리는 Tool 수가 늘어 빌드 시간이 문제가 될 때 다시 본다.

---

## 7. 일괄 리타깃 소요 시간

- **측정하지 못했다.** `FIKRetargetProcessor`는 Python에 노출되지 않고, `RunRetarget`을 돌리면 애셋이 생겨 읽기 전용 조건을 깬다.
- **추정:** 애셋 하나 = 복제 + 프레임 수 × (샘플링 0.11~0.19ms + `RunRetargeter` 미측정) + 키 기록 + (저장 시) 압축.
- **결정:** `[AnimGraphMcp] MaxRetargetAssetsPerCall=20`(잠정). Phase 1 완료 기준 1번 테스트에서 애셋당 시간을 기록하고, 프록시 타임아웃(`COMPILE_TIMEOUT` 180초) 안에 여유 있게 들어오도록 상한을 확정한다.

---

## 8. 스켈레톤 호환성 — 이름이 같다고 호환되지 않는다

| 소스 스켈레톤 | 본 | Vesper와 공통 이름 | 기준 포즈 로컬 회전 차 (p50 / 최대) | 본 길이 비 (p50, 최소~최대) |
| :--- | ---: | ---: | :--- | :--- |
| 옛 `/Game/IdaFaber/.../SKEL_UE5_F` | 172 | 172 | 0.00° / 0.06° | 1.000 (1.00~1.00) |
| UE4 마네킹 (CombatMaster DSAS) | 68 | **68 (전부)** | 10.7° / 40.8° | 1.33 (0.06~3.60) |
| UEFN 마네킹 | 88 | 85 | 7.9° / 42.9° | 1.03 (0.00~1.84) |
| UE5 Manny (CombatMaster DSAS1) | 161 | 87 | 7.8° / 39.1° | 1.08 (0.72~1.60) |
| IdaFaber 남성 `SKEL_UE5_M` | 143 | 87 | 8.6° / 40.4° | 1.07 (0.76~1.60) |
| Narmaya · SB | 343 · 300 | 0 · 0 | — | — |

- **UE4 마네킹은 본 이름이 전부 Vesper에 있다.** 그래서 기존 `reassign_skeleton`의 `BONES_MISSING` 검사(이름 기준)를 통과하지만, 기준 포즈가 10~40° 다르고 본 길이가 최대 3.6배 달라 결과가 틀어진다.
- 엔진의 메시 호환 판정(`USkeleton::IsCompatibleMesh`)도 이름 집합 기준이다.
- **결정:** `inspect_skeleton`에 `compare_to` 인자를 두고 위 표의 지표와 판정(`same_rig` | `needs_ik_retarget` | `no_common_bones`)을 돌려준다.
  - `same_rig` = 기준 포즈 회전 최대 < 1° ∧ 길이 비 0.99~1.01. **판정은 참고 정보다.** 생성 흐름은 `same_rig`여도 `retarget_animations`(복제 후 작업)로 처리한다. `reassign_skeleton`은 애셋을 제자리에서 옮겨 원본이 바뀌므로 생성 흐름에 쓰지 않는다.
  - CombatMaster의 AnimSequence 1,195개(UE4 마네킹 585 · UE5 Manny 610)를 포함한 현재 소스 풀은 전부 `needs_ik_retarget`다.

---

## 9. 지침서 정정 (개정 2로 반영)

| 위치 | 개정 1 | 정정 |
| :--- | :--- | :--- |
| §2.2 · §9 · §14 히어로 스켈레톤 | `/Game/IdaFaber/Meshes/Girl/SKEL_UE5_F` | `/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F` (프리뷰 `SK_StreetDemon_F_01`). 옛 사본은 애니 0개 |
| §2.3 포즈 샘플링 | `GetAnimPoseAtTimeIntervals` 포함 | 이 함수는 UFUNCTION이 아니라 C++ 전용. Python은 `GetAnimPoseAtFrame`/`AtTime` |
| §2.3 Control Rig | `UControlRigSequencerEditorLibrary` | Python 이름은 `ControlRigSequencerLibrary`(ScriptName) |
| §2.3 · §10 일괄 리타깃 | 덮어쓰기 위험 미기재 | `bOverwriteExistingFiles` 금지 · AnimBlueprint 입력 거부 · 취소 시 모달 |
| §2.3 · §10 Interchange | 설정 키 미확인 | `bImportOnlyAnimations` + `Skeleton`, `bReplaceExisting=false`, 파이프라인 임시 복제 |
| §10 자동 매핑 | "부분 실패면 수동" | 비표준 스켈레톤은 **부분 성공 없이 전부 실패** → 수동 체인이 정상 경로 |
| §10 재할당 vs 리타깃 | 미기재 | 이름 겹침이 아니라 기준 포즈 차로 판정 (§8) |
| §13 수치 검증 | 절대 임계값 전제 | 소스 대비 상대 비교 + 명백한 깨짐만 절대값 (§5) |
| §14 Phase 1 완료 기준 2 | 골든 비교 = 품질 비교 | 회귀 비교. 기존 RTG가 기본 자동 구성이라 품질 기준이 아님 (§4) |

---

## 10. Phase 1 Tool 시그니처 확정안

모두 기존 봉투·오류 체계를 쓴다. 공통 규칙:

- 쓰기 Tool은 `save` 기본 `false`이고 `[AnimGraphMcp] +GenerationOutputPaths=` 밖 경로는 `OUTPUT_PATH_NOT_ALLOWED`로 거부한다.
- 쓰기 Tool은 호출 전후 **전역 더티 패키지 집합**을 비교한다. 허용 목록 밖 패키지가 새로 더티가 되면 아무것도 저장하지 않고 `UNEXPECTED_DIRTY`(목록 포함)로 실패한다.
- 기존 IK Rig·RTG 재사용은 `existing_*`로 명시할 때만 한다. 메시는 항상 명시한다.

| Tool | 입력 | 결과 (`result`) |
| :--- | :--- | :--- |
| `inspect_skeleton` | `skeleton?` \| `skeletal_mesh?`, `details=false`, `compare_to?`(스켈레톤 경로) | `skeleton_path`, `meshes[]`, `bone_count`, `root_bone`, `bones[]`(details: 이름·부모·기준 로컬/컴포넌트), `virtual_bones[]`, `sockets[]`(스켈레톤+메시), `slot_groups[]`, `curve_count`, `ik_rigs[]`, `retargeters[]`, `animation_count`, `template_match{used, name, percent}`, `compare{common, missing_in_other, ref_rot_diff_deg{p50,max}, bone_length_ratio{p50,min,max}, verdict}` |
| `import_animation_file` | `file`(허용 루트 아래 절대 경로), `dest_path`, `skeleton?`(주면 그 스켈레톤에 애니만, 없으면 메시·스켈레톤째 새로), `sample_rate?`, `name?`, `save=false` | `imported[]`, `animations[]`, `skeleton`, `mesh?`, `source_frame_rate`. 같은 이름이 있으면 `ASSET_EXISTS`. 커브 메타데이터 추가·재질·텍스처·피직스·스태틱 메시는 항상 끔(§1) |
| `create_ik_rig` | `asset_path`, `skeletal_mesh`(필수), `existing_rig?`(주면 재사용 — 메시와 호환되지 않으면(`IsSkeletalMeshCompatible`) `BAD_REQUEST`, 프리뷰 메시가 다르면 `diagnostics` 경고), `mode: auto\|manual`, `pelvis?`, `chains?[{name, start, end, goal?}]`, `fbik=true`, `save=false` | `asset_path`, `reused`, `template_match`, `pelvis`, `chains[]`, `solvers`. auto 실패면 `IKRIG_AUTO_FAILED` + `details.bones[]`(이름·부모) |
| `create_ik_retargeter` | `asset_path`, `source_rig`, `target_rig`, `source_mesh`, `target_mesh`(필수), `existing_retargeter?`(주면 그 RTG의 IK Rig가 `source_rig`·`target_rig`와 같은지 검증 후 재사용), `ops: default\|match_existing`, `auto_align=false`, `save=false` | `asset_path`, `reused`, `ops[{name, enabled, parent}]`, `chain_mapping{target: source}`, `unmapped_target_chains[]` |
| `retarget_animations` | `retargeter`, `assets[]`(Sequence·Montage·BlendSpace), `source_mesh`, `target_mesh`(필수), `output_path`, `name_rule{prefix, suffix, replace_from, replace_to}`, `include_referenced=true`, `dry_run=false`, `validate=true`, `save=false` | `planned[]`(dry_run), `generated[{source, asset}]`, `referred[]`, `seconds_per_asset[]`, `validation`(validate 시). 상한 초과 `BAD_REQUEST` · 이름 충돌 `ASSET_EXISTS` · AnimBlueprint 입력 `BAD_REQUEST` |
| `validate_animation` | `assets[]`, `sources?[]`(같은 순서 — 상대 비교), `checks?["structural","numeric","relative"]`, `thresholds?{}` | 애셋별 `status`, `structural[]`, `numeric{ang_speed_p50/p99/max, max_deg_per_frame, foot_planted_p50, loop_boundary_ratio, root_travel_cm}`, `relative{...}`, `needs_review[]` |

**설정 추가** (`[AnimGraphMcp]`, 기존 키는 그대로):

```ini
+GenerationOutputPaths=/Game/Animation/Generated/
+GenerationOutputPaths=/Game/Animation/Test/
+ImportSourceRoots=Saved/AnimGen/Import/        ; 프로젝트 기준 상대 경로
MaxRetargetAssetsPerCall=20                     ; 잠정 — Phase 1 실측으로 확정
```

이 ini가 출력·임포트 경로의 **유일한 기준**이다. `get_editor_status`가 `GenerationOutputPaths`·`ImportSourceRoots`를 응답에 넣고, Phase 3의 `anim_gen`은 그것을 읽는다(정책 파일에 경로를 따로 두지 않는다).

**Python 프록시:** `Tools/mcp/anim_graph_mcp/server.py`에 6개 함수만 추가한다(로직 없음). 리타깃·임포트 호출은 `COMPILE_TIMEOUT`(180초)을 쓴다.

---

## 11. Phase 1 위험과 미확인

| 항목 | 영향 | 대응 |
| :--- | :--- | :--- |
| 동기 Interchange 임포트를 게임 스레드 HTTP 핸들러에서 대기 | 멈춤 가능성 | 첫 구현에서 확인, 안 되면 `ImportAssetAsync` + 잡 패턴 |
| 일괄 리타깃 진행 창의 취소 → 삭제 확인 모달 | 자동화 중 사람이 취소하면 브리지가 모달에 묶임 | 문서화. 취소 버튼을 끌 수 없는 엔진 코드라 사용 안내로 대응 |
| 리타깃 소요 시간 미측정 | 상한 20이 맞지 않을 수 있음 | 완료 기준 1번에서 실측 |
| 상대 검증 허용 비율 미정 | 경고 남발 또는 놓침 | 기존 RTG 출력으로 초기값 설정 후 기록 |
| `IK_AutoGeneratedTarget`·`RTG_HSwordToH`가 옛 스켈레톤 사본 참조 | 회귀 비교 혼선 | `RTG_KatanaToH`/`RTG_AutoGeneratedHandS`를 기준으로 사용 |
| Narmaya·SB 수동 체인 정의 | 343·300본 중 체인 지정은 사람이 계층을 보고 판단 | Tool은 본 목록·계층을 주고, 체인 결정은 Claude Code가 제안 → 사용자 확인 |
| 생성 경로가 스모크 경로(`SmokeTestPaths=/Game/Animation`) 안 | 생성된 몽타주가 "Slot 노드 없음" 경고를 받음 | 의도된 동작 — 생성물도 구조 검사를 받는다. 승격 전 경고는 정상 |

---

## 12. Phase 1 실측 정정 (개정 2)

Phase 1 구현(C++ Tool 6개)과 통합 테스트(`Tools/mcp/anim_gen_phase1_test.py`)에서 이 문서의 가정과 다르게 나온 것.

| 위치 | 이 문서 (개정 1) | Phase 1 실측 | 근거 |
| :--- | :--- | :--- | :--- |
| §4 기존 RTG 의 출처 | "사람이 바꾼 것인지 에디터 생성 경로의 기본값인지 확인 못 함" | 에디터 **"Retarget Animations" 창의 자동 생성**(`FProceduralRetargetAssets`) 산출물이다. 이 경로가 7 op 구성(Run IK Rig 끔 · Pin Bones 추가) · FK 체인 정확 매핑 · 루트 모션 op 설정을 만든다. `create_ik_retargeter ops: match_existing` 이 이 레시피를 그대로 재현해 결과가 본별 0° 로 같다 | `SRetargetAnimAssetsWindow.cpp:633-743` · 회귀 비교 |
| §4 리타깃 포즈 | "양쪽 Default Pose, 편집 흔적 없음" | 이름은 `Default Pose` 지만 **타깃 포즈는 자동 정렬돼 있다**(34본, 최대 20.234°) — 같은 자동 생성 경로의 `AutoAlignAllBones(Target)`. 사람의 수동 조정 흔적이 없다는 결론은 그대로 | `retarget_poses` 비교 |
| §4 핀 본 이름 | — | 기존 애셋은 템플릿의 `Root`, 새 애셋은 스켈레톤의 `root` 로 저장된다. FName 이라 같은 본이다(비교는 대소문자 무시) | `pin_bones` 비교 |
| §5 절대 규칙 "한 프레임 > 90° = 깨짐" | 히어로 애니 관측 최대 약 70° | 30fps **마켓 공격은 손·손가락이 93~109°/프레임**(`Katana_Attack_Slash1` `middle_03_l` 109.17° · `Slash2` `hand_r` 97.5° · `Combo2` 93.3°). 그대로 리타깃하면 결과도 같다 → 소스가 주어지면 소스 최대 + 10° 이내는 경고 `ROTATION_JUMP_INHERITED`. 소스 없이 측정하면 여전히 `FAILED` | `validate_animation` |
| §5.2 루프 경계 | 경계 최대 차 6.3~31°("한 프레임 동안의 정상 움직임") | `validate_animation` 은 **실제 첫·끝 샘플 키**를 비교한다 — 끝 키가 첫 키와 같은 루프(프로젝트 루프 전부)는 0~0.31°. 감사 측정은 마지막 직전 프레임 → 첫 프레임(한 프레임 이동)이라 정의가 다르다. 비율 = 경계 평균 차 / 프레임당 평균 차의 중앙값 | 히어로 루프 19종 |
| §5.2 기준선 재현 | — | C++ 측정이 감사 수치를 재현: Walk p99 315~456(감사 313~453) · Sickle 공격 p99 1,710~2,074(1,641~2,046) · 최대 회전 70.28° `index_03_l`(약 70°, 같은 본) · Idle 5.7·113.7. 애셋당 0.02~0.07초 | `validate_animation` |
| §7 리타깃 소요 시간 | 미측정, 잠정 상한 20 | `RunRetarget` 1.6~2.4ms/프레임(단일), 20개·1,329프레임 0.6~1.4초. 검증·저장 포함 20개 3.0초 → **상한 50**(애셋당 300프레임이어도 약 35초) | `retarget_animations` |
| §8 SB 공통 본 이름 | 0 | **1**(`Root` = `root`) — 엔진의 본 이름은 FName(대소문자 무시). 감사 측정은 대소문자 구분 문자열 비교였다. Narmaya 는 0 그대로 | `inspect_skeleton compare_to` |
| §8 UE4 DSAS 길이 비 p50 | 1.33 (0.06~3.60) | 1.29 (0.06~3.59) — 최소·최대는 같고, p50 차이는 길이 0 본 제외 기준(0.01cm) 차이로 보인다. 회전 차 10.7°/40.8° 는 그대로 | `inspect_skeleton compare_to` |
| §10 `retarget_animations.seconds_per_asset[]` | 애셋별 배열 | 평균값 + `frames` · `ms_per_frame`. 엔진이 복제·준비·변환을 애셋 묶음 단위로 돌려 애셋 하나만의 시간은 잴 수 없다 | `IKRetargetBatchOperation.cpp:942-946` |
| §10 `import_animation_file` 대상 | "같은 이름이 있으면 ASSET_EXISTS" | **대상 폴더가 비어 있어야 한다**(`ASSET_EXISTS` reason `DEST_NOT_EMPTY`). FBX 에서 생길 이름(메시 = 파일 이름, 애니 = `<파일>_Anim`, 스켈레톤 = `<파일>_Skeleton`)을 미리 다 알 수 없어서. 같은 이름이 있으면 엔진이 재임포트로 바꾸거나 대화상자를 띄운다 | `InterchangeManager.cpp:1914-2002` |
| §11 동기 Interchange 임포트 | 멈춤 가능성 | 정상 — `bRunSynchronous=true` 가 작업을 호출 스레드에서 끝까지 돌린다. 메시째 1.3초, 애니만 0.2초 | `InterchangeManager.cpp:1705-1712` |
| (신규) 엔진 함정 | — | `UIKRetargeterController::GetChainMapping(NAME_None)` 은 "첫 매핑" 이 아니라 **첫 op(Pelvis Motion)의 nullptr** 를 돌려준다. 체인 매핑은 FK Chains op 에서 직접 읽는다 | `IKRetargeterController.cpp:1062-1077` |
| (신규) 엔진 함정 | — | `RunRetarget` 은 만든 애셋 목록을 돌려주지 않는다(private). 출력 경로는 엔진 이름 규칙(`FNameDuplicationRule::Rename`)으로 먼저 계산하고, 충돌을 실행 전에 거부해 숫자 접미사가 생길 여지를 없앤다 | `IKRetargetBatchOperation.h:188-195` |

---

## 13. Phase 2 실측 (개정 3)

Phase 2 구현(`search_animations` · `preview/apply_animation_edits` · `validate_animation` 요청 충족)과 통합 테스트(`Tools/mcp/anim_gen_phase2_test.py`)에서 확인한 것.

| 항목 | 가정 | 실측 | 근거 |
| :--- | :--- | :--- | :--- |
| 미러 짝 없는 본 | 엔진 `MirrorPose` 가 전신을 반전 | 5.7 `UMirrorDataTable::FillMirrorBoneIndexes` 는 짝 없는 본(척추 · 골반 · 루트)을 `INDEX_NONE` 으로 두고, `MirrorPose` 는 그런 본을 **건너뛴다**(주석은 "falling back to mirroring to self"). 편집 op 는 짝 없는 본을 자기 자신으로 반전한다 → TurnLeft_90 미러의 좌우 손·발·머리 속도가 원본 반대쪽과 0.1 cm/s(출력 반올림) 안에서 같고 루트 Yaw −90° → +90° | `MirrorDataTable.cpp` `FillMirrorBoneIndexes` · `AnimationRuntime.cpp` `MirrorPose` |
| 미러와 커브 | — | 커브는 반전되지 않는다(엔진도 `CurveToMirrorCurveMap` 은 런타임 노드용). 부호 있는 커브(`remainingturnyaw`)는 반대 방향 동작과 어긋난다 → 경고 `MIRROR_CURVES_UNCHANGED` + `limitations[]` | TurnLeft_90 |
| 애셋 복제 | `IAssetTools::DuplicateAsset` | 소스 컨트롤이 켜져 있으면 즉시 저장 · 이름 충돌 시 모달 → 공통 가드 안 `StaticDuplicateObject` (원본 패키지 더티 0 · .uasset SHA-256 불변 확인) | `AssetTools.cpp` `PerformDuplicateAsset` · `CanCreateAsset` |
| 길이 변경과 노티파이 | — | `SetNumberOfFrames` → 길이 변경 알림 → 시퀀스가 노티파이·싱크 마커를 옮긴다. 비우고 길이를 바꾼 뒤 출처로 다시 건다(TurnLeft_90 ×2 리타임 + 0.1초 트림: 0.5125 · 0.775 → 0.156 · 0.288) | `AnimSequenceBase.cpp:1275` |
| `bLoop` 레지스트리 태그 | 루프는 인덱스에 있다 | `AssetRegistrySearchable` 이 아니다 → 루프 판정은 로드가 필요(`max_loads`). 길이 · 프레임 · fps · 루트 모션 · additive 태그는 마켓 시퀀스 1,237개 전부에 있다 | `AnimSequenceBase.h` · `search_animations` |
| 이음매 비 | 앞뒤를 섞은 창의 중앙값 | 포즈 유지 경계처럼 한쪽이 정지면 섞은 중앙값이 반으로 떨어져 "멈춤"을 튐으로 센다(Attack3 준비 → 유지 2.75). 앞 · 뒤 창 중앙값 중 큰 쪽으로 → 1.23 · 1.25 | `SeamStepRatio` |
| 빨라진 동작의 한 프레임 회전 | 소스 최대 + 10° 안이면 물려받은 튐 | 1.5배 리타임은 소스의 튐도 1.5배가 된다(Finisher1 `upperarm_twist_01_r` 113.6° — 소스 최대 82.0°). apply 의 내장 검증은 기준을 소스 최대 × 최대 재생 속도(123.1°)로 둔다. 재생 속도를 모르는 바깥 `validate_animation` 은 같은 애셋을 `ROTATION_JUMP` 로 본다 | `apply_animation_edits` · `validate_animation` |
| 리타기터 `default` vs `match_existing` (부록 B) | 품질 차이 미측정 | 같은 소스(HK `Katana_Attack_Combo2`)의 두 결과 본별 회전 차 p50 6.6° · p99 98.7° · 최대 178°(`ik_hand_*`) — `default` 의 Run IK Rig 가 IK 본과 손 위치를 바꾼다. Narmaya 수동 체인은 `match_existing` 이면 `PASSED`(각속도 p99 비 1.09, 최대 12°/프레임), `default` 는 자동 정렬과 상관없이 `FAILED`(179°/프레임 뒤집힘, 비 5.7) | `anim_gen_phase2_test.py` appendix |
| 상대 검증 허용 비율 (부록 B) | 초기값(각속도 0.5~2.0 · 발 ≤ 3.0 · 루트 0.67~1.5)은 Phase 1 한 건 근거 | 3계열 9건(UE4 HK · UE4 HS1 · UE5 Manny DSAS1)이 모두 범위 안: 전체 각속도 p99 비 0.71~0.86(Vesper 가 본이 많아 낮다) · 공통 본 p99 비 1.00~1.05 · 착지 발 0.94~2.26 · 루트 1.00 → 초기값 유지 | `anim_gen_phase2_test.py` appendix |

---

## 14. Phase 4 실측 (개정 4)

Blender 4.4.1 headless 변환 + 에디터 임포트(`import_animation_file`)로 확인했다. 스파이크는 합성 BVH(관절 11개, 키 183 단위, 발끝 +Z, 루트가 프레임당 2 cm 앞으로)를 0° · 180° 회전으로 변환해 `/Game/Animation/Test/AIAnimation/P4Spike/`에 미저장으로 임포트했다.

| 항목 | 가정 | 실측 | 근거 |
| :--- | :--- | :--- | :--- |
| 아마추어만 있는 FBX | Interchange 가 메시 없이 스켈레톤을 만들 수도 있다 | 못 만든다 — 스켈레톤 팩토리 노드는 스킨 메시마다, 애니 파이프라인은 기존 스켈레톤 지정 때만 관절에서 만든다. 본마다 가중치 1.0 기둥 메시를 붙이면 메시 · 스켈레톤 · 애니 3개가 새로 생긴다(0.07초) | `InterchangeGenericSkeletalMeshPipeline.cpp:181-314` · `InterchangeGenericAnimationPipeline.cpp:642-694, 850` · 스파이크 |
| 루트 본 | Blender 아마추어 객체가 루트 본이 될 수 있다 | 객체 이름 `Armature` 면 Interchange 가 그 널을 뺀다 → 루트 = `Hips`, 본 11 = BVH 관절 11 | `FbxScene.cpp:780-790` · 스파이크 |
| 단위 | Blender m ↔ UE cm 배율 문제 | 장면 `scale_length` 0.01 + `apply_unit_scale` + `FBX_SCALE_NONE` → 노드 스케일 1 · 모든 기준 본 스케일 1 · 좌표가 BVH(cm) 그대로(`LeftUpLeg` x = 10) | `export_fbx_bin.py:3453-3463` · 스파이크 |
| 축 | — | BVH `(x, y, z)` → UE `(x, z, y)`: BVH +Z 발끝 → UE +Y, `LeftUpLeg` +X 그대로. Vesper(`SKEL_UE5_F`)도 +Y 정면 · `thigh_l` +X → 회전 없이 같은 손잡이 | `inspect_skeleton details` |
| Vesper 정면 | 지침서 부록 B "Vesper −Y 쪽" | **+Y** — 기준 포즈 `foot_l` (11.95, −3.45, 9.45) → `ball_l` (12.90, 8.26, 2.55). 키 171.45 cm | `inspect_skeleton details` |
| 정면 회전 | 회전 적용이 루트 이동을 돌리는가 | 돌린다 — 180° 변환의 루트가 0 → −60 cm(0° 는 +60 cm), 발끝 −Y · `LeftUpLeg` x −10. BVH 위치 키가 기준 포즈 로컬 공간이라서 | `import_bvh.py:577-580` · report `root_path` |
| BVH 기준 포즈 높이 | — | 루트 OFFSET 0 → 기준 포즈 골반 z = 0, 발 −98 cm. 리타기터 Pelvis Motion op 는 소스 골반 높이가 0 근처면 높이 1 로 두고 이동을 대상 높이배로 키운다 → 가장 낮은 점을 z = 0 으로 올리고 루트 위치 키에서 뺀다: 임포트 기준 포즈 골반 98 cm · 최저 0, 애니 골반 높이 98 cm 유지 | `PelvisMotionOp.cpp:183-196` · 스파이크 |
| BVH 임포터 프레임 | `frame_start=0` 이면 키 0 부터 | 첫 키가 1(1 미만은 올림) — 0 기준이라고 보고 범위를 맞추면 첫 프레임이 겹치고 끝 프레임이 빠진다(60 cm 이동이 58 cm). 실제 첫 키 기준으로 옮겨 해결(범위 5~25 → 루트 −10 → −50 cm 정확) | 스파이크 |
| 포즈 평가 갱신 | — | `Armature.transform` 뒤 태그 + `view_layer.update()` 가 없으면 포즈 평가가 이전 기준 포즈를 쓴다(내보낸 FBX 는 맞았고 측정만 틀림) | 스파이크 |
| 자동 캐릭터라이즈 | BVH 이름은 템플릿 밖 | 합성 이름(Hips · LeftUpLeg · LeftToeBase · Spine · Head)은 **Mixamo 템플릿 57.7%** 로 통과 — 체인 Spine · Head · LeftLeg · RightLeg(골 2) | `inspect_skeleton.template_match` |
| 원격 실행 | — | 이 에디터에서 Python 원격 실행(UDP 6766)이 노드를 찾지 못한다 — 측정은 플러그인 Tool 과 Blender report 로 한다 | `Tools/ue_exec.py` |
| 임포트 리샘플 (CMU) | `sample_rate=30` 이면 Interchange 가 30 fps 로 굽는다 | CMU 01_01(2,752프레임 @ 120 fps = 22.925초)은 30 fps 로 687.75프레임 — 경계가 안 맞아 `CreateAnimSequenceFactoryNode` 가 애니를 건너뛴다(`bSnapToClosestFrameBoundary` 기본 false). 같은 FBX 를 `sample_rate` 0 으로는 2,752프레임 애니가 정상. 합성 BVH(1초 = 30프레임)는 경계라 통과했었다 → blender 가 범위 끝을 경계로 당긴다(끝 3프레임) | `InterchangeGenericAnimationPipeline.cpp:714-807` · 직접 임포트 비교 |
| CMU 단위 | cm · m · inch 중 하나 | 기준 포즈 키 25.65 단위 — 어느 표준 단위로도 사람 키가 안 된다(CMU ASF 단위는 약 1/0.45 inch) → 170 cm 정규화(cm/단위 6.627, `SCALE_NORMALIZED`). 리타깃 상대 비가 모두 허용 범위라 동작 크기 영향은 없다 | 계획 · `validate_animation` |
| CMU 정면 · 손잡이 | — | 발끝 +Z(BVH) → UE +Y, 편차 0.06° — Vesper 와 같아 회전 0. `LeftUpLeg` 쪽이 +X(UE)로 Vesper `thigh_l` 과 같은 쪽 | 계획 · 임포트 스켈레톤 |
| CMU 자동 캐릭터라이즈 | 비표준 이름이라 실패 | **HumanIK / Motionbuilder 템플릿 64%** 로 성공 → 체인 없이도 리타깃 `PASSED_WITH_WARNINGS`. 수동 체인 9개(골반 `Hips`, `LHipJoint`·`RHipJoint` 제외)와 같은 판정 | `inspect_skeleton.template_match` · 통합 `auto` |
| CMU 0번 프레임 | 첫 프레임부터 동작 | 0번 프레임은 회전 채널 73개 중 4개만 0 이 아닌 기준 포즈 → 1번 프레임에 179.8° 튐(소스 · 결과 모두, `ROTATION_JUMP_INHERITED`). `range.start` 로 빼면 최대 50.4°/프레임 · `PASSED` | BVH 데이터 · 통합 `trim` |
| 소요 시간 (CMU) | — | Blender 4.4~5.5초(그중 FBX 내보내기 2.4초, 5.4 MB) · 임포트 1.2초 · 계획~저장 전체 9.8초 | report · 통합 |

---

## 15. Phase 5 실측 (개정 5)

Kimodo 설치 · `local_ai` 구현(커밋 단위 1 · 2), 손가락 꺾임에서 시작한 리타깃 정렬 수정 세션들(per_bone · 축 체인 · 머리 · 메타카팔 · 손가락 체인 · 팔-몸통 관통), 통합 테스트(`Tools/mcp/anim_gen_phase5_test.py`, 단위 3)에서 확인한 것. 측정 방법은 C++ 추가 없이 `validate_animation profile_bones` + `profile_positions`(관절 위치 → 구간 방향 · 손 기준틀 · 마디 굽힘)로 했다.

| 항목 | 가정 | 실측 | 근거 |
| :--- | :--- | :--- | :--- |
| Kimodo 설치 (Windows · Python 3.13) | 조사 §5: Linux 개발 · 문서 예시 Python 3.10 · `motion_correction` 빌드 실패 가능 | 시스템 Python 3.13 venv 로 동작. NVIDIA 잠금 버전 72개 그대로(numpy 만 3.13 휠이 있는 2.3.5) · torch 2.14.1+cu130 · `motion_correction` VS2022 빌드 성공(후처리 켬). 비공식 휠 안 씀 | 설치 기록 |
| Hugging Face 다운로드 | — | 캐시 심볼릭 링크 경합(`WinError 1314` — 개발자 모드 없이 심볼릭 링크 불가) → 링크 없는 방식 + `--max-workers 1`. 게이트 모델 파일 해시는 익명 API 가 `****` 로 가려 인증 API 로 대조. pip 제약 파일의 한글 주석은 cp949 로 읽혀 실패 → 인자 · 제약 파일은 ASCII | 설치 기록 |
| Kimodo BVH 기준 포즈 | 기본(BONES-SEED 형식)으로 충분 | 기본 기준 포즈는 회전 0 이 서 있는 자세가 아니라 `bvh.py` 의 단위 · 정면 측정이 틀린다 → `motion_to_bvh(standard_tpose=True)` | 스파이크 |
| Kimodo BVH 루트 | 조사 §5 위험 — 원점 래퍼 `Root` | 그대로 리타깃하면 Root Motion op 가 정지한 `Root` 를 복사해 Vesper `root_travel_cm` 0(골반만 걸어 나감). 리타기터 op 를 바꾸면 Phase 1 ~ 4 경로가 다 바뀌므로 Kimodo 출력 안에서 고친다: `root_track` 이 모델의 바닥 궤적 `smooth_root_pos` · 방향 `global_root_heading` 을 `Root` 에 넣고 `Hips` 를 그 기준 상대값으로(펼친 θ) | `local_ai/root_track.py` · 통합 |
| 루트 이동 배율 | 소스 이동 그대로 | Root Motion op(`CopyFromSourceRoot`)는 소스 루트 이동 × Pelvis Motion op 전역 배율(골반 높이 비). 제약 3초 앞 400 cm: Kimodo 396.6 cm → Vesper 406.5 cm(프레임 1 → 끝), 비 1.047 = 골반 높이 105.24 / 100.52 | `RootMotionGeneratorOp.cpp:281-312` · 통합 `constraint` |
| 루트 경로 제약 (`root2d`) | — | 3초(끝 프레임 90)에 앞 400 · 왼쪽 0 cm · 방향 180°: Kimodo 끝 루트 앞 397.2 · 왼쪽 1.1 cm · 방향 182.5°. 방향은 (cos, sin) 으로만 고정돼 **도는 쪽은 모델이 정한다**(이번엔 왼쪽). Vesper 루트 Yaw Δ −181.98°(UE Yaw + = 오른쪽 — Kimodo θ + = 왼쪽과 부호 반대, 같은 방향). 결과는 `FOOT_SLIDE_RATIO` 3.86(허용 3.0) 경고 — 3초에 4 m + 180° 도는 빠른 동작이고 소스(후처리한 Kimodo) 착지 발 속도가 낮아 비가 커진다. 6초 걷기는 1.756 | 통합 `constraint` · `generate` |
| Kimodo 시간 · 메모리 | 조사: 미측정 | 에디터를 띄운 채 1건 51 ~ 88초(torch 임포트 18 ~ 47 · 모델 적재 24 ~ 28 · 확산 생성 8.5 ~ 13 · 내보내기 0.3초 — 그날 첫 실행이 가장 느림, 4건) · RAM 약 15 GB · VRAM < 3 GB. 기본 기한 300초 안. 취소는 torch 임포트 중인 프로세스를 2초 만에 종료(report · BVH 없음) | `report.json seconds` · 통합 `cancel` |
| SOMA 자동 캐릭터라이즈 | 조사 §5: `LeftLeg`(넓적다리) 오매핑 가능 | Mixamo 템플릿으로 잡혀 손가락이 한 마디 밀린다(`LeftIndex` = Index1 ~ 3 — 메타카팔부터). → SOMA 수동 체인 27개(몸 9 + 손 18: 엄지 Thumb1 ~ 3 · 손가락마다 메타카팔 Hand{F}1 + Hand{F}2 ~ 4, End 제외) | `FINGER_CHAINS_DIFFER` · `test_soma_chains_map_every_finger_by_standard_name` |
| 손가락 꺾임 | 소스에 없는 손가락은 대상 기준 포즈로 남는다(`UNMAPPED_TARGET_CHAINS` 문구) | 자동 정렬이 꺼진 Run IK Rig op 의 퍼지 매핑을 따라 꺾는다(지침서 §2.3). SOMA 9체인 왼손 MCP/PIP: 검지 120.3/−30.3 · 약지 107.8/−30.3 · 새끼 −109.4/130.5 · 순서 정상 0%(가운데만 멀쩡) → 모든 op 정확 매핑 뒤 기준 포즈 ±0.3° · 순서 100%. Phase 4 CMU 결과도 같은 패턴(검지 MCP 63.8°) → ±0.2°. `RTG_KatanaToH` 회귀 본별 0° · 리타깃 포즈 34본 20.234° 그대로 | `IKRetargetProcessor.cpp:1496, 1675` · `RunIKRigOp.cpp:150` · `IKRetargetChainMapping.cpp:222-242` |
| 팔꿈치 굽힘 전달 | 아래팔 오차 = 위팔 롤 | 롤이 아니다 — 굽힘 평면 회전 0.00°, 굽힘 전달 0.87 / 0.85배 = Vesper 팔꿈치 param 0.5116 ÷ CMU 0.5886 / 0.6035. FK Interpolated 가 대상 본 param 위치의 소스 회전을 섞는다. CMU 아래팔 구간 방향 p50 7.56 / 8.10° → `per_bone`(1:1) 0.02 / 0.02°(비 1.00), HK 6.1 / 5.7° → 0.02° · 손 굴림 ±7.3 → −0.03 / +0.06° | `FKChainsOp.cpp:283-291` |
| SOMA 기준 포즈 = 0프레임 | 임포트 스켈레톤 기준 포즈 = FBX 기준 포즈 | Interchange 가 바인드 포즈 무효 → 첫 프레임 재바인드(이분 탐색: 손가락 둘째 마디 아래, 계층 깊이 ≥ 10 이 있으면 무효 — FBX 행렬은 일관, SDK 정밀도 판정 0.0001 cm). 미터 FBX 는 유효하지만 루트 본 스케일 100. → 기준 포즈 2프레임 FBX + 2단 임포트: SOMA 쇄골 구간 13.3 / 29.4° → 5.8 / 5.8°, 발 26.8 / 17.3° → 13.4 / 13.4°. CMU(깊이 ≤ 9)는 원래 유효 | `InterchangeSkeletalMeshFactory.cpp:792-808` |
| 머리 · 목 · 몸통 | — | 엔진 자동 정렬은 머리(param 1)를 건너뛰고 펠비스(`AlignPelvisBone`) · 척추 접선 · 목을 소스 기준 포즈 몸통 모양에 맞춘다 → 모든 프레임에 일정 오프셋. ④ 머리 중립: 얼굴 들림 오차 CMU +6.84 → −0.31°, SOMA −3.72 → 0.00°. ⓪ 축 체인 중립: 목 윗마디(Vesper 대비) CMU +19.7 → +6.3°, SOMA −27.3 → −19.4°, 허리 CMU +11.9 → +1.3°. 팔 · 손 · 다리 관절 회귀 0. 남은 "젖혀 보임"은 소스 동작(CMU 8.7초에 37° 올려다봄) | `IKRetargeterPoseGenerator.cpp:107, 249, 386` · 측정 |
| 메타카팔 → 첫 마디 | — | 손바닥 해부 차로 3 ~ 7° 일정하게 어긋난다(SOMA MCP 최대 −17.5°). 메타카팔을 소스로 돌리면 손 굴림 −3.6° · 손바닥 변형 → 기각. 메타카팔은 대상 그대로 · 손가락은 메타카팔 상대(②'): MCP ±0.6 · 옆 벌림 ≤ 1° · 손 굴림 불변, 대가 = 손가락 전역 방향 3 ~ 7° · 오른 중지 PIP −0.75°(FK 전역 델타의 1차 오차) | 측정 |
| 메시 vs 스켈레톤 기준 포즈 | 같다 | Vesper 스켈레톤(메시 46개 공유) 기준 포즈와 `SK_StreetDemon_F_01` 의 손가락 로컬 회전이 최대 14.13°(`index_metacarpal`) 다르다 → 미매핑 손가락 비교는 대상 메시 기준(스켈레톤 기준이면 고친 결과도 30본 > 2° 오탐) | `fingers` 검사 |
| 손가락 체인 제안기 | — | 이름 없는 위상 · 좌표로: SOMA 18(템플릿과 다름 8 · 없음 8) · Vesper 18 · UE4 10(= 템플릿) · Narmaya 14(약지 · 새끼만 메타카팔) · SB 10 · CMU 0(`NO_HANDS` — 기준 포즈 좌우 손 높이 1 ~ 2.6 cm 비대칭이라 팔 짝 실패, 어차피 손가락 1개). 안전망: 수정 전 SOMA 결과 4종 경고(미매핑 16본 최대 147° · 순서 100% 깨짐), HK · Vesper 원본 57개 경고 0 | `AnimMcpFingerChains` · `AnimGraphMcp.Generation.FingerChains` |
| 팔-몸통 관통 | 위팔 매핑이 맞으면 관통 없음 | 위팔 월드 방향은 소스와 같다 — 원인은 체형(어깨 관절 반폭 CMU 21.5 · Vesper 12.0 cm, 엉덩 8.8 · 9.1 cm) + 옷(코트 · 벨트 · 파우치 — 같은 CMU 결과를 F_01 로 재면 49 / 73%, Lingerie 메시로는 20 / 33%). 판정을 '가장 가까운 몸 정점 법선'으로 하면 깊이 박힌 점에서 방향이 엉켜 보정 p50 20 ~ 30° · 보정 뒤에도 18 ~ 21% → **반경 지도**로 바꿈. 관통 프레임(왼/오른): CMU → Vesper 49.3 / 72.8% → 0 / 0(보정 p50 · 최대 9.0 · 17.3 / 14.5 · 26.7°, 팔꿈치 각 변화 0.06°), SOMA 71.7 / 0 → 0 / 0, HK 6.9 / 0 → 0 / 0, CMU → UE4 마네킹 9.3 / 19.3 → 0 / 0. 통합: Kimodo 걷기 52.5 / 45.3 → 0 / 0(최대 13.2 / 11.2°), 제약 클립 3.3 / 17.6 → 0 / 0. Vesper 원래 애니도 18 ~ 35%(기준선: UE4 카타나 7개 중 5개 0 — 원래 마네킹 메시) | `AnimMcpBodyClearance` · `AnimGraphMcp.Generation.BodyClearance` |
| Phase 4 CMU 회귀 수치 | 10-24 기준(§14 · 지침서 §14 Phase 4) 그대로 | 같은 CMU 01_01 요청이 anim_gen 기본 `per_bone` 정렬 + `body_clearance resolve` + 2단 임포트를 거치면서: 각속도 p99 비 0.833 → 0.868 · 착지 발 1.513 → 1.444(둘 다 허용 범위 — 정렬 · 관통 보정 각각의 기여는 따로 재지 않았다. 정렬 쪽 근거는 위 '팔꿈치 굽힘 전달' 행) · 골반 높이 0.975 · 루트 이동 1.299 · 최대 179.75°/프레임(`ROTATION_JUMP_INHERITED`) · Trim 50.44° `PASSED` · 자동 IK Rig HumanIK 64% 는 그대로. 관통 프레임 49.3 / 72.8% → 0 / 0(위팔 보정 최대 17.3 / 26.7°). 잡 9.8 → 27.2초(관통 보정 · 손가락 검사 · 2단 임포트 · 재검증이 더해짐 — 단계별 시간은 따로 재지 않음). 플러그인 기본(`align_mode engine`)을 쓰는 Phase 1 회귀는 `RTG_KatanaToH` 대비 본별 0° 그대로 | `anim_gen_phase4_test.py` · `phase1` 재실행 |
| 프레임 렌더 비교 비용 | 기한에 부담 | Blender Workbench 백그라운드: CMU 2,749프레임 4행 × 2뷰 1.9 ~ 2.6초, 12행 × 2뷰 + 레퍼런스 4 = 시트 2085 × 2994(상한 전 4344 × 6222 · 10.7 MB → 긴 변 3000 px 로 줄임), Kimodo 6초 4행 × 2뷰 2.2초 · 시트 1424 × 2078 — 기한 300초의 1% 안팎 | `review_render.py` · 통합 `generate` |

---

## 16. Phase 6 실측 (개정 6)

Meshy 공식 문서 · 약관(2026-10-25 열람, 지침서 부록 A)과 어댑터 구현 · `httpx.MockTransport` pytest · 실제 에디터 차단 통합(`Tools/mcp/anim_gen_phase6_test.py blocked`)에서 확인한 것. 실제 유료 1건은 **미실행**으로 마감 — 사용자 계정이 Free 요금제라 API 생성이 402 로 막힌다(문서 3곳). 아래 '출력 리그' 행은 문서 확인까지이고 실측이 아니다.

| 항목 | 가정 | 확인 | 근거 |
| :--- | :--- | :--- | :--- |
| 길이 · 모드 | 지침서 §2.4 "길이 범위는 Phase 6 에서" | 2 ~ 10초 · 0.5초 단위(필수, 다른 값 400) · prime(FBX, 기본) / swift(BVH) · 프롬프트 ≤ 400자. 요청 `duration_seconds` 는 0.5초로 맞춰 보내고(`DURATION_SNAPPED`) 결과 길이는 측정해 적는다 | text-to-motion 문서 |
| 가격 | 공식 가격표가 있으면 확정 | 크레딧만 공식(prime 10 · swift 3, 실패 0 = 환불). 돈 값은 요금제 페이지가 지역 통화(KRW)로만 보이고 크레딧 팩 가격은 비공개 → 문서로 USD 를 확정할 수 없다. 사용자 결정: 정책 `usd_per_credit`(없으면 `COST_UNKNOWN`) | pricing · meshy.ai/pricing |
| 잔액 · 사용 내역 | — | 잔액 `GET /openapi/v1/balance` 무료(`balance · monthly_credits · permanent_credits`) → 제출 직전 확인. 사용 내역은 Studio · Enterprise 만이라 대조에 못 쓴다 | balance · usage |
| 멱등 · 불확실 제출 | 멱등 키 헤더가 있을 수 있다 | 없다. 메타데이터 태그(`X-Meshy-Metadata`)는 Studio · Enterprise 만 반영되고, 태스크 객체에 프롬프트가 없다 → 목록으로 "방금 만든 태스크"를 고를 근거가 시각뿐 — 남의 태스크를 채택할 수 있어 자동 채택을 뺐다. 응답 없음 · 5xx 는 `SUBMISSION_UNCERTAIN`(다시 내지 않음, Meshy 안내 "클라이언트 타임아웃 뒤 바로 다시 만들지 말 것"과 같다) | errors · metadata · task-lifecycle |
| 취소 | 외부 작업 취소 API 가 있을 수 있다 | text-to-motion 취소 없음(`CANCELED` 는 Creative Lab 만). DELETE 는 PENDING 만 환불 · IN_PROGRESS 409 → 지침서대로 결과 무시 · 예약 유지 | text-to-motion · task-lifecycle |
| Rate Limit | — | 초당 20 요청(전 요금제) · 동시 태스크 Pro 10. 초당 초과 429 는 `Retry-After`, 동시 초과 429(`NoMorePendingTasks`)는 없음 → 앞은 같은 시도에서 기다렸다 한 번 더, 뒤는 `RATE_LIMITED`(승인 범위 안 재시도). poll 의 429 · 5xx 는 실패가 아니다(Meshy 안내) | rate-limits · task-lifecycle |
| 결과 URL | 만료 시각 고정 | `motion_url` 은 읽을 때마다 재서명, 보존 3일(`expires_at`). 다운로드 403 · 404 면 태스크를 다시 읽어 새 URL 로 한 번 더. 기록에는 서명 쿼리를 뺀 URL | text-to-motion · asset-retention |
| 키 노출 경로 | 로그 · 기록만 막으면 된다 | 결과 URL 은 다른 호스트(저장소) — 같은 클라이언트로 받으면 Authorization 이 그 호스트로 간다 → 헤더 없는 별도 클라이언트. API 리다이렉트는 따르지 않는다(POST 가 GET 으로 바뀌고 키가 다른 곳으로 갈 수 있다 — authentication 문서). 기본 URL 은 정책으로 바꿀 수 없다 | authentication · pytest `Authorization 은 API 호스트에만` |
| 테스트 키 | 무료 테스트 키로 통합 테스트 | 2026-09-16 폐지(401) → 실제 호출은 유료 1건뿐. 차단 통합은 더미 키(카나리 — 실수로 보내면 401 이 요청 로그에 남는다)로 했다: 기본 정책 · `FREE_ONLY` · 환율 없음 · 승인 없음 → 요청 로그 파일 없음 · 장부 0 | changelog · 통합 `blocked` |
| 출력 리그 | Meshy 리그 → 리타깃 필수 | 문서에 본 이름 · 기준 포즈 · 단위 · 축 · fps · FBX 안 메시 여부가 없다 → 실제 1건에서 잰다(미실행 — 유료 요금제에서 `--real` 이 `real.rig` 에 기록). 처음은 자동 IK Rig(실패하면 본 계층으로 수동 체인 제안) · 정면은 실행 때 측정 | text-to-motion · rigging |
| Free 요금제 | 무료 크레딧으로 API 1건 | Free 요금제(월 100 크레딧)는 API 접근이 없다 — 생성 요청은 402(`INSUFFICIENT_CREDITS` 로 분류, 예약 해제 · 과금 없음). 잔액 조회는 될 수 있으나 생성은 유료 요금제만 | text-to-motion · errors · credits guide |
| 다른 외부 후보 | Tripo 무료 API 로 대체 | Tripo3D 에는 텍스트 → 모션이 없다(리깅된 모델에 프리셋 적용만) → 모션 Provider 로 채택 안 함. 메시 생성은 애니 파이프라인 밖 별도 트랙(지침서 §14 끝) | developers.tripo3d.com |
| 약관 · 데이터 | — | 유료 요금제 출력 소유 · 비 Enterprise 입력 · 출력 학습 사용 가능(§2.9) · 경쟁 AI 학습 금지(§2.6(xi)) · API 출력 3일 뒤 삭제(§2.5) · 지역 제한 없음. 사용자 수용(2026-10-25) | terms-of-use · privacy-policy |

---

## 17. Phase 7 실측 (개정 7)

엔진 소스(`AssetRenameManager.cpp` · `AssetFixUpRedirectors.cpp` · `MessageDialog.cpp` · `AnimSequence.cpp`) 대조, 스파이크(rename · 복제 더티 · 복제본 시나리오), 통합 테스트(`Tools/mcp/anim_gen_phase7_test.py` — 실패 0 · 체크 85)에서 확인한 것. 운영 AnimBP 에는 쓰지 않았다(전후 SHA-256 · revision 같음).

| 항목 | 가정 | 확인 | 근거 |
| :--- | :--- | :--- | :--- |
| rename 저장 | 사후 더티 비교로 부작용을 잡는다 | 엔진이 새 패키지 · 참조 패키지 · 리디렉터를 `PromptForCheckoutAndSave(bPromptToSave=false)` 로 **저장까지** 끝낸다 → 더티로는 안 보인다. 그래서 사전 검사(참조자 분류 · 맵 · 미저장 참조자 · 보호 · CDO) + `confirm` + 저장 이벤트(`UPackage::PackageSavedWithContextEvent`)로 저장 집합을 따로 검사 | `AssetRenameManager.cpp:1978-1995` · 스파이크 `saved_packages` |
| rename 비용 · 결과 | — | BS 1개 0.59 ~ 0.61초. 저장 = 새 패키지(+ 참조자). 리디렉터 0 · 옛 파일은 엔진이 지움(`removed_files` 0 — 남는 경우 대비 코드만) · 내용 해시 같음. 시퀀스 승격은 참조자 BS · 몽타주까지 저장 | 스파이크 · 통합 `promote` |
| 이미 더티인 참조자 | 남의 편집은 건드리지 않는다 | 엔진은 이미 더티인 패키지의 소프트 참조도 고치고, 하드 참조자는 로드해 저장한다 → 미저장 편집이 있는 참조자는 남의 편집까지 저장된다 → `DIRTY_PACKAGES REFERENCER_DIRTY` 로 거부(통합에서 복제본을 미저장으로 두고 재현) | `AssetRenameManager.cpp:1742-1745, 921-1090` · 통합 |
| 리디렉터 조건 | — | 참조자가 맵(:1032) · 못 읽음(:1068) · 컬렉션 · 읽기 전용 · SCC 비로컬(:994) · 네이티브 CDO 소프트 참조(:796)일 때만 남긴다. 맵은 사전 거부, 나머지는 사후 `FixupReferencers(DeleteFixedUpRedirectors)` — 레지스트리가 로딩 중이 아니면 동기 | `AssetRenameManager.cpp` · `AssetFixUpRedirectors.cpp:534-560` |
| CDO 모달 | — | 네이티브 클래스 CDO 가 하드 · 소프트로 가리키면 OkCancel(기본 Cancel) → 무인 모드에서 rename 중단. 하드 참조는 사전 검사로 `CDO_REFERENCED`, 소프트는 엔진이 실행 때 멈추면 `ENGINE_ABORTED`(아무것도 안 옮김). 이 프로젝트에 해당 애셋이 없어 재현하지 않았다 | `AssetRenameManager.cpp:437-468, 708-807` · `MessageDialog.cpp:172` |
| 참조 확인 | 레지스트리 참조자가 바로 바뀐다 | 레지스트리 의존성은 디스크 기준이라 저장 직후 늦을 수 있다(7-5 실측) → 엔진이 저장한 파일을 `ScanModifiedAssetFiles` 로 다시 읽힌 뒤 `GetReferencers(dest)` ⊇ 이전 참조자(배치 안은 새 경로로 바꿔) 확인. 통합: 복제본 ABP .uasset 이 새 BS 경로를 담고 옛 경로 문자열은 없음 | 통합 `promote` |
| 메모리 객체 dest | 레지스트리에 없으면 비었다 | `GetAssetByObjectPath(bIncludeOnlyOnDiskAssets=false)` 가 메모리 애셋도 본다 — Automation 에서 메모리에만 만든 `UCurveFloat` 가 `DEST_EXISTS` 로 잡혔다(`DEST_IN_MEMORY` 는 레지스트리가 애셋으로 안 볼 때의 대비) | `AnimGraphMcp.Generation.Promote` |
| `ABP_Hero_Combat` 복제 더티 | 복제 · 컴파일이 ALI · 공급자 ABP 를 더티로 만들 수 있다 | `generation_guard` 로 복제하면 새로 더티 = 복제본 1개, 컴파일도 추가 더티 없음 → 복제본 검증 경로가 가드 아래에서 된다 | 스파이크 `guard.newly_dirty` |
| 복제본 시나리오 | — | `ABP_Hero_Combat` 복제본(네이티브 부모 `AstralAnimInstance`)도 PIE 스폰 · 몽타주 재생 · 슬롯 관측이 된다. PIE 10프레임 ≈ 0.47 ~ 0.57초 — 0.23초 반동 몽타주는 5프레임 뒤 끝나 슬롯 꺼짐, `Loop → Loop` 섹션이면 활성. UpperBody(반동 루프 additive) · DefaultSlot(Kimodo 칼 4초) 둘 다 활성 | 스파이크 · 통합 |
| 전이 시나리오 | 런타임 테스트 ABP 의 Run 상태 플레이어에 `set_asset $blendspace` | Run 상태 플레이어는 SequencePlayer 라 BlendSpace 를 못 받는다 → `remove_node` + BlendSpacePlayer(`$blendspace`) + `K2Node_VariableGet Speed` → X + StateResult 연결로 교체. 복제본 Speed 300 → `Run` · 0 → `Idle` | 통합 `chain_bs` |
| additive 기본 | `AnimFrame 0` + 기준 시퀀스 없음 | `IsValidAdditive` 는 `AnimFrame` · `AnimScaled` 에 `RefPoseSeq` 를 요구 → 기본을 `LocalAnimFrame 0` 으로, `AnimFrame` 이면 `ref_pose_sequence`(`$asset`) 필수. 반동(원래 Mesh Space · 자기 프레임 기준) 복제본을 `LocalSpaceBase` / `LocalAnimFrame` 으로 바꿔도 유효 | `AnimSequence.cpp:2615-2640` · 통합 `chain_montage` |
| 스모크 테스트 이름 | `<ABP>_Test` 로 충분 | 스모크 테스트 이름이 애셋 이름이고 필터가 접두 · 부분 일치라 Job 마다 같은 이름이면 옛 복제본까지 돈다 → 복제본 이름에 Job 꼬리(`_Test_<job 6자>A<시도>`) | `AnimMcpSmokeTests.cpp:62-71` · `AnimMcpAutomationRunner.cpp:138` |
| revision 과 무변경 op | — | 이미 같은 값인 `set_property`(런타임 테스트 ABP Slot `bAlwaysUpdateSourcePose` 가 원래 true)는 revision 이 그대로다(해시는 정상 — 값이 안 바뀜). 적용 메커니즘 시험은 실제로 바뀌는 값으로 | 통합 `apply_mech` 1차 실패 → 정정 |

---

## 18. Phase 8-1 실측 (개정 8)

생성 품질 단위(지침서 §14 Phase 8 — 8-1)에서 확인한 것. 첫 실험 E1 은 제품 코드를 바꾸기 전에 통합 테스트 `exp1` 섹션으로 했고(2026-10-26), Kimodo 쪽은 에디터 없이 전용 venv 스파이크 3회(모델 1회 적재 · 같은 1차에서 2차 변형 비교)로 Kimodo 소스(`kimodo/constraints.py` · `postprocess.py` · `MotionCorrection/src/cpp/AnimProcessing/Utility.cpp` · `BindingsPython.cpp`)와 대조했다. C++ 변경 없음.

| 항목 | 가정 | 실측 | 근거 |
| :--- | :--- | :--- | :--- |
| 관통 보정이 양손 파지를 깼나 (E1) | `resolve` 가 왼 위팔을 98% 프레임에서 최대 15.5° 돌려 파지를 깼을 수 있다(10-25 가설) | 같은 seed 를 `measure` 로: Vesper 손목 간격 최소 36.5 · p50 51.0 cm — 20 cm × scale(21.05 cm) 안 **0%**. `resolve` 와 비교: 간격 p50 +1.9 · 최대 +4.1 cm, 왼 손목 이동 p50 2.9 · 최대 5.7 cm, 위팔 방향 차 p50 8.2 · 최대 14.2°, 오른손 · 발 0 cm, 파지였다가 깨진 프레임 0 → **파지가 처음부터 없었고 보정은 더 벌렸을 뿐**. 같은 seed 결정성: `measure` 관통 39.7% · 3.5 cm = 기록의 보정 전 값, Kimodo 루트 105.66 cm · 72.4 cm · 0.41° 같음 | 통합 `exp1` · `KimodoSword1025_185815` 기록 |
| Vesper 발 좌우 비 | 소스 비(4.45 · 4.81)와 비슷 | Vesper p50 5.12 · p90 5.55 — 리타깃은 다리 각도를 옮기고 Vesper 엉덩 관절 폭(≈ 18 cm)이 SOMA(20.1 cm)보다 좁아 비가 커진다. 설계 벌점 `(p90 − 2.5) / 2.5` 는 5.0 에서 1.0 으로 포화해 넓은 후보끼리 구별이 안 된다 → 폭 5.0 으로 정정(기준 시험 0.61) | 통합 `exp1` · `selection.py` |
| SOMA30 ↔ 77 | `*End` 잎 관절 회전이 부모 회전일 것 | 77 출력 로컬 회전 → `SOMASkeleton30.from_SOMASkeleton77`(이름 대응 `get_skel_slice`) → `fk(local, root)` 의 공통 관절 위치가 77 출력과 **0.0 m** 차(손가락 사슬 끝인 `*End` 제외). 30 이름은 모두 77 에 있다 | 스파이크 `fk_check_m` |
| 2차 생성 제약의 후처리 | 후처리(`post_processing`)가 end-effector 목표를 강제한다(설계: `EndEffectorConstraintSet(joint_names=[LeftHand, RightHand])`) | 후처리 마스크는 **클래스 이름**(`fullbody` · `left-hand` · `right-hand` · `left-foot` · `right-foot` · `root2d`)만 본다 — 일반 `end-effector` 는 확산 조건만 받는다. 고정 목표는 제약의 **전역 회전**을 FK 로 다시 푼 포즈에서 얻고, 루트 xz 는 매끈한 루트로 바꾼다(`extract_input_motion_from_constraints`). 변형 비교(seed 20261025, meet): A `left-hand` · `right-hand` + 후처리 → 처음 · 끝 12프레임이 1차 손 간격(63.5 cm)으로 되돌아가고 경계에서 왼손 810 cm/s 순간 이동, 파지 89.3% / B 후처리 끔 → 파지 100% · 목표 오차 p50 2.3 cm, 그러나 접지 중 발 미끄러짐 p95 14 ~ 20 cm/s / C 손 제약에 `Hips` 포함 → A 와 같음 / D 손 키 프레임 매 프레임 → 파지 8.3% · 1447 cm/s / E 손 일반 EE + 발 `left-foot` 후처리 고정 → 발 목표가 매끈한 루트만큼 어긋나 미끄러짐 p95 34 ~ 45 cm/s / **G 손 · 발 모두 일반 EE + root2d + 후처리 → 파지 100% · 손 목표 오차 p50 2.5 cm · 발 위치 1차와 p50 2.2 ~ 2.6 cm · 접지 미끄러짐 p95 3 cm/s(1차와 같은 수준) · 발 좌우 비 1차와 같음** → G 채택 | Kimodo 소스 · 스파이크 2 · 3 |
| 제약 포즈의 팔 IK | 확산은 위치 · 손 회전만 쓰니 IK 불필요 | 후처리가 회전에서 목표를 다시 만들 수 있어 팔 2본 IK 로 FK 와 맞춘 포즈를 넣는다(G 에서는 후처리가 일반 EE 를 고정하지 않아 결과에 영향은 없음 — Kimodo 자체 구간 전이 제약과 같은 형식의 실제 골격 포즈를 유지). IK 목표 오차 0, 늘어남 0 | `refine.two_bone` · pytest |
| `meet` 도달 | 기준 시험은 오른손 옆 목표에 왼팔 도달 0% | seed 20261025: 보조 목표가 팔 길이의 1.48배 → 두 손목을 보조 어깨 쪽으로 p50 31.2 · 최대 33.5 cm 옮겨 0.92배 안. seed 20261026: 이미 닿음(이동 0) | 스파이크 `grip.stats` |
| 2차 생성의 휘두름 | — | 양손이 붙으면 소스 손목 정점이 줄었다: seed 20261025 542.8 → 401.3 cm/s, 20261026 365.2 → 232.5 cm/s — 선별의 휘두름 지표가 의미를 가진다(사용자 판정 "흐느적" 과 연결) | 스파이크 `metrics` |
| 2차 생성 결과 (E2 ① · ②) | 파지 목표를 따르면 품질이 오른다 | 소스 파지 0 → 100%(4 seed 모두), Vesper 21.05 cm 안 100%(간격 p50 5.2 ~ 6.6 cm), 접지 발 1차 ± 3.4 cm, 발 좌우 비 1차와 같음 — 그러나 **휘두름 정점이 줄고**(소스 543 → 401, 365 → 233 cm/s) **양손을 모은 팔이 Vesper 가슴 · 옷에 들어간다**(관통 72 ~ 84%, 최대 6.3 cm, 아래팔 → `breast_r` · `spine_02`). 관통은 전부 파지 프레임(비파지 관통 상한 0%) → B안(파지 프레임 마스크) 불필요, 남은 관통은 C안(8-4) | 통합 `refine` · `select` |
| `meet` vs `lead` (E2') | `lead` 는 모델 상체 비틀기 · 후처리 IK 로 닿을 수 있다 | 같은 seed `lead`: 소스 파지 21.5%(간격 p50 27.8 cm — 목표 손목 오차 p50 1.7 cm 인데도 팔 밖 목표라 모델이 못 모음) · Vesper 62.5%(Vesper 어깨가 좁아 더 붙는다) · 비파지 관통 상한 37.5% → 수치로는 `meet` | 통합 `lead` |
| 넓은 다리와 프롬프트 (E3) | "fighting stance" 표현이 넓은 자세를 부른다 | 끝을 "…ready stance with feet shoulder-width apart." 로(같은 seed · 플래그 없음): Vesper 발 좌우 비 p90 5.45(기준 5.55) — 거의 같다. 이 프롬프트 · seed 에서는 표현 탓이 아니다 | 통합 `e3` |
| 깨짐 벌점 | 검증 상태 = 깨짐 | `PASSED_WITH_WARNINGS` 가 하위 관통 검사(`BODY_PENETRATION`)에서도 나온다 → 관통이 '관통'과 '깨짐' 벌점에 이중으로 잡힌다(E2 ② 후보 0 · 2 · 3). 설계대로 두고 근거를 `breakage.all_warnings`(하위 검사 경고 전부)로 남겼다 — 기준 보정 후보 | 통합 `select` |
| 후보 임포트 | 같은 `Import/Motion/` 에 여러 FBX | `import_animation_file` 은 빈 폴더에만 임포트한다(FBX 가 만들 이름을 미리 검사할 수 없다 — `ASSET_EXISTS DEST_NOT_EMPTY`, 하위 폴더는 안 봄, `AnimMcpAnimImport.cpp:134-143`) → 첫 4후보 실행 실패 → 후보마다 `Import/Motion/C<번호>/` + `name` 명시. FakeEditor 도 같은 검사를 하게 고쳤다(pytest 가 못 잡은 이유) | 통합 `select` 1차 실패 |
| 2차 생성의 프레임 진동 (Persona 소견 ① 처음 · 끝 떨림) | 진동이 있으면 리타깃 · 관통 보정 · 루트 탓 | 지그재그(가속도가 프레임마다 반대 방향일 때 min(\|a_f\|, \|a_f−1\|), cm/프레임²) p95 처음 0.67초 / 중간 / 끝 0.67초: 1차 ≤ 0.09 vs **2차 0.18 ~ 1.23**(seed 25 1.01 / 0.59 / 0.63) — 소스 NPZ · UE 임포트 소스 · Vesper 가 1.0 ~ 1.03배로 같다 → **전부 2차 생성 소스**. 변형 스파이크: 후처리 끔 · cfg 낮춤은 효과 작거나 파지가 풀리고, 손 · 발 EE 를 매 프레임 주면 정지 구간이 1차 수준 → 원인 = **희소 키 프레임(3프레임마다) 사이를 separated CFG 의 제약 항이 진동하며 메운다**. 수정안 A = 2차 출력의 로컬 회전(쿼터니언 부호 연속) · 루트 위치에 가우시안 σ 1프레임 → 77 관절 FK(σ 는 계획 `refine.smooth_sigma_frames` 하나). 기록 NPZ 5개에 제품 `smooth_output` 을 걸면 FK 대응 **0.0 m**, 지그재그 ≤ 0.08, 파지 100% 그대로, 정점 −2.5 ~ −13%(seed 28 352.6 → 306.9). 재생성(A + B, 실행 `P81Run1026_180733`): 소스 4 seed ≤ 0.08(seed 27 처음 0.13) · Vesper 같음 · 파지 100% · 정점 −3 ~ −10%(스무딩 전 대비) · 접지 발 미끄러짐 p95 ≤ 2.0 cm/s | 하위 세션 스파이크(`phase8-1-quality-spike.md` ②) · 제품 `smooth_output` 스모크 · 통합 `select` |
| 보조 손목 꺾임 (소견 ③) | 2차 생성이 손을 비튼다 | `refine.solve_grip` 의 처음 규칙(보조 손 '손목 → MiddleEnd' 를 주 손에 맞추는 최소 회전 · 주 손 전역 회전 고정 — `meet` 은 주 손도 31 cm 옮기는데 아래팔만 돈다)이 **IK 목표에서 이미 손목을 96 ~ 99° 꺾었다**, 2차는 그 목표를 따라 116° 까지. 수정안 B = 손 회전 = 새 아래팔 × 1차 손목 로컬(keep, 두 팔 같은 규칙) → 스파이크 보조 손목 최대 116 → 50°, 파지 100%. 대가 = 양손 방향 정렬 7 → 35°(1차 수준) — 나란히 쥐기는 8-4. 재생성(같은 정의 — 아래팔 vs 손목 → 중지 첫 마디): 소스 보조 손목 최대 111.5 → 39.7°(seed 25) · 97.5 → 16.1°(26) · 63.0 → 22.3°(28), Vesper 112.8 → 41.5° 등. **1차부터 꺾인 seed 27(82.7°)은 keep 이 그대로 지킨다(41.8 → 84.4° — 처음 규칙이 오히려 폈다)** — 손목 절대 상한 또는 8-4 | 스파이크 ③ · pytest `test_keep_holds_the_pass1_wrist_bend…` · 통합 `select` |
| 선별이 '서 있기' 를 고름 (소견 ②) | 점수가 공격다운 후보를 고른다 | 기록 Job c49a83 이 seed 26(손이 머리 위로 한 번도 안 감 · 엉덩 앞 30 ~ 40 cm 에 머묾)을 골랐다. 원인 셋: ① 관통 경고가 깨짐 0.5 로 이중 계산 ② 양손을 모으면 아래팔이 가슴에 닿는 파지 프레임 관통(72 ~ 84%)을 벌점으로 셈 — 움직임이 작은 후보가 유리 ③ 공격다움 지표 없음. 수정안 C = 깨짐은 관통 검사(`body_clearance`) 밖 경고만(`breakage.scored_warnings`) · 파지 플래그면 관통 = 비파지 프레임 상한 · `attack` = 엉덩 관절 중점 기준 손목 중점 궤적 상자 대각선 / 팔 길이(위팔 + 아래팔), 벌점 max(후보 최고 대비, 팔 길이 1.0 하한) · 가중치 2. 손 들기(어깨 위 높이)는 수평 베기에 안 맞아 기록만. 측정 본에 어깨(템플릿 체인 LeftArm 시작) · 팔꿈치(손목 본의 부모) 추가. 통합 `recompute`(기록 후보 4개를 새 측정 · 점수로): **seed 20261025** 선택(0.114 vs 0.179), 궤적 폭 1.646 / 0.395 / 1.028 / 1.083 = 스파이크(팔 길이 정의 일치), seed 28 의 경고도 관통뿐(114.6°/프레임은 경고 아님). 재생성 Job 도 seed 20261025 · '서 있기'(seed 26) 4위 | 스파이크 ④ · 통합 `recompute` · `select` |
| 기준 무기 (Persona 재확인 — 낫 기준 보정) | 양손 파지 = 검 손잡이(손목 간격 ≈ 7 cm, 판정 ≤ 20 cm) | Vesper 근접 무기는 낫(로드아웃 `WD_Sickle1`), 스켈레톤에 무기 본 없음(소켓 `WeaponHandR` · `DisplayHip` · `DisplayBack`). 운영 낫 애니 4개: 손목 간격 4 ~ 104 cm, 간격이 일정한 양손 구간 24 ~ 47% · 그 간격 p50 55 ~ 66 cm, 손이 모이는 겹침 1 ~ 33%. 검 기준 생성물은 간격 4 ~ 14 cm · 겹침 7.5%(뼈 선분 < 2.5 cm). → 간격 상한 100 · 요청 간격이 있으면 판정 '간격 ± 13 cm × scale' · 낫 재생성(간격 60, `P81Run1026_184807`): Vesper 간격 p50 51 cm · 겹침 0 · 정점 321 → 493 cm/s. **FK 리타깃이 소스 58 ~ 60 → Vesper 49 ~ 51 cm 로 줄인다**(어깨 반폭 차 — 검 7 → 5 cm 와 같은 현상) → Vesper 띠 아래 끝에 걸려 seed 27 · 28 파지 35 · 67.5%(소스 100%). 요청 70 안팎이 후보(미검증), 정확히는 8-4 | 통합 `scythe` · 측정 스크립트(운영 낫) |
| 궤적 폭 정의 (버전 3) | 두 손목 중점이면 한손 · 양손 모두 맞다 | 한손 공격에서 빈 손이 가만있으면 중점 궤적은 절반쯤 → 손별로 재 큰 쪽(양손이면 거의 같다 — 기록 후보 seed 25 중점 1.646 → 손별 1.698, 운영 낫 중점 2.36 ~ 4.48 → 손별 2.71 ~ 4.64). 재계산 선택 seed 20261025 그대로 | pytest `test_attack_takes_the_wider_hand…` · 통합 `recompute` |
| 파지 목표 축 (낫 Persona '팔 꼬임 · 머리 · 배 관통') | 주 손 너클 `Index2 → Pinky2` = 손잡이 축(새끼 쪽 = 폼멜 — 보조 손이 그쪽) | 무기 없이 만든 1차의 펼친 손에서 너클 축은 실제 두 손목 방향과 **84 ~ 128°** 어긋난다(낫 4 seed · 검 4 seed 모두 p50 27 ~ 128°). 간격 60 cm(낫)면 보조 손 목표가 몸 반대편 — 손 좌우 뒤바뀜 1차 0 ~ 5% → 목표 85 ~ 93% → 2차 46 ~ 93%, 목표 이동 p50 34 ~ 59 cm, 손이 머리 15 cm 안 48 ~ 88%(Job ad275a). 검(7 cm)도 목표 24 ~ 32% 뒤바뀜(Job c0f5be). → 축 = 1차 '주 손목 → 보조 손목'(2 cm 안이면 너클). 기록 1차에 새 축: 목표 뒤바뀜 = 1차와 같음 · 이동 p50 0 ~ 19.6 cm · 머리 10 cm 안 목표 0%. 재생성(Job f991aa): Vesper 꼬임(10 cm 넘게) 12.5 ~ 91.7 → 0 ~ 5% | 측정 `cross_probe.py` · 새 축 오프라인 · 통합 `scythe` · pytest `test_handle_axis_…` |
| 선별이 망가진 낫을 골랐다 | 파지 플래그면 비파지 관통만(검 손잡이 가정) · 꼬임 · 머리는 관통 검사가 잡는다 | 자루 무기에도 비파지 규칙이 몸 관통 71 ~ 79% 를 0 으로 뺐고, 플러그인 `body_clearance` 는 위팔-몸통 · 골반 · 넓적다리만 봐 머리 · 꼬임 지표가 없었다 → 통합이 PASS. → 요청 간격이 있으면 관통 전체(`all_polearm`) · `motion_metrics` 버전 4 `arm_cross`(엉덩 축 위 손목 좌우, 10 cm × scale 넘게) · `head_near`(손 점 ↔ 머리 본 < 10 cm × scale) · 벌점 cross · head(가중치 2). 기준 = 운영 낫 애니 4개(꼬임 0 ~ 16.3% · 머리 0% · 최소 11.0 cm · 관통 0 ~ 34.4%)가 벌점 0. margin 0 꼬임은 운영 낫 4 ~ 42% · 검 손잡이 88 ~ 100% 라 못 쓴다. 통합 `scythe` 상한(꼬임 20 · 머리 5 · 관통 40%) — 재생성 4후보 중 seed 28 만 안(선택), seed 27 은 1차부터 손이 머리 2.5 cm 까지 와 Vesper 55.8% | 측정 스크립트(운영 낫 · 기록 후보) · 통합 `scythe` · pytest `test_cross_and_head_…` |
| 자루 무기 파지 띠 (정정 — 보강 4) | 띠 = (요청 간격 ± 13) × pelvis scale(1.052) — 리타깃이 간격을 scale 만큼 키운다 | FK 리타깃은 간격을 **× 0.79** 로 줄인다(재생성 4 seed 소스 60.1 ~ 62.7 → Vesper 48.2 ~ 49.3 cm). 띠 아래 끝 1.052 × (s − 13) > 0.79 s ⇔ s > 52 → 낫 간격은 어떻게 잡아도 Vesper 가 띠 밖(통합 FAIL 2 — 고른 후보 파지 37.5% · `GRIP_NOT_REACHED`). 원인 측정: 기준 포즈 어깨 관절 폭 SOMA 32.96 · Vesper 23.96, 팔 55.85 · 47.66 cm. 프레임별 FK 모델(대상 본 벡터 = 소스 본 벡터 × 길이 비 — 어깨 0.727 · 위팔 0.848 · 아래팔 0.859)이 Vesper 간격을 프레임마다 p50 0.2 cm 로 맞힌다 → 리타깃 모델 확인. 계획 때 쓸 수 있는 사상 비교(p50 오차): × pelvis +15 ~ +17 · 팔 비 +3 ~ +4 · 스팬 비 +1.4 ~ +2.5 · **'대상 = W_대상 + 팔 비 × (생성 − W_생성)'(파지선 ∥ 어깨선) −1.0 ~ +0.1 cm** → 채택(`motion_metrics` 버전 5 `gap_map` · `grip_spacing`, 계획이 한 번 풀어 생성 · 대상 띠가 같은 값, 새 요청 `target_spacing_cm`). 기록 재계산: Vesper 파지 4.2 ~ 37.5 → 100%(선택 seed 28 그대로). 대상 60 → 생성 75.19 재생성(`P81Run1026_205832`): Vesper 간격 p50 60.5 ~ 62.2(사상 오차 −0.9 ~ +0.2 cm) · 파지 100% · 통합 PASS. 남은 근사: 파지선이 세로에 가까우면 사상이 대상 간격을 낮게 본다(Vesper 생성 75 에서 최대 −4.3 cm), 키 프레임별 정확한 변환 · 손 부착은 8-4 | 측정 스크립트(기록 NPZ · Vesper profile) · 통합 `regrip` · `scythe` · pytest `test_gap_map_…` |
| Kimodo 시간 | 확산 1회 ≈ 10초(10-25 기록) | 에디터를 띄운 채 확산 + 후처리 1회 9 ~ 27초(편차 큼 — 스파이크 · E1 이 느렸다), 후보(1 · 2차 합) 19 ~ 58초, 모델 적재 25 ~ 38초, torch 임포트 11 ~ 45초. 4후보 × 2차 = 한 실행 117 ~ 128초 → 기한 = 정책 300 + 25초 × (확산 − 1)(8 확산 475초)이면 여유 | 스파이크 `seconds` · E1 · E2 ② |

---

## 부록. 측정 기록

| 회차 | 내용 | 결과 |
| :---: | :--- | :--- |
| 1 | 스켈레톤·메시·애니 레지스트리 집계, 자동 캐릭터라이즈 7종, 기존 IK Rig·RTG 덤프, Python 클래스·플러그인·Interchange 설정 | 더티 0 → 0. `FBoneChain` 필드 Python 미노출 확인 |
| 2 | 체인 이름 덤프(컨트롤러 getter), 히어로 애니 57개 수치 기준선, 소스 풀 샘플링 비용 | `GetAnimPoseAtTimeIntervals` Python 미노출 확인 후 프레임 단위로 재실행. 더티 0 → 0. 경고 20건(`AS_Vesper_Jump_FallLoop` Transform 커브) |
| 3 | 스켈레톤 8종 본 이름 겹침 · 기준 포즈 차 | 더티 0 → 0 |

측정 스크립트는 일회성이라 저장소에 두지 않았다. 같은 측정이 Phase 1의 `inspect_skeleton`(`compare_to`)과 `validate_animation`으로 C++ Tool이 된다.
