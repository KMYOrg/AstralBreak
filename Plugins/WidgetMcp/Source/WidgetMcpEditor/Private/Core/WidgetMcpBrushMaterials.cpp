#include "Core/WidgetMcpBrushMaterials.h"

#include "AssetCompilingManager.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Engine/Texture2D.h"
#include "MaterialShared.h"
#include "Materials/Material.h"
#include "Materials/MaterialExpressionCustom.h"
#include "Materials/MaterialExpressionMultiply.h"
#include "Materials/MaterialExpressionScalarParameter.h"
#include "Materials/MaterialExpressionTextureCoordinate.h"
#include "Materials/MaterialExpressionTextureSampleParameter2D.h"
#include "Materials/MaterialExpressionVectorParameter.h"
#include "Materials/MaterialExpressionVertexColor.h"
#include "Materials/MaterialInstanceConstant.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "RHI.h"
#include "ShaderCompiler.h"
#include "UObject/Package.h"

namespace WidgetMcpBrushMaterials
{
	namespace BrushMaterialsPrivate
	{
		const TCHAR* const ParentName = TEXT("M_RadialWipe");
		const TCHAR* const InstancePrefix = TEXT("MI_RadialWipe_");
		const FName TextureParam(TEXT("Texture"));
		const FName PercentParam(TEXT("Percent"));
		const FName CenterParam(TEXT("Center"));
		const FName SizeParam(TEXT("Size"));
		const FName ModeParam(TEXT("Mode"));
		const FName TrackAlphaParam(TEXT("TrackAlpha"));
		/** 부모의 기본 텍스처 — sRGB 색 텍스처여야 표본 종류(Color)가 맞는다. 인스턴스가 늘 바꿔 쓴다 */
		const TCHAR* const DefaultTexturePath = TEXT("/Engine/EngineResources/DefaultTexture.DefaultTexture");

		/** gen/radial.py wipe_factor 와 같은 식 — 고칠 때 둘을 같이 고친다 */
		const TCHAR* const WipeCode = TEXT(
			"float P = saturate(Percent);\n"
			"if (P >= 1.0) { return 1.0; }\n"
			"if (P <= 0.0) { return TrackAlpha; }\n"
			"float2 D = UV * Size.xy - Center.xy;\n"
			"float Radius = length(D);\n"
			"float Angle = atan2(D.x, -D.y);\n"
			"const float Turn = 6.28318530718;\n"
			"float Edge;\n"
			"if (Mode < 0.5)\n"
			"{\n"
			"	float T = Angle < 0.0 ? Angle + Turn : Angle;\n"
			"	float Gone = (1.0 - P) * Turn;\n"
			"	Edge = T < Gone ? max(T - Gone, -T) : min(T - Gone, Turn - T);\n"
			"}\n"
			"else\n"
			"{\n"
			"	Edge = abs(Angle) - (1.0 - P) * 0.5 * Turn;\n"
			"}\n"
			"return lerp(TrackAlpha, 1.0, saturate(Edge * Radius + 0.5));\n");

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

		/** 새로 만든 머티리얼은 Slate 셰이더가 준비될 때까지 그 배치가 빠진다 [실측 1b 후속 D] — 끝까지 기다리고 오류를 알린다 */
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

		UMaterialExpressionScalarParameter* AddScalar(UMaterial* M, const FName& Name, float Default, int32 X, int32 Y)
		{
			UMaterialExpressionScalarParameter* E = AddExpression<UMaterialExpressionScalarParameter>(M, X, Y);
			E->ParameterName = Name;
			E->DefaultValue = Default;
			return E;
		}

		UMaterialExpressionVectorParameter* AddVector(UMaterial* M, const FName& Name, const FLinearColor& Default, int32 X, int32 Y)
		{
			UMaterialExpressionVectorParameter* E = AddExpression<UMaterialExpressionVectorParameter>(M, X, Y);
			E->ParameterName = Name;
			E->DefaultValue = Default;
			return E;
		}

		/** UI 도메인 · 반투명 — Emissive = 텍스처 rgb × 정점 색, Opacity = 텍스처 알파 × 정점 알파 × 닦기 */
		UMaterial* FindOrCreateParent(const FString& Folder, bool& bOutCreated, FString& OutError)
		{
			bOutCreated = false;
			if (UMaterial* M = FindInFolder<UMaterial>(Folder, ParentName))
			{
				return M;
			}
			UTexture2D* DefaultTexture = LoadObject<UTexture2D>(nullptr, DefaultTexturePath);
			if (!DefaultTexture)
			{
				OutError = FString::Printf(TEXT("could not load the default texture %s"), DefaultTexturePath);
				return nullptr;
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

			UMaterialExpressionTextureCoordinate* UV = AddExpression<UMaterialExpressionTextureCoordinate>(M, -1300, 300);
			UV->CoordinateIndex = 0;
			UMaterialExpressionTextureSampleParameter2D* Sample = AddExpression<UMaterialExpressionTextureSampleParameter2D>(M, -900, -100);
			Sample->ParameterName = TextureParam;
			Sample->Texture = DefaultTexture;
			Sample->SamplerType = SAMPLERTYPE_Color;
			UV->ConnectExpression(&Sample->Coordinates, 0);
			UMaterialExpressionVertexColor* Vertex = AddExpression<UMaterialExpressionVertexColor>(M, -900, 200);

			UMaterialExpressionCustom* Wipe = AddExpression<UMaterialExpressionCustom>(M, -900, 450);
			Wipe->Description = TEXT("RadialWipe");
			Wipe->OutputType = CMOT_Float1;
			Wipe->Code = WipeCode;
			Wipe->Inputs.Reset();
			auto AddInput = [Wipe](const TCHAR* Name, UMaterialExpression* From)
			{
				FCustomInput& In = Wipe->Inputs.AddDefaulted_GetRef();
				In.InputName = FName(Name);
				From->ConnectExpression(&In.Input, 0);
			};
			AddInput(TEXT("UV"), UV);
			AddInput(TEXT("Percent"), AddScalar(M, PercentParam, 1.f, -1300, 400));
			AddInput(TEXT("Center"), AddVector(M, CenterParam, FLinearColor(16.f, 16.f, 0.f, 0.f), -1300, 480));
			AddInput(TEXT("Size"), AddVector(M, SizeParam, FLinearColor(32.f, 32.f, 0.f, 0.f), -1300, 640));
			AddInput(TEXT("Mode"), AddScalar(M, ModeParam, 0.f, -1300, 800));
			AddInput(TEXT("TrackAlpha"), AddScalar(M, TrackAlphaParam, 0.f, -1300, 880));

			UMaterialExpressionMultiply* Color = AddExpression<UMaterialExpressionMultiply>(M, -500, -50);
			Sample->ConnectExpression(&Color->A, 0);
			Vertex->ConnectExpression(&Color->B, 0);
			Color->ConnectExpression(&M->GetEditorOnlyData()->EmissiveColor, 0);
			UMaterialExpressionMultiply* Alpha = AddExpression<UMaterialExpressionMultiply>(M, -500, 200);
			Sample->ConnectExpression(&Alpha->A, 4);      // 출력 4 = A
			Vertex->ConnectExpression(&Alpha->B, 4);
			UMaterialExpressionMultiply* Opacity = AddExpression<UMaterialExpressionMultiply>(M, -300, 300);
			Alpha->ConnectExpression(&Opacity->A, 0);
			Wipe->ConnectExpression(&Opacity->B, 0);
			Opacity->ConnectExpression(&M->GetEditorOnlyData()->Opacity, 0);

			M->PreEditChange(nullptr);
			M->PostEditChange();
			FAssetRegistryModule::AssetCreated(M);
			Pkg->MarkPackageDirty();
			bOutCreated = true;
			return M;
		}
	}

	FName PercentParameter()
	{
		return BrushMaterialsPrivate::PercentParam;
	}

	bool Prepare(const FString& Folder, const TMap<FString, FRadialWipe>& Wipes, TMap<FString, UMaterialInterface*>& Out, FString& OutError)
	{
		using namespace BrushMaterialsPrivate;
		if (Wipes.Num() == 0)
		{
			return true;
		}
		bool bCreatedAny = false;
		UMaterial* Parent = FindOrCreateParent(Folder, bCreatedAny, OutError);
		if (!Parent)
		{
			return false;
		}
		for (const TPair<FString, FRadialWipe>& W : Wipes)
		{
			if (!W.Value.Texture)
			{
				OutError = FString::Printf(TEXT("'%s' wipe has no texture"), *W.Key);
				return false;
			}
			const FString Name = InstancePrefix + W.Key;
			UMaterialInstanceConstant* MIC = FindInFolder<UMaterialInstanceConstant>(Folder, Name);
			FRadialWipe Current;
			const bool bExisting = MIC != nullptr;
			if (bExisting && ReadRadialWipe(MIC, Current) && Current.Texture == W.Value.Texture && Current.Percent == W.Value.Percent
				&& Current.Center.Equals(W.Value.Center, 1.e-3) && Current.Size.Equals(W.Value.Size, 1.e-3)
				&& Current.bMirror == W.Value.bMirror && Current.TrackAlpha == W.Value.TrackAlpha)
			{
				Out.Add(W.Key, MIC);
				continue;
			}
			UPackage* Pkg = CreatePackage(*(Folder / Name));
			if (!bExisting)
			{
				MIC = NewObject<UMaterialInstanceConstant>(Pkg, *Name, RF_Public | RF_Standalone | RF_Transactional);
				MIC->SetParentEditorOnly(Parent);
			}
			MIC->SetTextureParameterValueEditorOnly(FMaterialParameterInfo(TextureParam), W.Value.Texture);
			MIC->SetScalarParameterValueEditorOnly(FMaterialParameterInfo(PercentParam), W.Value.Percent);
			MIC->SetVectorParameterValueEditorOnly(FMaterialParameterInfo(CenterParam), FLinearColor(static_cast<float>(W.Value.Center.X), static_cast<float>(W.Value.Center.Y), 0.f, 0.f));
			MIC->SetVectorParameterValueEditorOnly(FMaterialParameterInfo(SizeParam), FLinearColor(static_cast<float>(W.Value.Size.X), static_cast<float>(W.Value.Size.Y), 0.f, 0.f));
			MIC->SetScalarParameterValueEditorOnly(FMaterialParameterInfo(ModeParam), W.Value.bMirror ? 1.f : 0.f);
			MIC->SetScalarParameterValueEditorOnly(FMaterialParameterInfo(TrackAlphaParam), W.Value.TrackAlpha);
			MIC->PostEditChange();
			if (!bExisting)
			{
				FAssetRegistryModule::AssetCreated(MIC);
				bCreatedAny = true;
			}
			Pkg->MarkPackageDirty();
			Out.Add(W.Key, MIC);
		}
		return !bCreatedAny || CompileAndWait(Parent, OutError);
	}

	bool ReadRadialWipe(const UObject* BrushResource, FRadialWipe& Out)
	{
		using namespace BrushMaterialsPrivate;
		const UMaterialInstance* MI = Cast<UMaterialInstance>(BrushResource);
		if (const UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(BrushResource))
		{
			MI = Cast<UMaterialInstance>(MID->Parent);      // 이름 · 부모는 원본 인스턴스에서 본다(값은 아래에서 동적 머티리얼의 것)
		}
		if (!MI || !MI->Parent || MI->Parent->GetName() != ParentName || !MI->GetName().StartsWith(InstancePrefix))
		{
			return false;
		}
		const UMaterialInstance* Values = Cast<UMaterialInstance>(BrushResource);
		UTexture* Texture = nullptr;
		float Mode = 0.f;
		FLinearColor Center, Size;
		if (!Values->GetTextureParameterValue(FHashedMaterialParameterInfo(TextureParam), Texture, false)
			|| !Values->GetScalarParameterValue(FHashedMaterialParameterInfo(PercentParam), Out.Percent, false)
			|| !Values->GetVectorParameterValue(FHashedMaterialParameterInfo(CenterParam), Center, false)
			|| !Values->GetVectorParameterValue(FHashedMaterialParameterInfo(SizeParam), Size, false)
			|| !Values->GetScalarParameterValue(FHashedMaterialParameterInfo(ModeParam), Mode, false)
			|| !Values->GetScalarParameterValue(FHashedMaterialParameterInfo(TrackAlphaParam), Out.TrackAlpha, false))
		{
			return false;
		}
		Out.Texture = Cast<UTexture2D>(Texture);
		Out.Center = FVector2D(Center.R, Center.G);
		Out.Size = FVector2D(Size.R, Size.G);
		Out.bMirror = Mode >= 0.5f;
		return Out.Texture != nullptr;
	}
}
