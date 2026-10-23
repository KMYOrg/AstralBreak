// AI 애니 생성 Phase 2 — 키 편집 계산부(Core/AnimMcpAnimEditOps) 단위 테스트. 합성 리그(루트 · 골반 · 척추 · 좌우 팔)와 합성 키만 쓰고
// 애셋을 만들지 않는다. op 마다 길이·키 대응·출처·이음매가 의도대로인지, 미러를 두 번 하면 원래대로인지 확인한다.
// run_automation_tests {filter:"AnimGraphMcp.Generation"} 로 돈다.

#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Core/AnimMcpAnimEditOps.h"

namespace
{
	using namespace AnimMcpAnimEditOps;

	constexpr double Fps = 30.0;

	/** root → pelvis → spine → (upperarm_l, upperarm_r). 기준 포즈의 팔은 X 축 대칭 */
	FRig MakeRig()
	{
		FRig Rig;
		Rig.Bones = { TEXT("root"), TEXT("pelvis"), TEXT("spine_01"), TEXT("upperarm_l"), TEXT("upperarm_r") };
		Rig.Parents = { INDEX_NONE, 0, 1, 2, 2 };
		Rig.RefLocal = {
			FTransform::Identity,
			FTransform(FVector(0, 0, 90)),
			FTransform(FVector(0, 0, 20)),
			FTransform(FRotator(0, 90, 0).Quaternion(), FVector(15, 0, 30)),
			FTransform(FRotator(0, -90, 0).Quaternion(), FVector(-15, 0, 30)) };
		Rig.Finalize();
		return Rig;
	}

	/** 1초(31키) — 루트가 +Y 로 100cm, 골반이 비틀리고 왼팔만 들린다 */
	FSource MakeSource(const FRig& Rig)
	{
		FSource Source;
		Source.FrameRate = Fps;
		Source.NumKeys = 31;
		Source.Tracks.SetNum(Rig.Num());
		for (int32 Key = 0; Key < Source.NumKeys; ++Key)
		{
			const double T = Key / Fps;
			Source.Tracks[0].Add(FTransform(FRotator(0, 10 * T, 0).Quaternion(), FVector(0, 100 * T, 0)));
			Source.Tracks[1].Add(FTransform(FRotator(0, 20 * FMath::Sin(T * 2 * PI), 0).Quaternion(), FVector(0, 0, 90)));
			Source.Tracks[3].Add(FTransform(FRotator(40 * T, 90, 0).Quaternion(), FVector(15, 0, 30)));
		}
		Source.CurveNames = { TEXT("Weight") };
		FRichCurve& Curve = Source.Curves.AddDefaulted_GetRef();
		Curve.AddKey(0.f, 0.f);
		Curve.AddKey(1.f, 1.f);
		return Source;
	}

	bool PosesEqual(const TArray<FTransform>& A, const TArray<FTransform>& B, double Tolerance = 1e-3)
	{
		if (A.Num() != B.Num()) { return false; }
		for (int32 i = 0; i < A.Num(); ++i)
		{
			if (!A[i].Equals(B[i], Tolerance)) { return false; }
		}
		return true;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FAnimMcpEditOpsTest, "AnimGraphMcp.Generation.Edit", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

bool FAnimMcpEditOpsTest::RunTest(const FString& Parameters)
{
	const FRig Rig = MakeRig();
	const FSource Source = MakeSource(Rig);
	FClip Base;
	Sample(Rig, Source, 0, Fps, 0.0, Source.Length(), false, Base);
	TestEqual(TEXT("sample: 31 keys"), Base.NumKeys(), 31);
	TestTrue(TEXT("sample: key 15 = source key 15"), Base.Keys[15][0].Equals(Source.Tracks[0][15], 1e-4));
	TestTrue(TEXT("sample: untracked bone = ref pose"), Base.Keys[10][2].Equals(Rig.RefLocal[2], 1e-4));
	TestFalse(TEXT("sample: untracked bone not animated"), static_cast<bool>(Base.Animated[2]));
	TestEqual(TEXT("sample: curve evaluated"), Base.CurveValues[15][0], 0.5f, 1e-3f);

	// ---- trim ----
	{
		FClip Clip = Base;
		FReport Report;
		FString Error;
		TestTrue(TEXT("trim ok"), Trim(Clip, 0.2, 0.6, Report, Error));
		TestEqual(TEXT("trim: 13 keys"), Clip.NumKeys(), 13);
		TestTrue(TEXT("trim: first key = original key 6"), PosesEqual(Clip.Keys[0], Base.Keys[6]));
		TestEqual(TEXT("trim: provenance time"), Clip.Provenance[0].Time, 0.2, 1e-6);
		FClip Short = Base;
		TestFalse(TEXT("trim: < 1 frame refused"), Trim(Short, 0.5, 0.51, Report, Error));
		TestEqual(TEXT("trim: refused leaves the clip"), Short.NumKeys(), 31);
	}

	// ---- retime: 0..0.4s 를 2배 → 12프레임이 6프레임, 전체 24프레임 ----
	{
		FClip Clip = Base;
		FReport Report;
		FString Error;
		TestTrue(TEXT("retime ok"), Retime(Clip, 0.0, 0.4, 2.0, Report, Error));
		TestEqual(TEXT("retime: 25 keys"), Clip.NumKeys(), 25);
		TestTrue(TEXT("retime: key 3 = original key 6"), PosesEqual(Clip.Keys[3], Base.Keys[6]));
		TestTrue(TEXT("retime: key 10 = original key 16"), PosesEqual(Clip.Keys[10], Base.Keys[16]));
		TestEqual(TEXT("retime: max rate"), Clip.MaxRate, 2.0, 1e-9);
		TestTrue(TEXT("retime: seam at the rate change"), Clip.Seams.ContainsByPredicate([](double S) { return FMath::IsNearlyEqual(S, 0.2, 1e-6); }));
	}

	// ---- hold_pose: 0.5s 에서 0.2s 정지 → +6키 ----
	{
		FClip Clip = Base;
		FReport Report;
		FString Error;
		TestTrue(TEXT("hold ok"), HoldPose(Clip, 0.5, 0.2, Report, Error));
		TestEqual(TEXT("hold: 37 keys"), Clip.NumKeys(), 37);
		TestTrue(TEXT("hold: held keys equal"), PosesEqual(Clip.Keys[15], Clip.Keys[21]));
		TestTrue(TEXT("hold: after = original key 16"), PosesEqual(Clip.Keys[22], Base.Keys[16]));
		TestEqual(TEXT("hold: two seams"), Clip.Seams.Num(), 2);
	}

	// ---- 준비·복귀 모양: 0..0.5 + 같은 구간 역재생 → 끝 포즈 = 첫 포즈 ----
	{
		FClip Clip = Base;
		FReport Report;
		FString Error;
		TestTrue(TEXT("trim for concat"), Trim(Clip, 0.0, 0.5, Report, Error));
		FClip Segment;
		Sample(Rig, Source, 0, Fps, 0.0, 0.5, true, Segment);
		TestTrue(TEXT("concat ok"), Concat(Clip, Segment, 0.0, true, Report, Error));
		TestEqual(TEXT("concat: shared junction key"), Clip.NumKeys(), 16 + 16 - 1);
		TestTrue(TEXT("concat reverse: last pose = first pose"), PosesEqual(Clip.Keys.Last(), Clip.Keys[0]));
		TestTrue(TEXT("concat reverse: provenance reversed"), Clip.Provenance.Last().bReversed);
		FClip Blend = Base;
		TestFalse(TEXT("concat: blend longer than clip refused"), Concat(Blend, Segment, 2.0, true, Report, Error));
	}

	// ---- concat align_root: 붙는 구간이 현재 끝 루트에서 이어진다 ----
	{
		FClip Clip = Base;
		FReport Report;
		FString Error;
		FClip Segment;
		Sample(Rig, Source, 0, Fps, 0.0, 1.0, false, Segment);
		TestTrue(TEXT("concat forward ok"), Concat(Clip, Segment, 0.0, true, Report, Error));
		TestEqual(TEXT("concat forward: 61 keys"), Clip.NumKeys(), 61);
		TestTrue(TEXT("concat forward: root continues"), Clip.Keys[30][0].GetLocation().Equals(Base.Keys[30][0].GetLocation(), 1e-3));
		TestTrue(TEXT("concat forward: root keeps moving forward"), Clip.Keys[60][0].GetLocation().Size() > Base.Keys[30][0].GetLocation().Size() + 50.0);
	}

	// ---- mirror: 두 번이면 원래대로, 한 번이면 왼팔 동작이 오른팔로 ----
	{
		const TArray<int32> Pairs = MirrorPairs(Rig, [](FName Bone)
		{
			FString Name = Bone.ToString();
			if (Name.EndsWith(TEXT("_l"))) { return FName(*(Name.LeftChop(2) + TEXT("_r"))); }
			if (Name.EndsWith(TEXT("_r"))) { return FName(*(Name.LeftChop(2) + TEXT("_l"))); }
			return FName();
		});
		TestEqual(TEXT("mirror pairs: arm l ↔ r"), Pairs[3], 4);
		TestEqual(TEXT("mirror pairs: spine self"), Pairs[2], 2);
		FClip Clip = Base;
		Mirror(Rig, Clip, EAxis::X, Pairs);
		TestFalse(TEXT("mirror changes the pose"), PosesEqual(Clip.Keys[20], Base.Keys[20]));
		TestTrue(TEXT("mirror: the still right arm becomes the still left arm (ref pose)"), Clip.Keys[20][3].Equals(Rig.RefLocal[3], 1e-3));
		TestEqual(TEXT("mirror: root yaw turns the other way"), RootYawDelta(Clip), -RootYawDelta(Base), 1e-3);
		Mirror(Rig, Clip, EAxis::X, Pairs);
		bool bSame = true;
		for (int32 Key = 0; Key < Clip.NumKeys(); ++Key) { bSame &= PosesEqual(Clip.Keys[Key], Base.Keys[Key]); }
		TestTrue(TEXT("mirror twice = identity"), bSame);
	}

	// ---- offset_bone: 컴포넌트 축 Yaw 30° — 척추와 자식이 같이 돈다 ----
	{
		FClip Clip = Base;
		FReport Report;
		FString Error;
		FBoneOffset Offset;
		Offset.Bone = 2;
		Offset.Rotation = FRotator(0, 30, 0).Quaternion();
		TestTrue(TEXT("offset ok"), OffsetBones(Rig, Clip, { Offset }, true, 0.0, 1.0, 0.0, 0.0, Report, Error));
		TArray<FTransform> Before, After;
		ToComponent(Rig, Base.Keys[12], Before);
		ToComponent(Rig, Clip.Keys[12], After);
		const FQuat Expected = Offset.Rotation * Before[2].GetRotation();
		TestTrue(TEXT("offset: spine component rotation turned 30°"), After[2].GetRotation().Equals(Expected, 1e-4));
		TestTrue(TEXT("offset: pelvis untouched"), After[1].Equals(Before[1], 1e-4));
		TestTrue(TEXT("offset: child follows"), FMath::IsNearlyEqual(FMath::RadiansToDegrees(After[3].GetRotation().AngularDistance(Before[3].GetRotation())), 30.0, 0.01));
		FClip Blended = Base;
		TestTrue(TEXT("offset with blend ok"), OffsetBones(Rig, Blended, { Offset }, true, 0.0, 1.0, 0.3, 0.3, Report, Error));
		TestTrue(TEXT("offset blend: start untouched"), PosesEqual(Blended.Keys[0], Base.Keys[0]));
		TestTrue(TEXT("offset blend: end untouched"), PosesEqual(Blended.Keys[30], Base.Keys[30]));
		FClip TooLong = Base;
		TestFalse(TEXT("offset: blends longer than range refused"), OffsetBones(Rig, TooLong, { Offset }, true, 0.0, 0.4, 0.3, 0.3, Report, Error));
	}

	// ---- rotate_root: 0.5..1.0s 동안 +90° ----
	{
		FClip Clip = Base;
		FReport Report;
		FString Error;
		TestTrue(TEXT("rotate_root ok"), RotateRoot(Clip, 90.0, 0.5, 1.0, true, Report, Error));
		TestEqual(TEXT("rotate_root: yaw delta +90"), RootYawDelta(Clip), RootYawDelta(Base) + 90.0, 0.01);
		TestTrue(TEXT("rotate_root: before start untouched"), PosesEqual(Clip.Keys[15], Base.Keys[15]));
		const double Travel = FVector::Dist(Clip.Keys[30][0].GetLocation(), Clip.Keys[15][0].GetLocation());
		const double SourceTravel = FVector::Dist(Base.Keys[30][0].GetLocation(), Base.Keys[15][0].GetLocation());
		TestTrue(TEXT("rotate_root: path bends (shorter chord, same speed)"), Travel < SourceTravel - 1.0);
	}
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
