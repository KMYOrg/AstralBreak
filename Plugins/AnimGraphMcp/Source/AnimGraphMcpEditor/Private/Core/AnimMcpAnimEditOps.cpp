#include "AnimMcpAnimEditOps.h"

#include "AnimationRuntime.h"

namespace AnimMcpAnimEditOps
{
	namespace
	{
		FTransform BlendTransform(const FTransform& A, const FTransform& B, double Alpha)
		{
			if (Alpha <= 0.0)
			{
				return A;
			}
			if (Alpha >= 1.0)
			{
				return B;
			}
			// FQuat::Slerp 는 짧은 경로로 돌고 정규화한다
			return FTransform(FQuat::Slerp(A.GetRotation(), B.GetRotation(), Alpha), FMath::Lerp(A.GetLocation(), B.GetLocation(), Alpha), FMath::Lerp(A.GetScale3D(), B.GetScale3D(), Alpha));
		}

		double SmoothStep(double X)
		{
			X = FMath::Clamp(X, 0.0, 1.0);
			return X * X * (3.0 - 2.0 * X);
		}

		/** 버퍼의 분수 키 위치 — 포즈 · 커브 · 출처(같은 출처끼리면 소스 시각도 보간) */
		void Evaluate(const FClip& Clip, double KeyPos, TArray<FTransform>& OutPose, TArray<float>& OutCurves, FProvenance& OutProvenance)
		{
			const int32 Last = Clip.NumKeys() - 1;
			KeyPos = FMath::Clamp(KeyPos, 0.0, static_cast<double>(Last));
			const int32 K0 = FMath::Min(FMath::FloorToInt32(KeyPos), Last);
			const int32 K1 = FMath::Min(K0 + 1, Last);
			const double Alpha = KeyPos - K0;
			const TArray<FTransform>& A = Clip.Keys[K0];
			const TArray<FTransform>& B = Clip.Keys[K1];
			OutPose.SetNum(A.Num());
			for (int32 Bone = 0; Bone < A.Num(); ++Bone)
			{
				OutPose[Bone] = BlendTransform(A[Bone], B[Bone], Alpha);
			}
			const TArray<float>& CA = Clip.CurveValues[K0];
			const TArray<float>& CB = Clip.CurveValues[K1];
			OutCurves.SetNum(CA.Num());
			for (int32 Curve = 0; Curve < CA.Num(); ++Curve)
			{
				OutCurves[Curve] = FMath::Lerp(CA[Curve], CB[Curve], static_cast<float>(Alpha));
			}
			const FProvenance& P0 = Clip.Provenance[K0];
			const FProvenance& P1 = Clip.Provenance[K1];
			if (P0.Source != INDEX_NONE && P0.Source == P1.Source && P0.bReversed == P1.bReversed)
			{
				OutProvenance = P0;
				OutProvenance.Time = FMath::Lerp(P0.Time, P1.Time, Alpha);
			}
			else
			{
				OutProvenance = Alpha < 0.5 ? P0 : P1;
			}
		}

		/** OutTime → 현재 버퍼 시각으로 거꾸로 대응시켜 Frames 프레임짜리 버퍼로 다시 고른다 */
		void Resample(FClip& Clip, int32 Frames, TFunctionRef<double(double)> InverseMap)
		{
			const double Length = Clip.Length();
			TArray<TArray<FTransform>> Keys;
			TArray<TArray<float>> Curves;
			TArray<FProvenance> Provenance;
			Keys.SetNum(Frames + 1);
			Curves.SetNum(Frames + 1);
			Provenance.SetNum(Frames + 1);
			for (int32 Key = 0; Key <= Frames; ++Key)
			{
				const double Time = FMath::Clamp(InverseMap(Key / Clip.FrameRate), 0.0, Length);
				Evaluate(Clip, Time * Clip.FrameRate, Keys[Key], Curves[Key], Provenance[Key]);
			}
			Clip.Keys = MoveTemp(Keys);
			Clip.CurveValues = MoveTemp(Curves);
			Clip.Provenance = MoveTemp(Provenance);
		}

		template <typename T>
		void Slice(TArray<T>& Array, int32 First, int32 Count)
		{
			Array = TArray<T>(Array.GetData() + First, Count);
		}

		/** 이음매 옮기기 — Map 이 값을 안 주거나 양 끝 반 프레임 안이면 버린다 */
		void RemapSeams(FClip& Clip, TFunctionRef<TOptional<double>(double)> Map)
		{
			const double Half = 0.5 / Clip.FrameRate;
			TArray<double> Seams;
			for (const double Seam : Clip.Seams)
			{
				const TOptional<double> Moved = Map(Seam);
				if (Moved.IsSet() && Moved.GetValue() > Half && Moved.GetValue() < Clip.Length() - Half)
				{
					Seams.Add(Moved.GetValue());
				}
			}
			Clip.Seams = MoveTemp(Seams);
		}

		void AddSeam(FClip& Clip, double Time)
		{
			const double Half = 0.5 / Clip.FrameRate;
			if (Time <= Half || Time >= Clip.Length() - Half)
			{
				return;
			}
			if (!Clip.Seams.ContainsByPredicate([Time, Half](double Seam) { return FMath::Abs(Seam - Time) < Half; }))
			{
				Clip.Seams.Add(Time);
				Clip.Seams.Sort();
			}
		}

		/** [Start, End] 를 키로 맞춘다 — 한 프레임 미만이면 false */
		bool SnapRange(const FClip& Clip, double Start, double End, const TCHAR* What, FReport& Report, FString& OutError)
		{
			Report.StartKey = Clip.TimeToKey(Start);
			Report.EndKey = Clip.TimeToKey(End);
			Report.Start = Report.StartKey / Clip.FrameRate;
			Report.End = Report.EndKey / Clip.FrameRate;
			Report.LengthBefore = Clip.Length();
			if (Report.EndKey - Report.StartKey < 1)
			{
				OutError = FString::Printf(TEXT("%s range %.4f..%.4fs covers less than one frame at %.2f fps"), What, Start, End, Clip.FrameRate);
				return false;
			}
			return true;
		}

		double YawOf(const FTransform& Transform)
		{
			return Transform.GetRotation().Rotator().Yaw;
		}
	}

	void FRig::Finalize()
	{
		RefComponentRotations.SetNum(Bones.Num());
		for (int32 Bone = 0; Bone < Bones.Num(); ++Bone)
		{
			const FQuat Local = RefLocal[Bone].GetRotation();
			RefComponentRotations[Bone] = Parents[Bone] == INDEX_NONE ? Local : RefComponentRotations[Parents[Bone]] * Local;
		}
	}

	void Sample(const FRig& Rig, const FSource& Source, int32 SourceIndex, double OutRate, double Start, double End, bool bReverse, FClip& Out)
	{
		const double Length = Source.Length();
		Start = FMath::Clamp(Start, 0.0, Length);
		End = FMath::Clamp(End, Start, Length);
		const int32 Frames = FMath::Max(1, FMath::RoundToInt32((End - Start) * OutRate));
		Out = FClip();
		Out.FrameRate = OutRate;
		Out.Keys.SetNum(Frames + 1);
		Out.CurveNames = Source.CurveNames;
		Out.CurveValues.SetNum(Frames + 1);
		Out.Provenance.SetNum(Frames + 1);
		Out.Animated.Init(false, Rig.Num());
		for (int32 Bone = 0; Bone < Rig.Num(); ++Bone)
		{
			Out.Animated[Bone] = Source.Tracks.IsValidIndex(Bone) && Source.Tracks[Bone].Num() > 0;
		}
		const double LastSourceKey = FMath::Max(0.0, Source.NumKeys - 1.0);
		for (int32 Key = 0; Key <= Frames; ++Key)
		{
			// 키 간격은 출력 fps 그대로 — 구간 끝은 가장 가까운 키로 (늘이지 않는다)
			const double Time = bReverse ? FMath::Max(0.0, End - Key / OutRate) : FMath::Min(Length, Start + Key / OutRate);
			const double SourceKey = FMath::Clamp(Time * Source.FrameRate, 0.0, LastSourceKey);
			const int32 K0 = FMath::FloorToInt32(SourceKey);
			const int32 K1 = FMath::Min(K0 + 1, FMath::Max(0, Source.NumKeys - 1));
			double Alpha = SourceKey - K0;
			if (Source.bStep)
			{
				Alpha = FMath::RoundToDouble(Alpha); // 엔진 EvaluateBoneTrackTransform 의 Step 규칙
			}
			TArray<FTransform>& Pose = Out.Keys[Key];
			Pose.SetNum(Rig.Num());
			for (int32 Bone = 0; Bone < Rig.Num(); ++Bone)
			{
				const TArray<FTransform>* Track = Source.Tracks.IsValidIndex(Bone) ? &Source.Tracks[Bone] : nullptr;
				if (Track && Track->Num() > 0)
				{
					const int32 Last = Track->Num() - 1;
					Pose[Bone] = BlendTransform((*Track)[FMath::Min(K0, Last)], (*Track)[FMath::Min(K1, Last)], Alpha);
				}
				else
				{
					Pose[Bone] = Rig.RefLocal[Bone];
				}
			}
			TArray<float>& Curves = Out.CurveValues[Key];
			Curves.SetNum(Source.Curves.Num());
			for (int32 Curve = 0; Curve < Source.Curves.Num(); ++Curve)
			{
				Curves[Curve] = Source.Curves[Curve].Eval(static_cast<float>(Time));
			}
			Out.Provenance[Key] = FProvenance{ SourceIndex, Time, bReverse };
		}
	}

	bool Trim(FClip& Clip, double Start, double End, FReport& Report, FString& OutError)
	{
		if (!SnapRange(Clip, Start, End, TEXT("trim"), Report, OutError))
		{
			return false;
		}
		const int32 Count = Report.EndKey - Report.StartKey + 1;
		Slice(Clip.Keys, Report.StartKey, Count);
		Slice(Clip.CurveValues, Report.StartKey, Count);
		Slice(Clip.Provenance, Report.StartKey, Count);
		const double Shift = Report.Start;
		RemapSeams(Clip, [Shift](double Seam) { return TOptional<double>(Seam - Shift); });
		Report.LengthAfter = Clip.Length();
		return true;
	}

	bool Retime(FClip& Clip, double Start, double End, double Rate, FReport& Report, FString& OutError)
	{
		if (Rate <= 0.0)
		{
			OutError = FString::Printf(TEXT("retime rate must be > 0 (got %g)"), Rate);
			return false;
		}
		if (!SnapRange(Clip, Start, End, TEXT("retime"), Report, OutError))
		{
			return false;
		}
		const double Ts = Report.Start;
		const double Te = Report.End;
		const double Segment = Te - Ts;
		const double NewSegment = Segment / Rate;
		const double NewLength = Clip.Length() - Segment + NewSegment;
		const int32 Frames = FMath::Max(1, FMath::RoundToInt32(NewLength * Clip.FrameRate));
		Resample(Clip, Frames, [Ts, Te, NewSegment, Rate](double U)
		{
			if (U <= Ts) { return U; }
			if (U <= Ts + NewSegment) { return Ts + (U - Ts) * Rate; }
			return Te + (U - Ts - NewSegment);
		});
		RemapSeams(Clip, [Ts, Te, Segment, NewSegment, Rate](double Seam)
		{
			if (Seam <= Ts) { return TOptional<double>(Seam); }
			if (Seam <= Te) { return TOptional<double>(Ts + (Seam - Ts) / Rate); }
			return TOptional<double>(Seam - Segment + NewSegment);
		});
		AddSeam(Clip, Ts);
		AddSeam(Clip, Ts + NewSegment);
		Clip.MaxRate *= FMath::Max(1.0, Rate);
		Report.LengthAfter = Clip.Length();
		Report.Note = FString::Printf(TEXT("%.4fs → %.4fs (x%.3f)"), Segment, NewSegment, Rate);
		return true;
	}

	bool HoldPose(FClip& Clip, double At, double Duration, FReport& Report, FString& OutError)
	{
		const int32 Count = FMath::RoundToInt32(Duration * Clip.FrameRate);
		if (Count < 1)
		{
			OutError = FString::Printf(TEXT("hold_pose duration %.4fs is shorter than one frame at %.2f fps"), Duration, Clip.FrameRate);
			return false;
		}
		const int32 Key = Clip.TimeToKey(At);
		Report.StartKey = Key;
		Report.EndKey = Key;
		Report.Start = Report.End = Key / Clip.FrameRate;
		Report.LengthBefore = Clip.Length();
		const TArray<FTransform> Pose = Clip.Keys[Key];
		const TArray<float> Curves = Clip.CurveValues[Key];
		const FProvenance Provenance = Clip.Provenance[Key];
		for (int32 i = 0; i < Count; ++i)
		{
			Clip.Keys.Insert(Pose, Key + 1);
			Clip.CurveValues.Insert(Curves, Key + 1);
			Clip.Provenance.Insert(Provenance, Key + 1);
		}
		const double HoldStart = Report.Start;
		const double Shift = Count / Clip.FrameRate;
		RemapSeams(Clip, [HoldStart, Shift](double Seam) { return TOptional<double>(Seam > HoldStart ? Seam + Shift : Seam); });
		AddSeam(Clip, HoldStart);
		AddSeam(Clip, HoldStart + Shift);
		Report.LengthAfter = Clip.Length();
		Report.Note = FString::Printf(TEXT("%d frame(s) held"), Count);
		return true;
	}

	bool Concat(FClip& Clip, FClip Segment, double Blend, bool bAlignRoot, FReport& Report, FString& OutError)
	{
		const int32 N = Clip.NumKeys();
		const int32 S = Segment.NumKeys();
		if (S < 2)
		{
			OutError = TEXT("concat segment covers less than one frame");
			return false;
		}
		if (!FMath::IsNearlyEqual(Segment.FrameRate, Clip.FrameRate))
		{
			OutError = FString::Printf(TEXT("concat segment is sampled at %.2f fps, the clip at %.2f fps"), Segment.FrameRate, Clip.FrameRate);
			return false;
		}
		const int32 BlendKeys = FMath::RoundToInt32(Blend * Clip.FrameRate);
		if (BlendKeys > N - 1 || BlendKeys > S - 1)
		{
			OutError = FString::Printf(TEXT("concat blend %.4fs (%d frames) is longer than the clip (%d) or the segment (%d)"), Blend, BlendKeys, N - 1, S - 1);
			return false;
		}
		const int32 Anchor = N - 1 - BlendKeys;
		Report.LengthBefore = Clip.Length();
		Report.StartKey = Anchor;
		Report.Start = Anchor / Clip.FrameRate;

		if (bAlignRoot)
		{
			// 붙는 구간의 루트를 겹치는 첫 키의 루트 위치·Yaw 에 맞춘다 — 루트 모션이 끊기지 않게
			const FTransform Current = Clip.Keys[Anchor][0];
			const FTransform First = Segment.Keys[0][0];
			const FQuat Turn(FVector::UpVector, FMath::DegreesToRadians(FRotator::NormalizeAxis(YawOf(Current) - YawOf(First))));
			for (TArray<FTransform>& Pose : Segment.Keys)
			{
				FTransform& Root = Pose[0];
				Root.SetLocation(Current.GetLocation() + Turn.RotateVector(Root.GetLocation() - First.GetLocation()));
				Root.SetRotation((Turn * Root.GetRotation()).GetNormalized());
			}
			Segment.Animated[0] = true;
		}

		// 커브 합집합 — 한쪽에 없는 커브는 0 (엔진 평가에서 커브가 없을 때와 같다)
		TArray<FName> Names = Clip.CurveNames;
		for (const FName& Name : Segment.CurveNames)
		{
			if (!Names.Contains(Name))
			{
				Names.Add(Name);
				Report.FilledCurves.Add(Name);
			}
		}
		for (const FName& Name : Clip.CurveNames)
		{
			if (!Segment.CurveNames.Contains(Name))
			{
				Report.FilledCurves.AddUnique(Name);
			}
		}
		auto Widen = [&Names](const TArray<FName>& From, const TArray<float>& Values)
		{
			TArray<float> Out;
			Out.SetNumZeroed(Names.Num());
			for (int32 i = 0; i < From.Num(); ++i)
			{
				Out[Names.IndexOfByKey(From[i])] = Values[i];
			}
			return Out;
		};

		TArray<TArray<FTransform>> Keys;
		TArray<TArray<float>> Curves;
		TArray<FProvenance> Provenance;
		for (int32 Key = 0; Key < Anchor; ++Key)
		{
			Keys.Add(Clip.Keys[Key]);
			Curves.Add(Widen(Clip.CurveNames, Clip.CurveValues[Key]));
			Provenance.Add(Clip.Provenance[Key]);
		}
		for (int32 j = 0; j <= BlendKeys; ++j)
		{
			const double W = BlendKeys > 0 ? SmoothStep(static_cast<double>(j) / BlendKeys) : 0.0;
			const TArray<FTransform>& A = Clip.Keys[Anchor + j];
			const TArray<FTransform>& B = Segment.Keys[j];
			TArray<FTransform>& Pose = Keys.AddDefaulted_GetRef();
			Pose.SetNum(A.Num());
			for (int32 Bone = 0; Bone < A.Num(); ++Bone)
			{
				Pose[Bone] = BlendTransform(A[Bone], B[Bone], W);
			}
			const TArray<float> CA = Widen(Clip.CurveNames, Clip.CurveValues[Anchor + j]);
			const TArray<float> CB = Widen(Segment.CurveNames, Segment.CurveValues[j]);
			TArray<float>& C = Curves.AddDefaulted_GetRef();
			C.SetNum(Names.Num());
			for (int32 i = 0; i < Names.Num(); ++i)
			{
				C[i] = FMath::Lerp(CA[i], CB[i], static_cast<float>(W));
			}
			Provenance.Add(W < 0.5 ? Clip.Provenance[Anchor + j] : Segment.Provenance[j]);
		}
		for (int32 Key = BlendKeys + 1; Key < S; ++Key)
		{
			Keys.Add(Segment.Keys[Key]);
			Curves.Add(Widen(Segment.CurveNames, Segment.CurveValues[Key]));
			Provenance.Add(Segment.Provenance[Key]);
		}
		Clip.Keys = MoveTemp(Keys);
		Clip.CurveValues = MoveTemp(Curves);
		Clip.Provenance = MoveTemp(Provenance);
		Clip.CurveNames = MoveTemp(Names);
		for (int32 Bone = 0; Bone < Clip.Animated.Num() && Bone < Segment.Animated.Num(); ++Bone)
		{
			Clip.Animated[Bone] = Clip.Animated[Bone] || Segment.Animated[Bone];
		}
		AddSeam(Clip, Anchor / Clip.FrameRate);
		if (BlendKeys > 0)
		{
			AddSeam(Clip, (Anchor + BlendKeys) / Clip.FrameRate);
		}
		Report.EndKey = Clip.NumKeys() - 1;
		Report.End = Clip.Length();
		Report.LengthAfter = Clip.Length();
		Report.Note = FString::Printf(TEXT("%d key(s) appended, blend %d frame(s)"), S - 1 - BlendKeys, BlendKeys);
		return true;
	}

	void Mirror(const FRig& Rig, FClip& Clip, EAxis::Type Axis, const TArray<int32>& MirrorBones)
	{
		const TArray<FQuat>& Ref = Rig.RefComponentRotations;
		// FAnimationRuntime::MirrorPose 의 MirrorTransform — 부모의 기준 회전으로 컴포넌트 축에 올려 반전하고, 대상 본의 기준 방향으로 보정한 뒤 내린다
		auto MirrorTransform = [&Ref, Axis](const FTransform& X, int32 SourceParent, int32 SourceBone, int32 TargetParent, int32 TargetBone)
		{
			FVector T = Ref[SourceParent].RotateVector(X.GetTranslation());
			T = Ref[TargetParent].UnrotateVector(FAnimationRuntime::MirrorVector(T, Axis));
			FQuat Q = FAnimationRuntime::MirrorQuat(Ref[SourceParent] * X.GetRotation(), Axis);
			Q *= FAnimationRuntime::MirrorQuat(Ref[SourceBone], Axis).Inverse() * Ref[TargetBone];
			Q = Ref[TargetParent].Inverse() * Q;
			return FTransform(Q.GetNormalized(), T, X.GetScale3D());
		};
		for (TArray<FTransform>& Pose : Clip.Keys)
		{
			const TArray<FTransform> In = Pose;
			{
				FQuat Q = FAnimationRuntime::MirrorQuat(In[0].GetRotation(), Axis);
				Q *= FAnimationRuntime::MirrorQuat(Ref[0], Axis).Inverse() * Ref[0];
				Pose[0] = FTransform(Q.GetNormalized(), FAnimationRuntime::MirrorVector(In[0].GetTranslation(), Axis), In[0].GetScale3D());
			}
			for (int32 Bone = 1; Bone < Rig.Num(); ++Bone)
			{
				const int32 Other = MirrorBones[Bone];
				const int32 Parent = Rig.Parents[Bone];
				if (Other == Bone)
				{
					Pose[Bone] = MirrorTransform(In[Bone], Parent, Bone, Parent, Bone);
				}
				else if (Other > Bone)
				{
					const int32 OtherParent = Rig.Parents[Other];
					Pose[Bone] = MirrorTransform(In[Other], OtherParent, Other, Parent, Bone);
					Pose[Other] = MirrorTransform(In[Bone], Parent, Bone, OtherParent, Other);
				}
			}
		}
		Clip.Animated.Init(true, Rig.Num());
	}

	bool OffsetBones(const FRig& Rig, FClip& Clip, TArray<FBoneOffset> Targets, bool bComponentSpace, double Start, double End, double BlendIn, double BlendOut, FReport& Report, FString& OutError)
	{
		if (!SnapRange(Clip, Start, End, TEXT("offset_bone"), Report, OutError))
		{
			return false;
		}
		const double Ts = Report.Start;
		const double Te = Report.End;
		if (BlendIn < 0.0 || BlendOut < 0.0 || BlendIn + BlendOut > Te - Ts + 1e-6)
		{
			OutError = FString::Printf(TEXT("blend_in %.3f + blend_out %.3f must be >= 0 and fit in the range %.4f..%.4fs"), BlendIn, BlendOut, Ts, Te);
			return false;
		}
		// 부모부터 — 자식의 컴포넌트 회전 계산이 부모 변경을 반영하게
		Targets.Sort([](const FBoneOffset& A, const FBoneOffset& B) { return A.Bone < B.Bone; });
		auto Weight = [Ts, Te, BlendIn, BlendOut](double T)
		{
			double W = 1.0;
			if (BlendIn > 0.0) { W = FMath::Min(W, SmoothStep((T - Ts) / BlendIn)); }
			if (BlendOut > 0.0) { W = FMath::Min(W, SmoothStep((Te - T) / BlendOut)); }
			return W;
		};
		for (int32 Key = Report.StartKey; Key <= Report.EndKey; ++Key)
		{
			const double W = Weight(Key / Clip.FrameRate);
			if (W <= 0.0)
			{
				continue;
			}
			TArray<FTransform>& Pose = Clip.Keys[Key];
			for (const FBoneOffset& Target : Targets)
			{
				FTransform& Local = Pose[Target.Bone];
				const FQuat R = FQuat::Slerp(FQuat::Identity, Target.Rotation, W);
				const FVector T = Target.Translation * W;
				if (bComponentSpace)
				{
					// 부모의 현재 컴포넌트 회전 (루트까지 곱한다) — comp(b) = Parent * Local 이므로 Local' = Parent⁻¹ · R · Parent · Local 이면 comp'(b) = R · comp(b)
					FQuat Parent = FQuat::Identity;
					for (int32 P = Rig.Parents[Target.Bone]; P != INDEX_NONE; P = Rig.Parents[P])
					{
						Parent = Pose[P].GetRotation() * Parent;
					}
					Local.SetRotation((Parent.Inverse() * R * Parent * Local.GetRotation()).GetNormalized());
					Local.AddToTranslation(Parent.UnrotateVector(T));
				}
				else
				{
					Local.SetRotation((Local.GetRotation() * R).GetNormalized());
					Local.AddToTranslation(T);
				}
				Clip.Animated[Target.Bone] = true;
			}
		}
		// 블렌드 없이 끊기는 경계는 이음매로 검사한다
		if (BlendIn <= 0.0)
		{
			AddSeam(Clip, Ts);
		}
		if (BlendOut <= 0.0)
		{
			AddSeam(Clip, Te);
		}
		Report.LengthAfter = Clip.Length();
		return true;
	}

	bool RotateRoot(FClip& Clip, double Yaw, double Start, double End, bool bSmooth, FReport& Report, FString& OutError)
	{
		if (!SnapRange(Clip, Start, End, TEXT("rotate_root"), Report, OutError))
		{
			return false;
		}
		const int32 K0 = Report.StartKey;
		const int32 K1 = Report.EndKey;
		auto YawAt = [K0, K1, Yaw, bSmooth](int32 Key)
		{
			if (Key <= K0) { return 0.0; }
			if (Key >= K1) { return Yaw; }
			const double X = static_cast<double>(Key - K0) / (K1 - K0);
			return Yaw * (bSmooth ? SmoothStep(X) : X);
		};
		FVector PrevSource = Clip.Keys[K0][0].GetLocation();
		FVector PrevOut = PrevSource;
		for (int32 Key = K0 + 1; Key < Clip.NumKeys(); ++Key)
		{
			FTransform& Root = Clip.Keys[Key][0];
			const FQuat Turn(FVector::UpVector, FMath::DegreesToRadians(YawAt(Key)));
			const FVector Source = Root.GetLocation();
			const FVector Out = PrevOut + Turn.RotateVector(Source - PrevSource);
			PrevSource = Source;
			PrevOut = Out;
			Root.SetLocation(Out);
			Root.SetRotation((Turn * Root.GetRotation()).GetNormalized());
		}
		Clip.Animated[0] = true;
		Report.LengthAfter = Clip.Length();
		Report.Note = FString::Printf(TEXT("root yaw +%.1f° over %d frame(s)"), Yaw, K1 - K0);
		return true;
	}

	TArray<int32> MirrorPairs(const FRig& Rig, TFunctionRef<FName(FName)> MirrorName)
	{
		TArray<int32> Named;
		Named.SetNum(Rig.Num());
		for (int32 Bone = 0; Bone < Rig.Num(); ++Bone)
		{
			const FName Other = MirrorName(Rig.Bones[Bone]);
			const int32 Index = Other.IsNone() ? INDEX_NONE : Rig.Find(Other);
			Named[Bone] = Index == INDEX_NONE ? Bone : Index;
		}
		// 서로 가리키는 짝만 — 한쪽만 가리키면 둘 다 자기 자신
		TArray<int32> Pairs = Named;
		for (int32 Bone = 0; Bone < Rig.Num(); ++Bone)
		{
			if (Named[Bone] != Bone && Named[Named[Bone]] != Bone)
			{
				Pairs[Bone] = Bone;
			}
		}
		return Pairs;
	}

	void ToComponent(const FRig& Rig, const TArray<FTransform>& Local, TArray<FTransform>& OutComponent)
	{
		OutComponent.SetNum(Local.Num());
		for (int32 Bone = 0; Bone < Local.Num(); ++Bone)
		{
			const int32 Parent = Rig.Parents[Bone];
			OutComponent[Bone] = Parent == INDEX_NONE ? Local[Bone] : Local[Bone] * OutComponent[Parent];
		}
	}

	TArray<double> StepMeans(const FRig& Rig, const FClip& Clip)
	{
		TArray<double> Means;
		TArray<FTransform> Previous, Current;
		for (int32 Key = 0; Key < Clip.NumKeys(); ++Key)
		{
			ToComponent(Rig, Clip.Keys[Key], Current);
			if (Key > 0 && Current.Num() > 0)
			{
				double Sum = 0.0;
				for (int32 Bone = 0; Bone < Current.Num(); ++Bone)
				{
					Sum += FMath::RadiansToDegrees(Current[Bone].GetRotation().GetNormalized().AngularDistance(Previous[Bone].GetRotation().GetNormalized()));
				}
				Means.Add(Sum / Current.Num());
			}
			Swap(Previous, Current);
		}
		return Means;
	}

	double RootYawDelta(const FClip& Clip)
	{
		double Delta = 0.0;
		for (int32 Key = 1; Key < Clip.NumKeys(); ++Key)
		{
			Delta += FRotator::NormalizeAxis(YawOf(Clip.Keys[Key][0]) - YawOf(Clip.Keys[Key - 1][0]));
		}
		return Delta;
	}
}
