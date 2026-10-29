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
#include "Core/AnimMcpGeneration.h"
#include "Core/AnimMcpMontage.h"
#include "Core/AnimMcpSkeletonInspector.h"
#include "EditorAnimUtils.h"
#include "Engine/SkeletalMesh.h"
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
		// AI 애니 생성 Phase 1 — 스켈레톤 조회 (Core/AnimMcpSkeletonInspector). 읽기 전용: 호출 중 새로 더티가 된 패키지가 있으면 경고만 붙인다
		Dispatcher.RegisterTool(TEXT("inspect_skeleton"),
			TEXT("Read-only facts about a Skeleton for animation generation/retargeting. Params: skeleton? | skeletal_mesh? (one required; both must agree), details? (default false: bones as {name, parent}; true adds ref_local/ref_component {t, r[pitch,yaw,roll], s?} and socket transforms), compare_to? (another Skeleton path: common bone names, missing_in_other[], reference-pose local rotation difference {p50,max,max_bone} in degrees, bone length ratio {p50,min,max} = compare_to/this, verdict same_rig | needs_ik_retarget | no_common_bones — judged by reference pose, not names; reference info only), suggest_finger_chains? (default false: also finger_chain_suggestion — standard finger chains found by geometry, hands from the mesh template's arm chains or by topology; the same proposal as create_ik_rig, a proposal rather than a measurement, so only on request), geometry? (default false: also geometry{mesh, vertices, bounds{min, max, size}, centroid, principal_axes[{axis, extent_cm[min, max] from the centroid, length_cm, std_cm}] (LOD0 vertex covariance, largest first), slices{items[{from_cm, to_cm, vertices, width_cm[2], center_cm[2]}]} (24 cuts along the first axis — a handle is the thin part), per_bone[{bone, vertices, min, max}]} of the mesh in its reference pose — e.g. the long axis of a weapon mesh for a grip segment). Returns skeleton_path, meshes[] (registry), animation_count, bone_count, root_bone, bones[], virtual_bones[], mesh (skeletal_mesh, else skeleton preview, else first registered) + mesh_source, sockets[] (skeleton + mesh), slot_groups[], curve_count, ik_rigs[] (preview mesh is one of meshes[]), retargeters[] (referencing those rigs, with roles), template_match{used, name, percent, matching_bones, missing_bones, pelvis, chains[]} (IK Rig auto characterizer on the mesh; non-template skeletons report used=false and need manual chains)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				const AnimMcpGeneration::FDirtyGuard Guard;
				AnimMcpSkeletonInspector::FInspectParams Params;
				Params.bDetails = Context.Request.GetOptionalBool(TEXT("details"), false);
				Params.bSuggestFingerChains = Context.Request.GetOptionalBool(TEXT("suggest_finger_chains"), false);
				Params.bGeometry = Context.Request.GetOptionalBool(TEXT("geometry"), false);

				const FString SkeletonPath = Context.Request.GetOptionalString(TEXT("skeleton"));
				const FString MeshPath = Context.Request.GetOptionalString(TEXT("skeletal_mesh"));
				if (SkeletonPath.IsEmpty() && MeshPath.IsEmpty())
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("Pass skeleton or skeletal_mesh"));
					return nullptr;
				}
				if (!MeshPath.IsEmpty())
				{
					Params.Mesh = Cast<USkeletalMesh>(AnimMcpAssetResolver::LoadAssetOfClass(MeshPath, USkeletalMesh::StaticClass(), OutError));
					if (!Params.Mesh) { return nullptr; }
				}
				if (!SkeletonPath.IsEmpty())
				{
					Params.Skeleton = AnimMcpAssetResolver::LoadSkeleton(SkeletonPath, OutError);
					if (!Params.Skeleton) { return nullptr; }
				}
				if (Params.Mesh)
				{
					USkeleton* MeshSkeleton = Params.Mesh->GetSkeleton();
					if (!MeshSkeleton)
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' has no skeleton"), *Params.Mesh->GetPathName()));
						return nullptr;
					}
					if (Params.Skeleton && Params.Skeleton != MeshSkeleton)
					{
						TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
						Details->SetStringField(TEXT("reason"), TEXT("SKELETON_MISMATCH"));
						Details->SetStringField(TEXT("mesh_skeleton"), MeshSkeleton->GetPathName());
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' uses skeleton '%s', not '%s'"), *Params.Mesh->GetPathName(), *MeshSkeleton->GetPathName(), *Params.Skeleton->GetPathName()), Details);
						return nullptr;
					}
					Params.Skeleton = MeshSkeleton;
				}
				const FString ComparePath = Context.Request.GetOptionalString(TEXT("compare_to"));
				if (!ComparePath.IsEmpty())
				{
					Params.CompareTo = AnimMcpAssetResolver::LoadSkeleton(ComparePath, OutError);
					if (!Params.CompareTo) { return nullptr; }
				}

				TSharedRef<FJsonObject> Result = AnimMcpSkeletonInspector::Inspect(Params);
				TArray<FString> Allowed, Unexpected;
				Guard.GetNewlyDirty(Allowed, Unexpected);
				Unexpected.Append(Allowed);
				if (Unexpected.Num() > 0)
				{
					Context.AddDiagnostic(TEXT("warning"), AnimMcpErrorCodes::UnexpectedDirty,
						FString::Printf(TEXT("Read-only inspection left %d package(s) dirty (engine load fix-ups?): %s"), Unexpected.Num(), *FString::Join(Unexpected, TEXT(", "))));
				}
				return Result;
			});

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
