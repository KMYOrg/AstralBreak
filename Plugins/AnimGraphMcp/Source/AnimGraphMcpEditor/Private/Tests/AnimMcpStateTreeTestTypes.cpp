#include "AnimMcpStateTreeTestTypes.h"

#include "Abilities/GameplayAbility.h"
#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "AIController.h"
#include "Bridge/AnimMcpTypes.h"
#include "Components/ActorComponent.h"
#include "Core/AnimMcpStateTreeRuntime.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "StateTreeExecutionContext.h"
#include "StateTreeExecutionTypes.h"

namespace
{
	APawn* FindPawn(const FStateTreeExecutionContext& Context)
	{
		UObject* Owner = Context.GetOwner();
		const AAIController* Controller = Cast<AAIController>(Owner);
		return Controller ? Controller->GetPawn().Get() : Cast<APawn>(Owner);
	}

	/**
	 * 프로젝트의 ASC 결합이 끝났는가 — PawnExtension 이 ASC 를 쥐었는가. 플러그인이 프로젝트 모듈에 의존하지 않도록 이름으로 읽는다.
	 * ASC 자체로는 판단할 수 없다. 엔진이 InitializeComponent 에서 아바타를 소유 액터로 미리 채운다
	 */
	bool IsPawnExtensionBound(const APawn& Pawn)
	{
		for (const UActorComponent* Component : Pawn.GetComponents())
		{
			if (!Component || Component->GetFName() != TEXT("PawnExtComponent"))
			{
				continue;
			}
			const FObjectProperty* Property = CastField<FObjectProperty>(Component->GetClass()->FindPropertyByName(TEXT("AbilitySystemComponent")));
			return Property && Property->GetObjectPropertyValue_InContainer(Component) != nullptr;
		}
		return false;
	}

	TSharedRef<FJsonObject> MakeRecord(const FStateTreeExecutionContext& Context, const FAnimMcpLifecycleProbeInstanceData& Data, const TCHAR* Event)
	{
		TSharedRef<FJsonObject> Record = AnimMcpJson::MakeObject();
		Record->SetStringField(TEXT("event"), Event);
		Record->SetStringField(TEXT("label"), Data.Label);
		const UWorld* World = Context.GetWorld();
		Record->SetNumberField(TEXT("t"), World ? FMath::RoundToDouble(World->GetTimeSeconds() * 1000.0) / 1000.0 : -1.0);

		const APawn* Pawn = FindPawn(Context);
		Record->SetStringField(TEXT("pawn"), GetNameSafe(Pawn));
		const UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Pawn);
		Record->SetBoolField(TEXT("has_asc"), ASC != nullptr);
		Record->SetBoolField(TEXT("avatar_is_pawn"), ASC && Pawn && ASC->GetAvatarActor() == Pawn);
		Record->SetBoolField(TEXT("pawn_ext_bound"), Pawn && IsPawnExtensionBound(*Pawn));
		Record->SetNumberField(TEXT("abilities"), ASC ? ASC->GetActivatableAbilities().Num() : 0);
		return Record;
	}
}

FAnimMcpLifecycleProbeTask::FAnimMcpLifecycleProbeTask()
{
	bShouldCallTick = false;
}

EStateTreeRunStatus FAnimMcpLifecycleProbeTask::EnterState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const
{
	const FInstanceDataType& Data = Context.GetInstanceData<FInstanceDataType>(*this);
	TSharedRef<FJsonObject> Record = MakeRecord(Context, Data, TEXT("enter"));
	if (!Data.AbilityPath.IsEmpty())
	{
		UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(FindPawn(Context));
		const TSubclassOf<UGameplayAbility> Ability = LoadClass<UGameplayAbility>(nullptr, *Data.AbilityPath);
		Record->SetStringField(TEXT("try_ability"), Data.AbilityPath);
		Record->SetBoolField(TEXT("ability_class_found"), Ability != nullptr);
		Record->SetBoolField(TEXT("activated"), ASC && Ability && ASC->TryActivateAbilityByClass(Ability));
	}
	AnimMcpStateTreeRuntime::AddProbeRecord(Record);
	return EStateTreeRunStatus::Running;
}

void FAnimMcpLifecycleProbeTask::ExitState(FStateTreeExecutionContext& Context, const FStateTreeTransitionResult& Transition) const
{
	const FInstanceDataType& Data = Context.GetInstanceData<FInstanceDataType>(*this);
	TSharedRef<FJsonObject> Record = MakeRecord(Context, Data, TEXT("exit"));
	Record->SetStringField(TEXT("status"), StaticEnum<EStateTreeRunStatus>()->GetNameStringByValue(static_cast<int64>(Transition.CurrentRunStatus)));
	AnimMcpStateTreeRuntime::AddProbeRecord(Record);
}
