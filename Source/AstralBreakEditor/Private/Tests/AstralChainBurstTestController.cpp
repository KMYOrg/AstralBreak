#include "AstralChainBurstTestController.h"

#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Abilities/Hero/Combat/AstralGA_Hero_Ult.h"
#include "AbilitySystem/Attributes/AstralCombatSet.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "AbilitySystemComponent.h"
#include "Animation/AnimMontage.h"
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Character/Enemy/AstralCombatCharacter.h"
#include "Character/Enemy/AstralEnemySpawnSubsystem.h"
#include "Character/Enemy/AstralEnemySpawner.h"
#include "Components/BoxComponent.h"
#include "Components/ProgressBar.h"
#include "Components/TextBlock.h"
#include "Components/Widget.h"
#include "Engine/Engine.h"
#include "Engine/NetDriver.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameStateBase.h"
#include "GameplayTagContainer.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Net/UnrealNetwork.h"
#include "Player/AstralPlayerController.h"
#include "Player/AstralPlayerState.h"
#include "UI/HUD/AstralCombatHUDWidget.h"
#include "UI/HUD/AstralStatusHUDWidget.h"

DEFINE_LOG_CATEGORY_STATIC(LogAstralChainNetTest, Display, All);

namespace AstralChainNetTest
{
	const TCHAR* const HubMap = TEXT("HubMap");
	const TCHAR* const RaidMap = TEXT("RaidMap");
	const TCHAR* const CombatMap = TEXT("CombatTestMap");

	// 태그는 런타임 모듈이 내보내지 않는다 — 이름으로 찾는다
	const TCHAR* const UltInputTagName = TEXT("InputTag.Ult");
	const TCHAR* const UltActiveTagName = TEXT("State.Ult.Active");
	const TCHAR* const UltBlockedTagName = TEXT("State.Ult.Blocked");

	/** RaidMap 의 스포너가 내는 BP 이름의 앞부분 · 수(잠정 — raid_clear 의 상수와 같다. 맵의 스포너를 바꾸면 여기와 run_party_flow.py 도 바꾼다) */
	const TCHAR* const GuardianPrefix = TEXT("BP_Enemy_Guardian");
	const int32 GuardianCount = 3;

	/** CombatTestMap 의 적 — 체인 PIE 시험과 같은 BP · 자리 */
	const TCHAR* const MeleePrefix = TEXT("BP_Enemy_Melee");
	const TCHAR* const MeleeClassPath = TEXT("/Game/Characters/Enemy/BP_Enemy_Melee.BP_Enemy_Melee_C");
	const FVector MeleeLocation(1100.0, 250.0, 92.0);

	/** 히어로를 적 둘레에 세우는 거리 · 방향 — 체인 PIE 시험과 같다(오의 스윕 = 앞 50 ~ 450, 반경 150) */
	const float RingRadius = 250.f;
	const FVector2D RingDirections[] = { FVector2D(1.0, 0.0), FVector2D(-1.0, 0.0), FVector2D(0.0, 1.0), FVector2D(0.0, -1.0) };

	/** 구역에 들어설 때 — 상자 가운데에서 +X 로 물러선 줄(수호병은 -X 쪽에 선다) */
	const float EnterOffsetX = 350.f;
	const float EnterSpacingY = 150.f;

	/** 나머지 수호병 둘 — 히어로들의 스윕(축 방향) 밖, 버스트 반경(1000) 안 */
	const FVector2D SpareOffsets[] = { FVector2D(-450.0, 450.0), FVector2D(-450.0, -450.0) };

	const float SturdyHealth = 100000.f;

	/** 자기 화면의 남은 시간이 이 값 이하가 되면 누른다 (잠정) */
	const float TogetherRemaining = 3.0f;
	const float LastMomentRemaining = 0.05f;

	const double StepTimeout = 60.0;
	const double SettleSeconds = 1.0;

	/** 버스트를 본 뒤 HP 가 자리 잡을 때까지 */
	const double BurstSettleSeconds = 1.5;

	const float ClientMaxFPS = 60.f;

	/** 화면 값 ↔ 그 자리 속성 — 같은 순간의 값이라 반올림뿐 */
	const float HudTolerance = 0.002f;

	/** 단계 번호 — 허브 앞부분은 역할마다 길이가 달라 이동부터 같은 번호를 쓴다 */
	const int32 Stage_Travel = 10;
	const int32 Stage_Arena = 11;

	FString JoinIds(const TArray<int32>& Ids)
	{
		return Ids.IsEmpty() ? FString(TEXT("-")) : FString::JoinBy(Ids, TEXT(","), [](int32 Id) { return FString::FromInt(Id); });
	}

	const TCHAR* KindName(EAstralChainOrderKind Kind)
	{
		switch (Kind)
		{
		case EAstralChainOrderKind::Cast:       return TEXT("cast");
		case EAstralChainOrderKind::Together:   return TEXT("together");
		case EAstralChainOrderKind::LastMoment: return TEXT("last");
		case EAstralChainOrderKind::Done:       return TEXT("done");
		default:                                return TEXT("none");
		}
	}

	AAstralPlayerState* PlayerStateIn(const UWorld* World, int32 PlayerId)
	{
		if (const AGameStateBase* GameState = World ? World->GetGameState() : nullptr)
		{
			for (APlayerState* PlayerState : GameState->PlayerArray)
			{
				if (PlayerState && PlayerState->GetPlayerId() == PlayerId)
				{
					return Cast<AAstralPlayerState>(PlayerState);
				}
			}
		}
		return nullptr;
	}

	UAbilitySystemComponent* AscIn(const UWorld* World, int32 PlayerId)
	{
		const AAstralPlayerState* PlayerState = PlayerStateIn(World, PlayerId);
		return PlayerState ? PlayerState->GetAbilitySystemComponent() : nullptr;
	}

	AAstralCharacter* HeroIn(const UWorld* World, int32 PlayerId)
	{
		const AAstralPlayerState* PlayerState = PlayerStateIn(World, PlayerId);
		return PlayerState ? Cast<AAstralCharacter>(PlayerState->GetPawn()) : nullptr;
	}

	float HealthOf(const AActor* Actor)
	{
		const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(Actor);
		return HealthComponent ? HealthComponent->GetHealth() : -1.f;
	}

	float AttributeOf(const UAbilitySystemComponent* ASC, const FGameplayAttribute& Attribute, float Fallback = -1.f)
	{
		return (ASC && ASC->HasAttributeSetForAttribute(Attribute)) ? ASC->GetNumericAttribute(Attribute) : Fallback;
	}

	float RatioOf(const UAbilitySystemComponent* ASC, const FGameplayAttribute& Current, const FGameplayAttribute& Max)
	{
		const float MaxValue = AttributeOf(ASC, Max, 0.f);
		return MaxValue > 0.f ? AttributeOf(ASC, Current, 0.f) / MaxValue : -1.f;
	}

	float GaugeOf(const UAbilitySystemComponent* ASC)
	{
		return AttributeOf(ASC, UAstralHeroResourceSet::GetUltGaugeAttribute());
	}

	bool HasTag(const UAbilitySystemComponent* ASC, const TCHAR* TagName)
	{
		return ASC && ASC->HasMatchingGameplayTag(FGameplayTag::RequestGameplayTag(TagName));
	}

	/** 컴포넌트 · 어빌리티의 잠정값 — 프로퍼티가 protected 라 이름으로 읽는다 */
	float FloatProperty(const UObject* Object, const TCHAR* Name)
	{
		const FFloatProperty* Property = Object ? FindFProperty<FFloatProperty>(Object->GetClass(), Name) : nullptr;
		return Property ? Property->GetPropertyValue_InContainer(Object) : 0.f;
	}

	/** 그 사람의 오의 한 방이 적에게 넣는 피해 = 오의 기본 피해 × 자기 OutgoingDamageMultiplier × 적 IncomingDamageMultiplier */
	float UltDamageBy(const UAbilitySystemComponent* ASC, const AAstralCombatCharacter* Enemy)
	{
		if (ASC && Enemy)
		{
			for (const FGameplayAbilitySpec& Spec : ASC->GetActivatableAbilities())
			{
				if (Spec.Ability && Spec.Ability->IsA(UAstralGA_Hero_Ult::StaticClass()))
				{
					return FloatProperty(Spec.Ability, TEXT("BaseDamage"))
						* AttributeOf(ASC, UAstralCombatSet::GetOutgoingDamageMultiplierAttribute(), 1.f)
						* AttributeOf(Enemy->GetAbilitySystemComponent(), UAstralHealthSet::GetIncomingDamageMultiplierAttribute(), 1.f);
				}
			}
		}
		return 0.f;
	}

	TArray<AAstralCombatCharacter*> EnemiesIn(UWorld* World, const TCHAR* Prefix)
	{
		TArray<AAstralCombatCharacter*> Out;
		for (TActorIterator<AAstralCombatCharacter> It(World); It; ++It)
		{
			if (It->GetClass()->GetName().StartsWith(Prefix))
			{
				Out.Add(*It);
			}
		}
		return Out;
	}

	/** 적들의 HP — 큰 순서(프로세스마다 액터 이름이 달라 값으로 줄 세운다) */
	FString DescribeEnemyHealth(UWorld* World, const TCHAR* Prefix)
	{
		TArray<float> Values;
		for (const AAstralCombatCharacter* Enemy : EnemiesIn(World, Prefix))
		{
			Values.Add(HealthOf(Enemy));
		}
		Values.Sort(TGreater<float>());
		return Values.IsEmpty() ? FString(TEXT("-")) : FString::JoinBy(Values, TEXT(","), [](float Value) { return FString::Printf(TEXT("%.1f"), Value); });
	}

	double ServerNow(const UWorld* World)
	{
		const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;
		return GameState ? GameState->GetServerWorldTimeSeconds() : 0.0;
	}

	// ─── HUD 읽기 (바인딩 위젯 이름 — 생성 베이스의 BindWidget 과 같다) ───

	bool IsShown(const UWidget* Widget)
	{
		return Widget && Widget->GetVisibility() != ESlateVisibility::Collapsed && Widget->GetVisibility() != ESlateVisibility::Hidden;
	}

	UWidget* PartOf(UUserWidget* Hud, const FString& Name)
	{
		return Hud ? Hud->GetWidgetFromName(FName(*Name)) : nullptr;
	}

	float PercentOf(UUserWidget* Hud, const FString& Name)
	{
		const UProgressBar* Bar = Cast<UProgressBar>(PartOf(Hud, Name));
		return Bar ? Bar->GetPercent() : -1.f;
	}

	FString TextOf(UUserWidget* Hud, const FString& Name)
	{
		const UTextBlock* Text = Cast<UTextBlock>(PartOf(Hud, Name));
		return Text ? Text->GetText().ToString() : FString();
	}
}

// ─── 지시 액터 ───

AAstralNetTestDirector::AAstralNetTestDirector()
{
	bReplicates = true;
	bAlwaysRelevant = true;
	SetNetUpdateFrequency(60.f);
}

void AAstralNetTestDirector::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);

	DOREPLIFETIME(AAstralNetTestDirector, Order);
	DOREPLIFETIME(AAstralNetTestDirector, Target);
}

void AAstralNetTestDirector::Issue(EAstralChainOrderKind Kind, const TArray<int32>& PlayerIds)
{
	++Order.Serial;
	Order.Kind = Kind;
	Order.PlayerIds = PlayerIds;
	ForceNetUpdate();
	UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST ORDER serial=%d kind=%s ids=%s"), Order.Serial, AstralChainNetTest::KindName(Kind), *AstralChainNetTest::JoinIds(PlayerIds));
}

// ─── 공통 ───

void UAstralChainBurstTestController::OnInit()
{
	FString Scenario;
	FParse::Value(FCommandLine::Get(), TEXT("AstralPartyScenario="), Scenario);
	bDeadlineScenario = Scenario.Equals(TEXT("ChainDeadline"), ESearchCase::IgnoreCase);

	Super::OnInit();

	const int32 MaxPlayers = static_cast<int32>(UE_ARRAY_COUNT(AstralChainNetTest::RingDirections));
	if (NumPlayers > MaxPlayers || (bDeadlineScenario && NumPlayers != MaxPlayers))
	{
		Fail(TEXT("AstralPartyPlayers must be <= 4 (ChainDeadline: exactly 4)"));
	}
}

const TCHAR* UAstralChainBurstTestController::StartMap() const
{
	return bDeadlineScenario ? AstralChainNetTest::CombatMap : AstralChainNetTest::HubMap;
}

void UAstralChainBurstTestController::TickScenario(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralChainNetTest;

	// -nullrhi 는 묶지 않으면 수백 fps 로 돌아 프로세스들이 CPU 를 다툰다 — 지연 실측의 프레임 몫도 실제와 비슷해진다
	if (Snap.LocalPC && GEngine && GEngine->GetMaxFPS() != ClientMaxFPS)
	{
		GEngine->SetMaxFPS(ClientMaxFPS);
	}

	const bool bAuthority = Snap.NetMode == NM_DedicatedServer || Snap.NetMode == NM_ListenServer;

	if (bDeadlineScenario)
	{
		if (Stage < Stage_Arena)
		{
			JumpToStage(Stage_Arena); // CombatTestMap 에서 바로
			return;
		}
	}
	else if (Stage < Stage_Travel)
	{
		TickHubStart(Snap, Stage_Travel);
		return;
	}

	switch (Stage)
	{
	case Stage_Travel:
		if (IsSettled(Snap, RaidMap, NumPlayers) && CheckKept(Snap, RaidMap))
		{
			Advance();
		}
		break;

	case Stage_Arena:
		if (!BindChain(Snap))
		{
			if (StageAge() > StepTimeout)
			{
				Fail(TEXT("no chain component on the game state"));
			}
			break;
		}
		if (bAuthority)
		{
			TickAuthority(Snap);
		}
		if (!bFinished && Snap.LocalPC)
		{
			TickSeat(Snap);
		}
		if (!bFinished && (!bAuthority || bAuthorityDone) && (!Snap.LocalPC || bSeatDone))
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

bool UAstralChainBurstTestController::BindChain(const FAstralPartyFlowSnapshot& Snap)
{
	UAstralChainBurstComponent* Found = UAstralChainBurstComponent::FindChainBurstComponent(Snap.World);
	if (Found && Found != Chain.Get())
	{
		Chain = Found;
		Found->OnChainStateChanged.AddUObject(this, &ThisClass::HandleChainStateChanged);
		AuthorityStageStart = SeatStageStart = FPlatformTime::Seconds();
	}
	return Chain.IsValid();
}

void UAstralChainBurstTestController::HandleChainStateChanged(const FAstralChainState& NewState, const FAstralChainState& OldState)
{
	using namespace AstralChainNetTest;

	const UAstralChainBurstComponent* ChainComponent = Chain.Get();
	const AActor* Owner = ChainComponent ? ChainComponent->GetOwner() : nullptr;
	if (!Owner)
	{
		return;
	}

	const double Now = ServerNow(Owner->GetWorld());
	UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST CHAIN role=%s t=%.3f id=%d phase=%d ids=%s casting=%d paused=%d left=%.3f burst_id=%d burst_x=%d"),
		RoleName(Role), Now, NewState.ChainId, static_cast<int32>(NewState.Phase), *JoinIds(NewState.ParticipantIds), NewState.CastingPlayerId, NewState.bTimerPaused ? 1 : 0,
		NewState.bTimerPaused ? NewState.PausedRemainingSeconds : (NewState.Phase == EAstralChainPhase::Open ? NewState.DeadlineServerTime - Now : 0.0),
		NewState.LastBurstChainId, NewState.LastBurstCount);

	if (!Owner->HasAuthority())
	{
		return;
	}

	if (NewState.Phase == EAstralChainPhase::Open && !NewState.bTimerPaused)
	{
		LastDeadline = NewState.DeadlineServerTime;
	}
	if (OldState.CastingPlayerId == 0 && NewState.CastingPlayerId != 0)
	{
		// 시전이 서버에 닿은 그 호출 안이다 — 열린 체인이 있었으면 멈춘 채고, 남은 시간이 곧 '얼마나 일찍/늦게 왔는가' 다(유예 안이면 음수)
		LastCasterId = NewState.CastingPlayerId;
		bLastCastJoined = NewState.bTimerPaused;
		LastCastLeft = bLastCastJoined ? static_cast<double>(NewState.PausedRemainingSeconds) : LastDeadline - Now;
		CastersThisOrder.Add(LastCasterId);

		const AAstralNetTestDirector* DirectorActor = Director.Get();
		UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST CAST role=%s serial=%d kind=%s id=%d t=%.3f joined=%d left=%.3f"),
			RoleName(Role), DirectorActor ? DirectorActor->Order.Serial : 0, KindName(DirectorActor ? DirectorActor->Order.Kind : EAstralChainOrderKind::None),
			LastCasterId, Now, bLastCastJoined ? 1 : 0, LastCastLeft);
	}
	if (OldState.CastingPlayerId != 0 && NewState.CastingPlayerId == 0)
	{
		++NumCastsEnded;
		ExpectedUltDamage += UltDamageBy(AscIn(Owner->GetWorld(), OldState.CastingPlayerId), Enemies.IsEmpty() ? nullptr : Enemies[0].Get());
	}
	if (NewState.LastBurstChainId != OldState.LastBurstChainId)
	{
		// 피해는 이 통지 앞에서 이미 들어갔다. 여기서 센다 — 조금만 늦어도 나간 사람의 배수를 못 읽는다 [실측 — 처음에는 1.5초 뒤에 세어 한 사람 몫이 모자랐다]
		LogBurstReport(Owner->GetWorld());
	}
}

AAstralNetTestDirector*UAstralChainBurstTestController::FindDirector(const UWorld* World) const
{
	if (World)
	{
		for (TActorIterator<AAstralNetTestDirector> It(World); It; ++It)
		{
			return *It;
		}
	}
	return nullptr;
}

void UAstralChainBurstTestController::AdvanceAuthority()
{
	++AuthorityStage;
	AuthorityStageStart = FPlatformTime::Seconds();
}

double UAstralChainBurstTestController::AuthorityAge() const
{
	return FPlatformTime::Seconds() - AuthorityStageStart;
}

void UAstralChainBurstTestController::AdvanceSeat()
{
	++SeatStage;
	SeatStageStart = FPlatformTime::Seconds();
}

double UAstralChainBurstTestController::SeatAge() const
{
	return FPlatformTime::Seconds() - SeatStageStart;
}

// ─── 권위 ───

void UAstralChainBurstTestController::TickAuthority(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralChainNetTest;

	if (bAuthorityDone)
	{
		return;
	}
	if (AuthorityAge() > StepTimeout)
	{
		Fail(FString::Printf(TEXT("authority stuck at step %d (chain [%s])"), AuthorityStage, *Chain->GetDebugString()));
		return;
	}

	switch (AuthorityStage)
	{
	case 0: // 자리마다 '도착(동료 HUD 까지) 확인' 신호 — 준비 켬
	{
		bool bAllHavePawns = Snap.Ids.Num() == NumPlayers;
		for (const int32 PlayerId : Snap.Ids)
		{
			bAllHavePawns &= HealthOf(HeroIn(Snap.World, PlayerId)) > 0.f;
		}
		if (bAllHavePawns && Snap.bAllReady)
		{
			AdvanceAuthority();
		}
		break;
	}
	case 1:
		if (PrepareEnemies(Snap))
		{
			AdvanceAuthority();
		}
		break;
	case 2:
		if (PlaceHeroes(Snap))
		{
			AdvanceAuthority();
		}
		break;
	case 3:
		if (AuthorityAge() >= SettleSeconds && MakeSturdy(Snap))
		{
			AdvanceAuthority();
		}
		break;
	default:
		if (bDeadlineScenario)
		{
			TickDeadlineAuthority(Snap);
		}
		else
		{
			TickBurstAuthority(Snap);
		}
		break;
	}
}

bool UAstralChainBurstTestController::PrepareEnemies(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralChainNetTest;

	// ─── CombatTestMap — 시험이 한 마리를 세운다 ───
	if (bDeadlineScenario)
	{
		if (Enemies.IsEmpty())
		{
			UClass* EnemyClass = StaticLoadClass(APawn::StaticClass(), nullptr, MeleeClassPath, nullptr, LOAD_NoWarn);
			UAstralEnemySpawnSubsystem* SpawnSubsystem = Snap.World->GetSubsystem<UAstralEnemySpawnSubsystem>();
			AAstralCombatCharacter* Enemy = (EnemyClass && SpawnSubsystem)
				? Cast<AAstralCombatCharacter>(SpawnSubsystem->SpawnEnemy(EnemyClass, FTransform(FRotator::ZeroRotator, MeleeLocation))) : nullptr;
			if (!Enemy)
			{
				Fail(TEXT("could not spawn the enemy"));
				return false;
			}
			Enemies.Add(Enemy);
		}
		AAstralCombatCharacter* Enemy = Enemies[0].Get();
		if (!Enemy || HealthOf(Enemy) <= 0.f)
		{
			return false;
		}
		if (AController* Controller = Enemy->GetController())
		{
			Controller->UnPossess(); // 트리가 멈추고 제자리에 선다
		}
		return true;
	}

	// ─── RaidMap — 구역에 들어가 스포너로 수호병 셋을 부른다 ───
	if (!Spawner.IsValid())
	{
		TArray<AAstralEnemySpawner*> Spawners;
		for (TActorIterator<AAstralEnemySpawner> It(Snap.World); It; ++It)
		{
			Spawners.Add(*It);
		}
		if (Spawners.Num() != 1 || Spawners[0]->SpawnPoints.Num() != GuardianCount || Spawners[0]->HasActivated())
		{
			Fail(FString::Printf(TEXT("RaidMap: expected one unused spawner with %d points (spawners=%d)"), GuardianCount, Spawners.Num()));
			return false;
		}
		Spawner = Spawners[0];

		const FVector BoxCenter = Spawner->GetTriggerBox()->GetComponentLocation();
		for (int32 Index = 0; Index < BaseIds.Num(); ++Index)
		{
			AAstralCharacter* Hero = HeroIn(Snap.World, BaseIds[Index]);
			const FVector Destination(BoxCenter.X + EnterOffsetX, BoxCenter.Y + (Index - (BaseIds.Num() - 1) * 0.5f) * EnterSpacingY, Hero ? Hero->GetActorLocation().Z : 0.0);
			if (!Hero || !Hero->TeleportTo(Destination, FRotator(0.0, 180.0, 0.0)))
			{
				Fail(FString::Printf(TEXT("RaidMap: could not move hero %d into the zone"), BaseIds[Index]));
				return false;
			}
		}
		if (!Spawner->HasActivated())
		{
			Fail(TEXT("RaidMap: the spawner did not activate when the heroes entered its box"));
		}
		return false;
	}

	const TArray<AAstralCombatCharacter*> Guardians = EnemiesIn(Snap.World, GuardianPrefix);
	if (Guardians.Num() != GuardianCount)
	{
		return false;
	}
	for (const AAstralCombatCharacter* Guardian : Guardians)
	{
		if (HealthOf(Guardian) <= 0.f || !Guardian->GetController())
		{
			return false;
		}
	}

	const FVector BoxCenter = Spawner->GetTriggerBox()->GetComponentLocation();
	for (int32 Index = 0; Index < Guardians.Num(); ++Index)
	{
		AAstralCombatCharacter* Guardian = Guardians[Index];
		Guardian->GetController()->UnPossess();
		Guardian->GetCharacterMovement()->StopMovementImmediately();

		const FVector2D Offset = Index == 0 ? FVector2D::ZeroVector : SpareOffsets[Index - 1];
		if (!Guardian->TeleportTo(FVector(BoxCenter.X + Offset.X, BoxCenter.Y + Offset.Y, Guardian->GetActorLocation().Z), FRotator::ZeroRotator))
		{
			Fail(FString::Printf(TEXT("RaidMap: could not place guardian %d"), Index));
			return false;
		}
		Enemies.Add(Guardian);
	}
	return true;
}

bool UAstralChainBurstTestController::PlaceHeroes(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralChainNetTest;

	const AAstralCombatCharacter* Target = Enemies.IsEmpty() ? nullptr : Enemies[0].Get();
	if (!Target)
	{
		Fail(TEXT("the target enemy is gone"));
		return false;
	}

	for (int32 Index = 0; Index < BaseIds.Num(); ++Index)
	{
		AAstralCharacter* Hero = HeroIn(Snap.World, BaseIds[Index]);
		const FVector2D Direction = RingDirections[Index];
		const FVector TargetLocation = Target->GetActorLocation();
		const FRotator Facing(0.0, FMath::RadiansToDegrees(FMath::Atan2(-Direction.Y, -Direction.X)), 0.0);
		const FVector Destination(TargetLocation.X + Direction.X * RingRadius, TargetLocation.Y + Direction.Y * RingRadius, Hero ? Hero->GetActorLocation().Z : 0.0);
		if (!Hero || !Hero->TeleportTo(Destination, Facing))
		{
			Fail(FString::Printf(TEXT("could not place hero %d around the target"), BaseIds[Index]));
			return false;
		}
		Hero->SetActorRotation(Facing);
	}
	return true;
}

bool UAstralChainBurstTestController::MakeSturdy(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralChainNetTest;

	for (const TWeakObjectPtr<AAstralCombatCharacter>& EnemyPtr : Enemies)
	{
		AAstralCombatCharacter* Enemy = EnemyPtr.Get();
		UAbilitySystemComponent* EnemyASC = Enemy ? Enemy->GetAbilitySystemComponent() : nullptr;
		if (!EnemyASC)
		{
			Fail(TEXT("an enemy has no ASC"));
			return false;
		}
		EnemyASC->SetNumericAttributeBase(UAstralHealthSet::GetMaxHealthAttribute(), SturdyHealth);
		EnemyASC->SetNumericAttributeBase(UAstralHealthSet::GetHealthAttribute(), SturdyHealth);
	}

	AAstralCombatCharacter* Target = Enemies[0].Get();
	int32 NumFacing = 0;
	for (const int32 PlayerId : BaseIds)
	{
		const AAstralCharacter* Hero = HeroIn(Snap.World, PlayerId);
		const FVector ToTarget = Hero ? (Target->GetActorLocation() - Hero->GetActorLocation()).GetSafeNormal2D() : FVector::ZeroVector;
		NumFacing += (Hero && FVector::DotProduct(Hero->GetActorForwardVector(), ToTarget) > 0.9) ? 1 : 0;
	}

	AAstralNetTestDirector* NewDirector = Snap.World->SpawnActor<AAstralNetTestDirector>();
	if (!NewDirector)
	{
		Fail(TEXT("could not spawn the director"));
		return false;
	}
	NewDirector->Target = Target;
	Director = NewDirector;

	UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST SETUP role=%s map=%s enemies=%d facing=%d window=%.3f grace=%.3f team_gain=%.1f hp=%s"),
		RoleName(Role), *Snap.Map, Enemies.Num(), NumFacing, Chain->GetWindowSeconds(), FloatProperty(Chain.Get(), TEXT("GraceSeconds")), FloatProperty(Chain.Get(), TEXT("TeamUltGain")),
		*DescribeEnemyHealth(Snap.World, bDeadlineScenario ? MeleePrefix : GuardianPrefix));
	if (NumFacing != NumPlayers)
	{
		Fail(FString::Printf(TEXT("only %d of %d heroes face the target on the server"), NumFacing, NumPlayers));
		return false;
	}
	return true;
}

void UAstralChainBurstTestController::IssueCast(EAstralChainOrderKind Kind, const TArray<int32>& PlayerIds)
{
	CastersThisOrder.Reset();
	ExpectedCastsEnded = NumCastsEnded + 1;
	if (AAstralNetTestDirector* DirectorActor = Director.Get())
	{
		DirectorActor->Issue(Kind, PlayerIds);
	}
}

void UAstralChainBurstTestController::LogBurstReport(const UWorld* World) const
{
	using namespace AstralChainNetTest;

	const FAstralChainBurstReport& Report = Chain->GetLastBurstReport();
	const AAstralCombatCharacter* Target = Enemies.IsEmpty() ? nullptr : Enemies[0].Get();

	// 가운데 적이 잃었어야 할 HP = 맞힌 오의들 + 버스트(각자 몫 × ChainBurstDamageMultiplier × OutgoingDamageMultiplier × 적 IncomingDamageMultiplier).
	// 전원이 참가한 버스트에서만 뜻이 있다(ChainDeadline 의 2인 버스트는 실행 스크립트가 이 줄을 보지 않는다)
	float ExpectedBurst = 0.f;
	for (const int32 PlayerId : BaseIds)
	{
		const UAbilitySystemComponent* ASC = AscIn(World, PlayerId);
		ExpectedBurst += Report.TotalDamage / FMath::Max(Report.Count, 1)
			* AttributeOf(ASC, UAstralHeroResourceSet::GetChainBurstDamageMultiplierAttribute(), 1.f)
			* AttributeOf(ASC, UAstralCombatSet::GetOutgoingDamageMultiplierAttribute(), 1.f)
			* AttributeOf(Target ? Target->GetAbilitySystemComponent() : nullptr, UAstralHealthSet::GetIncomingDamageMultiplierAttribute(), 1.f);
	}
	UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST BURST_REPORT role=%s id=%d x=%d contributors=%d targets=%d total=%.1f target_loss=%.1f expected_loss=%.1f"),
		RoleName(Role), Report.ChainId, Report.Count, Report.NumContributors, Report.NumTargets, Report.TotalDamage, SturdyHealth - HealthOf(Target), ExpectedUltDamage + ExpectedBurst);
}

void UAstralChainBurstTestController::LogAuthorityBurst(const FAstralPartyFlowSnapshot& Snap) const
{
	using namespace AstralChainNetTest;

	// 리슨 호스트는 자리 몫(TickSeat)이 같은 줄을 낸다
	if (!Snap.LocalPC)
	{
		const FAstralChainState& State = Chain->GetChainState();
		UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST BURST role=%s id=%d x=%d hp=%s"),
			RoleName(Role), State.LastBurstChainId, State.LastBurstCount, *DescribeEnemyHealth(Snap.World, bDeadlineScenario ? MeleePrefix : GuardianPrefix));
	}
}

void UAstralChainBurstTestController::TickBurstAuthority(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralChainNetTest;

	const FAstralChainState& State = Chain->GetChainState();
	switch (AuthorityStage)
	{
	case 4:
		Pending = BaseIds;
		AdvanceAuthority();
		break;
	case 5: // 다음 사람
		if (Pending.IsEmpty())
		{
			AuthorityStage = 6;
			AdvanceAuthority();
			break;
		}
		IssueCast(EAstralChainOrderKind::Cast, { Pending[0] });
		AdvanceAuthority();
		break;
	case 6: // 그 사람의 오의가 끝날 때까지
		if (IsIssuedCastOver())
		{
			const int32 PlayerId = Pending[0];
			if (LastCasterId != PlayerId || !(State.ParticipantIds.Contains(PlayerId) || State.LastBurstChainId > 0))
			{
				Fail(FString::Printf(TEXT("player %d's ult did not enter the chain (caster %d, chain [%s])"), PlayerId, LastCasterId, *Chain->GetDebugString()));
				return;
			}
			Pending.RemoveAt(0);
			AuthorityStage = 4;
			AdvanceAuthority();
		}
		break;
	case 7:
		if (State.LastBurstChainId > 0)
		{
			AdvanceAuthority();
		}
		break;
	case 8:
		if (AuthorityAge() >= BurstSettleSeconds)
		{
			LogAuthorityBurst(Snap);
			AdvanceAuthority();
		}
		break;
	case 9: // 둘째 사람이 나갈 때까지 — 나머지 자리의 신호를 보고 스스로 나간다
		if (Snap.Ids.Num() == NumPlayers - 1 && !Snap.Ids.Contains(BaseIds[1]))
		{
			bAuthorityDone = true;
		}
		break;
	default:
		break;
	}
}

void UAstralChainBurstTestController::TickDeadlineAuthority(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralChainNetTest;

	const FAstralChainState& State = Chain->GetChainState();
	switch (AuthorityStage)
	{
	// ─── 경합 1판 ───
	case 4:
		IssueCast(EAstralChainOrderKind::Cast, { BaseIds[0] });
		AdvanceAuthority();
		break;
	case 5:
		if (IsIssuedCastOver())
		{
			if (State.Phase != EAstralChainPhase::Open || State.ParticipantIds != TArray<int32>({ BaseIds[0] }))
			{
				Fail(FString::Printf(TEXT("race: the opener did not open a chain ([%s])"), *Chain->GetDebugString()));
				return;
			}
			Pending = BaseIds;
			Pending.RemoveAt(0);
			ActiveDuringRace.Reset();
			MinGaugeDuringRace.Reset();
			IssueCast(EAstralChainOrderKind::Together, Pending);
			AdvanceAuthority();
		}
		break;
	case 6: // 셋이 함께 누른다 — 서버에서 오의가 켜진 사람과 게이지의 바닥을 본다
		for (const int32 PlayerId : Pending)
		{
			const UAbilitySystemComponent* ASC = AscIn(Snap.World, PlayerId);
			if (HasTag(ASC, UltActiveTagName))
			{
				ActiveDuringRace.Add(PlayerId);
			}
			// 채우기(FillUlt)가 닿은 뒤부터 — 가득인 것을 한 번 본 사람만 잰다
			const float Gauge = GaugeOf(ASC);
			const float MaxGauge = AttributeOf(ASC, UAstralHeroResourceSet::GetMaxUltGaugeAttribute());
			if (float* Min = MinGaugeDuringRace.Find(PlayerId))
			{
				*Min = FMath::Min(*Min, Gauge);
			}
			else if (Gauge >= MaxGauge - 0.01f)
			{
				MinGaugeDuringRace.Add(PlayerId, Gauge);
			}
		}
		if (IsIssuedCastOver())
		{
			FString Gauges;
			for (const int32 PlayerId : Pending)
			{
				Gauges += FString::Printf(TEXT("%s%d:%.1f"), Gauges.IsEmpty() ? TEXT("") : TEXT(","), PlayerId, MinGaugeDuringRace.FindRef(PlayerId));
			}
			TArray<int32> Active = ActiveDuringRace.Array();
			Active.Sort();
			UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST RACE role=%s serial=%d racers=%s casters=%s active=%s min_gauge=%s participants=%s"),
				RoleName(Role), Director->Order.Serial, *JoinIds(Pending), *JoinIds(CastersThisOrder), *JoinIds(Active), *Gauges, *JoinIds(State.ParticipantIds));
			Pending.Remove(LastCasterId);
			AdvanceAuthority();
		}
		break;
	case 7: // 진 사람들이 차례로 다시 쓴다
		if (Pending.IsEmpty())
		{
			AuthorityStage = 8;
			AdvanceAuthority();
			break;
		}
		IssueCast(EAstralChainOrderKind::Cast, { Pending[0] });
		AdvanceAuthority();
		break;
	case 8:
		if (IsIssuedCastOver())
		{
			if (LastCasterId != Pending[0])
			{
				Fail(FString::Printf(TEXT("race: expected player %d to cast again, got %d"), Pending[0], LastCasterId));
				return;
			}
			Pending.RemoveAt(0);
			AuthorityStage = 6;
			AdvanceAuthority();
		}
		break;
	case 9:
		if (State.LastBurstChainId > 0)
		{
			AdvanceAuthority();
		}
		break;
	case 10: // 자리들이 버스트를 적을 시간
		if (AuthorityAge() >= 2.0 * BurstSettleSeconds)
		{
			LogAuthorityBurst(Snap);
			Round = 0;
			AdvanceAuthority();
		}
		break;

	// ─── 마감 — 사람마다 한 판 ───
	case 11:
		if (Round >= NumPlayers)
		{
			Director->Issue(EAstralChainOrderKind::Done, BaseIds);
			bAuthorityDone = true;
			break;
		}
		if (State.Phase == EAstralChainPhase::None && State.CastingPlayerId == 0 && PlaceHeroes(Snap))
		{
			AdvanceAuthority();
		}
		break;
	case 12: // 여는 사람 = 다음 번호
		if (AuthorityAge() >= SettleSeconds)
		{
			IssueCast(EAstralChainOrderKind::Cast, { BaseIds[(Round + 1) % NumPlayers] });
			AdvanceAuthority();
		}
		break;
	case 13:
		if (IsIssuedCastOver())
		{
			if (State.Phase != EAstralChainPhase::Open || State.ParticipantIds.Num() != 1)
			{
				Fail(FString::Printf(TEXT("round %d: the opener did not open a chain ([%s])"), Round, *Chain->GetDebugString()));
				return;
			}
			RoundChainId = State.ChainId;
			IssueCast(EAstralChainOrderKind::LastMoment, { BaseIds[Round] });
			AdvanceAuthority();
		}
		break;
	case 14: // 마감에 누른 사람의 오의가 끝나고, 그 체인이 닫힐 때까지
		if (IsIssuedCastOver() && State.Phase == EAstralChainPhase::None && State.CastingPlayerId == 0)
		{
			UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST ROUND role=%s k=%d tester=%d opener=%d caster=%d chain=%d joined=%d left=%.3f burst_id=%d burst_x=%d chain_after=%d"),
				RoleName(Role), Round, BaseIds[Round], BaseIds[(Round + 1) % NumPlayers], LastCasterId, RoundChainId, bLastCastJoined ? 1 : 0, LastCastLeft,
				State.LastBurstChainId, State.LastBurstCount, State.ChainId);
			++Round;
			AuthorityStage = 10;
			AdvanceAuthority();
		}
		break;
	default:
		break;
	}
}

// ─── 자리 ───

void UAstralChainBurstTestController::TickSeat(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralChainNetTest;

	if (bSeatDone)
	{
		return;
	}

	const FAstralChainState& State = Chain->GetChainState();
	const TCHAR* const EnemyPrefix = bDeadlineScenario ? MeleePrefix : GuardianPrefix;

	switch (SeatStage)
	{
	case 0: // 도착 — 내 폰 · 동료 HUD (시임리스 이동 뒤의 HUD 는 여기서 처음 본다)
	{
		const bool bAlive = HealthOf(Snap.LocalPC->GetPawn()) > 0.f;
		FString Rows;
		const bool bRows = bDeadlineScenario || CheckAllyRows(Snap, Rows);
		if (!bAlive || !bRows)
		{
			if (SeatAge() > StepTimeout * 0.5)
			{
				Fail(FString::Printf(TEXT("arrival: alive=%d rows=%s"), bAlive ? 1 : 0, *Rows));
			}
			break;
		}
		if (!bDeadlineScenario)
		{
			UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST HUDROWS role=%s my=%d where=arrived rows=%s"), RoleName(Role), BaseMyId, *Rows);
		}
#if DO_ENABLE_NET_TEST
		if (const UNetDriver* NetDriver = Snap.World->GetNetDriver())
		{
			UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST LAG role=%s my=%d out=%d in_min=%d in_max=%d"), RoleName(Role), BaseMyId,
				NetDriver->PacketSimulationSettings.PktLag, NetDriver->PacketSimulationSettings.PktIncomingLagMin, NetDriver->PacketSimulationSettings.PktIncomingLagMax);
		}
#endif
		Snap.LocalPC->ServerSetReady(true); // 신호 A
		AdvanceSeat();
		break;
	}

	case 1: // 지시를 따르며 본다
		WatchSeat(Snap);
		TickOrders(Snap);
		TickPress(Snap);

		if (State.LastBurstChainId > 0 && BurstSeenTime == 0.0)
		{
			BurstSeenTime = FPlatformTime::Seconds();
		}
		if (BurstSeenTime > 0.0 && FPlatformTime::Seconds() - BurstSeenTime >= BurstSettleSeconds && OrderPhase == 0)
		{
			BurstSeenTime = TNumericLimits<double>::Max(); // 한 번만
			UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST BURST role=%s id=%d x=%d hp=%s"),
				RoleName(Role), State.LastBurstChainId, State.LastBurstCount, *DescribeEnemyHealth(Snap.World, EnemyPrefix));
			BlockedWhile.Sort();
			UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST SEEN role=%s my=%d blocked_while=%s blocked_by_own=%d counts=%s banner=%s"),
				RoleName(Role), BaseMyId, *JoinIds(BlockedWhile), bBlockedByOwnCast ? 1 : 0,
				ChainCounts.IsEmpty() ? TEXT("-") : *FString::Join(ChainCounts, TEXT(",")), BannerCount.IsEmpty() ? TEXT("-") : *BannerCount);
			if (!bDeadlineScenario)
			{
				Snap.LocalPC->ServerSetReady(false); // 신호 B
				AdvanceSeat();
				break;
			}
		}
		if (bDeadlineScenario)
		{
			const AAstralNetTestDirector* DirectorActor = FindDirector(Snap.World);
			if (DirectorActor && DirectorActor->Order.Kind == EAstralChainOrderKind::Done && OrderPhase == 0)
			{
				bSeatDone = true;
			}
		}
		break;

	default: // ChainBurst — 둘째 사람이 나가고, 남은 자리의 동료 줄이 당겨진다
		if (BaseMyId == BaseIds[1])
		{
			// 나머지 자리가 전부 버스트를 적었다는 신호(준비 끔) 뒤에 나간다
			if (Snap.NumOthers == NumPlayers - 1 && Snap.NumOthersReady == 0)
			{
				UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST LEAVING role=%s my=%d"), RoleName(Role), BaseMyId);
				Pass();
				Finish(0);
			}
			break;
		}
		if (Snap.Ids.Num() == NumPlayers - 1 && !Snap.Ids.Contains(BaseIds[1]))
		{
			FString Rows;
			if (CheckAllyRows(Snap, Rows))
			{
				UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST HUDROWS role=%s my=%d where=left rows=%s"), RoleName(Role), BaseMyId, *Rows);
				bSeatDone = true;
			}
			else if (SeatAge() > StepTimeout * 0.5)
			{
				Fail(FString::Printf(TEXT("after the leave: rows=%s"), *Rows));
			}
		}
		else if (SeatAge() > StepTimeout)
		{
			Fail(TEXT("the leaver did not leave"));
		}
		break;
	}
}

void UAstralChainBurstTestController::WatchSeat(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralChainNetTest;

	const FAstralChainState& State = Chain->GetChainState();
	const UAbilitySystemComponent* ASC = Snap.LocalPC->GetAstralAbilitySystemComponent();
	if (State.CastingPlayerId != 0 && HasTag(ASC, UltBlockedTagName))
	{
		if (State.CastingPlayerId == BaseMyId)
		{
			bBlockedByOwnCast = true;
		}
		else
		{
			BlockedWhile.AddUnique(State.CastingPlayerId);
		}
	}

	UAstralCombatHUDWidget* Hud = Snap.LocalPC->GetCombatHUDWidget();
	if (IsShown(PartOf(Hud, TEXT("ChainPanel"))))
	{
		ChainCounts.AddUnique(TextOf(Hud, TEXT("ChainCountText")));
	}
	if (BannerCount.IsEmpty() && IsShown(PartOf(Hud, TEXT("BurstBanner"))))
	{
		BannerCount = TextOf(Hud, TEXT("BurstCountText"));
	}
}

void UAstralChainBurstTestController::TickOrders(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralChainNetTest;

	const AAstralNetTestDirector* DirectorActor = FindDirector(Snap.World);
	if (!DirectorActor)
	{
		return;
	}
	if (DirectorActor->Order.Serial != SeenSerial)
	{
		SeenSerial = DirectorActor->Order.Serial;
		const bool bMine = DirectorActor->Order.Kind != EAstralChainOrderKind::Done && DirectorActor->Order.PlayerIds.Contains(BaseMyId);
		if (bMine)
		{
			if (OrderPhase != 0)
			{
				Fail(FString::Printf(TEXT("order %d arrived while order %d is still running (phase %d)"), SeenSerial, SeatOrder.Serial, OrderPhase));
				return;
			}
			SeatOrder = DirectorActor->Order;
			OrderPhase = 1;
			bFillRequested = false;
			bSawOpen = false;
		}
	}
	if (OrderPhase != 1 && OrderPhase != 2)
	{
		return;
	}

	AAstralCharacter* Hero = Cast<AAstralCharacter>(Snap.LocalPC->GetPawn());
	UAstralAbilitySystemComponent* ASC = Snap.LocalPC->GetAstralAbilitySystemComponent();
	const AAstralCombatCharacter* Target = DirectorActor->Target;
	if (!Hero || !ASC || !Target)
	{
		return;
	}

	// 누를 때까지 적을 본다 — 서 있는 폰의 방향은 서버가 따로 갖고 있어(서버는 자리를 잡을 때 돌려 뒀다) 자기 자리도 맞춰 둔다
	const FRotator Facing(0.0, (Target->GetActorLocation() - Hero->GetActorLocation()).GetSafeNormal2D().Rotation().Yaw, 0.0);
	Hero->SetActorRotation(Facing);
	Snap.LocalPC->SetControlRotation(Facing);

	if (OrderPhase == 1)
	{
		if (!bFillRequested)
		{
			bFillRequested = true;
			Hero->FillUlt();
		}
		const float MaxGauge = AttributeOf(ASC, UAstralHeroResourceSet::GetMaxUltGaugeAttribute());
		if (MaxGauge > 0.f && GaugeOf(ASC) >= MaxGauge - 0.01f)
		{
			OrderPhase = 2;
		}
		return;
	}

	// ─── 때를 기다린다 ───
	const FAstralChainState& State = Chain->GetChainState();
	const float Remaining = Chain->GetRemainingSeconds();
	bool bPress = false;
	if (SeatOrder.Kind == EAstralChainOrderKind::Cast)
	{
		bPress = State.CastingPlayerId == 0 && !HasTag(ASC, UltBlockedTagName) && !HasTag(ASC, UltActiveTagName)
			&& FVector::Dist2D(Hero->GetActorLocation(), Target->GetActorLocation()) < RingRadius + 150.f;
	}
	else
	{
		const bool bRunning = State.Phase == EAstralChainPhase::Open && !State.bTimerPaused;
		bSawOpen |= bRunning;
		bPress = bRunning && Remaining <= (SeatOrder.Kind == EAstralChainOrderKind::Together ? TogetherRemaining : LastMomentRemaining);
		if (bSawOpen && !bRunning)
		{
			// 내 때가 오기 전에 남이 쓰기 시작했거나 닫혔다
			UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST OUTCOME role=%s my=%d serial=%d kind=%s pressed=0 predicted=0 won=0"), RoleName(Role), BaseMyId, SeatOrder.Serial, KindName(SeatOrder.Kind));
			OrderPhase = 0;
			return;
		}
	}
	if (!bPress)
	{
		return;
	}

	const AAstralPlayerState* MyState = Snap.LocalPC->GetAstralPlayerState();
	UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST PRESS role=%s my=%d serial=%d kind=%s screen_left=%.3f screen_t=%.3f blocked=%d gauge=%.1f ping=%.1f"),
		RoleName(Role), BaseMyId, SeatOrder.Serial, KindName(SeatOrder.Kind), Remaining, ServerNow(Snap.World), HasTag(ASC, UltBlockedTagName) ? 1 : 0, GaugeOf(ASC),
		MyState ? MyState->GetPingInMilliseconds() : -1.f);
	ASC->AbilityInputTagPressed(FGameplayTag::RequestGameplayTag(UltInputTagName));
	PressTime = FPlatformTime::Seconds();
	bReleased = bSawActive = bSawCasting = bSawUltBlockedText = false;
	ActiveEndTime = 0.0;
	OrderPhase = 3;
}

void UAstralChainBurstTestController::TickPress(const FAstralPartyFlowSnapshot& Snap)
{
	using namespace AstralChainNetTest;

	if (OrderPhase != 3)
	{
		return;
	}
	UAstralAbilitySystemComponent* ASC = Snap.LocalPC->GetAstralAbilitySystemComponent();
	if (!ASC)
	{
		return;
	}

	const double Now = FPlatformTime::Seconds();
	if (!bReleased && Now - PressTime >= 0.1)
	{
		bReleased = true;
		ASC->AbilityInputTagReleased(FGameplayTag::RequestGameplayTag(UltInputTagName));
	}

	const bool bActive = HasTag(ASC, UltActiveTagName);
	bSawActive |= bActive;
	bSawCasting |= Chain->GetChainState().CastingPlayerId == BaseMyId;
	bSawUltBlockedText |= IsShown(PartOf(Snap.LocalPC->GetCombatHUDWidget(), TEXT("UltBlockedText")));
	if (bSawActive && !bActive && ActiveEndTime == 0.0)
	{
		ActiveEndTime = Now;
	}

	// 되돌림(또는 끝) 뒤 게이지 · 차단 · 몽타주가 자리 잡을 시간을 주고 적는다
	const bool bSettled = ActiveEndTime > 0.0 && Now - ActiveEndTime >= 0.5;
	const bool bNeverActive = !bSawActive && Now - PressTime >= 3.0;
	if (!bSettled && !bNeverActive)
	{
		return;
	}

	const AAstralCharacter* Hero = Cast<AAstralCharacter>(Snap.LocalPC->GetPawn());
	const UAnimMontage* Montage = Hero ? Hero->GetCurrentMontage() : nullptr;
	UE_LOG(LogAstralChainNetTest, Display, TEXT("ASTRAL_NETTEST OUTCOME role=%s my=%d serial=%d kind=%s pressed=1 predicted=%d won=%d active_seconds=%.3f active=%d gauge=%.1f blocked=%d montage=%s hud_blocked=%d"),
		RoleName(Role), BaseMyId, SeatOrder.Serial, KindName(SeatOrder.Kind), bSawActive ? 1 : 0, bSawCasting ? 1 : 0, ActiveEndTime > 0.0 ? ActiveEndTime - PressTime : 0.0, bActive ? 1 : 0,
		GaugeOf(ASC), HasTag(ASC, UltBlockedTagName) ? 1 : 0, Montage ? *Montage->GetName() : TEXT("-"), bSawUltBlockedText ? 1 : 0);
	OrderPhase = 0;
}

bool UAstralChainBurstTestController::CheckAllyRows(const FAstralPartyFlowSnapshot& Snap, FString& OutDescription) const
{
	using namespace AstralChainNetTest;

	UAstralStatusHUDWidget* Hud = Snap.LocalPC->GetStatusHUDWidget();
	if (!Hud || Snap.Ids.IsEmpty())
	{
		OutDescription = FString::Printf(TEXT("hud=%d,ids=%d"), Hud ? 1 : 0, Snap.Ids.Num());
		return false;
	}

	bool bOk = Hud->IsInViewport() && Hud->GetVisibility() == ESlateVisibility::SelfHitTestInvisible;

	// 나 — 칸 0
	const UAbilitySystemComponent* MyASC = AscIn(Snap.World, Snap.MyId);
	const float MyHp = RatioOf(MyASC, UAstralHealthSet::GetHealthAttribute(), UAstralHealthSet::GetMaxHealthAttribute());
	bOk &= Hud->GetSlotPlayerState(0) == PlayerStateIn(Snap.World, Snap.MyId) && FMath::IsNearlyEqual(PercentOf(Hud, TEXT("SelfHpBar")), MyHp, HudTolerance);
	OutDescription = FString::Printf(TEXT("vis%d|self:%.3f"), Hud->GetVisibility() == ESlateVisibility::SelfHitTestInvisible ? 1 : 0, PercentOf(Hud, TEXT("SelfHpBar")));

	// 동료 — 나를 뺀 PlayerId 순
	TArray<int32> Expected = Snap.Ids;
	Expected.Remove(Snap.MyId);
	for (int32 Row = 0; Row < UAstralStatusHUDWidget::MaxAllies; ++Row)
	{
		const FString Prefix = FString::Printf(TEXT("Ally%d"), Row + 1);
		const bool bRowShown = IsShown(PartOf(Hud, Prefix + TEXT("Panel")));
		const AAstralPlayerState* RowState = Hud->GetSlotPlayerState(Row + 1);
		if (!Expected.IsValidIndex(Row))
		{
			bOk &= !bRowShown && !RowState;
			OutDescription += FString::Printf(TEXT("|%s"), bRowShown ? TEXT("extra") : TEXT("-"));
			continue;
		}

		const AAstralPlayerState* Ally = PlayerStateIn(Snap.World, Expected[Row]);
		const UAbilitySystemComponent* ASC = AscIn(Snap.World, Expected[Row]);
		const float Hp = RatioOf(ASC, UAstralHealthSet::GetHealthAttribute(), UAstralHealthSet::GetMaxHealthAttribute());
		const float Ult = RatioOf(ASC, UAstralHeroResourceSet::GetUltGaugeAttribute(), UAstralHeroResourceSet::GetMaxUltGaugeAttribute());
		const FString Name = TextOf(Hud, Prefix + TEXT("NameText"));
		const float ShownHp = PercentOf(Hud, Prefix + TEXT("HpBar"));
		const float ShownUlt = PercentOf(Hud, Prefix + TEXT("UltBar"));
		const bool bName = Ally && !Name.IsEmpty() && Name == Ally->GetPlayerName();
		bOk &= bRowShown && Ally && RowState == Ally && bName && Hp > 0.f
			&& FMath::IsNearlyEqual(ShownHp, Hp, HudTolerance) && Ult >= 0.f && FMath::IsNearlyEqual(ShownUlt, Ult, HudTolerance);
		OutDescription += FString::Printf(TEXT("|%d:shown%d:name%d:hp%.3f:ult%.3f"), RowState ? RowState->GetPlayerId() : 0, bRowShown ? 1 : 0, bName ? 1 : 0, ShownHp, ShownUlt);
	}
	return bOk;
}
