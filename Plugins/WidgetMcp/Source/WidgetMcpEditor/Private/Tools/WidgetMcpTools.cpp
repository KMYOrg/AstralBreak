#include "Tools/WidgetMcpTools.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Widget.h"
#include "Core/WidgetMcpBlueprint.h"
#include "Core/WidgetMcpCommon.h"
#include "Core/WidgetMcpRender.h"
#include "Core/WidgetMcpRunPackages.h"
#include "Core/WidgetMcpSpec.h"
#include "Core/WidgetMcpTextures.h"
#include "Engine/Texture2D.h"
#include "Misc/PackageName.h"
#include "WidgetBlueprint.h"

namespace WidgetMcpTools
{
	namespace ToolsPrivate
	{
		TSharedPtr<FJsonObject> ObjectParam(const FEditorMcpContext& Context, const TCHAR* Key)
		{
			const TSharedPtr<FJsonObject>* O = nullptr;
			return Context.Request.Params->TryGetObjectField(Key, O) ? *O : nullptr;
		}

		bool LoadAssetsParam(const FEditorMcpContext& Context, WidgetMcpSpec::FAssets& Assets, FEditorMcpError& OutError)
		{
			return WidgetMcpSpec::LoadAssets(ObjectParam(Context, TEXT("assets")), Assets, OutError);
		}

		UWidgetBlueprint* LoadWbpParam(const FEditorMcpContext& Context, FEditorMcpError& OutError)
		{
			FString AssetPath;
			if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError))
			{
				return nullptr;
			}
			return WidgetMcpBlueprint::Load(AssetPath, OutError);
		}

		bool ReadIntPair(const TSharedPtr<FJsonValue>& V, FIntPoint& Out)
		{
			const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
			if (!V.IsValid() || !V->TryGetArray(A) || A->Num() != 2)
			{
				return false;
			}
			Out = FIntPoint(FMath::RoundToInt((*A)[0]->AsNumber()), FMath::RoundToInt((*A)[1]->AsNumber()));
			return true;
		}

		TSharedPtr<FJsonObject> ExportResult(UWidgetBlueprint* WBP, const WidgetMcpSpec::FAssets& Assets, bool bUseAssetIds)
		{
			TArray<TSharedPtr<FJsonValue>> Unsupported;
			TArray<FString> Locked;
			TSharedRef<FJsonObject> Tree = WidgetMcpBlueprint::ExportTree(WBP->WidgetTree, bUseAssetIds ? &Assets : nullptr, Unsupported, Locked);
			TSharedRef<FJsonObject> Spec = MakeShared<FJsonObject>();
			Spec->SetNumberField(TEXT("schema_version"), 1);
			Spec->SetStringField(TEXT("root"), Tree->GetStringField(TEXT("root")));
			Spec->SetArrayField(TEXT("widgets"), Tree->GetArrayField(TEXT("widgets")));
			Spec->SetArrayField(TEXT("locked"), WidgetMcp::StringArray(Locked));
			TArray<UTexture2D*> Textures;
			WBP->WidgetTree->ForEachWidget([&Textures](UWidget* W) { WidgetMcpSpec::CollectTextures(W, Textures); });
			Textures.Sort([](const UTexture2D& A, const UTexture2D& B) { return A.GetPathName() < B.GetPathName(); });
			TArray<TSharedPtr<FJsonValue>> TextureJson;
			for (const UTexture2D* T : Textures) { TextureJson.Add(MakeShared<FJsonValueObject>(WidgetMcpTextures::Describe(T))); }
			TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
			Out->SetStringField(TEXT("asset_path"), WBP->GetPathName());
			Out->SetStringField(TEXT("parent_class"), GetPathNameSafe(WBP->ParentClass));
			Out->SetObjectField(TEXT("spec"), Spec);
			Out->SetStringField(TEXT("revision"), WidgetMcpBlueprint::Revision(WBP));
			Out->SetArrayField(TEXT("unsupported"), Unsupported);
			Out->SetArrayField(TEXT("textures"), TextureJson);
			Out->SetArrayField(TEXT("bindings"), WidgetMcpBlueprint::BindWidgetsJson(WidgetMcpBlueprint::BindWidgets(WBP->ParentClass)));
			Out->SetNumberField(TEXT("guid_map_count"), WBP->WidgetVariableNameToGuidMap.Num());
			int32 WidgetCount = 0;
			TArray<FString> MissingGuid;
			WBP->WidgetTree->ForEachWidget([&](UWidget* W) { ++WidgetCount; if (!WBP->WidgetVariableNameToGuidMap.Contains(W->GetFName())) { MissingGuid.Add(W->GetName()); } });
			Out->SetNumberField(TEXT("widget_count"), WidgetCount);
			Out->SetArrayField(TEXT("guid_missing"), WidgetMcp::StringArray(MissingGuid));
			return Out;
		}
	}

	using namespace ToolsPrivate;

	const TArray<FString>& ToolNames()
	{
		static const TArray<FString> Names = { TEXT("import_ui_textures"), TEXT("create_widget_blueprint"), TEXT("preview_widget_spec"), TEXT("apply_widget_spec"),
			TEXT("apply_widget_patch"), TEXT("export_widget_spec"), TEXT("compile_widget_blueprint"), TEXT("list_bind_widgets"), TEXT("render_widget"),
			TEXT("save_widget_run"), TEXT("discard_run_packages") };
		return Names;
	}

	void Register(FEditorMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("import_ui_textures"),
			TEXT("Import PNGs as UI textures through Interchange into a run folder (never saved here). Params: dest_path (/Game/_AutoGen/<run_id>), textures[{file (under [WidgetMcp] WidgetImportSourceRoots), name (T_x), compression? (TC_EditorIcon|TC_BC7, default TC_EditorIcon), lod_group? (TEXTUREGROUP_UI), mip_gen? (TMGS_NoMipmaps), never_stream? (true), srgb? (true)}]. Refuses existing names and paths outside [WidgetMcp] WidgetOutputPaths; fails UNEXPECTED_DIRTY if anything outside got dirty."),
			[](FEditorMcpContext& Context, FEditorMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString Dest;
				if (!Context.Request.GetRequiredString(TEXT("dest_path"), Dest, OutError))
				{
					return nullptr;
				}
				const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
				if (!Context.Request.Params->TryGetArrayField(TEXT("textures"), Arr))
				{
					OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, TEXT("textures[] is required"));
					return nullptr;
				}
				TArray<WidgetMcpTextures::FRequest> Requests;
				for (const TSharedPtr<FJsonValue>& V : *Arr)
				{
					const TSharedPtr<FJsonObject> O = V.IsValid() ? V->AsObject() : nullptr;
					if (!O.IsValid())
					{
						OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, TEXT("textures[] items must be objects"));
						return nullptr;
					}
					WidgetMcpTextures::FRequest R;
					O->TryGetStringField(TEXT("file"), R.File);
					O->TryGetStringField(TEXT("name"), R.Name);
					O->TryGetStringField(TEXT("compression"), R.Compression);
					O->TryGetStringField(TEXT("lod_group"), R.LodGroup);
					O->TryGetStringField(TEXT("mip_gen"), R.MipGen);
					O->TryGetBoolField(TEXT("never_stream"), R.bNeverStream);
					O->TryGetBoolField(TEXT("srgb"), R.bSRGB);
					Requests.Add(R);
				}
				return WidgetMcpTextures::Import(WidgetMcp::LoadSettings(), Dest, Requests, Context, OutError);
			});

		Dispatcher.RegisterTool(TEXT("create_widget_blueprint"),
			TEXT("Create an empty Widget Blueprint (never saved here) with a CanvasPanel root. Params: asset_path (/Game/_AutoGen/<run_id>/WBP_x), parent_class? (/Script/<Module>.<Class> — the stub, a non-abstract UUserWidget subclass; default UserWidget), root_id? (default Root). Returns revision (needed by apply_widget_spec), compile result and the parent's BindWidget list."),
			[](FEditorMcpContext& Context, FEditorMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError))
				{
					return nullptr;
				}
				return WidgetMcpBlueprint::Create(WidgetMcp::LoadSettings(), AssetPath, Context.Request.GetOptionalString(TEXT("parent_class")),
					Context.Request.GetOptionalString(TEXT("root_id"), WidgetMcp::RootIdDefault), Context, OutError);
			});

		auto SpecTool = [](bool bApply)
		{
			return [bApply](FEditorMcpContext& Context, FEditorMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				UWidgetBlueprint* WBP = LoadWbpParam(Context, OutError);
				if (!WBP)
				{
					return nullptr;
				}
				const TSharedPtr<FJsonObject> Spec = ObjectParam(Context, TEXT("spec"));
				if (!Spec.IsValid())
				{
					OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, TEXT("spec{} is required"));
					return nullptr;
				}
				WidgetMcpSpec::FAssets Assets;
				if (!LoadAssetsParam(Context, Assets, OutError))
				{
					return nullptr;
				}
				return WidgetMcpBlueprint::Reconcile(WidgetMcp::LoadSettings(), WBP, Spec.ToSharedRef(), Assets, Context.Request.GetOptionalString(TEXT("expected_revision")),
					bApply, Context.Request.GetOptionalBool(TEXT("compile"), true), Context, OutError);
			};
		};
		Dispatcher.RegisterTool(TEXT("preview_widget_spec"),
			TEXT("Reconciler dry run: diff the Widget Blueprint against a target spec ({root, widgets[], locked[]?} — Tools/uigen spec shape) and validate everything; changes nothing. Params: asset_path, spec, assets? ({asset_id: texture path}). Returns valid, errors[], ops[], missing_bindings[], revision."),
			SpecTool(false));
		Dispatcher.RegisterTool(TEXT("apply_widget_spec"),
			TEXT("Reconciler: make the Widget Blueprint equal to the target spec in one atomic batch (built on a copy, verified by export, then swapped in — any failure leaves the blueprint unchanged). Params: asset_path, spec, assets?, expected_revision (required; REVISION_MISMATCH if the blueprint changed), compile? (default true). Refuses removing/retyping widgets bound by the parent class (BINDING_REMOVAL/BINDING_TYPE) and changing spec.locked widgets (LOCKED). Never saves."),
			SpecTool(true));

		Dispatcher.RegisterTool(TEXT("apply_widget_patch"),
			TEXT("Apply a spec patch through the reconciler. Params: asset_path, patch {base_revision, ops[set|add_widget|remove_widget|move]}, assets?, locked? (widget ids), compile? (default true). set paths cannot touch id/type/parent/slot.kind; binding and replace_asset ops are pipeline-only (PIPELINE_ONLY). Same guards as apply_widget_spec."),
			[](FEditorMcpContext& Context, FEditorMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				UWidgetBlueprint* WBP = LoadWbpParam(Context, OutError);
				if (!WBP)
				{
					return nullptr;
				}
				const TSharedPtr<FJsonObject> Patch = ObjectParam(Context, TEXT("patch"));
				const TArray<TSharedPtr<FJsonValue>>* Ops = nullptr;
				if (!Patch.IsValid() || !Patch->TryGetArrayField(TEXT("ops"), Ops) || Ops->Num() == 0)
				{
					OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, TEXT("patch{ops[]} is required"));
					return nullptr;
				}
				WidgetMcpSpec::FAssets Assets;
				if (!LoadAssetsParam(Context, Assets, OutError))
				{
					return nullptr;
				}
				TSharedPtr<FJsonObject> Target = WidgetMcpBlueprint::PatchTarget(WBP, *Ops, Assets, OutError);
				if (!Target.IsValid())
				{
					return nullptr;
				}
				const TArray<TSharedPtr<FJsonValue>>* Locked = nullptr;
				if (Context.Request.Params->TryGetArrayField(TEXT("locked"), Locked))
				{
					TArray<TSharedPtr<FJsonValue>> Merged = Target->GetArrayField(TEXT("locked"));
					Merged.Append(*Locked);
					Target->SetArrayField(TEXT("locked"), Merged);
				}
				FString Base;
				Patch->TryGetStringField(TEXT("base_revision"), Base);
				return WidgetMcpBlueprint::Reconcile(WidgetMcp::LoadSettings(), WBP, Target.ToSharedRef(), Assets, Base, true,
					Context.Request.GetOptionalBool(TEXT("compile"), true), Context, OutError);
			});

		Dispatcher.RegisterTool(TEXT("export_widget_spec"),
			TEXT("Widget Blueprint -> spec ({root, widgets[], locked[]}) + revision (SHA1 of the canonical export) + unsupported[] (widgets/properties outside the vocabulary, locked) + textures[] (settings of every brush texture) + bindings[] + GUID map check. Params: asset_path, assets? ({asset_id: texture path} — when given, brush textures come back as asset ids)."),
			[](FEditorMcpContext& Context, FEditorMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				UWidgetBlueprint* WBP = LoadWbpParam(Context, OutError);
				if (!WBP)
				{
					return nullptr;
				}
				WidgetMcpSpec::FAssets Assets;
				if (!LoadAssetsParam(Context, Assets, OutError))
				{
					return nullptr;
				}
				return ExportResult(WBP, Assets, ObjectParam(Context, TEXT("assets")).IsValid());
			});

		Dispatcher.RegisterTool(TEXT("compile_widget_blueprint"),
			TEXT("Compile a Widget Blueprint. Params: asset_path. Returns ok, status, errors, warnings, messages[], missing_bindings[] (required BindWidget of the parent class that is absent or of the wrong type), revision."),
			[](FEditorMcpContext& Context, FEditorMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				UWidgetBlueprint* WBP = LoadWbpParam(Context, OutError);
				if (!WBP)
				{
					return nullptr;
				}
				const WidgetMcp::FSettings Settings = WidgetMcp::LoadSettings();
				if (!WidgetMcp::CheckOutputAsset(Settings, WBP->GetPathName(), TEXT("asset_path"), OutError))
				{
					return nullptr;
				}
				const WidgetMcp::FWriteGuard Guard;
				TSharedRef<FJsonObject> Out = WidgetMcpBlueprint::Compile(WBP);
				TArray<FString> NewlyDirty;
				if (!Guard.Finish(Settings, OutError, NewlyDirty))
				{
					return nullptr;
				}
				Out->SetStringField(TEXT("asset_path"), WBP->GetPathName());
				Out->SetStringField(TEXT("revision"), WidgetMcpBlueprint::Revision(WBP));
				return Out;
			});

		Dispatcher.RegisterTool(TEXT("list_bind_widgets"),
			TEXT("BindWidget contract of a class (inherited, by name). Params: class (/Script/<Module>.<Class>) or asset_path (a Widget Blueprint — its parent class). Returns bindings[{name, widget_class, widget_class_path, optional}]."),
			[](FEditorMcpContext& Context, FEditorMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				const UClass* Class = nullptr;
				const FString ClassPath = Context.Request.GetOptionalString(TEXT("class"));
				if (!ClassPath.IsEmpty())
				{
					Class = LoadObject<UClass>(nullptr, *ClassPath, nullptr, LOAD_NoWarn);
					if (!Class)
					{
						OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::TypeNotFound, FString::Printf(TEXT("class '%s' does not load"), *ClassPath));
						return nullptr;
					}
				}
				else
				{
					UWidgetBlueprint* WBP = LoadWbpParam(Context, OutError);
					if (!WBP)
					{
						return nullptr;
					}
					Class = WBP->ParentClass;
				}
				TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
				Out->SetStringField(TEXT("class"), GetPathNameSafe(Class));
				Out->SetArrayField(TEXT("bindings"), WidgetMcpBlueprint::BindWidgetsJson(WidgetMcpBlueprint::BindWidgets(Class)));
				return Out;
			});

		Dispatcher.RegisterTool(TEXT("render_widget"),
			TEXT("Offscreen-render a compiled Widget Blueprint to PNG (gamma-corrected per design 12-1 A6) plus the paint-space geometry of every widget from the same draw. Params: asset_path, output_dir (new/empty folder under [WidgetMcp] WidgetRenderOutputRoots), resolutions? ([[w,h],...], default [[1920,1080]]), force_visible? (collapsed/hidden widgets drawn — layout checks), overrides? ({widget: {visible?, percent?, text?}}), scale? (1), draws? (2), prefix? (render), probes? ([{id, at:[x,y]}] — color after correction, first resolution)."),
			[](FEditorMcpContext& Context, FEditorMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				UWidgetBlueprint* WBP = LoadWbpParam(Context, OutError);
				if (!WBP)
				{
					return nullptr;
				}
				WidgetMcpRender::FRequest R;
				if (!Context.Request.GetRequiredString(TEXT("output_dir"), R.OutputDir, OutError))
				{
					return nullptr;
				}
				const TArray<TSharedPtr<FJsonValue>>* Res = nullptr;
				if (Context.Request.Params->TryGetArrayField(TEXT("resolutions"), Res))
				{
					for (const TSharedPtr<FJsonValue>& V : *Res)
					{
						FIntPoint P;
						if (!ReadIntPair(V, P))
						{
							OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, TEXT("resolutions[] items must be [w, h]"));
							return nullptr;
						}
						R.Resolutions.Add(P);
					}
				}
				else
				{
					R.Resolutions.Add(FIntPoint(1920, 1080));
				}
				R.bForceVisible = Context.Request.GetOptionalBool(TEXT("force_visible"), false);
				R.Scale = static_cast<float>(Context.Request.GetOptionalNumber(TEXT("scale"), 1.0));
				R.Draws = static_cast<int32>(Context.Request.GetOptionalNumber(TEXT("draws"), 2));
				R.Prefix = Context.Request.GetOptionalString(TEXT("prefix"), TEXT("render"));
				if (const TSharedPtr<FJsonObject> Overrides = ObjectParam(Context, TEXT("overrides")))
				{
					for (const TPair<FString, TSharedPtr<FJsonValue>>& P : Overrides->Values)
					{
						const TSharedPtr<FJsonObject> O = P.Value.IsValid() ? P.Value->AsObject() : nullptr;
						if (!O.IsValid()) { continue; }
						WidgetMcpRender::FOverride Ov;
						bool bVisible;
						double Percent;
						FString Text;
						if (O->TryGetBoolField(TEXT("visible"), bVisible)) { Ov.bVisible = bVisible; }
						if (O->TryGetNumberField(TEXT("percent"), Percent)) { Ov.Percent = static_cast<float>(Percent); }
						if (O->TryGetStringField(TEXT("text"), Text)) { Ov.Text = Text; }
						R.Overrides.Add(P.Key, Ov);
					}
				}
				const TArray<TSharedPtr<FJsonValue>>* Probes = nullptr;
				if (Context.Request.Params->TryGetArrayField(TEXT("probes"), Probes))
				{
					for (const TSharedPtr<FJsonValue>& V : *Probes)
					{
						const TSharedPtr<FJsonObject> O = V.IsValid() ? V->AsObject() : nullptr;
						FIntPoint At;
						if (O.IsValid() && ReadIntPair(O->Values.FindRef(TEXT("at")), At))
						{
							FString Id;
							O->TryGetStringField(TEXT("id"), Id);
							R.Probes.Add({ Id, At });
						}
					}
				}
				return WidgetMcpRender::Render(WidgetMcp::LoadSettings(), WBP, R, Context, OutError);
			});

		Dispatcher.RegisterTool(TEXT("save_widget_run"),
			TEXT("Save every package under a run folder (finalize only). Params: run_path (/Game/_AutoGen/<run_id> — a folder below [WidgetMcp] WidgetOutputPaths, never the prefix itself)."),
			[](FEditorMcpContext& Context, FEditorMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString Run;
				if (!Context.Request.GetRequiredString(TEXT("run_path"), Run, OutError))
				{
					return nullptr;
				}
				return WidgetMcpRunPackages::Save(WidgetMcp::LoadSettings(), Run, Context, OutError);
			});

		Dispatcher.RegisterTool(TEXT("discard_run_packages"),
			TEXT("Drop the never-saved packages under a run folder (unload, no files touched). Params: run_path (/Game/_AutoGen/<run_id>). Refuses (nothing discarded) if any package there is saved on disk."),
			[](FEditorMcpContext& Context, FEditorMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString Run;
				if (!Context.Request.GetRequiredString(TEXT("run_path"), Run, OutError))
				{
					return nullptr;
				}
				return WidgetMcpRunPackages::Discard(WidgetMcp::LoadSettings(), Run, Context, OutError);
			});
	}
}
