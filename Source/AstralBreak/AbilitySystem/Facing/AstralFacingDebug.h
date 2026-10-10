#pragma once

#include "CoreMinimal.h"

class UGameplayAbility;
class UAstralFacingSession;
struct FAstralFacingStageResolution;

/**
 * Facing 진단 — 테스트 훅(송신 생략·중복 송신)과 프로세스 전역 카운터, 단계 확정 로그.
 * 카운터는 프로세스 전역이라 One Process PIE에서는 호스트·클라 수치가 섞인다 — Separate Process에서 읽을 것.
 * Shipping에서는 전부 no-op 스텁 — 호출부에 #if를 두지 않는다
 */
namespace AstralFacingDebug
{
#if !UE_BUILD_SHIPPING
	/** Astral.Facing.Debug.DropSendStage — 이 단계의 송신을 생략한다. 0이면 활성화 이벤트에 빈 페이로드 (서버 Missing · 로컬 폴백 캡처 → 불일치 재현) */
	ASTRALBREAK_API bool ShouldDropSend(int32 StageIndex);

	/** Astral.Facing.Debug.DuplicateSend — Stage 1~N TargetData를 두 번 보낸다 (DuplicateIgnored 분류 확인) */
	ASTRALBREAK_API bool ShouldDuplicateSend();

	/** 카운터 — 정상 승인 경로와 예외 경로를 분리해 본다. Prepared(작성)와 TargetDataSendAttempts(송신)는 다른 의미 */
	struct FStats
	{
		/** Stage 0 페이로드 작성 (활성화 이벤트). 실제 GAS 송신을 가로채지 않는다 — 서버 수신·활성화 로그와 대응시킬 것 */
		int32 Prepared = 0;
		/** Stage 1~N CallServerSetReplicatedTargetData 호출 */
		int32 TargetDataSendAttempts = 0;
		int32 Received = 0;
		int32 StoredEarly = 0;
		int32 Approved = 0;
		int32 ExplicitNone = 0;
		int32 Missing = 0;
		int32 Rejected = 0;
		int32 Duplicate = 0;
		int32 Conflict = 0;
		int32 StageMismatch = 0;
		int32 AfterSession = 0;
		/** 같은 단계에 AdvanceStage가 두 번 — 세션이 이전 결과를 돌려준 횟수 */
		int32 DuplicateAdvance = 0;

		void Reset() { *this = FStats(); }
		FString ToString() const;
	};
	ASTRALBREAK_API FStats& GetStats();

	/**
	 * 단계 확정 로그 — 몽타주 위치·워프 이름·폰 충돌 정책은 적용 시점의 GA에서 수집한다.
	 * 세션은 CMC·AnimInstance를 모르므로 여기서 아바타를 통해 읽는다
	 */
	ASTRALBREAK_API void LogStageDecision(const UGameplayAbility* Ability, const UAstralFacingSession* Session, const FAstralFacingStageResolution& Resolution, FName WarpTargetName);
#else
	FORCEINLINE bool ShouldDropSend(int32) { return false; }
	FORCEINLINE bool ShouldDuplicateSend() { return false; }
	FORCEINLINE void LogStageDecision(const UGameplayAbility*, const UAstralFacingSession*, const FAstralFacingStageResolution&, FName) {}
#endif
}

#if !UE_BUILD_SHIPPING
#define ASTRAL_FACING_STAT(Field) (++AstralFacingDebug::GetStats().Field)
#else
#define ASTRAL_FACING_STAT(Field)
#endif
