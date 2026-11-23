// uigen 이 처음 한 번 만든 스텁 — 이제 사람 소유다. uigen 은 이 파일을 다시 쓰지 않는다(설계 Docs/Design/ui-autogen-pipeline.md §3-3).
// 게임 연결(GAS 속성 변화 · 컴포넌트 통지 → 생성 베이스의 setter 호출)은 여기에 쓴다.

#pragma once

#include "CoreMinimal.h"
#include "UI/HUD/AutoGen/AstralCombatHUDViewBase.h"
#include "AstralCombatHUDWidget.generated.h"

class AGameStateBase;
class APawn;
class UAbilitySystemComponent;
class UAstralChainBurstComponent;
class UGameplayAbility;
struct FAstralChainState;
struct FGameplayTagContainer;
struct FOnAttributeChangeData;

/**
 * CombatHUD 화면 위젯 — WBP 의 부모 클래스. 바인딩 위젯과 setter 는 생성 베이스 UAstralCombatHUDViewBase 에 있다.
 * M4 단위 C (설계 Docs/Design/m4-ult-chain.md §5 · §6 'C 구현 결과'). 화면은 상태를 갖지 않는다 — 전부 원천의 통지를 받아 setter 로 옮긴다.
 *
 *   오의 게이지     내 ASC 의 UltGauge · MaxUltGauge 값 변화 통지 → 비율, 가득이면 강조
 *   체인 패널       레이드 GameState 의 체인 컴포넌트 OnChainStateChanged → 열려 있을 때만 보임, 참가 N/최대
 *   남은 시간       열려 있고 돌고 있을 때만 틱마다 GetRemainingSeconds()(서버 시간에서 계산). 멈추면 그 값에서 멈춘다
 *   버스트 배너     LastBurstChainId 가 바뀌면 인원을 넣어 잠깐 띄운다 — 단계(Burst)는 한 틱이라 클라이언트가 못 볼 수 있다(§6 B 다듬기 6번)
 *   '오의 불가'     내 ASC 의 발동 실패 통지가 오의이고 그때 State.Ult.Blocked 가 있으면 잠깐 띄운다. 게이지 부족은 조용히 무시한다(§4)
 *
 * 연결 시점은 이벤트로 받는다(폴링 없음) — 클라이언트는 위젯이 만들어질 때 폰 · ASC · GameState 가 아직 없을 수 있다.
 *   폰    소유 컨트롤러의 OnPossessedPawnChanged (클라이언트는 OnRep_Pawn 에서도 나간다)
 *   ASC   그 폰의 PawnExtension OnAbilitySystemInitialized_RegisterAndCall
 *   체인  UWorld::GameStateSetEvent → GameState 의 체인 컴포넌트(없는 맵 = 허브면 패널은 계속 접힘)
 * 게임 월드에서 소유 플레이어가 있을 때만 동작한다 — 에디터 렌더(uigen 검증의 render_widget)는 spec 상태 · 덮어쓰기 그대로 그려야 해서 아무것도 안 한다.
 */
UCLASS()
class ASTRALBREAK_API UAstralCombatHUDWidget : public UAstralCombatHUDViewBase
{
	GENERATED_BODY()

public:
	/** 지금 연결된 원천 — 자동 시험이 연결이 끝났는지 본다 */
	UAbilitySystemComponent* GetBoundAbilitySystem() const { return BoundASC.Get(); }
	UAstralChainBurstComponent* GetBoundChainBurst() const { return BoundChain.Get(); }

protected:
	virtual void NativeConstruct() override;
	virtual void NativeDestruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;

	/** 버스트 배너를 띄워 두는 시간(초) — 잠정 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|HUD", meta = (ClampMin = "0.1"))
	float BurstBannerSeconds = 2.5f;

	/** '오의 불가' 를 띄워 두는 시간(초) — 잠정 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|HUD", meta = (ClampMin = "0.1"))
	float UltBlockedSeconds = 1.5f;

private:
	// ─── 연결 ───

	UFUNCTION()
	void HandlePossessedPawnChanged(APawn* OldPawn, APawn* NewPawn);

	/** 지켜보는 폰의 ASC 가 준비됐다(그 폰이 ASC 의 아바타가 됐다) */
	void HandleAbilitySystemInitialized();

	void BindAbilitySystem(UAbilitySystemComponent* ASC);
	void UnbindAbilitySystem();

	void HandleGameStateSet(AGameStateBase* GameState);
	void BindChainBurst(UAstralChainBurstComponent* Chain);
	void UnbindChainBurst();

	// ─── 원천 → 화면 ───

	void HandleUltAttributeChanged(const FOnAttributeChangeData& Data);
	void RefreshUltGauge();

	void HandleAbilityFailed(const UGameplayAbility* Ability, const FGameplayTagContainer& FailureTags);
	void HideUltBlocked();

	void HandleChainStateChanged(const FAstralChainState& NewState, const FAstralChainState& OldState);
	void ApplyChainState(const FAstralChainState& State);
	void ShowBurstBanner(int32 Count);
	void HideBurstBanner();

	TWeakObjectPtr<APawn> WatchedPawn;
	TWeakObjectPtr<UAbilitySystemComponent> BoundASC;
	TWeakObjectPtr<UAstralChainBurstComponent> BoundChain;

	FDelegateHandle UltGaugeChangedHandle;
	FDelegateHandle MaxUltGaugeChangedHandle;
	FDelegateHandle AbilityFailedHandle;
	FDelegateHandle ChainStateChangedHandle;
	FDelegateHandle GameStateSetHandle;

	/** 체인이 열려 있고 타이머가 돌고 있다 — 이때만 틱이 남은 시간을 다시 그린다 */
	bool bChainTimerRunning = false;

	FTimerHandle BurstBannerTimer;
	FTimerHandle UltBlockedTimer;
};
