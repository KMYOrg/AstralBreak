# CLAUDE.md — Project instructions

이 저장소는 Architecture v0.1 설계 단계의 AssetPipeline이다. 최초 적용 대상 AstralBreak(UE5.7.4). 목적은 게임 에셋 제작 자동화이며 런타임 AI가 아니다.

## 작업 규칙

- 첫 작업은 설계 및 출처 검토다.
- `docs/00_PROJECT_OVERVIEW.md`, `docs/01_SYSTEM_ARCHITECTURE.md`, `docs/12_IMPLEMENTATION_ROADMAP.md`, `docs/13_REFERENCES.md`, `docs/14_RISKS_AND_DECISIONS.md`를 먼저 읽고 나머지는 작업 범위에 따라 읽는다. 초기 전체 검토 시 docs 전체를 확인한다. 통합본은 중복 읽지 않는다.
- 기존 사례의 기능을 추정하지 않는다. URL, commit, license, code path, 실행 여부를 검증하고 재사용/직접 구현을 분리한다.
- Claude는 계획 및 판단, Python Core는 실행 및 복구. 원본 immutable, 작업별 workspace, checkpoint, 제한된 retries, 비용 제한, 검증 gate 및 명시적 publish를 유지한다.
- Blender MCP 직접 제어와 headless CLI를 모두 고려한다. 임의 코드 실행은 최소 권한 및 승인/격리. 동일 파일 동시 쓰기 금지.
- AI 영상 생성, 수치적 motion recovery, 의미적 Vision 분석, 기존 모션 수정, procedural 경로를 별도로 유지하고 공통 motion format으로 통합한다.
- 실패한 결과를 정상 결과로 보고하지 않는다. 자동 검사/시각 판단/실제 UE playback을 구분하고 불확실성을 보고한다.
- 실제 AstralBreak 인터페이스 확인 전 GAS/Notify class를 가정하지 않는다. 게임 밸런스/서버 권한 변경 금지.
- 먼저 humanoid 한 개 + 공격 한 개의 PoC. 불필요한 분산 인프라 및 multi-agent 구축 지연.
- 주요 설계 변경은 ADR로 대안, 이유, 영향, 근거를 기록하고 사용자 승인을 받는다.
- 비밀 키/모델 weight/대용량 원본을 Git에 넣지 않는다. 라이선스 확인 전 결과물 배포 금지.
- 모든 명령/스키마/임계값은 아직 구현 및 검증 전 제안이다. 테스트 실제 결과와 가정 분리.
