#include "AnimMcpRetargetAssets.h"

#include "AnimMcpGeneration.h"
#include "AnimMcpLog.h"
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

		/** 에디터 자동 생성 레시피 (SRetargetAnimAssetsWindow.cpp:668-742) — 컨트롤러는 SetIKRig·AddDefaultOps 뒤 */
		void ApplyMatchExisting(const UIKRetargeterController* Controller, const UIKRigDefinition* SourceRig, const UIKRigDefinition* TargetRig, const FAutoCharacterizeResults& TargetCharacterization)
		{
			// 정확한 이름 매핑만 (기본 fuzzy 는 발가락을 손가락에 붙이기도 한다 — 엔진 주석)
			if (FIKRetargetFKChainsOp* FKChainOp = Controller->GetFirstRetargetOpOfType<FIKRetargetFKChainsOp>())
			{
				FKChainOp->Settings.ChainMapping.AutoMapChains(EAutoMapChainType::Exact, /*bForceRemap*/ true);
			}

			// 타깃 리타깃 포즈 리셋 → 자동 정렬 → 템플릿이 제외한 본(보통 발)만 다시 리셋
			const FName TargetPose = Controller->GetCurrentRetargetPoseName(ERetargetSourceOrTarget::Target);
			Controller->ResetRetargetPose(TargetPose, TArray<FName>(), ERetargetSourceOrTarget::Target);
			Controller->AutoAlignAllBones(ERetargetSourceOrTarget::Target);
			const TArray<FName>& Excluded = TargetCharacterization.AutoRetargetDefinition.BonesToExcludeFromAutoPose;
			if (!Excluded.IsEmpty())
			{
				Controller->ResetRetargetPose(Controller->GetCurrentRetargetPoseName(ERetargetSourceOrTarget::Target), Excluded, ERetargetSourceOrTarget::Target);
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
				Details->SetStringField(TEXT("next"), TEXT("call create_ik_rig again with mode=manual, pelvis and chains[{name, start, end, goal?}] chosen from bones[]"));
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::IKRigAutoFailed,
					FString::Printf(TEXT("'%s' matches no known skeleton template — auto characterization makes no chains; define them manually"), *Params.Mesh->GetPathName()), Details);
				return nullptr;
			}
		}

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
			Obj->SetObjectField(TEXT("root_motion"), Root);
		}

		TSharedRef<FJsonObject> Poses = AnimMcpJson::MakeObject();
		Poses->SetObjectField(TEXT("source"), DescribePose(Controller, ERetargetSourceOrTarget::Source));
		Poses->SetObjectField(TEXT("target"), DescribePose(Controller, ERetargetSourceOrTarget::Target));
		Obj->SetObjectField(TEXT("retarget_poses"), Poses);
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
			Result->SetBoolField(TEXT("reused"), true);
			Result->SetBoolField(TEXT("saved"), false);
			return Result;
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
				ApplyMatchExisting(Controller, Params.SourceRig, Params.TargetRig, TargetCharacterization);
			}
			else
			{
				Controller->AutoMapChains(EAutoMapChainType::Exact, /*bForceRemap*/ true);
				if (Params.bAutoAlign)
				{
					Controller->AutoAlignAllBones(ERetargetSourceOrTarget::Target);
				}
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
		if (Result->GetArrayField(TEXT("unmapped_target_chains")).Num() > 0)
		{
			Context.AddDiagnostic(TEXT("warning"), TEXT("UNMAPPED_TARGET_CHAINS"), FString::Printf(TEXT("%d target chain(s) have no source chain (exact-name mapping) — they keep the target reference pose"),
				Result->GetArrayField(TEXT("unmapped_target_chains")).Num()));
		}
		Result->SetBoolField(TEXT("saved"), bSaved);
		return Result;
	}
}
