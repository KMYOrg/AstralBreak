#include "Core/WidgetMcpCommon.h"

#include "Misc/ConfigCacheIni.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
#include "UObject/Package.h"

namespace WidgetMcp
{
	namespace CommonPrivate
	{
		void ReadKeys(TFunctionRef<void(const TCHAR*, TArray<FString>&)> GetArray, FSettings& Out)
		{
			TArray<FString> Raw;
			GetArray(TEXT("WidgetOutputPaths"), Raw);
			for (const FString& R : Raw)
			{
				const FString P = EditorMcpGuard::NormalizePrefix(R);
				if (!EditorMcpGuard::IsValidPrefix(P))
				{
					Out.Warnings.Add(FString::Printf(TEXT("[WidgetMcp] WidgetOutputPaths '%s' ignored — needs a folder below a mount root (e.g. /Game/_AutoGen/)"), *R));
					continue;
				}
				Out.OutputPaths.AddUnique(P);
			}
			const TPair<const TCHAR*, TArray<FString>*> Dirs[] = { { TEXT("WidgetImportSourceRoots"), &Out.ImportRoots }, { TEXT("WidgetRenderOutputRoots"), &Out.RenderRoots } };
			for (const TPair<const TCHAR*, TArray<FString>*>& D : Dirs)
			{
				Raw.Reset();
				GetArray(D.Key, Raw);
				for (const FString& R : Raw)
				{
					const FString Dir = EditorMcpGuard::NormalizeDirectory(R);
					if (!Dir.IsEmpty())
					{
						D.Value->AddUnique(Dir);
					}
				}
			}
		}

		FString FormatNumber(double V)
		{
			const double R = Round3(V);
			if (FMath::IsNearlyEqual(R, FMath::RoundToDouble(R), 1e-9) && FMath::Abs(R) < 1e15)
			{
				return FString::Printf(TEXT("%lld"), static_cast<long long>(FMath::RoundToDouble(R)));
			}
			FString S = FString::Printf(TEXT("%.3f"), R);
			while (S.EndsWith(TEXT("0"))) { S.LeftChopInline(1); }
			return S;
		}

		FString QuoteString(const FString& S)
		{
			FString Out = TEXT("\"");
			for (const TCHAR C : S)
			{
				switch (C)
				{
				case TEXT('"'): Out += TEXT("\\\""); break;
				case TEXT('\\'): Out += TEXT("\\\\"); break;
				case TEXT('\n'): Out += TEXT("\\n"); break;
				case TEXT('\r'): Out += TEXT("\\r"); break;
				case TEXT('\t'): Out += TEXT("\\t"); break;
				default: Out.AppendChar(C); break;
				}
			}
			return Out + TEXT("\"");
		}
	}

	FSettings LoadSettings()
	{
		FSettings Out;
		CommonPrivate::ReadKeys([](const TCHAR* Key, TArray<FString>& Values) { GConfig->GetArray(Section, Key, Values, GEngineIni); }, Out);
		return Out;
	}

	FSettings LoadSettingsFromFile(const FConfigFile& File)
	{
		FSettings Out;
		CommonPrivate::ReadKeys([&File](const TCHAR* Key, TArray<FString>& Values) { File.GetArray(Section, Key, Values); }, Out);
		return Out;
	}

	TSharedRef<FJsonObject> SettingsToJson(const FSettings& Settings)
	{
		TSharedRef<FJsonObject> Obj = MakeShared<FJsonObject>();
		Obj->SetArrayField(TEXT("output_paths"), StringArray(Settings.OutputPaths));
		Obj->SetArrayField(TEXT("import_source_roots"), StringArray(Settings.ImportRoots));
		Obj->SetArrayField(TEXT("render_output_roots"), StringArray(Settings.RenderRoots));
		Obj->SetArrayField(TEXT("warnings"), StringArray(Settings.Warnings));
		return Obj;
	}

	FEditorMcpError MakeMcpError(const TCHAR* Code, const FString& Message, const TCHAR* Reason, TSharedPtr<FJsonObject> Details)
	{
		TSharedRef<FJsonObject> D = Details.IsValid() ? Details.ToSharedRef() : MakeShared<FJsonObject>();
		if (Reason)
		{
			D->SetStringField(TEXT("reason"), Reason);
		}
		return FEditorMcpError::Make(Code, Message, D);
	}

	double Round3(double V)
	{
		const double R = FMath::RoundToDouble(V * 1000.0) / 1000.0;
		return R == 0.0 ? 0.0 : R; // -0 → 0
	}

	TSharedPtr<FJsonValue> Num(double V)
	{
		return MakeShared<FJsonValueNumber>(Round3(V));
	}

	TSharedPtr<FJsonValue> Vec2(const FVector2D& V)
	{
		return MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{ Num(V.X), Num(V.Y) });
	}

	TSharedPtr<FJsonValue> Margin4(const FMargin& M)
	{
		return MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{ Num(M.Left), Num(M.Top), Num(M.Right), Num(M.Bottom) });
	}

	bool ReadNumber(const FJsonObject& Obj, const TCHAR* Key, double& Out)
	{
		return Obj.TryGetNumberField(Key, Out);
	}

	bool ReadVec2(const FJsonObject& Obj, const TCHAR* Key, FVector2D& Out)
	{
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (!Obj.TryGetArrayField(Key, Arr) || Arr->Num() != 2)
		{
			return false;
		}
		Out = FVector2D((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber());
		return true;
	}

	bool ReadMargin(const FJsonObject& Obj, const TCHAR* Key, FMargin& Out)
	{
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (!Obj.TryGetArrayField(Key, Arr) || Arr->Num() != 4)
		{
			return false;
		}
		Out = FMargin((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber(), (*Arr)[2]->AsNumber(), (*Arr)[3]->AsNumber());
		return true;
	}

	bool ReadVec4(const FJsonObject& Obj, const TCHAR* Key, FVector4& Out)
	{
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (!Obj.TryGetArrayField(Key, Arr) || Arr->Num() != 4)
		{
			return false;
		}
		Out = FVector4((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber(), (*Arr)[2]->AsNumber(), (*Arr)[3]->AsNumber());
		return true;
	}

	bool ParseHexColor(const FString& Hex, FLinearColor& Out)
	{
		FString H = Hex.TrimStartAndEnd();
		H.RemoveFromStart(TEXT("#"));
		if (H.Len() != 6 && H.Len() != 8)
		{
			return false;
		}
		for (const TCHAR C : H)
		{
			if (!FChar::IsHexDigit(C))
			{
				return false;
			}
		}
		if (H.Len() == 6)
		{
			H += TEXT("FF");
		}
		Out = FLinearColor::FromSRGBColor(FColor::FromHex(H));
		return true;
	}

	FString ToHexColor(const FLinearColor& Color)
	{
		const FColor C = Color.ToFColorSRGB();
		return FString::Printf(TEXT("#%02X%02X%02X%02X"), C.R, C.G, C.B, C.A);
	}

	FString CanonicalJson(const TSharedPtr<FJsonValue>& Value)
	{
		if (!Value.IsValid() || Value->IsNull())
		{
			return TEXT("null");
		}
		switch (Value->Type)
		{
		case EJson::Boolean: return Value->AsBool() ? TEXT("true") : TEXT("false");
		case EJson::Number: return CommonPrivate::FormatNumber(Value->AsNumber());
		case EJson::String: return CommonPrivate::QuoteString(Value->AsString());
		case EJson::Array:
		{
			FString Out = TEXT("[");
			const TArray<TSharedPtr<FJsonValue>>& Arr = Value->AsArray();
			for (int32 i = 0; i < Arr.Num(); ++i)
			{
				Out += (i ? TEXT(",") : TEXT("")) + CanonicalJson(Arr[i]);
			}
			return Out + TEXT("]");
		}
		case EJson::Object:
			return CanonicalJson(Value->AsObject().ToSharedRef());
		default:
			return TEXT("null");
		}
	}

	FString CanonicalJson(const TSharedRef<FJsonObject>& Object)
	{
		TArray<FString> Keys;
		Object->Values.GetKeys(Keys);
		Keys.Sort();
		FString Out = TEXT("{");
		for (int32 i = 0; i < Keys.Num(); ++i)
		{
			Out += (i ? TEXT(",") : TEXT("")) + CommonPrivate::QuoteString(Keys[i]) + TEXT(":") + CanonicalJson(Object->Values[Keys[i]]);
		}
		return Out + TEXT("}");
	}

	FString Sha1Revision(const FString& Text)
	{
		const FTCHARToUTF8 Utf8(*Text);
		uint8 Digest[FSHA1::DigestSize];
		FSHA1::HashBuffer(Utf8.Get(), Utf8.Length(), Digest);
		return TEXT("sha1:") + BytesToHex(Digest, FSHA1::DigestSize).ToLower();
	}

	void DiffJson(const TSharedPtr<FJsonValue>& A, const TSharedPtr<FJsonValue>& B, const FString& Path, TArray<FString>& Out, int32 Limit)
	{
		if (Out.Num() >= Limit)
		{
			return;
		}
		const bool bAObj = A.IsValid() && A->Type == EJson::Object;
		const bool bBObj = B.IsValid() && B->Type == EJson::Object;
		if (bAObj && bBObj)
		{
			TSet<FString> Keys;
			for (const TPair<FString, TSharedPtr<FJsonValue>>& P : A->AsObject()->Values) { Keys.Add(P.Key); }
			for (const TPair<FString, TSharedPtr<FJsonValue>>& P : B->AsObject()->Values) { Keys.Add(P.Key); }
			TArray<FString> Sorted = Keys.Array();
			Sorted.Sort();
			for (const FString& K : Sorted)
			{
				const TSharedPtr<FJsonValue>* VA = A->AsObject()->Values.Find(K);
				const TSharedPtr<FJsonValue>* VB = B->AsObject()->Values.Find(K);
				DiffJson(VA ? *VA : nullptr, VB ? *VB : nullptr, Path + TEXT(".") + K, Out, Limit);
			}
			return;
		}
		const bool bAArr = A.IsValid() && A->Type == EJson::Array;
		const bool bBArr = B.IsValid() && B->Type == EJson::Array;
		if (bAArr && bBArr && A->AsArray().Num() == B->AsArray().Num())
		{
			for (int32 i = 0; i < A->AsArray().Num(); ++i)
			{
				const TSharedPtr<FJsonValue>& EA = A->AsArray()[i];
				FString Key = FString::FromInt(i);
				FString Id;
				if (EA->Type == EJson::Object && EA->AsObject()->TryGetStringField(TEXT("id"), Id))
				{
					Key = Id;
				}
				DiffJson(EA, B->AsArray()[i], FString::Printf(TEXT("%s[%s]"), *Path, *Key), Out, Limit);
			}
			return;
		}
		const FString CA = A.IsValid() ? CanonicalJson(A) : TEXT("<missing>");
		const FString CB = B.IsValid() ? CanonicalJson(B) : TEXT("<missing>");
		if (CA != CB)
		{
			Out.Add(FString::Printf(TEXT("%s: %s != %s"), *Path, *CA.Left(200), *CB.Left(200)));
		}
	}

	TArray<TSharedPtr<FJsonValue>> StringArray(const TArray<FString>& Values)
	{
		return EditorMcpGuard::ToJsonArray(Values);
	}

	FString ToPackagePath(const FString& AssetPath)
	{
		FString P = AssetPath.TrimStartAndEnd();
		int32 Dot = INDEX_NONE;
		if (P.FindChar(TEXT('.'), Dot))
		{
			P.LeftInline(Dot);
		}
		return P;
	}

	bool PackageExists(const FString& PackagePath)
	{
		return FindPackage(nullptr, *PackagePath) != nullptr || FPackageName::DoesPackageExist(PackagePath);
	}

	bool CheckOutputAsset(const FSettings& Settings, const FString& AssetPath, const TCHAR* Field, FEditorMcpError& OutError)
	{
		const FString Package = ToPackagePath(AssetPath);
		TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
		D->SetStringField(TEXT("field"), Field);
		D->SetStringField(TEXT("path"), Package);
		D->SetArrayField(TEXT("allowed"), StringArray(Settings.OutputPaths));
		FText Reason;
		if (!FPackageName::IsValidLongPackageName(Package, /*bIncludeReadOnlyRoots*/ false, &Reason))
		{
			OutError = MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' is not a valid package path: %s"), *Package, *Reason.ToString()), TEXT("BAD_PATH"), D);
			return false;
		}
		if (Settings.OutputPaths.Num() == 0 || !EditorMcpGuard::IsUnderAnyPrefix(FPackageName::GetLongPackagePath(Package), Settings.OutputPaths))
		{
			OutError = MakeMcpError(EditorMcpErrorCodes::OutputPathNotAllowed,
				FString::Printf(TEXT("'%s' is outside [WidgetMcp] WidgetOutputPaths (%s)"), *Package, *FString::Join(Settings.OutputPaths, TEXT(", "))), nullptr, D);
			return false;
		}
		return true;
	}

	bool CheckRunFolder(const FSettings& Settings, const FString& Folder, const TCHAR* Field, FEditorMcpError& OutError)
	{
		const FString F = EditorMcpGuard::NormalizeFolderPath(Folder);
		TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
		D->SetStringField(TEXT("field"), Field);
		D->SetStringField(TEXT("path"), F);
		D->SetArrayField(TEXT("allowed"), StringArray(Settings.OutputPaths));
		if (!FPackageName::IsValidLongPackageName(F, false) || F.Contains(TEXT(".")))
		{
			OutError = MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' is not a valid folder path"), *F), TEXT("BAD_PATH"), D);
			return false;
		}
		const FString AsDir = F + TEXT("/");
		for (const FString& Prefix : Settings.OutputPaths)
		{
			if (AsDir.StartsWith(Prefix, ESearchCase::IgnoreCase) && AsDir.Len() > Prefix.Len())
			{
				return true;
			}
		}
		OutError = MakeMcpError(EditorMcpErrorCodes::OutputPathNotAllowed,
			FString::Printf(TEXT("'%s' must be a folder below [WidgetMcp] WidgetOutputPaths (%s) — the prefix itself is never a run folder"), *F, *FString::Join(Settings.OutputPaths, TEXT(", "))), nullptr, D);
		return false;
	}

	bool CheckDiskPath(const TArray<FString>& Roots, const FString& Path, const TCHAR* Field, const TCHAR* ConfigKey, FString& OutFull, FEditorMcpError& OutError)
	{
		FString Full = FPaths::ConvertRelativePathToFull(FPaths::IsRelative(Path) ? FPaths::Combine(FPaths::ProjectDir(), Path) : Path);
		FPaths::NormalizeFilename(Full);
		FPaths::CollapseRelativeDirectories(Full);
		TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
		D->SetStringField(TEXT("field"), Field);
		D->SetStringField(TEXT("path"), Full);
		D->SetArrayField(TEXT("allowed"), StringArray(Roots));
		const bool bInside = Roots.ContainsByPredicate([&Full](const FString& Root) { return Full.StartsWith(Root, ESearchCase::IgnoreCase) && Full.Len() > Root.Len(); });
		if (!bInside || Full.Contains(TEXT("..")))
		{
			OutError = MakeMcpError(EditorMcpErrorCodes::OutputPathNotAllowed,
				FString::Printf(TEXT("'%s' is outside [WidgetMcp] %s (%s)"), *Full, ConfigKey, *FString::Join(Roots, TEXT(", "))), TEXT("DISK_ROOT"), D);
			return false;
		}
		OutFull = Full;
		return true;
	}

	bool FWriteGuard::Finish(const FSettings& Settings, FEditorMcpError& OutError, TArray<FString>& OutNewlyDirty) const
	{
		TArray<FString> Unexpected;
		Snapshot.GetNewlyDirty(Settings.OutputPaths, OutNewlyDirty, Unexpected);
		if (Unexpected.Num() > 0)
		{
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetArrayField(TEXT("unexpected"), StringArray(Unexpected));
			D->SetArrayField(TEXT("allowed_dirty"), StringArray(OutNewlyDirty));
			OutError = MakeMcpError(EditorMcpErrorCodes::UnexpectedDirty,
				FString::Printf(TEXT("%d package(s) outside [WidgetMcp] WidgetOutputPaths became dirty — nothing was saved"), Unexpected.Num()), nullptr, D);
			return false;
		}
		return true;
	}
}
