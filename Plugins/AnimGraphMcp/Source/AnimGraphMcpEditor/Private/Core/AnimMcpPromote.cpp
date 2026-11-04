#include "AnimMcpPromote.h"

#include "AnimMcpAssetOps.h"
#include "AnimMcpAssetProtection.h"
#include "AnimMcpAssetResolver.h"
#include "AnimMcpGeneration.h"
#include "AnimMcpLog.h"
#include "Animation/AnimComposite.h"
#include "Animation/AnimData/IAnimationDataModel.h"
#include "Animation/AnimMontage.h"
#include "Animation/AnimSequence.h"
#include "Animation/BlendSpace.h"
#include "Animation/BlendSpace1D.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "AssetToolsModule.h"
#include "Bridge/AnimMcpTypes.h"
#include "Engine/World.h"
#include "FileHelpers.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "IAssetTools.h"
#include "Misc/PackageName.h"
#include "Misc/ScopeExit.h"
#include "Misc/SecureHash.h"
#include "UObject/ObjectRedirector.h"
#include "UObject/ObjectSaveContext.h"
#include "UObject/Package.h"
#include "UObject/UObjectIterator.h"

namespace AnimMcpPromote
{
	namespace
	{
		FAnimMcpError FieldError(const TCHAR* Code, const FString& Field, const TCHAR* Reason, const FString& Message, TSharedPtr<FJsonObject> Extra = nullptr)
		{
			TSharedRef<FJsonObject> Details = Extra.IsValid() ? Extra.ToSharedRef() : AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), Field);
			if (Reason) { Details->SetStringField(TEXT("reason"), Reason); }
			return FAnimMcpError::Make(Code, Message, Details);
		}

		bool IsSupportedClass(const UObject* Asset)
		{
			// 시퀀스 · 몽타주 · 컴포짓 · BlendSpace(1D · AimOffset 은 UBlendSpace 파생)
			return Asset->IsA<UAnimSequence>() || Asset->IsA<UAnimMontage>() || Asset->IsA<UAnimComposite>() || Asset->IsA<UBlendSpace>();
		}

		FString Hex(const FString& Text)
		{
			const FTCHARToUTF8 Utf8(*Text);
			uint8 Digest[FSHA1::DigestSize];
			FSHA1::HashBuffer(Utf8.Get(), Utf8.Length(), Digest);
			return BytesToHex(Digest, FSHA1::DigestSize).ToLower();
		}

		/** 세그먼트 — 참조 애셋은 경로가 아니라 클래스 · 길이만(같이 승격되면 경로가 바뀐다) */
		void AppendTrack(FString& Out, const FAnimTrack& Track)
		{
			for (const FAnimSegment& Segment : Track.AnimSegments)
			{
				const UAnimSequenceBase* Ref = Segment.GetAnimReference();
				Out += FString::Printf(TEXT("[%s %.5f %.5f %.5f %.5f %.4f %d]"), Ref ? *Ref->GetClass()->GetName() : TEXT("-"), Ref ? Ref->GetPlayLength() : 0.f,
					Segment.StartPos, Segment.AnimStartTime, Segment.AnimEndTime, Segment.AnimPlayRate, Segment.LoopingCount);
			}
		}

		struct FReferencer
		{
			FString Package;
			bool bCandidate = false;
			bool bAllowed = false;
			bool bMap = false;
			bool bDirty = false;
			bool bProtected = false;
		};

		struct FPlanned
		{
			TWeakObjectPtr<UObject> Asset;
			FString SourceObject;
			FString SourcePackage;
			FString DestObject;
			FString DestPackage;
			FString ClassName;
			FString Hash;
			TArray<FReferencer> Referencers;
			/** 레지스트리(디스크) 참조자 — 사후 검증에서 dest 를 가리키는지 본다 */
			TArray<FString> RegistryReferencers;
		};

		bool IsMapPackage(const FString& PackageName)
		{
			if (FEditorFileUtils::IsMapPackageAsset(PackageName))
			{
				return true;
			}
			UPackage* Package = FindPackage(nullptr, *PackageName);
			return Package && UWorld::FindWorldInPackage(Package) != nullptr;
		}

		/**
		 * FindCDOReferences(AssetRenameManager.cpp:708-807)의 하드 참조 부분 — 네이티브 클래스 CDO 의 오브젝트 프로퍼티가 가리키면 엔진이
		 * OkCancel 모달(기본 Cancel)로 rename 을 멈춘다 → dry_run 에서도 미리 알린다. 소프트 참조는 실행 때 엔진이 같은 모달로 멈춘다(ENGINE_ABORTED)
		 */
		TArray<FString> FindNativeCdoReferences(const TSet<const UObject*>& Assets)
		{
			TArray<FString> Out;
			for (TObjectIterator<UClass> It; It; ++It)
			{
				UClass* Class = *It;
				if (!Class->HasAnyClassFlags(CLASS_Native) || Class->HasAnyClassFlags(CLASS_Deprecated | CLASS_NewerVersionExists))
				{
					continue;
				}
				UObject* CDO = Class->GetDefaultObject(false);
				if (!CDO || !IsValid(CDO))
				{
					continue;
				}
				for (TFieldIterator<FObjectProperty> Prop(Class); Prop; ++Prop)
				{
					for (int32 Index = 0; Index < Prop->ArrayDim; ++Index)
					{
						const UObject* Value = Prop->GetObjectPropertyValue(Prop->ContainerPtrToValuePtr<void>(CDO, Index));
						if (Value && Assets.Contains(Value))
						{
							Out.AddUnique(FString::Printf(TEXT("%s.%s -> %s"), *Class->GetName(), *Prop->GetName(), *Value->GetPathName()));
						}
					}
				}
			}
			return Out;
		}

		TArray<TSharedPtr<FJsonValue>> DescribeReferencers(const TArray<FReferencer>& Referencers)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			for (const FReferencer& R : Referencers)
			{
				TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
				Obj->SetStringField(TEXT("package"), R.Package);
				Obj->SetBoolField(TEXT("candidate"), R.bCandidate);
				Obj->SetBoolField(TEXT("allowed"), R.bAllowed);
				if (R.bMap) { Obj->SetBoolField(TEXT("map"), true); }
				if (R.bDirty) { Obj->SetBoolField(TEXT("dirty"), true); }
				if (R.bProtected) { Obj->SetBoolField(TEXT("protected"), true); }
				Out.Add(MakeShared<FJsonValueObject>(Obj));
			}
			return Out;
		}

		TSharedRef<FJsonObject> DescribePlanned(const FPlanned& P)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("source"), P.SourceObject);
			Obj->SetStringField(TEXT("dest"), P.DestObject);
			Obj->SetStringField(TEXT("class"), P.ClassName);
			Obj->SetStringField(TEXT("content_hash"), P.Hash);
			Obj->SetArrayField(TEXT("referencers"), DescribeReferencers(P.Referencers));
			return Obj;
		}

		/** 엔진이 옛 패키지를 지우지 못하고 남긴 빈 .uasset — DeleteAssetAtPath 와 같은 방식(링커 끊고 짧게 재시도)으로 지운다 */
		bool RemoveLeftoverFile(const FString& PackageName, const FString& Filename, FString& OutError)
		{
			if (UPackage* Package = FindPackage(nullptr, *PackageName))
			{
				ResetLoaders(Package);
			}
			for (int32 Attempt = 0; Attempt < 10; ++Attempt)
			{
				IFileManager::Get().Delete(*Filename, /*RequireExists*/ false, /*EvenReadOnly*/ true, /*Quiet*/ true);
				if (!IFileManager::Get().FileExists(*Filename))
				{
					FAssetRegistryModule::GetRegistry().ScanModifiedAssetFiles({ Filename });
					return true;
				}
				FPlatformProcess::Sleep(0.3f);
			}
			OutError = FString::Printf(TEXT("'%s' could not be removed (locked by another process?)"), *Filename);
			return false;
		}

		/** 패키지에 애셋(리디렉터가 아닌 공개 객체)이 남아 있는가 */
		bool PackageHoldsAsset(const FString& PackageName)
		{
			const UPackage* Package = FindPackage(nullptr, *PackageName);
			if (!Package)
			{
				return false;
			}
			bool bHolds = false;
			ForEachObjectWithPackage(Package, [&bHolds](UObject* Obj)
			{
				if (Obj->HasAnyFlags(RF_Public) && !Obj->IsA<UObjectRedirector>() && IsValid(Obj))
				{
					bHolds = true;
					return false;
				}
				return true;
			}, /*bIncludeNestedObjects*/ false);
			return bHolds;
		}

		TArray<TSharedPtr<FJsonValue>> MovedArray(const TArray<FPlanned>& Planned, const TArray<bool>& Moved, const TArray<FString>* AfterHash = nullptr)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			for (int32 i = 0; i < Planned.Num(); ++i)
			{
				if (!Moved[i])
				{
					continue;
				}
				TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
				Obj->SetStringField(TEXT("source"), Planned[i].SourceObject);
				Obj->SetStringField(TEXT("dest"), Planned[i].DestObject);
				Obj->SetStringField(TEXT("class"), Planned[i].ClassName);
				if (AfterHash)
				{
					Obj->SetStringField(TEXT("content_hash"), (*AfterHash)[i]);
					Obj->SetBoolField(TEXT("same_content"), (*AfterHash)[i] == Planned[i].Hash);
				}
				Out.Add(MakeShared<FJsonValueObject>(Obj));
			}
			return Out;
		}
	}

	bool ParseRequest(const TSharedRef<FJsonObject>& Params, FRequest& Out, FAnimMcpError& OutError)
	{
		const TArray<TSharedPtr<FJsonValue>>* Assets = nullptr;
		if (!Params->TryGetArrayField(TEXT("assets"), Assets) || !Assets || Assets->Num() == 0)
		{
			OutError = FieldError(AnimMcpErrorCodes::BadRequest, TEXT("assets"), TEXT("MISSING_FIELD"), TEXT("Missing or empty required array 'assets' ([{source, dest}])"));
			return false;
		}
		for (int32 i = 0; i < Assets->Num(); ++i)
		{
			const TSharedPtr<FJsonObject>* Obj = nullptr;
			FItem Item;
			if (!(*Assets)[i].IsValid() || !(*Assets)[i]->TryGetObject(Obj) || !Obj
				|| !(*Obj)->TryGetStringField(TEXT("source"), Item.Source) || !(*Obj)->TryGetStringField(TEXT("dest"), Item.Dest)
				|| Item.Source.TrimStartAndEnd().IsEmpty() || Item.Dest.TrimStartAndEnd().IsEmpty())
			{
				OutError = FieldError(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("assets[%d]"), i), TEXT("BAD_FIELD"), TEXT("Each entry must be {source, dest} (full asset paths)"));
				return false;
			}
			Item.Source = Item.Source.TrimStartAndEnd();
			Item.Dest = Item.Dest.TrimStartAndEnd();
			Out.Items.Add(Item);
		}
		Params->TryGetBoolField(TEXT("dry_run"), Out.bDryRun);
		Params->TryGetBoolField(TEXT("confirm"), Out.bConfirm);
		const TArray<TSharedPtr<FJsonValue>>* Allow = nullptr;
		if (Params->TryGetArrayField(TEXT("allow_referencers"), Allow) && Allow)
		{
			for (int32 i = 0; i < Allow->Num(); ++i)
			{
				FString Path;
				if (!(*Allow)[i].IsValid() || !(*Allow)[i]->TryGetString(Path) || Path.TrimStartAndEnd().IsEmpty())
				{
					OutError = FieldError(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("allow_referencers[%d]"), i), TEXT("BAD_FIELD"), TEXT("allow_referencers entries must be asset or package paths"));
					return false;
				}
				Out.AllowReferencers.AddUnique(AnimMcpGeneration::NormalizeFolderPath(AnimMcpAssetResolver::ToPackagePath(Path)));
			}
		}
		return true;
	}

	bool ValidateDest(const FString& Dest, const FString& Field, FString& OutObjectPath, FAnimMcpError& OutError)
	{
		const FString Trimmed = Dest.TrimStartAndEnd();
		auto Detail = [&Trimmed]()
		{
			TSharedRef<FJsonObject> D = AnimMcpJson::MakeObject();
			D->SetStringField(TEXT("dest"), Trimmed);
			return D;
		};
		if (Trimmed.EndsWith(TEXT("/")))
		{
			OutError = FieldError(AnimMcpErrorCodes::BadRequest, Field, TEXT("DEST_NOT_ASSET_PATH"),
				FString::Printf(TEXT("dest '%s' is a folder — give the full asset path, e.g. /Game/Animation/Hero/<Hero>/<Family>/Actions/AS_<Name>"), *Trimmed), Detail());
			return false;
		}
		const FString Package = AnimMcpAssetResolver::ToPackagePath(Trimmed);
		FText Reason;
		if (!FPackageName::IsValidLongPackageName(Package, /*bIncludeReadOnlyRoots*/ false, &Reason))
		{
			OutError = FieldError(AnimMcpErrorCodes::BadRequest, Field, TEXT("INVALID_PATH"), FString::Printf(TEXT("dest '%s' is not a valid content path (%s)"), *Trimmed, *Reason.ToString()), Detail());
			return false;
		}
		const FString AssetName = FPackageName::GetLongPackageAssetName(Package);
		int32 Dot = INDEX_NONE;
		if (Trimmed.FindLastChar(TEXT('.'), Dot) && Trimmed.Mid(Dot + 1) != AssetName)
		{
			OutError = FieldError(AnimMcpErrorCodes::BadRequest, Field, TEXT("OBJECT_NAME_MISMATCH"), FString::Printf(TEXT("dest '%s': the object name must equal the package name '%s'"), *Trimmed, *AssetName), Detail());
			return false;
		}
		const AnimMcpGeneration::FSettings& Settings = AnimMcpGeneration::GetSettings();
		if (AnimMcpGeneration::IsOutputPathAllowed(Package))
		{
			OutError = FieldError(AnimMcpErrorCodes::OutputPathNotAllowed, Field, TEXT("DEST_IS_CANDIDATE_PATH"),
				FString::Printf(TEXT("dest '%s' is inside [AnimGraphMcp] GenerationOutputPaths — promotion moves assets out of the candidate paths"), *Package), Detail());
			return false;
		}
		if (!AnimMcpGeneration::IsPromotionPathAllowed(Package))
		{
			TSharedRef<FJsonObject> D = Detail();
			D->SetArrayField(TEXT("allowed"), AnimMcpGeneration::ToJsonArray(Settings.PromotionPaths));
			D->SetStringField(TEXT("config"), TEXT("[AnimGraphMcp] PromotionPaths in DefaultEngine.ini"));
			OutError = FieldError(AnimMcpErrorCodes::OutputPathNotAllowed, Field, TEXT("OUTSIDE_PROMOTION_PATHS"),
				Settings.PromotionPaths.Num() == 0
					? FString(TEXT("No [AnimGraphMcp] PromotionPaths configured — promote_animation moves nothing"))
					: FString::Printf(TEXT("dest '%s' is outside [AnimGraphMcp] PromotionPaths"), *Package), D);
			return false;
		}
		FString Rule;
		if (AnimMcpAssetProtection::IsProtected(Package, &Rule))
		{
			TSharedRef<FJsonObject> D = Detail();
			D->SetStringField(TEXT("rule"), Rule);
			OutError = FieldError(AnimMcpErrorCodes::AssetProtected, Field, TEXT("DEST_PROTECTED"), FString::Printf(TEXT("dest '%s' is protected by [AnimGraphMcp] rule '%s'"), *Package, *Rule), D);
			return false;
		}
		const FString ObjectPath = Package + TEXT(".") + AssetName;
		const TCHAR* ExistsReason = nullptr;
		if (AnimMcpAssetResolver::AssetExists(ObjectPath))
		{
			ExistsReason = TEXT("DEST_EXISTS");   // 리디렉터도 레지스트리에 ObjectRedirector 로 있다
		}
		else if (IFileManager::Get().FileExists(*FPackageName::LongPackageNameToFilename(Package, FPackageName::GetAssetPackageExtension())))
		{
			ExistsReason = TEXT("DEST_FILE_EXISTS");
		}
		else if (UPackage* InMemory = FindPackage(nullptr, *Package); InMemory && FindObject<UObject>(InMemory, *AssetName))
		{
			ExistsReason = TEXT("DEST_IN_MEMORY");
		}
		if (ExistsReason)
		{
			OutError = FieldError(AnimMcpErrorCodes::AssetExists, Field, ExistsReason, FString::Printf(TEXT("dest '%s' already exists (%s) — promotion never overwrites"), *ObjectPath, ExistsReason), Detail());
			return false;
		}
		OutObjectPath = ObjectPath;
		return true;
	}

	FString ContentHash(const UObject* Asset)
	{
		FString Summary;
		if (const UAnimSequence* Sequence = Cast<UAnimSequence>(Asset))
		{
			const IAnimationDataModel* Model = Sequence->GetDataModel();
			Summary = FString::Printf(TEXT("seq|%s|add %d %d %d|loop %d|rm %d|rate %.4f|notifies %d"), Model ? *Model->GenerateGuid().ToString() : TEXT("-"),
				static_cast<int32>(Sequence->AdditiveAnimType), static_cast<int32>(Sequence->RefPoseType), Sequence->RefFrameIndex,
				Sequence->bLoop ? 1 : 0, Sequence->bEnableRootMotion ? 1 : 0, Sequence->RateScale, Sequence->Notifies.Num());
		}
		else if (const UAnimMontage* Montage = Cast<UAnimMontage>(Asset))
		{
			Summary = FString::Printf(TEXT("montage|%.5f|blend %.4f %.4f %.4f|notifies %d"), Montage->GetPlayLength(), Montage->GetDefaultBlendInTime(),
				Montage->GetDefaultBlendOutTime(), Montage->BlendOutTriggerTime, Montage->Notifies.Num());
			for (const FSlotAnimationTrack& Track : Montage->SlotAnimTracks)
			{
				Summary += TEXT("|slot ") + Track.SlotName.ToString();
				AppendTrack(Summary, Track.AnimTrack);
			}
			for (const FCompositeSection& Section : Montage->CompositeSections)
			{
				Summary += FString::Printf(TEXT("|section %s %.5f %s"), *Section.SectionName.ToString(), Section.GetTime(), *Section.NextSectionName.ToString());
			}
		}
		else if (const UAnimComposite* Composite = Cast<UAnimComposite>(Asset))
		{
			Summary = FString::Printf(TEXT("composite|%.5f|notifies %d"), Composite->GetPlayLength(), Composite->Notifies.Num());
			AppendTrack(Summary, Composite->AnimationTrack);
		}
		else if (const UBlendSpace* BlendSpace = Cast<UBlendSpace>(Asset))
		{
			const int32 Dimensions = BlendSpace->IsA<UBlendSpace1D>() ? 1 : 2;
			Summary = FString::Printf(TEXT("blendspace|%s|loop %d"), *BlendSpace->GetClass()->GetName(), BlendSpace->bLoop ? 1 : 0);
			for (int32 Axis = 0; Axis < Dimensions; ++Axis)
			{
				const FBlendParameter& P = BlendSpace->GetBlendParameter(Axis);
				Summary += FString::Printf(TEXT("|axis %s %.4f %.4f %d %d %d"), *P.DisplayName, P.Min, P.Max, P.GridNum, P.bSnapToGrid ? 1 : 0, P.bWrapInput ? 1 : 0);
			}
			for (const FBlendSample& Sample : BlendSpace->GetBlendSamples())
			{
				Summary += FString::Printf(TEXT("|sample %.4f %.4f %.4f %.5f"), Sample.SampleValue.X, Sample.SampleValue.Y, Sample.RateScale,
					Sample.Animation ? Sample.Animation->GetPlayLength() : 0.f);
			}
		}
		else
		{
			Summary = Asset ? Asset->GetClass()->GetName() : TEXT("null");
		}
		return Hex(Summary);
	}

	TSharedPtr<FJsonObject> Run(const FRequest& Request, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		check(IsInGameThread());

		if (!Request.bDryRun && !Request.bConfirm)
		{
			OutError = FieldError(AnimMcpErrorCodes::BadRequest, TEXT("confirm"), TEXT("MISSING_CONFIRM"),
				TEXT("promote_animation moves assets and the engine saves the new and referencing packages — pass confirm=true after the user approved a dry_run"));
			return nullptr;
		}
		IAssetRegistry& Registry = FAssetRegistryModule::GetRegistry();
		if (Registry.IsLoadingAssets())
		{
			OutError = FieldError(AnimMcpErrorCodes::PromoteFailed, TEXT("assets"), TEXT("REGISTRY_LOADING"),
				TEXT("The asset registry is still discovering assets — referencers cannot be checked yet (the engine refuses to rename too); retry shortly"));
			return nullptr;
		}

		// ---- 1) 애셋 · 경로 검사 ----
		TArray<FPlanned> Planned;
		TSet<FString> SourcePackages, DestPackages;
		for (int32 i = 0; i < Request.Items.Num(); ++i)
		{
			const FItem& Item = Request.Items[i];
			const FString SourceField = FString::Printf(TEXT("assets[%d].source"), i);
			const FString DestField = FString::Printf(TEXT("assets[%d].dest"), i);
			FPlanned P;
			P.SourceObject = AnimMcpAssetResolver::NormalizeObjectPath(Item.Source);
			P.SourcePackage = AnimMcpAssetResolver::ToPackagePath(P.SourceObject);
			if (!AnimMcpGeneration::IsOutputPathAllowed(P.SourcePackage))
			{
				TSharedRef<FJsonObject> D = AnimMcpJson::MakeObject();
				D->SetStringField(TEXT("source"), P.SourceObject);
				D->SetArrayField(TEXT("candidate_paths"), AnimMcpGeneration::ToJsonArray(AnimMcpGeneration::GetSettings().OutputPaths));
				OutError = FieldError(AnimMcpErrorCodes::OutputPathNotAllowed, SourceField, TEXT("SOURCE_NOT_CANDIDATE"),
					FString::Printf(TEXT("source '%s' is not a candidate (outside [AnimGraphMcp] GenerationOutputPaths) — only generated candidates are promoted"), *P.SourceObject), D);
				return nullptr;
			}
			if (!AnimMcpAssetResolver::AssetExists(P.SourceObject))
			{
				OutError = FieldError(AnimMcpErrorCodes::AssetNotFound, SourceField, nullptr, FString::Printf(TEXT("No asset at '%s'"), *P.SourceObject));
				return nullptr;
			}
			UObject* Asset = LoadObject<UObject>(nullptr, *P.SourceObject);
			if (!Asset)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("Asset registry lists '%s' but it failed to load"), *P.SourceObject));
				return nullptr;
			}
			if (!Asset->GetPathName().Equals(P.SourceObject, ESearchCase::IgnoreCase))
			{
				OutError = FieldError(AnimMcpErrorCodes::BadRequest, SourceField, TEXT("SOURCE_IS_REDIRECTOR"),
					FString::Printf(TEXT("'%s' is a redirector to '%s' — promote the real asset"), *P.SourceObject, *Asset->GetPathName()));
				return nullptr;
			}
			if (!IsSupportedClass(Asset))
			{
				TSharedRef<FJsonObject> D = AnimMcpJson::MakeObject();
				D->SetStringField(TEXT("class"), Asset->GetClass()->GetName());
				OutError = FieldError(AnimMcpErrorCodes::BadRequest, SourceField, TEXT("UNSUPPORTED_CLASS"),
					FString::Printf(TEXT("'%s' is a %s — promote_animation moves AnimSequence · AnimMontage · AnimComposite · BlendSpace (1D · AimOffset) only"), *P.SourceObject, *Asset->GetClass()->GetName()), D);
				return nullptr;
			}
			if (SourcePackages.Contains(P.SourcePackage))
			{
				OutError = FieldError(AnimMcpErrorCodes::BadRequest, SourceField, TEXT("DUPLICATE_SOURCE"), FString::Printf(TEXT("'%s' appears more than once"), *P.SourceObject));
				return nullptr;
			}
			if (!ValidateDest(Item.Dest, DestField, P.DestObject, OutError))
			{
				return nullptr;
			}
			P.DestPackage = AnimMcpAssetResolver::ToPackagePath(P.DestObject);
			if (P.DestPackage.Equals(P.SourcePackage, ESearchCase::IgnoreCase))
			{
				OutError = FieldError(AnimMcpErrorCodes::BadRequest, DestField, TEXT("SAME_PATH"), TEXT("dest equals source"));
				return nullptr;
			}
			if (DestPackages.Contains(P.DestPackage))
			{
				OutError = FieldError(AnimMcpErrorCodes::BadRequest, DestField, TEXT("DUPLICATE_DEST"), FString::Printf(TEXT("dest '%s' appears more than once in this batch"), *P.DestObject));
				return nullptr;
			}
			SourcePackages.Add(P.SourcePackage);
			DestPackages.Add(P.DestPackage);
			P.Asset = Asset;
			P.ClassName = Asset->GetClass()->GetName();
			P.Hash = ContentHash(Asset);
			Planned.Add(MoveTemp(P));
		}

		// ---- 2) 참조자 — 엔진이 고쳐 저장할 패키지. 후보 경로 안은 허용, 밖은 allow_referencers 로 명시해야, 맵 · 이미 더티 · 보호는 거부 ----
		TSet<FString> UsedAllow;
		for (int32 i = 0; i < Planned.Num(); ++i)
		{
			FPlanned& P = Planned[i];
			P.RegistryReferencers = AnimMcpAssetOps::FindReferencers(P.SourceObject);
			for (const FString& Package : AnimMcpAssetOps::FindReferencersIncludingMemory(P.SourceObject))
			{
				if (SourcePackages.Contains(Package))
				{
					continue;   // 같이 옮기는 애셋 — 엔진이 배치 안 참조로 고친다
				}
				FReferencer R;
				R.Package = Package;
				R.bCandidate = AnimMcpGeneration::IsOutputPathAllowed(Package);
				const bool bListed = Request.AllowReferencers.ContainsByPredicate([&Package](const FString& A) { return A.Equals(Package, ESearchCase::IgnoreCase); });
				if (bListed) { UsedAllow.Add(Package); }
				R.bAllowed = R.bCandidate || bListed;
				R.bMap = IsMapPackage(Package);
				const UPackage* Loaded = FindPackage(nullptr, *Package);
				R.bDirty = Loaded && Loaded->IsDirty();
				R.bProtected = AnimMcpAssetProtection::IsProtected(Package);
				P.Referencers.Add(R);
			}
		}
		auto RefError = [&Planned](const TCHAR* Code, const TCHAR* Reason, TFunctionRef<bool(const FReferencer&)> Pred, const FString& Message)
		{
			TArray<TSharedPtr<FJsonValue>> Offending;
			for (const FPlanned& P : Planned)
			{
				for (const FReferencer& R : P.Referencers)
				{
					if (Pred(R))
					{
						TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
						Obj->SetStringField(TEXT("source"), P.SourceObject);
						Obj->SetStringField(TEXT("package"), R.Package);
						Obj->SetBoolField(TEXT("candidate"), R.bCandidate);
						Offending.Add(MakeShared<FJsonValueObject>(Obj));
					}
				}
			}
			if (Offending.Num() == 0)
			{
				return FAnimMcpError();
			}
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("reason"), Reason);
			Details->SetArrayField(TEXT("referencers"), Offending);
			return FAnimMcpError::Make(Code, FString::Printf(TEXT("%s (%d referencer(s), first: %s)"), *Message, Offending.Num(), *Offending[0]->AsObject()->GetStringField(TEXT("package"))), Details);
		};
		{
			FAnimMcpError Error = RefError(AnimMcpErrorCodes::AssetReferenced, TEXT("REFERENCED_BY_MAP"), [](const FReferencer& R) { return R.bMap; },
				TEXT("A map references the asset — the engine would leave a redirector (AssetRenameManager.cpp:1032)"));
			if (!Error.IsSet())
			{
				Error = RefError(AnimMcpErrorCodes::AssetProtected, TEXT("REFERENCER_PROTECTED"), [](const FReferencer& R) { return R.bProtected; },
					TEXT("A protected asset ([AnimGraphMcp] ProtectedAssets/ProtectedPaths) references the asset — the engine would modify and save it"));
			}
			if (!Error.IsSet())
			{
				Error = RefError(AnimMcpErrorCodes::DirtyPackages, TEXT("REFERENCER_DIRTY"), [](const FReferencer& R) { return R.bDirty; },
					TEXT("A referencing package has unsaved changes — the engine would save it together with someone else's edits; save or discard it first"));
			}
			if (!Error.IsSet())
			{
				Error = RefError(AnimMcpErrorCodes::AssetReferenced, TEXT("REFERENCED_OUTSIDE_CANDIDATES"), [](const FReferencer& R) { return !R.bAllowed; },
					TEXT("Packages outside the candidate paths reference the asset — the engine would fix and save them; list them in allow_referencers after the user agreed"));
			}
			if (Error.IsSet())
			{
				OutError = Error;
				return nullptr;
			}
		}
		for (const FString& Allow : Request.AllowReferencers)
		{
			if (!UsedAllow.Contains(Allow))
			{
				Context.AddDiagnostic(TEXT("warning"), TEXT("ALLOW_REFERENCER_UNUSED"), FString::Printf(TEXT("allow_referencers entry '%s' does not reference any promoted asset"), *Allow));
			}
		}

		// ---- 3) 네이티브 CDO 참조 — 엔진이 모달로 멈추는 경우를 미리 ----
		{
			TSet<const UObject*> Assets;
			for (const FPlanned& P : Planned) { Assets.Add(P.Asset.Get()); }
			const TArray<FString> Cdo = FindNativeCdoReferences(Assets);
			if (Cdo.Num() > 0)
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("reason"), TEXT("CDO_REFERENCED"));
				Details->SetArrayField(TEXT("references"), AnimMcpGeneration::ToJsonArray(Cdo));
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PromoteFailed,
					FString::Printf(TEXT("A native class default object references the asset (%s) — the engine stops the rename (source/config may need edits)"), *Cdo[0]), Details);
				return nullptr;
			}
		}

		TArray<TSharedPtr<FJsonValue>> PlannedJson;
		for (const FPlanned& P : Planned) { PlannedJson.Add(MakeShared<FJsonValueObject>(DescribePlanned(P))); }
		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetBoolField(TEXT("dry_run"), Request.bDryRun);
		Result->SetArrayField(TEXT("planned"), PlannedJson);
		if (Request.bDryRun)
		{
			Result->SetArrayField(TEXT("moved"), TArray<TSharedPtr<FJsonValue>>());
			return Result;
		}

		// ---- 4) 엔진 rename — 대화상자 없는 경로, 모달은 기본값 ----
		const AnimMcpGeneration::FDirtyGuard Guard;
		TArray<FString> SavedPackages;
		const FDelegateHandle SavedHandle = UPackage::PackageSavedWithContextEvent.AddLambda(
			[&SavedPackages](const FString&, UPackage* Package, FObjectPostSaveContext) { if (Package) { SavedPackages.AddUnique(Package->GetName()); } });
		ON_SCOPE_EXIT { UPackage::PackageSavedWithContextEvent.Remove(SavedHandle); };

		IAssetTools& AssetTools = FAssetToolsModule::GetModule().Get();
		TArray<FAssetRenameData> RenameData;
		for (const FPlanned& P : Planned)
		{
			RenameData.Emplace(P.Asset, FPackageName::GetLongPackagePath(P.DestPackage), FPackageName::GetLongPackageAssetName(P.DestPackage));
		}
		bool bRenamed = false;
		{
			TGuardValue<bool> Unattended(GIsRunningUnattendedScript, true);
			bRenamed = AssetTools.RenameAssets(RenameData);
		}
		TArray<bool> Moved;
		int32 MovedCount = 0;
		for (const FPlanned& P : Planned)
		{
			const bool bMoved = P.Asset.IsValid() && P.Asset->GetPathName().Equals(P.DestObject, ESearchCase::IgnoreCase);
			Moved.Add(bMoved);
			MovedCount += bMoved ? 1 : 0;
		}
		auto MovedDetails = [&](const TCHAR* Reason)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("reason"), Reason);
			Details->SetArrayField(TEXT("moved"), MovedArray(Planned, Moved));
			Details->SetArrayField(TEXT("saved_packages"), AnimMcpGeneration::ToJsonArray(SavedPackages));
			return Details;
		};
		if (!bRenamed || MovedCount < Planned.Num())
		{
			const TCHAR* Reason = Registry.IsLoadingAssets() ? TEXT("REGISTRY_LOADING") : (MovedCount == 0 ? TEXT("ENGINE_ABORTED") : TEXT("ENGINE"));
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PromoteFailed,
				MovedCount == 0
					? FString(TEXT("The engine renamed nothing (it aborted before moving — e.g. a class default object soft-references the asset, or a package is read-only; see LogAssetTools)"))
					: FString::Printf(TEXT("The engine moved %d of %d asset(s) (see LogAssetTools) — the moved ones are listed in details.moved"), MovedCount, Planned.Num()),
				MovedDetails(Reason));
			return nullptr;
		}

		// ---- 5) 사후 검증 — 리디렉터 · 옛 파일 · dest · 내용 · 참조 · 더티 / 저장 ----
		TArray<UObjectRedirector*> Redirectors;
		auto FindRedirectors = [&]()
		{
			Redirectors.Reset();
			for (const FPlanned& P : Planned)
			{
				const FAssetData Data = Registry.GetAssetByObjectPath(FSoftObjectPath(P.SourceObject), /*bIncludeOnlyOnDiskAssets*/ false);
				UObjectRedirector* Redirector = FindObject<UObjectRedirector>(nullptr, *P.SourceObject);
				if (!Redirector && Data.IsValid() && Data.IsRedirector())
				{
					Redirector = Cast<UObjectRedirector>(StaticLoadObject(UObjectRedirector::StaticClass(), nullptr, *P.SourceObject, nullptr, LOAD_NoRedirects));
				}
				if (Redirector && IsValid(Redirector))
				{
					Redirectors.AddUnique(Redirector);
				}
			}
		};
		FindRedirectors();
		const int32 FixedRedirectors = Redirectors.Num();
		if (Redirectors.Num() > 0)
		{
			Context.AddDiagnostic(TEXT("warning"), TEXT("REDIRECTOR_FIXUP"), FString::Printf(TEXT("The engine left %d redirector(s) — fixing up referencers and deleting them"), Redirectors.Num()));
			TGuardValue<bool> Unattended(GIsRunningUnattendedScript, true);
			AssetTools.FixupReferencers(Redirectors, /*bCheckoutDialogPrompt*/ false, ERedirectFixupMode::DeleteFixedUpRedirectors);
			FindRedirectors();
		}
		if (Redirectors.Num() > 0)
		{
			TSharedRef<FJsonObject> Details = MovedDetails(TEXT("REDIRECTOR_LEFT"));
			TArray<FString> Names;
			for (const UObjectRedirector* R : Redirectors) { Names.Add(R->GetPathName()); }
			Details->SetArrayField(TEXT("redirectors"), AnimMcpGeneration::ToJsonArray(Names));
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PromoteFailed, FString::Printf(TEXT("%d redirector(s) remain after fixup (first: %s)"), Names.Num(), *Names[0]), Details);
			return nullptr;
		}

		TArray<FString> RemovedFiles;
		for (const FPlanned& P : Planned)
		{
			const FString OldFile = FPackageName::LongPackageNameToFilename(P.SourcePackage, FPackageName::GetAssetPackageExtension());
			if (!IFileManager::Get().FileExists(*OldFile))
			{
				continue;
			}
			// 엔진은 아직 참조되는 옛 패키지를 지우지 않고 남긴다(ObjectTools CleanupAfterSuccessfulDelete) — 애셋이 없을 때만 파일을 지운다
			FString RemoveError;
			if (PackageHoldsAsset(P.SourcePackage) || !RemoveLeftoverFile(P.SourcePackage, OldFile, RemoveError))
			{
				TSharedRef<FJsonObject> Details = MovedDetails(TEXT("OLD_FILE_LEFT"));
				Details->SetStringField(TEXT("file"), OldFile);
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PromoteFailed,
					FString::Printf(TEXT("The old package file %s is still on disk%s"), *OldFile, RemoveError.IsEmpty() ? TEXT(" and still holds an asset") : *(TEXT(": ") + RemoveError)), Details);
				return nullptr;
			}
			RemovedFiles.Add(OldFile);
		}

		TArray<FString> AfterHash;
		for (int32 i = 0; i < Planned.Num(); ++i)
		{
			const FPlanned& P = Planned[i];
			UObject* Dest = LoadObject<UObject>(nullptr, *P.DestObject);
			if (!Dest || Dest->GetClass()->GetName() != P.ClassName)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PromoteFailed, FString::Printf(TEXT("'%s' is missing or not a %s after the rename"), *P.DestObject, *P.ClassName), MovedDetails(TEXT("DEST_MISSING")));
				return nullptr;
			}
			AfterHash.Add(ContentHash(Dest));
			if (AfterHash.Last() != P.Hash)
			{
				Context.AddDiagnostic(TEXT("warning"), TEXT("CONTENT_CHANGED"), FString::Printf(TEXT("%s content hash differs after the move (%s → %s)"), *P.DestObject, *P.Hash, *AfterHash.Last()));
			}
		}

		// 저장된 참조자 · 새 패키지를 레지스트리에 다시 읽힌다(의존성은 디스크 기준) → dest 를 가리키는지
		{
			TArray<FString> Files;
			for (const FString& Package : SavedPackages)
			{
				const FString File = FPackageName::LongPackageNameToFilename(Package, FPackageName::GetAssetPackageExtension());
				if (IFileManager::Get().FileExists(*File)) { Files.Add(File); }
			}
			if (Files.Num() > 0) { Registry.ScanModifiedAssetFiles(Files); }
		}
		TMap<FString, FString> OldToNew;
		for (const FPlanned& P : Planned) { OldToNew.Add(P.SourcePackage, P.DestPackage); }
		TArray<TSharedPtr<FJsonValue>> MissingRefs;
		for (const FPlanned& P : Planned)
		{
			const TArray<FString> Now = AnimMcpAssetOps::FindReferencers(P.DestObject);
			for (const FString& Before : P.RegistryReferencers)
			{
				const FString* Mapped = OldToNew.Find(Before);
				const FString Expected = Mapped ? *Mapped : Before;
				if (!Now.ContainsByPredicate([&Expected](const FString& N) { return N.Equals(Expected, ESearchCase::IgnoreCase); }))
				{
					TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
					Obj->SetStringField(TEXT("dest"), P.DestObject);
					Obj->SetStringField(TEXT("referencer"), Expected);
					MissingRefs.Add(MakeShared<FJsonValueObject>(Obj));
				}
			}
		}
		if (MissingRefs.Num() > 0)
		{
			TSharedRef<FJsonObject> Details = MovedDetails(TEXT("REFERENCES_NOT_UPDATED"));
			Details->SetArrayField(TEXT("missing"), MissingRefs);
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PromoteFailed, FString::Printf(TEXT("%d referencer(s) no longer reference the promoted asset on disk"), MissingRefs.Num()), Details);
			return nullptr;
		}

		// 전역 더티 · 엔진이 저장한 패키지 — 허용 목록 ∪ dest ∪ allow_referencers 밖이면 알린다(엔진이 저장까지 끝낸 뒤라 되돌리지 않는다)
		TSet<FName> ExtraAllowed;
		for (const FPlanned& P : Planned) { ExtraAllowed.Add(FName(*P.DestPackage)); }
		for (const FString& Allow : Request.AllowReferencers) { ExtraAllowed.Add(FName(*Allow)); }
		TArray<FString> UnexpectedSaved;
		for (const FString& Package : SavedPackages)
		{
			if (!AnimMcpGeneration::IsOutputPathAllowed(Package) && !ExtraAllowed.Contains(FName(*Package)))
			{
				UnexpectedSaved.Add(Package);
			}
		}
		FAnimMcpError DirtyError;
		if (!Guard.Check(DirtyError, &ExtraAllowed) || UnexpectedSaved.Num() > 0)
		{
			TSharedRef<FJsonObject> Details = DirtyError.Details.IsValid() ? DirtyError.Details.ToSharedRef() : AnimMcpJson::MakeObject();
			Details->SetArrayField(TEXT("moved"), MovedArray(Planned, Moved, &AfterHash));
			Details->SetArrayField(TEXT("unexpected_saved"), AnimMcpGeneration::ToJsonArray(UnexpectedSaved));
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::UnexpectedDirty,
				FString::Printf(TEXT("The rename touched packages outside the candidate paths, the destinations and allow_referencers (%s) — the move is done and was not reverted"),
					UnexpectedSaved.Num() > 0 ? *UnexpectedSaved[0] : *DirtyError.Message), Details);
			return nullptr;
		}

		TArray<FString> Fixed;
		for (const FPlanned& P : Planned)
		{
			for (const FReferencer& R : P.Referencers)
			{
				if (SavedPackages.Contains(R.Package)) { Fixed.AddUnique(R.Package); }
			}
		}
		Fixed.Sort();
		SavedPackages.Sort();
		Result->SetArrayField(TEXT("moved"), MovedArray(Planned, Moved, &AfterHash));
		Result->SetArrayField(TEXT("fixed_referencers"), AnimMcpGeneration::ToJsonArray(Fixed));
		Result->SetArrayField(TEXT("saved_packages"), AnimMcpGeneration::ToJsonArray(SavedPackages));
		Result->SetNumberField(TEXT("redirectors"), 0);
		Result->SetNumberField(TEXT("fixed_redirectors"), FixedRedirectors);
		Result->SetArrayField(TEXT("removed_files"), AnimMcpGeneration::ToJsonArray(RemovedFiles));
		UE_LOG(LogAnimGraphMcp, Log, TEXT("promote_animation: moved %d asset(s), saved %d package(s), fixed %d referencer(s)"), Planned.Num(), SavedPackages.Num(), Fixed.Num());
		return Result;
	}
}
