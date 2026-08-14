#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "Player/AstralPlayerLoadout.h"
#include "AstralPlayerController.generated.h"

class UAstralAbilitySystemComponent;
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

	/**
	 * 클라→서버 로드아웃 발신 — 3단 소스의 1단(PS.Loadout)을 채운다 (캐시 미스/타 서버 도착 시 복원 경로).
	 * 서버는 ID 해석 검증 후 PlayerState 반영 + PartySubsystem 캐시
	 */
	UFUNCTION(Server, Reliable)
	void ServerSetLoadout(FAstralPlayerLoadout InLoadout);

	UFUNCTION(Server, Reliable)
	void ServerSetReady(bool bInReady);

	/** 방장(리슨 호스트)만 — 목적지 선택 */
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

	/** 방장 판정 — MVP: 리슨 호스트(서버에서 로컬인 PC). TODO: 데디 전환 시 교체 지점 */
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
