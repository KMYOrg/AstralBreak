// 파티 흐름 네트워크 시험 — 한 프로세스 멀티 PIE (설계 Docs/Design/m3-enemy-ai.md §7-2 ①)
//
// 리슨 서버 · Dedicated 를 PIE 로 띄우고 각 클라이언트 월드의 컨트롤러에서 Server RPC 를 직접 부른다(실제 넷 드라이버 경유).
//   - 거부 판정: 서버 상태가 안 바뀜 + 거부 경고 로그가 정해진 횟수만큼(AddExpectedError)
//   - 시임리스 판정: 이동 뒤 PlayerId 집합이 그대로 (하드 트래블이면 새 번호를 받는다)
// 별도 프로세스 구성은 AstralPartyFlowTestController + Tools/net_test/run_party_flow.py 가 맡는다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Editor.h"
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "GameFramework/PlayerState.h"
#include "GameModes/AstralGameState.h"
#include "GameModes/AstralHubGameState.h"
#include "PlayInEditorDataTypes.h"
#include "Player/AstralPlayerController.h"
#include "Settings/LevelEditorPlaySettings.h"

namespace AstralPartyFlowPie
{
	const TCHAR* const HubMapPath = TEXT("/Game/Maps/HubMap");
	const TCHAR* const HubMap = TEXT("HubMap");
	const TCHAR* const RaidMap = TEXT("RaidMap");

	/** 플레이어 한 자리 — 로컬 컨트롤러가 있는 PIE 월드 (리슨: 호스트 + 클라이언트들, Dedicated: 클라이언트들) */
	struct FSeat
	{
		UWorld* World = nullptr;
		AAstralPlayerController* PC = nullptr;
		int32 PlayerId = 0;
	};

	struct FContext
	{
		FAutomationTestBase* Test = nullptr;
		bool bDedicated = false;
		int32 NumPlayers = 0;

		/** 한 단계라도 제한 시간을 넘기면 이후 단계를 건너뛰고 PIE 만 정리한다 */
		bool bAborted = false;
		bool bPieRequested = false;

		/** 처음 허브에 모였을 때의 스냅샷 — 이동 뒤 비교 기준 */
		TArray<int32> PlayerIds;
		int32 LeaderId = INDEX_NONE;
	};

	// ─── 월드 조회 — 이동 때마다 월드가 바뀌므로 저장하지 않고 매번 다시 찾는다 ───

	TArray<UWorld*> GetPieWorlds()
	{
		TArray<UWorld*> Out;
		for (const FWorldContext& WorldContext : GEngine->GetWorldContexts())
		{
			if (WorldContext.WorldType == EWorldType::PIE && WorldContext.World())
			{
				Out.Add(WorldContext.World());
			}
		}
		return Out;
	}

	UWorld* FindServerWorld()
	{
		for (UWorld* World : GetPieWorlds())
		{
			const ENetMode NetMode = World->GetNetMode();
			if (NetMode == NM_ListenServer || NetMode == NM_DedicatedServer)
			{
				return World;
			}
		}
		return nullptr;
	}

	FString MapOf(const UWorld* World)
	{
		return World ? UWorld::RemovePIEPrefix(World->GetMapName()) : FString();
	}

	AAstralPlayerController* GetLocalPC(const UWorld* World)
	{
		const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
		return GameInstance ? Cast<AAstralPlayerController>(GameInstance->GetFirstLocalPlayerController(World)) : nullptr;
	}

	/** 접속 중인 자리 전부. 아직 PlayerState · PlayerId 를 못 받은 자리는 PlayerId 0 */
	TArray<FSeat> GetSeats()
	{
		TArray<FSeat> Out;
		for (UWorld* World : GetPieWorlds())
		{
			const ENetMode NetMode = World->GetNetMode();
			if (NetMode != NM_ListenServer && NetMode != NM_Client)
			{
				continue; // Dedicated 서버 월드 · 접속을 끊고 Standalone 이 된 월드
			}
			FSeat Seat;
			Seat.World = World;
			Seat.PC = GetLocalPC(World);
			Seat.PlayerId = (Seat.PC && Seat.PC->PlayerState) ? Seat.PC->PlayerState->GetPlayerId() : 0;
			Out.Add(Seat);
		}
		return Out;
	}

	/** 이 월드가 계산한 방장의 PlayerId (클라이언트 월드에서는 복제된 값으로 한 계산). 없으면 INDEX_NONE */
	int32 LeaderIdIn(const UWorld* World)
	{
		const AAstralGameState* GameState = World ? World->GetGameState<AAstralGameState>() : nullptr;
		const APlayerState* Leader = GameState ? GameState->GetPartyLeader() : nullptr;
		return Leader ? Leader->GetPlayerId() : INDEX_NONE;
	}

	/** 이 월드의 PlayerArray 에 있는 PlayerId — 오름차순. 아직 번호가 없는(0) 항목이 있으면 빈 배열 */
	TArray<int32> PlayerIdsIn(const UWorld* World)
	{
		TArray<int32> Out;
		const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;
		if (!GameState)
		{
			return Out;
		}
		for (const APlayerState* PlayerState : GameState->PlayerArray)
		{
			if (!PlayerState || PlayerState->GetPlayerId() == 0)
			{
				return TArray<int32>();
			}
			Out.Add(PlayerState->GetPlayerId());
		}
		Out.Sort();
		return Out;
	}

	FString SelectedRaidIn(const UWorld* World)
	{
		const AAstralHubGameState* HubGameState = World ? World->GetGameState<AAstralHubGameState>() : nullptr;
		return HubGameState ? HubGameState->GetSelectedRaid().MapName : FString();
	}

	/** 서버와 모든 자리가 Map 에 있고, 서로를 NumPlayers 명으로 본다 */
	bool IsSettled(const TCHAR* Map, int32 NumPlayers)
	{
		const UWorld* ServerWorld = FindServerWorld();
		if (!ServerWorld || !ServerWorld->HasBegunPlay() || MapOf(ServerWorld) != Map || PlayerIdsIn(ServerWorld).Num() != NumPlayers)
		{
			return false;
		}

		const TArray<FSeat> Seats = GetSeats();
		if (Seats.Num() != NumPlayers)
		{
			return false;
		}
		for (const FSeat& Seat : Seats)
		{
			if (Seat.PlayerId == 0 || MapOf(Seat.World) != Map || PlayerIdsIn(Seat.World).Num() != NumPlayers || LeaderIdIn(Seat.World) == INDEX_NONE)
			{
				return false;
			}
		}
		return true;
	}

	AAstralPlayerController* FindSeatPC(int32 PlayerId)
	{
		for (const FSeat& Seat : GetSeats())
		{
			if (Seat.PlayerId == PlayerId)
			{
				return Seat.PC;
			}
		}
		return nullptr;
	}

	// ─── 단계 큐 ───

	void Step(TFunction<bool()> Fn)
	{
		FAutomationTestFramework::Get().EnqueueLatentCommand(MakeShared<FFunctionLatentCommand>(MoveTemp(Fn)));
	}

	/** 한 번 실행. 앞 단계가 실패했으면 건너뛴다 */
	void Do(const TSharedRef<FContext>& Ctx, TFunction<void()> Fn)
	{
		Step([Ctx, Fn = MoveTemp(Fn)]() -> bool
		{
			if (!Ctx->bAborted)
			{
				Fn();
			}
			return true;
		});
	}

	/** 조건이 참이 될 때까지. 조건을 먼저 보고 시간을 본다 — 맵 로드 프레임이 길어도 도착했으면 통과 */
	void WaitUntil(const TSharedRef<FContext>& Ctx, const TCHAR* What, double TimeoutSeconds, TFunction<bool()> Condition)
	{
		TSharedRef<double> StartTime = MakeShared<double>(-1.0);
		Step([Ctx, What = FString(What), TimeoutSeconds, StartTime, Condition = MoveTemp(Condition)]() -> bool
		{
			if (Ctx->bAborted)
			{
				return true;
			}
			if (*StartTime < 0.0)
			{
				*StartTime = FPlatformTime::Seconds();
			}
			if (Condition())
			{
				return true;
			}
			const bool bPieGone = Ctx->bPieRequested && !GEditor->PlayWorld && !GEditor->IsPlaySessionInProgress() && (FPlatformTime::Seconds() - *StartTime > 5.0);
			if (bPieGone || FPlatformTime::Seconds() - *StartTime > TimeoutSeconds)
			{
				const UWorld* ServerWorld = FindServerWorld();
				Ctx->Test->AddError(FString::Printf(TEXT("%s: %s (server map '%s', server players %d, seats %d)"),
					bPieGone ? TEXT("PIE ended while waiting") : TEXT("timed out waiting"), *What,
					*MapOf(ServerWorld), PlayerIdsIn(ServerWorld).Num(), GetSeats().Num()));
				Ctx->bAborted = true;
				return true;
			}
			return false;
		});
	}

	/** 거부 확인용 — RPC 가 서버에 닿아 처리될 시간을 준 뒤 다음 단계에서 '안 바뀜' 을 본다 */
	void Hold(const TSharedRef<FContext>& Ctx, double Seconds)
	{
		TSharedRef<double> StartTime = MakeShared<double>(-1.0);
		Step([Ctx, Seconds, StartTime]() -> bool
		{
			if (Ctx->bAborted)
			{
				return true;
			}
			if (*StartTime < 0.0)
			{
				*StartTime = FPlatformTime::Seconds();
			}
			return FPlatformTime::Seconds() - *StartTime >= Seconds;
		});
	}

	void StartPie(const TSharedRef<FContext>& Ctx)
	{
		Step([Ctx]() -> bool
		{
			if (!GEditor || GEditor->PlayWorld || GEditor->IsPlaySessionInProgress())
			{
				Ctx->Test->AddError(TEXT("PIE is already active — end it before running this test"));
				Ctx->bAborted = true;
				return true;
			}

			// 사용자 플레이 설정에 끌려가지 않게 넷 모드 · 인원 · 프로세스 구성을 명시한다
			FRequestPlaySessionParams Params;
			Params.GlobalMapOverride = HubMapPath;
			ULevelEditorPlaySettings* Settings = NewObject<ULevelEditorPlaySettings>(GetTransientPackage()); // RequestPlaySession 이 복제해 쥔다
			Settings->SetPlayNetMode(Ctx->bDedicated ? PIE_Client : PIE_ListenServer);
			Settings->SetPlayNumberOfClients(Ctx->NumPlayers);
			Settings->SetRunUnderOneProcess(true);
			Params.EditorPlaySettings = Settings;
			GEditor->RequestPlaySession(Params);
			Ctx->bPieRequested = true;
			return true;
		});

		WaitUntil(Ctx, TEXT("all players in HubMap"), 240.0, [Ctx]() { return IsSettled(HubMap, Ctx->NumPlayers); });
	}

	/** 실패했어도 반드시 PIE 를 내린다 */
	void EndPie(const TSharedRef<FContext>& Ctx)
	{
		Step([Ctx]() -> bool
		{
			if (Ctx->bPieRequested && (GEditor->PlayWorld || GEditor->IsPlaySessionInProgress()))
			{
				GEditor->RequestEndPlayMap();
			}
			return true;
		});
		Step([]() -> bool { return GEditor->PlayWorld == nullptr && !GEditor->IsPlaySessionInProgress(); });
	}

	/** 허브에 처음 모였을 때 — 방장이 누구인지와 넷 모드를 확인하고 기준값을 적는다 */
	void RecordAndCheckInitialLeader(const TSharedRef<FContext>& Ctx)
	{
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const UWorld* ServerWorld = FindServerWorld();

			Ctx->PlayerIds = PlayerIdsIn(ServerWorld);
			Ctx->LeaderId = LeaderIdIn(ServerWorld);
			Test.TestEqual(TEXT("server sees every player"), Ctx->PlayerIds.Num(), Ctx->NumPlayers);
			if (Ctx->PlayerIds.Num() > 0)
			{
				Test.TestEqual(TEXT("leader = smallest PlayerId"), Ctx->LeaderId, Ctx->PlayerIds[0]);
			}

			if (Ctx->bDedicated)
			{
				Test.TestEqual(TEXT("server is a dedicated server"), static_cast<int32>(ServerWorld->GetNetMode()), static_cast<int32>(NM_DedicatedServer));
				Test.TestNull(TEXT("dedicated server has no local controller"), GetLocalPC(ServerWorld));
			}
			else
			{
				Test.TestEqual(TEXT("server is a listen server"), static_cast<int32>(ServerWorld->GetNetMode()), static_cast<int32>(NM_ListenServer));
				const AAstralPlayerController* HostPC = GetLocalPC(ServerWorld);
				Test.TestTrue(TEXT("listen host is the leader"), HostPC && HostPC->PlayerState && HostPC->PlayerState->GetPlayerId() == Ctx->LeaderId);
			}

			for (const FSeat& Seat : GetSeats())
			{
				Test.TestEqual(*FString::Printf(TEXT("seat %d computes the same leader from replicated ids"), Seat.PlayerId), LeaderIdIn(Seat.World), Ctx->LeaderId);
			}
		});
	}

	/** 이동 뒤 — 번호 · 방장이 그대로인지 (시임리스 이월) */
	void CheckIdsAndLeaderKept(const TSharedRef<FContext>& Ctx, const TCHAR* Where)
	{
		Do(Ctx, [Ctx, Where = FString(Where)]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const UWorld* ServerWorld = FindServerWorld();

			Test.TestTrue(*FString::Printf(TEXT("%s: PlayerIds kept across travel (seamless)"), *Where), PlayerIdsIn(ServerWorld) == Ctx->PlayerIds);
			Test.TestEqual(*FString::Printf(TEXT("%s: leader kept"), *Where), LeaderIdIn(ServerWorld), Ctx->LeaderId);
			Test.TestEqual(*FString::Printf(TEXT("%s: server net mode kept"), *Where),
				static_cast<int32>(ServerWorld->GetNetMode()), static_cast<int32>(Ctx->bDedicated ? NM_DedicatedServer : NM_ListenServer));

			TArray<int32> SeatIds;
			for (const FSeat& Seat : GetSeats())
			{
				SeatIds.Add(Seat.PlayerId);
				Test.TestEqual(*FString::Printf(TEXT("%s: seat %d still computes the same leader"), *Where, Seat.PlayerId), LeaderIdIn(Seat.World), Ctx->LeaderId);
			}
			SeatIds.Sort();
			Test.TestTrue(*FString::Printf(TEXT("%s: every seat kept its own PlayerId"), *Where), SeatIds == Ctx->PlayerIds);

			if (!Ctx->bDedicated)
			{
				const AAstralPlayerController* HostPC = GetLocalPC(ServerWorld);
				Test.TestTrue(*FString::Printf(TEXT("%s: listen host is still the leader"), *Where),
					HostPC && HostPC->PlayerState && HostPC->PlayerState->GetPlayerId() == Ctx->LeaderId);
			}
		});
	}

	int32 FirstNonLeaderId(const FContext& Ctx)
	{
		for (const int32 PlayerId : Ctx.PlayerIds)
		{
			if (PlayerId != Ctx.LeaderId)
			{
				return PlayerId;
			}
		}
		return INDEX_NONE;
	}

	/** P2 · P4 — 허브 → 레이드 → 허브 전체 흐름 */
	void EnqueueFlow(FAutomationTestBase& Test, bool bDedicated, int32 NumPlayers)
	{
		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;
		Ctx->bDedicated = bDedicated;
		Ctx->NumPlayers = NumPlayers;

		// 거부는 경고 로그로 남는다 — 정해진 횟수만큼 나와야 통과 (안 나오거나 더 나오면 실패)
		Test.AddExpectedError(TEXT("ServerSelectRaid: 방장이 아님"), EAutomationExpectedErrorFlags::Contains, 1, /*IsRegex=*/false);
		Test.AddExpectedError(TEXT("ServerSelectRaid: 허용 목록에 없는 맵"), EAutomationExpectedErrorFlags::Contains, 2, false);
		Test.AddExpectedError(TEXT("ServerStartRaid: 방장이 아님"), EAutomationExpectedErrorFlags::Contains, 1, false);
		Test.AddExpectedError(TEXT("ServerStartRaid: 전원 준비 아님"), EAutomationExpectedErrorFlags::Contains, 1, false);
		Test.AddExpectedError(TEXT("ServerReturnToHub: 방장이 아님"), EAutomationExpectedErrorFlags::Contains, 1, false);

		StartPie(Ctx);
		RecordAndCheckInitialLeader(Ctx);

		// 거부 3종: 비방장의 선택 · 비방장의 시작 · 방장의 허용 밖 맵(임의 맵 + 옵션 주입)
		Do(Ctx, [Ctx]()
		{
			AAstralPlayerController* NonLeaderPC = FindSeatPC(FirstNonLeaderId(*Ctx));
			AAstralPlayerController* LeaderPC = FindSeatPC(Ctx->LeaderId);
			if (!Ctx->Test->TestNotNull(TEXT("non-leader seat"), NonLeaderPC) || !Ctx->Test->TestNotNull(TEXT("leader seat"), LeaderPC))
			{
				Ctx->bAborted = true;
				return;
			}
			NonLeaderPC->ServerSelectRaid(RaidMap);
			NonLeaderPC->ServerStartRaid();
			LeaderPC->ServerSelectRaid(TEXT("CombatTestMap"));
			LeaderPC->ServerSelectRaid(TEXT("RaidMap?game=/Script/Engine.GameModeBase"));
		});
		Hold(Ctx, 1.5);
		Do(Ctx, [Ctx]()
		{
			const UWorld* ServerWorld = FindServerWorld();
			Ctx->Test->TestTrue(TEXT("rejected requests left SelectedRaid empty"), SelectedRaidIn(ServerWorld).IsEmpty());
			Ctx->Test->TestEqual(TEXT("still in HubMap after rejected requests"), MapOf(ServerWorld), FString(HubMap));
		});

		// 방장의 선택 → 서버 반영 + 모든 자리에 복제
		Do(Ctx, [Ctx]()
		{
			if (AAstralPlayerController* LeaderPC = FindSeatPC(Ctx->LeaderId))
			{
				LeaderPC->ServerSelectRaid(RaidMap);
			}
		});
		WaitUntil(Ctx, TEXT("SelectedRaid = RaidMap on the server and every seat"), 20.0, []()
		{
			if (SelectedRaidIn(FindServerWorld()) != RaidMap)
			{
				return false;
			}
			for (const FSeat& Seat : GetSeats())
			{
				if (SelectedRaidIn(Seat.World) != RaidMap)
				{
					return false;
				}
			}
			return true;
		});

		// 전원 준비 전에는 방장도 시작 못 함
		Do(Ctx, [Ctx]()
		{
			if (AAstralPlayerController* LeaderPC = FindSeatPC(Ctx->LeaderId))
			{
				LeaderPC->ServerStartRaid();
			}
		});
		Hold(Ctx, 1.5);
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestEqual(TEXT("still in HubMap before everyone is ready"), MapOf(FindServerWorld()), FString(HubMap));
			for (const FSeat& Seat : GetSeats())
			{
				if (Seat.PC)
				{
					Seat.PC->ServerSetReady(true);
				}
			}
		});
		WaitUntil(Ctx, TEXT("everyone ready"), 20.0, []()
		{
			const UWorld* ServerWorld = FindServerWorld();
			const AAstralHubGameState* HubGameState = ServerWorld ? ServerWorld->GetGameState<AAstralHubGameState>() : nullptr;
			return HubGameState && HubGameState->AreAllPlayersReady();
		});

		// 시작 → 레이드 맵
		Do(Ctx, [Ctx]()
		{
			if (AAstralPlayerController* LeaderPC = FindSeatPC(Ctx->LeaderId))
			{
				LeaderPC->ServerStartRaid();
			}
		});
		WaitUntil(Ctx, TEXT("all players in RaidMap"), 180.0, [Ctx]() { return IsSettled(RaidMap, Ctx->NumPlayers); });
		CheckIdsAndLeaderKept(Ctx, TEXT("RaidMap"));

		// 비방장의 복귀 거부 → 방장의 복귀
		Do(Ctx, [Ctx]()
		{
			if (AAstralPlayerController* NonLeaderPC = FindSeatPC(FirstNonLeaderId(*Ctx)))
			{
				NonLeaderPC->ServerReturnToHub();
			}
		});
		Hold(Ctx, 1.5);
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestEqual(TEXT("still in RaidMap after a non-leader ReturnToHub"), MapOf(FindServerWorld()), FString(RaidMap));
			if (AAstralPlayerController* LeaderPC = FindSeatPC(Ctx->LeaderId))
			{
				LeaderPC->ServerReturnToHub();
			}
		});
		WaitUntil(Ctx, TEXT("all players back in HubMap"), 180.0, [Ctx]() { return IsSettled(HubMap, Ctx->NumPlayers); });
		CheckIdsAndLeaderKept(Ctx, TEXT("HubMap (returned)"));

		EndPie(Ctx);
	}

	/** P5 — Dedicated 에서 방장이 나가면 다음으로 작은 PlayerId 가 방장 */
	void EnqueueLeaderLeaves(FAutomationTestBase& Test, int32 NumPlayers)
	{
		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;
		Ctx->bDedicated = true;
		Ctx->NumPlayers = NumPlayers;

		Test.AddExpectedError(TEXT("ServerSelectRaid: 방장이 아님"), EAutomationExpectedErrorFlags::Contains, 1, /*IsRegex=*/false);

		StartPie(Ctx);
		RecordAndCheckInitialLeader(Ctx);

		// 방장 클라이언트가 스스로 접속을 끊는다 (콘솔 disconnect 와 같은 경로)
		Do(Ctx, [Ctx]()
		{
			AAstralPlayerController* LeaderPC = FindSeatPC(Ctx->LeaderId);
			if (!Ctx->Test->TestNotNull(TEXT("leader seat"), LeaderPC) || !Ctx->Test->TestTrue(TEXT("needs at least 3 players"), Ctx->PlayerIds.Num() >= 3))
			{
				Ctx->bAborted = true;
				return;
			}
			LeaderPC->ConsoleCommand(TEXT("disconnect"));
		});
		WaitUntil(Ctx, TEXT("server and remaining seats see one player fewer"), 60.0, [Ctx]()
		{
			if (PlayerIdsIn(FindServerWorld()).Num() != Ctx->NumPlayers - 1)
			{
				return false;
			}
			const TArray<FSeat> Seats = GetSeats();
			if (Seats.Num() != Ctx->NumPlayers - 1)
			{
				return false;
			}
			for (const FSeat& Seat : Seats)
			{
				if (PlayerIdsIn(Seat.World).Num() != Ctx->NumPlayers - 1)
				{
					return false;
				}
			}
			return true;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const int32 NextId = Ctx->PlayerIds[1];
			Test.TestEqual(TEXT("next smallest PlayerId is the leader on the server"), LeaderIdIn(FindServerWorld()), NextId);
			for (const FSeat& Seat : GetSeats())
			{
				Test.TestEqual(*FString::Printf(TEXT("seat %d sees the new leader"), Seat.PlayerId), LeaderIdIn(Seat.World), NextId);
			}

			// 여전히 방장이 아닌 사람은 거부된다
			if (AAstralPlayerController* StillNonLeaderPC = FindSeatPC(Ctx->PlayerIds[2]))
			{
				StillNonLeaderPC->ServerSelectRaid(RaidMap);
			}
		});
		Hold(Ctx, 1.5);
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestTrue(TEXT("non-leader request still rejected"), SelectedRaidIn(FindServerWorld()).IsEmpty());

			// 새 방장은 받아들여진다
			AAstralPlayerController* NewLeaderPC = FindSeatPC(Ctx->PlayerIds[1]);
			if (Ctx->Test->TestNotNull(TEXT("new leader seat"), NewLeaderPC))
			{
				NewLeaderPC->ServerSelectRaid(RaidMap);
			}
		});
		WaitUntil(Ctx, TEXT("new leader's SelectRaid accepted"), 20.0, []() { return SelectedRaidIn(FindServerWorld()) == RaidMap; });

		EndPie(Ctx);
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralPartyFlowListenPieTest, "AstralBreak.Net.PartyFlow.ListenPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralPartyFlowListenPieTest::RunTest(const FString& Parameters)
{
	AstralPartyFlowPie::EnqueueFlow(*this, /*bDedicated=*/false, /*NumPlayers=*/2);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralPartyFlowDedicatedPieTest, "AstralBreak.Net.PartyFlow.DedicatedPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralPartyFlowDedicatedPieTest::RunTest(const FString& Parameters)
{
	AstralPartyFlowPie::EnqueueFlow(*this, /*bDedicated=*/true, /*NumPlayers=*/2);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralPartyFlowLeaderLeavesPieTest, "AstralBreak.Net.PartyFlow.LeaderLeavesPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralPartyFlowLeaderLeavesPieTest::RunTest(const FString& Parameters)
{
	AstralPartyFlowPie::EnqueueLeaderLeaves(*this, /*NumPlayers=*/3);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
