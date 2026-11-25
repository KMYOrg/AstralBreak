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

	/** 전투 HUD — 화면의 주인(UAstralUISubsystem)에게 묻는다. 로컬이 아니거나 이 맵의 HUD 목록에 없으면 null. 자동 시험이 읽는다 */
	UAstralCombatHUDWidget* GetCombatHUDWidget() const;

	/** 내 상태 · 동료 HUD — 위와 같다 */
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
	 * Debug Members
	 */
	
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Debug")
	TSubclassOf<class UAstralDebugWidget> DebugWidgetClass;

	UPROPERTY()
	TObjectPtr<class UAstralDebugWidget> DebugWidget;
};
