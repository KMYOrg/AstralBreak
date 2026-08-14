#pragma once

#include "CoreMinimal.h"
#include "AbilitySystemInterface.h"
#include "GameFramework/Character.h"
#include "GameplayTagContainer.h"
#include "UObject/PrimaryAssetId.h"
#include "AstralCharacter.generated.h"

class UAstralAbilitySystemComponent;
class UAstralEquipmentManagerComponent;
class UAstralHealthComponent;
class UAstralPawnExtensionComponent;
class AAstralPlayerState;

/** 장비 복원에 실제 쓰인 소스 — 디버그 가시성용 (값 = "무엇을 썼는가", 우선순위 아님) */
UENUM()
enum class EAstralLoadoutSource : uint8
{
	None,
	PartyCache,
	PlayerState,
	PawnDataFallback,
};

UCLASS()
class ASTRALBREAK_API AAstralCharacter : public ACharacter, public IAbilitySystemInterface
{
	GENERATED_BODY()

public:
	AAstralCharacter(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	//~ IAbilitySystemInterface
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;
	//~ End IAbilitySystemInterface

	UFUNCTION(BlueprintCallable, Category = "Astral|Character")
	AAstralPlayerState* GetAstralPlayerState() const;

	UFUNCTION(BlueprintCallable, Category = "Astral|Character")
	UAstralAbilitySystemComponent* GetAstralAbilitySystemComponent() const;

	UFUNCTION(BlueprintPure, Category = "Astral|Character")
	UAstralHealthComponent* GetHealthComponent() const { return HealthComponent; }

	UFUNCTION(BlueprintPure, Category = "Astral|Character")
	UAstralEquipmentManagerComponent* GetEquipmentManagerComponent() const { return EquipmentManagerComponent; }

	/**
	 * 상태 = ASC 복제 루즈 태그(TagAndCountToAll — 오너·시뮬·후참가 전부 복제), 이 함수 외 쓰기 금지.
	 * 절대값 세팅이라 리스폰 시 ASC(PlayerState)에 잔존한 이전 폰의 태그도 자동 정정된다.
	 * 태그 갱신 직후 장비 부착 상태 갱신 통지 (비활성 스타일 장비는 홀스터/숨김)
	 */
	void SetCombatStyle(FGameplayTag NewStyle);

	/**
	 * 로드아웃 반영의 단일 진입점 ① 외형(전 머신) ② 장비(서버).
	 * 호출 지점: ASC 초기화(bReapply=false) · PS.OnLoadoutChanged(bReapply=true)
	 */
	void ApplyLoadout(bool bReapplyEquipment);

	/**
	 * 외형 갱신 (전 머신, 멱등) — PlayerState 로드아웃의 CharacterId → CharacterDefinition 메시/AnimBP 적용.
	 * ApplyLoadout 경유가 정경로. OnRep_PlayerState의 직접 호출은 "PS는 도착했으나 PawnData 복제 전"
	 * 창의 수 프레임 조기 표시용
	 */
	void RefreshAppearanceFromLoadout();

	/**
	 * 서버 — 장비 복원 (3단 소스: PlayerState.Loadout → PartySubsystem 캐시 → PawnData 폴백[Full 전용]).
	 * 장착 정책(GameState 소유)에 따름 — None=생략, VisualOnly=홀스터 표시만(부여 없음), Full=전부.
	 * bReapply: 늦게 도착한 로드아웃 반영 (동일 장착이면 no-op, 다르면 UnequipAll 후 재장착)
	 */
	void RestoreEquipmentFromLoadout(bool bReapply);

	/** 디버그 — 마지막 장비 복원 소스 */
	EAstralLoadoutSource GetLastLoadoutSource() const { return LastLoadoutSource; }

	/**
	 * 서버 — 스타일↔장비 정합. 현 스타일에 일치하는 장비가 없으면(선택적 로드아웃 — 한 무기만 장착 등)
	 * 장비가 있는 첫 스타일로 자동 전환. 장비 변이 지점(로드아웃 복원·교체) 직후 호출된다
	 */
	void EnsureCombatStyleMatchesEquipment();

	/** 디버그 — 콘솔에서 `DamageSelf 50`. 데미지 파이프라인(GE_Damage_Base)을 그대로 태워 사망/수급 경로 검증용 */
	UFUNCTION(Exec)
	void DamageSelf(float Amount = 25.0f);

	/** 디버그 — 콘솔에서 `ReviveSelf`. HP 전체 회복 + 사망 상태 리셋 (사망 재테스트용) */
	UFUNCTION(Exec)
	void ReviveSelf();

	/**
	 * 디버그 — 콘솔에서 `EquipWeapon WD_HSword_A` (타입 생략 시 AstralWeaponDefinition 가정).
	 * 기존 장비 전체 해제 후 교체 — 로비 없이 무기 변형(메쉬·사거리·스탯) 검증용
	 */
	UFUNCTION(Exec)
	void EquipWeapon(const FString& WeaponIdString);

protected:
	UFUNCTION(Server, Reliable)
	void ServerDamageSelf(float Amount);

	UFUNCTION(Server, Reliable)
	void ServerReviveSelf();

	UFUNCTION(Server, Reliable)
	void ServerEquipWeapon(FPrimaryAssetId WeaponId);

	virtual void OnAbilitySystemInitialized();
	virtual void OnAbilitySystemUninitialized();

	/** PS.OnLoadoutChanged 핸들러 — 준비된 폰에 대한 push 경로 (구독 시점 = 초기화 시점) */
	void HandleLoadoutChanged();

	/** 구독 해제 — ASC 해체·EndPlay 양쪽에서 안전 (멱등) */
	void UnbindLoadoutChanged();

	/** 사망 물리 반응 — 게임플레이 필수(콜리전/이동 정지)만 C++. 몽타주·래그돌 등 연출은 BP가 OnDeathStarted 구독 */
	UFUNCTION()
	virtual void HandleDeathStarted(AActor* OwningActor);

	/** 부활(디버그 ReviveSelf / 추후 M6 리스폰) — 콜리전/이동 복구 */
	UFUNCTION()
	virtual void HandleDeathReset(AActor* OwningActor);

protected:
	//~ AActor
	virtual void PreInitializeComponents() override;
	virtual void PostInitializeComponents() override;
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
	//~ End AActor

	//~ APawn
	virtual void PossessedBy(AController* NewController) override;
	virtual void UnPossessed() override;
	virtual void OnRep_Controller() override;
	virtual void OnRep_PlayerState() override;
	virtual void SetupPlayerInputComponent(UInputComponent* PlayerInputComponent) override;
	//~ End APawn


protected:
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Components", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralPawnExtensionComponent> PawnExtComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Components", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralHealthComponent> HealthComponent;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Astral|Components", Meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UAstralEquipmentManagerComponent> EquipmentManagerComponent;

	/** 디버그 — 마지막 장비 복원 소스 (서버 로컬) */
	EAstralLoadoutSource LastLoadoutSource = EAstralLoadoutSource::None;

	TWeakObjectPtr<AAstralPlayerState> BoundLoadoutPlayerState;

	FDelegateHandle LoadoutChangedHandle;
};
