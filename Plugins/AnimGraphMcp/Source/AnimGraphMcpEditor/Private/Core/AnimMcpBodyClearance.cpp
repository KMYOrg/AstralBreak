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
#include "Misc/Base64.h"
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
		 * 각도 칸 수 AngleBins 는 헤더(공개 FRadialAxis 와 함께)
		 */
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
		/** 부위 쌍(8-4a) — 위팔 점은 어깨 관절에서 위팔 길이 × 이 비 안을 뺀다(몸통에 붙은 삼각근은 기준 포즈부터 몸통 지도 안) */
		constexpr double ShoulderExcludeRatio = 0.4;
		/**
		 * 머리 · 목 축(목 뿌리 → 머리 꼭대기) · 종아리 축(무릎 → 발목)의 반경 지도. 머리 지도는 꼭대기(t 1.0 = 정수리)에서 끝난다 — 그 위는 머리 밖인데
		 * 뿔 줄기 정점이 t 1.0 ~ 1.05 에 반경 15 cm 로 들어가 칸을 꽉 찬 몸으로 채웠다(Vesper 낫 정정 선택 2.03초 정수리 위 손 13.2 cm 가짜 관통)
		 */
		constexpr int32 HeadBins = 24;
		constexpr double HeadTMin = -0.1, HeadTMax = 1.0;
		/** 머리 꼭대기 = 기준 축선(목 뿌리 → 머리 방향)에서 이 반경(cm × scale) 안 머리 정점의 최대 투영(정수리) — 축에서 먼 뿔 · 큰 머리카락 끝은 뺀다(Vesper 뿔 끝 z 185 → 꼭대기로 잡으면 두개 위 칸이 이웃 채움으로 15 ~ 17 cm, 손이 정수리 위 축 근처면 16.9 cm 관통) */
		constexpr double HeadCrownRadiusCm = 5.0;
		constexpr int32 CalfBins = 24;
		constexpr double CalfTMin = -0.1, CalfTMax = 1.0;
		/**
		 * 손끼리(8-4b) — 손 지도(손목 → 손 끝) · 아래팔 지도(팔꿈치 → 손목). 손 점 ≈ 200 개/손(낫 정정 선택 팔 점 1171 ÷ 6)이라 12 × 36 칸 절반쯤 차고
		 * 3×3 이웃이 메운다. 손 지도는 손목 조금 앞(t −0.15 — 손목 뼈 둘레 살)부터, 둘 다 끝을 살짝 넘긴다(손가락 끝 · 손목 쪽 손바닥 뿌리)
		 */
		constexpr int32 HandBins = 12;
		constexpr double HandTMin = -0.15, HandTMax = 1.05;
		constexpr int32 ForearmBins = 14;
		constexpr double ForearmTMin = -0.1, ForearmTMax = 1.05;
		/** 다리끼리 — 반대 넓적다리 지도는 칸 가운데 t 가 이 값 이상인 칸만(사타구니 쪽은 서 있기만 해도 안쪽 허벅지가 닿는다) */
		constexpr double LegThighTMin = 0.2;
		/** 중앙선 체인 — 두 위팔 중점에서 좌우로 어깨 반폭 × 이 비 안 */
		constexpr double MidlineRatio = 0.25;
		/** 몸통 칸 경계 기본값(척추 마디를 모를 때) */
		constexpr double DefaultBellyT = 0.2;
		constexpr double DefaultChestT = 0.5;
		/** 모델 내보내기 — 반경 int16 단위(cm) · 프레임 간격 상한 */
		constexpr double RadiusUnitCm = 0.01;
		constexpr int32 MaxModelStride = 10;

		// 체인 · 거울 짝 · 팔다리 판정은 공통부 (AnimMcpSkeletonGeometry — 손가락 체인 제안 · 검증과 같은 원천)
		using AnimMcpSkeletonGeometry::FTree;
		using AnimMcpSkeletonGeometry::MinSegmentCm;

		/** Upper · Head · Calf 는 부위 쌍(8-4a, Spec.NeedsParts)일 때만 — 지금 None 인 본에만 준다(몸 · 팔 그룹과 그 점은 그대로) */
		enum class EGroup : uint8
		{
			None,
			Core,
			Secondary,
			Arm0,
			Arm1,
			Upper0,
			Upper1,
			Head,
			Calf0,
			Calf1,
		};
		constexpr int32 NumSlots = 9;
		int32 Slot(EGroup Group) { return static_cast<int32>(Group) - 1; }

		/** 점의 부위 — 팔(손 · 아래팔 · 위팔) · 다리(넓적다리 · 종아리). 몸통 · 머리 정점은 NoPart */
		enum class EPart : uint8
		{
			Hand,
			Forearm,
			UpperArm,
			Thigh,
			Calf,
			NoPart = 255,
		};
		const TCHAR* const PartNames[] = { TEXT("hand"), TEXT("forearm"), TEXT("upper_arm"), TEXT("thigh"), TEXT("calf") };
		constexpr int32 NumArmParts = 3;
		/** 몸 부위 — 몸통 칸 3 · 넓적다리 좌우 · 머리 · 목 */
		enum EBodyPart : int32 { BodyPelvis, BodyBelly, BodyChest, BodyThighL, BodyThighR, BodyHeadNeck, NumBodyParts };
		const TCHAR* const BodyPartNames[] = { TEXT("pelvis"), TEXT("belly"), TEXT("chest"), TEXT("thigh_l"), TEXT("thigh_r"), TEXT("head_neck") };
		const TCHAR* const SideNames[] = { TEXT("l"), TEXT("r") };

		int32 TorsoPartIndex(double T, double BellyT, double ChestT)
		{
			return T < BellyT ? BodyPelvis : T < ChestT ? BodyBelly : BodyChest;
		}

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
			/** 부위 쌍(8-4a) — 머리 · 목 축(중앙선 체인의 가장 낮은 본 · 가장 높은 본) · 발목(다리 체인 [2]) · 몸 기준 좌우(0 = l, 1 = r) · 척추 마디(아래부터) */
			int32 NeckRoot = INDEX_NONE;
			int32 Head = INDEX_NONE;
			FString HeadSkipped;
			int32 Feet[2] = { INDEX_NONE, INDEX_NONE };
			int32 ArmSide[2] = { 0, 1 };
			int32 LegSide[2] = { 0, 1 };
			FString SidesFrom;
			TArray<int32> SpineRoots;
		};

		/** 줄인 스킨 정점 — 기준 포즈 컴포넌트 공간 위치, 큰 순 영향. Axis = 반경 지도 축(0 몸통, 1 · 2 넓적다리) · Part = 부위 쌍의 팔 · 다리 부위 */
		struct FPoint
		{
			FVector Position = FVector::ZeroVector;
			int32 Dominant = INDEX_NONE;
			int32 Axis = 0;
			EPart Part = EPart::NoPart;
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
			/** 부위 쌍(8-4a) — 몸통 칸 경계 t(척추 마디 s1 · s2 의 기준 포즈 t) · 머리 꼭대기(머리 본 로컬) · 위팔 어깨 제외 반경 */
			double BellyT = DefaultBellyT;
			double ChestT = DefaultChestT;
			int32 TorsoFrom[2] = { INDEX_NONE, INDEX_NONE };
			bool bHeadAxis = false;
			/** 머리 꼭대기를 축선 근처 정점(정수리)으로 잡았는지 — 아니면 머리 그룹 전체의 최대 투영 */
			bool bHeadCrown = false;
			FVector HeadTopLocal = FVector::ZeroVector;
			double ShoulderExcludeCm[2] = { 0.0, 0.0 };
			/** 손끼리(8-4b, Spec.bHands) — 손 끝(손목 본 로컬, 팔 a 순서) · 손 점이 있어 손 축을 잡았는지 */
			FVector HandTipLocal[2] = { FVector::ZeroVector, FVector::ZeroVector };
			bool bHandTip[2] = { false, false };
		};

		FName BoneName(const USkeletalMesh* Mesh, int32 Bone)
		{
			return Bone == INDEX_NONE ? NAME_None : Mesh->GetRefSkeleton().GetBoneName(Bone);
		}

		/**
		 * 부위 쌍 그룹(8-4a) — 지금 None 인 본에만: 위팔(위팔 본과 자손 중 팔꿈치 자손이 아닌 것 — 트위스트) · 종아리(무릎 본과 자손 중 발목 자손이
		 * 아닌 것) · 머리 · 목(중앙선 체인 — 척추 끝 아래 · 위팔 쪽 가지 밖 · 두 위팔 중점에서 좌우 어깨 반폭 × 0.25 안 · 척추 끝보다 위. 그 체인 본과
		 * 짧은 보조 본(눈 · 턱), 3마디+ 가지(머리카락 본)는 뺀다). 척추 마디(아래부터) · 몸 기준 좌우(발 영역 정면 — 이름 없이)
		 */
		void BuildPartGroups(const FTree& Tree, const TArray<TArray<int32>>& Chains, int32 LegA, int32 LegB, FBodyMap& Out)
		{
			const int32 N = Tree.Num();
			auto Assign = [&Out, N](EGroup Group, TFunctionRef<bool(int32)> Pred)
			{
				for (int32 Bone = 0; Bone < N; ++Bone)
				{
					if (Out.Groups[Bone] == EGroup::None && Pred(Bone)) { Out.Groups[Bone] = Group; }
				}
			};
			for (int32 a = 0; a < FMath::Min(2, Out.Arms.Num()); ++a)
			{
				const FArm Arm = Out.Arms[a];
				Assign(a == 0 ? EGroup::Upper0 : EGroup::Upper1, [&Tree, Arm](int32 Bone) { return Tree.IsSelfOrAncestor(Arm.Upper, Bone) && !Tree.IsSelfOrAncestor(Arm.Elbow, Bone); });
			}
			for (int32 k = 0; k < 2; ++k)
			{
				const int32 Index = k == 0 ? LegA : LegB;
				const int32 Knee = Out.Knees[k];
				if (Knee == INDEX_NONE)
				{
					continue;
				}
				Out.Feet[k] = Index != INDEX_NONE && Chains[Index].IsValidIndex(2) ? Chains[Index][2] : Tree.LargestChild(Knee);
				const int32 Foot = Out.Feet[k];
				Assign(k == 0 ? EGroup::Calf0 : EGroup::Calf1, [&Tree, Knee, Foot](int32 Bone) { return Tree.IsSelfOrAncestor(Knee, Bone) && (Foot == INDEX_NONE || !Tree.IsSelfOrAncestor(Foot, Bone)); });
			}

			// ---- 머리 · 목 ----
			if (Out.SpineTop == INDEX_NONE || Out.Arms.Num() != 2)
			{
				Out.HeadSkipped = TEXT("NO_TORSO_AXIS");
			}
			else
			{
				const FVector U0 = Tree.Pos(Out.Arms[0].Upper), U1 = Tree.Pos(Out.Arms[1].Upper);
				const FVector Mid = (U0 + U1) * 0.5;
				const FVector Lateral = (U0 - U1).GetSafeNormal();
				const double Half = FVector::Dist(U0, U1) * 0.5;
				// 팔 쪽 가지의 뿌리 = 위팔에서 척추 끝 바로 아래까지 올라간 본(쇄골)
				int32 ArmRoots[2];
				for (int32 a = 0; a < 2; ++a)
				{
					int32 Root = Out.Arms[a].Upper;
					while (Tree.Parents[Root] != INDEX_NONE && Tree.Parents[Root] != Out.SpineTop) { Root = Tree.Parents[Root]; }
					ArmRoots[a] = Root;
				}
				TSet<int32> HeadSet;
				for (const TArray<int32>& Chain : Chains)
				{
					if (Chain.Num() == 0)
					{
						continue;
					}
					const int32 Start = Chain[0];
					const bool bArmSide = Tree.IsSelfOrAncestor(ArmRoots[0], Start) || Tree.IsSelfOrAncestor(ArmRoots[1], Start);
					if (!Tree.IsAncestor(Out.SpineTop, Start) || bArmSide || FMath::Abs(FVector::DotProduct(Tree.Pos(Start) - Mid, Lateral)) > MidlineRatio * Half
						|| Tree.Pos(Start).Z < Tree.Pos(Out.SpineTop).Z - MinSegmentCm)
					{
						continue;
					}
					for (const int32 Bone : Chain) { HeadSet.Add(Bone); }
				}
				if (HeadSet.Num() == 0)
				{
					Out.HeadSkipped = TEXT("NO_HEAD_CHAIN");
				}
				else
				{
					for (const int32 Bone : HeadSet)
					{
						if (Out.NeckRoot == INDEX_NONE || Tree.Pos(Bone).Z < Tree.Pos(Out.NeckRoot).Z) { Out.NeckRoot = Bone; }
						if (Out.Head == INDEX_NONE || Tree.Pos(Bone).Z > Tree.Pos(Out.Head).Z) { Out.Head = Bone; }
					}
					TSet<int32> Stops;
					for (const TArray<int32>& Chain : Chains)
					{
						for (const int32 Bone : Chain)
						{
							if (!HeadSet.Contains(Bone)) { Stops.Add(Bone); }
						}
					}
					for (int32 Bone = 0; Bone < N; ++Bone)
					{
						if (Out.Groups[Bone] != EGroup::None)
						{
							continue;
						}
						int32 Below = INDEX_NONE;
						for (int32 Walk = Bone; Walk != INDEX_NONE && Walk != Out.SpineTop; Below = Walk, Walk = Tree.Parents[Walk])
						{
							if (HeadSet.Contains(Walk))
							{
								const bool bHanging = Below != INDEX_NONE && !HeadSet.Contains(Below) && Tree.Height[Below] >= SecondaryDepth;
								if (!bHanging) { Out.Groups[Bone] = EGroup::Head; }
								break;
							}
							if (Stops.Contains(Walk)) { break; }
						}
					}
				}
			}

			// ---- 척추 마디 · 좌우 ----
			for (const int32 Root : Out.CoreRoots)
			{
				if (Root != Out.Pelvis && Root != Out.Thighs[0] && Root != Out.Thighs[1]) { Out.SpineRoots.Add(Root); }
			}
			Out.SpineRoots.Sort([&Tree](int32 A, int32 B) { return Tree.Pos(A).Z < Tree.Pos(B).Z; });
			FVector Facing;
			if (AnimMcpSkeletonGeometry::FeetFacing(Tree, Facing))
			{
				// 몸 왼쪽 = 정면 × 위 (UE 왼손 좌표 — +Y 정면이면 +X, Vesper 와 같다)
				const FVector Left = FVector::CrossProduct(Facing, FVector::UpVector);
				if (Out.Arms.Num() == 2)
				{
					Out.ArmSide[0] = FVector::DotProduct(Tree.Pos(Out.Arms[0].Upper) - Tree.Pos(Out.Arms[1].Upper), Left) > 0.0 ? 0 : 1;
					Out.ArmSide[1] = 1 - Out.ArmSide[0];
				}
				if (Out.Thighs[0] != INDEX_NONE && Out.Thighs[1] != INDEX_NONE)
				{
					Out.LegSide[0] = FVector::DotProduct(Tree.Pos(Out.Thighs[0]) - Tree.Pos(Out.Thighs[1]), Left) > 0.0 ? 0 : 1;
					Out.LegSide[1] = 1 - Out.LegSide[0];
				}
				Out.SidesFrom = TEXT("feet_facing");
			}
			else
			{
				Out.SidesFrom = TEXT("chain_order");
			}
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
			if (Spec.NeedsParts())
			{
				BuildPartGroups(Tree, Chains, LegA, LegB, Out);
			}
			return true;
		}

		double SegmentDistance(const FVector& P, const FVector& A, const FVector& B)
		{
			const FVector AB = B - A;
			const double T = AB.SizeSquared() > UE_SMALL_NUMBER ? FMath::Clamp(FVector::DotProduct(P - A, AB) / AB.SizeSquared(), 0.0, 1.0) : 0.0;
			return FVector::Dist(P, A + AB * T);
		}

		/**
		 * OutHeadProj = 머리 그룹 정점(줄이기 전)이 목 뿌리에서 HeadDir 로 가장 멀리 나간 거리 · OutCrownProj = 그중 축선(목 뿌리 + HeadDir)에서
		 * CrownRadius 안 정점만(정수리 — 머리 그룹이 없거나 축 근처 정점이 없으면 그대로)
		 */
		bool BuildPoints(const USkeletalMesh* Mesh, const FTree& Tree, const FBodyMap& Map, double Cell, double ArmReach, TArray<FPoint> (&Out)[NumSlots], FString& OutWhy,
			const FVector& HeadDir, double CrownRadius, double& OutHeadProj, double& OutCrownProj)
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
					else if (Group == EGroup::Upper0 || Group == EGroup::Upper1)
					{
						// 위팔 선분(어깨 → 팔꿈치)에서 ArmReach 안, 어깨 관절에서 위팔 길이 × ShoulderExcludeRatio 밖
						const FArm& Arm = Map.Arms[Group == EGroup::Upper0 ? 0 : 1];
						const FVector S = Tree.Pos(Arm.Upper), E = Tree.Pos(Arm.Elbow);
						if (SegmentDistance(Position, S, E) > ArmReach || FVector::Dist(Position, S) <= ShoulderExcludeRatio * FVector::Dist(S, E))
						{
							continue;
						}
					}
					else if (Group == EGroup::Head && Map.NeckRoot != INDEX_NONE)
					{
						const FVector D = Position - Tree.Pos(Map.NeckRoot);
						const double Along = FVector::DotProduct(D, HeadDir);
						OutHeadProj = FMath::Max(OutHeadProj, Along);
						if ((D - HeadDir * Along).SizeSquared() <= FMath::Square(CrownRadius))
						{
							OutCrownProj = FMath::Max(OutCrownProj, Along);
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
					switch (Group)
					{
					case EGroup::Arm0:
					case EGroup::Arm1:
					{
						const int32 Wrist = Map.Arms[Group == EGroup::Arm0 ? 0 : 1].Wrist;
						Point.Part = Wrist != INDEX_NONE && Tree.IsSelfOrAncestor(Wrist, Dominant) ? EPart::Hand : EPart::Forearm;
						break;
					}
					case EGroup::Upper0:
					case EGroup::Upper1:
						Point.Part = EPart::UpperArm;
						break;
					case EGroup::Calf0:
					case EGroup::Calf1:
						Point.Part = EPart::Calf;
						break;
					case EGroup::Core:
						Point.Part = Point.Axis > 0 ? EPart::Thigh : EPart::NoPart;
						break;
					default:
						break;
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
			// 머리 · 목 축 방향(기준 포즈) — 목 뿌리 → 머리 본, 한 본이면 척추 끝 → 머리 본
			const FTree& Tree = Out.Tree;
			const FBodyMap& Map = Out.Map;
			FVector HeadDir = FVector::UpVector;
			double HeadProj = -TNumericLimits<double>::Max();
			double CrownProj = -TNumericLimits<double>::Max();
			if (Map.Head != INDEX_NONE)
			{
				const FVector From = FVector::Dist(Tree.Pos(Map.Head), Tree.Pos(Map.NeckRoot)) > MinSegmentCm ? Tree.Pos(Map.NeckRoot) : Tree.Pos(Map.SpineTop);
				HeadDir = (Tree.Pos(Map.Head) - From).GetSafeNormal();
				if (HeadDir.IsNearlyZero()) { HeadDir = FVector::UpVector; }
			}
			if (!BuildPoints(Mesh, Out.Tree, Out.Map, DecimateCellCm * Out.Scale, ArmReachCm * Out.Scale, Out.Points, OutWhy, HeadDir, HeadCrownRadiusCm * Out.Scale,
				HeadProj, CrownProj))
			{
				return false;
			}
			if (Spec.NeedsParts())
			{
				// 몸통 칸 경계 = 척추 마디(펠비스 위, 아래부터 s1 · s2)의 기준 포즈 t — 몸통 축 끝(척추 끝 자신)은 뺀다
				const bool bLegs = Map.Thighs[0] != INDEX_NONE && Map.Thighs[1] != INDEX_NONE;
				const FVector Bottom = bLegs ? (Tree.Pos(Map.Thighs[0]) + Tree.Pos(Map.Thighs[1])) * 0.5 : Tree.Pos(Map.Pelvis);
				const FVector Axis = Tree.Pos(Map.SpineTop) - Bottom;
				const double Length = Axis.Size();
				int32 Found = 0;
				for (const int32 Root : Map.SpineRoots)
				{
					const double T = Length > MinSegmentCm ? FVector::DotProduct(Tree.Pos(Root) - Bottom, Axis) / (Length * Length) : -1.0;
					if (T > 0.02 && T < 0.98 && Found < 2)
					{
						(Found == 0 ? Out.BellyT : Out.ChestT) = T;
						Out.TorsoFrom[Found++] = Root;
					}
				}
				if (Found < 2) { Out.ChestT = FMath::Max(Out.BellyT + 0.1, DefaultChestT); }
				// 머리 꼭대기 = 축선 근처 머리 정점의 최대 투영(정수리 — 그 위 뿔은 t > 1.0 으로 지도 밖), 축 근처 정점이 없으면 머리 그룹 전체의 최대 투영.
				// 머리 본보다 낮으면 머리 본 + 1 cm — 머리 본 로컬로 두어 프레임마다 따라간다
				if (Map.Head != INDEX_NONE && Out.Points[Slot(EGroup::Head)].Num() > 0)
				{
					Out.bHeadCrown = CrownProj > -TNumericLimits<double>::Max();
					const double HeadLen = FVector::DotProduct(Tree.Pos(Map.Head) - Tree.Pos(Map.NeckRoot), HeadDir);
					const FVector Top = Tree.Pos(Map.NeckRoot) + HeadDir * FMath::Max(Out.bHeadCrown ? CrownProj : HeadProj, HeadLen + 1.0);
					Out.HeadTopLocal = Tree.Global[Map.Head].InverseTransformPosition(Top);
					Out.bHeadAxis = true;
				}
				for (int32 a = 0; a < 2; ++a)
				{
					Out.ShoulderExcludeCm[a] = ShoulderExcludeRatio * FVector::Dist(Tree.Pos(Map.Arms[a].Upper), Tree.Pos(Map.Arms[a].Elbow));
				}
				// 손 끝(8-4b) — 기준 포즈 손 점의 무게중심 방향 최대 투영, 손목 본 로컬로 두어 프레임마다 따라간다
				for (int32 a = 0; a < 2 && Spec.bHands; ++a)
				{
					const FArm& Arm = Map.Arms[a];
					if (Arm.Wrist == INDEX_NONE)
					{
						continue;
					}
					TArray<FVector> HandPoints;
					for (const FPoint& Point : Out.Points[Slot(a == 0 ? EGroup::Arm0 : EGroup::Arm1)])
					{
						if (Point.Part == EPart::Hand) { HandPoints.Add(Point.Position); }
					}
					const FVector Tip = HandTip(HandPoints, Tree.Pos(Arm.Elbow), Tree.Pos(Arm.Wrist));
					Out.bHandTip[a] = FVector::Dist(Tip, Tree.Pos(Arm.Wrist)) > MinSegmentCm;
					Out.HandTipLocal[a] = Tree.Global[Arm.Wrist].InverseTransformPosition(Tip);
				}
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

		// 반경 지도 FRadialAxis 는 헤더(공개 — 계산부 단위 테스트 · anim_gen/body_model.py 와 같은 규칙), 정의는 아래 namespace 끝

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

		// ---- 부위 쌍 (Phase 8-4a — Spec.NeedsParts 일 때만) ----

		/** 한 프레임의 머리 · 목 · 종아리 반경 지도 (몸통 · 넓적다리는 FFrameBody) */
		struct FPartBody
		{
			FRadialAxis Head;
			FRadialAxis Calf[2];
			/** 지도에 넣은 정점 (Who 가 가리킨다) */
			TArray<FVector> HeadPositions;
			TArray<FVector> CalfPositions[2];

			void Build(const FModel& Model, const TArray<FTransform>& Pose, const TArray<FTransform>& Skin)
			{
				const FBodyMap& Map = Model.Map;
				const FVector Lateral = Pose[Map.Arms[0].Upper].GetLocation() - Pose[Map.Arms[1].Upper].GetLocation();
				Head = FRadialAxis();
				HeadPositions.Reset();
				if (Model.bHeadAxis)
				{
					Head.Init(Pose[Map.NeckRoot].GetLocation(), Pose[Map.Head].TransformPosition(Model.HeadTopLocal), Lateral, HeadTMin, HeadTMax, HeadBins);
					const TArray<FPoint>& Points = Model.Points[Slot(EGroup::Head)];
					SkinPoints(Points, Skin, HeadPositions);
					for (int32 i = 0; i < Points.Num(); ++i) { Head.Add(HeadPositions[i], i); }
				}
				for (int32 k = 0; k < 2; ++k)
				{
					Calf[k] = FRadialAxis();
					CalfPositions[k].Reset();
					const TArray<FPoint>& Points = Model.Points[Slot(k == 0 ? EGroup::Calf0 : EGroup::Calf1)];
					if (Map.Knees[k] == INDEX_NONE || Map.Feet[k] == INDEX_NONE || Points.Num() == 0)
					{
						continue;
					}
					Calf[k].Init(Pose[Map.Knees[k]].GetLocation(), Pose[Map.Feet[k]].GetLocation(), Lateral, CalfTMin, CalfTMax, CalfBins);
					SkinPoints(Points, Skin, CalfPositions[k]);
					for (int32 i = 0; i < Points.Num(); ++i) { Calf[k].Add(CalfPositions[k][i], i); }
				}
			}
		};

		/** 점 하나를 지도 하나에 — 칸 가운데 t < MinT 인 칸 · 빈 칸(이웃도 비면)은 안 본다. 깊이 = 반경 − 축까지 거리(부호 있음) */
		bool ProbeAxis(const FRadialAxis& Axis, const FVector& P, double MinT, int32& OutT, double& OutDepth, int32& OutWho)
		{
			int32 T = 0, Angle = 0;
			FVector Radial;
			if (!Axis.Locate(P, T, Angle, Radial) || Axis.BinCenter(T) < MinT)
			{
				return false;
			}
			const double Rho = Axis.Radius(T, Angle, OutWho);
			if (Rho < 0.0 || OutWho == INDEX_NONE)
			{
				return false;
			}
			OutT = T;
			OutDepth = Rho - Radial.Size();
			return true;
		}

		/** 한 쌍의 한 프레임 — 가장 깊은 점(부호 있음 — 음수는 틈). 걸리는 칸이 없으면 bFound 거짓 */
		struct FPairHit
		{
			bool bFound = false;
			double Depth = 0.0;
			int32 ArmBone = INDEX_NONE;
			int32 BodyBone = INDEX_NONE;
			FVector ArmPoint = FVector::ZeroVector;
			FVector BodyPoint = FVector::ZeroVector;

			void Offer(double InDepth, int32 InArmBone, int32 InBodyBone, const FVector& InArmPoint, const FVector& InBodyPoint)
			{
				if (!bFound || InDepth > Depth)
				{
					bFound = true;
					Depth = InDepth;
					ArmBone = InArmBone;
					BodyBone = InBodyBone;
					ArmPoint = InArmPoint;
					BodyPoint = InBodyPoint;
				}
			}
		};

		TArray<TSharedPtr<FJsonValue>> VecJson(const FVector& V, int32 Digits = 2)
		{
			return { MakeShared<FJsonValueNumber>(AnimMcpStats::Round(V.X, Digits)), MakeShared<FJsonValueNumber>(AnimMcpStats::Round(V.Y, Digits)),
				MakeShared<FJsonValueNumber>(AnimMcpStats::Round(V.Z, Digits)) };
		}

		/**
		 * 한 쌍의 프레임별 깊이 요약 — 관통 깊이는 0 아래를 0 으로(arms[] 와 같은 비율 · 백분위 정의), worst = 가장 깊은(관통이 없으면 가장 가까운) 프레임,
		 * gap_min_cm = 한 번도 닿지 않았으면 가장 작은 틈. 비율의 분모는 전체 프레임
		 */
		TSharedRef<FJsonObject> PairJson(const USkeletalMesh* Mesh, const TArray<FPairHit>& Hits, double FrameRate, double ContactCm, double PenetrationCm)
		{
			TArray<double> Depths;
			int32 Worst = INDEX_NONE, OverContact = 0, OverPenetration = 0, Located = 0;
			TOptional<double> First;
			for (int32 f = 0; f < Hits.Num(); ++f)
			{
				const FPairHit& Hit = Hits[f];
				const double Depth = Hit.bFound ? FMath::Max(0.0, Hit.Depth) : 0.0;
				Depths.Add(Depth);
				if (Hit.bFound)
				{
					++Located;
					if (Worst == INDEX_NONE || Hit.Depth > Hits[Worst].Depth) { Worst = f; }
				}
				if (Depth > ContactCm)
				{
					++OverContact;
					if (!First.IsSet()) { First = FrameRate > 0.0 ? f / FrameRate : 0.0; }
				}
				if (Depth > PenetrationCm) { ++OverPenetration; }
			}
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			const double Frames = FMath::Max(1, Hits.Num());
			Obj->SetNumberField(TEXT("frames_over_contact_pct"), AnimMcpStats::Round(100.0 * OverContact / Frames, 1));
			Obj->SetNumberField(TEXT("frames_over_penetration_pct"), AnimMcpStats::Round(100.0 * OverPenetration / Frames, 1));
			Obj->SetNumberField(TEXT("depth_p50"), AnimMcpStats::Round(AnimMcpStats::Percentile(Depths, 50.0), 2));
			Obj->SetNumberField(TEXT("depth_p95"), AnimMcpStats::Round(AnimMcpStats::Percentile(Depths, 95.0), 2));
			Obj->SetNumberField(TEXT("depth_max"), AnimMcpStats::Round(Worst == INDEX_NONE ? 0.0 : FMath::Max(0.0, Hits[Worst].Depth), 2));
			Obj->SetNumberField(TEXT("located_pct"), AnimMcpStats::Round(100.0 * Located / Frames, 1));
			if (Worst != INDEX_NONE && Hits[Worst].Depth < 0.0)
			{
				Obj->SetNumberField(TEXT("gap_min_cm"), AnimMcpStats::Round(-Hits[Worst].Depth, 2));
			}
			else
			{
				Obj->SetField(TEXT("gap_min_cm"), MakeShared<FJsonValueNull>());
			}
			if (First.IsSet()) { Obj->SetNumberField(TEXT("first_contact_time"), AnimMcpStats::Round(First.GetValue(), 4)); }
			else { Obj->SetField(TEXT("first_contact_time"), MakeShared<FJsonValueNull>()); }
			TSharedRef<FJsonObject> WorstObj = AnimMcpJson::MakeObject();
			if (Worst != INDEX_NONE)
			{
				const FPairHit& Hit = Hits[Worst];
				WorstObj->SetNumberField(TEXT("frame"), Worst);
				WorstObj->SetNumberField(TEXT("time"), AnimMcpStats::Round(FrameRate > 0.0 ? Worst / FrameRate : 0.0, 4));
				WorstObj->SetNumberField(TEXT("depth"), AnimMcpStats::Round(Hit.Depth, 2));
				WorstObj->SetField(TEXT("arm_bone"), AnimMcpJson::StringOrNull(Hit.ArmBone != INDEX_NONE ? BoneName(Mesh, Hit.ArmBone).ToString() : FString()));
				WorstObj->SetField(TEXT("body_bone"), AnimMcpJson::StringOrNull(Hit.BodyBone != INDEX_NONE ? BoneName(Mesh, Hit.BodyBone).ToString() : FString()));
				WorstObj->SetArrayField(TEXT("arm_point_cm"), VecJson(Hit.ArmPoint));
				WorstObj->SetArrayField(TEXT("body_point_cm"), VecJson(Hit.BodyPoint));
			}
			Obj->SetObjectField(TEXT("worst"), WorstObj);
			return Obj;
		}

		/** 지도 하나의 모델 내보내기 버퍼 — 프레임마다 축(A · Dir · X · Length, Length 0 = 축 없음)과 칸 반경 */
		struct FMapExport
		{
			FString Part;
			double TMin = 0.0, TMax = 1.0;
			int32 TBins = 1;
			TArray<double> Axis;
			TArray<double> Radius;

			void Add(const FRadialAxis& Map)
			{
				const FVector Zero = FVector::ZeroVector;
				const bool bValid = Map.bValid;
				for (const FVector& V : { bValid ? Map.A : Zero, bValid ? Map.Dir : Zero, bValid ? Map.X : Zero })
				{
					Axis.Append({ V.X, V.Y, V.Z });
				}
				Axis.Add(bValid ? Map.Length : 0.0);
				for (int32 Cell = 0; Cell < TBins * AngleBins; ++Cell)
				{
					Radius.Add(bValid && Map.MaxRadius.IsValidIndex(Cell) ? Map.MaxRadius[Cell] : -1.0);
				}
			}
		};

		/**
		 * 부위 쌍 측정 — 팔 부위 점(손 · 아래팔 · 위팔) × 몸 부위 지도(몸통 칸 · 넓적다리 · 머리 · 목), legs 면 다리 점 × 반대 다리 지도.
		 * Out 에 parts{} · per_frame?{} · model?{} 를 쓰고 경고는 Issues 에. 기존 arms[] 계산과 따로 돈다(기본 결과는 이 함수가 바꾸지 않는다)
		 */
		void MeasureParts(const USkeletalMesh* Mesh, const FModel& Model, const FSpec& Spec, const TArray<TArray<FTransform>>& Poses, const TArray<FTransform>& RefInverse,
			double FrameRate, double ContactCm, double PenetrationCm, const TSharedRef<FJsonObject>& Out, TArray<TSharedPtr<FJsonValue>>& Issues, bool& bOutWarning)
		{
			const double StartSeconds = FPlatformTime::Seconds();
			const FTree& Tree = Model.Tree;
			const FBodyMap& Map = Model.Map;
			const int32 Frames = Poses.Num();
			const double NoMinT = -TNumericLimits<double>::Max();
			const TArray<FPoint>& Core = Model.Points[Slot(EGroup::Core)];
			const TArray<FPoint>& Heads = Model.Points[Slot(EGroup::Head)];
			auto Calves = [&Model](int32 k) -> const TArray<FPoint>& { return Model.Points[Slot(k == 0 ? EGroup::Calf0 : EGroup::Calf1)]; };
			auto ThighPart = [&Map](int32 k) { return Map.LegSide[k] == 0 ? BodyThighL : BodyThighR; };
			// [몸 기준 좌우][팔 부위][몸 부위] · 다리 [좌우][넓적다리 · 종아리][반대 넓적다리 · 반대 종아리] · 손끼리 [좌우][팔 부위][반대 손 · 반대 아래팔] — 프레임마다
			TArray<FPairHit> ArmHits[2][NumArmParts][NumBodyParts];
			TArray<FPairHit> LegHits[2][2][2];
			TArray<FPairHit> HandHits[2][NumArmParts][2];
			for (int32 s = 0; s < 2; ++s)
			{
				for (int32 p = 0; p < NumArmParts; ++p)
				{
					for (int32 b = 0; b < NumBodyParts; ++b) { ArmHits[s][p][b].SetNum(Frames); }
					for (int32 m = 0; m < 2; ++m) { HandHits[s][p][m].SetNum(Frames); }
				}
				for (int32 p = 0; p < 2; ++p)
				{
					for (int32 b = 0; b < 2; ++b) { LegHits[s][p][b].SetNum(Frames); }
				}
			}
			// 손끼리 지도 이름 — 팔 a 의 몸 기준 좌우
			auto HandMapName = [&Map](int32 a, int32 m) { return FString::Printf(TEXT("%s_%s"), m == 0 ? TEXT("hand") : TEXT("forearm"), SideNames[Map.ArmSide[a]]); };
			// 모델 — 내보낼 프레임(간격 stride, 끝 프레임 포함)과 지도 버퍼
			TArray<int32> ModelFrames;
			TArray<FMapExport> MapsOut;
			if (Spec.bModel)
			{
				for (int32 Frame = 0; Frame < Frames; Frame += FMath::Max(1, Spec.ModelStride)) { ModelFrames.Add(Frame); }
				if (Frames > 0 && ModelFrames.Last() != Frames - 1) { ModelFrames.Add(Frames - 1); }
				MapsOut.Add({ TEXT("torso"), TorsoTMin, TorsoTMax, TorsoBins });
				MapsOut.Add({ BodyPartNames[ThighPart(0)], ThighTMin, ThighTMax, ThighBins });
				MapsOut.Add({ BodyPartNames[ThighPart(1)], ThighTMin, ThighTMax, ThighBins });
				MapsOut.Add({ TEXT("head_neck"), HeadTMin, HeadTMax, HeadBins });
				if (Spec.bLegs)
				{
					MapsOut.Add({ Map.LegSide[0] == 0 ? TEXT("calf_l") : TEXT("calf_r"), CalfTMin, CalfTMax, CalfBins });
					MapsOut.Add({ Map.LegSide[1] == 0 ? TEXT("calf_l") : TEXT("calf_r"), CalfTMin, CalfTMax, CalfBins });
				}
			}
			const int32 HandMapsAt = MapsOut.Num();
			if (Spec.bModel && Spec.bHands)
			{
				// 손끼리(8-4b) — [hand 팔0, hand 팔1, forearm 팔0, forearm 팔1]
				for (int32 m = 0; m < 2; ++m)
				{
					for (int32 a = 0; a < 2; ++a)
					{
						MapsOut.Add({ HandMapName(a, m), m == 0 ? HandTMin : ForearmTMin, m == 0 ? HandTMax : ForearmTMax, m == 0 ? HandBins : ForearmBins });
					}
				}
			}

			TArray<FTransform> Skin;
			// 팔마다 [팔꿈치 이하(손 · 아래팔), 위팔] 점 위치 — 몸 지도 조회와 손끼리(반대 팔 지도 · 조회)가 함께 쓴다
			TArray<FVector> ArmPositions[2][2];
			FFrameBody Body;
			FPartBody Parts;
			FArmAxes ArmAxes[2];
			int32 NextModel = 0;
			for (int32 Frame = 0; Frame < Frames; ++Frame)
			{
				SkinTransforms(Poses[Frame], RefInverse, Skin);
				Body.Build(Map, Poses[Frame], Core, Skin);
				Parts.Build(Model, Poses[Frame], Skin);
				for (int32 a = 0; a < 2; ++a)
				{
					SkinPoints(Model.Points[Slot(a == 0 ? EGroup::Arm0 : EGroup::Arm1)], Skin, ArmPositions[a][0]);
					SkinPoints(Model.Points[Slot(a == 0 ? EGroup::Upper0 : EGroup::Upper1)], Skin, ArmPositions[a][1]);
				}
				for (int32 a = 0; a < 2; ++a)
				{
					const int32 Side = Map.ArmSide[a];
					for (int32 g = 0; g < 2; ++g)
					{
						const TArray<FPoint>& Points = Model.Points[Slot(g == 0 ? (a == 0 ? EGroup::Arm0 : EGroup::Arm1) : (a == 0 ? EGroup::Upper0 : EGroup::Upper1))];
						const TArray<FVector>& Positions = ArmPositions[a][g];
						for (int32 i = 0; i < Points.Num(); ++i)
						{
							const int32 ArmPart = static_cast<int32>(Points[i].Part);
							if (ArmPart >= NumArmParts)
							{
								continue;
							}
							const FVector& P = Positions[i];
							TArray<FPairHit>* PerBody = ArmHits[Side][ArmPart];
							int32 T = 0, Who = INDEX_NONE;
							double Depth = 0.0;
							if (ProbeAxis(Body.Axes[0], P, NoMinT, T, Depth, Who))
							{
								PerBody[TorsoPartIndex(Body.Axes[0].BinCenter(T), Model.BellyT, Model.ChestT)][Frame].Offer(Depth, Points[i].Dominant, Core[Who].Dominant, P, Body.Positions[Who]);
							}
							for (int32 k = 0; k < 2; ++k)
							{
								if (ProbeAxis(Body.Axes[k + 1], P, NoMinT, T, Depth, Who))
								{
									PerBody[ThighPart(k)][Frame].Offer(Depth, Points[i].Dominant, Core[Who].Dominant, P, Body.Positions[Who]);
								}
							}
							if (ProbeAxis(Parts.Head, P, NoMinT, T, Depth, Who))
							{
								PerBody[BodyHeadNeck][Frame].Offer(Depth, Points[i].Dominant, Heads[Who].Dominant, P, Parts.HeadPositions[Who]);
							}
						}
					}
				}
				if (Spec.bHands)
				{
					// 손끼리(8-4b) — 팔마다 손 · 아래팔 지도(그 팔의 손 · 아래팔 점) → 반대 팔의 손 · 아래팔 · 위팔 점이 묻는다
					const FVector Lateral = Poses[Frame][Map.Arms[0].Upper].GetLocation() - Poses[Frame][Map.Arms[1].Upper].GetLocation();
					for (int32 a = 0; a < 2; ++a)
					{
						const FArm& Arm = Map.Arms[a];
						ArmAxes[a] = FArmAxes();
						if (Arm.Wrist == INDEX_NONE)
						{
							continue;
						}
						const FTransform& Wrist = Poses[Frame][Arm.Wrist];
						ArmAxes[a].Init(Poses[Frame][Arm.Elbow].GetLocation(), Wrist.GetLocation(), Model.bHandTip[a] ? Wrist.TransformPosition(Model.HandTipLocal[a]) : Wrist.GetLocation(),
							Lateral);
						const TArray<FPoint>& Points = Model.Points[Slot(a == 0 ? EGroup::Arm0 : EGroup::Arm1)];
						for (int32 i = 0; i < Points.Num(); ++i)
						{
							(Points[i].Part == EPart::Hand ? ArmAxes[a].Hand : ArmAxes[a].Forearm).Add(ArmPositions[a][0][i], i);
						}
					}
					for (int32 a = 0; a < 2; ++a)
					{
						const int32 Other = 1 - a;
						const TArray<FPoint>& OtherPoints = Model.Points[Slot(Other == 0 ? EGroup::Arm0 : EGroup::Arm1)];
						for (int32 g = 0; g < 2; ++g)
						{
							const TArray<FPoint>& Points = Model.Points[Slot(g == 0 ? (a == 0 ? EGroup::Arm0 : EGroup::Arm1) : (a == 0 ? EGroup::Upper0 : EGroup::Upper1))];
							for (int32 i = 0; i < Points.Num(); ++i)
							{
								const int32 ArmPart = static_cast<int32>(Points[i].Part);
								if (ArmPart >= NumArmParts)
								{
									continue;
								}
								const FVector& P = ArmPositions[a][g][i];
								for (int32 m = 0; m < 2; ++m)
								{
									int32 T = 0, Who = INDEX_NONE;
									double Depth = 0.0;
									if (ProbeAxis(m == 0 ? ArmAxes[Other].Hand : ArmAxes[Other].Forearm, P, NoMinT, T, Depth, Who))
									{
										HandHits[Map.ArmSide[a]][ArmPart][m][Frame].Offer(Depth, Points[i].Dominant, OtherPoints[Who].Dominant, P, ArmPositions[Other][0][Who]);
									}
								}
							}
						}
					}
				}
				if (Spec.bLegs)
				{
					for (int32 k = 0; k < 2; ++k)
					{
						const int32 Other = 1 - k;
						const int32 Side = Map.LegSide[k];
						auto ProbeLeg = [&](const FVector& P, int32 LegPart, int32 Dominant)
						{
							int32 T = 0, Who = INDEX_NONE;
							double Depth = 0.0;
							if (ProbeAxis(Body.Axes[Other + 1], P, LegThighTMin, T, Depth, Who))
							{
								LegHits[Side][LegPart][0][Frame].Offer(Depth, Dominant, Core[Who].Dominant, P, Body.Positions[Who]);
							}
							if (ProbeAxis(Parts.Calf[Other], P, NoMinT, T, Depth, Who))
							{
								LegHits[Side][LegPart][1][Frame].Offer(Depth, Dominant, Calves(Other)[Who].Dominant, P, Parts.CalfPositions[Other][Who]);
							}
						};
						for (int32 i = 0; i < Core.Num(); ++i)
						{
							if (Core[i].Axis == k + 1) { ProbeLeg(Body.Positions[i], 0, Core[i].Dominant); }
						}
						for (int32 j = 0; j < Parts.CalfPositions[k].Num(); ++j) { ProbeLeg(Parts.CalfPositions[k][j], 1, Calves(k)[j].Dominant); }
					}
				}
				if (Spec.bModel && NextModel < ModelFrames.Num() && ModelFrames[NextModel] == Frame)
				{
					MapsOut[0].Add(Body.Axes[0]);
					MapsOut[1].Add(Body.Axes[1]);
					MapsOut[2].Add(Body.Axes[2]);
					MapsOut[3].Add(Parts.Head);
					if (Spec.bLegs)
					{
						MapsOut[4].Add(Parts.Calf[0]);
						MapsOut[5].Add(Parts.Calf[1]);
					}
					if (Spec.bHands)
					{
						MapsOut[HandMapsAt + 0].Add(ArmAxes[0].Hand);
						MapsOut[HandMapsAt + 1].Add(ArmAxes[1].Hand);
						MapsOut[HandMapsAt + 2].Add(ArmAxes[0].Forearm);
						MapsOut[HandMapsAt + 3].Add(ArmAxes[1].Forearm);
					}
					++NextModel;
				}
			}

			// ---- parts{} ----
			TSharedRef<FJsonObject> PartsObj = AnimMcpJson::MakeObject();
			TArray<FString> ArmPartList, BodyPartList;
			for (int32 p = 0; p < NumArmParts; ++p) { ArmPartList.Add(PartNames[p]); }
			for (int32 b = 0; b < NumBodyParts; ++b) { BodyPartList.Add(BodyPartNames[b]); }
			auto Strings = [](const TArray<FString>& Values)
			{
				TArray<TSharedPtr<FJsonValue>> Arr;
				for (const FString& V : Values) { Arr.Add(MakeShared<FJsonValueString>(V)); }
				return Arr;
			};
			PartsObj->SetArrayField(TEXT("arm_parts"), Strings(ArmPartList));
			PartsObj->SetArrayField(TEXT("body_parts"), Strings(BodyPartList));
			TSharedRef<FJsonObject> Sides = AnimMcpJson::MakeObject();
			Sides->SetStringField(TEXT("from"), Map.SidesFrom);
			for (int32 a = 0; a < 2; ++a) { Sides->SetStringField(SideNames[Map.ArmSide[a]], BoneName(Mesh, Map.Arms[a].Upper).ToString()); }
			PartsObj->SetObjectField(TEXT("sides"), Sides);
			TSharedRef<FJsonObject> Bounds = AnimMcpJson::MakeObject();
			Bounds->SetNumberField(TEXT("belly"), AnimMcpStats::Round(Model.BellyT, 4));
			Bounds->SetNumberField(TEXT("chest"), AnimMcpStats::Round(Model.ChestT, 4));
			Bounds->SetArrayField(TEXT("from"), Names(Mesh, { Model.TorsoFrom[0], Model.TorsoFrom[1] }));
			PartsObj->SetObjectField(TEXT("torso_t_bounds"), Bounds);
			TArray<TSharedPtr<FJsonValue>> Exclude;
			for (int32 a = 0; a < 2; ++a) { Exclude.Add(MakeShared<FJsonValueNumber>(AnimMcpStats::Round(Model.ShoulderExcludeCm[Map.ArmSide[0] == a ? 0 : 1], 2))); }
			PartsObj->SetArrayField(TEXT("upper_arm_exclude_cm"), Exclude);
			TSharedRef<FJsonObject> HeadObj = AnimMcpJson::MakeObject();
			if (Model.bHeadAxis)
			{
				HeadObj->SetStringField(TEXT("neck_root"), BoneName(Mesh, Map.NeckRoot).ToString());
				HeadObj->SetStringField(TEXT("head"), BoneName(Mesh, Map.Head).ToString());
				HeadObj->SetArrayField(TEXT("top_local_cm"), VecJson(Model.HeadTopLocal));
				HeadObj->SetStringField(TEXT("top_from"), Model.bHeadCrown ? TEXT("crown") : TEXT("max_projection"));
				HeadObj->SetNumberField(TEXT("crown_radius_cm"), AnimMcpStats::Round(HeadCrownRadiusCm * Model.Scale, 2));
				HeadObj->SetNumberField(TEXT("points"), Heads.Num());
			}
			else
			{
				const FString Why = Map.HeadSkipped.IsEmpty() ? TEXT("NO_HEAD_VERTICES") : Map.HeadSkipped;
				HeadObj->SetStringField(TEXT("skipped_reason"), Why);
				Issues.Add(Issue(TEXT("info"), TEXT("HEAD_AXIS_SKIPPED"), FString::Printf(TEXT("No head/neck axis (%s) — head_neck pairs are empty"), *Why)));
			}
			PartsObj->SetObjectField(TEXT("head"), HeadObj);
			TSharedRef<FJsonObject> Counts = AnimMcpJson::MakeObject();
			for (int32 a = 0; a < 2; ++a)
			{
				int32 PerPart[NumArmParts] = {};
				for (const EGroup Group : { a == 0 ? EGroup::Arm0 : EGroup::Arm1, a == 0 ? EGroup::Upper0 : EGroup::Upper1 })
				{
					for (const FPoint& Point : Model.Points[Slot(Group)])
					{
						if (static_cast<int32>(Point.Part) < NumArmParts) { ++PerPart[static_cast<int32>(Point.Part)]; }
					}
				}
				for (int32 p = 0; p < NumArmParts; ++p) { Counts->SetNumberField(FString::Printf(TEXT("%s.%s"), SideNames[Map.ArmSide[a]], PartNames[p]), PerPart[p]); }
			}
			Counts->SetNumberField(TEXT("head_neck"), Heads.Num());
			PartsObj->SetObjectField(TEXT("points"), Counts);

			struct FWorstPair { FString Name; double Depth; double Pct; };
			TArray<FWorstPair> Over;
			TArray<TSharedPtr<FJsonValue>> PairsOut;
			for (int32 s = 0; s < 2; ++s)
			{
				for (int32 p = 0; p < NumArmParts; ++p)
				{
					for (int32 b = 0; b < NumBodyParts; ++b)
					{
						TSharedRef<FJsonObject> Pair = PairJson(Mesh, ArmHits[s][p][b], FrameRate, ContactCm, PenetrationCm);
						Pair->SetStringField(TEXT("side"), SideNames[s]);
						Pair->SetStringField(TEXT("arm_part"), PartNames[p]);
						Pair->SetStringField(TEXT("body_part"), BodyPartNames[b]);
						if (Pair->GetNumberField(TEXT("depth_max")) > PenetrationCm)
						{
							Over.Add({ FString::Printf(TEXT("%s %s → %s"), SideNames[s], PartNames[p], BodyPartNames[b]), Pair->GetNumberField(TEXT("depth_max")),
								Pair->GetNumberField(TEXT("frames_over_penetration_pct")) });
						}
						PairsOut.Add(MakeShared<FJsonValueObject>(Pair));
					}
				}
			}
			PartsObj->SetArrayField(TEXT("pairs"), PairsOut);
			auto Summary = [](TArray<FWorstPair> List)
			{
				List.Sort([](const FWorstPair& A, const FWorstPair& B) { return A.Depth > B.Depth; });
				TArray<FString> Items;
				for (int32 i = 0; i < FMath::Min(6, List.Num()); ++i) { Items.Add(FString::Printf(TEXT("%s %.1f cm (%.1f%%)"), *List[i].Name, List[i].Depth, List[i].Pct)); }
				return FString::Join(Items, TEXT(", "));
			};
			if (Spec.bAllParts && Over.Num() > 0)
			{
				bOutWarning = true;
				Issues.Add(Issue(TEXT("warning"), TEXT("BODY_PENETRATION_PARTS"), FString::Printf(TEXT("%d arm/body part pair(s) go deeper than %.1f cm: %s"), Over.Num(), PenetrationCm, *Summary(Over))));
			}
			TArray<FWorstPair> LegOver;
			if (Spec.bLegs)
			{
				TArray<TSharedPtr<FJsonValue>> LegPairs;
				for (int32 s = 0; s < 2; ++s)
				{
					const int32 OtherSide = 1 - s;
					for (int32 p = 0; p < 2; ++p)
					{
						for (int32 b = 0; b < 2; ++b)
						{
							TSharedRef<FJsonObject> Pair = PairJson(Mesh, LegHits[s][p][b], FrameRate, ContactCm, PenetrationCm);
							const FString BodyPart = FString::Printf(TEXT("%s_%s"), b == 0 ? TEXT("thigh") : TEXT("calf"), SideNames[OtherSide]);
							Pair->SetStringField(TEXT("side"), SideNames[s]);
							Pair->SetStringField(TEXT("leg_part"), PartNames[p == 0 ? 3 : 4]);
							Pair->SetStringField(TEXT("body_part"), BodyPart);
							if (Pair->GetNumberField(TEXT("depth_max")) > PenetrationCm)
							{
								LegOver.Add({ FString::Printf(TEXT("%s %s → %s"), SideNames[s], PartNames[p == 0 ? 3 : 4], *BodyPart), Pair->GetNumberField(TEXT("depth_max")),
									Pair->GetNumberField(TEXT("frames_over_penetration_pct")) });
							}
							LegPairs.Add(MakeShared<FJsonValueObject>(Pair));
						}
					}
				}
				TSharedRef<FJsonObject> Legs = AnimMcpJson::MakeObject();
				Legs->SetNumberField(TEXT("thigh_t_min"), LegThighTMin);
				Legs->SetArrayField(TEXT("pairs"), LegPairs);
				PartsObj->SetObjectField(TEXT("legs"), Legs);
				if (LegOver.Num() > 0)
				{
					bOutWarning = true;
					Issues.Add(Issue(TEXT("warning"), TEXT("LEG_PENETRATION"), FString::Printf(TEXT("%d leg pair(s) go deeper than %.1f cm: %s"), LegOver.Num(), PenetrationCm, *Summary(LegOver))));
				}
			}
			if (Spec.bHands)
			{
				// 손끼리(8-4b) — 팔 부위 점 ↔ 반대 팔 손 · 아래팔 지도. 맞닿음(contact)까지는 모아 쥔 손의 정상, 관통 넘으면 경고
				TArray<FWorstPair> HandOver;
				TArray<TSharedPtr<FJsonValue>> HandPairs;
				for (int32 a = 0; a < 2; ++a)
				{
					const int32 Side = Map.ArmSide[a];
					for (int32 p = 0; p < NumArmParts; ++p)
					{
						for (int32 m = 0; m < 2; ++m)
						{
							TSharedRef<FJsonObject> Pair = PairJson(Mesh, HandHits[Side][p][m], FrameRate, ContactCm, PenetrationCm);
							const FString BodyPart = HandMapName(1 - a, m);
							Pair->SetStringField(TEXT("side"), SideNames[Side]);
							Pair->SetStringField(TEXT("arm_part"), PartNames[p]);
							Pair->SetStringField(TEXT("body_part"), BodyPart);
							if (Pair->GetNumberField(TEXT("depth_max")) > PenetrationCm)
							{
								HandOver.Add({ FString::Printf(TEXT("%s %s → %s"), SideNames[Side], PartNames[p], *BodyPart), Pair->GetNumberField(TEXT("depth_max")),
									Pair->GetNumberField(TEXT("frames_over_penetration_pct")) });
							}
							HandPairs.Add(MakeShared<FJsonValueObject>(Pair));
						}
					}
				}
				TSharedRef<FJsonObject> HandsObj = AnimMcpJson::MakeObject();
				HandsObj->SetNumberField(TEXT("hand_bins"), HandBins);
				HandsObj->SetNumberField(TEXT("forearm_bins"), ForearmBins);
				auto Span = [](double Lo, double Hi) { return TArray<TSharedPtr<FJsonValue>>{ MakeShared<FJsonValueNumber>(Lo), MakeShared<FJsonValueNumber>(Hi) }; };
				TSharedRef<FJsonObject> Range = AnimMcpJson::MakeObject();
				Range->SetArrayField(TEXT("hand"), Span(HandTMin, HandTMax));
				Range->SetArrayField(TEXT("forearm"), Span(ForearmTMin, ForearmTMax));
				HandsObj->SetObjectField(TEXT("t_range"), Range);
				TSharedRef<FJsonObject> Tips = AnimMcpJson::MakeObject();
				TSharedRef<FJsonObject> HandCounts = AnimMcpJson::MakeObject();
				for (int32 a = 0; a < 2; ++a)
				{
					if (Model.bHandTip[a]) { Tips->SetArrayField(SideNames[Map.ArmSide[a]], VecJson(Model.HandTipLocal[a], 3)); }
					else { Tips->SetField(SideNames[Map.ArmSide[a]], MakeShared<FJsonValueNull>()); }
					int32 PerPart[2] = {};
					for (const FPoint& Point : Model.Points[Slot(a == 0 ? EGroup::Arm0 : EGroup::Arm1)]) { ++PerPart[Point.Part == EPart::Hand ? 0 : 1]; }
					HandCounts->SetNumberField(FString::Printf(TEXT("%s.hand"), SideNames[Map.ArmSide[a]]), PerPart[0]);
					HandCounts->SetNumberField(FString::Printf(TEXT("%s.forearm"), SideNames[Map.ArmSide[a]]), PerPart[1]);
				}
				HandsObj->SetObjectField(TEXT("tip_local_cm"), Tips);
				HandsObj->SetObjectField(TEXT("points"), HandCounts);
				HandsObj->SetArrayField(TEXT("pairs"), HandPairs);
				PartsObj->SetObjectField(TEXT("hands"), HandsObj);
				if (HandOver.Num() > 0)
				{
					bOutWarning = true;
					Issues.Add(Issue(TEXT("warning"), TEXT("HAND_PENETRATION"), FString::Printf(TEXT("%d hand/arm pair(s) go deeper than %.1f cm into the other hand/forearm: %s"),
						HandOver.Num(), PenetrationCm, *Summary(HandOver))));
				}
			}
			Out->SetObjectField(TEXT("parts"), PartsObj);

			// ---- per_frame{} — 쌍별 부호 있는 깊이(걸리는 칸이 없으면 null) ----
			if (Spec.bPerFrame)
			{
				auto Series = [Frames](const TArray<FPairHit>& Hits)
				{
					TArray<TSharedPtr<FJsonValue>> Values;
					for (int32 f = 0; f < Frames; ++f)
					{
						Values.Add(Hits[f].bFound ? TSharedPtr<FJsonValue>(MakeShared<FJsonValueNumber>(AnimMcpStats::Round(Hits[f].Depth, 3))) : MakeShared<FJsonValueNull>());
					}
					return Values;
				};
				TSharedRef<FJsonObject> PerFrame = AnimMcpJson::MakeObject();
				PerFrame->SetNumberField(TEXT("frames"), Frames);
				TArray<TSharedPtr<FJsonValue>> Times, SeriesOut;
				for (int32 f = 0; f < Frames; ++f) { Times.Add(MakeShared<FJsonValueNumber>(AnimMcpStats::Round(FrameRate > 0.0 ? f / FrameRate : 0.0, 4))); }
				PerFrame->SetArrayField(TEXT("times"), Times);
				for (int32 s = 0; s < 2; ++s)
				{
					for (int32 p = 0; p < NumArmParts; ++p)
					{
						for (int32 b = 0; b < NumBodyParts; ++b)
						{
							TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
							Item->SetStringField(TEXT("side"), SideNames[s]);
							Item->SetStringField(TEXT("arm_part"), PartNames[p]);
							Item->SetStringField(TEXT("body_part"), BodyPartNames[b]);
							Item->SetArrayField(TEXT("depth"), Series(ArmHits[s][p][b]));
							SeriesOut.Add(MakeShared<FJsonValueObject>(Item));
						}
					}
					if (Spec.bLegs)
					{
						for (int32 p = 0; p < 2; ++p)
						{
							for (int32 b = 0; b < 2; ++b)
							{
								TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
								Item->SetStringField(TEXT("side"), SideNames[s]);
								Item->SetStringField(TEXT("leg_part"), PartNames[p == 0 ? 3 : 4]);
								Item->SetStringField(TEXT("body_part"), FString::Printf(TEXT("%s_%s"), b == 0 ? TEXT("thigh") : TEXT("calf"), SideNames[1 - s]));
								Item->SetArrayField(TEXT("depth"), Series(LegHits[s][p][b]));
								SeriesOut.Add(MakeShared<FJsonValueObject>(Item));
							}
						}
					}
					if (Spec.bHands)
					{
						for (int32 p = 0; p < NumArmParts; ++p)
						{
							for (int32 m = 0; m < 2; ++m)
							{
								TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
								Item->SetStringField(TEXT("side"), SideNames[s]);
								Item->SetStringField(TEXT("arm_part"), PartNames[p]);
								Item->SetStringField(TEXT("body_part"), FString::Printf(TEXT("%s_%s"), m == 0 ? TEXT("hand") : TEXT("forearm"), SideNames[1 - s]));
								Item->SetArrayField(TEXT("depth"), Series(HandHits[s][p][m]));
								SeriesOut.Add(MakeShared<FJsonValueObject>(Item));
							}
						}
					}
				}
				PerFrame->SetArrayField(TEXT("series"), SeriesOut);
				Out->SetObjectField(TEXT("per_frame"), PerFrame);
			}

			// ---- model{} — Python 풀이(anim_gen/body_model.py)용 ----
			if (Spec.bModel)
			{
				// 내보낼 점 — 팔 부위 전부(+ legs 면 넓적다리 · 종아리). 본 = 영향 본 · 역할 본과 그 조상
				struct FExported { int32 Side; const FPoint* Point; };
				TArray<FExported> Exported;
				for (int32 a = 0; a < 2; ++a)
				{
					for (const EGroup Group : { a == 0 ? EGroup::Arm0 : EGroup::Arm1, a == 0 ? EGroup::Upper0 : EGroup::Upper1 })
					{
						for (const FPoint& Point : Model.Points[Slot(Group)])
						{
							if (static_cast<int32>(Point.Part) < NumArmParts) { Exported.Add({ Map.ArmSide[a], &Point }); }
						}
					}
				}
				if (Spec.bLegs)
				{
					for (int32 k = 0; k < 2; ++k)
					{
						for (const FPoint& Point : Core)
						{
							if (Point.Axis == k + 1) { Exported.Add({ Map.LegSide[k], &Point }); }
						}
						for (const FPoint& Point : Calves(k)) { Exported.Add({ Map.LegSide[k], &Point }); }
					}
				}
				TSet<int32> Needed;
				auto Need = [&Needed, &Tree](int32 Bone)
				{
					for (int32 Walk = Bone; Walk != INDEX_NONE && !Needed.Contains(Walk); Walk = Tree.Parents[Walk]) { Needed.Add(Walk); }
				};
				for (const FExported& E : Exported)
				{
					for (int32 k = 0; k < E.Point->Num; ++k) { Need(E.Point->Bones[k]); }
				}
				TArray<int32> Twists[2];
				for (int32 a = 0; a < 2; ++a)
				{
					const FArm& Arm = Map.Arms[a];
					for (const int32 Bone : { Arm.Upper, Arm.Elbow, Arm.Wrist, Tree.Parents[Arm.Upper] }) { if (Bone != INDEX_NONE) { Need(Bone); } }
					for (const int32 Child : Tree.Children(Arm.Upper)) { if (Child != Arm.Elbow) { Twists[a].Add(Child); Need(Child); } }
					for (const int32 Child : Tree.Children(Arm.Elbow)) { if (Child != Arm.Wrist) { Twists[a].Add(Child); Need(Child); } }
				}
				for (const int32 Bone : { Map.Pelvis, Map.SpineTop, Map.NeckRoot, Map.Head, Map.Thighs[0], Map.Thighs[1], Map.Knees[0], Map.Knees[1], Map.Feet[0], Map.Feet[1] })
				{
					if (Bone != INDEX_NONE) { Need(Bone); }
				}
				for (const int32 Bone : Map.SpineRoots) { Need(Bone); }
				TArray<int32> Bones = Needed.Array();
				Bones.Sort();
				TMap<int32, int32> Index;
				for (int32 i = 0; i < Bones.Num(); ++i) { Index.Add(Bones[i], i); }
				auto At = [&Index](int32 Bone) { const int32* Found = Index.Find(Bone); return Found ? *Found : INDEX_NONE; };

				TSharedRef<FJsonObject> ModelObj = AnimMcpJson::MakeObject();
				ModelObj->SetNumberField(TEXT("version"), 1);
				ModelObj->SetStringField(TEXT("mesh"), Mesh->GetPathName());
				ModelObj->SetNumberField(TEXT("scale"), AnimMcpStats::Round(Model.Scale, 6));
				ModelObj->SetNumberField(TEXT("contact_cm"), AnimMcpStats::Round(ContactCm, 6));
				ModelObj->SetNumberField(TEXT("penetration_cm"), AnimMcpStats::Round(PenetrationCm, 6));
				ModelObj->SetNumberField(TEXT("fps"), FrameRate);
				ModelObj->SetNumberField(TEXT("frames_total"), Frames);
				TArray<TSharedPtr<FJsonValue>> FramesOut, TimesOut;
				for (const int32 Frame : ModelFrames)
				{
					FramesOut.Add(MakeShared<FJsonValueNumber>(Frame));
					TimesOut.Add(MakeShared<FJsonValueNumber>(AnimMcpStats::Round(FrameRate > 0.0 ? Frame / FrameRate : 0.0, 6)));
				}
				ModelObj->SetArrayField(TEXT("frames"), FramesOut);
				ModelObj->SetArrayField(TEXT("times"), TimesOut);
				TSharedRef<FJsonObject> BonesObj = AnimMcpJson::MakeObject();
				TArray<TSharedPtr<FJsonValue>> BoneNames, BoneParents;
				for (const int32 Bone : Bones)
				{
					BoneNames.Add(MakeShared<FJsonValueString>(BoneName(Mesh, Bone).ToString()));
					BoneParents.Add(MakeShared<FJsonValueNumber>(At(Tree.Parents[Bone])));
				}
				BonesObj->SetArrayField(TEXT("names"), BoneNames);
				BonesObj->SetArrayField(TEXT("parents"), BoneParents);
				ModelObj->SetObjectField(TEXT("bones"), BonesObj);

				auto NameOf = [Mesh](int32 Bone) { return AnimMcpJson::StringOrNull(Bone == INDEX_NONE ? FString() : BoneName(Mesh, Bone).ToString()); };
				TSharedRef<FJsonObject> Roles = AnimMcpJson::MakeObject();
				TArray<TSharedPtr<FJsonValue>> ArmRoles, LegRoles;
				for (int32 a = 0; a < 2; ++a)
				{
					const FArm& Arm = Map.Arms[a];
					const int32 Clavicle = Tree.Parents[Arm.Upper] != Map.SpineTop ? Tree.Parents[Arm.Upper] : INDEX_NONE;
					TSharedRef<FJsonObject> Role = AnimMcpJson::MakeObject();
					Role->SetStringField(TEXT("side"), SideNames[Map.ArmSide[a]]);
					Role->SetField(TEXT("clavicle"), NameOf(Clavicle));
					Role->SetField(TEXT("upper"), NameOf(Arm.Upper));
					Role->SetField(TEXT("elbow"), NameOf(Arm.Elbow));
					Role->SetField(TEXT("wrist"), NameOf(Arm.Wrist));
					Role->SetArrayField(TEXT("twist"), Names(Mesh, Twists[a]));
					Role->SetNumberField(TEXT("shoulder_exclude_cm"), AnimMcpStats::Round(Model.ShoulderExcludeCm[a], 3));
					if (Spec.bHands)
					{
						if (Model.bHandTip[a]) { Role->SetArrayField(TEXT("hand_tip_local_cm"), VecJson(Model.HandTipLocal[a], 4)); }
						else { Role->SetField(TEXT("hand_tip_local_cm"), MakeShared<FJsonValueNull>()); }
					}
					ArmRoles.Add(MakeShared<FJsonValueObject>(Role));
				}
				for (int32 k = 0; k < 2; ++k)
				{
					TSharedRef<FJsonObject> Role = AnimMcpJson::MakeObject();
					Role->SetStringField(TEXT("side"), SideNames[Map.LegSide[k]]);
					Role->SetField(TEXT("thigh"), NameOf(Map.Thighs[k]));
					Role->SetField(TEXT("knee"), NameOf(Map.Knees[k]));
					Role->SetField(TEXT("foot"), NameOf(Map.Feet[k]));
					LegRoles.Add(MakeShared<FJsonValueObject>(Role));
				}
				Roles->SetArrayField(TEXT("arms"), ArmRoles);
				Roles->SetArrayField(TEXT("legs"), LegRoles);
				Roles->SetField(TEXT("pelvis"), NameOf(Map.Pelvis));
				Roles->SetField(TEXT("spine_top"), NameOf(Map.SpineTop));
				Roles->SetArrayField(TEXT("spine"), Names(Mesh, Map.SpineRoots));
				Roles->SetField(TEXT("neck_root"), NameOf(Model.bHeadAxis ? Map.NeckRoot : INDEX_NONE));
				Roles->SetField(TEXT("head"), NameOf(Model.bHeadAxis ? Map.Head : INDEX_NONE));
				Roles->SetArrayField(TEXT("head_top_local_cm"), VecJson(Model.HeadTopLocal, 4));
				Roles->SetStringField(TEXT("sides_from"), Map.SidesFrom);
				ModelObj->SetObjectField(TEXT("roles"), Roles);

				// 포즈 — 측정과 같은 샘플(메시 기준), 컴포넌트 공간
				TArray<double> PoseValues;
				PoseValues.Reserve(ModelFrames.Num() * Bones.Num() * 10);
				for (const int32 Frame : ModelFrames)
				{
					for (const int32 Bone : Bones)
					{
						const FTransform& X = Poses[Frame][Bone];
						const FQuat Q = X.GetRotation().GetNormalized();
						const FVector L = X.GetLocation(), S = X.GetScale3D();
						PoseValues.Append({ Q.X, Q.Y, Q.Z, Q.W, L.X, L.Y, L.Z, S.X, S.Y, S.Z });
					}
				}
				TSharedRef<FJsonObject> PosesObj = AnimMcpJson::MakeObject();
				PosesObj->SetStringField(TEXT("layout"), TEXT("f32 [frame][bone] qx qy qz qw tx ty tz sx sy sz"));
				const FString PoseB64 = EncodeF32(PoseValues);
				PosesObj->SetStringField(TEXT("b64"), PoseB64);
				ModelObj->SetObjectField(TEXT("poses"), PosesObj);

				// 점 — 측정 점 그대로. 영향마다 그 본 기준 포즈 공간 위치(스킨 = Σ w · 포즈(로컬) — 메시 기준 포즈가 따로 필요 없다)
				TArray<TSharedPtr<FJsonValue>> PointsOut;
				for (const FExported& E : Exported)
				{
					const FPoint& Point = *E.Point;
					TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
					Item->SetStringField(TEXT("side"), SideNames[E.Side]);
					Item->SetStringField(TEXT("part"), PartNames[static_cast<int32>(Point.Part)]);
					Item->SetNumberField(TEXT("dominant"), At(Point.Dominant));
					Item->SetArrayField(TEXT("ref_cm"), VecJson(Point.Position, 4));
					TArray<TSharedPtr<FJsonValue>> Influences;
					for (int32 k = 0; k < Point.Num; ++k)
					{
						const FVector Local = RefInverse[Point.Bones[k]].TransformPosition(Point.Position);
						Influences.Add(MakeShared<FJsonValueArray>(TArray<TSharedPtr<FJsonValue>>{ MakeShared<FJsonValueNumber>(At(Point.Bones[k])),
							MakeShared<FJsonValueNumber>(AnimMcpStats::Round(Point.Weights[k], 7)), MakeShared<FJsonValueNumber>(AnimMcpStats::Round(Local.X, 5)),
							MakeShared<FJsonValueNumber>(AnimMcpStats::Round(Local.Y, 5)), MakeShared<FJsonValueNumber>(AnimMcpStats::Round(Local.Z, 5)) }));
					}
					Item->SetArrayField(TEXT("influences"), Influences);
					PointsOut.Add(MakeShared<FJsonValueObject>(Item));
				}
				ModelObj->SetStringField(TEXT("influence_layout"), TEXT("[bone, weight, local_x, local_y, local_z] — local = that bone's reference-pose space"));
				ModelObj->SetArrayField(TEXT("points"), PointsOut);

				TSharedRef<FJsonObject> TorsoBounds = AnimMcpJson::MakeObject();
				TorsoBounds->SetNumberField(TEXT("belly"), Model.BellyT);
				TorsoBounds->SetNumberField(TEXT("chest"), Model.ChestT);
				ModelObj->SetObjectField(TEXT("torso_t_bounds"), TorsoBounds);
				ModelObj->SetNumberField(TEXT("leg_thigh_t_min"), LegThighTMin);
				int64 Bytes = PoseB64.Len();
				TArray<TSharedPtr<FJsonValue>> MapsJson;
				for (const FMapExport& M : MapsOut)
				{
					TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
					Item->SetStringField(TEXT("part"), M.Part);
					Item->SetNumberField(TEXT("t_min"), M.TMin);
					Item->SetNumberField(TEXT("t_max"), M.TMax);
					Item->SetNumberField(TEXT("t_bins"), M.TBins);
					Item->SetNumberField(TEXT("angle_bins"), AngleBins);
					if (M.Part == TEXT("torso"))
					{
						TArray<TSharedPtr<FJsonValue>> Labels;
						for (int32 T = 0; T < M.TBins; ++T)
						{
							Labels.Add(MakeShared<FJsonValueString>(TorsoPart(M.TMin + (T + 0.5) / M.TBins * (M.TMax - M.TMin), Model.BellyT, Model.ChestT)));
						}
						Item->SetArrayField(TEXT("part_of_t_bin"), Labels);
					}
					const FString AxisB64 = EncodeF32(M.Axis);
					const FString RadiusB64 = EncodeI16(M.Radius, RadiusUnitCm);
					Bytes += AxisB64.Len() + RadiusB64.Len();
					Item->SetStringField(TEXT("axis_layout"), TEXT("f32 [frame] ax ay az dx dy dz xx xy xz length (length 0 = no axis)"));
					Item->SetStringField(TEXT("axis_b64"), AxisB64);
					Item->SetNumberField(TEXT("radius_unit_cm"), RadiusUnitCm);
					Item->SetStringField(TEXT("radius_layout"), TEXT("i16 [frame][t][angle], -32768 = empty (reader applies the 3x3 neighbour rule)"));
					Item->SetStringField(TEXT("radius_b64"), RadiusB64);
					MapsJson.Add(MakeShared<FJsonValueObject>(Item));
				}
				ModelObj->SetArrayField(TEXT("maps"), MapsJson);
				ModelObj->SetNumberField(TEXT("b64_bytes"), static_cast<double>(Bytes));
				ModelObj->SetNumberField(TEXT("seconds"), AnimMcpStats::Round(FPlatformTime::Seconds() - StartSeconds));
				Out->SetObjectField(TEXT("model"), ModelObj);
			}
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
			else if (Key == TEXT("parts"))
			{
				if (!V.IsValid() || V->Type != EJson::String || (V->AsString() != TEXT("arms") && V->AsString() != TEXT("all")))
				{
					return Bad(Key, FString::Printf(TEXT("%s.parts must be \"arms\" (default — arms[] only) or \"all\" (hand/forearm/upper arm × pelvis/belly/chest/thighs/head_neck pairs)"), Field));
				}
				Out.bAllParts = V->AsString() == TEXT("all");
			}
			else if (Key == TEXT("legs") || Key == TEXT("per_frame") || Key == TEXT("hands"))
			{
				if (!V.IsValid() || V->Type != EJson::Boolean) { return Bad(Key, FString::Printf(TEXT("%s.%s must be a boolean"), Field, *Key)); }
				(Key == TEXT("legs") ? Out.bLegs : Key == TEXT("hands") ? Out.bHands : Out.bPerFrame) = V->AsBool();
			}
			else if (Key == TEXT("model"))
			{
				const TSharedPtr<FJsonObject>* ModelObj = nullptr;
				if (V.IsValid() && V->Type == EJson::Boolean)
				{
					Out.bModel = V->AsBool();
				}
				else if (V.IsValid() && V->TryGetObject(ModelObj))
				{
					Out.bModel = true;
					for (const TPair<FString, TSharedPtr<FJsonValue>>& M : (*ModelObj)->Values)
					{
						if (M.Key != TEXT("stride")) { return Bad(Key, FString::Printf(TEXT("%s.model.%s is unknown (stride)"), Field, *M.Key)); }
						const double Stride = M.Value.IsValid() && M.Value->Type == EJson::Number ? M.Value->AsNumber() : -1.0;
						if (Stride < 1.0 || Stride > MaxModelStride || Stride != FMath::FloorToDouble(Stride))
						{
							return Bad(Key, FString::Printf(TEXT("%s.model.stride must be an integer 1..%d (frames between exported poses)"), Field, MaxModelStride));
						}
						Out.ModelStride = static_cast<int32>(Stride);
					}
				}
				else
				{
					return Bad(Key, FString::Printf(TEXT("%s.model must be a boolean or {stride}"), Field));
				}
			}
			else
			{
				TArray<FString> Allowed = { TEXT("mesh"), TEXT("ik_rig"), TEXT("upper_arms"), TEXT("body_bones"), TEXT("include_secondary"), TEXT("contact_cm"), TEXT("penetration_cm"),
					TEXT("parts"), TEXT("legs"), TEXT("hands"), TEXT("per_frame"), TEXT("model") };
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
		if (Spec.NeedsParts())
		{
			// 부위 쌍 · 프레임 깊이 · 몸 모델 (8-4a) — 위 arms[] · body 와 따로 돈다
			MeasureParts(Mesh, Model, Spec, Poses, RefInverse, FrameRate, ContactCm, PenetrationCm, Out, Issues, bOutWarning);
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
		if (OutSpec.bPerFrame || OutSpec.bModel)
		{
			return Bad(OutSpec.bModel ? TEXT("model") : TEXT("per_frame"), FString::Printf(TEXT("%s.per_frame / model are validate_animation body_clearance only"), Field));
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

	void FRadialAxis::Init(const FVector& InA, const FVector& InB, const FVector& Lateral, double InTMin, double InTMax, int32 InTBins)
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

	bool FRadialAxis::Locate(const FVector& P, int32& OutT, int32& OutAngle, FVector& OutRadial) const
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

	void FRadialAxis::Add(const FVector& P, int32 Index)
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

	double FRadialAxis::Radius(int32 T, int32 Angle, int32& OutWho) const
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

	void FArmAxes::Init(const FVector& Elbow, const FVector& Wrist, const FVector& InHandTip, const FVector& Lateral)
	{
		Hand = FRadialAxis();
		Forearm = FRadialAxis();
		Hand.Init(Wrist, InHandTip, Lateral, HandTMin, HandTMax, HandBins);
		Forearm.Init(Elbow, Wrist, Lateral, ForearmTMin, ForearmTMax, ForearmBins);
	}

	FVector HandTip(const TArray<FVector>& HandPoints, const FVector& Elbow, const FVector& Wrist)
	{
		if (HandPoints.Num() == 0)
		{
			return Wrist;
		}
		FVector Centroid = FVector::ZeroVector;
		for (const FVector& P : HandPoints) { Centroid += P; }
		Centroid /= HandPoints.Num();
		FVector Dir = Centroid - Wrist;
		if (Dir.Size() <= MinSegmentCm) { Dir = Wrist - Elbow; }
		Dir = Dir.GetSafeNormal();
		if (Dir.IsNearlyZero())
		{
			return Wrist;
		}
		double Reach = 0.0;
		for (const FVector& P : HandPoints) { Reach = FMath::Max(Reach, FVector::DotProduct(P - Wrist, Dir)); }
		return Wrist + Dir * Reach;
	}

	const TCHAR* TorsoPart(double T, double BellyT, double ChestT)
	{
		return BodyPartNames[TorsoPartIndex(T, BellyT, ChestT)];
	}

	FString EncodeI16(const TArray<double>& Values, double Unit)
	{
		TArray<uint8> Bytes;
		Bytes.Reserve(Values.Num() * 2);
		for (const double Value : Values)
		{
			const int16 Q = Value < 0.0 ? EmptyRadiusI16 : static_cast<int16>(FMath::Clamp<int64>(FMath::RoundToInt64(Value / Unit), 0, 32767));
			const uint16 U = static_cast<uint16>(Q);
			Bytes.Add(static_cast<uint8>(U & 0xFF));
			Bytes.Add(static_cast<uint8>(U >> 8));
		}
		return FBase64::Encode(Bytes);
	}

	FString EncodeF32(const TArray<double>& Values)
	{
		TArray<uint8> Bytes;
		Bytes.SetNumUninitialized(Values.Num() * 4);
		for (int32 i = 0; i < Values.Num(); ++i)
		{
			const float F = static_cast<float>(Values[i]);
			uint32 U;
			FMemory::Memcpy(&U, &F, 4);
			for (int32 b = 0; b < 4; ++b) { Bytes[i * 4 + b] = static_cast<uint8>((U >> (8 * b)) & 0xFF); }
		}
		return FBase64::Encode(Bytes);
	}
}
