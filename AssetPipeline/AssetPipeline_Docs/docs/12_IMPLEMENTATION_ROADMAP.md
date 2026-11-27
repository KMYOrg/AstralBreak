# PoC / MVP / 구현 계획

최종 아키텍처는 목표일 뿐이며 한 번에 구현하지 않는다. 먼저 기술 검증 후 수직 슬라이스. 각 단계 시작 전 도구 버전, OS/GPU/VRAM, 비용, 라이선스 확인. 상세 일정은 실측 후 산정.

| Phase | 구현 | Exit criteria |
|---|---|---|
| 0 | 기술 검증 | Claude MCP bone 수정, Blender CLI import/export, snapshot 복구, rig, video motion, retarget, UE 재생 각각 성공 또는 blocker 명시 |
| 1 | Core | CLI, SQLite, task/attempt/artifact, snapshot, retry 제한, crash resume |
| 2 | Blender | MCP + headless, 안전 경로, render/inspection, 직접 수정 및 복구 |
| 3 | Mesh/Rig | Tripo 입력, 한 humanoid rig, pose QA, fallback |
| 4 | 기존 Animation | retarget, timing/root/IK 수정, UE 기본 import |
| 5 | Video-to-Motion | 생성 영상 및 기존 영상, 추출, 의미 분석, 공통 motion |
| 6 | Text-to-Motion | provider 연동, 공통 출력 및 retarget |
| 7 | Autonomous QA | render comparison, 제한된 수정/rollback/fallback |
| 8 | UE Gameplay | Montage/Notify/Combat metadata, 실제 GAS 검증 |
| 9 | 확장 | creature, batch, parallel, advanced retopo 및 QA |

Phase 0에서 전투 영상 mocap 품질을 먼저 실측한다. MVP(1~4)는 기존 모션 기반으로 작동 가능한 게임용 에셋 제작. Phase 5부터 AI 영상 생성/분석을 통합하되 PoC에서 성공 여부를 먼저 확인한다.

첫 vertical slice: Knight.glb → Mesh 검사 → Rig → Pose QA → 의도적 실패 복구 → 대검 공격 1개(기존 또는 영상 기반) → retarget → grip/foot/root/timing → FBX → UE staging → animation 재생 → 사용자 승인. 이후 Idle/Walk/Run/Dodge/3단 combo/Charged/HitReact 확대.

```text
AssetPipeline/
  CLAUDE.md README.md pyproject.toml .mcp.json .env.example
  .claude/{agents,skills}/
  pipeline/
    core/{planner,executor,task,registry,state_manager,checkpoint,recovery,artifact_manager,budget}.py
    domain/{mesh,rigging,motion,animation,video,validation}/
    providers/{mesh,rigging,video,motion,vision}/
    adapters/{blender,unreal}/
    schemas/{asset,skeleton,motion,workflow,validation,combat}.py
    mcp/{server.py,tools/}
    cli/main.py
  knowledge/{modeling,rigging,animation,video,unreal}/
  configs/{providers.yaml,recovery.yaml,validation.yaml,skeleton_profiles/,projects/astralbreak.yaml}
  workflows/{mesh_to_rig,video_to_animation,text_to_animation,modify_animation,character_to_unreal}.yaml
  workspace/{source,jobs,checkpoints,candidates,approved,reports}/
  tests/{unit,integration,regression,fixtures}/
  docs/
```

위 구조는 목표이며 현재 ZIP은 설계 문서만 포함한다. 기술 후보: Python, Pydantic, Typer, SQLite, NumPy/SciPy, bpy, FFmpeg/OpenCV, pytest, Git/Git LFS. 무거운 model weights, secret, 캐시, 원본 대용량 파일은 Git에 직접 넣지 않는다.

구현 착수 전 Claude에게 references 검증, repo commit/license, 재사용 범위, PoC 실행 계획, 위험 및 ADR을 요청한다. 사용자 승인 후 작은 단계로 구현 및 테스트한다.
