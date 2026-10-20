#include "AnimMcpTools.h"

#include "Animation/AnimData/IAnimationDataModel.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimationAsset.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/ARFilter.h"
#include "AssetRegistry/AssetData.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpMontage.h"
#include "EditorAnimUtils.h"
#include "Misc/PackageName.h"
#include "ReferenceSkeleton.h"

// Phase 7-6 — 스켈레톤 재할당. 본 이름이 같은 두 스켈레톤(같은 메시를 두 번 임포트한 경우)으로 갈라진 애니 애셋을 한쪽으로 모은다.
// 엔진의 "Retarget to another skeleton"(제자리) 경로 그대로: EditorAnimUtils::RetargetAnimations(NameRule 없음)
//   → FAnimationRetargetContext::RetargetAnimations → 시퀀스마다 CopyAnimationCurveNamesToSkeleton + ReplaceSkeleton(NewSkeleton)
//   (EditorAnimUtils.cpp:256-316 · AnimationAsset.cpp:460). 참조 애셋(몽타주 세그먼트·BlendSpace 샘플·기준 포즈)은 include_referred 면 같이 딸려간다.
// ReplaceSkeleton 은 새 스켈레톤에 없는 본 트랙을 조용히 버리므로 트랙 이름을 미리 대조해 BONES_MISSING 으로 거부한다(allow_missing_bones 로 해제).
// 참조 애셋은 **항상** 같이 옮겨진다 — UAnimationAsset::ReplaceSkeleton 자체가 GetAllAnimationSequencesReferred 로 세그먼트·샘플·기준 포즈를
// 모아 함께 바꾼다(AnimationAsset.cpp:468-474, 7-6 실측: include_referred=false 로 몽타주만 보내도 세그먼트가 딸려갔다). 그래서 옵션이 아니라
// 계획(referred[])으로 보여 주고 저장 목록에 넣는다.
namespace AnimMcpTools
{
	namespace
	{
		struct FReassignCandidate
		{
			UAnimationAsset* Asset = nullptr;
			USkeleton* From = nullptr;
			TArray<FName> MissingBones;
		};

		/** 시퀀스 본 트랙 중 새 스켈레톤 레퍼런스 스켈레톤에 없는 것 (IAnimationDataModel::GetBoneTrackNames) */
		TArray<FName> FindMissingBones(const UAnimationAsset* Asset, const USkeleton* NewSkeleton)
		{
			TArray<FName> Missing;
			const UAnimSequence* Sequence = Cast<UAnimSequence>(Asset);
			if (!Sequence || !NewSkeleton)
			{
				return Missing;
			}
			const IAnimationDataModel* Model = Sequence->GetDataModel();
			if (!Model)
			{
				return Missing;
			}
			TArray<FName> TrackNames;
			Model->GetBoneTrackNames(TrackNames);
			const FReferenceSkeleton& RefSkeleton = NewSkeleton->GetReferenceSkeleton();
			for (const FName& Track : TrackNames)
			{
				if (RefSkeleton.FindBoneIndex(Track) == INDEX_NONE)
				{
					Missing.Add(Track);
				}
			}
			return Missing;
		}

		TSharedPtr<FJsonValue> NamesToJson(const TArray<FName>& Names)
		{
			TArray<TSharedPtr<FJsonValue>> Values;
			for (const FName& N : Names) { Values.Add(MakeShared<FJsonValueString>(N.ToString())); }
			return MakeShared<FJsonValueArray>(Values);
		}

		/** AssetRegistry 로 from_skeleton 의 애니 애셋을 path_prefix 아래에서 모은다 (로드는 호출자) */
		TArray<FAssetData> CollectBySkeleton(const FString& PathPrefix, const FString& FromSkeletonObjectPath)
		{
			FARFilter Filter;
			Filter.ClassPaths.Add(UAnimationAsset::StaticClass()->GetClassPathName());
			Filter.bRecursiveClasses = true;
			Filter.PackagePaths.Add(FName(*PathPrefix));
			Filter.bRecursivePaths = true;

			TArray<FAssetData> Assets;
			FAssetRegistryModule::GetRegistry().GetAssets(Filter, Assets);
			Assets.Sort([](const FAssetData& A, const FAssetData& B) { return A.GetObjectPathString() < B.GetObjectPathString(); });

			static const FName SkeletonTag(TEXT("Skeleton"));
			TArray<FAssetData> Matched;
			for (const FAssetData& Data : Assets)
			{
				FString TagValue;
				Data.GetTagValue(SkeletonTag, TagValue);
				if (!TagValue.IsEmpty() && FPackageName::ExportTextPathToObjectPath(TagValue) == FromSkeletonObjectPath)
				{
					Matched.Add(Data);
				}
			}
			return Matched;
		}
	}

	void RegisterSkeletonTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("reassign_skeleton"),
			TEXT("Move animation assets (AnimSequence, AnimMontage, BlendSpace, AimOffset, AnimComposite) onto another Skeleton in place — the engine's 'retarget to another skeleton' path (bone tracks remapped by name, curves copied to the new skeleton). Params: skeleton (target), assets? [paths] or (from_skeleton + path_prefix? default /Game) to collect every animation asset currently on from_skeleton, confirm (must be true unless dry_run), dry_run? (default false; returns the plan), allow_missing_bones? (default false: an AnimSequence with a bone track the target skeleton lacks is refused with BONES_MISSING), convert_spaces? (default false), save? (default true: saves every changed asset and the target skeleton if it became dirty). Assets the listed ones reference (montage segments, BlendSpace samples, additive base poses) ALWAYS move with them (engine behaviour) — they are listed under 'referred'. Assets already on the target skeleton are skipped."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString SkeletonPath;
				if (!Context.Request.GetRequiredString(TEXT("skeleton"), SkeletonPath, OutError)) { return nullptr; }
				USkeleton* NewSkeleton = AnimMcpAssetResolver::LoadSkeleton(SkeletonPath, OutError);
				if (!NewSkeleton) { return nullptr; }

				const bool bDryRun = Context.Request.GetOptionalBool(TEXT("dry_run"), false);
				const bool bConfirm = Context.Request.GetOptionalBool(TEXT("confirm"), false);
				const bool bAllowMissingBones = Context.Request.GetOptionalBool(TEXT("allow_missing_bones"), false);
				const bool bConvertSpaces = Context.Request.GetOptionalBool(TEXT("convert_spaces"), false);
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), true);

				USkeleton* FromSkeleton = nullptr;
				const FString FromPath = Context.Request.GetOptionalString(TEXT("from_skeleton"));
				if (!FromPath.IsEmpty())
				{
					FromSkeleton = AnimMcpAssetResolver::LoadSkeleton(FromPath, OutError);
					if (!FromSkeleton) { return nullptr; }
					if (FromSkeleton == NewSkeleton)
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("from_skeleton and skeleton are the same asset"));
						return nullptr;
					}
				}

				// ---- 대상 수집: assets[] 명시 또는 from_skeleton + path_prefix 로 레지스트리 수집 ----
				TArray<FString> AssetPaths;
				const TArray<TSharedPtr<FJsonValue>>* AssetsArray = nullptr;
				if (Context.Request.Params->TryGetArrayField(TEXT("assets"), AssetsArray) && AssetsArray)
				{
					for (const TSharedPtr<FJsonValue>& V : *AssetsArray)
					{
						FString S;
						// 숫자도 TryGetString 이 문자열로 바꿔 주므로 타입을 직접 본다
						if (!V.IsValid() || V->Type != EJson::String || !V->TryGetString(S) || S.IsEmpty())
						{
							TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
							Details->SetStringField(TEXT("field"), TEXT("assets"));
							OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("assets must be an array of asset path strings"), Details);
							return nullptr;
						}
						AssetPaths.Add(AnimMcpAssetResolver::NormalizeObjectPath(S));
					}
				}
				else
				{
					if (!FromSkeleton)
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("Pass assets[] or from_skeleton (+ path_prefix) to choose what to reassign"));
						return nullptr;
					}
					const FString PathPrefix = Context.Request.GetOptionalString(TEXT("path_prefix"), TEXT("/Game"));
					for (const FAssetData& Data : CollectBySkeleton(PathPrefix, FromSkeleton->GetPathName()))
					{
						AssetPaths.Add(Data.GetObjectPathString());
					}
				}

				TArray<FReassignCandidate> Candidates;
				TArray<TSharedPtr<FJsonValue>> Skipped;
				TArray<TSharedPtr<FJsonValue>> MissingReport;
				for (const FString& Path : AssetPaths)
				{
					UAnimationAsset* Asset = AnimMcpAssetResolver::LoadAnimationAsset(Path, OutError);
					if (!Asset) { return nullptr; }

					auto Skip = [&](const TCHAR* Reason)
					{
						TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
						Item->SetStringField(TEXT("asset"), Asset->GetPathName());
						Item->SetField(TEXT("skeleton"), AnimMcpJson::ObjectPathOrNull(Asset->GetSkeleton()));
						Item->SetStringField(TEXT("reason"), Reason);
						Skipped.Add(MakeShared<FJsonValueObject>(Item));
					};

					if (Asset->GetSkeleton() == NewSkeleton)
					{
						Skip(TEXT("already_on_target"));
						continue;
					}
					if (FromSkeleton && Asset->GetSkeleton() != FromSkeleton)
					{
						Skip(TEXT("other_skeleton"));
						continue;
					}
					if (!Asset->GetSkeleton())
					{
						Skip(TEXT("no_skeleton"));
						continue;
					}

					FReassignCandidate& C = Candidates.AddDefaulted_GetRef();
					C.Asset = Asset;
					C.From = Asset->GetSkeleton();
					C.MissingBones = FindMissingBones(Asset, NewSkeleton);
					if (C.MissingBones.Num() > 0)
					{
						TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
						Item->SetStringField(TEXT("asset"), Asset->GetPathName());
						Item->SetField(TEXT("missing_bones"), NamesToJson(C.MissingBones));
						MissingReport.Add(MakeShared<FJsonValueObject>(Item));
					}
				}

				// 참조 애셋 — ReplaceSkeleton 이 무조건 같이 옮기므로 계획에 보여 주고 저장 목록에 넣는다 (스켈레톤이 이미 target 인 것은 제외)
				TArray<UAnimationAsset*> Referred;
				for (const FReassignCandidate& C : Candidates)
				{
					TArray<UAnimationAsset*> Refs;
					C.Asset->GetAllAnimationSequencesReferred(Refs, /*bRecursive*/ true);
					for (UAnimationAsset* R : Refs)
					{
						if (R && R != C.Asset && R->GetSkeleton() != NewSkeleton && !Candidates.ContainsByPredicate([R](const FReassignCandidate& X) { return X.Asset == R; }))
						{
							Referred.AddUnique(R);
						}
					}
				}

				if (MissingReport.Num() > 0 && !bAllowMissingBones)
				{
					TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
					Details->SetStringField(TEXT("reason"), TEXT("BONES_MISSING"));
					Details->SetArrayField(TEXT("assets"), MissingReport);
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest,
						FString::Printf(TEXT("%d asset(s) have bone tracks that '%s' lacks — those tracks would be dropped (pass allow_missing_bones=true to proceed)"), MissingReport.Num(), *NewSkeleton->GetPathName()), Details);
					return nullptr;
				}

				auto MakeAssetList = [](const TArray<FReassignCandidate>& List)
				{
					TArray<TSharedPtr<FJsonValue>> Values;
					for (const FReassignCandidate& C : List)
					{
						TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
						Item->SetStringField(TEXT("asset"), C.Asset->GetPathName());
						Item->SetStringField(TEXT("class"), C.Asset->GetClass()->GetName());
						Item->SetField(TEXT("from"), AnimMcpJson::ObjectPathOrNull(C.From));
						if (C.MissingBones.Num() > 0) { Item->SetField(TEXT("missing_bones"), NamesToJson(C.MissingBones)); }
						Values.Add(MakeShared<FJsonValueObject>(Item));
					}
					return Values;
				};
				TArray<TSharedPtr<FJsonValue>> ReferredValues;
				for (UAnimationAsset* R : Referred)
				{
					TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
					Item->SetStringField(TEXT("asset"), R->GetPathName());
					Item->SetStringField(TEXT("class"), R->GetClass()->GetName());
					Item->SetField(TEXT("from"), AnimMcpJson::ObjectPathOrNull(R->GetSkeleton()));
					ReferredValues.Add(MakeShared<FJsonValueObject>(Item));
				}

				TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
				Result->SetStringField(TEXT("skeleton"), NewSkeleton->GetPathName());
				Result->SetField(TEXT("from_skeleton"), AnimMcpJson::ObjectPathOrNull(FromSkeleton));
				Result->SetBoolField(TEXT("dry_run"), bDryRun);
				Result->SetNumberField(TEXT("total"), AssetPaths.Num());
				Result->SetArrayField(TEXT("skipped"), Skipped);
				Result->SetArrayField(TEXT("referred"), ReferredValues);

				if (bDryRun)
				{
					Result->SetArrayField(TEXT("planned"), MakeAssetList(Candidates));
					Result->SetBoolField(TEXT("changed"), false);
					return Result;
				}
				if (!bConfirm)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("reassign_skeleton rewrites animation assets on disk — pass confirm=true (or dry_run=true to see the plan)"));
					return nullptr;
				}
				if (Candidates.Num() == 0)
				{
					Result->SetArrayField(TEXT("changed_assets"), {});
					Result->SetArrayField(TEXT("failed"), {});
					Result->SetBoolField(TEXT("changed"), false);
					Result->SetBoolField(TEXT("saved"), false);
					Result->SetBoolField(TEXT("skeleton_saved"), false);
					Context.AddDiagnostic(TEXT("info"), TEXT("NOTHING_TO_DO"), TEXT("No asset needed reassigning"));
					return Result;
				}

				// ---- 실행: 원본 스켈레톤별로 묶어 엔진 리타겟 (커브 복사는 OldSkeleton 기준이라 묶음마다 호출) ----
				// 대상 스켈레톤이 이미 더티면(다른 작업의 미저장 편집 — 7-3 테스트의 임시 슬롯이 실제 사례) 우리가 더럽힌 게 아니므로 저장하지 않는다
				const bool bSkeletonWasDirty = NewSkeleton->GetOutermost()->IsDirty();
				TMap<USkeleton*, TArray<TWeakObjectPtr<UObject>>> Groups;
				for (const FReassignCandidate& C : Candidates)
				{
					Groups.FindOrAdd(C.From).Add(C.Asset);
				}
				for (TPair<USkeleton*, TArray<TWeakObjectPtr<UObject>>>& Group : Groups)
				{
					EditorAnimUtils::RetargetAnimations(Group.Key, NewSkeleton, Group.Value, /*bRetargetReferredAssets*/ true, /*NameRule*/ nullptr, bConvertSpaces);
				}

				// ---- 검증·저장 ----
				TArray<FReassignCandidate> Changed;
				TArray<TSharedPtr<FJsonValue>> Failed;
				for (const FReassignCandidate& C : Candidates)
				{
					if (C.Asset->GetSkeleton() == NewSkeleton)
					{
						Changed.Add(C);
					}
					else
					{
						TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
						Item->SetStringField(TEXT("asset"), C.Asset->GetPathName());
						Item->SetField(TEXT("skeleton"), AnimMcpJson::ObjectPathOrNull(C.Asset->GetSkeleton()));
						Failed.Add(MakeShared<FJsonValueObject>(Item));
					}
				}
				TArray<UAnimationAsset*> ReferredChanged;
				for (UAnimationAsset* R : Referred)
				{
					if (R->GetSkeleton() == NewSkeleton) { ReferredChanged.Add(R); }
				}

				bool bAllSaved = false;
				bool bSkeletonSaved = false;
				if (bSave)
				{
					bAllSaved = true;
					for (const FReassignCandidate& C : Changed) { bAllSaved &= AnimMcpMontage::SaveAsset(C.Asset, Context); }
					for (UAnimationAsset* R : ReferredChanged) { bAllSaved &= AnimMcpMontage::SaveAsset(R, Context); }
					// 커브 이름 복사로 대상 스켈레톤이 더티가 될 수 있다 — 애셋만 저장하면 다음 로드에서 커브가 사라진다.
					// 단, 호출 전부터 더티였던 스켈레톤은 남의 미저장 편집까지 디스크에 박아 버리므로 저장하지 않고 알린다
					if (NewSkeleton->GetOutermost()->IsDirty())
					{
						if (bSkeletonWasDirty)
						{
							Context.AddDiagnostic(TEXT("warning"), TEXT("SKELETON_DIRTY_NOT_SAVED"), FString::Printf(TEXT("'%s' had unsaved changes before this call — not saved (save it yourself if the copied curve names must persist)"), *NewSkeleton->GetPathName()));
						}
						else
						{
							bSkeletonSaved = AnimMcpMontage::SaveAsset(NewSkeleton, Context);
							bAllSaved &= bSkeletonSaved;
						}
					}
				}

				TArray<TSharedPtr<FJsonValue>> ReferredChangedValues;
				for (UAnimationAsset* R : ReferredChanged) { ReferredChangedValues.Add(MakeShared<FJsonValueString>(R->GetPathName())); }

				Result->SetArrayField(TEXT("changed_assets"), MakeAssetList(Changed));
				Result->SetArrayField(TEXT("referred_changed"), ReferredChangedValues);
				Result->SetArrayField(TEXT("failed"), Failed);
				Result->SetBoolField(TEXT("changed"), Changed.Num() > 0);
				Result->SetBoolField(TEXT("saved"), bAllSaved);
				Result->SetBoolField(TEXT("skeleton_saved"), bSkeletonSaved);
				if (Failed.Num() > 0)
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("REASSIGN_INCOMPLETE"), FString::Printf(TEXT("%d asset(s) still report the old skeleton after retargeting"), Failed.Num()));
				}
				return Result;
			});
	}
}
