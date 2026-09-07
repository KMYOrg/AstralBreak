#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"

class UAnimMontage;

#if !UE_BUILD_SHIPPING
/**
 * 공격 몽타주 검증 — 런타임 순서 추론이 아니라 데이터(노티파이)를 직접 대조
 * 애셋 설정은 C++이 강제할 수 없으므로 이 로그가 유일한 강제 수단. 활성화 1회차에 GA가 호출 (InstancedPerActor라 폰당 1회)
 */
namespace AstralAttackMontage
{
	/**
	 * Facing 워프 밴드 검증 (락온 4단계):
	 *   - UAnimNotifyState_MotionWarping 0개 = Warning(이 몽타주는 보정 없음) · 2개 이상 = Error
	 *   - 모디파이어 WarpTargetName == ExpectedWarpTargetName · bWarpRotation == true · bWarpTranslation == false (Error)
	 *   - 밴드 시작 < 종료 (Error) · 밴드 종료 ≤ WeaponTrace 밴드 시작 (Warning — 늦게 끝나면 전진이 곡선으로 휜다)
	 *   - 몽타주에 루트모션 없음 = Warning (워프 훅이 호출되지 않아 밴드가 무효)
	 * @param Context 로그 접두 (GA 이름 · 스테이지 등)
	 */
	ASTRALBREAK_API void ValidateFacingWarpBand(const UAnimMontage* Montage, FName ExpectedWarpTargetName, const FGameplayTag& TraceBeginEventTag, const FString& Context);
}
#endif
