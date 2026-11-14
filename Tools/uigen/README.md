# uigen — UI 자동 생성 파이프라인

컨셉아트(또는 텍스트 · 참조 이미지)나 손으로 쓴 spec 을 받아 C++ 바인딩 클래스 + WBP 프로토타입을 만들고 렌더 검증까지 무인으로 도는 오케스트레이터입니다. 설계: [Docs/Design/ui-autogen-pipeline.md](../../Docs/Design/ui-autogen-pipeline.md). 에디터 쪽 도구는 [Plugins/WidgetMcp](../../Plugins/WidgetMcp/README.md).

**상태: Phase 1a 완료(11-15, 미커밋).** normalize(손 spec) → codegen(C++ 생성 · UBT 빌드 · 에디터 재기동) → generate → refine → build → verify → (fix → 분기)… → finalize 가 끝까지 돈다. 재시도 fix 는 1a 에서 결정적 fixer(LLM 호출 0), `claude -p` verifier · fix 는 호출 틀만 있다(1b). 끝 검증(1a-5): pytest 142 · 정상 run 게이트 10/10 · 왕복 일치 · codegen 해시 건너뛰기 · 지표 줄 · 렌더 색 사람 눈 통과 — 숫자 · 1b 로 넘길 것은 설계 §11.

## 돌리기

```text
Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/run_pipeline.py --spec-dir Tools/uigen/fixtures/m4_combat_hud
Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/run_pipeline.py --spec-dir Tools/uigen/fixtures/m4_combat_hud --inject-fault offscreen
Tools/mcp/.venv/Scripts/python.exe -X utf8 -B -m pytest Tools/uigen/tests -q -p no:cacheprovider
```

- 종료 코드: 0 = pass · 1 = fail(입력 · 단계 실패 · 게이트 실패 · 잠금) · 2 = incomplete(`--until`).
- 옵션: `--until <단계>`(build · verify 는 첫 시도 뒤, finalize 안 함 — 패키지는 에디터에 저장 안 된 채 남는다) · `--inject-fault offscreen|overlap|drift`(normalize 뒤 spec 을 깨뜨려 재시도 경로를 돈다) · `--keep-failed`(실패해도 저장) · `--run-id` · `--config` · `--work-root` · `--metrics` · `--module-root`(시험용 — C++ 을 임시 모듈 폴더에).
- 의존성: `Tools/mcp/.venv` 그대로 + PyYAML(`requirements.txt`). pytest 는 에디터 · UBT · 네트워크 · claude 없이 돈다(`tests/conftest.py` 의 `FakeToolchain` + `tests/fake_editor.py`, 가짜 CLI `tests/fake_claude.py`).
- 에디터가 없으면 build 가 DebugGame 에디터를 띄운다(브리지 + 30초). 파이프라인은 끝나도 에디터를 내리지 않는다(다음 run 이 재사용).
- codegen 은 계약이 바뀌면 에디터를 내리고(`quit_editor` — `/Game/_AutoGen/` 밖이 더티면 거절) DebugGame 을 빌드한 뒤 에디터를 다시 띄운다(수 분). 계약이 같으면 건너뛴다.

## 재시도 · 게이트 (설계 §2-2 · §8-1)

- 시도 k 는 `specs/00k.json` 을 쓴다. verify 가 실패하면 fix 가 `patches/00k.json`(정정 patch)을 내고, op 종류로 돌아갈 단계를 정한다 — 배치 · 슬롯 · 스타일 · 텍스트 = build, 에셋 교체 = generate(그 에셋만) → refine → build, 바인딩 = codegen → build. `--inject-fault` 의 결함은 `patches/000.json`(source fault).
- 상한: 재시도 N = 3(`pipeline.yaml limits.retries` — 시도 최대 4번). 실패 게이트 집합이 두 번 연속 줄지 않으면(진부분집합이 아니면) 조기 종료(`NO_PROGRESS`), fixer 가 op 를 못 내면 바로 종료(`NO_FIX`).
- 게이트 10개(값은 `profiles/hud.yaml`): compile · bindings · texture_settings · offscreen(3 해상도 · force_visible) · overlap · required_elements · iou_region · iou_leaf · baked_text(procedural 은 건너뜀) · roundtrip. 모두 `report.json gates[]` 에 남는다.
- 결정적 fixer: 배치 게이트에서 실패한 위젯의 캔버스 슬롯 영역(루트 Canvas 직계 · 점 앵커)을 측정 bbox ↔ `bbox_intent` 차이로 옮긴다(position += d + alignment × dsize · size += dsize). 텍스처 설정 불일치 = `replace_asset`. 나머지는 fixes 에 문제만.
- **[실측] 컬링:** 화면 밖으로 완전히 나간 위젯(과 자식)은 Slate 가 그리지 않아 geometry 가 `(0, 0, 0, 0)` 이다 — 화면 밖 게이트는 이것을 `not_painted` 실패로 세고, fixer 는 측정값 대신 루트 bbox · 앵커로 `bbox_intent` 자리를 계산한다.
- finalize: 통과 = `save_widget_run` → `Content/_AutoGen/<run_id>/`(git 무시) + `lineage.json`, 실패 = `discard_run_packages`.

## 폴더

| 위치 | 내용 |
| :--- | :--- |
| `run_pipeline.py` | 진입점 — 단계 순서 · 잠금(`work/.lock`) · report · 지표 |
| `stages/` | normalize(1a: 손 spec 검사 · 복사) · fault(`--inject-fault`) · codegen · generate · refine · build · verify · fix(결정적 · llm 틀) · finalize |
| `codegen/` | C++ 템플릿 4개 — 생성 베이스 `view_base.h/.cpp.tmpl` · 스텁 `widget.h/.cpp.tmpl` |
| `gen/` | 라우터(`routing.yaml` + `pipeline.yaml backends.allowed`) · procedural 제공자(둥근 프레임 · 그라데이션 패널 · 빛) |
| `core/` | 설정 · JSON Schema 검사 · spec 정규화/왕복 비교 · spec patch · PNG(표준 라이브러리) · run 기록 · 지표 JSONL · `cppgen`(바인딩 계약 · 렌더) · `ue`(브리지 Tool 호출 · 종료 · tasklist · Build.bat · 에디터 기동) · `geometry`(게이트 수치 — 화면 밖 · 겹침 · IoU) · `llm`(`claude -p` 호출 틀) |
| `schemas/` | brief · spec · patch · manifest · report · fixes · codegen · build · lineage (Draft 2020-12, `urn:uigen:<kind>`) |
| `config/` | `pipeline.yaml`(상한 · 경로 · 텍스처 기본값 · codegen 모듈 · 에디터 · 빌드 · 렌더 해상도 · fix 모드 · llm 단계) · `routing.yaml` · `screens.yaml`(화면 ID → 클래스 · WBP 이름 · 폴더) · `empty_mcp.json` |
| `prompts/` · `claude_ctx/` | LLM 단계 시스템 프롬프트 · cwd(설정: Bash · 쓰기 거부, auto-memory 끔) — 1b 부터 |
| `profiles/` | 화면 종류 프로필(게이트 기준) — 1a 는 `hud.yaml` |
| `fixtures/m4_combat_hud/` | 1a 손 brief · spec — M4 전투 HUD(설계 §5 요소, 값은 잠정) |
| `work/` · `metrics/` | run 산출물 · `uigen.jsonl` — git 무시, Saved 밖(이미지를 Read · 전송할 수 있게) |

## run 폴더 (`work/<run_id>/`)

`brief.json` · `spec.json`(지금 목표 spec) · `specs/000.json`(입력 원본) · `specs/00k.json`(시도 k 가 쓴 spec) · `patches/000.json`(결함) · `patches/00k.json`(시도 k 뒤 정정) · `codegen.json`(계약 해시 · 쓴 파일 · skipped · 빌드 · 재기동 검증) · `codegen/`(`build.log` · `editor.log` · 덮어쓰기 전 `backup/` · 실패 원복 때 `failed/`) · `assets/raw` · `assets/final` · `gen.jsonl` · `manifest.json`(build 가 `ue_path` 를 채움) · `build.json`(WBP · revision · 에디터 세션 · 시도별 op) · `attempts/00k/`(`gates.json` · `geometry.json` · `fixes.json` · `render/` 3 해상도 · `sample/`) · `render.png`(기준 해상도 · force_visible) · `render_sample.png`(brief sample 값 — 사람 눈용) · `geometry.json` · `lineage.json`(저장했을 때) · `report.json` · `run.json`(단계 기록) · `run.log`.

## codegen 규칙 요약 (설계 §3-3)

- 화면마다 `Source/AstralBreak/UI/<feature>/AutoGen/<ViewBase>.h/.cpp`(생성 — 첫 줄 `// AUTO-GENERATED by uigen` 이 있을 때만 덮어씀) + `UI/<feature>/<Widget>.h/.cpp`(스텁 — 없을 때만, 이후 사람 소유). 이름은 `screens.yaml`.
- setter: progress `SetX(float Percent)` · text `SetX(const FText&)` · number `SetX(int32)`(`0`) / `SetX(float)`(`0.0` — 소수 자릿수) · flag `SetXVisible(bool)` · image `SetX(UTexture2D*)`. X = binding data id 의 PascalCase.
- 계약(바인딩 목록 + 생성기 식별자)을 생성 헤더 3줄째에 JSON 으로, 해시를 2줄째에 둔다. 해시가 같으면 쓰기 · 빌드 · 재기동을 건너뛴다.
- 바인딩은 추가만 — spec 에서 빠지면 `BindWidgetOptional`, 위젯 클래스가 바뀌면 거부. 빌드 성공 전 실패는 쓴 파일을 원복한다.

## spec 규칙 요약

- 위젯 `id` = WBP 위젯 이름 = 바인딩 이름. 형제 순서 = 슬롯 순서.
- 슬롯 `kind` 는 부모 타입이 정한다(Canvas → `canvas`, Overlay → `overlay`, Border → `border` …).
- 생략한 스칼라는 `core/spec.py` 기본값 표(5.7.4 UMG 생성자 기본값), 생략한 브러시는 엔진 기본 스타일. 파이프라인은 정규화한 spec 을 브리지에 보낸다.
- 왕복 판정 = `roundtrip_view(normalize(입력)) == roundtrip_view(normalize(역추출))` — WBP 가 담지 않는 `bbox_intent` · `binding` 은 빼고, 글자는 값만 비교.
- patch 는 원자적이고, locked 위젯 변경 · 바인딩 제거는 거부된다. 재시도 분기: 바인딩 = codegen, 에셋 교체 = generate, 그 밖 = build.
- `bbox_intent` 는 기준 해상도(spec.canvas)의 의도 좌표 — 루트 Canvas 직계 = 영역(IoU ≥ 0.85), 자식 없는 위젯 = 말단(IoU ≥ 0.70), min(w, h) < 48 이면 중심점 ≤ 8 px.
