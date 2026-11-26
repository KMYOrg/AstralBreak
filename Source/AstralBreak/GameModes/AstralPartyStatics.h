#pragma once

#include "CoreMinimal.h"

/**
 * 방장 선정 입력 1명 — 수집 시점의 스냅샷.
 * 수집(PlayerArray 순회)은 AAstralGameState::GetPartyLeader 가 하고, 순수 함수는 이 값만 받는다.
 */
struct FAstralPartyMember
{
	/** APlayerState::PlayerId — 로그인 순서대로 커지고 시임리스 이동에서 유지된다 */
	int32 PlayerId = 0;

	/** AI 컨트롤러 소유 PlayerState */
	bool bIsBot = false;

	/** 관전 전용 참가자 */
	bool bIsSpectator = false;
};

/**
 * 파티 규칙 순수 함수
 * 방장은 저장하지 않고 계산한다 — 넷 모드(리슨 · Dedicated)로 갈리는 코드가 없고, 방장이 나가면 인계 코드 없이 다음 사람이 된다
 * (Automation 테스트 대상 — 월드 의존을 인자로 받는다).
 */
namespace AstralParty
{
	/**
	 * 파티원인가 — 명단 거르기의 단일 원천. 방장 · 동료 · 로비 준비 집계 · 허브 화면의 줄이 모두 이 거르기를 탄다.
	 * 봇 · 관전자 · 번호를 아직 못 받은 항목(0 — 클라이언트에서 막 생긴 PlayerState, 서버에서는 로그인 도중 한 프레임)은 파티원이 아니다
	 */
	ASTRALBREAK_API bool IsPartyMember(const FAstralPartyMember& Member);

	/** 파티원 인덱스를 PlayerId 순으로 — 같은 번호가 둘이면 배열 앞쪽 하나(시임리스 교체 중 잠깐 겹침) */
	ASTRALBREAK_API TArray<int32> SortedMemberIndices(TConstArrayView<FAstralPartyMember> Members);

	/**
	 * 방장 인덱스 — 파티원 중 PlayerId 최소(가장 먼저 들어온 사람).
	 * PlayerId 동률이면 배열 앞쪽. 후보 없음 = INDEX_NONE.
	 */
	ASTRALBREAK_API int32 SelectLeaderIndex(TConstArrayView<FAstralPartyMember> Members);

	/** 동료 인덱스 — 나(SelfPlayerId)를 뺀 파티원을 PlayerId 순으로 최대 MaxAllies */
	ASTRALBREAK_API TArray<int32> SelectAllyIndices(TConstArrayView<FAstralPartyMember> Members, int32 SelfPlayerId, int32 MaxAllies);
}
