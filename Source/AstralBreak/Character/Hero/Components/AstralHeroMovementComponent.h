#pragma once

#include "CoreMinimal.h"
#include "GameplayTagContainer.h"
#include "Character/Components/AstralCharacterMovementComponent.h"
#include "Combat/AstralInputFacingTypes.h"
#include "AstralHeroMovementComponent.generated.h"

/**
 * 공용 이동 기능(GroundInfo·ASC 결합 등)은 베이스 UAstralCharacterMovementComponent에 있고,
 * 여기엔 Hero 고유 이동(스프린트/회피 튜닝 등)을 추가
 */
UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralHeroMovementComponent : public UAstralCharacterMovementComponent
{
	GENERATED_BODY()

public:
	UAstralHeroMovementComponent(const FObjectInitializer& ObjectInitializer);

	//~UCharacterMovementComponent
	virtual float GetMaxSpeed() const override;

	/** 압축 플래그 예측 — FAstralSavedMove_Hero를 만드는 클라 예측 데이터 (표준 lazy 생성) */
	virtual FNetworkPredictionData_Client* GetPredictionData_Client() const override;

	/** 서버가 원격 클라의 의도를 수신하는 지점 — 신뢰 대상이 아니다 (승인은 GetMaxSpeed의 게이트가 판단) */
	virtual void UpdateFromCompressedFlags(uint8 Flags) override;

	/** 입력 회전 샘플의 수명 창 — 설치된 샘플이 없으면(호스트·Standalone: SavedMove 경로가 없다) 라이브 입력으로 만들고, 이동 뒤 항상 해제 */
	virtual void PerformMovement(float DeltaSeconds) override;
	//~End UCharacterMovementComponent

	/** 현재 실행 중인 move의 샘플. PerformMovement 밖(시뮬 프록시 SimulateMovement 등)에서는 false — 보정 없음 */
	bool GetInputFacingSampleForCurrentMove(FAstralInputFacingSample& OutSample) const;

	/** move 시작 전에 설치 — SetMoveFor(예측)·PrepMoveFor(재실행)·ServerMove(서버)가 호출. PerformMovement가 소비 후 해제한다 */
	void InstallCurrentMoveInputFacing(const FAstralInputFacingSample& Sample);
	void ClearCurrentMoveInputFacing();

	/**
	 * 라이브 샘플 — 폰이 이번 틱 소비한 이동 입력(AddMovementInput과 같은 카메라 기준 월드 벡터, 무입력이면 0) + 현재 Yaw + 로컬 락온 억제.
	 * 부호는 여기서 한 번 고른다 (소유 클라·호스트). 서버·재실행은 고르지 않는다
	 */
	FAstralInputFacingSample MakeLiveInputFacingSample() const;

	/** Sprint GA에서 호출 — 의도만 세팅한다. SavedMove 리플레이 복원도 이 경로를 쓴다 */
	void SetSprinting(bool bNewSprinting) { bWantsToSprint = bNewSprinting; }

	/** 원시 의도 — SavedMove 직렬화 대상. "지금 질주 중인가"는 IsSprinting()을 쓸 것 */
	bool WantsToSprint() const { return bWantsToSprint; }

	/** GAS가 질주를 승인했고 지상인가 */
	bool CanActuallySprint() const { return bSprintAuthorized && IsMovingOnGround(); }

	/** 승인 캐시 단독 값 */
	bool IsSprintAuthorized() const { return bSprintAuthorized; }

	/** 실제 질주 상태 (의도 + 승인 + 지상)  */
	UFUNCTION(BlueprintPure, Category = "Astral|HeroMovement")
	bool IsSprinting() const { return bWantsToSprint && CanActuallySprint(); }

protected:
	//~UAstralCharacterMovementComponent
	virtual void OnAbilitySystemBound() override;
	virtual void OnAbilitySystemUnbound() override;
	//~End UAstralCharacterMovementComponent

	/** State.Movement.Sprinting 카운트 변경 — 승인 캐시 갱신 */
	void HandleSprintTagChanged(const FGameplayTag Tag, int32 NewCount);

	/** 로컬 락온 선택 중인가 — 샘플 억제 플래그의 원천 (로컬 제어 폰만. 서버는 패킷 샘플의 플래그를 쓴다) */
	bool IsLocalLockOnActive() const;

protected:

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Astral|HeroMovement", Meta = (ClampMin = "1.0"))
	float SprintSpeedMultiplier = 800.0f / 600.0f;

	/** 플레이어 의도 — 클라 발신(압축 플래그). 서버는 이 값 단독으로 속도를 인정하지 않는다 */
	bool bWantsToSprint = false;

	/** GAS 승인 캐시, ASC 미결합 폰은 질주 불가 */
	bool bSprintAuthorized = false;

	FDelegateHandle SprintTagChangedHandle;

private:
	/** 현재 move의 입력 회전 샘플 — PerformMovement 안에서만 유효 */
	FAstralInputFacingSample CurrentMoveInputFacing;
	bool bHasCurrentMoveInputFacing = false;
};

class FAstralSavedMove_Hero : public FSavedMove_Character
{
	using Super = FSavedMove_Character;

public:
	FAstralSavedMove_Hero();

	virtual void Clear() override;

	virtual uint8 GetCompressedFlags() const override;

	/** 현재 MC 상태를 SavedMove에 저장 (호출 시점: 클라가 서버로 이동 데이터 전송 전) */
	virtual void SetMoveFor(ACharacter* C, float InDeltaTime, FVector const& NewAccel, FNetworkPredictionData_Client_Character& ClientData) override;

	/** SavedMove 데이터를 MC로 복원 (호출 시점: 서버 보정 수신 후 리플레이 직전) */
	virtual void PrepMoveFor(ACharacter* C) override;

	/** PostUpdate_Record에서 이 move가 실제로 쓴 폰 충돌 정책을 기록 */
	virtual void PostUpdate(ACharacter* C, EPostUpdateMode PostUpdateMode) override;

	virtual bool CanCombineWith(const FSavedMovePtr& NewMove, ACharacter* InCharacter, float MaxDelta) const override;

protected:
	static UAstralHeroMovementComponent* GetHeroMovementComponent(ACharacter* C);

	/** move 시점의 스프린트 의도 */
	uint8 bSavedWantsToSprint : 1;

	/** 이 move가 쓴 폰 충돌 정책 — 리플레이 복원 전용 로컬 필드 */
	EAstralRootMotionPawnCollisionPolicy SavedPawnCollisionPolicy;
};

class FAstralNetworkPredictionData_Client_Hero : public FNetworkPredictionData_Client_Character
{
	using Super = FNetworkPredictionData_Client_Character;

public:
	explicit FAstralNetworkPredictionData_Client_Hero(const UCharacterMovementComponent& ClientMovement);

	/** 커스텀 SavedMove(FAstralSavedMove_Hero) 생성 */
	virtual FSavedMovePtr AllocateNewMove() override;
};

