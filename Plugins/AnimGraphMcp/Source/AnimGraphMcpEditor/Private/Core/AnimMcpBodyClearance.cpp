#include "AnimMcpBodyClearance.h"

#include "Animation/AnimData/IAnimationDataController.h"
#include "Animation/AnimData/IAnimationDataModel.h"
#include "AnimMcpAssetResolver.h"
#include "AnimMcpSkeletonGeometry.h"
#include "AnimMcpStats.h"
#include "AnimPose.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "Bridge/AnimMcpTypes.h"
#include "Engine/SkeletalMesh.h"
#include "HAL/PlatformTime.h"
#include "ReferenceSkeleton.h"
#include "Rendering/SkeletalMeshLODModel.h"
#include "Rendering/SkeletalMeshModel.h"
#include "Rig/IKRigDefinition.h"

namespace AnimMcpBodyClearance
{
	namespace
	{
		constexpr double DefaultContactCm = 1.0;
		constexpr double DefaultPenetrationCm = 2.0;
		/** 기본 거리값의 기준 펠비스 높이 — 사람 근사 (Vesper 105 · CMU 108 cm) */
		constexpr double ReferencePelvisCm = 100.0;
		/** 정점 줄이기 격자 (기준 포즈, cm × scale) — 한 칸에 한 정점 */
		constexpr double DecimateCellCm = 1.5;
		/** 팔 정점 = 팔 본 선분에서 이 거리 안 (cm × scale) — 아래팔 반지름 · 손 두께는 넘고, 손에 붙은 무기는 빠진다 */
		constexpr double ArmReachCm = 7.0;
		/**
		 * 반경 지도 — 몸통 축(엉덩 관절 중점 → 척추 끝) · 넓적다리 축(엉덩 → 무릎) 둘레를 (축 위치 t × 각도) 칸으로 나눠 칸마다 몸 정점의 최대 반경.
		 * 팔 점 깊이 = 그 칸 반경 − 축까지 거리, 밀어낼 방향 = 축에서 바깥. 가장 가까운 정점 법선 방식은 깊이 박힌 점(축 근처)에서 법선이 사방으로
		 * 흩어져 보정 방향이 엉키고 탐색 반경보다 깊은 점을 놓쳤다(2026-10-25 CMU: 보정 p50 20~30° · 30° 상한 273/398 프레임 · 보정 뒤 관통 18~21%)
		 */
		constexpr int32 AngleBins = 36;
		constexpr int32 TorsoBins = 40;
		constexpr double TorsoTMin = -0.25, TorsoTMax = 1.05;
		constexpr int32 ThighBins = 30;
		constexpr double ThighTMin = -0.15, ThighTMax = 1.0;
		/** 보정 — 몸 표면에서 띄울 기본 여유 (cm × scale) · 남은 깊이 허용치 (cm) · 한 걸음 상한 (°) · 반복 · 정규화(λ = 이 값 × tr/3 — 팔 축 비틀림 억제) */
		constexpr double DefaultMarginCm = 0.5;
		constexpr double ResolveToleranceCm = 0.05;
		constexpr double MaxStepDeg = 8.0;
		constexpr int32 MaxIterations = 8;
		constexpr double Regularization = 0.05;
		/** 시간 팽창 반경 (초) · 재검사 횟수 */
		constexpr double SmoothSeconds = 0.13;
		constexpr int32 VerifyPasses = 3;
		/** 양손 파지 근사 — 두 손목 거리 · 상대 위치 변화 (cm × scale) */
		constexpr double GripCm = 20.0;
		constexpr double GripMoveCm = 1.0;
		/** 몸 본 아래 매달린 가지가 이만큼(마디) 이어지면 secondary — 코트 자락 6 · 트위스트 · 가슴 1 */
		constexpr int32 SecondaryDepth = 3;
		constexpr int32 MaxInfluences = 8;

		// 체인 · 거울 짝 · 팔다리 판정은 공통부 (AnimMcpSkeletonGeometry — 손가락 체인 제안 · 검증과 같은 원천)
		using AnimMcpSkeletonGeometry::FTree;
		using AnimMcpSkeletonGeometry::MinSegmentCm;

		enum class EGroup : uint8
		{
			None,
			Core,
			Secondary,
			Arm0,
			Arm1,
		};
		constexpr int32 NumSlots = 4;
		int32 Slot(EGroup Group) { return static_cast<int32>(Group) - 1; }

		struct FArm
		{
			int32 Upper = INDEX_NONE;
			int32 Elbow = INDEX_NONE;
			int32 Wrist = INDEX_NONE;
		};

		struct FBodyMap
		{
			TArray<FArm> Arms;
			TArray<int32> CoreRoots;
			TArray<int32> SecondaryBranches;
			/** 메시 본마다 */
			TArray<EGroup> Groups;
			int32 Pelvis = INDEX_NONE;
			/** 반경 지도 축 — 척추 끝(두 위팔의 가장 가까운 공통 조상) · 넓적다리 · 무릎 (모르면 INDEX_NONE) */
			int32 SpineTop = INDEX_NONE;
			int32 Thighs[2] = { INDEX_NONE, INDEX_NONE };
			int32 Knees[2] = { INDEX_NONE, INDEX_NONE };
			FString ChainsFrom;
		};

		/** 줄인 스킨 정점 — 기준 포즈 컴포넌트 공간 위치, 큰 순 영향. Axis = 반경 지도 축(0 몸통, 1 · 2 넓적다리) */
		struct FPoint
		{
			FVector Position = FVector::ZeroVector;
			int32 Dominant = INDEX_NONE;
			int32 Axis = 0;
			int32 Num = 0;
			int32 Bones[MaxInfluences] = {};
			double Weights[MaxInfluences] = {};
		};

		struct FModel
		{
			FTree Tree;
			FBodyMap Map;
			TArray<FPoint> Points[NumSlots];
			/** 기본 거리값 배율 = 펠비스 기준 높이 / ReferencePelvisCm */
			double Scale = 1.0;
		};

		FName BoneName(const USkeletalMesh* Mesh, int32 Bone)
		{
			return Bone == INDEX_NONE ? NAME_None : Mesh->GetRefSkeleton().GetBoneName(Bone);
		}

		bool BuildMap(USkeletalMesh* Mesh, const FSpec& Spec, const FTree& Tree, FBodyMap& Out, FString& OutWhy)
		{
			const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
			const int32 N = Tree.Num();
			TArray<TArray<int32>> Chains;
			FName PelvisName;
			const bool bExplicitArms = Spec.UpperArms.Num() == 2;
			const bool bExplicitBody = Spec.BodyBones.Num() > 0;
			Out.ChainsFrom = bExplicitArms && bExplicitBody ? TEXT("explicit") : FString();
			if (!bExplicitArms || !bExplicitBody)
			{
				AnimMcpSkeletonGeometry::FChainSource Source = AnimMcpSkeletonGeometry::ResolveChains(Mesh, Spec.Rig, Ref, Tree);
				PelvisName = Source.Pelvis;
				Out.ChainsFrom = Source.From;
				for (AnimMcpSkeletonGeometry::FNamedChain& Chain : Source.Chains) { Chains.Add(MoveTemp(Chain.Bones)); }
			}

			// ---- 팔 · 다리 ----
			int32 ArmA = INDEX_NONE, ArmB = INDEX_NONE, LegA = INDEX_NONE, LegB = INDEX_NONE;
			AnimMcpSkeletonGeometry::PickLimbs(Chains, Tree, ArmA, ArmB, LegA, LegB);
			if (bExplicitArms)
			{
				for (const FName& Name : Spec.UpperArms)
				{
					FArm Arm;
					Arm.Upper = Ref.FindBoneIndex(Name);
					if (Arm.Upper == INDEX_NONE)
					{
						OutWhy = FString::Printf(TEXT("UPPER_ARM_NOT_FOUND: %s"), *Name.ToString());
						return false;
					}
					Arm.Elbow = Tree.LargestChild(Arm.Upper);
					Arm.Wrist = Arm.Elbow == INDEX_NONE ? INDEX_NONE : Tree.LargestChild(Arm.Elbow);
					if (Arm.Elbow == INDEX_NONE)
					{
						OutWhy = FString::Printf(TEXT("UPPER_ARM_HAS_NO_CHILD: %s"), *Name.ToString());
						return false;
					}
					Out.Arms.Add(Arm);
				}
			}
			else
			{
				if (ArmA == INDEX_NONE)
				{
					OutWhy = TEXT("NO_ARM_CHAINS");
					return false;
				}
				for (const int32 Index : { ArmA, ArmB })
				{
					const TArray<int32>& Chain = Chains[Index];
					FArm Arm;
					Arm.Upper = Chain[0];
					Arm.Elbow = Chain[1];
					Arm.Wrist = Chain.IsValidIndex(2) ? Chain[2] : Tree.LargestChild(Chain[1]);
					Out.Arms.Add(Arm);
				}
			}

			// ---- 몸 ----
			for (int32 k = 0; k < 2; ++k)
			{
				const int32 Index = k == 0 ? LegA : LegB;
				if (Index == INDEX_NONE) { continue; }
				Out.Thighs[k] = Chains[Index][0];
				Out.Knees[k] = Chains[Index].IsValidIndex(1) ? Chains[Index][1] : Tree.LargestChild(Chains[Index][0]);
			}
			Out.Groups.Init(EGroup::None, N);
			if (bExplicitBody)
			{
				for (const FName& Name : Spec.BodyBones)
				{
					const int32 Bone = Ref.FindBoneIndex(Name);
					if (Bone == INDEX_NONE)
					{
						OutWhy = FString::Printf(TEXT("BODY_BONE_NOT_FOUND: %s"), *Name.ToString());
						return false;
					}
					Out.CoreRoots.AddUnique(Bone);
					Out.Groups[Bone] = EGroup::Core;
					if (Out.SpineTop == INDEX_NONE || Tree.Pos(Bone).Z > Tree.Pos(Out.SpineTop).Z) { Out.SpineTop = Bone; }
				}
				Out.Pelvis = Ref.FindBoneIndex(PelvisName);
				if (Out.Pelvis == INDEX_NONE)
				{
					// 몸통 축 아래 끝 — 지정한 몸 본 중 가장 낮은 것
					for (const int32 Bone : Out.CoreRoots)
					{
						if (Out.Pelvis == INDEX_NONE || Tree.Pos(Bone).Z < Tree.Pos(Out.Pelvis).Z) { Out.Pelvis = Bone; }
					}
				}
			}
			else
			{
				Out.Pelvis = Ref.FindBoneIndex(PelvisName);
				if (Out.Pelvis == INDEX_NONE && LegA != INDEX_NONE)
				{
					// 펠비스를 모르면 두 넓적다리의 가장 가까운 공통 조상
					for (int32 Walk = Tree.Parents[Chains[LegA][0]]; Walk != INDEX_NONE && Out.Pelvis == INDEX_NONE; Walk = Tree.Parents[Walk])
					{
						if (Tree.IsAncestor(Walk, Chains[LegB][0])) { Out.Pelvis = Walk; }
					}
				}
				if (Out.Pelvis == INDEX_NONE)
				{
					OutWhy = TEXT("NO_PELVIS");
					return false;
				}
				// 척추 = 두 위팔의 공통 조상 중 펠비스 아래 (쇄골은 한쪽 것이라 빠진다)
				Out.CoreRoots.Add(Out.Pelvis);
				for (int32 Walk = Tree.Parents[Out.Arms[0].Upper]; Walk != INDEX_NONE && Walk != Out.Pelvis; Walk = Tree.Parents[Walk])
				{
					if (Tree.IsAncestor(Walk, Out.Arms[1].Upper) && Tree.IsAncestor(Out.Pelvis, Walk))
					{
						Out.CoreRoots.Add(Walk);
						if (Out.SpineTop == INDEX_NONE) { Out.SpineTop = Walk; }
					}
				}
				TSet<int32> Stops;
				for (const TArray<int32>& Chain : Chains)
				{
					for (const int32 Bone : Chain) { Stops.Add(Bone); }
				}
				for (const FArm& Arm : Out.Arms) { Stops.Add(Arm.Upper); }
				for (int32 k = 0; k < 2; ++k)
				{
					const int32 Index = k == 0 ? LegA : LegB;
					if (Index == INDEX_NONE) { continue; }
					Out.CoreRoots.AddUnique(Chains[Index][0]);
					if (Out.Knees[k] != INDEX_NONE) { Stops.Add(Out.Knees[k]); }
				}
				for (const int32 Root : Out.CoreRoots) { Stops.Remove(Root); }
				// 본마다 위로 — 몸 뿌리에 먼저 닿으면 몸, 다른 체인 본에 먼저 닿으면 아님. 몸 뿌리 바로 아래 가지가 SecondaryDepth 마디 이상이면 secondary
				TSet<int32> Branches;
				for (int32 Bone = 0; Bone < N; ++Bone)
				{
					int32 Below = INDEX_NONE;
					for (int32 Walk = Bone; Walk != INDEX_NONE; Below = Walk, Walk = Tree.Parents[Walk])
					{
						if (Out.CoreRoots.Contains(Walk))
						{
							const bool bSecondary = Below != INDEX_NONE && Tree.Height[Below] >= SecondaryDepth;
							Out.Groups[Bone] = bSecondary ? EGroup::Secondary : EGroup::Core;
							if (bSecondary) { Branches.Add(Below); }
							break;
						}
						if (Stops.Contains(Walk)) { break; }
					}
				}
				Out.SecondaryBranches = Branches.Array();
				Out.SecondaryBranches.Sort();
			}
			for (int32 a = 0; a < Out.Arms.Num(); ++a)
			{
				for (int32 Bone = 0; Bone < N; ++Bone)
				{
					if (Tree.IsSelfOrAncestor(Out.Arms[a].Elbow, Bone)) { Out.Groups[Bone] = a == 0 ? EGroup::Arm0 : EGroup::Arm1; }
				}
			}
			return true;
		}

		double SegmentDistance(const FVector& P, const FVector& A, const FVector& B)
		{
			const FVector AB = B - A;
			const double T = AB.SizeSquared() > UE_SMALL_NUMBER ? FMath::Clamp(FVector::DotProduct(P - A, AB) / AB.SizeSquared(), 0.0, 1.0) : 0.0;
			return FVector::Dist(P, A + AB * T);
		}

		bool BuildPoints(const USkeletalMesh* Mesh, const FTree& Tree, const FBodyMap& Map, double Cell, double ArmReach, TArray<FPoint> (&Out)[NumSlots], FString& OutWhy)
		{
			const FSkeletalMeshModel* Model = Mesh->GetImportedModel();
			if (!Model || Model->LODModels.Num() == 0)
			{
				OutWhy = TEXT("NO_IMPORTED_MODEL");
				return false;
			}
			// 팔 정점은 팔 본 선분(위팔 → 팔꿈치 → … 손가락)에서 ArmReach 안만 — 손에 붙은 무기 본(칼날 · 총열)은 팔이 아니다
			TArray<TPair<FVector, FVector>> ArmSegments[2];
			for (int32 a = 0; a < FMath::Min(2, Map.Arms.Num()); ++a)
			{
				const EGroup Group = a == 0 ? EGroup::Arm0 : EGroup::Arm1;
				for (int32 Bone = 0; Bone < Tree.Num(); ++Bone)
				{
					const int32 Parent = Tree.Parents[Bone];
					if (Map.Groups[Bone] == Group && Parent != INDEX_NONE && (Map.Groups[Parent] == Group || Parent == Map.Arms[a].Upper))
					{
						ArmSegments[a].Emplace(Tree.Pos(Parent), Tree.Pos(Bone));
					}
				}
			}
			const FSkeletalMeshLODModel& Lod = Model->LODModels[0];
			TSet<FIntVector> Seen[NumSlots];
			TArray<TPair<uint16, int32>, TInlineAllocator<MAX_TOTAL_INFLUENCES>> Influences;
			for (const FSkelMeshSection& Section : Lod.Sections)
			{
				if (Section.bDisabled)
				{
					continue;
				}
				for (const FSoftSkinVertex& Vertex : Section.SoftVertices)
				{
					Influences.Reset();
					for (int32 k = 0; k < MAX_TOTAL_INFLUENCES; ++k)
					{
						if (Vertex.InfluenceWeights[k] > 0 && Section.BoneMap.IsValidIndex(Vertex.InfluenceBones[k]))
						{
							Influences.Emplace(Vertex.InfluenceWeights[k], Section.BoneMap[Vertex.InfluenceBones[k]]);
						}
					}
					if (Influences.Num() == 0)
					{
						continue;
					}
					Influences.Sort([](const TPair<uint16, int32>& A, const TPair<uint16, int32>& B) { return A.Key > B.Key; });
					const int32 Dominant = Influences[0].Value;
					const EGroup Group = Map.Groups.IsValidIndex(Dominant) ? Map.Groups[Dominant] : EGroup::None;
					if (Group == EGroup::None)
					{
						continue;
					}
					const FVector Position(Vertex.Position);
					if (Group == EGroup::Arm0 || Group == EGroup::Arm1)
					{
						const TArray<TPair<FVector, FVector>>& Segments = ArmSegments[Group == EGroup::Arm0 ? 0 : 1];
						if (!Segments.ContainsByPredicate([&](const TPair<FVector, FVector>& S) { return SegmentDistance(Position, S.Key, S.Value) <= ArmReach; }))
						{
							continue;
						}
					}
					const FIntVector Key(FMath::FloorToInt32(Position.X / Cell), FMath::FloorToInt32(Position.Y / Cell), FMath::FloorToInt32(Position.Z / Cell));
					bool bAlready = false;
					Seen[Slot(Group)].Add(Key, &bAlready);
					if (bAlready)
					{
						continue;
					}
					FPoint Point;
					Point.Position = Position;
					Point.Dominant = Dominant;
					for (int32 k = 0; k < 2; ++k)
					{
						if (Map.Thighs[k] != INDEX_NONE && Tree.IsSelfOrAncestor(Map.Thighs[k], Dominant)) { Point.Axis = k + 1; }
					}
					Point.Num = FMath::Min(Influences.Num(), MaxInfluences);
					double Sum = 0.0;
					for (int32 k = 0; k < Point.Num; ++k)
					{
						Point.Bones[k] = Influences[k].Value;
						Point.Weights[k] = Influences[k].Key;
						Sum += Point.Weights[k];
					}
					for (int32 k = 0; k < Point.Num; ++k) { Point.Weights[k] /= Sum; }
					Out[Slot(Group)].Add(Point);
				}
			}
			return true;
		}

		bool BuildModel(USkeletalMesh* Mesh, const FSpec& Spec, FModel& Out, FString& OutWhy)
		{
			Out.Tree.Init(Mesh->GetRefSkeleton());
			if (!BuildMap(Mesh, Spec, Out.Tree, Out.Map, OutWhy))
			{
				return false;
			}
			if (Out.Map.Pelvis == INDEX_NONE || Out.Map.SpineTop == INDEX_NONE || Out.Map.Arms.Num() != 2)
			{
				OutWhy = TEXT("NO_TORSO_AXIS");
				return false;
			}
			if (Out.Map.Pelvis != INDEX_NONE)
			{
				Out.Scale = FMath::Clamp(Out.Tree.Pos(Out.Map.Pelvis).Z / ReferencePelvisCm, 0.25, 4.0);
			}
			if (!BuildPoints(Mesh, Out.Tree, Out.Map, DecimateCellCm * Out.Scale, ArmReachCm * Out.Scale, Out.Points, OutWhy))
			{
				return false;
			}
			if (Out.Points[Slot(EGroup::Core)].Num() == 0 || Out.Points[Slot(EGroup::Arm0)].Num() == 0 || Out.Points[Slot(EGroup::Arm1)].Num() == 0)
			{
				OutWhy = TEXT("NO_SKINNED_VERTICES");
				return false;
			}
			return true;
		}

		/** 프레임마다 메시 본 컴포넌트 공간 변환 — 메시 비율로 평가(validate_animation 샘플과 같은 루트 모션 포함) */
		bool SamplePoses(const UAnimSequence* Sequence, USkeletalMesh* Mesh, const FTree& Tree, TArray<TArray<FTransform>>& Out, double& OutFrameRate)
		{
			const int32 Frames = Sequence->GetNumberOfSampledKeys();
			const FFrameRate Rate = Sequence->GetDataModel()->GetFrameRate();
			OutFrameRate = Rate.AsDecimal();
			TArray<double> Times;
			for (int32 Frame = 0; Frame < Frames; ++Frame) { Times.Add(Rate.AsSeconds(Frame)); }
			FAnimPoseEvaluationOptions Options;
			Options.bExtractRootMotion = false;
			Options.bIncorporateRootMotionIntoPose = true;
			Options.bEvaluateCurves = false;
			Options.OptionalSkeletalMesh = Mesh;
			TArray<FAnimPose> Poses;
			UAnimPoseExtensions::GetAnimPoseAtTimeIntervals(Sequence, Times, Options, Poses);
			if (Frames == 0 || Poses.Num() != Frames || !Poses[0].IsValid())
			{
				return false;
			}
			const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
			TArray<FName> Names;
			UAnimPoseExtensions::GetBoneNames(Poses[0], Names);
			TArray<bool> InPose;
			InPose.SetNum(Tree.Num());
			for (int32 Bone = 0; Bone < Tree.Num(); ++Bone) { InPose[Bone] = Names.Contains(Ref.GetBoneName(Bone)); }
			Out.SetNum(Frames);
			for (int32 Frame = 0; Frame < Frames; ++Frame)
			{
				TArray<FTransform>& Row = Out[Frame];
				Row.SetNum(Tree.Num());
				for (int32 Bone = 0; Bone < Tree.Num(); ++Bone)
				{
					const int32 Parent = Tree.Parents[Bone];
					Row[Bone] = InPose[Bone] ? UAnimPoseExtensions::GetBonePose(Poses[Frame], Ref.GetBoneName(Bone), EAnimPoseSpaces::World)
						: Ref.GetRefBonePose()[Bone] * (Parent == INDEX_NONE ? FTransform::Identity : Row[Parent]);
				}
			}
			return true;
		}

		/** 스킨 변환 = 기준 전역⁻¹ · 현재 전역 (선형 블렌드 스키닝) */
		void SkinTransforms(const TArray<FTransform>& Pose, const TArray<FTransform>& RefInverse, TArray<FTransform>& Out)
		{
			Out.SetNum(Pose.Num());
			for (int32 Bone = 0; Bone < Pose.Num(); ++Bone) { Out[Bone] = RefInverse[Bone] * Pose[Bone]; }
		}

		void SkinPoints(const TArray<FPoint>& Points, const TArray<FTransform>& Skin, TArray<FVector>& OutPositions)
		{
			OutPositions.SetNum(Points.Num());
			for (int32 i = 0; i < Points.Num(); ++i)
			{
				const FPoint& P = Points[i];
				FVector Sum = FVector::ZeroVector;
				for (int32 k = 0; k < P.Num; ++k) { Sum += Skin[P.Bones[k]].TransformPosition(P.Position) * P.Weights[k]; }
				OutPositions[i] = Sum;
			}
		}

		/** 축 하나의 반경 지도 — [t 칸][각도 칸] 최대 반경과 그 정점 */
		struct FRadialAxis
		{
			bool bValid = false;
			FVector A = FVector::ZeroVector;
			FVector Dir = FVector::ZeroVector;
			double Length = 0.0;
			/** 각도 기준 — 축에 수직인 좌우 · 앞 */
			FVector X = FVector::ZeroVector;
			FVector Y = FVector::ZeroVector;
			double TMin = 0.0, TMax = 1.0;
			int32 TBins = 1;
			TArray<double> MaxRadius;
			TArray<int32> Who;

			void Init(const FVector& InA, const FVector& InB, const FVector& Lateral, double InTMin, double InTMax, int32 InTBins)
			{
				A = InA;
				Length = FVector::Dist(InA, InB);
				bValid = Length > MinSegmentCm;
				if (!bValid)
				{
					return;
				}
				Dir = (InB - InA) / Length;
				X = (Lateral - Dir * FVector::DotProduct(Lateral, Dir)).GetSafeNormal();
				if (X.IsNearlyZero()) { X = FVector::CrossProduct(Dir, FVector::ForwardVector).GetSafeNormal(); }
				Y = FVector::CrossProduct(Dir, X);
				TMin = InTMin;
				TMax = InTMax;
				TBins = InTBins;
				MaxRadius.Init(-1.0, TBins * AngleBins);
				Who.Init(INDEX_NONE, TBins * AngleBins);
			}

			/** 점의 (칸, 축 위 가장 가까운 점에서의 반경 벡터) — t 가 범위 밖이면 false */
			bool Locate(const FVector& P, int32& OutT, int32& OutAngle, FVector& OutRadial) const
			{
				if (!bValid)
				{
					return false;
				}
				const double Along = FVector::DotProduct(P - A, Dir);
				const double T = Along / Length;
				if (T < TMin || T > TMax)
				{
					return false;
				}
				OutRadial = P - (A + Dir * Along);
				OutT = FMath::Clamp(FMath::FloorToInt32((T - TMin) / (TMax - TMin) * TBins), 0, TBins - 1);
				const double Angle = FMath::Atan2(FVector::DotProduct(OutRadial, Y), FVector::DotProduct(OutRadial, X));
				OutAngle = FMath::Clamp(FMath::FloorToInt32((Angle + UE_DOUBLE_PI) / (2.0 * UE_DOUBLE_PI) * AngleBins), 0, AngleBins - 1);
				return true;
			}

			void Add(const FVector& P, int32 Index)
			{
				int32 T, Angle;
				FVector Radial;
				if (Locate(P, T, Angle, Radial))
				{
					const int32 Cell = T * AngleBins + Angle;
					if (Radial.Size() > MaxRadius[Cell])
					{
						MaxRadius[Cell] = Radial.Size();
						Who[Cell] = Index;
					}
				}
			}

			/** 칸 반경 — 빈 칸이면 이웃 3x3 의 최대(각도는 감아 돈다). 없으면 −1 */
			double Radius(int32 T, int32 Angle, int32& OutWho) const
			{
				const int32 Cell = T * AngleBins + Angle;
				OutWho = Who[Cell];
				if (MaxRadius[Cell] >= 0.0)
				{
					return MaxRadius[Cell];
				}
				double Best = -1.0;
				for (int32 dT = -1; dT <= 1; ++dT)
				{
					for (int32 dA = -1; dA <= 1; ++dA)
					{
						const int32 TT = T + dT;
						if (TT < 0 || TT >= TBins) { continue; }
						const int32 Neighbour = TT * AngleBins + (Angle + dA + AngleBins) % AngleBins;
						if (MaxRadius[Neighbour] > Best)
						{
							Best = MaxRadius[Neighbour];
							OutWho = Who[Neighbour];
						}
					}
				}
				return Best;
			}
		};

		/** 한 프레임의 몸 — 몸통 · 넓적다리 축의 반경 지도 (보정이 여러 번 다시 본다) */
		struct FFrameBody
		{
			FRadialAxis Axes[3];
			/** 지도에 넣은 몸 정점 (Who 가 가리킨다) */
			TArray<FVector> Positions;

			void Build(const FBodyMap& Map, const TArray<FTransform>& Pose, const TArray<FPoint>& Points, const TArray<FTransform>& Skin)
			{
				const FVector Lateral = Pose[Map.Arms[0].Upper].GetLocation() - Pose[Map.Arms[1].Upper].GetLocation();
				const bool bLegs = Map.Thighs[0] != INDEX_NONE && Map.Thighs[1] != INDEX_NONE;
				const FVector Bottom = bLegs ? (Pose[Map.Thighs[0]].GetLocation() + Pose[Map.Thighs[1]].GetLocation()) * 0.5 : Pose[Map.Pelvis].GetLocation();
				Axes[0].Init(Bottom, Pose[Map.SpineTop].GetLocation(), Lateral, TorsoTMin, TorsoTMax, TorsoBins);
				for (int32 k = 0; k < 2; ++k)
				{
					Axes[k + 1] = FRadialAxis();
					if (Map.Thighs[k] != INDEX_NONE && Map.Knees[k] != INDEX_NONE)
					{
						Axes[k + 1].Init(Pose[Map.Thighs[k]].GetLocation(), Pose[Map.Knees[k]].GetLocation(), Lateral, ThighTMin, ThighTMax, ThighBins);
					}
				}
				SkinPoints(Points, Skin, Positions);
				for (int32 i = 0; i < Points.Num(); ++i)
				{
					Axes[Axes[Points[i].Axis].bValid ? Points[i].Axis : 0].Add(Positions[i], i);
				}
			}

			/** 점의 깊이(+ 안쪽) · 밀어낼 방향 · 맞닿은 몸 정점 — 지도 밖이면 false. 여러 축에 걸리면 가장 깊은 것 */
			bool Depth(const FVector& P, double& OutDepth, FVector& OutPush, int32& OutWho) const
			{
				bool bFound = false;
				for (const FRadialAxis& Axis : Axes)
				{
					int32 T, Angle, Who;
					FVector Radial;
					if (!Axis.Locate(P, T, Angle, Radial))
					{
						continue;
					}
					const double Rho = Axis.Radius(T, Angle, Who);
					if (Rho < 0.0)
					{
						continue;
					}
					const double Depth = Rho - Radial.Size();
					if (!bFound || Depth > OutDepth)
					{
						bFound = true;
						OutDepth = Depth;
						OutPush = Radial.GetSafeNormal();
						OutWho = Who;
					}
				}
				return bFound;
			}
		};

		struct FHit
		{
			double Depth = 0.0;
			int32 ArmBone = INDEX_NONE;
			int32 BodyBone = INDEX_NONE;
			FVector ArmPoint = FVector::ZeroVector;
			FVector BodyPoint = FVector::ZeroVector;
		};

		/** 팔 정점마다 반경 지도 깊이 — 프레임의 최대 */
		FHit Probe(const TArray<FVector>& ArmPositions, const TArray<FPoint>& ArmPoints, const FFrameBody& Body, const TArray<FPoint>& BodyPoints)
		{
			FHit Hit;
			for (int32 i = 0; i < ArmPositions.Num(); ++i)
			{
				double Depth = 0.0;
				FVector Push;
				int32 Who = INDEX_NONE;
				if (Body.Depth(ArmPositions[i], Depth, Push, Who) && Depth > Hit.Depth)
				{
					Hit.Depth = Depth;
					Hit.ArmBone = ArmPoints[i].Dominant;
					Hit.BodyBone = Who == INDEX_NONE ? INDEX_NONE : BodyPoints[Who].Dominant;
					Hit.ArmPoint = ArmPositions[i];
					Hit.BodyPoint = Who == INDEX_NONE ? FVector::ZeroVector : Body.Positions[Who];
				}
			}
			return Hit;
		}

		struct FContactSet
		{
			/** r = 팔 점 − 피벗 */
			TArray<FVector> Offsets;
			/** d = (깊이 + margin) · 축에서 바깥 방향 */
			TArray<FVector> Displacements;
			/** 최대 (깊이 + margin) */
			double Worst = 0.0;
		};

		/** 컴포넌트 회전 R 로 어깨(피벗) 둘레를 돈 팔 점 중 몸 표면 + Margin 안쪽인 점 */
		void Contacts(const TArray<FVector>& ArmRest, const FVector& Pivot, const FQuat& R, const FFrameBody& Body, double Margin, FContactSet& Out)
		{
			Out.Offsets.Reset();
			Out.Displacements.Reset();
			Out.Worst = 0.0;
			for (const FVector& Rest : ArmRest)
			{
				const FVector A = Pivot + R.RotateVector(Rest - Pivot);
				double Depth = 0.0;
				FVector Push;
				int32 Who = INDEX_NONE;
				if (!Body.Depth(A, Depth, Push, Who) || Depth + Margin <= 0.0)
				{
					continue;
				}
				Out.Offsets.Add(A - Pivot);
				Out.Displacements.Add(Push * (Depth + Margin));
				Out.Worst = FMath::Max(Out.Worst, Depth + Margin);
			}
		}

		/** R 에서 시작해 남은 깊이가 허용치 안이 될 때까지 최소제곱 어깨 회전 — 결과 컴포넌트 회전 */
		FQuat SolveFrame(const TArray<FVector>& ArmRest, const FVector& Pivot, FQuat R, const FFrameBody& Body, double Margin)
		{
			FContactSet Set;
			for (int32 Iteration = 0; Iteration < MaxIterations; ++Iteration)
			{
				Contacts(ArmRest, Pivot, R, Body, Margin, Set);
				if (Set.Worst <= ResolveToleranceCm)
				{
					break;
				}
				const FVector Omega = SolveRotation(Set.Offsets, Set.Displacements, Regularization);
				const double Angle = FMath::Min(Omega.Size(), FMath::DegreesToRadians(MaxStepDeg));
				if (Angle < 1e-6)
				{
					break;
				}
				R = (FQuat(Omega.GetSafeNormal(), Angle) * R).GetNormalized();
			}
			return R;
		}

		/** 컴포넌트 회전 → 부모 공간 회전 벡터(°) · 그 역 — 보정은 몸통과 함께 움직이게 부모(쇄골) 공간에서 부드럽게 한다 */
		FVector ToParentVector(const FQuat& R, const FQuat& Parent)
		{
			FQuat Q = (Parent.Inverse() * R * Parent).GetNormalized();
			if (Q.W < 0.0) { Q = FQuat(-Q.X, -Q.Y, -Q.Z, -Q.W); }
			FVector Axis;
			double Angle = 0.0;
			Q.ToAxisAndAngle(Axis, Angle);
			return Angle < 1e-9 ? FVector::ZeroVector : Axis * FMath::RadiansToDegrees(Angle);
		}

		FQuat ParentQuat(const FVector& Vector)
		{
			const double Deg = Vector.Size();
			return Deg < 1e-9 ? FQuat::Identity : FQuat(Vector / Deg, FMath::DegreesToRadians(Deg));
		}

		FQuat FromParentVector(const FVector& Vector, const FQuat& Parent)
		{
			return (Parent * ParentQuat(Vector) * Parent.Inverse()).GetNormalized();
		}

		/** 메시 고르기 — 없으면 이유 */
		USkeletalMesh* PickMesh(const UAnimSequence* Sequence, const FSpec& Spec, FString& OutReason, FString& OutMessage)
		{
			USkeleton* Skeleton = Sequence->GetSkeleton();
			USkeletalMesh* Mesh = Spec.Mesh ? Spec.Mesh : (Skeleton ? Skeleton->GetPreviewMesh(/*bFindIfNotSet*/ true) : nullptr);
			if (!Mesh)
			{
				OutReason = TEXT("NO_MESH");
				OutMessage = TEXT("No target mesh — pass body_clearance.mesh (the skeleton has no preview mesh)");
				return nullptr;
			}
			if (Mesh->GetSkeleton() != Skeleton)
			{
				OutReason = TEXT("MESH_SKELETON_MISMATCH");
				OutMessage = FString::Printf(TEXT("Mesh skeleton '%s' is not the animation's '%s'"), *GetPathNameSafe(Mesh->GetSkeleton()), *GetPathNameSafe(Skeleton));
				return nullptr;
			}
			return Mesh;
		}

		TSharedPtr<FJsonValue> Issue(const TCHAR* Level, const TCHAR* Code, const FString& Message)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("level"), Level);
			Obj->SetStringField(TEXT("code"), Code);
			Obj->SetStringField(TEXT("message"), Message);
			return MakeShared<FJsonValueObject>(Obj);
		}

		TArray<TSharedPtr<FJsonValue>> Names(const USkeletalMesh* Mesh, const TArray<int32>& Bones)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			for (const int32 Bone : Bones) { Out.Add(MakeShared<FJsonValueString>(BoneName(Mesh, Bone).ToString())); }
			return Out;
		}

		/** 팔 하나의 프레임별 깊이 요약 */
		TSharedRef<FJsonObject> ArmJson(const USkeletalMesh* Mesh, const FArm& Arm, int32 NumPoints, const TArray<FHit>& Hits, double FrameRate, double ContactCm, double PenetrationCm)
		{
			TArray<double> Depths;
			int32 Worst = 0, OverContact = 0, OverPenetration = 0;
			TMap<int32, int32> BodyHits;
			for (int32 f = 0; f < Hits.Num(); ++f)
			{
				Depths.Add(Hits[f].Depth);
				if (Hits[f].Depth > Hits[Worst].Depth) { Worst = f; }
				if (Hits[f].Depth > ContactCm)
				{
					++OverContact;
					++BodyHits.FindOrAdd(Hits[f].BodyBone);
				}
				if (Hits[f].Depth > PenetrationCm) { ++OverPenetration; }
			}
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("upper_arm"), BoneName(Mesh, Arm.Upper).ToString());
			Obj->SetStringField(TEXT("elbow"), BoneName(Mesh, Arm.Elbow).ToString());
			Obj->SetNumberField(TEXT("points"), NumPoints);
			const double Frames = FMath::Max(1, Hits.Num());
			Obj->SetNumberField(TEXT("frames_over_contact_pct"), AnimMcpStats::Round(100.0 * OverContact / Frames, 1));
			Obj->SetNumberField(TEXT("frames_over_penetration_pct"), AnimMcpStats::Round(100.0 * OverPenetration / Frames, 1));
			Obj->SetNumberField(TEXT("depth_p50"), AnimMcpStats::Round(AnimMcpStats::Percentile(Depths, 50.0), 2));
			Obj->SetNumberField(TEXT("depth_p95"), AnimMcpStats::Round(AnimMcpStats::Percentile(Depths, 95.0), 2));
			Obj->SetNumberField(TEXT("depth_max"), AnimMcpStats::Round(Hits.Num() ? Hits[Worst].Depth : 0.0, 2));
			TSharedRef<FJsonObject> WorstObj = AnimMcpJson::MakeObject();
			WorstObj->SetNumberField(TEXT("frame"), Worst);
			WorstObj->SetNumberField(TEXT("time"), AnimMcpStats::Round(FrameRate > 0.0 ? Worst / FrameRate : 0.0, 4));
			WorstObj->SetField(TEXT("arm_bone"), AnimMcpJson::StringOrNull(Hits.Num() && Hits[Worst].ArmBone != INDEX_NONE ? BoneName(Mesh, Hits[Worst].ArmBone).ToString() : FString()));
			WorstObj->SetField(TEXT("body_bone"), AnimMcpJson::StringOrNull(Hits.Num() && Hits[Worst].BodyBone != INDEX_NONE ? BoneName(Mesh, Hits[Worst].BodyBone).ToString() : FString()));
			if (Hits.Num() && Hits[Worst].Depth > 0.0)
			{
				auto Vec = [](const FVector& V) { return TArray<TSharedPtr<FJsonValue>>{ MakeShared<FJsonValueNumber>(AnimMcpStats::Round(V.X, 2)),
					MakeShared<FJsonValueNumber>(AnimMcpStats::Round(V.Y, 2)), MakeShared<FJsonValueNumber>(AnimMcpStats::Round(V.Z, 2)) }; };
				WorstObj->SetArrayField(TEXT("arm_point_cm"), Vec(Hits[Worst].ArmPoint));
				WorstObj->SetArrayField(TEXT("body_point_cm"), Vec(Hits[Worst].BodyPoint));
			}
			Obj->SetObjectField(TEXT("worst"), WorstObj);
			BodyHits.ValueSort([](int32 A, int32 B) { return A > B; });
			TArray<TSharedPtr<FJsonValue>> HitsOut;
			for (const TPair<int32, int32>& Pair : BodyHits)
			{
				if (HitsOut.Num() == 5) { break; }
				TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
				Item->SetStringField(TEXT("bone"), BoneName(Mesh, Pair.Key).ToString());
				Item->SetNumberField(TEXT("frames"), Pair.Value);
				HitsOut.Add(MakeShared<FJsonValueObject>(Item));
			}
			Obj->SetArrayField(TEXT("body_bones_hit"), HitsOut);
			return Obj;
		}
	}

	bool ParseSpec(const TSharedPtr<FJsonValue>& Value, const TCHAR* Field, const TArray<FString>& ExtraKeys, FSpec& Out, bool& bOutEnabled, FAnimMcpError& OutError)
	{
		bOutEnabled = false;
		if (!Value.IsValid() || Value->Type == EJson::Null)
		{
			return true;
		}
		auto Bad = [&OutError, Field](const FString& Key, const FString& Message)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), Field);
			if (!Key.IsEmpty()) { Details->SetStringField(TEXT("key"), Key); }
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
			return false;
		};
		if (Value->Type == EJson::Boolean)
		{
			bOutEnabled = Value->AsBool();
			return true;
		}
		const TSharedPtr<FJsonObject>* Object = nullptr;
		if (!Value->TryGetObject(Object))
		{
			return Bad(FString(), FString::Printf(TEXT("%s must be true or an object"), Field));
		}
		bOutEnabled = true;
		auto Strings = [&Bad, Field](const FString& Key, const TSharedPtr<FJsonValue>& V, TArray<FName>& OutNames)
		{
			const TArray<TSharedPtr<FJsonValue>>* Array = nullptr;
			if (!V->TryGetArray(Array))
			{
				return Bad(Key, FString::Printf(TEXT("%s.%s must be an array of bone names"), Field, *Key));
			}
			for (const TSharedPtr<FJsonValue>& Item : *Array)
			{
				if (!Item.IsValid() || Item->Type != EJson::String || Item->AsString().IsEmpty())
				{
					return Bad(Key, FString::Printf(TEXT("%s.%s must be an array of bone names"), Field, *Key));
				}
				OutNames.Add(FName(*Item->AsString()));
			}
			return true;
		};
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*Object)->Values)
		{
			const FString& Key = Pair.Key;
			const TSharedPtr<FJsonValue>& V = Pair.Value;
			if (ExtraKeys.Contains(Key))
			{
				continue;
			}
			if (Key == TEXT("mesh") || Key == TEXT("ik_rig"))
			{
				if (!V.IsValid() || V->Type != EJson::String || V->AsString().IsEmpty())
				{
					return Bad(Key, FString::Printf(TEXT("%s.%s must be an asset path"), Field, *Key));
				}
				UObject* Asset = AnimMcpAssetResolver::LoadAssetOfClass(V->AsString(), Key == TEXT("mesh") ? USkeletalMesh::StaticClass() : UIKRigDefinition::StaticClass(), OutError);
				if (!Asset)
				{
					return false;
				}
				if (Key == TEXT("mesh")) { Out.Mesh = Cast<USkeletalMesh>(Asset); }
				else { Out.Rig = Cast<UIKRigDefinition>(Asset); }
			}
			else if (Key == TEXT("upper_arms"))
			{
				if (!Strings(Key, V, Out.UpperArms)) { return false; }
			}
			else if (Key == TEXT("body_bones"))
			{
				if (!Strings(Key, V, Out.BodyBones)) { return false; }
			}
			else if (Key == TEXT("include_secondary"))
			{
				if (!V.IsValid() || V->Type != EJson::Boolean) { return Bad(Key, FString::Printf(TEXT("%s.include_secondary must be a boolean"), Field)); }
				Out.bIncludeSecondary = V->AsBool();
			}
			else if (Key == TEXT("contact_cm") || Key == TEXT("penetration_cm"))
			{
				if (!V.IsValid() || V->Type != EJson::Number || V->AsNumber() <= 0.0) { return Bad(Key, FString::Printf(TEXT("%s.%s must be a positive number (cm)"), Field, *Key)); }
				(Key == TEXT("contact_cm") ? Out.ContactCm : Out.PenetrationCm) = V->AsNumber();
			}
			else
			{
				TArray<FString> Allowed = { TEXT("mesh"), TEXT("ik_rig"), TEXT("upper_arms"), TEXT("body_bones"), TEXT("include_secondary"), TEXT("contact_cm"), TEXT("penetration_cm") };
				Allowed.Append(ExtraKeys);
				return Bad(Key, FString::Printf(TEXT("%s.%s is unknown (%s)"), Field, *Key, *FString::Join(Allowed, TEXT(", "))));
			}
		}
		if (Out.UpperArms.Num() != 0 && Out.UpperArms.Num() != 2)
		{
			return Bad(TEXT("upper_arms"), FString::Printf(TEXT("%s.upper_arms needs exactly two bones (left and right upper arm)"), Field));
		}
		return true;
	}

	TSharedRef<FJsonObject> Measure(const UAnimSequence* Sequence, const FSpec& Spec, bool& bOutWarning)
	{
		bOutWarning = false;
		const double StartSeconds = FPlatformTime::Seconds();
		TSharedRef<FJsonObject> Out = AnimMcpJson::MakeObject();
		TArray<TSharedPtr<FJsonValue>> Issues;
		auto Skip = [&Out, &Issues](const FString& Reason, const FString& Message)
		{
			Issues.Add(Issue(TEXT("info"), TEXT("BODY_CLEARANCE_SKIPPED"), Message));
			Out->SetStringField(TEXT("skipped_reason"), Reason);
			Out->SetArrayField(TEXT("issues"), Issues);
			return Out;
		};
		FString Reason, Message;
		USkeletalMesh* Mesh = PickMesh(Sequence, Spec, Reason, Message);
		if (!Mesh)
		{
			return Skip(Reason, Message);
		}
		Out->SetStringField(TEXT("mesh"), Mesh->GetPathName());
		FModel Model;
		FString Why;
		if (!BuildModel(Mesh, Spec, Model, Why))
		{
			return Skip(Why, FString::Printf(TEXT("Could not find the arms / body on '%s' (%s) — pass body_clearance.upper_arms + body_bones, or ik_rig"), *Mesh->GetName(), *Why));
		}
		TArray<TArray<FTransform>> Poses;
		double FrameRate = 0.0;
		if (!SamplePoses(Sequence, Mesh, Model.Tree, Poses, FrameRate))
		{
			return Skip(TEXT("SAMPLE_FAILED"), TEXT("UAnimPoseExtensions could not evaluate the sequence on the mesh"));
		}
		const double Scale = Model.Scale;
		const double ContactCm = Spec.ContactCm.Get(DefaultContactCm * Scale);
		const double PenetrationCm = Spec.PenetrationCm.Get(DefaultPenetrationCm * Scale);

		TArray<FTransform> RefInverse;
		for (const FTransform& X : Model.Tree.Global) { RefInverse.Add(X.Inverse()); }
		const FBodyMap& Map = Model.Map;
		const TArray<FPoint>& Core = Model.Points[Slot(EGroup::Core)];
		const TArray<FPoint>& Secondary = Model.Points[Slot(EGroup::Secondary)];
		const bool bSecondary = Spec.bIncludeSecondary && Secondary.Num() > 0;
		TArray<TArray<FHit>> Hits, SecondaryHits;
		Hits.SetNum(Map.Arms.Num());
		SecondaryHits.SetNum(Map.Arms.Num());
		TArray<FTransform> Skin;
		TArray<FVector> ArmPos;
		FFrameBody Body, SecondaryBody;
		for (int32 Frame = 0; Frame < Poses.Num(); ++Frame)
		{
			SkinTransforms(Poses[Frame], RefInverse, Skin);
			Body.Build(Map, Poses[Frame], Core, Skin);
			if (bSecondary)
			{
				SecondaryBody.Build(Map, Poses[Frame], Secondary, Skin);
			}
			for (int32 a = 0; a < Map.Arms.Num(); ++a)
			{
				const TArray<FPoint>& Arm = Model.Points[Slot(a == 0 ? EGroup::Arm0 : EGroup::Arm1)];
				SkinPoints(Arm, Skin, ArmPos);
				Hits[a].Add(Probe(ArmPos, Arm, Body, Core));
				if (bSecondary) { SecondaryHits[a].Add(Probe(ArmPos, Arm, SecondaryBody, Secondary)); }
			}
		}

		Out->SetStringField(TEXT("chains_from"), Map.ChainsFrom);
		Out->SetNumberField(TEXT("scale"), AnimMcpStats::Round(Scale));
		Out->SetNumberField(TEXT("contact_cm"), AnimMcpStats::Round(ContactCm, 2));
		Out->SetNumberField(TEXT("penetration_cm"), AnimMcpStats::Round(PenetrationCm, 2));
		Out->SetNumberField(TEXT("frames"), Poses.Num());
		TArray<TSharedPtr<FJsonValue>> ArmsOut, SecondaryOut;
		for (int32 a = 0; a < Map.Arms.Num(); ++a)
		{
			const int32 NumPoints = Model.Points[Slot(a == 0 ? EGroup::Arm0 : EGroup::Arm1)].Num();
			TSharedRef<FJsonObject> ArmObj = ArmJson(Mesh, Map.Arms[a], NumPoints, Hits[a], FrameRate, ContactCm, PenetrationCm);
			ArmsOut.Add(MakeShared<FJsonValueObject>(ArmObj));
			const double DepthMax = ArmObj->GetNumberField(TEXT("depth_max"));
			if (DepthMax > PenetrationCm)
			{
				const TSharedPtr<FJsonObject> Worst = ArmObj->GetObjectField(TEXT("worst"));
				bOutWarning = true;
				Issues.Add(Issue(TEXT("warning"), TEXT("BODY_PENETRATION"), FString::Printf(TEXT("%s side: the hand/forearm (%s) goes %.1f cm into '%s' at frame %d (%.2fs); %.1f%% of frames are over %.1f cm"),
					*ArmObj->GetStringField(TEXT("upper_arm")), *Worst->GetStringField(TEXT("arm_bone")), DepthMax, *Worst->GetStringField(TEXT("body_bone")),
					static_cast<int32>(Worst->GetNumberField(TEXT("frame"))), Worst->GetNumberField(TEXT("time")), ArmObj->GetNumberField(TEXT("frames_over_penetration_pct")), PenetrationCm)));
			}
			if (bSecondary)
			{
				SecondaryOut.Add(MakeShared<FJsonValueObject>(ArmJson(Mesh, Map.Arms[a], NumPoints, SecondaryHits[a], FrameRate, ContactCm, PenetrationCm)));
			}
		}
		Out->SetArrayField(TEXT("arms"), ArmsOut);
		TSharedRef<FJsonObject> BodyObj = AnimMcpJson::MakeObject();
		BodyObj->SetArrayField(TEXT("core_roots"), Names(Mesh, Map.CoreRoots));
		BodyObj->SetNumberField(TEXT("core_points"), Core.Num());
		BodyObj->SetArrayField(TEXT("secondary_branches"), Names(Mesh, Map.SecondaryBranches));
		BodyObj->SetNumberField(TEXT("secondary_points"), Secondary.Num());
		BodyObj->SetField(TEXT("pelvis"), AnimMcpJson::StringOrNull(Map.Pelvis == INDEX_NONE ? FString() : BoneName(Mesh, Map.Pelvis).ToString()));
		BodyObj->SetStringField(TEXT("torso_axis"), FString::Printf(TEXT("%s → %s"), Map.Thighs[0] != INDEX_NONE && Map.Thighs[1] != INDEX_NONE ? TEXT("hip joints midpoint") : *BoneName(Mesh, Map.Pelvis).ToString(),
			*BoneName(Mesh, Map.SpineTop).ToString()));
		BodyObj->SetArrayField(TEXT("thigh_axes"), Names(Mesh, { Map.Thighs[0], Map.Thighs[1] }));
		Out->SetObjectField(TEXT("body"), BodyObj);
		if (bSecondary)
		{
			Out->SetArrayField(TEXT("secondary_arms"), SecondaryOut);
		}
		Out->SetArrayField(TEXT("issues"), Issues);
		Out->SetNumberField(TEXT("seconds"), AnimMcpStats::Round(FPlatformTime::Seconds() - StartSeconds));
		return Out;
	}

	bool ParseMode(const TSharedPtr<FJsonValue>& Value, const TCHAR* Field, EMode& OutMode, FSpec& OutSpec, FResolveOptions& OutOptions, FAnimMcpError& OutError)
	{
		OutMode = EMode::Off;
		if (!Value.IsValid() || Value->Type == EJson::Null)
		{
			return true;
		}
		auto Bad = [&OutError, Field](const FString& Key, const FString& Message)
		{
			TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
			Details->SetStringField(TEXT("field"), Field);
			if (!Key.IsEmpty()) { Details->SetStringField(TEXT("key"), Key); }
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
			return false;
		};
		auto ModeOf = [](const FString& Text, EMode& Out)
		{
			if (Text == TEXT("off")) { Out = EMode::Off; return true; }
			if (Text == TEXT("measure")) { Out = EMode::Measure; return true; }
			if (Text == TEXT("resolve")) { Out = EMode::Resolve; return true; }
			return false;
		};
		if (Value->Type == EJson::String)
		{
			return ModeOf(Value->AsString(), OutMode) ? true : Bad(FString(), FString::Printf(TEXT("%s must be off, measure, resolve or an object (got '%s')"), Field, *Value->AsString()));
		}
		const TSharedPtr<FJsonObject>* Object = nullptr;
		if (!Value->TryGetObject(Object))
		{
			return Bad(FString(), FString::Printf(TEXT("%s must be off, measure, resolve or an object"), Field));
		}
		bool bEnabled = false;
		if (!ParseSpec(Value, Field, { TEXT("mode"), TEXT("margin_cm"), TEXT("max_deg") }, OutSpec, bEnabled, OutError))
		{
			return false;
		}
		OutMode = EMode::Resolve;
		if (const TSharedPtr<FJsonValue> Mode = (*Object)->TryGetField(TEXT("mode")))
		{
			if (Mode->Type != EJson::String || !ModeOf(Mode->AsString(), OutMode))
			{
				return Bad(TEXT("mode"), FString::Printf(TEXT("%s.mode must be off, measure or resolve"), Field));
			}
		}
		if (const TSharedPtr<FJsonValue> Margin = (*Object)->TryGetField(TEXT("margin_cm")))
		{
			if (Margin->Type != EJson::Number || Margin->AsNumber() < 0.0)
			{
				return Bad(TEXT("margin_cm"), FString::Printf(TEXT("%s.margin_cm must be a number >= 0 (cm)"), Field));
			}
			OutOptions.MarginCm = Margin->AsNumber();
		}
		if (const TSharedPtr<FJsonValue> MaxDeg = (*Object)->TryGetField(TEXT("max_deg")))
		{
			if (MaxDeg->Type != EJson::Number || MaxDeg->AsNumber() <= 0.0 || MaxDeg->AsNumber() > 90.0)
			{
				return Bad(TEXT("max_deg"), FString::Printf(TEXT("%s.max_deg must be in (0, 90]"), Field));
			}
			OutOptions.MaxDeg = MaxDeg->AsNumber();
		}
		return true;
	}

	TSharedRef<FJsonObject> Resolve(UAnimSequence* Sequence, const FSpec& Spec, const FResolveOptions& Options, bool& bOutWarning)
	{
		bOutWarning = false;
		const double StartSeconds = FPlatformTime::Seconds();
		TSharedRef<FJsonObject> Out = AnimMcpJson::MakeObject();
		TArray<TSharedPtr<FJsonValue>> Issues;
		auto Skip = [&Out, &Issues](const FString& Reason, const FString& Message)
		{
			Issues.Add(Issue(TEXT("info"), TEXT("BODY_CLEARANCE_SKIPPED"), Message));
			Out->SetStringField(TEXT("skipped_reason"), Reason);
			Out->SetArrayField(TEXT("issues"), Issues);
			return Out;
		};
		FString Reason, Message;
		USkeletalMesh* Mesh = PickMesh(Sequence, Spec, Reason, Message);
		if (!Mesh)
		{
			return Skip(Reason, Message);
		}
		Out->SetStringField(TEXT("mesh"), Mesh->GetPathName());
		FModel Model;
		FString Why;
		if (!BuildModel(Mesh, Spec, Model, Why))
		{
			return Skip(Why, FString::Printf(TEXT("Could not find the arms / body on '%s' (%s) — nothing corrected"), *Mesh->GetName(), *Why));
		}
		TArray<TArray<FTransform>> Poses;
		double FrameRate = 0.0;
		if (!SamplePoses(Sequence, Mesh, Model.Tree, Poses, FrameRate))
		{
			return Skip(TEXT("SAMPLE_FAILED"), TEXT("UAnimPoseExtensions could not evaluate the sequence on the mesh — nothing corrected"));
		}
		bool bBeforeWarning = false;
		Out->SetObjectField(TEXT("before"), Measure(Sequence, Spec, bBeforeWarning));

		const double Scale = Model.Scale;
		const double Margin = Options.MarginCm.Get(DefaultMarginCm * Scale);
		const FBodyMap& Map = Model.Map;
		const int32 Frames = Poses.Num();
		const int32 NumArms = FMath::Min(2, Map.Arms.Num());
		TArray<FTransform> RefInverse;
		for (const FTransform& X : Model.Tree.Global) { RefInverse.Add(X.Inverse()); }

		// ---- 프레임마다 몸 · 팔(보정 전) · 피벗 · 부모 회전 · 손목 ----
		TArray<FFrameBody> Bodies;
		Bodies.SetNum(Frames);
		TArray<TArray<FVector>> ArmRest[2];
		TArray<FVector> Pivots[2], Wrists[2];
		TArray<FQuat> Parents[2];
		TArray<FTransform> Skin;
		for (int32 Frame = 0; Frame < Frames; ++Frame)
		{
			SkinTransforms(Poses[Frame], RefInverse, Skin);
			Bodies[Frame].Build(Map, Poses[Frame], Model.Points[Slot(EGroup::Core)], Skin);
			for (int32 a = 0; a < NumArms; ++a)
			{
				const FArm& Arm = Map.Arms[a];
				SkinPoints(Model.Points[Slot(a == 0 ? EGroup::Arm0 : EGroup::Arm1)], Skin, ArmRest[a].AddDefaulted_GetRef());
				Pivots[a].Add(Poses[Frame][Arm.Upper].GetLocation());
				const int32 Parent = Model.Tree.Parents[Arm.Upper];
				Parents[a].Add(Parent == INDEX_NONE ? FQuat::Identity : Poses[Frame][Parent].GetRotation());
				Wrists[a].Add(Poses[Frame][Arm.Wrist != INDEX_NONE ? Arm.Wrist : Arm.Elbow].GetLocation());
			}
		}

		// ---- 팔마다: 프레임별 최소 회전 → 부드럽게 → 재검사 ----
		const int32 SmoothRadius = FMath::Max(1, FMath::RoundToInt32(SmoothSeconds * FrameRate));
		TArray<FVector> Corrections[2];
		TArray<TSharedPtr<FJsonValue>> ArmsOut;
		FContactSet Set;
		for (int32 a = 0; a < NumArms; ++a)
		{
			TArray<FVector> Raw;
			Raw.Init(FVector::ZeroVector, Frames);
			for (int32 Frame = 0; Frame < Frames; ++Frame)
			{
				Contacts(ArmRest[a][Frame], Pivots[a][Frame], FQuat::Identity, Bodies[Frame], Margin, Set);
				if (Set.Worst > ResolveToleranceCm)
				{
					Raw[Frame] = ToParentVector(SolveFrame(ArmRest[a][Frame], Pivots[a][Frame], FQuat::Identity, Bodies[Frame], Margin), Parents[a][Frame]);
				}
			}
			TArray<FVector> Smoothed = SmoothRotationVectors(Raw, SmoothRadius);
			for (int32 Pass = 0; Pass < VerifyPasses; ++Pass)
			{
				bool bChanged = false;
				for (int32 Frame = 0; Frame < Frames; ++Frame)
				{
					const FQuat R = FromParentVector(Smoothed[Frame], Parents[a][Frame]);
					Contacts(ArmRest[a][Frame], Pivots[a][Frame], R, Bodies[Frame], Margin, Set);
					if (Set.Worst > 2.0 * ResolveToleranceCm)
					{
						Raw[Frame] = ToParentVector(SolveFrame(ArmRest[a][Frame], Pivots[a][Frame], R, Bodies[Frame], Margin), Parents[a][Frame]);
						bChanged = true;
					}
				}
				if (!bChanged)
				{
					break;
				}
				Smoothed = SmoothRotationVectors(Raw, SmoothRadius);
			}
			int32 Clamped = 0;
			TArray<double> Degrees, CorrectedDegrees, Speeds;
			for (int32 Frame = 0; Frame < Frames; ++Frame)
			{
				const double Deg = Smoothed[Frame].Size();
				if (Deg > Options.MaxDeg)
				{
					Smoothed[Frame] *= Options.MaxDeg / Deg;
					++Clamped;
				}
				Degrees.Add(Smoothed[Frame].Size());
				if (Degrees.Last() > 0.1) { CorrectedDegrees.Add(Degrees.Last()); }
				if (Frame > 0) { Speeds.Add((Smoothed[Frame] - Smoothed[Frame - 1]).Size() * FrameRate); }
			}
			Corrections[a] = Smoothed;
			TSharedRef<FJsonObject> ArmObj = AnimMcpJson::MakeObject();
			ArmObj->SetStringField(TEXT("upper_arm"), BoneName(Mesh, Map.Arms[a].Upper).ToString());
			ArmObj->SetNumberField(TEXT("corrected_frames_pct"), AnimMcpStats::Round(100.0 * CorrectedDegrees.Num() / FMath::Max(1, Frames), 1));
			ArmObj->SetNumberField(TEXT("deg_p50"), AnimMcpStats::Round(AnimMcpStats::Percentile(CorrectedDegrees, 50.0), 2));
			ArmObj->SetNumberField(TEXT("deg_p95"), AnimMcpStats::Round(AnimMcpStats::Percentile(Degrees, 95.0), 2));
			ArmObj->SetNumberField(TEXT("deg_max"), AnimMcpStats::Round(Degrees.Num() ? FMath::Max(Degrees) : 0.0, 2));
			ArmObj->SetNumberField(TEXT("deg_per_s_max"), AnimMcpStats::Round(Speeds.Num() ? FMath::Max(Speeds) : 0.0, 1));
			ArmObj->SetNumberField(TEXT("clamped_frames"), Clamped);
			ArmsOut.Add(MakeShared<FJsonValueObject>(ArmObj));
			if (Clamped > 0)
			{
				bOutWarning = true;
				Issues.Add(Issue(TEXT("warning"), TEXT("BODY_CLEARANCE_LIMIT"), FString::Printf(TEXT("%s: %d frame(s) needed more than max_deg %.0f° — clamped, the arm may still go into the body there"),
					*BoneName(Mesh, Map.Arms[a].Upper).ToString(), Clamped, Options.MaxDeg)));
			}
		}

		// ---- 양손 파지 근사: 가까운 두 손목의 상대 위치가 바뀌는 프레임 ----
		int32 GripChanged = 0;
		if (NumArms == 2)
		{
			for (int32 Frame = 0; Frame < Frames; ++Frame)
			{
				const FVector Before = Wrists[0][Frame] - Wrists[1][Frame];
				if (Before.Size() > GripCm * Scale)
				{
					continue;
				}
				FVector After[2];
				for (int32 a = 0; a < 2; ++a)
				{
					After[a] = Pivots[a][Frame] + FromParentVector(Corrections[a][Frame], Parents[a][Frame]).RotateVector(Wrists[a][Frame] - Pivots[a][Frame]);
				}
				if (FVector::Dist(After[0] - After[1], Before) > GripMoveCm * Scale) { ++GripChanged; }
			}
			if (GripChanged > 0)
			{
				bOutWarning = true;
				Issues.Add(Issue(TEXT("warning"), TEXT("CLEARANCE_GRIP_CHANGED"), FString::Printf(TEXT("%d frame(s) have the wrists within %.0f cm and the correction moves them %.1f+ cm relative to each other — a two-handed grip there is not kept (check visually)"),
					GripChanged, GripCm * Scale, GripMoveCm * Scale)));
			}
		}

		// ---- 쓰기: 위팔 로컬 회전 = 부모 공간 보정 · 원래 로컬 (자식은 따라온다) ----
		bool bAny = false;
		for (int32 a = 0; a < NumArms; ++a)
		{
			bAny |= Corrections[a].ContainsByPredicate([](const FVector& V) { return V.Size() > 1e-4; });
		}
		if (bAny)
		{
			const IAnimationDataModel* DataModel = Sequence->GetDataModel();
			const int32 Keys = DataModel->GetNumberOfKeys();
			IAnimationDataController& Controller = Sequence->GetController();
			constexpr bool bShouldTransact = false;
			Controller.OpenBracket(NSLOCTEXT("AnimGraphMcp", "BodyClearance", "AnimGraphMcp: body clearance"), bShouldTransact);
			for (int32 a = 0; a < NumArms; ++a)
			{
				const FName Name = BoneName(Mesh, Map.Arms[a].Upper);
				TArray<FTransform> Track;
				if (DataModel->IsValidBoneTrackName(Name))
				{
					DataModel->GetBoneTrackTransforms(Name, Track);
				}
				else
				{
					Controller.AddBoneCurve(Name, bShouldTransact);
				}
				const FTransform RefLocal = Mesh->GetRefSkeleton().GetRefBonePose()[Map.Arms[a].Upper];
				while (Track.Num() < Keys) { Track.Add(Track.Num() > 0 ? Track.Last() : RefLocal); }
				TArray<FVector3f> Positions;
				TArray<FQuat4f> Rotations;
				TArray<FVector3f> Scales;
				for (int32 Key = 0; Key < Keys; ++Key)
				{
					const FVector& Correction = Corrections[a][FMath::Min(Key, Frames - 1)];
					Positions.Add(FVector3f(Track[Key].GetLocation()));
					Rotations.Add(FQuat4f((ParentQuat(Correction) * Track[Key].GetRotation()).GetNormalized()));
					Scales.Add(FVector3f(Track[Key].GetScale3D()));
				}
				Controller.SetBoneTrackKeys(Name, Positions, Rotations, Scales, bShouldTransact);
			}
			Controller.CloseBracket(bShouldTransact);
			Sequence->PostEditChange();
			Sequence->MarkPackageDirty();
		}

		bool bAfterWarning = false;
		TSharedRef<FJsonObject> After = Measure(Sequence, Spec, bAfterWarning);
		Out->SetObjectField(TEXT("after"), After);
		if (bAfterWarning)
		{
			bOutWarning = true;
			Issues.Add(Issue(TEXT("warning"), TEXT("BODY_PENETRATION_REMAINS"), TEXT("Penetration is still over penetration_cm after the correction — see after.issues")));
		}
		Out->SetNumberField(TEXT("scale"), AnimMcpStats::Round(Scale));
		Out->SetNumberField(TEXT("margin_cm"), AnimMcpStats::Round(Margin, 2));
		Out->SetNumberField(TEXT("max_deg"), Options.MaxDeg);
		Out->SetNumberField(TEXT("smooth_frames"), SmoothRadius);
		Out->SetArrayField(TEXT("arms"), ArmsOut);
		Out->SetNumberField(TEXT("grip_changed_frames"), GripChanged);
		Out->SetBoolField(TEXT("modified"), bAny);
		Out->SetArrayField(TEXT("issues"), Issues);
		Out->SetNumberField(TEXT("seconds"), AnimMcpStats::Round(FPlatformTime::Seconds() - StartSeconds));
		return Out;
	}

	FVector SolveRotation(const TArray<FVector>& Offsets, const TArray<FVector>& Displacements, double InRegularization)
	{
		double A[3][3] = {};
		FVector B = FVector::ZeroVector;
		for (int32 i = 0; i < Offsets.Num(); ++i)
		{
			const FVector& R = Offsets[i];
			const double RR = R.SizeSquared();
			for (int32 Row = 0; Row < 3; ++Row)
			{
				for (int32 Col = 0; Col < 3; ++Col)
				{
					A[Row][Col] += (Row == Col ? RR : 0.0) - R[Row] * R[Col];
				}
			}
			B += FVector::CrossProduct(R, Displacements[i]);
		}
		const double Lambda = InRegularization * (A[0][0] + A[1][1] + A[2][2]) / 3.0 + 1e-9;
		for (int32 k = 0; k < 3; ++k) { A[k][k] += Lambda; }
		// 3x3 역행렬 (대칭 양의 정부호)
		const double C00 = A[1][1] * A[2][2] - A[1][2] * A[2][1];
		const double C01 = A[1][2] * A[2][0] - A[1][0] * A[2][2];
		const double C02 = A[1][0] * A[2][1] - A[1][1] * A[2][0];
		const double Det = A[0][0] * C00 + A[0][1] * C01 + A[0][2] * C02;
		if (FMath::Abs(Det) < 1e-12)
		{
			return FVector::ZeroVector;
		}
		const double C10 = A[0][2] * A[2][1] - A[0][1] * A[2][2];
		const double C11 = A[0][0] * A[2][2] - A[0][2] * A[2][0];
		const double C12 = A[0][1] * A[2][0] - A[0][0] * A[2][1];
		const double C20 = A[0][1] * A[1][2] - A[0][2] * A[1][1];
		const double C21 = A[0][2] * A[1][0] - A[0][0] * A[1][2];
		const double C22 = A[0][0] * A[1][1] - A[0][1] * A[1][0];
		// 역 = 여인수 행렬의 전치 / Det
		return FVector(C00 * B.X + C10 * B.Y + C20 * B.Z, C01 * B.X + C11 * B.Y + C21 * B.Z, C02 * B.X + C12 * B.Y + C22 * B.Z) / Det;
	}

	TArray<FVector> SmoothRotationVectors(const TArray<FVector>& Vectors, int32 Radius)
	{
		const int32 N = Vectors.Num();
		if (N == 0 || Radius <= 0)
		{
			return Vectors;
		}
		TArray<FVector> Dilated;
		Dilated.SetNum(N);
		for (int32 i = 0; i < N; ++i)
		{
			int32 Best = i;
			for (int32 j = FMath::Max(0, i - Radius); j <= FMath::Min(N - 1, i + Radius); ++j)
			{
				if (Vectors[j].SizeSquared() > Vectors[Best].SizeSquared()) { Best = j; }
			}
			Dilated[i] = Vectors[Best];
		}
		const double Sigma = FMath::Max(0.5, Radius / 2.0);
		TArray<double> Weights;
		double Sum = 0.0;
		for (int32 u = -Radius; u <= Radius; ++u)
		{
			Weights.Add(FMath::Exp(-0.5 * FMath::Square(u / Sigma)));
			Sum += Weights.Last();
		}
		TArray<FVector> Out;
		Out.SetNum(N);
		for (int32 i = 0; i < N; ++i)
		{
			FVector Acc = FVector::ZeroVector;
			for (int32 u = -Radius; u <= Radius; ++u)
			{
				Acc += Dilated[FMath::Clamp(i + u, 0, N - 1)] * Weights[u + Radius];
			}
			Out[i] = Acc / Sum;
		}
		return Out;
	}
}
