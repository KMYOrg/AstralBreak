#include "Spike/WidgetMcpSpike.h"

#include "AnimMcpLog.h"
#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetTree.h"
#include "Bridge/AnimMcpTypes.h"
#include "Components/Border.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/Image.h"
#include "Components/ProgressBar.h"
#include "Components/TextBlock.h"
#include "Editor.h"
#include "Engine/Texture2D.h"
#include "Engine/TextureRenderTarget2D.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "ImageCore.h"
#include "ImageUtils.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "RenderingThread.h"
#include "Slate/WidgetRenderer.h"
#include "TextureResource.h"
#include "UMGEditorProjectSettings.h"
#include "UObject/Package.h"
#include "UObject/StrongObjectPtr.h"
#include "WidgetBlueprint.h"
#include "WidgetBlueprintFactory.h"

namespace WidgetMcpSpike
{
	namespace
	{
		struct FSpecWidget
		{
			FString Id;
			FString Type;
			FString Parent;
			TSharedPtr<FJsonObject> Json;
			bool bCanvasSlot = false;
			FVector2D Position = FVector2D::ZeroVector;
			FVector2D Size = FVector2D(100, 30);
			FVector2D Alignment = FVector2D::ZeroVector;
			FVector4 Anchors = FVector4(0, 0, 0, 0);
		};

		FVector2D ReadVec2(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Key, const FVector2D& Default)
		{
			const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
			if (Obj.IsValid() && Obj->TryGetArrayField(Key, Arr) && Arr->Num() == 2)
			{
				return FVector2D((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber());
			}
			return Default;
		}

		FLinearColor ReadColor(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Key, const FLinearColor& Default)
		{
			FString Hex;
			if (Obj.IsValid() && Obj->TryGetStringField(Key, Hex) && !Hex.IsEmpty())
			{
				return FLinearColor::FromSRGBColor(FColor::FromHex(Hex));
			}
			return Default;
		}

		TArray<TSharedPtr<FJsonValue>> Vec2Json(const FVector2D& V)
		{
			return { MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.X * 100.0) / 100.0), MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.Y * 100.0) / 100.0) };
		}

		/** 8 px 체커 — UI 텍스처 설정(TC_EditorIcon · TEXTUREGROUP_UI · NoMipmaps · NeverStream · sRGB)을 단 트랜지언트 텍스처 */
		UTexture2D* MakeChecker(int32 N)
		{
			TArray64<uint8> Bytes;
			Bytes.SetNumUninitialized(int64(N) * N * 4);
			for (int32 Y = 0; Y < N; ++Y)
			{
				for (int32 X = 0; X < N; ++X)
				{
					const FColor C = ((X / 8 + Y / 8) % 2) ? FColor(232, 181, 74, 255) : FColor(40, 40, 40, 255);
					uint8* P = &Bytes[(int64(Y) * N + X) * 4];
					P[0] = C.B; P[1] = C.G; P[2] = C.R; P[3] = C.A; // PF_B8G8R8A8
				}
			}
			UTexture2D* Tex = UTexture2D::CreateTransient(N, N, PF_B8G8R8A8, TEXT("T_WidgetSpikeChecker"), Bytes);
			if (!Tex)
			{
				return nullptr;
			}
			Tex->CompressionSettings = TC_EditorIcon;
			Tex->LODGroup = TEXTUREGROUP_UI;
			Tex->SRGB = true;
			Tex->NeverStream = true;
#if WITH_EDITORONLY_DATA
			Tex->MipGenSettings = TMGS_NoMipmaps;
#endif
			Tex->UpdateResource();
			return Tex;
		}

		bool SavePng(const FString& Path, TArray<FColor> Pixels, int32 W, int32 H)
		{
			for (FColor& C : Pixels) { C.A = 255; }
			const FImageView View(Pixels.GetData(), W, H, EGammaSpace::sRGB);
			return FImageUtils::SaveImageByExtension(*Path, View) && IFileManager::Get().FileExists(*Path);
		}

		/** 한 번 그려 픽셀을 읽는다 — 감마 조합 비교용 (렌더러 · 타깃을 매번 새로) */
		bool DrawOnce(const TSharedRef<SWidget>& Slate, const FVector2D& Canvas, bool bGamma, TArray<FColor>& OutPixels, FString& OutFormat)
		{
			FWidgetRenderer* Renderer = new FWidgetRenderer(bGamma, /*bInClearTarget*/ true);
			TStrongObjectPtr<UTextureRenderTarget2D> Target(FWidgetRenderer::CreateTargetFor(Canvas, TF_Bilinear, bGamma));
			Renderer->DrawWidget(Target.Get(), Slate, 1.0f, Canvas, 0.1f);
			FlushRenderingCommands();
			FTextureRenderTargetResource* Resource = Target->GameThread_GetRenderTargetResource();
			const bool bOk = Resource && Resource->ReadPixels(OutPixels);
			OutFormat = FString::Printf(TEXT("%s srgb=%d"), GetPixelFormatString(Target->GetFormat()), Target->SRGB ? 1 : 0);
			BeginCleanup(Renderer);
			return bOk;
		}

		FString Hex(const FColor& C)
		{
			return FString::Printf(TEXT("#%02X%02X%02X"), C.R, C.G, C.B);
		}
	}

	bool Run(const FString& SpecJson, const FString& AssetPath, const FString& OutputDir, FResult& Out, FString& OutError)
	{
		const double Start = FPlatformTime::Seconds();
		TSharedRef<FJsonObject> Report = AnimMcpJson::MakeObject();
		Out.Report = Report;

		// ---- spec ------------------------------------------------------------------------------------------------
		TSharedPtr<FJsonObject> Spec;
		FString ParseError;
		if (!AnimMcpJson::Parse(SpecJson, Spec, ParseError))
		{
			OutError = FString::Printf(TEXT("spec parse: %s"), *ParseError);
			return false;
		}
		const FVector2D Canvas = ReadVec2(Spec, TEXT("canvas"), FVector2D(640, 360));
		FString RootId = TEXT("Root");
		Spec->TryGetStringField(TEXT("root"), RootId);
		TArray<FSpecWidget> Widgets;
		const TArray<TSharedPtr<FJsonValue>>* WidgetArr = nullptr;
		if (!Spec->TryGetArrayField(TEXT("widgets"), WidgetArr))
		{
			OutError = TEXT("spec has no widgets[]");
			return false;
		}
		for (const TSharedPtr<FJsonValue>& V : *WidgetArr)
		{
			FSpecWidget W;
			W.Json = V->AsObject();
			W.Json->TryGetStringField(TEXT("id"), W.Id);
			W.Json->TryGetStringField(TEXT("type"), W.Type);
			W.Json->TryGetStringField(TEXT("parent"), W.Parent);
			const TSharedPtr<FJsonObject>* Slot = nullptr;
			if (W.Json->TryGetObjectField(TEXT("slot"), Slot))
			{
				W.bCanvasSlot = true;
				W.Position = ReadVec2(*Slot, TEXT("position"), W.Position);
				W.Size = ReadVec2(*Slot, TEXT("size"), W.Size);
				W.Alignment = ReadVec2(*Slot, TEXT("alignment"), W.Alignment);
				const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
				if ((*Slot)->TryGetArrayField(TEXT("anchors"), A) && A->Num() == 4)
				{
					W.Anchors = FVector4((*A)[0]->AsNumber(), (*A)[1]->AsNumber(), (*A)[2]->AsNumber(), (*A)[3]->AsNumber());
				}
			}
			Widgets.Add(W);
		}

		// ---- A7: 팩토리만으로 WBP --------------------------------------------------------------------------------
		const UUMGEditorProjectSettings* UmgSettings = GetDefault<UUMGEditorProjectSettings>();
		Out.bUseWidgetTemplateSelector = UmgSettings->bUseWidgetTemplateSelector;
		Out.DefaultRootWidget = UmgSettings->DefaultRootWidget ? UmgSettings->DefaultRootWidget->GetPathName() : TEXT("(none)");

		const FString PackagePath = FPackageName::ObjectPathToPackageName(AssetPath);
		const FString AssetName = FPackageName::GetShortName(PackagePath);
		if (FindPackage(nullptr, *PackagePath) || FPackageName::DoesPackageExist(PackagePath))
		{
			OutError = FString::Printf(TEXT("%s already exists — the spike never overwrites"), *PackagePath);
			return false;
		}
		UPackage* Package = CreatePackage(*PackagePath);
		UWidgetBlueprintFactory* Factory = NewObject<UWidgetBlueprintFactory>(GetTransientPackage());
		Factory->ParentClass = UUserWidget::StaticClass();
		UWidgetBlueprint* WBP = Cast<UWidgetBlueprint>(Factory->FactoryCreateNew(UWidgetBlueprint::StaticClass(), Package, FName(*AssetName),
			RF_Public | RF_Standalone | RF_Transactional, nullptr, GWarn));
		if (!WBP || !WBP->WidgetTree)
		{
			OutError = TEXT("UWidgetBlueprintFactory::FactoryCreateNew returned no widget blueprint");
			return false;
		}
		TStrongObjectPtr<UWidgetBlueprint> KeepWBP(WBP);
		Out.bFactoryRootSet = WBP->WidgetTree->RootWidget != nullptr;
		Out.FactoryRootClass = Out.bFactoryRootSet ? WBP->WidgetTree->RootWidget->GetClass()->GetName() : TEXT("(none)");

		UCanvasPanel* Root = Cast<UCanvasPanel>(WBP->WidgetTree->RootWidget);
		if (!Root)
		{
			// 설계 §12-1 A7 '틀리면' — 루트를 Canvas 로 직접 만든다(팩토리가 루트를 만들 때와 같은 OnVariableAdded)
			Root = WBP->WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), FName(*RootId));
			WBP->WidgetTree->RootWidget = Root;
			WBP->OnVariableAdded(Root->GetFName());
		}
		TMap<FString, UWidget*> ById;
		ById.Add(RootId, Root);

		// ---- A6: ConstructWidget + OnVariableAdded ------------------------------------------------------------
		TStrongObjectPtr<UTexture2D> Checker(MakeChecker(64));
		TSharedRef<FJsonObject> TextureReport = AnimMcpJson::MakeObject();
		if (Checker.IsValid())
		{
			TextureReport->SetStringField(TEXT("compression"), TEXT("TC_EditorIcon"));
			TextureReport->SetNumberField(TEXT("compression_value"), static_cast<int32>(Checker->CompressionSettings.GetValue()));
			TextureReport->SetNumberField(TEXT("lod_group"), static_cast<int32>(Checker->LODGroup.GetValue()));
			TextureReport->SetBoolField(TEXT("never_stream"), Checker->NeverStream != 0);
			TextureReport->SetBoolField(TEXT("srgb"), Checker->SRGB != 0);
			TextureReport->SetStringField(TEXT("source"), TEXT("UTexture2D::CreateTransient (import path not exercised)"));
		}
		Report->SetObjectField(TEXT("texture"), TextureReport);

		for (const FSpecWidget& S : Widgets)
		{
			if (S.Id == RootId)
			{
				continue;
			}
			UClass* Class = nullptr;
			if (S.Type == TEXT("Border")) { Class = UBorder::StaticClass(); }
			else if (S.Type == TEXT("Image")) { Class = UImage::StaticClass(); }
			else if (S.Type == TEXT("TextBlock")) { Class = UTextBlock::StaticClass(); }
			else if (S.Type == TEXT("ProgressBar")) { Class = UProgressBar::StaticClass(); }
			else if (S.Type == TEXT("CanvasPanel")) { Class = UCanvasPanel::StaticClass(); }
			if (!Class)
			{
				OutError = FString::Printf(TEXT("unsupported spike widget type '%s'"), *S.Type);
				return false;
			}
			UWidget* W = WBP->WidgetTree->ConstructWidget<UWidget>(Class, FName(*S.Id));
			W->bIsVariable = true;
			WBP->OnVariableAdded(W->GetFName());

			UWidget* const* ParentPtr = ById.Find(S.Parent.IsEmpty() ? RootId : S.Parent);
			if (!ParentPtr)
			{
				OutError = FString::Printf(TEXT("'%s': parent '%s' must come earlier in widgets[]"), *S.Id, *S.Parent);
				return false;
			}
			if (UCanvasPanel* ParentCanvas = Cast<UCanvasPanel>(*ParentPtr))
			{
				UCanvasPanelSlot* Slot = ParentCanvas->AddChildToCanvas(W);
				Slot->SetAnchors(FAnchors(S.Anchors.X, S.Anchors.Y, S.Anchors.Z, S.Anchors.W));
				Slot->SetAlignment(S.Alignment);
				Slot->SetPosition(S.Position);
				Slot->SetSize(S.Size);
				Slot->SetAutoSize(false);
			}
			else if (UBorder* ParentBorder = Cast<UBorder>(*ParentPtr))
			{
				ParentBorder->SetContent(W);
			}
			else
			{
				OutError = FString::Printf(TEXT("'%s': parent '%s' is neither a CanvasPanel nor a Border"), *S.Id, *S.Parent);
				return false;
			}

			if (UBorder* Border = Cast<UBorder>(W))
			{
				Border->SetBrushColor(ReadColor(S.Json, TEXT("color"), FLinearColor(0.1f, 0.1f, 0.1f)));
			}
			else if (UImage* Image = Cast<UImage>(W))
			{
				if (Checker.IsValid()) { Image->SetBrushFromTexture(Checker.Get()); }
			}
			else if (UTextBlock* Text = Cast<UTextBlock>(W))
			{
				FString Value;
				S.Json->TryGetStringField(TEXT("text"), Value);
				Text->SetText(FText::FromString(Value));
				FSlateFontInfo Font = Text->GetFont();
				double FontSize = 18.0;
				S.Json->TryGetNumberField(TEXT("size"), FontSize);
				Font.Size = static_cast<float>(FontSize);
				Text->SetFont(Font);
				Text->SetColorAndOpacity(FSlateColor(ReadColor(S.Json, TEXT("color"), FLinearColor::White)));
			}
			else if (UProgressBar* Bar = Cast<UProgressBar>(W))
			{
				double Percent = 0.5;
				S.Json->TryGetNumberField(TEXT("percent"), Percent);
				Bar->SetPercent(static_cast<float>(Percent));
				Bar->SetFillColorAndOpacity(ReadColor(S.Json, TEXT("fill"), FLinearColor(0.8f, 0.6f, 0.2f)));
			}
			ById.Add(S.Id, W);
		}

		// ---- 컴파일 · GUID 맵 -----------------------------------------------------------------------------------
		FCompilerResultsLog Log;
		Log.bSilentMode = true;
		FKismetEditorUtilities::CompileBlueprint(WBP, EBlueprintCompileOptions::SkipGarbageCollection, &Log);
		Out.CompileErrors = Log.NumErrors;
		Out.CompileWarnings = Log.NumWarnings;
		Out.bCompiled = WBP->GeneratedClass != nullptr && (WBP->Status == BS_UpToDate || WBP->Status == BS_UpToDateWithWarnings);
		TArray<TSharedPtr<FJsonValue>> Messages;
		for (const TSharedRef<FTokenizedMessage>& M : Log.Messages) { Messages.Add(MakeShared<FJsonValueString>(M->ToText().ToString())); }
		for (const TPair<FString, UWidget*>& Pair : ById)
		{
			if (!WBP->WidgetVariableNameToGuidMap.Contains(Pair.Value->GetFName()))
			{
				Out.MissingGuids.Add(Pair.Key);
			}
		}
		Out.GuidMapCount = WBP->WidgetVariableNameToGuidMap.Num();
		if (!Out.bCompiled)
		{
			OutError = FString::Printf(TEXT("compile failed: %d error(s)"), Out.CompileErrors);
		}

		// ---- 렌더 3회 ---------------------------------------------------------------------------------------------
		IFileManager::Get().MakeDirectory(*OutputDir, /*Tree*/ true);
		TArray<TSharedPtr<FJsonValue>> GeometryJson;
		if (Out.bCompiled)
		{
			UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
			TStrongObjectPtr<UUserWidget> Instance(NewObject<UUserWidget>(World ? static_cast<UObject*>(World) : GetTransientPackage(), WBP->GeneratedClass, NAME_None, RF_Transient));
			Instance->Initialize();
			TSharedRef<SWidget> Slate = Instance->TakeWidget();

			const int32 W = FMath::RoundToInt32(Canvas.X);
			const int32 H = FMath::RoundToInt32(Canvas.Y);
			FWidgetRenderer* Renderer = new FWidgetRenderer(/*bUseGammaCorrection*/ true, /*bInClearTarget*/ true);
			TStrongObjectPtr<UTextureRenderTarget2D> Target(FWidgetRenderer::CreateTargetFor(Canvas, TF_Bilinear, /*bUseGammaCorrection*/ true));
			TArray<FColor> Prev;
			for (int32 Draw = 1; Draw <= 3; ++Draw)
			{
				Renderer->DrawWidget(Target.Get(), Slate, /*Scale*/ 1.0f, Canvas, /*DeltaTime*/ 0.1f);
				FlushRenderingCommands();
				TArray<FColor> Pixels;
				FTextureRenderTargetResource* Resource = Target->GameThread_GetRenderTargetResource();
				if (!Resource || !Resource->ReadPixels(Pixels) || Pixels.Num() != W * H)
				{
					OutError = FString::Printf(TEXT("ReadPixels failed on draw %d"), Draw);
					break;
				}
				if (Draw > 1)
				{
					int32 Diff = 0;
					for (int32 i = 0; i < Pixels.Num(); ++i) { Diff += Pixels[i] != Prev[i] ? 1 : 0; }
					Out.DiffPixelsVsPrev.Add(Diff);
				}
				const FString Png = FPaths::Combine(OutputDir, FString::Printf(TEXT("draw_%d.png"), Draw));
				if (SavePng(Png, Pixels, W, H)) { Out.Pngs.Add(Png); }

				// geometry · 글자 잉크 — 이 그림 직후의 페인트 공간 geometry
				double MaxErr = 0.0;
				GeometryJson.Reset();
				for (const FSpecWidget& S : Widgets)
				{
					UWidget* Live = S.Id == RootId ? Instance->GetRootWidget() : Instance->GetWidgetFromName(FName(*S.Id));
					if (!Live)
					{
						continue;
					}
					const FGeometry& G = Live->GetPaintSpaceGeometry();
					const FVector2D Pos(G.GetAbsolutePosition());
					const FVector2D Size(G.GetAbsoluteSize());
					TSharedRef<FJsonObject> GJ = AnimMcpJson::MakeObject();
					GJ->SetStringField(TEXT("id"), S.Id);
					GJ->SetArrayField(TEXT("pos"), Vec2Json(Pos));
					GJ->SetArrayField(TEXT("size"), Vec2Json(Size));
					const bool bRootCanvasChild = S.bCanvasSlot && (S.Parent.IsEmpty() || S.Parent == RootId) && S.Anchors.X == S.Anchors.Z && S.Anchors.Y == S.Anchors.W;
					if (bRootCanvasChild)
					{
						const FVector2D Expected = FVector2D(S.Anchors.X * Canvas.X, S.Anchors.Y * Canvas.Y) + S.Position - S.Alignment * S.Size;
						const double Err = FMath::Max(FMath::Max(FMath::Abs(Pos.X - Expected.X), FMath::Abs(Pos.Y - Expected.Y)),
							FMath::Max(FMath::Abs(Size.X - S.Size.X), FMath::Abs(Size.Y - S.Size.Y)));
						MaxErr = FMath::Max(MaxErr, Err);
						GJ->SetArrayField(TEXT("expected_pos"), Vec2Json(Expected));
						GJ->SetArrayField(TEXT("expected_size"), Vec2Json(S.Size));
						GJ->SetNumberField(TEXT("error_px"), FMath::RoundToDouble(Err * 100.0) / 100.0);
					}
					if (S.Type == TEXT("TextBlock"))
					{
						const int32 X0 = FMath::Clamp(FMath::FloorToInt32(Pos.X), 0, W), Y0 = FMath::Clamp(FMath::FloorToInt32(Pos.Y), 0, H);
						const int32 X1 = FMath::Clamp(FMath::CeilToInt32(Pos.X + Size.X), 0, W), Y1 = FMath::Clamp(FMath::CeilToInt32(Pos.Y + Size.Y), 0, H);
						int32 Ink = 0;
						for (int32 Y = Y0; Y < Y1; ++Y)
						{
							for (int32 X = X0; X < X1; ++X)
							{
								const FColor& C = Pixels[Y * W + X];
								Ink += FMath::Max3(C.R, C.G, C.B) >= 160 ? 1 : 0;
							}
						}
						Out.TextInk.FindOrAdd(S.Id).Add(Ink);
						GJ->SetNumberField(TEXT("ink_px"), Ink);
					}
					GeometryJson.Add(MakeShared<FJsonValueObject>(GJ));
				}
				Out.MaxGeometryErrorPx = MaxErr;
				Prev = MoveTemp(Pixels);
			}
			BeginCleanup(Renderer);

			// 색 탐침 — FWidgetRenderer 감마 조합 두 가지(위 3회 = gamma true)를 같은 픽셀에서 비교 (spec.color_probes[{id, at[x,y], expect "#RRGGBB"}])
			TArray<FColor> LinearPixels;
			FString FormatTrue, FormatFalse;
			{
				TArray<FColor> Ignored;
				DrawOnce(Slate, Canvas, /*bGamma*/ true, Ignored, FormatTrue);
			}
			const bool bLinearOk = DrawOnce(Slate, Canvas, /*bGamma*/ false, LinearPixels, FormatFalse) && LinearPixels.Num() == W * H;
			if (bLinearOk)
			{
				SavePng(FPaths::Combine(OutputDir, TEXT("draw_gamma_false.png")), LinearPixels, W, H);
			}
			TArray<TSharedPtr<FJsonValue>> Probes;
			const TArray<TSharedPtr<FJsonValue>>* ProbeArr = nullptr;
			if (Spec->TryGetArrayField(TEXT("color_probes"), ProbeArr) && Prev.Num() == W * H)
			{
				for (const TSharedPtr<FJsonValue>& PV : *ProbeArr)
				{
					const TSharedPtr<FJsonObject> P = PV->AsObject();
					const FVector2D At = ReadVec2(P, TEXT("at"), FVector2D::ZeroVector);
					const int32 X = FMath::Clamp(FMath::RoundToInt32(At.X), 0, W - 1), Y = FMath::Clamp(FMath::RoundToInt32(At.Y), 0, H - 1);
					TSharedRef<FJsonObject> PJ = AnimMcpJson::MakeObject();
					FString Id, Expect;
					P->TryGetStringField(TEXT("id"), Id);
					P->TryGetStringField(TEXT("expect"), Expect);
					PJ->SetStringField(TEXT("id"), Id);
					PJ->SetArrayField(TEXT("at"), Vec2Json(FVector2D(X, Y)));
					PJ->SetStringField(TEXT("expect"), Expect);
					PJ->SetStringField(TEXT("gamma_true"), Hex(Prev[Y * W + X]));
					PJ->SetStringField(TEXT("gamma_false"), bLinearOk ? Hex(LinearPixels[Y * W + X]) : TEXT("(failed)"));
					Probes.Add(MakeShared<FJsonValueObject>(PJ));
				}
			}
			Report->SetArrayField(TEXT("color_probes"), Probes);
			Report->SetStringField(TEXT("render_target_gamma_true"), FormatTrue);
			Report->SetStringField(TEXT("render_target_gamma_false"), FormatFalse);
		}

		// ---- 보고 --------------------------------------------------------------------------------------------------
		TSharedRef<FJsonObject> A7 = AnimMcpJson::MakeObject();
		A7->SetBoolField(TEXT("factory_root_set"), Out.bFactoryRootSet);
		A7->SetStringField(TEXT("factory_root_class"), Out.FactoryRootClass);
		A7->SetBoolField(TEXT("umg_use_widget_template_selector"), Out.bUseWidgetTemplateSelector);
		A7->SetStringField(TEXT("umg_default_root_widget"), Out.DefaultRootWidget);
		Report->SetObjectField(TEXT("a7"), A7);
		TSharedRef<FJsonObject> Compile = AnimMcpJson::MakeObject();
		Compile->SetBoolField(TEXT("ok"), Out.bCompiled);
		Compile->SetNumberField(TEXT("errors"), Out.CompileErrors);
		Compile->SetNumberField(TEXT("warnings"), Out.CompileWarnings);
		Compile->SetArrayField(TEXT("messages"), Messages);
		Compile->SetNumberField(TEXT("guid_map_count"), Out.GuidMapCount);
		TArray<TSharedPtr<FJsonValue>> Missing;
		for (const FString& M : Out.MissingGuids) { Missing.Add(MakeShared<FJsonValueString>(M)); }
		Compile->SetArrayField(TEXT("guid_missing"), Missing);
		Report->SetObjectField(TEXT("compile"), Compile);
		TArray<TSharedPtr<FJsonValue>> Pngs, Diffs;
		for (const FString& P : Out.Pngs) { Pngs.Add(MakeShared<FJsonValueString>(P)); }
		for (int32 D : Out.DiffPixelsVsPrev) { Diffs.Add(MakeShared<FJsonValueNumber>(D)); }
		TSharedRef<FJsonObject> Render = AnimMcpJson::MakeObject();
		Render->SetArrayField(TEXT("pngs"), Pngs);
		Render->SetArrayField(TEXT("diff_pixels_vs_prev"), Diffs);
		Render->SetNumberField(TEXT("max_geometry_error_px"), FMath::RoundToDouble(Out.MaxGeometryErrorPx * 100.0) / 100.0);
		Render->SetArrayField(TEXT("geometry_last_draw"), GeometryJson);
		TSharedRef<FJsonObject> Ink = AnimMcpJson::MakeObject();
		for (const TPair<FString, TArray<int32>>& Pair : Out.TextInk)
		{
			TArray<TSharedPtr<FJsonValue>> Per;
			for (int32 V : Pair.Value) { Per.Add(MakeShared<FJsonValueNumber>(V)); }
			Ink->SetArrayField(Pair.Key, Per);
		}
		Render->SetObjectField(TEXT("text_ink_per_draw"), Ink);
		Render->SetArrayField(TEXT("canvas"), Vec2Json(Canvas));
		Report->SetObjectField(TEXT("render"), Render);
		Report->SetStringField(TEXT("asset_path"), PackagePath);
		Report->SetBoolField(TEXT("asset_saved"), false);
		Report->SetNumberField(TEXT("seconds"), FPlatformTime::Seconds() - Start);
		if (!OutError.IsEmpty())
		{
			Report->SetStringField(TEXT("error"), OutError);
		}

		Out.ReportPath = FPaths::Combine(OutputDir, TEXT("report.json"));
		FFileHelper::SaveStringToFile(AnimMcpJson::ToString(Report, /*bPretty*/ true), *Out.ReportPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
		UE_LOG(LogAnimGraphMcp, Display, TEXT("WidgetMcp spike: root_by_factory=%s compiled=%s draws=%d geom_err=%.2f -> %s"),
			Out.bFactoryRootSet ? TEXT("yes") : TEXT("no"), Out.bCompiled ? TEXT("yes") : TEXT("no"), Out.Pngs.Num(), Out.MaxGeometryErrorPx, *Out.ReportPath);
		return OutError.IsEmpty();
	}
}
