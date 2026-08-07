---
name: astral-ue-montage
description: AstralBreak UE5.7 애니메이션 몽타주 생성 및 Notify 배치 자동화.
             몽타주 생성, 히트 윈도우 설정, GameplayEvent 태그 배치 시 사용.
---

# 실행 방법

에디터가 켜져 있어야 한다. 반드시 아래 형태로만 실행한다.

    python Tools/ue_exec.py Tools/scripts/<스크립트>.py

로컬에서 `import unreal` 을 시도하지 않는다. `unreal` 모듈은 에디터 프로세스 안에서만 존재한다.
`ue_exec.py -c` 는 사용하지 않는다. 항상 스크립트 파일을 만들어 실행한다.

스크립트 상단에는 항상 다음 두 줄을 넣는다.

    import sys
    sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

# 파일 인코딩

JSON을 읽을 때는 항상 `encoding="utf-8-sig"` 를 쓴다. Windows에서 만든 파일에
BOM이 붙어 있으면 `json.load` 가 실패한다.

# 헬퍼 API

`Tools/lib/ab_montage.py` 의 함수만 사용한다. 직접 `unreal.AnimMontageFactory` 를 호출하지 않는다.

- `build_from_spec(spec, dry_run=False)` — JSON 스펙 하나로 몽타주 생성. **기본 경로**
- `create_montage(...)` / `add_notify(...)` / `add_notify_state(...)` — 저수준
- `tag(str)` — 문자열을 FGameplayTag로. 미등록 태그면 예외
- `describe(montage)` — 생성 결과 검증

여러 개를 만들 때는 `Tools/data/montages.json` 을 수정하고
`Tools/scripts/build_montages.py` 를 실행한다.

# 경로 규약

- 몽타주: `/Game/Animation/{Job}/Montages/AM_{Job}_{Action}{NN}`
- 소스 애니메이션: `/Game/Animation/{Job}/Anims/...`
- 테스트 산출물: `/Game/AstralBreak/_ScriptTest/` (프로덕션 경로에 테스트 애셋을 만들지 않는다)

# Notify 클래스

- `GameplayEvent` — 단발. `event_tag`, `event_data`
- `GameplayEventWindow` — 구간. `begin_event_tag`, `end_event_tag`, `event_data`

`event_data` 는 `make_event_data(magnitude=...)` 로만 만든다.
`instigator`, `target`, `context_handle`, `target_data` 는 런타임 전용이므로 절대 설정하지 않는다.

# 금지사항

- **슬롯 이름 변경 금지.** `slot_anim_tracks` 는 Python에 노출되지 않는다. DefaultSlot 고정이다.
- **다중 섹션 구성 금지.** `composite_sections` 미노출. 몽타주 1개 = 1섹션.
  콤보는 몽타주를 쪼개고 GA에서 체이닝한다.
- **AnimGraph / EventGraph 노드 생성 시도 금지.** Python 경로가 없다.
- 태그 문자열을 지어내지 않는다. 프로젝트에 등록된 태그만 쓴다.
  새 태그가 필요해 보이면 사용자에게 확인한다.

# 작업 절차

1. 요청을 몽타주 스펙으로 변환한다
2. 실제 실행 후 `describe()` 출력으로 검증한다 (length가 0이면 소스 연결 실패)
3. 실행 전 사용자에게 커밋을 권고한다. .uasset 은 되돌리기 어렵다

# 모듈 캐시

`Tools/lib/*.py` 를 수정한 뒤에는 반드시 `importlib.reload()` 를 호출한다.
에디터가 이전 버전을 캐시하고 있어서 파일만 고치면 옛 코드가 실행되고
트레이스백 라인 번호가 어긋난다.

    import sys, importlib
    sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
    import unreal
    import ab_montage as m; importlib.reload(m)