#include "Core/WidgetMcpButtonStyle.h"

#include "AssetRegistry/AssetRegistryModule.h"
#include "CommonButtonBase.h"
#include "Engine/Blueprint.h"
#include "Engine/BlueprintGeneratedClass.h"
#include "Engine/Texture2D.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/PackageName.h"
#include "UObject/Package.h"
#include "WidgetBlueprint.h"

namespace WidgetMcpButtonStyle
{
	namespace ButtonStylePrivate
	{
		struct FBrushSlot { const TCHAR* Name; FSlateBrush UCommonButtonStyle::* Member; };

		const TArray<FBrushSlot>& Slots()
		{
			static const TArray<FBrushSlot> Table = {
				{ TEXT("normal_base"), &UCommonButtonStyle::NormalBase }, { TEXT("normal_hovered"), &UCommonButtonStyle::NormalHovered },
				{ TEXT("normal_pressed"), &UCommonButtonStyle::NormalPressed }, { TEXT("selected_base"), &UCommonButtonStyle::SelectedBase },
				{ TEXT("selected_hovered"), &UCommonButtonStyle::SelectedHovered }, { TEXT("selected_pressed"), &UCommonButtonStyle::SelectedPressed },
				{ TEXT("disabled"), &UCommonButtonStyle::Disabled } };
			return Table;
		}

		/** 부모(프로젝트 클래스)가 UCommonButtonStyle 에 더한 값 속성 */
		TArray<FProperty*> ExtraProperties(const UClass* Class)
		{
			TArray<FProperty*> Out;
			for (TFieldIterator<FProperty> It(Class); It; ++It)
			{
				const UClass* Owner = It->GetOwnerClass();
				const FStructProperty* Struct = CastField<FStructProperty>(*It);
				const bool bKind = (Struct && Struct->Struct == TBaseStructure<FVector2D>::Get()) || CastField<FNumericProperty>(*It) || CastField<FBoolProperty>(*It);
				if (bKind && It->HasAnyPropertyFlags(CPF_Edit) && Owner && Owner->IsChildOf(UCommonButtonStyle::StaticClass()) && Owner != UCommonButtonStyle::StaticClass())
				{
					Out.Add(*It);
				}
			}
			return Out;
		}

		TSharedPtr<FJsonValue> ReadProperty(const FProperty* Prop, const UObject* Object)
		{
			const void* Value = Prop->ContainerPtrToValuePtr<void>(Object);
			if (CastField<FStructProperty>(Prop)) { return WidgetMcp::Vec2(*static_cast<const FVector2D*>(Value)); }
			if (const FBoolProperty* Bool = CastField<FBoolProperty>(Prop)) { return MakeShared<FJsonValueBoolean>(Bool->GetPropertyValue(Value)); }
			const FNumericProperty* Number = CastFieldChecked<FNumericProperty>(Prop);
			return WidgetMcp::Num(Number->IsFloatingPoint() ? Number->GetFloatingPointPropertyValue(Value) : static_cast<double>(Number->GetSignedIntPropertyValue(Value)));
		}

		bool WriteProperty(const FProperty* Prop, UObject* Object, const TSharedPtr<FJsonValue>& V)
		{
			void* Value = Prop->ContainerPtrToValuePtr<void>(Object);
			if (CastField<FStructProperty>(Prop))
			{
				const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
				double X = 0.0, Y = 0.0;
				if (!V->TryGetArray(A) || A->Num() != 2 || !(*A)[0]->TryGetNumber(X) || !(*A)[1]->TryGetNumber(Y)) { return false; }
				*static_cast<FVector2D*>(Value) = FVector2D(X, Y);
				return true;
			}
			if (const FBoolProperty* Bool = CastField<FBoolProperty>(Prop))
			{
				bool B = false;
				if (!V->TryGetBool(B)) { return false; }
				Bool->SetPropertyValue(Value, B);
				return true;
			}
			const FNumericProperty* Number = CastFieldChecked<FNumericProperty>(Prop);
			double N = 0.0;
			if (!V->TryGetNumber(N)) { return false; }
			if (Number->IsFloatingPoint()) { Number->SetFloatingPointPropertyValue(Value, N); }
			else { Number->SetIntPropertyValue(Value, static_cast<int64>(FMath::RoundToInt64(N))); }
			return true;
		}

		FClassProperty* StyleProperty()
		{
			static FClassProperty* Prop = FindFProperty<FClassProperty>(UCommonButtonBase::StaticClass(), TEXT("Style"));
			return Prop;
		}
	}

	using namespace ButtonStylePrivate;

	const TArray<FString>& BrushNames()
	{
		static TArray<FString> Names;
		if (Names.Num() == 0)
		{
			for (const FBrushSlot& S : Slots()) { Names.Add(S.Name); }
		}
		return Names;
	}

	TSharedRef<FJsonObject> Describe(const UCommonButtonStyle* Style, const WidgetMcpSpec::FAssets* Assets, TArray<TSharedPtr<FJsonValue>>& OutUnsupported)
	{
		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetStringField(TEXT("class"), Style->GetClass()->GetOutermost()->GetName());
		Out->SetStringField(TEXT("parent_class"), GetPathNameSafe(Style->GetClass()->GetSuperClass()));
		TSharedRef<FJsonObject> Brushes = MakeShared<FJsonObject>();
		for (const FBrushSlot& S : Slots())
		{
			Brushes->SetObjectField(S.Name, WidgetMcpSpec::BrushTo(Style->*(S.Member), Assets, FString(TEXT("button_style.")) + S.Name, OutUnsupported));
		}
		Out->SetObjectField(TEXT("brushes"), Brushes);
		Out->SetArrayField(TEXT("min_size"), { MakeShared<FJsonValueNumber>(Style->MinWidth), MakeShared<FJsonValueNumber>(Style->MinHeight) });
		TSharedRef<FJsonObject> Props = MakeShared<FJsonObject>();
		for (const FProperty* P : ExtraProperties(Style->GetClass())) { Props->SetField(P->GetName(), ReadProperty(P, Style)); }
		Out->SetObjectField(TEXT("props"), Props);
		return Out;
	}

	void CollectTextures(const UCommonButtonStyle* Style, TArray<UTexture2D*>& Out)
	{
		for (const FBrushSlot& S : Slots())
		{
			if (UTexture2D* T = Cast<UTexture2D>((Style->*(S.Member)).GetResourceObject())) { Out.AddUnique(T); }
		}
	}

	TSharedPtr<FJsonObject> Create(const WidgetMcp::FSettings& Settings, const FRequest& Request, const WidgetMcpSpec::FAssets& Assets, FEditorMcpContext& Context, FEditorMcpError& OutError)
	{
		const FString Package = WidgetMcp::ToPackagePath(Request.AssetPath);
		if (!WidgetMcp::CheckOutputAsset(Settings, Package, TEXT("asset_path"), OutError))
		{
			return nullptr;
		}
		UClass* Parent = UCommonButtonStyle::StaticClass();
		if (!Request.ParentClass.IsEmpty())
		{
			Parent = LoadObject<UClass>(nullptr, *Request.ParentClass, nullptr, LOAD_NoWarn);
		}
		if (!Parent || !Parent->IsChildOf(UCommonButtonStyle::StaticClass()) || Parent->HasAnyClassFlags(CLASS_Deprecated | CLASS_NewerVersionExists))
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::TypeNotAllowed, FString::Printf(TEXT("parent_class '%s' must be UCommonButtonStyle or a subclass of it"), *Request.ParentClass));
			return nullptr;
		}
		// ---- 검사 먼저 — 하나라도 틀리면 아무것도 안 만든다
		TArray<FString> Errors;
		TMap<FString, FSlateBrush> Brushes;
		for (const FBrushSlot& S : Slots())
		{
			const TSharedPtr<FJsonObject>* B = nullptr;
			FString Problem;
			if (!Request.Brushes.IsValid() || !Request.Brushes->TryGetObjectField(S.Name, B))
			{
				Errors.Add(FString::Printf(TEXT("BRUSH_MISSING: brushes.%s is required (all seven states are drawn)"), S.Name));
				continue;
			}
			if (!WidgetMcpSpec::ValidateBrushJson(**B, Assets, FString(TEXT("brushes.")) + S.Name, Problem))
			{
				Errors.Add(TEXT("BRUSH: ") + Problem);
				continue;
			}
			const TSharedRef<FJsonObject> Norm = WidgetMcpSpec::NormalizeBrushJson(B->ToSharedRef(), Assets);
			FSlateBrush Brush;
			if (!WidgetMcpSpec::BrushFrom(*Norm, Assets, Brush, Problem))
			{
				Errors.Add(TEXT("BRUSH: ") + Problem);
				continue;
			}
			if (Brush.DrawAs == ESlateBrushDrawType::NoDrawType)
			{
				Errors.Add(FString::Printf(TEXT("BRUSH_EMPTY: brushes.%s draws nothing — an empty Disabled brush makes Slate dim the normal one instead"), S.Name));
				continue;
			}
			Brushes.Add(S.Name, Brush);
		}
		if (Request.MinSize.X <= 0 || Request.MinSize.Y <= 0)
		{
			Errors.Add(TEXT("MIN_SIZE: min_size [w, h] must be positive (the button's own size)"));
		}
		if (Request.Props.IsValid())
		{
			const TArray<FProperty*> Extra = ExtraProperties(Parent);
			for (const TPair<FString, TSharedPtr<FJsonValue>>& P : Request.Props->Values)
			{
				if (!Extra.ContainsByPredicate([&P](const FProperty* X) { return X->GetName() == P.Key; }))
				{
					Errors.Add(FString::Printf(TEXT("PROP: '%s' is not an editable number / bool / Vector2D property that %s adds to UCommonButtonStyle"), *P.Key, *Parent->GetName()));
				}
			}
		}
		if (Errors.Num())
		{
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetArrayField(TEXT("errors"), WidgetMcp::StringArray(Errors));
			FString Code;
			Errors[0].Split(TEXT(":"), &Code, nullptr);
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("button style failed validation (%d error(s)) — nothing was created: %s"), Errors.Num(), *Errors[0]), *Code, D);
			return nullptr;
		}
		// ---- 만들기 / 다시 쓰기
		const FString Name = FPackageName::GetShortName(Package);
		UBlueprint* Blueprint = FindObject<UBlueprint>(nullptr, *(Package + TEXT(".") + Name));
		const bool bExisted = Blueprint != nullptr;
		if (bExisted ? (!Request.bReplace || Blueprint->ParentClass != Parent) : WidgetMcp::PackageExists(Package))
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::AssetExists, FString::Printf(TEXT("'%s' already exists — pass replace only for a style this run made with the same parent class"), *Package), TEXT("OVERWRITE_NOT_ALLOWED"));
			return nullptr;
		}
		const WidgetMcp::FWriteGuard Guard;
		if (!Blueprint)
		{
			UPackage* Pkg = CreatePackage(*Package);
			Blueprint = FKismetEditorUtilities::CreateBlueprint(Parent, Pkg, FName(*Name), BPTYPE_Normal, UBlueprint::StaticClass(), UBlueprintGeneratedClass::StaticClass(), FName(TEXT("WidgetMcp")));
			if (Blueprint) { FAssetRegistryModule::AssetCreated(Blueprint); }
		}
		UCommonButtonStyle* Defaults = Blueprint && Blueprint->GeneratedClass ? Cast<UCommonButtonStyle>(Blueprint->GeneratedClass->GetDefaultObject()) : nullptr;
		if (!Defaults)
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::Internal, FString::Printf(TEXT("CreateBlueprint made no button style class for '%s'"), *Package));
			return nullptr;
		}
		Defaults->bSingleMaterial = false;
		for (const FBrushSlot& S : Slots()) { Defaults->*(S.Member) = Brushes[S.Name]; }
		Defaults->MinWidth = Request.MinSize.X;
		Defaults->MinHeight = Request.MinSize.Y;
		Defaults->ButtonPadding = FMargin(0.f);
		if (Request.Props.IsValid())
		{
			for (const FProperty* P : ExtraProperties(Defaults->GetClass()))
			{
				const TSharedPtr<FJsonValue>* V = Request.Props->Values.Find(P->GetName());
				if (V && !WriteProperty(P, Defaults, *V))
				{
					OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("props.%s has the wrong kind of value for %s"), *P->GetName(), *P->GetCPPType()), TEXT("PROP"));
					return nullptr;
				}
			}
		}
		FBlueprintEditorUtils::MarkBlueprintAsModified(Blueprint);
		FKismetEditorUtilities::CompileBlueprint(Blueprint, EBlueprintCompileOptions::SkipGarbageCollection);
		Blueprint->MarkPackageDirty();
		// ---- 다시 읽어 확인 — 컴파일이 기본 객체를 새로 만들어도 값이 남아야 한다
		const UCommonButtonStyle* Live = Cast<UCommonButtonStyle>(Blueprint->GeneratedClass->GetDefaultObject());
		TArray<FString> Lost;
		for (const FBrushSlot& S : Slots())
		{
			if (!Live || !(Live->*(S.Member) == Brushes[S.Name])) { Lost.Add(S.Name); }
		}
		TArray<FString> NewlyDirty;
		if (!Guard.Finish(Settings, OutError, NewlyDirty))
		{
			return nullptr;
		}
		if (Lost.Num() || !(Blueprint->Status == BS_UpToDate || Blueprint->Status == BS_UpToDateWithWarnings))
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::ValidationFailed, FString::Printf(TEXT("the style class lost %d brush(es) on compile (%s), status %d"), Lost.Num(), *FString::Join(Lost, TEXT(", ")), static_cast<int32>(Blueprint->Status)), TEXT("STYLE_MISMATCH"));
			return nullptr;
		}
		TArray<TSharedPtr<FJsonValue>> Unsupported;
		TSharedRef<FJsonObject> Out = Describe(Live, &Assets, Unsupported);
		Out->SetStringField(TEXT("asset_path"), Blueprint->GetPathName());
		Out->SetStringField(TEXT("class_path"), Blueprint->GeneratedClass->GetPathName());
		Out->SetBoolField(TEXT("replaced"), bExisted);
		Out->SetArrayField(TEXT("unsupported"), Unsupported);
		Out->SetArrayField(TEXT("newly_dirty"), WidgetMcp::StringArray(NewlyDirty));
		Out->SetBoolField(TEXT("saved"), false);
		return Out;
	}

	bool IsButtonBlueprint(const UWidgetBlueprint* WBP)
	{
		return WBP && WBP->ParentClass && WBP->ParentClass->IsChildOf(UCommonButtonBase::StaticClass());
	}

	const UCommonButtonStyle* StyleOf(const UWidgetBlueprint* WBP)
	{
		const FClassProperty* Prop = StyleProperty();
		if (!IsButtonBlueprint(WBP) || !WBP->GeneratedClass || !Prop)
		{
			return nullptr;
		}
		const UClass* Class = Cast<UClass>(Prop->GetObjectPropertyValue_InContainer(WBP->GeneratedClass->GetDefaultObject()));
		return Class ? Cast<UCommonButtonStyle>(Class->GetDefaultObject()) : nullptr;
	}

	TSharedRef<FJsonObject> ExportDefaults(const UWidgetBlueprint* WBP)
	{
		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		if (const UCommonButtonStyle* Style = StyleOf(WBP))
		{
			Out->SetStringField(TEXT("Style"), Style->GetClass()->GetOutermost()->GetName());
		}
		return Out;
	}

	bool ResolveDefaults(const WidgetMcp::FSettings& Settings, const UWidgetBlueprint* WBP, const TSharedPtr<FJsonObject>& Defaults, UClass*& OutStyle, FString& OutError)
	{
		OutStyle = nullptr;
		if (!Defaults.IsValid() || Defaults->Values.Num() == 0)
		{
			return true;
		}
		for (const TPair<FString, TSharedPtr<FJsonValue>>& P : Defaults->Values)
		{
			if (P.Key != TEXT("Style") || !IsButtonBlueprint(WBP))
			{
				OutError = FString::Printf(TEXT("defaults.%s cannot be set — only 'Style' of a Widget Blueprint whose parent is a UCommonButtonBase"), *P.Key);
				return false;
			}
		}
		FString Path;
		if (!Defaults->TryGetStringField(TEXT("Style"), Path))
		{
			OutError = TEXT("defaults.Style must be the path of a button style asset");
			return false;
		}
		const FString Package = WidgetMcp::ToPackagePath(Path);
		const FString Folder = FPackageName::GetLongPackagePath(WBP->GetOutermost()->GetName()) + TEXT("/");
		const bool bAllowed = Package.StartsWith(Folder, ESearchCase::IgnoreCase)
			|| Settings.PromotionPaths.ContainsByPredicate([&Package](const FString& Prefix) { return Package.StartsWith(Prefix, ESearchCase::IgnoreCase); });
		const UBlueprint* Blueprint = bAllowed ? LoadObject<UBlueprint>(nullptr, *(Package + TEXT(".") + FPackageName::GetShortName(Package)), nullptr, LOAD_NoWarn) : nullptr;
		if (!Blueprint || !Blueprint->GeneratedClass || !Blueprint->GeneratedClass->IsChildOf(UCommonButtonStyle::StaticClass()))
		{
			OutError = FString::Printf(TEXT("defaults.Style '%s' is not a button style in the blueprint's own folder or below WidgetPromotionPaths"), *Path);
			return false;
		}
		OutStyle = Blueprint->GeneratedClass;
		return true;
	}

	bool ApplyStyle(UWidgetBlueprint* WBP, UClass* StyleClass)
	{
		FClassProperty* Prop = StyleProperty();
		if (!IsButtonBlueprint(WBP) || !WBP->GeneratedClass || !Prop || !StyleClass)
		{
			return false;
		}
		UObject* Defaults = WBP->GeneratedClass->GetDefaultObject();
		if (Prop->GetObjectPropertyValue_InContainer(Defaults) != StyleClass)
		{
			Prop->SetObjectPropertyValue_InContainer(Defaults, StyleClass);
			// 새 인스턴스는 '기본 객체에서 옮길 속성' 목록(컴파일 · 로드 때 만든다)에 든 것만 물려받는다 — 다시 만들지 않으면 다음 컴파일까지 엔진 기본 스타일로 그려진다 [실측 11-25]
			CastChecked<UBlueprintGeneratedClass>(WBP->GeneratedClass)->UpdateCustomPropertyListForPostConstruction();
			WBP->MarkPackageDirty();
		}
		return Prop->GetObjectPropertyValue_InContainer(Defaults) == StyleClass;
	}
}
