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
#include "Character/AstralCharacter.h"
#include "Character/Components/AstralHealthComponent.h"
#include "Character/Components/AstralLoadoutComponent.h"
#include "Character/Hero/Components/AstralHeroCameraComponent.h"
#include "Character/Hero/Components/AstralHeroComponent.h"
#include "Character/Hero/Components/AstralHeroMovementComponent.h"
#include "Character/Hero/Components/AstralTargetingComponent.h"
#include "GameModes/AstralHubGameState.h"
#include "Player/AstralPlayerState.h"

void UAstralDebugWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
    Super::NativeTick(MyGeometry, InDeltaTime);

    if (!DebugText)
    {
        return;
    }

    // 슬롯이 있는 섹션은 자기 TextBlock으로, 없으면 좌측 열에 이어 붙인다 (WBP가 1열 구성이어도 동작)
    TStringBuilder<2048> Main;
    Main.Append(BuildStatusString());

    if (LockOnText)
    {
        LockOnText->SetText(FText::FromString(BuildLockOnString()));
    }
    else
    {
        Main.Append(TEXT("\n"));
        Main.Append(BuildLockOnString());
    }

    if (PartyText)
    {
        PartyText->SetText(FText::FromString(BuildPartyString()));
    }
    else
    {
        Main.Append(TEXT("\n"));
        Main.Append(BuildPartyString());
    }

    DebugText->SetText(FText::FromString(Main.ToString()));
}

FString UAstralDebugWidget::BuildStatusString() const
{
    TStringBuilder<1024> B;
    B.Append(TEXT("=== AstralBreak Debug ===\n"));
    B.Appendf(TEXT("%s | %s / %s | Death: %s\n"), *GetNetModeString(), *GetRoleString(), *GetRemoteRoleString(), *GetDeathStateString());
    B.Append(TEXT("\n[Attributes]\n"));
    B.Append(GetAttributesString());
    B.Append(TEXT("\n[Movement]\n"));
    B.Append(GetMovementString());
    B.Append(TEXT("\n[Abilities]\n"));
    B.Append(GetAbilitiesString());
    return B.ToString();
}

FString UAstralDebugWidget::BuildLockOnString() const
{
    TStringBuilder<1024> B;
    B.Append(TEXT("[LockOn]\n"));
    B.Append(GetLockOnString());
    B.Append(TEXT("\n[Target]\n"));
    B.Append(GetTargetString());
    return B.ToString();
}

FString UAstralDebugWidget::BuildPartyString() const
{
    TStringBuilder<512> B;
    B.Append(TEXT("[Party]\n"));
    B.Append(GetPartyString());
    return B.ToString();
}

FString UAstralDebugWidget::GetPartyString() const
{
    TStringBuilder<512> B;

    const UWorld* World = GetWorld();
    B.Appendf(TEXT("Map: %s\n"), World ? *World->GetMapName() : TEXT("?"));

    const APlayerController* PC = GetOwningPlayer();
    const APawn* Pawn = PC ? PC->GetPawn() : nullptr;

    // 장비 복원 소스 — 서버 로컬 값이라 원격 클라에선 None (리슨 호스트/서버 시점용)
    if (const UAstralLoadoutComponent* LoadoutComp = Pawn ? Pawn->FindComponentByClass<UAstralLoadoutComponent>() : nullptr)
    {
        static const TCHAR* SourceNames[] = { TEXT("None"), TEXT("PartyCache"), TEXT("PlayerState"), TEXT("PawnDataFallback") };
        B.Appendf(TEXT("EquipSource: %s (서버 로컬)\n"), SourceNames[static_cast<int32>(LoadoutComp->GetLastLoadoutSource())]);
    }

    if (const AAstralPlayerState* AstralPS = PC ? PC->GetPlayerState<AAstralPlayerState>() : nullptr)
    {
        B.Appendf(TEXT("Character: %s\n"), *AstralPS->GetLoadout().CharacterId.ToString());
        for (const FPrimaryAssetId& ItemId : AstralPS->GetLoadout().Equipment)
        {
            B.Appendf(TEXT("  Equip: %s\n"), *ItemId.ToString());
        }
    }

    if (const AAstralGameState* GS = World ? World->GetGameState<AAstralGameState>() : nullptr)
    {
        // 로비 상태는 Hub 전용 GameState — Raid 맵에선 미표시
        if (const AAstralHubGameState* HubGS = Cast<AAstralHubGameState>(GS))
        {
            B.Appendf(TEXT("Raid: %s | AllReady: %s\n"), *HubGS->GetSelectedRaid().MapName, HubGS->AreAllPlayersReady() ? TEXT("YES") : TEXT("no"));
        }
        for (const APlayerState* PS : GS->PlayerArray)
        {
            const AAstralPlayerState* MemberPS = Cast<AAstralPlayerState>(PS);
            B.Appendf(TEXT("  %s: %s\n"), *GetNameSafe(PS), (MemberPS && MemberPS->IsReady()) ? TEXT("READY") : TEXT("..."));
        }
    }

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
    
    // 2줄 압축 — 1행: 체력·데미지 배율, 2행: 히어로 자원
    TStringBuilder<512> Out;
    if (const UAstralHealthSet* H = ASC->GetSet<UAstralHealthSet>())
    {
        Out.Appendf(TEXT("HP %.0f/%.0f  InDmg x%.2f"), H->GetHealth(), H->GetMaxHealth(), H->GetIncomingDamageMultiplier());
    }
    else
    {
        Out.Append(TEXT("(HealthSet not found)"));
    }

    if (const UAstralCombatSet* C = ASC->GetSet<UAstralCombatSet>())
    {
        Out.Appendf(TEXT("  OutDmg x%.2f"), C->GetOutgoingDamageMultiplier());
    }
    Out.Append(TEXT("\n"));

    if (const UAstralHeroResourceSet* R = ASC->GetSet<UAstralHeroResourceSet>())
    {
        Out.Appendf(TEXT("STM %.0f/%.0f  ULT %.0f/%.0f (x%.2f)  MARK %.0f/%.0f (x%.2f)  GRD x%.2f\n"),
            R->GetStamina(), R->GetMaxStamina(),
            R->GetUltGauge(), R->GetMaxUltGauge(), R->GetUltGainMultiplier(),
            R->GetMarkStack(), R->GetMaxMarkStack(), R->GetMarkGainMultiplier(),
            R->GetGuardDamageMultiplier());
    }
    else
    {
        Out.Append(TEXT("(HeroResourceSet not found — Hero PawnData 미등록?)\n"));
    }

    return Out.ToString();
}

FString UAstralDebugWidget::GetMovementString() const
{
    const APlayerController* PC = GetOwningPlayer();
    const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
    const UAstralHeroMovementComponent* HeroMC = Pawn ? Cast<UAstralHeroMovementComponent>(Pawn->GetMovementComponent()) : nullptr;
    if (!HeroMC)
    {
        return TEXT("(Hero MovementComponent 아님)\n");
    }

    // Want(클라 의도) / Auth(서버 GAS 승인)를 분리 표시 — 원격 클라의 서버 인스턴스에서
    // "Want=1 Auth=0 → MaxSpeed는 걷기"가 찍히면 권한 게이트가 동작한 것
    TStringBuilder<256> Out;
    Out.Appendf(TEXT("Sprint Want=%d Auth=%d Ground=%d -> %d | MaxSpeed %.0f (Vel %.0f, x%.2f)\n"),
        HeroMC->WantsToSprint() ? 1 : 0,
        HeroMC->IsSprintAuthorized() ? 1 : 0,
        HeroMC->IsMovingOnGround() ? 1 : 0,
        HeroMC->IsSprinting() ? 1 : 0,
        HeroMC->GetMaxSpeed(), HeroMC->Velocity.Size2D(), HeroMC->GetMoveSpeedMultiplier());

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

FString UAstralDebugWidget::GetLockOnString() const
{
    const APlayerController* PC = GetOwningPlayer();
    const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
    const UAstralTargetingComponent* Targeting = UAstralTargetingComponent::FindTargetingComponent(Pawn);
    if (!Targeting)
    {
        return TEXT("(no TargetingComponent)\n");
    }

    static const TCHAR* ModeNames[] = { TEXT("Idle"), TEXT("SoftTracking"), TEXT("HardLocked") };

    TStringBuilder<1024> Out;
    Out.Appendf(TEXT("Mode: %s\n"), ModeNames[static_cast<int32>(Targeting->GetMode())]);

    const FAstralTargetHandle& Target = Targeting->GetEffectiveTarget();
    if (Target.IsSet())
    {
        Out.Appendf(TEXT("Target: %s  LosLost: %.2fs\n"), *GetNameSafe(Target.TargetActor.Get()), Targeting->GetLosLostTime());
    }
    else
    {
        Out.Append(TEXT("Target: (none)\n"));
    }

    // 전환 입력 기계 — 스틱 latch · 마우스 무장 상태 · 마우스 누적(MouseAccumulationThreshold 실측용, thr=off면 누적만 한다).
    // mouse=REARM-WAIT는 전환 직후 멈춤(RearmPause)을 기다리는 중 — 그동안 입력은 버려진다
    if (const UAstralHeroComponent* Hero = UAstralHeroComponent::FindHeroComponent(Pawn))
    {
        static const TCHAR* LatchNames[] = { TEXT("Neutral"), TEXT("LatchedLeft"), TEXT("LatchedRight") };
        Out.Appendf(TEXT("Switch: latch=%s  mouse=%s"), LatchNames[static_cast<int32>(Hero->GetTargetCycleInputState())],
            Hero->IsMouseSwitchArmed() ? TEXT("armed") : TEXT("REARM-WAIT"));

        Out.Appendf(TEXT("  mouseAccum=%+.1f"), Hero->GetMouseSwitchAccumulation());
        const float WindowAge = Hero->GetMouseSwitchWindowAge();
        if (WindowAge >= 0.f)
        {
            Out.Appendf(TEXT(" (win %.2fs)"), WindowAge);
        }
        const float Age = Hero->GetMouseSwitchAccumulationAge();
        if (Age >= 0.f)
        {
            Out.Appendf(TEXT(" (idle %.2fs)"), Age);
        }

        const float Threshold = Hero->GetTargetSwitchParams().MouseAccumulationThreshold;
        if (Threshold > 0.f)
        {
            Out.Appendf(TEXT("  thr=%.1f\n"), Threshold);
        }
        else
        {
            Out.Append(TEXT("  thr=off\n"));
        }
    }

#if !UE_BUILD_SHIPPING
    // 카메라 관측 — 실제 카메라 POV 기준 오차·화면 투영, 락온 시점부터의 수렴 반감기 (보간 속도 튜닝용)
    const UAstralHeroCameraComponent* Camera = Pawn ? Pawn->FindComponentByClass<UAstralHeroCameraComponent>() : nullptr;
    if (Camera && Target.IsSet())
    {
        const FAstralLockOnCameraDebugStats& S = Camera->GetDebugStats();
        Out.Appendf(TEXT("Cam: d=%.0f  yawErr=%+.1f  pitchErr=%+.1f  screen=(%+.2f, %+.2f)%s\n"),
            S.Distance, S.YawErrorDeg, S.PitchErrorDeg, S.ScreenOffset.X, S.ScreenOffset.Y, S.bOnScreen ? TEXT("") : TEXT(" OFF"));
        if (S.YawHalfLifeSeconds >= 0.f)
        {
            Out.Appendf(TEXT("     t=%.2fs  init=%+.1f  halfLife=%.2fs\n"), S.ElapsedSinceLock, S.InitialYawErrorDeg, S.YawHalfLifeSeconds);
        }
        else
        {
            Out.Appendf(TEXT("     t=%.2fs  init=%+.1f  halfLife=--\n"), S.ElapsedSinceLock, S.InitialYawErrorDeg);
        }
    }
#endif

    // 후보 목록 — '*' 현재 타겟, '>' 지금 선정한다면 뽑힐 후보 (히스테리시스 포함). 둘이 다르면 임계가 교체를 막고 있는 것
    const AActor* Best = Targeting->GetDebugBestCandidate();
    const TArray<FAstralTargetCandidate>& Candidates = Targeting->GetDebugCandidates();
    Out.Appendf(TEXT("Candidates: %d\n"), Candidates.Num());
    for (const FAstralTargetCandidate& Candidate : Candidates)
    {
        const AActor* Actor = Candidate.Actor.Get();
        Out.Appendf(TEXT("  %s%s %s  d=%.0f  yaw=%+.1f  score=%.3f\n"),
            Candidate.bIsCurrentTarget ? TEXT("*") : TEXT(" "),
            (Actor && Actor == Best) ? TEXT(">") : TEXT(" "),
            *GetNameSafe(Actor), Candidate.Distance, Candidate.YawDeg, Candidate.Score);
    }

    return Out.ToString();
}