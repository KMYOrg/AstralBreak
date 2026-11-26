#include "Core/WidgetMcpTextMaterials.h"

#include "AssetCompilingManager.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Materials/Material.h"
#include "Materials/MaterialExpressionComponentMask.h"
#include "Materials/MaterialExpressionDivide.h"
#include "Materials/MaterialExpressionFontSignedDistance.h"
#include "Materials/MaterialExpressionLinearInterpolate.h"
#include "Materials/MaterialExpressionMultiply.h"
#include "Materials/MaterialExpressionPower.h"
#include "Materials/MaterialExpressionSaturate.h"
#include "Materials/MaterialExpressionScalarParameter.h"
#include "Materials/MaterialExpressionSubtract.h"
#include "Materials/MaterialExpressionTextureCoordinate.h"
#include "Materials/MaterialExpressionVectorParameter.h"
#include "Materials/MaterialInstanceConstant.h"
#include "MaterialShared.h"
#include "RHI.h"
#include "ShaderCompiler.h"
#include "UObject/Package.h"

namespace WidgetMcpTextMaterials
{
	namespace TextMaterialsPrivate
	{
		const TCHAR* const ParentName = TEXT("M_TextGradient");
		const TCHAR* const InstancePrefix = TEXT("MI_TextGradient_");
		const FName TopParam(TEXT("TopColor"));
		const FName BottomParam(TEXT("BottomColor"));
		const FName VTopParam(TEXT("VTop"));
		const FName VBottomParam(TEXT("VBottom"));
		const TCHAR* const GlowParentName = TEXT("M_TextGlow");
		const TCHAR* const GlowInstancePrefix = TEXT("MI_TextGlow_");
		const FName GlowColorParam(TEXT("GlowColor"));
		const FName GlowAlphaParam(TEXT("GlowAlpha"));
		const FName OutlineEmParam(TEXT("OutlineEm"));
		const FName GammaParam(TEXT("Gamma"));
		/** 빛 감쇠 지수 — [실측 F] 컨셉 '4.2' 둘레 밝기가 획에서 3 px 쯤 가장 밝고 8 px 에서 거의 0 (잠정) */
		constexpr float DefaultGamma = 1.5f;

		/** [실측 D] Slate 는 셰이더를 못 찾은 머티리얼 배치를 건너뛴다(SlateRHIRenderingPolicy.cpp:1094-1112 — 외곽선만 보임) — 끝까지 기다리고 오류를 알린다 */
		bool CompileAndWait(UMaterial* Parent, FString& OutError)
		{
			Parent->ForceRecompileForRendering();
			FAssetCompilingManager::Get().FinishAllCompilation();
			if (GShaderCompilingManager)
			{
				GShaderCompilingManager->FinishAllCompilation();
			}
			if (const FMaterialResource* Resource = Parent->GetMaterialResource(GMaxRHIShaderPlatform))
			{
				if (Resource->GetCompileErrors().Num() > 0)
				{
					OutError = FString::Printf(TEXT("%s failed to compile: %s"), *Parent->GetPathName(), *Resource->GetCompileErrors()[0]);
					return false;
				}
			}
			return true;
		}

		template <typename T>
		T* FindInFolder(const FString& Folder, const FString& Name)
		{
			const FString ObjectPath = Folder / Name + TEXT(".") + Name;
			if (T* Found = FindObject<T>(nullptr, *ObjectPath))
			{
				return Found;
			}
			return LoadObject<T>(nullptr, *ObjectPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
		}

		template <typename T>
		T* AddExpression(UMaterial* M, int32 X, int32 Y)
		{
			T* E = NewObject<T>(M);
			E->Material = M;
			E->MaterialExpressionEditorX = X;
			E->MaterialExpressionEditorY = Y;
			M->GetExpressionCollection().AddExpression(E);
			return E;
		}

		/** UI 도메인 · 반투명 — Final Color = Lerp(TopColor, BottomColor, TexCoord0.y). 불투명도는 연결하지 않는다(1 — 글자 알파 · 틴트 알파가 곱해진다) */
		UMaterial* FindOrCreateParent(const FString& Folder, bool& bOutCreated, FString& OutError)
		{
			bOutCreated = false;
			if (UMaterial* M = FindInFolder<UMaterial>(Folder, ParentName))
			{
				return M;
			}
			UPackage* Pkg = CreatePackage(*(Folder / ParentName));
			if (!Pkg)
			{
				OutError = FString::Printf(TEXT("could not create package %s/%s"), *Folder, ParentName);
				return nullptr;
			}
			UMaterial* M = NewObject<UMaterial>(Pkg, ParentName, RF_Public | RF_Standalone | RF_Transactional);
			M->MaterialDomain = MD_UI;
			M->BlendMode = BLEND_Translucent;
			UMaterialExpressionTextureCoordinate* UV = AddExpression<UMaterialExpressionTextureCoordinate>(M, -900, 0);
			UV->CoordinateIndex = 0;
			UMaterialExpressionComponentMask* LineV = AddExpression<UMaterialExpressionComponentMask>(M, -1100, 0);
			LineV->R = 0; LineV->G = 1; LineV->B = 0; LineV->A = 0;
			UV->ConnectExpression(&LineV->Input, 0);
			// V 는 줄 상자 기준(위 · 아래 여백 포함) — 글자 몸통이 위 색 → 아래 색을 다 받게 saturate((V − VTop) / (VBottom − VTop))
			// [실측 D] 획 5 ~ 95 % 분위가 줄 상자의 Noto Serif KR 0.29 ~ 0.81 · Pretendard 0.21 ~ 0.79 → 기본 0.25 · 0.80(절충)
			UMaterialExpressionScalarParameter* VTop = AddExpression<UMaterialExpressionScalarParameter>(M, -1100, 160);
			VTop->ParameterName = VTopParam;
			VTop->DefaultValue = 0.25f;
			UMaterialExpressionScalarParameter* VBottom = AddExpression<UMaterialExpressionScalarParameter>(M, -1100, 260);
			VBottom->ParameterName = VBottomParam;
			VBottom->DefaultValue = 0.80f;
			UMaterialExpressionSubtract* FromTop = AddExpression<UMaterialExpressionSubtract>(M, -900, 40);
			LineV->ConnectExpression(&FromTop->A, 0);
			VTop->ConnectExpression(&FromTop->B, 0);
			UMaterialExpressionSubtract* Span = AddExpression<UMaterialExpressionSubtract>(M, -900, 200);
			VBottom->ConnectExpression(&Span->A, 0);
			VTop->ConnectExpression(&Span->B, 0);
			UMaterialExpressionDivide* Ratio = AddExpression<UMaterialExpressionDivide>(M, -800, 100);
			FromTop->ConnectExpression(&Ratio->A, 0);
			Span->ConnectExpression(&Ratio->B, 0);
			UMaterialExpressionSaturate* V = AddExpression<UMaterialExpressionSaturate>(M, -700, 100);
			Ratio->ConnectExpression(&V->Input, 0);
			UMaterialExpressionVectorParameter* Top = AddExpression<UMaterialExpressionVectorParameter>(M, -700, -260);
			Top->ParameterName = TopParam;
			Top->DefaultValue = FLinearColor::White;
			UMaterialExpressionVectorParameter* Bottom = AddExpression<UMaterialExpressionVectorParameter>(M, -700, -120);
			Bottom->ParameterName = BottomParam;
			Bottom->DefaultValue = FLinearColor::Gray;
			UMaterialExpressionLinearInterpolate* Lerp = AddExpression<UMaterialExpressionLinearInterpolate>(M, -400, -150);
			Top->ConnectExpression(&Lerp->A, 0);
			Bottom->ConnectExpression(&Lerp->B, 0);
			V->ConnectExpression(&Lerp->Alpha, 0);
			Lerp->ConnectExpression(&M->GetEditorOnlyData()->EmissiveColor, 0);
			M->PreEditChange(nullptr);
			M->PostEditChange();
			FAssetRegistryModule::AssetCreated(M);
			Pkg->MarkPackageDirty();
			bOutCreated = true;
			return M;
		}
	}

	FString GradientKey(const FString& TopHex, const FString& BottomHex)
	{
		return TopHex.Replace(TEXT("#"), TEXT("")).ToUpper() + TEXT("_") + BottomHex.Replace(TEXT("#"), TEXT("")).ToUpper();
	}

	bool Prepare(const FString& Folder, const TMap<FString, TPair<FLinearColor, FLinearColor>>& Gradients, TMap<FString, UMaterialInterface*>& Out, FString& OutError)
	{
		using namespace TextMaterialsPrivate;
		if (Gradients.Num() == 0)
		{
			return true;
		}
		bool bCreatedAny = false;
		UMaterial* Parent = FindOrCreateParent(Folder, bCreatedAny, OutError);
		if (!Parent)
		{
			return false;
		}
		for (const TPair<FString, TPair<FLinearColor, FLinearColor>>& G : Gradients)
		{
			const FString Name = InstancePrefix + G.Key;
			UMaterialInstanceConstant* MIC = FindInFolder<UMaterialInstanceConstant>(Folder, Name);
			if (!MIC)
			{
				UPackage* Pkg = CreatePackage(*(Folder / Name));
				MIC = NewObject<UMaterialInstanceConstant>(Pkg, *Name, RF_Public | RF_Standalone | RF_Transactional);
				MIC->SetParentEditorOnly(Parent);
				MIC->SetVectorParameterValueEditorOnly(FMaterialParameterInfo(TopParam), G.Value.Key);
				MIC->SetVectorParameterValueEditorOnly(FMaterialParameterInfo(BottomParam), G.Value.Value);
				MIC->PostEditChange();
				FAssetRegistryModule::AssetCreated(MIC);
				Pkg->MarkPackageDirty();
				bCreatedAny = true;
			}
			Out.Add(G.Key, MIC);
		}
		return !bCreatedAny || CompileAndWait(Parent, OutError);
	}

	FString GlowKey(const FString& ColorHex, int32 SizePx, double FontSize)
	{
		return FString::Printf(TEXT("%s_S%d_F%d"), *ColorHex.Replace(TEXT("#"), TEXT("")).ToUpper(), SizePx, FMath::RoundToInt(FontSize * 10.0));
	}

	float OutlineEmFor(int32 SizePx, double FontSize)
	{
		const double Ppem = FMath::Max(1.0, FontSize * 96.0 / 72.0);
		return static_cast<float>(SizePx / Ppem);
	}

	namespace TextMaterialsPrivate
	{
		/** UI 도메인 · 반투명 — Emissive = GlowColor, Opacity = GlowAlpha × saturate(FontSignedDistance.x / OutlineEm)^Gamma */
		UMaterial* FindOrCreateGlowParent(const FString& Folder, bool& bOutCreated, FString& OutError)
		{
			bOutCreated = false;
			if (UMaterial* M = FindInFolder<UMaterial>(Folder, GlowParentName))
			{
				return M;
			}
			UPackage* Pkg = CreatePackage(*(Folder / GlowParentName));
			if (!Pkg)
			{
				OutError = FString::Printf(TEXT("could not create package %s/%s"), *Folder, GlowParentName);
				return nullptr;
			}
			UMaterial* M = NewObject<UMaterial>(Pkg, GlowParentName, RF_Public | RF_Standalone | RF_Transactional);
			M->MaterialDomain = MD_UI;
			M->BlendMode = BLEND_Translucent;
			UMaterialExpressionFontSignedDistance* Sdf = AddExpression<UMaterialExpressionFontSignedDistance>(M, -1300, 200);
			UMaterialExpressionComponentMask* Dist = AddExpression<UMaterialExpressionComponentMask>(M, -1100, 200);
			Dist->R = 1; Dist->G = 0; Dist->B = 0; Dist->A = 0;
			Sdf->ConnectExpression(&Dist->Input, 0);
			UMaterialExpressionScalarParameter* Em = AddExpression<UMaterialExpressionScalarParameter>(M, -1100, 320);
			Em->ParameterName = OutlineEmParam;
			Em->DefaultValue = 0.1f;
			UMaterialExpressionDivide* Ratio = AddExpression<UMaterialExpressionDivide>(M, -900, 240);
			Dist->ConnectExpression(&Ratio->A, 0);
			Em->ConnectExpression(&Ratio->B, 0);
			UMaterialExpressionSaturate* T = AddExpression<UMaterialExpressionSaturate>(M, -750, 240);
			Ratio->ConnectExpression(&T->Input, 0);
			UMaterialExpressionScalarParameter* Gamma = AddExpression<UMaterialExpressionScalarParameter>(M, -750, 360);
			Gamma->ParameterName = GammaParam;
			Gamma->DefaultValue = DefaultGamma;
			UMaterialExpressionPower* Pow = AddExpression<UMaterialExpressionPower>(M, -600, 260);
			T->ConnectExpression(&Pow->Base, 0);
			Gamma->ConnectExpression(&Pow->Exponent, 0);
			UMaterialExpressionScalarParameter* Alpha = AddExpression<UMaterialExpressionScalarParameter>(M, -600, 400);
			Alpha->ParameterName = GlowAlphaParam;
			Alpha->DefaultValue = 0.6f;
			UMaterialExpressionMultiply* Opacity = AddExpression<UMaterialExpressionMultiply>(M, -400, 300);
			Pow->ConnectExpression(&Opacity->A, 0);
			Alpha->ConnectExpression(&Opacity->B, 0);
			UMaterialExpressionVectorParameter* Color = AddExpression<UMaterialExpressionVectorParameter>(M, -400, 0);
			Color->ParameterName = GlowColorParam;
			Color->DefaultValue = FLinearColor::White;
			Color->ConnectExpression(&M->GetEditorOnlyData()->EmissiveColor, 0);
			Opacity->ConnectExpression(&M->GetEditorOnlyData()->Opacity, 0);
			M->PreEditChange(nullptr);
			M->PostEditChange();
			FAssetRegistryModule::AssetCreated(M);
			Pkg->MarkPackageDirty();
			bOutCreated = true;
			return M;
		}
	}

	bool PrepareGlows(const FString& Folder, const TMap<FString, FGlowSpec>& Glows, TMap<FString, UMaterialInterface*>& Out, FString& OutError)
	{
		using namespace TextMaterialsPrivate;
		if (Glows.Num() == 0)
		{
			return true;
		}
		bool bCreatedAny = false;
		UMaterial* Parent = FindOrCreateGlowParent(Folder, bCreatedAny, OutError);
		if (!Parent)
		{
			return false;
		}
		for (const TPair<FString, FGlowSpec>& G : Glows)
		{
			const FString Name = GlowInstancePrefix + G.Key;
			UMaterialInstanceConstant* MIC = FindInFolder<UMaterialInstanceConstant>(Folder, Name);
			if (!MIC)
			{
				UPackage* Pkg = CreatePackage(*(Folder / Name));
				MIC = NewObject<UMaterialInstanceConstant>(Pkg, *Name, RF_Public | RF_Standalone | RF_Transactional);
				MIC->SetParentEditorOnly(Parent);
				FLinearColor Rgb = G.Value.Color;
				Rgb.A = 1.f;
				MIC->SetVectorParameterValueEditorOnly(FMaterialParameterInfo(GlowColorParam), Rgb);
				MIC->SetScalarParameterValueEditorOnly(FMaterialParameterInfo(GlowAlphaParam), G.Value.Color.A);
				MIC->SetScalarParameterValueEditorOnly(FMaterialParameterInfo(OutlineEmParam), G.Value.OutlineEm);
				MIC->PostEditChange();
				FAssetRegistryModule::AssetCreated(MIC);
				Pkg->MarkPackageDirty();
				bCreatedAny = true;
			}
			Out.Add(G.Key, MIC);
		}
		return !bCreatedAny || CompileAndWait(Parent, OutError);
	}

	bool ReadGlow(const UObject* OutlineMaterial, FLinearColor& OutColor)
	{
		using namespace TextMaterialsPrivate;
		const UMaterialInstance* MI = Cast<UMaterialInstance>(OutlineMaterial);
		if (!MI || !MI->Parent || MI->Parent->GetName() != GlowParentName || !MI->GetName().StartsWith(GlowInstancePrefix))
		{
			return false;
		}
		float Alpha = 1.f;
		if (!MI->GetVectorParameterValue(FHashedMaterialParameterInfo(GlowColorParam), OutColor, true)
			|| !MI->GetScalarParameterValue(FHashedMaterialParameterInfo(GlowAlphaParam), Alpha, true))
		{
			return false;
		}
		OutColor.A = Alpha;
		return true;
	}

	TSharedRef<FJsonObject> Describe(const UMaterialInterface* Material)
	{
		TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
		D->SetStringField(TEXT("path"), GetPathNameSafe(Material));
		const UMaterial* Base = Material ? Material->GetMaterial() : nullptr;
		D->SetBoolField(TEXT("ui_domain"), Base && Base->MaterialDomain == MD_UI);
		const FMaterialResource* Resource = Material ? Material->GetMaterialResource(GMaxRHIShaderPlatform) : nullptr;
		D->SetBoolField(TEXT("has_resource"), Resource != nullptr);
		if (Resource)
		{
			D->SetBoolField(TEXT("compiled"), Resource->IsCompilationFinished());
			D->SetBoolField(TEXT("game_thread_shader_map"), Resource->GetGameThreadShaderMap() != nullptr);
			D->SetNumberField(TEXT("compile_errors"), Resource->GetCompileErrors().Num());
			if (Resource->GetCompileErrors().Num()) { D->SetStringField(TEXT("first_error"), Resource->GetCompileErrors()[0]); }
		}
		return D;
	}

	bool ReadGradient(const UObject* FontMaterial, FLinearColor& OutTop, FLinearColor& OutBottom)
	{
		using namespace TextMaterialsPrivate;
		const UMaterialInstance* MI = Cast<UMaterialInstance>(FontMaterial);
		if (!MI || !MI->Parent || MI->Parent->GetName() != ParentName || !MI->GetName().StartsWith(InstancePrefix))
		{
			return false;
		}
		return MI->GetVectorParameterValue(FHashedMaterialParameterInfo(TopParam), OutTop, true)
			&& MI->GetVectorParameterValue(FHashedMaterialParameterInfo(BottomParam), OutBottom, true);
	}
}
