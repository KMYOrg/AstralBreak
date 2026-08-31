#include "AstralProjectile.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/ProjectileMovementComponent.h"

AAstralProjectile::AAstralProjectile()
{
	PrimaryActorTick.bCanEverTick = false;

	bReplicates = true;
	SetReplicatingMovement(true);

	// 수명 안전망 — 아무것도 못 맞히면 자동 소멸
	InitialLifeSpan = 3.0f;

	CollisionComponent = CreateDefaultSubobject<USphereComponent>(TEXT("CollisionComponent"));
	SetRootComponent(CollisionComponent);
	CollisionComponent->InitSphereRadius(15.f);
	CollisionComponent->SetCollisionObjectType(ECC_WorldDynamic);
	CollisionComponent->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	CollisionComponent->SetCollisionResponseToAllChannels(ECR_Ignore);
	CollisionComponent->SetCollisionResponseToChannel(ECC_Pawn, ECR_Overlap);
	CollisionComponent->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Block);
	CollisionComponent->SetGenerateOverlapEvents(true);

	MeshComponent = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("MeshComponent"));
	MeshComponent->SetupAttachment(CollisionComponent);
	MeshComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	MeshComponent->SetGenerateOverlapEvents(false);

	ProjectileMovement = CreateDefaultSubobject<UProjectileMovementComponent>(TEXT("ProjectileMovement"));
	ProjectileMovement->SetUpdatedComponent(CollisionComponent);
	ProjectileMovement->InitialSpeed = 3000.f;
	ProjectileMovement->MaxSpeed = 3000.f;
	ProjectileMovement->bRotationFollowsVelocity = true;
	ProjectileMovement->ProjectileGravityScale = 0.f; // 직선탄 기본 — 곡사 무기는 BP에서 조정
	ProjectileMovement->bShouldBounce = false;
}

void AAstralProjectile::InitializeProjectile(UAbilitySystemComponent* InSourceASC, AActor* InSourceAvatar, AActor* InSourceWeaponActor, float InBaseDamage, float InMarkGainOnHit, float InUltGainOnHit)
{
	SourceASC = InSourceASC;
	SourceAvatar = InSourceAvatar;
	SourceWeaponActor = InSourceWeaponActor;
	BaseDamage = InBaseDamage;
	MarkGainOnHit = InMarkGainOnHit;
	UltGainOnHit = InUltGainOnHit;

	// 발사자·자기 무기와의 스폰 즉시 오버랩/스윕 차단
	if (CollisionComponent)
	{
		if (InSourceAvatar)
		{
			CollisionComponent->MoveIgnoreActors.Add(InSourceAvatar);
		}
		if (InSourceWeaponActor)
		{
			CollisionComponent->MoveIgnoreActors.Add(InSourceWeaponActor);
		}
	}
}

void AAstralProjectile::BeginPlay()
{
	Super::BeginPlay();

	// 판정은 서버 전용 — 클라 인스턴스는 표시만 (이동은 액터 이동 복제가 담당)
	if (!HasAuthority())
	{
		CollisionComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		return;
	}

	CollisionComponent->OnComponentBeginOverlap.AddDynamic(this, &ThisClass::OnSphereBeginOverlap);
	ProjectileMovement->OnProjectileStop.AddDynamic(this, &ThisClass::OnProjectileStop);
}

void AAstralProjectile::OnSphereBeginOverlap(UPrimitiveComponent* OverlappedComponent, AActor* OtherActor, UPrimitiveComponent* OtherComp, int32 OtherBodyIndex, bool bFromSweep, const FHitResult& SweepResult)
{
	if (!HasAuthority() || !OtherActor || OtherActor == SourceAvatar.Get() || OtherActor == SourceWeaponActor.Get())
	{
		return;
	}

	UAbilitySystemComponent* ASC = SourceASC.Get();
	AActor* Avatar = SourceAvatar.Get();
	if (!ASC || !Avatar)
	{
		// 발사자 소멸 — 판정 주체가 없으므로 그냥 소멸
		Destroy();
		return;
	}

	// 이동 스윕이 아닌 오버랩엔 히트 정보가 비어 있을 수 있다 — 최소 정보 구성
	FHitResult Hit = SweepResult;
	if (!bFromSweep)
	{
		Hit = FHitResult(OtherActor, OtherComp, GetActorLocation(), -GetActorForwardVector());
	}

	// CanDamage 필터 포함 — Hostile이 아니면(아군/중립/사망) 관통 통과. EffectCauser = 발사 무기
	if (UAstralCombatStatics::ApplyAttackHit(ASC, Avatar, SourceWeaponActor.Get(), Hit, BaseDamage))
	{
		// 수급은 명중 시점(서버) — 발사 GA는 이미 종료됐을 수 있어 투사체가 직접
		UAstralCombatStatics::ApplyMarkGainToSelf(ASC, MarkGainOnHit);
		UAstralCombatStatics::ApplyUltGainToSelf(ASC, UltGainOnHit);
		Destroy();
	}
}

void AAstralProjectile::OnProjectileStop(const FHitResult& ImpactResult)
{
	// 월드 블록(벽/지형) — 소멸. 임팩트 연출은 GameplayCue 도입(M3) 시
	Destroy();
}
