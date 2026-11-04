# AI 애니메이션 생성 자동화 — U9 영상 포즈 추정 타당성 조사

작성일: 2026-11-04  
상태: 조사 완료 · **사용자 결정(2026-11-04): Provider 채택 안 함 · GEM-X 는 키 포즈 원천 후보로만 · 오프라인 시험 없이 닫음**(§7). 코드 · 하네스 변경 없음, 내려받기 · 설치 · 가입 · 업로드 0건.  
관련 문서: [후속 로드맵](FollowUpRoadmap.md) §11 · [개발 지침서](DevelopmentGuide.md) §2.4 · [Phase 5 로컬 모델 조사](LocalModelSurvey.md)(판정 기준 §1 · 데이터셋 조건 §2 · 판단 항목 §4)

**방법.** 공개 저장소 README · LICENSE · 모델 카드 · 서비스 약관 · 요금 페이지를 웹으로 읽었다(2026-11-04 시점 — 약관은 바뀔 수 있다). 코드 · 가중치는 받지 않았고 실행하지 않았다. 그래서 **VRAM · 속도 · Windows 동작 · 전투 동작 품질은 이 PC 실측이 아니다.** 웹 도구가 페이지를 변환 · 요약해 돌려주는 방식이라, 채택이나 지출을 결정하기 전에는 §2 · §5 의 조항을 원문 페이지에서 다시 확인해야 한다. 법률 자문이 아니다 — 원문 조항과 그 조항이 이 프로젝트의 어디에 걸리는지만 적고, 목적에 따라 갈리는 판단은 §5 에 남겨 사용자가 정한다.

**이 PC.** RTX 3080 Ti 12 GB(Ampere) · RAM 64 GB · i7-12700KF · Windows 11 · D: 여유 327 GB · 프로젝트 UE 5.7.4 소스 빌드 · Kimodo 는 `D:\AnimGenModels\Kimodo\` 에 전용 환경으로 설치됨.

**사용자 범위 결정(2026-11-04).** ① 로컬 모델 + 상용 서비스 ② 시험 영상은 조사 뒤 정한다 ③ 내려받기 · 설치 · 가입은 지금 없음, 필요하면 항목별로 다시 확인.

---

## 요약

### 로컬 모델

| 모델 (공개 시점) | 코드 | 가중치 | 학습 데이터 · 필수 의존 | 출력 | 세계 궤적 · 발 | 손 | 이 PC 호환 | 판정 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **GEM-X** (NVIDIA, v1.1 카드 날짜 2026-10-30) | Apache-2.0(파일별 OpenMDW-1.1 예외) | NVIDIA Open Model License(메인테이너 확인) — 단 Body Pose · 2D 관측은 **SAM 3D Body 가중치로 초기화** | 합성 영상(NVIDIA 모캡 기반) + 상업 호환 실제 영상 · SOMA 0.3.3(Apache-2.0) · 사람 검출기 YOLOX Human-Art | **SOMA 77 관절**(Kimodo 와 같은 배열) 파라미터 `.pt` · BVH · FBX 내보내기 없음 | 세계 궤적 ○ · 선택 Contact/IK 후처리 · 30 Hz · 최대 60초 | 77 관절에 손가락 자리 있음, 손가락 동작은 미확인 | △ 카드 OS 표기에 Windows · 설치 문서는 Linux 뿐 · 12 GB 미측정 | **적법 · 호환 후보 (조건 §5 V-1 · V-2)** |
| GEM-SMPL / GENMO (NVIDIA) | NVIDIA OneWay Noncommercial | 같음 | SMPL · HMR2 | SMPL 파라미터 | ○ | ✕ | 미측정 | 상업 부적법 · 포트폴리오 §5 |
| SAM 3D Body (Meta, 2025-11) | SAM License | SAM License · 게이트 | MHR · 학습 데이터 이름 미기재 | 프레임별 MHR | ✕ README 에 세계 좌표 · 영상 언급 없음 | ○(단일 이미지) | 미측정 | 적법(조건 V-1) · **호환 낮음 — 단일 이미지** |
| GVHMR (2024) | "research and non-profit purposes only" | 미기재 | AMASS · BEDLAM · H36M · **SMPL-X 필수** | SMPL 계열 파라미터 | ○ | ✕ | 미측정 | 상업 부적법(코드부터) · 포트폴리오 §5 |
| WHAM (2023) | MIT | 미기재 | **AMASS** · **SMPL 필수** | README 에 형식 미기재 | ○(SLAM) · 발 언급 없음 | ✕ | 미측정 | 상업 부적법 · 포트폴리오 §5 |
| 4D-Humans / HMR2 (2023) | MIT | 미기재 | **SMPL 필수** | `.pkl` · `.obj` | README 에 세계 좌표 언급 없음 | ✕ | 미측정 | 상업 부적법 · 호환 낮음 |
| TRAM (2024) | MIT | 미기재 | BEDLAM · **SMPL 필수** · DROID-SLAM 컴파일 | README 에 형식 미기재 | ○ | ✕ | 미측정 | 상업 부적법 · 포트폴리오 §5 |
| PromptHMR (2025) | "Non-Commercial Scientific Research Use Only" | 미기재 | **SMPL-X 필수** | MCS · GLB | ○ | 미확인 | 미측정 | 상업 부적법(코드부터) · 포트폴리오 §5 |

### 상용 서비스 · 엔진

| 서비스 | 가격 (공식 표기) | API | 출력 | 입력 영상 학습 사용 | 출력 권리 | 판정 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Move One / Move API | 앱 무료 30 크레딧 1회 · $18 ~ 490/월 · API 단일 카메라 $0.012 ~ 0.024/초 | ○ | 약관에 형식 미기재 | **○ — 영구 · 취소 불가 라이선스, 옵트아웃 조항 없음** | Move 소유 · 이용 허락. **AI 시스템 입력 금지**(원본 영상 제작 예외) | 비추천 — **키 포즈(Kimodo 입력)로 쓸 수 없음** |
| DeepMotion Animate 3D | 무료 월 60초(비상업) · 유료 금액 공식 페이지에서 확인 못함 | ○(접근 신청) | FBX · BVH · GLB · MP4 | 머신러닝 처리 · 서비스 개선 문구 있음, '학습' 단어 없음 | DeepMotion 소유 · 유료만 상업 · **게임은 바이너리로만** | 보류 — 공개 저장소 V-4 |
| Rokoko Vision (Create) | 무료 월 30초 · $10 ~ 12/월 600초 | ✕ | FBX · BVH(유료) · HIK · Mixamo · Manny | 개인정보 방침: 처리 뒤 삭제 · 다른 목적 안 씀. 단 약관은 User Content 개선 · 익명 재라이선스 허용 | 출력 조항 명시 없음(User Content 로 읽힘) | 수동 1회성 도구로만 가능 · Provider 불가 |
| Plask Motion | 무료 하루 15초(개인 비상업) · $18 ~ 50/월 | ○ | FBX · GLB · BVH | 목적 제한 없는 머신러닝 처리 문구 · 광고 사용 · '학습' 명시 없음 | 2023 약관 — 영상 자체의 상업 조건 불명확 | 보류 — 약관이 오래됨 |
| UE 5.8 MetaHuman Animator Markerless (Epic) | 무료(2차 출처) | 에디터 플러그인 | AnimSequence(MetaHuman) · 리타깃 가능(2차 출처) | 로컬 처리 | Fab 조건 · 번들 모델 조건 미확인 | **엔진을 5.8 로 올릴 때 재검토** · 지금은 범위 밖 |
| Meshcapade | — | — | — | — | — | 2026-02 Epic 인수 · 독립 플랫폼은 종료 보도(날짜 불일치) → 후보 제외 |
| QuickMagic | 2차 출처만 | 미확인 | 미확인 | 약관 원문 못 찾음 | 미확인 | 후보 제외(미확인) |

**결론.** 이 조사의 핵심 발견은 **GEM-X** 다. 영상 포즈 모델의 주류는 예상대로 SMPL · AMASS 에 묶여 상업이 막히지만(§3.2), GEM-X 는 SOMA 골격을 쓰고 카드가 상업 이용을 밝힌다. 골격이 Kimodo 와 같은 SOMA 77 이라 지금 경로에 코드 변경 없이 들어올 구조적 근거가 있다(§6). 다만 깨끗한 후보는 아니다 — 메인테이너가 두 체크포인트의 SAM 3D Body 초기화를 밝혔고, 필수 사람 검출기는 비상업 승인 데이터로 학습했다(§5 V-1 · V-2). 전투 동작 품질은 미측정이고 공개 이슈에 불리한 사례가 있다. 상용 서비스는 어느 것도 Provider 로 권하지 않는다. **권고: 지금은 Provider 채택 안 함 · GEM-X 를 키 포즈 원천 후보로만 기록**(§7).

---

## 1. 판정 기준

[로컬 모델 조사](LocalModelSurvey.md) §1 을 그대로 쓴다. 서비스 칸을 더했다.

| 항목 | 기준 |
| :--- | :--- |
| 적법 | 코드 · 가중치 · 학습 데이터 · 필수 의존 모델의 **원문 조건**이 한국에서 이 프로젝트(UE 게임의 애니 애셋 제작, 현재 개인 포트폴리오)의 이용을 허용한다. 조건이 목적에 따라 갈리면 그대로 적고(§5) 판단하지 않는다 |
| 호환 | ① RTX 3080 Ti 12 GB 추론 ② Windows 전용 환경 서브프로세스 ③ 출력이 BVH(또는 BVH 로 손실 없이 바뀌는 로컬 회전)라 `motion_file` → Phase 4 `blender` → Phase 1 리타깃으로 간다 |
| 서비스 | 위에 더해 업로드 영상의 학습 사용 · 보관 · 출력 권리 · 키 포즈 활용(출력을 Kimodo 에 넣어도 되는가) · API 유무 |
| 출처 | 각 행의 번호 → 부록. 원문이 말하지 않는 것은 "미기재", 찾지 못한 것은 "미확인" |

---

## 2. 공통 의존의 이용 조건

| 대상 | 원문 조건 (요지 · 짧은 인용) | 이 프로젝트에 걸리는 점 | 출처 |
| :--- | :--- | :--- | :--- |
| **SMPL · SMPL-X · AMASS** | 조사 §2 그대로 — 비상업 과학 연구 · 교육 · 예술만, 상업 목적 학습 · 이용 금지 | **로컬 모델과 다른 점:** SMPL 계열 영상 모델은 추론에도 바디 모델 파일이 필요해 **사용자가 직접 등록 · 동의하고 받는다**. Text-to-Motion 의 H-2(가중치만 받는 사람에게 미치는가)와 달리 계약 당사자가 된다 | 조사 [D1] · [D5] · [L2] · [L3] · [L5] |
| SMPL 상업 라이선스 창구 | 2026-02 Meshcapade 의 Epic 인수 발표. "MI will now directly take over the licensing" — Max Planck Innovation 이 SMPL 라이선스를 맡는다 | 조사 §2 의 창구 'Meshcapade' 는 낡았다. PromptHMR 라이선스의 문의처도 Meshcapade 로 남아 있다 | [E5] · [L9] |
| **NVIDIA Open Model License** | 조사 §2 그대로 — 상업 가능 · 전 세계 · 출력 소유 주장 없음 · 모델 재배포 시 고지 | GEM-X 가중치 조건. 모델을 재배포하지 않으면 고지 의무 없음 | 조사 [K4] · [G2] · [G11] |
| **SAM License** (2025-11-19) | 사용 · 복제 · 파생물 허용, 상업 금지 문구 없음. 배포 시 계약서 사본 · 연구 결과 공표 시 사용 사실 표기 · 역공학 금지. §1.b.v 금지 용도에 "the development or use of guns or illegal weapons". 출력 전용 조항 없음 · 위반 시 종료 · 삭제 | GEM-X `ATTRIBUTIONS.md` 에 전문이 실려 있고, 두 체크포인트가 이 가중치로 초기화됐다. 이 프로젝트에 라이플 캐릭터가 있어 §5 V-1 | [A1] · [G4] · [G11] |
| DINOv3 License | SAM License 와 같은 틀 — 같은 총기 문구 · 재배포 시 사본 · 공표 시 표기 | GEM-X 백본 구현이 DINOv3. 체크포인트에 백본이 포함돼 따로 받지 않는다. 이 라이선스가 체크포인트에 미치는지는 이슈에서 답하지 않았다 — V-1 | [A3] · [G6] · [G8] · [G11] |
| SOMA-X | 코드 · 카드 Apache-2.0, 카드 "ready for commercial use". SMPL · MANO 등 다른 백엔드는 사용자가 라이선스 파일 준비 | GEM-X 가 쓰는 파일(`SOMA_neutral.npz` · `SOMA_template_rig.usda` · `SOMA_procedural_transforms.json` · 렌더용 `correctives_model.pt`)은 SMPL 파일이 아니다. 관련 카드는 v0.3.0 까지만 적혀 있어 v0.3.3 자체는 미확인 | [S1] · [S2] · [G5] |
| **Human-Art** | 저장소 코드는 Apache-2.0, 데이터는 "authorization to use Human-Art for non-commercial purposes" 양식 | GEM-X 기본 검출기 `yolox_humanart.onnx` 의 학습 데이터 — §5 V-2 | [A4] · [G6] |
| ViPE | 대부분 Apache-2.0, Unik3D 부분 BY-NC-SA 4.0, 깊이 모델은 설치 때 별도 조건 | **움직이는 카메라에만 필요.** `--camera-mode static` 은 쓰지 않는다 → 고정 카메라 촬영이면 걸리지 않는다 | [A5] · [G7] |

---

## 3. 로컬 모델별

### 3.1 GEM-X — 유일한 비 SMPL 영상 궤적 후보

| 항목 | 내용 | 출처 |
| :--- | :--- | :--- |
| 코드 | 기본 Apache 2.0, 손 처리 · 카메라 복원 일부 파일은 OpenMDW-1.1. 나머지는 각 조건을 유지 | [G1] · [G4] |
| 가중치 | 카드 태그 `nvidia-open-model-license`, 카드에 "ready for commercial or non-commercial use". 저장소 안 `LICENSE` 파일이 Apache-2.0 이라 이슈 #32 가 물었고 메인테이너가 모델 = NVIDIA Open Model License, 코드 = Apache-2.0 으로 답했다 | [G2] · [G3] · [G11] |
| **체크포인트 계보** | 같은 이슈에서 `body_s240000.ckpt` · `vitpose.pth` 둘 다 SAM 3D Body 가중치에서 초기화했다고 답했다(2026-10-31). 모델 카드 · 모델 개요 문서에는 이 언급이 없다. SAM License 가 체크포인트에 어떻게 미치는지는 답이 없다 | [G11] · [G2] · [G8] |
| 학습 데이터 | 공식 카드: 합성 영상(NVIDIA 자체 모캡 기반) + 상업 사용 호환 라이선스 실제 영상. 비공식 복제 카드의 이전 판은 Bones RigPlay-1 · RenderPeople · 내부 합성 캐릭터 · HDRI Haven 을 나열한다(Kimodo 와 같은 데이터 계열). 실제 영상의 정체 · 비중은 미기재 | [G2] · [G17] |
| 지역 | "Global" | [G2] |
| 출력 | `motion.pt` — `pred_soma_params_global` · `pred_soma_params_incam` · 접촉 logit 6(발목 · 발 · 손목). 카드: 77 관절 포즈 + 세계 이동. **BVH · FBX 내보내기는 공식 문서에 없다** | [G2] · [G7] |
| 골격 | SOMA-X 문서: 사용자 쪽 77 항목, 0 = Hips, 11 몸통 · 머리 + 팔 28 × 2 + 다리 5 × 2. **Kimodo `SOMASkeleton77` 의 앞 11 이름 · 팔 28 · 다리 5 구성과 같다**(로컬 `definitions.py` 대조). +Y 위 · +Z 앞. 회전 기준 기본 = T 포즈 관절 방향. 런타임 이름 · 순서는 미확인 | [S3] · 로컬 |
| 궤적 · 발 | `--camera-mode static` 고정 카메라 · 기본 `background`(SIFT 회전 추정) · `vipe` · `provided`. `--postprocess` Contact/IK = 접촉 logit 으로 세계 이동 보정 + 다리 · 팔 CCD 2회, 원본은 `raw_predictions` 에 보존 | [G7] · [G8] |
| 손가락 · 얼굴 | 77 에 손가락 · 얼굴 관절 자리가 있지만 표정은 고정이고, 입력 쪽 설정 `remove_fingers` · 사용자 관찰(손가락 동작 안 보임)이 있다 → 손가락 동작은 미확인. 정밀 손은 별도 Hand Pose(EgoHand, 접근 승인 · 프레임별) — 이번 범위 밖 | [G13] · [G6] |
| 공개 벤치마크 | EMDB-2 Contact/IK: W-MPJPE₁₀₀ 267.20 mm · WA-MPJPE₁₀₀ 112.76 mm · RTE 2.45 % · Jitter 34.21 · Foot sliding 4.22(단위 미기재). 일반 동작 데이터라 전투 동작 품질을 뜻하지 않는다 | [G1] · [G18] |
| 약한 곳 | 발이 골반 위로 올라가는 동작 = 추적 붕괴 · 사지 뒤바뀜 — 메인테이너 답 "OOD motions"(2026-11-02). 손이 고정되고 하체가 격한 동작 = 손 표류 · 떨림(새 모델 시험 권유, 해결 미기재). 그 밖 이슈: 발꿈치 뜸 · 골반 회전 · 화면 밖 추적 · 앞으로 기욺. 무기를 든 영상 · 무기 가림은 공개 자료 없음 — **미확인** | [G15] · [G16] · [G19] |
| 환경 | Python ≥ 3.10 · `torch>=2.10,<3` · `transformers==5.3.0` · `py-soma-x==0.3.3` · FFmpeg. 메시 렌더는 Linux x86-64 + Open3D 0.19. 카드 OS 는 Linux · Windows · macOS 이나 **설치 · 데모 문서에 Windows 안내가 없다**. 추론 기준 하드웨어 A100 80 GB · Ampere 지원 · 12 GB 수치 없음(모델은 단계별 로드, 배치 4) | [G2] · [G5] · [G7] · [G9] · [G20] |
| 내려받기 크기 | `body_s240000.ckpt` 3.54 GB · `vitpose.pth` 3.39 GB(HF 스캔: pickle import 5개) · `motion_native77_e774_s292175.ckpt` 187 MB · 작은 설정 파일들. 저장소 전체 10.5 GB. SOMA 자산 · YOLOX ZIP 크기 미기재. 게이트 표시 없음 | [G3] · [G6] |
| 받지 말 것 | 같은 HF 저장소의 옛 커밋에 `gem_smpl.ckpt` 가 있다 — 비상업 쪽 모델이다 | [G21] · [L10] |

**적법:** 코드 · 가중치 · SOMA 자산은 원문상 상업 이용을 허용하고 지역 제한이 없다. 남는 조건은 §5 V-1(SAM 초기화 · 총기 문구) · V-2(Human-Art 검출기). 움직이는 카메라(ViPE)와 손 모델은 쓰지 않는 전제다.

**호환:** 골격 · 단위 · 30 Hz 는 지금 경로와 맞다. 내보내기 · Windows · 12 GB 는 실측이 필요하다(§6).

### 3.2 SMPL · SMPL-X 계열 (GVHMR · WHAM · 4D-Humans · TRAM · PromptHMR · GEM-SMPL)

조사 시작점의 예상대로 전부 SMPL 바디 모델을 추론에 요구한다.

| 모델 | 코드 라이선스 | SMPL 필수 근거 | 학습 데이터 | 환경 | 출처 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| GVHMR | ZJU 3D Vision 고지 — 교육 · 연구 · 비영리만, 수정물도 상업 금지, 상업은 저자 문의 | SMPL-X 파라미터 예측 · 등록 뒤 내려받기 | AMASS · BEDLAM · H36M(평가 3DPW · EMDB · RICH) | Python 3.10 · 선택 DPVO | [L1] · [L2] |
| WHAM | MIT | SMPL 등록 필요 | 1단계 AMASS | PyTorch · Docker · Colab | [L3] · [L4] |
| 4D-Humans | MIT | neutral 모델 필요 | 학습 데이터 별도 다운로드 · 라이선스 미기재 | Python 3.10 · 학습은 Linux | [L5] · [L6] |
| TRAM | MIT · "third-party 각자 라이선스" | SMPL 등록 필요 | BEDLAM 등 · HMR2b 초기화 | Python 3.10 · DROID-SLAM 컴파일 | [L7] |
| PromptHMR | 비상업 과학 연구 전용 · 군사 · 감시 금지 | SMPL-X 등록 | 비공개(학습 코드 미공개) | PyTorch 2.4 / 2.6 | [L8] · [L9] |
| GEM-SMPL(GENMO) | NVIDIA OneWay Noncommercial | SMPL · HMR2 체크포인트 | docs/DATA.md(읽지 않음) | — | [L10] |

**판정:** 상업 = **부적법**(SMPL 파일 조건, GVHMR · PromptHMR · GENMO 는 코드부터). 코드가 MIT 인 WHAM · 4D-Humans · TRAM 도 SMPL 파일이 막는다. 개인 포트폴리오 = **§5 사용자 판단**. 호환 = SMPL 은 손가락이 없고 BVH 변환에 바디 모델이 또 필요해 GEM-X 보다 낮다. BEDLAM 데이터 라이선스는 읽지 않았다 — SMPL 조건으로 결론이 이미 정해져 영향이 없다.

### 3.3 SAM 3D Body

단일 이미지 메시 복원이다. README 에 영상 · 세계 좌표 언급이 없고, 시간 연속성과 궤적을 직접 풀어야 한다. 체크포인트 게이트 · SAM License. 영상 궤적을 공개 후처리로 푼 논문은 로봇 리타깃 목적이다. 판정: 적법은 V-1 과 같고 호환이 낮다. GEM-X 가 이 가중치에서 출발해 시간 모델을 올린 쪽이라 직접 쓸 이유가 없다. [A2] · [G11]

---

## 4. 상용 서비스 · 엔진별

### 4.1 Move One / Move API

| 항목 | 내용 | 출처 |
| :--- | :--- | :--- |
| 가격 | 앱: Free 1회 30 크레딧(30초) · Starter $18/월 60 · Standard $48/월 180 · Plus $225/월 240 · Advanced $490/월 700(VAT 별도, s1 1초 1 크레딧 · s2 2 크레딧). API: 단일 카메라 s1 $0.012/초 · s2 $0.024/초 + fps · 해상도 배수 · 작업당 최소 $0.10 | [C3] · [C4] |
| 입력 영상 | 소유는 이용자. Move 에 전 세계 · 영구 · 취소 불가 · 재라이선스 가능 라이선스 — "development, training and improvement of our products" (API §6.2, 앱 §7.2). 영상 속 개인정보를 Move 가 독립 처리자로 쓴다. **옵트아웃 조항 없음** | [C1] · [C2] |
| 출력 | Output · Motion Data 는 Move 소유, 이용자에게 전 세계 · 로열티 무료 라이선스(§6.3). 판매 안 함 약속 | [C1] |
| **금지 용도** | §15.1 Prohibited Use = 경쟁 제품 · AI 학습 · AI 시스템 입력(원본 영상 저작물 제작 목적만 예외). §6.5 위반 시 라이선스 즉시 무효 | [C1] |
| 보관 | 구체 기간 없음 · 계약 종료 시 처리자로 다룬 개인정보 삭제 | [C1] |
| 지역 · 법 | Move AI Limited(런던) · 잉글랜드법 · 약관에 날짜 없음(© 2026) | [C1] · [C2] |

**판정:** 포트폴리오 · 상업 애니로 쓰는 것 자체는 막히지 않는다. 그러나 **키 포즈 경로(출력 → Kimodo)는 §15.1 과 충돌**하고, 사용자 신체 영상을 영구 · 취소 불가로 학습에 내주는 조건이다. 비추천.

### 4.2 DeepMotion Animate 3D

| 항목 | 내용 | 출처 |
| :--- | :--- | :--- |
| 가격 | 1 크레딧 = 1초(손 · 얼굴 각 + 0.5). 무료 월 60초 · 비상업. 유료 금액은 공식 페이지에서 읽지 못했고 2차 출처끼리 다르다 — **미확인** | [C7] |
| API | Animate 3D API 접근 요청 양식 · 공개 REST 저장소. 지침서 §2.4 의 'SayMotion 파트너 한정'과는 다른 제품 | [C8] |
| 출력 | FBX · BVH · GLB · MP4. 설정 Physics Filter · Motion Smoothing · Foot Locking 등 | [C7] · [C9] |
| 입력 영상 | 소유는 이용자. 서비스 제공 목적의 무상 · 전 세계 라이선스, 머신러닝 처리 · 서비스 개선 처리 문구 있음. '학습' 단어는 없다. 옵트아웃 · 보관 기간 없음(2025-03-30 약관 · 2023-12-01 방침) | [C5] · [C6] |
| 출력 권리 | **DeepMotion 이 소유하고 이용 허락.** 유료 플랜 출력만 상업(영구). 게임은 "as a binary only" 로만 배포 · 원본 에셋 단독 배포 금지 · 쉽게 추출되면 안 됨 | [C5] |
| 지역 · 법 | 미국 호스팅 · 캘리포니아법 | [C5] |

**판정:** 유료면 게임 애셋으로 쓸 수 있다. 공개 저장소에 `.uasset` 을 두는 것은 '바이너리로만'에 걸릴 수 있다(§5 V-4). 무료는 포트폴리오도 비상업 조건 안에서만. 보류.

### 4.3 Rokoko Vision (2026-07-16 부터 Rokoko Create 안)

| 항목 | 내용 | 출처 |
| :--- | :--- | :--- |
| 가격 | Starter 무료 월 30초 · FBX. Basic 월 $10(연) / $12(월) · 600초 · BVH · 커스텀 리타깃 | [C12] |
| 입력 조건 | 파일 업로드 · 한 사람 · 가림 · 화면 밖 품질 저하 · **손가락 미지원** · 듀얼 카메라 종료 예정 | [C12] |
| 입력 영상 | 개인정보 방침(2026-09-04): 처리에 필요한 기간만 보관, "not used for any other purpose" · 저장 선택 안 하면 삭제 | [C11] |
| 약관 | v2.0.1(2026-07-16): 소유 주장 없음 · 서비스 제공 목적의 영구 라이선스(§6.3). 그러나 §3.4 는 User Content · 사용 지표를 개선에 쓰고 익명 형태로 제3자 재라이선스하는 동의를 담는다. 출력 소유 · 상업 전용 조항 없음 — 사용자가 만든 결과는 정의상 User Content 로 읽힌다 | [C10] |
| 데이터셋 사업 | '사용자 커뮤니티에서 생성된' 익명 모션 데이터셋을 AI · 로봇용으로 판매한다. Create 업로드가 들어가는지, 옵트아웃이 있는지 미기재 | [C13] |
| API | 공개 Vision API 없음 — Provider 불가 | [C12] |
| 지역 · 법 | 접근 가능한 모든 지역 · 덴마크법 · 간이 중재 | [C10] |

**판정:** 입력 영상 조건은 넷 중 가장 낫다. 그러나 출력(애니)이 §3.4 에 드는 점이 남고 API 가 없다. Provider 불가, 사용자가 손으로 돌리는 1회성 도구로만 가능. 출력이 Manny · Mixamo 계라 지금 경로에 BVH 로 들어올 수 있다(유료).

### 4.4 Plask Motion

| 항목 | 내용 | 출처 |
| :--- | :--- | :--- |
| 가격 | Free 하루 15초 · Standard $18/월(연) 10분 · Pro $50/월(연) 1시간 · 전 등급 FBX · GLB · BVH · 손 · 다인원 | [C16] |
| API | 있음 — API 키 · 크레딧 · 영상 업로드 작업 · 배치 GPU 워커(2026-10-11 문서) | [C17] |
| 입력 영상 | 소유는 사용자. 취소 불가 · 전 세계 라이선스, "process User IP through machine learning" 목적 미기재 · 광고 사용 가능. 방침: 이미지 · 초상 수집 · 서비스 개선 · 영상 보관 기간 미기재 · AI 학습 명시 없음 | [C14] · [C15] |
| 상업 | 무료 = 개인 비상업. 유료 Commercial 플랜은 Plask IP 라이선스. 영상 자체의 상업 조건은 불명확. **약관 · 방침이 2023-04-05 판**이고 플랜 이름이 지금 요금제와 다르다 | [C14] · [C16] |
| 법 | 캘리포니아법 · 서울 법원 | [C14] |

**판정:** API 가 있어 Provider 구조에는 맞지만 약관이 오래돼 이 조건으로 결정하기 어렵다. 보류.

### 4.5 UE 5.8 MetaHuman Animator Markerless Motion Capture

Epic 문서: UE 5.8 이상 · Windows 전용 · 실험 기능 · 일반 카메라 영상 · 로컬 일괄 처리 · 결과는 애니메이션 시퀀스 · MetaHuman 대상. 기사: Meshcapade 기술 · 손 포함 · 다른 캐릭터로 리타깃 가능 · 권장 RTX 3070 급 · Fab 상 상업 포함 무료. Fab 페이지는 도구가 읽지 못해(403) **라이선스는 2차 출처**다. 개발자 포럼 글은 플러그인에 SMPL-X 파일이 들어 있다고 보고하며 모델 라이선스를 Epic 에 문의했으나 답을 받지 못했다고 적었다(보고자의 주장 · 미확인). 사용자 보고에 프레임레이트 오류 · RTX 5070 DirectML 장치 리셋 · 청크 경계 튐이 있다. [E1] · [E2] · [E3] · [E4]

**판정:** 이 프로젝트는 UE 5.7.4 소스 빌드라 지금 범위 밖이다. 5.8 로 올리거나 별도 5.8 에디터로 AnimSequence 를 뽑아 옮기는 경우에 재검토한다. 로컬 처리 · 영상 외부 전송 없음 · UE 안 결과라는 장점이 있어 §7 재검토 조건에 넣는다.

---

## 5. 이용 목적에 따라 갈리는 판단 (사용자 결정)

| # | 대상 | 갈림 | 원문 근거 |
| :---: | :--- | :--- | :--- |
| V-1 | GEM-X 체크포인트 | 모델 라이선스는 NVIDIA OML 인데 두 체크포인트가 SAM 3D Body 초기화다. ① SAM License 가 체크포인트 사용자에게 미치는가 ② 미친다면 §1.b.v 의 "development or use of guns" 가 **라이플 캐릭터가 나오는 게임의 애니 제작**에 해당하는가. 문장은 무역 통제 금지 용도의 예시로 나오고, 게임 · 가상 총기는 언급하지 않는다. 원문이 정하지 않는다. ③ 공표 표기 조항이 포트폴리오 문서에 미치는가(§1.b.ii) | [A1] · [A3] · [G11] |
| V-2 | `yolox_humanart.onnx` | `motion-video` 는 이 검출기를 거친다(문서상 상자 직접 입력 없음). Human-Art 승인 범위는 비상업이다. 구조는 조사 H-2 와 같다 — 데이터를 받지 않고 제3자가 학습한 가중치만 쓴다. 검출기는 사람 상자만 내고 동작 출력을 만들지 않는다. 대체 후보: `--body-detector` 로 다른 검출기(호환 미확인) · `motion-cache` 조건 파일 직접 작성(문서 없음) | [A4] · [G6] · [G7] |
| V-3 | SMPL 계열 포트폴리오 | 조사 H-1 · H-3 · H-4 그대로에 더해, 영상 모델은 사용자가 SMPL 파일을 직접 받으므로 계약 당사자가 된다(H-2 의 '가중치만 받음'이 적용되지 않는다). 취업용 포트폴리오가 비상업 연구 · 교육 · 예술에 드는지는 원문이 정하지 않는다 | 조사 [D1] · [D5] |
| V-4 | DeepMotion 출력 | 공개 저장소의 `.uasset` · BVH 가 '바이너리로만' · '쉽게 추출되면 안 됨'에 맞는가 | [C5] |
| V-5 | 사용자 영상 · 개인정보 | 서비스는 사용자 신체 · 얼굴 영상을 외부로 보낸다. GEM-X 는 로컬이라 나가지 않는다. 권리 · 동의는 입력자 몫(GEM-X 카드도 같은 취지) | [G2] · [C1] · [C14] |

---

## 6. 파이프라인 경로 (호환 상세)

코드 변경 없이 들어오는 경로가 이미 있다. `soma.is_soma()` 가 BVH 관절 이름으로 SOMA 를 알아보면 `blender.plan_convert` 가 `local_ai` 와 같은 리타깃 기본값을 채운다(`Tools/mcp/anim_gen/soma.py:48` · `providers/blender.py:113`).

```text
사용자 촬영 영상(고정 카메라 · 전신 · 30 fps 정규화 · ≤ 60초)
  → GEM-X motion-video --task body --camera-mode static --postprocess        (전용 환경 — Kimodo 환경과 분리)
  → motion.pt  pred_soma_params_global
  → 스크래치 변환  SOMA77 BVH                                                 (시험 전용 — 파이프라인 코드 아님)
  → motion_file{path, unit, ...} → blender → 리타깃(SOMA 기본값) → fix.* → validate → capture
  └ 키 포즈로 쓸 때: 결과 AS_ → generation.constraints[] key_pose{asset, times} → Kimodo(사이는 생성)
```

| 위험 | 내용 | 시험 때 확인 |
| :--- | :--- | :--- |
| 내보내기 없음 | 공식 BVH · FBX 경로가 없다. 커뮤니티는 USD 쪽 스크립트를 썼다 | 스크래치 변환 필요 — Kimodo `exports/bvh.py`(Apache-2.0) 재사용 가능성 |
| 기준 포즈 | 이슈 #17: 내보낸 BVH 기준 포즈 문제 · 공식 답 없음. SOMA-X 기본 회전은 T 포즈 기준이고 `--bvh_standard_tpose` 와 같은지 미확인 | 첫 출력의 관절 방향 비교 |
| 몸 비율 | GEM-X 는 사람별 identity · scale 을 낸다. 이동값은 그 몸 기준이라 BVH 오프셋과 맞춰야 한다 | 오프셋 원천 결정 · 골반 높이 대조 |
| 관절 이름 · 순서 | 배열은 같아 보이나 런타임 `_public_joint_names` 미확인 | 첫 실행 |
| Windows | 설치 문서가 Linux 뿐. `py-soma-x` 네이티브 의존(`usd-core` · `cholespy`) Windows 휠 미확인 · FFmpeg 필요 | 전용 환경 설치 시도 — 실패하면 호환 ✕ |
| 12 GB | 수치 없음. 체크포인트 3.4 GB 급 2개 · 단계별 로드 · 배치 4 | 실측(에디터 내리고) |
| 전투 품질 | 빠른 동작 · 무기 가림 · 높은 발차기 미확인 · OOD 사례 있음. **영상 복원의 떨림 · 발 미끄러짐은 전체 클립 경로에 그대로 들어온다** | 8-1 지표 · 캡처 |
| 손가락 | 정지로 볼 것 — 한계 `FINGERS_STATIC` · 8-4c `pose_from` 이 맡는다 | 첫 출력 |
| 키 포즈 왕복 | 키 경로는 Vesper → SOMA 역리타깃을 한 번 더 거친다. 왕복 위치 p95 0.36 cm(9-3a) — 시험 범위에서 무시 가능 | 추종 오차 |
| 신뢰 | `vitpose.pth` 는 pickle 체크포인트 — NVIDIA 공식 저장소 파일만 · 전용 환경 · 내려받은 폴더 밖에서 실행 | 설치 때 |

---

## 7. 권고

**지금은 Provider 로 채택하지 않는다. GEM-X 를 키 포즈 원천 후보로만 기록한다.** — **사용자 결정 2026-11-04: 권고대로.** 구현 · 설치는 없고, V-1 · V-2 는 열린 채로 둔다. 쓰게 되면 그때 사용자가 판단한다.

| 선택지 | 판단 |
| :--- | :--- |
| 채택(Provider) | **아니오.** 12 GB · Windows · 전투 품질이 실측 0 이고 내보내기가 없다. V-1 · V-2 도 열려 있다. 구현은 근거가 생긴 뒤다 |
| **키 포즈 원천으로만** | **권고.** 코드 변경 없이 시험할 수 있고(§6), 몇 프레임만 쓰면 영상 복원의 떨림 · 발 미끄러짐 · 가림에 덜 민감하다. 9-3a · 9-3b 판정 통과 경로에 얹힌다. 단 시험 전까지는 '후보'다 |
| 미채택 | 시험을 하지 않으면 실무상 같은 상태다. 다만 기록은 '적합 모델 없음'이 아니라 **'적법 · 호환 후보는 있으나 미시험'** 으로 남긴다(조사 §6 과 같은 원칙) |

상용 서비스는 Provider 로 권하지 않는다 — Move 는 키 포즈 경로가 약관에 막히고, Rokoko 는 API 가 없고, DeepMotion · Plask 는 공개 저장소 · 약관 시점 문제가 남는다. SMPL 계열은 쓰지 않는다.

**재검토 조건(U9):** ① 공식 내보내기 또는 Windows 설치 문서가 나온다 ② 메인테이너가 SAM · DINOv3 조건을 명시한다 ③ 비상업 데이터가 아닌 기본 검출기가 나온다 ④ 사용자가 시험 영상을 준비한다 ⑤ 엔진을 UE 5.8 로 올린다(§4.5) ⑥ Kimodo 가 못 내는 특정 동작이 필요해진다.

**오프라인 시험(로드맵 §11 범위 3) — 안 함(사용자 결정 2026-11-04).** 적법 · 호환 후보는 있지만 조건 둘이 맞지 않았다: 사용자가 권리를 가진 시험 영상이 없고, 내려받기 · 설치를 승인하지 않았다(사용자 촬영 · 약 8 GB + 환경 · V-1 · V-2 미정을 감안해 Phase 9 마감 뒤로). 그래서 8-1 지표 · 캡처는 없고, GEM-X 의 품질 · Windows · 12 GB 는 미측정으로 남는다.

나중에 시험할 때 받을 항목(시험 시점에 다시 항목별 승인):

| 항목 | 출처 | 라이선스 | 크기 | 비고 |
| :--- | :--- | :--- | :--- | :--- |
| GEM-X 코드 | `github.com/NVlabs/GEM-X` | Apache-2.0 | 소규모 | |
| `body_s240000.ckpt` · 설정 | `nvidia/GEM-X` | NVIDIA OML · V-1 | 3.54 GB | pickle 가능성 |
| `vitpose.pth` | 같음 | 같음 · V-1 | 3.39 GB | HF 스캔 pickle import 5 |
| `motion_native77_e774_s292175.ckpt` · 통계 · YAML | 같음 | NVIDIA OML | 187 MB | |
| SOMA v0.3.3 자산 | `nvidia/SOMA-X` | Apache-2.0(카드) | 미기재 | |
| `yolox_humanart.onnx` | OpenMMLab ZIP | **V-2** | 미기재 | |
| 전용 환경(PyTorch CUDA · `transformers` · `py-soma-x` · `onnxruntime`) · FFmpeg | PyPI · PyTorch | 각자 | 수 GB | Kimodo 환경과 분리 |

합계 약 8 GB + 환경. D: 여유 327 GB 로 충분하다.

**채택 쪽으로 바뀌면:** Phase 5 `local_ai` 와 같은 전용 환경 서브프로세스 구조 · 입력 `reference_video` · BVH 변환 단계 · 매니페스트 라이선스 조건을 Phase 6 형식 설계 초안으로 쓰고 다시 확인받는다. 이번에는 쓰지 않았다.

---

## 8. 미확인

| 항목 | 이유 · 확인 시점 |
| :--- | :--- |
| GEM-X 의 Windows 설치 · 12 GB VRAM · 속도 | 받지도 실행하지도 않았다 |
| 전투 동작 · 무기 가림 · 빠른 휘두름 품질 | 공개 자료 없음 — 시험 전에는 말할 수 없다 |
| `motion.pt` 텐서 형태 · 관절 이름 순서 · 손가락 동작 | 문서에 없음 — 첫 실행 |
| SAM License · DINOv3 License 가 GEM-X 체크포인트에 미치는 범위 | 이슈 #32 가 답하지 않음 — V-1 |
| GEM-X 학습의 '상업 호환 실제 영상'의 정체 | 카드 미기재 |
| SOMA 자산 v0.3.3 의 카드 표기 · 크기 | 카드는 v0.3.0 까지 |
| Move 출력 형식 · 앱 무료 플랜 상업 조건 · 보관 기간 | 약관에 없음 |
| DeepMotion 유료 금액 | 공식 페이지에서 읽지 못함 · 2차 출처 불일치 |
| Rokoko 출력의 소유 · 상업 명시 · 무료 등급 워터마크 | 약관에 명시 없음 · 2차 출처만 |
| Rokoko Create 업로드가 판매 데이터셋에 들어가는가 | 원문이 말하지 않음 |
| Plask 현행 약관(2023 판 뒤 변경 여부) | 페이지가 2023 판 |
| UE 5.8 플러그인 Fab 라이선스 · SMPL-X 포함 여부 · 번들 모델 조건 | Fab 403 · 포럼 주장 · Epic 답 없음 |
| Meshcapade 플랫폼 종료 날짜 | 2차 출처 불일치 |
| QuickMagic 약관 | 원문 못 찾음 |
| BEDLAM 데이터 라이선스 | 읽지 않음 — SMPL 조건으로 결론 불변 |
| §5 의 법적 해석 | 원문이 답하지 않는다 — 사용자 판단 |

---

## 부록. 출처 (2026-11-04 열람)

| 번호 | 출처 |
| :--- | :--- |
| G1 | GEM-X README — <https://github.com/NVlabs/GEM-X> |
| G2 | GEM-X 모델 카드 — <https://huggingface.co/nvidia/GEM-X> |
| G3 | GEM-X 파일 목록 — <https://huggingface.co/nvidia/GEM-X/tree/main> |
| G4 | `ATTRIBUTIONS.md` — <https://github.com/NVlabs/GEM-X/blob/main/ATTRIBUTIONS.md> |
| G5 | 설치 — <https://github.com/NVlabs/GEM-X/blob/main/docs/INSTALL.md> |
| G6 | 사전학습 모델 — <https://github.com/NVlabs/GEM-X/blob/main/docs/PRETRAINED_MODELS.md> |
| G7 | 추론 — <https://github.com/NVlabs/GEM-X/blob/main/docs/DEMO.md> |
| G8 | 모델 개요 — <https://github.com/NVlabs/GEM-X/blob/main/docs/MODEL_OVERVIEW.md> |
| G9 | `setup.cfg` — <https://github.com/NVlabs/GEM-X/blob/main/setup.cfg> |
| G10 | 변경 이력 — <https://github.com/NVlabs/GEM-X/blob/main/CHANGELOG.md> |
| G11 | 이슈 #32 체크포인트 라이선스 — <https://github.com/NVlabs/GEM-X/issues/32> |
| G12 | 이슈 #17 BVH 기준 포즈 — <https://github.com/NVlabs/GEM-X/issues/17> |
| G13 | 이슈 #20 손 · 얼굴 — <https://github.com/NVlabs/GEM-X/issues/20> |
| G14 | 이슈 #24 카메라 — <https://github.com/NVlabs/GEM-X/issues/24> |
| G15 | 이슈 #26 발이 골반 위 — <https://github.com/NVlabs/GEM-X/issues/26> |
| G16 | 이슈 #27 손 표류 — <https://github.com/NVlabs/GEM-X/issues/27> |
| G17 | 비공식 복제 카드(참고만) — <https://huggingface.co/WANGFEI1989/GEM-X> |
| G18 | Motion 벤치마크 정의 — <https://github.com/NVlabs/GEM-X/blob/main/docs/MOTION_BENCHMARKS.md> |
| G19 | 이슈 목록 — <https://github.com/NVlabs/GEM-X/issues> |
| G20 | `body_video_native77.yaml` — <https://github.com/NVlabs/GEM-X/blob/main/docs/configs/body_video_native77.yaml> |
| G21 | 옛 커밋 `gem_smpl` — <https://huggingface.co/nvidia/GEM-X/tree/f27ad5890b596c4192cc085b8e37a268b1f0e3c9/gem_smpl> |
| S1 | SOMA-X 저장소 — <https://github.com/NVlabs/SOMA-X> |
| S2 | SOMA-X 카드 — <https://huggingface.co/nvidia/SOMA-X> |
| S3 | SOMA 레이어 API — <https://nvlabs.github.io/SOMA-X/stable/api/somalayer.html> |
| A1 | SAM License — <https://github.com/facebookresearch/sam-3d-body/blob/main/LICENSE> |
| A2 | SAM 3D Body — <https://github.com/facebookresearch/sam-3d-body> |
| A3 | DINOv3 License — <https://github.com/facebookresearch/dinov3/blob/main/LICENSE.md> |
| A4 | Human-Art — <https://github.com/IDEA-Research/HumanArt> |
| A5 | ViPE — <https://github.com/nv-tlabs/vipe> |
| L1 · L2 | GVHMR LICENSE · 설치 — <https://github.com/zju3dv/GVHMR> |
| L3 · L4 | WHAM README · LICENSE — <https://github.com/yohanshin/WHAM> |
| L5 · L6 | 4D-Humans README · LICENSE — <https://github.com/shubham-goel/4D-Humans> |
| L7 | TRAM — <https://github.com/yufu-wang/tram> |
| L8 · L9 | PromptHMR README · LICENSE — <https://github.com/yufu-wang/PromptHMR> |
| L10 | GENMO — <https://github.com/NVlabs/GENMO> |
| C1 | Move One API EULA — <https://move.ai/move-one-api-eula> |
| C2 | Move One App EULA — <https://move.ai/move-one-app-eula> |
| C3 · C4 | Move 요금 — <https://docs.move.ai/knowledge/move-one-pricing> · <https://developers.move.ai/docs/pricing/> |
| C5 · C6 | DeepMotion 약관 · 개인정보 — <https://www.deepmotion.com/terms-of-use> · <https://www.deepmotion.com/privacy-policy> |
| C7 · C8 · C9 | DeepMotion 요금 · API · 문서 — <https://www.deepmotion.com/pricing-animate3d> · <https://www.deepmotion.com/animate-3d-api> · <https://www.deepmotion.com/doc/animate-3d> |
| C10 · C11 | Rokoko 약관 · 개인정보 — <https://www.rokoko.com/studio-term-of-use> · <https://www.rokoko.com/privacy-policy> |
| C12 · C13 | Rokoko 제품 · 데이터셋 — <https://rokoko.com/products/video> · <https://www.rokoko.com/mocap/motion-dataset> |
| C14 · C15 | Plask 약관 · 개인정보 — <https://plask.ai/docs/100002> · <https://plask.ai/en-US/docs/100001> |
| C16 · C17 | Plask 요금 · API — <https://plask.ai/en-US/pricing> · <https://plask.ai/docs/8> |
| E1 | Epic MetaHuman 모노 영상 문서 — <https://dev.epicgames.com/documentation/metahuman/metahuman-animation-from-mono-video-capture-in-unreal-engine> |
| E2 | Digital Production 기사 — <https://digitalproduction.com/2026/06/23/metahuman-gets-markerless-mocap/> |
| E3 · E4 | Epic 포럼(사용자 글) — <https://forums.unrealengine.com/t/licensing-question-shipping-metahuman-animator-markerless-motion-capture-runtime-models-in-a-steam-game/2839692> · <https://forums.unrealengine.com/t/epic-games-metahuman-animator-markerless-motion-capture-plugin/2729293?page=3> |
| E5 | Max Planck 보도 — <https://www.mpg.de/26082348/max-planck-spin-off-meshcapade-draws-epic-games-to-tuebingen> |
| 조사 | [로컬 모델 조사](LocalModelSurvey.md) — [D1] AMASS · [D5] SMPL · [K4] NVIDIA Open Model License |
