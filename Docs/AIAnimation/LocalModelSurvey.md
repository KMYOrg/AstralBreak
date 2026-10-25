# AI 애니메이션 생성 자동화 — Phase 5 로컬 Text-to-Motion 모델 조사

작성일: 2026-10-24  
상태: 조사 완료 · **채택**(2026-10-24, 사용자 — Kimodo-SOMA-RP-v1.2) · **설치 완료**(`D:\AnimGenModels\Kimodo\`, 항목별 승인 · 파일 SHA-256 대조) · `local_ai` 구현 · 검증 완료(2026-10-25 — [지침서](DevelopmentGuide.md) 개정 8 §2.2 · §4 · §14 Phase 5, [감사](ArchitectureAudit.md) §15). 아래 본문은 조사 시점(2026-10-24, 설치 전) 기록이고 §7 매니페스트 반영안은 그대로 적용됐다. §8 의 "이 PC 실측"은 지침서 §2.2 · 감사 §15 에 있다.  
관련 문서: [개발 지침서](DevelopmentGuide.md) §2.4 · §4 · §14 Phase 5 · §16-4 · 부록 B · [Phase 0 감사](ArchitectureAudit.md)

**방법.** 모델 저장소 README · LICENSE · Hugging Face 모델 카드 · 데이터셋 라이선스 원문을 웹으로 읽었다(2026-10-24 시점 — 라이선스는 바뀔 수 있다). 코드 · 가중치는 받지 않았고 실행하지 않았다. 그래서 **VRAM · 속도 · Windows 동작은 공식 문서의 수치이고 이 PC 실측이 아니다.** 법률 자문이 아니다 — 원문 조항과 그 조항이 이 프로젝트의 어디에 걸리는지만 적고, 이용 목적에 따라 갈리는 판단은 §4 에 남겨 사용자가 정한다.

**이 PC.** RTX 3080 Ti 12 GB(드라이버 610.88, 평소 약 3.4 GB 사용 중) · RAM 64 GB · i7-12700KF · Windows 11 · Python 3.13 만 설치 · CMake · MinGW g++(Strawberry) 있음 · Docker 없음 · D: 여유 270 GB.

---

## 요약

| 모델 (공개 시점) | 코드 | 가중치 | 학습 데이터 | 지역 | 이 PC 호환 | BVH → Phase 4 | 판정 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Kimodo SOMA-RP v1.2** (NVIDIA, 2026-10) | Apache-2.0 | NVIDIA Open Model License — "ready for commercial use" | Bones Rigplay(700 h, 독점 · NVIDIA 라이선스) | 제한 없음(전 세계 · 수출 규제 준수) | ○ 텍스트 인코더를 CPU로(VRAM < 3 GB 공식) · Windows 비공식 | **직접 BVH 출력**(SOMA 77관절 · cm) | **적법 · 호환 후보** (조건 §3.3) |
| ARDY SOMA (NVIDIA, 2026-07) | Apache-2.0 | NVIDIA Open Model Agreement | Bones Rigplay 1 | 제한 없음 | △ Ubuntu만 테스트 · 텍스트 인코더 약 14 GB | NPZ만 — BVH 변환 직접 작성 | 적법 · 호환 낮음(2순위) |
| Kimodo SMPLX-RP v1 | Apache-2.0 | **NVIDIA R&D Model License**(연구용) | Bones Rigplay → SMPL-X | — | — | AMASS NPZ | 상업 부적법 · 제외 |
| HY-Motion 1.0 / Lite (Tencent, 2025-12) | Tencent HY-Motion 1.0 Community | 같음 | 영상 추출 + 모캡 + 애니 애셋 | **한국 · EU · UK 제외** | ✕ VRAM 최소 26 / 24 GB | 미기재 | **부적법(지역) · 비호환** — 기록만 |
| MDM (2022~2025) | MIT | 미기재 | HumanML3D ← **AMASS** | 없음 | ○(미측정) | ✕ 관절 위치만 · SMPL 필수 | 상업 부적법 · 포트폴리오는 §4 |
| MoMask (2023) | MIT | 미기재 | HumanML3D ← AMASS | 없음 | ○ CPU 데모 가능 | △ IK 로 BVH(22관절 · 20 fps) | 상업 부적법 · 포트폴리오는 §4 |
| T2M-GPT (2023) | Apache-2.0 | 미기재 | HumanML3D · KIT-ML | 없음 | ○(미측정) | ✕ 관절 위치 | 상업 부적법 · 포트폴리오는 §4 |
| MotionGPT (2023) | MIT | 미기재 | HumanML3D ← AMASS | 없음 | ○(미측정) | ✕ 관절 위치 · SMPL 메시 | 상업 부적법 · 포트폴리오는 §4 |
| MLD (2023) | MIT | 미기재 | HumanML3D ← AMASS | 없음 | ○(미측정) | ✕ | 상업 부적법 · 포트폴리오는 §4 |
| MotionLCM (2024) | **"not allowed for commercial usage"** | 미기재 | HumanML3D ← AMASS | 없음 | ○(RTX 3090 테스트) | ✕ 관절 위치 | 상업 부적법(코드부터) · 포트폴리오는 §4 |
| MotionStreamer (2025) | 미확인 | 미기재 | HumanML3D · BABEL ← AMASS ("solely for academic purposes") | 없음 | 미확인 | △ 별도 저장소 | 상업 부적법 · 포트폴리오는 §4 |
| MoMask++ (SnapMoGen, 2025) | 미확인 | 미기재 | HumanML3D ← AMASS + SnapMoGen(라이선스 미표기) | 없음 | 미확인 | △ BVH 변환 가능(데이터 쪽) | 상업 부적법(HumanML3D 포함) · SnapMoGen 미확인 |

**결론:** 이용 목적과 상관없이 원문 조건상 적법하고, 출력이 이미 BVH 라서 Phase 4 Blender → Phase 1 리타깃 경로에 바로 이어지는 후보는 **Kimodo-SOMA-RP-v1.2 하나**다. 공개 Text-to-Motion 의 주류(HumanML3D 학습 모델 전부)는 학습 데이터 AMASS 가 "상업 용도를 위한 신경망 학습"을 금지해 상업 이용은 부적법이고, 개인 포트폴리오 이용은 판단이 갈린다(§4 — 사용자 판단). HY-Motion 1.0 은 한국이 라이선스 지역 밖이라 목적과 상관없이 쓸 수 없다. 추천안은 §6.

---

## 1. 판정 기준

| 항목 | 기준 |
| :--- | :--- |
| 적법 | 코드 · 가중치 · 학습 데이터 · 필수 의존 모델(텍스트 인코더 · 바디 모델)의 **원문 조건**이 한국에서 이 프로젝트(UE 게임의 애니 애셋 제작, 현재 개인 포트폴리오)의 이용을 허용한다. 하나라도 막으면 부적법. 조건이 목적에 따라 갈리면 그대로 적고(§4) 판단하지 않는다 — 지침서 §16-4 |
| 호환 | ① RTX 3080 Ti 12 GB 에서 추론(텍스트 인코더 CPU 이전 등 공식 옵션 포함) ② Windows 에서 서브프로세스로 실행(`blender` Provider 와 같은 Job 모델 — 지침서 §3.4) ③ 출력이 BVH(또는 BVH 로 손실 없이 바뀌는 로컬 회전)라 Phase 4 `blender` 변환(BVH → 더미 스킨 FBX) → Phase 1 `retarget` 으로 `SKEL_UE5_F` 까지 간다 |
| 출처 | 각 행 끝의 번호 → 부록 출처. 원문이 말하지 않는 것은 "미기재", 찾지 못한 것은 "미확인" |

---

## 2. 데이터셋 · 공통 의존의 이용 조건

모델 판정은 대부분 여기서 갈린다. 공개 모델 저장소들은 같은 문구로 이 조건을 넘긴다 — MDM · MoMask · MotionGPT · MLD: "uses datasets which each have their own respective licenses that must also be followed" [M1 · M2 · M4 · M5].

| 대상 | 원문 조건 (요지 · 짧은 인용) | 이 프로젝트에 걸리는 점 | 출처 |
| :--- | :--- | :--- | :--- |
| **AMASS** (MPI-IS) | 허용: "non-commercial scientific research", 비상업 교육 · 비상업 예술 프로젝트. "Any other use, in particular any use for commercial purposes, is prohibited." **"prohibits the use of the Dataset to train methods/algorithms/neural networks/etc. for commercial use of any kind"**. 재배포 · 제3자 제공 금지. 지역 조항 없음(준거법 독일). 상업 라이선스 문의 `ps-license@tue.mpg.de` | HumanML3D · BABEL · Motion-X(AMASS 부분)로 학습한 모든 가중치. 상업 이용은 명시적으로 막힌다. 포트폴리오가 "비상업 연구 · 교육 · 예술"에 드는지, 그리고 데이터를 직접 받지 않은 가중치 사용자에게 이 계약이 미치는지는 §4 | [D1] |
| **HumanML3D** | 저장소 MIT. "originates from a combination of HumanAct12 and Amass dataset". "Due to the distribution policy of AMASS dataset, we are not allowed to distribute the data directly" — 재구성에 SMPL+H · DMPL 바디 모델 필요. 스켈레톤 = SMPL 22관절 | AMASS 조건을 그대로 물려받는다. 텍스트 주석의 별도 라이선스는 미기재 | [D2] |
| HumanAct12 | Action2Motion 저장소(MIT 코드)에서 배포. 데이터 이용 조건 미기재 | 미확인 | [D3] |
| KIT-ML | 공식 라이선스 문서를 찾지 못함 — 원 논문은 "open"이라고만 한다 | 미확인 | [D4] |
| **SMPL** 바디 모델 (MPI-IS) | AMASS 와 같은 틀: 비상업 과학 연구 · 교육 · 예술만, 상업 금지, "prohibits the use of the Software to train methods/algorithms/neural networks/etc. for commercial use of any kind". 상업 라이선스는 Meshcapade | MDM 은 생성 경로에서도 SMPL 을 연다(`Rotation2xyz` 생성자가 `SMPL()` 로드). 메시 렌더(SMPLify) 경로를 쓰는 모델 전부 | [D5] · [M1c] |
| Motion-X | "request authorization to use Motion-X for non-commercial purposes". 하위 데이터(AMASS · GRAB 등) 각각 별도 라이선스 | Motion-X 학습 모델은 비상업 | [D6] |
| BONES-SEED (Bones Studio) | 학술(비상업 연구 · 평가 · 교육) 또는 연 매출 100만 달러 미만 스타트업 내부 이용. §6 이 데이터로 모션을 만드는 생성 모델을 만드는 것을 막는다(요지). 귀속 표기 필수 | 이 프로젝트가 **데이터를 직접 받지 않으므로** 걸리지 않는다. Kimodo `*-SEED` 체크포인트는 이 데이터로 학습했다 — NVIDIA 와 Bones 의 별도 계약은 공개 문서로 확인하지 못했다 → 추천은 RP 체크포인트 | [D7] · [D8] |
| Bones Rigplay | Kimodo · ARDY 모델 카드: "Proprietary Bones Rigplay Dataset", 700 h, "Is there provenance for all datasets used in training? Yes" | 데이터는 받을 수 없다(독점). 이용 조건은 모델 라이선스(NVIDIA Open Model License)가 정한다 | [K2] · [K3] |
| **Meta Llama 3 8B Instruct** (Kimodo · ARDY 텍스트 인코더) | Meta Llama 3 Community License(2024-04-18): "worldwide … royalty-free limited license", 월간 사용자 7억 초과 시 별도 라이선스, Acceptable Use Policy 준수, Llama 자료나 그 출력으로 다른 LLM 개선 금지. **배포하거나 Llama 를 쓰는 제품 · 서비스를 제공하면** "Built with Meta Llama 3" 표시 · 라이선스 사본 · 저작권 고지. 지역 제외 없음(EEA · 스위스는 계약 주체만 다름). Hugging Face 에서 **게이트** — 계정 정보 공유 · 약관 동의 후 접근 | 생성기 안에서만 텍스트를 임베딩하고 게임에는 Llama 가 들어가지 않는다. 그래도 약관 동의는 사용자가 직접 해야 한다(내가 대신 동의하지 않는다). 표시 의무가 생성된 애니 애셋까지 미치는지는 원문이 "product or service that uses any of them" 이라 §4 에 남긴다 | [L1] · [L2] |
| LLM2Vec 어댑터 (McGill-NLP) | `LLM2Vec-Meta-Llama-3-8B-Instruct-mntp` 모델 카드 "License: mit" | 걸리는 점 없음 | [L3] |
| NVIDIA Open Model License (2025-10-24판) | "Models are commercially usable." "perpetual, worldwide, non-exclusive, no-charge, royalty-free, revocable" · "NVIDIA claims no ownership rights in outputs" · 파생 모델 허용 · 모델을 배포할 때 "Licensed by NVIDIA Corporation under the NVIDIA Open Model License" 고지 · 안전 가드레일을 우회하면 자동 종료 · 특허 · 저작권 소송 제기 시 종료 · 수출 규제 준수 · Trustworthy AI 약관(불법 감시 · 생체정보 불법 수집 · 괴롭힘 · 기만 금지 — 게임 · 폭력 묘사 · 무기 관련 조항 없음) | 출력(애니 데이터)은 NVIDIA 소유가 아니다. 모델 자체를 배포하지 않으면 고지 의무는 생기지 않는다 | [K4] · [K5] |
| NVIDIA R&D Model License | Kimodo SMPLX-RP 의 라이선스(README 표). 연구용 | 제외 | [K1] |

---

## 3. 모델별

### 3.1 HumanML3D 계열 (MDM · MoMask · T2M-GPT · MotionGPT · MLD · MotionLCM · MotionStreamer · MoMask++)

공통: 코드는 대부분 MIT/Apache 지만 **가중치 라이선스를 따로 밝힌 곳이 없고**(Google Drive · Hugging Face 링크만), 저장소가 데이터셋 라이선스를 따르라고 한다. 학습 데이터가 AMASS 파생이라 판정은 §2 AMASS 행이 정한다.

| 모델 | 코드 라이선스 | 가중치 | 학습 데이터 | 환경 (원문) | 출력 · BVH 경로 | 출처 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| MDM | MIT ("This code is distributed under an MIT LICENSE") · CLIP · SMPL · SMPL-X · PyTorch3D 의존 명시 | Google Drive, 라이선스 미기재 | HumanML3D · KIT · HumanAct12 · UESTC | Ubuntu 18.04.5 · Python 3.7 · conda · spaCy · CLIP(git) · SMPL 파일 스크립트 · GPU 1개 | `results.npy` = 관절 xyz 위치, 최대 9.8초. `render_mesh` = SMPLify 로 SMPL θ · OBJ. **BVH 없음.** 2024-04 50-step(20배 빠름), DiP | [M1] · [M1c] |
| MoMask | MIT · 같은 의존 문구 | Google Drive, 미기재 · HF Space 데모 | HumanML3D · KIT-ML | Python 3.7.13 + PyTorch 1.7.1(conda) 또는 Python 3.10(pip) · CLIP · "No GPU is required to use MoMask"(WebUI 데모) | `(nframe, 22, 3)` 관절 위치 + **BVH**(`joints2bvh.py`: 템플릿 BVH + `BasicInverseKinematics`, 20 fps, SMPL 불필요) · 발 IK `_ik` "sometimes will fail" | [M2] · [M2b] |
| T2M-GPT | Apache-2.0 | 스크립트 · HF 미러 `vumichien/T2M-GPT`, 미기재 | HumanML3D · KIT-ML | Python 3.8 · PyTorch 1.8.1 · 학습 V100-32G | npy · SMPL 렌더 선택 · BVH 없음 | [M3] |
| MotionGPT | MIT · 같은 의존 문구 · T5-770M | HF `OpenMotionLab`, 미기재 | HumanML3D(학습) · KIT-ML(평가) | Python 3.10.6 · PyTorch 2.0.0 · spaCy · SMPL 스크립트 | `(nframe, 22, 3)` · SMPL 메시 `.ply` · BVH 없음 | [M4] |
| MLD | MIT | Google Drive, 미기재 | HumanML3D | Python 3.9.12 · PyTorch 1.12.1 | 관절 위치 · SMPL | [M5] |
| MotionLCM | **"MotionLCM LICENSE" — "not allowed for commercial usage"** | Google Drive · HF Space | HumanML3D | Python 3.10.12 · PyTorch 1.13.1 · RTX 3090 · SMPL · sentence-t5-large | `joints (nframes, njoints, 3)` pickle · SMPL 메시 | [M6] |
| MotionStreamer | 미확인(페이지에 이름 없음) | HF `lxxiao/MotionStreamer`, 미기재 | HumanML3D · BABEL 272차원 — "The processed data is solely for academic purposes"(AMASS 라이선스 링크) | 미기재 · sentence-T5-XXL | 위치/회전 복원 · BVH 는 별도 저장소 | [M7] |
| MoMask++ (SnapMoGen) | 미확인 | Google Drive, 미기재 | HumanML3D + SnapMoGen(43.7 h 모캡, 데이터 카드 라이선스 칸이 빈 자리표시) | Python 3.8.20 | SnapMoGen 원본은 BVH · 특징 → BVH 변환 가능 | [M8] · [D9] |

**호환 요약:** 모두 HumanML3D 표현(SMPL 22관절 · 20 fps · 대개 10초 안팎)이고, 대부분 **관절 위치만** 내놓는다. 회전은 IK 로 다시 풀어야 하며(MoMask 만 내장, 저자도 발 IK 가 실패할 수 있다고 적음) 손가락이 없다. Phase 4 경로에 넣으려면 MoMask BVH 를 쓰거나 위치 → 회전 IK 를 직접 붙여야 한다. 공식 문서는 Linux · 구버전 Python(3.7~3.10)이고 Windows 안내는 없다(MDM 의 ffmpeg 안내만). VRAM 은 원문 수치가 없다(T2M-GPT 학습 V100 32 GB · MotionLCM RTX 3090 테스트) — 추론은 12 GB 안일 가능성이 높지만 **미측정**.

**판정:** 상업 이용 = **부적법**(AMASS · SMPL 의 "commercial use of any kind" 학습 금지, MotionLCM 은 코드부터 비상업). 개인 포트폴리오 = **§4 사용자 판단**. 호환 = MoMask 만 실용(IK BVH), 나머지는 BVH 변환을 직접 만들어야 한다.

### 3.2 HY-Motion 1.0 (기록만)

| 항목 | 내용 | 출처 |
| :--- | :--- | :--- |
| 라이선스 | "TENCENT HY-MOTION 1.0 COMMUNITY LICENSE AGREEMENT". Territory = "the worldwide territory, excluding the territory of the European Union, United Kingdom and South Korea". 월간 사용자 100만 초과 시 별도 라이선스. 출력으로 다른 AI 모델 개선 금지. AUP 포함 | [H1] |
| 학습 데이터 | 영상 1,200만 클립에서 GVHMR 로 복원한 동작 + 모캡 + 3D 애니 애셋(모캡 · 애셋 약 500 h). 논문은 AMASS · HumanML3D 를 학습 소스로 적지 않는다 | [H2] |
| 모델 · 출력 | 1.0B(Lite 0.46B) DiT flow matching · SMPL-H 골격 22관절(손 없음) · 6D 회전 · 텍스트 Qwen3-8B + CLIP-L · 내보내기 형식 미기재 | [H2] · [H3] |
| 환경 | VRAM 최소 **26 GB / Lite 24 GB**(줄이는 옵션 `--num_seeds=1` · 프롬프트 30단어 미만 · 5초 미만) · "supports macOS, Windows, and Linux" | [H3] |

**판정:** **부적법 — 한국이 라이선스 지역 밖**이라 이용 목적과 상관없이 쓸 수 없다(지침서 §2.4 결정 유지). 12 GB 로는 공식 최소 VRAM 에도 못 미친다. 별도 적법 라이선스 없이 설치 · 활성화하지 않는다.

### 3.3 Kimodo — 추천 후보

NVIDIA(`nv-tlabs`)의 운동학 모션 확산 모델(2026-03-16 공개, SOMA-RP v1.2 = 2026-10-15). 텍스트 + 키프레임 · 끝단 위치 · 2D 경로 제약을 받는다.

| 항목 | 내용 | 출처 |
| :--- | :--- | :--- |
| 코드 | "This codebase is licensed under Apache-2.0" (LICENSE: Apache 2.0, © 2026 NVIDIA). "model checkpoints and data are licensed separately as indicated on the HuggingFace download pages" | [K1] · [K6] |
| 가중치 | `nvidia/Kimodo-SOMA-RP-v1.2`: "released under the NVIDIA Open Model License" · "ready for commercial use". 282M 파라미터(0.3B F32) · v1 `model.safetensors` 1.13 GB(v1.2 크기는 카드에 없음) | [K2] · [K3] · [K7] |
| 체크포인트 선택 | README 표 9종 — SOMA · G1 은 NVIDIA Open Model, **SMPLX-RP-v1 만 NVIDIA R&D Model**. "we recommend using the models trained on the full Bones Rigplay 1 dataset". v1.2 = v1.1 의 BONES-SEED 테스트 누수 수정 · 발 미끄러짐 감소(텍스트 일치 점수는 약간 낮음) | [K1] · [K2] |
| 학습 데이터 | Bones Rigplay — 700 h 광학 모캡 · SOMA 골격 · 텍스트 설명, 독점, 출처 확인 "Yes" · 남녀 배우 비슷한 수 | [K2] · [K3] |
| 텍스트 인코더 | LLM2Vec — **게이트 모델 `meta-llama/Meta-Llama-3-8B-Instruct`** 접근 승인 + HF 읽기 토큰 필요(§2 Llama 행). 어댑터 MIT | [K8] · [L2] · [L3] |
| 지역 | 모델 카드 "Deployment Geography: Global". NVIDIA OML · Llama 3 모두 지역 제외 없음(수출 · 제재 규정 준수) | [K3] · [K4] · [L1] |
| VRAM | "Kimodo requires ~17GB of VRAM to generate locally entirely on GPU, primarily due to the text embedding model". `TEXT_ENCODER_DEVICE=cpu` → "reduces VRAM usage to <3 GB"(조금 느림, 2026-04-24 개선). 이 PC 는 RAM 64 GB 라 Llama 3 8B(BF16 약 16 GB — 파라미터 × 2바이트 추정) CPU 적재가 들어간다 | [K1] |
| 환경 | 테스트 GPU RTX 3090 · 4090 · A100(카드는 30 · 40 · 50 시리즈 · Ampere 포함, OS "Linux and Windows"). README: "developed on Linux, though Windows should work especially if using Docker". Python 3.10 예시 · "Anything over PyTorch 2.0" · `requires-python >=3.8` | [K1] · [K3] · [K8] · [K9] |
| 의존성 | `transformers==5.1.0` · `peft` · `hydra-core` · `gradio` · `trimesh` · `scenepic` · `av` · `bvhio` · `boto3` 등(pip 순수 패키지). 선택 `[soma]` = SOMA-X, `[demo]` = viser. **C++ 확장 `motion_correction`**(CMake, Windows 는 MinGW g++ 또는 `CMAKE_GENERATOR`) — 발 미끄러짐 후처리. `SKIP_MOTION_CORRECTION_IN_SETUP=1` 이면 빼고 설치(그때 후처리 경로는 `RuntimeError` → `--no-postprocess`) | [K9] · [K10] · [K11] |
| 출력 | 30 fps · **최대 10초(300프레임)**. NPZ(`posed_joints` · `global_rot_mats` · `local_rot_mats` · `foot_contacts` · `root_positions` …, 77관절). **`--bvh`** → "standard plain-text BVH", `somaskel77`, 미터 → cm, 루트 이동 + 관절별 로컬 회전. 기준 포즈 기본 = BONES-SEED 형식, `--bvh_standard_tpose` = 표준 T 포즈. Kimodo 좌표 = "y-up, +z forward" | [K12] · [K2] |
| BVH 구조 (`exports/bvh.py`) | 원점 래퍼 관절 `Root`(위치 3 + `Zrotation Yrotation Xrotation`) → 그 자식 `Hips`(같은 6채널) → 나머지 회전 3채널(ZYX). End Site 를 지운다. `bvhio` · PyGLM 으로 기록(소수 6자리) | [K13] |
| 골격 이름 (SOMA77) | `Hips` · `Spine1` · `Spine2` · `Chest` · `Neck1` · `Neck2` · `Head` · `LeftShoulder` · `LeftArm` · `LeftForeArm` · `LeftHand` · 손가락(Thumb1~3 · Index/Middle/Ring/Pinky1~4 · `*End`) · `LeftLeg`(넓적다리) · `LeftShin` · `LeftFoot` · `LeftToeBase` · `LeftToeEnd` … 모델 내부는 손가락이 거의 없는 30관절 → 77로 바꿀 때 손은 `relaxed_hands_rest_pose` | [K14] · [K15] |
| 커뮤니티 | Windows 설치 가이드(gist)는 `SKIP_MOTION_CORRECTION_IN_SETUP=1` + **비공식 fork 의 미리 빌드한 휠**을 쓴다 — 출처가 공식이 아니어서 쓰지 않는다. 4비트 양자화 fork · C++/GGML 포트(kimodo.cpp)도 있다 | [K16] |

**적법:** 코드 Apache-2.0 · 가중치 NVIDIA Open Model License(상업 가능 · 전 세계 · 출력 소유 주장 없음) · 학습 데이터는 NVIDIA 가 라이선스한 독점 데이터(사용자에게 데이터 조건이 따로 오지 않음) · 텍스트 인코더 Llama 3(전 세계 · 7억 MAU 기준 · AUP). 원문상 **포트폴리오 · 상업 둘 다 허용**되고 지역 제한이 없다. 남는 조건(§4 표의 K 행): ① Llama 3 약관 동의를 사용자가 직접 한다 ② NVIDIA OML 가드레일 · 소송 종료 조항 ③ 모델을 재배포하지 않는다(고지 의무 회피) ④ "Built with Meta Llama 3" 표시가 생성 애셋을 쓰는 게임에도 필요한지.

**호환:** VRAM 은 공식 CPU 텍스트 인코더 옵션으로 12 GB 안(< 3 GB). 출력 BVH 가 Phase 4 `blender` 입력 형식과 같다 — `bvh.py` 가 읽는 표준 BVH, 단위 cm(`motion_file.unit` `cm`), y-up · +z 정면(CMU 와 같은 축 — Phase 4 기본 `axis_forward -Z` · `axis_up Y` 에 정면 자동 측정). 남는 위험은 2단계 설계에서 다룬다(§5).

### 3.4 ARDY (2순위)

| 항목 | 내용 | 출처 |
| :--- | :--- | :--- |
| 라이선스 | 코드 Apache-2.0 · 체크포인트 NVIDIA Open Model Agreement("ready for commercial or non-commercial use" — G1 카드) | [A1] · [A2] |
| 데이터 · 모델 | Bones Rigplay 1 · 자기회귀 확산(실시간 · 스트리밍 텍스트) · Core 20 fps · G1 25 fps · SOMA 30 fps(+ KimodoRep 변형) · SIGGRAPH 2026 | [A1] · [A3] |
| 환경 | Ubuntu 22.04 · RTX 4090 · Python 3.11 에서 주로 테스트 · Windows 언급 없음 · 기본 텍스트 인코더 "~14 GB VRAM"(같은 LLM2Vec · Llama 3 게이트) · TensorRT 선택 | [A1] |
| 출력 | NPZ(관절 위치 · 회전 · 루트 · 발 접촉 · fps) · G1 CSV · **BVH 언급 없음** · `scripts/generate.py` 오프라인 생성 있음 | [A1] |

**판정:** 적법(Kimodo 와 같은 구조). 호환은 Kimodo 보다 낮다 — BVH 기록을 직접 만들어야 하고 Windows 언급이 없다. 실시간성은 애셋 생성에 필요 없다.

---

## 4. 이용 목적에 따라 갈리는 판단 (사용자 결정)

이 프로젝트의 현재 목적은 개인 포트폴리오(취업 지원용 공개 저장소 · 시연)이고, 이후 상업 출시 여부는 정해지지 않았다. 아래는 원문이 답하지 않아 **판단을 대신하지 않은** 항목이다.

| # | 대상 | 갈림 | 원문 근거 |
| :---: | :--- | :--- | :--- |
| H-1 | HumanML3D 계열 모든 가중치 | **상업:** AMASS 가 "train methods/algorithms/neural networks/etc. for commercial use of any kind"를 금지 → 부적법. **포트폴리오:** AMASS 허용 범위는 "non-commercial scientific research" · 비상업 교육 · 비상업 예술 프로젝트 — 취업용 포트폴리오가 여기에 드는지 원문이 정하지 않는다 | [D1] |
| H-2 | 같음 | AMASS 계약 당사자는 **데이터를 내려받은 사람**이다. 우리는 데이터를 받지 않고 제3자가 학습한 가중치만 받는다. 모델 저장소들은 "datasets … licenses that must also be followed"라고 가중치 사용자에게 넘긴다. 이 조건이 가중치 사용자에게 법적으로 미치는지는 원문이 말하지 않는다 | [D1] · [M1] · [M2] |
| H-3 | 같음 | 공개 저장소에 생성 애셋(`.uasset`)을 올리면 그것이 "made available … to any third party" 인 데이터 파생물인지 — AMASS 는 데이터 재배포를 막지만 모델 출력에 대한 조항은 없다 | [D1] |
| H-4 | MDM 등 SMPL 의존 | SMPL 파일도 비상업 · 재배포 금지 — 생성 경로에서 SMPL 을 여는 MDM 은 SMPL 조건이 하나 더 붙는다 | [D5] · [M1c] |
| K-1 | Kimodo · ARDY | 목적에 따른 갈림 없음 — NVIDIA OML 은 상업 이용을 명시 허용한다. 단 Llama 3 라이선스 §1.b.i 의 "a product or service that uses any of them" 에 **생성 애셋만 담긴 게임**이 드는지는 원문이 정하지 않는다(게임은 Llama 를 실행하지 않는다). 든다고 보면 "Built with Meta Llama 3" 표시를 게임 · 문서에 넣으면 된다 | [L1] |
| K-2 | Kimodo · ARDY | Llama 3 게이트 모델의 약관 동의 · 계정 정보 공유는 **사용자 본인의 행위**다(내가 대신 동의하지 않는다). 동의하지 않으면 Kimodo 를 쓸 수 없다(텍스트 인코더 필수) | [L2] · [K8] |

---

## 5. Kimodo → Phase 4 → Phase 1 경로 (호환 상세 · 2단계 입력)

```text
local_ai(Kimodo CLI, 별도 venv 서브프로세스)  kimodo_gen "<prompt>" --model Kimodo-SOMA-RP-v1.2 --duration ≤10 --bvh [--bvh_standard_tpose]
  → <ImportSourceRoots>/LocalAI/<job_id>/A<n>/*.bvh       (SOMA77 · cm · 30 fps · y-up +z 정면)
  → blender (Phase 4 그대로)                               motion_file{unit: cm, facing: auto} → 더미 스킨 FBX · 바닥 맞춤
  → import_animation_file → retarget(match_existing) → validate_animation → /Game/.../AS_<영웅>_<계열>_<동작>
```

| 위험 | 내용 | 2단계 대응 후보 (설계 초안에서 확정) |
| :--- | :--- | :--- |
| 루트 래퍼 | BVH 루트가 원점의 `Root` 이고 이동은 자식 `Hips` 에 있다(Phase 4 CMU 는 루트 = `Hips`). `bvh.py` 는 `JOINT_POSITION_CHANNELS` 경고를 내고, Blender 는 위치 채널이 있는 본을 연결하지 않아 이동이 남는다. UE 루트 본 = `Root`(정지) → 리타기터 Root Motion op 가 소스 루트를 복사하면 루트 모션이 없고 골반만 움직인다 | ① `Root` 를 빼고 `Hips` 를 루트로 다시 쓰는 BVH 정리(NPZ `local_rot_mats` + `root_positions` 로 직접 기록 — 순수 Python) ② 또는 리타기터 Root Motion op 를 골반 기준 생성으로. 실측으로 고른다 |
| 다리 이름 | SOMA 는 `LeftLeg` = 넓적다리 · `LeftShin` = 정강이. HumanIK · Mixamo 템플릿은 `LeftUpLeg` = 넓적다리 · `LeftLeg` = 정강이 → 자동 캐릭터라이즈가 잘못 맞출 수 있다 | 계획에 SOMA 수동 체인(골반 `Hips`)을 고정 — Phase 4 CMU 수동 체인 9개와 같은 방식(`retarget.source_chains`) |
| 기준 포즈 | 기본 BVH 기준 포즈 = BONES-SEED 형식, `--bvh_standard_tpose` = 표준 T 포즈 | 리타기터 자동 정렬이 맞추기 쉬운 쪽을 실측으로 고른다(첫 후보 T 포즈) |
| 손가락 | 모델은 손가락 없는 30관절로 생성 — 77관절 BVH 의 손은 고정 포즈 | 한계 `FINGERS_STATIC` |
| 길이 · fps | 최대 10초 · 30 fps 고정 | 요청 `duration_seconds` > 10 → 계획 제외 `UNSUPPORTED_REQUEST`(매니페스트 `max_duration_seconds: 10`), fps 다르면 Phase 4 리샘플 · `FRAME_RATE_MISMATCH` |
| Windows 설치 | 공식 테스트는 Linux. C++ 확장 `motion_correction` 빌드(CMake + MinGW g++ — 이 PC 에 둘 다 있음)가 실패할 수 있다. 시스템 Python 은 3.13 뿐(문서 예시 3.10) | 별도 venv · Python 버전은 2단계 설치 계획에서 승인받는다. 빌드 실패면 `SKIP_MOTION_CORRECTION_IN_SETUP=1` + `--no-postprocess`(발 미끄러짐 후처리 없음 → 한계로 기록). 비공식 휠은 쓰지 않는다 |
| 메모리 · 시간 | CPU 텍스트 인코더 = Llama 3 8B 를 RAM 에 적재(추정 16 GB+) · 매 호출 로드 시간 미측정. 에디터와 동시 실행 시 GPU 약 3.4 GB 사용 중 | 첫 실행 실측 → `subprocess_timeout_seconds` 확인. 필요하면 `kimodo_textencoder` 서버(공식 진입점) 상주는 별도 결정 |
| 다운로드 | Kimodo 체크포인트(v1 기준 1.13 GB) + Llama 3 8B Instruct(약 16 GB, 게이트) + LLM2Vec 어댑터 + pip 패키지(PyTorch CUDA 포함 수 GB) | 2단계 — 항목마다 출처 · 라이선스 · 크기를 보여 주고 승인 |
| 품질 | 공식 한계: "cartoon motions or non-physically plausible motions" 불가 · 학습 데이터 편향 경고. 무기 파지 없음(낫 · 라이플) | 기존 한계 `GRIP_NOT_VALIDATED` · `DRAFT_NEEDS_CLEANUP` 그대로(지침서 §5) |

---

## 6. 추천안

**채택 후보: Kimodo-SOMA-RP-v1.2 (NVIDIA)** — 이 조사에서 원문 조건상 적법하고(목적 무관, 지역 제한 없음) 이 PC · Phase 4 경로와 호환될 근거가 있는 유일한 후보다.

- 채택 전제: 사용자가 Hugging Face 에서 `meta-llama/Meta-Llama-3-8B-Instruct` 약관에 직접 동의하고 읽기 토큰을 둔다(§4 K-2). §4 K-1(Llama 표시)을 어떻게 볼지 정한다.
- 채택하면 2단계: 설치 위치(저장소 밖 또는 `Saved/AnimGen/LocalAI/` 아래 별도 venv — `Tools/mcp/.venv` 는 건드리지 않음) · 다운로드 항목별 출처 · 라이선스 · 크기 → 항목마다 승인 → `local_ai` 설계 초안 · 커밋 단위 → 확인 → 구현(§5 위험 실측 포함).
- **채택하지 않으면** "적합 모델 없음"이 아니라 "적법 · 호환 후보는 있으나 미채택"으로 기록하고 `local_ai` 를 비활성으로 둔다.
- HumanML3D 계열은 §4 H-1 ~ H-3 를 사용자가 포트폴리오 이용 가능으로 판단하더라도 상업 전환 시 다시 막히고, 회전 품질(IK) · 손가락 · 20 fps 한계가 있어 추천하지 않는다. HY-Motion 1.0 은 쓸 수 없다.

---

## 7. 매니페스트 반영안 (결정 후 — 아직 바꾸지 않음)

현재 `providers.json` 의 `local_ai` 는 `license: "unverified"` 이고 구현이 없어 상태가 `PROVIDER_UNAVAILABLE` · `NOT_IMPLEMENTED` 다(`providers/base.py` `state()` 는 구현 여부를 라이선스보다 먼저 본다).

| 결정 | 매니페스트 | 코드 |
| :--- | :--- | :--- |
| Kimodo 채택 | `license: "ok"` · 모델 · 라이선스 출처 · `max_duration_seconds: 10` · `requires_gpu: true` · `output_formats: ["bvh"]` · 설명에 조건(Llama 3 게이트 · RP 체크포인트만) | `local_ai` 구현(2단계 설계 초안에서) |
| 미채택 | `license: "restricted"` 등 조사 결론 + 설명에 이 문서 링크 | `state()` 가 비활성 자리의 사유로 `NOT_IMPLEMENTED` 대신(또는 함께) 라이선스 결론을 내도록 하는 작은 변경 — 현재 구조로는 `unavailable_reason` 에 조사 결론이 드러나지 않는다. 변경 전 확인받는다 |

함께 고칠 지침서 항목(결정 후): §2.4 "공개 Text-to-Motion 모델" 행 · 부록 B "공개 Text-to-Motion 모델의 학습 데이터 라이선스" 행 · 부록 A 출처 · 상태 줄.

---

## 8. 미확인

| 항목 | 이유 · 확인 시점 |
| :--- | :--- |
| 이 PC 의 실제 VRAM · RAM · 시간 · Windows 설치 성공 여부 | 받지도 실행하지도 않았다 — 2단계 설치 후 실측 |
| Kimodo v1.2 체크포인트 크기 · LLM2Vec 어댑터 크기 | 카드에 없음 — 2단계 다운로드 승인 때 파일 목록으로 확인 |
| Kimodo BVH 의 정확한 정면 · 기준 포즈 모양 | 문서는 "y-up, +z forward"(SMPL-X 내보내기 설명)까지 — 첫 출력에서 `bvh.facing` 으로 잰다 |
| HumanAct12 · KIT-ML · SnapMoGen 데이터 라이선스 · MotionStreamer · MoMask++ 코드 라이선스 | 원문을 찾지 못함. HumanML3D 계열 판정은 AMASS 로 이미 정해져 결론에 영향 없음 |
| NVIDIA 와 Bones Studio 의 BONES-SEED 학습 계약 | 공개 문서 없음 → SEED 체크포인트는 추천에서 뺐다 |
| §4 의 법적 해석(H-1 ~ H-3 · K-1) | 원문이 답하지 않는다 — 사용자 판단 |

---

## 부록. 출처 (2026-10-24 열람)

| 번호 | 출처 |
| :--- | :--- |
| D1 | AMASS License — <https://amass.is.tue.mpg.de/license.html> |
| D2 | HumanML3D — <https://github.com/EricGuo5513/HumanML3D> |
| D3 | Action2Motion (HumanAct12) — <https://github.com/EricGuo5513/action-to-motion> |
| D4 | The KIT Motion-Language Dataset (Plappert et al., 2016) — <https://arxiv.org/abs/1607.03827> |
| D5 | SMPL Model License — <https://smpl.is.tue.mpg.de/modellicense.html> |
| D6 | Motion-X — <https://github.com/IDEA-Research/Motion-X> |
| D7 | BONES-SEED 데이터 카드 — <https://huggingface.co/datasets/bones-studio/seed> |
| D8 | BONES-SEED License — <https://bones.studio/info/seed-license> |
| D9 | SnapMoGen 데이터 카드 — <https://huggingface.co/datasets/Ericguo5513/SnapMoGen> |
| M1 · M1c | MDM — <https://github.com/GuyTevet/motion-diffusion-model> · `model/rotation2xyz.py`(생성자에서 `SMPL()` 로드) |
| M2 · M2b | MoMask — <https://github.com/EricGuo5513/momask-codes> · `visualization/joints2bvh.py` |
| M3 | T2M-GPT — <https://github.com/Mael-zys/T2M-GPT> |
| M4 | MotionGPT — <https://github.com/OpenMotionLab/MotionGPT> |
| M5 | MLD — <https://github.com/ChenFengYe/motion-latent-diffusion> |
| M6 | MotionLCM — <https://github.com/Dai-Wenxun/MotionLCM> |
| M7 | MotionStreamer — <https://github.com/zju3dv/MotionStreamer> |
| M8 | MoMask++ / SnapMoGen — <https://github.com/snap-research/SnapMoGen> |
| H1 | HY-Motion 1.0 License — <https://raw.githubusercontent.com/Tencent-Hunyuan/HY-Motion-1.0/master/License.txt> |
| H2 | HY-Motion 1.0 논문 — <https://arxiv.org/abs/2512.23464> |
| H3 | HY-Motion 1.0 저장소 — <https://github.com/Tencent-Hunyuan/HY-Motion-1.0> |
| K1 | Kimodo 저장소 README — <https://github.com/nv-tlabs/kimodo> |
| K2 | Kimodo-SOMA-RP-v1.2 모델 카드 — <https://huggingface.co/nvidia/Kimodo-SOMA-RP-v1.2> |
| K3 | Kimodo-SOMA-RP-v1 · SOMA-SEED-v1 모델 카드 — <https://huggingface.co/nvidia/Kimodo-SOMA-RP-v1> · <https://huggingface.co/nvidia/Kimodo-SOMA-SEED-v1> |
| K4 | NVIDIA Open Model License — <https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/> |
| K5 | NVIDIA Trustworthy AI Terms — <https://www.nvidia.com/en-us/agreements/trustworthy-ai/terms/> |
| K6 | Kimodo LICENSE — <https://github.com/nv-tlabs/kimodo/blob/main/LICENSE> |
| K7 | Kimodo-SOMA-RP-v1 파일 목록 — <https://huggingface.co/nvidia/Kimodo-SOMA-RP-v1/tree/main> |
| K8 | Kimodo 설치 문서 — <https://research.nvidia.com/labs/sil/projects/kimodo/docs/getting_started/installation.html> |
| K9 | Kimodo `pyproject.toml` — <https://github.com/nv-tlabs/kimodo/blob/main/pyproject.toml> |
| K10 | Kimodo `setup.py`(`motion_correction` CMake 확장) — <https://github.com/nv-tlabs/kimodo/blob/main/setup.py> |
| K11 | Kimodo `kimodo/postprocess.py` — <https://github.com/nv-tlabs/kimodo/blob/main/kimodo/postprocess.py> |
| K12 | Kimodo 출력 형식 문서 — <https://research.nvidia.com/labs/sil/projects/kimodo/docs/user_guide/output_formats.html> |
| K13 | Kimodo `kimodo/exports/bvh.py` — <https://github.com/nv-tlabs/kimodo/blob/main/kimodo/exports/bvh.py> |
| K14 | Kimodo 골격 문서 — <https://research.nvidia.com/labs/sil/projects/kimodo/docs/key_concepts/skeleton.html> |
| K15 | Kimodo 골격 정의 소스 — <https://research.nvidia.com/labs/sil/projects/kimodo/docs/_modules/kimodo/skeleton/definitions.html> |
| K16 | 커뮤니티(참고만, 사용 안 함) — Windows gist <https://gist.github.com/Aero-Ex/3affd23c4c9632dbff3045f4ae3655ec> · 양자화 fork <https://github.com/matbeedotcom/kimodo> |
| A1 | ARDY 저장소 — <https://github.com/nv-tlabs/ardy> |
| A2 | ARDY-G1 모델 카드 — <https://huggingface.co/nvidia/ARDY-G1-RP-25FPS-Horizon8> |
| A3 | ARDY 프로젝트 페이지 — <https://research.nvidia.com/labs/sil/projects/ardy/> |
| L1 | Meta Llama 3 Community License — <https://www.llama.com/llama3/license/> |
| L2 | Meta-Llama-3-8B-Instruct 모델 카드(게이트) — <https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct> |
| L3 | LLM2Vec 어댑터 — <https://huggingface.co/McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp> |
