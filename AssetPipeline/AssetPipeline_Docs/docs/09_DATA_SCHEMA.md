# 공통 데이터 규격

Asset Manifest는 source/license/hash/version, Mesh는 geometry/material, Skeleton은 hierarchy/rest pose/mapping, Motion은 frame/transform, Motion Specification은 phase/intent/constraints, QA는 metric/confidence, Engine Metadata는 import/montage/notify를 보관한다.

| 데이터 | 포맷 |
|---|---|
| 원본 | GLB/FBX |
| Blender 작업 및 snapshot | BLEND |
| Skeleton / Metadata / QA | JSON |
| Motion 배열 | NPZ (allow_pickle=False) |
| Workflow | YAML/JSON |
| 영상 / 이미지 | MP4/PNG |
| UE 교환 | FBX + manifest |
| 상태 | SQLite |

공통 좌표계 제안: right-handed, Z-up, +Y forward, meter, local rotation quaternion xyzw. Blender/UE/provider 변환 adapter에서 축·단위·handedness를 명시적으로 처리한다. Unreal은 cm, Z-up, +X forward 관례를 고려한다. 실제 mapping은 golden fixture로 검증.

```json
{
  "schema_version": "1.0",
  "motion_id": "knight_heavy_slash_001",
  "source": {"type": "video_to_motion", "provider": "gvhmr", "artifact_id": "reference_video_001"},
  "skeleton_id": "humanoid_v1",
  "coordinate_system": {"handedness": "right", "up_axis": "Z", "forward_axis": "Y", "unit": "meter"},
  "rotation": {"representation": "quaternion", "order": "xyzw", "space": "parent_local"},
  "fps": 60,
  "frame_count": 91,
  "duration_seconds": 1.5,
  "motion_file": "motion.npz",
  "phases": {"windup": [0.0, 0.45], "attack": [0.45, 0.70], "recovery": [0.70, 1.50]},
  "constraints": {"two_handed_grip": true, "foot_contact": true}
}
```

기존 설계의 90 frame/1.5초 예시를 양 끝 샘플 포함 규약으로 91 frame으로 정정했다. timestamps를 authoritative로 하고 duration = last-first. phase 경계는 마지막 구간을 제외하고 half-open으로 해석한다.

| NPZ 배열 | shape | 의미 |
|---|---|---|
| timestamps | F | seconds |
| local_rotations | F,J,4 | parent-local quaternion |
| local_translations | F,J,3 | parent-local position |
| root_translation | F,3 | global root |
| root_rotation | F,4 | global root orientation |
| joint_confidence | F,J | optional estimate confidence |
| foot_contacts | F,2 | optional contact |
| weapon_transform | F,7 | optional position + quaternion (space 명시) |
| validity_mask | F,J | optional valid sample flag |

Root 데이터 중복 적용 금지: local arrays의 root는 identity/zero 또는 별도 규약 명시; global root trajectory는 한 번만 합성. Quaternion 정규화, sign continuity, timestamps 단조 증가, shape/dtype/finite 검증. 누락된 confidence를 임의로 높은 값으로 채우지 않는다.

Canonical humanoid profile은 공통 관절 의미와 mapping용이다. Mixamo/SMPL/custom에서 변환하고 UE skeleton/knight/boss에 적용하되 twist/weapon/IK/extra bone을 보존한다. Skeleton마다 hierarchy, rest transform, bone axes, mapping version, unit, joint limits 저장. 비인간형은 별도 profile.

완료 조건: JSON schema/Pydantic 검사, NPZ roundtrip, 축/단위 변환 golden tests, root 중복 이동 없음.
