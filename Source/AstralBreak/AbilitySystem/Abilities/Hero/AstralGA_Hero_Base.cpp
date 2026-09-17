// Fill out your copyright notice in the Description page of Project Settings.


#include "AstralGA_Hero_Base.h"

#include "AbilitySystemComponent.h"
#include "AbilitySystem/AstralCombatStatics.h"
#include "AstralLogChannels.h"
#include "Character/Components/AstralCharacterMovementComponent.h"
#include "Character/Hero/AstralCharacter_Hero.h"
#include "Character/Hero/Components/AstralTargetingComponent.h"
#include "Combat/AstralCombatTypes.h"
#include "Combat/AstralTargetingStatics.h"
#include "GameFramework/Character.h"
#include "System/AstralGameData.h"

#if !UE_BUILD_SHIPPING
#include "HAL/IConsoleManager.h"

namespace AstralFacingDebug
{
	/** 이 단계의 Facing 송신을 생략 (-1 = 끔). 0이면 활성화 이벤트에 빈 페이로드를 싣는다 — "미수신"을 Reliable RPC 손실과 구분해 재현 */
	static int32 DropSendStage = -1;
	static FAutoConsoleVariableRef CVarDropSendStage(TEXT("Astral.Facing.Debug.DropSendStage"), DropSendStage,
		TEXT("Facing TargetData 송신을 생략할 StageIndex (-1 = off). 서버 NoWarp_Missing 재현용"), ECVF_Cheat);

	/** Stage 1~N 송신을 두 번 — 중복 수신 분류 확인 */
	static int32 DuplicateSend = 0;
	static FAutoConsoleVariableRef CVarDuplicateSend(TEXT("Astral.Facing.Debug.DuplicateSend"), DuplicateSend,
		TEXT("1이면 Stage 1~N Facing TargetData를 두 번 보낸다 (DuplicateIgnored 확인용)"), ECVF_Cheat);

	/** 카운터 — 정상 승인 경로와 예외 경로를 분리해 본다 */
	struct FStats
	{
		int32 Sent = 0;
		int32 Received = 0;
		int32 StoredEarly = 0;
		int32 Approved = 0;
		int32 ExplicitNone = 0;
		int32 Missing = 0;
		int32 Rejected = 0;
		int32 Duplicate = 0;
		int32 Conflict = 0;
		int32 StageMismatch = 0;
		int32 AfterSession = 0;

		void Reset() { *this = FStats(); }
		FString ToString() const
		{
			return FString::Printf(TEXT("Sent=%d Received=%d StoredEarly=%d Approved=%d ExplicitNone=%d Missing=%d Rejected=%d Duplicate=%d Conflict=%d StageMismatch=%d AfterSession=%d"),
				Sent, Received, StoredEarly, Approved, ExplicitNone, Missing, Rejected, Duplicate, Conflict, StageMismatch, AfterSession);
		}
	};
	static FStats Stats;

	static FAutoConsoleCommand CmdDumpStats(TEXT("Astral.Facing.DumpStats"), TEXT("Facing 전달 카운터 출력"),
		FConsoleCommandDelegate::CreateLambda([]() { UE_LOG(LogAstralAbilitySystem, Display, TEXT("[Facing] Stats: %s"), *Stats.ToString()); }));
	static FAutoConsoleCommand CmdResetStats(TEXT("Astral.Facing.ResetStats"), TEXT("Facing 전달 카운터 초기화"),
		FConsoleCommandDelegate::CreateLambda([]() { Stats.Reset(); }));
}
#define ASTRAL_FACING_STAT(Field) (++AstralFacingDebug::Stats.Field)
#else
#define ASTRAL_FACING_STAT(Field)
#endif

UAstralGA_Hero_Base::UAstralGA_Hero_Base(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

//////////////////////////////////////////////////////////////////////////
// 타게팅 바인딩

FAstralTargetHandle UAstralGA_Hero_Base::ResolveEffectiveTarget() const
{
	// GetAstralCharacterFromActorInfo는 베이스(AAstralCharacter)를 돌려주므로 히어로 캐스트는 여기서
	const AAstralCharacter_Hero* Hero = Cast<AAstralCharacter_Hero>(GetAvatarActorFromActorInfo());
	const UAstralTargetingComponent* Targeting = Hero ? Hero->GetTargetingComponent() : nullptr;
	return Targeting ? Targeting->GetEffectiveTarget() : FAstralTargetHandle();
}

FRotator UAstralGA_Hero_Base::ComputeFacingToward(const FVector& AimLocation) const
{
	const AActor* Avatar = GetAvatarActorFromActorInfo();
	if (!Avatar)
	{
		return FRotator::ZeroRotator;
	}

	const float CurrentYaw = Avatar->GetActorRotation().Yaw;
	const float DesiredYaw = AstralTargeting::ComputeFacingYaw(Avatar->GetActorLocation(), AimLocation, CurrentYaw);
	return FRotator(0.f, DesiredYaw, 0.f);
}

//////////////////////////////////////////////////////////////////////////
// Facing 세션

FAstralFacingProposal UAstralGA_Hero_Base::CaptureFacingProposal(const AActor* Avatar, int32 StageIndex) const
{
	FAstralFacingProposal Proposal = FAstralFacingProposal::MakeNone(static_cast<uint8>(StageIndex));

	const AAstralCharacter_Hero* Hero = Cast<AAstralCharacter_Hero>(Avatar);
	const UAstralTargetingComponent* Targeting = Hero ? Hero->GetTargetingComponent() : nullptr;
	if (!Targeting)
	{
		return Proposal;
	}

	const FAstralTargetHandle& Target = Targeting->GetEffectiveTarget();
	if (!Target.IsSet())
	{
		return Proposal;
	}

	const float CurrentYaw = Avatar->GetActorRotation().Yaw;
	const float DesiredYaw = AstralTargeting::ComputeFacingYaw(Avatar->GetActorLocation(), Target.GetAimLocation(), CurrentYaw);

	Proposal.Source = EAstralFacingSource::LockOn;
	Proposal.TargetActor = Target.TargetActor;
	Proposal.TargetPointId = NAME_None; // M5까지 부위 없음
	Proposal.QuantizedDesiredYaw = AstralFacing::QuantizeYaw(DesiredYaw);
	return Proposal;
}

bool UAstralGA_Hero_Base::MakeActivationEventData(const FGameplayAbilityActorInfo& ActorInfo, FGameplayEventData& OutEventData) const
{
	if (!UsesFacingWarp())
	{
		return false;
	}

	const AActor* Avatar = ActorInfo.AvatarActor.Get();
	if (!Avatar)
	{
		return false;
	}

	OutEventData.Instigator = Avatar;
	OutEventData.Target = Avatar;

#if !UE_BUILD_SHIPPING
	if (AstralFacingDebug::DropSendStage == 0)
	{
		// 이벤트 경로는 유지하되 페이로드만 비운다 — 서버는 Missing, 로컬은 BeginFacingSession의 폴백 캡처로 워프 → 불일치 재현
		return true;
	}
#endif

	const FAstralFacingProposal Proposal = CaptureFacingProposal(Avatar, 0);
	OutEventData.TargetData = FGameplayAbilityTargetData_AstralFacing::MakeHandle(Proposal);
	ASTRAL_FACING_STAT(Sent);
	return true;
}

bool UAstralGA_Hero_Base::IsRemoteServerInstance() const
{
	return CurrentActorInfo && CurrentActorInfo->IsNetAuthority() && !CurrentActorInfo->IsLocallyControlled();
}

void UAstralGA_Hero_Base::BeginFacingSession(const FGameplayEventData* TriggerEventData)
{
	if (!UsesFacingWarp() || !CurrentActorInfo)
	{
		return;
	}

	UAbilitySystemComponent* ASC = CurrentActorInfo->AbilitySystemComponent.Get();
	if (!ASC)
	{
		return;
	}

	// 늦은 종료·콜백이 새 활성화를 지우지 않도록 이 활성화의 키를 저장한다
	FacingSessionSpecHandle = CurrentSpecHandle;
	FacingSessionKey = CurrentActivationInfo.GetActivationPredictionKey();
	bFacingSessionActive = true;
	FacingInbox.Reset(GetFacingStageCount());

	// Stage 0 — 활성화 이벤트에서. 로컬도 같은 페이로드를 읽어 서버와 같은 양자화 값을 쓴다
	FAstralFacingProposal StageZero;
	bool bHasStageZero = TriggerEventData && FGameplayAbilityTargetData_AstralFacing::ExtractProposal(TriggerEventData->TargetData, GetFacingStageCount(), StageZero);

	if (!bHasStageZero && !IsRemoteServerInstance())
	{
		// 로컬 폴백 — 이벤트 경로 밖의 활성화(디버그 훅·다른 호출자). 서버는 폴백하지 않는다 (승인 스냅샷만)
		StageZero = CaptureFacingProposal(CurrentActorInfo->AvatarActor.Get(), 0);
		bHasStageZero = true;
	}

	if (bHasStageZero)
	{
		const EAstralFacingReceiveResult Result = FacingInbox.Receive(StageZero);
		UE_LOG(LogAstralAbilitySystem, Verbose, TEXT("[Facing] %s Stage0 from event: %s"), *GetName(), AstralFacing::ToString(Result));
	}

	// 원격 폰의 서버 인스턴스 — Stage 1~N 수신기. 등록 전 도착분(활성화 직후 캐시)도 회수
	if (IsRemoteServerInstance())
	{
		FacingTargetDataDelegateHandle = ASC->AbilityTargetDataSetDelegate(FacingSessionSpecHandle, FacingSessionKey)
			.AddUObject(this, &ThisClass::HandleFacingTargetDataReceived);
		ASC->CallReplicatedTargetDataDelegatesIfSet(FacingSessionSpecHandle, FacingSessionKey);
	}
}

void UAstralGA_Hero_Base::HandleFacingTargetDataReceived(const FGameplayAbilityTargetDataHandle& DataHandle, FGameplayTag ApplicationTag)
{
	UAbilitySystemComponent* ASC = CurrentActorInfo ? CurrentActorInfo->AbilitySystemComponent.Get() : nullptr;

	// 핸들을 먼저 로컬 복사 — 캐시 소비 후에도 데이터를 쓸 수 있게 
	const FGameplayAbilityTargetDataHandle LocalHandle = DataHandle;
	if (ASC)
	{
		ASC->ConsumeClientReplicatedTargetData(FacingSessionSpecHandle, FacingSessionKey);
	}

	ASTRAL_FACING_STAT(Received);

	if (!bFacingSessionActive)
	{
		ASTRAL_FACING_STAT(AfterSession);
		UE_LOG(LogAstralAbilitySystem, Verbose, TEXT("[Facing] %s: 세션 종료 후 수신 — 폐기"), *GetName());
		return;
	}

	FAstralFacingProposal Proposal;
	if (!FGameplayAbilityTargetData_AstralFacing::ExtractProposal(LocalHandle, GetFacingStageCount(), Proposal))
	{
		ASTRAL_FACING_STAT(Rejected);
		UE_LOG(LogAstralAbilitySystem, Warning, TEXT("[Facing] %s: 구조 검증 실패 (payload=%d) — 폐기"), *GetName(), LocalHandle.Num());
		return;
	}

	const EAstralFacingReceiveResult Result = FacingInbox.Receive(Proposal);
	switch (Result)
	{
	case EAstralFacingReceiveResult::StoredNext:     ASTRAL_FACING_STAT(StoredEarly); break;
	case EAstralFacingReceiveResult::DuplicateIgnored: ASTRAL_FACING_STAT(Duplicate); break;
	case EAstralFacingReceiveResult::ConflictIgnored:  ASTRAL_FACING_STAT(Conflict); break;
	default: break;
	}

	UE_LOG(LogAstralAbilitySystem, Log, TEXT("[Facing] Role=Server Spec=%s Key=%d Stage=%d Source=%s Yaw=%u ServerStage=%d Receive=%s"),
		*GetName(), FacingSessionKey.Current, Proposal.StageIndex, AstralFacing::ToString(Proposal.Source), Proposal.QuantizedDesiredYaw,
		FacingInbox.GetCurrentStage(), AstralFacing::ToString(Result));
}

EAstralFacingRejectReason UAstralGA_Hero_Base::ValidateFacingProposal(const FAstralFacingProposal& Proposal) const
{
	const AActor* Avatar = GetAvatarActorFromActorInfo();
	const AActor* Target = Proposal.TargetActor.Get();
	if (!Avatar || !Target)
	{
		return EAstralFacingRejectReason::InvalidTarget;
	}
	if (Target == Avatar)
	{
		return EAstralFacingRejectReason::SelfTarget;
	}
	// 락온과 같은 게임플레이 판정 (아군·시체 락온 차단). 충돌 정책의 AreHostile과는 다른 축
	if (!UAstralCombatStatics::CanDamage(Avatar, Target))
	{
		return EAstralFacingRejectReason::CannotDamage;
	}

	// 서버 방위는 검증에만 — 재계산하면 클라와 미세하게 달라져 발산이 되살아난다
	const float Distance2D = FVector::Dist2D(Avatar->GetActorLocation(), Target->GetActorLocation());
	const float ServerBearing = AstralTargeting::ComputeFacingYaw(Avatar->GetActorLocation(), Target->GetActorLocation(), Avatar->GetActorRotation().Yaw);
	return AstralFacing::ValidateBearing(Distance2D, ServerBearing, AstralFacing::DequantizeYaw(Proposal.QuantizedDesiredYaw));
}

EAstralFacingDecision UAstralGA_Hero_Base::ResolveFacingForStage(int32 StageIndex, FName WarpTargetName)
{
	if (!UsesFacingWarp() || !CurrentActorInfo)
	{
		return EAstralFacingDecision::NoWarp_Missing;
	}

	TOptional<FAstralFacingProposal> Proposal;
	EAstralFacingRejectReason Reason = EAstralFacingRejectReason::None;

	if (IsRemoteServerInstance())
	{
		// 승인 경로 — 보관함에서만. 서버의 로컬 TargetingComponent 조회 금지
		if (!FacingInbox.BeginStage(StageIndex))
		{
			ASTRAL_FACING_STAT(StageMismatch);
			UE_LOG(LogAstralAbilitySystem, Warning, TEXT("[Facing] %s: 단계 불일치 — 보관함 %d → 요청 %d (슬롯 초기화)"), *GetName(), FacingInbox.GetCurrentStage(), StageIndex);
		}
		Proposal = FacingInbox.TakeCurrent();
	}
	else
	{
		if (StageIndex == 0)
		{
			// 활성화 이벤트에서 보관함에 넣어 둔 값 — 서버와 같은 양자화 값
			FacingInbox.BeginStage(0);
			Proposal = FacingInbox.TakeCurrent();
		}
		else
		{
			// Stage 1~N — 단계 시작 직전 캡처 (예약 입력 시점 캡처는 조작감을 내준다 — 채택하지 않음)
			Proposal = CaptureFacingProposal(CurrentActorInfo->AvatarActor.Get(), StageIndex);

			// 비권위면 서버로 — 활성화 키로 캐시되며 서버 수신기가 같은 키로 듣는다
			if (!CurrentActorInfo->IsNetAuthority())
			{
				bool bSend = true;
#if !UE_BUILD_SHIPPING
				bSend = (AstralFacingDebug::DropSendStage != StageIndex);
#endif
				if (UAbilitySystemComponent* ASC = CurrentActorInfo->AbilitySystemComponent.Get(); ASC && bSend)
				{
					const FGameplayAbilityTargetDataHandle SendHandle = FGameplayAbilityTargetData_AstralFacing::MakeHandle(*Proposal);
					FScopedPredictionWindow ScopedPrediction(ASC);
					ASC->CallServerSetReplicatedTargetData(FacingSessionSpecHandle, FacingSessionKey, SendHandle, FGameplayTag(), ASC->ScopedPredictionKey);
					ASTRAL_FACING_STAT(Sent);
#if !UE_BUILD_SHIPPING
					if (AstralFacingDebug::DuplicateSend != 0)
					{
						ASC->CallServerSetReplicatedTargetData(FacingSessionSpecHandle, FacingSessionKey, SendHandle, FGameplayTag(), ASC->ScopedPredictionKey);
					}
#endif
				}
			}
		}
	}

	// 확정 — 이 단계에서 다시 바꾸지 않는다
	EAstralFacingDecision Decision;
	if (!Proposal.IsSet())
	{
		Decision = EAstralFacingDecision::NoWarp_Missing;
		ASTRAL_FACING_STAT(Missing);
	}
	else if (Proposal->IsNone())
	{
		Decision = EAstralFacingDecision::NoWarp_ExplicitNone;
		ASTRAL_FACING_STAT(ExplicitNone);
	}
	else
	{
		// 월드 검증은 원격 입력에만 — 호스트·자율 프록시는 자기 캡처를 그대로 쓴다
		Reason = IsRemoteServerInstance() ? ValidateFacingProposal(*Proposal) : EAstralFacingRejectReason::None;
		if (Reason == EAstralFacingRejectReason::None)
		{
			Decision = EAstralFacingDecision::Warp;
			ASTRAL_FACING_STAT(Approved);
		}
		else
		{
			Decision = EAstralFacingDecision::NoWarp_Rejected;
			ASTRAL_FACING_STAT(Rejected);
		}
	}

	if (Decision == EAstralFacingDecision::Warp)
	{
		// 승인 아니면 NoWarp — 서버 clamp는 양쪽 누구도 갖지 않은 제3의 방향을 만든다
		FAstralFacingWarpCommand Command;
		Command.WarpTargetName = WarpTargetName;
		Command.DesiredFacing = FRotator(0.f, AstralFacing::DequantizeYaw(Proposal->QuantizedDesiredYaw), 0.f);
		SetFacingWarp(Command);
	}
	else
	{
		// NoWarp 확정은 자기 이름을 제거한다 — 이전 활성화의 같은 이름이 남아 있을 수 있다
		ClearFacingWarp(WarpTargetName);
	}

	LogFacingDecision(StageIndex, WarpTargetName, Proposal.GetPtrOrNull(), Decision, Reason);
	return Decision;
}

void UAstralGA_Hero_Base::EndFacingSession()
{
	if (!bFacingSessionActive)
	{
		return;
	}
	bFacingSessionActive = false;

	if (UAbilitySystemComponent* ASC = CurrentActorInfo ? CurrentActorInfo->AbilitySystemComponent.Get() : nullptr)
	{
		if (FacingTargetDataDelegateHandle.IsValid())
		{
			ASC->AbilityTargetDataSetDelegate(FacingSessionSpecHandle, FacingSessionKey).Remove(FacingTargetDataDelegateHandle);
		}
		// 이 활성화의 pending/캐시 소비 — 다음 활성화가 이전 키 데이터를 보지 않도록
		ASC->ConsumeClientReplicatedTargetData(FacingSessionSpecHandle, FacingSessionKey);
	}

	FacingTargetDataDelegateHandle.Reset();
	FacingInbox.Reset(0);
	FacingSessionSpecHandle = FGameplayAbilitySpecHandle();
	FacingSessionKey = FPredictionKey();
}

void UAstralGA_Hero_Base::LogFacingDecision(int32 StageIndex, FName WarpTargetName, const FAstralFacingProposal* Proposal, EAstralFacingDecision Decision, EAstralFacingRejectReason Reason) const
{
#if !UE_BUILD_SHIPPING
	const TCHAR* Role = IsRemoteServerInstance() ? TEXT("Server") : (CurrentActorInfo && CurrentActorInfo->IsNetAuthority() ? TEXT("Host") : TEXT("Client"));

	float MontagePosition = -1.f;
	const TCHAR* Policy = TEXT("-");
	if (const ACharacter* Character = Cast<ACharacter>(GetAvatarActorFromActorInfo()))
	{
		if (const UAnimInstance* AnimInstance = Character->GetMesh() ? Character->GetMesh()->GetAnimInstance() : nullptr)
		{
			if (const UAnimMontage* Current = AnimInstance->GetCurrentActiveMontage())
			{
				MontagePosition = AnimInstance->Montage_GetPosition(Current);
			}
		}
		if (const UAstralCharacterMovementComponent* MC = Cast<UAstralCharacterMovementComponent>(Character->GetCharacterMovement()))
		{
			Policy = (MC->GetAuthoredPawnCollisionPolicy() == EAstralRootMotionPawnCollisionPolicy::StopOnHit) ? TEXT("StopOnHit") : TEXT("Normal");
		}
	}

	UE_LOG(LogAstralAbilitySystem, Log, TEXT("[Facing] Role=%s Spec=%s Key=%d Stage=%d Source=%s Yaw=%u ServerStage=%d Decision=%s Reason=%s Pos=%.3f Warp=%s Policy=%s"),
		Role, *GetName(), FacingSessionKey.Current, StageIndex,
		Proposal ? AstralFacing::ToString(Proposal->Source) : TEXT("-"), Proposal ? Proposal->QuantizedDesiredYaw : 0,
		FacingInbox.GetCurrentStage(), AstralFacing::ToString(Decision), AstralFacing::ToString(Reason), MontagePosition, *WarpTargetName.ToString(), Policy);
#endif
}

//////////////////////////////////////////////////////////////////////////
// 자원 바인딩

void UAstralGA_Hero_Base::ApplyUltGain(float Amount) const
{
	if (Amount <= 0.f)
	{
		return;
	}
	ApplySetByCallerEffect(UAstralGameData::Get().UltGain, Amount);
}

void UAstralGA_Hero_Base::ApplyMarkGain(float Amount) const
{
	if (Amount <= 0.f)
	{
		return;
	}
	ApplySetByCallerEffect(UAstralGameData::Get().MarkGain, Amount);
}

void UAstralGA_Hero_Base::ApplyStaminaDrain(float Amount) const
{
	if (Amount <= 0.f)
	{
		return;
	}
	ApplySetByCallerEffect(UAstralGameData::Get().StaminaDrain, -Amount);
}

void UAstralGA_Hero_Base::ApplyRegenBlockEffect(const FGameplayAbilitySpecHandle Handle, const FGameplayAbilityActorInfo* ActorInfo, const FGameplayAbilityActivationInfo ActivationInfo) const
{
	if (!ActorInfo || !ActorInfo->IsNetAuthority())
	{
		return;
	}

	const TSubclassOf<UGameplayEffect> EffectClass = UAstralGameData::Get().StaminaRegenBlockEffect.LoadSynchronous();
	if (!EffectClass)
	{
		return;
	}

	const FGameplayEffectSpecHandle SpecHandle = MakeOutgoingGameplayEffectSpec(Handle, ActorInfo, ActivationInfo, EffectClass, GetAbilityLevel());
	if (SpecHandle.IsValid())
	{
		ApplyGameplayEffectSpecToOwner(Handle, ActorInfo, ActivationInfo, SpecHandle);
	}
}
