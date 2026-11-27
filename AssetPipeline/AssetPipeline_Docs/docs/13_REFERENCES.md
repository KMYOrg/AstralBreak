# 출처 / 참고 자료 / 검증 정책

아래 링크는 앞선 대화에서 조사 대상으로 제시된 자료를 보존한 것이다. 이번 문서 패키징 과정에서는 외부 링크/저장소의 실재, 최신 상태, 전체 소스, 라이선스, 기능 실행을 새로 검증하지 않았다. 특히 개인 저장소의 이름·README 주장·기능은 Claude Code가 실제 접근 및 commit 단위로 재검증하기 전까지 **미확인 후보**로 취급한다. 이전 대화의 인라인 citation ID는 Claude에서 접근 불가하므로 URL 기반 목록으로 대체한다. 확인 불가 링크는 설계의 근거로 사용하지 않는다.

## 구현 사례 후보

| ID | URL | 참고할 설계 요소 (검증 필요) |
|---|---|---|
| R01 | [AssetForge](https://github.com/HErkanuzun/AssetForge) | 통합 orchestration, AI provider, UE 연동, QA |
| R02 | [Claude Blender Integration](https://github.com/rotembab/claude-blender-integration) | Agent/MCP/add-on, rig/animation tool, checkpoint/rollback |
| R03 | [Keyframe Coach](https://github.com/Guilherme-M-Mateus/keyframe-coach) | animation skill, key pose, audit |
| R04 | [AutoRig Workbench](https://github.com/sambena/autorig-workbench) | rig 선택, headless CLI, pose/skinning 검사 |
| R05 | [Scenario Fully Rigged](https://www.scenario.com/explorations/fully-rigged/) / [Uthana](https://www.scenario.com/blog/uthana-video-and-text-to-motion) | AI video → motion → retarget |
| R06 | [HY-Motion-Pipeline](https://github.com/wa-ys/HY-Motion-Pipeline) | text/video motion 통합 |
| R07 | [3DCharacterAutomationPipeline](https://github.com/SUPERpowerGT/3DCharacterAutomationPipeline) | Blender CLI 스크립트 구조 |
| R08 | [Character Animation Pipeline](https://github.com/flora6907/character-animation-pipeline) | AI 모델 조합 및 retarget |
| R09 | [Blender Unreal Pipeline Skill](https://github.com/AiverReaver/blender-unreal-pipeline-skill) | FBX 검증 및 UE 전달 |
| R10 | [ComfyUI-Video2MotionCapture](https://github.com/AKASubaz/ComfyUI-Video2MotionCapture) | video mocap workflow |
| R11 | [ActionMesh](https://github.com/facebookresearch/actionmesh) | 4D mesh 연구, skeletal pipeline과 구분 |
| R12 | [AI-native game dev case](https://www.singhabhilasha.com/case-studies/ai-native-pipeline.html) | AI mesh와 Blender/Claude 활용 |
| R13 | [Viggle game dev](https://viggle.ai/gamedev/) | 영상 기반 전투 애니메이션 사례 후보 |

## 공식 문서 및 기술 후보

| ID | URL | 활용 |
|---|---|---|
| T01 | [Claude Code docs](https://code.claude.com/docs/en/overview) | Skills, Agents, Hooks, MCP |
| T02 | [MCP](https://modelcontextprotocol.io/) | tool protocol |
| T03 | [Blender Python API](https://docs.blender.org/api/current/) | bpy |
| T04 | [Blender MCP](https://github.com/ahujasid/mcp-for-blender) / [CLI MCP candidate](https://github.com/bpy-dev/blender-mcp) | 직접 제어, headless 후보 (repo 경로 확인 필요) |
| T05 | [Rigify](https://docs.blender.org/manual/en/latest/addons/rigging/rigify/) | template rig |
| T06 | [Tripo API](https://developers.tripo3d.com/) | mesh |
| T07 | [Tripo Rigging](https://developers.tripo3d.com/en/docs/animations-rig) | auto rig |
| T08 | [UniRig](https://github.com/VAST-AI-Research/UniRig) | skeleton/weight |
| T09 | [ComfyUI](https://github.com/Comfy-Org/ComfyUI) / [Wan2.2](https://github.com/Wan-Video/Wan2.2) | 영상 생성 |
| T10 | [FFmpeg](https://ffmpeg.org/documentation.html) | video preprocessing |
| T11 | [GVHMR](https://github.com/zju3dv/GVHMR) | motion recovery |
| T12 | [DeepMotion REST API](https://github.com/DeepMotion/Animate-3D-REST-API) | cloud mocap |
| T13 | [HY-Motion 1.0](https://github.com/Tencent-Hunyuan/HY-Motion-1.0) | text motion |
| T14 | [Viggle MCP](https://viggle.ai/mcp) / [Scenario skills](https://github.com/scenario-labs/skills) | provider integration |
| T15 | [Video-to-3D-Animation](https://github.com/harlynkingm/Video-to-3D-Animation) | human/object interaction 후보 |
| T16 | [UE Python 5.7](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/?application_version=5.7) | editor automation |
| T17 | [AssetImportTask](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AssetImportTask?application_version=5.7) | import |
| T18 | [IKRetargetBatchOperation](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/IKRetargetBatchOperation?application_version=5.7) | retarget |
| T19 | [AnimationLibrary](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AnimationLibrary?application_version=5.7) | animation/notify |
| T20 | [AnimMontageFactory](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AnimMontageFactory?application_version=5.7) | montage |

## 근거와 자체 제안의 구분

Blender scripting, MCP 제어, 전문 리깅 및 motion recovery, UE editor API는 활용 기술 범주다. 각 구현체의 실제 제공 기능/호환성은 검증해야 한다. 통합 DAG/state, checkpoint 정책, unified NPZ schema, QA 기준값, AstralBreak GAS metadata 및 전체 시스템 결합은 자체 설계 제안이다. 특정 저장소가 이 전체 기능을 구현했다거나 상용 품질을 보장한다고 주장하지 않는다.

검증 결과는 URL, 접근일, commit/tag, README/코드 경로, license (code/weights/assets 별도), 실제 실행 여부, 지원 버전, 재사용 가능 기능, blocker, 대체 후보를 표로 기록한다. 문서만 확인한 경우 실행 검증과 구분한다. 앞선 대화의 특정 성공률 및 제작 시간은 독립 검증 없이 설계 기준으로 사용하지 않는다.
