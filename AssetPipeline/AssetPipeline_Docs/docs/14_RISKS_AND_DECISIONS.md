# 위험 / 미확정 사항 / 설계 결정

| 위험 | 대응 |
|---|---|
| AI mesh topology/장식 | 생성 조건 개선, 전처리, 분리, pose QA |
| 자동 rig 편차 | test poses, fallback, 직접 보정 |
| 영상 왜곡/가림/빠른 동작 | 영상 QA, 고정 camera, 재생성, key pose 보정 |
| 무기 3D 복원 불확실 | object tracking + IK + 사용자 검토 |
| retarget twist/root 오차 | rest pose, mapping, golden fixture |
| LLM 판단 및 임의 코드 | deterministic checks, sandbox, approval |
| 반복 비용/과금 | budget, idempotency, cache, retry limits |
| GPU 부족/환경 충돌 | 별도 worker/env, cloud fallback 검토 |
| 라이선스 | code/weights/SMPL/output/기존 애니메이션 권리 별도 검토 |
| UE 버전 차이 | 5.7.4 실제 소스 및 plugin/API 검증 |
| repo 미확인 | URL/commit/기능 검증, 불가 시 대체 |
| 과도한 설계 | PoC/vertical slice 우선, 분산 시스템 및 다중 agents 지연 |

## 초기 ADR 후보

- ADR-01: 독립 repository + AstralBreak Editor plugin 분리 (제안).
- ADR-02: Claude control plane / Python execution plane 분리 (권장).
- ADR-03: MCP interactive + headless CLI hybrid (권장).
- ADR-04: immutable artifacts, attempt-based candidates, SQLite state (제안).
- ADR-05: provider adapter + canonical motion schema (제안).
- ADR-06: hard gates + soft metrics + human review (권장).
- ADR-07: UE staging 및 명시적 publish (권장).
- ADR-08: 첫 PoC humanoid 한 개, 공격 한 개 (권장).

미확정: 실제 Blender 버전, Python 환경, GPU/VRAM, Tripo API access, 로컬/클라우드 비용, model license, skeleton profile, motion provider, QA threshold, 실제 AstralBreak interfaces, C++ Editor module 필요 범위, repo 재사용 범위. 사용자가 최종 확정한 사항으로 취급하지 않는다.

설계 검토 시 각 ADR에 alternatives, tradeoff, evidence, status(Proposed/Accepted/Rejected/Superseded)를 작성. 사용자 승인 없이 주요 architecture 변경 또는 대규모 implementation 금지. 실패 시 사용자에게 원인, 시도, 비용, 보존 artifact, 다음 선택지를 보고한다.
