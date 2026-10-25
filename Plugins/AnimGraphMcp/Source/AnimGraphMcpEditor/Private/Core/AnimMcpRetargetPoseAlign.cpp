#include "AnimMcpRetargetPoseAlign.h"

#include "Algo/AllOf.h"
#include "Algo/AnyOf.h"
#include "AnimMcpGeneration.h"
#include "AnimMcpStats.h"
#include "Bridge/AnimMcpTypes.h"
#include "Engine/SkeletalMesh.h"
#include "ReferenceSkeleton.h"
#include "RetargetEditor/IKRetargeterController.h"
#include "Retargeter/IKRetargeter.h"
#include "Retargeter/IKRetargetProcessor.h"
#include "Retargeter/IKRetargetProfile.h"
#include "Retargeter/RetargetOps/FKChainsOp.h"

namespace AnimMcpRetargetPoseAlign
{
	namespace
	{
		constexpr ERetargetSourceOrTarget Target = ERetargetSourceOrTarget::Target;
		constexpr ERetargetSourceOrTarget Source = ERetargetSourceOrTarget::Source;
		/** 구간 · 랜드마크가 이보다 짧으면(cm) 방향이 없다 — CMU Neck · 쇄골은 부모와 같은 자리(OFFSET 0) */
		constexpr double MinSegmentCm = 0.5;
		/** 랜드마크 방향이 이만큼 퍼져야(최대 사이각) 굴림까지 맞춘다 */
		constexpr double MinSpreadDeg = 10.0;
		/** 기준틀 맞춤 뒤 이보다 어긋난 랜드마크는 빼고 다시 맞춘다 — 관절 자리가 해부적으로 다른 것(엄지 시작: HK 35° · SOMA 24°) */
		constexpr double MaxResidualDeg = 15.0;
		/** 이보다 작은 보정은 넣지도 적지도 않는다 */
		constexpr double MinCorrectionDeg = 1e-3;
		/** 거울 짝 판정 허용 오차 = 두 시작 관절 거리 × 이 비율(최소 MinSegmentCm) — Vesper 몸 본 좌우 잔차 p50 0.27 cm */
		constexpr double MirrorToleranceRatio = 0.05;
		/** 거울 짝들의 좌우축이 이 안에서 모여야 같은 무리 — 같은 쪽 나란한 손가락끼리의 '짝'은 손 옆 방향이라 빠진다 */
		constexpr double AxisAgreeDeg = 10.0;
		/** 축 체인 = 모든 본이 정중선에서 '가장 안쪽 거울 짝 반폭 × 이 비율' 안 — Vesper 쇄골 반폭 1.76 cm → 0.44 cm, 척추 · 목 · head 0.00 cm */
		constexpr double AxialOffsetRatio = 0.25;

		struct FChainPair
		{
			FName TargetChain;
			FName SourceChain;
			const FResolvedBoneChain* TargetBones = nullptr;
			const FResolvedBoneChain* SourceBones = nullptr;
			FRetargetFKChainSettings* Settings = nullptr;

			bool IsOneToOne() const
			{
				return TargetBones->BoneIndices.Num() >= 2 && TargetBones->BoneIndices.Num() == SourceBones->BoneIndices.Num();
			}
		};

		double Deg(const FQuat& Q)
		{
			return FMath::RadiansToDegrees(Q.GetNormalized().AngularDistance(FQuat::Identity));
		}

		double MaxPairAngleDeg(const TArray<FVector>& Dirs)
		{
			double Max = 0.0;
			for (int32 i = 0; i < Dirs.Num(); ++i)
			{
				for (int32 j = i + 1; j < Dirs.Num(); ++j)
				{
					Max = FMath::Max(Max, FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(Dirs[i], Dirs[j]), -1.0, 1.0))));
				}
			}
			return Max;
		}

		/** Horn(1987) — Σ|R·From − To|² 를 최소로 하는 회전. N(4x4 대칭)의 최대 고유값 고유벡터 = (w, x, y, z), 고유값은 순환 야코비로 */
		FQuat FitRotation(const TArray<FVector>& From, const TArray<FVector>& To)
		{
			double S[3][3] = {};
			for (int32 k = 0; k < From.Num(); ++k)
			{
				for (int32 r = 0; r < 3; ++r)
				{
					for (int32 c = 0; c < 3; ++c)
					{
						S[r][c] += From[k][r] * To[k][c];
					}
				}
			}
			const double Sxx = S[0][0], Sxy = S[0][1], Sxz = S[0][2], Syx = S[1][0], Syy = S[1][1], Syz = S[1][2], Szx = S[2][0], Szy = S[2][1], Szz = S[2][2];
			double A[4][4] = {
				{ Sxx + Syy + Szz, Syz - Szy, Szx - Sxz, Sxy - Syx },
				{ Syz - Szy, Sxx - Syy - Szz, Sxy + Syx, Szx + Sxz },
				{ Szx - Sxz, Sxy + Syx, -Sxx + Syy - Szz, Syz + Szy },
				{ Sxy - Syx, Szx + Sxz, Syz + Szy, -Sxx - Syy + Szz } };
			double V[4][4] = { { 1, 0, 0, 0 }, { 0, 1, 0, 0 }, { 0, 0, 1, 0 }, { 0, 0, 0, 1 } };
			for (int32 Sweep = 0; Sweep < 60; ++Sweep)
			{
				double Off = 0.0;
				for (int32 p = 0; p < 4; ++p) { for (int32 q = p + 1; q < 4; ++q) { Off += A[p][q] * A[p][q]; } }
				if (Off < 1e-24) { break; }
				for (int32 p = 0; p < 4; ++p)
				{
					for (int32 q = p + 1; q < 4; ++q)
					{
						if (FMath::Abs(A[p][q]) < 1e-300) { continue; }
						const double Theta = (A[q][q] - A[p][p]) / (2.0 * A[p][q]);
						const double T = (Theta >= 0.0 ? 1.0 : -1.0) / (FMath::Abs(Theta) + FMath::Sqrt(Theta * Theta + 1.0));
						const double C = 1.0 / FMath::Sqrt(T * T + 1.0), Sn = T * C;
						for (int32 k = 0; k < 4; ++k) { const double Kp = A[k][p], Kq = A[k][q]; A[k][p] = C * Kp - Sn * Kq; A[k][q] = Sn * Kp + C * Kq; }
						for (int32 k = 0; k < 4; ++k) { const double Pk = A[p][k], Qk = A[q][k]; A[p][k] = C * Pk - Sn * Qk; A[q][k] = Sn * Pk + C * Qk; }
						for (int32 k = 0; k < 4; ++k) { const double Kp = V[k][p], Kq = V[k][q]; V[k][p] = C * Kp - Sn * Kq; V[k][q] = Sn * Kp + C * Kq; }
					}
				}
			}
			int32 Best = 0;
			for (int32 i = 1; i < 4; ++i) { if (A[i][i] > A[Best][Best]) { Best = i; } }
			return FQuat(V[1][Best], V[2][Best], V[3][Best], V[0][Best]).GetNormalized();
		}

		double MaxResidual(const FQuat& R, const TArray<FVector>& From, const TArray<FVector>& To, int32* OutWorst = nullptr)
		{
			double Max = -1.0;
			for (int32 k = 0; k < From.Num(); ++k)
			{
				const double D = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(R.RotateVector(From[k]), To[k]), -1.0, 1.0)));
				if (D > Max)
				{
					Max = D;
					if (OutWorst) { *OutWorst = k; }
				}
			}
			return FMath::Max(Max, 0.0);
		}

		/** Q 의 Axis(정규화) 둘레 성분 — Q = 스윙 · 비틀림 */
		FQuat TwistAbout(const FQuat& Q, const FVector& Axis)
		{
			const FVector P = Axis * FVector::DotProduct(FVector(Q.X, Q.Y, Q.Z), Axis);
			FQuat Twist(P.X, P.Y, P.Z, Q.W);
			if (Twist.SizeSquared() < 1e-12)
			{
				return FQuat::Identity;
			}
			Twist.Normalize();
			return Twist;
		}

		/** 리타깃 포즈 해석 결과를 읽고 쓰는 곳 — 엔진 자동 포즈 생성기처럼 별도 프로세서(IKRetargeterPoseGenerator.cpp:22-28, 611-641) */
		struct FPoseEditor
		{
			const UIKRetargeterController* Controller = nullptr;
			FIKRetargetProcessor Processor;
			FName PoseName;

			const TArray<FTransform>& Global(ERetargetSourceOrTarget Side) const { return Processor.GetSkeleton(Side).RetargetPoses.GetGlobalRetargetPose(); }
			FVector Pos(ERetargetSourceOrTarget Side, int32 Bone) const { return Global(Side)[Bone].GetLocation(); }
			FName TargetName(int32 Bone) const { return Processor.GetSkeleton(Target).BoneNames[Bone]; }

			/** 전역 회전 W 를 대상 본에 — 새 로컬 = 부모⁻¹ · W · 현재 전역, 리타깃 포즈 델타 = 기준 로컬⁻¹ · 새 로컬 (IKRetargetProcessor.cpp:73) */
			void RotateGlobal(int32 Bone, const FQuat& W)
			{
				const FRetargetSkeleton& Skeleton = Processor.GetSkeleton(Target);
				const TArray<FTransform>& Pose = Global(Target);
				const int32 Parent = Skeleton.ParentIndices[Bone];
				const FQuat ParentRotation = Parent == INDEX_NONE ? FQuat::Identity : Pose[Parent].GetRotation();
				const FQuat NewLocal = ParentRotation.Inverse() * (W * Pose[Bone].GetRotation());
				const FQuat RefLocal = Skeleton.SkeletalMesh->GetRefSkeleton().GetRefBonePose()[Bone].GetRotation();
				Controller->SetRotationOffsetForRetargetPoseBone(Skeleton.BoneNames[Bone], (RefLocal.Inverse() * NewLocal).GetNormalized(), Target);
				Processor.UpdateRetargetPoseAtRuntime(PoseName, Target);
			}
		};

		bool IsAncestor(const FRetargetSkeleton& Skeleton, int32 Ancestor, int32 Bone)
		{
			for (int32 Walk = Skeleton.ParentIndices[Bone]; Walk != INDEX_NONE; Walk = Skeleton.ParentIndices[Walk])
			{
				if (Walk == Ancestor) { return true; }
			}
			return false;
		}

		/** 기준 포즈 전역 변환 — 리타깃 스켈레톤 본 번호 = 메시 기준 스켈레톤 번호 (RotateGlobal 과 같은 전제), 부모가 자식보다 앞 */
		TArray<FTransform> RefGlobalPose(const FRetargetSkeleton& Skeleton)
		{
			const TArray<FTransform>& Local = Skeleton.SkeletalMesh->GetRefSkeleton().GetRefBonePose();
			TArray<FTransform> Global;
			Global.SetNum(Local.Num());
			for (int32 Bone = 0; Bone < Local.Num(); ++Bone)
			{
				const int32 Parent = Skeleton.ParentIndices[Bone];
				Global[Bone] = Parent == INDEX_NONE ? Local[Bone] : Local[Bone] * Global[Parent];
			}
			return Global;
		}

		/** 대상 기준 포즈의 정중선 — 좌우축(단위) · 평면 위 한 점 · 축 체인 허용 거리 · 거울 짝 체인 */
		struct FMidline
		{
			FVector Lateral = FVector::ZeroVector;
			FVector Center = FVector::ZeroVector;
			double ToleranceCm = 0.0;
			TArray<TPair<FName, FName>> MirrorPairs;

			bool IsValid() const { return !Lateral.IsZero() && MirrorPairs.Num() > 0; }
			double Offset(const FVector& P) const { return FMath::Abs(FVector::DotProduct(P - Center, Lateral)); }
		};

		/** A 의 본마다 평면(Center, Axis)에 비춘 자리가 B 의 같은 번호 본과 겹치는가 */
		bool IsMirror(const TArray<int32>& A, const TArray<int32>& B, const TArray<FTransform>& Ref, const FVector& Center, const FVector& Axis, double Tolerance)
		{
			for (int32 i = 0; i < A.Num(); ++i)
			{
				const FVector P = Ref[A[i]].GetLocation() - Center;
				const FVector Reflected = P - 2.0 * FVector::DotProduct(P, Axis) * Axis;
				if (FVector::Dist(Reflected, Ref[B[i]].GetLocation() - Center) > Tolerance)
				{
					return false;
				}
			}
			return true;
		}

		/**
		 * 이름 없이 기하로 — 1) 뼈 2개 이상 · 같은 수인 매핑 체인 쌍 중 두 시작 관절의 수직이등분면에 비춰 본마다 겹치는 것(팔 · 다리 · 손가락)에서
		 * 좌우축(시작 거리 가중 평균) · 평면. 같은 쪽의 나란한 체인(손가락끼리)도 그 사이 평면에 비추면 겹치므로 축 방향이 가장 많이(시작 거리 가중)
		 * 모이는 무리만 쓴다. 2) 그 평면으로 뼈 1개 체인까지 다시 짝짓는다(쇄골 — 서로에게 잔차가 가장 작은 짝만). 축 체인 허용 거리 = 가장 안쪽 짝
		 * 시작의 반폭 × AxialOffsetRatio.
		 * 정면 맞춤은 전체를 도는 Yaw 라 정면 맞춤 전 기준 포즈로 판정해도 같다
		 */
		FMidline FindMidline(const TArray<FChainPair>& Pairs, const TArray<FTransform>& Ref)
		{
			struct FCandidate
			{
				FVector Axis;
				FVector Mid;
				double Weight;
			};
			TArray<FCandidate> Candidates;
			for (int32 a = 0; a < Pairs.Num(); ++a)
			{
				for (int32 b = a + 1; b < Pairs.Num(); ++b)
				{
					const TArray<int32>& A = Pairs[a].TargetBones->BoneIndices;
					const TArray<int32>& B = Pairs[b].TargetBones->BoneIndices;
					const FVector A0 = Ref[A[0]].GetLocation(), B0 = Ref[B[0]].GetLocation();
					const double Separation = FVector::Dist(A0, B0);
					if (A.Num() < 2 || A.Num() != B.Num() || Separation < MinSegmentCm)
					{
						continue;
					}
					const FVector Axis = (A0 - B0) / Separation;
					if (IsMirror(A, B, Ref, (A0 + B0) * 0.5, Axis, FMath::Max(MinSegmentCm, MirrorToleranceRatio * Separation)))
					{
						Candidates.Add({ Axis, (A0 + B0) * 0.5, Separation });
					}
				}
			}
			const double AgreeCos = FMath::Cos(FMath::DegreesToRadians(AxisAgreeDeg));
			auto Agrees = [AgreeCos](const FCandidate& X, const FCandidate& Y) { return FMath::Abs(FVector::DotProduct(X.Axis, Y.Axis)) >= AgreeCos; };
			int32 Best = INDEX_NONE;
			double BestScore = 0.0;
			for (int32 k = 0; k < Candidates.Num(); ++k)
			{
				double Score = 0.0;
				for (const FCandidate& Other : Candidates) { Score += Agrees(Candidates[k], Other) ? Other.Weight : 0.0; }
				if (Score > BestScore)
				{
					Best = k;
					BestScore = Score;
				}
			}
			FMidline Out;
			if (Best == INDEX_NONE)
			{
				return Out;
			}
			FVector AxisSum = FVector::ZeroVector, CenterSum = FVector::ZeroVector;
			for (const FCandidate& C : Candidates)
			{
				if (Agrees(Candidates[Best], C))
				{
					// 짝마다 어느 쪽이 A 인지 다르다 — 가장 큰 무리의 대표 방향에 부호를 맞춘다
					AxisSum += (FVector::DotProduct(Candidates[Best].Axis, C.Axis) < 0.0 ? -C.Axis : C.Axis) * C.Weight;
					CenterSum += C.Mid * C.Weight;
				}
			}
			Out.Lateral = AxisSum.GetSafeNormal();
			Out.Center = CenterSum / BestScore;
			// 2) 정중선 평면으로 다시 — 허용 오차 안이고 서로에게 잔차가 가장 작은 짝만(손가락 간격이 허용 오차보다 좁아 이웃 손가락도 든다)
			const int32 N = Pairs.Num();
			TArray<double> Residual;
			Residual.Init(-1.0, N * N);
			for (int32 a = 0; a < N; ++a)
			{
				for (int32 b = a + 1; b < N; ++b)
				{
					const TArray<int32>& A = Pairs[a].TargetBones->BoneIndices;
					const TArray<int32>& B = Pairs[b].TargetBones->BoneIndices;
					const double Separation = FVector::Dist(Ref[A[0]].GetLocation(), Ref[B[0]].GetLocation());
					const double Tolerance = FMath::Max(MinSegmentCm, MirrorToleranceRatio * Separation);
					if (A.Num() == B.Num() && Separation >= MinSegmentCm && IsMirror(A, B, Ref, Out.Center, Out.Lateral, Tolerance))
					{
						double Worst = 0.0;
						for (int32 i = 0; i < A.Num(); ++i)
						{
							const FVector P = Ref[A[i]].GetLocation() - Out.Center;
							Worst = FMath::Max(Worst, FVector::Dist(P - 2.0 * FVector::DotProduct(P, Out.Lateral) * Out.Lateral, Ref[B[i]].GetLocation() - Out.Center));
						}
						Residual[a * N + b] = Residual[b * N + a] = Worst;
					}
				}
			}
			auto BestMirrorOf = [&Residual, N](int32 a)
			{
				int32 Best = INDEX_NONE;
				for (int32 b = 0; b < N; ++b)
				{
					if (Residual[a * N + b] >= 0.0 && (Best == INDEX_NONE || Residual[a * N + b] < Residual[a * N + Best])) { Best = b; }
				}
				return Best;
			};
			double MinHalf = TNumericLimits<double>::Max();
			for (int32 a = 0; a < N; ++a)
			{
				const int32 b = BestMirrorOf(a);
				if (b != INDEX_NONE && a < b && BestMirrorOf(b) == a)
				{
					Out.MirrorPairs.Emplace(Pairs[a].TargetChain, Pairs[b].TargetChain);
					MinHalf = FMath::Min(MinHalf, Out.Offset(Ref[Pairs[a].TargetBones->BoneIndices[0]].GetLocation()));
				}
			}
			Out.ToleranceCm = Out.MirrorPairs.Num() > 0 ? AxialOffsetRatio * MinHalf : 0.0;
			return Out;
		}

		/** FK 가 대상 체인 i 번째 본과 짝짓는 소스 본 — OneToOne 은 같은 번호, 뼈 1개 대상은 param 1 이라 소스 끝, 그 밖은 param 이 가장 가까운 본 */
		int32 SourceBoneFor(const FChainPair& Pair, int32 i)
		{
			const FResolvedBoneChain& T = *Pair.TargetBones;
			const FResolvedBoneChain& S = *Pair.SourceBones;
			if (Pair.IsOneToOne())
			{
				return S.BoneIndices[i];
			}
			if (T.BoneIndices.Num() == 1 || T.Params.Num() != T.BoneIndices.Num() || S.Params.Num() != S.BoneIndices.Num())
			{
				return S.BoneIndices.Last();
			}
			int32 Best = 0;
			for (int32 j = 1; j < S.BoneIndices.Num(); ++j)
			{
				if (FMath::Abs(S.Params[j] - T.Params[i]) < FMath::Abs(S.Params[Best] - T.Params[i]))
				{
					Best = j;
				}
			}
			return S.BoneIndices[Best];
		}

		TSharedRef<FJsonObject> BoneDeg(const FName Bone, double DegValue)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("bone"), Bone.ToString());
			Obj->SetNumberField(TEXT("deg"), AnimMcpStats::Round(DegValue));
			return Obj;
		}

		TSharedPtr<FJsonValue> Skip(const FName Bone, const TCHAR* Reason)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("bone"), Bone.ToString());
			Obj->SetStringField(TEXT("reason"), Reason);
			return MakeShared<FJsonValueObject>(Obj);
		}
	}

	TSharedRef<FJsonObject> AlignPerBone(const UIKRetargeterController* Controller, const TArray<FName>& ExcludedBones, const FQuat& FacingRotation, FAnimMcpContext& Context)
	{
		TSharedRef<FJsonObject> Out = AnimMcpJson::MakeObject();
		Out->SetStringField(TEXT("mode"), TEXT("per_bone"));
		auto Fallback = [&Out, &Context](const FString& Why)
		{
			Context.AddDiagnostic(TEXT("warning"), TEXT("ALIGN_PER_BONE_SKIPPED"), Why + TEXT(" — the engine's auto-aligned pose is kept"));
			Out->SetStringField(TEXT("mode"), TEXT("engine"));
			Out->SetStringField(TEXT("skipped_reason"), Why);
			return Out;
		};

		FIKRetargetFKChainsOp* FKOp = Controller->GetFirstRetargetOpOfType<FIKRetargetFKChainsOp>();
		if (!FKOp)
		{
			return Fallback(TEXT("no FK Chains op"));
		}
		TUniquePtr<FPoseEditor> Editor = MakeUnique<FPoseEditor>();
		Editor->Controller = Controller;
		Editor->PoseName = Controller->GetCurrentRetargetPoseName(Target);
		FRetargetProfile Profile;
		Profile.FillProfileWithAssetSettings(Controller->GetAsset());
		Editor->Processor.Initialize(Controller->GetPreviewMesh(Source), Controller->GetPreviewMesh(Target), Controller->GetAsset(), Profile, /*bSuppressWarnings*/ true);
		if (!Editor->Processor.IsInitialized())
		{
			return Fallback(TEXT("the retarget processor did not initialize"));
		}
		const FRetargetSkeleton& TargetSkeleton = Editor->Processor.GetSkeleton(Target);

		// ---- 매핑된 FK 체인 쌍 (FK op 가 짝짓는 그대로) — 뿌리 → 끝 순서 ----
		TArray<FChainPair> Pairs;
		const FRetargeterBoneChains& Chains = Editor->Processor.GetBoneChains();
		for (FRetargetFKChainSettings& Settings : FKOp->Settings.ChainsToRetarget)
		{
			FChainPair Pair;
			Pair.TargetChain = Settings.TargetChainName;
			Pair.SourceChain = FKOp->Settings.ChainMapping.GetChainMappedTo(Settings.TargetChainName, Target);
			Pair.TargetBones = Chains.GetResolvedBoneChainByName(Pair.TargetChain, Target, FKOp->Settings.IKRigAsset);
			Pair.SourceBones = Pair.SourceChain.IsNone() ? nullptr : Chains.GetResolvedBoneChainByName(Pair.SourceChain, Source);
			Pair.Settings = &Settings;
			if (Settings.EnableFK && Pair.TargetBones && Pair.SourceBones && Pair.TargetBones->BoneIndices.Num() > 0 && Pair.SourceBones->BoneIndices.Num() > 0)
			{
				Pairs.Add(Pair);
			}
		}
		Pairs.Sort([](const FChainPair& A, const FChainPair& B)
		{
			const int32 IA = A.TargetBones->BoneIndices[0], IB = B.TargetBones->BoneIndices[0];
			return IA == IB ? A.TargetChain.LexicalLess(B.TargetChain) : IA < IB;
		});

		// ① 뼈 수가 같으면 1:1 회전 복사
		TArray<FString> OneToOne, Interpolated;
		for (const FChainPair& Pair : Pairs)
		{
			if (Pair.IsOneToOne())
			{
				Pair.Settings->RotationMode = EFKChainRotationMode::OneToOne;
				OneToOne.Add(Pair.TargetChain.ToString());
			}
			else if (Pair.TargetBones->BoneIndices.Num() >= 2)
			{
				Interpolated.Add(Pair.TargetChain.ToString());
			}
		}
		Out->SetArrayField(TEXT("one_to_one_chains"), AnimMcpGeneration::ToJsonArray(OneToOne));
		Out->SetArrayField(TEXT("interpolated_chains"), AnimMcpGeneration::ToJsonArray(Interpolated));

		TSet<int32> Excluded;
		for (const FName& Name : ExcludedBones)
		{
			const int32 Index = TargetSkeleton.FindBoneIndexByName(Name);
			if (Index != INDEX_NONE) { Excluded.Add(Index); }
		}
		TMap<int32, int32> PairOfBone;
		for (int32 p = 0; p < Pairs.Num(); ++p)
		{
			for (int32 Bone : Pairs[p].TargetBones->BoneIndices) { PairOfBone.Add(Bone, p); }
		}
		auto NearestMappedAncestor = [&TargetSkeleton, &PairOfBone](int32 Bone)
		{
			for (int32 Walk = TargetSkeleton.ParentIndices[Bone]; Walk != INDEX_NONE; Walk = TargetSkeleton.ParentIndices[Walk])
			{
				if (PairOfBone.Contains(Walk)) { return Walk; }
			}
			return int32(INDEX_NONE);
		};

		TArray<TSharedPtr<FJsonValue>> BonesOut, RelativeOut, EndsOut, NeutralOut, Skipped;
		const FRetargetSkeleton& SourceSkeleton = Editor->Processor.GetSkeleton(Source);
		const TArray<FTransform> TargetRef = RefGlobalPose(TargetSkeleton);
		const TArray<FTransform> SourceRef = RefGlobalPose(SourceSkeleton);
		// 중립 = 정면 맞춤만 반영한 대상 기준 포즈 전역 회전 (소스 짝 본의 리타깃 포즈가 기준과 다르면 그 차도 — 지금 파이프라인은 단위).
		// FK 는 (소스 현재 · 소스 리타깃 포즈⁻¹) · 대상 리타깃 포즈 라(FKChainsOp.cpp:343-350) 결과 = 소스가 자기 기준 포즈에서 움직인 만큼 · 대상 기준 포즈
		auto SetNeutral = [&](int32 Bone, int32 SourceBone)
		{
			if (Excluded.Contains(Bone))
			{
				Skipped.Add(Skip(Editor->TargetName(Bone), TEXT("EXCLUDED")));
				return;
			}
			const FQuat SourceDelta = SourceBone == INDEX_NONE ? FQuat::Identity
				: Editor->Global(Source)[SourceBone].GetRotation() * SourceRef[SourceBone].GetRotation().Inverse();
			const FQuat Neutral = SourceDelta * FacingRotation * TargetRef[Bone].GetRotation();
			const FQuat W = Neutral * Editor->Global(Target)[Bone].GetRotation().Inverse();
			if (Deg(W) > MinCorrectionDeg)
			{
				Editor->RotateGlobal(Bone, W);
				NeutralOut.Add(MakeShared<FJsonValueObject>(BoneDeg(Editor->TargetName(Bone), Deg(W))));
			}
		};

		// ⓪ 축(정중선) 체인 · 펠비스 — 소스 기준 포즈 기하를 복사하지 않고 대상 고유 곡선(척추 굽이 · 목 앞기울기)을 유지한다. 엔진 정렬은 척추를
		//    소스 곡선 접선에, 펠비스를 소스 척추 방향에(AlignPelvisBone), ②③ 은 목을 소스 기준 포즈 모양에 맞춰 그 모양이 모든 프레임에 붙었다
		//    (2026-10-25 실측: 목 윗마디 몸통선 대비 Vesper −14.2° · CMU +0.7° → 결과 p50 +5.5°, SOMA 클립 −41.5°). 팔 · 다리는 바뀐 몸통 위에서 ②③ 이 다시 맞춘다
		const int32 TargetPelvis = TargetSkeleton.FindBoneIndexByName(Editor->Processor.GetPelvisBone(Target, ERetargetOpsToSearch::AssetOps));
		const int32 SourcePelvis = SourceSkeleton.FindBoneIndexByName(Editor->Processor.GetPelvisBone(Source, ERetargetOpsToSearch::AssetOps));
		const FMidline Midline = FindMidline(Pairs, TargetRef);
		TSet<int32> Axial;
		TSharedRef<FJsonObject> AxialObj = AnimMcpJson::MakeObject();
		if (!Midline.IsValid())
		{
			AxialObj->SetStringField(TEXT("skipped_reason"), TEXT("NO_MIRROR_CHAINS"));
		}
		else
		{
			TSet<FName> Paired;
			TArray<TSharedPtr<FJsonValue>> PairsOut;
			for (const TPair<FName, FName>& Mirror : Midline.MirrorPairs)
			{
				Paired.Add(Mirror.Key);
				Paired.Add(Mirror.Value);
				PairsOut.Add(MakeShared<FJsonValueArray>(AnimMcpGeneration::ToJsonArray({ Mirror.Key.ToString(), Mirror.Value.ToString() })));
			}
			auto OnMidline = [&Midline, &TargetRef](int32 Bone) { return Midline.Offset(TargetRef[Bone].GetLocation()) <= Midline.ToleranceCm; };
			// 펠비스 · 그 조상(정면 맞춤을 담는 루트)을 품은 체인은 빼고 펠비스는 따로
			auto AtOrAbovePelvis = [&TargetSkeleton, TargetPelvis](int32 Bone) { return TargetPelvis != INDEX_NONE && (Bone == TargetPelvis || IsAncestor(TargetSkeleton, Bone, TargetPelvis)); };
			TArray<FString> AxialNames;
			TArray<TPair<int32, int32>> AxialBones;
			for (int32 p = 0; p < Pairs.Num(); ++p)
			{
				const TArray<int32>& T = Pairs[p].TargetBones->BoneIndices;
				if (Paired.Contains(Pairs[p].TargetChain) || Algo::AnyOf(T, AtOrAbovePelvis) || !Algo::AllOf(T, OnMidline))
				{
					continue;
				}
				Axial.Add(p);
				AxialNames.Add(Pairs[p].TargetChain.ToString());
				for (int32 i = 0; i < T.Num(); ++i) { AxialBones.Emplace(T[i], SourceBoneFor(Pairs[p], i)); }
			}
			const bool bPelvis = TargetPelvis != INDEX_NONE && OnMidline(TargetPelvis);
			AxialObj->SetArrayField(TEXT("lateral_axis"), { MakeShared<FJsonValueNumber>(AnimMcpStats::Round(Midline.Lateral.X)),
				MakeShared<FJsonValueNumber>(AnimMcpStats::Round(Midline.Lateral.Y)), MakeShared<FJsonValueNumber>(AnimMcpStats::Round(Midline.Lateral.Z)) });
			AxialObj->SetNumberField(TEXT("tolerance_cm"), AnimMcpStats::Round(Midline.ToleranceCm));
			AxialObj->SetArrayField(TEXT("mirror_pairs"), PairsOut);
			AxialObj->SetArrayField(TEXT("chains"), AnimMcpGeneration::ToJsonArray(AxialNames));
			if (bPelvis)
			{
				AxialObj->SetStringField(TEXT("pelvis"), Editor->TargetName(TargetPelvis).ToString());
			}
			else
			{
				AxialObj->SetField(TEXT("pelvis"), MakeShared<FJsonValueNull>());
			}
			// 뿌리 → 끝 (부모 보정이 자식 전역에 반영된 뒤 자식을 놓는다)
			if (bPelvis)
			{
				SetNeutral(TargetPelvis, SourcePelvis);
			}
			AxialBones.Sort([](const TPair<int32, int32>& A, const TPair<int32, int32>& B) { return A.Key < B.Key; });
			for (const TPair<int32, int32>& Bone : AxialBones)
			{
				SetNeutral(Bone.Key, Bone.Value);
			}
		}

		for (int32 p = 0; p < Pairs.Num(); ++p)
		{
			const FChainPair& Pair = Pairs[p];
			if (!Pair.IsOneToOne() || Axial.Contains(p))
			{
				continue;
			}
			const TArray<int32>& T = Pair.TargetBones->BoneIndices;
			const TArray<int32>& S = Pair.SourceBones->BoneIndices;

			// ②' 정중선 밖 끝 본(손)에 매달린 뼈 1개 체인(메타카팔) 아래 체인 — 소스 구간을 그 본의 어긋남 Q(소스 '본 → 체인 시작' →
			//    대상 같은 구간 최소 회전)만큼 돌린 방향에. 메타카팔 배치(손바닥)는 대상 체형 그대로, 관절 각(MCP · PIP)만 소스를 복사한다
			//    (2026-10-25 실측 SOMA → Vesper 오른손: 이 구간이 소스와 3.2~7.0° 일정하게 달라 MCP −17.5~−1.7°). 쇄골 → 팔은 부모가 정중선 위라 해당 없음.
			//    본 순서상 손 ③ 이 이미 끝난 리타깃 포즈에서 잰다
			FQuat Offset = FQuat::Identity;
			const int32 Single = NearestMappedAncestor(T[0]);
			const int32* SinglePair = Single == INDEX_NONE ? nullptr : PairOfBone.Find(Single);
			if (SinglePair && Pairs[*SinglePair].TargetBones->BoneIndices.Num() == 1 && !Axial.Contains(*SinglePair))
			{
				const int32 Owner = NearestMappedAncestor(Single);
				if (Owner != INDEX_NONE && Midline.IsValid() && Midline.Offset(TargetRef[Owner].GetLocation()) > Midline.ToleranceCm)
				{
					const FVector Dt = Editor->Pos(Target, T[0]) - Editor->Pos(Target, Single);
					const FVector Ds = Editor->Pos(Source, S[0]) - Editor->Pos(Source, SourceBoneFor(Pairs[*SinglePair], 0));
					if (Dt.Size() < MinSegmentCm || Ds.Size() < MinSegmentCm)
					{
						Skipped.Add(Skip(Editor->TargetName(Single), TEXT("ZERO_LENGTH")));
					}
					else
					{
						Offset = FQuat::FindBetweenNormals(Ds.GetSafeNormal(), Dt.GetSafeNormal());
						TSharedRef<FJsonObject> RelObj = AnimMcpJson::MakeObject();
						RelObj->SetStringField(TEXT("chain"), Pair.TargetChain.ToString());
						RelObj->SetStringField(TEXT("parent_bone"), Editor->TargetName(Single).ToString());
						RelObj->SetNumberField(TEXT("offset_deg"), AnimMcpStats::Round(Deg(Offset)));
						RelativeOut.Add(MakeShared<FJsonValueObject>(RelObj));
					}
				}
			}

			// ② 구간 i → i+1 을 소스 같은 번호 구간에 (②' 이면 Q 만큼 돌린 방향에)
			for (int32 i = 0; i + 1 < T.Num(); ++i)
			{
				if (Excluded.Contains(T[i]))
				{
					Skipped.Add(Skip(Editor->TargetName(T[i]), TEXT("EXCLUDED")));
					continue;
				}
				const FVector Dt = Editor->Pos(Target, T[i + 1]) - Editor->Pos(Target, T[i]);
				const FVector Ds = Editor->Pos(Source, S[i + 1]) - Editor->Pos(Source, S[i]);
				if (Dt.Size() < MinSegmentCm || Ds.Size() < MinSegmentCm)
				{
					Skipped.Add(Skip(Editor->TargetName(T[i]), TEXT("ZERO_LENGTH")));
					continue;
				}
				const FQuat W = FQuat::FindBetweenNormals(Dt.GetSafeNormal(), Offset.RotateVector(Ds.GetSafeNormal()));
				if (Deg(W) > MinCorrectionDeg)
				{
					Editor->RotateGlobal(T[i], W);
					BonesOut.Add(MakeShared<FJsonValueObject>(BoneDeg(Editor->TargetName(T[i]), Deg(W))));
				}
			}

			// ③ 체인 끝 — 바로 아래에서 시작하는 매핑 체인의 시작 관절
			const int32 End = T.Last(), SourceEnd = S.Last(), Parent = T[T.Num() - 2];
			if (Excluded.Contains(End))
			{
				Skipped.Add(Skip(Editor->TargetName(End), TEXT("EXCLUDED")));
				continue;
			}
			TArray<FVector> From, To;
			TArray<FString> Landmarks, Dropped;
			auto IsSingleWithChildren = [&Pairs, &TargetSkeleton](const FChainPair& Chain)
			{
				const int32 Start = Chain.TargetBones->BoneIndices[0];
				return Chain.TargetBones->BoneIndices.Num() == 1
					&& Algo::AnyOf(Pairs, [&TargetSkeleton, Start](const FChainPair& Other) { return IsAncestor(TargetSkeleton, Start, Other.TargetBones->BoneIndices[0]); });
			};
			// Owner 바로 아래에서 시작하는 매핑 체인의 시작 관절 — 자손이 있는 뼈 1개 체인(메타카팔)은 관절 자리가 해부적으로 다르니
			// 그 아래 체인(손가락 첫 마디)으로 내려간다. 방향은 끝 본 기준
			TFunction<void(int32)> Collect = [&](int32 Owner)
			{
				for (const FChainPair& Child : Pairs)
				{
					const int32 Start = Child.TargetBones->BoneIndices[0];
					if (&Child == &Pair || NearestMappedAncestor(Start) != Owner)
					{
						continue;
					}
					if (IsSingleWithChildren(Child))
					{
						Collect(Start);
						continue;
					}
					const FVector Dt = Editor->Pos(Target, Start) - Editor->Pos(Target, End);
					const FVector Ds = Editor->Pos(Source, Child.SourceBones->BoneIndices[0]) - Editor->Pos(Source, SourceEnd);
					if (Dt.Size() >= MinSegmentCm && Ds.Size() >= MinSegmentCm)
					{
						From.Add(Dt.GetSafeNormal());
						To.Add(Ds.GetSafeNormal());
						Landmarks.Add(Editor->TargetName(Start).ToString());
					}
				}
			};
			Collect(End);
			if (From.Num() == 0)
			{
				continue;
			}
			TSharedRef<FJsonObject> EndObj = AnimMcpJson::MakeObject();
			EndObj->SetStringField(TEXT("bone"), Editor->TargetName(End).ToString());
			EndObj->SetArrayField(TEXT("landmarks"), AnimMcpGeneration::ToJsonArray(Landmarks));
			auto Spread = [&From, &To]() { return From.Num() >= 2 && MaxPairAngleDeg(From) >= MinSpreadDeg && MaxPairAngleDeg(To) >= MinSpreadDeg; };
			bool bFrame = Spread();
			FQuat R = bFrame ? FitRotation(From, To) : FQuat::Identity;
			// 어긋난 랜드마크를 하나씩 빼고 다시 — 2개 이상 · 퍼짐이 남는 동안만
			int32 Worst = INDEX_NONE;
			while (bFrame && From.Num() > 2 && MaxResidual(R, From, To, &Worst) > MaxResidualDeg)
			{
				Dropped.Add(Landmarks[Worst]);
				From.RemoveAt(Worst);
				To.RemoveAt(Worst);
				Landmarks.RemoveAt(Worst);
				bFrame = Spread();
				if (bFrame)
				{
					R = FitRotation(From, To);
				}
			}
			if (!bFrame)
			{
				FVector MeanT = FVector::ZeroVector, MeanS = FVector::ZeroVector;
				for (int32 k = 0; k < From.Num(); ++k) { MeanT += From[k]; MeanS += To[k]; }
				R = FQuat::FindBetweenNormals(MeanT.GetSafeNormal(), MeanS.GetSafeNormal());
			}
			EndObj->SetArrayField(TEXT("dropped_landmarks"), AnimMcpGeneration::ToJsonArray(Dropped));
			EndObj->SetStringField(TEXT("fit"), bFrame ? TEXT("frame") : TEXT("direction"));
			EndObj->SetNumberField(TEXT("deg"), AnimMcpStats::Round(Deg(R)));
			EndObj->SetNumberField(TEXT("residual_max_deg"), AnimMcpStats::Round(MaxResidual(R, From, To)));

			FQuat Twist = FQuat::Identity;
			if (bFrame)
			{
				// 굴림은 체인 부모가 — 부모 → 끝 본 축 둘레로 돌려도 끝 본 위치는 그대로
				const FVector Axis = (Editor->Pos(Target, End) - Editor->Pos(Target, Parent)).GetSafeNormal();
				Twist = TwistAbout(R, Axis);
				if (Deg(Twist) > MinCorrectionDeg)
				{
					Editor->RotateGlobal(Parent, Twist);
				}
				EndObj->SetStringField(TEXT("twist_bone"), Editor->TargetName(Parent).ToString());
				EndObj->SetNumberField(TEXT("twist_deg"), AnimMcpStats::Round(Deg(Twist)));
			}
			const FQuat W = R * Twist.Inverse();
			if (Deg(W) > MinCorrectionDeg)
			{
				Editor->RotateGlobal(End, W);
			}
			EndsOut.Add(MakeShared<FJsonValueObject>(EndObj));
		}

		// ④ 축이 아닌 랜드마크 없는 말단 체인(뼈 1개 · 아래에서 시작하는 매핑 체인 없음) — 방향 근거가 없으니 ⓪ 과 같은 중립(양쪽 기준 포즈가
		//    해부적 중립이라는 가정). 조상 정렬을 따라 기운 채 두면 그 기울기가 모든 프레임에 붙는다(2026-10-24 실측 head: CMU → Vesper 얼굴 +6.8° 위,
		//    SOMA −3.7° 아래 — head 는 이제 ⓪ 이 맡는다). 조상(팔 · 다리 체인일 수 있다)이 다 끝난 뒤라 다시 끌려가지 않는다
		for (int32 p = 0; p < Pairs.Num(); ++p)
		{
			const int32 Bone = Pairs[p].TargetBones->BoneIndices[0];
			if (Axial.Contains(p) || Pairs[p].TargetBones->BoneIndices.Num() != 1
				|| Algo::AnyOf(Pairs, [&TargetSkeleton, Bone](const FChainPair& Other) { return IsAncestor(TargetSkeleton, Bone, Other.TargetBones->BoneIndices[0]); }))
			{
				continue;
			}
			SetNeutral(Bone, SourceBoneFor(Pairs[p], 0));
		}
		Out->SetArrayField(TEXT("bones"), BonesOut);
		Out->SetArrayField(TEXT("relative_chains"), RelativeOut);
		Out->SetArrayField(TEXT("chain_ends"), EndsOut);
		Out->SetObjectField(TEXT("axial"), AxialObj);
		Out->SetArrayField(TEXT("neutral_bones"), NeutralOut);
		Out->SetArrayField(TEXT("skipped"), Skipped);
		return Out;
	}
}
