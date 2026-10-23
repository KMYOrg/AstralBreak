#include "AnimMcpTools.h"

#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAnimSearch.h"
#include "Core/AnimMcpAssetResolver.h"

// AI 애니 생성 Phase 2 — 기존 모션 검색 (Core/AnimMcpAnimSearch). 읽기 전용: loop 필터·details 만 애셋을 로드한다.
namespace AnimMcpTools
{
	namespace
	{
		FAnimMcpError SearchFieldError(const TCHAR* Field, const FString& Message)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), Field);
			return FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
		}

		bool ReadOptionalBool(const TSharedRef<FJsonObject>& Params, const TCHAR* Field, TOptional<bool>& Out, FAnimMcpError& OutError)
		{
			const TSharedPtr<FJsonValue> Value = Params->TryGetField(Field);
			if (!Value.IsValid() || Value->Type == EJson::Null)
			{
				return true;
			}
			if (Value->Type != EJson::Boolean)
			{
				OutError = SearchFieldError(Field, FString::Printf(TEXT("%s must be a boolean"), Field));
				return false;
			}
			Out = Value->AsBool();
			return true;
		}

		bool ReadOptionalNumber(const TSharedRef<FJsonObject>& Params, const TCHAR* Field, TOptional<double>& Out, FAnimMcpError& OutError)
		{
			const TSharedPtr<FJsonValue> Value = Params->TryGetField(Field);
			if (!Value.IsValid() || Value->Type == EJson::Null)
			{
				return true;
			}
			if (Value->Type != EJson::Number)
			{
				OutError = SearchFieldError(Field, FString::Printf(TEXT("%s must be a number"), Field));
				return false;
			}
			Out = Value->AsNumber();
			return true;
		}
	}

	void RegisterSearchTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("search_animations"),
			TEXT("Search existing animations by metadata (read-only). Index = asset registry tags (no loading) + manual tags from [AnimGraphMcp] AnimationTagFiles (JSON {\"tags\": {\"<asset path or folder/>\": [\"tag\", ...]}}). "
			     "Params: query? (name tokens — split at '_', CamelCase and digit edges; every query token must equal or prefix a token of the asset name (scored 3/2) or its folders (1.5/1)), skeleton?, path_prefix? (default /Game), class? (AnimSequence default | AnimMontage | AnimComposite | all), "
			     "min_length? / max_length? (seconds), root_motion?, additive?, loop? (not a registry tag — loads the candidates; more than max_loads is BAD_REQUEST LOAD_LIMIT), tags?[] (all required), limit? (default 50), details? (loads the returned assets: loop, notifies[{name, time, duration, track}], sync_markers[], curves[], root{bone, displacement_cm, yaw_delta_deg}), max_loads? (default 300). "
			     "Returns total, returned, truncated, items[{asset_path, name, class, skeleton, length, frames, frame_rate, root_motion, additive_type, loop (null unless loaded), tags[], score, matched[]}] (best score first, then path), loaded, tag_files[], query_tokens[]."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				const TSharedRef<FJsonObject>& Params = Context.Request.Params;
				AnimMcpAnimSearch::FQuery Query;
				Query.Tokens = AnimMcpAnimSearch::Tokenize(Context.Request.GetOptionalString(TEXT("query")));
				const FString Skeleton = Context.Request.GetOptionalString(TEXT("skeleton"));
				if (!Skeleton.IsEmpty())
				{
					Query.Skeleton = AnimMcpAssetResolver::NormalizeObjectPath(Skeleton);
					if (!AnimMcpAssetResolver::AssetExists(Query.Skeleton))
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::AssetNotFound, FString::Printf(TEXT("Skeleton '%s' not found"), *Query.Skeleton));
						return nullptr;
					}
				}
				Query.PathPrefix = Context.Request.GetOptionalString(TEXT("path_prefix"), TEXT("/Game"));
				Query.Class = Context.Request.GetOptionalString(TEXT("class"), TEXT("AnimSequence"));
				if (!ReadOptionalNumber(Params, TEXT("min_length"), Query.MinLength, OutError)
					|| !ReadOptionalNumber(Params, TEXT("max_length"), Query.MaxLength, OutError)
					|| !ReadOptionalBool(Params, TEXT("root_motion"), Query.bRootMotion, OutError)
					|| !ReadOptionalBool(Params, TEXT("additive"), Query.bAdditive, OutError)
					|| !ReadOptionalBool(Params, TEXT("loop"), Query.bLoop, OutError))
				{
					return nullptr;
				}
				const TArray<TSharedPtr<FJsonValue>>* Tags = nullptr;
				if (Params->HasField(TEXT("tags")))
				{
					if (!Params->TryGetArrayField(TEXT("tags"), Tags))
					{
						OutError = SearchFieldError(TEXT("tags"), TEXT("tags must be an array of strings"));
						return nullptr;
					}
					for (const TSharedPtr<FJsonValue>& V : *Tags)
					{
						FString Tag;
						if (!V.IsValid() || !V->TryGetString(Tag))
						{
							OutError = SearchFieldError(TEXT("tags"), TEXT("tags must be an array of strings"));
							return nullptr;
						}
						Query.Tags.AddUnique(Tag.ToLower());
					}
				}
				Query.Limit = FMath::Clamp(static_cast<int32>(Context.Request.GetOptionalNumber(TEXT("limit"), 50.0)), 1, 5000);
				Query.bDetails = Context.Request.GetOptionalBool(TEXT("details"), false);
				Query.MaxLoads = FMath::Clamp(static_cast<int32>(Context.Request.GetOptionalNumber(TEXT("max_loads"), 300.0)), 1, 5000);
				return AnimMcpAnimSearch::Search(Query, Context, OutError);
			});
	}
}
