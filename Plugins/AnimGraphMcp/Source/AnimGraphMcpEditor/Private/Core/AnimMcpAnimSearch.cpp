#include "AnimMcpAnimSearch.h"

#include "AnimMcpGeneration.h"
#include "AnimMcpStats.h"
#include "Animation/AnimComposite.h"
#include "Animation/AnimData/IAnimationDataModel.h"
#include "Animation/AnimMontage.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "AssetRegistry/ARFilter.h"
#include "AssetRegistry/AssetData.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "AssetRegistry/IAssetRegistry.h"
#include "Bridge/AnimMcpTypes.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace AnimMcpAnimSearch
{
	namespace
	{
		/** 수동 태그 — 키는 패키지 경로(애셋) 또는 '/' 로 끝나는 폴더 접두, 값은 소문자 태그 */
		struct FTagIndex
		{
			TArray<TPair<FString, TArray<FString>>> Folders;
			TMap<FString, TArray<FString>> Assets;

			TArray<FString> Find(const FString& PackagePath) const
			{
				TArray<FString> Out;
				for (const TPair<FString, TArray<FString>>& Folder : Folders)
				{
					if (PackagePath.StartsWith(Folder.Key, ESearchCase::IgnoreCase))
					{
						for (const FString& Tag : Folder.Value) { Out.AddUnique(Tag); }
					}
				}
				if (const TArray<FString>* Own = Assets.Find(PackagePath.ToLower()))
				{
					for (const FString& Tag : *Own) { Out.AddUnique(Tag); }
				}
				Out.Sort();
				return Out;
			}
		};

		/** 파일을 매 호출 읽는다(작은 JSON — 편집이 바로 반영되게). 없는 파일 · 잘못된 JSON 은 경고만 */
		FTagIndex LoadTags(FAnimMcpContext& Context)
		{
			FTagIndex Index;
			for (const FString& File : AnimMcpGeneration::GetSettings().AnimationTagFiles)
			{
				FString Text;
				if (!FFileHelper::LoadFileToString(Text, *File))
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("TAG_FILE_MISSING"), FString::Printf(TEXT("[AnimGraphMcp] AnimationTagFiles entry '%s' could not be read"), *File));
					continue;
				}
				TSharedPtr<FJsonObject> Root;
				const TSharedPtr<FJsonObject>* Tags = nullptr;
				if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid() || !Root->TryGetObjectField(TEXT("tags"), Tags))
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("TAG_FILE_INVALID"), FString::Printf(TEXT("'%s' is not {\"tags\": {\"<asset or folder/>\": [\"tag\", ...]}}"), *File));
					continue;
				}
				for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*Tags)->Values)
				{
					TArray<FString> Values;
					const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
					if (Pair.Value.IsValid() && Pair.Value->TryGetArray(Array))
					{
						for (const TSharedPtr<FJsonValue>& V : *Array)
						{
							FString Tag;
							if (V.IsValid() && V->TryGetString(Tag) && !Tag.IsEmpty()) { Values.AddUnique(Tag.ToLower()); }
						}
					}
					if (Pair.Key.EndsWith(TEXT("/")))
					{
						Index.Folders.Emplace(Pair.Key, Values);
					}
					else
					{
						Index.Assets.FindOrAdd(FPackageName::ObjectPathToPackageName(Pair.Key).ToLower()).Append(Values);
					}
				}
			}
			return Index;
		}

		bool AddClassFilter(FARFilter& Filter, const FString& ClassName, FAnimMcpError& OutError)
		{
			const FString Lower = ClassName.ToLower();
			if (Lower == TEXT("animsequence")) { Filter.ClassPaths.Add(UAnimSequence::StaticClass()->GetClassPathName()); return true; }
			if (Lower == TEXT("animmontage")) { Filter.ClassPaths.Add(UAnimMontage::StaticClass()->GetClassPathName()); return true; }
			if (Lower == TEXT("animcomposite")) { Filter.ClassPaths.Add(UAnimComposite::StaticClass()->GetClassPathName()); return true; }
			if (Lower == TEXT("all")) { Filter.ClassPaths.Add(UAnimSequenceBase::StaticClass()->GetClassPathName()); return true; }
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), TEXT("class"));
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Unknown class '%s' (AnimSequence, AnimMontage, AnimComposite, all)"), *ClassName), Details);
			return false;
		}

		TOptional<double> TagNumber(const FAssetData& Data, const TCHAR* Tag)
		{
			FString Value;
			if (Data.GetTagValue(FName(Tag), Value) && !Value.IsEmpty() && FCString::IsNumeric(*Value))
			{
				return FCString::Atod(*Value);
			}
			return {};
		}

		TOptional<bool> TagBool(const FAssetData& Data, const TCHAR* Tag)
		{
			FString Value;
			if (Data.GetTagValue(FName(Tag), Value) && !Value.IsEmpty())
			{
				return Value.ToBool();
			}
			return {};
		}

		void SetOptionalNumber(const TSharedRef<FJsonObject>& Obj, const TCHAR* Key, const TOptional<double>& Value, int32 Digits = 4)
		{
			if (Value.IsSet()) { Obj->SetNumberField(Key, AnimMcpStats::Round(Value.GetValue(), Digits)); }
			else { Obj->SetField(Key, MakeShared<FJsonValueNull>()); }
		}

		struct FCandidate
		{
			FAssetData Data;
			double Score = 0.0;
			TArray<FString> Matched;
			TArray<FString> Tags;
			TOptional<bool> bLoop;
		};

		/** 질의 토큰마다 이름 · 폴더 토큰에서 가장 좋은 일치 — 하나라도 없으면 false */
		bool MatchTokens(const TArray<FString>& Query, const TArray<FString>& NameTokens, const TArray<FString>& FolderTokens, double& OutScore, TArray<FString>& OutMatched)
		{
			OutScore = 0.0;
			for (const FString& Q : Query)
			{
				double Best = 0.0;
				FString BestToken;
				auto Try = [&](const TArray<FString>& Tokens, double Exact, double Prefix)
				{
					for (const FString& T : Tokens)
					{
						const double S = T == Q ? Exact : (T.StartsWith(Q) ? Prefix : 0.0);
						if (S > Best) { Best = S; BestToken = T; }
					}
				};
				Try(NameTokens, 3.0, 2.0);
				Try(FolderTokens, 1.5, 1.0);
				if (Best <= 0.0)
				{
					return false;
				}
				OutScore += Best;
				OutMatched.AddUnique(BestToken);
			}
			return true;
		}

		/** 루트 트랙의 첫 → 끝 이동량 · Yaw 변화 (원시 키) */
		void RootMotionSummary(const UAnimSequence* Sequence, const TSharedRef<FJsonObject>& Out)
		{
			const IAnimationDataModel* Model = Sequence->GetDataModel();
			const USkeleton* Skeleton = Sequence->GetSkeleton();
			if (!Model || !Skeleton || Skeleton->GetReferenceSkeleton().GetRawBoneNum() == 0)
			{
				return;
			}
			const FName Root = Skeleton->GetReferenceSkeleton().GetBoneName(0);
			TArray<FTransform> Keys;
			if (Model->IsValidBoneTrackName(Root))
			{
				Model->GetBoneTrackTransforms(Root, Keys);
			}
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("bone"), Root.ToString());
			double Yaw = 0.0;
			for (int32 i = 1; i < Keys.Num(); ++i)
			{
				Yaw += FRotator::NormalizeAxis(Keys[i].GetRotation().Rotator().Yaw - Keys[i - 1].GetRotation().Rotator().Yaw);
			}
			Obj->SetNumberField(TEXT("displacement_cm"), AnimMcpStats::Round(Keys.Num() > 1 ? FVector::Dist(Keys.Last().GetLocation(), Keys[0].GetLocation()) : 0.0, 2));
			Obj->SetNumberField(TEXT("yaw_delta_deg"), AnimMcpStats::Round(Yaw, 2));
			Obj->SetBoolField(TEXT("has_track"), Keys.Num() > 0);
			Out->SetObjectField(TEXT("root"), Obj);
		}

		void AddDetails(UAnimSequenceBase* Asset, const TSharedRef<FJsonObject>& Item)
		{
			TArray<TSharedPtr<FJsonValue>> Notifies;
			for (const FAnimNotifyEvent& Event : Asset->Notifies)
			{
				TSharedRef<FJsonObject> N = AnimMcpJson::MakeObject();
				N->SetStringField(TEXT("name"), Event.NotifyName.ToString());
				N->SetNumberField(TEXT("time"), AnimMcpStats::Round(Event.GetTime(), 4));
				N->SetNumberField(TEXT("duration"), AnimMcpStats::Round(Event.GetDuration(), 4));
				N->SetNumberField(TEXT("track"), Event.TrackIndex);
				Notifies.Add(MakeShared<FJsonValueObject>(N));
			}
			Item->SetArrayField(TEXT("notifies"), Notifies);
			TArray<FString> Curves;
			if (const IAnimationDataModel* Model = Asset->GetDataModel())
			{
				for (const FFloatCurve& Curve : Model->GetFloatCurves()) { Curves.Add(Curve.GetName().ToString()); }
			}
			Item->SetArrayField(TEXT("curves"), AnimMcpGeneration::ToJsonArray(Curves));
			if (const UAnimSequence* Sequence = Cast<UAnimSequence>(Asset))
			{
				TArray<TSharedPtr<FJsonValue>> Markers;
				for (const FAnimSyncMarker& Marker : Sequence->AuthoredSyncMarkers)
				{
					TSharedRef<FJsonObject> M = AnimMcpJson::MakeObject();
					M->SetStringField(TEXT("name"), Marker.MarkerName.ToString());
					M->SetNumberField(TEXT("time"), AnimMcpStats::Round(Marker.Time, 4));
					Markers.Add(MakeShared<FJsonValueObject>(M));
				}
				Item->SetArrayField(TEXT("sync_markers"), Markers);
				RootMotionSummary(Sequence, Item);
			}
		}
	}

	TArray<FString> Tokenize(const FString& Text)
	{
		TArray<FString> Tokens;
		FString Current;
		auto Flush = [&]()
		{
			if (!Current.IsEmpty()) { Tokens.Add(Current.ToLower()); Current.Reset(); }
		};
		for (int32 i = 0; i < Text.Len(); ++i)
		{
			const TCHAR C = Text[i];
			if (!FChar::IsAlnum(C))
			{
				Flush();
				continue;
			}
			if (!Current.IsEmpty())
			{
				const TCHAR P = Current[Current.Len() - 1];
				const bool bNext = i + 1 < Text.Len();
				const bool bLowerToUpper = FChar::IsLower(P) && FChar::IsUpper(C);
				const bool bDigitEdge = FChar::IsDigit(P) != FChar::IsDigit(C);
				// "HSword" → h, sword : 대문자 연속 뒤 소문자가 오면 마지막 대문자부터 새 토큰
				const bool bAcronymEnd = FChar::IsUpper(P) && FChar::IsUpper(C) && bNext && FChar::IsLower(Text[i + 1]);
				if (bLowerToUpper || bDigitEdge || bAcronymEnd)
				{
					Flush();
				}
			}
			Current.AppendChar(C);
		}
		Flush();
		return Tokens;
	}

	TSharedPtr<FJsonObject> Search(const FQuery& Query, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		const AnimMcpGeneration::FDirtyGuard Guard;
		FARFilter Filter;
		if (!AddClassFilter(Filter, Query.Class, OutError))
		{
			return nullptr;
		}
		Filter.bRecursiveClasses = true;
		Filter.PackagePaths.Add(FName(*AnimMcpGeneration::NormalizeFolderPath(Query.PathPrefix)));
		Filter.bRecursivePaths = true;
		TArray<FAssetData> Assets;
		FAssetRegistryModule::GetRegistry().GetAssets(Filter, Assets);
		const FTagIndex TagIndex = LoadTags(Context);

		// ---- 로드 없는 필터 · 점수 ----
		TArray<FCandidate> Candidates;
		static const FName SkeletonTag(TEXT("Skeleton"));
		for (const FAssetData& Data : Assets)
		{
			FString SkeletonValue;
			Data.GetTagValue(SkeletonTag, SkeletonValue);
			if (!Query.Skeleton.IsEmpty() && FPackageName::ExportTextPathToObjectPath(SkeletonValue) != Query.Skeleton)
			{
				continue;
			}
			const TOptional<double> Length = TagNumber(Data, TEXT("SequenceLength"));
			if (Query.MinLength.IsSet() && (!Length.IsSet() || Length.GetValue() < Query.MinLength.GetValue())) { continue; }
			if (Query.MaxLength.IsSet() && (!Length.IsSet() || Length.GetValue() > Query.MaxLength.GetValue())) { continue; }
			if (Query.bRootMotion.IsSet() && TagBool(Data, TEXT("bEnableRootMotion")).Get(false) != Query.bRootMotion.GetValue()) { continue; }
			if (Query.bAdditive.IsSet())
			{
				FString Additive;
				Data.GetTagValue(FName(TEXT("AdditiveAnimType")), Additive);
				const bool bAdditive = !Additive.IsEmpty() && Additive != TEXT("AAT_None");
				if (bAdditive != Query.bAdditive.GetValue()) { continue; }
			}
			FCandidate Candidate;
			Candidate.Data = Data;
			Candidate.Tags = TagIndex.Find(Data.PackageName.ToString());
			if (Query.Tags.ContainsByPredicate([&Candidate](const FString& Tag) { return !Candidate.Tags.Contains(Tag); }))
			{
				continue;
			}
			if (Query.Tokens.Num() > 0)
			{
				TArray<FString> FolderTokens;
				TArray<FString> Folders;
				Data.PackagePath.ToString().ParseIntoArray(Folders, TEXT("/"));
				for (const FString& Folder : Folders) { FolderTokens.Append(Tokenize(Folder)); }
				if (!MatchTokens(Query.Tokens, Tokenize(Data.AssetName.ToString()), FolderTokens, Candidate.Score, Candidate.Matched))
				{
					continue;
				}
			}
			Candidates.Add(MoveTemp(Candidate));
		}
		Candidates.Sort([](const FCandidate& A, const FCandidate& B)
		{
			return A.Score != B.Score ? A.Score > B.Score : A.Data.GetObjectPathString() < B.Data.GetObjectPathString();
		});

		// ---- 로드가 필요한 필터 (bLoop 은 레지스트리 태그가 아니다) ----
		int32 Loaded = 0;
		auto LoadOrFail = [&Loaded](FCandidate& Candidate) -> UAnimSequenceBase*
		{
			++Loaded;
			return Cast<UAnimSequenceBase>(Candidate.Data.GetAsset());
		};
		if (Query.bLoop.IsSet())
		{
			if (Candidates.Num() > Query.MaxLoads)
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("reason"), TEXT("LOAD_LIMIT"));
				Details->SetNumberField(TEXT("candidates"), Candidates.Num());
				Details->SetNumberField(TEXT("max_loads"), Query.MaxLoads);
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest,
					FString::Printf(TEXT("loop is not an asset registry tag — %d candidate(s) would have to be loaded (max_loads %d). Narrow with query, skeleton, path_prefix or length"), Candidates.Num(), Query.MaxLoads), Details);
				return nullptr;
			}
			TArray<FCandidate> Kept;
			for (FCandidate& Candidate : Candidates)
			{
				const UAnimSequenceBase* Asset = LoadOrFail(Candidate);
				Candidate.bLoop = Asset ? TOptional<bool>(Asset->bLoop) : TOptional<bool>();
				if (Candidate.bLoop.IsSet() && Candidate.bLoop.GetValue() == Query.bLoop.GetValue())
				{
					Kept.Add(MoveTemp(Candidate));
				}
			}
			Candidates = MoveTemp(Kept);
		}

		const int32 Returned = FMath::Min(Candidates.Num(), Query.bDetails ? FMath::Min(Query.Limit, Query.MaxLoads) : Query.Limit);
		TArray<TSharedPtr<FJsonValue>> Items;
		for (int32 i = 0; i < Returned; ++i)
		{
			FCandidate& Candidate = Candidates[i];
			const FAssetData& Data = Candidate.Data;
			TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
			Item->SetStringField(TEXT("asset_path"), Data.GetObjectPathString());
			Item->SetStringField(TEXT("name"), Data.AssetName.ToString());
			Item->SetStringField(TEXT("class"), Data.AssetClassPath.GetAssetName().ToString());
			FString SkeletonValue;
			Data.GetTagValue(SkeletonTag, SkeletonValue);
			Item->SetField(TEXT("skeleton"), AnimMcpJson::StringOrNull(SkeletonValue.IsEmpty() ? FString() : FPackageName::ExportTextPathToObjectPath(SkeletonValue)));
			SetOptionalNumber(Item, TEXT("length"), TagNumber(Data, TEXT("SequenceLength")));
			SetOptionalNumber(Item, TEXT("frames"), TagNumber(Data, TEXT("Number of Frames")), 0);
			SetOptionalNumber(Item, TEXT("frame_rate"), TagNumber(Data, TEXT("Source Frame Rate")), 2);
			const TOptional<bool> RootMotion = TagBool(Data, TEXT("bEnableRootMotion"));
			if (RootMotion.IsSet()) { Item->SetBoolField(TEXT("root_motion"), RootMotion.GetValue()); }
			else { Item->SetField(TEXT("root_motion"), MakeShared<FJsonValueNull>()); }
			FString Additive;
			Data.GetTagValue(FName(TEXT("AdditiveAnimType")), Additive);
			Item->SetField(TEXT("additive_type"), AnimMcpJson::StringOrNull(Additive));
			if (Query.bDetails)
			{
				// loop 필터가 이미 로드했으면 다시 세지 않는다
				UAnimSequenceBase* Asset = Candidate.bLoop.IsSet() ? Cast<UAnimSequenceBase>(Data.GetAsset()) : LoadOrFail(Candidate);
				if (Asset)
				{
					Candidate.bLoop = Asset->bLoop;
					AddDetails(Asset, Item);
				}
			}
			if (Candidate.bLoop.IsSet()) { Item->SetBoolField(TEXT("loop"), Candidate.bLoop.GetValue()); }
			else { Item->SetField(TEXT("loop"), MakeShared<FJsonValueNull>()); }
			Item->SetArrayField(TEXT("tags"), AnimMcpGeneration::ToJsonArray(Candidate.Tags));
			Item->SetNumberField(TEXT("score"), AnimMcpStats::Round(Candidate.Score, 2));
			Item->SetArrayField(TEXT("matched"), AnimMcpGeneration::ToJsonArray(Candidate.Matched));
			Items.Add(MakeShared<FJsonValueObject>(Item));
		}

		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetNumberField(TEXT("total"), Candidates.Num());
		Result->SetNumberField(TEXT("returned"), Items.Num());
		Result->SetBoolField(TEXT("truncated"), Items.Num() < Candidates.Num());
		Result->SetArrayField(TEXT("items"), Items);
		Result->SetNumberField(TEXT("loaded"), Loaded);
		Result->SetArrayField(TEXT("tag_files"), AnimMcpGeneration::ToJsonArray(AnimMcpGeneration::GetSettings().AnimationTagFiles));
		Result->SetArrayField(TEXT("query_tokens"), AnimMcpGeneration::ToJsonArray(Query.Tokens));

		TArray<FString> Allowed, Unexpected;
		Guard.GetNewlyDirty(Allowed, Unexpected);
		Unexpected.Append(Allowed);
		if (Unexpected.Num() > 0)
		{
			Context.AddDiagnostic(TEXT("warning"), AnimMcpErrorCodes::UnexpectedDirty,
				FString::Printf(TEXT("Loading for the search left %d package(s) dirty: %s"), Unexpected.Num(), *FString::Join(Unexpected, TEXT(", "))));
		}
		return Result;
	}
}
