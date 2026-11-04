#include "AnimMcpTools.h"

#include "Animation/Skeleton.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAnimImport.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpGeneration.h"
#include "Misc/Paths.h"

// AI 애니 생성 Phase 1 — FBX 임포트 (Core/AnimMcpAnimImport). 파일은 [AnimGraphMcp] ImportSourceRoots 아래, 대상은 GenerationOutputPaths 안의 빈 폴더.
namespace AnimMcpTools
{
	void RegisterImportTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("import_animation_file"),
			TEXT("Import an FBX through Interchange as a retarget source. Params: file (absolute path under [AnimGraphMcp] ImportSourceRoots — IMPORT_SOURCE_NOT_ALLOWED otherwise), dest_path (EMPTY content folder under GenerationOutputPaths — ASSET_EXISTS reason DEST_NOT_EMPTY otherwise), skeleton? (import only the animations onto this existing Skeleton; omitted = skeletal mesh + new skeleton + animations), sample_rate? (0 = Interchange picks the best rate), name? (base asset name, default the file name), save? (default false). A clip whose length is not on the bake rate's frame borders is snapped to the closest frames (warning LENGTH_SNAPPED {track}; the result length is animations[].length). Always off: curve metadata on the skeleton, materials, textures, physics asset, static meshes; never replaces assets; no dialogs. The project's default pipeline stack is duplicated transiently (the pipeline assets are untouched). Returns imported[], animations[{asset, skeleton, frame_rate, frames, length}], skeleton, skeleton_created, mesh, source_frame_rate, pipelines[], seconds, saved. Any package outside GenerationOutputPaths that becomes dirty fails the call with UNEXPECTED_DIRTY (nothing saved)."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				AnimMcpAnimImport::FParams Params;
				FString File, DestPath;
				if (!Context.Request.GetRequiredString(TEXT("file"), File, OutError)) { return nullptr; }
				if (!Context.Request.GetRequiredString(TEXT("dest_path"), DestPath, OutError)) { return nullptr; }
				if (!AnimMcpGeneration::EnsureOutputPathAllowed(DestPath, TEXT("dest_path"), OutError)) { return nullptr; }
				if (!AnimMcpGeneration::ResolveImportSource(File, Params.File, OutError)) { return nullptr; }
				if (!FPaths::GetExtension(Params.File).Equals(TEXT("fbx"), ESearchCase::IgnoreCase))
				{
					TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
					Details->SetStringField(TEXT("field"), TEXT("file"));
					Details->SetStringField(TEXT("reason"), TEXT("UNSUPPORTED_FORMAT"));
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Only .fbx is supported (got '%s') — convert BVH and others with Blender first"), *FPaths::GetExtension(Params.File)), Details);
					return nullptr;
				}
				Params.DestPath = AnimMcpGeneration::NormalizeFolderPath(DestPath);

				const FString SkeletonPath = Context.Request.GetOptionalString(TEXT("skeleton"));
				if (!SkeletonPath.IsEmpty())
				{
					Params.Skeleton = AnimMcpAssetResolver::LoadSkeleton(SkeletonPath, OutError);
					if (!Params.Skeleton) { return nullptr; }
				}
				const double SampleRate = Context.Request.GetOptionalNumber(TEXT("sample_rate"), 0.0);
				if (SampleRate < 0.0 || SampleRate > 48000.0 || SampleRate != FMath::FloorToDouble(SampleRate))
				{
					TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
					Details->SetStringField(TEXT("field"), TEXT("sample_rate"));
					Details->SetStringField(TEXT("reason"), TEXT("OUT_OF_RANGE"));
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("sample_rate must be an integer 0..48000 (0 = automatic)"), Details);
					return nullptr;
				}
				Params.SampleRate = static_cast<int32>(SampleRate);
				Params.Name = Context.Request.GetOptionalString(TEXT("name"));
				FText NameReason;
				if (!Params.Name.IsEmpty() && !FName(*Params.Name).IsValidObjectName(NameReason))
				{
					TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
					Details->SetStringField(TEXT("field"), TEXT("name"));
					Details->SetStringField(TEXT("reason"), TEXT("INVALID_NAME"));
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' is not a valid asset name: %s"), *Params.Name, *NameReason.ToString()), Details);
					return nullptr;
				}
				Params.bSave = Context.Request.GetOptionalBool(TEXT("save"), false);
				return AnimMcpAnimImport::Import(Params, Context, OutError);
			});
	}
}
