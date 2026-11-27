# Agent / Skill / MCP

| 역할 | 책임 |
|---|---|
| Master | 요구사항, DAG 계획, 작업 분배, 예산 및 승인 |
| Mesh | geometry, topology, UV, LOD 검사 및 정리 |
| Rigging | skeleton 배치, skinning, pose test, 수정 |
| Motion | 영상 생성/분석, motion 추출 및 생성 |
| Animation | keyframe, retarget, IK, root motion, timing |
| QA | 수치 결과 해석, 시각 비교, 수정 제안 |
| Unreal | import, montage, notify, 검증 |

MVP는 Master + 작업별 Skill로 시작한다. 논리 역할별로 반드시 독립 agent/process를 만들 필요는 없다.

```text
.claude/
  agents/{mesh-artist,rigging-artist,motion-designer,animator,quality-reviewer,unreal-integrator}.md
  skills/{asset-production,mesh-processing,auto-rigging,generate-reference-video,video-to-motion,text-to-motion,create-animation,modify-animation,combat-animation,validate-asset,unreal-export}/SKILL.md
  settings.json
CLAUDE.md
.mcp.json
```

CLAUDE.md는 공통 정책과 문서 인덱스, Skills는 입력/작업 순서/성공 기준, Subagents는 역할 및 접근 도구, MCP는 외부 tool interface, Hooks는 보조 정책 검사. 실제 권한 및 복구는 Core/OS에서 강제한다.

knowledge/ 아래 modeling(topology/UV/optimization), rigging(humanoid/creature/skinning/joint limits), animation(principles/locomotion/combat/grip/foot/root), video(prompt/extraction), unreal(skeleton/export/combat) 규칙을 관리한다.

Tool 호출 결과는 구조화된 상태, artifact ID, 진단, 검사 보고서, 다음 행동 후보를 반환한다. Claude의 임의 스크립트는 별도 승인 및 sandbox가 필요한 예외 경로다.

참고: R01, R02, R03, T01, T02 (13_REFERENCES.md).
