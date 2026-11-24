#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "Player/AstralPlayerLoadout.h"
#include "AstralPlayerController.generated.h"

class UAstralAbilitySystemComponent;
class UAstralCombatHUDWidget;
class UAstralStatusHUDWidget;
class AAstralPlayerState;
/**
 *
 */
UCLASS()
class ASTRALBREAK_API AAstralPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AAstralPlayerController(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	UFUNCTION(BlueprintCallable, Category = "Astral|PlayerController")
	AAstralPlayerState* GetAstralPlayerState() const;

	UFUNCTION(BlueprintCallable, Category = "Astral|PlayerController")
	UAstralAbilitySystemComponent* GetAstralAbilitySystemComponent() const;

	/** 전투 HUD — 로컬 컨트롤러만 갖는다(없으면 null). 자동 시험이 읽는다 */
	UAstralCombatHUDWidget* GetCombatHUDWidget() const;

	/** 내 상태 · 동료 HUD — 로컬 컨트롤러만 갖는다(없으면 null) */
	UAstralStatusHUDWidget* GetStatusHUDWidget() const;

	/**
	 * 클라→서버 로드아웃 발신 — 3단 소스의 1단(PS.Loadout)을 채운다 (캐시 미스/타 서버 도착 시 복원 경로).
	 * 서버는 ID 해석 검증 후 PlayerState 반영 + PartySubsystem 캐시
	 */
	UFUNCTION(Server, Reliable)
	void ServerSetLoadout(FAstralPlayerLoadout InLoadout);

	UFUNCTION(Server, Reliable)
	void ServerSetReady(bool bInReady);

	/** 방장만 — 목적지 선택. 게임모드 허용 목록(RaidMapNames)에 있는 이름만 받는다 */
	UFUNCTION(Server, Reliable)
	void ServerSelectRaid(const FString& MapName);

	/** 방장만 — 전원 준비 확인 후 ServerTravel */
	UFUNCTION(Server, Reliable)
	void ServerStartRaid();

	/** 방장만 — 허브 복귀 */
	UFUNCTION(Server, Reliable)
	void ServerReturnToHub();

	/*
	 * 로비 디버그 exec — 정식 UI는 M6. 예: `SetLoadout Vesper WD_Sickle1 WD_Rifle1`
	 */

	/** 캐릭터+무기 선택 (타입 접두 자동 보완). 빈 인자는 생략 취급 */
	UFUNCTION(Exec)
	void SetLoadout(const FString& CharacterName, const FString& Weapon1, const FString& Weapon2);

	UFUNCTION(Exec)
	void SetReady(int32 bReady = 1);

	UFUNCTION(Exec)
	void SelectRaid(const FString& MapName);

	UFUNCTION(Exec)
	void StartRaid();

	UFUNCTION(Exec)
	void ReturnToHub();

	/** 디버그 위젯 켜기 / 끄기 — 왼쪽 위 글자가 HUD(내 상태 · 동료)를 덮는다 */
	UFUNCTION(Exec)
	void ToggleDebugWidget();
	
	//~AActor interface
	virtual void PreInitializeComponents() override;
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	//~End of AActor interface
	
	//~APlayerController interface
	virtual void PostProcessInput(const float DeltaTime, const bool bGamePaused) override;
	//~End of APlayerController interface

protected:
	virtual void BeginPlayingState() override;

	/**
	 * 방장 판정 — AAstralGameState::GetPartyLeader()(PlayerId 최소)가 내 PlayerState 인가.
	 * 넷 모드 분기 없음: 리슨에선 호스트, Dedicated 에선 먼저 들어온 클라이언트. 방장 규칙이 바뀌면 이 한 곳을 고친다
	 */
	bool IsPartyLeader() const;

private:

	/*
	 * HUD — 처음 생기는 플레이어용 화면 (설계 Docs/Design/m4-ult-chain.md §5 · §6 'C 구현 결과')
	 */

	/**
	 * 전투 HUD 의 WBP. 기본값은 promote_widget 으로 승격한 /Game/UI/HUD/CombatHUD/WBP_CombatHUD — BP_PlayerController 는 값을 저장하지 않아 이것을 물려받는다.
	 * 다른 그림으로 바꾸려면 BP 에서 덮어쓴다. 비우면 HUD 를 만들지 않는다
	 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|HUD")
	TSoftClassPtr<UAstralCombatHUDWidget> CombatHUDWidgetClass;

	UPROPERTY()
	TObjectPtr<UAstralCombatHUDWidget> CombatHUDWidget;

	/** 내 상태 · 동료 HUD 의 WBP — 전투 HUD 와 같은 규칙. 화면을 나눈 까닭은 설계 Docs/Design/ui-autogen-pipeline.md §11 '메인 HUD 설계' 결정 2 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|HUD")
	TSoftClassPtr<UAstralStatusHUDWidget> StatusHUDWidgetClass;

	UPROPERTY()
	TObjectPtr<UAstralStatusHUDWidget> StatusHUDWidget;

	/*
	 * Debug Members
	 */
	
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Debug")
	TSubclassOf<class UAstralDebugWidget> DebugWidgetClass;

	UPROPERTY()
	TObjectPtr<class UAstralDebugWidget> DebugWidget;
};
