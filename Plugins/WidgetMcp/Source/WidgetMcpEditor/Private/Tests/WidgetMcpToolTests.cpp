// WidgetMcp Tool 자동 시험 — 설계 Docs/Design/ui-autogen-pipeline.md §6 · §9 (Phase 1a-2).
// 로컬 디스패처에 Tool 을 등록하고 실제 요청 본문(JSON)으로 부른다 — 브리지 봉투 · 오류 코드까지 같은 경로.
// 애셋은 /Game/_AutoGen/_WidgetMcpTest_<이름>_<시각>/ 에 메모리로만 만들고 끝에 discard_run_packages 로 버린다(저장 안 함).
// PNG 입력 · 렌더 출력은 Tools/uigen/work/_widgetmcp_tests/<이름>_<시각>/ (git 무시, Saved 밖).
// 실행: run_automation_tests {filter:"WidgetMcp."}

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Blueprint/WidgetTree.h"
#include "Core/WidgetMcpCommon.h"
#include "Core/WidgetMcpFonts.h"
#include "Engine/Font.h"
#include "Engine/FontFace.h"
#include "HAL/FileManager.h"
#include "ImageCore.h"
#include "ImageUtils.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/DateTime.h"
#include "Misc/Paths.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Tests/WidgetMcpTestWidgets.h"
#include "Tools/WidgetMcpTools.h"
#include "UObject/Package.h"
#include "WidgetBlueprint.h"

namespace WidgetMcpToolTests
{
	struct FCall
	{
		bool bOk = false;
		FString Code;
		FString Reason;
		FString Message;
		TSharedPtr<FJsonObject> Result;
		TSharedPtr<FJsonObject> Details;
	};

	struct FHarness
	{
		FEditorMcpDispatcher Dispatcher;
		FString RunPath;
		FString DiskDir;

		explicit FHarness(const TCHAR* Name)
		{
			WidgetMcpTools::Register(Dispatcher);
			const FString Stamp = FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"));
			RunPath = FString::Printf(TEXT("/Game/_AutoGen/_WidgetMcpTest_%s_%s"), Name, *Stamp);
			DiskDir = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectDir(), TEXT("Tools/uigen/work/_widgetmcp_tests"), FString::Printf(TEXT("%s_%s"), Name, *Stamp)));
			IFileManager::Get().MakeDirectory(*DiskDir, true);
		}

		FCall Call(const TCHAR* Tool, const FString& BodyJson)
		{
			int32 Status = 0;
			const FString Envelope = Dispatcher.Dispatch(FName(Tool), BodyJson, Status);
			TSharedPtr<FJsonObject> Env;
			FString ParseError;
			FCall Out;
			if (!EditorMcpJson::Parse(Envelope, Env, ParseError))
			{
				Out.Code = TEXT("UNPARSEABLE");
				Out.Message = ParseError;
				return Out;
			}
			Env->TryGetBoolField(TEXT("ok"), Out.bOk);
			const TSharedPtr<FJsonObject>* R = nullptr;
			if (Env->TryGetObjectField(TEXT("result"), R)) { Out.Result = *R; }
			const TSharedPtr<FJsonObject>* E = nullptr;
			if (Env->TryGetObjectField(TEXT("error"), E))
			{
				(*E)->TryGetStringField(TEXT("code"), Out.Code);
				(*E)->TryGetStringField(TEXT("message"), Out.Message);
				const TSharedPtr<FJsonObject>* D = nullptr;
				if ((*E)->TryGetObjectField(TEXT("details"), D)) { Out.Details = *D; (*D)->TryGetStringField(TEXT("reason"), Out.Reason); }
			}
			return Out;
		}

		FCall Call(const TCHAR* Tool, const TSharedRef<FJsonObject>& Params)
		{
			return Call(Tool, EditorMcpJson::ToString(Params));
		}

		void Discard()
		{
			Call(TEXT("discard_run_packages"), FString::Printf(TEXT("{\"run_path\":\"%s\"}"), *RunPath));
		}
	};

	TSharedRef<FJsonObject> Json(const FString& Text)
	{
		TSharedPtr<FJsonObject> O;
		FString Error;
		EditorMcpJson::Parse(Text, O, Error);
		return O.IsValid() ? O.ToSharedRef() : MakeShared<FJsonObject>();
	}

	/** 작은 RGBA PNG — 테두리 W 픽셀만 금색, 안은 반투명 어둠(9-slice 프레임 흉내) */
	FString WritePng(const FString& Dir, const FString& Name, int32 W, int32 H)
	{
		TArray<FColor> Pixels;
		Pixels.SetNum(W * H);
		for (int32 Y = 0; Y < H; ++Y)
		{
			for (int32 X = 0; X < W; ++X)
			{
				const bool bEdge = X < 3 || Y < 3 || X >= W - 3 || Y >= H - 3;
				Pixels[Y * W + X] = bEdge ? FColor(232, 181, 74, 255) : FColor(26, 20, 12, 200);
			}
		}
		const FString Path = FPaths::Combine(Dir, Name);
		FImageUtils::SaveImageByExtension(*Path, FImageView(Pixels.GetData(), W, H, EGammaSpace::sRGB));
		return Path;
	}

	FString ImportBody(const FString& Run, const FString& Frame, const FString& Glow)
	{
		return FString::Printf(TEXT(R"({"dest_path":"%s","textures":[{"file":"%s","name":"T_frame"},{"file":"%s","name":"T_glow","compression":"TC_BC7"}]})"), *Run, *Frame, *Glow);
	}

	/** 시험 spec — 부모 UWidgetMcpTestHud 의 바인딩(Gauge 필수 · Label 선택)을 채운다 */
	const TCHAR* const SpecA = TEXT(R"JSON({
  "root": "Root",
  "widgets": [
    { "id": "Root", "type": "CanvasPanel" },
    { "id": "Panel", "type": "Border", "parent": "Root",
      "slot": { "kind": "canvas", "position": [40, 40], "size": [320, 140], "z": 1 },
      "style": { "brush": { "draw_as": "box", "asset": "frame", "margin": [0.1, 0.2, 0.1, 0.2] } } },
    { "id": "PanelBox", "type": "VerticalBox", "parent": "Panel", "slot": { "kind": "border", "padding": [8, 6, 8, 6] } },
    { "id": "Title", "type": "TextBlock", "parent": "PanelBox", "slot": { "kind": "vertical_box", "size_rule": "fill", "fill": 1 },
      "text": { "value": "체인" }, "font": { "size": 18, "weight": "bold", "color": "#FFF3D6",
        "outline": { "size": 2, "color": "#1A0E05" }, "shadow": { "offset": [2, 3], "color": "#000000B0" }, "letter_spacing": 60,
        "gradient": { "top_color": "#FFE9A8", "bottom_color": "#C8902E" } }, "justification": "center" },
    { "id": "Label", "type": "TextBlock", "parent": "PanelBox", "slot": { "kind": "vertical_box", "size_rule": "fill", "fill": 2 },
      "text": { "source": "dynamic", "data": "label", "sample": "4.2" }, "font": { "size": 28, "weight": "regular", "glow": { "size": 6, "color": "#FFB04880" } } },
    { "id": "GaugeArea", "type": "Overlay", "parent": "Root",
      "slot": { "kind": "canvas", "anchors": [0.5, 1, 0.5, 1], "alignment": [0.5, 1], "position": [0, -20], "size": [300, 30] } },
    { "id": "Glow", "type": "Image", "parent": "GaugeArea", "slot": { "kind": "overlay", "h_align": "fill", "v_align": "fill" },
      "style": { "brush": { "asset": "glow" } }, "visibility": "collapsed" },
    { "id": "Gauge", "type": "ProgressBar", "parent": "GaugeArea", "slot": { "kind": "overlay", "padding": [6, 6, 6, 6], "h_align": "fill", "v_align": "fill" },
      "style": { "fill": { "draw_as": "rounded_box", "color": "#E8B54A", "radius": 4 }, "percent": 0.7, "bar_fill_style": "scale" } },
    { "id": "Swatch", "type": "Border", "parent": "Root", "slot": { "kind": "canvas", "position": [400, 40], "size": [80, 80] },
      "style": { "brush": { "draw_as": "image", "color": "#202838" } } }
  ]
})JSON");

	TSharedRef<FJsonObject> ApplyBody(const FHarness& H, const FString& Wbp, const TSharedRef<FJsonObject>& Spec, const FString& Revision, const TSharedRef<FJsonObject>& Assets)
	{
		TSharedRef<FJsonObject> B = MakeShared<FJsonObject>();
		B->SetStringField(TEXT("asset_path"), Wbp);
		B->SetObjectField(TEXT("spec"), Spec);
		B->SetObjectField(TEXT("assets"), Assets);
		if (!Revision.IsEmpty()) { B->SetStringField(TEXT("expected_revision"), Revision); }
		return B;
	}

	TSharedPtr<FJsonObject> FindWidget(const TSharedPtr<FJsonObject>& Spec, const FString& Id)
	{
		for (const TSharedPtr<FJsonValue>& V : Spec->GetArrayField(TEXT("widgets")))
		{
			if (V->AsObject()->GetStringField(TEXT("id")) == Id) { return V->AsObject(); }
		}
		return nullptr;
	}

	void RemoveWidget(const TSharedRef<FJsonObject>& Spec, const FString& Id)
	{
		TArray<TSharedPtr<FJsonValue>> Arr = Spec->GetArrayField(TEXT("widgets"));
		Arr.RemoveAll([&Id](const TSharedPtr<FJsonValue>& V) { return V->AsObject()->GetStringField(TEXT("id")) == Id; });
		Spec->SetArrayField(TEXT("widgets"), Arr);
	}
}

using namespace WidgetMcpToolTests;

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWidgetMcpImportTexturesTest, "WidgetMcp.Tools.ImportTextures", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWidgetMcpImportTexturesTest::RunTest(const FString& Parameters)
{
	FHarness H(TEXT("Import"));
	const FString Frame = WritePng(H.DiskDir, TEXT("frame.png"), 200, 50);   // 2의 거듭제곱이 아님 — 기본 Interchange 파이프라인이면 걸러진다
	const FString Glow = WritePng(H.DiskDir, TEXT("glow.png"), 64, 32);

	FCall C = H.Call(TEXT("import_ui_textures"), ImportBody(H.RunPath, Frame, Glow));
	TestTrue(FString::Printf(TEXT("import ok (%s %s)"), *C.Code, *C.Message), C.bOk);
	if (C.bOk)
	{
		const TArray<TSharedPtr<FJsonValue>>& T = C.Result->GetArrayField(TEXT("textures"));
		TestEqual(TEXT("two textures"), T.Num(), 2);
		if (T.Num() == 2)
		{
			const TSharedPtr<FJsonObject> F = T[0]->AsObject();
			TestEqual(TEXT("frame compression"), F->GetStringField(TEXT("compression")), FString(TEXT("TC_EditorIcon")));
			TestEqual(TEXT("frame lod group"), F->GetStringField(TEXT("lod_group")), FString(TEXT("TEXTUREGROUP_UI")));
			TestEqual(TEXT("frame mips"), F->GetStringField(TEXT("mip_gen")), FString(TEXT("TMGS_NoMipmaps")));
			TestTrue(TEXT("frame never streams"), F->GetBoolField(TEXT("never_stream")));
			TestTrue(TEXT("frame sRGB"), F->GetBoolField(TEXT("srgb")));
			TestEqual(TEXT("frame keeps its NPOT size"), F->GetArrayField(TEXT("size"))[0]->AsNumber(), 200.0);
			TestEqual(TEXT("frame asset path"), WidgetMcp::ToPackagePath(F->GetStringField(TEXT("asset_path"))), H.RunPath + TEXT("/T_frame"));
			TestEqual(TEXT("glow compression"), T[1]->AsObject()->GetStringField(TEXT("compression")), FString(TEXT("TC_BC7")));
			AddInfo(FString::Printf(TEXT("pipeline stack %s, pipelines %s"), *F->GetStringField(TEXT("pipeline_stack")), *EditorMcpJson::ToString(F.ToSharedRef())));
		}
		TestTrue(TEXT("newly dirty only inside the run"), C.Result->GetArrayField(TEXT("newly_dirty")).Num() >= 2);
	}

	// 안전장치
	C = H.Call(TEXT("import_ui_textures"), ImportBody(H.RunPath, Frame, Glow));
	TestEqual(TEXT("re-import refused"), C.Code, FString(TEXT("ASSET_EXISTS")));
	C = H.Call(TEXT("import_ui_textures"), ImportBody(TEXT("/Game/UI/WidgetMcpNotAllowed"), Frame, Glow));
	TestEqual(TEXT("dest outside WidgetOutputPaths"), C.Code, FString(TEXT("OUTPUT_PATH_NOT_ALLOWED")));
	C = H.Call(TEXT("import_ui_textures"), ImportBody(TEXT("/Game/_AutoGen"), Frame, Glow));
	TestEqual(TEXT("the prefix itself is not a run folder"), C.Code, FString(TEXT("OUTPUT_PATH_NOT_ALLOWED")));
	C = H.Call(TEXT("import_ui_textures"), FString::Printf(TEXT(R"({"dest_path":"%s_2","textures":[{"file":"Saved/nope.png","name":"T_x"}]})"), *H.RunPath));
	TestEqual(TEXT("file outside WidgetImportSourceRoots"), C.Reason, FString(TEXT("DISK_ROOT")));
	C = H.Call(TEXT("import_ui_textures"), FString::Printf(TEXT(R"({"dest_path":"%s_2","textures":[{"file":"%s","name":"T_x","compression":"TC_Nope"}]})"), *H.RunPath, *Frame));
	TestEqual(TEXT("unknown compression"), C.Reason, FString(TEXT("BAD_SETTING")));

	C = H.Call(TEXT("discard_run_packages"), FString::Printf(TEXT("{\"run_path\":\"%s\"}"), *H.RunPath));
	TestTrue(FString::Printf(TEXT("discard ok (%s %s)"), *C.Code, *C.Message), C.bOk);
	if (C.bOk)
	{
		TestEqual(TEXT("two packages discarded"), C.Result->GetArrayField(TEXT("discarded")).Num(), 2);
		TestEqual(TEXT("nothing still dirty"), C.Result->GetArrayField(TEXT("still_dirty")).Num(), 0);
	}
	TArray<FAssetData> Left;
	FAssetRegistryModule::GetRegistry().GetAssetsByPath(FName(*H.RunPath), Left, true, false);
	TestEqual(TEXT("asset registry forgot the run"), Left.Num(), 0);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWidgetMcpBuildRoundTripTest, "WidgetMcp.Tools.BuildRoundTrip", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWidgetMcpBuildRoundTripTest::RunTest(const FString& Parameters)
{
	FHarness H(TEXT("Build"));
	const FString Frame = WritePng(H.DiskDir, TEXT("frame.png"), 200, 50);
	const FString Glow = WritePng(H.DiskDir, TEXT("glow.png"), 64, 32);
	FCall C = H.Call(TEXT("import_ui_textures"), ImportBody(H.RunPath, Frame, Glow));
	TestTrue(TEXT("textures imported"), C.bOk);
	const TSharedRef<FJsonObject> Assets = Json(FString::Printf(TEXT(R"({"frame":"%s/T_frame","glow":"%s/T_glow"})"), *H.RunPath, *H.RunPath));
	const FString Wbp = H.RunPath + TEXT("/WBP_Test");

	C = H.Call(TEXT("create_widget_blueprint"), FString::Printf(TEXT(R"({"asset_path":"%s","parent_class":"%s"})"), *Wbp, *UWidgetMcpTestHud::StaticClass()->GetPathName()));
	TestTrue(FString::Printf(TEXT("create ok (%s %s)"), *C.Code, *C.Message), C.bOk);
	if (!C.bOk) { H.Discard(); return true; }
	FString Revision = C.Result->GetStringField(TEXT("revision"));
	TestEqual(TEXT("root is a canvas named Root"), C.Result->GetStringField(TEXT("root")), FString(TEXT("Root")));
	TestEqual(TEXT("parent bindings listed"), C.Result->GetArrayField(TEXT("bindings")).Num(), 2);

	const TSharedRef<FJsonObject> Spec = Json(SpecA);
	C = H.Call(TEXT("preview_widget_spec"), ApplyBody(H, Wbp, Spec, FString(), Assets));
	TestTrue(TEXT("preview ok"), C.bOk && C.Result->GetBoolField(TEXT("valid")));
	if (C.bOk)
	{
		TestEqual(TEXT("preview leaves revision"), C.Result->GetStringField(TEXT("revision")), Revision);
		TestTrue(TEXT("preview lists ops"), C.Result->GetArrayField(TEXT("ops")).Num() >= 8);
	}

	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Wbp, Spec, TEXT("sha1:stale"), Assets));
	TestEqual(TEXT("stale revision refused"), C.Code, FString(TEXT("REVISION_MISMATCH")));
	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Wbp, Spec, Revision, Assets));
	TestTrue(FString::Printf(TEXT("apply ok (%s %s %s)"), *C.Code, *C.Message, C.Details.IsValid() ? *EditorMcpJson::ToString(C.Details.ToSharedRef()) : TEXT("")), C.bOk);
	if (!C.bOk) { H.Discard(); return true; }
	TestTrue(TEXT("apply verified by export"), C.Result->GetBoolField(TEXT("verified")));
	const TSharedPtr<FJsonObject> Compile = C.Result->GetObjectField(TEXT("compile"));
	TestTrue(FString::Printf(TEXT("compiles (%s)"), *EditorMcpJson::ToString(Compile.ToSharedRef())), Compile->GetBoolField(TEXT("ok")));
	TestEqual(TEXT("no missing bindings"), Compile->GetArrayField(TEXT("missing_bindings")).Num(), 0);
	Revision = C.Result->GetStringField(TEXT("revision_after"));

	// export — revision 안정 · GUID 맵 · 텍스처 설정 · asset id 되돌림
	C = H.Call(TEXT("export_widget_spec"), FString::Printf(TEXT(R"({"asset_path":"%s","assets":%s})"), *Wbp, *EditorMcpJson::ToString(Assets)));
	TestTrue(TEXT("export ok"), C.bOk);
	if (C.bOk)
	{
		TestEqual(TEXT("export revision == apply revision"), C.Result->GetStringField(TEXT("revision")), Revision);
		TestEqual(TEXT("every widget has a GUID"), C.Result->GetArrayField(TEXT("guid_missing")).Num(), 0);
		TestEqual(TEXT("widget count"), C.Result->GetNumberField(TEXT("widget_count")), 9.0);
		TestEqual(TEXT("two brush textures described"), C.Result->GetArrayField(TEXT("textures")).Num(), 2);
		const TSharedPtr<FJsonObject> Exported = C.Result->GetObjectField(TEXT("spec"));
		const TSharedPtr<FJsonObject> Panel = FindWidget(Exported, TEXT("Panel"));
		TestEqual(TEXT("brush asset back as asset id"), Panel->GetObjectField(TEXT("style"))->GetObjectField(TEXT("brush"))->GetStringField(TEXT("asset")), FString(TEXT("frame")));
		TestEqual(TEXT("brush image_size = texture size"), Panel->GetObjectField(TEXT("style"))->GetObjectField(TEXT("brush"))->GetArrayField(TEXT("image_size"))[0]->AsNumber(), 200.0);
		TestEqual(TEXT("color round-trips"), FindWidget(Exported, TEXT("Title"))->GetObjectField(TEXT("font"))->GetStringField(TEXT("color")), FString(TEXT("#FFF3D6FF")));
		// 글자 효과(1b 후속 D) — 외곽선 · 그림자 · 자간 · 그라데이션(run 폴더 MIC) 왕복, 효과 없는 글자에는 키가 없다
		const TSharedPtr<FJsonObject> TitleFont = FindWidget(Exported, TEXT("Title"))->GetObjectField(TEXT("font"));
		const TSharedPtr<FJsonObject>* Outline = nullptr;
		TestTrue(TEXT("outline round-trips"), TitleFont->TryGetObjectField(TEXT("outline"), Outline) && (*Outline)->GetNumberField(TEXT("size")) == 2.0
			&& (*Outline)->GetStringField(TEXT("color")) == TEXT("#1A0E05FF"));
		const TSharedPtr<FJsonObject>* Shadow = nullptr;
		TestTrue(TEXT("shadow round-trips"), TitleFont->TryGetObjectField(TEXT("shadow"), Shadow) && (*Shadow)->GetArrayField(TEXT("offset"))[1]->AsNumber() == 3.0
			&& (*Shadow)->GetStringField(TEXT("color")) == TEXT("#000000B0"));
		TestEqual(TEXT("letter spacing round-trips"), TitleFont->GetNumberField(TEXT("letter_spacing")), 60.0);
		const TSharedPtr<FJsonObject>* Gradient = nullptr;
		TestTrue(TEXT("gradient round-trips"), TitleFont->TryGetObjectField(TEXT("gradient"), Gradient) && (*Gradient)->GetStringField(TEXT("top_color")) == TEXT("#FFE9A8FF")
			&& (*Gradient)->GetStringField(TEXT("bottom_color")) == TEXT("#C8902EFF"));
		TestTrue(TEXT("gradient material lives in the run folder"), FindObject<UObject>(nullptr, *(H.RunPath + TEXT("/MI_TextGradient_FFE9A8FF_C8902EFF.MI_TextGradient_FFE9A8FF_C8902EFF"))) != nullptr
			&& FindObject<UObject>(nullptr, *(H.RunPath + TEXT("/M_TextGradient.M_TextGradient"))) != nullptr);
		const TSharedPtr<FJsonObject> LabelFont = FindWidget(Exported, TEXT("Label"))->GetObjectField(TEXT("font"));
		TestFalse(TEXT("no effect keys without effects"), LabelFont->HasField(TEXT("outline")) || LabelFont->HasField(TEXT("shadow")) || LabelFont->HasField(TEXT("letter_spacing")) || LabelFont->HasField(TEXT("gradient")));
		// 1b 후속 F — 빛(외곽선 층 빛 MIC, 외곽선 키로는 안 나옴) · 진행바 채움 방식 scale 왕복, 빛 없는 글자에는 키가 없다
		const TSharedPtr<FJsonObject>* TextGlow = nullptr;
		TestTrue(TEXT("glow round-trips"), LabelFont->TryGetObjectField(TEXT("glow"), TextGlow) && (*TextGlow)->GetNumberField(TEXT("size")) == 6.0
			&& (*TextGlow)->GetStringField(TEXT("color")) == TEXT("#FFB04880"));
		TestTrue(TEXT("glow material lives in the run folder"), FindObject<UObject>(nullptr, *(H.RunPath + TEXT("/MI_TextGlow_FFB04880_S6_F280.MI_TextGlow_FFB04880_S6_F280"))) != nullptr
			&& FindObject<UObject>(nullptr, *(H.RunPath + TEXT("/M_TextGlow.M_TextGlow"))) != nullptr);
		TestFalse(TEXT("no glow key without a glow"), TitleFont->HasField(TEXT("glow")));
		TestEqual(TEXT("bar fill style round-trips"), FindWidget(Exported, TEXT("Gauge"))->GetObjectField(TEXT("style"))->GetStringField(TEXT("bar_fill_style")), FString(TEXT("scale")));
		TestEqual(TEXT("dynamic text shows its sample"), FindWidget(Exported, TEXT("Label"))->GetObjectField(TEXT("text"))->GetStringField(TEXT("value")), FString(TEXT("4.2")));
		TestEqual(TEXT("Korean text kept"), FindWidget(Exported, TEXT("Title"))->GetObjectField(TEXT("text"))->GetStringField(TEXT("value")), FString(TEXT("체인")));
	}

	// 같은 spec 다시 — op 0 · revision 그대로(멱등)
	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Wbp, Spec, Revision, Assets));
	TestTrue(TEXT("idempotent apply ok"), C.bOk);
	if (C.bOk)
	{
		TestEqual(TEXT("idempotent apply has no ops"), C.Result->GetArrayField(TEXT("ops")).Num(), 0);
		TestEqual(TEXT("idempotent apply keeps revision"), C.Result->GetStringField(TEXT("revision_after")), Revision);
	}

	// 바꾼 spec — 위치 · 추가 · 제거 · 이동 · 글자 크기
	const TSharedRef<FJsonObject> SpecB = Json(SpecA);
	FindWidget(SpecB, TEXT("Swatch"))->GetObjectField(TEXT("slot"))->SetArrayField(TEXT("position"), { MakeShared<FJsonValueNumber>(420), MakeShared<FJsonValueNumber>(50) });
	FindWidget(SpecB, TEXT("Label"))->GetObjectField(TEXT("font"))->SetNumberField(TEXT("size"), 30);
	RemoveWidget(SpecB, TEXT("Title"));
	TArray<TSharedPtr<FJsonValue>> Arr = SpecB->GetArrayField(TEXT("widgets"));
	Arr.Add(MakeShared<FJsonValueObject>(Json(TEXT(R"({"id":"Extra","type":"Spacer","parent":"Root","slot":{"kind":"canvas","position":[10,10],"size":[4,4]}})"))));
	SpecB->SetArrayField(TEXT("widgets"), Arr);
	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Wbp, SpecB, Revision, Assets));
	TestTrue(FString::Printf(TEXT("second apply ok (%s %s)"), *C.Code, *C.Message), C.bOk);
	if (C.bOk)
	{
		TSet<FString> Kinds;
		for (const TSharedPtr<FJsonValue>& V : C.Result->GetArrayField(TEXT("ops"))) { Kinds.Add(V->AsObject()->GetStringField(TEXT("op"))); }
		TestTrue(TEXT("ops include add/remove/set"), Kinds.Contains(TEXT("add_widget")) && Kinds.Contains(TEXT("remove_widget")) && Kinds.Contains(TEXT("set")));
		TestNotEqual(TEXT("revision moved"), C.Result->GetStringField(TEXT("revision_after")), Revision);
		Revision = C.Result->GetStringField(TEXT("revision_after"));
		TestTrue(TEXT("still compiles"), C.Result->GetObjectField(TEXT("compile"))->GetBoolField(TEXT("ok")));
		FEditorMcpError E;
		UWidgetBlueprint* Loaded = FindObject<UWidgetBlueprint>(nullptr, *(Wbp + TEXT(".WBP_Test")));
		TestTrue(TEXT("Title gone, Extra present"), Loaded && !Loaded->WidgetTree->FindWidget(TEXT("Title")) && Loaded->WidgetTree->FindWidget(TEXT("Extra")));
		TestTrue(TEXT("removed name left the GUID map"), Loaded && !Loaded->WidgetVariableNameToGuidMap.Contains(TEXT("Title")) && Loaded->WidgetVariableNameToGuidMap.Contains(TEXT("Extra")));
	}

	// 거부 — 바인딩 제거 · 바인딩 타입 · locked · 어휘 밖 타입
	{
		const TSharedRef<FJsonObject> Bad = Json(SpecA);
		RemoveWidget(Bad, TEXT("Gauge"));
		C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Wbp, Bad, Revision, Assets));
		TestEqual(TEXT("bound widget removal refused"), C.Reason, FString(TEXT("BINDING_REMOVAL")));
	}
	{
		const TSharedRef<FJsonObject> Bad = Json(SpecA);
		TSharedPtr<FJsonObject> G = FindWidget(Bad, TEXT("Gauge"));
		G->SetStringField(TEXT("type"), TEXT("Image"));
		G->RemoveField(TEXT("style"));
		C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Wbp, Bad, Revision, Assets));
		TestEqual(TEXT("bound widget retype refused"), C.Reason, FString(TEXT("BINDING_TYPE")));
	}
	{
		const TSharedRef<FJsonObject> Bad = Json(SpecA);
		Bad->SetArrayField(TEXT("locked"), { MakeShared<FJsonValueString>(TEXT("Swatch")) });
		C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Wbp, Bad, Revision, Assets));   // Swatch 는 지금 [420,50] — SpecA 는 [400,40]
		TestEqual(TEXT("locked widget change refused"), C.Reason, FString(TEXT("LOCKED")));
	}
	{
		const TSharedRef<FJsonObject> Bad = Json(SpecA);
		FindWidget(Bad, TEXT("Swatch"))->SetStringField(TEXT("type"), TEXT("ScrollBox"));
		C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Wbp, Bad, Revision, Assets));
		TestEqual(TEXT("unknown widget type refused"), C.Reason, FString(TEXT("TYPE_NOT_ALLOWED")));
	}
	C = H.Call(TEXT("export_widget_spec"), FString::Printf(TEXT(R"({"asset_path":"%s"})"), *Wbp));
	TestEqual(TEXT("refusals left the blueprint unchanged"), C.bOk ? C.Result->GetStringField(TEXT("revision")) : FString(), Revision);

	// patch
	C = H.Call(TEXT("apply_widget_patch"), FString::Printf(TEXT(R"({"asset_path":"%s","assets":%s,"patch":{"base_revision":"%s","ops":[{"op":"set","widget":"Swatch","path":"slot.position","value":[430,60]}]}})"),
		*Wbp, *EditorMcpJson::ToString(Assets), *Revision));
	TestTrue(FString::Printf(TEXT("patch ok (%s %s)"), *C.Code, *C.Message), C.bOk);
	const FString AfterPatch = C.bOk ? C.Result->GetStringField(TEXT("revision_after")) : Revision;
	C = H.Call(TEXT("apply_widget_patch"), FString::Printf(TEXT(R"({"asset_path":"%s","patch":{"base_revision":"%s","ops":[{"op":"set","widget":"Swatch","path":"slot.position","value":[0,0]}]}})"), *Wbp, *Revision));
	TestEqual(TEXT("stale patch refused"), C.Code, FString(TEXT("REVISION_MISMATCH")));
	C = H.Call(TEXT("apply_widget_patch"), FString::Printf(TEXT(R"({"asset_path":"%s","patch":{"base_revision":"%s","ops":[{"op":"replace_asset","asset":"frame"}]}})"), *Wbp, *AfterPatch));
	TestEqual(TEXT("replace_asset is pipeline-only"), C.Reason, FString(TEXT("PIPELINE_ONLY")));
	C = H.Call(TEXT("apply_widget_patch"), FString::Printf(TEXT(R"({"asset_path":"%s","patch":{"base_revision":"%s","ops":[{"op":"remove_widget","widget":"Gauge"}]}})"), *Wbp, *AfterPatch));
	TestEqual(TEXT("patch removing a bound widget refused"), C.Reason, FString(TEXT("BINDING_REMOVAL")));

	H.Discard();
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWidgetMcpRenderTest, "WidgetMcp.Tools.Render", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWidgetMcpRenderTest::RunTest(const FString& Parameters)
{
	FHarness H(TEXT("Render"));
	const FString Frame = WritePng(H.DiskDir, TEXT("frame.png"), 200, 50);
	const FString Glow = WritePng(H.DiskDir, TEXT("glow.png"), 64, 32);
	H.Call(TEXT("import_ui_textures"), ImportBody(H.RunPath, Frame, Glow));
	const TSharedRef<FJsonObject> Assets = Json(FString::Printf(TEXT(R"({"frame":"%s/T_frame","glow":"%s/T_glow"})"), *H.RunPath, *H.RunPath));
	const FString Wbp = H.RunPath + TEXT("/WBP_Render");
	FCall C = H.Call(TEXT("create_widget_blueprint"), FString::Printf(TEXT(R"({"asset_path":"%s","parent_class":"%s"})"), *Wbp, *UWidgetMcpTestHud::StaticClass()->GetPathName()));
	if (!TestTrue(TEXT("create ok"), C.bOk)) { H.Discard(); return true; }
	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Wbp, Json(SpecA), C.Result->GetStringField(TEXT("revision")), Assets));
	if (!TestTrue(FString::Printf(TEXT("apply ok (%s %s)"), *C.Code, *C.Message), C.bOk)) { H.Discard(); return true; }

	const FString OutA = FPaths::Combine(H.DiskDir, TEXT("render_a"));
	C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","resolutions":[[640,360],[800,360]],"probes":[{"id":"swatch","at":[440,80]}],"overrides":{"Label":{"text":"9.9"}}})"),
		*Wbp, *OutA));
	TestTrue(FString::Printf(TEXT("render ok (%s %s)"), *C.Code, *C.Message), C.bOk);
	if (C.bOk)
	{
		const TArray<TSharedPtr<FJsonValue>>& Renders = C.Result->GetArrayField(TEXT("renders"));
		TestEqual(TEXT("two resolutions"), Renders.Num(), 2);
		TestTrue(TEXT("png written"), IFileManager::Get().FileExists(*Renders[0]->AsObject()->GetStringField(TEXT("png"))));
		TMap<FString, TSharedPtr<FJsonObject>> Geo;
		for (const TSharedPtr<FJsonValue>& V : Renders[0]->AsObject()->GetArrayField(TEXT("geometry"))) { Geo.Add(V->AsObject()->GetStringField(TEXT("id")), V->AsObject()); }
		auto Check = [this, &Geo](const TCHAR* Id, double X, double Y, double W, double Hh)
		{
			const TSharedPtr<FJsonObject>* G = Geo.Find(Id);
			if (!TestTrue(FString::Printf(TEXT("geometry for %s"), Id), G != nullptr)) { return; }
			const double Err = FMath::Max(FMath::Max(FMath::Abs((*G)->GetNumberField(TEXT("x")) - X), FMath::Abs((*G)->GetNumberField(TEXT("y")) - Y)),
				FMath::Max(FMath::Abs((*G)->GetNumberField(TEXT("w")) - W), FMath::Abs((*G)->GetNumberField(TEXT("h")) - Hh)));
			TestTrue(FString::Printf(TEXT("%s geometry within 0.5 px (err %.3f)"), Id, Err), Err <= 0.5);
		};
		Check(TEXT("Panel"), 40, 40, 320, 140);
		Check(TEXT("PanelBox"), 48, 46, 304, 128);
		Check(TEXT("Swatch"), 400, 40, 80, 80);
		Check(TEXT("GaugeArea"), 170, 310, 300, 30);
		Check(TEXT("Gauge"), 176, 316, 288, 18);
		TestFalse(TEXT("collapsed Glow is not visible"), Geo.Contains(TEXT("Glow")) && Geo[TEXT("Glow")]->GetBoolField(TEXT("visible")));
		// A6-색: 지정색 #202838 이 보정 뒤 ±2 안
		const TArray<TSharedPtr<FJsonValue>>& Probes = C.Result->GetArrayField(TEXT("probes"));
		if (TestEqual(TEXT("one probe"), Probes.Num(), 1))
		{
			const FString Hex = Probes[0]->AsObject()->GetStringField(TEXT("color"));
			const FColor Got = FColor::FromHex(Hex);
			const bool bClose = FMath::Abs(Got.R - 0x20) <= 2 && FMath::Abs(Got.G - 0x28) <= 2 && FMath::Abs(Got.B - 0x38) <= 2;
			TestTrue(FString::Printf(TEXT("swatch color %s ~= #202838 after the sRGB->linear correction"), *Hex), bClose);
		}
		// 21:9 비슷한 넓이 — 아래 가운데 앵커는 따라 움직인다
		TMap<FString, TSharedPtr<FJsonObject>> Wide;
		for (const TSharedPtr<FJsonValue>& V : Renders[1]->AsObject()->GetArrayField(TEXT("geometry"))) { Wide.Add(V->AsObject()->GetStringField(TEXT("id")), V->AsObject()); }
		TestTrue(TEXT("bottom-center anchor follows the width"), Wide.Contains(TEXT("GaugeArea")) && FMath::IsNearlyEqual(Wide[TEXT("GaugeArea")]->GetNumberField(TEXT("x")), 250.0, 0.5));
	}

	const FString OutB = FPaths::Combine(H.DiskDir, TEXT("render_b"));
	C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","resolutions":[[640,360]],"force_visible":true})"), *Wbp, *OutB));
	TestTrue(TEXT("force_visible render ok"), C.bOk);
	if (C.bOk)
	{
		bool bGlowVisible = false;
		for (const TSharedPtr<FJsonValue>& V : C.Result->GetArrayField(TEXT("renders"))[0]->AsObject()->GetArrayField(TEXT("geometry")))
		{
			if (V->AsObject()->GetStringField(TEXT("id")) == TEXT("Glow")) { bGlowVisible = V->AsObject()->GetBoolField(TEXT("visible")); }
		}
		TestTrue(TEXT("force_visible shows collapsed widgets"), bGlowVisible);
	}
	C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s"})"), *Wbp, *OutA));
	TestEqual(TEXT("non-empty output_dir refused"), C.Reason, FString(TEXT("OUTPUT_DIR_NOT_EMPTY")));
	C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"Saved/WidgetMcpRender"})"), *Wbp));
	TestEqual(TEXT("output outside WidgetRenderOutputRoots"), C.Reason, FString(TEXT("DISK_ROOT")));
	H.Discard();
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWidgetMcpGuardTest, "WidgetMcp.Tools.Guard", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWidgetMcpGuardTest::RunTest(const FString& Parameters)
{
	// 설정 — 마운트 루트는 허용 목록이 될 수 없다
	{
		FConfigFile File;
		File.CombineFromBuffer(TEXT("[WidgetMcp]\n+WidgetOutputPaths=/Game/\n+WidgetOutputPaths=/Game/_AutoGen\n+WidgetRenderOutputRoots=Tools/uigen/work/\n"), TEXT("WidgetMcpGuardTest"));
		const WidgetMcp::FSettings S = WidgetMcp::LoadSettingsFromFile(File);
		TestEqual(TEXT("only the folder prefix survives"), S.OutputPaths.Num(), 1);
		TestEqual(TEXT("normalized prefix"), S.OutputPaths.Num() ? S.OutputPaths[0] : FString(), FString(TEXT("/Game/_AutoGen/")));
		TestEqual(TEXT("mount root warned"), S.Warnings.Num(), 1);
		TestEqual(TEXT("render root resolved"), S.RenderRoots.Num(), 1);
	}
	const WidgetMcp::FSettings Live = WidgetMcp::LoadSettings();
	TestTrue(TEXT("project config allows /Game/_AutoGen/"), Live.OutputPaths.Contains(TEXT("/Game/_AutoGen/")));

	FHarness H(TEXT("Guard"));
	const FString Wbp = H.RunPath + TEXT("/WBP_Guard");
	FCall C = H.Call(TEXT("create_widget_blueprint"), TEXT(R"({"asset_path":"/Game/UI/WBP_WidgetMcpNotAllowed"})"));
	TestEqual(TEXT("create outside WidgetOutputPaths"), C.Code, FString(TEXT("OUTPUT_PATH_NOT_ALLOWED")));
	C = H.Call(TEXT("create_widget_blueprint"), FString::Printf(TEXT(R"({"asset_path":"%s","parent_class":"%s"})"), *Wbp, *UWidgetMcpTestAbstractHud::StaticClass()->GetPathName()));
	TestEqual(TEXT("abstract parent (ViewBase) refused"), C.Code, FString(TEXT("TYPE_NOT_ALLOWED")));
	C = H.Call(TEXT("create_widget_blueprint"), FString::Printf(TEXT(R"({"asset_path":"%s"})"), *Wbp));
	TestTrue(TEXT("create with the default UserWidget parent"), C.bOk);
	C = H.Call(TEXT("create_widget_blueprint"), FString::Printf(TEXT(R"({"asset_path":"%s"})"), *Wbp));
	TestEqual(TEXT("overwrite refused"), C.Code, FString(TEXT("ASSET_EXISTS")));
	C = H.Call(TEXT("save_widget_run"), TEXT(R"({"run_path":"/Game/_AutoGen"})"));
	TestEqual(TEXT("saving the whole prefix refused"), C.Code, FString(TEXT("OUTPUT_PATH_NOT_ALLOWED")));
	C = H.Call(TEXT("discard_run_packages"), TEXT(R"({"run_path":"/Game/UI"})"));
	TestEqual(TEXT("discarding outside refused"), C.Code, FString(TEXT("OUTPUT_PATH_NOT_ALLOWED")));
	C = H.Call(TEXT("list_bind_widgets"), FString::Printf(TEXT(R"({"class":"%s"})"), *UWidgetMcpTestHud::StaticClass()->GetPathName()));
	TestTrue(TEXT("list_bind_widgets ok"), C.bOk);
	if (C.bOk)
	{
		const TArray<TSharedPtr<FJsonValue>>& B = C.Result->GetArrayField(TEXT("bindings"));
		TestEqual(TEXT("two bindings"), B.Num(), 2);
		if (B.Num() == 2)
		{
			TestEqual(TEXT("Gauge first (by name)"), B[0]->AsObject()->GetStringField(TEXT("name")), FString(TEXT("Gauge")));
			TestFalse(TEXT("Gauge required"), B[0]->AsObject()->GetBoolField(TEXT("optional")));
			TestEqual(TEXT("Gauge is a ProgressBar"), B[0]->AsObject()->GetStringField(TEXT("widget_class")), FString(TEXT("ProgressBar")));
			TestTrue(TEXT("Label optional"), B[1]->AsObject()->GetBoolField(TEXT("optional")));
		}
	}
	C = H.Call(TEXT("compile_widget_blueprint"), FString::Printf(TEXT(R"({"asset_path":"%s"})"), *Wbp));
	TestTrue(TEXT("compile of the empty canvas ok"), C.bOk && C.Result->GetBoolField(TEXT("ok")));
	H.Discard();
	TestNull(TEXT("discarded blueprint is gone"), FindObject<UWidgetBlueprint>(nullptr, *(Wbp + TEXT(".WBP_Guard"))));
	return true;
}

// import_font_family (1b-3) — 엔진 Roboto 두 파일을 시험 폴더로 복사해 임포트한다. 성공 경로는 코어를 직접 불러 WidgetFontOutputPaths 를
// run 접두(/Game/_AutoGen/)로 바꾼 설정 · save=false 로(프로젝트 폰트 폴더에 시험 애셋을 만들지 않게), 거부 경로는 디스패처 + 실제 ini 로.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWidgetMcpImportFontTest, "WidgetMcp.Tools.ImportFont", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWidgetMcpImportFontTest::RunTest(const FString& Parameters)
{
	{
		FConfigFile File;
		File.CombineFromBuffer(TEXT("[WidgetMcp]\n+WidgetFontOutputPaths=/Game/\n+WidgetFontOutputPaths=/Game/UI/Fonts\n"), TEXT("WidgetMcpFontTest"));
		const WidgetMcp::FSettings S = WidgetMcp::LoadSettingsFromFile(File);
		TestTrue(TEXT("font prefix normalized, mount root dropped"), S.FontOutputPaths.Num() == 1 && S.FontOutputPaths[0] == TEXT("/Game/UI/Fonts/"));
		TestEqual(TEXT("mount root warned"), S.Warnings.Num(), 1);
	}
	TestTrue(TEXT("project config allows /Game/UI/Fonts/ for fonts"), WidgetMcp::LoadSettings().FontOutputPaths.Contains(TEXT("/Game/UI/Fonts/")));

	FHarness H(TEXT("Font"));
	const FString EngineFonts = FPaths::Combine(FPaths::EngineContentDir(), TEXT("Slate/Fonts"));
	const FString Regular = FPaths::Combine(H.DiskDir, TEXT("Roboto-Regular.ttf"));
	const FString Bold = FPaths::Combine(H.DiskDir, TEXT("Roboto-Bold.ttf"));
	TestEqual(TEXT("copy regular"), IFileManager::Get().Copy(*Regular, *FPaths::Combine(EngineFonts, TEXT("Roboto-Regular.ttf"))), (uint32)COPY_OK);
	TestEqual(TEXT("copy bold"), IFileManager::Get().Copy(*Bold, *FPaths::Combine(EngineFonts, TEXT("Roboto-Bold.ttf"))), (uint32)COPY_OK);

	WidgetMcp::FSettings S = WidgetMcp::LoadSettings();
	S.FontOutputPaths = { TEXT("/Game/_AutoGen/") };
	WidgetMcpFonts::FRequest R;
	R.DestFolder = H.RunPath + TEXT("/Fonts");
	R.Family = TEXT("TestRoboto");
	R.Faces = { { Regular, TEXT("Regular") }, { Bold, TEXT("Bold") } };
	R.bSave = false;
	const FEditorMcpRequest Req(FName(TEXT("import_font_family")), TEXT("test"), MakeShared<FJsonObject>());
	FEditorMcpContext Ctx(Req);
	FEditorMcpError Err;
	const TSharedPtr<FJsonObject> Out = WidgetMcpFonts::ImportFamily(S, R, Ctx, Err);
	TestTrue(FString::Printf(TEXT("import ok (%s %s)"), *Err.Code, *Err.Message), Out.IsValid());
	if (Out.IsValid())
	{
		TestEqual(TEXT("typefaces in order"), Out->GetArrayField(TEXT("typefaces")).Num(), 2);
		const FString FamilyPath = Out->GetStringField(TEXT("family_asset"));
		TestEqual(TEXT("family asset path"), WidgetMcp::ToPackagePath(FamilyPath), R.DestFolder + TEXT("/F_TestRoboto"));
		const UFont* Font = LoadObject<UFont>(nullptr, *FamilyPath);
		TestNotNull(TEXT("family loads"), Font);
		if (Font)
		{
			TestTrue(TEXT("runtime cache"), Font->FontCacheType == EFontCacheType::Runtime);
			const TArray<FTypefaceEntry>& Fonts = Font->GetInternalCompositeFont().DefaultTypeface.Fonts;
			TestEqual(TEXT("two typeface entries"), Fonts.Num(), 2);
			if (Fonts.Num() == 2)
			{
				TestTrue(TEXT("Regular entry"), Fonts[0].Name == FName(TEXT("Regular")));
				TestTrue(TEXT("Bold entry"), Fonts[1].Name == FName(TEXT("Bold")));
				const UFontFace* Face = Cast<const UFontFace>(Fonts[1].Font.GetFontFaceAsset());
				TestTrue(TEXT("Bold entry points at FF_TestRoboto_Bold with data"), Face && Face->GetName() == TEXT("FF_TestRoboto_Bold") && Face->GetFontFaceData()->HasData());
			}
		}
		for (const TSharedPtr<FJsonValue>& V : Out->GetArrayField(TEXT("faces")))
		{
			TestTrue(TEXT("each face has sub faces"), V->AsObject()->GetArrayField(TEXT("sub_faces")).Num() > 0);
		}
		TestFalse(TEXT("not saved"), Out->GetBoolField(TEXT("saved")));
	}
	TestNull(TEXT("refused import leaves nothing (second call)"), WidgetMcpFonts::ImportFamily(S, R, Ctx, Err).Get());
	TestEqual(TEXT("re-import refused"), Err.Code, FString(TEXT("ASSET_EXISTS")));

	// 거부 경로 — 실제 ini(WidgetFontOutputPaths=/Game/UI/Fonts/)
	auto Body = [&](const FString& Dest, const FString& File, const FString& Typeface)
	{
		return FString::Printf(TEXT(R"({"dest_path":"%s","family":"TestRoboto","faces":[{"file":"%s","typeface":"%s"}],"save":false})"), *Dest, *File, *Typeface);
	};
	FCall C = H.Call(TEXT("import_font_family"), Body(H.RunPath + TEXT("/Fonts2"), Regular, TEXT("Regular")));
	TestEqual(TEXT("run folder is not a font folder"), C.Code, FString(TEXT("OUTPUT_PATH_NOT_ALLOWED")));
	C = H.Call(TEXT("import_font_family"), Body(TEXT("/Game/UI/Fonts"), Regular, TEXT("Regular")));
	TestEqual(TEXT("the font prefix itself is refused"), C.Code, FString(TEXT("OUTPUT_PATH_NOT_ALLOWED")));
	C = H.Call(TEXT("import_font_family"), Body(TEXT("/Game/UI/Fonts/_WidgetMcpTestNever"), Regular, TEXT("Medium")));
	TestEqual(TEXT("typeface outside the weight vocabulary"), C.Reason, FString(TEXT("BAD_TYPEFACE")));
	C = H.Call(TEXT("import_font_family"), Body(TEXT("/Game/UI/Fonts/_WidgetMcpTestNever"), TEXT("Saved/nope.ttf"), TEXT("Regular")));
	TestEqual(TEXT("file outside WidgetImportSourceRoots"), C.Reason, FString(TEXT("DISK_ROOT")));
	TestFalse(TEXT("nothing created under the project font folder"), WidgetMcp::PackageExists(TEXT("/Game/UI/Fonts/_WidgetMcpTestNever/F_TestRoboto")));

	H.Discard();
	TestNull(TEXT("discarded family is gone"), FindObject<UFont>(nullptr, *(R.DestFolder + TEXT("/F_TestRoboto.F_TestRoboto"))));
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
