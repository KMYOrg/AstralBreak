#include "AnimMcpFingerChains.h"

#include "Algo/AllOf.h"
#include "AnimMcpAssetResolver.h"
#include "AnimMcpStats.h"
#include "Animation/Skeleton.h"
#include "Bridge/AnimMcpTypes.h"
#include "Engine/SkeletalMesh.h"
#include "ReferenceSkeleton.h"
#include "RetargetEditor/IKRetargeterController.h"
#include "Retargeter/IKRetargeter.h"
#include "Retargeter/RetargetOps/FKChainsOp.h"
#include "Rig/IKRigDefinition.h"

namespace AnimMcpFingerChains
{
	using AnimMcpSkeletonGeometry::FNamedChain;
	using AnimMcpSkeletonGeometry::FTree;

	namespace
	{
		/** 메타카팔 뒤 손가락 · 엄지 마디 수 — 넘는 잎 쪽 관절은 끝점(SOMA End · Mixamo Index4) */
		constexpr int32 MaxPhalanges = 3;
		/** 위상으로 손을 찾을 때 손가락 사슬 최소 수 */
		constexpr int32 MinChainsForHand = 3;
		constexpr double ThumbAmbiguousDeg = 3.0;
		/** 최소 구간 길이 배율의 기준 키 (cm) */
		constexpr double ReferenceHeightCm = 170.0;

		constexpr int32 NumNonThumb = 4;
		const EFinger NonThumb[NumNonThumb] = { EFinger::Index, EFinger::Middle, EFinger::Ring, EFinger::Pinky };

		double AngleDeg(const FVector& A, const FVector& B)
		{
			return FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(FVector::DotProduct(A.GetSafeNormal(), B.GetSafeNormal()), -1.0, 1.0)));
		}

		/** 손가락 사슬 구간 하한 — MinSegmentCm × 키 / 170 (길이 0 인 무기 제약 사슬 · 손목과 같은 자리의 본을 거른다) */
		double MinSegment(const FTree& Tree)
		{
			double Floor = 0.0, Top = 0.0;
			const double Height = AnimMcpSkeletonGeometry::VerticalRange(Tree, Floor, Top) ? Top - Floor : ReferenceHeightCm;
			return AnimMcpSkeletonGeometry::MinSegmentCm * FMath::Clamp(Height / ReferenceHeightCm, 0.25, 4.0);
		}

		/** Start 에서 가장 깊은 자식(Height 최대, 같으면 앞 번호)을 따라 잎까지 */
		TArray<int32> LinearChain(const FTree& Tree, int32 Start)
		{
			TArray<int32> Out = { Start };
			for (;;)
			{
				int32 Best = INDEX_NONE;
				for (const int32 Child : Tree.Children(Out.Last()))
				{
					if (Best == INDEX_NONE || Tree.Height[Child] > Tree.Height[Best]) { Best = Child; }
				}
				if (Best == INDEX_NONE)
				{
					return Out;
				}
				Out.Add(Best);
			}
		}

		/** 손 본 바로 아래 자식마다 사슬 — 2관절 이상, 사슬 안 구간이 모두 MinSeg 이상(잎 본 · 길이 0 제약 사슬은 손가락이 아니다) */
		TArray<TArray<int32>> FingerChainsUnder(const FTree& Tree, int32 Hand, double MinSeg)
		{
			TArray<TArray<int32>> Out;
			for (const int32 Child : Tree.Children(Hand))
			{
				TArray<int32> Chain = LinearChain(Tree, Child);
				if (Chain.Num() < 2)
				{
					continue;
				}
				bool bOk = true;
				for (int32 i = 0; i + 1 < Chain.Num() && bOk; ++i)
				{
					bOk = FVector::Dist(Tree.Pos(Chain[i + 1]), Tree.Pos(Chain[i])) >= MinSeg;
				}
				if (bOk)
				{
					Out.Add(MoveTemp(Chain));
				}
			}
			return Out;
		}

		/** 두 손의 손가락 시작들이 두 손 본의 수직이등분면에 비춰 서로 겹치는가 (거울 짝 판정과 같은 허용 오차, 좌우축 수평) */
		bool HandsMirror(const FTree& Tree, int32 A, int32 B, const TArray<TArray<int32>>& ChainsA, const TArray<TArray<int32>>& ChainsB, double MinSeg)
		{
			const FVector PA = Tree.Pos(A), PB = Tree.Pos(B);
			const double Separation = FVector::Dist(PA, PB);
			if (Separation < MinSeg)
			{
				return false;
			}
			const FVector Axis = (PA - PB) / Separation;
			if (FMath::Abs(Axis.Z) > 0.5)
			{
				return false;
			}
			const FVector Center = (PA + PB) * 0.5;
			const double Tolerance = FMath::Max(MinSeg, AnimMcpSkeletonGeometry::MirrorToleranceRatio * Separation);
			const TArray<TArray<int32>>& Fewer = ChainsA.Num() <= ChainsB.Num() ? ChainsA : ChainsB;
			const TArray<TArray<int32>>& More = ChainsA.Num() <= ChainsB.Num() ? ChainsB : ChainsA;
			for (const TArray<int32>& Chain : Fewer)
			{
				const FVector P = Tree.Pos(Chain[0]) - Center;
				const FVector Reflected = P - 2.0 * FVector::DotProduct(P, Axis) * Axis;
				const bool bMatch = More.ContainsByPredicate([&](const TArray<int32>& Other) { return FVector::Dist(Reflected, Tree.Pos(Other[0]) - Center) <= Tolerance; });
				if (!bMatch)
				{
					return false;
				}
			}
			return true;
		}

		FString SideFromName(FName Name)
		{
			const FString S = Name.ToString();
			if (S.StartsWith(TEXT("Left"), ESearchCase::IgnoreCase)) { return TEXT("Left"); }
			if (S.StartsWith(TEXT("Right"), ESearchCase::IgnoreCase)) { return TEXT("Right"); }
			return FString();
		}

		/** 손 하나 — 엄지 · 측면 순서 · 메타카팔 · 끝점 (헤더 규칙) */
		FHand Classify(const FTree& Tree, int32 HandBone, double MinSeg)
		{
			FHand Hand;
			Hand.Bone = HandBone;
			const TArray<TArray<int32>> Chains = FingerChainsUnder(Tree, HandBone, MinSeg);
			if (Chains.Num() < 2)
			{
				Hand.Issues.Add(TEXT("TOO_FEW_FINGER_CHAINS"));
				return Hand;
			}
			const FVector Wrist = Tree.Pos(HandBone);
			TArray<FVector> Dirs;
			for (const TArray<int32>& Chain : Chains) { Dirs.Add((Tree.Pos(Chain.Last()) - Tree.Pos(Chain[0])).GetSafeNormal()); }
			// 엄지 = 다른 사슬 평균 방향에서 가장 벗어난 사슬
			TArray<double> Deviation;
			for (int32 i = 0; i < Chains.Num(); ++i)
			{
				FVector Others = FVector::ZeroVector;
				for (int32 j = 0; j < Chains.Num(); ++j) { if (j != i) { Others += Dirs[j]; } }
				Deviation.Add(AngleDeg(Dirs[i], Others));
			}
			int32 Thumb = 0;
			for (int32 i = 1; i < Chains.Num(); ++i) { if (Deviation[i] > Deviation[Thumb]) { Thumb = i; } }
			double Second = -1.0;
			for (int32 i = 0; i < Chains.Num(); ++i) { if (i != Thumb) { Second = FMath::Max(Second, Deviation[i]); } }
			Hand.ThumbMarginDeg = Deviation[Thumb] - Second;
			if (Hand.ThumbMarginDeg < ThumbAmbiguousDeg)
			{
				Hand.Issues.Add(TEXT("THUMB_AMBIGUOUS"));
			}

			// 메타카팔 = 첫 관절이 자기 구간 길이보다 손목에 가깝다
			auto IsMetacarpal = [&Tree, &Wrist](const TArray<int32>& Chain)
			{
				return FVector::Dist(Tree.Pos(Chain[0]), Wrist) < FVector::Dist(Tree.Pos(Chain[1]), Tree.Pos(Chain[0]));
			};
			TArray<int32> Rest;
			TArray<FVector> Knuckles;
			for (int32 i = 0; i < Chains.Num(); ++i)
			{
				if (i == Thumb) { continue; }
				Rest.Add(i);
				Knuckles.Add(Tree.Pos(Chains[i][IsMetacarpal(Chains[i]) ? 1 : 0]));
			}
			FVector Mean = FVector::ZeroVector;
			for (const FVector& K : Knuckles) { Mean += K; }
			Mean /= Knuckles.Num();
			const FVector X = (Mean - Wrist).GetSafeNormal();
			// 측면축 = 너클을 X 에 수직인 평면에 투영한 주축(거듭제곱법), 엄지 시작 쪽이 +
			TArray<FVector> Projected;
			for (const FVector& K : Knuckles)
			{
				const FVector P = K - Mean;
				Projected.Add(P - X * FVector::DotProduct(P, X));
			}
			FVector Lateral = (Projected[0] - Projected.Last()).GetSafeNormal();
			if (Lateral.IsNearlyZero())
			{
				Lateral = FVector::CrossProduct(X, FVector::UpVector).GetSafeNormal();
			}
			for (int32 Iteration = 0; Iteration < 50; ++Iteration)
			{
				FVector Next = FVector::ZeroVector;
				for (const FVector& P : Projected) { Next += P * FVector::DotProduct(P, Lateral); }
				if (Next.SizeSquared() < 1e-12) { break; }
				Lateral = Next.GetSafeNormal();
			}
			if (FVector::DotProduct(Tree.Pos(Chains[Thumb][0]) - Mean, Lateral) < 0.0)
			{
				Lateral = -Lateral;
			}
			TArray<int32> Order;
			for (int32 k = 0; k < Rest.Num(); ++k) { Order.Add(k); }
			Order.Sort([&](int32 A, int32 B) { return FVector::DotProduct(Knuckles[A] - Mean, Lateral) > FVector::DotProduct(Knuckles[B] - Mean, Lateral); });

			auto Take = [](const TArray<int32>& Chain, int32 First, FFinger& Out)
			{
				for (int32 i = First; i < Chain.Num(); ++i) { (Out.Bones.Num() < MaxPhalanges ? Out.Bones : Out.Tips).Add(Chain[i]); }
			};
			FFinger ThumbFinger;
			ThumbFinger.Finger = EFinger::Thumb;
			Take(Chains[Thumb], 0, ThumbFinger);
			Hand.Fingers.Add(ThumbFinger);
			if (Rest.Num() != NumNonThumb)
			{
				Hand.Issues.Add(FString::Printf(TEXT("FINGER_COUNT_%d"), Rest.Num() + 1));
			}
			for (int32 k = 0; k < Order.Num() && k < NumNonThumb; ++k)
			{
				const TArray<int32>& Chain = Chains[Rest[Order[k]]];
				FFinger Finger;
				Finger.Finger = NonThumb[k];
				const bool bMetacarpal = IsMetacarpal(Chain);
				if (bMetacarpal) { Finger.Metacarpal = Chain[0]; }
				Take(Chain, bMetacarpal ? 1 : 0, Finger);
				Hand.Fingers.Add(Finger);
			}
			return Hand;
		}

		/** 메타카팔(있으면) + 마디 — 거울 판정 · 검사용 */
		TArray<int32> AllBones(const FFinger& Finger)
		{
			TArray<int32> Out;
			if (Finger.Metacarpal != INDEX_NONE) { Out.Add(Finger.Metacarpal); }
			Out.Append(Finger.Bones);
			return Out;
		}

		TSharedRef<FJsonObject> ChainJson(const FName Name, const FName Start, const FName End)
		{
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetStringField(TEXT("name"), Name.ToString());
			Obj->SetStringField(TEXT("start"), Start.ToString());
			Obj->SetStringField(TEXT("end"), End.ToString());
			return Obj;
		}

		TArray<TSharedPtr<FJsonValue>> Strings(const TArray<FString>& Values)
		{
			TArray<TSharedPtr<FJsonValue>> Out;
			for (const FString& V : Values) { Out.Add(MakeShared<FJsonValueString>(V)); }
			return Out;
		}

		TSharedPtr<FJsonValue> Range(const TArray<double>& Values)
		{
			if (Values.Num() == 0)
			{
				return MakeShared<FJsonValueNull>();
			}
			TSharedRef<FJsonObject> Obj = AnimMcpJson::MakeObject();
			Obj->SetNumberField(TEXT("min"), AnimMcpStats::Round(FMath::Min(Values), 2));
			Obj->SetNumberField(TEXT("p50"), AnimMcpStats::Round(AnimMcpStats::Percentile(Values, 50.0), 2));
			Obj->SetNumberField(TEXT("max"), AnimMcpStats::Round(FMath::Max(Values), 2));
			return MakeShared<FJsonValueObject>(Obj);
		}
	}

	const TCHAR* FingerName(EFinger Finger)
	{
		switch (Finger)
		{
		case EFinger::Thumb: return TEXT("Thumb");
		case EFinger::Index: return TEXT("Index");
		case EFinger::Middle: return TEXT("Middle");
		case EFinger::Ring: return TEXT("Ring");
		default: return TEXT("Pinky");
		}
	}

	FName StandardChainName(const FString& Side, EFinger Finger, bool bMetacarpal)
	{
		return FName(*FString::Printf(TEXT("%s%s%s"), *Side, FingerName(Finger), bMetacarpal ? TEXT("Metacarpal") : TEXT("")));
	}

	FHands FindHands(const FTree& Tree, const TArray<FNamedChain>& Chains)
	{
		FHands Out;
		const double MinSeg = MinSegment(Tree);
		TArray<TArray<int32>> ChainBones;
		for (const FNamedChain& Chain : Chains) { ChainBones.Add(Chain.Bones); }
		int32 ArmA = INDEX_NONE, ArmB = INDEX_NONE, LegA = INDEX_NONE, LegB = INDEX_NONE;
		AnimMcpSkeletonGeometry::PickLimbs(ChainBones, Tree, ArmA, ArmB, LegA, LegB);

		TArray<int32> HandBones;
		TArray<FString> NamedSides;
		if (ArmA != INDEX_NONE)
		{
			// 팔 체인 끝 본 — 그 자손 중 손가락 사슬이 더 많은 본이 있으면 그 본(팔 체인이 위팔에서 끝나는 리그)
			Out.HandsFrom = TEXT("arm_chains");
			for (const int32 Arm : { ArmA, ArmB })
			{
				const int32 End = Chains[Arm].Bones.Last();
				int32 Best = End;
				int32 BestCount = FingerChainsUnder(Tree, End, MinSeg).Num();
				for (int32 Bone = End + 1; Bone < Tree.Num(); ++Bone)
				{
					if (!Tree.IsAncestor(End, Bone)) { continue; }
					const int32 Count = FingerChainsUnder(Tree, Bone, MinSeg).Num();
					if (Count > BestCount)
					{
						Best = Bone;
						BestCount = Count;
					}
				}
				HandBones.Add(Best);
				NamedSides.Add(SideFromName(Chains[Arm].Name));
			}
		}
		else
		{
			// 팔 체인이 없다(자동 캐릭터라이즈 실패 · 인자 없음) — 손가락 사슬 3개 이상인 본 중 서로 거울인 가장 먼 짝
			Out.HandsFrom = TEXT("topology");
			TArray<int32> Candidates;
			TArray<TArray<TArray<int32>>> CandidateChains;
			for (int32 Bone = 0; Bone < Tree.Num(); ++Bone)
			{
				TArray<TArray<int32>> Fingers = FingerChainsUnder(Tree, Bone, MinSeg);
				if (Fingers.Num() >= MinChainsForHand)
				{
					Candidates.Add(Bone);
					CandidateChains.Add(MoveTemp(Fingers));
				}
			}
			int32 BestA = INDEX_NONE, BestB = INDEX_NONE;
			double BestSeparation = 0.0;
			for (int32 a = 0; a < Candidates.Num(); ++a)
			{
				for (int32 b = a + 1; b < Candidates.Num(); ++b)
				{
					const double Separation = FVector::Dist(Tree.Pos(Candidates[a]), Tree.Pos(Candidates[b]));
					if (Separation > BestSeparation && HandsMirror(Tree, Candidates[a], Candidates[b], CandidateChains[a], CandidateChains[b], MinSeg))
					{
						BestA = a;
						BestB = b;
						BestSeparation = Separation;
					}
				}
			}
			if (BestA == INDEX_NONE)
			{
				Out.SkippedReason = TEXT("NO_HANDS");
				return Out;
			}
			HandBones = { Candidates[BestA], Candidates[BestB] };
		}

		// 좌우 — 팔 체인 이름이 서로 다른 쪽을 말하면 그대로, 아니면 발 영역 정면의 −90° 쪽이 왼쪽(UE: +Y 정면 → +X 왼쪽)
		TArray<FString> Sides;
		if (NamedSides.Num() == 2 && !NamedSides[0].IsEmpty() && !NamedSides[1].IsEmpty() && NamedSides[0] != NamedSides[1])
		{
			Sides = NamedSides;
			Out.SideFrom = TEXT("chain_names");
		}
		else
		{
			FVector Facing;
			if (AnimMcpSkeletonGeometry::FeetFacing(Tree, Facing))
			{
				const FVector Left(Facing.Y, -Facing.X, 0.0);
				const FVector Mid = (Tree.Pos(HandBones[0]) + Tree.Pos(HandBones[1])) * 0.5;
				for (const int32 Hand : HandBones) { Sides.Add(FVector::DotProduct(Tree.Pos(Hand) - Mid, Left) > 0.0 ? TEXT("Left") : TEXT("Right")); }
				if (Sides[0] == Sides[1]) { Sides.Reset(); }
				else { Out.SideFrom = TEXT("facing"); }
			}
		}
		if (Sides.Num() != 2)
		{
			Out.SkippedReason = TEXT("SIDE_UNKNOWN");
			Sides = { FString(), FString() };
		}
		for (int32 k = 0; k < 2; ++k)
		{
			FHand Hand = Classify(Tree, HandBones[k], MinSeg);
			Hand.Side = Sides[k];
			Out.Hands.Add(MoveTemp(Hand));
		}
		// 왼손 먼저 (출력 순서 고정)
		if (Out.Hands[0].Side == TEXT("Right")) { Out.Hands.Swap(0, 1); }
		return Out;
	}

	TArray<FGivenChain> GivenChains(const FReferenceSkeleton& Ref, const AnimMcpSkeletonGeometry::FChainSource& Source)
	{
		TArray<FGivenChain> Out;
		for (const FNamedChain& Chain : Source.Chains)
		{
			if (Chain.Bones.Num() > 0) { Out.Add({ Chain.Name, Ref.GetBoneName(Chain.Bones[0]), Ref.GetBoneName(Chain.Bones.Last()) }); }
		}
		return Out;
	}

	FSuggestion Suggest(const FReferenceSkeleton& Ref, const FTree& Tree, const AnimMcpSkeletonGeometry::FChainSource& Source, const TArray<FGivenChain>& Given)
	{
		FSuggestion Out;
		const FHands Hands = FindHands(Tree, Source.Chains);
		TSharedRef<FJsonObject> Json = Out.Json;
		Json->SetStringField(TEXT("hands_from"), Hands.HandsFrom);
		Json->SetStringField(TEXT("side_from"), Hands.SideFrom);
		Json->SetStringField(TEXT("chains_from"), Source.From);
		if (!Hands.SkippedReason.IsEmpty())
		{
			Json->SetStringField(TEXT("skipped_reason"), Hands.SkippedReason);
		}
		TArray<TSharedPtr<FJsonValue>> HandsOut, ChainsOut;
		struct FProposed
		{
			FName Name;
			FName Start;
			FName End;
		};
		TArray<FProposed> Proposed;
		for (const FHand& Hand : Hands.Hands)
		{
			TSharedRef<FJsonObject> HandObj = AnimMcpJson::MakeObject();
			HandObj->SetStringField(TEXT("side"), Hand.Side);
			HandObj->SetStringField(TEXT("hand"), Ref.GetBoneName(Hand.Bone).ToString());
			HandObj->SetNumberField(TEXT("fingers"), Hand.Fingers.Num());
			HandObj->SetNumberField(TEXT("thumb_margin_deg"), AnimMcpStats::Round(Hand.ThumbMarginDeg, 1));
			TArray<FString> Tips;
			for (const FFinger& Finger : Hand.Fingers)
			{
				for (const int32 Tip : Finger.Tips) { Tips.Add(Ref.GetBoneName(Tip).ToString()); }
				if (Hand.Side.IsEmpty() || Finger.Bones.Num() == 0) { continue; }
				if (Finger.Metacarpal != INDEX_NONE)
				{
					const FName Bone = Ref.GetBoneName(Finger.Metacarpal);
					Proposed.Add({ StandardChainName(Hand.Side, Finger.Finger, true), Bone, Bone });
				}
				Proposed.Add({ StandardChainName(Hand.Side, Finger.Finger, false), Ref.GetBoneName(Finger.Bones[0]), Ref.GetBoneName(Finger.Bones.Last()) });
			}
			HandObj->SetArrayField(TEXT("tips_excluded"), Strings(Tips));
			HandObj->SetArrayField(TEXT("issues"), Strings(Hand.Issues));
			HandsOut.Add(MakeShared<FJsonValueObject>(HandObj));
		}
		for (const FProposed& P : Proposed)
		{
			ChainsOut.Add(MakeShared<FJsonValueObject>(ChainJson(P.Name, P.Start, P.End)));
			const FGivenChain* Same = Given.FindByPredicate([&P](const FGivenChain& G) { return G.Name == P.Name; });
			if (!Same)
			{
				Out.Missing.Add(MakeShared<FJsonValueObject>(ChainJson(P.Name, P.Start, P.End)));
			}
			else if (Same->Start != P.Start || Same->End != P.End)
			{
				TSharedRef<FJsonObject> Differ = AnimMcpJson::MakeObject();
				Differ->SetStringField(TEXT("name"), P.Name.ToString());
				TSharedRef<FJsonObject> GivenObj = AnimMcpJson::MakeObject();
				GivenObj->SetStringField(TEXT("start"), Same->Start.ToString());
				GivenObj->SetStringField(TEXT("end"), Same->End.ToString());
				TSharedRef<FJsonObject> SuggestedObj = AnimMcpJson::MakeObject();
				SuggestedObj->SetStringField(TEXT("start"), P.Start.ToString());
				SuggestedObj->SetStringField(TEXT("end"), P.End.ToString());
				Differ->SetObjectField(TEXT("given"), GivenObj);
				Differ->SetObjectField(TEXT("suggested"), SuggestedObj);
				Out.Differs.Add(MakeShared<FJsonValueObject>(Differ));
			}
		}
		Out.NumChains = Proposed.Num();
		Json->SetArrayField(TEXT("hands"), HandsOut);
		Json->SetArrayField(TEXT("chains"), ChainsOut);
		Json->SetArrayField(TEXT("missing"), Out.Missing);
		Json->SetArrayField(TEXT("differs"), Out.Differs);

		// 좌우 같은 손가락끼리 거울인가 — 다르면 위상 · 순서 판정이 한쪽에서 틀렸을 수 있다
		TArray<TSharedPtr<FJsonValue>> Mirrored;
		TArray<FString> NotMirrored;
		if (Hands.Hands.Num() == 2 && !Hands.Hands[0].Side.IsEmpty())
		{
			for (const FFinger& L : Hands.Hands[0].Fingers)
			{
				const FFinger* R = Hands.Hands[1].Find(L.Finger);
				if (!R) { continue; }
				const FName LeftName = StandardChainName(Hands.Hands[0].Side, L.Finger, false);
				if (AnimMcpSkeletonGeometry::IsMirror(AllBones(L), AllBones(*R), Tree))
				{
					Mirrored.Add(MakeShared<FJsonValueArray>(Strings({ LeftName.ToString(), StandardChainName(Hands.Hands[1].Side, L.Finger, false).ToString() })));
				}
				else
				{
					NotMirrored.Add(LeftName.ToString());
				}
			}
		}
		Json->SetArrayField(TEXT("mirrored"), Mirrored);
		Json->SetArrayField(TEXT("not_mirrored"), Strings(NotMirrored));
		return Out;
	}

	bool ParseSpec(const TSharedPtr<FJsonValue>& Value, const TCHAR* Field, FCheckSpec& Out, bool& bOutEnabled, FAnimMcpError& OutError)
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
			return Bad(FString(), FString::Printf(TEXT("%s must be a boolean or an object"), Field));
		}
		bOutEnabled = true;
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*Object)->Values)
		{
			UClass* Class = Pair.Key == TEXT("ik_rig") ? UIKRigDefinition::StaticClass() : Pair.Key == TEXT("retargeter") ? UIKRetargeter::StaticClass()
				: Pair.Key == TEXT("mesh") ? USkeletalMesh::StaticClass() : nullptr;
			if (!Class)
			{
				return Bad(Pair.Key, FString::Printf(TEXT("%s.%s is unknown (ik_rig, retargeter, mesh)"), Field, *Pair.Key));
			}
			if (!Pair.Value.IsValid() || Pair.Value->Type != EJson::String || Pair.Value->AsString().IsEmpty())
			{
				return Bad(Pair.Key, FString::Printf(TEXT("%s.%s must be an asset path"), Field, *Pair.Key));
			}
			UObject* Asset = AnimMcpAssetResolver::LoadAssetOfClass(Pair.Value->AsString(), Class, OutError);
			if (!Asset)
			{
				return false;
			}
			if (Class == UIKRigDefinition::StaticClass()) { Out.Rig = Cast<UIKRigDefinition>(Asset); }
			else if (Class == UIKRetargeter::StaticClass()) { Out.Retargeter = Cast<UIKRetargeter>(Asset); }
			else { Out.Mesh = Cast<USkeletalMesh>(Asset); }
		}
		return true;
	}

	double SignedBendDeg(const FVector& Prev, const FVector& Joint, const FVector& Next, const FVector& BendAxis)
	{
		const FVector D0 = (Joint - Prev).GetSafeNormal(), D1 = (Next - Joint).GetSafeNormal();
		const FVector Axis = FVector::CrossProduct(D0, D1);
		if (Axis.SizeSquared() < 1e-12)
		{
			return 0.0;
		}
		const double Angle = AngleDeg(D0, D1);
		return FVector::DotProduct(Axis, BendAxis) >= 0.0 ? Angle : -Angle;
	}

	TSharedRef<FJsonObject> Check(const USkeleton* Skeleton, const TArray<FName>& Bones, const TArray<TArray<FTransform>>& Component, const FCheckSpec& Spec, bool& bOutWarning)
	{
		bOutWarning = false;
		TSharedRef<FJsonObject> Out = AnimMcpJson::MakeObject();
		TArray<TSharedPtr<FJsonValue>> Issues;
		auto Issue = [&Issues, &bOutWarning](const TCHAR* Level, const TCHAR* Code, const FString& Message, TSharedPtr<FJsonObject> Extra = nullptr)
		{
			TSharedRef<FJsonObject> Item = Extra.IsValid() ? Extra.ToSharedRef() : AnimMcpJson::MakeObject();
			Item->SetStringField(TEXT("level"), Level);
			Item->SetStringField(TEXT("code"), Code);
			Item->SetStringField(TEXT("message"), Message);
			Issues.Add(MakeShared<FJsonValueObject>(Item));
			bOutWarning |= FCString::Strcmp(Level, TEXT("warning")) == 0;
		};
		auto Skip = [&](const FString& Why)
		{
			Out->SetStringField(TEXT("skipped_reason"), Why);
			Issue(TEXT("info"), TEXT("FINGERS_SKIPPED"), FString::Printf(TEXT("finger check skipped (%s)"), *Why));
			Out->SetArrayField(TEXT("issues"), Issues);
			return Out;
		};
		if (!Skeleton || Component.Num() == 0)
		{
			return Skip(TEXT("NO_POSE"));
		}
		// 기준 포즈 = 리타깃이 쓴 대상 메시의 것(헤더 FCheckSpec::Mesh) — 본은 이름으로 포즈 열과 맞춘다
		const USkeletalMesh* RefMesh = Spec.Mesh ? Spec.Mesh : (Spec.Retargeter ? Spec.Retargeter->GetPreviewMesh(ERetargetSourceOrTarget::Target) : nullptr);
		if (RefMesh && RefMesh->GetSkeleton() != Skeleton)
		{
			RefMesh = nullptr;
		}
		const FReferenceSkeleton& Ref = RefMesh ? RefMesh->GetRefSkeleton() : Skeleton->GetReferenceSkeleton();
		FTree Tree;
		Tree.Init(Ref);
		const UIKRigDefinition* Rig = Spec.Rig ? Spec.Rig : (Spec.Retargeter ? Spec.Retargeter->GetIKRig(ERetargetSourceOrTarget::Target) : nullptr);
		const AnimMcpSkeletonGeometry::FChainSource Source = AnimMcpSkeletonGeometry::ResolveChains(Rig ? nullptr : Skeleton->GetPreviewMesh(), Rig, Ref, Tree);
		const FHands Hands = FindHands(Tree, Source.Chains);
		Out->SetStringField(TEXT("topology_from"), Hands.HandsFrom);
		Out->SetStringField(TEXT("chains_from"), Source.From);
		Out->SetField(TEXT("reference_mesh"), AnimMcpJson::ObjectPathOrNull(RefMesh));
		if (!Hands.SkippedReason.IsEmpty())
		{
			return Skip(Hands.SkippedReason);
		}

		// ---- 체인 소속 · FK 매핑 ----
		TMap<int32, FName> ChainOfBone;
		for (const FNamedChain& Chain : Source.Chains)
		{
			for (const int32 Bone : Chain.Bones) { ChainOfBone.Add(Bone, Chain.Name); }
		}
		TSet<FName> Mapped;
		bool bMapping = false;
		if (Spec.Retargeter)
		{
			const UIKRetargeterController* Controller = UIKRetargeterController::GetController(Spec.Retargeter);
			if (const FIKRetargetFKChainsOp* FKOp = Controller ? Controller->GetFirstRetargetOpOfType<FIKRetargetFKChainsOp>() : nullptr)
			{
				bMapping = true;
				for (const FRetargetFKChainSettings& Settings : FKOp->Settings.ChainsToRetarget)
				{
					if (FKOp->IsEnabled() && Settings.EnableFK && !FKOp->Settings.ChainMapping.GetChainMappedTo(Settings.TargetChainName, ERetargetSourceOrTarget::Target).IsNone())
					{
						Mapped.Add(Settings.TargetChainName);
					}
				}
			}
		}
		Out->SetStringField(TEXT("mapping_from"), bMapping ? TEXT("retargeter") : TEXT("none"));
		auto IsMapped = [&ChainOfBone, &Mapped](int32 Bone) { const FName* Chain = ChainOfBone.Find(Bone); return Chain && Mapped.Contains(*Chain); };

		// ---- 포즈 열 ----
		TArray<int32> Column;
		Column.Init(INDEX_NONE, Tree.Num());
		for (int32 Bone = 0; Bone < Tree.Num(); ++Bone) { Column[Bone] = Bones.IndexOfByKey(Ref.GetBoneName(Bone)); }
		auto Has = [&Column](int32 Bone) { return Bone != INDEX_NONE && Column[Bone] != INDEX_NONE; };
		const int32 Frames = Component.Num();
		auto PosAt = [&](int32 Frame, int32 Bone) { return Component[Frame][Column[Bone]].GetLocation(); };

		TArray<TSharedPtr<FJsonValue>> HandsOut, UnmappedOut, UnmappedOver, Reversed, Overbent, OrderBroken;
		FString WorstBone;
		double WorstDeg = -1.0;
		int32 WorstFrame = 0;
		for (const FHand& Hand : Hands.Hands)
		{
			TSharedRef<FJsonObject> HandObj = AnimMcpJson::MakeObject();
			HandObj->SetStringField(TEXT("side"), Hand.Side);
			HandObj->SetStringField(TEXT("hand"), Ref.GetBoneName(Hand.Bone).ToString());
			HandObj->SetArrayField(TEXT("issues"), Strings(Hand.Issues));

			// 매핑 안 된 본 = 기준 로컬 회전 유지
			if (bMapping)
			{
				for (const FFinger& Finger : Hand.Fingers)
				{
					for (const int32 Bone : AllBones(Finger))
					{
						const int32 Parent = Tree.Parents[Bone];
						if (IsMapped(Bone) || !Has(Bone) || !Has(Parent)) { continue; }
						const FQuat RefLocal = Ref.GetRefBonePose()[Bone].GetRotation().GetNormalized();
						double MaxDeg = 0.0;
						int32 MaxFrame = 0;
						for (int32 Frame = 0; Frame < Frames; ++Frame)
						{
							const FQuat Local = Component[Frame][Column[Parent]].GetRotation().Inverse() * Component[Frame][Column[Bone]].GetRotation();
							const double D = FMath::RadiansToDegrees(Local.GetNormalized().AngularDistance(RefLocal));
							if (D > MaxDeg) { MaxDeg = D; MaxFrame = Frame; }
						}
						TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
						Item->SetStringField(TEXT("bone"), Ref.GetBoneName(Bone).ToString());
						const FName* Chain = ChainOfBone.Find(Bone);
						Item->SetField(TEXT("chain"), AnimMcpJson::StringOrNull(Chain ? Chain->ToString() : FString()));
						Item->SetNumberField(TEXT("max_deg"), AnimMcpStats::Round(MaxDeg, 2));
						Item->SetNumberField(TEXT("frame"), MaxFrame);
						UnmappedOut.Add(MakeShared<FJsonValueObject>(Item));
						if (MaxDeg > UnmappedMaxDeg)
						{
							UnmappedOver.Add(MakeShared<FJsonValueObject>(Item));
							if (MaxDeg > WorstDeg) { WorstDeg = MaxDeg; WorstBone = Ref.GetBoneName(Bone).ToString(); WorstFrame = MaxFrame; }
						}
					}
				}
			}

			// 굽힘 · 끝 순서 — 엄지 아닌 손가락, 좌우를 알 때(손바닥 = 키랄리티)
			TArray<const FFinger*> Fingers;
			for (const FFinger& Finger : Hand.Fingers)
			{
				if (Finger.Finger != EFinger::Thumb && Finger.Bones.Num() > 0 && Algo::AllOf(AllBones(Finger), Has)) { Fingers.Add(&Finger); }
			}
			const bool bMeasure = !Hand.Side.IsEmpty() && Fingers.Num() >= 2 && Has(Hand.Bone);
			TArray<TArray<double>> Mcp, Pip;
			Mcp.SetNum(Fingers.Num());
			Pip.SetNum(Fingers.Num());
			int32 BrokenFrames = 0;
			if (bMeasure)
			{
				const double PalmSign = Hand.Side == TEXT("Left") ? -1.0 : 1.0;
				for (int32 Frame = 0; Frame < Frames; ++Frame)
				{
					const FVector Wrist = PosAt(Frame, Hand.Bone);
					FVector Mean = FVector::ZeroVector;
					for (const FFinger* Finger : Fingers) { Mean += PosAt(Frame, Finger->Bones[0]); }
					Mean /= Fingers.Num();
					const FVector X = (Mean - Wrist).GetSafeNormal();
					FVector Lateral = PosAt(Frame, Fingers[0]->Bones[0]) - PosAt(Frame, Fingers.Last()->Bones[0]);
					Lateral = (Lateral - X * FVector::DotProduct(Lateral, X)).GetSafeNormal();
					const FVector Palm = PalmSign * FVector::CrossProduct(X, Lateral);
					const FVector BendAxis = FVector::CrossProduct(X, Palm).GetSafeNormal();
					TArray<double> TipLateral;
					for (int32 k = 0; k < Fingers.Num(); ++k)
					{
						const FFinger& Finger = *Fingers[k];
						const FVector Prev = Finger.Metacarpal != INDEX_NONE ? PosAt(Frame, Finger.Metacarpal) : Wrist;
						if (Finger.Bones.Num() >= 2)
						{
							Mcp[k].Add(SignedBendDeg(Prev, PosAt(Frame, Finger.Bones[0]), PosAt(Frame, Finger.Bones[1]), BendAxis));
						}
						if (Finger.Bones.Num() >= 3)
						{
							Pip[k].Add(SignedBendDeg(PosAt(Frame, Finger.Bones[0]), PosAt(Frame, Finger.Bones[1]), PosAt(Frame, Finger.Bones[2]), BendAxis));
						}
						TipLateral.Add(FVector::DotProduct(PosAt(Frame, Finger.Bones.Last()) - Wrist, Lateral));
					}
					for (int32 k = 0; k + 1 < TipLateral.Num(); ++k)
					{
						if (TipLateral[k] <= TipLateral[k + 1])
						{
							++BrokenFrames;
							break;
						}
					}
				}
			}
			TArray<TSharedPtr<FJsonValue>> FingersOut;
			for (const FFinger& Finger : Hand.Fingers)
			{
				TSharedRef<FJsonObject> FingerObj = AnimMcpJson::MakeObject();
				FingerObj->SetStringField(TEXT("finger"), FingerName(Finger.Finger));
				const FName* Chain = Finger.Bones.Num() > 0 ? ChainOfBone.Find(Finger.Bones[0]) : nullptr;
				const FString ChainName = Chain ? Chain->ToString() : Hand.Side.IsEmpty() ? FString(FingerName(Finger.Finger)) : StandardChainName(Hand.Side, Finger.Finger, false).ToString();
				FingerObj->SetStringField(TEXT("chain"), ChainName);
				if (Finger.Metacarpal != INDEX_NONE)
				{
					const FName* Meta = ChainOfBone.Find(Finger.Metacarpal);
					FingerObj->SetField(TEXT("metacarpal_chain"), AnimMcpJson::StringOrNull(Meta ? Meta->ToString() : FString()));
				}
				if (bMapping && Finger.Bones.Num() > 0) { FingerObj->SetBoolField(TEXT("mapped"), IsMapped(Finger.Bones[0])); }
				else { FingerObj->SetField(TEXT("mapped"), MakeShared<FJsonValueNull>()); }
				const int32 k = Fingers.IndexOfByKey(&Finger);
				if (k != INDEX_NONE)
				{
					FingerObj->SetField(TEXT("mcp"), Range(Mcp[k]));
					FingerObj->SetField(TEXT("pip"), Range(Pip[k]));
					auto Limit = [&](const TArray<double>& Values, const TCHAR* Joint, double Low, double High)
					{
						const int32 Under = Values.FilterByPredicate([Low](double V) { return V < Low; }).Num();
						const int32 Over = Values.FilterByPredicate([High](double V) { return V > High; }).Num();
						for (const bool bLow : { true, false })
						{
							const int32 Count = bLow ? Under : Over;
							if (Count == 0) { continue; }
							TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
							Item->SetStringField(TEXT("chain"), ChainName);
							Item->SetStringField(TEXT("joint"), Joint);
							Item->SetNumberField(TEXT("deg"), AnimMcpStats::Round(bLow ? FMath::Min(Values) : FMath::Max(Values), 2));
							Item->SetNumberField(TEXT("limit_deg"), bLow ? Low : High);
							Item->SetNumberField(TEXT("frames_pct"), AnimMcpStats::Round(100.0 * Count / Values.Num(), 1));
							(bLow ? Reversed : Overbent).Add(MakeShared<FJsonValueObject>(Item));
						}
					};
					Limit(Mcp[k], TEXT("mcp"), McpReversedDeg, McpOverbentDeg);
					Limit(Pip[k], TEXT("pip"), PipReversedDeg, PipOverbentDeg);
				}
				FingersOut.Add(MakeShared<FJsonValueObject>(FingerObj));
			}
			HandObj->SetArrayField(TEXT("fingers"), FingersOut);
			if (bMeasure)
			{
				const double Pct = 100.0 * BrokenFrames / Frames;
				HandObj->SetNumberField(TEXT("order_broken_pct"), AnimMcpStats::Round(Pct, 1));
				if (Pct > OrderBrokenMaxPct)
				{
					TSharedRef<FJsonObject> Item = AnimMcpJson::MakeObject();
					Item->SetStringField(TEXT("side"), Hand.Side);
					Item->SetNumberField(TEXT("frames_pct"), AnimMcpStats::Round(Pct, 1));
					OrderBroken.Add(MakeShared<FJsonValueObject>(Item));
				}
			}
			else
			{
				HandObj->SetField(TEXT("order_broken_pct"), MakeShared<FJsonValueNull>());
			}
			HandsOut.Add(MakeShared<FJsonValueObject>(HandObj));
		}

		if (UnmappedOver.Num() > 0)
		{
			TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
			Extra->SetArrayField(TEXT("bones"), UnmappedOver);
			Issue(TEXT("warning"), TEXT("FINGER_UNMAPPED_NOT_REFERENCE"), FString::Printf(TEXT("%d finger bone(s) with no source chain leave the target reference pose by more than %.0f° — worst %s %.1f° (frame %d); an unmapped finger should keep the reference pose (a bent retarget pose rides on every frame)"),
				UnmappedOver.Num(), UnmappedMaxDeg, *WorstBone, WorstDeg, WorstFrame), Extra);
		}
		if (Reversed.Num() > 0)
		{
			TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
			Extra->SetArrayField(TEXT("items"), Reversed);
			Issue(TEXT("warning"), TEXT("FINGER_BEND_REVERSED"), FString::Printf(TEXT("%d finger joint(s) bend toward the back of the hand beyond MCP %.0f° / PIP %.0f°"), Reversed.Num(), McpReversedDeg, PipReversedDeg), Extra);
		}
		if (Overbent.Num() > 0)
		{
			TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
			Extra->SetArrayField(TEXT("items"), Overbent);
			Issue(TEXT("warning"), TEXT("FINGER_OVERBENT"), FString::Printf(TEXT("%d finger joint(s) bend past MCP %.0f° / PIP %.0f°"), Overbent.Num(), McpOverbentDeg, PipOverbentDeg), Extra);
		}
		if (OrderBroken.Num() > 0)
		{
			TSharedRef<FJsonObject> Extra = AnimMcpJson::MakeObject();
			Extra->SetArrayField(TEXT("hands"), OrderBroken);
			Issue(TEXT("warning"), TEXT("FINGER_ORDER_BROKEN"), FString::Printf(TEXT("fingertips leave the index → pinky order on more than %.0f%% of frames (crossed fingers)"), OrderBrokenMaxPct), Extra);
		}
		Out->SetArrayField(TEXT("hands"), HandsOut);
		Out->SetArrayField(TEXT("unmapped"), UnmappedOut);
		TSharedRef<FJsonObject> Thresholds = AnimMcpJson::MakeObject();
		Thresholds->SetNumberField(TEXT("unmapped_max_deg"), UnmappedMaxDeg);
		Thresholds->SetNumberField(TEXT("mcp_reversed_deg"), McpReversedDeg);
		Thresholds->SetNumberField(TEXT("pip_reversed_deg"), PipReversedDeg);
		Thresholds->SetNumberField(TEXT("mcp_overbent_deg"), McpOverbentDeg);
		Thresholds->SetNumberField(TEXT("pip_overbent_deg"), PipOverbentDeg);
		Thresholds->SetNumberField(TEXT("order_broken_max_pct"), OrderBrokenMaxPct);
		Out->SetObjectField(TEXT("thresholds"), Thresholds);
		Out->SetArrayField(TEXT("issues"), Issues);
		return Out;
	}
}
