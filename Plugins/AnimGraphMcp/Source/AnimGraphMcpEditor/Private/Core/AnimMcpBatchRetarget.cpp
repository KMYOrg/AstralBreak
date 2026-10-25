#include "AnimMcpBatchRetarget.h"

#include "AnimMcpAnimValidator.h"
#include "AnimMcpAssetResolver.h"
#include "AnimMcpGeneration.h"
#include "AnimMcpLog.h"
#include "AnimMcpStats.h"
#include "Animation/AnimMontage.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "Bridge/AnimMcpTypes.h"
#include "EditorAnimUtils.h"
#include "Engine/SkeletalMesh.h"
#include "HAL/PlatformTime.h"
#include "RetargetEditor/IKRetargetBatchOperation.h"
#include "Retargeter/IKRetargeter.h"
#include "RigEditor/IKRigController.h"
#include "UObject/Package.h"
#include "UObject/StrongObjectPtr.h"

namespace AnimMcpBatchRetarget
{
	namespace
	{
		struct FPlanned
		{
			UAnimationAsset* Source = nullptr;
			FString ObjectPath;
			bool bReferenced = false;
		};

		/** UIKRetargetBatchOperation::GenerateAssetLists 와 같은 규칙 (IKRetargetBatchOperation.cpp:39-98, AnimBlueprint 분기 제외) */
		TArray<UAnimationAsset*> CollectAssets(const TArray<UAnimationAsset*>& Inputs, bool bIncludeReferenced)
		{
			TArray<UAnimationAsset*> List;
			for (UAnimationAsset* Asset : Inputs)
			{
				List.AddUnique(Asset);
				if (const UAnimMontage* Montage = Cast<UAnimMontage>(Asset))
				{
					for (const FSlotAnimationTrack& Track : Montage->SlotAnimTracks)
					{
						for (const FAnimSegment& Segment : Track.AnimTrack.AnimSegments)
						{
							if (Segment.IsValid() && Segment.GetAnimReference())
							{
								List.AddUnique(Segment.GetAnimReference().Get());
							}
						}
					}
					if (Montage->PreviewBasePose)
					{
						List.AddUnique(Montage->PreviewBasePose.Get());
					}
				}
			}
			if (bIncludeReferenced)
			{
				int32 Index = 0;
				while (Index < List.Num())
				{
					List[Index++]->HandleAnimReferenceCollection(List, /*bRecursive*/ true);
				}
			}
			return List;
		}

		TSharedRef<FJsonObject> PlannedJson(const FPlanned& P)
		{
			TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
			Item->SetStringField(TEXT("source"), P.Source->GetPathName());
			Item->SetStringField(TEXT("asset"), P.ObjectPath);
			Item->SetStringField(TEXT("class"), P.Source->GetClass()->GetName());
			Item->SetBoolField(TEXT("referenced"), P.bReferenced);
			return Item;
		}

		FAnimMcpError Bad(const TCHAR* Reason, const FString& Message, TSharedPtr<FJsonObject> Details = nullptr)
		{
			TSharedRef<FJsonObject> D = Details.IsValid() ? Details.ToSharedRef() : AnimMcpJson::MakeObject();
			D->SetStringField(TEXT("reason"), Reason);
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, D);
		}
	}

	TSharedPtr<FJsonObject> Run(const FParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		const UIKRigDefinition* SourceRig = Params.Retargeter->GetIKRig(ERetargetSourceOrTarget::Source);
		const UIKRigDefinition* TargetRig = Params.Retargeter->GetIKRig(ERetargetSourceOrTarget::Target);
		if (!SourceRig || !TargetRig)
		{
			OutError = Bad(TEXT("RETARGETER_INCOMPLETE"), FString::Printf(TEXT("'%s' has no %s IK Rig"), *Params.Retargeter->GetPathName(), SourceRig ? TEXT("target") : TEXT("source")));
			return nullptr;
		}
		for (const TPair<const UIKRigDefinition*, USkeletalMesh*>& Pair : { TPair<const UIKRigDefinition*, USkeletalMesh*>(SourceRig, Params.SourceMesh), TPair<const UIKRigDefinition*, USkeletalMesh*>(TargetRig, Params.TargetMesh) })
		{
			if (!UIKRigController::GetController(Pair.Key)->IsSkeletalMeshCompatible(Pair.Value))
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("rig"), Pair.Key->GetPathName());
				Details->SetStringField(TEXT("mesh"), Pair.Value->GetPathName());
				OutError = Bad(TEXT("INCOMPATIBLE_MESH"), FString::Printf(TEXT("'%s' is not compatible with IK Rig '%s'"), *Pair.Value->GetPathName(), *Pair.Key->GetPathName()), Details);
				return nullptr;
			}
		}
		// 소스 애니는 소스 메시로 샘플링된다(EvaluationOptions.OptionalSkeletalMesh) — 스켈레톤이 다르면 엉뚱한 포즈를 읽는다
		for (const UAnimationAsset* Asset : Params.Assets)
		{
			if (Asset->GetSkeleton() != Params.SourceMesh->GetSkeleton())
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("asset"), Asset->GetPathName());
				Details->SetField(TEXT("asset_skeleton"), AnimMcpJson::ObjectPathOrNull(Asset->GetSkeleton()));
				Details->SetField(TEXT("source_mesh_skeleton"), AnimMcpJson::ObjectPathOrNull(Params.SourceMesh->GetSkeleton()));
				OutError = Bad(TEXT("SKELETON_MISMATCH"), FString::Printf(TEXT("'%s' is on '%s' but source_mesh uses '%s'"), *Asset->GetPathName(), *GetPathNameSafe(Asset->GetSkeleton()), *GetPathNameSafe(Params.SourceMesh->GetSkeleton())), Details);
				return nullptr;
			}
		}

		// ---- 계획: 엔진과 같은 대상 목록 · 출력 이름 ----
		EditorAnimUtils::FNameDuplicationRule NameRule;
		NameRule.Prefix = Params.NameRule.Prefix;
		NameRule.Suffix = Params.NameRule.Suffix;
		NameRule.ReplaceFrom = Params.NameRule.ReplaceFrom;
		NameRule.ReplaceTo = Params.NameRule.ReplaceTo;
		NameRule.FolderPath = Params.OutputPath;

		const TArray<UAnimationAsset*> Collected = CollectAssets(Params.Assets, Params.bIncludeReferenced);
		const int32 Limit = AnimMcpGeneration::GetSettings().MaxRetargetAssetsPerCall;
		if (Collected.Num() > Limit)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetNumberField(TEXT("planned"), Collected.Num());
			Details->SetNumberField(TEXT("limit"), Limit);
			OutError = Bad(TEXT("LIMIT"), FString::Printf(TEXT("%d asset(s) planned (inputs + referenced) — over [AnimGraphMcp] MaxRetargetAssetsPerCall=%d; split the call"), Collected.Num(), Limit), Details);
			return nullptr;
		}
		TArray<FPlanned> Plan;
		TArray<TSharedPtr<FJsonValue>> Problems;
		TSet<FString> Seen;
		for (UAnimationAsset* Asset : Collected)
		{
			FPlanned& P = Plan.AddDefaulted_GetRef();
			P.Source = Asset;
			P.bReferenced = !Params.Assets.Contains(Asset);
			const FString Name = NameRule.Rename(Asset);
			P.ObjectPath = FString::Printf(TEXT("%s/%s.%s"), *Params.OutputPath, *Name, *Name);
			FText NameReason;
			auto Problem = [&](const TCHAR* Code, const FString& Message)
			{
				TSharedRef<FJsonObject> Item = PlannedJson(P);
				Item->SetStringField(TEXT("code"), Code);
				Item->SetStringField(TEXT("message"), Message);
				Problems.Add(MakeShared<FJsonValueObject>(Item));
			};
			if (!FName(*Name).IsValidObjectName(NameReason))
			{
				Problem(TEXT("INVALID_NAME"), NameReason.ToString());
				continue;
			}
			bool bDuplicate = false;
			Seen.Add(P.ObjectPath.ToLower(), &bDuplicate);
			if (bDuplicate)
			{
				Problem(TEXT("NAME_COLLISION_IN_BATCH"), TEXT("Two planned assets get the same output name — the engine would add a numeric suffix"));
			}
			else if (AnimMcpAssetResolver::AssetExists(P.ObjectPath) || StaticFindObject(UObject::StaticClass(), nullptr, *P.ObjectPath))
			{
				Problem(TEXT("ASSET_EXISTS"), TEXT("Output already exists — generation never overwrites (the engine's overwrite mode would replace references and force-delete it)"));
			}
		}
		if (Problems.Num() > 0)
		{
			const bool bOnlyExisting = !Problems.ContainsByPredicate([](const TSharedPtr<FJsonValue>& V) { return V->AsObject()->GetStringField(TEXT("code")) != TEXT("ASSET_EXISTS"); });
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetArrayField(TEXT("problems"), Problems);
			Details->SetStringField(TEXT("reason"), bOnlyExisting ? TEXT("ASSET_EXISTS") : TEXT("BAD_PLAN"));
			OutError = FAnimMcpError::Make(bOnlyExisting ? AnimMcpErrorCodes::AssetExists : AnimMcpErrorCodes::BadRequest,
				FString::Printf(TEXT("%d planned output(s) cannot be created — nothing was retargeted"), Problems.Num()), Details);
			return nullptr;
		}

		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetStringField(TEXT("retargeter"), Params.Retargeter->GetPathName());
		Result->SetStringField(TEXT("output_path"), Params.OutputPath);
		if (Params.bDryRun)
		{
			TArray<TSharedPtr<FJsonValue>> Planned;
			for (const FPlanned& P : Plan) { Planned.Add(MakeShared<FJsonValueObject>(PlannedJson(P))); }
			Result->SetArrayField(TEXT("planned"), Planned);
			Result->SetBoolField(TEXT("dry_run"), true);
			return Result;
		}

		// ---- 실행 ----
		const AnimMcpGeneration::FDirtyGuard Guard;
		FIKRetargetBatchOperationContext BatchContext;
		for (UAnimationAsset* Asset : Params.Assets) { BatchContext.AssetsToRetarget.Add(Asset); }
		BatchContext.SourceMesh = Params.SourceMesh;
		BatchContext.TargetMesh = Params.TargetMesh;
		BatchContext.IKRetargetAsset = Params.Retargeter;
		BatchContext.NameRule = NameRule;
		BatchContext.bUseSourcePath = false;
		BatchContext.bOverwriteExistingFiles = false;
		BatchContext.bIncludeReferencedAssets = Params.bIncludeReferenced;
		int32 Frames = 0;
		for (const FPlanned& P : Plan)
		{
			if (const UAnimSequence* Sequence = Cast<UAnimSequence>(P.Source)) { Frames += Sequence->GetNumberOfSampledKeys(); }
		}
		const double Start = FPlatformTime::Seconds();
		{
			TStrongObjectPtr<UIKRetargetBatchOperation> Operation(NewObject<UIKRetargetBatchOperation>());
			Operation->RunRetarget(BatchContext);
		}
		const double Seconds = FPlatformTime::Seconds() - Start;
		UE_LOG(LogAnimGraphMcp, Log, TEXT("retarget_animations: %d asset(s), %d frame(s) via %s in %.2fs"), Plan.Num(), Frames, *Params.Retargeter->GetName(), Seconds);

		// ---- 계획대로 생겼는지 ----
		TArray<UObject*> Generated;
		TArray<TSharedPtr<FJsonValue>> GeneratedJson, Referred, Missing;
		TArray<TPair<UAnimSequence*, UAnimSequence*>> ToValidate;
		for (const FPlanned& P : Plan)
		{
			UAnimationAsset* NewAsset = Cast<UAnimationAsset>(StaticFindObject(UAnimationAsset::StaticClass(), nullptr, *P.ObjectPath));
			if (!NewAsset)
			{
				Missing.Add(MakeShared<FJsonValueObject>(PlannedJson(P)));
				continue;
			}
			Generated.Add(NewAsset);
			GeneratedJson.Add(MakeShared<FJsonValueObject>(PlannedJson(P)));
			if (P.bReferenced) { Referred.Add(MakeShared<FJsonValueString>(P.ObjectPath)); }
			UAnimSequence* NewSequence = Cast<UAnimSequence>(NewAsset);
			UAnimSequence* SourceSequence = Cast<UAnimSequence>(P.Source);
			if (NewSequence && SourceSequence) { ToValidate.Emplace(NewSequence, SourceSequence); }
		}
		Result->SetArrayField(TEXT("generated"), GeneratedJson);
		Result->SetArrayField(TEXT("referred"), Referred);
		Result->SetNumberField(TEXT("seconds"), AnimMcpStats::Round(Seconds));
		Result->SetNumberField(TEXT("seconds_per_asset"), AnimMcpStats::Round(Plan.Num() > 0 ? Seconds / Plan.Num() : 0.0, 4));
		Result->SetNumberField(TEXT("frames"), Frames);
		Result->SetNumberField(TEXT("ms_per_frame"), AnimMcpStats::Round(Frames > 0 ? Seconds * 1000.0 / Frames : 0.0, 4));
		if (Missing.Num() > 0)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetArrayField(TEXT("missing"), Missing);
			Details->SetObjectField(TEXT("partial"), Result);
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::RetargetFailed,
				FString::Printf(TEXT("%d planned asset(s) were not created (cancelled, or the retargeter failed to initialize — see Output Log); %d created asset(s) left unsaved"), Missing.Num(), Generated.Num()), Details);
			return nullptr;
		}

		// ---- 팔-몸통 관통: 체인은 리타기터의 대상 IK Rig, 몸은 대상 메시 ----
		AnimMcpBodyClearance::FSpec Clearance = Params.BodyClearance;
		if (Params.BodyClearanceMode != AnimMcpBodyClearance::EMode::Off)
		{
			if (!Clearance.Mesh) { Clearance.Mesh = Params.TargetMesh; }
			if (!Clearance.Rig) { Clearance.Rig = Params.Retargeter->GetIKRig(ERetargetSourceOrTarget::Target); }
		}
		const bool bResolve = Params.BodyClearanceMode == AnimMcpBodyClearance::EMode::Resolve;
		if (bResolve || (Params.BodyClearanceMode == AnimMcpBodyClearance::EMode::Measure && !Params.bValidate))
		{
			TArray<TSharedPtr<FJsonValue>> Items;
			for (const TPair<UAnimSequence*, UAnimSequence*>& Pair : ToValidate)
			{
				bool bWarning = false;
				TSharedRef<FJsonObject> One = bResolve ? AnimMcpBodyClearance::Resolve(Pair.Key, Clearance, Params.BodyClearanceOptions, bWarning)
					: AnimMcpBodyClearance::Measure(Pair.Key, Clearance, bWarning);
				One->SetStringField(TEXT("asset"), Pair.Key->GetPathName());
				Items.Add(MakeShared<FJsonValueObject>(One));
				if (bWarning)
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("BODY_CLEARANCE_WARNINGS"), FString::Printf(TEXT("%s: body clearance %s left warnings — see body_clearance[].issues"),
						*Pair.Key->GetName(), bResolve ? TEXT("resolve") : TEXT("measure")));
				}
			}
			Result->SetArrayField(TEXT("body_clearance"), Items);
		}

		// ---- 검증 ----
		if (Params.bValidate)
		{
			AnimMcpAnimValidator::FOptions Options;
			Options.ExpectedSkeleton = Params.TargetMesh->GetSkeleton();
			if (Params.BodyClearanceMode != AnimMcpBodyClearance::EMode::Off)
			{
				Options.BodyClearance = Clearance;
			}
			if (Params.bFingers)
			{
				// 매핑 안 된 대상 손가락은 기준 포즈 그대로인지, 매핑된 손가락은 손바닥 쪽으로 · 순서대로 굽는지 — 꺼진 op 의 퍼지 매핑 같은 사고를 잡는다
				AnimMcpFingerChains::FCheckSpec Fingers;
				Fingers.Retargeter = Params.Retargeter;
				Fingers.Mesh = Params.TargetMesh;
				Options.Fingers = Fingers;
			}
			if (!AnimMcpAnimValidator::ParseThresholds(Params.Thresholds, Options.Thresholds, OutError))
			{
				return nullptr;
			}
			FString Worst = TEXT("PASSED");
			TArray<TSharedPtr<FJsonValue>> Assets;
			for (const TPair<UAnimSequence*, UAnimSequence*>& Pair : ToValidate)
			{
				TSharedRef<FJsonObject> One = AnimMcpAnimValidator::Validate(Pair.Key, Pair.Value, Options);
				Worst = AnimMcpAnimValidator::WorstStatus(Worst, One->GetStringField(TEXT("status")));
				Assets.Add(MakeShared<FJsonValueObject>(One));
				const TSharedPtr<FJsonObject>* FingersObj = nullptr;
				const TArray<TSharedPtr<FJsonValue>>* FingerIssues = nullptr;
				if (One->TryGetObjectField(TEXT("fingers"), FingersObj) && (*FingersObj)->TryGetArrayField(TEXT("issues"), FingerIssues))
				{
					TArray<FString> Codes;
					for (const TSharedPtr<FJsonValue>& Item : *FingerIssues)
					{
						const TSharedPtr<FJsonObject>* IssueObj = nullptr;
						if (Item->TryGetObject(IssueObj) && (*IssueObj)->GetStringField(TEXT("level")) == TEXT("warning")) { Codes.Add((*IssueObj)->GetStringField(TEXT("code"))); }
					}
					if (Codes.Num() > 0)
					{
						Context.AddDiagnostic(TEXT("warning"), TEXT("FINGER_WARNINGS"), FString::Printf(TEXT("%s: finger check %s — see validation.assets[].fingers"),
							*Pair.Key->GetName(), *FString::Join(Codes, TEXT(", "))));
					}
				}
			}
			TSharedRef<FJsonObject> Validation = AnimMcpJson::MakeObject();
			Validation->SetStringField(TEXT("status"), Worst);
			Validation->SetArrayField(TEXT("assets"), Assets);
			Result->SetObjectField(TEXT("validation"), Validation);
			if (Worst == TEXT("FAILED"))
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetObjectField(TEXT("partial"), Result);
				FAnimMcpError DirtyError;
				if (!Guard.Check(DirtyError)) { Details->SetObjectField(TEXT("unexpected_dirty"), DirtyError.Details); }
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::ValidationFailed,
					FString::Printf(TEXT("Validation FAILED for at least one of %d retargeted sequence(s) — nothing saved (details.partial.validation)"), ToValidate.Num()), Details);
				return nullptr;
			}
		}

		bool bSaved = false;
		if (!AnimMcpGeneration::FinishWrite(Guard, Generated, Params.bSave, Context, OutError, bSaved))
		{
			if (OutError.Details.IsValid()) { OutError.Details->SetObjectField(TEXT("partial"), Result); }
			return nullptr;
		}
		Result->SetBoolField(TEXT("saved"), bSaved);
		return Result;
	}
}
