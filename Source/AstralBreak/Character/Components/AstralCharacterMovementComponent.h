#pragma once

#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameplayEffectTypes.h"
#include "AstralCharacterMovementComponent.generated.h"

class UAstralAbilitySystemComponent;
class UAnimNotifyState;

/**
 * 루트모션 중 폰과 blocking hit이 났을 때 정책
 */
UENUM()
enum class EAstralRootMotionPawnCollisionPolicy : uint8
{
	/** 기존 UCharacterMovementComponent 동작 — 막히고 표면을 따라 슬라이드 */
	Normal,
	/** 적대 Pawn blocking hit 이후 남은 이동량을 소비하지 않고 정지 */
	StopOnHit,
};

/** 정책 출처 — 노티파이 인스턴스 × 몽타주 인스턴스. 콤보 스테이지 교체 시 구 몽타주의 지각 End가 새 밴드를 지우지 않도록 InstanceID로 키를 잡는다 */
struct FAstralPawnCollisionPolicySource
{
	TObjectKey<const UAnimNotifyState> NotifyState;
	int32 MontageInstanceID = INDEX_NONE;

	bool operator==(const FAstralPawnCollisionPolicySource& Other) const
	{
		return NotifyState == Other.NotifyState && MontageInstanceID == Other.MontageInstanceID;
	}
};

struct FAstralPawnCollisionPolicyOverride
{
	FAstralPawnCollisionPolicySource Source;
	EAstralRootMotionPawnCollisionPolicy Policy = EAstralRootMotionPawnCollisionPolicy::Normal;
	/** 유효 정책 = 남아 있는 항목 중 가장 최근 Begin. 단순 스택은 교차 구간(A Begin → B Begin → A End)에서 남의 것을 지운다 */
	uint32 BeginOrder = 0;
};

USTRUCT(BlueprintType)
struct FAstralCharacterGroundInfo
{
	GENERATED_BODY()

	FAstralCharacterGroundInfo()
		: LastUpdateFrame(0)
		, GroundDistance(0.0f)
	{}

	uint64 LastUpdateFrame;

	UPROPERTY(BlueprintReadOnly)
	FHitResult GroundHitResult;

	UPROPERTY(BlueprintReadOnly)
	float GroundDistance;
};

UCLASS(ClassGroup=(Custom), meta=(BlueprintSpawnableComponent))
class ASTRALBREAK_API UAstralCharacterMovementComponent : public UCharacterMovementComponent
{
	GENERATED_BODY()

public:
	UAstralCharacterMovementComponent(const FObjectInitializer& ObjectInitializer);

	/** 프레임당 1회 캐싱되는 발밑 지면 정보 반환 (Game Thread 전용 — 내부에서 World trace 수행) */
	UFUNCTION(BlueprintCallable, Category = "Astral|CharacterMovement")
	const FAstralCharacterGroundInfo& GetGroundInfo();

	/** 모드별 최대 속도 × MoveSpeedMultiplier — 슬로우/가속이 걷기·질주(파생에서 승계) 전부에 일괄 적용 */
	virtual float GetMaxSpeed() const override;

	// 폰 충돌 정책 — 저작 경로는 NotifyState, 리플레이 경로는 SavedMove

	/** NotifyState Begin — 같은 source가 다시 오면 중복 없이 갱신. 시뮬 프록시는 정책을 소비하지 않으므로 무시 */
	void PushOrUpdatePawnCollisionPolicy(const FAstralPawnCollisionPolicySource& Source, EAstralRootMotionPawnCollisionPolicy Policy);

	/** NotifyState End — 자기 source만 제거 */
	void RemovePawnCollisionPolicy(const FAstralPawnCollisionPolicySource& Source);

	/** 유효 정책 — 죽은 MontageInstanceID 항목은 선택에서 제외(const 필터, 제거는 하지 않는다) */
	EAstralRootMotionPawnCollisionPolicy GetAuthoredPawnCollisionPolicy() const;

	/** 리플레이 전용 — FAstralSavedMove_Hero::PrepMoveFor만 호출. bClientUpdating 창에서만 읽힌다 */
	void SetReplayPawnCollisionPolicy(EAstralRootMotionPawnCollisionPolicy Policy) { ReplayPawnCollisionPolicy = Policy; }

	/** 죽은 MontageInstanceID 항목 실제 제거 — 비const 시점(Push/Remove 초입)에서만 */
	void PruneStalePawnCollisionPolicies();

	/**
	 * StopOnHit 정책 × 적대 Pawn이면 남은 이동량을 소비하지 않고 정지 (슬라이드 0).
	 * 근접 공격의 전진 루트모션이 적 캡슐을 밀며 슬라이드하면 적 주위를 도는 궤도가 생겨 방향 보정(락온 4단계)이 무의미해진다.
	 * 벽·지형·아군은 기존대로. 정책은 클라·서버가 각자 자기 몽타주에서 유도하므로 전송하지 않는다
	 */
	virtual float SlideAlongSurface(const FVector& Delta, float Time, const FVector& Normal, FHitResult& Hit, bool bHandleImpact) override;

	/** 보험 — ACharacter 캡슐은 CanCharacterStepUpOn=No라 원래 못 밟지만, 비ACharacter Pawn을 StopOnHit 대상으로 밟고 올라가는 경로를 닫는다 */
	virtual bool CanStepUp(const FHitResult& Hit) const override;

	void InitializeWithAbilitySystem(UAstralAbilitySystemComponent* InASC);
	void UninitializeFromAbilitySystem();

	UAstralAbilitySystemComponent* GetBoundAbilitySystem() const { return BoundASC; }

	float GetMoveSpeedMultiplier() const { return CachedMoveSpeedMultiplier; }
	float GetScaledMaxWalkSpeed() const { return MaxWalkSpeed * CachedMoveSpeedMultiplier; }

protected:

	virtual void OnUnregister() override;

	virtual void OnAbilitySystemBound();
	virtual void OnAbilitySystemUnbound();

	void HandleMoveSpeedMultiplierChanged(const FOnAttributeChangeData& Data);

	/** 정상 실행은 저작 정책, 클라 보정 리플레이(bClientUpdating)는 그 move가 기록한 정책 — 리플레이 중 노티파이는 재발화하지 않는다 */
	EAstralRootMotionPawnCollisionPolicy GetEffectivePawnCollisionPolicy() const;

	/** 정책 × 대상(AreHostile) — SlideAlongSurface·CanStepUp이 공유하는 단일 판정 */
	bool ShouldStopOnPawn(const FHitResult& Hit) const;

	/** source의 몽타주 인스턴스가 아직 살아 있는가 — 인터럽트 시 Terminate가 조기 return하면 End가 누락될 수 있다 */
	bool IsPawnCollisionPolicySourceAlive(const FAstralPawnCollisionPolicySource& Source) const;

	UPROPERTY(Transient)
	TObjectPtr<UAstralAbilitySystemComponent> BoundASC;

	float CachedMoveSpeedMultiplier = 1.0f;

	FDelegateHandle MoveSpeedMultiplierChangedHandle;

	FAstralCharacterGroundInfo CachedGroundInfo;

private:
	TArray<FAstralPawnCollisionPolicyOverride> PolicyOverrides;
	uint32 NextBeginOrder = 0;
	EAstralRootMotionPawnCollisionPolicy ReplayPawnCollisionPolicy = EAstralRootMotionPawnCollisionPolicy::Normal;
};
