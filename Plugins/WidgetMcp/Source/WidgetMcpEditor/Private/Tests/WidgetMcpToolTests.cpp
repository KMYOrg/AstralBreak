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
#include "Core/WidgetMcpPromote.h"
#include "Engine/Font.h"
#include "Engine/FontFace.h"
#include "HAL/FileManager.h"
#include "ImageCore.h"
#include "ImageUtils.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/DateTime.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/SecureHash.h"
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
      "text": { "source": "dynamic", "data": "label", "sample": "4.2" }, "font": { "size": 28, "weight": "regular", "glow": { "size": 6, "color": "#FFB04880" } }, "overflow": "ellipsis" },
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
		TestFalse(TEXT("no overflow key at the engine default"), FindWidget(C.Result->GetObjectField(TEXT("spec")), TEXT("Title"))->HasField(TEXT("overflow")));
		FString LabelOverflow;
		TestTrue(TEXT("ellipsis round-trips"), FindWidget(C.Result->GetObjectField(TEXT("spec")), TEXT("Label"))->TryGetStringField(TEXT("overflow"), LabelOverflow) && LabelOverflow == TEXT("ellipsis"));
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
	{
		const TSharedRef<FJsonObject> Bad = Json(SpecA);
		FindWidget(Bad, TEXT("Label"))->SetStringField(TEXT("overflow"), TEXT("wrap"));
		C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Wbp, Bad, Revision, Assets));
		TestFalse(TEXT("unknown text overflow refused"), C.bOk);
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

/** 전투 HUD 동작(11-23) — Image brush.wipe: 머티리얼 준비 · 왕복 · 비율 렌더(게임과 같은 길 — 동적 머티리얼) · 거절 */
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWidgetMcpRadialWipeTest, "WidgetMcp.Tools.RadialWipe", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWidgetMcpRadialWipeTest::RunTest(const FString& Parameters)
{
	FHarness H(TEXT("Wipe"));
	TArray<FColor> Pixels;
	Pixels.Init(FColor(232, 181, 74, 255), 100 * 100);
	const FString Solid = FPaths::Combine(H.DiskDir, TEXT("solid.png"));
	FImageUtils::SaveImageByExtension(*Solid, FImageView(Pixels.GetData(), 100, 100, EGammaSpace::sRGB));
	FCall C = H.Call(TEXT("import_ui_textures"), FString::Printf(TEXT(R"({"dest_path":"%s","textures":[{"file":"%s","name":"T_ring"}]})"), *H.RunPath, *Solid));
	TestTrue(TEXT("texture imported"), C.bOk);
	const TSharedRef<FJsonObject> Assets = Json(FString::Printf(TEXT(R"({"ring":"%s/T_ring"})"), *H.RunPath));
	const FString Wbp = H.RunPath + TEXT("/WBP_Wipe");
	C = H.Call(TEXT("create_widget_blueprint"), FString::Printf(TEXT(R"({"asset_path":"%s","parent_class":"/Script/UMG.UserWidget"})"), *Wbp));
	if (!TestTrue(FString::Printf(TEXT("create ok (%s %s)"), *C.Code, *C.Message), C.bOk)) { H.Discard(); return true; }
	FString Revision = C.Result->GetStringField(TEXT("revision"));

	const auto SpecWith = [](const FString& Style)
	{
		return Json(FString::Printf(TEXT(R"({"root":"Root","widgets":[{"id":"Root","type":"CanvasPanel"},{"id":"Ring","type":"Image","parent":"Root","slot":{"kind":"canvas","position":[100,40],"size":[100,100]},"style":%s}]})"), *Style));
	};
	const FString Good = TEXT(R"({"brush":{"asset":"ring","wipe":{"kind":"radial","mode":"clockwise","center":[50,50],"track_alpha":0.25}},"percent":1})");

	// 거절 — 잘못된 닦기는 아무것도 만들지 않는다
	struct FBad { const TCHAR* What; const TCHAR* Style; };
	const FBad Bad[] = {
		{ TEXT("percent without wipe"), TEXT(R"({"brush":{"asset":"ring"},"percent":0.5})") },
		{ TEXT("unknown mode"), TEXT(R"({"brush":{"asset":"ring","wipe":{"kind":"radial","mode":"spiral","center":[50,50]}}})") },
		{ TEXT("no center"), TEXT(R"({"brush":{"asset":"ring","wipe":{"kind":"radial","mode":"mirror"}}})") },
		{ TEXT("wipe without a texture"), TEXT(R"({"brush":{"draw_as":"image","wipe":{"center":[50,50]}}})") },
	};
	for (const FBad& B : Bad)
	{
		C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Wbp, SpecWith(B.Style), Revision, Assets));
		TestFalse(FString::Printf(TEXT("refused: %s"), B.What), C.bOk);
	}

	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Wbp, SpecWith(Good), Revision, Assets));
	if (!TestTrue(FString::Printf(TEXT("apply ok (%s %s)"), *C.Code, *C.Message), C.bOk)) { H.Discard(); return true; }
	Revision = C.Result->GetStringField(TEXT("revision_after"));
	const TArray<TSharedPtr<FJsonValue>>* Materials = nullptr;
	if (TestTrue(TEXT("brush material reported"), C.Result->TryGetArrayField(TEXT("brush_materials"), Materials) && Materials->Num() == 1))
	{
		const TSharedPtr<FJsonObject> M = (*Materials)[0]->AsObject();
		TestTrue(TEXT("material is UI domain"), M->GetBoolField(TEXT("ui_domain")));
		TestEqual(TEXT("material has no compile errors"), static_cast<int32>(M->GetNumberField(TEXT("compile_errors"))), 0);
		TestTrue(TEXT("material lives in the run folder"), M->GetStringField(TEXT("path")).StartsWith(H.RunPath + TEXT("/MI_RadialWipe_Ring")));
	}

	// 왕복 — 역추출이 텍스처 · 닦기 · 비율을 되돌린다, 같은 spec 을 다시 적용하면 바뀔 것이 없다
	C = H.Call(TEXT("export_widget_spec"), FString::Printf(TEXT(R"({"asset_path":"%s"})"), *Wbp));
	if (TestTrue(TEXT("export ok"), C.bOk))
	{
		const TSharedPtr<FJsonObject> Ring = FindWidget(C.Result->GetObjectField(TEXT("spec")), TEXT("Ring"));
		const TSharedPtr<FJsonObject> Style = Ring.IsValid() ? Ring->GetObjectField(TEXT("style")) : nullptr;
		const TSharedPtr<FJsonObject>* Wipe = nullptr;
		if (TestTrue(TEXT("exported ring has a wipe"), Style.IsValid() && Style->GetObjectField(TEXT("brush"))->TryGetObjectField(TEXT("wipe"), Wipe)))
		{
			TestEqual(TEXT("wipe mode"), (*Wipe)->GetStringField(TEXT("mode")), FString(TEXT("clockwise")));
			TestEqual(TEXT("wipe center x"), (*Wipe)->GetArrayField(TEXT("center"))[0]->AsNumber(), 50.0);
			TestEqual(TEXT("wipe track alpha"), (*Wipe)->GetNumberField(TEXT("track_alpha")), 0.25);
			TestEqual(TEXT("percent"), Style->GetNumberField(TEXT("percent")), 1.0);
			TestEqual(TEXT("brush texture"), WidgetMcp::ToPackagePath(Style->GetObjectField(TEXT("brush"))->GetStringField(TEXT("asset"))), H.RunPath + TEXT("/T_ring"));
		}
	}
	C = H.Call(TEXT("preview_widget_spec"), ApplyBody(H, Wbp, SpecWith(Good), FString(), Assets));
	TestTrue(TEXT("the same spec previews no ops"), C.bOk && C.Result->GetArrayField(TEXT("ops")).Num() == 0);

	// 렌더 — 100 % 는 이미지 브러시와 같은 색, 0 % 는 흔적(25 %), 50 % 는 오른쪽 반(12시에서 시계 방향으로 반 바퀴)만 흔적
	struct FState { double Percent; bool bLeftKept; bool bRightKept; };
	const FState States[] = { { 1.0, true, true }, { 0.5, true, false }, { 0.0, false, false } };
	for (const FState& St : States)
	{
		const FString Out = FPaths::Combine(H.DiskDir, FString::Printf(TEXT("render_%03d"), FMath::RoundToInt(St.Percent * 100.0)));
		C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","resolutions":[[320,200]],"probes":[{"id":"left","at":[120,90]},{"id":"right","at":[180,90]}],"overrides":{"Ring":{"percent":%g}}})"),
			*Wbp, *Out, St.Percent));
		if (!TestTrue(FString::Printf(TEXT("render %.2f ok (%s %s)"), St.Percent, *C.Code, *C.Message), C.bOk)) { continue; }
		const TArray<TSharedPtr<FJsonValue>>& Probes = C.Result->GetArrayField(TEXT("probes"));
		if (!TestEqual(TEXT("two probes"), Probes.Num(), 2)) { continue; }
		for (int32 i = 0; i < 2; ++i)
		{
			const bool bKept = i == 0 ? St.bLeftKept : St.bRightKept;
			const double K = bKept ? 1.0 : 0.25;
			const FString Hex = Probes[i]->AsObject()->GetStringField(TEXT("color"));
			const FColor Got = FColor::FromHex(Hex);
			const bool bClose = FMath::Abs(Got.R - 232.0 * K) <= 3.0 && FMath::Abs(Got.G - 181.0 * K) <= 3.0 && FMath::Abs(Got.B - 74.0 * K) <= 3.0;
			TestTrue(FString::Printf(TEXT("percent %.2f %s probe %s ~= %.0f %% of #E8B54A"), St.Percent, i == 0 ? TEXT("left") : TEXT("right"), *Hex, K * 100.0), bClose);
		}
	}
	// 렌더 덮어쓰기는 인스턴스의 동적 머티리얼만 움직인다 — 애셋은 그대로
	C = H.Call(TEXT("export_widget_spec"), FString::Printf(TEXT(R"({"asset_path":"%s"})"), *Wbp));
	TestTrue(TEXT("revision unchanged after renders"), C.bOk && C.Result->GetStringField(TEXT("revision")) == Revision);

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

	// 상태 묶음(uigen Phase 2) — 상태마다 한 장씩 부른 것과 PNG 가 바이트까지 같고, 이름 · 섞어 쓰기 · 빈 폴더를 지킨다
	{
		const TPair<FString, FString> Cases[] = {
			{ TEXT("plain"), TEXT("{}") },
			{ TEXT("label"), TEXT(R"({"Label":{"text":"9.9"}})") },
			{ TEXT("gauge"), TEXT(R"({"Gauge":{"percent":0.15}})") },
			{ TEXT("glow"), TEXT(R"({"Glow":{"visible":true},"Panel":{"visible":false}})") },
		};
		const FString OutS = FPaths::Combine(H.DiskDir, TEXT("render_states"));
		FString List;
		for (const TPair<FString, FString>& St : Cases) { List += FString::Printf(TEXT("%s{\"name\":\"%s\",\"overrides\":%s}"), List.IsEmpty() ? TEXT("") : TEXT(","), *St.Key, *St.Value); }
		const FCall Batch = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","resolutions":[[640,360]],"states":[%s]})"), *Wbp, *OutS, *List));
		if (TestTrue(FString::Printf(TEXT("states render ok (%s %s)"), *Batch.Code, *Batch.Message), Batch.bOk))
		{
			const TArray<TSharedPtr<FJsonValue>>& States = Batch.Result->GetArrayField(TEXT("states"));
			TestEqual(TEXT("one result per state"), States.Num(), static_cast<int32>(UE_ARRAY_COUNT(Cases)));
			TSet<FString> Hashes;
			for (int32 i = 0; i < States.Num() && i < static_cast<int32>(UE_ARRAY_COUNT(Cases)); ++i)
			{
				TestEqual(TEXT("state order kept"), States[i]->AsObject()->GetStringField(TEXT("name")), Cases[i].Key);
				const FString BatchPng = States[i]->AsObject()->GetArrayField(TEXT("renders"))[0]->AsObject()->GetStringField(TEXT("png"));
				const FString OutOne = FPaths::Combine(H.DiskDir, TEXT("render_one_") + Cases[i].Key);
				C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","resolutions":[[640,360]],"overrides":%s})"), *Wbp, *OutOne, *Cases[i].Value));
				if (!TestTrue(FString::Printf(TEXT("single render of '%s' ok"), *Cases[i].Key), C.bOk)) { continue; }
				TArray<uint8> A, B;
				const bool bRead = FFileHelper::LoadFileToArray(A, *BatchPng) && FFileHelper::LoadFileToArray(B, *C.Result->GetArrayField(TEXT("renders"))[0]->AsObject()->GetStringField(TEXT("png")));
				TestTrue(FString::Printf(TEXT("state '%s' PNG is byte-identical to the single render"), *Cases[i].Key), bRead && A.Num() > 0 && A == B);
				Hashes.Add(FMD5::HashBytes(A.GetData(), A.Num()));
			}
			TestEqual(TEXT("the four states are different pictures"), Hashes.Num(), static_cast<int32>(UE_ARRAY_COUNT(Cases)));
		}
		C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","states":[{"name":"plain"}]})"), *Wbp, *OutS));
		TestEqual(TEXT("non-empty state folder refused"), C.Reason, FString(TEXT("OUTPUT_DIR_NOT_EMPTY")));
		C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","states":[{"name":"twice"},{"name":"Twice"}]})"), *Wbp, *OutS));
		TestEqual(TEXT("duplicate state name refused"), C.Reason, FString(TEXT("STATE_NAME")));
		C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","states":[{"name":"../up"}]})"), *Wbp, *OutS));
		TestEqual(TEXT("state name that leaves the folder refused"), C.Reason, FString(TEXT("STATE_NAME")));
		C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","states":[{"name":"mixed"}],"overrides":{"Label":{"text":"1"}}})"), *Wbp, *OutS));
		TestEqual(TEXT("states with overrides refused"), C.Reason, FString(TEXT("STATES_WITH_OVERRIDES")));
	}
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

// 버튼 칸(uigen Phase 3-2) — 스타일 애셋 · 클래스 기본값 · 상태 일곱 렌더 · 안 먹은 덮어쓰기 = 오류 · 칸을 다른 화면에 놓기(UserWidget)
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWidgetMcpButtonCellTest, "WidgetMcp.Tools.ButtonCell", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWidgetMcpButtonCellTest::RunTest(const FString& Parameters)
{
	FHarness H(TEXT("Button"));
	struct FBrush { const TCHAR* Name; FColor Color; const TCHAR* Override; };
	const FBrush Brushes[] = {
		{ TEXT("normal_base"), FColor(200, 0, 0), TEXT("{}") }, { TEXT("normal_hovered"), FColor(0, 200, 0), TEXT(R"({".":{"button":"hovered"}})") },
		{ TEXT("normal_pressed"), FColor(0, 0, 200), TEXT(R"({".":{"button":"pressed"}})") }, { TEXT("selected_base"), FColor(200, 200, 0), TEXT(R"({".":{"button":"selected"}})") },
		{ TEXT("selected_hovered"), FColor(0, 200, 200), TEXT(R"({".":{"button":"selected_hovered"}})") },
		{ TEXT("selected_pressed"), FColor(200, 0, 200), TEXT(R"({".":{"button":"selected_pressed"}})") }, { TEXT("disabled"), FColor(120, 120, 120), TEXT(R"({".":{"enabled":false}})") },
	};
	FString Textures, AssetMap, BrushJson;
	for (const FBrush& B : Brushes)
	{
		TArray<FColor> Pixels;
		Pixels.Init(B.Color, 120 * 40);
		const FString File = FPaths::Combine(H.DiskDir, FString(B.Name) + TEXT(".png"));
		FImageUtils::SaveImageByExtension(*File, FImageView(Pixels.GetData(), 120, 40, EGammaSpace::sRGB));
		const TCHAR* Comma = Textures.IsEmpty() ? TEXT("") : TEXT(",");
		Textures += FString::Printf(TEXT("%s{\"file\":\"%s\",\"name\":\"T_%s\"}"), Comma, *File, B.Name);
		AssetMap += FString::Printf(TEXT("%s\"%s\":\"%s/T_%s\""), Comma, B.Name, *H.RunPath, B.Name);
		BrushJson += FString::Printf(TEXT("%s\"%s\":{\"asset\":\"%s\"}"), Comma, B.Name, B.Name);
	}
	FCall C = H.Call(TEXT("import_ui_textures"), FString::Printf(TEXT(R"({"dest_path":"%s","textures":[%s]})"), *H.RunPath, *Textures));
	if (!TestTrue(FString::Printf(TEXT("textures imported (%s %s)"), *C.Code, *C.Message), C.bOk)) { H.Discard(); return true; }
	const TSharedRef<FJsonObject> Assets = Json(FString::Printf(TEXT("{%s}"), *AssetMap));
	const FString StylePath = H.RunPath + TEXT("/BS_Button");
	const FString StyleParent = UWidgetMcpTestButtonStyle::StaticClass()->GetPathName();
	const auto StyleBody = [&](const FString& BrushList, const FString& Extra)
	{
		return FString::Printf(TEXT(R"({"asset_path":"%s","parent_class":"%s","brushes":{%s},"assets":%s%s})"), *StylePath, *StyleParent, *BrushList, *EditorMcpJson::ToString(Assets), *Extra);
	};
	const FString Size = TEXT(R"(,"min_size":[120,40])");

	// 거절 — 하나라도 비면 아무것도 안 만든다
	C = H.Call(TEXT("create_button_style"), StyleBody(BrushJson.Replace(TEXT(",\"disabled\":{\"asset\":\"disabled\"}"), TEXT("")), Size));
	TestEqual(TEXT("a missing Disabled brush is refused"), C.Reason, FString(TEXT("BRUSH_MISSING")));
	C = H.Call(TEXT("create_button_style"), StyleBody(BrushJson.Replace(TEXT("\"disabled\":{\"asset\":\"disabled\"}"), TEXT("\"disabled\":{\"draw_as\":\"none\"}")), Size));
	TestEqual(TEXT("an empty Disabled brush is refused"), C.Reason, FString(TEXT("BRUSH_EMPTY")));
	C = H.Call(TEXT("create_button_style"), StyleBody(BrushJson, Size + TEXT(R"(,"props":{"Nope":1})")));
	TestEqual(TEXT("an unknown style property is refused"), C.Reason, FString(TEXT("PROP")));
	C = H.Call(TEXT("create_button_style"), StyleBody(BrushJson, TEXT("")));
	TestEqual(TEXT("no size is refused"), C.Reason, FString(TEXT("MIN_SIZE")));
	TestFalse(TEXT("nothing was created by the refused calls"), WidgetMcp::PackageExists(StylePath));

	C = H.Call(TEXT("create_button_style"), StyleBody(BrushJson, Size + TEXT(R"(,"props":{"PressedTextOffset":[0,1]})")));
	if (!TestTrue(FString::Printf(TEXT("style ok (%s %s)"), *C.Code, *C.Message), C.bOk)) { H.Discard(); return true; }
	TestEqual(TEXT("seven brushes read back"), C.Result->GetObjectField(TEXT("brushes"))->Values.Num(), 7);
	TestEqual(TEXT("extra property read back"), C.Result->GetObjectField(TEXT("props"))->GetArrayField(TEXT("PressedTextOffset"))[1]->AsNumber(), 1.0);
	C = H.Call(TEXT("create_button_style"), StyleBody(BrushJson, Size));
	TestEqual(TEXT("rewriting needs replace"), C.Code, FString(TEXT("ASSET_EXISTS")));
	C = H.Call(TEXT("create_button_style"), StyleBody(BrushJson, Size + TEXT(R"(,"replace":true,"props":{"PressedTextOffset":[0,2]})")));
	TestTrue(TEXT("replace rewrites the run's own style"), C.bOk && C.Result->GetObjectField(TEXT("props"))->GetArrayField(TEXT("PressedTextOffset"))[1]->AsNumber() == 2.0);

	// 버튼 WBP — 클래스 기본값 Style 은 트리와 한 묶음으로 적용 · 역추출
	const FString Cell = H.RunPath + TEXT("/Cells/WBP_Button");
	C = H.Call(TEXT("create_widget_blueprint"), FString::Printf(TEXT(R"({"asset_path":"%s","parent_class":"%s"})"), *(H.RunPath + TEXT("/WBP_Loose")), *UWidgetMcpTestHud::StaticClass()->GetPathName()));
	const FString LooseRevision = C.bOk ? C.Result->GetStringField(TEXT("revision")) : FString();
	C = H.Call(TEXT("create_widget_blueprint"), FString::Printf(TEXT(R"({"asset_path":"%s","parent_class":"%s"})"), *Cell, *UWidgetMcpTestButton::StaticClass()->GetPathName()));
	if (!TestTrue(FString::Printf(TEXT("button blueprint ok (%s %s)"), *C.Code, *C.Message), C.bOk)) { H.Discard(); return true; }
	FString Revision = C.Result->GetStringField(TEXT("revision"));
	const auto CellSpec = [](const FString& Defaults)
	{
		return Json(FString::Printf(TEXT(R"({"root":"Root","widgets":[{"id":"Root","type":"CanvasPanel"},{"id":"ButtonLabel","type":"TextBlock","parent":"Root","slot":{"kind":"canvas","anchors":[0.5,0.5,0.5,0.5],"alignment":[0.5,0.5],"auto_size":true},"text":{"value":"OK"},"font":{"size":12}}]%s})"),
			*Defaults));
	};
	const FString OtherStyle = FString::Printf(TEXT(R"(,"defaults":{"Style":"%s"})"), *StylePath);
	// 스타일은 WBP 와 같은 폴더이거나 승격 경로여야 한다 — 이 WBP 는 하위 폴더라 거절
	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Cell, CellSpec(OtherStyle), Revision, Assets));
	TestEqual(TEXT("a style outside the blueprint's folder is refused"), C.Reason, FString(TEXT("DEFAULTS")));
	const FString CellStyle = H.RunPath + TEXT("/Cells/BS_Button");
	C = H.Call(TEXT("create_button_style"), StyleBody(BrushJson, Size).Replace(*StylePath, *CellStyle));
	TestTrue(TEXT("style next to the blueprint"), C.bOk);
	const FString Defaults = FString::Printf(TEXT(R"(,"defaults":{"Style":"%s"})"), *CellStyle);
	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Cell, CellSpec(TEXT(R"(,"defaults":{"MinWidth":4})")), Revision, Assets));
	TestEqual(TEXT("only Style can be set"), C.Reason, FString(TEXT("DEFAULTS")));
	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, H.RunPath + TEXT("/WBP_Loose"), CellSpec(Defaults), LooseRevision, Assets));
	TestFalse(TEXT("defaults on a blueprint that is not a button are refused"), C.bOk);
	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Cell, CellSpec(Defaults), Revision, Assets));
	if (!TestTrue(FString::Printf(TEXT("apply ok (%s %s)"), *C.Code, *C.Message), C.bOk)) { H.Discard(); return true; }
	Revision = C.Result->GetStringField(TEXT("revision_after"));
	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Cell, CellSpec(Defaults), Revision, Assets));
	TestTrue(TEXT("idempotent apply"), C.bOk && C.Result->GetArrayField(TEXT("ops")).Num() == 0 && C.Result->GetStringField(TEXT("revision_after")) == Revision);
	// 컴파일을 한 번 더 하지 않아도 새 인스턴스가 이 스타일을 물려받는다
	C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","resolutions":[[120,40]],"probes":[{"id":"corner","at":[5,5]}]})"), *Cell, *FPaths::Combine(H.DiskDir, TEXT("right_after_apply"))));
	if (TestTrue(TEXT("render right after apply ok"), C.bOk))
	{
		const FColor Got = FColor::FromHex(C.Result->GetArrayField(TEXT("probes"))[0]->AsObject()->GetStringField(TEXT("color")));
		TestTrue(FString::Printf(TEXT("the style is drawn right after apply (%s)"), *Got.ToHex()), FMath::Abs(Got.R - Brushes[0].Color.R) <= 2 && FMath::Abs(Got.G - Brushes[0].Color.G) <= 2 && FMath::Abs(Got.B - Brushes[0].Color.B) <= 2);
	}
	C = H.Call(TEXT("compile_widget_blueprint"), FString::Printf(TEXT(R"({"asset_path":"%s"})"), *Cell));
	TestTrue(TEXT("the style survives another compile"), C.bOk && C.Result->GetStringField(TEXT("revision")) == Revision);
	C = H.Call(TEXT("export_widget_spec"), FString::Printf(TEXT(R"({"asset_path":"%s","assets":%s})"), *Cell, *EditorMcpJson::ToString(Assets)));
	if (TestTrue(TEXT("export ok"), C.bOk))
	{
		TestEqual(TEXT("defaults come back"), C.Result->GetObjectField(TEXT("spec"))->GetObjectField(TEXT("defaults"))->GetStringField(TEXT("Style")), CellStyle);
		TestEqual(TEXT("style textures are described"), C.Result->GetArrayField(TEXT("textures")).Num(), 7);
		TestEqual(TEXT("style brush comes back as an asset id"), C.Result->GetObjectField(TEXT("button_style"))->GetObjectField(TEXT("brushes"))->GetObjectField(TEXT("disabled"))->GetStringField(TEXT("asset")), FString(TEXT("disabled")));
	}

	// 상태 일곱 — 진짜 버튼 상태로 그린 색 = 그 상태의 브러시(선택 + 누름까지)
	for (const FBrush& B : Brushes)
	{
		const FString Out = FPaths::Combine(H.DiskDir, FString(TEXT("state_")) + B.Name);
		C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","resolutions":[[120,40]],"probes":[{"id":"corner","at":[5,5]}],"overrides":%s})"), *Cell, *Out, B.Override));
		if (!TestTrue(FString::Printf(TEXT("render %s ok (%s %s)"), B.Name, *C.Code, *C.Message), C.bOk)) { continue; }
		const FString Hex = C.Result->GetArrayField(TEXT("probes"))[0]->AsObject()->GetStringField(TEXT("color"));
		const FColor Got = FColor::FromHex(Hex);
		TestTrue(FString::Printf(TEXT("%s draws its own brush (%s)"), B.Name, *Hex), FMath::Abs(Got.R - B.Color.R) <= 2 && FMath::Abs(Got.G - B.Color.G) <= 2 && FMath::Abs(Got.B - B.Color.B) <= 2);
		const TArray<TSharedPtr<FJsonValue>>& Desired = C.Result->GetArrayField(TEXT("renders"))[0]->AsObject()->GetArrayField(TEXT("desired_size"));
		TestTrue(FString::Printf(TEXT("%s keeps the button size (%.1f x %.1f)"), B.Name, Desired[0]->AsNumber(), Desired[1]->AsNumber()), Desired[0]->AsNumber() == 120.0 && Desired[1]->AsNumber() == 40.0);
	}
	// 안 먹은 덮어쓰기는 오류 — 없는 위젯 · 버튼이 아님 · 모르는 상태 · 꺼진 버튼을 누름
	const TCHAR* const Bad[] = { TEXT(R"({"Nope":{"enabled":false}})"), TEXT(R"({"ButtonLabel":{"button":"hovered"}})"), TEXT(R"({".":{"button":"glowing"}})"), TEXT(R"({".":{"enabled":false,"button":"pressed"}})") };
	for (int32 i = 0; i < static_cast<int32>(UE_ARRAY_COUNT(Bad)); ++i)
	{
		C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","resolutions":[[120,40]],"overrides":%s})"), *Cell, *FPaths::Combine(H.DiskDir, FString::Printf(TEXT("bad_%d"), i)), Bad[i]));
		TestEqual(FString::Printf(TEXT("override %s is an error"), Bad[i]), C.Reason, FString(TEXT("OVERRIDE_NOT_APPLIED")));
	}

	// 칸을 다른 화면에 놓기 — 승격 경로의 클래스만 · 허용한 속성만 · 왕복 · 칸 안까지 덮어쓰기
	TArray<FString> SavedPaths;
	GConfig->GetArray(WidgetMcp::Section, TEXT("WidgetPromotionPaths"), SavedPaths, GEngineIni);
	const FString Screen = H.RunPath + TEXT("/WBP_Screen");
	C = H.Call(TEXT("create_widget_blueprint"), FString::Printf(TEXT(R"({"asset_path":"%s"})"), *Screen));
	TestTrue(TEXT("screen created"), C.bOk);
	const FString ScreenRevision = C.bOk ? C.Result->GetStringField(TEXT("revision")) : FString();
	const auto ScreenSpec = [&Cell](const FString& PropsA)
	{
		return Json(FString::Printf(TEXT(R"({"root":"Root","widgets":[{"id":"Root","type":"CanvasPanel"},
			{"id":"CellA","type":"UserWidget","class":"%s","parent":"Root","slot":{"kind":"canvas","position":[10,10],"size":[120,40],"auto_size":true},"props":%s},
			{"id":"CellB","type":"UserWidget","class":"%s","parent":"Root","slot":{"kind":"canvas","position":[200,10],"size":[120,40]}}]})"), *Cell, *PropsA, *Cell));
	};
	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Screen, ScreenSpec(TEXT(R"({"ButtonText":"GO"})")), ScreenRevision, MakeShared<FJsonObject>()));
	TestEqual(TEXT("a cell outside the promotion paths is refused"), C.Reason, FString(TEXT("CELL_CLASS")));
	{
		TArray<FString> Paths = SavedPaths;
		Paths.Add(H.RunPath + TEXT("/Cells/"));
		GConfig->SetArray(WidgetMcp::Section, TEXT("WidgetPromotionPaths"), Paths, GEngineIni);
	}
	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Screen, ScreenSpec(TEXT(R"({"Style":"x"})")), ScreenRevision, MakeShared<FJsonObject>()));
	TestEqual(TEXT("a property that is not listed is refused"), C.Reason, FString(TEXT("BAD_VALUE")));
	C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Screen, ScreenSpec(TEXT(R"({"ButtonText":"GO"})")), ScreenRevision, MakeShared<FJsonObject>()));
	if (TestTrue(FString::Printf(TEXT("screen apply ok (%s %s)"), *C.Code, *C.Message), C.bOk))
	{
		const FString After = C.Result->GetStringField(TEXT("revision_after"));
		C = H.Call(TEXT("apply_widget_spec"), ApplyBody(H, Screen, ScreenSpec(TEXT(R"({"ButtonText":"GO"})")), After, MakeShared<FJsonObject>()));
		TestTrue(TEXT("idempotent with cells"), C.bOk && C.Result->GetArrayField(TEXT("ops")).Num() == 0);
		C = H.Call(TEXT("compile_widget_blueprint"), FString::Printf(TEXT(R"({"asset_path":"%s"})"), *Screen));
		C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","resolutions":[[400,60]]})"), *Screen, *FPaths::Combine(H.DiskDir, TEXT("cell_texts"))));
		if (TestTrue(TEXT("screen geometry ok"), C.bOk))
		{
			TMap<FString, TSharedPtr<FJsonObject>> Rows;
			for (const TSharedPtr<FJsonValue>& V : C.Result->GetArrayField(TEXT("renders"))[0]->AsObject()->GetArrayField(TEXT("geometry"))) { Rows.Add(V->AsObject()->GetStringField(TEXT("id")), V->AsObject()); }
			const TSharedPtr<FJsonObject>* Inner = Rows.Find(TEXT("CellA/ButtonLabel"));
			TestTrue(TEXT("the label inside a placed cell has its own row"), Inner && (*Inner)->GetStringField(TEXT("parent")) == TEXT("CellA") && (*Inner)->GetStringField(TEXT("type")) == TEXT("TextBlock")
				&& (*Inner)->GetNumberField(TEXT("w")) > 0.0 && (*Inner)->GetNumberField(TEXT("x")) >= 10.0);
			TestFalse(TEXT("only the texts of a cell are listed"), Rows.Contains(TEXT("CellA/InternalRootButtonBase")));
		}
		C = H.Call(TEXT("export_widget_spec"), FString::Printf(TEXT(R"({"asset_path":"%s"})"), *Screen));
		if (TestTrue(TEXT("screen export ok"), C.bOk))
		{
			const TSharedPtr<FJsonObject> A = FindWidget(C.Result->GetObjectField(TEXT("spec")), TEXT("CellA"));
			const TSharedPtr<FJsonObject> B = FindWidget(C.Result->GetObjectField(TEXT("spec")), TEXT("CellB"));
			TestEqual(TEXT("cell type"), A->GetStringField(TEXT("type")), FString(TEXT("UserWidget")));
			TestEqual(TEXT("cell class"), A->GetStringField(TEXT("class")), Cell);
			TestEqual(TEXT("cell property"), A->GetObjectField(TEXT("props"))->GetStringField(TEXT("ButtonText")), FString(TEXT("GO")));
			TestFalse(TEXT("no props when they are the class defaults"), B->HasField(TEXT("props")));
			TestEqual(TEXT("nothing unsupported"), C.Result->GetArrayField(TEXT("unsupported")).Num(), 0);
		}
		C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","resolutions":[[340,60]],"probes":[{"id":"a","at":[15,15]},{"id":"b","at":[205,15]}],"overrides":{"CellA":{"button":"hovered"},"CellB":{"enabled":false},"CellA/ButtonLabel":{"text":"IN"}}})"),
			*Screen, *FPaths::Combine(H.DiskDir, TEXT("screen"))));
		if (TestTrue(FString::Printf(TEXT("screen render ok (%s %s)"), *C.Code, *C.Message), C.bOk))
		{
			const TArray<TSharedPtr<FJsonValue>>& Probes = C.Result->GetArrayField(TEXT("probes"));
			const FColor A = FColor::FromHex(Probes[0]->AsObject()->GetStringField(TEXT("color")));
			const FColor B = FColor::FromHex(Probes[1]->AsObject()->GetStringField(TEXT("color")));
			TestTrue(FString::Printf(TEXT("cell A is hovered (%s)"), *A.ToHex()), A.G > 190 && A.R < 10);
			TestTrue(FString::Printf(TEXT("cell B is disabled (%s)"), *B.ToHex()), FMath::Abs(B.R - 120) <= 2 && FMath::Abs(B.G - 120) <= 2);
			for (const TSharedPtr<FJsonValue>& V : C.Result->GetArrayField(TEXT("renders"))[0]->AsObject()->GetArrayField(TEXT("geometry")))
			{
				if (V->AsObject()->GetStringField(TEXT("id")) == TEXT("CellA"))
				{
					TestEqual(TEXT("geometry names the cell type"), V->AsObject()->GetStringField(TEXT("type")), FString(TEXT("UserWidget")));
					TestEqual(TEXT("an auto-sized cell takes its own width"), V->AsObject()->GetNumberField(TEXT("w")), 120.0);
				}
			}
		}
		C = H.Call(TEXT("render_widget"), FString::Printf(TEXT(R"({"asset_path":"%s","output_dir":"%s","resolutions":[[340,60]],"overrides":{"CellA/Nope":{"enabled":false}}})"), *Screen, *FPaths::Combine(H.DiskDir, TEXT("screen_bad"))));
		TestEqual(TEXT("a wrong path inside a cell is an error"), C.Reason, FString(TEXT("OVERRIDE_NOT_APPLIED")));
	}
	GConfig->SetArray(WidgetMcp::Section, TEXT("WidgetPromotionPaths"), SavedPaths, GEngineIni);

	H.Discard();
	TestNull(TEXT("discarded style is gone"), FindObject<UBlueprint>(nullptr, *(StylePath + TEXT(".BS_Button"))));
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
	// 어휘 밖 굵기 — 1b 후속 K 가 Medium · SemiBold · ExtraBold · Black 을 어휘에 넣어 예전 예('Medium')는 거절되지 않았다(WidgetMcpFonts AllowedTypefaces)
	C = H.Call(TEXT("import_font_family"), Body(TEXT("/Game/UI/Fonts/_WidgetMcpTestNever"), Regular, TEXT("Thin")));
	TestEqual(TEXT("typeface outside the weight vocabulary"), C.Reason, FString(TEXT("BAD_TYPEFACE")));
	C = H.Call(TEXT("import_font_family"), Body(TEXT("/Game/UI/Fonts/_WidgetMcpTestNever"), TEXT("Saved/nope.ttf"), TEXT("Regular")));
	TestEqual(TEXT("file outside WidgetImportSourceRoots"), C.Reason, FString(TEXT("DISK_ROOT")));
	TestFalse(TEXT("nothing created under the project font folder"), WidgetMcp::PackageExists(TEXT("/Game/UI/Fonts/_WidgetMcpTestNever/F_TestRoboto")));

	H.Discard();
	TestNull(TEXT("discarded family is gone"), FindObject<UFont>(nullptr, *(R.DestFolder + TEXT("/F_TestRoboto.F_TestRoboto"))));
	return true;
}

// promote_widget (M4 단위 C 가 앞당긴 최소판) — 거절 경로만 본다. 성공 경로는 run 이 디스크에 저장돼 있어야 해서(엔진 복사는 디스크의 패키지를 읽는다)
// 시험 파일을 남기지 않으려고 여기서 돌리지 않는다 — 실제 승격(L-1 → /Game/UI/HUD/CombatHUD)의 사후 검증과 AstralBreak.Net.CombatHUD.* 가 그 몫이다.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWidgetMcpPromoteTest, "WidgetMcp.Tools.Promote", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)
bool FWidgetMcpPromoteTest::RunTest(const FString& Parameters)
{
	{
		FConfigFile File;
		File.CombineFromBuffer(TEXT("[WidgetMcp]\n+WidgetPromotionPaths=/Game/\n+WidgetPromotionPaths=/Game/UI/HUD\n"), TEXT("WidgetMcpPromoteTest"));
		const WidgetMcp::FSettings S = WidgetMcp::LoadSettingsFromFile(File);
		TestTrue(TEXT("promotion prefix normalized, mount root dropped"), S.PromotionPaths.Num() == 1 && S.PromotionPaths[0] == TEXT("/Game/UI/HUD/"));
		TestEqual(TEXT("mount root warned"), S.Warnings.Num(), 1);
	}
	TestTrue(TEXT("project config allows /Game/UI/HUD/ for promotion"), WidgetMcp::LoadSettings().PromotionPaths.Contains(TEXT("/Game/UI/HUD/")));

	FHarness H(TEXT("Promote"));
	const FString Wbp = H.RunPath + TEXT("/WBP_Promote");
	FCall C = H.Call(TEXT("create_widget_blueprint"), FString::Printf(TEXT(R"({"asset_path":"%s"})"), *Wbp));
	TestTrue(TEXT("an unsaved run blueprint"), C.bOk);

	const FString NeverDest = TEXT("/Game/UI/HUD/_WidgetMcpTestNever");
	auto Body = [](const FString& Run, const FString& Dest, const TCHAR* Extra)
	{
		return FString::Printf(TEXT(R"({"run_path":"%s","dest_path":"%s"%s})"), *Run, *Dest, Extra);
	};
	const TCHAR* const Dry = TEXT(R"(,"dry_run":true)");

	C = H.Call(TEXT("promote_widget"), Body(H.RunPath, NeverDest, TEXT("")));
	TestEqual(TEXT("neither dry_run nor confirm"), C.Reason, FString(TEXT("MISSING_CONFIRM")));
	C = H.Call(TEXT("promote_widget"), Body(TEXT("/Game/UI/Fonts"), NeverDest, Dry));
	TestEqual(TEXT("run outside WidgetOutputPaths"), C.Code, FString(TEXT("OUTPUT_PATH_NOT_ALLOWED")));
	C = H.Call(TEXT("promote_widget"), Body(H.RunPath, TEXT("/Game/UI/_WidgetMcpTestNever"), Dry));
	TestEqual(TEXT("dest outside WidgetPromotionPaths"), C.Reason, FString(TEXT("OUTSIDE_PROMOTION_PATHS")));
	C = H.Call(TEXT("promote_widget"), Body(H.RunPath, TEXT("/Game/UI/HUD"), Dry));
	TestEqual(TEXT("the promotion prefix itself is refused"), C.Reason, FString(TEXT("OUTSIDE_PROMOTION_PATHS")));
	C = H.Call(TEXT("promote_widget"), Body(H.RunPath, H.RunPath + TEXT("/Copy"), Dry));
	TestEqual(TEXT("dest inside the run paths"), C.Reason, FString(TEXT("DEST_IS_RUN_PATH")));
	C = H.Call(TEXT("promote_widget"), Body(H.RunPath, NeverDest, Dry));
	TestEqual(TEXT("a never-saved run is refused"), C.Reason, FString(TEXT("RUN_NOT_SAVED")));

	// dest 가 비어 있지 않음 — 코어를 직접, 승격 접두를 /Game/UI/ 로 바꾼 설정으로 이미 커밋된 /Game/UI/Fonts 를 dest 로 준다(run 검사보다 먼저 본다)
	WidgetMcp::FSettings S = WidgetMcp::LoadSettings();
	S.PromotionPaths = { TEXT("/Game/UI/") };
	WidgetMcpPromote::FRequest R;
	R.RunFolder = H.RunPath;
	R.DestFolder = TEXT("/Game/UI/Fonts");
	R.bDryRun = true;
	const FEditorMcpRequest Req(FName(TEXT("promote_widget")), TEXT("test"), MakeShared<FJsonObject>());
	FEditorMcpContext Ctx(Req);
	FEditorMcpError Err;
	TestNull(TEXT("a non-empty dest is refused"), WidgetMcpPromote::Run(S, R, Ctx, Err).Get());
	TestEqual(TEXT("non-empty dest → ASSET_EXISTS"), Err.Code, FString(TEXT("ASSET_EXISTS")));

	TestFalse(TEXT("nothing created under the promotion folder"), WidgetMcp::PackageExists(NeverDest + TEXT("/WBP_Promote")));
	H.Discard();
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
