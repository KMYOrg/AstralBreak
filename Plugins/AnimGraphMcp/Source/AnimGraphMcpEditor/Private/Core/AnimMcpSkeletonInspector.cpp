#include "AnimMcpSkeletonInspector.h"

#include "AnimMcpMontage.h"
#include "AnimMcpStats.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetData.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "Bridge/AnimMcpTypes.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/SkeletalMeshSocket.h"
#include "Misc/PackageName.h"
#include "ReferenceSkeleton.h"
#include "Retargeter/IKRetargeter.h"
#include "Rig/IKRigDefinition.h"
#include "RigEditor/IKRigAutoCharacterizer.h"
#include "RigEditor/IKRigController.h"
#include "UObject/Package.h"

namespace AnimMcpSkeletonInspector
{
	namespace
	{
		/** same_rig 판정 (감사 §8) */
		constexpr double SameRigMaxRotDeg = 1.0;
		constexpr double SameRigLengthTolerance = 0.01;
		/** 이보다 짧은 본(부모와 같은 위치 — 트위스트·IK 본 등)은 길이 비에서 뺀다 (cm) */
		constexpr double MinBoneLength = 0.01;

		TSharedPtr<FJsonValue> VectorJson(const FVector& V)
		{
			return MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{
				MakeShared<FJsonValueNumber>(AnimMcpStats::Round(V.X)), MakeShared<FJsonValueNumber>(AnimMcpStats::Round(V.Y)), MakeShared<FJsonValueNumber>(AnimMcpStats::Round(V.Z)) });
		}

		/** [pitch, yaw, roll] (도) */
		TSharedPtr<FJsonValue> RotatorJson(const FQuat& Q)
		{
			const FRotator R = Q.Rotator();
			return MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{
				MakeShared<FJsonValueNumber>(AnimMcpStats::Round(R.Pitch)), MakeShared<FJsonValueNumber>(AnimMcpStats::Round(R.Yaw)), MakeShared<FJsonValueNumber>(AnimMcpStats::Round(R.Roll)) });
		}

		TSharedRef<FJsonObject> TransformJson(const FTransform& T)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetField(TEXT("t"), VectorJson(T.GetTranslation()));
			Obj->SetField(TEXT("r"), RotatorJson(T.GetRotation()));
			if (!T.GetScale3D().Equals(FVector::OneVector, 1e-4))
			{
				Obj->SetField(TEXT("s"), VectorJson(T.GetScale3D()));
			}
			return Obj;
		}

		TSharedPtr<FJsonValue> NameOrNull(FName Name)
		{
			return AnimMcpJson::StringOrNull(Name.IsNone() ? FString() : Name.ToString());
		}

		/** 태그 값(익스포트 텍스트 경로 또는 오브젝트 경로) → 오브젝트 경로 */
		FString TagObjectPath(const FAssetData& Data, FName Tag)
		{
			FString Value;
			Data.GetTagValue(Tag, Value);
			return Value.IsEmpty() ? Value : FPackageName::ExportTextPathToObjectPath(Value);
		}

		/** Class 애셋 중 Tag 가 Targets 의 하나를 가리키는 것 (경로 순) */
		TArray<FAssetData> AssetsReferencingByTag(UClass* Class, FName Tag, const TSet<FString>& Targets)
		{
			TArray<FAssetData> All;
			FAssetRegistryModule::GetRegistry().GetAssetsByClass(Class->GetClassPathName(), All, /*bSearchSubClasses*/ true);
			TArray<FAssetData> Matched;
			for (const FAssetData& Data : All)
			{
				if (Targets.Contains(TagObjectPath(Data, Tag)))
				{
					Matched.Add(Data);
				}
			}
			Matched.Sort([](const FAssetData& A, const FAssetData& B) { return A.GetObjectPathString() < B.GetObjectPathString(); });
			return Matched;
		}

		/** 컴포넌트 공간 기준 포즈 (raw 본) */
		TArray<FTransform> ComponentSpacePose(const FReferenceSkeleton& RefSkeleton)
		{
			const TArray<FMeshBoneInfo>& Info = RefSkeleton.GetRawRefBoneInfo();
			const TArray<FTransform>& Local = RefSkeleton.GetRawRefBonePose();
			TArray<FTransform> Component;
			Component.SetNum(Local.Num());
			for (int32 i = 0; i < Local.Num(); ++i)
			{
				const int32 Parent = Info[i].ParentIndex;
				Component[i] = Parent == INDEX_NONE ? Local[i] : Local[i] * Component[Parent];
			}
			return Component;
		}

		TArray<TSharedPtr<FJsonValue>> DescribeSockets(const USkeleton* Skeleton, USkeletalMesh* Mesh, bool bDetails)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			auto Add = [&Out, bDetails](const USkeletalMeshSocket* Socket, const TCHAR* Owner, const UObject* OwnerAsset)
			{
				if (!Socket)
				{
					return;
				}
				TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
				Item->SetStringField(TEXT("name"), Socket->SocketName.ToString());
				Item->SetStringField(TEXT("bone"), Socket->BoneName.ToString());
				Item->SetStringField(TEXT("owner"), Owner);
				Item->SetStringField(TEXT("asset"), OwnerAsset->GetPathName());
				if (bDetails)
				{
					Item->SetField(TEXT("location"), VectorJson(Socket->RelativeLocation));
					Item->SetField(TEXT("rotation"), RotatorJson(Socket->RelativeRotation.Quaternion()));
				}
				Out.Add(MakeShared<FJsonValueObject>(Item));
			};
			for (const USkeletalMeshSocket* Socket : Skeleton->Sockets)
			{
				Add(Socket, TEXT("skeleton"), Skeleton);
			}
			if (Mesh)
			{
				for (const USkeletalMeshSocket* Socket : Mesh->GetMeshOnlySocketList())
				{
					Add(Socket, TEXT("mesh"), Mesh);
				}
			}
			return Out;
		}

		/** IK Rig 패키지를 참조하는 리타기터 — 로드해서 소스/타깃 역할을 본다 */
		void CollectRetargeters(const TArray<FAssetData>& Rigs, TArray<TSharedPtr<FJsonValue>>& Out)
		{
			IAssetRegistry& Registry = FAssetRegistryModule::GetRegistry();
			TSet<FString> RigPaths;
			TSet<FName> Referencers;
			for (const FAssetData& Rig : Rigs)
			{
				RigPaths.Add(Rig.GetObjectPathString());
				TArray<FName> Refs;
				Registry.GetReferencers(Rig.PackageName, Refs);
				Referencers.Append(Refs);
			}
			TArray<FName> Sorted = Referencers.Array();
			Sorted.Sort(FNameLexicalLess());
			for (const FName& Package : Sorted)
			{
				TArray<FAssetData> Assets;
				Registry.GetAssetsByPackageName(Package, Assets);
				for (const FAssetData& Data : Assets)
				{
					if (Data.AssetClassPath != UIKRetargeter::StaticClass()->GetClassPathName())
					{
						continue;
					}
					const UIKRetargeter* Retargeter = Cast<UIKRetargeter>(Data.GetAsset());
					if (!Retargeter)
					{
						continue;
					}
					const UIKRigDefinition* Source = Retargeter->GetIKRig(ERetargetSourceOrTarget::Source);
					const UIKRigDefinition* Target = Retargeter->GetIKRig(ERetargetSourceOrTarget::Target);
					TArray<TSharedPtr<FJsonValue>> Roles;
					if (Source && RigPaths.Contains(Source->GetPathName())) { Roles.Add(MakeShared<FJsonValueString>(TEXT("source"))); }
					if (Target && RigPaths.Contains(Target->GetPathName())) { Roles.Add(MakeShared<FJsonValueString>(TEXT("target"))); }
					TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
					Item->SetStringField(TEXT("asset"), Retargeter->GetPathName());
					Item->SetField(TEXT("source_rig"), AnimMcpJson::ObjectPathOrNull(Source));
					Item->SetField(TEXT("target_rig"), AnimMcpJson::ObjectPathOrNull(Target));
					Item->SetArrayField(TEXT("roles"), Roles);
					Out.Add(MakeShared<FJsonValueObject>(Item));
				}
			}
		}
	}

	TArray<TSharedPtr<FJsonValue>> DescribeBones(const FReferenceSkeleton& RefSkeleton, bool bDetails)
	{
		const TArray<FMeshBoneInfo>& Info = RefSkeleton.GetRawRefBoneInfo();
		const TArray<FTransform>& Local = RefSkeleton.GetRawRefBonePose();
		TArray<FTransform> Component;
		if (bDetails)
		{
			Component = ComponentSpacePose(RefSkeleton);
		}
		TArray<TSharedPtr<FJsonValue>> Out;
		for (int32 i = 0; i < Info.Num(); ++i)
		{
			TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
			Item->SetStringField(TEXT("name"), Info[i].Name.ToString());
			const int32 Parent = Info[i].ParentIndex;
			Item->SetField(TEXT("parent"), NameOrNull(Parent == INDEX_NONE ? NAME_None : Info[Parent].Name));
			if (bDetails)
			{
				Item->SetObjectField(TEXT("ref_local"), TransformJson(Local[i]));
				Item->SetObjectField(TEXT("ref_component"), TransformJson(Component[i]));
			}
			Out.Add(MakeShared<FJsonValueObject>(Item));
		}
		return Out;
	}

	void Characterize(USkeletalMesh* Mesh, FAutoCharacterizeResults& OutResults)
	{
		if (!Mesh)
		{
			return;
		}
		// 트랜지언트 IK Rig — PreviewSkeletalMesh 만 채우면 된다(AutoGenerateRetargetDefinition 은 메시만 읽는다).
		// SetSkeletalMesh 를 거치지 않아 트랜잭션도 남지 않는다
		UIKRigDefinition* Rig = NewObject<UIKRigDefinition>(GetTransientPackage(), NAME_None, RF_Transient);
		Rig->PreviewSkeletalMesh = Mesh;
		UIKRigController::GetController(Rig)->AutoGenerateRetargetDefinition(OutResults);
		Rig->MarkAsGarbage();
	}

	TSharedRef<FJsonObject> DescribeTemplateMatch(USkeletalMesh* Mesh)
	{
		if (!Mesh)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetField(TEXT("mesh"), MakeShared<FJsonValueNull>());
			Obj->SetBoolField(TEXT("used"), false);
			Obj->SetStringField(TEXT("reason"), TEXT("NO_MESH"));
			return Obj;
		}
		FAutoCharacterizeResults Results;
		Characterize(Mesh, Results);
		return TemplateMatchToJson(Results, Mesh);
	}

	TSharedRef<FJsonObject> TemplateMatchToJson(const FAutoCharacterizeResults& Results, const USkeletalMesh* Mesh)
	{
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetField(TEXT("mesh"), AnimMcpJson::ObjectPathOrNull(Mesh));
		Obj->SetBoolField(TEXT("used"), Results.bUsedTemplate);
		Obj->SetField(TEXT("name"), NameOrNull(Results.BestTemplateName));
		Obj->SetNumberField(TEXT("percent"), AnimMcpStats::Round(Results.BestPercentageOfTemplateScore * 100.0, 1));
		Obj->SetNumberField(TEXT("matching_bones"), Results.BestNumMatchingBones);
		Obj->SetNumberField(TEXT("missing_bones"), Results.MissingBones.Num());
		Obj->SetNumberField(TEXT("bones_with_missing_parent"), Results.BonesWithMissingParent.Num());
		const FRetargetDefinition& Definition = Results.AutoRetargetDefinition.RetargetDefinition;
		Obj->SetField(TEXT("pelvis"), NameOrNull(Results.bUsedTemplate ? Definition.RootBone : NAME_None));
		TArray<TSharedPtr<FJsonValue>> Chains;
		if (Results.bUsedTemplate)
		{
			for (const FBoneChain& Chain : Definition.BoneChains)
			{
				TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
				Item->SetStringField(TEXT("name"), Chain.ChainName.ToString());
				Item->SetStringField(TEXT("start"), Chain.StartBone.BoneName.ToString());
				Item->SetStringField(TEXT("end"), Chain.EndBone.BoneName.ToString());
				Item->SetField(TEXT("goal"), NameOrNull(Chain.IKGoalName));
				Chains.Add(MakeShared<FJsonValueObject>(Item));
			}
		}
		Obj->SetArrayField(TEXT("chains"), Chains);
		return Obj;
	}

	TSharedRef<FJsonObject> Compare(const USkeleton* Skeleton, const USkeleton* Other)
	{
		const FReferenceSkeleton& A = Skeleton->GetReferenceSkeleton();
		const FReferenceSkeleton& B = Other->GetReferenceSkeleton();
		const TArray<FMeshBoneInfo>& InfoA = A.GetRawRefBoneInfo();
		const TArray<FMeshBoneInfo>& InfoB = B.GetRawRefBoneInfo();
		const TArray<FTransform>& PoseA = A.GetRawRefBonePose();
		const TArray<FTransform>& PoseB = B.GetRawRefBonePose();

		int32 Common = 0;
		TArray<TSharedPtr<FJsonValue>> MissingInOther;
		TArray<double> RotDiffs;
		TArray<double> LengthRatios;
		double MaxRot = -1.0;
		FName MaxRotBone;
		for (int32 i = 0; i < InfoA.Num(); ++i)
		{
			const int32 j = B.FindRawBoneIndex(InfoA[i].Name);
			if (j == INDEX_NONE)
			{
				MissingInOther.Add(MakeShared<FJsonValueString>(InfoA[i].Name.ToString()));
				continue;
			}
			++Common;
			const double Deg = FMath::RadiansToDegrees(PoseA[i].GetRotation().GetNormalized().AngularDistance(PoseB[j].GetRotation().GetNormalized()));
			RotDiffs.Add(Deg);
			if (Deg > MaxRot)
			{
				MaxRot = Deg;
				MaxRotBone = InfoA[i].Name;
			}
			// 본 길이 = 부모까지 거리(로컬 이동량). 루트·길이 0 본은 뺀다
			const double LenA = PoseA[i].GetTranslation().Size();
			const double LenB = PoseB[j].GetTranslation().Size();
			if (InfoA[i].ParentIndex != INDEX_NONE && LenA > MinBoneLength && LenB > MinBoneLength)
			{
				LengthRatios.Add(LenB / LenA);
			}
		}

		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetStringField(TEXT("skeleton"), Other->GetPathName());
		Obj->SetNumberField(TEXT("bone_count"), InfoB.Num());
		Obj->SetNumberField(TEXT("common"), Common);
		Obj->SetArrayField(TEXT("missing_in_other"), MissingInOther);
		Obj->SetNumberField(TEXT("only_in_other_count"), InfoB.Num() - Common);

		TSharedRef<FJsonObject> Rot = AnimMcpJson::MakeObject();
		Rot->SetNumberField(TEXT("p50"), AnimMcpStats::Round(AnimMcpStats::Percentile(RotDiffs, 50.0)));
		Rot->SetNumberField(TEXT("max"), AnimMcpStats::Round(FMath::Max(MaxRot, 0.0)));
		Rot->SetField(TEXT("max_bone"), NameOrNull(MaxRotBone));
		Obj->SetObjectField(TEXT("ref_rot_diff_deg"), Rot);

		TSharedRef<FJsonObject> Ratio = AnimMcpJson::MakeObject();
		double MinRatio = 0.0, MaxRatio = 0.0;
		if (LengthRatios.Num() > 0)
		{
			MinRatio = FMath::Min(LengthRatios);
			MaxRatio = FMath::Max(LengthRatios);
		}
		Ratio->SetStringField(TEXT("definition"), TEXT("compare_to length / this length, common non-root bones longer than 0.01cm"));
		Ratio->SetNumberField(TEXT("count"), LengthRatios.Num());
		Ratio->SetNumberField(TEXT("p50"), AnimMcpStats::Round(AnimMcpStats::Percentile(LengthRatios, 50.0), 4));
		Ratio->SetNumberField(TEXT("min"), AnimMcpStats::Round(MinRatio, 4));
		Ratio->SetNumberField(TEXT("max"), AnimMcpStats::Round(MaxRatio, 4));
		Obj->SetObjectField(TEXT("bone_length_ratio"), Ratio);

		const TCHAR* Verdict = TEXT("needs_ik_retarget");
		if (Common == 0)
		{
			Verdict = TEXT("no_common_bones");
		}
		else if (MaxRot < SameRigMaxRotDeg && MinRatio >= 1.0 - SameRigLengthTolerance && MaxRatio <= 1.0 + SameRigLengthTolerance)
		{
			Verdict = TEXT("same_rig");
		}
		Obj->SetStringField(TEXT("verdict"), Verdict);
		return Obj;
	}

	TSharedRef<FJsonObject> Inspect(const FInspectParams& Params)
	{
		USkeleton* Skeleton = Params.Skeleton;
		check(Skeleton);
		const FReferenceSkeleton& RefSkeleton = Skeleton->GetReferenceSkeleton();
		const FString SkeletonPath = Skeleton->GetPathName();

		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetStringField(TEXT("skeleton_path"), SkeletonPath);

		// ---- 이 스켈레톤을 쓰는 메시 · 시퀀스 (레지스트리, 로드 없음) ----
		const TSet<FString> SkeletonSet = { SkeletonPath };
		static const FName SkeletonTag(TEXT("Skeleton"));
		const TArray<FAssetData> Meshes = AssetsReferencingByTag(USkeletalMesh::StaticClass(), SkeletonTag, SkeletonSet);
		TArray<TSharedPtr<FJsonValue>> MeshValues;
		TSet<FString> MeshPaths;
		for (const FAssetData& Data : Meshes)
		{
			MeshValues.Add(MakeShared<FJsonValueString>(Data.GetObjectPathString()));
			MeshPaths.Add(Data.GetObjectPathString());
		}
		Result->SetArrayField(TEXT("meshes"), MeshValues);
		Result->SetNumberField(TEXT("animation_count"), AssetsReferencingByTag(UAnimSequence::StaticClass(), SkeletonTag, SkeletonSet).Num());

		// ---- 본 ----
		Result->SetNumberField(TEXT("bone_count"), RefSkeleton.GetRawBoneNum());
		Result->SetField(TEXT("root_bone"), NameOrNull(RefSkeleton.GetRawBoneNum() > 0 ? RefSkeleton.GetBoneName(0) : NAME_None));
		Result->SetArrayField(TEXT("bones"), DescribeBones(RefSkeleton, Params.bDetails));
		TArray<TSharedPtr<FJsonValue>> VirtualBones;
		for (const FVirtualBone& VB : Skeleton->GetVirtualBones())
		{
			TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
			Item->SetStringField(TEXT("name"), VB.VirtualBoneName.ToString());
			Item->SetStringField(TEXT("source"), VB.SourceBoneName.ToString());
			Item->SetStringField(TEXT("target"), VB.TargetBoneName.ToString());
			VirtualBones.Add(MakeShared<FJsonValueObject>(Item));
		}
		Result->SetArrayField(TEXT("virtual_bones"), VirtualBones);

		// ---- 메시: 명시 → 스켈레톤 프리뷰 → 레지스트리 첫 메시 (조회 전용 — 쓰기 Tool 은 메시를 항상 명시한다) ----
		USkeletalMesh* Mesh = Params.Mesh;
		const TCHAR* MeshSource = TEXT("argument");
		if (!Mesh)
		{
			Mesh = Skeleton->GetPreviewMesh(/*bFindIfNotSet*/ false);
			MeshSource = TEXT("skeleton_preview");
		}
		if (!Mesh && Meshes.Num() > 0)
		{
			Mesh = Cast<USkeletalMesh>(Meshes[0].GetAsset());
			MeshSource = TEXT("first_registered");
		}
		Result->SetField(TEXT("mesh"), AnimMcpJson::ObjectPathOrNull(Mesh));
		Result->SetStringField(TEXT("mesh_source"), Mesh ? MeshSource : TEXT("none"));

		Result->SetArrayField(TEXT("sockets"), DescribeSockets(Skeleton, Mesh, Params.bDetails));
		Result->SetArrayField(TEXT("slot_groups"), AnimMcpMontage::SlotGroupsArray(Skeleton));
		Result->SetNumberField(TEXT("curve_count"), Skeleton->GetNumCurveMetaData());

		// ---- IK Rig · 리타기터 (existing_rig / existing_retargeter 후보) ----
		static const FName PreviewMeshTag(TEXT("PreviewSkeletalMesh"));
		const TArray<FAssetData> Rigs = AssetsReferencingByTag(UIKRigDefinition::StaticClass(), PreviewMeshTag, MeshPaths);
		TArray<TSharedPtr<FJsonValue>> RigValues;
		for (const FAssetData& Data : Rigs)
		{
			TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
			Item->SetStringField(TEXT("asset"), Data.GetObjectPathString());
			Item->SetStringField(TEXT("preview_mesh"), TagObjectPath(Data, PreviewMeshTag));
			RigValues.Add(MakeShared<FJsonValueObject>(Item));
		}
		Result->SetArrayField(TEXT("ik_rigs"), RigValues);
		TArray<TSharedPtr<FJsonValue>> RetargeterValues;
		CollectRetargeters(Rigs, RetargeterValues);
		Result->SetArrayField(TEXT("retargeters"), RetargeterValues);

		Result->SetObjectField(TEXT("template_match"), DescribeTemplateMatch(Mesh));

		if (Params.CompareTo)
		{
			Result->SetObjectField(TEXT("compare"), Compare(Skeleton, Params.CompareTo));
		}
		return Result;
	}
}
