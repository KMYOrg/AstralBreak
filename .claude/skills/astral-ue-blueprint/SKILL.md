---
name: astral-ue-blueprint
description: AstralBreak UE5.7 Blueprint 생성 자동화. BP 애셋 생성,
             컴포넌트 계층 구성, CDO 디폴트값 설정 시 사용.
---

# 실행 방법

에디터가 켜져 있어야 한다.

    python Tools/ue_exec.py Tools/scripts/<스크립트>.py

스크립트 상단 고정 패턴 (reload 필수 — 에디터가 모듈을 캐시한다):

    import sys, importlib
    sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
    import unreal
    import ab_blueprint as B; importlib.reload(B)

# 헬퍼 API

- `build_from_spec(spec)` — JSON 스펙으로 BP 생성. **기본 경로**
- `create_bp(path, parent_class)` / `duplicate_bp(src, dst)` — 저수준
- `add_component(bp, class, name, parent_handle)` — 계층은 parent_handle 로
- `set_defaults(bp, {...})` — CDO 값. 실패한 키 리스트 반환
- `list_bps(package_path, parent_filter)` — 부모 클래스로 필터
- `batch_set_defaults(paths, props, dry_run=True)` — 일괄 수정, 기본 dry run

# 스펙 형식

    {
      "path": "/Game/AstralBreak/Characters/BP_Astral_Warrior",
      "parent": "/Script/AstralBreak.AstralCharacterPlayer",
      "template": null,
      "components": [
        {"class": "/Script/Engine.SpringArmComponent", "name": "CameraBoom"},
        {"class": "/Script/Engine.CameraComponent", "name": "FollowCamera",
         "parent": "CameraBoom"}
      ],
      "defaults": {"MaxCombo": 4},
      "overwrite": false
    }

`parent` 는 컴포넌트 이름 문자열. 앞서 정의된 컴포넌트만 참조 가능하다.

# 애셋 삭제 규칙

애셋을 삭제하기 전에 에디터에서 해당 애셋이 열려 있지 않은지 확인한다.
열린 애셋을 `delete_asset` / `delete_directory` 로 지우면 에디터가 크래시한다.

`ab_blueprint.safe_delete_directory()` 를 쓰거나, 사용자에게 탭을 닫아달라고
요청한다. 레벨은 삭제 대상 맵이 현재 열려 있으면 안 되므로 다른 맵을 먼저 로드한다.

# 금지사항

- **EventGraph 노드 생성 금지.** Python 경로가 없다. 로직은 C++ 부모 클래스에 둔다.
- 멤버 변수 추가는 하지 않는다. `UPROPERTY` 로 C++ 에 선언한다.
- `describe_bp` 는 컴포넌트 목록을 반환하지 않는다. 컴포넌트 확인은
  에디터에서 BP 를 열어 사용자가 한다.
- CDO 값 설정 실패는 조용히 넘어간다. `set_defaults` 반환값을 반드시 확인하고
  실패한 키를 보고한다. 프로퍼티 이름은 스네이크케이스로 변환된다.

# 절차

1. 스펙을 작성한다
2. 실행 후 `set_defaults` 실패 목록을 확인한다
3. 사용자에게 에디터에서 컴포넌트 계층 확인을 요청한다
4. 실행 전 커밋을 권고한다

# 모듈 캐시

`Tools/lib/*.py` 를 수정한 뒤에는 반드시 `importlib.reload()` 를 호출한다.
에디터가 이전 버전을 캐시하고 있어서 파일만 고치면 옛 코드가 실행되고
트레이스백 라인 번호가 어긋난다.

    import sys, importlib
    sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
    import unreal
    import ab_blueprint as B; importlib.reload(B)