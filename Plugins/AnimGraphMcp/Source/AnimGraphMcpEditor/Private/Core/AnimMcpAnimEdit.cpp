#include "AnimMcpAnimEdit.h"

#include "AnimMcpAnimEditOps.h"
#include "AnimMcpAnimValidator.h"
#include "AnimMcpAssetResolver.h"
#include "AnimMcpGeneration.h"
#include "AnimMcpLog.h"
#include "AnimMcpStats.h"
#include "Animation/AnimData/IAnimationDataController.h"
#include "Animation/AnimData/IAnimationDataModel.h"
#include "Animation/AnimNotifies/AnimNotify.h"
#include "Animation/AnimNotifies/AnimNotifyState.h"
#include "Animation/AnimSequence.h"
#include "Animation/MirrorDataTable.h"
#include "Animation/Skeleton.h"
#include "Bridge/AnimMcpTypes.h"
#include "HAL/PlatformTime.h"
#include "UObject/Package.h"

#define LOCTEXT_NAMESPACE "AnimMcpAnimEdit"

namespace AnimMcpAnimEdit
{
	using namespace AnimMcpAnimEditOps;

	const TCHAR* const OperationsDoc =
		TEXT("Operations (times in seconds on the timeline as it is before that op; start/end default to the whole clip; ranges snap to the nearest frame): "
		     "trim {start?, end?} | "
		     "retime {start?, end?, rate | duration} (rate 1.5 = that range plays 1.5x faster) | "
		     "hold_pose {at, duration} (freeze the pose at 'at'; at = end extends the clip) | "
		     "concat {asset? (AnimSequence on the same skeleton; default the original source), start?, end? (on that asset), reverse? (false), blend? (seconds of crossfade, 0 = the segment's first key overlaps the current last key), align_root? (true: the segment's root continues from the current root position and yaw)} | "
		     "mirror {axis? (x|y|z; default x or the table's), mirror_table? (MirrorDataTable path; default the project's Animation settings mirror rules)} — unpaired bones mirror onto themselves | "
		     "offset_bone {targets[{bone, rotation?{pitch, yaw, roll}, translation?[x,y,z]}], space? (component: rotate about component axes at the bone, children follow; local: bone axes / parent-space move), start?, end?, blend_in? (0.2), blend_out? (0.2)} | "
		     "rotate_root {yaw, start?, end?, ease? (smooth|linear)} (root yaw ramps 0 → yaw over the range and stays; root motion after the start turns with it).");

	namespace
	{
		/** 결과 길이 상한 — 버퍼 메모리(키 × 본) 보호 */
		constexpr double MaxLengthSeconds = 120.0;

		enum class EOpKind : uint8 { Trim, Retime, HoldPose, Concat, Mirror, OffsetBone, RotateRoot };

		struct FParsedOp
		{
			int32 Index = 0;
			FString Name;
			EOpKind Kind = EOpKind::Trim;
			TOptional<double> Start;
			TOptional<double> End;
			// retime
			TOptional<double> Rate;
			TOptional<double> Duration;
			// hold_pose
			double At = 0.0;
			double HoldDuration = 0.0;
			// concat
			int32 Source = 0;
			bool bReverse = false;
			double Blend = 0.0;
			bool bAlignRoot = true;
			// mirror
			TOptional<EAxis::Type> Axis;
			UMirrorDataTable* MirrorTable = nullptr;
			// offset_bone
			TArray<FBoneOffset> Targets;
			bool bComponentSpace = true;
			double BlendIn = 0.2;
			double BlendOut = 0.2;
			// rotate_root
			double Yaw = 0.0;
			bool bSmooth = true;
		};

		/** 노티파이·싱크 마커 이동 결과 */
		struct FMovedEvent
		{
			int32 Source = 0;
			int32 Index = 0;
			double Time = 0.0;
			double Duration = 0.0;
			bool bTruncated = false;
		};

		struct FState
		{
			USkeleton* Skeleton = nullptr;
			FRig Rig;
			/** [0] = 주 소스 */
			TArray<UAnimSequence*> Sources;
			TArray<FSource> SourceData;
			TArray<FParsedOp> Ops;
			FClip Clip;
			TArray<TSharedPtr<FJsonValue>> Planned;
			bool bValid = true;
			/** 커브 이름 → (플래그, 색) — 먼저 나온 소스 기준 */
			TMap<FName, TPair<int32, FLinearColor>> CurveMeta;
			TArray<FName> FilledCurves;
			TArray<FString> Limitations;
			TArray<FMovedEvent> Notifies;
			TArray<FMovedEvent> SyncMarkers;
			TArray<TSharedPtr<FJsonValue>> DroppedNotifies;
			int32 DroppedSyncMarkers = 0;
			bool bMirroredWithCurves = false;
		};

		TSharedRef<FJsonObject> ErrorJson(const FString& Code, const FString& Message)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("code"), Code);
			Obj->SetStringField(TEXT("message"), Message);
			return Obj;
		}

		TSharedRef<FJsonObject> PlannedJson(int32 Index, const FString& Name)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetNumberField(TEXT("index"), Index);
			Obj->SetStringField(TEXT("op"), Name);
			return Obj;
		}

		// ---- 파싱 ----

		/** 키 검사 — op 마다 허용 목록 밖 키는 오타로 보고 거부한다 */
		bool CheckKeys(const FJsonObject& Json, std::initializer_list<const TCHAR*> Allowed, FString& OutCode, FString& OutMessage)
		{
			for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : Json.Values)
			{
				if (Pair.Key == TEXT("op"))
				{
					continue;
				}
				bool bKnown = false;
				for (const TCHAR* Key : Allowed) { bKnown |= Pair.Key == Key; }
				if (!bKnown)
				{
					TArray<FString> Names;
					for (const TCHAR* Key : Allowed) { Names.Add(Key); }
					OutCode = TEXT("BAD_OP");
					OutMessage = FString::Printf(TEXT("unknown key '%s' (allowed: %s)"), *Pair.Key, *FString::Join(Names, TEXT(", ")));
					return false;
				}
			}
			return true;
		}

		bool ReadNumber(const FJsonObject& Json, const TCHAR* Key, TOptional<double>& Out, FString& OutCode, FString& OutMessage)
		{
			const TSharedPtr<FJsonValue> Value = Json.TryGetField(Key);
			if (!Value.IsValid() || Value->Type == EJson::Null)
			{
				return true;
			}
			if (Value->Type != EJson::Number)
			{
				OutCode = TEXT("BAD_OP");
				OutMessage = FString::Printf(TEXT("'%s' must be a number"), Key);
				return false;
			}
			Out = Value->AsNumber();
			return true;
		}

		bool ReadBool(const FJsonObject& Json, const TCHAR* Key, bool& Out, FString& OutCode, FString& OutMessage)
		{
			const TSharedPtr<FJsonValue> Value = Json.TryGetField(Key);
			if (!Value.IsValid() || Value->Type == EJson::Null)
			{
				return true;
			}
			if (Value->Type != EJson::Boolean)
			{
				OutCode = TEXT("BAD_OP");
				OutMessage = FString::Printf(TEXT("'%s' must be a boolean"), Key);
				return false;
			}
			Out = Value->AsBool();
			return true;
		}

		bool RequireNumber(const FJsonObject& Json, const TCHAR* Key, double& Out, FString& OutCode, FString& OutMessage)
		{
			TOptional<double> Value;
			if (!ReadNumber(Json, Key, Value, OutCode, OutMessage))
			{
				return false;
			}
			if (!Value.IsSet())
			{
				OutCode = TEXT("BAD_OP");
				OutMessage = FString::Printf(TEXT("missing required number '%s'"), Key);
				return false;
			}
			Out = Value.GetValue();
			return true;
		}

		/** concat 소스 — 주 소스와 같은 스켈레톤만. 이미 있으면 그 번호 */
		bool AddSource(FState& State, const FString& Path, int32& OutIndex, FString& OutCode, FString& OutMessage)
		{
			FAnimMcpError Error;
			UAnimSequence* Sequence = Cast<UAnimSequence>(AnimMcpAssetResolver::LoadAssetOfClass(Path, UAnimSequence::StaticClass(), Error));
			if (!Sequence)
			{
				OutCode = Error.Code;
				OutMessage = Error.Message;
				return false;
			}
			if (Sequence->GetSkeleton() != State.Skeleton)
			{
				OutCode = TEXT("SKELETON_MISMATCH");
				OutMessage = FString::Printf(TEXT("'%s' is on '%s', the source on '%s' — retarget it first (retarget_animations)"),
					*Sequence->GetPathName(), *GetPathNameSafe(Sequence->GetSkeleton()), *GetPathNameSafe(State.Skeleton));
				return false;
			}
			OutIndex = State.Sources.AddUnique(Sequence);
			return true;
		}

		bool ParseOp(FState& State, const TSharedPtr<FJsonValue>& Value, int32 Index, FParsedOp& Op, FString& OutCode, FString& OutMessage)
		{
			Op.Index = Index;
			const TSharedPtr<FJsonObject>* JsonPtr = nullptr;
			if (!Value.IsValid() || !Value->TryGetObject(JsonPtr) || !JsonPtr->IsValid())
			{
				OutCode = TEXT("BAD_OP");
				OutMessage = TEXT("each operation must be an object {op, ...}");
				return false;
			}
			const FJsonObject& Json = **JsonPtr;
			if (!Json.TryGetStringField(TEXT("op"), Op.Name) || Op.Name.IsEmpty())
			{
				OutCode = TEXT("BAD_OP");
				OutMessage = TEXT("missing 'op'");
				return false;
			}
			if (!ReadNumber(Json, TEXT("start"), Op.Start, OutCode, OutMessage) || !ReadNumber(Json, TEXT("end"), Op.End, OutCode, OutMessage))
			{
				return false;
			}
			if ((Op.Start.IsSet() && Op.Start.GetValue() < 0.0) || (Op.End.IsSet() && Op.End.GetValue() < 0.0))
			{
				OutCode = TEXT("OUT_OF_RANGE");
				OutMessage = TEXT("start/end must be >= 0");
				return false;
			}

			if (Op.Name == TEXT("trim"))
			{
				Op.Kind = EOpKind::Trim;
				return CheckKeys(Json, { TEXT("start"), TEXT("end") }, OutCode, OutMessage);
			}
			if (Op.Name == TEXT("retime"))
			{
				Op.Kind = EOpKind::Retime;
				if (!CheckKeys(Json, { TEXT("start"), TEXT("end"), TEXT("rate"), TEXT("duration") }, OutCode, OutMessage)
					|| !ReadNumber(Json, TEXT("rate"), Op.Rate, OutCode, OutMessage) || !ReadNumber(Json, TEXT("duration"), Op.Duration, OutCode, OutMessage))
				{
					return false;
				}
				if (Op.Rate.IsSet() == Op.Duration.IsSet())
				{
					OutCode = TEXT("BAD_OP");
					OutMessage = TEXT("retime needs exactly one of rate or duration");
					return false;
				}
				if ((Op.Rate.IsSet() && Op.Rate.GetValue() <= 0.0) || (Op.Duration.IsSet() && Op.Duration.GetValue() <= 0.0))
				{
					OutCode = TEXT("OUT_OF_RANGE");
					OutMessage = TEXT("retime rate/duration must be > 0");
					return false;
				}
				return true;
			}
			if (Op.Name == TEXT("hold_pose"))
			{
				Op.Kind = EOpKind::HoldPose;
				if (!CheckKeys(Json, { TEXT("at"), TEXT("duration") }, OutCode, OutMessage)
					|| !RequireNumber(Json, TEXT("at"), Op.At, OutCode, OutMessage) || !RequireNumber(Json, TEXT("duration"), Op.HoldDuration, OutCode, OutMessage))
				{
					return false;
				}
				if (Op.At < 0.0 || Op.HoldDuration <= 0.0)
				{
					OutCode = TEXT("OUT_OF_RANGE");
					OutMessage = TEXT("hold_pose needs at >= 0 and duration > 0");
					return false;
				}
				return true;
			}
			if (Op.Name == TEXT("concat"))
			{
				Op.Kind = EOpKind::Concat;
				if (!CheckKeys(Json, { TEXT("asset"), TEXT("start"), TEXT("end"), TEXT("reverse"), TEXT("blend"), TEXT("align_root") }, OutCode, OutMessage)
					|| !ReadBool(Json, TEXT("reverse"), Op.bReverse, OutCode, OutMessage) || !ReadBool(Json, TEXT("align_root"), Op.bAlignRoot, OutCode, OutMessage))
				{
					return false;
				}
				TOptional<double> Blend;
				if (!ReadNumber(Json, TEXT("blend"), Blend, OutCode, OutMessage))
				{
					return false;
				}
				Op.Blend = Blend.Get(0.0);
				if (Op.Blend < 0.0)
				{
					OutCode = TEXT("OUT_OF_RANGE");
					OutMessage = TEXT("blend must be >= 0");
					return false;
				}
				FString Asset;
				Op.Source = 0;
				if (Json.TryGetStringField(TEXT("asset"), Asset) && !Asset.IsEmpty())
				{
					return AddSource(State, Asset, Op.Source, OutCode, OutMessage);
				}
				return true;
			}
			if (Op.Name == TEXT("mirror"))
			{
				Op.Kind = EOpKind::Mirror;
				if (!CheckKeys(Json, { TEXT("axis"), TEXT("mirror_table") }, OutCode, OutMessage))
				{
					return false;
				}
				FString Axis;
				if (Json.TryGetStringField(TEXT("axis"), Axis))
				{
					Axis = Axis.ToLower();
					if (Axis == TEXT("x")) { Op.Axis = EAxis::X; }
					else if (Axis == TEXT("y")) { Op.Axis = EAxis::Y; }
					else if (Axis == TEXT("z")) { Op.Axis = EAxis::Z; }
					else
					{
						OutCode = TEXT("BAD_OP");
						OutMessage = FString::Printf(TEXT("axis must be x, y or z (got '%s')"), *Axis);
						return false;
					}
				}
				FString Table;
				if (Json.TryGetStringField(TEXT("mirror_table"), Table) && !Table.IsEmpty())
				{
					FAnimMcpError Error;
					Op.MirrorTable = Cast<UMirrorDataTable>(AnimMcpAssetResolver::LoadAssetOfClass(Table, UMirrorDataTable::StaticClass(), Error));
					if (!Op.MirrorTable)
					{
						OutCode = Error.Code;
						OutMessage = Error.Message;
						return false;
					}
				}
				return true;
			}
			if (Op.Name == TEXT("offset_bone"))
			{
				Op.Kind = EOpKind::OffsetBone;
				if (!CheckKeys(Json, { TEXT("targets"), TEXT("space"), TEXT("start"), TEXT("end"), TEXT("blend_in"), TEXT("blend_out") }, OutCode, OutMessage))
				{
					return false;
				}
				FString Space;
				if (Json.TryGetStringField(TEXT("space"), Space))
				{
					if (Space != TEXT("component") && Space != TEXT("local"))
					{
						OutCode = TEXT("BAD_OP");
						OutMessage = FString::Printf(TEXT("space must be component or local (got '%s')"), *Space);
						return false;
					}
					Op.bComponentSpace = Space == TEXT("component");
				}
				TOptional<double> BlendIn, BlendOut;
				if (!ReadNumber(Json, TEXT("blend_in"), BlendIn, OutCode, OutMessage) || !ReadNumber(Json, TEXT("blend_out"), BlendOut, OutCode, OutMessage))
				{
					return false;
				}
				Op.BlendIn = BlendIn.Get(0.2);
				Op.BlendOut = BlendOut.Get(0.2);
				const TArray<TSharedPtr<FJsonValue>>* Targets = nullptr;
				if (!Json.TryGetArrayField(TEXT("targets"), Targets) || Targets->Num() == 0)
				{
					OutCode = TEXT("BAD_OP");
					OutMessage = TEXT("offset_bone needs targets[{bone, rotation?{pitch,yaw,roll}, translation?[x,y,z]}]");
					return false;
				}
				for (const TSharedPtr<FJsonValue>& TargetValue : *Targets)
				{
					const TSharedPtr<FJsonObject>* TargetPtr = nullptr;
					FString Bone;
					if (!TargetValue.IsValid() || !TargetValue->TryGetObject(TargetPtr) || !(*TargetPtr)->TryGetStringField(TEXT("bone"), Bone))
					{
						OutCode = TEXT("BAD_OP");
						OutMessage = TEXT("each target needs 'bone'");
						return false;
					}
					const FJsonObject& Target = **TargetPtr;
					if (!CheckKeys(Target, { TEXT("bone"), TEXT("rotation"), TEXT("translation") }, OutCode, OutMessage))
					{
						return false;
					}
					FBoneOffset Offset;
					Offset.Bone = State.Rig.Find(FName(*Bone));
					if (Offset.Bone == INDEX_NONE)
					{
						OutCode = TEXT("BONE_NOT_FOUND");
						OutMessage = FString::Printf(TEXT("bone '%s' is not in skeleton '%s'"), *Bone, *GetPathNameSafe(State.Skeleton));
						return false;
					}
					if (Op.Targets.ContainsByPredicate([&Offset](const FBoneOffset& Other) { return Other.Bone == Offset.Bone; }))
					{
						OutCode = TEXT("BAD_OP");
						OutMessage = FString::Printf(TEXT("bone '%s' is listed twice"), *Bone);
						return false;
					}
					const TSharedPtr<FJsonObject>* Rotation = nullptr;
					const TArray<TSharedPtr<FJsonValue>>* Translation = nullptr;
					const bool bRotation = Target.TryGetObjectField(TEXT("rotation"), Rotation);
					const bool bTranslation = Target.TryGetArrayField(TEXT("translation"), Translation);
					if (!bRotation && !bTranslation)
					{
						OutCode = TEXT("BAD_OP");
						OutMessage = FString::Printf(TEXT("target '%s' needs rotation{pitch,yaw,roll} and/or translation[x,y,z]"), *Bone);
						return false;
					}
					if (bRotation)
					{
						if (!CheckKeys(**Rotation, { TEXT("pitch"), TEXT("yaw"), TEXT("roll") }, OutCode, OutMessage))
						{
							return false;
						}
						TOptional<double> Pitch, Yaw, Roll;
						if (!ReadNumber(**Rotation, TEXT("pitch"), Pitch, OutCode, OutMessage) || !ReadNumber(**Rotation, TEXT("yaw"), Yaw, OutCode, OutMessage)
							|| !ReadNumber(**Rotation, TEXT("roll"), Roll, OutCode, OutMessage))
						{
							return false;
						}
						Offset.Rotation = FRotator(Pitch.Get(0.0), Yaw.Get(0.0), Roll.Get(0.0)).Quaternion();
					}
					if (bTranslation)
					{
						if (Translation->Num() != 3 || Translation->ContainsByPredicate([](const TSharedPtr<FJsonValue>& V) { return !V.IsValid() || V->Type != EJson::Number; }))
						{
							OutCode = TEXT("BAD_OP");
							OutMessage = FString::Printf(TEXT("target '%s' translation must be [x, y, z]"), *Bone);
							return false;
						}
						Offset.Translation = FVector((*Translation)[0]->AsNumber(), (*Translation)[1]->AsNumber(), (*Translation)[2]->AsNumber());
					}
					Op.Targets.Add(Offset);
				}
				return true;
			}
			if (Op.Name == TEXT("rotate_root"))
			{
				Op.Kind = EOpKind::RotateRoot;
				if (!CheckKeys(Json, { TEXT("yaw"), TEXT("start"), TEXT("end"), TEXT("ease") }, OutCode, OutMessage)
					|| !RequireNumber(Json, TEXT("yaw"), Op.Yaw, OutCode, OutMessage))
				{
					return false;
				}
				FString Ease;
				if (Json.TryGetStringField(TEXT("ease"), Ease))
				{
					if (Ease != TEXT("smooth") && Ease != TEXT("linear"))
					{
						OutCode = TEXT("BAD_OP");
						OutMessage = FString::Printf(TEXT("ease must be smooth or linear (got '%s')"), *Ease);
						return false;
					}
					Op.bSmooth = Ease == TEXT("smooth");
				}
				return true;
			}
			OutCode = TEXT("BAD_OP");
			OutMessage = FString::Printf(TEXT("unknown op '%s' (trim, retime, hold_pose, concat, mirror, offset_bone, rotate_root)"), *Op.Name);
			return false;
		}

		// ---- 소스 읽기 ----

		void BuildRig(const USkeleton* Skeleton, FRig& Rig)
		{
			// 가상 본은 트랙이 없다 — raw 본만
			const FReferenceSkeleton& Ref = Skeleton->GetReferenceSkeleton();
			const int32 Num = Ref.GetRawBoneNum();
			for (int32 Bone = 0; Bone < Num; ++Bone)
			{
				Rig.Bones.Add(Ref.GetBoneName(Bone));
				Rig.Parents.Add(Ref.GetRawParentIndex(Bone));
				Rig.RefLocal.Add(Ref.GetRawRefBonePose()[Bone]);
			}
			Rig.Finalize();
		}

		void ReadSource(FState& State, int32 Index, FAnimMcpContext& Context)
		{
			const UAnimSequence* Sequence = State.Sources[Index];
			const IAnimationDataModel* Model = Sequence->GetDataModel();
			FSource& Out = State.SourceData[Index];
			Out.FrameRate = Model->GetFrameRate().AsDecimal();
			Out.NumKeys = Model->GetNumberOfKeys();
			Out.bStep = Sequence->Interpolation == EAnimInterpolationType::Step;
			Out.Tracks.SetNum(State.Rig.Num());
			TArray<FName> TrackNames;
			Model->GetBoneTrackNames(TrackNames);
			TArray<FString> Missing;
			for (const FName& Name : TrackNames)
			{
				const int32 Bone = State.Rig.Find(Name);
				if (Bone == INDEX_NONE)
				{
					Missing.Add(Name.ToString());
					continue;
				}
				TArray<FTransform>& Track = Out.Tracks[Bone];
				Model->GetBoneTrackTransforms(Name, Track);
				// 키 수가 모델과 다르면 끝 키로 맞춘다 (방어)
				if (Track.Num() > Out.NumKeys) { Track.SetNum(Out.NumKeys); }
				while (Track.Num() > 0 && Track.Num() < Out.NumKeys) { Track.Add(Track.Last()); }
			}
			for (const FFloatCurve& Curve : Model->GetFloatCurves())
			{
				Out.CurveNames.Add(Curve.GetName());
				Out.Curves.Add(Curve.FloatCurve);
				if (!State.CurveMeta.Contains(Curve.GetName()))
				{
					State.CurveMeta.Add(Curve.GetName(), TPair<int32, FLinearColor>(Curve.GetCurveTypeFlags(), Curve.Color));
				}
			}
			const FString Name = Sequence->GetName();
			if (Missing.Num() > 0)
			{
				Context.AddDiagnostic(TEXT("warning"), TEXT("TRACKS_NOT_IN_SKELETON"),
					FString::Printf(TEXT("%s: %d bone track(s) are not in the skeleton and are dropped: %s"), *Name, Missing.Num(), *FString::Join(Missing, TEXT(", "))));
			}
			if (Model->GetNumberOfTransformCurves() > 0)
			{
				Context.AddDiagnostic(TEXT("warning"), TEXT("TRANSFORM_CURVES_DROPPED"),
					FString::Printf(TEXT("%s has %d transform curve(s) (additive layer tracks) — raw keys do not include them; the result has none"), *Name, Model->GetNumberOfTransformCurves()));
				State.Limitations.Add(FString::Printf(TEXT("%s: transform curves dropped"), *Name));
			}
			if (Model->GetNumberOfAttributes() > 0)
			{
				Context.AddDiagnostic(TEXT("warning"), TEXT("ATTRIBUTES_DROPPED"),
					FString::Printf(TEXT("%s has %d bone attribute(s) — not carried over to the edited timeline"), *Name, Model->GetNumberOfAttributes()));
				State.Limitations.Add(FString::Printf(TEXT("%s: bone attributes dropped"), *Name));
			}
		}

		// ---- 적용 ----

		/** 소스 시각 → 출력 시각. 출처가 같은 소스의 정방향인 첫 구간만 (포즈 유지 구간은 시각이 늘지 않아 건너뛴다) */
		TOptional<double> MapTime(const FClip& Clip, int32 Source, double SourceTime, int32* OutKey = nullptr)
		{
			constexpr double Eps = 1e-4;
			const int32 N = Clip.NumKeys();
			for (int32 Key = 0; Key < N; ++Key)
			{
				const FProvenance& P = Clip.Provenance[Key];
				if (P.Source != Source || P.bReversed)
				{
					continue;
				}
				if (FMath::Abs(P.Time - SourceTime) <= Eps)
				{
					if (OutKey) { *OutKey = Key; }
					return Key / Clip.FrameRate;
				}
				if (Key + 1 < N)
				{
					const FProvenance& Q = Clip.Provenance[Key + 1];
					if (Q.Source == Source && !Q.bReversed && Q.Time > P.Time + Eps && SourceTime > P.Time && SourceTime < Q.Time)
					{
						if (OutKey) { *OutKey = Key; }
						return (Key + (SourceTime - P.Time) / (Q.Time - P.Time)) / Clip.FrameRate;
					}
				}
			}
			return {};
		}

		/** 키부터 이어지는 같은 소스 정방향 구간의 끝 시각 — 길이 노티파이를 자를 때 */
		double RunEnd(const FClip& Clip, int32 Source, int32 Key)
		{
			while (Key + 1 < Clip.NumKeys())
			{
				const FProvenance& P = Clip.Provenance[Key];
				const FProvenance& Q = Clip.Provenance[Key + 1];
				if (Q.Source != Source || Q.bReversed || Q.Time < P.Time)
				{
					break;
				}
				++Key;
			}
			return Key / Clip.FrameRate;
		}

		void MoveEvents(FState& State)
		{
			for (int32 Source = 0; Source < State.Sources.Num(); ++Source)
			{
				const UAnimSequence* Sequence = State.Sources[Source];
				for (int32 i = 0; i < Sequence->Notifies.Num(); ++i)
				{
					const FAnimNotifyEvent& Event = Sequence->Notifies[i];
					const double Time = Event.GetTime();
					const double Duration = Event.GetDuration();
					int32 Key = INDEX_NONE;
					const TOptional<double> Mapped = MapTime(State.Clip, Source, Time, &Key);
					if (!Mapped.IsSet())
					{
						TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
						Item->SetStringField(TEXT("source"), Sequence->GetName());
						Item->SetStringField(TEXT("name"), Event.NotifyName.ToString());
						Item->SetNumberField(TEXT("time"), AnimMcpStats::Round(Time, 4));
						State.DroppedNotifies.Add(MakeShared<FJsonValueObject>(Item));
						continue;
					}
					FMovedEvent Moved{ Source, i, Mapped.GetValue(), 0.0, false };
					if (Duration > 0.0)
					{
						const TOptional<double> MappedEnd = MapTime(State.Clip, Source, Time + Duration);
						if (MappedEnd.IsSet() && MappedEnd.GetValue() > Moved.Time)
						{
							Moved.Duration = MappedEnd.GetValue() - Moved.Time;
						}
						else
						{
							Moved.Duration = FMath::Max(0.0, RunEnd(State.Clip, Source, Key) - Moved.Time);
							Moved.bTruncated = true;
						}
					}
					State.Notifies.Add(Moved);
				}
				for (int32 i = 0; i < Sequence->AuthoredSyncMarkers.Num(); ++i)
				{
					const TOptional<double> Mapped = MapTime(State.Clip, Source, Sequence->AuthoredSyncMarkers[i].Time);
					if (Mapped.IsSet())
					{
						State.SyncMarkers.Add(FMovedEvent{ Source, i, Mapped.GetValue(), 0.0, false });
					}
					else
					{
						++State.DroppedSyncMarkers;
					}
				}
			}
		}

		bool ApplyOp(FState& State, FParsedOp& Op, FReport& Report, FString& OutCode, FString& OutMessage)
		{
			FClip& Clip = State.Clip;
			const double Length = Clip.Length();
			const double Half = 0.5 / Clip.FrameRate;
			const double Start = Op.Start.Get(0.0);
			const double End = Op.End.Get(Length);
			auto CheckRange = [&](double S, double E, double Max) -> bool
			{
				if (S > Max + Half || E > Max + Half || S >= E)
				{
					OutCode = TEXT("OUT_OF_RANGE");
					OutMessage = FString::Printf(TEXT("range %.4f..%.4fs is outside 0..%.4fs (or empty)"), S, E, Max);
					return false;
				}
				return true;
			};
			OutCode = TEXT("BAD_RANGE");
			switch (Op.Kind)
			{
			case EOpKind::Trim:
				return CheckRange(Start, End, Length) && Trim(Clip, Start, End, Report, OutMessage);
			case EOpKind::Retime:
			{
				if (!CheckRange(Start, End, Length))
				{
					return false;
				}
				double Rate = Op.Rate.Get(1.0);
				if (Op.Duration.IsSet())
				{
					const double Snapped = (Clip.TimeToKey(End) - Clip.TimeToKey(Start)) / Clip.FrameRate;
					Rate = Snapped / Op.Duration.GetValue();
				}
				return Retime(Clip, Start, End, Rate, Report, OutMessage);
			}
			case EOpKind::HoldPose:
				if (Op.At > Length + Half)
				{
					OutCode = TEXT("OUT_OF_RANGE");
					OutMessage = FString::Printf(TEXT("at %.4fs is beyond the clip (%.4fs)"), Op.At, Length);
					return false;
				}
				return HoldPose(Clip, Op.At, Op.HoldDuration, Report, OutMessage);
			case EOpKind::Concat:
			{
				const FSource& Source = State.SourceData[Op.Source];
				const double SourceStart = Op.Start.Get(0.0);
				const double SourceEnd = Op.End.Get(Source.Length());
				if (!CheckRange(SourceStart, SourceEnd, Source.Length()))
				{
					OutMessage += FString::Printf(TEXT(" — concat start/end are on '%s'"), *State.Sources[Op.Source]->GetName());
					return false;
				}
				FClip Segment;
				Sample(State.Rig, Source, Op.Source, Clip.FrameRate, SourceStart, SourceEnd, Op.bReverse, Segment);
				if (!Concat(Clip, MoveTemp(Segment), Op.Blend, Op.bAlignRoot, Report, OutMessage))
				{
					return false;
				}
				for (const FName& Name : Report.FilledCurves) { State.FilledCurves.AddUnique(Name); }
				if (Op.bReverse)
				{
					Report.Note += TEXT(" (reversed — its notifies are not copied)");
				}
				return true;
			}
			case EOpKind::Mirror:
			{
				TArray<int32> Pairs;
				EAxis::Type Axis = Op.Axis.Get(EAxis::X);
				if (Op.MirrorTable)
				{
					TCustomBoneIndexArray<FSkeletonPoseBoneIndex, FSkeletonPoseBoneIndex> Indexes;
					Op.MirrorTable->FillMirrorBoneIndexes(State.Skeleton, Indexes);
					// 엔진은 짝 없는 본을 반전하지 않는다(INDEX_NONE — MirrorDataTable.cpp FillMirrorBoneIndexes). 전신 반전이 되도록 자기 자신으로 둔다
					Pairs = MirrorPairs(State.Rig, [&State, &Indexes](FName Bone)
					{
						const int32 Index = State.Rig.Find(Bone);
						const int32 Other = Indexes.IsValidIndex(Index) ? Indexes[FSkeletonPoseBoneIndex(Index)].GetInt() : INDEX_NONE;
						return State.Rig.Bones.IsValidIndex(Other) ? State.Rig.Bones[Other] : NAME_None;
					});
					if (!Op.Axis.IsSet())
					{
						Axis = Op.MirrorTable->MirrorAxis;
					}
					if (Op.MirrorTable->Skeleton && Op.MirrorTable->Skeleton != State.Skeleton)
					{
						Report.Note = FString::Printf(TEXT("mirror table is for '%s' — pairs matched by bone name"), *GetPathNameSafe(Op.MirrorTable->Skeleton));
					}
				}
				else
				{
					Pairs = MirrorPairs(State.Rig, [](FName Bone) { return UMirrorDataTable::GetSettingsMirrorName(Bone); });
				}
				int32 PairCount = 0;
				for (int32 Bone = 0; Bone < Pairs.Num(); ++Bone) { PairCount += Pairs[Bone] > Bone ? 1 : 0; }
				Report.LengthBefore = Report.LengthAfter = Length;
				Report.End = Length;
				Report.EndKey = Clip.NumKeys() - 1;
				if (PairCount == 0)
				{
					OutCode = TEXT("NO_MIRROR_PAIRS");
					OutMessage = TEXT("no left/right bone pairs found — set the project's Animation mirror rules or pass mirror_table");
					return false;
				}
				Mirror(State.Rig, Clip, Axis, Pairs);
				Report.Note = (Report.Note.IsEmpty() ? FString() : Report.Note + TEXT("; ")) + FString::Printf(TEXT("%d bone pair(s), axis %s"), PairCount, Axis == EAxis::X ? TEXT("X") : Axis == EAxis::Y ? TEXT("Y") : TEXT("Z"));
				// 커브·노티파이는 반전하지 않는다 — 부호 있는 커브(예: 남은 회전 Yaw)는 반대 방향 동작과 어긋난다
				if (Clip.CurveNames.Num() > 0)
				{
					State.Limitations.AddUnique(TEXT("mirror: curves keep their values (a signed curve such as a remaining-turn yaw now has the wrong sign)"));
					State.bMirroredWithCurves = true;
				}
				return true;
			}
			case EOpKind::OffsetBone:
				return CheckRange(Start, End, Length) && OffsetBones(State.Rig, Clip, Op.Targets, Op.bComponentSpace, Start, End, Op.BlendIn, Op.BlendOut, Report, OutMessage);
			case EOpKind::RotateRoot:
				return CheckRange(Start, End, Length) && RotateRoot(Clip, Op.Yaw, Start, End, Op.bSmooth, Report, OutMessage);
			}
			return false;
		}

		/** 파싱 → 소스 읽기 → 버퍼 → op 차례 적용. State.bValid 가 거짓이면 Planned 에 이유가 있다. 요청 자체의 오류만 false */
		bool Build(const FRequest& Request, FState& State, FAnimMcpContext& Context, FAnimMcpError& OutError)
		{
			UAnimSequence* Primary = Request.Source;
			State.Skeleton = Primary->GetSkeleton();
			if (!State.Skeleton || Primary->GetDataModel() == nullptr || Primary->GetDataModel()->GetNumberOfKeys() < 2)
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("field"), TEXT("source"));
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("'%s' has no skeleton or fewer than two keys"), *Primary->GetPathName()), Details);
				return false;
			}
			if (Request.Operations.Num() == 0)
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("field"), TEXT("operations"));
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("operations[] needs at least one op"), Details);
				return false;
			}
			BuildRig(State.Skeleton, State.Rig);
			if (State.Rig.Num() == 0 || State.Rig.Parents[0] != INDEX_NONE)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("Skeleton '%s' has no root bone at index 0"), *State.Skeleton->GetPathName()));
				return false;
			}
			State.Sources.Add(Primary);

			// 1) 전부 파싱 — 독립적으로 잡을 수 있는 오류는 모든 op 에 대해 한 번에 보고한다
			bool bParsed = true;
			for (int32 i = 0; i < Request.Operations.Num(); ++i)
			{
				FParsedOp& Op = State.Ops.AddDefaulted_GetRef();
				FString Code, Message;
				if (!ParseOp(State, Request.Operations[i], i, Op, Code, Message))
				{
					bParsed = false;
					TSharedRef<FJsonObject> Item = PlannedJson(i, Op.Name);
					Item->SetBoolField(TEXT("ok"), false);
					Item->SetObjectField(TEXT("error"), ErrorJson(Code, Message));
					State.Planned.Add(MakeShared<FJsonValueObject>(Item));
				}
				else
				{
					TSharedRef<FJsonObject> Item = PlannedJson(i, Op.Name);
					Item->SetBoolField(TEXT("ok"), true);
					State.Planned.Add(MakeShared<FJsonValueObject>(Item));
				}
			}
			if (!bParsed)
			{
				State.bValid = false;
				return true;
			}

			// 2) 소스 읽기 → 주 소스 전체를 버퍼로
			State.SourceData.SetNum(State.Sources.Num());
			for (int32 i = 0; i < State.Sources.Num(); ++i)
			{
				ReadSource(State, i, Context);
			}
			const FSource& PrimaryData = State.SourceData[0];
			Sample(State.Rig, PrimaryData, 0, PrimaryData.FrameRate, 0.0, PrimaryData.Length(), false, State.Clip);

			// 3) op 차례 적용 — 앞 op 결과가 뒤 op 의 타임라인이므로 첫 실패에서 멈춘다
			for (int32 i = 0; i < State.Ops.Num(); ++i)
			{
				FParsedOp& Op = State.Ops[i];
				TSharedRef<FJsonObject> Item = PlannedJson(i, Op.Name);
				if (!State.bValid)
				{
					Item->SetBoolField(TEXT("ok"), false);
					Item->SetBoolField(TEXT("skipped"), true);
					State.Planned[i] = MakeShared<FJsonValueObject>(Item);
					continue;
				}
				FReport Report;
				FString Code, Message;
				const bool bOk = ApplyOp(State, Op, Report, Code, Message);
				if (bOk && State.Clip.Length() > MaxLengthSeconds)
				{
					Code = TEXT("LIMIT");
					Message = FString::Printf(TEXT("the result would be %.2fs — over the %.0fs limit"), State.Clip.Length(), MaxLengthSeconds);
				}
				const bool bAccepted = bOk && Code != TEXT("LIMIT");
				Item->SetBoolField(TEXT("ok"), bAccepted);
				if (!bAccepted)
				{
					Item->SetObjectField(TEXT("error"), ErrorJson(Code, Message));
					State.bValid = false;
				}
				else
				{
					TSharedRef<FJsonObject> Range = AnimMcpJson::MakeObject();
					Range->SetNumberField(TEXT("start"), AnimMcpStats::Round(Report.Start, 4));
					Range->SetNumberField(TEXT("end"), AnimMcpStats::Round(Report.End, 4));
					Range->SetNumberField(TEXT("start_key"), Report.StartKey);
					Range->SetNumberField(TEXT("end_key"), Report.EndKey);
					Item->SetObjectField(TEXT("range"), Range);
					Item->SetNumberField(TEXT("length_before"), AnimMcpStats::Round(Report.LengthBefore, 4));
					Item->SetNumberField(TEXT("length_after"), AnimMcpStats::Round(Report.LengthAfter, 4));
					if (!Report.Note.IsEmpty())
					{
						Item->SetStringField(TEXT("note"), Report.Note);
					}
				}
				State.Planned[i] = MakeShared<FJsonValueObject>(Item);
			}
			if (State.bValid)
			{
				MoveEvents(State);
				if (State.FilledCurves.Num() > 0)
				{
					TArray<FString> Names;
					for (const FName& Name : State.FilledCurves) { Names.Add(Name.ToString()); }
					Context.AddDiagnostic(TEXT("info"), TEXT("CURVE_FILLED"),
						FString::Printf(TEXT("%d curve(s) exist on only one side of a concat and are 0 on the other: %s"), Names.Num(), *FString::Join(Names, TEXT(", "))));
				}
				if (State.bMirroredWithCurves)
				{
					TArray<FString> Names;
					for (const FName& Name : State.Clip.CurveNames) { Names.Add(Name.ToString()); }
					Context.AddDiagnostic(TEXT("warning"), TEXT("MIRROR_CURVES_UNCHANGED"),
						FString::Printf(TEXT("mirror flips bones only — curve values are kept as they are (check signed ones): %s"), *FString::Join(Names, TEXT(", "))));
				}
				if (State.DroppedNotifies.Num() > 0)
				{
					Context.AddDiagnostic(TEXT("warning"), TEXT("NOTIFIES_DROPPED"),
						FString::Printf(TEXT("%d notify(ies) fall in trimmed or reversed parts and are not in the result (result.notifies.dropped)"), State.DroppedNotifies.Num()));
					State.Limitations.Add(FString::Printf(TEXT("%d notify(ies) dropped"), State.DroppedNotifies.Num()));
				}
			}
			return true;
		}

		TArray<TSharedPtr<FJsonValue>> SeamsJson(const FState& State, double RatioMax)
		{
			const TArray<double> Steps = StepMeans(State.Rig, State.Clip);
			TArray<TSharedPtr<FJsonValue>> Items;
			for (const double Seam : State.Clip.Seams)
			{
				const int32 Frame = State.Clip.TimeToKey(Seam);
				const double Ratio = AnimMcpAnimValidator::SeamStepRatio(Steps, Frame);
				TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
				Item->SetNumberField(TEXT("time"), AnimMcpStats::Round(Seam, 4));
				Item->SetNumberField(TEXT("frame"), Frame);
				Item->SetNumberField(TEXT("step_ratio"), AnimMcpStats::Round(Ratio, 2));
				Item->SetBoolField(TEXT("jump"), Ratio > RatioMax);
				Items.Add(MakeShared<FJsonValueObject>(Item));
			}
			return Items;
		}

		TSharedRef<FJsonObject> SummaryJson(const FState& State)
		{
			const FClip& Clip = State.Clip;
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetNumberField(TEXT("frame_rate"), AnimMcpStats::Round(Clip.FrameRate));
			Obj->SetNumberField(TEXT("frames"), FMath::Max(0, Clip.NumKeys() - 1));
			Obj->SetNumberField(TEXT("length"), AnimMcpStats::Round(Clip.Length(), 4));
			int32 Tracks = 0;
			for (int32 Bone = 0; Bone < Clip.Animated.Num(); ++Bone) { Tracks += Clip.Animated[Bone] ? 1 : 0; }
			Obj->SetNumberField(TEXT("bone_tracks"), Tracks);
			TArray<FString> Curves;
			for (const FName& Name : Clip.CurveNames) { Curves.Add(Name.ToString()); }
			Obj->SetArrayField(TEXT("curves"), AnimMcpGeneration::ToJsonArray(Curves));
			Obj->SetNumberField(TEXT("root_yaw_delta_deg"), AnimMcpStats::Round(RootYawDelta(Clip), 2));
			if (Clip.NumKeys() > 0)
			{
				Obj->SetNumberField(TEXT("root_displacement_cm"), AnimMcpStats::Round(FVector::Dist(Clip.Keys.Last()[0].GetLocation(), Clip.Keys[0][0].GetLocation()), 2));
			}
			Obj->SetNumberField(TEXT("max_rate"), AnimMcpStats::Round(Clip.MaxRate, 3));
			TArray<TSharedPtr<FJsonValue>> Sources;
			for (const UAnimSequence* Source : State.Sources) { Sources.Add(MakeShared<FJsonValueString>(Source->GetPathName())); }
			Obj->SetArrayField(TEXT("sources"), Sources);
			TSharedRef<FJsonObject> Notifies = AnimMcpJson::MakeObject();
			Notifies->SetNumberField(TEXT("kept"), State.Notifies.Num());
			Notifies->SetNumberField(TEXT("truncated"), State.Notifies.FilterByPredicate([](const FMovedEvent& E) { return E.bTruncated; }).Num());
			Notifies->SetArrayField(TEXT("dropped"), State.DroppedNotifies);
			Obj->SetObjectField(TEXT("notifies"), Notifies);
			TSharedRef<FJsonObject> Markers = AnimMcpJson::MakeObject();
			Markers->SetNumberField(TEXT("kept"), State.SyncMarkers.Num());
			Markers->SetNumberField(TEXT("dropped"), State.DroppedSyncMarkers);
			Obj->SetObjectField(TEXT("sync_markers"), Markers);
			return Obj;
		}

		// ---- 쓰기 ----

		void WriteSequence(FState& State, UAnimSequence* NewSequence, const FRequest& Request)
		{
			const FClip& Clip = State.Clip;
			// 복제본이 물려받은 노티파이 — 주 소스(0)의 이벤트는 이 배열을 쓴다(UAnimNotify 객체가 이미 새 애셋 안에 있다)
			const TArray<FAnimNotifyEvent> InheritedNotifies = NewSequence->Notifies;
			const TArray<FAnimSyncMarker> InheritedMarkers = NewSequence->AuthoredSyncMarkers;
			// 길이 변경 알림이 노티파이·싱크 마커를 옮기지 않게 먼저 비운다
			NewSequence->Notifies.Reset();
			NewSequence->AuthoredSyncMarkers.Reset();

			IAnimationDataController& Controller = NewSequence->GetController();
			constexpr bool bShouldTransact = false;
			Controller.OpenBracket(LOCTEXT("ApplyAnimationEdits", "AnimGraphMcp: apply animation edits"), bShouldTransact);
			Controller.NotifyPopulated();
			Controller.RemoveAllBoneTracks(bShouldTransact);
			Controller.RemoveAllCurvesOfType(ERawCurveTrackTypes::RCT_Float, bShouldTransact);
			Controller.RemoveAllCurvesOfType(ERawCurveTrackTypes::RCT_Transform, bShouldTransact);
			Controller.RemoveAllAttributes(bShouldTransact);
			Controller.SetNumberOfFrames(FFrameNumber(Clip.NumKeys() - 1), bShouldTransact);

			const int32 Keys = Clip.NumKeys();
			TArray<FVector3f> Positions;
			TArray<FQuat4f> Rotations;
			TArray<FVector3f> Scales;
			for (int32 Bone = 0; Bone < State.Rig.Num(); ++Bone)
			{
				if (!Clip.Animated[Bone])
				{
					continue;
				}
				Positions.SetNum(Keys);
				Rotations.SetNum(Keys);
				Scales.SetNum(Keys);
				for (int32 Key = 0; Key < Keys; ++Key)
				{
					const FTransform& X = Clip.Keys[Key][Bone];
					Positions[Key] = FVector3f(X.GetLocation());
					Rotations[Key] = FQuat4f(X.GetRotation().GetNormalized());
					Scales[Key] = FVector3f(X.GetScale3D());
				}
				const FName Name = State.Rig.Bones[Bone];
				Controller.AddBoneCurve(Name, bShouldTransact);
				Controller.SetBoneTrackKeys(Name, Positions, Rotations, Scales, bShouldTransact);
			}
			for (int32 Curve = 0; Curve < Clip.CurveNames.Num(); ++Curve)
			{
				const FName Name = Clip.CurveNames[Curve];
				const FAnimationCurveIdentifier Id(Name, ERawCurveTrackTypes::RCT_Float);
				const TPair<int32, FLinearColor>* Meta = State.CurveMeta.Find(Name);
				Controller.AddCurve(Id, Meta ? Meta->Key : 0x00000004, bShouldTransact);
				TArray<FRichCurveKey> CurveKeys;
				CurveKeys.Reserve(Keys);
				for (int32 Key = 0; Key < Keys; ++Key)
				{
					CurveKeys.Add(FRichCurveKey(static_cast<float>(Key / Clip.FrameRate), Clip.CurveValues[Key][Curve]));
				}
				Controller.SetCurveKeys(Id, CurveKeys, bShouldTransact);
				if (Meta)
				{
					Controller.SetCurveColor(Id, Meta->Value, bShouldTransact);
				}
			}
			Controller.CloseBracket(bShouldTransact);

			// 노티파이 — 출처 기준으로 새 시각에 다시 건다. 주 소스가 아닌 소스의 UAnimNotify 객체는 새 애셋 안으로 복제한다
			// 물려받은 이벤트는 번호로 센다 — 객체 없는 이벤트(이름만 있는 스켈레톤 노티파이 · 상태 없는 노티파이)도 있으니 포인터로 세지 않는다
			TSet<int32> UsedInherited;
			const int32 TrackCount = FMath::Max(1, NewSequence->AnimNotifyTracks.Num());
			for (const FMovedEvent& Moved : State.Notifies)
			{
				FAnimNotifyEvent Event = Moved.Source == 0 ? InheritedNotifies[Moved.Index] : State.Sources[Moved.Source]->Notifies[Moved.Index];
				if (Moved.Source != 0)
				{
					if (Event.Notify) { Event.Notify = DuplicateObject<UAnimNotify>(Event.Notify, NewSequence); }
					if (Event.NotifyStateClass) { Event.NotifyStateClass = DuplicateObject<UAnimNotifyState>(Event.NotifyStateClass, NewSequence); }
					Event.Guid = FGuid::NewGuid();
				}
				else
				{
					if (UsedInherited.Contains(Moved.Index))
					{
						continue; // 같은 이벤트가 두 번 매핑되지 않는다(MapTime 은 첫 구간만) — 방어
					}
					UsedInherited.Add(Moved.Index);
				}
				const float Time = static_cast<float>(Moved.Time);
				Event.Link(NewSequence, Time);
				Event.TriggerTimeOffset = GetTriggerTimeOffsetForType(NewSequence->CalculateOffsetForNotify(Time));
				if (Moved.Duration > 0.0)
				{
					Event.SetDuration(static_cast<float>(Moved.Duration));
					Event.EndLink.Link(NewSequence, Time + static_cast<float>(Moved.Duration));
					Event.EndTriggerTimeOffset = GetTriggerTimeOffsetForType(NewSequence->CalculateOffsetForNotify(Time + static_cast<float>(Moved.Duration)));
				}
				Event.TrackIndex = FMath::Clamp(Event.TrackIndex, 0, TrackCount - 1);
				NewSequence->Notifies.Add(Event);
			}
			// 결과에 남지 않은 물려받은 UAnimNotify 객체는 패키지에 남지 않게 치운다
			for (int32 Index = 0; Index < InheritedNotifies.Num(); ++Index)
			{
				if (UsedInherited.Contains(Index))
				{
					continue;
				}
				const FAnimNotifyEvent& Event = InheritedNotifies[Index];
				for (UObject* Object : { static_cast<UObject*>(Event.Notify), static_cast<UObject*>(Event.NotifyStateClass) })
				{
					if (Object)
					{
						Object->Rename(nullptr, GetTransientPackage(), REN_DontCreateRedirectors | REN_NonTransactional);
						Object->MarkAsGarbage();
					}
				}
			}
			if (NewSequence->AnimNotifyTracks.Num() == 0 && NewSequence->Notifies.Num() > 0)
			{
				NewSequence->AnimNotifyTracks.Add(FAnimNotifyTrack(TEXT("1"), FLinearColor::White));
			}
			for (const FMovedEvent& Moved : State.SyncMarkers)
			{
				FAnimSyncMarker Marker = Moved.Source == 0 ? InheritedMarkers[Moved.Index] : State.Sources[Moved.Source]->AuthoredSyncMarkers[Moved.Index];
				Marker.Time = static_cast<float>(Moved.Time);
				Marker.TrackIndex = FMath::Clamp(Marker.TrackIndex, 0, FMath::Max(1, NewSequence->AnimNotifyTracks.Num()) - 1);
				NewSequence->AuthoredSyncMarkers.Add(Marker);
			}
			NewSequence->RefreshSyncMarkerDataFromAuthored();
			NewSequence->RefreshCacheData();

			if (Request.bLoop.IsSet()) { NewSequence->bLoop = Request.bLoop.GetValue(); }
			if (Request.bRootMotion.IsSet()) { NewSequence->bEnableRootMotion = Request.bRootMotion.GetValue(); }
			NewSequence->PostEditChange();
			NewSequence->MarkPackageDirty();
		}
	}

	TSharedPtr<FJsonObject> Preview(const FRequest& Request, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		const AnimMcpGeneration::FDirtyGuard Guard;
		FState State;
		if (!Build(Request, State, Context, OutError))
		{
			return nullptr;
		}
		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetBoolField(TEXT("valid"), State.bValid);
		Result->SetStringField(TEXT("source"), Request.Source->GetPathName());
		Result->SetArrayField(TEXT("planned"), State.Planned);
		if (State.bValid)
		{
			Result->SetObjectField(TEXT("result"), SummaryJson(State));
			Result->SetArrayField(TEXT("seams"), SeamsJson(State, AnimMcpAnimValidator::FThresholds().SeamRatioMax));
			Result->SetArrayField(TEXT("limitations"), AnimMcpGeneration::ToJsonArray(State.Limitations));
		}
		if (!Request.AssetPath.IsEmpty())
		{
			TSharedRef<FJsonObject> Would = AnimMcpJson::MakeObject();
			const FString ObjectPath = AnimMcpAssetResolver::NormalizeObjectPath(AnimMcpAssetResolver::ToPackagePath(Request.AssetPath));
			Would->SetStringField(TEXT("asset_path"), ObjectPath);
			Would->SetBoolField(TEXT("allowed"), AnimMcpGeneration::IsOutputPathAllowed(Request.AssetPath));
			Would->SetBoolField(TEXT("exists"), AnimMcpAssetResolver::AssetExists(ObjectPath) || StaticFindObject(UObject::StaticClass(), nullptr, *ObjectPath) != nullptr);
			Result->SetObjectField(TEXT("would_create"), Would);
		}
		TArray<FString> Allowed, Unexpected;
		Guard.GetNewlyDirty(Allowed, Unexpected);
		Unexpected.Append(Allowed);
		if (Unexpected.Num() > 0)
		{
			Context.AddDiagnostic(TEXT("warning"), AnimMcpErrorCodes::UnexpectedDirty,
				FString::Printf(TEXT("Read-only preview left %d package(s) dirty: %s"), Unexpected.Num(), *FString::Join(Unexpected, TEXT(", "))));
		}
		return Result;
	}

	TSharedPtr<FJsonObject> Apply(const FRequest& Request, FAnimMcpContext& Context, FAnimMcpError& OutError)
	{
		const AnimMcpGeneration::FDirtyGuard Guard;
		if (!AnimMcpGeneration::EnsureOutputPathAllowed(Request.AssetPath, TEXT("asset_path"), OutError))
		{
			return nullptr;
		}
		AnimMcpAnimValidator::FOptions Options;
		if (!AnimMcpAnimValidator::ParseThresholds(Request.Thresholds, Options.Thresholds, OutError))
		{
			return nullptr;
		}
		const double Start = FPlatformTime::Seconds();
		FState State;
		if (!Build(Request, State, Context, OutError))
		{
			return nullptr;
		}
		if (!State.bValid)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetArrayField(TEXT("planned"), State.Planned);
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("One or more operations failed; nothing was created (details.planned)"), Details);
			return nullptr;
		}

		// ---- 여기부터 애셋을 만든다 ----
		UAnimSequence* NewSequence = Cast<UAnimSequence>(AnimMcpGeneration::DuplicateAssetObject(Request.Source, Request.AssetPath, TEXT("asset_path"), OutError));
		if (!NewSequence)
		{
			return nullptr;
		}
		WriteSequence(State, NewSequence, Request);
		UE_LOG(LogAnimGraphMcp, Log, TEXT("apply_animation_edits: %s → %s (%d op(s), %d keys) in %.2fs"),
			*Request.Source->GetName(), *NewSequence->GetPathName(), State.Ops.Num(), State.Clip.NumKeys(), FPlatformTime::Seconds() - Start);

		TSharedRef<FJsonObject> Result = SummaryJson(State);
		Result->SetStringField(TEXT("asset_path"), NewSequence->GetPathName());
		Result->SetStringField(TEXT("source"), Request.Source->GetPathName());
		Result->SetArrayField(TEXT("planned"), State.Planned);
		Result->SetArrayField(TEXT("seams"), SeamsJson(State, Options.Thresholds.SeamRatioMax));
		Result->SetArrayField(TEXT("limitations"), AnimMcpGeneration::ToJsonArray(State.Limitations));

		if (Request.bValidate)
		{
			// 내장 검증: 상대 비교는 끈다(길이·재생 속도가 바뀌어 프레임 대조가 무의미). 쓰기 충실도(길이 · 루프 · 루트 Yaw) + 이음매 + 물려받은 튐
			Options.ExpectedSkeleton = State.Skeleton;
			Options.bRelative = false;
			Options.Expect.Length = State.Clip.Length();
			Options.Expect.bLoop = NewSequence->bLoop;
			Options.Expect.RootYawDelta = RootYawDelta(State.Clip);
			Options.Expect.RootYawTolerance = 1.0;
			Options.Seams = State.Clip.Seams;
			double Inherited = 0.0;
			for (int32 i = 0; i < State.Sources.Num(); ++i)
			{
				const double RateScale = FMath::Max(1.0, State.SourceData[i].FrameRate / State.Clip.FrameRate);
				Inherited = FMath::Max(Inherited, AnimMcpAnimValidator::MaxDegPerFrame(State.Sources[i]) * RateScale);
			}
			Options.InheritedMaxDegPerFrame = Inherited * State.Clip.MaxRate;
			TSharedRef<FJsonObject> One = AnimMcpAnimValidator::Validate(NewSequence, nullptr, Options);
			TSharedRef<FJsonObject> Validation = AnimMcpJson::MakeObject();
			Validation->SetStringField(TEXT("status"), One->GetStringField(TEXT("status")));
			Validation->SetObjectField(TEXT("asset"), One);
			Validation->SetObjectField(TEXT("thresholds"), AnimMcpAnimValidator::ThresholdsToJson(Options.Thresholds));
			Validation->SetNumberField(TEXT("inherited_max_deg_per_frame"), AnimMcpStats::Round(Options.InheritedMaxDegPerFrame.GetValue(), 2));
			Result->SetObjectField(TEXT("validation"), Validation);
			if (One->GetStringField(TEXT("status")) == TEXT("FAILED"))
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetObjectField(TEXT("partial"), Result);
				FAnimMcpError DirtyError;
				if (!Guard.Check(DirtyError)) { Details->SetObjectField(TEXT("unexpected_dirty"), DirtyError.Details); }
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::ValidationFailed,
					FString::Printf(TEXT("Validation FAILED for '%s' — nothing saved; the asset stays unsaved in memory (details.partial.validation)"), *NewSequence->GetPathName()), Details);
				return nullptr;
			}
		}

		bool bSaved = false;
		if (!AnimMcpGeneration::FinishWrite(Guard, { NewSequence }, Request.bSave, Context, OutError, bSaved))
		{
			if (OutError.Details.IsValid()) { OutError.Details->SetObjectField(TEXT("partial"), Result); }
			return nullptr;
		}
		Result->SetBoolField(TEXT("saved"), bSaved);
		Result->SetNumberField(TEXT("seconds"), AnimMcpStats::Round(FPlatformTime::Seconds() - Start));
		return Result;
	}
}

#undef LOCTEXT_NAMESPACE
