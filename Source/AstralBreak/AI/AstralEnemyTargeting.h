#pragma once

#include "CoreMinimal.h"

/**
 * 적의 타깃 후보 1명 — 수집 시점의 스냅샷.
 * 수집(PlayerArray 순회 · 사망 판정)은 AAstralEnemyController::AcquireTarget 이 하고, 순수 함수는 이 값만 받는다.
 */
struct FAstralEnemyTargetCandidate
{
	FVector Location = FVector::ZeroVector;

	/** 죽었거나 죽는 중 — 후보에서 뺀다 */
	bool bDeadOrDying = false;
};

/**
 * 위협 추첨의 후보 1명 (단위 B) — 위 스냅샷에 적대심 · 최근 피해 · 제외 여부를 더한다.
 * 최근 피해와 제외 여부는 UAstralThreatComponent 가 채운다
 */
struct FAstralEnemyThreatCandidate : FAstralEnemyTargetCandidate
{
	/** 닿을 수 없어 잠시 후보에서 뺀 상태 */
	bool bExcluded = false;

	/** 노려지기 쉬움 — 히어로 Attribute Hostility. 0 이하면 뽑히지 않는다 */
	float Hostility = 100.f;

	/** 최근 창 안에서 이 후보가 이 적에게 넣은 피해 합 */
	float RecentDamage = 0.f;
};

/** 피해 기록 1건 — 시각은 월드 시간(초) */
struct FAstralEnemyDamageEntry
{
	double Time = 0.0;
	float Damage = 0.f;
};

/**
 * 적 타깃 선정 순수 함수 (Docs/Design/m3-enemy-ai.md §8 ② · §9 ① ②)
 * 단위 A 의 규칙 '죽지 않은 후보 중 가장 가까운 것' 은 피해 기록이 없을 때의 규칙으로 남고, 단위 B 가 적대심 가중 추첨을 더한다
 * (Automation 테스트 대상 — 월드 의존 · 시각 · 난수를 전부 인자로 받는다).
 */
namespace AstralEnemyTargeting
{
	/** 히어로 자원 세트가 없는 후보의 적대심 — 세트의 초기값과 같다 */
	constexpr float DefaultHostility = 100.f;

	/**
	 * 가장 가까운 후보의 인덱스 — 죽었거나 죽는 중인 후보는 뺀다.
	 * 거리 동률이면 배열 앞쪽. 후보 없음 = INDEX_NONE.
	 */
	ASTRALBREAK_API int32 SelectNearestIndex(const FVector& Origin, TConstArrayView<FAstralEnemyTargetCandidate> Candidates);

	/**
	 * 가중 뽑기 — 가중치 비율로 한 칸을 고른다. Roll 은 0 ~ 1 (호출하는 쪽이 난수를 넣는다).
	 * 0 이하 가중치는 뽑히지 않는다. 전부 0 이하 · 빈 배열 = INDEX_NONE. Roll 0 = 뽑힐 수 있는 첫 칸, Roll 1 = 마지막 칸
	 */
	ASTRALBREAK_API int32 SelectWeightedIndex(TConstArrayView<float> Weights, float Roll);

	/** 가중치 = max(0, 적대심) × (1 + DamageWeight × 점유율). 점유율은 0 ~ 1 */
	ASTRALBREAK_API float ComputeThreatWeight(float Hostility, float DamageWeight, float DamageShare);

	/** StartTime 부터 Duration 이 아직 안 지났는가 — 유지 시간 · 제외 · 재추첨 간격 · 피해 창이 전부 이 비교다. StartTime 이 음수면 '없음' */
	ASTRALBREAK_API bool IsWithinDuration(double StartTime, double Now, double Duration);

	/** 창 안의 피해 합 — 창 밖 기록은 세지 않는다 */
	ASTRALBREAK_API float SumDamageInWindow(TConstArrayView<FAstralEnemyDamageEntry> Entries, double Now, double Window);

	/** 뽑힐 자격 — 살아 있고 제외 중이 아니며 적대심이 0 보다 크다 */
	ASTRALBREAK_API bool IsThreatEligible(const FAstralEnemyThreatCandidate& Candidate);

	/**
	 * 위협 기준 선정 — 자격 있는 후보 중 누구도 피해를 넣지 않았으면 가장 가까운 후보, 아니면 가중 추첨.
	 * 점유율 = 이 후보의 최근 피해 ÷ 자격 있는 후보 전체의 최근 피해. 후보 없음 = INDEX_NONE
	 */
	ASTRALBREAK_API int32 SelectThreatIndex(const FVector& Origin, TConstArrayView<FAstralEnemyThreatCandidate> Candidates, float DamageWeight, float Roll);
}
