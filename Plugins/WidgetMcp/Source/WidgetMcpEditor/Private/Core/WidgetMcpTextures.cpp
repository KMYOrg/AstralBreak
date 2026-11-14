#include "Core/WidgetMcpTextures.h"

#include "AnimMcpLog.h"
#include "Engine/Texture2D.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "InterchangeGenericAssetsPipeline.h"
#include "InterchangeGenericMaterialPipeline.h"
#include "InterchangeGenericTexturePipeline.h"
#include "InterchangeManager.h"
#include "InterchangeProjectSettings.h"
#include "InterchangeSourceData.h"
#include "InterchangeTranslatorBase.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "TextureCompiler.h"
#include "UObject/StrongObjectPtr.h"

namespace WidgetMcpTextures
{
	namespace TexturesPrivate
	{
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

		void ConfigureTexturePipeline(UInterchangeGenericTexturePipeline* Texture, const FString& Name)
		{
			Texture->bImportTextures = true;
			Texture->bAllowNonPowerOfTwo = true;
			Texture->AssetName = Name;
#if WITH_EDITORONLY_DATA
			Texture->bDetectNormalMapTexture = false;
			Texture->bFlipNormalMapGreenChannel = false;
			Texture->bImportUDIMs = false;
#endif
		}

		template <typename TEnum>
		bool EnumValue(const UEnum* Enum, const FString& Name, TEnum& Out)
		{
			const int64 V = Enum ? Enum->GetValueByNameString(Name) : INDEX_NONE;
			if (V == INDEX_NONE)
			{
				return false;
			}
			Out = static_cast<TEnum>(V);
			return true;
		}

		bool IsValidAssetName(const FString& Name)
		{
			if (Name.IsEmpty() || Name.Len() > 64 || !FChar::IsAlpha(Name[0]))
			{
				return false;
			}
			for (const TCHAR C : Name)
			{
				if (!FChar::IsAlnum(C) && C != TEXT('_'))
				{
					return false;
				}
			}
			return true;
		}
	}

	TSharedRef<FJsonObject> Describe(const UTexture2D* Texture)
	{
		TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
		Obj->SetStringField(TEXT("asset_path"), Texture->GetPathName());
#if WITH_EDITORONLY_DATA
		Obj->SetArrayField(TEXT("size"), { MakeShared<FJsonValueNumber>(Texture->Source.GetSizeX()), MakeShared<FJsonValueNumber>(Texture->Source.GetSizeY()) });
		Obj->SetStringField(TEXT("mip_gen"), StaticEnum<TextureMipGenSettings>()->GetNameStringByValue(Texture->MipGenSettings));
#endif
		Obj->SetStringField(TEXT("compression"), StaticEnum<TextureCompressionSettings>()->GetNameStringByValue(Texture->CompressionSettings));
		Obj->SetStringField(TEXT("lod_group"), StaticEnum<TextureGroup>()->GetNameStringByValue(Texture->LODGroup));
		Obj->SetBoolField(TEXT("never_stream"), Texture->NeverStream != 0);
		Obj->SetBoolField(TEXT("srgb"), Texture->SRGB != 0);
		return Obj;
	}

	TSharedPtr<FJsonObject> Import(const WidgetMcp::FSettings& Settings, const FString& DestFolderIn, const TArray<FRequest>& Requests,
		FEditorMcpContext& Context, FEditorMcpError& OutError)
	{
		using namespace TexturesPrivate;
		const FString DestFolder = EditorMcpGuard::NormalizeFolderPath(DestFolderIn);
		if (!WidgetMcp::CheckRunFolder(Settings, DestFolder, TEXT("dest_path"), OutError))
		{
			return nullptr;
		}
		if (Requests.Num() == 0)
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, TEXT("textures[] is empty"));
			return nullptr;
		}

		// ---- 사전 검증 — 하나라도 어긋나면 아무것도 임포트하지 않는다 -------------------------------------------------------
		struct FPlanned
		{
			FRequest Request;
			FString FullFile;
			FString Package;
			TextureCompressionSettings Compression = TC_EditorIcon;
			TextureGroup LodGroup = TEXTUREGROUP_UI;
			TextureMipGenSettings MipGen = TMGS_NoMipmaps;
		};
		TArray<FPlanned> Planned;
		TSet<FString> Names;
		for (int32 i = 0; i < Requests.Num(); ++i)
		{
			const FRequest& R = Requests[i];
			FPlanned P;
			P.Request = R;
			const FString Field = FString::Printf(TEXT("textures[%d]"), i);
			if (!IsValidAssetName(R.Name) || Names.Contains(R.Name))
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("%s.name '%s' is empty, not [A-Za-z][A-Za-z0-9_]*, or repeated"), *Field, *R.Name), TEXT("BAD_NAME"));
				return nullptr;
			}
			Names.Add(R.Name);
			if (!WidgetMcp::CheckDiskPath(Settings.ImportRoots, R.File, *Field, TEXT("WidgetImportSourceRoots"), P.FullFile, OutError))
			{
				return nullptr;
			}
			if (!FPaths::GetExtension(P.FullFile).Equals(TEXT("png"), ESearchCase::IgnoreCase) || !IFileManager::Get().FileExists(*P.FullFile))
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("%s.file '%s' is not an existing .png"), *Field, *P.FullFile), TEXT("FILE_NOT_FOUND"));
				return nullptr;
			}
			P.Package = DestFolder / R.Name;
			if (!WidgetMcp::CheckOutputAsset(Settings, P.Package, *Field, OutError))
			{
				return nullptr;
			}
			if (WidgetMcp::PackageExists(P.Package))
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::AssetExists, FString::Printf(TEXT("'%s' already exists — textures are never overwritten (new run folder)"), *P.Package), TEXT("OVERWRITE_NOT_ALLOWED"));
				return nullptr;
			}
			if (!EnumValue(StaticEnum<TextureCompressionSettings>(), R.Compression, P.Compression)
				|| !EnumValue(StaticEnum<TextureGroup>(), R.LodGroup, P.LodGroup)
				|| !EnumValue(StaticEnum<TextureMipGenSettings>(), R.MipGen, P.MipGen))
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest,
					FString::Printf(TEXT("%s: unknown compression '%s' / lod_group '%s' / mip_gen '%s'"), *Field, *R.Compression, *R.LodGroup, *R.MipGen), TEXT("BAD_SETTING"));
				return nullptr;
			}
			Planned.Add(P);
		}

		// ---- 임포트 -------------------------------------------------------------------------------------------------
		const WidgetMcp::FWriteGuard Guard;
		UInterchangeManager& Manager = UInterchangeManager::GetInterchangeManager();
		TArray<TSharedPtr<FJsonValue>> Results;
		TArray<FString> ImportedPaths;
		for (const FPlanned& P : Planned)
		{
			const double Start = FPlatformTime::Seconds();
			TStrongObjectPtr<UInterchangeSourceData> Source(UInterchangeManager::CreateSourceData(P.FullFile));
			auto Fail = [&](const TCHAR* Reason, const FString& Message) -> TSharedPtr<FJsonObject>
			{
				TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
				D->SetStringField(TEXT("file"), P.FullFile);
				D->SetArrayField(TEXT("imported_before_failure"), WidgetMcp::StringArray(ImportedPaths));
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::ImportFailed, Message, Reason, D);
				return nullptr;
			};
			if (!Source.IsValid() || !Manager.CanTranslateSourceData(Source.Get()))
			{
				return Fail(TEXT("NO_TRANSLATOR"), FString::Printf(TEXT("Interchange has no translator for '%s'"), *P.FullFile));
			}
			FName StackName;
			const TArray<FSoftObjectPath> StackPipelines = DefaultStackPipelines(*Source, Manager.GetTranslatorForSourceData(Source.Get()), StackName);
			if (StackPipelines.Num() == 0)
			{
				return Fail(TEXT("NO_PIPELINE_STACK"), FString::Printf(TEXT("Default pipeline stack '%s' has no pipelines"), *StackName.ToString()));
			}
			TArray<TStrongObjectPtr<UObject>> Keep;
			FImportAssetParameters Params;
			TArray<FString> PipelineNames;
			for (const FSoftObjectPath& Path : StackPipelines)
			{
				UObject* Original = Path.TryLoad();
				PipelineNames.Add(Path.ToString());
				if (UInterchangeGenericTexturePipeline* Tex = Cast<UInterchangeGenericTexturePipeline>(Original))
				{
					UInterchangeGenericTexturePipeline* Copy = DuplicateObject<UInterchangeGenericTexturePipeline>(Tex, GetTransientPackage());
					Copy->SetFlags(RF_Transient);
					ConfigureTexturePipeline(Copy, P.Request.Name);
					Keep.Emplace(Copy);
					Params.OverridePipelines.Add(FSoftObjectPath(Copy));
				}
				else if (UInterchangeGenericAssetsPipeline* Assets = Cast<UInterchangeGenericAssetsPipeline>(Original))
				{
					UInterchangeGenericAssetsPipeline* Copy = DuplicateObject<UInterchangeGenericAssetsPipeline>(Assets, GetTransientPackage());
					Copy->SetFlags(RF_Transient);
					if (Copy->MaterialPipeline)
					{
						Copy->MaterialPipeline->bImportMaterials = false;
						if (Copy->MaterialPipeline->TexturePipeline)
						{
							ConfigureTexturePipeline(Copy->MaterialPipeline->TexturePipeline, P.Request.Name);
						}
					}
					Keep.Emplace(Copy);
					Params.OverridePipelines.Add(FSoftObjectPath(Copy));
				}
				else
				{
					return Fail(TEXT("UNSUPPORTED_PIPELINE"), FString::Printf(TEXT("Pipeline '%s' in stack '%s' is neither a generic texture nor assets pipeline — its settings cannot be made safe"), *Path.ToString(), *StackName.ToString()));
				}
			}
			Params.bIsAutomated = true;
			Params.bReplaceExisting = false;
			Params.DestinationName = P.Request.Name;

			const UE::Interchange::FAssetImportResultRef Result = Manager.ImportAssetWithResult(EditorMcpGuard::NormalizeFolderPath(DestFolder), Source.Get(), Params);
			UTexture2D* Texture = nullptr;
			for (UObject* Obj : Result->GetImportedObjects())
			{
				if (UTexture2D* T = Cast<UTexture2D>(Obj); T && IsValid(T))
				{
					Texture = T;
					ImportedPaths.Add(T->GetPathName());
				}
				else if (IsValid(Obj))
				{
					ImportedPaths.Add(Obj->GetPathName());
				}
			}
			if (!Result->IsValid() || !Texture)
			{
				return Fail(TEXT("NO_TEXTURE"), FString::Printf(TEXT("Interchange produced no Texture2D from '%s' (see Output Log, LogInterchange*)"), *P.FullFile));
			}
			if (WidgetMcp::ToPackagePath(Texture->GetPathName()) != P.Package)
			{
				Context.AddDiagnostic(TEXT("warning"), TEXT("NAME_CHANGED"), FString::Printf(TEXT("'%s' was imported as '%s'"), *P.Package, *Texture->GetPathName()));
			}

			Texture->PreEditChange(nullptr);
			Texture->CompressionSettings = P.Compression;
			Texture->LODGroup = P.LodGroup;
			Texture->NeverStream = P.Request.bNeverStream;
			Texture->SRGB = P.Request.bSRGB;
#if WITH_EDITORONLY_DATA
			Texture->MipGenSettings = P.MipGen;
			Texture->CompressionNoAlpha = false;
#endif
			Texture->PostEditChange();
			const TArray<UTexture*> Built = { Texture };
			FTextureCompilingManager::Get().FinishCompilation(Built);
			Texture->MarkPackageDirty();

			TSharedRef<FJsonObject> Item = Describe(Texture);
			Item->SetStringField(TEXT("name"), P.Request.Name);
			Item->SetStringField(TEXT("file"), P.FullFile);
			Item->SetStringField(TEXT("pipeline_stack"), StackName.ToString());
			Item->SetArrayField(TEXT("pipelines"), WidgetMcp::StringArray(PipelineNames));
			Item->SetNumberField(TEXT("seconds"), WidgetMcp::Round3(FPlatformTime::Seconds() - Start));
			Results.Add(MakeShared<FJsonValueObject>(Item));
			UE_LOG(LogAnimGraphMcp, Log, TEXT("import_ui_textures: %s -> %s (%s)"), *P.FullFile, *Texture->GetPathName(), *P.Request.Compression);
		}

		TArray<FString> NewlyDirty;
		if (!Guard.Finish(Settings, OutError, NewlyDirty))
		{
			OutError.Details->SetArrayField(TEXT("imported"), WidgetMcp::StringArray(ImportedPaths));
			return nullptr;
		}
		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetStringField(TEXT("dest_path"), DestFolder);
		Out->SetArrayField(TEXT("textures"), Results);
		Out->SetArrayField(TEXT("newly_dirty"), WidgetMcp::StringArray(NewlyDirty));
		Out->SetBoolField(TEXT("saved"), false);
		return Out;
	}
}
