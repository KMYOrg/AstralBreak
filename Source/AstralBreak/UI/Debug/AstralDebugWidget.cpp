#include "AstralDebugWidget.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystemGlobals.h"
#include "Components/TextBlock.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "Engine/World.h"
#include "AbilitySystem/Attributes/AstralHealthSet.h"
#include "AbilitySystem/Attributes/AstralCombatSet.h"
#include "AbilitySystem/Attributes/Hero/AstralHeroResourceSet.h"

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
    B.Append(TEXT("\n[Attributes]\n"));
    B.Append(GetAttributesString());
    B.Append(TEXT("\n[Abilities]\n"));
    B.Append(GetAbilitiesString());
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
        Out.Appendf(TEXT("ULT: %.0f / %.0f\n"), R->GetUltGauge(), R->GetMaxUltGauge());
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