#include "Core/WidgetMcpSpec.h"

#include "Components/Border.h"
#include "Components/BorderSlot.h"
#include "Components/Button.h"
#include "Components/ButtonSlot.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/Image.h"
#include "Components/Overlay.h"
#include "Components/OverlaySlot.h"
#include "Components/ProgressBar.h"
#include "Components/SizeBox.h"
#include "Components/SizeBoxSlot.h"
#include "Components/Spacer.h"
#include "Components/TextBlock.h"
#include "Components/UniformGridPanel.h"
#include "Components/UniformGridSlot.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Engine/Font.h"
#include "Engine/Texture2D.h"
#include "Misc/PackageName.h"
#include "Styling/SlateTypes.h"

namespace WidgetMcpSpec
{
	namespace SpecPrivate
	{
		struct FTypeEntry { const TCHAR* Name; UClass* (*Class)(); const TCHAR* ChildSlot; bool bSingle; bool bPanelVisibility; };

		const TArray<FTypeEntry>& Types()
		{
			static const TArray<FTypeEntry> Table = {
				{ TEXT("CanvasPanel"),      [] { return UCanvasPanel::StaticClass(); },      TEXT("canvas"),         false, true },
				{ TEXT("Overlay"),          [] { return UOverlay::StaticClass(); },          TEXT("overlay"),        false, true },
				{ TEXT("VerticalBox"),      [] { return UVerticalBox::StaticClass(); },      TEXT("vertical_box"),   false, true },
				{ TEXT("HorizontalBox"),    [] { return UHorizontalBox::StaticClass(); },    TEXT("horizontal_box"), false, true },
				{ TEXT("UniformGridPanel"), [] { return UUniformGridPanel::StaticClass(); }, TEXT("uniform_grid"),   false, true },
				{ TEXT("SizeBox"),          [] { return USizeBox::StaticClass(); },          TEXT("size_box"),       true,  true },
				{ TEXT("Border"),           [] { return UBorder::StaticClass(); },           TEXT("border"),         true,  false },
				{ TEXT("Button"),           [] { return UButton::StaticClass(); },           TEXT("button"),         true,  false },
				{ TEXT("Image"),            [] { return UImage::StaticClass(); },            TEXT(""),               false, false },
				{ TEXT("TextBlock"),        [] { return UTextBlock::StaticClass(); },        TEXT(""),               false, false },
				{ TEXT("ProgressBar"),      [] { return UProgressBar::StaticClass(); },      TEXT(""),               false, false },
				{ TEXT("Spacer"),           [] { return USpacer::StaticClass(); },           TEXT(""),               false, true },
			};
			return Table;
		}

		const FTypeEntry* FindType(const FString& Type)
		{
			return Types().FindByPredicate([&Type](const FTypeEntry& E) { return Type == E.Name; });
		}

		const TMap<FString, TSet<FString>>& StyleKeys()
		{
			static const TMap<FString, TSet<FString>> Keys = {
				{ TEXT("Border"), { TEXT("brush") } },
				{ TEXT("Image"), { TEXT("brush") } },
				{ TEXT("ProgressBar"), { TEXT("background"), TEXT("fill"), TEXT("fill_color"), TEXT("percent"), TEXT("bar_fill_type") } },
				{ TEXT("SizeBox"), { TEXT("width_override"), TEXT("height_override") } },
				{ TEXT("Spacer"), { TEXT("size") } },
				{ TEXT("UniformGridPanel"), { TEXT("slot_padding"), TEXT("min_slot_width"), TEXT("min_slot_height") } },
				{ TEXT("Button"), { TEXT("normal"), TEXT("hovered"), TEXT("pressed") } },
			};
			return Keys;
		}

		bool IsBrushKey(const FString& Key)
		{
			return Key == TEXT("brush") || Key == TEXT("background") || Key == TEXT("fill") || Key == TEXT("normal") || Key == TEXT("hovered") || Key == TEXT("pressed");
		}

		// ---- 열거 표 ---------------------------------------------------------------------------------------------
		template <typename T>
		struct FNamed { const TCHAR* Name; T Value; };

		const TArray<FNamed<EHorizontalAlignment>>& HAligns()
		{
			static const TArray<FNamed<EHorizontalAlignment>> T = { { TEXT("left"), HAlign_Left }, { TEXT("center"), HAlign_Center }, { TEXT("right"), HAlign_Right }, { TEXT("fill"), HAlign_Fill } };
			return T;
		}
		const TArray<FNamed<EVerticalAlignment>>& VAligns()
		{
			static const TArray<FNamed<EVerticalAlignment>> T = { { TEXT("top"), VAlign_Top }, { TEXT("center"), VAlign_Center }, { TEXT("bottom"), VAlign_Bottom }, { TEXT("fill"), VAlign_Fill } };
			return T;
		}
		const TArray<FNamed<ESlateVisibility>>& Visibilities()
		{
			static const TArray<FNamed<ESlateVisibility>> T = { { TEXT("visible"), ESlateVisibility::Visible }, { TEXT("collapsed"), ESlateVisibility::Collapsed },
				{ TEXT("hidden"), ESlateVisibility::Hidden }, { TEXT("hit_test_invisible"), ESlateVisibility::HitTestInvisible },
				{ TEXT("self_hit_test_invisible"), ESlateVisibility::SelfHitTestInvisible } };
			return T;
		}
		const TArray<FNamed<ESlateBrushDrawType::Type>>& DrawTypes()
		{
			static const TArray<FNamed<ESlateBrushDrawType::Type>> T = { { TEXT("image"), ESlateBrushDrawType::Image }, { TEXT("box"), ESlateBrushDrawType::Box },
				{ TEXT("border"), ESlateBrushDrawType::Border }, { TEXT("rounded_box"), ESlateBrushDrawType::RoundedBox }, { TEXT("none"), ESlateBrushDrawType::NoDrawType } };
			return T;
		}
		const TArray<FNamed<EProgressBarFillType::Type>>& FillTypes()
		{
			static const TArray<FNamed<EProgressBarFillType::Type>> T = { { TEXT("left_to_right"), EProgressBarFillType::LeftToRight },
				{ TEXT("right_to_left"), EProgressBarFillType::RightToLeft }, { TEXT("fill_from_center"), EProgressBarFillType::FillFromCenter },
				{ TEXT("top_to_bottom"), EProgressBarFillType::TopToBottom }, { TEXT("bottom_to_top"), EProgressBarFillType::BottomToTop } };
			return T;
		}
		const TArray<FNamed<ETextJustify::Type>>& Justifies()
		{
			static const TArray<FNamed<ETextJustify::Type>> T = { { TEXT("left"), ETextJustify::Left }, { TEXT("center"), ETextJustify::Center }, { TEXT("right"), ETextJustify::Right } };
			return T;
		}
		/** 굵기 → Roboto(엔진 기본) 타입페이스 이름 */
		const TArray<FNamed<const TCHAR*>>& Weights()
		{
			static const TArray<FNamed<const TCHAR*>> T = { { TEXT("regular"), TEXT("Regular") }, { TEXT("bold"), TEXT("Bold") }, { TEXT("light"), TEXT("Light") },
				{ TEXT("italic"), TEXT("Italic") }, { TEXT("bold_italic"), TEXT("Bold Italic") } };
			return T;
		}

		template <typename T>
		bool FromName(const TArray<FNamed<T>>& Table, const FString& Name, T& Out)
		{
			for (const FNamed<T>& E : Table) { if (Name == E.Name) { Out = E.Value; return true; } }
			return false;
		}
		template <typename T>
		FString ToName(const TArray<FNamed<T>>& Table, T Value)
		{
			for (const FNamed<T>& E : Table) { if (E.Value == Value) { return E.Name; } }
			return FString();
		}
		FString WeightFromTypeface(const FName& Typeface)
		{
			for (const FNamed<const TCHAR*>& E : Weights()) { if (Typeface == FName(E.Value)) { return E.Name; } }
			return FString();
		}

		// ---- JSON 도우미 ----------------------------------------------------------------------------------------
		TSharedPtr<FJsonValue> DeepCopy(const TSharedPtr<FJsonValue>& V)
		{
			if (!V.IsValid())
			{
				return V;
			}
			if (V->Type == EJson::Object)
			{
				TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
				for (const TPair<FString, TSharedPtr<FJsonValue>>& P : V->AsObject()->Values) { O->Values.Add(P.Key, DeepCopy(P.Value)); }
				return MakeShared<FJsonValueObject>(O);
			}
			if (V->Type == EJson::Array)
			{
				TArray<TSharedPtr<FJsonValue>> A;
				for (const TSharedPtr<FJsonValue>& E : V->AsArray()) { A.Add(DeepCopy(E)); }
				return MakeShared<FJsonValueArray>(A);
			}
			return V;
		}

		FString CanonColorString(const FString& S)
		{
			FString C = S.TrimStartAndEnd().ToUpper();
			if (C.Len() == 7)
			{
				C += TEXT("FF");
			}
			return C;
		}

		void CanonColors(const TSharedRef<FJsonObject>& O)
		{
			for (TPair<FString, TSharedPtr<FJsonValue>>& P : O->Values)
			{
				if (!P.Value.IsValid())
				{
					continue;
				}
				if (P.Value->Type == EJson::String && P.Key.EndsWith(TEXT("color")))
				{
					P.Value = MakeShared<FJsonValueString>(CanonColorString(P.Value->AsString()));
				}
				else if (P.Value->Type == EJson::Object)
				{
					CanonColors(P.Value->AsObject().ToSharedRef());
				}
			}
		}

		void SetDefault(const TSharedRef<FJsonObject>& O, const TCHAR* Key, const TSharedPtr<FJsonValue>& V)
		{
			if (!O->HasField(Key))
			{
				O->SetField(Key, V);
			}
		}
		TSharedPtr<FJsonValue> Arr(std::initializer_list<double> Values)
		{
			TArray<TSharedPtr<FJsonValue>> A;
			for (double D : Values) { A.Add(MakeShared<FJsonValueNumber>(D)); }
			return MakeShared<FJsonValueArray>(A);
		}
		TSharedPtr<FJsonValue> S(const TCHAR* V) { return MakeShared<FJsonValueString>(V); }
		TSharedPtr<FJsonValue> N(double V) { return MakeShared<FJsonValueNumber>(V); }
		TSharedPtr<FJsonValue> B(bool V) { return MakeShared<FJsonValueBoolean>(V); }

		TSharedPtr<FJsonObject> ObjField(const FJsonObject& O, const TCHAR* Key)
		{
			const TSharedPtr<FJsonObject>* P = nullptr;
			return O.TryGetObjectField(Key, P) ? *P : nullptr;
		}
		FString StrField(const FJsonObject& O, const TCHAR* Key, const FString& Default = FString())
		{
			FString V;
			return O.TryGetStringField(Key, V) ? V : Default;
		}
		double NumField(const FJsonObject& O, const TCHAR* Key, double Default)
		{
			double V = Default;
			O.TryGetNumberField(Key, V);
			return V;
		}
		FLinearColor ColorField(const FJsonObject& O, const TCHAR* Key, const FLinearColor& Default)
		{
			FLinearColor C = Default;
			FString Hex;
			if (O.TryGetStringField(Key, Hex))
			{
				WidgetMcp::ParseHexColor(Hex, C);
			}
			return C;
		}

		// ---- 브러시 --------------------------------------------------------------------------------------------
		UTexture2D* ResolveTexture(const FString& Asset, const FAssets& Assets)
		{
			if (UTexture2D* const* T = Assets.Textures.Find(Asset))
			{
				return *T;
			}
			if (Asset.StartsWith(TEXT("/")))
			{
				const FString Package = WidgetMcp::ToPackagePath(Asset);
				return LoadObject<UTexture2D>(nullptr, *(Package + TEXT(".") + FPackageName::GetShortName(Package)));
			}
			return nullptr;
		}

		bool ValidateBrush(const FJsonObject& Brush, const FAssets& Assets, const FString& Where, FString& OutError)
		{
			ESlateBrushDrawType::Type Draw;
			const FString DrawName = StrField(Brush, TEXT("draw_as"), TEXT("image"));
			if (!FromName(DrawTypes(), DrawName, Draw))
			{
				OutError = FString::Printf(TEXT("%s.draw_as '%s' is not image|box|border|rounded_box|none"), *Where, *DrawName);
				return false;
			}
			for (const TCHAR* Key : { TEXT("color"), TEXT("outline_color") })
			{
				FString Hex;
				FLinearColor C;
				if (Brush.TryGetStringField(Key, Hex) && !WidgetMcp::ParseHexColor(Hex, C))
				{
					OutError = FString::Printf(TEXT("%s.%s '%s' is not #RRGGBB(AA)"), *Where, Key, *Hex);
					return false;
				}
			}
			FString Asset;
			if (Brush.TryGetStringField(TEXT("asset"), Asset) && !ResolveTexture(Asset, Assets))
			{
				OutError = FString::Printf(TEXT("%s.asset '%s' is neither in assets{} nor a loadable Texture2D"), *Where, *Asset);
				return false;
			}
			return true;
		}

		bool BrushFromJson(const FJsonObject& J, const FAssets& Assets, FSlateBrush& Out, FString& OutError)
		{
			FSlateBrush Brush;
			ESlateBrushDrawType::Type Draw = ESlateBrushDrawType::Image;
			FromName(DrawTypes(), StrField(J, TEXT("draw_as"), TEXT("image")), Draw);
			Brush.DrawAs = Draw;
			FVector2D ImageSize(32.0, 32.0);
			FString Asset;
			if (J.TryGetStringField(TEXT("asset"), Asset) && !Asset.IsEmpty())
			{
				UTexture2D* Texture = ResolveTexture(Asset, Assets);
				if (!Texture)
				{
					OutError = FString::Printf(TEXT("brush asset '%s' did not resolve to a Texture2D"), *Asset);
					return false;
				}
				Brush.SetResourceObject(Texture);
				if (const FVector2D* Size = Assets.Sizes.Find(Asset))
				{
					ImageSize = *Size;
				}
				else
				{
					ImageSize = FVector2D(Texture->GetSizeX(), Texture->GetSizeY());
				}
			}
			WidgetMcp::ReadVec2(J, TEXT("image_size"), ImageSize);
			Brush.ImageSize = ImageSize;
			Brush.TintColor = FSlateColor(ColorField(J, TEXT("color"), FLinearColor::White));
			if (Draw == ESlateBrushDrawType::Box || Draw == ESlateBrushDrawType::Border)
			{
				FMargin M(0.f);
				WidgetMcp::ReadMargin(J, TEXT("margin"), M);
				Brush.Margin = M;
			}
			if (Draw == ESlateBrushDrawType::RoundedBox)
			{
				const double R = NumField(J, TEXT("radius"), 0.0);
				FSlateBrushOutlineSettings Outline(FVector4(R, R, R, R));
				Outline.Color = FSlateColor(ColorField(J, TEXT("outline_color"), FLinearColor::Transparent));
				Outline.Width = static_cast<float>(NumField(J, TEXT("outline_width"), 0.0));
				Brush.OutlineSettings = Outline;
			}
			Out = Brush;
			return true;
		}

		TSharedRef<FJsonObject> BrushToJson(const FSlateBrush& Brush, const FAssets* Assets, const FString& Where, TArray<TSharedPtr<FJsonValue>>& Unsupported)
		{
			auto Note = [&Unsupported, &Where](const FString& What)
			{
				TSharedRef<FJsonObject> U = MakeShared<FJsonObject>();
				U->SetStringField(TEXT("where"), Where);
				U->SetStringField(TEXT("reason"), What);
				Unsupported.Add(MakeShared<FJsonValueObject>(U));
			};
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			const FString Draw = ToName(DrawTypes(), Brush.DrawAs.GetValue());
			J->SetStringField(TEXT("draw_as"), Draw.IsEmpty() ? TEXT("image") : Draw);
			if (UObject* Resource = Brush.GetResourceObject())
			{
				if (const UTexture2D* Texture = Cast<UTexture2D>(Resource))
				{
					const FString Package = WidgetMcp::ToPackagePath(Texture->GetPathName());
					const FString* Id = Assets ? Assets->IdByPackage.Find(Package) : nullptr;
					J->SetStringField(TEXT("asset"), Id ? *Id : Package);
				}
				else
				{
					Note(FString::Printf(TEXT("brush resource is a %s (only Texture2D is in the spec vocabulary)"), *Resource->GetClass()->GetName()));
				}
			}
			if (Brush.TintColor.IsColorSpecified())
			{
				J->SetStringField(TEXT("color"), WidgetMcp::ToHexColor(Brush.TintColor.GetSpecifiedColor()));
			}
			else
			{
				Note(TEXT("brush tint uses a style color rule, not a specified color"));
				J->SetStringField(TEXT("color"), TEXT("#FFFFFFFF"));
			}
			if (Brush.DrawAs == ESlateBrushDrawType::Box || Brush.DrawAs == ESlateBrushDrawType::Border)
			{
				J->SetField(TEXT("margin"), WidgetMcp::Margin4(Brush.Margin));
			}
			if (Brush.DrawAs == ESlateBrushDrawType::RoundedBox)
			{
				const FVector4 R = Brush.OutlineSettings.CornerRadii;
				if (R.X != R.Y || R.X != R.Z || R.X != R.W)
				{
					Note(TEXT("rounded_box corner radii differ — the spec keeps one radius"));
				}
				J->SetField(TEXT("radius"), WidgetMcp::Num(R.X));
				J->SetStringField(TEXT("outline_color"), WidgetMcp::ToHexColor(Brush.OutlineSettings.Color.GetSpecifiedColor()));
				J->SetField(TEXT("outline_width"), WidgetMcp::Num(Brush.OutlineSettings.Width));
			}
			if (Brush.DrawAs != ESlateBrushDrawType::NoDrawType)
			{
				J->SetField(TEXT("image_size"), WidgetMcp::Vec2(Brush.ImageSize));
			}
			return J;
		}

		TSharedRef<FJsonObject> NormalizeBrush(const TSharedRef<FJsonObject>& Brush, const FAssets& Assets)
		{
			SetDefault(Brush, TEXT("draw_as"), S(TEXT("image")));
			SetDefault(Brush, TEXT("color"), S(TEXT("#FFFFFFFF")));
			const FString Draw = Brush->GetStringField(TEXT("draw_as"));
			if (Draw == TEXT("box") || Draw == TEXT("border"))
			{
				SetDefault(Brush, TEXT("margin"), Arr({ 0, 0, 0, 0 }));
			}
			if (Draw == TEXT("rounded_box"))
			{
				SetDefault(Brush, TEXT("radius"), N(0));
				SetDefault(Brush, TEXT("outline_color"), S(TEXT("#00000000")));
				SetDefault(Brush, TEXT("outline_width"), N(0));
			}
			if (Draw != TEXT("none"))
			{
				FString Asset;
				FVector2D Size(32.0, 32.0);
				if (Brush->TryGetStringField(TEXT("asset"), Asset))
				{
					if (const FVector2D* Known = Assets.Sizes.Find(Asset))
					{
						Size = *Known;
					}
					else if (const UTexture2D* Texture = ResolveTexture(Asset, Assets))
					{
						Size = FVector2D(Texture->GetSizeX(), Texture->GetSizeY());   // UE 경로로 적은 에셋 — 적용(BrushFromJson)과 같은 기본값
					}
				}
				SetDefault(Brush, TEXT("image_size"), Arr({ Size.X, Size.Y }));
			}
			return Brush;
		}

		// ---- 슬롯 ---------------------------------------------------------------------------------------------
		struct FAlignPadding
		{
			FMargin Padding;
			EHorizontalAlignment H = HAlign_Fill;
			EVerticalAlignment V = VAlign_Fill;
		};

		FAlignPadding ReadAlignPadding(const FJsonObject& J)
		{
			FAlignPadding Out;
			WidgetMcp::ReadMargin(J, TEXT("padding"), Out.Padding);
			FromName(HAligns(), StrField(J, TEXT("h_align"), TEXT("fill")), Out.H);
			FromName(VAligns(), StrField(J, TEXT("v_align"), TEXT("fill")), Out.V);
			return Out;
		}

		void WriteAlignPadding(const TSharedRef<FJsonObject>& J, const FMargin& Padding, EHorizontalAlignment H, EVerticalAlignment V)
		{
			J->SetField(TEXT("padding"), WidgetMcp::Margin4(Padding));
			J->SetStringField(TEXT("h_align"), ToName(HAligns(), H));
			J->SetStringField(TEXT("v_align"), ToName(VAligns(), V));
		}

		const TMap<FString, TSharedRef<FJsonObject>>& SlotDefaults()
		{
			static TMap<FString, TSharedRef<FJsonObject>> Table;
			if (Table.Num() == 0)
			{
				auto Make = [](std::initializer_list<TPair<const TCHAR*, TSharedPtr<FJsonValue>>> Fields)
				{
					TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
					for (const TPair<const TCHAR*, TSharedPtr<FJsonValue>>& F : Fields) { O->SetField(F.Key, F.Value); }
					return O;
				};
				Table.Add(TEXT("canvas"), Make({ { TEXT("anchors"), Arr({ 0, 0, 0, 0 }) }, { TEXT("alignment"), Arr({ 0, 0 }) }, { TEXT("position"), Arr({ 0, 0 }) },
					{ TEXT("size"), Arr({ 100, 30 }) }, { TEXT("z"), N(0) }, { TEXT("auto_size"), B(false) } }));
				Table.Add(TEXT("overlay"), Make({ { TEXT("padding"), Arr({ 0, 0, 0, 0 }) }, { TEXT("h_align"), S(TEXT("left")) }, { TEXT("v_align"), S(TEXT("top")) } }));
				for (const TCHAR* Box : { TEXT("vertical_box"), TEXT("horizontal_box") })
				{
					Table.Add(Box, Make({ { TEXT("padding"), Arr({ 0, 0, 0, 0 }) }, { TEXT("h_align"), S(TEXT("fill")) }, { TEXT("v_align"), S(TEXT("fill")) },
						{ TEXT("size_rule"), S(TEXT("auto")) }, { TEXT("fill"), N(1) } }));
				}
				Table.Add(TEXT("uniform_grid"), Make({ { TEXT("row"), N(0) }, { TEXT("column"), N(0) }, { TEXT("h_align"), S(TEXT("left")) }, { TEXT("v_align"), S(TEXT("top")) } }));
				Table.Add(TEXT("border"), Make({ { TEXT("padding"), Arr({ 4, 2, 4, 2 }) }, { TEXT("h_align"), S(TEXT("fill")) }, { TEXT("v_align"), S(TEXT("fill")) } }));
				Table.Add(TEXT("size_box"), Make({ { TEXT("padding"), Arr({ 0, 0, 0, 0 }) }, { TEXT("h_align"), S(TEXT("fill")) }, { TEXT("v_align"), S(TEXT("fill")) } }));
				Table.Add(TEXT("button"), Make({ { TEXT("padding"), Arr({ 4, 2, 4, 2 }) }, { TEXT("h_align"), S(TEXT("center")) }, { TEXT("v_align"), S(TEXT("center")) } }));
			}
			return Table;
		}

		void NoteUnsupported(TArray<TSharedPtr<FJsonValue>>& Out, const FString& Widget, const FString& Property, const FString& Reason)
		{
			TSharedRef<FJsonObject> U = MakeShared<FJsonObject>();
			U->SetStringField(TEXT("widget"), Widget);
			U->SetStringField(TEXT("property"), Property);
			U->SetStringField(TEXT("reason"), Reason);
			Out.Add(MakeShared<FJsonValueObject>(U));
		}

		uint8 ReadJustification(const UTextBlock* Text)
		{
			static const FProperty* Prop = UTextLayoutWidget::StaticClass()->FindPropertyByName(TEXT("Justification"));
			if (const FByteProperty* Byte = CastField<FByteProperty>(Prop))
			{
				return Byte->GetPropertyValue_InContainer(Text);
			}
			return ETextJustify::Left;
		}
	}

	using namespace SpecPrivate;

	UClass* ClassForType(const FString& Type)
	{
		const FTypeEntry* E = FindType(Type);
		return E ? E->Class() : nullptr;
	}

	FString TypeForWidget(const UWidget* Widget)
	{
		if (!Widget)
		{
			return FString();
		}
		for (const FTypeEntry& E : Types())
		{
			if (Widget->GetClass() == E.Class())
			{
				return E.Name;
			}
		}
		return FString();
	}

	FString ChildSlotKind(const FString& ParentType)
	{
		const FTypeEntry* E = FindType(ParentType);
		return E ? FString(E->ChildSlot) : FString();
	}

	bool IsSingleChild(const FString& Type)
	{
		const FTypeEntry* E = FindType(Type);
		return E && E->bSingle;
	}

	bool IsPanelType(const FString& Type)
	{
		return !ChildSlotKind(Type).IsEmpty();
	}

	bool LoadAssets(const TSharedPtr<FJsonObject>& AssetsMap, FAssets& Out, FEditorMcpError& OutError)
	{
		if (!AssetsMap.IsValid())
		{
			return true;
		}
		for (const TPair<FString, TSharedPtr<FJsonValue>>& P : AssetsMap->Values)
		{
			FString Path;
			if (!P.Value.IsValid() || !P.Value->TryGetString(Path))
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("assets.%s must be a texture path string"), *P.Key));
				return false;
			}
			const FString Package = WidgetMcp::ToPackagePath(Path);
			UTexture2D* Texture = LoadObject<UTexture2D>(nullptr, *(Package + TEXT(".") + FPackageName::GetShortName(Package)));
			if (!Texture)
			{
				TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
				D->SetStringField(TEXT("asset"), P.Key);
				D->SetStringField(TEXT("path"), Path);
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::AssetNotFound, FString::Printf(TEXT("assets.%s → '%s' is not a Texture2D"), *P.Key, *Path), nullptr, D);
				return false;
			}
			Out.Textures.Add(P.Key, Texture);
			Out.IdByPackage.Add(Package, P.Key);
#if WITH_EDITORONLY_DATA
			Out.Sizes.Add(P.Key, FVector2D(Texture->Source.GetSizeX(), Texture->Source.GetSizeY()));
#else
			Out.Sizes.Add(P.Key, FVector2D(Texture->GetSizeX(), Texture->GetSizeY()));
#endif
		}
		return true;
	}

	TSharedRef<FJsonObject> NormalizeWidget(const TSharedRef<FJsonObject>& Widget, const FString& ParentType, const FAssets& Assets)
	{
		TSharedRef<FJsonObject> W = DeepCopy(MakeShared<FJsonValueObject>(Widget))->AsObject().ToSharedRef();
		CanonColors(W);
		const FString Type = StrField(*W, TEXT("type"));
		if (!ParentType.IsEmpty())
		{
			TSharedPtr<FJsonObject> Slot = ObjField(*W, TEXT("slot"));
			if (!Slot.IsValid())
			{
				Slot = MakeShared<FJsonObject>();
			}
			const FString Kind = ChildSlotKind(ParentType);
			if (!Kind.IsEmpty())
			{
				SetDefault(Slot.ToSharedRef(), TEXT("kind"), MakeShared<FJsonValueString>(Kind));
			}
			if (const TSharedRef<FJsonObject>* Defaults = SlotDefaults().Find(StrField(*Slot, TEXT("kind"))))
			{
				for (const TPair<FString, TSharedPtr<FJsonValue>>& P : (*Defaults)->Values) { SetDefault(Slot.ToSharedRef(), *P.Key, P.Value); }
			}
			W->SetObjectField(TEXT("slot"), Slot);
		}
		const FTypeEntry* Entry = FindType(Type);
		SetDefault(W, TEXT("visibility"), S(Entry && Entry->bPanelVisibility ? TEXT("self_hit_test_invisible") : TEXT("visible")));
		TSharedPtr<FJsonObject> Style = ObjField(*W, TEXT("style"));
		if (!Style.IsValid())
		{
			Style = MakeShared<FJsonObject>();
		}
		if (Type == TEXT("ProgressBar"))
		{
			SetDefault(Style.ToSharedRef(), TEXT("fill_color"), S(TEXT("#FFFFFFFF")));
			SetDefault(Style.ToSharedRef(), TEXT("percent"), N(0));
			SetDefault(Style.ToSharedRef(), TEXT("bar_fill_type"), S(TEXT("left_to_right")));
		}
		else if (Type == TEXT("Spacer"))
		{
			SetDefault(Style.ToSharedRef(), TEXT("size"), Arr({ 1, 1 }));
		}
		else if (Type == TEXT("UniformGridPanel"))
		{
			SetDefault(Style.ToSharedRef(), TEXT("slot_padding"), Arr({ 0, 0, 0, 0 }));
			SetDefault(Style.ToSharedRef(), TEXT("min_slot_width"), N(0));
			SetDefault(Style.ToSharedRef(), TEXT("min_slot_height"), N(0));
		}
		for (TPair<FString, TSharedPtr<FJsonValue>>& P : Style->Values)
		{
			if (IsBrushKey(P.Key) && P.Value.IsValid() && P.Value->Type == EJson::Object)
			{
				P.Value = MakeShared<FJsonValueObject>(NormalizeBrush(P.Value->AsObject().ToSharedRef(), Assets));
			}
		}
		if (Style->Values.Num() > 0)
		{
			W->SetObjectField(TEXT("style"), Style);
		}
		else
		{
			W->RemoveField(TEXT("style"));
		}
		if (Type == TEXT("TextBlock"))
		{
			TSharedPtr<FJsonObject> Text = ObjField(*W, TEXT("text"));
			if (!Text.IsValid())
			{
				Text = MakeShared<FJsonObject>();
			}
			SetDefault(Text.ToSharedRef(), TEXT("source"), S(TEXT("static")));
			SetDefault(Text.ToSharedRef(), Text->GetStringField(TEXT("source")) == TEXT("static") ? TEXT("value") : TEXT("sample"), S(TEXT("")));
			W->SetObjectField(TEXT("text"), Text);
			TSharedPtr<FJsonObject> Font = ObjField(*W, TEXT("font"));
			if (!Font.IsValid())
			{
				Font = MakeShared<FJsonObject>();
			}
			SetDefault(Font.ToSharedRef(), TEXT("size"), N(24));
			SetDefault(Font.ToSharedRef(), TEXT("weight"), S(TEXT("bold")));
			SetDefault(Font.ToSharedRef(), TEXT("color"), S(TEXT("#FFFFFFFF")));
			SetDefault(Font.ToSharedRef(), TEXT("family"), MakeShared<FJsonValueNull>());
			W->SetObjectField(TEXT("font"), Font);
			SetDefault(W, TEXT("justification"), S(TEXT("left")));
		}
		return W;
	}

	TSharedRef<FJsonObject> WbpView(const TSharedRef<FJsonObject>& NormalizedWidget)
	{
		TSharedRef<FJsonObject> V = DeepCopy(MakeShared<FJsonValueObject>(NormalizedWidget))->AsObject().ToSharedRef();
		V->RemoveField(TEXT("bbox_intent"));
		V->RemoveField(TEXT("binding"));
		V->RemoveField(TEXT("note"));
		if (TSharedPtr<FJsonObject> Text = ObjField(*V, TEXT("text")))
		{
			FString Value;
			if (!Text->TryGetStringField(TEXT("value"), Value))
			{
				Text->TryGetStringField(TEXT("sample"), Value);
			}
			TSharedRef<FJsonObject> T = MakeShared<FJsonObject>();
			T->SetStringField(TEXT("value"), Value);
			V->SetObjectField(TEXT("text"), T);
		}
		return V;
	}

	bool ValidateWidget(const FJsonObject& Widget, const FString& Type, const FAssets& Assets, FString& OutError)
	{
		const FString Id = StrField(Widget, TEXT("id"));
		FString Vis;
		ESlateVisibility VisValue;
		if (Widget.TryGetStringField(TEXT("visibility"), Vis) && !FromName(Visibilities(), Vis, VisValue))
		{
			OutError = FString::Printf(TEXT("'%s'.visibility '%s' is unknown"), *Id, *Vis);
			return false;
		}
		if (TSharedPtr<FJsonObject> Slot = ObjField(Widget, TEXT("slot")))
		{
			EHorizontalAlignment H;
			EVerticalAlignment V;
			FString HName, VName;
			if ((Slot->TryGetStringField(TEXT("h_align"), HName) && !FromName(HAligns(), HName, H)) || (Slot->TryGetStringField(TEXT("v_align"), VName) && !FromName(VAligns(), VName, V)))
			{
				OutError = FString::Printf(TEXT("'%s'.slot alignment '%s'/'%s' is unknown"), *Id, *HName, *VName);
				return false;
			}
		}
		if (TSharedPtr<FJsonObject> Style = ObjField(Widget, TEXT("style")))
		{
			const TSet<FString>* Allowed = StyleKeys().Find(Type);
			for (const TPair<FString, TSharedPtr<FJsonValue>>& P : Style->Values)
			{
				if (!Allowed || !Allowed->Contains(P.Key))
				{
					OutError = FString::Printf(TEXT("'%s' (%s) has no style '%s'"), *Id, *Type, *P.Key);
					return false;
				}
				if (IsBrushKey(P.Key))
				{
					if (!P.Value.IsValid() || P.Value->Type != EJson::Object || !ValidateBrush(*P.Value->AsObject(), Assets, FString::Printf(TEXT("'%s'.style.%s"), *Id, *P.Key), OutError))
					{
						if (OutError.IsEmpty()) { OutError = FString::Printf(TEXT("'%s'.style.%s must be an object"), *Id, *P.Key); }
						return false;
					}
				}
			}
			FLinearColor C;
			FString Hex;
			if (Style->TryGetStringField(TEXT("fill_color"), Hex) && !WidgetMcp::ParseHexColor(Hex, C))
			{
				OutError = FString::Printf(TEXT("'%s'.style.fill_color '%s' is not #RRGGBB(AA)"), *Id, *Hex);
				return false;
			}
			EProgressBarFillType::Type Fill;
			FString FillName;
			if (Style->TryGetStringField(TEXT("bar_fill_type"), FillName) && !FromName(FillTypes(), FillName, Fill))
			{
				OutError = FString::Printf(TEXT("'%s'.style.bar_fill_type '%s' is unknown"), *Id, *FillName);
				return false;
			}
		}
		const bool bText = Type == TEXT("TextBlock");
		for (const TCHAR* Key : { TEXT("text"), TEXT("font"), TEXT("justification") })
		{
			if (!bText && Widget.HasField(Key))
			{
				OutError = FString::Printf(TEXT("'%s' (%s) cannot have '%s'"), *Id, *Type, Key);
				return false;
			}
		}
		if (bText)
		{
			if (TSharedPtr<FJsonObject> Font = ObjField(Widget, TEXT("font")))
			{
				const TCHAR* Typeface = nullptr;
				FString Weight;
				if (Font->TryGetStringField(TEXT("weight"), Weight) && !FromName(Weights(), Weight, Typeface))
				{
					OutError = FString::Printf(TEXT("'%s'.font.weight '%s' is unknown"), *Id, *Weight);
					return false;
				}
				FString Hex, Family;
				FLinearColor C;
				if (Font->TryGetStringField(TEXT("color"), Hex) && !WidgetMcp::ParseHexColor(Hex, C))
				{
					OutError = FString::Printf(TEXT("'%s'.font.color '%s' is not #RRGGBB(AA)"), *Id, *Hex);
					return false;
				}
				if (Font->TryGetStringField(TEXT("family"), Family) && !Family.IsEmpty() && !LoadObject<UObject>(nullptr, *Family))
				{
					OutError = FString::Printf(TEXT("'%s'.font.family '%s' does not load"), *Id, *Family);
					return false;
				}
			}
			ETextJustify::Type J;
			FString JName;
			if (Widget.TryGetStringField(TEXT("justification"), JName) && !FromName(Justifies(), JName, J))
			{
				OutError = FString::Printf(TEXT("'%s'.justification '%s' is unknown"), *Id, *JName);
				return false;
			}
		}
		return true;
	}

	bool ApplySlot(UPanelSlot* Slot, const FJsonObject& J, FString& OutError)
	{
		if (UCanvasPanelSlot* Canvas = Cast<UCanvasPanelSlot>(Slot))
		{
			FVector4 A(0, 0, 0, 0);
			WidgetMcp::ReadVec4(J, TEXT("anchors"), A);
			FVector2D Alignment(0, 0), Position(0, 0), Size(100, 30);
			WidgetMcp::ReadVec2(J, TEXT("alignment"), Alignment);
			WidgetMcp::ReadVec2(J, TEXT("position"), Position);
			WidgetMcp::ReadVec2(J, TEXT("size"), Size);
			Canvas->SetAnchors(FAnchors(A.X, A.Y, A.Z, A.W));
			Canvas->SetAlignment(Alignment);
			Canvas->SetPosition(Position);
			Canvas->SetSize(Size);
			Canvas->SetZOrder(static_cast<int32>(NumField(J, TEXT("z"), 0)));
			bool bAuto = false;
			J.TryGetBoolField(TEXT("auto_size"), bAuto);
			Canvas->SetAutoSize(bAuto);
			return true;
		}
		const FAlignPadding AP = ReadAlignPadding(J);
		if (UOverlaySlot* O = Cast<UOverlaySlot>(Slot)) { O->SetPadding(AP.Padding); O->SetHorizontalAlignment(AP.H); O->SetVerticalAlignment(AP.V); return true; }
		if (UBorderSlot* Bo = Cast<UBorderSlot>(Slot)) { Bo->SetPadding(AP.Padding); Bo->SetHorizontalAlignment(AP.H); Bo->SetVerticalAlignment(AP.V); return true; }
		if (USizeBoxSlot* Sz = Cast<USizeBoxSlot>(Slot)) { Sz->SetPadding(AP.Padding); Sz->SetHorizontalAlignment(AP.H); Sz->SetVerticalAlignment(AP.V); return true; }
		if (UButtonSlot* Bu = Cast<UButtonSlot>(Slot)) { Bu->SetPadding(AP.Padding); Bu->SetHorizontalAlignment(AP.H); Bu->SetVerticalAlignment(AP.V); return true; }
		const bool bFill = StrField(J, TEXT("size_rule"), TEXT("auto")) == TEXT("fill");
		FSlateChildSize ChildSize(bFill ? ESlateSizeRule::Fill : ESlateSizeRule::Automatic);
		ChildSize.Value = static_cast<float>(NumField(J, TEXT("fill"), 1.0));
		if (UVerticalBoxSlot* Vb = Cast<UVerticalBoxSlot>(Slot)) { Vb->SetPadding(AP.Padding); Vb->SetHorizontalAlignment(AP.H); Vb->SetVerticalAlignment(AP.V); Vb->SetSize(ChildSize); return true; }
		if (UHorizontalBoxSlot* Hb = Cast<UHorizontalBoxSlot>(Slot)) { Hb->SetPadding(AP.Padding); Hb->SetHorizontalAlignment(AP.H); Hb->SetVerticalAlignment(AP.V); Hb->SetSize(ChildSize); return true; }
		if (UUniformGridSlot* G = Cast<UUniformGridSlot>(Slot))
		{
			G->SetRow(static_cast<int32>(NumField(J, TEXT("row"), 0)));
			G->SetColumn(static_cast<int32>(NumField(J, TEXT("column"), 0)));
			G->SetHorizontalAlignment(AP.H);
			G->SetVerticalAlignment(AP.V);
			return true;
		}
		OutError = FString::Printf(TEXT("slot class %s is not in the spec vocabulary"), Slot ? *Slot->GetClass()->GetName() : TEXT("(null)"));
		return false;
	}

	TSharedPtr<FJsonObject> ExportSlot(const UPanelSlot* Slot)
	{
		TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
		if (const UCanvasPanelSlot* Canvas = Cast<UCanvasPanelSlot>(Slot))
		{
			const FAnchors A = Canvas->GetAnchors();
			J->SetStringField(TEXT("kind"), TEXT("canvas"));
			J->SetArrayField(TEXT("anchors"), { WidgetMcp::Num(A.Minimum.X), WidgetMcp::Num(A.Minimum.Y), WidgetMcp::Num(A.Maximum.X), WidgetMcp::Num(A.Maximum.Y) });
			J->SetField(TEXT("alignment"), WidgetMcp::Vec2(Canvas->GetAlignment()));
			J->SetField(TEXT("position"), WidgetMcp::Vec2(Canvas->GetPosition()));
			J->SetField(TEXT("size"), WidgetMcp::Vec2(Canvas->GetSize()));
			J->SetNumberField(TEXT("z"), Canvas->GetZOrder());
			J->SetBoolField(TEXT("auto_size"), Canvas->GetAutoSize());
			return J;
		}
		if (const UOverlaySlot* O = Cast<UOverlaySlot>(Slot)) { J->SetStringField(TEXT("kind"), TEXT("overlay")); WriteAlignPadding(J, O->GetPadding(), O->GetHorizontalAlignment(), O->GetVerticalAlignment()); return J; }
		if (const UBorderSlot* Bo = Cast<UBorderSlot>(Slot)) { J->SetStringField(TEXT("kind"), TEXT("border")); WriteAlignPadding(J, Bo->GetPadding(), Bo->GetHorizontalAlignment(), Bo->GetVerticalAlignment()); return J; }
		if (const USizeBoxSlot* Sz = Cast<USizeBoxSlot>(Slot)) { J->SetStringField(TEXT("kind"), TEXT("size_box")); WriteAlignPadding(J, Sz->GetPadding(), Sz->GetHorizontalAlignment(), Sz->GetVerticalAlignment()); return J; }
		if (const UButtonSlot* Bu = Cast<UButtonSlot>(Slot)) { J->SetStringField(TEXT("kind"), TEXT("button")); WriteAlignPadding(J, Bu->GetPadding(), Bu->GetHorizontalAlignment(), Bu->GetVerticalAlignment()); return J; }
		auto Box = [&J](const TCHAR* Kind, const FMargin& Padding, EHorizontalAlignment H, EVerticalAlignment V, const FSlateChildSize& Size)
		{
			J->SetStringField(TEXT("kind"), Kind);
			WriteAlignPadding(J, Padding, H, V);
			J->SetStringField(TEXT("size_rule"), Size.SizeRule == ESlateSizeRule::Fill ? TEXT("fill") : TEXT("auto"));
			J->SetField(TEXT("fill"), WidgetMcp::Num(Size.Value));
		};
		if (const UVerticalBoxSlot* Vb = Cast<UVerticalBoxSlot>(Slot)) { Box(TEXT("vertical_box"), Vb->GetPadding(), Vb->GetHorizontalAlignment(), Vb->GetVerticalAlignment(), Vb->GetSize()); return J; }
		if (const UHorizontalBoxSlot* Hb = Cast<UHorizontalBoxSlot>(Slot)) { Box(TEXT("horizontal_box"), Hb->GetPadding(), Hb->GetHorizontalAlignment(), Hb->GetVerticalAlignment(), Hb->GetSize()); return J; }
		if (const UUniformGridSlot* G = Cast<UUniformGridSlot>(Slot))
		{
			J->SetStringField(TEXT("kind"), TEXT("uniform_grid"));
			J->SetNumberField(TEXT("row"), G->GetRow());
			J->SetNumberField(TEXT("column"), G->GetColumn());
			J->SetStringField(TEXT("h_align"), ToName(HAligns(), G->GetHorizontalAlignment()));
			J->SetStringField(TEXT("v_align"), ToName(VAligns(), G->GetVerticalAlignment()));
			return J;
		}
		return nullptr;
	}

	bool ApplyWidget(UWidget* Widget, const FJsonObject& J, const FAssets& Assets, FString& OutError)
	{
		ESlateVisibility Vis = Widget->GetVisibility();
		FString VisName;
		if (J.TryGetStringField(TEXT("visibility"), VisName))
		{
			FromName(Visibilities(), VisName, Vis);
		}
		Widget->SetVisibility(Vis);

		const TSharedPtr<FJsonObject> Style = ObjField(J, TEXT("style"));
		auto BrushOr = [&](const TCHAR* Key, const FSlateBrush& Fallback, FSlateBrush& Out) -> bool
		{
			const TSharedPtr<FJsonObject> BrushJson = Style.IsValid() ? ObjField(*Style, Key) : nullptr;
			if (!BrushJson.IsValid())
			{
				Out = Fallback;   // 생략 = CDO
				return true;
			}
			return BrushFromJson(*BrushJson, Assets, Out, OutError);
		};

		if (UBorder* Border = Cast<UBorder>(Widget))
		{
			FSlateBrush Brush;
			if (!BrushOr(TEXT("brush"), GetDefault<UBorder>()->Background, Brush)) { return false; }
			Border->SetBrush(Brush);
		}
		else if (UImage* Image = Cast<UImage>(Widget))
		{
			FSlateBrush Brush;
			if (!BrushOr(TEXT("brush"), GetDefault<UImage>()->GetBrush(), Brush)) { return false; }
			Image->SetBrush(Brush);
		}
		else if (UProgressBar* Bar = Cast<UProgressBar>(Widget))
		{
			const FProgressBarStyle& Cdo = GetDefault<UProgressBar>()->GetWidgetStyle();
			FProgressBarStyle BarStyle = Cdo;
			if (!BrushOr(TEXT("background"), Cdo.BackgroundImage, BarStyle.BackgroundImage)) { return false; }
			if (!BrushOr(TEXT("fill"), Cdo.FillImage, BarStyle.FillImage)) { return false; }
			Bar->SetWidgetStyle(BarStyle);
			const FJsonObject Empty;
			const FJsonObject& St = Style.IsValid() ? *Style : Empty;
			Bar->SetFillColorAndOpacity(ColorField(St, TEXT("fill_color"), FLinearColor::White));
			Bar->SetPercent(static_cast<float>(NumField(St, TEXT("percent"), 0.0)));
			EProgressBarFillType::Type Fill = EProgressBarFillType::LeftToRight;
			FromName(FillTypes(), StrField(St, TEXT("bar_fill_type"), TEXT("left_to_right")), Fill);
			Bar->SetBarFillType(Fill);
		}
		else if (UButton* Button = Cast<UButton>(Widget))
		{
			const FButtonStyle& Cdo = GetDefault<UButton>()->GetStyle();
			FButtonStyle ButtonStyle = Cdo;
			if (!BrushOr(TEXT("normal"), Cdo.Normal, ButtonStyle.Normal)) { return false; }
			if (!BrushOr(TEXT("hovered"), Cdo.Hovered, ButtonStyle.Hovered)) { return false; }
			if (!BrushOr(TEXT("pressed"), Cdo.Pressed, ButtonStyle.Pressed)) { return false; }
			Button->SetStyle(ButtonStyle);
		}
		else if (USizeBox* Size = Cast<USizeBox>(Widget))
		{
			double V = 0.0;
			if (Style.IsValid() && Style->TryGetNumberField(TEXT("width_override"), V)) { Size->SetWidthOverride(static_cast<float>(V)); } else { Size->ClearWidthOverride(); }
			if (Style.IsValid() && Style->TryGetNumberField(TEXT("height_override"), V)) { Size->SetHeightOverride(static_cast<float>(V)); } else { Size->ClearHeightOverride(); }
		}
		else if (USpacer* Spacer = Cast<USpacer>(Widget))
		{
			FVector2D V(1, 1);
			if (Style.IsValid()) { WidgetMcp::ReadVec2(*Style, TEXT("size"), V); }
			Spacer->SetSize(V);
		}
		else if (UUniformGridPanel* Grid = Cast<UUniformGridPanel>(Widget))
		{
			FMargin P(0.f);
			const FJsonObject Empty;
			const FJsonObject& St = Style.IsValid() ? *Style : Empty;
			WidgetMcp::ReadMargin(St, TEXT("slot_padding"), P);
			Grid->SetSlotPadding(P);
			Grid->SetMinDesiredSlotWidth(static_cast<float>(NumField(St, TEXT("min_slot_width"), 0.0)));
			Grid->SetMinDesiredSlotHeight(static_cast<float>(NumField(St, TEXT("min_slot_height"), 0.0)));
		}
		else if (UTextBlock* Text = Cast<UTextBlock>(Widget))
		{
			const TSharedPtr<FJsonObject> TextJson = ObjField(J, TEXT("text"));
			FString Value;
			if (TextJson.IsValid())
			{
				const bool bDynamic = StrField(*TextJson, TEXT("source"), TEXT("static")) == TEXT("dynamic");
				Value = StrField(*TextJson, bDynamic ? TEXT("sample") : TEXT("value"), StrField(*TextJson, TEXT("value")));
			}
			Text->SetText(FText::FromString(Value));
			const TSharedPtr<FJsonObject> FontJson = ObjField(J, TEXT("font"));
			const FJsonObject Empty;
			const FJsonObject& F = FontJson.IsValid() ? *FontJson : Empty;
			FSlateFontInfo Font = GetDefault<UTextBlock>()->GetFont();
			FString Family;
			if (F.TryGetStringField(TEXT("family"), Family) && !Family.IsEmpty())
			{
				UObject* FontObject = LoadObject<UObject>(nullptr, *Family);
				if (!FontObject)
				{
					OutError = FString::Printf(TEXT("font family '%s' does not load"), *Family);
					return false;
				}
				Font.FontObject = FontObject;
			}
			const TCHAR* Typeface = TEXT("Bold");
			FromName(Weights(), StrField(F, TEXT("weight"), TEXT("bold")), Typeface);
			Font.TypefaceFontName = FName(Typeface);
			Font.Size = static_cast<float>(NumField(F, TEXT("size"), 24.0));
			Text->SetFont(Font);
			Text->SetColorAndOpacity(FSlateColor(ColorField(F, TEXT("color"), FLinearColor::White)));
			ETextJustify::Type Justify = ETextJustify::Left;
			FromName(Justifies(), StrField(J, TEXT("justification"), TEXT("left")), Justify);
			Text->SetJustification(Justify);
		}
		return true;
	}

	void ExportWidgetProps(const UWidget* Widget, const FAssets* Assets, const TSharedRef<FJsonObject>& Out, TArray<TSharedPtr<FJsonValue>>& Unsupported)
	{
		const FString Id = Widget->GetName();
		Out->SetStringField(TEXT("visibility"), ToName(Visibilities(), Widget->GetVisibility()));
		if (!FMath::IsNearlyEqual(Widget->GetRenderOpacity(), 1.f)) { NoteUnsupported(Unsupported, Id, TEXT("RenderOpacity"), TEXT("not in the spec vocabulary")); }
		if (!Widget->GetRenderTransform().IsIdentity()) { NoteUnsupported(Unsupported, Id, TEXT("RenderTransform"), TEXT("not in the spec vocabulary")); }
		if (!Widget->GetIsEnabled()) { NoteUnsupported(Unsupported, Id, TEXT("bIsEnabled"), TEXT("disabled widgets are not in the spec vocabulary")); }
		if (Widget->GetClipping() != EWidgetClipping::Inherit) { NoteUnsupported(Unsupported, Id, TEXT("Clipping"), TEXT("not in the spec vocabulary")); }

		TSharedRef<FJsonObject> Style = MakeShared<FJsonObject>();
		auto BrushIfChanged = [&](const TCHAR* Key, const FSlateBrush& Brush, const FSlateBrush& Cdo)
		{
			if (!(Brush == Cdo))
			{
				Style->SetObjectField(Key, BrushToJson(Brush, Assets, Id + TEXT(".style.") + Key, Unsupported));
			}
		};
		if (const UBorder* Border = Cast<UBorder>(Widget))
		{
			BrushIfChanged(TEXT("brush"), Border->Background, GetDefault<UBorder>()->Background);
			if (!Border->GetBrushColor().Equals(FLinearColor::White)) { NoteUnsupported(Unsupported, Id, TEXT("BrushColor"), TEXT("use style.brush.color")); }
			if (!Border->GetContentColorAndOpacity().Equals(FLinearColor::White)) { NoteUnsupported(Unsupported, Id, TEXT("ContentColorAndOpacity"), TEXT("not in the spec vocabulary")); }
		}
		else if (const UImage* Image = Cast<UImage>(Widget))
		{
			BrushIfChanged(TEXT("brush"), Image->GetBrush(), GetDefault<UImage>()->GetBrush());
			if (!Image->GetColorAndOpacity().Equals(FLinearColor::White)) { NoteUnsupported(Unsupported, Id, TEXT("ColorAndOpacity"), TEXT("use style.brush.color")); }
		}
		else if (const UProgressBar* Bar = Cast<UProgressBar>(Widget))
		{
			const FProgressBarStyle& Cdo = GetDefault<UProgressBar>()->GetWidgetStyle();
			BrushIfChanged(TEXT("background"), Bar->GetWidgetStyle().BackgroundImage, Cdo.BackgroundImage);
			BrushIfChanged(TEXT("fill"), Bar->GetWidgetStyle().FillImage, Cdo.FillImage);
			Style->SetStringField(TEXT("fill_color"), WidgetMcp::ToHexColor(Bar->GetFillColorAndOpacity()));
			Style->SetField(TEXT("percent"), WidgetMcp::Num(Bar->GetPercent()));
			Style->SetStringField(TEXT("bar_fill_type"), ToName(FillTypes(), Bar->GetBarFillType()));
		}
		else if (const UButton* Button = Cast<UButton>(Widget))
		{
			const FButtonStyle& Cdo = GetDefault<UButton>()->GetStyle();
			BrushIfChanged(TEXT("normal"), Button->GetStyle().Normal, Cdo.Normal);
			BrushIfChanged(TEXT("hovered"), Button->GetStyle().Hovered, Cdo.Hovered);
			BrushIfChanged(TEXT("pressed"), Button->GetStyle().Pressed, Cdo.Pressed);
		}
		else if (const USizeBox* Size = Cast<USizeBox>(Widget))
		{
PRAGMA_DISABLE_DEPRECATION_WARNINGS
			if (Size->bOverride_WidthOverride) { Style->SetField(TEXT("width_override"), WidgetMcp::Num(Size->GetWidthOverride())); }
			if (Size->bOverride_HeightOverride) { Style->SetField(TEXT("height_override"), WidgetMcp::Num(Size->GetHeightOverride())); }
PRAGMA_ENABLE_DEPRECATION_WARNINGS
		}
		else if (const USpacer* Spacer = Cast<USpacer>(Widget))
		{
			Style->SetField(TEXT("size"), WidgetMcp::Vec2(Spacer->GetSize()));
		}
		else if (const UUniformGridPanel* Grid = Cast<UUniformGridPanel>(Widget))
		{
			Style->SetField(TEXT("slot_padding"), WidgetMcp::Margin4(Grid->GetSlotPadding()));
			Style->SetField(TEXT("min_slot_width"), WidgetMcp::Num(Grid->GetMinDesiredSlotWidth()));
			Style->SetField(TEXT("min_slot_height"), WidgetMcp::Num(Grid->GetMinDesiredSlotHeight()));
		}
		else if (const UTextBlock* Text = Cast<UTextBlock>(Widget))
		{
			TSharedRef<FJsonObject> T = MakeShared<FJsonObject>();
			T->SetStringField(TEXT("value"), Text->GetText().ToString());
			Out->SetObjectField(TEXT("text"), T);
			const FSlateFontInfo& Font = Text->GetFont();
			TSharedRef<FJsonObject> F = MakeShared<FJsonObject>();
			F->SetField(TEXT("size"), WidgetMcp::Num(Font.Size));
			FString Weight = WeightFromTypeface(Font.TypefaceFontName);
			if (Weight.IsEmpty())
			{
				NoteUnsupported(Unsupported, Id, TEXT("Font.TypefaceFontName"), FString::Printf(TEXT("typeface '%s' has no spec weight"), *Font.TypefaceFontName.ToString()));
				Weight = TEXT("regular");
			}
			F->SetStringField(TEXT("weight"), Weight);
			const FSlateColor Color = Text->GetColorAndOpacity();
			if (!Color.IsColorSpecified()) { NoteUnsupported(Unsupported, Id, TEXT("ColorAndOpacity"), TEXT("uses a style color rule")); }
			F->SetStringField(TEXT("color"), WidgetMcp::ToHexColor(Color.IsColorSpecified() ? Color.GetSpecifiedColor() : FLinearColor::White));
			const UObject* CdoFont = GetDefault<UTextBlock>()->GetFont().FontObject;
			if (Font.FontObject == CdoFont) { F->SetField(TEXT("family"), MakeShared<FJsonValueNull>()); }
			else { F->SetStringField(TEXT("family"), GetPathNameSafe(Font.FontObject)); }
			if (Font.OutlineSettings.OutlineSize > 0) { NoteUnsupported(Unsupported, Id, TEXT("Font.OutlineSettings"), TEXT("text outline is not in the spec vocabulary")); }
			if (Font.LetterSpacing != 0) { NoteUnsupported(Unsupported, Id, TEXT("Font.LetterSpacing"), TEXT("not in the spec vocabulary")); }
			Out->SetObjectField(TEXT("font"), F);
			const FString Justify = ToName(Justifies(), static_cast<ETextJustify::Type>(ReadJustification(Text)));
			Out->SetStringField(TEXT("justification"), Justify.IsEmpty() ? TEXT("left") : Justify);
			if (Text->GetAutoWrapText()) { NoteUnsupported(Unsupported, Id, TEXT("AutoWrapText"), TEXT("not in the spec vocabulary")); }
		}
		if (Style->Values.Num() > 0)
		{
			Out->SetObjectField(TEXT("style"), Style);
		}
	}

	void CollectTextures(const UWidget* Widget, TArray<UTexture2D*>& Out)
	{
		auto Add = [&Out](const FSlateBrush& Brush) { if (UTexture2D* T = Cast<UTexture2D>(Brush.GetResourceObject())) { Out.AddUnique(T); } };
		if (const UBorder* Border = Cast<UBorder>(Widget)) { Add(Border->Background); }
		else if (const UImage* Image = Cast<UImage>(Widget)) { Add(Image->GetBrush()); }
		else if (const UProgressBar* Bar = Cast<UProgressBar>(Widget)) { Add(Bar->GetWidgetStyle().BackgroundImage); Add(Bar->GetWidgetStyle().FillImage); }
		else if (const UButton* Button = Cast<UButton>(Widget)) { Add(Button->GetStyle().Normal); Add(Button->GetStyle().Hovered); Add(Button->GetStyle().Pressed); }
	}
}
