// uigen 스텁 자리(사람 소유 — uigen 은 이 파일을 다시 쓰지 않는다).

#include "AstralStatusHUDWidget.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "Character/Components/AstralPawnExtensionComponent.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "GameModes/AstralGameState.h"
#include "GameModes/AstralPartyStatics.h"
#include "Player/AstralPlayerState.h"

namespace AstralStatusHUD
{
	float Value(const UAbilitySystemComponent* ASC, const FGameplayAttribute& Attribute)
	{
		return (ASC && ASC->HasAttributeSetForAttribute(Attribute)) ? ASC->GetNumericAttribute(Attribute) : 0.f;
	}

	/** 지금 값 ÷ 지금 최대 — 세트가 아직 없으면 0 */
	float Ratio(const UAbilitySystemComponent* ASC, const FGameplayAttribute& Current, const FGameplayAttribute& Max)
	{
		const float MaxValue = Value(ASC, Max);
		return MaxValue > 0.f ? Value(ASC, Current) / MaxValue : 0.f;
	}
}

AAstralPlayerState* UAstralStatusHUDWidget::GetSlotPlayerState(int32 SlotIndex) const
{
	return (SlotIndex >= 0 && SlotIndex < NumSlots) ? Slots[SlotIndex].PlayerState.Get() : nullptr;
}

void UAstralStatusHUDWidget::NativeConstruct()
{
	Super::NativeConstruct();

	// 에디터 렌더(WidgetMcp render_widget)는 spec 상태 · 덮어쓰기 그대로 그려야 한다(UAstralCombatHUDWidget 과 같은 까닭)
	UWorld* World = GetWorld();
	if (!GetOwningPlayer() || !World || !World->IsGameWorld())
	{
		return;
	}

	// 처음 모양 — 원천이 붙기 전에는 아무것도 띄우지 않는다. GameState 가 오면 HandleGameStateSet 이 켠다
	SetVisibility(ESlateVisibility::Collapsed);
	for (int32 SlotIndex = 0; SlotIndex < NumSlots; ++SlotIndex)
	{
		RefreshSlot(SlotIndex);
	}

	// GameState 는 클라이언트에서 늦게 올 수 있다 — 설정 통지를 계속 받고, 이미 있으면 바로 붙는다
	GameStateSetHandle = World->GameStateSetEvent.AddUObject(this, &ThisClass::HandleGameStateSet);
	if (AGameStateBase* GameState = World->GetGameState())
	{
		HandleGameStateSet(GameState);
	}
}

void UAstralStatusHUDWidget::NativeDestruct()
{
	if (UWorld* World = GetWorld())
	{
		World->GameStateSetEvent.Remove(GameStateSetHandle);
	}
	GameStateSetHandle.Reset();

	if (AAstralGameState* GameState = BoundGameState.Get())
	{
		GameState->OnPlayerRosterChanged.Remove(RosterChangedHandle);
	}
	RosterChangedHandle.Reset();
	BoundGameState.Reset();

	for (int32 SlotIndex = 0; SlotIndex < NumSlots; ++SlotIndex)
	{
		ClearSlot(SlotIndex);
	}

	Super::NativeDestruct();
}

// ─── 연결 ───

void UAstralStatusHUDWidget::HandleGameStateSet(AGameStateBase* GameState)
{
	AAstralGameState* AstralGameState = Cast<AAstralGameState>(GameState);
	if (AstralGameState != BoundGameState.Get())
	{
		if (AAstralGameState* OldGameState = BoundGameState.Get())
		{
			OldGameState->OnPlayerRosterChanged.Remove(RosterChangedHandle);
		}
		RosterChangedHandle.Reset();
		BoundGameState = AstralGameState;
		if (AstralGameState)
		{
			RosterChangedHandle = AstralGameState->OnPlayerRosterChanged.AddUObject(this, &ThisClass::HandleRosterChanged);
		}
	}

	// 어느 맵에 뜨는가는 그 맵의 목록(AAstralGameState::ContextHUDWidgets)이 정한다 — 여기서는 원천이 붙었는가만 본다
	SetVisibility(AstralGameState ? ESlateVisibility::SelfHitTestInvisible : ESlateVisibility::Collapsed);
	HandleRosterChanged();
}

void UAstralStatusHUDWidget::HandleRosterChanged()
{
	const APlayerController* PC = GetOwningPlayer();
	AAstralPlayerState* Self = PC ? PC->GetPlayerState<AAstralPlayerState>() : nullptr;
	SetSlot(0, Self);

	// 동료 — 후보 수집만 여기서, 고르는 규칙은 AstralParty::SelectAllyIndices (월드 없이 시험). 내가 누구인지 모르면 아직 그리지 않는다(나까지 동료로 보인다)
	TArray<AAstralPlayerState*, TInlineAllocator<8>> States;
	TArray<FAstralPartyMember, TInlineAllocator<8>> Members;
	if (const AAstralGameState* GameState = Self ? BoundGameState.Get() : nullptr)
	{
		for (APlayerState* PlayerState : GameState->PlayerArray)
		{
			AAstralPlayerState* AstralPS = Cast<AAstralPlayerState>(PlayerState);
			if (!AstralPS || AstralPS == Self || AstralPS->IsInactive())
			{
				continue;
			}
			FAstralPartyMember& Member = Members.AddDefaulted_GetRef();
			Member.PlayerId = AstralPS->GetPlayerId();
			Member.bIsBot = AstralPS->IsABot();
			Member.bIsSpectator = AstralPS->IsOnlyASpectator();
			States.Add(AstralPS);
		}
	}

	const TArray<int32> Allies = AstralParty::SelectAllyIndices(Members, Self ? Self->GetPlayerId() : 0, MaxAllies);
	for (int32 AllyIndex = 0; AllyIndex < MaxAllies; ++AllyIndex)
	{
		SetSlot(1 + AllyIndex, Allies.IsValidIndex(AllyIndex) ? States[Allies[AllyIndex]] : nullptr);
	}
}

void UAstralStatusHUDWidget::SetSlot(int32 SlotIndex, AAstralPlayerState* PlayerState)
{
	FPlayerSlot& PlayerSlot = Slots[SlotIndex];
	if (PlayerSlot.PlayerState.Get() != PlayerState || !PlayerState)
	{
		ClearSlot(SlotIndex);
		UAbilitySystemComponent* ASC = PlayerState ? PlayerState->GetAstralAbilitySystemComponent() : nullptr;
		if (ASC)
		{
			PlayerSlot.PlayerState = PlayerState;
			PlayerSlot.ASC = ASC;

			TArray<FGameplayAttribute, TInlineAllocator<8>> Attributes = { UAstralHealthSet::GetHealthAttribute(), UAstralHealthSet::GetMaxHealthAttribute() };
			if (SlotIndex == 0)
			{
				Attributes.Append({ UAstralHeroResourceSet::GetStaminaAttribute(), UAstralHeroResourceSet::GetMaxStaminaAttribute(), UAstralHeroResourceSet::GetMarkStackAttribute() });
			}
			else
			{
				Attributes.Append({ UAstralHeroResourceSet::GetUltGaugeAttribute(), UAstralHeroResourceSet::GetMaxUltGaugeAttribute() });
			}
			for (const FGameplayAttribute& Attribute : Attributes)
			{
				PlayerSlot.Handles.Emplace(Attribute, ASC->GetGameplayAttributeValueChangeDelegate(Attribute).AddUObject(this, &ThisClass::HandleSlotAttributeChanged, SlotIndex));
			}

			PlayerState->OnPawnSet.AddUniqueDynamic(this, &ThisClass::HandlePawnSet);
			WatchPawn(PlayerState->GetPawn());
		}
	}
	RefreshSlot(SlotIndex);
}

void UAstralStatusHUDWidget::ClearSlot(int32 SlotIndex)
{
	FPlayerSlot& PlayerSlot = Slots[SlotIndex];
	if (UAbilitySystemComponent* ASC = PlayerSlot.ASC.Get())
	{
		for (const TPair<FGameplayAttribute, FDelegateHandle>& Handle : PlayerSlot.Handles)
		{
			ASC->GetGameplayAttributeValueChangeDelegate(Handle.Key).Remove(Handle.Value);
		}
	}
	PlayerSlot.Handles.Reset();
	PlayerSlot.ASC.Reset();

	// 줄이 당겨져 같은 사람이 다른 칸에 앉아 있을 수 있다 — 다른 칸이 지켜보는 동안은 폰 통지를 떼지 않는다
	AAstralPlayerState* PlayerState = PlayerSlot.PlayerState.Get();
	PlayerSlot.PlayerState.Reset();
	if (PlayerState)
	{
		for (const FPlayerSlot& Other : Slots)
		{
			if (Other.PlayerState.Get() == PlayerState)
			{
				return;
			}
		}
		PlayerState->OnPawnSet.RemoveDynamic(this, &ThisClass::HandlePawnSet);
	}
}

void UAstralStatusHUDWidget::HandlePawnSet(APlayerState* Player, APawn* NewPawn, APawn* OldPawn)
{
	WatchPawn(NewPawn);
}

void UAstralStatusHUDWidget::WatchPawn(APawn* Pawn)
{
	if (UAstralPawnExtensionComponent* PawnExtension = UAstralPawnExtensionComponent::FindPawnExtensionComponent(Pawn))
	{
		PawnExtension->OnAbilitySystemInitialized_RegisterAndCall(FSimpleMulticastDelegate::FDelegate::CreateUObject(this, &ThisClass::HandleAbilitySystemInitialized));
	}
}

void UAstralStatusHUDWidget::HandleAbilitySystemInitialized()
{
	for (int32 SlotIndex = 0; SlotIndex < NumSlots; ++SlotIndex)
	{
		RefreshSlot(SlotIndex);
	}
}

// ─── 원천 → 화면 ───

void UAstralStatusHUDWidget::HandleSlotAttributeChanged(const FOnAttributeChangeData& Data, int32 SlotIndex)
{
	RefreshSlot(SlotIndex);
}

void UAstralStatusHUDWidget::RefreshSlot(int32 SlotIndex)
{
	const FPlayerSlot& PlayerSlot = Slots[SlotIndex];
	if (SlotIndex == 0)
	{
		RefreshSelf(PlayerSlot.ASC.Get());
	}
	else
	{
		RefreshAlly(SlotIndex - 1, PlayerSlot.PlayerState.Get(), PlayerSlot.ASC.Get());
	}
}

void UAstralStatusHUDWidget::RefreshSelf(const UAbilitySystemComponent* ASC)
{
	using namespace AstralStatusHUD;
	SetSelfHp(Ratio(ASC, UAstralHealthSet::GetHealthAttribute(), UAstralHealthSet::GetMaxHealthAttribute()));
	SetSelfHpValue(FMath::CeilToInt32(Value(ASC, UAstralHealthSet::GetHealthAttribute())));   // 살아 있는데 0 으로 보이지 않게 올림
	SetSelfStamina(Ratio(ASC, UAstralHeroResourceSet::GetStaminaAttribute(), UAstralHeroResourceSet::GetMaxStaminaAttribute()));
	SetSelfMark(FMath::FloorToInt32(Value(ASC, UAstralHeroResourceSet::GetMarkStackAttribute()) + KINDA_SMALL_NUMBER));
}

void UAstralStatusHUDWidget::RefreshAlly(int32 AllyIndex, const AAstralPlayerState* PlayerState, const UAbilitySystemComponent* ASC)
{
	using namespace AstralStatusHUD;
	SetAllyVisible(AllyIndex, PlayerState != nullptr);
	if (PlayerState)
	{
		SetAllyName(AllyIndex, FText::FromString(PlayerState->GetPlayerName()));
		SetAllyHp(AllyIndex, Ratio(ASC, UAstralHealthSet::GetHealthAttribute(), UAstralHealthSet::GetMaxHealthAttribute()));
		SetAllyUlt(AllyIndex, Ratio(ASC, UAstralHeroResourceSet::GetUltGaugeAttribute(), UAstralHeroResourceSet::GetMaxUltGaugeAttribute()));
	}
}

void UAstralStatusHUDWidget::SetAllyVisible(int32 AllyIndex, bool bVisible)
{
	switch (AllyIndex)
	{
	case 0: SetAlly1PanelVisible(bVisible); break;
	case 1: SetAlly2PanelVisible(bVisible); break;
	case 2: SetAlly3PanelVisible(bVisible); break;
	default: break;
	}
}

void UAstralStatusHUDWidget::SetAllyName(int32 AllyIndex, const FText& Name)
{
	switch (AllyIndex)
	{
	case 0: SetAlly1Name(Name); break;
	case 1: SetAlly2Name(Name); break;
	case 2: SetAlly3Name(Name); break;
	default: break;
	}
}

void UAstralStatusHUDWidget::SetAllyHp(int32 AllyIndex, float Percent)
{
	switch (AllyIndex)
	{
	case 0: SetAlly1Hp(Percent); break;
	case 1: SetAlly2Hp(Percent); break;
	case 2: SetAlly3Hp(Percent); break;
	default: break;
	}
}

void UAstralStatusHUDWidget::SetAllyUlt(int32 AllyIndex, float Percent)
{
	switch (AllyIndex)
	{
	case 0: SetAlly1Ult(Percent); break;
	case 1: SetAlly2Ult(Percent); break;
	case 2: SetAlly3Ult(Percent); break;
	default: break;
	}
}
