#pragma once

#include "CoreMinimal.h"
#include "GameplayEffect.h"
#include "AstralGE_UltBlocked.generated.h"

/**
 * 오의 차단 — 걸려 있는 동안 State.Ult.Blocked 를 준다 (설계 Docs/Design/m4-ult-chain.md §3 끝 'B 다듬기' ② · §4).
 * 동료가 오의를 쓰는 동안 UAstralChainBurstComponent 가 나머지 히어로에게 걸고, 그 오의가 끝나면 걷는다(무기한 — 걷는 쪽이 책임진다).
 * 효과가 준 태그는 복제되므로 받는 사람의 클라이언트도 발동 전에 안다. M5 의 Burst Aura 도 같은 태그를 쓴다.
 *
 * 네이티브로 둔 이유: 태그 하나를 주는 것이 전부라 데이터로 바뀔 것이 없다. 갈아 끼우려면 체인 컴포넌트의 UltBlockEffectClass 를 바꾼다.
 */
UCLASS()
class ASTRALBREAK_API UAstralGE_UltBlocked : public UGameplayEffect
{
	GENERATED_BODY()

public:
	UAstralGE_UltBlocked();
};
