#include "AnimMcpAnimValidator.h"

#include "AnimMcpStats.h"
#include "AnimPose.h"
#include "Animation/AnimData/IAnimationDataModel.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "Bridge/AnimMcpTypes.h"
#include "HAL/PlatformTime.h"
#include "Misc/PackageName.h"
#include "ReferenceSkeleton.h"
#include "UObject/Package.h"

namespace AnimMcpAnimValidator
{
	namespace
	{
		/** 프레임별 컴포넌트 공간 포즈 */
		struct FSampled
		{
			int32 Frames = 0;
			double FrameRate = 0.0;
			double Length = 0.0;
			bool bLoop = false;
			TArray<FName> Bones;
			/** [frame][bone] */
			TArray<TArray<FTransform>> Component;
			/** 펠비스의 기준 포즈 높이 (cm) — 길이 비 보정용 */
			TOptional<double> PelvisHeight;
			FName Pelvis;
		};

		struct FMetrics
		{
			double AngP50 = 0.0, AngP99 = 0.0, AngMax = 0.0;
			FName AngMaxBone;
			double MaxDegPerFrame = 0.0;
			int32 MaxDegFrame = 0;
			FName MaxDegBone;
			TOptional<double> FootPlantedP50;
			TArray<FName> Feet;
			double LoopBoundaryMaxDeg = 0.0;
			TOptional<double> LoopBoundaryRatio;
			double RootTravel = 0.0;
			double RootDisplacement = 0.0;
			/** 루트(본 0) Yaw 의 첫 → 끝 변화 — 프레임마다 ±180 안으로 접어 누적 (방향 포함) */
			double RootYawDelta = 0.0;
			/** [F-1] = 프레임 F-1 → F 의 본 평균 회전 (°) — 루프 경계·이음매 비의 분모 */
			TArray<double> StepMeans;
			bool bNaN = false;
			FName NaNBone;
			bool bBadScale = false;
			FName BadScaleBone;
			double BadScale = 1.0;
		};

		/** 오류·경고·정보 항목 */
		struct FIssues
		{
			TArray<TSharedPtr<FJsonValue>> Items;
			bool bError = false;
			bool bWarning = false;
			bool bUndetermined = false;

			void Add(const TCHAR* Level, const TCHAR* Code, const FString& Message, TSharedPtr<FJsonObject> Extra = nullptr)
			{
				TSharedRef<FJsonObject> Item = Extra.IsValid() ? Extra.ToSharedRef() : AnimMcpJson::MakeObject();
				Item->SetStringField(TEXT("level"), Level);
				Item->SetStringField(TEXT("code"), Code);
				Item->SetStringField(TEXT("message"), Message);
				Items.Add(MakeShared<FJsonValueObject>(Item));
				bError |= FCString::Strcmp(Level, TEXT("error")) == 0;
				bWarning |= FCString::Strcmp(Level, TEXT("warning")) == 0;
			}
		};

		double AngleDeg(const FQuat& A, const FQuat& B)
		{
			return FMath::RadiansToDegrees(A.GetNormalized().AngularDistance(B.GetNormalized()));
		}

		int32 FindBone(const TArray<FName>& Bones, FName Name)
		{
			// FName 비교는 대소문자를 무시한다 — 엔진의 본 이름 규칙과 같다
			return Name.IsNone() ? INDEX_NONE : Bones.IndexOfByKey(Name);
		}

		bool Sample(const UAnimSequence* Sequence, FName PelvisHint, FSampled& Out)
		{
			Out.FrameRate = Sequence->GetSamplingFrameRate().AsDecimal();
			Out.Frames = Sequence->GetNumberOfSampledKeys();
			Out.Length = Sequence->GetPlayLength();
			Out.bLoop = Sequence->bLoop;
			FAnimPoseEvaluationOptions Options;
			Options.bExtractRootMotion = false;
			Options.bIncorporateRootMotionIntoPose = true;
			for (int32 Frame = 0; Frame < Out.Frames; ++Frame)
			{
				FAnimPose Pose;
				UAnimPoseExtensions::GetAnimPoseAtFrame(Sequence, Frame, Options, Pose);
				if (!Pose.IsValid())
				{
					return false;
				}
				if (Frame == 0)
				{
					UAnimPoseExtensions::GetBoneNames(Pose, Out.Bones);
					const FName Pelvis = PelvisHint.IsNone() ? FName(TEXT("pelvis")) : PelvisHint;
					if (FindBone(Out.Bones, Pelvis) != INDEX_NONE)
					{
						Out.Pelvis = Pelvis;
						Out.PelvisHeight = UAnimPoseExtensions::GetRefBonePose(Pose, Pelvis, EAnimPoseSpaces::World).GetLocation().Z;
					}
				}
				TArray<FTransform>& Row = Out.Component.AddDefaulted_GetRef();
				Row.SetNum(Out.Bones.Num());
				for (int32 Bone = 0; Bone < Out.Bones.Num(); ++Bone)
				{
					Row[Bone] = UAnimPoseExtensions::GetBonePose(Pose, Out.Bones[Bone], EAnimPoseSpaces::World);
				}
			}
			return Out.Frames > 0 && Out.Bones.Num() > 0;
		}

		FMetrics Measure(const FSampled& S, const TArray<FName>& FeetHint, const FThresholds& T)
		{
			FMetrics M;
			const int32 N = S.Frames;
			const int32 B = S.Bones.Num();
			const double Dt = S.FrameRate > 0.0 ? 1.0 / S.FrameRate : 1.0 / 30.0;

			// NaN · 스케일
			for (int32 F = 0; F < N && !M.bNaN; ++F)
			{
				for (int32 Bone = 0; Bone < B; ++Bone)
				{
					const FTransform& X = S.Component[F][Bone];
					if (X.ContainsNaN())
					{
						M.bNaN = true;
						M.NaNBone = S.Bones[Bone];
						break;
					}
					const FVector Scale = X.GetScale3D();
					if (!M.bBadScale && (Scale.GetAbsMin() < 1e-3 || Scale.GetAbsMax() > 10.0))
					{
						M.bBadScale = true;
						M.BadScaleBone = S.Bones[Bone];
						M.BadScale = Scale.GetAbsMin() < 1e-3 ? Scale.GetAbsMin() : Scale.GetAbsMax();
					}
				}
			}

			// 각속도 (°/s) · 한 프레임 최대 회전 · 루프 경계용 프레임 평균
			TArray<double> Speeds;
			Speeds.Reserve(FMath::Max(0, N - 1) * B);
			TArray<double>& FrameMeans = M.StepMeans;
			for (int32 F = 1; F < N; ++F)
			{
				double Sum = 0.0;
				for (int32 Bone = 0; Bone < B; ++Bone)
				{
					const double Deg = AngleDeg(S.Component[F][Bone].GetRotation(), S.Component[F - 1][Bone].GetRotation());
					Sum += Deg;
					Speeds.Add(Deg / Dt);
					if (Deg > M.MaxDegPerFrame)
					{
						M.MaxDegPerFrame = Deg;
						M.MaxDegFrame = F;
						M.MaxDegBone = S.Bones[Bone];
					}
				}
				FrameMeans.Add(B > 0 ? Sum / B : 0.0);
			}
			M.AngP50 = AnimMcpStats::Percentile(Speeds, 50.0);
			M.AngP99 = AnimMcpStats::Percentile(Speeds, 99.0);
			M.AngMax = M.MaxDegPerFrame / Dt;
			M.AngMaxBone = M.MaxDegBone;

			// 착지 발 수평 속도 p50 — 발 높이가 클립 최저 + FootPlantedHeight 안인 연속 두 프레임의 XY 속도
			TArray<FName> Feet = FeetHint;
			if (Feet.Num() == 0)
			{
				for (const TCHAR* Name : { TEXT("foot_l"), TEXT("foot_r") })
				{
					if (FindBone(S.Bones, FName(Name)) != INDEX_NONE) { Feet.Add(FName(Name)); }
				}
			}
			TArray<double> FootSpeeds;
			for (const FName& Foot : Feet)
			{
				const int32 Bone = FindBone(S.Bones, Foot);
				if (Bone == INDEX_NONE)
				{
					continue;
				}
				M.Feet.Add(Foot);
				double MinZ = TNumericLimits<double>::Max();
				for (int32 F = 0; F < N; ++F) { MinZ = FMath::Min(MinZ, S.Component[F][Bone].GetLocation().Z); }
				for (int32 F = 1; F < N; ++F)
				{
					const FVector A = S.Component[F - 1][Bone].GetLocation();
					const FVector C = S.Component[F][Bone].GetLocation();
					if (A.Z <= MinZ + T.FootPlantedHeight && C.Z <= MinZ + T.FootPlantedHeight)
					{
						FootSpeeds.Add(FVector2D(C.X - A.X, C.Y - A.Y).Size() / Dt);
					}
				}
			}
			if (FootSpeeds.Num() > 0)
			{
				M.FootPlantedP50 = AnimMcpStats::Percentile(FootSpeeds, 50.0);
			}

			// 루프 경계 — 첫·끝 프레임 차(본별 최대·평균) / 프레임당 평균 차의 중앙값
			if (N > 1)
			{
				double BoundarySum = 0.0;
				for (int32 Bone = 0; Bone < B; ++Bone)
				{
					const double Deg = AngleDeg(S.Component[0][Bone].GetRotation(), S.Component[N - 1][Bone].GetRotation());
					M.LoopBoundaryMaxDeg = FMath::Max(M.LoopBoundaryMaxDeg, Deg);
					BoundarySum += Deg;
				}
				const double MedianStep = AnimMcpStats::Percentile(FrameMeans, 50.0);
				if (MedianStep > 1e-6 && B > 0)
				{
					M.LoopBoundaryRatio = (BoundarySum / B) / MedianStep;
				}
			}

			// 루트(본 0) 이동 — 루트 모션이 포즈에 포함돼 있다
			for (int32 F = 1; F < N; ++F)
			{
				M.RootTravel += FVector::Dist(S.Component[F][0].GetLocation(), S.Component[F - 1][0].GetLocation());
			}
			if (N > 0)
			{
				M.RootDisplacement = FVector::Dist(S.Component[N - 1][0].GetLocation(), S.Component[0][0].GetLocation());
			}
			for (int32 F = 1; F < N; ++F)
			{
				const double Prev = S.Component[F - 1][0].GetRotation().Rotator().Yaw;
				const double Cur = S.Component[F][0].GetRotation().Rotator().Yaw;
				M.RootYawDelta += FRotator::NormalizeAxis(Cur - Prev);
			}
			return M;
		}

		/** 프레임별 선속도 (cm/s) — 최대 MaxSamples 개 구간으로 묶어 구간 최대값 (타격 정점이 묶음에 묻히지 않게). bPositions 면 구간 끝 프레임의 위치 (cm) */
		TSharedRef<FJsonObject> ProfileJson(const FSampled& S, const TArray<FName>& ProfileBones, bool bPositions, FIssues& Issues)
		{
			constexpr int32 MaxSamples = 240;
			const double Dt = S.FrameRate > 0.0 ? 1.0 / S.FrameRate : 1.0 / 30.0;
			const int32 Steps = FMath::Max(0, S.Frames - 1);
			const int32 PerBucket = FMath::Max(1, FMath::DivideAndRoundUp(Steps, MaxSamples));
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			TArray<TSharedPtr<FJsonValue>> Times;
			for (int32 Start = 0; Start < Steps; Start += PerBucket)
			{
				// 구간 끝 시각 — 변화 F-1 → F 는 프레임 F 의 시각에 적는다
				Times.Add(MakeShared<FJsonValueNumber>(AnimMcpStats::Round(FMath::Min(Start + PerBucket, Steps) * Dt, 4)));
			}
			Obj->SetArrayField(TEXT("times"), Times);
			Obj->SetNumberField(TEXT("frames_per_sample"), PerBucket);
			TSharedRef<FJsonObject> Bones = AnimMcpJson::MakeObject();
			TSharedRef<FJsonObject> Positions = AnimMcpJson::MakeObject();
			for (const FName& Bone : ProfileBones)
			{
				const int32 Index = FindBone(S.Bones, Bone);
				if (Index == INDEX_NONE)
				{
					Issues.Add(TEXT("info"), TEXT("PROFILE_BONE_MISSING"), FString::Printf(TEXT("profile bone '%s' is not in the pose"), *Bone.ToString()));
					continue;
				}
				TArray<TSharedPtr<FJsonValue>> Speeds;
				TArray<TSharedPtr<FJsonValue>> Points;
				for (int32 Start = 0; Start < Steps; Start += PerBucket)
				{
					double Max = 0.0;
					const int32 End = FMath::Min(Start + PerBucket, Steps);
					for (int32 F = Start + 1; F <= End; ++F)
					{
						Max = FMath::Max(Max, FVector::Dist(S.Component[F][Index].GetLocation(), S.Component[F - 1][Index].GetLocation()) / Dt);
					}
					Speeds.Add(MakeShared<FJsonValueNumber>(AnimMcpStats::Round(Max, 1)));
					if (bPositions)
					{
						const FVector P = S.Component[End][Index].GetLocation();
						Points.Add(MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{ MakeShared<FJsonValueNumber>(AnimMcpStats::Round(P.X, 2)),
							MakeShared<FJsonValueNumber>(AnimMcpStats::Round(P.Y, 2)), MakeShared<FJsonValueNumber>(AnimMcpStats::Round(P.Z, 2)) }));
					}
				}
				Bones->SetArrayField(S.Bones[Index].ToString(), Speeds);
				if (bPositions)
				{
					Positions->SetArrayField(S.Bones[Index].ToString(), Points);
				}
			}
			Obj->SetObjectField(TEXT("speed_cm_s"), Bones);
			if (bPositions)
			{
				Obj->SetObjectField(TEXT("position_cm"), Positions);
			}
			return Obj;
		}

		TSharedRef<FJsonObject> NumericJson(const FSampled& S, const FMetrics& M)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetNumberField(TEXT("frames"), S.Frames);
			Obj->SetNumberField(TEXT("frame_rate"), AnimMcpStats::Round(S.FrameRate));
			Obj->SetNumberField(TEXT("length"), AnimMcpStats::Round(S.Length, 4));
			Obj->SetBoolField(TEXT("loop"), S.bLoop);
			Obj->SetNumberField(TEXT("bones"), S.Bones.Num());
			Obj->SetNumberField(TEXT("ang_speed_p50"), AnimMcpStats::Round(M.AngP50, 1));
			Obj->SetNumberField(TEXT("ang_speed_p99"), AnimMcpStats::Round(M.AngP99, 1));
			Obj->SetNumberField(TEXT("ang_speed_max"), AnimMcpStats::Round(M.AngMax, 1));
			Obj->SetStringField(TEXT("ang_speed_max_bone"), M.AngMaxBone.ToString());
			Obj->SetNumberField(TEXT("max_deg_per_frame"), AnimMcpStats::Round(M.MaxDegPerFrame, 2));
			Obj->SetNumberField(TEXT("max_deg_frame"), M.MaxDegFrame);
			TArray<TSharedPtr<FJsonValue>> Feet;
			for (const FName& Foot : M.Feet) { Feet.Add(MakeShared<FJsonValueString>(Foot.ToString())); }
			Obj->SetArrayField(TEXT("feet"), Feet);
			if (M.FootPlantedP50.IsSet()) { Obj->SetNumberField(TEXT("foot_planted_p50"), AnimMcpStats::Round(M.FootPlantedP50.GetValue(), 2)); }
			else { Obj->SetField(TEXT("foot_planted_p50"), MakeShared<FJsonValueNull>()); }
			Obj->SetNumberField(TEXT("loop_boundary_max_deg"), AnimMcpStats::Round(M.LoopBoundaryMaxDeg, 2));
			if (M.LoopBoundaryRatio.IsSet()) { Obj->SetNumberField(TEXT("loop_boundary_ratio"), AnimMcpStats::Round(M.LoopBoundaryRatio.GetValue(), 2)); }
			else { Obj->SetField(TEXT("loop_boundary_ratio"), MakeShared<FJsonValueNull>()); }
			Obj->SetNumberField(TEXT("root_travel_cm"), AnimMcpStats::Round(M.RootTravel, 2));
			Obj->SetNumberField(TEXT("root_displacement_cm"), AnimMcpStats::Round(M.RootDisplacement, 2));
			Obj->SetNumberField(TEXT("root_yaw_delta_deg"), AnimMcpStats::Round(M.RootYawDelta, 2));
			Obj->SetField(TEXT("pelvis"), AnimMcpJson::StringOrNull(S.Pelvis.IsNone() ? FString() : S.Pelvis.ToString()));
			if (S.PelvisHeight.IsSet()) { Obj->SetNumberField(TEXT("pelvis_height_cm"), AnimMcpStats::Round(S.PelvisHeight.GetValue(), 2)); }
			else { Obj->SetField(TEXT("pelvis_height_cm"), MakeShared<FJsonValueNull>()); }
			return Obj;
		}

		void RatioCheck(TSharedRef<FJsonObject> Relative, FIssues& Issues, const TCHAR* Key, double Value, double Min, double Max, const TCHAR* Code, const FString& What)
		{
			Relative->SetNumberField(Key, AnimMcpStats::Round(Value, 3));
			if (Value < Min || Value > Max)
			{
				TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
				Extra->SetNumberField(TEXT("value"), AnimMcpStats::Round(Value, 3));
				Extra->SetArrayField(TEXT("range"), { MakeShared<FJsonValueNumber>(Min), MakeShared<FJsonValueNumber>(Max) });
				Issues.Add(TEXT("warning"), Code, FString::Printf(TEXT("%s ratio %.3f is outside %.2f..%.2f"), *What, Value, Min, Max), Extra);
			}
		}

		/** 같은 스켈레톤 — 본별 컴포넌트 공간 회전·위치 차 (회귀 비교) */
		TSharedRef<FJsonObject> CompareSameSkeleton(const FSampled& A, const FSampled& S)
		{
			const int32 N = FMath::Min(A.Frames, S.Frames);
			TArray<double> AllRot;
			TArray<double> AllPos;
			TArray<TPair<double, FName>> PerBoneMax;
			for (int32 Bone = 0; Bone < A.Bones.Num(); ++Bone)
			{
				const int32 Other = FindBone(S.Bones, A.Bones[Bone]);
				if (Other == INDEX_NONE)
				{
					continue;
				}
				double BoneMax = 0.0;
				for (int32 F = 0; F < N; ++F)
				{
					const double Deg = AngleDeg(A.Component[F][Bone].GetRotation(), S.Component[F][Other].GetRotation());
					AllRot.Add(Deg);
					AllPos.Add(FVector::Dist(A.Component[F][Bone].GetLocation(), S.Component[F][Other].GetLocation()));
					BoneMax = FMath::Max(BoneMax, Deg);
				}
				PerBoneMax.Emplace(BoneMax, A.Bones[Bone]);
			}
			PerBoneMax.Sort([](const TPair<double, FName>& X, const TPair<double, FName>& Y) { return X.Key > Y.Key; });
			TSharedRef<FJsonObject> Rot = AnimMcpJson::MakeObject();
			Rot->SetNumberField(TEXT("p50"), AnimMcpStats::Round(AnimMcpStats::Percentile(AllRot, 50.0)));
			Rot->SetNumberField(TEXT("p99"), AnimMcpStats::Round(AnimMcpStats::Percentile(AllRot, 99.0)));
			Rot->SetNumberField(TEXT("max"), AnimMcpStats::Round(AllRot.Num() ? FMath::Max(AllRot) : 0.0));
			TArray<TSharedPtr<FJsonValue>> Worst;
			for (int32 i = 0; i < FMath::Min(5, PerBoneMax.Num()); ++i)
			{
				TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
				Item->SetStringField(TEXT("bone"), PerBoneMax[i].Value.ToString());
				Item->SetNumberField(TEXT("max_deg"), AnimMcpStats::Round(PerBoneMax[i].Key));
				Worst.Add(MakeShared<FJsonValueObject>(Item));
			}
			Rot->SetArrayField(TEXT("worst"), Worst);
			TSharedRef<FJsonObject> Pos = AnimMcpJson::MakeObject();
			Pos->SetNumberField(TEXT("p50"), AnimMcpStats::Round(AnimMcpStats::Percentile(AllPos, 50.0)));
			Pos->SetNumberField(TEXT("p99"), AnimMcpStats::Round(AnimMcpStats::Percentile(AllPos, 99.0)));
			Pos->SetNumberField(TEXT("max"), AnimMcpStats::Round(AllPos.Num() ? FMath::Max(AllPos) : 0.0));
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("mode"), TEXT("same_skeleton"));
			Obj->SetNumberField(TEXT("frames_compared"), N);
			Obj->SetNumberField(TEXT("bones_compared"), PerBoneMax.Num());
			Obj->SetObjectField(TEXT("per_bone_rot_diff_deg"), Rot);
			Obj->SetObjectField(TEXT("per_bone_pos_diff_cm"), Pos);
			return Obj;
		}

		/** 다른 스켈레톤 — 소스 대비 비율 (리타깃 결과 검증) */
		TSharedRef<FJsonObject> CompareRetargeted(const FSampled& A, const FMetrics& MA, const FSampled& S, const FMetrics& MS, const FThresholds& T, FIssues& Issues)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("mode"), TEXT("retargeted"));
			if (MS.AngP99 > 1e-3)
			{
				RatioCheck(Obj, Issues, TEXT("ang_speed_p99_ratio"), MA.AngP99 / MS.AngP99, T.AngSpeedP99RatioMin, T.AngSpeedP99RatioMax, TEXT("ANG_SPEED_RATIO"), TEXT("Angular speed p99"));
			}
			// 이름이 같은 본만 모은 p99 비 — 본 구성이 다른 스켈레톤끼리도 같은 부위를 비교한다 (공통 본 10개 이상일 때)
			{
				TArray<double> SpeedA, SpeedS;
				const double DtA = A.FrameRate > 0.0 ? 1.0 / A.FrameRate : 1.0 / 30.0;
				const double DtS = S.FrameRate > 0.0 ? 1.0 / S.FrameRate : 1.0 / 30.0;
				int32 Common = 0;
				for (int32 Bone = 0; Bone < A.Bones.Num(); ++Bone)
				{
					const int32 Other = FindBone(S.Bones, A.Bones[Bone]);
					if (Other == INDEX_NONE) { continue; }
					++Common;
					for (int32 F = 1; F < A.Frames; ++F) { SpeedA.Add(AngleDeg(A.Component[F][Bone].GetRotation(), A.Component[F - 1][Bone].GetRotation()) / DtA); }
					for (int32 F = 1; F < S.Frames; ++F) { SpeedS.Add(AngleDeg(S.Component[F][Other].GetRotation(), S.Component[F - 1][Other].GetRotation()) / DtS); }
				}
				Obj->SetNumberField(TEXT("common_bones"), Common);
				const double P99S = AnimMcpStats::Percentile(SpeedS, 99.0);
				if (Common >= 10 && P99S > 1e-3)
				{
					RatioCheck(Obj, Issues, TEXT("common_bones_ang_speed_p99_ratio"), AnimMcpStats::Percentile(SpeedA, 99.0) / P99S,
						T.AngSpeedP99RatioMin, T.AngSpeedP99RatioMax, TEXT("COMMON_BONES_ANG_SPEED_RATIO"), TEXT("Common-bone angular speed p99"));
				}
			}
			// 크기 보정 — 펠비스 기준 포즈 높이 비 (다리 길이 비의 대용)
			double Scale = 1.0;
			if (A.PelvisHeight.IsSet() && S.PelvisHeight.IsSet() && S.PelvisHeight.GetValue() > 1.0)
			{
				Scale = A.PelvisHeight.GetValue() / S.PelvisHeight.GetValue();
				Obj->SetNumberField(TEXT("pelvis_height_ratio"), AnimMcpStats::Round(Scale, 3));
			}
			else
			{
				Obj->SetField(TEXT("pelvis_height_ratio"), MakeShared<FJsonValueNull>());
				Issues.Add(TEXT("info"), TEXT("NO_PELVIS_SCALE"), TEXT("Pelvis not found on one side — distance ratios are not size-corrected (pass pelvis / source_pelvis)"));
			}
			if (MA.FootPlantedP50.IsSet() && MS.FootPlantedP50.IsSet() && MS.FootPlantedP50.GetValue() >= 1.0)
			{
				RatioCheck(Obj, Issues, TEXT("foot_planted_p50_ratio"), (MA.FootPlantedP50.GetValue() / MS.FootPlantedP50.GetValue()) / Scale, 0.0, T.FootPlantedRatioMax, TEXT("FOOT_SLIDE_RATIO"), TEXT("Planted-foot horizontal speed p50 (size-corrected)"));
			}
			else
			{
				Obj->SetField(TEXT("foot_planted_p50_ratio"), MakeShared<FJsonValueNull>());
				Issues.Add(TEXT("info"), TEXT("FOOT_RATIO_SKIPPED"), TEXT("Feet not found, or the source's planted feet barely move (< 1 cm/s) — no foot slide ratio"));
			}
			if (MS.RootTravel > 1.0)
			{
				RatioCheck(Obj, Issues, TEXT("root_travel_ratio"), (MA.RootTravel / MS.RootTravel) / Scale, T.RootTravelRatioMin, T.RootTravelRatioMax, TEXT("ROOT_TRAVEL_RATIO"), TEXT("Root travel (size-corrected)"));
			}
			else
			{
				Obj->SetField(TEXT("root_travel_ratio"), MakeShared<FJsonValueNull>());
			}
			const double LengthDiff = FMath::Abs(A.Length - S.Length);
			Obj->SetNumberField(TEXT("length_diff"), AnimMcpStats::Round(LengthDiff, 4));
			if (A.FrameRate > 0.0 && LengthDiff > 1.0 / A.FrameRate + 1e-4)
			{
				Issues.Add(TEXT("warning"), TEXT("LENGTH_CHANGED"), FString::Printf(TEXT("Length %.4fs differs from the source %.4fs by more than a frame"), A.Length, S.Length));
			}
			if (A.bLoop && MA.LoopBoundaryRatio.IsSet() && MS.LoopBoundaryRatio.IsSet() && MS.LoopBoundaryRatio.GetValue() > 1e-6)
			{
				const double Ratio = MA.LoopBoundaryRatio.GetValue() / MS.LoopBoundaryRatio.GetValue();
				RatioCheck(Obj, Issues, TEXT("loop_boundary_ratio_vs_source"), Ratio, 0.0, T.LoopBoundaryRatioMax, TEXT("LOOP_BOUNDARY_WORSE"), TEXT("Loop boundary jump vs source"));
			}
			return Obj;
		}

		int32 StatusRank(const FString& Status)
		{
			if (Status == TEXT("FAILED")) { return 3; }
			if (Status == TEXT("NEEDS_REVIEW")) { return 2; }
			if (Status == TEXT("PASSED_WITH_WARNINGS")) { return 1; }
			return 0;
		}

		const TCHAR* const ThresholdKeys[] = {
			TEXT("max_deg_per_frame"), TEXT("ang_speed_p99_ratio_min"), TEXT("ang_speed_p99_ratio_max"), TEXT("foot_planted_ratio_max"),
			TEXT("root_travel_ratio_min"), TEXT("root_travel_ratio_max"), TEXT("loop_boundary_ratio_max"), TEXT("foot_planted_height"), TEXT("seam_ratio_max") };

		double* ThresholdField(FThresholds& T, const FString& Key)
		{
			if (Key == ThresholdKeys[0]) { return &T.MaxDegPerFrame; }
			if (Key == ThresholdKeys[1]) { return &T.AngSpeedP99RatioMin; }
			if (Key == ThresholdKeys[2]) { return &T.AngSpeedP99RatioMax; }
			if (Key == ThresholdKeys[3]) { return &T.FootPlantedRatioMax; }
			if (Key == ThresholdKeys[4]) { return &T.RootTravelRatioMin; }
			if (Key == ThresholdKeys[5]) { return &T.RootTravelRatioMax; }
			if (Key == ThresholdKeys[6]) { return &T.LoopBoundaryRatioMax; }
			if (Key == ThresholdKeys[7]) { return &T.FootPlantedHeight; }
			if (Key == ThresholdKeys[8]) { return &T.SeamRatioMax; }
			return nullptr;
		}
	}

	/**
	 * 이음매 F(프레임) 주변의 튐 — 이음매를 낀 두 변화(F-1 → F, F → F+1)의 최대 / 앞 4 변화 중앙값과 뒤 4 변화 중앙값 중 큰 쪽.
	 * 앞뒤를 따로 보는 이유: 포즈 유지 경계처럼 한쪽이 정지면 섞은 중앙값이 반으로 떨어져 "멈춤"을 튐으로 센다(Phase 2 실측 2.75).
	 * 양쪽이 다 거의 정지면 전체 중앙값의 1/4 을 바닥으로 쓴다
	 */
	double SeamStepRatio(const TArray<double>& StepMeans, int32 SeamFrame)
	{
		constexpr int32 Window = 4;
		if (StepMeans.Num() == 0)
		{
			return 0.0;
		}
		// StepMeans[i] = 프레임 i → i+1
		const int32 First = FMath::Clamp(SeamFrame - 1, 0, StepMeans.Num() - 1);
		const int32 Last = FMath::Clamp(SeamFrame, 0, StepMeans.Num() - 1);
		double Seam = 0.0;
		for (int32 i = First; i <= Last; ++i) { Seam = FMath::Max(Seam, StepMeans[i]); }
		TArray<double> Before, After;
		for (int32 i = First - Window; i < First; ++i) { if (StepMeans.IsValidIndex(i)) { Before.Add(StepMeans[i]); } }
		for (int32 i = Last + 1; i <= Last + Window; ++i) { if (StepMeans.IsValidIndex(i)) { After.Add(StepMeans[i]); } }
		const double Floor = FMath::Max(AnimMcpStats::Percentile(StepMeans, 50.0) * 0.25, 1e-3);
		const double Denominator = FMath::Max(FMath::Max(AnimMcpStats::Percentile(Before, 50.0), AnimMcpStats::Percentile(After, 50.0)), Floor);
		return Seam / Denominator;
	}

	bool ParseExpect(const TSharedPtr<FJsonObject>& Object, FExpect& Out, FAnimMcpError& OutError)
	{
		if (!Object.IsValid())
		{
			return true;
		}
		auto Bad = [&OutError](const FString& Key, const FString& Message)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), TEXT("expect"));
			Details->SetStringField(TEXT("key"), Key);
			Details->SetArrayField(TEXT("allowed"), { MakeShared<FJsonValueString>(TEXT("length")), MakeShared<FJsonValueString>(TEXT("length_tolerance")),
				MakeShared<FJsonValueString>(TEXT("loop")), MakeShared<FJsonValueString>(TEXT("root_yaw_delta")), MakeShared<FJsonValueString>(TEXT("root_yaw_tolerance")) });
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
			return false;
		};
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : Object->Values)
		{
			const TSharedPtr<FJsonValue>& V = Pair.Value;
			if (Pair.Key == TEXT("loop"))
			{
				if (!V.IsValid() || V->Type != EJson::Boolean) { return Bad(Pair.Key, TEXT("expect.loop must be a boolean")); }
				Out.bLoop = V->AsBool();
				continue;
			}
			if (!V.IsValid() || V->Type != EJson::Number)
			{
				return Bad(Pair.Key, FString::Printf(TEXT("expect.%s is unknown or not a number"), *Pair.Key));
			}
			const double Value = V->AsNumber();
			if (Pair.Key == TEXT("length")) { Out.Length = Value; }
			else if (Pair.Key == TEXT("length_tolerance")) { Out.LengthTolerance = FMath::Abs(Value); }
			else if (Pair.Key == TEXT("root_yaw_delta")) { Out.RootYawDelta = Value; }
			else if (Pair.Key == TEXT("root_yaw_tolerance")) { Out.RootYawTolerance = FMath::Abs(Value); }
			else { return Bad(Pair.Key, FString::Printf(TEXT("expect.%s is unknown"), *Pair.Key)); }
		}
		return true;
	}

	bool ParseThresholds(const TSharedPtr<FJsonObject>& Object, FThresholds& Out, FAnimMcpError& OutError)
	{
		if (!Object.IsValid())
		{
			return true;
		}
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : Object->Values)
		{
			double* Field = ThresholdField(Out, Pair.Key);
			double Value = 0.0;
			if (!Field || !Pair.Value.IsValid() || !Pair.Value->TryGetNumber(Value) || Pair.Value->Type != EJson::Number)
			{
				TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
				Details->SetStringField(TEXT("field"), TEXT("thresholds"));
				Details->SetStringField(TEXT("key"), Pair.Key);
				TArray<TSharedPtr<FJsonValue>> Allowed;
				for (const TCHAR* Key : ThresholdKeys) { Allowed.Add(MakeShared<FJsonValueString>(Key)); }
				Details->SetArrayField(TEXT("allowed"), Allowed);
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("thresholds.%s is unknown or not a number"), *Pair.Key), Details);
				return false;
			}
			*Field = Value;
		}
		return true;
	}

	TSharedRef<FJsonObject> ThresholdsToJson(const FThresholds& Thresholds)
	{
		FThresholds Copy = Thresholds;
		TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
		for (const TCHAR* Key : ThresholdKeys)
		{
			Obj->SetNumberField(Key, *ThresholdField(Copy, Key));
		}
		return Obj;
	}

	FString WorstStatus(const FString& A, const FString& B)
	{
		return StatusRank(A) >= StatusRank(B) ? A : B;
	}

	double MaxDegPerFrame(const UAnimSequence* Sequence)
	{
		FSampled S;
		if (!Sequence || !Sample(Sequence, NAME_None, S))
		{
			return 0.0;
		}
		return Measure(S, {}, FThresholds()).MaxDegPerFrame;
	}

	TSharedRef<FJsonObject> Validate(const UAnimSequence* Asset, const UAnimSequence* Source, const FOptions& Options)
	{
		const double Start = FPlatformTime::Seconds();
		FIssues Structural;
		FIssues RelativeIssues;
		FIssues RequestIssues;
		TSharedRef<FJsonObject> Result = AnimMcpJson::MakeObject();
		Result->SetStringField(TEXT("asset"), Asset->GetPathName());
		Result->SetField(TEXT("source"), AnimMcpJson::ObjectPathOrNull(Source));
		Result->SetField(TEXT("skeleton"), AnimMcpJson::ObjectPathOrNull(Asset->GetSkeleton()));

		// ---- 구조 ----
		const USkeleton* Skeleton = Asset->GetSkeleton();
		if (!Skeleton)
		{
			Structural.Add(TEXT("error"), TEXT("NO_SKELETON"), TEXT("The sequence has no skeleton"));
		}
		if (Options.ExpectedSkeleton && Skeleton != Options.ExpectedSkeleton)
		{
			Structural.Add(TEXT("error"), TEXT("SKELETON_MISMATCH"), FString::Printf(TEXT("Skeleton is '%s', expected '%s'"), *GetPathNameSafe(Skeleton), *Options.ExpectedSkeleton->GetPathName()));
		}
		if (Asset->GetNumberOfSampledKeys() < 1 || Asset->GetPlayLength() <= 0.f)
		{
			Structural.Add(TEXT("error"), TEXT("NO_FRAMES"), FString::Printf(TEXT("%d frame(s), length %.4fs"), Asset->GetNumberOfSampledKeys(), Asset->GetPlayLength()));
		}
		if (Skeleton && Options.bStructural)
		{
			TArray<FName> Tracks;
			if (const IAnimationDataModel* Model = Asset->GetDataModel())
			{
				Model->GetBoneTrackNames(Tracks);
			}
			TArray<FString> Missing;
			for (const FName& Track : Tracks)
			{
				if (Skeleton->GetReferenceSkeleton().FindBoneIndex(Track) == INDEX_NONE) { Missing.Add(Track.ToString()); }
			}
			if (Missing.Num() > 0)
			{
				Structural.Add(TEXT("error"), TEXT("TRACK_BONE_MISSING"), FString::Printf(TEXT("%d bone track(s) are not in the skeleton: %s"), Missing.Num(), *FString::Join(Missing, TEXT(", "))));
			}
			const UPackage* Package = Asset->GetPackage();
			if (Package->IsDirty() || !FPackageName::DoesPackageExist(Package->GetName()))
			{
				Structural.Add(TEXT("info"), TEXT("NOT_SAVED"), TEXT("The asset has unsaved changes (expected with save=false)"));
			}
		}

		// ---- 수치 ----
		FSampled A;
		const bool bSampled = !Structural.bError && Sample(Asset, Options.Pelvis, A);
		if (!Structural.bError && !bSampled)
		{
			Structural.Add(TEXT("error"), TEXT("SAMPLE_FAILED"), TEXT("UAnimPoseExtensions::GetAnimPoseAtFrame returned an invalid pose"));
		}
		if (bSampled)
		{
			const FMetrics MA = Measure(A, Options.Feet, Options.Thresholds);
			if (MA.bNaN)
			{
				Structural.Add(TEXT("error"), TEXT("NAN"), FString::Printf(TEXT("NaN in the component-space pose of '%s'"), *MA.NaNBone.ToString()));
			}
			if (MA.bBadScale)
			{
				Structural.Add(TEXT("error"), TEXT("ABNORMAL_SCALE"), FString::Printf(TEXT("Scale %.4g on '%s' (allowed 0.001..10)"), MA.BadScale, *MA.BadScaleBone.ToString()));
			}
			if (Options.bNumeric)
			{
				TSharedRef<FJsonObject> Numeric = NumericJson(A, MA);
				if (Options.ProfileBones.Num() > 0)
				{
					Numeric->SetObjectField(TEXT("profile"), ProfileJson(A, Options.ProfileBones, Options.bProfilePositions, Structural));
				}
				Result->SetObjectField(TEXT("numeric"), Numeric);
			}

			// ---- 요청 충족 (Phase 2) ----
			if (Options.Expect.IsSet() || Options.Seams.Num() > 0)
			{
				TSharedRef<FJsonObject> Request = AnimMcpJson::MakeObject();
				const FExpect& E = Options.Expect;
				if (E.Length.IsSet())
				{
					const double Tolerance = E.LengthTolerance.IsSet() ? E.LengthTolerance.GetValue() : (A.FrameRate > 0.0 ? 1.0 / A.FrameRate : 1.0 / 30.0) + 1e-4;
					Request->SetNumberField(TEXT("length"), AnimMcpStats::Round(A.Length, 4));
					if (FMath::Abs(A.Length - E.Length.GetValue()) > Tolerance)
					{
						RequestIssues.Add(TEXT("error"), TEXT("EXPECT_LENGTH"), FString::Printf(TEXT("Length %.4fs, expected %.4fs (±%.4fs)"), A.Length, E.Length.GetValue(), Tolerance));
					}
				}
				if (E.bLoop.IsSet())
				{
					Request->SetBoolField(TEXT("loop"), A.bLoop);
					if (A.bLoop != E.bLoop.GetValue())
					{
						RequestIssues.Add(TEXT("error"), TEXT("EXPECT_LOOP"), FString::Printf(TEXT("bLoop is %s, expected %s"), A.bLoop ? TEXT("true") : TEXT("false"), E.bLoop.GetValue() ? TEXT("true") : TEXT("false")));
					}
				}
				if (E.RootYawDelta.IsSet())
				{
					Request->SetNumberField(TEXT("root_yaw_delta_deg"), AnimMcpStats::Round(MA.RootYawDelta, 2));
					if (FMath::Abs(MA.RootYawDelta - E.RootYawDelta.GetValue()) > E.RootYawTolerance)
					{
						RequestIssues.Add(TEXT("error"), TEXT("EXPECT_ROOT_YAW"), FString::Printf(TEXT("Root yaw turns %.1f° first → last, expected %.1f° (±%.1f°)"), MA.RootYawDelta, E.RootYawDelta.GetValue(), E.RootYawTolerance));
					}
				}
				TArray<TSharedPtr<FJsonValue>> SeamItems;
				for (const double Time : Options.Seams)
				{
					const int32 Frame = FMath::Clamp(FMath::RoundToInt32(Time * A.FrameRate), 0, A.Frames - 1);
					const double Ratio = SeamStepRatio(MA.StepMeans, Frame);
					TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
					Item->SetNumberField(TEXT("time"), AnimMcpStats::Round(Time, 4));
					Item->SetNumberField(TEXT("frame"), Frame);
					Item->SetNumberField(TEXT("step_ratio"), AnimMcpStats::Round(Ratio, 2));
					SeamItems.Add(MakeShared<FJsonValueObject>(Item));
					if (Ratio > Options.Thresholds.SeamRatioMax)
					{
						RequestIssues.Add(TEXT("warning"), TEXT("SEAM_JUMP"), FString::Printf(TEXT("Pose jumps at the seam %.3fs (frame %d): step %.2fx the surrounding frames (max %.2f)"), Time, Frame, Ratio, Options.Thresholds.SeamRatioMax), Item);
					}
				}
				if (Options.Seams.Num() > 0)
				{
					Request->SetArrayField(TEXT("seams"), SeamItems);
				}
				Request->SetArrayField(TEXT("issues"), RequestIssues.Items);
				Result->SetObjectField(TEXT("request"), Request);
			}

			// ---- 상대 ----
			// 소스는 상대 비교 외에 "물려받은 튐" 기준(절대 규칙 완화)에도 쓴다 — 호출자가 기준값을 주면 샘플하지 않는다
			TOptional<double> SourceMaxDegPerFrame = Options.InheritedMaxDegPerFrame;
			if (Source && (Options.bRelative || (Options.bNumeric && !SourceMaxDegPerFrame.IsSet())))
			{
				FSampled S;
				if (!Sample(Source, Options.SourcePelvis, S))
				{
					if (Options.bRelative)
					{
						RelativeIssues.Add(TEXT("warning"), TEXT("SOURCE_SAMPLE_FAILED"), FString::Printf(TEXT("Could not sample source '%s'"), *Source->GetPathName()));
						RelativeIssues.bUndetermined = true;
					}
				}
				else
				{
					const FMetrics MS = Measure(S, Options.SourceFeet, Options.Thresholds);
					if (!SourceMaxDegPerFrame.IsSet())
					{
						SourceMaxDegPerFrame = MS.MaxDegPerFrame;
					}
					if (Options.bRelative && Source->GetSkeleton() == Skeleton)
					{
						Result->SetObjectField(TEXT("relative"), CompareSameSkeleton(A, S));
					}
					else if (Options.bRelative)
					{
						TSharedRef<FJsonObject> Relative = CompareRetargeted(A, MA, S, MS, Options.Thresholds, RelativeIssues);
						Relative->SetObjectField(TEXT("source_numeric"), NumericJson(S, MS));
						Result->SetObjectField(TEXT("relative"), Relative);
					}
				}
			}

			// ---- 절대: 한 프레임 회전 ----
			// 30fps 마켓 공격은 손·손가락이 프레임당 90° 를 넘기도 한다(Phase 1 실측: Katana_Attack_Slash1 109°). 소스에 이미 있던 튐은 리타깃이 만든
			// 깨짐이 아니므로, 소스가 있으면 소스 최대 + InheritedJumpMargin 이내는 경고로 낮춘다. 소스가 없으면 절대 규칙 그대로(감사 §5)
			if (Options.bNumeric && MA.MaxDegPerFrame > Options.Thresholds.MaxDegPerFrame)
			{
				constexpr double InheritedJumpMargin = 10.0;
				TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
				Extra->SetNumberField(TEXT("frame"), MA.MaxDegFrame);
				Extra->SetStringField(TEXT("bone"), MA.MaxDegBone.ToString());
				Extra->SetNumberField(TEXT("deg"), AnimMcpStats::Round(MA.MaxDegPerFrame, 2));
				if (SourceMaxDegPerFrame.IsSet())
				{
					Extra->SetNumberField(TEXT("source_deg"), AnimMcpStats::Round(SourceMaxDegPerFrame.GetValue(), 2));
				}
				if (SourceMaxDegPerFrame.IsSet() && MA.MaxDegPerFrame <= SourceMaxDegPerFrame.GetValue() + InheritedJumpMargin)
				{
					Structural.Add(TEXT("warning"), TEXT("ROTATION_JUMP_INHERITED"), FString::Printf(TEXT("'%s' rotates %.1f° in one frame (frame %d) — over %.0f°, but the source already jumps %.1f°"),
						*MA.MaxDegBone.ToString(), MA.MaxDegPerFrame, MA.MaxDegFrame, Options.Thresholds.MaxDegPerFrame, SourceMaxDegPerFrame.GetValue()), Extra);
				}
				else
				{
					Structural.Add(TEXT("error"), TEXT("ROTATION_JUMP"), FString::Printf(TEXT("'%s' rotates %.1f° in one frame (frame %d) — over %.0f°%s"), *MA.MaxDegBone.ToString(), MA.MaxDegPerFrame, MA.MaxDegFrame, Options.Thresholds.MaxDegPerFrame,
						SourceMaxDegPerFrame.IsSet() ? *FString::Printf(TEXT(" and %.1f° above the source"), MA.MaxDegPerFrame - SourceMaxDegPerFrame.GetValue()) : TEXT("")), Extra);
				}
			}
		}
		Result->SetArrayField(TEXT("structural"), Structural.Items);
		if (Result->HasField(TEXT("relative")))
		{
			Result->GetObjectField(TEXT("relative"))->SetArrayField(TEXT("issues"), RelativeIssues.Items);
		}
		else if (RelativeIssues.Items.Num() > 0)
		{
			TSharedRef<FJsonObject> Relative = AnimMcpJson::MakeObject();
			Relative->SetArrayField(TEXT("issues"), RelativeIssues.Items);
			Result->SetObjectField(TEXT("relative"), Relative);
		}

		// 시각 확인은 자동 검사가 대신하지 못한다 — 항상 남긴다
		TArray<TSharedPtr<FJsonValue>> NeedsReview;
		{
			TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
			Item->SetStringField(TEXT("item"), TEXT("visual"));
			Item->SetStringField(TEXT("message"), TEXT("Watch it in Persona or PIE — structural/numeric checks do not judge motion quality"));
			NeedsReview.Add(MakeShared<FJsonValueObject>(Item));
		}
		Result->SetArrayField(TEXT("needs_review"), NeedsReview);

		FString Status = TEXT("PASSED");
		if (Structural.bError || RequestIssues.bError) { Status = TEXT("FAILED"); }
		else if (RelativeIssues.bUndetermined) { Status = TEXT("NEEDS_REVIEW"); }
		else if (Structural.bWarning || RelativeIssues.bWarning || RequestIssues.bWarning) { Status = TEXT("PASSED_WITH_WARNINGS"); }
		Result->SetStringField(TEXT("status"), Status);
		Result->SetNumberField(TEXT("seconds"), AnimMcpStats::Round(FPlatformTime::Seconds() - Start));
		return Result;
	}
}
