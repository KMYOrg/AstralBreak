# uigen — UI 자동 생성 파이프라인

컨셉아트(또는 텍스트 · 참조 이미지)나 손으로 쓴 spec 을 받아 C++ 바인딩 클래스 + WBP 프로토타입을 만들고 렌더 검증까지 무인으로 도는 오케스트레이터입니다. 설계: [Docs/Design/ui-autogen-pipeline.md](../../Docs/Design/ui-autogen-pipeline.md). 에디터 쪽 도구는 [Plugins/WidgetMcp](../../Plugins/WidgetMcp/README.md).

**1b 후속 A · B · C · D 완료(11-15, 미커밋)** — 컨셉에서 프레임 따오기 · 게이지 채움 뽑기 · 세리프 폰트 + 글자 효과(외곽선 · 그림자 · 자간 · 그라데이션) · 게이트 통과 뒤 외형 검토 라운드, 끝 run `R20261115_160430` 무인 통과 · pytest 253(설계 §11 '1b 후속'). **상태: Phase 1a 완료(커밋 `c890a47`) · Phase 1b 완료(11-15, 미커밋) — 컨셉아트 1장 → analyze(LLM) → codex 에셋 → refine(OCR · 9-slice) → build → verify → hybrid fix(LLM) → 저장이 무인 1회 통과(`R20261115_024358`, 3분 56초, 10/10). pytest 198. 숫자 · 다음으로 넘길 것은 설계 §11 'Phase 1b 결과 요약'.** normalize(손 spec) → codegen(C++ 생성 · UBT 빌드 · 에디터 재기동) → generate → refine → build → verify → (fix → 분기)… → finalize 가 끝까지 돈다. 재시도 fix 는 1a 에서 결정적 fixer(LLM 호출 0), `claude -p` verifier · fix 는 호출 틀만 있다(1b). 끝 검증(1a-5): pytest 142 · 정상 run 게이트 10/10 · 왕복 일치 · codegen 해시 건너뛰기 · 지표 줄 · 렌더 색 사람 눈 통과 — 숫자 · 1b 로 넘길 것은 설계 §11.

## 돌리기

```text
Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/run_pipeline.py --spec-dir Tools/uigen/fixtures/m4_combat_hud
Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/run_pipeline.py --spec-dir Tools/uigen/fixtures/m4_combat_hud --inject-fault offscreen
Tools/mcp/.venv/Scripts/python.exe -X utf8 -B -m pytest Tools/uigen/tests -q -p no:cacheprovider
Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/make_concept.py --out-dir Tools/uigen/fixtures/m4_combat_hud_concept   # 1b 컨셉(codex 1회)
Tools/mcp/.venv/Scripts/python.exe -X utf8 -B Tools/uigen/run_pipeline.py --inputs Tools/uigen/fixtures/m4_combat_hud_concept/inputs.yaml --until analyze   # 1b — 에디터 없이 spec 까지
```

- **concept 모드(1b):** `--inputs <inputs.yaml>`(schemas/inputs — 화면 · 계약 · 컨셉 경로, `--concept` 로 그림만 바꿀 수 있음). 단계 = preflight(claude 로그인 · 구독 인증) → normalize(컨셉 → `reference.png` 1920×1080 · `brief.json`) → analyze(`claude -p` + `prompts/analyze.md` → spec, 계약 필드는 코드가 채움 · 검사 실패 시 1회 재요청 · `analyze/overlay.png`) → 이후는 1a 와 같다.

- 종료 코드: 0 = pass · 1 = fail(입력 · 단계 실패 · 게이트 실패 · 잠금) · 2 = incomplete(`--until`).
- 옵션: `--until <단계>`(build · verify 는 첫 시도 뒤, finalize 안 함 — 패키지는 에디터에 저장 안 된 채 남는다) · `--inject-fault offscreen|overlap|drift|shrink_text`(spec 을 깨뜨려 재시도 경로를 돈다 — shrink_text 는 영역 안쪽 결함이라 LLM fix 경로) · `--fix-mode deterministic|hybrid|llm`(pipeline.yaml fix.mode 덮기 — 기본 hybrid) · `--keep-failed`(실패해도 저장) · `--run-id` · `--config` · `--work-root` · `--metrics` · `--module-root`(시험용 — C++ 을 임시 모듈 폴더에).
- 의존성: `Tools/mcp/.venv` 그대로 + PyYAML(`requirements.txt`). pytest 는 에디터 · UBT · 네트워크 · claude · codex 없이 돈다(`tests/conftest.py` 의 `FakeToolchain` + `tests/fake_editor.py`, 가짜 CLI `tests/fake_claude.py` · `tests/fake_codex.py` — `CODEX_HOME` 도 임시 폴더).
- 에디터가 없으면 build 가 DebugGame 에디터를 띄운다(브리지 + 30초). 파이프라인은 끝나도 에디터를 내리지 않는다(다음 run 이 재사용).
- codegen 은 계약이 바뀌면 에디터를 내리고(`quit_editor` — `/Game/_AutoGen/` 밖이 더티면 거절) DebugGame 을 빌드한 뒤 에디터를 다시 띄운다(수 분). 계약이 같으면 건너뛴다.

## 재시도 · 게이트 (설계 §2-2 · §8-1)

- 시도 k 는 `specs/00k.json` 을 쓴다. verify 가 실패하면 fix 가 `patches/00k.json`(정정 patch)을 내고, op 종류로 돌아갈 단계를 정한다 — 배치 · 슬롯 · 스타일 · 텍스트 = build, 에셋 교체 = generate(그 에셋만) → refine → build, 바인딩 = codegen → build. `--inject-fault` 의 결함은 `patches/000.json`(source fault).
- 상한: 재시도 N = 3(`pipeline.yaml limits.retries` — 시도 최대 4번). 실패 게이트 집합이 두 번 연속 줄지 않으면(진부분집합이 아니면) 조기 종료(`NO_PROGRESS`), fixer 가 op 를 못 내면 바로 종료(`NO_FIX`).
- 게이트 10개(값은 `profiles/hud.yaml`): compile · bindings · texture_settings · offscreen(3 해상도 · force_visible) · overlap · required_elements · iou_region · iou_leaf · baked_text(procedural 은 건너뜀) · roundtrip. 모두 `report.json gates[]` 에 남는다.
- 결정적 fixer: 배치 게이트에서 실패한 위젯의 캔버스 슬롯 영역(루트 Canvas 직계 · 점 앵커)을 측정 bbox ↔ `bbox_intent` 차이로 옮긴다(position += d + alignment × dsize · size += dsize). 텍스처 설정 불일치 · 구운 글자 = `replace_asset`. 나머지는 fixes 에 문제만.
- **hybrid(1b-6 기본):** 결정적 fixer 의 op 를 먼저 쓰고, op 가 없거나 직전 결정적 patch 가 실패 게이트를 줄이지 못했으면 LLM verifier(`prompts/verifier.md` — 보는 눈) → fix(`prompts/fix.md` — 고치는 손). LLM patch 는 가드(bbox_intent · binding · 계약 위젯 글자 금지, 필수 요소 제거 금지) · patch 스키마 · 사본 적용으로 검사하고, 안 되면 오류를 붙여 1회 다시, 그래도 안 되면 op 없음(`NO_FIX`). 기록 `attempts/00k/llm_verifier.json` · `llm_fix_N.json` · `llm.jsonl`.
- **[실측] 컬링:** 화면 밖으로 완전히 나간 위젯(과 자식)은 Slate 가 그리지 않아 geometry 가 `(0, 0, 0, 0)` 이다 — 화면 밖 게이트는 이것을 `not_painted` 실패로 세고, fixer 는 측정값 대신 루트 bbox · 앵커로 `bbox_intent` 자리를 계산한다.
- **통과 뒤 외형 라운드(1b 후속 C — `stages/style.py`):** 게이트를 모두 통과하면 finalize 전에 concept 모드에서 영역 · 글자 · 게이지 비교를 기록하고(`style/before/` — `gen/fidelity.region_report`, force_visible 렌더), `pipeline.yaml style_review.rounds`(기본 1)만큼 style_verifier(`prompts/style_verifier.md` — 영역마다 '컨셉 | 렌더' 그림 + 지표) → style_fix(`prompts/style_fix.md`) → build → verify. 허용 op 는 외형만(`style.*` · 글자 색 · 굵기 · 크기 · 폰트 · 효과 · `slot.padding` · `justification` · `replace_asset` 라운드당 1). 합격은 게이트만 — 라운드 뒤 게이트가 하나라도 깨지면 마지막 통과 spec · manifest(· 교체 에셋 파일)로 되돌리고 run 패키지를 전부 버린 뒤(`build.reset_run`) 처음부터 다시 build → verify. 기록 `report.recorded.style_review`(라운드 · op · 전후 요약) · `patches/style_00k.json` · `attempts[]` 의 `style_round` · `revert`. fix.mode deterministic 이면 비교만.
- finalize: 통과 = `save_widget_run` → `Content/_AutoGen/<run_id>/`(git 무시) + `lineage.json`, 실패 = `discard_run_packages`.

## 폴더

| 위치 | 내용 |
| :--- | :--- |
| `run_pipeline.py` | 진입점 — 단계 순서 · 잠금(`work/.lock`) · report · 지표 |
| `stages/` | normalize(1a: 손 spec 검사 · 복사 / 1b: 컨셉 맞춤 · brief) · analyze(1b: LLM → spec · 계약 채움 · 검사 · 1회 재요청 · 겹침 그림) · fault(`--inject-fault`) · codegen · generate · refine · build · verify · fix(결정적 · llm 틀) · style(1b 후속 C — 통과 뒤 외형 라운드 · 가드 · 되돌림 사본) · finalize |
| `codegen/` | C++ 템플릿 4개 — 생성 베이스 `view_base.h/.cpp.tmpl` · 스텁 `widget.h/.cpp.tmpl` |
| `gen/` | 라우터(`routing.yaml` + `pipeline.yaml backends.allowed`) · procedural 제공자(둥근 프레임 · 그라데이션 패널 · 빛 · 세로 색 단계 막대 `gradient_bar` · 컨셉 채움 `concept_fill` — 1b 후속 F `concept_fill.py`) · `codex`(공식 codex CLI built-in image_gen — 한 번에 하나 `work/.codex.lock` · stdin 닫음 · API 키 환경 변수 제거 · `thread_id` 폴더로 결과 찾기 · 한도 판정 · run 당 호출 상한, 1b-2) · `postprocess`(생성 이미지 배경 제거 · 여백 자르기 · 크기 맞춤 · 9-slice margin 축별 추정 · codex 참조 자르기와 글자 자리 지우기, 1b-5 / 1b 후속 A: 따오기 입력 조각(3:1 안으로 넓힘) · 되자르기 · 안쪽 알파) · `fidelity`(1b 후속 A — 따온 에셋 ↔ 컨셉: 구도 · 비율 · 실루엣 IoU · 장식선 F1 · 대표색 ΔE00, 기록만 + 나란히 그림 / D — 글자 획 찾기 `text_ink` / C — 영역 · 글자 · 게이지 전부 `region_report`) |
| 게이지 · 토글 (1b 후속 B) | analyze 가 통과한 뒤 `derive_gauge_fills` — 가로 게이지의 채움을 컨셉의 채워진 부분에서 줄마다 대표색을 뽑아 procedural `gradient_bar`(`<위젯>_fill`)로, 배경은 아래에 따온 프레임이 있으면 none · 없으면 빈 부분 색(`analyze/derived.json`). 샘플이 꺼짐인 flag 위젯은 처음부터 `collapsed`, flag 위젯이 VerticalBox · HorizontalBox · UniformGrid 의 자식이면 `FLAG_IN_BOX` 로 재요청. 렌더 지표 `report.recorded.gauge_fidelity`(채운 · 빈 부분 대표색 · 줄 단위 ΔE00) |
| 게이지 채움 모양 (1b 후속 F) | 아래에 따온 프레임이 깔린 가로 게이지는 `gen/concept_fill.measure` 가 컨셉의 채움 몸통(밝기 문턱 · 열기 · flood)과 트랙 상자(빈 쪽 열에서 프레임 선까지 · 왼쪽 '<' 끝 포함)를 재고, procedural `concept_fill`(reference 에서 다시 그림 — 왼쪽 끝은 컨셉 픽셀 + 알파, 몸통은 줄 대표색, 트랙 띠의 빛 포함)로 채운다. 막대 bbox_intent · slot.padding = 트랙 상자. `pipeline.yaml gauge_fill.end: scale` 이면 진행 끝 테두리 · 번짐까지(ProgressBar `style.bar_fill_style: scale` + 채움 box 여백 = 양끝 고정). 못 재면 B 방식(`shape_fallback` 기록). 지표 `gauge_fidelity.<위젯>.shape`(채움 실루엣 IoU · 왼쪽 끝 차) |
| 글자 빛 · 크기 (1b 후속 F) | `derive_text_glow` 가 컨셉 글자 획 둘레 거리별 밝기에서 번지는 빛을 재 `font.glow{size, color}` + 그 역할의 `sdf_family`(거리장 폰트 사본 `F_NotoSerifKR_SDF` — `import_font_family distance_field`)로 바꾼다. 빛은 외곽선 층을 run 폴더 `M_TextGlow` MIC 로 그린다(SDF 거리값 — Config `bEnableDistanceFieldFontRasterization` · `UI.SlateSDFText.RasterizationMode=Msdf` 필요). 빛은 글자 상자를 사방 size 만큼 키우므로 bbox_intent 를 넓히고 slot padding 을 줄인다(음수). analyze 프롬프트는 폰트별 글자 높이 비(`fonts.glyph_height` — 한글 · 숫자)로 크기를 고른다. 외형 라운드가 글자 크기 · 폰트 · 자간 · 외곽선을 바꾸면 `style.follow_text_boxes` 가 그 글자만 자기 가운데를 중심으로 커지게 하고(슬롯 padding 양쪽 −Δ/2 — 형제 · 패널은 그대로, fill · 고정 크기 세로는 위로 옮김) bbox_intent 를 직전 통과 렌더 상자를 Δ 키운 것으로 바꾼다 — LLM 은 크기 때문에 형제를 보정하지 않는다 |
| 글자 (1b 후속 D) | 역할별 폰트 — analyze 가 TextBlock 마다 `font.role`(body = Pretendard · title = Noto Serif KR, `pipeline.yaml fonts.roles`)을 고르고 `apply_contract` 가 family 경로로 바꾼다. 글자 효과 어휘 `font.outline{size, color}` · `font.shadow{offset, color}` · `font.letter_spacing` · `font.gradient{top_color, bottom_color}`(기본값이면 정규화가 지움 — 그라데이션은 run 폴더의 UI 머티리얼 `M_TextGradient` + MIC, WidgetMcp 가 적용 때 만듦). analyze 뒤 `derive_text_fills` 가 글자색 · 세로 그라데이션을 컨셉의 글자 획에서 뽑는다(`analyze/derived.json text_fills`, `pipeline.yaml text_fill`) |
| spec `source_mode` | codex 에셋만 — `extract`(컨셉에 보이는 요소를 ref_bbox 자르기의 codex **편집**으로 따옴, `pipeline.yaml extract`) · `generate`(없을 때 기본 — 새로 그림, ref_bbox 는 스타일 참조). run 의 `assets/compare/<id>.png` · `report.recorded.extract_fidelity` |
| `make_concept.py` | 컨셉아트 1장 만들기(codex) → `fixtures/<화면>_concept/concept.png` + `concept.json`(출처). 1b 의 concept 입력 — 사람 그림으로 바꿔 다시 돌릴 수 있다. 종료 코드 0 · 1 · 3(한도) |
| `core/` | 설정 · JSON Schema 검사 · spec 정규화/왕복 비교 · spec patch · PNG(표준 라이브러리) · run 기록 · 지표 JSONL · `cppgen`(바인딩 계약 · 렌더) · `ue`(브리지 Tool 호출 · 종료 · tasklist · Build.bat · 에디터 기동) · `geometry`(게이트 수치 — 화면 밖 · 겹침 · IoU) · `ocr`(RapidOCR 검출 모델만 — 구운 글자 상자, 번들 모델 경로 명시) · `llm`(`claude -p` 호출 틀 — 인라인 스키마(`$schema` 뺌 · 최상위 조합자 거부) · `--tools` 로 도구 정의 줄임 · 오류 분류 · run 시작 검사 `preflight`, 1b-1 실측) · `color`(sRGB → Lab · CIEDE2000 · 영역 대표색 ΔE — 1b 후속 A · C 공용) |
| `schemas/` | inputs(1b) · brief · spec · patch · manifest · report · fixes · codegen · build · lineage (Draft 2020-12, `urn:uigen:<kind>`) |
| `config/` | `pipeline.yaml`(상한 · 경로 · 텍스처 기본값 · codegen 모듈 · 에디터 · 빌드 · 렌더 해상도 · fix 모드 · llm 단계) · `routing.yaml` · `screens.yaml`(화면 ID → 클래스 · WBP 이름 · 폴더) · `empty_mcp.json` |
| `prompts/` · `claude_ctx/` | LLM 단계 시스템 프롬프트(`analyze.md` — 1b-4 · `verifier.md` · `fix.md` · `style_verifier.md` · `style_fix.md` — 1b 후속 C) · cwd(설정: Bash · 쓰기 거부, auto-memory 끔) |
| `profiles/` | 화면 종류 프로필(게이트 기준) — 1a 는 `hud.yaml` |
| `fixtures/m4_combat_hud/` | 1a 손 brief · spec — M4 전투 HUD(설계 §5 요소, 값은 잠정) |
| `fixtures/m4_combat_hud_concept/` | 1b 컨셉 입력 — `concept_prompt.md`(codex 프롬프트) · `concept.png` · `concept.json` |
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
