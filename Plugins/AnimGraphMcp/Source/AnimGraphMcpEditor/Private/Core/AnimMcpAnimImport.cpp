#include "AnimMcpAnimImport.h"

#include "AnimMcpGeneration.h"
#include "AnimMcpLog.h"
#include "AnimMcpStats.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/AssetData.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "Bridge/AnimMcpTypes.h"
#include "Engine/SkeletalMesh.h"
#include "HAL/PlatformTime.h"
#include "InterchangeGenericAnimationPipeline.h"
#include "InterchangeGenericAssetsPipeline.h"
#include "InterchangeGenericAssetsPipelineSharedSettings.h"
#include "InterchangeGenericMaterialPipeline.h"
#include "InterchangeGenericMeshPipeline.h"
#include "InterchangeGenericTexturePipeline.h"
#include "InterchangeManager.h"
#include "InterchangeProjectSettings.h"
#include "InterchangeResult.h"
#include "InterchangeResultsContainer.h"
#include "InterchangeSourceData.h"
#include "InterchangeTranslatorBase.h"
#include "UObject/Package.h"
#include "UObject/StrongObjectPtr.h"

namespace AnimMcpAnimImport
{
	namespace
	{
		FAnimMcpError ImportError(const TCHAR* Code, const TCHAR* Reason, const FString& Message, TSharedPtr<FJsonObject> Details = nullptr)
		{
			TSharedRef<FJsonObject> D = Details.IsValid() ? Details.ToSharedRef() : AnimMcpJson::MakeObject();
			if (Reason)
			{
				D->SetStringField(TEXT("reason"), Reason);
			}
			return FAnimMcpError::Make(Code, Message, D);
		}

		/** 기본 콘텐츠 스택의 파이프라인 경로 (번역기별 대체 목록이 있으면 그것) */
		TArray<FSoftObjectPath> DefaultStackPipelines(const UInterchangeSourceData& SourceData, const UInterchangeTranslatorBase* Translator, FName& OutStackName)
		{
			const FInterchangeImportSettings& Settings = FInterchangeProjectSettingsUtils::GetDefaultImportSettings(/*bIsSceneImport*/ false);
			OutStackName = FInterchangeProjectSettingsUtils::GetDefaultPipelineStackName(/*bIsSceneImport*/ false, SourceData);
			const FInterchangePipelineStack* Stack = Settings.PipelineStacks.Find(OutStackName);
			if (!Stack)
			{
				return {};
			}
			if (Translator)
			{
				for (const FInterchangeTranslatorPipelines& PerTranslator : Stack->PerTranslatorPipelines)
				{
					if (PerTranslator.Translator.ToSoftObjectPath() == FSoftObjectPath(Translator->GetClass()))
					{
						return PerTranslator.Pipelines;
					}
				}
			}
			return Stack->Pipelines;
		}

		/** 리타깃 소스에 필요한 것만 — 스켈레탈 메시·스켈레톤·애니 */
		void ConfigurePipeline(UInterchangeGenericAssetsPipeline* Pipeline, const FParams& Params)
		{
			if (UInterchangeGenericCommonSkeletalMeshesAndAnimationsProperties* Common = Pipeline->CommonSkeletalMeshesAndAnimationsProperties)
			{
				Common->bAddCurveMetadataToSkeleton = false;
				Common->bImportOnlyAnimations = Params.Skeleton != nullptr;
				Common->Skeleton = Params.Skeleton;
			}
			if (UInterchangeGenericMeshPipeline* Mesh = Pipeline->MeshPipeline)
			{
				Mesh->bImportStaticMeshes = false;
				Mesh->bImportSkeletalMeshes = Params.Skeleton == nullptr;
				Mesh->bCreatePhysicsAsset = false;
			}
			if (UInterchangeGenericMaterialPipeline* Material = Pipeline->MaterialPipeline)
			{
				Material->bImportMaterials = false;
				if (UInterchangeGenericTexturePipeline* Texture = Material->TexturePipeline)
				{
					Texture->bImportTextures = false;
				}
			}
			if (UInterchangeGenericAnimationPipeline* Animation = Pipeline->AnimationPipeline)
			{
				Animation->bImportAnimations = true;
				Animation->bImportBoneTracks = true;
				// 굽는 rate 의 프레임 경계에 안 맞는 길이는 꺼 두면 애니를 건너뛴다(InterchangeGenericAnimationPipeline.cpp:757-807)
				// → 가까운 프레임에 맞춘다 (LENGTH_SNAPPED)
				Animation->bSnapToClosestFrameBoundary = true;
				if (Params.SampleRate > 0)
				{
					Animation->bUse30HzToBakeBoneAnimation = false;
					Animation->CustomBoneAnimationSampleRate = Params.SampleRate;
				}
			}
		}

		/** 길이를 프레임 경계에 맞춘 트랙 — 애니 파이프라인의 Info_ImportLengthSnap 경고. 문구는 에디터 언어로 바뀌므로 원문 키로 찾는다 */
		TArray<FString> SnappedTracks(const UInterchangeResultsContainer* Results)
		{
			TArray<FString> Tracks;
			if (!Results)
			{
				return Tracks;
			}
			for (const UInterchangeResult* Item : Results->GetResults())
			{
				if (!Item || Item->GetResultType() != EInterchangeResultType::Warning || Item->AssetType != UAnimSequence::StaticClass())
				{
					continue;
				}
				TArray<FHistoricTextFormatData> Formats;
				FTextInspector::GetHistoricFormatData(Item->GetText(), Formats);
				if (Formats.ContainsByPredicate([](const FHistoricTextFormatData& Format) { return FTextInspector::GetKey(Format.SourceFmt.GetSourceText()).Get(FString()) == TEXT("Info_ImportLengthSnap"); }))
				{
					Tracks.AddUnique(Item->DestinationAssetName);
				}
			}
			return Tracks;
		}
	}

	TSharedPtr<FJsonObject> Import(const FParams& Params, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		// ---- 대상 폴더는 비어 있어야 한다 (메모리에만 있는 미저장 애셋 포함) ----
		{
			TArray<FAssetData> Existing;
			FAssetRegistryModule::GetRegistry().GetAssetsByPath(FName(*Params.DestPath), Existing, /*bRecursive*/ false, /*bIncludeOnlyOnDiskAssets*/ false);
			if (Existing.Num() > 0)
			{
				TArray<FString> Paths;
				for (const FAssetData& Data : Existing) { Paths.Add(Data.GetObjectPathString()); }
				Paths.Sort();
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("dest_path"), Params.DestPath);
				Details->SetArrayField(TEXT("existing"), AnimMcpGeneration::ToJsonArray(Paths));
				OutError = ImportError(AnimMcpErrorCodes::AssetExists, TEXT("DEST_NOT_EMPTY"),
					FString::Printf(TEXT("'%s' already holds %d asset(s) — import into an empty folder (names produced from an FBX cannot be checked beforehand)"), *Params.DestPath, Paths.Num()), Details);
				return nullptr;
			}
		}

		UInterchangeManager& Manager = UInterchangeManager::GetInterchangeManager();
		TStrongObjectPtr<UInterchangeSourceData> SourceData(UInterchangeManager::CreateSourceData(Params.File));
		if (!SourceData.IsValid() || !Manager.CanTranslateSourceData(SourceData.Get()))
		{
			OutError = ImportError(AnimMcpErrorCodes::ImportFailed, TEXT("NO_TRANSLATOR"), FString::Printf(TEXT("Interchange has no translator for '%s'"), *Params.File));
			return nullptr;
		}

		// ---- 파이프라인: 기본 스택을 트랜지언트로 복제 + 설정 ----
		FName StackName;
		const TArray<FSoftObjectPath> StackPipelines = DefaultStackPipelines(*SourceData, Manager.GetTranslatorForSourceData(SourceData.Get()), StackName);
		if (StackPipelines.Num() == 0)
		{
			OutError = ImportError(AnimMcpErrorCodes::ImportFailed, TEXT("NO_PIPELINE_STACK"), FString::Printf(TEXT("Default content pipeline stack '%s' has no pipelines"), *StackName.ToString()));
			return nullptr;
		}
		TArray<TStrongObjectPtr<UInterchangeGenericAssetsPipeline>> Pipelines;
		FImportAssetParameters ImportParams;
		for (const FSoftObjectPath& Path : StackPipelines)
		{
			UInterchangeGenericAssetsPipeline* Original = Cast<UInterchangeGenericAssetsPipeline>(Path.TryLoad());
			if (!Original)
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("stack"), StackName.ToString());
				Details->SetStringField(TEXT("pipeline"), Path.ToString());
				OutError = ImportError(AnimMcpErrorCodes::ImportFailed, TEXT("UNSUPPORTED_PIPELINE"),
					FString::Printf(TEXT("Pipeline '%s' in stack '%s' is not an InterchangeGenericAssetsPipeline — its settings cannot be made safe"), *Path.ToString(), *StackName.ToString()), Details);
				return nullptr;
			}
			UInterchangeGenericAssetsPipeline* Copy = DuplicateObject<UInterchangeGenericAssetsPipeline>(Original, GetTransientPackage());
			Copy->SetFlags(RF_Transient);
			ConfigurePipeline(Copy, Params);
			Pipelines.Emplace(Copy);
			ImportParams.OverridePipelines.Add(FSoftObjectPath(Copy));
		}
		ImportParams.bIsAutomated = true;
		ImportParams.bReplaceExisting = false;
		ImportParams.DestinationName = Params.Name;

		// ---- 임포트 (동기) ----
		const AnimMcpGeneration::FDirtyGuard Guard;
		const double Start = FPlatformTime::Seconds();
		const UE::Interchange::FAssetImportResultRef ImportResult = Manager.ImportAssetWithResult(Params.DestPath, SourceData.Get(), ImportParams);
		const double Seconds = FPlatformTime::Seconds() - Start;
		TArray<UObject*> Imported = ImportResult->GetImportedObjects();
		const bool bImportOk = ImportResult->IsValid();
		Imported.RemoveAll([](const UObject* Obj) { return !IsValid(Obj); });
		UE_LOG(LogAnimGraphMcp, Log, TEXT("import_animation_file: '%s' -> %s, %d object(s), %.2fs (ok=%d)"), *Params.File, *Params.DestPath, Imported.Num(), Seconds, bImportOk);

		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		TArray<FString> ImportedPaths;
		TArray<TSharedPtr<FJsonValue>> Animations;
		USkeleton* Skeleton = Params.Skeleton;
		USkeletalMesh* Mesh = nullptr;
		TOptional<double> SourceFrameRate;
		for (UObject* Obj : Imported)
		{
			ImportedPaths.Add(Obj->GetPathName());
			if (UAnimSequence* Sequence = Cast<UAnimSequence>(Obj))
			{
				const FFrameRate Rate = Sequence->GetSamplingFrameRate();
				TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
				Item->SetStringField(TEXT("asset"), Sequence->GetPathName());
				Item->SetField(TEXT("skeleton"), AnimMcpJson::ObjectPathOrNull(Sequence->GetSkeleton()));
				Item->SetNumberField(TEXT("frame_rate"), AnimMcpStats::Round(Rate.AsDecimal()));
				Item->SetNumberField(TEXT("frames"), Sequence->GetNumberOfSampledKeys());
				Item->SetNumberField(TEXT("length"), AnimMcpStats::Round(Sequence->GetPlayLength(), 4));
				Animations.Add(MakeShared<FJsonValueObject>(Item));
				if (!SourceFrameRate.IsSet() && Params.SampleRate <= 0)
				{
					SourceFrameRate = Rate.AsDecimal();
				}
				if (Params.Skeleton && Sequence->GetSkeleton() != Params.Skeleton)
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("SKELETON_MISMATCH"), FString::Printf(TEXT("'%s' ended up on '%s', not the requested skeleton"), *Sequence->GetPathName(), *GetPathNameSafe(Sequence->GetSkeleton())));
				}
			}
			else if (USkeleton* NewSkeleton = Cast<USkeleton>(Obj))
			{
				Skeleton = Skeleton ? Skeleton : NewSkeleton;
			}
			else if (USkeletalMesh* NewMesh = Cast<USkeletalMesh>(Obj))
			{
				Mesh = Mesh ? Mesh : NewMesh;
			}
		}
		// 맞춘 뒤 길이는 animations[].length — 잘린 양은 반 프레임 이하
		for (const FString& Track : SnappedTracks(ImportResult->GetResults()))
		{
			const FString Rate = Params.SampleRate > 0 ? FString::Printf(TEXT("%d Hz"), Params.SampleRate) : FString(TEXT("the source rate"));
			TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
			Extra->SetStringField(TEXT("track"), Track);
			Context.AddDiagnostic(TEXT("warning"), TEXT("LENGTH_SNAPPED"),
				FString::Printf(TEXT("'%s' length was not on the frame borders of %s — Interchange moved its start/stop to the closest frames"), *Track, *Rate), Extra);
		}
		ImportedPaths.Sort();
		Animations.Sort([](const TSharedPtr<FJsonValue>& A, const TSharedPtr<FJsonValue>& B) { return A->AsObject()->GetStringField(TEXT("asset")) < B->AsObject()->GetStringField(TEXT("asset")); });

		Result->SetStringField(TEXT("file"), Params.File);
		Result->SetStringField(TEXT("dest_path"), Params.DestPath);
		Result->SetArrayField(TEXT("imported"), AnimMcpGeneration::ToJsonArray(ImportedPaths));
		Result->SetArrayField(TEXT("animations"), Animations);
		Result->SetField(TEXT("skeleton"), AnimMcpJson::ObjectPathOrNull(Skeleton));
		Result->SetBoolField(TEXT("skeleton_created"), Params.Skeleton == nullptr && Skeleton != nullptr);
		Result->SetField(TEXT("mesh"), AnimMcpJson::ObjectPathOrNull(Mesh));
		if (SourceFrameRate.IsSet())
		{
			Result->SetNumberField(TEXT("source_frame_rate"), AnimMcpStats::Round(SourceFrameRate.GetValue()));
		}
		else
		{
			Result->SetField(TEXT("source_frame_rate"), MakeShared<FJsonValueNull>());
		}
		Result->SetNumberField(TEXT("sample_rate"), Params.SampleRate);
		Result->SetStringField(TEXT("pipeline_stack"), StackName.ToString());
		TArray<FString> PipelinePaths;
		for (const FSoftObjectPath& Path : StackPipelines) { PipelinePaths.Add(Path.ToString()); }
		Result->SetArrayField(TEXT("pipelines"), AnimMcpGeneration::ToJsonArray(PipelinePaths));
		Result->SetNumberField(TEXT("seconds"), AnimMcpStats::Round(Seconds));

		if (!bImportOk || Animations.Num() == 0)
		{
			// 실패해도 전역 더티 검사는 한다 — 무엇이 남았는지 함께 보고
			FAnimMcpError DirtyError;
			const bool bClean = Guard.Check(DirtyError);
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("reason"), bImportOk ? TEXT("NO_ANIMATION") : TEXT("INTERCHANGE_FAILED"));
			Details->SetObjectField(TEXT("partial"), Result);
			if (!bClean)
			{
				Details->SetObjectField(TEXT("unexpected_dirty"), DirtyError.Details);
			}
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::ImportFailed,
				bImportOk ? FString::Printf(TEXT("'%s' produced no AnimSequence (%d other object(s) left unsaved in %s)"), *Params.File, Imported.Num(), *Params.DestPath)
				          : FString::Printf(TEXT("Interchange failed to import '%s' (see Output Log, LogInterchange*) — %d object(s) left unsaved"), *Params.File, Imported.Num()),
				Details);
			return nullptr;
		}

		bool bSaved = false;
		if (!AnimMcpGeneration::FinishWrite(Guard, Imported, Params.bSave, Context, OutError, bSaved))
		{
			if (OutError.Details.IsValid())
			{
				OutError.Details->SetObjectField(TEXT("partial"), Result);
			}
			return nullptr;
		}
		Result->SetBoolField(TEXT("saved"), bSaved);
		return Result;
	}
}
