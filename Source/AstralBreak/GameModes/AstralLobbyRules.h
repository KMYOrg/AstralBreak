#pragma once

#include "CoreMinimal.h"
#include "GameModes/AstralPartyStatics.h"
#include "AstralLobbyRules.generated.h"

/**
 * 로비 요청이 왜 안 되는가 — 서버 RPC 의 거절과 화면(버튼 켜고 끔 · 이유 한 줄)이 같은 값을 쓴다.
 * 순서는 판정 순서와 같지 않다(판정 순서는 AstralLobby::Check… 의 주석)
 */
UENUM(BlueprintType)
enum class EAstralLobbyDenial : uint8
{
	None,
	/** 허브(AAstralHubGameState)가 아닌 맵 — 고르기 · 출정만 막는다 */
	NotInHub,
	/** 방장이 아님 — 고르기 · 출정은 방장만 */
	NotLeader,
	/** 목적지 목록(AAstralHubGameState::RaidDestinations)에 없는 맵 */
	RaidNotAllowed,
	/** 목적지를 아직 안 골랐다 */
	NoRaidSelected,
	/** 파티원 중 준비 안 된 사람이 있다 */
	NotAllReady
};

/** 고를 수 있는 레이드 하나 — 허용 목록이자 보이는 이름의 단일 원천(AAstralHubGameState::RaidDestinations) */
USTRUCT(BlueprintType)
struct FAstralRaidDestination
{
	GENERATED_BODY()

	/** ServerTravel 주소가 되는 맵 이름 — 대소문자까지 정확히 같은 것만 받는다 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Astral|Lobby")
	FString MapName;

	/** 화면에 보이는 이름 */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Astral|Lobby")
	FText DisplayName;
};

/** 로비 판정 입력 1명 — 방장 선정 입력(FAstralPartyMember)에 준비 여부를 더한 것 */
struct FAstralLobbyMember
{
	FAstralPartyMember Party;
	bool bIsReady = false;
};

/**
 * 로비 판정 입력 — 수집 시점의 스냅숏(AAstralGameState::MakeLobbySnapshot 이 만든다). 순수 함수는 이 값만 본다.
 * 서버는 RPC 안에서, 화면은 통지를 받을 때마다 같은 모양으로 만들어 같은 함수에 넣는다 — 화면 쪽은 표시일 뿐이고 최종 판정은 서버다
 */
struct FAstralLobbySnapshot
{
	/** 허브 맵인가(GameState 가 AAstralHubGameState) */
	bool bInHub = false;

	/** PlayerArray 순서 그대로 · 거르기 전 — 누가 파티원인가는 AstralParty::IsPartyMember 한 곳이 정한다 */
	TArray<FAstralLobbyMember> Members;

	/** 요청한 사람 — Members 의 인덱스. 명단에 없으면 INDEX_NONE */
	int32 RequesterIndex = INDEX_NONE;

	/** 방장이 고른 목적지(맵 이름). 안 골랐으면 빈 문자열 */
	FString SelectedRaid;

	/** 고를 수 있는 맵 이름 — RaidDestinations 순서 */
	TArray<FString> AllowedRaids;
};

/**
 * 로비 규칙 순수 함수 — 준비 · 목적지 고르기 · 출정 (설계 Docs/Design/ui-autogen-pipeline.md §11 'Phase 3 설계' ③ · 'Phase 3-4 결과').
 * 월드 없이 시험한다(AstralBreak.Lobby.Rules). 방장 · 파티원 규칙은 AstralParty 의 것을 그대로 쓴다.
 */
namespace AstralLobby
{
	/**
	 * 준비 켜고 끔 — 지금은 막는 규칙이 없다(누구나 · 어느 맵에서나). 레이드 맵 · 시험 맵에서도 준비 값을 신호로 쓰는 시험이 있고,
	 * 준비 값은 이동 때 넘어가지 않아 막아서 얻는 것도 없다. 규칙이 생기면(예: 로드아웃이 있어야 준비) 여기 한 곳에 더한다
	 */
	ASTRALBREAK_API EAstralLobbyDenial CheckReady(const FAstralLobbySnapshot& Snapshot);

	/** 목적지 고르기 — 방장 아님 → 허브 아님 → 목록에 없음 순서(서버 거절 로그를 세는 시험이 이 순서에 기댄다) */
	ASTRALBREAK_API EAstralLobbyDenial CheckSelect(const FAstralLobbySnapshot& Snapshot, const FString& MapName);

	/** 출정 — 방장 아님 → 허브 아님 → 목적지 미선택 → 목록에 없음 → 전원 준비 아님 순서 */
	ASTRALBREAK_API EAstralLobbyDenial CheckStart(const FAstralLobbySnapshot& Snapshot);

	/** 파티원(봇 · 관전자 · 번호 없음 제외)이 한 명 이상이고 모두 준비됐다 */
	ASTRALBREAK_API bool AreAllMembersReady(const FAstralLobbySnapshot& Snapshot);

	/** 방장 — Members 의 인덱스(AstralParty::SelectLeaderIndex). 없으면 INDEX_NONE */
	ASTRALBREAK_API int32 SelectLeaderIndex(const FAstralLobbySnapshot& Snapshot);

	/** 화면의 줄 — 파티원을 PlayerId 순으로 최대 MaxRows 명(Members 의 인덱스) */
	ASTRALBREAK_API TArray<int32> SelectRowIndices(const FAstralLobbySnapshot& Snapshot, int32 MaxRows);

	/** 허용 목록과 정확히(대소문자 포함) 같은 이름만 참 — 옵션(?…)이 붙은 문자열은 거짓 */
	ASTRALBREAK_API bool IsRaidAllowed(TConstArrayView<FString> AllowedRaids, const FString& MapName);

	/** 지금 상태에서 버튼을 못 누르는 까닭(이유 한 줄). None 이면 빈 글 */
	ASTRALBREAK_API FText GetDenialText(EAstralLobbyDenial Denial);

	/** 서버가 요청을 거절했을 때의 글 — 지금 상태의 까닭과 구별된다 */
	ASTRALBREAK_API FText GetRequestDeniedText(EAstralLobbyDenial Denial);

	/** 로그용 이름 */
	ASTRALBREAK_API const TCHAR* LexToString(EAstralLobbyDenial Denial);
}
