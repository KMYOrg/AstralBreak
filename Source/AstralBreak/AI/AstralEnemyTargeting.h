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
 * 적 타깃 선정 순수 함수 (Docs/Design/m3-enemy-ai.md §8 ②)
 * 단위 A 의 규칙은 '죽지 않은 후보 중 가장 가까운 것' 하나다. 단위 B 가 위협 표를 들이면 AcquireTarget 의 안쪽이 바뀌고 이 함수는 첫 인지 규칙으로 남는다
 * (Automation 테스트 대상 — 월드 의존을 인자로 받는다).
 */
namespace AstralEnemyTargeting
{
	/**
	 * 가장 가까운 후보의 인덱스 — 죽었거나 죽는 중인 후보는 뺀다.
	 * 거리 동률이면 배열 앞쪽. 후보 없음 = INDEX_NONE.
	 */
	ASTRALBREAK_API int32 SelectNearestIndex(const FVector& Origin, TConstArrayView<FAstralEnemyTargetCandidate> Candidates);
}
