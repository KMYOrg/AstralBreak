#include "AnimMcpRetargetAssets.h"

#include "AnimMcpFingerChains.h"
#include "AnimMcpGeneration.h"
#include "AnimMcpLog.h"
#include "AnimMcpRetargetPoseAlign.h"
#include "AnimMcpSkeletonInspector.h"
#include "AnimMcpStats.h"
#include "Bridge/AnimMcpTypes.h"
#include "Engine/SkeletalMesh.h"
#include "ReferenceSkeleton.h"
#include "RetargetEditor/IKRetargeterController.h"
#include "RetargetEditor/IKRetargeterPoseGenerator.h"
#include "Retargeter/IKRetargeter.h"
#include "Retargeter/IKRetargetChainMapping.h"
#include "Retargeter/RetargetOps/FKChainsOp.h"
#include "Retargeter/RetargetOps/PinBoneOp.h"
#include "Retargeter/RetargetOps/RetargetPoseOp.h"
#include "Retargeter/RetargetOps/RootMotionGeneratorOp.h"
#include "Retargeter/RetargetOps/RunIKRigOp.h"
#include "Rig/IKRigDefinition.h"
#include "Rig/Solvers/IKRigFullBodyIK.h"
#include "RigEditor/IKRigAutoCharacterizer.h"
#include "RigEditor/IKRigAutoFBIK.h"
#include "RigEditor/IKRigController.h"

namespace AnimMcpRetargetAssets
{
	namespace
	{
		TSharedPtr<FJsonValue> NameOrNull(FName Name)
		{
			return AnimMcpJson::StringOrNull(Name.IsNone() ? FString() : Name.ToString());
		}

		FAnimMcpError FieldError(const TCHAR* Field, const TCHAR* Reason, const FString& Message, TSharedPtr<FJsonObject> Details = nullptr)
		{
			TSharedRef<FJsonObject> D = Details.IsValid() ? Details.ToSharedRef() : AnimMcpJson::MakeObject();
			D->SetStringField(TEXT("field"), Field);
			D->SetStringField(TEXT("reason"), Reason);
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, D);
		}

		/** 메시가 IK Rig 의 본·골·솔버 요구를 만족하는가 (UIKRigController::IsSkeletalMeshCompatible — 엔진이 리타깃 프로세서에서 쓰는 판정) */
		bool EnsureCompatible(const UIKRigDefinition* Rig, USkeletalMesh* Mesh, const TCHAR* Field, FAnimMcpError& OutError)
		{
			if (UIKRigController::GetController(Rig)->IsSkeletalMeshCompatible(Mesh))
			{
				return true;
			}
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("rig"), Rig->GetPathName());
			Details->SetStringField(TEXT("mesh"), Mesh->GetPathName());
			Details->SetField(TEXT("rig_preview_mesh"), AnimMcpJson::ObjectPathOrNull(Rig->GetPreviewMesh()));
			OutError = FieldError(Field, TEXT("INCOMPATIBLE_MESH"),
				FString::Printf(TEXT("'%s' lacks bones required by IK Rig '%s' (see Output Log, LogIKRig)"), *Mesh->GetPathName(), *Rig->GetPathName()), Details);
			return false;
		}

		void WarnPreviewMesh(const UObject* Asset, const USkeletalMesh* Preview, const USkeletalMesh* Requested, const TCHAR* Role, FAnimMcpContext& Context)
		{
			if (Preview != Requested)
			{
				Context.AddDiagnostic(TEXT("warning"), TEXT("PREVIEW_MESH_DIFFERS"),
					FString::Printf(TEXT("%s preview mesh of '%s' is '%s', not the requested '%s' — retargeting uses the requested mesh"),
						Role, *Asset->GetPathName(), *GetPathNameSafe(Preview), *GetPathNameSafe(Requested)));
			}
		}

		/** 수동 체인 사전 검증 — 본 존재(이름은 엔진처럼 대소문자 무시) · end 가 start 의 자손(같아도 됨) · 이름 · 골 중복 */
		bool ValidateManual(const FReferenceSkeleton& RefSkeleton, FName Pelvis, const TArray<FChainSpec>& Chains, FAnimMcpError& OutError)
		{
			if (Pelvis.IsNone())
			{
				OutError = FieldError(TEXT("pelvis"), TEXT("MISSING_PELVIS"), TEXT("mode manual needs pelvis (the retarget root — Pelvis Motion op copies it)"));
				return false;
			}
			if (RefSkeleton.FindRawBoneIndex(Pelvis) == INDEX_NONE)
			{
				OutError = FieldError(TEXT("pelvis"), TEXT("BONE_NOT_FOUND"), FString::Printf(TEXT("Pelvis bone '%s' is not in the mesh"), *Pelvis.ToString()));
				return false;
			}
			if (Chains.Num() == 0)
			{
				OutError = FieldError(TEXT("chains"), TEXT("NO_CHAINS"), TEXT("mode manual needs chains[{name, start, end, goal?}]"));
				return false;
			}
			TArray<TSharedPtr<FJsonValue>> Problems;
			TSet<FName> Names, Goals;
			for (int32 i = 0; i < Chains.Num(); ++i)
			{
				const FChainSpec& Chain = Chains[i];
				auto Problem = [&Problems, &Chain, i](const TCHAR* Error, FName Bone = NAME_None)
				{
					TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
					Item->SetNumberField(TEXT("index"), i);
					Item->SetStringField(TEXT("name"), Chain.Name.ToString());
					Item->SetStringField(TEXT("error"), Error);
					if (!Bone.IsNone()) { Item->SetStringField(TEXT("bone"), Bone.ToString()); }
					Problems.Add(MakeShared<FJsonValueObject>(Item));
				};
				bool bNameDup = false;
				Names.Add(Chain.Name, &bNameDup);
				if (bNameDup) { Problem(TEXT("DUPLICATE_NAME")); }
				if (!Chain.Goal.IsNone())
				{
					bool bGoalDup = false;
					Goals.Add(Chain.Goal, &bGoalDup);
					if (bGoalDup) { Problem(TEXT("DUPLICATE_GOAL"), Chain.Goal); }
				}
				const int32 Start = RefSkeleton.FindRawBoneIndex(Chain.Start);
				const int32 End = RefSkeleton.FindRawBoneIndex(Chain.End);
				if (Start == INDEX_NONE) { Problem(TEXT("BONE_NOT_FOUND"), Chain.Start); }
				if (End == INDEX_NONE) { Problem(TEXT("BONE_NOT_FOUND"), Chain.End); }
				if (Start != INDEX_NONE && End != INDEX_NONE)
				{
					int32 Walk = End;
					while (Walk != INDEX_NONE && Walk != Start)
					{
						Walk = RefSkeleton.GetRawParentIndex(Walk);
					}
					if (Walk == INDEX_NONE) { Problem(TEXT("END_NOT_BELOW_START"), Chain.End); }
				}
			}
			if (Problems.Num() > 0)
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetArrayField(TEXT("chains"), Problems);
				OutError = FieldError(TEXT("chains"), TEXT("BAD_CHAINS"), FString::Printf(TEXT("%d chain problem(s) — nothing was created"), Problems.Num()), Details);
				return false;
			}
			return true;
		}

		TSharedRef<FJsonObject> DescribePose(const UIKRetargeterController* Controller, ERetargetSourceOrTarget Side)
		{
			const FIKRetargetPose& Pose = Controller->GetCurrentRetargetPose(Side);
			int32 Rotated = 0;
			double MaxDeg = 0.0;
			for (const TPair<FName, FQuat>& Pair : Pose.GetAllDeltaRotations())
			{
				const double Deg = FMath::RadiansToDegrees(Pair.Value.GetNormalized().AngularDistance(FQuat::Identity));
				if (Deg > 1e-3)
				{
					++Rotated;
					MaxDeg = FMath::Max(MaxDeg, Deg);
				}
			}
			const FVector Root = Pose.GetRootTranslationDelta();
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("name"), Controller->GetCurrentRetargetPoseName(Side).ToString());
			Obj->SetNumberField(TEXT("rotated_bones"), Rotated);
			Obj->SetNumberField(TEXT("max_rotation_deg"), AnimMcpStats::Round(MaxDeg));
			Obj->SetArrayField(TEXT("root_offset"), { MakeShared<FJsonValueNumber>(AnimMcpStats::Round(Root.X)), MakeShared<FJsonValueNumber>(AnimMcpStats::Round(Root.Y)), MakeShared<FJsonValueNumber>(AnimMcpStats::Round(Root.Z)) });
			return Obj;
		}

		/** 정면 맞춤 (헤더 주석) — 대상 리타깃 포즈 루트(본 0)의 로컬 델타 두 개 */
		struct FFacing
		{
			FName Root;
			/** 소스 정면 → 대상 정면 (UE +Z) */
			FQuat Yaw = FQuat::Identity;
			/** 풀이용 포즈: 루트 전역 = Yaw⁻¹ · 기준 */
			FQuat AlignDelta = FQuat::Identity;
			/** 복원 포즈(Additive Pose): 루트 전역 = 기준 */
			FQuat RestoreDelta = FQuat::Identity;

			bool IsSet() const { return !Root.IsNone(); }
		};

		const FName FacingRestorePoseName(TEXT("FacingRestore"));

		FFacing MakeFacing(const USkeletalMesh* TargetMesh, double YawDeg)
		{
			FFacing Facing;
			if (FMath::IsNearlyZero(YawDeg, 1e-3))
			{
				return Facing;
			}
			const FReferenceSkeleton& RefSkeleton = TargetMesh->GetRefSkeleton();
			Facing.Root = RefSkeleton.GetBoneName(0);
			const FQuat RefRoot = RefSkeleton.GetRefBonePose()[0].GetRotation();
			Facing.Yaw = FQuat(FVector::UpVector, FMath::DegreesToRadians(YawDeg));
			// 리타깃 포즈 로컬 = 기준 × 델타 (IKRetargetProcessor.cpp:73) — 전역 Yaw⁻¹ 를 걸려면 델타 = 기준⁻¹ · Yaw⁻¹ · 기준
			Facing.AlignDelta = RefRoot.Inverse() * Facing.Yaw.Inverse() * RefRoot;
			Facing.RestoreDelta = Facing.AlignDelta.Inverse();
			return Facing;
		}

		/** ① 현재 대상 포즈에 루트 회전을 넣는다 (자동 정렬 앞) */
		void SetFacingAlignDelta(const UIKRetargeterController* Controller, const FFacing& Facing)
		{
			if (Facing.IsSet())
			{
				Controller->SetRotationOffsetForRetargetPoseBone(Facing.Root, Facing.AlignDelta, ERetargetSourceOrTarget::Target);
			}
		}

		/** 대상 포즈 자동 정렬 — AutoAlignAllBones 는 포즈를 먼저 전부 리셋한다(IKRetargeterController.cpp:1356). 정면 맞춤이면 루트를 돌린 뒤 리셋 없는 정렬(빈 목록 = 전부) */
		void AutoAlignTarget(const UIKRetargeterController* Controller, const FFacing& Facing)
		{
			if (!Facing.IsSet())
			{
				Controller->AutoAlignAllBones(ERetargetSourceOrTarget::Target);
				return;
			}
			Controller->ResetRetargetPose(Controller->GetCurrentRetargetPoseName(ERetargetSourceOrTarget::Target), TArray<FName>(), ERetargetSourceOrTarget::Target);
			SetFacingAlignDelta(Controller, Facing);
			Controller->AutoAlignBones(TArray<FName>(), ERetargetAutoAlignMethod::ChainToChain, ERetargetSourceOrTarget::Target);
		}

		int32 FindOpIndex(const UIKRetargeterController* Controller, const UScriptStruct* Type)
		{
			for (int32 i = 0; i < Controller->GetNumRetargetOps(); ++i)
			{
				const FInstancedStruct* Op = Controller->GetRetargetOpStructAtIndex(i);
				if (Op && Op->GetScriptStruct() && Op->GetScriptStruct()->IsChildOf(Type))
				{
					return i;
				}
			}
			return INDEX_NONE;
		}

		/** ② 복원 포즈 + Additive Pose op(Root Motion op 앞) ③ 소스 루트 복사면 Root Motion GlobalOffset — 레시피 적용 뒤 */
		void ApplyFacingRestore(const UIKRetargeterController* Controller, const FFacing& Facing, FAnimMcpContext& Context)
		{
			const FName AlignedPose = Controller->GetCurrentRetargetPoseName(ERetargetSourceOrTarget::Target);
			// 새 포즈가 현재 포즈가 된다 — 델타를 넣고 풀이용 포즈로 돌려 놓는다
			const FName RestorePose = Controller->CreateRetargetPose(FacingRestorePoseName, ERetargetSourceOrTarget::Target);
			Controller->SetRotationOffsetForRetargetPoseBone(Facing.Root, Facing.RestoreDelta, ERetargetSourceOrTarget::Target);
			Controller->SetCurrentRetargetPose(AlignedPose, ERetargetSourceOrTarget::Target);

			int32 OpIndex = Controller->AddRetargetOp(FIKRetargetAdditivePoseOp::StaticStruct());
			if (FIKRetargetOpBase* Op = Controller->GetRetargetOpByIndex(OpIndex))
			{
				FIKRetargetAdditivePoseOpSettings* Settings = static_cast<FIKRetargetAdditivePoseOpSettings*>(Op->GetSettings());
				Settings->PoseToApply = RestorePose;
				Settings->Alpha = 1.0f;
			}
			// 루트 모션은 되돌린 좌표계의 펠비스에서 만들어야 한다
			const int32 RootMotionIndex = FindOpIndex(Controller, FIKRetargetRootMotionOp::StaticStruct());
			if (RootMotionIndex != INDEX_NONE && RootMotionIndex < OpIndex && Controller->MoveRetargetOpInStack(OpIndex, RootMotionIndex))
			{
				OpIndex = RootMotionIndex;
			}

			FIKRetargetRootMotionOp* RootOp = Controller->GetFirstRetargetOpOfType<FIKRetargetRootMotionOp>();
			if (RootOp && RootOp->IsEnabled())
			{
				if (RootOp->Settings.RootMotionSource == ERootMotionSource::CopyFromSourceRoot)
				{
					// 소스 루트 복사는 풀이 좌표계(Yaw⁻¹) 값 — 전역에서 Yaw 를 마지막에 곱한다
					RootOp->Settings.GlobalOffset = RootOp->Settings.GlobalOffset * FTransform(Facing.Yaw);
				}
				else if (!RootOp->Settings.bRotateWithPelvis)
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("FACING_ROOT_ROTATION"),
						TEXT("root motion is generated from the pelvis without rotate_with_pelvis — the root keeps the facing-aligned reference rotation"));
				}
			}
		}

		/** 애셋의 정면 맞춤 — Additive Pose op 가 대상 루트(본 0) 하나만 돌리는 포즈를 쓰면 그 전역 Yaw. 풀이용 포즈가 그 역인지(consistent)도 본다 */
		TSharedPtr<FJsonValue> DescribeFacing(const UIKRetargeter* Retargeter, const UIKRetargeterController* Controller)
		{
			const USkeletalMesh* Mesh = Retargeter->GetPreviewMesh(ERetargetSourceOrTarget::Target);
			if (!Mesh || Mesh->GetRefSkeleton().GetNum() == 0)
			{
				return MakeShared<FJsonValueNull>();
			}
			const FName Root = Mesh->GetRefSkeleton().GetBoneName(0);
			const FQuat RefRoot = Mesh->GetRefSkeleton().GetRefBonePose()[0].GetRotation();
			for (int32 i = 0; i < Controller->GetNumRetargetOps(); ++i)
			{
				const FInstancedStruct* Struct = Controller->GetRetargetOpStructAtIndex(i);
				FIKRetargetOpBase* Op = Controller->GetRetargetOpByIndex(i);
				if (!Struct || !Op || Struct->GetScriptStruct() != FIKRetargetAdditivePoseOp::StaticStruct())
				{
					continue;
				}
				const FIKRetargetAdditivePoseOpSettings* Settings = static_cast<const FIKRetargetAdditivePoseOpSettings*>(Op->GetSettings());
				const FIKRetargetPose* Pose = Retargeter->GetRetargetPoseByName(ERetargetSourceOrTarget::Target, Settings->PoseToApply);
				const FQuat* Restore = Pose && Pose->GetAllDeltaRotations().Num() == 1 ? Pose->GetAllDeltaRotations().Find(Root) : nullptr;
				if (!Restore)
				{
					continue;
				}
				const FQuat Yaw = RefRoot * *Restore * RefRoot.Inverse();
				const FQuat* Aligned = Controller->GetCurrentRetargetPose(ERetargetSourceOrTarget::Target).GetAllDeltaRotations().Find(Root);
				TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
				Obj->SetNumberField(TEXT("yaw_deg"), AnimMcpStats::Round(Yaw.Rotator().Yaw));
				Obj->SetStringField(TEXT("target_root"), Root.ToString());
				Obj->SetStringField(TEXT("restore_pose"), Settings->PoseToApply.ToString());
				Obj->SetStringField(TEXT("op"), Controller->GetOpName(i).ToString());
				Obj->SetNumberField(TEXT("op_index"), i);
				Obj->SetBoolField(TEXT("enabled"), Controller->GetRetargetOpEnabled(i));
				Obj->SetBoolField(TEXT("consistent"), Aligned && FMath::RadiansToDegrees(Aligned->AngularDistance(Restore->Inverse())) < 0.01);
				return MakeShared<FJsonValueObject>(Obj);
			}
			return MakeShared<FJsonValueNull>();
		}

		/** 에디터 자동 생성 레시피 (SRetargetAnimAssetsWindow.cpp:668-742) — 컨트롤러는 SetIKRig·AddDefaultOps 뒤. per_bone 이면 OutAlignment 에 정렬 결과 */
		void ApplyMatchExisting(const UIKRetargeterController* Controller, const UIKRigDefinition* SourceRig, const UIKRigDefinition* TargetRig, const FAutoCharacterizeResults& TargetCharacterization, const FFacing& Facing,
			EAlignMode AlignMode, TSharedPtr<FJsonObject>& OutAlignment, FAnimMcpContext& Context)
		{
			// 모든 op 를 정확한 이름 매핑으로 (기본 fuzzy 는 발가락을 손가락에 붙이기도 한다 — 엔진 주석). 에디터 레시피는 FK op 만 바꿔
			// 꺼진 Run IK Rig op 에 fuzzy 가 남는데, 자동 정렬은 꺼진 op 의 매핑도 '매핑된 체인'으로 본다(IKRetargetProcessor.cpp
			// GetFirstChainMappedToChain) → 소스에 없는 대상 체인이 이름만 닮은 체인 방향으로 꺾인 채 남는다(Phase 5: LeftIndex → LeftLeg, 검지 MCP 120°)
			Controller->AutoMapChains(EAutoMapChainType::Exact, /*bForceRemap*/ true);

			// 타깃 리타깃 포즈 리셋 → 자동 정렬 → 템플릿이 제외한 본(보통 발)만 다시 리셋
			const FName TargetPose = Controller->GetCurrentRetargetPoseName(ERetargetSourceOrTarget::Target);
			Controller->ResetRetargetPose(TargetPose, TArray<FName>(), ERetargetSourceOrTarget::Target);
			AutoAlignTarget(Controller, Facing);
			const TArray<FName>& Excluded = TargetCharacterization.AutoRetargetDefinition.BonesToExcludeFromAutoPose;
			if (!Excluded.IsEmpty())
			{
				Controller->ResetRetargetPose(Controller->GetCurrentRetargetPoseName(ERetargetSourceOrTarget::Target), Excluded, ERetargetSourceOrTarget::Target);
				SetFacingAlignDelta(Controller, Facing);
			}
			if (AlignMode == EAlignMode::PerBone)
			{
				// 엔진 정렬 결과 위에 — 제외 본은 그대로 둔다
				OutAlignment = AnimMcpRetargetPoseAlign::AlignPerBone(Controller, Excluded, Facing.Yaw.Inverse(), Context);
			}

			// 자동 IK 는 아직 불안정 — 엔진도 끈다
			if (FIKRetargetRunIKRigOp* RunIKOp = Controller->GetFirstRetargetOpOfType<FIKRetargetRunIKRigOp>())
			{
				RunIKOp->SetEnabled(false);
			}

			// 루트 모션: 타깃에 펠비스와 별개인 루트가 있을 때만. 소스에 그런 루트가 없으면 타깃 펠비스에서 생성
			// (엔진은 캐릭터라이저의 펠비스를 쓰지만 여기서는 리그의 펠비스 — 템플릿 리그면 같고, 수동 리그에서도 의미가 맞다)
			if (FIKRetargetRootMotionOp* RootOp = Controller->GetFirstRetargetOpOfType<FIKRetargetRootMotionOp>())
			{
				const FName TargetRoot = TargetRig->GetSkeleton().BoneNames.Num() > 0 ? TargetRig->GetSkeleton().BoneNames[0] : NAME_None;
				if (TargetRoot != TargetRig->GetPelvis())
				{
					const FName SourceRoot = SourceRig->GetSkeleton().BoneNames.Num() > 0 ? SourceRig->GetSkeleton().BoneNames[0] : NAME_None;
					if (SourceRoot == SourceRig->GetPelvis())
					{
						RootOp->Settings.RootMotionSource = ERootMotionSource::GenerateFromTargetPelvis;
						RootOp->Settings.RootHeightSource = ERootMotionHeightSource::SnapToGround;
						RootOp->Settings.bRotateWithPelvis = true;
						RootOp->Settings.bMaintainOffsetFromPelvis = true;
					}
				}
				else
				{
					RootOp->SetEnabled(false);
				}
			}

			// IK 본을 새 위치에 붙이는 Pin Bones (템플릿의 핀 목록)
			Controller->AddRetargetOp(FIKRetargetPinBoneOp::StaticStruct());
			if (FIKRetargetPinBoneOp* PinBoneOp = Controller->GetFirstRetargetOpOfType<FIKRetargetPinBoneOp>())
			{
				PinBoneOp->Settings.TranslationMode = EPinBoneTranslationMode::CopyGlobalPosition;
				PinBoneOp->Settings.RotationMode = EPinBoneRotationMode::CopyGlobalRotation;
				for (const FBoneToPin& Pin : TargetCharacterization.AutoRetargetDefinition.BonesToPin.GetBonesToPin())
				{
					FPinBoneData Data;
					Data.BoneToCopyFrom.BoneName = Pin.BoneToPinTo;
					Data.BoneToCopyTo.BoneName = Pin.BoneToPin;
					PinBoneOp->Settings.BonesToPin.Add(Data);
				}
			}
		}
	}

	bool ParseChains(const TSharedRef<FJsonObject>& Params, TArray<FChainSpec>& Out, FAnimMcpError& OutError)
	{
		const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
		if (!Params->HasField(TEXT("chains")))
		{
			return true;
		}
		if (!Params->TryGetArrayField(TEXT("chains"), Array))
		{
			OutError = FieldError(TEXT("chains"), TEXT("BAD_TYPE"), TEXT("chains must be an array of {name, start, end, goal?}"));
			return false;
		}
		for (int32 i = 0; i < Array->Num(); ++i)
		{
			const TSharedPtr<FJsonObject>* Obj = nullptr;
			FString Name, Start, End, Goal;
			if (!(*Array)[i].IsValid() || !(*Array)[i]->TryGetObject(Obj) || !(*Obj)->TryGetStringField(TEXT("name"), Name) || Name.IsEmpty()
				|| !(*Obj)->TryGetStringField(TEXT("start"), Start) || Start.IsEmpty() || !(*Obj)->TryGetStringField(TEXT("end"), End) || End.IsEmpty())
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetNumberField(TEXT("index"), i);
				OutError = FieldError(TEXT("chains"), TEXT("BAD_TYPE"), FString::Printf(TEXT("chains[%d] needs string name, start, end (goal optional)"), i), Details);
				return false;
			}
			(*Obj)->TryGetStringField(TEXT("goal"), Goal);
			Out.Add({ FName(*Name), FName(*Start), FName(*End), Goal.IsEmpty() ? NAME_None : FName(*Goal) });
		}
		return true;
	}

	TSharedRef<FJsonObject> DescribeIKRig(const UIKRigDefinition* Rig)
	{
		UIKRigController* Controller = UIKRigController::GetController(Rig);
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetStringField(TEXT("asset_path"), Rig->GetPathName());
		Obj->SetField(TEXT("preview_mesh"), AnimMcpJson::ObjectPathOrNull(Rig->GetPreviewMesh()));
		Obj->SetField(TEXT("pelvis"), NameOrNull(Rig->GetPelvis()));
		TArray<TSharedPtr<FJsonValue>> Chains;
		for (const FBoneChain& Chain : Rig->GetRetargetChains())
		{
			TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
			Item->SetStringField(TEXT("name"), Chain.ChainName.ToString());
			Item->SetStringField(TEXT("start"), Chain.StartBone.BoneName.ToString());
			Item->SetStringField(TEXT("end"), Chain.EndBone.BoneName.ToString());
			Item->SetField(TEXT("goal"), NameOrNull(Chain.IKGoalName));
			Chains.Add(MakeShared<FJsonValueObject>(Item));
		}
		Obj->SetArrayField(TEXT("chains"), Chains);
		TArray<TSharedPtr<FJsonValue>> Goals;
		for (const UIKRigEffectorGoal* Goal : Rig->GetGoalArray())
		{
			if (!Goal) { continue; }
			TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
			Item->SetStringField(TEXT("name"), Goal->GoalName.ToString());
			Item->SetStringField(TEXT("bone"), Goal->BoneName.ToString());
			Goals.Add(MakeShared<FJsonValueObject>(Item));
		}
		Obj->SetArrayField(TEXT("goals"), Goals);
		TArray<TSharedPtr<FJsonValue>> Solvers;
		for (int32 i = 0; i < Controller->GetNumSolvers(); ++i)
		{
			const FInstancedStruct* Solver = Controller->GetSolverStructAtIndex(i);
			TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
			Item->SetNumberField(TEXT("index"), i);
			Item->SetField(TEXT("type"), AnimMcpJson::StringOrNull(Solver && Solver->GetScriptStruct() ? Solver->GetScriptStruct()->GetName() : FString()));
			Item->SetBoolField(TEXT("enabled"), Controller->GetSolverEnabled(i));
			Item->SetField(TEXT("start_bone"), NameOrNull(Controller->GetStartBone(i)));
			Solvers.Add(MakeShared<FJsonValueObject>(Item));
		}
		Obj->SetArrayField(TEXT("solvers"), Solvers);
		return Obj;
	}

	TSharedPtr<FJsonObject> CreateIKRig(const FIKRigParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		check(Params.Mesh);
		// ---- 재사용: 호환성만 본다 ----
		if (Params.ExistingRig)
		{
			if (!EnsureCompatible(Params.ExistingRig, Params.Mesh, TEXT("existing_rig"), OutError))
			{
				return nullptr;
			}
			WarnPreviewMesh(Params.ExistingRig, Params.ExistingRig->GetPreviewMesh(), Params.Mesh, TEXT("IK Rig"), Context);
			TSharedRef<FJsonObject> Result = DescribeIKRig(Params.ExistingRig);
			Result->SetBoolField(TEXT("reused"), true);
			Result->SetObjectField(TEXT("template_match"), AnimMcpSkeletonInspector::DescribeTemplateMatch(Params.Mesh));
			Result->SetBoolField(TEXT("saved"), false);
			return Result;
		}

		// ---- 애셋을 만들기 전에 끝낼 수 있는 검사 전부 ----
		const FReferenceSkeleton& RefSkeleton = Params.Mesh->GetRefSkeleton();
		FAutoCharacterizeResults Characterization;
		AnimMcpSkeletonInspector::Characterize(Params.Mesh, Characterization);
		const TSharedRef<FJsonObject> TemplateMatch = AnimMcpSkeletonInspector::TemplateMatchToJson(Characterization, Params.Mesh);
		// 손가락 체인 제안 — 손은 정할 체인(manual 인자 · 템플릿)의 팔 짝에서, 없으면 위상으로. 이름이 아니라 기하라 템플릿이 손가락을 밀려 맞춘 것도 드러난다
		auto SuggestFingers = [&Params, &RefSkeleton, &Characterization]()
		{
			AnimMcpSkeletonGeometry::FTree Tree;
			Tree.Init(RefSkeleton);
			AnimMcpSkeletonGeometry::FChainSource Source;
			TArray<AnimMcpFingerChains::FGivenChain> Given;
			const TArray<FBoneChain>& Template = Characterization.AutoRetargetDefinition.RetargetDefinition.BoneChains;
			Source.From = Params.bManual ? TEXT("argument") : Characterization.bUsedTemplate ? TEXT("template") : TEXT("characterize");
			auto Add = [&](FName Name, FName Start, FName End)
			{
				TArray<int32> Bones = AnimMcpSkeletonGeometry::ChainBones(RefSkeleton, Tree, Start, End);
				if (Bones.Num() > 0) { Source.Chains.Add({ Name, MoveTemp(Bones) }); }
				Given.Add({ Name, Start, End });
			};
			if (Params.bManual)
			{
				for (const FChainSpec& Chain : Params.Chains) { Add(Chain.Name, Chain.Start, Chain.End); }
			}
			else
			{
				for (const FBoneChain& Chain : Template) { Add(Chain.ChainName, Chain.StartBone.BoneName, Chain.EndBone.BoneName); }
			}
			return AnimMcpFingerChains::Suggest(RefSkeleton, Tree, Source, Given);
		};
		if (Params.bManual)
		{
			if (!ValidateManual(RefSkeleton, Params.Pelvis, Params.Chains, OutError))
			{
				return nullptr;
			}
		}
		else
		{
			if (!Params.Pelvis.IsNone() && RefSkeleton.FindRawBoneIndex(Params.Pelvis) == INDEX_NONE)
			{
				OutError = FieldError(TEXT("pelvis"), TEXT("BONE_NOT_FOUND"), FString::Printf(TEXT("Pelvis bone '%s' is not in the mesh"), *Params.Pelvis.ToString()));
				return nullptr;
			}
			if (!Characterization.bUsedTemplate)
			{
				// 엔진은 템플릿이 맞을 때만 정의를 만든다(부분 성공 없음) — 본 계층을 돌려주고 수동 체인으로 다시 부르게 한다
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("mesh"), Params.Mesh->GetPathName());
				Details->SetObjectField(TEXT("template_match"), TemplateMatch);
				Details->SetNumberField(TEXT("bone_count"), RefSkeleton.GetRawBoneNum());
				Details->SetArrayField(TEXT("bones"), AnimMcpSkeletonInspector::DescribeBones(RefSkeleton, /*bDetails*/ false));
				Details->SetObjectField(TEXT("finger_chain_suggestion"), SuggestFingers().Json);
				Details->SetStringField(TEXT("next"), TEXT("call create_ik_rig again with mode=manual, pelvis and chains[{name, start, end, goal?}] chosen from bones[] — finger_chain_suggestion.chains[] are finger chains found by geometry; add them once the user confirms"));
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::IKRigAutoFailed,
					FString::Printf(TEXT("'%s' matches no known skeleton template — auto characterization makes no chains; define them manually"), *Params.Mesh->GetPathName()), Details);
				return nullptr;
			}
		}

		const AnimMcpFingerChains::FSuggestion Fingers = SuggestFingers();

		// ---- 생성 ----
		const AnimMcpGeneration::FDirtyGuard Guard;
		UIKRigDefinition* Rig = Cast<UIKRigDefinition>(AnimMcpGeneration::CreateAssetObject(UIKRigDefinition::StaticClass(), Params.AssetPath, TEXT("asset_path"), OutError));
		if (!Rig)
		{
			return nullptr;
		}
		UIKRigController* Controller = UIKRigController::GetController(Rig);
		auto Abort = [&](const TCHAR* Code, const FString& Message)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("partial_asset"), Rig->GetPathName());
			OutError = FAnimMcpError::Make(Code, Message + TEXT(" — the half-built asset is left unsaved"), Details);
			return nullptr;
		};
		if (!Controller->SetSkeletalMesh(Params.Mesh))
		{
			return Abort(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("SetSkeletalMesh('%s') failed on a new IK Rig"), *Params.Mesh->GetPathName()));
		}

		if (!Params.bManual)
		{
			// 에디터 자동 생성과 같은 순서 (SRetargetAnimAssetsWindow.cpp:648-653)
			Controller->SetRetargetDefinition(Characterization.AutoRetargetDefinition.RetargetDefinition);
			if (!Params.Pelvis.IsNone())
			{
				Controller->SetRetargetRoot(Params.Pelvis);
			}
			if (Params.bFBIK)
			{
				FAutoFBIKResults FBIK;
				Controller->AutoGenerateFBIK(FBIK);
				if (FBIK.Outcome != EAutoFBIKResult::AllOk)
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("AUTO_FBIK_INCOMPLETE"), FString::Printf(TEXT("Auto FBIK outcome %d, missing chains: %s"),
						static_cast<int32>(FBIK.Outcome), *FString::JoinBy(FBIK.MissingChains, TEXT(", "), [](FName N) { return N.ToString(); })));
				}
			}
		}
		else
		{
			Controller->SetRetargetRoot(Params.Pelvis);
			TArray<FName> GoalNames;
			for (const FChainSpec& Chain : Params.Chains)
			{
				FName Goal = NAME_None;
				if (!Chain.Goal.IsNone())
				{
					Goal = Controller->AddNewGoal(Chain.Goal, Chain.End);
					if (Goal.IsNone())
					{
						return Abort(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("AddNewGoal('%s', '%s') failed"), *Chain.Goal.ToString(), *Chain.End.ToString()));
					}
					GoalNames.Add(Goal);
				}
				const FName Added = Controller->AddRetargetChain(Chain.Name, Chain.Start, Chain.End, Goal);
				if (Added != Chain.Name)
				{
					return Abort(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("AddRetargetChain('%s') returned '%s'"), *Chain.Name.ToString(), *Added.ToString()));
				}
			}
			if (Params.bFBIK && GoalNames.Num() > 0)
			{
				const int32 SolverIndex = Controller->AddSolver(FIKRigFullBodyIKSolver::StaticStruct());
				Controller->SetStartBone(Params.Pelvis, SolverIndex);
				for (const FName& Goal : GoalNames)
				{
					Controller->ConnectGoalToSolver(Goal, SolverIndex);
				}
			}
			else if (Params.bFBIK)
			{
				Context.AddDiagnostic(TEXT("info"), TEXT("FBIK_SKIPPED"), TEXT("No chain has a goal — no Full Body IK solver added (FK chain retargeting does not need it)"));
			}
		}
		Rig->MarkPackageDirty();
		UE_LOG(LogAnimGraphMcp, Log, TEXT("create_ik_rig: %s (%s, %d chains, mesh %s)"), *Rig->GetPathName(), Params.bManual ? TEXT("manual") : TEXT("auto"), Rig->GetRetargetChains().Num(), *Params.Mesh->GetPathName());

		bool bSaved = false;
		if (!AnimMcpGeneration::FinishWrite(Guard, { Rig }, Params.bSave, Context, OutError, bSaved))
		{
			return nullptr;
		}
		TSharedRef<FJsonObject> Result = DescribeIKRig(Rig);
		Result->SetBoolField(TEXT("reused"), false);
		Result->SetStringField(TEXT("mode"), Params.bManual ? TEXT("manual") : TEXT("auto"));
		Result->SetObjectField(TEXT("template_match"), TemplateMatch);
		Result->SetObjectField(TEXT("finger_chain_suggestion"), Fingers.Json);
		const TCHAR* Whose = Params.bManual ? TEXT("given") : TEXT("template");
		if (Fingers.Differs.Num() > 0)
		{
			TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
			Extra->SetArrayField(TEXT("differs"), Fingers.Differs);
			Context.AddDiagnostic(TEXT("warning"), TEXT("FINGER_CHAINS_DIFFER"), FString::Printf(TEXT("%d %s finger chain(s) sit on other bones than the geometry suggests (thumb, metacarpal and fingertips found by position, not name) — see finger_chain_suggestion.differs"),
				Fingers.Differs.Num(), Whose), Extra);
		}
		if (Fingers.Missing.Num() > 0)
		{
			TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
			Extra->SetArrayField(TEXT("chains"), Fingers.Missing);
			Context.AddDiagnostic(TEXT("info"), TEXT("FINGER_CHAINS_SUGGESTED"), FString::Printf(TEXT("%d finger chain(s) found by geometry are not in the %s chains — without them the target fingers keep their reference pose; add chains[] (mode manual) once the user confirms"),
				Fingers.Missing.Num(), Whose), Extra);
		}
		Result->SetBoolField(TEXT("saved"), bSaved);
		return Result;
	}

	TSharedRef<FJsonObject> DescribeRetargeter(const UIKRetargeter* Retargeter)
	{
		const UIKRetargeterController* Controller = UIKRetargeterController::GetController(Retargeter);
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetStringField(TEXT("asset_path"), Retargeter->GetPathName());
		Obj->SetField(TEXT("source_rig"), AnimMcpJson::ObjectPathOrNull(Retargeter->GetIKRig(ERetargetSourceOrTarget::Source)));
		Obj->SetField(TEXT("target_rig"), AnimMcpJson::ObjectPathOrNull(Retargeter->GetIKRig(ERetargetSourceOrTarget::Target)));
		Obj->SetField(TEXT("source_mesh"), AnimMcpJson::ObjectPathOrNull(Retargeter->GetPreviewMesh(ERetargetSourceOrTarget::Source)));
		Obj->SetField(TEXT("target_mesh"), AnimMcpJson::ObjectPathOrNull(Retargeter->GetPreviewMesh(ERetargetSourceOrTarget::Target)));

		TArray<TSharedPtr<FJsonValue>> Ops;
		for (int32 i = 0; i < Controller->GetNumRetargetOps(); ++i)
		{
			const FInstancedStruct* Op = Controller->GetRetargetOpStructAtIndex(i);
			const FName Name = Controller->GetOpName(i);
			TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
			Item->SetStringField(TEXT("name"), Name.ToString());
			Item->SetField(TEXT("type"), AnimMcpJson::StringOrNull(Op && Op->GetScriptStruct() ? Op->GetScriptStruct()->GetName() : FString()));
			Item->SetBoolField(TEXT("enabled"), Controller->GetRetargetOpEnabled(i));
			Item->SetField(TEXT("parent"), NameOrNull(Controller->GetParentOpByName(Name)));
			Ops.Add(MakeShared<FJsonValueObject>(Item));
		}
		Obj->SetArrayField(TEXT("ops"), Ops);

		TSharedRef<FJsonObject> Mapping = AnimMcpJson::MakeObject();
		TArray<FString> Unmapped;
		// FK Chains op 의 매핑 — 컨트롤러의 GetChainMapping(NAME_None) 은 "첫 매핑" 이 아니라 첫 op(Pelvis Motion, 매핑 없음)의 nullptr 를
		// 돌려준다(IKRetargeterController.cpp:1062-1077). 체인 단위 FK 복사가 리타깃 결과를 정하므로 이 op 를 기준으로 본다
		if (const FIKRetargetFKChainsOp* FKOp = Controller->GetFirstRetargetOpOfType<FIKRetargetFKChainsOp>())
		{
			for (const FRetargetChainPair& Pair : FKOp->Settings.ChainMapping.GetChainPairs())
			{
				Mapping->SetField(Pair.TargetChainName.ToString(), NameOrNull(Pair.SourceChainName));
				if (Pair.SourceChainName.IsNone())
				{
					Unmapped.Add(Pair.TargetChainName.ToString());
				}
			}
		}
		Obj->SetObjectField(TEXT("chain_mapping"), Mapping);
		Obj->SetArrayField(TEXT("unmapped_target_chains"), AnimMcpGeneration::ToJsonArray(Unmapped));

		TArray<TSharedPtr<FJsonValue>> Pins;
		if (const FIKRetargetPinBoneOp* PinOp = Controller->GetFirstRetargetOpOfType<FIKRetargetPinBoneOp>())
		{
			for (const FPinBoneData& Pin : PinOp->Settings.BonesToPin)
			{
				TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
				Item->SetStringField(TEXT("from"), Pin.BoneToCopyFrom.BoneName.ToString());
				Item->SetStringField(TEXT("to"), Pin.BoneToCopyTo.BoneName.ToString());
				Pins.Add(MakeShared<FJsonValueObject>(Item));
			}
		}
		Obj->SetArrayField(TEXT("pin_bones"), Pins);

		if (const FIKRetargetRootMotionOp* RootOp = Controller->GetFirstRetargetOpOfType<FIKRetargetRootMotionOp>())
		{
			TSharedRef<FJsonObject> Root = AnimMcpJson::MakeObject();
			Root->SetBoolField(TEXT("enabled"), RootOp->IsEnabled());
			Root->SetStringField(TEXT("source"), StaticEnum<ERootMotionSource>()->GetNameStringByValue(static_cast<int64>(RootOp->Settings.RootMotionSource)));
			Root->SetStringField(TEXT("height_source"), StaticEnum<ERootMotionHeightSource>()->GetNameStringByValue(static_cast<int64>(RootOp->Settings.RootHeightSource)));
			Root->SetBoolField(TEXT("rotate_with_pelvis"), RootOp->Settings.bRotateWithPelvis);
			Root->SetBoolField(TEXT("maintain_offset_from_pelvis"), RootOp->Settings.bMaintainOffsetFromPelvis);
			Root->SetNumberField(TEXT("global_offset_yaw_deg"), AnimMcpStats::Round(RootOp->Settings.GlobalOffset.GetRotation().Rotator().Yaw));
			Obj->SetObjectField(TEXT("root_motion"), Root);
		}

		TSharedRef<FJsonObject> Poses = AnimMcpJson::MakeObject();
		Poses->SetObjectField(TEXT("source"), DescribePose(Controller, ERetargetSourceOrTarget::Source));
		Poses->SetObjectField(TEXT("target"), DescribePose(Controller, ERetargetSourceOrTarget::Target));
		Obj->SetObjectField(TEXT("retarget_poses"), Poses);
		Obj->SetField(TEXT("facing_alignment"), DescribeFacing(Retargeter, Controller));
		return Obj;
	}

	TSharedPtr<FJsonObject> CreateRetargeter(const FRetargeterParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		if (!EnsureCompatible(Params.SourceRig, Params.SourceMesh, TEXT("source_mesh"), OutError)
			|| !EnsureCompatible(Params.TargetRig, Params.TargetMesh, TEXT("target_mesh"), OutError))
		{
			return nullptr;
		}

		// ---- 재사용: 그 RTG 의 IK Rig 가 요청과 같아야 한다 ----
		if (Params.Existing)
		{
			const UIKRigDefinition* ExistingSource = Params.Existing->GetIKRig(ERetargetSourceOrTarget::Source);
			const UIKRigDefinition* ExistingTarget = Params.Existing->GetIKRig(ERetargetSourceOrTarget::Target);
			if (ExistingSource != Params.SourceRig || ExistingTarget != Params.TargetRig)
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetField(TEXT("existing_source_rig"), AnimMcpJson::ObjectPathOrNull(ExistingSource));
				Details->SetField(TEXT("existing_target_rig"), AnimMcpJson::ObjectPathOrNull(ExistingTarget));
				OutError = FieldError(TEXT("existing_retargeter"), TEXT("RIG_MISMATCH"),
					FString::Printf(TEXT("'%s' uses source '%s' / target '%s', not the requested rigs"), *Params.Existing->GetPathName(), *GetPathNameSafe(ExistingSource), *GetPathNameSafe(ExistingTarget)), Details);
				return nullptr;
			}
			WarnPreviewMesh(Params.Existing, Params.Existing->GetPreviewMesh(ERetargetSourceOrTarget::Source), Params.SourceMesh, TEXT("Source"), Context);
			WarnPreviewMesh(Params.Existing, Params.Existing->GetPreviewMesh(ERetargetSourceOrTarget::Target), Params.TargetMesh, TEXT("Target"), Context);
			TSharedRef<FJsonObject> Result = DescribeRetargeter(Params.Existing);
			// 재사용은 쓰지 않는다 — 요청한 정면 맞춤과 애셋의 것이 다르면 알리기만 한다
			const TSharedPtr<FJsonObject>* ExistingFacing = nullptr;
			const double ExistingYaw = Result->TryGetObjectField(TEXT("facing_alignment"), ExistingFacing) ? (*ExistingFacing)->GetNumberField(TEXT("yaw_deg")) : 0.0;
			if (!FMath::IsNearlyEqual(ExistingYaw, Params.FacingYawDeg, 0.5))
			{
				Context.AddDiagnostic(TEXT("warning"), TEXT("FACING_MISMATCH_EXISTING"),
					FString::Printf(TEXT("existing retargeter aligns facing by %.1f deg, the request asks %.1f deg — the existing asset is used unchanged"), ExistingYaw, Params.FacingYawDeg));
			}
			if (Params.AlignMode != EAlignMode::Engine)
			{
				Context.AddDiagnostic(TEXT("warning"), TEXT("ALIGN_MODE_IGNORED_EXISTING"), TEXT("align_mode applies to new retargeters only — the existing asset is used unchanged"));
			}
			Result->SetBoolField(TEXT("reused"), true);
			Result->SetBoolField(TEXT("saved"), false);
			return Result;
		}

		const FFacing Facing = MakeFacing(Params.TargetMesh, Params.FacingYawDeg);
		if (Facing.IsSet())
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetNumberField(TEXT("facing_yaw_deg"), Params.FacingYawDeg);
			Details->SetStringField(TEXT("target_root"), Facing.Root.ToString());
			if (FMath::Abs(Params.FacingYawDeg) > 180.0)
			{
				OutError = FieldError(TEXT("facing_yaw_deg"), TEXT("OUT_OF_RANGE"), TEXT("facing_yaw_deg must be within [-180, 180]"), Details);
				return nullptr;
			}
			if (Facing.Root == Params.TargetRig->GetPelvis())
			{
				// 루트 = 펠비스면 Additive Pose 가 펠비스 제자리에서만 돌아 펠비스 이동이 소스 정면에 남는다
				OutError = FieldError(TEXT("facing_yaw_deg"), TEXT("FACING_NEEDS_ROOT"),
					FString::Printf(TEXT("target root '%s' is the pelvis — facing alignment needs a separate root bone above the pelvis"), *Facing.Root.ToString()), Details);
				return nullptr;
			}
		}

		if (Params.AlignMode == EAlignMode::PerBone && Params.Ops == EOpsRecipe::Default && !Params.bAutoAlign)
		{
			OutError = FieldError(TEXT("align_mode"), TEXT("ALIGN_MODE_WITHOUT_ALIGN"), TEXT("align_mode per_bone refines the auto-aligned target pose — use ops=match_existing or auto_align=true"));
			return nullptr;
		}

		FAutoCharacterizeResults TargetCharacterization;
		if (Params.Ops == EOpsRecipe::MatchExisting)
		{
			AnimMcpSkeletonInspector::Characterize(Params.TargetMesh, TargetCharacterization);
		}

		const AnimMcpGeneration::FDirtyGuard Guard;
		UIKRetargeter* Retargeter = Cast<UIKRetargeter>(AnimMcpGeneration::CreateAssetObject(UIKRetargeter::StaticClass(), Params.AssetPath, TEXT("asset_path"), OutError));
		if (!Retargeter)
		{
			return nullptr;
		}
		const UIKRetargeterController* Controller = UIKRetargeterController::GetController(Retargeter);
		TSharedPtr<FJsonObject> Alignment;
		{
			FScopedReinitializeIKRetargeter Reinitialize(Controller, ERetargetRefreshMode::ProcessorAndOpStack);
			Controller->SetIKRig(ERetargetSourceOrTarget::Source, Params.SourceRig);
			Controller->SetIKRig(ERetargetSourceOrTarget::Target, Params.TargetRig);
			Controller->SetPreviewMesh(ERetargetSourceOrTarget::Source, Params.SourceMesh);
			Controller->SetPreviewMesh(ERetargetSourceOrTarget::Target, Params.TargetMesh);
			Controller->RemoveAllOps();
			Controller->AddDefaultOps();
			if (Params.Ops == EOpsRecipe::MatchExisting)
			{
				ApplyMatchExisting(Controller, Params.SourceRig, Params.TargetRig, TargetCharacterization, Facing, Params.AlignMode, Alignment, Context);
			}
			else
			{
				Controller->AutoMapChains(EAutoMapChainType::Exact, /*bForceRemap*/ true);
				if (Params.bAutoAlign)
				{
					AutoAlignTarget(Controller, Facing);
					if (Params.AlignMode == EAlignMode::PerBone)
					{
						Alignment = AnimMcpRetargetPoseAlign::AlignPerBone(Controller, TArray<FName>(), Facing.Yaw.Inverse(), Context);
					}
				}
				else
				{
					SetFacingAlignDelta(Controller, Facing);
				}
			}
			if (Facing.IsSet())
			{
				ApplyFacingRestore(Controller, Facing, Context);
			}
		}
		Retargeter->MarkPackageDirty();
		UE_LOG(LogAnimGraphMcp, Log, TEXT("create_ik_retargeter: %s (%s -> %s, %d ops)"), *Retargeter->GetPathName(), *Params.SourceRig->GetName(), *Params.TargetRig->GetName(), Controller->GetNumRetargetOps());

		bool bSaved = false;
		if (!AnimMcpGeneration::FinishWrite(Guard, { Retargeter }, Params.bSave, Context, OutError, bSaved))
		{
			return nullptr;
		}
		TSharedRef<FJsonObject> Result = DescribeRetargeter(Retargeter);
		Result->SetBoolField(TEXT("reused"), false);
		Result->SetStringField(TEXT("ops_recipe"), Params.Ops == EOpsRecipe::MatchExisting ? TEXT("match_existing") : TEXT("default"));
		Result->SetStringField(TEXT("align_mode"), Params.AlignMode == EAlignMode::PerBone ? TEXT("per_bone") : TEXT("engine"));
		if (Alignment.IsValid())
		{
			Result->SetObjectField(TEXT("pose_alignment"), Alignment);
		}
		else
		{
			Result->SetField(TEXT("pose_alignment"), MakeShared<FJsonValueNull>());
		}
		if (Result->GetArrayField(TEXT("unmapped_target_chains")).Num() > 0)
		{
			Context.AddDiagnostic(TEXT("warning"), TEXT("UNMAPPED_TARGET_CHAINS"), FString::Printf(TEXT("%d target chain(s) have no source chain (exact-name mapping) — they keep the target reference pose"),
				Result->GetArrayField(TEXT("unmapped_target_chains")).Num()));
		}
		Result->SetBoolField(TEXT("saved"), bSaved);
		return Result;
	}
}
