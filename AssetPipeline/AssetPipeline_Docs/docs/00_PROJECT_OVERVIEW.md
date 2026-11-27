# 프로젝트 정의 및 요구사항

Architecture v0.1 · 2026-11-26 · 목표 엔진 UE5.7.4 (소스 빌드). 프로젝트명 AssetPipeline은 임시 명칭이다. AstralBreak(4인 협동 PvE 액션 레이드)를 첫 적용 대상으로 하되 독립 저장소로 개발한다.

목표: Claude Code가 전문 AI 및 Blender를 활용하여 게임용 Mesh, Rig, Animation을 제작하고 검증하며 실패 시 복구하는 재현 가능한 제작 파이프라인. 런타임 AI가 아니라 Editor/오프라인 제작 도구다.

| ID | 요구사항 | 완료 조건 |
|---|---|---|
| FR-01 | Mesh 확보 | Tripo GLB 및 기존 FBX 입력, 원본 해시/출처 기록 |
| FR-02 | Mesh 처리 | 단위, 축, 재질, topology 검사 및 정리 |
| FR-03 | 자동 리깅 | Skeleton, skinning 생성 및 pose test |
| FR-04 | Blender 직접 제어 | Claude가 scene 조회, bone/weight/keyframe 수정 및 렌더링 |
| FR-05 | 레퍼런스 영상 생성 | 동작 명세에서 추적 가능한 영상 생성 |
| FR-06 | Video-to-Motion | 실제/AI 영상에서 3D 모션 추출 및 의미 분석 |
| FR-07 | Text-to-Motion | 자연어 기반 모션 생성 |
| FR-08 | Animation-to-Animation 및 Procedural | 기존 모션 수정, 직접 keyframe/IK 제작 |
| FR-09 | Retargeting | 다른 skeleton에 모션 적용 및 검증 |
| FR-10 | QA | 정량 검사, 렌더링 비교, 수정 및 재검증 |
| FR-11 | 복구 | Checkpoint, Rollback, Retry, Fallback, 재개 |
| FR-12 | UE5 연동 | Skeletal Mesh 및 Animation Sequence 임포트 |
| FR-13 | Gameplay 연동 | Montage, Notify, Motion Warping, Combat Metadata |
| FR-14 | Human review | 자동 해결 불가/중요 품질 판단 시 승인 요청 |
| FR-15 | Provenance | 입력, 도구 버전, 설정, 라이선스, 생성 이력 추적 |

원칙: Agentic, Modular, Recoverable, Self-validating, Reproducible, Human-in-the-loop, Engine-aware, Extensible. 정형 작업은 결정적 스크립트로 처리하되 AI 모델 결과의 완전한 결정성은 보장하지 않는다. 원본 보호와 비용 제한을 코드로 강제한다.

범위: 최초 PoC는 휴머노이드 1개와 공격 1개. 복잡한 크리처, 고품질 자동 retopology, 대규모 분산 실행은 후속 단계. 모든 도구가 검증된 통합 제품이라는 의미는 아니다.
