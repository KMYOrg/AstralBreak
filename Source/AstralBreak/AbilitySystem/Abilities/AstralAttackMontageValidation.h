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
	/** GameplayEventWindow NotifyState 중 Begin 태그가 일치하는 가장 이른 시작 시각 — 근접의 WeaponTrace 밴드 경계 */
	ASTRALBREAK_API TOptional<float> FindEarliestWindowBegin(const UAnimMontage* Montage, const FGameplayTag& BeginEventTag);

	/**
	 * 단발 발사 노티파이 검증 (6단계) — UAstralAnimNotify_GameplayEvent(FireEventTag):
	 *   - 정확히 1개 (0개·2개 이상 = Error)
	 *   - TriggerTime > 0 (Error — 엔진 추출 조건 `Start <= Cur && End > Prev`상 첫 틱(Prev=0)에 누락된다)
	 * @return 발사 시각 (검증 실패면 미설정)
	 */
	ASTRALBREAK_API TOptional<float> ValidateFireNotify(const UAnimMontage* Montage, const FGameplayTag& FireEventTag, const FString& Context);

	/**
	 * Facing 워프 밴드 검증 (락온 4단계):
	 *   - UAnimNotifyState_MotionWarping 0개 = Warning(이 몽타주는 보정 없음) · 2개 이상 = Error
	 *   - 모디파이어 WarpTargetName == ExpectedWarpTargetName · bWarpRotation == true · bWarpTranslation == false (Error)
	 *   - 밴드 시작 < 종료 (Error) · 밴드 종료 ≤ BoundaryTime (Warning — 늦게 끝나면 전진이 곡선으로 휘거나 발사 방향과 어긋난다)
	 *   - 몽타주에 루트모션 없음 = Warning (워프 훅이 호출되지 않아 밴드가 무효)
	 * @param BoundaryTime 워프가 끝나야 하는 시각 — 근접은 FindEarliestWindowBegin(WeaponTrace), 원거리는 ValidateFireNotify. 미설정이면 순서 검사 생략
	 * @param Context 로그 접두 (GA 이름 · 스테이지 등)
	 */
	ASTRALBREAK_API void ValidateFacingWarpBand(const UAnimMontage* Montage, FName ExpectedWarpTargetName, TOptional<float> BoundaryTime, const FString& Context);

	/**
	 * 폰 충돌 정책 밴드 검증 (root-motion-pawn-collision-policy.md):
	 *   - 밴드 없음 = Warning (공격 루트모션이 적 캡슐을 따라 슬라이드해 적 주위를 돈다)
	 *   - 같은 NotifyState 인스턴스가 두 번 배치 = Error (TObjectKey가 같아져 CMC가 둘을 구분 못 한다)
	 *   - 밴드끼리 부분 겹침 = Error (완전 중첩 또는 비겹침만 허용, A.End == B.Begin 인접은 허용)
	 */
	ASTRALBREAK_API void ValidatePawnCollisionBands(const UAnimMontage* Montage, const FString& Context);
}
#endif
