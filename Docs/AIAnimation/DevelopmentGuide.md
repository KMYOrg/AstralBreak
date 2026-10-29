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
개정 8: 2026-10-25 — Phase 5(로컬 AI) 구현·실측 반영. 조사 결론과 채택(NVIDIA Kimodo-SOMA-RP-v1.2, §2.4), `local_ai` Provider(전용 venv 서브프로세스 · 오프라인 · 텍스트 인코더 CPU — §4 · §6), 요청 `prompt` · `generation` · `review` · `fix` · `retarget.align_mode` · `retarget.body_clearance`(§9), 생성 BVH → `blender` 변환 사슬(§5), 리타깃 정렬 엔진 함정과 `per_bone` 정렬 · 기준 포즈 FBX 2단 임포트 · 손가락 체인 · 팔-몸통 관통 보정(§2.3 · §10 · §13), §14 Phase 5 결과.  
개정 9: 2026-10-25 — Phase 6(외부 AI — Meshy Text-to-Motion) 공식 문서 확인 · 구현. API · 크레딧 가격 · Rate Limit · 만료 · 약관(§2.4 · 부록 A · B), `external.meshy` Provider(HTTP 어댑터 · 비동기 Job · 잔액 확인 · 요청 로그 — §4), 크레딧 × 사용자 환율 비용 추정과 장부의 크레딧(§6), 요청 `generation.options`(§9), poll 단계 실패의 환불 · 과금 반영(§3.4 · §6), §14 Phase 6.  
개정 10: 2026-10-25 — Phase 7(AnimBP 연결 · 승격) 설계 확정 · 구현 · 실측. 새 Tool `promote_animation`(엔진 AssetTools rename — 자동 저장이라 사전 검사 + `confirm`, ini `PromotionPaths`), 기존 쓰기 Tool 6개의 옵트인 `generation_guard`(기본 = 기존 동작), 요청 `package` · `anim_bp`(§9), 계획 단계 `package_*` · `anim_bp_test` · `anim_bp_prepare`(§5), `INTEGRATION_FAILED`(§7), 운영 AnimBP 적용 승인 게이트와 노티파이 순서(§12), §14 Phase 7 결과.  
개정 11: 2026-10-26 — Phase 8-1(생성 품질) 설계 확정 · 첫 실험 E1 · Kimodo 소스 대조 · 구현 · 실측. 요청 플래그 `two_hand_weapon_grip` · `foot_contact` → `local_ai` 2차 생성 제약(§4 · §5 · §9), seed 후보 · select 단계 · 점수 선별(§5 · §7 · §13 · §14), 파지 플래그면 관통 기본 `measure`(§9 · §10), Kimodo 후처리 실측에 따른 제약 형식 정정(§14 Phase 8 · 감사 §18). 같은 날 보강: 사용자 Persona 소견 4가지 → 수정안 A(2차 출력 시간 스무딩 σ 1프레임) · B(손 회전 keep — 1차 손목 굽힘 유지) · C(선별 — 관통 이중 계산 제거 · 파지면 비파지 관통 · 궤적 폭 `attack`) 적용 · 같은 4 seed 재생성(§9 · §14 Phase 8 '수정안 A · B · C' · 감사 §18). 보강 2: 기준 무기 = Vesper 낫 — 파지 간격 상한 · 파지 판정 띠 · 손별 궤적 폭 · 양손 겹침 기록 · 낫 프롬프트 재생성(§14 Phase 8 '낫 기준 보정'). 보강 3: 낫 정정 — 팔 꼬임 · 머리 · 배 관통(§14 Phase 8 '낫 정정'). 보강 4: 파지 띠를 대상 메시 골격 치수로 · 요청 `target_spacing_cm`(§9 · §14 Phase 8 '파지 띠 정정').  
개정 12: 2026-10-26 — Phase 8-2(Vesper 캡처) 설계 확정 · 엔진 소스 대조 · 구현 · 실측. 새 Tool `capture_animation`(임시 프리뷰 월드 + 정사영 SceneCapture → PNG · 시트 · 소스 골격 비교 시트 · 연속 프레임 — 애셋 0 · 새 더티 0, ini `CaptureOutputRoots`, 오류 `CAPTURE_FAILED`), 요청 `review.capture` → `review` 파이프 capture 단계(모든 경로) · APNG(표준 라이브러리) · Job `review.capture`(§2.3 · §3 · §4 · §5 · §7 · §9 · §13 · §14 Phase 8 '8-2'), 채팅 표시 = Saved 밖 캡처 루트 + SendUserFile.  
개정 13: 2026-10-27 — Phase 8-3(자동 보정) 설계 확정 · E0 실측 · 엔진 소스 대조 · 구현 · 실측. 요청 `fix.timing`(리타깃 뒤 **대상** 시퀀스 — 손목 속도로 휘두름 구간 탐지 → 기존 `retime` · `trim` 으로 가속 · 정지 머리/꼬리 트림, 모든 경로, `direct_key` timing 단계), `fix.ops` 사전(smooth · stance_width · foot_lock — Blender 변환 단계, 다리는 **리타깃된 다리의 모델**(Pelvis Motion op 배율 · 회전 + 소스 뼈 방향 · 대상 길이) 안에서 한 풀이 → 대상 발 고정), 저장된 Kimodo BVH 의 SOMA 기본값, `capture_animation` 비교 칸 루트에 캡처 루트(§2.3 · §4 · §5 · §7 · §9 · §13 · §14 Phase 8 '8-3'). 같은 날 보강(8-3 후속): 품질 탐침에서 나온 8-3 의 새 문제 2건 — 가속 구간 끊김 → 새 C++ 편집 op `time_warp`(단조 3차 시각 사상 · antialias) + `timing.py` 배율 곡선(trim 하나 + time_warp 하나), 무릎 굽힘 증가 → `stance_width.keep_knee_bend`(골반 상승), 떨림 기준 = 균일 r 배 기대값(§14 Phase 2 op 표 · §14 Phase 8 '8-3 후속' · 감사 §20).  
개정 14: 2026-10-27 ~ 28 — Phase 8-4(대상 쪽 보정) 총괄 설계 확정(결정 A ~ G — Python 한 풀이 + C++ 얇은 입출력 · 4단위 a → b → c → d · 낫 손잡이 = 요청의 무기 공간 선분 · 새 측정 옵트인) · **8-4a(기반 — 측정 한 원천 · 입출력 · 무기 부착 캡처 · E0)** 엔진 소스 대조 · 구현 · 실측. C++ 5개(전부 옵트인 — 기본 결과 불변): `validate_animation body_clearance` v2(`parts: "all"` 팔 3 × 몸 6 부위 쌍 — 머리 · 목 · 위팔 · 몸통 칸, `legs` 다리끼리, `per_frame`, `model` 몸 모델 내보내기) · `profile_rotations` · 편집 op `bone_deltas{space: parent}` · `capture_animation attachments`(무기 부착) · `inspect_skeleton geometry`(메시 주축 · 단면), 순수 Python `anim_gen/body_model.py`(C++ 몸 모델을 같은 규칙으로 재현 — 8-4b 한 풀이의 바탕), E0(비교 대상 16개 '전' 수치 · 낫 부착값 · 자루 선 · 왼손 파지 선분 제안 · 사건 · 낫 붙인 '전' 캡처)(§2.3 · §8 · §13 · §14 Phase 2 op 표 · Phase 8 '8-4a' · 감사 §21). 같은 날 **8-4b(한 풀이 엔진 + 지시 목표)** 구현 · 실측: 파이프 `body_fit`(control_rig 자리) · 순수 Python `anim_gen/body_fit.py` · 요청 `fix.body`(+ `targets[]` — 자연어 지시 → 목표는 Claude Code) · 리타깃 관통 기본 measure 전환 · C++ 옵트인 `body_clearance.hands`(양손끼리)(§4 · §5 · §9 · §10 · §13 · §14 Phase 8 '8-4b' · 감사 §21-2).  
상태: Phase 1 · 2 · 3 · 4 · 5 · 6 · 7 완료 · **Phase 8-1 구현 · 검증 + 수정안 A · B · C(2026-10-26, 사람의 Persona 재판정 대기)** · **Phase 8-2 구현 · 검증(2026-10-26 — 캡처는 판정 근거, 판정은 사람)** · **Phase 8-3 구현 · 검증 + 후속 수정 2건(가속 끊김 · 무릎 굽힘, 2026-10-27 — 전후 캡처 사용자 판정 통과 · antialias 1.0 확정, 남은 검 다리 떨림은 8-4 ③)** · **Phase 8-4a 구현 · 검증(2026-10-28 — 기반, 낫 붙인 '전' 캡처는 판정 근거 · 8-4b ~ d 는 사용자 승인 뒤 단위마다)** · **Phase 8-4b 구현 · 검증(2026-10-28 — 관통 목표 쌍은 대부분 해소, 파지 keep · 충실도 일부 · 지시 목표 경로(떨림 · 구간 밖 변화)는 기준 미달 — 사용자 판정 · 결정 대기)**(§14). Phase 6 완료 기준 ① 실제 유료 1건은 **미실행으로 마감**(사용자 Meshy 계정이 Free 요금제 — API 생성은 유료 요금제만, 2026-10-25 사용자 결정). Phase 7 은 운영 AnimBP 실제 적용을 완료 기준에서 뺐다(사용자 결정 — 미리보기 · revision · 복제본 검증까지). 다음 = 8-1 결과 Persona 판정 → 기준값 · 가중치 보정 → 8-2(Vesper 캡처) 또는 8-3 · 8-4 — 사용자 승인 후. 3D 메시 생성(Tripo)은 애니 파이프라인 밖 별도 트랙(§14 끝).  
관련 문서: [AnimGraphMcp README](../../Plugins/AnimGraphMcp/README.md) · [Phase 0 감사](ArchitectureAudit.md) · [Phase 5 로컬 모델 조사](LocalModelSurvey.md)

| 항목 | 내용 |
| :--- | :--- |
| 환경 | Windows 11 · UE 5.7.4 소스 빌드 · C++ · Python 3.13 · Claude Code · MCP |
| 구조 | Multi-Provider + 규칙 기반 라우터 + 폴백 + 공통 리타깃 처리 + 기존 AnimBP MCP 연결 |
| 기본 정책 | Free-First · 유료 API는 명시 승인 · 비파괴 · Editor 전용 |

---

## 개정 14 변경 요약 (Phase 8-4a — 대상 쪽 보정 기반 · 8-4b 한 풀이)

| 항목 | 개정 13 | 개정 14 (8-4a 설계 확정 · 엔진 소스 대조 · 구현 · 실측) | 위치 |
| :--- | :--- | :--- | :--- |
| 몸 전체 관통 측정 | `body_clearance` = 손 · 아래팔 ↔ 몸통 · 넓적다리 축 하나씩(`arms[]` — 위팔 · 머리 · 목 안 봄), 머리는 `head_near`(손 ↔ 머리 본 한 점) | 옵트인 `parts: "all"` — 팔 3(손 · 아래팔 · 위팔(어깨 0.4 × 위팔 길이 밖)) × 몸 6(몸통 칸 pelvis · belly · chest · 넓적다리 좌우 · head_neck) 36 쌍 · `legs`(다리끼리) · `per_frame` · 경고 `BODY_PENETRATION_PARTS` · `LEG_PENETRATION`. 같은 반경 지도 · 이웃 규칙 — 기본(키 없음) 결과는 비교 대상 16/16 같음(옛 빌드 baseline 대조). 사용자 소견 자리(낫 정정 선택 1.53초 손 → 머리 11.86 cm · 2.43초 왼 아래팔 → 배 6.53 cm)가 잡힌다 | §13 · §14 '8-4a' |
| 머리 꼭대기 (뿔) | — | 정수리 = 머리 축선 5 cm × scale 안 머리 정점의 최대 투영, 머리 지도 t ≤ 1.0 — 최대 투영 · t 1.05 는 Vesper 뿔(머리 관절 위 23 cm)이 칸을 채워 손이 정수리 위에 있어도 13 ~ 17 cm 가짜 관통 | §13 · 감사 §21 |
| 몸 모델 · 재현 | — | `body_clearance model` — 측정 점 전부 · 포즈 · 프레임별 반경 지도(base64, 최대 3.0 MB) → `anim_gen/body_model.py`(순수 — LBS · FK · 지도 조회 · 델타) 재현 차 p95 0.005 cm · 관통 % 같음(5건). Python 평가 최대 9.9 ms/프레임(다리 포함) → 감쇠 GN 24 평가 예측 29초(121 프레임) | §13 · §14 '8-4a' |
| 포즈 읽기 · 쓰기 | `profile_positions`(위치만) · 편집 op 는 구간 상수 오프셋(`offset_bone`)뿐 | `profile_rotations`(위치와 같은 시각의 회전) · 새 op `bone_deltas{space: parent, bones[{bone, rotation_deg[키마다], translation_cm[키마다]}]}`(0 = 원래 키 · 한 본 = 그 본과 자손만 · 키 수 불일치 `BAD_OP` · 원자성) | §13 · §14 Phase 2 op 표 |
| 무기 부착 캡처 | 메시 하나(무기 없음) | `capture_animation attachments[{mesh, socket \| bone, offset}]` ≤ 4 — 낫을 `WeaponHandR` 에 붙인 시트 · APNG(잘린 칸 0 · 더티 0). 게임 배치는 변환 2단(`AttachOffset` · `AttachTransform` · 소켓 · 손) — 캡처 offset 은 합성한 한 변환 | §2.3 · §14 '8-4a' |
| 무기 기하 | 인스펙터는 무기 정보를 추정하지 않음 | `inspect_skeleton geometry`(범위 · 주축 · 단면 · 본별) — 근거만, 손잡이 선분은 요청이 준다. 낫: 자루 선(좁은 단면 중심) ∥ 첫 주축 2.3° · TraceStart → End 0.35°, 운영 낫 왼손 파지 선분 제안 | §8 · §14 '8-4a' |
| DA 값 읽기 | 원격 실행(UDP) | 원격 실행이 안 되는 환경 — 에디터 시작 스크립트 `-ExecutePythonScript`(끝나면 에디터를 닫으므로 keep-alive, `Tools/mcp/e0_weapon_attach.py`) | §2.3 |
| (8-4b) 한 풀이 | `control_rig` 비활성 자리 · 관통 보정 = 리타깃 `resolve`(위팔만 · 팔마다) | 파이프 `body_fit` + 순수 Python `body_fit.py`(쇄골 · 위팔 · 팔꿈치 · 파지 프레임 두 손목, 목표 구간만 척추 · 목 · 골반 — 층 가중 감쇠 GN · 관통 몫 가중 매끈화 스플라인 · 재검사) → `bone_deltas` 새 애셋 → C++ 재측정. 요청 `fix.body` · 모든 경로 timing 뒤 · edit 앞, 리타깃 관통 기본 `measure`(`CLEARANCE_BY_BODY_FIT`) | §4 · §5 · §9 · §10 · §14 '8-4b' |
| (8-4b) 지시 목표 | — | `fix.body.targets[]`(부위 × 사건 · 시각 · 구간 × 몸 기준틀 위치 · 회전 × 완급 × soft/hard) — 자연어 → 목표는 Claude Code, 계획이 풀어 보이고(사건 → 프레임 · 부위 → 본 · 목표 위치) 못 닿으면 `TARGET_NOT_REACHED{blocked_by}` | §9 · §14 '8-4b' |
| (8-4b) 양손끼리 | 측정 없음(사용자 Persona 검 선택 f0 소견) | C++ 옵트인 `body_clearance.hands` — 팔마다 손 · 아래팔 지도 · 12 쌍 · `HAND_PENETRATION`(기본 결과 불변 16/16) | §13 |

---

## 개정 13 변경 요약 (Phase 8-3 — 자동 보정)

| 항목 | 개정 12 | 개정 13 (설계 확정 · E0 실측 · 엔진 소스 대조 · 구현 · 실측) | 위치 |
| :--- | :--- | :--- | :--- |
| 흐느적 | 휘두름 정점이 운영 공격의 1/2 ~ 1/4 · 4초 중 정지 꼬리 2.2 ~ 2.5초(검) · 정지 머리 0.9초(낫) — 프롬프트 · 선별로만 | 요청 `fix.timing` → 리타깃 뒤 **대상** 시퀀스(재사용이면 그 애셋 — 모든 경로)에서 `direct_key` timing 단계: `validate_animation profile` 손목 속도로 핵심(정점 50% 이상) · 휘두름(20% 까지 넓혀 국소 최소) · 정지 머리 / 꼬리(전신 < 30 cm/s) → 기존 `retime`(핵심 ×r = 1,200 ÷ 정점 · 상한 2.0, 앞뒤 계단 램프, 복귀 ×1.5) · `trim`(머리 0.2 · 꼬리 0.3초 남김) — 순수 `timing.py`, 정수 프레임 조각, 늦은 시각부터. 대상 스켈레톤의 기존 애셋이면 계획이 op · 결과 길이를 미리 보인다. Job `timing`, 한계 `TIMING_CHANGED_LENGTH` · `TIMING_NOT_APPLIED` | §4 · §5 · §7 · §9 · §13 · §14 |
| 넓은 다리 · 발 미끄러짐 | `fix.ops` 사전 비어 있음(`UNSUPPORTED_FIX_OP`) | 사전 `smooth` · `stance_width`(두 발 디딘 발 좌우 비 상한 3.0 — 대상 메시 기준, 사용자 결정) · `foot_lock` — `fix_ops.py`(이름 · 기본값 · 순서 한 곳) · `foot_fix.py`(순수) · `blender/fix_legs.py`. 다리 둘은 한 풀이로, **리타깃된 다리의 모델**(대상 골반 = 소스 골반 × 대상/소스 골반 높이 · 회전 변화 — `PelvisMotionOp.cpp DecodePose`, 다리 뼈 = 소스 방향 · 대상 길이) 안에서 풀어 그 뼈 방향을 소스에 입힌다 → 대상 발 고정. 실측: 소스 발만 고정하면 대상 미끄러짐이 줄지 않았다(낫 10.3 → 16.2 cm/s) → 모델 풀이로 4건 0.0 | §4 · §5 · §9 · §13 · §14 |
| 저장된 생성 결과 다시 보정 | — | SOMA77 BVH 를 `motion_file` 로 주면 local_ai 와 같은 리타깃 기본값(골반 · 체인 · 발 — `soma.py` 한 곳) — 다시 생성하지 않고 보정만. 기준 재현 4건 0.000 cm | §5 · §14 |
| 전후 캡처 | 비교 칸 이미지 = `ImportSourceRoots` 만 | `capture_animation` 비교 칸 이미지에 `CaptureOutputRoots` 도(앞선 캡처 = 보정 전) — C++ 1곳 · Automation | §2.3 · §14 |
| (보강) 가속 구간 끊김 | 구간 등속 `retime` 조각(계단 램프) — 떨림 최대 0.5 ~ 3.4 → 7.4 ~ 12.5 cm/프레임² | 새 C++ op `time_warp{knots, rates?, antialias?}`(새 시각 → 원 시각 단조 3차 Hermite — 속도 단차 · 새 이음매 없음, 1배보다 빠른 곳은 σ = c·√(배율² − 1) 프레임 가우시안으로 거른 뒤 고름) + `timing.py` 배율 곡선(출력 시각에 선형인 램프, 새 길이 정수 프레임 올림) → op = trim 하나 + time_warp 하나, `fix.timing.antialias` 기본 1.0. 떨림 최대 3.8 / 2.3 / 3.4 / 2.6(시간만) — 첫 판의 1/3 ~ 1/7 | §14 Phase 2 · Phase 8 '8-3 후속' |
| (보강) 떨림 기준 | 원본 × r² | 떨림 지표가 보폭에 민감해 원본 × r² 는 가속을 하는 한 못 지킨다 → **균일 r 배 기대값 × 0.8**(`motion_metrics.zigzag_at_rate`) | §14 Phase 8 '8-3 후속' |
| (보강) 무릎 굽힘 | 발을 모으면 무릎 굽힘 p50 37 ~ 42° → 48 ~ 60° | `stance_width.keep_knee_bend`(기본 참) — 좁힌 만큼 골반을 올려 엉덩 → 발목 거리를 원래대로(두 다리 중 작은 쪽, `foot_fix.pelvis_raise`) → 원본 + 0 ~ 3°, 상체는 골반과 함께 오름(골반 기준 0.01 cm) | §9 · §14 Phase 8 '8-3 후속' |

---

## 개정 12 변경 요약 (Phase 8-2 — Vesper 캡처)

| 항목 | 개정 11 | 개정 12 (설계 확정 · 엔진 소스 대조 · 구현 · 실측) | 위치 |
| :--- | :--- | :--- | :--- |
| 시각 근거 | `review.render` = 변환된 **소스 골격**(Blender), 대상 메시는 Persona 에서 사람이 연다 | 새 Tool `capture_animation`(C++, Tool 41) — 임시 `FPreviewScene` + 정사영 `SceneCapture2D` 로 시퀀스를 **대상 메시**(Vesper `SK_StreetDemon_F_01`)에 입혀 행(시각) × 뷰(정면 · 측면) PNG · 시트 · (소스 골격 이미지를 주면) 비교 시트 · 연속 프레임. 카메라 · 셀 규칙 = `review_render.py`(전 프레임 범위에 한 번 고정 · 셀 높이 512 · 폭 = 범위 비율) — 두 시트가 같은 행이라 나란히 본다. 애셋 0 · 새 더티 0(`UNEXPECTED_DIRTY`), 쓰기는 ini `+CaptureOutputRoots` 아래 새 폴더만, 오류 `CAPTURE_FAILED` | §2.3 · §3.1 · §3.2 · §3.3 · §13 |
| 요청 · 실행 | — | `review.capture{times? \| count?, views?, mesh?, sequence?, compare?}` → 새 파이프 `review` 의 capture 단계(검증 뒤 · 포장 앞, **모든 경로** — 생성 · 재사용 · 편집). render 가 있으면 그 시각을 행으로 쓰고 소스 골격 프레임을 비교 칸으로. 연속 프레임은 anim_gen 이 **APNG** 한 장으로 잇는다(표준 라이브러리 — ffmpeg · 패키지 설치 없음). Job `review.capture{sheet, compare_sheet, animation, frames, camera, …}`. 캡처 실패는 생성 실패가 아니다(한계 `REVIEW_NOT_CAPTURED`), 한계 `REVIEW_CAPTURE_PREVIEW_ONLY` | §3.4 · §4 · §5 · §7 · §9 |
| 채팅 표시 | — | 세션 권한 `Read(./Saved/**)` 거부가 SendUserFile 에도 걸린다(실측) → 캡처 루트는 Saved 밖 `Tools/mcp/results/capture/`(gitignore). 결과 PNG · APNG 를 SendUserFile 로 보인다 | §3.1 · §14 Phase 8 '8-2' |
| 엔진 함정 (실측) | — | ① 쇼 플래그는 등록이 덮어쓴다 → `SetShowFlagSettings` ② 틱 없는 프리뷰 월드는 동적 데이터로 스키닝이 갱신되지 않는다 → 포즈마다 `RecreateRenderState_Concurrent`(썸네일 장면과 같은 순서) ③ 메시는 본 밖으로 나온다 → 범위 = LOD0 정점을 본 로컬 상자로 | §2.3 · 감사 §19 |

---

## 개정 11 변경 요약 (Phase 8-1 — 생성 품질)

| 항목 | 개정 10 | 개정 11 (설계 확정 · 실측 · 구현) | 위치 |
| :--- | :--- | :--- | :--- |
| 플래그 | `two_hand_weapon_grip` · `foot_contact` = 한계(`GRIP_NOT_VALIDATED` · `FOOT_CONTACT_NOT_ENFORCED`) | `local_ai` 가 **2차 생성 제약**으로: 같은 seed 1차 → `local_ai/refine.py`(순수 Python) 가 1차 결과로 양손 파지 목표(주 손 너클 Index2 → Pinky2 = 손잡이 축, 간격 = 너클 폭 + 1 cm, `meet` = 두 손목을 함께 옮겨 보조 · 주 팔 길이 × 0.92 · 0.98 안 — 기본, `lead` = 주 손 궤적 그대로 · 비교용) · 1차 접지 발 · 1차 루트를 계산 → 2차. 한계 교체 `GRIP_POSITION_ONLY` · 진단 `FOOT_CONTACT_CONSTRAINED`. 그 밖의 Provider 는 그대로 | §4 · §5 · §9 · §14 |
| 후보 | `samples`(같은 seed) · `pick` | `generation.candidates` 1 ~ 6(seed, seed+1, … 한 Kimodo 실행) → **select 단계**(후보 전부 같은 RTG 로 리타깃 → `validate_animation profile_positions · body_clearance` 한 번 → `motion_metrics.py` 지표 → `selection.py` 점수 → 하나 → 최종 리타깃은 그 후보만). Job `selection`(후보별 수치 · 벌점 · 순위 · 근거 — 같은 기록 → 같은 선택), 한계 `SELECTED_BY_NUMBERS` | §5 · §7 · §9 · §13 · §14 |
| 관통 보정 | 기본 `resolve` | 비우면 계획이 정한다 — 파지 플래그면 `measure`(모든 Provider, 한계 `BODY_CLEARANCE_MEASURED_FOR_GRIP`), 명시 `resolve` 는 위험 `CLEARANCE_MAY_BREAK_GRIP`. 근거 E1(같은 seed `measure` vs `resolve`): 파지가 처음부터 없었고 보정은 손목을 p50 1.9 cm 더 벌렸다. C안(파지 + 관통 0)은 8-4 | §9 · §10 |
| Kimodo 제약 형식 (실측 정정) | 설계: 손 `EndEffectorConstraintSet(LeftHand, RightHand)`, 발 `left-foot` · `right-foot` | Kimodo 후처리는 클래스 이름으로만 고정 마스크를 만들고 목표를 회전 FK · 매끈한 루트로 다시 계산한다 — 손을 고정하면 처음 · 끝 12프레임이 되돌아가고, 발을 고정하면 미끄러진다. → **손 · 발 모두 일반 end-effector(확산 조건만) + root2d**, 후처리는 표준 접지 정리만(파지 100% · 발 위치 1차 ± 3.4 cm · 접지 미끄러짐 1차 수준). 제약 포즈는 팔 2본 IK 로 FK 와 맞춘다 | §14 Phase 8 · 감사 §18 |
| 선별 점수 기준 (실측 정정) | 설계: 발 좌우 비 `(p90 − 2.5) / 2.5` | Vesper 비가 소스보다 크다(엉덩 관절 폭이 좁다 — 기준 시험 5.55) → 폭 2.5 는 1.0 으로 포화 → **폭 5.0** | §14 Phase 8 · 감사 §18 |
| 실행 | Kimodo 기한 = 정책 | 기한 = 정책 + 25초 × (확산 − 1), 후보 BVH 는 Blender 한 실행(`bvh_to_fbx.py items`), 후보 임포트는 `Import/Motion/C<번호>/`(임포트는 빈 폴더만 — `DEST_NOT_EMPTY`) | §5 · §14 |
| Persona 소견 후 수정안 A · B · C (같은 날 보강) | 2차 생성 그대로 · 보조 손 방향을 주 손에 맞춤 · 선별 5지표 | A: 2차 출력 시간 스무딩 σ 1프레임(계획 `refine.smooth_sigma_frames` — 떨림 0.18 ~ 1.23 → ≤ 0.13). B: 손 회전 keep(보조 손목 최대 111.5 → 39.7°, seed 25). C: 깨짐에서 관통 경고 제외 · 파지면 비파지 관통 · 궤적 폭 `attack`(가중치 2) — 기록 후보 재계산 · 재생성 모두 seed 20261025. `motion_metrics` 버전 2(어깨 · 팔꿈치 역할, 떨림 · 손목 굽힘 · 손 들기 · 접지 미끄러짐 기록) | §9 · §14 Phase 8 · 감사 §18 |
| 낫 기준 보정 (같은 날 보강 2) | 파지 = 검 손잡이(간격 ≤ 30 · 판정 ≤ 20 cm) | Vesper 근접 무기 = 낫 → `spacing_cm` 상한 100 · 요청 간격이 있으면 파지 판정 '간격 ± 13 cm' · 궤적 폭 손별 큰 쪽(한손에도 맞게) · 양손 겹침 기록(`hand_contact`) · `motion_metrics` 버전 3. 낫 재생성(간격 60): Vesper 손목 간격 51 cm · 겹침 0 · 정점 +53% | §9 · §14 Phase 8 '낫 기준 보정' · 감사 §18 |
| 낫 정정 — 팔 꼬임 · 머리 · 배 관통 (같은 날 보강 3) | 손잡이 축 = 주 손 너클 · 파지면 비파지 관통만 · 꼬임 · 머리 지표 없음 | 축 = 1차 두 손목 방향(손목 2 cm 안이면 너클) · 자루 무기는 관통 전체 · `motion_metrics` 버전 4(`arm_cross` · `head_near`) · 벌점 `cross` · `head`(가중치 각 2, 기준 = 운영 낫 애니 0) · 통합 `scythe` 상한 검사. 재생성: Vesper 꼬임 12.5 ~ 91.7 → 0 ~ 5% · 선택 후보(seed 25 → 28) 머리 41.7 → 4.2% · 관통 75.2 → 6.6%. **파지 띠는 FAIL**(Vesper 간격 = 요청 × 0.79 — 띠 정의 후속). 남은 머리 · 배 · 가슴 관통(사용자 Persona)으로 8-4 범위를 '대상 쪽 몸 전체 관통 · 무기 파지'로 보강 | §9 · §14 Phase 8 '낫 정정' · 로드맵 '8-4 범위 보강 근거' · 감사 §18 |
| 파지 띠 정정 — 대상 메시 기준 간격 (같은 날 보강 4) | 자루 무기 띠 = (요청 간격 ± 13) × 대상 pelvis scale — FK 리타깃은 간격을 어깨 폭 · 팔 길이로 바꾸므로(Vesper × 0.79) 요청 > 52 cm 면 늘 띠 밖 | 간격 사상(두 골격 기준 포즈의 어깨 관절 폭 · 팔 길이 — 대상 = W_대상 + k × (생성 − W_생성), 기록 오차 ≤ 1 cm)을 계획이 한 번 풀어 generate(생성 간격 · 소스 띠 ± 13)와 select(대상 띠 ± 13 × k)가 같은 값을 쓴다 · 새 요청 `target_spacing_cm`(대상 메시 기준) · `motion_metrics` 버전 5 · 한계 `GRIP_SPACING_MAPPED`. 기록 재계산: Vesper 파지 4 ~ 38 → 100%(선택 그대로). 대상 60 cm 재생성: Vesper 간격 60.5 ~ 62.2 cm · 파지 100% · 선택 seed 28 머리 0 · 관통 0.8% · 통합 PASS | §9 · §14 Phase 8 '파지 띠 정정' · 감사 §18 |

---

## 개정 10 변경 요약 (Phase 7 — AnimBP 연결 · 승격)

| 항목 | 개정 9 | 개정 10 (설계 확정 · 엔진 소스 대조 · 구현 · 실측) | 위치 |
| :--- | :--- | :--- | :--- |
| 승격 | "AssetTools rename, 리디렉터 없음" 한 줄 | 새 Tool `promote_animation(assets[{source, dest}], dry_run, confirm, allow_referencers)` — `IAssetTools::RenameAssets` 는 새 패키지 · 참조 패키지를 **자동 저장**한다(사후 더티 비교로는 못 막음) → 사전 검사(후보 소스 · 클래스 · dest 규칙 · 참조자 · 맵 · 미저장 참조자 · 보호 · 네이티브 CDO) + `confirm`, 후보 경로 밖 참조자는 `allow_referencers` 로 명시. 사후 검증(리디렉터 0 · 옛 파일 · 내용 해시 · 참조 · 저장 집합). ini `+PromotionPaths=/Game/Animation/Hero/`(생성 경로와 겹치면 무시). 오류 `PROMOTE_FAILED` | §2.3 · §3.1 · §3.2 · §3.3 · §12 · §14 |
| 기존 쓰기 Tool | "기존 Tool 동작은 바꾸지 않는다" | `create_anim_montage` · `set_montage_sections` · `create_blendspace` · `set_sequence_additive` · `duplicate_animation_blueprint` · `apply_graph_operations` 에 옵트인 `generation_guard`(허용 목록 · 덮어쓰기 거부 · 전역 더티 비교 · 검사 뒤 저장 — 원천은 C++ `FWriteGuard` 한 곳). **기본 false = 기존 동작 그대로**(원칙의 범위 = 기본값) | §3.1 · §3.3 |
| 요청 | `integrate_anim_bp` → 한계 `ANIM_BP_NOT_INTEGRATED` | `package{additive?, montage?, blendspace?}` · `integrate_anim_bp: true` + `anim_bp{asset_path, operations[], scenario?, smoke}`(참인데 없으면 `MISSING_FIELD`, 거짓인데 있으면 `CONFLICTING_FIELDS`) · 자리표시 `$asset` · `$montage` · `$blendspace`. 한계 `ANIM_BP_APPLY_PENDING` · `NOTIFIES_NOT_ADDED`(`ANIM_BP_NOT_INTEGRATED` 폐지) | §9 |
| 라우터 · 실행 | 검증에서 끝 | 모든 후보의 검증 뒤 `package_additive` · `package_montage` · `package_blendspace` · `anim_bp_test`(복제본 적용 · 컴파일 · 스모크 · 시나리오 — 비동기) · `anim_bp_prepare`(운영 AnimBP revision · 미리보기 — 읽기만). 계획 때 슬롯 등록(`SLOT_NOT_IN_SKELETON`) · ABP 스켈레톤(`SKELETON_MISMATCH`) · 운영 미리보기(`PREVIEW_INVALID`) · revision 고정 | §5 |
| 실패 | — | 포장 · 연결 실패 = `INTEGRATION_FAILED`(폴백 없음 · 만든 시퀀스는 `generated_assets` 에 남음), 가드 오류는 그대로 중단 | §7 |
| 운영 AnimBP | 기존 Tool 로 연결 | **anim_gen 은 운영 AnimBP 에 쓰지 않는다** — Job `anim_bp.apply_payload{asset_path, operations, expected_revision, compile}` 까지. 적용은 사용자 승인 뒤 승격 → 바인딩을 정식 경로로 → `apply_graph_operations(expected_revision)`(가드 없이). Phase 7 완료 기준에서 실제 운영 적용은 뺐다(사용자 결정) | §12 · §14 |
| 노티파이 | — | 플러그인 = 몽타주 구조(슬롯 · 섹션 · 블렌드), 프로젝트 노티파이 = `astral-ue-montage` 스킬. 순서 = 생성 → 포장 → 확인 → 승격 → 정식 몽타주에 노티파이 → GA 지정(승인). 스킬의 "슬롯 이름 변경 · 다중 섹션 금지"는 Python API 한계였다 → 플러그인 Tool 로(스킬 문서 정정) | §12 |
| 설계 정정 (엔진 실측) | — | ① additive 기본 = `LocalAnimFrame 0`(설계 예시 `AnimFrame` + 기준 시퀀스 없음은 `IsValidAdditive` 가 거짓 — `AnimSequence.cpp:2627-2639`) ② `ABP_McpRuntimeTest` 의 Run 상태 플레이어는 SequencePlayer 라 `set_asset $blendspace` 가 안 된다 → BlendSpacePlayer 추가 · Speed 연결 · 교체 op ③ 짧은 몽타주는 `wait_frames` 안에 끝나 슬롯이 꺼진다 → 루프 섹션 ④ 복제본 이름에 Job 꼬리(`_Test_<job>A<n>`) — 스모크 테스트 이름이 애셋 이름이라 겹치지 않게 ⑤ additive 는 제자리 편집이라 재사용 애셋에는 거부(`ADDITIVE_ON_REUSED`) | §9 · §14 |

---

## 개정 9 변경 요약 (Phase 6 — 외부 AI · Meshy)

| 항목 | 개정 8 | 개정 9 (공식 문서 확인 · 구현) | 위치 |
| :--- | :--- | :--- | :--- |
| Meshy API | 엔드포인트 · Bearer 만 | `prompt` ≤ 400자 · `duration` 2 ~ 10초(0.5초 단위, 필수) · `mode` prime(FBX, 기본) / swift(BVH) → 태스크(`consumed_credits` · `expires_at` · `task_error`), 결과 3일 보존, 취소 없음(DELETE 는 PENDING 만 환불), 잔액 `GET /openapi/v1/balance`(무료), 초당 20 요청 · 동시 태스크 Pro 10, 테스트 모드 키 폐지(2026-09-16). **출력 리그는 문서에 없다** | §2.4 · 부록 A · B |
| 가격 | 미확인 | 크레딧은 공식(prime 10 · swift 3, 실패 환불). **돈 값은 요금제마다 달라(KRW 표시 · 크레딧 팩 비공개) 공식 문서로 확정할 수 없다** → 정책 `external.meshy.usd_per_credit`(사용자가 자기 요금제로 정함, 기본 null = `COST_UNKNOWN`) | §6 |
| 약관 · 데이터 | 미확인 | 유료 요금제 출력 소유 · 비 Enterprise 입력 · 출력 학습 사용 가능(§2.9) · 경쟁 AI 학습 금지 · 지역 제한 없음 → 사용자 수용(`license: ok`). 보내는 것은 프롬프트 · 길이 · 모드뿐 | §2.4 · §16-11 |
| `external.meshy` | 비활성 자리 | `providers/meshy.py`: 계획(보낼 본문 고정 · 네트워크 없음) → 승인된 유료 단계 안에서만 잔액 → 제출 → poll(Retry-After) → 결과 다운로드(인증 헤더 없음 · https · 형식 바이트) → prime = import, swift = blender 변환 → retarget(자동 IK Rig). 요청 로그 `<state>/external/meshy_requests.jsonl` | §4 · §14 |
| 요청 | — | `generation.options{<provider>: {...}}` — 그 Provider 만 읽는 설정(`{"external.meshy": {"mode": "swift"}}`), 이름은 레지스트리로 검사 | §9 |
| 장부 · Job | USD 만 · poll 실패는 예약 유지 | reserve · charge 에 `credits`, Job `cost.credits{estimated, actual}`. **poll 단계 실패**도 Provider 가 환불(`charged: false`)이나 실제 과금을 알려 주면 반영(전에는 제출 단계만) | §3.4 · §6 |
| 비용 추정 | `estimate(request)` | `estimate(request, policy)` — 정책이 환산을 정하는 Provider 용. 계획 후보 `estimated_credits`, 견적 `credits` · `usd_per_credit` | §6 |
| Phase 6 마감 | — | 완료 기준 ② · ③ · ④ 충족, ① 실제 유료 1건은 **미실행**(사용자 Meshy Free 요금제 — API 생성 402). 유료 요금제에서 `anim_gen_phase6_test.py --real` 로 실행 | §14 |
| Phase 8 로드맵 | "품질 · 세그먼트" 한 줄 | Kimodo 칼 휘두르기 시험(사용자 Persona 판정: 다리가 많이 벌어짐 · 베기가 흐느적)을 근거로 8-1 생성 품질 · 8-2 Vesper 캡처 · 8-3 자동 보정 · 8-4 무기 파지 4단위. 세그먼트는 그 뒤. 상세 시그니처는 착수 때 개정 10 | §14 |
| 별도 트랙 | — | 3D 메시 생성(Tripo — 텍스트 → 모션 없음)은 애니 파이프라인 밖 별도 트랙, 애니 자동화 뒤 | §2.4 · §14 |

---

## 개정 8 변경 요약 (Phase 5 — 로컬 AI · Kimodo)

| 항목 | 개정 7 | 개정 8 (조사 · 엔진 소스 대조 · 실측) | 위치 |
| :--- | :--- | :--- | :--- |
| 로컬 모델 | "공개 Text-to-Motion 은 학습 데이터 조건 미확인" | HumanML3D 계열(MDM · MoMask · T2M-GPT …)은 AMASS 가 "commercial use of any kind" 학습을 금지 → 상업 부적법(포트폴리오는 원문이 정하지 않음). HY-Motion 1.0 은 한국 제외. **유일한 적법 · 호환 후보 Kimodo-SOMA-RP-v1.2 채택**(2026-10-24, 사용자) | §2.4 · 부록 B · [조사](LocalModelSurvey.md) |
| `local_ai` | 비활성 자리(`NOT_IMPLEMENTED`) | Kimodo 전용 venv 를 서브프로세스로(`kimodo_run.py`, 오프라인 · 텍스트 인코더 CPU) → BVH(SOMA77 표준 T 포즈 · cm · 루트 트랙) → `blender` 변환 → retarget(SOMA 수동 체인 27개). 서브프로세스 공통 기반 `subprocess_step.py`(blender 와 같이) | §3.4 · §4 · §14 |
| 정책 | `paths.blender_executable` | + `paths.kimodo_python` · `paths.kimodo_hf_cache` | §6 |
| 요청 | 생성 필드 없음 | `prompt`(모델이 읽는 영어 문장) · `generation{seed, samples, steps, postprocess, pick, constraints[root_path · keep_pose · kimodo_raw]}` · `review.render` · `fix.ops`(사전 비어 있음) · `retarget.align_mode` · `retarget.body_clearance` | §9 |
| 라우터 | 생성 → import | 생성 결과가 BVH 면 `blender` 변환을 잇는다(예상 규약 고정 → 실행 때 측정). blender 가 없으면 `DEPENDS_ON_BLENDER`. Provider 가 아는 리타깃 기본값(SOMA 골반 · 체인 · 발)은 요청이 비운 것만 채운다 | §5 |
| 리타깃 정렬 (엔진 함정) | `match_existing` = FK op 만 정확 매핑 | 리타깃 포즈 자동 정렬은 '매핑된 체인'을 **꺼진 op 까지 모든 op** 의 매핑으로 판정한다 → 꺼진 Run IK Rig op 의 퍼지 매핑이 소스에 없는 손가락을 다리 · 팔 방향으로 꺾었다(SOMA 검지 MCP 120°). `match_existing` 은 모든 op 를 정확 매핑 | §2.3 · §10 |
| 리타깃 정렬 (`per_bone`) | 엔진 자동 정렬만 | `create_ik_retargeter align_mode=per_bone`(anim_gen 기본): 뼈 수 같은 체인 FK 1:1 + 본 대 본 · 체인 끝 정렬, 축 체인(척추 · 목 · 머리) · 펠비스 = 대상 고유 자세, 머리 해부적 중립, 손가락은 메타카팔 상대 | §2.3 · §10 |
| 기준 포즈 FBX | 동작 FBX 하나 | Interchange 는 계층 깊이 ≥ 10 본이 있으면 바인드 포즈를 무효로 보고 첫 프레임으로 다시 바인드한다 → blender 가 기준 포즈 2프레임 FBX 를 따로 내고 임포트는 2단(스켈레톤 ← 기준 포즈 FBX, 동작 ← 그 스켈레톤에 애니만) | §2.3 · §10 |
| 손가락 · 관통 | 검증 없음 | `create_ik_rig finger_chain_suggestion`(이름 없는 위상 · 좌표 제안) · `validate_animation fingers`(미매핑 = 기준 포즈 · 굽힘 방향 · 끝 순서) · `body_clearance`(대상 메시 반경 지도) · `retarget_animations body_clearance resolve`(관통 프레임만 위팔 최소 회전) | §10 · §13 |
| 시각 확인 | 사람이 Persona/PIE (캡처는 Phase 8) | + `review.render` — 변환된 **소스 골격**의 프레임 PNG · 비교 시트(Blender Workbench). Vesper 캡처는 Phase 8 그대로 | §13 |

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
| GPU · 메모리 | RTX 3080 Ti 12GB · RAM 64 GB · i7-12700KF |
| MCP Python | `Tools/mcp/.venv` Python 3.13.1, `mcp` 2.x |
| 로컬 AI (개정 8) | Kimodo — 저장소 밖 `D:\AnimGenModels\Kimodo\`. 시스템 Python 3.13 venv(`Tools/mcp/.venv` 와 별개) · 코드 `nv-tlabs/kimodo` `e1c219c` · torch 2.14.1+cu130 · NVIDIA 잠금 버전 72개(numpy 만 2.3.5 — 3.13 휠) · C++ 확장 `motion_correction`(발 미끄러짐 후처리) VS2022 빌드. 오프라인 Hugging Face 캐시 `hf_cache` 17 GB(체크포인트 `nvidia/Kimodo-SOMA-RP-v1.2` · LLM2Vec 어댑터 2개 · `meta-llama/Meta-Llama-3-8B-Instruct` — 사용자가 직접 약관 동의 후 받음, 파일 SHA-256 대조). 텍스트 인코더 CPU(`TEXT_ENCODER_DEVICE=cpu`) → 생성 1건(프로세스 하나 = torch 임포트 + 모델 · 인코더 적재 + 생성) 에디터를 띄운 채 51 ~ 88초(그중 확산 생성 8.5 ~ 13초, 첫 실행은 torch 임포트가 47초) · RAM 약 15 GB · VRAM < 3 GB. 실행에 HF 토큰을 쓰지 않는다(`HF_HUB_OFFLINE`) |

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
| 리타깃 포즈 자동 정렬의 '매핑된 체인' (개정 8) | `FIKRetargetProcessor::IsBoneInAMappedChain` · `GetFirstChainMappedToChain` · Run IK Rig op `AutoMapChains(Fuzzy)` · `FRetargetChainMapping::AutoMapChains` | `Plugins/Animation/IKRig/Source/IKRig/Private/Retargeter/IKRetargetProcessor.cpp:1496, 1675` · `…/RetargetOps/RunIKRigOp.cpp:150` · `…/Retargeter/IKRetargetChainMapping.cpp:222-242` | 자동 정렬이 본을 '매핑된 체인'으로 보는지는 스택의 **모든 op**(꺼진 op 포함) 매핑에서 첫 상대를 찾는다. 엔진은 Run IK Rig op 에 퍼지 매핑(점수 = 1 − 편집거리 / 두 이름 길이 합, 0.2 초과)을 깔아 두므로, FK op 만 정확 매핑하면 꺼진 op 의 퍼지 짝(LeftIndex · LeftRing → LeftLeg, LeftThumb · LeftPinky → LeftArm)으로 소스에 없는 손가락의 리타깃 포즈를 돌린다. FK op 는 그 손가락을 움직이지 않으니 꺾인 포즈가 모든 프레임에 남는다(SOMA 검지 MCP 120° · CMU 63.8°, 가운데 손가락만 멀쩡 — 퍼지 짝이 뼈 1개 쇄골이라 접선 0). → `match_existing` 은 `AutoMapChains(Exact, bForceRemap=true)` 를 모든 op 에 |
| FK 체인 Interpolated 회전 (개정 8) | `FIKRetargetFKChainsOp` `EFKChainRotationMode::Interpolated` · `GetTransformAtChainParam` | `…/RetargetOps/FKChainsOp.cpp:283-291` | 대상 본의 체인 param(길이 비율) 위치에서 **소스 체인을 보간한 회전**을 쓴다 → 관절 비율이 다르면(팔꿈치 param Vesper 0.512 · CMU 0.589) 위팔 · 아래팔 회전이 섞여 굽힘이 0.87배로 전달된다(굽힘 평면 회전 0.00° — 롤 문제가 아님). 뼈 수가 같은 체인은 1:1(`OneToOne`)이 맞다 |
| 리타깃 포즈 자동 생성기 (개정 8) | `FRetargetAutoPoseGenerator::AlignPelvisBone` · 체인 접선 | `Plugins/Animation/IKRig/Source/IKRigEditor/Private/RetargetEditor/IKRetargeterPoseGenerator.cpp:107, 249, 386` | 같은 param 의 접선(유한 차분)끼리 맞춘다 — param 1 근처(뼈 1개 말단 · 머리)는 접선을 못 만들어 건너뛰고, 펠비스는 소스 척추 방향으로, 척추는 소스 곡선 접선으로 돌린다 → 대상 몸통이 소스 기준 포즈 모양(숙임 · 목 기울기)을 물려받아 모든 프레임에 붙는다 |
| 바인드 포즈 무효 → 첫 프레임 재바인드 (개정 8) | `UInterchangeSkeletalMeshFactory` `bUseTimeZeroAsBindPose` | `Plugins/Interchange/Runtime/Source/Import/Private/Mesh/InterchangeSkeletalMeshFactory.cpp:792-808` | FBX SDK 가 바인드 포즈를 무효로 보면 "invalid bind poses … rebind using the time zero pose" — 스켈레톤 기준 포즈가 **애니 첫 프레임**이 된다. Blender 가 쓴 FBX 는 행렬이 일관인데도 계층 깊이 ≥ 10 본(SOMA 손가락 둘째 마디 아래)이 있으면 정밀도 판정(허용 0.0001 cm)으로 무효가 된다(이분 탐색 실측, CMU 깊이 ≤ 9 는 유효). 미터 단위 FBX 는 유효하지만 루트 본 스케일 100 이 남아 못 쓴다 → 기준 포즈 2프레임 FBX 로 스켈레톤을 만들고 동작은 그 스켈레톤에 애니만 임포트(§10) |
| 메시 기준 포즈 ≠ 스켈레톤 기준 포즈 (개정 8) | `USkeletalMesh::GetRefSkeleton` · `USkeleton::GetReferenceSkeleton` | — | 메시 46개가 공유하는 Vesper 스켈레톤의 기준 포즈는 `SK_StreetDemon_F_01` 과 손가락 로컬 회전이 최대 14.13°(`index_metacarpal`) 다르다 — 리타기터 · 렌더는 **메시** 기준 포즈를 쓰므로 미매핑 손가락 비교도 대상 메시 기준이어야 한다(스켈레톤 기준이면 고친 결과도 30본 오탐) |
| 애셋 이동 (개정 10 — 승격) | `IAssetTools::RenameAssets(TArray<FAssetRenameData>)` · `FixupReferencers` | `Source/Developer/AssetTools/Private/AssetRenameManager.cpp:138-152, 386-554, 708-807, 921-1090, 1734-2024` · `Public/IAssetTools.h:121-151, 470, 649` | 대화상자 없는 경로(`bAutoCheckout` · `bWithDialog=false`), 레지스트리 로딩 중이면 false. 네이티브 클래스 CDO 가 하드 · 소프트로 가리키면 OkCancel 모달(기본 Cancel → 중단, 소프트면 리디렉터 표시도). 리디렉터는 참조자가 맵(:1032) · 못 읽음(:1068) · 컬렉션 · 읽기 전용 · SCC 비로컬(:994)일 때만. `PerformAssetRename` 이 **이미 더티인 패키지의 소프트 참조까지 고치고** 새 패키지 · 참조 패키지 · 리디렉터를 `PromptForCheckoutAndSave(bPromptToSave=false)` 로 **자동 저장**, 리디렉터가 없으면 옛 패키지를 지운다(:2014-2023 — 아직 참조되면 파일이 남을 수 있다). 실측: BS 1개 0.6초 · 저장 = 새 패키지(+ 참조자) · 옛 파일 없음 · 리디렉터 0. `UEditorAssetSubsystem::RenameAsset` 도 같은 경로 |
| 모달 기본값 (개정 10) | `FMessageDialog::Open` | `Source/Runtime/Core/Private/Misc/MessageDialog.cpp:172` | `FApp::IsUnattended() \|\| GIsRunningUnattendedScript` 면 DefaultValue 반환 → `promote_animation` 은 rename 호출 동안만 `TGuardValue(GIsRunningUnattendedScript, true)` |
| additive 유효 (개정 10) | `UAnimSequence::IsValidAdditive` | `Source/Runtime/Engine/Private/Animation/AnimSequence.cpp:2615-2640` | `RefPose` · `LocalAnimFrame` 은 기준 시퀀스 없이 유효, `AnimScaled` · `AnimFrame` 은 `RefPoseSeq` 가 있어야 — 요청 `package.additive` 기본 `LocalAnimFrame 0`, `AnimFrame` 이면 `ref_pose_sequence`(`$asset` = 자기 자신) 필수 |
| 시퀀스 내용 해시 (개정 10) | `IAnimationDataModel::GenerateGuid()` | `Source/Runtime/Engine/Classes/Animation/AnimData/IAnimationDataModel.h:380-385` | 경로와 무관한 원시 데이터 GUID — 승격 전후 같으면 같은 내용 |
| 대상 메시 캡처 (개정 12) | `FPreviewScene` · `USceneCaptureComponent2D::CaptureScene` · `UTextureRenderTarget2D` · `FTextureRenderTargetResource::ReadPixels` · `FImageUtils::{SaveImageByExtension, LoadImage, ImageResize}` | `Source/Runtime/Engine/Private/PreviewScene.cpp:21-95` · `…/Components/SceneCaptureComponent.cpp:817-831` · `Source/Runtime/Renderer/Private/SceneCaptureRendering.cpp:511-535` · `Engine/Public/ImageUtils.h` | 프리뷰 월드는 트랜지언트 패키지(애셋 · 더티 없음), 기본 방향광 + 스카이라이트(썸네일 환경 큐브맵 `UThumbnailManager::AmbientCubemap`), 메시 텍스처 상주. `CaptureScene()` 은 `SendAllEndOfFrameUpdates` 뒤 즉시 렌더(뷰포트 · 창 불필요 — `-unattended` 실측). 정사영 투영 = `OrthoWidth` · 높이는 렌더 타깃 비율 · near 0. `FImage` 는 ImageCore 모듈(링크에 명시 의존 필요 — 실측) |
| 캡처 포즈 · 쇼 플래그 (개정 12) | `USkeletalMeshComponent::SetPosition` · `RefreshBoneTransforms(nullptr)` · `RecreateRenderState_Concurrent` · `USceneCaptureComponent::SetShowFlagSettings` | `Source/Editor/UnrealEd/Private/ThumbnailHelpers.cpp:645-709` · `…/Components/SceneCaptureComponent.cpp:264-288, 431-447` | 포즈 = 썸네일 장면과 같은 순서(단일 노드 `SetPosition` → 동기 평가 → **렌더 상태 재생성** — 틱 없는 프리뷰 월드에서 동적 데이터만 표시하면 스키닝이 첫 포즈에 머문다, 실측). `ShowFlags` 를 직접 바꾸면 등록이 `ShowFlagSettings` 로 되돌린다 → 설정 배열로 끈다 |
| 골반 이동 모델 (개정 13) | `FIKRetargetPelvisMotionOp::DecodePose` · `InitializeTarget` | `…/RetargetOps/PelvisMotionOp.cpp:205-221, 297-325` | 대상 골반 위치 = 소스 골반 **절대** 위치 × (대상 / 소스 골반 초기 높이)(초기값 기준 상대 아님), 회전 = (소스 현재 × 소스 초기⁻¹) × 대상 초기. 바닥 제약 가중치 0(기본)이면 그대로 → 다리 보정의 대상 모델(대상 엉덩 = s · P_s + Δ · 대상 엉덩 오프셋, 다리 = 소스 뼈 방향 · 대상 길이 — FK 체인 회전 복사와 per_bone 정렬). 실측: 모델이 예측한 Vesper 두 발 디딘 발 좌우 비 · 접지 미끄러짐이 리타깃 결과와 ±0.03 · ±1 cm/s 안(§14 '8-3') |
| 캡처 무기 부착 (개정 14 — 8-4a) | `USceneComponent::AttachToComponent(KeepRelativeTransform, 소켓)` · `USkeletalMeshComponent::FinalizeAnimationUpdate` | `Source/Runtime/Engine/Private/PhysicsEngine/PhysAnim.cpp:468-485` · 게임 배치(프로젝트) `Source/AstralBreak/Equipment/AstralEquipmentInstance.cpp:110` · `AstralWeaponActor.cpp:74` | 소켓에 붙은 자식은 `bHasSocketAttachments` 면 애니 갱신 끝(`FinalizeAnimationUpdate` → `UpdateChildTransforms(OnlyUpdateIfUsingSocket)`)에서 따라온다 → `capture_animation attachments` 는 부착 컴포넌트를 소켓에 붙이고 포즈마다 렌더 상태를 다시 만든다. 게임의 무기 메시 = `MeshInfo.AttachOffset` · `ActorsToSpawn[0].AttachTransform` · 소켓 상대 · 손 본(UE 곱 순서 — 변환 2단이라 캡처 `offset` 은 둘을 합성한 한 변환) |
| 에디터 시작 스크립트 (개정 14 — 8-4a) | `-ExecutePythonScript=<파일>` · `unreal.EditorPythonScripting.set_keep_python_script_alive` | `Plugins/Experimental/PythonScriptPlugin/Source/PythonScriptPlugin/Private/EditorUtilities/EditorPythonExecuter.cpp:71-77` | 원격 실행(UDP)이 안 되는 환경에서 DA 값을 읽은 경로. 스크립트가 끝나면 `GetKeepPythonScriptAlive()` 가 거짓일 때 **에디터를 닫는다** → 끝에서 keep-alive 를 켜야 같은 기동으로 브리지 측정을 잇는다(`Tools/mcp/e0_weapon_attach.py` — 읽기 전용, 더티 전후 0) |
| 몸 모델 내보내기 (개정 14 — 8-4a) | `FBase64::Encode` | `Source/Runtime/Core/Public/Misc/Base64.h` | `body_clearance model` 의 반경 지도(int16 0.01 cm, −32768 = 빈 칸) · 축 · 포즈(float32)는 base64 — 121 프레임 · 측정 점 전부 JSON 최대 3.0 MB(점을 줄이면 Python 재현 ≠ 측정이라 줄이지 않는다) |
| IKRig 플러그인 | `EnabledByDefault: true` | `Plugins/Animation/IKRig/IKRig.uplugin` | 플러그인 의존 선언만 추가하면 된다 |

### 2.4 외부 Provider와 라이선스

| 대상 | 확인 결과 | 결정 |
| :--- | :--- | :--- |
| HY-Motion 1.0 | "Tencent HY-MOTION 1.0 Community License". Territory = 전 세계에서 **EU · UK · 한국 제외**. 월간 사용자 100만 초과 시 별도 라이선스 | 별도 적법 라이선스 없이 설치·활성화 금지 |
| 공개 Text-to-Motion 모델 (MDM · MoMask · T2M-GPT · MotionGPT · MLD · MotionLCM · MotionStreamer · MoMask++) | 개정 8 — **확인**([조사](LocalModelSurvey.md) §2 · §3.1): 코드는 대개 MIT/Apache 지만 가중치 라이선스 미기재, 학습 데이터 HumanML3D ← AMASS 가 "train methods/algorithms/neural networks/etc. for commercial use of any kind" 를 금지(SMPL 도 같은 조항, MotionLCM 은 코드부터 비상업) → 상업 이용 부적법. 개인 포트폴리오가 AMASS 허용 범위(비상업 연구 · 교육 · 예술)에 드는지, 가중치 사용자에게 미치는지는 원문이 정하지 않는다(조사 §4 H-1 ~ H-3). 대부분 관절 위치만 내고 손가락 없음 · 20 fps | 채택하지 않음 |
| **NVIDIA Kimodo-SOMA-RP-v1.2** (개정 8) | 코드 Apache-2.0 · 가중치 NVIDIA Open Model License("commercially usable" · 전 세계 · 출력 소유 주장 없음 · 모델 재배포 시 고지) · 학습 데이터 Bones Rigplay(700 h 독점 모캡, NVIDIA 라이선스) · 텍스트 인코더 Meta Llama 3 8B Instruct(Llama 3 Community License — HF 게이트, 약관 동의는 사용자 본인) + LLM2Vec 어댑터(MIT). 같은 저장소의 SMPLX-RP 는 NVIDIA R&D 라이선스라 제외, `*-SEED` 는 BONES-SEED 학습 계약이 공개되지 않아 제외. 출력 30 fps · 최대 10초 · `--bvh` SOMA77 cm. ARDY(같은 데이터 · 라이선스)는 BVH 가 없어 2순위 | **채택**(2026-10-24, 사용자) → `local_ai`(§4 · §14 Phase 5). 남은 해석: "Built with Meta Llama 3" 표시가 생성 애셋만 쓰는 게임에도 필요한지(조사 §4 K-1) |
| Meshy Text-to-Motion | 개정 9 — **확인**(2026-10-25, 부록 A): `POST https://api.meshy.ai/openapi/v1/text-to-motion` `{prompt ≤ 400자, duration 2 ~ 10초 · 0.5초 단위(필수), mode prime(FBX · 10 크레딧, 기본) \| swift(BVH · 3 크레딧)}` → 202 `{result: task_id}`, `GET …/:id`(PENDING · IN_PROGRESS · SUCCEEDED · FAILED, `consumed_credits` — 실패 0 = 환불, `expires_at` — 결과 3일 보존, `motion_url` 은 읽을 때마다 재서명), SSE · 목록 · DELETE(PENDING 만 환불) — 취소 없음. 잔액 `GET /openapi/v1/balance`(무료). 초당 20 요청 · 동시 태스크 Pro 10, 429 = `Retry-After`(초당) / `NoMorePendingTasks`(동시). 멱등 키 헤더 없음. API 는 유료 요금제 필요(Free 402), 테스트 모드 키 폐지(2026-09-16). **출력 리그 · FBX 안 메시 여부는 문서에 없다.** 돈 값은 요금제마다 다르다(요금제 페이지는 KRW — Pro ₩28,869/월 1,000 크레딧 · 크레딧 팩 가격 비공개). 약관(2026-09-19): 유료 요금제 출력 소유 · 비 Enterprise 입력 · 출력을 Meshy 학습에 쓸 수 있음(§2.9) · Meshy 와 경쟁하는 AI 학습에 출력 사용 금지 · 지역 제한 없음. 보내는 것은 프롬프트 · 길이 · 모드뿐(캐릭터 데이터 없음) | **채택**(2026-10-25, 사용자 — 약관 수용 · `license: ok`) → `external.meshy`(§4 · §14 Phase 6). 금액 = 크레딧 × 정책 `usd_per_credit`(사용자 요금제) |
| DeepMotion SayMotion | REST API 있음. 검증 파트너 한정, base URL은 요청해야 받음 | 보류 |
| Tripo3D (개정 9) | 2026-10-25 확인([developers.tripo3d.com](https://developers.tripo3d.com/en/models/animation)): **텍스트 → 모션 생성 없음.** 애니메이션 API 는 리깅된 모델(보통 Tripo Auto Rig, 25 크레딧)에 프리셋(100개 이상)을 적용하는 retarget(10 크레딧/개). 무료 API 크레딧 양은 공식 문서로 확인 안 됨. 본업은 텍스트 · 이미지 → 3D 메시(공식 CLI 있음) | 모션 Provider 로는 채택 안 함. 메시 생성은 **별도 트랙**(§14 끝) |

---

## 3. 통합 원칙

### 3.1 배치

```text
Claude Code — 자연어 해석·분해·계획 (에이전트 자신)
  │ MCP
  ├─▶ anim-graph-mcp  (기존, 얇은 프록시 — Tool 하나 = 라우트 하나)
  │       └─ HTTP ─▶ AnimGraphMcpEditor (C++, 게임 스레드)
  │                   ├─ 기존: AnimBP · 몽타주 · BlendSpace · 스켈레톤 슬롯·재할당
  │                   └─ 신규: 스켈레톤 조회 · 임포트 · IK Rig · 리타기터 · 리타깃 · 키 편집 · 검증 · 승격(Phase 7) · 대상 메시 캡처(Phase 8-2) — 기존 쓰기 Tool 6개는 옵트인 generation_guard
  │
  └─▶ anim-gen-mcp    (신규, Phase 3 — Tools/mcp/anim_gen/)
          ├─ 정책 · 비용 장부 · 승인 · Provider 레지스트리 · 라우터 · 폴백 · Job 저장소
          ├─ Provider: existing_motion · direct_key · blender · local_ai · external.meshy · 파이프 retarget · package · anim_bp(Phase 7)
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
   - **옵트인 생성 가드 (개정 10):** "기존 Tool 동작은 바꾸지 않는다"의 범위는 **기본값**이다. 기존 쓰기 Tool 6개(`create_anim_montage` · `set_montage_sections` · `create_blendspace` · `set_sequence_additive` · `duplicate_animation_blueprint` · `apply_graph_operations`)는 `generation_guard: true` 일 때만 생성 Tool 과 같은 가드(허용 목록 · 덮어쓰기 거부 · 전역 더티 비교 · 검사 뒤 저장, 결과 `guard{newly_dirty[]}`)를 받는다. 기본 false 는 지금까지와 같다(`build_hero_combat.py` 등 영향 없음). anim_gen 은 포장 · 연결 단계의 모든 쓰기에 켠다 — 규칙은 C++ `AnimMcpGeneration::FWriteGuard` 한 곳에만 있다.
   - **승격 경로 (개정 10):** `+PromotionPaths=/Game/Animation/Hero/` — `promote_animation` 이 후보를 옮길 수 있는 유일한 기준. 생성 경로와 겹치는 항목 · 마운트 루트는 경고 후 무시(`get_editor_status.generation.promotion_paths`).
   - **캡처 경로 (개정 12):** `+CaptureOutputRoots=Tools/mcp/results/capture/`(디스크, 프로젝트 기준 상대 또는 절대) — `capture_animation` 이 PNG 를 쓰는 유일한 기준(루트 아래 **새 · 빈 하위 폴더**만, 루트 자체는 거부). 비면 캡처를 거부한다. Saved 밖에 둔 이유: 세션 권한 `Read(./Saved/**)` 가 Read 와 SendUserFile 을 모두 막아(브리지 토큰 보호 — 우회하지 않는다) 결과를 채팅에 보일 수 없다(`get_editor_status.generation.capture_output_roots`).
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
- 오류 코드는 기존 체계(HTTP 상태 + 코드)에 추가한다. 예: `IMPORT_FAILED` · `IKRIG_AUTO_FAILED` · `RETARGET_FAILED` · `VALIDATION_FAILED` · `OUTPUT_PATH_NOT_ALLOWED` · `UNEXPECTED_DIRTY` · `PROVIDER_UNAVAILABLE` · `APPROVAL_REQUIRED` · `BUDGET_EXCEEDED` · `COST_UNKNOWN` · `LICENSE_RESTRICTED` · `PROMOTE_FAILED`(개정 10 — 플러그인, HTTP 400) · `INTEGRATION_FAILED`(개정 10 — anim_gen 포장 · 연결) · `CAPTURE_FAILED`(개정 12 — 플러그인 캡처의 렌더 · 읽기 · 쓰기, HTTP 400). 세부 사유는 기존 Tool처럼 `error.details.reason`에 둔다.
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
| `create_animation_montage` | 기존 `create_anim_montage`(+ `set_montage_sections`) — 개정 10: 옵트인 `generation_guard`, anim_gen `package.montage` | 7 |
| `create_animation_blendspace` | 기존 `create_blendspace` — 개정 10: 옵트인 `generation_guard`, anim_gen `package.blendspace` | 7 |
| (AnimBP 연결) | 기존 `duplicate_animation_blueprint` · `apply_graph_operations` · `run_automation_tests` · `run_anim_scenario` 조합(개정 10 — 복제본에만, `generation_guard`) | 7 |
| `promote_animation` | 신규 (C++, 개정 10) — 후보 → 정식 경로 rename, `dry_run` · `confirm` · `allow_referencers` | 7 |
| `list_motion_providers` · `get/set_generation_policy` · `plan_motion_generation` · `estimate_generation_cost` · `generate_motion` · `get_generation_status` · `cancel_generation` | anim-gen-mcp + 신규 `approve_generation` | 3 |
| `apply_motion_constraints` | 보류 | 8 |
| `preview_generated_animation` | 신규 `capture_animation` (C++, 개정 12) — 대상 메시 정사영 캡처(시트 · 비교 시트 · 연속 프레임), anim_gen `review.capture` 가 부른다 | 8-2 |
| `create_animation_from_prompt` | **폐기.** 자연어 분해는 Claude Code가 하고 `plan_motion_generation`에 구조화된 요청을 넘긴다 | — |

### 3.4 Job

- **에디터 작업:** 기본은 동기다. 일괄 리타깃은 엔진이 한 번의 동기 호출로 처리하므로, 요청당 애셋 수 상한(입력 + 동반 참조 **50** — Phase 1 실측: 20개·1,317프레임을 리타깃·검증·저장까지 3.0초, 애셋당 300프레임이어도 50개 약 35초) + 180초 타임아웃으로 한다. 상한을 넘는 일괄 처리가 실제로 필요해지면 `AnimMcpAutomationRunner`의 `job_id` + poll 패턴으로 애셋 단위 틱 분할을 추가한다.
- **Provider 작업**(외부 API · Blender · 로컬 AI)은 `anim_gen`의 Job 저장소가 맡는다.
  - 상태: `QUEUED` · `RUNNING` · `WAITING_FOR_APPROVAL` · `SUCCEEDED` · `FAILED` · `CANCELLED`
  - 필드: id, plan_id, provider, 현재 단계, 비용(추정/실제), 결과 파일, 오류 코드, attempt · retry_count, fallback_history, approval_id, idempotency_key, events[](상태 전이 기록), diagnostics[]
  - diagnostics(개정 7 보강 2): `anim_gen` 자신의 진단과 함께 **단계 안 에디터 Tool 이 봉투로 돌려준 진단**(`LENGTH_SNAPPED` · `UNMAPPED_TARGET_CHAINS` 등)을 항목마다 `tool` · `step` 을 붙여 남긴다. 단계가 실패해도 남긴다. 실행기가 단계마다 `EditorClient.collect()`(스레드별)로 감싸 모으므로 Provider 는 따로 넘기지 않는다. 계획 시점 호출의 진단은 계획 `diagnostics` 쪽이다
  - 전이: `QUEUED → RUNNING | WAITING_FOR_APPROVAL | CANCELLED`, `RUNNING → SUCCEEDED | FAILED | WAITING_FOR_APPROVAL | CANCELLED`, `WAITING_FOR_APPROVAL → QUEUED(승인) | CANCELLED`. 종료 3종(`SUCCEEDED` · `FAILED` · `CANCELLED`) 뒤 전이는 없다.
  - 실행 모델(Phase 3): 에디터 Provider(`existing_motion` · `direct_key` · `retarget`)는 `generate_motion` 호출 안에서 동기로 끝난다. 비동기 Provider(외부 · Blender · 로컬 AI)는 백그라운드 스레드 없이 `get_generation_status`가 poll 할 때 진행한다.
  - 로컬 서브프로세스(개정 7 — `blender`, 개정 8 — `local_ai`): `generate_motion`이 프로세스를 띄우고 `RUNNING`을 돌려준다. poll 이 끝남(report 파일)을 보면 같은 호출 안에서 다음 단계를 잇는다 — 다음도 서브프로세스면(Kimodo → Blender) 그것을 띄우고 다시 `RUNNING`, 에디터 단계면 import → retarget → 검증까지 동기로. 자식은 stdin을 막고 출력을 로그 파일로 보낸다(MCP stdio 보호), 키·토큰 이름의 환경 변수는 넘기지 않는다. 기한(`execution.subprocess_timeout_seconds`, 단계마다)을 넘기면 끝내고 `GENERATION_FAILED`(`TIMEOUT`). 서버가 다시 뜨면 프로세스 핸들이 없어 report 파일로만 판정하고, 기한까지 report가 없으면 멈추지 못한 채 `TIMEOUT`으로 적는다. 공통 부분은 `providers/subprocess_step.py`(`SubprocessProvider` — 띄우기 · report 대기 · 기한 · 종료 · 로그 꼬리)이고 Provider 는 명령 · 인자와 report 해석만 정한다.
  - AnimBP 시나리오(개정 10 — `anim_bp_test`): 복제 · 적용 · 컴파일 · 스모크는 동기, `run_anim_scenario` 는 에디터 잡(PIE)이라 `generate_motion` 이 `RUNNING` 을 돌려주고 `get_generation_status` 의 poll 이 `poll_automation_tests` 로 잇는다(무료 비동기 단계 — 장부 없음). 기다리기 전에 만든 복제본은 Job `intermediate_assets` 에 바로 남는다(취소 · 실패해도). 취소는 PIE 잡을 멈추지 않는다(결과 무시 — 러너가 기한에 PIE 를 닫는다).
  - 프레임 렌더 비교(개정 8): `blender` 변환 단계가 `review.render` 결과(`values.review` — 프레임 PNG · 시트 · 배치 · 카메라)를 내면 Job 최상위 `review` 에도 남긴다. 뒤 단계가 실패하거나 폴백해도 지우지 않는다(무엇이 변환됐는지 보는 근거).
  - 대상 메시 캡처(개정 12): capture 단계 결과(`values.review_capture`)는 Job `review.capture{ok, shows: target_mesh, mesh, facing, dir, sheet, compare_sheet, rows_from, animation{path, frames, fps, size, bytes}, frames[], sequence, camera, layout, bounds, cells_touching_edge, seconds}` — `review` 맨 위(소스 골격 렌더)는 그대로 둔다. 실패면 `{ok: false, reason, message, editor_error?}`.
  - 같은 계획으로 `generate_motion`을 다시 부르면 기존 Job을 돌려준다. 실패·취소된 Job은 `retry=true`일 때만 새 Job을 만든다.
  - 저장 위치: `Saved/AnimGen/{policy.json, plans/, jobs/, approvals/, ledger.jsonl}`(`ANIM_GEN_STATE_DIR`로 바꿀 수 있다 — 테스트 격리용). 서버 프로세스 하나를 전제한다.
- **취소:** 취소가 Provider 실행의 즉시 중단을 뜻하지 않는다. 외부 작업은 "결과 무시"로 처리하고, 이미 발생한 비용은 장부에 남긴다. 로컬 서브프로세스(`blender` · `local_ai`)는 실제로 종료하고 Job에 `cancel_effect{stopped, pid}`를 남긴다(개정 7 · 8). `external.meshy`(개정 9)는 Meshy 에 취소가 없어 아무것도 보내지 않는다(PENDING 태스크 DELETE 는 환불되지만 처리 중앙값 15초라 쓰지 않는다) — 예약은 남는다.
- **외부 비동기 단계 (개정 9 — `external.meshy`):** 유료 단계는 실행기가 승인 · 장부 예약(`(plan_id, attempt)`)을 마친 뒤 Provider `run` 을 부르고, `run` 은 잔액 확인 → 제출 → `pending{task_id, deadline, usd_per_credit}` 를 돌려준다(장부 `submitted`). `get_generation_status` 의 poll 이 태스크를 읽어 끝났으면 결과를 받고 다음 단계(import · blender)를 같은 호출에서 잇는다 — 백그라운드 스레드 없음. poll 의 429 · 5xx · 연결 실패는 실패가 아니라 다음 poll(Meshy 안내), `Retry-After` 전에는 요청하지 않는다. 기한(정책 `external.meshy.timeout_seconds`, 기본 3600 — Meshy 권장 "60분은 기다릴 것")을 넘기면 `GENERATION_FAILED TIMEOUT`(예약 유지 — 끝날 수도 있다). poll 단계가 실패로 끝나면 Provider 가 알려 준 과금을 장부에 반영한다: 환불(`charged: false`, 실패 태스크 `consumed_credits` 0) → `release`, 실제 크레딧 → `charge`, 모르면 예약 유지.

---

## 4. Provider

| Provider | 하는 일 | Phase | 기본 상태 |
| :--- | :--- | :---: | :--- |
| `retarget` (파이프) | 공통 처리 계층 — 모든 Provider 결과가 지난다 | 1 | 활성 |
| `package` (파이프, 개정 10) | 검증 뒤 포장 — additive · 몽타주 · BlendSpace (요청 `package`, 모든 쓰기 `generation_guard`) | 7 | 활성 |
| `anim_bp` (파이프, 개정 10) | AnimBP 복제본 연결 · 검증 + 운영 AnimBP 미리보기 · 적용 페이로드 (요청 `integrate_anim_bp` 일 때만) | 7 | 활성 |
| `review` (파이프, 개정 12) | 검증 뒤 최종 시퀀스를 대상 메시로 캡처(`capture_animation`) → 시트 · 비교 시트 · APNG (요청 `review.capture` 일 때만, 모든 경로) | 8 | 활성 (ini `CaptureOutputRoots` 가 있을 때 단계가 생긴다) |
| `existing_motion` | 메타데이터 인덱스로 검색 → 리타깃 → 편집 | 2 | 활성 (주 경로) |
| `direct_key` | `IAnimationDataController`로 키 작성: 리타임 · 트림 · 미러 · 본 오프셋 · 루트 Yaw · 포즈 유지 · 구간 연결. 개정 13: timing 단계(`fix.timing` — 휘두름 구간 탐지 → 리타임 · 트림, `anim_gen/timing.py`) | 2 · 8 | 활성 |
| `blender` | `motion_file`(BVH)을 headless(`blender -b --factory-startup -P anim_gen/blender/bvh_to_fbx.py`)로 FBX로 바꿔 retarget 파이프로 넘긴다 — 더미 스킨 메시 · 대상 정면 · 바닥 맞춤 · 범위 · fps. 개정 8: 기준 포즈 2프레임 FBX 도 낸다(§10), 생성 Provider 의 BVH 도 변환한다(§5), 같은 실행에서 프레임 렌더 비교(`review.render`)와 보정 op(`fix.ops` — 개정 13: smooth · stance_width · foot_lock, 다리는 리타깃된 다리의 모델 안에서 한 풀이). 개정 13: SOMA77 BVH 면 local_ai 리타깃 기본값. FBX 입력·아마추어 편집은 이후 | 4 · 5 · 8 | 실행 파일(정책 `paths.blender_executable`)이 있으면 활성 |
| `local_ai` | 개정 8 — NVIDIA Kimodo-SOMA-RP-v1.2(§2.4). `request.prompt`(+ `generation`) → Kimodo 전용 venv 서브프로세스 `<paths.kimodo_python> -I anim_gen/local_ai/kimodo_run.py args.json`(오프라인 · 텍스트 인코더 CPU) → 샘플별 NPZ + BVH(SOMA77 표준 T 포즈 · cm · 루트 트랙) → `blender` 변환 → retarget(SOMA 수동 체인 27개 · 골반 `Hips`). 제약 `root_path` · `keep_pose` · `kimodo_raw`. 개정 11: 요청 플래그 `two_hand_weapon_grip` · `foot_contact` → **2차 생성 제약**(같은 seed 1차 → `local_ai/refine.py` 가 양손 파지 목표 · 1차 접지 발 · 1차 루트 → 2차, Kimodo 일반 end-effector · root2d) · **seed 후보** `generation.candidates`(한 실행) · 후보 선별은 retarget 파이프 select 단계 | 5 · 8 | 정책 `paths.kimodo_python` · `kimodo_hf_cache` 가 있고 캐시에 필요한 4개 저장소가 있으면 활성(`license: ok`) |
| `external.meshy` | 개정 9 — Meshy Text-to-Motion(§2.4). `request.prompt` · 길이(0.5초 단위로 맞춤) · `generation.options["external.meshy"].mode` 로 보낼 본문을 계획에 고정 → 승인된 유료 단계에서 잔액 → 제출 → poll → 결과 다운로드(`<ImportSourceRoots[0]>/Meshy/<job_id>/A<n>/meshy_motion.{fbx,bvh}` + `task.json`) → prime(FBX) = `import_animation_file`, swift(BVH) = `blender` 변환 → retarget(리그 미문서 — 자동 IK Rig, 실패하면 본 계층으로 수동 체인). 금액 = 크레딧 × 정책 `external.meshy.usd_per_credit` | 6 | 키(`MESHY_API_KEY`)가 있으면 사용 가능(`license: ok`). 유료 — 정책 `paid_api_enabled` + 환율 + 승인이 있어야 실행 |
| `body_fit` (파이프, 개정 14 — 8-4b) | `control_rig` 비활성 자리를 대신한 **한 풀이**(Provider 수 10 그대로 — 이름 변경은 기대된 변화): 리타깃 · timing 뒤 대상 시퀀스(또는 같은 스켈레톤의 기존 Vesper 애니)를 C++ 몸 모델(`validate_animation body_clearance{parts all, hands, model}`)로 재고 → 순수 Python `anim_gen/body_fit.py` 가 관통(손 · 아래팔 ↔ 몸통 · 넓적다리 · 머리목 · 반대 손) · 양손 파지 keep · 위팔 '안 깊어짐' · 지시 목표(`fix.body.targets[]`)를 한 번에 풀어 → `apply_animation_edits bone_deltas` 로 새 애셋 → 같은 측정으로 C++ 실측(모델 예측과 Job 에 함께). 요청 `fix.body` 일 때만 | 8 | 활성 |

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
- **생성 BVH (개정 8 — `local_ai`):** 생성 Provider 의 출력이 BVH 면 사슬 = 생성 → 변환(`blender`) → import → `retarget` → [`direct_key`] → 검증(`chain` 은 `local_ai` · `blender` · `retarget`). 파일이 계획 때 없으므로 변환 단계는 생성 Provider 가 아는 규약(Kimodo: cm · 정면 +Y · 관절 78 · 30 fps · 프레임 수)을 `expected` 로 고정하고(위험 `CONVERT_RESOLVED_AT_RUN`), 실행 때 그 파일로 같은 규칙을 돌려 다르면 진단 `GENERATED_BVH_UNEXPECTED` 를 남기고 잰 값으로 변환한다. 리샘플은 생성 fps 와 요청 `frame_rate` 가 다를 때만. `blender` 를 쓸 수 없으면 그 후보를 `PROVIDER_UNAVAILABLE`(`DEPENDS_ON_BLENDER`)로 제외. 리타깃 단계의 소스 골반 · 체인 · 발은 요청이 비운 것만 Provider 기본값으로 채우고 계획에 `defaults_from{provider, keys}` 로 보인다(Kimodo = SOMA 골반 `Hips` · 체인 27개 · 발 — SOMA `LeftLeg` 는 넓적다리라 자동 캐릭터라이즈를 믿지 않는다). 생성 단계의 프롬프트 · 프레임 수 · seed(없으면 계획이 골라 고정 — `SEED_PINNED`) · 모델 커밋 · 제약 파일 SHA-256 도 계획에 고정한다.
- **2차 생성 · 후보 선별 (개정 11 — `local_ai`, Phase 8-1):** 플래그를 바꿨거나(`generation.refine.mode` auto + `two_hand_weapon_grip` · `foot_contact` 중 하나 이상) `generation.candidates` > 1 이면 사슬 = 생성(seed 후보 N × 차수 1 · 2) → 변환(`blender` — 후보 BVH N 개를 **Blender 한 실행**으로, 기준 포즈 FBX 는 첫 후보만) → import(기준 포즈 1번 + 동작 N 개를 그 스켈레톤에 애니만) → **select**(retarget 파이프 — IK Rig · RTG 1벌로 후보 전부를 `<work>/Candidates/Cand_*` 로 리타깃 → `validate_animation`(소스 대비 · `profile_positions` · `body_clearance` · `fingers`) 한 번 → 지표 · 점수로 하나) → retarget(그 RTG 로 고른 후보만 최종 이름 — 결정적이라 잰 값 = 최종) → [`direct_key`] → 검증. `chain` 은 그대로(`local_ai` · `blender` · `retarget`). 생성 단계 계획에 seed 목록 · 2차 규칙(플래그 · Kimodo 제약 · 프레임 · 목표 · 주 손 · 간격 근거) · 기한(정책 + 25초 × (확산 횟수 − 1))을 고정해 보이고(모델을 띄우지 않는다, 목표 값은 1차 결과로 실행 때 — 위험 `REFINE_RESOLVED_AT_RUN`), select 단계에 후보 · 지표 · 가중치 · 기준 · 측정 본(대상 템플릿 체인 — 손목 · 엉덩 관절 · 발목, 못 찾으면 기본 이름 + 진단 `SELECTION_BONES_DEFAULTED`)을 고정한다. 1후보 + 플래그면 select 는 선택 없이 측정만 한다. 플래그 · 후보가 없으면 사슬 · 계획이 개정 10 과 같다.
- **외부 생성 (개정 9 — `external.meshy`):** prime(FBX) = 생성 → `import_animation_file`(요청 `frame_rate` 로 굽기) → `retarget` → 검증, swift(BVH) = 생성 → `blender` 변환(단위 · 정면 · 관절 모름 → `expected{unit: auto}` 로 실행 때 잼, 대상 정면으로 돌림) → import(2단) → `retarget` → 검증(`blender` 가 없으면 `DEPENDS_ON_BLENDER`). 리그가 문서에 없어 리타깃 소스 체인을 채우지 않는다(자동 IK Rig — 위험 `SOURCE_RIG_UNVERIFIED`), prime 은 정면을 실행 때 잰다(`FACING_UNRESOLVED_AT_PLAN`). 후보의 위험 `PROMPT_SENT_EXTERNALLY` 와 생성 단계 `inputs.request_body`(보낼 본문 그대로)를 승인 전에 보여 준다. 비용 미확인(환율 없음) 후보는 `COST_UNKNOWN` 으로 제외된다.
- **포장 · AnimBP 연결 (개정 10 — Phase 7):** 어느 후보든 검증 뒤에 같은 단계가 붙는다(계획 안에서 한 번 계산). `package` 가 있으면 `package_additive`(`set_sequence_additive` — 새로 만든 시퀀스만; 재사용 애셋이면 `ADDITIVE_ON_REUSED` 로 막는다 · 계획 때 소스를 모르면 위험 `ADDITIVE_TARGET_RESOLVED_AT_RUN`) → `package_montage`(`create_anim_montage` → `set_montage_sections`, 슬롯이 대상 스켈레톤에 없으면 `SLOT_NOT_IN_SKELETON` — `add_skeleton_slot` 은 공유 스켈레톤 편집이라 별도 승인) → `package_blendspace`(`create_blendspace`, 고정 샘플 존재 · 스켈레톤), 출력 이름이 있으면 `ASSET_EXISTS`. `integrate_anim_bp` 가 참일 때만 `anim_bp_test`(→ `<work>/<ABP>_Test_<job>A<n>` 복제(노드 Guid 보존) → `apply_graph_operations(compile)` → 스모크 `AnimGraphMcp.Smoke.AnimBlueprint.<복제본>` (+ 몽타주면 `AnimMontage.<몽타주>`) → `run_anim_scenario`) · `anim_bp_prepare`(운영 AnimBP `get_anim_blueprint_info` → `preview_graph_operations` — 읽기만). 계획은 ABP 존재 · 스켈레톤(`SKELETON_MISMATCH`)을 보고 revision 을 고정하며, 자리표시 없는 op 는 운영 AnimBP 로 미리 본다(`PREVIEW_INVALID`), 자리표시가 있으면 위험 `ANIM_BP_OPS_RESOLVED_AT_RUN`. `integrate_anim_bp` 가 거짓이면 AnimBP 호출은 0 이다. 사슬 `chain` 끝에 `package` · `anim_bp` 가 붙는다.
- **변환 없는 경로 (개정 8):** `existing_motion` · `direct_key` 처럼 `blender` 변환이 없는 후보는 `fix.ops` 가 있으면 `UNSUPPORTED_FIX_OP` 로 막고(개정 13 문구: 소스 BVH 를 `motion_file` 로 · 시간 보정은 `fix.timing` · 대상 쪽 다리는 8-4), `review.render` 에는 한계 `REVIEW_NOT_RENDERED` 를 단다.
- **자동 보정 (개정 13 — Phase 8-3):** `fix.timing` 이면 리타깃 뒤(재사용 경로는 소스 확정 뒤) · `edits` 앞에 timing 단계(Provider `direct_key`): 측정(`validate_animation profile` — 측정 본 = select 와 같은 `selection_bones`) → `timing.plan`(휘두름 탐지 · op) → `apply_animation_edits` → 새 애셋 다시 측정. 소스가 계획 때 대상 스켈레톤 위에 있고 에디터가 있으면 계획이 op 를 구해 `preview_animation_edits` 까지(결과 길이 · 이음매), 아니면 위험 `TIMING_RESOLVED_AT_RUN`. timing 이 있으면 재사용이 아니다(새 애셋), 캡처는 비교 칸 없이 자기 행(편집과 같음), 앞 단계는 Work 이름. `fix.ops` 는 변환 단계 안(범위를 정한 뒤 · 기둥 메시 앞)에서 순서 고정 smooth → 다리 풀이(stance_width + foot_lock 한 번). 다리 본은 retarget 단계 입력(요청 `source_chains` 또는 Provider 기본값)의 LeftLeg/RightLeg 체인 시작 · `source_feet`(없으면 체인 끝의 부모) · 그 부모(무릎) — 기본값이 채워진 뒤 라우터가 정하고(파일이 계획 때 있으면), 대상 다리 치수 · 기준 포즈(골반 · 엉덩 관절)도 계획에 싣는다. 못 정하면 그 후보 `UNSUPPORTED_REQUEST FIX_LEGS_UNKNOWN`. 다리 op 가 있으면 최종 retarget 단계가 대상 다리를 잰다(Job `fix.target`). SOMA77 BVH(`soma.is_soma` — 리타깃 기본값이 가리키는 관절 이름 전부)를 `motion_file` 로 주면 변환 단계가 local_ai 와 같은 리타깃 기본값을 낸다(`defaults_from{provider: blender}`, 진단 `SOMA_BVH_DEFAULTS`).
- **한 풀이 (개정 14 — Phase 8-4b):** `fix.body` 면 모든 경로에서 timing 뒤 · `edits` 앞에 `body_fit` 단계(파이프 `body_fit`): 생성 = … → retarget → [timing] → **body_fit** → [edit] → 검증, 재사용 = resolve → [retarget] → [timing] → **body_fit** → [edit] → 검증 — 같은 스켈레톤 기존 애니도 새 애셋(재사용 아님, 앞 단계는 Work 이름). `mode: measure` 는 측정 · 계획만(애셋 없음 — 재사용 경로면 재사용 그대로). 리타깃 단계의 관통 보정은 기본 `resolve` → **`measure`** 로 바꾸고(보정 원천 하나 — 한계 `CLEARANCE_BY_BODY_FIT`, 계획 `retarget.inputs.body_clearance_from: body_fit`), 요청이 retarget `body_clearance: resolve` 를 명시하면 그대로 두되 위험 `CLEARANCE_DOUBLE_FIX`. 계획은 실행하지 않는다 — 소스가 계획 때 대상 스켈레톤 위에 있고 에디터가 있으면 측정해 '전' 수치 · 사건(초) · 지시 목표를 풀어 보이고(사건 → 프레임 구간 · ease 프레임 · 부위 → 본 · 자유도 · 몸 기준틀 오프셋 → 목표 위치 from/to), 생성 경로는 위험 `TARGETS_RESOLVED_AT_RUN`, 풀이는 항상 실행 때(`BODY_FIT_RESOLVED_AT_RUN`). 계획 때 아는 목표 오류는 후보를 막는다: 모르는 effector `BAD_REQUEST UNKNOWN_EFFECTOR` · 사건 없음 `EVENT_NOT_FOUND` · 클립 밖 `TARGET_OUT_OF_RANGE` · `target_mesh` 없음 `BODY_FIT_NO_MESH`(실행 때 알면 그 목표만 건너뛰고 한계 `TARGET_NOT_REACHED{reason}`).
- **대상 메시 캡처 (개정 12 — Phase 8-2):** `review.capture` 면 모든 후보의 검증 뒤(포장 · 연결 앞)에 `capture` 단계(파이프 `review`, Tool `capture_animation`). 계획은 대상 정면(대상 스켈레톤 기준 포즈 — retarget 의 정면 측정과 같은 원천), 메시(`review.capture.mesh` 또는 `target_mesh`), 행 규칙(`rows_from: render` = 변환 단계의 렌더 시각 · 비교 칸 / `request` = times · count), 셀 상수(blender `REVIEW_RENDER` — 소스 골격 렌더와 같은 값 하나), 출력 `<CaptureOutputRoots[0]>/<job_id>/A<n>/` 을 고정한다. 메시가 없거나 ini 캡처 루트가 비면 단계 없이 한계 `REVIEW_NOT_CAPTURED`(후보는 막지 않는다), 에디터가 없으면 정면 · 루트를 실행 때(위험 `CAPTURE_FACING_RESOLVED_AT_RUN` · `CAPTURE_ROOTS_UNCHECKED`), 변환 없는 경로에서 render 를 요청했거나 `edits` 로 시간축이 바뀌면 비교 칸 없이 자기 행(위험 `CAPTURE_ROWS_NOT_RENDER` · `CAPTURE_COMPARE_SKIPPED_EDITS`). 실행은 최종 시퀀스(재사용이면 그 애셋, 8-1 후보면 고른 후보 — 비교 칸도 그 후보의 소스 골격 프레임)를 캡처하고 연속 프레임을 APNG 로 잇는다. 사슬 `chain` 끝에 `review` 가 붙는다.
- **계획 단계 제외(`excluded[]`):** `PROVIDER_UNAVAILABLE`(`NOT_IMPLEMENTED` · `NOT_INSTALLED` · `DEPENDS_ON_BLENDER` 등) · `LICENSE_RESTRICTED` · `AUTHENTICATION_FAILED`(`API_KEY_MISSING`) · `APPROVAL_REQUIRED`(`POLICY_FREE_ONLY` · `PAID_API_DISABLED`) · `COST_UNKNOWN` · `UNSUPPORTED_REQUEST`(Capability 밖, 예: 최대 길이 초과 `DURATION_OVER_MAX`. 개정 8: `MISSING_INPUT`(프롬프트 없음) · `CONSTRAINT_OUT_OF_RANGE` · `DUPLICATE_FRAME` · `BAD_RAW_CONSTRAINTS` · `FILE_NOT_FOUND` · `POSTPROCESS_UNAVAILABLE` · `REVIEW_TIME_OUT_OF_RANGE` · `UNSUPPORTED_FIX_OP`). 제약 파일 · 레퍼런스 이미지가 `ImportSourceRoots` 밖이면 계획 전체가 `IMPORT_SOURCE_NOT_ALLOWED`.
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
    "blender_executable": "C:/Program Files/Blender Foundation/Blender 4.4/blender.exe",
    "kimodo_python": "D:/AnimGenModels/Kimodo/.venv/Scripts/python.exe",   // 개정 8 — Kimodo 전용 venv
    "kimodo_hf_cache": "D:/AnimGenModels/Kimodo/hf_cache"                    // 개정 8 — 오프라인 Hugging Face 캐시
  },
  "external": { "meshy": { "usd_per_credit": null, "timeout_seconds": 3600 } }  // 개정 9 — 크레딧당 USD(사용자 요금제) · 결과 대기 한도
}
```

- **외부 AI 금액 (개정 9 — `external.meshy`):** 크레딧 가격(prime 10 · swift 3)은 공식 문서지만 크레딧의 돈 값은 요금제(월 크레딧 · 구매 크레딧)마다 달라 문서로 확정할 수 없다. 그래서 추정액 = 공식 크레딧 × **사용자가 정한** `external.meshy.usd_per_credit`(0 초과 10 이하)이고, null(기본)이면 비용 미확인 — 계획에서 `COST_UNKNOWN` 으로 빠지고 승인도 실행도 없다. 승인 상한 · 정책 상한은 그대로 USD 다. 실제 금액 = 태스크의 `consumed_credits` × 제출 때 핸들에 고정한 같은 환율(장부 `charge{usd, credits}`) — 크레딧은 Provider 가 알려 준 실제 값이다. 제출 직전 잔액(무료 엔드포인트)이 모자라면 제출하지 않는다(`BUDGET_EXCEEDED INSUFFICIENT_CREDITS`, 예약 해제). 키 · 결과 서명 URL 은 정책 · 장부 · Job · 요청 로그 어디에도 남기지 않는다. 기본 URL 은 코드에 고정이다(정책으로 바꿀 수 없다 — 키가 다른 호스트로 가지 않게).

- **로컬 AI 경로 (개정 8):** `paths.kimodo_python` 이 파일이 아니거나 `paths.kimodo_hf_cache` 에 `nvidia/Kimodo-SOMA-RP-v1.2` · LLM2Vec 어댑터 2개 · `meta-llama/Meta-Llama-3-8B-Instruct` 의 `refs/main` 이 없으면 `local_ai` 는 미설치(`NOT_INSTALLED`, 사유에 빠진 저장소). 캐시 `refs/main` 이 계획의 `model_commit` 이 된다. 실행 환경은 `HF_HUB_OFFLINE` · `TRANSFORMERS_OFFLINE` · `TEXT_ENCODER_DEVICE=cpu` 등을 Provider 가 넣고 HF 토큰은 넘기지 않는다. 기본 `subprocess_timeout_seconds` 300 은 Kimodo 1건(차가운 첫 실행 약 90초 — §14 Phase 5)에 충분하다. 다른 PC 는 `Saved/AnimGen/policy.json` 의 `paths` 로 덮어쓴다.

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
| select 단계 (개정 11) — 후보 일괄 리타깃 실패 · 후보 일부 검증 `FAILED` · 전부 `FAILED` | `RETARGET_FAILED` · (그 후보만 제외 — `selection.candidates[].excluded`) · `VALIDATION_FAILED` (`ALL_CANDIDATES_FAILED`) | 다음 후보(Provider) · 남은 후보에서 선택 · 다음 후보(Provider). 후보 애셋 · IK Rig · RTG 는 `intermediate_assets` |
| `UNEXPECTED_DIRTY` · `OUTPUT_PATH_NOT_ALLOWED` · `ASSET_EXISTS` · `ASSET_PROTECTED` · `IMPORT_SOURCE_NOT_ALLOWED` | 그대로 | **중단** — 가드·요청 문제라 다른 Provider도 같다 |
| Provider `RATE_LIMITED` | 그대로 | 같은 후보 재시도 |
| 포장 · AnimBP 연결 단계의 실패 (개정 10) — 슬롯 · 컴파일 · 스모크 · 시나리오 · 운영 미리보기 등 | `INTEGRATION_FAILED` (`SLOT_NOT_IN_SKELETON` · `COMPILE_FAILED` · `SMOKE_FAILED` · `SMOKE_NOT_FOUND` · `SCENARIO_FAILED`(Job `error.details.observed`) · `PREVIEW_INVALID` · `ADDITIVE_INVALID` …) | **중단** — 다른 Provider 도 같은 포장 · 연결을 한다. 이미 만든 시퀀스는 `generated_assets` 에 남는다(다시 할 때는 그 애셋을 `reference_animations` 로 — 독립 실행). 이 단계의 가드 오류(`UNEXPECTED_DIRTY` 등)는 위 행대로 그대로 중단 |
| 자동 보정 (개정 13) — timing: 휘두름 없음 · 이미 빠름 · 바꿀 것 없음 / 측정 profile 없음 / `apply_animation_edits` 거부 · 검증 실패. fix.ops: 다리 본을 못 정함 · Blender 안 보정 실패 | timing: 한계 `TIMING_NOT_APPLIED{reason}`(항등 trim 으로 최종 애셋은 만든다) / `VALIDATION_FAILED NO_PROFILE` / `UNSUPPORTED_REQUEST BAD_OPERATIONS` · `VALIDATION_FAILED`. fix.ops: `UNSUPPORTED_REQUEST FIX_LEGS_UNKNOWN`(계획 — 후보 제외 · 실행) · `GENERATION_FAILED <Blender 코드>`(`FIX_LEGS_UNKNOWN` · `FIX_BONE_MISSING` · `UNSUPPORTED_FIX_OP`) | 계속(한계) / 다음 후보 / 다음 후보 · 같은 규칙. fix op 인자 오류 · 중복은 계획 전체 `BAD_REQUEST`(`DUPLICATE_FIX_OP`) |
| 대상 메시 캡처 단계 (개정 12) — `CAPTURE_FAILED` · 캡처 루트 · 비교 이미지 · 메시 불일치 · 정면을 못 잼 | 한계 `REVIEW_NOT_CAPTURED{reason}` (Job `review.capture.ok = false`) | **계속** — 캡처는 판정 근거라 생성 실패가 아니다(blender 렌더 실패와 같은 규칙). 연결 오류(`EDITOR_GONE` · `TIMEOUT` …)와 `UNEXPECTED_DIRTY` 는 위 행대로 중단 |
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
| `geometry` (개정 14 — 8-4a) | `geometry: true` 일 때: 메시(인자 `skeletal_mesh` → 해석된 메시) LOD0 정점의 범위 · 무게중심 · 주축 3개(공분산 야코비, 부호 = 가장 큰 성분 +, 범위 · 길이 · 표준편차) · 첫 주축 단면 24칸(칸마다 정점 수 · 둘째 · 셋째 축 폭 · 중심 — 손잡이 = 가늘고 정점이 적은 구간) · 본별 정점 범위. 무기 손잡이 축의 **근거**(선분은 요청이 준다 — 아래) |

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
  "retarget": { "source_mesh": null, "existing_retargeter": null, "source_facing": "auto",   // 개정 6 — 재사용은 명시할 때만 · 개정 7 보강 source_facing
                "align_mode": "per_bone", "body_clearance": null },                     // 개정 8 · 개정 11 — 비우면 파지 플래그 = measure, 아니면 resolve
  "constraints": { "two_hand_weapon_grip": true, "foot_contact": true, "smooth_start_end": true },   // 개정 11 — local_ai 는 앞 둘을 2차 생성 제약으로
  "generation_policy": "FREE_FIRST",
  "provider": "auto",
  "package": {                               // 개정 10 — 있을 때만 포장 단계. 출력은 output_path, 쓰기는 generation_guard
    "additive":   { "additive_type": "LocalSpaceBase", "ref_pose_type": "LocalAnimFrame", "ref_frame_index": 0, "ref_pose_sequence": null },
    "montage":    { "name": null, "slot": "UpperBody", "blend_in": 0.1, "blend_out": 0.15,           // name 생략 = AS_ → AM_
                    "sections": [{ "name": "Loop", "start": 0, "next": "Loop" }] },
    "blendspace": { "name": "BS_Vesper_Sickle_Walk1D", "dimensions": 1, "axes": [{ "name": "Speed", "min": 0, "max": 500 }],
                    "samples": [{ "animation": "$asset", "value": [300] }, { "animation": "/Game/…/AS_Idle", "value": [0] }], "aim_offset": false }
  },
  "integrate_anim_bp": false,                // 개정 10 — 참일 때만 anim_bp 를 읽는다(anim_gen 은 복제본에만 쓴다)
  "anim_bp": { "asset_path": "/Game/Animation/Hero/ABP_Hero_Combat",
               "operations": [{ "op": "set_asset", "node": "<guid>", "asset": "$blendspace" }],   // apply_graph_operations op 사전, 빈 목록 = 재생 확인만
               "scenario": { "montage": "$montage", "expect": { "slots_active": ["UpperBody"] }, "wait_frames": 10 },
               "smoke": true },
  "output_path": "/Game/Animation/Generated/Vesper",
  "motion_file": null,                       // 개정 7 — BVH 경로 또는 {path, unit, facing, range, axis_forward, axis_up}
  "prompt": "A person swings a scythe in a circle three times.",   // 개정 8 — 생성 모델이 읽는 영어 문장 (description 은 기록만)
  "generation": { "seed": null, "samples": 1, "steps": 100, "postprocess": "auto", "pick": 0,
                  "constraints": [{ "type": "root_path", "points": [{ "t": 3.0, "forward_cm": 400, "left_cm": 0, "yaw_deg": 180 }] }],  // 개정 8
                  "options": { "external.meshy": { "mode": "prime" } },                      // 개정 9 — Provider 별 설정
                  "candidates": 1,                                                           // 개정 11 — 1 ~ 6: seed, seed+1, … (한 Kimodo 실행)
                  "refine": { "mode": "auto",                                                // 개정 11 — auto: 바꿀 플래그가 있으면 2차 생성 · off: 한계로만
                              "grip": { "lead_hand": "right", "target": "meet", "spacing_cm": null, "target_spacing_cm": null, "from_s": null, "to_s": null },  // 개정 11 보강 4 — 간격은 둘 중 하나(생성 골격 · 대상 메시)
                              "keyframe_step": 3 },
                  "select": { "weights": { "grip": 3, "stance": 2, "swing": 2, "attack": 2, "clearance": 1, "breakage": 1, "cross": 2, "head": 2 } } },  // 개정 11 — 후보 선별 가중치(attack = 수정안 C, cross · head = 낫 정정)
  "review": { "render": { "count": 4, "views": ["front", "side"], "reference_images": [] },   // 개정 8 — blender 변환 단계의 소스 골격 렌더
              "capture": { "views": null, "mesh": null, "sequence": { "fps": 15, "cell_height_px": 320 }, "compare": true } },  // 개정 12 — 대상 메시 캡처(행 = render 시각)
  "fix": { "ops": [{ "op": "stance_width", "max_ratio": 3.0 }, { "op": "foot_lock" }],   // 개정 13 — blender 보정 op(리타깃 전 소스 골격, 다리는 대상 모델로 풀이)
           "timing": true,                   // 개정 13 — 리타깃 뒤 대상 시퀀스의 휘두름 가속 · 정지 머리/꼬리 트림(모든 경로)
           "body": {                         // 개정 14 (8-4b) — timing 뒤 대상 시퀀스의 한 풀이(모든 경로). true = 기본값
             "grip": { "spacing_cm": 60, "tolerance_cm": 11.09 },                 // 낫 = 소스 자루 간격 60 ± 13 × 팔 길이 비(E0 와 같은 띠), 검은 비움
             "targets": [ { "id": "lower_finish", "note": "베기 끝에 낫을 더 낮게",     // note = 사용자 지시 원문(기록만) — 바꾸는 것은 Claude Code
                            "effector": "hand_r", "at": { "event": "swing_end" }, "hold_s": 0.3,
                            "position": { "offset_cm": [0, 0, -15], "space": "body" }, "ease_s": 0.15, "priority": "soft" } ] } }
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
| `duration_seconds` · `frame_rate` · `loop` · `constraints` | 결과와 다르면 한계로 기록: `DURATION_MISMATCH` · `FRAME_RATE_MISMATCH`(출력 fps = 주 소스, §2.3) · `LOOP_MISMATCH` · `GRIP_NOT_VALIDATED` · `FOOT_CONTACT_NOT_ENFORCED` · `CONSTRAINT_UNSUPPORTED`. 길이·fps·루프는 결과를 측정해 적는다(계획 단계 값은 예상). `loop`는 `direct_key` 결과의 `bLoop`로도 쓰인다(내장 검증 `expect`가 쓴 값을 확인). 개정 10: `ANIM_BP_NOT_INTEGRATED` 폐지 — `integrate_anim_bp` 는 아래 `anim_bp` 행 |
| `package{additive?, montage?, blendspace?}` (개정 10) | 하나 이상. `additive{additive_type LocalSpaceBase \| RotationOffsetMeshSpace, ref_pose_type RefPose \| AnimScaled \| AnimFrame \| LocalAnimFrame (기본 LocalAnimFrame 0), ref_frame_index ≥ 0, ref_pose_sequence ('$asset' = 자기 자신 · 경로 · null)}` — `AnimFrame` · `AnimScaled` 는 기준 시퀀스 필수(§2.3), 새로 만든 시퀀스만(재사용이면 `ADDITIVE_ON_REUSED`). `montage{name? (생략 = animation_name 의 AS_ → AM_), slot (기본 DefaultSlot, 이름 형식), blend_in? · blend_out? ≥ 0, sections?[{name, start ≥ 0, next?}]}`. `blendspace{name (필수), dimensions 1 \| 2, axes[{name, min, max > min, grid?, snap?, wrap?}], samples[{animation '$asset' \| 경로, value[dimensions]}] (축 범위 밖 `OUT_OF_RANGE`), aim_offset}`. 이름은 서로 · `animation_name` 과 달라야(`DUPLICATE_NAME`). 몽타주면 한계 `NOTIFIES_NOT_ADDED` |
| `integrate_anim_bp` · `anim_bp{asset_path, operations[], scenario?, smoke}` (개정 10) | `integrate_anim_bp` 가 참일 때만 `anim_bp` 를 읽는다 — 참인데 없으면 `MISSING_FIELD`, 거짓인데 있으면 `CONFLICTING_FIELDS`(애셋만 요청하면 AnimBP 를 건드리지 않는다). `asset_path` = 연결할 AnimBP(anim_gen 은 복제본에만 쓴다). `operations` = `apply_graph_operations` op 사전(빈 목록 = 복제본 컴파일 · 스모크 · 시나리오로 재생만 확인), 있으면 한계 `ANIM_BP_APPLY_PENDING`. `scenario{montage? ('$montage' · 경로), expect{state_machines{}, slots_active[]}, wait_frames 1 ~ 600, set_variables{}, mesh? (기본 target_mesh), map?}` = 복제본의 `run_anim_scenario`. `smoke` 기본 true |
| 자리표시 `$asset` · `$montage` · `$blendspace` (개정 10) | 문자열 값 **전체**가 자리표시일 때만 실행 때 바꾼다(부분 문자열은 그대로). `$asset` = 최종 시퀀스(재사용이면 그 애셋), `$montage` · `$blendspace` = 그 포장 단계가 같은 요청에 있을 때만(`PLACEHOLDER_UNBOUND`), 모르는 `$이름` 은 `UNKNOWN_PLACEHOLDER` |
| `save` | 요청에 두지 않는다 — `generate_motion(plan_id, save)` 인자 |
| `motion_file` (개정 7) | 문자열이면 `path`. `path`: 절대 경로, ini `ImportSourceRoots` 아래만(밖이면 계획 전체가 `IMPORT_SOURCE_NOT_ALLOWED`), `.bvh`만. `unit`: `auto`(기본) · `cm` · `m` · `mm` · `inch` · 숫자(cm/파일 단위). `facing`: `auto`(대상 스켈레톤 정면에 맞춤, 기본) · `keep` · `+X` · `−X` · `+Y` · `−Y`(UE 축). `range{start, end}`(초, 굽기 범위 — 요청 `frame_rate` 가 있으면 끝을 그 rate 의 프레임 경계로 당긴다, 진단 `RANGE_ALIGNED`. 정수 fps 가 아니라 맞출 수 없으면 리샘플하지 않는다). `axis_forward`(`-Z`) · `axis_up`(`Y`) — Blender BVH 임포터와 같은 뜻. 계획이 BVH 헤더(관절 계층 — 수동 체인 제안용) · 단위 · 회전 · 범위 · fps · 파일 SHA-256 을 고정하고, 실행 때 파일이 바뀌었으면 `FILE_CHANGED`로 멈춘다 |
| `prompt` (개정 8) | 생성 Provider(`local_ai`)가 읽는 영어 문장, 1 ~ 500자. `description` 은 기록만이고 서버는 해석하지 않는다(자연어 → 프롬프트 변환은 Claude Code). 없으면 `local_ai` 후보는 `MISSING_INPUT` 으로 제외. 길이는 `duration_seconds`(없으면 5초 — `DURATION_DEFAULTED`) → 프레임 = round(길이 × 30) + 1(최대 300 = 10초) |
| `generation{seed?, samples=1, steps=100, postprocess=auto, pick=0, constraints[]}` (개정 8) | `seed` 0 ~ 2³¹−1(없으면 계획이 골라 고정 — `SEED_PINNED`) · `samples` 1 ~ 4(같은 seed 로 여러 샘플, 리타깃은 `pick` 번째) · `steps` 10 ~ 1000(확산 단계) · `postprocess` `auto`(설치돼 있으면 켬) · `on`(없으면 `POSTPROCESS_UNAVAILABLE`) · `off`(한계 `POSTPROCESS_OFF`) — Kimodo 발 미끄러짐 후처리(`motion_correction`). `constraints[]`: `root_path{points[{t, forward_cm, left_cm, yaw_deg?}]}` — **캐릭터 기준**(생성 첫 프레임 정면 = forward, 왼쪽 = left, yaw + = 왼쪽으로 돎) → Kimodo `root2d`(yaw 있는 점은 따로 묶어 방향 고정). `keep_pose{npz, times[], part=full\|left_hand\|right_hand\|left_foot\|right_foot}` — 이전 Kimodo 결과 NPZ 의 그 시각 포즈를 고정하고 나머지를 다시 만든다(레퍼런스 기반 다듬기). `kimodo_raw{path}` — Kimodo `constraints.json` 그대로(≤ 8 MB, 타입 · 프레임 범위 검사). 시각 → 프레임 round(t × 30), 생성 길이 밖이면 `CONSTRAINT_OUT_OF_RANGE`, 같은 프레임 두 번이면 `DUPLICATE_FRAME`. 파일은 `ImportSourceRoots` 아래만 · SHA-256 고정(실행 때 바뀌었으면 `FILE_CHANGED`). 요청 `constraints{}`(플래그)와는 별개다 |
| `generation.options{<provider>: {...}}` · `prompt` 의 Meshy 규칙 (개정 9) | Provider 이름 → 그 Provider 만 읽는 설정(다른 Provider 는 무시). 이름이 레지스트리에 없으면 `BAD_REQUEST UNKNOWN_PROVIDER`, 값은 그 Provider 계획이 검사한다. `external.meshy`: `{mode: prime (기본, FBX · 10 크레딧) \| swift (BVH · 3 크레딧 — blender 변환 사슬)}`, 다른 키 · 값은 `BAD_OPTION`. Meshy 는 `prompt` 1 ~ 400자(넘으면 `PROMPT_TOO_LONG`), 길이를 0.5초 단위로 맞추고(`DURATION_SNAPPED` — 결과 `DURATION_MISMATCH`), 없으면 5초(`DURATION_DEFAULTED`), 2초 미만 `DURATION_TOO_SHORT` · 10초 초과 `DURATION_OVER_MAX`. 로컬 모델 설정(`seed` · `samples` · `steps` · `postprocess` · `pick`)을 기본값과 다르게 주면 한계 `GENERATION_SETTINGS_IGNORED{fields}`, 생성 제약은 종류마다 `CONSTRAINT_UNSUPPORTED`, 항상 `NOT_REPRODUCIBLE`(seed 없음) |
| `review{render{times[] \| count, views[], reference_images[]}}` (개정 8) | `blender` 변환 단계의 프레임 렌더 비교. `times`(변환된 클립 기준 초, 0 = 첫 프레임, 1 ~ 12개) 또는 `count`(1 ~ 12, 기본 4 — 첫 · 끝 포함 고르게, 실행 때 잰 길이로 다시 펼친다). 둘 다 주면 `CONFLICTING_FIELDS`, 클립 끝을 넘는 시각은 그 후보를 `REVIEW_TIME_OUT_OF_RANGE` 로 막는다. `views` ⊆ `front` · `side`(기본 둘). `reference_images` ≤ 4, `ImportSourceRoots` 아래 .png/.jpg(시트의 모든 행에 같은 그림). 보이는 것은 변환된 **소스 골격**이다(한계 `REVIEW_IS_SOURCE_SKELETON`) |
| `review.capture` (개정 12) | `true` 또는 `{times? \| count?, views?, mesh?, sequence?, compare?}` — 하나라도 오면 `review` 는 `{render?, capture?}`(빠진 쪽은 키가 없다 — render 만이면 개정 8 모양 그대로). render 가 있으면 행 = render 시각(capture 에 times · count 를 주면 `CONFLICTING_FIELDS` — 두 시트가 같은 행이어야 나란히 본다), 없으면 `times`(최종 클립 기준 초, 1 ~ 12) 또는 `count`(1 ~ 12, 기본 4 — 첫 · 끝 포함). `views` 기본 = render 의 뷰 또는 `front` · `side`. `mesh` 기본 `target_mesh`(없으면 단계 없이 `REVIEW_NOT_CAPTURED MISSING_MESH`). `sequence{fps 1 ~ 30 (15), cell_height_px 64 ~ 1024 (320), max_frames 1 ~ 300 (150)} \| false` — 연속 프레임 → APNG. `compare`(기본 true) — render 행이면 같은 시각의 소스 골격 프레임을 비교 칸으로(`compare.png`). 한계 `REVIEW_CAPTURE_PREVIEW_ONLY`(무기 · 옷/머리 물리 · 게임 AnimBP 레이어 없음 · 프리뷰 조명 — 판정은 사람) |
| `fix{ops[{op, …}]}` (개정 8 · 개정 13) | `blender` 변환 단계의 보정 op(범위를 정한 뒤 · 기둥 메시 앞, 리타깃 **전** 소스 골격). 사전(개정 13 — `anim_gen/fix_ops.py`): `smooth{sigma_frames 0.5 ~ 3 (1), bones "all" \| [이름], root true, from_s?, to_s?}`(로컬 회전 쿼터니언 부호 연속 · 루트 위치 가우시안 — 8-1 수정안 A 함수, 휘두름 정점을 깎아 기본으로 안 켠다) · `stance_width{max_ratio 1 ~ 10 (3.0), min_ratio (1.2), max_shift_cm (25), blend_s (0.2), keep_knee_bend (true — 개정 13 보강: 좁힌 만큼 골반을 올려 무릎 굽힘을 원래대로)}`(**두 발을 디딘 프레임**의 발 좌우 비 — §13 stance 정의 · 대상 메시 기준 — 상한. 오프셋은 발마다 접지 구간 상수 · 공중은 smoothstep, 모자라면 전역 배율 · 최소 간격 지킴) · `foot_lock{feet [left, right], contacts "auto", height_ratio (0.04), speed_ratio (0.25 다리/s), min_frames (4), blend_frames (3), lock_rotation false}`(접지 구간마다 발목 한 점 — 가장 느린 프레임 수평 · 중앙값 높이). 순서 고정 smooth → 다리 풀이(요청 순서가 다르면 진단 `FIX_OPS_REORDERED`), 다리 둘은 한 풀이 — **리타깃된 다리의 모델**(대상 엉덩 관절 = 대상/소스 골반 높이 × 소스 골반 + 골반 회전 변화 · 대상 엉덩 오프셋, 다리 = 소스 뼈 방향 · 대상 길이)에서 접지 · 간격 · 고정을 풀고 '엉덩 둘레로 먼저 돌린 뒤 길이 맞춤' 2본 IK 의 방향 변화를 소스 뼈에 입힌다(대상 치수가 없으면 소스 공간). 사전 밖 op 는 모든 후보 `UNSUPPORTED_FIX_OP`(`available` = 사전), 인자 오류 · 같은 op 두 번은 `BAD_REQUEST`(`fix.ops[i].<키>` · `DUPLICATE_FIX_OP`). 다리 op 는 소스 다리 체인이 필요(`FIX_LEGS_UNKNOWN`). 한계 `FIX_ON_SOURCE_SKELETON`, 위험 `FIX_RESOLVED_AT_RUN`. Job `fix{source(Blender 보고 — before · after = 대상 예측, source_before · after = 소스), target(리타깃 뒤 실측)}` |
| `fix.timing` (개정 13) | `true` 또는 `{mode auto \| off, target_peak_cm_s 50 ~ 5000 (1200), max_rate 1 ~ 4 (2.0), recovery_rate 1 ~ 4 (1.5), antialias 0 ~ 1.5 (1.0 — 개정 13 보강), swing{core_ratio (0.5), edge_ratio (< core, 0.2)}, still{speed_cm_s (30), min_s (0.3), trim_head (true), keep_head_s (0.2), trim_tail (true), keep_tail_s (0.3)}}` — 리타깃 뒤 대상 시퀀스(모든 경로)의 흐느적 보정(§5 · §14 '8-3'). 끄면 키가 없다(계획 = 개정 12). 범위 밖 · 모르는 키 `BAD_REQUEST`(`fix.timing.<키>`). 길이가 바뀌면 `DURATION_MISMATCH` 대신 한계 `TIMING_CHANGED_LENGTH`, 바꿀 것이 없으면 `TIMING_NOT_APPLIED{reason NO_SWING \| ALREADY_FAST \| NOTHING_TO_CHANGE}` |
| `fix.body` (개정 14 — 8-4b) | `true` 또는 `{mode auto \| measure \| off, clearance{margin_cm 0 ~ 5 (0.5 × scale), allow_contact (true — 8-4b 후속: 몸통 · 넓적다리는 맞닿음 contact_cm 까지 정상, 머리목 · false 는 margin 만큼 뗀다), hands (true — C++ body_clearance hands), upper_arm no_worse \| off, secondary record \| off, legs (false)}, grip{mode auto \| keep \| off, lead_hand right \| left, window null \| [a, b] 초, spacing_cm null \| (0, 200], tolerance_cm null \| (0, 100]}, joints{clavicle_deg 10, upper_arm_deg 45, elbow_deg 60, wrist_deg 30, spine_deg 0 (목표 구간 밖 척추는 8-4b 에서 끔 — 결정 D, 주면 NOT_SUPPORTED), spine_deg_for_targets 20, neck_deg_for_targets 20, pelvis_cm 15, pelvis_deg 10}, targets[], weights{clearance 10, grip 10, pins 10, targets 5, lead_hand 3, fidelity 1}, smooth_s 0.13, passes 3}` — 리타깃 · timing 뒤 대상 시퀀스의 한 풀이(§4 `body_fit` · §5 · §14 '8-4b'). 모르는 키 `BAD_REQUEST UNKNOWN_FIELD`(`fix.body.<키>`), 범위 밖 `BAD_FIELD`. 파지 = 손목 간격이 띠(`motion_metrics.grip_band(scale, spacing, tolerance)` — 비우면 검 띠 [0, 20 × scale]) 안인 구간(짧은 빈틈 2 프레임 잇기 · 3 프레임 이상 · 경계 0.1초 블렌드). `mode: measure` 는 측정만(애셋 없음). 한계 `BODY_FIT_APPROXIMATE`(항상) · `BODY_PENETRATION_REMAINS{pairs, reason}` · `GRIP_RELAXED{keep}` · `TARGET_NOT_REACHED{id, error, blocked_by}` · `BODY_FIT_SECONDARY_RECORDED` · `BODY_FIT_NOT_APPLIED`(바꿀 것 없음 — 항등 trim). Job `fix.body{version, mode, source, asset, model, events, grip{…, keep}, before, after (C++ 요약 — 후속: + loop_boundary_max_deg), predicted, predicted_vs_after, deltas, joints_moved_cm, passes, stats, targets, remains, loop{source (원본 numeric.loop — 루프면 시간 처리 순환), seam_deg (첫 · 끝 델타 차 °), boundary_max_deg [전, 후]}, seconds}` |
| `fix.body.targets[]` (개정 14 — 8-4b) | **자연어 지시 → 목표는 Claude Code 가 바꾼다**(서버는 해석하지 않는다 — `prompt` 와 같은 원칙). 계획에서 풀어 보이고 사용자 확인 뒤 실행. `{id (영숫자 _ - 64자, 중복 DUPLICATE_ID), note?, effector hand_l \| hand_r \| foot_l \| foot_r \| head \| pelvis \| 몸 모델 본 이름(척추 · 목 · 팔), at {event swing_start \| swing_peak \| swing_end \| still_start \| still_end (+ offset_s) \| swing \| both_planted (+ index)} \| {time} \| {window [a, b]}, hold_s (점 사건 · time 의 구간 길이, 0), position {offset_cm [앞, 왼, 위], space body} \| {offset_cm [x, y, z], space component} \| {absolute_cm, space} \| {away_from 본 \| head …, min_cm} \| null, rotation {offset_deg [pitch, yaw, roll], space body \| local} \| null, ease_s 0.15, weight 1, priority soft \| hard}`. 몸 기준틀(프레임마다 원래 포즈): 원점 = 두 엉덩 관절 중점, 왼 = 엉덩 축 수평, 위 = +Z, 앞 = 위 × 왼. 사건은 `timing.events` 한 원천(흐느적 보정과 같은 신호). 부위 → 자유도: 손 = 그 팔(+ 회전 목표면 손목) · 척추 본 = 그 본까지 척추 마디(합 ≤ spine_deg_for_targets) · head = 목 · 머리 · pelvis = 골반 이동 · 회전 + 다리 닫힌 식 IK(원래 발목 · 발 회전) — **몸통 · 골반 자유도는 그 목표 구간만**. soft(기본)는 관통 · keep 이 이기고 못 닿으면 `TARGET_NOT_REACHED{blocked_by clearance \| grip \| joint_limit \| pins}`, hard 는 관통보다 앞선다(남은 관통 → `BODY_PENETRATION_REMAINS`) |
| `retarget.align_mode` · `retarget.body_clearance` (개정 8) | `align_mode`: `per_bone`(`ops: match_existing` 의 기본) · `engine`(`ops: default` 는 정렬하지 않아 `engine` 만 — `per_bone` 이면 `ALIGN_MODE_WITHOUT_ALIGN`). §10. `body_clearance`: `resolve`(관통 프레임만 위팔 보정) · `measure`(검증에만) · `off` → `retarget_animations body_clearance`. **개정 11: 비우면 계획이 정한다** — `constraints.two_hand_weapon_grip` 이 참이면 `measure`(모든 Provider — 한계 `BODY_CLEARANCE_MEASURED_FOR_GRIP`), 아니면 `resolve`(개정 10 그대로). 파지 플래그에 `resolve` 를 명시하면 그대로 + 위험 `CLEARANCE_MAY_BREAK_GRIP`. 계획 단계 `inputs.body_clearance_from: request \| default \| grip_flag`. **개정 14(8-4b): `fix.body` 가 있으면 비운 값은 `measure`**(`body_clearance_from: body_fit` · 한계 `CLEARANCE_BY_BODY_FIT` — 보정 원천은 body_fit 하나), 명시 `resolve` 는 그대로 + 위험 `CLEARANCE_DOUBLE_FIX`. §10 · §13 |
| `generation.candidates` · `refine` · `select` (개정 11 — `local_ai`) | `candidates` 1 ~ 6(seed, seed+1, … — 한 Kimodo 실행, 기본 1). `samples` > 1 과 같이 주면 `BAD_REQUEST CONFLICTING_FIELDS`. `refine{mode auto \| off, grip{lead_hand right \| left, target meet \| lead, spacing_cm null \| (0, 100], target_spacing_cm null \| (0, 100], from_s?, to_s? (from ≤ to)}, keyframe_step 1 ~ 10}`(간격 둘 다 비우면 검 손잡이 = 주 손 너클 폭 + 1 cm · 판정 '≤ 20 cm × pelvis scale'. 자루 무기는 축을 따른 손목 간격 — **`target_spacing_cm` = 대상 메시 기준**(Vesper 낫 60) 또는 `spacing_cm` = 생성 골격 기준(처음 의미 그대로) 중 하나, 둘 다면 `CONFLICTING_FIELDS`. 개정 11 보강 4: 계획이 두 골격 기준 포즈의 어깨 관절 폭 · 팔 길이로 간격 사상(대상 = W_대상 + k × (생성 − W_생성), k = 팔 길이 비 — `motion_metrics.gap_map`)을 풀어 생성 간격(generate 규칙 · 소스 띠 '생성 간격 ± 13 cm')과 대상 띠('대상 간격 ± 13 × k cm' — select)를 한 값으로 정한다. 대상 팔을 재야 하므로 에디터 없이 계획하면 `PROVIDER_UNAVAILABLE EDITOR`, 대상 어깨 · 팔꿈치 · 손목 기준 위치가 없으면 `TARGET_ARMS_UNKNOWN`, 생성 골격 두 팔이 닿지 않는 간격이면 `GRIP_SPACING_OUT_OF_RANGE`, 한계 `GRIP_SPACING_MAPPED`) — auto 면 바꿀 플래그가 있을 때 2차 생성(§5 · §14 Phase 8), 파지 구간이 생성 길이 밖이면 `CONSTRAINT_OUT_OF_RANGE`, 2차 생성 + `samples` > 1 은 `UNSUPPORTED_REQUEST REFINE_WITH_SAMPLES`. `foot_contact` 를 바꾸면 후처리 `auto` 를 켠다(명시 `off` · 미설치면 한계 `FOOT_CONTACT_WITHOUT_POSTPROCESS`). `select{weights{grip, stance, swing, attack, clearance, breakage}}` — 키 6개만 · 0 이상(`selection.py`, attack 은 수정안 C — §14 Phase 8). 2차 생성은 1차 손목 굽힘을 지키고(keep) 출력을 σ 1프레임 스무딩한다(계획 `refine.smooth_sigma_frames` — 수정안 A · B). Meshy 는 기본값과 다르면 `GENERATION_SETTINGS_IGNORED.fields` 에 `candidates` · `refine` |
| 플래그 `constraints{two_hand_weapon_grip, foot_contact}` 의 처리 (개정 11) | `local_ai`(refine auto): 2차 생성 제약으로 바꾸고 한계 교체 — `GRIP_NOT_VALIDATED` → `GRIP_POSITION_ONLY`(손목 위치만 — 손 회전은 1차 손목 굽힘 유지일 뿐 손잡이에 나란히 맞추지 않는다. 손 방향 · 손가락 · 무기 소켓은 8-4, FK 리타깃은 양손 상대 위치를 보존하지 않는다), `FOOT_CONTACT_NOT_ENFORCED` → 진단 `FOOT_CONTACT_CONSTRAINED`, 고른 후보의 Vesper 파지가 80% 미만이면 `GRIP_NOT_REACHED{grip_pct}`, select 가 있으면 `SELECTED_BY_NUMBERS`. 그 밖의 Provider · refine off: 개정 10 그대로 한계로만(`GRIP_NOT_VALIDATED` · `FOOT_CONTACT_NOT_ENFORCED`) — 관통 기본값(위 행)만 모든 Provider 에 적용 |

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
  - **손가락 체인 제안 (개정 8):** 손가락은 이름 대신 위상 · 좌표로 찾는다(`Core/AnimMcpFingerChains` — 손목 아래 갈래 · 마디 수 · 좌우 거울 · 엄지 = 손바닥 평면에서 가장 벗어난 갈래). `create_ik_rig` 결과(auto 실패 `details` 포함)에 `finger_chain_suggestion`, 진단 `FINGER_CHAINS_SUGGESTED`(info) · 템플릿 체인과 다르면 `FINGER_CHAINS_DIFFER`(warning — SOMA 는 자동 캐릭터라이즈가 Mixamo 템플릿으로 잡혀 `LeftIndex` = Index1 ~ 3, 메타카팔부터 한 마디 밀림). `inspect_skeleton suggest_finger_chains`(옵트인)도 같다. 대상에 손가락 체인이 있는데 소스에 없으면 그 손가락은 대상 기준 포즈로 남아야 한다(아래 정렬 · §13 `fingers`).
- **`match_existing` 매핑 (개정 8):** 모든 op 를 정확 이름으로 매핑한다(`AutoMapChains(Exact, bForceRemap)` — 꺼진 Run IK Rig op 포함). FK op 만 바꾸면 꺼진 op 의 퍼지 매핑이 자동 정렬을 그르친다(§2.3). 기존 RTG 회귀(`RTG_KatanaToH` 본별 0°)는 그대로 — 메타카팔은 뼈 1개 체인이라 그 RTG 에서도 퍼지 매핑이 정렬에 안 걸렸다.
- **리타깃 포즈 정렬 `align_mode` (개정 8):** `create_ik_retargeter align_mode` = `engine`(플러그인 기본 — 엔진 `AutoAlignAllBones`/`AutoAlignBones`, Phase 1 회귀 기준) · `per_bone`(anim_gen `match_existing` 기본, `Core/AnimMcpRetargetPoseAlign`). 원칙: **기준 포즈 관례가 다른 부위(팔 · 다리의 T 대 A)만 소스에 맞추고, 같은 자세(직립)를 뜻하는 부위의 차이는 체형이니 대상 것을 둔다.** `per_bone` 순서:
  - ⓪ 축 체인 중립 — 대상 기준 포즈에서 거울 짝 체인(뼈 ≥ 2, 수직이등분면 반사)으로 좌우축 · 정중선을 이름 없이 정하고, 짝이 없고 정중선 근처(가장 안쪽 짝 반폭 × 0.25)인 체인(척추 · 목 · 머리)과 펠비스는 **정면 맞춤만 반영한 대상 기준 포즈**로 둔다(엔진의 `AlignPelvisBone` · 척추 접선 · 목 정렬이 소스 몸통 모양을 복사하던 것을 되돌림). 팔 · 다리는 바뀐 몸통 위에서 다시 정렬한다.
  - ① 뼈 수가 같은 체인은 FK op 를 `OneToOne`(관절 비율 차가 굽힘을 섞지 않게 — §2.3), ② 대응 본 구간 정렬 + ③ 체인 끝 랜드마크(매핑된 자식 체인의 시작, 둘 이상이면 Horn 최소제곱, 잔차 15° 넘는 랜드마크는 뺌 — 엄지)로 굴림은 체인 부모가 정한다.
  - ②' 메타카팔 상대 — 손가락 체인은 대상 메타카팔을 그대로 두고 소스 메타카팔 → 첫 마디 구간을 대상 메타카팔 구간에 맞춘 최소 회전(Q) 뒤의 소스 방향으로(부모 매핑 본이 정중선 밖일 때 — 쇄골 → 팔은 제외), 응답 `relative_chains[]`. 메타카팔 자체를 소스로 돌리는 안은 손 굴림 · 손바닥 변형으로 기각.
  - ④ 머리 해부적 중립 — 아래에 매핑 체인이 없는 뼈 1개 말단(머리)은 엔진이 건너뛴다(§2.3) → 소스 짝 본의 기준 포즈 대비 회전 × 정면 맞춤 × 대상 기준.
  - 결과 `pose_alignment{chains[], chain_ends[], relative_chains[], axial{lateral_axis, mirror_pairs, chains, pelvis}, neutral_bones[]}`.
- **기준 포즈 FBX 2단 임포트 (개정 8):** `blender` 변환이 동작 FBX 와 함께 기준 포즈 2프레임 FBX(`<이름>_Rest.fbx` — 애니가 없으면 `import_animation_file` 이 `NO_ANIMATION`)를 내면, import 단계는 ① 기준 포즈 FBX → `<work>/Import/`(메시 · `_Rest_Skeleton` · `_Rest_Anim`) ② 동작 FBX → `<work>/Import/Motion/` 에 그 스켈레톤으로 애니만. 깊은 본 때문에 Interchange 가 첫 프레임을 기준 포즈로 삼는 것을 피한다(§2.3).
- **팔-몸통 관통 (개정 8):** 위팔 월드 방향은 소스와 같아도 어깨 반폭 · 옷 부피가 다르면(CMU 21.5 vs Vesper 12.0 cm) 손 · 아래팔이 허리 · 넓적다리에 들어간다. `retarget_animations body_clearance` = `off`(플러그인 기본) · `measure` · `resolve`(anim_gen 기본) · `{mode, margin_cm, max_deg, …}`. `resolve` 는 관통한 프레임만 위팔 트랙을 어깨 둘레 최소 회전(최소제곱, 8° 걸음, 쇄골 공간에서 ±0.13 초 팽창 + 가우시안, 재검사 3회)으로 고친다 — 팔꿈치 · 손 로컬 회전은 그대로. 몸은 대상 메시 LOD0 스킨의 **반경 지도**(몸통 축 = 엉덩 관절 중점 → 척추 끝, 넓적다리 축, (t × 10°) 칸마다 최대 반경, 깊이 = 반경 − 축 거리)로 잰다 — 가장 가까운 정점 법선은 깊이 박힌 점에서 방향이 엉켜 버렸다. 체인 = 리타기터 대상 IK Rig, 거리 기본값 × 펠비스 높이 / 100. 경고 `BODY_CLEARANCE_LIMIT` · `CLEARANCE_GRIP_CHANGED`(양손 거리 변화) · `BODY_PENETRATION_REMAINS`, anim_gen 진단 `BODY_CLEARANCE_RESOLVED`. 기존 Vesper 애니(다른 체형에서 리타깃된 마켓 애니)도 18 ~ 35% 관통하지만 일괄 보정은 하지 않았다(부록 B).
  - **양손 파지 요청이면 측정만 (개정 11 — 사용자 결정 A안):** `resolve` 는 관통 프레임마다 위팔을 몸 바깥으로 돌리므로 양손으로 모아야 할 팔을 벌린다. 첫 실험 E1(기준 Kimodo 칼 시험과 같은 seed 를 `measure` 로 다시 만들어 유지 애셋(`resolve`)과 비교, 2026-10-26): Vesper 손목 간격 `measure` 최소 36.5 · p50 51.0 cm(20 cm × scale = 21.05 cm 안 **0%**) → `resolve` p50 53.1 cm(벌림 p50 1.9 · 최대 4.1 cm, 왼 손목 이동 p50 2.9 · 최대 5.7 cm, 위팔 방향 p50 8.2 · 최대 14.2°, 오른손 · 발 0) — **파지가 처음부터 없었고 보정은 더 벌렸을 뿐**(파지 프레임을 깬 0프레임). 그래서 `two_hand_weapon_grip` 이면 기본 `measure`(모든 Provider, C++ 변경 없음). 파지를 지키면서 관통을 없애는 C안(두 팔을 함께 옮겨 파지 + 관통 0)은 8-4 손 IK 와 같은 계산이라 8-4 에서. 비파지 프레임의 관통은 select 지표 `non_grip`(상한 = min(비파지 프레임 %, 관통 %)) — 기록만.
  - **`resolve` 와 `body_fit` (개정 14 — 8-4b, C안 실현):** `fix.body` 가 있으면 리타깃의 `resolve`(위팔만 · 팔마다 따로)는 기본 `measure` 로 바뀌고, 관통은 **대상 시퀀스 위 한 풀이**(`body_fit`)가 고친다 — 쇄골 · 위팔 swing · 팔꿈치 경첩 · (파지 프레임만) 두 손목을 두 팔 함께 움직여 관통(몸통 · 넓적다리 · 머리목 · 반대 손) · 파지 keep · 주 손 충실도를 같은 GN 안에서 맞춘다(같은 반경 지도 원천 — C++ 몸 모델). 같은 자유도를 두 번 고치지 않으려고 둘을 함께 쓰지 않는다(요청이 `resolve` 를 명시하면 위험 `CLEARANCE_DOUBLE_FIX`). `resolve` 자체는 그대로(플러그인 기본 off · `fix.body` 없는 anim_gen 기본 resolve — 회귀 기대값 불변).

---

## 11. 복합 애니메이션 (Phase 8)

원본의 세그먼트 계획(Dash → Takeoff → Airborne Rotation → Attack → Landing → Recovery)을 유지한다. 각 세그먼트는 길이, 시작·끝 포즈, 루트 모션, 접촉·무기·타이밍 제약을 가진다. 세그먼트별 Provider가 다를 수 있다. 연결부의 포즈·속도 연속성은 `validate_animation`의 수치 항목으로 검증한다. 분해했다고 자연스러운 연결이 보장되지는 않는다.

---

## 12. AnimBP 연결과 승격 (Phase 7 — 개정 10)

- **기존 Tool만 쓴다:** `create_anim_montage` · `set_montage_slots` · `set_montage_sections` · `create_blendspace` · `set_sequence_additive` · `duplicate_animation_blueprint` · `apply_graph_operations` · `run_automation_tests` · `run_anim_scenario`. 새 Tool 은 승격(`promote_animation`) 하나. anim_gen 의 포장 · 연결 단계는 이 Tool 들을 옵트인 `generation_guard` 로 부른다(§3.1-6).
- **애셋만 요청하면 AnimBP를 수정하지 않는다**(원본 유지) — `integrate_anim_bp` 가 거짓이면 AnimBP 호출 0.
- **anim_gen 은 운영 AnimBP 에 쓰지 않는다.** 복제본(`<work>/<ABP>_Test_<job>A<n>`)에서 적용 · 컴파일 · 스모크 · 시나리오 → 운영 AnimBP 는 `get_anim_blueprint_info`(revision) · `preview_graph_operations`(읽기)만 → Job `anim_bp.apply_payload{asset_path, operations, expected_revision, compile: true}`. 운영 경로는 가드가 거부하므로(`OUTPUT_PATH_NOT_ALLOWED`) 실수로도 쓰지 못한다.
- **사격 + Strafe(예시 C):** 하체 strafe, 상체 조준·레이어 블렌드, AimOffset, 왼손 IK, 조준 보정은 이미 `ABP_Hero_Combat` 계열에 있다. 생성할 것은 상체 사격 루프·반동 시퀀스이고, 연결은 기존 레이어 구조에 애셋을 끼우는 일이다(`UpperBody` 슬롯 몽타주 — 2026-10-25 복제본에서 `slots_active[UpperBody]` 확인).
- 이동 로직, 락온 방향, 사격 지속 시간 같은 게임플레이 상태는 기존 C++/GAS가 기준이다(원본 유지). 운영 계열은 네이티브 AnimInstance 가 매 프레임 변수를 덮어써 시나리오의 `set_variables` 로 전이를 몰 수 없다 — 전이 확인은 BP 변수 ABP(`ABP_McpRuntimeTest` 복제본), 운영 계열은 슬롯 · 진입 상태로 본다(플러그인 README 제약).

**승격 (`promote_animation`)** — 후보 경로 → 정식 경로(`/Game/Animation/Hero/<영웅>/<계열 | Common>/<Locomotion | Actions>/<이름>` — `.claude/plans/anim-asset-naming.md`). 엔진 AssetTools rename(2026-10-22 애셋 정리와 같은 경로)이 새 패키지 · 참조 패키지를 **자동 저장**하므로 사전 검사 + `confirm`:
- `dry_run` 으로 `planned[{source, dest, class, content_hash, referencers[{package, candidate, allowed}]}]` 를 보이고 → 사용자 승인 → `confirm: true`.
- 후보 경로 안 참조자는 허용(엔진이 고치고 저장), 밖은 `allow_referencers` 로 명시해야 한다(예: 먼저 승격한 BS 가 그 샘플을 참조). 맵 · 보호 애셋 · 미저장 편집이 있는 참조자는 거부. 서로 참조하는 애셋은 한 배치로 옮기면 참조 거부가 없다.
- 결과: 옛 경로 애셋 · 리디렉터 0 · 옛 .uasset 없음 · 내용 해시 같음 · 참조자가 새 경로 · 저장 집합 ⊆ 후보 ∪ dest ∪ allow_referencers.
- 이름 규칙은 플러그인이 모른다 — anim_gen Job 의 `promotion{folder, assets[{source, dest}]}` 이 제안한다(idle · locomotion → Locomotion, 그 밖 Actions, hero 없으면 제안 없음). 재사용 애셋은 제안하지 않는다.

**운영 AnimBP 적용 절차 (승인 게이트 — Phase 7 은 실제 적용을 하지 않았다, 사용자 결정):**
1. anim_gen Job 이 복제본 검증 + 운영 미리보기 · revision 까지 끝낸다(운영 SHA-256 무변경).
2. 정식 경로로 쓸 애셋이면 `promote_animation` dry_run → 사용자에게 보임 → 승인 → 실행. **운영 AnimBP 가 후보 경로를 가리키게 하지 않는다**(승격 → 운영 적용 순서). 복제본(후보 경로)의 참조는 엔진이 새 경로로 고친다.
3. 적용 직전 다시 `get_anim_blueprint_info`(revision) + `preview_graph_operations`(페이로드의 바인딩을 정식 경로로 바꾼 op — `rebind_after_promotion`) → 사용자에게: planned 목록 · `expected_revision` · 복제본 검증 결과(컴파일 · 스모크 · 시나리오 관측).
4. 승인 → `apply_graph_operations(운영, operations, expected_revision, compile=true, save=true)` — 가드 없이(운영 경로라 가드가 거부한다 — 의도). revision 이 바뀌었으면 `REVISION_MISMATCH` 무변경(2026-10-25 복제본에서 같은 메커니즘 확인).
5. 검증: 컴파일 0/0 · `AnimGraphMcp.Smoke.AnimBlueprint.<이름>` · `run_anim_scenario`(운영) · 관련 `AstralBreak.*`.
6. 되돌리기: 운영 .uasset 은 git 추적 — 사용자가 되돌린다. 스켈레톤 슬롯 등록(`add_skeleton_slot`, 스켈레톤이 `/Game/Assets/` 아래) · GA 몽타주 지정(`FireMontage` 등 데이터)은 별도 승인 사항.

**노티파이와의 관계:**
- 플러그인 = 몽타주 구조(슬롯 · 섹션 · 블렌드). 프로젝트 노티파이(`AstralAnimNotify_GameplayEvent` · `…GameplayEventWindow` · MotionWarping · PawnCollision + GameplayTag) = `astral-ue-montage` 스킬 / `Tools/lib/ab_montage.py`. 플러그인 · anim_gen 은 프로젝트 클래스를 모르므로 부르지 않는다(§3.1-4) — 몽타주를 만들면 한계 `NOTIFIES_NOT_ADDED`.
- 순서: 생성 → 포장(플러그인) → 사람 확인 → 승격 → **정식 몽타주에** 노티파이(스킬의 `add_notify` / `add_notify_state` — `build_from_spec` 은 DefaultSlot 몽타주를 새로 만드므로 쓰지 않는다) → GA 지정(데이터, 승인). 후보는 버려질 수 있어 먼저 달지 않는다. rename 은 몽타주 안의 노티파이를 그대로 옮긴다.
- 스킬 문서의 "슬롯 이름 변경 · 다중 섹션 금지"는 Python API 한계였다 → 플러그인 `set_montage_slots` · `set_montage_sections` 로(스킬 문서 정정 2026-10-25).
- 이 환경은 원격 실행(UDP)이 안 돼 노티파이 단계는 Phase 7 테스트 범위 밖이다.

---

## 13. 검증 — `validate_animation`

| 구분 | 항목 | Phase |
| :--- | :--- | :---: |
| 구조 | 애셋 존재·저장 · 타깃 스켈레톤 일치 · 길이·프레임 수·프레임레이트 · 모든 트랙 본이 스켈레톤에 있음 · NaN·비정상 스케일 | 1 |
| 수치 — 절대 | 명백한 깨짐만: NaN · 비정상 스케일 · 한 프레임 회전 > 90°(기존 히어로 애니 관측 최대 약 70°) → `FAILED`. 단 소스가 주어졌고 소스도 그만큼 튀면(소스 최대 + 10° 이내) 리타깃이 만든 깨짐이 아니므로 경고 `ROTATION_JUMP_INHERITED` — 30fps 마켓 공격은 손·손가락이 93~109°/프레임(Phase 1 실측) | 1 |
| 수치 — 상대 | 리타깃 결과 vs 소스: 체인별 각속도 p99 비율 · 착지 발 수평 속도 p50 비율(다리 길이 비 보정) · 루트 이동 거리 비율(펠비스 높이 비 보정) · 루프 경계 차 / 프레임당 중앙값 비율. 허용 범위 밖이면 `PASSED_WITH_WARNINGS`. 허용 비율 초기값은 Phase 1 첫 결과로 정한다 | 1 |
| 회귀 비교 | 같은 소스를 기존 RTG로 리타깃한 결과와 본별 각 차이 — "Tool 결과 = 에디터 수동 절차 결과" 확인 (Phase 1 테스트 전용) | 1 |
| 요청 충족 | 길이·루프 조건 · 요청한 순서(세그먼트 경계) · 제약 충족. Phase 2: `expect{length, loop, root_yaw_delta}` 불일치 → `FAILED`(`EXPECT_*`), `seams[]`(이음매 시각)의 회전 변화가 앞 · 뒤 4프레임 중앙값 중 큰 쪽의 `seam_ratio_max`(3.0)배 초과 → 경고 `SEAM_JUMP`. 구간을 고르는 측정용 `profile_bones[]`(프레임별 본 선속도) — 개정 7 보강 `profile_positions`면 같은 시각의 컴포넌트 공간 위치도(동작 평면 비교) | 2 · 8 |
| 손가락 (개정 8) | `fingers: true \| {ik_rig?, retargeter?, mesh?}` → `fingers{hands[{side, fingers[{chain, mapped, mcp, pip}], order_broken_pct}], unmapped[], thresholds, issues[]}`. 손 기준틀(손목 → 손가락 첫 마디 평균, 검지 − 새끼) 위의 MCP · PIP 굽힘(손바닥 쪽 +). 경고 `FINGER_UNMAPPED_NOT_REFERENCE`(소스 체인 없는 손가락이 **대상 메시** 기준 포즈에서 벗어남 — 꺾인 리타깃 포즈가 모든 프레임에 탄다) · `FINGER_BEND_REVERSED` · `FINGER_OVERBENT` · `FINGER_ORDER_BROKEN`(손끝 검지 → 새끼 순서가 깨진 프레임 비율). `retarget_animations` 는 기본으로 그 리타기터 매핑으로 검사하고 경고면 진단 `FINGER_WARNINGS`. Vesper 원본 57개 경고 0 | 5 |
| 팔-몸통 관통 (개정 8) | `body_clearance: true \| {mesh, ik_rig, upper_arms, body_bones, include_secondary, contact_cm, penetration_cm}` → `body_clearance{arms[{upper_arm, frames_over_contact_pct, frames_over_penetration_pct, depth_p50/p95/max, worst{frame, time, arm_bone, body_bone}}], body{…}, issues[]}`. 관통(기본 깊이 > 2 cm × 펠비스 높이 / 100 — Vesper 2.1 cm, 접촉 1 cm × 같은 배율)이면 경고 `BODY_PENETRATION`. 보정은 §10 | 5 |
| 몸 전체 관통 (개정 14 — 8-4a, 옵트인) | `body_clearance` 의 새 키 `parts: "all"` · `legs` · `per_frame` · `model` — 주지 않으면 개정 13 결과 그대로(비교 대상 16개 `arms[]` · `body` · 상태 · 경고 같음, 실측). `parts`: 팔 부위 3(손 = 손목 본과 자손 · 아래팔 = 팔꿈치 본과 트위스트 · 위팔 = 위팔 본과 트위스트, 어깨 관절에서 위팔 길이 × 0.4 안은 뺀다 — 몸통에 붙은 삼각근, Vesper 9.8 cm) × 몸 부위 6(몸통 칸 `pelvis` · `belly` · `chest` = 몸통 축 t 를 기준 포즈 척추 마디 s1 · s2 의 t 로 나눔 · `thigh_l` · `thigh_r` · `head_neck` = 중앙선 체인(이름 없이 — 위팔 중점 좌우 어깨 반폭 × 0.25 안 · 척추 끝 위)의 가장 낮은 본 → 정수리) 36 쌍, 쌍마다 접촉 · 관통 % · 깊이 p50/p95/max · 첫 접촉 시각 · 최악 {프레임, 팔 · 몸 본, 점}, 경고 `BODY_PENETRATION_PARTS`(parts 일 때만 상태 반영) · info `HEAD_AXIS_SKIPPED`. 정수리 = 기준 포즈에서 머리 축선 5 cm × scale 안 머리 정점의 최대 투영(뿔 · 큰 머리카락 끝 제외 — `head.top_from`), 머리 지도 t −0.1 ~ 1.0(정수리 위 뿔 줄기 밖). `legs`: 넓적다리 · 종아리 점 ↔ 반대 다리 넓적다리(칸 가운데 t ≥ 0.2 — 사타구니는 서 있기만 해도 닿는다) · 종아리(무릎 → 발목 새 축), 경고 `LEG_PENETRATION`. `per_frame`: 쌍별 부호 있는 프레임 깊이(음수 = 틈 cm, 걸리는 칸이 없으면 null). `model`: 측정 점 전부(기준 위치 · 영향 본 ≤ 8) · 측정과 같은 메시 기준 샘플 포즈 · 프레임별 반경 지도(base64) → `anim_gen/body_model.py`(순수)가 같은 규칙으로 깊이를 다시 낸다(8-4b 한 풀이의 바탕 — 재현 차 p95 0.005 cm). `retarget_animations body_clearance` 에는 `per_frame` · `model` 없음(`BAD_REQUEST`). `profile_rotations: true` = profile 위치와 **같은 시각**의 컴포넌트 공간 회전(`profile.rotations{bone: [[x,y,z,w]…]}`) | 8 |
| 손끼리 · 위팔 기준 (개정 14 — 8-4b, 옵트인) | `body_clearance.hands: true` → `parts.hands{hand_bins 12, forearm_bins 14, t_range, tip_local_cm{l, r}, points, pairs[]}` — 팔마다 손 지도(손목 → 손 끝 = 기준 포즈 손 점 무게중심 방향 최대 투영, 손목 로컬로 따라감 · t −0.15 ~ 1.05) · 아래팔 지도(팔꿈치 → 손목 · t −0.1 ~ 1.05)를 **그 팔의** 손 · 아래팔 점으로 만들고(몸 지도와 같은 `FRadialAxis` 규칙 — 공개 `FArmAxes` · `HandTip`), 반대 팔의 손 · 아래팔 · 위팔 점이 묻는다 → 12 쌍(`body_part` = `hand_<반대>` · `forearm_<반대>`), 경고 `HAND_PENETRATION`(hands 일 때만), per_frame · model 지도 `hand_l/r` · `forearm_l/r` · `roles.arms[].hand_tip_local_cm`. 모아 쥔 두 손은 맞닿음(contact_cm)까지 정상 — 풀이는 손끼리 쌍을 '깊이 ≤ contact' 로만 민다. 기본(키 없음)은 결과 그대로. 8-4a 측정에 없던 사용자 Persona 자리(검 선택 f0 손끼리 통과)를 잡는다. **위팔 쌍 기준(총괄 정정):** 운영 애니도 위팔 → 가슴 접촉 42 ~ 100%(겨드랑이 · 옆구리 눌림 · 지도 근사 — Rifle Idle 사용자 눈 '아주 미세' vs 측정 98.1%)라 관통 목표에서 빼고 '점마다 원래 깊이보다 안 깊어짐'(`fix.body.clearance.upper_arm: no_worse`)만 — 판정 = 쌍별 관통 % +1 · 최대 깊이 +0.5 cm 안. 코트 자락(3마디+ 가지 = secondary)은 `include_secondary` 로 재기만(한계 `BODY_FIT_SECONDARY_RECORDED`) | 8 |
| 제약 | 양손 파지 오차 · 무기 궤적 이상. **개정 11(8-1 구현 — `anim_gen/motion_metrics.py`, Kimodo 소스와 Vesper 결과에 같은 정의):** `validate_animation profile_positions` 의 손목 · 엉덩 관절 · 발목 위치로 — 손목 간격(프레임별) · `grip_pct` = 간격 ≤ 20 cm × scale(scale = 펠비스 높이 / 100, 플러그인 관통 · `CLEARANCE_GRIP_CHANGED` 와 같은 기준) 프레임 %, 발 좌우 간격 비 = 발 간격의 엉덩 축 성분 / 엉덩 관절 폭(프레임별 — 몸이 돌아도 좌우만) p50 · p90, 앞뒤 보폭 / 다리 길이(기록), 휘두름 정점 = 빠른 손목 최대 속도 / scale · 시각 · 동작 구간 비율, 비파지 관통 상한 = min(100 − grip_pct, 관통 %) · 최악 프레임이 파지 프레임인가(검증기가 프레임별 관통을 내지 않아 C++ 없이 상한으로). 선별 점수는 `selection.py`(§14 Phase 8). 무기 궤적은 8-4(무기 메시 · 소켓) | 8 |
| 자동 보정 (개정 13) | 흐느적(`timing.py` — Job `timing.before/after`): 휘두름 정점(손목 속도 최대 / scale — select `swing` 과 같은 크기) · 정점 시각 · 정지 머리 / 꼬리 길이(전신 < 30 cm/s) · 길이. 다리(`motion_metrics.legs_report` — 소스 · 대상 같은 정의): 발 좌우 비 p50 · p90 · **두 발 디딘 프레임의 최대**, 접지(`detect_contacts` — 발목이 최저 + 다리 × 0.04 · 수평 속도 < 다리 × 0.25 /s, 4 프레임 이상 — 대상 측정은 대상 발목 트랙으로 다시 판정) 비율 · 접지 발목 수평 미끄러짐 p95(cm/s ÷ scale), 무릎 간격 최소. Blender 보고는 대상 모델 예측 — 리타깃 뒤 실측(Job `fix.target`)과 비교해 모델을 확인한다 | 8 |
| 시각 | 항상 `needs_review[]`에 남긴다(사람이 Persona/PIE에서 확인). 개정 8: `review.render` 가 변환된 **소스 골격**(본마다 기둥, 좌 파랑 · 우 빨강 · 머리 앞 초록 코 · 루트 호박색 막대 · 바닥 띠)을 정면 · 측면 정사영으로 그린 프레임 PNG 와 시트(행 = 시각, 열 = 뷰 + 레퍼런스)를 낸다(Blender Workbench, 카메라는 전 프레임 범위에 고정 — 이동이 보인다). **개정 12(8-2):** `capture_animation` 이 같은 카메라 · 셀 규칙으로 **대상 메시**(Vesper)를 찍은 시트 · 소스 골격 비교 시트(같은 시각 행) · APNG 를 낸다 — Persona 를 열지 않고 채팅에서 본다(SendUserFile). 캡처는 근거이고 판정은 사람이다(§16-9). 칸마다 피사체 픽셀 범위(`subject_px` · `touches_edge` — 잘림 점검)와 행마다 포즈 중심(`pose_center` — 포즈가 바뀌는지)을 기록한다 | 1 · 5 · 8 |

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
- `preview_animation_edits` / `apply_animation_edits`: op 사전(`retime` · `trim` · `mirror` · `offset_bone` · `rotate_root` · `hold_pose` · `concat`, 개정 13 보강에 `time_warp`), 전체 사전 검증 → 원자 적용.

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
| `time_warp` (개정 13 보강 — 8-3 후속) | `knots[[src, dst]…]`, `rates?`, `antialias?`(0 ~ 1.5, 기본 0) | 전체를 매끈한 시각 사상 하나로 — 새 시각 → 원 시각 = 단조 3차 Hermite(`rates` = 매듭 재생 배율, 없으면 PCHIP), 속도 단차 · 새 이음매 없음. 첫 매듭 `[0, 0]`, 마지막 `src` = 길이. `antialias` > 0 이면 1배보다 빠른 곳을 σ = antialias·√(배율² − 1) 프레임 가우시안으로 거른 뒤 고른다 |
| `hold_pose` | `at`, `duration` | `at`의 포즈를 `duration` 동안 정지 삽입(`at` = 끝이면 연장) |
| `concat` | `asset?`(생략 = 원래 `source`), `start?`, `end?`, `reverse=false`, `blend=0`, `align_root=true` | 같은 스켈레톤 구간을 뒤에 붙인다. `blend`초 크로스페이드, 붙는 구간의 루트를 현재 끝 루트의 위치·Yaw에 맞춘다 |
| `mirror` | `axis="x"`, `mirror_table?` | 전체 좌우 반전 |
| `offset_bone` | `targets[{bone, rotation?{pitch,yaw,roll}, translation?}]`, `space=component\|local`, `start?`, `end?`, `blend_in=0.2`, `blend_out=0.2` | 본 회전·이동 오프셋(상체 회전) |
| `bone_deltas` (개정 14 — 8-4a) | `space="parent"`, `bones[{bone, rotation_deg[[x,y,z]…키마다] \| null, translation_cm[[x,y,z]…키마다] \| null}]` | 키마다 본 델타(8-4b 한 풀이의 쓰기) — 회전 벡터(축 × 각°, 부모 공간): 새 로컬 회전 = Q(Δ) · 원래(관절 위치 그대로), 이동 = 원래 + Δ. 정확히 0 인 키는 손대지 않는다. 배열 길이 = 그 op 직전 버퍼의 키 수(아니면 `BAD_OP` — 기대 키 수 포함), \|Δ\| ≤ 180°(`OUT_OF_RANGE`), 없는 본 `BONE_NOT_FOUND`, 중복 · 둘 다 null `BAD_OP`. 이름이 `offset_bone` 의 `local`(본 자신의 축 · 뒤에 곱함)과 반대 뜻이라 `parent` |
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

**진행 (개정 8):** 조사(2026-10-24) → 사용자 Kimodo-SOMA-RP-v1.2 채택 → 설치 항목별 승인 · 설치(§2.2) → 설계 초안 확인 → 커밋 단위 ① `local_ai` Provider ② Blender 프레임 렌더 비교 · 보정 op 자리 ③ 통합 테스트 + 회귀 + 이 개정. ① · ② 뒤 손가락 꺾임을 고치는 과정에서 리타깃 정렬(§2.3 · §10)과 손가락 · 관통 검사(§13)를 플러그인에 더했다.

**구성:**

| 파일 | 내용 |
| :--- | :--- |
| `Tools/mcp/anim_gen/providers/local_ai.py` | `KimodoProvider`: `installed`(정책 경로 + 캐시 4개 저장소) · `plan_generate`(프롬프트 · 프레임 · seed · 샘플 · 후처리 · 제약 → 계획 고정, 제약 파일 루트 · SHA-256, **모델을 띄우지 않음**) · `run`(Popen, 오프라인 환경) · `poll`(report · 샘플 수 · BVH 존재) · `cancel`(종료). SOMA 수동 체인 27개 · 골반 `Hips` · 발 · 예상 BVH 규약 |
| `Tools/mcp/anim_gen/local_ai/kimodo_run.py` | Kimodo venv 의 python 으로 도는 스크립트(서버가 import 하지 않음) — `load_model` · 제약(`load_constraints_lst`, `keep_pose` 는 NPZ 에서 꺼냄) · `seed_everything` · 생성(`num_samples` · `post_processing`) → 샘플별 NPZ + BVH(`motion_to_bvh(standard_tpose=True)` + 루트 트랙) · report.json(종료 코드 0 / 2 알려진 실패 / 3 예외) |
| `Tools/mcp/anim_gen/local_ai/{root_track, constraints}.py` | 순수 Python(pytest): Kimodo BVH `Root` 래퍼에 바닥 궤적 · 방향을 넣고 `Hips` 를 Root 기준으로 / 요청 제약 → Kimodo 제약(`root2d` 등) |
| `Tools/mcp/anim_gen/providers/subprocess_step.py` | 서브프로세스 공통(`blender` 에서 뽑아냄) — 띄우기 · report 대기 · 기한 · 종료 · 로그 꼬리 · 키 이름 환경 변수 제외 |
| `providers/blender.py` · `blender/bvh_to_fbx.py` · `blender/review_render.py` | `plan_convert_generated`(생성 BVH 예상 → 실행 때 측정) · 기준 포즈 FBX · `review.render`(Workbench 프레임 PNG · 시트) · `fix.ops` 자리 |
| `router.py` · `request.py` · `executor.py` · `service.py` · `providers/builtin.py` | 생성 BVH 사슬 · `DEPENDS_ON_BLENDER` · `defaults_from` · 요청 필드 검사 · Job `review` · 2단 임포트 · 재검증(소스 골반 + `body_clearance` + `fingers`) · 관통 보정 진단 |
| 플러그인 C++ (`Plugins/AnimGraphMcp`) | `create_ik_retargeter align_mode`(`Core/AnimMcpRetargetPoseAlign`) · `match_existing` 모든 op 정확 매핑 · `retarget_animations body_clearance` · `fingers` · `validate_animation body_clearance` · `fingers` · `create_ik_rig finger_chain_suggestion` · `inspect_skeleton suggest_finger_chains` · 공유 기하 `Core/AnimMcpSkeletonGeometry` · `Core/AnimMcpBodyClearance` · `Core/AnimMcpFingerChains` · 단위 테스트 `AnimGraphMcp.Generation.BodyClearance` · `FingerChains`. Tool 수는 그대로(39 — 인자 · 결과만 늘었다) |
| `providers.json` · `policy.default.json` · `anim_gen/server.py` · `anim_graph_mcp/server.py` · 플러그인 README | `local_ai` 매니페스트(`license: ok` · 최대 10초 · 출력 bvh) · `paths.kimodo_*` · Tool 설명 |

산출물: `<ImportSourceRoots[0]>/LocalAI/<job_id>/A<n>/{args.json, kimodo.log, report.json, kimodo_00.npz, kimodo_00.bvh}` → `…/Blender/<job_id>/A<n>/{BVH_kimodo_00.fbx, BVH_kimodo_00_Rest.fbx, frames/{front,side}_<프레임>.png, frames/sheet.png, report.json, blender.log}`. UE 이름: `<output_path>/Work/<job_id>/A<n>/Import/BVH_kimodo_00_Rest{, _Skeleton, _Anim}` · `Import/Motion/BVH_kimodo_00` · `IK_Source` · `IK_Target` · `RTG_Retarget` → `<output_path>/<animation_name>`.

**세부 완료 기준 (개정 8 — 위 완료 기준을 Phase 4 형식으로 나눔):**

1. 적법 · 호환 모델 판정 + 사용자 승인(채택).
2. 승인한 모델로 프롬프트 → `/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F`(대상 메시 `SK_StreetDemon_F_01`) `AS_` 저장 + `validate_animation`.
3. 에디터 없이 도는 pytest: Provider Mock(설치 없음 · 성공 사슬 · 실패 · 폴백 · 타임아웃 · 취소 · 제약 · 루트 트랙 · 렌더 비교).
4. 실제 Kimodo · Blender · 에디터 통합(`Tools/mcp/anim_gen_phase5_test.py`).
5. 기존 pytest · Phase 1 ~ 4 통합 테스트 회귀 없음 · 두 구성 빌드 경고 0.

**결과 (2026-10-25, `Tools/mcp/anim_gen_phase5_test.py` 전 섹션 PASS 두 번 — 요약 `anim_gen_phase5_state.json`, 마지막 실행 `P5Run1025_160301`):**

| # | 기준 | 결과 |
| :---: | :--- | :--- |
| 1 | 모델 판정 · 채택 | ✅ [조사](LocalModelSurvey.md)(2026-10-24): 적법 · 호환 후보는 Kimodo-SOMA-RP-v1.2 하나(§2.4) → 사용자 채택 · 설치(§2.2). `list_motion_providers`: `local_ai` 구현 · 설치 · 사용 가능 · `license: ok`, 캐시 모델 커밋 `0e3c890…`, 후처리(`motion_correction`) 설치됨 |
| 2 | 프롬프트 → Vesper `AS_` + 검증 | ✅ "A person walks forward, turns around and walks back." · 6초 · seed 20261025 · `locomotion` · `provider: auto` → 계획: `existing_motion` 제외(`NO_SOURCE_HINT` — 검색 힌트 없음) · `external.meshy` 제외(`PAID_API_DISABLED`) → `local_ai` → `blender` → `retarget`(181프레임 · SOMA 체인 27 · `per_bone` · `body_clearance resolve` 고정). 실행: Kimodo 52.2초(RTX 3080 Ti, 확산 9.8초 · 후처리 켬) → BVH 181프레임 · 루트 이동 660.8 cm · 방향 −189.8° → Blender 3.1초(본 78 · +Y · 바닥 0.5 cm) + 렌더 비교 1.9초 → 2단 임포트(본 78 · 루트 `Root`) → SOMA 수동 체인 IK Rig + Vesper 자동 IK Rig → RTG `match_existing` · `per_bone` → 리타깃 + 관통 보정(관통 프레임 왼/오른 52.5 / 45.3% → 0 / 0, 위팔 최대 13.2 / 11.2°) → **`/Game/Animation/Test/AIAnimation/P5Run1025_160301/AS_Vesper_Kimodo_WalkTurnBackP5` 저장**, 잡 69.6초(첫 실행 107초 — Kimodo 88초). `validate_animation`(소스 골반 `Hips` · 손가락 · 관통): **`PASSED`** — 181프레임 @ 30 · 6.0초(요청 그대로), 각속도 p99 비 0.954 · 골반 높이 1.047 · 착지 발 1.756 · 루트 이동 비 1.000(Vesper 691.8 cm), 루트 Yaw +189.8°(Kimodo θ −189.8° 와 같은 오른쪽 돌기 — UE Yaw + = 오른쪽, Kimodo θ + = 왼쪽), 최대 33.5°/프레임, 손가락 경고 0 · 순서 깨짐 0 / 0%, 관통 0 / 0%. 한계 `FINGERS_STATIC` · `REVIEW_IS_SOURCE_SKELETON`. **같은 seed 로 두 번 실행한 결과가 같다**(Kimodo 루트 660.78 cm · −189.81°, Vesper 691.83 cm · 189.81° — 소수 둘째 자리까지) |
| 3 | pytest (Mock) | ✅ **282건**(Phase 4 189 → 282: `test_local_ai.py` 39 · `test_review.py` 32 · `test_blender` · `test_bvh` · `test_router` · `test_jobs` 추가). 계획이 실행하지 않음 · SOMA 체인이 손가락을 표준 이름으로 매핑 · 요청 체인이 기본값을 덮음 · seed 고정 · 30 fps 아니면 실행 값으로 리샘플 · 제외(프롬프트 · 길이 · 후처리) · 미설치 · `DEPENDS_ON_BLENDER` · 성공 사슬(오프라인 환경 · 인자 · Kimodo → Blender → 리타깃) · 샘플 · `pick` · 예상과 다른 BVH = 경고 · Kimodo 오류 → 폴백 기록 · 보고 없이 종료 · 타임아웃 · 취소 = 종료 · `keep_pose` 파일 고정 · 루트 밖 거부 · `kimodo_raw` 검사 · 재검증 실패 시 리타깃 검증 유지 · 루트 경로 캐릭터 기준 변환 · 오일러 왕복 · 방향 펼침 · 루트 트랙이 월드 포즈 유지 · 다른 BVH 구조 거부 · 정책 경로 검사. 렌더 비교: 요청 형식 · 시각 펼침 · 범위 밖 · 레퍼런스 루트 · 사라진 레퍼런스 · 렌더 실패 = 한계(`REVIEW_NOT_RENDERED`) · 변환 없는 경로 · `fix` 사전 |
| 4 | 실제 통합 | ✅ `state` · `plan`(계획이 Kimodo 를 띄우지 않음 · 애셋 0 · 더티 0 · 거부 5종: 프롬프트 없음 `MISSING_INPUT` · 12초 `DURATION_OVER_MAX` · 7초 제약 `CONSTRAINT_OUT_OF_RANGE` · 보정 op `UNSUPPORTED_FIX_OP` · 루트 밖 NPZ `IMPORT_SOURCE_NOT_ALLOWED`) · `generate`(위 2 + 프레임 PNG 8장 · 시트 1424 × 2078 을 직접 보고 확인 — 앞으로 걷기 → 4초에 뒤로 돎 → 6초에 출발점 근처) · `constraint`(`root_path` 3초에 앞 400 cm · 왼쪽 0 · 방향 180° → Kimodo `root2d` 프레임 90: 끝 루트 앞 397.2 · 왼쪽 1.1 cm · 방향 182.5°(왼쪽으로 돎) → Vesper 루트 프레임 1 → 끝 406.5 · 1.7 cm = Kimodo 388.3 × 1.047(골반 높이 비 — Root Motion op 배율), Yaw Δ −182.0°, 검증 `PASSED_WITH_WARNINGS` — `FOOT_SLIDE_RATIO` 3.86(3초에 4 m + 180° 도는 빠른 동작)) · `cancel`(torch 임포트 중인 실제 Kimodo 프로세스 종료 · pid 사라짐 · report · BVH 없음) · `dirty`(대상 스켈레톤 · 메시 .uasset SHA-256 불변 · 미저장 수 그대로 · `Content/` 변경은 실행 폴더뿐) |
| 5 | 회귀 · 빌드 | ✅ 같은 에디터에서 `anim_gen_phase1_test.py` 113 · `phase2` 62 · `phase3` 34 · `phase4` 27 확인 실패 0 — Phase 1 `RTG_KatanaToH` 대비 본별 0° · 위치 0 cm(플러그인 기본 `engine` 정렬), `AnimGraphMcp.Generation` 4/4(BodyClearance · Edit · FingerChains · Guard) · `AnimGraphMcp.Smoke` 26/26 · `AstralBreak.*` 31/31 · 런타임 시나리오 2/2. Phase 3 · 4 는 테스트 기대값 두 곳을 Phase 5 동작에 맞춘 뒤 다시 돌렸다(아래). Development · DebugGame 빌드 경고 0(C++ 는 리타깃 수정 세션들이 두 구성으로 빌드 · 이 단위의 빌드는 "Target is up to date") |

Phase 4 CMU 수치는 anim_gen 기본이 `per_bone` 정렬 + 관통 보정 + 2단 임포트로 바뀌어 달라졌다(기대된 변화 — 감사 §15): 각속도 p99 비 0.833 → 0.868 · 착지 발 1.513 → 1.444 · 골반 높이 0.975 · 루트 이동 1.299 그대로, 관통 프레임 49.3 / 72.8% → 0 / 0, 잡 9.8 → 27.2초. Trim(`PASSED`, 50.44°/프레임) · 자동 IK Rig(HumanIK 64%)는 그대로.

통합 테스트에서 고친 것(테스트만, 제품 코드 변경 없음): ① `anim_gen_phase3_test.py` 가 `local_ai` 제외 사유를 `NOT_IMPLEMENTED` 로 기대했다 → 구현 뒤에는 이 요청(프롬프트 없음)에서 `MISSING_INPUT`(Kimodo 가 없는 PC 는 `NOT_INSTALLED`). ② `anim_gen_phase4_test.py` 가 소스 애니를 `_Anim` 접미사로 골라 2단 임포트의 기준 포즈 애니(`BVH_01_01_Rest_Anim`, 2프레임)를 소스로 비교해 `FAILED` → `Import/Motion/` 애니 우선(잡 내장 검증은 처음부터 `PASSED_WITH_WARNINGS`). ③ Phase 5 테스트의 기록용 골반 높이 비가 소스 골반 이름 없이 재 105.24 로 나왔다 → `pelvis` 를 주고 다시 실행(1.047).

남은 것: Vesper 메시로 Persona/PIE 눈 확인(부록 B) · 기존 Vesper 애니의 팔-몸통 관통 18 ~ 35%(사용자 결정으로 일괄 보정 안 함 — 부록 B) · `keep_pose` · `kimodo_raw` 제약과 `samples` > 1 은 pytest(Mock)로만 확인 · "Built with Meta Llama 3" 표시 판단(부록 B).

### Phase 6 — 외부 AI (Meshy)

어댑터, 비용 추정(공식 가격을 확인할 수 없으면 승인 단계에서 "미확인"으로 차단), 결과 다운로드·만료 처리, 폴백 통합.

완료 기준:

- 승인된 경우에만 1건을 생성하고, Phase 1 처리를 거쳐 검증한다.
- 승인이 없거나 `FREE_ONLY`이면 외부 호출 0회(요청 로그로 확인).

**진행 (개정 9):** 공식 문서 확인(2026-10-25, §2.4 · 부록 A) → 설계 초안 → 사용자 결정(기본 · 첫 호출 prime, 금액 = 정책 `usd_per_credit`, 약관 수용) → 정정 3건 반영 후 착수(불확실 제출의 목록 기반 자동 채택은 뺌 — 태스크 객체에 프롬프트가 없어 시각만으로는 남의 태스크를 채택할 수 있다 / 요청 로그는 실행기 상태 폴더 / 실제 금액 환산은 제출 때 핸들에 고정한 환율). C++ 변경 없음.

**구성:**

| 파일 | 내용 |
| :--- | :--- |
| `Tools/mcp/anim_gen/providers/meshy.py` | `MeshyProvider`: `estimate(request, policy)`(매니페스트 크레딧 × 정책 환율) · `plan_generate`(본문 고정 · 길이 맞춤 · 모드 · 한계, 네트워크 없음) · `run`(키 · 에디터 · 환율 확인 → 잔액 → 제출, 초당 429 는 `Retry-After` ≤ 5초면 같은 시도에서 한 번 더) · `poll`(Retry-After 간격 · 기한 · FAILED 환불 · 재시도 가능 분류) · 결과 다운로드(인증 헤더 없는 별도 클라이언트 · https · 200 MB · FBX 매직 / `HIERARCHY` · 403 · 404 면 태스크를 다시 읽어 재서명 URL 로 한 번 더) · `cancel`(외부 호출 없음). httpx, 기본 URL 고정, 리다이렉트 안 따름, POST 60초 · GET 30초 |
| `providers/base.py` · `executor.py` · `router.py` · `service.py` | `estimate(request, policy)` · `StepResult.actual_credits` · `RunContext.state_dir`(요청 로그 위치) · 장부 `credits` · Job `cost.credits` · poll 단계 실패의 환불 / 과금(`_settle_failure`) · 후보 `estimated_credits` · 견적 `credits` · `usd_per_credit` · `generation.options` 이름 검사 |
| `policy.py` · `policy.default.json` · `request.py` · `providers.json` · `registry.py` · `server.py` | `external.meshy{usd_per_credit, timeout_seconds}` · `generation.options` · 매니페스트(모드 · 크레딧 · 길이 · 프롬프트 한도 · 보존 3일 · `license: ok` · 약관 요약) · Tool 설명 |
| `tests/test_meshy.py` · `conftest.py` | `httpx.MockTransport` 가짜 Meshy(잔액 · 제출 · 태스크 · 결과 호스트). conftest 가 실제 `HTTPTransport` 를 막는다 |
| `Tools/mcp/anim_gen_phase6_test.py` | 통합 — `hashes` · `state` · `blocked`(완료 기준 ②) · `real`(완료 기준 ① — `--real` 과 터미널에서 plan_id 를 직접 입력해야 승인, 키는 그 셸의 환경 변수만) · `dirty` |

산출물: `<ImportSourceRoots[0]>/Meshy/<job_id>/A<n>/{submission.json, meshy_motion.fbx \| .bvh, task.json(서명 쿼리 뺀 URL)}` · 요청 로그 `<state>/external/meshy_requests.jsonl`(시각 · Job · 시도 · 메서드 · 엔드포인트 · 태스크 · 상태 · ms, 본문은 길이 · 모드 · 프롬프트 SHA-256 만 — 헤더 · 쿼리 없음).

**오류 분류:** 키 없음 `AUTHENTICATION_FAILED API_KEY_MISSING`(계획 제외 · 실행 게이트) · 401 `UNAUTHORIZED` · 403 IP `IP_NOT_AUTHORIZED` · 402 / 잔액 부족 `BUDGET_EXCEEDED INSUFFICIENT_CREDITS` · 403 모더레이션 `UNSUPPORTED_REQUEST MODERATION_BLOCKED` · 400 `BAD_REQUEST` → 모두 예약 해제 후 폴백. 429 → `RATE_LIMITED`(`CONCURRENT_TASKS` · `REQUESTS_PER_SECOND`, 재시도는 승인 `max_attempts` 안에서만). 제출 응답 없음 · 5xx → `GENERATION_FAILED SUBMISSION_UNCERTAIN`(멈춤 · 다시 내지 않음 · 예약 유지). 태스크 FAILED → `GENERATION_FAILED <task_error.code | type>`(환불 = 해제, timeout · service_unavailable · server_error · queue_timeout 계열만 재시도 가능). 결과 만료 · 재서명 뒤에도 못 받음 → `RESULT_EXPIRED`(과금 확정). 형식 · 크기 · https 위반 → `BAD_FORMAT` · `DOWNLOAD_TOO_LARGE` · `INSECURE_URL`. 404 → `TASK_NOT_FOUND`. 기한 → `TIMEOUT`.

**결과 (2026-10-25 — 완료. 완료 기준 ① 은 미실행으로 마감, 사용자 결정):**

| # | 기준 | 결과 |
| :---: | :--- | :--- |
| 1 | 승인된 경우에만 실제 1건 → Phase 1 처리 → Vesper `AS_` + 검증 | ⏸ **미실행** — 사용자 Meshy 계정이 Free 요금제(100 크레딧)다. Meshy API 는 Free 요금제의 생성 요청을 402 로 거절한다(text-to-motion 402 "free plan (paid plan required)" · errors "On the Free plan, most task-creating requests return this" · credits guide "API access requires a paid plan"). 이 기준은 "승인된 경우에만"이라 승인 없는 마감도 기준 안이다. 그래서 **실제 Meshy 응답 형식 · 다운로드 · 출력 리그(본 · 정면 · 단위 · FBX 안 메시 여부) · Vesper 리타깃 결과는 미검증**이다(부록 B). 유료 요금제가 되면 키를 그 셸에만 설정하고 `anim_gen_phase6_test.py --only hashes,state,blocked,real,dirty --real --usd-per-credit <요금제 값>` (승인 화면에서 plan_id 를 직접 입력) — `real` 섹션은 리허설(더미 키 · 비대화형 → 승인 화면 → 호출 0)까지 확인했다 |
| 2 | 승인 없음 · `FREE_ONLY` → 외부 호출 0(요청 로그) | ✅ 실제 에디터 · 더미 키(카나리)로 기본 정책(`PAID_API_DISABLED`) · `FREE_ONLY`(`POLICY_FREE_ONLY`) · 환율 없음(`COST_UNKNOWN`) · 유료 켬 + 승인 없음(`WAITING_FOR_APPROVAL NO_APPROVAL`, 대기 Job poll 도 호출 없음) → 계획 · `generate_motion` · `approve_generation` 거부, 요청 로그 파일 없음 · 장부 0건 · Meshy 결과 폴더 0. 견적: 본문 고정 · 10 크레딧 × $0.02 = $0.20 · `needs_approval` |
| 3 | 어댑터 pytest (HTTP Mock) | ✅ `test_meshy.py` 43건 — 계획(본문 · 크레딧 견적 · 호출 0) · swift 사슬 · blender 없음 · 길이 맞춤 · 제외 6종 · 옵션 이름 · 한계 · 환율 없음 · `FREE_ONLY` / 유료 끔 / 승인 없음 = 요청 0 · 성공(잔액 → 제출 1회 → poll 2 → 다운로드, 장부 reserve → submitted → charge 10 크레딧 $0.20, Job `cost.credits`, 결과 파일 루트 · 서명 쿼리 없는 `task.json` · Authorization 은 API 호스트에만, 요청 로그 5줄) · 키 문자열이 상태 · 결과 · 봉투 어디에도 없음 · 실행 때 키 없음 → 폴백(예약 없음) · 거부 6종(401 잔액 · 401 · 402 · 403 모더레이션 · 403 IP · 400) → 해제 · 폴백 · 잔액 부족 → 제출 안 함 · 잔액 조회 실패는 제출을 막지 않음 · 초당 429 → 기다렸다 같은 시도 · 동시 429 → 새 승인 뒤 `plan#2` · poll 500 / 429 는 실패 아님 · Retry-After 전 요청 없음 · FAILED → 환불 · 폴백 / 재시도 가능 → 새 승인 · 만료 → 과금 · 다운로드 403 → 재서명 1회 · 두 번 실패 → `RESULT_EXPIRED` · HTML → `BAD_FORMAT`(파일 안 남김) · 형식 불일치 · 기한 → `TIMEOUT`(예약 유지) · 404 · 취소 = 요청 없음 · 예약 유지 · 서버 재시작 → 같은 태스크 poll · 응답 없음 / 502 → `SUBMISSION_UNCERTAIN`(다시 내지 않음) |
| 4 | 기존 pytest · Phase 1 ~ 5 통합 회귀 | ✅ pytest **325건**(기존 282 + 43, 기존 기대값 1곳 갱신 — `external.meshy` 가 이제 구현됨). 같은 에디터에서 `anim_gen_phase1_test.py` · `phase2` · `phase3` · `phase4` · `phase5`(실제 Kimodo 2건) 실패 0 — Phase 5 수치는 개정 8 과 같다(각속도 p99 비 0.954 · 루트 691.83 cm · Yaw 189.81°, 같은 seed). C++ 변경 없음 — 빌드 생략. `real` 섹션 리허설(더미 키 · 비대화형): 승인 화면(본문 · 10 크레딧 × $0.02 · 사슬 · 위험) → plan_id 미입력 = 호출 0 |

### Phase 7 — AnimBP 연결 · 승격

기존 Tool 조합 + `promote_animation`.

**진행 (개정 10):** 엔진 소스 대조(AssetRenameManager · MessageDialog) → 설계 초안 → 사용자 결정 3건(① 기존 쓰기 Tool 옵트인 `generation_guard` ② 승격 실제 이동 테스트 폴더 `/Game/Animation/Hero/Vesper/_P7PromoteTest/`(끝나고 목록 확인 후 휴지통) ③ **운영 AnimBP 실제 적용은 완료 기준에서 제외** — 미리보기 · revision · 복제본 검증 · 메커니즘까지) → "추천안으로 착수"(2026-10-25) → 구현 → 스파이크(rename 실측 · `ABP_Hero_Combat` 복제 더티 · 복제본 시나리오) → 통합 · 회귀.

**시그니처:**

```
promote_animation(assets[{source, dest}], dry_run=false, confirm=false, allow_referencers=[])   # 플러그인 C++ — Tool 39 → 40
<create_anim_montage | set_montage_sections | create_blendspace | set_sequence_additive | duplicate_animation_blueprint | apply_graph_operations>(…, generation_guard=false)
plan_motion_generation(request{…, package?, integrate_anim_bp, anim_bp?})   # anim_gen — 단계 package_* · anim_bp_test · anim_bp_prepare
```

**구성:**

| 파일 | 내용 |
| :--- | :--- |
| `Plugins/AnimGraphMcp/…/Core/AnimMcpPromote.{h,cpp}` · `Tools/AnimMcpTools_Promote.cpp` | `promote_animation` — 요청 파싱 · dest 규칙(`ValidateDest`) · 내용 해시(`ContentHash`) · 참조자 분류 · 네이티브 CDO 하드 참조 사전 검사 · `RenameAssets`(unattended) · 저장 패키지 추적(`PackageSavedWithContextEvent`) · 리디렉터 fixup · 옛 파일 · 해시 · 참조(저장 파일 재스캔) · 더티 / 저장 집합 검사 |
| `Core/AnimMcpGeneration.{h,cpp}` | `FSettings::PromotionPaths` · `NormalizePromotionPaths`(겹침 · 마운트 루트 무시) · `IsUnderAnyPrefix` · `IsPromotionPathAllowed` · `DescribeSettings.promotion_paths` · `FDirtyGuard` 추가 허용 집합 · `FWriteGuard`(옵트인 가드) |
| `Tools/AnimMcpTools_{Montage, Assets, Sequence, Graph}.cpp` · `Core/AnimMcpOperations.{h,cpp}` | 6개 Tool 에 `generation_guard` — 핸들러 첫 줄 스냅샷 → 경로 · 덮어쓰기 → 작업 → 저장 직전 `Check` → `guard{}`. `Apply` 는 컴파일 뒤 · 저장 전 |
| `Bridge/AnimMcpTypes.{h,cpp}` · `AnimGraphMcpEditor.Build.cs` · `AnimGraphMcpEditorModule.cpp` · `Config/DefaultEngine.ini` | `PROMOTE_FAILED`(400) · 의존 모듈 `AssetTools` · Tool 등록 · `+PromotionPaths=/Game/Animation/Hero/` |
| `Tests/AnimMcpGenerationTests.cpp` | `AnimGraphMcp.Generation.Promote` · `.WriteGuard`(쓰기 Tool 6개를 로컬 디스패처로 — 애셋을 만들지 않는다) |
| `Tools/mcp/anim_graph_mcp/server.py` | 6개 함수 `generation_guard: bool = False` · 새 `promote_animation` |
| `Tools/mcp/anim_gen/providers/integrate.py` | `PackagePipe`(additive · 몽타주 · BlendSpace) · `AnimBpPipe`(복제본 검증 — 시나리오 비동기 poll · 운영 미리보기 · 적용 페이로드) · `promotion_proposal` |
| `anim_gen/{request, router, executor, envelope, registry, service, server}.py` · `providers/base.py` · `providers.json` | 요청 `package` · `anim_bp` · 자리표시 · 단계 결합(`_integrate` — 계획 안 1회) · `StepResult.deliverables` · `INTEGRATION_FAILED`(details) · Job `package` · `anim_bp` · `promotion` · 비동기 대기 전 복제본 기록 · 파이프 2개 |
| `anim_gen/tests/test_integrate.py` · `conftest.py` · `test_router.py` | pytest 41건 · FakeEditor 에 포장 · AnimBP · 스모크 · 시나리오 흉내 · 기존 기대값 3곳(Provider 목록 · `ANIM_BP_NOT_INTEGRATED` 폐지) |
| `Tools/mcp/anim_gen_phase7_test.py` | 통합 — hashes · plan · chain_bs · chain_montage · independent · guard · apply_mech · promote · dirty |

완료 기준 (설계 확정본 §9):

1. 생성 → 몽타주/BlendSpace → (요청 시에만) AnimBP 연결을 독립 · 연속으로 실행하고, 스모크 · `run_anim_scenario` 로 재생 · 전이를 확인한다.
2. 애셋만 요청하면 AnimBP 를 수정하지 않는다(읽지도 않는다).
3. 승격은 원본(내용) 무변경 · 리디렉터 0 · 참조 유지.
4. 운영 AnimBP 는 미리보기 · revision 까지 — 적용은 사용자 승인 사항(§12 절차).
5. 회귀 없음 — pytest · Phase 1 ~ 6 통합 · `AnimGraphMcp.Smoke` · `AstralBreak.*` · Development · DebugGame 빌드 경고 0.

**결과 (2026-10-25 — `anim_gen_phase7_test.py` 실패 0 · 체크 85, 56.6초):**

| # | 기준 | 결과 |
| :---: | :--- | :--- |
| 1 | 독립 · 연속 연결 + 재생 · 전이 | ✅ **연속 B(chain_bs)**: Vesper 걷기 `retime 1.25` → `BS_Vesper_Common_WalkFastP7`(생성물 @300 + `AS_Vesper_Rifle_Idle` @0) → `ABP_McpRuntimeTest` 복제본의 Run 상태 SequencePlayer 를 BlendSpacePlayer(`$blendspace`, X ← Speed)로 교체 → 컴파일 0/0 · 스모크 통과 · 시나리오 Speed 300 → `Run`(+ 복제본 Speed 0 → `Idle`), 잡 5.9초. **연속 C(chain_montage)**: `AS_Vesper_Rifle_Recoil` concat ×3(0.70초) → additive `LocalSpaceBase`/`LocalAnimFrame 0` · UpperBody `Loop → Loop` 몽타주 → `ABP_Hero_Combat` 복제본 `slots_active[UpperBody]` 참 · 운영 미리보기 valid, 잡 7.1초. **독립(independent)**: 유지한 Kimodo 칼 애셋 재사용(새 시퀀스 없음 · 원본 SHA-256 불변) → DefaultSlot 몽타주 → `ABP_Hero_Combat` 복제본 `slots_active[DefaultSlot]` 참, 잡 5.6초. 플러그인 Tool 직접 호출도 같은 가드(guard 섹션) |
| 2 | 애셋만 = AnimBP 무변경 | ✅ 계획 단계에 `anim_bp_*` 없음 · 운영 revision 불변(통합) · AnimBP Tool 호출 0(pytest FakeEditor 호출 기록) |
| 3 | 승격 원본 무변경 · 리디렉터 0 · 참조 유지 | ✅ `_P7PromoteTest/P7Run…/` 로 4개(BS → 샘플 시퀀스 → 몽타주 + 시퀀스 한 배치): 내용 해시 같음 · 리디렉터 0 · 옛 .uasset 없음(엔진이 지움 — `removed_files` 0) · 레지스트리에 옛 경로 애셋 없음 · 복제본 ABP 파일이 새 BS 경로를 담고 옛 경로는 없음 · BS 샘플 · 몽타주 세그먼트가 새 시퀀스를 가리킴 · 복제본 재컴파일 0 오류. BS 1개 0.59초. dry_run 거부 사유 10종(`MISSING_CONFIRM` · `SOURCE_NOT_CANDIDATE` · `UNSUPPORTED_CLASS` · `DEST_IS_CANDIDATE_PATH` · `OUTSIDE_PROMOTION_PATHS` · `DEST_PROTECTED` · `DEST_EXISTS` · `DEST_NOT_ASSET_PATH` · `DUPLICATE_DEST` · `REFERENCER_DIRTY`) + 후보 밖 참조자(승격한 BS → 그 샘플) 거부 → `allow_referencers` 통과. 맵 참조 · CDO 참조는 이 프로젝트에 해당 애셋이 없어 통합에서 재현하지 않았다(코드 경로 · 사유만) |
| 4 | 운영 AnimBP = 미리보기 · revision | ✅ 운영 4개(`ABP_Hero_Combat` · `ABP_HeroLayers_Rifle` · `ABP_Hero_Base` · `ALI_HeroCombat`) · 스켈레톤 · `ABP_McpRuntimeTest` · 소스 4개 SHA-256 전후 같음 · revision 불변. 적용 페이로드 `{asset_path, operations, expected_revision, compile}` · 복제본에 낡은 `expected_revision` → `REVISION_MISMATCH` 무변경, 맞는 revision → 적용(같은 메커니즘). 가드 켜면 운영 AnimBP · 운영 시퀀스 · 운영 몽타주 쓰기 거부(`OUTPUT_PATH_NOT_ALLOWED`) |
| 5 | 회귀 없음 | ✅ pytest **366건**(기존 325 + `test_integrate.py` 41, 기존 기대값 3곳 갱신 — Provider 목록 2 · `ANIM_BP_NOT_INTEGRATED` 폐지 1) · Automation `AnimGraphMcp.Generation` 6/6(새 `.Promote` · `.WriteGuard`) · 같은 에디터에서 `anim_gen_phase1` · `phase2` · `phase3`(Provider 수 기대값 7 → 9 갱신 후) · `phase4` · `phase5`(실제 Kimodo 2건 — 각속도 p99 비 0.954 · 루트 691.83 cm · Yaw 189.81°, 개정 8 과 같다) · `phase6`(외부 호출 0) 실패 0 · `AnimGraphMcp.Smoke` 41/41 · `AstralBreak.*` 31/31 · Development · DebugGame 빌드 코드 경고 0(UBT 의 "VS 2022 not a preferred version" 안내만) |

**스파이크 실측 (2026-10-25):** rename — BS 1개 0.61초 · 저장 = 새 패키지만 · 리디렉터 0 · 옛 파일 없음 · 시퀀스 승격(참조자 BS · 몽타주)은 그 둘까지 저장. `ABP_Hero_Combat` 을 `generation_guard` 로 복제하면 새로 더티 = 복제본 1개(ALI · 공급자 ABP 무변경), 컴파일도 추가 더티 없음. 복제본 시나리오: PIE 10프레임 ≈ 0.47 ~ 0.57초 — 0.23초 반동 몽타주는 5프레임 뒤 끝나 슬롯이 꺼진다(루프 섹션이면 활성).

### Phase 8 — 품질 · 세그먼트

세그먼트 생성·연결, 손 IK·무기 파지 보정(`control_rig`), 프리뷰 프레임 캡처, 다양한 스켈레톤.

**로드맵 (개정 9 — 2026-10-25 사용자 합의, 상세 시그니처 · 완료 기준은 착수 때 개정 10):** 목표는 "AI 가 품질을 최대한 끌어올리고, 사람은 결과를 보고 판정 · 말로만 지시한다"(사람이 키를 직접 만지는 애니메이터 작업이 아니다 — 남는 수작업은 출시용 핵심 동작처럼 기준이 아주 높을 때의 선택지). 지시는 Claude Code 가 편집 · 보정 op 로 바꿔 원본을 둔 채 새 애셋으로 적용한다(§16-9 — 시각 판정은 사람). 단위마다 설계 확인 → 구현 → 검증 → 사용자 판정, 효과 대비 비용 순서.

| 단위 | 내용 | 겨냥하는 문제 | 무게 |
| :--- | :--- | :--- | :--- |
| 8-1 생성 품질 (개정 11 — 구현 · 검증, 아래) | 요청 제약 플래그(`two_hand_weapon_grip` · `foot_contact`)를 생성 제약(Kimodo 손 · 발 end-effector · `root_path`)으로 자동 변환 · seed 별 후보 여러 개 생성 · 수치 자동 선별(양손 간격 · 발 간격 · 휘두르는 손 속도 정점 · 관통 · 깨짐 — `validate_animation profile_positions` 측정) · 팔-몸통 관통 보정이 양손 파지를 깨지 않게(양손 무기면 보조 손 팔 보정 제한 또는 측정만) | 처음부터 덜 틀린 동작 | Python 위주 |
| 8-2 Vesper 캡처 (개정 12 — 구현 · 검증, 아래) | 리타깃 결과를 **대상 메시 모습**으로 찍은 프레임 시트 · 짧은 영상(지금 `review.render` 는 변환된 소스 골격) — Persona 를 열지 않고 채팅에서 판정 | "보고 말하기" 단계의 근거 | C++ 조금(에디터 캡처) |
| 8-3 자동 보정 (개정 13 — 구현 · 검증, 아래) | 휘두르는 구간 자동 탐지(손 속도) 후 가속(`retime`) · 정지 머리/꼬리 트림 — 리타깃 뒤 대상(모든 경로) · blender `fix.ops` 사전 채우기: 발 고정 · 발 간격 좁히기(IK, 발 접지 유지 — 리타깃된 다리의 모델로 풀이) · 스무딩 | 넓은 다리 · 흐느적거림 · 발 미끄러짐 | Blender 스크립트 + Python + C++ 1곳(비교 칸 루트) |
| 8-4 대상 쪽 보정 — 몸 전체 관통 · 무기 파지 (범위 보강 2026-10-26 밤, 사용자 제안 — 아래 근거. 개정 14: 총괄 설계 확정 — 4단위 a → b → c → d, **8-4a 기반 구현 · 검증**, 아래) | 리타깃이 끝난 **대상(Vesper) 애니 위에서** 한 풀이로: ① 몸 전체 자기 관통 — 특정 부위(손-손잡이 · 팔-몸통)만이 아니라 손 · 아래팔 · 위팔 ↔ 머리 · 목 · 몸통 · 가슴 · 골반 · 넓적다리(필요하면 다리끼리 · 양손끼리)를 대상 메시 기준으로 밀어낸다 ② 무기 파지 — 손 IK 로 손을 무기 손잡이 · 소켓에 붙인다(무기 정보는 요청이 무기 메시 · 소켓으로 준다, §8). 파지 · 발 접지 · 원래 동작을 제약으로 함께 지킨다(부위별로 차례로 고치면 서로 깬다 — E1: 위팔만 돌린 `resolve` 가 양손을 벌렸다). 수단 `control_rig`(UE Control Rig 베이크) 또는 Blender IK — 지금 Blender `fix.ops` 자리는 리타깃 **전** 소스 골격이라 대상 체형에서 커지는 관통을 못 본다(Vesper FBX 입력이 필요). 측정은 지금 지표(`body_clearance` · `head_near` · `arm_cross` · `hand_contact`)를 한 원천으로 넓혀 쓴다. 생성 애니만이 아니라 기존 Vesper 애니에도 쓸 수 있다. 착수 때 설계에서 ① · ② 를 나눌지 정한다. ③ (8-3 후속에서 넘김 — 사용자 결정 2026-10-27) 펴진 다리의 무릎 떨림 — 8-3 다리 보정(`fix.ops` 간격 전환 · 발 고정 블렌드)이 공중 발 경로에 만드는 엉덩 → 발목 거리 꺾임이 거의 편 무릎을 흔든다(검 선택 `P81Run1026_180733` 다리 보정본 0.5 ~ 0.57초 오른 무릎, 떨림 0.56 → 1.89 > 기준 1.56). 대상 쪽 풀이에서 발 접지를 제약으로 지키면서 공중 발 경로를 디딤 사이 매끈한 곡선으로 다시 짠다 — 8-3 안에서의 블렌드 5 · 7 프레임 · 공중 보정량 스무딩 · C2 블렌드 · 최소 굽힘 25° 는 줄이지 못했다(§14 '8-3 후속') | 몸 관통 · 머리 관통 · 양손 무기 완성도 · 펴진 다리 무릎 떨림 | 가장 무겁다 |

세그먼트 생성(준비 → 베기 → 복귀를 따로 만들어 연결)과 다양한 스켈레톤은 8-1 ~ 8-4 결과를 보고 필요하면 뒤에 붙인다. Phase 7(AnimBP 연결)은 2026-10-25 먼저 끝냈다(개정 10).

**8-4 범위 보강 근거 (2026-10-26 밤 — 낫 정정 뒤 사용자 Persona: "팔이 머리를 약간 통과하고 배 · 가슴도 약간 통과한다"):** 관통은 한 부위 · 한 동작의 문제가 아니다. 사례(Vesper 측정 — 지표 정의는 §14 Phase 8 '8-1 낫 정정'):

| 사례 | 부위 | 수치 | 원인 쪽 |
| :--- | :--- | :--- | :--- |
| 낫 정정 선택 `P81Run1026_192547/AS_Vesper_Sickle_KimodoSlashPick`(seed 28) — 8-1 상한 안이라 통과했지만 눈에 보인다 | 손 → 머리 · 목 | 5 / 120 프레임(1.53초부터) 머리 본 10 cm 안, 최소 3.0 cm | 소스에서도 4.8 cm 까지 → Vesper 에서 3.0 cm(체형 차가 키움) |
| 같은 애니 | 왼 아래팔 → 배(`spine_01`) | 8 프레임(6.6%), 최대 7.4 cm(2.43초) | 양손으로 자루를 몸 앞에 쥔 자세 |
| 같은 실행 seed 27 | 손 → 머리 | 55.8% 프레임, 최소 1.4 cm | 1차 생성부터 손이 머리 2.5 cm(소스 15.7%) — 리타깃이 키움 |
| 같은 실행 seed 25 · 26 | 팔 → 몸통 | 55.4 · 70.2% | 자루 파지 자세 |
| 검 기준 선택(8-1 E2 · 수정안 A · B · C) | 모은 양 아래팔 → 가슴(`breast_r` · `spine_02`) | 72 ~ 84% 프레임, 최대 6.3 cm | 손잡이를 가슴 앞에 모은 자세 |
| 이전 낫(축 결함, `P81Run1026_184807`) — 원인은 고쳤지만 실패 모양의 기록 | 팔 꼬임 · 손 → 머리 · 팔 → 몸통 | 91.7 · 41.7 · 75.2% | 파지 목표 축(8-1 정정) |
| 운영 Vesper 애니(사람이 만든 것) | 팔 → 몸통 · 옷 | Neutral Walk/Run · Rifle Idle 18 ~ 35%, 운영 낫 0 ~ 34.4% | 다른 체형에서 리타깃 · 옷 부피(부록 B) |

공통점: ① 리타깃이 체형 차(Vesper 팔 47.7 vs SOMA 55.9 cm · 어깨 반폭 12.0 vs 17.3 cm · 가슴 · 옷 부피)로 손-몸 거리를 바꾼다 — 소스에서 피한 것이 대상에서 닿는다(FK 는 양손 간격도 × 0.79) ② 생성 모델은 무기 · 몸 부피를 모른다 ③ 지금 보정은 부위 하나씩이다 — `body_clearance resolve` 는 위팔만 돌려 양손을 벌리고(E1), 머리는 재기만 하고(`head_near`) 고치지 않는다, Blender `fix.ops` 는 소스 골격 단계. → 8-4 는 대상 메시 기준 몸 전체 관통을 파지 · 접지와 함께 한 풀이로 보정한다. 완료 기준은 착수 때 이 사례들(같은 애셋)을 전후 비교 대상으로 정한다 — 수치와 함께 사람 Persona 판정.

**근거 — Kimodo 칼 휘두르기 시험 (2026-10-25):** "A person holds a sword with both hands, raises it over the right shoulder, slashes diagonally down to the left, then returns to a fighting stance." · 4초 · seed 20261025 · `weapon_action` · `provider: local_ai` → `/Game/Animation/Test/AIAnimation/KimodoSword1025_185815/AS_Vesper_Sword_KimodoSlash`(저장, 사용자 확인용으로 유지). 잡 98.5초(Kimodo 80초). 자동 검증 `PASSED`(121프레임 · 최대 44.6°/프레임 · 관통 0 · 손가락 경고 0). **사용자 Persona 판정: 다리가 많이 벌어지고 베기가 흐느적거린다.** 원인 측정:
- 넓은 다리 = Kimodo 원본 동작 자체(소스 골격 렌더 시트 0.8초 큰 내디딤, 1.6 ~ 4초 넓은 자세 유지) — 리타깃은 다리 각도를 그대로 옮긴다
- 양손 파지 없음 = 생성 모델이 무기 없이 몸만 만든다(손이 붙지 않음 · `FINGERS_STATIC`)
- 우리 후처리 영향 가능성 = `body_clearance resolve` 가 **왼 위팔을 98.3% 프레임에서 최대 15.5° 바깥으로** 돌렸다(관통 프레임 39.7% → 0) — 양손으로 모아야 할 팔을 벌렸을 수 있다(가설: 같은 seed · `body_clearance: measure` 비교로 확인 — 8-1 첫 실험)
- 휘두르는 구간이 짧고 나머지는 자세 유지 — 4초 중 동작 구간 비율이 낮다(8-3 의 구간 탐지 · 가속 · 트림 대상)
- 상대 각속도 p99 비 0.688 은 공통 본 3개 기준이라 근거로 쓰지 않는다
- **사전 측정(8-1 설계, Kimodo 원본 NPZ):** 양손 손목 간격 최소 45.8 · p50 64.6 cm(20 cm 안 0%) · 발 좌우 간격이 엉덩 관절 폭의 4.45(p50) · 4.81(p90)배 · 오른손 옆 파지 목표는 왼 어깨에서 82.6 cm(왼팔 55.8 cm — 도달 0%) · 오른손 정점 543 cm/s(0.83초), 정점 50% 이상 20% 프레임
- **E1 판정(8-1 첫 실험, 2026-10-26):** 파지가 처음부터 없었다 — 같은 seed 를 `measure` 로 만들면 Vesper 손목 간격 최소 36.5 · p50 51.0 cm(20 cm × scale 안 0%), `resolve` 는 간격을 p50 1.9 cm 더 벌렸을 뿐 깨진 파지 프레임 0(§10). 같은 seed 결정성 확인(관통 39.7% · 3.5 cm 같음)

#### 8-1 생성 품질 (개정 11 — 2026-10-26 구현 · 검증)

**진행:** 설계 확정본(공유 노트 `phase8-1-design.md`) 사용자 승인 → 사용자 결정 ① 관통 A안(파지 플래그 = 측정만, Python 만) + ② 비파지 관통 기록 지표 ③ 파지 목표 기본 `meet`(`lead` 는 비교) ④ 발 간격은 고르기만(좁히기는 8-3) ⑤ 8-1 만 ⑥ 수치 선별은 근거와 함께 보이고 시각 판정은 사람 → E1(제품 코드 무변경, 통합 `exp1`) → 순수 모듈 + pytest → Kimodo 스파이크(제약 형식 정정 — 아래) → Provider · 라우터 · select → E2 · E2' · E3 + 회귀. C++ 변경 없음, MCP Tool 추가 · 변경 없음.

**시그니처(요청 · 계획 · 결과):**

```jsonc
"constraints": { "two_hand_weapon_grip": true, "foot_contact": true },
"generation": { …, "candidates": 4,
  "refine": { "mode": "auto", "grip": { "lead_hand": "right", "target": "meet", "spacing_cm": null, "from_s": null, "to_s": null }, "keyframe_step": 3 },
  "select": { "weights": { "grip": 3, "stance": 2, "swing": 2, "clearance": 1, "breakage": 1 } } }
// 계획 generate.inputs: seeds[] · candidates · refine{mode, passes 1|2, rules[{flag, kimodo, frames, target, lead_hand, spacing_cm, spacing_from, reach}], keyframe_step, flags}
//                       · metric_window · diffusions · timeout_s (= 정책 + 25 × (확산 − 1)) · timeout_extra_s
//   보강 4 — 자루 무기 간격이 있으면 규칙에 spacing_cm(= 생성 간격 — 러너가 읽는다) · target_spacing_cm · band_cm(소스 띠) · target_band_cm · spacing_map
// 계획 select.inputs: candidates[{index, seed}] · metrics · weights · thresholds · metric_version · grip_on · swing_on · grip_window_s · bones{from, hand_l …, arm_dims} · body_clearance
//   보강 4 — grip_spacing{from, source_cm, target_cm, tolerance_cm{source, target}, source_band_cm, target_band_cm, map{source_shoulder_cm, target_shoulder_cm, arm_ratio}}
// Job: selection{metric_version, weights, thresholds, best_swing_cm_s, bones, body_clearance, retargeter,
//                candidates[{index, seed, source, asset, status, metrics{grip, stance, swing, clearance, non_grip, breakage}, penalties, score, rank, excluded}],
//                picked{index, seed, score, reason}} · cursor.values.generated.candidates[{index, seed, bvh, npz, pass1_npz, source_metrics{pass1, pass2}, refine{constraints, follow, grip, foot}}]
```

**구성:**

| 파일 | 내용 |
| :--- | :--- |
| `Tools/mcp/anim_gen/local_ai/refine.py` | 순수 Python — 프레임(키 프레임 · 파지 구간 · 접지 구간 ≥ 4 · 요청 제약이 고정한 부위 건너뛰기) · 계획 규칙(`plan`) · 팔 2본 IK(`two_bone`, 1차 팔꿈치 굽힘 평면 유지) · `meet` 최소 평행 이동(구 교집합 해석해 — 보조 어깨 쪽 → 어깨 중점 쪽 → 가장 가까운 곳) · `solve_grip`(주 손 너클 축 · 간격, 손 회전 = 새 아래팔 × 1차 손목 로컬 — keep, 수정안 B. 처음 규칙 = 보조 손 '손목 → MiddleEnd' 를 주 손에 맞춘 최소 회전, 손 끝 관절 강체) · 2차 출력 스무딩(`gaussian_kernel` · `smooth_series` · 쿼터니언 부호 연속 `smooth_rotations` — 수정안 A) |
| `Tools/mcp/anim_gen/motion_metrics.py` | 순수 Python — 손목 간격 · `grip_pct` · 발 좌우 비 · 앞뒤 보폭 · 휘두름 정점 · 동작 구간 · 비파지 관통 상한(§13). 버전 2(수정안 C): 궤적 폭 · 손 들기(`attack`) · 떨림(`zigzag`) · 손목 굽힘(`wrist_bend`) · 접지 발 미끄러짐(`contact_slide`), 역할에 어깨 · 팔꿈치(· 중지 첫 마디). Kimodo 쪽(m · y-up)과 Vesper 쪽(cm · z-up)이 같이 쓴다 |
| `Tools/mcp/anim_gen/selection.py` | 순수 Python — 벌점 · 점수 · 순위 · 근거 한 줄 · 가중치 검사(아래 표 — 수정안 C 뒤 표는 '수정안 A · B · C' 절) |
| `local_ai/kimodo_run.py` | 후보 경로(`candidates_mode`): seed 마다 1차 → 77 → SOMA30 FK → `refine` → 일반 EE · root2d 제약 → 같은 seed 2차 → 계획 σ 로 2차 출력 스무딩(77 관절 FK, 수정안 A), 1차 NPZ(`kimodo_<n>_pass1.npz`) · 소스 수치(1차 · 스무딩 전 2차 · 2차) · 제약 추종(목표 손목 · 접지 발 · 루트 차) 기록. 기존 경로는 그대로 |
| `providers/local_ai.py` · `request.py` · `router.py` | 요청 `candidates` · `refine` · `select` 검사 · 계획 규칙 · seed 목록 · 기한 · 한계 교체 · `REFINE_WITH_SAMPLES` · `FOOT_CONTACT_WITHOUT_POSTPROCESS` · select 단계 삽입 · 처리한 플래그의 한계 빼기 |
| `providers/builtin.py` | `body_clearance` 기본값 결정(모든 Provider) · `plan_select`(측정 본 = 대상 템플릿 체인) · 후보 임포트(`Import/Motion/C<번호>/`) · `_rigs`(select · 최종 리타깃 공유) · `_select` · `candidate_metrics` |
| `providers/blender.py` · `blender/bvh_to_fbx.py` | 후보 BVH 를 한 Blender 실행으로(`items` — 기준 포즈 FBX 는 첫 후보만, 렌더 비교는 `frames/c<번호>/`) |
| `executor.py` · `service.py` · `providers/base.py` · `subprocess_step.py` · `meshy.py` · `server.py` | Job `selection` · `RunContext.steps` · 기한 연장(`extra_timeout_s`) · Meshy 무시 설정에 `candidates` · `refine` · Tool 설명 |
| `tests/test_refine.py` · `test_select.py` · `conftest.py` · `test_local_ai.py` · `test_blender.py` · `test_meshy.py` | pytest 40건 추가(순수 모듈 15 · 요청 · 계획 · 라우터 · 실행 25) · FakeEditor profile · 관통 · 이름 규칙 · 빈 폴더 임포트 흉내 · 가짜 Kimodo 후보 · 가짜 Blender items |
| `Tools/mcp/anim_gen_phase8_1_test.py` | 통합 — hashes · exp1 · plan · refine · lead · select · e3 · dirty, 요약 `anim_gen_phase8_1_state.json` |

**설계 정정 (Kimodo 소스 · 스파이크 실측 — 감사 §18):**
1. 손 · 발 제약 = **일반 end-effector**(`EndEffectorConstraintSet(joint_names=[LeftHand, RightHand])` · `[LeftFoot]` · `[RightFoot]`) + `root2d`. Kimodo 후처리는 고정 마스크를 클래스 이름(`left-hand` · `left-foot` …)으로만 만들고 목표를 제약의 회전 FK + 매끈한 루트로 다시 계산한다(`postprocess.extract_input_motion_from_constraints`) — `left-hand` · `right-hand` 로 고정하면 처음 · 끝 12프레임이 1차 손 간격으로 되돌아가고(810 cm/s 순간 이동), 발을 고정하면 미끄러진다(p95 34 ~ 45 cm/s). 일반 EE 면 확산이 따르고 후처리는 표준 접지 정리만 한다.
2. 제약 포즈는 팔 2본 IK 로 FK 와 맞춘다(손 회전 · 손 끝 위치가 팔과 어긋나지 않는 실제 골격 포즈).
3. 발 좌우 비 벌점 폭 2.5 → 5.0(Vesper 비 포화).
4. 후보 임포트는 후보마다 빈 하위 폴더(`import_animation_file` 은 빈 폴더만 — 첫 4후보 실행이 `DEST_NOT_EMPTY` 로 실패해 정정, FakeEditor 도 같은 검사).

**선별 점수 (`selection.py`, 첫 값 — 사용자 소견 뒤 수정안 C 로 바꿨다, 지금 표는 아래 '수정안 A · B · C' 절):** score = Σ wᵢ·pᵢ / Σ wᵢ(0 = 좋음, 낮은 쪽 · 동률은 낮은 번호). 원 수치는 Job 에 다 남긴다.

| 지표 | 벌점 pᵢ | 가중치 |
| :--- | :--- | :---: |
| 양손 파지 | 1 − grip_pct / 100 | 3 (`two_hand_weapon_grip` 일 때만) |
| 발 간격 | clamp((Vesper 발 좌우 비 p90 − 2.5) / 5.0, 0, 1) | 2 |
| 휘두름 정점 | 1 − 정점 / 후보 중 최고(상대) | 2 (`weapon_action` 일 때만) |
| 관통 | 보정 전 관통 % / 100 (팔 중 큰 쪽) | 1 |
| 깨짐 | `FAILED` = 제외 · `PASSED_WITH_WARNINGS` = 0.5 · `PASSED` = 0 | 1 |

**8-1 완료 기준:**

1. 플래그 변환 — local_ai 계획이 `two_hand_weapon_grip` · `foot_contact` 를 Kimodo 2차 생성 제약(양손 · 발 end-effector · root2d 의 규칙 · 프레임 · 목표)으로 모델을 띄우지 않고 보이고, 실행 결과를 소스와 Vesper 양쪽에서 잰다: 파지 구간 손목 간격 ≤ 20 cm × scale 프레임 ≥ 80%, 접지 구간 발 위치가 1차와 같다(수치).
2. 후보 · 선별 — N 후보를 한 Kimodo 실행으로 만들고 전부 Vesper 리타깃 · `validate_animation profile_positions` · `body_clearance` 로 재서 점수로 하나를 고른다. Job `selection` 에 후보별 수치 · 벌점 · 순위 · 근거, 같은 기록으로 다시 계산하면 같은 선택.
3. 관통-파지 — 파지 플래그면 기본 측정만(위팔 보정 0), 명시 resolve 는 위험 표시. 첫 실험(같은 seed measure vs resolve) 판정과 비파지 관통 상한을 기록.
4. 기본 동작 불변 — 플래그 · 후보 설정이 없으면 계획 · 결과가 개정 10 과 같다.
5. 회귀 없음 — pytest(366 + 신규) · Phase 1 ~ 7 통합 실패 0 · C++ 무변경(바뀌면 Development · DebugGame 경고 0).
6. 사람 판정 — Persona 확인 목록을 보고하고, 수치 통과를 품질 합격으로 보고하지 않는다(§16-9).

**결과 (2026-10-26 — `anim_gen_phase8_1_test.py` 전 섹션 PASS, 실행 `P81Run1026_145046`(E1) · `_153634`(plan) · `_153646`(E2 ① · E2' · E3) · `_154722`(E2 ②)):**

| # | 기준 | 결과 |
| :---: | :--- | :--- |
| 1 | 플래그 변환 | ✅ 계획(Kimodo 안 띄움 · 애셋 0 · 더티 0): 규칙 3개(양손 EE 41 키 프레임 · 발 EE · root2d) · seed 4개 · 8 확산 · 기한 475초 · 측정 본 = Vesper 템플릿 체인. **E2 ①(seed 20261025 · meet):** 소스 손목 간격 p50 64.6 → 7.6 cm, 20 cm 안 0 → **100%**(목표 간격 6.96 cm, 목표 손목 오차 p50 2.5 / 1.8 cm), 접지 발 1차와 최대 3.0 / 2.2 cm, 루트 차 ≤ 3.9 cm · Vesper 손목 간격 p50 6.0 cm, 21.05 cm 안 **100%** · 검증 `PASSED_WITH_WARNINGS`(관통 경고), 잡 93초(Kimodo 80 — 2회 확산) |
| 2 | 후보 · 선별 | ✅ **E2 ②(seed 20261025 ~ 28, meet):** 한 Kimodo 실행(117 ~ 128초 — 후보당 1 · 2차 합 19 ~ 24초) → Blender 한 실행 → 후보 4개 리타깃 · 측정 → seed 20261026 선택(아래 표), 기록한 수치로 다시 계산 = 같은 선택, 최종 애셋 = 잰 후보(간격 p50 6.6 = 6.6 cm, 검증 `PASSED`), 잡 152초. 두 번 실행 결과가 소수 둘째 자리까지 같다 |
| 3 | 관통-파지 | ✅ 파지 플래그 → `measure`(`body_clearance_from: grip_flag` · 위팔 보정 0 · 한계 `BODY_CLEARANCE_MEASURED_FOR_GRIP`), 명시 `resolve` → `CLEARANCE_MAY_BREAK_GRIP`(pytest). E1 판정 = 파지 없음 · 보정은 벌렸을 뿐(§10). **비파지 관통 상한 = 0%**(E2 ① · ② 모두 전 프레임 파지 — 관통은 전부 파지 프레임: E2 ① 72.7% · 최대 6.3 cm, 아래팔 → 가슴) → **B안(파지 프레임 마스크 C++)은 불필요가 확정** — 남은 관통은 양손을 모은 팔이 몸에 들어가는 것이라 C안(8-4)의 몫 |
| 4 | 기본 동작 불변 | ✅ 플래그 · 후보가 없으면 사슬 5단계 · `body_clearance resolve` · `GRIP_NOT_VALIDATED` 그대로(통합 `plan` · pytest), `refine.mode off` 면 플래그는 지금처럼 한계 · Kimodo 인자에 후보 경로 없음(pytest). Phase 5 수치 회귀는 아래 5 |
| 5 | 회귀 없음 | ✅ pytest **406건**(기존 366 + `test_refine.py` 15 · `test_select.py` 25 — 기존 기대값 변경 없음, FakeEditor 에 profile · 관통 · 이름 규칙 · 빈 폴더 임포트 흉내 추가). 같은 에디터에서 `anim_gen_phase1_test.py` 113 · `phase2` 62 · `phase3` 35(+1 = 기대된 변화: 카타나 + `two_hand_weapon_grip` → `body_clearance measure` · `BODY_CLEARANCE_MEASURED_FOR_GRIP`) · `phase4` 27 · `phase5` 57(실제 Kimodo 2건 — 각속도 p99 비 0.954 · 루트 691.83 cm · Yaw 189.81°, 개정 8 과 같다) · `phase6` 20(외부 호출 0) · `phase7` 85 확인 실패 0. C++ 변경 없음 — 빌드 생략 |
| 6 | 사람 판정 | ⏳ Persona 확인 목록(아래)을 보고 — 수치 통과는 품질 합격이 아니다. 기준값 · 가중치는 사용자 판정으로 고친다 |

**E2 ② 선별 근거 (Vesper 측정 — 원 수치 · 벌점 · 점수):**

| 후보 · seed | 순위 · 점수 | Vesper 파지 % · 간격 p50 | 발 좌우 비 p90 | 휘두름 정점 cm/s | 관통 % | 비파지 관통 상한 | 최대 °/프레임 | 벌점 (grip · stance · swing · clearance · breakage) | 소스 파지 1 → 2차 · 휘두름 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 · 20261026 | **1 · 0.220** | 100 · 6.6 cm | 5.63 | 210.7 | 0 | 0 | 17.1 | 0 · 0.63 · 0.36 · 0 · 0 | 0 → 100% · 232.5 |
| 0 · 20261025 | 2 · 0.275 | 100 · 6.0 cm | 5.63 | **330.6** | 72.7 | 0 | 44.4 | 0 · 0.63 · 0 · 0.73 · 0.5 | 0 → 100% · 401.3 |
| 3 · 20261028 | 3 · 0.292 | 100 · 5.2 cm | 4.92 | 278.0 | 84.3 | 0 | 114.6 | 0 · 0.48 · 0.16 · 0.84 · 0.5 | 0 → 100% · 352.6 |
| 2 · 20261027 | 4 · 0.295 | 100 · 6.0 cm | **4.23** | 217.4 | 77.7 | 0 | 28.9 | 0 · 0.35 · 0.34 · 0.78 · 0.5 | 0 → 100% · 296.5 |

근거 한 줄(Job): "score 0.220 vs #0 0.275 — ahead on clearance +0.73, breakage +0.50". 읽는 법: 네 후보 모두 2차에서 파지 100% 라 파지는 가르지 못했고, 관통 0% · 경고 없는 seed 20261026 이 뽑혔다 — **그 대신 휘두름이 가장 느리다**(210.7 cm/s, 최고 330.6). `PASSED_WITH_WARNINGS` 는 관통 경고에서 와 관통이 '관통'과 '깨짐'에 이중으로 잡혔다(Job `breakage.all_warnings` 로 근거를 남김 — 기준 보정 후보). 발 간격은 seed 20261027 이 가장 좁다(4.23). 휘두름을 중시하면 `select.weights.swing` 을 올린다(같은 기록으로 다시 계산 가능).

**E2'(lead) · E3:** `lead`(같은 seed) — 보조 목표가 팔 밖이라 소스 파지 21.5%(간격 p50 27.8 cm) · Vesper 62.5% · 비파지 관통 상한 37.5% → 수치로는 `meet` 가 낫다(기본 `meet` 유지 — 사용자 눈 비교로 확정). E3(프롬프트 끝을 "…ready stance with feet shoulder-width apart." 로, 플래그 없이 같은 seed) — Vesper 발 좌우 비 p90 5.45(기준 5.55) — **넓은 다리는 이 프롬프트 표현 탓이 아니다**(좁히기는 8-3).

**발견:** ① 양손을 붙이면 휘두름이 느려진다(소스 정점 543 → 401, 365 → 233 cm/s — 사용자 판정 "흐느적" 과 같은 방향, 8-3 가속 · 프롬프트 · 선별 가중치 후보) ② 양손을 모은 팔은 Vesper 가슴 · 옷에 들어간다(관통 72 ~ 84%, 최대 6.3 cm — 8-4 C안) ③ seed 20261028 은 최대 114.6°/프레임(깨짐 의심 — 눈 확인 대상).

**Persona 확인 목록:** 기준(유지) `/Game/Animation/Test/AIAnimation/KimodoSword1025_185815/AS_Vesper_Sword_KimodoSlash` · E1 measure `…/P81Run1026_145046/AS_Vesper_Sword_KimodoSlashMeasure` · E2 ① meet `…/P81Run1026_153646/AS_Vesper_Sword_KimodoSlashMeet` · E2' lead `…/P81Run1026_153646/AS_Vesper_Sword_KimodoSlashLead` · E2 ② 선택 `…/P81Run1026_154722/AS_Vesper_Sword_KimodoSlashPick` · 상위 후보 `…/P81Run1026_154722/Work/job_20261026_154723_c49a83/A1/Candidates/Cand_BVH_kimodo_01`(1위 = 선택과 같은 동작) · `…/Cand_BVH_kimodo_00`(2위) · E3 `…/P81Run1026_153646/AS_Vesper_Sword_KimodoSlashStance`.

**남은 것(부록 B):** 사람의 Persona 판정 · 점수 기준값(2.5 · 폭 5.0) · 가중치 · 깨짐 이중 계산 보정 · `meet`/`lead` 기본값 확정 · 손 방향 · 손가락 · 무기 소켓(8-4) · 관통 C안(8-4) · Vesper 캡처(8-2). (깨짐 이중 계산 · 공격다움은 아래 수정안 C 로 처리)

#### 8-1 수정안 A · B · C (개정 11 보강 — 2026-10-26 Persona 소견 후)

**진행:** 사용자 Persona 소견 4가지(① 양손 · 한손 모두 처음 · 끝 메시 떨림 ② "이게 공격 자세가 맞나?" ③ 손이 꺾여 보인다 ④ 한손 공격이 여전히 흐느적) → 하위 세션이 측정으로 원인 확정 · 수정안 스파이크(공유 노트 `phase8-1-quality-spike.md` — 제품 코드 무변경) → 사용자 지시: A · B · C 적용 + 같은 4 seed 재생성. D(프롬프트 '빠르게 · 힘있게' + 2.5초 — 요청만)는 범위 밖, 휘두름 구간 자동 가속은 8-3, 칼을 나란히 쥐는 손 방향 · 파지 프레임 관통은 8-4. C++ · MCP Tool 변경 없음.

| # | 소견 | 원인 (측정) | 수정 | 바꾼 곳 |
| :---: | :--- | :--- | :--- | :--- |
| A | ① 떨림 | **2차 생성 소스의 프레임 진동** — 지그재그 p95 1차 ≤ 0.09 vs 2차 0.18 ~ 1.23 cm/프레임². 리타깃 · 관통 보정 · 루트 몫 0(소스 NPZ · UE 소스 · Vesper 가 1.0 ~ 1.03배로 같다). 손 · 발 end-effector 를 3프레임마다 조건으로 주면 separated CFG 의 제약 항이 키 프레임 사이를 진동하며 메운다(매 프레임 키면 정지 구간 1차 수준 — 감사 §18) | 2차 출력의 로컬 회전(쿼터니언 — 부호 연속) · 루트 위치에 시간 가우시안 σ 1프레임 → 77 관절 FK 로 전역 회전 · 관절 위치를 다시 만든다(1차는 그대로, NPZ · BVH · 소스 수치는 스무딩 뒤). σ 의 단일 원천 = 계획 `refine.smooth_sigma_frames`(러너는 받기만) · report `refine.smooth{sigma_frames, fk_check_m, joint_moved_cm}` · 스무딩 전 수치 `source_metrics.pass2_unsmoothed`. 스무딩 전 FK 가 모델 출력과 1 cm 넘게 다르면 `SMOOTH_FK_MISMATCH` 로 멈춘다 | `local_ai/refine.py`(`gaussian_kernel` · `smooth_series` · `smooth_rotations` · `plan`) · `kimodo_run.py`(`smooth_output`) |
| B | ③ 손 꺾임 | 처음 파지 규칙(보조 손 '손목 → MiddleEnd' 를 주 손에 맞추는 최소 회전 · 주 손 전역 회전 고정)이 **IK 목표에서 이미 보조 손목을 96 ~ 99° 꺾었고** 2차가 그대로 따랐다 | 손 전역 회전 = 새 아래팔 × 1차 손목 로컬(keep — 주 · 보조 모두 `_move_arm` 한 규칙). 목표 포즈 통계 `grip.stats.hand_align_deg` · `support_wrist_bend_deg`, `grip.hand_rule: keep`. 한계 `GRIP_POSITION_ONLY` 문구(손 방향은 1차 손목 굽힘 유지 — 나란히 쥐기는 8-4) | `refine._move_arm` · `solve_grip` · `providers/local_ai.py` |
| C | ② 공격 자세 | 기록 Job c49a83 이 seed 26('양손 모아 서 있기' — 손이 머리 위로 한 번도 안 감, 궤적 폭 0.40)을 골랐다: 관통 경고가 깨짐 0.5 로 **이중 계산** · 양손을 모으면 아래팔이 가슴에 닿는 **파지 프레임 관통**(72 ~ 84%)을 벌점으로 셈 → 움직임이 작은 후보가 유리 · **공격다움 지표 없음** | ① 깨짐 = 관통 검사(`body_clearance`) 밖 경고만(`breakage.scored_warnings`) ② 파지 플래그면 관통 = 비파지 프레임 상한(`non_grip`) ③ `attack`: 궤적 폭 = 엉덩 관절 중점(≈ 펠비스) 기준 손목 중점 궤적 상자 대각선 / 팔 길이(위팔 + 아래팔), 벌점 = max(1 − 폭 / 후보 최고, (1.0 − 폭) / 1.0) · 가중치 2(`weapon_action` 일 때만). 손 들기(어깨 위 높이)는 수평 베기에 안 맞아 기록만, 떨림도 기록만(빠른 타격 순간도 잡는다). 측정 본에 어깨(템플릿 체인 LeftArm/RightArm 시작) · 팔꿈치(손목 본의 부모) | `motion_metrics.py`(버전 2) · `selection.py` · `providers/builtin.py`(`selection_bones` · `candidate_metrics`) · `kimodo_run.METRIC_JOINTS` |

**지표 정의 (`motion_metrics` 버전 2 — Kimodo · Vesper 공용):** 떨림 = 지그재그(가속도 a_f = p[f+1] − 2p[f] + p[f−1] 이 앞 프레임과 반대 방향이면 min(\|a_f\|, \|a_f−1\|)) 를 측정 관절마다(소스 12 · Vesper 10) 재서 처음 0.67초 · 중간 · 끝 0.67초 p95 · 손목 굽힘 = 아래팔(팔꿈치 → 손목)과 손(손목 → 중지 첫 마디 — SOMA `{Side}HandMiddle2` · Vesper `middle_01`) 방향의 각 · 궤적 폭 · 손 들기(위) · 접지 발 미끄러짐 = 앞 · 뒤 표본이 모두 접지인 발목 수평 속도 p95(Kimodo 접지 라벨 — 소스만). 스파이크 노트의 손목 굽힘은 다른 마디로 재 절대값이 다르다 — 아래 표는 모두 같은 정의로 다시 잰 값.

**결과 (2026-10-26 — `anim_gen_phase8_1_test.py --only hashes,plan,recompute,select,dirty` PASS · 실패 0, 실행 `P81Run1026_180733` · Job `job_20261026_180741_c0f5be`, 잡 209초 · Kimodo 179초):** 같은 프롬프트 · seed 20261025 ~ 28 · `meet`. 수정 전 = 기록 Job c49a83(소스 NPZ 는 제품 지표 · 스무딩 함수로, Vesper 후보는 통합 `recompute` 로 다시 잼). 1차 생성은 같은 seed 라 수정 전후 같다(결정성 — 1차 수치 일치).

소스(Kimodo NPZ — 1차 → 수정 전 2차 → 수정 후 2차):

| seed | 떨림 p95 처음 / 중간 / 끝 | 보조(왼) 손목 굽힘 최대 ° | 파지 20 cm 안 · 간격 p50 / 최대 cm | 휘두름 정점 cm/s | 접지 발 미끄러짐 p95 L / R cm/s |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 20261025 | 0.00 / 0.01 / 0.03 → 1.01 / 0.59 / 0.63 → **0.02 / 0.06 / 0.08** | 22.8 → 111.5 → **39.7** | 0% → 100% · 7.6 / 12.0 → 100% · 7.2 / 14.0 | 542.8 → 401.3 → 400.9 | 0.7 / 0.9 → 3.0 / 2.8 → 1.2 / 1.3 |
| 20261026 | 0.03 / 0.01 / 0.02 → 0.35 / 0.69 / 0.67 → **0.06 / 0.07 / 0.08** | 39.9 → 97.5 → **16.1** | 0% → 100% · 7.2 / 9.1 → 100% · 9.2 / 11.2 | 365.2 → 232.5 → 243.8 | 2.1 / 0 → 0 / 1.5 → 0.8 / 0.2 |
| 20261027 | 0.09 / 0.01 / 0.01 → 1.23 / 0.74 / 0.66 → **0.13 / 0.07 / 0.07** | 82.7 → 41.8 → **84.4** | 0% → 100% · 8.1 / 10.5 → 100% · 7.8 / 9.1 | 457.1 → 296.5 → 279.0 | 1.6 / 0.7 → 2.4 / 0 → 2.0 / 0.9 |
| 20261028 | 0.01 / 0.01 / 0.02 → 0.22 / 0.27 / 0.18 → **0.04 / 0.02 / 0.03** | 38.5 → 63.0 → **22.3** | 0% → 100% · 6.4 / 8.8 → 100% · 8.8 / 10.4 | 657.4 → 352.6 → 326.4 | 0.7 / 0 → 0 / 0 → 0.9 / 0.8 |

Vesper(수정 전 → 수정 후):

| seed | 순위 · 점수 | 떨림 p95 처음 / 중간 / 끝 | 보조 손목 굽힘 p50 / 최대 ° | 궤적 폭(팔 길이 대비) | 휘두름 정점 cm/s | 간격 p50 · 파지 | 관통 %(비파지 상한) | 최대 °/프레임 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 20261025 | 2 · 0.275 → **1 · 0.102** | 0.99 / 0.56 / 0.60 → 0.00 / 0.06 / 0.07 | 43.6 / 112.8 → 37.4 / 41.5 | 1.65 → 1.63 | 330.6 → 321.4 | 6.0 → 5.2 cm · 100% | 72.7 → 77.7 (0) | 44.4 → 25.7 |
| 20261026 | **1 · 0.220** → 4 · 0.307 | 0.32 / 0.64 / 0.64 → 0.06 / 0.07 / 0.08 | 78.3 / 94.3 → 8.5 / 17.1 | 0.40 → 0.43 | 210.7 → 220.4 | 6.6 → 7.3 · 100% | 0 → 0 | 17.1 → 22.8 |
| 20261027 | 4 · 0.295 → 3 · 0.199 | 1.03 / 0.74 / 0.65 → 0.21 / 0.08 / 0.08 | 37.3 / 42.7 → 62.5 / 86.6 | 1.03 → 1.02 | 217.4 → 206.2 | 6.0 → 5.0 · 100% | 77.7 → 80.2 (0) | 28.9 → 20.7 |
| 20261028 | 3 · 0.292 → 2 · 0.193 | 0.21 / 0.28 / 0.21 → 0.04 / 0.03 / 0.04 | 61.4 / 63.4 → 20.4 / 24.9 | 1.08 → 1.01 | 278.0 → 261.2 | 5.2 → 7.1 · 100% | 84.3 → 74.4 (0) | 114.6 → 42.4 |

**새 선별 근거 (수정 후 Job — 원 수치 · 벌점 · 순위):**

| 후보 · seed | 순위 · 점수 | Vesper 파지 % | 발 좌우 비 p90 | 휘두름 정점 | 궤적 폭 (손 들기) | 관통 % → 벌점에 쓴 값 | 깨짐 근거 (점수용 / 전체) | 벌점 grip · stance · swing · attack · clearance · breakage |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 0 · 20261025 | **1 · 0.102** | 100 | 5.30 | **321.4** | **1.63** (+0.63) | 77.7 → 비파지 0 | 없음 / `BODY_PENETRATION` | 0 · 0.56 · 0 · 0 · 0 · 0 |
| 3 · 20261028 | 2 · 0.193 | 100 | 4.96 | 261.2 | 1.01 (+0.29) | 74.4 → 0 | 없음 / `BODY_PENETRATION` | 0 · 0.49 · 0.19 · 0.38 · 0 · 0 |
| 2 · 20261027 | 3 · 0.199 | 100 | **4.30** | 206.2 | 1.02 (+0.12) | 80.2 → 0 | 없음 / `BODY_PENETRATION` | 0 · 0.36 · 0.36 · 0.37 · 0 · 0 |
| 1 · 20261026 | 4 · 0.307 | 100 | 5.71 | 220.4 | 0.43 (+0.07) | 0 → 0 | 없음 / 없음 | 0 · 0.64 · 0.31 · 0.73 · 0 · 0 |

근거 한 줄(Job): "score 0.102 vs #3 0.193 — ahead on attack +0.76, swing +0.37". 지금 벌점 표:

| 지표 | 벌점 pᵢ | 가중치 |
| :--- | :--- | :---: |
| 양손 파지 | 1 − grip_pct / 100 | 3 (`two_hand_weapon_grip` 일 때만) |
| 발 간격 | clamp((Vesper 발 좌우 비 p90 − 2.5) / 5.0, 0, 1) | 2 |
| 휘두름 정점 | 1 − 정점 / 후보 중 최고 | 2 (`weapon_action` 일 때만) |
| 궤적 폭 (attack — 신규) | max(1 − 폭 / 후보 중 최고, clamp((1.0 − 폭) / 1.0)) — 하한 = 팔 길이 1.0(운영 공격 최저 1.46 · 기록의 '서 있기' 0.40) | 2 (`weapon_action` 일 때만) |
| 관통 | 보정 전 관통 % / 100 (팔 중 큰 쪽) — **파지 플래그면 비파지 프레임 관통 상한**(손목 트랙이 없어 못 재면 전체) | 1 |
| 깨짐 | `FAILED` = 제외 · `NEEDS_REVIEW` 0.5 · `PASSED_WITH_WARNINGS` 0.5 — **경고가 관통 검사에서만 왔으면 0**(`scored_warnings` 가 기록에 없으면 상태대로) · `PASSED` 0 | 1 |

**읽는 법:**
- A — 소스 떨림이 네 seed 모두 1차 수준(≤ 0.08, seed 27 처음 0.67초만 0.13 — 빠른 디딤 구간)으로 내려가고 Vesper 도 같다(리타깃이 그대로 옮긴다). 파지 100% 유지 · FK 대응 0.0 m · 관절 이동 p95 0.7 ~ 1.6 · 최대 5.7 cm. 대가 = 휘두름 정점 −3 ~ −10%(같은 실행 스무딩 전 412.8 / 271.8 / 308.9 / 360.3 → 400.9 / 243.8 / 279.0 / 326.4). 접지 발 미끄러짐 p95 ≤ 2.0 cm/s(수정 전 ≤ 3.0).
- B — 보조 손목 최대가 1차 수준 근처로(seed 25 111.5 → 39.7°, 26 97.5 → 16.1°, 28 63.0 → 22.3° — Vesper 도 112.8 → 41.5 · 94.3 → 17.1 · 63.4 → 24.9°). **seed 27 은 1차부터 82.7° 꺾인 생성이라 keep 이 그 꺾임을 지킨다(수정 전 aim 이 오히려 41.8° 로 폈다 — 84.4°)** — 손목 절대 상한 또는 8-4. 양손 방향 정렬은 맞추지 않는다(목표 포즈 양손 방향 차 p50 23 ~ 86° — 나란히 쥐기는 8-4).
- C — 통합 `recompute`: 수정 전 기록 후보 4개를 새 측정 · 점수로 다시 재면 **seed 20261025**(0.114 vs 2위 seed 28 0.179 — attack +0.68 · swing +0.32). 관통 경고만 있던 후보 3개(seed 28 포함 — 114.6°/프레임은 경고를 만들지 않았다)의 깨짐 0.5 → 0, 파지 프레임 관통 72.7 ~ 84.3% → 비파지 상한 0. 궤적 폭 · 손 들기가 스파이크 값과 같다(1.646 / 0.395 / 1.028 / 1.083 vs 1.65 / 0.38 / 1.02 / 1.08, 손 들기 ±0.01). 새 실행도 seed 20261025 를 고르고 '서 있기'(seed 26, 궤적 폭 0.43)는 4위.
- 그대로 남은 것: ④ 흐느적 — 고른 후보 정점 321 cm/s(운영 공격 1,200 ~ 2,600, 이 프롬프트 · 4초는 정지 꼬리 2.2 ~ 2.5초 — 스파이크 ⑤) → D(요청 — 프롬프트 · 2.5초) · 8-3 가속 · 트림. 양손을 모은 팔의 몸 관통(파지 프레임 74 ~ 80%, 아래팔 → `breast_r`) → 8-4 C안. seed 27 손목. **수치 통과는 품질 합격이 아니다 — 사람의 Persona 판정 대기.**

**Persona 확인 목록 (수정 후):** 선택 `/Game/Animation/Test/AIAnimation/P81Run1026_180733/AS_Vesper_Sword_KimodoSlashPick`(seed 20261025 — 1위 `Cand_BVH_kimodo_00` 과 같은 동작) · 2위 `…/P81Run1026_180733/Work/job_20261026_180741_c0f5be/A1/Candidates/Cand_BVH_kimodo_03`(seed 20261028) · 3위 `…/Cand_BVH_kimodo_02`(seed 20261027 — 발 간격 가장 좁음 · 손목 꺾임 남음) · 비교(수정 전) `…/P81Run1026_154722/AS_Vesper_Sword_KimodoSlashPick`(수정 전 선택 seed 26) · `…/P81Run1026_153646/AS_Vesper_Sword_KimodoSlashMeet`(수정 전 seed 25 — 새 선택과 같은 seed).

#### 8-1 낫 기준 보정 (개정 11 보강 2 — 2026-10-26 저녁)

**진행:** 사용자 Persona 재확인 — "의도한 동작이 맞나 · 시작 손 모양 · 손끼리 겹침" → 측정: 생성물은 검 손잡이 기준(손목 간격 4 ~ 14 cm, 손 겹침 7.5% 프레임 · 처음 1.37초)인데 **Vesper 의 근접 무기는 낫**(로드아웃 `WD_Sickle1` + `WD_Rifle1` — `AstralPlayerController.h:50`)이고 운영 낫 애니는 양손으로 자루를 쥐는 구간의 손목 간격이 50 ~ 78 cm(p50 55 ~ 66)다. 스켈레톤에 무기 본은 없다(소켓 `WeaponHandR` · `DisplayHip` · `DisplayBack` 만 — Persona 의 낫은 애니가 움직이지 않는다). 사용자 결정: 기준 = 낫, 8-1 안에서 보정(한손으로 바뀌어도 맞게). C++ · MCP Tool 변경 없음.

| 항목 | 바꾼 것 | 곳 |
| :--- | :--- | :--- |
| 파지 간격 상한 | `grip.spacing_cm` (0, 30] → **(0, 100]** — 비우면 검 손잡이(너클 폭 + 1 cm) 그대로, 낫 요청은 60 | `request.py` · `server.py` · §9 |
| 파지 판정 띠 | 요청 간격 s 가 있으면 파지 = \|간격 − s·scale\| ≤ 13·scale(`motion_metrics.grip_band` — 검 기준 '≤ 20 cm' 이 7 cm 손잡이에 준 여유 13 cm 와 같다). 소스 수치(kimodo_run) · Vesper 선별 · 비파지 관통 · `GRIP_NOT_REACHED` 가 같은 띠 — 계획 select 에 `grip_spacing_cm` | `motion_metrics.py` · `kimodo_run.py` · `local_ai.py` · `builtin.py` |
| 궤적 폭 일반화 (`motion_metrics` 버전 3) | 손별 궤적 폭 중 큰 쪽(한손 공격에서 빈 손이 가만있으면 두 손 중점은 절반쯤 — 중점 값은 `width_mid_arm_ratio` 로 기록), 손 들기도 손별 큰 쪽 | `motion_metrics.attack` · `selection.py` 문구 |
| 양손 겹침 (기록) | `hand_contact` — 손 본 아래 자손(손가락 · 메타카팔, 이름을 보지 않고 부모 관계로)의 뼈 선분 사이 최단 거리 < 2.5 cm × scale 프레임 % · 처음 시각 · 최소. 측정 본 = `selection_bones.hand_tree_l/r` | `motion_metrics.hand_contact` · `builtin.selection_bones` · `profile_bones` · `candidate_metrics` |
| 테스트 | pytest **426**(417 + 9 — 한손 궤적 폭 · 손 겹침 · 파지 띠 · 낫 간격 select · 간격 상한 4) · 통합 새 섹션 `scythe`(운영 낫 애니 4개를 같은 측정으로 비교) | `test_refine.py` · `test_select.py` · `anim_gen_phase8_1_test.py` |

**결과 (`anim_gen_phase8_1_test.py --only hashes,plan,recompute,scythe,dirty` PASS · 실패 0, 실행 `P81Run1026_184807` · Job `job_20261026_184814_ad275a`, 잡 294초 · Kimodo 265초):** 프롬프트 "A person holds a long-handled scythe with both hands, raises it over the right shoulder, slashes diagonally down to the left, then returns to a fighting stance." · seed 20261025 ~ 28 · `meet` · `spacing_cm` 60. 기록 후보 재계산(`recompute`, 버전 3 궤적 폭 1.698 / 0.403 / 1.110 / 1.097)도 seed 20261025.

| 후보 · seed | 순위 · 점수 | Vesper 파지 %(띠 49.5 ~ 76.8) · 간격 p50 | 발 좌우 비 p90 | 휘두름 정점 cm/s | 궤적 폭(손별 큰 쪽) | 관통 % → 벌점 값(비파지) | 보조 손목 최대 ° | 벌점 grip · stance · swing · attack · clearance · breakage |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 0 · 20261025 | **1 · 0.096** | 93.3 · 51.1 cm | 4.48 | **492.6** | **2.24** | 75.2 → 6.7 | 39.0 | 0.07 · 0.40 · 0 · 0 · 0.07 · 0 |
| 1 · 20261026 | 2 · 0.193 | 96.7 · 50.5 | **4.00** | 313.2 | 1.50 | 79.3 → 3.3 | 59.2 | 0.03 · 0.30 · 0.36 · 0.33 · 0.03 · 0 |
| 3 · 20261028 | 3 · 0.337 | 67.5 · 49.9 | 4.11 | 262.1 | 1.31 | 73.6 → 32.5 | 109.2 | 0.33 · 0.32 · 0.47 · 0.41 · 0.33 · 0 |
| 2 · 20261027 | 4 · 0.359 | 35.0 · 49.0 | 4.18 | 366.9 | 2.05 | 71.1 → 65.0 | 55.1 | 0.65 · 0.34 · 0.26 · 0.08 · 0.65 · 0 |

검 기준(같은 seed 25 선택, 실행 `P81Run1026_180733`) → 낫 기준: Vesper 손목 간격 p50 5.2 → **51.1 cm** · 양손 겹침 7.5% → **0%**(최소 48 cm) · 휘두름 정점 321.4 → **492.6 cm/s**(소스 400.9 → 604.0) · 발 좌우 비 p90 5.30 → 4.48 · 보조 손목 최대 41.5 → 39.0° · 떨림 p95 0.00 / 0.06 / 0.07 → 0.08 / 0.00 / 0.04 · 소스 접지 발 미끄러짐 p95 L/R 1.2 / 1.3 → 5.8 / 2.6 cm/s(1차 2.0 / 2.8 — 왼발이 커졌다). 검증 `PASSED_WITH_WARNINGS`(관통 경고뿐), `GRIP_NOT_REACHED` 없음.

운영 낫 애니(같은 측정 — `candidate_metrics` · 간격 60 띠):

| 애셋 | 손목 간격 p50 (범위) | 양손 구간(간격 일정) % · 그 간격 p50 | 띠 안 % | 궤적 폭 손별 (중점) | 손 들기 | 휘두름 정점 cm/s | 양손 겹침 % |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Sickle Attack1 | 72.2 (8 ~ 104) | 24 · 54.8 | 26.7 | 3.38 (2.36) | 0.81 | 2,068 | 4.0 |
| Sickle Attack2 | 15.2 (9 ~ 60) | 24 · 54.9 | 28.4 | 2.71 (2.47) | 0.36 | 1,221 | 15.8 |
| Sickle Attack3 | 49.0 (11 ~ 78) | 47 · 63.3 | 44.6 | 3.65 (3.21) | 0.58 | 1,947 | 1.1 |
| Sickle Finisher1 | 33.2 (4 ~ 90) | 32 · 66.2 | 40.3 | 4.64 (4.48) | 0.90 | 1,967 | 33.3 |
| **Kimodo 낫 선택 (seed 25)** | 51.1 (p90 53.2) | 내내(클립 전체 파지) | 93.3 | 2.24 | 0.40 | 493 | 0 |

**읽는 법:**
- 낫 프롬프트 · 간격으로 양손이 자루 간격으로 벌어졌고(겹침 0), 휘두름 정점이 +53%(검 기준 대비) · 궤적 폭이 커졌다 — 그래도 운영 낫의 1/2.5 ~ 1/4 속도다(흐느적 → D · 8-3).
- **FK 리타깃이 간격을 줄인다:** 소스 58 ~ 60 cm → Vesper 49 ~ 51 cm(−9 ~ −11 cm, 어깨 반폭 차 — 검 기준 7 → 5 cm 와 같은 현상). Vesper 띠(60 × 1.05 ± 13.65 = 49.5 ~ 76.8)의 아래 끝에 걸려 seed 27 · 28 은 파지 35 · 67.5% 로 깎였다(소스는 100%). 운영 낫 간격(p50 55 ~ 66)에 맞추려면 요청 간격을 70 안팎으로 올리는 것이 후보 — **검증 안 함**. 정확히 맞추는 것은 대상 쪽 IK(8-4).
- 운영 낫은 양손 구간이 24 ~ 47% 뿐이고 손이 모이거나(겹침 최대 33%) 왼손이 떨어진다 — 클립 전체를 같은 간격으로 쥐게 하는 지금 규칙은 단순화다(구간은 `grip.from_s` · `to_s`, 구간별 전환은 8-4).
- seed 28 보조 손목 109° 는 1차부터(107°) — keep 이 그대로 지킨다(B 의 알려진 한계).
- **수치 통과는 품질 합격이 아니다** — 낫이 손에 없고(무기 본 없음) 손가락은 고정 포즈라, Persona 에서는 몸 · 팔 궤적과 손이 붙는 자리를 본다.

**Persona 확인 목록 (낫 기준):** 선택 `/Game/Animation/Test/AIAnimation/P81Run1026_184807/AS_Vesper_Sickle_KimodoSlashPick`(seed 20261025) · 2위 `…/P81Run1026_184807/Work/job_20261026_184814_ad275a/A1/Candidates/Cand_BVH_kimodo_01`(seed 20261026 — 발 간격 가장 좁음) · 3위 `…/Cand_BVH_kimodo_03`(seed 20261028 — 손목 109°) · 비교: 검 기준 선택 `…/P81Run1026_180733/AS_Vesper_Sword_KimodoSlashPick` · 운영 `/Game/Animation/Hero/Vesper/Sickle/Actions/AS_Vesper_Sickle_Attack1`.

#### 8-1 낫 정정 — 팔 꼬임 · 머리 · 배 관통 (개정 11 보강 3 — 2026-10-26 밤)

**진행:** 사용자 Persona — 낫 선택 애니(`P81Run1026_184807/AS_Vesper_Sickle_KimodoSlashPick`)가 팔 꼬임 · 머리 관통 · 배 관통으로 망가졌다. 지난 실행은 이 수치 이상을 PASS 로 넘겼다(통합 `scythe` 에 꼬임 · 머리 · 관통 검사가 없었다). 사용자 승인 수정 방향으로 고치고 같은 4 seed 를 다시 만들었다. C++ · MCP Tool 변경 없음.

**원인 (측정):**
1. `refine.solve_grip` 의 손잡이 축 = 주 손 너클(`RightHandIndex2 → Pinky2`). 무기 없이 만든 Kimodo 1차의 펼친 손에서 이 축은 실제 두 손목 방향과 **84 ~ 128°** 어긋났다. 간격 7 cm(검)에서는 목표가 조금 비켜날 뿐이지만 60 cm(낫)에서는 보조 손 목표가 몸 반대편에 찍혔다 — 손 좌우 뒤바뀜 1차 0 ~ 5% → 목표 85 ~ 93%(seed 25 · 26 · 28) → 2차 46 ~ 93%, 목표 이동 p50 34 ~ 59 cm(팔 길이 1.5 ~ 2배), 손이 머리 15 cm 안 48 ~ 88% 프레임(seed 26 최소 1.2 cm). 검 실행(`job_20261026_180741_c0f5be`)도 목표 단계 24 ~ 32% 뒤바뀜 — 같은 결함.
2. 선별 `clearance_pct` 가 파지 플래그면 '비파지 프레임 관통'만 셌다(검 손잡이처럼 양손을 가슴 앞에 모으면 아래팔이 가슴에 닿는 게 정상이라는 가정). 낫에서는 몸 관통 71 ~ 79% 를 0 으로 뺐다. 머리 관통 · 팔 꼬임은 지표가 없었다(플러그인 `body_clearance` 는 몸통 · 골반 · 넓적다리만).

| 항목 | 바꾼 것 | 곳 |
| :--- | :--- | :--- |
| 손잡이 축 | 축 = 1차 '주 손목 → 보조 손목' 단위 벡터(프레임별 — 보조 손이 이미 있는 쪽). 두 손목이 `AXIS_MIN_CM` 2 cm 안이면 주 손 너클 축. 간격 규칙(요청 `spacing_cm` 또는 너클 폭 + 1 cm) · `meet` · 손 회전 keep 은 그대로. 계획 규칙에 `axis` 문구, 목표 통계에 `axis_from` · `knuckle_vs_wrist_line_deg`(처음 규칙이었다면 어긋났을 각) · `crossed_pct{pass1, targets}`(어깨 축 기준 — 보조 손목이 주 어깨 쪽으로 넘어간 프레임). 검 기준에도 같이 적용 | `local_ai/refine.py` · `local_ai.py`(`GRIP_POSITION_ONLY` 문구) · `request.py` · `server.py` |
| 자루 무기 관통 | 측정이 쓴 요청 간격(`metrics.grip.spacing_cm` — 같은 기록으로 다시 계산해도 같은 선택)이 있으면 관통 = 전체 프레임(`clearance_basis` `all_polearm`). 비파지만 세는 규칙은 검 손잡이(간격 없음)에만 | `selection.clearance_pct` |
| 팔 꼬임 (`motion_metrics` 버전 4) | `arm_cross` — 프레임마다 엉덩 관절 축(왼 − 오른, 수평) 위 (왼 손목 − 오른 손목). 10 cm × scale(손 폭) 넘게 넘어간 프레임 % = `crossed_pct`(점수), 조금이라도 = `swapped_pct`(기록 — 검 손잡이는 손목을 포개 88 ~ 100%), 깊이 p50 · 최대 · 처음 시각 | `motion_metrics.arm_cross` · `measure` |
| 손-머리 근접 (버전 4) | `head_near` — 손 점(양 손목 + 손가락 · 손바닥 관절)과 머리 본(두개 바닥) 사이 최소 거리 < 10 cm × scale 프레임 % · 최소 · p10 · p50. 손 점: Kimodo = SOMA77 손목 아래 손 관절 24 × 2, Vesper = 손 본 자손(손 트리 — 이름을 보지 않는다) 19 × 2. 머리 본: Vesper = 템플릿 체인 `Head` 시작(없으면 `Neck` 끝, 없으면 기본 이름 `head` · `SELECTION_BONES_DEFAULTED`), Kimodo = `Head`(`METRIC_JOINTS`). 떨림 · 다른 지표에는 머리를 안 쓴다 | `motion_metrics.head_near` · `builtin.selection_bones` · `profile_bones` · `candidate_metrics` · `kimodo_run.METRIC_JOINTS` · `source_metrics` |
| 선별 벌점 | `cross` = clamp((꼬임 % − 20) / 50) — 파지 플래그일 때만(한손 베기 · 팔짱은 원래 교차), `head` = clamp((근접 % − 5) / 25) — 모든 동작. 가중치 각 2(합 15). 기준값 = 운영 낫 애니 4개가 0 이 되는 곳(아래 표) | `selection.py` · `server.py` 문구 |
| 통합 검사 | `scythe` — 고른 후보(Vesper · 소스 2차)의 꼬임 ≤ 20% · 머리 ≤ 5% · 관통 ≤ 40%(`SCYTHE_LIMITS` — 꼬임 · 머리는 선별 벌점 시작값, 관통은 운영 최대 34.4 + 5 반올림)가 아니면 **FAIL**. 운영 낫 애니 자신도 그 상한 안인지(상한이 과하지 않다) · 2차 목표가 1차보다 손을 더 뒤바꾸지 않는지(≤ +5%) · 후보별 꼬임 · 머리 · 관통 출력. `plan` 은 버전 4 · 머리 본 · 축 문구, `recompute` 는 머리 · 손 트리 본까지 잰다 | `anim_gen_phase8_1_test.py` |
| 테스트 | pytest **432**(426 + 6 — 축 = 1차 손목 방향 · 손목이 겹치면 너클 · 꼬임 · 머리 근접 · 자루 무기 관통 · 꼬임/머리 벌점이 운영 낫을 깎지 않음, 기존 기대값: 축 · 버전 4 · 벌점 8키 · 측정 본에 `head` · 머리 본 체인/대체). 회귀: Phase 5 통합 PASS(57 — 0.954 · 691.83 cm · 189.81° 불변, `kimodo_run` 변경) | `test_refine.py` · `test_select.py` |

**기준값 근거 — 운영 낫 애니 4개 vs 망가진 낫 후보(Job `job_20261026_184814_ad275a`, Vesper · 지금 측정 `candidate_metrics` 버전 4):**

| 애셋 | 꼬임 %(> 10 cm) · 조금이라도 | 손-머리 10 cm 안 % · 최소 cm | 관통 % | 벌점 cross · head |
| :--- | :--- | :--- | :--- | :--- |
| Sickle Attack1 | 2.7 · 14.7 | 0 · 11.6 | 13.2 | 0 · 0 |
| Sickle Attack2 | 7.4 · 42.1 | 0 · 36.1 | 34.4 | 0 · 0 |
| Sickle Attack3 | 16.3 · 32.6 | 0 · 25.5 | 0 | 0 · 0 |
| Sickle Finisher1 | 0 · 4.2 | 0 · 15.0 | 12.3 | 0 · 0 |
| 이전 낫 seed 25 (선택) | 91.7 · 93.3 | 41.7 · 2.8 | 75.2 | 1.0 · 1.0 |
| 이전 낫 seed 26 | 28.3 · 94.2 | 90.0 · 0.6 | 79.3 | 0.17 · 1.0 |
| 이전 낫 seed 27 | 12.5 · 20.0 | 59.2 · 1.1 | 71.1 | 0 · 1.0 |
| 이전 낫 seed 28 | 82.5 · 94.2 | 69.2 · 1.6 | 73.6 | 1.0 · 1.0 |

margin 0(조금이라도 뒤바뀜)은 운영 낫도 4 ~ 42%(낫 베기는 원래 팔이 교차한다)이고 검 손잡이(손목 5 ~ 7 cm)는 88 ~ 100%(손목을 포갠다)라 점수에 못 쓴다 → 손 폭 10 cm × scale. 머리 15 cm 는 운영 Attack1 4% · Finisher1 2.8% 가 걸려 10 cm(운영 최소 11.0). 기록 후보 재계산으로 새 점수는 낫 Job 에서 seed 26 을 고른다(넷 다 머리 벌점 1.0 — 고를 후보가 없다, 그래서 통합 상한 검사로 막는다) · 검 Job c0f5be 는 seed 25 그대로(머리 벌점 seed 26 0.07 만) · 검 Job c49a83(`recompute`)도 seed 25 그대로(0.084 vs 0.133).

**새 축의 오프라인 확인(기록 1차 NPZ 에 새 `solve_grip` — Kimodo venv, 생성 없음):** 낫 4 seed · 검 4 seed 모두 축 = 1차 손목 방향 41/41 키 프레임(손목 2 cm 안 0), 처음 축과의 차 p50 27 ~ 128°. 목표 뒤바뀜(어깨 축) = 1차와 같음(낫 4.9 / 0 / 0 / 0%, 검 0%), 엉덩 축 10 cm 넘게 뒤바뀐 목표 0 ~ 2%, 손목 목표가 머리 10 cm 안 0%, 목표 이동 p50 0 ~ 19.6 · 최대 28.0 cm(처음 34 ~ 59), IK 늘어남 0.

**요청 간격 60 유지(70 으로 올리지 않음):** ① Vesper 간격 = 소스 × 0.79(새 실행 4 seed 48.2 / 48.6 / 48.2 / 49.3 ÷ 60.1 ~ 62.7 — 어깨 폭 · 팔 길이 차, Vesper 팔 47.7 vs SOMA 55.9 cm)인데 띠 아래 끝은 (요청 − 13) × 1.052(pelvis scale)라 **요청이 52 cm 를 넘으면 간격을 어떻게 잡아도 Vesper 가 띠 밖**이다 — 70 이면 Vesper ≈ 55 cm 가 띠 [60.0, 87.3] 밖. ② 기록 1차로 푼 목표 이동이 60 → 70 에서 p50 0 ~ 19.6 → 0 ~ 28.5 · 최대 28.0 → 44.5 cm, 도달 비 최대 1.27 → 1.43 으로 커진다(1차에서 멀어질수록 2차가 비튼다). 띠를 팔 길이 비로 재는 정의 정정과 운영 낫 간격(Vesper 55 ~ 66 → 요청 ≈ 76)은 후속 → 아래 '파지 띠 정정'(보강 4)에서 정정(대상 60 → 생성 75.2).

**결과 (`anim_gen_phase8_1_test.py --only hashes,plan,recompute,scythe,dirty` — FAIL 2 · 나머지 통과, 실행 `P81Run1026_192547` · Job `job_20261026_192555_f991aa`, 잡 402초 · Kimodo 374초):** 같은 프롬프트 · seed 20261025 ~ 28 · `meet` · 간격 60. **FAIL 2건 = 파지 띠**(고른 후보 Vesper 띠 [49.5, 76.8] 안 37.5% < 80 · `GRIP_NOT_REACHED`) — 위 ①의 정의 문제다. 꼬임 · 머리 · 관통 상한, 운영 낫 4개가 상한 안(상한이 과하지 않다), 목표가 1차보다 손을 뒤바꾸지 않음(4 seed 모두 ≤ +5%), 소스 파지 97.5 ~ 100%, 스무딩, 최종 = 잰 후보, 해시 · 더티 · Content 는 통과.

같은 seed 전 → 후 (Vesper, 소스는 2차):

| seed | 꼬임 % Vesper (소스) | 손-머리 10 cm 안 % Vesper · 최소 cm (소스) | 관통 % | 파지 % · 간격 p50 Vesper (소스 p50) | 휘두름 정점 cm/s | 떨림 p95 Vesper 처음 / 중간 / 끝 | 보조 손목 최대 ° (소스 2차) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 25 | 91.7 → **5.0** (91.7 → 4.1) | 41.7 · 2.8 → **0 · 11.6** (41.3 → 0) | 75.2 → 55.4 | 93.3 · 51.1 → 4.2 · 48.3 (60.3 → 61.1) | 492.6 → 508.5 | 0.08 / 0 / 0.04 → 0.02 / 0 / 0.01 | 42.3 → 64.6 |
| 26 | 28.3 → **0** (9.1 → 0) | 90.0 · 0.6 → **2.5 · 9.6** (86.8 → 0) | 79.3 → 70.2 | 96.7 · 50.5 → 10.8 · 48.6 (60.2 → 61.8) | 313.2 → 261.2 | 0.02 / 0.03 / 0.04 → 0.02 / 0.02 / 0.03 | 57.2 → 62.1 |
| 27 | 12.5 → **0** (11.6 → 0) | 59.2 · 1.1 → 55.8 · 1.4 (38.0 → 15.7) | 71.1 → 34.7 | 35.0 · 49.0 → 26.7 · 48.2 (60.0 → 60.1) | 366.9 → 443.0 | 0.01 / 0.04 / 0.05 → 0.01 / 0.04 / 0.06 | 52.0 → 58.1 |
| 28 | 82.5 → **0** (81.8 → 0) | 69.2 · 1.6 → **4.2 · 3.0** (34.7 → 2.5) | 73.6 → **6.6** | 67.5 · 49.9 → 37.5 · 49.3 (58.0 → 62.7) | 262.1 → 527.6 | 0.02 / 0 / 0.02 → 0.02 / 0 / 0.01 | 106.5 → 88.9 |

새 선별 (가중치 grip 3 · stance 2 · swing 2 · attack 2 · clearance 1 · breakage 1 · cross 2 · head 2, 관통 근거 `all_polearm`):

| 순위 · seed · 점수 | 벌점 grip · stance · swing · attack · clearance · breakage · cross · head | Vesper 원 수치 (발 좌우 비 p90 · 궤적 폭 · 꼬임 · 머리 · 관통) | 상한 안 |
| :--- | :--- | :--- | :--- |
| **1 · 20261028 · 0.196** | 0.63 · 0.31 · 0 · 0.19 · 0.07 · 0 · 0 · 0 | 4.05 · 2.17 · 0 · 4.2% (최소 3.0 cm) · 6.6% | 예 (유일) |
| 2 · 20261025 · 0.285 | 0.96 · 0.37 · 0.04 · 0.02 · 0.55 · 0 · 0 · 0 | 4.35 · 2.64 · 5.0 · 0 · 55.4% | 관통 초과 |
| 3 · 20261027 · 0.368 | 0.73 · 0.33 · 0.16 · 0 · 0.35 · 0 · 0 · **1.0** | 4.15 · 2.68 · 0 · 55.8% (1.4 cm) · 34.7% | 머리 초과 |
| 4 · 20261026 · 0.403 | 0.89 · 0.29 · 0.50 · 0.53 · 0.70 · 0 · 0 · 0 | 3.97 · 1.26 · 0 · 2.5% · 70.2% | 관통 초과 |

파지 벌점(망가진 띠)을 빼도 순위가 같다(0.089 · 0.117 · 0.277 · 0.280) — 선택은 띠에 기대지 않는다. 운영 낫 대비: 고른 후보 휘두름 정점 528 cm/s(운영 1,221 ~ 2,068), 궤적 폭 2.17(운영 2.71 ~ 4.64), 꼬임 0(운영 0 ~ 16.3), 머리 4.2%(운영 0), 관통 6.6%(운영 0 ~ 34.4).

**검 기준 재실행(`--only hashes,select,dirty` PASS · 실패 0, 실행 `P81Run1026_193811` · Job `job_20261026_193812_763264` — 검증용, 애셋 · Job 은 정리했다):** 새 축(41/41 키 프레임 손목 방향, 목표 뒤바뀜 0%)으로도 **seed 20261025** 선택(0.076 · 2위 seed 27 0.131 · '서 있기' seed 26 4위) — 이전(`P81Run1026_180733`)과 같은 선택. Vesper 파지 100% · 간격 p50 4.96 cm · 휘두름 정점 321.4 → 332.8 cm/s · 꼬임 0 · 머리 0(최소 20.5 cm) · 관통 69.4%(비파지 0 — 검 손잡이 규칙 그대로) · 보조 손목 최대 41.6°. 머리 근접은 seed 26 · 28 이 4.2%(최소 9.4 · 3.5 cm).

**읽는 법:**
- 팔 꼬임은 축 정정으로 사라졌다(4 seed Vesper 0 ~ 5%, 소스 2차 0 ~ 4.1% — 1차 수준). 남은 seed 25 의 5% 는 1차부터의 4.9%.
- 손-머리는 3 seed 가 운영 수준에 가까워졌지만 **seed 27 은 1차부터 손이 머리 2.5 cm 까지 왔고(4.1%) 목표 이동(보조 어깨 쪽 p50 19.6 cm)이 키워 Vesper 55.8%** — 지표가 잡아 3위로 밀렸다. **seed 28 도 5 프레임(4.2%)은 머리 3 cm 안** — 상한 5% 안이지만 Persona 에서 볼 곳.
- 관통은 seed 마다 크게 다르다(6.6 ~ 70.2%). 낫을 양손으로 몸 앞에 쥐면 위팔이 몸통에 닿는 자세가 남는다 — 파지를 지키며 관통을 없애는 것은 8-4. 사용자 Persona(같은 날 밤): 선택 애니도 팔이 머리 · 배 · 가슴을 약간 통과한다 → 8-4 범위를 부위별이 아닌 **몸 전체 관통 보정**(머리 포함)으로 보강했다(로드맵 표 · '8-4 범위 보강 근거').
- seed 28 보조 손목 89° 는 1차부터(107°) — keep 이 지킨다(B 의 알려진 한계).
- **수치 통과는 품질 합격이 아니다** — 이번 결함도 수치 검사가 못 잡아 사용자가 눈으로 찾았다. 머리 지표는 머리 본(두개 바닥) 한 점과의 거리라 메시 접촉이 아니고, 관통은 위팔-몸통 · 골반 · 넓적다리만 본다.

**Persona 확인 목록 (낫 정정):** 선택 `/Game/Animation/Test/AIAnimation/P81Run1026_192547/AS_Vesper_Sickle_KimodoSlashPick`(seed 20261028) · 2위 `…/P81Run1026_192547/Work/job_20261026_192555_f991aa/A1/Candidates/Cand_BVH_kimodo_00`(seed 20261025 — 이전 선택과 같은 seed, 관통 55%) · 3위 `…/Cand_BVH_kimodo_02`(seed 20261027 — 머리 지표 55.8%: 지표가 눈과 맞는지) · 비교(망가진 이전 결과) `/Game/Animation/Test/AIAnimation/P81Run1026_184807/AS_Vesper_Sickle_KimodoSlashPick`(seed 20261025).

#### 8-1 파지 띠 정정 — 대상 메시 기준 간격 (개정 11 보강 4 — 2026-10-26 밤)

**진행:** 낫 정정의 FAIL 2건(파지 띠)은 띠 정의 문제였다 — 띠 = (요청 간격 ± 13) × 대상 pelvis scale(Vesper 1.052)인데 FK 리타깃은 관절 회전을 복사해 손 간격이 어깨 폭 · 팔 길이를 따른다(Vesper = 소스 × 0.79). 1.052 × (s − 13) > 0.79 s ⇔ s > 52 라 낫 간격은 어떻게 잡아도 Vesper 가 띠 밖이고, 어깨가 넓은 메시는 반대로 띠를 넘친다 — Vesper 전용이 아닌 범용 정의 문제. 사용자 결정(같은 밤): ① 띠를 각 대상 메시의 골격 치수로 계산(측정만 바뀌고 애니는 그대로) ② 요청 간격을 대상 메시 기준으로도 받아 계획 단계에서 생성 간격으로 변환(근사). 정확한 손 부착 · 몸 전체 관통은 8-4. C++ · MCP Tool 변경 없음, `kimodo_run.py` 변경 없음.

**측정 (기록 Job `job_20261026_192555_f991aa` — 소스 2차 NPZ 와 Vesper 후보 4개 profile, 생성 없음):** 기준 포즈 치수(관절 사이 거리) — SOMA(Kimodo BVH 표준 T 포즈 오프셋) 어깨 관절(LeftArm ↔ RightArm) 32.96 · 위팔 28.74 · 아래팔 27.11 cm(팔 55.85), Vesper(`inspect_skeleton` ref_component · 템플릿 체인 LeftArm/RightArm) 어깨 관절(upperarm_l ↔ r) 23.96 · 위팔 24.38 · 아래팔 23.28 cm(팔 47.66). 비 = 어깨 0.727 · 위팔 0.848 · 아래팔 0.859 · 팔 0.853 · pelvis 1.052. 실측 Vesper / 소스 손목 간격 p50 비 0.792 / 0.786 / 0.801 / 0.786(seed 25 ~ 28), 파지선(손목 L − R)과 어깨선의 cos p50 0.79 ~ 0.97(낫을 몸 앞에 가로로 쥔다).

| 대안 (소스 2차 간격 → Vesper 간격 예측) | p50 오차 (4 seed) | 프레임별 \|오차\| p50 · p90 (4 seed 평균) | 계획 때 쓸 수 있나 |
| :--- | :--- | :--- | :--- |
| 지금 — × pelvis scale 1.052 | +15.1 ~ +16.7 cm | 16.1 · 16.5 cm | 예 |
| A1 단일 비 — 팔 길이 비 0.853 | +3.2 ~ +4.3 | 3.8 · 4.0 | 예 |
| A2 단일 비 — 스팬(어깨 + 2 × 팔) 0.825 | +1.4 ~ +2.5 | 2.1 · 2.3 | 예 |
| **B 사상 — 대상 = W_대상 + k × (생성 − W_생성)**(어깨 관절은 그 폭대로, 나머지 팔 부분은 팔 길이 비 k) | **−1.0 ~ +0.1** | **0.45 · 0.92** | **예 — 두 골격 치수 4개** |
| C 프레임별 — \|k_어깨 · 어깨 차 + k_위팔 · 위팔 차 + k_아래팔 · 아래팔 차\|(소스 트랙) | −0.3 ~ −0.1 | 0.20 · 0.45 | 아니오 — 생성 뒤 소스 트랙이 있어야 |

- C 가 프레임마다 0.2 cm 로 맞는다 = FK 리타깃(per_bone 정렬) 모델 확인: 대상 본 벡터 = 소스 본 벡터 × 길이 비. B 는 C 에 '파지선 ∥ 어깨선'을 둔 닫힌 식(\|k · g + (k_어깨 − k) · D_어깨\|, g ∥ D) — 파지선이 세로에 가까울수록 대상 간격을 낮게 본다(Vesper 생성 75 cm 에서 최대 −4.3 cm, 어깨가 넓은 메시 W 40 · k 1.04 에서 −6.6 cm). 띠 폭(대상 ±11 cm) 안이고 결과는 select 가 대상에서 직접 잰다 — 빗나가면 `GRIP_NOT_REACHED` 로 드러난다.
- C 를 refine 목표(키 프레임마다 정확한 생성 간격)나 소스 수치(대상 간격 예측)에 쓰면 ≤ 1 cm 더 맞지만 `kimodo_run` · `solve_grip` 이 대상 치수를 받아야 하고 소스 띠가 프레임마다 달라진다 → 이번엔 **B**, C 는 근거 · 8-4 후보로 남긴다.
- 요청 필드: `spacing_cm` 의 뜻(생성 골격 간격)을 바꾸지 않고 새 필드 `target_spacing_cm`(대상 메시 간격)를 넣었다 — 기록 Job 재계산 재현성 유지, 둘 다 주면 `CONFLICTING_FIELDS`.

| 항목 | 바꾼 것 | 곳 |
| :--- | :--- | :--- |
| 간격 사상 (`motion_metrics` 버전 5) | `arm_dims`(역할 본 기준 포즈 위치 → 어깨 관절 폭 · 팔 길이) · `gap_map`(두 골격 치수 → {생성 어깨 · 대상 어깨 · 팔 길이 비}) · `map_gap` · `grip_spacing`(요청 하나 → 생성 · 대상 간격, 허용 생성 13 · 대상 13 × k, 두 띠, 사상 — 대상 띠 = 생성 띠의 상). `grip_band` 는 자루 무기면 '그 골격 간격 ± 허용'(scale 을 곱하지 않는다), 검 손잡이는 그대로 ≤ 20 × pelvis scale. `grip` 기록에 `tolerance_cm` | `motion_metrics.py` |
| 생성 골격 치수 | `SOMA_ARMS = {shoulder_width_cm 32.96, arm_cm 55.85}` — SOMA77 은 고정 골격이라 상수(기록 Job BVH 오프셋 실측 · 근거 주석). 통합 `scythe` 가 그 실행 BVH 와 같은지 본다 | `providers/local_ai.py` |
| 대상 치수 | `RetargetPipe.selection_bones` 가 같은 `inspect_skeleton details` 로 `arm_dims`(어깨 = LeftArm 체인 시작, 팔꿈치 = 손목 부모, 손목 = 체인 끝의 ref_component) | `providers/builtin.py` |
| 계획 (단일 원천) | local_ai 가 간격 요청이 있으면 대상 측정 본 → 사상 → `grip_spacing` 을 한 번 풀어 generate 규칙(`spacing_cm` = 생성 간격 — 러너 그대로 · `target_spacing_cm` · `band_cm` · `target_band_cm` · `spacing_map` · `spacing_from` 문구)과 select 입력(`grip_spacing` · `bones` — 다시 재지 않는다)에 싣는다. 한계 `GRIP_SPACING_MAPPED`(두 간격 · 두 띠 · 근사 설명). 에디터 없음 → `PROVIDER_UNAVAILABLE EDITOR`, 대상 팔 위치 없음 → `TARGET_ARMS_UNKNOWN`, 생성 골격 두 팔(어깨 폭 + 팔 × (0.98 + 0.92) = 139.1 cm)이 닿지 않으면 `GRIP_SPACING_OUT_OF_RANGE` | `providers/local_ai.py` · `local_ai/refine.py`(`plan(spacing=…)`) |
| select | 대상 띠 = 계획의 `grip_spacing.target_cm ± tolerance_cm.target`. 버전 4 계획(`grip_spacing_cm`)은 실행 때 `PLAN_OUTDATED`(폴백 없이 멈춤 — 다시 계획). `GRIP_NOT_REACHED` 문구 = 대상 띠 · 근거(자루 무기 / 검 손잡이), `band_cm` 필드 | `providers/builtin.py` |
| 요청 · 설명 | `generation.refine.grip.target_spacing_cm` (0, 100] · `spacing_cm` 과 배타 | `request.py` · `server.py` · §9 · `Tools/mcp/README.md` |
| 테스트 | pytest **442**(432 + 10 — 기록 Job 수치로 사상 · 역사상 · 띠, 요청 하나 → 두 띠, 다른 체형 3개(Vesper · 어깨 넓은 메시 · 좁고 팔 긴 메시 — FK 모델로 옮긴 대상 간격이 요청 0.5 cm 안, 파지선 30° 기울어도 띠 안), 대상 기준 요청의 계획 → 러너 → select, 생성 기준 요청의 대상 띠 · `GRIP_NOT_REACHED` 문구, 에디터 없음 · 팔 위치 없음 · 닿지 않는 간격, 옛 계획 `PLAN_OUTDATED`, 요청 필드 2 · 기존 기대값 수정: 버전 5 · 띠에 scale 없음). FakeEditor 가짜 Vesper 에 팔 본(실제 기준 포즈 위치). 통합 새 섹션 `regrip`(애셋 0 — 기록 Job f991aa 후보를 새 띠로) · `scythe` 대상 기준 60 cm · SOMA 상수 = BVH · 사상이 Vesper 간격 p50 을 3 cm 안으로(`MAP_TOLERANCE_CM`) · `plan` 버전 5 · 대상 팔 치수 | `test_refine.py` · `test_select.py` · `conftest.py` · `anim_gen_phase8_1_test.py` |

**결과 ① 기록 재계산 (`--only hashes,plan,recompute,regrip,dirty` PASS · 실패 0, 애셋 0):** Job f991aa(생성 간격 60)의 Vesper 띠 [49.46, 76.83](버전 4) → **[35.95, 58.13]**(47.04 ± 11.09). 4 후보 Vesper 파지 4.2 / 10.8 / 26.7 / 37.5 → **100 / 100 / 100 / 100%**, 사상 예측 vs 실측 Vesper 간격 p50 47.95 / 48.58 / 47.15 / 49.37 vs 48.32 / 48.57 / 48.17 / 49.28(오차 −1.02 ~ +0.09 cm). 선택은 그대로 seed 20261028(0.196 → 0.071 — 파지 벌점 0.63 → 0), 순위 같음(seed 25 0.093 · 27 0.222 · 26 0.224) — FAIL 원인이 풀렸다. 검 기록 `recompute`(간격 없음)도 그대로(seed 25 0.0835 vs 0.1329).

**결과 ② 낫 재생성 (`--only hashes,plan,recompute,scythe,dirty` PASS · 실패 0, 실행 `P81Run1026_205832` · Job `job_20261026_205840_56d522`, 잡 241초 · Kimodo 219초):** 같은 프롬프트 · seed 20261025 ~ 28 · `meet` · **`target_spacing_cm` 60** → 생성 75.19 cm(규칙 · select 띠가 한 값, 한계 `GRIP_SPACING_MAPPED`). SOMA 상수 = 이 실행 BVH 기준 포즈(32.96 · 55.85). 사상 예측 vs Vesper 간격 p50: 60.15 / 61.52 / 59.59 / 62.29 vs 60.92 / 61.36 / 60.50 / 62.23(오차 −0.91 ~ +0.16 cm, 비 0.797 ~ 0.810).

같은 seed 전(`P81Run1026_192547`, 생성 간격 60 · 버전 4 띠) → 후(대상 60 → 생성 75.19 · 버전 5 띠), Vesper(소스는 2차):

| seed | 파지 % · 띠 | 손목 간격 p50 Vesper (소스) | 꼬임 % | 손-머리 10 cm 안 % · 최소 cm | 관통 % | 휘두름 정점 cm/s | 궤적 폭 | 발 좌우 비 p90 | 보조 손목 최대 ° Vesper (소스 2차) | 목표 이동 p50 · 최대 cm |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 25 | 4.2 [49.5, 76.8] → **100** [48.9, 71.1] | 48.3 (61.1) → **60.9** (75.4) | 5.0 → 5.0 | 0 · 11.6 → 0 · 16.3 | 55.4 → 65.3 | 508.5 → 592.5 | 2.64 → 2.68 | 4.35 → 4.37 | — (64.6) → 70.9 (67.9) | 0 · 27.9 → 11.3 · 47.3 |
| 26 | 10.8 → **100** | 48.6 (61.8) → **61.4** (77.0) | 0 → 0 | 2.5 · 9.6 → 3.3 · 5.9 | 70.2 → 58.7 | 261.2 → 251.7 | 1.26 → 1.26 | 3.97 → 3.95 | — (62.1) → 67.8 (65.7) | 2.3 · 12.4 → 15.8 · 27.3 |
| 27 | 26.7 → **100** | 48.2 (60.1) → **60.5** (74.7) | 0 → 0 | 55.8 · 1.4 → **5.8 · 2.1** | 34.7 → 9.1 | 443.0 → 454.8 | 2.68 → 2.77 | 4.15 → 4.18 | — (58.1) → 57.8 (57.0) | 19.6 · 28.0 → 33.2 · 42.0 |
| 28 | 37.5 → **100** | 49.3 (62.7) → **62.2** (77.9) | 0 → 0 | 4.2 · 3.0 → **0 · 13.6** | 6.6 → **0.8** | 527.6 → **636.8** | 2.17 → 2.68 | 4.05 → 3.98 | — (88.9) → 103.1 (100.0) | 0 · 2.8 → 0 · 13.8 |

(목표 이동 '전' 은 같은 1차에 생성 간격 60 으로 푼 값 — 실행 기록과 같다. 손 뒤바뀜 목표 = 1차 그대로 4.9 / 0 / 0 / 0%, IK 늘어남 0, 소스 파지 97.5 ~ 100%, 떨림 Vesper p95 ≤ 0.06.)

새 선별 (가중치 그대로, 관통 근거 `all_polearm`):

| 순위 · seed · 점수 | 벌점 grip · stance · swing · attack · clearance · breakage · cross · head | 상한(꼬임 20 · 머리 5 · 관통 40%) 안 |
| :--- | :--- | :--- |
| **1 · 20261028 · 0.044** | 0 · 0.30 · 0 · 0.03 · 0.01 · 0 · 0 · 0 | 예 (유일) |
| 2 · 20261027 · 0.093 | 0 · 0.34 · 0.29 · 0 · 0.09 · 0 · 0 · 0.03 | 머리 5.8% 초과 |
| 3 · 20261025 · 0.107 | 0 · 0.37 · 0.07 · 0.03 · 0.65 · 0 · 0 · 0 | 관통 65.3% 초과 |
| 4 · 20261026 · 0.231 | 0 · 0.29 · 0.60 · 0.55 · 0.59 · 0 · 0 · 0 | 관통 58.7% 초과 |

운영 낫 대비(같은 측정 — 새 띠 [48.91, 71.09]): 운영 양손 구간 간격 p50 54.8 / 54.9 / 63.3 / 66.2 cm · 띠 안 24.0 / 28.4 / 35.9 / 33.3%(양손 구간만 쥔다) · 휘두름 정점 1,221 ~ 2,068 cm/s · 궤적 폭 2.71 ~ 4.64 · 꼬임 0 ~ 16.3% · 머리 0% · 관통 0 ~ 34.4%. 고른 후보: 간격 p50 62.2(운영 범위 안) · 클립 전체 띠 안 · 정점 637(운영의 1/1.9 ~ 1/3.2) · 궤적 폭 2.68 · 꼬임 0 · 머리 0(최소 13.6 cm) · 관통 0.8%.

**결과 ③ 검 기준 재생성 (`--only hashes,select,dirty` PASS · 실패 0, 실행 `P81Run1026_210325` · Job `job_20261026_210326_971ad6` — 검증용):** 간격 요청이 없으면 계획 · 러너 · 띠가 그대로다 — seed 20261025 선택(0.076 · 2위 seed 27 0.131 · '서 있기' seed 26 4위), Vesper 파지 100%(≤ 21.05 cm) · 간격 p50 4.96 cm · 정점 332.8 cm/s · 관통 69.4%(비파지 0) — 보강 3 의 검 재실행(`P81Run1026_193811`)과 같은 수치.

**읽는 법:**
- 띠 FAIL 은 정의 문제였고 측정만 고쳐 풀렸다(기록 재계산 — 애니 그대로). 새 생성은 Vesper 손목 간격이 요청 60 근처(60.5 ~ 62.2 cm, 사상 오차 ≤ 0.9 cm)에 떨어졌다 — 운영 낫 양손 구간(55 ~ 66)과 같은 폭.
- 대가: 생성 간격이 60 → 75 로 넓어져 목표 이동이 커졌다(seed 25 최대 47 cm · seed 27 p50 33 cm). seed 25 관통 55 → 65% · 왼발 접지 미끄러짐 p95 5.3 cm/s, seed 28 보조 손목 최대 103°(1차부터 107° — keep 이 지킨다)는 남았다. seed 27 은 머리 근접이 55.8 → 5.8%(최소 2.1 cm)로 크게 줄었지만 상한 5% 를 넘는다.
- 선택(seed 28)은 이전 선택과 같은 seed 이고 머리 · 관통이 줄고(4.2 → 0%, 6.6 → 0.8%) 정점 · 궤적 폭이 커졌다(528 → 637, 2.17 → 2.68) — 그래도 운영 낫의 1/2 ~ 1/3 속도(흐느적 → D · 8-3).
- 사상은 '파지선 ∥ 어깨선' 근사다 — 이번 낫(가로로 쥠)에서 오차 ≤ 1 cm, 세로로 세운 자루 · 어깨가 넓은 메시에서는 몇 cm 커진다(띠 안 · 통합이 3 cm 넘으면 FAIL). 키 프레임마다 정확히 맞추는 것(위 표 C)과 손을 자루에 붙이는 것은 8-4.
- **수치 통과는 품질 합격이 아니다** — 낫은 손에 없고(무기 본 없음) 손가락은 고정 포즈다. 머리 · 관통 지표는 근사(머리 본 한 점 · 위팔-몸통 · 골반 · 넓적다리만)라 Persona 에서 눈으로 본다.

**Persona 확인 목록 (파지 띠 정정):** 선택 `/Game/Animation/Test/AIAnimation/P81Run1026_205832/AS_Vesper_Sickle_KimodoSlashPick`(seed 20261028 — Vesper 손목 간격 p50 62.2 cm) · 2위 `…/P81Run1026_205832/Work/job_20261026_205840_56d522/A1/Candidates/Cand_BVH_kimodo_02`(seed 20261027 — 머리 5.8%, 최소 2.1 cm) · 3위 `…/Cand_BVH_kimodo_00`(seed 20261025 — 관통 65%) · 비교(직전 선택, 생성 간격 60 · Vesper 간격 49 cm) `/Game/Animation/Test/AIAnimation/P81Run1026_192547/AS_Vesper_Sickle_KimodoSlashPick`(seed 20261028) · 운영 `/Game/Animation/Hero/Vesper/Sickle/Actions/AS_Vesper_Sickle_Attack3`(양손 구간 간격 p50 63.3 cm).

#### 8-2 Vesper 캡처 (개정 12 — 2026-10-26 구현 · 검증)

**진행:** 설계 초안(캡처 방식 비교 · Tool 시그니처 · anim_gen 연결 · 출력 · 표시 · 테스트 · 커밋 단위 — 공유 노트 `phase8-2-design.md`) → 사용자 "추천안으로 착수"(결정: 캡처 루트 `Tools/mcp/results/capture/` · 움직임은 APNG 만 — MP4 는 Blender 4.4 내장 FFmpeg 로 필요하면 후속) → C++ Tool · 두 구성 빌드 → `-unattended` 에디터 스파이크 4회(엔진 함정 3건 정정 — 감사 §19) → anim_gen 연결 · pytest → 통합 · 회귀.

**방식:** 임시 `FPreviewScene`(트랜지언트) 안에 스켈레탈 메시(단일 노드 — `SetPosition` → `RefreshBoneTransforms` → `RecreateRenderState`) · 무광 배경판 · 바닥 판(엔진 `LevelColorationUnlitMaterial` 동적 인스턴스) · 카메라 왼쪽 위 주광(그림자) + 보조광 + 썸네일 환경 큐브맵, `USceneCaptureComponent2D` 정사영 · `FinalColorLDR` · ShowOnly 목록 · Lumen · SSR · TAA(→ FXAA) · 모션 블러 · 블룸 · 자동 노출 · DOF · 비네트 끔 · 노출 고정 · 2배 슈퍼샘플 → 읽기 → 줄임 → PNG. 썸네일 렌더러(원근 · 프리뷰 메시 · 가운데 시각 고정) · 하이레즈 스크린샷(창 의존) · Movie Render Queue(레벨 시퀀스 · 플러그인)는 기각.

**시그니처:**

```jsonc
capture_animation(asset, mesh, facing ("+Y"|"-Y"|"+X"|"-X"), output_dir (CaptureOutputRoots 아래 새 · 빈 폴더),
  times?[] | count? (1 ~ 12, 기본 4), views? (front · side), label?,
  cell_height_px 512, max_aspect 2, margin 0.08, bounds_max_samples 600, sheet_max_px 3000, supersample 2,   // 앞 5개 = blender REVIEW_RENDER
  sequence? {fps 15, cell_height_px 320, start?, end?, max_frames 150} | null,
  compare? {label?, rows[[이미지 …] 행마다]} (ImportSourceRoots 아래), lighting? {exposure_bias, key, fill, sky}, max_seconds 120)
→ {asset, mesh, facing, length, frame_rate, frames_total, dir, frames[{row, time, frame, frame_time, view, path, sha1, subject_px, coverage_pct, touches_edge}],
   sheet, compare{path, label, own_columns, compare_columns, size, scale} | null, sequence{dir, fps, count, frames[], times[], size, truncated, seconds} | null,
   layout{rows[{time, frame, frame_time, clamped, pose_center}], columns[], cell_height, gap, size, scale},
   camera{view: {look, right, ortho_width_cm, ortho_height_cm, resolution, cm_per_px}}, bounds{min, max, frames_sampled, from, boxed_bones}, render{…}, cells_touching_edge, seconds}
// 오류: BAD_REQUEST(SKELETON_MISMATCH · OUTPUT_DIR_NOT_EMPTY · RELATIVE_PATH · CONFLICTING_FIELDS …) · OUTPUT_PATH_NOT_ALLOWED(CAPTURE_ROOT) · IMPORT_SOURCE_NOT_ALLOWED ·
//       ASSET_NOT_FOUND · CAPTURE_FAILED(NO_SCENE · RENDER_TARGET · READBACK · WRITE_FAILED · IMAGE_UNREADABLE · NO_POSE) · UNEXPECTED_DIRTY(새 더티 하나라도 — 파일은 남음, details.dir)
// 경고: CAPTURE_TRUNCATED(max_seconds) · CAPTURE_SUBJECT_AT_EDGE(잘린 칸)
// anim_gen: request.review.capture → 계획 단계 capture{asset "$asset", mesh, facing, rows_from render|request, times, count, views, sequence, compare, label, layout, dir}
//           → Job review.capture{ok, shows target_mesh, sheet, compare_sheet, animation{path, frames, fps, delay, size, bytes}, frames, sequence, camera, layout, bounds, rows_from, …}
```

**구성:**

| 파일 | 내용 |
| :--- | :--- |
| `Plugins/AnimGraphMcp/…/Core/AnimMcpCapture.{h,cpp}` | 장면 · 범위(LOD0 정점 → 본 로컬 상자, 정점 없는 본 제외) · 카메라 맞춤(`FitView` = `review_render.py frame_view`) · 셀 렌더 · 라벨(`FCanvas`) · 시트 · 비교 시트 · 연속 프레임 · 피사체 범위 · 가드 |
| `…/Tools/AnimMcpTools_Capture.cpp` · `AnimMcpTools.h` · 모듈 등록 | Tool `capture_animation`(41번째) |
| `…/Core/AnimMcpGeneration.{h,cpp}` · `Bridge/AnimMcpTypes.{h,cpp}` · `AnimGraphMcpEditor.Build.cs` | ini `CaptureOutputRoots` · `ResolveCaptureDir` · `get_editor_status.generation.capture_output_roots` · 오류 `CAPTURE_FAILED` · ImageCore 의존 |
| `…/Tests/AnimMcpCaptureTests.cpp` | Automation `AnimGraphMcp.Generation.Capture` — 카메라 맞춤 · 시트 축소 · 시각 펼치기 · 샘플 프레임(Blender 수식 손 계산값) · 출력 폴더 규칙 |
| `Config/DefaultEngine.ini` | `+CaptureOutputRoots=Tools/mcp/results/capture/` |
| `Tools/mcp/anim_graph_mcp/server.py` | 프록시 함수 `capture_animation` |
| `Tools/mcp/anim_gen/apng.py` | APNG 조립(재압축 없이 IDAT → fdAT, CRC · 순번) · 검사 |
| `Tools/mcp/anim_gen/providers/review.py` · `providers.json` · `registry.py` · `router.py` · `executor.py` · `request.py` · `server.py` | 파이프 `review` · capture 단계 · Job `review.capture` · 요청 `review.capture` · Tool 설명 |
| `tests/test_capture.py` · `conftest.py` · `test_router.py` | pytest 37건(APNG · 요청 · 계획 · 실행 · blender 경로 비교 칸) · FakeEditor 캡처 흉내(작은 진짜 PNG) · Provider 목록에 `review`(기대된 변화) |
| `Tools/mcp/anim_gen_phase8_2_test.py` | 통합 — hashes · automation · tool · guard · existing · chain · dirty |

**8-2 완료 기준:**

1. 캡처 Tool — 대상 메시를 시각 × 뷰 정사영(전 프레임 고정 카메라) PNG · 시트로, 애셋 0 · 새 더티 0 · 원본 SHA-256 불변 · 같은 입력 = 같은 픽셀, `-unattended` 에디터에서 동작.
2. 소스 골격과 나란히 — `review.render` 와 같은 행 · 열 · 셀 규칙, render 가 있으면 비교 시트.
3. 움직임 — 프레임 연속 이미지 + APNG(설치 없음).
4. anim_gen 연결 — 모든 경로 capture 단계 · Job `review.capture` · 캡처 실패는 한계만.
5. 채팅 표시 — 시험 대상 3건 시트 · 비교 시트 · APNG 를 SendUserFile 로 보고에 첨부.
6. 회귀 없음 — pytest · Phase 1 ~ 7 · 8-1 통합 실패 0 · 두 구성 빌드 경고 0.
7. 사람 판정 — 캡처는 근거일 뿐 품질 합격이 아니다(§16-9).

**결과 (2026-10-26 — `anim_gen_phase8_2_test.py` 전 섹션 PASS):**

| # | 기준 | 결과 |
| :---: | :--- | :--- |
| 1 | 캡처 Tool | ✅ DebugGame `-unattended` 에디터에서 칼 시험 4초 클립 6행 × 2뷰 1.1초(+ 15 fps 61장 1.7초 — 한 번 3.0초, 첫 호출 준비 0.9 ~ 2.9초) · 미저장 0 → 0 · Content 변경 0(캡처) · 시험 대상 3개 · 스켈레톤 · 메시 SHA-256 불변 · 같은 입력 두 번 = 모든 칸 SHA-1 같음 · 잘린 칸 0 · 행마다 포즈 다름(`pose_center`). 거부(루트 밖 · 루트 자체 · 상대 · 비지 않음 · 루트 밖 비교 이미지 · 잘못된 정면 · times + count · 없는 애셋)는 파일 · 더티 0. Automation `AnimGraphMcp.Generation.Capture` 통과 |
| 2 | 소스 골격과 나란히 | ✅ 정면(몸 왼쪽 = 화면 오른쪽) · 측면(정면 = 화면 오른쪽) 축 · 셀 512 · 폭 비율 · 바닥 띠가 Blender 와 같다. 비교 시트(행 = 같은 시각, 열 = Vesper 정면 · 측면 + 소스 골격 정면 · 측면) — 시험 대상 3건 + chain Job. 행은 시각으로 맞는다(프레임 번호는 각 fps — CMU 120 · 애셋 30, 캡처 시각 차 ≤ 0.011초) |
| 3 | 움직임 | ✅ 연속 프레임(뷰를 나란히 526 × 320) → APNG 61장 · 6.6 ~ 8.0 MB(4초 · 15 fps) — 설치 없음 |
| 4 | anim_gen 연결 | ✅ pytest 37건(재사용 · 편집 · blender 경로, 루트 없음 = 단계 없음, 에디터 없음 = 실행 때, 포장 앞, 실패 = 한계 · Job SUCCEEDED, `UNEXPECTED_DIRTY` = 중단, 렌더 실패 = count 행). 통합 chain: CMU 01_01 0 ~ 3초 BVH → blender(render 4) → 리타깃 → capture — Job 15초 SUCCEEDED · `review` 맨 위 = 소스 골격 · `review.capture` = 같은 행 8칸 · 비교 시트 · APNG 46장 · 출력 `CaptureOutputRoots/<job>/A1` |
| 5 | 채팅 표시 | ✅ Saved 밖 캡처 루트의 비교 시트 · APNG(시험 대상 3건 · 6파일)를 SendUserFile 로 전달(같은 경로가 Saved 아래면 거부 — 설계 단계 실측). APNG 가 채팅 미리보기에서 움직이는지는 사용자 눈 확인 |
| 6 | 회귀 없음 | ✅ pytest **479건**(기존 442 + `test_capture.py` 37 — 기존 기대값 변경 1: Provider 목록에 파이프 `review`). Development · DebugGame 빌드 코드 경고 0(툴체인 버전 안내만). 통합 `anim_gen_phase1_test.py` · `phase2` · `phase4` · `phase6` · `phase7`(Tool 수 검사 `== 40` → `≥ 40` — 기대된 변화) · `phase3`(Provider 수 9 → 10 — 기대된 변화) · `phase5`(실제 Kimodo) PASS · `phase8_1` 전 섹션 실행에서 plan 1건만 FAIL — 기본 섹션 순서가 exp1(실행 폴더에 애셋을 만듦) → plan(실행 폴더가 없어야 함)이라 생기는 테스트 순서 문제(8-2 와 무관), `--only hashes,plan,dirty` 단독 PASS. 첫 회귀 시도에서 Phase 5 도중 에디터가 종료 코드 3 으로 내려갔다(같은 에디터로 Phase 1 ~ 7 · 캡처를 연달아 돈 뒤 — 크래시 로그는 Saved 라 세션이 못 읽음), 새 에디터로 다시 돌려 PASS |
| 7 | 사람 판정 | ⏳ 캡처 결과(아래)를 보고 — 캡처가 나왔다고 품질 합격이 아니다 |

**시험 대상 캡처(통합 `existing` — 실행 `P82Run1026_232446`, 출력 `Tools/mcp/results/capture/P82Run1026_232446/<이름>/{sheet.png, compare.png, animation.png}`):** `kimodo_sword_1025`(기준 칼 시험) · `p81_sword_pick`(8-1 수정안 뒤 검 선택 seed 20261025) · `p81_scythe_pick`(8-1 파지 띠 정정 뒤 낫 선택 seed 20261028). 비교 칸 = 그 애셋을 만든 Job 의 Blender 소스 골격 프레임.

**읽는 법 · 한계:**
- 캡처는 시퀀스를 메시에 그대로 입힌 프리뷰다 — 무기가 없고(8-4), 옷 · 머리카락 물리가 돌지 않으며(천 시뮬레이션 끔 — 스키닝 그대로), 게임 AnimBP 레이어(왼손 IK · 조준 보정 · 레이어 블렌드)가 없고, 조명은 프리뷰 조명이다. 게임 화면과 다를 수 있다.
- 카메라는 전 프레임 범위에 고정이라 루트 이동이 큰 클립은 캐릭터가 작게 보인다(칼 시험 0.43 cm/px).
- APNG 는 크다(4초 6.6 ~ 8.0 MB) — 필요하면 `sequence.fps` · `cell_height_px` 를 낮춘다. MP4 는 후속(Blender 내장 FFmpeg).

#### 8-3 자동 보정 (개정 13 — 2026-10-27 구현 · 검증)

**진행:** 설계 초안(구간 탐지 · 가속 · 트림 · op 사전 · 보정 위치 · 연결 · 시그니처 · 테스트 — 공유 노트 `phase8-3-design.md`) → 사용자 "추천안으로 착수"(A 위치 분리: 시간 = 대상 · 다리 = 소스 Blender, B 낫 시험 대상 둘 다(`P81Run1026_192547` · `_205832`), C 가속 기본값, D C++ 비교 칸 루트) → **E0**(제품 코드 무변경 — 운영 Vesper 애니 · 시험 대상 측정, 기준 재현) → 사용자 결정 2건(발 간격 = **두 발 디딘 구간의 상한 3.0**(대상 기준 — 클립 p90 은 운영 공격과 구별이 안 됐다) · 정지 머리 트림 기본 켬 0.2초) → timing 구현 · 시험 대상 적용 → 다리 구현 · Blender 스파이크(무릎이 밖으로 빠짐 → 엉덩 둘레 회전 후 길이 맞춤) → 첫 실측에서 **Vesper 접지 미끄러짐이 줄지 않음**(소스만 고정) → 엔진 `PelvisMotionOp` 대조 → **리타깃된 다리의 모델**로 풀이(설계 정정 — 아래) → C++ 비교 칸 루트 · 두 구성 빌드 → 통합 · 회귀.

**설계 정정 (실측):**
1. 발 간격 지표 = 클립 p90 → **두 발을 디딘 프레임의 상한**. E0: 운영 낫 공격 타격 중 p50 4.1 ~ 5.0 · p90 4.9 ~ 7.4 로 생성물(3.7 ~ 5.1)과 비슷했고, 차이는 처음부터 끝까지 넓은 자세를 유지하는 것(운영 공격 끝 2.1 · 대기 1.9).
2. 다리 풀이 공간 = 소스 골격 → **리타깃된 다리의 모델**(대상 엉덩 관절 = 대상/소스 골반 높이 s × 소스 골반 절대 위치 + 골반 회전 변화 · 대상 엉덩 오프셋, 다리 = 소스 뼈 방향 · 대상 길이 — `PelvisMotionOp.cpp:297-325` · FK 체인 복사). 소스 발만 고정하면 Vesper p95 가 그대로이거나 늘었다(검 7.3 / 9.2 → 7.4 / 8.2, 낫 왼발 10.3 → 16.2 cm/s). 모델 풀이로 4건 모두 0.0 — 대신 소스 발이 움직인다(의도, 소스 p95 0.7 ~ 3.4 → 5.3 ~ 15.8 cm/s). 완료 기준 2 의 '소스 접지 미끄러짐 ≤ 0.5' 는 '대상 모델 예측 0 · Vesper 실측 ≤ 전' 으로 바꿨다.
3. 다리 IK = 원래 무릎 평면 → **엉덩 둘레로 먼저 돌린 뒤 길이만**(`foot_fix.swing_two_bone`). 원래 평면이면 발을 모을 때 무릎이 밖으로 빠졌다(무릎 간격 57.7 → 60.0 cm).

**시그니처:**

```jsonc
"fix": {
  "ops": [ { "op": "smooth", "sigma_frames": 1.0, "bones": "all", "root": true, "from_s": null, "to_s": null },
           { "op": "stance_width", "max_ratio": 3.0, "min_ratio": 1.2, "max_shift_cm": 25, "blend_s": 0.2, "keep_knee_bend": true },
           { "op": "foot_lock", "feet": ["left", "right"], "contacts": "auto", "height_ratio": 0.04, "speed_ratio": 0.25, "min_frames": 4,
             "blend_frames": 3, "lock_rotation": false } ],
  "timing": { "mode": "auto", "target_peak_cm_s": 1200, "max_rate": 2.0, "recovery_rate": 1.5,
              "antialias": 1.0,   // 개정 13 보강 — time_warp 의 앤티에일리어싱(ramp_pieces 는 없앴다)
              "swing": { "core_ratio": 0.5, "edge_ratio": 0.2 },
              "still": { "speed_cm_s": 30, "min_s": 0.3, "trim_head": true, "keep_head_s": 0.2, "trim_tail": true, "keep_tail_s": 0.3 } } }
// 계획 convert.inputs.fix{ops(기본값 · 순서), legs{left{hip, knee, ankle}, right}, target_dims{hip_width_cm, leg_cm, thigh_cm, shin_cm, pelvis_height_cm, rest{pelvis, hip_l, hip_r}}}
// 계획 timing{step, provider direct_key, inputs{…timing, loop, root_motion, bones{hands, body}}, resolved{signal, windows, rate, recovery_rate, segments, ops, warp, cut, length, before, preview} | null}
// Job: timing{…plan, source, asset, bones, before, after} · fix{source[{op: smooth, …} | {op: legs, space, scale, contacts, stance, pins, ik, before, after, source_before, source_after}], target{bones, leg_dims, ratio, contact_pct, slide_p95, knee_gap_min_cm}}
// capture_animation compare.rows 이미지 = ImportSourceRoots ∪ CaptureOutputRoots (C++ AnimMcpGeneration::ResolveCompareImage)
```

**구성:**

| 파일 | 내용 |
| :--- | :--- |
| `Tools/mcp/anim_gen/timing.py` | 순수 — 요청 정규화 · 신호(profile → 손목 · 전신 속도) · 탐지(핵심 · 휘두름 · 정지 머리 / 꼬리) · rate · 배율 곡선(보강 — 처음 판은 정수 프레임 retime 조각) · op(trim + time_warp) · warp(Hermite) · 전후 수치 · C++ trim/retime/time_warp 시뮬레이션(pytest 대조용) |
| `Tools/mcp/anim_gen/fix_ops.py` · `foot_fix.py` | op 사전(이름 · 기본값 · 범위 · 순서 · 다리 본) · 다리 풀이(접지 구간 상수 오프셋 · 배율 · 최소 간격 · 고정 · 대상 모델 · 엉덩 둘레 2본 IK) — 순수 |
| `Tools/mcp/anim_gen/blender/fix_legs.py` · `bvh_to_fbx.py` | Blender 안 실행 — 포즈 읽기 · 부모 순 로컬 회전 키 쓰기(오일러 연속), smooth · legs, 보고(대상 예측 · 소스) |
| `Tools/mcp/anim_gen/motion_metrics.py` | `detect_contacts` · `leg_dims`(+ 넓적다리 · 정강이 · 골반 높이) · `stance_map` · `legs_report` · `runs` |
| `Tools/mcp/anim_gen/soma.py` | SOMA77 상수(골반 · 체인 · 발 · 팔 치수)와 `is_soma` — `providers/local_ai.py` 에서 옮김(다시 내보냄) |
| `providers/blender.py` · `builtin.py` · `router.py` · `executor.py` · `request.py` · `review.py` · `service.py` · `server.py` | fix op 검사 · SOMA BVH 기본값 · 다리 본 · 대상 치수 · `fix_legs` 인자 · Job `fix` / `DirectKey` timing 단계 · `selection_bones` 다리 치수 · `legs_on_target` / 단계 순서 · 재사용 판정 / `_PRODUCING` · 최종 이름 · `DURATION_MISMATCH` 대체 / `fix.timing` / 비교 칸 생략 / Job 기본 필드 / Tool 설명 |
| `Plugins/AnimGraphMcp/…/Core/AnimMcpGeneration.{h,cpp}` · `AnimMcpCapture.cpp` · `Tests/AnimMcpCaptureTests.cpp` · `README.md` | `ResolveCompareImage`(캡처 루트도) · Automation 4건 추가 |
| `tests/test_timing.py` · `test_fix_legs.py` · `conftest.py` · `test_review.py` | pytest 58건 추가(timing 29 · 다리 29) · FakeEditor 속도 열 · retime/trim 길이 · 기대된 변화 3건(사전이 비어 있지 않음 — 사전 밖 op 로 막기 · 확장점 · 생성 경로가 op 를 싣는다) |
| `Tools/mcp/anim_gen_phase8_3_test.py` | 통합 — hashes · automation · plan · baseline · timing · legs · smooth · combined · capture · dirty |

**8-3 완료 기준:**

1. 흐느적 — `fix.timing` 계획이 탐지 규칙 · 매개변수를 보이고(기존 애셋은 구체 op · 결과 길이 미리보기까지), 시험 대상마다 새 애셋: Vesper 휘두름 정점 = 원 정점 × 계획 rate ± 10%(목표 1,200 · 상한 ×2.0), 정지 꼬리 ≤ 0.3초 + 1프레임, `SEAM_JUMP` 0 · 검증 FAILED 0. Job `timing` 에 신호 · 구간 · op · warp · 전후 길이.
2. 다리 — `fix.ops`(stance_width + foot_lock, smooth 단독 1건): Vesper 두 발 디딘 발 좌우 비 ≤ 3.2(상한 3.0 + 0.2), 대상 모델 예측 접지 미끄러짐 0 · Vesper 실측 ≤ 전, 상체 · 골반 불변(≤ 0.1 cm), IK 늘어남 0, 검증 FAILED 0. Job `fix.source` · `fix.target`.
3. 기준 재현 — fix 없는 재실행 = 기존 애셋(≤ 0.1 cm).
4. 합본 — 한 Job(BVH → fix.ops → 리타깃 → timing → 검증 → capture) SUCCEEDED, 한계 `FIX_ON_SOURCE_SKELETON` · `TIMING_CHANGED_LENGTH`.
5. 전후 캡처 — 시험 대상마다 전 · 후 시트(같은 동작 위상 행) · 비교 시트 · APNG 둘 → SendUserFile.
6. 비파괴 · 회귀 — 시험 대상 · 스켈레톤 · 메시 SHA-256 불변 · 새 더티 0 · Content 변경 = 실행 폴더뿐, pytest · Phase 1 ~ 7 · 8-1 · 8-2 통합 실패 0, Development · DebugGame 경고 0.
7. 사람 판정 — 수치 · 캡처는 근거, 판정은 사람(§16-9).

**결과 (2026-10-27 — `anim_gen_phase8_3_test.py` 전 섹션 PASS · 실패 0, 실행 `P83Run1027_153224` · 225초):**

| # | 기준 | 결과 |
| :---: | :--- | :--- |
| 1 | 흐느적 | ✅ 계획(애셋 0 · 더티 0): 검 선택 → 사슬 `resolve_source → timing → validate` · rate 2.0 · op 7개 · 미리보기 길이 1.1667초, 실행 op = 계획 op(4건). 정점 × 1.84 ~ 1.88(계획 ×2.0 · 1.95 의 92 ~ 95%), 정지 꼬리 2.4 · 2.43 → 0.3 · 0.27초(검), 정지 머리 0.9 → 0.2초(낫), 검증 `PASSED` 4건 · 이음매 경고 0. 손목 · 발목 궤적 상자 차 0.02 ~ 2.65 cm — 트림한 머리 · 꼬리의 느린 움직임이 빠져 정보로만(설계의 '≤ 1 cm' 는 트림이 없을 때) |
| 2 | 다리 | ✅ 대상 모델 풀이(s 1.047 · IK 늘어남 0 · 오차 0.0 cm). Vesper 두 발 디딘 발 좌우 비 5.24 / 5.25 / 4.17 / 4.14 → **3.04 / 3.02 / 3.07 / 3.04**, 접지 미끄러짐 p95 (7.33, 9.2) / (8.29, 5.76) / (10.28, 16.64) / (11.43, 16.52) → **0.0 / 0.0 (4건)**, 무릎 간격 최소 52.5 / 55.1 / 41.2 / 43.2 → 40.3 / 43.7 / 30.2 / 31.5 cm, 손목 · 머리 · 골반 궤적 차 0.0 cm. 모델 예측 = Vesper(디딘 최대 ±0.01). smooth 단독: 관절 이동 p95 1.56 · 최대 5.93 cm · `PASSED`. 검증 `PASSED` · `PASSED_WITH_WARNINGS`(전과 같은 관통 경고) |
| 3 | 기준 재현 | ✅ 4건 모두 0.0 cm(손목 · 발목 · 넓적다리 · 무릎 · 골반 · 머리) — 저장된 Kimodo BVH + SOMA 기본값 자동 |
| 4 | 합본 | ✅ 4건 SUCCEEDED(10 ~ 17초 — Blender 포함), Job `fix` · `timing` · `review.capture`, 한계 `FIX_ON_SOURCE_SKELETON` · `TIMING_CHANGED_LENGTH` · `REVIEW_CAPTURE_PREVIEW_ONLY` |
| 5 | 전후 캡처 | ✅ 4건 — 전(기존 애셋 6행) · 후(합본 — 행 = warp(전 행 시각)) · 비교 시트(후 \| 전) · APNG 전 61 · 후 19 ~ 37장, 잘린 칸 0 · 더티 0. 채팅 표시는 보고에서 |
| 6 | 비파괴 · 회귀 | ✅ 시험 대상 4 · 스켈레톤 · 메시 SHA-256 불변 · 미저장 0 → 0 · Content 변경 = 실행 폴더뿐. pytest **537건**(479 + 58, 기대된 변화 3). Development · DebugGame 빌드 경고 0. 통합 회귀 `anim_gen_phase1_test.py` 113 · `phase2` 62 · `phase3` 35 · `phase4` 27 · `phase5` 57(실제 Kimodo — 각속도 p99 비 0.954 · 루트 691.83 cm · Yaw 189.81°, 개정 8 과 같다 · 기대된 변화 1: 'fix op 사전이 비어 있음' 검사 → 사전 밖 op 로 막기) · `phase6` 20 · `phase7` 85 · `phase8_1` 100(`--only hashes,plan,exp1,…` — plan 을 exp1 앞에, 8-2 기록의 순서 문제 회피) · `phase8_2` 52 확인 실패 0. 첫 Kimodo 회귀는 에디터 재기동 때 이전 에디터가 미저장 패키지로 `quit_editor` 를 거절한 채 남아 토큰 파일이 엇갈려 `UNAUTHORIZED` — 에디터 하나로 다시 돌려 PASS(코드 무관) |
| 7 | 사람 판정 | ✅ 사용자 판정 통과(2026-10-27 — 후속 수정 뒤 전후 캡처 `P83Run1027_190338` 기준, '8-3 후속' 절) |

시험 대상별 (전 → 후, Vesper):

| 대상 | 길이 초 | 휘두름 정점 cm/s | 정지 머리 / 꼬리 초 | 두 발 디딘 발 좌우 비 · p50 | 접지 미끄러짐 p95 L / R cm/s | 무릎 간격 최소 cm |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 칼 시험 `KimodoSword1025_185815` | 4.0 → 1.23 | 425 → 794 | 0 / 2.4 → 0 / 0.3 | 5.24 · 5.12 → 3.04 · 2.89 | 7.3 / 9.2 → 0 / 0 | 52.5 → 40.3 |
| 검 선택 `P81Run1026_180733` | 4.0 → 1.17 | 322 → 604 | 0.07 / 2.43 → 0.03 / 0.27 | 5.25 · 5.08 → 3.02 · 2.81 | 8.3 / 5.8 → 0 / 0 | 55.1 → 43.7 |
| 낫 정정 선택 `P81Run1026_192547` | 4.0 → 2.40 | 527 → 972 | 0.9 / 0.03 → 0.2 / 0.03 | 4.17 · 3.72 → 3.07 · 2.48 | 10.3 / 16.6 → 0 / 0 | 41.2 → 30.2 |
| 낫 띠 정정 선택 `P81Run1026_205832` | 4.0 → 2.37 | 637 → 1,177 | 0.9 / 0.03 → 0.2 / 0.03 | 4.14 · 3.66 → 3.04 · 2.48 | 11.4 / 16.5 → 0 / 0 | 43.2 → 31.5 |

(운영 Vesper 낫 공격: 길이 1.25 ~ 2.4초 · 정점 1,098 ~ 1,821 · 끝 자세 2.1 · 접지 미끄러짐 p95 6 ~ 22 cm/s — E0.)

**전후 캡처:** `Tools/mcp/results/capture/P83Run1027_154153/<대상>/{before, after}/{sheet.png, animation.png}` · `after/compare.png`(행마다 after 정면 · 측면 | before 정면 · 측면, 같은 동작 위상 — `--only hashes,capture,dirty` 로 라벨을 붙여 다시 찍었다, 애셋은 `P83Run1027_153224` 합본). 잘린 정지 꼬리 · 머리의 전 행은 후의 끝 · 처음 프레임으로 모인다.

**읽는 법 · 한계:**
- 검은 4초 중 2.4초가 정지 꼬리라 길이가 1.2초로, 낫은 정지 머리 0.7초 · 복귀 ×1.5 로 2.4초로 줄었다. 검의 정점은 상한 ×2.0 에 걸려 운영 최저(1,098)에 못 미친다(604 · 794) — 더 빠르게는 `max_rate` 를 올린다(사람 판정 뒤).
- 다리는 두 발을 디딘 구간이 상한 3.0 안이고 Vesper 발이 미끄러지지 않는다. 그 대신 소스 발은 움직인다(대상 기준으로 고정했다) — 다른 대상 메시로 같은 애니를 리타깃하면 그 메시 치수로 다시 보정해야 한다(계획이 대상 치수를 싣는다).
- 낫은 디딘 구간 안에 두 발이 가까운 프레임이 있어 최소 간격(1.2 × 엉덩 폭) 때문에 3.07 에서 멈췄다.
- 모델은 바닥 제약 · 골반 오프셋 설정이 기본값인 리타기터를 가정한다(`match_existing` — 지금 anim_gen 의 RTG). 다른 RTG 구성이면 모델 예측 ≠ 실측일 수 있다 — `fix.target` 실측으로 드러난다.
- 무기 · 손 · 몸 관통은 그대로(8-4). **수치 통과는 품질 합격이 아니다** — 전후 캡처를 사람이 본다.

#### 8-3 후속 — 가속 구간 끊김 · 무릎 굽힘 (개정 13 보강 — 2026-10-27 밤)

**진행:** 8-3 보고 뒤 품질 탐침(원본 · 다리만 · 시간만 · 합본)에서 8-3 이 새로 만든 문제 2건(가속 구간 떨림 0.5 ~ 3.4 → 7.4 ~ 12.5 cm/프레임² · 무릎 굽힘 p50 37 ~ 42° → 48 ~ 60°) → 사용자 지시로 새 세션 → **설계 전 실측**(제품 코드 무변경 — 공유 노트 `phase8-3-followup-design.md` §0): 떨림 최댓값은 속도 경계가 아니라 원본의 빠른 꺾임(발볼 디딤 · 손가락 끝 · 아래팔)을 2배로 접은 것이고, 매끈한 사상 · 3차 보간만으로는 줄지 않으며(위치 공간 흉내), 앤티에일리어싱이 줄인다 → 사용자 결정(A 떨림 기준 = 균일 r 배 기대값 × 0.8 · B 앤티에일리어싱 · C 무릎 = 두 다리 중 작은 필요량) → 구현 → 실측에서 C++ 앤티에일리어싱이 흉내보다 약해 c 0.7 은 기준 A 를 3건 넘김 → **c 1.0**(기준 A 를 지키는 쪽, 정점 손실은 설계 때 보인 범위 안 — 사용자 확정 2026-10-27). 전후 캡처 사용자 판정 통과(2026-10-27).

**구성:**

| 파일 | 내용 |
| :--- | :--- |
| `Plugins/AnimGraphMcp/…/Core/AnimMcpAnimEditOps.{h,cpp}` · `AnimMcpAnimEdit.cpp` · `Tests/AnimMcpEditTests.cpp` · `README.md` | 새 op `time_warp{knots, rates?, antialias?}` — `FWarpCurve`(Hermite · PCHIP · 정방향 이분 탐색) · `EvaluateFiltered`(선형 보간 트랙 ∗ 가우시안을 닫힌 식으로 — 키 가중치 = E[hat(T − j)], `erfc`) · `Resample` 키별 σ(기존 `retime` 은 σ 0 — 결과 그대로) · Automation `AnimGraphMcp.Generation.Edit` time_warp 블록(항등 · 2배 = retime · 램프 속도 변화 ≤ 0.25 · antialias 지그재그 · 거부 8종 · 이음매) |
| `Tools/mcp/anim_gen/timing.py` | VERSION 2 — 배율 곡선 매듭(`rate_marks`) · 매듭 사이 출력 길이 = 원 길이 / 두 끝 배율 평균(Hermite 끝 기울기 = 매듭 배율 → 출력 시각에 선형인 램프) · 새 길이 정수 프레임 올림(배율이 상한을 넘지 않게) · op = trim 하나 + time_warp 하나 · `WarpCurve` · `warp_time`(Hermite) · `simulate`(time_warp) · `max_rate_step` · `fix.timing.antialias` 1.0, `swing.ramp_pieces` 삭제 |
| `fix_ops.py` · `foot_fix.py` · `blender/fix_legs.py` · `providers/blender.py` | `stance_width.keep_knee_bend` · `pelvis_raise`(프레임별 필요 상승 → 두 다리 중 작은 쪽 → σ 2 → 다시 상한) · `raised` · solve(골반 올린 프레임도 IK) · `raise_pelvis`(골반 위치 키 — 루트면 기준 회전의 역, 부모가 있으면 부모 포즈 · 기준 상대 회전의 역, 부모에 붙은 본은 `PELVIS_CONNECTED`) · IK 는 올린 엉덩 · 무릎 · 발목(방향 그대로)에서 · 진단에 골반 상승 |
| `motion_metrics.py` | `knee_bend` · `legs_report.knee_bend`(Job `fix.target` 에도) · `zigzag_at_rate`(균일 r 배 기대값 — 위상 0 · r/2 중 큰 쪽) |
| `tests/test_timing.py` · `test_fix_legs.py` · `conftest.py` | pytest 546(537 + 9, 기대된 변화: retime 조각 · ramp_pieces → 배율 곡선 · time_warp, stance_width 기본값에 keep_knee_bend) |
| `Tools/mcp/anim_gen_phase8_3_test.py` | automation 에 Edit · timing(op = trim + time_warp · 정점 ≥ ×0.75 · 속도 단차 ≤ 램프 + 0.05) · legs(골반 기준 상체 · 골반 수평 · 골반 상승 = 계획 ± 0.5 · 무릎 p50 ≤ +5°) · 새 `quality` 섹션(4 대상 × 원본 · 다리 · 시간 · 합본) |

**설계 정정 (실측):**
1. 떨림의 원인 = 계단 경계가 아니라 원본의 빠른 꺾임의 에일리어싱(위 진행). 기준 = 균일 r 배 기대값 × 0.8(원본 × r² 는 13.7 / 2.2 / 5.8 / 5.8 — 지킬 수 없다).
2. 앤티에일리어싱 강도 — C++ 실측(같은 op, c 만 바꿔): 떨림 c 0 → 0.7 → **1.0** → 1.5 = 칼 8.8 → 5.2 → **3.8** → 2.3 · 검 선택 7.4 → 6.3 → **2.3** → 1.6 · 낫 정정 24.3 → 21.0 → **3.4** → 1.8 · 낫 띠 12.8 → 10.3 → **2.6** → 1.9, 정점 ×1.85 ~ 1.92 → ×1.77 ~ 1.84 → **×1.67 ~ 1.78** → ×1.44 ~ 1.64. 로컬 회전을 거르는 실제 결과는 위치 공간 흉내(c 0.7 이 충분)보다 약하다 → 1.0.
3. 무릎 — 시간 보정이 머리 · 꼬리를 잘라 무릎 굽힘 p50 의 모집단이 바뀐다 → 합본의 무릎은 '같은 시간 보정의 원본(시간만)'과 비교(시간 보정은 자세를 바꾸지 않는다).

**결과 (2026-10-27 — `anim_gen_phase8_3_test.py` 전 섹션, 실행 `P83Run1027_190338` · 253초 · 실패 1):**

| 대상 | 정점 cm/s (×비) | 떨림 시간만 · 합본 (첫 판) | 균일 기대값 × 0.8 | 다리 떨림 (원본) | 무릎 p50 L/R 다리 (원본 · 첫 판) | 골반 상승 p50 · 최대 cm |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 칼 시험 | 425 → 720 (×1.69) | 3.81 · 3.87 (10.78 · 12.5) | 12.09 | 3.33 (3.42) | 38.4 / 37.8 (38.2 / 36.8 · 57.8 / 57.6) | 6.67 · 11.6 |
| 검 선택 | 322 → 571 (×1.77) | 2.25 · 2.38 (7.43 · 9.21) | 6.47 | **1.89 (0.56) ✗** | 42.7 / 38.5 (42.4 / 36.3 · 59.0 / 57.6) | 6.33 · 10.95 |
| 낫 정정 | 527 → 884 (×1.68) | 3.43 · 3.45 (11.78 · 11.78) | 20.74 | 1.97 (1.44) | 40.1 / 40.7 (37.1 / 40.7 · 47.7 / 49.1) | 2.45 · 3.70 |
| 낫 띠 | 637 → 1,084 (×1.70) | 2.61 · 3.32 (11.08 · 11.08) | 9.56 · 9.64 | 1.59 (1.53) | 40.9 / 41.2 (38.3 / 41.2 · 48.1 / 49.3) | 2.35 · 3.51 |

- 그대로 지킨 것: 길이 1.2 / 1.2 / 2.33 / 2.33초 · 정지 꼬리 ≤ 0.3초 · 이음매 경고 0 · 검증 FAILED 0 · 속도 단차 ≤ 램프 기울기(0.25 / 0.29 / 0.20 / 0.20 — 첫 판은 조각 경계에서 0.5 이상) · Vesper 두 발 디딘 발 좌우 비 3.04 / 3.02 / 3.07 / 3.04 · 접지 미끄러짐 0 · IK 늘어남 0 · 상체의 골반 기준 위치 0.01 cm · 골반 수평 0.0 cm · 골반 상승 = 계획(±0.01) · 합본 무릎 ≤ 시간만 + 2.8° · 관통 · 손목 굽힘 · 손-머리 · 꼬임 원본 대비 나빠짐 0(12 변형) · 기준 재현 0.0 cm · 시험 대상 · 스켈레톤 · 메시 SHA-256 불변 · 미저장 0 · Content 변경 = 실행 폴더뿐 · 두 구성 빌드 경고 0 · C++ Automation Capture · Edit 통과.
- **기준 미달 1건 — 검 선택 다리만 떨림 1.89 > 원본 + 1.0(1.56).** 오른 무릎 0.5 ~ 0.57초, 원본이 다리를 11° 까지 펴는 자리. 다리 보정의 간격 전환 · 발 고정 블렌드가 공중 발 경로에 만드는 엉덩 → 발목 거리 꺾임(+1.2 → −2.7 cm/프레임² — 첫 판에도 같은 자리, 떨림 1.32)이, 원래 굽힘을 되찾아 거의 펴진 다리에서 무릎을 더 흔든다. 시도(블렌드 5 · 7 프레임, 공중 보정량 스무딩 2가지, C2 블렌드, 최소 굽힘 25° 상한)는 모두 줄이지 못했다(2.05 · 9.5 · 1.63 · 2.33 · 3.94 · 2.01) — 공중 발 경로를 디딤 사이 곡선으로 다시 짜는 것을 **8-4 범위로 넘겼다**(사용자 결정 2026-10-27 — 대상 쪽 풀이가 발 접지를 제약으로 함께 지킨다). 1.89 는 운영 공격 떨림 범위(0.6 ~ 5.6) 안.
- 회귀: pytest 546 · 통합 `phase1` · `phase2`(retime 결과 그대로 — `Resample` σ 0) · `phase3` · `phase4` · `phase5`(실제 Kimodo) · `phase6` · `phase7` · `phase8_1`(`--only hashes,plan,exp1,…`) · `phase8_2` 실패 0. 회귀 뒤 에디터를 다시 띄울 때 테스트 경로 미저장 55개를 버리고 종료했는데 프로세스가 종료 중 응답 없음으로 남아(13.8 GB) 강제 종료했다(코드 무관 — 다시 띄운 에디터 인증 확인 후 Phase 5 · 8-1).

**읽는 법 · 한계:**
- 원본 숙임이 평평해졌다 — 검 2건은 원본이 넓은 다리로 골반을 8 cm 숙이는 구간에서 골반 상승이 최대 11 cm 라, 좁힌 다리로 원래 굽힘을 지키면 골반 높이가 거의 일정해진다(기하로는 맞다 — 눈 판정 대상).
- 앤티에일리어싱은 빠른 손가락 · 손목 꺾임을 흐리게 한다 — 정점 −8 ~ −10%(c 0 대비). 더 빠르게는 `max_rate` 를 올린다.
- 전후 캡처: `Tools/mcp/results/capture/P83Run1027_190338/<대상>/{before, after}/` — 비교 시트(후 | 전) · APNG 둘. **사용자 판정 통과(2026-10-27).**

#### 8-4a 기반 — 측정 한 원천 · 입출력 · 무기 부착 캡처 · E0 (개정 14 — 2026-10-27 ~ 28 구현 · 검증)

**진행:** 8-4 총괄 설계(공유 노트 `phase8-4-design.md` — 결정 A ~ G 추천안 확정: A 수단 = Python 한 풀이 + C++ 얇은 입출력(UE Control Rig 베이크 · Blender IK on Vesper FBX 기각, C++ PBIK 는 차선) · B 4단위 a → b → c → d 하나씩 · C 낫 손잡이 = 요청의 무기 공간 선분(E0 제안 — 운영 애셋 무변경) · D 몸통 자유도 기본 끔 · E 새 측정 옵트인(기본 결과 · 검증 상태 · 선별 점수 불변) · F 지시 목표 soft · G 샘플 전이 같은 스켈레톤만) → 8-4a 상세 시그니처 · 정정안 11건(사용자 승인 — `phase8-4a-design.md`) → 옛 빌드로 비교 대상 16개 기본 `body_clearance` 를 state 에 찍음(`baseline`) · DA 값(시작 스크립트) → C++ 5개 · Automation · Python · 통합 1차 → (컴퓨터 강제 종료 뒤 마무리 세션) 머리 꼭대기 정정 · E0 낫 축 · 왼손 파지 판정 정정 → 통합 · 회귀. **C++ 는 8-4 전체에서 이 단위에만 있다**(8-4b ~ d 는 이 op · 측정으로 Python 만).

**C++ (전부 옵트인 — 주지 않으면 개정 13 결과 그대로):** ① `validate_animation body_clearance` v2 `parts: "all"` · `legs` · `per_frame` · `model`(§13) ② `profile_rotations`(§13) ③ 편집 op `bone_deltas{space: parent}`(§14 Phase 2 op 표) ④ `capture_animation attachments[{mesh (SkeletalMesh | StaticMesh), socket | bone, offset{location, rotation[pitch, yaw, roll], scale}}]` ≤ 4 — 부착 = `AttachToComponent(KeepRelative)` + 상대 offset, 렌더 · ShowOnly · 범위(정점 상자)에 포함, 결과 `attachments[{mesh, class, socket | bone, offset, local_bounds_cm}]`, 오류 `BAD_REQUEST`(`SOCKET_NOT_FOUND` · `BONE_NOT_FOUND` · `CONFLICTING_FIELDS` · `NOT_A_MESH`) ⑤ `inspect_skeleton geometry`(§8). 플러그인은 프로젝트 이름을 모른다 — 부위 · 좌우 · 중앙선은 이름 없이 기하로.

**구성:**

| 파일 | 내용 |
| :--- | :--- |
| `Plugins/AnimGraphMcp/…/Core/AnimMcpBodyClearance.{h,cpp}` | 부위 그룹(위팔 · 머리 · 종아리 — 지금 None 인 본에만, 기존 점 · 지도 불변) · 몸통 칸 t 경계 · 정수리(축선 5 cm 안 최대 투영) · 머리 · 종아리 지도 · 쌍 통계 · 다리끼리 · 프레임별 깊이 · 모델 내보내기(base64) |
| `…/Core/AnimMcpAnimValidator.{h,cpp}` · `Tools/AnimMcpTools_Validate.cpp` | `profile_rotations` · body_clearance 새 키 파싱(`retarget_animations` 에는 `per_frame` · `model` 없음) |
| `…/Core/AnimMcpAnimEdit.cpp` · `AnimMcpAnimEditOps.{h,cpp}` | op `bone_deltas`(키 수 검사 · 부모 공간 회전 벡터 · 0 키 그대로 · Animated 트랙만) |
| `…/Core/AnimMcpCapture.{h,cpp}` · `Tools/AnimMcpTools_Capture.cpp` | `attachments`(offset 해석 · 소켓/본 · 범위 포함 · 포즈마다 렌더 상태) |
| `…/Core/AnimMcpSkeletonGeometry.{h,cpp}` · `AnimMcpSkeletonInspector.{h,cpp}` · `Tools/AnimMcpTools_Skeleton.cpp` | 주축(3×3 야코비) · 단면 · 본별 범위 — `geometry` |
| `…/Tests/AnimMcp{BodyClearance,Edit,Capture,Geometry}Tests.cpp` · `README.md` · `Tools/mcp/anim_graph_mcp/server.py` | Automation(반경 지도 · 몸통 칸 · 어깨 제외 · base64 왕복 / bone_deltas 항등 · 한 본 · 거부 / offset 해석 / 야코비) · 문서 · 프록시 인자 |
| `Tools/mcp/anim_gen/body_model.py` · `tests/{test_body_model.py, model_fixture.py}` · `conftest.py` | 순수 Python 몸 모델(디코드 · 쿼터니언 · FK · LBS · 지도 조회 · 델타 · 통계 · 대조) · pytest 14 · FakeEditor(profile_rotations · body_clearance parts/per_frame/model · bone_deltas 키 수) — pytest 560(546 + 14, 기존 기대값 변경 0) |
| `Tools/mcp/anim_gen_phase8_4_test.py` · `Tools/mcp/e0_weapon_attach.py` | 통합 `hashes · baseline · automation · model · e0 · dirty`(state `Tools/mcp/anim_gen_phase8_4_state.json`) · DA 값 시작 스크립트(결과 `Tools/mcp/results/p84_weapon_attach.json`) |

**설계 정정 (실측 — 상세 감사 §21):**
1. 무기 부착 = 변환 2단(`AttachOffset` · `AttachTransform` · 소켓 · 손) — 캡처 `offset` 은 합성 한 변환, 8-4c 요청 `weapon.attach` 는 두 값을 받아 anim_gen 이 합성한다.
2. `bone_deltas.space` 이름 = `parent`(`offset_bone` 의 `local` 과 반대 뜻), 몸 모델이 자기 포즈(모든 프레임)를 함께 낸다(profile 은 표본 ≤ 240 · 0번 프레임 없음), 모델은 측정 점 전부(줄이면 재현 ≠ 측정 — base64 로 크기를 잡았다).
3. 머리 꼭대기 — 최대 투영은 Vesper 뿔 끝이었다 → 정수리 규칙 + 머리 지도 t ≤ 1.0(뿔 줄기가 t 1.0 ~ 1.05 칸을 15.6 cm 로 채워 정수리 위 손을 13.2 cm 로 셌다).
4. 낫 손잡이 축 — 첫 주축은 길이가 둘째(날 142.7 cm)의 2배가 안 된다, 자루는 저폴리 원기둥이라 가운데 단면에 정점이 없다 → 자루 선 = 좁은 단면 중심 직선. 낫 메시 `Root` 기준 포즈가 (−27.73, 0, −131.13) 이동이라 Trace 소켓 선은 자루에서 27.3 cm 떨어진 판정용 선이다(손잡이 선분이 아니다).
5. 왼손 파지 판정 — 손바닥 점(뼈 선 위)은 쥔 오른손도 자루에서 12.4 cm → '오른 손바닥 거리 + 3 cm · 자루 범위 안'.

**결과 (2026-10-28 — `anim_gen_phase8_4_test.py --only hashes,automation,model,e0,dirty`, 실행 `P84Run1028_000654` · 85초 · 실패 0, baseline 은 옛 빌드 `P84Run1027_225342`):**

| 완료 기준 | 결과 |
| :--- | :--- |
| 1 기본 결과 불변 | 비교 대상 16/16 — 키 없는 `body_clearance` = 옛 빌드(`arms[]` · `body` · 상태 · 경고), `parts` 를 켜도 `arms[]` · `body` 그대로(5건) |
| 2 부위 쌍 | 36 쌍 · 모든 몸 부위가 잡힘(낫 정정 선택 걸림 % pelvis 6.6 · belly 10.7 · chest 100 · thigh 14.9 / 47.1 · head_neck 52.1). 소견 자리 1.53초 손 → head_neck 11.86 cm · 2.43초 왼 아래팔 → belly 6.53 cm. `head_near` 와 같은 방향 — 상관 0.952, 최근접 1.6초(3.0 cm) · 최심 1.533초 둘 다 소견 창 안. 몸통 칸 경계 belly 0.181 · chest 0.327(spine_01 · spine_02), 위팔 어깨 제외 9.75 cm, 정수리 `crown`(반경 5.26 cm) |
| 3 Python 재현 | 5건(낫 정정 · 검 선택 · 낫 띠 · 운영 낫 Attack2 · 검 다리 보정본(다리 포함)) 쌍별 깊이 차 p95 0.0047 ~ 0.0048 · 최대 ≤ 0.0055 cm · 걸림 불일치 0 · 관통 % 같음 |
| 4 bone_deltas · profile_rotations | 0 델타 = 원본(회전 0° · 위치 0 cm) · `trim{}` 항등과 내용 해시 같음 · `upperarm_l` 15° = 자손만(아래팔 6.4 · 손 11.2 cm, 나머지 ≤ 0.01) · 거부 `BAD_OP`(키 수) · `BONE_NOT_FOUND` · `OUT_OF_RANGE` · 원자성 `BAD_REQUEST`(애셋 0) · 미리보기 통과. profile_rotations = 위치 시각(자식의 부모 기준 위치 퍼짐 0.023 cm, 한 표본 밀면 19.7 cm) |
| 5 무기 부착 캡처 | 낫을 `WeaponHandR` 에 붙인 '전' 시트 · APNG 3건(낫 정정 · 낫 띠 · 운영 Attack1) — 잘린 칸 0 · 더티 0 · `Tools/mcp/results/capture/P84Run1028_000654/<이름>/before/{sheet.png, animation.png}` |
| 6 E0 | 아래 표 — 16개 '전' 수치 · 부착값 · 자루 선 · 왼손 파지 선분 제안 · 모델 크기 · 풀이 시간 예측 · 사건. 시험 대상 · 운영 낫 · 스켈레톤 · 메시 · 무기 메시 · DA 24개 SHA-256 불변 · 미저장 0 · Content 변경 = 실행 폴더뿐 |
| 7 회귀 | 두 구성 빌드 경고 0(툴체인 안내만) · Automation `AnimGraphMcp.*` 35/35 · pytest 560 · 통합 phase1 · phase2 · phase8_2 실패 0 · phase8_3 `quality` 39/40 — 남은 1건은 8-3 때부터의 알려진 기준 미달(검 선택 다리 떨림 1.891 > 1.56, 값 그대로 — 8-4 범위 ③ = 8-4d 기준 1), 나머지 떨림 · 무릎 · 관통 · 손목 · 손-머리 · 꼬임 값은 8-3 결과 표와 같다 |

**E0 — 비교 대상 '전' 수치(parts all, 관통 = 깊이 > 2.1 cm, 접촉 1.05 cm):**

| 대상 | 단위 | 관통 쌍 상위(쌍 프레임 % · 최대 cm) | 손 → 머리 · 목 % · 최대 | head_near % | 위팔 → 몸통 접촉 % | 파지 % | 떨림 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| scythe_pick (낫 정정) | b · c | 왼 위팔 → 가슴 8.3 · 4.79 / 왼 손 → 머리 7.4 · 11.86 / 왼 아래팔 → 배 3.3 · 6.53 | 7.4 · 11.86 | 4.2 | 13.2 | 72.5 | 1.44 |
| scythe_s25 | b | 오른 아래팔 → 가슴 50.4 · 12.74 / 오른 손 → 가슴 47.9 · 14.7 | 0.8 · 3.92 | 0 | 26.4 | 14.2 | 2.65 |
| scythe_s26 | b | 오른 손 → 가슴 70.2 · 6.32 / 오른 아래팔 → 가슴 70.2 · 5.87 | 2.5 · 3.16 | 2.5 | 21.5 | 25.8 | 0.27 |
| scythe_s27 | b | 오른 위팔 → 가슴 64.5 · 5.7 / 오른 손 → 머리 57 · 11.08 | 57 · 11.08 | 55.8 | 76 | 27.5 | 2.36 |
| sword_pick (검 선택) | b | 왼 위팔 → 가슴 90.9 · 11.48 / 왼 아래팔 → 가슴 77.7 · 6.69 / 오른 손 → 머리 5 · 10.18 | 5 · 10.18 | 0 | 90.9 | 100 | 0.56 |
| scythe_regrip (낫 띠) | c · b | 왼 위팔 → 가슴 5 · 4.17 / 오른 위팔 → 가슴 1.7 · 2.4 | 0 · 1.82 | 0 | 10.7 | 100 | 1.53 |
| scythe_axis_bug | b 스트레스 | 오른 위팔 → 가슴 100 · 8.42 / 왼 위팔 → 가슴 89.3 · 13.44 / 왼 아래팔 → 가슴 75.2 · 13.16 | 43.8 · 9.11 | 41.7 | 100 | 97.5 | 1.48 |
| 운영 Walk | b 기존 | 오른 위팔 → 가슴 76 · 3.28 / 왼 위팔 → 가슴 46.3 · 4.32 / 오른 손 → 오른 넓적다리 22.3 · 7.93 | 0 | 0 | 92.6 | 0 | 2.27 |
| 운영 Run | b 기존 | 왼 손 → 배 15.8 · 4.26 / 오른 위팔 → 가슴 13.2 · 2.94 / 왼 손 → 골반 11.8 · 10.84 | 0 | 0 | 42.1 | 0 | 8.02 |
| 운영 Rifle Idle | b 기존 | 왼 위팔 → 가슴 98.1 · 4.64 / 왼 아래팔 → 가슴 34.5 · 3.25 | 0 | 0 | 100 | 0 | 0.29 |
| 운영 낫 Attack2 | b 기존 | 왼 위팔 → 가슴 42.7 · 7.24 / 오른 위팔 → 가슴 37.5 · 6.81 / 왼 손 → 왼 넓적다리 27.1 · 6.43 | 0 | 0 | 65.6 | 28.4 | 8.16 |
| legs_sword · legs_scythe_pick · legs_scythe_regrip | d | 각 원본과 같은 쌍(상체 불변) — 다리끼리 쌍 0 | 5 · 10.18 / 7.4 · 11.86 / 0 · 1.82 | 0 / 4.2 / 0 | 90.9 / 13.2 / 10.7 | 100 / 72.5 / 100 | 1.89 / 1.97 / 1.59 |
| legs_kimodo_sword · kimodo_sword_1025 | d · b 대조 | 오른 위팔 → 머리 2.5 · 4.0 | 0 | 0 | 0.8 | 0 | 3.33 / 3.42 |

**E0 — 낫(무기 공간 = `SKM_Hero_Sickle` 메시 컴포넌트 공간 cm):**
- 부착값: `DA_WD_Sickle1.MeshInfo.AttachOffset` 이동 (−8.582, 3.961, 56.356) · 회전 0 · `DA_EF_Sickle.ActorsToSpawn[0].AttachTransform` 항등 · `AttachSocket = WeaponHandR`(`hand_r` 상대 (−3.509, 3.388, −1.033) · pitch −0.817 · yaw 4.743 · roll −12.853) · `LeftHandGripSocket = None`(런타임 왼손 IK 없음) → 캡처 offset = 이동 (−8.582, 3.961, 56.356) · 회전 0 · 스케일 1.
- 기하: 정점 범위 x −98.2 ~ 42.8 · y ±5.0 · z −131.1 ~ 88.5, 무게중심 (−5.79, 0, 23.41), 첫 주축 (−0.047, 0, 0.999) 219.5 cm · 둘째 (0.999, 0, 0.047) 142.7 cm(날) · 셋째 9.9 cm. **자루 선** = 점 (−0.98, 0, −49.27) · 방향 (−0.006, 0, 1.000), 좁은 단면 9칸(끝 고리 u −155 ~ −118 · 목 −45 ~ 1 — 가운데 −118 ~ −45 는 정점 0), 자루 범위 선 위 −81.9 ~ 73.7 cm. 자루 ∥ 첫 주축 2.31° · ∥ TraceStart → End 0.35°(Trace 선은 자루에서 27.3 cm — 판정용).
- **왼손 파지 선분 제안**(운영 낫 4개 — 왼 손바닥 자루 선 거리 ≤ 오른 손바닥(12.4 cm) + 3 cm · 자루 범위 안, Attack1 5.3 · Attack2 31.6 · Attack3 5.4 · Finisher1 16.7%, 51 표본): 자루 선 위 좌표 p5 ~ p95 = −21.0 ~ 12.5 cm → **선분 (−0.85, 0, −70.32) → (−1.05, 0, −36.74)**(자루 중심선 위), 손바닥 점 기준 평균 반경 오프셋 (10.78, −1.79, 0.07)(10.9 cm)을 더하면 (9.93, −1.78, −70.26) → (9.72, −1.78, −36.67). 손바닥 점이 뼈 선 위라 8-4c 파지 잔차의 기준점(손바닥 점 vs 손바닥 면)에 따라 둘 중 하나를 쓴다 — 요청 `weapon.grips[].segment` 로 준다(운영 애셋 무변경).
- 사건(`timing` 신호 · `detect_contacts`): scythe_pick 정점 1.933 · 휘두름 [1.433, 2.633] · 두 발 [[0.033, 1.833], [2.433, 4]] / sword_pick 0.867 · [0.033, 1.533] · [[0.033, 0.233], [0.933, 4]] / scythe_regrip 1.933 · [1.4, 2.667] · [[0.033, 1.867], [2.433, 4]] / 운영 Attack1 0.333 · [0.1, 0.583] · [[0.417, 0.65]] · Attack2 0.583 · [0, 0.883] · 없음 · Attack3 0.567 · [0.233, 0.783] · 없음 · Finisher1 0.7 · [0, 1.067] · [[0.967, 1.133], [1.967, 2.167]] — 표준 지시 T1 ~ T5 · 샘플 S1 ~ S3 이 쓰는 사건은 전부 잡힌다(운영 Attack2 · 3 은 두 발 디딘 구간 없음).
- 모델 크기 · 시간: model JSON 1.8 ~ 3.0 MB(73 ~ 81 본 · 1,171 ~ 2,139 점) · C++ 모델 0.9 ~ 1.1초 · Python 평가 5.5 ~ 9.9 ms/프레임 → 감쇠 GN 8 × 재검사 3 = 24 평가 예측 28.8초(121 프레임 · 다리 포함 최대).

**발견 — 위팔 → 가슴이 운영 애니에서도 높다:** Rifle Idle 왼 위팔 → 가슴 98.1% · 4.64 cm, Walk 오른 76% · 왼 46.3%, 운영 낫 Attack2 42.7 · 37.5%, 검 선택 90.9% · 11.48 cm(위팔 → 몸통 접촉 % 는 운영 42 ~ 100). 겨드랑이 · 옆구리 눌림과 몸통 지도 위쪽(어깨 · 가슴 옆) 정점의 근사일 가능성이 크다 — **8-4b 는 운영 수준 기준(운영 애니 분포) 또는 위팔 쌍 기본 제외를 설계에서 정한다**(8-4b 완료 기준 1 '모든 쌍 관통 ≤ 2%' 는 위팔 쌍에서 운영 애니도 못 지킨다).

**읽는 법 · 한계:**
- 반경 지도는 칸 안을 꽉 찬 몸으로 본다 — 뿔 뿌리가 정수리 아래 칸(t 0.96 ~ 1.0)에 반경 ≈ 12 cm 로 남아, 손이 정수리 근처 그 방향이면 깊이를 키울 수 있다(낫 정정 2.07 · 2.1초 5.6 · 7.1 cm — 정수리 바로 아래 칸, 최심 11.86 보다 작다). 머리카락 · 옷 물리는 없다.
- 손바닥 점(`hand_l` · `middle_01_l` 중점)은 뼈 선 위 — 파지 선분 제안은 이 점 기준이다.
- 낫 붙인 '전' 캡처는 판정 근거(§16-9) — 무기를 쥔 손 모양 · 왼손 파지는 8-4c.

#### 8-4b ① 몸 전체 관통 — 한 풀이 엔진 + 지시 목표 (개정 14 — 2026-10-28 구현 · 검증)

**진행:** 상세 설계(공유 노트 `phase8-4b-design.md` — 사용자 승인: Python 순수 풀이 + C++ 얇은 입출력 · 양손끼리 = C++ 소폭 · 지시 목표 기본 soft · 새 측정 옵트인 · 몸통 자유도는 목표 구간만 · 코트 자락 기록만 · 손목은 파지 방향을 맞출 때만) → 순수 풀이 · 파이프 · 요청 · 라우터 · Job · pytest(단위 세션) → 실제 모델 12개 오프라인 조율 · 실제 Job 프로브 → (컨텍스트 부족으로 마무리 세션) C++ 손끼리 · 두 구성 빌드 · 통합 · 회귀 · 문서. 총괄 정정(착수 전): 기준 1 의 위팔 쌍 = '전보다 나빠지지 않음'만(운영 애니도 42 ~ 100%), 손 · 아래팔 쌍 ≤ 2% · 최대 ≤ 2 cm × scale, 머리목 하드.

**풀이 (`anim_gen/body_fit.py` — 순수 Python, numpy 없음, 상수 · 독스트링에 실측 근거):**
- 자유도(프레임마다, 부모 공간 회전 벡터 = `bone_deltas` 와 같은 뜻): 팔마다 쇄골 swing 2(≤ 10°) · 위팔 swing 2(뼈 축에 수직 — 비틀림 0, ≤ 45°) · 팔꿈치 경첩 1(굽힘 평면 법선, 굽힘 2 ~ 155°, ≤ 60°) · **파지 프레임만 두 손목** 3(≤ 30°). 지시 목표 구간만: 척추 마디 · 목/머리(합 ≤ 20°) · 골반 이동 3 + 회전 3(→ 다리 닫힌 식 IK 로 원래 발목 · 발 전역 회전, 곧은 다리는 몸 앞으로 굽힘).
- 잔차(같은 감쇠 GN 안의 층 가중 — 하드 목표 1000 > 관통 30 · 다리 늘어남 > keep 10 > 소프트 목표 10 > 소프트 1): 관통 = 손 · 아래팔 점(LBS)의 max(0, 깊이 + margin) ↔ 몸통 칸 · 넓적다리 · 머리목 · 반대 팔 손 · 아래팔(손끼리는 맞닿음 contact 까지 허용 — **후속: 몸통 · 넓적다리도 `allow_contact` 기본으로 max(0, 깊이 − contact), 머리목은 margin 그대로** — 아래 '8-4b 후속'), 위팔 점 = 원래 깊이보다 안 깊어짐(후속 2차: 관통 층 30 → keep 층 10 · 재검사 위반에서 뺌 — 아래 '8-4b 후속'), keep = 보조 손바닥 점 · 회전의 주 손목 기준 상대 변환(11.5 cm/rad), 주 손 · 손목 위치 충실도(어깨 바탕 본 기준), 관절 변화 충실도 100 cm/rad · 시간 연속(앞 프레임 보정 쪽). 바깥 방향 = 지도 축에서 점 쪽(C++ Resolve 의 ω × r 와 같은 선형화), 야코비안 = 조상 관절마다 ω × (가중 점 − 관절).
- 지도는 기준 본(몸통 = t 칸별 펠비스 · 척추 마디, 넓적다리, 머리 = 목 · 머리, 손 = 손목, 아래팔 = 팔꿈치)에 붙어 강체로 따라간다 — 풀이 포즈의 점을 T원래 · T풀이⁻¹ 로 되돌려 원래 지도에 묻는다(기준 본이 안 움직이면 C++ 규칙 그대로).
- 한 프레임 = LM(μ 0.1 시작) ≤ 12 회 · 한 걸음 ≤ 8°(상한을 넘는 관절은 그 걸음만 상한까지), 목표가 있으면 x_T(목표 · keep · 충실도) → x(전부) 두 번. 시간 = 관통 몫 Δ = x − x_T 만 **가중 매끈화 스플라인**(보정 프레임 가중 30 · 그 밖 10(후속 — 처음 판 1) · λ = (1.5 R)⁴), 목표 몫은 완급(smoothstep)이라 그대로, 원본이 루프(`numeric.loop`)면 순환(후속). 재검사 = 하드 잔차가 남은 프레임만 두 팔 함께 → 증분을 같은 스플라인으로(그 밖 가중 1 — 후속, passes 3 + 3). 쓰기 = `bone_deltas{space: parent}`(바꿀 것이 없으면 항등 `trim{}` — 최종 이름 애셋은 만든다).

**C++ (8-4b — 옵트인, 기본 결과 불변):** `body_clearance.hands`(§13 손끼리 행) — 공개 `FArmAxes`(손 · 아래팔 지도) · `HandTip`, `MeasureParts` 가 프레임마다 두 팔 점을 먼저 스킨해 몸 지도 조회와 손끼리가 함께 쓴다(기본 값 그대로), `parts.hands` · `HAND_PENETRATION` · per_frame · 모델 지도 `hand_l/r` · `forearm_l/r` · `roles.arms[].hand_tip_local_cm`. Automation `AnimGraphMcp.Generation.BodyClearance` 에 손끼리(손 끝 · 두 원통 겹침 깊이 ≈ 1.0 · 떨어지면 ≈ −2.0 · 손 끝 밖).

**구성:**

| 파일 | 내용 |
| :--- | :--- |
| `Tools/mcp/anim_gen/body_fit.py` | 요청 정규화 · 몸 기준틀 · 사건 → 목표 · 파지 가중 · 감쇠 GN · 스플라인 · 재검사 · 다리 IK · 예측 측정 · `bone_deltas_op` |
| `Tools/mcp/anim_gen/providers/body_fit.py` | 파이프 `BodyFitPipe`(control_rig 자리) — 계획 미리보기(측정 · 사건 · 목표) · 실행(측정 + 모델 → 풀이 → 쓰기 → C++ 재측정 → Job `fix.body` · 한계) |
| `timing.py` · `request.py` · `router.py` · `executor.py` · `registry.py` · `providers.json` · `providers/builtin.py` · `providers/inactive.py` · `server.py` | `timing.events`(사건 한 원천) · `fix.body` · 단계 위치 · 재사용 판정 · 생산 단계 · 레지스트리 · 매니페스트(control_rig → body_fit) · 리타깃 관통 measure 전환 · `apply_edits` 모듈 함수 · 문구 · Tool 설명 |
| `Tools/mcp/anim_gen/body_model.py` · `tests/conftest.py`(8-4a 파일) | 손끼리 지도 조회(`has_hands` · `pair_depths` · `series`) · FakeEditor `hands` → `parts.hands.pairs` |
| `tests/{body_fit_fixture.py, test_body_fit.py, test_body_fit_pipe.py}` · `test_body_model.py` · `test_router.py` | 합성 몸 모델(양팔 · 척추 · 목 · 다리 · 손 지도) · 풀이 · 파이프 · 손끼리 조회 · Provider 이름(기대된 변화) — pytest 603(560 + 43) |
| `Plugins/AnimGraphMcp/…/Core/AnimMcpBodyClearance.{h,cpp}` · `Tests/AnimMcpBodyClearanceTests.cpp` · `Tools/AnimMcpTools_Validate.cpp` · `README.md` · `Tools/mcp/anim_graph_mcp/server.py`(8-4a 파일) | 손끼리(위) · Tool 설명(16 KB 리터럴 한도 — 두 리터럴로) · 문서 |
| `Tools/mcp/anim_gen_phase8_4_test.py` | 통합 `plan · clearance · targets · existing`(+ automation 의 손끼리) |

**결과 (2026-10-28 — `anim_gen_phase8_4_test.py`: `hashes,automation,plan,dirty` 실패 0 · `hashes,clearance,dirty` 실행 `P84Run1028_181805` · `hashes,targets,existing,dirty` 실행 `P84Run1028_183211`, Job 16/16 SUCCEEDED · 비파괴(24 파일 SHA-256 · 새 더티 0 · Content = 실행 폴더) 통과, 실패 = 기준 미달 39건 — 시험 오류 0):**

| 완료 기준 | 결과 | 충족 |
| :--- | :--- | :---: |
| 1 관통 | 손 · 아래팔 ↔ 몸 쌍: 낫 정정 7.4% · 11.86 → 0 · 2.1 cm · s26 70.2 · 6.32 → 0 · 0.86 · 검 선택 77.7 · 10.18 → 0 · 1.28 · 띠 정정 0.8 · 2.73 → 0 · 0.84 · 칼 시험 0 · 1.19 → 0 · 0 · 운영 걷기 22.3 · 7.93 → 0 · 0 · 달리기 15.8 · 10.84 → 0 · 1.93 · 라이플 34.5 · 3.25 → 0 · 0 · 낫 Attack2 27.1 · 6.43 → 0 · 2.02. **못 맞춤:** s25 50.4 · 14.7 → 0.8 · 2.41(머리 1 프레임 — NOT_RESOLVED) · s27 57 · 11.08 → 3.3 · 10.07(머리 — JOINT_LIMIT, 인계 위험). 머리목 관통 0 · head_near ≤ 5% 는 s25 · s27 밖 전부(s27 head_near 55.8 → 3.3). 손끼리: 검 선택 62.8 · 5.09 → 0 · 1.87(사용자 Persona f0 소견 자리) · **낫 Attack2 7.3 · 5.31 → 12.5 · 5.23(나빠짐 — 파지 프레임 손끼리 · keep 충돌, 모델도 남김)**. 위팔 쌍 '나빠지지 않음' 전부(검 선택 90.9 · 11.48 → 82.6 · 4.86, 라이플 98.1 → 28.1%) | 부분 |
| 2 파지 keep | `grip_pct` 줄지 않음 전부. keep 상대 위치 최대 ≤ 1 cm × scale 은 **못 맞춤** — 모델 최대 1.07 ~ 2.66 cm(p95 0.74 ~ 2.44) · C++ 손목 실측 1.0 ~ 2.6 cm, 방향 ≤ 5° 는 검 선택(9.4°) 밖 전부. s27 10.9 cm(머리 속 손 — 인계 위험). 한계 `GRIP_RELAXED` | 아님 |
| 3 발 | 접지 미끄러짐 p95 · 두 발 디딘 발 좌우 비 전 = 후(다리 자유도 없음 — 목표 없으면 다리 불변) | 예 |
| 4 충실도 | 보정 구간(± 2·폭) 밖 관절 변화 0 · 검증 FAILED 0 · 꼬임 나빠짐 0 · 떨림 기준 안(라이플 대기 0.29 → 0.81 밖 전부). **못 맞춤:** 휘두름 ± 5% — 낫 정정 +6.5 · s25 −9.4 · 검 선택 −16.6(인계 위험 — 아래팔 가슴 속 6.7 cm 라 두 손을 함께 앞으로) · s27 +8.2 · 라이플 대기 +59(정지 동작 — 작은 값 비율) · 낫 Attack2 +16, 궤적 폭 — 낫 정정 +5.3 · 검 선택 −12 · 걷기 +7.9 · 달리기 +7.0 · 라이플 +47, 보조 손목 굽힘 최대 ≤ +5° — 낫 정정 +11 · s27 +13 · 검 선택 +12(파지 프레임은 두 손목을 연다 — keep 방향을 맞추느라 더 굽는다) | 부분 |
| 5 예측 vs 실측 | 손 · 아래팔 목표 쌍은 전부 일치(쌍별 관통 % 차 ≤ 1 · p95 차 ≤ 0.3 — 낫 Attack2 손끼리 1.0 · T3 손끼리 하나 빼고). **기록만 하는 위팔 쌍 `l\|upper_arm\|chest` 가 9 Job 에서 어긋남**(예측 0 ~ 72% vs 실측 1.3 ~ 74% — 원인 추정: 겨드랑이 몸통 정점은 팔 본 가중이 섞여 C++ 지도에서는 팔과 함께 움직이는데 Python 은 기준 본 강체로 본다) | 부분 |
| 6 기존 Vesper 애니 | 걷기 · 달리기 · 라이플 대기 · 낫 Attack2 — 새 애셋, 원본 SHA-256 불변 · 기준은 위 1 ~ 4 행에 함께 | 예(기준은 위) |
| 7 스트레스 | 이전 낫(축 결함) — FAILED 0 · 다리 0 · 꼬임 91.7 → 31.7%, 손 · 아래팔 75.2 · 16.9 → 42.1 · 10.81(머리 — JOINT_LIMIT) | 예 |
| 8 지시 목표 | 계획이 목표를 풀어 보임(T1: swing_end 2.667초 → 프레임 80 ~ 89 · ease 4 · hand_r · Δ (0, 0, −15)) · 오류 4종 막음. T2(spine_05 yaw 15°) 2.26° 닿음 · T3(골반 −5 cm) 0.007 cm 닿음 · 발 고정 0.0 cm · 늘어남 0 · T4 관통에 막힘(`blocked_by` clearance · grip, 새 관통 0) · `SEAM_JUMP` T1 · T2 · T4 0. **못 맞춤:** T1 못 닿음(4.19 cm — clearance · grip · joint_limit), T3 프레임 0 `SEAM_JUMP` 3.07, **구간 ± ease 밖 변화(목표 없는 같은 Job 대비) T1 1.81 · T2 5.05 · T3 23.35 · T4 10.41 cm**, 떨림 T1 1.53 → 5.44 · T2 1.44 → 11.96 · T3 0.46 → 5.47 · T4 0.46 → 5.98, T3 keep 10.8 cm | 아님 |
| 9 전후 캡처 | 16건 후 \| 전(목표는 후 \| 목표 없음) 비교 시트 · APNG — 낫은 `WeaponHandR` 부착, 잘린 칸 0 · 더티 0 — `Tools/mcp/results/capture/P84Run1028_181805/<이름>/` · `P84Run1028_183211/<이름>/` | 예 |

**사용자 Persona 자리(깊이 cm, + 안쪽 — 전 → 후):** 낫 정정 f46 손 → 머리 11.86 → 0.32 · f50/51 손 → 가슴 6.76 → 1.85 · f70/73 손 · 아래팔 → 허리 · 다리 5.54 → −8.47(틈), 코트 자락(secondary) 왼팔 2.5% · 7.45 → 0 · 0.9 / 검 선택 f34 손 → 머리 7.22 → 지도 밖 · f0/f46 아래팔 → 가슴 6.69 → −2.97 · 위팔(기록) 11.03 → 3.69 · f0 손끼리 2.2 → 1.19(맞닿음 1.05 수준) / 운영 걷기 f22 손 → 넓적다리 6.52 → −3.95 / 라이플 대기 f51 왼 위팔(기록 — 측정 과대) 3.84 → 2.33 · 왼 손 · 아래팔 1.11 → −4.01.

**회귀:** Development · DebugGame 빌드 경고 0(툴체인 안내만) · Automation `AnimGraphMcp.*` 35/35 · pytest 603 · 통합 phase1 · phase2 · phase3 · phase8_2 실패 0 · phase8_4 `model`(기본 결과 = 옛 빌드 16/16 · 재현 p95 ≤ 0.0048 cm) 실패 0 · phase8_3 `quality` 1건 = 알려진 검 선택 다리 떨림 1.891 > 1.56(8-4d 기준 1, 값 그대로).

**풀이 시간:** 17.7 ~ 196.5초(8 대상) · 22.8 ~ 85.4(운영) · 22.2 ~ 286.5(목표 — T3 골반 · 다리), 측정 · 쓰기 · 재측정은 합쳐 5 ~ 6초.

**지시 목표 경로의 문제 (원인 조사 — 고치지 않음, 설계 결정 필요):**
- 구간 안 관통 몫은 ρ 블렌드로 그 프레임 Δ 를 매끈화 없이 그대로 쓴다(목표가 관통에 막힌 되돌림이 이웃으로 번지지 않게 한 설계) → 프레임마다 다른 관통 해가 그대로 남아 구간 안 떨림이 커진다(T2 11.96).
- 구간 밖 변화는 목표 몫이 아니다(x_T 는 구간 밖 0) — ① 재검사 '±1 프레임 받침'이 ρ 를 안 봐 구간 가장자리 증분이 밖으로 복사된다(오프라인 T1: (1 − ρ) 로 줄이면 1.81 → 1.69 cm) ② 관통 몫 스플라인이 목표 자세가 바꾼 관통 보정에 반응한다(구간을 스플라인에서 비우면 먼 프레임 0.1 cm 안팎 · 구간 ± 6 프레임 1.5 ~ 1.8 그대로) ③ 위반 프레임이 이어지는 대상(검 선택 — 거의 전 프레임)은 앞 프레임 해로 시작하는 사슬이 구간 끝의 다른 상태에서 출발해 뒤쪽 전체가 다른 국소 해로 간다(T3 프레임 47 23 cm · T4 10 cm).
- 수정 후보(8-4c 와 함께 또는 따로 — 사용자 결정): 목표 없는 풀이를 먼저 하고 구간 ± (ease + 2·폭) 밖은 그 해를 그대로 잇기(기준 8 을 정의대로) · 구간 안 관통 몫도 약한 매끈화 · 받침 (1 − ρ).

**읽는 법 · 한계:** 관통은 반경 지도 근사(§13 · 부록 B), 판정은 사람(캡처 — §16-9). 휘두름 · 궤적 폭 비율은 정지 동작(라이플 대기)에서 작은 값이라 과장된다. keep 은 모델(손바닥 점) · C++(손목) 두 값을 남겼다.

#### 8-4b 후속 — 루프 이음매 · 팔 벌어짐 (2026-10-28 밤)

**사용자 소견(Persona):** 운영 걷기 보정본(`P84Run1028_183211/AS_Vesper_Neutral_P84bOpWalkFit`) 등의 팔이 몸에서 지나치게 떨어지고, 걷기 루프의 시작 · 끝이 달라 끊긴다.

**진단(오프라인 — 8-4a 모델 사본, 처음 판 = 에디터 결과와 같은 수치 재현):** 걷기 손목이 121 프레임 전부 3 cm 넘게 움직였다(p50 13.9 · p95 21.0 · 최대 24.2 cm — 관통 없던 f0 도 19 cm). 깊이는 과대가 아니다(f22 최심 = 엄지 끝이 넓적다리 축에서 3.6 cm). 주원인은 스플라인이다 — 바깥 프레임 가중 1 이 λ 에 비해 약해, 반 주기마다 넓적다리를 스치는 걷기에서 사이 프레임까지 팔을 벌린 채 이었다. 첫 · 끝 프레임 보정 차 15.3°(왼 아래팔) — 스플라인 · 프레임 사슬이 순환이 아니다(달리기 8.1°).

**수정(사용자 승인 ① ② ③ — 구현에서 다듬은 것 둘은 굵게):**
- ① **루프 순환** — 원본 측정의 `numeric.loop`(C++ bLoop 한 원천 — 요청 `loop` 아님)면 끝 프레임 = 첫 프레임(같은 시점)으로 보고 스플라인을 순환으로(끝을 뺀 열을 앞뒤로 8 × 폭 감아 붙여 풀고 가운데를 쓴다 — 두 관측은 보정한 쪽 값으로 합침), 재검사 받침 · 앞 프레임 연속 항도 감아 돈다, 결과 첫 · 끝 상태 같음. Job `fix.body.loop{source, seam_deg(첫 · 끝 델타 차 °), boundary_max_deg[전, 후](C++ 첫 · 끝 포즈 차)}`, 통합 기준 `c4_loop`(원본 루프면 후 경계 ≤ 전 + 0.5° 또는 이음매 ≤ 0.5°).
- ② **바깥 프레임 가중** `SPLINE_QUIET_WEIGHT` 1 → 10(포락선 · λ · 보정 가중 30 그대로). **재검사 증분만 `SPLINE_RECHECK_QUIET_WEIGHT` 1** — 재검사는 남은 1 ~ 3 프레임 위반의 작은 증분이라 10 이면 절반쯤 묽어져 패스가 끝나도 못 풀었다(오프라인 걷기 손 → 넓적다리 1.7% · 4.44 cm · 달리기 1.3% · 2.47 → 0, 손목 p50 +0.9 cm).
- ③ **맞닿음 허용** `fix.body.clearance.allow_contact`(기본 true) — 몸 지도 관통 잔차 `깊이 + margin` → `깊이 − contact_cm`(≤ 접촉은 정상, 관통 판정 2.1 cm 그대로 — 손끼리와 같은 규칙), false 면 처음 판. **몸통 · 넓적다리만(`CONTACT_MAPS`) — 머리목은 margin 그대로**: 맞닿음(1.05)과 관통 판정(2.1) 사이 여유가 1 cm 뿐이라 매끈화로 묽어진 프레임이 넘는다(오프라인 검 선택 손 → 머리 2.5% · 8.26 cm, 머리목 margin 이면 0.8% · 2.19). 넓적다리만은 안 된다 — 걷기 손은 골반 쪽 몸통에도 스친다(손목 p50 13.7 그대로). 후보 점 문턱은 허용 깊이와 무관(−(margin + 3 cm)).
- 범위 밖(사용자 결정): ④ 손가락 끝 점 가중 낮추기, 지시 목표 경로(위 '지시 목표 경로의 문제').

**오프라인 변형 비교(모델 예측 — 손끼리 지도 없는 8-4a 사본, 손목 이동 p50 / p95 / 최대 cm · 남은 손 · 아래팔 관통 % · cm):**

| 대상 | 처음 판 | ② 만 | ③ 만(모든 지도) | ② + ③(모든 지도) | 채택(② + 재검사 1 + ③ 머리목 margin + ①) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 운영 걷기 | 13.9 / 21.0 / 24.2 · 0 · 이음매 15.3° | — | — | 6.5 / 14.4 / 15.6 · 1.7% · 4.44 · 0° | 7.4 / 14.9 / 15.8 · 0 · 0° ‡ |
| 운영 달리기 | 6.6 / 13.7 / 16.7 · 0 · 8.1° | — | — | 2.1 / 8.0 / 10.1 · 1.3% · 2.47 · 0° | 2.8 / 9.2 / 11.3 · 0 · 0° ‡ |
| 낫 정정 | 1.9 / 16.2 / 22.1 · 0 · keep 1.87 | 1.5 / 14.5 / 21.8 · 0 | 0.7 / 10.4 / 16.6 · 머리 1.7% · 3.51 † | 0.2 / 10.1 / 16.2 · 머리 0.8% · 4.08 | 0.3 / 13.1 / 21.3 · 머리 1.7% · 2.37 · 가슴 0.8% · 2.98 · keep 1.91 |
| 검 선택 | 17.7 / 23.0 / 24.3 · 머리 1.7% · 2.96 | — | — | 11.9 / 17.8 / 23.0 · 머리 2.5% · 8.26 | 11.9 / 22.0 / 24.3 · 머리 0.8% · 2.19 |
| 낫 Attack2 | 7.2 / 13.4 / 19.2 · 넓적다리 1.0% · 2.22 · keep 3.57 | 5.7 / 13.7 / 19.3 · 1.0% · 2.35 | 5.5 / 13.3 / 24.6 · 2.1% · 3.26 † | — | 4.8 / 13.1 / 24.6 · 2.1% · 3.23 · keep 3.64 |
| 띠 정정 | 0.1 / 6.7 / 11.2 · 0 · keep 1.37 · 떨림 0.89 | — | — | 0.0 / 2.2 / 4.5 · 0 · keep 0.46 · 1.00 † | 0.0 / 3.4 / 5.3 · 0 · keep 0.54 · 떨림 1.03 |

† 후보 점 문턱을 '허용 깊이 − 3 cm' 로 좁혔던 중간 판 실행(정정 전 — 참고값). ‡ 재검사 가중 1 · 맞닿음 모든 지도(걷기 · 달리기는 머리와 무관 — 걷기는 채택 조합으로 다시 돌려 같은 값). 처음 판 = 마무리 세션 표와 같다(걷기 13.89 / 21.03 / 24.19 재현).

**결과(통합 — `hashes,clearance,dirty` 실행 `P84Run1028_205745` 실패 17 · `hashes,targets,existing,dirty` 실행 `P84Run1028_211420` 실패 30, 전부 기준 미달 · 시험 오류 0 · 비파괴 통과, `model` 회귀 `P84Run1028_212754` 실패 0 · pytest 609):** C++ 실측, 지난 실행(`P84Run1028_181805` · `_183211`) → 이번. 손목 이동 = 두 손목 중 큰 쪽의 원본 대비 위치 차.

| 대상 | 손목 이동 p50 / p95 / max cm | 루프 경계 ° (원본 → 지난 → 이번) | 손 · 아래팔 ↔ 몸 % · cm | 그 밖 |
| :--- | :--- | :--- | :--- | :--- |
| 운영 걷기 | 13.87 / 21.06 / 24.18 → **7.39 / 14.86 / 15.77** | 0.03 → 18.96 → **0.03**(이음매 0) | 0 · 0 → 0 · 2.02(접촉) | 궤적 폭 +7.9 → +1.6% |
| 운영 달리기 | 6.8 / 13.65 / 16.69 → **2.76 / 9.19 / 11.25** | 0 → 8.8 → **0** | 0 · 1.93 → 0 · 1.84 | 폭 +7.0 → +1.8% |
| 라이플 대기 | 5.52 / 7.62 / 10.38 → 2.42 / 6.69 / 8.62 | — | 0 · 0 → 0 · 1.15 | 떨림 0.81 → 0.42(원본 0.29) · 휘두름 +59 → +26% |
| 띠 정정 | 0.11 / 6.75 / 11.18 → 0.0 / 3.38 / 5.27 | — | 0 · 0.84 → 0 · 0 | keep 1.37 → **0.54**(기준 안) · 떨림 1.27 → 1.45 |
| 낫 정정 | 1.93 / 16.26 / 22.1 → 0.36 / 13.14 / 21.3 | — | 0 · 2.1 → **1.7 · 3.1** | 머리목 0 → **1.7% · 2.37** · 떨림 1.74 → 1.90 |
| 검 선택 | 17.85 / 22.32 / 23.25 → 17.99 / 22.68 / 23.55 | — | 0 · 1.28 → 0 · 1.04 | 손끼리 0 · 1.87 → 0.8 · 2.11 · 폭 −12.1 → −3.3% |
| 낫 Attack2 | 5.91 / 15.08 / 15.42 → 4.36 / 12.49 / 18.87 | — | 0 · 2.02 → **2.1 · 2.33** | keep 모델 2.66 → 3.56(C++ 손목 2.61 → 2.15) |
| s25 · s26 · s27 | > 3 cm 표본 91 → 43 · 108 → 92 · 95 → 93 | — | s25 2.41 → **4.05** · s26 0.86 → 1.51 · s27 10.07 → 9.67 | s27 keep 10.9 → 8.4 |
| T1 ~ T4 | — | — | T2 0 → 0.8% · 2.26 · **T3 · T4 0 → 3.3% · 9.3(머리 — 구간 밖 f34 ~ 38)** | T1 오차 4.19 → 2.71 · 구간 밖 T1 1.81 → 1.20 · T2 5.05 → 3.64 · T3 23.35 → 17.93 · T4 10.41 → 24.71 · T3 SEAM_JUMP 1 → 0 · 떨림 T3 5.47 → 2.04 |

- **읽는 법:** 루프 두 대상과 띠 정정 · 라이플은 좋아졌다. 빠른 무기 휘두름은 맞닿음 허용 뒤 1 ~ 2 프레임 관통이 새로 남는다(부록 B). 걷기 손목 p95 14.9 cm 는 인계 조건(≈ 14)이라 ④(손가락 끝 점 가중) 여부는 사용자 판정 뒤.
- **T3 · T4 머리 관통:** 위 '지시 목표 경로의 문제' ③(위반 프레임 사슬이 다른 국소 해 — 쇄골 상한 JOINT_LIMIT)이 머리 안에서 멈춘 것이다. 목표 없는 같은 Job 은 머리 0.
- **캡처:** `Tools/mcp/results/capture/P84Run1028_205745/` · `P84Run1028_211420/<대상>{, _vs_prev}/`(이번 | 원본 · 이번 | 지난 보정본) — 후속 2차가 대신해 정리했다(Content · 캡처 휴지통, 수치는 위 표).

**후속 2차 — 위팔 '안 깊어짐' 층 (2026-10-29, 사용자 Persona 재판정 뒤):**

- **소견:** 걷기 보정본의 팔이 주기마다 달라 중간(f32 · f39)에 허리에서 더 멀어졌다 돌아온다. 낫 정정 f72 손목이 크게 꺾인다. 나머지는 통과.
- **진단(오프라인):** 원본 관통은 4 주기가 비슷하다(30 프레임마다 접촉 넘는 프레임 6 ~ 9). 그런데 왼손목 바깥 이동 최대는 10 / 13.6 / 13.4 / 7 cm 로 주기마다 달랐다. 가장 먼 f30 ~ 33 은 원본이 넓적다리에서 3.7 ~ 5.8 cm 떨어진 프레임이다(위팔 보정 6.2 → 17.6 → 4.4°). 위팔 '안 깊어짐' 위반이 65 프레임(손 44 보다 많다)이었다. 사이로 이어진 보정이 위팔을 조금 깊게 만들고, 재검사가 그것을 하드 층으로 다시 풀며 팔을 벌렸다.
- **효과 없던 것:** 재검사 가중 1 ↔ 10, 위팔 허용 폭 +0.5 · +1 cm · 바닥 1.8 cm.
- **수정:** `TIER["upper"]` 10(keep 층 — 관통의 1/3), `_violations` 에서 위팔 제외(풀 때만 함께 맞춘다).
- **손목:** 낫 정정 f72 왼손목은 원본 91.1° → 100.5°(파지 프레임은 두 손목이 자유도) — 원본 탓이 대부분이라 8-4c(부록 B '파지 keep · 보조 손목').
- **결과(통합 — `hashes,clearance,dirty` `P84Run1029_152335` 실패 15 · `hashes,targets,existing,dirty` `P84Run1029_154526` 실패 31, 전부 기준 미달 · 시험 오류 0 · 비파괴 통과 · pytest 610):** 아래 표는 1차 후속 → 2차.

| 대상 | 손목 이동 p50 / p95 / max cm | 손 · 아래팔 ↔ 몸 % · cm | 그 밖 |
| :--- | :--- | :--- | :--- |
| 운영 걷기 | 7.39 / 14.86 / 15.77 → **4.70 / 6.61 / 6.98** | 0 · 2.02 → **1.7 · 4.58**(오른손 → 넓적다리 2 프레임) | 주기마다 바깥 최대 3.9 ~ 5.7 cm(오프라인) · 루프 0.03° · 이음매 0 · 궤적 폭 +1.6 → +8.6% |
| 운영 달리기 | 2.76 / 9.19 / 11.25 → 3.06 / 9.23 / 11.05 | 0 · 1.84 → 0 · 1.75 | 루프 0° |
| 라이플 대기 | 2.42 / 6.69 / 8.62 → 1.53 / 4.18 / 5.43 | 0 · 1.15 → 0 · 1.46 | 떨림 0.42 → 0.30(원본 0.29) · 휘두름 · 폭 기준 안으로 |
| 낫 정정 | 0.36 / 13.14 / 21.3 → 0.33 / 12.89 / 21.49 | 1.7 · 3.1 → 1.7 · 3.09 | **머리목 1.7% · 2.37 → 0** · 떨림 1.90 → 2.01 |
| s25 · s26 · s27 | s25 p95 12.6 → 17.2 · s26 8.6 → 7.8 · s27 23.8 → 24.7 | s25 4.05 → 2.71 · s26 1.51 → 1.52 · s27 9.67 → 10.15 | s25 머리목 0.8% → 0 · s27 keep 8.4 → 6.6 · 위팔(기록) 왼 → 가슴 s25 14 → 19% · s26 10.7 → 19% |
| 검 선택 | 17.99 / 22.68 / 23.55 → 18.21 / 22.01 / 23.26 | 0 · 1.04 → 0 · 1.7 | 손끼리 2.11 → 2.17 |
| 띠 정정 | 0 / 3.38 / 5.27 → 0 / 3.2 / 4.67 | 0 → 0 · 0.63 | keep 0.54 → 0.45 |
| 축 결함(스트레스) | 21.82 / 25.4 → 19.42 / 25.37 | **49.6 · 10.4 → 3.3 · 3.34** | 머리목 49.6% → 0 · keep 6.19 → 2.20 |
| 낫 Attack2 | 4.36 / 12.49 / 18.87 → 4.11 / 10.01 / 21.13 | 2.1 · 2.33 → 2.1 · 2.74 | keep 3.56 → 3.33 |
| T3 · T4 | — | **T3 3.3 · 9.37(머리) → 0 · 0.28** · T4 3.3 · 9.28 → 2.5 · 10.63(머리 — 구간 밖) | 구간 밖 변화 T3 17.9 → 4.9 · T4 24.7 → 30.5 cm |

- **읽는 법:** 걷기는 주기가 고르고 팔이 붙었다(사용자 소견의 원인). 대신 오른손이 넓적다리에 2 프레임 4.58 cm 남는다 — 재검사가 수렴하지 못한 자리다. 위팔 쌍은 기록만 하는 쌍이지만 일부 대상(s25 · s26 · 검 선택)에서 '나빠지지 않음'이 미달이다.
- **캡처:** `Tools/mcp/results/capture/P84Run1029_152335/` · `P84Run1029_154526/<대상>{, _vs_prev}/`(이번 | 원본 · 이번 | 1차 후속).

### 별도 트랙 — 3D 메시(에셋) 생성 (개정 9 메모)

애니 파이프라인(이 지침서의 Phase 1 ~ 8) 밖의 별도 작업으로 둔다 — **애니 자동화 뒤**에 착수(사용자 결정 2026-10-25). Phase 6(외부 AI **애니메이션**)에 넣지 않는 이유: 완료 기준이 모션(`AS_` · 리타깃 · 검증)이고, 요청 스키마(대상 스켈레톤 · 동작 분류 · 애니 이름)와 맞지 않으며, 메시 임포트는 재질 · 텍스처가 핵심이라 지금 `import_animation_file`(리타깃 소스용 — 재질 · 텍스처를 끈다)과 다른 경로가 필요하다.

- 후보: Tripo3D — 텍스트 · 이미지 → 3D 메시(공식 CLI · API), 자동 리깅. 무료 크레딧 · 가격 · 출력 리그 · 약관은 그 트랙에서 다시 확인. 조사 · 설계 초안(모션 Provider 로는 채택 안 함 결론 포함): 공유 노트 `phase6-tripo-survey-design.md`(Tripo 세션)
- 재사용: Phase 6 의 외부 API 공통 구조(승인 · 장부 `(plan_id, attempt)` · 요청 로그 · 비동기 Job · 키는 환경 변수만 · 기본 URL 고정)
- 애니 쪽과 만나는 곳: 생성 · 리깅한 캐릭터를 새 대상 스켈레톤으로 삼아 Vesper 애니를 리타깃(Phase 8 "다양한 스켈레톤")

---

## 15. 테스트 시나리오

| 원본 | 개정 | Phase | 종류 |
| :--- | :--- | :---: | :--- |
| A 무료 기본 동작 | 기존 공격에서 트림·편집으로 공격 준비·복귀 생성 | 2 | 에디터 통합 |
| B 기존 모션 수정 | 그대로 + 원본 패키지 해시 불변 확인 | 2 | 에디터 통합 |
| C 커스텀 스켈레톤 | Narmaya 또는 SB ↔ `SKEL_UE5_F`, 수동 체인 폴백 포함 | 1 | 에디터 통합 |
| D 폴백 | Mock Provider 실패 → 다른 Provider · 경로 기록 | 3 | Mock (pytest) |
| E 비용 통제 | `FREE_ONLY` + 유료 요청 → `APPROVAL_REQUIRED`/`BUDGET_EXCEEDED`, 외부 호출 0 | 3 · 6 | Mock → 실제 어댑터 |
| F AnimBP 연결 | 명시 요청(`integrate_anim_bp` + `anim_bp`) 시에만 기존 AnimBP MCP로 연결 — 개정 10: 운영 AnimBP 는 복제본에서 적용 · 컴파일 · 스모크 · 시나리오, 운영은 revision · 미리보기 · 적용 페이로드까지(SHA-256 불변). 연속(생성 → BS → 전이 · 생성 → additive 몽타주 → 슬롯) · 독립(기존 애셋 재사용 → 몽타주 → 슬롯) · 승격(리디렉터 0 · 참조 유지) — `anim_gen_phase7_test.py` | 7 | 에디터 통합 + pytest(`test_integrate.py`) |
| (신규) G 회귀 비교 | Tool이 만든 리타기터 결과 vs 기존 RTG 결과 | 1 | 에디터 통합 |
| (신규) I 대상 메시 캡처 (개정 12) | 기존 애셋(칼 시험 · 8-1 검 · 낫 선택)을 Vesper 로 캡처 + 소스 골격 비교 시트 · APNG · 가드(루트 · 폴더 · 이미지 · 더티 0) · BVH → blender render → 리타깃 → capture Job — `anim_gen_phase8_2_test.py` | 8 | 에디터 통합 + pytest(`test_capture.py`) + Automation(`AnimGraphMcp.Generation.Capture`) |
| (신규) K 대상 쪽 보정 기반 (개정 14 — 8-4a) | 비교 대상 16개(8-1 · 8-3 결과 · 운영 Vesper) — 기본 body_clearance = 옛 빌드 baseline · parts all(소견 자리 · head_near 방향) · Python 몸 모델 재현 = C++ · bone_deltas · profile_rotations · E0(낫 부착값 · 자루 선 · 왼손 파지 선분 · 사건 · 낫 붙인 '전' 캡처) — `anim_gen_phase8_4_test.py`(baseline 은 코드 바꾸기 전 빌드에서 한 번) | 8 | 에디터 통합 + pytest(`test_body_model.py`) + Automation(`AnimGraphMcp.Generation.{BodyClearance, Edit, Capture, Geometry}`) |
| (신규) L 한 풀이 · 지시 목표 (개정 14 — 8-4b) | 비교 대상 8개 + 운영 Vesper 4개를 기존 애셋 경로 `fix.body` Job 으로 — 기준 1 ~ 5 · 스트레스 7 · 사용자 Persona 자리 전후 · 전후 캡처(낫 부착), 표준 지시 T1 ~ T4(목표 오차 · `SEAM_JUMP` · 목표 없는 같은 Job 대비 구간 밖 변화 · 발 고정 · 막힘), 계획(목표 풀어 보임 · 생성 경로 단계 순서 · 오류 4종) — `anim_gen_phase8_4_test.py --only plan,clearance,targets,existing`(targets 는 clearance 뒤) | 8 | 에디터 통합 + pytest(`test_body_fit.py` · `test_body_fit_pipe.py` · `test_body_model.py` 손끼리) + Automation(`BodyClearance` 손끼리) |
| (신규) J 자동 보정 (개정 13) | 시험 대상 4개(칼 시험 · 8-1 검 · 낫 선택 둘) — 저장된 Kimodo BVH 재리타깃 = 기존(기준 재현) · `fix.timing`(기존 애셋) · `fix.ops` 다리(BVH — 대상 모델 풀이) · smooth · 합본 Job · 전후 캡처(warp 행 · 비교 시트 · APNG) — `anim_gen_phase8_3_test.py` | 8 | 에디터 · Blender 통합 + pytest(`test_timing.py` · `test_fix_legs.py`) + Automation(`AnimGraphMcp.Generation.Capture`) |
| (신규) H 생성 품질 (개정 11) | 양손 칼 베기 프롬프트 + `two_hand_weapon_grip` · `foot_contact` → 2차 생성(meet · lead) · seed 후보 4개 선별 · 같은 seed measure vs resolve(E1) · 프롬프트만 바꿈(E3) — `anim_gen_phase8_1_test.py` | 8 | 실제 Kimodo · Blender · 에디터 + pytest(`test_refine.py` · `test_select.py`) |

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
9. 애셋 생성 성공과 시각 품질 검증 성공을 혼동하지 않는다. 개정 11: **선별은 수치, 판정은 사람** — 후보 선별(select)은 근거(Job `selection` 의 원 수치 · 벌점 · 순위)와 함께 보이고 한계 `SELECTED_BY_NUMBERS` 를 단다. 수치 기준 통과를 품질 합격으로 보고하지 않는다. 개정 12: 대상 메시 캡처(`review.capture`)는 판정의 **근거**다 — 캡처가 나왔다는 것을 품질 합격으로 보고하지 않고, 한계 `REVIEW_CAPTURE_PREVIEW_ONLY`(무기 · 물리 · AnimBP 레이어 없음)를 함께 보인다.
10. 에디터 전용 제작 기능을 런타임 모듈에 넣지 않는다.
11. 외부 서비스에 캐릭터 데이터나 애셋을 보낼 때는 그 서비스의 데이터 정책을 확인한다.
12. 미완성 기능이나 Mock 동작을 실제 구현 완료로 보고하지 않는다.

추가:

13. 기존 응답 봉투와 오류 체계를 깨지 않는다.
14. 게임 스레드에서 네트워크 호출·서브프로세스·대기를 하지 않는다.
15. `anim_graph_mcp/server.py`에 로직을 넣지 않는다(프록시만).
16. API 키를 저장소·로그·Tool 인자·Job 기록에 남기지 않는다(환경 변수만).
17. 생성물은 허용 목록 경로에만 쓴다. 정식 경로 이동은 사용자 확인 후 — `promote_animation` 의 `dry_run` → 확인 → `confirm`, 대상은 ini `PromotionPaths` 안만(개정 10). 운영 AnimBP 적용도 사용자 승인 뒤 사람이 한다(anim_gen 은 복제본까지 — §12).
18. 플러그인에 프로젝트 고유 이름·경로를 하드코딩하지 않는다.

---

## 17. Claude Code 작업 지시

1. 한 번에 한 Phase만 진행한다(Phase 0 · 1 · 2 · 3 · 4 · 5 · 6 · 7 완료 — 6 의 실제 유료 1건은 미실행, 7 의 운영 AnimBP 실제 적용은 범위 밖. 8-1 구현 · 검증 + 수정안 A · B · C 2026-10-26 — 사람 재판정 대기, 8-2 구현 · 검증 2026-10-26 — 캡처 결과는 사람 판정 대기, 8-3 구현 · 검증 2026-10-27 + 후속 수정 2건(같은 날 밤) — 전후 캡처 사용자 판정 통과 · antialias 1.0 확정, 8-4a 기반 구현 · 검증 2026-10-28 — 낫 붙인 '전' 캡처는 사람 판정 근거, 8-4b 한 풀이 구현 · 검증 2026-10-28 — 관통 목표 쌍 대부분 해소 · keep · 충실도 일부 · 지시 목표 경로 기준 미달, 전후 캡처 사람 판정 · 수정 방향 결정 대기). 다음 Phase는 사용자 승인 후 착수한다. Phase 8 은 단위(8-1 ~ 8-4)마다, 8-4 는 하위 단위(a ~ d)마다 승인한다.
2. 각 Phase는 코드 편집 전에 Tool 시그니처 · 커밋 단위 · 구현 순서를 보여 주고 **사용자 확인을 받는다.** 문서와 엔진 API가 어긋나면 문서 수정안을 함께 낸다.
3. 에디터 확인용 애셋은 `/Game/Animation/Test/AIAnimation/`에 만들고, 끝나면 정리 목록을 보고한다.
4. 순서: 구현 → 정적 검증(두 구성 빌드 · Python 문법) → 에디터 통합 테스트(`Tools/mcp/anim_gen_phaseN_test.py`) → 결과 기록.
5. 보고에 포함할 것(원본 유지): 수정·추가된 파일 · 새 MCP Tool · 구현된 기능 · 실제 테스트 여부 · 실패·미검증 사항 · 기존 AnimBP MCP에 미친 영향 · 후속 Phase 작업. 여기에 **그 Phase 완료 기준 각각의 충족 여부**를 더한다.

---

## 부록 A. 출처

- 엔진 소스: `D:/UnrealSource/UnrealEngine-5.7.4-release/Engine/` 아래, §2.3 표의 경로
- 기존 플러그인: [Plugins/AnimGraphMcp/README.md](../../Plugins/AnimGraphMcp/README.md) · `Tools/mcp/anim_graph_mcp/server.py` · `bridge.py`
- HY-Motion 1.0 라이선스: <https://raw.githubusercontent.com/Tencent-Hunyuan/HY-Motion-1.0/master/License.txt> · <https://huggingface.co/tencent/HY-Motion-1.0>
- Meshy Text-to-Motion API: <https://docs.meshy.ai/vi/api/text-to-motion> · 개정 9(2026-10-25 열람): <https://docs.meshy.ai/en/api/text-to-motion> · 가격(크레딧) <https://docs.meshy.ai/en/api/pricing> · Rate Limit <https://docs.meshy.ai/en/api/rate-limits> · 오류 · `task_error` <https://docs.meshy.ai/en/api/errors> · 잔액 <https://docs.meshy.ai/en/api/balance> · 사용 내역(Studio · Enterprise) <https://docs.meshy.ai/en/api/usage> · 태스크 수명 · poll · 타임아웃 <https://docs.meshy.ai/api/task-lifecycle.md> · 결과 보존 3일 <https://docs.meshy.ai/api/asset-retention.md> · 인증(`msy_` 키 · IP 허용 목록) <https://docs.meshy.ai/api/authentication.md> · 변경 이력(2026-08-21 출시 · 2026-09-16 테스트 키 폐지) <https://docs.meshy.ai/api/changelog.md> · 메타데이터 태그(Studio · Enterprise) <https://docs.meshy.ai/api/metadata.md> · 문서 색인 <https://docs.meshy.ai/llms.txt> · 요금제(KRW 표시) <https://www.meshy.ai/pricing> · 크레딧 안내 <https://www.meshy.ai/tutorials/meshy-credits-guide> · 약관(2026-09-19) <https://www.meshy.ai/terms-of-use> · 개인정보(2026-09-19) <https://www.meshy.ai/privacy-policy>
- DeepMotion SayMotion REST API: <https://github.com/DeepMotion/SayMotion-REST-API> · <https://deepmotion.com/post/saymotion-api-now-available-for-free-trials>
- Phase 5 로컬 모델 조사(개정 8): [LocalModelSurvey.md](LocalModelSurvey.md) 부록(2026-10-24 열람 — 데이터셋 · 모델 · 라이선스 원문 전체 목록). 채택 근거만 여기 다시 적는다:
  - Kimodo 저장소 · 라이선스: <https://github.com/nv-tlabs/kimodo> · <https://github.com/nv-tlabs/kimodo/blob/main/LICENSE> · 출력 형식 <https://research.nvidia.com/labs/sil/projects/kimodo/docs/user_guide/output_formats.html> · BVH 내보내기 `kimodo/exports/bvh.py`
  - 모델 카드: <https://huggingface.co/nvidia/Kimodo-SOMA-RP-v1.2> · NVIDIA Open Model License <https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/>
  - 텍스트 인코더: Meta Llama 3 Community License <https://www.llama.com/llama3/license/> · <https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct>(게이트) · LLM2Vec 어댑터 <https://huggingface.co/McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp>
  - 공개 T2M 학습 데이터: AMASS License <https://amass.is.tue.mpg.de/license.html> · SMPL Model License <https://smpl.is.tue.mpg.de/modellicense.html> · HumanML3D <https://github.com/EricGuo5513/HumanML3D>
- 엔진 소스(개정 8 추가 행): `Plugins/Animation/IKRig/Source/IKRig/Private/Retargeter/{IKRetargetProcessor.cpp, IKRetargetChainMapping.cpp, RetargetOps/RunIKRigOp.cpp, RetargetOps/FKChainsOp.cpp, RetargetOps/RootMotionGeneratorOp.cpp}` · `…/IKRigEditor/Private/RetargetEditor/IKRetargeterPoseGenerator.cpp` · `Plugins/Interchange/Runtime/Source/Import/Private/Mesh/InterchangeSkeletalMeshFactory.cpp`

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
| ~~Blender 출력의 단위·축~~ · Meshy 출력의 단위·축 · 리그 | Blender — Phase 4 확인(§2.3 · §10). Meshy — 공식 문서에 없음(개정 9). Phase 6 실제 1건이 **미실행**(Free 요금제, 2026-10-25)이라 여전히 미확인 — 유료 요금제에서 `anim_gen_phase6_test.py --real` 이 임포트 스켈레톤 · 자동 IK Rig 템플릿 · 정면을 `real.rig` 에 기록한다. prime FBX 에 스킨 메시가 없으면 Interchange 가 스켈레톤을 만들지 못한다(§2.3) — 그때는 blender FBX 변환 경로가 후속 |
| ~~`import_animation_file` + `sample_rate` 의 경계 안 맞는 길이~~ | Phase 4 발견(Interchange 가 애니를 건너뛰어 `IMPORT_FAILED NO_ANIMATION`) → 개정 7 보강 2 해결 — `ConfigurePipeline` 이 `bSnapToClosestFrameBoundary` 를 항상 켜고, 맞춘 트랙은 `warning LENGTH_SNAPPED`. 경계 안 맞는 CMU 01_01 FBX `sample_rate=30` → 689키 · 22.9333초(§2.3). 다른 FBX(Meshy 등)도 같은 경로로 임포트된다. blender 의 범위 정렬(`bvh.align_to_rate`)은 그대로 둔다(반 프레임 늘림·줄임 없이 소스 프레임 그대로 — `RANGE_ALIGNED` 문구도 이에 맞춰 정정). 생성 잡도 이 진단을 받는다 — 실행기가 단계 안 에디터 진단을 `tool` · `step` 과 함께 Job `diagnostics` 에 남긴다(§3.4) |
| cgspeed CMU BVH 의 0번 프레임 | Phase 4 확인 — 회전 거의 없는 기준 포즈(T 비슷)라 1번 프레임에 최대 179.8° 튐(`ROTATION_JUMP_INHERITED`). `motion_file.range.start` = 1프레임으로 뺀다. 다른 CMU 클립도 같은 형식일 것(미확인) |
| ~~Meshy 길이 범위 · 가격 · 결과 파일 만료 · 데이터 정책~~ | Phase 6 확인(개정 9, §2.4 · 부록 A): 2 ~ 10초 · 0.5초 단위 · 프롬프트 ≤ 400자 · prime 10 / swift 3 크레딧(실패 환불) · 결과 3일 · 약관 수용(사용자). **크레딧의 돈 값은 공식 문서로 확정 불가**(요금제마다 다름) → 정책 `usd_per_credit`(사용자) |
| Meshy 크레딧의 돈 값 (개정 9) | 사용자 요금제가 정한다 — 월 크레딧을 다 쓰기 전에는 추가 지출이 없고, 크레딧 팩 가격은 공개되지 않았다. 정책 `external.meshy.usd_per_credit` 는 사용자가 정한 환산값이고 장부 USD 는 그 값 기준이다 |
| ~~공개 Text-to-Motion 모델의 학습 데이터 라이선스~~ | Phase 5 확인(개정 8, [조사](LocalModelSurvey.md) §2 · §3.1 · §4) — HumanML3D 계열의 학습 데이터 AMASS(와 SMPL)는 "commercial use of any kind" 를 위한 신경망 학습을 금지 → **상업 이용 부적법**. 개인 포트폴리오가 허용 범위(비상업 연구 · 교육 · 예술)에 드는지 · 가중치만 받은 사용자에게 미치는지는 원문이 정하지 않는다(사용자 판단, 채택하지 않음). HumanAct12 · KIT-ML · SnapMoGen 데이터 라이선스는 원문을 못 찾았지만 AMASS 로 이미 판정돼 결론에 영향 없음. **적법 · 호환 후보 Kimodo-SOMA-RP-v1.2 채택**(§2.4) |
| "Built with Meta Llama 3" 표시가 생성 애셋만 쓰는 게임 · 문서에도 필요한지 (개정 8) | 원문(Llama 3 License §1.b.i "a product or service that uses any of them")이 정하지 않는다 — 출시 · 배포 전 사용자 판단([조사](LocalModelSurvey.md) §4 K-1). 필요하다고 보면 표시를 넣는다 |
| Phase 5 결과의 사람 시각 확인 (개정 8) | 자동 검증(소스 대비 상대 비 · 손가락 · 관통 · 루트 궤적)과 소스 골격 렌더 시트까지 확인. **Vesper 메시로 Persona/PIE 에서 보는 것은 남음** — 통합 테스트 산출물(`P5Run…/AS_Vesper_Kimodo_WalkTurnBackP5` · `AS_Vesper_Kimodo_RootPathP5`)은 2026-10-25 휴지통으로 정리했다. 다시 보려면 `anim_gen_phase5_test.py --only hashes,generate,constraint,dirty` 로 만든다(같은 seed 면 같은 동작). 같은 계열로 이전 세션들이 남긴 확인용 애셋(관통 보정 CMU 오른팔 최대 27° 벌림 · SOMA 양손 상대 위치 · 손가락 메타카팔 상대 정렬)도 Persona 눈 확인 남음 |
| 기존 Vesper 애니의 팔-몸통 관통 (개정 8) | 다른 체형에서 리타깃된 원래 애니(Neutral Walk/Run · Rifle Idle)도 관통 프레임 18 ~ 35%(옷 부피 포함). 사용자 결정(2026-10-25)으로 일괄 보정하지 않음 — PIE 에서 거슬리면 재검토(확인 장면 `Neutral_Run_Loop_F` 1.9 s · `Walk_Loop_F` 0.23 s). 런타임 레이어가 팔을 덮으므로 고친다면 ABP · Control Rig 쪽도 후보 |
| Phase 8-1 결과의 사람 판정 · 기준 보정 (개정 11) | 수치 선별(§14 Phase 8 표)까지 확인 — **Persona 눈 확인은 사용자**. 소견 4가지 중 ①②③ 은 수정안 A · B · C 로 수치가 바뀌었다(재판정 대기), ④ 흐느적은 D(요청) · 8-3. 남은 보정 후보: 발 좌우 비 기준(2.5 · 폭 5.0) · 궤적 폭 하한(1.0) · 가중치 · `meet`/`lead` 기본값(수치는 `meet`) · 1차부터 꺾인 손목(seed 27 — 손목 상한). 원 수치는 Job `selection` 에 있어 다시 계산할 수 있다 |
| 2차 생성의 손 방향 · 손가락 · 무기 · 관통 (개정 11) | 손목 위치만 맞춘다(`GRIP_POSITION_ONLY`) — 손 회전은 1차 손목 굽힘 유지(수정안 B — 처음 규칙의 보조 손 '손목 → 중지 끝' 맞춤은 손목을 96 ~ 116° 꺾었다), 양손을 손잡이에 나란히 맞추지 않는다, 손가락은 고정 포즈. FK 리타깃은 양손 상대 위치를 보존하지 않는다(SOMA 어깨 반폭 17.3 vs Vesper 12.0 cm — Vesper 에서 간격 p50 5.2 ~ 6.6 cm 로 소스 7.2 ~ 8.1 보다 가깝다). 모은 팔의 몸 관통(72 ~ 84%)은 C안 — 모두 8-4. 8-4 는 머리 · 가슴 · 배를 포함한 몸 전체 관통 보정으로 범위를 보강했다(2026-10-26 밤, §14 Phase 8 '8-4 범위 보강 근거') |
| 2차 생성이 목표를 얼마나 따르는지 (개정 11) | 이 프롬프트 · seed 4개에서 목표 손목 오차 p50 1.8 ~ 2.5 · 최대 6.4 cm, 접지 발 ± 3.4 cm. 다른 동작(걷기 · 회전 · 큰 이동)과 `lead` 처럼 팔 밖 목표는 따르지 않을 수 있다(E2' 소스 파지 21.5%) — 동작 종류별 실측 남음. 비파지 프레임 관통의 프레임별 측정(C++)은 상한이 0% 라 필요 없었다(필요해지면 후속) |
| 대상 메시 캡처와 게임 화면의 차이 (개정 12) | 캡처는 시퀀스를 메시에 그대로 입힌 프리뷰다 — 무기 없음(개정 14: `attachments` 로 소켓에 붙여 찍는다 — 8-4a) · 옷 · 머리 물리 없음(천 시뮬레이션 끔) · 게임 AnimBP 레이어(왼손 IK · 조준 보정 · 레이어 블렌드) 없음 · 프리뷰 조명. 판정은 캡처로 하고, 게임 안 모습이 필요하면 PIE · 운영 ABP 복제본 시나리오(Phase 7)로 본다. 무기를 붙여 찍는 것은 8-4(무기 메시 · 소켓)와 함께 |
| APNG 의 채팅 표시 · 영상 (개정 12) | APNG(4초 · 15 fps 6.6 ~ 8.0 MB)가 채팅 미리보기에서 움직이는지는 사용자 눈 확인 — 움직이지 않으면 첫 프레임 정지 그림이고 시트 · 비교 시트가 근거다. MP4 는 Blender 4.4 에 들어 있는 FFmpeg(`avcodec-60.dll`)로 설치 없이 만들 수 있다 — 필요하면 후속(Blender 단계 하나 추가) |
| Phase 8-3 결과의 사람 판정 · 기준값 (개정 13) | 수치(정점 · 꼬리 · 발 간격 · 미끄러짐)와 전후 캡처 — **사용자 판정 통과(2026-10-27, 후속 수정 뒤 캡처)**. 남은 보정 후보: 가속 상한(검은 ×2.0 에서 운영 최저에 못 미침) · 복귀 배율 1.5 · 발 간격 상한 3.0 · 머리 · 꼬리 남김 0.2 · 0.3초 · antialias 1.0(보강 — 정점 −8 ~ −10%, 사용자 확정 2026-10-27). 매끈한 시각 사상 op(C++ `time_warp`)는 보강에서 들어왔다(§14 '8-3 후속'). 공중 발 경로의 거리 꺾임(검 선택 다리 떨림 1.89 — 무릎을 원래대로 펴면 커진다)은 **8-4 범위 ③**(사용자 결정 2026-10-27) |
| 다리 보정의 대상 모델 (개정 13) | 리타기터 `match_existing` 구성(Pelvis Motion 바닥 제약 0 · 회전 알파 1 · FK 회전 복사 · per_bone 정렬)을 가정한다 — 이 구성에서 예측 = 실측(디딘 발 좌우 비 ±0.01 · 미끄러짐 ±1 cm/s). 다른 RTG(기존 RTG 재사용 · `ops: default` · 바닥 제약)는 미측정 — `fix.target` 실측으로 확인. 보정은 그 대상 메시 치수 기준이라 다른 메시로 리타깃하면 다시 보정. 발끝 접지(뒤꿈치 듦)는 고정하지 않는다(발목만) · 손 · 몸 관통과 함께 푸는 대상 쪽 풀이는 8-4 |
| 몸 모델 근사 · 머리 지도 (개정 14) | 반경 지도(축 둘레 칸마다 최대 반경)는 칸 안을 꽉 찬 몸으로 본다 — 뿔 · 큰 머리카락 · 옷자락처럼 축에서 튀어나온 부분이 있는 칸은 깊이를 키운다. 정수리 규칙 · 머리 지도 t ≤ 1.0 으로 뿔 끝 · 줄기는 뺐지만 뿔 뿌리(정수리 아래 t 0.96 ~ 1.0)는 남았다. 옷 · 머리카락 물리 없음. 8-4b 풀이는 이 모델을 쓰고 최종 판정은 C++ 실측 + 사람(§16-9). 8-4b 손 지도는 쥔 주먹을 축 둘레 별 모양으로 보고 오목한 손바닥 면은 바깥 면으로 메운다(맞닿음 contact 까지는 정상으로 둔다) |
| 낫 왼손 파지 선분 (개정 14) | E0 제안(운영 낫 4개 51 표본 — 손바닥 뼈 선 점 기준, 자루 중심선 (−0.85, 0, −70.32) → (−1.05, 0, −36.74))은 근거이고, 8-4c 착수 때 파지 잔차의 기준점과 함께 확정한다(요청 `weapon.grips[].segment` — 운영 애셋 무변경, 결정 C). 운영 낫은 대부분 한 손(왼손 파지 5 ~ 32%) |
| 위팔 → 가슴 기준 (개정 14) | 운영 애니도 위팔 → 가슴 접촉 42 ~ 100% · 관통 최대 98.1% — **8-4b 확정: 위팔 쌍은 관통 목표 밖 · '점마다 원래보다 안 깊어짐'만**(총괄 정정). 남은 것: 그 쌍(`l\|upper_arm\|chest`)의 모델 예측이 C++ 실측과 9 Job 에서 어긋남 — 겨드랑이 몸통 정점의 팔 본 가중(C++ 지도는 팔과 함께 움직임) 추정, 확인 · 모델 보강은 후속 |
| 지시 목표 경로 (개정 14 — 8-4b) | 표준 지시 T1 ~ T4 에서 구간 ± ease 밖 변화 1.8 ~ 23 cm · 떨림 5 ~ 12 · T3 keep 10.8 cm — 구간 안 관통 몫 무매끈화 · 받침 · 스플라인 반응 · 위반 프레임 사슬의 다른 국소 해(§14 '8-4b'). 목표 없는 풀이를 먼저 하고 구간 밖은 그 해를 잇는 안 등 — 사용자 결정 뒤 |
| 맞닿음 허용 뒤 짧은 관통 (개정 14 — 8-4b 후속) | `allow_contact`(몸통 · 넓적다리)는 관통 판정까지 여유가 1 cm 라 빠른 휘두름에서 1 ~ 2 프레임이 남는다(오프라인 낫 정정 머리 1.7% · 2.37 · 가슴 0.8% · 2.98, 낫 Attack2 넓적다리 2.1% · 3.23 — 처음 판은 0 · 1.0% · 2.22). 재검사 패스를 늘리는 것(EXTRA 3 → 8)은 손목 이동을 다시 키워(걷기 p50 6.5 → 7.5 · p95 14.4 → 16.0) 재검사 증분 가중 1 로 대신했다. 합성 몸에서 몸통 맞닿음 자리가 넓적다리 축과 겹치는 우연한 자리는 넓적다리 바깥 방향이 몸 안쪽을 가리켜 갇힌다(정중앙 관통 한계와 같은 꼴 — 4.7 cm). 실제 판정은 통합 C++ 실측 · 캡처(§14 '8-4b 후속'). **후속 2차(위팔 keep 층) 뒤:** 낫 정정 머리 · T3 머리는 0 이 됐고, 남은 것은 걷기 오른손 → 넓적다리 1.7% · 4.58 cm(2 프레임 — 재검사 미수렴) · 낫 정정 손 → 가슴 1.7% · 3.09 · 낫 Attack2 넓적다리 2.1% · 2.74 · T4 머리 2.5% · 10.63(구간 밖 — 지시 목표 경로) · 위팔 기록 쌍 '나빠지지 않음' 미달(s25 · s26 · s27 · 검 선택) |
| 파지 keep · 보조 손목 (개정 14 — 8-4b) | keep 최대 1 ~ 2.7 cm(기준 1 cm) · 파지 프레임 두 손목을 열어 손목 굽힘 최대 +11 ~ +13°(기준 +5°) · 낫 Attack2 파지 프레임 손끼리 관통이 안 풀림(7.3 → 12.5%) — 관통 · keep · 손목의 우선순위 · 손목 상한은 8-4c(무기 파지 — 손잡이 선분 · 손 축)와 함께 다시 정한다 |
| `head_near` 와 메시 머리 지표 (개정 14) | 메시 기준 `head_neck` 쌍은 옵트인(결정 E) — 8-1 선별 점수는 `head_near`(뼈 한 점) 그대로. 둘은 같은 방향(낫 정정 상관 0.952)이지만 메시 쪽이 깊이를 준다 — 선별 반영 여부는 8-4b 이후 사용자 판단(8-4b 는 선별을 바꾸지 않았다) |
| 몸통 대비 팔 벌림 (개정 8) | 위팔은 월드로 소스에 맞추고 몸통은 대상 중립(⓪)이라 몸통 기준 팔 벌림이 소스와 ±2.6°(CMU) 다르다 — 후속 후보: 팔 리타깃 포즈 정렬을 몸통 기준틀 상대로. 미수정 |
