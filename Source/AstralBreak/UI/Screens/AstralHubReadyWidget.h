// uigen 이 처음 한 번 만든 스텁 — 이제 사람 소유다. uigen 은 이 파일을 다시 쓰지 않는다(설계 Docs/Design/ui-autogen-pipeline.md §3-3).
// 게임 연결(GAS 속성 변화 · 컴포넌트 통지 → 생성 베이스의 setter 호출)은 여기에 쓴다.

#pragma once

#include "CoreMinimal.h"
#include "GameModes/AstralLobbyRules.h"
#include "UI/Screens/AutoGen/AstralHubReadyViewBase.h"
#include "AstralHubReadyWidget.generated.h"

class AAstralGameState;
class AAstralPlayerController;
class AAstralPlayerState;
class AGameStateBase;
class APlayerState;

/**
 * HubReady 화면 위젯 — 허브의 '준비 · 목적지 · 출정' 요청 화면(설계 Docs/Design/ui-autogen-pipeline.md §11 'Phase 3 설계' ① · ③, 'Phase 3-4 결과').
 * WBP 의 부모 클래스. 바인딩 위젯과 setter 는 생성 베이스 UAstralHubReadyViewBase 에 있다.
 *
 *   원천 → 화면   명단(AAstralGameState::OnPlayerRosterChanged) · 준비(AAstralPlayerState::OnReadyChanged) · 목적지(AAstralHubGameState::OnSelectedRaidChanged)
 *                 통지가 오면 스냅숏(AAstralPlayerController::MakeLobbySnapshot)을 만들어 서버와 같은 규칙(AstralLobby::Check…)으로 버튼을 켜고 끈다. 폴링 없음
 *   화면 → 원천   버튼은 요청만 보낸다(ServerSetReady · ServerSelectRaid · ServerStartRaid). 모양은 값이 바뀐 통지로만 바뀐다
 *   거절          ClientLobbyRequestDenied → 이유 한 줄에 거절 글 DeniedReasonSeconds 초 → 지금 상태의 까닭으로
 *   여닫기        허브 GameState 의 ContextScreens(UI.Action.HubReady, 게임 입력)로 열린다. 같은 키(Menu 묶음) · 뒤로(UI.Action.Back)에 닫힌다
 *
 * 에디터 렌더(WidgetMcp render_widget)에서는 아무것도 붙지 않는다 — spec 상태 · 덮어쓰기 그대로 그려야 한다(StatusHUD 와 같은 까닭)
 */
UCLASS()
class ASTRALBREAK_API UAstralHubReadyWidget : public UAstralHubReadyViewBase
{
	GENERATED_BODY()

public:
	UAstralHubReadyWidget(const FObjectInitializer& ObjectInitializer);

	/** 목적지 버튼이 가리키는 맵 — 고른 것이 목록에 있으면 그것, 아니면 목록의 첫째. 없으면 빈 문자열 */
	const FString& GetShownDestination() const { return ShownDestination; }

	/** 서버 거절 글을 띄우고 있는가 */
	bool IsShowingDeniedReason() const { return bShowingDeniedReason; }

	/** 이유 한 줄에 서버 거절 글이 머무는 시간(초) */
	float GetDeniedReasonSeconds() const { return DeniedReasonSeconds; }

protected:
	//~UUserWidget interface
	virtual void NativeOnInitialized() override;
	virtual void NativeConstruct() override;
	virtual void NativeDestruct() override;
	//~End of UUserWidget interface

	//~UCommonActivatableWidget interface
	virtual UWidget* NativeGetDesiredFocusTarget() const override;
	//~End of UCommonActivatableWidget interface

	//~UAstralHubReadyViewBase interface
	virtual void HandleReadyClicked() override;
	virtual void HandleDestinationClicked() override;
	virtual void HandleLaunchClicked() override;
	//~End of UAstralHubReadyViewBase interface

	/** 서버 거절 글이 이유 한 줄에 머무는 시간(초) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|HubReady", meta = (ClampMin = "0.1"))
	float DeniedReasonSeconds = 3.f;

private:
	void HandleGameStateSet(AGameStateBase* GameState);
	void HandleRosterChanged();
	void HandleLobbyValueChanged();
	void HandleRequestDenied(EAstralLobbyDenial Reason);
	void HandleDeniedReasonExpired();
	void HandleHubReadyAction();

	void BindMembers(const TArray<APlayerState*>& States);
	void UnbindMembers();
	void UnbindAll();

	/** 원천 값으로 화면 전체를 다시 정한다 — 네 줄 · 버튼 셋(켜짐 · 선택 · 목적지 글자) · 이유 한 줄 */
	void Refresh();

	UAstralHubMemberRowWidget* GetRow(int32 RowIndex) const;
	AAstralPlayerController* GetAstralPlayerController() const;
	bool IsLocalPlayerReady() const;

	static constexpr int32 NumRows = 4;

	TWeakObjectPtr<AAstralGameState> BoundGameState;
	TWeakObjectPtr<AAstralPlayerController> BoundController;
	TArray<TPair<TWeakObjectPtr<AAstralPlayerState>, FDelegateHandle>> BoundMembers;

	FDelegateHandle GameStateSetHandle;
	FDelegateHandle RosterChangedHandle;
	FDelegateHandle SelectedRaidChangedHandle;
	FDelegateHandle RequestDeniedHandle;

	FString ShownDestination;
	FTimerHandle DeniedReasonTimer;
	bool bShowingDeniedReason = false;
};
