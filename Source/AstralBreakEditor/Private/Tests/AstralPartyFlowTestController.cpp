#include "AstralPartyFlowTestController.h"

#include "AstralEnemySpawnerTestListener.h"
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Character/Enemy/AstralCombatCharacter.h"
#include "Character/Enemy/AstralEnemyController.h"
#include "Character/Enemy/AstralEnemySpawner.h"
#include "Components/BoxComponent.h"
#include "Components/StateTreeAIComponent.h"
#include "Engine/Engine.h"
#include "EngineUtils.h"
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
	const TCHAR* const CombatMap = TEXT("CombatTestMap");

	/** 적 전투 — SpawnEnemy 가 부르는 BP 이름의 앞부분, 부르는 거리 */
	const TCHAR* const EnemyClassPrefix = TEXT("BP_Enemy_Melee");
	const float EnemySpawnDistance = 600.f;

	/** 거부 확인 — RPC 가 서버에 닿아 처리될 시간. 이 뒤에 '안 바뀜' 을 본다 */
	const double RejectHoldSeconds = 3.0;

	/** 끝난 뒤 남의 확인을 기다려 주는 시간 — 먼저 나가면 남은 프로세스가 인원 변화를 먼저 본다 */
	const double ExitGraceSeconds = 3.0;

	const double LingerSeconds = 30.0;

	FString JoinIds(const TArray<int32>& Ids)
	{
		return FString::JoinBy(Ids, TEXT(","), [](int32 Id) { return FString::FromInt(Id); });
	}

	// ─── 레이드 전멸 (설계 §12 E2) ───

	/** RaidMap 의 스포너가 내는 BP 이름의 앞부분 · 수(잠정 — 맵의 스포너 인스턴스를 바꾸면 여기와 run_party_flow.py 도 바꾼다) */
	const TCHAR* const RaidGuardianPrefix = TEXT("BP_Enemy_Guardian");
	const int32 RaidGuardianCount = 3;

	/** 구역 안에 히어로를 세우는 간격 — 상자 가운데에서 Y 로 벌린다(상자 반크기 Y 700) */
	const float RaidHeroSpacing = 150.f;
	const float RaidKillDamage = 1000000.f;

	/** 단계 번호 — 허브 앞부분은 역할마다 길이가 달라(방장 3, 나머지 1) 이동부터 같은 번호를 쓴다 */
	const int32 RaidClearStage_Travel = 10;
	const int32 RaidClearStage_Arrive = 11;
	const int32 RaidClearStage_Guardians = 12;
	const int32 RaidClearStage_Combat = 13;
	const int32 RaidClearStage_Gone = 14;
	const int32 RaidClearStage_Return = 15;
	const int32 RaidClearStage_Hub = 16;
	const int32 RaidClearStage_Result = 17;

	TArray<APlayerState*> RaidPlayersById(const UWorld* World)
	{
		TArray<APlayerState*> Out;
		if (const AGameStateBase* GameState = World ? World->GetGameState() : nullptr)
		{
			for (APlayerState* PlayerState : GameState->PlayerArray)
			{
				if (PlayerState)
				{
					Out.Add(PlayerState);
				}
			}
		}
		Out.Sort([](const APlayerState& A, const APlayerState& B) { return A.GetPlayerId() < B.GetPlayerId(); });
		return Out;
	}

	/** 히어로들의 HP 를 번호 순으로 "번호:HP" 로 잇는다. 폰 · 값을 못 본 자리는 -1 */
	FString DescribeRaidHeroHealth(const UWorld* World)
	{
		FString Out;
		for (const APlayerState* PlayerState : RaidPlayersById(World))
		{
			const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(PlayerState->GetPawn());
			Out += FString::Printf(TEXT("%s%d:%.1f"), Out.IsEmpty() ? TEXT("") : TEXT(","), PlayerState->GetPlayerId(), HealthComponent ? HealthComponent->GetHealth() : -1.f);
		}
		return Out;
	}

	/** 맞은 히어로 — HP 가 최대보다 낮은 사람 중 가장 낮은 쪽. 죽은 사람(0)도 센다 — 최대값이 아직 안 온 자리만 뺀다 */
	bool FindHurtRaidHero(const UWorld* World, int32& OutPlayerId, float& OutHealth)
	{
		bool bFound = false;
		for (const APlayerState* PlayerState : RaidPlayersById(World))
		{
			const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(PlayerState->GetPawn());
			if (!HealthComponent || HealthComponent->GetMaxHealth() <= 0.f)
			{
				continue;
			}
			const float Health = HealthComponent->GetHealth();
			if (Health < HealthComponent->GetMaxHealth() && (!bFound || Health < OutHealth))
			{
				bFound = true;
				OutPlayerId = PlayerState->GetPlayerId();
				OutHealth = Health;
			}
		}
		return bFound;
	}

	TArray<AAstralCombatCharacter*> RaidGuardiansIn(UWorld* World)
	{
		TArray<AAstralCombatCharacter*> Out;
		for (TActorIterator<AAstralCombatCharacter> It(World); It; ++It)
		{
			if (It->GetClass()->GetName().StartsWith(RaidGuardianPrefix))
			{
				Out.Add(*It);
			}
		}
		return Out;
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
	bEnemyCombatScenario = Scenario.Equals(TEXT("EnemyCombat"), ESearchCase::IgnoreCase);
	bRaidClearScenario = Scenario.Equals(TEXT("RaidClear"), ESearchCase::IgnoreCase);
	bEnemySpawner = FParse::Param(FCommandLine::Get(), TEXT("AstralEnemySpawner"));
	FParse::Value(FCommandLine::Get(), TEXT("AstralPartyPlayers="), NumPlayers);
	FParse::Value(FCommandLine::Get(), TEXT("AstralPartyTimeout="), TimeoutSeconds);

	StartTime = StageStartTime = FPlatformTime::Seconds();

	const TCHAR* ScenarioName = bRaidClearScenario ? TEXT("RaidClear")
		: (bEnemyCombatScenario ? TEXT("EnemyCombat") : (bLeaderLeavesScenario ? TEXT("LeaderLeaves") : TEXT("Flow")));
	UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST INIT scenario=%s players=%d timeout=%.0f"), ScenarioName, NumPlayers, TimeoutSeconds);

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
	if (!bReadyLogged && (Snap.NetMode == NM_DedicatedServer || Snap.NetMode == NM_ListenServer) && Snap.Map == StartMap())
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
		// 첫 맵에 전원이 모일 때까지
		if (IsSettled(Snap, StartMap(), NumPlayers) && RecordBase(Snap))
		{
			Advance();
		}
		return;
	}

	if (Role != ERole::Server && !Snap.LocalPC)
	{
		return; // 이동 직후 — 내 컨트롤러를 아직 못 받았다
	}

	if (bEnemyCombatScenario)
	{
		TickEnemyCombat(Snap);
	}
	else if (bRaidClearScenario)
	{
		TickRaidClear(Snap);
	}
	else if (bLeaderLeavesScenario)
	{
		TickLeaderLeaves(Snap);
	}
	else
	{
		TickFlow(Snap);
	}
}

const TCHAR* UAstralPartyFlowTestController::StartMap() const
{
	return bEnemyCombatScenario ? AstralPartyFlowController::CombatMap : AstralPartyFlowController::HubMap;
}

void UAstralPartyFlowTestController::TickEnemyCombat(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralPartyFlowController;

	// ─── 이 프로세스가 지금 보는 것 ───

	AAstralCombatCharacter* Enemy = nullptr;
	int32 NumEnemies = 0;
	for (TActorIterator<AAstralCombatCharacter> It(Snap.World); It; ++It)
	{
		if (It->GetClass()->GetName().StartsWith(EnemyClassPrefix))
		{
			Enemy = *It;
			++NumEnemies;
		}
	}

	// 맞은 히어로 — HP 가 최대보다 낮은 사람 중 가장 낮은 쪽. 값이 아직 안 온 사람(0)은 뺀다
	const AGameStateBase* GameState = Snap.World->GetGameState();
	int32 VictimId = 0;
	float VictimHealth = 0.f;
	APawn* VictimPawn = nullptr;
	APawn* MyPawn = Snap.LocalPC ? Snap.LocalPC->GetPawn() : nullptr;
	float MyHealth = 0.f;
	for (const APlayerState* PlayerState : GameState->PlayerArray)
	{
		APawn* Pawn = PlayerState ? PlayerState->GetPawn() : nullptr;
		const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(Pawn);
		if (!HealthComponent)
		{
			continue;
		}
		const float Health = HealthComponent->GetHealth();
		if (Pawn == MyPawn)
		{
			MyHealth = Health;
		}
		if (Health > 0.f && Health < HealthComponent->GetMaxHealth() && (VictimId == 0 || Health < VictimHealth))
		{
			VictimId = PlayerState->GetPlayerId();
			VictimHealth = Health;
			VictimPawn = Pawn;
		}
	}

	const bool bAuthority = Snap.NetMode == NM_DedicatedServer || Snap.NetMode == NM_ListenServer;
	const bool bOthersReady = Snap.NumOthers == NumPlayers - (Snap.NetMode == NM_DedicatedServer ? 0 : 1) && Snap.NumOthersReady == Snap.NumOthers;

	// ─── 권위 프로세스 (Dedicated 서버 · 리슨 호스트) ───
	if (bAuthority)
	{
		switch (Stage)
		{
		case 1: // 클라이언트의 SpawnEnemy 가 닿아 적이 생기고 트리가 돈다
			if (NumEnemies == 1)
			{
				const AAstralEnemyController* Controller = Cast<AAstralEnemyController>(Enemy->GetController());
				if (Controller && Controller->GetStateTreeComponent()->IsRunning())
				{
					UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST ENEMY role=%s seen=1 controller=1"), RoleName(Role));
					Advance();
				}
			}
			break;
		case 2: // 적이 누군가를 때렸다
			if (VictimId != 0 && Enemy)
			{
				const AAstralEnemyController* Controller = Cast<AAstralEnemyController>(Enemy->GetController());
				const float Distance = static_cast<float>(FVector::Dist2D(Enemy->GetActorLocation(), VictimPawn->GetActorLocation()));
				UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST HIT role=%s victim=%d hp=%.1f target_is_victim=%d distance=%.0f"),
					RoleName(Role), VictimId, VictimHealth, (Controller && Controller->GetCurrentTarget() == VictimPawn) ? 1 : 0, Distance);
				Advance();
			}
			break;
		case 3: // 클라이언트들이 같은 것을 본 뒤 적을 죽인다
			if (bOthersReady && Enemy)
			{
				UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST KILL role=%s"), RoleName(Role));
				Enemy->DamageSelf(100000.f);
				Advance();
			}
			break;
		case 4:
			if (NumEnemies == 0)
			{
				UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST GONE role=%s"), RoleName(Role));
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

	// ─── 클라이언트 ───
	switch (Stage)
	{
	case 1: // 한 클라이언트만 적을 부른다 — Exec → 서버 RPC
		if (!bEnemySpawner)
		{
			Advance();
		}
		else if (AAstralCharacter* MyCharacter = Cast<AAstralCharacter>(MyPawn); MyCharacter && MyHealth > 0.f)
		{
			UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST SPAWN_REQUEST role=%s my=%d"), RoleName(Role), BaseMyId);
			MyCharacter->SpawnEnemy(FString(), EnemySpawnDistance);
			Advance();
		}
		break;
	case 2: // 적 폰이 복제돼 온다
		if (NumEnemies == 1)
		{
			UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST ENEMY role=%s seen=1 controller=%d"), RoleName(Role), Enemy->GetController() ? 1 : 0);
			Advance();
		}
		break;
	case 3: // 맞은 히어로의 HP 가 복제돼 온다 — 본 것을 준비 신호로 알린다
		if (VictimId != 0)
		{
			UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST HIT role=%s victim=%d hp=%.1f"), RoleName(Role), VictimId, VictimHealth);
			Snap.LocalPC->ServerSetReady(true);
			Advance();
		}
		break;
	case 4:
		if (NumEnemies == 0)
		{
			UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST GONE role=%s"), RoleName(Role));
			Pass();
			Advance();
		}
		break;
	default:
		TickLinger(Snap, /*bWaitForOthersToLeave=*/false);
		break;
	}
}

void UAstralPartyFlowTestController::TickRaidClear(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralPartyFlowController;

	const bool bAuthority = Snap.NetMode == NM_DedicatedServer || Snap.NetMode == NM_ListenServer;
	const bool bOthersCounted = Snap.NumOthers == NumPlayers - (Snap.NetMode == NM_DedicatedServer ? 0 : 1);
	const bool bOthersReady = bOthersCounted && Snap.NumOthersReady == Snap.NumOthers;
	const bool bOthersNotReady = bOthersCounted && Snap.NumOthersReady == 0;

	// ─── 허브: 선택 · 준비 · 시작 (거부 확인은 Flow 시나리오가 한다) ───
	if (Stage < RaidClearStage_Travel)
	{
		if (Role != ERole::Leader)
		{
			if (Role == ERole::NonLeader)
			{
				Snap.LocalPC->ServerSetReady(true);
			}
			JumpToStage(RaidClearStage_Travel);
			return;
		}
		switch (Stage)
		{
		case 1:
			Snap.LocalPC->ServerSelectRaid(RaidMap);
			Advance();
			break;
		case 2: // 선택이 복제돼 돌아오면
			if (Snap.SelectedRaid == RaidMap)
			{
				Snap.LocalPC->ServerSetReady(true);
				Advance();
			}
			break;
		default:
			if (Snap.bAllReady && Snap.Map == HubMap)
			{
				Snap.LocalPC->ServerStartRaid();
				JumpToStage(RaidClearStage_Travel);
			}
			break;
		}
		return;
	}

	// ─── 이 프로세스가 지금 보는 것 ───

	const TArray<AAstralCombatCharacter*> Guardians = RaidGuardiansIn(Snap.World);
	const APawn* MyPawn = Snap.LocalPC ? Snap.LocalPC->GetPawn() : nullptr;

	switch (Stage)
	{
	case RaidClearStage_Travel:
		if (IsSettled(Snap, RaidMap, NumPlayers) && CheckKept(Snap, RaidMap))
		{
			Advance();
		}
		break;

	case RaidClearStage_Arrive: // 모든 프로세스가 적 0 을 본 뒤 권위 프로세스가 히어로들을 구역으로 옮긴다
		if (bAuthority)
		{
			const TArray<APlayerState*> Players = RaidPlayersById(Snap.World);
			bool bAllHavePawns = Players.Num() == NumPlayers;
			for (const APlayerState* PlayerState : Players)
			{
				bAllHavePawns &= UAstralHealthComponent::FindHealthComponent(PlayerState->GetPawn()) != nullptr;
			}
			if (!bAllHavePawns || !bOthersReady)
			{
				break; // 클라이언트 전원의 '도착 · 적 0' 신호(A)를 기다린다
			}

			TArray<AAstralEnemySpawner*> Spawners;
			for (TActorIterator<AAstralEnemySpawner> It(Snap.World); It; ++It)
			{
				Spawners.Add(*It);
			}
			if (Spawners.Num() != 1 || Spawners[0]->SpawnPoints.Num() != RaidGuardianCount)
			{
				Fail(FString::Printf(TEXT("RaidMap: expected one spawner with %d spawn points (spawners=%d points=%d)"),
					RaidGuardianCount, Spawners.Num(), Spawners.Num() > 0 ? Spawners[0]->SpawnPoints.Num() : -1));
				return;
			}
			AAstralEnemySpawner* Spawner = Spawners[0];
			if (Spawner->HasActivated() || Guardians.Num() != 0)
			{
				Fail(FString::Printf(TEXT("RaidMap: enemies before any hero entered the zone (activated=%d enemies=%d)"), Spawner->HasActivated() ? 1 : 0, Guardians.Num()));
				return;
			}
			UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST ARRIVED role=%s enemies=0 spawner=%s activated=0 points=%d"),
				RoleName(Role), *Spawner->GetName(), Spawner->SpawnPoints.Num());

			RaidSpawner = Spawner;
			RaidClearedListener = NewObject<UAstralEnemySpawnerTestListener>(this);
			Spawner->OnCleared.AddDynamic(RaidClearedListener.Get(), &UAstralEnemySpawnerTestListener::HandleCleared);

			// 상자 가운데에 Y 로 벌려 세운다. 높이는 지금 서 있는 높이 그대로 — 바닥이 평평해 걷는 상태가 유지된다(낙하로 바뀌지 않는다)
			const FVector BoxCenter = Spawner->GetTriggerBox()->GetComponentLocation();
			for (int32 Index = 0; Index < Players.Num(); ++Index)
			{
				APawn* Pawn = Players[Index]->GetPawn();
				const FVector Destination(BoxCenter.X, BoxCenter.Y + (Index - (Players.Num() - 1) * 0.5f) * RaidHeroSpacing, Pawn->GetActorLocation().Z);
				if (!Pawn->TeleportTo(Destination, Pawn->GetActorRotation()))
				{
					Fail(FString::Printf(TEXT("RaidMap: could not move hero %d into the zone at %s"), Players[Index]->GetPlayerId(), *Destination.ToCompactString()));
					return;
				}
			}
			if (!Spawner->HasActivated())
			{
				Fail(TEXT("RaidMap: the spawner did not activate when the heroes entered its box"));
				return;
			}
			UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST ENTER role=%s heroes=%d activated=1"), RoleName(Role), Players.Num());
			Advance();
		}
		else if (const UAstralHealthComponent* MyHealthComponent = UAstralHealthComponent::FindHealthComponent(MyPawn); MyHealthComponent && MyHealthComponent->GetHealth() > 0.f)
		{
			if (Guardians.Num() != 0)
			{
				Fail(FString::Printf(TEXT("RaidMap: %d enemies on arrival (expected 0)"), Guardians.Num()));
				return;
			}
			UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST ARRIVED role=%s enemies=0"), RoleName(Role));
			Snap.LocalPC->ServerSetReady(true); // 신호 A
			Advance();
		}
		break;

	case RaidClearStage_Guardians: // 수호병 3 — 서버는 폰 · 컨트롤러 · 도는 트리, 클라이언트는 폰만
		if (bAuthority)
		{
			int32 NumControllers = 0;
			int32 NumTrees = 0;
			for (const AAstralCombatCharacter* Guardian : Guardians)
			{
				if (const AAstralEnemyController* Controller = Cast<AAstralEnemyController>(Guardian->GetController()))
				{
					++NumControllers;
					NumTrees += Controller->GetStateTreeComponent()->IsRunning() ? 1 : 0;
				}
			}
			if (Guardians.Num() == RaidGuardianCount && NumTrees == RaidGuardianCount && RaidSpawner.IsValid() && RaidSpawner->GetNumAliveEnemies() == RaidGuardianCount)
			{
				for (AAstralCombatCharacter* Guardian : Guardians)
				{
					RaidGuardians.Add(Guardian);
					Guardian->OnDestroyed.AddDynamic(this, &UAstralPartyFlowTestController::HandleRaidGuardianDestroyed);
				}
				UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST GUARDIANS role=%s pawns=%d controllers=%d trees=%d alive=%d"),
					RoleName(Role), Guardians.Num(), NumControllers, NumTrees, RaidSpawner->GetNumAliveEnemies());
				Advance();
			}
		}
		else if (Guardians.Num() == RaidGuardianCount)
		{
			int32 NumControllers = 0;
			for (const AAstralCombatCharacter* Guardian : Guardians)
			{
				NumControllers += Guardian->GetController() ? 1 : 0;
			}
			UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST GUARDIANS role=%s pawns=%d controllers=%d"), RoleName(Role), Guardians.Num(), NumControllers);
			Snap.LocalPC->ServerSetReady(false); // 신호 B
			Advance();
		}
		break;

	case RaidClearStage_Combat: // 수호병이 누군가를 때렸다 — 권위 프로세스는 본 틱에 곧바로 셋을 죽인다(히어로 HP 가 여기서 멈춘다)
	{
		int32 VictimId = 0;
		float VictimHealth = 0.f;
		const bool bHurt = FindHurtRaidHero(Snap.World, VictimId, VictimHealth);
		if (!bAuthority)
		{
			if (bHurt)
			{
				UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST HIT role=%s victim=%d hp=%.1f"), RoleName(Role), VictimId, VictimHealth);
				Advance();
			}
			break;
		}
		if (!bHurt || !bOthersNotReady)
		{
			break; // 클라이언트 전원의 '수호병 3' 신호(B)와 첫 피해를 기다린다
		}
		if (!RaidSpawner.IsValid() || Guardians.Num() != RaidGuardianCount)
		{
			Fail(FString::Printf(TEXT("RaidMap: guardians changed before the kill (spawner=%d guardians=%d)"), RaidSpawner.IsValid() ? 1 : 0, Guardians.Num()));
			return;
		}
		UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST HIT role=%s victim=%d hp=%.1f heroes=%s"), RoleName(Role), VictimId, VictimHealth, *DescribeRaidHeroHealth(Snap.World));

		for (const TWeakObjectPtr<AAstralCombatCharacter>& Guardian : RaidGuardians)
		{
			if (Guardian.IsValid())
			{
				Guardian->DamageSelf(RaidKillDamage);
			}
		}
		RaidKillTime = FPlatformTime::Seconds();

		// 죽기 시작하는 것은 피해와 같은 호출 안이다 — 스포너는 곧바로 '끝났다' 고 한다
		const int32 NumCleared = RaidClearedListener ? RaidClearedListener->NumCleared : -1;
		UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST CLEARED role=%s activated=%d alive=%d cleared=%d"),
			RoleName(Role), RaidSpawner->HasActivated() ? 1 : 0, RaidSpawner->GetNumAliveEnemies(), NumCleared);
		if (!RaidSpawner->HasActivated() || RaidSpawner->GetNumAliveEnemies() != 0 || NumCleared != 1)
		{
			Fail(FString::Printf(TEXT("RaidMap: the spawner is not cleared after the kills (alive=%d cleared=%d)"), RaidSpawner->GetNumAliveEnemies(), NumCleared));
			return;
		}
		Advance();
		break;
	}

	case RaidClearStage_Gone: // 죽은 수호병이 사라진다
		if (bAuthority)
		{
			if (NumRaidGuardiansDestroyed == RaidGuardianCount)
			{
				UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST HEROES role=%s hp=%s"), RoleName(Role), *RaidHeroesAtGone);
				UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST GONE role=%s destroyed=%d seconds=%.1f"), RoleName(Role), NumRaidGuardiansDestroyed, RaidGoneTime - RaidKillTime);
				Advance();
			}
		}
		else if (Snap.Map != RaidMap)
		{
			Fail(FString::Printf(TEXT("left RaidMap before this client saw the guardians removed (map=%s)"), *Snap.Map));
			return;
		}
		else if (Guardians.Num() == 0)
		{
			UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST HEROES role=%s hp=%s"), RoleName(Role), *DescribeRaidHeroHealth(Snap.World));
			UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST GONE role=%s"), RoleName(Role));
			Snap.LocalPC->ServerSetReady(true); // 신호 C
			Advance();
		}
		break;

	case RaidClearStage_Return: // 방장은 나머지 전원이 '수호병 0' 을 알린 뒤(C) 돌아간다
		if (Role != ERole::Leader)
		{
			Advance();
		}
		else if (bOthersReady && Snap.Map == RaidMap)
		{
			UE_LOG(LogAstralNetTest, Display, TEXT("ASTRAL_NETTEST RETURN role=%s"), RoleName(Role));
			Snap.LocalPC->ServerReturnToHub();
			Advance();
		}
		break;

	case RaidClearStage_Hub:
		if (IsSettled(Snap, HubMap, NumPlayers) && CheckKept(Snap, TEXT("HubMap(returned)")))
		{
			if (Snap.LocalPC)
			{
				Snap.LocalPC->ServerSetReady(true);
			}
			Advance();
		}
		break;

	case RaidClearStage_Result:
		if (Snap.bAllReady)
		{
			Pass();
			Advance();
		}
		break;

	default:
		TickLinger(Snap, /*bWaitForOthersToLeave=*/bAuthority);
		break;
	}
}

void UAstralPartyFlowTestController::HandleRaidGuardianDestroyed(AActor* DestroyedActor)
{
	++NumRaidGuardiansDestroyed;
	if (NumRaidGuardiansDestroyed == AstralPartyFlowController::RaidGuardianCount)
	{
		RaidGoneTime = FPlatformTime::Seconds();
		RaidHeroesAtGone = AstralPartyFlowController::DescribeRaidHeroHealth(DestroyedActor ? DestroyedActor->GetWorld() : nullptr);
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

void UAstralPartyFlowTestController::JumpToStage(int32 NewStage)
{
	Stage = NewStage - 1;
	Advance();
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
