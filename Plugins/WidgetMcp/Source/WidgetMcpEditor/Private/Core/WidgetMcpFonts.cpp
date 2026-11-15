#include "Core/WidgetMcpFonts.h"

#include "AnimMcpLog.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Editor.h"
#include "Engine/Font.h"
#include "Engine/FontFace.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "PackageTools.h"
#include "Subsystems/EditorAssetSubsystem.h"
#include "UObject/Package.h"
#include "UObject/UObjectHash.h"

namespace WidgetMcpFonts
{
	namespace FontsPrivate
	{
		constexpr int64 MaxFontBytes = 64ll * 1024 * 1024;
		constexpr int32 MaxFaces = 8;

		bool IsIdentifier(const FString& S, int32 MaxLen)
		{
			if (S.IsEmpty() || S.Len() > MaxLen || !FChar::IsAlpha(S[0]))
			{
				return false;
			}
			for (const TCHAR C : S)
			{
				if (!FChar::IsAlnum(C) && C != TEXT('_'))
				{
					return false;
				}
			}
			return true;
		}

		/** TrueType 0x00010000 · 'true' · OpenType CFF 'OTTO' · 컬렉션 'ttcf' */
		bool LooksLikeFont(const TArray<uint8>& Data)
		{
			if (Data.Num() < 12)
			{
				return false;
			}
			const uint32 Tag = (uint32(Data[0]) << 24) | (uint32(Data[1]) << 16) | (uint32(Data[2]) << 8) | uint32(Data[3]);
			return Tag == 0x00010000u || Tag == 0x74727565u /*true*/ || Tag == 0x4F54544Fu /*OTTO*/ || Tag == 0x74746366u /*ttcf*/;
		}

		/** 만든 패키지를 내린다(저장 전 실패 — 아무것도 남기지 않음) */
		void Unload(const TArray<UPackage*>& Packages)
		{
			if (Packages.Num() == 0)
			{
				return;
			}
			for (UPackage* P : Packages)
			{
				ForEachObjectWithPackage(P, [](UObject* Obj) { if (Obj->IsAsset()) { FAssetRegistryModule::AssetDeleted(Obj); } return true; }, /*bIncludeNestedObjects*/ false);
			}
			FText Ignored;
			UPackageTools::UnloadPackages(Packages, Ignored, /*bUnloadDirtyPackages*/ true);
		}
	}

	using namespace FontsPrivate;

	const TArray<FString>& AllowedTypefaces()
	{
		// WidgetMcpSpec.cpp Weights() 의 값(굵기 → 타입페이스 이름)과 같아야 한다 — spec font.weight 가 이 이름으로 타입페이스를 고른다
		static const TArray<FString> Names = { TEXT("Regular"), TEXT("Bold"), TEXT("Light"), TEXT("Italic"), TEXT("Bold Italic") };
		return Names;
	}

	TSharedPtr<FJsonObject> ImportFamily(const WidgetMcp::FSettings& Settings, const FRequest& Request, FEditorMcpContext& Context, FEditorMcpError& OutError)
	{
		// ---- 사전 검사(아무것도 만들기 전) -------------------------------------------------------------------------------
		const FString Dest = EditorMcpGuard::NormalizeFolderPath(Request.DestFolder);
		{
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetStringField(TEXT("field"), TEXT("dest_path"));
			D->SetStringField(TEXT("path"), Dest);
			D->SetArrayField(TEXT("allowed"), WidgetMcp::StringArray(Settings.FontOutputPaths));
			if (!FPackageName::IsValidLongPackageName(Dest, false) || Dest.Contains(TEXT(".")))
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' is not a valid folder path"), *Dest), TEXT("BAD_PATH"), D);
				return nullptr;
			}
			const FString AsDir = Dest + TEXT("/");
			const bool bInside = Settings.FontOutputPaths.ContainsByPredicate([&AsDir](const FString& P) { return AsDir.StartsWith(P, ESearchCase::IgnoreCase) && AsDir.Len() > P.Len(); });
			if (!bInside)
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::OutputPathNotAllowed,
					FString::Printf(TEXT("'%s' must be a folder below [WidgetMcp] WidgetFontOutputPaths (%s)"), *Dest, *FString::Join(Settings.FontOutputPaths, TEXT(", "))), nullptr, D);
				return nullptr;
			}
		}
		if (!IsIdentifier(Request.Family, 48))
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("family '%s' must be an identifier (letters, digits, '_' — max 48)"), *Request.Family), TEXT("BAD_NAME"));
			return nullptr;
		}
		if (Request.Faces.Num() == 0 || Request.Faces.Num() > MaxFaces)
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("faces[] needs 1..%d entries"), MaxFaces));
			return nullptr;
		}

		struct FPlanned
		{
			FFace Face;
			FString FullPath;
			FString AssetName;
			FString Package;
			TArray<uint8> Bytes;
		};
		TArray<FPlanned> Plan;
		TSet<FString> SeenTypefaces;
		for (const FFace& F : Request.Faces)
		{
			if (!AllowedTypefaces().Contains(F.Typeface))
			{
				TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
				D->SetArrayField(TEXT("allowed"), WidgetMcp::StringArray(AllowedTypefaces()));
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest,
					FString::Printf(TEXT("typeface '%s' is not one the spec weight vocabulary selects (%s)"), *F.Typeface, *FString::Join(AllowedTypefaces(), TEXT(", "))), TEXT("BAD_TYPEFACE"), D);
				return nullptr;
			}
			if (SeenTypefaces.Contains(F.Typeface))
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("typeface '%s' appears twice"), *F.Typeface), TEXT("DUPLICATE_TYPEFACE"));
				return nullptr;
			}
			SeenTypefaces.Add(F.Typeface);
			FPlanned P;
			P.Face = F;
			if (!WidgetMcp::CheckDiskPath(Settings.ImportRoots, F.File, TEXT("faces[].file"), TEXT("WidgetImportSourceRoots"), P.FullPath, OutError))
			{
				return nullptr;
			}
			const FString Ext = FPaths::GetExtension(P.FullPath).ToLower();
			if (Ext != TEXT("ttf") && Ext != TEXT("otf") && Ext != TEXT("ttc") && Ext != TEXT("otc"))
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' is not a .ttf/.otf/.ttc/.otc file"), *P.FullPath), TEXT("BAD_FILE"));
				return nullptr;
			}
			const int64 Size = IFileManager::Get().FileSize(*P.FullPath);
			if (Size <= 0 || Size > MaxFontBytes || !FFileHelper::LoadFileToArray(P.Bytes, *P.FullPath) || !LooksLikeFont(P.Bytes))
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::ImportFailed, FString::Printf(TEXT("'%s' is missing, too large or not a font file (%lld bytes)"), *P.FullPath, Size), TEXT("BAD_FILE"));
				return nullptr;
			}
			P.AssetName = FString::Printf(TEXT("FF_%s_%s"), *Request.Family, *F.Typeface.Replace(TEXT(" "), TEXT("")));
			P.Package = Dest / P.AssetName;
			Plan.Add(MoveTemp(P));
		}
		const FString FamilyName = FString::Printf(TEXT("F_%s"), *Request.Family);
		const FString FamilyPackage = Dest / FamilyName;
		{
			TArray<FString> Existing;
			if (WidgetMcp::PackageExists(FamilyPackage)) { Existing.Add(FamilyPackage); }
			for (const FPlanned& P : Plan) { if (WidgetMcp::PackageExists(P.Package)) { Existing.Add(P.Package); } }
			if (Existing.Num())
			{
				TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
				D->SetArrayField(TEXT("existing"), WidgetMcp::StringArray(Existing));
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::AssetExists,
					FString::Printf(TEXT("%d target asset(s) already exist — fonts are never overwritten (nothing was created)"), Existing.Num()), TEXT("OVERWRITE_NOT_ALLOWED"), D);
				return nullptr;
			}
		}

		// ---- 만들기 ------------------------------------------------------------------------------------------------------
		const EditorMcpGuard::FDirtySnapshot Snapshot;
		TArray<UPackage*> Created;
		TArray<UFontFace*> Faces;
		TArray<TSharedPtr<FJsonValue>> FaceJson;
		const EObjectFlags Flags = RF_Public | RF_Standalone | RF_Transactional;
		for (FPlanned& P : Plan)
		{
			UPackage* Pkg = CreatePackage(*P.Package);
			Created.Add(Pkg);
			UFontFace* Face = NewObject<UFontFace>(Pkg, *P.AssetName, Flags);
			Face->SourceFilename = P.FullPath;
			const int32 Bytes = P.Bytes.Num();
			Face->FontFaceData->SetData(MoveTemp(P.Bytes));
			Face->CacheSubFaces();
			if (Face->SubFaces.Num() == 0)
			{
				Unload(Created);
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::ImportFailed, FString::Printf(TEXT("'%s' has no readable font face (FreeType found no sub-faces) — nothing was created"), *P.FullPath), TEXT("BAD_FONT"));
				return nullptr;
			}
			FAssetRegistryModule::AssetCreated(Face);
			Pkg->MarkPackageDirty();
			Faces.Add(Face);
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			J->SetStringField(TEXT("asset_path"), Face->GetPathName());
			J->SetStringField(TEXT("typeface"), P.Face.Typeface);
			J->SetStringField(TEXT("file"), P.FullPath);
			J->SetNumberField(TEXT("bytes"), Bytes);
			J->SetArrayField(TEXT("sub_faces"), WidgetMcp::StringArray(Face->SubFaces));
			FaceJson.Add(MakeShared<FJsonValueObject>(J));
		}
		UPackage* FamilyPkg = CreatePackage(*FamilyPackage);
		Created.Add(FamilyPkg);
		UFont* Font = NewObject<UFont>(FamilyPkg, *FamilyName, Flags);
		Font->FontCacheType = EFontCacheType::Runtime;   // UFontFactory::FactoryCreateNew(EditorFactories.cpp:5047)와 같음
		FCompositeFont& Composite = Font->GetMutableInternalCompositeFont();
		Composite.DefaultTypeface.Fonts.Reset();
		TArray<FString> Typefaces;
		for (int32 i = 0; i < Faces.Num(); ++i)
		{
			FTypefaceEntry& Entry = Composite.DefaultTypeface.Fonts.AddDefaulted_GetRef();
			Entry.Name = FName(*Plan[i].Face.Typeface);
			Entry.Font = FFontData(Faces[i]);
			Typefaces.Add(Plan[i].Face.Typeface);
		}
		FAssetRegistryModule::AssetCreated(Font);
		FamilyPkg->MarkPackageDirty();

		TArray<FString> NewlyDirty, Unexpected;
		Snapshot.GetNewlyDirty(Settings.FontOutputPaths, NewlyDirty, Unexpected);
		if (Unexpected.Num())
		{
			Unload(Created);
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetArrayField(TEXT("unexpected"), WidgetMcp::StringArray(Unexpected));
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::UnexpectedDirty,
				FString::Printf(TEXT("%d package(s) outside [WidgetMcp] WidgetFontOutputPaths became dirty — the new font assets were unloaded"), Unexpected.Num()), nullptr, D);
			return nullptr;
		}

		// ---- 저장 --------------------------------------------------------------------------------------------------------
		TArray<FString> Saved, Failed;
		if (Request.bSave)
		{
			UEditorAssetSubsystem* Assets = GEditor ? GEditor->GetEditorSubsystem<UEditorAssetSubsystem>() : nullptr;
			TArray<UObject*> ToSave;
			for (UFontFace* F : Faces) { ToSave.Add(F); }
			ToSave.Add(Font);
			for (UObject* A : ToSave)
			{
				if (Assets && Assets->SaveLoadedAsset(A, /*bOnlyIfIsDirty*/ false))
				{
					Saved.Add(A->GetOutermost()->GetName());
				}
				else
				{
					Failed.Add(A->GetOutermost()->GetName());
				}
			}
			if (Failed.Num())
			{
				TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
				D->SetArrayField(TEXT("failed"), WidgetMcp::StringArray(Failed));
				D->SetArrayField(TEXT("saved"), WidgetMcp::StringArray(Saved));
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::SaveFailed, FString::Printf(TEXT("%d font package(s) could not be saved (see log)"), Failed.Num()), nullptr, D);
				return nullptr;
			}
		}

		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetStringField(TEXT("dest_path"), Dest);
		Out->SetStringField(TEXT("family_asset"), Font->GetPathName());
		Out->SetArrayField(TEXT("typefaces"), WidgetMcp::StringArray(Typefaces));
		Out->SetStringField(TEXT("font_cache_type"), TEXT("Runtime"));
		Out->SetArrayField(TEXT("faces"), FaceJson);
		Out->SetBoolField(TEXT("saved"), Request.bSave);
		Out->SetArrayField(TEXT("saved_packages"), WidgetMcp::StringArray(Saved));
		Out->SetArrayField(TEXT("newly_dirty"), WidgetMcp::StringArray(Request.bSave ? TArray<FString>() : NewlyDirty));
		UE_LOG(LogAnimGraphMcp, Log, TEXT("import_font_family: %s — %d face(s), saved %d"), *Font->GetPathName(), Faces.Num(), Saved.Num());
		return Out;
	}
}
