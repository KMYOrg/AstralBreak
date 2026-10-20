#pragma once

#include "CoreMinimal.h"
#include "GameplayEffect.h"
#include "AstralGE_RangedAimHold.generated.h"

/**
 * 사격 자세 유지 GE — 원거리 공격 GA가 활성화(발사 시작)마다 서버에서 오너에 적용한다.
 *  - Has Duration, 지속 시간은 SetByCaller.Duration (GA의 AimHoldSeconds 노브)
 *  - 스택 1 · 재적용 시 지속 시간 갱신 → "일정 시간 안에 계속 쏘는 동안" 유지되는 창
 *  - 대상에 State.Ranged.Aiming 부여 (Mixed 복제라 전 머신이 본다: AnimInstance bIsAiming · 회전 모드 전환)
 * 네이티브 클래스로 두는 이유: 어빌리티 고유 GE 는 GA 소유(GameData 수납 기준 밖)이고, 태그·스택 규칙이 데이터로 바뀔 일이 없다.
 * 지속 시간만 데이터(GA)에서 온다. BP 파생으로 교체 가능(GA 의 AimHoldEffect).
 */
UCLASS()
class ASTRALBREAK_API UAstralGE_RangedAimHold : public UGameplayEffect
{
	GENERATED_BODY()

public:
	UAstralGE_RangedAimHold();
};
