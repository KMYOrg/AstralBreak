---
name: astral-ue-level
description: AstralBreak UE5.7 레벨 블록아웃 자동화. 맵 생성, 액터 배치,
             레이아웃 설계 및 파라미터 기반 재생성 시 사용.
---

# 실행 방법

에디터가 켜져 있어야 한다.

    python Tools/ue_exec.py Tools/scripts/build_level.py

스크립트 상단에 항상 두 줄:

    import sys
    sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")

JSON 읽을 때는 `encoding="utf-8-sig"`.

# 작업 흐름

1. **애셋 확인** — `Tools/data/asset_catalog.json` 을 읽는다.
   여기 없는 메시 경로를 지어내지 않는다. 카탈로그가 오래됐으면
   `Tools/scripts/dump_assets.py` 를 먼저 실행한다.
2. **컨셉 정리** — 사용자와 대화로 크기/구조/동선을 확정한다.
   추측하지 말고 모호하면 묻는다.
3. **레이아웃 작성** — `Tools/data/<맵이름>.layout.json` 을 만든다.
4. **빌드** — `build_level.py` 의 SPEC 경로를 맞추고 실행한다.
5. **검증** — 사용자에게 스크린샷을 요청한다. 결과를 눈으로 볼 수 없다.

# 레이아웃 스키마

    {
      "map": "/Game/AstralBreak/Maps/L_Raid_Boss01",
      "mode": "new",              // new: 새로 생성, rebuild: 생성 액터만 교체
      "actors": [
        { "kind": "mesh", "shape": "cube" | "<애셋경로>",
          "label": "...", "location": [x,y,z], "rotation": [p,y,r], "scale": [x,y,z] },
        { "kind": "class", "class": "PlayerStart",
          "pattern": { "type": "radial", "count": 8, "radius": 1200,
                       "z": 400, "face_center": true } }
      ]
    }

패턴: `radial` (count, radius, z, start_deg, face_center, yaw_offset),
`grid` (cols, rows, spacing, z)

사용 가능한 클래스: PlayerStart, TargetPoint, DirectionalLight, SkyLight,
PointLight, SpotLight, NavMeshBoundsVolume, TriggerBox, TriggerSphere,
PostProcessVolume

BP 액터도 배치된다 (실측 확인). `class` 에 **`_C` 접미사가 붙은 전체 경로**를 준다.
접미사 없는 경로는 None을 반환해 실패한다.

    { "kind": "class",
      "class": "/Game/Characters/Enemy/BP_TargetDummy.BP_TargetDummy_C",
      "location": [0, 0, 100] }

# 배치 패턴

- `radial` — 원형 방사 (count, radius, z, start_deg, face_center, yaw_offset)
  기본은 액터 +X가 반지름 바깥. 장축이 X인 벽/차폐물을 링으로 세울 때는
  `yaw_offset: 90` 으로 접선 방향을 만든다 (안 주면 바큇살이 된다).
- `grid` — 격자 (cols, rows, spacing, z)
- `line` — 두 점 사이 선형 (count, start, end, face_path)
- `rect_ring` — 사각 링, 내부 비움 (cols, rows, spacing, z)
- `explicit` — 좌표 직접 나열 (points: [{location, rotation}, ...])

패턴으로 표현이 안 되면 `explicit` 을 쓴다. 좌표를 직접 계산해서 넣는다.
패턴에 억지로 끼워 맞추지 않는다.

# 크기 계산

스케일을 눈대중으로 정하지 않는다. `ab_assets.scale_for(mesh_path, [x,y,z])` 로
목표 크기(cm)를 스케일로 환산한다. None을 넣으면 해당 축은 1.0 유지.

엔진 기본 도형은 100cm 기준이다. Cube를 높이 800cm 기둥으로 쓰려면 z 스케일 8.

# 규칙

- 레벨은 JSON에서 재생성한다. .umap 은 git diff 가 안 되므로 JSON 이 진실이다.
- 생성 액터에는 `AB_Generated` 태그가 붙는다. `mode: rebuild` 는 이 태그가 붙은
  것만 지우므로 손으로 놓은 액터는 보존된다.
- **실행 전 커밋을 권고한다.** 레벨 재생성은 되돌리기 어렵다.
- `new_level()` 은 현재 열린 레벨을 닫는다. 저장 안 된 작업이 있으면 먼저 알린다.
- 프로덕션 맵 경로에 테스트 레벨을 만들지 않는다. `/Game/AstralBreak/_ScriptTest/` 를 쓴다.

# 한계

- 공간감, 동선, 시야 차단 같은 판단은 못 한다. 블록아웃까지가 범위다.
- 자연스러운 불규칙 배치는 어렵다. 규칙적 패턴 + 파라미터 조정이 강점이다.
- 결과를 볼 수 없으므로 반드시 사용자 피드백 루프를 돈다.

# 알려진 함정

- `new_level()` 직후 `get_all_level_actors()` 를 읽지 않는다. 이전 월드가 아직
  정리되지 않아 다른 맵의 액터가 섞여 나온다. `ab_level.build()` 는 내부에서
  `save_current_level()` → `load_level()` 로 상태를 확정한 뒤 집계한다.

- `mode` 는 작업 후 원래 값으로 되돌린다. `rebuild` 로 둔 채 방치하면 다음에
  새 맵을 만들 때 에러가 난다. 레벨이 없으면 `rebuild` 는 실패한다.

- 맵 경로와 레이아웃 파일명을 일치시킨다. `L_Raid_Boss01.layout.json` 의
  `map` 필드는 `.../L_Raid_Boss01` 이어야 한다. 테스트 중이면 파일명도
  테스트용으로 짓는다.

- 맵을 바꿀 때는 `build_level.py` 의 `SPEC_NAME` 상수만 수정한다.
  `ue_exec.py` 는 인자를 전달하지 않는다.

# 보고 규칙

빌드 후 액터 개수만 보고하지 않는다. 다음을 계산해서 함께 제시한다.

- 각 오브젝트의 실제 크기 (스케일 × 메시 bounds)
- 배치 간격 (기둥 중심간 거리, 통로 폭)
- 커버리지 (NavMesh 가 바닥을 덮는지, 링이 바닥 안에 있는지)

수치가 맞아도 눈으로 본 것은 아니므로 사용자에게 스크린샷을 요청한다.

# 모듈 캐시

`Tools/lib/*.py` 를 수정한 뒤에는 반드시 `importlib.reload()` 를 호출한다.
에디터가 이전 버전을 캐시하고 있어서 파일만 고치면 옛 코드가 실행되고
트레이스백 라인 번호가 어긋난다.

    import sys, importlib
    sys.path.insert(0, r"D:/UE5Projects/AstralBreak/Tools/lib")
    import unreal
    import ab_level as L; importlib.reload(L)
    import ab_assets as A; importlib.reload(A)