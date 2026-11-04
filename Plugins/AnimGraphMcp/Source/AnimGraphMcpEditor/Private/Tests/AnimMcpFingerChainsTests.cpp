// 손가락 체인 제안 · 검사(Core/AnimMcpFingerChains)의 위상 판정 단위 테스트 — 실측 좌표로 만든 합성 스켈레톤(SOMA77 · Biped(SB) · CMU 유형). 애셋 없이 메모리에서만.
// run_automation_tests {filter:"AnimGraphMcp.Generation.FingerChains"} 로 돈다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Core/AnimMcpFingerChains.h"
#include "Core/AnimMcpSkeletonGeometry.h"
#include "ReferenceSkeleton.h"

namespace
{
	/** 이름 · 부모(없으면 루트) · 컴포넌트 공간 위치 — 회전은 모두 단위 */
	struct FBoneSpec
	{
		FString Name;
		FString Parent;
		FVector Position;
	};

	void Build(const TArray<FBoneSpec>& Bones, FReferenceSkeleton& Out)
	{
		FReferenceSkeletonModifier Modifier(Out, nullptr);
		TMap<FString, FVector> Positions;
		for (const FBoneSpec& Bone : Bones)
		{
			const int32 Parent = Bone.Parent.IsEmpty() ? INDEX_NONE : Out.FindRawBoneIndex(FName(*Bone.Parent));
			const FVector Local = Bone.Position - (Bone.Parent.IsEmpty() ? FVector::ZeroVector : Positions[Bone.Parent]);
			Modifier.Add(FMeshBoneInfo(FName(*Bone.Name), Bone.Name, Parent), FTransform(Local));
			Positions.Add(Bone.Name, Bone.Position);
		}
	}

	/** +Y 정면 · +X 왼쪽(UE 마네킹 · Vesper) 몸 — 팔은 수평(T 포즈), 발끝이 +Y */
	TArray<FBoneSpec> Body()
	{
		TArray<FBoneSpec> Out = { { TEXT("root"), TEXT(""), FVector(0, 0, 0) }, { TEXT("pelvis"), TEXT("root"), FVector(0, 0, 100) }, { TEXT("spine"), TEXT("pelvis"), FVector(0, 0, 125) } };
		for (const double S : { 1.0, -1.0 })
		{
			const FString Side = S > 0 ? TEXT("l") : TEXT("r");
			Out.Add({ TEXT("clavicle_") + Side, TEXT("spine"), FVector(5 * S, 0, 145) });
			Out.Add({ TEXT("upperarm_") + Side, TEXT("clavicle_") + Side, FVector(15 * S, 0, 145) });
			Out.Add({ TEXT("lowerarm_") + Side, TEXT("upperarm_") + Side, FVector(40 * S, 0, 145) });
			Out.Add({ TEXT("hand_") + Side, TEXT("lowerarm_") + Side, FVector(65 * S, 0, 145) });
			Out.Add({ TEXT("thigh_") + Side, TEXT("pelvis"), FVector(10 * S, 0, 95) });
			Out.Add({ TEXT("calf_") + Side, TEXT("thigh_") + Side, FVector(10 * S, 0, 50) });
			Out.Add({ TEXT("foot_") + Side, TEXT("calf_") + Side, FVector(10 * S, 0, 8) });
			Out.Add({ TEXT("ball_") + Side, TEXT("foot_") + Side, FVector(10 * S, 12, 1) });
		}
		return Out;
	}

	/** 손 아래 사슬 — Offsets 는 부모 기준(왼손 좌표, 오른손은 X 를 뒤집는다) */
	void AddChain(TArray<FBoneSpec>& Out, const FString& Hand, double S, const TArray<TPair<FString, FVector>>& Offsets)
	{
		FString Parent = Hand;
		FVector Position = Out.FindByPredicate([&Hand](const FBoneSpec& B) { return B.Name == Hand; })->Position;
		for (const TPair<FString, FVector>& Offset : Offsets)
		{
			Position += FVector(Offset.Value.X * S, Offset.Value.Y, Offset.Value.Z);
			Out.Add({ Offset.Key, Parent, Position });
			Parent = Offset.Key;
		}
	}

	AnimMcpSkeletonGeometry::FNamedChain Named(const FReferenceSkeleton& Ref, const AnimMcpSkeletonGeometry::FTree& Tree, const TCHAR* Name, const TCHAR* Start, const TCHAR* End)
	{
		return { FName(Name), AnimMcpSkeletonGeometry::ChainBones(Ref, Tree, FName(Start), FName(End)) };
	}

	/** 제안 체인 이름 → "start..end" */
	TMap<FString, FString> ChainMap(const AnimMcpFingerChains::FSuggestion& Suggestion)
	{
		TMap<FString, FString> Out;
		for (const TSharedPtr<FJsonValue>& V : Suggestion.Json->GetArrayField(TEXT("chains")))
		{
			const TSharedPtr<FJsonObject> C = V->AsObject();
			Out.Add(C->GetStringField(TEXT("name")), C->GetStringField(TEXT("start")) + TEXT("..") + C->GetStringField(TEXT("end")));
		}
		return Out;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAnimMcpFingerChainsTest, "AnimGraphMcp.Generation.FingerChains", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FAnimMcpFingerChainsTest::RunTest(const FString& Parameters)
{
	using namespace AnimMcpFingerChains;

	// ---- SOMA77: Hand{F}1 메타카팔(손목에서 2.9~4.0 cm) → 2~4 → End, 엄지 Thumb1~3 → End. 수동 팔 체인(이름 Left/Right) ----
	// 좌표는 Kimodo BVH(표준 T 포즈) 오프셋을 UE (x, z, y) 로 — walk_turn_tpose.bvh 실측
	{
		TArray<FBoneSpec> Bones = Body();
		for (const double S : { 1.0, -1.0 })
		{
			const FString Side = S > 0 ? TEXT("Left") : TEXT("Right");
			const FString Hand = S > 0 ? TEXT("hand_l") : TEXT("hand_r");
			const FString H = Side + TEXT("Hand");
			AddChain(Bones, Hand, S, { { H + TEXT("Thumb1"), FVector(2.28, 3.19, -1.39) }, { H + TEXT("Thumb2"), FVector(4.01, 1.64, -1.83) }, { H + TEXT("Thumb3"), FVector(2.8, 0, 0) }, { H + TEXT("ThumbEnd"), FVector(3.18, 0, 0) } });
			AddChain(Bones, Hand, S, { { H + TEXT("Index1"), FVector(3.25, 2.3, -0.53) }, { H + TEXT("Index2"), FVector(6.36, 0.18, 0.01) }, { H + TEXT("Index3"), FVector(3.66, 0, 0) }, { H + TEXT("Index4"), FVector(2.33, 0, 0) }, { H + TEXT("IndexEnd"), FVector(2.76, -0.11, -0.18) } });
			AddChain(Bones, Hand, S, { { H + TEXT("Middle1"), FVector(3.16, 1.0, 0.24) }, { H + TEXT("Middle2"), FVector(6.19, -1.0, -0.26) }, { H + TEXT("Middle3"), FVector(4.36, 0, 0) }, { H + TEXT("Middle4"), FVector(3.0, 0, 0) }, { H + TEXT("MiddleEnd"), FVector(2.3, -0.03, -0.29) } });
			AddChain(Bones, Hand, S, { { H + TEXT("Ring1"), FVector(2.88, -0.32, -0.05) }, { H + TEXT("Ring2"), FVector(5.85, -1.37, -0.49) }, { H + TEXT("Ring3"), FVector(4.35, 0, 0) }, { H + TEXT("Ring4"), FVector(2.65, 0, 0) }, { H + TEXT("RingEnd"), FVector(1.94, 0, 0.08) } });
			AddChain(Bones, Hand, S, { { H + TEXT("Pinky1"), FVector(2.87, -1.6, -0.31) }, { H + TEXT("Pinky2"), FVector(5.09, -1.77, -1.33) }, { H + TEXT("Pinky3"), FVector(3.07, 0, 0) }, { H + TEXT("Pinky4"), FVector(1.55, 0, 0) }, { H + TEXT("PinkyEnd"), FVector(1.94, 0.06, -0.16) } });
		}
		FReferenceSkeleton Ref;
		Build(Bones, Ref);
		AnimMcpSkeletonGeometry::FTree Tree;
		Tree.Init(Ref);
		AnimMcpSkeletonGeometry::FChainSource Source;
		Source.From = TEXT("argument");
		Source.Chains = { Named(Ref, Tree, TEXT("LeftArm"), TEXT("upperarm_l"), TEXT("hand_l")), Named(Ref, Tree, TEXT("RightArm"), TEXT("upperarm_r"), TEXT("hand_r")),
			Named(Ref, Tree, TEXT("LeftLeg"), TEXT("thigh_l"), TEXT("ball_l")), Named(Ref, Tree, TEXT("RightLeg"), TEXT("thigh_r"), TEXT("ball_r")) };
		const FSuggestion Suggestion = Suggest(Ref, Tree, Source, GivenChains(Ref, Source));
		const TMap<FString, FString> Chains = ChainMap(Suggestion);
		TestEqual(TEXT("SOMA: hands from the arm chains"), Suggestion.Json->GetStringField(TEXT("hands_from")), FString(TEXT("arm_chains")));
		TestEqual(TEXT("SOMA: sides from the chain names"), Suggestion.Json->GetStringField(TEXT("side_from")), FString(TEXT("chain_names")));
		TestEqual(TEXT("SOMA: 18 finger chains"), Suggestion.NumChains, 18);
		TestEqual(TEXT("SOMA: none of them in the 4 given chains"), Suggestion.Missing.Num(), 18);
		for (const FString Side : { TEXT("Left"), TEXT("Right") })
		{
			TestEqual(TEXT("SOMA thumb = Thumb1..3 (End out)"), Chains.FindRef(Side + TEXT("Thumb")), Side + TEXT("HandThumb1..") + Side + TEXT("HandThumb3"));
			for (const FString Finger : { TEXT("Index"), TEXT("Middle"), TEXT("Ring"), TEXT("Pinky") })
			{
				TestEqual(*(TEXT("SOMA metacarpal ") + Side + Finger), Chains.FindRef(Side + Finger + TEXT("Metacarpal")), Side + TEXT("Hand") + Finger + TEXT("1..") + Side + TEXT("Hand") + Finger + TEXT("1"));
				TestEqual(*(TEXT("SOMA finger ") + Side + Finger), Chains.FindRef(Side + Finger), Side + TEXT("Hand") + Finger + TEXT("2..") + Side + TEXT("Hand") + Finger + TEXT("4"));
			}
		}
		const TArray<TSharedPtr<FJsonValue>>& Hands = Suggestion.Json->GetArrayField(TEXT("hands"));
		TestEqual(TEXT("SOMA: left hand first"), Hands[0]->AsObject()->GetStringField(TEXT("hand")), FString(TEXT("hand_l")));
		TestEqual(TEXT("SOMA: 5 tips excluded per hand"), Hands[0]->AsObject()->GetArrayField(TEXT("tips_excluded")).Num(), 5);
		TestTrue(TEXT("SOMA: thumb margin is clear"), Hands[0]->AsObject()->GetNumberField(TEXT("thumb_margin_deg")) > 3.0);
		TestEqual(TEXT("SOMA: all 5 fingers mirror left/right"), Suggestion.Json->GetArrayField(TEXT("mirrored")).Num(), 5);

		// 같은 이름 · 다른 본(자동 캐릭터라이즈가 Mixamo 로 잡은 Index1~3) → differs
		TArray<FGivenChain> Mixamo = GivenChains(Ref, Source);
		Mixamo.Add({ FName(TEXT("LeftIndex")), FName(TEXT("LeftHandIndex1")), FName(TEXT("LeftHandIndex3")) });
		const FSuggestion Shifted = Suggest(Ref, Tree, Source, Mixamo);
		TestEqual(TEXT("SOMA: a template index chain one joint off differs"), Shifted.Differs.Num(), 1);
		TestEqual(TEXT("SOMA: the rest stay missing"), Shifted.Missing.Num(), 17);
	}

	// ---- Biped(SB 유형): 메타카팔 없이 3마디 · 손목 가까운 엄지 · 손 아래 FX 잎 본과 길이 0 제약 사슬. 체인 없이 위상 + 발 정면 ----
	{
		TArray<FBoneSpec> Bones = Body();
		for (const double S : { 1.0, -1.0 })
		{
			const FString L = S > 0 ? TEXT("L") : TEXT("R");
			const FString Hand = S > 0 ? TEXT("hand_l") : TEXT("hand_r");
			const FString F = TEXT("Bip001-") + L + TEXT("-Finger");
			AddChain(Bones, Hand, S, { { F + TEXT("0"), FVector(2.0, 1.8, -0.5) }, { F + TEXT("01"), FVector(2.5, 3.2, -0.8) }, { F + TEXT("02"), FVector(1.5, 2.0, -0.5) } });
			AddChain(Bones, Hand, S, { { F + TEXT("1"), FVector(8.3, 1.8, 0) }, { F + TEXT("11"), FVector(3.5, 0, 0) }, { F + TEXT("12"), FVector(2.2, 0, 0) } });
			AddChain(Bones, Hand, S, { { F + TEXT("2"), FVector(8.4, 0.6, 0) }, { F + TEXT("21"), FVector(3.6, 0, 0) }, { F + TEXT("22"), FVector(2.6, 0, 0) } });
			AddChain(Bones, Hand, S, { { F + TEXT("3"), FVector(8.1, -0.6, 0) }, { F + TEXT("31"), FVector(3.2, 0, 0) }, { F + TEXT("32"), FVector(2.3, 0, 0) } });
			AddChain(Bones, Hand, S, { { F + TEXT("4"), FVector(7.8, -1.8, 0) }, { F + TEXT("41"), FVector(2.5, 0, 0) }, { F + TEXT("42"), FVector(1.5, 0, 0) } });
			AddChain(Bones, Hand, S, { { TEXT("FX_Hand_") + L, FVector(9.7, 0, 0) } });
			AddChain(Bones, Hand, S, { { TEXT("SC_Weapon_") + L, FVector(6.4, 0, -2) }, { TEXT("SC_WeaponRot_") + L, FVector(0, 0, 0) } });
		}
		FReferenceSkeleton Ref;
		Build(Bones, Ref);
		AnimMcpSkeletonGeometry::FTree Tree;
		Tree.Init(Ref);
		AnimMcpSkeletonGeometry::FChainSource None;
		None.From = TEXT("none");
		const FSuggestion Suggestion = Suggest(Ref, Tree, None, {});
		const TMap<FString, FString> Chains = ChainMap(Suggestion);
		TestEqual(TEXT("Biped: hands by topology"), Suggestion.Json->GetStringField(TEXT("hands_from")), FString(TEXT("topology")));
		TestEqual(TEXT("Biped: sides from the feet facing"), Suggestion.Json->GetStringField(TEXT("side_from")), FString(TEXT("facing")));
		TestEqual(TEXT("Biped: 10 finger chains, no metacarpal"), Suggestion.NumChains, 10);
		TestEqual(TEXT("Biped: left thumb = Finger0..02"), Chains.FindRef(TEXT("LeftThumb")), FString(TEXT("Bip001-L-Finger0..Bip001-L-Finger02")));
		TestEqual(TEXT("Biped: left index = Finger1"), Chains.FindRef(TEXT("LeftIndex")), FString(TEXT("Bip001-L-Finger1..Bip001-L-Finger12")));
		TestEqual(TEXT("Biped: left pinky = Finger4"), Chains.FindRef(TEXT("LeftPinky")), FString(TEXT("Bip001-L-Finger4..Bip001-L-Finger42")));
		TestEqual(TEXT("Biped: right ring = Finger3"), Chains.FindRef(TEXT("RightRing")), FString(TEXT("Bip001-R-Finger3..Bip001-R-Finger32")));
		TestFalse(TEXT("Biped: the zero-length weapon chain is no finger"), Chains.Contains(TEXT("LeftIndexMetacarpal")));
	}

	// ---- CMU 유형: 손목과 같은 자리의 FingerBase → Fingers 사슬 1개 + 엄지 잎 → 제안 없음 ----
	{
		TArray<FBoneSpec> Bones = Body();
		for (const double S : { 1.0, -1.0 })
		{
			const FString Side = S > 0 ? TEXT("Left") : TEXT("Right");
			const FString Hand = S > 0 ? TEXT("hand_l") : TEXT("hand_r");
			AddChain(Bones, Hand, S, { { Side + TEXT("FingerBase"), FVector(0, 0, 0) }, { Side + TEXT("Fingers"), FVector(4.7, 0, 0) } });
			AddChain(Bones, Hand, S, { { Side + TEXT("Thumb"), FVector(0, 0, 0) } });
		}
		FReferenceSkeleton Ref;
		Build(Bones, Ref);
		AnimMcpSkeletonGeometry::FTree Tree;
		Tree.Init(Ref);
		AnimMcpSkeletonGeometry::FChainSource Source;
		Source.Chains = { Named(Ref, Tree, TEXT("LeftArm"), TEXT("upperarm_l"), TEXT("hand_l")), Named(Ref, Tree, TEXT("RightArm"), TEXT("upperarm_r"), TEXT("hand_r")),
			Named(Ref, Tree, TEXT("LeftLeg"), TEXT("thigh_l"), TEXT("ball_l")), Named(Ref, Tree, TEXT("RightLeg"), TEXT("thigh_r"), TEXT("ball_r")) };
		const FSuggestion Suggestion = Suggest(Ref, Tree, Source, GivenChains(Ref, Source));
		TestEqual(TEXT("CMU: no finger chains"), Suggestion.NumChains, 0);
		const TArray<TSharedPtr<FJsonValue>>& Issues = Suggestion.Json->GetArrayField(TEXT("hands"))[0]->AsObject()->GetArrayField(TEXT("issues"));
		TestTrue(TEXT("CMU: TOO_FEW_FINGER_CHAINS"), Issues.Num() == 1 && Issues[0]->AsString() == TEXT("TOO_FEW_FINGER_CHAINS"));
	}

	// ---- 굽힘 부호: 왼손 손바닥 아래(−Z), x = +X → 굽힘축 x × 손바닥 = +Y. 손바닥 쪽 +, 손등 쪽 − ----
	{
		const FVector BendAxis = FVector::CrossProduct(FVector::XAxisVector, -FVector::ZAxisVector);
		TestTrue(TEXT("toward the palm is +45°"), FMath::IsNearlyEqual(SignedBendDeg(FVector::ZeroVector, FVector(1, 0, 0), FVector(2, 0, -1), BendAxis), 45.0, 1e-6));
		TestTrue(TEXT("toward the back is −45°"), FMath::IsNearlyEqual(SignedBendDeg(FVector::ZeroVector, FVector(1, 0, 0), FVector(2, 0, 1), BendAxis), -45.0, 1e-6));
		TestTrue(TEXT("straight is 0°"), FMath::IsNearlyZero(SignedBendDeg(FVector::ZeroVector, FVector(1, 0, 0), FVector(2, 0, 0), BendAxis)));
	}
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
