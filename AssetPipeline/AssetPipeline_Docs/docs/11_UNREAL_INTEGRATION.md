# UE5.7.4 및 AstralBreak 연동

```mermaid
flowchart TD
 A[Approved Blender Asset] --> B[FBX + textures + manifest + combat metadata]
 B --> C[UE Python / C++ Editor Module]
 C --> D[/Game/Generated/Staging/JobID]
 D --> E[Import / Skeleton / playback QA]
 E --> F[Montage / Notify / Combat QA]
 F -->|승인| G[Publish game assets]
 F -->|실패| H[Staging 보존 / 수정 또는 복구]
```

AssetImportTask, AnimationLibrary, IKRetargetBatchOperation, AnimMontageFactory 등 API는 실제 UE5.7.4 source build에서 기능/플러그인 활성화 확인. Python으로 불가능한 조작은 Editor 전용 C++ module. FBX export: deform bones만 필요한 경우 export, scale/axis/root/animation length/bake settings 검사. 기존 skeleton 선택과 새 skeleton 생성 분리.

```text
Plugins/AssetPipelineEditor/
  AssetPipelineEditor.uplugin
  Source/AssetPipelineEditor/{Public,Private}/
    AssetPipelineSubsystem
    AssetImportService
    MontageGenerationService
    CombatMetadataService
    AssetValidationService
```

에셋: Skeletal Mesh, Skeleton, Animation Sequence, IK Rig/Retargeter, Montage, Notify/NotifyState, 필요시 Blend Space 등. 승격 전 package reference 및 충돌 확인. 임의로 기존 게임 콘텐츠 overwrite 금지.

```json
{
  "animation": "AM_Knight_HeavySlash_01",
  "combat_type": "HeavyAttack",
  "duration_seconds": 1.4,
  "phases": {"windup": [0, 0.45], "attack": [0.45, 0.70], "recovery": [0.70, 1.40]},
  "hit_window": [0.45, 0.70],
  "root_motion_distance_cm": 180,
  "motion_warping": {"enabled": true, "window": [0.10, 0.45]},
  "combo_window": [0.70, 1.15],
  "notify_states": ["WeaponTrace", "MotionWarping"]
}
```

예시 metadata는 제안이며 실제 Notify class명, hit window, montage slot/section, combo semantics를 프로젝트 코드와 비교해 확정. Claude가 damage, balance, 서버 권한 정책을 임의 변경하지 않는다. 무기 socket/trace path, root rotation, warping, cancel, montage timing을 검사한다.

멀티플레이 QA: Listen Server + remote client, dedicated 호환 설계; GAS activation/cancellation, montage 동기화, root motion/warping 위치 차이, 서버 권한 hit detection, latency에서 combo/notify 확인. Dedicated 서버에서 필요한 skeletal tick 정책은 실제 trace 구현에 맞춰 검사. 자동 생성은 런타임 권한 변경과 별개다.

완료 조건: staging import, animation playback, montage/notify 생성, 오류 시 승인본 불변, 실제 공격 1개를 게임 내 smoke test. AstralBreak 소스는 이번 문서 생성에서 직접 검사하지 않았으므로 실제 인터페이스 확정 전 별도 검토.

참고 R01, R09, T16~T20.
