#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"

class UIKRetargeterController;
struct FAnimMcpContext;

/**
 * 대상 리타깃 포즈의 본 대 본 정렬 (create_ik_retargeter align_mode per_bone) — 엔진 자동 정렬(ChainToChain) 뒤에 덧씌운다.
 *
 * 실측 근거 (2026-10-24, CMU · SOMA · UE4 HK → Vesper):
 *   - FK op Interpolated 는 대상 본을 체인 param 위치로 소스와 짝짓고 그 자리의 소스 회전을 섞는다(FKChainsOp.cpp:283-291,
 *     IKRetargetProcessor.cpp:671-707). 팔꿈치 param 이 다르면(Vesper 0.512 · CMU 0.589) 굽힘이 0.87 배만 전달된다.
 *   - 엔진 정렬은 대상 본과 같은 param 의 소스 접선에 맞춘다 — 소스 기준 포즈 팔꿈치가 굽어 있으면(HK) 접선이 팔꿈치를 걸쳐
 *     아래팔이 6° 어긋난다. 체인 끝 본은 접선이 없어 건너뛴다(IKRetargeterPoseGenerator.cpp:386) — 목 끝 · 손 굴림이 남는다.
 *
 *   - 축 체인(척추 · 목)을 소스 기준 포즈 모양에 맞추면(엔진: 척추 접선 · AlignPelvisBone, ②③: 목) 소스 골격의 정형화된 몸통 모양이 모든 프레임에
 *     붙는다 — 목 윗마디의 몸통선 대비 기울기 Vesper 기준 −14.2° · CMU +0.7° → CMU 결과 p50 +5.5°(고개를 들면 목이 길고 뒤로 젖혀짐),
 *     SOMA 기준 −19.5° → 클립 −41.5°(Vesper 기준 대비 −27°). 같은 원인이 스켈레톤마다 반대로 나타난다.
 *   - 메타카팔(손에 매달린 뼈 1개 체인)은 손바닥 해부가 달라(SOMA → Vesper: 손 → 메타카팔 시작 방향 4.8~27° · 길이 5.6~6.4 대 4.3~4.8 cm)
 *     메타카팔 → 첫 마디 구간이 소스와 3.2~7.0° 일정하게 어긋나고, 첫 마디를 소스 전역 방향에 맞추면 MCP 가 −17.5~−1.7° 틀어졌다(2026-10-25,
 *     오른손). 메타카팔을 소스 방향으로 돌리면 MCP 는 맞지만 마디 줄이 움직여 손 굴림 −3.6° · 손바닥 3~7° 변형 — 손가락을 메타카팔 상대로 맞춘다(②').
 *
 * 한다 (FK op 의 매핑 · 프로세서가 해석한 체인 하나를 단일 원천으로 — FK 가 실제로 짝짓는 본끼리 맞춘다):
 *   ① 소스 · 대상 뼈 수가 같은 매핑 체인(2개 이상)은 FK RotationMode = OneToOne. 뼈 수가 다른 체인(척추)은 Interpolated 그대로.
 *   ⓪ 축 체인(정중선 위 · 좌우 짝 없음 — 척추 · 목 · head)과 펠비스는 해부적 중립: 정면 맞춤만 반영한 대상 기준 포즈 전역 회전(소스 짝 본의
 *      리타깃 포즈가 기준과 다르면 그 차도). FK 결과 = 대상 고유 곡선 · 소스가 자기 기준 포즈에서 움직인 만큼. 가정: 양쪽 기준 포즈가 직립.
 *      판정은 이름 없이 대상 기준 포즈 기하로 — 뼈 2개 이상 · 같은 수인 매핑 체인 쌍이 두 시작 관절의 수직이등분면에 비춰 본마다 겹치면 거울 짝,
 *      그 좌우축이 가장 많이 모이는 무리(시작 거리 가중 평균)가 좌우축 · 정중선 평면, 그 평면으로 뼈 1개 체인(쇄골)까지 다시 짝짓는다(서로 가장 잘 맞는 짝만).
 *      짝이 아니고 모든 본이 '가장 안쪽 짝 반폭 × 0.25' 안이면 축(Vesper: 쇄골 1.76 cm → 0.44 cm, 척추 · 목 · head 0.00 cm). 펠비스 · 그 조상을
 *      품은 체인(루트 — 정면 맞춤)은 빼고 펠비스는 따로. 짝이 없으면 건너뛴다(axial.skipped_reason). 팔 · 다리 정렬(②③)보다 먼저 — 바뀐 몸통 위에서 맞춘다.
 *   ② 축이 아닌 OneToOne 체인의 본 i → i+1 구간을 소스 같은 번호 구간에 최소 회전으로 (뿌리 → 끝 순서, 부모 보정이 자식에 반영된 뒤).
 *   ②' 그 체인의 가장 가까운 매핑 조상이 뼈 1개 체인(메타카팔)이고 그 본의 부모 매핑 본(손)이 정중선 밖이면, 소스 구간 대신 Q · 소스 구간에 —
 *      Q = 소스 '그 본 → 체인 시작' 구간을 대상 같은 구간으로 돌리는 최소 회전(손 ③ 이 끝난 리타깃 포즈 — 본 순서상 팔이 먼저). 메타카팔 배치
 *      (손바닥)는 대상 체형 그대로, 관절 각(MCP · PIP)만 소스를 복사한다 — 손가락 전역 방향은 Q 만큼 대상 고유 벌림을 띤다. 쇄골 → 팔은 부모
 *      (척추 끝)가 정중선 위라 해당 없음(팔은 소스 전역 방향 그대로), 정중선이 없으면 건너뛴다.
 *   ③ 체인 끝 본 = 그 본 바로 아래에서 시작하는 매핑 체인(가장 가까운 매핑 조상이 끝 본)의 시작 관절이 랜드마크 — 자손이 있는
 *      뼈 1개 체인(메타카팔)은 건너뛰고 그 아래 체인 시작(손가락 첫 마디)을 쓴다. 1개 → 방향만. 2개 이상이고 양쪽 모두 퍼져 있으면
 *      (최대 사이각 ≥ 10°) Horn 최소제곱으로 기준틀 전체, 잔차 15° 넘는 랜드마크(엄지 시작 — 관절 자리가 다르다)는 빼고 다시. 그 회전의
 *      체인 축(부모 → 끝 본) 둘레 성분은 체인 부모가 맡는다(손 굴림을 아래팔이 — 손목이 비틀리지 않게).
 *   ④ 축이 아닌 랜드마크 없는 말단 체인(뼈 1개 · 그 본 아래에서 시작하는 매핑 체인 없음)은 ⓪ 과 같은 중립. 엔진은 이 본을 건너뛰어(param 1 —
 *      접선 없음) 조상 정렬에 끌려간 채 두고, 그 기울기가 모든 프레임에 붙었다(head 실측: CMU → Vesper 얼굴 +6.8° 위 · SOMA −3.7° 아래 — head 는 이제 ⓪).
 * 하지 않는다: 자손 체인이 있는 뼈 1개 체인 자체(쇄골 · 메타카팔 — 관절 위치가 해부적으로 다르다; 메타카팔 아래 손가락은 ②' 가 상대로),
 *   제외 본(템플릿 BonesToExcludeFromAutoPose — 발).
 * 원칙: 기준 포즈 관례가 다른 부위(팔 · 다리 — T 대 A 포즈)는 소스에 맞추고, 같은 자세(직립)를 뜻하는 부위의 차이는 체형이니 대상 것을 둔다.
 */
namespace AnimMcpRetargetPoseAlign
{
	/**
	 * 현재 대상 리타깃 포즈에 ①⓪②②'③④. FacingRotation = 정면 맞춤이 대상 전체에 건 전역 회전(루트 전역 = FacingRotation · 기준, 없으면 단위).
	 * 반환 {mode, one_to_one_chains[], interpolated_chains[], bones[{bone, deg}], relative_chains[{chain, parent_bone, offset_deg}](②'), chain_ends[],
	 * axial{lateral_axis[3], tolerance_cm, mirror_pairs[[a, b]],
	 * chains[], pelvis|null} | {skipped_reason}, neutral_bones[{bone, deg}](펠비스 · 축 · ④), skipped[]}
	 */
	TSharedRef<FJsonObject> AlignPerBone(const UIKRetargeterController* Controller, const TArray<FName>& ExcludedBones, const FQuat& FacingRotation, FAnimMcpContext& Context);
}
