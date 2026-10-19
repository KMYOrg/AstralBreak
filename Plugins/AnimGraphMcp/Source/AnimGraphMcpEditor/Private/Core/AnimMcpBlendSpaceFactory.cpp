#include "AnimMcpBlendSpaceFactory.h"

#include "AnimMcpAssetOps.h"
#include "AnimMcpAssetProtection.h"
#include "AnimMcpAssetResolver.h"
#include "AnimMcpLog.h"
#include "Animation/AimOffsetBlendSpace.h"
#include "Animation/AimOffsetBlendSpace1D.h"
#include "Animation/AnimSequence.h"
#include "Animation/BlendSpace.h"
#include "Animation/BlendSpace1D.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Bridge/AnimMcpTypes.h"
#include "Engine/SkeletalMesh.h"
#include "Misc/PackageName.h"
#include "UObject/Package.h"
#include "UObject/UnrealType.h"

namespace AnimMcpBlendSpaceFactory
{
	namespace
	{
		FAnimMcpError FieldError(const FString& Field, const FString& Message)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), Field);
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
		}

		FAnimMcpError SampleError(int32 Index, const FString& Message, const TCHAR* Reason)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), FString::Printf(TEXT("samples[%d]"), Index));
			Details->SetStringField(TEXT("reason"), Reason);
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
		}

		/** BlendParameters[AxisIndex] 의 주소 — protected 멤버라 리플렉션으로 얻는다 (BlendSpace.h:906-907, EditAnywhere static array[3]) */
		FBlendParameter* AxisPtr(UBlendSpace* BlendSpace, int32 AxisIndex)
		{
			static const FName PropName(TEXT("BlendParameters"));
			FProperty* Prop = UBlendSpace::StaticClass()->FindPropertyByName(PropName);
			if (!Prop || AxisIndex < 0 || AxisIndex >= Prop->ArrayDim)
			{
				return nullptr;
			}
			return Prop->ContainerPtrToValuePtr<FBlendParameter>(BlendSpace, AxisIndex);
		}

		bool SameSamplePoint(const FVector& A, const FVector& B)
		{
			// UBlendSpace::IsSameSamplePoint (BlendSpace.cpp:2270-2275) 와 같은 허용 오차
			return FMath::IsNearlyEqual(A.X, B.X, (FVector::FReal)UE_KINDA_SMALL_NUMBER)
				&& FMath::IsNearlyEqual(A.Y, B.Y, (FVector::FReal)UE_KINDA_SMALL_NUMBER)
				&& FMath::IsNearlyEqual(A.Z, B.Z, (FVector::FReal)UE_KINDA_SMALL_NUMBER);
		}
	}

	bool ParseCreateParams(const TSharedRef<FJsonObject>& Params, FCreateParams& Out, FAnimMcpError& OutError)
	{
		if (!Params->TryGetStringField(TEXT("asset_path"), Out.AssetPath) || Out.AssetPath.IsEmpty())
		{
			OutError = FieldError(TEXT("asset_path"), TEXT("Missing or empty required string parameter 'asset_path'"));
			return false;
		}
		if (!Params->TryGetStringField(TEXT("skeleton"), Out.SkeletonPath) || Out.SkeletonPath.IsEmpty())
		{
			OutError = FieldError(TEXT("skeleton"), TEXT("Missing or empty required string parameter 'skeleton'"));
			return false;
		}
		Params->TryGetStringField(TEXT("preview_mesh"), Out.PreviewMeshPath);
		Params->TryGetBoolField(TEXT("overwrite"), Out.bOverwrite);
		Params->TryGetBoolField(TEXT("aim_offset"), Out.bAimOffset);

		double Dim = 1.0;
		Params->TryGetNumberField(TEXT("dimensions"), Dim);
		Out.Dimensions = static_cast<int32>(Dim);
		if (Out.Dimensions != 1 && Out.Dimensions != 2)
		{
			OutError = FieldError(TEXT("dimensions"), TEXT("'dimensions' must be 1 or 2"));
			return false;
		}

		const TArray<TSharedPtr<FJsonValue>>* Axes = nullptr;
		if (!Params->TryGetArrayField(TEXT("axes"), Axes) || !Axes)
		{
			OutError = FieldError(TEXT("axes"), TEXT("Missing required array parameter 'axes'"));
			return false;
		}
		if (Axes->Num() != Out.Dimensions)
		{
			OutError = FieldError(TEXT("axes"), FString::Printf(TEXT("'axes' must have exactly %d entr%s for dimensions=%d (got %d)"), Out.Dimensions, Out.Dimensions == 1 ? TEXT("y") : TEXT("ies"), Out.Dimensions, Axes->Num()));
			return false;
		}
		for (int32 i = 0; i < Axes->Num(); ++i)
		{
			const TSharedPtr<FJsonObject>* AxisObj = nullptr;
			if (!(*Axes)[i].IsValid() || !(*Axes)[i]->TryGetObject(AxisObj) || !AxisObj)
			{
				OutError = FieldError(FString::Printf(TEXT("axes[%d]"), i), TEXT("Each axis must be an object {name, min, max, grid, snap?, wrap?}"));
				return false;
			}
			FAxisParams Axis;
			(*AxisObj)->TryGetStringField(TEXT("name"), Axis.Name);
			if (Axis.Name.IsEmpty())
			{
				OutError = FieldError(FString::Printf(TEXT("axes[%d].name"), i), TEXT("Axis 'name' is required"));
				return false;
			}
			double Min = 0.0, Max = 0.0, Grid = 4.0;
			const bool bHasMin = (*AxisObj)->TryGetNumberField(TEXT("min"), Min);
			const bool bHasMax = (*AxisObj)->TryGetNumberField(TEXT("max"), Max);
			if (!bHasMin || !bHasMax)
			{
				OutError = FieldError(FString::Printf(TEXT("axes[%d]"), i), TEXT("Axis 'min' and 'max' are required numbers"));
				return false;
			}
			if (!(Max > Min))
			{
				OutError = FieldError(FString::Printf(TEXT("axes[%d]"), i), FString::Printf(TEXT("Axis '%s': max (%g) must be greater than min (%g)"), *Axis.Name, Max, Min));
				return false;
			}
			(*AxisObj)->TryGetNumberField(TEXT("grid"), Grid);
			if (Grid < 1.0 || Grid > 1000.0 || !FMath::IsNearlyEqual(Grid, FMath::RoundToDouble(Grid)))
			{
				OutError = FieldError(FString::Printf(TEXT("axes[%d].grid"), i), TEXT("Axis 'grid' must be an integer in 1..1000"));
				return false;
			}
			Axis.Min = static_cast<float>(Min);
			Axis.Max = static_cast<float>(Max);
			Axis.GridNum = static_cast<int32>(Grid);
			(*AxisObj)->TryGetBoolField(TEXT("snap"), Axis.bSnapToGrid);
			(*AxisObj)->TryGetBoolField(TEXT("wrap"), Axis.bWrapInput);
			Out.Axes.Add(Axis);
		}

		const TArray<TSharedPtr<FJsonValue>>* Samples = nullptr;
		if (Params->TryGetArrayField(TEXT("samples"), Samples) && Samples)
		{
			for (int32 i = 0; i < Samples->Num(); ++i)
			{
				const TSharedPtr<FJsonObject>* SampleObj = nullptr;
				if (!(*Samples)[i].IsValid() || !(*Samples)[i]->TryGetObject(SampleObj) || !SampleObj)
				{
					OutError = FieldError(FString::Printf(TEXT("samples[%d]"), i), TEXT("Each sample must be an object {animation, value:[x] | [x, y]}"));
					return false;
				}
				FSampleParams Sample;
				(*SampleObj)->TryGetStringField(TEXT("animation"), Sample.AnimationPath);
				if (Sample.AnimationPath.IsEmpty())
				{
					OutError = FieldError(FString::Printf(TEXT("samples[%d].animation"), i), TEXT("Sample 'animation' (AnimSequence path) is required"));
					return false;
				}
				const TArray<TSharedPtr<FJsonValue>>* ValueArr = nullptr;
				if (!(*SampleObj)->TryGetArrayField(TEXT("value"), ValueArr) || !ValueArr || ValueArr->Num() != Out.Dimensions)
				{
					OutError = FieldError(FString::Printf(TEXT("samples[%d].value"), i), FString::Printf(TEXT("Sample 'value' must be an array of %d number(s) for dimensions=%d"), Out.Dimensions, Out.Dimensions));
					return false;
				}
				for (const TSharedPtr<FJsonValue>& V : *ValueArr)
				{
					double D = 0.0;
					if (!V.IsValid() || !V->TryGetNumber(D))
					{
						OutError = FieldError(FString::Printf(TEXT("samples[%d].value"), i), TEXT("Sample 'value' entries must be numbers"));
						return false;
					}
					Sample.Value.Add(D);
				}
				Out.Samples.Add(Sample);
			}
		}
		return true;
	}

	UBlendSpace* CreateBlendSpace(const FCreateParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		check(IsInGameThread());

		const FString PackagePath = AnimMcpAssetResolver::ToPackagePath(Params.AssetPath);
		FText PathReason;
		if (!FPackageName::IsValidLongPackageName(PackagePath, /*bIncludeReadOnlyRoots*/ false, &PathReason))
		{
			OutError = FieldError(TEXT("asset_path"), FString::Printf(TEXT("Invalid package path '%s': %s"), *PackagePath, *PathReason.ToString()));
			return nullptr;
		}
		const FString AssetName = FPackageName::GetLongPackageAssetName(PackagePath);
		const FString ObjectPath = PackagePath + TEXT(".") + AssetName;

		USkeleton* Skeleton = AnimMcpAssetResolver::LoadSkeleton(Params.SkeletonPath, OutError);
		if (!Skeleton) { return nullptr; }

		USkeletalMesh* PreviewMesh = nullptr;
		if (!Params.PreviewMeshPath.IsEmpty())
		{
			PreviewMesh = Cast<USkeletalMesh>(AnimMcpAssetResolver::LoadAssetOfClass(Params.PreviewMeshPath, USkeletalMesh::StaticClass(), OutError));
			if (!PreviewMesh) { return nullptr; }
		}

		// 샘플 사전 검증 — 애셋 생성 전에 전부 거부 (실패해도 빈 애셋을 남기지 않는다)
		struct FResolvedSample { UAnimSequence* Sequence = nullptr; FVector Value = FVector::ZeroVector; };
		TArray<FResolvedSample> Resolved;
		for (int32 i = 0; i < Params.Samples.Num(); ++i)
		{
			const FSampleParams& S = Params.Samples[i];
			FAnimMcpError LoadError;
			UAnimSequence* Sequence = Cast<UAnimSequence>(AnimMcpAssetResolver::LoadAssetOfClass(S.AnimationPath, UAnimSequence::StaticClass(), LoadError));
			if (!Sequence)
			{
				OutError = LoadError;
				if (OutError.Details.IsValid()) { OutError.Details->SetStringField(TEXT("field"), FString::Printf(TEXT("samples[%d].animation"), i)); }
				return nullptr;
			}
			if (!Sequence->GetSkeleton() || !Skeleton->IsCompatibleForEditor(Sequence->GetSkeleton()))
			{
				OutError = SampleError(i, FString::Printf(TEXT("Sample %d '%s' uses skeleton '%s', not compatible with '%s'"), i, *Sequence->GetPathName(), *GetPathNameSafe(Sequence->GetSkeleton()), *Skeleton->GetPathName()), TEXT("SKELETON_MISMATCH"));
				return nullptr;
			}
			FResolvedSample R;
			R.Sequence = Sequence;
			R.Value = FVector(S.Value[0], Params.Dimensions > 1 ? S.Value[1] : 0.0, 0.0);
			for (int32 Axis = 0; Axis < Params.Dimensions; ++Axis)
			{
				const double V = S.Value[Axis];
				if (V < Params.Axes[Axis].Min || V > Params.Axes[Axis].Max)
				{
					OutError = SampleError(i, FString::Printf(TEXT("Sample %d value %g is outside axis '%s' range [%g, %g] (AddSample would silently expand the axis)"), i, V, *Params.Axes[Axis].Name, Params.Axes[Axis].Min, Params.Axes[Axis].Max), TEXT("OUT_OF_RANGE"));
					return nullptr;
				}
			}
			for (int32 j = 0; j < Resolved.Num(); ++j)
			{
				if (SameSamplePoint(Resolved[j].Value, R.Value))
				{
					OutError = SampleError(i, FString::Printf(TEXT("Sample %d has the same position as sample %d"), i, j), TEXT("DUPLICATE_POSITION"));
					return nullptr;
				}
			}
			// (7-3) additive 로 표시됐지만 기준 포즈가 없는 시퀀스(IsValidAdditive false) 는 엔진이 **그 다음** 샘플부터 거부한다
			// (ContainsMatchingSamples, BlendSpace.cpp:2253-2268 — 기존 샘플의 IsValidAdditive 를 본다) → 먼저 거부해 원인을 돌려준다
			if (Sequence->AdditiveAnimType != AAT_None && !Sequence->IsValidAdditive())
			{
				OutError = SampleError(i, FString::Printf(TEXT("Sample %d '%s' is marked %s but is not a valid additive (RefPoseType %s, base pose sequence %s) — fix the sequence's Additive Settings first"), i, *Sequence->GetPathName(), *StaticEnum<EAdditiveAnimationType>()->GetNameStringByValue(static_cast<int64>(Sequence->AdditiveAnimType)), *StaticEnum<EAdditiveBasePoseType>()->GetNameStringByValue(static_cast<int64>(Sequence->RefPoseType)), *GetPathNameSafe(Sequence->RefPoseSeq)), TEXT("ADDITIVE_INVALID"));
				return nullptr;
			}
			// (7-3) AimOffset 은 Mesh-space 회전 additive 만 받는다 — 엔진은 AddSample 에서 INDEX_NONE 으로 거부하므로 먼저 이유를 돌려준다
			if (Params.bAimOffset && Sequence->AdditiveAnimType != AAT_RotationOffsetMeshSpace)
			{
				OutError = SampleError(i, FString::Printf(TEXT("Sample %d '%s' additive type is %s; an AimOffset needs AAT_RotationOffsetMeshSpace (Mesh Space additive)"), i, *Sequence->GetPathName(), *StaticEnum<EAdditiveAnimationType>()->GetNameStringByValue(static_cast<int64>(Sequence->AdditiveAnimType))), TEXT("ADDITIVE_TYPE"));
				return nullptr;
			}
			if (Resolved.Num() > 0 && Resolved[0].Sequence->AdditiveAnimType != Sequence->AdditiveAnimType)
			{
				OutError = SampleError(i, FString::Printf(TEXT("Sample %d additive type differs from sample 0 (all samples must share the additive type)"), i), TEXT("ADDITIVE_MISMATCH"));
				return nullptr;
			}
			Resolved.Add(R);
		}

		// 기존 애셋 — 보호 → 삭제 (AnimMcpAssetOps, Phase 6-2)
		if (AnimMcpAssetResolver::AssetExists(ObjectPath))
		{
			if (!Params.bOverwrite)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetExists, FString::Printf(TEXT("'%s' already exists (pass overwrite=true to replace)"), *ObjectPath));
				return nullptr;
			}
			if (!AnimMcpAssetProtection::EnsureNotProtected(ObjectPath, TEXT("overwrite"), OutError)) { return nullptr; }
			if (!AnimMcpAssetOps::DeleteAssetAtPath(ObjectPath, Context, OutError)) { return nullptr; }
			Context.AddDiagnostic(TEXT("info"), TEXT("ASSET_REPLACED"), FString::Printf(TEXT("Deleted existing '%s' before creating"), *ObjectPath));
		}

		UPackage* Package = CreatePackage(*PackagePath);
		if (!Package)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("CreatePackage failed for '%s'"), *PackagePath));
			return nullptr;
		}
		Package->FullyLoad();
		if (UObject* Stale = FindObject<UObject>(Package, *AssetName))
		{
			const FName StaleName = MakeUniqueObjectName(GetTransientPackage(), Stale->GetClass(), FName(*(AssetName + TEXT("_MCP_STALE"))));
			Stale->ClearFlags(RF_Public | RF_Standalone);
			if (!Stale->Rename(*StaleName.ToString(), GetTransientPackage(), REN_DontCreateRedirectors | REN_NonTransactional | REN_DoNotDirty))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetExists, FString::Printf(TEXT("An object named '%s' still exists in package '%s' and could not be moved aside"), *AssetName, *PackagePath));
				return nullptr;
			}
			Stale->MarkAsGarbage();
			Context.AddDiagnostic(TEXT("info"), TEXT("STALE_OBJECT_MOVED"), FString::Printf(TEXT("In-memory object '%s' survived deletion; moved to transient package before creating"), *AssetName));
		}

		// 팩토리 재현 (EditorFactories.cpp:7357-7363 / :7431-7437; AimOffset 은 :7461-7477 / :7489-7505 — 클래스만 다르다)
		UClass* Class = Params.Dimensions == 1
			? (Params.bAimOffset ? UAimOffsetBlendSpace1D::StaticClass() : UBlendSpace1D::StaticClass())
			: (Params.bAimOffset ? UAimOffsetBlendSpace::StaticClass() : UBlendSpace::StaticClass());
		UBlendSpace* BlendSpace = NewObject<UBlendSpace>(Package, Class, FName(*AssetName), RF_Public | RF_Standalone | RF_Transactional);
		if (!BlendSpace)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("NewObject<UBlendSpace> returned null"));
			return nullptr;
		}
		BlendSpace->SetSkeleton(Skeleton);
		if (PreviewMesh)
		{
			BlendSpace->SetPreviewMesh(PreviewMesh);
		}

		// 축 — Persona 의 디테일 패널과 같은 경로(프로퍼티 시스템) 로 고정 필드만 쓴다
		for (int32 Axis = 0; Axis < Params.Dimensions; ++Axis)
		{
			FBlendParameter* P = AxisPtr(BlendSpace, Axis);
			if (!P)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("UBlendSpace::BlendParameters not found by reflection"));
				return nullptr;
			}
			P->DisplayName = Params.Axes[Axis].Name;
			P->Min = Params.Axes[Axis].Min;
			P->Max = Params.Axes[Axis].Max;
			P->GridNum = Params.Axes[Axis].GridNum;
			P->bSnapToGrid = Params.Axes[Axis].bSnapToGrid;
			P->bWrapInput = Params.Axes[Axis].bWrapInput;
		}
		BlendSpace->PostEditChange();

		// 샘플 — AddSample 은 범위 밖을 늘리므로 위에서 거부했다. 여기서 INDEX_NONE 이면 엔진 측 거부(additive·스켈레톤·중복)
		for (int32 i = 0; i < Resolved.Num(); ++i)
		{
			const int32 Index = BlendSpace->AddSample(Resolved[i].Sequence, Resolved[i].Value);
			if (Index == INDEX_NONE)
			{
				OutError = SampleError(i, FString::Printf(TEXT("UBlendSpace::AddSample rejected sample %d ('%s' at %s)"), i, *Resolved[i].Sequence->GetName(), *Resolved[i].Value.ToString()), TEXT("ENGINE_REJECTED"));
				// 생성 중 실패 — 빈 애셋을 남기지 않는다. (7-3 실측) MarkAsGarbage 만으로는 GC 전까지 AssetExists 가 참이라 다음 create/overwrite 의
				// DeleteAsset 이 실패한다 → 먼저 임시 패키지로 옮겨 경로를 비운다 (위 Stale 처리와 같은 방식)
				BlendSpace->ClearFlags(RF_Public | RF_Standalone);
				const FName GarbageName = MakeUniqueObjectName(GetTransientPackage(), BlendSpace->GetClass(), FName(*(AssetName + TEXT("_MCP_REJECTED"))));
				BlendSpace->Rename(*GarbageName.ToString(), GetTransientPackage(), REN_DontCreateRedirectors | REN_NonTransactional | REN_DoNotDirty);
				BlendSpace->MarkAsGarbage();
				return nullptr;
			}
		}
		// Persona 와 같은 순서 (SAnimationBlendSpace.cpp:192-199)
		BlendSpace->ResampleData();
		BlendSpace->ValidateSampleData();
		BlendSpace->PostEditChange();

		FAssetRegistryModule::AssetCreated(BlendSpace);
		BlendSpace->MarkPackageDirty();

		UE_LOG(LogAnimGraphMcp, Log, TEXT("Created %s %s (skeleton %s, %d axes, %d samples)"), *Class->GetName(), *ObjectPath, *Skeleton->GetName(), Params.Dimensions, Resolved.Num());
		return BlendSpace;
	}

	TSharedRef<FJsonObject> DescribeBlendSpace(UBlendSpace* BlendSpace)
	{
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		Obj->SetStringField(TEXT("asset_path"), BlendSpace->GetPathName());
		Obj->SetStringField(TEXT("class"), BlendSpace->GetClass()->GetName());
		Obj->SetField(TEXT("skeleton"), AnimMcpJson::ObjectPathOrNull(BlendSpace->GetSkeleton()));
		const int32 Dimensions = BlendSpace->IsA<UBlendSpace1D>() ? 1 : 2;
		Obj->SetNumberField(TEXT("dimensions"), Dimensions);
		Obj->SetBoolField(TEXT("aim_offset"), BlendSpace->IsA<UAimOffsetBlendSpace>() || BlendSpace->IsA<UAimOffsetBlendSpace1D>());

		TArray<TSharedPtr<FJsonValue>> Axes;
		for (int32 Axis = 0; Axis < Dimensions; ++Axis)
		{
			const FBlendParameter& P = BlendSpace->GetBlendParameter(Axis);
			TSharedRef<FJsonObject> A = AnimMcpJson::MakeObject();
			A->SetNumberField(TEXT("index"), Axis);
			A->SetStringField(TEXT("name"), P.DisplayName);
			A->SetNumberField(TEXT("min"), P.Min);
			A->SetNumberField(TEXT("max"), P.Max);
			A->SetNumberField(TEXT("grid"), P.GridNum);
			A->SetBoolField(TEXT("snap"), P.bSnapToGrid);
			A->SetBoolField(TEXT("wrap"), P.bWrapInput);
			Axes.Add(MakeShared<FJsonValueObject>(A));
		}
		Obj->SetArrayField(TEXT("axes"), Axes);

		TArray<TSharedPtr<FJsonValue>> Samples;
		const TArray<FBlendSample>& SampleData = BlendSpace->GetBlendSamples();
		for (int32 i = 0; i < SampleData.Num(); ++i)
		{
			const FBlendSample& S = SampleData[i];
			TSharedRef<FJsonObject> SO = AnimMcpJson::MakeObject();
			SO->SetNumberField(TEXT("index"), i);
			SO->SetField(TEXT("animation"), AnimMcpJson::ObjectPathOrNull(S.Animation));
			TArray<TSharedPtr<FJsonValue>> Value;
			Value.Add(MakeShared<FJsonValueNumber>(S.SampleValue.X));
			if (Dimensions > 1) { Value.Add(MakeShared<FJsonValueNumber>(S.SampleValue.Y)); }
			SO->SetArrayField(TEXT("value"), Value);
			SO->SetNumberField(TEXT("rate_scale"), S.RateScale);
#if WITH_EDITORONLY_DATA
			SO->SetBoolField(TEXT("valid"), S.bIsValid != 0);
#endif
			Samples.Add(MakeShared<FJsonValueObject>(SO));
		}
		Obj->SetArrayField(TEXT("samples"), Samples);
		Obj->SetNumberField(TEXT("sample_count"), SampleData.Num());
		// 보간 데이터 — 1D 는 선분, 2D 는 삼각분할(기본) 또는 그리드(bInterpolateUsingGrid, BlendSpace.cpp:2784-2804)
		Obj->SetNumberField(TEXT("grid_sample_count"), BlendSpace->GetGridSamples().Num());
		Obj->SetNumberField(TEXT("segment_count"), BlendSpace->GetBlendSpaceData().Segments.Num());
		Obj->SetNumberField(TEXT("triangle_count"), BlendSpace->GetBlendSpaceData().Triangles.Num());
		Obj->SetBoolField(TEXT("interpolate_using_grid"), BlendSpace->bInterpolateUsingGrid);
		Obj->SetNumberField(TEXT("anim_length"), BlendSpace->AnimLength);
		Obj->SetBoolField(TEXT("loop"), BlendSpace->bLoop);
		return Obj;
	}
}
