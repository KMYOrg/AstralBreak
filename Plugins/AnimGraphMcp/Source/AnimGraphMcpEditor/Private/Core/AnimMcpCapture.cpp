#include "AnimMcpCapture.h"

#include "AnimMcpAssetResolver.h"
#include "AnimMcpGeneration.h"
#include "AnimMcpLog.h"
#include "AnimMcpSkeletonGeometry.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "AssetCompilingManager.h"
#include "Bridge/AnimMcpTypes.h"
#include "CanvasItem.h"
#include "CanvasTypes.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/SceneCaptureComponent2D.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "ContentStreaming.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/World.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "ImageCore.h"
#include "ImageUtils.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
#include "PreviewScene.h"
#include "Rendering/SkeletalMeshLODModel.h"
#include "Rendering/SkeletalMeshModel.h"
#include "ThumbnailRendering/ThumbnailManager.h"
#include "UObject/StrongObjectPtr.h"

namespace AnimMcpCapture
{
	namespace
	{
		/** 시트 칸 사이 간격 · 색 — review_render.py GAP_PX · GAP_COLOR(0.3) 와 같다. 빈칸은 BACKGROUND(0.96) */
		constexpr int32 GapPx = 6;
		const FColor GapColor(77, 77, 77, 255);
		const FColor SheetBackground(245, 245, 245, 255);
		constexpr int32 MaxRows = 12;
		constexpr int32 MaxCompareColumns = 4;
		/** 배경판 · 바닥 판의 무광 색 (선형 — 톤매퍼를 지나 화면에서 밝은 회색 · 중간 회색) */
		const FLinearColor BackdropColor(0.80f, 0.80f, 0.80f, 1.0f);
		const FLinearColor FloorColor(0.30f, 0.30f, 0.30f, 1.0f);
		/** 피사체 판정 — 배경색과 한 채널이라도 이만큼 다르면 피사체 픽셀 */
		constexpr int32 SubjectTolerance = 10;
		/** 라벨 글자 높이 = 셀 높이 × 이 값 (Blender 0.045) */
		constexpr double LabelHeightRatio = 0.04;

		FAnimMcpError FieldError(const TCHAR* Field, const FString& Message, const TCHAR* Reason = TEXT("BAD_FIELD"))
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), Field);
			Details->SetStringField(TEXT("reason"), Reason);
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
		}

		FAnimMcpError CaptureError(const TCHAR* Reason, const FString& Message)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("reason"), Reason);
			UE_LOG(LogAnimGraphMcp, Warning, TEXT("CAPTURE_FAILED %s: %s"), Reason, *Message);
			return FAnimMcpError::Make(AnimMcpErrorCodes::CaptureFailed, Message, Details);
		}

		/** 필드가 있고 null 이 아닌가 */
		bool Present(const TSharedRef<FJsonObject>& Params, const TCHAR* Field)
		{
			const TSharedPtr<FJsonValue> Value = Params->TryGetField(Field);
			return Value.IsValid() && Value->Type != EJson::Null;
		}

		/** 선택 숫자 — 없으면 Default, 범위 밖 · 형식 오류는 BAD_REQUEST */
		bool ReadNumber(const TSharedRef<FJsonObject>& Params, const TCHAR* Field, double Default, double Min, double Max, double& Out, FAnimMcpError& OutError)
		{
			Out = Default;
			const TSharedPtr<FJsonValue> Value = Params->TryGetField(Field);
			if (!Value.IsValid() || Value->Type == EJson::Null)
			{
				return true;
			}
			if (Value->Type != EJson::Number || !FMath::IsFinite(Value->AsNumber()) || Value->AsNumber() < Min || Value->AsNumber() > Max)
			{
				OutError = FieldError(Field, FString::Printf(TEXT("%s must be a number in [%g, %g]"), Field, Min, Max));
				return false;
			}
			Out = Value->AsNumber();
			return true;
		}

		bool ReadInt(const TSharedRef<FJsonObject>& Params, const TCHAR* Field, int32 Default, int32 Min, int32 Max, int32& Out, FAnimMcpError& OutError)
		{
			double Value = 0.0;
			if (!ReadNumber(Params, Field, Default, Min, Max, Value, OutError))
			{
				return false;
			}
			if (Value != FMath::RoundToDouble(Value))
			{
				OutError = FieldError(Field, FString::Printf(TEXT("%s must be an integer in [%d, %d]"), Field, Min, Max));
				return false;
			}
			Out = static_cast<int32>(Value);
			return true;
		}

		/** "+Y" · "-Y" · "+X" · "-X" (유니코드 '−' 도) → 단위 벡터 */
		bool ParseFacing(const FString& Raw, FVector& Out)
		{
			FString Axis = Raw.TrimStartAndEnd().Replace(TEXT("−"), TEXT("-"));
			if (Axis.Len() != 2 || (Axis[0] != TEXT('+') && Axis[0] != TEXT('-')))
			{
				return false;
			}
			const double Sign = Axis[0] == TEXT('+') ? 1.0 : -1.0;
			const TCHAR Letter = FChar::ToUpper(Axis[1]);
			if (Letter == TEXT('X')) { Out = FVector(Sign, 0.0, 0.0); return true; }
			if (Letter == TEXT('Y')) { Out = FVector(0.0, Sign, 0.0); return true; }
			return false;
		}

		struct FImageBuf
		{
			int32 W = 0;
			int32 H = 0;
			TArray<FColor> Px;

			void Init(int32 InW, int32 InH, const FColor& Fill)
			{
				W = InW;
				H = InH;
				Px.Init(Fill, W * H);
			}
		};

		FImageBuf Resized(const FImageBuf& Src, int32 W, int32 H)
		{
			if (Src.W == W && Src.H == H)
			{
				return Src;
			}
			FImageBuf Out;
			Out.W = W;
			Out.H = H;
			Out.Px.SetNumUninitialized(W * H);
			FImageUtils::ImageResize(Src.W, Src.H, Src.Px, W, H, Out.Px, /*bResizeSRGBinLinearSpace*/ true, /*bForceOpaqueOutput*/ true);
			return Out;
		}

		void Blit(FImageBuf& Dst, const FImageBuf& Src, int32 X, int32 Y)
		{
			for (int32 Row = 0; Row < Src.H; ++Row)
			{
				const int32 DY = Y + Row;
				if (DY < 0 || DY >= Dst.H)
				{
					continue;
				}
				const int32 X0 = FMath::Max(0, X);
				const int32 X1 = FMath::Min(Dst.W, X + Src.W);
				if (X1 > X0)
				{
					FMemory::Memcpy(&Dst.Px[DY * Dst.W + X0], &Src.Px[Row * Src.W + (X0 - X)], (X1 - X0) * sizeof(FColor));
				}
			}
		}

		/** 비율을 지켜 (W, H) 칸 가운데에 — review_render.py reference_cell */
		FImageBuf FitIntoCell(const FImageBuf& Src, int32 W, int32 H)
		{
			FImageBuf Cell;
			Cell.Init(W, H, SheetBackground);
			if (Src.W <= 0 || Src.H <= 0)
			{
				return Cell;
			}
			const double S = FMath::Min(static_cast<double>(W) / Src.W, static_cast<double>(H) / Src.H);
			const int32 FW = FMath::Max(1, FMath::RoundToInt32(Src.W * S));
			const int32 FH = FMath::Max(1, FMath::RoundToInt32(Src.H * S));
			Blit(Cell, Resized(Src, FW, FH), (W - FW) / 2, (H - FH) / 2);
			return Cell;
		}

		FString PixelHash(const FImageBuf& Img)
		{
			FSHAHash Hash;
			FSHA1::HashBuffer(Img.Px.GetData(), Img.Px.Num() * sizeof(FColor), Hash.Hash);
			return Hash.ToString().ToLower();
		}

		bool SavePng(const FString& Path, FImageBuf& Img, FAnimMcpError& OutError)
		{
			for (FColor& C : Img.Px) { C.A = 255; }
			const FImageView View(Img.Px.GetData(), Img.W, Img.H, EGammaSpace::sRGB);
			if (!FImageUtils::SaveImageByExtension(*Path, View) || !IFileManager::Get().FileExists(*Path))
			{
				OutError = CaptureError(TEXT("WRITE_FAILED"), FString::Printf(TEXT("Could not write '%s'"), *Path));
				return false;
			}
			return true;
		}

		bool LoadPng(const FString& Path, FImageBuf& Out, FAnimMcpError& OutError)
		{
			FImage Image;
			if (!FImageUtils::LoadImage(*Path, Image) || Image.SizeX <= 0 || Image.SizeY <= 0)
			{
				OutError = CaptureError(TEXT("IMAGE_UNREADABLE"), FString::Printf(TEXT("Could not read compare image '%s'"), *Path));
				return false;
			}
			Image.ChangeFormat(ERawImageFormat::BGRA8, EGammaSpace::sRGB);
			const TArrayView64<FColor> Colors = Image.AsBGRA8();
			Out.W = static_cast<int32>(Image.SizeX);
			Out.H = static_cast<int32>(Image.SizeY);
			Out.Px.SetNumUninitialized(Out.W * Out.H);
			FMemory::Memcpy(Out.Px.GetData(), Colors.GetData(), Out.Px.Num() * sizeof(FColor));
			return true;
		}

		/** 피사체 픽셀 범위 — 오른쪽 위 구석을 배경색으로 보고, 바닥 판(FloorTopRow 아래)과 라벨 글자 상자(LabelBox)는 뺀다. 잘림 · 빈 칸 점검용 */
		TSharedRef<FJsonObject> SubjectStats(const FImageBuf& Img, int32 FloorTopRow, const FIntRect& LabelBox)
		{
			const FColor Bg = Img.Px[Img.W - 1];
			int32 X0 = Img.W, Y0 = Img.H, X1 = -1, Y1 = -1;
			int64 Count = 0;
			const int32 Rows = FMath::Clamp(FloorTopRow, 0, Img.H);
			for (int32 Y = 0; Y < Rows; ++Y)
			{
				for (int32 X = 0; X < Img.W; ++X)
				{
					if (LabelBox.Contains(FIntPoint(X, Y)))
					{
						continue;
					}
					const FColor& C = Img.Px[Y * Img.W + X];
					if (FMath::Abs(C.R - Bg.R) > SubjectTolerance || FMath::Abs(C.G - Bg.G) > SubjectTolerance || FMath::Abs(C.B - Bg.B) > SubjectTolerance)
					{
						X0 = FMath::Min(X0, X); X1 = FMath::Max(X1, X);
						Y0 = FMath::Min(Y0, Y); Y1 = FMath::Max(Y1, Y);
						++Count;
					}
				}
			}
			TSharedRef<FJsonObject> Out = AnimMcpJson::MakeObject();
			Out->SetNumberField(TEXT("coverage_pct"), FMath::RoundToDouble(1000.0 * Count / FMath::Max<int64>(1, int64(Img.W) * Rows)) / 10.0);
			if (Count == 0)
			{
				Out->SetField(TEXT("subject_px"), MakeShared<FJsonValueNull>());
				Out->SetBoolField(TEXT("touches_edge"), false);
				return Out;
			}
			TSharedRef<FJsonObject> Box = AnimMcpJson::MakeObject();
			Box->SetNumberField(TEXT("x0"), X0);
			Box->SetNumberField(TEXT("y0"), Y0);
			Box->SetNumberField(TEXT("x1"), X1);
			Box->SetNumberField(TEXT("y1"), Y1);
			Out->SetObjectField(TEXT("subject_px"), Box);
			Out->SetBoolField(TEXT("touches_edge"), X0 == 0 || Y0 == 0 || X1 == Img.W - 1);
			return Out;
		}

		TArray<TSharedPtr<FJsonValue>> VectorJson(const FVector& V)
		{
			return { MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.X * 1000.0) / 1000.0),
			         MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.Y * 1000.0) / 1000.0),
			         MakeShared<FJsonValueNumber>(FMath::RoundToDouble(V.Z * 1000.0) / 1000.0) };
		}

		/** 메시 LOD0 정점 → 가장 큰 가중치 본의 로컬 상자(기준 포즈) — 프레임마다 그 본 변환으로 옮겨 범위를 잰다 */
		TArray<FBox> BoneVertexBoxes(const USkeletalMesh* Mesh, const AnimMcpSkeletonGeometry::FTree& Tree)
		{
			TArray<FBox> Boxes;
			Boxes.Init(FBox(ForceInit), Tree.Num());
			const FSkeletalMeshModel* Model = Mesh->GetImportedModel();
			if (!Model || Model->LODModels.Num() == 0)
			{
				return Boxes;
			}
			for (const FSkelMeshSection& Section : Model->LODModels[0].Sections)
			{
				if (Section.bDisabled)
				{
					continue;
				}
				for (const FSoftSkinVertex& Vertex : Section.SoftVertices)
				{
					int32 Dominant = INDEX_NONE;
					uint16 Best = 0;
					for (int32 k = 0; k < MAX_TOTAL_INFLUENCES; ++k)
					{
						if (Vertex.InfluenceWeights[k] > Best && Section.BoneMap.IsValidIndex(Vertex.InfluenceBones[k]))
						{
							Best = Vertex.InfluenceWeights[k];
							Dominant = Section.BoneMap[Vertex.InfluenceBones[k]];
						}
					}
					if (Boxes.IsValidIndex(Dominant))
					{
						Boxes[Dominant] += Tree.Global[Dominant].InverseTransformPosition(FVector(Vertex.Position));
					}
				}
			}
			return Boxes;
		}

		struct FView
		{
			FString Name;
			/** 시선 · 화면 오른쪽 (단위) */
			FVector Look = FVector::ZeroVector;
			FVector Right = FVector::ZeroVector;
			FRange Range;
			FViewFit Fit;
			/** 연속 프레임 셀 크기 (같은 시야, 낮은 해상도) */
			int32 SeqWidth = 0;
			int32 SeqHeight = 0;
		};

		/** 부착물 하나 — 인자(메시 · 소켓 또는 본 · 상대 변환)와 장면 컴포넌트 · 메시 로컬 정점 상자 */
		struct FAttachment
		{
			FString MeshPath;
			UObject* Asset = nullptr;
			FName Socket;
			FName Bone;
			FTransform Offset = FTransform::Identity;
			UPrimitiveComponent* Component = nullptr;
			FBox LocalBox = FBox(ForceInit);
		};
		constexpr int32 MaxAttachments = 4;

		/** 부착 메시의 컴포넌트 공간 정점 상자 — 스켈레탈은 LOD0 정점(기준 포즈), 스태틱은 메시 범위 */
		FBox AttachmentBox(const UObject* Asset)
		{
			FBox Box(ForceInit);
			if (const USkeletalMesh* Skeletal = Cast<USkeletalMesh>(Asset))
			{
				if (const FSkeletalMeshModel* Model = Skeletal->GetImportedModel(); Model && Model->LODModels.Num() > 0)
				{
					for (const FSkelMeshSection& Section : Model->LODModels[0].Sections)
					{
						if (Section.bDisabled) { continue; }
						for (const FSoftSkinVertex& Vertex : Section.SoftVertices) { Box += FVector(Vertex.Position); }
					}
				}
				if (!Box.IsValid) { Box = Skeletal->GetBounds().GetBox(); }
			}
			else if (const UStaticMesh* Static = Cast<UStaticMesh>(Asset))
			{
				Box = Static->GetBoundingBox();
			}
			return Box;
		}

		/** 캡처 장면 — 임시 프리뷰 월드와 그 안 컴포넌트 · 렌더 타깃(모두 트랜지언트) */
		struct FRig
		{
			TUniquePtr<FPreviewScene> Scene;
			USkeletalMeshComponent* Skel = nullptr;
			TArray<FAttachment> Attachments;
			UStaticMeshComponent* Backdrop = nullptr;
			UStaticMeshComponent* Floor = nullptr;
			UDirectionalLightComponent* Fill = nullptr;
			USceneCaptureComponent2D* Capture = nullptr;
			TArray<TStrongObjectPtr<UObject>> Keep;
			int32 Supersample = 2;
			double FloorPad = 0.0;
		};

		UTextureRenderTarget2D* MakeTarget(FRig& Rig, int32 W, int32 H)
		{
			UTextureRenderTarget2D* RT = NewObject<UTextureRenderTarget2D>(GetTransientPackage(), NAME_None, RF_Transient);
			RT->RenderTargetFormat = RTF_RGBA8_SRGB;
			RT->ClearColor = FLinearColor::Black;
			RT->bAutoGenerateMips = false;
			RT->InitAutoFormat(W, H);
			RT->UpdateResourceImmediate(true);
			Rig.Keep.Emplace(RT);
			return RT;
		}

		/** 셀 하나 — 카메라 · 배경판 · 빛을 뷰에 맞추고 캡처 → 라벨 → 읽기 → 축소. OutLabelBox = 라벨 글자 상자(출력 픽셀, 여유 2 px) */
		bool RenderCell(FRig& Rig, const FView& View, UTextureRenderTarget2D* RT, int32 W, int32 H, const FString& Label, FImageBuf& Out, FAnimMcpError& OutError,
			FIntRect* OutLabelBox = nullptr)
		{
			if (OutLabelBox) { *OutLabelBox = FIntRect(); }
			const FVector Up(0.0, 0.0, 1.0);
			const FViewFit& Fit = View.Fit;
			const FVector Center = View.Right * Fit.CenterU + Up * Fit.CenterV;
			const double Distance = 100.0 + (Fit.DMax - Fit.DMin);
			Rig.Capture->SetWorldLocationAndRotation(Center + View.Look * (Fit.DMin - Distance), View.Look.Rotation());
			Rig.Capture->OrthoWidth = static_cast<float>(Fit.ExtentW);
			Rig.Capture->TextureTarget = RT;
			// 배경판 = 시선에 수직, 피사체 · 바닥 판 뒤 — 무광이라 그림자 · 빛을 받지 않는다
			const double BackdropSize = FMath::Max(Fit.ExtentW, Fit.ExtentH) * 2.0;
			Rig.Backdrop->SetWorldTransform(FTransform(FRotationMatrix::MakeFromZ(-View.Look).ToQuat(),
				Center + View.Look * (Fit.DMax + Rig.FloorPad + 50.0), FVector(BackdropSize / 100.0, BackdropSize / 100.0, 1.0)));
			// 주광은 카메라 왼쪽 위에서(그림자), 보조광은 오른쪽에서 — 두 뷰가 같은 조명 관계
			Rig.Scene->SetLightDirection((View.Look - Up * 0.8 + View.Right * 0.5).GetSafeNormal().Rotation());
			Rig.Fill->SetWorldRotation((View.Look - Up * 0.3 - View.Right * 0.8).GetSafeNormal().Rotation());
			Rig.Capture->CaptureScene();

			FTextureRenderTargetResource* Resource = RT->GameThread_GetRenderTargetResource();
			if (!Resource)
			{
				OutError = CaptureError(TEXT("RENDER_TARGET"), TEXT("The render target has no resource (no RHI?)"));
				return false;
			}
			if (!Label.IsEmpty() && GEngine && GEngine->GetSmallFont())
			{
				UFont* Font = GEngine->GetSmallFont();
				const double Pixel = LabelHeightRatio * RT->SizeY;
				const double Scale = Pixel / FMath::Max(1.0, static_cast<double>(Font->GetMaxCharHeight()));
				FCanvas Canvas(Resource, nullptr, Rig.Scene->GetWorld(), Rig.Scene->GetWorld()->GetFeatureLevel());
				FCanvasTextItem Item(FVector2D(Pixel * 0.5, Pixel * 0.4), FText::FromString(Label), Font, FLinearColor(0.02f, 0.02f, 0.02f, 1.0f));
				Item.Scale = FVector2D(Scale, Scale);
				Canvas.DrawItem(Item);
				Canvas.Flush_GameThread(true);
				if (OutLabelBox)
				{
					// 렌더 타깃 픽셀 → 출력 픽셀 (축소 비율)
					const double ToOut = static_cast<double>(H) / RT->SizeY;
					const double TextW = Font->GetStringSize(*Label) * Scale;
					*OutLabelBox = FIntRect(0, 0, FMath::CeilToInt32((Pixel * 0.5 + TextW) * ToOut) + 2, FMath::CeilToInt32((Pixel * 0.4 + Pixel * 1.3) * ToOut) + 2);
				}
			}
			FImageBuf Raw;
			Raw.W = RT->SizeX;
			Raw.H = RT->SizeY;
			if (!Resource->ReadPixels(Raw.Px) || Raw.Px.Num() != Raw.W * Raw.H)
			{
				OutError = CaptureError(TEXT("READBACK"), FString::Printf(TEXT("ReadPixels failed for a %dx%d capture"), Raw.W, Raw.H));
				return false;
			}
			Out = Resized(Raw, W, H);
			return true;
		}

		FString Fmt2(double Value)
		{
			return FString::Printf(TEXT("%.2f"), Value);
		}
	}

	bool ParseOffset(const TSharedPtr<FJsonObject>& Object, FTransform& Out, FString& OutWhy)
	{
		Out = FTransform::Identity;
		if (!Object.IsValid())
		{
			return true;
		}
		FVector Values[3] = { FVector::ZeroVector, FVector::ZeroVector, FVector::OneVector };
		const TCHAR* Keys[3] = { TEXT("location"), TEXT("rotation"), TEXT("scale") };
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : Object->Values)
		{
			int32 Which = INDEX_NONE;
			for (int32 k = 0; k < 3; ++k) { if (Pair.Key == Keys[k]) { Which = k; } }
			if (Which == INDEX_NONE)
			{
				OutWhy = FString::Printf(TEXT("offset.%s is unknown (location, rotation [pitch, yaw, roll], scale)"), *Pair.Key);
				return false;
			}
			const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
			if (!Pair.Value.IsValid() || !Pair.Value->TryGetArray(Array) || Array->Num() != 3
				|| Array->ContainsByPredicate([](const TSharedPtr<FJsonValue>& V) { return !V.IsValid() || V->Type != EJson::Number || !FMath::IsFinite(V->AsNumber()); }))
			{
				OutWhy = FString::Printf(TEXT("offset.%s must be three finite numbers"), Keys[Which]);
				return false;
			}
			Values[Which] = FVector((*Array)[0]->AsNumber(), (*Array)[1]->AsNumber(), (*Array)[2]->AsNumber());
		}
		if (Values[2].GetAbsMin() < 1e-4)
		{
			OutWhy = TEXT("offset.scale must not be zero");
			return false;
		}
		Out = FTransform(FRotator(Values[1].X, Values[1].Y, Values[1].Z).Quaternion(), Values[0], Values[2]);
		return true;
	}

	FViewFit FitView(const FRange& Range, double Margin, int32 CellHeight, double MaxAspect)
	{
		FViewFit Fit;
		const double UMin = Range.UMin, UMax = Range.UMax;
		const double VMin = FMath::Min(Range.VMin, 0.0), VMax = Range.VMax;  // 바닥(z = 0)은 늘 보이게
		const double NeedW = FMath::Max(UMax - UMin, 1.0) * (1.0 + 2.0 * Margin);
		const double NeedH = FMath::Max(VMax - VMin, 1.0) * (1.0 + 2.0 * Margin);
		const int32 HPx = FMath::Max(2, CellHeight);
		const double Aspect = FMath::Clamp(NeedW / NeedH, 1.0 / MaxAspect, MaxAspect);
		// Python round(반올림 짝수)와 같게 — 같은 범위면 Blender 시트와 같은 셀 폭
		const int32 WPx = FMath::Max(2, static_cast<int32>(FMath::RoundHalfToEven(HPx * Aspect / 2.0)) * 2);
		const double R = static_cast<double>(WPx) / HPx;
		if (WPx >= HPx)
		{
			Fit.Scale = FMath::Max(NeedW, NeedH * R);
			Fit.ExtentW = Fit.Scale;
			Fit.ExtentH = Fit.Scale / R;
		}
		else
		{
			Fit.Scale = FMath::Max(NeedH, NeedW / R);
			Fit.ExtentW = Fit.Scale * R;
			Fit.ExtentH = Fit.Scale;
		}
		Fit.CenterU = (UMin + UMax) / 2.0;
		Fit.CenterV = (VMin + VMax) / 2.0;
		Fit.Width = WPx;
		Fit.Height = HPx;
		Fit.DMin = Range.DMin;
		Fit.DMax = Range.DMax;
		return Fit;
	}

	double SheetScale(const TArray<int32>& ColumnWidths, int32 CellHeight, int32 Rows, int32 Gap, double SheetMaxPx)
	{
		int64 Sum = 0;
		for (const int32 Width : ColumnWidths) { Sum += Width; }
		const double GapsW = static_cast<double>(Gap) * (ColumnWidths.Num() + 1);
		const double GapsH = static_cast<double>(Gap) * (Rows + 1);
		return FMath::Min3(1.0, (SheetMaxPx - GapsW) / FMath::Max<double>(1.0, static_cast<double>(Sum)),
			(SheetMaxPx - GapsH) / FMath::Max(1.0, static_cast<double>(CellHeight) * Rows));
	}

	TArray<double> Spread(int32 Count, double Duration)
	{
		TArray<double> Times;
		if (Count <= 1 || Duration <= 0.0)
		{
			Times.Add(0.0);
			return Times;
		}
		for (int32 i = 0; i < Count; ++i)
		{
			Times.Add(FMath::RoundToDouble(i * Duration / (Count - 1) * 10000.0) / 10000.0);
		}
		return Times;
	}

	TArray<int32> SampleFrames(int32 First, int32 Last, int32 Cap, const TArray<int32>& Extra)
	{
		const int32 Step = FMath::Max(1, FMath::DivideAndRoundUp(Last - First + 1, FMath::Max(1, Cap)));
		TSet<int32> Frames;
		for (int32 Frame = First; Frame <= Last; Frame += Step) { Frames.Add(Frame); }
		Frames.Add(Last);
		for (const int32 Frame : Extra) { Frames.Add(Frame); }
		TArray<int32> Out = Frames.Array();
		Out.Sort();
		return Out;
	}

	TSharedPtr<FJsonObject> Capture(FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		const double T0 = FPlatformTime::Seconds();
		const AnimMcpGeneration::FDirtyGuard Guard;
		const TSharedRef<FJsonObject>& Params = Context.Request.Params;

		// ---- 인자 ----
		FString AssetPath, MeshPath, FacingRaw, DirRaw;
		if (!Context.Request.GetRequiredString(TEXT("asset"), AssetPath, OutError)) { return nullptr; }
		if (!Context.Request.GetRequiredString(TEXT("mesh"), MeshPath, OutError)) { return nullptr; }
		if (!Context.Request.GetRequiredString(TEXT("facing"), FacingRaw, OutError)) { return nullptr; }
		if (!Context.Request.GetRequiredString(TEXT("output_dir"), DirRaw, OutError)) { return nullptr; }
		FVector Facing;
		if (!ParseFacing(FacingRaw, Facing))
		{
			OutError = FieldError(TEXT("facing"), FString::Printf(TEXT("facing '%s' must be one of +X, -X, +Y, -Y (the UE axis the mesh's front looks along — Vesper +Y)"), *FacingRaw));
			return nullptr;
		}
		int32 CellHeight = 512, BoundsSamples = 600, Supersample = 2, Count = 0;
		double MaxAspect = 2.0, Margin = 0.08, SheetMax = 3000.0, MaxSeconds = 120.0;
		if (!ReadInt(Params, TEXT("cell_height_px"), 512, 64, 2048, CellHeight, OutError)) { return nullptr; }
		if (!ReadNumber(Params, TEXT("max_aspect"), 2.0, 1.0, 4.0, MaxAspect, OutError)) { return nullptr; }
		if (!ReadNumber(Params, TEXT("margin"), 0.08, 0.0, 0.5, Margin, OutError)) { return nullptr; }
		if (!ReadInt(Params, TEXT("bounds_max_samples"), 600, 1, 5000, BoundsSamples, OutError)) { return nullptr; }
		if (!ReadNumber(Params, TEXT("sheet_max_px"), 3000.0, 256.0, 8000.0, SheetMax, OutError)) { return nullptr; }
		if (!ReadInt(Params, TEXT("supersample"), 2, 1, 3, Supersample, OutError)) { return nullptr; }
		if (!ReadNumber(Params, TEXT("max_seconds"), 120.0, 5.0, 170.0, MaxSeconds, OutError)) { return nullptr; }
		const FString LabelPrefix = Context.Request.GetOptionalString(TEXT("label")).TrimStartAndEnd();

		TArray<double> Times;
		const bool bHasTimes = Present(Params, TEXT("times"));
		const bool bHasCount = Present(Params, TEXT("count"));
		if (bHasTimes && bHasCount)
		{
			OutError = FieldError(TEXT("times"), TEXT("give times or count, not both"), TEXT("CONFLICTING_FIELDS"));
			return nullptr;
		}
		if (bHasTimes)
		{
			const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
			if (!Params->TryGetArrayField(TEXT("times"), Array) || Array->Num() < 1 || Array->Num() > MaxRows)
			{
				OutError = FieldError(TEXT("times"), FString::Printf(TEXT("times must be 1 to %d seconds (≥ 0) on the clip"), MaxRows));
				return nullptr;
			}
			for (const TSharedPtr<FJsonValue>& V : *Array)
			{
				if (!V.IsValid() || V->Type != EJson::Number || V->AsNumber() < 0.0 || !FMath::IsFinite(V->AsNumber()))
				{
					OutError = FieldError(TEXT("times"), TEXT("times must be numbers ≥ 0 (seconds on the clip, 0 = first frame)"));
					return nullptr;
				}
				Times.Add(V->AsNumber());
			}
		}
		else if (!ReadInt(Params, TEXT("count"), 4, 1, MaxRows, Count, OutError))
		{
			return nullptr;
		}

		TArray<FString> ViewNames;
		{
			const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
			if (Present(Params, TEXT("views")))
			{
				if (!Params->TryGetArrayField(TEXT("views"), Array) || Array->Num() == 0)
				{
					OutError = FieldError(TEXT("views"), TEXT("views must be a non-empty list of distinct 'front' / 'side'"));
					return nullptr;
				}
				for (const TSharedPtr<FJsonValue>& V : *Array)
				{
					const FString Name = V.IsValid() && V->Type == EJson::String ? V->AsString() : FString();
					if ((Name != TEXT("front") && Name != TEXT("side")) || ViewNames.Contains(Name))
					{
						OutError = FieldError(TEXT("views"), TEXT("views must be a non-empty list of distinct 'front' / 'side'"));
						return nullptr;
					}
					ViewNames.Add(Name);
				}
			}
			else
			{
				ViewNames = { TEXT("front"), TEXT("side") };
			}
		}

		// 연속 프레임(움직임) — {fps, cell_height_px, start?, end?, max_frames} | null
		bool bSequence = false;
		double SeqFps = 15.0, SeqStart = 0.0, SeqEnd = -1.0;
		int32 SeqHeight = 320, SeqMaxFrames = 150;
		{
			const TSharedPtr<FJsonObject>* Seq = nullptr;
			if (Present(Params, TEXT("sequence")))
			{
				if (!Params->TryGetObjectField(TEXT("sequence"), Seq))
				{
					OutError = FieldError(TEXT("sequence"), TEXT("sequence must be {fps?, cell_height_px?, start?, end?, max_frames?} or null"));
					return nullptr;
				}
				const TSharedRef<FJsonObject> S = Seq->ToSharedRef();
				if (!ReadNumber(S, TEXT("fps"), 15.0, 1.0, 30.0, SeqFps, OutError)) { return nullptr; }
				if (!ReadInt(S, TEXT("cell_height_px"), 320, 64, 1024, SeqHeight, OutError)) { return nullptr; }
				if (!ReadNumber(S, TEXT("start"), 0.0, 0.0, 600.0, SeqStart, OutError)) { return nullptr; }
				if (!ReadNumber(S, TEXT("end"), -1.0, -1.0, 600.0, SeqEnd, OutError)) { return nullptr; }
				if (!ReadInt(S, TEXT("max_frames"), 150, 1, 300, SeqMaxFrames, OutError)) { return nullptr; }
				bSequence = true;
			}
		}

		// 조명 · 노출 (고급 — 기본값은 스파이크 실측으로 정한 값)
		double ExposureBias = 0.0, KeyIntensity = 3.0, FillIntensity = 1.0, SkyIntensity = 1.0;
		{
			const TSharedPtr<FJsonObject>* Lighting = nullptr;
			if (Params->TryGetObjectField(TEXT("lighting"), Lighting))
			{
				const TSharedRef<FJsonObject> L = Lighting->ToSharedRef();
				if (!ReadNumber(L, TEXT("exposure_bias"), 0.0, -10.0, 10.0, ExposureBias, OutError)) { return nullptr; }
				if (!ReadNumber(L, TEXT("key"), 3.0, 0.0, 100.0, KeyIntensity, OutError)) { return nullptr; }
				if (!ReadNumber(L, TEXT("fill"), 1.0, 0.0, 100.0, FillIntensity, OutError)) { return nullptr; }
				if (!ReadNumber(L, TEXT("sky"), 1.0, 0.0, 100.0, SkyIntensity, OutError)) { return nullptr; }
			}
		}

		// 비교 칸 — 행마다 같은 시각의 소스 골격 이미지(Blender review.render) 또는 앞선 캡처(보정 전 · 후 — Phase 8-3) · ImportSourceRoots · CaptureOutputRoots 아래만
		FString CompareLabel;
		TArray<TArray<FString>> CompareRows;
		{
			const TSharedPtr<FJsonObject>* Compare = nullptr;
			if (Present(Params, TEXT("compare")))
			{
				const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
				if (!Params->TryGetObjectField(TEXT("compare"), Compare) || !(*Compare)->TryGetArrayField(TEXT("rows"), Rows))
				{
					OutError = FieldError(TEXT("compare"), TEXT("compare must be {label?, rows[[image path, …] per row]}"));
					return nullptr;
				}
				(*Compare)->TryGetStringField(TEXT("label"), CompareLabel);
				for (const TSharedPtr<FJsonValue>& RowValue : *Rows)
				{
					const TArray<TSharedPtr<FJsonValue>>* Row = nullptr;
					if (!RowValue.IsValid() || !RowValue->TryGetArray(Row) || Row->Num() == 0 || Row->Num() > MaxCompareColumns)
					{
						OutError = FieldError(TEXT("compare"), FString::Printf(TEXT("compare.rows[] must be lists of 1 to %d image paths"), MaxCompareColumns));
						return nullptr;
					}
					TArray<FString>& Paths = CompareRows.AddDefaulted_GetRef();
					for (const TSharedPtr<FJsonValue>& PathValue : *Row)
					{
						FString Absolute;
						if (!PathValue.IsValid() || PathValue->Type != EJson::String)
						{
							OutError = FieldError(TEXT("compare"), TEXT("compare.rows[][] must be absolute image paths"));
							return nullptr;
						}
						if (!AnimMcpGeneration::ResolveCompareImage(PathValue->AsString(), Absolute, OutError))
						{
							if (OutError.Details.IsValid()) { OutError.Details->SetStringField(TEXT("field"), TEXT("compare")); }
							return nullptr;
						}
						Paths.Add(Absolute);
					}
				}
				if (CompareRows.Num() > 0 && CompareRows.Num() != (bHasTimes ? Times.Num() : Count))
				{
					OutError = FieldError(TEXT("compare"), FString::Printf(TEXT("compare.rows has %d row(s) but the sheet has %d"), CompareRows.Num(), bHasTimes ? Times.Num() : Count));
					return nullptr;
				}
			}
		}

		// 부착물 (Phase 8-4a) — [{mesh, socket | bone, offset?}] ≤ MaxAttachments. 소켓 · 본 존재는 메시를 읽은 뒤에
		TArray<FAttachment> Attachments;
		if (Present(Params, TEXT("attachments")))
		{
			const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
			if (!Params->TryGetArrayField(TEXT("attachments"), Array) || Array->Num() > MaxAttachments)
			{
				OutError = FieldError(TEXT("attachments"), FString::Printf(TEXT("attachments must be a list of at most %d {mesh, socket | bone, offset?}"), MaxAttachments));
				return nullptr;
			}
			for (const TSharedPtr<FJsonValue>& Item : *Array)
			{
				const TSharedPtr<FJsonObject>* Obj = nullptr;
				if (!Item.IsValid() || !Item->TryGetObject(Obj))
				{
					OutError = FieldError(TEXT("attachments"), TEXT("each attachment must be {mesh, socket | bone, offset?}"));
					return nullptr;
				}
				for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*Obj)->Values)
				{
					if (Pair.Key != TEXT("mesh") && Pair.Key != TEXT("socket") && Pair.Key != TEXT("bone") && Pair.Key != TEXT("offset"))
					{
						OutError = FieldError(TEXT("attachments"), FString::Printf(TEXT("attachments[].%s is unknown (mesh, socket, bone, offset)"), *Pair.Key));
						return nullptr;
					}
				}
				FAttachment& A = Attachments.AddDefaulted_GetRef();
				FString Socket, Bone;
				(*Obj)->TryGetStringField(TEXT("socket"), Socket);
				(*Obj)->TryGetStringField(TEXT("bone"), Bone);
				if (!(*Obj)->TryGetStringField(TEXT("mesh"), A.MeshPath) || A.MeshPath.IsEmpty() || Socket.IsEmpty() == Bone.IsEmpty())
				{
					OutError = FieldError(TEXT("attachments"), TEXT("each attachment needs mesh and exactly one of socket or bone"), Socket.IsEmpty() == Bone.IsEmpty() && !Socket.IsEmpty() ? TEXT("CONFLICTING_FIELDS") : TEXT("BAD_FIELD"));
					return nullptr;
				}
				A.Socket = Socket.IsEmpty() ? NAME_None : FName(*Socket);
				A.Bone = Bone.IsEmpty() ? NAME_None : FName(*Bone);
				const TSharedPtr<FJsonObject>* Offset = nullptr;
				FString Why;
				if ((*Obj)->HasField(TEXT("offset")) && !(*Obj)->TryGetObjectField(TEXT("offset"), Offset))
				{
					OutError = FieldError(TEXT("attachments"), TEXT("attachments[].offset must be {location?, rotation?, scale?}"));
					return nullptr;
				}
				if (!ParseOffset(Offset ? *Offset : nullptr, A.Offset, Why))
				{
					OutError = FieldError(TEXT("attachments"), FString::Printf(TEXT("attachments[] %s"), *Why));
					return nullptr;
				}
				A.Asset = AnimMcpAssetResolver::LoadAssetOfClass(A.MeshPath, UObject::StaticClass(), OutError);
				if (!A.Asset) { return nullptr; }
				if (!Cast<USkeletalMesh>(A.Asset) && !Cast<UStaticMesh>(A.Asset))
				{
					OutError = FieldError(TEXT("attachments"), FString::Printf(TEXT("'%s' is a %s — attachments take a SkeletalMesh or StaticMesh"), *A.MeshPath, *A.Asset->GetClass()->GetName()), TEXT("NOT_A_MESH"));
					return nullptr;
				}
			}
		}

		// ---- 애셋 · 폴더 ----
		UObject* AssetObject = AnimMcpAssetResolver::LoadAssetOfClass(AssetPath, UAnimSequence::StaticClass(), OutError);
		if (!AssetObject) { return nullptr; }
		UAnimSequence* Sequence = CastChecked<UAnimSequence>(AssetObject);
		UObject* MeshObject = AnimMcpAssetResolver::LoadAssetOfClass(MeshPath, USkeletalMesh::StaticClass(), OutError);
		if (!MeshObject) { return nullptr; }
		USkeletalMesh* Mesh = CastChecked<USkeletalMesh>(MeshObject);
		USkeleton* Skeleton = Sequence->GetSkeleton();
		if (!Skeleton || !Skeleton->IsCompatibleMesh(Mesh))
		{
			OutError = FieldError(TEXT("mesh"), FString::Printf(TEXT("'%s' is not compatible with the animation's skeleton '%s'"),
				*Mesh->GetPathName(), Skeleton ? *Skeleton->GetPathName() : TEXT("(none)")), TEXT("SKELETON_MISMATCH"));
			OutError.Details->SetField(TEXT("skeleton"), AnimMcpJson::ObjectPathOrNull(Skeleton));
			return nullptr;
		}
		for (const FAttachment& A : Attachments)
		{
			// FindSocket = 메시 소켓 → 스켈레톤 소켓
			if (!A.Socket.IsNone() && !Mesh->FindSocket(A.Socket))
			{
				OutError = FieldError(TEXT("attachments"), FString::Printf(TEXT("socket '%s' is not on '%s' or its skeleton"), *A.Socket.ToString(), *Mesh->GetName()), TEXT("SOCKET_NOT_FOUND"));
				return nullptr;
			}
			if (!A.Bone.IsNone() && Mesh->GetRefSkeleton().FindBoneIndex(A.Bone) == INDEX_NONE)
			{
				OutError = FieldError(TEXT("attachments"), FString::Printf(TEXT("bone '%s' is not in '%s'"), *A.Bone.ToString(), *Mesh->GetName()), TEXT("BONE_NOT_FOUND"));
				return nullptr;
			}
		}
		FString Dir;
		if (!AnimMcpGeneration::ResolveCaptureDir(DirRaw, Dir, OutError)) { return nullptr; }

		const double Fps = Sequence->GetSamplingFrameRate().AsDecimal();
		const int32 NumKeys = Sequence->GetNumberOfSampledKeys();
		const double Length = Sequence->GetPlayLength();
		if (NumKeys < 1 || Fps <= 0.0)
		{
			OutError = FieldError(TEXT("asset"), FString::Printf(TEXT("'%s' has no sampled frames"), *Sequence->GetPathName()), TEXT("NO_FRAMES"));
			return nullptr;
		}
		if (!bHasTimes)
		{
			Times = Spread(Count, Length);
		}
		struct FRow { double Time; int32 Frame; double FrameTime; bool bClamped; };
		TArray<FRow> Rows;
		for (const double Time : Times)
		{
			const int32 Want = static_cast<int32>(FMath::RoundHalfToEven(Time * Fps));
			const int32 Frame = FMath::Clamp(Want, 0, NumKeys - 1);
			Rows.Add({ Time, Frame, Frame / Fps, Frame != Want });
		}

		// ---- 장면 ----
		FRig Rig;
		Rig.Supersample = Supersample;
		Rig.Scene = MakeUnique<FPreviewScene>(FPreviewScene::ConstructionValues()
			.SetCreatePhysicsScene(false)
			.SetTransactional(false)
			.SetLightBrightness(static_cast<float>(KeyIntensity))
			.SetSkyBrightness(static_cast<float>(SkyIntensity)));
		if (!Rig.Scene->GetWorld() || !Rig.Scene->GetScene())
		{
			OutError = CaptureError(TEXT("NO_SCENE"), TEXT("Could not create the preview world"));
			return nullptr;
		}
		Rig.Scene->SetSkyCubemap(UThumbnailManager::Get().AmbientCubemap);

		Rig.Skel = NewObject<USkeletalMeshComponent>(GetTransientPackage(), NAME_None, RF_Transient);
		Rig.Skel->SetSkeletalMesh(Mesh);
		Rig.Skel->SetForcedLOD(1);                      // 1 = LOD0
		Rig.Skel->bEnableUpdateRateOptimizations = false;
		Rig.Skel->bDisableClothSimulation = true;        // 옷 · 머리 물리는 돌지 않는다 — 스키닝 그대로
		Rig.Skel->SetBoundsScale(20.0f);                 // 루트가 움직여도 컬링되지 않게
		Rig.Scene->AddComponent(Rig.Skel, FTransform::Identity);
		Rig.Skel->SetDisablePostProcessBlueprint(true);
		Rig.Skel->SetAnimationMode(EAnimationMode::AnimationSingleNode);
		Rig.Skel->SetAnimation(Sequence);
		Rig.Skel->Stop();

		// 부착물 — 소켓 · 본에 붙인 트랜지언트 컴포넌트(스켈레탈은 기준 포즈 그대로)
		for (FAttachment& A : Attachments)
		{
			UPrimitiveComponent* Component = nullptr;
			if (USkeletalMesh* Skeletal = Cast<USkeletalMesh>(A.Asset))
			{
				USkeletalMeshComponent* Comp = NewObject<USkeletalMeshComponent>(GetTransientPackage(), NAME_None, RF_Transient);
				Comp->SetSkeletalMesh(Skeletal);
				Comp->SetForcedLOD(1);
				Comp->bDisableClothSimulation = true;
				Component = Comp;
			}
			else
			{
				UStaticMeshComponent* Comp = NewObject<UStaticMeshComponent>(GetTransientPackage(), NAME_None, RF_Transient);
				Comp->SetStaticMesh(Cast<UStaticMesh>(A.Asset));
				Component = Comp;
			}
			Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Component->SetBoundsScale(4.0f);
			Rig.Scene->AddComponent(Component, FTransform::Identity);
			Component->AttachToComponent(Rig.Skel, FAttachmentTransformRules::KeepRelativeTransform, A.Socket.IsNone() ? A.Bone : A.Socket);
			Component->SetRelativeTransform(A.Offset);
			A.Component = Component;
			A.LocalBox = AttachmentBox(A.Asset);
		}
		Rig.Attachments = Attachments;

		UStaticMesh* Plane = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane"));
		UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
		UMaterial* Unlit = GEngine ? GEngine->LevelColorationUnlitMaterial.Get() : nullptr;
		if (!Plane || !Cube || !Unlit)
		{
			OutError = CaptureError(TEXT("NO_SCENE"), TEXT("Engine content missing (/Engine/BasicShapes/Plane · Cube or LevelColorationUnlitMaterial)"));
			return nullptr;
		}
		auto MakeSolid = [&Rig, Unlit](UStaticMesh* StaticMesh, const FLinearColor& Color)
		{
			UMaterialInstanceDynamic* Material = UMaterialInstanceDynamic::Create(Unlit, GetTransientPackage());
			Material->SetVectorParameterValue(TEXT("Color"), Color);
			Rig.Keep.Emplace(Material);
			UStaticMeshComponent* Component = NewObject<UStaticMeshComponent>(GetTransientPackage(), NAME_None, RF_Transient);
			Component->SetStaticMesh(StaticMesh);
			Component->SetMaterial(0, Material);
			Component->SetCastShadow(false);
			Rig.Scene->AddComponent(Component, FTransform::Identity);
			return Component;
		};
		Rig.Backdrop = MakeSolid(Plane, BackdropColor);
		Rig.Floor = MakeSolid(Cube, FloorColor);

		Rig.Fill = NewObject<UDirectionalLightComponent>(GetTransientPackage(), NAME_None, RF_Transient);
		Rig.Fill->SetIntensity(static_cast<float>(FillIntensity));
		Rig.Fill->SetCastShadows(false);
		Rig.Scene->AddComponent(Rig.Fill, FTransform::Identity);

		Rig.Capture = NewObject<USceneCaptureComponent2D>(GetTransientPackage(), NAME_None, RF_Transient);
		Rig.Capture->ProjectionType = ECameraProjectionMode::Orthographic;
		Rig.Capture->bCaptureEveryFrame = false;
		Rig.Capture->bCaptureOnMovement = false;
		Rig.Capture->bAlwaysPersistRenderingState = false;
		Rig.Capture->bExcludeFromSceneTextureExtents = true;
		Rig.Capture->bUseRayTracingIfEnabled = false;
		Rig.Capture->CaptureSource = SCS_FinalColorLDR;
		Rig.Capture->PrimitiveRenderMode = ESceneCapturePrimitiveRenderMode::PRM_UseShowOnlyList;
		Rig.Capture->ShowOnlyComponent(Rig.Skel);
		Rig.Capture->ShowOnlyComponent(Rig.Backdrop);
		Rig.Capture->ShowOnlyComponent(Rig.Floor);
		for (const FAttachment& A : Rig.Attachments) { Rig.Capture->ShowOnlyComponent(A.Component); }
		{
			// ShowFlags 를 직접 바꾸면 등록(OnRegister → UpdateShowFlags)이 설정 배열로 되돌린다 — 설정 배열로 준다(2026-10-26 실측: 비네트가 남았다)
			TArray<FEngineShowFlagsSetting> Flags;
			for (const TCHAR* Name : { TEXT("TemporalAA"), TEXT("MotionBlur"), TEXT("Bloom"), TEXT("EyeAdaptation"), TEXT("LumenGlobalIllumination"),
			                           TEXT("LumenReflections"), TEXT("ScreenSpaceReflections"), TEXT("Vignette"), TEXT("DepthOfField"), TEXT("LensFlares"),
			                           TEXT("Grain"), TEXT("Atmosphere"), TEXT("Cloud"), TEXT("VolumetricFog") })
			{
				FEngineShowFlagsSetting& Setting = Flags.AddDefaulted_GetRef();
				Setting.ShowFlagName = Name;   // TemporalAA 를 끄면 이력 없는 한 장 캡처에 FXAA
				Setting.Enabled = false;
			}
			Rig.Capture->SetShowFlagSettings(Flags);
		}
		FPostProcessSettings& Post = Rig.Capture->PostProcessSettings;
		Post.bOverride_AutoExposureMethod = true;
		Post.AutoExposureMethod = AEM_Manual;
		Post.bOverride_AutoExposureApplyPhysicalCameraExposure = true;
		Post.AutoExposureApplyPhysicalCameraExposure = 0;
		Post.bOverride_AutoExposureBias = true;
		Post.AutoExposureBias = static_cast<float>(ExposureBias);
		Post.bOverride_DynamicGlobalIlluminationMethod = true;
		Post.DynamicGlobalIlluminationMethod = EDynamicGlobalIlluminationMethod::None;
		Post.bOverride_ReflectionMethod = true;
		Post.ReflectionMethod = EReflectionMethod::None;
		Rig.Capture->PostProcessBlendWeight = 1.0f;
		Rig.Scene->AddComponent(Rig.Capture, FTransform::Identity);

		// bRender 면 렌더 상태를 다시 만든다 — 틱하지 않는 프리뷰 월드에서는 동적 데이터만 표시해서는 스키닝이 첫 포즈에 머물렀다
		// (2026-10-26 실측: 행마다 같은 포즈). 엔진 썸네일(FAnimationSequenceThumbnailScene::SetAnimation)도 같은 순서다
		auto Pose = [&Rig](double Time, bool bRender)
		{
			Rig.Skel->SetPosition(static_cast<float>(Time), false);
			Rig.Skel->RefreshBoneTransforms(nullptr);
			Rig.Skel->UpdateBounds();
			// 부착물은 소켓 · 본의 새 변환을 따라간다 — 포즈 평가의 자식 갱신에 기대지 않고 한 번 더 맞춘다
			for (const FAttachment& A : Rig.Attachments)
			{
				A.Component->UpdateComponentToWorld();
			}
			if (bRender)
			{
				Rig.Skel->RecreateRenderState_Concurrent();
				for (const FAttachment& A : Rig.Attachments) { A.Component->RecreateRenderState_Concurrent(); }
			}
		};

		// ---- 범위 — 전 프레임(상한 BoundsSamples + 행 프레임)의 본 위치 + 본 정점 상자 꼭짓점 ----
		const FVector Up(0.0, 0.0, 1.0);
		const FVector BodyRight = FVector::CrossProduct(Up, Facing);   // UE 왼손 좌표 — +Y 정면이면 -X
		TArray<FView> Views;
		for (const FString& Name : ViewNames)
		{
			FView& View = Views.AddDefaulted_GetRef();
			View.Name = Name;
			View.Look = Name == TEXT("front") ? -Facing : -BodyRight;   // 정면 = 몸 앞에서, 측면 = 몸 오른쪽에서
			View.Right = FVector::CrossProduct(Up, View.Look);           // 화면 오른쪽 = 카메라 +Y — 정면이면 몸의 왼쪽, 측면이면 몸의 정면
		}
		AnimMcpSkeletonGeometry::FTree Tree;
		Tree.Init(Mesh->GetRefSkeleton());
		const TArray<FBox> Boxes = BoneVertexBoxes(Mesh, Tree);
		int32 BoxedBones = 0;
		for (const FBox& Box : Boxes) { BoxedBones += Box.IsValid ? 1 : 0; }
		TArray<int32> RowFrames;
		for (const FRow& Row : Rows) { RowFrames.Add(Row.Frame); }
		const TArray<int32> BoundFrames = SampleFrames(0, NumKeys - 1, BoundsSamples, RowFrames);
		FBox World(ForceInit);
		for (const int32 Frame : BoundFrames)
		{
			Pose(Frame / Fps, false);
			const TArray<FTransform>& Space = Rig.Skel->GetComponentSpaceTransforms();
			auto AddPoint = [&World, &Views](const FVector& P)
			{
				World += P;
				for (FView& View : Views) { View.Range.Add(FVector::DotProduct(P, View.Right), P.Z, FVector::DotProduct(P, View.Look)); }
			};
			// 부착물 정점 상자 꼭짓점(무기 끝이 화면 밖으로 나가지 않게)
			for (const FAttachment& A : Rig.Attachments)
			{
				if (!A.LocalBox.IsValid) { continue; }
				const FTransform& X = A.Component->GetComponentTransform();
				for (int32 Corner = 0; Corner < 8; ++Corner)
				{
					AddPoint(X.TransformPosition(FVector((Corner & 1) ? A.LocalBox.Max.X : A.LocalBox.Min.X, (Corner & 2) ? A.LocalBox.Max.Y : A.LocalBox.Min.Y,
						(Corner & 4) ? A.LocalBox.Max.Z : A.LocalBox.Min.Z)));
				}
			}
			for (int32 Bone = 0; Bone < Space.Num(); ++Bone)
			{
				// 정점이 묶이지 않은 본(IK · 무기 · 루트 보조 본)은 메시 밖에 있을 수 있다 — 범위는 스킨된 본의 정점 상자만(없으면 본 위치)
				if (BoxedBones == 0)
				{
					AddPoint(Space[Bone].GetLocation());
				}
				if (Boxes.IsValidIndex(Bone) && Boxes[Bone].IsValid)
				{
					const FBox& Box = Boxes[Bone];
					for (int32 Corner = 0; Corner < 8; ++Corner)
					{
						const FVector Local((Corner & 1) ? Box.Max.X : Box.Min.X, (Corner & 2) ? Box.Max.Y : Box.Min.Y, (Corner & 4) ? Box.Max.Z : Box.Min.Z);
						AddPoint(Space[Bone].TransformPosition(Local));
					}
				}
			}
		}
		if (!World.IsValid)
		{
			OutError = CaptureError(TEXT("NO_POSE"), TEXT("The mesh produced no bone transforms"));
			return nullptr;
		}
		const double Height = FMath::Max(1.0, World.Max.Z - FMath::Min(World.Min.Z, 0.0));
		Rig.FloorPad = 0.15 * Height;
		const double FloorThickness = FMath::Max(0.5, 0.01 * Height);
		{
			// 바닥 판 = 전 프레임 범위 + 여유(키 × 0.15), 윗면 z = 0 — review_render.py 의 바닥 띠
			const FVector Size((World.Max.X - World.Min.X) + 2.0 * Rig.FloorPad, (World.Max.Y - World.Min.Y) + 2.0 * Rig.FloorPad, FloorThickness);
			const FVector Center((World.Min.X + World.Max.X) / 2.0, (World.Min.Y + World.Max.Y) / 2.0, -FloorThickness / 2.0);
			Rig.Floor->SetWorldTransform(FTransform(FQuat::Identity, Center, Size / 100.0));
		}
		for (FView& View : Views)
		{
			View.Fit = FitView(View.Range, Margin, CellHeight, MaxAspect);
			View.SeqHeight = SeqHeight;
			View.SeqWidth = FMath::Max(2, static_cast<int32>(FMath::RoundHalfToEven(View.Fit.Width * static_cast<double>(SeqHeight) / CellHeight / 2.0)) * 2);
		}

		// ---- 준비 — 한 번 그려 셰이더 · 메시 · 텍스처 요청을 낸 뒤 컴파일 · 스트리밍을 기다린다 ----
		TMap<FIntPoint, UTextureRenderTarget2D*> Targets;
		auto Target = [&Rig, &Targets](int32 W, int32 H)
		{
			const FIntPoint Key(W * Rig.Supersample, H * Rig.Supersample);
			if (UTextureRenderTarget2D** Found = Targets.Find(Key)) { return *Found; }
			UTextureRenderTarget2D* RT = MakeTarget(Rig, Key.X, Key.Y);
			Targets.Add(Key, RT);
			return RT;
		};
		{
			Pose(Rows[0].FrameTime, true);
			FImageBuf Warm;
			for (int32 Pass = 0; Pass < 2; ++Pass)
			{
				for (const FView& View : Views)
				{
					if (!RenderCell(Rig, View, Target(View.Fit.Width, View.Fit.Height), View.Fit.Width, View.Fit.Height, FString(), Warm, OutError)) { return nullptr; }
				}
				FAssetCompilingManager::Get().FinishAllCompilation();
				IStreamingManager::Get().UpdateResourceStreaming(0.0f, true);
				IStreamingManager::Get().BlockTillAllRequestsFinished(10.0f);
			}
		}
		const double PrepareSeconds = FPlatformTime::Seconds() - T0;

		IFileManager::Get().MakeDirectory(*Dir, true);
		auto LabelFor = [&LabelPrefix](const FString& View, double FrameTime, int32 Frame)
		{
			const FString Text = FString::Printf(TEXT("%s   t %ss   frame %d"), *View, *Fmt2(FrameTime), Frame);
			return LabelPrefix.IsEmpty() ? Text : LabelPrefix + TEXT(" ") + Text;
		};

		// ---- 행 × 뷰 ----
		TArray<TArray<FImageBuf>> Grid;
		TArray<TSharedPtr<FJsonValue>> FramesJson;
		int32 EdgeCells = 0;
		// 행마다 스킨된 본의 평균 위치 — 행끼리 같으면 포즈가 바뀌지 않은 것(점검용)
		auto PoseCenter = [&Rig, &Boxes]()
		{
			const TArray<FTransform>& Space = Rig.Skel->GetComponentSpaceTransforms();
			FVector Sum = FVector::ZeroVector;
			int32 N = 0;
			for (int32 Bone = 0; Bone < Space.Num(); ++Bone)
			{
				if (Boxes.IsValidIndex(Bone) && Boxes[Bone].IsValid) { Sum += Space[Bone].GetLocation(); ++N; }
			}
			return N > 0 ? Sum / N : FVector::ZeroVector;
		};
		TArray<FVector> RowCenters;
		for (int32 r = 0; r < Rows.Num(); ++r)
		{
			Pose(Rows[r].FrameTime, true);
			RowCenters.Add(PoseCenter());
			TArray<FImageBuf>& Cells = Grid.AddDefaulted_GetRef();
			for (const FView& View : Views)
			{
				FImageBuf& Cell = Cells.AddDefaulted_GetRef();
				FIntRect LabelBox;
				if (!RenderCell(Rig, View, Target(View.Fit.Width, View.Fit.Height), View.Fit.Width, View.Fit.Height,
					LabelFor(View.Name, Rows[r].FrameTime, Rows[r].Frame), Cell, OutError, &LabelBox)) { return nullptr; }
				const FString Path = FString::Printf(TEXT("%s/%s_%05d.png"), *Dir, *View.Name, Rows[r].Frame);
				if (!SavePng(Path, Cell, OutError)) { return nullptr; }
				const int32 FloorTop = FMath::FloorToInt32((View.Fit.CenterV + View.Fit.ExtentH / 2.0) / View.Fit.ExtentH * View.Fit.Height);
				TSharedRef<FJsonObject> Stats = SubjectStats(Cell, FloorTop, LabelBox);
				EdgeCells += Stats->GetBoolField(TEXT("touches_edge")) ? 1 : 0;
				TSharedRef<FJsonObject> Entry = AnimMcpJson::MakeObject();
				Entry->SetNumberField(TEXT("row"), r);
				Entry->SetNumberField(TEXT("time"), Rows[r].Time);
				Entry->SetNumberField(TEXT("frame"), Rows[r].Frame);
				Entry->SetNumberField(TEXT("frame_time"), FMath::RoundToDouble(Rows[r].FrameTime * 10000.0) / 10000.0);
				Entry->SetStringField(TEXT("view"), View.Name);
				Entry->SetStringField(TEXT("path"), Path);
				Entry->SetStringField(TEXT("sha1"), PixelHash(Cell));
				Entry->Values.Append(Stats->Values);
				FramesJson.Add(MakeShared<FJsonValueObject>(Entry));
			}
		}

		// ---- 시트 (행 = 시각, 열 = 뷰) · 비교 시트 (+ 소스 골격 칸) ----
		auto ComposeSheet = [&Grid, CellHeight, SheetMax](const TArray<int32>& ExtraWidths, const TArray<TArray<FImageBuf>>* Extra, FImageBuf& Sheet, TArray<int32>& OutWidths)
		{
			TArray<int32> Widths;
			for (const FImageBuf& Cell : Grid[0]) { Widths.Add(Cell.W); }
			Widths.Append(ExtraWidths);
			const double Scale = SheetScale(Widths, CellHeight, Grid.Num(), GapPx, SheetMax);
			const int32 CellH = FMath::Max(2, static_cast<int32>(CellHeight * Scale));   // 내림 — 반올림이 쌓여 한도를 넘지 않게
			OutWidths.Reset();
			for (const int32 Width : Widths) { OutWidths.Add(FMath::Max(2, static_cast<int32>(Width * Scale))); }
			int32 TotalW = GapPx * (OutWidths.Num() + 1);
			for (const int32 Width : OutWidths) { TotalW += Width; }
			Sheet.Init(TotalW, CellH * Grid.Num() + GapPx * (Grid.Num() + 1), GapColor);
			for (int32 r = 0; r < Grid.Num(); ++r)
			{
				int32 X = GapPx;
				const int32 Y = GapPx + r * (CellH + GapPx);
				for (int32 c = 0; c < OutWidths.Num(); ++c)
				{
					const bool bOwn = c < Grid[r].Num();
					const FImageBuf& Src = bOwn ? Grid[r][c] : (*Extra)[r][c - Grid[r].Num()];
					Blit(Sheet, bOwn ? Resized(Src, OutWidths[c], CellH) : FitIntoCell(Src, OutWidths[c], CellH), X, Y);
					X += OutWidths[c] + GapPx;
				}
			}
			return Scale;
		};
		FImageBuf Sheet;
		TArray<int32> SheetWidths;
		const double SheetScaleUsed = ComposeSheet({}, nullptr, Sheet, SheetWidths);
		const FString SheetPath = Dir / TEXT("sheet.png");
		if (!SavePng(SheetPath, Sheet, OutError)) { return nullptr; }

		TSharedPtr<FJsonObject> CompareJson;
		if (CompareRows.Num() > 0)
		{
			TArray<TArray<FImageBuf>> Extra;
			TArray<int32> ExtraWidths;
			for (int32 r = 0; r < CompareRows.Num(); ++r)
			{
				TArray<FImageBuf>& Images = Extra.AddDefaulted_GetRef();
				for (int32 c = 0; c < CompareRows[r].Num(); ++c)
				{
					if (!LoadPng(CompareRows[r][c], Images.AddDefaulted_GetRef(), OutError)) { return nullptr; }
				}
			}
			const int32 Columns = Extra[0].Num();
			for (int32 r = 1; r < Extra.Num(); ++r)
			{
				if (Extra[r].Num() != Columns)
				{
					OutError = FieldError(TEXT("compare"), TEXT("every compare row needs the same number of images"));
					return nullptr;
				}
			}
			for (const FImageBuf& Image : Extra[0])
			{
				const double Aspect = FMath::Clamp(static_cast<double>(Image.W) / Image.H, 1.0 / MaxAspect, MaxAspect);
				ExtraWidths.Add(FMath::Max(2, FMath::RoundToInt32(CellHeight * Aspect)));
			}
			FImageBuf CompareSheet;
			TArray<int32> CompareWidths;
			const double CompareScale = ComposeSheet(ExtraWidths, &Extra, CompareSheet, CompareWidths);
			const FString ComparePath = Dir / TEXT("compare.png");
			if (!SavePng(ComparePath, CompareSheet, OutError)) { return nullptr; }
			CompareJson = AnimMcpJson::MakeObject();
			CompareJson->SetStringField(TEXT("path"), ComparePath);
			CompareJson->SetStringField(TEXT("label"), CompareLabel);
			CompareJson->SetNumberField(TEXT("own_columns"), Views.Num());
			CompareJson->SetNumberField(TEXT("compare_columns"), Columns);
			TArray<TSharedPtr<FJsonValue>> Size = { MakeShared<FJsonValueNumber>(CompareSheet.W), MakeShared<FJsonValueNumber>(CompareSheet.H) };
			CompareJson->SetArrayField(TEXT("size"), Size);
			CompareJson->SetNumberField(TEXT("scale"), FMath::RoundToDouble(CompareScale * 10000.0) / 10000.0);
		}

		// ---- 연속 프레임 — 뷰를 나란히 한 장씩 (anim_gen 이 APNG 로 잇는다) ----
		TSharedPtr<FJsonObject> SequenceJson;
		if (bSequence)
		{
			const double Start = FMath::Clamp(SeqStart, 0.0, Length);
			const double End = SeqEnd < 0.0 ? Length : FMath::Clamp(SeqEnd, Start, Length);
			// 끝 프레임까지 — 마지막 시각은 End 로 자른다(1.3333초 · 15 fps = 21장, 마지막 1.3333초)
			const int32 Wanted = FMath::CeilToInt32((End - Start) * SeqFps - 1e-3) + 1;
			const int32 Planned = FMath::Min(Wanted, SeqMaxFrames);
			const FString SeqDir = Dir / TEXT("sequence");
			IFileManager::Get().MakeDirectory(*SeqDir, true);
			int32 TotalW = GapPx * (Views.Num() - 1);
			for (const FView& View : Views) { TotalW += View.SeqWidth; }
			TArray<TSharedPtr<FJsonValue>> SeqFrames, SeqTimes;
			bool bTruncated = Planned < Wanted;
			const double SeqT0 = FPlatformTime::Seconds();
			for (int32 k = 0; k < Planned; ++k)
			{
				if (FPlatformTime::Seconds() - T0 > MaxSeconds)
				{
					bTruncated = true;
					Context.AddDiagnostic(TEXT("warning"), TEXT("CAPTURE_TRUNCATED"), FString::Printf(TEXT("sequence stopped after %d of %d frame(s) — max_seconds %g reached"), k, Planned, MaxSeconds));
					break;
				}
				const double Time = FMath::Min(Start + k / SeqFps, End);
				Pose(Time, true);
				FImageBuf Frame;
				Frame.Init(TotalW, SeqHeight, GapColor);
				int32 X = 0;
				for (int32 v = 0; v < Views.Num(); ++v)
				{
					const FView& View = Views[v];
					FImageBuf Cell;
					const FString TimeLabel = FString::Printf(TEXT("t %ss"), *Fmt2(Time));
					const FString Label = v != 0 ? FString() : LabelPrefix.IsEmpty() ? TimeLabel : LabelPrefix + TEXT("   ") + TimeLabel;
					if (!RenderCell(Rig, View, Target(View.SeqWidth, View.SeqHeight), View.SeqWidth, View.SeqHeight, Label, Cell, OutError)) { return nullptr; }
					Blit(Frame, Cell, X, 0);
					X += View.SeqWidth + GapPx;
				}
				const FString Path = FString::Printf(TEXT("%s/f_%05d.png"), *SeqDir, k);
				if (!SavePng(Path, Frame, OutError)) { return nullptr; }
				SeqFrames.Add(MakeShared<FJsonValueString>(Path));
				SeqTimes.Add(MakeShared<FJsonValueNumber>(FMath::RoundToDouble(Time * 10000.0) / 10000.0));
			}
			SequenceJson = AnimMcpJson::MakeObject();
			SequenceJson->SetStringField(TEXT("dir"), SeqDir);
			SequenceJson->SetNumberField(TEXT("fps"), SeqFps);
			SequenceJson->SetNumberField(TEXT("count"), SeqFrames.Num());
			SequenceJson->SetArrayField(TEXT("frames"), SeqFrames);
			SequenceJson->SetArrayField(TEXT("times"), SeqTimes);
			TArray<TSharedPtr<FJsonValue>> Size = { MakeShared<FJsonValueNumber>(TotalW), MakeShared<FJsonValueNumber>(SeqHeight) };
			SequenceJson->SetArrayField(TEXT("size"), Size);
			SequenceJson->SetBoolField(TEXT("truncated"), bTruncated);
			SequenceJson->SetNumberField(TEXT("seconds"), FMath::RoundToDouble((FPlatformTime::Seconds() - SeqT0) * 1000.0) / 1000.0);
		}

		// ---- 가드 — 캡처는 패키지를 하나도 더티로 만들지 않아야 한다(파일은 이미 썼다 — 폴더를 details 에) ----
		TArray<FString> NewlyAllowed, NewlyUnexpected;
		Guard.GetNewlyDirty(NewlyAllowed, NewlyUnexpected);
		NewlyUnexpected.Append(NewlyAllowed);
		if (NewlyUnexpected.Num() > 0)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetArrayField(TEXT("unexpected"), AnimMcpGeneration::ToJsonArray(NewlyUnexpected));
			Details->SetStringField(TEXT("dir"), Dir);
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::UnexpectedDirty,
				FString::Printf(TEXT("capture_animation left %d package(s) dirty (first: %s) — a capture must not touch assets"), NewlyUnexpected.Num(), *NewlyUnexpected[0]), Details);
			return nullptr;
		}

		// ---- 결과 ----
		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetStringField(TEXT("asset"), Sequence->GetPathName());
		Result->SetStringField(TEXT("mesh"), Mesh->GetPathName());
		Result->SetStringField(TEXT("facing"), FacingRaw.TrimStartAndEnd());
		Result->SetNumberField(TEXT("length"), Length);
		Result->SetNumberField(TEXT("frame_rate"), Fps);
		Result->SetNumberField(TEXT("frames_total"), NumKeys);
		Result->SetStringField(TEXT("dir"), Dir);
		Result->SetArrayField(TEXT("frames"), FramesJson);
		Result->SetStringField(TEXT("sheet"), SheetPath);
		Result->SetField(TEXT("compare"), CompareJson.IsValid() ? TSharedPtr<FJsonValue>(MakeShared<FJsonValueObject>(CompareJson)) : MakeShared<FJsonValueNull>());
		Result->SetField(TEXT("sequence"), SequenceJson.IsValid() ? TSharedPtr<FJsonValue>(MakeShared<FJsonValueObject>(SequenceJson)) : MakeShared<FJsonValueNull>());
		{
			TSharedRef<FJsonObject> Layout = AnimMcpJson::MakeObject();
			TArray<TSharedPtr<FJsonValue>> RowsJson, ColumnsJson;
			for (int32 r = 0; r < Rows.Num(); ++r)
			{
				TSharedRef<FJsonObject> R = AnimMcpJson::MakeObject();
				R->SetNumberField(TEXT("time"), Rows[r].Time);
				R->SetNumberField(TEXT("frame"), Rows[r].Frame);
				R->SetNumberField(TEXT("frame_time"), FMath::RoundToDouble(Rows[r].FrameTime * 10000.0) / 10000.0);
				R->SetBoolField(TEXT("clamped"), Rows[r].bClamped);
				R->SetArrayField(TEXT("pose_center"), VectorJson(RowCenters[r]));
				RowsJson.Add(MakeShared<FJsonValueObject>(R));
			}
			for (int32 c = 0; c < Views.Num(); ++c)
			{
				TSharedRef<FJsonObject> C = AnimMcpJson::MakeObject();
				C->SetStringField(TEXT("kind"), TEXT("view"));
				C->SetStringField(TEXT("view"), Views[c].Name);
				C->SetNumberField(TEXT("width"), Views[c].Fit.Width);
				C->SetNumberField(TEXT("sheet_width"), SheetWidths[c]);
				ColumnsJson.Add(MakeShared<FJsonValueObject>(C));
			}
			Layout->SetArrayField(TEXT("rows"), RowsJson);
			Layout->SetArrayField(TEXT("columns"), ColumnsJson);
			Layout->SetNumberField(TEXT("cell_height"), FMath::Max(2, static_cast<int32>(CellHeight * SheetScaleUsed)));
			Layout->SetNumberField(TEXT("gap"), GapPx);
			TArray<TSharedPtr<FJsonValue>> Size = { MakeShared<FJsonValueNumber>(Sheet.W), MakeShared<FJsonValueNumber>(Sheet.H) };
			Layout->SetArrayField(TEXT("size"), Size);
			Layout->SetNumberField(TEXT("scale"), FMath::RoundToDouble(SheetScaleUsed * 10000.0) / 10000.0);
			Result->SetObjectField(TEXT("layout"), Layout);
		}
		{
			TSharedRef<FJsonObject> Camera = AnimMcpJson::MakeObject();
			for (const FView& View : Views)
			{
				TSharedRef<FJsonObject> C = AnimMcpJson::MakeObject();
				C->SetArrayField(TEXT("look"), VectorJson(View.Look));
				C->SetArrayField(TEXT("right"), VectorJson(View.Right));
				C->SetNumberField(TEXT("ortho_width_cm"), FMath::RoundToDouble(View.Fit.ExtentW * 1000.0) / 1000.0);
				C->SetNumberField(TEXT("ortho_height_cm"), FMath::RoundToDouble(View.Fit.ExtentH * 1000.0) / 1000.0);
				TArray<TSharedPtr<FJsonValue>> Resolution = { MakeShared<FJsonValueNumber>(View.Fit.Width), MakeShared<FJsonValueNumber>(View.Fit.Height) };
				C->SetArrayField(TEXT("resolution"), Resolution);
				C->SetNumberField(TEXT("cm_per_px"), FMath::RoundToDouble(View.Fit.ExtentH / View.Fit.Height * 10000.0) / 10000.0);
				Camera->SetObjectField(View.Name, C);
			}
			Result->SetObjectField(TEXT("camera"), Camera);
		}
		{
			TSharedRef<FJsonObject> Bounds = AnimMcpJson::MakeObject();
			Bounds->SetArrayField(TEXT("min"), VectorJson(World.Min));
			Bounds->SetArrayField(TEXT("max"), VectorJson(World.Max));
			Bounds->SetNumberField(TEXT("frames_sampled"), BoundFrames.Num());
			Bounds->SetStringField(TEXT("from"), Rig.Attachments.Num() > 0 ? TEXT("bone_vertex_boxes + attachment boxes") : TEXT("bone_vertex_boxes"));
			Bounds->SetNumberField(TEXT("boxed_bones"), BoxedBones);
			Result->SetObjectField(TEXT("bounds"), Bounds);
		}
		{
			TArray<TSharedPtr<FJsonValue>> AttachmentsJson;
			for (const FAttachment& A : Rig.Attachments)
			{
				TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
				Item->SetStringField(TEXT("mesh"), A.Asset->GetPathName());
				Item->SetStringField(TEXT("class"), A.Asset->GetClass()->GetName());
				Item->SetField(TEXT("socket"), AnimMcpJson::StringOrNull(A.Socket.IsNone() ? FString() : A.Socket.ToString()));
				Item->SetField(TEXT("bone"), AnimMcpJson::StringOrNull(A.Bone.IsNone() ? FString() : A.Bone.ToString()));
				TSharedRef<FJsonObject> Offset = AnimMcpJson::MakeObject();
				const FRotator R = A.Offset.GetRotation().Rotator();
				Offset->SetArrayField(TEXT("location"), VectorJson(A.Offset.GetLocation()));
				Offset->SetArrayField(TEXT("rotation"), VectorJson(FVector(R.Pitch, R.Yaw, R.Roll)));
				Offset->SetArrayField(TEXT("scale"), VectorJson(A.Offset.GetScale3D()));
				Item->SetObjectField(TEXT("offset"), Offset);
				TSharedRef<FJsonObject> Box = AnimMcpJson::MakeObject();
				Box->SetArrayField(TEXT("min"), VectorJson(A.LocalBox.IsValid ? A.LocalBox.Min : FVector::ZeroVector));
				Box->SetArrayField(TEXT("max"), VectorJson(A.LocalBox.IsValid ? A.LocalBox.Max : FVector::ZeroVector));
				Item->SetObjectField(TEXT("local_bounds_cm"), Box);
				AttachmentsJson.Add(MakeShared<FJsonValueObject>(Item));
			}
			Result->SetArrayField(TEXT("attachments"), AttachmentsJson);
		}
		{
			TSharedRef<FJsonObject> Render = AnimMcpJson::MakeObject();
			Render->SetStringField(TEXT("capture_source"), TEXT("FinalColorLDR"));
			Render->SetStringField(TEXT("anti_aliasing"), FString::Printf(TEXT("FXAA + supersample %d"), Supersample));
			Render->SetNumberField(TEXT("exposure_bias"), ExposureBias);
			Render->SetNumberField(TEXT("key_light"), KeyIntensity);
			Render->SetNumberField(TEXT("fill_light"), FillIntensity);
			Render->SetNumberField(TEXT("sky_light"), SkyIntensity);
			Render->SetStringField(TEXT("disabled"), TEXT("Lumen GI/reflections, SSR, TAA, motion blur, bloom, eye adaptation, DOF, vignette, cloth simulation"));
			Render->SetNumberField(TEXT("prepare_seconds"), FMath::RoundToDouble(PrepareSeconds * 1000.0) / 1000.0);
			Result->SetObjectField(TEXT("render"), Render);
		}
		Result->SetNumberField(TEXT("cells_touching_edge"), EdgeCells);
		Result->SetNumberField(TEXT("seconds"), FMath::RoundToDouble((FPlatformTime::Seconds() - T0) * 1000.0) / 1000.0);
		if (EdgeCells > 0)
		{
			Context.AddDiagnostic(TEXT("warning"), TEXT("CAPTURE_SUBJECT_AT_EDGE"), FString::Printf(TEXT("%d cell(s) have subject pixels on the image edge — framing may cut the mesh"), EdgeCells));
		}
		return Result;
	}
}
