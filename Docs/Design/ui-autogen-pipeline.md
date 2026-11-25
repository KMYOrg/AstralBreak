# UI 자동 생성 파이프라인 설계 (컨셉아트 · 텍스트 · 참조 이미지 → WBP)

작성일: 2026-11-14 · 대상: UE 5.7.4 · 기준 커밋: `88a4813` · 원 요구사항: [ui-autogen-requirements.md](ui-autogen-requirements.md) · 관련: [m4-ult-chain.md](m4-ult-chain.md) §5(HUD)
상태: **Phase 1 종료 · 남은 Phase 조정(11-24 사용자 승인 — §11 'Phase 조정'): 순서 2(정리 · 집계) → 4(이어서 고치기) → 3(조작 화면), 근사 다듬기 · 5 · 6 삭제** · **Phase 4(이어서 고치기) 구현 · 검증 완료 · 미커밋(11-25 — §11 'Phase 4 결과': `run_pipeline --from … --edit …` · 12번째 게이트 `edit_regression` · `promote_screen.py` · 승격 기록 둘, 수정 run 12/12 · 틀린 수정 둘 막힘 · 재승격 → `AstralBreak.` 60/60 → 되돌려 승격본 23/23 처음과 같음, pytest 586 통과 · 정답 묶음 35/35 · 1/1 · 8/8 · 회귀 새 결함 0) — 다음 = Phase 3(조작 화면)** · **Phase 2(정리 · 집계) 완료 · 커밋 `fe0bac4`(11-24 — §11 'Phase 2 결과': verify 1번 StatusHUD 217 → 26초 · CombatHUD 221 → 28초, LLM 외형 라운드 끔, 집계 리포트 · 스킬 문서 둘, 두 화면 run 오류 0 · 회귀 새 결함 0 · pytest 496 · 정답 묶음 35/35 · 1/1 · 8/8 · `WidgetMcp.` 8/8)** · **메인 HUD(내 상태 · 동료 — `StatusHUD`) 구현 · 승격 · 자동 검증 완료 · 커밋 `2c850de`(11-24 — §11 '메인 HUD 결과': 승격본 `R20261124_130129_StatusHUD` · `AstralBreak.` 60/60 · pytest 485 · 정답 묶음 35/35 · 1/1 · 8/8 · 기준선 `status_1124` · run 그림 눈 확인 통과, 게임 안 눈 확인 통과)** · **전투 HUD 동작(고리 줄어듦 · 오의 키 안내 · '오의 불가' 외곽선) 완료 · 승격 · 눈 확인 통과 · 커밋 `a15fad4`(11-24 — §11 '전투 HUD 동작 결과': 승격본 `R20261123_194019_CombatHUD` · `AstralBreak.` 57/57 · `WidgetMcp.` 8/8 · pytest 463 · 정답 묶음 35/35 · 1/1 · 8/8 · 기준선 `ring_1123`)** · **Phase 1 마감 회귀 통과(11-19 — §11 'L 다음 고침' 끝: 빌드 2 구성 · `AstralBreak.` 55/55 · `EditorMcpCore.` 2/2 · `WidgetMcp.` 6/6)** · **1b 후속 L 다음 고침 — 외부 · 단색 입력 결함 고침 미커밋(11-19 — §11 'L 다음 고침'): 판 글자 메우기를 원래 컨셉으로 판정(순서 무관 — 단색 '4' 밑 잔상 · 금선 혹 해결) · 다른 글자 몫 빼기 · 다른 글자 상자는 메움 원천에서 빼기 · 판만 투명한 빛 글자는 판 중앙값 메움 · 글자색 추정 띠 오판 막기, 글자 맞춤 컨셉 대비 안전망 · 빛 크기 ↔ 세기 반대면 세기 먼저, 진단 E1 baked(텍스처에 남은 글자 — 이중 글자). 새 run 단색 전투 HUD 오류 0 · 근사 3 · 파티 HUD 0 · 10 · 조작 안내 원본 0 · 3, 보호 L-1 0 · 1 · L-2 0 · 2, controls_alpha 는 LLM 정정 적용 실패(VALIDATION_FAILED) 사슬을 실패 경로에서만 고친 뒤(재시도 루프 build 거절 받기 · 편집기 어휘 가드 · 결정적 투명 image 브러시 — 사용자 승인 추천안) 새 run 둘 오류 0 · 근사 5 · 0 · 4, L-1 다시 0 · 1, 정답 묶음 25/25 caught · 1/1 clean · 7/7 protected, pytest 382, 기준선 `base_1119`)** · **1b 후속 L 다음 — 외부 · 단색 입력 검증 틀 + 보호 항목(커밋 `db18ab9`, 11-18 — §11 'L 다음', K ~ L 은 사용자 커밋 `93b91c5`): 진단 E1 획에 붙은 잔상(`diagnose.glyph_residue` — 단색 '4' 밑 잔상 11 px 잡음 · 보호 run 오탐 0) · 컨셉 획 측정 실패 안전망(`concept_contrast` → E6 unmeasured — 파티 '100' 을 글자 맞춤이 검정 · 52 로 바꾼 것), 정답 묶음 새 항목 다섯 + 보호(`clean_run`) 넷 → 24/24 caught · 1/1 clean · 4/4 protected, 오프라인 비교 묶음 `regress_set.py`(입력 8 — 기준선 `base_1118`) — 판 메우기 · 글자 맞춤 고침은 다음 단위(사용자 요청 때), 커밋 · 사람 눈은 사용자)** · **1b 후속 L-2 구현(11-18 — §11 'L-2 구현': `make_concept --text-free-first` 글자 없는 원본 아트 + codex 편집 글자 참고판 · normalize 가 레퍼런스 = 원본 아트 + 참고판 글자 획(`gen/text_ref`) · 아트 · 글자 없는 판 = 원본 아트, 원래 전투 HUD 를 L-2 로 새로 만든 run `R20261118_142524` 오류 0 · 근사 2, 회귀 controls_alpha 오류 0 · 원래 전투 HUD L-1 오류 1(E6 — L-3 남은 결함, L-2 탓 아님), pytest 365 · 정답 묶음 19/19 · 디자이너 미리보기 = 컨셉 상태(spec `designer_hidden` + WidgetMcp C++ · 빌드 2), `WidgetMcp.` 6/6(K 부터 낡았던 ImportFont 기대값 고침), 빛 세기 = 가장 가까운 선택(E9 `glow_strength` + 알파 맞춤 — 마지막 L-2 run `R20261118_164931` 오류 0 · 근사 4), '체인 버스트' 정렬 끝 판정 갈림 고침(자간 뒤 폭 판정 · 빈 열 뺀 획 밀도 + 굵기 표 다시 잼) — 마지막 코드 run: L-2 `R20261118_175732` 오류 0 · controls_alpha `180405` 오류 0 · L-1 원래 전투 HUD `175104` 오류 1(E1 진단 거짓 양성 — '4.2' 빛 상자가 '체인' 받침 획을 가져가 바탕으로 셈, '체인 버스트' 자체는 해결), pytest 366 · 정답 묶음 19/19 — 사람 눈 · 커밋은 사용자)** · **진단 거짓 양성 E1 고침 미커밋(11-18 — §11 L-2 절 끝: `assign_glyphs` 겹친 core 안에만 있는 센 획은 통째로 이어진 본체 쪽 · 정답 묶음 '오류 아님' 항목 19/19 caught · 1/1 clean · pytest 367 · L-1 원래 전투 HUD `R20261118_184602` 오류 0 · 근사 0, L-2 `R20261118_191532` 오류 0 · 근사 2 — 새 측정대로 '체인' black · '2/4' medium)** · **1b 후속 L-1 · L-3 구현 미커밋(11-18 — §11 'L-1 · L-3 구현': 아트 모드 = 원본 생성 아트일 때만 · 정답 묶음 18/18 · Spacer 겹침 제외 · 판 글자 메우기 정리 · 그림자 측정, 최종 코드 끝 run 오류 0 = controls_alpha · 조작 안내 원본, 원래 전투 HUD 1 · 단색 2 · 파티 9(앞 run 은 원래 · 단색 0))** · **Phase 0 완료 · 커밋 `6700484`(2026-11-14)** — 플러그인 분리(EditorMcpCore · AnimGraphMcp · StateTreeMcp · WidgetMcp 뼈대) · 빌드 2구성 · 회귀 통과, 가정 A1 ~ A7 결과는 §12-1(A4 · A5 는 사용자 CLI 로그인 뒤 `claude` 2.1.325 로 실측). **Phase 1a 완료(11-15)** — 하위 단계 1a-1 ~ 1a-5 끝, 끝 조건 4개 충족(§11 'Phase 1a 결과 요약' · '1b 로 넘길 것'), 빌드 2구성 · 에디터 1회 · pytest 142 통과, 렌더 색 사람 눈 확인 통과(§12-1 A6-색) — 커밋 `c890a47`. **Phase 1b 완료(11-15, 미커밋)** — 하위 단계 1b-1 ~ 1b-7(§11), 끝 조건 충족: 컨셉아트 → analyze → codex 에셋 → build → verify(hybrid LLM fix 1회) → 저장이 **무인 1회 통과**(`R20261115_024358`, 3분 56초, 10/10) + 리포트. 빌드 2구성 · 에디터 시험(`AstralBreak.` 55/55 — 1차 53/55 일시 실패 · `EditorMcpCore.` 2/2 · `WidgetMcp.` 6/6) · pytest 198 통과. 렌더 사람 눈 확인 결과(11-15): **레이아웃은 맞고 외형(게이지 · 프레임 모양 · 글꼴)은 다름** — 다음은 1b 후속 '외형 재현 A · B · C · D'(사용자 결정 — §11 방향 메모). **1b 후속 A 완료(11-15, 미커밋)** — 컨셉에 보이는 프레임 · 패널을 codex **편집**으로 따오기(spec asset `source_mode: extract`) · 공용 ΔE00(`core/color.py`) · 충실도 기록(`gen/fidelity.py`) · 9-slice 추정 v3(축별) · 안쪽 칠하기 · **크기 고정 위젯은 image 로 그리기**(사용자 눈 확인 지적 — box 9-slice 가 2배 텍스처의 모서리를 키우고 가운데를 누름) · WBP 렌더 ↔ 컨셉 이식 지표, 채록 2장 + 실제 run 3회(전부 10/10 — run 3 은 LLM fix 1회 뒤) · pytest 227(§11 'A 에서 확인 · 정한 것' · 'A 보강'). **1b 후속 B 완료(11-15, 미커밋)** — 게이지 채움 · 배경을 컨셉에서 결정적으로 뽑기(procedural `gradient_bar`) · 꺼진 flag 초기 접힘 · flag 위젯 상자 패널 금지 · 따온 텍스처를 위젯 상자 그대로 되자르기(A 결함 수정), C++ 변경 없음, 실제 run 2회(둘 다 LLM fix 1회 뒤 10/10) · 렌더 장식선 F1 0.98 · 0.90 · 0.96 · 게이지 채움 줄 단위 ΔE00 12.1 → 1.8 · pytest 235(§11 'B 에서 확인 · 정한 것'). B ③ 은 D 로. **1b 후속 D 완료(11-15, 미커밋)** — 제목 · 숫자용 Noto Serif KR(OTF) 임포트 · 역할별 폰트(`font.role` → family) · 글자 효과 어휘 outline · shadow · letter_spacing · gradient(WidgetMcp C++ — 그라데이션은 run 폴더 UI 머티리얼 + MIC) · 글자색 · 그라데이션을 컨셉에서 결정적으로 뽑기, 실제 run 1회(LLM fix 1회 뒤 10/10) · 금색 글자 획 대표색 ΔE00 15.9 · 18.4 → 0.9 · 1.2 · pytest 245 · `WidgetMcp.` 6/6(§11 'D 에서 확인 · 정한 것'). **1b 후속 C 완료(11-15, 미커밋)** — 게이트 통과 뒤 외형 검토 라운드(LLM style_verifier → style_fix, 허용 op 는 외형만 · 게이트가 깨지면 run 패키지를 전부 버리고 마지막 통과 spec 으로 다시 build) · 영역 · 글자 · 게이지 전부의 컨셉 ↔ 렌더 비교 기록, 끝 run `R20261115_160430` 무인 통과(라운드 1회 받음 — 글자 높이 비 오차 0.094 → 0.046 · 체인 패널 장식선 F1 0.899 → 0.978) · pytest 253(§11 'C 에서 확인 · 정한 것'). **1b 후속 F 완료(11-15, 미커밋 · 사람 눈: run 4 가 낫고 게이지 · 빛 지적 없음, 남은 차이 = 배너 위아래 빛 · 체인 패널 모서리 · 글자 위치 약간 — A 따오기 · analyze 몫, 다음 후속 G)** — 사람 눈 판정의 외형 차이 셋: 게이지 채움을 컨셉 모양 그대로 따오기(procedural `concept_fill` — 왼쪽 '<' 끝 · 밝은 테두리 · 트랙 띠 빛) + 진행 끝 테두리 · 번짐(WidgetMcp ProgressBar `bar_fill_style: scale` + 채움 9-slice) · 글자 빛(엔진 SDF 글꼴 + 외곽선 층 빛 머티리얼 `font.glow` — Config 2줄 · 새 폰트 `F_NotoSerifKR_SDF`, 컨셉에서 결정적으로 — '4.2' 만) · 배너 크기(analyze 글자 높이 비 정정 + 외형 라운드에서 크기 바뀐 글자만 가운데 중심으로 커지게), 끝 run 5번 모두 무인 통과(외형 라운드 받음 1 · 버림 4 — 원인마다 고침, 마지막은 analyze 배치 한계로 남김) · 게이지 채움 줄 단위 ΔE00 6.52 → 0.51 · 실루엣 IoU 0.891 → 0.937 · 회귀 빌드 2구성 · `AstralBreak.` 55/55 · `EditorMcpCore.` 2/2 · `WidgetMcp.` 6/6 · pytest 264(§11 'F 에서 확인 · 정한 것'). **1b 후속 G 완료(11-15, 미커밋 · 사람 눈: '오의 불가' 글꼴(굵기)만 약간 다르고 나머지 통과)** — F 사람 눈의 남은 차이 셋: 따온 frame · panel_bg 에 **컨셉 픽셀 옮겨 심기**(`gen/concept_pixels` — codex 는 실루엣만, 상자를 꽉 채우는 사각 패널은 실루엣도 상자 · 금테 색 · 모서리 장식 · 안쪽 위아래 빛은 컨셉 그대로, 글자 자리는 메움) · 외형 라운드 다시 따오기의 **충실도 기준**(나빠지면 그 에셋만 옛 것) + 모서리 장식선 지표 · **글자 위치 결정적 맞춤**(`style.text_fit` — 글자 사이 틈 차이로 자간 · 중심 차를 자리 유지 padding 으로, LLM 없음), run 간 흔들림은 이 결정적 단계로 흡수(추가 비용 없음), C++ · Config 변경 없음 · 끝 run 4번 모두 무인 통과(1 ~ 3 에서 결함 셋을 찾아 고침) · 체인 패널 모서리 장식선 F1 최소 0.643 → 1.0 · 배너 장식선 ΔE00 20.6 → 6.0 · 글자 중심 차 ≤ 1.5 px · pytest 273(§11 'G 에서 확인 · 정한 것'). **G 후속 완료(11-16, 미커밋 · 사람 눈: 글자 통과 — '오의 불가' 글꼴은 비슷한 폰트 없음, 게이지 테두리 · 빛의 run 간 흔들림은 뒤로)** — 글자 굵기 · 크기도 결정적으로: `style.text_fit` 을 크기 판(높이 비로 새 크기 · 굵기, build 전 형제 겹침 예측으로 성장 상한) → 위치 판(자간 · 중심 · 걸쳐 잘린 획 다시 재기 · 겹침 없으면 자기 padding 이동)으로 나눠 판마다 build → verify · 그 판만 버림, 외형 라운드를 받든 버리든 글자가 같게 — 끝 run `R20261116_093639` 무인 통과 · 남은 중심 차 ≤ 1 px · 높이 비 0.95 ~ 1.02 · pytest 278(§11 'G 후속'). **1b 후속 G2 완료(11-16, 미커밋 · 사람 눈: 게이지 개선됨, 새 컨셉 2장은 매핑 미흡)** — 게이지 테두리 · 빛을 run 마다 같게(게이지 프레임 옮겨 심기 — 트랙 전체를 빈 트랙 색으로 · 숨은 빛 procedural 고정) + 다른 컨셉 2장(파티 HUD · 조작 안내 — 상용 게임 화면, git 무시 `work/_probe`)으로 보편화 검증(C++ 없는 검증 화면 모드 `screens.yaml probe`), 새 컨셉이 드러낸 일반 결함 9 개 고침, 최종 코드 세 컨셉 모두 무인 통과 · pytest 283 — 남은 차이(선 끊김 · 잘림 · 띠 장식 · 반투명)는 '합성 스크린샷을 codex 로 다시 그리는' 에셋 확보 방식의 한계로 정리(§11 'G2'). **1b 후속 H 설계(11-16, 사용자 승인 — 구현은 새 세션)** — 에셋 확보를 '컨셉 픽셀 직접 오리기'로(창작 = codex, 매핑 = 결정적), 구현 · 검증은 새 세션(§11 'H 설계'). **1b 후속 H 진행 중(11-16, 미커밋)** — 오리기 · 배경 판정 · 넘침 장식 Image 구현, 시험 입력 4개 무인 통과 · pytest 299, 단색 배경 컨셉은 깨끗 · 합성 스크린샷은 잔상 · 흐림(사람 눈) → 사용자 결정으로 codex 'UI 만 컨셉' 변환 뒤 오리기(조작 안내 시험 통과), 남은 글자 자리 패치는 codex '글자 없는 판'으로 메우는 중(이어서 새 세션 — §11 'H 에서 확인 · 정한 것'). **1b 후속 H2 완료(11-16, 미커밋 · 사람 눈: '이 정도면 나쁘지 않다')** — 글자 없는 판(`make_concept --text-free` · inputs `concept_notext`)으로 글자 구멍만 메우기 · 오리는 위젯 상자가 겹친 자리는 한쪽만 그리기 · 모서리 장식 글자 획 오인 · 글자 맞춤 컨셉 측정을 판 차이로 + 크기 판 신뢰 범위 0.7 ~ 1.4, 글자 획 측정(가로선 오인 · 글자색 쪽 · 큰 띠 테두리) 고침으로 라벨 굵기 · 크기 · 위치까지 컨셉과 같게, 최종 run `R20261116_212649` 무인 통과(장식선 F1 0.9997 · 끊김 0 · 글자 높이 비 0.97 ~ 1.0) · 단색 전투 HUD `R20261116_185558` 통과 · pytest 307 · 'T 미표시' 원인(위 z 장식 텍스처가 글자를 가림) 확인 · 고침(§11 'H2'). **1b 후속 H3 완료(11-17, 미커밋)** — 검정 배경(ⓑ)은 어둡고 반투명한 장식을 불투명으로 읽어(회색 바탕에서만 보임) 진짜 알파 컨셉(`make_concept --transparent` · ⓐ)으로 바꿈 · 회색 바탕 확인(`gen/backdrop` — `report.recorded.backdrop`) · 판 알파 맞춤 · 획 둘레 정합 · 넘침 장부 · 아래 영역 글자 · 이미지 자리 비우기, 최종 run `R20261117_095249` 무인 통과(회색 ΔE00 0.22 · 컨셉에 없는 알파 절벽 0) · 단색 전투 HUD `R20261117_094643` 통과 · pytest 316, 스킬 아이콘 런타임 이미지는 동작하나 마름모 아이콘 회전이 남음(§11 'H3'). **1b 후속 H 계열 종료(11-17, 미커밋)** — 남은 작은 문제 마무리: 다른 영역 글자 보호(측정) · 렌더 글자 마스크(글자 없는 합성 차 — 못 믿을 때만) · 겹친 자리 양쪽 같은 답 · 아이콘 실루엣 0.85 · 오리는 이미지 여유 막기 없앰 · 글자 주인 둘레, 최종 run `R20261117_120813` · `R20261117_121432` 무인 통과 · pytest 319 — 마름모 아이콘 · 다른 컨셉 적용 검증은 뒤로(§11 'H 계열 마무리'). **1b 후속 I 완료(11-17, 미커밋)** — 오리는 위젯이 겹친 자리를 물체 단위로(`refine.cut_ownership` — 알파 경계 위 가장 넓은 길 · 동점 = 작은 상자 · 넘칠 수 있는 위젯 둘레 8 px, 배너 텍스처가 끝 · 끝 장식을 혼자 갖고 엠블럼 텍스처엔 엠블럼만 — 오프라인 4 배치 회색 ΔE00 0.168 · 0.157 → 0.157 · 0.127 · 구멍 0) + 합성 스크린샷을 codex 편집 2 회로 'UI 만 · 진짜 알파' 컨셉 + 글자 없는 판으로 자동 변환해 ⓐ 로 잇는 단계(`gen/concept_convert` · inputs `concept_convert: auto | force | off` · 캐시 `work/_convert` · run 당 2 회 · 실패면 예전 경로), 끝 run 원래 전투 HUD `R20261117_134535` · 조작 안내 원본 `R20261117_135206`(회색 ΔE00 0.24 · 절벽 0) · 회귀 `R20261117_135820`(0.14) 무인 통과 · pytest 326, I 후속(사람 눈 — 디자이너 확대 때 텍스처 경계 검은 절취선 · 엠블럼 직선 잘림): 투명 픽셀 색 채우기 · 불투명 2 px 겹침 · 반투명 소용돌이는 겨루지 않는 자기 반투명 쪽 — 3 배 확대 절취선 7 천여 → 800 ~ 1,300 px(오프라인), 확인 run `R20261117_154442` 무인 통과 · pytest 328(§11 'I'). **1b 후속 J 설계 작성 · 결정(11-17, 구현 전)** — 텍스처를 런타임 기능 단위로 나누기(정적 장식은 한 장 · 기능 요소만 따로 · 요소 없는 판) + 레퍼런스 ↔ 렌더 국소 차이 자동 진단(원인 단계 짚기 · 게이트) + LLM 외형 라운드 글자 스타일 금지(§11 'J 설계'). 설계 승인(11-14) · §12-2 질문 1 · 2 · 4 · 5 · 6 · 8 결정. 값은 전부 잠정이다. **1b 후속 J 진행 · 미커밋(11-17, I 는 커밋 49a45be)** — J-b 자동 차이 진단 게이트 appearance(gen/diagnose) · J-a 기능 단위 레이어(stages/layer — 정적 판) · J-c 글자 스타일 결정적만(외형 라운드 글자 op 금지 · 글자색 · 외곽선 맞춤), 끝 run 4/5 무인 통과(controls_alpha 173753 · 조작 안내 원본 175512 · 전투 HUD 183524 · 단색 191446 — 진단 결함 0), 파티 HUD 192631 진단 결함 11 로 실패(게이지 · 글자 — §11 'J 에서 확인 · 정한 것' 다음), 최종 코드 5 입력 재확인 남음 · pytest 343. **1b 후속 J 남은 일(11-17 밤, 미커밋)** — 본문 Pretendard SDF 사본(`F_Pretendard_SDF` · `fonts.roles.body.sdf_family` — '오의 불가' 빛 그려짐 · limits 0) · 파티 HUD 고침(0 % 게이지 판 유지 · 가득 찬 게이지 컨셉 조각 · 투명 위 · 정합 실패 글자 상자 안 메우기 · 빛으로 이어진 글자 획 나누기 · 빛 크기 맞춤 · 글자 맞춤 판 글자별 다시 고르기), 최종 코드 다섯 입력 중 **넷 무인 통과(진단 결함 0)** — 파티 HUD 는 결함 11 → 1(HP 현재치 위치 — 컨셉 숫자 글꼴이 좁음, 사용자 결정 남음) · pytest 347(§11 'J 남은 일'). **사람 눈(11-17 밤): 진단 0 인 run 에도 굵기 · 컨셉에 없는 빛 · 글자 둘레 얼룩이 보임 → 1b 후속 K 설계 작성(구현 전 — 오류 0 · 가장 가까운 스타일, 우리가 만든 컨셉은 글자 없는 아트 + 엔진 글자, 외부 컨셉은 오류 0 + 근사 표, 검증 = 컨셉 상태 비교 그림 · 글자 구역 바탕 · 빛 단일 측정 · 사용자 발견 결함 정답 묶음, §11 'K 설계' — 질문 4 개 전부 추천안으로 결정, 구현 전)**. **1b 후속 K 구현(11-18, 미커밋 — §11 'K 구현'): 오류(E1 ~ E9) · 근사 판정 · compare.png(컨셉 상태 엔진 렌더) · 정답 묶음 16/16 · 빛 단일 측정 · 굵기 변형 family(+ WidgetMcp 굵기 어휘 C++ · 빌드 2) · (가) 글자 없는 아트 정답 · (나) 좁은 색조 맞춤 메우기. 끝 run: 원래 전투 HUD · controls_alpha · 조작 안내 원본 오류 0(근사 2 · 4 · 4), 단색 전투 HUD · 파티 HUD 는 남음(§11 표), pytest 349 — 사람 눈 확인 · 커밋은 사용자.** **사람 눈(11-18): (가) 아트 정답 탓 게이지 테두리 빛 · 배너 색 차이(진단이 아트와 비교해 못 봄) → 1b 후속 L 설계 작성(구현 전 — L-1 컨셉 픽셀 + 글자 자리만 판 · L-2 글자 없는 컨셉부터 + 글자 참고판 · L-3 남은 결함 단색 배너 위치 · 파티 HUD · 글자 그림자, §11 'L 설계' — 질문 5 개)**.

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
6. 합격은 규칙 · 수치로만. 외형은 국소 ΔE 게이트(`appearance`, 1b 후속 J)가 본다 — 스타일 유사도는 재지 않는다(11-24, §11 'Phase 조정').
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
| 12 | 수치 지표 전부로 합격 판정 | 영역 대표색 ΔE 는 기록만, 국소 ΔE 는 외형 게이트(1b 후속 J) — 스타일 유사도는 21 | 보정 안 된 임베딩 임계값은 결과를 흔든다 |
| 13 | Phase 1 ~ 6 | Phase 0(플러그인 분리 + 스파이크) 추가, Phase 1 = 1a(손 spec) · 1b(컨셉아트) | §11 |
| 14 | 출처 3종 | `provided` 추가(component 이미지를 그대로 쓰기) | 요청 때 `use: auto/asset/reference` 로 선언 — 실행 중 묻지 않는다 |
| 15 | 진행 순서 Phase 2 → 3 → 4 | **2 → 4(이어서 고치기) → 3(조작 화면)** (11-24) | 작은 수정도 LLM 분석부터 다시 돌아 승인한 부분이 흔들린다 — §11 'Phase 조정' |
| 16 | text 모드 — 목업 K장 생성 · 규칙 + LLM 자동 선택 | 글 → 그림은 `make_concept`(L-2), 후보는 **사람이 고른다**. 한 명령으로 묶기만 한다 (11-24) | 원본 아트가 사람이 승인하는 픽셀 정답이라 자동 선택이 맞지 않는다 |
| 17 | multi_ref — layout · style · component · mood 역할 | `--style-ref`(느낌 · 색 · 재질)만. 나머지 역할 · 충돌 우선순위 · component 개별 비교는 만들지 않는다 (11-24) | 쓸 화면이 없다. 필요해지면 그때 설계 |
| 18 | 수정 모드 — 주석 스크린샷 · 새 목업 해석 | 이어서 고치기 · 재승격 · 되돌리기 먼저, 지시 해석 · 주석 스크린샷은 뒤(선택) (11-24) | 지금 막히는 곳은 해석이 아니라 다시 도는 비용과 재승격이다 |
| 19 | ComfyUI 백엔드 · 아이콘 A/B (Phase 5) · codex 한도 폴백 | 삭제 (11-24) — 다시 여는 조건은 §11 'Phase 조정'. 한도에 걸리면 지금처럼 멈추고 재개 | 11-17 부터 run 안 codex 에셋 0 개 |
| 20 | 지표 기반 라우팅 (Phase 6) | 삭제 (11-24) | 고를 백엔드가 없다 |
| 21 | 스타일 임베딩 유사도 | 삭제 (11-24) — 외형 게이트(국소 ΔE) · 정답 묶음 · 사람 눈으로 대신 | 한 번도 재지 않았고(1,424 줄 중 0), 컨셉 픽셀이 정답이라 국소 비교가 더 엄격하다 |

---

## 2. 전체 구조

### 2-1. 구성 요소

```text
run_pipeline (Python 오케스트레이터 — 순서 · 재시도 · 분기 · 상한 · 잠금)
 ├─ LLM 단계 ─────▶ claude -p   (UE 도구 없음 · work/<run_id> 파일만 읽고 씀 · JSON 스키마 출력)
 ├─ 코드 단계 ────▶ editor_bridge (HTTP 127.0.0.1:18765) ─▶ UE 에디터: EditorMcpCore + WidgetMcp
 │               ├─▶ generate_ui_asset 라우터 ─▶ procedural / codex exec / provided
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
- **통과 뒤 외형 라운드(1b 후속 C — `stages/style.py` · `run_pipeline._style_review`, Phase 2 부터 기본 끔 — `rounds: 0`):** 게이트가 모두 통과하면 finalize 전에, concept 모드(reference 있음)에서 영역 · 글자 비교를 기록하고(`style/before`), `style_review.rounds`(기본 1)만큼 style_verifier → style_fix → (에셋 교체면 generate → refine) → build → verify 를 돈다. 허용 op 는 외형만(`style.*` · 글자 색 · 굵기 · 크기 · 폰트 · 효과 · `slot.padding` · `justification` · `replace_asset`) — 배치는 못 고친다. **합격 판정은 그대로 게이트만**: 라운드 뒤 게이트가 모두 통과하면 그 라운드를 받고, 하나라도 깨지면 버린다 — 마지막 통과 spec · manifest(· 교체한 에셋 파일)로 되돌리고 저장 안 한 run 패키지를 전부 버린 뒤 처음부터 다시 build → verify(통과해야 함, 아니면 `STYLE_REVERT_FAILED`)하고 finalize — 에디터의 WBP · 라운드가 만든 텍스처 · 머티리얼이 라운드 상태로 저장되지 않게. fix.mode deterministic 이면 라운드는 돌지 않고 비교만 기록한다. 라운드 시도도 `specs/NNN.json` · `attempts[]`(`style_round`, 되돌림은 `revert`)에 남고 재시도 상한 N 에는 세지 않는다.
- codegen 은 **바인딩 계약 해시가 바뀔 때만** 돈다 — 대부분의 재시도는 빌드 · 재기동이 없다.
- codegen 이 analyze 직후(아직 에디터에 이번 run 의 것이 없을 때)라서 재기동해도 잃는 것이 없다. 재시도 중 재기동이 필요하면 저장 안 한 run 패키지를 버리고 spec + manifest 에서 다시 빌드한다(결정적이라 같은 결과).

### 2-3. 에디터 운용

- 시작 · 대기 · 종료는 CLAUDE.md 의 에디터 주기를 그대로 쓴다(DebugGame 에디터 · `wait_for_bridge.py` · `quit_editor` · `wait_for_exit.py`).
- `quit_editor` 는 더티면 거절한다 — **`/Game/_AutoGen/` 만 더티일 때 discard 를 허용**하도록 그 목록에 더한다.
- codegen 빌드는 실행 중인 에디터 구성(DebugGame)만 한다. 두 구성 빌드는 Phase 검증 때(프로젝트 회귀 방침).
- ~~Phase 5 ComfyUI~~ 삭제(11-24, §11 'Phase 조정') — 다시 열면 12 GB VRAM 을 에디터와 나누지 않게 generate 동안 에디터를 내린다(§7).

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
| `list` | 반복 하위 WBP(ListView 는 대형 인벤토리 때) | Phase 3 (하위 WBP 생성과 같이 — 버튼 이벤트 계약도 여기, 11-24) |

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
- 위젯 타입 어휘(Phase 1): CanvasPanel · Overlay · VerticalBox · HorizontalBox · UniformGridPanel · SizeBox · Border · Image · TextBlock · ProgressBar · Button · Spacer. Phase 3 에서 하위 WBP(`repeat`) · 버튼 상태 · 이벤트(11-24 조정 — ScrollBox · ListView 는 대형 인벤토리 때, Slider · CheckBox · ComboBoxString 은 쓸 화면이 없어 뺌).
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

`metrics/uigen.jsonl` 한 줄 = 에셋 하나 또는 run 하나: `run_id · asset_id · kind · backend · ok · duration_s · retries · verify · style_sim_anchor` (+ comfy: `workflow_sha256 · model_sha256 · lora_sha256[] · seed`, codex: `codex_version`). Phase 1 부터 쓰고, 집계는 Phase 2. `style_sim_anchor` 는 늘 null 이고 comfy 필드는 쓰지 않는다(11-24 — 둘 다 삭제).

---

## 5. 화면 종류 프로필 (`profiles/*.yaml`)

| 항목 | hud | menu (장비 · 인벤토리 · 상점) | options | dialog |
| :--- | :--- | :--- | :--- | :--- |
| 배경 | 없음(투명) | 전체 화면 패널 | 전체 또는 중앙 패널 | 반투명 막 + 중앙 패널 |
| 앵커 | 화면 가장자리 · 세이프존 안 | 영역 단위 | 영역 단위 | 중앙 |
| analyze 주의 | **reference 뒤의 게임 장면과 UI 분리** — 장면을 에셋으로 만들지 않는다 | 반복 슬롯 = 그리드 + 템플릿 | 표준 컨트롤(Slider · CheckBox · ComboBox) | 버튼 행 |
| verify 영역 | UI bbox 합집합만 비교(장면 제외) | 전체 | 전체 | 패널 |
| 작은 요소 | 많음 → 중심점 거리 기준 | 슬롯 아이콘 | 적음 | 적음 |
| Phase (11-24 조정) | 1 | 3 | 쓸 화면 없음 — 뺌 | 3 |

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
| `promote_widget` | run 결과를 `/Game/UI/<기능>/` 로 복사(원본 run 은 그대로) | `promote_animation` 과 같은 방식 · **최소판은 M4 단위 C 가 앞당김(11-19, 미커밋)** — `WidgetMcpPromote.cpp` · `IAssetTools::AdvancedCopyPackages` · `[WidgetMcp] WidgetPromotionPaths=/Game/UI/HUD/` 아래 화면별 새 폴더 · `dry_run` → `confirm` · 대상이 있으면 거절 · 다른 run 에 기대면 거절 · 무인 파이프라인 밖. 재승격(대상이 있을 때) · lineage 잇기 · 되돌리기 = Phase 4 `promote_screen.py`(11-25 — 이 Tool 은 그대로, 에디터를 끈 채 파일을 사본으로 치운 뒤 빈 폴더에 부른다) |
| `import_font_family` | **[1b-3]** 폰트 파일 → `UFontFace` 여러 개 + 컴포지트 `UFont`(타입페이스 = spec 굵기 이름) — 프로젝트 폰트라 저장까지 | 이 Tool 만 별도 접두 `WidgetFontOutputPaths=/Game/UI/Fonts/`(§11 '1b 착수 때 정한 것' — 위 '쓰기는 `/Game/_AutoGen/` 만'의 예외) · 덮어쓰기 거부 · 전역 더티 비교 · `UFontFileImportFactory` 순서 [소스] `EditorFactories.cpp:5077` |

`get_editor_status` 에 `widget` 섹션(허용 경로 · 폰트 · 렌더 출력 루트)을 더한다.

---

## 7. 이미지 생성 백엔드 — `generate_ui_asset`

```yaml
# Tools/uigen/config/routing.yaml (잠정 — 아래 comfy A/B · mockup 줄은 11-24 조정으로 쓰지 않는다)
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
- **comfy (Phase 5 — 삭제 11-24, §11 'Phase 조정'. 다시 열 때의 메모):** SDXL급 + 스타일 참조(앵커 이미지). 실행마다 워크플로 JSON · 모델/LoRA 해시 · 시드를 기록. generate 동안 에디터를 내린다(12 GB 공유).
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

### 8-2. 기록만 (게이트로 올리지 않는다 — 11-24 조정, 외형 판정은 `appearance` 게이트)

| 지표 | 잠정 목표 | 비고 |
| :--- | :--- | :--- |
| 영역 대표색 ΔE00 | 평균 ≤ 10 | reference vs render, 영역 마스크 — **[1b 후속 C] 구현 · 기록:** `gen/fidelity.region_report`(영역 · 글자 · 게이지 전부, force_visible 렌더) → `style/<라벨>/report.json` · `report.recorded.style_review`. 글자는 획 상자(크기 · 중심) · 획 대표색 ΔE00 |
| ~~스타일 유사도~~ | 삭제(11-24) | 한 번도 재지 않음 — §1 21 |
| ~~component 유사도~~ | 삭제(11-24) | component 역할을 만들지 않음 — §1 17 |
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
| 기존 에셋 덮어쓰기 · 삭제 금지 | `ProtectedPaths` · 덮어쓰기 거부 · 수정도 새 run 폴더 · 폐기는 저장 안 한 이번 run 패키지만. **예외 하나(11-24 사용자 승인 — Phase 4): 사람이 확인하고 부르는 `promote_screen.py apply · revert`** — 에디터를 끈 채, 자기가 기록한 승격본 파일이 그대로일 때만(파일 SHA256 + 파일 목록, 다르면 거절 · 강제 옵션 없음), 해시를 확인한 사본을 남긴 뒤 바꾸고 실패하면 되돌린다. 무인 파이프라인은 부르지 않는다 |
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
| 저장소 `.claude/skills/` | `ue-umg-authoring`(Phase 2 에서 씀) — GUID 맵 · FWidgetRenderer · 텍스처 설정 · BindWidget · UHT 헤더 이름 등 부딪힌 엔진 제약 | 개발 세션(플러그인 구현) |
| 저장소 `.claude/skills/` | `uigen-run`(Phase 2 에서 씀) — 파이프라인 돌리는 법 · 리포트 읽는 법 · 에디터 주기 | 개발 · 운용 세션 |
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
| → M4 C | 스텁 `UAstralCombatHUDWidget` 에 게이지 · 체인 연결(개발 세션) — **완료 — 커밋 `929085f`(11-19 첫 승격본 L-1 `R20261119_091634`, 결과는 M4 설계 §6 '단위 C 구현 결과') · `a15fad4`(11-23 승격본을 L-2 '검은 날' `R20261123_172628` → 고리 · 키 안내를 더한 `R20261123_194019` 로 바꿈 — §11 'L-2 기본 전환 결과' · '전투 HUD 동작 결과'), 사용자 눈 확인 통과(11-23)** | M4 설계 §5 화면 동작 | M4 방침 |
| ~~→ 근사 다듬기~~ | **삭제(11-24 조정)** | — | — |
| **2** | **완료(11-24 — 'Phase 2 결과')** · 정리 · 집계(작게) — run 기록 집계 리포트 · LLM 외형 검토 라운드 끄기 · verify 시간 줄이기 · 스킬 문서 둘(§10-2) | 집계 리포트 1개 · 라운드를 끈 run 이 오류 0 · verify 시간 앞뒤 수치 · 스킬 둘(잠정) | pytest · 정답 묶음 · `regress_set` · 실제 run |
| **4**(2 다음 — 3 보다 먼저) | **완료(11-25 — 'Phase 4 결과')** · 이어서 고치기 — 지난 run 의 최종 spec 에서 이어 시작(analyze 생략) · 안 바꾼 위젯은 그대로(수정 회귀 게이트) · 재승격 · 되돌리기 · 사람이 고친 WBP 안 덮기. 선택(뒤): 지시 해석 · 주석 스크린샷 → 위젯 매핑 | 승격한 화면 하나를 이어서 고쳐 수정 회귀 게이트 통과 · 재승격 · 되돌리기 1회(잠정) | 실제 run |
| **3**(4 다음) | **설계 승인(11-25 — 'Phase 3 설계') · 3-1 화면 체계(완료 11-25 — 'Phase 3-1 결과') → 3-2 칸과 버튼(완료 11-25 — 'Phase 3-2 결과', 버튼 칸 둘 승격) → 3-3 화면(완료 11-25 — 'Phase 3-3 결과', 파티 줄 칸 승격 · `HubReady` 눈 확인 통과) → 3-4 게임 연결** · 조작 화면 — 버튼 이벤트 계약 · 버튼 상태 그림(올림 · 누름 · 선택 · 비활성) · 반복 칸(하위 WBP) · 메뉴 프로필 · 긴 글자 처리 · 승격 경로 추가. 첫 대상 = 허브 준비 화면(추천 — 착수 때 확인) + 글 → 컨셉 → run 을 한 명령으로 | 첫 화면 무인 1회 통과 · 게임에서 조작 동작(잠정) | 실제 run · 사람 눈 · 조작감 |
| ~~5~~ | ComfyUI 연결 — **삭제(11-24 조정)** | — | — |
| ~~6~~ | 지표 기반 라우팅 — **삭제(11-24 조정)** | — | — |

**Phase 조정 (2026-11-24 사용자 승인 — 번호는 그대로 두고 순서만 2 → 4 → 3)**

Phase 1 은 끝났다(1a · 1b · 마감 회귀 · M4 C 연결). 남은 표는 11-14 에 L-2 전환 전의 방식을 전제로 세운 것이라 코드 · 실행 기록 · 게임 계획과 다시 대조했다. 읽고 센 것이고 새로 돌린 시험은 없다. 각 Phase 의 자세한 설계 · 질문은 착수할 때 쓴다.

| Phase | 판단 | 근거 |
| :--- | :--- | :--- |
| 근사 다듬기 | 삭제 | 대상이던 파티 HP 숫자 폭은 시험용 외부 컨셉(L-1 — 동결)이다. 승격본에 남은 근사(CombatHUD `194019` 3 · StatusHUD `130129` 4)는 오류가 아니고 눈 확인을 통과했다. 새 화면은 참고판을 글꼴로 그려 크기 · 굵기 · 색이 단일 원천이다('메인 HUD 결과') |
| 2 | 축소 | ① 보정하려던 스타일 유사도는 한 번도 재지 않았다 — `metrics/uigen.jsonl` 에셋 1,424 줄 중 `style_sim_anchor` 값 0 개 ② 영역 ΔE 를 게이트로 올리는 일은 1b 후속 J 의 외형 게이트(국소 ΔE) + 정답 묶음 + `regress_set` 이 맡고 있다 ③ 보정 세트의 옵션 화면은 게임 계획에 없고, 시스템이 없는 화면을 가짜 값으로 만들지 않는다('메인 HUD 설계' 원칙). 문턱은 새 종류의 화면이 실제로 올 때 그 화면으로 다시 본다 |
| 2 — 외형 검토 라운드 | 끄기 | 11-18 이후 남은 report 41 개의 라운드 = 지적 없음 29 · 되돌림 10 · **받아들임 2**(LLM 약 8.8 USD). 글자는 결정적 맞춤이, 픽셀은 오리기가 맡은 뒤로 라운드가 더하는 것이 거의 없다 |
| 2 — verify 시간 | 줄이기 | 최근 최종 run 셋에서 verify 가 72 %(`172628` · 658 초) · 87 %(`194019` · 1,818 초) · 78 %(`130129` · 842 초). 후보 = 안 겹치는 막대의 같은 비율을 한 렌더로('메인 HUD 결과' 남긴 것 ②) |
| 4 | 3 보다 먼저 · 나눔 | 승인된 화면을 조금만 고쳐도 analyze(LLM)부터 다시 돌아 눈 확인이 끝난 칸까지 흔들린다(StatusHUD 를 따로 나눈 까닭 — '메인 HUD 설계' 결정 2). `promote_widget` 은 대상이 있으면 거절하므로 재승격마다 옛 애셋을 손으로 휴지통에 보낸다. lineage 는 쓰지만 `parent_run_id` 는 늘 null. 조작 화면은 요소가 많아 고치는 횟수가 더 많다. 승격 최소판(`promote_widget`)은 이미 있다 |
| 3 | 범위 변경 | ① 글 → 그림은 `make_concept`(L-2 기본 · `--style-ref` · 후보는 사람이 고름)가 한다 → text 모드는 한 명령으로 묶기만, 목업 K 장 자동 선택 · multi_ref 의 나머지 역할(layout · component · mood)은 뺀다 ② 빠진 것은 조작 화면이다 — inputs 데이터 종류에 동작이 없고(text · number · progress · flag · image), 프로필은 `hud.yaml` 하나, `WidgetPromotionPaths` 는 `/Game/UI/HUD/` 하나, spec Button 에 올림 · 누름 브러시는 있으나 그 그림을 받는 길이 없다 ③ Slider · CheckBox · ComboBox 는 쓸 화면이 없어 뺀다. ListView · ScrollBox 는 대형 인벤토리(후순위)가 들어올 때 |
| 5 | 삭제 | 11-17 부터 run 안에서 codex 로 만든 에셋이 **0 개**다(concept_cut · concept_plate · procedural 뿐 — codex 는 컨셉 만들기 · 컨셉 변환에만) — A/B 할 대상이 없다. V8 `extract.text_fill_complex` 는 자리만 있고 none 그대로. **다시 여는 조건:** M7 에서 스킬 · 룬 아이콘이 수십 개 필요하고 codex 로 감당이 안 될 때 |
| 6 | 삭제 | 고를 백엔드가 없다(5 와 같은 이유) |

- **Phase 3 의 첫 대상 — 허브 준비 화면(추천):** 값의 원천이 이미 있다 — `AAstralPlayerState::bIsReady` · `AAstralHubGameState::SelectedRaid` 복제(둘 다 RepNotify 없음 — 통지를 더해야 한다), 요청은 `ServerSetReady` · `ServerSelectRaid`. 지금은 콘솔 명령으로만 조작한다. 그 뒤 M6 결과 화면 · M7 로드아웃 · 룬 · 성장 트리.
- **Phase 3 의 가장 큰 위험:** 지금 방식은 컨셉 한 장의 픽셀이 정답이라 버튼 상태별 그림이 없다. 상태 그림을 받는 법을 작게 먼저 시험한다. 게임패드 초점 · 입력 모드 · CommonUI 를 쓸지도 정해지지 않았다(지금 모듈은 UMG · Slate 만).
- **지난 기록 읽는 법:** 아래 기록의 'Phase 2 보정 세트에서 다시 본다'(OCR 기준 0.7 · 장식선 판정 · A8 등)는 '새 종류의 화면이 실제로 올 때 다시 본다'로, 'Phase 5'(ComfyUI)는 '삭제 · 다시 여는 조건'으로, 'Phase 2 전 남은 단계'는 '없음'으로 읽는다. 기록은 그때 글이라 고치지 않았다.
- **M5 보스 HUD 는 Phase 에 넣지 않는다:** 막대 · 켜고 끄기 · 글자라 지금 기능으로 될 것으로 본다(안 돌려 봄). 시안 `hud_blade_sheet` 의 보스 칸을 M5 에서 값이 생길 때 오린다.

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
  | 4 `R20261115_190401` | 3 | **받음** | 배너 높이 비 0.898 → 1.02 · '오의 불가' 0.946 → 1.0 · 배너 프레임 다시 따옴(G 에서 정정 — `patches/style_001.json` 은 `burst_banner_frame` 교체). 단 옛 지표(1.65)에 속아 '4.2' 56 → 64 → fill 상자라 아래로만 커져 '2/4' 에 닿음 → 위로 옮김(`_shift_up_fixed_text`) |
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

**1b 후속 G 에서 확인 · 정한 것 (11-15, 미커밋 — F 사람 눈 판정의 남은 차이 셋: 배너 위아래 빛 · 체인 패널 모서리 · 글자 위치 + run 간 흔들림. 사용자: 하위 단계 없이, 범위 ①②③ 승인 · 흔들림은 결정적 단계로 흡수(추가 비용 없음), C++ · Config 변경 없음)**

착수 때 정한 것(조사 · 시제품 뒤 제안 그대로 승인): ① 따온 frame · panel_bg 에 컨셉 픽셀 옮겨 심기 ② 외형 라운드 다시 따오기의 충실도 기준 + 모서리 지표 ③ 글자 위치 결정적 맞춤. 흔들림은 ① · ③ 이 codex · analyze 몫을 덜어내는 것으로 다룬다(여러 판 뽑아 고르기 · 지난 run 재사용은 하지 않음).

- **원인 확인 [실측 F run 4]:**
  - **배너 '위아래 빛' = 테두리 안쪽 빛:** 컨셉 안쪽 줄 단면(글자 없는 열)은 위 L 29.6 → 가운데 24 → 아래 30.1, 가운데 열(x 900 ~ 1020) 위 안쪽 133 · 아래 안쪽 68 — 렌더는 18.9 한 값(`interior_flatten`). 바깥은 금테 밖 어두운 테(L 13 ~ 15)뿐이다: 위 가운데 바깥 73 ~ 83 은 뒤 하늘(행마다 평평), inpaint 배경 대비 바깥 띠 밝기 초과는 d 1 ~ 6 px 음수(−8 ~ −22) · d 8 ~ 14 p90 +3 ~ +8 → **바깥 빛은 굽지 않았다**(인계 메모의 '바탕 23' 은 안쪽 값과 비교한 것).
  - **run 4 배너 금테가 노란 이유 = 외형 라운드의 다시 따오기:** 처음 판 장식선 F1 0.983 · 선 ΔE00 7.92 → 다시 따온 판(프롬프트 'light, warm, slightly glowing') 0.914 · 14.56 인데 게이트만 보고 받았다.
  - **체인 패널 모서리:** codex 가 모서리 장식을 작게 다시 그렸다(오른쪽 아래는 거의 없음). 영역 장식선 F1 은 0.98 — 테두리 띠 전체 F1(±2 px)은 긴 직선이 지배해 모서리를 못 가른다.
  - **글자:** 배너 라벨은 왼쪽 끝이 같고(789) 폭만 좁다(254 vs 275 · 높이 비 1.02) — dx −10.5 는 글자 사이 틈 · 정렬 몫, dy −4.5 는 세로 자리. 외형 비교(region_report)의 패널 폭 상자('체인' · '4.2' · '2/4')는 모서리 장식 · 테두리선이 획에 섞여 제대로 못 쟀다('4.2' 는 제대로 재면 13.5 px 낮았다 — F 의 `_shift_up_fixed_text` 전 run).
- **구현 — 컨셉 픽셀 옮겨 심기(Python):** `gen/concept_pixels.py`(새) `transplant` — codex 결과는 **실루엣(알파)만**, 색은 컨셉 픽셀. 정합(위젯 해상도 장식선 F1 허용 1 px 최대인 ±6 px 이동, F1 0.01 안 동점은 허용 없는 겹침 IoU) → 실루엣(컨셉 장식선 채운 모양이 위젯 상자의 0.97 이상 = **사각 패널 → 상자 그대로**(codex 무관 — [실측] 체인 패널 0.995 ~ 0.999 · 배너 0.74 · 게이지 0.79), 아니면 codex 실루엣 · 컨셉 모양 IoU < 0.85 면 물러남) → 글자 구멍(상자 +6 안 획 + 바탕과 L 6 넘게 다른 둘레 6 px, 6 + 1.5 × 빛 크기 넓힘 — **테두리에 이어진 장식선 덩어리 · 테두리 띠에 닿는 획 덩어리는 뺀다**, 자식 Image 상자도 구멍) → 줄마다 좌우 보간 → 합치기(텍스처 해상도: 안쪽 = `interior_alpha`, 컨셉 장식선 알파 1(codex 실루엣 3 px 안), 실루엣 가장 바깥 1 px 의 비장식선 · 바깥은 codex 색). `stages/refine.py` — `extract.concept_pixels`(기본 켬)면 안쪽 한 색 대신 이것. 게이지(ProgressBar 가 겹친 프레임)는 건너뛴다(컨셉은 채움 한 상태라 프레임에 채움 빛이 구워진다), 옮긴 뒤 OCR 자국이면 한 색으로 물러남, 9-slice margin 은 한 색 판에서 잰다. 기록 `refine.json concept_pixels`.
- **구현 — 지표 · 교체 기준:** `fidelity.corner_f1`(모양 상자 네 모서리 정사각(짧은 변 22 %)마다 장식선 F1 허용 1 px — 기록만) · `glyph_exclusion`(모서리 지표만 글자 위젯 상자 통째가 아니라 획 둘레를 뺀다 — 기존 장식선 F1 · ΔE00 값은 그대로) · 요약 `text_center_err_px` · `region_corner_f1`. `style.replace_guard` — 라운드가 다시 따온 에셋의 충실도 점수(실루엣 IoU · 장식선 F1 · 모서리 F1 최소 중 가장 낮은 것)가 라운드 전 − `style_review.replace_guard_tol`(0.02)보다 낮으면 **그 에셋만** 옛 것으로(사본 final · raw · compare · manifest 항목, 라운드의 다른 op 는 그대로). `prompts/style_verifier.md` — 글자 위치 · 자간 · 따온 프레임의 색 · 장식은 결정적 단계 몫이라 op 를 내지 말 것, replace_asset 은 바깥 모양이 틀렸을 때만.
- **구현 — 글자 위치(`style.text_fit` + `run_pipeline._text_fit_round`):** 외형 라운드 뒤(받든 버리든 · deterministic 모드에서도 — `style_review.text_fit`) 마지막 통과 렌더에서 글자마다 컨셉 ↔ 렌더 획 상자를 같은 측정 상자(컨셉 획 상자 + 획 높이 × 0.3, 그 영역 안)에서 잰다: 영역 테두리에 이어진 장식선 덩어리는 획에서 빼고(`_frame_drop`), analyze 상자가 글자보다 짧으면 컨셉 획을 가로로 0.5 · 1.0 · 1.5 × 높이 넓혀 원래 획을 품는 큰 것을 받고(이웃 글자 상자 앞까지 · 세로로는 안 넓힘 — '2/4' 위 '4.2' 를 잡음), 렌더 획이 측정 상자 끝에 닿으면 그쪽만 넓혀 다시(2번). 높이 비 0.88 ~ 1.12 일 때만 ① 자간 = 글자 사이 틈(획 상자 안 세로 투영의 빈 열) 차이 ÷ (글자 수 − 1) — 글자 모양이 넓어서 생긴 폭 차이는 메우지 않는다 ② 중심 차 2 px ~ min(40, 0.8 × 획 높이)면 슬롯 padding 양쪽 ±(가운데 정렬 축은 ±d/2) · 캔버스 점 앵커 위치(bbox_intent 같이). build → verify 1회, 깨지면 외형 라운드처럼 버린다. 받은 뒤 같은 측정으로 남은 차를 기록(`style_review.text_fit.residual`).
  - **[소스] `SlateCore/Public/Layout/LayoutUtils.h:663-664 · 1112-1117`:** 상자 · 오버레이 슬롯 모두 `AlignChild` — 가운데 = (할당 − 자식)/2 + **앞 여백 − 뒤 여백**(양쪽 ±k 는 2k 움직임), 왼 · 위 · 채움 = 앞 여백, 오른 · 아래 = 할당 − 자식 − 뒤 여백. F 의 `follow_text_boxes` · `_glow_layout` 은 대칭 변화라 맞다.
- **끝 run 4번(전부 옵션 없음 · 같은 컨셉 · 무인 통과) [실측]** — 1 ~ 3 은 결함을 찾아 고친 run, 4 가 최종 코드:

  | run | 시도 | 외형 라운드 | 글자 맞춤 | 찾은 것 → 고침 |
  | :--- | :--- | :--- | :--- | :--- |
  | 1 `R20261115_224323` | 4 | 받음(크기 5) | 받음(5 글자) | 폭 차이를 자간으로 메워 '4.2' 가 '4 . 2' 로 벌어짐(자간 0 → 110 — 컨셉 숫자가 더 넓은 몫) → 자간 = 틈 열 차이만 · 측정에서 테두리 장식선 덩어리 빼기 |
  | 2 `R20261115_225312` | 5 | 받음(+ 체인 패널 replace — 교체 기준 kept_new, 상자 실루엣이라 0.9924 = 0.9924) | 받음(3) | 세로 가운데 '3' 을 ±3.5 로 옮기자 7 px(가운데 정렬 = 앞 − 뒤 여백) → 가운데 축 ±d/2. 체인 패널 오른쪽 테두리 y 214 ~ 235 끊김 — 테두리 가운데는 채도 낮은 연보라 선이라 '체인' 획으로 잡혀 메워짐 → 테두리 띠에 닿는 획 덩어리 빼기 |
  | 3 `R20261115_230508` | 4 | 받음 | 받음(3) — 배너 라벨 건너뜀 | analyze 라벨 상자 끝 1024 < 컨셉 '트' 1064 → 컨셉 획 상자부터 잘림(222 px — 잘린 조각은 `text_ink` 가 지움) + 실제 어긋남 30 px 가 측정 여유 밖 → 컨셉 획 가로 넓혀 재기 · 렌더 닿은 쪽 넓혀 재기 · 상한 40 px |
  | 4 `R20261115_231512` | 3 | 받음(7 op — 크기 · 그라데이션) | 받음(3 — 라벨 자간 200 → 79 · '3' (−5.5, −3.5) · '4.2' (2, −4)) | **최종 — 사람 눈 통과('오의 불가' 글꼴만)** |

  | 렌더 ↔ 컨셉(기록만) | F run 4 `R20261115_190401` | **G 끝 run 4 `R20261115_231512`** |
  | :--- | :--- | :--- |
  | 배너 안쪽 줄 밝기 L(옆 열 위 · 가운데 · 아래 / 가운데 열 위 안쪽) — 컨셉 29.6 · 24.1 · 30.1 / 133.1 | 18.9 · 18.9 · 18.9 / 18.9 | **25.5 · 21.8 · 26.8 / 133.5**(≈ 컨셉 × 0.9 — 안쪽 알파 0.9 를 검은 바탕에) |
  | 배너 장식선 대표색 ΔE00 · 장식선 F1 · 실루엣 IoU | 20.62 · 0.882 · 0.906 | **6.04** · 0.876 · 0.894 |
  | 체인 패널 모서리 장식선 F1(왼위 · 오른위 · 왼아래 · 오른아래) | 0.876 · 0.835 · 0.747 · **0.643**(G 지표로 다시 잼) | **1.0 · 0.997 · 0.997 · 1.0** |
  | 체인 패널 장식선 대표색 ΔE00 · 장식선 F1 | 4.45 · 0.980 | **1.83 · 1.0** |
  | 글자 중심 차 컨셉 − 렌더 px(글자 맞춤과 같은 측정 — 배너 라벨 · '3' · '4.2' · '오의 불가') | (10.5, 4.5) · (1.5, 2.5) · (2, −13.5) · (1.5, −3) | **(−1, −1.5) · (0.5, −0.5) · (0, 0) · (0.5, −1.5)** |
  | 외형 비교 요약: 글자 획 ΔE00 · 높이 비 오차 · 폭 비 오차 | 2.44 · 0.115 · 0.289 | **0.97 · 0.025 · 0.052** |
  | 게이지 채움 줄 단위 ΔE00 · 실루엣 IoU(F 그대로) | 0.51 · 0.931 | 0.51 · 0.930 |

  - '체인' · '2/4' 는 높이 비 0.85 · 1.17 이라 글자 맞춤이 건너뛰었다(크기는 외형 라운드 몫). 게이지 프레임은 옮겨 심지 않아 금테가 codex 그대로(선 ΔE00 5.5).
  - run 2 의 시도 1 baked_text 는 게이지 프레임 codex 판의 글자 자국(옮겨 심기 대상 아님 — 재생성 1회로 통과).
  - 비용(구독 — 과금 아님): LLM(API 정가 환산) run 1 ~ 4 = 0.878 · 0.863 · 0.767 · 0.477 USD, codex 3 · 5 · 3 · 3 = 14회(1b 부터 누적 69회, 한도 걸림 0).
- **시험:** pytest **273**(264 → +9: `tests/test_concept_pixels.py` 7 — 옮겨 심기(모서리 · 테두리 색 · 안쪽 빛 · 글자 메움 · 알파) · 연보라 테두리 조각 · 정합 · 실루엣 거부 · 사각 패널 · 게이지 건너뜀 · 모서리 F1 · 교체 기준 · 글자 맞춤(자간 · 가운데 축 · 캔버스 · 닿음 · 모양 폭 · 잘린 상자) / `tests/test_style.py` +2 — 글자 맞춤 받기 · 버리기(가짜 에디터) / `tests/test_extract.py` 1 수정 — 안쪽 단계 기록 → 옮겨 심기 기록).
- **G 끝 회귀(필수만, 11-15) [실측]:** C++ 변경이 없어 빌드 없음. 끝 run 뒤 에디터를 내리고(버린 0 · 소멸 확인) 새 에디터 1회(DebugGame): `AstralBreak.` **55/55**(시험 시간 합 389초) → `EditorMcpCore.` 2/2 → `WidgetMcp.` 6/6 → `quit_editor`(버린 것 = `WidgetMcp.Spike` 시험 WBP 1개) · 소멸 확인. pytest **273**.
- **사람 눈 확인(11-15, 사용자 — 비교 그림 3장, 줄마다 컨셉 · F run 4 · G):** **'오의 불가' 글꼴만 약간 다르고 나머지는 통과.** [실측] 렌더 획이 더 굵다 — 획 굵기 약 4.6 vs 3.8 px · 획 픽셀 1.45 배(색 · 크기 · 높이 비 1.03 은 같음). Pretendard 는 Regular · Bold 만 임포트돼 사이 굵기가 없다 → 뒤로 넘김.
- **증거 정리(11-15 사용자 승인 — 휴지통):** 끝 run 4 `R20261115_231512`(최종 코드 · 사람 눈 판정 대상 — work 의 `assets/compare/hud_concept_run4_G.png` · `chain_corners_concept_run4_G.png` · `text_zoom_concept_run4_G.png` 는 줄마다 컨셉 · F run 4 · G)의 work · `Content/_AutoGen/` 을 남겼다(11-17 사용자 승인으로 이것도 휴지통 — 숫자는 위 표로만 남는다). 끝 run 1 ~ 3 의 work(55 MB) · `Content/_AutoGen/`(1.8 MB) · 스크래치(조사 · 시제품 · 비교 스크립트와 그림, 1.8 MB)는 휴지통 — run 1 ~ 3 숫자는 위 표로만 남는다. F 의 run 4 · 5 는 그대로.
- **G 후속 — 굵기 · 크기 · 상자 안 이동(11-16, 미커밋 · 사람 눈: 글자 통과 — 사용자: 여기서 이어서, '굵기만 결정적으로' → '크기도 결정적으로' 승인):**
  - [실측] 컨셉 '오의 불가' 획 밀도(획 픽셀 / 획 상자 넓이) 0.254 · 획 굵기 3.82 px = PIL Pretendard Regular 0.237 · 3.82, 지금 렌더(Slate Bold) 0.360 · 4.65 = PIL Bold 0.361 · 4.65(PIL 이 Slate 렌더와 같음 — 보정 확인). Bold/Regular 밀도 비는 Pretendard 1.52 · Noto Serif KR 1.49 → 경계 1.22(기하 중간). 여섯 글자 중 Pretendard Bold '오의 불가' 만 컨셉/렌더 비 0.71 ~ 0.74, 나머지 1.00 ~ 1.22. analyze 의 글꼴 역할도 run 마다 다르다(F run 4 = Noto · G run 4 = Pretendard — 기록만).
  - `style.text_fit` ③ 굵기: 컨셉/렌더 밀도 비 < 1/1.22 이면 bold → regular, regular 인데 > 1.22 면 bold(높이 비 0.75 ~ 1.33 에서 판정 · 바꾼 글자는 그 판에서 자간 안 건드림), 잔여 기록에 `ink_density`, `prompts/style_verifier.md` 에 굵기도 결정적 몫.
  - `style._take_from_neighbour`: [실측 run `R20261115_234443`] 채움 칸 배너 라벨을 자기 padding ±5 로 옮기자 칸을 넘어 옆 Spacer(`BurstGap`)와 겹쳐 overlap 게이트 → 글자 맞춤 통째로 버려짐. 가로 · 세로 상자 **주축** 이동은 이동 방향 이웃에서 |d| 를 가져와(Spacer 크기 · bbox_intent, 아니면 이웃의 맞닿은 padding — 이웃 주축 가운데 정렬은 제외) 자기 반대쪽 여백에 더한다. 이동 방향에 형제가 없으면 양쪽 ±, 여유가 없거나 자기 주축이 가운데 정렬이면 그 축은 안 옮김.
  - 끝 run `R20261115_235354` pass(시도 5): '오의 불가' Pretendard Bold → Regular(밀도 0.232 ↔ 컨셉 0.254), 배너 라벨 +16.5 px 는 '3' 의 앞 여백에서 가져옴, 글자 맞춤 받음. **단 이 run 은 LLM 외형 라운드가 overlap 으로 버려져 analyze 의 작은 글자 크기가 그대로**(높이 비 배너 0.90 · '4.2' 0.80 · '오의 불가' 0.81) — 굵기와 무관한 run 간 흔들림. 사용자 눈: 가운데(G 끝 run 4 — 라운드가 크기를 고친 run)가 가장 잘 맞음 → 목표 = 'G 끝 run 4 + 오의 불가 Regular' 가 매번 나오게. pytest 274(+1 `test_shift_text_along_a_box_takes_room_from_the_neighbour`, 글자 맞춤 시험에 굵기 검사).
  - **크기 — 크기 판 → 위치 판(11-16 설계 승인, 하위 세션):** 목표 = 'G 끝 run 4 + 오의 불가 Regular' 가 외형 라운드를 받든 버리든 매번. `style.text_fit(mode)` 를 두 판으로 나눠 `run_pipeline._text_fit_round` 가 판마다 build → verify(약 6초) — 통과면 받고 깨지면 **그 판만** 버린다(한 판에 섞으면 크기 탓 overlap 에 위치 맞춤까지 버려지고, 다시 돌려도 같은 크기를 내 같은 이유로 버려진다 — '2회 반복안' 대신 고른 이유).
    - **크기 판**(`mode="size"`): 높이 비 0.75 ~ 1.33(`TEXT_FIT_WEIGHT_H` — 밖은 측정 오류로 봄 · [실측 235354] '2/4' 0.38 = 획이 패널 밖으로 잘림)일 때만, |1 − 높이 비| ≥ 0.04(`TEXT_FIT_SIZE_TOL`)면 새 크기 = round(크기 ÷ 높이 비)(빛 · 외곽선 그대로), 상자는 `follow_text_boxes` 가 가운데 중심으로 키운다. 굵기 판정도 이 판으로 옮김. **build 전 형제 겹침 예측**(`_fit_sizes`): 직전 통과 렌더 geometry 에 커질 상자(grow · shift_up)를 넣어 overlap 게이트와 같은 규칙(profile 의 overlap_max_ratio · stacking_parents · allow_overlap)으로 재 새로 겹치는 쌍이 있으면 키운 글자를 1 씩 원래 쪽으로(`size_capped`), 줄 높이 표가 없는 폰트는 크기를 되돌린다. [실측 235354 오프라인] 라운드가 버려진 그 run 의 VerticalBox 체인 패널은 '체인' 22 그대로 · '4.2' 52 → 53 에서 멈춤(라운드는 65 로 키워 0.29 · 0.48 겹침), 배너 34 → 38 · '3' 56 → 61 · '오의 불가' 26 → 32 + Regular. G 끝 run 4 데이터로는 '체인' 21 → 25 · '2/4' 26 → 22 · '오의 불가' Regular.
    - **위치 판**(`mode="place"` — 최신 통과 렌더에서 다시 잼): 예전 자간 · 중심(높이 비 0.88 ~ 1.12, 굵기는 빠짐).
    - `prompts/style_verifier.md`: 크기도 결정적 몫(`font.size` op 를 내지 말 것) — 가드는 막지 않음(내도 크기 판이 다시 맞춤).
  - **1차 끝 run `R20261116_092237` pass(시도 5 — 라운드 받음 · 크기 판 6 글자 받음 · 위치 판 받음) — 결함 둘 → 고침:** 배너 라벨(채움 칸 · 왼쪽 정렬)의 중심 차 25 px 가 남았다. ① 크기 판이 가운데 중심으로 키우자 왼쪽 끝이 17 px 나가 위치 판 측정 상자(여유 15 px) 끝에 '체' 가 걸쳤는데, `text_ink` 는 좌우 끝에 닿은 덩어리를 지우므로(모서리 장식 빼기) '체' 가 그냥 사라져 '닿음'으로도 안 보였다(렌더 폭 225 — 실제 약 257) → `_cut_sides`: 끝 덩어리를 지우기 전 획(`fidelity.text_ink(drop_edges=False)`)으로 걸침을 보고 그쪽을 넓혀 다시(다른 글자 상자 앞까지 — `_stop_at_others`, `_concept_ink` 와 공용). ② 주축 이동이 이웃 규칙에 막힘('3' 의 앞 여백이 크기 판 뒤 −4) — 라벨 칸 안 오른쪽엔 약 50 px 빈자리 → 위치 판도 같은 겹침 예측으로, 새로 겹치지 않으면 **자기 양쪽 padding**(`_shift_text(own_main=True)` — 여백 합이 그대로라 auto · 채움 칸 모두 칸 자리는 그대로이고 위젯만 d, [소스] `LayoutUtils.h:642-670` AlignChild), 겹치면 예전 이웃 규칙. 시도 4 렌더로 오프라인 재측정: 렌더 획 771 ~ 1014 · +34 자기 padding.
  - **끝 run 2번(전부 옵션 없음 · 같은 컨셉 · 무인 통과) [실측]:**

    | run | 시도 | 외형 라운드 | 크기 판 | 위치 판 | 결과 |
    | :--- | :--- | :--- | :--- | :--- | :--- |
    | 1 `R20261116_092237` | 5 | 받음(2 op) | 받음(6 — 배너 32 → 37 · '3' 52 → 62 · '체인' 22 → 25 · '4.2' 58 → 65 · '2/4' 26 → 23 + bold · '오의 불가' 26 → 31 + Regular) | 받음 — 배너 라벨 가로 건너뜀 | 결함 둘(위) → 고침 |
    | 2 `R20261116_093639` | 4 | 받음(4 op · 배너 프레임 다시 따옴 — 교체 기준 kept_new) | 받음(4 — '3' 56 → 61 · '체인' 22 → 25 · '2/4' 26 → 22 · '오의 불가' Regular) | 받음(5 — 배너 라벨 자간 200 → 79 · '3' (−5.5, −8.5) 자기 padding) | **최종 — 사람 눈: 글자 통과** |

    | run 2 글자(같은 측정 — `text_fit.residual`) | 배너 라벨 | '3' | '체인' | '4.2' | '2/4' | '오의 불가' |
    | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
    | 높이 비(크기 판 전 → 끝) | 1.02 → 1.02 | 0.92 → 0.98 | 0.88 → 1.00 | 0.97 → 0.97 | 1.17 → 0.97 | 0.97 → 0.95 |
    | 남은 중심 차 px | (−1, 0.5) | (0.5, −0.5) | (0.5, 0) | (0, 0) | (0.5, 0.5) | (1, 0) |

    - 외형 비교 요약(region_report — 기록만): 글자 높이 비 오차 0.079 → 크기 판 뒤 0.026. 위치 판 뒤 폭 비 오차 0.40 · 중심 차 11.2 px 는 '체인' 한 글자 탓 — 패널 폭 상자를 2 px 올리자 그 측정 상자 맨 위가 금테에 닿아 획 상자 181 px(폭 비 2.9)로 잡힘(G 뒤로 ⑤ 의 흔들림 — 글자 맞춤 측정으로는 (0.5, 0) · 높이 비 1.00).
    - '오의 불가' 는 Regular 로 바뀌며 높이가 약 3 % 낮아진다(0.973 → 0.946 — 굵기와 크기가 같은 판이라 다시 안 맞춤, 허용 4 % 안).
    - 비용(구독 — 과금 아님): LLM(API 정가 환산) run 1 · 2 = 0.895 · 0.471 USD, codex 3 · 5 = 8회.
  - **사람 눈 확인(11-16, 사용자 — 비교 그림 2장, 줄마다 컨셉 · G 끝 run 4 · run 2):** 글자는 통과. '오의 불가' 글꼴은 컨셉과 다르지만 비슷한 폰트가 없는 문제(임포트 폰트 = Pretendard · Noto Serif KR). **게이지 테두리 · 빛은 G 끝 run 4 가 낫다** — [실측] 글자와 무관한 analyze 흔들림: G 끝 run 4 는 `UltReadyGlow`(오의 준비 빛, flag)를 procedural(828×66) · 게이지 프레임을 9-slice 상자로, run 2 는 빛을 codex(2172×724) · `UltFrame` 을 크기 고정 image 로 골랐다(렌더는 force_visible 이라 꺼진 빛도 보임).
  - **시험:** pytest **278**(274 → +4: `tests/test_concept_pixels.py` +2 — 크기 판(높이 비 · 가운데 성장 · Overlay 는 그대로 · VerticalBox 는 겹침 예측으로 25 에서 멈춤 · geometry 없으면 예측 없음 · 0.75 밖 건너뜀) · 주축 자기 padding(겹침 예측 있으면 이웃 규칙), 기존 글자 맞춤 시험에 걸친 획 다시 재기 · 굵기는 크기 판 / `tests/test_style.py` +2 — 크기 판이 깨져 버려져도 위치 판은 돎 · 두 판 모두 받음). C++ · Config 변경 없음 → 빌드 없음, 에디터 회귀는 G 에서 했고 Python 만 바뀌어 생략. 끝 run 마다 에디터 `quit_editor`(버린 것 0) · 소멸 확인.
  - **증거 정리(11-16 사용자 승인 — 휴지통):** 끝 run 2 `R20261116_093639`(최종 · 사람 눈 판정 대상 — work 의 `assets/compare/hud_concept_G_size.png` · `text_zoom_concept_G_size.png` 는 줄마다 컨셉 · G 끝 run 4 · run 2)와 G 끝 run 4 `R20261115_231512`(11-17 휴지통)의 work · `Content/_AutoGen/` 을 남겼다. 굵기 단계 run `R20261115_234443` · `R20261115_235354` 와 크기 1차 run `R20261116_092237` 의 work(54 MB) · `Content/_AutoGen/`(1.5 MB), 스크래치 `uigenG2` · `uigenG3` 는 휴지통 — 그 숫자는 위 글로만 남는다.
  - **G 후속 뒤로 넘길 것:** ① 게이지 테두리 · 준비 빛의 run 간 흔들림(analyze 가 `UltReadyGlow` 원천을 procedural ↔ codex, 게이지 프레임을 상자 ↔ image 로 고름) — 결정적 규칙 또는 게이지 프레임 옮겨 심기(G 뒤로 ③)와 같이. ② 체인 패널을 VerticalBox 로 짠 run 은 줄 상자가 꽉 차 크기 판이 성장을 막는다 — analyze 배치 몫(B 뒤 컨셉 run 9개 중 1개 — 나머지는 Overlay). ③ 컨셉 글꼴과 비슷한 폰트가 없으면 높이만 맞고 폭 · 모양은 남는다('4.2' 폭 비 0.88 · '오의 불가' 0.94) — 폰트 임포트(내려받기 승인). ④ 기준값(크기 4 % · 측정 0.75 ~ 1.33 · 굵기 1.22)과 측정 가정(한 줄 · 바탕과 대비)은 이 컨셉 하나에서 — 다른 컨셉 시험 입력으로 재야 보편성을 말할 수 있다.
- **G 뒤로 넘길 것:** ① '오의 불가' 굵기 — Pretendard SemiBold 등 사이 굵기 임포트(내려받기 승인 필요) 또는 컨셉 획 굵기로 weight 를 결정적으로 고르기 → **G 후속에서 결정적 선택(regular ↔ bold)으로 처리(위)**. ② 배너 끝(뾰족 캡) 곡선 자리는 codex 실루엣 몫(모서리 F1 오른아래 0.31 그대로 — 눈 지적 없음). 사각 패널이 아닌 프레임은 codex 실루엣에 기대므로 그 변동은 남는다(IoU < 0.85 면 한 색으로 물러남). ③ 게이지 프레임은 옮겨 심지 않는다(채움 상태가 구워짐) — 채움 자리만 빼고 옮겨 심는 길. ④ 글자 크기가 외형 라운드에서 안 맞으면(높이 비 밖) 글자 맞춤이 건너뛴다 — F 뒤로 넘길 것 ② 의 결정적 크기 맞추기와 같이 → **G 후속의 크기 판으로 처리(위)**. ⑤ region_report 의 글자 지표는 예전 방식 그대로(패널 폭 상자는 흔들림) — 믿을 값은 글자 맞춤의 측정(`text_fit.residual`). ⑥ 외형 라운드가 사각 패널을 replace 하면 codex 호출만 쓰고 결과는 같다(run 2) — 가드에서 막을지.

**1b 후속 G2 에서 확인 · 정한 것 (11-16, 미커밋 — 사용자: G 후속 사람 눈에서 '게이지 테두리 · 빛은 G 끝 run 4 가 낫다' + 새 컨셉 2장(파티 HUD · 조작 안내 — 상용 게임 화면)으로 개선 · 보편화 검증, 추천안 승인, C++ · Config 변경 없음)**

- **게이지(지적 부분):** ① 숨은 빛 — `analyze.derive_hidden_glows`: flag 시작값 false 인 이미지의 빛(codex generate + 빛 낱말, 또는 LLM 의 procedural soft_glow)을 procedural soft_glow(falloff 0.6 · 그 자리 컨셉의 밝고 채도 높은 색 + 알파 CC — G 끝 run 4 값)로 맞춘다 [실측 — 컨셉 run 9 번 중 8 번 LLM procedural 0.6, 1 번 codex 캡슐 후광 · 한 번은 알파 1.0 으로 번짐 진함]. ② 게이지 프레임 옮겨 심기 — 채움이 `concept_fill` 이면 `concept_fill.unfilled_track` 이 트랙 전체(줄 top ~ bot × 열 left ~ right)를 줄마다 빈 트랙 맨 오른쪽 60 px 중앙값으로 칠하고(구역 밖까지 이어진 밝은 덩어리 = 프레임 선 · 캡만 남김), 그 컨셉으로 G 의 옮겨 심기를 돈다 — 채움 끝 + 번짐까지만 메우자 그 뒤 옅은 빛과 단이 졌고(렌더 x 1171), 컨셉 75 % 자리 빛이 진행률과 무관하게 남는 유령 빛 문제도 같이 없앰. 숨은 이미지 · 프레임 넓이 절반 넘는 이미지(뒤에 깔린 빛)는 빼는 상자에서 제외(안 그러면 프레임 전체가 구멍).
- **보편화 검증 — 검증 화면 모드:** `screens.yaml probe: true`(ProbePartyHUD · ProbeControlGuide) — codegen `_probe`(C++ 안 씀 · reason `probe` · 스키마 enum), build 부모 `/Script/UMG.UserWidget`, verify `gate_bindings_probe`(WBP 트리의 계약 위젯 이름 · 타입), normalize 계약 class `UUserWidget`/existing. 입력은 git 무시 `Tools/uigen/work/_probe/{party,controls}/`(webp → png, 1920×1080 가운데 맞춤 — 1.8 · 2.4 배로 커짐), 초상화는 런타임 이미지 바인딩(캐릭터 그림을 따오지 않음).
- **새 컨셉이 드러낸 일반 결함 → 고침(모두 위젯 이름 · 좌표에 기대지 않음):**

  | 결함 [실측 run] | 고침 |
  | :--- | :--- |
  | 여러 위젯이 쓰는 에셋(파티원 슬롯 3개)을 첫 위젯 상자로 되자르다 codex 입력 영역 밖이라 상자가 뒤집힘(refine 오류, 파티 1차) | `refine.extract_target_box` = 입력 영역과 가장 많이 겹치는 위젯 |
  | 컨셉에 그려진 마우스 · 스페이스 아이콘을 OCR 이 0.72 ~ 0.75 로 글자로 잡아 재생성 3 번 뒤 baked_text 실패(조작 1차) | `refine._split_marks` — 따온 에셋은 검출 상자를 컨셉 좌표로 옮겨 글자 위젯 자리와 20 % 이상 겹치는 것만 구운 글자(나머지 `ocr_decor`), 옮겨 심기 물러남 판정도 같은 기준 |
  | 초상화 테두리를 따올 상자가 캐릭터 그림을 덮음 | 런타임 이미지(binding image)는 codex 입력에서 상자째 지우고(`generate._image_boxes`) 옮겨 심기에서 구멍 |
  | codex 입력에서 글자 줄 상자 전체를 지워 그 안으로 내려온 HP 프레임 윗선이 끊겨 codex 가 다르게 그림(렌더에 선 조각 2 개, 파티 3차) | `postprocess.reference_crop` — 글자는 획(`text_ink`) 3 px 둘레만 지움(획을 못 찾으면 상자 전체) |
  | '체인' 상자 46 px · 컨셉 글자 62 px 라 글자 구멍이 좁아 컨셉 획 조각이 체인 패널 텍스처에 남음(전투 2차) | `concept_pixels.text_holes` — 지우기 전 획이 상자 좌우에 걸치면 획 높이 × 0.5 씩 2 번 넓혀 다시(다른 글자 상자 앞까지) |
  | 캔버스 직계 '0 %' 를 위로 3.5 옮기자 옆 영역과 겹쳐(0.086) 위치 판 전체가 버려짐(파티 2차) | 위치 판 모든 이동에 겹침 예측 — 전체 → 한 축(`axis_dropped`) → 상자 주축만 이웃 규칙 → 아니면 안 옮김(`shift_skipped`) |
  | 작게 나온 '4.2'(높이 비 0.742 · 폭 0.674)를 측정 하한 0.75 가 막음(전투 1차) | 크기 판 신뢰 = 높이 비 0.6 ~ 1.6 + 폭 비 ÷ 높이 비 1 ± 0.3(잘린 '2/4' 0.379 · 1.70 은 걸러짐) — `TEXT_FIT_TRUST_*` |
  | 숨은 빛 · 게이지 트랙(위) | 위 |

- **끝 run(최종 코드 · 옵션 없음 · 무인 통과 — 외형 라운드 · 크기 판 · 위치 판 모두 받음) [실측]:**

  | 컨셉 | run | 시도 | 글자 남은 중심 차 · 높이 비(측정된 글자) | LLM(API 정가 환산) · codex |
  | :--- | :--- | :--- | :--- | :--- |
  | 전투 HUD | `R20261116_120451_CombatHUD` | 5 | ≤ 1.5 px · 0.98 ~ 1.03(6/6) — 게이지 테두리 · 트랙 · 빛이 G 끝 run 4 와 같음 | 0.756 USD · 3 |
  | 파티 HUD | `R20261116_121050_ProbePartyHUD` | 5 | 'Lv' · '100' · '0 %' ≤ 0.5 px(4/7 — '/44993' 15 px 는 붙은 '44993' 과 측정이 섞임) | 1.436 · 7 |
  | 조작 안내 | `R20261116_122100_ProbeControlGuide` | 4 | ≤ 3 px · 0.97 ~ 1.0(7/9 — T 키 · '어빌리티' 는 배지 · 띠와 섞여 측정 밖) | 0.564 · 7 |

  그 전 run 9 번(1 ~ 3 차, 결함 찾기)은 위 표의 결함 열로만 남는다. 누적 비용 — LLM 약 9 USD 환산 · codex 약 60 회(구독 — 과금 아님).
- **사람 눈(11-16, 사용자):** 게이지는 개선됨. 그러나 **새 컨셉 두 장은 컨셉 대비 매핑이 미흡** — 선이 끊기거나 테두리가 덜 깔끔하고, 특정 부분이 잘리고(띠 끝 장식 · 연결선), 가운데 문양 · 라벨 띠(돌진 공격 · 링크 어택 · 회피 · 어빌리티)의 장식 · 무늬가 빠져 단색 상자가 됨. 원인(run 기록): ① 따온 띠 안쪽을 한 색으로 칠함(`interior_flatten`) — 옮겨 심기는 실루엣 IoU 0.55 ~ 0.70 < 0.85 로 물러남 ② 텍스처를 위젯 상자로 되자름 — 상자 밖 장식이 잘림 ③ codex 는 다시 그리므로 얇은 선 · 빛 가장자리가 흐려지거나 끊김, 원본 807 px 를 2.4 배 키운 컨셉 자체도 흐림 ④ analyze 의 요소 나눔(E 키 배지 누락 · codex 에셋 상한 6) ⑤ 54 px 방패 배지는 codex 입력을 17 배 키워 흐리거나 빈 그림. **반투명 · 빛나는 UI 가 게임 장면 위에 합성된 스크린샷은 UI 와 장면을 갈라낼 수 없다** — 원래 전투 HUD 컨셉(불투명 패널 · 충분한 해상도)이 잘 맞은 이유. 사용자와 정리한 결론: 화면 짜기(LLM 배치 → MCP 로 WBP → 렌더 검증)는 맞는 골격이고, 바꿀 곳은 **에셋 확보 단계**(창작 = codex, 매핑 = 결정적) → 아래 H 설계.
- **시험:** pytest **283**(G 후속 278 → +5: `test_gauge` +2 — 트랙 메우기 · 숨은 빛 / `test_concept_pixels` +1 — 캔버스 이동 겹침 예측, 기존 시험에 숨은 · 큰 이미지 · 런타임 이미지 · 게이지 입력 · 걸친 획 넓히기 / `test_codegen` +1 — 검증 화면 / `test_refine_codex` +1 — 글자 획만 지우기). C++ · Config 변경 없음 → 빌드 없음, 에디터 회귀 생략(Python 만).
- **증거 정리(11-16 사용자 승인 — 휴지통):** G2 최종 세 run(`R20261116_120451_CombatHUD` · `121050_ProbePartyHUD` · `122100_ProbeControlGuide` — H 의 비교 기준, work 의 `assets/compare/regions_G2.png` · `overview_G2.png` = 컨셉 ↔ 렌더)과 G 끝 run 4 · G 후속 끝 run `R20261116_093639` 의 work · `Content/_AutoGen/`, 시험 입력 `work/_probe`, 비교 스크립트 스크래치 `uigenG4`(H 가 기준 run 과 대조할 때 씀 — H 끝에 정리)는 남겼다. G2 1 ~ 3 차 run 9 개의 work(230 MB) · `Content/_AutoGen/` 7 개는 휴지통.
- **G2 뒤로 넘길 것:** ① 에셋 확보 방식(H — 아래). ② 가득 · 빈 게이지(HP 1.0)는 `concept_fill` 측정 불가(0.15 ~ 0.9 만) → 평평한 막대. ③ 체인 패널 VerticalBox run(10 번 중 2 번)의 줄 상자 겹침 — 글리프는 안 겹치는데 줄 상자가 겹쳐 크기 · 위치가 막힘. 글자 형제끼리 줄 상자 겹침을 허용(allow_overlap)할지는 게이트 정책이라 사용자 결정. ④ 붙은 두 글자 위젯('44993' + '/44993')의 측정 섞임.

**1b 후속 H 설계 — 에셋 확보: 컨셉 픽셀 직접 오리기 (11-16 작성 · 사용자 승인 — 구현 · 검증은 새 세션)**

원칙: **창작은 codex, 매핑은 결정적.** 컨셉에 보이는 요소의 그림은 codex 로 다시 그리지 않고 컨셉 픽셀을 오려 쓴다(선 · 장식 · 무늬 그대로). codex 는 컨셉 이미지를 만들거나 바꿀 때(텍스트만 요청 · "컨셉을 ~식으로 바꿔 줘")와 컨셉에 없는 것(숨은 상태 · 가려진 자리)에만 쓴다. 세 경우 모두 '컨셉 이미지 한 장 → 결정적 매핑' 한 길로 모인다. 화면 짜기(analyze → spec → WidgetMcp build → 렌더 · 게이트 · 외형 라운드 · 글자 맞춤)는 그대로다.

- **입력 종류(normalize 가 판정 · inputs `concept_background: auto | flat | transparent | scene`):** ⓐ 투명 PNG(레이어 디자인 내보내기) — 알파 그대로(가장 좋음). ⓑ 단색 배경(codex 로 만든 컨셉 · UI 만 그린 컨셉) — 테두리 픽셀이 한 색이면 그 색을 키로 알파 = 배경색과의 거리, 빛 · 반투명은 배경색 언믹싱(색 = (P − (1 − α)K) / α). ⓒ 합성 스크린샷(장면 위 UI — G2 의 두 장) — 아래 오리기의 실루엣 추정 · 반투명은 실험. normalize 는 `reference.png`(RGB) 옆에 `reference_alpha.png`(ⓐ ⓑ) 와 판정 기록을 남긴다.
- **컨셉 생성 · 편집(make_concept 와 새 'concept edit'):** 프롬프트 = UI 만, 단색 배경(#000000 — 빛이 있으면 언믹싱이 쉬운 검정), 장면 없음, codex 최대 해상도(1b-2 실측 1672 × 941). 텍스트만 요청이면 에셋을 하나씩 그리지 않고 컨셉 한 장을 먼저(스타일 일관), 컨셉 바꾸기는 컨셉 전체를 codex 편집 → 새 컨셉으로 다시 매핑.
- **오리기 단계(refine 의 extract 경로를 바꿈):** 요소마다 (ref_bbox + 넘침 여유)에서 —
  1. 알파: ⓐ ⓑ = `reference_alpha`. ⓒ = OpenCV GrabCut(위젯 상자 초기화 + codex 실루엣을 '아마 전경' 시드로 — codex 는 실루엣 힌트로만) → 가장자리는 가이드 필터(numpy box filter 로 구현 — ximgproc 없음)로 부드러운 알파.
  2. 색: 컨셉 픽셀 그대로 — ⓑ 는 배경 언믹싱, ⓒ 는 실험: 요소 둘레 장면을 inpaint 로 이어 추정 배경 B 를 만들고 같은 식으로 언믹싱(지표가 나빠지면 불투명으로 굽고 '장면 섞임' 기록).
  3. 가려진 자리(글자 · 런타임 이미지 · 다른 위젯 위치): 지금의 줄 보간(결정적)이 기본, 둘레에 무늬가 있으면 그 자리만 codex inpaint(선택 · 호출 상한 안).
  4. 지금의 안쪽 한 색 칠하기(`interior_flatten`)와 'IoU < 0.85 면 물러남'은 오리기 경로에서 없앤다(원천이 컨셉 픽셀). codex 편집 따오기는 ⓒ 에서 GrabCut 이 실패할 때의 물러남으로만 남긴다.
  5. 작은 요소(짧은 변 < 64 px)는 codex 를 거치지 않는다(오리기가 유리 — G2 방패 배지).
- **넘침(overhang):** 실루엣이 위젯 상자 밖으로 이어지면(띠 끝 장식 · 연결선) 텍스처 상자 = 실루엣 상자. 그리는 법 후보 — (가) 같은 영역 Overlay 안 장식 Image 를 따로 둠(쌓기 부모라 겹침 게이트 밖) (나) 위젯 상자를 실루엣까지 키움(bbox_intent · 형제 겹침 영향). 구현 세션 첫 조사로 고르고 사용자에게 알린다.
- **analyze 쪽:** 오리기 에셋은 codex 호출이 없으므로 codex 에셋 상한(6)은 generate 에만. 프롬프트 — 원형 키 배지 · 아이콘은 따로 두고, 장식 요소의 위젯 상자는 장식 전체를 덮게. 반투명 그라데이션 띠는 텍스처(언믹싱 결과)로 먼저 — 부족하면 UI 머티리얼(그라데이션 + 무늬, WidgetMcp C++ — 먼저 묻기)을 다음 후보로.
- **검증(끝 조건):** 시험 입력 4 개 — 전투 HUD(지금 컨셉 · 회귀 기준 = G2 끝 run) · 새 단색 배경 컨셉 1 장(make_concept 새 프롬프트) · 파티 HUD · 조작 안내(`work/_probe`, 기준 = G2 끝 run). 지표 — 영역 렌더 ↔ 컨셉의 장식선 F1 · 모서리 F1 · 선 ΔE00 · 실루엣 IoU + 새로 선 연속성(장식선 끊김 수) · ⓒ 는 '추정 배경 위에 합성한 렌더 ↔ 컨셉' ΔE00. 기준 — 전투 HUD 회귀 없음, 파티 · 조작은 G2 대비 장식선 F1 · 선 ΔE00 개선 + 사람 눈(선 끊김 · 테두리 · 잘림 · 띠 장식). pytest, C++ 를 바꾸면 빌드 2 구성 + 에디터 회귀.
- **구현 세션이 시작 때 사용자에게 물을 것:** ① 설치 없이(OpenCV GrabCut · numpy 가이드 필터) 갈지, 분할 모델(SAM 계열 — onnxruntime 로 돌릴 모델 내려받기 승인)까지 쓸지 — 추천: 설치 없이 먼저 ② 넘침 그리는 법 (가) · (나) ③ ⓒ 반투명 언믹싱을 실험으로 넣을지 ④ 하위 단계 나눔(사용자 선호 — 잘게 나누지 않음).
- **환경 [실측 11-16]:** OpenCV 5.0(grabCut · inpaint 있음, ximgproc 없음) · numpy 2.5 · PIL 13 · onnxruntime(RapidOCR 용), scipy · scikit-image · torch · 분할 모델 없음.

**1b 후속 H 에서 확인 · 정한 것 (11-16, 미커밋 — 시작 질문 4개는 사용자가 전부 추천안: ① 설치 없이(OpenCV GrabCut · 가이드 필터) ② 넘침 = (가') 캔버스 직속 장식 Image ③ ⓒ 반투명 언믹싱 실험 안 넣음(기록만) ④ 하위 단계 나누지 않음. C++ · Config 변경 없음)**

- **구현(설계 H 대로):** ① normalize — 배경 판정 `gen/cutout.classify`(알파 < 250 이 1 % 이상 → ⓐ transparent · 테두리 띠(짧은 변 2 %)의 97 % 가 키 ± 12 → ⓑ flat · 아니면 ⓒ scene, inputs `concept_background` 로 덮음), ⓐ ⓑ 는 `reference_alpha.png` · `reference_color.png`(곧은 색 — 미리 곱한 색과 알파를 따로 늘려 나눔)와 판정 기록 `normalize.json background`, 그때 `reference.png` = 곧은 색을 검정 위에(렌더 바탕과 같게). ⓑ 언믹싱 `flat_unmix` — 키와 채널 최대 차 ≥ 64 덩어리의 바깥 윤곽 안(키 그대로인 구멍 제외) = 불투명, 밖은 색→알파(채널마다 키에서 끝값까지의 비 중 최대 · 색 = K + (P − K)/α). ② generate — ⓐ ⓑ 의 extract 에셋과 ⓒ 의 짧은 변 < 64 px 요소는 codex 를 부르지 않는다(`cut_only_reason` — backend `concept_cut`, 호출 상한 안 씀). ③ refine `_cut_entry`(extract.cutout) — 알파(ⓐ ⓑ reference_alpha · ⓒ 사각 패널 = 상자, 아니면 GrabCut + 가이드 필터(cv2.boxFilter) · 실패 = codex 실루엣(상자 안) · 그것도 없으면 상자) → 넘침 → 색 = 컨셉(ⓒ 는 장면 섞인 채 — '장면 섞임' 기록) → 가려진 자리 메우기 → 안쪽 알파(frame · panel_bg, ⓐ 제외) → 크기(위젯 대비 analyze 배율, ≤ 1024) → OCR(글자 위젯 자리 자국이면 글자 상자 전체를 구멍으로 한 번 더 — 한 색 물러남 없음). 한 색 칠하기 · IoU 0.85 물러남 없음. 예전 따오기는 `extract.cutout: false` 로 남김. ④ 넘침(가') — 캔버스 직속 장식 Image `<주인>Overhang`(주인 영역과 같은 앵커 · z, 그 영역 바로 앞 순서 = 영역 · 글자 아래), 주인 브러시 `draw_as none`(에셋 유지 — 왕복 · 다시 다듬기 식별), 겹치는 캔버스 형제 쌍 `allow_overlap` 자동, 에셋 크기 = 텍스처 크기(지난 크기는 `refine.json overhang_updates` — 다시 다듬을 때 걷고 원래 기준에서 새로). 크기 고정 · 런타임에 안 접히는(flag 아님 · collapsed 아님) 위젯만 — 장식 Image 는 바인딩이 없어 같이 안 접힌다. ⑤ analyze — codex 상한 6 은 generate 에셋에만, 프롬프트에 배경 판정 한 줄 · 'extract 는 컨셉 픽셀을 오린다' · 장식 위젯 상자는 끝 캡 · 연결선 · 빛까지 · 키 배지 · 작은 아이콘은 따로. ⑥ make_concept `--flat`(UI 만 · #000000 · 장면 없음 · 가장 큰 크기) · `--edit`(컨셉 바꾸기 — 실제 호출 시험은 안 함). ⑦ 지표 `fidelity.line_breaks`(컨셉 장식선 중 렌더 장식선(±2 px)이 못 덮은 조각 ≥ 6 px 의 수 — `region_report` 영역마다 · 요약 `region_line_gaps` · `region_line_de00`).
- **오프라인 확인에서 찾은 결함 → 고침 [실측 — G2 기준 run 3 개의 analyze spec · codex raw 로 새 refine 만, 에디터 · LLM 없음]:**

  | 결함 | 고침 |
  | :--- | :--- |
  | 밝은 청록 띠 전체가 장식선 판정(L* ≥ 45 · C* ≥ 20)이라 '테두리 장식선' 덩어리에 묻혀 띠 위 글자('어빌리티' · '링크 어택')에 구멍이 안 뚫리고, 줄 보간이 띠 전체를 피해 흰 줄을 칠함 | `cutout.frame_keep` — 테두리에 닿는 장식선 덩어리가 실루엣의 15 % 를 넘으면(선이 아니라 채움) 테두리 띠 안만 지킴, 줄 보간 원천도 그것만 피함 |
  | 두 톤 띠(위 밝은 청록 · 아래 짙은 파랑) 위 흰 글자 — `text_ink` 가 획 아래 절반만 잡음('돌진 공격' 위 절반이 남음) | `cutout.glyph_holes` — 글자 상자(빛 여백 뺀 줄 상자) 안 L* 흰 · 검은 탑햇(커널 = 상자 높이 × 0.3) > 14 를 더함 |
  | 구멍은 뚫렸는데 안쪽 알파를 '메우기 전' 색의 장식선 판정으로 정해 글자 모양대로 0.9 / 1 이 갈림(유령 글자) | 장식선 판정을 메운 뒤 색으로 |
  | GrabCut 이 반투명하게 장면으로 옅어지는 띠 끝을 배경으로 뗌('돌진 공격' 띠 왼쪽 반이 잘림) | ⓒ 는 GrabCut 결과에 codex 실루엣 속(3 px 침식 · 위젯 상자 안)을 더함 |
  | 넘침이 이웃 띠 bbox 바로 밖 테두리선 조각 · 뒤 바탕(엠블럼) 자리로 샘(스킬 다이아몬드 7284 px) | 막는 자리 = 다른 그리는 위젯 상자 + 4 px, 뒤에 깔린 바탕 위젯도 막음 |
  | 엠블럼 속 자식 이미지(스킬 다이아몬드) 자리를 줄 보간으로 메워 다이아몬드 실루엣 밖에 줄무늬 | 컨셉에서 따오는 자식 이미지 자리는 메우지 않음(같은 픽셀이 위에 겹침) — 런타임 이미지 · 새로 그리는 자식만 구멍 |
  | 큰 초상화(런타임 이미지) 상자가 그 위 배지 · 옆 검 아이콘 상자를 덮어 문양이 지워짐 | `refine.runtime_boxes` — 초상화 넓이의 반 이상이 요소 상자 안일 때만(초상화 테두리) 그 자리를 투명하게, 아니면 GrabCut 이 가름 |
  | 숫자 '10'(빛 13 px)이 54 px 방패 배지를 거의 다 덮어 구멍 = 배지 전체 → 원천 없이 회색 사각형 · 원래 숫자가 남음 | 글자 빛 넓힘 ≤ 요소 짧은 변 × 0.2, 탑햇 · 글자 상자 전체 구멍이 요소의 80 % 를 넘으면 안 씀, 메우기 원천 = 요소 안 성한 픽셀만(멀면 inpaint · 짧은 변 < 64 px 는 전부 inpaint — 줄 보간이 베벨 · 외곽선 사이를 이어 줄무늬), 요소 밖 구멍 알파 0(ⓒ = 원래 알파 < 0.5 인 자리 · ⓐ ⓑ = 구멍 뺀 실루엣 윤곽 밖) |
  | codex 시드 밖을 '아마 배경'으로 두자 codex 가 안 그린 부분(검 아이콘 둘레 청록 마름모)이 빠짐 · 상자 전체를 '아마 전경'으로 두자 엠블럼이 둘레 연기 · 이웃 띠 조각까지 끌어옴 | codex 실루엣이 상자의 30 % 미만이거나 가는 고리(3 px 침식 뒤 20 % 미만)면 상자 전체 = 아마 전경, 아니면 실루엣 안만 · 실루엣 속 = 확실한 전경 |
  | 가는 고리 시드(안쪽을 지운 HP 프레임)는 '상자 안 전경 < 15 %' 로 실패 판정 | 실패 = 시드의 40 % 미만만 남김(상자 전체 시드일 때만 상자 비율) |
  | codex 물러남 때 codex 가 상자 밖에 그린 것을 넘침으로 받음 · 1 ~ 3 px 가장자리 빛에도 장식 Image | 물러난 실루엣은 상자 안만 · 넘침은 4 px 넘게 나갈 때만 |

  남은 성질(ⓒ — 설계대로): 반투명 띠 뒤 장면(나뭇결)이 같이 구워진다 · 가득 찬 게이지(HP 1.0)는 채움 측정 불가라 트랙이 채움 색으로 메워진다(G2 뒤로 ②).
- **끝 run 1차(4개 모두 무인 통과 — `R20261116_145346_CombatHUD`(단색) · `145737_CombatHUD` · `150411_ProbePartyHUD` · `151500_ProbeControlGuide`)에서 찾은 결함 → 고침:**

  | 결함 [실측 run] | 고침 |
  | :--- | :--- |
  | 샘플 렌더에 접힌 '오의 불가' 글자 자국 — 넘침이 접힌(collapsed) 글자 자리를 막지 않아 게이지 프레임이 그 빛 · 획을 가져감(단색) | 접힌 위젯도 자리를 막음 — 뒤에 깔린 숨은 빛 이미지(요소 상자를 거의 다 덮는 것)만 예외 |
  | 96 px R 키 배지가 둘레 빛 선으로 상자를 '꽉 채워' 사각 패널 규칙(실루엣 = 상자)에 걸리고, 배지 폭 전체 글자 상자의 탑햇이 배지 테두리까지 지워 줄 보간 줄무늬(조작 안내) · 단색 체인 패널 아래 모서리 장식이 가로로 번짐 | 사각 패널 규칙은 짧은 변 ≥ 100 px, 탑햇 획은 `text_ink` 구멍에 닿는 덩어리만, 정사각에 가까운 요소(긴 변 < 짧은 변 × 1.5)도 inpaint |
  | 엠블럼(650 × 513)의 codex 실루엣이 0.11 이라 '상자 전체 시드'가 돼 둘레 연기를 끌어오고 이웃 상자 모양으로 네모나게 잘림(조작 안내) | 상자 전체 시드는 짧은 변 < 128 px 요소만 |
- **끝 run 2차(최종 코드 · 4개 모두 무인 통과 — `R20261116_154308_CombatHUD`(단색) · `154730_CombatHUD` · `155358_ProbePartyHUD` · `160219_ProbeControlGuide`)에서 찾은 결함 → 고침:**

  | 결함 [실측 run] | 고침 |
  | :--- | :--- |
  | 원형 키 아이콘(96 px)이 상자 모서리까지 전경(0.98)이라 네모 조각으로 보이고, 띠 넘침이 그 아이콘 상자에서 네모나게 끊겨 검은 홈(조작 안내) | 작은 정사각형 요소(짧은 변 < 128 · 긴 변 < 짧은 변 × 1.5, extract)는 상자 안 GrabCut 전경을 codex 실루엣 + 3 px 안으로 묶고, 넘치지 않으며, 이웃의 넘침을 막지 않는다(아이콘이 위에 겹침) |
  | (조작 안내만 다시 — 최종 `R20261116_162859_ProbeControlGuide`) | 위 고침 뒤 네모 아이콘 · 홈 사라짐(띠 끝 작은 홈 하나는 남음) |
  | (H 밖 — 기록만) 단색 컨셉 2차 run 의 외형 라운드(LLM)가 force_visible 렌더의 숨은 '가득 빛'을 빈 트랙 색 차이(ΔE00 51)로 보고 게이지 배경을 어두운 색으로 칠해 끝 캡 일부를 덮음 · '오의 불가' 빛 글자 뒤 어두운 상자 | 뒤로 넘김 — style_verifier 가 숨은 flag 위젯이 보이는 렌더라는 것을 모른다(1차 run 은 같은 컨셉에서 없었다 — 라운드 흔들림) |

- **최종 run(최종 코드 · 옵션 없음 · 무인 통과) — 기준 G2 끝 run 과 같은 (새) 지표 코드로 [실측 — 스크래치 `uigenH/metrics.py`]:** 화면 = 글자 상자를 뺀 화면 전체 장식선(L* ≥ 45 · C* ≥ 20) F1(±2 px) · 끊김 수(`line_breaks`) · 선 대표색 ΔE00. ⓒ 는 반투명 띠 뒤 장면도 같이 구워져 그만큼 화면 지표가 높게 나온다(띠 위 나뭇결이 컨셉과 같음).

  | 컨셉(배경) | run | 시도 | 화면 장식선 F1 · 끊김 · 선 ΔE00 (G2 → H) | 영역 | LLM(API 정가 환산) · codex |
  | :--- | :--- | :--- | :--- | :--- | :--- |
  | 단색 전투 HUD(ⓑ — 새 컨셉, `fixtures/m4_combat_hud_flat`) | `R20261116_154308_CombatHUD` | 5 | (기준 없음) 0.982 · 9 · 0.69 | 배너 F1 1.0 · ΔE00 0.38 · 모서리 1.0, 체인 패널 1.0 · 0.07 · 1.0 | 0.819 USD · 0 |
  | 전투 HUD(ⓒ — 회귀 기준) | `R20261116_154730_CombatHUD` | 5 | 0.654 → 0.655 · 273 → 273 · 15.2 → 15.2(장면 선이 재현율을 깎는 것은 같음) | 배너 0.890 → 0.878 · 5.57 → 6.29, 체인 패널 1.0 → 1.0 · 1.67 → 1.04, 게이지 0.957 → 0.958 — 회귀 없음(run 간 흔들림) | 0.713 · 3 |
  | 파티 HUD(ⓒ) | `R20261116_155358_ProbePartyHUD` | 4 | 0.855 → 0.949 · 52 → 29 · 7.19 → 2.57 | (은청색 선은 채도가 낮아 장식선 판정 밖 — 영역 지표 대부분 0) | 0.924 · 3 |
  | 조작 안내(ⓒ) | `R20261116_162859_ProbeControlGuide` | 5 | 0.535 → 0.998 · 110 → 9 · 9.9 → 0.04 | 영역 평균 F1 1.0 · ΔE00 0.11 · 모서리 0.998 | 0.597 · 16 |

  비교 그림 = 각 run 의 work `assets/compare/overview_H.png` · `regions_H.png`(컨셉 | G2 렌더 | H 렌더). 그 전 run 5 개(1차 4 · 조작 안내 2차 1)는 위 결함 표로만 남는다.
- **증거 정리(11-17 사용자 승인 — '원래 추천대로'):** 위 표의 최종 run 4 개(`R20261116_154308_CombatHUD` · `154730_CombatHUD` · `155358_ProbePartyHUD` · `162859_ProbeControlGuide`)의 work · `Content/_AutoGen/` 은 남겼다. 중간 run 7 개(`145346` · `145737` · `150411` · `151500` · `160219` · UI 만 컨셉 `171638` · `173820`)의 work · `Content/_AutoGen/` 과 스크래치 `uigenH` 는 휴지통 — 그 숫자는 위 표 · 글로만 남는다. make_concept 출처 기록 `work/_concept/20261116_145230`(단색 컨셉) · `20261116_171507`(UI 만 변환)과 시험 입력 `fixtures/m4_combat_hud_flat` · `work/_probe/controls_ui` 는 concept.json 이 참조해 남긴다. 누적 비용 — LLM 약 8.5 USD 환산 · codex 62 회(새 컨셉 1 포함, 구독 — 과금 아님). 걸린 시간: 단색 컨셉 4분 14초(codex 0) · 조작 안내 17분(extract 14개 중 codex 시드 16회 — ⓒ 의 codex 는 실루엣 시드로만 쓰지만 호출 한 번에 약 1분).
- **사람 눈 1차(11-16, 사용자):** 합성 스크린샷 두 장의 H 결과에 '배경 잔상 · 화질 저하(마우스 아이콘) · 가운데 흐린 문양 일부 잘림'. 원인 정리 [실측]: 잔상 = 반투명 UI 픽셀이 'UI 색 × 투명도 + 뒤 장면'이라 오리면 장면이 같이 옴(방식 한계 — 언믹싱은 뒤 장면을 몰라 못 함) · 화질 = 원본 807 × 353 을 2.38 배 늘린 픽셀을 오림(마우스 아이콘 원본 약 40 px → 190 px 텍스처 — 오리기는 원본보다 선명해질 수 없음, G2 는 codex 가 1254 px 로 새로 그려 선명) · 문양 잘림 = 어둡고 반투명한 문양 색이 장면과 비슷해 GrabCut(색 기반)이 엠블럼 상자의 39 % 를 배경으로 판정, codex 실루엣 시드도 상자의 11 % 뿐(분리 오차). 단색 배경 새 컨셉은 셋 다 없음. 사용자 결정: **합성 스크린샷은 codex 로 'UI 만 · 검정 배경' 컨셉으로 한 번 바꾼 뒤 오려 쓰는 길을 시험.**
- **UI 만 컨셉 시험(조작 안내):** `make_concept.py --edit <스크린샷> --flat`(편집용 규칙 `FLAT_EDIT_RULES` — 장면 제거 · 검정 단색 · 구도 · 비율 유지 · 반투명은 검정 위 모습 · 최대 해상도, codex 1회 50 초) → 1898 × 829 UI 만 컨셉(`work/_probe/controls_ui` — 띠가 그림 좌우 끝에 닿아 `concept_background: flat` 명시). 끝 run(ⓑ — codex 호출 0, 약 5분): 1차 `R20261116_171638` · 최종 `R20261116_173820_ProbeControlGuide`(무인 통과 · LLM 0.667 USD · 화면 장식선 F1 0.995 · 끊김 4 · 선 ΔE00 0.21 — 비교 그림 work `assets/compare/overview_H.png`). **잔상 · 흐림 · 문양 잘림 없음.** 1차에서 드러난 ⓑ 글자 구멍 결함 → 고침: 획 모양 구멍이 조각나 줄 보간이 조각 사이 글자색 · 이웃 배지 테두리를 끌어옴('공격' 줄무늬 · '회피' 회색 네모) → 글자마다 (획 ∪ 탑햇) ∪ 글자 줄 상자 + 가로 획 높이 × 0.5 사각형을 통째로 · 어두운 반투명 띠(알파 < 0.5)가 메우기 원천에서 빠짐 → 원천 = 알파 > 0.05 · 구멍 크기 판정도 보이는 모양 기준 · 두 톤 띠 가운데 밝은 경계선이 '테두리 장식선'으로 지켜져 첫 글자 획이 남음 → 지키는 장식선은 보이는 윤곽에서 짧은 변 × 0.25 안만. **남은 것:** 글자 사각형 자리를 줄 보간으로 메워 띠의 사선 무늬가 그 자리만 평평한 패치로 보이고(글자가 일부만 덮음), R 키 글자 사각형이 날개 장식 일부를 흰 얼룩으로 메움 — 설계 H 3 의 '둘레에 무늬가 있으면 codex 로 메우기' 몫(예: UI 만 컨셉을 만들 때 글자 없는 판을 한 장 더 받아 구멍만 그 픽셀로). 1차 run 의 'T' 가 안 보이던 것은 최종 run 에서 재현 안 됨(원인 미확인 — analyze 배치가 run 마다 다름).
- **시험:** pytest **299**(G2 283 → +16: `test_cutout` 16 — 배경 판정 · 단색 언믹싱 · GrabCut 결정성 · 넘침 · 메우기 · normalize 층 · generate 오리기만 · refine 오리기 + 넘침 장식 다시 다듬기 · 접힌 위젯 넘침 · 합성 스크린샷 시드 · 두 톤 띠 글자 · 덮인 배지 · 런타임 이미지 속 · 작은 아이콘 · analyze 상한 · 끊김 지표 · make_concept 옵션 / `test_extract` 옛 따오기 시험은 `cutout: false` 로). C++ · Config 변경 없음 → 빌드 없음, 에디터 회귀 생략(Python 만).

**1b 후속 H2 — 글자 없는 판 · 겹친 오리기 · 글자 측정 (11-16, 미커밋 — H 의 이어서 세션, 사용자 승인 '추천한 고치기' + 진행 중 사용자 요청 2건(E 배지 아래 네모 · 'T' 측정). C++ · Config 변경 없음)**

- **글자 없는 판 연결(설계 H 3 의 '둘레에 무늬가 있으면 codex' 몫):** `make_concept.py --text-free`(codex 1회 50초 — 글자만 빠졌는지 사람 눈 확인 통과) → inputs `concept_notext` → normalize 가 같은 배경 처리 · 배치로 맞추고 위상 상관 정합(조작 안내 (−0.15, −0.91) px, ±12 px 넘으면 안 씀) → `reference_notext_color/alpha.png` → refine `_cut_entry` 가 텍스처 상자 조각(사방 6 px 크게)을 `cutout.compose(fill_from)` 로: 글자 구멍(획 ∪ 탑햇 ∪ 사각형 — 자식 이미지 · 게이지 구멍 · 게이지 막대 상자 제외)만 판 픽셀로, 요소마다 ±6 px 이동 탐색(구멍 밖 6 px 띠 미리 곱한 색 평균 차 — 가장 작은 차와 0.5 단계 · 5 % 안이면 작은 이동), 차 > 24 면 판 없이 예전 길(too_big 규칙도 되살림), 경계는 2 px 넓혀 σ 1.2 흐린 마스크로 섞되 그 요소에 보이던 자리만, 판이 있으면 too_big 규칙 끔. 판 조각에도 같은 OCR 자국(IoU ≥ 0.3)이면 장식 · 남으면 글자 상자 전체 + 판 → 그래도 남을 때만 판 없이. `pipeline.yaml extract.notext`.
- **진행 중 찾은 결함 → 고침 [실측]:**

  | 결함 | 고침 |
  | :--- | :--- |
  | 판 이동이 ±3 끝에 걸림(왼쪽 띠 −1 ~ −3 · 오른쪽 +3 ~ +4 — codex 가 그림을 가로로 살짝 늘림) · 완만한 띠는 −3 (4.20) · −6 (3.97)처럼 차가 거의 같아 범위 끝으로 끌림 | ±6 · 동점 폭 안이면 작은 이동(확대 비교로 결과 같음 확인) |
  | '링크 어택' 띠 — 컨셉에 원래 있던 옅은 사선을 OCR 이 글자로(0.766, 판 이동 1 px 차로 켜졌다 꺼짐) → 판 없이 다시 해 줄 보간 패치로 돌아감 | 판 조각 OCR 비교로 장식 분류 |
  | 단색 전투 HUD 첫 run `R20261116_184545` 실패(baked_text 4회) — analyze 가 체인 패널 글자 상자를 패널 폭 전체로 잡아 금색 모서리 장식이 글자 획으로 잡혀 줄 보간이 가로로 번짐, ⓑ 안쪽 알파를 없앤(H 고침) 뒤 그 줄이 OCR 에 잡힘 | `concept_pixels.text_holes(drop_frame_touch)`(오리기만) — 테두리 장식선에 닿고 글자 상자 가운데 절반 밖인 획 덩어리는 구멍에서 뺌(가운데 덩어리 — 키 배지 테두리 — 는 그대로) |
  | (사용자 사람 눈) E 배지 왼쪽 · 오른쪽 아래 네모 — 엠블럼 위젯 상자가 회피 띠 아래 28 px 와 겹쳐 ⓑ 오리기가 띠의 반투명(알파 0.16)까지 엠블럼 텍스처에 넣어 두 번 쌓임 | `refine._drop_neighbour_pixels` — 오리는 두 위젯 상자가 일부만 겹치면(포함 관계 90 % · 작은 아이콘 제외) 겹친 자리를 한쪽만: 불투명 덩어리(2 px 깎아 가는 연결선 끊음)는 더 많이 걸친 쪽, 반투명은 작은 상자. 오프라인 1 · 2차 부작용(양쪽 다 빼 빈 줄 · '더 깊은 쪽' 규칙이면 엠블럼 글자 구멍 규칙이 다시 지움 · 판 섞기 경계가 빈 자리에 알파를 넣어 세로줄)도 고침 |
  | 키 배지 둘레 차 15.5 ~ 18.6 — 기준 18 이면 E 배지가 판을 썼다 못 썼다(못 쓰면 예전 방사 무늬) | 기준 24(다른 그림은 수십) |
  | (사용자 요청) 'T' 가 배지 위로 크게 — 크기 판이 컨셉 'T' 를 측정 상자 3번 넓히며 배지 베벨까지 잡아(51 × 57, 정답 약 30 × 38) 높이 비 0.632 → 40 → 63 | 글자 맞춤 `style._notext_text_mask` — 판이 있으면 컨셉 획 = 판과 다른 픽셀(글자 상자마다 오츠 문턱 ≥ 48 — 다시 그린 원판 차 수십은 빠짐): '공격' · '점프' 175 × 61 → 87 × 49 · 'R' 198 × 71 → 36 × 46 · 'E' 27 × 38(정답). 크기 판 신뢰 범위 0.6 ~ 1.6 → 0.7 ~ 1.4(0.75 면 G2 '4.2' 0.742 를 막음). 판 없이 쟀다면 최종 run 직전 run 에서도 'T' 0.719 → 38 → 53 이었다(재현 확인) |
  | (사용자 사람 눈) 최종 run 후보 `202833` 의 '회피' · '어빌리티' 가 크고 굵고 '회피' 가 위로 — analyze 가 42 · bold 로 시작했고, 글자 맞춤의 렌더 측정(`fidelity.text_ink`)이 '칠해진 픽셀이 상자 폭 60 % 인 줄 = 가로 테두리선'으로 크고 굵은 글씨의 가로획 줄('회' + '피')을 지워 높이를 반만 쟀다(58 → 29 px · '어빌리티' 27 · '돌진 공격' 22) → '회피' 42 → 50 · 위로 이동, 나머지는 건너뛰어 bold 유지 | 테두리선 = 끊김 없는 한 조각이 폭의 85 % 이상인 줄만(`INK_LINE_RUN` — 글자 하나짜리 'T' 가로획도 살림) · 글자색을 아는 쪽(밝음 · 어두움)을 글자로 고르는 `prefer`(처음 가설 '획 사이 틈을 고름'은 틀렸다 — 해 없는 안전장치로 남김) · 글자 맞춤 `_frame_drop` 도 큰 띠 덩어리는 테두리 띠만(`cutout.frame_keep` — 밝은 청록 띠와 거기 닿은 '어빌리티' 획이 통째로 빠져 컨셉 획이 비었다). 결과: 라벨 7 개 측정 · 높이 비 0.94 ~ 1.06 · 굵게 → 보통 자동 판정, '점프' 는 렌더 측정이 상자 끝에 닿아 건너뜀(크기 analyze 그대로) |
  | 엠블럼(위 z)이 E 배지 오른쪽 아래를 어둡게 덮음 · 배지 뒤 옅은 네모 — 이웃 몫으로 비운 자리 · 작은 아이콘 실루엣 밖을 글자 없는 판 채우기가 다시 채움 | 비운 자리 · 아이콘 실루엣 밖은 메우기 뒤에도 투명(`_cut_entry` keep 마스크) |
  | 'T' 미표시(H 1차 run `171638` 과 같은 현상 — 원인 확인) — analyze 가 가운데 엠블럼 영역을 띠들보다 위(z 2)에 두고, 엠블럼 텍스처가 띠 · T 배지(글자 자리는 판으로 메운 원판)를 다시 그려 엔진 'T' 를 가림. 띠 끝 가는 연결선이 띠 · 엠블럼을 한 덩어리로 이어 위 겹침 규칙을 피함 | 위 겹침 규칙의 2 px 깎기 — 엠블럼 텍스처의 T 배지 자리 알파 250 → 0 |

- **끝 run [실측 — 스크래치 `uigenH/metrics.py`]:**

  | 컨셉 | run | 결과 | 화면 장식선 F1 · 끊김 · 선 ΔE00 | LLM(API 정가 환산) · codex |
  | :--- | :--- | :--- | :--- | :--- |
  | 조작 안내 UI 만(ⓑ + 글자 없는 판) — 판 연결 첫 run | `R20261116_184042` | 무인 통과(4 시도) | 0.9947 → 0.9999 · 4 → 0 · 0.21 → 0.15(직전 `173820` 대비) | 0.753 · 0 |
  | 같은 컨셉 — 겹침 고침 뒤 | `R20261116_191939` | 통과(4) | 0.9997 · 0 · 0.19 | 0.569 · 0 |
  | 같은 컨셉 — 글자 측정 고침 뒤(T 미표시 발견) | `R20261116_201538` | 통과(4) | 0.9998 · 0 · 0.14 | 0.669 · 0 |
  | 같은 컨셉 — T 미표시 고침 뒤(라벨 크게 · 굵게 — 사용자 지적) | `R20261116_202833` | 통과(4) | 0.9998 · 0 · 0.16 | 0.961 · 0 |
  | 같은 컨셉 — 렌더 획 측정 고침 뒤 | `R20261116_210642` · `212033` | 통과(5 · 4) | 0.9996 · 0 · 0.15 / 0.9997 · 0 · 0.17 | 1.002 · 0.534 · 0 |
  | **같은 컨셉 — 최종 코드** | **`R20261116_212649`** | 통과(5) — 글자 9 개 중 8 개 측정 · 높이 비 0.97 ~ 1.0 · 중심 차 ≤ 1.5 px, 라벨 굵기 · 크기 · 위치 컨셉과 같음('E' 는 렌더 측정이 배지 베벨까지 잡아 건너뜀) | 0.9997 · 0 · 0.12 | 1.006 · 0 |
  | 단색 전투 HUD(ⓑ, 판 없음) — 모서리 장식 고침 뒤 | `R20261116_185558` | 통과(5 — 1차 겹침 · iou_leaf 는 LLM fix) | 0.896(렌더는 숨은 요소까지 보이게 — 숨은 '가득 빛'이 트랙 위에 보여 낮게 나옴, 실제 상태 렌더는 직전 `154308` 보다 컨셉에 가까움: 외형 라운드가 끝 캡을 가리던 것이 없음) · 체인 패널 F1 0 은 글자 상자가 패널을 다 덮어 잴 선이 없는 측정 탓 | 0.776 · 0 |

  **증거 정리(11-17):** H2 의 run 은 전부 휴지통 — 중간 run 은 11-16 사용자 승인, 최종 `R20261116_212649` · `185558` 의 work 는 11-17('판단에 맞게' — 단색 전투 HUD 는 H3 `094643` 이 같은 입력의 최신 기준, 조작 안내의 회색 합성은 H3 최종 run `overview_H3.png` 위 칸에 남음). 같은 이름 `Content/_AutoGen/` 2 개도 지움(11-17 — 에디터를 끈 뒤 H3 세션이, 사용자 승인 · 휴지통). 아래 비교 그림 경로는 지워졌고 이 표 · 결함 표로만 남는다.
  비교 그림 = 각 run work `assets/compare/overview_H2.png`(컨셉 | 직전 | 새). 사람 눈(사용자): 판 연결 첫 run 에서 글자 자리 패치 · R 배지 · R 옆 얼룩 · E 네모(H 고침) · 왼쪽 그림자(H 고침) 사라짐 확인 → E 배지 아래 네모 지적 → 고친 run 에 '이 정도면 나쁘지 않다' → 'T' 측정 고침 요청. 최종 run 은 'T' · 'E' · 'R' 이 배지 안에 맞고 패치 없음.
- **남은 것(기록):** analyze 의 run 별 흔들림(라벨 굵기 · 크기 시작값 · 영역 z 순서)은 글자 맞춤이 측정을 믿을 수 있을 때만 흡수한다 — 키 배지 'E' 는 렌더 쪽 측정이 배지 베벨까지 잡아(높이 비 1.3) 건너뛰는 일이 남음(렌더 쪽은 글자 없는 판이 없다), 렌더 측정이 상자 끝에 닿으면 건너뜀(이번 '점프' 한 번). 겹친 오리기는 '작은 상자가 반투명을 가짐'이 전제(큰 장식 요소는 가장자리에서 이웃을 걸칠 뿐) — 반대인 배치가 나오면 다시 볼 것.
- **비용 · 시험:** H2 LLM 약 6.8 USD 환산(끝 run 9 — 실패 run `184545` 0.54 포함) · codex 1(글자 없는 판), 구독 — 과금 아님. pytest **307**(H 299 → +8: 판 채우기 · 물러남 · 정합 · run 연결 · OCR 장식 분류 · 모서리 장식 · 겹친 오리기 · 판 마스크 · 글자 획 가로선, make_concept `--text-free` 는 기존 시험에 덧붙임). C++ · Config 변경 없음 → 빌드 · 에디터 회귀 없음.

**1b 후속 H3 — 진짜 알파 컨셉 · 회색 바탕 확인 (11-17, 미커밋 — H2 의 이어서 세션. 시작 질문 3개 사용자 전부 추천안: ① 투명 배경 컨셉 먼저(안 되면 두 배경 매팅 → 규칙 다듬기) ② 투명판은 원본 스크린샷에서 편집 ③ 회색 검증은 오프라인 합성(C++ 없음). C++ · Config 변경 없음)**

- **결함 · 원인(H2 끝 run `R20261116_212649` — 사용자가 WBP 디자이너 회색 격자에서 찾음):** 검정 배경(ⓑ)에선 '어둡고 반투명한 장식'과 '어둡고 불투명한 칠'이 같은 픽셀이다. `flat_unmix` 의 '키와 64 이상 다른 덩어리 윤곽 안 = 불투명' 규칙이 엠블럼 뒤 소용돌이를 불투명 남색 얼룩으로(텍스처 어두운 픽셀 95 % 가 알파 > 0.95), 서서히 옅어지는 띠 끝을 윤곽 경계 · `LOW_DIFF` 딱 자르기로 들쭉날쭉하게 만들었다. 렌더 · 지표가 전부 검정 바탕이라 못 잡았다. 회색 합성으로 재현하니 ⓑ 추정 알파 자체에 컨셉 알파 절벽 14,640 px · 어둡고 불투명 비율 0.93 이었다(합성은 그 추정을 그대로 따름 — 고칠 곳은 컨셉 쪽).
- **① 진짜 알파 컨셉(②③ 은 필요 없었음):** `make_concept.py --transparent`(`TRANSPARENT_RULES` · `TRANSPARENT_EDIT_RULES` — 장면 완전 제거 · 진짜 알파 채널 · 반투명은 알파로 · 검정 · 흰 · 회색 · 그린 격자 금지, `--flat` 과 함께 못 씀, 알파 없이 오면 그림은 남기고 종료 코드 1 `no_alpha`). 원본 합성 스크린샷(`work/_probe/controls`)에서 codex 1회 48초 → 1897 × 829 RGBA(투명 41 % · 반투명 픽셀 곧은 색 평균 채널 최대 177 — 검정을 구운 흔적 없음, 엠블럼 뒤 소용돌이 반투명 · 띠 끝 부드럽게 옅어짐 — 그림 확인). 글자 없는 판 `--text-free` 는 원본이 알파 PNG 면 '알파 유지' 문구를 자동으로 붙임(codex 1회 40초 — 진짜 알파로 왔지만 반투명 띠를 더 불투명하게 그림: 글자 둘레 알파 컨셉 0.85 ~ 0.94 ↔ 판 0.98 ~ 0.99). 시험 입력 `work/_probe/controls_alpha`(git 무시 — `concept_background: transparent`). `flat_unmix`(ⓑ) 는 그대로 — 사람이 검정 배경 컨셉을 주면 같은 한계가 남는다(README 에 'ⓐ 가 기본' 명시).
- **④ 회색 바탕 확인 `gen/backdrop.py`(기록만):** 통과한 run 의 최종 텍스처를 실제 렌더 상자(geometry — force_visible) · 그리는 순서(캔버스 z 안정 정렬 · 자식 순서)대로 #808080 위에 다시 쌓는다(image 늘림 · box/border 9-slice · rounded_box · ProgressBar 채움 · 틴트, 글자 TextBlock 은 빠짐 — 지표는 글자 상자 + 6 px 를 뺌). 합성기 검산 = 검정 위 합성 ↔ `render.png` 평균 0.4 ~ 0.8 · p95 1.0 ~ 1.9 / 255(엔진이 곧은 색을 sRGB 값 그대로 섞는 것 재확인). `report.recorded.backdrop`(검산 · 회색 위 ΔE00 · 알파 MAE · 컨셉에 없는 알파 절벽 · 어둡고 불투명 비율 합성 ↔ 컨셉 · 텍스처별) + `artifacts.backdrop` = `assets/compare/backdrop.png`(컨셉을 회색 위에 | 합성). 정답은 ⓐ 만(`truth: concept_alpha`), ⓑ 는 언믹싱 추정(`unmix_estimate`), ⓒ 는 비교 없음.
- **진행 중 찾은 결함 → 고침 [실측]:**

  | 결함 | 고침 |
  | :--- | :--- |
  | 판으로 메운 글자 자리만 진한 사각 패치(회색 바탕 — 판의 띠가 더 불투명) | `cutout._notext_alpha_gain` — 글자 구멍 둘레의 컨셉 ÷ 판 알파 비를 구멍 안으로 이어(가로로 긴 구멍은 세로로 — 위 · 아래 둘레 사이) σ 4 정규화 가우시안으로 펴서 판 알파에 곱함(둘레 비가 1 ± 0.02 면 손대지 않음). 오프라인 2판을 거침: 줄(가로) 보간은 줄마다 비가 달라 가로 줄무늬 · 넓은 글자 사각형 가운데에서 어긋남(옅어지는 쪽이 회색으로) |
  | E 배지 inpaint 방사 무늬 — analyze 글자 상자가 배지보다 커 글자 사각형 구멍이 배지 전체 → 둘레 0 px 라 판을 못 씀 | 둘레가 20 px 미만이면 획 둘레(획에서 2 ~ 8 px)로 정합(`notext.ring_from strokes` — 차 1.24 로 판 사용) |
  | 위 · 아래 띠 넘침이 두 띠 사이 반투명 소용돌이를 둘 다 가져가 두 번 쌓임(덮임 0.6 ~ 0.8 ↔ 컨셉 0.27 ~ 0.45, 2.2 만 px — 검정에선 안 보임) | 넘침 장부 `run.overhang_claims` — spec 에셋 순서로 앞 에셋 넘침이 차지한 빈 자리(위젯 상자 밖)는 뒤 에셋 넘침이 못 가져감(`overhang.blocked_claimed_px`), 다시 다듬기(`only_assets`)는 건너뛴 에셋의 지난 넘침 알파를 장부에. 오프라인 2.2 만 → 3.7 천 px · 알파 MAE 0.0091 → 0.0050 |
  | 'T' 미표시 재발(`R20261117_094157`) — analyze 가 가운데 엠블럼 영역(z 2)을 T 배지까지 덮게 잡아 엠블럼 텍스처가 T 배지 상자를 통째로 품고(포함 관계라 H2 '겹친 자리 한쪽만' 규칙 밖) 위에 그려 엔진 'T' 를 가림 | `refine._drop_covered_below` — 오리는 텍스처는 자기 최상위 영역보다 먼저(아래) 그려지는 다른 영역의 담긴 글자(상자 + 2 px) · 오린 이미지(그 텍스처 자리) · 늘 보이는 것만 비움. 위에 그려지는 자기 자식은 그대로 |
  | (시험 뒤 되돌림) 담긴 자식(엠블럼 속 키 아이콘 · 원판 · 다이아몬드) 자리를 늘 비우기 | ⓐ 에선 뒤 장식 · 띠가 불투명해 작은 아이콘 실루엣 · 다이아몬드 텍스처가 상자째라 네모 구멍이 되고, 어빌리티 띠는 T 배지 네모 둘레 줄 보간 줄무늬 · 네모 테 — 자식이 같은 픽셀로 위를 덮어 회색에서도 차이가 없어(알파 MAE 0.0076 → 0.0059 뿐) 안 함. 엠블럼 이웃 조각(결함 3)의 결론: 띠 상자 밖 띠 끝은 엠블럼 몫 그대로(보기 같음), 담긴 자식은 위에 같은 픽셀, 아래 영역을 덮어 가릴 때만 비움(위 행) |
  | (시험 뒤 되돌림) 회색 합성에서 시작 때 숨은 위젯(collapsed) 빼기 | 컨셉이 경고 글자 · 빛처럼 기본으로 숨은 위젯이 보이는 상태를 그려 오히려 멀어짐(단색 전투 HUD ΔE00 6.8 → 11.0) — force_visible 그대로 |

- **⑤ 스킬 아이콘 = 런타임 이미지 시험(`work/_probe/controls_alpha_icons` — 같은 투명 컨셉, data 4개 `type: image`) `R20261117_093639`:** 실패 — 겹침 게이트(analyze 가 Hub 영역 ↔ 회피 · 어빌리티 띠 겹침 쌍을 `allow_overlap` 에 안 넣음 · 결정적 fix 에 겹침 op 없음 — 아이콘과 무관한 배치 흔들림). 아이콘 길 자체는 동작: Image 4 + `binding {kind: image}` + 반투명 어두운 `rounded_box` 자리표시(Hub Overlay 안 — 겹침 검사 밖) · 오린 다이아몬드 틀의 아이콘 자리 비움(`runtime_boxes`). **그러나 아이콘이 45° 마름모인데 위젯 · 비움이 축 정렬 82 × 82 사각형** → 비운 네모가 다이아몬드 틀 선을 자르고 자리표시끼리 겹친다. 후보(사용자 결정): (가) 위젯 회전(RenderTransform angle — WidgetMcp spec · C++ 확장, 먼저 묻기) (나) 비움을 컨셉 실루엣 모양(마름모)으로 + 게임 쪽 아이콘 텍스처를 마름모 알파로 (다) 마름모 마스크 UI 머티리얼.
- **끝 run [실측 — `report.recorded.backdrop`]:**

  | 컨셉 | run | 결과 | 회색 ΔE00 평균 · p95 · 알파 MAE · 컨셉에 없는 절벽 px · 어둡고 불투명(합성 ↔ 컨셉) | LLM(API 정가 환산) |
  | :--- | :--- | :--- | :--- | :--- |
  | (H2 기준 — ⓑ 검정 UI 만 + 판 · run 은 11-17 휴지통) | `R20261116_212649` | — | 정답 없음(언믹싱 추정과는 0.18 로 같음 — 결함이 추정 자체에), 텍스처 어둡고 불투명 엠블럼 0.95 · 띠 0.92 ~ 0.96, 추정 알파 절벽 14,640 | — |
  | 조작 안내 투명(ⓐ + 판) — 첫 run | `R20261117_090812` | 통과(4) | 0.31 · 1.45 · 0.0126 · 1 · 0.36 ↔ 0.35 — 얼룩 · 잘림 없음, 글자 자리 패치 · E 방사 무늬 발견 | 0.761 |
  | 판 알파 맞춤 · 획 정합 뒤 | `R20261117_092636` | 통과(4) | 0.29 · 1.46 · 0.0091 · 75(띠 상자 모서리 5 × 5 틈) · 0.34 ↔ 0.34 — 두 띠 사이 이중 발견 | 0.735 |
  | 스킬 아이콘 데이터(⑤) | `R20261117_093639` | 실패(겹침 — 위) | — | 1.193 |
  | 넘침 장부 뒤 | `R20261117_094157` | 통과(4) | 0.24 · 1.05 · 0.0061 · 11 · 0.40 ↔ 0.39 — 'T' 가려짐 발견 | 0.684 |
  | 단색 전투 HUD(ⓑ, 판 없음 — 회귀) | `R20261117_094643` | 통과(4) | 정답 없음: 언믹싱 추정과 6.84 · 47.9(글자 빛이 글자 상자 밖 · force_visible 의 숨은 '가득 빛') · 패널은 원래 불투명(어둡고 불투명 0.94 ↔ 0.93) — 회색 위 테두리 깨끗 | 0.464 |
  | **조작 안내 — 최종 코드** | **`R20261117_095249`** | 통과(4) — E · T · R 보임 | **0.22 · 1.10 · 0.0075 · 0 · 0.36 ↔ 0.35** | 0.618 |

  비교 그림 = 최종 run work `assets/compare/overview_H3.png`(위 H2 회색 합성 | 가운데 H3 회색 합성 | 아래 H3 컨셉을 회색 위에) · `backdrop.png`. 사람 눈(사용자 — WBP 디자이너 회색 바탕)은 이 run 의 `/Game/_AutoGen/R20261117_095249_ProbeControlGuide/WBP_ProbeControlGuide`.
- **증거 정리(11-17 사용자 승인 — 휴지통):** 최종 run 2 개(`R20261117_095249_ProbeControlGuide` · `R20261117_094643_CombatHUD`)의 work · `Content/_AutoGen/` 과 시험 입력 `work/_probe/controls_alpha` · `controls_alpha_icons`, codex 호출 기록 `work/_concept/20261117_090516` · `090634` 는 남겼다. 중간 run 4 개(`090812` · `092636` · `093639` · `094157`)의 work(약 200 MB) · `Content/_AutoGen/` 3 개와 스크래치 `uigenH3`(151 MB)는 휴지통 — 위 표의 결함 열로만 남는다.
- **남은 것(기록):** ① '어빌리티' 라벨이 컨셉보다 작음 — 글자 맞춤 컨셉 측정(판 차이)이 첫 글자 '어' 획을 놓쳐 높이 비 0.83 · 폭 비 1.17 로 어긋나 건너뛰고 analyze 크기 34 그대로(H2 계열 측정 흔들림) ② 띠 끝 ↔ 엠블럼 상자 일부 겹침 자리 반투명 약간 이중(1 천여 px) · 두 상자 BLOCK_PAD 가 서로 막는 모서리 5 × 5 틈(run 마다 0 ~ 75 px) ③ 글자 구멍이 첫 획을 덜 덮어 띠 텍스처에 '(' 모양 획 자국(엔진 글자 아래 가려짐) ④ 판 알파 차가 판 둘레 차에도 섞여 공격 띠 20.9(기준 24 에 가까움) ⑤ ⓑ 경로는 그대로(검정 배경 컨셉의 근본 한계) ⑥ 마름모 런타임 아이콘(⑤).
- **비용 · 시험:** LLM 약 4.5 USD 환산(run 6 — 실패 1 포함) · codex 2(투명 컨셉 · 글자 없는 판), 구독 — 과금 아님. pytest **316**(H2 307 → +9: `test_backdrop` 9 — 그리는 순서 · 바탕 비침 합성 · 9-slice 모서리 · 회색에서만 보이는 얼룩 · 잘림 검출 · 판 알파 맞춤 · 획 둘레 정합 · 넘침 장부 · 아래 영역 비우기 · `make_concept --transparent`, `test_pipeline_retry` 기대값에 `artifacts.backdrop`). C++ · Config 변경 없음 → 빌드 · 에디터 회귀 없음.

**1b 후속 H 계열 마무리 — 남은 작은 문제 (11-17, 미커밋 — H3 세션에서 이어서. 사용자 '나머지 작은 문제 고치고 이 단계 최종 종료', 다른 컨셉 적용 검증은 뒤 phase 로. C++ · Config 변경 없음)**

- **고친 것 [실측]:**

  | 결함 | 원인 | 고침 |
  | :--- | :--- | :--- |
  | '어빌리티' 라벨이 컨셉보다 확연히 작음(34) | 글자 측정의 테두리선 빼기(`style._frame_drop`)가 영역마다 상자 가장자리 밝은 선을 지우는데, 가운데 엠블럼 영역 상자 오른쪽 끝(x 1280)이 '어' 를 지나가 'ㅇ' 이 엠블럼 테두리선으로 빠짐 → 컨셉 획 1286 부터(정답 1272) · 높이 비 0.83 · 폭 비 1.17 로 어긋나 크기 판 건너뜀 | 다른 영역의 글자 상자 안은 그 영역의 테두리선으로 지우지 않음 → 측정 0.894 / 0.912 → 40 |
  | '돌진 공격' · '점프' · 키 배지 'E' 가 측정 건너뜀(렌더 쪽) | 렌더 획 측정(밝기 가르기)이 두 톤 띠 밝은 윗면 · 배지 베벨까지 글자로 잡아 상자 끝에 닿거나 신뢰 범위 밖 | 렌더 쪽 '글자 없는 판' = 최종 텍스처를 렌더 상자대로 다시 쌓은 합성(`gen/backdrop` — 렌더와 1/255 안)과의 차(`style._render_text_mask`, 합성이 렌더를 못 따라가면 안 씀). 밝기 측정을 못 믿을 때만 대신 쓰고 그때는 굵기 판정 안 함(늘 쓰면 획 밀도 기준이 달라 '어빌리티' 를 굵게로 오판) |
  | 띠 끝 ↔ 엠블럼 겹친 자리 반투명 이중 — 점프 띠 끝 아래 소용돌이(덮임 0.83 ↔ 컨셉 0.67) | '겹친 자리 한쪽만'(`_drop_neighbour_pixels`)이 덩어리를 각자 다른 크기 검색 조각에서 세어 양쪽 모두 '내 쪽이 많다' · 소용돌이 0.6 을 불투명 덩어리(> 0.5)로 침 | 두 상자를 합친 영역 · 전체 알파로 세고(양쪽 같은 답) 덩어리 크기는 겹친 자리 둘레 24 px 안에서만(합친 영역 전체면 띠 몸통이 엠블럼 큰 장식에 끌려가 띠에 검은 네모 24 × 29 — 시험 run `112216`), 불투명 기준 0.85 → 0.67 ↔ 0.67 |
  | 위 마우스 아이콘 오른쪽 위 밝은 네모(0.81 ↔ 0.65) | 작은 아이콘 실루엣 = 알파 > 0.5 — 진짜 알파 컨셉에선 둘레 소용돌이도 0.65 라 아이콘 텍스처가 상자 모서리까지 품어 엠블럼과 이중 | 실루엣 기준 0.85(`refine._icon_mask`) → 0.68 ↔ 0.65 |
  | 띠 상자 모서리 5 × 5 틈(run 마다 0 ~ 75 px) | 두 상자의 BLOCK_PAD 4 px 가 서로의 넘침을 막은 모서리는 아무도 안 그림 | 오리는 이미지는 상자째로만 막음(여유 0 — 넘침끼리는 H3 넘침 장부가 가름), 글자 · 게이지 · 생성 이미지는 여유째 |
  | (위 고침 뒤 시험 run `114906` 에서) '돌진 공격' 오른쪽 ㄴ자 · '점프' 오른쪽 막대 구멍 | 띠가 겹친 자리 픽셀을 엠블럼 몫으로 넘겼는데 엠블럼은 그 자리를 남의 글자 구멍(걸친 획 넓히기로 상자보다 66 px 까지 넓음)으로 지움 — 판정이 뒤에 지워질 자리를 모름 | 글자 '주인'(글자 상자와 가장 많이 겹치는 오리는 위젯)은 그 글자 둘레(가로 높이 × 1.5 · 세로 8 px, 주인 상자 안)의 겹친 자리 픽셀을 넘기지 않음(`_own_text_zone`) — 주인은 하나라 양쪽이 같이 갖지 않음 |
  | '(' 자국(띠 텍스처에 첫 획 일부) | 이웃 몫 판정 탓으로 글자 구멍 밖에 남은 획 | 위 겹친 자리 고침 뒤 사라짐(오프라인 확인) |
  | 판 둘레 차에 알파 수준 차가 섞임(공격 띠 20.9, 물러남 기준 24) | 판이 반투명 띠를 더 불투명하게 그림 | 정합 차를 잴 때 판 알파를 둘레의 컨셉 수준으로 먼저 맞춤(`notext.alpha_level`) → 19.2 → 16.8 · 돌진 19.1 → 17.8(나머지는 색 차) |

  오프라인 확인(같은 analyze spec · 텍스처로 refine 만 — 세 배치 `095249` · `112216` · `114906`): 회색 ΔE00 평균 0.16 ~ 0.17 · 알파 MAE 0.003 · 구멍 0(마지막 배치는 띠 윗변 1 px 줄 하나).
- **끝 run [실측 — `report.recorded.backdrop`]:** 조작 안내 시험 run `112216`(통과 3 — 검은 네모 발견) · `113744`(통과 4 — '회피' 0.62 · '어빌리티' 굵게 오판 발견 → 렌더 마스크는 못 믿을 때만) · `114906`(통과 4 — ㄴ자 · 막대 구멍 발견 → 글자 주인 둘레). **최종 `R20261117_120813_ProbeControlGuide` 무인 통과(5)** — 회색 ΔE00 0.21 · p95 1.09 · 알파 MAE 0.003 · 컨셉에 없는 절벽 0 · 어둡고 불투명 0.37 ↔ 컨셉 0.36, 구멍 · 이중 없음, 라벨 크기 '어빌리티' 41 · '회피' 41 · '점프' 42 · '공격' 42 · '링크 어택' 42 · 키 E · T · R 높이 비 1.0(사람 눈용 `/Game/_AutoGen/R20261117_120813_ProbeControlGuide/WBP_ProbeControlGuide`, 비교 그림 work `assets/compare/backdrop.png`). '돌진 공격' 은 이 run 에서 측정이 상자 끝에 닿아 38(조금 작음 — 기록). 단색 전투 HUD `112754`(통과 5) · `114328`(통과 6) · **최종 `R20261117_121432_CombatHUD` 통과(4)** — 회색 ΔE00 3.0(H3 6.8 — 남은 차는 글자 빛 · force_visible 숨은 빛, 정답은 언믹싱 추정) · 컨셉에 없는 절벽 23. LLM 약 5.2 USD 환산(run 8) · codex 0, 구독 — 과금 아님.
- **뒤로 남긴 것(범위 밖 — 사용자 결정):** 마름모 런타임 스킬 아이콘 방식((가) 회전 · (나) 실루엣 비움 · (다) 마스크 머티리얼) · ⓑ 검정 배경 컨셉의 근본 한계 · 다른 컨셉 적용 검증(뒤 phase). 그 밖 기록: '회피' 가 일부 run 에서 측정 0.62(렌더 획 일부만 잡힘 — 원인 미확정, 신뢰 범위가 걸러 크기 그대로) · 키 배지 'E' 는 렌더 글자 마스크로 측정되는 run 이 생김.
- **증거 정리(11-17 사용자 승인 — 휴지통):** 최종 run 2 개(`R20261117_120813_ProbeControlGuide` · `R20261117_121432_CombatHUD`)와 H3 최종 run 2 개(`095249` · `094643` — H2 ↔ H3 비교 그림 `overview_H3.png`)의 work · `Content/_AutoGen/`, 시험 입력 · codex 기록은 남겼다. 시험 run 5 개(`112216` · `112754` · `113744` · `114328` · `114906`)의 work(약 190 MB) · `Content/_AutoGen/` 과 스크래치 `uigenH4`(220 MB) · `uigenH2b`(H2 세션 것) 는 휴지통.
- **시험:** pytest **319**(H3 316 → +3 · 기존 시험 보강: 다른 영역 글자 보호 · 겹친 자리 양쪽 같은 답 · 렌더 글자 마스크). **1b 후속 H 계열(H · H2 · H3 · 마무리) 종료.**

**1b 후속 I — 겹친 자리를 물체 단위로 · 'UI 만 · 진짜 알파' 자동 변환 (11-17, 미커밋 — 새 세션. 시작 질문 4개 사용자 전부 추천안: ① 순서 = 과제 1(오프라인 도구 → 4 배치 기준 → 고침 → 4 배치 비교) → 과제 2 → 끝 run 3개 하나씩 ② 겹친 자리 = 양쪽 몸통에서 채워 가르기 ③ 자동 변환 = ⓒ 만 기본(ⓑ 는 force) ④ 변환 결과는 사람 눈 확인 없이 무인 + 자동 검사. C++ · Config 변경 없음)**

- **과제 1 결함 [실측 — H 마무리 최종 run `R20261117_120813`]:** 엠블럼(`center_ornament`) 텍스처가 왼쪽 배너 3개의 끝 약 260 px(뾰족한 끝 · 문양 · 고리)와 어빌리티 띠의 T 배지 · '어' 첫 획 조각까지 갖고, 배너 텍스처는 엠블럼 상자 왼쪽 끝(x 540)에서 잘린 채 소용돌이 조각이 붙었다. 합쳐 그리면 서로 빈 곳을 메워 회색 바탕에선 거의 같아 보였다. 원인 = H2 · 마무리의 '겹친 자리(O) 불투명 덩어리는 두 상자 합친 영역 · O 둘레 24 px 에서 어느 쪽이 많은가' + '반투명은 작은 상자 몫' + '글자 주인 둘레 사각형은 넘기지 않음'(계단).
- **오프라인 재실행 도구(`Tools/uigen/replay_refine.py` — 사용자 결정으로 남김, 11-17):** run 폴더에서 refine 직전 spec(`specs/000.json` — 최종 spec 은 글자 맞춤으로 글자 상자가 바뀌어 다른 결과)과 analyze · normalize 산출물만 복사해 `refine.run` 만 다시 → spec bbox_intent 상자로 `backdrop.compose`(회색) → 회색 ΔE00 · 알파 MAE · 컨셉에 없는 절벽 · 구멍(컨셉 알파 − 덮임 > 0.25, 20 px 넘는 덩어리) · 이중(덮임 − 컨셉 > 0.15) + 그림 3(컨셉 | 합성 | 차이 · 오리는 텍스처마다 혼자 · 소유 지도). 4 배치 = 조작 안내 `120813` · `095249`, 단색 전투 HUD `094643` · `121432`.
- **고침 — 소유 지도 `refine.cut_ownership`(run 에서 한 번, 모든 오리는 위젯이 같은 지도):**
  - 겨루는 자리 = 오리는 위젯(작은 아이콘 · 넘침 장식 제외) 상자가 일부만 겹친 곳(포함 관계 0.9 는 겨루지 않음 — 띠 위 배지 · 엠블럼 속 다이아몬드) + 넘칠 수 있는 위젯(넘침 막는 이유 없음)의 상자 둘레 8 px 중 상대 상자 안 + 어느 상자에도 안 속한 빈 자리 중 그 둘레. 후보 = 픽셀을 (넓힌) 상자에 품은 위젯.
  - 물체 속 = 알파 > 0.5 · 알파 기울기(소벨 / 8) ≤ 0.006. 물체 속 픽셀은 **가장 넓은 길**: 위젯마다 씨앗(겨루지 않는 자기 상자 쪽 물체 속 — 포함 관계면 바깥 상자)에서 그 픽셀까지 '길의 가장 가는 곳(거리 변환 최솟값)'의 최댓값을 구하고(최대 병목 다익스트라), 가장 큰 값의 1/1.25 안이면 동점 → 작은 상자(더 구체적인 요소). 물체 속이 아닌 픽셀(경계 · 반투명 · 떨어진 조각) = 4 px 안 물체 속 주인 → 48 px 안 가장 가까운 자기 픽셀 주인 → 작은 상자.
  - `_cut_entry`: 남의 몫은 그리지 않고(메우기 뒤에도 투명) 넘침으로도 안 가져가며, 둘레로 받은 내 몫은 넘침 최소 폭(4 px)과 상관없이 그린다. `_drop_neighbour_pixels` · `_neighbour_cut_boxes` · `_own_text_zone` 없앰. `_drop_covered_below`(위 z 텍스처가 아래 영역 글자를 가림) · 작은 아이콘 실루엣은 그대로.
  - 글자 구멍 '요소 밖 = 투명'(`cutout.compose` · ⓐ ⓑ): 글자 없는 판이 있으면 판 알파가 정답이라 판으로 메운 글자 구멍은 비우지 않고, 같은 줄(또는 열)에서 구멍 구간 양 끝 바로 바깥이 요소 픽셀이면 요소 안(`cutout._bridged`).
- **오프라인에서 거친 판(같은 4 배치) [실측]:**

  | 판 | 결과 · 원인 |
  | :--- | :--- |
  | 알파 > 0.75 + 표준 watershed(깊은 곳부터 채우기) | 배너가 엠블럼 상자 경계에서 그대로 끊김 — 배너 띠가 배너 상자 위아래로 2 ~ 5 px 삐져나온 자리(엠블럼 상자 안 = 엠블럼 씨앗)에서 엠블럼이 띠 속으로 흘러내림(씨앗이 비탈) |
  | 알파 > 0.75 + 가장 넓은 길(동점 = 씨앗 깊이) | 그대로 — 배너 사이 엠블럼 바탕(알파 0.84 ~ 0.95)도 '불투명'이라 띠 · 바탕 · 다음 띠가 한 덩어리(띠 가운데 거리 72). 어빌리티 띠는 0.85 ~ 0.94 라 문턱을 올려도 못 가름 |
  | 물체 속 = 알파 기울기 ≤ 0.03 | 그대로 — 띠 ↔ 바탕 알파가 약 10 px 에 걸쳐 완만(기울기 최대 0.021) |
  | 기울기 ≤ 0.006 | 돌진 · 공격 · 링크 배너가 끝 · 문양을 혼자 가짐. 점프 띠는 위쪽 반이 엠블럼 — 띠 끝이 엠블럼 몸통과 목 없이 두껍게 붙어 병목이 같고(17 = 17) 동점을 씨앗 깊이(엠블럼 99.6)로 가름 · 배너 위아래 테두리 줄(상자 밖)이 엠블럼 |
  | 동점 = 작은 상자 + 넘칠 수 있는 위젯 둘레 8 px 겨루기 · 둘레 내 몫 넘침 강제 + 빈 자리 둘레도 지도(엠블럼 넘침이 상자 왼쪽 빈 자리의 배너 테두리 줄을 먼저 가져감) | 배너 4 개 모두 끝 · 끝 장식을 혼자, 엠블럼은 자기 몸통만 |
  | 위젯마다 넓은 길 값 + 25 % 동점(시험에서 같은 두께 길이 씨앗 자리에 따라 43.0 · 43.4 로 갈려 소수점이 주인을 정함) | 최종 — 위와 같은 그림 · 지표 |

  최종 지표(기준 = 지금 코드 전 → 고친 뒤): 조작 안내 `120813` 회색 ΔE00 0.168 → **0.157** · 알파 MAE 0.0029 → 0.0025 · 구멍 0 → 0 · 이중 174 → 27 px, `095249` 0.157 → **0.127** · 0.0033 → 0.0024 · 구멍 144 → 0 · 이중 246 → 111 px, 단색 전투 HUD 2 배치 = 변화 없음(겨루는 상자 쌍 없음 — 이중 4.5 천 · 5.3 천 px 은 force_visible 숨은 빛). 최종 spec 의 큰 글자 상자로 refine 을 다시 돌린 조건(처음에 우연히 드러난 결함 — 회피 띠 가운데 270 px 가 윤곽 밖으로 비워짐)도 구멍 8,547 → 0 px. (오프라인 그림은 스크래치째 지웠다 — `replay_refine.py` 로 다시 만들 수 있다.)
- **과제 2 — 'UI 만 · 진짜 알파' 자동 변환(`gen/concept_convert` · normalize):** H 에서 사람이 `make_concept.py --edit <스크린샷> --transparent` + `--text-free` 로 하던 것을 normalize 안에서. inputs `concept_convert: auto | force | off`(없으면 `pipeline.yaml concept_convert.default: auto`) — auto = ⓒ scene 만 · force = ⓑ flat 도 · ⓐ 는 안 함. codex 편집 2 회: ① 원본 → UI 만 · 진짜 알파 컨셉(프롬프트 = 화면 종류 머리말 + '보이는 상태 그대로 — 없는 요소 · 빛 · 글자를 더하지 말 것' + inputs text · required_elements(알아보기용 이름) · static_text(보이면 그대로) + `make_concept.TRANSPARENT_EDIT_RULES`) ② 그 컨셉 → 글자 없는 판(`TEXT_FREE_PROMPT` + 알파 유지). 검사 = 알파 채널 · 투명 비율 0.05 ~ 0.95 · 원본과 비율 차 ≤ 3 %(판은 변환 컨셉과). 캐시 `work/_convert/<원본 sha256 앞 16>_<프롬프트 sha256 앞 8>/`(`convert.json` — 다시 돌리면 codex 0, 검사 탈락도 남김 · codex 오류 · 한도는 안 남김). 상한 run 당 2(run 전체 장부 `codex_calls.jsonl` 에도 셈). 물러날 길: 컨셉 실패 · 탈락 = 원본 그대로(예전 ⓒ 경로 — run 은 계속), 판만 실패 = ⓐ 로 가되 판 없이. 변환이 쓰이면 inputs `concept_notext`(원본용)는 무시. 출처 = `normalize.json background.convert` · `original_concept` · run 폴더 `convert/`(사본 · 호출 기록 · `convert.json`) · `report.recorded.concept_convert` · `artifacts.concept_convert`. 시험은 기본 off(conftest — 실제 codex 금지).
- **끝 run [실측 — `report.recorded.backdrop` · `concept_convert`]:**

  | 입력 | run | 결과 | 변환 | 회색 ΔE00 평균 · p95 · 알파 MAE · 컨셉에 없는 절벽 | LLM(API 정가 환산) |
  | :--- | :--- | :--- | :--- | :--- | :--- |
  | 원래 전투 HUD(장면 합성 `fixtures/m4_combat_hud_concept` — 1b ~ G2 기준) | `R20261117_134535_CombatHUD` | 무인 통과(5 — 시도 2 에 10/10, 외형 라운드 받음 · 글자 맞춤 2 판) · 5분 27초 | codex 2(컨셉 48초 · 판 34초) → 1672 × 941 투명 89 % · 비율 차 0, 판 정합 (0.51, 0.46) px · 생성 단계 codex 0(오리기 3 · procedural 2) | 6.0 · 32.2 · 0.015 · 0 — 남은 차는 force_visible 숨은 '가득 빛'(게이지 빈 트랙) · 글자 빛(글자 상자 밖), 실제 상태 렌더는 컨셉과 같음 | 0.276(analyze) + 라운드 |
  | 조작 안내 원본 스크린샷(`work/_probe/controls` — 807 × 353 합성) | `R20261117_135206_ProbeControlGuide` | 무인 통과(3 — 시도 1 에 10/10, 외형 라운드 op 없음) · 5분 14초 | codex 2 → 1898 × 829 투명 44 % · 비율 차 0.0015, 판 정합 (−2.88, −0.56) px · 생성 단계 codex 0(오리기 14) | **0.24 · 1.33 · 0.0033 · 0** — H 마무리 최종(손 변환 `120813` 0.21 · 1.09 · 0.003 · 0)과 같은 수준. 텍스처 단독: 배너가 끝 · 끝 장식 · 문양을 혼자, 엠블럼 텍스처엔 엠블럼만 | 0.228(analyze) + 라운드 |
  | 회귀 — 손 변환 투명 컨셉(`work/_probe/controls_alpha`, ⓐ — 변환 안 함 '이미 진짜 알파') | `R20261117_135820_ProbeControlGuide` | 무인 통과(4 — 시도 1 에 10/10, 외형 라운드 받음) · 5분 23초 | — | **0.14 · 0.87 · 0.0025 · 0** — H 마무리 최종 `120813`(0.21 · 1.09 · 0.003 · 0)보다 나음 | 0.241(analyze) + 라운드 |

  LLM 합계(세 run, API 정가 환산 — 구독 · 과금 아님) 약 2.8 USD(전투 HUD 1.18 · 조작 안내 0.68 · 회귀 0.90), codex 4(변환 2 run × 2). 사람 눈용 WBP = `/Game/_AutoGen/R20261117_134535_CombatHUD/WBP_CombatHUD` · `R20261117_135206_ProbeControlGuide/WBP_ProbeControlGuide` · `R20261117_135820_ProbeControlGuide/WBP_ProbeControlGuide`, 변환 그림 = run 폴더 `convert/concept.png` · `concept_notext.png`, 회색 합성 = `assets/compare/backdrop.png`.
- **뒤로 남긴 것(범위 밖 — 손대지 않음, 기록만):** 게이지 빈 트랙이 오른쪽 끝 장식을 덮음 · '오의 불가' 뒤 어두운 상자 · 마름모 런타임 스킬 아이콘 방식 · '돌진 공격' · '회피' 글자 측정이 run 에 따라 건너뜀(이번 조작 안내 원본 run 도 '돌진 공격' 0.569 · '점프' 0.469 로 위치 판 건너뜀 — 크기 판 몫) · 성격이 다른 컨셉 시험 묶음(다음 권장). 이번에 새로 본 것: 자동 변환은 codex 가 구도를 조금 옮겨 그릴 수 있다(세로 59 px — 파이프라인은 변환 컨셉을 기준으로 삼아 문제 없음, 원본 좌표가 필요해지면 정합 단계 필요) · 프롬프트가 inputs 설명뿐이라 원본의 옅은 장식(엠블럼 뒤 소용돌이)이 덜 나올 수 있다 · 분석 쪽 화면 설명이 장식을 적으면 그대로 쓰인다.

  손 변환(`work/_probe/controls_alpha`) ↔ 자동 변환 컨셉 [스크래치 비교 스크립트 — 위상 상관으로 이동을 맞춘 뒤 알파 > 0.5 실루엣 IoU · 알파 MAE · 둘 다 보이는 자리 색 ΔE00]: 요소 · 구도 · 글자 같음, 자동 쪽이 그림 안에서 세로 59 px 아래(codex 가 구도를 조금 옮겨 그림) — 이동을 맞추면 실루엣 IoU 0.874 · 알파 MAE 0.045 · 색 ΔE00 중앙값 3.8, 엠블럼 뒤 어두운 소용돌이가 옅음(보이는 픽셀 46 % ↔ 41 % — 손 프롬프트는 소용돌이를 직접 적었고 자동 프롬프트는 inputs 설명뿐).
- **증거 정리(11-17 사용자 승인 — '도구는 남기고 휴지통'):** 끝 run 3 개(`R20261117_134535_CombatHUD` · `R20261117_135206_ProbeControlGuide` · `R20261117_135820_ProbeControlGuide`)의 work · `Content/_AutoGen/` 과 변환 캐시 `work/_convert`(3.4 MB — 다시 돌리면 codex 0)는 남겼다. 오프라인 재실행 도구는 `Tools/uigen/replay_refine.py` 로 옮겨 남기고(같은 배치로 같은 숫자 확인), 스크래치 `uigenI`(287 MB — 4 배치 재실행 사본 · 비교 그림 · 비교 스크립트)는 휴지통. H 계열 최종 run 4 개(`095249` · `094643` · `120813` · `121432`)는 그대로.
- **I 후속 — 확대 절취선 · 반투명 소용돌이(11-17, 사용자 사람 눈 — 회귀 run `R20261117_135820` 의 엠블럼 텍스처가 배너 상자 끝에서 직선으로 잘림 · 디자이너 확대 때 텍스처 경계를 따라 검은 '절취선'. 사용자 '여기서 고침'):**
  - 원인 [실측]: 1920 × 1080 렌더(텍스처 = 상자 1:1)에선 경계 픽셀 밝기가 컨셉과 같다(1.001). 디자이너 확대 · 1:1 이 아닌 해상도에서 엔진이 텍스처를 따로따로 늘리면(곧은 알파 이중선형) 겹침 없이 나눈 경계에서 두 텍스처 가장자리가 같이 옅어지고(덮임 약 75 %) 투명 픽셀 색 (0, 0, 0)이 섞여 바탕이 가는 선으로 비친다. 한 장짜리 컨셉(레이어 없음)을 칠 한가운데에서 자르는 방식의 성질 — 레이어 원본이면 아래 레이어가 위 요소 밑까지 이어져 생기지 않는다. 직선 잘림은 배너 끝 둘레 소용돌이(알파 0.16 ~ 0.45)가 '가장 가까운 자기 픽셀' 규칙으로 바로 옆 배너 끝 몸통에 간 탓(엠블럼이 잃은 13.3 만 px 중 1.8 만 px 가 반투명).
  - 고침: ① `cutout.bleed_transparent_rgb`(`to_image`) — 알파 0 픽셀 색을 가장 가까운 보이는 색으로(알파 그대로 — 1:1 같음, OCR 은 회색 바탕 합성이라 무관) ② `refine._opaque_bleed` — 남의 몫 중 내 보이는 픽셀 2 px 안 · 컨셉 알파 ≥ 0.97 은 같이 그림(불투명 위 같은 불투명 — 1:1 덮임 차 ≤ 0.03, 반투명은 두 번 쌓여 안 함) ③ 소유 지도에서 물체 속이 아닌 픽셀은 4 px 안 물체 속 주인 → **겨루지 않는 자기 반투명 픽셀이 가까운 쪽** → 가장 가까운 자기 픽셀 → 작은 상자.
  - 확대 모사 지표 `replay_refine.zoom_seams`(3 배 · Slate 처럼 상자 밖은 안 그리고 가장자리는 텍셀 고정 · 배율 텍스처는 늘려 그림 · 두 텍스처 이상이 2 px 안에 맞닿는 경계만 · 글자 상자 밖): 컨셉 한 장 확대보다 20 넘게 어두운 픽셀 — 조작 안내 `120813` 7,091 → **1,341** · `095249` 7,445 → **804** · 원본 변환 `135206` 7,383 → 3,186(남은 것은 키 배지 테두리 · 2 배 다이아몬드를 줄여 그린 아이콘 가장자리의 판 차이 — 절취선 아님, 그림 확인), 최대 어두움 133 ~ 137 → 61 ~ 71. 1:1 회색 ΔE00 은 불투명 겹침으로 0.157 → 0.165 · 0.127 → 0.134(구멍 0 · 이중 그대로). 처음 모사(텍스처 바깥을 투명 검정으로 샘플링)는 아이콘 상자마다 가짜 네모 테두리를 그려 고쳤다.
  - 확인 끝 run: 조작 안내 원본 `R20261117_154442_ProbeControlGuide` 무인 통과(4 — 시도 1 에 10/10, 외형 라운드 받음) · 변환은 캐시라 codex 0 · 회색 ΔE00 0.26 · p95 1.23 · 알파 MAE 0.0035 · 절벽 0(I 끝 run `135206` 0.24 · 1.33 · 0.0033 · 0). 실제 run 텍스처의 확대 절취선 7,778 → 4,562 px — 남은 다섯 자리는 모두 키 배지(E · T · R) 테두리(글자 없는 판에서 온 배지 테두리 밝기 차 — 고치기 전 숫자에도 있던 것), 처음 지적한 돌진 배너 끝 자리의 세로 · 가로 절취선은 3 배 확대 그림에서 사라짐(그림 work `seam_fix_run_zoom3x.png` — 컨셉 | 고치기 전 run | 고친 뒤 run).
  - 시험 pytest **328**(+2: 반투명 소용돌이 주인 · 불투명 겹침 + 투명 색 채우기).
- **시험:** pytest **326**(319 → +7: 소유 지도 2 · 구멍 가로지름 1 · 변환 5 — 캐시 · 탈락 · 한도 · 상한 · normalize 연결, 예전 겹친 자리 시험 2 개는 새 규칙으로 바꿈, 가짜 codex `opaque` 모드). C++ · Config 변경 없음 → 빌드 · 에디터 회귀 없음.

**1b 후속 J 설계 — 기능 단위로 쪼개기 · 자동 차이 진단 (11-17 작성 · 사용자 '함께 설계' — 결정 4개 전부 추천안: ① 정적 판 2048 한 장(넘으면 투명한 틈에서 나눔) ② 진단은 처음부터 게이트 ③ LLM 외형 라운드는 글자 스타일 op 금지 ④ 순서 J-b → J-a → J-c(요소 없는 판이 글자 없는 판 호출 대체). 구현 전)**

왜(사용자 질문 '1b 고치기만 9번째 — 뭐가 문제냐'에 대한 답): 개별 버그가 아니라 접근 방식. ① **쪼갤 필요 없는 것까지 쪼갬** — 조작 안내는 런타임에 바뀌는 그림이 0(바인딩 0)인데 텍스처 14 장으로 나눴고, 한 장으로 칠한 그림을 겹치게 나누면 '이 픽셀은 누구 것'에 정답이 없다. H 이후 고친 결함 대부분(이중 · 'T' 가림 · ㄴ자 구멍 · 계단 · 배너 끝 넘어감 · 절취선 · 직선 잘림 · 배지 양옆 선)이 이 겹친 경계에서 났고, 겹치는 장식이 없는 전투 HUD 는 H 이후 거의 안정. ② **규칙끼리 얽힘** — 소유 지도 × 글자 구멍 × 판 정합 × 넘침 × 장부 × 아이콘 실루엣이 서로의 입력을 바꿔 하나 고치면 다른 데가 깨졌고, 기준값은 한 컨셉에 맞췄다. ③ **검증이 사람 눈과 다름** — 게이트는 상자, 지표는 1:1 합성의 평균 색이라 매번 '통과' 뒤 사람이 새 결함을 찾았다. [실측 — `R20261117_154442`] 렌더 ↔ 컨셉 평균 ΔE00 0.54 인데 7 × 7 창 국소 차이 지도의 상위 자리는 사용자가 찾은 결함 그대로(E · T 배지 양옆 · '돌진 공격' 10.5 px 어긋남 — 최대 ΔE00 55). ④ **무작위 입력 위에 결정적 규칙** — codex 판 · 변환이 매번 몇 px 다르게 그리고(배지 원판 3 px), analyze 상자 · LLM 외형 라운드가 run 마다 다르다(남색 외곽선 추가).

원칙: **텍스처를 나누는 기준 = 런타임 기능.** 보이는 요소마다 나누지 않는다. **합격 = 레퍼런스와의 국소 차이가 없음**(평균이 아니라 자리마다, 여러 배율에서), 결함이 남으면 어느 단계 탓인지 리포트가 짚는다.

- **J-a 기능 단위 레이어(analyze 뒤 결정적 단계 — LLM 판단에 맡기지 않음):**
  - 기능 요소 = 런타임에 따로 그려야 하는 것: inputs `data` 바인딩(글자 · 숫자 · 게이지 · 런타임 이미지) · flag(켜고 끔 — 패널 · 배너 · 빛) · 버튼 · 크기가 변하는 9-slice 패널, 그리고 inputs 새 `separate`(사람이 따로 두고 싶은 요소 id — 나중에 애니메이션 등). 고정 글자는 지금처럼 엔진 TextBlock(현지화).
  - 그 밖의 오리는 정적 요소(장식 · 배너 · 고정 아이콘 · 키 배지 원판)는 **정적 판 한 장**으로 굽는다 — 보이는 정적 픽셀을 2 px 넓혀 이은 덩어리마다 텍스처 하나(투명한 틈에서만 나뉘므로 공유 픽셀 · 경계 없음), 크기 상한 2048(analyze 에셋 1024 상한과 별개 — 조작 안내 덩어리 약 1830 × 620). 그리는 순서는 영역 맨 아래, 기능 요소 · 글자는 위.
  - **요소 없는 판**(지금 글자 없는 판을 넓힘): codex 편집 1 회로 '글자 + 기능 요소(설명 목록)를 지우고 그 뒤를 이어 그린' 판 — 호출 수는 지금과 같음, 캐시는 변환과 같은 방식. 정적 판 = 컨셉 픽셀, 단 기능 요소 · 글자 자리만 요소 없는 판 픽셀(요소마다 ±6 px 재정합은 지금 그대로). 기능 요소 텍스처 = 컨셉 픽셀, 모양(알파) = 컨셉 ↔ 요소 없는 판 차이(+ 그 위젯 상자) — 사용자 제안 '컨셉 − 판'. 기능 요소는 정적 판 위에 그려지고 아래는 '요소 없는' 그림이라, 숨겨도 구멍이 없고 겹친 경계 · 절취선이 원리상 없다(아래 레이어가 이어짐).
  - 지금 규칙의 자리: 소유 지도 · 넘침 · 장부 · 작은 아이콘 실루엣은 **기능 요소끼리 겹칠 때만** 남는다(드묾). 게이지 트랙 메우기(`unfilled_track`)는 그대로.
  - 예상 결과: 조작 안내 = 정적 판 1 + 글자 9(오늘 결함 — 엠블럼 직선 잘림 · 배지 양옆 선 · 다이아몬드 네모 · 절취선 — 이 생길 자리가 없음). 전투 HUD = 게이지 프레임은 정적 판, 체인 패널 · 버스트 배너 · 가득 빛은 flag 라 기능 요소(지금과 거의 같음). 파티 HUD = 초상화(런타임 이미지) · 게이지 4 · 글자 · 나머지 장식은 정적 판.
- **J-b 자동 차이 진단(verify 의 새 게이트 `appearance` + 리포트):**
  - 비교 셋: 레퍼런스(변환 컨셉) ↔ 렌더(force_visible, 1:1) · 레퍼런스 3 배 ↔ 텍스처를 Slate 처럼 3 배로 그린 합성(`replay_refine.zoom_seams` 를 파이프라인으로) · 글자 상자는 따로 — 렌더 글자 ↔ 컨셉 글자를 그림으로 맞대(크기 · 위치 · 굵기 · 외곽선 · 색, 측정값이 아니라 획 마스크끼리 — 컨셉 획 = 글자색 쪽 핵심 획만, 빛 번짐 제외).
  - 국소 결함 = 7 × 7 창 평균 ΔE00 > T 인 자리 덩어리(넓이 ≥ A) — 위치 · 넓이 · 최대값 · 그 자리 위젯 · 텍스처 이름.
  - **원인 단계 짚기**(결함마다, 차이가 처음 생긴 단계): 텍스처를 1:1 로 합친 그림에도 있으면 → 텍스처 단계(그 자리 텍스처 · 판 정합 이동 · 글자 구멍 · 요소 모양), 합성엔 없고 렌더에만 있으면 → 배치 · 엔진(위치 어긋남 = 위상 상관 이동, 배율 · 압축), 글자 상자면 → 글자(크기 · 위치 · 굵기 · 외곽선 · 색 중 무엇), 3 배에서만 → 텍스처 경계(절취선), 변환 컨셉 ↔ 원본 비교로 → codex 변환 흔들림(기록). 리포트 `report.recorded.diagnosis` + 번호 붙인 결함 그림.
  - 고침 연결: 원인이 결정적으로 분류된 것만 자동 고침(글자 크기 · 위치 → `text_fit`, 판 정합 → 재정합), 나머지는 고치지 않고 리포트로 실패(NO_FIX) — '통과'는 국소 결함 0 일 때만.
  - **비교로 원리상 못 보는 것**: 텍스처를 어떻게 나눴는지(합친 그림이 같으면 차이 0 — 오늘 엠블럼 직선 잘림은 국소 지도에도 안 잡혔다) → J-a 로 없애고, 남는 기능 요소 경계는 텍스처 단독 검사(위젯 상자 선을 따라가는 직선 알파 잘림)로. 레퍼런스에 안 그려진 상태(숨은 경고 · 가득 찬 게이지)는 비교 정답이 없어 기록만.
- **J-c LLM 외형 라운드 손 묶기:** 글자 스타일(크기 · 굵기 · 외곽선 · 빛 · 색)은 결정적 측정만 쓴다 — style_fix 허용 op 에서 글자 효과를 뺀다(오늘 '남색 외곽선 2 px' 처럼 측정 오판을 키움). 글자 맞춤의 컨셉 획 측정은 '판과 다른 픽셀' 중 글자색에 가까운 핵심 획만(빛 번짐이 획 밀도 · 높이를 부풀려 보통 → 굵게 · 40 → 46 으로 키웠고, '회피' 는 반대로 덜 잡아 38 → 31).
- **순서(제안):** J-b 진단을 먼저(지금 방식의 결함을 숫자 · 자리로 기준선 — 4 배치 + 끝 run) → J-a 기능 단위 레이어 → J-c, 각 단계 끝에 같은 진단으로 전후 비교. 하위 단계로 잘게 나누지 않고 한 묶음으로.
- **끝 조건:** 시험 입력 5 개(조작 안내 원본 · `controls_alpha` · 원래 전투 HUD · 단색 전투 HUD · 파티 HUD) 무인 통과 + 진단 국소 결함 0(문턱은 J-b 에서 지난 최종 run 들로 보정) + 사람 눈. pytest. C++ · Config 변경 없음 예상(정적 판 2048 은 WidgetMcp 임포트가 받는지 J-a 첫 확인).
- **사용자에게 물을 것:** ① 정적 판 크기 상한 2048(한 장) — 넘으면 투명한 틈에서 나눔 ② 진단을 처음부터 게이트(결함 남으면 run 실패 + 리포트)로 — 문턱 보정은 지난 run 들로 ③ LLM 외형 라운드: 글자 스타일 op 금지(영역 외형만 남김) vs 기본 끔 ④ 요소 없는 판 = 글자 없는 판 호출을 대체(codex 호출 수 그대로) ⑤ 순서 J-b → J-a → J-c.

**1b 후속 J 에서 확인 · 정한 것 (11-17, 미커밋 — 새 세션. 설계 결정 4개는 확정된 그대로(정적 판 2048 · 진단 게이트 · 외형 라운드 글자 op 금지 · J-b → J-a → J-c), 하위 단계 없이 한 묶음. C++ · Config 변경 없음)**

- **J-b 자동 차이 진단 — `gen/diagnose.py` · verify 게이트 `appearance`(11 번째):**
  - 비교 셋(ⓐ ⓑ — 레퍼런스 = 곧은 색 × 알파, ⓒ 는 비교 정답이 없어 건너뜀): ① 검정 위 렌더(force_visible 1:1) ↔ 레퍼런스 ② 회색 위 텍스처 합성(`gen/backdrop`) ↔ 레퍼런스(검정이 숨기는 알파 이중 · 구멍) ③ 3 배 확대 절취선(`zoom_seams` — `replay_refine.py` 에서 옮김, 경계 둘레 타일만 계산 · 이미지 브러시가 아닌 그리기(게이지 · 9-slice)가 덮는 자리는 확대 모사에 없어 뺌) ④ 글자 획 맞대기.
  - 국소 결함 = 7 × 7 창 평균 ΔE00 > `local_de`(10) 인 덩어리 넓이 ≥ `min_area`(24) — 글자 자리(자기 상자 ∪ 두 쪽 획 후보 + 4 px + 빛)는 빼고 ④ 로 본다.
  - **레퍼런스에 안 그려진 상태**: 시작 때 숨은 위젯(subtree)마다 '넣은 합성 ↔ 뺀 합성'(글자는 렌더 ↔ 글자 없는 합성) 중 레퍼런스에 가까운 쪽으로 컨셉이 그 상태를 그렸는지 정하고(`hidden_state_split`), 안 그렸으면 그 자리를 그 위젯을 뺀 합성으로 비교(그 자리 다른 글자 픽셀은 렌더 그대로 — 숨은 '가득 빛' 위 '오의 불가' 아래 반이 지워졌던 것) — 전투 HUD 의 `UltReadyGlow` 가 이것(기록 `hidden_states`).
  - **글자(그림끼리, J-c 와 같은 획):** 렌더 획 = 렌더 ↔ 렌더 상태 텍스처 합성 차, 컨셉 획 = 컨셉 ↔ 글자 없는 텍스처 합성 차와 컨셉 ↔ 글자 없는 판 차 중 작은 것(글자는 두 바탕 모두와 다르고, 줄 보간 자리는 판과 같고, codex 판이 다시 그린 배지 테두리는 합성과 같다). 차 > 48 덩어리를 무게중심이 든 구역의 가장 가까운 글자 상자에 배정(겹친 상자 '4.2' 아래 '2/4') → 글자 하나보다 긴 가는 선 열림 연산으로 빼기 · 자기 상자(+ 0.25 h) 밖이 대부분인 덩어리 · 넓이 가중 중앙값 획 두께의 0.45 배도 안 되는 가는 덩어리(배지 테두리 호) · 가로 틈이 글자 높이 0.6 배 넘게 떨어진 묶음 빼기 → **핵심 획 = 주변 9 px 안 최대 차의 0.55 이상**(빛 번짐 · 그림자 · 안티앨리어싱은 바로 옆 획보다 차가 작다 — 전체 p90 기준은 빛 위 글자 아래 반을 지웠고, 밝기 반 가르기는 그라데이션 금색 글자 아래 반을 지웠다). 획 상자 = 픽셀 좌표 1 ~ 99 백분위. 결함: 높이 비 |1 − 비| > 0.08 · 중심 차 > max(3 px, 0.1 h) · 획 밀도 비 밖 [1/1.22, 1.22] · 대표색 ΔE00 > 12 · 획 안 '바탕보다 어두운' 비율 차 > 0.2(외곽선 · 그림자) · 핵심 밖 '바탕보다 밝은' 비율 차 > 0.2(빛). 크기 · 위치 · 굵기만 `fixable`(글자 맞춤).
  - **원인 단계:** 결함 덩어리가 1:1 텍스처 합성(검정)에서도 0.7 T 넘으면(또는 회색 지도에서만) '텍스처' — 그 자리 맨 위 위젯(`backdrop.compose(owners=True)`) · 알파 차 부호로 이중 / 구멍 / 빠짐(아무 텍스처도 안 그림) / 색(글자 구멍 메움 근처인지), 아니면 위상 상관 이동 ≥ 1 px 이면 '배치', 아니면 '엔진'(그리기 · 압축). 3 배에서만 = '경계'(그 자리 위젯). 변환 컨셉 ↔ 원본 이동은 기록(`conversion`).
  - 출력: `attempts/NNN/diagnosis/`(`diagnosis.json` · 번호 붙인 `defects.png` — 레퍼런스 | 렌더 | 국소 지도, 단계별 색 · `defects_sheet.png` — 결함마다 레퍼런스 | 렌더 | 합성 확대) · run 폴더 `diagnosis.json`(마지막 verify) · `report.recorded.diagnosis` · `artifacts.diagnosis`.
  - **오케스트레이터:** 재시도 · fix 는 구조 게이트(10 개)만 본다(`verify.structural_failed` — appearance 는 fixer 몫이 아님). 구조가 통과하면 외형 라운드 · 글자 맞춤을 돌고 **run 합격 = 마지막 verify 의 appearance 통과**(아니면 `stop: APPEARANCE` + 메시지에 결함 · 원인). 외형 라운드 · 글자 맞춤 판은 '구조 통과 + 진단이 나빠지지 않음'(결함 수가 줄거나, 같으면 나쁨 정도 `badness` 가 2 % 넘게 늘지 않음)일 때만 받는다(`_round_ok` — 예전 '게이트 전부 통과'). 되돌림 뒤 재빌드는 구조 통과면 된다.
  - **기준선 [실측 — 지난 최종 run 8 개, 지금 방식(J-a 전)]:**

    | run | 결함(단계별) | 텍스처 원인 | 글자 원인 | 3 배 어두운 확대 px |
    | :--- | :--- | :--- | :--- | :--- |
    | 조작 안내 `154442`(사용자가 결함 찾은 run) | 26(텍스처 9 · 경계 10 · 글자 7) | 색 7(E · T · R 배지 양옆 — 글자 구멍 메움 근처) · 이중 2(다이아몬드) | '돌진 공격' 크기 · 위치 24.5 px · 굵기 · 외곽선 / '공격' · '점프' 크기 · 굵기 · 외곽선 / '회피' 0.75 / '어빌리티' 굵기 / '링크 어택' 외곽선 / 'R' 0.81 | 4,562 |
    | 조작 안내 `120813` | 29(경계 24 · 글자 5) | — | 외곽선 5(analyze 남색 1 px) · '돌진 공격' 위치 18.5 | 22,393 |
    | 조작 안내 `095249` | 4(경계 3 · 글자 1) | — | '어빌리티' 0.83 · 굵기 · 외곽선 | 1,742 |
    | 조작 안내 원본 변환 `135206` | 30(텍스처 9 · 경계 16 · 글자 5) | 구멍 1 · 색 5 · 이중 3 | 크기 3 · 굵기 1 · 외곽선 1 | 7,778 |
    | 회귀 `135820` | 12(경계 9 · 글자 3) | — | 크기 2 · 외곽선 1 | 8,177 |
    | 원래 전투 HUD `134535` | 8(텍스처 7 · 글자 1) | 색 7 — 게이지 채움 끝이 컨셉보다 약 25 px 짧음(최대 80.8) · 채움 결 평평(10 ~ 22) · 왼쪽 끝 어두운 초승달 | '2/4' 굵기 | 0 |
    | 단색 전투 HUD `094643` · `121432` | 4 · 8 | 색 1 · 4, 이중 1(게이지) | '체인 버스트' 크기 · 위치(배너 장식 끝이 글자 구멍 줄 보간에 지워짐) · '2/4' · '오의 불가' 빛 | 0 |

    파티 HUD 는 지난 run(G2 `155358`)이 ⓒ 장면 컨셉이라 비교 불가(건너뜀). 사용자가 사람 눈으로 찾았던 결함(배지 양옆 · 다이아몬드 네모 · '돌진 공격' 어긋남 · 왼쪽 라벨 굵게 + 남색 외곽선 · '회피' 작아짐 · '어빌리티' 작음)이 전부 숫자 · 자리로 잡힌다. 측정 다듬기 중 거친 판(기록): 렌더 획이 엔진 외곽선까지 품어 둘레 띠 ΔE 로는 외곽선이 안 보임 → 획 안 어두운 비율 · 가는 선 규칙(두께만)은 작은 렌더 '회피' 세로획(ㅣ 2 px)까지 지움 → 글자 상자에 견준 길이 · codex 판만 바탕으로 쓰면 배지 테두리 호, 합성만 쓰면 줄 보간 자리가 획으로.
- **J-a 기능 단위 레이어 — 새 결정적 단계 `stages/layer.py`(analyze 뒤, ⓐ ⓑ 만):** 기능 요소 = 바인딩(글자 · 숫자 · 게이지 · 런타임 이미지 · flag) · 시작 때 숨은 위젯 · flag · 숨김 · 버튼 · separate 의 subtree(같이 접힘) · 버튼 · 크기가 변하는 9-slice · 크기 고정이 아닌 영역 안 · inputs 새 `separate`(스키마 추가). 정적 장식(그 밖의 extract 브러시 위젯) → 브러시 `{draw_as: none}`(위젯은 자리 · 필수 요소로 남음) · 안 쓰이는 extract 에셋은 spec 에서 뺌. **정적 판** = 컨셉 보이는 픽셀(알파 > 0.02) − 오리는 기능 요소 상자 − 런타임 이미지 상자를, 픽셀이 속한 영역(상자 안, 아니면 가장 가까운 상자 — 크기 고정 영역만)의 앵커 묶음마다 2 px 넓혀 이은 덩어리로 → 덩어리마다 에셋 `static_plate<n>`(kind ornament · provenance provided · source_mode plate — 스키마 추가) · 캔버스 직속 Image `StaticPlate<n>`(그 영역 앵커 · 정렬 · 루트 자식 맨 앞 · 가장 작은 z · 겹침 허용 쌍). 글자 상자 안에만 있는 덩어리(투명 위 글자)와 24 px 미만 잡티는 판이 아니다. 판 마스크 `layer/plate_<n>.png` · 기록 `layer.json`(기능 요소 이유 · 정적 위젯 · 판 · 뺀 에셋). generate 는 판을 codex 없이 기록용 조각만(backend `concept_plate`), refine 이 판 텍스처를 굽는다(`_plate_entry`): 컨셉 곧은 색 · 판 마스크 알파 → 판 위 게이지 트랙은 `unfilled_track`(채움이 컨셉 모양) · 아니면 막대 상자를 판으로 → **글자 자리는 '판과 다른 글자 획'만 글자 없는 판 픽셀로**(`_plate_item_fill` — 진단과 같은 획 + 글자색 ΔE00 < 20 인 픽셀만, + 3 px + 빛, 획 둘레로 ±6 px 정합 · 판 알파 수준 맞춤 · 흐린 경계 섞기) — 판이 없거나 못 맞춘 글자만 줄 보간(`cutout.compose`). 글자 상자 사각형을 통째로 바꾸면 codex 판이 몇 px 다르게 다시 그린 배지 테두리가 사각형 가장자리에서 어긋났다(= 배지 양옆 선 — 오프라인 154442 최대 17.6). OCR 자국이면 상자째 → 판 없이. 텍스처 = 판 상자 1:1(상한 `layers.plate_max` 2048 — WidgetMcp 임포트에 크기 상한 없음 확인, 스키마 4096). 기능 요소는 예전 오리기(`_cut_entry`) 그대로 — 소유 지도 · 넘침 · 장부는 기능 요소끼리 겹칠 때만 남는다. 기능 요소 상자 안쪽 2 px 를 판에도 그리는 규칙은 flag 패널이 숨어도 테두리가 남아 뺐다.
  - **요소 없는 판**(`concept_convert.notext_prompt`): 글자 없는 판 프롬프트 + 게이지 채움 비우기 · 런타임 그림 지우기 · separate(inputs 에서 — analyze 전이라 알 수 있음). flag 는 지우지 않는다(대개 홀로 서 있어 아래가 투명이고, 그 안 글자 자리를 이 판으로 메운다 — 설계 원안에서 바꾼 점). 지울 것이 없으면 프롬프트가 예전과 같아 캐시가 맞는다(조작 안내 = codex 0).
  - **게이지 채움(진단이 잡은 전투 HUD 결함):** `concept_fill` 텍스처 = 컨셉의 채워진 구간 그대로(왼쪽 끝 ~ 진행 끝 + 번짐, 알파 = `unfilled_track` 이 메우는 자리 — `render_concept_segment`), 양끝 margin 은 그 폭 기준, **미리보기 진행률 = 구간 폭 ÷ 막대 폭**(입력 sample 은 `sample_percent` 로 기록 — 렌더가 컨셉 상태와 1:1, 런타임 값은 게임이 넣음). 예전 params(`texture` 없음)는 예전 그림.
  - **오프라인 확인 [실측 — `replay_refine.py --layer`(새 옵션) + 텍스처 단계 지도]:** 조작 안내 4 배치(`154442` · `095249` · `135206` · `120813`) = 텍스처 14 장 → 판 1 장(1833 × 623 등) · 1:1 국소 결함 0(최대 ΔE00 0.7 ~ 1.1) · 3 배 절취선 0. 전투 HUD 2 배치 = 게이지 프레임만 판(+ 패널 둘레 빛 조각), 국소 결함 0 · 절취선 0.
- **J-c:** 외형 라운드 가드가 글자 위젯 `set` 을 전부 거절(`style.guard_style_ops` · 두 프롬프트 — 판도 교체 불가), analyze LLM 이 고른 글자 외곽선 · 그림자는 걷는다(`analyze.strip_llm_text_effects` · `pipeline.yaml text_style.deterministic_only` — 기록 `analyze/derived.json text_effects_dropped`). 글자 맞춤(`style.text_fit`)은 진단과 같은 핵심 획 마스크(`diagnose.run_text_masks`)로 컨셉 · 렌더를 잰다(상자 넓히기 대신 마스크 전체 · 측정 상자 = 두 획 상자 + 여유) — 못 만들면 예전 밝기 측정.
- **실제 run 에서 진단이 잡아 고친 것(같은 날, 각 고침 뒤 오프라인 재확인):** 글자 맞춤에 **글자색 · 그라데이션**(`style._fit_color` — 핵심 획 위 · 아래 반 대표색, analyze 색 파생이 두 톤 띠 위 라벨 셋을 남색으로 잡음) · **외곽선**(`_fit_outline` — 컨셉 획 안 어두운 비율로 두께 · 색, 빛 글자는 안 넣음 — WidgetMcp 가 빛 · 외곽선 동시 거절) · 색 · 외곽선을 고친 판 뒤 크기 판 한 번 더(색이 틀린 렌더는 높이를 못 믿음) · 맞춤이 진단 `_stats` 를 그대로(획 상자 정의 차 1.03 ↔ 1.12) · 진단 '색' · '외곽선'도 고칠 수 있는 원인 · 굵기 허용 1.3(Regular · Bold 반 단계 1.233 + 잡음 — 그 사이 굵기 컨셉은 어느 쪽도 1.22 안에 못 듦) · 핵심 획 = 획 속(2 px 안쪽) 대표색 ΔE00 < 25(검은 외곽선 빼기) · 빛 비율은 핵심 획에서 1 px 넘게 떨어진 것만(작은 글자 흐림 오판) · **본문 글꼴 SDF 사본이 없으면 '빛'은 `summary.limits`(기록만)** — Pretendard 는 SDF 가 없어 analyze 도 빛을 건너뜀(에셋 추가는 사용자 결정) · 판 글자 메우기: 글자색은 spec 이 아니라 컨셉 획에서 · 바꾸는 자리는 글자 상자 +2 px 안 · 판 알파가 글자 둘레 컨셉 알파와 중앙값 0.3 넘게 다르면 둘레 컨셉 알파를 이어 씀(codex 판이 투명 위 '오의 불가' 둘레를 0.9 로 칠함) · 기능 요소 오리기도 글자 획만 먼저(배너 아래 그림자 줄 2 px 이중) · 판 위 게이지 트랙 자리는 채움과 같은 reference.png 로(왼쪽 끝 조각 41) · 판 위 게이지의 텍스처 없는 배경은 none(파티 HUD) · ⓑ 단색 컨셉 **요소 없는 판 `concept_convert.plate_only`**(codex 1 · 캐시 `work/_convert/<sha16>_plate_<sha8>` — 단색 입력은 예전 0 → 1, 설계 '호출 수 그대로'에서 바뀐 점) · analyze 빛 여백으로 넓힌 글자 상자가 원래는 안 겹치던 형제와 겹치면 `allow_overlap`(단색 '오의 불가' ↔ 게이지 영역 — 세 run 연속 구조 실패) · 진단 글자 자리에 refine 때 글자 상자(`specs/000.json`) 포함(글자를 옮기면 메움 자리가 드러남) · 런타임 이미지 자리는 진단에서 뺌(`maps.runtime_image_px`) · 3 배 확대 모사는 이미지 브러시가 아닌 그리기 자리 뺌.
- **끝 run [실측 — 각 run 의 마지막 진단]:**

  | 입력 | run | 결과 | 진단(시도별 결함 수 → 마지막) | codex |
  | :--- | :--- | :--- | :--- | :--- |
  | `controls_alpha`(ⓐ) | `R20261117_173753_ProbeControlGuide` | **무인 통과** · 4분 | 9(글자 굵기 · 크기) → 0 · 1:1 국소 최대 1.66 · 절취선 0 · 텍스처 14 → 판 1 | 0 |
  | 조작 안내 원본(변환) | `R20261117_175512_ProbeControlGuide` | **무인 통과** · 4분 37초 | 7 → 7 → 1 → 1 → 0 · 최대 2.46 · 절취선 0 | 0(캐시) |
  | 원래 전투 HUD(변환) | `R20261117_183524_CombatHUD` | **무인 통과** · 6분 | 4 → 4 → 3 → 0 · 최대 7.7 · 기록만 1(‘오의 불가’ 빛 — 본문 SDF 없음) | 0(캐시 — 요소 없는 판 첫 호출 1 은 `180053`) |
  | 단색 전투 HUD(ⓑ) | `R20261117_191446_CombatHUD` | **무인 통과** · 3분 40초 | 4 → 8(LLM 외형 라운드가 게이지 텍스처를 망침 → 진단이 나빠져 자동으로 버림) → 4 → 2 → 0 | 0(캐시 — 첫 호출 1 은 `185327`) |
  | 파티 HUD(변환) | `R20261117_192631_ProbePartyHUD` | **실패**(구조 통과 · 진단 결함 11) | 텍스처 7(0 % 게이지 트랙 3 줄 — 판 메우기가 이미 빈 게이지를 codex 판 트랙으로 바꿈 · HP 막대 위 6 px 구멍 — analyze 막대 상자가 컨셉 막대보다 작은데 판은 막대 상자 +2 px 를 빈 트랙으로 · 막대 양끝) · 배치 1(오른쪽 'HpMax' 35 px) · 글자 3(이름 크기 · 굵기 · 위치 / HpMax · 방패 숫자) | 2(변환 — 첫 run `191858`, 이번 캐시) |

  LLM(API 정가 환산 — 구독 · 과금 아님): analyze run 당 0.16 ~ 0.34 USD. 끝 조건 중 **'5 입력 무인 통과'는 4/5** — 파티 HUD 남음. 또 위 통과 run 들은 그 뒤 고친 코드(진단 빛 비율 · SDF 기록 · refine 시점 글자 자리 · 판 메우기 상자 안 · 알파 불일치)보다 앞선 판으로 돌았다 — 새 진단으로 다시 재면 네 run 모두 결함 0(전투 HUD 는 기록만 1)이지만 **최종 코드로 다섯 입력을 다시 돌린 확인은 아직**.
- **다음(파티 HUD — 원인 짚음, 미구현):** ① 판 위 게이지(채움이 컨셉 모양이 아닌 것)는 컨셉의 진행률만큼만 판으로 바꾸기(0 % 면 안 바꿈 — 컨셉이 이미 빈 트랙) ② 가득 찬 게이지(HP 1.0)는 채움 텍스처를 컨셉 막대 조각으로(concept_fill 처럼 1:1) + 막대 상자를 컨셉 막대 실루엣에 맞춤 ③ 'HpMax' 35 px 배치 · 이름 크기 — 글자 맞춤 판 기록 확인. ④ 다섯 입력 최종 코드 재확인.
- **시험:** pytest **343**(328 → +15: 진단 7 — 깨끗 · 글자 어긋남 · 텍스처 구멍 · 숨은 상태 · 절취선 · 건너뜀 · 획 거르기, 레이어 5 — 분류 · 판 계획 · 적용 · 글자만 덩어리 · 글자 획만 메우기 · 요소 없는 판 프롬프트, 글자색 맞춤 1 · 외형 라운드 글자 op 거절 1 · 단색 요소 없는 판 1, 게이지 · 외형 라운드 · 단계 목록 · 오리기 시험을 새 동작으로 바꿈). C++ · Config 변경 없음.

**1b 후속 J 남은 일 (11-17 밤, 미커밋 — 새 세션. 쓰기 = Tools/uigen · 이 문서 · Pretendard SDF 폰트 에셋, C++ · Config 변경 없음)**

- **본문 글꼴 빛:** WidgetMcp `import_font_family distance_field` 로 `/Game/UI/Fonts/Pretendard/F_Pretendard_SDF`(+ `FF_Pretendard_SDF_Regular` · `_Bold`, Msdf — 1b 후속 F 의 Noto SDF 와 같은 길) 저장, `pipeline.yaml fonts.roles.body.sdf_family`(`config.font_roles` 가 기본 body 에만 붙임). 원래 전투 HUD '오의 불가' 가 SDF 빛 10 으로 그려지고 진단 limits 0 [실측 `R20261117_214505`].
  - 본문 빛이 생기며 드러난 것(같이 고침): ① 투명 위 빛 글자의 판 메우기 — 획을 판 차로 찾으면 판이 불투명이라 상자 전체가 한 덩어리 → 걸러져 '오의' 만 지워짐 · 정합 둘레가 빛 안이라 늘 실패 → **투명 위 글자(둘레 컨셉 알파 < 0.35 · 판 알파 불일치)는 글자 상자 전체를 둘레 컨셉으로**(상자 밖으로 이어진 불투명 구조물은 3 px 지킴 — 단 글자색 근처 + 빛 반경은 안 지킴), **정합 실패도 같은 상자 안 메우기**(예전 줄 보간은 상자 + 획 높이 × 0.5 가로 여유로 초상화 테두리를 팠다), 메우기 원천은 둘레 대표색과 비슷한 픽셀만(밝은 이웃 가장자리 줄무늬), **빛 글자는 정합 둘레를 빛 반경 밖으로**(`refine._plate_item_fill`) ② 진단 글자 획 — 빛 번짐이 이웃 글자를 한 덩어리로 이음 → 빛 여백 뺀 상자(core)에 센 획 40 px · 5 % 이상씩 걸친 덩어리는 **센 획(덩어리 p95 × 0.55)끼리 주인을 정하고 나머지는 가장 가까운 센 획을 따름**, 한 센 획이 두 core 의 자기 구역에 걸치면 픽셀로, 한 상자 안 덩어리의 렌더 획 주인은 **컨셉에서 정한 획(3 px 넓힘)과 겹치면 그 주인**(`diagnose.assign_glyphs`), 판 메우기가 글자 없는 판을 안 쓴 글자는 컨셉 획을 판 차로 재지 않음(`notext_unused`), 렌더 외곽선 글자의 핵심 획은 글꼴색 기준(굵은 검은 외곽선이 핵심 획으로 잡혀 색 ΔE00 88) ③ 글자 맞춤 — **빛 크기 맞춤**(`style._fit_glow` — 핵심 획 밖 밝은 비율 차 > 0.15 면 크기 × 비율, 컨셉 비율 < 0.05 면 빛을 떼고 보통 글꼴로: 조작 안내 '점프' 는 analyze 가 띠 밝기를 빛으로 오판) · **굵은 외곽선(어두운 비율 ≥ 0.45)은 빛보다 앞섬**(방패 '10') · 진단 '빛' 은 그 글자에 빛이 있으면 고칠 수 있는 원인.
- **파티 HUD 결함(설계 '다음' ① ② ③):** ① 판 위 게이지(채움이 컨셉 모양이 아님)는 **컨셉 진행률만큼만** 요소 없는 판으로, 0 % 면 안 바꿈(`PLATE_EMPTY_GAUGE`) ② **가득 찬 게이지(≥ 0.97)** `concept_fill._measure_full` — 둘레 어두운 띠로 문턱 · 프레임 상자를 16 px 넓혀 잼 · 둘레에 밝은 선이 없으면 막대 자체가 트랙 · 양끝 모양(lead · rlead) 고정 margin · 텍스처 = 막대 실루엣(몸통 + 띠 반지름) 컨셉 조각 1:1, 판은 그 실루엣 자리만 요소 없는 판으로(`mask` — 넓히기 · 섞기 없음), 프레임 = 게이지 상자를 80 % 이상 덮는 앞 형제(없으면 가득 찬 게이지는 자기 상자) · 캔버스 부모도(점 앵커 위치 · 크기) — LLM 이 게이지를 Overlay · 캔버스 · 패널 전체 Overlay 에 번갈아 둠 ③ **글자 맞춤 판을 글자별로 다시 고르기**(`run_pipeline._text_fit_pass` — 판이 진단을 나쁘게 해 버려지면 그 판에서 원인이 줄어든 글자만 `<판>_partial` 로 한 번 더, 겹침만 깨졌으면 겹친 글자 빼고) — 한 글자 탓에 HP 숫자 크기까지 버려지던 것.
- **끝 run(최종 코드, 하나씩 — 각 run 뒤 에디터 내림) [실측]:**

  | 입력 | run | 결과 | 진단(마지막) | 
  | :--- | :--- | :--- | :--- |
  | `controls_alpha` | `R20261117_220533_ProbeControlGuide` | **무인 통과** | 0 (시도 3) |
  | 조작 안내 원본(변환) | `R20261117_214030_ProbeControlGuide` | **무인 통과** | 0 (시도 3) |
  | 원래 전투 HUD(변환) | `R20261117_214505_CombatHUD` | **무인 통과** | 0 · limits 0 (시도 7, '오의 불가' SDF 빛) |
  | 단색 전투 HUD(ⓑ) | `R20261117_215227_CombatHUD` | **무인 통과** | 0 (시도 6) |
  | 파티 HUD(변환) | `R20261117_215853_ProbePartyHUD` | **실패** | 1 — HP 현재치 위치 7.5 px(허용 4.6) |

  codex 0(전부 캐시). 파티 HUD 경과: 결함 11(192631) → 10 → 7 → 4 → 3 → 2 → **1** — 텍스처 결함은 0(HP 화살 끝 · 0 % 트랙 · 이름 자리 구멍 모두 해결), 남은 것은 글자 하나.
- **남은 것(사용자 결정):** 파티 HUD HP 현재치 — 컨셉 숫자가 좁은 글꼴이라 같은 높이에서 렌더(Pretendard)가 20 ~ 30 % 넓다(폭 192 ↔ 159). 오른쪽 정렬이라 가운데로 맞추면 끝이 어긋나고(위치 판 9.5 px 옮김 뒤에도 진단 7.5), 정렬 끝 기준으로 재는 규칙은 다른 글자 셋에 새 위치 결함을 만들어 되돌렸다. 길: ⓐ 좁은 숫자 글꼴 역할(에셋 — 내려받기 승인) ⓑ 폭 맞춤 음수 자간(디자이너식 — 글자 모양 폭 차이는 자간으로 안 메운다는 G 결정과 충돌) ⓒ 진단 위치 허용을 폭 차이만큼 넓힘(기준 완화). 그 밖: 파티 HUD 는 상용 게임 화면(검증 전용 `work/_probe`).
- **시험:** pytest **347**(343 → +4: 가득 찬 게이지 · 투명 위 글자 / 가득 찬 게이지 mask 판 메우기 · 굵은 외곽선이 빛보다 앞섬 · 빛으로 이어진 덩어리 나누기 + `_text_causes`, body SDF 역할은 기존 시험에 더함).
- **사람 눈(11-17 밤, 사용자):** 진단 결함 0 · '무인 통과' 넷에서 바로 보인 차이 — '돌진 공격' · '공격' 에 컨셉에 없는 청록 빛(본문 SDF 로 analyze 빛 오판 — 이번 작업의 회귀), '어빌리티' 굵음 · '오의 불가' · '체인 버스트' · 체인 숫자 가늚(굵기 2 종 한계 + 진단 굵기 허용 1.3 배), '공격' 둘레 구름 얼룩(글자 없는 판 조각의 색조 차 + 빛 크기만큼 부푼 메울 범위 — 조작 안내 · 전투 HUD 모든 글자 둘레 국소 ΔE00 최대 13 ~ 22, J-a 부터 있었음, 진단은 글자 구역을 국소 지도에서 빼서 못 봄), 게이지 뒤 금빛(숨은 '가득 빛'까지 켠 `render.png` 를 사람 눈용으로 잘못 안내 — 컨셉 상태 그림이 없음). → 아래 K.

**1b 후속 K 설계 — 오류 0 · 가장 가까운 스타일, 글자와 아트를 처음부터 나누기 (11-17 밤 작성, 사용자 요청 '그 기준으로 K 설계'. 구현 전 — 아래 질문 확인 뒤)**

왜(사용자 질문 'J 까지 왔는데 근본 한계냐'에 대한 답): A ~ J 결함 대부분이 글자와 그 둘레였고 구조 원인이 셋이다. ① **납작한 그림에서 글자 아래는 지어내야 한다** — TextBlock 을 쓰려면 컨셉에서 글자를 지워야 하는데 그 아래 배경은 원래 없는 픽셀이고, codex '글자 없는 판'은 다시 그린 그림이라 색조 · 선 위치가 매번 달라(배지 양옆 선 · 얼룩 · 잔상) 정답 없는 자리에서 규칙만 늘었다. ② **컨셉 글자는 실제 글꼴이 아니다** — 이미지 모델이 그린 글자는 어떤 폰트와도 같지 않고(중간 굵기 · 다른 폭), 우리 수단은 글꼴 2 × 굵기 2 + 효과 몇 개라 '픽셀 같음'은 원리상 근사까지. ③ **검증이 3 ~ 5 장에 맞춘 휴리스틱** — 새 입력 · 새 기능마다 사각지대(오늘 굵기 · 빛 · 글자 둘레). 글자는 TextBlock 이 표준(바인딩 · 현지화) — 그림으로 굽는 길(앞서 낸 ①혼합)은 거둠.

원칙: 결과를 두 종류로 나눠 따로 판정한다.
- **오류(E — 반드시 0):** 컨셉에 없는데 파이프라인이 만든 것. E1 얼룩 · 잔상(글자 구역 바탕 포함) · E2 텍스처 뭉개짐(원본보다 흐림) · E3 잘림 · E4 구멍 · 이중 · E5 확대 절취선 · E6 위치 어긋남 · E7 컨셉에 없는 효과(빛 · 외곽선 · 그림자 유무) · E8 상태 불일치(사람 눈 그림 · 미리보기가 컨셉과 다른 상태). 하나라도 있으면 실패.
- **근사(A — 기준 안이면 받음, 따로 보고):** 가진 수단으로 원리상 못 내는 차이 — 글자 모양 · 중간 굵기 · 폭 · 효과 세기의 결. 판정 = **가장 가까운 선택지를 골랐나**: 어휘 안에 더 가까운 선택(다른 굵기 · 크기 · 색 · 효과 크기)이 있는데 안 골랐으면 오류(E9), 골랐는데 남은 차이는 '표현 한계'로 표에만 남긴다. 보고 문구는 '통과'가 아니라 '오류 0 · 근사 n 건'.

- **K-a 입력 두 갈래(inputs `concept_source: generated | external`, 없으면 make_concept 출처 기록으로 판단):**
  - **(가) generated — 우리가 컨셉을 만든 경우(M4 HUD 같은 주 용도):** 아트의 정답 = **글자 없는 아트**(codex 판 — 진짜 알파), 글자는 **사양**(문구 · 자리 · 글꼴 역할 · 크기 · 굵기 · 색 · 효과)으로 엔진 TextBlock 이 그린다. 컨셉에서 글자를 **지우지 않는다**(구멍 메우기 · 판 정합 · 글자 획 측정이 아트 쪽에서 사라짐). 글자 컨셉(글자 든 그림)은 사양을 재는 참고로만 — 자리 · 크기 · 색 · 효과를 결정적으로 재 가장 가까운 어휘로. 사람이 승인하는 최종 그림 = 글자 없는 아트 + 엔진 글자 = WBP 렌더(보이는 것이 곧 결과). 진단: 아트 = 글자 뺀 렌더 ↔ 글자 없는 아트 픽셀 비교(E 전부), 글자 = 사양 ↔ 렌더(자리 · 크기) + 글자 컨셉과 A 표.
  - **(나) external — 외부 그림 · 스크린샷(검증 입력 3 종):** 지금 길(변환 → 글자 지움 → 엔진 글자) 그대로, 단 기준을 E 0 + A 로. 글자 지운 자리: 메울 범위 = 획 + 안티앨리어싱(빛 크기로 안 부풀림), 판 조각은 둘레 컨셉 색조에 맞춰(둘레 고리의 평균 · 기울기 맞춤) 흐린 경계로 섞음 — 그래도 E1 이 남으면 실패로 보고(정답 없는 자리를 '통과'로 세지 않음).
- **K-b 검증을 사람 눈에 맞추기(먼저 구현 — 지금 run 들로 기준선):**
  - **컨셉 상태 비교 그림** `compare.png`(run 폴더 · `report.artifacts.compare`): 컨셉 | 컨셉과 같은 상태의 렌더(숨은 상태는 `hidden_state_split` 결과로 flag 값을 정해 sample 렌더 — inputs sample 이 컨셉 상태와 다르면 기록, E8) | 국소 차이 + 글자마다 3 배 확대 타일. 보고 전에 이 그림을 본다(force_visible `render.png` 는 기계용).
  - **E1 글자 구역 바탕 검사:** 지금 국소 지도에서 빼는 글자 구역도, 모든 글자 획(+2 px)을 뺀 바탕 픽셀에서 텍스처 합성 ↔ 컨셉 국소 ΔE00 [실측 오늘 — 모든 글자 13 ~ 22]. (가)는 글자 없는 아트 ↔ 글자 뺀 렌더라 원래부터 전 화면.
  - **E2 뭉개짐:** 위젯마다 텍셀 밀도(텍스처 px ÷ 화면 px) < 1 기록 + 영역 선명도(기울기 에너지) 렌더 ÷ 컨셉 < 0.8 이면 오류.
  - **E7 효과 유무 · 빛 측정 단일화:** 빛은 획 둘레 고리(2 ~ 10 px)의 '글자 없는 바탕보다 밝음'으로 재고(지금 진단은 후보 마스크 안만 세 옅은 빛을 못 봄), **analyze derive_text_glow · 글자 맞춤 · 진단이 같은 함수**를 쓴다(오늘 analyze 만 띠 밝기를 빛으로 봤다).
  - **E9 · A 굵기:** 굵기 판정 = 두 굵기(있으면 더) 중 컨셉 밀도에 가까운 것을 골랐나(로그 거리) — 아니면 E9, 맞으면 남은 비를 A 표에. 진단 굵기 허용 1.3 배(한 굵기 안 잡음)는 이것으로 대체.
  - **정답 묶음(골든 세트):** 사용자가 사람 눈으로 찾은 결함을 run 사본 + 자리 + 기대 분류로 모은다(외부 화면이라 git 무시 `work/_golden/`, 시험은 파일 없으면 건너뜀) — 배지 양옆 선 · 다이아몬드 이중 · '돌진 공격' 어긋남 · 왼쪽 라벨 굵게 + 남색 외곽선 · '회피' 작아짐 · '어빌리티' 작음 / 굵음 · '공격' 얼룩 · '돌진 공격' 빛 · 게이지 끝 조각 · HP 화살 끝 · 0 % 트랙 · 이름 구멍 · 게이지 뒤 금빛(E8). 진단이 모두 그 분류로 잡아야 하고(오프라인 pytest), 문턱을 바꾸면 이 묶음으로 다시 잰다 — 몇 장에 맞추는 보정을 끊는다.
- **K-c 글자 처리:** (가) 사양 경로(analyze 가 글자 컨셉에서 자리 · 스타일을 재 사양으로, 글자 없는 아트로 판 · 기능 요소), (나) 색조 맞춘 좁은 메우기, 공통 빛 단일 측정 · 가장 가까운 선택 규칙. 지금 결정적 글자 맞춤(크기 · 위치 · 색 · 외곽선 · 빛 · 판 글자별 다시 고르기)은 그대로 쓰되 목표가 '가장 가까운 선택'.
- **유지하는 것:** 정적 판 · 기능 요소 레이어 · 게이지 측정(가득 찬 게이지 포함) · 오리기 · 구조 게이트 10 개 · 진단 틀 · 변환 캐시 · 오프라인 재생. 바뀌는 것은 '컨셉에서 글자를 지우고 맞추는' 부분의 비중과 합격 기준.
- **순서:** K-b(검증 · 골든 세트 — 지금 run 들 기준선, 오늘 사람 눈 결함이 전부 잡히는지) → K-c(가) 원래 전투 HUD · 단색으로(글자 든 컨셉 + 글자 없는 판이 캐시에 있어 codex 0) → K-c(나) 외부 3 종 → 끝 run. 하위 단계로 잘게 나누지 않음.
- **끝 조건:** 골든 세트 전부 잡힘 · 다섯 입력 오류(E) 0 + 근사(A) 표 · compare.png 사람 눈 확인(사용자) · pytest. 보고는 '오류 0 · 근사 n 건'.
- **사용자에게 물을 것:** ① (가)의 순서 — 글자 든 컨셉 → codex 글자 없는 판(추천 — 지금 길 · 캐시 재사용, 글자 스타일 참고가 생김) vs 처음부터 글자 자리 빈 아트(사양은 요청 · LLM 이 어휘에서 고름) ② (나)에서 E1 이 색조 맞춤으로도 남을 때 — 실패로 보고(추천) vs 글자 구역만 판 전체 픽셀로(전역 색 차는 생김) ③ 굵기 — 굵기 변형 더 들여오기(Pretendard Medium · SemiBold · ExtraBold, Noto Serif KR SemiBold · Black — 내려받기 승인 + WidgetMcp 굵기 어휘 C++) vs 같은 색 1 px 외곽선 '가짜 굵게'(C++ 없음, 빛 글자엔 못 씀) vs 근사로 남김 ④ 정답 묶음 자리 `work/_golden/`(git 무시 — 외부 화면 포함).
- **결정(11-17 밤, 사용자 '전부 추천안'):** ① 글자 든 컨셉 → codex 글자 없는 판(지금 길 · 캐시 재사용) ② (나) 색조 맞춤 뒤에도 E1 이 남으면 실패로 보고 ③ 굵기 변형 더 들여오기 — Pretendard Medium · SemiBold · ExtraBold, Noto Serif KR SemiBold · Black(OFL, 공식 배포처 내려받기 승인 · WidgetMcp 굵기 어휘 C++ 변경 승인 — 빌드 2 구성), 글자 맞춤은 가진 굵기 중 가장 가까운 것 ④ 정답 묶음 `work/_golden/`(git 무시).

**1b 후속 K 구현 (11-17 밤 ~ 11-18, 미커밋 — 새 세션. 쓰기 = Tools/uigen · Plugins/WidgetMcp(굵기 어휘) · Tools/mcp/widget_mcp · Content/UI/Fonts(새 굵기 family) · 이 문서)**

- **K-b 검증:** `gen/diagnose.py` — 결함마다 오류 번호(E1 ~ E9) · 근사 `approx[]` · `summary{errors, approx, by_code}`, 게이트 = 오류 0. E1 글자 구역 바탕(획 · 획에 붙은 효과 · 컨셉 빛 자리를 뺀 바탕에서 min(렌더, 합성) ↔ 컨셉) · E2 선명도 · E6 정렬 끝 근사 / 측정 불가 `unmeasured` · E7 빛 단일 측정 `glow_measure`(analyze `derive_text_glow` · 글자 맞춤 `_fit_glow` · 진단 공용, 있음 = 띠 밝기 ≥ 문턱/2 `glow_on`) · E8 상태(숨은 글자 위젯 = 컨셉에 그 획이 있나 + 안전망) · E9 가장 가까운 굵기(`fonts.weight_density` 표, 여유 0.06). `compare.png`(run 폴더 — 컨셉 | 컨셉 상태 실제 엔진 렌더(verify `render_state` 가 숨은 위젯을 `hidden_state_split` 대로 켜고 끔) | 국소 차이, 글자 3 배 타일). 정답 묶음 `golden.py` · `work/_golden/` 16 건(설계 목록 14 + 이 세션 compare.png 눈 확인 2 — '오의 불가' 자리 판 잔상 · 상태 오판, 단색 '2/4' 테두리선 겹침) — 전부 잡힘 · `tests/test_golden.py`.
  - 기준선 [실측 — 지난 run 9 개]: 오늘 사람 눈 결함 '공격' 얼룩 E1 · '돌진 공격' 빛 E7(띠 7.8 — 문턱 8 하나로는 갈렸음) · '어빌리티' 굵음 E9 · 게이지 뒤 금빛(상태 `force_visible_extra` = UltReadyGlow) 모두 잡힘.
- **굵기 변형:** Pretendard v1.3.9 Medium · SemiBold · ExtraBold, Noto Serif KR SemiBold · Black(공식 저장소 — `curl` 은 권한 프롬프트에서 취소돼 스크래치 파이썬 urllib, 크기 · 글꼴 머리 확인) → `work/_fonts`. WidgetMcp 는 폰트 덮어쓰기 금지라 새 family `F_Pretendard_W`(+`_SDF`) · `F_NotoSerifKR_W`(+`_SDF`). C++ `Weights()` · `AllowedTypefaces()` + 4 굵기, 빌드 2 구성 성공. 밀도 표 [실측 PIL]: Pretendard M 1.176 · SB 1.348 · B 1.488 · EB 1.628 / Noto SB 1.271 · B 1.482 · Bk 1.692 — 엔진 렌더 간격은 약 5 % 달라(Regular ↔ Medium 실측 1.235) 여유 0.06.
- **K-c (가) generated:** `normalize.concept_source`(inputs 또는 concept.json) → `background.art`(글자 없는 판) — refine · layer 가 아트에서 바로 오림(글자 구멍 없음), 판 게이지 트랙 덧칠 안 함, 아트 모드 OCR 자국 = 장식, 진단은 아트와(게이지 채운 구간 트랙 안쪽만 컨셉 · 글자 획 둘레는 글자 든 컨셉과 · 글자 후보 사양 글자색 근처 · ±2 px 이동 최소 차). **아트(codex 판)는 투명 위 글자를 잔상으로 남긴다**[실측 R20261117_233356 — 붉은 '오의 불가' 얼룩, 그 탓에 숨은 상태 오판 · 빛 측정 실패 · 렌더에서 글자 빠짐] → `diagnose.clear_text_residue`(상자 둘레 투명 + 상자 밖 구조물 < 절반 → 상자 안 투명, refine 아트 · analyze 빛 바탕 · 진단 공용, 진단은 refine 때 상자 `specs/000.json`).
- **K-c (나) external:** `refine._plate_item_fill` 좁은 메우기(획 + 3 px + 획에 이어진 실제 밝은 빛 픽셀 — 구조선 제외) + 둘레 고리 색조 평면 보정. controls 두 입력은 글자 구역 바탕 국소 최대 13 ~ 22 → 3.9 ~ 4.9.
- **글자 맞춤:** 가장 가까운 굵기(크기를 바꾸는 판은 굵기를 다음 판으로 — 작은 글자는 획이 두껍게 재져 Medium ↔ Regular 진동) · 빛 넣기 `_add_glow` · 떼기 · 크기(`glow_on` 같은 기준 — 넣기 · 떼기 문턱이 달라 진동했음) · 폭 다른 글자 정렬 끝 · 획 상자 높이 = 몸통 줄(사선 꼬리 제외 — 조건부로 하면 크기마다 켜졌다 꺼져 '2/4' 30 → 22 → 26 진동) · `measure_trusted` 진단 · 맞춤 공용(위치 판에도 — 못 믿는 측정으로 옮겨 '2/4' 를 금선 위로 보냈음) · 위치 판 뒤 크기 판 한 번 더 `text_fit_size_final`. 외형 라운드 op 를 build 가 거절하면 그 라운드만 버림(파티 HUD — LLM 이 초상화 이미지 브러시에 radius).
- **끝 run [실측 — 하나씩, 각 run 뒤 에디터 내림, codex 0(캐시)]:**

  | 입력 | run | 결과 |
  | :--- | :--- | :--- |
  | 원래 전투 HUD (가) | `R20261118_003804_CombatHUD` | **오류 0 · 근사 2**(굵기 — Bold · Black) — 뒤 코드 변경 후 진단 재측정도 오류 0 (refine 게이지 트랙 변경 전 run) |
  | 단색 전투 HUD (가) | `R20261118_093320_CombatHUD` | **실패 — 오류 2**(E6 배너 '체인 버스트' 10 px · '3' 세로 19.5 px — 위치 판이 세로 이동을 형제 겹침 예측으로 버리고 가로만 옮긴 판이 진단을 못 줄여 되돌려짐, 배너 줄 높이 · 세로 정렬은 analyze 배치 몫). 앞 run `010950` 은 통과였으나 사람 눈으로 '2/4' 금선 겹침을 찾아(측정 불가 · 위치 판이 못 믿는 측정으로 옮김) 고친 뒤 다시 돌린 것 — '2/4' 는 해결 |
  | `controls_alpha` (나) | `R20261118_084216_ProbeControlGuide` | **오류 0 · 근사 4**(굵기 — Medium · Regular), 글자 구역 바탕 국소 최대 4.9 |
  | 조작 안내 원본 (나) | `R20261118_085640_ProbeControlGuide` | **오류 0 · 근사 4**(굵기 3 · '어빌리티' 글자 폭), 국소 최대 3.9 |
  | 파티 HUD (나) | `R20261118_092315_ProbePartyHUD` | **실패 — 오류 15**(E1 12 · E6 3): HP 막대 윗선 청록 빛 줄이 글자 상자 겹친 구간에서 어두운 띠(값이 run 마다 같아 결정적 — J 까지는 글자 구역이라 안 보였음, 가득 찬 게이지 판 메우기 의심) · 이름 '지크프리트' 회청색 + 가로 줄무늬 · 막대 왼쪽 위 홈(J 215853 보다 나빠짐 — 이번 (나) 메우기 · 색조 보정 회귀로 봄) · 측정 불가 3 |

- **남은 것:** 파티 HUD (나) 회귀 · HP 막대 윗선 · 이름 색 — 다음 세션. → 아래 'L 설계'.

**1b 후속 L 설계 — 정답 = 사람이 승인한 그림, 다시 그린 그림은 정답 없는 자리에만 (11-18 작성, 사용자 요청 'L 설계 작성'. 구현 전 — 아래 질문 확인 뒤)**

왜(사용자 사람 눈 11-18 — K 끝 run 원래 전투 HUD 에서 게이지 테두리 둘레 빛 · 버스트 배너 상자 색 차이, 사용자 질문 'codex 가 색을 바꾸는 게 근본이냐 · 지시를 명확히 하면 되냐 · 방식이 잘못이냐'): K (가) 는 codex 가 다시 그린 '글자 없는 판'을 아트의 정답으로 삼았다. 렌더는 그 판을 충실히 옮겼지만(배너 렌더 ↔ 컨셉 차 = 판 ↔ 컨셉 차) **사용자가 승인한 그림은 글자 든 컨셉**이고, 진단도 판과 비교해 그 차이를 못 봤다. codex 편집은 그림 전체를 다시 그리고(구독 경로는 마스크 편집 없음 — 마스크 인페인트는 유료 API) 프롬프트에 이미 '모든 요소 · 색 · 위치 · 크기를 그대로'(`gen/concept_convert.py`)가 있는데도 색조 · 빛 · 선 위치가 매번 달라진다 — 지시 강화는 확률을 줄일 뿐 '오류 0' 의 근거가 못 된다. 원칙: **다시 그린 그림의 픽셀은 원래 정답이 없는 자리(글자 획 아래)에만 쓰고, 그 밖의 정답은 사람이 승인한 그림의 픽셀이다.** 진단의 비교 대상도 늘 그 그림.

- **L-1 ⓐ 우리가 만든 컨셉도 '컨셉 픽셀 + 글자 자리만 판' (외부 컨셉 길과 하나로):**
  - 근거 [실측 K]: 버스트 배너 렌더 ↔ 컨셉 7 × 7 국소 상위 5 % — K 원래 전투 HUD `003804` 10.9 · 단색 `093320` 14.9 ↔ J(컨셉 픽셀) `214505` 0.5 · `215227` 1.0, 체인 패널 11 ~ 12.6 ↔ 0.5 ~ 1.3, 게이지 테두리 둘레 빛(사용자 눈). 같은 자리 판 ↔ 컨셉 10.5 · 14.8 — 렌더 ≈ 판.
  - 고칠 곳: 글자 든 컨셉이 정답인 run 에서는 `background.art` 를 쓰지 않는다 — refine `_reference_layers` · layer 판 알파 = 컨셉, 글자 자리는 (나) 좁은 색조 맞춤 메우기(`_plate_item_fill` — 판 = 글자 없는 판, 투명 위 글자는 `clear_text_residue` 그대로), 판 게이지 트랙 · OCR 자국 규칙은 예전대로. 진단은 늘 글자 든 컨셉과(아트 모드 분기 — 게이지 트랙 안쪽만 컨셉 · 글자 후보 글자색 거르기 · ±2 px 이동 최소 차 — 는 L-2 의 '원본 아트' 일 때만 켬). 아트 모드 코드는 지우지 않고 L-2 가 쓴다(정답이 원본 생성일 때만).
  - 검증: 먼저 정답 묶음에 이번 사람 눈 결함 2 개(원래 전투 HUD `003804` 게이지 테두리 빛 · 배너 · 패널 색)를 넣고 컨셉 비교 진단이 E1 로 잡는지 → 고친 뒤 원래 전투 HUD · 단색 run, compare.png 직접 확인.
- **L-2 ⓑ' 컨셉 단계에서 글자 없는 UI 를 만들게 유도 (새로 만드는 컨셉 — M4 HUD 등 주 용도):**
  - 흐름: ① `make_concept --text-free-first` — codex 새 그림, 프롬프트에 화면 요소 · 글자 칸(static_text · 바인딩 글자의 자리 설명 — '빈 배너 가운데', '빈 패널 위 칸')을 '글자 없이 비워 둔 칸'으로 → **원본 아트(픽셀 정답)** ② 그 아트에 codex 편집 1 회 '이 칸들에 이 글자만 얹어라'(static_text · sample 값 그대로) → **글자 참고판**(스타일 측정용 — 배경 픽셀은 안 씀, 다시 그려 색이 조금 바뀌어도 상관없음) ③ inputs `concept` = 원본 아트 · `concept_text_ref` = 참고판(새 필드), `concept_source: generated_textfree`(새 값) ④ normalize — 참고판을 아트에 정합(전역 이동 — 지금 글자 없는 판 정합의 반대 방향) ⑤ analyze — 배치 · 글자 상자 · 글자색 · 빛 · 굵기는 참고판에서(지금 측정 도구 그대로 — 참고판 ↔ 아트 차가 글자 획, 다시 그린 어긋남은 ±2 px 이동 최소 차로 덮음), 아트 픽셀은 원본 ⑥ refine · layer = K 아트 모드 그대로(정답이 원본이라 맞는 경우) ⑦ 진단 — 아트 = 원본 ↔ 렌더(전 화면), 글자 = 참고판 ↔ 렌더(근사 표), compare.png 왼쪽은 '원본 아트 + 참고판 글자'.
  - 사람 승인: 컨셉 단계에서 원본 아트 + 참고판(글자 모습)을 같이 본다 — 최종 승인은 WBP 렌더.
  - 위험 · 가드: 글자 없이 그리라 해도 codex 가 글자를 그림 → OCR(검출 상자) 로 잡아 1 회 다시, 그래도면 그 컨셉은 L-1 길(글자 든 컨셉 취급)로 물러남. 참고판이 칸 밖에 글자를 얹거나 칸을 바꿔 그림 → 정합 잔차 · 글자 칸 밖 차이로 검사, 실패면 참고판 없이 사양(LLM 이 어휘에서)으로. codex 호출 컨셉당 +1(캐시).
  - C++ 변경 없음 예상. 바뀌는 곳: make_concept · inputs 스키마 · normalize · analyze(글자 측정 그림 선택) · 진단(compare.png 왼쪽).
- **L-3 남은 결함 (서로 독립):**
  - **L-3a 단색 HUD 배너 글자 세로 위치** [실측 `093320` — '체인 버스트' 가로 10 px · '3' 세로 19.5 px]: 위치 판이 '모든 이동이 형제와 겹침(예측)'으로 세로 축을 버리고 가로만 옮긴 판이 진단을 못 줄여 통째로 되돌려짐. 할 일: 가로 상자 안 세로 이동(교차 축 — 슬롯 위아래 padding · v_align)이 왜 형제 겹침으로 예측되는지 확인(겹침 상대 · 규칙) → 교차 축 이동은 같은 줄 형제와 안 겹치면 받기, 판 되돌림 때 원인이 줄어든 글자만 다시(`_partial`) 가 위치 판에서도 도는지.
  - **L-3b 파티 HUD** [실측 `092315` — 오류 15, J `215853` 보다 나빠짐]: ① HP 막대 윗선 청록 빛 줄이 이름 · HP 숫자 아래에서 어두운 띠(국소 20.9 · 21.3 · 22.9 … — run 마다 같은 값 = 결정적, J 까지는 글자 구역이라 진단 밖) — `replay_refine` 으로 그 픽셀을 쓰는 단계(가득 찬 게이지 판 메우기 `mask` · 글자 구멍 · 색조 보정)를 짚고, 구조선(가로 빛 줄)은 컨셉 픽셀로 지킴 ② 이름 '지크프리트' 회청색 + 가로 줄무늬 — J 와 비교해 원인이 (나) 메우기 · 색조 평면 외삽인지 글자 맞춤 색(`_fit_color`)인지 오프라인으로 가름 ③ 측정 불가 3(이름 · HpMax · 링크 %) — ② 와 같이.
  - **L-3c 컨셉 글자의 얇은 그림자** [사람 눈 — 원래 전투 HUD '체인 버스트' · '체인' · '2/4' 오른쪽 아래 어두운 그림자, 렌더엔 없음, 진단 어두운 비율 차 0.065 ~ 0.117 < 0.2 라 오류도 근사도 아님]: 그림자 유무 · 오프셋 · 색을 빛처럼 한 함수(`shadow_measure` — 획을 (dx, dy) 옮긴 자리가 글자 없는 바탕보다 어두운가)로 → 진단 E7 · 글자 맞춤이 `font.shadow{offset, color}`(이미 있는 어휘 — J-c 가 LLM 값만 걷음)를 결정적으로 넣고 뺌.
- **순서:** L-1(작음 · 두 입력) → L-3(지금 다섯 입력의 남은 오류) → L-2(흐름이 바뀌는 큰 일 — 설계 질문 확인 뒤). 각 단계 끝 = 정답 묶음 전부 잡힘 · 해당 입력 오류 0 + compare.png 직접 확인. 하위 단계로 잘게 나누지 않음.
- **끝 조건:** 다섯 입력 오류 0 + 근사 표(L-1 · L-3) · L-2 로 원래 전투 HUD 를 새로 만든 컨셉 1 개 오류 0 · pytest · 정답 묶음 · compare.png 사람 눈(사용자).
- **사용자에게 물을 것:** ① L-1: 아트 모드 코드는 지우지 않고 L-2 전용으로 남김(추천) vs 지움 ② L-2 글자 칸 지시: 칸 자리 설명만(추천 — codex 가 구도를 정함) vs 칸 크기 · 자리까지 좌표로 ③ L-2 에서 codex 가 글자를 그려 버리면: 1 회 다시 → 그래도면 L-1 길로 물러남(추천) vs 실패 ④ L-2 시험 컨셉: 원래 전투 HUD 를 L-2 로 새로 만들기(codex 2 회 — 추천) vs 새 화면 하나 ⑤ 순서 L-1 → L-3 → L-2(추천).
- **결정(11-18, 사용자 '전부 추천안'):** ① 아트 모드 코드는 L-2 전용으로 남김 ② 글자 칸은 자리 설명만 ③ codex 가 글자를 그리면 1 회 다시 → L-1 길로 물러남 ④ L-2 시험 = 원래 전투 HUD 를 새로 만들기(codex 2 회) ⑤ 순서 L-1 → L-3 → L-2. 컨셉 글자의 얇은 그림자(전투 HUD '체인 버스트' 등)는 외곽선 · 그림자 기준(어두운 비율 차 0.2) 밖이라 오류도 근사도 아님 — 사람 눈에 보일 수 있음. pytest 349(+2 정답 묶음).

**1b 후속 L-1 · L-3 구현 (11-18, 미커밋 — 새 세션. 쓰기 = Tools/uigen · 이 문서, C++ 변경 없음. L-2 는 컨텍스트 때문에 새 세션으로 인계)**

- **L-1:** 아트 모드 스위치를 `diagnose.art_mode(bgrec)` 한 함수로 — `normalize.json background.art.role == "original"`(L-2 원본 생성 아트)일 때만. normalize 는 `generated`(글자 든 컨셉)에 `art.used False`(이유 기록), `generated_textfree` 분기는 L-2 자리(`concept_source` 가 아직 그 값을 안 냄). refine `art_files` · layer · 진단(아트 비교 분기 · 글자 후보 `color_gate`)이 같은 함수 — K 의 run 들(role 없음)도 다시 진단하면 컨셉 비교. K 아트 모드 코드는 그대로(결정 ①). 정답 묶음 +2(`R20261118_003804` — '게이지 테두리 둘레 빛' UltGauge · StaticPlate6 · '버스트 배너 · 체인 패널 상자 색') → 컨셉 비교 진단이 둘 다 **E4**(컨셉보다 불투명 — 판 색 · 빛 차, 설계의 E1 대신)로 잡음, 묶음 **18/18**.
- **L-3a [실측 `093320` 재현]:** 단색 배너 '3' 의 세로 이동을 막은 '형제 겹침'의 상대는 보이지 않는 `BurstSpacer`(글자 상자 왼쪽 padding −1.2 가 스페이서에 걸침 → 0.164). `core/geometry.overlaps` 가 Spacer 쌍을 세지 않음(`skipped_spacer`) — overlap 게이트 · 글자 맞춤 겹침 예측 공용(같은 함수). `_partial`(원인 줄어든 글자만 다시)은 위치 판에서도 돌고 있었음.
- **L-3b [실측 `092315` 오프라인 — `replay_refine` + 텍스처 확대]:** 이름 회청색 + 줄무늬의 원인 = 판 정합 실패(둘레 차 57) → '상자 안 둘레 컨셉 메움'(줄 보간)이 글자 상자 전체를 메워 가로 줄무늬 → 그 줄무늬가 컨셉 획 측정을 오염(핵심 획 L* 27 — 어두운 쪽을 글자로) → `_fit_color` 가 글자색을 어둡게. 고친 것(`refine._plate_item_fill`): ① **투명 위 글자** 판정을 글자 획 둘레(빛 반경 밖 고리) 알파 < 0.35 로(상자 둘레 고리는 빛 여백까지 넓힌 상자가 배너 밖으로 나가 배너 위 '3' 을 오판 — 외곽선이 남아 baked_text 0.709 [실측 run `113122`]) — 판을 안 쓰고 상자를 둘레 매끈한 메움, 판에도 있는 구조물(`_plate_same` — ±2 px 이동 최소 차 < 24 또는 판 밝기 ≥ 컨셉 × 0.6 [실측 — codex 판은 HP 막대 윗선을 1 px 어긋나고 더 밝게(245 ↔ 188 ~ 218) 그려 차 42 ~ 46, 글자 빛 줄은 판이 어두워 차 33 ~ 57 — 차 하나로 못 가름])은 지킴 — 막대 윗선 어두운 띠 · HP 최대치 유령 숫자(판 잔상을 알파 이득 × 4 가 키움) 해결 ② 정합 실패 불투명 바탕 글자 = **좁은 둘레 메움** `_narrow_neigh_fill`(획 + 3 px + 매끈한 바탕과 채널 최대 차 > 12 인 획에 이어진 빛 · 외곽선 · 그림자, 긴 구조선 제외 — 루마로 재면 파란 빛이 안 넘었다) ③ 메움 = **가우스 가중 평균** `_smooth_fill`(줄 보간의 가로 줄무늬 없음) ④ 판이 글자 자리를 투명하게 비운 픽셀(판 알파 < 그 픽셀 둘레 메움 알파 − 0.3)은 둘레 메움(`plate_clear_px` — 트랙 위 '0 %' 의 어두운 글자 모양 구멍) ⑤ 판 정합은 원래 컨셉에 대고(`orig` — 앞 글자 메움이 둘레를 바꿔 같은 글자가 순서에 따라 정합 11 ↔ 30). 시도했다 뺀 것: 길고 얇은 선 모양으로 구조선 가르기(빛으로 이어진 글자 획 · 띠까지 선으로 잡힘) · '둘레 구조물 색과 같은 픽셀' 지키기(구조물에 이어진 컨셉 빛까지 지켜 회녹색 얼룩) · 좁은 메움 원천을 거르지 않기(위 초록 막대가 흘러내림). 남은 모호한 자리 = '0 %'(판이 트랙까지 지워 트랙 끝에 걸친 글자 밑의 정답이 없음 — 원천을 둘레 대표색으로 거르면 트랙이 '0' 앞에서 끝남).
- **L-3c:** `diagnose.shadow_measure`(핵심 획을 (dx, dy) ≤ 3 px 옮긴 자리 — 안티앨리어싱 1 px 밖 — 의 평균 어두움 − 반대쪽 중앙값, 있음 = 16 이상) → 진단 E7 `shadow` · 글자 맞춤 `style._fit_shadow`(font.shadow{offset, color} 넣고 뺌, 같은 문턱 — K 교훈). [실측] 원래 전투 HUD '체인 버스트' · '체인' · '2/4' 는 어느 오프셋에서도 ≤ 3(측정상 그림자 없음 — 사람 눈 관찰은 측정으로 확인 못 함), 조작 안내 띠 위 글자는 띠 경계 탓에 9.6 ~ 12.3(그래서 문턱 16 — 10 이면 거짓 양성), 합성 그림자 시험 (2, 2) 정확.
- **L-3b 후속(run 에서 드러난 것):** 배너 '3' 외곽선 잔상(좁은 메움이 글자색 근처만 봄 → '매끈한 바탕과 다른' 픽셀로) · 단색 패널 폭 '2/4' 상자 — 글자색 원천이 모서리 장식(판이 다르게 그림)이 돼 '2/' 를 못 지우고 장식을 지움 → 원천에서 상자 밖으로 이어진 덩어리 빼기 · 획 후보와 메울 자리에서 판에도 있는 구조물(`_plate_same(ratio=False)` — 밝기 비 규칙은 회색 배지 위 흰 글자를 구조물로 오판해 조작 안내 'E' · 'T' 회귀) 빼기 · 판에 남은 자국(판 자기 미디언과 차) 자리는 둘레 메움.
- **끝 run [실측 — 최종 코드, `uigenL/run_set.py` 로 하나씩 · run 마다 에디터 내림 · codex 0(캐시), pytest 355]:**

  | 입력 | run | 결과 |
  | :--- | :--- | :--- |
  | 원래 전투 HUD (L-1) | `R20261118_123805_CombatHUD` | **실패 — 오류 1**(E6 배너 '체인 버스트' 위치 — 글자 맞춤이 못 줄임) · 근사 3. 같은 L-1 코드의 앞 run `R20261118_114547` 은 **오류 0 · 근사 3**(배너 국소 상위 5 % 0.5 · 체인 패널 0.6 ↔ K 10.9 · 11.2, compare.png 직접 확인) — analyze 배치 흔들림 |
  | 단색 전투 HUD (L-1) | `R20261118_124503_CombatHUD` | **실패 — 오류 2**(E1 '2/4' 아래 금선 위 밝은 혹 · E6) · 근사 2. 앞 run `R20261118_120715`(판 구조물 규칙 전)은 **오류 0 · 근사 4**, 배너 글자 세로 위치(L-3a) 해결 확인 |
  | `controls_alpha` | `R20261118_125054_ProbeControlGuide` | **오류 0 · 근사 3** |
  | 조작 안내 원본 | `R20261118_125624_ProbeControlGuide` | **오류 0 · 근사 4**(중간 run `122008` 의 'E' · 'T' 회귀 해결) |
  | 파티 HUD | `R20261118_130201_ProbePartyHUD` | **실패 — 오류 9**(E1 6 · E6 3) · K `092315` 15 → 중간 run `122655` 7 → 9. 이름 · Lv · HP 숫자 자리 줄무늬 · 막대 윗선 띠 · 유령 숫자는 오프라인으로 해결 확인, 남은 것 = 투명 바탕 빛 글자 둘레 얼룩 · 글자 크기(측정 불가) · '0 %'(판이 트랙까지 지운 모호한 자리) |

- **남은 것(다음 세션):** 끝 조건 미달 — 원래 · 단색 전투 HUD 는 run 마다 갈림(배너 글자 위치 E6 · '2/4' 금선 혹 E1), 파티 HUD 오류 9. L-2 미착수(인계 `side-session-notes/local_7fbf149a…/uigen-L2-handoff.md`). 교훈: 판 메우기 규칙 하나를 고칠 때마다 다른 입력의 다른 글자에서 새 결함이 났다(배너 '3' · 패널 '2/4' · 배지 'E' · 'T') — 고친 뒤 다섯 입력을 `replay_refine` 로 같이 돌려 텍스처를 먼저 보고 run 할 것.
- **사람 눈 · 결정(11-18, 사용자):** 단색 '2/4' 의 '4' 밑 잔상(`120715` — 진단 오류 0 이었음: 글자 둘레 바탕 검사가 렌더 획 + 2 px 를 빼 획에 붙은 잔상이 사각지대) · `124503` '2/4' 가 커져 금선에 걸림 + 금선 위 혹 · 파티 `130201` 전체 개선(방패 '10' 많이 좋아짐), 'Lv 100' · '0 %' 위치 약간 아쉬움. 결정 = **방식 유지 · L-2 먼저**(우리 컨셉은 글자 지운 자리가 아예 없어짐), 그 다음 외부 · 단색 입력은 검증 틀(이 지적들 정답 묶음 + 획에 붙은 잔상 검사 + 다섯 입력 오프라인 비교) 먼저.

**1b 후속 L-2 구현 — 글자 없는 컨셉부터 + 글자 참고판 (11-18, 미커밋 — 새 세션. 쓰기 = Tools/uigen · 이 문서, C++ 변경 없음)**

- **흐름(위 L-2 ① ~ ⑦ 그대로):** ① `make_concept --text-free-first`(+ `--inputs`, codex 상한 3) — 프롬프트 = fixture `concept_prompt.md`(화면 요소 · 글자 칸 자리 설명만, 좌표 없음) + 진짜 알파 규칙 + `NO_TEXT_RULES`('글자 없음 · 칸은 요소 표면 그대로, 자리표시 상자 금지') → `concept.png` = **원본 아트**. OCR(검출 0.7)에 상자가 있으면 1 회 다시, 그래도면 `concept.json text_free_first.status: text_drawn` → normalize `concept_source` 가 generated(L-1)로 물러남. ② 그 아트에 codex 편집 1 회 — `gen/text_ref.text_ref_prompt`('이 칸들에 이 글자만': static_text 값 · text/number sample(format 대로), 칸 설명 = `desc` — static_text 새 선택 필드(brief 로는 안 넘김) · data · required_elements 순) → `concept_text_ref.png` + `concept_text_ref.json`(검사 기록). ③ inputs `concept_source: generated_textfree`(새 값) · `concept_text_ref`(새 필드). ④ normalize `_fit_text_ref` — 원본 아트를 아트(`reference_art_*`) · 글자 없는 판(`reference_notext_*`) 둘 다로, 참고판은 같은 배치 · 배경 처리 뒤 위상 상관 **정수 px** 정합(소수 이동은 쌍선형으로 획을 흐려 굵기 측정이 달라짐 — 글자 획은 아트에 짝이 없어 0.5 px 는 상관없음) → `gen/text_ref.merge`: 참고판 OCR(0.6 — 아트에도 있는 자국은 IoU ≥ 0.3 이면 장식) 상자 + 6 px 안에서 아트와 ±2 px 이동 최소 채널 차 > 48 인 글자 획(6 px 미만 잡티 제외) + 2 px(안티앨리어싱) + 획 12 px 안 둘레 바탕 색조보다 L* 8 더 밝은 빛만 원본 아트 위에 붙인 그림 = **레퍼런스(`reference*`) = 원본 아트 + 참고판 글자 획**(붙인 자리 `reference_textref_paste.png`, 정합한 참고판 `reference_textref_*`). 다시 그린 바탕의 색조 차가 analyze · 글자 맞춤 · 진단 어디에도 안 섞인다(인계 메모의 '참고판을 레퍼런스로' 매핑보다 한 걸음 — 레퍼런스 바탕까지 원본 아트). 기록 `background.text_ref` · `art{used, role original, element_free false, text_residue false, text_ref_used}` · `notext{role original_art, text_residue false}`. ⑤ analyze · 글자 맞춤 = 그 레퍼런스(도구 그대로). ⑥ refine · layer = K 아트 모드 — 단 원본 아트는 K 의 '요소 없는 판'이 아니라 게이지 채움까지 그린 그림이라 `diagnose.art_element_free` = false(판 게이지 빈 트랙 덧칠은 함 · 진단은 막대 구간을 컨셉으로 안 바꿈), 글자를 그린 적 없어 `diagnose.residue_free`(투명 위 글자 잔상 지우기 안 함 — 글자 상자 안 아트 장식을 비우지 않게, refine · analyze 빛 바탕 · 진단 공용). ⑦ 진단 = 아트 ↔ 렌더(전 화면) · 글자 = 레퍼런스 글자 획 ↔ 렌더(`diagnosis.truth_text: text_reference_glyphs`, 참고판이 없으면 `spec_only` — 글자 record_only), `compare.png` 왼쪽 = 레퍼런스(원본 아트 + 참고판 글자).
- **가드 보정 [실측 codex 2 회 — 원본 아트 1(글자 없음, 다시 그리기 없음) · 참고판 1]:** 참고판 글자 6 개는 칸에 맞게 들어갔으나 codex 가 원본 아트의 옅은 바깥 빛(반투명)을 **불투명한 갈색 띠로 다시 그려** 처음 칸 밖 검사(보이는 UI 전체의 큰 차 · 알파 차)가 18 % · 20 % 로 떨어뜨렸다. 합친 그림은 글자 상자 안 픽셀만 참고판에서 가져와 그 차가 결과에 안 섞이므로, 칸 밖 차이를 '아트가 단단히 그린 자리(알파 > 0.9)의 큰 색 차 > 80' · '아트가 비운 먼 자리(보이는 픽셀 16 px 밖)에 새로 그림'(각 3 % 이하)으로 나누고 반투명 가장자리 알파 차는 기록만(`fringe_alpha_frac`) · 글자 획 · 빛 후보에서도 뺌 → 0.0002 · 0 · 가장자리 0.15, 상자 6 개 = 글자 6 개, 붙인 픽셀 19 457(정합 (1, 0) px). fixture 기록은 새 검사로 갈아 끼움(`check_history` 에 처음 판정).
- **진단 고침 [실측 첫 L-2 run `R20261118_141410` — 오류 1]:** 참고판 '오의 불가'(노란 그라데이션 + 짙은 붉은 빛)를 analyze 가 빛 #FF1606 알파 0.96 으로 → 렌더에서 빛이 글자와 한 후보 덩어리가 돼 획 속 대표색 = 빛 색, 렌더 핵심 획을 빛으로 잡음(L* 14 · 색 ΔE00 75 · 상자 83 × 50) → 글자 맞춤이 그 측정으로 크기 32 → 25 → 22 · 빛 8 → 12 → 18 로 돌다 '측정 불가'. `diagnose._font_refs`(렌더 글자색 = 사양 색으로 핵심 획 고르기)를 외곽선 글자에서 **빛 글자까지** — 진단 · 글자 맞춤 공용. 시도 3 상태 오프라인 재측정 색 ΔE 1.1 · 높이 비 1.11(고칠 수 있는 값), 정답 묶음 18/18 그대로.
- **끝 run [실측 — `uigenL/run_set.py` 로 하나씩 · run 마다 에디터 내림, 각 compare.png 직접 확인]:**

  | 입력 | run | 결과 |
  | :--- | :--- | :--- |
  | 원래 전투 HUD **L-2**(`fixtures/m4_combat_hud_l2` — codex 2, fixture 캐시) | `R20261118_142524_CombatHUD` | **오류 0 · 근사 2**(굵기 — '3' · '2/4'), 시도 7. 국소 지도 최대 10.6(게이지 빈 트랙 오른쪽 옅은 차 — 문턱 아래) · 글자 구역 바탕 최대 8.6, 글자 6 개 위치 ≤ 1.5 px · 높이 비 0.97 ~ 1.06 · 색 ΔE00 ≤ 2.8 |
  | 원래 전투 HUD L-1(회귀) | `R20261118_143409_CombatHUD` | **실패 — 오류 1**(E6 배너 '체인 버스트' 5.5 px) · 근사 1. **L-2 변경 탓 아님** — 빛 · 외곽선 없는 글자라 바뀐 코드를 안 타고, 측정값(높이 비 1.022 · 폭 비 0.958 · 밀도 비 1.05 · 색 0.64)이 L-1 끝 run `123805` 의 같은 오류와 똑같다(정렬 끝만 반대). 원인 = 위치 판이 폭 비 ÷ 높이 비 0.90 으로 '오른쪽 끝 맞춤'을 고른 뒤 마지막 크기 판(`text_fit_size_final`)이 굵기를 bold → black 으로 바꿔 폭이 넓어지자 진단은 0.937(모양 차 8 % 안 → 가운데 기준)로 재 어긋남 — 맞춤 · 진단의 정렬 끝 판정이 판 사이 굵기 변경으로 갈림(L-3 남은 결함) |
  | `controls_alpha`(회귀) | `R20261118_143847_ProbeControlGuide` | **오류 0 · 근사 2** |
  | 원래 전투 HUD **L-2**(빛 세기 고침 뒤 — 아래) | `R20261118_164931_CombatHUD` | **오류 0 · 근사 4**(굵기) — 마지막 코드 |
  | 원래 전투 HUD L-1(마지막 코드 회귀) | `R20261118_171644_CombatHUD` | **오류 0 · 근사 5**(굵기 3 · '체인 버스트' 폭 · '오의 불가' 빛 크기). 빛 세기 맞춤은 안 켜짐(띠 밝기 7.0 ↔ 9.8 — 차 < 문턱/2) → L-1 길 그대로. 단 '체인 버스트' 는 렌더가 오른쪽 끝 맞춤으로 약 11 px 오른쪽(이번엔 글자 폭 차가 커 '폭 근사' 판정 — 위 E6 와 같은 L-1 기존 결함, compare.png 에서 보임) |

- **사람 눈 몫(L-2 compare.png 에서 보이는 근사 — 진단 기준 안):** '3' 참고판은 기울임 세리프 ↔ 렌더 바로 선 세리프(글꼴 모양) · '4.2' 참고판의 그라데이션 입체감 ↔ 평평한 크림색 · '오의 불가' 렌더 빛이 더 세고 붉음(빛 세기 30.7 ↔ 42.7 — 둘 다 '있음'이라 오류 아님) · 참고판의 얇은 짙은 붉은 외곽선은 렌더에 없음(외곽선 측정 0). 아트(배너 · 체인 패널 · 게이지)는 원본 아트 픽셀 그대로.
- **시험:** pytest **363**(355 → +8 `tests/test_followup_l2.py` — 참고판 프롬프트 · 글자 획만 붙이기(색조 · 어긋남 · 반투명 가장자리) · 칸 밖 검사 · normalize L-2(참고판 있음 · 없음) · 글자 그린 아트 물러남 · make_concept 다시 그리기 · 물러남), 정답 묶음 18/18.
- **디자이너 미리보기 = 컨셉 상태(사용자 눈 11-18 — WidgetMcp C++ 승인):** `WBP_CombatHUD` 를 UMG 디자이너에서 열자 게이지 빈 트랙 오른쪽이 황갈색으로 옅어짐 — 결함이 아니라 **디자이너가 위젯 Visibility 를 무시하고 'Hide in Designer'(`bHiddenInDesigner`)만 본다**[소스 UMG `Widget.cpp:1482` '디자이너에서는 늘 보이는 상태']. 런타임에 접힌 `UltReadyGlow`(게이지 가득 참 빛)가 반투명 빈 트랙 뒤로 비친 것(force_visible `render.png` 도 같은 모습 [실측]). 사용자 결정 = 컨셉 상태로(컨셉이 그린 숨은 배너 · '오의 불가' 는 보이게). spec 위젯 `designer_hidden`(새 필드, 기본 false 는 키 없음 — `core/spec` · WidgetMcp 정규형 같음) → WidgetMcp `ApplyWidget` 이 `bHiddenInDesigner` 로 · 역추출 `ExportWidgetProps` 가 내보냄(C++ 3 곳, 빌드 2 구성). `finalize._designer_hidden` 이 저장 직전 마지막 진단의 '컨셉이 안 그린 숨은 위젯'(`state.force_visible_extra` · 시작 때 숨음)에만 켜 `apply_widget_spec` 한 번 더(런타임 · 렌더 무관, 실패해도 저장 — 기록 `report.finalize.designer_hidden`). pytest 364(+1). [실측 확인 run `R20261118_155806_CombatHUD` — 오류 0 · 근사 3, finalize 가 `UltReadyGlow` 하나만 켬, 저장된 WBP 역추출 `designer_hidden` = [UltReadyGlow](접힌 셋 중 배너 · '오의 불가'는 디자이너에 보임)] · `WidgetMcp.` 처음 5/6 — 실패 1 `WidgetMcp.Tools.ImportFont` 는 **K 부터 낡은 기대값**(굵기 어휘 밖 예로 'Medium' 을 쓰는데 K 가 Medium 을 어휘에 넣어 거절 안 됨 → 시험 글꼴 패키지가 생겨 quit 거절 — 저장 안 된 시험 패키지만 버리고 내림, 디스크 파일 없음) → 사용자 승인으로 예를 'Thin' 으로 고침(`WidgetMcpToolTests.cpp`), 빌드 2 구성 · 에디터 1 회 **`WidgetMcp.` 6/6**.
- **빛 세기 = 가장 가까운 선택(사용자 판단 11-18 — compare.png '오의 불가' 렌더 빛이 더 세고 붉음):** 진단은 둘 다 빛나면 크기 차만 근사로 보고 세기는 안 봐, 어휘(빛 색 알파)에 더 가까운 선택이 있는데도 오류가 아니었다(K 원칙 E9 의 사각지대). `diagnose.compare_text` — 둘 다 빛나고 띠 밝기(`glow_measure` peak) 비 > 1.25 · 차 ≥ 문턱/2 이면 알파를 더 내리거나 올릴 수 있을 때 **E9 `glow_strength`**, 알파가 끝(0.15 · 1.0)이면 근사 `glow_strength`(나쁨 점수 |log 비| × 20). 글자 맞춤 `style._glow_strength`(크기 판, 빛 크기가 ±1 안일 때) — 새 알파 = 알파 × 컨셉 ÷ 렌더 띠 밝기 [실측 — 엔진 빛 띠 밝기는 알파에 거의 비례: 0.957 → 0.52 에 41.0 → 21.3. 처음 쓴 선형 휘도(L* 세제곱) 모델은 절반으로 내려 반대로 어긋남(run `163950` 오류 1)], 마지막 크기 판(`text_fit_size_final`)도 이 원인에서 돈다. 정답 묶음 +1('오의 불가' 빛 세기 — `142524`, snapshot 이 원본 아트 파일도 복사) **19/19**. 기준선: L-1 원래 전투 HUD `114547` 의 '오의 불가'(12.2 ↔ 7.0)도 걸림(맞춤이 고칠 대상), controls 두 run 은 그대로 오류 0. [실측 run `R20261118_164931_CombatHUD` — **오류 0 · 근사 4**(굵기), '오의 불가' 띠 밝기 30.7 ↔ 29.9 · 크기 8 ↔ 8(알파 0.96 → 0.71) · 높이 비 1.00 · 위치 0 px, compare.png 직접 확인]. 참고판의 얇은 짙은 외곽선은 엔진이 빛과 외곽선을 같은 층으로 그려(`_fit_outline` 은 빛 글자에 안 넣음) 못 냄 — 근사(측정도 투명 바탕 위라 '바탕보다 어두움'이 0).
- **'체인 버스트' 정렬 끝 판정 갈림(사용자 승인 11-18 — L-1 `171644` 에서 렌더가 11 px 오른쪽):** 원인 둘 [실측 `171644` 시도 6] ① 위치 판이 자간(+2 px — 획 사이 틈 51 ↔ 40 열)을 넣으면서 '끝 맞춤 · 가운데 맞춤'은 **자간 전 폭**(폭/높이 0.90 → 오른쪽 끝)으로 정했고, 진단은 자간 뒤 폭(0.937 — 모양 차 8 % 안 → 가운데)으로 재 6.5 px E6 ② 획 밀도가 상자 전체(빈 열 포함)라 자간에 밀도 비 0.936 → 0.898 로 굵기 E9 가 새로 생김 → 판이 통째로 버려져 오른쪽 끝 맞춤(폭 근사)로 남았다. 고침: 위치 판 판정은 자간 뒤 예상 폭으로(`style.text_fit` `w_over_h_after` — 진단과 같은 상태) · 획 밀도는 **잉크 있는 열만**(`diagnose._stats` — 진단 · 글자 맞춤 공용, 빈 열 = 낱말 · 글자 사이 틈 뺌) + 굵기 표 `fonts.weight_density` 를 같은 정의로 다시 잼(PIL — 예전 정의 값은 기존 표와 ±1.5 % 로 재현, 새 정의는 무거운 굵기에서 3 ~ 5 % 낮음: Pretendard Bold 1.488 → 1.433 · Noto Black 1.692 → 1.672). 정답 묶음 19/19 그대로, pytest 366(+1).
  - **끝 run [실측 — 하나씩]:** L-1 원래 전투 HUD `R20261118_175104` — '체인 버스트' **가운데 차 (−1.5, −0.5) px · 폭 근사 없음(해결)**, 그러나 **오류 1(E1 — 체인 패널 '인' 오른쪽 아래 8 × 6 px, ΔE 27) = 진단 거짓 양성** [오프라인 확인 `uigenL2/blob_probe.py` · `owner_probe.py`]: 그 자리는 '인' ㄴ 받침 가로획(컨셉 · 렌더 둘 다 밝은 획 L* 55 ~ 84, 텍스처 · 글자 없는 판 9 — 렌더는 약 1 px 아래)인데, '4.2'(빛 글자)의 analyze 상자가 빛 여백만큼 넓어져(높이 135) '체인' 아래와 겹치고, `assign_glyphs` 의 '한 센 획이 두 글자 구역에 걸치면 픽셀로 나눔'(J — 빛으로 이어진 이웃 글자용)이 그 획 일부를 '4.2' 몫으로 줘 '4.2' 의 `_filter_glyph_parts` 가 버림 → 어느 글자 획도 아니라 바탕으로 셈. 처음 추정(컨셉 얇은 그림자)은 틀림 — 그 차이는 한쪽 그림자가 아니라 획 사방 L* 5 ~ 6 의 옅은 어두운 테라 그림자 측정(≤ 3)에도 외곽선 기준에도 안 걸림(근사로 남음). 고침(다음 일): 두 글자 구역에 걸친 센 획은 다수 쪽 · 이어진 본체 쪽으로 — J 규칙 이력 때문에 정답 묶음 · 다섯 입력 재측정 필요. L-2 전투 HUD `R20261118_175732` **오류 0 · 근사 2**, controls_alpha `R20261118_180405` **오류 0 · 근사 4**. 세 compare.png 직접 확인.
- **진단 거짓 양성 E1 고침 — 겹친 글자 상자 안 센 획의 주인(11-18, 미커밋 — 새 세션. 쓰기 = Tools/uigen · 이 문서):** [실측 추적 `175104`] ㄴ 받침(센 획 91 px)은 '체인' core 와 '4.2' core(빛 여백 뺀 상자 [1650, 209, 128, 121] — 빛 7 만 빼도 '4.2' 실제 획(y 242 ~)보다 33 px 위까지)에 **둘 다 통째로** 들고 자기 구역(다른 core 와 안 겹친 곳) 픽셀은 둘 다 0 — J 의 '센 획도 한 덩어리 → 픽셀마다 상자 거리'(`n2 ≤ 2`) 갈래에서 상자 중심 거리로 오른쪽 반이 '4.2' 몫이 됐다(J 이력: 빛 번짐으로 이어진 'Lv' · '100' · 이름 `201408`, 넓은 렌더 '3' 에 붙은 '/' `211123`). 본체 거리: '체인' 4 ~ 5 px ↔ '4.2' 18 ~ 23 px. 고침(`diagnose.assign_glyphs`): 센 획 하나가 **두 글자 이상의 자기 구역에 15 px · 10 % 이상씩 걸칠 때만 픽셀로**(J 그대로 — 붙은 '3/' · 빛으로 이어진 이웃 글자), 아니면 통째로 — 컨셉 획(렌더 prior) → 자기 구역 증거가 한 글자뿐이면 그 글자(다수 쪽) → 겹친 core 안에만 있으면 **이어진 본체**(증거로 정한 그 글자의 다른 센 획까지 ≤ max(6, 0.3 × core 높이) · 다른 후보보다 2 배 이상 가까움 · 후보 모두 본체 있음 — 본체는 첫 패스에서 모으고 한 번만 판정해 잇달아 번지지 않음) → 예전 무게중심 상자 거리. 무게중심이 core 둘 이상에 든 증거 없는 작은 덩어리(센 획 40 px 미만)도 같은 본체 판정.
  - **재측정 [실측 — 옛 규칙을 스크래치에 그대로 두고 같은 run 을 새 · 옛으로 오프라인 진단, `uigenE1/ab_compare.py`]:** 최근 run 11(L-1 `175104` · L-2 `175732` · controls `180405` · 단색 `124503` · controls `125054` · 조작 안내 원본 `125624` · 파티 `130201` + J 나눔 근거 파티 `201408` · `204115` · `211123` · `215853`) + 정답 묶음 run 10. 결함 목록이 바뀐 것: ① '체인' ㄴ 받침 E1 거짓 양성이 `175104` · `235644` · `003804` **셋에서 사라짐**(같은 원인), `235644` 는 잘린 받침 탓 '체인' 크기 E9 도 사라짐 ② L-2 `175732` '체인' · `142524` '2/4' 에 **새 E9 굵기** — 옛 측정이 받침 63 px · '2/4' 윗줄 4 ~ 5 줄(→ '4.2' 몫 → 걸러짐)을 빼고 재 밀도 비가 근사 범위 안(0.909 · 1.092)이던 것이, 글자 전체로 재자 0.824('체인' bold → black 이 가까움, 확대 그림에서도 참고판이 뚜렷이 굵음) · 1.121('2/4' semibold → medium) — 거짓 양성이 아니라 잘린 측정이 가리던 실제 굵기 차. 글자 맞춤도 같은 마스크(`run_text_masks`)로 재므로 새 L-2 run 에서는 맞춤 대상 ③ 파티 `192631`(J 시절 run) HP 최대치 — 렌더 '3' 이 넓어 오른쪽 조각이 최대치 core 와 겹쳐 최대치 몫이던 것(폭 비 1.18 · 'size' E7)이 현재치로 → 최대치는 '/' 부터(폭 비 0.98 · 위치 E6) — 같은 run 의 같은 위젯 오류가 원인만 바뀜. 나머지 run 은 결함 목록 그대로(J 나눔 근거 run 셋 포함 — 측정값 소수 셋째 자리만).
  - **정답 묶음 '오류가 아니어야 하는 자리'(검토 → 넣음):** 지금 묶음은 놓침만 막고 거짓 양성은 못 막아 이번 고침이 되돌아가도 모른다 → `golden.py` 항목 `expect: none` + `box`(그 자리와 겹치는 결함만 셈 — 같은 글자의 다른 정상 결함과 섞이지 않게), 첫 항목 = '체인' ㄴ 받침(`175104` 사본, 1.7 MB). `check` 출력 'n/n caught · n/n clean', `tests/test_golden.py` 는 거짓 양성도 실패. 옛 규칙으로는 그 사본에서 E1 [1737, 218, 8, 6] 이 걸림(확인).
  - **시험:** 정답 묶음 **19/19 caught · 1/1 clean**, 합성 시험 `test_stroke_only_inside_overlapping_cores_goes_whole_to_its_connected_body`(옛 규칙에서는 받침 19 px 가 B 몫으로 실패 — 확인), pytest **367**(366 → +1).
  - **끝 run [실측 — `uigenL/run_set.py` 1 회, 끝나고 에디터 내림 · compare.png 직접 확인]:** 원래 전투 HUD L-1 `R20261118_184602_CombatHUD` — **오류 0 · 근사 0**(시도 6: 1 iou_leaf + 진단 → 2 ~ 5 글자 맞춤 판 → 6 `text_fit_size_final` 뒤 통과). 글자 6 개 위치 ≤ 1.5 px · 높이 비 0.97 ~ 1.04 · 폭 비 0.88 ~ 1.0 · 밀도 비 0.97 ~ 1.04(굵기 표에서 가장 가까운 굵기) · 색 ΔE00 ≤ 1.5 · 빛 크기 7 ↔ 6('4.2') · 6 ↔ 5('오의 불가'), 글자 구역 바탕 국소 최대 **2.5**(고치기 전 `175104` 27.3), '체인 버스트' 가운데 차 (0, −1.5). compare.png 에서 '인' ㄴ 받침이 컨셉 · 렌더 둘 다 그대로. 진단 기준 밖 사람 눈 차이(전과 같음): '4.2' 의 그라데이션 입체감 ↔ 평평한 크림색 · '3' · '2/4' 세리프 모양(글꼴 모양 — 근사 표 항목 아님).
  - **남은 것:** L-2 run(`fixtures/m4_combat_hud_l2`)은 새 측정에서 '체인' · '2/4' 굵기 E9 가 나오는 상태 — 글자 맞춤이 같은 마스크로 고칠 대상이지만 실제 run 으로는 미확인.
  - **굵기냐 글꼴 모양이냐(사용자 질문 11-18 — '폰트 차이로 감안해도 되지 않나'):** 모양 · 폭과 무관한 평균 획 두께(핵심 획 넓이 ÷ 둘레의 절반, 4 배 확대)로 다시 잼 [실측 `uigenE1/stroke_width.py`, PIL 같은 몸통 높이 굵기별 두께와 비교]. L-2 '체인' 컨셉 3.92 ↔ 렌더 bold 3.29(컨셉 19 % 두꺼움) — Noto black 은 bold × 1.194 = 3.93 으로 **한 굵기 단계와 거의 정확히 같다** → 모양 차가 아니라 굵기 차. L-2 '2/4' 컨셉 4.28 ↔ 렌더 semibold 4.79(11 % 두꺼움) — medium 은 3.96(7.5 % 얇음): medium 이 조금 더 가깝지만 **두 굵기 사이**(중간 굵기 근사에 가까움). 대조: L-1 `184602` '체인' 0.94 · '2/4' 0.98(지금 굵기가 맞음). 진단 밀도 비(0.824 · 1.121)도 획 두께 비와 같은 방향 · 크기.
  - **L-2 확인 run [실측 — 사용자 요청, `run_set.py` 1 회 · 에디터 내림 · compare.png 직접 확인]:** `R20261118_191532_CombatHUD` **오류 0 · 근사 2**(굵기 — '체인 버스트' black 밀도 비 1.06 · '3' bold 0.933), 시도 7(LLM 외형 라운드 1 받았다가 되돌림 → 글자 맞춤 판 셋). 글자 맞춤이 같은 마스크로 **'체인' bold → black**(획 두께 컨셉 3.92 ↔ 렌더 3.90, 밀도 비 0.987) · **'2/4' semibold → medium**(4.28 ↔ 3.95 — 두 굵기 사이, 밀도 비 1.018). 글자 6 개 위치 ≤ 1.5 px(단 '3' 은 (−5, 0) — 허용 6 안, 기울임 세리프 ↔ 바로 선 세리프 모양 차) · 글자 구역 바탕 국소 최대 0.48. 관찰: '3' 은 획 두께로는 컨셉이 41 % 두껍지만(기울임 · 음영 입체 숫자) 밀도 비로는 bold · black 차가 여유 0.06 안이라 근사 — 두 측정이 갈리는 글자(모양이 다른 글꼴은 밀도가 덜 민감).
  - **증거 정리(11-18 사용자 승인 — 휴지통):** 끝 run `R20261118_184602_CombatHUD`(L-1) · `R20261118_191532_CombatHUD`(L-2)의 work · `Content/_AutoGen/` 과 정답 묶음 사본 `work/_golden/R20261118_175104_CombatHUD` 는 남겼다. 스크래치 `uigenE1`(추적 · 새 · 옛 비교 · 획 두께 스크립트와 그림, 약 1 MB) · 옛 함수 진단 출력 `uigenL/e1_before` 는 휴지통 — 위 숫자는 이 글로만 남는다.
- **한계 · 남은 것:** 가득 찬 게이지(≥ 0.97 — J 는 요소 없는 판으로 빈 트랙)와 concept_fill 아닌 게이지는 원본 아트에 빈 트랙 정답이 없어 채움이 판에 남는다(이번 HUD 는 concept_fill 70 % 라 해당 없음 — 필요하면 요소 없는 판 codex 1 회를 L-2 에 더함) · 참고판 검사 탈락(사양만) 길은 단위 시험뿐(실제 run 없음) · 원래 전투 HUD L-1 E6(위 표) · 외부 · 단색 입력 결함과 검증 틀은 다음 세션.

**1b 후속 L 다음 — 외부 · 단색 입력 검증 틀 + L-2 성과 보호 항목 (11-18, 미커밋 — K ~ L 은 사용자 커밋 `93b91c5`. 새 세션. 쓰기 = Tools/uigen · 이 문서, C++ · 에디터 run 없음 — 오프라인 진단 · replay 만. 결함 고침(판 글자 메우기 `refine._plate_item_fill` · 글자 맞춤 `style.text_fit`)은 다음 단위 — 사용자 요청 때)**

- **왜(사용자 결정 11-18):** L-1 · L-3 에서 판 메우기 규칙 하나를 고칠 때마다 다른 입력 · 다른 글자에서 새 결함이 났고(배너 '3' · 패널 '2/4' · 배지 'E' · 'T'), 사람 눈 결함 일부는 진단이 '오류 0' 이었다. → 고치기 전에 ① 사람 눈 결함을 정답 묶음에 ② 진단 사각지대를 메우고 ③ 지금 잘 나온 run 을 '오류 0 유지'로 보호하고 ④ 여러 입력을 고치기 전후로 오프라인 비교하는 도구를 저장소 안에.
- **E1 획에 붙은 잔상 — `diagnose.glyph_residue` [실측 단색 `R20261118_120715` '2/4']:** 사각지대 원인 = 글자 구역 바탕 E1 이 모든 글자 획(컨셉 · 렌더 후보) + 2 px 와 컨셉 획 4 px 안 효과를 빼고 잰다. '4' 잔상은 텍스처가 컨셉 '4' 발 오른쪽 끝([1727, 286, 5, 3])을 남긴 것인데 렌더 '4' 가 더 좁아 안 덮는다 — 컨셉에서는 그 자리가 글자 획이라 늘 빠졌다(국소 최대 9.78 < 10). 그 자리는 컨셉이 글자라 '컨셉과 같나'로는 판정이 안 되므로 **글자 없는 바탕 추정**과 견준다: 자리 = 컨셉 획(후보 · 핵심 + 1 px) 중 렌더 글자(모든 글자의 렌더 후보 · 렌더 핵심 + 1 px)가 안 덮은 픽셀(렌더가 텍스처를 그대로 보여 주는 곳), 잔상 = 텍스처 합성과 렌더가 **둘 다** 두 추정 — ① 컨셉 글자 바깥(모든 글자 획 · 빛 반경 + 3 px 밖)의 가우스 가중 평균(σ 2 → 4 → 8 → 16) ② 글자 없는 판 ±2 px 이동 최소 — **모두**와 ΔE00 > `appearance.residue_de` 20 인 픽셀 덩어리 ≥ `residue_min_px` 6. 엔진 글자 차이(빛 · 그림자 · 외곽선 · 글꼴 모양 — 기울어진 '3', '4.2' 입체감)는 렌더에만 있어 텍스처 합성 쪽 min 으로 빠지고(텍스처 합성 ↔ 컨셉 · 렌더 ↔ 컨셉 min 과 같은 원리), 판이 지킨 구조선(금선)은 판 쪽 min 으로 빠진다. 기록 `diagnosis.json text_residue`, 결함 cause `residue — …`.
  - [실측] '4' 잔상 **11 px · 평균 ΔE00 31.3 · 최대 45.7**(텍스처 쪽 바탕 차 31.3 · 판 차 34.6). 오탐 — 20 넘는 픽셀: 보호 후보 다섯(L-1 `184602` · L-2 `191532` · controls_alpha `180405` · controls `125054` · 조작 안내 원본 `125624`) **0**, 그 밖 최근 run 일곱(`123805` · `175732` · `175104` · `164931` · `171644` · `142524` · `143847`) 0, L-2 run 은 최대 0.0(텍스처 = 원본 아트). 단색 `124503` 은 같은 자리 1 px 둘(안 셈). 새로 잡힌 것: 파티 `130201` 이름 오른쪽 끝 92 px · 평균 22.2(번진 회청색 상자 끝), J 시절 `192631` +18 · K `235644` +18(알려진 판 잔상 · 막대 위 띠 — 정답 묶음의 결함 run, 항목 판정 그대로).
- **컨셉 획 측정 실패 안전망 — `diagnose.concept_contrast` [실측 파티 `R20261118_130201` 'Lv 100', 사용자 결정]:** 먼저 위치를 쟀다 — 'Lv' 중심 차 (+0.5, +2.0) · 허용 3.2(**기준 안 — 사용자 결정으로 항목 아님**). 실제 차이는 '100': 렌더가 **검정(#010202) · 크기 40 → 52(획 상자 높이 38 → 약 52 ~ 57 px) · 빛 없음 · 외곽선 1**. 원인 — `LevelText` 는 판을 안 쓴 글자(`notext_unused` — 투명 위)라 컨셉 획 = 컨셉 ↔ 텍스처 합성 차인데, 텍스처가 그 자리를 불투명 회청색 상자로 메워(판 메우기 결함) 상자 전체가 '차'가 되고 핵심 획이 어두운 투명 틈(L* 0.5)으로 잡혔다. 글자 맞춤(`style._fit_color` · 크기 판 — 같은 마스크 `run_text_masks`)이 그 측정대로 색 · 크기 · 외곽선을 바꿨고(specs/000 #EDF2F4 · 40 · 빛 9 → 최종 #010202 · 52 · 외곽선), 진단도 같은 마스크라 색 차 0.37 · 높이 비 0.96 '같음'. 안전망: 컨셉 핵심 획 ↔ 둘레(핵심 획 밖 1 ~ 4 px 중 후보 밖) 대표색 ΔE00 < `CONCEPT_CONTRAST_MIN` 10 이면 '바탕을 글자로 잼' → 아무것도 비교하지 않고 **E6 unmeasured**(`text.unmeasured.concept_contrast`). [실측] 정상 글자 **39.5 이상**(보호 run · 단색 둘 · 정답 묶음 run 셋 — 가장 낮은 것 L-1 '오의 불가' 붉은 글자 39.5), '100' **0.5** · 이름 2.2(이름은 이미 unmeasured · 색으로 잡힘). 처음 후보 'analyze 글자색(specs/000)과 견줌'은 `125624` '점프' 71.6(analyze 색이 틀렸고 글자 맞춤이 고친 것)으로 오탐이라 버렸다.
  - **다음 고침 단위가 알 것:** 글자 맞춤은 이 안전망을 안 탄다 — 같은 판정(컨셉 대비 < 10 이면 그 글자 안 건드림)을 써야 '100' 을 안 망가뜨린다. 근본은 판 메우기가 투명 위 빛 글자 자리를 불투명 상자로 메운 것.
- **정답 묶음 — 새 항목 다섯 + 보호 넷:** ① '2/4' '4' 밑 잔상(`120715` E1 box [1723, 282, 13, 10] — 새 잔상 검사) ② '2/4' 아래 금선 위 혹(`124503` E1 box [1675, 295, 13, 9] — 글자 구역 바탕 [1677, 297, 9, 5]) ③ '2/4' 위치(`124503` E6 position — 중심 차 (3.5, 3.0) · 허용 3.3) ④ '0 %' 위치(`130201` E6 position — (−1.5, −10.0) · 허용 3.5) ⑤ 'Lv 100' → '100' 측정 실패(`130201` `LevelText` unmeasured). **보호 = `expect: clean_run`**(그 run 의 결함 하나라도 나오면 깨짐 — 진단 건너뜀도): L-2 `R20261118_191532`(오류 0 · 근사 2) · L-1 원래 전투 HUD `184602`(0 · 0) · controls_alpha `180405` · controls `125054`(지금 코드 오프라인 재진단 0). 조작 안내 원본 `125624` 는 지금 코드로 오류 1(E9 — 아래 기준선)이라 넣지 않음. `golden.py check` = 'n/n caught · n/n clean · n/n protected(errors 0)', `tests/test_golden.py` 는 보호 깨짐도 실패. 사본 7 run 추가(`work/_golden`).
  - [실측 — 새 코드] **24/24 caught · 1/1 clean · 4/4 protected**(397 초). 기존 19 항목 · '체인' 받침 '오류 아님' 그대로. 참고: L-2 `142524` '오의 불가' 항목의 결함은 이제 굵기 · 빛 세기 둘 다(이번 두 검사는 글자 측정값을 바꾸지 않는다 — 앞 단위 측정 정의 변경 몫).
- **오프라인 비교 묶음 — `regress_set.py`(저장소 안, 스크래치 `uigenL/run_set.py` · `baseline.py` · `fill_probe.py` 를 대신):** 고정 입력 `SET` 8 개(입력마다 대표 끝 run — 보호 표시 넷)를 ① 오프라인 재진단(run 의 렌더 · 텍스처 그대로 — 진단 규칙 변경을 봄, `compare.png` 포함) ② `replay_refine.replay`(run 사본에서 specs/000 으로 refine 만 — 판 메우기 · 오리기 규칙 변경을 봄) + **글자 상자 안 텍스처 지표**(렌더 없이 합성만 — 글자 구역 바탕 7 × 7 국소 ΔE00 최대 · p95 · 문턱 넘는 픽셀, 잔상 `glyph_residue(render=None)` — 자리는 컨셉 획 전체라 렌더가 덮어 진단엔 안 보이는 텍스처 잔상까지 셈) + 회색 위 합성 `gray.png` 로 재서 `work/_regress/<label>/`(git 무시)에 저장, 코드 상태(HEAD · 미커밋 diff 해시)를 `set.json` 에 적는다. `compare <옛> <새>` = 입력마다 오류 · 근사 수, 결함 새 · 사라짐(같은 오류 번호 · 위젯 · 상자 겹침, 글자 결함은 위젯만), 글자 측정값 차(높이 · 폭 비 · 중심 차 · 밀도 비 · 색 차 · 컨셉 대비 · 원인 · 근사 · 빛 띠 밝기), 글자 구역 바탕 · 잔상 · replay 지표 차, 보호 입력 오류 경고 + 글자 상자마다 '컨셉 | 옛 텍스처 | 새 텍스처 | 차(ΔE00 × 8)' 그림(텍스처가 ΔE00 1 넘게 바뀐 글자만, `--all-texts` 면 전부) → `compare_<옛>_vs_<새>/report.txt · summary.json · <입력>.png`. 규칙을 바꾼 뒤 에디터 run 전에 `run <새>` → `compare base_1118 <새>`.
  - [실측 — replay 충실도] L-1 `184602` replay 텍스처 ↔ run 텍스처 회색 위 ΔE00 최대 **0.0**(에셋 9 개 같음 — 지금 코드 refine 이 그 run 을 그대로 다시 만든다).
  - **기준선 `base_1118`(지금 코드, 11-18 — 입력마다 42 ~ 96 초):**

    | 입력 | run | 진단 오류 · 근사 | 오류 내용 | replay 회색 ΔE00 평균 | 글자 상자 텍스처 잔상(렌더 없이) |
    | :--- | :--- | :--- | :--- | :--- | :--- |
    | combat_l1(보호) | `184602` | 0 · 0 | — | 3.11 | 0 |
    | combat_l2(보호) | `191532` | 0 · 2 | — | 1.49 | 0 |
    | combat_flat_a | `120715` | 2 · 2 | E1 '4' 밑 잔상 · E9 '2/4' 크기 | 3.89 | '2/4' 12 px(최대 45.7) |
    | combat_flat_b | `124503` | 2 · 1 | E1 금선 위 혹 · E6 '2/4' 위치(+ 그림자) | 4.13 | '2/4' 12 px(최대 47.6 — 렌더 '2/4' 가 덮어 진단엔 1 px 둘) |
    | controls_alpha(보호) | `180405` | 0 · 4 | — | 0.00(판 = 컨셉 픽셀) | 0 |
    | controls(보호) | `125054` | 0 · 5 | — | 0.00 | 0 |
    | controls_orig | `125624` | 1 · 2 | E9 '회피' 굵기 | 0.00 | 0 |
    | party | `130201` | 13 · 3 | E1 7(바탕 6 · 이름 끝 잔상 1) · E6 4('100' · 이름 · HP 최대치 unmeasured, '0 %' 위치) · E9 2(빛 세기 'Lv' · HP 현재치) | 1.28 | 이름 96 px · HP 현재치 44 px |

    replay 회색 ΔE00 은 숨은 위젯까지 합성한 replay_refine 그대로의 값(입력 사이가 아니라 같은 입력의 옛 ↔ 새로 본다). 결정성 [실측]: 같은 코드로 `combat_flat_a` · `party` 를 다시 재 `compare base_1118 chk_1118` — 결함 · 측정값 · 텍스처 **차이 없음**. 비교 그림에서 '2/4' 칸 텍스처에 '4' 밑 잔상이 보이고, '4.2' 칸 텍스처엔 옅은 '4.2' 윤곽이 남아 있다(잔상 문턱 20 아래 · 렌더 글자 · 빛이 덮음 — 고침 단위가 볼 것).
- **남은 것(다음 고침 단위 — 사용자 요청 때):** 판 메우기 — 단색 '4' 밑 잔상(텍스처 잔상은 `124503` 에도 같은 12 px, 렌더 '2/4' 가 덮어 진단엔 안 보였을 뿐) · '2/4' 금선 위 혹 · 파티 투명 위 빛 글자 자리의 번진 불투명 상자('100' · 이름 — 측정 실패와 글자 맞춤 오작동의 뿌리). 글자 맞춤 — 컨셉 대비 안전망과 같은 판정으로 측정 실패 글자 건너뛰기 · '2/4' · '0 %' 위치 · 조작 안내 원본 '회피' 굵기(E9). 고친 뒤 순서: `regress_set run <새>` → `compare base_1118 <새>`(보호 넷 오류 0 · 측정값 차 확인) → `golden.py check` → 에디터 run.
- **시험:** pytest **371**(367 → +4 `tests/test_followup_lnext.py` — 잔상: 텍스처 획 끝 남김은 잡고 엔진 빛 · 렌더 획이 안 덮은 깨끗한 자리 · 판이 그린 구조물 · 렌더가 덮은 잔상은 안 잡음, 렌더 없는 모드 / 대비 안전망 → E6 unmeasured / 비교 결함 짝짓기 · 목록 길이 차(이 시험이 `_num_diff` 가 원인 목록 `['size']` → `[]` 를 같다고 보던 버그를 잡음)) + `test_golden.py` 보호 규칙. 정답 묶음 24/24 · 1/1 · 4/4. C++ · 에디터 run 없음.
- **정리(11-18 사용자 승인 — 휴지통):** 이 세션 스크래치 `uigenM`(조사 스크립트 · 확대 그림 · 시험 replay, 8.2 MB) · 결정성 확인 `work/_regress/chk_1118` · `compare_base_1118_vs_chk_1118` — 위 숫자는 이 글로만 남는다. 남김: 기준선 `work/_regress/base_1118`(48 MB — 다음 고침 단위의 옛 쪽) · `work/_golden` 새 사본 7 run. 다른 세션 스크래치(`uigenL` 등)는 건드리지 않음.

**1b 후속 L 다음 고침 — 외부 · 단색 입력 결함 고침 (11-19, 미커밋 — 새 세션. 쓰기 = Tools/uigen · 이 문서, C++ 변경 없음)**

- **방식:** 원인 추적은 스크래치 `uigenN`(`capture.py` — replay 중 `_plate_item_fill` 입력 저장 · `probe_fill.py` · `masks.py` 중간 마스크 그림) → 규칙마다 `regress_set run` · `compare base_1118` → 정답 묶음 → 에디터 run 하나씩(`uigenL/run_set.py`, run 마다 에디터 내림 · compare.png 직접 확인).
- **원인 [실측]:** ① 단색 '4' 밑 잔상 — 빛 여백으로 넓은 '4.2' 상자의 메움이 '2/4' 의 '4' 를 먹고 발 끝만 남겨, '2/4' 는 **앞 글자가 바꾼 그림**으로 획을 찾아 남은 발을 작은 덩어리로 버림(텍스처 잔상 12 px). ② 금선 혹 — 그 탓에 '2/4' 판 정합이 (0, −1) 로 어긋나 금선이 '판과 다른 획' · '판에 남은 글자 자국'(판 자기 미디언과 다름)이 돼 획 근처 금선 자리가 둘레 메움(투명 · 금색 섞임)으로. ③ 파티 '100' 뒤 불투명 남색 상자 — 투명 위 글자 둘레 고리 · 메움 원천에 **이웃 글자('Lv' · 이름) 빛**(알파 0.7 ~ 0.9)이 들어가 고리 알파 0.765. ④ 이름 자리 회청 · 초록 얼룩 — 컨셉 빛이 분석 빛 크기보다 넓어 획 둘레 고리도 빛 속(불투명)이라 '투명 위 글자'가 아니라 좁은 메움으로 가고 남은 빛 · 막대 색이 원천. ⑤ '0 %' — 트랙 끝에 걸친 글자 빛 고리가 트랙과 이어져 '지킬 구조물'(판 밝기 비 규칙)로 남음.
- **고친 것(`stages/refine._plate_item_fill` · `_narrow_neigh_fill`):** ① 판정(글자색 · 획 · 구조물 · 투명 판정 · 판 정합 · 메움 원천)은 모두 **원래 컨셉**(`orig`)에서, 결과만 지금 그림에 섞음(순서 무관). ② `others`(같은 판 · 조각의 다른 글자 상자) — 획 후보 덩어리 중 다른 상자 안 비율이 자기 상자보다 0.25 넘게 크면 빼고(`_drop_other_glyphs`), 둘레 고리 · 메움 원천에서 다른 상자(+2 px)를 뺌. ③ 판 글자 자국에서 글자보다 긴 가로 · 세로 선을 뺌. ④ 투명 위 글자 판정에 **판 알파**를 더함 — 획 + 빛 자리의 판 알파 중앙값 < 0.35 이고 (컨셉 둘레가 불투명이거나 글자 자리가 상자 밖으로 이어진 불투명 구조물과 10 % 이상 겹치면) **판 중앙값 메움**(판을 글자 높이 반 크기 중앙값으로 — 판의 글자 자국은 뭉갬, 알파 이득 없음), 이 길은 빛 자리(획 + 빛 + 5 px, 그 밖 빛 × 2 + 6 px 까지는 판에 그만큼 밝은 것이 없는 픽셀) 안에서 **길고 가는 선**(`_thin_lines` — 위아래 3 px 와 채널 최대 차 > 48 인 긴 줄, 밝기로 재면 초록 막대 위 청록 윗선을 못 잡았다) · 판과 ±2 px 같은 픽셀만 지킨다. 둘레가 투명하고 구조물과 안 겹치면 예전 둘레 메움(판 중앙값은 단색 '오의 불가' 둘레 옅은 바탕 빛까지 지워 국소 9.9 → 12.9 — 되돌림). 진단 `notext_unused` 도 판 중앙값 메움 글자를 '판 그대로 안 씀'으로. ⑤ 글자색 추정 검사 `_glyph_like` — 잰 글자색 근처 픽셀이 상자 테두리에 닿는 면(띠)이고 사양 글자색 쪽이 0.2 이상 더 글자 같으면 사양색(controls_alpha 새 analyze 상자에서 '돌진 공격' 색이 띠 (44, 136, 192) 로 잡혀 텍스처에 글자가 남음 — 아래).
- **글자 맞춤(`stages/style.text_fit`):** 진단과 같은 컨셉 대비 안전망(`run_text_masks` 가 `concept_contrast` 를 실음 — < 10 이면 그 글자 건너뜀). 빛 크기와 세기가 반대로 가야 하면(키워야 하는데 렌더 띠가 이미 더 밝음) 세기(알파) 먼저 — 파티 '0 %' 빛 크기 11 ↔ 9 · 띠 22.6 ↔ 27.1 에서 크기 판이 띠를 31.1 로 올려 버려지고 E9 가 남았다(run `R20261119_002317` 오류 1).
- **진단 E1 baked(`diagnose.baked_glyphs`):** 컨셉 획 = 컨셉 ↔ 텍스처 합성 차라 텍스처가 컨셉 글자를 그대로 남기면 획이 비어 **말없이 건너뛰었다**(렌더 = 남은 글자 + 엔진 글자 이중, 진단 오류 0 — controls_alpha `R20261119_004119` compare.png 에서 이 세션이 발견). 글자 상자 안 컨셉 ↔ 글자 없는 판 차 > 48 인 픽셀(≥ 60) 중 텍스처 합성이 컨셉과 24 안으로 같은 몫 ≥ 0.6 이면 E1 `baked`. 정답 묶음 항목 추가.
- **오프라인 비교 [실측 `compare base_1118 n2`]:** 보호 넷 · 조작 안내 원본 텍스처 변화 0. 단색 '2/4' 칸 텍스처 잔상 12 → 0 px · 글자 구역 바탕 국소 최대 21.8 → 1.8(두 run 모두). 파티 — 'Lv 100' 칸 58.7 → 1.2 · 이름 58.2 → 10.3 · '0 %' 17.6 → 6.5 · 'Lv' 10.8 → 3.7, HP 칸 그대로(둘레 메움 길).
- **끝 run [실측 — 하나씩 · run 마다 에디터 내림 · compare.png 직접 확인]:**

  | 입력 | run | 결과 |
  | :--- | :--- | :--- |
  | 단색 전투 HUD | `R20261119_001742_CombatHUD` | **오류 0 · 근사 3**(굵기 '4.2' · '2/4' · '오의 불가') — '2/4' 크기 · 위치 · '4' 밑 잔상 · 금선 혹 해결 |
  | 파티 HUD | `R20261119_002317_ProbePartyHUD` → `R20261119_003127_ProbePartyHUD` | 오류 1(E9 '0 %' 빛 세기) → 빛 세기 먼저 고침 뒤 **오류 0 · 근사 10**(굵기 · 폭 — HP 숫자 폭은 J 때 남은 '좁은 숫자 글꼴' 사용자 결정 · '0 %' 빛 크기). 'Lv 100' 흰 빛 글자 · 맞는 크기, 이름 · '0 %' 위치 맞음 |
  | 조작 안내 원본 | `R20261119_003647_ProbeControlGuide` | **오류 0 · 근사 3**('회피' 굵기 해결 — 옛 run 은 '잉크 있는 열만' 밀도 정의 전 맞춤) |
  | 원래 전투 HUD L-1(보호) | `R20261119_005755_CombatHUD` | **오류 0 · 근사 1** |
  | 원래 전투 HUD L-2(보호) | `R20261119_010312_CombatHUD` | **오류 0 · 근사 2** |
  | controls_alpha(보호) | `R20261119_004119` · `004942` · `005341` → `R20261119_090205` · `091024` | 004119 진단 오류 0 이지만 '돌진 공격' 이중(위 E1 baked · 글자색 추정 고침 — 오프라인 메움 구멍 448 → 5 081 px 확인). 고침 뒤 두 run 은 **시도 1 analyze 배치 흔들림 → iou_leaf 실패 → LLM 정정이 `draw_as: none` 브러시에 image_size 를 넣음 → 엔진 정규형이 버려 `VALIDATION_FAILED`**(기존 결함 — 아래 후속 설계로 실패 경로만 고침) → 고친 뒤 **오류 0 · 근사 5** · **오류 0 · 근사 4** |

- **시험:** pytest 379(371 → +8 `tests/test_followup_lfix.py` — 원래 컨셉 판정 · 이웃 상자 원천 빼기 · 판 중앙값 메움과 막대 윗선 지킴 · 가는 선 · `notext_unused` · 글자 맞춤 대비 건너뜀 · 글자 같음 · E1 baked; 순서 시험은 합성 장면에서 옛 길도 통과 — 실측 재현은 비교 묶음). 정답 묶음 **25/25 caught · 1/1 clean · 7/7 protected**(새 항목 '돌진 공격' 이중 · 보호 셋 — 이번 끝 run 단색 · 파티 · 조작 안내 원본). `regress_set.py` SET 에 이번 끝 run 여섯(보호 다섯) 추가, 기준선 **`base_1119`**.
- **controls_alpha 실패 — 후속 설계(11-19, 사용자 승인 '추천안대로 구현' — (가) + (나) + (다) 구현 · 아래 '구현 · 결과'):**
  - **사슬 [실측 · 소스]:** ① analyze 배치가 흔들린 run 에서 시도 1 `iou_leaf` 실패 — 판이 그린 아이콘 · 배지 자리를 `draw_as: none` Image 로 두고 Overlay · 박스 슬롯에 넣으면 Slate 원하는 크기 = 브러시 ImageSize(기본 32 × 32)라 잎 상자가 줄어든다(통과한 `004119` · `180405` 는 시도 1 에 이 실패가 없음). ② LLM fixer 가 그 브러시에 `style.brush.image_size` 를 넣음(이유는 맞음). ③ WidgetMcp 적용 `BrushFromJson` 은 모든 그리기 종류에서 image_size 를 읽어 ImageSize 로 넣지만(`WidgetMcpSpec.cpp:440`), 역추출 `BrushToJson` 은 NoDrawType 이면 image_size 를 안 내보내고(`:510`) 정규형(C++ `NormalizeBrush` · Python `core/spec.normalize_brush`)도 none 엔 기본값을 안 둠 → 적용 검증 'applied tree differs' → `VALIDATION_FAILED`. ④ 재시도 루프(`run_pipeline` 시도 → fix → build)는 build 거절을 받지 않아 run 이 멈춘다(외형 라운드는 K 부터 받음 — `run_pipeline.py:432`).
  - **원칙:** 잘 되던 길(통과 run · 결정적 고침 · refine · 진단)은 건드리지 않고 **실패 경로에서만** 고친다.
  - **(가) 안전망 — Python:** 재시도 루프에서 fix patch 뒤 build 가 `StageError` 면 run 을 멈추지 않고 그 시도의 spec 으로 되돌린 뒤 build 오류를 붙여 fix 를 1 회 다시(그래도 안 되면 지금처럼 NO_FIX). 외형 라운드 받기와 같은 모양.
  - **(나) 어휘 가드 — Python:** `stages/fix` patch 가드에 '편집기가 담지 못하는 값' 검사 — 패치 뒤 `draw_as: none` 브러시에 image_size 가 있으면 거절하고 LLM 에 대안을 알림(크기가 필요하면 `draw_as: image` + 투명 색 `#FFFFFF00` + image_size — 어휘 안이고 아무것도 안 그림, 또는 슬롯으로). 거절 → 1 회 재요청은 기존 가드 길.
  - **(다) 결정적 고침 — Python(선택):** `iou_leaf` 실패 잎이 `draw_as: none` Image 이고 캔버스가 아닌 슬롯이면 결정적 fixer 가 위 투명 image 브러시 + image_size = bbox_intent 크기 op 를 낸다 — LLM 흔들림 없이 시도 2 에서 풀림. 실패한 잎에만 닿는다.
  - **(라) 어휘 맞춤 — C++(사용자 승인 필요 · 이번 추천 아님):** 역추출 · 정규형이 none 브러시 image_size 도 담게(기본 32 × 32). 엔진 동작은 그대로지만 none 브러시가 있는 모든 spec 의 정규형 · revision 해시가 바뀐다.
  - **추천:** (가) + (나) + (다). C++ · refine · 진단 · 글자 맞춤 무변경. 검증 = pytest(재시도 루프 build 거절 · 가드 · 결정적 op 시험 추가) · 정답 묶음(진단 무변경이라 같아야 함) · `regress_set` 보호 입력 텍스처 차 0 · 에디터 run controls_alpha 1 ~ 2 회 + L-1 1 회.
  - **구현 · 결과:** (가) `run_pipeline._refix_after_build_rejection` — 시도 k 의 build 가 `StageError` 이고 직전 시도의 fix patch 가 build 분기면 거절된 patch 를 `patches/<k−1>_rejected.json` 으로 남기고 `specs/<k−1>.json` 으로 되돌려 `fix.propose(…, rejected=[이유])` 1 회(LLM 프롬프트에 '편집기가 거절 — 되풀이 금지'), 새 patch 도 build 분기일 때만 다시 build · 두 번째 거절이나 다른 분기는 원래 오류 그대로. (나) `fix.vocabulary_errors` — LLM patch 사본 적용 뒤 patch 가 건드린 위젯에 `draw_as: none` + image_size 가 남으면 거절 이유(대안: 투명 image 브러시 `{draw_as: image, color: #FFFFFF00, image_size}` 또는 슬롯)로 기존 1 회 재요청 길. (다) `fix._none_image_leaf_ops` — `iou_leaf` 실패 잎이 캔버스 밖 슬롯의 `draw_as: none` Image 면 결정적 op `set style.brush = 투명 image 브러시 + image_size = bbox_intent 크기`(그 잎은 영역 이동 후보에서 뺌). 투명 image 브러시는 합성(`backdrop._brush_layer` — 에셋 없음 = 색 채움, 알파 0)에서도 아무것도 안 그린다.
  - [실측] pytest **382**(+3 `tests/test_fix_rejection.py` — 가드 거절 · 안 건드린 위젯은 안 봄 · 결정적 투명 브러시 op · 캔버스 잎 · 보이는 브러시는 옛 길 · 재시도 루프 되돌림 + 1 회만 + 첫 시도 build 실패는 안 받음), 정답 묶음 **25/25 · 1/1 · 7/7** 그대로. 에디터 run: controls_alpha `R20261119_090205` **오류 0 · 근사 5**(시도 1 iou_leaf 는 글자 `RKeyText` — LLM padding 으로 통과) · `R20261119_091024` **오류 0 · 근사 4**(시도 1 구조 게이트 통과), L-1 `R20261119_091634` **오류 0 · 근사 1** — 셋 compare.png 직접 확인('돌진 공격' 이중 없음). **두 controls_alpha run 모두 analyze 배치가 none Image 잎 실패를 내지 않아 (가) · (나) · (다) 길은 실제 run 에서 아직 안 탔다**(단위 시험으로만 확인 — 그 흔들림이 다시 나면 run 기록 `attempts[].refixed` · `patches/*_rejected.json` 으로 보임).
- **남은 것 · 사용자 결정:** ① (가) · (나) · (다) 실제 run 확인은 analyze 흔들림이 다시 날 때 ② 파티 HP 숫자 폭(좁은 숫자 글꼴 — J 때부터) ③ 근사 표의 굵기 · 빛 크기 ④ (라) C++ 어휘 맞춤은 안 함(필요해지면 사용자 승인).
**Phase 1 마감 회귀 (11-19, 사용자 요청 — 필수만) [실측]:** 마지막 전체 회귀는 G 끝(11-15)이었고 그 뒤 WidgetMcp C++ 가 두 번 바뀌어(K 굵기 어휘 · L-2 `designer_hidden`) L-2 때 `WidgetMcp.` 만 확인했었다. 빌드 DebugGame(11.0초) · Development `-DisableAdaptiveUnity`(3.2초 — 둘 다 이미 최신) `Result: Succeeded` → 새 DebugGame 에디터 1 회(브리지 12.5초 + 30초 대기): `AstralBreak.` **55/55**(389초) → `EditorMcpCore.` **2/2** → `WidgetMcp.` **6/6** → `quit_editor`(버린 것 = `WidgetMcp.Spike` 시험 WBP 1 개 `/Game/_AutoGen/Spike/…`) · 소멸 확인(6.6초, 남은 에디터 0). pytest 는 같은 코드로 고침 세션이 잰 **382** 를 그대로 둠(다시 안 돌림), 정답 묶음 **25/25 · 1/1 · 7/7** 은 이 마감 직전 다시 잼. → Phase 1(1a · 1b + 1b 후속 A ~ L 다음 고침) 마감 — 남은 것은 위 '남은 것 · 사용자 결정' 과 1b '다음으로 넘길 것'(컨셉 대역 · A3 · 재시도 codegen 분기 — 기록만), 커밋 · 사람 눈 확인은 사용자. **Phase 2 전 남은 단계(위 Phase 계획표):** '→ M4 C'(HUD 를 게임에 연결 — WBP 를 손으로 옮길지 · 승격 도구를 앞당길지 사용자 결정) · '→ 근사 다듬기'(선택 — 위 남은 것 ② ③), 둘의 순서는 사용자 결정.

**1b 후속 L 다음 — 상태 렌더 검증 + 좁은 고침 (11-19, 미커밋 — M4 단위 C 총괄 세션이 띄운 새 세션. 사용자 승인 '이 설계안 구현', 쓰기 = Tools/uigen · 이 문서, C++ · WidgetMcp 변경 없음 · 승격(8단계)은 총괄 몫)**

- **결함 [실측 — 사용자 인게임, M4 C 가 L-1 run `R20261119_091634_CombatHUD` 를 승격한 HUD]:** ① 오의 게이지 위 회색 둥근 상자 + 어두운 덩어리 ② 게이지를 꽉 채우면 오른쪽 끝 어두운 사각형. 컨셉은 문제없고, 매핑이 컨셉 한 장(한 상태)만 보고 픽셀 주인 · 다른 상태를 추측했고 진단도 그 상태 하나를 검정 바탕에서만 봐 추측을 성공으로 판정했다.
  - ① 원인(이 세션 재확인 — 총괄 추정과 다른 점): 판5 `UltBlockedText` 자리는 refine `_plate_item_fill` 의 '투명 위 글자 → 상자 + 2 px 둘레 메움'(`neigh_fill`, `refine.json` alpha_from 'concept neighbourhood')이 칠했다. 원천을 **미리 곱한 색으로만** 골라 아래 어둡고 불투명한 게이지 트랙(미리 곱한 색 ≈ 검정)을 '투명과 비슷'하다며 끌어왔고, 원천에서 먼 가운데는 원천 전체 중앙값(트랙 알파 0.98)으로 채워 반투명 갈색 상자 · 위 가운데 덩어리가 됐다(검정 위에선 거의 안 보이고, 진단은 글자를 컨셉 상태로 켠 렌더 · 글자 상자를 뺀 회색 합성만 봤다). 판에 들어간 경로(layer 글자 자리 90 % 규칙을 게이지 테두리 빛과 이어진 큰 덩어리가 통과)는 총괄 분석 그대로.
  - ② 원인: `concept_fill.render_concept_segment` 채움 텍스처 = 컨셉의 채운 구간 + 번짐 24 px(알파 = 트랙 전체 1 — 번짐 열은 어두운 빈 트랙 색 그대로 불투명), 막대 폭 785 = 트랙 761 + 24, 오른쪽 9-slice 여백 30 px 고정 → 100 % 에서 트랙 끝을 24 px 넘어 끝 장식을 덮음.
- **A 검증 — `gen/state_check.py`(새) + `gen/diagnose` 연결:**
  - **S1 숨김 흔적**(`hidden_trace`): 시작 때 숨는 위젯(`_hidden_roots` 의 subtree)을 모두 끈 게임 기본 상태를 검정 엔진 렌더(verify `render_state(overrides, name)` — 없으면 검정 합성) · 회색 · 흰 바탕 텍스처 합성으로 그리고, 컨셉이 그린 숨는 위젯(`hidden_state_split` drawn)마다 자리(글자 = 상자 + 빛 + 4 px, 그 밖 = 상자 + 4 px — 다른 보이는 글자 · 런타임 그림 자리 뺌)에서 둘레로 설명되지 않는 덩어리. 설명 = (가) 둘레 고리 6 px 의 가우스 가중 평균 σ 2 · 4(받침 있는 자리만) (나) 같은 줄 · 열 양끝 둘레 중앙값이 ΔE00 10 안이면 선형 보간(가로지르는 구조선 · 빛 띠) (다) 둘레 대표색(고리 중앙값) (라) 컨셉 글자 획 + 빛 + 3 px(글자 아닌 위젯은 상자) 밖에서 컨셉과 같음(그 자리 구조물 — 테두리 가운데 장식). 픽셀 차 = 그중 최소 ΔE00 → 자리 안만의 7 × 7 창 평균 > `local_de`(10) · 덩어리 ≥ `min_area`(24), 바탕 셋 중 하나라도.
  - **S2 게이지 끝**(`gauge_states`): 가로 게이지마다 진행률 0 · 0.05 · 1.0 렌더(엔진 — 없으면 합성 `backdrop._progress_layers` scale + box 그대로): 트랙(concept_fill 이면 잰 트랙, 아니면 막대 상자) 밖 · 막대 상자 + 8 px 안이 컨셉 상태 렌더와 **트랙 밖만의** 창 평균 > 10(트랙 안 채움 차가 번져 들지 않게 — 처음엔 그냥 창 평균이라 번짐 아닌 판도 걸렸다) → `gauge_outside` · 1.0 트랙 끝 구간(끝에서 max(8, 3 %) px × 가운데 절반 줄)이 0 렌더와 30 % 넘게 같음(ΔE00 < 5) → `gauge_end_short` · 0 엔진 렌더 트랙 안이 채움 없는 합성과 창 평균 > 10 → `gauge_zero_fill`.
  - **S3:** S1 회색 · 흰 바탕 지표는 숨는 글자 상자를 빼지 않는다(그 자리가 검사 대상 — `backdrop.text_mask` · 진단 글자 구역 제외 안 씀).
  - 기록 `diagnosis.json state_checks{mode, hidden_trace.roots[](자리 · 바탕별 국소 최대 · 덩어리 · 기록만 `overhang_px`), gauge_states.gauges[], findings[]}`, 오류 = **E8**(stage state, `check` 키) — `pipeline.yaml appearance.state_checks: record | error | off`. 엔진 렌더는 이름마다 폴더(`attempts/NNN/state_off` · `state_<게이지>_000|005|100` — `render_widget` 은 빈 폴더에만 씀).
  - **`compare.png` 상태 띠**(`diagnose._band_rows`): 맨 아래 ① 게임 기본 상태 — 엔진(또는 합성) 검정 | 회색 바탕 합성 | 흰 바탕 합성(절반 크기) ② 게이지마다 컨셉 상태 | 0 % | 5 % | 100 % 조각(1:1, 두 장씩).
  - **기록만 → 오류:** 정답 · 회귀 묶음 26 run 을 기록만으로 재진단 — 발견은 모두 같은 종류 실제 결함(확대 그림으로 확인), 거짓 양성 0 → `error` 로 올림. 정답 묶음은 기록만일 때도 발견으로 잡힘을 본다(`golden.matches` 가 `state_checks.findings` 도 봄 · 항목 `checks` 거르기).
- **B 고침(조건을 좁게):**
  - **F1 — refine 판 메우기에서(layer 아님):** `refine._hidden_text_fill` — 판 위 글자가 **시작 때 숨고**(`_starts_hidden` — 자기나 조상 visibility collapsed · hidden, flag 만 있고 보이는 체인 패널은 아님) **컨셉이 그 글자를 그렸을 때만**(상자 안 글자 없는 판과 > 48 차 픽셀 ≥ 5 % — 판 없으면 사양 글자색 근처) 자리(상자 + 빛 + 4 px — S1 과 같은 자리) 전체를 메운다. 자리를 가로지르는 불투명 구조물(자리 밖으로 이어진 알파 > 0.5 덩어리 — 글자색 · 빛 자리 뺌)은 3 px · 길고 가는 선(`_thin_lines`)은 1 px 넓혀 지키고, 판 마스크 밖은 안 칠함. 메움 = **경계값 보간**(`_harmonic_fill` — 빨강-검정 SOR, 첫 값 = 미리 곱한 색 · 알파가 **모두** 둘레와 비슷한 원천의 `_smooth_fill`, 세로 무게 0.05 — 줄마다 양끝 둘레를 잇고 줄 사이는 살짝, 판 상자 끝에 닿은 창 가장자리 = 투명 경계). 고친 판 셋 [실측 오프라인 replay 091634 · 흰 바탕]: `_smooth_fill` 만 → 가운데 원천 중앙값 대체 경계가 반원으로 · 등방 보간 → 아래 테두리 빛이 위로 번진 돔(알파 최대 0.15) · 비등방 + 투명 경계 → 자리 안 알파 평균 0.012(둘레 고리 값 그대로), S1 국소 최대 87.4 → 3.5. **layer 가 아니라 refine 을 고른 이유:** layer 에서 자리를 판 마스크에서 빼면 게이지 테두리 윗선까지 판에서 빠지고(구조선 보호를 마스크 단계에 새로 넣어야 함) 판 상자 · spec · 겹침 쌍 · 위젯 자리가 바뀌어 영향이 넓다 — refine 은 그 판 텍스처의 그 자리 픽셀만 바꾸고, 회귀 묶음 replay(refine 만 다시)로 전 입력을 잴 수 있다. 판 위 숨는 글자는 묶음에서 전투 HUD 의 '오의 불가' 뿐(L-2 아트 모드는 판에 글자가 없어 안 탐).
  - **F2 — 번짐 0:** 먼저 번짐 열 알파를 '빈 트랙보다 밝은 만큼'(절차 길 식)으로 준 판을 오프라인으로 쟀다 — 진행 끝 바로 뒤 빛(알파 0.75)이 100 % 에서 끝 장식 첫 5 px 에 남아 S2 트랙 밖 국소 최대 15.9 · 27 px > 10(최소 넓이 24 초과)으로 **미달** → 설계대로 번짐을 뺌. `concept_fill.measure` 는 번짐을 재서 `spill_measured` 로만 기록하고 채움 텍스처 · 막대 상자 · 오른쪽 여백에는 안 넣음(spill 0 — 막대 = 트랙, 여백 = 끝 테두리 6 px). 판 빈 트랙 색 표본 자리(`unfilled_track`)는 잰 번짐 뒤 그대로라 판 바이트 같음. 컨셉 진행률의 끝 빛(번짐)은 진단이 **근사 `gauge_end_glow`**(`state_check.end_glow_zones` — 트랙 줄 × 몸통 끝 − 3 ~ + spill_measured + 8, 국소 결함 상자의 60 % 이상이 그 자리면 오류에서 뺌) — 한 brush(scale + box 여백 고정)로는 컨셉 진행률의 끝 빛과 100 % 의 트랙 끝 맞춤을 같이 못 한다. 예전 spec(번짐 든 채움)은 예전 그림 그대로.
- **C 상태별 컨셉(codex 상태 변형) — 이번엔 안 함**(L-1 교훈: 다시 그린 그림은 색 · 빛이 어긋나 정답으로 쓰면 고친 얼룩 · 색 문제가 다시 남).
- **회귀 방지 [실측]:**
  - 기준선(지금 코드 — 고치기 전): `regress_set run pre_state_1119`(기존 `base_1119` 안 건드림) · 정답 묶음 **25/25 · 1/1 · 7/7** · pytest **382**.
  - `regress_set compare pre_state_1119 state_fix_1119`: **회귀(`+ new`) 결함 0**. 바뀐 텍스처 = `UltBlockedText` 글자 상자뿐(L-1 `184602` · `005755`, 단색 `120715` · `124503` · `001742`), L-2 · 조작 안내 · 파티 텍스처 변화 0, replay 상태 검사 숨김 흔적 국소 최대 → 1.2 ~ 3.4(덩어리 0). 글자 상자 텍스처 지표: L-1 `005755` 글자 구역 바탕 국소 최대 8.18 → 2.73 · 획에 붙은 잔상 5.7 → 1.1, 단색 셋 9.9 · 10.2 · 10.3 → 12.89(L 다음 고침이 '판 중앙값이 단색 오의 불가 둘레 옅은 바탕 빛을 지움'으로 되돌린 신호와 같은 숫자 — 그래서 단색 · L-1 보호 run 에 새 판을 넣고 렌더를 합성 차로 고친 진단 어림: **새 오류 0**, 단색 글자 구역 바탕 10.21 → 12.88(덩어리 최소 넓이 미만), L-1 8.01 → 2.53 · 숨김 흔적 E8 사라짐, 눈으로 보면 옛 렌더의 옅은 갈색 상자가 사라져 컨셉에 더 가까움). L-1 `005755` replay '이중' 741 → 825 px.
  - 정답 묶음 **27/27 caught · 1/1 clean · 7/7 protected(errors 0)** — 기존 25 그대로 + 새 2 건('오의 불가' 숨김 흔적 · 게이지 100 % 끝, run `R20261119_091634` 사본) 잡힘.
  - **보호 판정에서 상태 검사 결함은 따로 셈(결정 — 총괄 확인 필요):** 보호 run L-1 `184602` · L-2 `191532` · 단색 `001742`(정답 묶음), `005755` · `010312`(회귀 묶음 추가)는 상태 검사가 그 run **자기 텍스처**에서 같은 종류 결함(게이지 끝 · 숨김 흔적)을 찾는다 — 회귀가 아니라 이번에 고친 결함이 그 run 에도 있던 것. `golden.matches(clean_run)` · `regress compare` 는 `check` 키 결함을 보호 판정에서 빼고 따로 표시(`state-check errors in 3 protected run(s)` · `!! protected run — n state-check error(s)`). 엄격히 세면 정답 묶음 보호는 4/7.
  - 다른 입력에서 새 검사가 찾은 진짜 결함(고치지 않음 — 목록만): 게이지 100 % 끝(`gauge_outside`) — 전투 HUD run 전부(L-1 `184602` · `005755` · `175104` · `214505` · `235644` · `003804` · `134535`(24 px) · L-2 `142524` · `191532` · `010312` · 단색 `120715` · `124503` · `001742` · `010950`). 숨김 흔적(`hidden_trace`) — '오의 불가' 자리: L-1 `175104` · `005755` · 단색 `120715` · `124503` · `001742` · K `235644`, 배너를 숨겨도 남는 판 조각(끝 · 위 문장 · 아래 선): K `235644` · `003804`. 둘 다 F1 · F2 가 새 run 에서 고치는 종류(배너 조각은 아래 한계).
  - **한계(기록만):** 숨는 패널 상자 바로 밖 넘침 조각이 판에 남는 것(091634 배너 양끝 · 아래 문장 판1 · 2 · 3, 4 × 11 px 등)은 컨셉 픽셀과 같아 S1 (라)가 설명함 — 결함으로 안 세고 `hidden_trace.roots[].overhang_px`(091634 배너 49 ~ 61 px, L-2 5 443 px)만. 고치려면 layer 의 판 소유(숨는 위젯 넘침을 그 위젯 쪽으로) — 이번 범위 밖.
- **시험:** pytest **391**(382 + `tests/test_state_check.py` — S1 덩어리 · 구조선 · 컨셉 구조물 · 안 그린 숨은 위젯 건너뜀, S2 번짐 · 번짐 없음 · 엔진 0 % 채움, 끝 빛 근사 자리, F1 자리 메움 · 구조물 지킴 · 안 그린 글자 건너뜀, 경계값 보간, 진단 record · error · 상태 띠, 정답 묶음 기록만 발견 · 보호 분리; `test_gauge` F2 갱신).
- **에디터 run(L-1 입력 `fixtures/m4_combat_hud_concept`) [실측]:**

  | run | 결과 | 원인 · 비고 |
  | :--- | :--- | :--- |
  | `R20261119_141345_CombatHUD` | 실패(iou_region · iou_leaf · appearance, 3 시도) | **M4 C 미커밋 스텁** `UAstralCombatHUDWidget::NativeConstruct` 가 에디터 렌더에서도 돌아(render_widget 이 force_visible · overrides 를 넣은 뒤 `TakeWidget` 에서 NativeConstruct — `WidgetMcpRender.cpp:113-136`, 총괄 확인) 게이지 0 · flag 위젯 접기 → 배너 · 체인 패널 · '오의 불가' · 준비 빛 not_painted. 총괄이 스텁을 '게임 월드 · 소유 플레이어 있을 때만'으로 고치고 DebugGame · Development 빌드 |
  | `R20261119_142159_ProbeCombatHUD` | **통과 — 오류 0(상태 검사 포함) · 근사 3**(시도 5) | 같은 입력을 C++ 부모 없는 검증 화면으로(상태 검사 확인용 — 임시 `screens.yaml ProbeCombatHUD`, 끝나고 걷음). 엔진 렌더 상태 검사: S1 '오의 불가' 국소 최대 1.35 · 배너 0.28(기록 `overhang_px` 61), S2 0 · 5 · 100 % 트랙 밖 0 · 끝 구간 안 바뀜 0 · 0 % 채움 0.59, 근사 `gauge_end_glow`(401 px · 21.2) · 굵기 · 빛. 채움 텍스처 594 → 570 px(spill 0 · spill_measured 24) |
  | `R20261119_143110_CombatHUD` | 실패(구조 게이트 통과, appearance 오류 10 — 5 시도) | 스텁 고침 확인(구조 통과). 오류 = '4.2'(`ChainTimerText`) 획 잔상 E1 8 · `BurstLabelText` 위치 E6 · '오의 불가' 빛 세기 E9, **상태 검사 발견 0**. 이번 analyze 가 '4.2' 에 빛 7 · 상자 331 px 를 줘 체인 패널 오리기 글자 메움(`_cut_entry` → `_plate_item_fill` — 이번에 안 바꿈)이 '투명 위 글자' 둘레 메움으로 가 획을 놓침(probe run · 091634 · 아래 144231 은 판 정합 길, diff 2.87). → 이번 변경 · 스텁 아님 — **이미 있던 약점**(아래) |
  | **`R20261119_144231_CombatHUD`** | **통과 — 오류 0(상태 검사 포함) · 근사 2**(시도 6, 11/11) | 총괄 지시로 한 번만 더(재시도 통과는 '운에 맡긴 통과'라 이것으로 끝). 엔진 렌더 상태 검사: S1 '오의 불가' 국소 최대 1.3 · 배너 0.28(`overhang_px` 61), S2 0 · 5 · 100 % 트랙 밖 0 · 끝 구간 안 바뀜 0 · 0 % 채움 0.59. 근사 = '오의 불가' 빛 세기 차 · `gauge_end_glow`(401 px · 21.2). F1 판6 자리 9 760 px(이번 analyze 는 '오의 불가' 빛 없음 — 자리가 테두리선에 안 닿아 지킨 구조물 0). 채움 570 × 44 · spill 0 · spill_measured 24. **승격 후보 · 사용자 눈 확인 대상**(`compare.png` 맨 아래 상태 띠) |
- **이미 있던 약점 — 체인 패널 글자 메움(이번 범위 밖, 고치지 않음):** analyze 결과가 흔들리면(글자 빛 크기 · 상자 폭) 오리기 텍스처의 글자 메움 `_cut_entry` → `_plate_item_fill` 이 '투명 위 글자'(둘레 컨셉 매끈한 메움) 길로 가서 판 정합이 되는 글자인데도 획을 다 못 덮는다(143110 '4.2' — E1 잔상 8 · E6 · E9). 이번에 안 바꾼 근거: `git diff` 상 `refine.py` 변경은 새 함수(`_harmonic_fill` · `_starts_hidden` · `_hidden_text_fill`)와 `_plate_entry`(판) 안의 숨는 글자 갈래뿐이고 `_cut_entry` · `_plate_item_fill` 본문 diff 0, F1 은 판(`_plate_entry`)의 `_starts_hidden` 글자에만 닿는다('4.2' 는 시작 때 보이는 체인 패널 안 — 해당 없음). 다음 제안: 판 정합이 되는 글자(정합 diff ≤ `NOTEXT_MAX_DIFF`)는 '투명 위 글자' 판정을 쓰지 않거나, 둘레 메움 뒤 획 잔상(`glyph_residue` 와 같은 기준)이 남으면 판 정합 길로 물러나기 + 정답 묶음에 143110 '4.2' 잔상 항목.
- **돌리지 않은 것:** 승격 · HUD PIE 시험(8단계 — 총괄) · 단색 · L-2 · 조작 안내 · 파티 에디터 run(오프라인 비교 · 어림만) · `AstralBreak.` 등 엔진 자동 시험(이 세션 C++ 변경 없음 — 스텁 고침 · 빌드는 총괄) · F2 알파 판의 엔진 렌더(오프라인 합성만 — S2 미달이라 안 씀) · 사람 눈 확인(대기). 임시 `screens.yaml ProbeCombatHUD` 는 걷음(원인이 스텁에서 고쳐졌고 승격 후보는 C++ 부모가 있는 CombatHUD run 이어야 해, 쓰지 않을 검증 화면을 설정에 남기지 않음 — probe run 산출물은 work 에 그대로).

**1b 후속 L 다음 — L-1 글자 완전 지우기 · 게이지 끝 모양 설계 (11-19 작성 · 사용자 확정 '이대로 확정' — 구현은 새 하위 세션, 인계 `uigen-l1-text-erase-handoff.md`(공유 노트 폴더 local_b686cc15…))**

- **계기 [실측 — 사용자 눈 확인, 새 run `R20261119_144231_CombatHUD`]:** ① 체인 패널 텍스처에 '4.2' 빛 바깥 테두리가 주황 윤곽으로, '2/4' · '체인' 이 옅게 남음 ② 게이지 100 % 오른쪽 끝이 곧은 세로 테두리로 끝나 끝 장식 안쪽 호를 덮고 위아래 띠도 네모로 끝남(왼쪽은 '<' 로 호에 맞게 들어감). 둘 다 상태 렌더 검증과 같은 종류 — 컨셉 한 상태('4.2' 를 띄운 70 % 화면)만 보고 정한 결과. 이 run 은 승격하지 않는다(게임 HUD = 12:01 승격본 그대로).
- **L-1 을 고쳐야 하는 이유:** L-2(글자 없는 컨셉부터)는 텍스처를 글자를 그린 적 없는 원본 아트에서 오려 ①이 생기지 않는다(L-2 run `R20261119_010312` 체인 패널 텍스처 깨끗함 — 확인). 그러나 원본 아트는 codex 가 새로 그린 다른 그림이라 모양(패널 색 · 모서리 장식)이 바뀐다. 사용자는 지금 컨셉에서 크게 바뀌지 않기를 원함 → 글자 든 컨셉(L-1) 길이 완성돼야 파이프라인이 끝난다. 글자 잔상은 J · K · L 내내 되풀이됐고 L-2 가 그 대안으로 나왔다 — 이번엔 외부 도구(인페인팅)도 후보.
- **L-1 · L-2 관계 [소스 확인]:** 파이프라인은 하나다(같은 단계 preflight → normalize → analyze → layer → codegen → generate → refine → build → verify). 다른 곳 = normalize 가 무엇을 아트 정답으로 삼는지(글자 든 컨셉 ↔ 원본 아트)와 그것을 읽는 스위치 하나 `diagnose.art_mode`(refine `art_files` · layer · 진단 공용) — 즉 '글자 자리를 지우고 메울 일이 있느냐'. 게이지 채움(`gen/concept_fill`)과 상태 검사는 공용(두 run 모두 `concept_fill · texture concept`), 그래서 ②는 한 곳만 고치면 L-1 · L-2 · 외부 컨셉에 같이 간다(F2 · S1 · S2 도 이미 그렇다).
- **원인 [실측]:**
  - ① 지금 L-1 글자 메움(`refine._plate_item_fill` — 판 · 오리기 텍스처 공용, 오리기는 `_cut_entry` glyph_fill)은 **좁은 메움**: 바꿀 자리 = 컨셉 ↔ 글자 없는 판이 다른 글자색 획 + 3 px + analyze 빛 크기 안에서 판보다 L 10 넘게 밝은 픽셀(K (나)). 컨셉 '4.2' 빛은 획에서 1 px +12.4 · 3 px +7.0 · 5 px +3.7 · 7 px +1.1 L*(컨셉 − 글자 없는 판 중앙값)로 번지는데 메움 경계에서 끊겨, 텍스처가 판보다 L 6 넘게 밝은 픽셀 2 466 개가 메움 경계 고리로 남는다(텍스처 ↔ 판 ΔE00 p95 9.2). 컨셉 상태 렌더에선 엔진 글자 · 빛이 그 자리를 덮어 진단이 통과하지만, 값이 바뀌면(남은 시간은 매 프레임) 옛 '4.2' 윤곽이 보인다. 좁게 한 이유는 이력 그대로 — 넓게 지우면 codex 판의 색조 · 장식 어긋남이 조각으로 드러나고(J '공격' 구름 얼룩 · 배지 양옆 선) 둘레 보간은 결을 뭉갰다. 즉 **'지울 범위'와 '지운 뒤 메우기'가 맞물린 문제**다.
  - ② 채움 텍스처의 오른쪽 고정 여백 = 컨셉 70 % 의 진행 끝(곧은 테두리). 컨셉엔 100 % 오른쪽 끝 모양이 없다(왼쪽 '<' 는 컨셉에 있음). S2 는 트랙 상자 밖만 봐 상자 안에서 호를 덮는 것을 못 봤다.
- **A 검증 먼저(기록만 → 묶음 거짓 양성 0 → 오류, 이번 단위와 같은 절차):**
  - **S4 글자 밑 흔적(UI ↔ 글자 분리):** L-1 의 **모든 TextBlock** 을 빈 값으로 그린 상태(엔진 overrides `text: ""` · 회색 · 흰 바탕 텍스처 합성 = 글자 없는 상태)에서 그 자리(상자 + 빛 + 4 px)를 S1 규칙으로 — 단 자리 안에서는 (라) '컨셉 그대로'를 안 씀(빈 값에선 컨셉 글자가 정답이 아님). 값이 바뀌는 글자(바인딩 number · text — 체인 남은 시간 · 참가 수 · 버스트 인원)는 같은 형식의 다른 값(예 '8.8' · '1/4' · '7')으로도 그려 그 값 획 밖에 옛 획 잔상(`glyph_residue` 기준)이 있는지. 더 긴 가짜 번역문 검사는 하지 않음(배치 · 현지화 주제 — 범위 밖).
  - **S2 보강 — 끝 모양:** 1.0 에서 트랙 끝 구간(끝에서 8 %) 안의 '0 % 렌더에서 밝은 프레임 구조물'(끝 장식 호 — 채움색 아님)이 덮이면 `gauge_end_cover`, 그 구간의 빈 트랙 자리(트랙 hole)가 채움색이 아니면 `gauge_end_gap`.
  - 정답 묶음 + 3: 144231 '4.2' 윤곽(S4) · 144231 100 % 오른쪽 끝(S2 보강) · 143110 '4.2' 획 잔상(이미 E1 — 보호용 기록).
- **B 고침(조건을 좁게):**
  - **G1 지울 범위:** 대상 = L-1(아트 모드 아님)의 **모든 글자**(UI 텍스처 ↔ 글자 분리 — 글자는 이미 전부 엔진 TextBlock, 그 밑 텍스처에 컨셉 글자 흔적이 없어야 값 · 문자열이 바뀌어도 깨끗함. 이미 F1 인 시작 때 숨는 글자는 F1 그대로). 자리 = 핵심 획에 이어지고 컨셉이 바탕 추정(정합된 글자 없는 판, 없으면 둘레)과 ΔE00 3 넘게 다른 픽셀, 빛 끝(`glow_measure` 꼬리 — 상한 16 → 24 px)까지. 지킬 것(구조선 · 판에도 있는 구조물 · 가로지르는 불투명 덩어리 · 다른 글자 상자)은 지금 규칙 그대로. **한 묶음 안에서 순서만:** 값이 바뀌는 글자 먼저 → 회귀 비교(새 결함 0) → 고정 글자('체인' · '체인 버스트' 등) → 회귀 비교(새 결함 0). 언어별 글꼴 · 긴 번역문 배치 · 언어별 텍스처는 나중 주제.
  - **G2 메우기 — 오프라인 겨루기로 고름:**
    - (가) **외부 인페인팅 LaMa**(Samsung 'Resolution-robust Large Mask Inpainting with Fourier Convolutions', WACV 2022) ONNX 판 `lama_fp32.onnx`(Hugging Face `Carve/LaMa-ONNX` — big-lama 를 옮긴 것, 원본과 같은 결과라고 적힘 · Apache-2.0 · 208 MB · 입력 512 × 512 고정 · opset 17; 커뮤니티 int8 판 37 MB 는 자기 보고뿐). 추론은 이미 깔린 `onnxruntime` 1.32.0 CPU(OCR 용 — 새 패키지 없음, GPU 실행기 없음). 글자 자리 둘레 512 × 512 창(자리 ≤ 약 360 × 150 이라 들어감 · 넘으면 나눔)에 마스크 = G1 자리 + 2 px, 결과는 마스크 안에만 2 px 섞어 붙임 · 알파는 판 · 둘레(경계값 보간)에서. CPU 는 같은 입력 → 같은 출력, 창 · 마스크 해시로 캐시(`_convert` 처럼). 결 · 장식을 이어 그리는 데 강하다는 것이 채택 이유 — 실제로 우리 패널에서 나은지는 겨루기로.
    - (나) **정합된 codex 글자 없는 판**을 G1 자리 전체에 + 둘레 색조 평면 보정(`PLATE_TONE_MAX`) + 2 px 섞기(지금 판 정합 길을 넓힌 것).
    - (다) 투명 바탕 글자는 F1 경계값 보간 그대로.
    - **고르는 규칙:** 회귀 묶음 · 정답 묶음의 값이 바뀌는 글자 자리마다 S4(빈 값 · 다른 값 잔상), 컨셉 상태 글자 구역 바탕 E1 지표, 3 배 절취선, 확대 그림 — (가)가 모든 입력에서 (나)보다 낫고 새 결함 0 이면 (가), 아니면 (나). 모델 파일이 없거나 추론이 실패하면 (나)로 물러나고 기록(run 을 막지 않음, 실행 중 내려받기 없음 — 경로는 `pipeline.yaml`).
  - **G3 게이지 오른쪽 끝(`gen/concept_fill` 한 곳 — L-1 · L-2 공용):** (가) 오른쪽 고정 여백의 알파 = 컨셉 빈 트랙 오른쪽 끝 모양(끝 장식 안쪽 호까지의 트랙 hole 윤곽 — 진행 끝 테두리는 그 윤곽을 따라) → 100 % 에서 왼쪽처럼 호에 맞게 들어감, 대신 중간 진행률의 끝이 곧은 선 대신 둥근 모양(컨셉 70 % 와 다름 → 진단 근사 `gauge_end_shape` — `gauge_end_glow` 와 같은 방식) (나) 왼쪽 '<' 를 뒤집은 '>' — 같은 근사 (다) 곧은 끝 유지 + 트랙을 호 시작에서 끝냄 — 100 % 에 어두운 틈이 남아 '꽉 찬' 느낌이 안 남(비추천). 추천 (가).
- **손상 방지(가장 경계하는 것 — 이번 단위와 같은 틀):** 바꾸는 범위 = L-1 의 글자 자리 · 채움 텍스처 오른쪽 여백뿐, 그 밖 텍스처는 바이트가 같아야 함(회귀 묶음 비교에서 바뀐 텍스처 목록 = 대상 글자 상자 · 채움뿐인지 입력마다). 기준선 = `state_fix_1119`, 고친 뒤 회귀(`+ new`) 결함 0 · 정답 묶음 27/27 + 새 항목 · 보호 run 오류 0(상태 검사 결함 따로) · pytest. 에디터 run 은 L-1 1 회 + L-2 1 회(게이지 끝 공용 고침 확인) — 둘 다 compare 상태 띠로 사람 눈.
- **순서:** ① S4 · S2 보강 기록만 + 정답 묶음 → ② 묶음 재진단(거짓 양성 정리 · 진짜 결함 목록) → ③ 오프라인 겨루기 (가) · (나)(LaMa 는 내려받기 승인 뒤) → ④ G1 · G2 · G3 + 검사 오류 승격 → ⑤ 회귀 비교 · 정답 묶음 · pytest → ⑥ 에디터 run L-1 · L-2 → ⑦ 사람 눈 → 승격(총괄).
- **결정(사용자, 11-19):** ① LaMa = **fp32 `lama_fp32.onnx` 208 MB**(int8 아님) · 저장 `Tools/uigen/work/_models/`(이미 git 무시인 work 아래 — `Tools/uigen/models/` 는 무시 목록에 없고 `.gitignore` 는 쓰기 범위 밖) — 내려받기는 구현 세션이 시작할 때 한 번(그 세션에서 파일명 · 출처 · 크기로 확인받고), 학습 데이터(Places 계열) 라이선스는 코드(Apache-2.0)와 따로라 그때 확인 ② G1 대상 = **L-1 의 모든 글자** — 뜻은 UI 텍스처 ↔ 글자 **분리까지만**(언어별 글꼴 · 긴 번역문 배치 · 언어별 텍스처는 나중), 값이 바뀌는 글자 → 고정 글자 순서로 회귀 비교 ③ 게이지 끝 = **(가) 호 모양**(컨셉 빈 트랙 끝 모양을 재서 따라감 — 대칭을 가정하지 않아 비대칭 · 둥근 · 뾰족한 끝 장식 bar 에도 범용, 오른쪽→왼쪽 채움은 지금 측정이 뒤집어 처리) ④ 중간 진행률 끝 모양 차이 = **근사**(`gauge_end_shape`). 받지 않으면 '가득 찰 때만 보이는 끝 조각 위젯'(바인딩 계약 · C++ — 총괄 몫)이 필요했음.
- **조사 출처:** Hugging Face `Carve/LaMa-ONNX`(lama_fp32.onnx 추천 · 512 × 512 고정 · Apache-2.0) · `opencv/inpainting_lama`(같은 파일 · Apache) · `othytenk/lama-int4-int8`(37 MB) · 장면 글자 지우기 연구 모델(MTRNet++ · PSSTRNet · FETNet)은 ONNX 가중치 · 라이선스가 확인되지 않아 후보에서 뺌.

**1b 후속 L 다음 — L-1 글자 완전 지우기 · 게이지 끝 모양 결과 (11-19, 미커밋 — 구현 하위 세션. 쓰기 = Tools/uigen · 이 문서, C++ · WidgetMcp 변경 없음 · 승격은 총괄 몫)**

- **A 검사(기록만 → 묶음 거짓 양성 0 → 오류) [실측]:**
  - **S4 `text_trace`**(`gen/state_check.text_trace`): 설계의 '상자 + 빛 + 4 px 자리에 S1 규칙' 그대로는 못 썼다 — ① 빛 여백으로 넓은 상자('4.2' 352 × 143)가 패널 전체라 둘레 고리가 패널 밖이 됨 → 자리 = 컨셉 글자 획(후보 · 핵심) + 빛 꼬리(`glow_measure`, ≤ 24) + 3 px ∩ 상자 + 빛 + 4 px, 겹친 글자 자리는 한 덩어리(고리 공유) ② 둘레 보간만으로는 글자가 띠 · 테두리 위에 있는 외부 입력에서 거짓 양성(조작 안내 '돌진 공격' 국소 30 · 파티 숫자 35) → 설명에 (마) 글자 없는 판 ±2 px 이동 최소를 더함 ③ (라) '컨셉 그대로'는 컨셉이 글자 · 빛을 그린 자리(핵심 획 + 2 px ∪ 빛 꼬리 안 '컨셉이 판 ±2 px 이동 최대보다 L* 3 넘게 밝은' 픽셀) 밖에서만 ④ S1 의 7 × 7 · 10 은 얇은 빛 윤곽을 못 봄(144231 '4.2' 7 × 7 최대 5.8) → 자리 안만의 **3 × 3 창 평균 > 5**(`appearance.text_trace_de`) · 덩어리 ≥ 24. 보정 숫자: 144231 '4.2' 3 × 3 최대 6.5 · 깨끗한 L-2 010312 글자 자리 ≤ 0.24, 보호 run(판 설명 넣은 뒤) 조작 안내 ≤ 4.8. 값 글자는 같은 형식 다른 값(`value_overrides` — 숫자마다 + 5 mod 10: '4.2' → '9.7' · '2/4' → '7/9' · '3' → '8')의 엔진 렌더에서 새 글자 + 빛 자리를 뺀 옛 자리도(`text_value_trace`, 엔진만). 엔진 렌더 = verify `render_state` 이름별 폴더 `state_notext`(시작 때 숨는 위젯 끔 + 모든 글자 `text ""`) · `state_values`. compare.png 상태 띠에 '모든 글자 빈 값(검정 엔진 | 회색 | 흰 합성)' · '값 글자 다른 값' 줄.
  - **S2 보강**(`gauge_states(ref_png=…)`): concept_fill 트랙 끝 구간(끝에서 max(8, 8 %) 열) 안 `track_hole` 밖(끝 장식 호 · 프레임)이 100 % 에서 0 % 렌더와 국소 차 > 10(덩어리 ≥ 12) → `gauge_end_cover`, 그 구간 hole 이 0 % 와 30 % 넘게 같음 → `gauge_end_gap`. 144231: 덮음 2 덩어리(위 · 아래 모서리, 국소 최대 43 · 48).
  - **묶음 재진단(기록만 — 정답 30 run · 회귀 14 run):** 발견 = 게이지 끝 덮음(전투 HUD 전부 — L-1 · L-2 · 단색), '4.2' 빛 윤곽(L-1 · 단색 run 전부), 단색 '2/4' 흔적, 파티 '0 %' 어두운 윤곽 · 옛 파티 run 이름 자리 얼룩, 조작 안내 `AttackLabelText` 흰 바탕에서만 옅은 'o' 고리 — 확대 그림으로 모두 같은 종류 실제 흔적. **거짓 양성 1**: 파티 HP 숫자 아래 막대 윗선 23 × 2 px(구조선) → 짧은 변 ≤ 2 px 덩어리는 `line_like` 기록만 → 0 → `appearance.state_record_only: []`(오류 E8).
  - 정답 묶음 + 3(144231 '4.2' 빛 윤곽 S4 · 144231 100 % 오른쪽 끝 덮음 S2 보강 · 143110 '4.2' 획 잔상 E1): 기록만 상태에서 **30/30 caught · 1/1 clean · 7/7 protected**, 오류 승격 뒤에도 30/30 · 1/1 · 7/7(보호 run 상태 검사 결함은 그 run 자기 옛 텍스처 — 6 run 따로 표시).
- **B 고침:**
  - **G3 게이지 끝(`concept_fill.end_shape` · `_apply_end_shape`, L-1 · L-2 공용):** 줄마다 컨셉 빈 트랙 hole 이 끝 24 px 구간 시작부터 **처음 끊기는 열**까지(마지막 hole 열로 재면 끝 장식 안쪽 선 너머 hole 까지 닿아 50 % 끝에 ')' 모양 빈 트랙 선이 비쳤다 — 오프라인), offsets = right − 그 열, 오른쪽 고정 여백 = END_IN + 1 + 호 깊이(144231 깊이 13 · 여백 19 px), 여백 알파 = 줄 끝까지 · 진행 끝 테두리(컨셉 그 줄 6 열)가 줄 끝을 따라감. 호 깊이 0(곧은 끝 — 시험 게이지)이면 예전 그대로(같은 바이트). 오프라인(옛 파라미터 + 끝 모양 다시 그림): 덮음 국소 최대 48.2 → 0 · S2 발견 2 → 0, 50 % 끝은 둥근 끝. 중간 진행률 끝 차이는 근사 `gauge_end_shape`(`state_check.end_shape_zones` — 끝 빛 자리와 이어진 합에서 넓이 비 60 % 이상).
  - **G1 지울 범위(`refine._erase_zone`, `extract.text_erase` — 최종 `values_glow`, 아래 '범위'):** 좁은 메움 자리 + 핵심 획에 이어지고 컨셉이 **색조 맞춘 판 또는 빛 꼬리 밖 둘레 추정** 어느 쪽과도 ΔE00 3 넘게 다른 픽셀, 빛 꼬리(판 · 둘레 기준 `glow_measure` 중 긴 쪽, ≤ 24) + 3 px까지. 판과만 견주면 codex 판이 덜 지운 갈색 빛 잔재 자리가 빠졌다. 지킴 = 다른 글자 **획 + 2 px**(상자째 빼면 겹친 상자 '4.2' ↔ '2/4' 안의 '4.2' 빛이 남음) · 길고 가는 선 · 판에도 있고 둘레 추정과 ΔE00 10 넘는 구조물(`_plate_same` 만으로 지키면 평평한 패널 바탕 · 빛 잔재까지 지켜 넓힘 0 px 이었다). 시작 때 숨는 글자는 F1 그대로. 지우는 글자는 획 둘레(빛 반경 밖)가 불투명하면 상자 둘레 알파로 '투명 위 글자'라 하지 않음 → **143110 약점 해결**(오프라인 '4.2' 잔상 250 → 0 px · S4 27 → 2.9).
  - **G2 메우기 — 오프라인 겨루기:** (나) 판으로 넓게 메우기는 144231 '4.2' 자리에 판의 갈색 빛 잔재가 그대로 드러남(S4 6.5 → 9.0 — 그림). (가) LaMa(`gen/inpaint`): 받은 모델 `lama_fp32.onnx` 208 044 816 바이트 · SHA-256 인계 값과 같음(사용자 승인 — curl 거절 뒤 Python 으로 받기), 입력 `image`(0 ~ 1) · `mask`(1 = 메울 자리), 출력 0 ~ 255, CPU 약 12 초/회, 같은 입력 → 같은 출력. 다듬은 순서와 이유(전부 144231 오프라인 S4 · 그림): 마스크 안 글자를 다시 그림 → 메울 자리를 입력에서 지움(이 ONNX 판은 안에서 지우는 것으로 보임 — 결과 같음) · 판 자국 픽셀을 매끈한 평균으로 덮던 길에 LaMa 색 우선(글자 모양 얼룩 S4 58 → 34) · 넓힘 0 원인 고침 + 마스크 + 2 px · 다른 글자 획 + 12 px 원천 가림('체인' · '2/4' 깨끗, '4.2' 7.6) · 원천 가림을 획 + 빛 꼬리 × 2 + 6 px 로(마스크 밖 옅은 빛 기울기를 '가운데 광원'으로 이어 그린 아지랑이 → 2.8) · 그만큼을 붙임(경계 윤곽 → 3.2) · 알파는 둘레 경계값 보간. 매끈한 이음(테두리 차 경계값 보간)은 세 판 모두 나빠져 끔(14.8 · 9.6 · 11.3).
  - **고르는 규칙(설계 '조건을 좁게'):** 단색 입력에서는 (가)가 패널 결을 못 이어 어두운 실루엣 · 지어낸 하이라이트(오프라인 001742 '4.2' 좁은 10.6 → LaMa 28.7), (나)도 8.8 — 설계 규칙('(가)가 모든 입력에서 (나)보다 낫고 새 결함 0 이면 (가)')을 입력 단위로 적용: **텍스처마다 지운 판 · 좁은 판을 둘 다 만들어(모든 글자를 메운 뒤 — 글자마다 따로 만들면 겹친 상자의 안 메운 이웃 획이 점수 86 을 냄) 글자 흔적 지표(`_trace_score` — S4 와 같은 설명 · 검정 · 회색 · 흰 바탕 · 두 판이 다른 픽셀만)로 글자마다 고름(`_erase_choice`)**: 모든 글자가 지운 판 ≤ max(좁은 판, 3) + 0.5 면 지운 판, 일부만이면 그 글자만 지운 판을 다시 만들어 같은 규칙, 아니면 좁은 판(예전 텍스처 그대로).
  - **범위 = `values_glow`(설계 'L-1 모든 글자'에서 좁힘 — 사용자 확인 필요):** 'all' 로 돌린 회귀 묶음(`i_final` → `j_final` → `k_final`, 고르기 규칙을 셋 다 다듬음)에서도 빛 없는 고정 글자 몇 개가 S4 기준 예전보다 나빠졌다(controls_alpha `DashLabelText` 좁은 3.9 → 7.6 · 옛 조작 안내 원본 run `EKeyText` 4.8 → 18.6 — 텍스처만 보는 고르기 점수는 12.4 대 12.1 · 21.9 대 26.4 로 못 가림, 엔진 · 캔버스 합성에선 다른 텍스처와 겹친 모습이 다름). 좁은 메움이 흔적을 남기는 원인은 **빛 꼬리가 잘리는 빛 글자**(실측 '4.2' — 컨셉 − 판 L* 3 px +7.0 · 5 px +3.7)와 **값이 바뀌는 글자**이고, 빛 없는 고정 글자는 좁은 메움(획 + 3 px)이 이미 덮는다 → `extract.text_erase: values_glow`(값 글자 + 빛 글자). 대가: L-1 '체인'(고정 · 빛 없음)은 좁은 판 그대로 — S4 1.9(문턱 5 아래), 엔진 빈 값 렌더 2 배 확대에서 옅은 얼룩이 보임(사람 눈 판정 대상). 'all' 은 설정 한 줄로 돌릴 수 있다.

- **회귀 방지 [실측]:**
  - 회귀 묶음 `regress_set compare state_fix_1119 l_final_1119`(최종 설정): **회귀(`+ new`) 결함 0 · 보호 run 깨짐 0**(14 입력). `+ state` 는 새 검사(S4 · S2 보강 — 오류로 올림)가 옛 run **자기 텍스처**에서 찾은 같은 종류 결함(회귀 아님). **바뀐 텍스처 = 대상 글자 상자뿐**: L-1(`184602` · `005755`) 체인 패널 `ChainTimerText` · `ChainCountText` · `ChainTitleText` 상자(제목 상자는 '4.2' 붙인 자리가 걸쳐서 — 최대 ΔE00 7.5 · 6.9), 단색 `124503` · `001742` `ChainCountText` · `ChainTimerText` 상자('2/4' 만 지운 판을 받음 — '4.2' 는 지운 판이 나빠 좁은 판). L-2 · 조작 안내 넷 · 파티 둘 · 단색 `120715` 텍스처 변화 0. 게이지 채움(G3)은 replay 가 procedural 을 다시 안 그려 묶음엔 안 나타남 — 오프라인 · 에디터 run 으로 확인.
  - replay S4(글자 흔적, 합성) 고치기 전 → 뒤: L-1 '4.2' 6.5(텍스처 윤곽) → 2.9 · 3.1, '2/4' → 1.1 ~ 1.9, '체인' 1.9(좁은 판 그대로), 단색 '2/4' 2.8 → 1.7 ~ 2.0, 단색 '4.2' 10.2(그대로 — 다른 입력 진짜 결함), 조작 안내 · 파티 = 예전 값 그대로. 143110 '4.2'(약점) 오프라인 27 → 2.9.
  - 겨루기 숫자(같은 묶음 · 범위 'all'): (나) 판 — 새 결함 0 이지만 단색 '4.2' 8.8 · 144231 '4.2' 9.0(오프라인 단독) / (가) LaMa 값 글자만(`g_lama_values`) — L-1 '4.2' 2.9 ~ 3.1 이지만 단색 '4.2' 13 ~ 39 로 악화 → 텍스처별 고르기 넣음.
  - 정답 묶음 **30/30 caught · 1/1 clean · 7/7 protected(errors 0)** — 기존 27 그대로 + 새 3 건(S4 · S2 보강 · 143110 E1) 잡힘, 상태 검사 결함은 보호 run 6 곳 자기 옛 텍스처(따로 표시). pytest **382 → 391(앞 단위) → 399**(+ `tests/test_text_erase.py` 8 — S4 윤곽 잡음 · 깨끗함 · 선 모양 기록만 · 값 바꾸기, G3 호 따라감 · 곧은 끝 그대로, G1 빛 꼬리까지 · 이웃 획 지킴, 고르기(나쁘면 좁은 판), 인페인팅 창 · 모델 없음 물러남).
- **에디터 run [실측]:**

  | run | 결과 | 비고 |
  | :--- | :--- | :--- |
  | `R20261119_180316_CombatHUD`(L-1, 범위 all · 글자마다 고르기 전 판) | 실패 — 구조 통과, 진단 오류 1 = '2/4' 굵기 E9(획 밀도 비 0.75) | 새 검사는 엔진 렌더로 모두 통과(S4 '4.2' 3.0 · 다른 값 3.1 · '체인' 1.2 · '2/4' 1.2, S2 끝 덮음 0.0). 원인 = 이번 analyze 가 '2/4' 를 regular 로(144231 은 bold) → 마지막 크기 판 `text_fit_size_final` 이 semibold 로 고쳤지만 같은 판의 '오의 불가' 크기 변경이 빛 세기 10.9 → 13.0(E9)을 만들어 **판 전체가 버려짐**, '원인이 줄어든 글자만 다시'(`_partial`)가 이 경우 돌지 않음(`better_texts` 기록 없음) — 텍스처 지우기와 무관한 기존 글자 맞춤 흐름(후속). 같은 설정으로 다시 돌리지 않음 |
  | **`R20261119_182159_CombatHUD`(L-2)** | **통과 — 오류 0 · 근사 4**(굵기 3 · `gauge_end_shape`) | 엔진 렌더 S2 끝 덮음 0.0 · 끝 hole 안 바뀜 0.13, S4 ≤ 0.6, 채움 끝 모양 깊이 23 · 여백 29 px — 100 % 끝이 끝 장식 '>' 호에 맞게 들어감 |
  | **`R20261119_190059_CombatHUD`(L-1, 최종 설정 `values_glow`)** | **통과 — 오류 0 · 근사 3**(시도 8 — '2/4' 굵기 · '오의 불가' 빛 · `gauge_end_glow`) | 엔진 렌더: S4 '4.2' 3.1(다른 값 '9.7' 3.1) · '체인' 2.2 · '2/4' 1.5, S1 '오의 불가' 1.3 · 배너 3.3, S2 끝 덮음 0.0 · 끝 모양 깊이 13 · 여백 19 px. 체인 패널 고르기: '4.2' 지운 3.27 ↔ 좁은 7.08, '2/4' 2.53 ↔ 1.63(받음). 엔진 빈 값 렌더 2 배 확대: '4' 붙인 자리 경계의 아주 옅은 윤곽 · '체인' 자리 옅은 얼룩이 보임(지표 문턱 아래) — **사람 눈 판정 대상**. `compare.png` 상태 띠에 '모든 글자 빈 값' · '값 글자 다른 값' 줄 |
- **새 검사가 다른 입력에서 찾은 진짜 결함(고치지 않음 — 목록만):** 게이지 100 % 끝이 끝 장식 호를 덮음(`gauge_end_cover`) — 옛 전투 HUD run 전부(L-1 `184602` · `005755` · `144231`, L-2 `191532` · `010312`, 단색 `120715` · `124503` · `001742`). '4.2' 빛 윤곽(`text_trace`) — L-1 `184602` · `005755` · `144231`, 단색 셋(단색 '4.2' 는 고친 뒤에도 10.2 — 지운 판이 더 나빠 좁은 판 유지). 단색 '2/4' 흔적(`120715` · `124503`). 파티 '0 %' 어두운 윤곽(`130201` · `003127`, replay 50) · 옛 파티 run 이름 자리 얼룩(`130201`) · 방패 숫자(`003127` replay 18.6). 조작 안내 `AttackLabelText` 흰 바탕에서만 옅은 'o' 고리(`180405` · `125054` · `004119`).
- **돌리지 않은 것:** 승격 · HUD PIE 시험(총괄 몫), 단색 · 조작 안내 · 파티 에디터 run(오프라인 replay · 재진단만), 엔진 자동 시험(C++ 변경 없음), 범위 'all' 의 에디터 run 재실행(실패 run 은 원인만 가름), 글자 맞춤 `_partial` 빈틈 고침(범위 밖 — 후속), 사람 눈 확인(대기).
- **결정 — 사용자 확인 필요:** ① 범위 `values_glow`(설계 'L-1 모든 글자'에서 좁힘 — 위 근거) ② 보호 판정에서 상태 검사 결함 따로 셈(앞 단위 결정 그대로) ③ L-1 '체인' 옅은 얼룩 · '4' 붙인 자리 옅은 윤곽을 받아들일지(사람 눈).

**1b 후속 L 다음 — 글자 지우기 마감 설계 (11-19 작성 · 구현 전, 사용자 '설계부터 하고 새 세션에서' — 위 결과 절의 바탕)**

- **계기 [실측 — 사용자 눈, 위 결과 run]:** ① 배너 텍스처(`T_burst_banner_frame`)에 '체인 버스트' · '3' 글자 모양 얼룩 ② 체인 패널 '4' 자리에 옅은 윤곽(바깥 · 안쪽 선) ③ 파티 HUD '0 %' 어두운 '0' 테두리 + 안쪽 어두운 타원(구멍 느낌) ④ 게이지 중간 진행률 끝이 뾰족하고 계단 모양.
- **원인 [실측 · 소스]:**
  - ① 배너는 `BurstBanner`(Border · 시작 때 접힘 · flag)가 텍스처를 직접 가진 위젯이라 **텍스처째 숨는다**. 결과 단위는 시작 때 숨는 글자를 지우기(G1)와 S4 에서 뺐다(S1 · F1 몫이라 봄). 그런데 S1 은 숨은 상태만 보고(배너는 통째로 안 보임), F1 은 '글자만 숨고 판은 보이는' 경우('오의 불가' — 판6 위)다 → 배너가 뜬 상태의 글자 밑은 아무도 안 봤다. 배너 글자는 좁은 판 메움(정합 차 3.5 · 3.3) 그대로.
  - ② '4' 윤곽은 **남은 컨셉 픽셀이 아니라 메움 결과에서 생김**(오프라인 R20261119_190059 — 컨셉 그대로 남은 글자 · 빛 픽셀 4 531 px 는 '체인' 자리 · 테두리에 있고 '4' 윤곽과 안 겹침, 가는 선 지킴과 겹침 914 px 도 윤곽 모양 아님 — 결과 절의 '가는 선 지킴' 추정은 틀림). 후보: 바깥 윤곽 = 붙인 자리 경계의 흐린 섞임 띠(`NOTEXT_GROW` 블러)에 판 색(인페인팅 아님)이 섞임, 안쪽 윤곽 = 미확인(인페인팅 원본 출력 · 알파 판정 `low` · 두 번째 판 순서 중 하나 — 구현 세션이 원본 출력 단계별로 가를 것). 검사는 3 × 3 창 평균 > 5 라 가는 선(국소 3.1)을 못 봄.
  - ③ 파티 글자 7 개는 모두 **지우기가 연결되지 않은 메움 길**로 간다(결과 단위 G1 · G2 는 '판 정합' 길에만 붙음 — 회귀 `l_final_1119` 기록): 'Lv' · '100' · 이름 · '0 %' = 판 중앙값 메움(판이 글자 자리를 투명하게 그림), HP 숫자 = 투명 위 글자 둘레 메움, 방패 숫자 = 좁은 둘레 메움. '0 %' 자국은 판을 글자 크기로 뭉갠 중앙값이 '0' 테두리를 남기고 안쪽을 어둡게 비운 것. 조작 안내도 같은 길들을 쓴다. 파티 마지막 run `R20261119_003127` 은 새 S4 오류 3('0 %' 34.7 ~ 50) — 지금 규칙이면 실패.
  - ④ 채움 텍스처는 오른쪽 끝 모양이 하나뿐이라(scale + box 여백 고정) 100 % 에 맞춘 호 · '>' 가 중간 진행률 끝에도 나옴(설계가 받은 근사) + 줄마다 알파 0/1 로 잘라 계단(구현 결함).
- **A 검사 먼저(기록만 → 묶음 거짓 양성 0 → 오류 — 이 문서의 같은 절차):**
  - **S4 숨는 묶음:** 시작 때 숨는 위젯 중 **자기 · 자손이 텍스처를 그리는 것**(배너 — 텍스처째 숨음)은 그 위젯을 켠 상태 + 안 글자 빈 값(엔진 overrides visible + `text ""`, 합성 = 그 하위만 켬)으로 S4 를 돈다. 글자만 숨는 것('오의 불가')은 S1 · F1 그대로.
  - **S4 가는 선(`text_contour`):** 3 × 3 평균으로 못 보는 가는 윤곽 — 자리 안 설명 안 되는 차(같은 설명) > 2.5 인 픽셀이 8-연결로 길게(골격 길이 ≥ 40 px) 이어지고 글자 획 윤곽 근처(획에서 빛 꼬리 + 6 px 안)를 따라가면. 정답 묶음 + 3(190059 '4' 윤곽 · 190059 배너 '체인 버스트' · '3' · 003127 '0 %' 구멍) — 문턱은 묶음으로 보정(깨끗한 L-2 · 보호 run 거짓 양성 0).
  - **고르기 = 게이트와 같은 함수:** 결과 단위의 텍스처 단독 점수(`_trace_score`)는 S4 와 달라(캔버스 합성 · 다른 텍스처 겹침 · 바탕 셋) 조작 안내 악화를 못 가렸다 → refine 끝에 한 번, 모든 텍스처 후보로 캔버스 합성(`replay_refine.boxes_from_spec` 상자 — refine 시점엔 엔진 geometry 없음)을 만들어 `diagnose.text_glyph_masks` + `state_check.text_trace`(S4 · 가는 선 그대로)로 글자마다 고른다.
- **B 고침:**
  - **H1 숨는 묶음 지우기:** 텍스처째 숨는 위젯(배너) 안 글자도 G1 · G2 대상(값 · 빛 글자 범위 규칙 그대로).
  - **H2 붙인 자리 경계:** 인페인팅을 쓴 자리는 섞임 띠에도 인페인팅 원본 출력(마스크를 띠만큼 넓혀 돌림)을 쓰고 판 색은 안 섞는다 — 결과 단위에서 '붙일 자리 + 4 px · 밖은 컨셉' 판은 오프라인 3.2 → 11.3 으로 나빠졌으니, 띠 폭 · 섞는 쪽을 단계별로 재고 원본 출력과 대조해 안쪽 윤곽 원인부터 가른다(고치기 전 확정).
  - **H3 다른 메움 길(파티 · 조작 안내):** 판 중앙값 · 투명 위 글자 둘레 · 좁은 둘레 길에도 지우기 후보를 만든다 — 바탕이 투명 · 반투명 · 막대 위라 후보 셋을 겨룸: (가) 인페인팅 색 + 둘레 경계값 보간 알파 (나) F1 경계값 보간(미리 곱한 색 · 알파 함께) (다) 지금 길. 고르기는 위 '게이트와 같은 함수'.
  - **H4 게이지 끝:** 가장자리 부드럽게(줄 끝 알파를 분수 px 로 — 계단 없앰, 모든 안에서 함). 모양은 **사용자 결정**: (가) 지금처럼 끝 장식 모양(호 · '>') — 중간 진행률도 그 모양(근사 그대로) (나) **중간은 곧은 끝, 가득 차면 호에 맞게** — 곧은 끝 채움 위에 끝 장식 안쪽(빈 트랙 hole 밖 · 트랙 상자 안 컨셉 픽셀)을 오린 이미지를 한 장 더 얹어 100 % 에서 넘는 부분을 덮음(layer · spec 에 위젯 하나 — C++ 없음, z 순서 · 런타임에 안 접히는 위젯이어야 함 — 넘침 장식 Image 와 같은 틀) (다) 가득 찰 때만 보이는 끝 조각 위젯(바인딩 · C++ — 총괄 몫). 추천 (나).
- **손상 방지:** 바뀌는 텍스처 = 대상 글자 자리 · 채움 텍스처(+ (나)면 새 끝 덮개 이미지)뿐 — 회귀 묶음 기준선 **`l_final_1119`**(결과 단위 끝 — `state_fix_1119` 와도 비교), `+ new` 0 · 보호 run 깨짐 0, 정답 묶음 30/30 · 1/1 · 7/7 + 새 항목, pytest 399 +. 에디터 run 은 L-1 CombatHUD 1 회 · L-2 1 회 · 파티 1 회(외부 입력 길 확인 — 이번엔 고친 대상이므로), 재시도로 통과 얻지 않음.
- **순서:** ① 원인 가르기(안쪽 윤곽 — 원본 출력 단계별) ② 검사(숨는 묶음 S4 · 가는 선 · 게이트 같은 고르기) 기록만 + 정답 묶음 + 묶음 재진단 ③ H1 · H2 · H3 오프라인 겨루기 · 회귀 비교(입력마다 S4 가 좁은 판보다 나빠지지 않는지 — 결과 단위의 조작 안내 교훈) ④ H4 ⑤ 오류 승격 · pytest ⑥ 에디터 run ⑦ 사람 눈.
- **결정(사용자, 11-19):** ① 게이지 끝 = **(나) 중간은 곧은 끝 + 가득 차면 호**(끝 덮개 이미지 — C++ 없음, 가장자리 부드럽게) ② 지우기 범위 = **모든 글자 다시 시도**('all' — 게이트와 같은 고르기가 예전보다 나빠지는 글자는 예전 판으로 되돌림) ③ **파티 · 조작 안내도 이번 범위**(다른 메움 길 H3 + 파티 에디터 run 1 회). 구현은 새 세션(인계 `uigen-text-erase-finish-handoff.md` — 공유 노트 폴더 local_ed21a9e8…).

**1b 후속 L 다음 — 글자 지우기 마감 결과 (11-19, 미커밋 — 구현 하위 세션. 쓰기 = Tools/uigen · 이 문서, C++ · WidgetMcp 변경 없음 · 승격은 총괄 몫)**

- **① '4' 안쪽 윤곽 원인 [실측 — R20261119_190059 refine 오프라인 다시 굽기, `_plate_item_fill` 지역 변수 단계 그림]:** LaMa 원본 출력은 깨끗했다(붙인 자리 안 '4' 모양 없음 · 알파 `low` 갈래 0 px · 알파 0.98 이상). 안쪽 윤곽 = **붙인 자리 안에 안 붙이고 남긴 컨셉 픽셀 385 px — 전부 판 구조물 지킴(`same_struct` — 판 ±2 px 이동 최소 차 < 24)**: codex 판이 '4' 빛 테두리를 덜 지워 그 자리가 '판에도 있는 구조물'로 지켜졌고 컨셉의 빛 테두리가 선으로 남았다(가는 선 지킴 0 px — 결과 절의 추정 둘 다 아님). 바깥 윤곽 = 섞임 띠(`NOTEXT_GROW` 흐림)에 색조 맞춘 판 색이 섞임(띠 최대 ΔE00 80 — 판이 컨셉보다 갈색).
- **② 검사 [실측 · 보정]:**
  - **S4 숨는 묶음**(`state_check.texture_groups` — 시작 때 숨는 위젯 중 자기 · 자손이 텍스처를 그리는 것): 그 위젯만 켠 글자 없는 상태(합성 · 엔진 `state_notext_<위젯>` = 다른 숨는 위젯 끔 + 그 위젯 visible + 모든 글자 `text ""`)에서 그 아래 글자 자리를 같은 판정, 결함 · 기록에 `state`. compare.png 상태 띠에 '<위젯> shown, texts empty' 줄. 글자만 숨는 것('오의 불가')은 S1 · F1 그대로.
  - **S4 가는 선 `text_contour`:** 자리 안 픽셀 차(같은 설명) > 2.5 가 1 px 틈을 이어(`text_contour_link` — 이은 덩어리 원래 픽셀 ≥ 30 %) 골격(Zhang-Suen — numpy) ≥ 40 px · 두께(넓이 ÷ 골격) ≤ 3, 짧은 변 ≤ 5 · 긴 변 ≥ 4 배인 곧은 선은 구조선(`line_like` 기록만). 잇기 전에는 190059 '4' 가 조각나 골격 24 px(문턱 아래) → 이은 뒤 53 px.
  - **(마) 설명 = 둘레에 색조 맞춘 판(`_tone_matched` — 자리 둘레 고리에서 채널마다 평면, ± 40):** 판 그대로 설명은 텍스처가 둘레와 색조가 다른 판 조각을 글자 자리에 붙인 얼룩까지 '판과 같다'로 설명했다. 바꾼 뒤 새로 잡힌 것은 그림으로 모두 실제 흔적(조작 안내 '링크 어택' 판 조각 7.1 · 원본 '돌진 공격' 가는 선 4.1 · 단색 '4.2' 등).
  - **배너 '체인 버스트' · '3' 은 게이트 문턱으로 못 잡음(사실대로):** 어두운 판(L* ≈ 9)의 ΔL* 1 ~ 2 흔적이라 ΔE00(SL 가중 — 어두운 쪽 둔감) 3 × 3 최대 1.47 · 가는 선 0. 글자 모양 상관(획 가장자리 무늬 ↔ 고주파)도 깨끗한 L-2 와 못 가름. **밝힌 검정(검정 합성 × 3 — `appearance.text_trace_lift`)** 은 배너 4.5 · 깨끗한 L-2 0.5 로 가르지만 보호 run 조작 안내도 5 ~ 9 로 부풀어 게이트로 못 씀 → **기록만**(`local_max.lift`), refine 고르기의 부 지표와 정답 묶음 '기록 지표' 항목(`lift_min` 4.0)으로만 쓴다.
  - 정답 묶음 + 3: 190059 '4' 가는 선(`text_contour`) · 190059 배너(밝힌 검정 기록 ≥ 4.0) · 003127 '0 %'(`text_trace` · `text_contour`).
- **③ H1 · H2 · H3 + 게이트와 같은 고르기:**
  - **고르기(`refine._gate_erase_choice`):** 지울 글자가 있는 텍스처를 방법마다 굽는다 — `lama`(G1 넓힌 자리 + 인페인팅) · `harmonic`(넓힌 자리를 미리 곱한 색 · 알파 함께 경계값 보간) · `off`(예전 좁은 판). refine 끝에 합성용 spec 사본(margin · 크기 고정 image · 넘침 적용)과 `_boxes_from_spec` 상자로 캔버스 합성 → `diagnose.composite_text_trace`(= `text_glyph_masks` + `state_check.text_trace` — 회귀 묶음 replay 와 같은 함수) → 글자마다 `_erase_ok`: S4 ≤ max(off, 3.0) + 0.5 · 결함 수 ≤ off 이고, 결함을 줄이면 받음 / 같으면 가는 선 길이 ≤ max(off, 20) · (문턱 위 S4 가 뚜렷이 나아지지 않으면) 밝힘 ≤ off + 1.5. 받을 수 있는 방법 중 (결함, S4, 밝힘) 최소 → 섞이면 그 계획으로 다시 굽고 전체 다시 합성해 확인 → 나빠진 글자는 off 로 한 번 더 → 그래도면 그 텍스처 전부 off. 텍스처 단독 점수(`_trace_score` · `_erase_choice`)는 지웠다. 지운 판 후보에서는 OCR '구운 글자' 물러남(상자째 · 판 없이 다시 굽기)을 안 한다(기록 `text_marks_erase`) — 그 물러남이 다른 글자 · 게이지 트랙까지 바꿔 후보 점수를 오염시켰다(파티 lama 후보 초록 막대 · 삼각 조각).
  - **H1** 텍스처째 숨는 위젯 안 글자도 지움(`_same_hidden_group` — 밑 텍스처를 쓰는 위젯이 모두 같은 숨는 위젯 아래). **H2** 지우는 글자: 판 구조물 · 길고 가는 선은 글자 · 빛 자리를 **가로지르는 것만** 지킴(`_crossing` · 판 구조물은 둘레와 ΔE00 10 넘게 다른 것 — `_struct_keep`; 평평한 바탕까지 한 덩어리인 '판에도 있는 픽셀'을 그대로 지키면 harmonic 경계값 검은 점), 자리 안 갇힌 칠 안 된 픽셀 메움(`_fill_enclosed`), 지울 자리 최소 = 획 + `ERASE_PAD` 6 px(상자 밖 획 포함 — 어두운 외곽 그림자 · 잘린 획 끝이 인페인팅 마스크 경계에 걸려 LaMa 가 글자를 다시 그렸다), 인페인팅 섞임 띠 = 인페인팅 출력(판 색 안 섞음), `gen/inpaint` 거울 채움 때 마스크도 거울(텍스처가 512 보다 작으면 거울에 비친 글자 사본을 LaMa 가 베껴 배너 '3' 을 흰 글자로 다시 그렸다 — 캐시 판 `lama-v3-mirrored-mask`). **H3** 판 중앙값 · 투명 위 글자 둘레 · 좁은 둘레 길도 같은 후보(`_erase_fill`) — 판 정합 길은 harmonic 도.
  - **오프라인 190059 [실측]:** 체인 '4.2' off 6.65 → lama 2.68(결함 1 → 0) · '체인' 1.49 → harmonic 0.71 · '2/4' 1.02 → harmonic 0.53, 배너 '체인 버스트' 밝힘 4.54 → harmonic 3.39(글자 모양 얼룩 → 작은 점 몇 개) · '3' 4.57 → 1.71. 파티 003127 '0 %' off 46.5(결함 4 · 가는 선 89) → lama 35.0(결함 1), 이름 · HP 숫자는 후보가 모두 나빠(lama 14 ~ 97) 예전 판.
- **④ H4 게이지 끝 (나):** `concept_fill.measure` 는 채움 끝을 곧게(오른쪽 여백 END_IN + 1 — G3 호 여백 되돌림, 근사 `gauge_end_shape` 는 새 run 에서 사라짐 — 옛 spec 의 `end_shape` 읽기만 남김) 하고 끝 장식 호(`end_shape`)를 `end_cap` 으로 돌려준다. analyze `_add_end_cap` 이 채움 바로 다음(같은 Overlay — padding 자리, 캔버스 부모면 같은 앵커 위치 + allow_overlap)에 Image `<게이지>EndCap` + procedural `concept_end_cap` 에셋 하나(C++ · 바인딩 없음, 게이지가 flag · 숨김이면 안 만듦). `render_end_cap`: 트랙 끝 열(호 깊이 + 3) 중 호부터 바깥(줄마다 hole 이 처음 끊기는 열 · 구역 밖까지 이어진 밝은 구조물)은 판이 그리는 그림 그대로(빈 트랙 덧칠 `unfilled_track` — 중간 진행률엔 판과 같은 픽셀) 알파 1, 그 왼쪽 2 px 는 컨셉 밝기를 호 ↔ 빈 트랙 색으로 풀어 분수 알파 + 호 색(계단 없음). 오리기는 덮개를 구멍 · 넘침 막기로 안 본다(`end_caps`). 오프라인 190059 다시 그리기: S2 끝 덮음 0.0 · 끝 hole 안 바뀜 0.021 · 트랙 밖 0, 100 % 끝이 호 안쪽에서 곧은 채움 + 덮개로 맞게 들어감.
- **⑤ 오류 · 회귀 [실측]:** 새 검사는 오류(`state_record_only: []`, 밝힌 검정만 기록). **정답 묶음 33/33 caught · 1/1 clean · 7/7 protected(errors 0)**(30 + 새 3, 보호 run 상태 검사 결함은 7 run 자기 옛 텍스처 — 따로 표시). **회귀 묶음 `n_erase_1119`(14 입력) ↔ `l_final_1119` · `state_fix_1119`: `+ new` 0 · 보호 run 깨짐 0**, `+ state` 12(새 검사가 옛 run 텍스처에서 찾은 실제 흔적). **입력마다 S4 가 예전(off) 판보다 나빠진 글자 0**(같은 잣대 — 고르기 확인 합성): L-1 '4.2' 6.5 → 1.5 ~ 2.9, 단색 '4.2' 10.2 → 3.0 ~ 4.5(결함 4 → 0), 조작 안내 '링크 어택' 7.1 → 4.8(결함 1 → 0), 원본 5.9 → 2.2 ~ 2.8, 파티 '0 %' 46.5 ~ 49.3 → 21.6 ~ 35.0(결함 4 → 1). 바뀐 텍스처 = 지운 글자 상자뿐(L-2 둘은 아트 모드 — 변화 0). pytest **399 → 406**(403 + 정답 묶음 시험 3).
- **⑥ 에디터 run [실측]:**

  | run | 결과 | 비고 |
  | :--- | :--- | :--- |
  | **`R20261119_235452_CombatHUD`(L-1)** | **통과 — 오류 0 · 근사 1**(`gauge_end_glow` — 컨셉 70 % 진행 끝 빛, 예전부터) | 고르기: 체인 '4.2' lama · '체인' · '2/4' · 배너 둘 harmonic. 엔진 렌더 S4 '4.2' 2.2(다른 값 '9.7' 1.3) · '체인' 0.9 · '2/4' 0.7, 숨는 묶음 배너 1.6 · '3' 1.0(밝힘 3.5 · 2.2), 가는 선 0. S2 끝 덮음 0 · 끝 빈틈 0.02, `UltGaugeEndCap` 17 × 44(호 깊이 13). `gauge_end_shape` 사라짐 |
  | `R20261120_001224_CombatHUD`(L-2 첫 run) | 실패 — 오류 1 = `ChainTimerText` 값 흔적(`text_value_trace` 12.9) | **거짓 양성(이번 단위가 만든 것)**: 값 바꿈 렌더('9.7')에서 판정 자리 둘레 고리에 새 글자 픽셀이 섞여 둘레 설명 · 색조 맞춘 판이 그 밝은 쪽으로 끌림(텍스처는 원본 아트 그대로). 값 검사 고리에서 값 렌더의 모든 글자 자리를 뺌(`judge(ring_excl=…)`) → 이 run 의 엔진 렌더 그대로 오프라인 재진단 오류 0(12.9 → 0.55), L-1 run 재진단도 오류 0. 시험 + 1 |
  | **`R20261120_004053_CombatHUD`(L-2, 고친 뒤 새 run)** | **통과 — 오류 0 · 근사 3**(굵기 2 · `gauge_end_glow`) | 아트 모드라 지우기 없음. 엔진 S4 ≤ 0.6 · 값 0.5. S2 끝 덮음 0 · 빈틈 0.14, `UltGaugeEndCap` 27 × 43(호 깊이 23) — 100 % 끝이 '>' 끝 장식에 맞게 들어감, 0 · 5 % 는 컨셉 상태와 같음 |
  | `R20261120_005215_ProbePartyHUD`(파티) | **실패 — 구조 통과, 진단 오류 4 = 모두 새 S4(E8)** | 이름 `NameText` 2(16.9 · 16.4 — HP 막대 윗선 위 남은 컨셉 빛 · 홈), '0 %' 1(37.1 — harmonic 이 골라졌지만 주황 빛 덩어리), 방패 숫자 가는 선 1(골격 54 · 13.2 — 다시 그린 방패 판 조각). 옛 파티 run 003127 텍스처에서도 같은 자리 · 크기로 잡히던 실제 흔적. **원인:** 투명 바탕 위 빛 글자는 지울 자리 밖에도 컨셉 빛 알파가 넓게 남아 lama(투명 자리에 무늬를 지어냄)도 harmonic(둘레 빛 알파를 이어 뿌연 덩어리)도 예전 판보다 나빠 고르기가 예전 판(off)을 지킴. 지울 자리를 잰 빛 꼬리 끝까지 넓히는 시도는 '0 %' 36.6 → 38.5 로 나아지지 않아 되돌림. 같은 설정으로 다시 돌리지 않음 |
- **⑦ 사람 눈(요청 — 승격은 총괄 몫):** L-1 `work/R20261119_235452_CombatHUD/compare.png`(맨 아래 상태 띠 — 게임 기본 · 모든 글자 빈 값 · 값 글자 다른 값 · **배너 켠 상태 + 글자 빈 값** · 게이지 0 / 5 / 100 %) · `review/texture_zoom_chain_panel_frame.png` · `texture_zoom_burst_banner_frame.png`(컨셉 | 텍스처 | × 3 밝힘) · `review/gauge_end_concept_0_5_100.png`, L-2 `work/R20261120_004053_CombatHUD/compare.png` · `review/` 같은 그림. 오프라인으로 본 것: 체인 패널 '4.2' · '체인' · '2/4' 흔적 없음, 배너는 글자 모양 없음 · × 3 밝힘에서 작은 어두운 점 몇 개(harmonic 경계값).
- **새 검사가 다른 입력에서 찾은 진짜 결함(고치지 않음):** 파티(위 셋 — 옛 run 들도 같음) · 조작 안내 '링크 어택' 판 조각(옛 텍스처 — 새 refine replay 는 harmonic 으로 결함 0) · 조작 안내 원본 '돌진 공격' 가는 선(옛 · 새 replay 모두 — 지운 판이 더 나빠 예전 판) · 단색 '4.2'(옛 텍스처 — 새 replay 는 결함 0).
- **돌리지 않은 것:** 승격 · HUD PIE(총괄 몫), 단색 · 조작 안내 에디터 run(오프라인 replay 만), 엔진 자동 시험(C++ 변경 없음), 파티 고침(아래 결정).
- **결정 — 사용자 확인 필요:** ① 파티(투명 바탕 위 빛 글자 · 다시 그린 배지 위 숫자)는 이번 후보로 못 지움 — 투명 바탕 전용 지우기(빛 꼬리 밖 둘레 알파 ≈ 0 으로 · 판 알파가 투명이면 투명) 같은 다음 단위로 할지 ② 배너 낮은 대비 흔적은 게이트 아닌 기록 지표(밝힌 검정)로만 지킴 — 받아들일지 ③ 100 % 에서 L-1 채움의 곧은 진행 끝 테두리가 호 꼭짓점 안쪽에 남음(그림 `gauge_end_concept_0_5_100.png`) — 사람 눈 판정.

**1b 후속 L 다음 — 글자 지우기 다음 설계 (11-20 작성 · 구현 전 — 사용자 '채택할 것 · 잘못된 부분 · 해결 설계까지 쓰고 이 세션 종료', 바탕 = 위 마감 결과 + 사용자 눈 + 사용자가 가져온 일반 글자 지우기 구조 비교. 구현은 새 세션 — 인계 `uigen-text-erase-next-handoff.md`(공유 노트 폴더 local_ed21a9e8…))**

- **계기 [사용자 눈 — 마감 결과 run]:** ① L-1 배너 `T_burst_banner_frame` 의 글자 지운 자리에 작은 점들 ② 파티 텍스처(글자 빈 값)에서 HP 막대 둘레 테두리 · '0 %' 자리가 깨끗하지 않음 — "판정으로는 통과라서 그런가". 답: ①은 **통과라서 남음**(엔진 S4 1.6 < 5 — 어두운 판에서 ΔE00 이 둔함, 밝힌 검정 3.5 는 기록만) ② 파티 run 은 실패(이름 · '0 %' · 방패 오류)지만 **HP 숫자 쪽 막대 윗선 자국은 판정 사각**(흔적 7.1 이지만 22 × 2 선이라 '짧은 변 ≤ 2 px = 구조선' 규칙으로 기록만 · 가는 선 골격 39 < 40).
- **가져온 구조(6 단계) 대비 — 채택 · 활용 · 안 함:**

  | 단계 | 가져온 구조 | 지금 | 판단 |
  | :--- | :--- | :--- | :--- |
  | 1 마스크 | 단어 상자 + 여백 ≥ 6 px, OCR 상자 합침(어두운 외곽선 글자) | 픽셀 마스크(획 = 컨셉 ↔ 글자 없는 판 차 · 글자색, + 빛 꼬리 ≤ 24 · + `ERASE_PAD` 6, 가로지르는 구조물 지킴), 글자 위치 = spec 상자 | **활용** — OCR 상자는 '지울 수 있는 범위(상자 밖 획)'를 넓히는 데만, 상자째 지우기는 안 함(상자에 걸친 테두리 · 막대선을 다시 그려 UI 깨짐 위험 — 지킴 규칙 유지) |
  | 2 인페인팅 | LaMa(big-lama.pt), cv2.inpaint 금지 | LaMa ONNX(같은 가중치) + harmonic + 예전 판 후보, 게이트 같은 고르기 | **지금 유지**(.pt 는 PyTorch 새 설치가 필요 — 이득 없음) |
  | 3 합성 | 마스크 안만 교체 · 경계 페더링 | 같음(섞임 띠 2 px · 인페인팅 출력), 알파는 둘레에서 따로 | 유지 |
  | 4 검증 A | 마스크 밖 원본과 차 = 0 | **없음**(회귀 묶음이 상자 단위로만 봄) | **채택** — 손상 방지 공백 |
  | 5 검증 B | 다시 OCR → 잔여물이면 여백 키워 다시 · 놓친 글자면 마스크에 추가, 최대 2 회 | 남으면 바로 예전 판(재시도 없음), 상자 밖 OCR 자국은 장식 | **채택(일부)** — 잔여물 → 여백 키워 다시(최대 2 회). '놓친 글자 추가'는 안 함: 우리 글자는 spec 위젯이라 엔진이 다시 그린다 — spec 에 없는 글자를 지우면 내용이 사라진다 → 대신 기록 + 진단(놓친 글자 = analyze 누락 — 사람 확인) |
  | 6 복잡 배경 분기 | 둘레 엣지 밀도 · 색 분산 크면 ComfyUI FLUX Fill · Qwen-Image-Edit, 없으면 '수동 확인 필요' | 없음 | **채택(인터페이스만)** — 판정 · 기록 · '수동 확인 필요' 표시 + 백엔드 자리(ComfyUI 는 Phase 5 — 지금 워크플로 없음) |

- **지금 잘못된 부분 [실측 · 소스]:**
  - **W1 harmonic 경계 잡티 → 점(배너):** `_erase_fill` harmonic 은 지울 자리 밖 픽셀 값을 그대로 경계로 쓴다 — 경계에 걸린 어두운 잡티 · 그림자 조각이 라플라스 보간으로 안쪽에 번져 점이 된다(× 3 밝힘에서 보임). 고르기는 예전 판(글자 모양 얼룩)보다 나아 받았다.
  - **W2 판정 사각 — 어두운 판 낮은 대비:** S4 는 ΔE00(SL 가중 — L* ≈ 9 에서 ΔL* 를 ÷ 1.6)이라 배너 흔적 1.5. 밝힌 검정(× 3)을 오류로 올리지 않은 이유는 보호 run 조작 안내 5 ~ 9 — 그런데 뒤에 그 발견 일부(조작 안내 '링크 어택' 판 조각 · 원본 '돌진 공격')가 그림으로 **실제 흔적**이었다 → 보정이 끝나지 않았다(거짓 양성인지 분류 안 함).
  - **W3 판정 사각 — 구조선 규칙이 너무 넓음:** `text_trace` 의 짧은 변 ≤ 2 px 선 · `text_contour` 의 곧은 선은 '구조선(다시 그린 판과 1 px 어긋남)'이라며 기록만 — 그 선이 **글자 없는 판에도 있는 선인지**는 안 봐서, 막대 윗선 위에 남은 글자 빛 자국(파티 HP 숫자 22 × 2 · 7.1)도 빠졌다. 가는 선 길이 문턱 40 에 39 로 1 px 모자란 것도 같은 자리.
  - **W4 투명 바탕 위 빛 글자를 못 지움(파티 이름 · HP · '0 %'):** 컨셉 빛이 지울 자리 밖까지 알파로 넓게 남아 — lama 는 투명 자리에 무늬를 지어내고(알파는 둘레 경계값), harmonic 은 둘레 빛 알파를 이어 뿌연 덩어리. 잰 빛 꼬리 끝까지 넓혀도 '0 %' 36.6 → 38.5(개선 없음 — 되돌림). 원인은 '빛 꼬리'를 밝기(L*)로만 재고 알파(투명 바탕 위 빛 = 알파 테두리)로 안 잰 것 + 알파 경계값이 빛 자리 안에 있다는 것.
  - **W5 다시 그린 배지 위 숫자(파티 방패 '10'):** 판(codex)이 방패 두 톤 경계를 다른 자리에 그려 붙인 조각이 모자이크(가는 선 54 · 13.2). lama 14.8 은 바닥(max(off 8.5, 3) + 0.5) 넘어 못 받음.
  - **W6 검증 A 없음:** 지운 판이 마스크 밖을 바꾸지 않는다는 보장이 코드 읽기뿐(사용자가 가장 경계하는 UI 잔상 · 깨짐의 안전망 공백).
  - **W7 남으면 바로 예전 판:** 후보가 S4 를 못 넘으면 재시도 없이 off — 여백 · 꼬리를 더 넓혔으면 됐을 글자도 예전 판(파티 '0 %' 등).
  - **W8(사람 눈 판정) L-1 100 % 곧은 진행 끝 테두리가 호 꼭짓점 안쪽에 남음:** (나) 의 본질(채움은 곧은 끝 · 덮개는 늘 보이는 같은 픽셀)이라 덮개로는 못 지움 — 없애려면 (다) 가득 찰 때만 보이는 끝 조각(바인딩 · C++ — 총괄 몫).
- **고침 설계(조건을 좁게 — 이 문서의 같은 절차: 검사 먼저 기록만 → 묶음 거짓 양성 0 → 오류, 고침은 후보 하나 더 + 게이트 같은 고르기):**
  - **V1 검증 A(채택) `refine._outside_unchanged`:** 지운 판 후보마다 '바꿀 수 있는 자리' = 그 텍스처 모든 글자의 (지울 자리 ∪ 좁은 판 자리) + 섞임 띠(`NOTEXT_GROW` + 흐림 3σ) 를 기록(`_plate_item_fill` · `_erase_fill` 이 자리 마스크를 돌려줌), 그 밖 픽셀이 off 판과 RGBA 바이트로 같아야 함 — 다르면 그 후보 버림 + 기록(`erase_gate.outside_changed_px`). 회귀 묶음 replay 에도 같은 검사(텍스처마다 0 이어야 — `regress_set` 기록 · compare 줄).
  - **V2 판정 — 구조선 규칙 좁힘(W3):** `text_trace` line_like · `text_contour` 곧은 선은 **그 선이 글자 없는 판(색조 맞춘 판 ±2 px)에도 있을 때만** 기록만(판과 1 px 어긋난 다시 그린 구조선 — 원래 거짓 양성), 판에 없으면 결함. 가는 선 길이 문턱은 보정으로(39 · 40 경계 — 묶음 분포 보고 정함).
  - **V3 판정 — 어두운 판(W2):** 밝힌 검정을 '어두운 판 자리(그 자리 둘레 L* < 20)'에서만 쓰는 판정으로 다시 보정 — 정답 묶음 보호 run · 회귀 묶음의 밝힘 발견을 **그림으로 실제 · 거짓 분류**(이번 단위에서 일부는 실제로 확인됨)한 뒤 거짓 양성 0 인 문턱이 있으면 오류, 없으면 기록 유지(사용자 결정 ②).
  - **V4 지우기 — harmonic 경계 다듬기(W1):** 경계값 = 지울 자리 밖 3 px 띠의 **잡티 뺀 매끈한 값**(픽셀마다 5 × 5 중앙값과 ΔE00 6 넘게 다른 바깥 픽셀은 경계에서 빼고 그 자리도 메움) + 결 되살리기는 안 함(밋밋함은 S4 · 밝힘으로 고르기가 lama 와 견줌). 배너 · 체인 '체인' · '2/4' 에 오프라인 그림 · 밝힘으로 먼저.
  - **V5 지우기 — 투명 바탕 글자 후보 `clear_alpha`(W4 — 새 후보, 고르기에 넣음):** 글자 둘레 바탕이 투명(빛 꼬리 밖 둘레 알파 중앙값 < 0.35)이면 ① **알파 꼬리** = 획에서 거리마다 컨셉 알파 − 둘레 바탕 알파 중앙값이 0.03 넘는 데까지(≤ 32 px — 밝기 꼬리와 따로) ② 지울 자리 = 획 + 알파 꼬리 + 2(가로지르는 구조물 · 막대 · 테두리 지킴) ③ 알파 = 경계값 보간인데 **경계를 알파 꼬리 바깥 고리로**(그 자리 알파는 바탕 수준 ≈ 0) · 지킨 구조물 경계는 구조물 알파 ④ 색 = 남은 알파가 있는 곳만 가장 가까운 구조물 색(미리 곱한 색 경계값). 글자 밑에 정답이 없는 자리('0 %' 가 트랙 끝에 걸침 — 판도 트랙 끝을 다르게 그림)는 판이 그 자리를 불투명하게 그렸으면 판의 트랙 끝을 경계로 쓰는 갈래 하나 더, 그래도 S4 를 못 넘으면 **'정답 없음 — 수동 확인 필요'** 기록(오류 대신 표시 — 사용자 결정 ③).
  - **V6 검증 B 반복 보강(채택 — W7):** 고르기에서 받은 후보가 없거나 받은 후보에 S4 결함이 남은 글자는 그 글자만 여백을 키워(ERASE_PAD 6 → 12 → 18 · 빛 · 알파 꼬리 + 6 씩) 다시 굽고 같은 고르기(최대 2 회) — 그래도면 예전 판. OCR(지금 rapidocr 검출)은 지운 판에 다시 돌려 **글자 상자 근처 검출 = 잔여물 → 그 글자 반복 보강 대상**, 상자에서 먼 새 검출은 지우지 않고 기록(`erase_gate.ocr_far`) + 진단 기록(spec 에 없는 글자 — analyze 누락 의심, 사람 확인).
  - **V7 OCR 상자로 지울 범위 넓힘(활용 — 가져온 구조 1):** 컨셉(레퍼런스)에 OCR 검출을 한 번(캐시) — spec 글자 상자와 겹치는 검출 상자 ∪ 상자 + 6 px 를 '지울 수 있는 범위'(`rect_e`)에 합침. 안에서 지우는 픽셀은 지금 규칙 그대로(판 · 둘레와 다른 픽셀 · 획 + `ERASE_PAD` · 구조물 지킴) — 상자째 지우지 않음. analyze 상자가 획보다 좁을 때(배너 '3' — 지금은 획 + 6 으로 땜) 일반 해법.
  - **V8 복잡 배경 분기(인터페이스만 — 가져온 구조 6):** 지울 자리 둘레 6 px 띠의 엣지 밀도(소벨 크기 > 40 비율) · 색 분산(L* 표준편차)을 기록(`erase_gate.background`), 둘 다 문턱 넘으면 그 글자 `complex_background: true` + 보고서 '수동 확인 필요' 줄. 생성형 메우기 백엔드 자리(`extract.text_fill_complex: none | comfy_flux_fill | comfy_qwen_edit`, 기본 none — 지금은 워크플로 없음, Phase 5 ComfyUI 와 함께) — 있으면 같은 마스크 · 같은 합성 · V1 · S4 고르기를 거친다.
  - **W5 방패(다시 그린 배지 위 숫자)** 는 V6(여백 키운 lama 재시도 — 문맥을 배지 실루엣 안으로 한정) · V8(배지 결 · 두 톤 → 복잡 배경이면 수동 확인)로 먼저 보고, 남으면 사람 결정.
- **손상 방지 · 검증:** V1 이 모든 후보에 붙고(마스크 밖 0), 바뀌는 텍스처 = 대상 글자 자리뿐 · 회귀 묶음 기준선 **`n_erase_1119`**(이 결과 절 끝 — `l_final_1119` 과도) 대비 `+ new` 0 · 보호 깨짐 0 · **입력마다 글자 S4 가 예전(off)보다 나빠지지 않음**(`gate_summary` 와 같은 표 — 이번엔 저장소 도구로 `regress_set` 에 넣음) · 정답 묶음 33/33 · 1/1 · 7/7 + 새 항목(파티 HP 막대 윗선 자국 · 배너 점 — 밝힘 기록 또는 오류) · pytest 406 +. 에디터 run: L-1 · L-2 · 파티 각 1 회(재시도로 통과 얻지 않음).
- **순서:** ① V2 · V3 검사(기록만) + 정답 묶음 새 항목 + 묶음 재진단(밝힘 발견 그림 분류) ② V1 검증 A ③ V4 · V5 오프라인 겨루기(배너 · 체인 · 파티 · 조작 안내) ④ V6 · V7 ⑤ V8 인터페이스 ⑥ 오류 승격 · 회귀 · 정답 묶음 · pytest ⑦ 에디터 run ⑧ 사람 눈 → 승격(총괄).
- **결정 — 사용자 확인 필요:** ① V8 생성형 메우기(ComfyUI FLUX Fill · Qwen-Image-Edit)는 인터페이스만 · 수동 확인 표시까지로(워크플로 · 모델 내려받기는 Phase 5) ② V3 밝힌 검정 — 보정에서 거짓 양성 0 문턱이 있으면 오류로 올림 ③ V5 '0 %' 처럼 글자 밑 정답이 없는 자리는 고치지 못하면 오류 대신 '수동 확인 필요'로 통과시킬지(아니면 파티 run 은 계속 실패) ④ W8 L-1 100 % 테두리 — 받아들임 / (다) 총괄로 넘김.
- **결정(사용자, 11-20 확정):** ① V8 은 인터페이스만(판정 · `complex_background` 기록 · 보고서 '수동 확인 필요' 줄 · 백엔드 자리 `extract.text_fill_complex: none`, ComfyUI · 모델 내려받기 안 함 — 끝 보고에 입력마다 '복잡 배경' 글자 수) ② V3 — 묶음 밝힘 발견을 그림으로 분류, 거짓 양성 0 문턱이 있으면 오류 ③ 글자 밑 정답 없는 자리는 못 고치면 '정답 없음 — 수동 확인 필요'(근거 기록 · 다른 결함은 그대로 오류 · 진단 · 보고 · compare 에서 눈에 띄게) ④ W8 은 총괄이 (다)로 — 이 단위는 게이지 끝 코드(`concept_fill` · `_add_end_cap` · `render_end_cap`)를 안 건드림.

**1b 후속 L 다음 — 글자 지우기 다음 결과 (11-20, 미커밋 — 구현 하위 세션. 쓰기 = Tools/uigen · 이 문서, C++ · WidgetMcp · 게이지 끝 코드 변경 없음 · 승격은 총괄 몫)**

- **① V2 · V3 검사(기록만 → 묶음 보정 → 오류) [실측 — 정답 · 회귀 묶음 32 run 기록만 재진단]:**
  - **V2 구조선 규칙 좁힘(`state_check.plate_line`):** 선 모양 덩어리(짧은 변 ≤ 2 px · 곧은 가는 선)는 그 선 픽셀의 60 % 이상이 색조 맞춘 판 ±2 px 로 판 바탕보다 2 넘게 잘 설명되고 판의 그 자리가 판 바탕과 `text_trace_de` 넘게 다를 때만 구조선(기록만). 발견 = 파티 run 셋(130201 · 003127 · 005215)의 같은 HP 숫자 막대 윗선 약 5 px 위 녹색 빛 반원 23 × 2(판에 없음 · closer 0.51 · 판 대비 4.1 — 사용자 눈 실제)뿐, 판에 있는 선 0 → **`appearance.text_line_plate: error`**. 가는 선 길이 분포 = 39 는 그 HP 숫자 둘, 30 대 = 파티 방패 · 조작 안내 원본 '공격', 50 넘음 = 모두 실제 결함 → 문턱 40 유지(39 반원은 V2 가 잡음).
  - **V3 밝힌 검정(`ring_l` · `lift_like`):** 어두운 판 자리(둘레 고리 검정 합성 L* < 20)의 밝힘 3 × 3 국소 > 3.0 · ≥ 24 px 덩어리 63 개(18 run)를 그림으로 분류 — **모두 실제 흔적**(최저 3.7 = 190059 '4' 가는 윤곽, 4.1 · 5.2 = 파티 빛 줄기), 깨끗한 판(L-2 셋 · 마감 L-1 235452)은 덩어리 0(국소 최대 3.6) → 거짓 양성 0 문턱 4.0 으로 **`text_lift_mode: error` · `text_lift_de: 4.0`**(사용자 결정 ②). 밝은 자리(조작 안내 5 ~ 9 — 예전에 게이트로 못 쓴 이유)는 판정 밖.
  - 정답 묶음 + 3: 005215 HP 숫자 막대 윗선 자국(V2 오류) · 235452 배너 점(밝힌 검정 기록 지표 `lift_min` 3.0 — 국소 3.41, 덩어리 < 24 px 라 V3 오류 문턱 아래) · 보호 L-2 004053.
- **② V1 검증 A(`refine._outside_unchanged` 자리 — 이름은 `_outside_changed`):** 글자 메움 함수(판 정합 길 · 판 중앙값 · 투명 위 둘레 · 좁은 둘레 · `_erase_fill` · `_hidden_text_fill` · 가득 찬 게이지 · compose 창 물러남)가 '바꿀 수 있는 자리'(메울 자리 + 섞임 띠 = 넓힘 + 흐림 3σ — `_blend_band` 가 그 밖 섞임 무게를 0 으로 자름)를 `_zone` 으로 돌려주고 쓰기는 그 안만(`_put` — pm / 알파 되돌림 반올림 차도 안 남김). `_plate_entry` · `_cut_entry` 가 텍스처 크기 자리(늘림이면 LANCZOS 반경만큼 넓힘)를 모으고, 고르기는 후보마다 두 판 자리 합 밖 RGBA 바이트(알파 0 픽셀의 번짐 색은 뺌)를 견줘 다르면 버린다(`erase_gate.outside_changed_px`, 섞인 계획 다시 굽기도). **겨루기 · 회귀 모든 후보 0 px.**
- **③ V4 · V5 오프라인 겨루기:**
  - **V4(harmonic 경계 잡티 빼기 `_boundary_specks` — 밝힌 그림으로도 잼):** 배너에서 잡은 점 0 ~ 1 px, 켬/끔 결과 같음 — 그림으로 가른 실제 원인은 경계 잡티가 아니라 **한 글자 위젯 안 글자 사이 · 낱말 사이 틈에 남은 바탕 얼룩**(매끈하게 지운 자리 사이에 고립돼 × 3 밝힘에서 점). 고침 = `_erase_zone` 닫기 `ERASE_CLOSE`(지울 수 있는 범위 · 지킬 것 밖 · 자기 상자 + 2 안) 6(글자 사이만 닫혀 낱말 사이 점 남음) → **12**(글자 자리 한 덩어리), **단 다른 글자 상자와 겹치지 않는 글자만**(`lone` — 겹친 체인 패널 '체인' · '4.2' · '2/4' 에서 닫기가 이웃 경계에서 곧게 잘려 가는 선 98 · 서로 나쁘게 해 회귀 q_next_1120 에서 패널이 통째로 예전 판). 차이 꼬리(둘레 · 판 대비 밝힌 그림 차 고리로 지울 자리 넓힘)는 배너 3 ~ 4 px 로 효과가 작고 단색 '2/4' lama 를 5.87 로 나쁘게 해(끄면 1.62) **끔**(`ERASE_DIFF_TAIL`). L-1 235452 겨루기(최종 코드): 배너 '체인 버스트' S4 1.38 → 1.14 · 밝힘 3.23 → 2.43, '3' 밝힘 4.04 → 1.65, 체인 '4.2' 6.49(결함 1) → **2.23(결함 0, 밝힘 15.26 → 3.57, lama)** · '체인' 1.38 → 0.6 · '2/4' 0.92 → 0.43.
  - **V5 투명 바탕 글자 후보 `clear_alpha`(`_clear_alpha_fill` — 다섯 판 손봄, 파티 005215):** 처음 판(경계 = 알파 꼬리 고리 라플라스 · 다른 글자 상자 통째 빼기)은 이름 77 · Lv 87(빛과 이어진 막대를 지켜 30 px 넘게 번짐 · 겹친 상자를 서로 빼 'Lv 100' 윗부분 남음) → 최종 판 = 알파 꼬리(거리마다 컨셉 알파 − 바탕 알파 > 0.03, ≤ 32 px) + 자기 상자, 판(±6 정합 · 색조 맞춤)은 Z 밖으로 이어진 판 구조물만(Z 안에 갇힌 판 덩어리 = codex 판이 덜 지운 글자 'Lv 지크'), 판에 남은 글자 자국 뺌, Z 를 가로지르는 줄 토막 양끝이 같은 불투명 색이면 직선 보간(띠), 나머지는 가림 라플라스(경계에서 약 1.4 px 안에 사라짐). 겨루기: Lv 2.59 → **0.0** · '0 %' 47.0(결함 6) → 18.7(결함 4 — harmonic 38.4 결함 2 가 골라짐) · 이름 16.1 → 17.0(못 받음) · HP 숫자 8.3 → 12.4(못 받음). **에디터 run `R20261120_142400_ProbePartyHUD` 에서 Lv · 이름 · HP 에 골라져 빈 값 S4 는 좋아졌지만 컨셉 상태 진단 E1(글자 구역 바탕) 9 · E6 2 를 새로 만들었다** — 이 컨셉은 글자 빛이 엔진 빛보다 넓어(알파 꼬리 10 ~ 14 px) 텍스처에서 지우면 컨셉 상태가 달라지는데, 고르기는 S4(빈 값)만 본다 → **옵트인**(`extract.text_erase_methods: [lama, harmonic]` 기본, `refine.erase_methods`). 다음에 켜려면 고르기에 컨셉 상태 바탕(엔진 글자 + 빛 자리 밖 합성 ↔ 컨셉) 검사를 더해야 한다.
  - **'정답 없음 — 수동 확인 필요'(사용자 결정 ③ — `_no_truth` · `diagnose.manual_checks/manual_match` · compare.png 자홍 'M' 상자 + 위 판 밑 줄 · `report.recorded.manual_check` · run.log 줄):** 근거 = ① 획 둘레 1 ~ 4 px 고리의 20 % 이상이 자리 밖 구조물 대표색(빛 대표색보다 5 넘게 가까움 — 글자가 구조물 위에 앉음) ② 구조물 ↔ 투명 가장자리가 글자 자리로 들어감(≥ 10 px) ③ 판이 그 구조물을 글자 밑에서 다르게 그림(판 ±2 px ΔE00 중앙값 > 10 또는 투명) — 셋 다일 때만 그 자리 안 S4 결함(같은 글자 · 결함 상자 60 % 이상)이 오류 대신 표시, 다른 결함은 그대로 오류. 첫 근거(구조물 픽셀 + 판 투명)는 이 컨셉의 불투명 빛 고리를 구조물로 봐 이름 · Lv 전체를 '정답 없음'으로 만들어 버렸다(남발). 최종 근거로 파티 이름 · Lv(고리 = 빛) · '0 %'(판이 보이는 트랙과 같게 그림 — ΔE00 4.7, 고리 구조물 색 5 % → 판이 정답 근거)는 **모두 표시 0** — '0 %' 는 정답이 없는 자리가 아니라 판으로 고칠 수 있어야 하는 자리로 판정됐다.
- **고르기에 컨셉 상태 글자 구역 바탕 검사(이 단위에서 더함 — 설계 밖, 손상 방지):** `diagnose.text_zone_bg`(진단 E1 글자 구역 바탕 · 회귀 묶음 텍스처 지표와 같은 정의 — 글자 상자 + 4 + 빛에서 컨셉 획 · 빛 자리 + 2 를 뺀 합성 ↔ 정답 7 × 7 국소, > local_de 픽셀 `bg_px`)를 게이트 같은 합성에서 같이 재고 `_erase_ok` 가 예전 판보다 24 px(결함 최소 넓이) 넘게 늘면 거절(`ERASE_BG_MARGIN`). 이유: 고르기는 빈 값 S4 만 봐서 **파티 방패 '10' lama(S4 8.5 → 2.4 인데 두 톤 배지를 다시 그려 컨셉 상태 E1 7 · E4 1, 최대 75 — run `R20261122_135359`)** · Lv clear_alpha(E1 9 — run `R20261120_142400`)를 골랐다. 이 검사로 단색 '체인' lama(바탕 59 px)가 거절돼, '4.2' 를 지우면 예전 판 '체인'이 2.69 → 14.45 로 나빠지므로 '4.2' 도 예전 판(10.4 · 결함 5 — 원래 있던 흔적)으로 남는다 — 앞 단위 회귀(n_erase_1119)의 '체인 · 4.2 · 2/4 전부 lama' 는 이 컨셉 상태 위험을 못 본 선택이었다.
- **④ V6 · V7:** **V6** 계획 값 '방법@단계'(`ERASE_PAD_STEP` 6 — 여백 · 빛 · 알파 꼬리 + 6 × 단계), 받은 후보에 결함이 남았거나 받은 후보가 없는데 예전 판에 결함 · OCR 잔여물이 있는 글자만 @1 · @2 × 후보마다 다시 굽고 같은 고르기(V1 확인 포함) — 파티 이름 · HP · '0 %' 에 돌았지만 받은 개선 0. 지운 판 OCR(`_ocr_marks` — 판에도 있는 자국은 장식이라 뺌)의 먼 검출은 `ocr_far` 기록(조작 안내에서 1). **고르기 확인 보강:** 예전 판(off)으로 둔 글자가 상자 겹친 이웃의 지우기 탓에 나빠지면 그 이웃을 off 로(`off_worse` — 회귀 첫 판에서 단색 '2/4' · 파티 HP 숫자가 이 사각으로 나빠졌다). **V7** 컨셉 OCR 한 번(`refine_concept_ocr.json`) — 글자 상자와 겹친 검출 + 6 px 를 획 찾기 · `rect_e` 에 합침(상자째 안 지움, `extract.text_erase_ocr`). L-1 4 상자 · 파티 4 상자, L-1 켬/끔 결과 같음(획이 이미 상자 + 여백 안).
- **⑤ V8 인터페이스(사용자 결정 ①):** 지울 자리 둘레 6 px(다른 글자 자리 뺌)의 엣지 밀도(미리 곱한 루마 소벨 > 40 비율) · L* 표준편차 — 띠를 가로지르는 긴 곧은 엣지 줄(15 px 넘고 둘레 엣지가 빽빽하지 않은 것 — 막대 윗선)은 뺌(첫 판에서 파티 HP 숫자가 막대 윗선 때문에 '복잡') — 둘 다 `extract.complex_background{edge_frac 0.35, l_std 12}` 넘으면 `complex_background` → `erase_gate.complex` · 보고 '수동 확인 필요' 줄 · compare 줄, 백엔드 자리 `extract.text_fill_complex: none`(워크플로 · 모델 없음 — Phase 5). **입력마다 '복잡 배경' 글자 수는 아래 회귀 표**.
- **⑥ 오류 승격 · 회귀 · 정답 묶음 · pytest [실측]:** V2 · V3 오류(`state_record_only: []`). **정답 묶음 33/33 · 1/1 · 7/7 → 35/35 caught · 1/1 clean · 8/8 protected(errors 0)**(보호 7 run 의 상태 검사 결함은 그 run 자기 옛 텍스처 — 따로 표시). **pytest 406 → 422**(새 `tests/test_text_erase_next.py` 16 · 정답 묶음 시험 포함 — 최종 코드 전체 실행 25 분). **회귀 묶음 `s_next_1122`(최종 코드, 14 입력) ↔ `n_erase_1119` · `l_final_1119`: `+ new` 0 · 보호 깨짐 0 · 예전 판보다 나빠진 글자(S4 · 결함 수 · 컨셉 상태 바탕) 0 · V1 자리 밖 0(14 입력 전부)**. `+ state` 늘어남 = V2 · V3 오류 승격이 옛 run 텍스처에서 잡은 실제 흔적(보호 run 은 자기 텍스처라 따로 표시). 고른 판 ↔ 예전 판 S4(같은 잣대): L-1 둘 '4.2' 6.65 · 6.49 → 2.91 · 1.53(결함 2 · 1 → 0, lama) · 배너 '체인 버스트' 1.47 · 1.50 → 1.16 · 1.15(밝힘 4.5 → 2.5) · '3' 밝힘 4.6 · 3.7 → 1.7, 조작 안내 '링크 어택' 7.1(결함 2) → 5.3 ~ 5.6(0) · 원본 5.9(1) → 2.1(0), 파티 1119 '0 %' 46.5(결함 7) → 36.6(2), 단색 셋 '2/4' 2.4 ~ 2.5 → 1.8(lama, 셋 중 하나는 harmonic 2.9) · '4.2' 예전 판(위 바탕 검사), 나머지 같거나 낮음 · 고른 판의 컨셉 상태 바탕 결함 픽셀 증가 ≤ 16. 바뀐 텍스처 = 지운 글자 자리뿐(V1). **V8 '복잡 배경' 글자 수(입력마다 — 결함 남은 수 / 깨끗):** L-1 0 · L-2 0(지우기 없음) · 최종 L-1 run 0 · 최종 파티 run 0 · 파티 130201 0(정답 없음 근거 1 — 진단은 그 run 옛 refine 이라 변환 없음) · 파티 1119 1(방패 — 결함 남음) · 단색 a 1('2/4' — 깨끗) · 단색 b 2('체인' · '2/4' — 깨끗) · 단색 1119 1('2/4' — 깨끗) · 조작 안내 넷 각 1(E 키 배지 — 깨끗). 모두 배지 둥근 테두리 · 두 톤 · 패널 장식 엣지(긴 곧은 선은 뺐음) — 생성형 메우기가 필요한 결 무늬는 아님.
- **⑦ 에디터 run [실측]:**

  | run | 결과 | 비고 |
  | :--- | :--- | :--- |
  | `R20261120_135156_CombatHUD`(L-1 첫 run) | 통과 — 오류 0 · 근사 3 | 닫기 · 차이 꼬리 고침 전 — 아래 최종 run 으로 대체 |
  | **`R20261122_133445_CombatHUD`(L-1 최종)** | **통과 — 오류 0 · 근사 2**(굵기 · `gauge_end_glow`) | 고르기: 배너 둘 harmonic · 체인 '4.2' lama · '체인' · '2/4' harmonic. 엔진 S4 ≤ 1.73 · 밝힘 ≤ 3.69(배너 2.51 — 마감 run 3.5), 값 검사 1.49, 선 · 밝힘 결함 0, V1 0. 컨셉 상태 바탕 검사는 이 run 뒤에 더했지만 L-1 고르기는 그 전후 같음(겨루기 c_l1_5 = c_l1_6) |
  | **`R20261120_140653_CombatHUD`(L-2)** | **통과 — 오류 0 · 근사 4**(굵기 3 · `gauge_end_glow`) | 아트 모드라 지우기 없음(이 단위 변경과 무관한 길). 엔진 S4 ≤ 0.59 |
  | `R20261120_142400_ProbePartyHUD`(파티) | 실패 — 오류 21(E1 9 · E6 2 · S4 10) | **clear_alpha 탓 새 결함(E1 · E6)** → 옵트인 |
  | `R20261122_110838_ProbePartyHUD`(파티) | 실패 — 오류 12(모두 S4) | clear_alpha 끈 뒤. 닫기 · 차이 꼬리 고침 전 |
  | `R20261122_135359_ProbePartyHUD`(파티) | 실패 — 오류 23(E1 7 · E4 1 · S4 14 · 게이지 1) | **방패 lama 탓 새 결함(E1 · E4)** → 컨셉 상태 바탕 검사 더함 |
  | **`R20261122_142544_ProbePartyHUD`(파티 최종)** | **실패 — 구조 통과, 진단 오류 18** | **S4 14**: 이름 흔적 2(17.0 · 16.1) · 밝힘 1(20.1), HP 숫자 V2 막대 윗선 자국 1(22 × 2 · 7.1) · V3 밝힘 7(막대 윗선 위 반원 6 ~ 18.4), '0 %' 흔적 1(35.7) · 밝힘 1(26.1), 방패 가는 선 1(13.2 — 마감 run 과 같은 옛 결함). **지우기와 무관 4**: E1 1(이름 [674, 147, 1 × 9] 21.4) · E9 1(방패) · E6 1(HP 최대) · `gauge_end_short` 1(HP 게이지) — 모두 예전 판으로 둔 글자 · 게이지 자리(run 마다 analyze 상자 · 글자 맞춤이 다름). 고르기 '0 %' harmonic · 나머지 예전 판, 반복 보강 받은 것 0, V1 0, 수동 확인 0. 마감 run 005215(오류 4)보다 늘어난 S4 는 V2 · V3 가 막대 윗선 위 빛 자국(사용자 눈 실제)을 이제 오류로 잡아서 |
- **⑧ 사람 눈(요청):** L-1 `work/R20261122_133445_CombatHUD/compare.png`(맨 아래 상태 띠 — 게임 기본 · 모든 글자 빈 값 · 값 글자 다른 값 · 배너 켠 상태 + 글자 빈 값 · 게이지 0 / 5 / 100 %) · `review/texture_zoom_burst_banner_frame.png` · `review/texture_zoom_chain_panel_frame.png`(컨셉 | 텍스처 | × 3 밝힘). 오프라인으로 본 것: 배너 × 3 에서 낱말 사이 고립된 점은 없어짐 — **단 11-23 다시 보니 지운 자리 가장자리('체' 왼쪽 · '3' 양옆)에 작은 어두운 얼룩이 남고 지운 자리가 둘레 결보다 매끈하다(× 3 에서 보임, 국소 밝힘 2.5 — 문턱 4.0 아래 · 원래 밝기에서는 거의 안 보임, 받을지 사람 눈)**(오른쪽 끝 컨셉 얼룩 결은 남음) · 체인 패널 '4.2' · '체인' · '2/4' 흔적 없음. L-2 `work/R20261120_140653_CombatHUD/compare.png`. 파티(실패) `work/R20261122_142544_ProbePartyHUD/compare.png`.
- **단색 HUD(오프라인 replay):** 체인 패널 '4.2' 는 예전 판(위 바탕 검사 — '체인' 을 지우면 컨셉 상태 바탕 59 px, '4.2' 만 지우면 '체인' 이 나빠짐), '2/4' lama · 배너 둘 harmonic.
- **다른 입력의 진짜 결함(고치지 못함):** 파티 — ① 이름 · HP 숫자 아래 **막대 윗선 위 빛 자국**(글자 빛이 막대 윗선을 물들이고 그 위 투명 자리에 반원으로 남음 — 판은 막대선을 다르게 그려 판 · 보간 · 남김 어느 것도 띠를 깨끗이 못 이음, clear_alpha 띠 직선 보간도 HP 는 매끈해졌지만 이름 아래는 선이 끊김) ② **'0 %'**(트랙 끝에 걸친 빛 글자 — 판은 보이는 트랙과 같아 정답 근거는 있으나 판 · 보간 후보가 S4 를 못 넘음: harmonic 38.4 · clear_alpha 18.7 결함 4). 같은 자리를 다섯 판 손봤으니 증상 패치를 멈춤 — 다음 접근 후보: 막대 윗선 띠를 판 띠의 줄 단위 정합(± 1 px 이동을 줄마다)으로 바꾸기 · 컨셉 상태 바탕 검사를 고르기에 더해 clear_alpha 를 다시 켜기 · V8 백엔드(생성형 메우기). 조작 안내 원본 '돌진 공격' 가는 선 · 단색 · 조작 안내 옛 텍스처의 흔적은 보호 run 자기 텍스처의 상태 검사 결함(회귀 replay 는 아래).
- **돌리지 않은 것:** 승격 · HUD PIE(총괄 몫), 단색 · 조작 안내 에디터 run(오프라인 replay 만), 엔진 자동 시험(C++ 변경 없음), V8 생성형 메우기 워크플로(사용자 결정 ①), clear_alpha 를 켠 회귀(옵트인 — 겨루기 숫자만).
- **정리(11-22 사용자 승인 — 휴지통):** 스크래치 `uigen_erase_next`(조사 · 겨루기 스크립트와 replay 사본 · 그림, 57 MB), 낡은 · 끊긴 회귀 `work/_regress/o_next_1120` · `p_next_1120` · `q_next_1120` · `r_next_1122` 와 그 비교 3 개, 낡은 · 미완 run `R20261120_135156_CombatHUD` · `R20261120_150911_ProbePartyHUD` · `R20261122_110838_ProbePartyHUD` 의 work(합계 약 560 MB). 남김: 회귀 `s_next_1122` · `compare_*_vs_s_next_1122`(비교 폴더는 11-24 사용자 승인으로 나머지 `work/_regress/compare_*` 와 함께 휴지통 — 기준선이 남아 `regress_set.py compare` 로 다시 만든다), 최종 run `R20261122_133445` · `R20261120_140653` · `R20261122_142544`, 정답 묶음 새 사본 셋, 근거 run `R20261120_142400`(clear_alpha E1) · `R20261122_135359`(방패 lama E1 — 둘 다 처분은 사용자). `Content/_AutoGen/R20261120_135156_CombatHUD`(17 개)는 쓰기 범위 밖이라 그대로 — 총괄 · 사용자 몫.
- **결정 — 사용자 확인 필요:** ① 파티(막대 윗선 위 빛 자국 · '0 %')를 다음 단위로 — 후보: 막대 윗선 띠를 판 띠의 줄 단위 정합으로 / 컨셉 상태 바탕을 지키는 clear_alpha(넓은 컨셉 빛 중 엔진 빛 밖은 남김)를 바탕 검사와 함께 다시 켜기 / V8 생성형 메우기 연결 ② V8 '복잡 배경' 수(위 — 모두 배지 · 패널 장식 엣지, 결 무늬 0)를 보고 생성형 메우기 연결 여부 ③ 단색 '4.2' 는 '체인' 과 함께 지울 방법이 없어 예전 판 — 받아들일지. 끝 보고 = 공유 노트 `uigen-text-erase-next-report.md`(local_b686cc15…).

**L-2 기본 전환 설계 (11-23 작성 · 승인 · 구현됨 — 결과는 바로 아래 절. 하위 세션. 쓰기 = Tools/uigen · 이 문서 · 승격 때 Content/UI/HUD, C++ 변경 없음)**

- **계기(사용자 결정 11-23):** ① 우리가 만드는 화면은 L-2(글자 없이 그린 원본 아트 + 글자 참고판)를 기본으로 한다 ② 글자 있는 컨셉을 받으면 L-1 로 가되 L-1 은 더 다듬지 않는다 — 못 지운 자리는 '수동 확인 필요' ③ 지금까지의 컨셉은 시험용이었다 — 게임과 어울리는 HUD 를 codex 로 새로 만든다. 글자 밑에는 정답 픽셀이 없어서 지우기를 여러 단위 다듬어도 깔끔하지 않았다.
- **갈림길 규칙:**

  | 받은 것 | 길 | 컨셉 만들기 | `concept_source` |
  | :--- | :--- | :--- | :--- |
  | 화면 설명만 | L-2 | `make_concept.py`(기본) | `generated_textfree` |
  | 글자 있는 그림 — 그대로 옮길 것 | L-1 | 없음(받은 그림) | `external` · `generated` |
  | 글자 없는 그림 | L-2, 참고판 없으면 글자는 사양만(`spec_only`) | 없음(받은 그림) | `external_textfree`(새 값) |
  | 글자 있는 그림 — 느낌만 참고 | L-2 + 참고 그림 | `make_concept.py --style-ref` | `generated_textfree` |

  - 입력의 `concept_source` 가 언제나 먼저다. 없으면 컨셉 옆 concept.json 의 `text_free_first`(우리가 글자 없이 만든 기록), 그것도 없으면 OCR 이 정한다.
- **L-1 은 멈춘다:** 코드는 외부 그림용으로 그대로 두고 새로 고치지 않는다. 못 지운 자리는 지금 있는 '정답 없음 — 수동 확인 필요' 표시까지. `fixtures/m4_combat_hud_concept`(글자 있음 — 규칙대로면 L-1)와 `m4_combat_hud_flat` · `m4_combat_hud_l2` 는 시험용으로만 남는다. 총괄이 맡기로 했던 L-1 게이지 100 % 끝 조각((다), 바인딩 · C++)은 **하지 않는다** — L-2 run `R20261120_140653` 에서 100 % 끝이 장식에 맞게 들어가는 것을 이미 확인했다.
- **새 컨셉 — 그림 방향과 배치(사용자 선택 11-23):**
  - 첫 방향 셋(A 금 간 봉인석 · B 별빛 봉인 · C 녹청 수호체)은 문서의 글(봉인 유적 · 제목의 Astral)에서만 끌어냈다. 사용자가 B 를 골라 후보 2장 · 전체 배치 시안 1장을 그렸으나(codex 3회) **'너무 우주틱하고 2D 횡스크롤 UI 같다 — 우리 게임 컨셉에 안 어울린다'** 로 버렸다. 원인 = 게임의 **실제 모습**을 안 봤다 — 주인공 Vesper 는 검은 가죽 롱코트 · 붉은 머리 · 검은 강철 낫, 수호병은 각진 기계 짐승, 그림체는 사실적인 3D(애셋 썸네일로 확인). 별 · 천구 고리 · 보라색이 우주 느낌을, 두꺼운 조각 금속 액자가 2D 느낌을 만들었다.
  - 다시 낸 방향 셋(D 검은 날 · E 가죽과 강철 · F 봉인 장치) 가운데 **D 검은 날**(사용자 선택) — 평평한 먹색 반투명 띠(끝이 사라짐) · 뼈색 1 ~ 2 px 선 · 낫날처럼 휘어 뾰족한 끝 · 강조 한 색(창백한 상아). 액자 · 입체 조각 · 별 · 문장 없음. 보스 강공격 전조가 붉은 이펙트(game-plan §7-9)라 HUD 의 넓은 면 · 빛에 빨강 · 주황을 쓰지 않는다('오의 불가' 글자만). **교훈: 그림 방향은 글이 아니라 게임의 실제 모델 · 무기 · 적에서 먼저 끌어낸다.**
  - 배치(사용자가 참고작 화면 둘을 보이며 '레이아웃 배치만 참고'): 체인 남은 시간 = 화면 가운데 **큰 고리**(안은 비어 시야를 안 가림), 오의 가능 표시 = 아래 가운데 문장 + 가로 빛줄기, 메인 HUD 칸 = 내 상태 · 파티 왼쪽 위 / 보스 위 가운데 / 목표 오른쪽 위 / 아이템 왼쪽 아래 / 스킬 오른쪽 아래. 모양 · 색 · 장식 · 글꼴은 가져오지 않고, 참고작 그림은 codex 에 첨부하지 않는다.
  - **범위(사용자 선택 '그림 먼저, 동작은 다음'):** 이번 단위 = 전체 배치 시안 1장(룩 확정 — 바인딩 없음) + 지금 계약 8개로 새 배치의 전투 HUD WBP. **전투 HUD 원본 아트는 승인한 시안에서 그 부분만 픽셀 그대로 오린다**(다른 요소 자리는 투명 — codex 추가 생성 없음, 승인한 그림과 같은 픽셀. 메인 HUD 도 뒤에 같은 시안에서 오린다). 고리(지름 약 440 px — 사용자 선택)는 가득 찬 그림 + 남은 시간 숫자. **다음 단위로 미룬 것:** 고리가 줄어드는 동작(원형 닦기 머티리얼 · `progress` 바인딩의 Image 허용 · 생성 베이스 · 스텁), 오의 가능 표시의 키 안내 글자(flag 바인딩 타입 변경), 메인 HUD 칸의 WBP. 그래서 고리 그림은 안쪽 명판과 떨어뜨려 그린다(각도로 닦아도 명판이 안 잘리게).
- **구현 네 가지:**
  1. **L-2 기본값(`make_concept.py`):** 모드 옵션이 없으면 글자 없는 원본 아트 + 참고판(지금 `--text-free-first` 와 같은 길 — 이름은 별칭으로 남김). 글자를 그리는 길은 `--with-text` 로 따로 고른다(`--flat` · `--transparent` 의 새 그림도 `--with-text` 가 있어야 함 — 없으면 이유를 적고 거절). 편집 길(`--edit` · `--text-free`)은 그대로. `--only art | text_ref` = 원본 아트 · 참고판 나눠 부르기(후보를 보고 고른 한 장에만 참고판 — 먼저 넣음, 사용자 승인). 글자 그리기를 시험하던 기존 시험 셋은 `--with-text` 를 붙인다.
  2. **OCR 로 길 고르기(`normalize.concept_source` · 새 `gen/concept_route`):** 지금 기준(검출 0.7 한 번)은 글자 없는 조작 안내 판의 장식을 0.72 ~ 0.76 으로 잡아 틀린다. 새 점수 = 원래 크기와 2 배 크기에서 **같은 자리(IoU ≥ 0.3)에 다시 잡힌 상자의 낮은 쪽 점수**, 바탕 셋(회색 · 검정 · 흰)의 최대.
     - [실측] 글자 있는 그림 7장 최대 점수의 배율 최소 **0.83 ~ 0.89**, 글자 없는 그림 8장 **0 ~ 0.66**(장식이 많은 조작 안내 판 0.66 · 후보 2 0.61). → **0.78 이상 = 글자 있음(L-1) · 0.70 이하 = 글자 없음(L-2) · 그 사이 = 모호 → L-1**(글자 든 그림을 L-2 로 보내면 텍스처에 글자가 구워진 채 정답이 돼 진단이 못 본다 — 안전한 쪽).
     - 기록 `normalize.json background.concept_source{value, from, ocr{score, boxes, per_scale, thresholds, decision}}` + `report.recorded.concept_route` + run.log 한 줄. 글자 없는 그림인데 참고판이 없으면 `spec_only` 를 같은 자리에 적는다.
     - 배경이 장면(ⓒ)인 글자 없는 그림은 알파가 없어 원본 아트로 못 쓴다 — 지금처럼 변환 길(`concept_convert`) 뒤 판정.
  3. **참고 그림(`--style-ref <png>` — 여러 번):** 새 그림에만. codex 에 '느낌 · 색 · 재질만, 배치와 요소는 요청대로' 로 첨부(`codex.generate refs`). 허용 = 우리가 만든 그림(옆 concept.json 의 generator 가 codex) 또는 `--style-ref-from-user`(사용자가 준 그림이라고 밝힘). `work/_probe`(상용 게임 화면)는 늘 거절. 투명 그림은 어두운 중립 바탕에 얹은 사본을 붙인다(알파를 무시하면 투명 자리 잡색이 보인다 — 후보 2 실측). 기록 `concept.json style_refs[{file, sha256, source}]`. 글자 · 로고를 옮기지 말라는 문구는 지금 틀(REFS_NOTE)에 있고, 글자 검사(OCR)는 그대로.
  4. **숨는 위젯의 빛 · 넘침을 그 위젯 텍스처로(`stages/layer`):** 원인 = 런타임에 접히는 위젯은 넘침 장식을 못 쓰고(`overhang_blockers`) 상자 밖 픽셀은 가장 가까운 영역의 **정적 판**으로 간다.
     - [실측 — 위젯을 끈 합성에서 그 위젯 몫 자리에 남은 픽셀] L-2 `R20261120_140653`: 배너 **23,021 px**(국소 ΔE00 최대 검정 23.1 · 회색 14.2 · 흰 22.8), **체인 패널 19,583 px**(18.1 · 11.0 · 16.1 — 컨셉에서는 켜져 있지만 게임에서는 체인이 없으면 접힌다). 예전 기록 5,443 px 는 상자 밖 4 px 고리만 센 것이다. L-1 `R20261122_133445`: 배너 189 px · 체인 패널 2,695 px(흰 바탕 35.2). 단색 `R20261119_001742`: 0 · 128 px.
     - **대상 = 시작 때 숨는 위젯만이 아니라 flag 바인딩으로 접히는 위젯 전부**(루트 직계 · 크기 고정 · 컨셉에서 오리는 브러시를 가진 것).
     - 고침: layer 첫 단계에서 그 영역 몫(보이는 픽셀 중 가장 가까운 영역이 이 위젯 · 상자에서 96 px 안)을 **자기 마스크**로 잡고, 위젯 상자를 그 범위까지 넓힌다 — canvas 슬롯 자리 · 크기, `bbox_intent`, 에셋 크기 · margin 을 같이 바꾸고 자식(글자 묶음)은 슬롯 여백을 같은 만큼 늘려 **화면 자리를 그대로** 둔다. 판 계획은 상자 대신 자기 마스크를 빼고(`layer/own_<id>.png`), 오리기는 자기 마스크 밖을 투명으로 둔다(이웃 픽셀을 안 가져감). 새로 겹친 형제 상자는 `allow_overlap`. 넓힐 수 없는 구조(루트 직계가 아님 · 여백 없는 부모)는 이유를 기록하고 검사가 오류로 잡는다.
     - 검사 `hidden_halo`(E8, `gen/state_check`): 접히는 위젯을 하나씩 끈 상태에서 그 위젯 몫 자리 + 상자에 **정적 판이 그린 픽셀**이 바탕(검정 · 회색 · 흰)과 다르면 결함(3 × 3 국소 ΔE00 > `appearance.halo_de`, 넓이 ≥ `min_area`). 엔진에서는 모두 끈 렌더 `state_toggles_off` 한 장을 더 본다. 순서 = `state_record_only` 로 기록만 → 정답 · 회귀 묶음 재진단으로 거짓 양성 0 확인 · 문턱 정하기 → 오류. `compare.png` 상태 띠에 '접히는 위젯 모두 끔' 줄을 더한다.
     - 공용 층이라 L-1 도 바뀐다 → 회귀 묶음은 refine 만 다시 돌리므로 layer 부터 다시 도는 replay(`--relayer`)를 더해 `s_next_1122` 와 견주고, L-1 에디터 run 1 회도 돌린다.
- **검증:** pytest(시작 기준 수 이상) · 정답 묶음 · 회귀 묶음 새 라벨(`l2d_1123`) ↔ `s_next_1122` `+ new` 0 · 보호 깨짐 0 · 새 컨셉 L-2 run 무인 통과(오류 0 · compare · 상태 띠 눈으로) · L-1 에디터 run 1 회. 재시도로 통과를 얻지 않는다.
- **결정(사용자 11-23 승인 '승인, 구현 시작'):** ① 위 네 가지 구현 ② 4번 대상을 flag 로 접히는 위젯 전부로 넓힌다(체인 패널도 같은 결함) ③ OCR 모호 구간은 L-1 로 보낸다. 시안은 D 첫 장이 '좋음, 무게감만 조금' → codex 편집 1 회(강철 날 질감 · 띠 정리 · 달처럼 보이는 문장을 낫날로).

**L-2 기본 전환 결과 (11-23, 미커밋 — 하위 세션. 쓰기 = Tools/uigen · 이 문서 · 승격한 Content/UI/HUD/CombatHUD, C++ · WidgetMcp · Config 변경 없음)**

- **고른 것:** 방향 **D 검은 날**(사용자 — B 별빛은 '너무 우주틱 · 2D 횡스크롤'로 버림), 시안 확정, 고리 약 440 px, 범위 '그림 먼저 · 동작은 다음', 게이지 양끝 칼끝을 속이 찬 강철로(codex 없이 픽셀 — 뾰족한 채움 칸은 엔진의 곧은 채움 끝과 안 맞아 100 %에서 칼끝을 덮는다), '2/4' 를 뼈색 · 띠 안쪽으로(참고판 다시), '오의 불가' 를 밝은 빨강으로(참고판 글자 픽셀 색만). **codex 7/9**(버린 방향 후보 2 + 시안 1 · D 시안 1 · D 편집 1 · 참고판 2).
- **산출물:** 시안 `fixtures/hud_blade_sheet/`(메인 HUD 도 뒤에 여기서 `--cut-from` 으로 오림), 전투 HUD 입력 `fixtures/combat_hud_blade/`(원본 아트 = 시안 픽셀, 참고판, 계약 8 개 그대로 — codegen 해시 같음 · 빌드 없음).
- **바꾼 파일(Tools/uigen):** `make_concept.py` · 새 `gen/concept_route.py` · 새 `gen/territory.py` · `gen/concept_convert.py` · `gen/state_check.py` · `gen/diagnose.py` · `gen/text_ref.py` · `stages/normalize.py` · `stages/layer.py` · `stages/refine.py` · `stages/style.py` · `run_pipeline.py` · `replay_refine.py` · `regress_set.py` · `schemas/inputs.schema.json` · `config/pipeline.yaml`(`halo_de: 2.0` · `state_record_only: []`) · `README.md`, 시험 새 `test_l2_default.py` + 기존 여섯 파일.
- **네 가지 실측:**
  1. **L-2 기본값** — 옵션 없이 부르면 글자 없는 원본 아트 + 참고판, 글자를 그리는 길은 `--with-text`. `--only art | text_ref` 로 나눠 불러 후보를 보고 고른 한 장에만 참고판. 재시도 상한이면 첫 그림을 남긴다.
  2. **OCR 길 고르기** — 글자 있는 그림 0.82 ~ 0.89 ↔ 없는 그림 0 ~ 0.69(문턱 0.78 · 0.70). 예: L-1 전투 HUD 0.892 → L-1, 조작 안내 글자 없는 판 0.66 → L-2(옛 기준 0.7 한 번 검출은 0.72 ~ 0.76 으로 틀림), D 시안의 빈 동그라미 칸 둘 = 한 배율 0.76 이지만 두 배율 같은 자리 점수로 글자 없음. run.log · `report.recorded.concept_route` 에 한 줄.
  3. **`--style-ref`** — 우리 그림 · 사용자가 준 그림만, `work/_probe` 거절, 투명 그림은 어두운 중립 바탕 사본. 참고작 화면은 넣지 않았다.
  4. **숨는 위젯의 빛** — 접히는 위젯을 끈 상태에서 정적 판에 남은 픽셀: L-2 `R20261120_140653` 배너 23,021 → **0** · 체인 패널 19,583 → **0** px(국소 ΔE00 최대 23.1 · 18.1 → 0), L-1 `R20261122_133445` 배너 189 → **0** · 체인 2,695 → **0**(앞은 옛 run 텍스처, 뒤는 새 코드 — L-2 는 replay, L-1 은 replay + 새 에디터 run), 새 컨셉 최종 run 배너 · 체인 · 문장 모두 **0**(엔진 렌더). 검사 `hidden_halo` 는 34 run 의 발견 88(17 run) 을 그림으로 분류해 모두 실제(최저 2.8) · 거짓 양성 0 → 오류.
- **구현 중 드러나 같이 고친 것(원인을 가른 뒤 새 run — 재시도로 통과 얻지 않음):**
  - `text_ref`: 끝이 사라지는 반투명 띠 위 글자를 장식 빛으로 빼 획이 1,731 px 만 남음 → 8,728 px, 없는 안개를 '글자 빛'으로 재 '2/4' 가 흐려짐(획 둘레 2 px 는 참고판 자기 바탕과 다른 것만).
  - `diagnose.spacing_gap`: 자간이 넓은 글자('체인 버스트')의 낱말 틈 때문에 '체인' 이 획 묶음에서 빠져 unmeasured(자간 0 글자는 예전 판정 그대로).
  - **글자 맞춤 마지막 판(`run_pipeline._text_fit_round` · `style.text_fit(resize)`)** — 결함: 크기를 바꾸는 판마다 굵기 판정을 미뤄 L-1 '오의 불가' 가 27 ↔ 29 를 오가며 굵기가 끝내 판정되지 않았고(`R20261123_161929`), 새 컨셉에서는 마지막 판이 **통과하던 배너 라벨 크기까지** 바꿔 깨지면서 판 전체가 버려졌다(`R20261123_170301`). 고침: 마지막 판은 진단이 결함이라고 한 글자만 · 크기 결함인 글자만 크기를 바꾸고(나머지는 지금 크기에서 굵기 판정) · 나아지는 동안 최대 3 번(크기를 고쳐 드러난 굵기는 다음 판 몫). 두 경우 모두 고친 코드의 새 run 에서 되풀이가 실제로 일해 통과(L-1 `text_fit_size_final_2`).
- **run:**

  | run | 결과 | 비고 |
  | :--- | :--- | :--- |
  | `R20261123_150237` · `155229`(새 컨셉) | 실패 | 게이지 100 % 끝 덮임 · '2/4' 굵기 / '체인 버스트' unmeasured — 위 고침의 근거 |
  | `R20261123_160441`(새 컨셉) | 통과 — 오류 0 · 근사 1 | 첫 눈 확인('2/4' 흐림 지적) |
  | `R20261123_163724`(참고판 다시) | 통과 — 오류 0 · 근사 4 | '오의 불가' 어두움(#973D39) |
  | `R20261123_170301`('오의 불가' 색) | 실패 — 오류 1 | 글자 맞춤 마지막 판 결함 |
  | **`R20261123_172628`(새 컨셉 최종 — 승격본)** | **통과 — 오류 0 · 근사 3**(굵기) | 11/11, 접히는 위젯 판 잔여 0, S4 ≤ 0.5, 게이지 0 · 5 · 100 % 트랙 밖 0 · 끝 덮개 차 0, 글자 중심 차 ≤ 1 px |
  | `R20261123_161929`(L-1) | 실패 — 오류 1 | 글자 맞춤 결함(위) — 접히는 위젯 빛 · S4 · 게이지는 깨끗, 자간 보정을 끈 재진단도 같은 값 |
  | **`R20261123_174627`(L-1 최종)** | **통과 — 오류 0 · 근사 3** | 접히는 위젯 빛 0/0, S4 ≤ 1.73 |
- **회귀 [실측]:** 묶음 `l2d_1123`(14 입력, layer 부터) ↔ `s_next_1122` — **`+ new` 0 · 보호 깨짐 0 · 지우기 자리 밖 0 · 예전 판보다 나빠진 글자 0**, 접히는 위젯 빛 replay 8 입력 모두 0. 달라진 것(결함 아님): 단색 둘의 '2/4' 지우기가 lama → harmonic 으로 바뀜(S4 1.8 → 2.9 · 문턱 5 아래, 컨셉 상태 바탕은 좋아짐), L-1 '4.2' 흰 바탕 2.9 → 4.99(문턱 바로 아래 — 에디터 run 은 1.4). 이 묶음은 글자 맞춤을 안 돈다 → 그 고침은 위 에디터 run 둘로 확인. 정답 묶음 **35/35 · 1/1 · 8/8 그대로**. pytest 422 → **443 통과**(실패 0, 31 분 52 초 — 최종 코드 전체).
- **승격:** 옛 L-1 승격본 16 개(커밋 929085f 에 있음)를 사용자 승인 뒤 휴지통 → `promote_widget`(dry_run → confirm) `R20261123_172628_CombatHUD` → `/Game/UI/HUD/CombatHUD/` **7 개**(텍스처 6 + `WBP_CombatHUD`), 부모 `AstralCombatHUDWidget` · 생성 클래스 경로 그대로 · 바깥 의존성은 `F_Pretendard_W` 하나. DebugGame 에디터 1 회(빌드 없음) **`AstralBreak.` 전체 57/57 통과**(413 초, `AstralBreak.Net.CombatHUD.DedicatedPIE` 11.3 초 · `ListenPIE` 11.1 초 포함, 경고는 RecastNavMesh 없음뿐), `quit_editor` 더티 0.
- **남긴 것 · 주의:** '오의 불가' 는 어두운 바탕 대비 1.3 → 2.3 으로 나아졌지만 밝은 바탕은 2.7 → 1.5 로 낮아졌다(테두리 · 그림자 없는 한 색으로는 둘 다 못 만족 — 필요하면 다음 단위에서 옅은 어두운 외곽선). 빈 게이지 100 % 끝 덮개(`concept_end_cap`)는 뾰족한 채움 칸 컨셉에서 실루엣 밖을 불투명하게 그린다 — 이번엔 그림을 고쳐 해당 없음(코드 그대로). 고리 안 띠와 고리 아래 호가 가깝다 — 원형 닦기는 반지름 범위로.
- **다음 단위로 미룬 것(사용자 결정):** 고리가 줄어드는 동작 · 오의 가능 키 안내 글자(둘은 아래 '전투 HUD 동작' 에서 함) · 메인 HUD WBP. 더 있으면 좋은 요소(목록만): 시전 중인 동료 표시 · 체인 참가자 4 칸 표시.
- **돌리지 않은 것:** L-1 게이지 100 % 끝 조각((다) — 하지 않기로 함), 파티 · 조작 안내 · 단색 에디터 run(오프라인 replay 만), `WidgetMcp.` 자동 시험(C++ 변경 없음), 3 · 4 인 체인 HUD · 별도 프로세스.
- **정리(11-23 사용자 승인 — 휴지통, 244 MB):** 실패 · 미완 · 대체된 run 7(`R20261123_145511` · `150237` · `155229` · `160441` · `161929` · `163724` · `170301`)과 그 저장 패키지 2(`160441` · `163724`), `work/_concept_candidates`, 버린 방향 codex 기록 3 + 대체된 참고판 기록 1, `fixtures/combat_hud_astral`, 스크래치. 남김: 승격본 run `172628` · L-1 최종 `174627` · 시안 codex 기록 3(`_concept/20261123_130650` · `140312` · `163125`) · 회귀 `l2d_1123`.
- **사용자 눈 확인 통과(11-23 — 아래 절차, 게임 안 PIE).**
- **눈 확인(사용자):** `work/R20261123_172628_CombatHUD/eye.png`(어두운 · 밝은 바탕 × 전부 켬 / 게임 시작 / 체인 열림) · `compare.png`. 게임 안은 m4-ult-chain.md §6 '사용자 눈 확인' 절차 그대로(`CombatTestMap` PIE 2 인, 오의 쓰기 직전 `SpawnEnemy`) — 볼 것: 시작 때 게이지만 보임(배너 · 고리 · 문장 자국 없음) → 게이지 가득 = 낫날 문장 → 체인 열림 = 고리 + 띠 → 버스트 = 위 배너 → '오의 불가'.

**전투 HUD 동작 설계 — 고리 줄어듦 · 오의 키 안내 (11-23 작성 · 같은 날 사용자 승인. 하위 세션. 파이프라인 몫 — 화면 동작 몫은 m4-ult-chain.md §6 '단위 C 다듬기')**

- **사용자 결정(11-23, 미리보기 그림 2장을 보고 — 전부 추천안):** 고리 = **A2** 12시에서 시계 방향으로 지워짐 + 지나간 자리 18 % 흔적 · 키 글자 = **Enhanced Input 에서 읽음** · 키 모양 = **(가) 글자만 + 어두운 외곽선**(키캡 없음) · **설계 승인 + '오의 불가' 외곽선 2 px 넣기**(쓰기 범위 밖 `GetWindowSeconds()` 한 줄 · 시험 입력 세 개를 검증 화면으로 · codex 0 · 빌드 2 포함).

- **계기:** 위 'L-2 기본 전환 결과'가 미룬 두 동작 — ① 체인 남은 시간 고리가 줄어듦 ② 오의 가능 표시의 키 안내 글자 — 와 ③ '오의 불가' 밝은 바탕 대비. **그림은 다시 그리지 않는다**(시안 `hud_blade_sheet` · 전투 HUD 입력 `combat_hud_blade` 픽셀 그대로). codex 0 회.
- **고리 실측 [승격본 run `R20261123_172628` 의 원본 아트 알파, 캔버스 px]:** 원 하나로 맞는다 — 중심 (954.35, 584.82) · 바깥 반지름 256.1(1,987 점 잔차 중앙 0.38 · p95 1.14 · 최대 1.79). 안쪽 모서리는 원이 아니라 초승달 둘이다 — 두께가 옆(90° · 270°)에서 16 px, 45° 에서 12 px, 위 · 아래 끝에서 0(위아래 거울 자리끼리 ≤ 2 px 로 같다). 먹색 띠는 115 ~ 150° · 205 ~ 240° 에서 고리 안쪽 모서리까지 닿는다(알파 0.1 ~ 0.8).
- **결정 1 — 고리와 띠를 텍스처 둘로 나눈다(픽셀 나눔).** 픽셀마다 주인이 하나다 — 고리 마스크 안이면 고리 텍스처, 밖이면 패널 텍스처. 1:1 로 그리므로 가득 찬 상태의 합성은 지금 텍스처와 **정확히 같은 그림**이다.
  - 왜 한 장 + '반지름 범위로 닦기' 가 아닌가: 안쪽 모서리가 각도마다 239 ~ 254 px 로 달라 반지름 하나로는 못 가른다 [실측 — r 238.5 로 닦으면 띠 837 px 이 잘리고, 240 이면 띠 499 px 이 잘리며 고리 471 px 이 남는다]. 또 바인딩은 위젯 하나에 하나라(`ChainPanel` 은 flag) 고리 위젯은 어차피 따로 있어야 한다.
  - 나누는 법(새 `gen/radial.py`, 결정적 — LLM · codex 없음): 바깥 윤곽에 최소제곱 원 → 각도(1°)마다 안쪽 모서리(바깥에서 안으로 처음 끊기는 곳)를 재고, 띠처럼 다른 요소가 닿아 안으로 번진 각도는 거울 자리 넷(θ · −θ · 180° ± θ)의 두 번째로 큰 값으로 바꾼다(번짐은 언제나 안쪽으로만 틀린다) → 1.5 px 안쪽으로 여유. 못 재면(원 잔차 p95 > 2 px · 안쪽 모서리를 각도의 80 % 이상에서 못 찾음) `RADIAL_MEASURE` 로 멈춘다 — 조용한 물러남 없음.
  - 자리: `stages/analyze` 가 게이지 채움과 같은 자리에서 재(`derive_radial_fills`) 고리 위젯 상자를 원 상자(바깥 반지름 + 2 px, 정수)로 맞추고 슬롯 여백을 고친다. `stages/layer` 가 마스크 `layer/ring_<id>.png` 와 기록(`layer.json radials`)을 남긴다. `stages/refine._cut_entry` 는 고리 에셋이면 마스크 안만, 같은 자리를 품은 다른 에셋이면 마스크 밖만 남긴다(접히는 위젯의 자기 마스크와 같은 길 — 메우기 뒤에도 투명).
- **결정 2 — 원형 닦기 머티리얼(WidgetMcp 새 `Core/WidgetMcpBrushMaterials`).** `WidgetMcpTextMaterials` 와 같은 방식 — run 폴더에 부모 `M_RadialWipe` 하나 + 위젯마다 `MI_RadialWipe_<위젯>`(저장 · 폐기 · 승격이 같이 간다).
  - UI 도메인 · 반투명. 색 = 텍스처 rgb × 정점 색, 불투명도 = 텍스처 알파 × 정점 알파 × 닦기. 닦기 = 중심에서 본 각도와 남은 비율 `Percent` 로 계산한 부호 거리(px)를 ± 0.5 px 로 부드럽게 — 끝이 계단지지 않는다. `Percent` ≥ 1 은 전부 1(12시 이음매 없음), ≤ 0 은 전부 흔적 값. 파라미터: `Texture` · `Percent` · `Center`(px) · `Size`(px) · `Mode`(0 = 시계 방향 한 바퀴 · 1 = 좌우 거울) · `TrackAlpha`(지나간 자리에 남기는 옅은 흔적).
  - Slate 머티리얼 셰이더는 정점 색을 곱하지 않고(`SlateElementPixelShader.usf:198-206` — 색 = Emissive, 불투명도 = Opacity [소스]) 뒤에 같은 감마 처리를 거친다 → 정점 색은 머티리얼 안에서 곱한다. 이미지 브러시와 색이 같은지는 '100 % 렌더 = 컨셉' 진단이 잰다.
- **결정 3 — 계약: `progress` 가 `Image` 도 받는다.**
  - spec: `Image` 의 `style.percent`(미리보기 비율) + `style.brush.wipe{kind: "radial", mode, center, track_alpha}`. `progress` 바인딩인 Image 에 `wipe` 가 없으면 의미 검사 오류. 정규화 · 역추출(MIC → wipe) · 왕복 비교 · `render_widget` 의 `percent` 덮어쓰기(Image 면 동적 머티리얼에) · 텍스처 목록(`CollectTextures` 가 MIC 의 텍스처도) · 오프라인 합성(`gen/backdrop` 이 같은 식으로 닦음)을 같이 고친다.
  - codegen: `progress` + `Image` → `GetDynamicMaterial()->SetScalarParameterValue("Percent", 0 ~ 1)`. setter 조각이 바뀌어 생성기 식별자(계약 해시)가 바뀐다 — 생성 C++ 를 쓰는 화면은 `CombatHUD` 하나뿐이다.
  - 입력(`inputs.yaml data`): 새 항목 `inside: <위젯 id>`(그 위젯 아래에 있어야 함 — 같이 접힌다, analyze 가 어기면 1회 재요청)와 `radial: {mode, track_alpha}`.
- **결정 4 — 오의 가능 표시 = 상자 + 그림 + 글자.** `ult_ready`(flag)를 `UltReadyGlow`(Image) 대신 새 `UltReadyPanel`(Overlay)에 바인딩하고, 그 아래에 낫날 그림 `UltReadyGlow` 와 새 `UltKeyText`(TextBlock, `ult_key` text)를 둔다.
  - flag 하나가 그림과 글자를 같이 접으므로 '글자는 게이지가 가득할 때만' 이 구조로 선다(보이기 코드를 따로 쓰지 않는다 — 원천 하나). setter 이름은 data id 로 정해져 `SetUltReadyVisible` 그대로다(스텁의 부르는 곳 무변경).
  - 버린 안: ① `UltReadyGlow` 의 타입을 바꿈 — 바인딩 위젯은 타입을 안 바꾼다(`BINDING_RETYPE`) ② 글자에 flag 를 하나 더 — 같은 상태의 원천이 둘이 된다.
  - `UltReadyGlow` 는 계약에서 선택(`BindWidgetOptional`, setter 없음)으로 내려간다(§3-3 규칙 2). 새 바인딩(`ChainRing` · `UltReadyPanel` · `UltKeyText`)은 필수라 **옛 WBP(지금 승격본 · 지난 run)는 새 C++ 로 빌드한 뒤 다시 승격할 때까지 컴파일 오류**다 — 빌드와 승격을 한 번에 이어서 한다.
  - 레이어: 접히는 영역의 그림이 영역을 꽉 채워야 빛을 옮길 수 있다(`layer._carrier`) → 영역에 오리는 그림이 하나뿐이고 꽉 차지 않으면 그 그림 상자를 영역까지 넓힌다(투명한 자리 — 픽셀 그대로).
  - 글자 정답: 참고판 `concept_text_ref.png` 에 'R' 글자 픽셀만 스크립트로 더한다(Pretendard · 뼈색, `concept_text_ref.json` lineage — '오의 불가' 색 보정과 같은 방식). 원본 아트는 안 건드린다.
- **결정 5 — 요청이 정한 글자 외곽선.** `inputs.yaml` 의 `data` · `static_text` 항목에 `outline{size, color}` → `apply_contract` 가 넣고, 컨셉에서 재는 외곽선 맞춤(`style._fit_outline`) · LLM 외곽선 걷기 · 스타일 op 이 못 건드린다(요청이 정한 값). 검정 바탕 비교에서는 어두운 외곽선이 안 보여 진단의 크기 · 굵기 판정에 영향이 없다 — 대신 밝은 바탕 합성으로 대비를 기록한다.
- **결정 6 — 자동 진단이 0 · 중간 · 100 % 를 보는 법(`gen/state_check.radial_states`, 오류 E8).** 엔진 렌더를 비율마다 한 장(`state_<위젯>_000 · 015 · 040 · 065 · 090 · 100`), 컨셉 상태 렌더와 견준다. (구현 때 바꿈: 처음 안 25 · 50 · 75 % 는 닦는 끝이 90° 배수에 놓여 중심이 8 px 어긋나도 안 잡혔다 [시험] → 끝이 네 사분면의 빗각 306 · 216 · 126 · 36° 에 오는 비율로.)

  | 검사 | 무엇을 | 어디서 |
  | :--- | :--- | :--- |
  | `radial_full` | 100 % = 컨셉 상태(차 ≤ `local_de`) | 고리 마스크 |
  | `radial_zero` | 0 % = 고리 위젯을 뺀 합성 + 흔적 값 | 고리 마스크 |
  | `radial_arc` | 15 · 40 · 65 · 90 %: 남아야 할 쪽 = 100 % 렌더, 닦여야 할 쪽 = 0 % 렌더 | 고리 마스크(끝 ± 2 px · 글자 뺌) |
  | `radial_outside` | 모든 비율에서 고리 마스크 밖(띠 · 글자 · 나머지 화면)이 그대로 | 마스크 밖 전부 |

  `radial_outside` 가 '고리가 닦일 때 띠가 잘리나' 를, `radial_arc` 가 '각도 · 방향 · 중심이 맞나' 를 잡는다. compare.png 상태 띠에 고리 다섯 칸을 더한다. 새 검사이므로 먼저 일부러 틀린 값(중심 8 px 어긋남 · 띠까지 품은 마스크 · 방향 반대)으로 잡히는지 시험에서 본다.
- **결정 7 — 시험 입력이 실제 화면의 C++ 를 되돌리지 않게.** 시험용 `m4_combat_hud_concept` · `_flat` · `_l2` 의 `screen_id` 가 `CombatHUD` 라, 옛 계약 8 개로 run 을 돌리면 새 바인딩이 선택으로 내려가고 `SetUltReadyVisible` 이 옛 위젯으로 되돌아간다(재빌드까지 한다). → `screens.yaml` 에 검증 화면 `ProbeCombatHUD`(probe — C++ 없음)를 더하고 세 입력의 `screen_id` 를 바꾼다. L-1 확인 run 은 이 화면으로 돈다.
- **쓰기 범위:** `Tools/uigen/**` · `Plugins/WidgetMcp/**` · `Source/AstralBreak/UI/HUD/**`(생성 베이스는 codegen) · `Source/AstralBreakEditor` 의 HUD PIE 시험 · **`Source/AstralBreak/GameModes/AstralChainBurstComponent.h` 에 `GetWindowSeconds()` 한 줄**(브리프의 범위 밖 — 값을 밖에서 읽을 길이 없다) · 승격 때 `Content/UI/HUD/**` · 두 설계 문서. 앞 단위(미커밋)의 파일 위에 이어서 고친다 — 덮거나 되돌리지 않는다. L-1 글자 지우기 코드는 안 고친다.
- **검증:** pytest(새 시험 포함 전체 1 회) · 정답 묶음 · 오프라인 회귀 새 라벨(`ring_1123`) ↔ `l2d_1123`(`+ new` 0 · 보호 깨짐 0) · 새 전투 HUD run 무인 통과(오류 0) · L-1 확인 run 1 회 · 빌드 2(DebugGame · Development) · 에디터 1 회에 `AstralBreak.` 1 회 + `WidgetMcp.` 1 회. 재시도로 통과를 얻지 않는다.

**전투 HUD 동작 결과 (11-23 ~ 24, 미커밋 — 하위 세션. 위 설계 그대로, 다른 곳은 아래 '설계와 달라진 것')**

- **한 일:** 체인 고리가 남은 시간만큼 12시에서 시계 방향으로 지워지고(흔적 18 %) 숫자와 같이 멈춘다 · 오의 가능 표시에 키 글자(게이지가 가득할 때만) · '오의 불가' 와 키 글자에 어두운 외곽선 2 px. 그림은 다시 그리지 않았다 — **codex 0 회**, analyze 호출 run 마다 1 회.
- **산출물:** 승격본 run **`R20261123_194019_CombatHUD`** → `/Game/UI/HUD/CombatHUD/` 10 개(`M_RadialWipe` · `MI_RadialWipe_ChainRing` · 텍스처 7 · `WBP_CombatHUD`). 계약 해시 `sha1:2ee29ce6627da37b994b13b4e1e304a3e864968d`(앞 `5ae0d80a…`) — 바인딩 10 + 선택 1.
- **바꾼 파일:** Tools/uigen — 새 `gen/radial.py` · 새 `tests/test_hud_motion.py`(20), `core/{spec,cppgen}` · `stages/{normalize,analyze,layer,refine,style,fix}` · `gen/{backdrop,state_check,diagnose}` · `run_pipeline.py` · `schemas/{spec,inputs,brief}` · `config/screens.yaml`(`ProbeCombatHUD`) · `fixtures/combat_hud_blade`(`inputs.yaml` · 참고판 'R' 픽셀 · lineage) · 시험 입력 셋의 `screen_id` · `tests/test_analyze.py` · README. WidgetMcp — 새 `Core/WidgetMcpBrushMaterials.h/.cpp`, `Core/{WidgetMcpSpec,WidgetMcpBlueprint,WidgetMcpRender}`, 시험 `WidgetMcp.Tools.RadialWipe`. 게임 쪽은 m4-ult-chain.md §6.
- **고리 나누기 [실측]:** 중심 (954.52, 584.99) · 반지름 256.07 · 바깥 윤곽 2,046 점 잔차 중앙 0.36 · p95 1.04 · 최대 1.66 px(문턱 2), 두께 2.5 ~ 18.5 px(여유 포함), 띠가 닿아 거울 자리로 바꾼 각도 43°, 마스크 26,956 px(보이는 22,261 px).
- **run `R20261123_194019`:** 무인 통과 **11/11 · 오류 0 · 근사 3**(굵기 — 배너 라벨 · 배너 숫자 · '체인', 쓸 수 있는 굵기 중 가장 가까움), 시도 7(첫 빌드 → LLM 정정 1 → 글자 크기 판은 되돌림 → 키 글자만 크기 → 위치 → 마지막 크기 판). 엔진 렌더 고리 검사: `radial_full` 0.0 · `radial_zero` 1.18(문턱 안) · `radial_arc` 15 · 40 · 65 · 90 % 모두 0.0 · `radial_outside` 0 ~ 90 % 다섯 비율 모두 0.0 — 결함 0. `radial_full` 의 기준은 컨셉 상태 렌더(표본 비율 1.0)이고, 컨셉 그림과의 차는 외형 진단이 본다(오류 0).
- **'오의 불가' 대비(WCAG, 글자색 `#D55C56`):** 외곽선이 없을 때 글자 ↔ 바탕은 흰 3.8 · 밝은 모래 2.5 · **중간 회색 1.03** · 검정 5.5 로 바탕에 따라 사라진다. 외곽선(`#0C0C0E` 86 % · 2 px)이 글자를 두르면 글자 ↔ 외곽선이 흰 3.6 · 모래 3.9 · 회색 4.5 · 검정 5.2 — 어느 바탕에서도 3.5 이상. 앞 절의 2.3 / 1.5 는 다른 바탕으로 잰 값이라 직접 견주지 않는다.
- **L-1 확인 run `R20261123_234540_ProbeCombatHUD`:** 무인 통과 **11/11 · 오류 0 · 근사 2**(UltBlockedText 빛 · 게이지 끝 빛), 시도 4, 글자 지우기 5/5, 접히는 위젯 빛 판 잔여 0 · 0 px, 검증 화면이라 C++ 를 안 건드림(codegen skipped). 앞 L-1 최종 `174627` 은 오류 0 · 근사 3.
- **회귀:** 오프라인 묶음 `ring_1123`(14 입력, layer 부터) ↔ `l2d_1123` — **14/14 오류 · 근사 수 같음, `+ new` 0**(보호 run 의 E8 은 옛 텍스처를 새 상태 검사로 본 값이라 기준선에도 그대로). 정답 묶음 **35/35 · 1/1 · 8/8**. pytest 443 → **463 통과**(실패 0 · 경고 2, 28 분 57 초). 빌드 DebugGame · Development `Result: Succeeded`.
- **승격:** 옛 승격본 7 개(run `R20261123_172628`)를 사용자 승인 뒤 휴지통 → `promote_widget` dry_run(10 개 · 바깥 의존성 `F_Pretendard_W` 와 엔진 `DefaultTexture` 둘) → confirm, WBP 컴파일 정상. 같은 에디터 1 회에 `AstralBreak.` **57/57**(414 초) · `WidgetMcp.` **8/8**.
- **사용자 눈 확인: 통과(11-23, 답 '눈 확인 통과' — m4-ult-chain.md §6 결과 절의 네 가지).**
- **설계와 달라진 것:** ① 중간 비율 25 · 50 · 75 → 15 · 40 · 65 · 90 %(결정 6 에 적음 — 90° 배수 끝은 중심이 8 px 어긋나도 안 잡힘) ② 결정 1 의 '합성이 **정확히 같은** 그림' 은 아니다 — 텍스처 둘로 나눈 반투명 경계의 8 비트 반올림 · 옅은 잡티 때문에 컨셉 대비 최대 4.2/255(검정 바탕)가 남는다. 컨셉 외형 진단에서는 오류 0 이다.
- **구현 중 고친 것:** 요청 외곽선을 지키는 `outline_locked` 를 값이 있을 때만 넘김(가짜 `text_fit` 을 쓰는 기존 시험 4 개가 깨졌다) · 일부러 틀린 색 시험의 값이 너무 약해 강하게 함.
- **돌리지 않은 것:** 파티 · 조작 안내 · 단색 에디터 run(오프라인만), 좌우 거울 모드(`mode: mirror`)의 엔진 렌더(파이썬 단위 시험만 — 어느 화면도 쓰지 않는다), 게임패드 키 글자 · 장치 바꿈의 자동 시험, 3 · 4 인 체인 · 별도 프로세스.
- **남긴 것 · 주의:** ① 옛 계약의 저장본(`Content/_AutoGen/` 의 지난 `*_CombatHUD` run, 앞 승격본 `172628` 포함)은 새 C++ 에서 열면 필수 바인딩 누락으로 컴파일 오류다(git 무시 폴더 — 안 열면 영향 없음). ② 옛 손 spec `fixtures/m4_combat_hud`(1a, `--spec-dir`)도 `screen_id: CombatHUD` 라 실제로 돌리면 HUD 계약을 되돌린다 — 시험(임시 폴더)이 쓰는 입력이라 안 건드렸다. ③ 원형 닦기 텍스처는 1:1 로만 그린다(늘리면 끝 선 ± 0.5 px 가 같이 늘어난다). ④ 한 화면에 고리가 여럿이어도 되지만, 고리끼리 겹치는 컨셉은 시험하지 않았다.
- **정리(11-24 사용자 승인 — 휴지통, 약 11 MB):** 스크래치 `uigen_ring` · `work/_widgetmcp_tests` · `work/_regress/compare_l2d_1123_vs_ring_1123`. 남김: 승격본 run `194019` · L-1 확인 `234540` · 회귀 `ring_1123` · 옛 승격본 저장본 `172628`.
- **눈 확인(사용자) 자료:** `work/R20261123_194019_CombatHUD/compare.png`(상태 띠에 고리 칸).

**메인 HUD 설계 — 내 상태 · 동료 화면 `StatusHUD` (11-24 작성 · 같은 날 사용자 승인. 하위 세션)**

- **사용자 결정(11-24, 미리보기 3장을 보고):** 범위 = 내 상태 + 동료 3(추천안) · 화면 이름 = StatusHUD 따로(추천안) · 빈 자리 = **B 먹색 + 곧은 끝** · 표식 = 초승달 안(추천안). 그래서 결정 6 의 `end: tip` 은 만들지 않는다(막대는 모두 곧은 끝 — 엔진 Mask 하나).
- **진행(11-24, 세션 인계):** 파이프라인 모양 막대 · 글꼴로 그린 참고판 · 입력 `fixtures/status_hud_blade` · 게임 연결 C++ · 시험을 썼다(`test_shaped_bar.py` 18 통과, DebugGame 빌드 성공, C++ 시험은 아직 안 돌림). 마지막 run `R20261124_120141_StatusHUD` = 구조 10/11 · **오류 1**('표식' 작은 글자 굵기 하나) — 막대 8개는 엔진 렌더에서 100 % = 컨셉 · 중간 비율 · 막대 밖 차 0. 참고판 글자 크기를 정수 pt 로 고쳐 다시 그렸고 그 run 은 아직이다. 남은 일 = 무인 통과 run → 눈 확인 → 승격 → 빌드 · 시험 · 회귀 → 결과 절. → **이어받은 세션이 끝냄: 아래 '메인 HUD 결과'.**

- **계기(사용자 11-24):** 다음 UI 작업 = 메인 HUD. 시안 `fixtures/hud_blade_sheet` 의 칸(내 상태 · 파티 / 보스 / 목표 / 아이템 / 스킬) 가운데 **게임에 값이 있는 것만** 만든다. 원칙 — 시스템이 없는 칸을 가짜 값으로 채우지 않는다.
- **값의 원천 조사 [소스]:**

  | 시안 칸 | 값 | 원천 | 남이 보나(복제) | 바뀜 통지 | 판정 |
  | :--- | :--- | :--- | :--- | :--- | :--- |
  | 내 상태 | HP | `UAstralHealthSet` `Health`/`MaxHealth`(PlayerState 의 ASC) | 전원(`COND_None`) | 속성 값 변화 델리게이트 | **지금 가능** |
  | 내 상태 | 스태미나 | `UAstralHeroResourceSet` `Stamina`/`MaxStamina`(AbilitySet 이 줌 — 허브 폰에는 없음) | 전원 | 같음 | **지금 가능** |
  | 내 상태 | 표식 | 같은 세트 `MarkStack`/`MaxMarkStack`(기본 5) — 강화 공격이 씀 | 전원 | 같음 | **지금 가능**(시안에 자리 없음) |
  | 내 상태 | 오의 게이지 | 같은 세트 | 전원 | 같음 | 전투 HUD 에 있음 |
  | 파티 | 동료 HP · 오의 게이지 | 동료 PlayerState 의 ASC(PlayerState 는 거리와 상관없이 복제) | 전원 | 같음 | **지금 가능** |
  | 파티 | 누가 있나 | `GameState.PlayerArray` | 전원 | **없음** — `AddPlayerState` · `RemovePlayerState` 가 가상 함수일 뿐 | 통지 하나 더하면 가능 |
  | 파티 | 이름 | `APlayerState::GetPlayerName()` | 전원 | `OnRep_PlayerName`(가상) | 가능 — 이름 정하는 곳이 없어 접속 이름 그대로(PIE 는 기기 이름 꼴) |
  | 내 상태 · 파티 | 초상화 | 없음 — `UAstralCharacterDefinition` 은 메시 · AnimBP 뿐 | — | — | 원천 없음(초승달은 장식으로만) |
  | 보스 | HP · 모드 · Break | 보스 클래스 · 상태 없음(적은 `BP_Enemy_Melee` · `_Guardian` · 더미) | — | — | 원천 없음 → **M5** |
  | 목표 | 지금 목표 | 없음(`AAstralRaidGameState` 는 체인뿐) | — | — | 원천 없음 → **M6** |
  | 아이템 | 회복 아이템 2종 | 없음 | — | — | 원천 없음 → **M7** |
  | 스킬 4칸 | 로드아웃 · 쿨다운 · 아이콘 | 로드아웃 4칸 없음, 쿨다운 GE 0 개, 아이콘 0 개. 스킬성 어빌리티는 강화 공격 하나 | — | — | 원천 없음 → **M7**(game-plan 부록 E 1번 — 스킬 만드는 마일스톤도 없음) |

- **결정 1 — 범위(추천): 내 상태 + 동료 3.** 나머지 네 칸은 원천이 생기는 마일스톤에서 같은 시안을 오려 만든다. 버린 안 — ① 보스 · 목표 칸을 늘 접힌 채 미리 만들기: 계약만 있고 시험할 값이 없으며, M5 에서 모드 · Break 게이지 요구가 정해지면 다시 만든다 ② 스킬 한 칸(강화 공격)만: 시안의 네 칸 중 하나만 살아 빈 칸 셋이 '가짜 칸'이 된다 ③ 보스 바를 락온 대상 HP 로 대신: 시안의 보스 칸과 뜻이 다르다(원하면 따로 '대상 HP' 화면).
- **결정 2 — 화면을 나눈다(추천): `StatusHUD`.** 전투 HUD 와 합치지 않고, '메인 HUD' 한 화면으로도 묶지 않는다. 원천이 생기는 때가 다르므로(지금 · M5 · M6 · M7) 화면도 따로 둔다 — 한 화면이면 칸을 더할 때마다 이미 눈 확인이 끝난 칸까지 analyze(LLM)부터 다시 돌아 그림이 흔들리고 계약 · 승격본이 통째로 바뀐다. `screen_id: StatusHUD` · `UAstralStatusHUDViewBase`(생성) · `UAstralStatusHUDWidget`(스텁) · `WBP_StatusHUD` · `/Game/UI/HUD/StatusHUD/`. 이름은 나중에 안 바꾼다(§3-3). 버린 안 — `MainHUD` 하나로 키워 가기(위 이유) · `PartyHUD`(검증 화면 `ProbePartyHUD` 와 헷갈림).
- **결정 3 — 시안에서 오릴 곳(codex 0):** `--cut-from fixtures/hud_blade_sheet/concept.png --keep 40,40,512,130 --keep 40,175,360,215`(1920 기준 — 내 상태 · 동료 세 줄. 전투 HUD 가 오린 자리 · 보스 칸과 안 겹친다). 동료 세 줄의 그림은 조금씩 다른 픽셀이라 줄마다 자기 텍스처.
- **결정 4 — 반복(동료 3)은 고정 세 줄.** Phase 1 에 list · 하위 WBP 가 없다(Phase 3 몫) → `Ally1` · `Ally2` · `Ally3` 을 따로 바인딩하고 스텁이 번호로 돈다. 줄마다 flag 하나로 접히고(동료가 없으면), 위에서부터 채워 가운데가 비지 않는다. 버린 안 — 줄 하나짜리 WBP 를 만들어 C++ 이 세 번 붙이기: 자리 · 간격이 시안 픽셀이 아니라 코드에 들어가고 진단이 못 본다.
- **결정 5 — 데이터 계약(바인딩 16):**

  | data | 종류 · 위젯 | 뜻 |
  | :--- | :--- | :--- |
  | `self_hp` | progress · `SelfHpBar`(ProgressBar) | 내 HP 비율 |
  | `self_hp_value` | number `0` · `SelfHpText` | 내 HP 숫자(시안에 없는 글자 — 막대 왼쪽 위) |
  | `self_stamina` | progress · `SelfStaminaBar` | 스태미나 비율 |
  | `self_mark` | number `0` · `SelfMarkText` | 표식 수(+ 고정 글자 '표식' `SelfMarkLabel`) — 결정 7 |
  | `ally1 ~ 3_panel` | flag · `Ally<n>Panel`(Overlay) | 그 줄 전체 |
  | `ally1 ~ 3_name` | text · `Ally<n>NameText` | 이름 |
  | `ally1 ~ 3_hp` | progress · `Ally<n>HpBar` | HP 비율 |
  | `ally1 ~ 3_ult` | progress · `Ally<n>UltBar` | **오의 게이지** 비율(얇은 막대) |

  동료의 얇은 막대를 스태미나가 아니라 오의 게이지로 쓰는 까닭 — 남의 스태미나는 쓸모가 없고, 체인을 이으려면 '누가 오의가 찼나'를 봐야 한다(M4). 모든 글자는 요청 외곽선 2 px(`#0C0C0EDC` — 전투 HUD 와 같음).
- **결정 6 — '모양 막대'(파이프라인 새 어휘).** [실측] 시안의 HP 막대는 **빈 자리 그림이 없는 가득 찬 칼날**(내 것 386 × 18 px)이고, 얇은 막대는 채움 58 % + 검은 빈 자리(299 × 14 px)다. 지금 길로는 ① 가득 찬 막대 = L-2 의 알려진 한계('원본 아트에 빈 트랙 정답이 없어 채움이 판에 남는다') ② 얇은 막대 = `concept_fill` 이 찾는 밝은 프레임 선이 없어 `gradient_bar` 로 물러나고 자리를 LLM 상자에 기댄다(높이 4 ~ 6 px 라 1 px 만 틀려도 보인다). 또 동료 줄의 두 막대는 사이 알파가 0.4 ~ 0.9 로 이어져 있다.
  - 새 입력 `bar: {track: "#404144CC", end: tip | straight}`(progress + ProgressBar 에만). 막대 하나 = 텍스처 한 장(컨셉 픽셀 그대로, 픽셀마다 주인 하나 — 고리와 같은 틀), 채움 브러시 = 그 텍스처, 빈 자리 = **같은 텍스처를 `track` 색으로 물들인 배경 브러시**. 엔진 `UProgressBar` 의 기본 기능만 쓴다(`straight` = Mask 자르기, `tip` = Scale + 끝 여백 고정 — 오의 게이지가 쓰는 길) → **WidgetMcp C++ · 머티리얼 변경 없음**.
  - 재는 법(새 `gen/silhouette.py`, 결정적): LLM 상자 둘레의 알파 > 0.25 덩어리 → 두 막대가 이어져 있으면 그 사이 알파가 가장 낮은 줄에서 가름 → 4 px 안 옅은 가장자리까지 자기 마스크 → 상자 · 슬롯 여백 · 에셋을 잰 값으로. 못 재면 `BAR_MEASURE` 로 멈춤(조용한 물러남 없음). layer · refine 은 고리 마스크 자리(`layer.json`)에 같이 싣고, 접히는 줄의 빛 주인(`_carrier`)에서 막대 에셋은 뺀다. 막대의 자리 · 모양은 fix · 외형 라운드가 못 건드린다(고리와 같음).
  - 얇은 막대 넷은 원본 아트를 **픽셀로 한 번 보정**한다(codex 없음): 왼쪽 절반(채워진 쪽)을 거울로 오른쪽에 — 가득 찬 막대가 되고 나머지는 막대 하나의 규칙이 맡는다. `concept.json lineage` 에 기록(오의 게이지 칼끝 보정과 같은 방식). 게임에서는 비율만큼만 칠해지고 나머지는 먹색이라 시안과 같은 모양이다.
  - 상태 검사: 지금의 게이지 검사(0 · 0.05 · 1.0 — 트랙 밖 · 끝 · 0 % 잔여)를 막대 모양 자리로 좁혀 쓰고, 새 `bar_cut`(E8) — 15 · 40 · 65 · 90 % 에서 남아야 할 쪽 = 100 % 그림, 빈 쪽 = 0 % 그림, 막대 밖은 그대로. 먼저 일부러 틀린 값(방향 반대 · 물들임 없음 · 이웃 막대 침범)으로 잡히는지 시험에서 본다. `compare.png` 상태 띠에 막대 칸.
  - 버린 안 — ① 고리처럼 Image + 닦기 머티리얼(선형): 머티리얼 · 정규화 · 역추출 · 셋터까지 WidgetMcp C++ 를 다시 고치는데 얻는 것이 없다(ProgressBar 로 됨) ② 시안을 codex 로 다시 그려 빈 트랙 받기: 승인한 픽셀이 바뀐다 ③ 얇은 막대만 지금 길: 막대 규칙이 둘이 된다.
  - 빈 자리 표현은 사용자가 고른다 — 미리보기 A(흔적 18 % — 밝은 바탕에서 안 보임) · B(먹색 · 곧은 끝) · **C(먹색 · HP 는 칼끝이 따라 짧아짐 — 추천)**. 얇은 막대는 어느 쪽이든 곧은 끝.
- **결정 7 — 표식(추천: 내 초승달 안 숫자).** 시안에 자리가 없지만 원천이 있고 강화 공격을 쓸 수 있는지는 이 값으로만 안다. 초상화 자리로 그린 초승달은 초상화 원천이 없어 비어 있다. 값 · 이름은 잠정(기획 요소) — 없어지면 바인딩을 선택으로 내린다.
- **결정 8 — 글자 참고판도 codex 없이.** `make_concept.py --only text_ref --draw <fixture>/text_ref_layout.yaml` — 글자마다 자리 · 크기 · 굵기 · 색을 적으면 **엔진과 같은 글꼴 파일**(Pretendard TTF)로 원본 아트 위에 그린다. 글자 상자는 OCR 대신 그린 자리를 쓴다(작은 글자는 OCR 이 놓친다). 앞 화면은 codex 2회 + 픽셀 보정 2회가 들었다. 버린 안 — codex 편집 1회.
- **결정 9 — 게임 연결(폴링 없음).** 나와 동료를 같은 틀로: 칸 4 = PlayerState 하나씩.
  - 명단: `AAstralGameState` 에 `OnPlayerRosterChanged`(C++ 델리게이트) — `AddPlayerState` · `RemovePlayerState` 재정의에서 방송. 클라이언트에서는 그 시점에 번호 · 이름이 아직 없으므로 `AAstralPlayerState` 가 `OnRep_PlayerId` · `OnRep_PlayerName` · `OnRep_bIsInactive` · `ClientInitialize`(이 PlayerState 가 내 것이 됨)에서 같은 통지를 부른다. 위젯은 통지마다 명단을 다시 뽑는다 — 나 = `PC->PlayerState`, 동료 = 봇 · 관전자 · 비활성 뺀 나머지를 PlayerId 순 최대 3(규칙은 `AstralPartyStatics` 순수 함수 — 방장 고르기와 같은 자리, 월드 없이 시험).
  - 값: 칸마다 그 PlayerState 의 ASC 속성 변화 델리게이트(HP · 최대 HP · 오의 · 최대 오의, 나는 + 스태미나 · 최대 · 표식). 늦게 오는 속성 세트는 `OnPawnSet` → 그 폰의 `PawnExtension::OnAbilitySystemInitialized_RegisterAndCall` 에서 다시 읽는다. 비율은 매번 ASC 의 지금 값 둘로(최대치가 기본값이면 통지가 없다 — C 단위 교훈).
  - 화면 전체는 **레이드 GameState 가 있는 맵에서만** 보인다(허브 폰에는 전투 자원이 없다). 만드는 자리 = 전투 HUD 와 같은 `BeginPlayingState`(z 0) — 위젯 만들기 · 옛 월드 것 버리기를 컨트롤러의 함수 하나로 묶어 두 HUD 가 같이 쓴다(클래스 프로퍼티 `StatusHUDWidgetClass` 하나 추가).
  - 버린 안 — 틱마다 `PlayerArray` 훑기(폴링) · 전투 HUD 의 폰 감시 코드를 베끼기(내 상태도 PlayerState 로 보면 필요 없다) · 폰의 `HealthComponent::OnHealthChanged`(동료 폰이 멀면 없다).
- **겹치는 자리:** 전투 HUD 와 없음(시안 자리가 다르다). 디버그 위젯(z 100)이 왼쪽 위를 덮는다 → 콘솔 명령 `ToggleDebugWidget` 하나를 더한다(기본 켜짐 그대로 — 지금 쓰는 방식을 안 바꿈).
- **시험:** pytest — 막대 재기(이어진 두 막대 · 틀린 상자 오류) · 픽셀 주인 하나 · `bar_cut` 일부러 틀린 셋 · 그린 글자 참고판 · 계약 16 codegen · 스키마 오류. C++ — `AstralBreak.Party.Allies`(명단 순수 함수), 멀티 PIE 2인 `AstralBreak.Net.StatusHUD.ListenPIE` · `.DedicatedPIE`: 두 자리에 HUD · 내 값 = 자기 자리 속성 / 동료 줄 1 에 상대 이름 · 값, 줄 2 · 3 접힘 / 서버가 A 에게 피해 → A 의 내 HP 와 B 의 동료 HP 가 같은 비율 / `FillUlt` → 상대 자리 동료 오의 1.0 / 스태미나 · 표식 변화 / 명단에서 빠지면 줄이 접힘. → `AstralBreak.` 60.
- **쓰기 범위:** `Tools/uigen/**` · `Source/AstralBreak/UI/HUD/**` · `GameModes/AstralGameState.*` · `AstralPartyStatics.*` · `Player/AstralPlayerState.*` · `Player/AstralPlayerController.*` · `AstralBreak/Tests` · `AstralBreakEditor` 의 새 PIE 시험 · 승격 때 `Content/UI/HUD/StatusHUD/` · 이 문서. WidgetMcp · 전투 HUD 파일 · M4 단위 D 파일은 안 건드린다.
- **검증:** pytest 전체 1회 · 정답 묶음 · 오프라인 회귀 새 라벨 ↔ `ring_1123`(`+ new` 0 — 공용 코드를 고치므로) · 새 run 무인 통과(오류 0 · `compare.png` 직접 봄) · 빌드 2 · 에디터 1회에 `AstralBreak.` 1회. `WidgetMcp.` 는 C++ 를 안 고치면 안 돌린다. 비용 = codex 0 · run 마다 analyze LLM 1회 + 정정.

**메인 HUD 결과 — `StatusHUD` (11-24, 커밋 `2c850de` — 하위 세션. 위 설계 그대로, 다른 곳은 아래 '설계와 달라진 것')**

- **한 일:** 내 상태(HP 칼날 막대 · HP 숫자 · 스태미나 얇은 막대 · 초승달 안 표식 수)와 동료 세 줄(이름 · HP · 오의 게이지)이 게임 값에 이어졌다. codex **0 회**, run 마다 analyze 호출 1 회.
- **산출물:** 승격본 run **`R20261124_130129_StatusHUD`** → `/Game/UI/HUD/StatusHUD/` 13 개(텍스처 12 + `WBP_StatusHUD`), 부모 `AstralStatusHUDWidget` · 컴파일 상태 3 · 바깥 의존성 `F_Pretendard_W` 하나. 계약 해시 `sha1:82d77227b6d6…` — 바인딩 16.
- **run 기록:**

  | run | 결과 |
  | :--- | :--- |
  | `R20261124_114205` · `114339` · `114802` | analyze 확인 / 모듈 경로를 잘못 준 run / verify 487 초 — 중단 |
  | `R20261124_120141` | 10/11 · 오류 1('표식' 굵기 E9) — 참고판 글자 크기가 정수 pt 가 아니었다 |
  | `R20261124_123020` | 무인 통과 11/11 · 오류 0 · 근사 4(시도 5) — **그런데 동료 1 이름만 `regular`(2 · 3 은 `medium`), '표식' 14 pt(그린 값 15 pt), 세 이름의 색이 서로 다름** → 승격하지 않음 |
  | **`R20261124_130129`** | **무인 통과 11/11 · 오류 0 · 근사 4(시도 3)** — 사용자 눈 확인 통과('통과, 승격') |

- **'오류 0' 인데 틀린 run 의 원인 · 고침(사용자 승인 '고치고 다시 run'):** 참고판은 우리가 14 pt `medium` 으로 그린 그림인데, 파이프라인이 그 픽셀을 다시 재 크기 · 굵기 · 색을 알아맞혔다. 같은 글꼴로 그린 세 줄의 획 밀도 비가 1.145 · 1.096 · 1.093 으로 재져(획 높이 13 px) 한 줄만 문턱을 넘었고, 글자 맞춤이 **정답을 틀린 값으로** 바꿨다. `120141` 의 '표식' 도 같은 뿌리로 보인다. 문턱을 만지지 않고 접근을 바꿨다 — **배치 파일(`text_ref_layout.yaml`)이 글꼴 값의 단일 원천**:
  - `pt`(정수) · `weight` · `color` → `draw_items` 가 그리고 `concept_text_ref.json drawn[].font` 에 남김 → normalize 가 brief `font{size, weight, color}` → analyze `apply_declared_fonts` 가 spec 에 그대로(자간 · 그라데이션 없음, 상자는 가운데 기준으로 따라감).
  - 글자 맞춤은 위치만(`font_locked` — 크기 판은 건너뜀 · 위치 판은 자간 없이), LLM fix 는 `font.*` 를 못 건드림, 진단 E9 는 '그 값과 같은가'(다르면 오류 · fixable 아님). 그려진 높이 차(8 %) · 색 차(ΔE00 12) · 위치는 그대로 잰다.
  - 글꼴로 그린 참고판에만 걸린다(codex 참고판 · L-1 은 `drawn[].font` 가 없어 예전 길). 버린 안 — 굵기 문턱 넓히기(다른 화면의 판정이 느슨해짐) · 세 줄 다수결('표식' 처럼 혼자인 글자는 못 고침).
- **엔진 렌더 막대 검사(`130129`, 막대 8 × 0 · 5 · 15 · 40 · 65 · 90 · 100 %):** `bar_full` · `bar_cut` · `bar_outside` 모두 최대 0.0, 100 % 와 0 % 의 차(`track_contrast`) 32.8 ~ 64.9(문턱 10). 컨셉과의 국소 ΔE00 최대 검정 1.69 · 회색 5.15.
- **바꾼 파일(설계의 쓰기 범위 안):** Tools/uigen — 새 `gen/silhouette.py` · `tests/test_shaped_bar.py`(22) · `fixtures/status_hud_blade/`, `gen/{state_check,text_ref,diagnose}` · `stages/{normalize,analyze,layer,refine,style,fix}` · `run_pipeline.py` · `make_concept.py` · `schemas/{brief,inputs}` · `config/screens.yaml` · README. 게임 — 새 `UI/HUD/AstralStatusHUDWidget.*` · `AutoGen/AstralStatusHUDViewBase.*`, `AstralGameState.*` · `AstralPartyStatics.*` · `AstralPlayerState.*` · `AstralPlayerController.*`, 시험 `AstralPartyStaticsTests.cpp` · 새 `AstralStatusHUDPieTests.cpp`. WidgetMcp · 전투 HUD 파일은 안 건드렸다.
- **시험:** 빌드 DebugGame · Development(`-DisableAdaptiveUnity`) `Result: Succeeded` · 에디터 1 회에 `AstralBreak.` **60/60**(423 초, 경고는 RecastNavMesh 없음뿐) — 새 셋 `AstralBreak.Party.Allies` · `AstralBreak.Net.StatusHUD.ListenPIE`(2.3 초) · `.DedicatedPIE`(2.5 초)가 **첫 실행에 통과**, `ASTRAL_PIETEST` S0 ~ S5 실측값을 두 구성에서 확인(HP 0.4 → 최대 HP 두 배 0.2 · `FillUlt` 동료 오의 1.0 · 스태미나 0.1 · 표식 3 · 명단에서 빼고 넣기). `quit_editor` 미저장 0.
- **회귀:** pytest 463 → **485 통과**(실패 0 · 경고 2, 25 분 47 초) · 정답 묶음 **35/35 · 1/1 · 8/8** · 오프라인 묶음 새 라벨 `status_1124`(14 입력, layer 부터) ↔ `ring_1123` — **14/14 오류 · 근사 수 같음, `+ new` 0**.
- **긴 글자(엔진 렌더 — `work/R20261124_130129_StatusHUD/eye3/long.png`):** PIE 접속 이름(20 글자 · 231 px)은 이름 칸(204 px)을 넘지만 잘리지 않고 HP 막대 폭(257 px) 안, 30 글자는 막대 오른쪽으로 넘쳐 그려진다(잘림 · 말줄임 없음). HP '1250' · 표식 '10' 도 자리 안.
- **설계와 달라진 것:** ① 결정 8 에 글꼴 단일 원천을 더함(위) — 배치 파일의 `size`(px)가 `pt`(정수)로 ② 결정 9 의 `OnRep_bIsInactive` 는 따로 부르지 않는다 — 엔진이 그때 명단에서 빼고 다시 넣어 GameState 통지가 난다 [소스] ③ 리슨 호스트에는 RepNotify 가 없어 `CopyProperties` 에서도 같은 통지를 낸다.
- **사용자 눈 확인:** run 그림 **통과(11-24)** · 게임 안 **통과(11-24, 사용자 답 '통과' — 안내한 것: `CombatTestMap` PIE 2인 · 시작 모양 · `DamageSelf` · `FillUlt` · 스태미나 · 표식 · 허브에서 안 보임)**
- **돌리지 않은 것:** 3 · 4 인(동료 줄 2 · 3 이 실제로 채워지는 것 — 화면은 엔진 렌더로만, 고르는 규칙은 `AstralBreak.Party.Allies`) · 별도 프로세스 · 재접속(비활성 PlayerState) · 허브 → 레이드 이동 뒤 · 좁은 해상도의 눈 확인(1920 × 1200 · 2560 × 1080 은 화면 밖 게이트만). → **4인 동료 줄 1 ~ 3 · 이탈 뒤 줄 당겨짐 · 별도 프로세스 · 허브 → 레이드 이동 뒤는 M4 단위 E 가 돌려 통과했다(11-24, [m4-ult-chain.md](m4-ult-chain.md) §6 '단위 E 결과').** 남은 것 = 재접속 · 좁은 해상도 눈 확인.
- **남긴 것 · 주의:** ① 동료 이름은 접속 이름 그대로다(이름을 정하는 곳이 게임에 없다) ② verify 한 번이 약 220 초 — 막대 8 × 비율 7 을 하나씩 렌더한다. 막대끼리 안 겹치므로 같은 비율을 한 렌더로 묶으면 준다(안 함 — 선택) ③ 글꼴 값을 바꿀 때는 배치 파일을 고치고 `make_concept.py --only text_ref --draw … --force` 로 다시 그린 뒤 run 을 돌린다(기록과 그림이 같이 만들어진다).
- **정리(11-24 사용자 승인 — 휴지통, 약 146 MB):** run `114205` · `114339` · `114802` · `120141` · `123020`(`work` + `123020` 의 `_AutoGen`) · `work/_regress/compare_ring_1123_vs_status_1124` · 스크래치 `mainhud` · `mainhud2`. 남김: 승격본 run `130129`(`work` · `_AutoGen`) · 회귀 `status_1124`.

**Phase 2 설계 — 정리 · 집계 (2026-11-24, 사용자 승인 '전부 추천안' — 하위 세션, 결과는 아래 'Phase 2 결과')**

읽고 잰 것만 적는다(승인 전 글 — 저장소 코드를 고치기 전, 시제품은 스크래치 사본에서만). 잰 환경 = 이 PC, DebugGame 에디터 1회.

*① verify 시간 — 어디서 드나 [실측]*

재는 법: 지난 run 의 **엔진 렌더 PNG 를 그대로 돌려주는 가짜 `render_state`** 로 진단만 다시 돌린다(`diagnose.diagnose`). 다섯 run 모두 다시 만든 `diagnosis.json` 이 기록과 **차이 0** — 진단은 같은 입력에 같은 답을 내므로, 이 재생이 '고친 뒤에도 판정이 같은가'를 보는 도구가 된다. 렌더 호출의 구성은 저장된 run WBP 둘에서 호출 16번으로 쟀다.

| 렌더 호출 1번 | 초 | 내용 |
| :--- | ---: | :--- |
| SDF 글꼴 준비 대기 | 2.02 | 호출마다 **고정** — `WidgetMcpRender.cpp:169` `Sleep(0.05) × 40`. SDF 글꼴이 없는 화면(StatusHUD)도 같다 |
| HTTP 왕복 | 0.33 | 호출마다 새 연결(httpx 클라이언트 만들기 0.29) |
| 실제 그리기 · PNG 저장 | 0.07 | 2번 그려 비교 + 저장 |
| **합** | **2.41** | 일하는 시간은 3 % |

| verify 1번(초) | StatusHUD `130129` | CombatHUD `194019` | CombatHUD `172628` |
| :--- | ---: | ---: | ---: |
| 기록된 값(run.log) | 216 ~ 223 | 198 ~ 283 | 74 ~ 82 |
| 렌더 호출 수(상태 렌더) | 62(60) | 18(16) | 11(9) |
| 렌더 호출 시간(× 2.41) | 149 | 43 | 27 |
| └ 그중 고정 대기 | 125 | 36 | 22 |
| Python 진단(재생으로 잰 값) | 84.5 | 77.6 | 45.6 |
| 컴파일 · 역추출 등(단계 기록 차) | 약 2 | 약 2 | 약 2 |
| run 의 verify 횟수 | 3 | 7 | 6 |

`194019` 의 기록(198 ~ 283초)은 지금 잰 구성(약 123초)보다 길다 — 그때 PC 에 다른 일이 겹쳤을 것으로 본다 [추론 — 확인할 기록 없음]. Python 시간의 대부분은 **전 화면 ΔE00**(1920 × 1080 한 번에 약 0.9초)이다: 바뀐 픽셀이 화면의 몇 %뿐인데 200만 픽셀을 다 잰다(접힌 위젯 빛 · 고리 · 막대 밖 검사), 글자 밑 흔적의 ±2 px 이동 최소(`_shift_min_de`)는 25번마다 판 전체를 실수로 바꾸고 Lab 을 다시 구한다.

*② verify 시간 — 선택지*

| 안 | 내용 | verify 1번(예상) StatusHUD · CombatHUD | 판정 |
| :--- | :--- | ---: | :--- |
| (가) Python 만 | ΔE00 을 **다른 픽셀 · 판정에 쓰는 자리에서만** 잰다(`delta_e(a, b, where)` — 같은 픽셀의 ΔE00 은 정확히 0), `_shift_min_de` 는 Lab 을 한 번만 구하고 이미 같은 픽셀은 건너뜀, `explain_diff` · `hidden_halo` · 게이지 · 고리 · 막대 검사는 자리 안만 | 217 → 약 166 · 약 123 → 약 61 | 시제품으로 다섯 run 에서 `diagnosis.json` · `compare.png` **바이트까지 같음**(진단 시간 84.5 → 15.1 · 77.6 → 16.2 · 45.6 → 12.3 · 40.5 → 11.3 · 41.1 → 11.4) |
| **(나) (가) + 상태 렌더 묶음 — 추천** | `render_widget` 에 선택 인자 `states: [{name, overrides}]` — 한 호출에서 상태마다 **새 인스턴스로 똑같이** 그린다(준비 대기는 모든 상태를 한 번씩 미리 그린 뒤 한 번). Python 은 필요한 상태를 먼저 모아 한 번에 부르고, 이름 · 값이 다르거나 묶음이 실패하면 지금처럼 한 장씩 | → 약 28 · 약 26 | 그리는 길이 같다. 저장된 두 WBP 에서 '한 장씩' ↔ '묶음' PNG 를 전부 바이트로 견줘 같을 때만 쓴다. **WidgetMcp C++ 를 고친다**(`WidgetMcpRender` · 도구 인자 · 시험 1개) → 빌드 2 구성 + `WidgetMcp.` 시험. 게임 모듈은 안 바뀌어 `AstralBreak.` 은 뺀다 |
| (다) 막대 묶기(설계 때 후보) | (가) + 안 겹치는 막대의 같은 비율을 한 렌더로 | → 약 45 · 약 61 | **버림** — `bar_outside`(막대 하나를 바꿀 때 다른 그림이 바뀌나)의 뜻이 바뀐다: 막대들이 같이 바뀌면 한 막대가 이웃 막대 픽셀을 침범해도 못 가른다 |
| 되돌린 뒤 재검증 건너뛰기 | 되돌린 spec · revision · 렌더가 앞 시도와 같으면 진단을 재사용 | run 에 되돌림이 있을 때만 1번분 | **버림** — (나) 뒤엔 한 번이 약 30초라 얻는 것이 작고, 되돌린 에디터 상태를 다시 보는 뜻이 약해진다 |
| 구조 게이트가 깨진 시도의 진단 생략 | 첫 시도는 재시도가 구조만 보므로 진단을 안 씀 | run 마다 1번분 | **버림** — 검사를 빼서 빨라지는 것은 제외(요청). 실패한 run 의 `compare.png` 도 없어진다 |
| 준비 대기 줄이기 · 끄기 | 0.05 × 40 을 줄이거나 SDF 글꼴이 없으면 생략 | — | **버림** — 글리프가 다 됐는지 알 공개 API 를 찾지 못했다. 줄이면 자리표시 글리프가 그려질 수 있다(F 에서 겪음) |

- 같은 ΔE00 함수를 refine 의 글자 지우기 고르기 · 글자 맞춤도 쓴다 — 그쪽도 빨라지지만 결과가 바뀌면 안 되므로 `regress_set`(refine replay 포함)으로 같이 본다.
- **측정 중 찾은 것(기록만 — 이번 범위 밖):** 저장된 CombatHUD WBP 를 **새 에디터에서 처음** 그린 한 장만 24,688 px 이 기록과 달랐다(고리 자리). 두 번째부터는 16 상태 모두 기록과 바이트까지 같다. 머티리얼 셰이더가 첫 그리기에서야 컴파일을 시작하는 것으로 보인다 [추론]. 그 자리에서 머티리얼을 만드는 run 은 첫 시도부터 정상이었다(`render` = `state`, 세 run 확인). 저장된 화면을 다시 여는 **Phase 4 에서 부딪힌다** — (나) 를 고르면 미리 그린 뒤 셰이더를 한 번 더 기다리게 해 같이 막는다.

*③ LLM 외형 검토 라운드*

- 남은 report 중 11-18 이후 41 개(직접 다시 셈): 지적 없음 29 · 되돌림 10 · 받아들임 2 — 총괄 값과 같다. LLM 환산 8.82 USD(구독 — 과금 아님 · verifier 6.83 + fix 1.98) · 라운드 단계 817초 + 라운드가 더 돌린 verify 1,799초.
- **받아들인 2건** = `R20261120_142400` · `R20261122_142544`, 둘 다 파티 HUD(`ProbePartyHUD` — 외부 시험 컨셉 · L-1)이고 **둘 다 실패한 run**(오류 21 · 18)이다. 고친 것도 같은 op 하나 — 초상화 자리표시 `PortraitImage.style.brush.color` 알파 `FF → 00`(불투명 네모가 마름모 프레임을 가림). 진단 점수는 그 앞뒤가 같다(결함 23 → 23 · 나쁨 208.629 → 208.629, 20 → 20 · 252.069 → 251.458) — 런타임 그림 자리는 진단이 빼고 보기 때문이다. **지금 게임 화면 둘에는 런타임 그림(binding `image`)이 없어 필요 없다.** 다만 '그림을 넣기 전 자리표시가 프레임을 가린다'는 M7 아이콘 때 다시 나올 수 있다 → 그때 결정적 규칙(자리표시 알파 0)으로 — 남긴 것에 적는다.
- **흐름 확인:** `_style_review` 는 `rounds` 와 무관하게 비교 기록(`style_compare` → `style/before` · `report.recorded.style_review.before`)을 먼저 남기고, 글자 맞춤은 따로 `style_review.text_fit` 만 본다(`run_pipeline.py:426 · 434 · 501`). 라운드가 0 인 길은 이미 deterministic 모드에서 시험한다(`test_style_round_off_in_deterministic_mode` — `rounds_allowed 0` · `before` 있음 · 글자 맞춤 돎). 즉 **`style_review.rounds: 0` 만으로 라운드만 꺼진다.**

| 안 | 내용 |
| :--- | :--- |
| **설정으로 끄기 — 추천** | `rounds: 1 → 0` + 이유 주석. 코드 · 프롬프트 둘은 남긴다 — Phase 4 '지시 해석'(선택)이 같은 가드(`guard_style_ops`)와 patch 길을 쓸 수 있다. 라운드 시험 셋은 `rounds: 1` 을 명시해 계속 돈다. hybrid 모드에서 라운드 0 인 run 시험을 하나 더한다 |
| 걷어내기 | `_style_review` 의 라운드 반복 · `style.propose` · 가드 · 사본/되돌림 · 프롬프트 2 · 시험 약 10개를 지운다. 되살릴 때 다시 쓴다 — **지금은 버림**, Phase 4 가 쓰지 않기로 정해지면 그때 |

*④ 집계 리포트*

- 스크립트 `Tools/uigen/summarize.py`(읽기만 — `metrics/uigen.jsonl` · `work/R*/report.json` · `run.json` · `llm.jsonl`) → 글 리포트 하나(마크다운). 숫자는 모두 스크립트가 세고, 같은 입력이면 같은 글이 나온다. 경로 · 토큰 · 계정 · LLM 글은 넣지 않는다(run id · 화면 이름 · 수만). 시험 = 합성 입력으로 세는 값 · 경로 문자열 없음.
- 담을 것: 자료 범위와 한계(아래) · 날짜 × 화면별 run 수와 결과 · 실패 게이트 · 걸린 시간 · 에셋 출처 추이 · LLM 호출과 환산 비용(단계별) · 외형 라운드 결과 · verify 비중(앞 · 뒤) · 게임 화면 승격 run 표.
- **한계를 리포트 첫머리에 적는다:** ① jsonl 은 208 run 전부지만 `work` 폴더는 57 run 만 남았다(정리 때 실패 · 중간 run 을 지움) — report 에서 센 값은 '남은 57'의 값이고 **전체 통과율이 아니다** ② `CombatHUD` 122 run 은 대부분 파이프라인을 만들던 시험이다 — 화면 이름만으로 게임 run 과 가를 수 없어 통과율을 내지 않고 날짜 × 화면 수만 싣는다. 게임 화면은 승격한 run 만 따로(이름은 이 문서에서) ③ 초기 줄 셋은 `status` 가 없다 ④ 'USD' 는 API 정가 환산이고 구독이라 과금이 아니다.
- 이미 센 값(확인용): 1,632 줄 = run 208 + 에셋 1,424 · `style_sim_anchor` 값 0 · 실패 게이트 appearance 65 · iou_leaf 10 · baked_text 6 · overlap 5 · iou_region 2 · 11-17 부터 codex 에셋 0(11-16 115 → 0) — 앞 절의 값과 다른 것 없음.
- **저장소에 둘지(§12-2 의 7):** (a) **스크립트 + 글 리포트 `Docs/Design/ui-autogen-report.md` 를 커밋 대상으로 — 추천**(원본 jsonl · work 는 git 무시라 리포트가 남는 유일한 증거, 넣는 것은 수와 이름뿐) (b) 스크립트만 저장소, 리포트는 `Tools/uigen/metrics/`(git 무시) (c) 둘 다 저장소에 안 둠.

*⑤ 스킬 문서 둘(§10-2 — `.claude/` 라 쓰기 전 확인)*

| 파일 | 담을 것(확인된 것만, 근거 파일:줄) |
| :--- | :--- |
| `.claude/skills/ue-umg-authoring/SKILL.md` | 새 WBP 루트 없음(`DefaultRootWidget`) · GUID 맵과 `OnVariableAdded` · FWidgetRenderer 감마(LUT) · 2번 그리기 · SDF 글리프 준비 · 첫 그리기 셰이더 · 화면 밖 컬링 geometry 0 · 텍스처 설정(압축 이름 · NeverStream · Interchange NPOT) · box 9-slice 모서리 크기 · 디자이너 미리보기(`bHiddenInDesigner`) · ProgressBar Mask/Scale · BindWidget 계약 해시 · 생성 헤더 이름 겹침 · 지난 `_AutoGen` WBP 컴파일 오류 주의 |
| `.claude/skills/uigen-run/SKILL.md` | 화면 만들기 순서(make_concept → run → compare.png → 승격) · 명령 · 에디터 주기 · report 읽는 법(오류 E · 근사 A · 게이트 11 · manual_check) · 규칙을 고친 뒤 회귀(golden · regress_set) · 함정(옛 손 spec 을 돌리지 말 것 등) |

`CLAUDE.md` · 기존 스킬 셋 · 훅은 안 건드린다. `.claude/settings.local.json` 도 안 건드린다(git 무시 — 개인 설정).

*⑥ 곁가지*

- 고칠 것(주석 · 안 읽는 키만): `pipeline.yaml` 의 'comfy 는 Phase 5' · 'Phase 5 ComfyUI 와 함께' 주석 → '삭제(11-24)', `routing.yaml` 의 `mockup` 줄 · icon `anchor` · `retry_backend`(읽는 코드 없음) · 낡은 '1a 는 …' 주석.
- **목록만 남김(스키마 · 시험이 걸림):** `metrics.py` 의 `style_sim_anchor`(늘 null — `test_run.py:72` 가 확인) · spec 스키마 `provenance` 의 `comfy` · manifest/spec 의 `anchor` · `extract.text_fill_complex`(V8 인터페이스 — 사용자 결정으로 둔 자리) · `routing.yaml limits.on_quota`(읽는 코드 없음 — 동작은 늘 '멈춤').

*⑦ 검증(승인 뒤)*

1. pytest 전체 1회(새 시험: `delta_e(where)` · `_shift_min_de` · `explain_diff` ↔ 옛 식, 묶음 렌더 = 한 장씩 · 실패하면 한 장씩, 라운드 0 hybrid, 집계).
2. 오프라인 새 ↔ 옛: 남은 run 중 재생할 수 있는 것 전부에서 `diagnosis.json` · `compare.png` 바이트 비교.
3. 정답 묶음 `golden.py check` · `regress_set run p2_1124 --relayer` ↔ `status_1124`(새 결함 0).
4. ((나)를 고르면) 빌드 DebugGame · Development + 에디터 1회에 `WidgetMcp.` + 두 WBP '한 장씩 ↔ 묶음' PNG 바이트 비교.
5. 실제 run — `fixtures/combat_hud_blade` · `fixtures/status_hud_blade` 각 1회(라운드 끔), 시간 앞뒤 · 오류 · 근사 · 게이트 비교, `compare.png` 직접 봄. 승격하지 않는다. analyze(LLM)가 run 마다 배치를 조금 다르게 내므로 run 끼리의 근사 수가 같을 거라고는 약속하지 않는다 — '판정이 같다'는 2 · 3 · 4 가 증명한다.

**쓰기 범위:** `Tools/uigen/**`(새 `summarize.py` · 시험) · ((나)면) `Plugins/WidgetMcp/**` · `Docs/Design/ui-autogen-pipeline.md` · (승인되면) 리포트 · `.claude/skills/` 둘. 측정이 남긴 일회성 = `work/_measure_p2/` + 세션 스크래치(끝에 목록 → 승인 → 휴지통).

**사용자에게 묻는 것:** 1 집계 리포트를 저장소에((a) 추천) · 2 외형 라운드(설정으로 끄기 추천) · 3 verify((나) 추천 — WidgetMcp C++ 승인 포함) · 4 `.claude/skills/` 에 문서 둘 쓰기(추천: 승인). → **결정(11-24): 전부 추천안.**

**Phase 2 결과 (11-24, 커밋 `fe0bac4` — 하위 세션. 위 설계 그대로, 다른 곳은 '설계와 달라진 것')**

*verify 시간 — 앞 · 뒤*

| | StatusHUD 앞 `130129` | 뒤 `R20261124_201408` | CombatHUD 앞 `194019` | 앞 `172628` | 뒤 `R20261124_200822` |
| :--- | ---: | ---: | ---: | ---: | ---: |
| verify 1번(초, 중앙값) | 217.2 | **25.9** | 220.9 | 78.7 | **27.8** |
| verify 합(횟수) | 657(3) | **78(3)** | 1,585(7) | 470(6) | **140(5)** |
| run 단계 합(초) | 842 | **183** | 1,818 | 658 | **260** |
| verify 비중 | 78 % | 43 % | 87 % | 72 % | 54 % |
| 상태 렌더(묶음 · 한 장씩) | 0 · 60 | 60 · 0(5.8초) | 0 · 16 | 0 · 9 | 16 · 0(3.3초) |
| 결과 · 게이트 · 오류 · 근사 | pass · 11/11 · 0 · 4 | pass · 11/11 · 0 · 4(같은 위젯 · 같은 종류) | pass · 11/11 · 0 · 3 | pass · 11/11 · 0 · 3 | pass · 11/11 · 0 · 2 |

횟수가 다른 것은 analyze(LLM) 배치가 run 마다 조금 달라 글자 맞춤 판 수가 다르기 때문이다(앞 `194019` 는 되돌린 판이 하나 있었다). `194019` 의 긴 시간에는 다른 작업이 겹쳤을 수 있다 [추론]. StatusHUD 의 refine 도 77.9 → 9.9초로 나왔는데 원인은 재지 않았다(앞 run 때의 PC 부하일 수 있다).

- **고친 것 — Python:** `diagnose.delta_e(a, b, where)`(다른 픽셀 · 자리 안만 — 같은 픽셀의 ΔE00 은 정확히 0) · `_shift_min_de(where)`(Lab 한 번 · 같은 픽셀 건너뜀) · `state_check` 의 `explain_diff` · `hidden_halo` · 게이지 · 고리 · 막대 검사. 상태 렌더 목록은 `state_check.state_requests` 하나로(대상 고르기 `gauge_targets` · `radial_targets` 를 검사와 같이 씀), verify 의 `StateRenders` 가 묶음으로 그리고 못 하면 한 장씩(기록 `attempts/NNN/gates.json notes.state_renders`).
- **고친 것 — WidgetMcp C++:** `render_widget states[{name, overrides}]` — 한 장씩 그리던 길을 함수(`MakeInstance` · `WarmUp` · `DrawInstance`)로 나눠 둘이 같이 쓴다. 상태마다 새 인스턴스, 준비 대기 한 번, 이름 = 폴더(영숫자 · _ · - , 대소문자 무시 중복 거절), overrides · probes 와 함께 못 씀, 최대 256. 미리 그린 뒤 셰이더를 한 번 더 기다린다 — 측정 중 찾은 '새 에디터 첫 렌더에서 고리가 빠짐'이 없어졌다(첫 장 = 기록과 바이트 같음).
- **판정이 같다는 증명:**
  - 엔진: 저장된 두 WBP 의 76 상태(16 + 60)에서 **묶음 = 한 장씩 = 앞 run 기록, PNG 바이트까지 76/76**(한 장씩 36.8 · 137.2초 → 묶음 3.3 · 6.1초).
  - 오프라인: 남은 run 의 마지막 시도를 옛 코드(HEAD 사본)와 지금 코드로 다시 진단 — 비교할 수 있는 **44 run 전부 `diagnosis.json` · `compare.png` 바이트까지 같음**(차이 0). 13 run 은 컨셉에 알파가 없어 예전부터 진단 대상이 아니다. 진단 시간 합 4,954 → 1,349초(다른 시험과 같이 돌림).
  - 회귀 묶음 `p2_1124`(14 입력, layer 부터) ↔ `status_1124`: `+ new` **0**, 파일 529개 중 **528개 바이트 같음**(남은 하나는 코드 파일 목록을 적는 `set.json`) — refine 이 고른 텍스처까지 같다. 새 기준선 = `p2_1124`.
  - 정답 묶음 **35/35 caught · 1/1 clean · 8/8 protected** · pytest 485 → **496 통과**(실패 0, 다른 시험과 같이 17분 47초) · 빌드 DebugGame · Development(`-DisableAdaptiveUnity`) `Result: Succeeded` · `WidgetMcp.` **8/8**(Render 시험에 묶음 = 한 장씩 바이트 비교 · 거절 4 종을 더함). 게임 모듈을 안 고쳐 `AstralBreak.` 은 돌리지 않았다.
- **LLM 외형 라운드:** `style_review.rounds: 0`. 두 run 모두 `rounds_allowed 0` · 라운드 0 · `style_compare`(before) 기록 있음 · 글자 맞춤은 그대로(CombatHUD 크기 판 · 위치 판 · 마지막 크기 판 받음, StatusHUD 위치 판 받음). LLM 호출 4 → 3. hybrid 모드에서 라운드 0 을 보는 시험을 더했다(라운드 시험 셋은 켜고 돈다).
- **집계:** `Tools/uigen/summarize.py` → [ui-autogen-report.md](ui-autogen-report.md)(110 줄). 총괄이 센 값(run 208 · 에셋 1,424 · 라운드 41 = 29 · 10 · 2 · 8.8 USD)과 같고, 이번 run 둘이 더해져 run 210 이다. 설계에 적은 '초기 2줄에 status 없음'은 세어 보니 **3줄**이라 고쳤다.
- **스킬:** `.claude/skills/ue-umg-authoring/SKILL.md` · `.claude/skills/uigen-run/SKILL.md`(사용자 승인). 엔진 줄 번호는 5.7.4 소스에서 다시 확인했다. `CLAUDE.md` · 기존 스킬 · 훅 · `settings.local.json` 은 안 건드렸다.
- **곁가지:** `pipeline.yaml` 의 comfy · Phase 5 주석, `routing.yaml` 의 `mockup` · `anchor` · `retry_backend` · 낡은 1a 주석을 정리했다. 스키마 · 시험이 걸린 것은 ⑥ 의 목록대로 남겼다.
- **눈으로 본 것:** 두 run 의 `compare.png` 를 이 세션이 직접 봤다 — CombatHUD 글자 높이 비 0.964 ~ 1.069(앞 0.96 ~ 1.077) · 게이지 · 고리 여섯 비율, StatusHUD 동료 이름 세 줄 굵기 · 크기 · 색 같음(14 pt medium) · 막대 검사 전부 0.0. **사람 눈 확인은 받지 않았다** — 승격하지 않았으므로 게임 화면은 앞 승격본 그대로다.
- **설계와 달라진 것:** ① 게이지 · 고리 비율 렌더를 8 비트로 든다(값 같음 — PNG 가 정수라, 전 화면 실수 그림을 들고 있지 않게) ② 시험 `golden` · `regress` 에 더해 남은 run 전체 바이트 비교를 했다 ③ `Tools/mcp/widget_mcp`(MCP 창구)에는 `states` 를 더하지 않았다 — 쓰기 범위 밖이고 파이프라인은 브리지를 직접 부른다.
- **돌리지 않은 것 · 남긴 것:** 게임 안 확인(승격 안 함) · L-1 컨셉과 검증 화면의 실제 run(오프라인 재진단 · 회귀 묶음으로만) · `AstralBreak.` · 새 계약의 codegen 길(두 run 모두 `skipped`). 런타임 그림 자리표시가 프레임을 가리는 것은 M7 아이콘 때 결정적 규칙으로(③). verify 1번에서 남은 시간은 Python 진단 12 ~ 16초 · 묶음 렌더 3 ~ 6초 · 묶음 밖 렌더 두 호출(해상도 셋 · sample) 약 5초.
- **정리(11-24 사용자 승인 — 휴지통, 약 225 MB):** `Tools/uigen/work/_measure_p2`(35 MB) · `work/_widgetmcp_tests`(467 KB, `WidgetMcp.` 시험 출력) · `Tools/mcp/results/widget_spike/20261124_200751` · `work/_regress/compare_status_1124_vs_p2_1124` · 세션 스크래치(약 190 MB). 남김: run `200822` · `201408`(`work` + `_AutoGen`, 앞뒤 증거) · 기준선 `p2_1124`.

**Phase 4 설계 — 이어서 고치기 (2026-11-24 작성 · 같은 날 사용자 승인 '추천안으로' — 하위 세션, 구현은 새 세션)**

읽고 잰 것만 적는다(저장소 코드는 안 고침 — 이 글과 위 '미커밋' 표기 둘뿐). 잰 환경 = DebugGame 에디터 1회, 승격본 둘은 읽고 그리기만, 새 패키지는 메모리에만 만들고 폐기(종료 때 미저장 0), 나머지는 스크래치 재생.

*① 조사 [실측 · 소스]*

| 물음 | 답 |
| :--- | :--- |
| 승격본 = 기록된 run 인가 | **그렇다.** 역추출 spec 이 run 의 최종 spec 과 같고(차이 0 · `unsupported` 0), 렌더 PNG 가 StatusHUD **63/63** · CombatHUD **19/19 바이트까지** 같다(3 해상도 + 상태 60 · 16). 디스크 파일 23개의 SHA256 = 커밋한 LFS 값 23/23 — 승격 뒤 사람이 고친 것이 없다 |
| 다시 지으면 같은가 | **같다.** spec · brief · manifest · `assets/final` 만으로 새 run 폴더에 지은 WBP 가 승격본과 63/63 · 19/19 바이트 같음(짓기 1.2 · 0.8초, 전체 상태 렌더 8.5 · 5.7초). LLM · codex 0 |
| 고쳤다 되돌리면 | 작은 수정 아홉 가지(StatusHUD 5 · CombatHUD 4)를 하나씩 넣고 되돌림 — revision 은 매번, 렌더는 끝에 63/63 · 19/19 처음과 같음. 수정 한 번 짓기 0.4 ~ 0.7초, 조정기가 바꾼 위젯 = patch 대상 하나뿐 |
| 안 바꾼 위젯이 흔들리나 | 다른 위젯의 geometry 차 **0**. 대상 상자 + 2 px 밖 픽셀 차도 아홉 중 여덟에서 0 — 하나는 글자가 상자 밖으로 넘쳐 상자 기준으로 44 px 이 남는다(`SelfHpText` 20 → 22 pt, 상자 그대로면 88 px — 기본 상태는 0, 값을 바꿔 그린 상태에서만) |
| 지금 외형 게이트를 그대로 쓰면 | **아홉 수정 중 여덟이 실패한다**(E9 크기 · 색, E6 위치, 패널을 옮기면 오류 5 ~ 28). 정답이 컨셉이라 '일부러 바꾼 것'을 결함으로 본다. `iou_leaf` · `iou_region` 도 옮긴 대상에서 실패, 좁은 자리에서 옮기면 `overlap` 1(`UltBlockedText` ↔ `ChainPanel` 0.146 · `Ally2Panel` ↔ `Ally3Panel` 0.086 · `ChainPanel` ↔ `BurstBanner` 0.201) |
| revision 으로 알 수 있나 | 부족하다. revision 은 `ExportTree(…, Assets = nullptr)` 의 SHA1 이라(`WidgetMcpBlueprint.cpp:395`) **텍스처 경로가 들어가** 같은 내용도 폴더마다 다르다 — run `5d57d1a1…` ↔ 승격본 `934da996…`. 이벤트 그래프 · 위젯 애니메이션 · 어휘 밖 속성의 값 · 텍스처 픽셀은 아예 안 들어간다 |
| 승격본을 가리키는 쪽 | C++ 기본값 둘뿐(`AstralPlayerController.cpp:93-94`, 소프트 클래스 경로) + 시험 둘(`AstralCombatHUDPieTests.cpp:59` · `AstralStatusHUDPieTests.cpp:41`). 다른 uasset · umap 이 가리키는 것 0(Content 전체 문자열 검색 — 자기 폴더와 `_AutoGen` 뿐) |
| 다시 진단에 필요한 파일 | 최종 시도의 엔진 렌더를 되돌려 주며 파일을 빼 봤다. 아트 · 글자 없는 판을 빼면 진단이 달라지고(차이 25 ~ 97 곳), `reference*` 셋은 없으면 진단을 건너뛴다 [소스]. `raw` · `reference_textref_*` · `compare.png` · `gen.jsonl` · `codegen.json` · `lineage.json` · (이 두 화면에서는) `refine.json` · `layer` 는 빼도 같다(차이 0) |

*② 명령과 흐름*

```text
run_pipeline.py --from <ScreenId | run_id> --edit <patch.json>
  seed(원천 묶음 → 새 run 폴더 · parent_run_id) → base(고치기 전 spec 을 그대로 짓고 전체 게이트) → patch 적용 → build → verify(+ edit_regression) → finalize
```

- **LLM 0 · codex 0 · 재시도 0 · 글자 맞춤 0.** analyze · layer · generate · refine 을 안 돌고 최종 spec · 텍스처를 그대로 쓴다. 고침 · 글자 맞춤을 켜면 안 바꾼 칸이 다시 흔들리므로 실패하면 이유를 남기고 끝낸다(patch 를 고쳐 다시 — 한 번에 약 1분). codegen 은 지금처럼 계약 해시 확인만(같아서 `skipped`, 다르면 `EDIT_CONTRACT_CHANGED` 로 멈춤).
- **기준은 저장해 둔 그림이 아니라 같은 에디터에서 막 지은 base 다** — GPU · 드라이버가 바뀌어도 견줄 수 있다. `--from <ScreenId>` 면 base 가 **지금 승격본**과 spec · 렌더까지 같은지도 본다(다르면 `BASE_DRIFT` — 승격본 · 원천 · 코드 중 하나가 어긋난 것).
- `parent_run_id` 는 `lineage.json` · `report.json` 둘 다(스키마에 이미 자리가 있다). 새 `edit.json` = 부모 · patch · 대상 · 자리 · 게이트 기록.

*③ 입력 — §4-4 patch 그대로 + 선택 필드 셋*

- `source: "edit"`. 받는 op: `set` · `move` · 바인딩 없는 `add_widget` · 바인딩 없는 `remove_widget`. 선택 필드 `affects`(자동 배치 때문에 같이 움직여도 되는 위젯) · `allow_overlap`(겹쳐도 되는 쌍) · `note`(왜).
- 거절: `binding` 바꿈 · 바인딩 위젯 추가(계약의 원천은 inputs — 전체 run) · `replace_asset`(지금 텍스처는 전부 컨셉 픽셀 · 판이라 옮긴 spec 으로 다시 오리면 다른 자리를 오린다 — 2판) · 어휘 밖 값(지금 검사 그대로).
- **글꼴 값의 단일 원천:** StatusHUD 는 `text_ref_layout.yaml` 이 크기 · 굵기 · 색을 정한다. patch 가 그 값을 바꾸면 `edit.json source_notes` 에 '원천 파일의 어느 줄이 낡았나'를 적고, 승격 기록의 `edits[]` 에 patch 를 쌓는다. 원천 파일을 자동으로 고치지는 않는다(그림까지 다시 그려야 한다). 대신 **전체 run 을 새로 돌린 결과는 '지금 승격본의 자식'이 아니므로 재승격이 거절한다** — 쌓인 수정이 조용히 사라지지 않는다.

*④ 수정 회귀 게이트 `edit_regression`(수정 run 에만 — 12번째)*

| | 무엇을 | 기준 |
| :--- | :--- | :--- |
| spec | 엔진 역추출 base ↔ 새 것, 대상(+ 자손 · `affects`) 밖 위젯 · 텍스처 설정 | 같음. 조정기 op 의 위젯 ⊆ 대상 |
| geometry | 세 해상도, 대상 밖 위젯 | 차 0(> 0.01 px 이면 실패 — §8-1 의 1 px 보다 좁힘, 같은 세션이라 실측 0) |
| 픽셀 | 세 해상도 + 진단이 쓰는 모든 상태(63 · 19장), 대상 자리 밖 | 다른 픽셀 **0**(문턱 없음). 자리 = 대상 상자(앞 ∪ 뒤) + 외곽선 · 그림자 · 빛 크기 + 2 px. 밖에 남으면 **그 상태만 대상을 끈 렌더**를 앞뒤로 더 그려 '대상이 실제로 그린 픽셀'로 다시 잰다(넘친 글자는 여기서 풀린다) |
| 효과 | 어느 상태에서도 픽셀 · geometry 가 안 변함 | 실패 `NO_EFFECT`(이름을 틀렸거나 가려진 것) |

- 구조 게이트 10개는 그대로. `iou_*` 는 대상만 새 실측 상자를 `bbox_intent` 로 삼고(옮긴 값은 기록), `overlap` 은 base 에도 있던 쌍 · `allow_overlap` 쌍을 뺀다.
- 외형 게이트는 진단(`gen/diagnose`)을 **안 고치고** 결과를 나눈다: base 에도 있던 결함 = 이어받음(기록) · 새 결함이 대상 자리 안 = 의도한 변경(기록) · **자리 밖 = 오류**. 엔진 그림끼리 견주는 상태 검사(막대 · 고리 · 게이지)는 자리 안이어도 새로 생기면 오류.
- **한계(그대로 적는다): 바꾼 자리 안의 모양은 기계가 판정하지 않는다 — 정답이 없다.** 실측에서 '표식' 을 18 pt 로 키운 수정은 글자 외곽선이 초승달을 파먹지만 자리 밖 차가 0 이라 회귀 게이트로는 안 잡힌다. 그래서 `edit.png`(고치기 전 | 고친 뒤 | 달라진 픽셀, 확대)를 만들고 승격 앞에 사람 눈을 둔다.

*⑤ 원천 보관 — 승격 때 무엇을 어디에*

| 안 | 화면당 크기 | 판정 |
| :--- | ---: | :--- |
| **(가) 최소 묶음을 저장소에 — 추천.** `Tools/uigen/promoted/<ScreenId>/source/` = spec · `specs/000` · brief · inputs · normalize · manifest · refine · layer(+ 마스크) · gen · codegen · lineage · geometry · diagnosis + `assets/final` + `reference*`(글자 참고판 정합본 셋은 뺌) | CombatHUD 2.1 MB(31 파일) · StatusHUD 1.0 MB(42 파일) — LFS 에 올라갈 PNG 는 1.6 · 0.6 MB(아트와 글자 없는 판이 같은 파일), JSON 은 119 · 174 KB | 이 PC 가 없어져도 이어서 고친다. PNG 는 이미 LFS 대상 |
| (나) JSON 과 `assets/final` 만, reference 는 fixture 에서 normalize 로 다시 | 0.6 · 0.3 MB | normalize 코드가 바뀌면 정답 그림이 달라져 옛 화면을 못 잇는다 — 버림 |
| (다) run 폴더 통째 | 55 · 36 MB | 시도별 렌더가 대부분 — 버림 |
| (라) 지금처럼 git 무시 | 0 | 이 PC 에서만, 폴더를 지우면 끝 — 버림 |

`promoted/<ScreenId>/promotion.json` = 승격 기록의 단일 원천: 화면 · run · 부모 · 대상 폴더 · **파일마다 SHA256 · 크기** · 승격본 revision · 계약 해시 · 묶음 JSON 의 정규 해시(줄바꿈이 바뀌어도 같게) · `edits[]`(전체 run 뒤 쌓인 patch). **소급:** 같은 도구의 `record` 로 두 run 을 묶는다 — 역추출 · 렌더가 run 기록과 바이트까지 같을 때만 쓴다(①에서 이미 둘 다 같음).

*⑥ 재승격 · 되돌리기*

| 안 | 내용 | 판정 |
| :--- | :--- | :--- |
| **(가) 제자리 바꾸기 — 에디터를 끈 채 파일로 · 추천** | 사람이 부르는 `promote_screen.py apply`: 에디터 꺼짐 확인 → 파일 해시 = 승격 기록(아니면 거절) → 옛 파일 · 묶음을 `work/_promoted/<화면>/<시각>/` 에 복사하고 해시 확인 → 기록에 있는 파일만 비움 → 에디터를 띄워 **지금 `promote_widget`(빈 폴더에만)** → 역추출 · 렌더가 run 과 같은지 → 에디터 종료 → 새 기록. 중간에 어디서 실패하든 옛 파일을 되돌리고 해시 확인(일지 `journal.json` + `recover`). `revert` = 사본을 그대로 되돌림(바이트 같음, 에디터 불필요) | 경로가 그대로라 C++ · 시험 · 다른 애셋 변경 0, **WidgetMcp C++ 변경 0 · 빌드 0**. 엔진 쪽 마지막 방어(대상이 비어 있지 않으면 거절)도 그대로 남는다 |
| (나) 새 판 폴더 + 참조 바꾸기(`StatusHUD_v2` …) | 기존 파일을 절대 안 건드림 | 고칠 때마다 C++ 경로 · 시험 · 빌드 2, 옛 폴더가 쌓이고 LFS 도 매번 새 파일. `screens.yaml` 의 '화면 하나 = 폴더 하나'가 깨짐. 데이터 애셋으로 한 겹 두면 C++ 은 안 바뀌지만 게임 코드에 '판 고르기'가 생긴다 |
| (다) 지금처럼 거절하고 손으로 | 변경 없음 | Phase 4 가 없애려는 것. 손 작업이라 사본 · 확인이 매번 다르다 |
| (라) 에디터 안에서 덮어쓰기 | `AdvancedCopyPackages(…, bCopyOverAllDestinationOverlaps = true)` | 로드된 애셋 위에 `DuplicateSingleObject` + `ConsolidateObjects` 로 바꿔 끼운다(`AssetTools.cpp:2630-2688` [소스]) — 되돌리기 저널이 없고 열린 클래스의 재인스턴스가 낀다. 버림 |

- **안전 규칙과의 관계:** '`/Game/_AutoGen/<run_id>/` 아래에만 생성 · 기존 애셋 덮어쓰기 · 삭제 금지'는 **무인 파이프라인에 그대로**다(수정 run 도 새 run 폴더에만 만든다). 예외는 사람이 확인하고 부르는 `promote_screen.py` 하나 — 자기가 기록한 파일이 **그대로일 때만**, 해시를 확인한 사본을 남긴 뒤 바꾼다. 강제 옵션은 만들지 않는다. §9 에 이 예외를 적는다.
- **재승격이 더 보는 것:** 그 run 이 통과 · 저장됐나, 부모가 지금 승격본인가(아니면 거절 — 전체 run 으로 갈아탈 때만 `--unrelated`, 사라질 `edits[]` 를 보여 주고), 계약 해시 = 지금 생성 C++.

*⑦ 사람이 고쳤는지 아는 법*

| 후보 | 놓치는 것 · 헛짚는 것 | 쓰임 |
| :--- | :--- | :--- |
| **파일 SHA256 + 파일 목록 — 판정(추천)** | 놓치는 것 없음. 내용 없이 다시 저장만 해도 다르다고 봄(안전한 쪽) | 승격본이 기록과 하나라도 다르면 **거절**. 에디터 없이 즉시, 커밋한 것은 LFS 값과 같아 git 으로도 확인된다 |
| revision(SHA1) | 폴더가 다르면 늘 다름 · 그래프 · 애니메이션 · 어휘 밖 값 · 텍스처를 못 봄 | 판정에 안 씀. patch 의 `base_revision` 검사는 지금처럼 run 안에서만 |
| 역추출 spec 비교 | 위와 같은 것을 못 봄 | 거절했을 때 **무엇이 달라졌나 알려 주는 데만**(위젯 · 속성 이름) |
| git 상태 | 커밋 전 승격본 · 커밋한 사람 수정을 못 가름 | 안 씀 |
| 저장 이벤트 훅(에디터 델리게이트) | 플러그인이 꺼진 에디터 · git 으로 들어온 수정을 못 봄 | 안 씀 — 필요한 때 한 번 재는 것이라 폴링이 아니고, 원천은 디스크 파일 하나다 |

사람이 고친 WBP 를 새 기준으로 받아들이기(역추출 → spec)는 이번에 안 만든다 — 거절하고 알려 주는 데까지.

*⑧ 베이스 클래스 · 공용 코드에 주는 영향*

- 게임 C++ · 생성 베이스 · 스텁 · WidgetMcp · Config **변경 0**. 계약이 안 바뀌므로 옛 WBP 도 그대로 컴파일된다.
- `run_pipeline` 은 입구 하나와 `_edit_pipeline` 갈래를 더한다(기존 `_pipeline` 은 그대로). `verify` 는 `edit.json` 이 있을 때만 12번째 게이트와 외형 나누기를 부른다 — 없으면 게이트 11개 · 출력이 지금과 같다. `finalize` · report 는 `parent_run_id` 값만. `diagnose` · `state_check` · `refine` · `style` 은 안 고친다(→ `golden` · `regress_set` 결과가 바뀔 이유가 없고, 그걸 확인하려고 돌린다).
- 새 파일: `stages/edit.py`(seed · patch 검사 · base) · `gen/edit_gate.py`(순수 계산) · `core/promotion.py`(기록 · 해시 · 사본 · 되돌리기) · `promote_screen.py`(status · record · plan · apply · revert · recover) · 스키마 둘(`edit` · `promotion`) · 시험.

*⑨ LLM 외형 라운드 코드(`style_review.rounds`) — 의견*

여기서 안 쓴다. 지시 해석을 나중에 하더라도 필요한 것은 '지시 → spec patch' 호출 하나이고, 막이는 '외형 op 만'(`guard_style_ops`)이 아니라 위 회귀 게이트다. LLM 호출 틀은 `stages/fix.py` 에 따로 있다. **걷는 쪽을 권한다 — 단 이번에는 안 건드리고 Phase 4 뒤 따로**(`run_pipeline._style_review` 의 라운드 반복 · `style.propose` · `guard_style_ops` · `snapshot` · `restore` · `replace_guard` · 프롬프트 2 · 설정 4줄 · 시험. `text_fit` · `compare` · `follow_text_boxes` · `rendered_boxes` 는 계속 쓴다).

*⑩ 첫 실증 · 검증 (승인 뒤)*

- **실증(추천): StatusHUD 의 `SelfHpText`(내 HP 숫자) 20 → 22 pt 를 재승격까지 하고 되돌려 바이트가 처음과 같은 것으로 끝낸다** — 게임 화면은 결국 그대로다. 이 수정은 글꼴 단일 원천 · 상자 밖으로 넘치는 글자 · 63 상태를 모두 지난다. 실제로 고치고 싶은 것이 있으면 그걸로 하고 남긴다. 후보 그림 = 스크래치 `uigen_p4/edit_candidates.png`.
- **사람이 고친 대상 거절:** 파일 판정은 pytest(임시 폴더의 1바이트 · 빠진 파일 · 더해진 파일), 실물은 재승격 직전에 승격본 사본 폴더를 흉내 낸 임시 대상으로 — 실제 승격본은 안 건드린다.
- pytest 전체 1회(새 시험 포함) · `golden.py check` · `regress_set` 새 라벨 `p4_11xx` ↔ `p2_1124`(`+ new` 0) · 실제 수정 run 1회 + 일부러 틀린 수정 하나(대상 밖까지 바뀌는 patch)가 막히는지 · 재승격 1회 · 그 상태에서 `AstralBreak.` 1회 · 되돌리기 1회(해시 같음). WidgetMcp C++ 를 안 고치므로 빌드 · `WidgetMcp.` 는 뺀다.
- **안 하는 것:** 지시 해석 · 주석 스크린샷 · `replace_asset` · 바인딩 바꾸기 · 사람이 고친 WBP 받아들이기 · CombatHUD 실증(묶음 소급과 ①의 실측까지만).

**쓰기 범위:** `Tools/uigen/**`(새 `promoted/` 포함) · 이 문서 · (승인되면) `.claude/skills/` 둘의 재승격 줄 · 재승격 실증 때 `Content/UI/HUD/StatusHUD/`(되돌려 처음과 같게). 측정이 남긴 일회성 = `work/_measure_p4/` + 스크래치 `uigen_p4`(끝에 목록 → 승인 → 휴지통).

**사용자에게 묻는 것:** 1 원천 보관(⑤ (가) 추천) · 2 재승격 방식과 안전 규칙 예외(⑥ (가) 추천) · 3 사람 수정 판정(⑦ 파일 SHA256 — 강제 옵션 없음 추천) · 4 첫 실증(⑩ — StatusHUD HP 숫자, 되돌려 끝내기 추천) · 5 `.claude/skills/` 둘의 '재승격은 사람이 손으로' 줄 고치기(추천: 승인). → **결정(11-24): 전부 추천안.** 구현은 컨텍스트 때문에 새 세션에서(인계 `uigen-phase4-impl-handoff.md`, 공유 노트 폴더 local_b686cc15…).

**Phase 4 결과 — 이어서 고치기 (2026-11-24 ~ 25 구현 · 검증 — 하위 세션, 커밋 `83f94e6`)**

승인된 설계대로 만들었고 끝 조건(수정 회귀 게이트 통과 · 재승격 · 되돌리기 1회)을 채웠다. **승격본 23개 파일은 처음과 바이트까지 같다**(커밋한 LFS 값 23/23 · `git status -- Content` 빈 줄). 게임 C++ · WidgetMcp · Config 변경 0 · 빌드 0 · LLM 0 · codex 0.

*만든 것*

| 무엇 | 어디 |
| :--- | :--- |
| 수정 run `run_pipeline.py --from <ScreenId \| run_id> --edit <patch.json>` | `stages/edit.py`(seed · patch 검사 · 계약 지킴이 · base ↔ 승격본 · 대상 상자) · `run_pipeline._edit_pipeline` |
| 12번째 게이트 `edit_regression` · 외형 나누기 · `edit.png` | `gen/edit_gate.py`(순수 계산) · `verify` 는 `edit.json` 이 있을 때만 부른다 |
| 승격 기록 · 묶음 · 사본 · 일지 | `core/promotion.py` · `promoted/CombatHUD`(묶음 31 파일 · 2.12 MB) · `promoted/StatusHUD`(42 파일 · 0.97 MB) |
| `promote_screen.py` status · record · plan · apply · revert · recover | 사람이 확인하고 부르는 명령 — 무인 파이프라인은 부르지 않는다 |
| 스키마 | `edit` · `promotion` 새로, `patch` 에 `affects` · `allow_overlap` |

`gen/diagnose` · `state_check` · `refine` · `style` 은 안 고쳤다.

*검증 [실측]*

| 무엇 | 결과 |
| :--- | :--- |
| pytest 전체 | 496 → **586 통과(실패 0, 15분 26초)** — 새 시험 90(게이트 계산 21 · 수정 run 38 · 승격 28 · 집계 1 · 스키마 2) |
| 정답 묶음 | **35/35 caught · 1/1 clean · 8/8 protected**(그대로) |
| 회귀 묶음 `p4_1124` ↔ `p2_1124`(14 입력, layer 부터) | `+ new` **0**, 파일 529개 중 **528개 바이트 같음**(남은 하나는 코드 파일 목록 `set.json`). 새 기준선 = `p4_1124` |
| 오프라인 — 설계 때 잰 아홉 수정을 새 게이트에 | 여덟 통과, `SelfHpText` 22 pt 만 `state_values` 에 7 px 남음(외곽선 여유까지 넣은 상자 기준 — 설계의 44 px 은 여유 2 px). 진단 결함 1 · 1 · 1 · 5 · 1 · 0 · 20 · 1 · 1 은 모두 '의도한 변경'으로 나뉨, 오류 0 |
| 소급 `record` | StatusHUD 그림 **64/64** · CombatHUD **20/20** 이 run 기록과 바이트까지 같음, 역추출 같음, `unsupported` 0 |
| 수정 run `R20261124_225244_StatusHUD`(HP 숫자 20 → 22 pt) | **12/12 통과**, 101초 = base 검증 35 · 승격본과 견주기 9(64/64 바이트 같음) · 고친 뒤 검증 51(진단 + 회귀 게이트). 대상 밖 spec · geometry · 픽셀 차 **0**, 바뀐 그림 63/64(최대 1,231 px), 넘친 글자(`state_values`)는 대상 끈 렌더로 풀림, 외형 = 의도한 변경 1(E9 크기) · 오류 0, `source_notes` = `text_ref_layout.yaml:6 pt 20 → 22`. 같은 수정을 먼저 돌린 `R20261124_224422_StatusHUD` 도 같은 결과 |
| 일부러 틀린 수정 ① `R20261124_225105_StatusHUD`(동료 2 줄을 내려 동료 3 줄과 겹침) | 실패 — `overlap`(Ally2Panel ↔ Ally3Panel 0.086), run 패키지 폐기 |
| 일부러 틀린 수정 ② `R20261124_224752_StatusHUD`(두 위젯을 바꾸면서 대상은 하나 — 도구가 대상을 좁게 잡은 흉내) | 실패 — `edit_regression`(spec 1곳 · 조정기가 바꾼 위젯이 대상 밖 · 그림 63/64 가 자리 밖에서 다름, 최대 241 px) + `appearance` 오류 1 |
| 사람이 고친 대상(사본 폴더 — 실제 승격본은 안 건드림) | 1 바이트 · 빠진 파일 · 더한 파일 셋 다 `plan` · `apply` 가 에디터를 띄우기 전에 `PROMOTED_CHANGED`. 그대로인 사본은 통과 |
| 재승격 `apply`(사용자가 `edit.png` · `compare.png` 를 보고 승인 11-25) | 100초(에디터 기동 82 포함), 승격본 ↔ run 역추출 같음 · 그림 64/64 바이트 같음, 기록 갱신(부모 `R20261124_130129_StatusHUD` · 쌓인 수정 1) |
| 그 상태에서 `AstralBreak.` | **60/60**(StatusHUD 두 시험 포함, 425초) |
| 되돌리기 `revert` | 승격본 13 파일 · 기록 · 묶음 모두 처음과 바이트 같음. 앞서 두 번은 에디터 프로세스가 남아 있어 `EDITOR_RUNNING` 으로 거절(아무것도 안 바꿈) |

*알아낸 것*

- **에디터는 종료 코드를 낸 뒤에도 프로세스가 몇 분 남을 수 있다** — 시험 60개 뒤 약 6분(메모리 3.8 → 1.4 GB 로 줄며). 그사이 `Toolchain.wait_exit` 는 '끝남'이라고 한다(종료 코드만 본다). `promote_screen` 은 프로세스가 목록에서 사라질 때까지 기다리게 했다. `codegen` 은 원래 `editor_processes` 를 따로 봐서 안전하게 멈춘다(`EDITOR_STILL_RUNNING`).
- **재승격 한 번에 13 파일이 전부 바뀐다**(합 385 KB) — 글자 크기 하나를 고쳐도 텍스처까지 새 패키지라 바이트가 다르다(그림은 같음). 작은 수정을 자주 올리면 LFS 가 그만큼 쌓인다. 바뀐 파일만 바꾸는 것은 엔진 밖에서 참조를 다시 잇는 일이라 이번에 안 했다.

*설계와 달라진 것*

1. `overlap` 의 'base 에도 있던 쌍 빼기'는 따로 만들지 않았다 — base 가 구조 게이트를 못 지나면 `BASE_FAILED` 로 멈추므로 그런 쌍이 없다. `allow_overlap` 은 spec 에 더해져 다음 수정으로 이어진다.
2. 견주는 그림에 `sample`(게임에 가까운 렌더)을 더했다 — 63 · 19장 → 64 · 20장.
3. 수정 run 의 finalize 는 `designer_hidden` 을 다시 매기지 않는다 — 게이트가 본 WBP 그대로 저장하고 대상 밖 위젯을 안 건드리려고.
4. 부모 규칙을 '쌓인 수정이 지금 기록의 `edits[]` 로 시작하고 그다음 줄의 부모가 지금 승격본'으로 했다 — 승격 안 한 수정 run 위에 이어 고친 것도 받고, 갈라진 것은 거절한다.
5. 거절을 더했다: 루트를 대상으로 함 · `bbox_intent` set · `base_revision` · 지금과 같은 값(`NO_EFFECT` — 에디터 앞에서).
6. '대상을 끈 렌더'의 base 쪽은 같은 WBP 를 잠깐 base spec 으로 되돌려 그리고 다시 적용한다(revision 이 같아야 통과). 대상을 끄면 다른 위젯이 움직이는 배치면 발자국을 안 쓴다 → **박스 안에서 상자 밖으로 넘치는 글자는 막힌다**(지금 두 화면에는 박스가 없다).
7. 외형 나누기 — 대상 글자만 재는 결함(stage text)은 상자 자리와 상관없이 의도한 변경, 그 밖은 결함 상자가 통째로 자리(+ 진단 창 7 × 7 의 절반 3 px) 안일 때만.
8. 지표 줄에 `edit_of` 를 더하고 에셋 줄은 안 쓴다(만들지 않았다). 집계(`summarize.py`)는 수정 run 을 표에 안 넣고 수만 적는다.
9. 첫 승격(기록이 없는 화면)은 지금처럼 `promote_widget` + `record` 다 — `apply` 는 재승격만.
10. 두 위젯을 바꾸면서 하나만 대상으로 적는 patch 는 쓸 수 없다(대상 = op 의 위젯). 그래서 ② 는 스크래치에서 대상 목록을 좁게 바꿔 돌렸다.

*안 한 것 · 못 본 것*

- 게임 안 눈 확인(되돌리고 끝내는 실증이라 화면은 그대로) · CombatHUD 수정 run · 실제 파일에서의 `recover` · `--unrelated`(둘 다 pytest 로만) · Development 구성(고친 C++ 가 없다) · `WidgetMcp.`(같은 까닭).
- 바꾼 자리 안의 모양은 여전히 사람 눈이다(④ 의 한계 그대로). 지시 해석 · `style_review` 라운드 걷기 · Phase 3 은 시작하지 않았다.
- **정리(11-25 사용자 승인 — 휴지통, 약 382 MB):** `work/_measure_p4`(99 MB) · `work/_promoted`(재승격 · 되돌리기 일지, 둘 다 `done`, 25 MB) · 시험 run 다섯 `R20261124_224422` · `224621` · `224752` · `225105` · `225244`(`work` 173 MB + `224422` · `225244` 의 `_AutoGen`) · `work/_regress/compare_p2_1124_vs_p4_1124` · 스크래치 `uigen_p4` · `uigen_p4b`(84 MB) — 위 숫자는 이 글로만 남는다. 남김: 승격본 run `R20261123_194019_CombatHUD` · `R20261124_130129_StatusHUD`(`work` · `_AutoGen`) · 기준선 `p4_1124`. 정리 뒤 `promote_screen.py status` 두 화면 다 기록과 같음.

**Phase 3 설계 — 조작 화면 (2026-11-25 작성 · 같은 날 사용자 승인 'HUD까지 확정' — 하위 세션. 조사 · 작은 시험 · 설계까지, 구현은 단계마다 새 세션)**

읽은 근거 = 아래 [소스](줄 번호는 HEAD `83f94e6` · 엔진 5.7.4)와 작은 시험 [실측](`work/_measure_p3/`, 저장소 무변경, codex 3회). 에디터는 띄우지 않았다.

*작은 시험 — 버튼 상태 그림의 정답을 어디서 받나 (상한 codex 4회로 미리 정함, 쓴 것 3회)*

본 그림 1장('검은 날' 느낌을 `--style-ref` 로 — 파티 줄 4 · 목적지 버튼 · 작은 버튼 2, 글자 없음 · 진짜 알파)을 만들고 세 길을 견줬다.

| 길 | codex | 버튼 윤곽 어긋남(기본 그림 대비, px) | 안 바꿔야 할 자리 | 상태 구별(버튼 안 평균 ΔE00 — 올림 · 누름 · 선택) |
| :--- | :---: | :--- | :--- | :--- |
| (가) 상태별 컨셉 판 — 본 그림을 편집해 버튼만 '올림'으로 | 상태마다 1 | 최대 2.6 | **버튼 밖이 통째로 바뀜** — 회색 바탕 ΔE00 중앙 4.66 · 95 % 25.6 · 5 를 넘는 픽셀 44 %(밝은 바탕 중앙 9.5 · 96 %). 파티 줄의 옅어지는 끝이 둥근 불투명 끝으로 다시 그려짐 | — |
| (나) 상태 시트 — 기본 버튼 2종을 5줄 복제한 판을 편집 | 1 | 최대 3.9(오른쪽 끝) · '그대로 두라'고 한 첫 줄도 8 ~ 16 % 픽셀이 ΔE00 5 초과 | (버튼만 있음) | 6.9 ~ 8.0 · 2.6 ~ 2.9 · 8.0 ~ 8.5 |
| **(다) 결정적 처리 — 기본 버튼 픽셀의 함수** | **0** | **0(정의)** — 알파를 안 바꾼다(비활성만 × 0.5) | 해당 없음 | 8.9 · 3.3 · 9.4(선택 + 올림 16.6 · 비활성 12.2) |

→ **(다)를 쓴다(추천).** 정답이 '기본 그림 + 식'이라 엔진 렌더를 픽셀로 견줄 수 있고, 사람이 승인한 본 그림의 윤곽이 상태마다 흔들리지 않는다. 구별되는 정도는 codex 시트와 같다.
(가)는 본 그림의 정답을 깨므로 버리고, (나)의 그림은 식의 색 · 세기를 고를 때 눈 참고로만 썼다. 식(`preview.py`): 올림 = 판을 따뜻하게 9 ~ 16 % 밝힘 + 선 · 칼날을 상아색으로 ·
누름 = 판 × 0.5 + 선 어둡게 + 글자 1 px 아래 · 비활성 = 무채색 + 알파 × 0.5(글자는 Slate 가 알파 × 0.45) · **선택 = 어느 상태 위에나 얹는 투명 덮개**(왼쪽에서 옅어지는 상아색 30 % + 상아색 선) — 구워서 선택 · 선택 + 올림 · 선택 + 누름 그림이 된다.
초점(게임패드 · 키보드) = 올림 그림을 같이 쓴다. 식의 값은 프로젝트 공용 테마 하나(사람이 승인하는 미리보기 1장과 함께) — 눈으로 고르는 값이지 문턱이 아니다.

*① 첫 화면 — 허브 준비 화면 `HubReady` (추천)*

| 자리 | 값 · 동작 | 원천 [소스] | 지금 있나 |
| :--- | :--- | :--- | :--- |
| 파티 4줄(고정) | 이름 | `APlayerState::GetPlayerName` + `AAstralGameState::OnPlayerRosterChanged` | 있음(StatusHUD 가 씀) |
| | 방장 표시(초승달) | `AAstralGameState::GetPartyLeader()` — PlayerId 최소, 클라이언트도 같은 값 | 있음 |
| | 준비됨 | `AAstralPlayerState::bIsReady` | 값 있음 · **통지 없음** → RepNotify + 델리게이트 |
| 목적지 버튼(방장만 누름) | 고를 수 있는 레이드 | 허용 목록 — 지금은 `AAstralGameMode::RaidMapNames`(서버 전용) → **`AAstralHubGameState` 로 옮김**(아래) | 1개(`RaidMap`) |
| | 골라짐(선택 모양) | `AAstralHubGameState::SelectedRaid` | 값 있음 · **통지 없음** |
| 준비 버튼 | 내 준비 켜고 끔(선택 모양 = 내가 준비됨) | `ServerSetReady` | 있음 |
| 출정 버튼(방장만) | 전원 준비 + 목적지 → 이동 | `ServerStartRaid` | 있음 |
| 이유 한 줄 | 왜 못 누르나 · 서버가 거절한 까닭 | 새 순수 함수(③) | 규칙은 있음(흩어져 있음) |
| 고정 글자 | '출정 준비' · '목적지' · '준비 완료' · '닫기' 안내 | — | — |

- **안 넣는 것:** 캐릭터 · 무기 · 룬 고르기(M7 로드아웃 — 표시 이름 FText 도 없다), 레이드 브리핑 · 보상(M6), 초상화. 시스템 없는 값은 만들지 않는다.
- **M6 과의 관계:** 이 화면은 '준비 · 목적지 · 출정' **요청의 정식 화면**이고, 여는 방법(NPC 와 대화 · 브리핑)과 퀘스트 데이터는 M6 이 가져간다. M6 은 여는 함수 호출 자리와 목적지 목록의 원천만 바꾸면 된다. 콘솔 명령(`SetReady` · `SelectRaid` · `StartRaid`)은 시험이 쓰므로 그대로 둔다.
- **목적지 목록:** 화면이 클라이언트에서 읽어야 하므로 게임모드(서버 전용)가 아니라 **문맥(월드) 정책의 소유자인 GameState** 가 갖는 것이 이 프로젝트 규칙이다(`AstralGameState.h:11` — 장비 정책 · 공통 어빌리티와 같은 자리). `AAstralHubGameState::RaidDestinations {MapName, DisplayName}`(편집 기본값 — 복제할 것 없음) 하나가 허용 목록이자 보이는 이름의 단일 원천이고, 서버 검사도 이것을 본다.
  `IsRaidMapAllowed` · `RaidMapNames` 를 쓰는 곳은 컨트롤러의 RPC 하나뿐이고 BP 에 저장된 값이 없다 [실측]. 글 '봉인된 유적'은 game-plan 7-5 의 콘셉트 이름(기획 요소 — 잠정). 프로젝트의 정의 애셋 꼴(`UPrimaryDataAsset`)로 올리는 것은 M6 퀘스트 구조의 몫 — 시작하지 않는다.

*② 파이프라인 — 칸 · 버튼 · 동작의 계약*

- **칸도 하나의 화면:** 파이프라인은 run 하나 = spec 하나 = 화면 하나 = 승격 폴더 하나로 짜여 있다(`run_pipeline` · `core/promotion` · 수정 run 전부). 한 run 에 spec 둘을 넣으면 이 전제가 깨지므로 칸을 자기 run · 자기 승격본으로 먼저 만들고, 큰 화면은 새 위젯 타입 `UserWidget {class, props}` 로 **승격된 칸만** 넣는다.
  칸의 컨셉 = 승인한 그림에서 그 자리만 `--cut-from`(codex 0), 캔버스 = 칸 크기(`profiles/cell.yaml`). 진단은 칸을 '그 칸의 spec + 텍스처로 합성한 그림 한 장'으로 본다.
- **칸은 두 종류다:**

  | 종류 | 예 | C++ | 두는 곳 |
  | :--- | :--- | :--- | :--- |
  | 공용 부품 | 버튼 모양 둘(`ButtonLarge` · `ButtonSmall`) | **손으로 쓴 `UAstralButtonBase` 하나** — 모양마다 클래스를 만들지 않는다(`screens.yaml parent`, codegen 없음 · 바인딩은 리플렉션으로 대조) | `/Game/UI/Common/` |
  | 화면 전용 | 파티 줄 `HubMemberRow` | 생성 베이스 + 스텁(지금 규칙 그대로) | `/Game/UI/Screens/HubReady…/` |

- **버튼 = CommonButton:** `UAstralButtonBase : UCommonButtonBase`(Lyra `ULyraButtonBase` 꼴 — 글자 값 `ButtonText` 하나). 상태 그림 일곱(기본 · 올림 · 누름 · 선택 · 선택 + 올림 · 선택 + 누름 · 비활성)은 `UCommonButtonStyle` 파생 클래스 애셋이 담는다(`BuildStyles` 가 클래스 기본 객체만 읽고 가상 함수가 아니다 [소스] `CommonButtonBase.cpp:1900`) → WidgetMcp 새 도구 `create_button_style`.
  **버튼이 스스로 선택을 바꾸지 않게:** 누르면 `SetIsSelected(!bSelected)` 를 부르지만(`:1466-1493`) `bSelectable` 이 꺼져 있으면 아무 일도 없다(`:1031`). 선택 모양은 원천이 바뀐 통지에서 우리 클래스가 `SetSelectedInternal`(protected `CommonButtonBase.h:741`) 로만 바꾼다. `bInteractableWhenSelected` 는 켠다(준비를 다시 눌러 풀어야 하므로).
- **상태 그림의 식은 프로젝트 공용 테마 하나:** `Tools/uigen/config/theme_blade.yaml`(식 값 + 공용 글자색 · 외곽선). 화면마다 두면 버튼이 화면마다 달라진다. 텍스처는 refine 이 기본 그림에서 만든다(provenance `derived`, 원본 sha256 · 테마 해시 기록). LLM 은 기본 그림만 정한다.
- **동작의 계약:** 데이터 종류 **`action`**(위젯 = 버튼 칸). 생성 베이스: `UPROPERTY(BindWidget) UAstralButtonBase* ReadyButton` · `NativeOnInitialized` 에서 `OnClicked()` 에 묶음 · **`virtual void HandleReadyClicked() {}`**(스텁이 재정의) · `SetReadyEnabled(bool)` · `selectable` 이면 `SetReadySelected(bool)`. 생성 코드는 누름에 자기 모양을 바꾸지 않는다 — 요청만.
- **기존 두 화면의 계약 해시를 안 바꾼다.** 지금 `generator_id()` 는 `SETTERS` 표와 템플릿 4개 **전체**를 해시해(`cppgen.py:180-187`, 지금 값 `1:49a7a94ed467`) 한 줄만 더해도 두 화면의 해시가 바뀌고 수정 run 이 `EDIT_CONTRACT_CHANGED` 로 막힌다.
  → 새 조각 · 새 템플릿은 **그 계약이 쓸 때만** 해시에 넣는다(`screens.yaml base` 도 기본값이 아닐 때만). 시험 = 커밋된 두 헤더의 해시를 그대로 재현.
- **가리는 위젯 없음(새 구조 규칙):** UMG Image · TextBlock 의 기본 보이기는 `visible`(입력을 먹음)이라, 버튼 위에 놓인 장식이 클릭을 가로챈다. `menu` 프로필은 버튼이 아닌 잎을 `hit_test_invisible`, 패널을 `self_hit_test_invisible` 로 **코드가** 정하고, 버튼보다 뒤에 그려지며 겹치는 `visible` 위젯이 있으면 게이트에서 실패.
- **긴 글자:** spec 글자에 `overflow: ellipsis`(기본은 지금처럼 없음), inputs 에 `long_sample`. 상태 렌더 하나(`state_long`)를 더해 긴 값이 글자 칸 밖으로 안 나가고 이웃 글자와 안 겹치는지 본다.
- **메뉴 프로필** `profiles/menu.yaml`: 배경 투명(가운데가 열린 화면) · 게이트 값은 hud 와 같게 시작 · 입력 규칙 켬 · analyze 에 줄 짧은 주의(HUD 문구 대신).
- **WidgetMcp C++:** 위젯 타입 `UserWidget`(승격 경로 아래 클래스만 · 허용한 인스턴스 속성만) · `create_button_style` · 글자 `overflow` · `render_widget` 덮어쓰기 `enabled` · `button: hovered | pressed | selected`(칸 안까지). 역추출 · 왕복 · 시험 포함.

*③ 게임 쪽 — 화면의 주인 · 값 · 요청*

```text
[여는 쪽]  키(UI 액션 태그) 또는 M6 NPC → UAstralUISubsystem(LocalPlayer) → 루트 레이아웃의 Menu 층에 화면을 밀어 넣음
[동작]     버튼 → UAstralHubReadyWidget(스텁)::Handle…Clicked → AAstralPlayerController::Server…(있는 RPC) → 서버 검사 → 복제 값 → RepNotify · 델리게이트 → setter
                                                                            └─ 거절 → ClientLobbyRequestDenied(이유) → 이유 한 줄 3초
```

- **화면의 주인 = LocalPlayer:** 지금 HUD 둘은 컨트롤러가 클래스 값과 인스턴스를 하나씩 들고 있다(`AstralPlayerController.h:108-122`). 화면이 늘 때마다(M5 보스 · M6 목표 · 결과 · M7 로드아웃 · 룬 · 트리) 컨트롤러가 커지는 꼴이라 새 화면을 거기에 더하지 않는다.
  새 `UAstralUISubsystem : ULocalPlayerSubsystem` 이 루트 레이아웃을 갖는다(`PlayerControllerChanged` 에서 만들고 월드가 바뀌면 다시 만듦 — 프로젝트의 `UAstralLocalPlayer::OnPlayerControllerChanged` 와 같은 시점).
  `UAstralRootLayout : UCommonActivatableWidget` = 늘 켜진 Game 입력 설정 + 층 셋(HUD · Menu 스택 · Modal 스택 — Lyra 의 층을 줄인 것). 늘 켜진 Game 설정이 필요한 까닭 — 마지막 화면이 닫히면 라우터가 입력 설정을 되돌리지 않는다 [소스] `CommonUIActionRouterBase.cpp:948-966`.
- **어느 맵에 무엇이 뜨나 = GameState 의 편집 기본값:** 문맥 정책의 소유자 규칙대로 `AAstralGameState` 에 `ContextHUDWidgets`(층 HUD) · `ContextScreens {UI 액션 태그 → 화면 클래스}` 를 둔다. 위젯이 GameState 종류를 캐스트해 스스로 숨는 일(StatusHUD)이 없어진다. Lyra 의 Experience · AddWidgets 를 프로젝트 크기로 줄인 것.
- **틀과 입력 = CommonUI:** 화면 베이스 `UAstralActivatableWidget : UCommonActivatableWidget`(입력 설정 열거형 — Lyra 꼴, 생성 베이스의 부모). 메뉴 모드에서 게임 입력이 막히고(`:647 · 1463` `BlockGameInput`) 이동 · 시점 막기 · 눌린 키 비우기 · 커서 · 첫 초점과 되돌리기는 라우터가 한다(`:1809-1830`). 패드 초점은 가상 커서가 올림으로 만든다(`CommonAnalogCursor.cpp:150-236`).
- **여는 키 · 닫는 키 = UI 액션 태그:** `UI.Action.HubReady`(Tab · 게임패드 Special_Left) · `UI.Action.Back`(Esc · 게임패드 B)을 `DefaultInput.ini [/Script/CommonUI.CommonUIInputSettings]` 에 두고 `RegisterUIActionBinding` 한다(Lyra `UI.Action.Escape` 와 같은 길). 라우터가 가장 안쪽 켜진 화면부터 준다(`UIActionRouterTypes.cpp:1005-1019`) → 화면이 겹쳐도 맨 위 것만 닫힌다. 입력 애셋 · 폰의 InputConfig · `BindKey`(게임에 0곳)를 안 쓴다.
- **규칙의 단일 원천:** 지금 거절 규칙은 RPC 안에 흩어져 로그만 남긴다(`AstralPlayerController.cpp:233-289`). 순수 함수 `AstralLobby::CheckReady / CheckSelect / CheckStart(스냅숏) → EAstralLobbyDenial{None, NotInHub, NotLeader, RaidNotAllowed, NoRaidSelected, NotAllReady}`(월드 없이 시험 — `AstralParty` 와 같은 자리)로 모으고,
  **서버 RPC 와 화면(버튼 켜고 끔 · 이유 글)이 같은 함수**를 쓴다. 화면 쪽은 표시일 뿐 — 최종 판정은 서버. 지금 로그 문구는 시험이 세므로 그대로. `ServerSetReady` 는 지금 아무 맵에서나 받으므로 `CheckReady` 로 허브에서만.
  **명단 거르기도 하나로:** 방장 · 동료 규칙은 봇 · 관전자를 빼는데 `AreAllPlayersReady` 는 전원을 센다(관전자가 하나 있으면 출정할 수 없다 — 지금 있는 문제). 스냅숏을 만들 때 같은 거르기를 쓴다.
- **거절이 보이는 때:** 정상이면 못 누르는 버튼이 꺼져 있고 이유 줄이 그 까닭을 말한다. 서버 거절은 경합(출정을 누른 순간 누가 준비를 풂)에서만 나고, 같은 줄에 3초 — 그 뒤 지금 상태의 이유로 돌아간다.
- **통지:** `bIsReady` · `SelectedRaid` 를 `ReplicatedUsing` + C++ 델리게이트(`OnReadyChanged` · `OnSelectedRaidChanged`). 리슨 호스트에는 RepNotify 가 없으므로 서버 쪽 set 에서도 방송(로드아웃과 같은 모양). 폴링 없음.
- **방장 · 아닌 사람:** 목적지 · 출정은 방장만 켜짐, 아닌 사람은 꺼진 모양 + '방장이 고른다' 이유. 방장이 나가면 명단 통지로 다음 사람의 버튼이 켜진다(인계 코드 없음).
- **Dedicated · 리슨 · 늦은 입장:** 넷 모드 분기 없음. 늦게 온 사람은 첫 복제 값을 만들 때 읽고(기본값과 다르면 RepNotify 도 남), GameState 가 늦으면 `GameStateSetEvent`(StatusHUD 와 같은 틀).
- **기존 HUD 둘도 같은 층으로(11-25 확정):** WBP · 계약 · 승격본은 그대로 두고 **만드는 자리만** 컨트롤러 → 루트 레이아웃의 HUD 층으로 옮긴다. 안 옮기면 화면을 띄우는 길이 둘이 남는다. 시험 넷이 쓰는 `GetCombatHUDWidget()` · `GetStatusHUDWidget()` 은 서브시스템에 묻는 함수로 남긴다.
- **바뀌는 설정:** uproject 에 CommonUI 켜기 · `Build.cs` CommonUI · CommonInput(+ Slate · SlateCore) · `DefaultEngine.ini` `GameViewportClientClassName=/Script/CommonUI.CommonGameViewportClient`(지금은 엔진 기본값) · `DefaultInput.ini` UI 액션.

*④ 검증*

- **버튼 상태 렌더:** `state_requests` 에 버튼마다 올림 · 누름 · 선택 · 선택 + 올림 · 선택 + 누름 · 비활성을 더한다 — 묶음 렌더 그대로. 엔진은 **진짜 버튼 상태**를 쓴다(CommonButton 안쪽도 `UButton` → 오프스크린 위젯에 `OnMouseEnter` · `OnMouseButtonDown` · `SetIsEnabled` [소스] `SButton.cpp:176 · 208 · 221`).
  검사 `button_state`(E8): 버튼 밖 = 컨셉 상태와 같음 · 안 = 만든 그림을 얹은 값과 국소 ΔE · 상태끼리 구별됨. **먼저 일부러 틀린 값**(올림 ↔ 누름 바꿈 · 비활성 빠짐 · 여백 밀림 · 덮어쓰기가 안 먹음)이 잡히는지 시험에서 본다. `compare.png` 상태 띠에 버튼 칸.
- **눌렀을 때의 동작(PIE — 사람 손 없이):** `AstralBreak.Net.HubReady.ListenPIE` · `.DedicatedPIE`(2인 + 늦은 입장 1). 실제 Slate 경로로 — 버튼 가운데 좌표의 히트 테스트 길이 그 버튼까지 닿는지 보고, 마우스 눌림 · 뗌을 흘린다.
  ① 열면 커서 · 입력 모드 · 첫 초점, 게임 이동이 막힘 ② 준비 클릭 → 서버 값 → 두 자리의 줄 ③ 방장 아닌 사람의 목적지 · 출정은 꺼져 있고 눌러도 요청이 안 나감 ④ 방장 목적지 클릭 → 두 자리 선택 모양 ⑤ 준비 안 된 채 서버에 직접 출정 → 거절 → 이유 줄 → 3초 뒤 복귀 ⑥ 늦은 입장이 지금 상태를 봄 ⑦ 방장이 나가면 다음 사람 버튼이 켜짐 ⑧ 게임패드 방향 + A 로 준비 ⑨ 전원 준비 → 출정 클릭 → RaidMap, 화면이 닫히고 입력 모드가 돌아옴 ⑩ 닫기 액션은 맨 위 화면만 닫음.
- 순수 함수 시험 `AstralBreak.Lobby.Rules`. **사람 몫 = 눈 확인과 조작감뿐.**
- 끝 검증(필수만): pytest · `golden.py check` · `regress_set`(기준선 `p4_1124`, `+ new` 0) · 빌드 2 구성 · `WidgetMcp.` · `AstralBreak.` 1회. 상태 묶음 렌더는 새 화면에서 묶음 ↔ 한 장씩 바이트를 한 번 전부 견줘 기록.

*⑤ 승격 · 한 명령 · 작은 것 둘*

- 승격 경로 둘 — `+WidgetPromotionPaths=/Game/UI/Common/`(공용 부품) · `/Game/UI/Screens/`(화면). 코드 `UI/Foundation/`(손으로 쓴 공용 클래스) · `UI/Screens/`(생성 · 스텁). 첫 승격은 `promote_widget` + `promote_screen.py record`(Phase 4 규칙 그대로). **공용 칸을 다시 승격하면 그 칸을 쓰는 화면도 다시 검증**한다 — 기록에 '쓰는 화면' 목록을 두고 `plan` 이 보여 준다.
- **한 명령:** `Tools/uigen/make_screen.py <fixture> [--text "…"] [--candidates 2]` — 후보까지 만들고 **멈춰 사람이 고른다** → `--pick N` 이 참고판 → run → 요약까지. 후보 고르기는 자동으로 하지 않는다.
- **절대 경로:** 쓰는 쪽(normalize · diagnose)을 저장소 상대 경로로, 읽는 쪽(`edit.source_notes`)은 상대 경로 + 옛 절대 경로(없는 드라이브면 `Tools/uigen/` 뒤로 다시 찾기)를 받게. **이미 기록한 두 화면의 묶음 4 파일(`normalize.json` 2 · `diagnosis.json` 2, 경로 6 곳)은 안 고친다(추천)** — 승격 때의 기록이고 해시가 걸려 있다. 다음 재승격 때 새 판으로 자연히 바뀐다.

*판단을 바꾼 기록 (2026-11-25 — 사용자 질문 'commonUI 를 왜 안 써' · '지금 구조에 부합하면 다 하자' · '잘못 판단한 것 없나'를 받아 다시 따짐)*

첫 안은 '첫 화면 하나를 가장 적은 일로'를 잣대로 골랐다. 이 프로젝트는 Lyra 구조를 따르고 M5 ~ M7 에 화면이 이어지므로 잣대가 틀렸다.

| # | 첫 안 | 무엇이 잘못됐나 | 고친 안 |
| :-- | :--- | :--- | :--- |
| 1 | 화면 틀을 손으로 짬 · CommonUI 안 씀 | Lyra 와 다르고, 라우터에 있는 것을 다시 만듦 | CommonUI 틀 |
| 2 | 하위 WBP 는 M7 로 | 나중에 하면 계약 · 스텁 · 승격을 다시 함. '한 run 에 spec 둘'로만 생각해 크기를 크게 봄 | 칸도 하나의 화면 — 지금 |
| 3 | 버튼은 `UButton` | 근거가 '하위 WBP 가 필요해서'였는데 2 를 바꾸고도 다시 안 봄 | CommonButton |
| 4 | 화면의 주인 = 컨트롤러(의 컴포넌트) | 화면마다 컨트롤러가 커짐. 맵별 화면을 위젯이 캐스트로 가림 | LocalPlayer 서브시스템 + 층, 맵별 목록은 GameState |
| 5 | 여는 키 `BindKey`, 닫는 키는 위젯이 직접 | 태그 입력 규칙 밖 · 화면이 겹치면 맨 위만 닫는 것을 보장 못 함 | UI 액션 태그 |
| 6 | 목적지 목록 = 게임모드(클라이언트가 게임모드 기본 객체를 읽음) | 문맥 정책의 소유자는 GameState 라는 프로젝트 규칙과 다름 | `AAstralHubGameState` |
| 7 | 상태 그림의 식을 화면마다 | 버튼 모양이 화면마다 갈라짐 | 공용 테마 하나 |
| 8 | 버튼 칸마다 생성 클래스 | 글자 하나짜리 클래스가 모양 수만큼 생김 | 손으로 쓴 버튼 베이스 하나 + 애셋 |
| 9 | 승격 경로 하나(`/Game/UI/Screens/`) | 공용 부품이 화면 폴더에 섞임 | Common · Screens 둘 |

- **다시 따져도 그대로인 것:** 상태 그림 = 기본 그림 + 식(작은 시험) · RepNotify + 델리게이트(폴링 없음) · 규칙은 순수 함수, 판정은 서버 · 예측 없음 · 기존 두 화면의 계약 해시 유지 · 가리는 위젯 규칙 · 옛 묶음 안 고침 · 후보는 사람이 고름.
- **알고 미루는 것:** 버튼은 고정 크기 그림이다 — 크기가 다른 버튼이 여럿 필요해지면 9-slice 로(지금 두 모양이면 충분). 글자는 WBP 에 문자열로 들어가 번역 표를 안 탄다(`WidgetMcpSpec.cpp:1236` — 기존 화면도 같음). MVVM(ViewModel)은 생성 setter 방식과 겹쳐 안 쓴다.
- **안 돌려 본 것(3-1 첫 작업에서 잰다):** CommonUI 뷰포트 클라이언트가 기존 시험 60개에 주는 영향 · 한 프로세스 다인 PIE 에서 로컬 플레이어마다 생기는 입력 처리기의 간섭 · 로컬 플레이어 없는 오프스크린 렌더에서의 CommonButton(소스로는 입력 서브시스템이 없으면 건너뜀) · 키보드 방향키 초점의 올림 모양. 나쁘면 `UButton` + 손으로 짠 틀로 물러난다.

*규모와 단계 — 넷(11-25 사용자 확정 '네 단계로', 단계마다 새 세션 하나 · 더 잘게 나누지 않음)*

| 단계 | 몫 | 추정 | 끝 |
| :--- | :--- | ---: | :--- |
| **3-1 화면 체계(게임)** | **CommonUI 켜고 위 '안 돌려 본 것'부터** · `UAstralUISubsystem` · `UAstralRootLayout` · `UAstralActivatableWidget` · GameState 의 맵별 목록 · UI 액션 태그(뒤로) · 기존 HUD 둘 옮기기 · 시험용 화면(C++)으로 여닫기 PIE 시험 | 약 1,300 줄 | 기존 시험 새 실패 0(HUD 시험 포함) · 여닫기 시험 통과 · 기존 HUD 눈 확인. 파이프라인 · WidgetMcp 는 안 고침 |
| **3-2 칸과 버튼(파이프라인)** | `UserWidget` 타입 · `cell` 프로필 · `UAstralButtonBase` · 버튼 스타일 애셋 · 공용 테마 · 상태 그림 · 버튼 상태 렌더 검사 · 승격 경로 · 컨셉 후보(codex ≤ 4) 승인 · 버튼 칸 둘 | 약 2,600 줄(가장 큼) | 버튼 칸 2 개 무인 통과 → 사람 승인 → 승격, 회귀 `+ new` 0. 모자라면 칸(파티 줄 칸으로 검증)과 버튼 사이에서 끊는다 |
| **3-3 화면**(완료 11-25 — 'Phase 3-3 결과') | action 계약 · 가리는 위젯 · 긴 글자 · 메뉴 프로필 · 한 명령 · 상대 경로 · 파티 줄 칸 · `HubReady` run | 약 1,700 줄 | 칸 · 화면 무인 1회씩 통과, 사람이 `compare.png` 를 봄, 회귀 `+ new` 0 |
| **3-4 게임 연결** | 규칙 함수 · 통지 · 거절 · 목적지 목록 · 스텁 · 여는 액션 · PIE 시험 · 승격 · 끝 검증 · 결과 절 | 약 1,900 줄 | 게임에서 조작 동작, 눈 확인 · 조작감 → Phase 3 끝 조건 |

- **나눈 근거:** 지난 커밋에서 센 줄 수 — Phase 4 구현(파이썬 1,837 + 시험 1,107)이 한 세션을 꽉 채웠고, StatusHUD 는 도중에 새 세션으로 넘어갔다. 처음의 세 단계는 3-1 이 3,000 줄을 넘고 3-3 이 2,400 줄로 컸다(줄 수는 추정).
- **3-1 을 앞에 떼어 낸 까닭:** 가장 큰 위험(CommonUI)을 버리는 시험 코드가 아니라 실제로 쓸 구조로 먼저 본다. 나쁘면 파이프라인을 고치기 전에 방향을 바꾼다. 게임 C++ 과 파이프라인을 나눠 깨진 쪽을 가리기 쉽다.

**쓰기 범위:** `Tools/uigen/**` · `Plugins/WidgetMcp/**` · `Source/AstralBreak/UI/**` · `GameModes/{AstralGameState, AstralHubGameState, AstralRaidGameState(목록 기본값만), AstralGameMode, AstralPartyStatics 곁 새 파일}` · `Player/{AstralPlayerController, AstralPlayerState, AstralLocalPlayer}` · 시험 · `Config/{DefaultEngine, DefaultInput}.ini` · `AstralBreak.uproject` · `AstralBreak.Build.cs` · 승격 때 `Content/UI/{Common, Screens}/` · 이 문서. 허브 맵 · BP · 입력 애셋은 안 고친다.

**사용자에게 묻는 것:** 1 첫 화면과 담을 것(①) · 2 버튼 상태 그림 = 기본 그림 + 식 · 3 칸도 하나의 화면 + CommonButton(②) · 4 화면의 주인 = LocalPlayer 서브시스템, 맵별 목록 = GameState, 틀 = CommonUI(③) · 5 기존 HUD 둘도 같은 층으로 옮길지(③ — 추천: 옮김) · 6 거절과 규칙의 단일 원천 · 목적지 이름(잠정 글) · 7 승격 경로 둘과 옛 묶음의 절대 경로(⑤) · 8 단계 나누기. → **결정(11-25): 전부 추천안 — 기존 HUD 둘도 같은 층으로 옮긴다. 단계는 넷(3-1 화면 체계 → 3-2 칸과 버튼 → 3-3 화면 → 3-4 게임 연결).** 3-1 인계 `uigen-phase3-1-handoff.md`(공유 노트 폴더 local_b686cc15…).

**Phase 3-1 결과 — 화면 체계(게임) (2026-11-25, 하위 세션 · 구현 · 검증 완료 · 사람 눈 확인 통과 · 커밋 `06c800d`)**

`Tools/uigen` · `Plugins/WidgetMcp` · 승격본 · 생성 코드 · 맵 · BP · 입력 애셋은 안 고쳤다.

*1번 — CommonUI 만 켜고 먼저 잰 것 (설계 '안 돌려 본 것' 넷 — 나쁜 것 없음, 물러나지 않음)*

| 물음 | 측정 |
| :--- | :--- |
| 켜기만 한 상태(uproject · Build.cs · `GameViewportClientClassName`)에서 기존 시험 | **60/60**(421초), 라우터 · CommonInput · CommonUI 경고 · 오류 0, ensure 0 |
| 로컬 플레이어 없는 오프스크린의 CommonButton(3-2 의 전제) | **그려진다** — 편집기 월드 · 소유 플레이어 없음 · `FWidgetRenderer` 로 C++ 버튼을 자식으로 둔 화면의 가운데 픽셀: 기본 `FF0000` · 올림 `00FF00` · 누름 `0000FF` · 선택 `FFFF00` · 선택 + 올림 `00FFFF` · 비활성 `FFFFFF`(준 색 그대로), 버튼 밖 0. 선택 + 누름은 안 쟀다 |
| ↑ 의 함정 | 안쪽 위젯(`UCommonButtonInternalBase`)의 Slate 는 **SBox** 이고 진짜 버튼 `SCommonButton` 은 그 자식이다. SBox 에 마우스 이벤트를 보내면 오류 없이 아무 일도 없다(첫 측정이 그렇게 틀렸다) → 3-2 `render_widget` 의 덮어쓰기가 받을 자리 |
| 한 프로세스 다인 PIE 에서 자리끼리의 간섭 | 없음(A 의 메뉴가 떠 있는 동안 B 의 입력 · 폰 그대로). 단 **편집기에서만** 라우터는 초점이 있는 창의 입력 설정만 바꾼다(`UIActionRouterTypes.cpp` `IsViewportWindowInFocusPath`) — 초점이 없던 자리는 설정이 안 걸린 채(= 게임 · 메뉴 다 받음) 시작하고, 그 창에서 화면을 여닫으면 걸린다 |
| 키보드 방향키 초점의 모양 | **올림이 아니다** — 초점은 안쪽 `SCommonButton` 에 가지만(cause = Navigation) `IsHovered` 거짓. 엔진 초점 테두리는 소스로는 그려지는 조건(`RenderFocusRule = NavigationOnly`)이고 픽셀로는 안 봤다. 설계 '초점 = 올림 그림'은 3-2 의 `UAstralButtonBase` 가 스스로 입혀야 한다 |

*만든 것*

| 파일 | 내용 |
| :--- | :--- |
| `UI/Foundation/AstralActivatableWidget.*` | `UAstralActivatableWidget : UCommonActivatableWidget` — 입력 설정 열거형(Lyra 꼴), 뒤로 액션(`UI.Action.Back`) 묶음 → 닫기. 조작 화면 생성 베이스의 부모(3-3) |
| `UI/Foundation/AstralRootLayout.*` | 늘 켜진 Game 설정 + 층: HUD(클릭 안 받음) · Debug · Menu 스택 · Modal 스택. 층은 코드로 짓는다(WBP 없음) |
| `UI/Foundation/AstralUISubsystem.*` | `ULocalPlayerSubsystem` — 레이아웃을 만들고 걷음, `OpenScreen(클래스, 층)` · `FindHUDWidget` · `ShowDebugWidget` |
| `UI/Foundation/AstralUITypes.h` · `AstralUIGameplayTags.*` | 층 열거형 · `FAstralContextScreen {액션 태그, 화면}` · `UI.Action.Back` |
| `GameModes/AstralGameState.h` · `AstralRaidGameState.cpp` | `ContextHUDWidgets` · `ContextScreens`(편집 기본값 · 복제 없음), 레이드 기본값에 HUD 둘(전과 같은 순서) |
| `Player/AstralPlayerController.*` | HUD 클래스 값 · 인스턴스 · `EnsureHUDWidget` 을 걷음. `GetCombatHUDWidget` · `GetStatusHUDWidget` 은 서브시스템에 묻는 함수로 |
| `UI/HUD/AstralStatusHUDWidget.cpp`(사람 스텁) | GameState 를 캐스트해 스스로 숨던 줄을 걷음 — 어느 맵에 뜨는가는 목록이 정한다 |
| `Config/DefaultInput.ini` | `UI.Action.Back` = Esc · 게임패드 B. 네이티브 태그라도 ini 가 읽힌다(시험 U0) |
| 시험 | `AstralBreak.UI.ScreenStack.{ListenPIE, DedicatedPIE}`(U0 ~ U9) + 시험 화면(C++), `AstralUITestHelpers.h` `IsOnScreen` — HUD 가 이제 레이아웃의 자식이라 `IsInViewport` 로 묻던 세 곳(CombatHUD · StatusHUD PIE · `AstralChainBurstTestController`)을 바꿈 |

*구현하며 정한 것 (설계에 없던 것 · 다르게 한 것)*

1. **층에 Debug 를 더함** — 디버그 글자는 전과 같이 HUD 위, 그리고 메뉴 아래여야 하는데 화면에 오른 위젯이 하나(레이아웃)라 그 사이에 층이 필요하다.
2. **Modal 층의 화면은 `bIsModal`** — 설계는 '라우터가 가장 안쪽부터 준다'고 봤지만 Menu 화면과 Modal 화면은 **형제**이고 형제는 먼저 열린 쪽이 키를 먼저 받는다(`FActivatableTreeNode::ProcessNormalInput` 의 자식 순서). 그대로면 뒤로가 아래 메뉴를 닫는다. Modal 로 열 때 켜서 따로 선 뿌리로 만든다.
3. **화면을 겹쳐 열고 닫는 사이 Game 으로 안 떨어지게** — 스택은 위 화면을 먼저 끄고 다음 것을 켠다. 그 사이 뿌리의 Game 설정이 걸려 커서가 숨었다가 **화면 가운데로 튀었다**(첫 실행에서 봄). 루트 레이아웃이 전환 중에는 다음에 설 화면의 설정을 말한다. 시험이 모드 변화 0 회를 본다.
4. **화면의 주인 컨트롤러 = `PlayerControllerChanged` 로 받은 것만** — 클라이언트가 맵을 여는 동안 `ULocalPlayer::PlayerController` 에는 입력이 없는 임시 컨트롤러가 있어, 첫 실행에서 거기에 레이아웃이 서고 EnhancedInput 오류 두 줄이 났다.
   프로젝트의 `UAstralLocalPlayer::OnPlayerControllerChanged` 는 그 임시 컨트롤러에도 불리고 `SetPlayer` 도중(입력 준비 전)에도 불려 같은 시점이 아니다 — 엔진 서브시스템 통지가 맞다.
5. **시임리스 이동은 컨트롤러를 항상 새로 만든다**(5.7 `AGameModeBase::HandleSeamlessTravelPlayer` — 실측으로도 교체) → 맵 로드 통지 없이 `PlayerControllerChanged` 하나로 충분. 컨트롤러가 이어지는 경우는 `BeginPlayingState` 의 `EnsureLayout` 이 받친다(이 경로는 시험에 없다).
6. 디버그 카메라(`ToggleDebugCamera`)로 컨트롤러가 잠깐 바뀌는 것은 무시한다(화면 유지 — 시험에 없다).
7. 뒤로는 엔진의 `bIsBackHandler` 를 안 쓴다 — 그것은 데이터 테이블 애셋이나 IA 애셋을 요구한다(입력 애셋 안 고침). 여는 액션은 Game 입력에서만 묶인다.
8. 메뉴 중 이동 · 시점 막기는 라우터의 `BlockGameInput` + 눌린 키 비우기만으로 한다(`bIgnoreMoveInput` 은 안 켬 — 컨트롤러의 세는 값이라 편집기에서 설정이 안 걸린 채 끝나면 남는다).

*검증*

| 무엇 | 결과 |
| :--- | :--- |
| 빌드 | DebugGame · Development 둘 다 `Result: Succeeded`(최종 코드) |
| `AstralBreak.` 전체(DebugGame, 최종 코드) | **62/62**(433초) — 기존 60 새 실패 0(HUD 시험 포함) + ScreenStack 2. 라우터 · EnhancedInput 오류 0, ensure 0 |
| ScreenStack(리슨 · Dedicated 각 2인) | U0 ~ U9 전부: 커서 · 메뉴 입력 · 마우스 안 잡음 · 첫 초점 · **눌러 둔 W 가 풀리고 폰이 섬** · 메뉴 중 W 가 게임에 안 감 · B 자리 간섭 없음 · 겹쳐 열고 뒤로 = 맨 위만 · Modal · 액션으로 여닫기 · 열어 둔 채 이동 → 레이아웃 새로 · HUD 둘 · 입력 복구 |
| **HUD 가 전과 같은가(기계)** | 같은 WBP 를 예전 방식(뷰포트에 직접)으로 나란히 띄워 모든 위젯의 그려진 자리 · 크기를 견줌 — StatusHUD 24 개(그려진 것 14) · CombatHUD 20 개(6), **다른 것 0**(허용 0.01 px, 리슨 · Dedicated) |
| **HUD 가 전과 같은가(사람 눈, 11-25 사용자)** | 통과 — '전과 같아'. 3-1 끝 조건 전부 채움 |
| 별도 프로세스 `run_party_flow.py listen --scenario chain_burst` 1회 | PASS(40초) — `-game -nullrhi` 에서도 HUD 가 서고 동료 줄 · 배너 값이 전과 같은 판정. 고친 판정 한 줄을 보려고 돌림 |

*알아 둘 것(쓰는 사람 쪽에서 달라진 것)*

- **허브에서 전투 HUD 가 안 뜬다**(전에는 모든 맵에서 빈 게이지가 떴다 — 허브 맵에서 기대하는 시험은 없었다).
- **PIE 에서 Esc 는 여전히 PIE 정지다** — 라우터가 정지 명령의 키를 일부러 통과시킨다(`CommonUIActionRouterBase.cpp:513-531`). PIE 에서는 게임패드 B, Esc 는 `-game` · 쿠킹에서.
- PIE · 게임이 시작되면 초점이 있는 창의 **마우스가 바로 잡힌다**(Game 설정이 걸리며 라우터가 초점 · 잡기를 요청한다 — 로그 · 소스로 본 것, 손으로는 안 봄). 전에는 창을 누른 뒤였다.

*안 돌린 것 · 못 본 것*

- 실제 키보드 Esc(ini 에 있는 것과 게임패드 B 의 동작만 봄) · 실물 게임패드(가상 커서의 올림 · 초점) · 실제 마우스 클릭(3-4 의 시험 몫) · 화면 배율(DPI) 바뀜.
- Development 구성 실행 · 쿠킹 · `WidgetMcp.`(고치지 않음) · pytest(파이프라인 안 고침) · 별도 프로세스의 다른 시나리오 · 4인.
- 컨트롤러가 유지된 채의 월드 이동 · 디버그 카메라 · HUD 애셋이 없을 때의 경고 경로.

*정리 (11-25 사용자 승인 — 휴지통)* — `AstralCommonUIProbe.{h,cpp}`(1번 측정) · `Tools/mcp/results/net_test/1125_134227_listen_chain_burst` · 스크래치 `uigen_p31`. 뺀 뒤 두 구성 빌드 `Result: Succeeded`(시험은 다시 안 돌림 — 빠진 것은 빈 파일 둘뿐). 1번 측정의 수치는 위 표로만 남는다.

3-2 인계 = 공유 노트 폴더 `local_86515f5f…/uigen-phase3-2-handoff.md`.

**Phase 3-2 결과 — 칸과 버튼(파이프라인) (2026-11-25, 하위 세션 · 구현 · 검증 완료 · 버튼 칸 둘 승격(사용자 승인) · 커밋 `ebf7b83`)**

기존 두 화면의 승격본 · 원천 묶음 · 생성 코드, 허브 맵 · BP · 입력 애셋은 안 고쳤다. 게임 쪽은 새 파일 둘(`UI/Foundation/AstralButtonBase.*`)과 화면 체계 시험뿐.

*사용자가 정한 것 (11-25)*

| 물음 | 답 |
| :--- | :--- |
| 컨셉 후보(A = 설계 세션 그림 · B = 사선 · C = 테두리 없이 위 · 아래 칼날) | **C** → `fixtures/hub_ready_sheet/`(codex 2 / 4 회) |
| 테마 미리보기(상태 일곱 × 게임 · 밝은 바탕, `theme_preview.py`) | **그대로 승인** |
| 엔진 초점 테두리 | **버튼만 끄기**(아래 2 — 전역 ini 는 안 바꿈) |
| `ButtonLarge` · `ButtonSmall` 승격 | **둘 다 승인**(`compare.png` 를 보고) |

*만든 것*

| 자리 | 내용 |
| :--- | :--- |
| 게임 C++ | `UAstralButtonBase : UCommonButtonBase`(글자 `ButtonText` · 선택 모양 `SetSelectedLook` · 초점 모양 · 누른 글자 이동) · `UAstralButtonStyle`(그림이 아닌 테마 값 `PressedTextOffset`) |
| WidgetMcp C++ | 위젯 타입 `UserWidget {class, props}`(승격 경로의 WBP 만 · `[WidgetMcp] WidgetInstanceProperties` 에 있는 속성만 · 자식 없음 — 적용 · 역추출 · 왕복) · 도구 `create_button_style`(일곱 다 · 빈 브러시 거절) · 클래스 기본값 `defaults.Style` · `render_widget` 덮어쓰기 `enabled` · `button`(`.` = 자신, `칸/위젯`, 그리기 앞 · 뒤로 확인해 안 먹으면 `OVERRIDE_NOT_APPLIED`) · `desired_size` · 칸 안 글자의 geometry 줄 |
| 파이프라인 | `profiles/cell.yaml`(캔버스 크기 하나 · 자기 크기 검사) · `screens.yaml parent`(손으로 쓴 부모 — C++ 0, 계약 = 리플렉션 대조) · 최상위 spec `button` + `core/button.py`(단일 원천) · `gen/theme.py` + `config/theme_blade.yaml` · 파생 에셋(provenance `derived` — 원본 sha256 · 테마 해시) · `gen/cells.py`(놓인 칸 = 그 칸의 원천 묶음에서 합성한 그림) · 상태 검사 `state_check.button_states`(E8) · `compare.png` 버튼 칸 · `make_concept --crop` · 글자 배치 `base_width` · `theme_preview.py` |
| 승격 경로 | `/Game/UI/Common/` · `/Game/UI/Screens/` |

*구현하며 정한 것 (설계에 없던 것 · 다르게 한 것)*

1. **초점 모양 = 스타일의 '기본' 브러시를 같은 묶음의 '올림' 브러시로 갈아 끼움**(인스턴스마다, 방향키로 온 초점만 — 엔진 테두리의 기본 규칙과 같다). 겹 그림은 반투명 가장자리가 두 번 겹쳐 어두워지고, 스타일 애셋을 하나 더 두면 모양마다 애셋이 둘이 된다. 부모가 선택 · 켜짐이 바뀔 때마다 스타일을 통째로 다시 걸어 `NativeOnCurrentTextStyleChanged` 에서 다시 입는다 [소스 `CommonButtonBase.cpp` `SetButtonStyle`].
2. **엔진 초점 테두리는 버튼 하나만 막는다** — 버튼의 Slate 를 `OnQueryShowFocus` 가 거짓인 얇은 껍데기로 감쌌다(초점을 받은 위젯에서 바깥으로 올라가며 처음 답한 것을 쓴다 [소스 `SlateApplication.cpp:3056-3065`]). PIE 시험: 프로젝트 버튼 테두리 없음 · 같은 화면의 엔진 버튼은 있음(대조) [실측].
3. **버튼 칸은 analyze 의 LLM 을 안 부른다**(설계 'LLM 은 기본 그림만 정한다'와 다름) — 기본 그림 = 오린 그림 전체, 글자 = 가운데 하나라 요청이 구조를 다 정하고 LLM 이 판단할 것이 남지 않는다. LLM 이 보는 스키마는 예전 그대로다(칸 · 버튼 어휘를 뺀다 — 시험).
4. **spec 에는 기본 그림이 Image 위젯으로 있고 에디터 트리에서만 뺀다** — 오리기 · 합성 · 진단이 위젯마다 그림을 보기 때문(`core/button`). 렌더 geometry 에서는 안쪽 버튼(`InternalRootButtonBase`)의 상자가 그 자리다.
5. **칸의 자기 크기도 본다** — 자동 크기로 놓았을 때의 크기(`desired_size`)가 캔버스와 0.5 px 넘게 다르면 `iou_region` 실패(화면에 놓을 때 그림이 늘어난다).
6. **선택 모양은 알파를 안 바꾸고 강조색 쪽으로 섞는다**(설계 미리보기는 덮개를 얹음 — 알파 1 인 자리에서는 같다).
7. **우리가 그린 글자 참고판은 정합하지 않는다** — 같은 아트 위에 그려 어긋날 수 없는데, 작은 그림에서는 위상 상관이 글자에 끌려 (0.2, 3.1) px 로 쟀다 [실측 477 × 113]. StatusHUD 의 참고판은 전부터 (0, 0) 이라 달라지지 않는다.
8. **글꼴을 우리가 정한 글자는 '가는 꼬리' 자르기를 안 한다**(`diagnose._stats same_font`) — 그 규칙은 글꼴이 다를 때 사선 길이가 달라서 만든 것이다. 받침 아래에 세로획만 있는 '목적지'가 컨셉에서만 잘려 같은 글자의 높이 비가 1.304 로 걸렸다 [실측 `R20261125_155731`]. 문턱은 안 만졌다.
9. **상태끼리 구별은 검정 바탕(렌더)과 회색 바탕(합성) 중 큰 쪽** — 검정에서는 투명도 차이가 숨는다: 누름 ↔ 비활성이 검정 0.98 · 회색 18.55 [실측].
10. **놓인 칸의 글자 자리는 실제로 그려진 것**(geometry 의 `칸/글자` 줄) — 칸 혼자의 보기 글자 자리를 쓰자 긴 글자('봉인된 유적')가 '틀린 그림'(ΔE 74)으로 걸렸다 [실측]. 칸 자신의 정답이 그 글자를 모르므로 자리는 화면의 렌더가 원천이다.

*일부러 틀린 값이 잡히는가 — 쓰기 전에 본 것*

| 틀린 값 | 오프라인 시험(합성으로 흉내 낸 엔진) | 실제 엔진(틀린 스타일을 만들어 그림, 저장 안 함) |
| :--- | :--- | :--- |
| 올림 ↔ 누름 바꿈 | 둘 다 `button_state` + 역추출(`roundtrip`) | 둘 다 `button_state`(ΔE 41) |
| 비활성 빠짐(빈 브러시 · 기본 그림) | `button_state` + 역추출, 빈 브러시는 `create_button_style` 이 거절 | 기본 그림으로 바꾼 것 `button_state`(47 ~ 49) |
| 여백 밀림 | 3 px 밀림 셋 다 `button_state`, 자기 크기 · 최소 크기가 다르면 게이트 실패 | 브러시 여백(box 0.3)만 준 것은 그림이 같아(텍스처 = 칸 크기) 안 걸린다 — 역추출이 본다 |
| 덮어쓰기가 안 먹음 | 못 그리면 `button_render`(합성으로 물러나지 않음) · 오류 없이 기본 그림이 나와도 여섯 상태 전부 `button_state` | 버튼이 아닌 것 · 없는 위젯 · 모르는 상태 · 꺼진 버튼 누름 = `OVERRIDE_NOT_APPLIED` |
| 선택 + 누름 = 선택 그림 | `button_state` | `button_state`(3.1 ~ 3.9 — 문턱 3.0 바로 위, 두 상태의 차가 가장 작은 쌍이다) |
| 글자가 사라짐 · 밀림 · 흐림, 버튼 밖이 바뀜, 두 상태가 같음 | `button_text` · `button_text_moved` · `button_outside` · `button_same` | — |

옳은 스타일은 오류 0 이었다. **틀린 값을 엔진에서 보다가 찾은 플러그인 결함 하나:** 클래스 기본값을 컴파일 뒤에 고치면 새 인스턴스가 다음 컴파일까지 엔진 기본 스타일로 그려졌다(BP 인스턴스는 컴파일 · 로드 때 만든 '옮길 속성' 목록만 물려받는다). 파이프라인은 verify 의 컴파일에 가려 안 드러났다 → `UpdateCustomPropertyListForPostConstruction` + 시험.

*두 칸의 무인 run*

| | `ButtonLarge` `R20261125_160008` | `ButtonSmall` `R20261125_160033` |
| :--- | :--- | :--- |
| 크기 · 글자 | 596 × 132 · 26 pt semibold | 288 × 93 · 16 pt semibold |
| 게이트 | 11 / 11(시도 1) | 11 / 11(시도 1) |
| 오류 / 근사 | 0 / 0 | 0 / 0 |
| 상태 일곱 ↔ 식 | 국소 ΔE00 최대 0.95 · 1.36 · 0.85 · 1.51 · 1.65 · 1.79 · 0.14(기본 · 올림 · 누름 · 선택 · 선택 + 올림 · 선택 + 누름 · 비활성, 문턱 3.0) | 0.83 · 1.37 · 0.60 · 1.28 · 1.37 · 1.68 · 0.13 |
| 버튼 밖 · 글자 이동 | 바뀐 것 0 · 누름 둘만 (0, 1) px | 같음 |
| 상태끼리 가장 가까운 쌍 | 선택 ↔ 선택 + 누름 2.44(하한 2.0), 기본 ↔ 누름 3.75 | 2.38 · 4.17 |
| 글자 읽힘(ΔE) | 54 ~ 86, 비활성 31.7 | 54 ~ 86, 비활성 31.7 |
| 시간 · LLM · codex | 약 23초 · 0 · 0 | 약 16초 · 0 · 0 |
| 묶음 ↔ 한 장씩 렌더 | 9 / 9 바이트 같음 | 9 / 9 바이트 같음 |
| 사람 눈 | 승인(11-25, `compare.png`) — **게임 안에서는 아직 안 봄**(3-4) | 같음 |
| 승격 | `/Game/UI/Common/ButtonLarge` 9 애셋, 새 에디터에서 `record`: 왕복 같음 · 그림 10 / 10 바이트 같음 | `/Game/UI/Common/ButtonSmall`, 같음 |

- 한 번 실패한 run: `R20261125_155731_ButtonLarge`(위 8 의 글자 높이 오측정 — 진단 규칙을 고친 뒤 다시). 시험용 run 셋(`153023` · `153053` · `153207` — 후보 A 로 길을 보던 것)은 게임 화면 run 이 아니다.
- **승격한 칸을 화면에 놓기**(손 spec — 큰 칸 1 · 작은 칸 2, 글자 props, 실제 엔진): 컴파일 · 왕복 같음 · 자리 · 크기 그대로, 글자 밖은 합성과 최대 ΔE 2.9(평균 0.01), 상태 렌더 18 장 오류 0, 다른 칸 · 버튼 밖 바뀜 0.

*검증*

| 무엇 | 결과 |
| :--- | :--- |
| 빌드 | DebugGame · Development(`-DisableAdaptiveUnity`) 둘 다 `Result: Succeeded`(최종 코드) |
| `AstralBreak.` 전체(DebugGame, 최종 코드) | **62/62**(443초) — 기존 62 새 실패 0. ScreenStack 은 U4 를 넓혔다(초점 모양 · 선택 + 초점 · 초점을 잃으면 벗음 · Enter 로 눌러도 스스로 선택 안 됨 · 프로젝트 버튼 테두리 없음 ↔ 엔진 버튼 있음) |
| `WidgetMcp.`(이어서 같은 에디터) | **9/9**(42초 — 새로 `ButtonCell`) |
| pytest `Tools/uigen/tests` | **644 통과**(899초 — 전 586 + 새 58: `test_button_states` 21 · `test_button_cell` 37) |
| `golden.py check` | 35/35 caught · 1/1 clean · 8/8 protected |
| `regress_set`(기준선 `p4_1124` ↔ `p32_1125`, `--relayer`) | `+ new` **0**. 파일 529개 중 514개 바이트 같음 — 다른 15개 = `diagnosis.json` 14(기록된 설정에 새 문턱 셋이 더해진 것뿐) · 코드 목록 `set.json`. 그림 · 판정은 전부 같다. 새 기준선 = `p32_1125` |
| 기존 두 화면 | `promote_screen.py status` — 승격본 · 원천 묶음 · 계약 '기록 그대로'(승격 앞뒤로 두 번). `cppgen.generator_id()` = `1:49a7a94ed467` 그대로, 커밋된 두 헤더의 계약 해시 재현 시험 |

*안 돌린 것 · 못 본 것*

- 게임 안에서 버튼을 본 것 · 실제 마우스 클릭 · 실물 게임패드 · 쿠킹 빌드. 초점 모양은 방향키만(PIE 시험), 게임패드 가상 커서의 올림은 소스만.
- 칸 프로필을 LLM analyze 로 만든 칸(파티 줄 — 3-3) · 바인딩이 있는 칸 · 칸 안의 칸. 버튼 없는 칸 inputs 는 시험이 없다.
- 공용 칸을 다시 승격했을 때 '쓰는 화면' 목록(설계 ⑤) — 쓰는 화면이 아직 없어 안 만들었다(3-3 · 3-4).
- 비활성 글자의 모양은 Slate 흐림 그대로 — 값으로 정하지 않고 읽히는지만 본다.
- 문턱 셋(`button_de` 3.0 · `button_distinct_de` 2.0 · `button_text_de` 8.0)은 칸 둘에서 정한 **잠정**이다. 선택 ↔ 선택 + 누름(2.4)이 하한에 가깝다 — 모양이 다른 버튼이 생기면 다시 볼 값.

*정리* — (11-25 사용자 승인 — 휴지통) `work/` 의 `_measure_p3` · `_measure_p32` · `_candidates_p3` · `_theme` · `_concept/20261125_{115736, 115957, 120053, 150436, 150653}` · 시험 run `R20261125_{153023, 153053, 153207, 155731}_ButtonLarge` · `_promoted` · `_widgetmcp_tests` 의 11-25 것 · `_regress/compare_p4_1124_vs_p32_1125`, `Content/_AutoGen/R20261125_153207_ButtonLarge`, 스크래치 `uigen_p32`. 남긴 것: 승격한 run 둘의 `work` · `_AutoGen`, 기준선 `p32_1125`. 위 표의 측정 수치는 이 글에만 남는다.

3-3 인계 = 공유 노트 폴더 `local_86515f5f…/uigen-phase3-3-handoff.md`.

**Phase 3-3 결과 — 화면 (2026-11-25, 하위 세션 · 구현 · 검증 완료 · `HubMemberRow` 승격(사용자 승인) · `HubReady` 눈 확인 통과 · 미커밋)**

기존 두 HUD 와 버튼 칸 둘의 승격본 · 원천 묶음 · 생성 코드, 허브 맵 · BP · 입력 애셋 · `Config` 는 안 고쳤다. codex 0회. 게임 쪽 새 파일은 `Source/AstralBreak/UI/Screens/` 8개뿐이고 전부 codegen 이 만든 것이다(생성 베이스 둘 · 빈 스텁 둘).

*사용자가 정한 것 (11-25)*

| 물음 | 답 |
| :--- | :--- |
| `HubMemberRow` 승격(`compare.png` 를 보고) | 승인 → `/Game/UI/Screens/HubMemberRow` |
| `HubReady` `compare.png` 눈 확인 | **통과**(승격은 3-4) |

*만든 것*

| 자리 | 내용 |
| :--- | :--- |
| 동작 · 칸의 계약(`core/cppgen` · `codegen/screen_base.*.tmpl`) | 바인딩 종류 `cell`(접근자 `Get…()` 하나) · `action`(`Handle…Clicked` 가상 함수 · `OnClicked()` 묶음 · `Set…Enabled` · `selectable` 이면 `Set…Selected`). 생성 베이스의 부모 `screens.yaml base`(기본이 아닐 때만 계약에) |
| 칸의 정체(`core/cellref`) | 화면은 칸을 ScreenId 로만 부른다 — WBP · 크기 · 버튼인가 · 승격한 run = `promoted/<칸>`, C++ 클래스 = `screens.yaml`(승격한 run 의 `codegen.json` 과 다르면 멈춤), include = 생성 화면은 규칙 · 손으로 쓴 클래스는 모듈 안의 헤더 하나(UHT 가 이름을 하나로 묶는다). 리플렉션 대조 포함 |
| 요청이 정하는 자리(`stages/request`) | inputs `cells[] {id, type, widget, cell, at, text, selectable}` → analyze 뒤 코드가 루트 직계로 넣음(크기 = 칸 캔버스) · `anchor_regions`(묶음의 앵커 — 해상도가 바뀌어도 같이) · 글자 칸 `text_box` · 표시 `over`. LLM 이 보는 스키마 · 어휘는 그대로, 프롬프트에는 칸 자리를 '비워 둘 곳'으로 |
| 원본 아트 속 칸(`gen/cell_art`) | normalize 가 시안의 칸 자리를 재고(±8 px, 3 px 넘으면 `CELL_PLACE`) 칸의 승인한 그림으로 바꾼다 — 아트 · 글자 참고판 둘 다 |
| 바탕 위 표시(`gen/overlay_mark` · layer · refine) | 켜고 끄는 그림이 불투명한 띠 위에 있을 때 획 · 바탕으로 나눔 |
| 가리는 위젯 없음(`core/spec.default_visibility` · `core/hit` · 게이트 `input_clear`) | 클릭을 받는 화면 종류(`menu` · `cell`)에서 안 적은 보이기의 기본값이 잎 `hit_test_invisible` · 패널 `self_hit_test_invisible` · 버튼 아닌 칸 `hit_test_invisible`. 구조 게이트 `input_clear` = 역추출한 트리에서 버튼 위에 클릭을 먹는 위젯 0 · 버튼이 클릭을 받을 수 있음 |
| 긴 글자(`gen/screen_check` · WidgetMcp `overflow`) | `overflow: ellipsis` + `long_sample` + `text_box` → 상태 렌더 `state_long`, E8 `long_outside` · `long_touch` · `long_short` · `long_render` |
| 표시 상태(`gen/screen_check`) | 상태 렌더 `state_<표시>_off`, E8 `mark_state` · `mark_trace` · `mark_same` · `mark_outside` · `mark_render`. `compare.png` 에 표시 켬 · 끔 줄, 긴 글자 줄 |
| `profiles/menu.yaml` · `make_screen.py` · 상대 경로 · 쓰는 화면 | 메뉴 프로필(게이트 값은 hud 와 같음) · 한 명령(후보 → 멈춤(종료 코드 4) → `--pick N \| current`) · 기록 경로는 저장소 상대(`config.repo_rel`), 읽기는 옛 절대 경로도(`recorded_path`) · 승격 기록 `cells`(검증한 칸의 run 까지), `promote_screen.py plan · apply · status` 가 보여 주고 칸이 다시 승격됐으면 화면 승격을 `CELL_CHANGED` 로 거절 |

*구현하며 정한 것 (설계에 없던 것 · 다르게 한 것)*

1. **칸이 여러 번 놓이면 시안 픽셀이 정답이 못 된다** — AI 가 그린 반복은 서로 같은 픽셀이 아니다 [실측 hub_ready_sheet: 파티 줄 2 ~ 4 는 줄 1 과 국소 ΔE00 최대 14 ~ 20(문턱 10)]. 정답 = 칸의 승인한 그림(칸은 자기 run 에서 사람이 승인했다)으로 바꾸고, **자리만** 시안과 견준다. 인계의 추천('버튼 픽셀을 넣고 진단이 칸 합성과 견줌')은 첫 자리에서만 맞는다.
2. **켜고 끄는 그림이 불투명한 띠 위에 있으면 지금 규칙(상자째 오리고 판에서 뺌)은 껐을 때 네모 구멍을 낸다** → 요청이 `over` 로 밝히고, 표시 획만 둘레에서 메운 바탕 + 얹으면 시안이 되는 그림으로 나눈다(덮는 정도는 시안의 알파에서 — 회색 · 흰 바탕에서도 맞게). 획 밖은 시안 픽셀 그대로다.
3. **LLM 상자가 몇 px 모자라면 획이 잘린다** [실측 첫 run — 초승달 아래 끝] → 획이 닿은 변만 2 px 씩 12 px 까지 넓힌다. 상자 다섯을 달리해도 같은 획 상자로 모인다 [실측]. 바탕을 재는 고리가 바뀌면 옅은 가장자리가 1 px 흔들려, 위젯 상자는 획 상자 + 여유로 둔다.
4. **말줄임은 글자 상자가 아니라 잘라 내는 사각형(scissor)에서 정해진다** [소스 `ElementBatcher.cpp` BuildFontGeometry — 실측으로 먼저 걸림: 정책만 넣자 긴 이름이 '준비 완료' 위를 지나갔고 `long_outside` 가 잡았다] → `Clipping = OnDemand` 를 같이 건다. **가운데 정렬 글자는 엔진이 줄이지 않는다** [소스 `SlateTextLayout.cpp` OnPaint] → 요청 검사 `TEXT_BOX_JUSTIFY`, 이유 한 줄은 왼쪽 정렬.
5. **E2(뭉개짐)에 '8 비트 반올림보다 크게 다른 픽셀이 있을 때만'** 을 더했다 — 첫 HubReady run 이 이유 띠에서 걸렸는데 1,981 px 중 63 px 만 1 단계 다르고 나머지는 같았다(평균 밝기 3.2 의 1 단계 잡음 기울기 비 0.79) [실측 `R20261125_213809`]. 문턱(0.8)은 그대로. 낮은 대비 무늬의 진짜 뭉개짐은 시험에서 그대로 걸린다.
6. **칸의 처음 상태** — `render_widget` 의 force_visible 은 칸 속까지 들어가지 않는다 [소스] → 합성도 시작 때 접힌 위젯을 뺀다.
7. **보이기 기본값은 정규화 한 곳에서** — layer · refine · fix 가 나중에 더하는 위젯(정적 판 · 넘침 장식)까지 같은 규칙을 탄다. spec 에는 안 적히고 에디터로 보내는 정규형에만 있다. 버튼 칸(최상위 `button`)은 속이 전부 버튼이라 예전 그대로.
8. **`HubReady` 의 목적지 글자** — `DestinationButton` 의 `props.ButtonText` 로 '봉인된 유적'(잠정)이 들어 있다. 3-4 의 스텁은 `DestinationButton->SetButtonText` 로 바꾼다(생성 베이스에 글자 setter 는 없다 — 버튼 클래스의 것).

*일부러 틀린 값이 잡히는가 — 쓰기 전에 본 것 (`tests/test_screen.py`)*

| 검사 | 틀린 값 → 결과 |
| :--- | :--- |
| `input_clear` | 버튼 위 visible 장식(z 가 뒤) · 조상이 안 막아 주는 장식 · 두 버튼 겹침 · 속이 클릭을 먹는 칸이 덮음 → `blocked`, 꺼진 보이기 · 안 그려진 버튼 → `dead`. hit_test_invisible · 먼저 그려진 장식은 통과 |
| `mark_*` | 상자째 뺀 판(구멍) · 판에 구워진 표시 → `mark_trace`, 안 꺼짐 → `mark_state` + `mark_same`, 다른 것이 움직임 → `mark_outside`, 못 그림 → `mark_render` |
| `long_*` | 줄임이 안 먹음 → `long_outside`, 짧거나 덮어쓰기가 안 먹음 → `long_short`, 글자 칸끼리 겹침 → `long_touch`, 못 그림 → `long_render` |
| 칸 자리 | 6 px 틀린 자리 → `CELL_PLACE`, 칸 상자를 지나는 다른 그림 → `CELL_ART_OVERLAP`, 칸 자리를 덮는 LLM 영역 → `CELL_COVER` |
| 계약 | 버튼을 `cell` 로 · 줄을 `action` 으로 → `CELL_KIND`, 승격 안 된 칸 → `CELL_NOT_PROMOTED`, 클래스가 바뀐 칸 → `CELL_CLASS_CHANGED`, 이름 충돌 → `SETTER_COLLISION` |

*두 run*

| | `HubMemberRow` `R20261125_211554` | `HubReady` `R20261125_215251` |
| :--- | :--- | :--- |
| 크기 · 바인딩 | 610 × 82 · text 1 · flag 2 | 1920 × 1080 · text 1 · cell 4 · action 3 |
| 게이트 | 12 / 12(시도 1 — 글자 맞춤 뒤 한 번 더 12 / 12) | 12 / 12(시도 1) |
| 오류 / 근사 | 0 / 1('준비 완료' 굵기 — 글꼴은 참고판과 같고 작은 획의 측정 차) | 0 / 1(이유 글자 굵기 — 같은 까닭) |
| 시안 ↔ 렌더 국소 ΔE00 최대 | 검정 0.95 · 회색 1.29 | 검정 0.95 · 회색 0.63 |
| 표시 끔 · 긴 글자 | 흔적 검정 1.57 · 회색 2.27(문턱 5) · 켬 ↔ 끔 37.5 / 이름 칸의 97 % 에서 '…' | 이유 칸의 98 % 에서 '…' |
| 칸 자리(시안이 그린 자리 − 요청한 자리) | — | 일곱 다 1 px 이하(줄 2 · 4 만 세로 1 px) |
| 놓인 버튼 상태(국소 ΔE00 최대, 문턱 3.0) | — | 셋 다 0.13 ~ 1.79 · 버튼 밖 0 · 가장 가까운 쌍 2.41(하한 2.0 — 칸 run 과 같음) |
| 시간 · LLM · codex | 약 1분 50초(에디터 기동 48초 포함) · 1회 · 0 | 약 2분 34초 · 1회 · 0 |
| 묶음 ↔ 한 장씩 렌더 | 5 / 5 바이트 같음 | 21 / 21 바이트 같음 |
| 사람 눈 | 승격 승인(`compare.png`) — 게임 안에서는 아직 안 봄 | 통과(`compare.png`) — 게임 안 · 조작감은 3-4 |
| 승격 | `/Game/UI/Screens/HubMemberRow` 3 애셋, 새 에디터에서 `record`: 왕복 같음 · 그림 7 / 7 바이트 같음 | 안 함(3-4) |

- 실패한 run 셋: `210820`(위 3 — analyze 에서 멈춤) · `210931`(위 4 의 말줄임 + 표시 구별을 옅은 가장자리까지 재던 검사 — 검사를 획 속으로) · `213809`(위 5). 승격 전 예행(스크래치 · 임시 승격 폴더) 둘은 세지 않는다.
- 다른 해상도(1920 × 1200 · 2560 × 1080)에서 왼쪽 · 오른쪽 묶음이 통째로 움직인다(`anchor_regions`) — 사람 눈으로도 봄(세션).

*검증*

| 무엇 | 결과 |
| :--- | :--- |
| 빌드 | DebugGame · Development(`-DisableAdaptiveUnity`) 둘 다 `Result: Succeeded`(최종 코드) |
| `AstralBreak.` 전체(DebugGame, 최종 코드) | **62/62**(457초) — 새 실패 0 |
| `WidgetMcp.`(이어서 같은 에디터) | **9/9**(43초 — `BuildRoundTrip` 에 `overflow` 왕복 · 모르는 값 거절을 더함) |
| pytest `Tools/uigen/tests` | **685 통과**(980초 — 전 644 + 새 41 `test_screen`) |
| `golden.py check` | 35/35 caught · 1/1 clean · 8/8 protected(E2 규칙을 바꾼 뒤) |
| `regress_set`(기준선 `p32_1125` ↔ `p33_1125`, `--relayer`) | `+ new` **0**. 파일 529개 중 528개 바이트 같음 — 다른 하나는 코드 목록 `set.json`. 새 기준선 = `p33_1125` |
| 기존 화면 | `promote_screen.py status` — 다섯 화면 승격본 · 원천 묶음 · 계약 전부 '기록 그대로'(승격 앞뒤). `cppgen.generator_id()` = `1:49a7a94ed467` 그대로, 두 HUD 헤더 해시 재현 시험 통과. `HubReady` 계약의 생성기 = `1:49a7a94ed467+a088c62e72cf` |

*안 돌린 것 · 못 본 것*

- 게임 안에서 화면 · 칸을 본 것, 실제 마우스 클릭 · 초점 이동 · 게임패드(3-4 의 PIE 시험). 버튼 위를 가리는 위젯은 트리와 상자로 본 것이고 엔진 히트 테스트는 안 돌렸다.
- 조작 화면을 이어서 고치기(`--from HubReady --edit`) · 칸의 재승격 뒤 `CELL_CHANGED` 를 실제 파일로 · `make_screen.py` 의 후보 만들기(codex 0 으로 지내 `--pick current` 만 실제로 돌림, 후보 길은 시험).
- 표시 획을 나누는 자리의 바탕은 시안에 없던 픽셀이다 — 매끈한 띠에서만 봤다. 무늬 위 표시는 안 봤다.
- LLM fix 경로가 칸이 있는 화면에서 도는 것(두 run 다 시도 1 에서 구조 통과 — 가드는 시험만) · Development 구성 실행 · 쿠킹.
- 스킬 문서 둘(`.claude/skills/uigen-run` · `ue-umg-authoring`)은 사용자 승인(11-25) 뒤 이 절의 규칙으로 고쳤다.

*정리* — (11-25 사용자 승인 — 휴지통, 44.4 MB) `work/_measure_p33` · 실패한 run 셋 `R20261125_{210820, 210931}_HubMemberRow` · `R20261125_213809_HubReady` · `work/_promoted/HubMemberRow/record_20261125_213641` · `work/_regress/compare_p32_1125_vs_p33_1125` · 세션 스크래치. 정리 뒤 `promote_screen.py status` 다섯 화면 전부 '기록 그대로'. 남긴 것: 승격한 칸 run `211554` 과 3-4 가 승격할 화면 run `215251` 의 `work` · `_AutoGen`, 기준선 `p33_1125`(과 `p32_1125`). 실패한 run 의 측정 수치는 이 글과 코드 주석에만 남는다.

3-4 인계 = 공유 노트 폴더 `local_86515f5f…/uigen-phase3-4-handoff.md`.

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
7. ~~집계 리포트 커밋~~ — **결정(11-24): 스크립트 `Tools/uigen/summarize.py` + 글 리포트 `Docs/Design/ui-autogen-report.md` 를 커밋 대상으로**(원본 `metrics/` · `work/` 는 git 무시 그대로).
8. ~~HUD 요소 목록~~ — **결정(11-14): M4 설계 §5 그대로** — 오의 게이지(+가득 시 강조) · 체인 패널(남은 시간 · 참가 N/4) · 버스트 배너(인원) · '오의 불가'.
**1b 착수 때 물을 것(1a-5 정리, 11-15):** 3(컨셉아트 경로) · 4 후속(프로젝트 폰트 선택 · 내려받기 승인) · OCR 엔진 선택 — 근거는 §11 '1b 로 넘길 것'. 7(집계 리포트 커밋)은 Phase 2.
→ **결정(11-15, 1b 착수):** 3 = codex 로 컨셉아트 1장 생성 · 4 = Pretendard(Regular · Bold — 내려받기는 1b-3 에서 따로 승인) · OCR = RapidOCR(설치는 1b-3 에서 따로 승인) · 6 후속 = codex run 당 20 그대로 + analyze 상한 1.0 USD · 턴 6 · 600초(잠정). 나머지 1b 결정은 §11 '1b 착수 때 정한 것'.

9. **Phase 1a 진행 방식(11-14 결정):** 브랜치 `feat/M4_Ultimate_Skills` 그대로 · 하위 단계 1a-1 ~ 1a-5(§11) · 재시도 fix 는 **결정적 fixer**(일부러 깨뜨린 spec + 정정 patch, LLM verifier · fix 실제 호출은 1b — 1a 에는 reference.png 가 없어 verifier 가 비교할 대상이 없다) · 설정 YAML 을 위해 venv 에 **PyYAML 6.0.3 설치**(사용자 승인).
