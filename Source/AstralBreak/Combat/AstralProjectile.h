#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstralProjectile.generated.h"

class UAbilitySystemComponent;
class UProjectileMovementComponent;
class USphereComponent;
class UStaticMeshComponent;

/**
 * 서버 권위 투사체 — 원거리 기본 공격의 판정 단위 (M2: 예측 없음, 가짜 투사체 동기화는 M4).
 * 서버만 콜리전 활성(판정), 클라는 bReplicates + 이동 복제로 표시만.
 * 판정이 월드 오브젝트 기준이라 히트스캔과 달리 랙 컴펜세이션 부채가 없다.
 *
 * 명중(서버): CanDamage 필터는 ApplyWeaponDamage 내부 — Hostile이면 데미지 + 표식/오의 수급 후 소멸,
 * 아군/중립/사망 대상은 관통 통과. 월드 블록(벽) 또는 수명(InitialLifeSpan) 만료 시 소멸.
 * Instigator=폰 (방어 정면 판정 OriginalInstigator 무회귀), EffectCauser=무기.
 *
 * 페이로드는 Deferred 스폰으로 주입 (InitializeProjectile → FinishSpawning) — 초기 번치 원자성 계약.
 */
UCLASS(Abstract, Blueprintable)
class ASTRALBREAK_API AAstralProjectile : public AActor
{
	GENERATED_BODY()

public:
	AAstralProjectile();

	/** 서버 — Deferred 스폰 직후, FinishSpawning 전에 호출 (발사 GA가 주입) */
	void InitializeProjectile(UAbilitySystemComponent* InSourceASC, AActor* InSourceAvatar, AActor* InSourceWeaponActor, float InBaseDamage, float InMarkGainOnHit, float InUltGainOnHit);

protected:
	virtual void BeginPlay() override;

	UFUNCTION()
	void OnSphereBeginOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult);

	/** 블록 충돌(벽 등)로 이동이 멎으면 소멸 */
	UFUNCTION()
	void OnProjectileStop(const FHitResult& ImpactResult);

protected:
	/** 판정 스피어 (루트) — Pawn Overlap / WorldStatic Block, 서버 전용 활성 */
	UPROPERTY(VisibleAnywhere, Category = "Astral|Projectile")
	TObjectPtr<USphereComponent> CollisionComponent;

	/** 표시 전용 메시 */
	UPROPERTY(VisibleAnywhere, Category = "Astral|Projectile")
	TObjectPtr<UStaticMeshComponent> MeshComponent;

	UPROPERTY(VisibleAnywhere, Category = "Astral|Projectile")
	TObjectPtr<UProjectileMovementComponent> ProjectileMovement;

private:
	// 발사 페이로드 (서버 로컬 — 판정이 전부 서버라 복제 불필요). 비행 중 소스 소멸 대비 약참조
	TWeakObjectPtr<UAbilitySystemComponent> SourceASC;
	TWeakObjectPtr<AActor> SourceAvatar;
	TWeakObjectPtr<AActor> SourceWeaponActor;

	float BaseDamage = 0.f;
	float MarkGainOnHit = 0.f;
	float UltGainOnHit = 0.f;
};
