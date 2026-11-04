#include "AnimMcpSkeletonGeometry.h"

#include "Algo/Reverse.h"
#include "Algo/Sort.h"
#include "AnimMcpSkeletonInspector.h"
#include "Engine/SkeletalMesh.h"
#include "ReferenceSkeleton.h"
#include "Rig/IKRigDefinition.h"
#include "RigEditor/IKRigAutoCharacterizer.h"

namespace AnimMcpSkeletonGeometry
{
	namespace
	{
		/** 발 영역 = 바닥 + 키 × 이 비율 (anim_gen bvh.FOOT_REGION) */
		constexpr double FootRegion = 0.15;
		/** p5 ~ p95 폭보다 이만큼(배) 더 떨어진 외톨이 본은 바닥 · 꼭대기에서 뺀다 — SB 의 FX 본 z −2217 cm (bvh.OUTLIER_MARGIN) */
		constexpr double OutlierMargin = 1.0;
	}

	void FTree::Init(const FReferenceSkeleton& Ref)
	{
		const int32 N = Ref.GetNum();
		const TArray<FTransform>& Local = Ref.GetRefBonePose();
		Parents.SetNum(N);
		Global.SetNum(N);
		Descendants.Init(0, N);
		Height.Init(1, N);
		for (int32 Bone = 0; Bone < N; ++Bone)
		{
			Parents[Bone] = Ref.GetParentIndex(Bone);
			Global[Bone] = Parents[Bone] == INDEX_NONE ? Local[Bone] : Local[Bone] * Global[Parents[Bone]];
		}
		for (int32 Bone = N - 1; Bone >= 0; --Bone)
		{
			if (Parents[Bone] != INDEX_NONE)
			{
				Descendants[Parents[Bone]] += Descendants[Bone] + 1;
				Height[Parents[Bone]] = FMath::Max(Height[Parents[Bone]], Height[Bone] + 1);
			}
		}
	}

	bool FTree::IsAncestor(int32 Ancestor, int32 Bone) const
	{
		for (int32 Walk = Parents[Bone]; Walk != INDEX_NONE; Walk = Parents[Walk])
		{
			if (Walk == Ancestor) { return true; }
		}
		return false;
	}

	int32 FTree::LargestChild(int32 Bone) const
	{
		int32 Best = INDEX_NONE;
		for (int32 Child = Bone + 1; Child < Num(); ++Child)
		{
			if (Parents[Child] == Bone && (Best == INDEX_NONE || Descendants[Child] > Descendants[Best])) { Best = Child; }
		}
		return Best;
	}

	TArray<int32> FTree::Children(int32 Bone) const
	{
		TArray<int32> Out;
		for (int32 Child = Bone + 1; Child < Num(); ++Child)
		{
			if (Parents[Child] == Bone) { Out.Add(Child); }
		}
		return Out;
	}

	TArray<int32> ChainBones(const FReferenceSkeleton& Ref, const FTree& Tree, FName Start, FName End)
	{
		TArray<int32> Out;
		const int32 StartBone = Ref.FindBoneIndex(Start);
		const int32 EndBone = Ref.FindBoneIndex(End);
		if (StartBone == INDEX_NONE || EndBone == INDEX_NONE)
		{
			return Out;
		}
		for (int32 Walk = EndBone; Walk != INDEX_NONE; Walk = Tree.Parents[Walk])
		{
			Out.Add(Walk);
			if (Walk == StartBone)
			{
				Algo::Reverse(Out);
				return Out;
			}
		}
		Out.Reset();
		return Out;
	}

	bool IsMirror(const TArray<int32>& A, const TArray<int32>& B, const FTree& Tree)
	{
		if (A.Num() < 2 || A.Num() != B.Num())
		{
			return false;
		}
		const FVector A0 = Tree.Pos(A[0]), B0 = Tree.Pos(B[0]);
		const double Separation = FVector::Dist(A0, B0);
		if (Separation < MinSegmentCm)
		{
			return false;
		}
		const FVector Axis = (A0 - B0) / Separation;
		if (FMath::Abs(Axis.Z) > 0.5)
		{
			return false;
		}
		const FVector Center = (A0 + B0) * 0.5;
		const double Tolerance = FMath::Max(MinSegmentCm, MirrorToleranceRatio * Separation);
		for (int32 i = 0; i < A.Num(); ++i)
		{
			const FVector P = Tree.Pos(A[i]) - Center;
			if (FVector::Dist(P - 2.0 * FVector::DotProduct(P, Axis) * Axis, Tree.Pos(B[i]) - Center) > Tolerance)
			{
				return false;
			}
		}
		return true;
	}

	void PickLimbs(const TArray<TArray<int32>>& Chains, const FTree& Tree, int32& OutArmA, int32& OutArmB, int32& OutLegA, int32& OutLegB)
	{
		OutArmA = OutArmB = OutLegA = OutLegB = INDEX_NONE;
		TArray<TPair<int32, int32>> Pairs;
		for (int32 a = 0; a < Chains.Num(); ++a)
		{
			for (int32 b = a + 1; b < Chains.Num(); ++b)
			{
				if (IsMirror(Chains[a], Chains[b], Tree)) { Pairs.Emplace(a, b); }
			}
		}
		auto Under = [&Chains, &Tree](const TPair<int32, int32>& P, const TPair<int32, int32>& Other)
		{
			for (const int32 Index : { P.Key, P.Value })
			{
				for (const int32 OtherIndex : { Other.Key, Other.Value })
				{
					if (Tree.IsAncestor(Chains[OtherIndex].Last(), Chains[Index][0]) || Tree.IsAncestor(Chains[OtherIndex][0], Chains[Index][0]))
					{
						return true;
					}
				}
			}
			return false;
		};
		TArray<TPair<int32, int32>> Roots;
		for (const TPair<int32, int32>& P : Pairs)
		{
			if (!Pairs.ContainsByPredicate([&](const TPair<int32, int32>& Other) { return &Other != &P && Under(P, Other); })) { Roots.Add(P); }
		}
		int32 Leg = INDEX_NONE;
		for (int32 k = 0; k < Roots.Num(); ++k)
		{
			const double EndZ = FMath::Min(Tree.Pos(Chains[Roots[k].Key].Last()).Z, Tree.Pos(Chains[Roots[k].Value].Last()).Z);
			if (Leg == INDEX_NONE || EndZ < FMath::Min(Tree.Pos(Chains[Roots[Leg].Key].Last()).Z, Tree.Pos(Chains[Roots[Leg].Value].Last()).Z)) { Leg = k; }
		}
		// 다리 후보가 팔보다 높은 곳에서 끝나는 경우(상체 리그)를 가리려고 다리는 짝이 둘 이상일 때만
		if (Roots.Num() < 2) { Leg = INDEX_NONE; }
		const double LegStartZ = Leg == INDEX_NONE ? -TNumericLimits<double>::Max() : Tree.Pos(Chains[Roots[Leg].Key][0]).Z;
		int32 Arm = INDEX_NONE;
		for (int32 k = 0; k < Roots.Num(); ++k)
		{
			if (k == Leg || Tree.Pos(Chains[Roots[k].Key][0]).Z <= LegStartZ) { continue; }
			const int32 Score = Tree.Descendants[Chains[Roots[k].Key][0]] + Tree.Descendants[Chains[Roots[k].Value][0]];
			if (Arm == INDEX_NONE || Score > Tree.Descendants[Chains[Roots[Arm].Key][0]] + Tree.Descendants[Chains[Roots[Arm].Value][0]]) { Arm = k; }
		}
		if (Arm != INDEX_NONE) { OutArmA = Roots[Arm].Key; OutArmB = Roots[Arm].Value; }
		if (Leg != INDEX_NONE) { OutLegA = Roots[Leg].Key; OutLegB = Roots[Leg].Value; }
	}

	FChainSource ResolveChains(USkeletalMesh* Mesh, const UIKRigDefinition* Rig, const FReferenceSkeleton& Ref, const FTree& Tree)
	{
		FChainSource Out;
		TArray<FBoneChain> RigChains;
		if (Rig)
		{
			RigChains = Rig->GetRetargetChains();
			Out.Pelvis = Rig->GetPelvis();
			Out.From = TEXT("ik_rig");
		}
		else if (Mesh)
		{
			FAutoCharacterizeResults Results;
			AnimMcpSkeletonInspector::Characterize(Mesh, Results);
			RigChains = Results.AutoRetargetDefinition.RetargetDefinition.BoneChains;
			Out.Pelvis = Results.AutoRetargetDefinition.RetargetDefinition.RootBone;
			Out.From = Results.bUsedTemplate ? TEXT("template") : TEXT("characterize");
		}
		else
		{
			Out.From = TEXT("none");
		}
		for (const FBoneChain& Chain : RigChains)
		{
			TArray<int32> Bones = ChainBones(Ref, Tree, Chain.StartBone.BoneName, Chain.EndBone.BoneName);
			if (Bones.Num() > 0) { Out.Chains.Add({ Chain.ChainName, MoveTemp(Bones) }); }
		}
		return Out;
	}

	bool VerticalRange(const FTree& Tree, double& OutFloor, double& OutTop)
	{
		TArray<double> Zs;
		for (int32 Bone = 0; Bone < Tree.Num(); ++Bone)
		{
			if (Tree.Parents[Bone] != INDEX_NONE)
			{
				Zs.Add(Tree.Pos(Tree.Parents[Bone]).Z);
				Zs.Add(Tree.Pos(Bone).Z);
			}
		}
		if (Zs.Num() == 0)
		{
			return false;
		}
		Zs.Sort();
		const double Lo = Zs[static_cast<int32>(0.05 * (Zs.Num() - 1))], Hi = Zs[static_cast<int32>(0.95 * (Zs.Num() - 1))];
		const double Margin = OutlierMargin * (Hi - Lo);
		OutFloor = TNumericLimits<double>::Max();
		OutTop = -TNumericLimits<double>::Max();
		for (const double Z : Zs)
		{
			if (Z >= Lo - Margin && Z <= Hi + Margin)
			{
				OutFloor = FMath::Min(OutFloor, Z);
				OutTop = FMath::Max(OutTop, Z);
			}
		}
		return true;
	}

	bool FeetFacing(const FTree& Tree, FVector& OutFacing)
	{
		double Floor = 0.0, Top = 0.0;
		if (!VerticalRange(Tree, Floor, Top))
		{
			return false;
		}
		const double Limit = Floor + FootRegion * (Top - Floor);
		FVector Sum = FVector::ZeroVector;
		for (int32 Bone = 0; Bone < Tree.Num(); ++Bone)
		{
			const int32 Parent = Tree.Parents[Bone];
			if (Parent == INDEX_NONE) { continue; }
			const FVector A = Tree.Pos(Parent), B = Tree.Pos(Bone);
			if (A.Z >= Floor && A.Z <= Limit && B.Z >= Floor && B.Z <= Limit)
			{
				Sum += FVector(B.X - A.X, B.Y - A.Y, 0.0);
			}
		}
		if (Sum.Size2D() < 1e-3 * FMath::Max(Top - Floor, 1.0))
		{
			return false;
		}
		OutFacing = Sum.GetSafeNormal2D();
		return true;
	}

	bool PrincipalAxes(const TArray<FVector>& Points, FVector& OutCentroid, FVector (&OutAxes)[3], double (&OutVariance)[3])
	{
		if (Points.Num() == 0)
		{
			return false;
		}
		OutCentroid = FVector::ZeroVector;
		for (const FVector& P : Points) { OutCentroid += P; }
		OutCentroid /= Points.Num();
		double C[3][3] = {};
		for (const FVector& P : Points)
		{
			const FVector D = P - OutCentroid;
			for (int32 i = 0; i < 3; ++i)
			{
				for (int32 j = 0; j < 3; ++j) { C[i][j] += D[i] * D[j]; }
			}
		}
		for (int32 i = 0; i < 3; ++i)
		{
			for (int32 j = 0; j < 3; ++j) { C[i][j] /= Points.Num(); }
		}
		// 순환 야코비 — 비대각 원소를 하나씩 0 으로(대칭 3×3 은 몇 번이면 수렴)
		double V[3][3] = { { 1, 0, 0 }, { 0, 1, 0 }, { 0, 0, 1 } };
		for (int32 Sweep = 0; Sweep < 50; ++Sweep)
		{
			const double Off = FMath::Abs(C[0][1]) + FMath::Abs(C[0][2]) + FMath::Abs(C[1][2]);
			if (Off < 1e-12 * (FMath::Abs(C[0][0]) + FMath::Abs(C[1][1]) + FMath::Abs(C[2][2]) + 1e-30))
			{
				break;
			}
			for (int32 p = 0; p < 2; ++p)
			{
				for (int32 q = p + 1; q < 3; ++q)
				{
					if (FMath::Abs(C[p][q]) < 1e-300)
					{
						continue;
					}
					const double Theta = (C[q][q] - C[p][p]) / (2.0 * C[p][q]);
					const double T = (Theta >= 0.0 ? 1.0 : -1.0) / (FMath::Abs(Theta) + FMath::Sqrt(Theta * Theta + 1.0));
					const double Cos = 1.0 / FMath::Sqrt(T * T + 1.0);
					const double Sin = T * Cos;
					for (int32 k = 0; k < 3; ++k)
					{
						const double Ckp = C[k][p], Ckq = C[k][q];
						C[k][p] = Cos * Ckp - Sin * Ckq;
						C[k][q] = Sin * Ckp + Cos * Ckq;
					}
					for (int32 k = 0; k < 3; ++k)
					{
						const double Cpk = C[p][k], Cqk = C[q][k];
						C[p][k] = Cos * Cpk - Sin * Cqk;
						C[q][k] = Sin * Cpk + Cos * Cqk;
					}
					for (int32 k = 0; k < 3; ++k)
					{
						const double Vkp = V[k][p], Vkq = V[k][q];
						V[k][p] = Cos * Vkp - Sin * Vkq;
						V[k][q] = Sin * Vkp + Cos * Vkq;
					}
				}
			}
		}
		int32 Order[3] = { 0, 1, 2 };
		Algo::Sort(Order, [&C](int32 A, int32 B) { return C[A][A] > C[B][B]; });
		for (int32 i = 0; i < 3; ++i)
		{
			const int32 k = Order[i];
			FVector Axis(V[0][k], V[1][k], V[2][k]);
			Axis.Normalize();
			const int32 Big = FMath::Abs(Axis.X) >= FMath::Abs(Axis.Y) && FMath::Abs(Axis.X) >= FMath::Abs(Axis.Z) ? 0 : FMath::Abs(Axis.Y) >= FMath::Abs(Axis.Z) ? 1 : 2;
			if (Axis[Big] < 0.0) { Axis = -Axis; }
			OutAxes[i] = Axis;
			OutVariance[i] = FMath::Max(0.0, C[k][k]);
		}
		return true;
	}
}
