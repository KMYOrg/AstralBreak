#pragma once

#include "CoreMinimal.h"
#include "GameplayEffectExecutionCalculation.h"
#include "AstralDamageExecution.generated.h"

/**
 * UAstralDamageExecution
 *  Damage 공식: Final = SetByCaller(Damage) × Source.OutgoingDmgMul × Target.IncomingDmgMul
 *  Output: HealthSet.Damage(meta) Add — PostGameplayEffectExecute가 Health에 반영
 */
UCLASS()
class ASTRALBREAK_API UAstralDamageExecution : public UGameplayEffectExecutionCalculation
{
	GENERATED_BODY()
	
public:
	UAstralDamageExecution();

	virtual void Execute_Implementation(const FGameplayEffectCustomExecutionParameters& ExecutionParams, FGameplayEffectCustomExecutionOutput& OutExecutionOutput) const override;
};
