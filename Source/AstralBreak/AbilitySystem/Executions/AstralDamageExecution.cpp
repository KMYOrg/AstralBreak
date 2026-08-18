#include "AstralDamageExecution.h"

#include "AstralGameplayTags.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Attributes/AstralCombatSet.h"
#include "AbilitySystem/Effects/AstralSetByCallerGameplayTags.h"

struct FAstralDamageStatics
{
    FGameplayEffectAttributeCaptureDefinition IncomingDamageMultiplierDef;
    FGameplayEffectAttributeCaptureDefinition OutgoingDamageMultiplierDef;

    FAstralDamageStatics()
    {
        IncomingDamageMultiplierDef = FGameplayEffectAttributeCaptureDefinition(UAstralHealthSet::GetIncomingDamageMultiplierAttribute(), EGameplayEffectAttributeCaptureSource::Target, false);
        OutgoingDamageMultiplierDef = FGameplayEffectAttributeCaptureDefinition(UAstralCombatSet::GetOutgoingDamageMultiplierAttribute(), EGameplayEffectAttributeCaptureSource::Source, false);
    }
};

static const FAstralDamageStatics& DamageStatics()
{
    static FAstralDamageStatics Statics;
    return Statics;
}

UAstralDamageExecution::UAstralDamageExecution()
{
    RelevantAttributesToCapture.Add(DamageStatics().IncomingDamageMultiplierDef);
    RelevantAttributesToCapture.Add(DamageStatics().OutgoingDamageMultiplierDef);
}

void UAstralDamageExecution::Execute_Implementation(const FGameplayEffectCustomExecutionParameters& ExecutionParams, FGameplayEffectCustomExecutionOutput& OutExecutionOutput) const
{
    const FGameplayEffectSpec& Spec = ExecutionParams.GetOwningSpec();
    FAggregatorEvaluateParameters EvalParams;
    EvalParams.SourceTags = Spec.CapturedSourceTags.GetAggregatedTags();
    EvalParams.TargetTags = Spec.CapturedTargetTags.GetAggregatedTags();

    float IncomingMul = 1.f;
    float OutgoingMul = 1.f;
    ExecutionParams.AttemptCalculateCapturedAttributeMagnitude(DamageStatics().IncomingDamageMultiplierDef, EvalParams, IncomingMul);
    ExecutionParams.AttemptCalculateCapturedAttributeMagnitude(DamageStatics().OutgoingDamageMultiplierDef, EvalParams, OutgoingMul);

    IncomingMul = FMath::Max(IncomingMul, 0.f);
    OutgoingMul = FMath::Max(OutgoingMul, 0.f);

    // SetByCaller로 GA가 주입한 BaseDamage
    const FGameplayTag DamageTag = AstralGameplayTags::SetByCaller_Damage;
    const float BaseDamage = Spec.GetSetByCallerMagnitude(DamageTag, false, 0.f);

    const float FinalDamage = FMath::Max(BaseDamage * OutgoingMul * IncomingMul, 0.f);

    if (FinalDamage > 0.f)
    {
        OutExecutionOutput.AddOutputModifier(FGameplayModifierEvaluatedData(UAstralHealthSet::GetDamageAttribute(), EGameplayModOp::Additive, FinalDamage));
    }
}