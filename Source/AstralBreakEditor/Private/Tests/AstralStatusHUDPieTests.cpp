// 메인 HUD(내 상태 · 동료) 시험 — 한 프로세스 멀티 PIE 2인 (설계 Docs/Design/ui-autogen-pipeline.md §11 '메인 HUD 설계')
//
// 리슨 서버 · Dedicated 를 PIE 로 띄워 CombatTestMap 에서 두 사람(A = 첫 클라이언트 자리, B = 다른 자리)의 StatusHUD(승격본 WBP) 바인딩 위젯 값을 직접 읽는다.
// 값은 서버에서 바꾸고(속성 · 디버그 명령) 두 자리 화면을 본다. 사람 몫은 화면 모양 눈 확인뿐이다.
//
//   S0  자리마다 HUD 가 있고(승격본 WBP · 뷰포트 안 · 보임) 나 = 자기 PlayerState, 동료 1 = 상대. 값 = 그 자리에서 보이는 속성, 동료 2 · 3 줄은 접힘
//   S1  서버가 A 의 HP 를 줄임 → A 자리의 내 HP(막대 · 숫자)와 B 자리의 동료 HP 가 같은 비율. B 의 내 HP 는 그대로
//   S2  A 의 최대 HP 를 올림 → 두 자리 비율이 다시 계산된다(최대치 통지)
//   S3  B 가 FillUlt → A 자리의 동료 오의 막대 1, B 자리의 동료(= A) 오의 막대는 A 의 값 그대로
//   S4  서버가 A 의 스태미나 · 표식을 바꿈 → A 자리 화면이 따라온다(B 자리 화면에는 A 의 스태미나가 없다)
//   S5  A 자리 명단에서 B 를 뺌 → 동료 줄이 접히고, 다시 넣으면 같은 이름 · 값으로 돌아온다

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "AstralPieTestHelpers.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Components/ProgressBar.h"
#include "Components/TextBlock.h"
#include "Components/Widget.h"
#include "Engine/GameInstance.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerState.h"
#include "Player/AstralPlayerController.h"
#include "Player/AstralPlayerState.h"
#include "UI/HUD/AstralStatusHUDWidget.h"

namespace AstralStatusHUDPie
{
	using namespace AstralPieTest;

	const TCHAR* const MapPath = TEXT("/Game/Maps/CombatTestMap");
	const TCHAR* const MapName = TEXT("CombatTestMap");
	const TCHAR* const PromotedHudClassPath = TEXT("/Game/UI/HUD/StatusHUD/WBP_StatusHUD.WBP_StatusHUD_C");

	constexpr int32 NumPlayers = 2;
	/** 화면 값 ↔ 그 자리 속성의 차 — 같은 순간의 값이라 반올림뿐 */
	constexpr float Tolerance = 0.002f;

	struct FContext : FContextBase
	{
		bool bDedicated = false;

		/** [0] = A(첫 클라이언트 자리), [1] = B */
		TArray<int32> Ids;

		float MaxHealth = 0.f;
		FString NameOfB;
	};

	// ─── 조회 ───

	APlayerController* GetLocalPC(const UWorld* World)
	{
		const UGameInstance* GameInstance = World ? World->GetGameInstance() : nullptr;
		return GameInstance ? GameInstance->GetFirstLocalPlayerController(World) : nullptr;
	}

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

	AAstralPlayerState* StateIn(const UWorld* World, int32 PlayerId)
	{
		const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;
		if (GameState)
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

	AAstralCharacter* PawnIn(const UWorld* World, int32 PlayerId)
	{
		const AAstralPlayerState* PlayerState = StateIn(World, PlayerId);
		return PlayerState ? Cast<AAstralCharacter>(PlayerState->GetPawn()) : nullptr;
	}

	/** 그 월드에서 보이는 그 플레이어의 ASC — 동료 것도 PlayerState 로 본다 */
	UAbilitySystemComponent* AscIn(const UWorld* World, int32 PlayerId)
	{
		const AAstralPlayerState* PlayerState = StateIn(World, PlayerId);
		return PlayerState ? PlayerState->GetAbilitySystemComponent() : nullptr;
	}

	float AttributeOf(const UAbilitySystemComponent* ASC, const FGameplayAttribute& Attribute)
	{
		return (ASC && ASC->HasAttributeSetForAttribute(Attribute)) ? ASC->GetNumericAttribute(Attribute) : -1.f;
	}

	float RatioOf(const UAbilitySystemComponent* ASC, const FGameplayAttribute& Current, const FGameplayAttribute& Max)
	{
		const float MaxValue = AttributeOf(ASC, Max);
		return MaxValue > 0.f ? AttributeOf(ASC, Current) / MaxValue : -1.f;
	}

	float HpRatio(const UAbilitySystemComponent* ASC) { return RatioOf(ASC, UAstralHealthSet::GetHealthAttribute(), UAstralHealthSet::GetMaxHealthAttribute()); }
	float UltRatio(const UAbilitySystemComponent* ASC) { return RatioOf(ASC, UAstralHeroResourceSet::GetUltGaugeAttribute(), UAstralHeroResourceSet::GetMaxUltGaugeAttribute()); }
	float StaminaRatio(const UAbilitySystemComponent* ASC) { return RatioOf(ASC, UAstralHeroResourceSet::GetStaminaAttribute(), UAstralHeroResourceSet::GetMaxStaminaAttribute()); }

	// ─── HUD 읽기 ───

	UAstralStatusHUDWidget* HudOf(int32 PlayerId)
	{
		const AAstralPlayerController* PC = Cast<AAstralPlayerController>(GetLocalPC(FindSeatWorld(PlayerId)));
		return PC ? PC->GetStatusHUDWidget() : nullptr;
	}

	UWidget* PartOf(int32 PlayerId, const FString& Name)
	{
		UAstralStatusHUDWidget* Hud = HudOf(PlayerId);
		return Hud ? Hud->GetWidgetFromName(FName(*Name)) : nullptr;
	}

	bool Shown(int32 PlayerId, const FString& Name)
	{
		const UWidget* Widget = PartOf(PlayerId, Name);
		return Widget && Widget->GetVisibility() != ESlateVisibility::Collapsed && Widget->GetVisibility() != ESlateVisibility::Hidden;
	}

	float PercentOf(int32 PlayerId, const FString& Name)
	{
		const UProgressBar* Bar = Cast<UProgressBar>(PartOf(PlayerId, Name));
		return Bar ? Bar->GetPercent() : -1.f;
	}

	FString TextOf(int32 PlayerId, const FString& Name)
	{
		const UTextBlock* Text = Cast<UTextBlock>(PartOf(PlayerId, Name));
		return Text ? Text->GetText().ToString() : FString(TEXT("<none>"));
	}

	bool Near(float A, float B) { return FMath::IsNearlyEqual(A, B, Tolerance); }

	/** 자리의 내 상태가 자기 ASC 의 지금 값과 같은가 */
	bool SelfMatches(int32 PlayerId)
	{
		const UAbilitySystemComponent* ASC = AscIn(FindSeatWorld(PlayerId), PlayerId);
		return Near(PercentOf(PlayerId, TEXT("SelfHpBar")), HpRatio(ASC)) && Near(PercentOf(PlayerId, TEXT("SelfStaminaBar")), StaminaRatio(ASC))
			&& TextOf(PlayerId, TEXT("SelfHpText")) == FString::FromInt(FMath::CeilToInt32(AttributeOf(ASC, UAstralHealthSet::GetHealthAttribute())))
			&& TextOf(PlayerId, TEXT("SelfMarkText")) == FString::FromInt(FMath::FloorToInt32(AttributeOf(ASC, UAstralHeroResourceSet::GetMarkStackAttribute())));
	}

	/** 자리의 동료 1 줄이 상대의(그 자리에서 보이는) 값과 같은가 */
	bool AllyMatches(int32 PlayerId, int32 OtherId)
	{
		const UWorld* SeatWorld = FindSeatWorld(PlayerId);
		const AAstralPlayerState* Other = StateIn(SeatWorld, OtherId);
		const UAbilitySystemComponent* ASC = AscIn(SeatWorld, OtherId);
		return Other && Shown(PlayerId, TEXT("Ally1Panel")) && TextOf(PlayerId, TEXT("Ally1NameText")) == Other->GetPlayerName()
			&& Near(PercentOf(PlayerId, TEXT("Ally1HpBar")), HpRatio(ASC)) && Near(PercentOf(PlayerId, TEXT("Ally1UltBar")), UltRatio(ASC));
	}

	FString DescribeHud(int32 PlayerId)
	{
		const UAstralStatusHUDWidget* Hud = HudOf(PlayerId);
		if (!Hud)
		{
			return FString::Printf(TEXT("%d: no HUD"), PlayerId);
		}
		const UAbilitySystemComponent* ASC = AscIn(FindSeatWorld(PlayerId), PlayerId);
		return FString::Printf(TEXT("%d: vis %d hp %.3f (%.3f) [%s] stamina %.3f (%.3f) mark [%s] | ally1 %d [%s] hp %.3f ult %.3f | ally2 %d ally3 %d"), PlayerId,
			static_cast<int32>(Hud->GetVisibility()), PercentOf(PlayerId, TEXT("SelfHpBar")), HpRatio(ASC), *TextOf(PlayerId, TEXT("SelfHpText")),
			PercentOf(PlayerId, TEXT("SelfStaminaBar")), StaminaRatio(ASC), *TextOf(PlayerId, TEXT("SelfMarkText")), Shown(PlayerId, TEXT("Ally1Panel")) ? 1 : 0,
			*TextOf(PlayerId, TEXT("Ally1NameText")), PercentOf(PlayerId, TEXT("Ally1HpBar")), PercentOf(PlayerId, TEXT("Ally1UltBar")),
			Shown(PlayerId, TEXT("Ally2Panel")) ? 1 : 0, Shown(PlayerId, TEXT("Ally3Panel")) ? 1 : 0);
	}

	FString Describe(const FContext& Ctx)
	{
		FString Out = FString::Printf(TEXT("server map '%s'"), *MapOf(FindServerWorld()));
		for (const int32 PlayerId : Ctx.Ids)
		{
			Out += TEXT(" | seat ") + DescribeHud(PlayerId);
		}
		return Out;
	}

	void Wait(const TSharedRef<FContext>& Ctx, const FString& What, double TimeoutSeconds, TFunction<bool()> Condition)
	{
		WaitUntil(Ctx, *What, TimeoutSeconds, MoveTemp(Condition), [Ctx]() { return Describe(*Ctx); });
	}

	void SetOnServer(const TSharedRef<FContext>& Ctx, int32 Index, const FGameplayAttribute& Attribute, float NewValue)
	{
		UAbilitySystemComponent* ASC = AscIn(FindServerWorld(), Ctx->Ids[Index]);
		if (!Ctx->Test->TestNotNull(TEXT("player's ASC on the server"), ASC))
		{
			Ctx->bAborted = true;
			return;
		}
		ASC->SetNumericAttributeBase(Attribute, NewValue);
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
			const TArray<UWorld*> SeatWorlds = GetSeatWorlds();
			if (SeatWorlds.Num() != NumPlayers)
			{
				return false;
			}
			for (const UWorld* SeatWorld : SeatWorlds)
			{
				const int32 MyId = LocalPlayerIdIn(SeatWorld);
				if (MyId == 0 || HpRatio(AscIn(SeatWorld, MyId)) <= 0.f || !PawnIn(SeatWorld, MyId) || !PawnIn(ServerWorld, MyId))
				{
					return false;
				}
			}
			return true;
		});

		Do(Ctx, [Ctx]()
		{
			FAutomationTestBase& Test = *Ctx->Test;
			Test.TestEqual(TEXT("server net mode"), static_cast<int32>(FindServerWorld()->GetNetMode()), static_cast<int32>(Ctx->bDedicated ? NM_DedicatedServer : NM_ListenServer));

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
			Ctx->MaxHealth = AttributeOf(AscIn(FindServerWorld(), Ctx->Ids[0]), UAstralHealthSet::GetMaxHealthAttribute());
			Test.TestTrue(TEXT("the hero has health"), Ctx->MaxHealth > 0.f);
		});

		// S0 — HUD 가 원천에 붙을 때까지(클라이언트는 명단 · 번호 · 이름 · 속성 세트가 늦게 올 수 있다 — 위젯이 이벤트로 붙는다)
		Wait(Ctx, TEXT("S0: every seat shows its own status and the other player"), 15.0, [Ctx]()
		{
			for (int32 Index = 0; Index < NumPlayers; ++Index)
			{
				const int32 PlayerId = Ctx->Ids[Index];
				const int32 OtherId = Ctx->Ids[1 - Index];
				const UAstralStatusHUDWidget* Hud = HudOf(PlayerId);
				const UWorld* SeatWorld = FindSeatWorld(PlayerId);
				if (!Hud || Hud->GetSlotPlayerState(0) != StateIn(SeatWorld, PlayerId) || Hud->GetSlotPlayerState(1) != StateIn(SeatWorld, OtherId)
					|| !SelfMatches(PlayerId) || !AllyMatches(PlayerId, OtherId))
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
				const UAstralStatusHUDWidget* Hud = HudOf(PlayerId);
				Test.TestEqual(TEXT("S0: the HUD is the promoted WBP"), GetPathNameSafe(Hud ? Hud->GetClass() : nullptr), FString(PromotedHudClassPath));
				Test.TestTrue(TEXT("S0: the HUD is in the viewport"), Hud && Hud->IsInViewport());
				Test.TestEqual(TEXT("S0: the HUD is visible on a raid map"), static_cast<int32>(Hud ? Hud->GetVisibility() : ESlateVisibility::Collapsed), static_cast<int32>(ESlateVisibility::SelfHitTestInvisible));
				for (const TCHAR* Name : { TEXT("SelfHpBar"), TEXT("SelfHpText"), TEXT("SelfStaminaBar"), TEXT("SelfMarkText"), TEXT("Ally1Panel"), TEXT("Ally1NameText"), TEXT("Ally1HpBar"), TEXT("Ally1UltBar"),
					TEXT("Ally2Panel"), TEXT("Ally2NameText"), TEXT("Ally2HpBar"), TEXT("Ally2UltBar"), TEXT("Ally3Panel"), TEXT("Ally3NameText"), TEXT("Ally3HpBar"), TEXT("Ally3UltBar") })
				{
					Test.TestNotNull(*FString::Printf(TEXT("S0: bound widget %s exists"), Name), PartOf(PlayerId, Name));
				}
				Test.TestTrue(TEXT("S0: own health starts full"), Near(PercentOf(PlayerId, TEXT("SelfHpBar")), 1.f));
				Test.TestTrue(TEXT("S0: own stamina is read even though nothing has changed yet"), PercentOf(PlayerId, TEXT("SelfStaminaBar")) > 0.9f);
				Test.TestTrue(TEXT("S0: the ally is full too"), Near(PercentOf(PlayerId, TEXT("Ally1HpBar")), 1.f));
				Test.TestFalse(TEXT("S0: no second ally"), Shown(PlayerId, TEXT("Ally2Panel")));
				Test.TestFalse(TEXT("S0: no third ally"), Shown(PlayerId, TEXT("Ally3Panel")));
				Test.TestFalse(TEXT("S0: the ally has a name"), TextOf(PlayerId, TEXT("Ally1NameText")).IsEmpty());
			}
			Ctx->NameOfB = TextOf(Ctx->Ids[0], TEXT("Ally1NameText"));
			Note(Test, FString::Printf(TEXT("S0: %s, A %d B %d, max health %.0f — %s"), Ctx->bDedicated ? TEXT("dedicated") : TEXT("listen"), Ctx->Ids[0], Ctx->Ids[1], Ctx->MaxHealth, *Describe(*Ctx)));
		});
	}

	void EnqueueHealth(const TSharedRef<FContext>& Ctx)
	{
		// S1 — A 의 HP 40 %
		Do(Ctx, [Ctx]() { SetOnServer(Ctx, 0, UAstralHealthSet::GetHealthAttribute(), Ctx->MaxHealth * 0.4f); });
		Wait(Ctx, TEXT("S1: A's own bar and B's ally bar both show 40 %"), 5.0, [Ctx]()
		{
			return Near(PercentOf(Ctx->Ids[0], TEXT("SelfHpBar")), 0.4f) && Near(PercentOf(Ctx->Ids[1], TEXT("Ally1HpBar")), 0.4f) && SelfMatches(Ctx->Ids[0]);
		});
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestTrue(TEXT("S1: B's own bar is untouched"), Near(PercentOf(Ctx->Ids[1], TEXT("SelfHpBar")), 1.f));
			Ctx->Test->TestTrue(TEXT("S1: A's ally (B) is untouched"), Near(PercentOf(Ctx->Ids[0], TEXT("Ally1HpBar")), 1.f));
			Note(*Ctx->Test, FString::Printf(TEXT("S1: %s"), *Describe(*Ctx)));
		});

		// S2 — A 의 최대 HP 를 두 배로(현재값 그대로) → 비율 20 %
		Do(Ctx, [Ctx]() { SetOnServer(Ctx, 0, UAstralHealthSet::GetMaxHealthAttribute(), Ctx->MaxHealth * 2.f); });
		Wait(Ctx, TEXT("S2: a changed max health is shown on both seats"), 5.0, [Ctx]()
		{
			return Near(PercentOf(Ctx->Ids[0], TEXT("SelfHpBar")), 0.2f) && Near(PercentOf(Ctx->Ids[1], TEXT("Ally1HpBar")), 0.2f);
		});
		Do(Ctx, [Ctx]() { Note(*Ctx->Test, FString::Printf(TEXT("S2: %s"), *Describe(*Ctx))); });
	}

	void EnqueueResources(const TSharedRef<FContext>& Ctx)
	{
		// S3 — B 가 자기 자리에서 채운다(클라이언트는 Exec → 서버 RPC, 리슨 호스트는 바로)
		Do(Ctx, [Ctx]()
		{
			AAstralCharacter* SeatPawn = PawnIn(FindSeatWorld(Ctx->Ids[1]), Ctx->Ids[1]);
			if (!Ctx->Test->TestNotNull(TEXT("B's pawn on its own seat"), SeatPawn))
			{
				Ctx->bAborted = true;
				return;
			}
			Ctx->Test->TestFalse(TEXT("S3: B's gauge does not start full on A's screen"), Near(PercentOf(Ctx->Ids[0], TEXT("Ally1UltBar")), 1.f));
			SeatPawn->FillUlt();
		});
		Wait(Ctx, TEXT("S3: A's screen shows B's full ult gauge"), 10.0, [Ctx]() { return Near(PercentOf(Ctx->Ids[0], TEXT("Ally1UltBar")), 1.f); });
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestTrue(TEXT("S3: B's screen still shows A's own gauge"), AllyMatches(Ctx->Ids[1], Ctx->Ids[0]));
			Note(*Ctx->Test, FString::Printf(TEXT("S3: %s"), *Describe(*Ctx)));
		});

		// S4 — A 의 스태미나 · 표식 (스태미나는 회복하므로 '내려갔다' 와 '지금 값과 같다' 만 본다)
		Do(Ctx, [Ctx]()
		{
			SetOnServer(Ctx, 0, UAstralHeroResourceSet::GetStaminaAttribute(), 10.f);
			SetOnServer(Ctx, 0, UAstralHeroResourceSet::GetMarkStackAttribute(), 3.f);
		});
		Wait(Ctx, TEXT("S4: A's screen follows its stamina and marks"), 5.0, [Ctx]()
		{
			const float Percent = PercentOf(Ctx->Ids[0], TEXT("SelfStaminaBar"));
			return Percent >= 0.f && Percent < 0.8f && TextOf(Ctx->Ids[0], TEXT("SelfMarkText")) == TEXT("3");
		});
		Do(Ctx, [Ctx]()
		{
			Ctx->Test->TestTrue(TEXT("S4: A's screen equals its attributes"), SelfMatches(Ctx->Ids[0]));
			Ctx->Test->TestEqual(TEXT("S4: B's own marks are untouched"), TextOf(Ctx->Ids[1], TEXT("SelfMarkText")), FString(TEXT("0")));
			Ctx->Test->TestTrue(TEXT("S4: B's own stamina is untouched"), PercentOf(Ctx->Ids[1], TEXT("SelfStaminaBar")) > 0.9f);
			Note(*Ctx->Test, FString::Printf(TEXT("S4: %s"), *Describe(*Ctx)));
		});
	}

	void EnqueueRoster(const TSharedRef<FContext>& Ctx)
	{
		// S5 — A 자리의 명단에서만 B 를 뺐다 넣는다(나가고 들어올 때 엔진이 부르는 함수 그대로)
		Do(Ctx, [Ctx]()
		{
			UWorld* SeatWorld = FindSeatWorld(Ctx->Ids[0]);
			AAstralPlayerState* StateOfB = StateIn(SeatWorld, Ctx->Ids[1]);
			AGameStateBase* GameState = SeatWorld ? SeatWorld->GetGameState() : nullptr;
			if (!Ctx->Test->TestNotNull(TEXT("B's player state on A's seat"), StateOfB) || !Ctx->Test->TestNotNull(TEXT("game state on A's seat"), GameState))
			{
				Ctx->bAborted = true;
				return;
			}
			GameState->RemovePlayerState(StateOfB);
			Ctx->Test->TestFalse(TEXT("S5: the ally row closes when the player leaves"), Shown(Ctx->Ids[0], TEXT("Ally1Panel")));
			Ctx->Test->TestTrue(TEXT("S5: my own status stays"), SelfMatches(Ctx->Ids[0]));
			GameState->AddPlayerState(StateOfB);
			Ctx->Test->TestTrue(TEXT("S5: the ally row comes back with the same player"), AllyMatches(Ctx->Ids[0], Ctx->Ids[1]));
			Ctx->Test->TestEqual(TEXT("S5: ... and the same name"), TextOf(Ctx->Ids[0], TEXT("Ally1NameText")), Ctx->NameOfB);
			Note(*Ctx->Test, FString::Printf(TEXT("S5: %s"), *Describe(*Ctx)));
		});

		// 줄을 떼었다 붙인 뒤에도 통지가 이어진다
		Do(Ctx, [Ctx]() { SetOnServer(Ctx, 1, UAstralHealthSet::GetHealthAttribute(), AttributeOf(AscIn(FindServerWorld(), Ctx->Ids[1]), UAstralHealthSet::GetMaxHealthAttribute()) * 0.5f); });
		Wait(Ctx, TEXT("S5: the returned ally row still follows B's health"), 5.0, [Ctx]() { return Near(PercentOf(Ctx->Ids[0], TEXT("Ally1HpBar")), 0.5f); });
	}

	void EnqueueAll(FAutomationTestBase& Test, bool bDedicated)
	{
		TSharedRef<FContext> Ctx = MakeShared<FContext>();
		Ctx->Test = &Test;
		Ctx->bDedicated = bDedicated;
		EnqueueSetup(Ctx);
		EnqueueHealth(Ctx);
		EnqueueResources(Ctx);
		EnqueueRoster(Ctx);
		EndPie(Ctx);
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralStatusHUDListenPieTest, "AstralBreak.Net.StatusHUD.ListenPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FAstralStatusHUDListenPieTest::RunTest(const FString& Parameters)
{
	AstralStatusHUDPie::EnqueueAll(*this, /*bDedicated*/ false);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAstralStatusHUDDedicatedPieTest, "AstralBreak.Net.StatusHUD.DedicatedPIE", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FAstralStatusHUDDedicatedPieTest::RunTest(const FString& Parameters)
{
	AstralStatusHUDPie::EnqueueAll(*this, /*bDedicated*/ true);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
