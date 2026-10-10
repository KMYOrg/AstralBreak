#include "AstralFacingDebug.h"

#if !UE_BUILD_SHIPPING

#include "Abilities/GameplayAbility.h"
#include "AbilitySystem/Facing/AstralFacingSession.h"
#include "Animation/AnimInstance.h"
#include "AstralLogChannels.h"
#include "Character/Components/AstralCharacterMovementComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/Character.h"
#include "HAL/IConsoleManager.h"

namespace AstralFacingDebug
{
	namespace
	{
		/** 이 단계의 Facing 송신을 생략 (-1 = 끔). 0이면 활성화 이벤트에 빈 페이로드 — "미수신"을 Reliable RPC 손실과 구분해 재현 */
		int32 DropSendStage = -1;
		FAutoConsoleVariableRef CVarDropSendStage(TEXT("Astral.Facing.Debug.DropSendStage"), DropSendStage,
			TEXT("Facing TargetData 송신을 생략할 StageIndex (-1 = off). 서버 NoWarp_Missing 재현용"), ECVF_Cheat);

		int32 DuplicateSend = 0;
		FAutoConsoleVariableRef CVarDuplicateSend(TEXT("Astral.Facing.Debug.DuplicateSend"), DuplicateSend,
			TEXT("1이면 Stage 1~N Facing TargetData를 두 번 보낸다 (DuplicateIgnored 확인용)"), ECVF_Cheat);

		FStats Stats;

		FAutoConsoleCommand CmdDumpStats(TEXT("Astral.Facing.DumpStats"), TEXT("Facing 전달 카운터 출력"),
			FConsoleCommandDelegate::CreateLambda([]() { UE_LOG(LogAstralAbilitySystem, Display, TEXT("[Facing] Stats: %s"), *Stats.ToString()); }));
		FAutoConsoleCommand CmdResetStats(TEXT("Astral.Facing.ResetStats"), TEXT("Facing 전달 카운터 초기화"),
			FConsoleCommandDelegate::CreateLambda([]() { Stats.Reset(); }));

		const TCHAR* RoleToString(EAstralFacingSessionRole Role)
		{
			switch (Role)
			{
			case EAstralFacingSessionRole::AutonomousProxy: return TEXT("Client");
			case EAstralFacingSessionRole::LocalAuthority:  return TEXT("Host");
			case EAstralFacingSessionRole::RemoteServer:    return TEXT("Server");
			}
			return TEXT("?");
		}
	}

	bool ShouldDropSend(int32 StageIndex)
	{
		return DropSendStage == StageIndex;
	}

	bool ShouldDuplicateSend()
	{
		return DuplicateSend != 0;
	}

	FStats& GetStats()
	{
		return Stats;
	}

	FString FStats::ToString() const
	{
		return FString::Printf(TEXT("Prepared=%d SendAttempts=%d Received=%d StoredEarly=%d Approved=%d ExplicitNone=%d Missing=%d Rejected=%d Duplicate=%d Conflict=%d StageMismatch=%d AfterSession=%d DuplicateAdvance=%d"),
			Prepared, TargetDataSendAttempts, Received, StoredEarly, Approved, ExplicitNone, Missing, Rejected, Duplicate, Conflict, StageMismatch, AfterSession, DuplicateAdvance);
	}

	void LogStageDecision(const UGameplayAbility* Ability, const UAstralFacingSession* Session, const FAstralFacingStageResolution& Resolution, FName WarpTargetName)
	{
		if (!Ability || !Session)
		{
			return;
		}

		float MontagePosition = -1.f;
		const TCHAR* Policy = TEXT("-");
		if (const ACharacter* Character = Cast<ACharacter>(Ability->GetAvatarActorFromActorInfo()))
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

		const FAstralFacingProposal* Proposal = Resolution.Proposal.GetPtrOrNull();
		UE_LOG(LogAstralAbilitySystem, Log, TEXT("[Facing] Role=%s Spec=%s Key=%d Stage=%d Source=%s Yaw=%u ServerStage=%d Decision=%s Reason=%s Pos=%.3f Warp=%s Policy=%s"),
			RoleToString(Session->GetRole()), *Ability->GetName(), Session->GetActivationKey().Current, Resolution.StageIndex,
			Proposal ? AstralFacing::ToString(Proposal->Source) : TEXT("-"), Proposal ? Proposal->QuantizedDesiredYaw : 0,
			Session->GetInboxStage(), AstralFacing::ToString(Resolution.Decision), AstralFacing::ToString(Resolution.Reason),
			MontagePosition, *WarpTargetName.ToString(), Policy);
	}
}

#endif // !UE_BUILD_SHIPPING
