#pragma once

#include "CoreMinimal.h"
#include "GameplayEffect.h"
#include "AstralGE_Cost_Ult.generated.h"

/**
 * 오의 비용 GE — 오의 게이지를 통째로 쓴다 (설계 Docs/Design/m4-ult-chain.md §2).
 *  - Instant, UltGauge 에 (MaxUltGauge × −1) 을 더한다. 크기는 소스(= 오너)의 MaxUltGauge 에서 읽는다
 *  - 엔진의 비용 검사(CanApplyAttributeModifiers)는 '현재값 + 비용 < 0 이면 거부' 라서 게이지가 가득일 때만 통과한다 —
 *    '가득인가' 를 보는 코드를 GA 에 따로 쓰지 않는다. 최대치가 빌드로 바뀌어도 맞는다
 * 네이티브 클래스로 두는 이유: 규칙('전부 쓴다')이 데이터로 바뀔 일이 없고, 속성 기반 크기를 애셋으로 저작하면 실수하기 쉽다.
 * 바꿔야 하면 오의 GA BP 의 Cost Gameplay Effect Class 를 다른 GE 로 갈아 끼운다.
 */
UCLASS()
class ASTRALBREAK_API UAstralGE_Cost_Ult : public UGameplayEffect
{
	GENERATED_BODY()

public:
	UAstralGE_Cost_Ult();
};
