#include "AstralAbilityTask_WeaponTrace.h"

#include "Abilities/GameplayAbility.h"
#include "Engine/World.h"
#include "Equipment/AstralEquipmentInstance.h"
#include "Equipment/AstralWeaponActor.h"

UAstralAbilityTask_WeaponTrace::UAstralAbilityTask_WeaponTrace(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	bTickingTask = true;
	bSimulatedTask = false;
}

UAstralAbilityTask_WeaponTrace* UAstralAbilityTask_WeaponTrace::WeaponTrace(UGameplayAbility* OwningAbility, AAstralWeaponActor* InWeaponActor, float InTraceRadius, int32 InNumBladeSamples)
{
	UAstralAbilityTask_WeaponTrace* Task = NewAbilityTask<UAstralAbilityTask_WeaponTrace>(OwningAbility);
	Task->WeaponActor = InWeaponActor;
	Task->TraceRadius = InTraceRadius;
	Task->NumBladeSamples = FMath::Max(2, InNumBladeSamples);
	return Task;
}

AAstralWeaponActor* UAstralAbilityTask_WeaponTrace::FindWeaponActorFromAbility(const UGameplayAbility* Ability)
{
	if (!Ability)
	{
		return nullptr;
	}

	// 장비 부여 시 SourceObject = EquipmentInstance (EquipmentList::AddEntry)
	if (const UAstralEquipmentInstance* Instance = Cast<UAstralEquipmentInstance>(Ability->GetCurrentSourceObject()))
	{
		return Instance->GetFirstSpawnedActorOfType<AAstralWeaponActor>();
	}
	return nullptr;
}

void UAstralAbilityTask_WeaponTrace::Activate()
{
	Super::Activate();

	if (!WeaponActor)
	{
		EndTask();
		return;
	}

	// 첫 틱의 기준 위치 — 밴드 시작 프레임부터 궤적이 이어지도록
	SampleBladePositions(PrevSamplePositions);
	bHasPrevSamples = PrevSamplePositions.Num() > 0;
}

void UAstralAbilityTask_WeaponTrace::SampleBladePositions(TArray<FVector>& OutPositions) const
{
	OutPositions.Reset();
	if (!WeaponActor)
	{
		return;
	}

	const FVector Start = WeaponActor->GetTraceStartLocation();
	const FVector End   = WeaponActor->GetTraceEndLocation();

	for (int32 Index = 0; Index < NumBladeSamples; ++Index)
	{
		const float Alpha = (NumBladeSamples > 1) ? (static_cast<float>(Index) / (NumBladeSamples - 1)) : 0.f;
		OutPositions.Add(FMath::Lerp(Start, End, Alpha));
	}
}

void UAstralAbilityTask_WeaponTrace::TickTask(float DeltaTime)
{
	Super::TickTask(DeltaTime);

	AActor* Avatar = GetAvatarActor();
	UWorld* World = Avatar ? Avatar->GetWorld() : nullptr;
	if (!World || !WeaponActor)
	{
		return;
	}

	TArray<FVector> CurrentPositions;
	SampleBladePositions(CurrentPositions);
	if (CurrentPositions.Num() == 0)
	{
		return;
	}

	if (bHasPrevSamples && PrevSamplePositions.Num() == CurrentPositions.Num())
	{
		FCollisionQueryParams Params(SCENE_QUERY_STAT(AstralWeaponTrace), false);
		Params.AddIgnoredActor(Avatar);
		Params.AddIgnoredActor(WeaponActor);

		// 샘플별 prev → curr 스윕 — 칼날 길이(샘플)와 스윙 궤적(프레임 간) 양방향을 덮는다
		for (int32 Index = 0; Index < CurrentPositions.Num(); ++Index)
		{
			TArray<FHitResult> Hits;
			World->SweepMultiByChannel(Hits, PrevSamplePositions[Index], CurrentPositions[Index], FQuat::Identity, ECC_Pawn, FCollisionShape::MakeSphere(TraceRadius), Params);

			for (const FHitResult& Hit : Hits)
			{
				AActor* HitActor = Hit.GetActor();
				if (!HitActor || HitActors.Contains(HitActor))
				{
					continue;
				}
				HitActors.Add(HitActor);

				if (ShouldBroadcastAbilityTaskDelegates())
				{
					OnHitTarget.Broadcast(Hit);
				}
			}
		}
	}

	PrevSamplePositions = MoveTemp(CurrentPositions);
	bHasPrevSamples = true;
}

void UAstralAbilityTask_WeaponTrace::OnDestroy(bool bInOwnerFinished)
{
	HitActors.Reset();
	PrevSamplePositions.Reset();

	Super::OnDestroy(bInOwnerFinished);
}
