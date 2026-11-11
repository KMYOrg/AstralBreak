#include "AstralPartyFlowTestController.h"

#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "GameFramework/PlayerState.h"
#include "GameModes/AstralGameState.h"
#include "GameModes/AstralHubGameState.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Player/AstralPlayerController.h"
#include "Player/AstralPlayerState.h"

DEFINE_LOG_CATEGORY_STATIC(LogAstralNetTest, Display, All);

namespace AstralPartyFlowController
{
	const TCHAR* const HubMap = TEXT("HubMap");
	const TCHAR* const RaidMap = TEXT("RaidMap");

	/** 거부 확인 — RPC 가 서버에 닿아 처리될 시간. 이 뒤에 '안 바뀜' 을 본다 */
	const double RejectHoldSeconds = 3.0;

	/** 끝난 뒤 남의 확인을 기다려 주는 시간 — 먼저 나가면 남은 프로세스가 인원 변화를 먼저 본다 */
	const double ExitGraceSeconds = 3.0;

	const double LingerSeconds = 30.0;

	FString JoinIds(const TArray<int32>& Ids)
	{
		return FString::JoinBy(Ids, TEXT(","), [](int32 Id) { return FString::FromInt(Id); });
	}
}

/** 한 틱에 본 것 — 월드는 이동 때마다 바뀌므로 저장하지 않고 매 틱 다시 만든다 */
struct FAstralPartyFlowSnapshot
{
	UWorld* World = nullptr;
	ENetMode NetMode = NM_Standalone;
	FString Map;

	/** PlayerArray 의 PlayerId — 오름차순. 번호를 못 받은 항목이 있으면 비운다 */
	TArray<int32> Ids;
	int32 LeaderId = INDEX_NONE;

	AAstralPlayerController* LocalPC = nullptr;
	int32 MyId = 0;

	FString SelectedRaid;
	int32 NumOthers = 0;
	int32 NumOthersReady = 0;
	bool bAllReady = false;
};

const TCHAR* UAstralPartyFlowTestController::RoleName(ERole InRole)
{
	switch (InRole)
	{
	case ERole::Server:    return TEXT("server");
	case ERole::Leader:    return TEXT("leader");
	case ERole::NonLeader: return TEXT("nonleader");
	default:               return TEXT("unknown");
	}
}

void UAstralPartyFlowTestController::OnInit()
{
	FString Scenario;
	FParse::Value(FCommandLine::Get(), TEXT("AstralPartyScenario="), Scenario);
	bLeaderLeavesScenario = Scenario.Equals(TEXT("LeaderLeaves"), ESearchCase::IgnoreCase);
	FParse::Value(FCommandLine::Get(), TEXT("AstralPartyPlayers="), NumPlayers);
	FParse::Value(FCommandLine::Get(), TEXT("AstralPartyTimeout="), TimeoutSeconds);

	StartTime = StageStartTime = FPlatformTime::Seconds();

	UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST INIT scenario=%s players=%d timeout=%.0f"),
		bLeaderLeavesScenario ? TEXT("LeaderLeaves") : TEXT("Flow"), NumPlayers, TimeoutSeconds);

	if (NumPlayers < 2 || (bLeaderLeavesScenario && NumPlayers < 3))
	{
		Fail(TEXT("AstralPartyPlayers must be >= 2 (LeaderLeaves: >= 3)"));
	}
}

bool UAstralPartyFlowTestController::TakeSnapshot(FAstralPartyFlowSnapshot& Out) const
{
	UWorld* World = GetWorld();
	if (!World || !World->HasBegunPlay())
	{
		return false;
	}

	Out.World = World;
	Out.NetMode = World->GetNetMode();
	Out.Map = World->GetMapName();

	const UGameInstance* GameInstance = World->GetGameInstance();
	Out.LocalPC = GameInstance ? Cast<AAstralPlayerController>(GameInstance->GetFirstLocalPlayerController(World)) : nullptr;
	Out.MyId = (Out.LocalPC && Out.LocalPC->PlayerState) ? Out.LocalPC->PlayerState->GetPlayerId() : 0;

	const AAstralGameState* GameState = World->GetGameState<AAstralGameState>();
	if (!GameState)
	{
		return true;
	}

	if (const APlayerState* Leader = GameState->GetPartyLeader())
	{
		Out.LeaderId = Leader->GetPlayerId();
	}
	if (const AAstralHubGameState* HubGameState = Cast<AAstralHubGameState>(GameState))
	{
		Out.SelectedRaid = HubGameState->GetSelectedRaid().MapName;
	}

	bool bAllNumbered = true;
	int32 NumReady = 0;
	for (const APlayerState* PlayerState : GameState->PlayerArray)
	{
		if (!PlayerState)
		{
			continue;
		}
		const int32 PlayerId = PlayerState->GetPlayerId();
		bAllNumbered &= (PlayerId != 0);
		Out.Ids.Add(PlayerId);

		const AAstralPlayerState* AstralPlayerState = Cast<AAstralPlayerState>(PlayerState);
		const bool bReady = AstralPlayerState && AstralPlayerState->IsReady();
		NumReady += bReady ? 1 : 0;
		if (Out.MyId == 0 || PlayerId != Out.MyId)
		{
			++Out.NumOthers;
			Out.NumOthersReady += bReady ? 1 : 0;
		}
	}
	Out.bAllReady = Out.Ids.Num() > 0 && NumReady == Out.Ids.Num();
	if (bAllNumbered)
	{
		Out.Ids.Sort();
	}
	else
	{
		Out.Ids.Reset();
	}
	return true;
}

bool UAstralPartyFlowTestController::IsSettled(const FAstralPartyFlowSnapshot& Snap, const TCHAR* Map, int32 InNumPlayers) const
{
	if (Snap.NetMode == NM_Standalone || Snap.Map != Map || Snap.Ids.Num() != InNumPlayers || Snap.LeaderId == INDEX_NONE)
	{
		return false;
	}
	// 플레이어 자리는 내 컨트롤러 · PlayerState 까지 받아야 한다
	return Snap.NetMode == NM_DedicatedServer || (Snap.LocalPC && Snap.MyId != 0 && Snap.Ids.Contains(Snap.MyId));
}

bool UAstralPartyFlowTestController::RecordBase(const FAstralPartyFlowSnapshot& Snap)
{
	BaseIds = Snap.Ids;
	BaseLeaderId = Snap.LeaderId;
	BaseMyId = Snap.MyId;

	if (Snap.NetMode == NM_DedicatedServer)
	{
		Role = ERole::Server;
		if (Snap.LocalPC)
		{
			Fail(TEXT("dedicated server has a local controller"));
			return false;
		}
	}
	else
	{
		Role = (Snap.MyId == Snap.LeaderId) ? ERole::Leader : ERole::NonLeader;
	}

	UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST BASE role=%s netmode=%d my=%d leader=%d ids=%s"),
		RoleName(Role), static_cast<int32>(Snap.NetMode), BaseMyId, BaseLeaderId, *AstralPartyFlowController::JoinIds(BaseIds));

	if (BaseLeaderId != BaseIds[0])
	{
		Fail(FString::Printf(TEXT("leader %d is not the smallest PlayerId %d"), BaseLeaderId, BaseIds[0]));
		return false;
	}
	if (Snap.NetMode == NM_ListenServer && Role != ERole::Leader)
	{
		Fail(TEXT("listen host is not the leader"));
		return false;
	}
	return true;
}

bool UAstralPartyFlowTestController::CheckKept(const FAstralPartyFlowSnapshot& Snap, const TCHAR* Where)
{
	if (Snap.Ids != BaseIds)
	{
		// 하드 트래블이면 새 번호를 받는다 — 시임리스 이월이 깨졌다는 뜻
		Fail(FString::Printf(TEXT("%s: PlayerIds changed across travel (%s -> %s)"), Where,
			*AstralPartyFlowController::JoinIds(BaseIds), *AstralPartyFlowController::JoinIds(Snap.Ids)));
		return false;
	}
	if (Snap.LeaderId != BaseLeaderId)
	{
		Fail(FString::Printf(TEXT("%s: leader changed across travel (%d -> %d)"), Where, BaseLeaderId, Snap.LeaderId));
		return false;
	}
	if (Role != ERole::Server && Snap.MyId != BaseMyId)
	{
		Fail(FString::Printf(TEXT("%s: my PlayerId changed across travel (%d -> %d)"), Where, BaseMyId, Snap.MyId));
		return false;
	}
	UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST KEPT role=%s where=%s leader=%d ids=%s"),
		RoleName(Role), Where, Snap.LeaderId, *AstralPartyFlowController::JoinIds(Snap.Ids));
	return true;
}

void UAstralPartyFlowTestController::OnTick(float TimeDelta)
{
	if (bFinished)
	{
		return;
	}
	if (FPlatformTime::Seconds() - StartTime > TimeoutSeconds)
	{
		Fail(FString::Printf(TEXT("timeout role=%s stage=%d"), RoleName(Role), Stage));
		return;
	}

	FAstralPartyFlowSnapshot Snap;
	if (!TakeSnapshot(Snap))
	{
		return; // 접속 중 · 이동 중
	}

	// 실행 스크립트는 이 줄을 보고 클라이언트를 띄운다
	if (!bReadyLogged && (Snap.NetMode == NM_DedicatedServer || Snap.NetMode == NM_ListenServer) && Snap.Map == AstralPartyFlowController::HubMap)
	{
		bReadyLogged = true;
		UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST READY netmode=%d map=%s"), static_cast<int32>(Snap.NetMode), *Snap.Map);
	}

	if (Snap.NetMode != NM_Standalone)
	{
		bWasConnected = true;
	}
	else if (bWasConnected && !bResultLogged)
	{
		Fail(FString::Printf(TEXT("connection lost role=%s stage=%d map=%s"), RoleName(Role), Stage, *Snap.Map));
		return;
	}

	if (Stage == 0)
	{
		// 허브에 전원이 모일 때까지
		if (IsSettled(Snap, AstralPartyFlowController::HubMap, NumPlayers) && RecordBase(Snap))
		{
			Advance();
		}
		return;
	}

	if (Role != ERole::Server && !Snap.LocalPC)
	{
		return; // 이동 직후 — 내 컨트롤러를 아직 못 받았다
	}

	if (bLeaderLeavesScenario)
	{
		TickLeaderLeaves(Snap);
	}
	else
	{
		TickFlow(Snap);
	}
}

void UAstralPartyFlowTestController::TickFlow(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralPartyFlowController;

	const bool bOthersReady = Snap.NumOthers == NumPlayers - 1 && Snap.NumOthersReady == Snap.NumOthers;

	if (Role == ERole::NonLeader)
	{
		switch (Stage)
		{
		case 1: // 거부당할 요청 — 방장은 내가 준비를 켤 때까지 고르지 않으므로 '안 바뀜' 이 내 요청의 결과다
			Snap.LocalPC->ServerSelectRaid(RaidMap);
			Snap.LocalPC->ServerStartRaid();
			Advance();
			break;
		case 2:
			if (StageAge() >= RejectHoldSeconds)
			{
				if (!Snap.SelectedRaid.IsEmpty() || Snap.Map != HubMap)
				{
					Fail(FString::Printf(TEXT("non-leader SelectRaid/StartRaid was not rejected (raid='%s' map=%s)"), *Snap.SelectedRaid, *Snap.Map));
					return;
				}
				Snap.LocalPC->ServerSetReady(true);
				Advance();
			}
			break;
		case 3:
			if (IsSettled(Snap, RaidMap, NumPlayers) && CheckKept(Snap, RaidMap))
			{
				Snap.LocalPC->ServerReturnToHub();
				Advance();
			}
			break;
		case 4:
			if (StageAge() >= RejectHoldSeconds)
			{
				if (Snap.Map != RaidMap)
				{
					Fail(FString::Printf(TEXT("non-leader ReturnToHub was not rejected (map=%s)"), *Snap.Map));
					return;
				}
				Snap.LocalPC->ServerSetReady(true); // 레이드 맵에서는 '거부 확인 끝' 신호로만 쓴다
				Advance();
			}
			break;
		case 5:
			if (IsSettled(Snap, HubMap, NumPlayers) && CheckKept(Snap, TEXT("HubMap(returned)")))
			{
				Snap.LocalPC->ServerSetReady(true);
				Advance();
			}
			break;
		case 6:
			if (Snap.bAllReady)
			{
				Pass();
				Advance();
			}
			break;
		default:
			TickLinger(Snap, /*bWaitForOthersToLeave=*/false);
			break;
		}
		return;
	}

	if (Role == ERole::Leader)
	{
		switch (Stage)
		{
		case 1: // 비방장들의 거부 확인이 끝난 뒤 — 허용 밖 맵 2종(임의 맵 · 옵션 주입)
			if (bOthersReady)
			{
				Snap.LocalPC->ServerSelectRaid(TEXT("CombatTestMap"));
				Snap.LocalPC->ServerSelectRaid(TEXT("RaidMap?game=/Script/Engine.GameModeBase"));
				Advance();
			}
			break;
		case 2:
			if (StageAge() >= RejectHoldSeconds)
			{
				if (!Snap.SelectedRaid.IsEmpty())
				{
					Fail(FString::Printf(TEXT("map outside the allow list was accepted (raid='%s')"), *Snap.SelectedRaid));
					return;
				}
				Snap.LocalPC->ServerSelectRaid(RaidMap);
				Advance();
			}
			break;
		case 3: // 선택이 복제돼 돌아오면 — 내가 아직 준비 전이라 시작은 거부된다
			if (Snap.SelectedRaid == RaidMap)
			{
				Snap.LocalPC->ServerStartRaid();
				Advance();
			}
			break;
		case 4:
			if (StageAge() >= RejectHoldSeconds)
			{
				if (Snap.Map != HubMap)
				{
					Fail(TEXT("StartRaid went through before everyone was ready"));
					return;
				}
				Snap.LocalPC->ServerSetReady(true);
				Advance();
			}
			break;
		case 5:
			if (Snap.bAllReady && Snap.Map == HubMap)
			{
				Snap.LocalPC->ServerStartRaid();
				Advance();
			}
			break;
		case 6:
			if (IsSettled(Snap, RaidMap, NumPlayers) && CheckKept(Snap, RaidMap))
			{
				Advance();
			}
			break;
		case 7: // 비방장들의 복귀 거부 확인이 끝난 뒤
			if (bOthersReady && Snap.Map == RaidMap)
			{
				Snap.LocalPC->ServerReturnToHub();
				Advance();
			}
			break;
		case 8:
			if (IsSettled(Snap, HubMap, NumPlayers) && CheckKept(Snap, TEXT("HubMap(returned)")))
			{
				Snap.LocalPC->ServerSetReady(true);
				Advance();
			}
			break;
		case 9:
			if (Snap.bAllReady)
			{
				Pass();
				Advance();
			}
			break;
		default:
			TickLinger(Snap, /*bWaitForOthersToLeave=*/Snap.NetMode == NM_ListenServer);
			break;
		}
		return;
	}

	// Dedicated 서버 — 지켜보기만 한다
	switch (Stage)
	{
	case 1:
		if (IsSettled(Snap, RaidMap, NumPlayers) && CheckKept(Snap, RaidMap))
		{
			Advance();
		}
		break;
	case 2:
		if (IsSettled(Snap, HubMap, NumPlayers) && CheckKept(Snap, TEXT("HubMap(returned)")))
		{
			Advance();
		}
		break;
	case 3:
		if (Snap.bAllReady)
		{
			Pass();
			Advance();
		}
		break;
	default:
		TickLinger(Snap, /*bWaitForOthersToLeave=*/true);
		break;
	}
}

void UAstralPartyFlowTestController::TickLeaderLeaves(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralPartyFlowController;

	const bool bLeaderGone = Snap.Ids.Num() == NumPlayers - 1 && !Snap.Ids.Contains(BaseLeaderId);
	const int32 NextLeaderId = BaseIds[1];

	if (Role == ERole::Leader)
	{
		// 남은 사람들이 기준값을 적었다는 신호(준비)를 본 뒤 나간다
		if (Stage == 1 && Snap.NumOthers == NumPlayers - 1 && Snap.NumOthersReady == Snap.NumOthers)
		{
			UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST LEAVING role=leader my=%d"), BaseMyId);
			Pass();
			Finish(0);
		}
		return;
	}

	if (Role == ERole::Server)
	{
		switch (Stage)
		{
		case 1:
			if (bLeaderGone)
			{
				if (Snap.LeaderId != NextLeaderId)
				{
					Fail(FString::Printf(TEXT("after the leader left, leader is %d (expected %d)"), Snap.LeaderId, NextLeaderId));
					return;
				}
				UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST NEWLEADER role=server leader=%d ids=%s"), Snap.LeaderId, *JoinIds(Snap.Ids));
				Advance();
			}
			break;
		case 2:
			if (Snap.SelectedRaid == RaidMap)
			{
				Pass();
				Advance();
			}
			break;
		default:
			TickLinger(Snap, /*bWaitForOthersToLeave=*/true);
			break;
		}
		return;
	}

	// 처음에 방장이 아니던 클라이언트
	const bool bNewLeader = (BaseMyId == NextLeaderId);
	switch (Stage)
	{
	case 1:
		Snap.LocalPC->ServerSetReady(true); // '기준값 적음' 신호
		Advance();
		break;
	case 2:
		if (bLeaderGone)
		{
			if (Snap.LeaderId != NextLeaderId)
			{
				Fail(FString::Printf(TEXT("after the leader left, leader is %d (expected %d)"), Snap.LeaderId, NextLeaderId));
				return;
			}
			UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST NEWLEADER role=%s leader=%d ids=%s"),
				bNewLeader ? TEXT("newleader") : TEXT("nonleader"), Snap.LeaderId, *JoinIds(Snap.Ids));
			if (!bNewLeader)
			{
				Snap.LocalPC->ServerSelectRaid(RaidMap); // 여전히 방장이 아니다 — 거부돼야 한다
			}
			Advance();
		}
		break;
	case 3:
		if (bNewLeader)
		{
			// 남은 비방장들이 거부 확인을 끝내면 준비를 끈다
			if (Snap.NumOthers == NumPlayers - 2 && Snap.NumOthersReady == 0)
			{
				Snap.LocalPC->ServerSelectRaid(RaidMap);
				Advance();
			}
		}
		else if (StageAge() >= RejectHoldSeconds)
		{
			if (!Snap.SelectedRaid.IsEmpty())
			{
				Fail(FString::Printf(TEXT("non-leader SelectRaid was not rejected after the leader left (raid='%s')"), *Snap.SelectedRaid));
				return;
			}
			Snap.LocalPC->ServerSetReady(false); // '거부 확인 끝' 신호
			Advance();
		}
		break;
	case 4:
		if (Snap.SelectedRaid == RaidMap)
		{
			Pass();
			Advance();
		}
		break;
	default:
		TickLinger(Snap, /*bWaitForOthersToLeave=*/false);
		break;
	}
}

void UAstralPartyFlowTestController::TickLinger(const FAstralPartyFlowSnapshot& Snap, bool bWaitForOthersToLeave)
{
	using namespace AstralPartyFlowController;

	if (!bWaitForOthersToLeave)
	{
		if (StageAge() >= ExitGraceSeconds)
		{
			Finish(0);
		}
		return;
	}

	// 서버 · 리슨 호스트 — 먼저 내려가면 클라이언트의 확인이 접속 끊김으로 깨진다
	const int32 NumRemote = (Snap.NetMode == NM_ListenServer) ? Snap.Ids.Num() - 1 : Snap.Ids.Num();
	if ((StageAge() >= ExitGraceSeconds && NumRemote <= 0) || StageAge() >= LingerSeconds)
	{
		Finish(0);
	}
}

void UAstralPartyFlowTestController::Advance()
{
	++Stage;
	StageStartTime = FPlatformTime::Seconds();
	UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST STAGE role=%s stage=%d t=%.1f"), RoleName(Role), Stage, StageStartTime - StartTime);
}

double UAstralPartyFlowTestController::StageAge() const
{
	return FPlatformTime::Seconds() - StageStartTime;
}

void UAstralPartyFlowTestController::Pass()
{
	if (!bResultLogged)
	{
		bResultLogged = true;
		UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST RESULT PASS role=%s my=%d leader=%d"), RoleName(Role), BaseMyId, BaseLeaderId);
	}
}

void UAstralPartyFlowTestController::Fail(const FString& Reason)
{
	if (!bResultLogged)
	{
		bResultLogged = true;
		UE_LOG(LogAstralNetTest, Error, TEXT("ASTRAL_NETTEST RESULT FAIL role=%s reason=%s"), RoleName(Role), *Reason);
	}
	Finish(1);
}

void UAstralPartyFlowTestController::Finish(int32 ExitCode)
{
	if (!bFinished)
	{
		bFinished = true;
		EndTest(ExitCode);
	}
}
