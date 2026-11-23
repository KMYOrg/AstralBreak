#include "Core/WidgetMcpRender.h"

#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetTree.h"
#include "Components/Image.h"
#include "Components/PanelWidget.h"
#include "Components/ProgressBar.h"
#include "Components/TextBlock.h"
#include "Core/WidgetMcpBrushMaterials.h"
#include "Core/WidgetMcpSpec.h"
#include "Editor.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/UserInterfaceSettings.h"
#include "Fonts/FontCache.h"
#include "Framework/Application/SlateApplication.h"
#include "HAL/PlatformProcess.h"
#include "Rendering/SlateRenderer.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "ImageCore.h"
#include "ImageUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "RenderingThread.h"
#include "ShaderCompiler.h"
#include "Slate/WidgetRenderer.h"
#include "TextureResource.h"
#include "UObject/StrongObjectPtr.h"
#include "WidgetBlueprint.h"

namespace WidgetMcpRender
{
	namespace RenderPrivate
	{
		/** sRGB 8비트 → 선형 8비트 — A6-색 보정(읽은 값에 채널마다 1회) */
		const TArray<uint8>& SrgbToLinearLut()
		{
			static TArray<uint8> Lut;
			if (Lut.Num() == 0)
			{
				Lut.SetNum(256);
				for (int32 i = 0; i < 256; ++i)
				{
					const double C = i / 255.0;
					const double L = C <= 0.04045 ? C / 12.92 : FMath::Pow((C + 0.055) / 1.055, 2.4);
					Lut[i] = static_cast<uint8>(FMath::Clamp(FMath::RoundToInt(L * 255.0), 0, 255));
				}
			}
			return Lut;
		}

		bool IsEffectivelyVisible(const UWidget* W)
		{
			for (const UWidget* It = W; It; It = It->GetParent())
			{
				const ESlateVisibility V = It->GetVisibility();
				if (V == ESlateVisibility::Collapsed || V == ESlateVisibility::Hidden)
				{
					return false;
				}
			}
			return true;
		}

		FString Hex(const FColor& C)
		{
			return FString::Printf(TEXT("#%02X%02X%02X"), C.R, C.G, C.B);
		}
	}

	TSharedPtr<FJsonObject> Render(const WidgetMcp::FSettings& Settings, UWidgetBlueprint* WBP, const FRequest& Request, FEditorMcpContext& Context, FEditorMcpError& OutError)
	{
		using namespace RenderPrivate;
		const double Start = FPlatformTime::Seconds();
		FString Dir;
		if (!WidgetMcp::CheckDiskPath(Settings.RenderRoots, Request.OutputDir, TEXT("output_dir"), TEXT("WidgetRenderOutputRoots"), Dir, OutError))
		{
			return nullptr;
		}
		TArray<FString> Existing;
		IFileManager::Get().FindFiles(Existing, *FPaths::Combine(Dir, TEXT("*")), true, true);
		if (Existing.Num() > 0)
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("output_dir '%s' is not empty — every render goes into a new folder"), *Dir), TEXT("OUTPUT_DIR_NOT_EMPTY"));
			return nullptr;
		}
		if (!WBP->GeneratedClass || !(WBP->Status == BS_UpToDate || WBP->Status == BS_UpToDateWithWarnings))
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::CompileFailed, FString::Printf(TEXT("'%s' is not compiled cleanly — compile_widget_blueprint first"), *WBP->GetPathName()), TEXT("NOT_COMPILED"));
			return nullptr;
		}
		if (Request.Resolutions.Num() == 0 || Request.Draws < 1 || Request.Scale <= 0.f)
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, TEXT("resolutions[] must be non-empty, draws >= 1, scale > 0"));
			return nullptr;
		}
		for (const FIntPoint& R : Request.Resolutions)
		{
			if (R.X < 16 || R.Y < 16 || R.X > 8192 || R.Y > 8192)
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("resolution %dx%d is outside 16..8192"), R.X, R.Y));
				return nullptr;
			}
		}
		IFileManager::Get().MakeDirectory(*Dir, /*Tree*/ true);

		const WidgetMcp::FWriteGuard Guard;
		UWorld* World = GEditor ? GEditor->GetEditorWorldContext().World() : nullptr;
		TStrongObjectPtr<UUserWidget> Instance(NewObject<UUserWidget>(World ? static_cast<UObject*>(World) : GetTransientPackage(), WBP->GeneratedClass, NAME_None, RF_Transient));
		Instance->Initialize();
		UWidgetTree* Tree = Instance->WidgetTree;
		if (!Tree)
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::Internal, TEXT("widget instance has no widget tree"));
			return nullptr;
		}
		if (Request.bForceVisible)
		{
			Tree->ForEachWidget([](UWidget* W)
			{
				const ESlateVisibility V = W->GetVisibility();
				if (V == ESlateVisibility::Collapsed || V == ESlateVisibility::Hidden)
				{
					W->SetVisibility(ESlateVisibility::HitTestInvisible);
				}
			});
		}
		for (const TPair<FString, FOverride>& P : Request.Overrides)
		{
			UWidget* W = Instance->GetWidgetFromName(FName(*P.Key));
			if (!W)
			{
				Context.AddDiagnostic(TEXT("warning"), TEXT("OVERRIDE_NOT_FOUND"), FString::Printf(TEXT("override '%s' names no widget"), *P.Key));
				continue;
			}
			if (P.Value.bVisible.IsSet()) { W->SetVisibility(P.Value.bVisible.GetValue() ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed); }
			if (P.Value.Percent.IsSet())
			{
				if (UProgressBar* Bar = Cast<UProgressBar>(W)) { Bar->SetPercent(P.Value.Percent.GetValue()); }
				else if (UImage* Image = Cast<UImage>(W))
				{
					// 원형 닦기(전투 HUD 동작) — 게임과 같은 길(동적 머티리얼의 Percent). 인스턴스의 것이라 애셋은 그대로다
					WidgetMcpBrushMaterials::FRadialWipe Wipe;
					UMaterialInstanceDynamic* Dynamic = WidgetMcpBrushMaterials::ReadRadialWipe(Image->GetBrush().GetResourceObject(), Wipe) ? Image->GetDynamicMaterial() : nullptr;
					if (Dynamic) { Dynamic->SetScalarParameterValue(WidgetMcpBrushMaterials::PercentParameter(), FMath::Clamp(P.Value.Percent.GetValue(), 0.f, 1.f)); }
					else { Context.AddDiagnostic(TEXT("warning"), TEXT("OVERRIDE_NOT_APPLIED"), FString::Printf(TEXT("override '%s'.percent — the image has no radial wipe"), *P.Key)); }
				}
			}
			if (P.Value.Text.IsSet()) { if (UTextBlock* Text = Cast<UTextBlock>(W)) { Text->SetText(FText::FromString(P.Value.Text.GetValue())); } }
		}
		TSharedRef<SWidget> Slate = Instance->TakeWidget();
		const TArray<uint8>& Lut = SrgbToLinearLut();
		// 폰트 · 브러시 머티리얼(1b 후속 D — 글자 그라데이션 MIC)의 셰이더가 컴파일 중이면 Slate 는 그 배치를 그리지 않는다 [실측 D] — 기다린다
		if (GShaderCompilingManager)
		{
			GShaderCompilingManager->FinishAllCompilation();
		}
		// 1b 후속 F — 거리장(SDF) 글꼴은 글리프를 작업 스레드에서 만들고 처음엔 자리표시 그림을 쓴다(FontCache.cpp:1470 SpawnWithPlaceholder,
		// 다 되면 UpdateCache 가 바꿔 넣음 — 1872). 에디터 틱이 안 도는 이 함수 안에서는 한 번 미리 그려 요청을 넣고, 잠깐씩 쉬며 UpdateCache 를 돌린다
		double SdfWarmup = 0.0;
		if (IsSlateSdfTextFeatureEnabled() && GetDefault<UUserInterfaceSettings>()->bEnableDistanceFieldFontRasterization && FSlateApplication::IsInitialized())
		{
			const double W0 = FPlatformTime::Seconds();
			const FVector2D WarmSize(Request.Resolutions[0].X, Request.Resolutions[0].Y);
			FWidgetRenderer* Warm = new FWidgetRenderer(/*bUseGammaCorrection*/ true, /*bInClearTarget*/ true);
			TStrongObjectPtr<UTextureRenderTarget2D> WarmTarget(FWidgetRenderer::CreateTargetFor(WarmSize, TF_Bilinear, /*bUseGammaCorrection*/ true));
			Warm->DrawWidget(WarmTarget.Get(), Slate, Request.Scale, WarmSize, 0.0f);
			FlushRenderingCommands();
			const TSharedRef<FSlateFontCache> FontCache = FSlateApplication::Get().GetRenderer()->GetFontCache();
			for (int32 i = 0; i < 40; ++i)
			{
				FPlatformProcess::Sleep(0.05f);
				FontCache->UpdateCache();
			}
			BeginCleanup(Warm);
			SdfWarmup = FPlatformTime::Seconds() - W0;
		}

		TArray<TSharedPtr<FJsonValue>> Renders;
		TArray<TSharedPtr<FJsonValue>> ProbeResults;
		for (int32 r = 0; r < Request.Resolutions.Num(); ++r)
		{
			const FIntPoint Res = Request.Resolutions[r];
			const FVector2D DrawSize(Res.X, Res.Y);
			FWidgetRenderer* Renderer = new FWidgetRenderer(/*bUseGammaCorrection*/ true, /*bInClearTarget*/ true);
			TStrongObjectPtr<UTextureRenderTarget2D> Target(FWidgetRenderer::CreateTargetFor(DrawSize, TF_Bilinear, /*bUseGammaCorrection*/ true));
			TArray<FColor> Prev, Pixels;
			TArray<TSharedPtr<FJsonValue>> Diffs;
			bool bRead = true;
			for (int32 d = 0; d < Request.Draws; ++d)
			{
				Renderer->DrawWidget(Target.Get(), Slate, Request.Scale, DrawSize, 0.0f);
				FlushRenderingCommands();
				Pixels.Reset();
				FTextureRenderTargetResource* Resource = Target->GameThread_GetRenderTargetResource();
				if (!Resource || !Resource->ReadPixels(Pixels) || Pixels.Num() != Res.X * Res.Y)
				{
					bRead = false;
					break;
				}
				if (d > 0)
				{
					int32 Diff = 0;
					for (int32 i = 0; i < Pixels.Num(); ++i) { Diff += Pixels[i] != Prev[i] ? 1 : 0; }
					Diffs.Add(MakeShared<FJsonValueNumber>(Diff));
				}
				Prev = Pixels;
			}
			BeginCleanup(Renderer);
			if (!bRead)
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::CaptureFailed, FString::Printf(TEXT("ReadPixels failed at %dx%d"), Res.X, Res.Y), TEXT("READBACK"));
				return nullptr;
			}
			for (FColor& C : Pixels)
			{
				C.R = Lut[C.R];
				C.G = Lut[C.G];
				C.B = Lut[C.B];
				C.A = 255;
			}
			const FString Png = FPaths::Combine(Dir, FString::Printf(TEXT("%s_%dx%d.png"), *Request.Prefix, Res.X, Res.Y));
			const FImageView View(Pixels.GetData(), Res.X, Res.Y, EGammaSpace::sRGB);
			if (!FImageUtils::SaveImageByExtension(*Png, View) || !IFileManager::Get().FileExists(*Png))
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::CaptureFailed, FString::Printf(TEXT("could not write '%s'"), *Png), TEXT("WRITE_FAILED"));
				return nullptr;
			}

			// geometry — 마지막 그림 직후의 페인트 공간(= 픽셀, Scale 반영)
			TArray<TSharedPtr<FJsonValue>> Geometry;
			Tree->ForEachWidget([&Geometry](UWidget* W)
			{
				const FGeometry& G = W->GetPaintSpaceGeometry();
				const FVector2D Pos(G.GetAbsolutePosition());
				const FVector2D Size(G.GetAbsoluteSize());
				TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
				J->SetStringField(TEXT("id"), W->GetName());
				J->SetStringField(TEXT("type"), WidgetMcpSpec::TypeForWidget(W).IsEmpty() ? W->GetClass()->GetName() : WidgetMcpSpec::TypeForWidget(W));
				J->SetStringField(TEXT("parent"), W->GetParent() ? W->GetParent()->GetName() : FString());
				J->SetField(TEXT("x"), WidgetMcp::Num(Pos.X));
				J->SetField(TEXT("y"), WidgetMcp::Num(Pos.Y));
				J->SetField(TEXT("w"), WidgetMcp::Num(Size.X));
				J->SetField(TEXT("h"), WidgetMcp::Num(Size.Y));
				J->SetBoolField(TEXT("visible"), IsEffectivelyVisible(W));
				Geometry.Add(MakeShared<FJsonValueObject>(J));
			});
			if (r == 0)
			{
				for (const TPair<FString, FIntPoint>& Probe : Request.Probes)
				{
					const int32 X = FMath::Clamp(Probe.Value.X, 0, Res.X - 1);
					const int32 Y = FMath::Clamp(Probe.Value.Y, 0, Res.Y - 1);
					TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
					J->SetStringField(TEXT("id"), Probe.Key);
					J->SetArrayField(TEXT("at"), { MakeShared<FJsonValueNumber>(X), MakeShared<FJsonValueNumber>(Y) });
					J->SetStringField(TEXT("color"), Hex(Pixels[Y * Res.X + X]));
					ProbeResults.Add(MakeShared<FJsonValueObject>(J));
				}
			}
			TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
			Item->SetArrayField(TEXT("resolution"), { MakeShared<FJsonValueNumber>(Res.X), MakeShared<FJsonValueNumber>(Res.Y) });
			Item->SetStringField(TEXT("png"), Png);
			Item->SetNumberField(TEXT("draws"), Request.Draws);
			Item->SetArrayField(TEXT("diff_pixels_vs_prev"), Diffs);
			Item->SetArrayField(TEXT("geometry"), Geometry);
			Renders.Add(MakeShared<FJsonValueObject>(Item));
		}

		TArray<FString> NewlyDirty;
		if (!Guard.Finish(Settings, OutError, NewlyDirty))
		{
			return nullptr;
		}
		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetStringField(TEXT("asset_path"), WBP->GetPathName());
		Out->SetStringField(TEXT("output_dir"), Dir);
		Out->SetArrayField(TEXT("renders"), Renders);
		Out->SetArrayField(TEXT("probes"), ProbeResults);
		Out->SetStringField(TEXT("color_correction"), TEXT("gamma=true render, then sRGB->linear per 8-bit channel (design 12-1 A6)"));
		Out->SetNumberField(TEXT("scale"), Request.Scale);
		Out->SetBoolField(TEXT("force_visible"), Request.bForceVisible);
		Out->SetNumberField(TEXT("sdf_warmup_seconds"), WidgetMcp::Round3(SdfWarmup));
		Out->SetNumberField(TEXT("seconds"), WidgetMcp::Round3(FPlatformTime::Seconds() - Start));
		return Out;
	}
}
