# UI 자동 생성 파이프라인 — 원 요구사항 (사용자 원문)

> 2026-11-14 사용자가 대화에 붙여넣은 계획서 원문이다. 고치지 않고 그대로 둔다 — 설계와 달라진 점과 그 근거는 [ui-autogen-pipeline.md](ui-autogen-pipeline.md) §1 에 있다.
> 원문의 빈칸(`<…>`)이 정해진 값은 설계 문서 §0 '빈칸 채움' 표를 본다.

---

# 작업: 컨셉아트·텍스트·참조 이미지 → UE5 WBP 프로토타입 무인 자동화 파이프라인 설계·구현

## 목표
이미지나 텍스트로 UI를 요청하면 사람 개입 없이
UI 에셋 생성 → 후처리 → 임포트·설정 → WBP 레이아웃 구성 → 검증(실패 시 재시도)까지 수행하고,
WBP 프로토타입과 리포트를 남기는 파이프라인을 만든다.
이미 만든 프로토타입을 이미지나 텍스트 지시로 수정하는 기능도 포함한다.

## 환경
- UE 5.7.4 소스 빌드 C++ 프로젝트: <프로젝트 경로>
- 기존 자산: AnimBP 자동화용 UE C++ 에디터 플러그인 + MCP 서버 (<경로>)
  - 통신 구조와 안전장치 원칙을 참고할 것
  - 이 플러그인을 확장할지, 별도 플러그인으로 만들지는 설계안에서 근거와 함께 제안
- 이미지 생성 1: ChatGPT Plus 계정으로 로그인된 Codex CLI (`codex exec` + `$imagegen`, 참조 이미지는 `-i`)
- 이미지 생성 2: 로컬 ComfyUI (Phase 5부터), GPU: <모델 / VRAM>
- 폰트: <폰트 파일 경로>, 기준 해상도: 1920x1080

## 작업 모드

### 입력 정규화 (공통 원칙)
모든 생성 모드는 먼저 "기준 이미지(reference.png) + 요구사항(brief.json)"으로 정규화한다.
그 뒤 analyze 이후 단계는 모드와 상관없이 같은 파이프라인을 탄다.
기준 이미지 없이 진행하는 경로는 만들지 않는다.

- brief.json: 화면 종류, 필수 요소, 동적 데이터, 스타일 키워드, 참조 이미지별 역할

### 생성 모드
1. concept: 컨셉아트 1장을 그대로 reference.png로 사용
2. text: 텍스트 명령 (예: "다크 판타지 스타일 인벤토리, 4x6 슬롯, 우측 장비창")
   - brief.json 작성
   - Codex로 목업 후보 K장 생성
   - 규칙 검사(필수 요소 포함 여부, 실제 구현 가능한 레이아웃인지) + LLM 판정으로 1장 자동 선택
   - 선택된 목업을 reference.png로 사용
3. multi_ref: inputs.yaml (이미지 여러 장 + 선택적 텍스트). "스타일 참조 이미지 + 텍스트" 요청도 이 모드로 처리
   - 이미지마다 역할 부여: layout / style / component(target 위젯 지정) / mood
   - 역할이 지정되지 않은 이미지는 analyze 단계가 자동 분류하고, brief.json에 근거와 함께 기록
   - 지시가 충돌할 때 우선순위: 텍스트 지시 > layout > component > style > mood
   - 역할별로 정리한 내용을 바탕으로 목업 생성 (참조 이미지 여러 장 전달) → reference.png

```yaml
# inputs.yaml 예시
mode: multi_ref
text: "모바일 RPG 상점 화면"
images:
  - { path: ref/layout_shop.png,    role: layout }
  - { path: ref/style_darkgold.png, role: style }
  - { path: ref/btn_buy.png,        role: component, target: Btn_Buy }
```

### 수정 모드
입력: 기존 run_id + 수정 지시 (주석이 그려진 스크린샷 / 특정 부분의 새 참조 이미지 / 새 전체 목업 / 텍스트)
1. 현재 WBP 상태를 spec으로 역추출한다 (WBP → spec).
   마지막 파이프라인 출력 이후 사람이 직접 수정했다면 그 상태를 기준으로 삼고, 절대 덮어쓰지 않는다.
2. 현재 렌더 결과와 수정 지시를 비교해 변경 목록(spec patch)을 만든다.
3. 변경된 위젯·에셋만 다시 생성하고 다시 구성한다. 전체 재빌드 금지.
4. 역추출이 지원하지 않는 위젯 타입이나 속성은 목록으로 표시하고, patch가 건드리지 못하게 한다.
5. 결과는 새 run_id로 저장하고 parent_run_id를 기록한다. 언제든 이전 버전으로 되돌릴 수 있어야 한다.

### 진입점
run_pipeline --concept <img>
             | --text "<명령>"
             | --inputs inputs.yaml
             | --edit <run_id> [--image <img>] [--text "<지시>"]

## 확정된 결정 (바꾸려면 근거 제시)
1. 오케스트레이션: 외부 스크립트가 단계마다 `claude -p`를 호출한다.
   단계 순서·재시도·분기는 코드가 결정하고, LLM은 각 단계 안의 작업만 수행한다.
2. 단계: (normalize) → analyze → generate → refine → build → verify
   - verify 실패 시 report의 fixes를 가지고 build(필요하면 generate)로 돌아간다. 재시도는 최대 N회.
3. 단계 사이의 데이터는 파일로 주고받는다:
   work/<run_id>/reference.png, brief.json, spec.json, manifest.json, render.png, report.json
4. 에셋마다 출처를 셋 중 하나로 분류한다:
   - procedural: Claude Code가 SVG / UI 머티리얼 / RoundedBox 브러시로 직접 생성
   - codex
   - comfy
5. WBP 로직은 C++ UUserWidget + meta=(BindWidget)로 분리한다. MCP는 위젯 트리와 스타일만 담당한다.
6. 목업이나 컨셉아트 속 글자는 레이아웃 참고용으로만 쓴다. 실제 텍스트는 brief 기준으로 TextBlock에 넣고, 이미지에 굽지 않는다.

## 이미지 생성 백엔드
- 이미지 생성은 MCP 도구 하나(generate_ui_asset) 뒤에 백엔드를 숨긴다.
  요소 종류(kind)별 라우팅은 설정 파일로 관리한다: primary / fallback / anchor / retry_backend
  - Codex: 기준(앵커) 에셋, 목업 생성, 고품질 요소
  - ComfyUI: 앵커를 참조한 변형 대량 생산, 검증 실패 후 재생성
  - Codex 플랜 한도 초과를 감지하면 자동으로 폴백
- 모든 생성·검증 결과를 JSONL로 기록한다:
  run_id, asset_id, kind, backend, 성공 여부, 소요 시간, 재시도 횟수, 검증 결과, 앵커 대비 스타일 유사도
- ComfyUI 실행 기록에는 워크플로 JSON, 모델·LoRA 해시, 시드를 함께 저장한다 (재현성)

## 검증
- 규칙 검사:
  - 컴파일 에러, BindWidget 누락, 텍스처 UI 설정
  - 화면 밖으로 나간 위젯, 의도치 않은 겹침
  - brief.json 필수 요소 누락
- 수치 비교:
  - spec의 bbox vs 실제 배치 geometry IoU
  - 주요 색상 ΔE
  - 스타일 임베딩 유사도: 앵커 에셋 대비, multi_ref 모드에서는 style 역할 이미지 대비
  - component 역할 이미지 vs 해당 target 위젯 개별 비교
- 수정 모드 회귀 검사: 변경하지 않은 위젯의 geometry·스타일이 그대로인지 확인
- LLM 시각 판정: 독립 컨텍스트의 verifier 서브에이전트가 reference와 render를 비교해 구체적인 fixes를 출력
- 합격(pass) 판정은 규칙·수치 기준으로만 한다. LLM 판정은 fixes를 만드는 데만 쓴다.

## UE 측 필요 기능 (도구 단위와 이름은 설계에서 결정)
- UI 텍스처 임포트 + 설정 적용 (UserInterface2D, TEXTUREGROUP_UI, NoMipmaps, NeverStream), 9-slice Margin
- WBP 생성, spec 기반 위젯 트리 일괄 구성, 슬롯·스타일 설정, UI 머티리얼 인스턴스
- spec patch를 기존 WBP에 부분 적용
- WBP → spec 역추출
- 컴파일·저장, 위젯 geometry 조회
- 위젯을 PNG로 렌더링 (검증용)
- 에디터·MCP 연결 상태 확인

## 안전장치 (필수)
- 결과물은 /Game/_AutoGen/<run_id>/ 아래에만 생성한다. 기존 에셋 덮어쓰기·삭제 금지.
- 실행 전에 전체를 먼저 검증하고, 실패하면 해당 run 전체를 롤백한다.
- 조회 이후 대상이 바뀐 것이 감지되면 수정을 거부한다.
- 권한은 허용 목록(allowlist)으로만 준다. --dangerously-skip-permissions 사용 금지.
- 단계마다 --max-turns, --max-budget-usd, 재시도 상한을 둔다.
- Stop 훅을 쓸 경우 stop_hook_active를 확인해 무한 루프를 막고, 차단은 exit 2로 한다.
- ChatGPT 내부 엔드포인트를 직접 호출하지 않는다. 이미지 생성은 공식 codex CLI로만 한다.
- 토큰·시크릿을 로그나 리포트에 남기지 않는다.

## 구현 규칙
- 엔진 API는 기억에 의존하지 말고 5.7.4 엔진 소스에서 시그니처를 확인한 뒤 사용한다.
  - 확인 포인트: 코드로 위젯을 추가할 때 WidgetVariableNameToGuidMap 갱신 경로, FWidgetRenderer 사용법
- 반복해서 부딪히는 엔진 제약은 Claude Code Skill로 정리한다.
- C++은 Allman 스타일로 작성한다.

## 진행 단계 (순서 조정이 필요하면 근거와 함께 제안)
- Phase 1: concept 모드, procedural + Codex만으로 처음부터 끝까지 1회 성공 (샘플: <컨셉아트 경로>)
- Phase 2: 지표 기록 + 리포트 집계 스크립트
- Phase 3: text / multi_ref 생성 모드 (목업 생성·선택 포함)
- Phase 4: 수정 모드 (WBP → spec 역추출 도구부터)
- Phase 5: ComfyUI 연결. 요소 종류 하나(아이콘)만 Codex와 A/B 비교
- Phase 6: 지표를 기준으로 라우팅을 조정하는 규칙

## 첫 응답에서 할 일 (구현 전)
1. 현재 프로젝트와 기존 플러그인 구조 조사
2. 설계안 제출:
   - 아키텍처, 디렉터리 구조
   - brief.json / spec.json / spec patch / inputs.yaml 스키마 초안
   - MCP 도구 목록, 단계별 입출력
   - 검증 지표별 임계값 초안
   - .claude/ 구성 (skills / agents / hooks / settings)
3. 불확실한 가정과 질문 목록

내 승인을 받은 뒤 Phase 1 구현을 시작한다.
각 Phase가 끝날 때마다 실제로 실행한 결과로 검증하고 보고한다.
