# UI 자동 생성 파이프라인 설계 (컨셉아트 · 텍스트 · 참조 이미지 → WBP)

작성일: 2026-11-14 · 대상: UE 5.7.4 · 기준 커밋: `88a4813` · 원 요구사항: [ui-autogen-requirements.md](ui-autogen-requirements.md) · 관련: [m4-ult-chain.md](m4-ult-chain.md) §5(HUD)
상태: **Phase 0 완료 · 커밋 `6700484`(2026-11-14)** — 플러그인 분리(EditorMcpCore · AnimGraphMcp · StateTreeMcp · WidgetMcp 뼈대) · 빌드 2구성 · 회귀 통과, 가정 A1 ~ A7 결과는 §12-1(A4 · A5 는 사용자 CLI 로그인 뒤 `claude` 2.1.325 로 실측). **Phase 1a 완료(11-15)** — 하위 단계 1a-1 ~ 1a-5 끝, 끝 조건 4개 충족(§11 'Phase 1a 결과 요약' · '1b 로 넘길 것'), 빌드 2구성 · 에디터 1회 · pytest 142 통과, 렌더 색 사람 눈 확인 통과(§12-1 A6-색) — 커밋 `c890a47`. **Phase 1b 완료(11-15, 미커밋)** — 하위 단계 1b-1 ~ 1b-7(§11), 끝 조건 충족: 컨셉아트 → analyze → codex 에셋 → build → verify(hybrid LLM fix 1회) → 저장이 **무인 1회 통과**(`R20261115_024358`, 3분 56초, 10/10) + 리포트. 빌드 2구성 · 에디터 시험(`AstralBreak.` 55/55 — 1차 53/55 일시 실패 · `EditorMcpCore.` 2/2 · `WidgetMcp.` 6/6) · pytest 198 통과. 렌더 사람 눈 확인 결과(11-15): **레이아웃은 맞고 외형(게이지 · 프레임 모양 · 글꼴)은 다름** — 다음은 1b 후속 '외형 재현 A · B · C · D'(사용자 결정 — §11 방향 메모). **1b 후속 A 완료(11-15, 미커밋)** — 컨셉에 보이는 프레임 · 패널을 codex **편집**으로 따오기(spec asset `source_mode: extract`) · 공용 ΔE00(`core/color.py`) · 충실도 기록(`gen/fidelity.py`) · 9-slice 추정 v3(축별) · 안쪽 칠하기 · **크기 고정 위젯은 image 로 그리기**(사용자 눈 확인 지적 — box 9-slice 가 2배 텍스처의 모서리를 키우고 가운데를 누름) · WBP 렌더 ↔ 컨셉 이식 지표, 채록 2장 + 실제 run 3회(전부 10/10 — run 3 은 LLM fix 1회 뒤) · pytest 227(§11 'A 에서 확인 · 정한 것' · 'A 보강'). **1b 후속 B 완료(11-15, 미커밋)** — 게이지 채움 · 배경을 컨셉에서 결정적으로 뽑기(procedural `gradient_bar`) · 꺼진 flag 초기 접힘 · flag 위젯 상자 패널 금지 · 따온 텍스처를 위젯 상자 그대로 되자르기(A 결함 수정), C++ 변경 없음, 실제 run 2회(둘 다 LLM fix 1회 뒤 10/10) · 렌더 장식선 F1 0.98 · 0.90 · 0.96 · 게이지 채움 줄 단위 ΔE00 12.1 → 1.8 · pytest 235(§11 'B 에서 확인 · 정한 것'). B ③ 은 D 로. **1b 후속 D 완료(11-15, 미커밋)** — 제목 · 숫자용 Noto Serif KR(OTF) 임포트 · 역할별 폰트(`font.role` → family) · 글자 효과 어휘 outline · shadow · letter_spacing · gradient(WidgetMcp C++ — 그라데이션은 run 폴더 UI 머티리얼 + MIC) · 글자색 · 그라데이션을 컨셉에서 결정적으로 뽑기, 실제 run 1회(LLM fix 1회 뒤 10/10) · 금색 글자 획 대표색 ΔE00 15.9 · 18.4 → 0.9 · 1.2 · pytest 245 · `WidgetMcp.` 6/6(§11 'D 에서 확인 · 정한 것'). **1b 후속 C 완료(11-15, 미커밋)** — 게이트 통과 뒤 외형 검토 라운드(LLM style_verifier → style_fix, 허용 op 는 외형만 · 게이트가 깨지면 run 패키지를 전부 버리고 마지막 통과 spec 으로 다시 build) · 영역 · 글자 · 게이지 전부의 컨셉 ↔ 렌더 비교 기록, 끝 run `R20261115_160430` 무인 통과(라운드 1회 받음 — 글자 높이 비 오차 0.094 → 0.046 · 체인 패널 장식선 F1 0.899 → 0.978) · pytest 253(§11 'C 에서 확인 · 정한 것'). **1b 후속 F 완료(11-15, 미커밋 · 사람 눈: run 4 가 낫고 게이지 · 빛 지적 없음, 남은 차이 = 배너 위아래 빛 · 체인 패널 모서리 · 글자 위치 약간 — A 따오기 · analyze 몫, 다음 후속 G)** — 사람 눈 판정의 외형 차이 셋: 게이지 채움을 컨셉 모양 그대로 따오기(procedural `concept_fill` — 왼쪽 '<' 끝 · 밝은 테두리 · 트랙 띠 빛) + 진행 끝 테두리 · 번짐(WidgetMcp ProgressBar `bar_fill_style: scale` + 채움 9-slice) · 글자 빛(엔진 SDF 글꼴 + 외곽선 층 빛 머티리얼 `font.glow` — Config 2줄 · 새 폰트 `F_NotoSerifKR_SDF`, 컨셉에서 결정적으로 — '4.2' 만) · 배너 크기(analyze 글자 높이 비 정정 + 외형 라운드에서 크기 바뀐 글자만 가운데 중심으로 커지게), 끝 run 5번 모두 무인 통과(외형 라운드 받음 1 · 버림 4 — 원인마다 고침, 마지막은 analyze 배치 한계로 남김) · 게이지 채움 줄 단위 ΔE00 6.52 → 0.51 · 실루엣 IoU 0.891 → 0.937 · 회귀 빌드 2구성 · `AstralBreak.` 55/55 · `EditorMcpCore.` 2/2 · `WidgetMcp.` 6/6 · pytest 264(§11 'F 에서 확인 · 정한 것'). 설계 승인(11-14) · §12-2 질문 1 · 2 · 4 · 5 · 6 · 8 결정. 값은 전부 잠정이다.

표기: **[소스]** = 5.7.4 엔진 · 프로젝트 소스에서 확인한 것(파일:줄) · **[실측]** = 이 PC 에서 명령으로 확인한 것 · **[P0]** = Phase 0 스파이크에서 확인할 것 · **[P0 결과]** = Phase 0 에서 확인한 결과(11-14) · **[바이너리]** = 설치된 실행 파일 안의 문자열로 확인(동작은 미실측).

---

## 0. 요약

**무엇을 만드나.** UI 컨셉아트(또는 텍스트 · 참조 이미지 묶음)를 주면, 사람 개입 없이 에셋 생성 → 후처리 → 임포트 → C++ 바인딩 클래스 생성 → WBP 구성 → 렌더 검증(실패 시 재시도)까지 돌고, WBP 프로토타입과 리포트를 남긴다. 만든 화면을 이미지 · 텍스트로 고치는 수정 모드도 있다. UI 종류(메인 HUD · 장비창 · 옵션 등)는 고르는 대상이 아니라 입력(`screen_type`)이다.

**왜 지금.** M4 단위 C(전투 HUD)부터 본격적으로 UI 에셋이 필요하다. **첫 실전 대상은 M4 전투 HUD** 이고, 파이프라인 Phase 1 의 산출물이 곧 M4 단위 C 의 화면 부분이다.

**핵심 결정 (원문과 달라지는 것은 §1 에 근거와 함께)**

1. 플러그인은 **공용 코어 `EditorMcpCore` + 기능별 플러그인**(`AnimGraphMcp` · `WidgetMcp` · 나중에 `StateTreeMcp`)으로 나눈다.
2. 오케스트레이터(Python)가 순서 · 재시도 · 분기를 정하고, **LLM 은 판단이 필요한 곳에만** 쓴다(normalize · analyze · verifier 시각 판정 · fix · 수정 지시 해석). 생성 실행 · 후처리 · 코드 생성 · 빌드 · 규칙/수치 검증은 결정적 코드다.
3. build 는 **spec ↔ WBP 조정기**다 — 첫 빌드도 '빈 WBP 에서의 차이 적용'. 그래서 WBP → spec 역추출이 Phase 1 부터 있다(왕복 검증 도구).
4. C++ 위젯 클래스는 **템플릿 코드 생성**(LLM 아님)으로 만든다 — 생성 베이스(매번 덮어씀) + 스텁(한 번만, 사람 소유) 두 겹, **기능 폴더 + `AutoGen/` 하위**.
5. 결과는 `/Game/_AutoGen/<run_id>/`(git 무시)에만 만들고, **verify 를 통과할 때까지 저장하지 않는다** — 롤백 = 저장 안 한 패키지 폐기. 사람이 고른 것만 `/Game/UI/...` 로 승격해 커밋한다.
6. 합격은 규칙 · 수치로만. 스타일 유사도 · ΔE 는 **Phase 2 보정 전까지 기록만** 한다.
7. Codex 한도에 걸리면 **멈추고 나중에 재개**한다(procedural 이 원래 잘하는 종류만 대체).

**빈칸 채움 (원문 `<…>`)**

| 원문 | 값 | 근거 |
| :--- | :--- | :--- |
| 프로젝트 경로 | `D:/UE5Projects/AstralBreak` | |
| 기존 플러그인 경로 | `Plugins/AnimGraphMcp` + `Tools/mcp/` | |
| GPU / VRAM | RTX 3080 Ti · 12 GB (RAM 64 GB) | [실측] `nvidia-smi` |
| 폰트 | Pretendard 또는 Noto Sans KR (OFL — 게임에 넣어 배포 가능) · 저장소에 폰트 없음 | [실측] · §12 질문 |
| 샘플 컨셉아트 | M4 전투 HUD 컨셉아트 — 사용자 준비 | §12 질문 |

---

## 1. 원 요구사항에서 달라지는 것

| # | 원문 | 이 설계 | 근거 |
| ---: | :--- | :--- | :--- |
| 1 | 플러그인 확장 또는 별도 — 제안 | 공용 코어 + 기능별 플러그인 (§3) | 사용자: "기능별로 나눈 느낌이 나야 한다". 지금 디스패처가 이미 기능별 등록 함수 20개로 나뉘어 있어 옮기기 쉽다 [소스] `AnimGraphMcpEditorModule.cpp:101-123`. 별도 브리지(포트 · 토큰 두 벌)는 안전장치가 따로 놀게 된다 |
| 2 | 단계마다 `claude -p` | LLM 단계(정규화 · 분석 · 시각 판정 · 수정안) + 코드 단계 (§2) | 생성 실행 · 후처리 · 빌드 · 규칙 검사는 판단이 아니라 계산이다. 코드로 두면 재시도가 재현되고, 무인 LLM 이 에디터 쓰기 도구를 쥐지 않으며, 사용량이 준다. '순서는 코드가 정한다'(결정 1)를 더 엄격하게 지키는 쪽이다 |
| 3 | 단계: normalize → analyze → generate → refine → build → verify | **codegen** 을 analyze 와 generate 사이에, 재시도용 **fix** 를 verify 뒤에 둔다 | 결정 5(C++ + BindWidget)를 무인으로 지키려면 바인딩 클래스 생성 · 빌드가 단계로 있어야 한다 |
| 4 | 역할 미지정 이미지는 analyze 가 분류 | **normalize** 가 분류 | multi_ref 는 역할별 정리로 목업(= reference.png)을 만든다 — 분류가 normalize 안에서 끝나야 한다. 원문 안의 순서 모순 |
| 5 | spec → WBP 구성, 부분 적용은 Phase 4 | build = 조정기, 역추출은 Phase 1 | 재시도(fix → patch → build)와 수정 모드가 같은 코드 경로를 쓴다. 역추출은 Phase 1 의 왕복 검증(spec → WBP → spec 일치)으로 쓴다 |
| 6 | 실패하면 run 전체 롤백 | 사전 검증 실패 = 배치 무변경. verify 최종 실패 = 디스크 기록은 남기고 uasset 은 저장 안 함 | 실패 원인을 볼 수 있어야 한다. build 가 결정적이라 uasset 은 spec 에서 몇 초 만에 다시 만든다(`--keep-failed` 로 저장도 가능) |
| 7 | 텍스처 `UserInterface2D` | 같은 값 `TC_EditorIcon` — 5.7.4 에서 표시 이름이 **`Uncompressed (RGBA8)`** 로 바뀌었고 엔진이 BC7 을 권한다 | [소스] `TextureDefines.h:400`. 기본값은 원문대로 두고 종류별로 BC7 을 고를 수 있게 한다(§12 질문) |
| 8 | 9-slice Margin 을 텍스처 설정으로 | 브러시(`FSlateBrush` DrawAs Box/Border) 속성 | refine 이 margin 을 추정해 manifest 에 적고 spec 의 브러시가 쓴다 |
| 9 | verifier 서브에이전트 | 별도 `claude -p` 호출 | 오케스트레이터가 따로 부르면 그 자체로 독립 컨텍스트다 |
| 10 | 단계 출력 검증은 Stop 훅 | `--json-schema` + `--output-format json` 우선, Stop 훅은 여러 파일을 쓰는 단계만 | [실측] `claude` 2.1.177 에 `--json-schema` 있음 |
| 11 | 단계마다 `--max-turns` | `--max-budget-usd` + 프로세스 벽시계 타임아웃 (+ 숨은 `--max-turns` 는 보조로만) | [실측] 2.1.177 help 에 `--max-turns` 없음. [P0 결과 · 실측 2.1.325] 숨은 옵션이고 동작한다 — `--max-turns 1` 에 2턴이 필요한 일을 주면 `subtype:"error_max_turns"` · `is_error:true` · `errors:["Reached maximum number of turns (1)"]` · 종료 코드 1. 상한 수단으로 같이 쓴다 |
| 12 | 수치 지표 전부로 합격 판정 | 스타일 유사도 · ΔE 는 Phase 2 보정 전까지 기록만 | 보정 안 된 임베딩 임계값은 결과를 흔든다 |
| 13 | Phase 1 ~ 6 | Phase 0(플러그인 분리 + 스파이크) 추가, Phase 1 = 1a(손 spec) · 1b(컨셉아트) | §11 |
| 14 | 출처 3종 | `provided` 추가(component 이미지를 그대로 쓰기) | 요청 때 `use: auto/asset/reference` 로 선언 — 실행 중 묻지 않는다 |

---

## 2. 전체 구조

### 2-1. 구성 요소

```text
run_pipeline (Python 오케스트레이터 — 순서 · 재시도 · 분기 · 상한 · 잠금)
 ├─ LLM 단계 ─────▶ claude -p   (UE 도구 없음 · work/<run_id> 파일만 읽고 씀 · JSON 스키마 출력)
 ├─ 코드 단계 ────▶ editor_bridge (HTTP 127.0.0.1:18765) ─▶ UE 에디터: EditorMcpCore + WidgetMcp
 │               ├─▶ generate_ui_asset 라우터 ─▶ procedural / codex exec / ComfyUI(Phase 5) / provided
 │               └─▶ UBT 빌드 (codegen 단계에서만, 에디터 내린 상태)
 └─ 파일 ────────▶ Tools/uigen/work/<run_id>/   (단계 사이 데이터 · git 무시 · Saved 밖)
```

- **MCP 서버(`widget_mcp`)는 사람 · Claude 가 대화로 쓸 때의 창구**다. 파이프라인은 같은 브리지 엔드포인트를 HTTP 로 직접 부른다 — 무인 LLM 단계에는 UE 도구를 주지 않는다.
- 작업 폴더를 `Saved/` 밖에 두는 이유: `Saved/` 아래 이미지는 Read · 파일 전송이 막혀 render.png 를 사람도 verifier 도 못 본다(프로젝트 실측 함정).
- 한 번에 run 하나(`work/.lock`) — 브리지 · 에디터가 하나이고, 에디터가 둘 뜨면 `UNAUTHORIZED` 가 난다.

### 2-2. 단계와 입출력

| 단계 | 주체 | 입력 | 출력 (`work/<run_id>/`) | 실패 시 |
| :--- | :--- | :--- | :--- | :--- |
| normalize | concept = 코드(복사) · text / multi_ref = LLM + codex | 진입점 인자 · inputs.yaml | `reference.png` · `brief.json` · (text) `mockups/` · `selection.json` | 중단 |
| analyze | LLM | reference · brief · 화면 프로필 · (있으면) 기존 바인딩 계약 | `spec.json` | 스키마 위반 → 1회 재요청 후 중단 |
| codegen | 코드 | spec 의 바인딩 목록 | C++ 파일 · `codegen.json`(계약 해시) · 빌드 로그 | 생성 파일 원복 후 중단 |
| generate | 코드 | spec.assets[] · routing.yaml | `assets/raw/` · `gen.jsonl` | 에셋별 폴백 → 한도면 `quota` 로 멈춤 |
| refine | 코드 | raw | `assets/final/` · `manifest.json` | 에셋 재생성 요청(generate) |
| build | 코드(브리지) | spec · manifest | `/Game/_AutoGen/<run_id>/` (저장 안 함) · `build.json`(적용 op · revision) | 배치 무변경 · 중단 |
| verify | 코드 + LLM(fixes 만) | reference · spec · 컴파일된 WBP | `render.png` · `geometry.json` · `report.json` · (실패) `fixes.json` | fix 로 |
| fix | LLM | report · fixes · spec | `patches/NNN.json` (spec patch) | 상한 도달 → finalize(실패) |
| finalize | 코드 | report | 통과: run 패키지 저장 · `lineage.json` 갱신 / 실패: 폐기(`--keep-failed` 면 저장) | — |

**재시도 분기** — fix 가 낸 patch 의 op 종류로 코드가 정한다.

| patch op 종류 | 돌아가는 단계 |
| :--- | :--- |
| 배치 · 슬롯 · 스타일 · 텍스트 | build |
| 에셋 교체 · 재생성 | generate(그 에셋만) → refine → build |
| 바인딩 추가 · 타입 변경 | codegen → (에디터 재기동) → build |

- 상한: 재시도 N = 3(잠정). **두 번 연속 실패 게이트 집합이 줄지 않으면 조기 종료**(같은 자리를 맴도는 것 방지). 가장 나은 시도의 기록은 디스크에 남는다.
- **통과 뒤 외형 라운드(1b 후속 C — `stages/style.py` · `run_pipeline._style_review`):** 게이트가 모두 통과하면 finalize 전에, concept 모드(reference 있음)에서 영역 · 글자 비교를 기록하고(`style/before`), `style_review.rounds`(기본 1)만큼 style_verifier → style_fix → (에셋 교체면 generate → refine) → build → verify 를 돈다. 허용 op 는 외형만(`style.*` · 글자 색 · 굵기 · 크기 · 폰트 · 효과 · `slot.padding` · `justification` · `replace_asset`) — 배치는 못 고친다. **합격 판정은 그대로 게이트만**: 라운드 뒤 게이트가 모두 통과하면 그 라운드를 받고, 하나라도 깨지면 버린다 — 마지막 통과 spec · manifest(· 교체한 에셋 파일)로 되돌리고 저장 안 한 run 패키지를 전부 버린 뒤 처음부터 다시 build → verify(통과해야 함, 아니면 `STYLE_REVERT_FAILED`)하고 finalize — 에디터의 WBP · 라운드가 만든 텍스처 · 머티리얼이 라운드 상태로 저장되지 않게. fix.mode deterministic 이면 라운드는 돌지 않고 비교만 기록한다. 라운드 시도도 `specs/NNN.json` · `attempts[]`(`style_round`, 되돌림은 `revert`)에 남고 재시도 상한 N 에는 세지 않는다.
- codegen 은 **바인딩 계약 해시가 바뀔 때만** 돈다 — 대부분의 재시도는 빌드 · 재기동이 없다.
- codegen 이 analyze 직후(아직 에디터에 이번 run 의 것이 없을 때)라서 재기동해도 잃는 것이 없다. 재시도 중 재기동이 필요하면 저장 안 한 run 패키지를 버리고 spec + manifest 에서 다시 빌드한다(결정적이라 같은 결과).

### 2-3. 에디터 운용

- 시작 · 대기 · 종료는 CLAUDE.md 의 에디터 주기를 그대로 쓴다(DebugGame 에디터 · `wait_for_bridge.py` · `quit_editor` · `wait_for_exit.py`).
- `quit_editor` 는 더티면 거절한다 — **`/Game/_AutoGen/` 만 더티일 때 discard 를 허용**하도록 그 목록에 더한다.
- codegen 빌드는 실행 중인 에디터 구성(DebugGame)만 한다. 두 구성 빌드는 Phase 검증 때(프로젝트 회귀 방침).
- Phase 5 ComfyUI: 12 GB VRAM 을 에디터와 나누면 부족할 수 있다 — generate 동안 에디터를 내리는 운용을 기본으로 둔다(§7).

---

## 3. 플러그인 · 디렉터리 구조

### 3-1. 플러그인 분리 (Phase 0)

```text
Plugins/
├── EditorMcpCore/   공용 — HTTP 브리지 · 디스패처 · 봉투 · 토큰 · request_id 멱등 캐시
│                    · get_editor_status · 자동 시험 실행 · 보호 목록 · 쓰기 허용 경로 · 전역 더티 비교
│                    · revision(SHA1) · 되돌리기 저널 · PNG 출력 경로 제한
├── AnimGraphMcp/    애니 — AnimBP · 몽타주 · 리타깃 · 캡처 · 생성 (지금 기능 그대로)
├── WidgetMcp/       UI — 텍스처 임포트 · WBP 생성/조정/역추출 · 렌더 · 바인딩 계약 (§6)
└── StateTreeMcp/    AI — StateTree 저작 (Phase 0 에서 같이 옮김 — 사용자 결정 11-14)
```

- **코어로 가는 것의 기준 = StateTree 가 기대는 것.** StateTree 코드(`Core/AnimMcpStateTree*` · `Tools/AnimMcpTools_StateTree.cpp` · `Tests/AnimMcpStateTree*`, 약 6.8K줄)가 include 하는 비-StateTree 헤더는 `AnimMcpAssetProtection` · `AnimMcpAssetResolver` · `AnimMcpPropertyRules` · `AnimMcpRuntimeScenario` · `AnimMcpAutomationRunner` · `Bridge/AnimMcpDispatcher` · `Bridge/AnimMcpTypes` · `AnimMcpLog` 뿐이다 [실측 11-14]. 이것들이 코어에 있으면 StateTree 이전은 거의 기계적이다.
- **모듈 이름:** `EditorMcpCore`(Editor) · `AnimGraphMcpEditor`(그대로) · `StateTreeMcpEditor` · `WidgetMcpEditor`. 콘솔 명령은 `EditorMcp.Start/Stop/Status` + 기존 `AnimGraphMcp.*` 별칭.
- **StateTree 빌드 의존성**(`StateTreeModule` · `StateTreeEditorModule` · `GameplayStateTreeModule` · `AIModule` · `PropertyBindingUtils(Editor)` 등)은 StateTree 와 같이 옮겨 AnimGraphMcp 를 가볍게 한다.
- **자동 시험 이름:** `AnimGraphMcp.StateTree.*` → `StateTreeMcp.*`. 현행 참조 문서(플러그인 README · `Tools/mcp/README.md` · `Docs/StateTree/DevelopmentGuide.md`)는 고치고, 지난 보고서 · M3 설계의 기록은 그대로 둔다.
- `StateTreeEditPaths` 는 `[EditorMcp]` 와 기존 `[AnimGraphMcp]` 둘 다에서 읽고, `get_editor_status.state_tree_edit_paths` 필드는 그대로 둔다.

- **등록 방식:** 코어가 `IEditorMcpCoreModule::Get().RegisterTools(FName Feature, TFunction<void(FEditorMcpDispatcher&)>)`(이름 잠정)를 내보내고, 기능 플러그인이 모듈 시작 때 등록한다. 지금 `FAnimMcpDispatcher::RegisterTool(Name, Description, Handler)` [소스] `AnimMcpDispatcher.h:19` 를 그대로 코어로 옮기는 것이다.
- **옮길 양:** 브리지 735줄 + 자동 시험 실행 335줄 + 보호 목록 171줄 + 생성 가드의 공용 부분 — 대략 2 ~ 3K줄. [실측]
- **호환 유지:** 포트 18765 · 토큰 파일 위치 · `-AnimGraphMcpPort` 그대로. ini 는 새 `[EditorMcp]` 와 기존 `[AnimGraphMcp]` 를 둘 다 읽는다. 기존 Python 클라이언트와 하네스는 수정 없이 돌아야 한다.
- **Python 쪽:** `Tools/mcp/anim_graph_mcp/bridge.py` → `Tools/mcp/editor_bridge/`(공용) + 기능별 서버(`anim_graph_mcp/` · `state_tree_mcp/` · `widget_mcp/`). 지금 `state_tree_mcp/server.py` 가 `from anim_graph_mcp import bridge` 로 공유하는 방식 [소스] 의 일반화다.
- **회귀:** `AnimGraphMcp.*` 자동 시험 · `Tools/mcp` pytest · 통합 하네스 1개 · 빌드 2회(프로젝트 방침).

**[P0 결과] 실제로 나눈 모양 (11-14, 미커밋)**

| 플러그인 · 모듈 | 줄 수 | 내용 |
| :--- | ---: | :--- |
| `EditorMcpCore` · `EditorMcpCore` | 2,985 | 브리지 · 디스패처(기능 소유 `BeginFeature/EndFeature/RemoveFeature`) · 봉투 · 토큰 · 캐시 · 코어 Tool 4개(`get_editor_status` · `quit_editor` · `run/poll_automation_tests`) · 러너 · 시나리오 슬롯 · 보호 목록 · 경로 해석 · 값 변환(`Core/AnimMcpPropertyValues`) · 쓰기 가드 공용부(`Core/EditorMcpGuard` — 접두 · `FDirtySnapshot`) · 설정(`Core/EditorMcpSettings`) · 시험 `EditorMcpCore.*` |
| `AnimGraphMcp` · `AnimGraphMcpEditor` | 31,097 | 애니 Tool 37개 + `generation` 상태 필드. 동작 불변 — `AnimMcpGeneration::FDirtyGuard` 는 코어 스냅샷 + 생성 경로, `AnimMcpPropertyRules` 는 노드 허용 목록만 남기고 코어 값 변환 헤더를 포함 |
| `StateTreeMcp` · `StateTreeMcpEditor` | 6,851 | StateTree Tool 9개 + `state_tree_edit_paths` 상태 필드 · 시험 `StateTreeMcp.*`(20개) |
| `WidgetMcp` · `WidgetMcpEditor` | 666 | 뼈대(기능 이름 · `widget` 상태 필드, Tool 0) + `Private/Spike`(A6 · A7) · 시험 `WidgetMcp.Spike.BuildRender` |

- **등록 API(확정):** `IEditorMcpCoreModule::Get().RegisterTools(FName Feature, TFunction<void(FAnimMcpDispatcher&)>)` · `RegisterStatusSection(FName, TFunction<void(const TSharedRef<FJsonObject>&)>)` · `UnregisterTools(FName)` (종료 경로는 `GetIfLoaded()`). 코어는 `OnPostEngineInit` 에 브리지를 열며 등록 함수를 전부 돌리고, 떠 있는 동안의 등록 · 해제는 `FAnimMcpHttpBridge::SyncRoutes` 로 라우트를 붙이고 뗀다.
- **이름:** 코어 타입은 분리 전 이름(`FAnimMcpDispatcher` · `FAnimMcpError` · `AnimMcpJson` · 로그 `LogAnimGraphMcp`)을 그대로 쓰고 헤더 경로(`Bridge/…` · `Core/…`)도 같게 둬서 AnimGraphMcp · StateTree 코드는 include 몇 줄만 바뀌었다. 새 코드용 별칭은 `EditorMcp.h`(`FEditorMcpDispatcher` 등). 이름 뒤집기는 후속 과제.
- **코어 범위 조정 2건:** ① `AnimMcpPropertyRules` 는 통째가 아니라 **값 변환만** 코어로(노드 허용 표는 AnimGraph 모듈을 끌어오므로 AnimGraphMcp 에 남김) ② `AnimMcpAssetResolver` 의 애니 단축 로더(`LoadAnimBlueprint` 등)는 Engine 타입뿐이라 코어에 그대로 둠.
- **호환 [실측]:** 포트 18765 · `Saved/AnimGraphMcp/token` · 헤더 `X-AnimMcp-Token` · `-AnimGraphMcpPort` · 콘솔 `AnimGraphMcp.*`(별칭) + `EditorMcp.*` · 기동 로그 문구 · `get_editor_status` 필드(`features[]` · `widget` 만 추가, `plugin_version` 은 EditorMcpCore 0.1.0) · Tool 50개 이름 그대로. ini 는 `[EditorMcp]` + `[AnimGraphMcp]`(배열 합침 · 값은 새 섹션 우선). Python `Tools/mcp/editor_bridge/bridge.py` — 옛 `anim_graph_mcp/bridge.py` 는 `sys.modules` 교체로 **같은 모듈 객체**(monkeypatch 호환).
- **옮긴 시험 타입의 애셋 호환:** `Content/AI/Test/ST_M3_Probe` 가 `/Script/AnimGraphMcpEditor.AnimMcpLifecycleProbeTask` 를 저장하고 있어 `DefaultEngine.ini [CoreRedirects]` 에 `StructRedirects` 4줄을 더했다 — [실측] 새 에디터에서 `inspect_state_tree` 가 `/Script/StateTreeMcpEditor.…` 로 풀고 값 · `ready_to_run` 유지.
- **함정 [실측]:** ① 파일이 빠지면 유니티 묶음이 바뀌어 다른 파일의 익명 이름공간이 부딪힌다(`AnimMcpRuntimeTests.cpp` 와 `AnimMcpAutomationRunnerTests.cpp` 의 `Step` — 한쪽 이름 변경). 새 모듈은 `-DisableAdaptiveUnity` 로 한 번 묶어 빌드해 확인했다. ② `FPackageName::IsValidLongPackageName("/Game")` 이 true — '마운트 루트 거부' 판정이 실제로는 막지 못한다. 코어 `EditorMcpGuard::IsValidPrefix` 는 고쳤고, AnimGraphMcp 생성 경로 설정은 동작 불변 원칙으로 그대로(후속). ③ 엔진이 PIE 시작마다 로드된 StateTree 를 전부 `CompileIfChanged` 한다 [소스] `StateTreeCompilerManager.cpp:238-245` — `StateTreeMcp.06_CompileFailure` 의 깨진 트리가 메모리에 남으면 같은 에디터의 이후 PIE 시험이 그 로그로 실패한다(시험 순서 — `AstralBreak.*` 를 먼저 돌린다).

### 3-2. 저장소 디렉터리

```text
Plugins/EditorMcpCore/ · AnimGraphMcp/ · WidgetMcp/
Tools/mcp/editor_bridge/ · widget_mcp/                MCP 창구 (대화용)
Tools/uigen/
├── run_pipeline.py                                   진입점
├── stages/        normalize · analyze · codegen · generate · refine · build · verify · fix · finalize
├── gen/           generate_ui_asset 라우터 · 제공자(procedural · codex · comfy · provided) · 정책 · 기록
├── schemas/       inputs · brief · spec · patch · manifest · report · fixes (JSON Schema)
├── profiles/      화면 종류 프로필 (hud · menu · options · dialog)
├── prompts/       LLM 단계 시스템 프롬프트
├── codegen/       C++ 템플릿
├── config/        pipeline.yaml (상한 · 경로 · 모델) · routing.yaml · screens.yaml (화면 ID → 폴더 · 클래스)
├── claude_ctx/    LLM 단계 작업 디렉터리 (자체 .claude · 짧은 CLAUDE.md)
├── tests/         pytest
├── work/          run 별 산출물 — git 무시
└── metrics/       uigen.jsonl · 집계 리포트 — git 무시(집계 결과는 §12 질문)
Source/AstralBreak/UI/<기능>/ + <기능>/AutoGen/       C++ (§3-3)
Content/_AutoGen/<run_id>/                            run 산출물 — git 무시
Content/UI/<기능>/                                     승격본 — git 커밋
Content/UI/Fonts/                                      프로젝트 폰트
```

`.gitignore` 에 `Tools/uigen/work/` · `Tools/uigen/metrics/` · `Content/_AutoGen/` 를 더한다. `.png` · `.uasset` 은 LFS 대상이다 [실측] `.gitattributes:5,18` — 그래서 run 산출물은 커밋하지 않는다.

### 3-3. C++ 코드 생성 — 생성 베이스 + 스텁 (Generation Gap)

```text
Source/AstralBreak/UI/
├── Debug/                                   기존
└── HUD/
    ├── AstralCombatHUDWidget.h/.cpp         스텁 — 없을 때만 생성, 이후 사람 소유 (M4 C 로직)
    └── AutoGen/
        └── AstralCombatHUDViewBase.h/.cpp   생성 — 매번 덮어씀 (첫 줄 표식)
```

| 파일 | 내용 | 덮어쓰기 |
| :--- | :--- | :--- |
| `UAstral<화면>ViewBase` (`UUserWidget` 자식, Abstract) | 동적 위젯마다 `UPROPERTY(meta=(BindWidget))` + **데이터 종류별 setter** | 매번 — 첫 줄 `// AUTO-GENERATED by uigen` 이 있을 때만 |
| `UAstral<화면>Widget : ViewBase` | 빈 클래스. 게임 시스템 연결(GAS · 체인 컴포넌트)은 여기 | **절대 안 함** — 없을 때만 생성 |
| WBP | 부모 = 스텁 | run 마다 새로 |

**setter 템플릿 (Phase 1 범위)**

| brief 데이터 종류 | 위젯 | 생성되는 함수 |
| :--- | :--- | :--- |
| `text` | TextBlock | `SetX(const FText&)` |
| `number` | TextBlock | `SetX(int32 / float)` — 형식은 brief 의 `format` |
| `progress` | ProgressBar | `SetX(float Percent)` |
| `flag` | 아무 위젯 | `SetXVisible(bool)` |
| `image` | Image | `SetX(UTexture2D*)` |
| `list` | ListView / 반복 하위 WBP | Phase 3 (하위 WBP 생성과 같이) |

이름은 brief 의 데이터 id 에서 나온다. M4 HUD 예(§4-2 의 `dynamic_data`): `SetUltGauge(float)` · `SetUltReadyVisible(bool)` · `SetChainPanelVisible(bool)` · `SetChainRemaining(float)` · `SetChainCount(const FText&)` · `SetBurstBannerVisible(bool)` · `SetBurstCount(int32)` · `SetUltBlockedVisible(bool)`. 스텁(`UAstralCombatHUDWidget`, M4 설계 §5 의 이름)에는 개발 세션이 '속성 변화 통지 → setter 호출' 몇 줄을 쓴다.

**소유 규칙 (codegen 의 안전장치)**

1. 쓰기는 `Source/AstralBreak/UI/*/AutoGen/`(덮어쓰기, 표식 있는 파일만)과 `Source/AstralBreak/UI/*/`(스텁 새로 만들기만)뿐 — 그 밖은 거부. 사람이 표식을 지우면 그 파일은 사람 소유가 된다.
2. **바인딩은 추가만** — 제거 대신 `BindWidgetOptional` 로 낮춘다. 같은 클래스를 쓰는 이전 run 의 WBP 가 계속 컴파일되게 하려는 것이다.
3. 빌드 실패 → 이번에 쓴 파일을 `work/<run_id>/codegen/backup/` 에서 되돌리고 중단.
4. 클래스 이름이 정체성이다 — WBP 가 기억하는 부모 경로는 `/Script/AstralBreak.<클래스>` 로 폴더가 들어가지 않는다. 폴더는 옮겨도 되고, 이름은 `screens.yaml` 에서 처음에 정해 바꾸지 않는다.
5. 헤더 파일 이름은 모듈 안에서 겹치면 안 된다(UHT) — `ViewBase` / `Widget` 접미사로 피한다. 생성 cpp 에는 익명 네임스페이스를 쓰지 않는다(유니티 빌드 충돌 — 프로젝트 실측 함정).
6. 바인딩 계약은 기존 클래스에서 리플렉션으로 읽는다 — `FWidgetBlueprintEditorUtils::IsBindWidgetProperty(Property, bIsOptional)` [소스] `WidgetBlueprintEditorUtils.h:104`.
7. 채택되지 않은 화면의 클래스가 쌓이므로, '승격된 WBP 가 없는 화면' 목록을 보여 주는 정리 도구를 둔다(삭제는 사람이 결정).

---

## 4. 스키마 초안

전부 `schema_version` 을 갖고 `Tools/uigen/schemas/` 의 JSON Schema 로 검사한다. 아래 예시는 M4 HUD 기준이다.

### 4-1. inputs.yaml

```yaml
mode: multi_ref                 # concept | text | multi_ref (진입점 --concept / --text 는 이 파일을 내부에서 만든다)
screen_type: hud                # hud | menu | options | dialog  → profiles/
screen_id: CombatHUD            # screens.yaml 의 키 → C++ 클래스 · 폴더 · 승격 경로
text: "전투 HUD — 오의 게이지 · 체인 패널 · 버스트 배너"
data:                           # 동적 데이터 (생략 시 analyze 가 제안하고 brief 에 근거를 적는다)
  - { id: ult_gauge, type: progress }
  - { id: chain_remaining, type: number, format: "0.0" }
images:
  - { path: ref/hud_concept.png, role: layout }
  - { path: ref/style_gold.png,  role: style }
  - { path: ref/ult_frame.png,   role: component, target: UltGauge, use: auto }   # auto | asset | reference
  - { path: ref/mood.png }       # 역할 생략 → normalize 가 분류하고 brief 에 근거 기록
```

`use` 는 component 역할에만 뜻이 있다(기본 `auto` — 검사(투명 · 글자 없음 · 해상도)를 통과하면 그대로 쓰고, 아니면 참조로 새로 생성 · 리포트에 이유). 나머지 역할은 항상 참조만.

### 4-2. brief.json

```json
{
  "schema_version": 1,
  "run_id": "R20261114_153000_CombatHUD",
  "mode": "concept",
  "screen_type": "hud",
  "screen_id": "CombatHUD",
  "resolution": [1920, 1080],
  "language": "ko",
  "font": "/Game/UI/Fonts/Pretendard",
  "required_elements": [
    { "id": "UltGauge", "kind": "progress", "desc": "오의 게이지, 가득 차면 강조" },
    { "id": "ChainPanel", "kind": "panel", "desc": "체인 남은 시간 · 참가 N/4" },
    { "id": "BurstBanner", "kind": "banner", "desc": "버스트 인원 표시" },
    { "id": "UltBlockedText", "kind": "text", "desc": "'오의 불가'" }
  ],
  "dynamic_data": [
    { "id": "ult_gauge", "type": "progress", "widget": "UltGauge", "sample": 0.7 },
    { "id": "ult_ready", "type": "flag", "widget": "UltReadyGlow", "sample": false },
    { "id": "chain_panel", "type": "flag", "widget": "ChainPanel", "sample": true },
    { "id": "chain_remaining", "type": "number", "widget": "ChainTimerText", "format": "0.0", "sample": 4.2 },
    { "id": "chain_count", "type": "text", "widget": "ChainCountText", "sample": "2/4" },
    { "id": "burst_banner", "type": "flag", "widget": "BurstBanner", "sample": false },
    { "id": "burst_count", "type": "number", "widget": "BurstCountText", "format": "0", "sample": 3 },
    { "id": "ult_blocked", "type": "flag", "widget": "UltBlockedText", "sample": false }
  ],
  "static_text": [ { "widget": "UltBlockedText", "value": "오의 불가" } ],
  "style_keywords": ["dark fantasy", "gold trim", "thin frames"],
  "references": [
    { "path": "reference.png", "role": "layout", "role_source": "user" },
    { "path": "ref/mood.png", "role": "mood", "role_source": "auto", "reason": "색 · 조명만 있고 UI 요소가 없다" }
  ],
  "conflicts": [ { "between": ["text", "style"], "resolved_by": "text", "note": "…" } ],
  "binding_contract": { "class": "UAstralCombatHUDWidget", "source": "new", "bindings": ["UltGauge", "UltReadyGlow", "ChainPanel", "ChainTimerText", "ChainCountText", "BurstBanner", "BurstCountText", "UltBlockedText"] }
}
```

### 4-3. spec.json

(발췌 — 위젯 두 개와 에셋 하나만 보인다)

```json
{
  "schema_version": 1,
  "canvas": [1920, 1080],
  "profile": "hud",
  "root": "Root",
  "widgets": [
    { "id": "Root", "type": "CanvasPanel" },
    { "id": "UltGauge", "type": "ProgressBar", "parent": "Root",
      "slot": { "kind": "canvas", "anchors": [0.5, 1, 0.5, 1], "alignment": [0.5, 1], "position": [0, -64], "size": [420, 28], "z": 1 },
      "bbox_intent": [750, 988, 420, 28],
      "style": { "background": { "asset": "ult_frame", "draw_as": "box", "margin": [0.25, 0.4, 0.25, 0.4] },
                 "fill": { "procedural": { "kind": "rounded_box", "color": "#E8B54A", "radius": 6 } } },
      "binding": { "data": "ult_gauge", "kind": "progress" } },
    { "id": "ChainTimerText", "type": "TextBlock", "parent": "ChainPanel",
      "slot": { "kind": "vertical_box", "padding": [0, 0, 0, 4], "h_align": "center" },
      "bbox_intent": [1640, 120, 120, 36],
      "text": { "source": "dynamic", "data": "chain_remaining" },
      "font": { "size": 28, "weight": "bold", "color": "#FFF3D6" },
      "binding": { "data": "chain_remaining", "kind": "number" } }
  ],
  "assets": [
    { "asset_id": "ult_frame", "kind": "frame", "provenance": "codex", "size": [512, 64], "nine_slice": true,
      "prompt": "ornate thin gold frame for a horizontal gauge, transparent background, no text", "anchor": true }
  ],
  "allow_overlap": [ ["BurstBanner", "ChainPanel"] ],
  "locked": []
}
```

- `id` = WBP 의 위젯 이름(= 바인딩 이름). `bbox_intent` 는 reference 픽셀 좌표 `[x, y, w, h]` — verify 의 IoU 기준. canvas 슬롯의 `anchors` 는 `[min.x, min.y, max.x, max.y]`, `margin` 은 `[left, top, right, bottom]` 비율.
- 슬롯 종류: `canvas`(앵커 · 위치 · 크기) · `overlay` · `vertical_box` · `horizontal_box` · `uniform_grid` · `scroll` · `size_box`. 최상위 영역은 Canvas + 앵커, 영역 안은 박스 계열(프로필이 권장을 정한다).
- 위젯 타입 어휘(Phase 1): CanvasPanel · Overlay · VerticalBox · HorizontalBox · UniformGridPanel · SizeBox · Border · Image · TextBlock · ProgressBar · Button · Spacer. Phase 3 에서 ScrollBox · ListView · Slider · CheckBox · ComboBoxString · 하위 WBP(`repeat`).
- `locked` — 역추출이 지원하지 않는 위젯 · 속성(§6 `export_widget_spec` 의 `unsupported[]`). patch 가 건드리면 **브리지가 거부**한다(LLM 이 지키는 규칙이 아니다).

### 4-4. spec patch

```json
{
  "schema_version": 1,
  "base_revision": "sha1:…",
  "source": "fix",
  "ops": [
    { "op": "set", "widget": "UltGauge", "path": "slot.position", "value": [0, -72], "reason": "IoU 0.61 — 너무 아래" },
    { "op": "replace_asset", "asset": "ult_frame", "regenerate": true, "reason": "OCR 에 글자 검출" },
    { "op": "add_widget", "widget": { "id": "UltReadyGlow", "type": "Image", "parent": "UltGaugeOverlay" }, "index": 1 },
    { "op": "remove_widget", "widget": "OldDecor" },
    { "op": "move", "widget": "ChainCountText", "parent": "ChainPanel", "index": 0 }
  ]
}
```

- `base_revision` 이 지금 WBP 의 revision 과 다르면 `REVISION_MISMATCH` 로 무변경(사람이 그사이 고쳤다는 뜻 — 수정 모드는 다시 역추출부터).
- op 종류가 §2-2 재시도 분기를 정한다. 바인딩 위젯의 `remove_widget` 은 거부된다(바인딩은 추가만).

### 4-5. manifest.json · report.json · 지표 JSONL

```json
{ "assets": [ { "asset_id": "ult_frame", "file": "assets/final/ult_frame.png", "sha256": "…", "size": [512, 64],
    "alpha": true, "nine_slice_margin": [0.25, 0.4, 0.25, 0.4], "ocr_text": "", "provenance": "codex",
    "backend": "codex", "prompt": "…", "anchor": true, "ue_path": "/Game/_AutoGen/R…/T_ult_frame",
    "compression": "TC_EditorIcon" } ] }
```

```json
{ "run_id": "R…", "parent_run_id": null, "status": "pass", "attempt": 2,
  "gates": [ { "name": "iou_leaf_min", "value": 0.78, "threshold": 0.70, "pass": true } ],
  "recorded": { "delta_e_region_mean": 6.1, "style_sim_anchor": 0.82 },
  "fixes": [], "unsupported": [], "durations_s": { "generate": 212.4, "build": 6.1 } }
```

`metrics/uigen.jsonl` 한 줄 = 에셋 하나 또는 run 하나: `run_id · asset_id · kind · backend · ok · duration_s · retries · verify · style_sim_anchor` (+ comfy: `workflow_sha256 · model_sha256 · lora_sha256[] · seed`, codex: `codex_version`). Phase 1 부터 쓰고, 집계는 Phase 2.

---

## 5. 화면 종류 프로필 (`profiles/*.yaml`)

| 항목 | hud | menu (장비 · 인벤토리 · 상점) | options | dialog |
| :--- | :--- | :--- | :--- | :--- |
| 배경 | 없음(투명) | 전체 화면 패널 | 전체 또는 중앙 패널 | 반투명 막 + 중앙 패널 |
| 앵커 | 화면 가장자리 · 세이프존 안 | 영역 단위 | 영역 단위 | 중앙 |
| analyze 주의 | **reference 뒤의 게임 장면과 UI 분리** — 장면을 에셋으로 만들지 않는다 | 반복 슬롯 = 그리드 + 템플릿 | 표준 컨트롤(Slider · CheckBox · ComboBox) | 버튼 행 |
| verify 영역 | UI bbox 합집합만 비교(장면 제외) | 전체 | 전체 | 패널 |
| 작은 요소 | 많음 → 중심점 거리 기준 | 슬롯 아이콘 | 적음 | 적음 |
| Phase | 1 | 2 보정 세트 · 3 | 2 보정 세트 · 3 | 3 |

---

## 6. UE 쪽 도구 — `WidgetMcp`

모든 쓰기 도구는 코어의 공통 가드를 받는다: 쓰기 허용 경로 `WidgetOutputPaths=/Game/_AutoGen/`(밖이면 `OUTPUT_PATH_NOT_ALLOWED`) · 덮어쓰기 거부 · 호출 전후 전역 더티 비교(`UNEXPECTED_DIRTY`) · `save` 기본 false. 지금 생성 Tool 이 쓰는 방식과 같다 [소스] `Plugins/AnimGraphMcp/README.md:49-51`.

| Tool | 하는 일 | 안전장치 · 엔진 근거 |
| :--- | :--- | :--- |
| `import_ui_textures` | PNG 묶음 임포트 + UI 설정: 압축 `TC_EditorIcon`(기본, 종류별 `TC_BC7`) · `TEXTUREGROUP_UI` · `TMGS_NoMipmaps` · `NeverStream` · sRGB | [소스] `TextureDefines.h:46,156,400` · `NeverStream` 은 `UStreamableRenderAsset` 의 비트필드 `StreamableRenderAsset.h:299`. 임포트 경로는 기존 Interchange 사용 — **[1a-2 실측] 동기 · 기본 텍스처 파이프라인 복제 + `bAllowNonPowerOfTwo=true`**(§11 1a-2) |
| `create_ui_material_instances` | UI 도메인 머티리얼 인스턴스(procedural 그라데이션 · 마스크) | Phase 1b |
| `create_widget_blueprint` | 부모 클래스(스텁)로 빈 WBP 생성 | `UWidgetBlueprintFactory`(MinimalAPI — `ParentClass` 프로퍼티 · 가상 `FactoryCreateNew`) [소스] `WidgetBlueprintFactory.h:13-29` · 기본 루트 위젯 [P0 결과] 없음 → Canvas 를 직접 만들고 `OnVariableAdded` (§12-1 A7) |
| `preview_widget_spec` / `apply_widget_spec` | **조정기** — 지금 WBP 와 목표 spec 의 차이를 op 로 계산 → 전체 사전 검증 → 배치 적용(되돌리기 저널) → 컴파일. `expected_revision` 필수 | 위젯 생성 `UWidgetTree::ConstructWidget<T>(Class, Name)` [소스] `WidgetTree.h:102`. **GUID 맵:** 위젯 추가 · 이름 변경 · 제거마다 `UWidgetBlueprint::OnVariableAdded / OnVariableRenamed / OnVariableRemoved` 를 부른다 [소스] `WidgetBlueprint.h:259-261`. 맵이 비어 있는 새 WBP 는 컴파일러가 결정적 GUID 로 채우지만, 비어 있지 않은 WBP 에 그냥 더하면 `ensureAlways` 가 터진다 [소스] `WidgetBlueprintCompiler.cpp:769,794` |
| `apply_widget_patch` | spec patch 를 조정기로 적용(`locked` 거부 · 바인딩 제거 거부) | 위와 같음 |
| `export_widget_spec` | WBP → spec + `unsupported[]` + `revision`(정규화 spec 의 SHA1) | 사람이 고친 것도 그대로 읽는다 |
| `compile_widget_blueprint` · `save_widget_run` | 컴파일(오류 · BindWidget 누락 보고) · run 패키지 일괄 저장 | 저장은 finalize 에서만 |
| `render_widget` | 오프스크린 렌더 → PNG + **같은 그리기에서** 이름 있는 위젯 전부의 geometry | `FWidgetRenderer::DrawWidget(RenderTarget, SWidget, Scale, DrawSize, DeltaTime)` [소스] `Slate/WidgetRenderer.h:75` · `UWidget::GetPaintSpaceGeometry()` [소스] `Widget.h:786`. Scale 을 직접 주므로 DPI 곡선이 끼지 않는다. 폰트 · 텍스처 로딩 때문에 두 번 그린다 [P0 결과 — 에디터 안에서는 첫 그림부터 같았다, 두 번 그리기는 안전장치로 유지] · geometry 오차 0 px · **감마 조합 주의(§12-1 A6-색)**. 출력은 PNG 출력 경로 제한 안 새 폴더만 |
| `list_bind_widgets` | 클래스의 BindWidget 목록(선택 여부 포함) | `IsBindWidgetProperty` [소스] `WidgetBlueprintEditorUtils.h:104` |
| `discard_run_packages` | 저장 안 한 `/Game/_AutoGen/<run_id>/` 패키지 폐기 | 그 경로 밖 거부 |
| `promote_widget` | run 결과를 `/Game/UI/<기능>/` 로 복사(원본 run 은 그대로) | `promote_animation` 과 같은 방식 · Phase 4 |
| `import_font_family` | **[1b-3]** 폰트 파일 → `UFontFace` 여러 개 + 컴포지트 `UFont`(타입페이스 = spec 굵기 이름) — 프로젝트 폰트라 저장까지 | 이 Tool 만 별도 접두 `WidgetFontOutputPaths=/Game/UI/Fonts/`(§11 '1b 착수 때 정한 것' — 위 '쓰기는 `/Game/_AutoGen/` 만'의 예외) · 덮어쓰기 거부 · 전역 더티 비교 · `UFontFileImportFactory` 순서 [소스] `EditorFactories.cpp:5077` |

`get_editor_status` 에 `widget` 섹션(허용 경로 · 폰트 · 렌더 출력 루트)을 더한다.

---

## 7. 이미지 생성 백엔드 — `generate_ui_asset`

```yaml
# Tools/uigen/config/routing.yaml (잠정)
kinds:
  icon:       { primary: codex, fallback: [], anchor: codex, retry_backend: codex }     # Phase 5 에서 comfy A/B
  frame:      { primary: codex, fallback: [procedural], retry_backend: codex }
  panel_bg:   { primary: procedural, fallback: [codex] }
  fill:       { primary: procedural }                                                  # RoundedBox · UI 머티리얼
  ornament:   { primary: codex, fallback: [] }
  mockup:     { primary: codex }                                                       # text / multi_ref 의 목업
limits: { codex_calls_per_run: 20, on_quota: pause }      # pause | fallback_if_listed
```

- **procedural:** RoundedBox 브러시 · UI 머티리얼은 텍스처 없이 spec 의 브러시로 끝난다. SVG 는 Python 에서 래스터화(resvg 계열 의존성 [P0]).
- **codex:** `npm i -g @openai/codex@<고정 버전>` 으로 설치하고 `pipeline.yaml` 에 경로 · 기대 버전을 적는다(매 run 시작 때 `codex --version` 확인).
  - [실측] PATH 에 없다. 앱이 `%LOCALAPPDATA%\OpenAI\Codex\bin\codex.exe`(`0.130.0-alpha.5`, 해시 하위 폴더 포함)를 번들하지만 앱 업데이트 때 경로 · 버전이 바뀐다.
  - 호출: `codex exec -C <work/…/gen/<asset_id>> -s workspace-write --json -o last.txt -i <참조>… "<프롬프트>"` — [실측] 번들 버전에 `-i`(여러 장) · `--json` · `-o` · `-s` · `-C` 있음.
  - 프롬프트는 `$imagegen` **built-in `image_gen` 만**(API 키 경로 금지) · 투명 배경 · 글자 없음을 명시한다. built-in 은 키가 필요 없고 플랜을 쓴다 [실측] `~/.codex/skills/.system/imagegen/SKILL.md:14-15`.
  - **저장 위치를 지정할 수 없다** — 결과가 `$CODEX_HOME/generated_images/...` 에만 생긴다 [실측] 같은 파일 `:33-36`. `--json` 이벤트에서 세션을 찾아 그 파일을 work 로 복사한다 [P0]. 그래서 **codex 호출은 한 번에 하나**(동시에 돌리면 어느 파일이 어느 요청 것인지 모른다).
  - codex 프로세스 환경에는 `OPENAI_API_KEY` 를 넣지 않는다(유료 CLI 폴백 차단). 한도 초과 메시지 형태는 [P0] 에서 채록해 `quota` 판정에 쓴다.
  - **[P0 결과] (11-14, npm `@openai/codex@0.166.0` — 사용자 승인, `codex-cli 0.166.0`)**
    - 로그인: `codex login status` → `Logged in using ChatGPT` — npm 판도 `~/.codex` 로그인을 같이 쓴다(A2 참). `OPENAI_API_KEY` 는 환경에 없음을 확인하고 실행.
    - 1장 생성: `codex exec -C <dir> --skip-git-repo-check -s workspace-write --json -o last.txt "<built-in image_gen 만 · 투명 · 글자 없음 · 생성 뒤 cwd 로 복사>"` — 내장 `image_gen` 이 비대화형에서 돈다(A1 참). 결과 2172×724 RGBA PNG(357 KB), 완전 투명 픽셀 89.9 %, 글자 없음, 프롬프트대로 금색 게이지 프레임(사람 눈 확인).
    - **결과 찾기:** 파일은 `~/.codex/generated_images/<thread_id>/exec-<uuid>.png` — 폴더 이름이 `--json` 첫 이벤트 `thread.started.thread_id` 와 같다. 이벤트 흐름에 image_gen 항목은 따로 나오지 않았다(`agent_message` · `command_execution` 만). → generate 는 `thread_id` 로 폴더를 집고, 없으면 실행 전후 `generated_images` 차이로 대신한다(직렬 실행 전제 그대로).
    - 비용 · 시간: `turn.completed.usage` 입력 91,703(캐시 79,744) · 출력 508 토큰 — 대부분 에이전트가 imagegen `SKILL.md` 를 읽은 몫이다. 프롬프트에 '스킬 문서를 읽지 말 것'을 넣어 줄일 여지.
    - 함정: 출력 맨 앞에 `Reading additional input from stdin...` — stdin 이 열려 있으면 기다릴 수 있으니 오케스트레이터는 stdin 을 닫고(`DEVNULL`) 부른다.
    - **[1b-2 결과]** 생성기 `Tools/uigen/gen/codex.py` — 호출 규칙 · 실측은 §11 '1b-2 에서 확인 · 정한 것'(npm `.cmd` 래퍼를 피해 `node codex.js` 직접 · 프롬프트는 `exec` 바로 뒤 · '스킬 문서 읽지 말 것'으로 입력 91,703 → 38,362 토큰).
    - **한도(A3) — 재현 안 함.** [바이너리] codex.exe 안에 `usage_limit_reached` · `quota_exceeded` · `usage_not_included` · `rate_limit_exceeded` 식별자와 `Try again at …` 문구가 있다. `quota` 판정은 `--json` 오류 이벤트에서 이 식별자를 찾고, 없으면 연속 실패 횟수로 추정(§12-1 '틀리면' 그대로). 실제 이벤트 모양 · 종료 코드는 한도에 걸렸을 때 채록.
- **comfy (Phase 5):** SDXL급 + 스타일 참조(앵커 이미지). 실행마다 워크플로 JSON · 모델/LoRA 해시 · 시드를 기록. generate 동안 에디터를 내린다(12 GB 공유).
- **provided:** `use: auto/asset` 인 component 이미지 — 같은 refine · 검사를 거치고 출처 · 해시를 기록.
- **구조 재사용:** `Tools/mcp/anim_gen` 의 `router.py` · `fallback.py` · `policy.py` · `store.py` · `selection.py` 와 같은 모양으로 `Tools/uigen/gen/` 을 짓는다(import 로 묶지 않고 구조만 따른다).

**refine (코드):** 배경 제거(투명이 아니면) · 여백 자르기 · 크기 맞춤 · 9-slice margin 추정(가장자리에서 늘려도 되는 균일 띠 검출) · **OCR 로 구운 글자 검출**(결정 6 — 검출되면 재생성) · 알파 검사.

---

## 8. 검증

### 8-1. 합격 게이트 (Phase 1 부터)

| 게이트 | 기준(잠정) |
| :--- | :--- |
| 컴파일 | 오류 0 |
| 바인딩 | 계약의 필수 바인딩 전부 존재 · 타입 일치 |
| 텍스처 설정 | 압축 · 그룹 · 밉 · 스트리밍이 manifest 와 일치 |
| 화면 밖 | 0 — 1920×1080 + 21:9(2560×1080) · 16:10(1920×1200) 두 비율에서도 |
| 의도치 않은 겹침 | 0 — `allow_overlap` 밖에서 형제 위젯 bbox 교차 면적 > 4 % |
| 필수 요소 | brief 의 `required_elements` 전부 존재 |
| 배치 — 영역 | 최상위 영역 IoU ≥ 0.85 |
| 배치 — 말단 | 말단 위젯 IoU ≥ 0.70 · **48 px 미만은 중심점 거리 ≤ 8 px** |
| 구운 글자 | 생성 에셋 OCR 검출 0 |
| 수정 회귀(수정 모드) | patch 밖 위젯의 geometry 차이 ≤ 1 px · 스타일 spec 동일 |
| 왕복(Phase 1a) | spec → WBP → spec 이 정규화 후 같음 |

### 8-2. 기록만 (Phase 2 에서 보정 후 게이트로 올림)

| 지표 | 잠정 목표 | 비고 |
| :--- | :--- | :--- |
| 영역 대표색 ΔE00 | 평균 ≤ 10 | reference vs render, 영역 마스크 — **[1b 후속 C] 구현 · 기록:** `gen/fidelity.region_report`(영역 · 글자 · 게이지 전부, force_visible 렌더) → `style/<라벨>/report.json` · `report.recorded.style_review`. 글자는 획 상자(크기 · 중심) · 획 대표색 ΔE00 |
| 스타일 유사도 | 앵커 / style 이미지 대비 — 보정 뒤 결정 | 모델(CLIP · DINOv2 · 스타일 전용) 선택도 Phase 2 |
| component 유사도 | target 위젯 잘라낸 것 vs component 이미지 | |
| 전체 지각 유사도 | 기록만 | 글자 · 자리표시가 달라 게이트로 부적합 |

### 8-3. LLM verifier

- 별도 `claude -p` — 입력은 reference.png · render.png · spec(위젯 이름) · 실패 게이트 목록, 출력은 `fixes.json`(스키마: 위젯 · 문제 · 근거 · 제안 op). 합격 판정에는 쓰지 않는다.
- fix 단계가 fixes 를 spec patch 로 바꾼다. verifier 와 fix 를 나누는 이유: 보는 눈(비교)과 고치는 손(patch)을 분리해, verifier 가 자기 수정안을 변호하지 않게 한다.
- **두 가지 모드(1b 후속 C 에서 바뀜 — 예전 문구 'verifier 는 실패 게이트만 설명'):** ① 재시도 모드(1b-6) — 실패 게이트를 설명하고 고친다(`prompts/verifier.md` · `fix.md`). ② **외형 모드**(게이트를 모두 통과한 뒤) — 영역마다 '컨셉 | 렌더' 나란히 그림과 기록 지표(§8-2 — 장식선 F1 · 대표색 ΔE00 · 글자 획 상자 · 색)를 보고 보이는 외형 차이를 고친다(`prompts/style_verifier.md` · `style_fix.md`, 허용 op 는 외형만 · 가드 `style.guard_style_ops`). 두 모드 모두 합격 판정은 하지 않는다 — 외형 모드의 patch 도 게이트를 깨면 버려진다(§2-2 '통과 뒤 외형 라운드').

---

## 9. 안전장치 — 요구사항별 구현

| 요구 | 구현 |
| :--- | :--- |
| `/Game/_AutoGen/<run_id>/` 에만 생성 | `WidgetOutputPaths` 허용 목록 + 전역 더티 비교 — 기존 생성 가드 재사용 |
| 기존 에셋 덮어쓰기 · 삭제 금지 | `ProtectedPaths` · 덮어쓰기 거부 · 수정도 새 run 폴더 · 폐기는 저장 안 한 이번 run 패키지만 |
| 사전 검증 + 롤백 | preview / apply 분리 · 배치 원자성(되돌리기 저널 + `rollback_verified`) [소스] `Plugins/AnimGraphMcp/README.md:245-249` · 저장 지연 |
| 조회 뒤 변경 감지 | `expected_revision` = 정규화 spec 의 SHA1 → `REVISION_MISMATCH` |
| C++ 쓰기 | §3-3 소유 규칙 |
| 권한 허용 목록 | `claude -p "<프롬프트>" --permission-mode dontAsk` + `--allowedTools "Read" "Edit(work/<run_id>/**)"`(cwd 기준 상대 경로 — [P0 결과] 실측으로 밖 쓰기 거부 확인, §10-1) · Bash 없음 · `--strict-mcp-config` 로 MCP 없음. `--dangerously-skip-permissions` 금지 |
| 단계 상한 | `--max-budget-usd`(단계별) + 벽시계 타임아웃 + 재시도 N + run 당 codex 호출 상한 |
| Stop 훅 | 여러 파일을 쓰는 단계(normalize-text)만 — 출력 파일 검사, `stop_hook_active` 면 통과, 막을 때 exit 2 |
| 공식 CLI 만 | codex exec 만 · 내부 엔드포인트 호출 없음 · `OPENAI_API_KEY` 비움 · `--dangerously-bypass-approvals-and-sandbox` 금지 |
| 시크릿 | 브리지 토큰 헤더 · 환경 변수를 로그에서 가림 · `~/.codex/auth.json` 은 읽지 않음 |

---

## 10. `claude -p` 운용 · `.claude/` 구성

### 10-1. LLM 단계 호출 틀

```text
claude -p "<단계 지시>"
  --permission-mode dontAsk --allowedTools "<단계별 허용>"
  --strict-mcp-config --mcp-config config/empty_mcp.json
  --setting-sources project --settings claude_ctx/.claude/settings.json
  --output-format json --json-schema schemas/<stage>.json
  --max-budget-usd <단계별> --append-system-prompt-file prompts/<stage>.md
  [--model <pipeline.yaml 의 단계별 값 — 기본은 사용자 기본 모델>]
  --tools <허용 도구 이름> --allowedTools <단계별 허용>      ← [1b-1] 값이 여러 개인 옵션은 맨 뒤 · --tools 로 도구 정의 자체를 줄인다
  (cwd = Tools/uigen/claude_ctx, 벽시계 타임아웃은 오케스트레이터가)
```

- **[1b-1 실측]** `--json-schema` 는 인라인 JSON 만(파일 경로 거부) · 최상위 `$schema` · `$id` 는 빼고 넘긴다 · 최상위 allOf/anyOf/oneOf 는 API 400 — 자세한 것은 §11 '1b-1 에서 확인 · 정한 것'.

- [실측] 2.1.177 에 위 플래그가 모두 있다. `dontAsk` 는 허용 목록 밖을 묻지 않고 거부한다.
- `--bare` 는 훅 · auto-memory · CLAUDE.md 를 끄지만 **OAuth 를 읽지 않아(API 키만) 구독 인증이면 못 쓴다** [실측]. 대신 cwd 를 `claude_ctx/` 로 두고 auto-memory 를 settings 로 끈다(키 `autoMemoryEnabled` — [P0 결과]). 저장소 CLAUDE.md 는 상위 탐색으로 읽히는데 짧아서 감수한다.
- `--json-schema` 결과가 JSON 출력의 어느 필드에 담기는지 — [P0 결과] `structured_output`(아래).
- **[P0 결과] (11-14 — 바이너리는 2.1.177 에서, 런타임은 사용자 로그인 뒤 자동 업데이트된 2.1.325 · haiku 호출 3번, 합계 약 $0.02)**
  - **전제:** 독립 실행 `claude`(`~/.local/bin/claude.exe`)는 데스크톱 앱 인증과 따로 로그인해야 한다(Claude 구독 계정 — Console API 키를 고르면 토큰 과금). 로그인 전에는 `{"type":"result","is_error":true,"result":"Not logged in · Please run /login","total_cost_usd":0}` 을 돌려주고 끝난다(비용 0). 파이프라인 시작 검사에 넣는다. 자동 업데이트로 버전이 바뀌므로 `pipeline.yaml` 에 기대 버전을 적고 run 시작 때 `claude --version` 을 기록한다.
  - `--json-schema` 출력 **[실측]**: `--output-format json` 결과 `{"type":"result","subtype":"success","structured_output":{"answer":"ok","n":3},"result":"{…}"}` — 오케스트레이터는 `structured_output` 을 읽고, 없거나 `is_error` 면 실패 처리. [바이너리] 재시도 · 실패 표식 `structured_output_retries` · `structured_output_failure` 도 있다.
  - `--max-turns` **[실측]**: 동작한다(§1 #11 — `error_max_turns`).
  - auto-memory 끄기: 설정 키 **`autoMemoryEnabled: false`**(설정 스키마 · [바이너리]). 끈 효과 자체는 init 이벤트에 드러나지 않아 동작은 미관측 — 프롬프트 · 결과에 메모리 내용이 섞이는지는 Phase 1b 첫 run 에서 본다.
  - **`--setting-sources project` = cwd [실측]:** cwd(저장소 안 `…/claude_ctx/`)의 `.claude/settings.json` 에 둔 `deny: ["Read(note.txt)"]` 가 걸렸다(`File is in a directory that is denied by your permission settings.`) — 저장소 루트 설정에는 없는 규칙이다. 루트 설정이 **같이** 읽히는지는 이 시험으로 가를 수 없다 → 계획대로 단계 권한은 `--settings` · `--allowedTools` 로 명시하고 루트 설정에 기대지 않는다.
  - **경로 권한 규칙 [실측]:** `--permission-mode dontAsk --allowedTools "Edit(work/**)"` 에서 `Write` 로 `work/inside.txt` 는 써지고 cwd 의 `outside.txt` 는 `Permission to use Write has been denied because Claude Code is running in don't ask mode` 로 막혔다 — **상대 경로는 cwd 기준**이고 `Write` 도 `Edit(path)` 규칙으로 판정된다(설정 스키마의 `Write(path)` 무시와 일치). → 단계 허용은 `--allowedTools "Read" "Edit(work/<run_id>/**)"` 로 충분, PreToolUse 경로 훅은 대비책으로만. 거부 메시지가 '다른 도구로 해 봐도 된다'고 유도하므로 Bash 등은 허용 목록에 넣지 않는다(설계 그대로).
  - **함정 [실측]:** `--allowedTools` 는 값을 여러 개 받는 옵션이라 뒤에 오는 위치 인자(프롬프트)까지 도구 이름으로 삼킨다 → 프롬프트는 `-p "<프롬프트>"` 처럼 맨 앞에 두거나 stdin 으로 준다. `--output-format stream-json` 의 마지막 줄은 결과가 아니라 `system/task_summary` 일 수 있어 `type:"result"` 를 찾아 읽는다.

### 10-2. `.claude/` 구성

| 위치 | 구성 | 용도 |
| :--- | :--- | :--- |
| 저장소 `.claude/skills/` | `ue-umg-authoring` — GUID 맵 · FWidgetRenderer · 텍스처 설정 · BindWidget · UHT 헤더 이름 등 부딪힌 엔진 제약 | 개발 세션(플러그인 구현) |
| 저장소 `.claude/skills/` | `uigen-run` — 파이프라인 돌리는 법 · 리포트 읽는 법 · 에디터 주기 | 개발 · 운용 세션 |
| 저장소 `settings.local.json` | `run_pipeline` · pytest 실행 허용 규칙(CLAUDE.md 의 모양 규칙대로) | 프롬프트 없이 돌게 |
| `Tools/uigen/claude_ctx/.claude/settings.json` | 권한(Bash 거부 · 쓰기 경로 제한) · auto-memory 끔 · Stop 훅 등록 | LLM 단계 |
| `Tools/uigen/claude_ctx/.claude/skills/` | `uigen-spec` — spec 어휘 · 프로필 규칙 · 좌표 규약 | analyze · fix |
| `Tools/uigen/claude_ctx/.claude/hooks/` | `check_outputs.py`(Stop) | normalize-text |
| agents | 두지 않는다 — verifier 는 별도 호출, 서브에이전트는 사용자 요청 때만(프로젝트 방침) | |

기존 스킬 3종(`astral-ue-*`)은 Python 원격 실행에 기대는데, 에디터 안 원격 실행은 지금 불통이다(프로젝트 실측). 파이프라인은 HTTP 브리지만 쓴다.

---

## 11. Phase 계획

| Phase | 내용 | 끝 조건 | 검증 |
| :--- | :--- | :--- | :--- |
| **0** | (a) 플러그인 분리 §3-1 — 코어 추출 → StateTree 이전, WidgetMcp 는 뼈대만(스파이크 코드를 둘 자리) (b) 스파이크: codex 설치 · 1장 생성 · 결과 찾기 · 한도 메시지 / `claude -p` 플래그 · 스키마 출력 필드 · 경로 권한 규칙 · auto-memory 끄기 / 손 spec 으로 WBP 생성 · `ConstructWidget` · 렌더 · geometry / 텍스처 임포트 설정 / 새 WBP 기본 루트 | 기존 회귀 통과 + 스파이크 보고(§12 가정 확정) | 빌드 2회 · `AnimGraphMcp.*` · pytest · 통합 1개 |
| **1a** | 손으로 쓴 M4 HUD spec → codegen → build → verify → 재시도, procedural 에셋만. 역추출 왕복 · JSONL 기록 시작 | 게이트 통과 · 왕복 일치 · codegen 해시 건너뛰기 확인 | pytest + 에디터 1회 실행 |
| **1b** | M4 HUD 컨셉아트 → analyze → codex 에셋 → 끝까지 1회 성공 | 무인 1회 통과 + 리포트 | 실제 run · 사람 눈 확인(화면) |
| → M4 C | 스텁 `UAstralCombatHUDWidget` 에 게이지 · 체인 연결(개발 세션) | M4 설계 §5 화면 동작 | M4 방침 |
| **2** | 집계 스크립트 + 임계값 보정(HUD · 장비창 · 옵션 5 ~ 10장) | 기록 지표 중 게이트로 올릴 것 결정 | 보정 리포트 |
| **3** | text · multi_ref(목업 K장 · 선택) + 리스트 · 표준 컨트롤 · 하위 WBP | 각 모드 1회 통과 | 실제 run |
| **4** | 수정 모드 — 지시 해석 · 주석 스크린샷 → 위젯 매핑(렌더 geometry 로) · lineage · 되돌리기 · 승격 | 수정 회귀 게이트 통과 | 실제 run |
| **5** | ComfyUI 연결 · 아이콘만 codex 와 A/B | A/B 리포트 | 실제 run |
| **6** | 지표 기반 라우팅 규칙(종류별 최소 표본 수 넘을 때만) | 규칙 반영 | 리포트 |

**Phase 1a 하위 단계 (11-14 사용자 승인 — 단계마다 보고 → 승인 뒤 다음)**

| 단계 | 범위 | 단계 검증 | 상태 |
| :--- | :--- | :--- | :--- |
| 1a-1 | `Tools/uigen` 뼈대 · JSON Schema 6종 · 설정 · `profiles/hud` · 손 brief/spec(`fixtures/m4_combat_hud`) · spec 정규화 · 왕복 비교 · patch · procedural PNG · run 잠금 · 지표 JSONL · `.gitignore` 3줄 | pytest | **끝(11-14)** — pytest 76 통과, 손 spec run 이 normalize → generate → refine 까지(나머지는 미구현 표시로 incomplete) |
| 1a-2 | WidgetMcp 도구 — 텍스처 임포트 경로 확인(첫 작업) → create → 조정기 preview/apply · patch → export → compile · list_bind_widgets → render(감마 LUT · 3 해상도) → save · discard, `quit_editor` 선택 인자, `widget_mcp` 창구 | DebugGame 빌드 + `WidgetMcp.*` + 브리지 스모크 | **끝(11-14)** — Tool 11개, `WidgetMcp.*` 5/5, 손 spec 스모크(왕복 차이 0 · bbox 오차 0 px · 3 해상도 화면 밖 0), `quit_editor` 두 경로 확인 |
| 1a-3 | codegen(템플릿 · 계약 해시 · 소유 규칙) · UBT 빌드 · 에디터 재기동 | pytest + 실제 생성 · 빌드 1회 + 같은 spec 건너뜀 | **끝(11-14)** — pytest 96 통과(codegen 20). 실제 run: C++ 4개 생성 → DebugGame 빌드 22.4초(`Result: Succeeded`) → 재기동(브리지 12.4초 + 30초) → `list_bind_widgets` = 계약 8개. 같은 spec 재실행은 codegen `skipped`(0.46초, 빌드 · 재기동 없음). 같은 에디터에서 스텁 부모 WBP 생성 `compile.ran=false` → spec 적용 컴파일 ok · `missing_bindings` 0 · 왕복 일치 → 폐기 |
| 1a-4 | verify 게이트 · 재시도 분기(결정적 fixer) · finalize · report · 지표 | pytest + 깨뜨린 run 1회가 재시도로 통과 | **끝(11-14)** — pytest 142 통과(새 46: 게이트 계산 · fixer · 재시도 분기 · 조기 종료 · 상한 · generate/codegen 분기 · 가짜 claude CLI). 실제 run(DebugGame 에디터 — build 가 기동, 브리지 12.8초 + 30초): 손 spec 첫 시도 게이트 10/10 · 왕복 일치 · `Content/_AutoGen/<run_id>/` 4개 저장 · 지표 줄(`R20261114_235335`). `--inject-fault offscreen`(`R20261114_235343`) · `overlap` · `drift` 모두 시도 1 실패 → 정정 patch 1 op → build → 시도 2 통과 · 저장. 첫 offscreen run 은 컬링 함정(아래)으로 조기 종료 · 폐기 — 고친 뒤 통과 |
| 1a-5 | Phase 끝 검증(빌드 2 · 에디터 1회 · pytest · 색 눈 확인) · 문서 | 끝 조건 4개 | **끝(11-15)** — 빌드: DebugGame `Result: Succeeded`(이미 최신) · Development `-DisableAdaptiveUnity` `Result: Succeeded`(26.6초 · 18 작업 · 적응형 제외 0 — 새 cpp 를 유니티 묶음에 넣어도 충돌 없음). pytest 142 통과. 에디터 1회(DebugGame): `AstralBreak.` 55/55(먼저, 415초) → `EditorMcpCore.` 2/2 · `WidgetMcp.` 5/5 → 정상 run `R20261115_001147` 시도 1 에 게이트 10/10 · 왕복 일치 · codegen `skipped` · 지표 4줄(아래 요약) → `quit_editor` · 소멸 확인. 렌더 색 사람 눈 통과(§12-1) |

1a-1 에서 정한 구체 규칙(설계 초안 §4 를 구체화한 것):
- **spec 브러시 모양:** `{draw_as: image|box|border|rounded_box|none, asset?, color(틴트), margin?(9-slice), image_size?, radius?, outline_color?, outline_width?}` — §4-3 예시의 `fill.procedural{kind: rounded_box}` 대신 `fill: {draw_as: rounded_box, color, radius}`. 텍스처 없는 procedural 채움은 브러시 자체가 담는다.
- **슬롯 kind 는 부모 타입이 정한다** — `canvas` · `overlay` · `vertical_box` · `horizontal_box` · `uniform_grid` · `border` · `size_box` · `button`(Border · SizeBox · Button 의 자식 슬롯도 따로 둔다).
- **정규화 기본값:** 생략한 스칼라 = `core/spec.py` 표(5.7.4 UMG 생성자 기본값 — 예: Border 슬롯 padding (4,2) `BorderSlot.cpp:18`, Overlay 슬롯 Left/Top `OverlaySlot.cpp:15`, 박스 슬롯 Automatic `VerticalBoxSlot.cpp:19`, TextBlock Roboto 24 Bold `TextBlock.cpp:35`), 생략한 브러시 = 엔진 기본 스타일(CDO). 파이프라인은 정규화한(전부 명시한) spec 을 브리지에 보내므로 표와 엔진 값이 어긋나도 파이프라인 왕복은 깨지지 않는다. 브러시 `image_size` 기본 = 그 에셋 크기(9-slice 두께가 이 값에 달려 있다).
- **왕복 투영:** `bbox_intent` · `binding` · `note` 는 WBP 가 담지 않아 뺀다. 글자는 정적/동적 구분 없이 값(동적이면 sample)만. 역추출의 브러시 asset(UE 경로)은 manifest `ue_path` 로 asset_id 에 되돌려 비교.
- **겹침 게이트:** Overlay 자식끼리는 겹치는 것이 정의라 빼고(`profiles/hud.yaml stacking_parents`), '48 px 미만' = min(w, h) < 48.
- **지표 JSONL** 은 성공 · 실패 · 미완 모든 run 끝에 run 한 줄 + manifest 에셋마다 한 줄(1a-1 부터 기록 중).

1a-2 에서 확인 · 정한 것 (11-14):
- **텍스처 임포트 경로 [실측]:** Interchange `ImportAssetWithResult` 는 동기다(`InterchangeManager.cpp:1720-1726`). PNG 는 기본 'Textures' 스택(`/Interchange/Pipelines/DefaultTexturePipeline`, `UInterchangeGenericTexturePipeline`)을 탄다. **함정: 그 파이프라인의 `bAllowNonPowerOfTwo` 기본값이 false** 라 200×50 같은 UI 텍스처를 걸러 낸다(`InterchangeGenericTexturePipeline.h:70`) → 트랜지언트로 복제해 true · 노멀맵 감지 끔 · UDIM 끔 · `AssetName` 지정. 임포트 뒤 압축 · 그룹 · 밉 · NeverStream · sRGB 를 넣고 `PostEditChange` + `FTextureCompilingManager::FinishCompilation`(렌더 전에 빌드를 끝낸다). 손 spec 의 3장: 200×50 · 320×160(BC7) · 256×32 모두 크기 유지 · 설정 manifest 와 일치, 한 장 0.01초.
- **조정기 적용 방식(설계 §6 '되돌리기 저널' 대신):** WidgetTree 를 트랜지언트로 복제해 거기에 적용 → 사본을 역추출해 정규화한 목표와 같은지 확인 → 같을 때만 WBP 의 WidgetTree 와 바꿔 끼우고 GUID 맵을 이름 차이로 맞춘다. 실패하면 원본을 손대지 않아 `rollback_verified`(revision 불변)가 구조로 보장된다. 지운 위젯은 트랜지언트 패키지로 이름을 옮겨 같은 이름을 다시 쓸 수 있게 한다.
- **revision** = (부모 클래스 경로 + 역추출 트리)의 정규 JSON(키 정렬 · 수 소수 셋째 자리) SHA1. 같은 spec 을 다시 적용하면 op 0 · revision 그대로(멱등) [실측].
- **`quit_editor` 선택 인자 `discard_only_under`**(패키지 접두 배열): `discard_dirty` 와 함께 주면 그 밖의 더티가 하나라도 있을 때 `DIRTY_PACKAGES`(details `outside_discard_only_under`)로 거절. 인자가 없으면 기존 동작 그대로. 파이프라인은 `pipeline.yaml editor.quit_discard_only_under: [/Game/_AutoGen/]` 를 넘긴다.
- **생성 때 컴파일:** 부모에 필수 BindWidget 이 있으면(스텁) 빈 캔버스는 컴파일될 수 없으므로 건너뛰고 `compile.ran=false` — apply 가 컴파일한다.
- **렌더 [실측]:** 1920×1080 에서 손 spec 위젯 14개 geometry 가 `bbox_intent` 와 오차 0 px, 2 · 3 해상도(2560×1080 · 1920×1200)에서 화면 밖 0, 그림 1 · 2 픽셀 차이 0. 색 탐침: 배너 `#2A1A0ACC` 를 검은 바탕에 얹은 값 `#221508` 이 그대로 나옴(감마 LUT 확인). 1920×1080 세 장 0.2초.
- **함정 [실측]:** UE 전역 `MakeError`(TValueOrError) 템플릿이 ADL 로 같은 이름의 우리 함수를 이긴다 → `MakeMcpError`. `PI` 는 엔진 매크로라 변수 이름으로 못 쓴다.

1a-3 에서 확인 · 정한 것 (11-14):
- **계약:** 바인딩마다 `{name, widget_class, data, kind, format?, optional, setter}` + 모듈 · 클래스 이름 + 생성기 식별자(버전 + 템플릿 4개 · setter 조각의 해시 — 템플릿이 바뀌어도 다시 생성). 해시 = 정규 JSON 의 SHA1. 생성 헤더 1줄째 표식, 2줄째 해시, 3줄째 계약 JSON(다음 run 의 '추가만' 판정 원천), cpp 는 표식 + 해시. 해시 줄과 계약 줄이 어긋나면 `CODEGEN_HEADER_CORRUPT`.
- **추가만 구체화:** spec 에서 빠진 바인딩은 `BindWidgetOptional` + setter 유지. 같은 이름의 위젯 클래스가 바뀌면 거부(`BINDING_RETYPE` — 옛 WBP 는 이름으로 묶임). data · kind · format 변경은 허용(setter 가 바뀐다 — 스텁이 옛 setter 를 부르면 빌드가 실패해 원복된다). setter 의 정체성은 data id — 같은 data 를 새 바인딩이 쓰면 빠진 쪽은 setter 를 잃는다(위젯 이름을 바꿔도 사람 코드의 `SetX` 가 새 위젯을 움직임). setter 이름 · 위젯 이름 충돌은 거부.
- **setter 세부:** flag 보이기 = `SelfHitTestInvisible`(Button 만 `Visible`) · 숨김 = `Collapsed`. number `0` = `int32` · 자릿수 묶음 없음, `0.0…` = `float` · 소수 자릿수 최소 = 최대. progress 는 0 ~ 1 로 자른다. 전부 `UFUNCTION(BlueprintCallable, Category="uigen|<화면>")` · 선택 바인딩 대비 null 검사. 매개변수 이름이 `UUserWidget` · `UWidget` · `UVisual` 멤버와 겹치지 않음을 엔진 헤더로 확인(가림 경고 = 오류).
- **건너뛰기:** 해시가 같고 스텁이 있으면 건너뛴다. 에디터가 떠 있으면 `list_bind_widgets` 로 리플렉션만 대조하고, 다르면(낡은 바이너리) 쓰기 없이 빌드 · 재기동(`reason: stale_binary`).
- **원복 범위:** 에디터 종료는 쓰기 전에 한다. 쓰기부터 빌드 성공 전까지의 모든 실패(종료 거절 · 남은 에디터 프로세스 · 빌드 실패 · Ctrl+C)는 덮어쓴 파일을 `codegen/backup/` 에서 되돌리고, 새로 만든 파일은 지우는 대신 `codegen/failed/` 로 옮긴다(실패한 판 보존). 빌드가 성공한 뒤의 실패(기동 · 브리지 · 계약 불일치)는 되돌리지 않는다 — 바이너리가 새 코드라 소스가 그것과 같아야 한다.
- **그 밖의 검사:** 헤더 이름 중복(모듈 전체) · `screens.yaml` 이름 규칙(식별자 · ViewBase/Widget 접미사) · brief `binding_contract.class` = `U<Widget>`. 파일은 CRLF · UTF-8(BOM 없음) — 작업 트리(`text: auto` · autocrlf)와 같게.
- **설정 · 기록:** `pipeline.yaml` 에 `codegen` 절(module · api_macro · module_root · ui_dir) · `editor.args` · `build.args`(`-WaitMutex -NoHotReload`). `codegen.json` 스키마 추가(7종), `report.json` 에 codegen 요약, `run_pipeline --module-root`(시험용). 에디터는 떼어 내 기동(DETACHED · 새 프로세스 그룹, 가능하면 job breakaway), 표준 출력은 `codegen/editor.log`.
- **[실측]** 적응형 유니티가 새 cpp 2개를 유니티 묶음에서 뺐다(`[Adaptive Build] Excluded from AstralBreak unity file`) — 묶음 충돌은 1a-5 의 `-DisableAdaptiveUnity` 에서 본다. DDC 가 따뜻하면 브리지 준비가 12초대였다.

1a-4 에서 확인 · 정한 것 (11-14):
- **재시도 루프:** 시도 k 는 `specs/00k.json` 을 쓰고, 실패하면 fix 가 `patches/00k.json`(source fix)을 낸다. `--inject-fault` 의 결함도 같은 patch 모양(`patches/000.json`, source fault)으로 normalize 뒤에 적용한다. 재시도 N = 3 → 시도는 최대 4번. '실패 게이트 집합이 줄었다' = 직전 집합의 진부분집합 — 아니면 무진전, 두 번 연속이면 `NO_PROGRESS` 로 끝. fixer 가 op 를 하나도 못 내면 바로 `NO_FIX`. 끝나면 finalize(실패 = 폐기). **[실측]** 첫 offscreen run 이 아래 컬링 함정으로 시도 3 에서 `NO_PROGRESS` 로 멈추고 run 패키지를 폐기했다(안전장치 동작 확인).
- **build:** 에디터가 없으면 `core.ue.Toolchain` 으로 띄운다(로그 `build/editor_00k.log`). 텍스처는 manifest 의 `ue_path` 가 빈 에셋만 임포트한다(첫 시도는 전부, generate 로 다시 만든 에셋은 refine 이 비운다). 이름은 `T_<asset_id>`, 같은 에디터 세션에서 다시 임포트하면 `T_<asset_id>_2` …(임포트는 덮어쓰기를 거부). `ue_path` = 패키지 경로. WBP 이름은 `screens.yaml` 의 `wbp`(없으면 `WBP_<화면 ID>`), 생성은 첫 시도에만. 에디터 세션(`process_id`)이 지난 build 와 다르면(codegen 재기동이 저장 안 한 패키지를 버림) 처음부터 다시 만든다. `build.json` = 지금 상태(WBP · revision · 세션 · 텍스처 이름) + 시도별 op.
- **verify 게이트 세부:** 기준 해상도 = spec.canvas. 영역 = 루트 Canvas 직계, 말단 = 자식 없는 위젯, 둘 다면 영역(더 엄격), 그 사이(박스)는 기록만(`report.recorded.placement_inner`). 바인딩 = `missing_bindings` 0 + `list_bind_widgets(WBP)` = `codegen.json` 계약. 텍스처 = export `textures[]` ↔ manifest(압축은 manifest, 그룹 · 밉 · 스트리밍 · sRGB 는 `pipeline.yaml textures`), 크기 차이는 기록만. 왕복 = `roundtrip_equal` + GUID 맵 누락 0. 렌더가 안 되면(컴파일 실패 등) 렌더 게이트 넷을 오류와 함께 실패로 남긴다. 사람 눈용 `render_sample.png` 는 brief sample 을 overrides 로(보이기 규칙 그대로) — 게이트와 무관.
- **[실측] 컬링 함정:** Slate 는 그리기(클립) 영역 밖으로 완전히 나간 위젯을 그리지 않는다(패널 자식 컬링). 그 위젯과 자식의 페인트 공간 geometry 는 기본값 `(0, 0, 0, 0)` 으로 남고 `visible` 은 true 다. 처음에는 화면 밖 게이트가 이를 '크기 0' 으로 건너뛰었고(IoU 게이트만 실패), fixer 가 0 을 측정값으로 써서 크기를 두 배로 키웠다. → 그려지지 않은 보이는 위젯 = 화면 밖 실패(`not_painted`), fixer 는 그때 측정값 대신 루트 bbox · 앵커 · 정렬로 `bbox_intent` 자리를 계산한다. 부분적으로 걸친 위젯은 그려지고 실제 좌표가 나온다. 가짜 에디터(pytest)도 같은 컬링을 흉내 낸다.
- **결정적 fixer:** 배치 게이트(offscreen · overlap · iou_region · iou_leaf)에서 실패한 위젯마다 자신 또는 가장 가까운 캔버스 슬롯 조상(영역)을 점 앵커일 때만 고친다 — `position += d + alignment × dsize`, `size += dsize`(d = `bbox_intent` − 측정). 영역이 이미 제자리(≤ 0.5 px)면 안쪽 문제로 보고 op 없음. 겹침은 `bbox_intent` 에서 벗어난 쪽만, 둘 다 제자리면 제안만. 텍스처 설정 불일치 = `replace_asset(regenerate)` → generate 분기(새 이름으로 다시 임포트). compile · bindings · required_elements · roundtrip 은 op 없음(1b LLM 몫).
- **finalize:** 통과 = `save_widget_run` + `lineage.json`(최종 spec 파일 · sha256 · 시도 · 결함 · patch 목록 · 텍스처 · 저장 패키지 · 계약 해시 · revision). 실패 · 오류 = `discard_run_packages`(`--keep-failed` 면 저장 + lineage `status: fail`). build 전에 끝난 run 은 할 일 없음(단계 기록도 없음), `--until` 은 finalize 를 하지 않는다(패키지는 에디터에 저장 안 된 채). 에디터 세션이 바뀌었으면 패키지는 이미 사라진 것으로 본다. 파이프라인은 끝나도 에디터를 내리지 않는다(다음 run 이 재사용).
- **report · 지표:** report 에 `attempts[]`(spec · 실패 게이트 · patch · 분기 · 멈춘 이유) · `fault` · `finalize` · `artifacts` · `verify` 를 더했다(스키마 9종 — `build` · `lineage` 추가). 지표 run 줄 = `status`(run 결과) + `verify`(마지막 verify 의 게이트 결과, 돌지 않았으면 null) + `failed_gates` · `fault` · `retries`(시도 − 1). 에셋 줄의 `retries` = 그 에셋을 다시 만든 횟수.
- **LLM 호출 틀(1b 용, 1a 호출 0):** `core/llm.py` — 프롬프트는 `-p` 바로 뒤, `--allowedTools` 는 맨 뒤, `--json-schema` 는 인라인 JSON(파일 경로가 아님 — 1b 첫 실제 호출에서 확인), `--max-budget-usd` + 숨은 `--max-turns`, cwd `claude_ctx/`, stdin 닫음, 환경에서 `ANTHROPIC_API_KEY` 제거, `--dangerously-skip-permissions` · `--bare` 거부. 단계 출력은 structured_output 으로만 받으므로 허용 도구는 `Read` 하나(§9 표의 `Edit(work/<run_id>/**)` 는 필요 없어 뺐다 — 파일은 오케스트레이터가 쓴다). `claude_ctx/.claude/settings.json`(Bash · 쓰기 · 웹 거부, auto-memory 끔) · `prompts/verifier.md` · `fix.md` · `config/empty_mcp.json`. pytest 는 가짜 CLI 만(실제 CLI 는 conftest 가 막음).
- **손 spec 글자 정렬(선택 항목):** 박스 칸의 글자 5개를 `v_align: center` 로 바꾸고 `bbox_intent` 를 실측 글자 상자로 맞췄다. **[실측]** 엔진 기본 글꼴(Roboto + 한글 대체)의 줄 높이 ≈ 글꼴 크기 × 1.6(16→26 · 18→29 · 26→42 · 30→48), 칸보다 크면 칸 높이(34 → 50). 값은 잠정.

**Phase 1a 결과 요약 (11-15, 1a-5 정상 run `R20261115_001147_CombatHUD` — DebugGame 에디터, 자동 시험 뒤 같은 에디터)**

| 끝 조건 | 판정 | 숫자 |
| :--- | :--- | :--- |
| 게이트 통과 | 충족 | 시도 1 에 10/10 — compile 오류 0 · bindings 누락 0 · texture_settings 불일치 0 · offscreen 0(3 해상도) · overlap 0(기준 0.04) · required_elements 누락 0 · iou_region 최소 1.0(영역 4개 · 중심 0 px) · iou_leaf 최소 1.0(말단 7개 · 중심 0 px) · baked_text 건너뜀(procedural — 통과 + 이유) · roundtrip 0. 결함 주입 3종(1a-4: offscreen · overlap · drift)은 모두 시도 2 통과 |
| 왕복 일치 | 충족 | `roundtrip.equal` true · 차이 0 · GUID 누락 0 · unsupported 0 · 역추출 revision `sha1:fd6614d5…` = build revision |
| codegen 해시 건너뛰기 | 충족 | 계약 `sha1:5ae0d80a…` 같음 → `skipped`(`contract_unchanged`) · 빌드 안 함 · 떠 있는 에디터 리플렉션 대조 일치(바인딩 8개) · 0.63초. (1a-3: 첫 생성 · 빌드 22.4초 · 재기동 → 같은 spec 재실행 0.46초 건너뜀) |
| JSONL 기록 | 충족 | `metrics/uigen.jsonl` 에 run 1줄(`status: pass` · `verify: pass` · `retries` 0 · `failed_gates` [] · 4.15초) + 에셋 3줄(procedural · `retries` 0). 1a 동안 run 12개 · 48줄 |

- run 시간 4.15초 = normalize 0.01 · codegen 0.63 · generate 0.11 · refine 0.02 · build 0.98(텍스처 3장 임포트 · WBP 생성 · apply 13 op) · verify 1.56(렌더 3 해상도 + sample) · finalize 0.82(패키지 4개 저장). 에디터 기동 · 빌드가 없는 경우의 값이다.
- 생성 C++(`Source/AstralBreak/UI/HUD/`)은 1a-3 의 첫 생성 이후 바뀌지 않았다(git 상태 run 전후 같음).
- **증거 run(11-15 정리 뒤 — 사용자 결정):** `R20261115_001147_CombatHUD`(1a-5 정상 · 눈 확인한 WBP) · `R20261114_235343_CombatHUD`(1a-4 offscreen 결함 → 재시도 통과)만 `Tools/uigen/work/` 와 `Content/_AutoGen/` 에 남겼다(둘 다 git 무시). 위 표 · 단계 기록의 다른 run 이름은 기록으로만 남는다(폴더는 휴지통). `metrics/uigen.jsonl` 은 지운 run 의 줄까지 그대로 둔다.

**1b 로 넘길 것 (1a-5 정리)**
- **`claude -p` 첫 실제 호출에서 채록:** `--json-schema` 값 형식(1a 틀은 인라인 JSON) · 결과의 `structured_output` 모양 · `--max-budget-usd` 예산 끊김 메시지 · 종료 코드 — 그 뒤 단계 상한 값(예산 0.5 USD · 턴 8/6 · 300초, 잠정)을 다시 본다.
- **프로젝트 폰트 결정 · 내려받기 승인**(§12-2 4 — Pretendard / Noto Sans KR). 정하면 spec `font.family` 를 채우고 줄 높이(1a 실측 × 1.6 은 엔진 기본 글꼴 값)를 다시 잰다.
- **OCR 엔진 선택** — `baked_text` 게이트는 1a 에서 한 번도 돌지 않았다(procedural 은 글자를 그리지 않음). 생성 이미지가 들어오는 1b 에서 처음 돈다.
- **재시도 codegen 분기의 실제 경로**(정정 patch 가 바인딩을 바꿈 → 에디터 내리기 → 빌드 → 재기동 → 세션이 바뀌어 build 처음부터) — 1a 는 pytest(가짜 도구 사슬)로만 확인했다. 계약을 바꾸는 결함이 생기면(또는 1b LLM fix 가 바인딩 op 를 내면) 실제로 확인한다.
- 원래 1b 몫: 컨셉아트(§12-2 3) · analyze 의 장면 / UI 가르기(A8) · codex 한도 이벤트 모양(A3 — 걸렸을 때 채록).

**Phase 1b 하위 단계 (11-15 사용자 승인 — 단계마다 보고 → 승인 뒤 다음)**

| 단계 | 범위 | 단계 검증 | 상태 |
| :--- | :--- | :--- | :--- |
| 1b-1 | `claude -p` 첫 실제 호출 채록 → `core/llm.py` · 가짜 CLI 보정 · run 시작 검사(`preflight`) | pytest + haiku 호출 몇 번 | **끝(11-15)** — 채록 11건(아래) · pytest 150 통과 |
| 1b-2 | codex 생성기 `gen/codex.py`(한 번에 하나 · stdin 닫기 · `OPENAI_API_KEY` 제거 · 버전 · `thread_id` 로 결과 찾기 · 한도 판정 → `quota` · run 당 20회 · `-i` 참조 이미지) → 그것으로 컨셉아트 1장 | pytest(가짜 codex) + 실제 1 ~ 2회 · 컨셉 눈 확인 | **끝(11-15, 컨셉 사람 눈 통과)** — pytest 163 통과 · 실제 1회로 컨셉 생성(아래) |
| 1b-3 | RapidOCR 설치 · Pretendard Regular · Bold 내려받기 · 폰트 임포트 Tool(`FontOutputPaths=/Game/UI/Fonts/`) · 줄 높이 재측정 | DebugGame 빌드 + `WidgetMcp.*` + 폰트 렌더 | **끝(11-15)** — 설치 · 내려받기 승인 각 1회, DebugGame `Result: Succeeded`, `WidgetMcp.*` 6/6, `F_Pretendard` 저장 · 렌더(아래) |
| 1b-4 | normalize(concept) + analyze(A8) — `--concept` · `--inputs`, 바인딩 8개 · 위젯 이름 고정(계약 같음 → codegen 건너뜀), `prompts/analyze.md`, 검사 실패 시 1회 재요청 | pytest + 실제 analyze 1 ~ 2회 · bbox_intent 겹친 그림 눈 확인 | **끝(11-15, 겹침 그림 사람 눈 대기)** — pytest 180 통과 · 실제 run `R20261115_014638` analyze 통과(호출 2 · 0.43 USD 환산 · 87초) |
| 1b-5 | generate(codex 연결) + refine(배경 제거 · 여백 자르기 · 크기 맞춤 · 9-slice 추정 · OCR → 그 에셋 재생성) | pytest(합성 이미지) + 실제 `--until refine` 1회 → **사용자 요청으로 build · verify 까지(첫 컨셉 WBP)** | **끝(11-15, 렌더 사람 눈 대기)** — pytest 190 통과 · 실제 run `R20261115_015927` 끝까지(게이트 8/10, `--keep-failed` 저장) |
| 1b-6 | LLM verifier · fix 를 재시도에 연결(`fix.mode: hybrid`) · `llm.jsonl` · 바인딩 op → codegen 분기 | pytest + 실제 결함 주입 1회 | **끝(11-15)** — pytest 198 통과 · 실제 `R20261115_021926`(shrink_text) 시도 2 에 10/10 · LLM 2호출 |
| 1b-7 | 끝 run · 컨셉 ↔ 렌더 사람 눈 · Phase 끝 회귀 · 문서 · 정리 | 끝 조건 | **끝(11-15, 정리 완료 · 렌더 사람 눈 대기)** — 끝 run `R20261115_024358` 무인 1회 통과 · 빌드 2구성 · 에디터 시험 · pytest 198(아래 'Phase 1b 결과 요약') |

1b 착수 때 정한 것(11-15 사용자 — 전부 추천안): 컨셉아트는 codex 로 1장 생성(원래 text 모드 성격 — 나중에 사람 그림으로 바꿔 다시 돌릴 수 있다) · 파일은 `Tools/uigen/fixtures/m4_combat_hud_concept/`(concept.png + inputs.yaml, git 추적 — 커밋은 사용자) · 폰트 Pretendard Regular · Bold(spec 굵기 어휘 regular · bold · light 를 바꾸지 않음) · 폰트 임포트는 WidgetMcp Tool + 별도 허용 경로(설계 §6 '쓰기는 `/Game/_AutoGen/` 만'의 예외 — 폰트 패키지만 저장) · OCR = RapidOCR · 상한 = codex run 당 20 · verifier/fix 0.5 USD · 턴 8/6 · 300초 그대로 + analyze 1.0 USD · 턴 6 · 600초(잠정) · fix = hybrid(결정적 fixer 먼저, op 를 못 내면 LLM verifier → fix — §8-3 보완) · analyze 지침은 스킬(§10-2 `uigen-spec`) 대신 `prompts/analyze.md` 를 명시적으로 준다 · 1b-6 에서 LLM fix 경로 실제 확인용 결함 주입 run 1회.

1b-1 에서 확인 · 정한 것 (11-15, `claude` 2.1.325 · 독립 CLI 로그인 = 구독 `claude.ai` · 채록 11번 — haiku 10번 합계 약 0.05 USD 환산 + 기본 모델 1번 0.05 USD):
- **`--json-schema` 형식 [실측]:** 인라인 JSON 만 받는다 — 파일 경로를 주면 stderr `Error: --json-schema is not valid JSON` · 종료 1 · stdout 없음(→ `LLM_NO_RESULT`). 최상위 `"$schema": ".../draft/2020-12/schema"` 가 있으면 CLI 검사기가 거부한다(`no schema with key or ref …` · 종료 1) → `cli_schema` 가 최상위 `$schema` · `$id` 를 빼고 넘긴다. 스키마는 StructuredOutput 도구의 input_schema 가 되므로 **최상위 allOf/anyOf/oneOf 는 API 400**(`input_schema does not support oneOf, allOf, or anyOf at the top level` — subtype `success` + `is_error` + terminal_reason `api_error` · 비용 0 · 종료 1) → 호출 전에 `LLM_SCHEMA_UNSUPPORTED` 로 거부, `type: object` 도 요구. 안쪽 `$defs` · `$ref`(42개) · allOf-if-then 은 된다 — **spec 스키마 통째로 통과**하고 결과가 로컬 검사(`core.schema`) 오류 0.
- **결과 모양 [실측]:** `{"type":"result","subtype":"success","is_error":false,"terminal_reason":"completed","stop_reason":"tool_use","num_turns":2~4,"structured_output":{…},"total_cost_usd":…,"modelUsage":{"<모델 id>":{inputTokens · outputTokens · cacheReadInputTokens · cacheCreationInputTokens · thinkingTokens · costUSD · costBasis:"list"}},"usage":{…},"permission_denials":[],"session_id":…}` — 결과 이벤트에 `credential_expires_at` 같은 필드도 있어 run 기록에는 고른 필드만 옮긴다(`usage_summary` → `model` · `tokens`). `total_cost_usd` 는 API 정가 환산값이다(구독이라 실제 과금은 아님 — 상한의 단위).
- **예산 끊김 [실측]:** subtype `error_max_budget_usd` · terminal_reason `budget_exhausted` · `errors: ["Reached maximum budget ($0.0001)"]` · 종료 1 · `structured_output` 없음(→ `LLM_BUDGET`). **예산은 턴 사이에 검사한다** — 0.0001 상한에 0.0019 를 썼다(이미 시작한 턴은 끝까지). 상한은 '한 턴 더' 여유를 두고 정한다.
- **`--tools` 로 도구 줄이기 [실측]:** `--allowedTools Read` 만으로는 내장 도구 정의가 전부 실려 첫 요청 캐시 쓰기가 38,167 토큰, `--tools Read` 를 더하면 7,015 토큰(haiku 0.0080 → 0.0014 USD, 턴 3 → 2). 기본 모델은 **`claude-opus-5-5`**(Max 구독 — `--model` 없음)이고, `--tools Read` 로 최소 호출 1번이 0.052 USD(캐시 쓰기 1시간 = 입력 단가 × 2). → 틀에 `--tools <허용 도구 이름>` 을 넣었다(값 하나 — 쉼표 목록, `--allowedTools` 앞). 도구 정의를 넣으면 Opus 호출마다 기본 약 0.3 USD 가 더 든다는 뜻이라 단계 상한 0.5 USD 와 맞물리는 결정이다.
- **cwd 밖 파일 [실측]:** `--permission-mode dontAsk --allowedTools Read` 에서 cwd(`claude_ctx/`) 밖 절대 경로 `Tools/uigen/work/<run>/render.png` 를 `--add-dir` 없이 읽었다(권한 거부 0) — 이미지도 보인다(haiku 가 HUD 요소 · 한글 문구를 맞게 읽음, 크기는 추정). → 입력 파일은 지금처럼 프롬프트에 절대 경로로 준다.
- **맥락에 들어오는 지침 [실측]:** 저장소 `CLAUDE.md`(상위 탐색) + `claude_ctx/CLAUDE.md` 두 개, auto-memory 없음 — `autoMemoryEnabled: false` 와 일치(§10-1 '효과 미관측'이 이것으로 확인). 저장소 CLAUDE.md 는 설계대로 감수.
- **스키마 위반 재시도:** 일부러 어기라고 시킨 호출(안쪽 if-then)에서 모델이 처음부터 맞춘 값을 내 CLI 쪽 검증 · 재시도 여부는 가르지 못했다 — 오케스트레이터는 로컬 검사(스키마 · 의미 · brief 맞물림)를 그대로 하고, 실패하면 오류를 붙여 1회 재요청한다(§2-2).
- **run 시작 검사 `llm.preflight`:** `claude --version`(기대 버전과 다르면 `version_match: false` 표시만) · `claude auth status` JSON 에서 `loggedIn` · `authMethod` · `subscriptionType` **만** 옮긴다(이메일 · 조직 id 는 남기지 않음). 미로그인 → `LLM_NOT_LOGGED_IN`, 구독이 아닌 인증(`claude.ai` 밖 — API 키 · 콘솔) → `LLM_AUTH_METHOD`(토큰 과금 경로 거부). 파이프라인 연결은 LLM 단계가 처음 들어오는 1b-4 에서.
- **오류 분류(`classify_error`):** `LLM_MAX_TURNS` · `LLM_NOT_LOGGED_IN` · `LLM_BUDGET`(subtype · terminal_reason) · `LLM_API_ERROR`(terminal_reason `api_error` · `api_error_status`) · `LLM_ERROR`. 가짜 CLI 에 `budget` · `api_error` · `bad_schema_arg` 모드와 `--version` · `auth status` 응답을 채록 모양 그대로 더했다. `llm.jsonl` 에 `model` · `tokens` 도 남긴다.
- **analyze 상한 근거(잠정 그대로):** Opus 5.5 · `--tools Read` 기준 — 시스템 + 프롬프트 파일 + 스키마(spec 10 KB) 캐시 쓰기 약 1.3만 토큰 ≈ 0.1 USD, 이미지 읽기 턴, spec 출력 + 생각 1.5 ~ 3만 토큰 ≈ 0.3 ~ 0.6 USD → 합계 0.4 ~ 0.7 USD. 1.0 USD 는 '한 턴 더' 여유를 포함한다. 1b-4 첫 analyze 에서 실측으로 다시 본다.

1b-2 에서 확인 · 정한 것 (11-15, `codex-cli` 0.166.0 · ChatGPT 로그인 · 실제 호출 1번):
- **생성기 `gen/codex.py`:** `generate(prompt, dest, gen_dir, cfg, budget, refs?)` — `CodexLock`(`work/.codex.lock`, pid — 죽은 잠금은 넘겨받음; run · 컨셉 도구 사이에서도 한 번에 하나) · `CallBudget`(호출마다 JSONL 한 줄, **실패도 센다** — 플랜을 쓰므로; 상한이면 띄우기 전에 `CODEX_CALL_LIMIT`) · `preflight`(`codex --version` 기록 · `codex login status` 가 'Logged in using ChatGPT' 인지 — API 키 로그인은 `CODEX_AUTH_METHOD` 로 거부, auth.json 은 읽지 않음) · 환경에서 `OPENAI_API_KEY` · `CODEX_API_KEY` · `AZURE_OPENAI_API_KEY` 제거 · stdin DEVNULL · 벽시계 600초(넘으면 `taskkill /T` 로 node → codex.exe 트리까지) · `--dangerously-bypass-*` · `--approve-for-me` 거부. gen_dir 에 `prompt.txt` · `events.jsonl`(원문) · `stderr.txt` · `last.txt` · `result.json`.
- **결과 찾기:** `generated_images/<thread_id>/` 의 가장 새 PNG → 없으면 실행 전후 `generated_images` 차이 → 없으면 cwd 의 새 PNG(에이전트가 복사했을 때) → 없으면 `CODEX_NO_IMAGE`. 식별자 없이 이미지가 안 나온 호출이 연속 2번(`suspect_quota_after_failures`)이면 `CODEX_QUOTA_SUSPECTED`(§12-1 A3 '틀리면'). 식별자(`usage_limit_reached` 등 · `Try again at`)가 출력에 있으면 `CODEX_QUOTA` — 이벤트 원문은 그대로 남는다.
- **실행 파일 [실측]:** PATH 의 `codex` 는 npm `.cmd` 래퍼(`… & "%_prog%" "%dp0%\node_modules\@openai\codex\bin\codex.js" %*`)라 프롬프트가 cmd.exe 를 거치면 `&` `%` `^` `|` `<` `>` 가 해석된다 → `resolve_cli` 가 `node <npm>/node_modules/@openai/codex/bin/codex.js` 로 직접 부른다(래퍼의 `.cmd` 와 같은 node 선택 규칙). 실제 바이너리는 `@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe` 지만 codex.js 가 `CODEX_MANAGED_*` 환경을 넣으므로 그 경로를 거친다.
- **인자 [실측]:** `-i, --image <FILE>...` 는 값을 여러 개 받는다 → 프롬프트를 `exec` 바로 뒤에 두고 `-i` 를 맨 끝에(`codex exec "<프롬프트>" -C <gen_dir> --skip-git-repo-check -s workspace-write --json -o <gen_dir>/last.txt [-i <참조>…]`). stdin 을 닫아도 stderr 에 `Reading additional input from stdin...` 이 찍히지만 기다리지 않고 진행한다.
- **프롬프트 틀(`WRAPPER`):** 'built-in image_gen 을 정확히 한 번 · CLI 대체 경로 · API 키 금지 · SKILL.md 등 파일을 읽지 말고 셸 명령 금지 · 결과를 옮기지 말 것 · 한 줄로 답' + (참조가 있으면) '참조 이미지는 용도만 — 글자 · 배경을 베끼지 말 것' + 요청 본문. **[실측]** 셸 명령 0 · 입력 38,362(캐시 31,744) · 출력 436 토큰 — P0(91,703, 에이전트가 SKILL.md 를 읽음)의 42 %. 사용자 `config.toml` 의 플러그인 · 설정은 그대로 둔다(`--ignore-user-config` 는 Windows 샌드박스 설정까지 빼서 시험하지 않음).
- **이벤트 [실측]:** `thread.started{thread_id}` → `turn.started` → `item.completed{agent_message}` ×2 → `turn.completed{usage: input_tokens · cached_input_tokens · cache_write_input_tokens · output_tokens · reasoning_output_tokens}` — image_gen 항목은 여전히 따로 나오지 않는다(P0 와 같음). 결과는 `thread_id` 폴더에서 찾았다. 1장 57.9초.
- **컨셉아트(`fixtures/m4_combat_hud_concept/`):** `concept_prompt.md`(장면 + HUD 4요소만, 위치 · 크기 · 색은 1a 손 spec 값을 글로) → `concept.png` **1672 × 941 RGB(알파 없음, 2.3 MB — LFS)** · `concept.json`(codex 버전 · thread_id · 프롬프트 sha256 · 크기 · 저장소 기준 상대 기록 경로). '16:9 1920x1080' 을 요청해도 크기는 고를 수 없다(비율 1.777 은 맞음) → 1b-4 normalize 가 기준 해상도로 맞춘다. 버스트 배너('체인 버스트 3') · 체인 패널('체인' · '4.2' · '2/4') · '오의 불가' · 70 % 금색 게이지가 모두 있고 한글이 맞게 그려졌다(사람 눈 확인 통과 11-15). 장면에는 인물 5명 · 고딕 폐허 · 깃발 — analyze 의 장면 / UI 가르기(A8) 시험감이다.
- **한도(A3):** 이번에도 걸리지 않아 이벤트 모양 · 종료 코드는 미채록.

1b-3 에서 확인 · 정한 것 (11-15):
- **OCR 설치(사용자 승인):** `Tools/mcp/.venv` 에 `rapidocr==3.10.0` + `onnxruntime==1.32.0` 과 의존성 16개(내려받기 110.8 MB — opencv-python-headless 5.0.0.93 · numpy 2.5.4 · Pillow 13.0.0 · shapely · pyclipper · omegaconf · protobuf · requests 등), `requirements.txt` 에 고정. **[실측]** 예전 `rapidocr_onnxruntime` 은 Python 3.13 을 받지 않아 pip 가 2022 년판 1.2.3(≤3.10)까지 물러났다 → 새 `rapidocr` 패키지. 기본 모델 `PP-OCRv6_det_small` · `PP-OCRv6_rec_small` · `ch_ppocr_mobile_v2.0_cls` 가 **휠 안에** 있다(실행 중 내려받기 없음 — `requests.get` 을 막은 채로 돌려 확인). 단 설정 기본 Cls 는 번들에 없는 PP-OCRv4 라 모델 경로를 명시하고 `use_cls=False` 로 쓴다(1b-5 래퍼에서).
- **OCR 첫 측정 [실측]:** 검출만(`use_rec=False`) — 컨셉 5곳(체인 버스트 3 · 체인 · 4.2 · 2/4 · 오의 불가, 점수 0.66 ~ 0.89) · 1a 렌더 6곳 · **procedural 에셋 2장 0곳**, 1장 0.3 ~ 1.0초. 인식(중국어 기본 모델)은 한글을 못 읽는다(`三3`) — 게이트는 **검출 상자**로 하고(언어 무관), 인식 문자열은 기록만.
- **폰트 내려받기(사용자 승인):** GitHub `orioncactus/pretendard` v1.3.9(최신, 2023-11) `alternative/Pretendard-Regular.ttf` 2,725,828 B · `Pretendard-Bold.ttf` 2,661,752 B · `LICENSE`(SIL OFL 1.1) 4,418 B — 스크래치의 새 폴더에 받아 크기 · TTF 머리(0x00010000) 확인 → 원본은 `Tools/uigen/work/_fonts/pretendard/`(git 무시, WidgetImportSourceRoots 안), 라이선스는 `Content/UI/Fonts/Pretendard/OFL.txt`.
- **Tool `import_font_family`(WidgetMcp 12번째):** 엔진 `UFontFileImportFactory::FactoryCreateBinary`(`EditorFactories.cpp:5077`)와 같은 순서를 대화창 없이 — 파일마다 `UFontFace`(SourceFilename · `FontFaceData->SetData` · `CacheSubFaces`, sub-face 0 이면 거부) + 컴포지트 `UFont`(`FontCacheType = Runtime` — `UFontFactory` 와 같음, DefaultTypeface 에 `{Name = 타입페이스, FFontData(Face)}`). 타입페이스 이름은 spec 굵기 어휘가 고르는 것(Regular · Bold · Light · Italic · Bold Italic)만. 새 ini 키 **`[WidgetMcp] WidgetFontOutputPaths=/Game/UI/Fonts/`** — 그 아래 하위 폴더만(접두 자체 거부) · 원본은 WidgetImportSourceRoots 안 · 덮어쓰기 거부(하나라도 있으면 아무것도 안 만듦) · 전역 더티 비교(밖이 더티면 만든 것을 내림) · `save` 기본 true(프로젝트 폰트는 커밋 대상). `get_editor_status.widget.font_output_paths` · MCP 창구 `widget_mcp.import_font_family`. 자동 시험 `WidgetMcp.Tools.ImportFont`(엔진 Roboto 두 파일 → run 폴더 · 저장 안 함 → 폐기 + 거부 경로 4개).
- **실제 임포트:** `/Game/UI/Fonts/Pretendard/` 에 `FF_Pretendard_Regular`(2.73 MB) · `FF_Pretendard_Bold`(2.66 MB) · `F_Pretendard`(9 KB) 저장 — 에디터 저장은 폰트 데이터를 애셋 안에 넣는다(`bSaveInlineData = … || !Ar.IsCooking()` `FontFace.cpp:111`). sub-face 'Pretendard (Regular)' · 'Pretendard (Bold)'. `.uasset` 은 LFS. spec 값 = `font.family: "/Game/UI/Fonts/Pretendard/F_Pretendard.F_Pretendard"`(export 가 돌려주는 객체 경로 그대로 — 왕복 비교) → `pipeline.yaml fonts.default_family`.
- **줄 높이 재측정 [실측]:** TextBlock `auto_size` 높이 — Pretendard 16→26 · 18→30 · 22→36 · 26→43 · 30→49 · 34→55(크기 × 1.62 ~ 1.67, regular · bold 같음), 엔진 기본 16→26 · 18→29 · 22→35 · 26→42 · 30→48 · 34→54(1a 값과 같음). 같은 글자열 너비는 Pretendard 가 8 ~ 10 % 좁다. → `pipeline.yaml fonts.line_height`(1b-4 analyze 프롬프트 · bbox 계산에 쓴다).
- **렌더 눈 확인(내 확인):** 한글 · 숫자 · 라틴 모두 그려지고, **엔진 기본 글꼴은 bold 를 줘도 한글이 굵어지지 않는데(대체 폰트에 굵은 면 없음) Pretendard 는 한글도 굵다** — 프로젝트 폰트를 넣은 실익. 렌더는 `Tools/uigen/work/_fonts/measure_20261115_013607/render_1920x1080.png`.
- **빌드 [실측]:** DebugGame 15 작업 23.1초 `Result: Succeeded` — WidgetMcp 외에 `Module.EditorMcpCore.cpp` · `Module.AstralBreak.9.cpp` 도 다시 컴파일됐다(이번 변경과 무관한 묶음 — 1a-5 마지막 빌드가 Development 였던 영향으로 보임, 소스 변경 없음).

1b-4 에서 확인 · 정한 것 (11-15):
- **입력 `inputs.yaml`(새 스키마 `schemas/inputs.schema.json`, 10종째):** mode `concept` · screen_type · screen_id · concept(inputs 기준 상대) · resolution · font(null = `pipeline.yaml fonts.default_family`) · text · required_elements · **data[]{id, type, widget, widget_type, format?, sample?, desc?}** · static_text · style_keywords. 진입점 `--inputs <yaml>`(+ `--concept <png>` 로 그림만 바꿈, `--spec-dir` 와 둘 중 하나). 바인딩 위젯의 **타입까지 요청이 고정**한다 — codegen 계약(BindWidget 타입)이 바뀌면 `BINDING_RETYPE` 이므로 LLM 이 고르게 두지 않는다. M4 HUD 는 1a 손 spec 과 같은 8개(`fixtures/m4_combat_hud_concept/inputs.yaml`) → 계약 해시가 같아 codegen 이 건너뛸 자리. brief 스키마에 `dynamic_data[].widget_type` · `desc` · `text`, spec 스키마 asset 에 `ref_bbox`(codex 참조로 자를 reference 영역), report 에 `analyze` 요약을 더했다.
- **normalize(concept):** 스키마 → 맞물림 검사(데이터 id · 위젯 중복, 데이터 종류 ↔ 위젯 타입, number 의 format, 동적 글자 위젯에 고정 글자 금지) → 컨셉을 기준 해상도 RGB 로(Pillow LANCZOS — 비율 차이 ≤ 1 % 늘림, 넘으면 가운데 + 검은 띠) → `reference.png` · `brief.json`(binding_contract 는 `U<screens.yaml widget>` + 데이터 위젯 목록) · `normalize.json`(원본 크기 · 변환 · sha256) · `inputs.json`. 실제: 1672×941 → 1920×1080 stretch(비율 차이 0.06 %).
- **analyze(`stages/analyze.py`):** `llm.run_stage("analyze")` — 출력 스키마 = spec 스키마 통째(1b-1 실측), 시스템 프롬프트 `prompts/analyze.md`(장면 / UI 가르기 · 계약 · 트리와 슬롯 · 점 앵커 배치 공식 · 좌표 규약 · 글자는 TextBlock 만 · 줄 높이 표 · 브러시 · 에셋 출처 고르기 — codex 는 '고립된 요소 · 투명 배경 · 글자 없음' 프롬프트 + `ref_bbox`, 최대 6개, 나머지 procedural / rounded_box). 사용자 프롬프트는 파일 절대 경로 · 계약 표 · 필수 요소 · 줄 높이 · 게이트 기준을 넣는다. **LLM 은 배치 · 스타일 · 에셋만 판단하고 계약 필드는 코드가 채운다(`apply_contract`)** — canvas · profile · binding(data · kind · format) · 동적 글자(sample 을 format 대로) · 게이지 percent · 고정 글자 · TextBlock `font.family`. 검사(`check`) = spec 스키마 · 의미 · brief 맞물림 · 바인딩 위젯 타입 · bbox_intent 있음 · 캔버스 안(±2 px) · **영역 캔버스 슬롯이 bbox_intent 에 놓이는지(±2 px)** · 에셋이 쓰이는지 · codex 프롬프트 · ref_bbox · procedural 매개변수 · 크기 ≤ 1024 · codex ≤ 6 · 계약 밖 바인딩. 실패하면 오류 목록 + 앞 출력 파일 경로를 주고 1회 재요청, 또 실패면 `ANALYZE_INVALID`. 출력 `spec.json` · `specs/000.json` · `analyze/attempt_NNN(.json|_errors.json)` · `analyze/overlay.png`(bbox_intent · ref_bbox 를 reference 위에) · `analyze.json` · `llm.jsonl`.
- **run 시작 검사 연결:** LLM 단계가 있는 run(concept 모드 · fix.mode ≠ deterministic)만 `preflight` 단계(claude 버전 · 로그인 · 구독) — 실패하면 아무 호출 없이 끝. 단계 순서: preflight → normalize → analyze → (inject_fault — concept 은 analyze 뒤, hand_spec 은 그대로 normalize 뒤) → codegen …. `pipeline.yaml phase: 1b`.
- **실제 run `R20261115_014638_CombatHUD`(`--until analyze`, 에디터 없음) [실측]:** preflight 0.37초 · normalize 0.34초 · **analyze 87.4초 · 호출 2번 · 0.432 USD 환산 · claude-opus-5-5**. 1번째(60.3초 · 0.271 USD · 턴 3 · 출력 6,203 + 생각 2,862 토큰 · 캐시 쓰기 17,931)는 검사 2건만 실패 — codex 에셋 크기 1240 × 236 · 1648 × 124 가 상한 1024 를 넘음(프롬프트의 '얇은 프레임은 2배'를 따른 것) → 2번째(26.7초 · 0.161 USD)가 1024 안으로 줄여 통과. **실제 LLM 으로 재요청 경로가 한 번 돌았다.** 프롬프트를 '2배까지 · 어느 변도 1024 를 넘지 말 것'으로 고쳤다(다음 run 부터). 결과 위젯 18개(영역 3 — BurstBanner · ChainPanel · UltArea) · 에셋 4(codex 3 — 버스트 배너 · 체인 패널 · 게이지 프레임, procedural 1 — soft_glow). `note`: '고딕 성당 폐허 · 하늘 · 총잡이 · 보스 · 아군 · 월드 깃발 · 마법 효과는 UI 아님'.
- **A8(장면 / UI 가르기) [실측 1회]:** 장면 요소는 위젯 · 에셋 어디에도 없고, 위젯 bbox 가 HUD 4요소 자리에 맞는다(겹침 그림 — 내 확인, 사람 눈 확인 대기). 숨은 상태 요소(게이지가 가득 찰 때의 빛 `UltReadyGlow`)는 프롬프트대로 게이지 영역 크기로 만들었다.
- **남은 것 · 관찰:** 줄 높이 표가 34 까지라 큰 글자(44 · 56 · 80)는 모델이 비율로 늘려 잡았다(80 → 130 px ≈ 1.63 배 — 실측 비율과 같음). 큰 크기가 게이트에서 어긋나면 표를 늘린다. 위치 정확도 · 게이트 통과 여부는 build · verify(1b-5 이후)에서 본다.
- **비용 표기(사용자 지적 11-15):** 리포트 · 로그의 USD 는 claude CLI 가 붙이는 **API 정가 환산값**(`costBasis: list`)이다 — 구독(claude.ai · max) 로그인이라 과금되지 않고 플랜 사용량만 쓴다. 로그 문구를 'API list-price equivalent … (subscription login — plan usage, not billed)'로 바꿨다.

1b-5 에서 확인 · 정한 것 (11-15):
- **generate ← codex:** `backends.allowed: [procedural, codex]`. codex 에셋을 처음 만들 때 run 마다 한 번 `codex.preflight`(→ run.json `codex_cli`), 단계 동안 `work/.codex.lock`, 호출 상한 `codex_calls.jsonl`(run 폴더 — 실패도 셈). 참조(-i) = reference.png 의 `ref_bbox`(+8 px) 자른 것에서 **그 안의 TextBlock bbox 자리를 OpenCV inpaint 로 지운 것**(`gen/<asset_id>/<시도>/ref.png` — 참조의 글자를 베끼지 않게). 프롬프트 = analyze 의 asset.prompt + 출력 조건(고립된 한 요소 · 비율 W:H · 최종 크기 · 9-slice 면 가운데가 늘어남 · 진짜 알파 · 글자 · 숫자 · 글자 같은 자국 금지 · 틀은 속을 비움), 다시 만들 때(replace_asset)는 '앞 판에 글자 같은 자국' 문구를 더한다. 한도 → `CODEX_QUOTA` 로 멈춤, 그 밖 실패는 그 코드로 멈춤(요청한 출처를 바꾸지 않음). gen.jsonl 에 thread_id · usage · found_by · 참조 정보.
- **refine(생성 이미지, `gen/postprocess.py` · `core/ocr.py`):** 배경 — 완전 투명 픽셀이 2 % 이상이면 그대로, 아니면 테두리 색 중앙값을 배경으로 보고 테두리에서 이어진 비슷한 색(채널 ±22)을 flood fill 로 투명 + 가장자리 1 px 부드럽게 → 여백 자르기(알파 > 8, +2 px) → spec 크기로(9-slice 는 늘림, 나머지는 비율 유지 + 투명 여백) → **9-slice margin 추정**(미리 곱한 RGBA 의 열 · 행 평균이 가운데와 ±6 안인 연속 띠 = 늘려도 되는 부분, 띠가 20 % 미만이면 실패 → spec 값) → 알파 검사 → OCR. 추정한 margin 은 **spec 의 에셋 margin 과 그 에셋을 쓰는 box · border 브러시 margin 에 넣는다**(build 는 manifest 가 아니라 브러시 margin 을 쓴다 — 0.02 이상 다를 때만, `refine.json margin_updates` 에 전후 기록). OCR 은 RapidOCR **검출 모델만**(번들 경로 명시 · 회색 바탕 합성) — 상자가 있으면 `ocr_text` 에 '글자 같은 상자 n 개'(실패가 아니라 기록), verify `baked_text` 가 잡고 결정적 fixer 가 그 에셋 `replace_asset(regenerate)` 를 낸다(재시도 분기 generate → refine → build, §2-2 그대로).
- **실제 run `R20261115_015927_CombatHUD`(`--keep-failed`, 6분 44초) [실측]:** preflight · normalize → **analyze 1번에 통과**(50.7초 · 0.221 USD 환산 — 1b-4 의 크기 규칙 수정 효과) · 위젯 15 · 에셋 4(codex 3) → **codegen 건너뜀**(계약 `sha1:5ae0d80a…` 1a 와 같음 — 바인딩 위젯 타입을 요청이 고정한 효과) → generate codex 3장 118초(원본 2172×724 · 1615×974 · 1495×1052 — **셋 다 진짜 알파로 왔다**, 배경 제거 불필요) → refine 3.5초(margin 추정 2/3 — 가운데 장식이 있는 배너는 spec 값, 바뀐 margin 4곳) → build 48초(에디터 기동 · 브리지 14.6초 + 30초, 텍스처 4 · WBP 생성 · apply 14 op) → verify **8/10**: `iou_leaf`(BurstCountText 1개 — 아래) · `baked_text`(배너 · 게이지 프레임 — 아래). 결정적 fixer 가 두 에셋 재생성을 두 번 냈고(codex 7/20) 실패 게이트 집합이 줄지 않아 `NO_PROGRESS` 로 끝 → `--keep-failed` 로 `/Game/_AutoGen/R20261115_015927_CombatHUD/` 에 9 패키지(WBP_CombatHUD + 텍스처 8 — 재생성분 `_2` · `_3` 포함) 저장. 에디터는 내렸다.
- **OCR 오검출 [실측] → 기준 0.5 → 0.7:** 생성 에셋에는 글자가 없었다(눈 확인). 검출 모델이 금색 장식(배너 양끝 캡 · 가운데 장식, 게이지 양끝 캡)을 점수 **0.527 ~ 0.645** 의 '글자 같은 상자' 7개로 잡았다. 같은 엔진으로 진짜 글자는 **0.704 ~ 0.908**(컨셉 속 '체인 버스트 3' · '4.2' · '2/4' · '오의 불가', 합성 영문 0.79 · 0.86). 인식 모델(중국어)은 장식에서 아무것도 못 읽었지만 한글 '오의 불가'도 못 읽어 판정에는 못 쓴다. → `core/ocr.py DEFAULT_MIN_SCORE = 0.7`(잠정 — 여유가 좁다, Phase 2 보정 세트에서 다시 본다). 이 기준이면 이번 run 의 에셋은 모두 통과한다.
- **iou_leaf [실측]:** BurstCountText 의도 [1085, 117, 52, 84] ↔ 측정 [1069.5, 117.5, 44, 83] — IoU 0.418. 원인은 글자 실측 폭: Pretendard 로 '체인 버스트'가 의도보다 37 px 좁게(243 vs 280) 그려지고 가로 상자가 가운데 정렬이라 숫자가 왼쪽으로 15 px 밀렸다(숫자 자체도 44 vs 52). 영역 안쪽 문제라 결정적 fixer 는 고칠 수 없다 → **1b-6 LLM fix 의 첫 실전 대상**(예: 라벨 칸 fill · 고정 폭).
- **렌더 눈 확인(사람이 보고 1b-6 으로 진행 — 11-15):** 배치는 컨셉과 거의 겹친다(`compare.png` — 컨셉 | 렌더 | 겹침). 다른 점은 글꼴(컨셉은 세리프 느낌 · 렌더는 Pretendard) · 게이지 채움이 프레임 안쪽 선을 조금 덮음 · 프레임 장식 굵기.

1b-6 에서 확인 · 정한 것 (11-15):
- **`fix.mode: hybrid`(pipeline.yaml 기본 — `--fix-mode deterministic|hybrid|llm` 로 run 마다 덮음):** 결정적 fixer 의 op 를 먼저 쓰고, **op 가 없거나 직전 시도의 결정적 patch 가 실패 게이트 집합을 줄이지 못했으면** LLM 으로 넘긴다. 뒤쪽 조건은 1b-5 실측(OCR 오검출로 같은 에셋 재생성을 반복하다 `NO_PROGRESS`)에서 나왔다 — 조기 종료(무진전 2번) 전에 LLM 이 한 번 본다. §8-3 의 'LLM verifier · fix' 를 이렇게 보완한다(사용자 결정).
- **LLM 경로(`fix.llm_propose`):** verifier(`prompts/verifier.md` — 보는 눈: render · reference · spec · gates · **geometry**(측정 상자) · brief 를 읽고 실패 게이트마다 위젯 · 원인 · 숫자 근거 · 제안 op) → fix(`prompts/fix.md` — 고치는 손: op 문법 · 슬롯 규칙 · 점 앵커 공식 · 글자 상자 = 줄 높이 · 최소 patch). 두 프롬프트 모두 실패 게이트 요약(배치 게이트는 실패 위젯의 의도 ↔ 측정 상자 · 값 · 기준)과 줄 높이 표(프로젝트 폰트면 Pretendard 표, 아니면 엔진 × 1.6)를 사용자 프롬프트에 넣는다. **patch 검사:** `guard_ops`(bbox_intent · binding · note 고치기 금지 — bbox_intent 는 reference 에서 잰 목표라 바꾸면 게이트를 속인다, 계약 위젯의 text 금지, 필수 요소 제거 · 바인딩 추가 금지) → patch 스키마 → 사본 적용(`apply_patch`). 실패하면 오류 목록을 붙여 fix 를 1회 다시, 또 실패하거나 LLM 이 실패(예산 · 시간 · 미로그인)하면 **예외가 아니라 op 없음**(`NO_FIX`, fixes 에 이유) — run 은 finalize 까지 간다(1a 틀은 `LLM_PATCH_INVALID` 예외였다). 기록 `attempts/00k/llm_verifier.json` · `llm_fix_N.json` · `llm.jsonl`(단계 · 호출 · 모델 · 토큰 · 환산 비용 · op 수 · 오류 수).
- **결함 `shrink_text`(4번째):** 가장 큰 글자(bbox_intent 높이)의 font.size 를 45 % 로 — 영역은 제자리라 결정적 fixer 는 '안쪽 문제'로 op 를 못 낸다(LLM 경로 시험용).
- **pytest:** 1b-6 부터 pipeline.yaml 기본이 hybrid 라 conftest 가 파이프라인 시험의 기본을 deterministic 으로 덮는다(1a 시험의 전제 — LLM 을 보는 시험은 `--fix-mode hybrid`). 새 시험 8개(hybrid 가 결정적 op 를 쓰는 경우 · 안쪽 실패 → LLM · 가드 거부 → 재요청 통과 · 쓸 수 없는 patch / LLM 실패 → NO_FIX · 무진전 → LLM · 가드 규칙 · shrink_text 대상 · 가짜 에디터로 끝까지 통과).
- **실제 결함 주입 run `R20261115_021926_CombatHUD`(1a 손 spec + `--inject-fault shrink_text`, 기본 hybrid, 1분 20초) [실측]:** ChainTimerText 34 → 15 → 시도 1 verify 9/10(`iou_leaf` — 의도 [1628, 180, 228, 50] ↔ 측정 [1628, 193, 228, 24], IoU 0.48) → 결정적 fixer op 없음 → **LLM verifier**(12.5초 · 0.149 USD 환산 · 턴 4): '칸은 50 px(110 × 5/11)에 맞게 놓였는데 글자 15 의 줄 높이 24 px 가 가운데 정렬됨 — 30 → 48 px 이면 IoU ≈ 0.96' → **LLM fix**(10.6초 · 0.125 USD 환산 · 가드 · 적용 검사 통과 1번에): `set ChainTimerText font.size 30`(원래 34 가 아니라 표로 계산한 30 — 칸 50 px 에서 줄 48 px) → build(apply 1 op) → **시도 2 verify 10/10** → 저장 4 패키지. LLM 2호출 합계 23초 · 0.274 USD 환산(구독 — 과금 아님). 에디터는 내렸다.
- **'1b 로 넘길 것'의 재시도 codegen 분기 실제 경로:** 이번 LLM fix 는 배치 op 만 내서(바인딩은 가드가 막음) 실제로는 돌지 않았다 — 계약을 요청이 고정하는 1b 구조에서는 LLM fix 가 바인딩을 바꾸는 일이 없다. 1a 처럼 pytest(가짜 도구 사슬)로만 확인된 상태로 둔다.

**Phase 1b 결과 요약 (11-15, 1b-7 끝 run `R20261115_024358_CombatHUD` — DebugGame 에디터, 자동 시험 뒤 같은 에디터)**

| 끝 조건 · 검증 | 판정 | 숫자 |
| :--- | :--- | :--- |
| 무인 1회 통과 + 리포트 | **충족** | `run_pipeline --inputs fixtures/m4_combat_hud_concept/inputs.yaml`(옵션 없음 · 기본 hybrid) → **pass**, 3분 56초, 사람 개입 0. preflight 0.29 · normalize 0.31 · **analyze 50.5초(1번 · 재요청 없음)** · codegen 0.40(건너뜀 — 계약 `sha1:5ae0d80a…` · 떠 있는 에디터 리플렉션 일치) · generate 119.9초(codex 3장 · 3/20) · refine 14.8초(OCR 상자 0 · 3장) · build 1.2초 · verify 2.6초(2번) · **fix 45.4초(LLM)** · finalize 0.6초(5 패키지). 시도 1 = 9/10(`iou_leaf` — BurstCountText IoU 0.661, 1b-5 와 같은 '글자 폭 → 가운데 정렬 행 밀림') → 결정적 fixer op 없음 → **LLM verifier**(27.6초 · 턴 5 · fixes 2) → **LLM fix**(17.7초 · 1번에 가드 · 적용 통과): `BurstLabelText slot.padding [0,0,27,0]` + `BurstRow slot.padding [0,2,0,0]`(근거: '가운데 정렬 행 폭 W = 270 + 27 + 49 → 숫자 x 1084', 'v 가운데라 위 padding 8 줄이면 4 px 위로') → **시도 2 = 10/10** — iou_region 최소 1.0(4 영역 · 중심 0 px) · iou_leaf 최소 0.796(8 말단 · 중심 최대 1 px) · offscreen 0(3 해상도) · overlap 0 · **baked_text 0(생성 에셋 3장 검사 — 건너뜀 아님)** · roundtrip 0 · bindings · compile · texture_settings · required_elements 통과. report · lineage · `metrics/uigen.jsonl` 줄 남음. WBP = `/Game/_AutoGen/R20261115_024358_CombatHUD/WBP_CombatHUD`(+ 텍스처 4) |
| 사람 눈 확인(렌더 ↔ 컨셉) | **레이아웃 통과 · 외형 차이(11-15)** — 아래 '1b 후속 — 외형 재현' | `work/R20261115_024358_CombatHUD/compare.png`(위: 컨셉 · 렌더, 아래: 렌더를 컨셉 위에 얹음). 내 확인: 네 영역 위치 · 크기 · 색이 겹치고, 다른 점은 글꼴(세리프 ↔ Pretendard) · 게이지 프레임 장식 · '오의 불가' 글자 크기(얹으면 두 겹으로 보임 — 게이트 기준 안) |
| Phase 끝 회귀(필수만) | **통과** | 빌드: DebugGame `Result: Succeeded`(이미 최신) · Development `-DisableAdaptiveUnity` `Result: Succeeded`(WidgetMcp 묶음 4 작업 · 24.9초 — 새 cpp 를 유니티 묶음에 넣어도 충돌 없음). 에디터 1회(DebugGame): `AstralBreak.` 1차 53/55(665초 — 에디터 기동 직후, **실패 2개의 이름은 내 회귀 스크립트가 결과 필드를 잘못 읽어 남지 않았다**) → 같은 에디터 2차 **55/55**(398초 — 1a-5 의 415초와 같은 수준, 일시 실패로 판단) → `EditorMcpCore.` 2/2 → `WidgetMcp.` 6/6(새 `ImportFont` 포함) → 끝 run → `quit_editor` · 소멸 확인. pytest **198** 통과(1a 142 → +56) |
| 비용(구독 — 과금 아님) | 기록 | LLM(API 정가 환산): 1b-1 채록 약 0.10 · 1b-4 analyze 0.43 · 1b-5 run analyze 0.22 · 1b-6 결함 run 0.27 · 1b-7 끝 run 0.53(analyze 0.17 · verifier 0.20 · fix 0.16) — 모두 claude.ai Max 구독 사용량. codex: 컨셉 1 + 1b-5 run 7 + 끝 run 3 = **11회**(한도 걸림 0) |

- **증거 run(11-15 정리 뒤 — 사용자 결정):** 1b 는 끝 run `R20261115_024358`(통과 · 저장)만 `Tools/uigen/work/` 와 `Content/_AutoGen/` 에 남겼다. 1b-4 `R20261115_014638`(analyze 만) · 1b-5 `R20261115_015927`(첫 컨셉 WBP · 8/10) · 1b-6 `R20261115_021926`(shrink_text → LLM fix)은 휴지통 — 위 숫자는 기록으로만 남는다. 1a 증거 2개(`R20261115_001147` · `R20261114_235343`) · `work/_fonts/pretendard`(폰트 애셋의 원본 경로) · `work/_concept/20261115_011603`(`concept.json` 이 가리키는 기록)은 그대로. 일회성 스크래치(채록 · 측정 스크립트 · 내려받은 폰트 사본) · `work/_widgetmcp_tests` · 폰트 측정 렌더도 휴지통(합계 28.5 MB). `metrics/uigen.jsonl` 은 지운 run 의 줄까지 그대로.

**다음으로 넘길 것 (1b → M4 단위 C · Phase 2 이후)**
- **M4 단위 C:** 스텁 `UAstralCombatHUDWidget`(1a-3 생성 · 사람 소유)에 게이지 · 체인 연결. 쓸 WBP 는 끝 run 의 것이지만 `/Game/_AutoGen/`(git 무시)에 있다 — **정식 위치 `/Game/UI/HUD/` 로 옮기는 승격 도구(`promote_widget`)는 Phase 4** 라, M4 C 가 먼저 오면 손으로 옮길지 · 승격만 앞당길지 정해야 한다(사용자 결정).
- **A3(codex 한도) 미채록:** 1b 에서 11회 써도 걸리지 않았다. 판정 코드(식별자 + 연속 실패 2번 추정)는 가짜 codex 로만 확인.
- **보정이 필요한 잠정값(Phase 2 보정 세트):** OCR 검출 기준 0.7(오검출 최대 0.645 ↔ 진짜 글자 최소 0.704 — 여유가 좁다) · 9-slice margin 추정(끝 run 은 3장 모두 추정 실패 → spec 값 — 생성 텍스처의 미세한 색 변화에 띠 허용 ±6 이 빡빡해 보인다) · 줄 높이 표(34 까지 — 44 · 56 · 80 은 비율로 늘림) · LLM 단계 상한(analyze 실측 0.17 ~ 0.27 · verifier 0.15 ~ 0.20 · fix 0.13 ~ 0.16 USD 환산 — 잠정 상한 1.0 / 0.5 / 0.5 안).
- **화면 품질(게이트 밖):** 글꼴 느낌 차이 · 게이지 채움이 프레임 안쪽 선을 덮는 문제 같은 '스타일'은 지금 게이트가 보지 않고, LLM verifier 도 실패 게이트만 설명한다 — Phase 2 의 스타일 · ΔE 지표(§8-2 기록만)와 같이 본다.
- **컨셉 대역:** `fixtures/m4_combat_hud_concept/concept.png` 는 codex 로 만든 대역이다 — 사람이 그린 컨셉으로 바꾸고 `--concept` 로 다시 돌리면 1b 본래 검증(사람 그림 재현)이 된다.
- **재시도 codegen 분기 실제 경로:** 1b 구조(계약 고정 · 가드)에서는 돌 일이 없어 pytest 로만 확인된 채다.
- **운용:** `make_concept.py` 는 `.claude/settings.local.json` 허용 규칙에 없다(실행 때 확인이 뜬다 — 넣을지는 사용자). `claude` 독립 CLI 는 자동 업데이트로 버전이 바뀐다(`pipeline.yaml llm.expected_version` 2.1.325 — 다르면 표시만).

**1b 후속 — 외형 재현 A · B · C · D (11-15 사용자 결정 · 방향 메모 — A 완료 11-15(아래 'A 에서 확인 · 정한 것' · 'A 보강'), B 완료 11-15('B 에서 확인 · 정한 것' — B ③ 은 D 로), C · D 미착수)**

배경: 끝 run 은 게이트 10/10 이지만 **레이아웃만** 재현했다. 사용자 눈 확인에서 컨셉 대비 하단 게이지(금테 · 안쪽 트랙 · 그라데이션 채움 사라짐 + 노란 번짐), 상단 배너 · 체인 패널 프레임 모양(컨셉은 깔끔한 캡슐 · 얇은 금테, 생성본은 뾰족한 끝 장식 · 가운데 장식), 글자(컨셉 명조 계열 금색 ↔ Pretendard 단색)가 다르다는 지적. 원인: 게이트는 상자 위치 · 크기만 보고 스타일은 '기록만'(결정 6), LLM verifier 는 실패 게이트만 설명(§8-3) — 외형 차이는 수정 대상에 오르지 않는다. 원인 상세는 끝 run `specs/002.json`(게이지 = 프레임 Image 위에 ProgressBar — 어두운 배경 상자 + 단색 채움 `#F2B13A` 가 padding 10 ~ 12 px 만 두고 프레임 몸통을 덮음, 빛 `UltReadyGlow` 는 WBP 기본 '보임').

- **A. 컨셉에서 직접 따오기(가장 큰 효과 예상):** 컨셉에 보이는 프레임 · 패널은 새로 그리지 말고 **codex 편집**으로 분리한다 — 입력 = `gen/postprocess.reference_crop`(ref_bbox 자르기 + 글자 자리 inpaint, 이미 있음), 프롬프트 = '첨부 그림의 이 프레임을 모양 · 장식 · 비율 · 색 그대로 두고 장면 · 글자만 지워 투명 배경으로, 속이 비치는 안쪽은 같은 색의 어두운 단색(알파 약 90 %)으로'. spec asset 에 생성 방식 필드(예: `source_mode: extract | generate`)를 더하고 analyze 프롬프트는 '컨셉에 보이면 extract, 안 보이는 상태 요소(가득 찬 빛 등)만 generate'. built-in image_gen 의 편집은 대화에 보이는 그림이 대상이라(`~/.codex/skills/.system/imagegen/SKILL.md` 'Built-in edit semantics') `-i` 첨부로 되는지 먼저 1장 채록. refine(OCR · 배경 · 9-slice)은 그대로 거치되, 9-slice 추정이 끝 run 에서 3장 모두 실패했으니 띠 허용(`BAND_TOL` ±6)을 실측으로 다시 본다. 검증 = 에셋별 '컨셉 자른 것 ↔ 최종 텍스처' 나란히 그림 + 영역 ΔE 기록.
- **B. analyze 규칙 · 결정적 보정:** ① 게이지 = 프레임 텍스처를 ProgressBar `style.background`(box 9-slice)로, 채움은 프레임 안쪽 트랙에 들여(padding = 프레임 테두리 두께) **그라데이션 텍스처**(procedural 새 모양 예: `gradient_bar` — 위 · 아래 색 + 윗면 하이라이트)를 `style.fill` 로. 프레임 Image 를 따로 겹치지 않는다. ② **샘플이 꺼짐인 flag 바인딩 위젯은 WBP 초기 visibility 를 collapsed** 로(`stages/analyze.apply_contract` — 게이트 렌더는 force_visible 이라 영향 없음, 왕복 · verify 확인). ③ (선택) 글자 금색 그라데이션 · 외곽선은 TextBlock 폰트 Outline/Shadow 가 필요 — spec 어휘 · WidgetMcp `WidgetMcpSpec.cpp` 확장이라 C++ 빌드가 낀다.
- **C. 외형 검토 라운드(합격 판정은 그대로 게이트만):** 게이트를 통과한 뒤에도 LLM verifier 를 '스타일 모드'로 1 ~ 2회 — 입력 = 영역별 '컨셉 자른 것 ↔ 렌더 자른 것'(샘플 보이기 상태) + spec, 출력 = 허용 경로만의 스타일 op(`style.*` · `font.color/weight/size` · `slot.padding` · `replace_asset`(extract/generate 재시도 + 프롬프트)). 라운드 뒤 게이트가 하나라도 깨지면 그 라운드를 버리고 마지막 통과 spec 으로 finalize. 영역 ΔE00(§8-2)를 이번에 실제로 구현해 라운드 전후를 기록(게이트로 올리는 건 Phase 2 보정 뒤). 설계 §8-3('verifier 는 실패 게이트만') · §2-2(재시도 분기 — 통과 뒤 라운드) 문구를 바꿔야 한다. 상한: LLM 단계 `style_verifier` · `style_fix` 를 pipeline.yaml 에 따로(예산 · 턴), codex 재생성은 run 당 상한 안.
- **D. 제목용 세리프 폰트:** 한글 세리프(후보 Noto Serif KR — OFL, Regular · Bold 정적 TTF) — **내려받기는 파일명 · 출처 · 크기를 밝히고 따로 승인**(1b-3 과 같은 절차) → `import_font_family` 로 `/Game/UI/Fonts/<이름>/F_<이름>` → 줄 높이 재측정. `pipeline.yaml fonts` 를 역할별(본문 = Pretendard · 제목/숫자 = 세리프)로 바꾸고, analyze 가 글자마다 역할을 고르면 `apply_contract` 가 경로로 바꾼다(spec 은 지금처럼 `font.family` = 경로).
- **E. 지표 → 게이트(이 후속의 범위 밖 — Phase 2 그대로):** 영역 ΔE00 · 스타일 유사도(모델 선택 CLIP · DINOv2 · 스타일 전용 포함)를 보정 세트(HUD · 장비창 · 옵션 5 ~ 10장)로 임계값을 정해 게이트로 올리는 일은 §8-2 · §11 Phase 2 계획대로. 이 후속에서는 C 가 ΔE00 을 먼저 구현해 **기록만** 하고(Phase 2 의 입력이 된다), 스타일 유사도 모델은 넣지 않는다.
- **순서 제안:** B(싸고 결정적) → A(codex 사용 — 편집 가능 여부 채록부터) → D(승인) → C(위 셋 위에 라운드) → 컨셉 끝 run 1회 + 사람 눈(컨셉 ↔ 렌더) → 회귀(필수만: 빌드 2 · 에디터 1회 `AstralBreak.` → `EditorMcpCore.` · `WidgetMcp.` · pytest). 사용자 방침대로 시작 때 하위 단계 나눔 · 범위를 먼저 확인받는다.

**1b 후속 A 에서 확인 · 정한 것 (11-15, 미커밋 — 사용자: B 보다 A 먼저 · 하위 단계는 나누지 않음 · 커밋은 끝에 한꺼번에)**

착수 때 정한 것(제안 그대로 승인): 채록 2장(체인 패널 1.6:1 · 게이지를 3:1 로 넓혀) · spec asset 필드 `source_mode: extract | generate`(codex 에셋만, 없으면 generate) · 충실도 · ΔE 는 **기록만**(결정 6) · ΔE00 은 `core/color.py` 한 곳(C 가 재사용) · 안쪽 반투명은 채록 결과를 보고 결정적 단계로 · codex 세션 기록(rollout) 확인은 하지 않았다(구도 숫자로 편집이 확인돼 필요 없었음).

- **채록 [실측] (`codex-cli` 0.166.0 · 호출 2회, 저장소 코드 변경 전 — 스크래치 스크립트가 `gen/codex.py` 를 그대로 쓰고 프롬프트 틀만 편집판):** 입력 = `reference_crop`(ref_bbox + 글자 inpaint), 게이지는 828×64 를 위아래 실제 장면으로 넓혀 844×282('오의 불가' 자리도 inpaint). 기준선 = 끝 run 생성본(같은 에셋 raw)에 같은 지표.

  | | 체인 패널 | 게이지 |
  | :--- | :--- | :--- |
  | 입력 → 출력 | 354×218(1.624) → **1598×984 RGBA(1.624)** | 844×282(2.993) → **2170×725 RGBA(2.993)** |
  | 시간 · 토큰 | 37.2초 · 입력 36,414(캐시 30,848) · 출력 267 | 28.4초 · 38,588(27,136) · 335 |
  | 구도: 중심 차 · 크기 비 | 0.5 px · 0.997 / 1.005 | 0 px · 1.002 / 1.000 |
  | 비율 오차(생성본) | **−0.53 %**(+6.38 %) | **+0.50 %**(**+49.2 %**) |
  | 실루엣 IoU · 금선 F1(±2 px)(생성본) | 0.964 · 0.77(0.959 · 0.76) | 0.979 · 0.90(0.975 · 0.91) |
  | 안쪽 알파 | 중앙값 254 · 20 ~ 235 사이 0 % | 250 · 0 % |
  | OCR 상자 · 셸 명령 | 0 · 0 | 0 · 0 |

  - **판정: 편집이다** — 모서리 장식 · 변 가운데 표식 · 끝 캡이 그대로이고 게이지 채움은 지시대로 빠졌다(내 눈 확인 + 구도 숫자). `-i` 첨부가 SKILL.md 'Built-in edit semantics'의 '대화에 보이는 그림'으로 통한다. 이벤트 모양은 생성과 같다(`thread.started` → `turn.started` → `item.completed` ×2 → `turn.completed`, image_gen 항목 없음).
  - **출력 캔버스 비율 = 입력 비율** → 입력을 3:1 안으로 넓히면 얇은 요소도 비율이 지켜진다. 3:1 은 지금까지 본 가장 긴 출력(2172×724)에서 잡은 값이다(built-in 규칙은 문서에 없음 — 추정).
  - **반투명 안쪽은 못 낸다** — '알파 약 90 %'를 요청해도 250 ~ 254 → refine 의 결정적 단계로.
  - **지표 함정:** 픽셀별 ΔE00 은 얇은 금선의 1 px 어긋남에 흔들린다(금선 평균 12 ~ 27) → 영역 비교 기본은 **대표색**(영역 Lab 중앙값끼리, §8-2 '영역 대표색' 정의대로). 실루엣 IoU 는 사각 패널에서 생성본과 거의 같다 — 변별력은 구도 · 비율 · 대표색에 있다.
- **구현(Python 만 — WidgetMcp C++ · Config 변경 없음, 빌드 없음):**
  - `core/color.py`(새) — sRGB → Lab(D65) · CIEDE2000 · `region_delta_e`(대표색 + 같은 격자면 픽셀별 평균 · p95). Sharma(2005) 쌍 11개가 소수 넷째 자리까지 맞음.
  - `gen/fidelity.py`(새) — `extract_fidelity(컨셉 요소 상자, 되자른 결과, 최종 텍스처)` → framing(중심 차 · 크기 비 · IoU) · aspect · shape_iou · line_f1(테두리 띠 = 짧은 변 12 %, 장식선 = L* ≥ 45 · C* ≥ 20 — 은색 · 어두운 테는 못 잡음) · delta_e00(lines · interior 대표색, shape 픽셀별) + 나란히 그림(컨셉 | 체크무늬 위 최종 | 컨셉 위에 얹은 것).
  - `gen/codex.py` — `EDIT_WRAPPER` · `EDIT_NOTE` · `generate(…, edit=True)`(첨부 없으면 `CODEX_REF_MISSING`), 호출 기록에 `mode`. 생성 틀(`WRAPPER`)은 그대로.
  - `gen/postprocess.py` — `extract_region` / `extract_input`(ref_bbox + pad 8, 3:1 보다 길면 짧은 변을 실제 화면으로 넓히고 캔버스 가장자리면 밀어 넣음, 글자 inpaint) · `crop_back`(편집 캔버스 → 요소 상자, 캔버스 비율 변화 기록) · `interior_fill`(안쪽을 대표색 · 알파 0.9 로 — 처음엔 어두운 픽셀 알파 배수만이었다가 run 1 의 구멍으로 평탄화를 기본으로, 아래) · 9-slice 추정 v3 + `merge_margin`(아래).
  - `stages/generate.py` — `source_mode: extract` 면 `gen/<id>/<시도>/input.png` + `EXTRACT_HEAD`(요소 + analyze prompt) + `EXTRACT_RULES`(그대로 둘 것 · 바깥 투명 · 안쪽 단색 · 글자 금지 · 구도 유지) + 재생성 문구, gen.jsonl 에 `source_mode` · `extract{region, element, aspect}`. **extract 실패를 generate 로 바꾸지 않는다**(ref_bbox 가 없으면 `EXTRACT_NO_REFERENCE`).
  - `stages/refine.py` — extract 는 되자르기 → (기존) 배경 · 자르기 · 크기 → frame · panel_bg 안쪽 칠하기(`pipeline.yaml extract.interior_alpha` 0.9 · `interior_flatten`, alpha 가 null 이면 끔) → 9-slice(축별) → OCR → 충실도 `refine.json fidelity` + `assets/compare/<id>.png`. `run_pipeline` 이 `report.recorded.extract_fidelity` 로 옮긴다.
  - `stages/analyze.py` 검사 — `ASSET_SOURCE_MODE`(codex 밖) · `ASSET_REF_BBOX`(extract 인데 ref_bbox 없음). `prompts/analyze.md` — '컨셉에 보이면 extract(기본 선택), 안 보이는 상태 요소만 generate', extract 의 prompt = 그려진 요소 이름 + 상자 안에서 지울 것(예: 게이지 채움).
  - spec 스키마 asset `source_mode` enum. **계약 해시 · 왕복 영향 없음**(`cppgen.binding_entries` · `roundtrip_view` 같음 — pytest), normalize 는 필드를 그대로 둔다.
- **9-slice 띠 [실측 — 끝 run 텍스처 3 + 채록 2]:** 옛 방식(열 · 행 평균을 가운데 열 · 행과 비교, ±6)은 5장 중 4장 실패. ±6 이 빡빡해서가 아니었다 — ① **가운데 열 · 행이 장식**(변 가운데 표식 · 왕관)이라 기준이 틀어짐: 가운데 열 ↔ 3 px 옆 차이가 게이지 편집본 7.4 · 9.2, 끝 run 체인 패널 2.8 · 3.6(몸통 자체는 중앙값 기준 p90 0.16 ~ 0.39) ② **평균이 모서리 장식을 묻음**: 체인 패널 모서리(눈으로 0.13 · 0.21)를 0.018 까지 넓혔다. → **v3**: 기준 = 가운데 20 % 열(행)의 픽셀별 중앙값, 거리 = 픽셀 차이의 p99, 가운데에서 넓히며 2 % 이하 끊김(가운데 표식)은 건너뜀, **축마다 따로**(실패한 축만 spec 값 — 출처 `mixed`). `BAND_TOL` = 10 — p99 에서 체인 패널 margin 이 허용 6 ~ 24 사이 거의 같다(생성본 0.12 · 0.19 ~ 0.20, 편집본 0.13 · 0.21 ~ 0.22). 게이지는 가로(끝 캡 0.083 · 0.064)만 추정되고 세로는 끝 캡이 행마다 달라 spec 값(위젯 높이 = 텍스처 비율이라 세로 늘림은 거의 없음). 끝 run 배너(가운데 왕관 + 가로 그라데이션 빛)는 v3 로도 두 축 실패 — spec 값.
- **채록 실물을 새 refine 경로에 넣은 값(에디터 없이):** 체인 패널 9-slice [0.13, 0.215, 0.13, 0.217] · 안쪽 알파 바뀐 비율 0.82 · 구도 0.5 px · 비율 −0.53 % · 실루엣 0.955 · 장식선 F1 0.89 · 대표색 ΔE00 장식선 6.8 · 안쪽 5.8 / 게이지 [0.083, —, 0.064, —] · 0.61 · 0.5 px · +0.74 % · 0.968 · 0.94 · 10.6 · 1.9.
- **pytest 223 → 225**(198 → +27: `test_color.py` 13 · `test_extract.py` 14 — 입력 조각 · 되자르기 · 안쪽 칠하기 · 구멍 메우기 · 9-slice 축별 · 가운데 근처 넓은 표식 · analyze 검사 · 스키마 · 계약/왕복 · generate 편집 틀 · refine 충실도). 기존 `test_margin_estimate_gives_up_on_center_ornament` 는 축별 동작으로 바꿨다(가로만 실패).
- **실제 run 1 `R20261115_131656_CombatHUD`(옵션 없음 · DebugGame 에디터를 파이프라인이 띄움, 3분 52초) [실측]:** analyze 1번(53.8초 · 0.261 USD 환산 — 구독, 과금 아님)이 **codex 에셋 3개를 모두 `extract`** 로 골랐다(prompt 예: 게이지 'remove the gold fill bar so the inner track is empty and dark', ref_bbox 는 세 요소에 맞음 — `analyze/overlay.png`) → codegen 건너뜀(계약 `sha1:5ae0d80a…`) → generate 104.8초(codex 3/20 — 배너 2172×724 · 체인 패널 1580×996 · 게이지 2170×725, 모두 입력 비율) → refine 3.6초 → build 62.0초(에디터 기동 · 브리지 27.9초 + 30초) → **verify 시도 1 에 10/10**(iou_region 1.0 · iou_leaf 최소 0.827 · baked_text 0) → 5 패키지 저장 → `quit_editor`(버린 패키지 0 · 6.2초).

  | 충실도(기록만) | 배너 | 체인 패널 | 게이지 |
  | :--- | :--- | :--- | :--- |
  | 구도: 중심 차 · 크기 비 | 0 · 0.5 px · 1.006 / 0.992 | **−4.5 · 3.0 px** · 0.974 / 0.953 | 0 px · 1.005 / 0.968 |
  | 비율 오차 · 실루엣 IoU | −0.94 % · 0.972 | +2.31 % · 0.949 | −1.49 % · 0.967 |
  | 장식선 F1 · 대표색 ΔE00 장식선 / 안쪽 | 0.85 · 8.7 / 2.9 | **0.40** · 6.4 / 2.0 | 0.93 · 7.9 / 2.8 |
  | 9-slice | 두 축 실패(가운데 왕관) → spec | **두 축 실패** → spec | 가로 0.081 · 0.065 / 세로 spec(mixed) |

  - **편집은 판마다 다르다:** 체인 패널은 채록 판(장식선 F1 0.89 · 구도 0.5 px)과 달리 이번 판이 모서리 장식을 작게 다시 그렸고(F1 0.40), **글자를 지운 자리를 메우지 않고 구멍으로 남겼다**(안쪽 35.6 % 가 알파 < 128, 값 6 ~ 19) — 렌더에서 '4.2' 둘레가 검은 얼룩. 9-slice 실패도 이 구멍 때문.
  - **그래서 고친 것(run 1 뒤):** ① refine 안쪽 단계 `interior_alpha` → **`interior_fill`** — 안쪽(모양 가장자리에서 짧은 변 4 % 안쪽 · 장식선 2 px 넓힌 곳 밖)을 **대표색 한 색 · 알파 0.9** 로 칠한다(프롬프트가 이미 '안쪽 한 색'을 요구 — 그 요구를 결정적으로 보장). `pipeline.yaml extract.interior_flatten: true`(false 면 예전처럼 알파 배수만). 기록 `refine.json interior{holes_before, fill_color, changed_ratio}`. run 1 원본으로 재처리: 구멍 27.3 % → 0, 배너 · 게이지 값은 거의 그대로. ② 9-slice — 이번 판 체인 패널의 변 가운데 표식이 2 % 보다 넓어(2.9 · 3.3 %, 가운데에서 4 px 비켜남) 띠가 가운데 바로 아래에서 끊겨 아래 margin 이 상한 0.45 에 걸렸다 → **가운데 ±5 % 안에서 시작한 끊김은 4 % 까지** 건너뜀(`BAND_CENTER_GAP_FRAC` · `BAND_CENTER_ZONE`). 재처리 값 [0.129, 0.194, 0.129, 0.098], 채록 판 값은 그대로([0.13, 0.215, 0.13, 0.217]).
  - pytest 225(+2: 구멍 메우기 · 가운데 근처 넓은 표식).
- **실제 run 2 `R20261115_132452_CombatHUD`(고친 refine — 같은 입력 · 옵션 없음, 3분 43초) [실측]:** analyze 1번(60.2초 · 0.192 USD 환산 — 구독, 과금 아님)이 이번에도 codex 3개 모두 `extract` → codex 3/20(31.6 · 42.3 · 30.4초, 입력 약 38,300 · 출력 272 ~ 341 토큰, 출력 2170×725 · 1591×989 · 2169×725) → refine 3.4초 → build 46.4초 → **verify 시도 1 에 10/10**(iou_region 1.0 · iou_leaf 최소 0.711 = BurstCountText — 1b 의 '글자 폭' 문제 그대로) → 5 패키지 저장 → `quit_editor`(버린 0 · 7.2초).

  | 충실도(기록만) | 배너 | 체인 패널 | 게이지 |
  | :--- | :--- | :--- | :--- |
  | 구도: 중심 차 · 크기 비 | 0 · −0.5 px · 1.006 / 0.992 | **−5.0 · 3.5 px** · 0.971 / 0.967 | 0.5 · 0.5 px · 1.004 / 0.952 |
  | 비율 오차 · 실루엣 IoU | −1.68 % · 0.964 | +0.15 % · 0.952 | +0.52 % · 0.977 |
  | 장식선 F1 · 대표색 ΔE00 장식선 / 안쪽 | 0.85 · 11.5 / 3.5 | **0.48** · 5.4 / 0.7 | 0.99 · 8.9 / 2.9 |
  | 안쪽 칠하기(구멍 → 대표색) | 0 → #26110B | 0 → #241923 | 0 → #1B100C |
  | 9-slice | 두 축 실패 → spec | **[0.129, 0.225, 0.128, 0.22] 추정** | [0.152, —, 0.063, —] mixed |

  - 이번 체인 패널 편집은 구멍이 없었다(holes_before 0) — 구멍은 판마다 나오거나 안 나온다. 렌더(`render_sample.png`)의 체인 패널 안쪽은 평탄.
  - **체인 패널 모서리는 파이프라인 run 2번 모두 다시 그려졌다**(장식선 F1 0.40 · 0.48, 구도 4.5 ~ 5 px) — 채록 판(같은 요소, F1 0.89 · 0.5 px)과 다른 점은 ref_bbox(채록 [1543, 168, 338, 202] ↔ analyze [1541, 165, 341, 209] · [1541, 166, 341, 206])와 프롬프트 문구(채록은 '이중선 · 변의 작은 표식 · 선 굵기'까지 적음, analyze 는 두 번 다 'a dark purple rectangular panel with a thin gold border and small gold corner flourishes.')뿐이라 원인은 가르지 못했다. 배너 · 게이지는 세 판 모두 충실(장식선 F1 0.85 ~ 0.99, 구도 ≤ 0.5 px).
  - 게이지 왼쪽 margin 0.152(오른쪽 0.063): 안쪽은 평탄한데 금테가 왼쪽 60 ~ 260 열에서 고르지 않다(p99 11 ~ 20) — 컨셉의 채움 빛을 금테가 그대로 받은 판. 텍스처대로 잰 값이다.
  - 사람 눈 확인은 아직 — 에셋별 `assets/compare/<id>.png` 3장 · `render_sample.png`.
- **증거 정리(11-15 사용자 승인 세 번 — 휴지통):** A · B 의 증거는 **B 끝 run `R20261115_142018`**(work · `Content/_AutoGen/` — A 의 따오기 · image 그리기 · 되자르기 수정과 B 를 모두 담은 run, `assets/compare/hud_concept_vs_render.png`)과 채록 `work/_extract_probe/A1_20261115/`(입력 · 결과 · `measure.json` · 나란히 그림) · 원인 그림 `work/_extract_probe/A_box_vs_image/box_vs_image.png`만 남겼다. run 1 `R20261115_131656` · run 2 `R20261115_132452` · run 3 `R20261115_135349` · B 첫 run `R20261115_140937`(각 work 11 ~ 12 MB · Content 0.3 ~ 0.7 MB) · run 1 재처리 `A_run_refix` · 진단 그림 · 스크래치 스크립트는 휴지통 — 그 run 들의 숫자는 표로만 남는다.

**A 보강 — 이식(WBP 에서 그려지는 모양) (11-15, 사용자 눈 확인 지적 → 사용자 '지금 고치기')**
- **지적:** 에셋별 나란히 그림(컨셉 ↔ 텍스처)은 맞는데 WBP(디자이너 · `render_sample.png`)는 컨셉과 다르다 — 배너 끝이 뿔처럼 벌어지고 체인 패널 모서리가 크다. **A 의 검증이 '컨셉 ↔ 텍스처'에서 멈춰 이식 단계를 재지 않았다**(내 누락).
- **원인 [소스] `SlateCore/Private/Rendering/ElementBatcher.cpp:857-860`:** box(9-slice) 그리기의 모서리 크기 = **실제 텍스처 픽셀 × margin**(브러시 ImageSize 가 아님), margin 합이 위젯을 넘으면 절반으로 자른다(`:864-873`). analyze 가 장식 프레임을 1.2 ~ 2배 크게 잡으므로 run 2 에서: 배너 텍스처 1024×205 → 위젯 620×124, 위+아래 모서리 62 + 62 = 123 px(높이 124) — **텍스처 가운데 40 % 가 약 1 px 로 눌려** 캡슐 끝 가운데(뾰족한 끝)가 사라지고 모서리는 1.65배 / 체인 패널 674×404 → 337×202, 모서리 87×91 px(컨셉 크기 43×45 — 2배), 가운데 세로 띠 22 px / 게이지 1024×77 → 830×62, 왼쪽 156 px · 오른쪽 65 px. Slate 그리기를 Python 으로 흉내 낸 그림(`work/_extract_probe/A_box_vs_image/box_vs_image.png`)이 디자이너 화면 모양을 그대로 재현했고, 텍스처를 통째로 줄인 판(image)은 컨셉과 거의 같았다.
- **고친 것:** `stages/refine.py _extract_brushes_to_image` — 따온 에셋(source_mode extract)을 쓰는 box/border 브러시를 **위젯 크기가 고정이면 `draw_as: image`(margin 뺌)** 로. 고정 = 최상위 영역(Root 의 자식)이 canvas 점 앵커 + 고정 size(auto_size 아님)이고 그 안의 자식 전부(`fixed_size`). 늘림 앵커 영역은 box 그대로. `pipeline.yaml extract.fixed_size_draw_as: image`(box = 끔), `refine.json brush_updates`. 9-slice margin 추정은 그대로 에셋 margin 에 남는다(크기가 변하는 쓰임을 위해).
- **이식 지표(기록만):** `gen/fidelity.render_vs_concept` · `render_comparisons` — 마지막 시도의 `render.png`(force_visible) ↔ `reference.png` 를 따온 에셋을 쓰는 위젯의 bbox_intent(+4 px) 상자에서: 장식선 F1(테두리 띠, 글자 위젯 자리 제외) · 대표색 ΔE00 · 실루엣 IoU. 렌더는 검은 바탕 불투명이라 비치는 안쪽은 비교하지 않는다. `report.recorded.extract_fidelity.<에셋>.render[]` + `assets/compare/<에셋>_render_<위젯>.png`.
- **고치기 전 기준(run 2 렌더 — box):** 장식선 F1 배너 **0.09** · 체인 패널 **0.20** · 게이지 **0.57**(텍스처 자체는 0.85 · 0.48 · 0.99), 실루엣 IoU 0.74 · 0.93 · 0.87, 대표색 ΔE00 장식선 18.4 · 8.5 · 9.6.
- pytest 227(+2 — box → image 전환 · 늘림 영역은 box 유지, 렌더 지표가 9-slice 왜곡을 잡는지) + 리포트 렌더 비교 경로.
- **실제 run 3 `R20261115_135349_CombatHUD`(image 그리기 · 같은 입력 · 옵션 없음, 4분 44초) [실측]:** analyze 1번(50.0초 · 0.177 USD 환산) — codex 3개 모두 extract → codex 3/20(32.7 · 32.3 · 30.2초) → refine 3.5초(`brush_updates` 3: BurstBanner · ChainPanel · UltGaugeFrame box → image) → build 46.7초 → verify 시도 1 = 8/10(`overlap` — ChainTimerText ↔ ChainCountText 2 px · `iou_leaf` — 배너 안 글자, 둘 다 영역 안 글자 배치로 1b 와 같은 종류 · 영역 편차 ≤ 0.5 px) → 결정적 fixer op 없음 → LLM verifier(50.0초 · 0.311 USD) + fix(29.0초 · 0.227 USD, 8 op — padding) → **시도 2 = 10/10**(iou_leaf 최소 0.789) → 5 패키지 저장 → `quit_editor`(버린 0 · 6.9초). LLM 합계 0.715 USD 환산(구독 — 과금 아님).

  | 이식(WBP 렌더 ↔ 컨셉) | 배너 | 체인 패널 | 게이지 |
  | :--- | :--- | :--- | :--- |
  | 장식선 F1(run 2 box → **run 3 image**) | 0.09 → **0.80** | 0.20 → **0.68** | 0.57 → **0.78** |
  | 실루엣 IoU | 0.74 → **0.95** | 0.93 → 0.93 | 0.87 → 0.88 |
  | 대표색 ΔE00 장식선 | 18.4 → **8.9** | 8.5 → 8.8 | 9.6 → 10.0 |
  | (참고) 텍스처 자체 장식선 F1 | 0.96 | 0.55 | 0.98 |

  - 렌더(`render.png` · `assets/compare/*_render_*.png`): 배너는 컨셉의 캡슐 · 위 왕관 · 뾰족 끝 그대로, 체인 패널 모서리는 컨셉 크기. 남은 차이 = 글꼴(D) · 게이지 채움이 몸통을 덮음(B — 게이지 F1 0.78 의 대부분) · 이번 판 체인 패널 모서리 장식이 컨셉보다 가늘게 따와짐(텍스처 F1 0.55 — 편집 변동, C).
  - 시도 1 의 실패 2개는 글자 배치(padding) 문제로 브러시 그리기 방식과 무관하다 — Border 의 안쪽 배치는 슬롯 padding 이 정하고 브러시 모양은 배치에 끼지 않는다(영역 편차 ≤ 0.5 px).

**A 뒤로 넘길 것 (B · C · D · Phase 2)**
- **크기가 변하는 위젯의 9-slice:** 위 보강은 크기 고정 위젯만 image 로 바꾼다. 늘림 앵커 영역 · 내용 따라 크기가 변하는 칸에서 box 를 쓰면 여전히 '텍스처 픽셀 × margin' 모서리라, analyze 의 '2배까지' 텍스처는 모서리가 커진다 — 그런 쓰임이 생기면 텍스처를 그려질 크기(1×)로 두는 규칙이 필요(B). run 2 의 게이지처럼 VerticalBox 안에서 형제가 숨으면 칸이 늘어나는 경우 image 는 통째로 늘어난다(아래 B ② 항목과 같이).
- **편집 결과는 판마다 다르다**(체인 패널 모서리 · 안쪽 구멍) — 충실도는 기록만이라 run 은 통과한다. **C(외형 검토 라운드)** 가 대표색 ΔE · 장식선 F1 · 구도를 보고 `replace_asset`(extract 재시도)을 낼 자리. 지금 LLM fix 의 `replace_asset` 은 prompt 만 바꾸고 source_mode 는 모른다(재생성은 원래 방식 그대로 — extract 면 extract).
- **게이지 · 빛**(ProgressBar 가 프레임 몸통을 덮음 · 빛 기본 보임)은 B 그대로. 추가로 run 2 analyze 는 '오의 불가'와 게이지를 한 VerticalBox 에 넣어, 샘플 렌더에서 글자가 숨으면 게이지 칸이 세로로 늘어났다(`render_sample.png` 에서 눈으로 약 110 px — 의도 62 px, 게이트는 force_visible 렌더라 통과) — B ②(꺼진 flag 의 초기 가시성)와 같이 본다.
- 장식선 판정(L* ≥ 45 · C* ≥ 20)은 밝은 색 테두리만 잡는다 — 은색 · 어두운 테 컨셉은 Phase 2 보정 세트에서. 출력 비율 상한 3:1 은 관측값(문서 없음). 편집 동작은 '첨부 = 대화에 보이는 그림'에 기대므로 codex 버전이 바뀌면 다시 채록(0.166.0 기준).
- A3(codex 한도) 여전히 미채록 — A 에서 codex 11회(채록 2 · run 3 + 3 + 3), 1b 부터 누적 22회. LLM 은 analyze 3회 + verifier · fix 각 1회 = 1.17 USD 환산(구독 — 과금 아님).

**1b 후속 B 에서 확인 · 정한 것 (11-15, 미커밋 — 사용자: A 세션에서 이어서 · 하위 단계 없이)**

착수 때 정한 것(제안 그대로 승인): 게이지 채움은 **컨셉에서 결정적으로 뽑기**(codex · LLM 없음) · 구조는 지금 것(따온 프레임 Image 아래 + ProgressBar 위, 슬롯 padding 으로 트랙에 맞춤) 유지 — **C++ 변경 · 빌드 없음** · B ② = 꺼진 flag 초기 접힘 + flag 위젯 상자 패널 금지 · **B ③(글자 금색 그라데이션 · 외곽선)은 D 로 미룸**(WidgetMcp C++ 확장 · 빌드가 끼는 글자 작업).

- **메모 원안과 다른 점:** 원안은 '프레임 텍스처를 ProgressBar `style.background`(box 9-slice)로, 채움은 padding 만큼 들임'이었다. ① box 는 A 보강에서 확인한 대로 크기 고정이면 image 가 맞고, ② 채움을 안으로 들이려면 UProgressBar 의 `BorderPadding` 을 spec 어휘 · 역추출 · 시험에 넣어야 해서 C++ 빌드가 낀다. 프레임 Image 를 아래에 깔고 ProgressBar 를 슬롯 padding 으로 트랙에 맞추면 같은 그림이 C++ 없이 나온다 → 구조는 그대로 두고 채움 · 배경만 바꾼다.
- **채움 [소스] `Slate/Private/Widgets/Notifications/SProgressBar.cpp:237-253`:** Slate 는 채움 이미지를 바 전체 크기로 그리고 진행률만큼 잘라 낸다(`bScaleWithFillPerc` 아닐 때) — 가로가 같은 색인 세로 그라데이션 텍스처면 진행률이 바뀌어도 맞다. `fill_color` 기본 흰색(곱 없음).
- **구현(Python 만):**
  - `gen/procedural.py` `gradient_bar` — 세로 색 단계(stops, 위 → 아래 고르게)를 줄마다 보간, 가로는 같은 색. spec 스키마 procedural shape 에 추가.
  - `stages/analyze.derive_gauge_fills` — analyze 가 통과한 뒤: 가로 ProgressBar(left_to_right · right_to_left)의 bbox_intent 안 채워진 부분(샘플 percent, 양끝 4 % 뺌)에서 줄마다 대표색(중앙값) → 색 단계 ≤ 48 → 에셋 `<위젯>_fill`(procedural · `source` 에 뽑은 자리) → `style.fill = image`. 배경은 같은 Overlay 의 앞(아래) 형제가 따온 프레임이면 `none`(프레임의 어두운 트랙이 보이게), 아니면 빈 부분 대표색 `rounded_box`. 기록 `analyze/derived.json`.
  - `stages/analyze.apply_contract` — 샘플이 `false` 인 flag 위젯 `visibility: collapsed`(런타임 setter 와 같은 접힘 — `core/cppgen.py` SETTERS flag). 게이트 렌더는 force_visible 이라 영향 없음, 사람 눈용 `render_sample.png` 는 접힌 채로.
  - `stages/analyze.check` — `FLAG_IN_BOX`: flag 위젯이 VerticalBox · HorizontalBox · UniformGridPanel 의 직계 자식이면 거부(1회 재요청) — 런타임에 접히면 형제가 움직인다(run 2 · 3 의 '오의 불가' + 게이지 VerticalBox). `prompts/analyze.md` 에 같은 규칙 + '틀 있는 게이지 = Overlay(프레임 Image 먼저, ProgressBar 위 · padding 으로 트랙)'.
  - `gen/fidelity.gauge_vs_concept` + `run_pipeline._gauge_fidelity_summary` — 채운 · 빈 부분의 컨셉 ↔ 렌더 대표색 ΔE00 · 픽셀별 평균 · **줄 단위**(줄마다 대표색 — 세로 그라데이션을 본다) → `report.recorded.gauge_fidelity`.
- **고치기 전 기준(run 3 렌더 — 단색 `#F2B544` 채움 · 어두운 rounded_box 배경):** 채운 부분 대표색 ΔE00 4.58 · 픽셀별 평균 12.9(p95 47.3) · **줄 단위 평균 12.1 · 최대 51.4**, 빈 부분 대표색 1.78 · 줄 단위 평균 2.1. 단색이어도 중앙값은 맞아 대표색은 작게 나온다 — 그라데이션 차이는 줄 단위가 보여 준다.
- pytest 234(+7 — `tests/test_gauge.py`: gradient_bar · 채움/빈 부분 색 뽑기 · 따온 프레임 아래면 배경 none · right_to_left · 너무 작으면 건너뜀 · 꺼진 flag 접힘 · FLAG_IN_BOX · 줄 단위 지표).
- **실제 run B1 `R20261115_140937_CombatHUD`(4분 53초) [실측]:** analyze 1번(50.7초 · 0.257 USD) — `FLAG_IN_BOX` 재요청 없이 '오의 불가'를 자기 영역(Root 의 캔버스 자식)으로 · 게이지 = Overlay(UltReadyGlow · UltFrame · UltGauge) · `derive_gauge_fills` 가 UltGauge 채움(색 단계 40, x 611 ~ 1083)과 배경 none(UltFrame 아래) → codex 3/20 → 시도 1 = 9/10(`iou_leaf` — 배너 안 글자 행 폭, B 와 무관) → LLM verifier · fix(6 op) → **시도 2 = 10/10**(iou_leaf 최소 0.988). 꺼진 flag 3개(BurstBanner · UltBlockedText · UltReadyGlow) `collapsed`. **게이지 채움: 줄 단위 ΔE00 평균 12.1 → 1.8 · 최대 51.4 → 13.3, 픽셀별 12.9 → 5.3, 대표색 4.6 → 0.9.** 빈 부분은 대표색 1.8 → 5.6 · 줄 단위 2.1 → 6.2 로 나빠짐 — 배경 none 이라 프레임의 반투명(0.9) 트랙이 검은 바탕 렌더 위에서 컨셉(장면 위)보다 어둡게 나오는 몫이 섞여 있다(렌더 지표의 한계, 게임에서는 장면 위).
- **run B1 에서 찾은 A 결함 — 따온 텍스처 되자르기:** 렌더에서 게이지 왼쪽 끝 캡이 채움에 덮여 안 보였다. 원인: 따온 텍스처를 '요소 상자 + 여유'로 되자른 뒤 trim(알파 > 8)하면 끝 캡 바깥의 옅은 빛(알파 8 ~ 128)이 남아, 텍스처 안의 프레임이 위젯보다 좌우 27 · 28 px 씩 작게 그려졌다(캡이 화면 576 px — 채움은 581 px 부터). 텍스처 단계 지표는 알파 > 128 모양 상자로 맞춰 재서 못 잡았다. → **refine 이 따온 텍스처를 그 에셋을 쓰는 위젯의 bbox_intent 상자 그대로 되자르고 trim 하지 않는다**(`refine.extract_target_box` — 텍스처 = 위젯 1:1, 컨셉 위치 그대로). B1 원본 재처리: 좌우 틈 27.3 · 28.1 → 0 px. 바짝 자르면 프레임이 그림 가장자리에 닿아 형태 연산(close — 침식 테두리값이 최대)이 가장자리를 메우고 distanceTransform 이 그림 밖을 바깥으로 치지 않는 함정이 있어, `fidelity.fill_shape` · `_ring` · `postprocess.interior_fill` 이 마스크에 0 테두리(8 px)를 덧대고 계산한다(그대로였으면 장식선 F1 0 · 가장자리 어두운 띠를 안쪽으로 칠함). pytest 235(+1 — 가장자리에 닿은 프레임).
- **실제 run B2 `R20261115_142018_CombatHUD`(되자르기 수정 뒤 · 같은 입력 · 옵션 없음, 4분 50초) [실측]:** analyze 1번(50.9초 · 0.177 USD — 재요청 없음, 꺼진 flag 3개 collapsed · '오의 불가'는 자기 영역) → codex 3/20 → refine(따온 3장 모두 위젯 상자 그대로 되자름 · trim 없음) → 시도 1 = 9/10(`iou_leaf` — 배너 안 글자 행, B 와 무관) → LLM verifier(42.1초 · 0.257) + fix(45.7초 · 0.282, 4 op — padding · 정렬) → **시도 2 = 10/10**(iou_leaf 최소 0.776) → 6 패키지 저장 → `quit_editor`(버린 0 · 6.4초). LLM 합계 0.716 USD 환산(구독 — 과금 아님).

  | 렌더 ↔ 컨셉(기록만) | A run 3(image) | **B2** |
  | :--- | :--- | :--- |
  | 장식선 F1 — 배너 · 체인 패널 · 게이지 프레임 | 0.80 · 0.68 · 0.78 | **0.98 · 0.90 · 0.96** |
  | 실루엣 IoU — 같은 순서 | 0.95 · 0.93 · 0.88 | **0.99 · 0.97 · 0.97** |
  | 텍스처 구도(중심 차) | 0.5 ~ 6 px | **0 px 셋 다** |
  | 게이지 채움 줄 단위 ΔE00 평균 · 최대 | 12.1 · 51.4 | **1.8 · 15.1** |
  | 게이지 채움 대표색 · 픽셀별 평균 | 4.6 · 12.9 | **0.6 · 5.2** |
  | 게이지 빈 부분 대표색 | 1.8 | 5.8(배경 none — 반투명 트랙 · 검은 바탕 렌더) |

  - 눈 확인(내 확인 — `assets/compare/hud_concept_vs_render.png` · `*_render_*.png`): 배너 캡슐 · 위 왕관 · 뾰족 끝, 체인 패널 모서리, 게이지 양끝 캡 · 금색 그라데이션 채움이 컨셉과 겹친다. 남은 차이 = 글꼴(컨셉 세리프 · 빛나는 숫자 ↔ Pretendard — D) · 배너 글자 사이 간격(LLM fix padding) · 컨셉 채움의 왼쪽 '<' 모양 끝(지금 채움은 사각).
- **B 뒤로 넘길 것:** ① 빈 부분 배경 — 지금은 따온 프레임이 아래 있으면 none(프레임 트랙이 보임). 렌더 지표가 검은 바탕이라 비치는 트랙이 어둡게 잡힌다 — 게임 화면(장면 위)에서 맞는지는 사람 눈 · C 의 장면 합성 비교로. 컨셉 대표색으로 칠하는 쪽(`rounded_box`)은 코드에 있는 다른 갈래(프레임이 없을 때). ② 채움 끝 모양(컨셉 '<')은 채움 텍스처 · 브러시 모양 문제 — 필요하면 C 의 스타일 라운드나 따오기(채움도 extract)로. ③ B ③ 글자 금색 그라데이션 · 외곽선 → D 와 같이(WidgetMcp C++). ④ 세로 게이지(top_to_bottom 등)는 채움 뽑기를 건너뛴다(가로만).

**1b 후속 D 에서 확인 · 정한 것 (11-15, 미커밋 — 사용자: 남은 D · C 를 새 세션에서 차례로 · 하위 단계 없이 · 그라데이션 포함 · 내려받기 승인)**

착수 때 정한 것(제안 그대로 승인): 제목 · 숫자 = Noto Serif KR(OTF) · 역할별 폰트(analyze 가 `font.role` → `apply_contract` 가 family) · 글자 효과 어휘 4종(outline · shadow · letter_spacing · gradient) · 그라데이션은 run 폴더 안 UI 머티리얼 + MIC(**Config 변경 없음**) · 글자색 · 그라데이션은 컨셉에서 결정적으로(B 의 게이지 채움과 같은 방식).

- **폰트 내려받기(사용자 승인):** 공식 `github.com/notofonts/noto-cjk` `Serif/SubsetOTF/KR/NotoSerifKR-Regular.otf` 7,669,020 B · `NotoSerifKR-Bold.otf` 7,910,236 B · `Serif/LICENSE` 4,301 B(SIL OFL 1.1) — 크기는 GitHub API 로 미리 밝히고, 스크래치의 새 폴더에 받아 크기 · 머리('OTTO') 확인 → `Tools/uigen/work/_fonts/notoserifkr/`(git 무시) · 라이선스 `Content/UI/Fonts/NotoSerifKR/OFL.txt`. **[실측]** 공식 저장소에는 정적 TTF 가 없다(google/fonts 는 가변 폰트 하나) → 정적 OTF(CFF). 엔진 임포트 · `import_font_family` 모두 OTF 를 받고(`EditorFactories.cpp:5065` · `WidgetMcpFonts.cpp:143`), 렌더 · 한글 · 숫자 모두 그려졌다.
- **임포트:** `import_font_family` → `/Game/UI/Fonts/NotoSerifKR/` 에 `FF_NotoSerifKR_Regular` · `FF_NotoSerifKR_Bold` · `F_NotoSerifKR` 저장(sub-face 'Noto Serif KR (Regular/Bold)', 바깥 더티 0).
- **줄 높이 재측정 [실측]** (TextBlock auto_size 높이, regular · bold 같음): Noto Serif KR 16→31 · 18→35 · 22→43 · 26→51 · 30→58 · 34→66 · 44→86 · 56→109 · 80→155(크기 × 약 1.94 — Pretendard 의 1.62 보다 크다), Pretendard 표를 큰 크기까지 늘림 44→71 · 56→90 · 80→129(1b-4 의 '34 까지' 남은 일). 같은 글자열('체인 버스트 4.2 Ag', regular) 폭은 Noto 가 Pretendard 보다 4.7 ~ 8.5 %(대개 약 7 %) 넓다. → `pipeline.yaml fonts.line_height`(body) · `fonts.roles.title{family, line_height}`.
- **역할별 폰트:** `core/config.font_roles` — body = 요청 폰트 또는 `fonts.default_family`, 그 밖 역할 = `fonts.roles.<역할>`. analyze 프롬프트는 역할마다 폰트 · 용도 · 줄 높이 표를 주고(`analyze.font_lines`), LLM 은 TextBlock 마다 `font.role`(body | title)만 고른다 → `apply_contract` 가 family 경로로 바꾸고 role 을 지운다(모르는 역할 · 없음 = body). spec · WBP · 왕복은 지금처럼 `font.family` = 경로. 남은 role 은 의미 검사 `FONT_ROLE`. fix 프롬프트의 줄 높이 문장은 spec 이 쓰는 폰트마다(`fix._line_height_note`).
- **글자 효과 어휘(WidgetMcp C++ — 사용자 승인):** spec `font.outline{size, color}`(FSlateFontInfo.OutlineSettings) · `font.shadow{offset, color}`(TextBlock ShadowOffset · ShadowColorAndOpacity) · `font.letter_spacing`(1/1000 em) · `font.gradient{top_color, bottom_color}`. **기본값이면 정규화가 키를 지운다**(outline size 0 · shadow 알파 0 · 자간 0 · gradient null) — 효과 없는 spec 의 정규형 · revision 이 예전과 같다(1a · 1b 픽스처 왕복 그대로). 같은 규칙을 `core/spec.normalize_font_effects` 와 `WidgetMcpSpec.cpp NormalizeTextEffects` 에 두고, 검사(외곽선 0 ~ 1024 정수 · 색 · offset [x, y] · 자간 −1000 ~ 10000) · 적용(없으면 엔진 기본으로 되돌림 — 적용은 목표값 전부) · 역추출(기본값이 아닐 때만 · 지원 안 되는 외곽선 옵션 · 다른 FontMaterial · Skew 는 unsupported)을 맞췄다. 예전에 '지원 안 됨'으로 적던 외곽선 · 자간이 정식 어휘가 됐다.
- **그라데이션 [소스 · 실측]:** `ElementBatcher.cpp:3780-3790` — 폰트 머티리얼이 있으면 글자 사각형마다 줄 기준 UV(U = 글자 순번/글자 수, V = 줄 위 0 → 아래 1)를 넘기고, 머티리얼에서 **TexCoord[0]** 으로 읽힌다(빨강 위 → 파랑 아래 시험 글자로 확인). 새 파일 `WidgetMcpTextMaterials` — 조정기가 **적용 직전에만**(미리보기 · 거부된 요청은 안 만듦) WBP 의 run 폴더에 부모 `M_TextGradient`(UI 도메인 · 반투명 · Final Color = Lerp(TopColor, BottomColor, saturate((V − VTop) / (VBottom − VTop))))와 색 쌍마다 `MI_TextGradient_<위>_<아래>` 를 찾거나 만들고, 적용은 키로 찾아 FontMaterial 에 넣는다(`FAssets.TextGradients`). 역추출은 MIC 매개변수로 되읽는다. 저장 · 폐기는 run 폴더 일괄(save_widget_run · discard_run_packages)이 같이 한다. 그라데이션 색의 알파는 쓰지 않고, 쓸 때 `font.color` 는 흰색(틴트 없음 — 알파만 유지).
  - **[실측] 함정 1 — 셰이더 없음:** `PreEditChange` / `PostEditChange` 만으로 만든 머티리얼은 Slate 셰이더가 없어 Slate 가 그 글자 배치를 건너뛰었다(`SlateRHIRenderingPolicy.cpp:1094-1112` — 폴백도 UI 도메인이 아니라 못 그림 → 렌더에 외곽선만 보임 · 회색 바탕에서도 채움 0 px). `ForceRecompileForRendering()` + 셰이더 컴파일 대기(`GShaderCompilingManager->FinishAllCompilation()`) 뒤 그려졌다. 컴파일 오류가 있으면 적용 오류 `TEXT_MATERIAL`, apply 결과에 `text_materials[]`(UI 도메인 · 셰이더 맵 · 컴파일 완료 · 오류 수) 진단. render_widget 도 그리기 전에 셰이더 컴파일을 기다린다(에디터를 새로 띄워 저장된 MIC 를 불러올 때 대비).
  - **[실측] 함정 2 — V 는 줄 상자 기준:** 글자 획(5 ~ 95 % 분위)은 줄 상자의 Noto Serif KR 0.29 ~ 0.81 · Pretendard 0.21 ~ 0.79 에 있어, 그대로면 글자 몸통에 가운데 색만 걸렸다(빨강 → 파랑 시험의 위 띠 R 212 · 아래 띠 R 132). VTop 0.25 · VBottom 0.80(두 폰트 절충 — 부모 머티리얼 매개변수)으로 다시 펴서 위 띠 R 236 · 아래 띠 R 68.
- **글자색 · 그라데이션을 컨셉에서 뽑기(`analyze.derive_text_fills` — LLM · codex 없음, `pipeline.yaml text_fill.enabled`):** TextBlock bbox_intent 안에서 글자 획(`fidelity.text_ink` — L* 를 Otsu 로 둘로 나눠 **적은 쪽**, 문턱에서 끝값 쪽으로 30 % 들인 획 안쪽)을 찾아 위 25 % 줄 ↔ 아래 25 % 줄 대표색 ΔE00 ≥ 8 이면 gradient(+ color 흰색), 아니면 color = 획 대표색. 기록 `analyze/derived.json text_fills`. **[실측 — 증거 run R20261115_142018 의 reference · spec 에 돌린 것]** 배너 '체인 버스트' LLM `#F2DFB0`(연한 크림) → **`#E7AE4E`(컨셉 금색)** · 체인 제목 `#F0E2C0` → `#EAB34F` · '4.2' `#F7E8CA`(그대로에 가까움) · '오의 불가' `#F25331` · '2/4' 그라데이션 `#EFECE0 → #D9CAC0`(ΔE00 9.5). 컨셉의 금색 글자는 획 안쪽이 거의 한 색이라(위 ↔ 아래 ΔE00 1.6 ~ 1.8) 그라데이션이 아니라 단색으로 뽑혔다 — 눈에 보이는 '금빛'은 색 차이보다 외곽선 · 그림자 · 빛 몫이 크다(C 라운드 몫).
  - **[실측] 함정 — 상자에 걸친 금테:** '2/4' 상자 아래쪽에 패널 금테 · 모서리 장식이 걸려 처음엔 가짜 그라데이션(ΔE00 28.4, 아래 = 금색)이 나왔다 → `_text_band`: 폭 60 % 넘게 칠해진 줄(가로선) 지움 · 상자 좌우 끝에 닿은 덩어리 지움(남는 획이 절반 이상일 때) · 가장 큰 덩어리의 10 % 미만 잔조각 지움 · 빈 줄 3 개까지 이은 줄 띠 중 가장 큰 띠만. 그 뒤 9.5.
  - **[실측] 함정 — 양자화:** 바탕이 한 값이면 Otsu 문턱 = 바탕 값이라 실수 L* 로 비교하면 바탕이 '밝은 쪽'이 됐다 → Otsu 와 같은 8비트 L 로 가른다.
- **analyze 프롬프트:** Text 절 — role 고르기 · '파이프라인이 글자색을 다시 뽑는다(그래도 최선의 color)' · 효과는 보일 때만(outline 1 ~ 4 px · shadow · letter_spacing 50 ~ 150).
- **시험:** pytest 245(235 → +10 `tests/test_text_style.py` — 역할 설정 · role → family · FONT_ROLE · 프롬프트 표 · 효과 정규화 · 왕복 · 그라데이션 / 단색 뽑기 · 획 찾기 · fix 줄 높이 문장). WidgetMcp `BuildRoundTrip` 에 효과 왕복(외곽선 · 그림자 · 자간 · 그라데이션 · run 폴더 MIC · 효과 없는 글자에 키 없음) — `WidgetMcp.` 6/6. DebugGame 빌드 4번(링크 RHI 추가 · 셰이더 대기 · 재매핑 — 마지막 `Result: Succeeded`).
- **바뀐 C++:** `WidgetMcpTextMaterials.{h,cpp}`(새) · `WidgetMcpSpec.{h,cpp}` · `WidgetMcpBlueprint.cpp`(적용 전 Prepare · text_materials 진단) · `WidgetMcpRender.cpp`(셰이더 대기) · `WidgetMcpEditor.Build.cs`(+RHI — GMaxRHIShaderPlatform) · `WidgetMcpToolTests.cpp`.
- **실제 run D1 `R20261115_154416_CombatHUD`(옵션 없음 · 같은 컨셉, 3분 28초) [실측]:** analyze 1번(61.7초 · 0.303 USD 환산 — 구독, 과금 아님)이 글자 6개 중 5개를 `title`(배너 · 카운트 · 체인 제목 · 4.2 · 2/4), '오의 불가'를 `body` 로 골랐고, 그림자(`[1, 2]` · `#000000AA`) 4개 · 배너 자간 50 을 넣었다(외곽선은 고르지 않음). `derive_text_fills` = 단색 6 · 그라데이션 0 → codex 3/20 → 시도 1 = 9/10(`iou_leaf` BurstCountText — 세리프 라벨이 의도보다 넓어 가운데 정렬 행이 밀림, 1b 와 같은 종류) → LLM verifier(25.1초 · 0.223) + fix(14.3초 · 0.147, 1 op — 카운트 padding 0) → **시도 2 = 10/10** → 6 패키지 저장. LLM 합계 0.673 USD 환산.

  | 렌더 ↔ 컨셉(기록만, force_visible 렌더) | B2 `R20261115_142018` | **D1** |
  | :--- | :--- | :--- |
  | 글자 획 대표색 ΔE00 — 배너 · 카운트 · 체인 제목 · 4.2 · 2/4 · 오의 불가 | 15.87 · 1.98 · 18.35 · 1.74 · 2.95 · 3.99 | **0.85 · 0.98 · 1.17 · 0.38 · 0.52 · 0.25** |
  | 글자 획 높이 비(렌더 / 컨셉) — 배너 · 카운트 · 4.2 · 오의 불가 | 0.96 · 0.78 · 1.06 · 0.84 | 1.18 · 0.92 · **0.80** · 1.08 |
  | 장식선 F1 — 배너 · 체인 패널 · 게이지 프레임 | 0.98 · 0.90 · 0.96 | 0.88 · 0.97 · 0.99 |
  | 게이지 채움 줄 단위 ΔE00 평균 · 빈 부분 대표색 | 1.8 · 5.8 | 1.8 · 6.5 |

  - 눈 확인(내 확인 — `assets/compare/hud_concept_vs_render.png`, 위에서부터 배너 · 체인 패널 · 게이지, 왼쪽 컨셉 · 오른쪽 렌더): 배너 '체인 버스트' · 체인 '체인'이 컨셉처럼 **세리프 금색**, 4.2 · 2/4 · 3 도 세리프. 남은 차이 = '4.2' · '2/4' 가 작고 덜 굵다 · 배너 '버스트'와 '3' 사이가 붙음(자간 50 + 넓은 세리프 + fix 의 padding 0) · 컨셉 글자의 빛 · 금빛 입체감(그림자만으로는 약함).
  - **글자 크기 원인 [실측]:** Noto Serif KR 은 줄 높이(크기 × 1.94)에 비해 글자 몸통이 작아(줄 상자의 0.29 ~ 0.81) '상자 높이 = 줄 높이'로 고른 크기는 컨셉보다 글자가 작다(4.2: 상자 101 px → 크기 52 → 획 높이 53 px, 컨셉 66 px). 두 폰트 모두 **보이는 글자 높이 ≈ 크기 px**(Noto 1.01 × · Pretendard 0.94 ×)라서, analyze 프롬프트를 '글자 높이로 크기를 고르고 bbox_intent 는 그 크기의 줄 상자(글자 가운데)'로 고쳤다(`analyze.font_lines` · `prompts/analyze.md`) — **이 run 뒤의 수정이라 C · 끝 run 에서 확인한다.**
  - 측정 주의: 컨셉 글자 상자를 4 px 넓혀 자르면 체인 제목 · 2/4 처럼 패널 금테에 붙은 상자는 획 찾기가 금테를 섞는다(위 표에서 뺀 두 값) — C 의 글자 지표는 상자를 넓히지 않고, 가장자리 덩어리 제거(`_text_band`)에 기댄다.

**1b 후속 C 에서 확인 · 정한 것 (11-15, 미커밋 — 사용자: D 보고 뒤 'C 시작')**

- **흐름(§2-2 '통과 뒤 외형 라운드' · §8-3 '두 가지 모드'):** 게이트가 모두 통과하면 `run_pipeline._style_review` — concept 모드면 영역 · 글자 비교를 늘 기록(`style/before/report.json` + 영역마다 '컨셉 | 렌더' 그림, 글자 상자 노랑) → 라운드(`pipeline.yaml style_review.rounds` 기본 1, fix.mode deterministic 이면 0): `style_verifier` → `style_fix` → 가드 · 사본 적용 → `patches/style_00k.json` → (에셋 교체면 generate → refine) → build → verify. 통과면 받고(`style/round_00k`), 하나라도 깨지면 버린다 — 라운드 전 사본(`style/round_00k_backup` — manifest · refine.json · 교체 에셋의 final/raw/compare PNG)과 마지막 통과 spec 으로 되돌리고 `build.reset_run`(discard_run_packages 로 run 패키지 전부 버림 + build 상태를 '세션이 바뀐 것'처럼 비움) → 처음부터 build → verify(통과해야 함 — 아니면 `STYLE_REVERT_FAILED`) → finalize. **설계 세션 메모의 'rebuild 뒤 저장'을 'run 패키지를 전부 버리고 다시 build'로 했다** — 조정기만 다시 돌리면 라운드가 만든 텍스처 · 그라데이션 MIC 가 run 폴더에 남아 save_widget_run(run 폴더 일괄)이 같이 저장한다(WidgetMcp 에 패키지 골라 버리기가 없어 C++ 변경 없이 푼 방법).
- **허용 op(가드 `style.guard_style_ops` — fix 의 가드 위에):** set 경로 = `style.*` · `font.color|weight|size|family|outline(.*)|shadow(.*)|letter_spacing|gradient(.*)` · `slot.padding` · `justification`, `font.family` 는 설정된 역할 폰트만, `replace_asset` 은 codex 에셋만 · `regenerate: true` · 라운드당 1(`max_replace_per_round`)이면서 run 의 codex 남은 수 이하, op ≤ 16(`max_ops`), 그 밖 op 종류 거부. 거부되면 오류를 붙여 1회 다시, 또 안 되면 라운드 없음(`no_ops`).
- **영역 비교(§8-2 '기록만' — `gen/fidelity.region_report`):** 루트 직계 영역마다 장식선 F1 · 실루엣 IoU · 선 대표색 ΔE00 · 영역 대표색(글자 상자 뺌), 글자마다 획 상자(`text_vs_concept` — 크기 비 · 중심 차) · 획 대표색 ΔE00, 게이지 채움 · 빈 부분, 요약 `report_summary`. **메모와 다른 점: 렌더는 '샘플 보이기 상태'가 아니라 force_visible `render.png`** — 샘플 렌더는 꺼진 flag(배너 · '오의 불가')를 접지만 컨셉에는 보이기 때문. 렌더는 검은 바탕이라 비치는 안쪽은 영역 대표색에 섞인 채 기록한다(장면 합성 비교는 하지 않음 — 아래 '넘길 것').
- **프롬프트:** `prompts/style_verifier.md`(검은 바탕 · 비치는 안쪽 · 배치는 무시, 글자 → 상자 안 간격 → 프레임 → 게이지 순, 글자 높이 비로 새 크기 = 크기 / 비, 찾은 것 ≤ 8) · `prompts/style_fix.md`(허용 op 문법 · 그라데이션이면 color 흰색 · 크기를 키우면 줄 높이가 bbox_intent 의 1.3 배를 넘지 않게 — 넘으면 말단 게이트가 깨져 라운드가 버려짐). 사용자 프롬프트에 영역 그림 경로 · 지표 표 · 역할 폰트 · 줄 높이 · codex 남은 수.
- **시험:** pytest 253(245 → +8 `tests/test_style.py` — 허용 · 거부 경로 · 폰트 · 에셋 교체 상한 · 영역 비교 · 배치 op 거부 뒤 재요청 통과 · 찾은 것 없음 · **오케스트레이터에서 받기 / 버리기**(가짜 에디터 — 버리면 discard → WBP 를 다시 만들고 저장, 최종 spec = 마지막 통과) · deterministic 이면 비교만).
- **실제 run C1 `R20261115_160430_CombatHUD`(옵션 없음 · 같은 컨셉 — 끝 run, 6분 46초) [실측]:** analyze 1번(54.1초 · 0.213 USD 환산 — 구독, 과금 아님) → codex 3/20 → 시도 1 = 9/10(`iou_leaf` — 배너 행) → LLM verifier(0.211) + fix(0.169, 2 op) → **시도 2 = 10/10** → 비교 기록(before) → **외형 라운드 1**: style_verifier(27.5초 · 턴 7 · 0.183) + style_fix(39.6초 · 0.188, 가드 1번에 통과) → 7 op: 배너 라벨 크기 44 → 42 · 카운트 padding 왼쪽 20 · 카운트 크기 56 → 61 · '4.2' 그림자 `[0, 0]` `#D88A2EAA`(빛 대신) · '2/4' 크기 → 23 · '오의 불가' 외곽선 2 `#3A0C06D0` · **체인 패널 프레임 replace_asset**(프롬프트 '가는 금테 · 연보라 안쪽 선 · 모서리 장식 그대로') → generate(codex 4/20, 47.3초) → refine → build → **시도 3 = 10/10 → 받음** → 7 패키지 저장. LLM 합계 0.964 USD 환산.

  | 렌더 ↔ 컨셉(기록만) | 라운드 전(시도 2) | **라운드 뒤(시도 3)** |
  | :--- | :--- | :--- |
  | 글자 획 높이 비 오차 평균 \|1 − r\| · 폭 비 오차 | 0.094 · 0.177 | **0.046 · 0.113** |
  | 배너 라벨 · 카운트 · '2/4' 높이 비 | 1.184 · 0.921 · 1.172 | 1.122 · 0.984 · 1.034 |
  | 체인 패널 장식선 F1 · 선 대표색 ΔE00 | 0.899 · 12.19 | **0.978 · 2.59** |
  | 글자 획 대표색 ΔE00 평균 | 0.43 | 0.43 |
  | 영역 대표색 ΔE00 평균(비치는 안쪽 포함) | 7.37 | 7.88 |
  | 게이지 채움 줄 단위 ΔE00 | 1.79 | 1.79 |

  - **D 의 프롬프트 수정 확인:** '4.2' 획 높이 비 0.80(D1) → **0.985**(C1 라운드 전 — analyze 가 글자 높이로 크기를 골랐다).
  - 눈 확인(내 확인 — `assets/compare/hud_concept_vs_render_before_style.png` · `hud_concept_vs_render.png`): 배너 '버스트'와 '3' 사이가 벌어지고 '3' · '4.2' 크기가 컨셉과 같아졌다, 체인 패널 테두리가 덜 노랗다(컨셉의 바랜 금색), '오의 불가'에 어두운 테.
  - 받은 라운드에 에셋 교체가 있으면 옛 텍스처(`T_chain_panel_frame`)는 쓰이지 않은 채 같이 저장된다(재시도 replace_asset 과 같은 동작 — git 무시 폴더).
- **실제 에디터에서 '버리기' 확인 [실측]:** 회귀 세션에서 스크래치 스크립트로 텍스처 · WBP · 그라데이션 MIC 를 만들고 → `discard_run_packages` → 같은 이름으로 다시 임포트 · 생성 · 적용 · 렌더 — 두 번 모두 적용 검증 통과 · 머티리얼 컴파일 · 렌더 글자 픽셀이 같다(빨강 470 · 파랑 583), 두 번 다 4 패키지 버림 · 남은 더티 0. 파이프라인 안의 되돌림 경로 전체는 가짜 에디터(pytest)로만 돌았다 — 실제 run 에서는 라운드가 게이트를 깨지 않았다.
- **D · C 끝 회귀(필수만, 11-15) [실측]:** 빌드 Development `-DisableAdaptiveUnity`(WidgetMcp 4 작업 · 30.5초) · DebugGame(최신) 모두 `Result: Succeeded` → 에디터 1회(DebugGame, 끝 run 뒤 새로 띄움): 위 '버리기' 확인 → `AstralBreak.` **55/55**(시험 시간 합 393초) → `EditorMcpCore.` 2/2 → `WidgetMcp.` 6/6 → `quit_editor`(버린 것 = `WidgetMcp.Spike` 시험의 WBP 1개) · 소멸 확인. pytest **253**.
- **사람 눈 확인(11-15, 사용자 — 끝 run `hud_concept_vs_render.png` · 게이지 왼쪽 끝 확대 비교):** 글꼴 · 글자는 대체로 괜찮다, 단 **상단 '체인 버스트' 글자 크기가 컨셉과 약간 다르다**(지표로도 획 높이 비 1.12 — 라운드가 44 → 42 로만 줄임, 말단 게이트 여유 때문에 한 번에 37 까지 못 내림). **게이지 채움의 왼쪽 끝이 다르다** — 컨셉은 채움이 프레임 안쪽 '<' 모양 끝까지 차고 안쪽 밝은 테두리가 있는데, 렌더는 채움이 사각형으로 끝 캡 앞에서 잘리고 위아래에 어두운 트랙이 보인다(B '뒤로 넘길 것 ②'). **글자 · 게이지의 빛나는 느낌(번지는 빛 · 그라데이션)이 없다**(C '뒤로 넘길 것 ②'). 두 항목은 지금 어느 단계에도 맡겨져 있지 않다(아래 '넘길 것').
- **증거 정리(11-15 사용자 승인 — 휴지통):** D · C 의 증거는 **끝 run `R20261115_160430`**(work · `Content/_AutoGen/`)과 D 단독 run `R20261115_154416`(D 표의 비교 그림), 폰트 원본 `work/_fonts/notoserifkr` 을 남겼다. 줄 높이 · 그라데이션 측정 렌더 `work/_fonts/measure_D_*` 6폴더 · 실제 에디터 '버리기' 확인 렌더 `revert_C_*` 2폴더(합계 3.6 MB) · 스크래치(스크립트 · 내려받은 폰트 사본 · 진단 그림, 16 MB)는 휴지통 — 숫자는 위 기록으로만 남는다.
- **비용(구독 — 과금 아님):** D · C 에서 LLM(API 정가 환산) D1 0.673 · C1 0.964 USD, codex D1 3 · C1 4 = 7회(1b 부터 누적 35회 — A 기록 22 + B run 2번 6 + 이번 7, 한도 걸림 0).
- **C 뒤로 넘길 것:** ① 비치는 안쪽 · 빈 게이지 트랙 비교 — 렌더가 검은 바탕이라 영역 대표색 ΔE00 이 이 몫만큼 크다(장면 합성 비교 또는 알파 렌더). ② 컨셉 글자의 빛(번짐) — Slate 그림자는 번지지 않아 오프셋 0 그림자로 흉내만(번지는 빛은 글자 머티리얼 · 후처리 몫 — 범위 밖). ③ 라운드는 1회 — 2회째의 득실은 미측정(설정만 있음). ④ 영역 비교 · 외형 지표를 게이트로 올리는 일은 Phase 2(보정 세트) 그대로. ⑤ 받은 라운드의 옛 텍스처를 저장에서 빼려면 WidgetMcp 에 '패키지 골라 버리기'가 필요(C++).

**1b 후속 F 에서 확인 · 정한 것 (11-15, 미커밋 — 사람 눈 판정의 외형 차이 셋: 게이지 채움 모양 · 빛 · 배너 글자 크기. 사용자: 새 세션에서, 하위 단계 없이, 진행 끝 C++ · SDF 글자 빛(Config 2줄 · 새 폰트 애셋 · C++) 승인)**

착수 때 정한 것(제안 그대로 승인 — 조사 · 시제품 뒤): 게이지 채움은 컨셉 모양 그대로 따오기(codex 없음) + 진행 끝은 `BarFillStyle::Scale` + 채움 9-slice(C++) · 글자 빛은 엔진 거리장(SDF) 글꼴 + 외곽선 층 빛 머티리얼(RetainerBox + 흐림은 무겁고 오프스크린 렌더에서 불확실해 뺌) · 배너 크기는 analyze 의 글자 높이 비 정정 + 외형 라운드에서 글자 상자가 크기를 따라가게.

- **원인 확인 [실측 — C1 끝 run 컨셉 6배 확대]:** 컨셉 채움 = ⓐ 왼쪽 '<' 끝(프레임 안쪽 모양을 따름) ⓑ 몸통 둘레 1 ~ 2 px 밝은 테두리 ⓒ 몸통 ↔ 프레임 선 사이 띠(위 6 · 아래 5 px)가 빈 트랙보다 밝음(L 58 ~ 81 vs 35 ~ 50 — 빛 번짐, 띠 안에 빛 받은 경사면 밝은 줄 L 100 ~ 200) ⓓ 진행 끝 세로 밝은 테두리 + 빈 트랙으로 약 24 px 번짐. B 의 렌더는 LLM 막대 상자(34 px — 띠 뺌)에 줄마다 색만 뽑은 사각형이라 넷 다 없었다. 글자: 획 바깥 거리별 밝기를 재면 **뚜렷한 빛은 '4.2' 하나**(획 2 ~ 8 px 이 바탕보다 L +11 ~ 17), 나머지 5개는 빛이 아니라 1 ~ 2 px 어두운 테(L −8 ~ −16 — 범위 밖, 기록만). 배너: style_fix 가 37 대신 42 를 고른 이유는 그 reason 에 그대로 — '37 이면 옛 bbox_intent(44 기준 줄 상자)와 말단 IoU < 0.70'. analyze 프롬프트의 '보이는 글자 높이 ≈ 크기'는 숫자에만 맞고 한글은 Noto Serif KR 에서 1.32 ~ 1.35 × 크기(렌더 실측 배너 58/44 · 체인 35/26, 숫자 '4.2' 65/64 · '3' 62/61, Pretendard 한글 '오의 불가' 35/30).
- **[소스] 진행바 · 9-slice:** `SProgressBar.cpp:141-157 · 161-253` — 채움은 진행률 자리에서 클립으로 딱 자르고(Mask), `Scale` 이면 칠할 폭 = W·p(그림 전체를 그 폭으로). `ElementBatcher.cpp:857-867` — box 여백은 텍스처 픽셀 × margin 고정, 여백 합 > 폭이면 양쪽 반반으로 눌림. 그래서 '양끝 고정 · 가운데 늘림' 채움 텍스처를 Scale 로 그리면 진행 끝 테두리 · 번짐이 진행률을 따라간다(진행률 7 % 아래에서는 양끝이 눌림).
- **[소스] SDF 글자 빛:** `SlateElementPixelShader.usf:275-335` — 거리장 글꼴이면 글꼴 · 외곽선 머티리얼이 `FontSignedDistance` 노드(`MaterialExpressionFontSignedDistance.h` — x = 외곽선 경계 기준 em 부호 거리, 안 = +)를 받고, 비스텐실이면 최종 알파 = 머티리얼 불투명도 × 거리장 불투명도. `FontCache.cpp:1346-1349` — 외곽선 크기만큼 거리장 바깥 퍼짐이 늘어난다(상한 8 em). `ElementBatcher.cpp:1669-1683` — 외곽선 층이 먼저, 채움이 위. 켜는 조건 `FontFace.cpp:21-42 · 321-363`: 프로젝트 설정 `UserInterfaceSettings.bEnableDistanceFieldFontRasterization` + CVar `UI.SlateSDFText.RasterizationMode`(기본 Bitmap, 'Preview' 표시) + 폰트 애셋 `bEnableDistanceFieldRendering`. 비트맵 글꼴의 외곽선 머티리얼은 덮임 값만 받아 번질 수 없다(`:340-368`).
- **구현 — 게이지(Python):** `gen/concept_fill.py`(새) — `measure`: 밝기 L 문턱 T = (몸통 L + 빈 트랙 L)/2 → 3×3 열기(가는 프레임 선과 이어진 다리 끊기) → 씨앗에서 4-연결 → 2 px 되살림 = 몸통, 트랙 오른쪽 = 가운데 줄 따라 프레임 선까지, **트랙 위 · 아래 = 빈 쪽 열에서 프레임 선까지**(채운 쪽 띠 안 경사면 밝은 줄 때문에 몸통 열로 재면 선 앞에서 멈춤 — 실측으로 고침), 왼쪽 = 몸통 끝 − 띠, 왼쪽 끝 구간(lead) = 몸통 세로 폭이 안정 구간의 85 % 에 닿는 열 + 8, 번짐 = 빈 트랙보다 L 4 이상 밝은 열(≤ 24). `render`(같은 값 → 같은 바이트): 트랙 상자 1:1, 왼쪽 끝 = 컨셉 픽셀 + 알파(몸통 ∪ 띠 폭 안 어두운 쪽 4-연결 + 구멍 메우기), 몸통 = 줄 대표색(띠 포함), 8 px 섞음, scale 이면 오른쪽 끝에 진행 끝 테두리 + 번짐(번짐 = 빈 트랙 색 위 그 줄 채움색의 투영 알파 × 끝 0 페이드 — 테두리 흰빛 기준이면 희뿌옇게 나와 고침), right_to_left 는 뒤집어 계산. procedural shape `concept_fill`(파이프라인만 — LLM 이 쓰면 analyze 검사 거부, `procedural.render(asset, reference)`). `analyze.derive_gauge_fills` — 아래 따온 프레임이 있으면 이 방식(`pipeline.yaml gauge_fill{mode: shape, end: scale}`), 막대 bbox_intent · slot.padding(프레임 상자 기준) = 트랙 상자, scale 이면 `style.bar_fill_style: scale` + 채움 `box`(margin = 왼쪽 끝 · 오른쪽 끝), 못 재면 B 방식 + `shape_fallback`. 지표 `fidelity.gauge_shape`(채운 부분 L > T 마스크 IoU · 시작 끝 차 · 줄 수 — 진행 끝 앞까지) → `gauge_fidelity.<위젯>.shape` · 외형 비교 보고.
- **구현 — WidgetMcp C++(승인):** ProgressBar `bar_fill_style`(mask|scale — 기본 mask 는 정규화가 지워 예전 spec 정규형 · revision 그대로, 검사 · `SetBarFillStyle` · scale 만 역추출). 글자 빛 `font.glow{size 0 ~ 64, color}` — `WidgetMcpTextMaterials`: run 폴더 부모 `M_TextGlow`(UI · 반투명, Emissive = GlowColor, Opacity = GlowAlpha × saturate(FontSignedDistance.x / OutlineEm)^Gamma(1.5)) + `MI_TextGlow_<색>_S<px>_F<크기×10>`(OutlineEm = px / (크기 × 96/72) — `FontCache.cpp:1346`), 적용 = 외곽선 층(OutlineSize = size, OutlineColor 흰색, OutlineMaterial = MIC), outline 과 동시 금지(검사 · Python `FONT_GLOW_OUTLINE`), 역추출은 MIC 매개변수. 그라데이션과 같은 '적용 직전 준비 · 컴파일 대기' 경로(`CompileAndWait` 로 묶음). `import_font_family distance_field` — `bEnableDistanceFieldRendering` + `PostEditChange`(private 래스터화 설정 갱신), 결과에 `rasterization_mode`. `render_widget` — SDF 가 켜져 있으면 한 번 미리 그려 글리프 요청을 넣고 40 × (0.05초 + `FontCache->UpdateCache`) — 거리장 글리프는 작업 스레드에서 만들고 처음엔 자리표시 그림이라(`FontCache.cpp:1470 · 1872`), 결과에 `sdf_warmup_seconds`. 시험 `BuildRoundTrip` 에 빛 · scale 왕복.
- **Config(승인):** `DefaultEngine.ini` — `[/Script/Engine.UserInterfaceSettings] bEnableDistanceFieldFontRasterization=True` · `[ConsoleVariables] UI.SlateSDFText.RasterizationMode=Msdf`. SDF 를 켠 폰트 애셋만 영향(기존 `F_NotoSerifKR` · Pretendard 는 비트맵 그대로).
- **새 폰트 애셋:** `/Game/UI/Fonts/NotoSerifKR/F_NotoSerifKR_SDF` + `FF_NotoSerifKR_SDF_Regular` · `_Bold`(같은 OTF, `distance_field: true` — 결과 `rasterization_mode: Msdf`, 저장). `pipeline.yaml fonts.roles.title.sdf_family` — 빛을 쓰는 글자만 이 사본으로 바꾼다.
- **구현 — 글자(Python):** `analyze.derive_text_glow` — 획(`text_ink`)에서 거리별 밝기 띠를 바탕(10 ~ 14 px 띠)과 비교, 2 ~ 6 px 띠 최대 초과 ≥ `text_glow.min_excess`(8)이면 빛: size = 바탕 + 3 이상인 마지막 거리 + 1, 색 = 바탕에서 2 ~ 3 px 띠 색 쪽으로 한 채널이 255 에 닿을 때까지 민 색, 알파 = 1 / (k × (1 − 2.5/size)^1.5) → `font.glow` + family = `sdf_family`, LLM 이 넣은 빛 · 겹치는 outline 은 지움(기록). **[실측 F 에디터] 빛(외곽선 층)은 글자 상자를 사방 size 만큼 키우고 글자를 그만큼 들인다**(위쪽 정렬 상자에서 글자가 8 px 아래로) → `_glow_layout` 이 bbox_intent 를 사방 size 넓히고 slot padding 을 사방 size 줄인다(음수 — 형제 자리 그대로, 빛만 이웃 위로; 캔버스 점 앵커는 위치 += s(2·alignment − 1) · 고정 크기 += 2s) — 에디터 시험에서 빛 글자 · 빛 없는 글자의 획 상자가 픽셀까지 같음(x 99 ~ 218 · y 114 ~ 178). 글자 높이 비 `fonts.glyph_height` · `fonts.roles.<역할>.glyph_height`(한글 · 숫자) → `config.font_roles` · `analyze.font_lines` · `prompts/analyze.md`(크기 = 보이는 높이 / 비, glow 는 넣지 말 것). `style.follow_text_boxes`(끝 run 1 ~ 4 에서 세 번 고친 최종형) — 외형 라운드가 글자 크기 · 폰트 · 자간 · 외곽선을 바꾸면 **그 글자만 자기 가운데를 중심으로 커지고 레이아웃의 다른 것은 그대로**: 축마다 글자가 길이를 정하는지(`_axis_follow` — 정렬 left/center/right · 박스 주축 auto 는 따라감, fill · 캔버스 고정 크기는 아님), 늘어나는 길이 Δ = 직전 통과 렌더 상자(`rendered_boxes` — attempts/NNN/geometry.json)에서 폭 = 글자 몸통 × 크기 비 + (글자 수 − 1) × ⌊크기 × 자간/1000⌋ + 외곽선 양쪽([실측] 자간 133 → 280 · 크기 38 · 6 글자 → +25 px 정확히), 높이 = 줄 × 줄 높이 비 + 외곽선 위아래 → 슬롯 padding 양쪽 −Δ/2(슬롯이 차지하는 자리 그대로 — 형제 · 행 · 패널 안 움직임) · 캔버스 자동 크기는 위치 보정, bbox_intent = 그 렌더 상자를 Δ 키운 것. 세로가 fill · 캔버스 고정 크기면 글자가 위쪽 기준으로 그려져 아래로만 커지므로 줄 높이 변화 절반만큼 위로(`_shift_up_fixed_text`). → `report.recorded.style_review.rounds[].text_boxes_followed`. `prompts/style_fix.md` — 크기는 비율대로 한 번에, **크기 때문에 형제를 padding 으로 보정하지 말 것**(파이프라인 몫 — 단일 원천). `fix._line_height_note` 는 SDF 사본도 같은 줄 높이 표. `fidelity._text_band` — 키 큰 가는 덩어리(높이 ≥ 상자 80 % · 폭 ≤ 높이 × 0.25 — 세로 테두리선) 빼기, 외형 비교의 빛 글자는 빛 크기만큼 줄인 원래 줄 상자에서 잰다(끝 run 3 '4.2' 높이 비 2.0 → 0.94, C1 기록값 그대로).
- **[실측 F 에디터] 빛 시험 WBP(스크래치 — 버림):** `MI_TextGlow_FF890032_S8_F640` 컴파일 오류 0 · 셰이더 맵 있음, 렌더에 '4.2' 둘레 주황 빛, SDF 사본(빛 없음)과 기존 비트맵 글자 모양 같음, 미리 그리기 2.0초. C1 컨셉에 `derive_text_glow` → '4.2' 만 `{size 8, #FF890032}`(최대 초과 16.7), 나머지 5개 빛 없음(최대 초과 −4.4 ~ 2.1).
- **실제 끝 run 5번(전부 옵션 없음 · 같은 컨셉 · 무인 통과) [실측]:** 게이지 · 빛은 매번 같다(결정적 — 트랙 상자 [575, 923, 787, 44] · 띠 위 6 · 아래 5 · lead 27 · 번짐 24 · 컨셉 진행률 0.748, '4.2' 만 빛 {8, `#FF890032`}, 최대 초과 16.7 ~ 16.8). 외형 라운드는 한 번 받고 네 번 버려졌는데, 버려질 때마다 원인을 고쳤다:

  | run | 시도 | 외형 라운드 | 원인 → 고침 |
  | :--- | :--- | :--- | :--- |
  | 1 `R20261115_183627` | 4 | 버림(iou_region · iou_leaf) | 상자 따라가기가 축 구분 없이 폭 · 높이 다 바꿈('오의 불가' 캔버스 고정 · 배너 라벨 가로 fill 은 렌더 그대로) → 축별 |
  | 2 `R20261115_184553` | 4 | 버림(iou_leaf) | analyze 상자가 글자보다 넓은 것(체인 제목 104 vs 57 px)을 비율로 키움 + 높이 48 px 넘어 '작은 상자' 판정이 IoU 로 바뀜 · style_fix 의 형제 padding 보정 오류로 '3' 10 px → 렌더 상자 기준 · 가운데 중심 성장 · 형제 보정 금지 |
  | 3 `R20261115_185524` | 4 | 버림(iou_leaf) | 자간 133 → 280 이 '3' 을 12.5 px 밈 → 자간 · 외곽선도 성장에 포함 / '4.2' 높이 비 2.0(세로선) → 측정 고침 |
  | 4 `R20261115_190401` | 3 | **받음** | 배너 높이 비 0.898 → 1.02 · '오의 불가' 0.946 → 1.0 · 체인 패널 다시 따옴. 단 옛 지표(1.65)에 속아 '4.2' 56 → 64 → fill 상자라 아래로만 커져 '2/4' 에 닿음 → 위로 옮김(`_shift_up_fixed_text`) |
  | 5 `R20261115_193549` | 4 | 버림(overlap) | analyze 가 배너 라벨 · '3' 을 1 px 간격으로 붙여 놓아, 라벨이 넓어지면 겹치거나(overlap) '3' 을 밀거나(iou_leaf) — **한계로 남김** |

  | 렌더 ↔ 컨셉(기록만, 같은 트랙 상자 [575, 923, 787, 44]) | C1(F 전) | **F(run 4 · 5)** |
  | :--- | :--- | :--- |
  | 게이지 채움 실루엣 IoU | 0.891 | **0.931 · 0.937** |
  | 채운 부분 줄 단위 ΔE00 평균 · 최대 | 6.52 · 33.1 | **0.51 · 1.95** |
  | 채운 부분 픽셀별 평균 · p95 | 9.67 · 31.4 | **4.37 · 8.63** |
  | 배너 '체인 버스트' 글자 높이 비 | 1.12 | **1.02(run 4 라운드 뒤) · 1.061(run 5)** |

  - 왼쪽 끝 차(tip_dx)는 C1 · F 모두 0 — 가운데 줄에서는 프레임 캡 선도 밝아 이 지표가 '<' 모양을 못 가른다(실루엣 IoU · 눈으로 본다). 빈 부분 대표색은 run 마다 2.9 ~ 6.1(따온 프레임 트랙 · 검은 바탕 — C 뒤로 넘길 것 ①).
  - analyze 의 글자 크기는 run 마다 흔들린다: 배너 높이 비 run 1 0.80 · run 2 0.90 · run 3 1.02 · run 4 0.90 · run 5 1.06(F 전 C1 1.18 — 높이 비 정정 뒤 '크게'는 사라졌지만 LLM 눈대중 폭 ±10 %). 외형 라운드가 크기를 비율대로 맞추고, 받아들여지면 1.0 근처(run 4).
  - 눈 확인(내 확인 — run 4 `assets/compare/hud_concept_vs_render.png` · `gauge_zoom.png` · `text_zoom.png`): 게이지 왼쪽 '<' 끝 · 밝은 테두리 · 트랙 띠 빛 · 진행 끝 테두리와 번짐이 컨셉과 겹친다, '4.2' 둘레 주황 빛. run 5 는 F 밖 변동 — codex 가 따온 체인 패널 테두리가 오목하게 일그러짐(A 따오기 변동 — 라운드가 다시 따오려다 overlap 으로 버려짐) · '3' 이 '트' 에 붙음(analyze 배치).
  - 비용(구독 — 과금 아님): LLM(API 정가 환산) run 1 ~ 5 = 1.047 · 0.858 · 0.843 · 0.869 · 0.857 USD, codex 5 × 4 = 20회(1b 부터 누적 55회, 한도 걸림 0).
- **시험:** pytest 264(253 → +11: `tests/test_gauge.py` +6 — 합성 컨셉(프레임 선 · '<' 끝 몸통 · 밝은 띠 · 번짐)으로 measure · render(같은 바이트) · derive scale/mask · 물러남 · right_to_left 거울 · 실루엣 지표 · LLM concept_fill 거부 · 빛+외곽선 거부 / `tests/test_text_style.py` +4 — 빛 찾기 · SDF 로 바꾸기 · 상자 넓힘 · padding 줄임 · 빛 없음 · SDF 없음 · 상자 따라가기(축별 · 렌더 기준 · 자간 · 외곽선 · fill 위로) · 세로 테두리선 / `tests/test_style.py` +1 — 크게 줄이는 라운드가 받아들여짐; 기존 '게이트 깨면 버리기' 시험은 깨는 op 를 글자 크기에서 위치(padding)로 바꿈 — 이제 크기만으로는 게이트가 안 깨진다). DebugGame 빌드 `Result: Succeeded`(첫 빌드는 시험 변수 이름 겹침 C4456 — 고침).
- **F 끝 회귀(필수만, 11-15) [실측]:** 빌드 DebugGame(마지막 C++ 뒤) · Development `-DisableAdaptiveUnity`(WidgetMcp 4 작업 · 19.1초) 모두 `Result: Succeeded` → 새 에디터 1회(DebugGame): `AstralBreak.` **55/55**(시험 시간 합 390초) → `EditorMcpCore.` 2/2 → `WidgetMcp.` 6/6 → `quit_editor`(버린 것 = `WidgetMcp.Spike` 시험 WBP 1개) · 소멸 확인. pytest **264**.
- **사람 눈 확인(11-15, 사용자 — 에디터 위젯 디자이너에서 run 4 · run 5 WBP):** run 4 가 run 5 보다 잘 이식됐다(run 5 는 글자 위치 · 오른쪽 위 체인 패널 모양이 다름 — codex 따오기 · analyze 배치 변동, 게이지 · 빛은 같음). run 4 에서도 남은 차이 셋 — ① 글자 위치가 컨셉과 약간 다르다([실측] 배너 라벨 획 중심 dx −10.5 · dy −4.5 px, 나머지 ≤ 3 px · run 4 의 '4.2' 가 '2/4' 에 닿음은 run 4 뒤 고침 · 실제 run 미확인), ② **배너 위아래 빛이 원본처럼 안 보인다** — [실측] 컨셉 배너는 테두리 바깥(L 33 ~ 40)과 안쪽 가장자리(30 ~ 36)에 빛이 번지는데, 따온 텍스처는 안쪽을 대표색 한 색으로 칠하고(`extract.interior_flatten` — 21) 바깥은 배경 제거로 투명이라 빛이 없다(렌더 안쪽 18 · 바깥 0), ③ **체인 패널 모서리 장식이 원본과 다르다** — codex 가 다시 그린 모서리(run 4 는 외형 라운드가 한 번 더 다시 따옴). 셋 다 F 범위 밖(A 따오기 · analyze 배치) — 다음 후속으로(인계 메모 `uigen-1b-followup-G-handoff.md`). 게이지 · 글자 빛에 대한 지적은 없었다.
- **증거 정리(11-15 사용자 승인 — 휴지통):** 끝 run 4 `R20261115_190401`(외형 라운드 받음 — 사람 눈 판정 대상) · run 5 `R20261115_193549`(최종 코드)의 work · `Content/_AutoGen/` 과 새 폰트 애셋 `F_NotoSerifKR_SDF` 를 남겼다. run 1 ~ 3 의 work · `Content/_AutoGen/`(47 MB) · 빛 시험 렌더 `work/_fonts/measure_F_glow_1` · `_2` · 스크래치(시제품 · 측정 스크립트 · 확대 그림, 4.9 MB)는 휴지통 — run 1 ~ 3 숫자는 위 표로만 남는다. 빛 시험 WBP 두 개는 처음부터 저장하지 않고 버렸다.
- **F 뒤로 넘길 것:** ① 외형 라운드에서 크기 · 자간이 커지는 글자가 형제와 붙어 있으면(run 5 — 1 px 간격) 겹치거나 형제를 밀어 라운드가 버려진다 — 라운드를 op 별로 나눠 받기(크기 고치기 결정적 단계를 LLM 라운드 앞에 따로) 또는 analyze 의 '형제 사이 간격' 규칙. ② analyze 글자 크기의 LLM 흔들림(±10 %) — 결정적 크기 맞추기(컨셉 획 높이 ÷ 실측 비)를 analyze 뒤에 둘지. ③ 패널 폭 상자(h_align fill)의 글자 지표는 이웃 글자 · 모서리 장식에 흔들린다(체인 제목 폭 비 0.16 · 커진 '4.2' 가 '2/4' 상자에 걸리면 0.2) — 지표는 기록만. ④ 컨셉의 다른 글자 5개의 어두운 1 ~ 2 px 테(L −8 ~ −16)는 재기만 하고 넣지 않았다(outline 어휘로 결정적으로 넣을 수 있음). ⑤ 진행 끝 9-slice 는 진행률 7 % 아래에서 양끝이 눌린다(엔진 규칙). ⑥ SDF 는 'Preview' CVar — 패키징 · 다른 플랫폼 확인은 M4 C 의 실제 HUD 때. ⑦ codex 따오기 변동(run 5 체인 패널 오목) — A 의 몫.

- M4 단위 E(4인 별도 프로세스 시험)는 UI 와 무관해 에디터가 비는 때 아무 때나. 단위 D(오의 애니)는 별개.
- 감안할 점: M4 C 의 화면은 Phase 0 ~ 1b 가 끝나야 완성된다. 그동안 HUD 는 디버그 위젯이다.

---

## 12. 불확실한 가정 · 질문

### 12-1. Phase 0 에서 확인할 가정

| # | 가정 | 틀리면 | Phase 0 결과 (11-14) |
| ---: | :--- | :--- | :--- |
| A1 | codex built-in `image_gen` 이 `codex exec`(비대화형)에서도 돌고, `--json` 이벤트로 결과 파일을 찾을 수 있다 | 생성 앞뒤로 `generated_images` 폴더 차이를 본다(직렬 실행이라 가능) | **참(조건부) [실측]** — 비대화형에서 돈다. 이벤트에 파일 경로 항목은 없지만 폴더 `generated_images/<thread_id>/` 의 `thread_id` 가 첫 이벤트에 있다 → 그것으로 찾고, 폴더 차이는 대비책(§7) |
| A2 | npm 의 codex 가 `~/.codex` 의 ChatGPT 로그인을 같이 쓴다 | 사용자가 한 번 `codex login` | **참 [실측]** — npm 0.166.0 `codex login status` = `Logged in using ChatGPT` |
| A3 | 한도 초과가 식별 가능한 메시지 · 종료 코드로 온다 | 연속 실패 횟수로 추정 | **미확인(재현 안 함)** — [바이너리] 식별자 `usage_limit_reached` · `quota_exceeded` · `usage_not_included` · `rate_limit_exceeded` · 문구 `Try again at …` 있음. 이벤트 모양 · 종료 코드는 걸렸을 때 채록, 그때까지 '틀리면' 경로를 같이 둔다. **[1b]** codex 11회 써도 걸리지 않음 — `gen/codex.py` 가 식별자 판정 + '이미지 없는 호출 연속 2번 = 한도 추정'을 둘 다 갖고 있다(가짜 codex 로만 확인) |
| A4 | `--json-schema` 결과를 JSON 출력에서 꺼낼 수 있다 · `--max-turns` 존재 여부 | 출력 파일 + Stop 훅 검사로 대신 · 타임아웃만 | **참 [실측 2.1.325]** — 스키마 출력은 결과 `structured_output`(`{"answer":"ok","n":3}`), 숨은 `--max-turns 1` 이 `error_max_turns` 로 끊는다(§10-1) |
| A5 | `--allowedTools` 경로 규칙으로 쓰기를 `work/<run_id>/` 로 묶을 수 있다 · auto-memory 를 settings 로 끌 수 있다 · `--setting-sources project` 의 project 가 저장소 루트가 아니라 cwd(`claude_ctx/`)다 | PreToolUse 훅으로 경로 검사 · 루트 설정이 읽히면 `--settings` 로 덮는 값만 믿는다 | **참(셋 중 둘 실측 · 하나 근거)** — `Edit(work/**)` 가 cwd 기준으로 `work/` 밖 `Write` 를 막는다 [실측] · `--setting-sources project` 의 project 는 cwd 다(cwd 설정의 deny 가 걸림 [실측] — 루트가 같이 읽히는지는 미판별이라 `--settings` 로 명시) · auto-memory 는 `autoMemoryEnabled: false`(설정 스키마 — 효과는 미관측) |
| A6 | `FWidgetRenderer` 두 번 그리기로 폰트 · 텍스처가 다 그려지고, 그 뒤 `GetPaintSpaceGeometry` 가 렌더 좌표와 맞는다 | 그리기 사이 `FlushRenderingCommands` · 폰트 캐시 미리 채움 | **참 + 새 문제 1건 [실측]** — 각 그림 뒤 `FlushRenderingCommands` 로 3회: 1·2·3회 그림이 픽셀 단위로 같다(다른 픽셀 0 — 에디터가 이미 폰트를 올린 상태라 첫 그림부터 완성). geometry 는 캔버스 슬롯(앵커 · 정렬 포함)과 **오차 0 px**. 라틴 · **한글(대체 폰트)** · 트랜지언트 텍스처 모두 그려짐. 단 **색에 감마가 두 번 걸린다**(아래 A6-색) |
| A7 | `UWidgetBlueprintFactory` 를 대화창 없이(`ConfigureProperties` 생략) 써도 루트 위젯이 정해진다 | 만든 뒤 루트를 Canvas 로 교체 | **거짓 [실측 · 소스]** — 이 프로젝트 설정(`bUseWidgetTemplateSelector` false · `DefaultRootWidget` 없음)에서는 루트가 없다(`WidgetBlueprintFactory.cpp:184-200` — 선택기를 끄면 `RootWidgetClass = DefaultRootWidget` 로 덮는다). → build 는 루트가 없으면 `ConstructWidget<UCanvasPanel>` + `RootWidget` 지정 + `OnVariableAdded` (팩토리가 루트를 만들 때와 같은 순서). GUID 맵 8/8 · 컴파일 오류 0 |
| A8 | HUD 컨셉아트에서 analyze 가 장면과 UI 를 안정적으로 가른다 | brief 에 HUD 영역을 손으로 적는 선택 입력 | Phase 1b 로 미룸(컨셉아트 필요) → **[1b-4 실측 1회] 참** — 인물 5 · 성당 · 깃발 · 마법 효과가 있는 컨셉에서 장면은 위젯 · 에셋 0, HUD 4요소만 영역으로(§11 '1b-4'). 표본 1장이라 '안정적'은 Phase 2 보정 세트에서 다시 본다 |

**A6-색 [실측]:** `FWidgetRenderer(true)` + `CreateTargetFor(…, true)`(엔진이 RT 를 `SRGB=false` · B8G8R8A8 로 만든다 [소스] `WidgetRenderer.cpp:81-100`) 조합에서 지정색이 sRGB 를 한 번 더 거친 값으로 나온다 — 패널 `#202838` → `#636E81`, 체커 `#282828` → `#6E6E6E`, `#E8B54A` → `#F5DB93`(모두 'sRGB 값을 선형으로 보고 다시 인코딩한 값'과 일치). verify 의 영역 대표색 ΔE(§8-2)가 이 상태로는 뜻이 없으므로 render_widget 은 아래 규칙으로 고친다.

| 탐침 (지정색) | `gamma=true` (RT B8G8R8A8 · SRGB=0) | `gamma=false` (RT B8G8R8A8 · SRGB=1) |
| :--- | :--- | :--- |
| 패널 Border `#202838` | `#636E81` = sRGB 인코딩(지정값) | `#04050A` = sRGB 디코딩(지정값) |
| 체커 텍스처 금 `#E8B54A` | `#F5DB93` | `#CE7611` |
| 체커 텍스처 어둠 `#282828` | `#6E6E6E` | `#050505` |

→ **규칙(실측 3점 일치):** `gamma=true` 로 그리고 읽은 8비트 값에 채널마다 sRGB→선형 변환을 한 번 하면 지정색이 나온다(예 `0x63 → 0x20`). `gamma=false` 는 어두운 쪽이 8비트에서 뭉개지므로(`0x20 → 0x04`) 쓰지 않는다. render_widget(Phase 1a)은 이 보정 LUT 를 적용한 PNG 를 내고, 에디터 디자이너 화면과 같아 보이는지는 Phase 1a 에서 사람 눈으로 한 번 맞춘다.

**[사람 눈 11-15] 통과** — 1a-5 정상 run `R20261115_001147` 의 `render.png`(force_visible · LUT 적용 · 검은 바탕)와 같은 WBP 의 UMG 디자이너(1920×1080)를 사용자가 비교했고, 게이지 금색(`#E8B54A`) · 체인 패널 · 글자색이 같아 보인다고 답했다. 바탕은 다르다(렌더 검정 · 디자이너 격자 — 반투명 배너 `#2A1A0ACC` 만 바탕 차이). → LUT 보정을 확정한다. 영역 대표색 ΔE(§8-2)는 Phase 2 보정 때 이 규칙의 PNG 로 잰다.

스파이크 산출물: `Tools/mcp/results/widget_spike/<시각>/`(draw_1~3.png · report.json, git 무시). 코드는 `Plugins/WidgetMcp/Source/WidgetMcpEditor/Private/Spike/` · 시험 `WidgetMcp.Spike.BuildRender`.

### 12-2. 사용자에게 묻는 것

1. ~~플러그인 이름~~ — **결정(11-14): `EditorMcpCore` / `WidgetMcp`.** 편집 대상 애셋 이름으로 짓는 기존 관례(AnimGraph · StateTree)와 맞고, 코어는 프로젝트 코드에 의존하지 않으므로 일반 이름.
2. ~~StateTree 도구 이전 시점~~ — **결정(11-14): Phase 0 에서 같이 이전.** 분리가 한 번에 끝나고 회귀도 한 번이다(§3-1).
3. **M4 HUD 컨셉아트** — 준비돼 있는지, 경로.
4. ~~폰트~~ — **결정(11-14): 1a 는 엔진 기본 폰트(Roboto + 한글 대체)**, 프로젝트 폰트(Pretendard / Noto Sans KR)는 1b 에서 결정 · 내려받기는 그때 따로 승인. spec `font.family` = null.
5. ~~텍스처 압축 기본값~~ — **결정(11-14): `TC_EditorIcon` 기본 + 큰 배경(`panel_bg`)만 `TC_BC7`** — `pipeline.yaml textures.compression_by_kind`.
6. ~~상한 값~~ — **결정(11-14): 재시도 N = 3** 으로 시작(codex 20 회는 1b 에서 실제로 쓸 때 다시 본다).
7. **집계 리포트 커밋** — `metrics/` 집계 결과(텍스트)를 포트폴리오 증거로 커밋할지. (Phase 2 몫)
8. ~~HUD 요소 목록~~ — **결정(11-14): M4 설계 §5 그대로** — 오의 게이지(+가득 시 강조) · 체인 패널(남은 시간 · 참가 N/4) · 버스트 배너(인원) · '오의 불가'.
**1b 착수 때 물을 것(1a-5 정리, 11-15):** 3(컨셉아트 경로) · 4 후속(프로젝트 폰트 선택 · 내려받기 승인) · OCR 엔진 선택 — 근거는 §11 '1b 로 넘길 것'. 7(집계 리포트 커밋)은 Phase 2.
→ **결정(11-15, 1b 착수):** 3 = codex 로 컨셉아트 1장 생성 · 4 = Pretendard(Regular · Bold — 내려받기는 1b-3 에서 따로 승인) · OCR = RapidOCR(설치는 1b-3 에서 따로 승인) · 6 후속 = codex run 당 20 그대로 + analyze 상한 1.0 USD · 턴 6 · 600초(잠정). 나머지 1b 결정은 §11 '1b 착수 때 정한 것'.

9. **Phase 1a 진행 방식(11-14 결정):** 브랜치 `feat/M4_Ultimate_Skills` 그대로 · 하위 단계 1a-1 ~ 1a-5(§11) · 재시도 fix 는 **결정적 fixer**(일부러 깨뜨린 spec + 정정 patch, LLM verifier · fix 실제 호출은 1b — 1a 에는 reference.png 가 없어 verifier 가 비교할 대상이 없다) · 설정 YAML 을 위해 venv 에 **PyYAML 6.0.3 설치**(사용자 승인).
