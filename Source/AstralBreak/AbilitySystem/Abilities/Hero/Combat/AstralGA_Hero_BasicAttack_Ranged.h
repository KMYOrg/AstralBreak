#pragma once

#include "CoreMinimal.h"
#include "AbilitySystem/Abilities/Hero/AstralGA_Hero_Base.h"
#include "Combat/AstralRangedAttackTypes.h"
#include "GameplayTagContainer.h"
#include "AstralGA_Hero_BasicAttack_Ranged.generated.h"

class AAstralRangedWeaponActor;
class UAnimMontage;
class UAstralFacingSession;
struct FAstralFacingStageResolution;

/** 이 공격에 고정된 조준 모드 — 공격 시작에 결정되고 도중에 락온이 바뀌어도 유지된다 */
enum class EAstralRangedAimMode : uint8
{
	FreeAim,
	LockOn,
};

/**
 * 원거리 기본 공격 공통 베이스 — 발사 방식 무관 부분만 소유:
 * Ranged 모드 게이트·상호배타 정책, 초기 페이로드(고정 타겟·시작 몸 방향·폴백 발사 방향), 단발 FacingSession,
 * 커밋 → 시작 방향 설치 → FireMontage → 발사 이벤트 → 발사선 확정 흐름, 발사 가드.
 * 발사 방식(투사체/히트스캔/...)은 ExecuteRangedAttack(Shot) 훅의 파생이 구현하고,
 * 어느 파생이 부여되는지는 무기 계열의 AbilitySet(데이터)이 결정한다 — 입력은 공통(InputTag.Attack.Basic).
 * 조준: 공격 시작에 타겟 A를 고정하고 선딜로 자세를 잡은 뒤, 발사 순간 A의 최신 조준점으로 비유도 발사.
 * A 무효·각도 이탈이면 새 타겟·카메라로 바꾸지 않고 공격 시작에 조준한 지점(FallbackAimPoint)을 향해 그대로 쏜다.
 */
UCLASS(Abstract)
class ASTRALBREAK_API UAstralGA_Hero_BasicAttack_Ranged : public UAstralGA_Hero_Base
{
	GENERATED_BODY()

public:
	UAstralGA_Hero_BasicAttack_Ranged(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());

	//~UAstralGameplayAbility — 원거리 초기 페이로드. 총구·무기·CurrentSpecHandle을 조회하지 않는다 (ActorInfo만)
	virtual EAstralInputActivationPreparation MakeActivationEventData(const FGameplayAbilityActorInfo& ActorInfo, FGameplayEventData& OutEventData) const override;
	//~End UAstralGameplayAbility

protected:
	virtual void ActivateAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const FGameplayEventData* TriggerEventData) override;
	virtual void EndAbility(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, bool bReplicateEndAbility, bool bWasCancelled) override;

	/** 서버 — 확정된 발사선으로 발사 실행. 파생이 구현 (투사체 스폰 / 히트스캔 판정 / ...). 조준을 다시 계산하지 않는다 */
	virtual void ExecuteRangedAttack(const FAstralRangedShot& Shot) {}

	virtual TOptional<FAstralMuzzleClearance> GetMuzzleClearance() const { return TOptional<FAstralMuzzleClearance>(); }

	/** 장착 중인 원거리 무기 (SourceObject 경유) — 원거리 무기가 아니면 null */
	AAstralRangedWeaponActor* GetRangedWeaponActor() const;

	/**
	 * 자유 조준 — 화면 중앙(카메라) 레이 해석 (서버). OutMuzzle→OutTargetPoint가 발사선.
	 * 조준점이 총구 뒤(극근접 지형 등)면 카메라 레이 방향의 원거리 지점으로 보정해 전방을 보장.
	 * 컨트롤러 부재 등 해석 불가 시 false
	 */
	bool ComputeAimTarget(const AAstralRangedWeaponActor* WeaponActor, FVector& OutMuzzleLocation, FVector& OutTargetPoint) const;

	/** 발사 노티파이 수신 — 활성화·출처 확인 후 ProcessFire */
	UFUNCTION()
	void OnFireEventReceived(FGameplayEventData EventData);

	UFUNCTION()
	void OnMontageFinished();

	/** 발사 처리 — 즉발(몽타주 없음) 경로와 이벤트 경로가 공유 (정책이 갈라지지 않도록). */
	void ProcessFire();

	/** 서버 — 발사선 확정. 고정 모드별 해석(최신 타겟 / 폴백 / 카메라) + 총구 여유 검사. 실패면 미설정 (발사 소모, 무기 실행 없음) */
	TOptional<FAstralRangedShot> ResolveShot() const;

	/**
	 * 로컬 발사 연출 훅 — 활성화당 1회. FireCueTag가 있으면 활성화 예측 키로 GameplayCue 실행:
	 * 소유 클라는 예측 실행(서버 거부보다 먼저 보일 수 있다), 서버는 멀티캐스트 — 소유자는 자기 키를 알아보고 건너뛰고 관찰자만 재생.
	 */
	void PresentShot();

	/** 총구 여유 — 아바타 기준점 → 총구 스윕 + 투사체 반경. 막혔으면 false (벽 너머/벽 내부 스폰 방지) */
	bool IsMuzzleClear(const UWorld* World, const AActor* Avatar, const AActor* WeaponActor, const FVector& MuzzleLocation, const FAstralMuzzleClearance& Clearance) const;

	/** 초기 페이로드 캡처 — 시작 몸 방향(Facing 제안) + 폴백 조준점. 훅과 로컬 폴백이 공유 */
	FAstralRangedActivationData CaptureActivationData(const AActor* Avatar, const FGameplayAbilityActorInfo& ActorInfo) const;

	/** 활성화마다 새 Facing 세션 (NumStages = 1). Stage 0은 초기 페이로드의 BodyFacing 어댑터 */
	void BeginFacingSession(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo, const TOptional<FAstralFacingProposal>& StageZero);

	/** 확정 결과 → 워프 설치/제거. 서버가 거부한 타겟은 발사 시점 조준점으로도 쓰지 않는다 (고정 타겟 해제) */
	void ApplyFacingResolution(const FAstralFacingStageResolution& Resolution);

	void ResetShotState();

protected:
	/** 발사 모션 (플레이스홀더 가능 — 미지정이면 즉발 후 종료. 정식 무기는 FireMontage + 발사 노티파이 필수) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ranged")
	TObjectPtr<UAnimMontage> FireMontage;

	/** 명중 데미지 (Damage GE는 GameData 전역, SetByCaller.Damage 주입) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ranged")
	float BaseDamage = 15.f;

	/** 명중 시 표식 수급 — 기획상 표식의 주 축적원 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ranged", Meta = (ClampMin = "0.0"))
	float MarkGainOnHit = 10.f;

	/** 자유 조준 — 조준점 확정 트레이스 사거리 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ranged")
	float AimTraceRange = 10000.f;

	/** 시작 몸 방향 워프 타겟 이름 — FireMontage의 MotionWarping 노티파이와 일치. 비우면 몸 회전 보정 없음 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ranged|Facing")
	FName FacingWarpTargetName = TEXT("RangedAttack.Facing");

	/** 발사 순간 몸 전방 대비 고정 타겟 허용각 (도). 초과 = 등 뒤로 꺾지 않고 최초 조준점. Facing의 방위 오차와 별개 설정 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ranged|Facing", Meta = (ClampMin = "0.0", ClampMax = "180.0"))
	float MaxFireAssistYaw = 60.f;

	/** 이 거리 미만이면 발사 허용각 검사를 건너뛴다 — 접촉 거리에서 방위가 불안정하다 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ranged|Facing", Meta = (ClampMin = "0.0"))
	float FireAssistMinDistance = 100.f;

	/** 고정 타겟까지 허용 거리 — 초과 시 최초 조준점 (락온 유지 반경 2000 + 여유) */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ranged|Facing", Meta = (ClampMin = "0.0"))
	float LockOnFireRange = 2200.f;

	/** 발사 연출 GameplayCue (선택) — 비우면 훅만 있고 연출 없음. 총구 섬광·발사음은 여기 연결 */
	UPROPERTY(EditDefaultsOnly, Category = "Astral|Ranged|Presentation", Meta = (Categories = "GameplayCue"))
	FGameplayTag FireCueTag;

private:
	/** 이 공격의 고정 조준 모드·타겟 — 활성화 시작에 결정, EndAbility에서 정리 */
	EAstralRangedAimMode PinnedAimMode = EAstralRangedAimMode::FreeAim;
	TWeakObjectPtr<AActor> PinnedTarget;
	FName PinnedTargetPointId = NAME_None;

	/** 공격 시작에 조준한 월드 지점 — 타겟 무효·각도 이탈·카메라 해석 실패 시 발사 순간 총구에서 이 점을 향해 쏜다 */
	TOptional<FVector> FallbackAimPoint;

	/** 서버 발사 처리 진입 여부 — 총구가 막혀 소모돼도 되돌리지 않는다 */
	bool bHasExecutedShot = false;

	/** 이번 활성화의 로컬 발사 연출 실행 여부 */
	bool bHasPresentedShot = false;

	UPROPERTY(Transient)
	TObjectPtr<UAstralFacingSession> FacingSession;

#if !UE_BUILD_SHIPPING
	/** FireMontage의 발사 노티파이·Facing 밴드 저작 검증 (활성화 1회차) */
	bool bMontageValidated = false;
#endif
};
