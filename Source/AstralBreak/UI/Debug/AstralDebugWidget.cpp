#include "AstralDebugWidget.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "Components/TextBlock.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Engine/World.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Attributes/AstralCombatSet.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"
#include "Character/Components/AstralHealthComponent.h"

void UAstralDebugWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
    Super::NativeTick(MyGeometry, InDeltaTime);
    if (DebugText)
    {
        DebugText->SetText(FText::FromString(BuildDebugString()));
    }
}

FString UAstralDebugWidget::BuildDebugString() const
{
    TStringBuilder<2048> B;
    B.Append(TEXT("=== AstralBreak Debug ===\n"));
    B.Appendf(TEXT("NetMode:  %s\n"),  *GetNetModeString());
    B.Appendf(TEXT("Role:     %s\n"),  *GetRoleString());
    B.Appendf(TEXT("Remote:   %s\n"),  *GetRemoteRoleString());
    B.Appendf(TEXT("Death:    %s\n"), *GetDeathStateString());
    B.Append(TEXT("\n[Attributes]\n"));
    B.Append(GetAttributesString());
    B.Append(TEXT("\n[Abilities]\n"));
    B.Append(GetAbilitiesString());
    B.Append(TEXT("\n[Target]\n"));
    B.Append(GetTargetString());
    return B.ToString();
}

FString UAstralDebugWidget::GetNetModeString() const
{
    if (UWorld* World = GetWorld())
    {
        switch (World->GetNetMode())
        {
        case NM_Standalone:      return TEXT("Standalone");
        case NM_DedicatedServer: return TEXT("DedicatedServer");
        case NM_ListenServer:    return TEXT("ListenServer");
        case NM_Client:          return TEXT("Client");
        default: break;
        }
    }
    return TEXT("Unknown");
}

static FString RoleToString(ENetRole Role)
{
    switch (Role)
    {
    case ROLE_Authority:       return TEXT("Authority");
    case ROLE_AutonomousProxy: return TEXT("AutonomousProxy");
    case ROLE_SimulatedProxy:  return TEXT("SimulatedProxy");
    case ROLE_None:            return TEXT("None");
    default:                   return TEXT("Unknown");
    }
}

FString UAstralDebugWidget::GetRoleString() const
{
    APlayerController* PC = GetOwningPlayer();
    APawn* Pawn = PC ? PC->GetPawn() : nullptr;
    if (!Pawn)
    {
        return TEXT("NoPawn");
    }
    return RoleToString(Pawn->GetLocalRole());
}

FString UAstralDebugWidget::GetRemoteRoleString() const
{
    APlayerController* PC = GetOwningPlayer();
    APawn* Pawn = PC ? PC->GetPawn() : nullptr;
    if (!Pawn)
    {
        return TEXT("NoPawn");
    }
    return RoleToString(Pawn->GetRemoteRole());
}

FString UAstralDebugWidget::GetAttributesString() const
{
    APlayerController* PC = GetOwningPlayer();
    APawn* Pawn = PC ? PC->GetPawn() : nullptr;
    if (!Pawn)
    {
        return TEXT("NoPawn\n");
    }
    UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Pawn);
    if (!ASC)
    {
        return TEXT("NoASC\n");
    }
    
    TStringBuilder<512> Out;
    if (const UAstralHealthSet* H = ASC->GetSet<UAstralHealthSet>())
    {
        Out.Appendf(TEXT("HP:        %.0f / %.0f\n"), H->GetHealth(),    H->GetMaxHealth());
        Out.Appendf(TEXT("InDmgMul:  %.2f\n"),         H->GetIncomingDamageMultiplier());
    }
    else
    {
        Out.Append(TEXT("(HealthSet not found)\n"));
    }

    if (const UAstralCombatSet* C = ASC->GetSet<UAstralCombatSet>())
    {
        Out.Appendf(TEXT("OutDmgMul: %.2f\n"), C->GetOutgoingDamageMultiplier());
    }

    if (const UAstralHeroResourceSet* R = ASC->GetSet<UAstralHeroResourceSet>())
    {
        Out.Appendf(TEXT("STM: %.0f / %.0f\n"), R->GetStamina(),  R->GetMaxStamina());
        Out.Appendf(TEXT("ULT: %.0f / %.0f (Mul %.2f)\n"), R->GetUltGauge(), R->GetMaxUltGauge(), R->GetUltGainMultiplier());
    }
    else
    {
        Out.Append(TEXT("(HeroResourceSet not found — Hero PawnData 미등록?)\n"));
    }

    return Out.ToString();
}

FString UAstralDebugWidget::GetAbilitiesString() const
{
    APlayerController* PC = GetOwningPlayer();
    APawn* Pawn = PC ? PC->GetPawn() : nullptr;
    if (!Pawn)
    {
        return TEXT("NoPawn\n");
    }
    UAbilitySystemComponent* ASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Pawn);
    if (!ASC)
    {
        return TEXT("NoASC\n");
    }
    TStringBuilder<512> Out;
    Out.Appendf(TEXT("Activatable: %d\n"), ASC->GetActivatableAbilities().Num());

    FGameplayTagContainer Tags;
    ASC->GetOwnedGameplayTags(Tags);
    if (Tags.Num() > 0)
    {
        Out.Appendf(TEXT("Tags: %s\n"), *Tags.ToStringSimple());
    }
    else
    {
        Out.Append(TEXT("Tags: (none)\n"));
    }

    return Out.ToString();
}

FString UAstralDebugWidget::GetDeathStateString() const
{
    APlayerController* PC = GetOwningPlayer();
    APawn* Pawn = PC ? PC->GetPawn() : nullptr;
    const UAstralHealthComponent* HealthComponent = UAstralHealthComponent::FindHealthComponent(Pawn);
    if (!HealthComponent)
    {
        return TEXT("NoHealthComp");
    }

    switch (HealthComponent->GetDeathState())
    {
    case EAstralDeathState::NotDead:       return TEXT("NotDead");
    case EAstralDeathState::DeathStarted:  return TEXT("DeathStarted");
    case EAstralDeathState::DeathFinished: return TEXT("DeathFinished");
    default:                               return TEXT("Unknown");
    }
}

FString UAstralDebugWidget::GetTargetString() const
{
    APlayerController* PC = GetOwningPlayer();
    APawn* Pawn = PC ? PC->GetPawn() : nullptr;
    UWorld* World = GetWorld();
    if (!PC || !Pawn || !World)
    {
        return TEXT("(no view)\n");
    }

    // 조준선 트레이스 — 카메라 기준 전방
    FVector ViewLocation;
    FRotator ViewRotation;
    PC->GetPlayerViewPoint(ViewLocation, ViewRotation);

    const FVector TraceStart = ViewLocation;
    const FVector TraceEnd = TraceStart + ViewRotation.Vector() * 5000.0f;

    FCollisionQueryParams Params(SCENE_QUERY_STAT(DebugWidget_TargetTrace), false);
    Params.AddIgnoredActor(Pawn);

    FHitResult Hit;
    if (!World->LineTraceSingleByChannel(Hit, TraceStart, TraceEnd, ECC_Pawn, Params) || !Hit.GetActor())
    {
        return TEXT("(none)\n");
    }

    const AActor* Target = Hit.GetActor();

    TStringBuilder<256> Out;
    Out.Appendf(TEXT("%s\n"), *GetNameSafe(Target));
    Out.Appendf(TEXT("Team: %d  CanDamage: %s  Dead: %s\n"),
        UAstralCombatStatics::GetTeamIdAsInt(Target),
        UAstralCombatStatics::CanDamage(Pawn, Target) ? TEXT("Y") : TEXT("N"),
        UAstralCombatStatics::IsDeadOrDying(Target) ? TEXT("Y") : TEXT("N"));

    if (const UAbilitySystemComponent* TargetASC = UAbilitySystemGlobals::GetAbilitySystemComponentFromActor(Target))
    {
        if (const UAstralHealthSet* TargetHealth = TargetASC->GetSet<UAstralHealthSet>())
        {
            Out.Appendf(TEXT("HP: %.0f / %.0f\n"), TargetHealth->GetHealth(), TargetHealth->GetMaxHealth());
        }
    }

    return Out.ToString();
}