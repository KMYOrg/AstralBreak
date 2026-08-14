#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "GameFramework/PlayerState.h"
#include "GenericTeamAgentInterface.h"
#include "Player/AstralPlayerLoadout.h"
#include "AstralPlayerState.generated.h"

class UAstralCombatSet;
class UAstralHealthSet;
class UAstralAbilitySystemComponent;
class UAstralPawnData;
class AAstralPlayerController;
/**
 *
 */
UCLASS()
class ASTRALBREAK_API AAstralPlayerState : public APlayerState, public IAbilitySystemInterface, public IGenericTeamAgentInterface
{
	GENERATED_BODY()
	
public:
	AAstralPlayerState(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
	
	virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
	
	UFUNCTION(BlueprintCallable, Category = "Lyra|PlayerState")
	AAstralPlayerController* GetAstralPlayerController() const;

	UFUNCTION(BlueprintCallable, Category = "Lyra|PlayerState")
	UAstralAbilitySystemComponent* GetAstralAbilitySystemComponent() const { return AbilitySystemComponent; }
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;
	
	template <class T>
	const T* GetPawnData() const { return Cast<T>(PawnData); }

	void SetPawnData(const UAstralPawnData* InPawnData);

	/** 서버 — 로드아웃 반영 (검증은 PlayerController RPC에서 완료된 상태). OnLoadoutChanged로 전파 */
	void SetLoadout(const FAstralPlayerLoadout& InLoadout);

	/** 서버 — 준비 상태 (로비) */
	void SetReady(bool bInReady);

	const FAstralPlayerLoadout& GetLoadout() const { return Loadout; }
	bool IsReady() const { return bIsReady; }

	/**
	 * 로드아웃 변경 통지 (서버 SetLoadout + 클라 OnRep — 전 머신)
	 */
	FSimpleMulticastDelegate OnLoadoutChanged;
	
	//~AActor interface
	virtual void PreInitializeComponents() override;
	virtual void PostInitializeComponents() override;
	//~End of AActor interface
	
	//~APlayerState interface
	virtual void Reset() override;
	virtual void ClientInitialize(AController* C) override;
	virtual void CopyProperties(APlayerState* PlayerState) override;
	//~End of APlayerState interface

	//~IGenericTeamAgentInterface (플레이어는 전원 팀 0 — 4인 협동)
	virtual void SetGenericTeamId(const FGenericTeamId& NewTeamID) override;
	virtual FGenericTeamId GetGenericTeamId() const override { return MyTeamID; }
	//~End of IGenericTeamAgentInterface

protected:

	UFUNCTION()
	void OnRep_Loadout();

private:
	
	// TODO: M1 마일스톤
	//void OnExperienceLoaded(const UAstralExperienceDefinition* CurrentExperience);

protected:

	// RepNotify 없음 — 클라 InitState 진행은 PawnExtensionComponent 자체의 PawnData 복제가 담당
	UPROPERTY(Replicated)
	TObjectPtr<const UAstralPawnData> PawnData;

	/** 로비 선택 — 남의 선택이 보여야 하므로 복제 (구조체 통째 = 원자 복제) */
	UPROPERTY(ReplicatedUsing = OnRep_Loadout)
	FAstralPlayerLoadout Loadout;

	/** 로비 준비 상태 */
	UPROPERTY(Replicated)
	bool bIsReady = false;

private:

	UPROPERTY(VisibleAnywhere, Category = "Lyra|PlayerState")
	TObjectPtr<UAstralAbilitySystemComponent> AbilitySystemComponent;

	UPROPERTY()
	TObjectPtr<const UAstralHealthSet> HealthSet;

	UPROPERTY()
	TObjectPtr<const UAstralCombatSet> CombatSet;

	// FGenericTeamId는 USTRUCT라 직접 복제 가능 (Lyra 동일 패턴)
	UPROPERTY(Replicated)
	FGenericTeamId MyTeamID = FGenericTeamId(0);
};
