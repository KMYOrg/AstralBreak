// uigen 이 처음 한 번 만든 스텁 — 이제 사람 소유다. uigen 은 이 파일을 다시 쓰지 않는다.

#include "AstralCombatHUDWidget.h"

#include "AbilitySystemComponent.h"
#include "Abilities/GameplayAbility.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/AstralAbilitySystemComponent.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "Character/Components/AstralPawnExtensionComponent.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "GameModes/AstralChainBurstComponent.h"
#include "TimerManager.h"

void UAstralCombatHUDWidget::NativeConstruct()
{
	Super::NativeConstruct();

	// 게임 월드에서 소유 플레이어가 있을 때만 원천에 붙고 시작 모양을 정한다. 에디터 렌더(WidgetMcp render_widget — uigen 검증 · 진단)는 편집기 월드에
	// 소유자 없이 만들어 spec 상태 · 덮어쓰기(force_visible · overrides) 그대로 그려야 한다 — 덮어쓰기는 TakeWidget(= 이 함수) 전에 들어간다
	// [실측 R20261119_141345_CombatHUD — 여기서 접고 0 으로 만들어 렌더 · 구조 게이트 iou_region · iou_leaf 가 not_painted]
	const UWorld* World = GetWorld();
	APlayerController* PC = GetOwningPlayer();
	if (!PC || !World || !World->IsGameWorld())
	{
		return;
	}

	// 처음 모양 — 원천이 붙기 전에는 아무것도 띄우지 않는다
	SetUltGauge(0.f);
	SetUltReadyVisible(false);
	SetUltBlockedVisible(false);
	SetChainPanelVisible(false);
	SetBurstBannerVisible(false);

	PC->OnPossessedPawnChanged.AddUniqueDynamic(this, &ThisClass::HandlePossessedPawnChanged);
	HandlePossessedPawnChanged(nullptr, PC->GetPawn());

	// GameState 는 클라이언트에서 늦게 올 수 있다 — 설정 통지를 계속 받고, 이미 있으면 바로 붙는다
	if (UWorld* MutableWorld = GetWorld())
	{
		GameStateSetHandle = MutableWorld->GameStateSetEvent.AddUObject(this, &ThisClass::HandleGameStateSet);
		if (AGameStateBase* GameState = MutableWorld->GetGameState())
		{
			HandleGameStateSet(GameState);
		}
	}
}

void UAstralCombatHUDWidget::NativeDestruct()
{
	if (APlayerController* PC = GetOwningPlayer())
	{
		PC->OnPossessedPawnChanged.RemoveDynamic(this, &ThisClass::HandlePossessedPawnChanged);
	}
	if (UWorld* World = GetWorld())
	{
		World->GameStateSetEvent.Remove(GameStateSetHandle);
		World->GetTimerManager().ClearTimer(BurstBannerTimer);
		World->GetTimerManager().ClearTimer(UltBlockedTimer);
	}
	GameStateSetHandle.Reset();
	UnbindAbilitySystem();
	UnbindChainBurst();
	WatchedPawn.Reset();

	Super::NativeDestruct();
}

void UAstralCombatHUDWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	// 남은 시간은 상태가 아니라 서버 시간에서 계산한 값이다 — 도는 동안만 매 프레임 다시 그린다
	if (bChainTimerRunning)
	{
		if (const UAstralChainBurstComponent* Chain = BoundChain.Get())
		{
			SetChainRemaining(Chain->GetRemainingSeconds());
		}
	}
}

// ─── 연결 ───

void UAstralCombatHUDWidget::HandlePossessedPawnChanged(APawn* OldPawn, APawn* NewPawn)
{
	WatchedPawn = NewPawn;

	// ASC 는 PlayerState 에 있어 폰이 바뀌어도 같은 것이다 — 폰이 아바타가 되는 순간을 기다렸다가 붙는다(이미 됐으면 바로 불린다)
	if (UAstralPawnExtensionComponent* PawnExtension = UAstralPawnExtensionComponent::FindPawnExtensionComponent(NewPawn))
	{
		PawnExtension->OnAbilitySystemInitialized_RegisterAndCall(FSimpleMulticastDelegate::FDelegate::CreateUObject(this, &ThisClass::HandleAbilitySystemInitialized));
	}
}

void UAstralCombatHUDWidget::HandleAbilitySystemInitialized()
{
	const UAstralPawnExtensionComponent* PawnExtension = UAstralPawnExtensionComponent::FindPawnExtensionComponent(WatchedPawn.Get());
	BindAbilitySystem(PawnExtension ? PawnExtension->GetAstralAbilitySystemComponent() : nullptr);
}

void UAstralCombatHUDWidget::BindAbilitySystem(UAbilitySystemComponent* ASC)
{
	if (!ASC || ASC == BoundASC.Get())
	{
		RefreshUltGauge();
		return;
	}

	UnbindAbilitySystem();
	BoundASC = ASC;
	UltGaugeChangedHandle = ASC->GetGameplayAttributeValueChangeDelegate(UAstralHeroResourceSet::GetUltGaugeAttribute()).AddUObject(this, &ThisClass::HandleUltAttributeChanged);
	MaxUltGaugeChangedHandle = ASC->GetGameplayAttributeValueChangeDelegate(UAstralHeroResourceSet::GetMaxUltGaugeAttribute()).AddUObject(this, &ThisClass::HandleUltAttributeChanged);
	AbilityFailedHandle = ASC->AbilityFailedCallbacks.AddUObject(this, &ThisClass::HandleAbilityFailed);
	RefreshUltGauge();
}

void UAstralCombatHUDWidget::UnbindAbilitySystem()
{
	if (UAbilitySystemComponent* ASC = BoundASC.Get())
	{
		ASC->GetGameplayAttributeValueChangeDelegate(UAstralHeroResourceSet::GetUltGaugeAttribute()).Remove(UltGaugeChangedHandle);
		ASC->GetGameplayAttributeValueChangeDelegate(UAstralHeroResourceSet::GetMaxUltGaugeAttribute()).Remove(MaxUltGaugeChangedHandle);
		ASC->AbilityFailedCallbacks.Remove(AbilityFailedHandle);
	}
	UltGaugeChangedHandle.Reset();
	MaxUltGaugeChangedHandle.Reset();
	AbilityFailedHandle.Reset();
	BoundASC.Reset();
}

void UAstralCombatHUDWidget::HandleGameStateSet(AGameStateBase* GameState)
{
	BindChainBurst(GameState ? GameState->FindComponentByClass<UAstralChainBurstComponent>() : nullptr);
}

void UAstralCombatHUDWidget::BindChainBurst(UAstralChainBurstComponent* Chain)
{
	if (Chain != BoundChain.Get())
	{
		UnbindChainBurst();
		BoundChain = Chain;
		if (Chain)
		{
			ChainStateChangedHandle = Chain->OnChainStateChanged.AddUObject(this, &ThisClass::HandleChainStateChanged);
		}
	}
	// 붙은 순간의 상태를 그린다 — 지난 버스트의 배너는 띄우지 않는다(번호 변화를 본 것이 아니다)
	ApplyChainState(Chain ? Chain->GetChainState() : FAstralChainState());
}

void UAstralCombatHUDWidget::UnbindChainBurst()
{
	if (UAstralChainBurstComponent* Chain = BoundChain.Get())
	{
		Chain->OnChainStateChanged.Remove(ChainStateChangedHandle);
	}
	ChainStateChangedHandle.Reset();
	BoundChain.Reset();
	bChainTimerRunning = false;
}

// ─── 원천 → 화면 ───

void UAstralCombatHUDWidget::HandleUltAttributeChanged(const FOnAttributeChangeData& Data)
{
	RefreshUltGauge();
}

void UAstralCombatHUDWidget::RefreshUltGauge()
{
	// 둘 다 ASC 의 지금 값으로 — 속성 세트는 AbilitySet 이 주므로 클라이언트에는 늦게 올 수 있고, 최대치가 기본값 그대로면 변화 통지가 없다
	const UAbilitySystemComponent* ASC = BoundASC.Get();
	float Gauge = 0.f;
	float MaxGauge = 0.f;
	if (ASC && ASC->HasAttributeSetForAttribute(UAstralHeroResourceSet::GetUltGaugeAttribute()))
	{
		Gauge = ASC->GetNumericAttribute(UAstralHeroResourceSet::GetUltGaugeAttribute());
		MaxGauge = ASC->GetNumericAttribute(UAstralHeroResourceSet::GetMaxUltGaugeAttribute());
	}
	const bool bValid = MaxGauge > 0.f;
	SetUltGauge(bValid ? Gauge / MaxGauge : 0.f);
	SetUltReadyVisible(bValid && Gauge >= MaxGauge - KINDA_SMALL_NUMBER);
}

void UAstralCombatHUDWidget::HandleAbilityFailed(const UGameplayAbility* Ability, const FGameplayTagContainer& FailureTags)
{
	// 엔진은 차단 사유를 ini(ActivateFailTagsBlockedTag)가 있을 때만 넣는다 — 대신 실패한 순간 내 차단 태그를 본다(설계 §4, C 결정 3)
	const UAbilitySystemComponent* ASC = BoundASC.Get();
	if (!ASC || !Ability || !Ability->GetAssetTags().HasTag(AstralGameplayTags::Ability_Ult))
	{
		return;
	}
	if (!ASC->HasMatchingGameplayTag(AstralGameplayTags::State_Ult_Blocked))
	{
		return;   // 게이지 부족 등 — 조용히
	}
	SetUltBlockedVisible(true);
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().SetTimer(UltBlockedTimer, this, &ThisClass::HideUltBlocked, UltBlockedSeconds, /*bLoop*/ false);
	}
}

void UAstralCombatHUDWidget::HideUltBlocked()
{
	SetUltBlockedVisible(false);
}

void UAstralCombatHUDWidget::HandleChainStateChanged(const FAstralChainState& NewState, const FAstralChainState& OldState)
{
	ApplyChainState(NewState);

	// 버스트 통지는 단계가 아니라 마지막 버스트 번호의 변화다 — 클라이언트는 '열림 → 없음' 과 번호 변화를 한 번에 받는다
	if (NewState.LastBurstChainId > 0 && NewState.LastBurstChainId != OldState.LastBurstChainId)
	{
		ShowBurstBanner(NewState.LastBurstCount);
	}
}

void UAstralCombatHUDWidget::ApplyChainState(const FAstralChainState& State)
{
	const UAstralChainBurstComponent* Chain = BoundChain.Get();
	const bool bOpen = Chain && State.Phase == EAstralChainPhase::Open;
	SetChainPanelVisible(bOpen);
	bChainTimerRunning = bOpen && !State.bTimerPaused;
	if (bOpen)
	{
		SetChainCount(FText::FromString(FString::Printf(TEXT("%d/%d"), State.ParticipantIds.Num(), Chain->GetMaxParticipants())));
		SetChainRemaining(Chain->GetRemainingSeconds());
	}
}

void UAstralCombatHUDWidget::ShowBurstBanner(int32 Count)
{
	SetBurstCount(Count);
	SetBurstBannerVisible(true);
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().SetTimer(BurstBannerTimer, this, &ThisClass::HideBurstBanner, BurstBannerSeconds, /*bLoop*/ false);
	}
}

void UAstralCombatHUDWidget::HideBurstBanner()
{
	SetBurstBannerVisible(false);
}
