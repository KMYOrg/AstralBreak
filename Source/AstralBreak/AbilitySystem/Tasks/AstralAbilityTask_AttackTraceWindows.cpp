#include "AstralAbilityTask_AttackTraceWindows.h"

#include "AbilitySystemComponent.h"
#include "Abilities/GameplayAbility.h"
#include "Engine/World.h"
#include "Equipment/AstralEquipmentInstance.h"
#include "Equipment/AstralWeaponActor.h"

UAstralAbilityTask_AttackTraceWindows::UAstralAbilityTask_AttackTraceWindows(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	bTickingTask = true;
	bSimulatedTask = false;
}

UAstralAbilityTask_AttackTraceWindows* UAstralAbilityTask_AttackTraceWindows::WaitAttackTraceWindows(UGameplayAbility* OwningAbility, float InTraceRadius, FGameplayTag InBeginEventTag, FGameplayTag InEndEventTag, int32 InNumBladeSamples)
{
	UAstralAbilityTask_AttackTraceWindows* Task = NewAbilityTask<UAstralAbilityTask_AttackTraceWindows>(OwningAbility);
	Task->TraceRadius = InTraceRadius;
	Task->BeginEventTag = InBeginEventTag;
	Task->EndEventTag = InEndEventTag;
	Task->NumBladeSamples = FMath::Max(2, InNumBladeSamples);
	return Task;
}

AAstralWeaponActor* UAstralAbilityTask_AttackTraceWindows::FindWeaponActorFromAbility(const UGameplayAbility* Ability)
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

void UAstralAbilityTask_AttackTraceWindows::Activate()
{
	Super::Activate();

	UAbilitySystemComponent* ASC = AbilitySystemComponent.Get();
	if (!ASC || !BeginEventTag.IsValid() || !EndEventTag.IsValid())
	{
		EndTask();
		return;
	}

	// 자식 WaitGameplayEvent 태스크를 만들지 않고 ASC에 직접 등록 (WaitGameplayEvent의 exact-match 경로와 동일 시맨틱)
	BeginEventHandle = ASC->GenericGameplayEventCallbacks.FindOrAdd(BeginEventTag).AddUObject(this, &ThisClass::HandleBeginEvent);
	EndEventHandle = ASC->GenericGameplayEventCallbacks.FindOrAdd(EndEventTag).AddUObject(this, &ThisClass::HandleEndEvent);

	// 스윕은 authority 전용 — 예측 클라 인스턴스는 틱 자체를 등록하지 않는다
	// (틱 등록은 Activate 리턴 후라 여기서 끄면 반영된다).
	// TODO: 클라이언트 측 vfx효과를 위해 부분적 서버 권위 실행 — 그때 이 게이트를 완화
	if (!IsAuthority())
	{
		bTickingTask = false;
	}
}

bool UAstralAbilityTask_AttackTraceWindows::IsAuthority() const
{
	const FGameplayAbilityActorInfo* ActorInfo = Ability ? Ability->GetCurrentActorInfo() : nullptr;
	return ActorInfo && ActorInfo->IsNetAuthority();
}

void UAstralAbilityTask_AttackTraceWindows::HandleBeginEvent(const FGameplayEventData* /*Payload*/)
{
	// 데미지는 서버 권위 — authority 인스턴스만 밴드를 연다
	if (!IsAuthority())
	{
		return;
	}

	// 겹침 방어 — 이전 밴드가 안 닫혔으면(누락 End) 정리 후 새 밴드로 (구 StopWeaponTrace 선행 호출의 역할)
	ResetBandState();

	++WindowSerial;

	// 무기 해석은 밴드마다 — 미장착(장비 해제 상태 등)이면 이번 밴드는 판정 없음
	CurrentWeaponActor = FindWeaponActorFromAbility(Ability);
	if (!CurrentWeaponActor)
	{
		return;
	}

	State = EWindowState::Tracing;

	// 밴드 시작 프레임부터 궤적이 이어지도록 기준 위치를 먼저 잡는다
	SampleBladePositions(PrevSamplePositions);
	bHasPrevSamples = PrevSamplePositions.Num() > 0;
}

void UAstralAbilityTask_AttackTraceWindows::HandleEndEvent(const FGameplayEventData* /*Payload*/)
{
	if (!IsAuthority())
	{
		return;
	}

	ResetBandState();
}

void UAstralAbilityTask_AttackTraceWindows::ResetBandState()
{
	State = EWindowState::Waiting;
	CurrentWeaponActor = nullptr;
	HitActors.Reset();
	PrevSamplePositions.Reset();
	bHasPrevSamples = false;
}

void UAstralAbilityTask_AttackTraceWindows::SampleBladePositions(TArray<FVector>& OutPositions) const
{
	OutPositions.Reset();
	if (!CurrentWeaponActor)
	{
		return;
	}

	const FVector Start = CurrentWeaponActor->GetTraceStartLocation();
	const FVector End   = CurrentWeaponActor->GetTraceEndLocation();

	for (int32 Index = 0; Index < NumBladeSamples; ++Index)
	{
		const float Alpha = (NumBladeSamples > 1) ? (static_cast<float>(Index) / (NumBladeSamples - 1)) : 0.f;
		OutPositions.Add(FMath::Lerp(Start, End, Alpha));
	}
}

void UAstralAbilityTask_AttackTraceWindows::TickTask(float DeltaTime)
{
	Super::TickTask(DeltaTime);

	if (State != EWindowState::Tracing)
	{
		return;
	}

	AActor* Avatar = GetAvatarActor();
	UWorld* World = Avatar ? Avatar->GetWorld() : nullptr;
	if (!World || !CurrentWeaponActor)
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
		Params.AddIgnoredActor(CurrentWeaponActor);

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
					FAstralAttackTraceHit HitContext;
					HitContext.HitResult = Hit;
					HitContext.EffectCauser = CurrentWeaponActor;
					HitContext.WindowSerial = WindowSerial;
					OnHitTarget.Broadcast(HitContext);
				}
			}
		}
	}

	PrevSamplePositions = MoveTemp(CurrentPositions);
	bHasPrevSamples = true;
}

void UAstralAbilityTask_AttackTraceWindows::OnDestroy(bool bInOwnerFinished)
{
	// GenericGameplayEventCallbacks 맵 엔트리는 ASC 수명이라 핸들 해제 필수
	if (UAbilitySystemComponent* ASC = AbilitySystemComponent.Get())
	{
		if (FGameplayEventMulticastDelegate* BeginDelegate = ASC->GenericGameplayEventCallbacks.Find(BeginEventTag))
		{
			BeginDelegate->Remove(BeginEventHandle);
		}
		if (FGameplayEventMulticastDelegate* EndDelegate = ASC->GenericGameplayEventCallbacks.Find(EndEventTag))
		{
			EndDelegate->Remove(EndEventHandle);
		}
	}

	HitActors.Reset();
	PrevSamplePositions.Reset();

	Super::OnDestroy(bInOwnerFinished);
}
