#include "AstralEnemyController.h"

#include "AI/AstralEnemyTargeting.h"
#include "AI/AstralThreatComponent.h"
#include "AbilitySystem/AstralEventGameplayTags.h"
#include "AbilitySystem/Abilities/AstralAbilityGameplayTags.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AstralCombatCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Components/StateTreeAIComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerState.h"

namespace
{
	/** 타깃 후보가 될 수 있는 폰 — 플레이어의 폰. 봇(AI 가 가진 PlayerState) · 적 · 자기 자신은 아니다 */
	bool IsEnemyTargetCandidatePawn(const APawn* Pawn)
	{
		const APlayerState* PlayerState = Pawn ? Pawn->GetPlayerState() : nullptr;
		return PlayerState && !PlayerState->IsABot();
	}

	/** 후보의 적대심 — 히어로 자원 세트가 없으면 기본값 (AstralCombatStatics 가 GuardDamageMultiplier 를 읽는 방식과 같다) */
	float ReadEnemyTargetHostility(const APawn* Pawn)
	{
		const UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Pawn);
		if (ASC && ASC->HasAttributeSetForAttribute(UAstralHeroResourceSet::GetHostilityAttribute()))
		{
			return ASC->GetNumericAttribute(UAstralHeroResourceSet::GetHostilityAttribute());
		}
		return AstralEnemyTargeting::DefaultHostility;
	}
}

AAstralEnemyController::AAstralEnemyController(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	StateTreeComponent = CreateDefaultSubobject<UStateTreeAIComponent>(TEXT("StateTreeComponent"));
	StateTreeComponent->SetStartLogicAutomatically(false);

	ThreatComponent = CreateDefaultSubobject<UAstralThreatComponent>(TEXT("ThreatComponent"));

	// OnPossess 는 APawn::PostInitializeComponents 안에서 돌아 어빌리티 부여보다 앞선다 — 시작은 폰의 준비 완료 신호로 한다
	bStartAILogicOnPossess = false;
}

void AAstralEnemyController::OnPossess(APawn* InPawn)
{
	Super::OnPossess(InPawn);

	// 엔진이 무효 폰을 거부하면 빙의되지 않은 채 돌아온다
	if (!InPawn || GetPawn() != InPawn)
	{
		return;
	}

	BindPawnDamaged(InPawn);
	BindPawnStaggered(InPawn);

	AAstralCombatCharacter* CombatCharacter = Cast<AAstralCombatCharacter>(InPawn);
	if (!CombatCharacter)
	{
		// 부여 단계가 없는 폰 — 엔진 Possess 시작과 같다
		TryStartLogic();
		return;
	}

	CombatCharacter->GetHealthComponent()->OnDeathStarted.AddUniqueDynamic(this, &ThisClass::HandlePawnDeathStarted);
	CombatCharacter->OnCombatReady_RegisterAndCall(FSimpleMulticastDelegate::FDelegate::CreateUObject(this, &ThisClass::TryStartLogic));
}

void AAstralEnemyController::OnUnPossess()
{
	// Super 는 폰을 비운 뒤 StopLogic 을 불러 컨텍스트 검사가 실패한다 — 폰이 있을 때 먼저 멈춘다. 뒤따르는 호출은 실행 중이 아니므로 바로 돌아온다
	StateTreeComponent->StopLogic(TEXT("UnPossess"));

	// 트리가 멈춘 뒤라 이벤트 없이 구독만 푼다
	SetCurrentTarget(nullptr);

	UnbindPawnDamaged();
	UnbindPawnStaggered();
	ThreatComponent->Reset();

	if (AAstralCombatCharacter* CombatCharacter = Cast<AAstralCombatCharacter>(GetPawn()))
	{
		CombatCharacter->OnCombatReady_Unregister(this);
		CombatCharacter->GetHealthComponent()->OnDeathStarted.RemoveDynamic(this, &ThisClass::HandlePawnDeathStarted);
	}

	Super::OnUnPossess();
}

bool AAstralEnemyController::AcquireTarget()
{
	const APawn* MyPawn = GetPawn();
	const UWorld* World = GetWorld();
	const AGameStateBase* GameState = World ? World->GetGameState() : nullptr;
	if (!MyPawn || !GameState)
	{
		SetCurrentTarget(nullptr);
		return false;
	}

	// 수집 — 플레이어의 폰. 봇(AI 가 가진 PlayerState)은 뺀다. 사망 판정은 구독하는 것과 같은 원천(HealthComponent)으로 한다
	TArray<FAstralThreatCandidateInfo> Candidates;
	for (const APlayerState* CandidateState : GameState->PlayerArray)
	{
		APawn* PlayerPawn = CandidateState ? CandidateState->GetPawn() : nullptr;
		if (!IsEnemyTargetCandidatePawn(PlayerPawn))
		{
			continue;
		}

		const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(PlayerPawn);

		FAstralThreatCandidateInfo& Candidate = Candidates.AddDefaulted_GetRef();
		Candidate.Pawn = PlayerPawn;
		Candidate.Location = PlayerPawn->GetActorLocation();
		Candidate.bDeadOrDying = HealthComponent && HealthComponent->IsDeadOrDying();
		Candidate.Hostility = ReadEnemyTargetHostility(PlayerPawn);
	}

	// 분산(§13 T3) — 후보마다 '이미 노리는 다른 적의 수' 를 지금 읽는다(등록부 없음 — 공격 자리와 같은 방식). 값이 0 인 적(마네킹)은 세지 않는다
	if (ThreatComponent->SpreadWeight > 0.f)
	{
		for (TActorIterator<AAstralEnemyController> It(GetWorld()); It; ++It)
		{
			const AAstralEnemyController* Other = *It;
			if (Other == this || !Other->CurrentTarget)
			{
				continue;
			}
			for (FAstralThreatCandidateInfo& Candidate : Candidates)
			{
				if (Candidate.Pawn == Other->CurrentTarget)
				{
					++Candidate.NumOtherAttackers;
					break;
				}
			}
		}
	}

	// 누구를 고를지는 위협 컴포넌트의 규칙이다 — 기록 없음 → 가장 가까운 후보(또는 추첨) / 유지 시간 안 → 그대로 / 아니면 가중 추첨
	const int32 TargetIndex = ThreatComponent->SelectTarget(MyPawn->GetActorLocation(), Candidates, CurrentTarget);
	SetCurrentTarget(Candidates.IsValidIndex(TargetIndex) ? Candidates[TargetIndex].Pawn : nullptr);
	return CurrentTarget != nullptr;
}

bool AAstralEnemyController::GetBearingFromTarget(float& OutDegrees) const
{
	const APawn* MyPawn = GetPawn();
	const AActor* Target = CurrentTarget;
	if (!MyPawn || !Target)
	{
		return false;
	}

	const FVector ToMe = MyPawn->GetActorLocation() - Target->GetActorLocation();
	if (ToMe.SizeSquared2D() <= UE_KINDA_SMALL_NUMBER)
	{
		return false;
	}

	OutDegrees = FMath::RadiansToDegrees(FMath::Atan2(ToMe.Y, ToMe.X));
	return true;
}

bool AAstralEnemyController::SelectEngageSlot(float MinSeparationDegrees)
{
	UWorld* World = GetWorld();
	const AActor* Target = CurrentTarget;
	if (!World || !GetPawn() || !Target)
	{
		bHasEngageSlot = false;
		return false;
	}

	// 내 쪽 = 타깃에서 나를 보는 방위. 타깃과 겹쳐 있으면 쥐고 있던 자리(없으면 0)
	float Preferred = bHasEngageSlot ? EngageBearing : 0.f;
	GetBearingFromTarget(Preferred);

	// 같은 타깃을 쥔 다른 적의 자리 — 지금 읽는다. 적이 몇 마리뿐이라 순회로 충분하다
	TArray<float, TInlineAllocator<8>> Occupied;
	for (TActorIterator<AAstralEnemyController> It(World); It; ++It)
	{
		const AAstralEnemyController* Other = *It;
		if (Other != this && Other->bHasEngageSlot && Other->CurrentTarget == Target)
		{
			Occupied.Add(Other->EngageBearing);
		}
	}

	EngageBearing = AstralEnemyTargeting::SelectEngageBearing(Preferred, Occupied, MinSeparationDegrees);
	bHasEngageSlot = true;
	return true;
}

bool AAstralEnemyController::GetEngageLocation(float Radius, FVector& OutLocation) const
{
	const AActor* Target = CurrentTarget;
	if (!Target || !bHasEngageSlot)
	{
		return false;
	}

	const float Radians = FMath::DegreesToRadians(EngageBearing);
	OutLocation = Target->GetActorLocation() + FVector(FMath::Cos(Radians), FMath::Sin(Radians), 0.f) * FMath::Max(Radius, 0.f);
	return true;
}

void AAstralEnemyController::BindPawnDamaged(const APawn* InPawn)
{
	UnbindPawnDamaged();

	const UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(InPawn);
	const UAstralHealthSet* HealthSet = ASC ? ASC->GetSet<UAstralHealthSet>() : nullptr;
	if (!HealthSet)
	{
		return;
	}

	// 서버에서만 불린다 (PostGameplayEffectExecute) — 컨트롤러도 서버에만 있다
	PawnDamagedHandle = HealthSet->OnDamaged.AddUObject(this, &ThisClass::HandlePawnDamaged);
	BoundHealthSet = HealthSet;
}

void AAstralEnemyController::UnbindPawnDamaged()
{
	if (const UAstralHealthSet* HealthSet = BoundHealthSet.Get())
	{
		HealthSet->OnDamaged.Remove(PawnDamagedHandle);
	}
	BoundHealthSet.Reset();
	PawnDamagedHandle.Reset();
}

void AAstralEnemyController::BindPawnStaggered(const APawn* InPawn)
{
	UnbindPawnStaggered();

	UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(InPawn);
	if (!ASC)
	{
		return;
	}

	// 0 ↔ 1 이상으로 바뀔 때만 온다 — 움찔 중에 경직이 겹쳐도(같은 태그) 한 번이다
	PawnStaggeredHandle = ASC->RegisterGameplayTagEvent(AstralGameplayTags::State_Enemy_Staggered, EGameplayTagEventType::NewOrRemoved).AddUObject(this, &ThisClass::HandlePawnStaggeredTagChanged);
	BoundStaggerAbilitySystem = ASC;
}

void AAstralEnemyController::UnbindPawnStaggered()
{
	if (UAbilitySystemComponent* ASC = BoundStaggerAbilitySystem.Get())
	{
		ASC->UnregisterGameplayTagEvent(PawnStaggeredHandle, AstralGameplayTags::State_Enemy_Staggered, EGameplayTagEventType::NewOrRemoved);
	}
	BoundStaggerAbilitySystem.Reset();
	PawnStaggeredHandle.Reset();
}

void AAstralEnemyController::HandlePawnStaggeredTagChanged(const FGameplayTag Tag, int32 NewCount)
{
	// 하던 일을 멈추는 것은 트리의 몫이다 — Root 의 Staggered 전환이 Stagger 로 보내고, 상태를 나가며 MoveTo · 공격 GA 가 취소된다
	if (NewCount > 0 && StateTreeComponent->IsRunning())
	{
		StateTreeComponent->SendStateTreeEvent(AstralGameplayTags::AIEvent_Staggered);
	}
}

void AAstralEnemyController::HandlePawnDamaged(AActor* EffectInstigator, AActor* EffectCauser, const FGameplayEffectSpec* EffectSpec, float Damage, float OldValue, float NewValue)
{
	// 가해자 = 이펙트 컨텍스트의 Instigator. 프로젝트의 피해 경로(UAstralCombatStatics::ApplyAttackHit)는 여기에 폰을 싣는다.
	// 자기 자신(DamageSelf) · 다른 적은 위협이 아니다
	const APawn* Attacker = Cast<APawn>(EffectInstigator);
	if (!IsEnemyTargetCandidatePawn(Attacker))
	{
		return;
	}

	// 다시 고르는 것은 트리의 몫이다 — Chase 의 Retarget 전환이 Acquire 로 보낸다. 공격 중이면 이벤트는 버려지고 표시만 남아 그 사이클 뒤에 반영된다
	if (ThreatComponent->RecordDamage(Attacker, Damage, CurrentTarget) && StateTreeComponent->IsRunning())
	{
		StateTreeComponent->SendStateTreeEvent(AstralGameplayTags::AIEvent_Retarget);
	}
}

void AAstralEnemyController::SetCurrentTarget(AActor* NewTarget)
{
	if (CurrentTarget == NewTarget)
	{
		return;
	}

	if (AActor* OldTarget = CurrentTarget)
	{
		OldTarget->OnDestroyed.RemoveDynamic(this, &ThisClass::HandleTargetDestroyed);
		if (UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(OldTarget))
		{
			HealthComponent->OnDeathStarted.RemoveDynamic(this, &ThisClass::HandleTargetDeathStarted);
		}
	}

	CurrentTarget = NewTarget;

	// 자리는 타깃에 딸린 값이다 — 타깃이 바뀌면(없어지면) 비워, 같은 타깃을 쥔 다른 적이 이 자리를 피하지 않게 한다
	bHasEngageSlot = false;

	if (NewTarget)
	{
		// 접속 종료는 폰 파괴로 온다
		NewTarget->OnDestroyed.AddUniqueDynamic(this, &ThisClass::HandleTargetDestroyed);
		if (UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(NewTarget))
		{
			HealthComponent->OnDeathStarted.AddUniqueDynamic(this, &ThisClass::HandleTargetDeathStarted);
		}
	}
}

void AAstralEnemyController::HandleTargetLost(const AActor* LostActor)
{
	// 이미 다른 타깃으로 넘어간 뒤에 온 통지는 버린다
	if (!LostActor || LostActor != CurrentTarget.Get())
	{
		return;
	}

	SetCurrentTarget(nullptr);

	// 다시 고르는 것은 트리의 몫이다 — Chase 의 TargetLost 전환이 Acquire 로 보낸다. 공격 중이면 공격은 끝까지 가고 그 뒤 Acquire 가 고른다
	if (StateTreeComponent->IsRunning())
	{
		StateTreeComponent->SendStateTreeEvent(AstralGameplayTags::AIEvent_TargetLost);
	}
}

void AAstralEnemyController::HandleTargetDeathStarted(AActor* OwningActor)
{
	HandleTargetLost(OwningActor);
}

void AAstralEnemyController::HandleTargetDestroyed(AActor* DestroyedActor)
{
	HandleTargetLost(DestroyedActor);
}

void AAstralEnemyController::TryStartLogic()
{
	const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(GetPawn());
	if (!GetPawn() || (HealthComponent && HealthComponent->IsDeadOrDying()) || StateTreeComponent->IsRunning())
	{
		return;
	}

	StateTreeComponent->StartLogic();
}

void AAstralEnemyController::HandlePawnDeathStarted(AActor* OwningActor)
{
	// GA 는 GA_Death 가 StartDeath 전에 취소했고, 콜리전 · 이동은 폰이 끈다 — 구독 순서에 기대지 않는다
	StateTreeComponent->StopLogic(TEXT("PawnDeathStarted"));

	// 트리 작업의 이동은 ExitState 가 취소한다. 트리 밖에서 시작된 이동까지 끊는다
	StopMovement();

	// 죽은 적은 타깃을 쥐지 않는다 (구독 정리)
	SetCurrentTarget(nullptr);

	// 위협 기록도 같이 비운다
	UnbindPawnDamaged();
	UnbindPawnStaggered();
	ThreatComponent->Reset();
}
