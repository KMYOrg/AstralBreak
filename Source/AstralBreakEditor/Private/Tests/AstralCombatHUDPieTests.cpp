// M4 단위 C 전투 HUD 시험 — 한 프로세스 멀티 PIE 2인 (설계 Docs/Design/m4-ult-chain.md §5 · §6 'C 구현 결과')
//
// 리슨 서버 · Dedicated 를 PIE 로 띄워 CombatTestMap 에서 두 사람(A = 첫 클라이언트 자리, B = 다른 자리)이 차례로 오의를 쓰고,
// 자리마다 전투 HUD(승격본 WBP)의 바인딩 위젯 값 — 게이지 비율 · 글자 · Visibility — 을 직접 읽는다. 사람 몫은 화면 모양 눈 확인뿐이다.
//
//   H0  자리마다 HUD 가 있고(승격본 WBP 클래스) 원천에 붙었다(자기 자리 ASC · 체인 컴포넌트). 게이지 = 자기 자리 값, 패널 · 배너 · '오의 불가' 접힘
//   H1  게이지가 모자란 채 누름 → '오의 불가' 안 뜸 (실패 통지는 오지만 차단 태그가 없다 — 게이지 부족은 조용히)
//   H2  FillUlt → 비율 1 · 오의 가능 표시와 키 안내 글자 보임(가득이 아닐 때는 안 보임) · 글자 = 그 자리 Enhanced Input 이 오의 액션에 걸어 둔 키,
//       키 배치를 바꾸면 통지를 받아 글자가 따라 바뀐다
//   H3  A 가 쓰는 동안 B 가 누름(차단 중) → B 자리에 '오의 불가', UltBlockedSeconds 뒤 접힘. A 자리는 게이지 0 · 강조 접힘, 체인 패널은 아직 없음
//   H4  A 가 맞히고 끝남 → 두 자리에 체인 패널 · "1/최대" · 남은 시간 ≤ 윈도우이고 0.5초 뒤 더 작다. 고리 비율 = 남은 시간 / 윈도우, 같이 줄어든다
//   H5  B 가 쓰는 동안 → 두 자리의 남은 시간 글자와 고리 비율이 0.5초 동안 그대로(멈춤)
//   H6  B 가 맞히고 끝남 → 살아 있는 2명 전원이라 바로 버스트: 두 자리에 배너 · "2" · 패널 접힘, BurstBannerSeconds 뒤 배너 접힘
//
// 적은 체인 시험(AstralChainBurstPieTests)처럼 서버에서 직접 세운다 — AI 컨트롤러를 떼고 HP 를 크게 올린다. 두 히어로가 250 cm 거리에서 적을 본다.
// 값(윈도우 · 최대 인원 · 표시 시간)은 컴포넌트 · 위젯의 프로퍼티이고 전부 잠정이다 — 시험은 프로퍼티에서 읽어 규칙만 본다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AstralPieTestHelpers.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Character/Enemy/AstralCombatCharacter.h"
#include "Character/Enemy/AstralEnemySpawnSubsystem.h"
#include "Components/Image.h"
#include "Components/PanelWidget.h"
#include "Components/ProgressBar.h"
#include "Components/TextBlock.h"
#include "Components/Widget.h"
#include "Engine/GameInstance.h"
#include "Engine/LocalPlayer.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/Controller.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerState.h"
#include "GameModes/AstralChainBurstComponent.h"
#include "GameplayTagContainer.h"
#include "InputAction.h"
#include "InputCoreTypes.h"
#include "InputMappingContext.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Player/AstralPlayerController.h"
#include "UI/HUD/AstralCombatHUDWidget.h"

namespace AstralCombatHUDPie
{
	using namespace AstralPieTest;

	const TCHAR* const MapPath = TEXT("/Game/Maps/CombatTestMap");
	const TCHAR* const MapName = TEXT("CombatTestMap");
	const TCHAR* const EnemyClassPath = TEXT("/Game/Characters/Enemy/BP_Enemy_Melee.BP_Enemy_Melee_C");
	const TCHAR* const PromotedHudClassPath = TEXT("/Game/UI/HUD/CombatHUD/WBP_CombatHUD.WBP_CombatHUD_C");

	// 태그는 런타임 모듈이 내보내지 않는다 — 이름으로 찾는다
	const TCHAR* const UltInputTagName = TEXT("InputTag.Ult");
	const TCHAR* const UltActiveTagName = TEXT("State.Ult.Active");
	const TCHAR* const UltBlockedTagName = TEXT("State.Ult.Blocked");

	const TCHAR* const UltActionPath = TEXT("/Game/Input/Actions/IA_Ult.IA_Ult");
	/** 고리 비율을 재는 순간과 HUD 가 그린 순간의 차(한두 프레임) — 윈도우 6초에서 0.12초 */
	constexpr float RingTolerance = 0.02f;

	// 바인딩 위젯 이름 — 생성 베이스 UAstralCombatHUDViewBase 의 BindWidget 과 같다(계약 sha1:2ee29ce6…). 그림 UltReadyGlow 는 이제 UltReadyPanel 의 자식(선택 바인딩)
	const TCHAR* const UltGaugeName = TEXT("UltGauge");
	const TCHAR* const UltReadyPanelName = TEXT("UltReadyPanel");
	const TCHAR* const UltReadyGlowName = TEXT("UltReadyGlow");
	const TCHAR* const UltKeyName = TEXT("UltKeyText");
	const TCHAR* const UltBlockedName = TEXT("UltBlockedText");
	const TCHAR* const ChainPanelName = TEXT("ChainPanel");
	const TCHAR* const ChainRingName = TEXT("ChainRing");
	const TCHAR* const ChainTimerName = TEXT("ChainTimerText");
	const TCHAR* const ChainCountName = TEXT("ChainCountText");
	const TCHAR* const BurstBannerName = TEXT("BurstBanner");
	const TCHAR* const BurstCountName = TEXT("BurstCountText");

	// CombatTestMap 좌표 — 체인 시험과 같은 자리. 적을 가운데 두고 A 는 +X 쪽, B 는 -X 쪽에서 250 cm 거리로 적을 본다
	constexpr int32 NumPlayers = 2;
	const FVector EnemyLocation(1100.0, 250.0, 92.0);
	const FVector HeroLocations[NumPlayers] = { FVector(1350.0, 250.0, 92.0), FVector(850.0, 250.0, 92.0) };
	const float HeroFacingYaws[NumPlayers] = { 180.f, 0.f };
	constexpr float SturdyHealth = 100000.f;

	struct FContext : FContextBase
	{
		bool bDedicated = false;

		/** [0] = A(첫 클라이언트 자리 — 입력이 실제 넷 드라이버를 탄다), [1] = B */
		TArray<int32> Ids;

		TWeakObjectPtr<AAstralCombatCharacter> Enemy;
		float MaxGauge = 0.f;

		/** 잠정값 — 체인 컴포넌트 · HUD 위젯의 프로퍼티에서 읽는다 */
		float WindowSeconds = 0.f;
		int32 MaxParticipants = 0;
		float UltBlockedSeconds = 0.f;
		float BurstBannerSeconds = 0.f;

		/** 자리마다 읽어 둔 남은 시간 글자 · 고리 비율 */
		TMap<int32, FString> TimerTexts;
		TMap<int32, float> RingPercents;

		/** H2 — 시험이 잠깐 얹는 키 배치(오의 = T) */
		TStrongObjectPtr<UInputMappingContext> ExtraMapping;
		FString KeyBefore;
	};

	// ─── 조회 ───

	APlayerController* GetLocalPC(const UWorld* World)
	{
		const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
		return GameInstance ? GameInstance->GetFirstLocalPlayerController(World) : nullptr;
	}

	/** 로컬 컨트롤러가 있는 PIE 월드 — 리슨: 호스트 + 클라이언트, Dedicated: 클라이언트들 */
	TArray<UWorld*> GetSeatWorlds()
	{
		TArray<UWorld*> Out;
		for (UWorld* World : GetPieWorlds())
		{
			const ENetMode NetMode = World->GetNetMode();
			if (NetMode == NM_ListenServer || NetMode == NM_Client)
			{
				Out.Add(World);
			}
		}
		return Out;
	}

	int32 LocalPlayerIdIn(const UWorld* World)
	{
		const APlayerController* PC = GetLocalPC(World);
		return (PC && PC->PlayerState) ? PC->PlayerState->GetPlayerId() : 0;
	}

	UWorld* FindSeatWorld(int32 PlayerId)
	{
		for (UWorld* World : GetSeatWorlds())
		{
			if (LocalPlayerIdIn(World) == PlayerId)
			{
				return World;
			}
		}
		return nullptr;
	}

	AAstralCharacter* PawnIn(const UWorld* World, int32 PlayerId)
	{
		const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;
		if (!GameState)
		{
			return nullptr;
		}
		for (const APlayerState* PlayerState : GameState->PlayerArray)
		{
			if (PlayerState && PlayerState->GetPlayerId() == PlayerId)
			{
				return Cast<AAstralCharacter>(PlayerState->GetPawn());
			}
		}
		return nullptr;
	}

	float HealthOf(const AActor* Actor)
	{
		const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(Actor);
		return HealthComponent ? HealthComponent->GetHealth() : -1.f;
	}

	UAbilitySystemComponent* ServerASC(int32 PlayerId)
	{
		const AAstralCharacter* Pawn = PawnIn(FindServerWorld(), PlayerId);
		return Pawn ? Pawn->GetAbilitySystemComponent() : nullptr;
	}

	/** 그 플레이어 자기 자리의 ASC — 입력을 넣는 곳, HUD 가 붙어야 할 곳 (리슨 호스트는 서버의 것과 같다) */
	UAstralAbilitySystemComponent* SeatASC(int32 PlayerId)
	{
		const AAstralPlayerController* PC = Cast<AAstralPlayerController>(GetLocalPC(FindSeatWorld(PlayerId)));
		return PC ? PC->GetAstralAbilitySystemComponent() : nullptr;
	}

	float AttributeOf(const UAbilitySystemComponent* ASC, const FGameplayAttribute& Attribute, float Fallback = -1.f)
	{
		return (ASC && ASC->HasAttributeSetForAttribute(Attribute)) ? ASC->GetNumericAttribute(Attribute) : Fallback;
	}

	float GaugeOf(const UAbilitySystemComponent* ASC)
	{
		return AttributeOf(ASC, UAstralHeroResourceSet::GetUltGaugeAttribute());
	}

	bool HasTag(const UAbilitySystemComponent* ASC, const TCHAR* TagName)
	{
		return ASC && ASC->HasMatchingGameplayTag(FGameplayTag::RequestGameplayTag(TagName));
	}

	UAstralChainBurstComponent* ChainIn(const UWorld* World)
	{
		return World ? UAstralChainBurstComponent::FindChainBurstComponent(World) : nullptr;
	}

	FAstralChainState ServerState()
	{
		const UAstralChainBurstComponent* Chain = ChainIn(FindServerWorld());
		return Chain ? Chain->GetChainState() : FAstralChainState();
	}

	float FloatProperty(const UObject* Object, const TCHAR* Name)
	{
		const FFloatProperty* Property = Object ? FindFProperty<FFloatProperty>(Object->GetClass(), Name) : nullptr;
		return Property ? Property->GetPropertyValue_InContainer(Object) : 0.f;
	}

	// ─── HUD 읽기 ───

	UAstralCombatHUDWidget* HudOf(int32 PlayerId)
	{
		const AAstralPlayerController* PC = Cast<AAstralPlayerController>(GetLocalPC(FindSeatWorld(PlayerId)));
		return PC ? PC->GetCombatHUDWidget() : nullptr;
	}

	UWidget* PartOf(int32 PlayerId, const TCHAR* Name)
	{
		UAstralCombatHUDWidget* Hud = HudOf(PlayerId);
		return Hud ? Hud->GetWidgetFromName(FName(Name)) : nullptr;
	}

	/** 보이는가 — setter 는 보이기 = SelfHitTestInvisible, 접기 = Collapsed 로 바꾼다 */
	bool Shown(int32 PlayerId, const TCHAR* Name)
	{
		const UWidget* Widget = PartOf(PlayerId, Name);
		return Widget && Widget->GetVisibility() != ESlateVisibility::Collapsed && Widget->GetVisibility() != ESlateVisibility::Hidden;
	}

	/** 화면에 보이는가 — 조상까지 접히지 않았다(키 안내는 UltReadyPanel 과 같이 접힌다) */
	bool ShownOnScreen(int32 PlayerId, const TCHAR* Name)
	{
		const UWidget* Widget = PartOf(PlayerId, Name);
		if (!Widget)
		{
			return false;
		}
		for (const UWidget* It = Widget; It; It = It->GetParent())
		{
			if (It->GetVisibility() == ESlateVisibility::Collapsed || It->GetVisibility() == ESlateVisibility::Hidden)
			{
				return false;
			}
		}
		return true;
	}

	/** 고리에 남은 비율 — HUD 가 움직인 동적 머티리얼의 Percent. 아직 안 움직였으면 -1 */
	float RingOf(int32 PlayerId)
	{
		const UImage* Ring = Cast<UImage>(PartOf(PlayerId, ChainRingName));
		const UMaterialInstanceDynamic* Material = Ring ? Cast<UMaterialInstanceDynamic>(Ring->GetBrush().GetResourceObject()) : nullptr;
		float Percent = -1.f;
		return (Material && Material->GetScalarParameterValue(FHashedMaterialParameterInfo(TEXT("Percent")), Percent)) ? Percent : -1.f;
	}

	/** 그 자리 체인 컴포넌트의 남은 시간 / 윈도우 */
	float ExpectedRing(int32 PlayerId)
	{
		const UAstralChainBurstComponent* Chain = ChainIn(FindSeatWorld(PlayerId));
		return (Chain && Chain->GetWindowSeconds() > 0.f) ? FMath::Clamp(Chain->GetRemainingSeconds() / Chain->GetWindowSeconds(), 0.f, 1.f) : -2.f;
	}

	UEnhancedInputLocalPlayerSubsystem* InputOf(int32 PlayerId)
	{
		const APlayerController* PC = GetLocalPC(FindSeatWorld(PlayerId));
		const ULocalPlayer* LocalPlayer = PC ? PC->GetLocalPlayer() : nullptr;
		return LocalPlayer ? LocalPlayer->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>() : nullptr;
	}

	/** 그 자리에서 오의 액션에 걸린 첫 키보드 · 마우스 키의 짧은 이름(무인 실행이라 게임패드 입력이 없다) */
	FString ExpectedKey(int32 PlayerId)
	{
		const UEnhancedInputLocalPlayerSubsystem* Input = InputOf(PlayerId);
		const UInputAction* Action = LoadObject<UInputAction>(nullptr, UltActionPath);
		if (Input && Action)
		{
			for (const FKey& Key : Input->QueryKeysMappedToAction(Action))
			{
				if (!Key.IsGamepadKey())
				{
					return Key.GetDisplayName(false).ToString();
				}
			}
		}
		return FString();
	}

	float PercentOf(int32 PlayerId)
	{
		const UProgressBar* Bar = Cast<UProgressBar>(PartOf(PlayerId, UltGaugeName));
		return Bar ? Bar->GetPercent() : -1.f;
	}

	FString TextOf(int32 PlayerId, const TCHAR* Name)
	{
		const UTextBlock* Text = Cast<UTextBlock>(PartOf(PlayerId, Name));
		return Text ? Text->GetText().ToString() : FString(TEXT("<none>"));
	}

	float NumberOf(int32 PlayerId, const TCHAR* Name)
	{
		return FCString::Atof(*TextOf(PlayerId, Name));
	}

	/** 자리의 HUD 게이지 비율이 자기 자리 ASC 의 값과 같은가 */
	bool GaugeMatchesSeat(const FContext& Ctx, int32 PlayerId)
	{
		const UAbilitySystemComponent* ASC = SeatASC(PlayerId);
		const float Max = AttributeOf(ASC, UAstralHeroResourceSet::GetMaxUltGaugeAttribute(), 0.f);
		const float Expected = Max > 0.f ? FMath::Clamp(GaugeOf(ASC) / Max, 0.f, 1.f) : 0.f;
		return FMath::IsNearlyEqual(PercentOf(PlayerId), Expected, 0.001f);
	}

	FString DescribeHud(int32 PlayerId)
	{
		const UAstralCombatHUDWidget* Hud = HudOf(PlayerId);
		if (!Hud)
		{
			return FString::Printf(TEXT("%d: no HUD"), PlayerId);
		}
		return FString::Printf(TEXT("%d: gauge %.3f ready %d key %d [%s] blocked %d panel %d ring %.3f (want %.3f) [%s | %s] banner %d [%s]"), PlayerId, PercentOf(PlayerId),
			Shown(PlayerId, UltReadyPanelName) ? 1 : 0, ShownOnScreen(PlayerId, UltKeyName) ? 1 : 0, *TextOf(PlayerId, UltKeyName), Shown(PlayerId, UltBlockedName) ? 1 : 0,
			Shown(PlayerId, ChainPanelName) ? 1 : 0, RingOf(PlayerId), ExpectedRing(PlayerId), *TextOf(PlayerId, ChainCountName), *TextOf(PlayerId, ChainTimerName), Shown(PlayerId, BurstBannerName) ? 1 : 0, *TextOf(PlayerId, BurstCountName));
	}

	FString Describe(const FContext& Ctx)
	{
		const UAstralChainBurstComponent* Chain = ChainIn(FindServerWorld());
		FString Out = FString::Printf(TEXT("server map '%s', chain [%s]"), *MapOf(FindServerWorld()), Chain ? *Chain->GetDebugString() : TEXT("no component"));
		for (const int32 PlayerId : Ctx.Ids)
		{
			const UAbilitySystemComponent* ASC = SeatASC(PlayerId);
			Out += FString::Printf(TEXT(" | seat %s, seat gauge %.1f%s%s"), *DescribeHud(PlayerId), GaugeOf(ASC),
				HasTag(ServerASC(PlayerId), UltActiveTagName) ? TEXT(" *ult") : TEXT(""), HasTag(ASC, UltBlockedTagName) ? TEXT(" xblocked") : TEXT(""));
		}
		return Out;
	}

	void Wait(const TSharedRef<FContext>& Ctx, const FString& What, double TimeoutSeconds, TFunction<bool()> Condition)
	{
		WaitUntil(Ctx, *What, TimeoutSeconds, MoveTemp(Condition), [Ctx]() { return Describe(*Ctx); });
	}

	// ─── 조작 ───

	/** 몸 · 시점을 적 쪽으로 — 서버의 폰과 자기 자리의 폰 · 컨트롤 회전을 함께 (서 있는 폰의 방향은 클라이언트에서만 돌려서는 서버에 가지 않는다) */
	void Face(const TSharedRef<FContext>& Ctx, int32 Index)
	{
		Do(Ctx, [Ctx, Index]()
		{
			const FRotator Facing(0.0, HeroFacingYaws[Index], 0.0);
			if (AAstralCharacter* ServerPawn = PawnIn(FindServerWorld(), Ctx->Ids[Index]))
			{
				ServerPawn->SetActorRotation(Facing);
			}
			UWorld* SeatWorld = FindSeatWorld(Ctx->Ids[Index]);
			AAstralCharacter* SeatPawn = PawnIn(SeatWorld, Ctx->Ids[Index]);
			APlayerController* PC = GetLocalPC(SeatWorld);
			if (SeatPawn && PC)
			{
				SeatPawn->SetActorRotation(Facing);
				PC->SetControlRotation(Facing);
			}
		});
	}

	void PlaceHeroes(const TSharedRef<FContext>& Ctx)
	{
		Do(Ctx, [Ctx]()
		{
			UWorld* ServerWorld = FindServerWorld();
			for (int32 Index = 0; Index < Ctx->Ids.Num(); ++Index)
			{
				if (AAstralCharacter* ServerPawn = PawnIn(ServerWorld, Ctx->Ids[Index]))
				{
					ServerPawn->TeleportTo(HeroLocations[Index], FRotator(0.0, HeroFacingYaws[Index], 0.0));
				}
			}
		});
		for (int32 Index = 0; Index < NumPlayers; ++Index)
		{
			Face(Ctx, Index);
		}
		Hold(Ctx, 0.7);
	}

	/** 자기 자리의 디버그 명령으로 채운다 — 클라이언트는 Exec → 서버 RPC, 리슨 호스트는 바로 */
	void Fill(const TSharedRef<FContext>& Ctx, int32 Index)
	{
		Do(Ctx, [Ctx, Index]()
		{
			const int32 PlayerId = Ctx->Ids[Index];
			AAstralCharacter* SeatPawn = PawnIn(FindSeatWorld(PlayerId), PlayerId);
			if (!Ctx->Test->TestNotNull(TEXT("hero pawn on its own seat"), SeatPawn))
			{
				Ctx->bAborted = true;
				return;
			}
			SeatPawn->FillUlt();
		});
		Wait(Ctx, FString::Printf(TEXT("H2: FillUlt fills player %d's gauge on the server and on its own seat"), Index), 10.0, [Ctx, Index]()
		{
			const int32 PlayerId = Ctx->Ids[Index];
			return FMath::IsNearlyEqual(GaugeOf(ServerASC(PlayerId)), Ctx->MaxGauge, 0.01f) && FMath::IsNearlyEqual(GaugeOf(SeatASC(PlayerId)), Ctx->MaxGauge, 0.01f);
		});
	}

	/** 자기 자리에서 오의 입력을 눌렀다 뗀다 */
	void PressUlt(const TSharedRef<FContext>& Ctx, int32 Index)
	{
		Do(Ctx, [Ctx, Index]()
		{
			UAstralAbilitySystemComponent* ASC = SeatASC(Ctx->Ids[Index]);
			if (!Ctx->Test->TestNotNull(TEXT("player's ASC on its own seat"), ASC))
			{
				Ctx->bAborted = true;
				return;
			}
			ASC->AbilityInputTagPressed(FGameplayTag::RequestGameplayTag(UltInputTagName));
		});
		Hold(Ctx, 0.1);
		Do(Ctx, [Ctx, Index]()
		{
			if (UAstralAbilitySystemComponent* ASC = SeatASC(Ctx->Ids[Index]))
			{
				ASC->AbilityInputTagReleased(FGameplayTag::RequestGameplayTag(UltInputTagName));
			}
		});
	}

	/** 두 자리의 남은 시간 글자 · 고리 비율을 읽어 둔다 */
	void SnapshotTimers(FContext& Ctx)
	{
		Ctx.TimerTexts.Reset();
		Ctx.RingPercents.Reset();
		for (const int32 PlayerId : Ctx.Ids)
		{
			Ctx.TimerTexts.Add(PlayerId, TextOf(PlayerId, ChainTimerName));
			Ctx.RingPercents.Add(PlayerId, RingOf(PlayerId));
		}
	}

	// ─── 단계 ───

	void EnqueueSetup(const TSharedRef<FContext>& Ctx)
	{
		RequestPie(Ctx, MapPath, Ctx->bDedicated ? PIE_Client : PIE_ListenServer, NumPlayers);
		Wait(Ctx, TEXT("every player has a living pawn on the server and on its own seat"), 240.0, []()
		{
			const UWorld* ServerWorld = FindServerWorld();
			const AGameStateBase* GameState = ServerWorld ? ServerWorld->GetGameState() : nullptr;
			if (!ServerWorld || !ServerWorld->HasBegunPlay() || MapOf(ServerWorld) != MapName || !GameState || GameState->PlayerArray.Num() != NumPlayers)
			{
				return false;
			}
			for (const APlayerState* PlayerState : GameState->PlayerArray)
			{
				if (!PlayerState || PlayerState->GetPlayerId() == 0 || HealthOf(PlayerState->GetPawn()) <= 0.f)
				{
					return false;
				}
			}
			const TArray<UWorld*> SeatWorlds = GetSeatWorlds();
			if (SeatWorlds.Num() != NumPlayers)
			{
				return false;
			}
			for (const UWorld* SeatWorld : SeatWorlds)
			{
				const int32 MyId = LocalPlayerIdIn(SeatWorld);
				if (MyId == 0 || HealthOf(PawnIn(SeatWorld, MyId)) <= 0.f)
				{
					return false;
				}
			}
			return true;
		});

		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			UWorld* ServerWorld = FindServerWorld();
			Test.TestEqual(TEXT("server net mode"), static_cast<int32>(ServerWorld->GetNetMode()), static_cast<int32>(Ctx->bDedicated ? NM_DedicatedServer : NM_ListenServer));

			// A = 첫 클라이언트 자리, B = 다른 자리 (리슨이면 호스트)
			TArray<int32> ClientIds;
			TArray<int32> AllIds;
			for (const UWorld* SeatWorld : GetSeatWorlds())
			{
				AllIds.Add(LocalPlayerIdIn(SeatWorld));
				if (SeatWorld->GetNetMode() == NM_Client)
				{
					ClientIds.Add(LocalPlayerIdIn(SeatWorld));
				}
			}
			ClientIds.Sort();
			if (!Test.TestTrue(TEXT("a client seat exists"), ClientIds.Num() > 0))
			{
				Ctx->bAborted = true;
				return;
			}
			Ctx->Ids = { ClientIds[0] };
			for (const int32 PlayerId : AllIds)
			{
				if (PlayerId != ClientIds[0])
				{
					Ctx->Ids.Add(PlayerId);
				}
			}

			const UAstralChainBurstComponent* Chain = ChainIn(ServerWorld);
			if (!Test.TestNotNull(TEXT("chain component on the server's game state"), Chain))
			{
				Ctx->bAborted = true;
				return;
			}
			Ctx->WindowSeconds = FloatProperty(Chain, TEXT("WindowSeconds"));
			Ctx->MaxParticipants = Chain->GetMaxParticipants();
			Ctx->MaxGauge = AttributeOf(ServerASC(Ctx->Ids[0]), UAstralHeroResourceSet::GetMaxUltGaugeAttribute(), 0.f);
			Test.TestTrue(TEXT("the hero has an ult gauge with a positive max"), Ctx->MaxGauge > 0.f);

			// 적 — 서버에서 직접 세운다. 컨트롤러를 떼면 트리가 멈추고 제자리에 선다
			UClass* EnemyClass = StaticLoadClass(APawn::StaticClass(), nullptr, EnemyClassPath, nullptr, LOAD_NoWarn);
			UAstralEnemySpawnSubsystem* SpawnSubsystem = ServerWorld->GetSubsystem<UAstralEnemySpawnSubsystem>();
			if (!Test.TestNotNull(TEXT("enemy class"), EnemyClass) || !Test.TestNotNull(TEXT("enemy spawn subsystem on the server"), SpawnSubsystem))
			{
				Ctx->bAborted = true;
				return;
			}
			AAstralCombatCharacter* Enemy = Cast<AAstralCombatCharacter>(SpawnSubsystem->SpawnEnemy(EnemyClass, FTransform(FRotator::ZeroRotator, EnemyLocation)));
			if (!Test.TestNotNull(TEXT("enemy spawned on the server"), Enemy))
			{
				Ctx->bAborted = true;
				return;
			}
			if (AController* Controller = Enemy->GetController())
			{
				Controller->UnPossess();
			}
			Ctx->Enemy = Enemy;
		});

		Wait(Ctx, TEXT("the enemy's health set is ready on the server"), 30.0, [Ctx]() { return Ctx->Enemy.IsValid() && HealthOf(Ctx->Enemy.Get()) > 0.f; });
		Do(Ctx, [Ctx]()
		{
			UAbilitySystemComponent* EnemyASC = Ctx->Enemy->GetAbilitySystemComponent();
			if (!Ctx->Test->TestNotNull(TEXT("enemy ASC"), EnemyASC))
			{
				Ctx->bAborted = true;
				return;
			}
			EnemyASC->SetNumericAttributeBase(UAstralHealthSet::GetMaxHealthAttribute(), SturdyHealth);
			EnemyASC->SetNumericAttributeBase(UAstralHealthSet::GetHealthAttribute(), SturdyHealth);
		});
		PlaceHeroes(Ctx);

		// H0 — HUD 가 원천에 붙을 때까지(클라이언트는 폰 · ASC · GameState 가 늦게 올 수 있다 — 위젯이 이벤트로 붙는다)
		Wait(Ctx, TEXT("H0: every seat has a combat HUD bound to its own ASC and its chain component"), 15.0, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Ids)
			{
				const UAstralCombatHUDWidget* Hud = HudOf(PlayerId);
				const UAstralChainBurstComponent* SeatChain = ChainIn(FindSeatWorld(PlayerId));
				if (!Hud || !SeatChain || Hud->GetBoundAbilitySystem() != SeatASC(PlayerId) || Hud->GetBoundChainBurst() != SeatChain || !GaugeMatchesSeat(*Ctx, PlayerId))
				{
					return false;
				}
			}
			return true;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const UAstralCombatHUDWidget* FirstHud = HudOf(Ctx->Ids[0]);
			Ctx->UltBlockedSeconds = FloatProperty(FirstHud, TEXT("UltBlockedSeconds"));
			Ctx->BurstBannerSeconds = FloatProperty(FirstHud, TEXT("BurstBannerSeconds"));
			for (const int32 PlayerId : Ctx->Ids)
			{
				const UAstralCombatHUDWidget* Hud = HudOf(PlayerId);
				Test.TestEqual(TEXT("H0: the HUD is the promoted WBP"), GetPathNameSafe(Hud ? Hud->GetClass() : nullptr), FString(PromotedHudClassPath));
				Test.TestTrue(TEXT("H0: the HUD is in the viewport"), Hud && Hud->IsInViewport());
				for (const TCHAR* Name : { UltGaugeName, UltReadyPanelName, UltReadyGlowName, UltKeyName, UltBlockedName, ChainPanelName, ChainRingName, ChainTimerName, ChainCountName, BurstBannerName, BurstCountName })
				{
					Test.TestNotNull(*FString::Printf(TEXT("H0: bound widget %s exists"), Name), PartOf(PlayerId, Name));
				}
				const bool bFull = GaugeOf(SeatASC(PlayerId)) >= Ctx->MaxGauge - 0.01f;
				Test.TestTrue(TEXT("H0: the ready sign follows the gauge"), Shown(PlayerId, UltReadyPanelName) == bFull);
				Test.TestTrue(TEXT("H0: the key hint is visible only with a full gauge"), ShownOnScreen(PlayerId, UltKeyName) == bFull);
				Test.TestFalse(TEXT("H0: the gauge does not start full (the key hint starts hidden)"), bFull);
				Test.TestFalse(TEXT("H0: no chain panel without a chain"), Shown(PlayerId, ChainPanelName));
				Test.TestFalse(TEXT("H0: no burst banner at start"), Shown(PlayerId, BurstBannerName));
				Test.TestFalse(TEXT("H0: no 'ult blocked' at start"), Shown(PlayerId, UltBlockedName));
			}
			Note(Test, FString::Printf(TEXT("H0: %s, A %d B %d, window %.2f, max participants %d, blocked %.2fs, banner %.2fs — %s"),
				Ctx->bDedicated ? TEXT("dedicated") : TEXT("listen"), Ctx->Ids[0], Ctx->Ids[1], Ctx->WindowSeconds, Ctx->MaxParticipants,
				Ctx->UltBlockedSeconds, Ctx->BurstBannerSeconds, *Describe(*Ctx)));
		});
	}

	void EnqueueGaugeShort(const TSharedRef<FContext>& Ctx)
	{
		// H1 — 게이지가 모자란 채 누름: 실패 통지는 오지만 차단 태그가 없으니 '오의 불가' 는 뜨지 않는다
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestTrue(TEXT("H1: A's gauge starts below max"), GaugeOf(SeatASC(Ctx->Ids[0])) < Ctx->MaxGauge - 0.01f);
		});
		PressUlt(Ctx, 0);
		Hold(Ctx, 0.6);
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestFalse(TEXT("H1: no ult without a full gauge"), HasTag(ServerASC(Ctx->Ids[0]), UltActiveTagName));
			Ctx->Test->TestFalse(TEXT("H1: a short gauge does not show 'ult blocked'"), Shown(Ctx->Ids[0], UltBlockedName));
		});
	}

	/** A 자리의 키 배치를 바꿔도 B 자리 글자는 자기 배치 그대로다 */
	void TestKeyUnchangedElsewhere(FContext& Ctx)
	{
		Ctx.Test->TestEqual(TEXT("H2: B's key hint keeps B's own mapping"), TextOf(Ctx.Ids[1], UltKeyName), ExpectedKey(Ctx.Ids[1]));
		Ctx.Test->TestNotEqual(TEXT("H2: B's key hint did not change with A's mapping"), TextOf(Ctx.Ids[1], UltKeyName), FString(TEXT("T")));
	}

	void EnqueueFill(const TSharedRef<FContext>& Ctx)
	{
		Fill(Ctx, 0);
		Fill(Ctx, 1);
		Wait(Ctx, TEXT("H2: both HUDs show a full gauge with the ready sign and the key hint"), 5.0, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Ids)
			{
				if (!FMath::IsNearlyEqual(PercentOf(PlayerId), 1.f, 0.001f) || !ShownOnScreen(PlayerId, UltReadyGlowName) || !ShownOnScreen(PlayerId, UltKeyName))
				{
					return false;
				}
			}
			return true;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			for (const int32 PlayerId : Ctx->Ids)
			{
				const FString Expected = ExpectedKey(PlayerId);
				Test.TestFalse(TEXT("H2: the ult action has a key on this seat"), Expected.IsEmpty());
				Test.TestEqual(*FString::Printf(TEXT("H2: seat %d shows the mapped key"), PlayerId), TextOf(PlayerId, UltKeyName), Expected);
			}
			Note(Test, FString::Printf(TEXT("H2: full — %s"), *Describe(*Ctx)));

			// 키 배치를 바꾼다(A 자리에 오의 = T 를 더 높은 우선순위로) — 글자가 통지로 따라 바뀌는가
			UEnhancedInputLocalPlayerSubsystem* Input = InputOf(Ctx->Ids[0]);
			const UInputAction* Action = LoadObject<UInputAction>(nullptr, UltActionPath);
			if (!Test.TestNotNull(TEXT("enhanced input on A's seat"), Input) || !Test.TestNotNull(TEXT("IA_Ult"), Action))
			{
				Ctx->bAborted = true;
				return;
			}
			Ctx->KeyBefore = TextOf(Ctx->Ids[0], UltKeyName);
			Ctx->ExtraMapping.Reset(NewObject<UInputMappingContext>(GetTransientPackage()));
			Ctx->ExtraMapping->MapKey(Action, EKeys::T);
			Input->AddMappingContext(Ctx->ExtraMapping.Get(), 1000);
		});
		Wait(Ctx, TEXT("H2: the key hint follows a remapped key"), 5.0, [Ctx]() { return TextOf(Ctx->Ids[0], UltKeyName) == TEXT("T"); });
		Do(Ctx, [Ctx]()
		{
			TestKeyUnchangedElsewhere(*Ctx);
			if (UEnhancedInputLocalPlayerSubsystem* Input = InputOf(Ctx->Ids[0]))
			{
				Input->RemoveMappingContext(Ctx->ExtraMapping.Get());
			}
		});
		Wait(Ctx, TEXT("H2: the key hint returns with the mapping"), 5.0, [Ctx]() { return TextOf(Ctx->Ids[0], UltKeyName) == Ctx->KeyBefore; });
		Do(Ctx, [Ctx]() { Ctx->ExtraMapping.Reset(); });
	}

	void EnqueueFirstCast(const TSharedRef<FContext>& Ctx)
	{
		// H3 — A 가 쓰는 동안 B 는 차단된다. 차단이 B 자리에 복제된 뒤 B 가 누르면 B 자리의 HUD 에 '오의 불가'
		PressUlt(Ctx, 0);
		Wait(Ctx, TEXT("H3: A's ult is active on the server"), 5.0, [Ctx]() { return HasTag(ServerASC(Ctx->Ids[0]), UltActiveTagName); });
		Wait(Ctx, TEXT("H3: the block reaches B's own seat while A casts"), 3.0, [Ctx]()
		{
			return HasTag(SeatASC(Ctx->Ids[1]), UltBlockedTagName) && HasTag(ServerASC(Ctx->Ids[0]), UltActiveTagName);
		});
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestFalse(TEXT("H3: B's HUD shows no 'ult blocked' before B presses"), Shown(Ctx->Ids[1], UltBlockedName));
		});
		PressUlt(Ctx, 1);
		Wait(Ctx, TEXT("H3: B's HUD shows 'ult blocked' after pressing while blocked"), 1.0, [Ctx]() { return Shown(Ctx->Ids[1], UltBlockedName); });
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			Test.TestFalse(TEXT("H3: B's ult did not start"), HasTag(ServerASC(Ctx->Ids[1]), UltActiveTagName));
			Test.TestFalse(TEXT("H3: A's HUD shows no 'ult blocked'"), Shown(Ctx->Ids[0], UltBlockedName));
			for (const int32 PlayerId : Ctx->Ids)
			{
				Test.TestFalse(TEXT("H3: no chain panel while the first ult is still casting"), Shown(PlayerId, ChainPanelName));
			}
			Note(Test, FString::Printf(TEXT("H3: blocked shown — %s"), *Describe(*Ctx)));
		});
		Wait(Ctx, TEXT("H3: A's HUD shows the spent gauge (0) without the ready sign and the key hint"), 5.0, [Ctx]()
		{
			return FMath::IsNearlyZero(PercentOf(Ctx->Ids[0]), 0.001f) && !Shown(Ctx->Ids[0], UltReadyPanelName) && !ShownOnScreen(Ctx->Ids[0], UltKeyName)
				&& GaugeMatchesSeat(*Ctx, Ctx->Ids[0]);
		});
		Hold(Ctx, 0.3);
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestTrue(TEXT("H3: 'ult blocked' stays up for a while"), Shown(Ctx->Ids[1], UltBlockedName));
		});
		// 제한 시간은 큐에 넣을 때 정해진다 — 잠정 1.5초보다 넉넉히
		Wait(Ctx, TEXT("H3: 'ult blocked' hides after UltBlockedSeconds"), 4.0, [Ctx]() { return !Shown(Ctx->Ids[1], UltBlockedName); });

		// H4 — A 가 맞히고 끝나면 그 시각에 체인이 열린다. 두 자리에 패널 · 1/최대 · 줄어드는 남은 시간
		Wait(Ctx, TEXT("H4: A's ult ends and opens chain #1 with A on the server"), 15.0, [Ctx]()
		{
			const FAstralChainState State = ServerState();
			return !HasTag(ServerASC(Ctx->Ids[0]), UltActiveTagName) && State.Phase == EAstralChainPhase::Open && State.ParticipantIds == TArray<int32>({ Ctx->Ids[0] });
		});
		Wait(Ctx, TEXT("H4: both HUDs show the chain panel with 1/max"), 3.0, [Ctx]()
		{
			const FString Expected = FString::Printf(TEXT("1/%d"), Ctx->MaxParticipants);
			for (const int32 PlayerId : Ctx->Ids)
			{
				if (!Shown(PlayerId, ChainPanelName) || TextOf(PlayerId, ChainCountName) != Expected)
				{
					return false;
				}
			}
			return true;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			for (const int32 PlayerId : Ctx->Ids)
			{
				const float Remaining = NumberOf(PlayerId, ChainTimerName);
				Test.TestTrue(*FString::Printf(TEXT("H4: seat %d shows a remaining time within the window (%.1f)"), PlayerId, Remaining), Remaining > 0.f && Remaining <= Ctx->WindowSeconds + 0.05f);
				Test.TestTrue(*FString::Printf(TEXT("H4: seat %d's ring shows remaining / window (ring %.3f, want %.3f)"), PlayerId, RingOf(PlayerId), ExpectedRing(PlayerId)),
					FMath::IsNearlyEqual(RingOf(PlayerId), ExpectedRing(PlayerId), RingTolerance));
				Test.TestTrue(*FString::Printf(TEXT("H4: seat %d's ring agrees with the number (ring %.3f x window = %.2f, text %.1f)"), PlayerId, RingOf(PlayerId),
					RingOf(PlayerId) * Ctx->WindowSeconds, Remaining), FMath::IsNearlyEqual(RingOf(PlayerId) * Ctx->WindowSeconds, Remaining, 0.06f));
			}
			SnapshotTimers(*Ctx);
		});
		Hold(Ctx, 0.5);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			for (const int32 PlayerId : Ctx->Ids)
			{
				const float Before = FCString::Atof(*Ctx->TimerTexts.FindRef(PlayerId));
				const float After = NumberOf(PlayerId, ChainTimerName);
				Test.TestTrue(*FString::Printf(TEXT("H4: seat %d's remaining time counts down (%.1f -> %.1f)"), PlayerId, Before, After), After < Before - 0.2f);
				const float RingBefore = Ctx->RingPercents.FindRef(PlayerId);
				Test.TestTrue(*FString::Printf(TEXT("H4: seat %d's ring empties with it (%.3f -> %.3f)"), PlayerId, RingBefore, RingOf(PlayerId)),
					RingOf(PlayerId) < RingBefore - 0.2f / Ctx->WindowSeconds && FMath::IsNearlyEqual(RingOf(PlayerId), ExpectedRing(PlayerId), RingTolerance));
			}
			Note(Test, FString::Printf(TEXT("H4: chain open — %s"), *Describe(*Ctx)));
		});
	}

	void EnqueueSecondCast(const TSharedRef<FContext>& Ctx)
	{
		// H5 — B 가 쓰는 동안 열린 체인의 타이머가 멈춘다. 두 자리의 남은 시간 글자가 그대로
		Wait(Ctx, TEXT("H5: B is unblocked on its own seat"), 3.0, [Ctx]() { return !HasTag(SeatASC(Ctx->Ids[1]), UltBlockedTagName); });
		Face(Ctx, 1);
		PressUlt(Ctx, 1);
		Wait(Ctx, TEXT("H5: B casts and the chain timer is paused on the server and on both seats"), 5.0, [Ctx]()
		{
			if (!HasTag(ServerASC(Ctx->Ids[1]), UltActiveTagName) || !ServerState().bTimerPaused)
			{
				return false;
			}
			for (const int32 PlayerId : Ctx->Ids)
			{
				const UAstralChainBurstComponent* SeatChain = ChainIn(FindSeatWorld(PlayerId));
				if (!SeatChain || !SeatChain->GetChainState().bTimerPaused)
				{
					return false;
				}
			}
			return true;
		});
		Do(Ctx, [Ctx]() { SnapshotTimers(*Ctx); });
		Hold(Ctx, 0.5);
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			const FString ExpectedCount = FString::Printf(TEXT("1/%d"), Ctx->MaxParticipants);
			for (const int32 PlayerId : Ctx->Ids)
			{
				const FString Before = Ctx->TimerTexts.FindRef(PlayerId);
				const FString After = TextOf(PlayerId, ChainTimerName);
				Test.TestEqual(*FString::Printf(TEXT("H5: seat %d's remaining time stands still while B casts"), PlayerId), After, Before);
				const float RingBefore = Ctx->RingPercents.FindRef(PlayerId);
				Test.TestTrue(*FString::Printf(TEXT("H5: seat %d's ring stands still with it (%.4f -> %.4f, want %.4f)"), PlayerId, RingBefore, RingOf(PlayerId), ExpectedRing(PlayerId)),
					RingBefore > 0.f && FMath::IsNearlyEqual(RingOf(PlayerId), RingBefore, 1.e-4f) && FMath::IsNearlyEqual(RingOf(PlayerId), ExpectedRing(PlayerId), 0.002f));
				Test.TestTrue(TEXT("H5: the chain panel stays up while paused"), Shown(PlayerId, ChainPanelName));
				Test.TestEqual(TEXT("H5: still 1/max while B casts"), TextOf(PlayerId, ChainCountName), ExpectedCount);
			}
			Note(Test, FString::Printf(TEXT("H5: paused — %s"), *Describe(*Ctx)));
		});

		// H6 — B 가 맞히고 끝나면 살아 있는 2명 전원이 차서 바로 닫히고 버스트가 나간다. 배너는 단계가 아니라 번호 변화로 뜬다
		Wait(Ctx, TEXT("H6: B's ult ends and burst #1 x2 fires on the server"), 15.0, [Ctx]()
		{
			const FAstralChainState State = ServerState();
			return !HasTag(ServerASC(Ctx->Ids[1]), UltActiveTagName) && State.LastBurstChainId == 1 && State.LastBurstCount == 2;
		});
		Wait(Ctx, TEXT("H6: both HUDs show the burst banner with 2 and drop the chain panel"), 3.0, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Ids)
			{
				if (!Shown(PlayerId, BurstBannerName) || TextOf(PlayerId, BurstCountName) != TEXT("2") || Shown(PlayerId, ChainPanelName))
				{
					return false;
				}
			}
			return true;
		});
		Do(Ctx, [Ctx]() { Note(*Ctx->Test, FString::Printf(TEXT("H6: burst — %s"), *Describe(*Ctx))); });
		// 제한 시간은 큐에 넣을 때 정해진다(그때는 프로퍼티를 아직 안 읽었다) — 잠정 2.5초보다 넉넉히
		Wait(Ctx, TEXT("H6: the burst banner hides after BurstBannerSeconds"), 6.0, [Ctx]()
		{
			for (const int32 PlayerId : Ctx->Ids)
			{
				if (Shown(PlayerId, BurstBannerName))
				{
					return false;
				}
			}
			return true;
		});
		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			for (const int32 PlayerId : Ctx->Ids)
			{
				Test.TestTrue(TEXT("H6: the HUD gauge still follows the seat"), GaugeMatchesSeat(*Ctx, PlayerId));
			}
		});
	}

	void EnqueueAll(FAutomationTestBase& Test, bool bDedicated)
	{
		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;
		Ctx->bDedicated = bDedicated;

		EnqueueSetup(Ctx);
		EnqueueGaugeShort(Ctx);
		EnqueueFill(Ctx);
		EnqueueFirstCast(Ctx);
		EnqueueSecondCast(Ctx);
		EndPie(Ctx);
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralCombatHUDListenPieTest, "AstralBreak.Net.CombatHUD.ListenPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralCombatHUDListenPieTest::RunTest(const FString& Parameters)
{
	AstralCombatHUDPie::EnqueueAll(*this, /*bDedicated=*/false);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralCombatHUDDedicatedPieTest, "AstralBreak.Net.CombatHUD.DedicatedPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FAstralCombatHUDDedicatedPieTest::RunTest(const FString& Parameters)
{
	AstralCombatHUDPie::EnqueueAll(*this, /*bDedicated=*/true);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
