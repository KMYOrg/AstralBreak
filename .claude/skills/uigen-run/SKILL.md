---
name: uigen-run
description: AstralBreak UI 자동 생성 파이프라인(Tools/uigen)을 돌리거나 결과를 읽을 때 — 컨셉 만들기, run 실행, report · compare.png 판독, 회귀 확인, 에디터 주기,
             승격 전 확인. "HUD 를 새로 만들어 줘", "uigen run 을 돌려 줘", "이 run 왜 실패했어" 같은 일에 쓴다.
---

규칙의 원문은 `Tools/uigen/README.md`(돌리는 법 · 게이트 · 폴더)와 `Docs/Design/ui-autogen-pipeline.md`(설계 · 결정 기록)다. 여기는 순서와 자주 틀리는 것만.
명령 앞의 Python 은 늘 `D:/UE5Projects/AstralBreak/Tools/mcp/.venv/Scripts/python.exe -X utf8 -B`.

# 어느 길인가

| 받은 것 | 길 | inputs `concept_source` |
| :--- | :--- | :--- |
| 화면 설명만 · 우리가 만드는 화면 | **L-2(기본)** — 글자 없는 컨셉 + 글자 참고판 | `generated_textfree` |
| 글자 있는 그림 그대로 | L-1 — 더 다듬지 않는다. 못 지운 자리는 '수동 확인 필요' | `external` · `generated` |
| 글자 있는 그림을 느낌만 | L-2 + `make_concept.py --style-ref` | `generated_textfree` |

글자 밑에는 정답 픽셀이 없어 지우기는 지어낸 그림이다 — 그래서 L-2 가 기본이다. 스타일 유사도 · ComfyUI · 라우팅은 만들지 않기로 했다(설계 §11 'Phase 조정').

# 순서

1. `fixtures/<화면>/inputs.yaml` — 화면 · 데이터 계약(바인딩) · 필수 요소. 지금 있는 화면: `combat_hud_blade`(CombatHUD) · `status_hud_blade`(StatusHUD). 승인한 전체 시안 = `hud_blade_sheet`.
2. 컨셉 — 승인한 시안에서 오리기(`make_concept.py --cut-from … --keep x,y,w,h`, codex 0 회) 또는 새로(`make_concept.py --out-dir …`, codex 2 ~ 3 회). 후보는 **사람이** 고른다.
   글자 참고판은 엔진 글꼴로 그린다: `--only text_ref --draw …/text_ref_layout.yaml`(codex 0). 글꼴 값을 바꾸려면 그 yaml 을 고치고 다시 그린 뒤 run.
3. run — `Tools/uigen/run_pipeline.py --inputs Tools/uigen/fixtures/<화면>/inputs.yaml`(백그라운드로 — 3 ~ 6 분). 에디터가 없으면 스스로 띄우고, **끝나도 내리지 않는다**.
4. 읽기(아래) → 사람 눈(`compare.png` · 게임 안) → 승격(`promote_widget`)은 사용자 승인 뒤.
   이미 승격한 화면을 조금 고칠 때는 처음부터 다시 돌리지 않는다 — `run_pipeline.py --from <ScreenId> --edit <patch.json>`(약 1분) → `edit.png` · `compare.png` 를
   사람이 본다 → 재승격 `promote_screen.py plan` → 승인 뒤 `apply`(에디터를 끈 채, 되돌리기 = `revert`). 승격본 · `promoted/` 를 손으로 치우거나 고치지 않는다(해시가 다르면 거절).

**칸 · 버튼(Phase 3-2)** — 여러 화면에 놓는 부품도 자기 run · 자기 승격본(`/Game/UI/Common/`)이다. 지금 있는 칸: `button_large`(ButtonLarge) · `button_small`(ButtonSmall), 시안 = `hub_ready_sheet`.
- 칸의 원본 아트 = 승인한 시안에서 그 상자만 `make_concept.py --cut-from … --keep x,y,w,h --crop`(codex 0). inputs `resolution` = `concept.json` 의 `cut_from.size_1920`, 글자 배치 yaml 에 `base_width`(= 그 폭).
- 버튼 상태 그림 여섯은 공용 테마 `config/theme_blade.yaml` 의 식이 만든다 — 값을 바꾸면 `theme_preview.py` 그림을 **사람이** 다시 승인하고 버튼 칸을 다시 돌린다. 버튼 칸 run 은 LLM 0 · codex 0(약 20초).
- `compare.png` 맨 아래 상태 일곱(왼쪽 엔진 · 오른쪽 회색 바탕 합성)을 사람이 본다. `E8 button_*` 는 상태 렌더 ↔ 식의 그림이 다르거나 덮어쓰기가 안 먹은 것이다.
- 첫 승격 = `promote_widget` → (새 에디터에서) `promote_screen.py record <ScreenId> --run <run_id>`.

- 종료 코드 0 통과 · 1 실패 · 2 미완(`--until`). 한 번에 run 하나(`work/.lock`).
- `--until analyze` 는 에디터 없이 spec 까지, `--inject-fault …` 는 재시도 경로 시험, `--fix-mode deterministic` 은 LLM fix 없이.

# 에디터 주기

- 시작 전 `tasklist` 로 다른 에디터 · 빌드가 없는지 확인한다(둘이면 브리지가 `UNAUTHORIZED`). 손으로 띄울 때는 CLAUDE.md 의 명령 → `wait_for_bridge.py 540 10` → **30 초 더** 기다린다.
- 계약(바인딩)이 바뀐 run 은 codegen 이 에디터를 내리고 DebugGame 을 빌드한 뒤 다시 띄운다(수 분). 같으면 `skipped`.
- 끝나면 `quit_editor` → `wait_for_exit.py <pid> 180 5` 로 내려 메모리를 비운다. 더티가 `/Game/_AutoGen/` 밖이면 거절된다 — 강제로 버리지 말고 무엇인지 본다.

# 결과 읽기 — `work/<run_id>/`

| 볼 것 | 어디 |
| :--- | :--- |
| 결과 · 시도 · 시간 | `report.json` `status` · `attempts[]` · `durations_s`(한 줄씩은 `run.log`) |
| 게이트 11 개 | `report.json gates[]` — 앞 10 개가 구조(재시도 · LLM fix 는 이것만 본다), 11 번째 `appearance` = 외형 진단 **오류 0** |
| 외형 결함 | `diagnosis.json` `defects[]`(오류 E1 ~ E9) · `approx[]`(근사 — 가장 가까운 선택을 골랐는데 남은 표현 차이, 기록만) |
| **사람 눈 그림** | **`compare.png`** — 위: 컨셉 \| 엔진 렌더 \| 국소 차이, 아래: 글자 3 배 확대, 맨 아래: 상태 띠(게임 기본 상태 · 게이지 비율 · 글자 빈 값 …) |
| 정답 없는 자리 | `report.recorded.manual_check` — '수동 확인 필요'(오류가 아니라 사람이 봐야 하는 자리) |
| 실패 이유 | `stop`: `RETRY_LIMIT` · `NO_PROGRESS` · `NO_FIX` · `APPEARANCE`(구조는 통과, 외형 결함이 남음) + `message` |
| 상태 렌더 | `attempts/NNN/gates.json notes.state_renders` — `batch` 가 0 이고 `error` 가 있으면 묶음이 실패해 한 장씩 그린 것(느려질 뿐 판정은 같다) |

- **'오류 0' 이어도 `compare.png` 를 직접 본다.** 같은 역할의 글자끼리(동료 이름 1 · 2 · 3 처럼) 굵기 · 크기 · 색이 같은지 줄마다 견준다 — 오류 0 인 run 에서 한 줄만 다른 굵기였던 적이 있다
  [실측 `R20261124_123020`]. `render.png` 는 기계용(숨은 위젯도 켠 그림)이다.
- '통과'를 '컨셉과 똑같다'로 말하지 않는다 — 오류 수 · 근사 수 · 사람 눈 확인 여부를 따로 적는다.
- 비용은 API 정가 환산이다(구독 — 과금 아님). 여러 run 을 모아 보려면 `Tools/uigen/summarize.py` → `Docs/Design/ui-autogen-report.md`. 시험 run 과 게임 화면 run 을 섞어 통과율을 말하지 않는다.

# 규칙을 고쳤을 때 — 에디터 run 전에

1. `-m pytest Tools/uigen/tests -q -p no:cacheprovider`(18 ~ 25 분 — 백그라운드). 에디터 · codex · claude 없이 돈다.
2. `Tools/uigen/golden.py check` — 사람이 찾은 결함을 여전히 잡는가(n/n caught · clean · protected).
3. `Tools/uigen/regress_set.py run <새 라벨> --relayer` → `compare <마지막 기준선> <새 라벨>` — `+ new` 가 0 이어야 한다(`+ state` 는 옛 run 텍스처에 있던 것이라 따로).
4. 그다음 실제 run. 결함을 고치려고 **문턱을 만지지 않는다** — 같은 자리가 거듭 나오면 접근부터 다시 제시한다.

# 하지 말 것

- `--spec-dir Tools/uigen/fixtures/m4_combat_hud` 를 그대로 돌리기 — 실제 CombatHUD 의 C++ 를 옛 계약으로 다시 쓴다(빌드는 통과, 게임에서 안 뜸). 되돌리기 = combat_hud_blade 로 `--until codegen`.
- `/Game/_AutoGen/<run_id>/` 밖에 쓰기 · 기존 애셋 덮어쓰기 · 승격본 손대기. `--dangerously-skip-permissions`.
- `~/.codex/auth.json` · 토큰 파일 읽기, codex 환경에 `OPENAI_API_KEY` 넣기. 이미지 생성은 공식 codex CLI 만.
- 하위 세션 · 커밋 · 승격을 묻지 않고 하기. 일회성 파일은 목록 → 승인 → 휴지통(`rm` 금지).
