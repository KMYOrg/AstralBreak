#include "AnimMcpTools.h"

#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpAssetResolver.h"
#include "Core/AnimMcpMontage.h"
#include "UObject/UnrealType.h"

// Phase 7-6 — AnimSequence additive 설정. AimOffset 샘플은 Mesh Space additive 이면서 기준 포즈가 있어야 한다(7-3 실측: 기준 포즈 없는
// additive 시퀀스는 BlendSpace::AddSample 이 그 다음 샘플부터 거부 → ADDITIVE_INVALID). 에디터 디테일 패널이 하는 일을 그대로 —
// 필드 설정 뒤 PostEditChangeProperty(AnimSequence.cpp:1277-1331: 기준 포즈 스켈레톤 불일치는 조용히 null, additive 설정 변경은 재압축).
namespace AnimMcpTools
{
	namespace
	{
		template <typename TEnum>
		bool ParseEnum(const FString& Text, const TCHAR* Prefix, TEnum& Out, FString& OutAllowed)
		{
			const UEnum* Enum = StaticEnum<TEnum>();
			TArray<FString> Allowed;
			for (int32 i = 0; i < Enum->NumEnums() - 1; ++i)
			{
				Allowed.Add(Enum->GetNameStringByIndex(i));
			}
			OutAllowed = FString::Join(Allowed, TEXT(", "));
			FString Name = Text;
			if (!Name.StartsWith(Prefix))
			{
				Name = FString(Prefix) + Name;
			}
			const int64 Value = Enum->GetValueByNameString(Name);
			if (Value == INDEX_NONE)
			{
				return false;
			}
			Out = static_cast<TEnum>(Value);
			return true;
		}

		TSharedRef<FJsonObject> DescribeAdditive(const UAnimSequence* Sequence)
		{
			TSharedRef<FJsonObject> Out = AnimMcpJson::MakeObject();
			Out->SetStringField(TEXT("asset_path"), Sequence->GetPathName());
			Out->SetField(TEXT("skeleton"), AnimMcpJson::ObjectPathOrNull(Sequence->GetSkeleton()));
			Out->SetStringField(TEXT("additive_type"), StaticEnum<EAdditiveAnimationType>()->GetNameStringByValue(static_cast<int64>(Sequence->AdditiveAnimType)));
			Out->SetStringField(TEXT("ref_pose_type"), StaticEnum<EAdditiveBasePoseType>()->GetNameStringByValue(static_cast<int64>(Sequence->RefPoseType)));
			Out->SetField(TEXT("ref_pose_sequence"), AnimMcpJson::ObjectPathOrNull(Sequence->RefPoseSeq));
			Out->SetNumberField(TEXT("ref_frame_index"), Sequence->RefFrameIndex);
			Out->SetBoolField(TEXT("additive_valid"), Sequence->AdditiveAnimType == AAT_None || Sequence->IsValidAdditive());
			return Out;
		}
	}

	void RegisterSequenceTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("set_sequence_additive"),
			TEXT("Set the additive settings of an AnimSequence (what the Details panel's Additive Settings does) — needed before a sequence can be an AimOffset sample (Mesh Space additive with a base pose). Params: asset_path (AnimSequence), additive_type? (None | LocalSpaceBase | RotationOffsetMeshSpace), ref_pose_type? (None | RefPose | AnimScaled | AnimFrame | LocalAnimFrame), ref_pose_sequence? (AnimSequence path on the same skeleton, or null to clear), ref_frame_index?, save? (default false). Omitted fields keep their value; identical values = unchanged. Returns the resulting settings with additive_valid."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				FString AssetPath;
				if (!Context.Request.GetRequiredString(TEXT("asset_path"), AssetPath, OutError)) { return nullptr; }
				UAnimSequence* Sequence = Cast<UAnimSequence>(AnimMcpAssetResolver::LoadAssetOfClass(AssetPath, UAnimSequence::StaticClass(), OutError));
				if (!Sequence) { return nullptr; }
				const bool bSave = Context.Request.GetOptionalBool(TEXT("save"), false);

				auto BadField = [&OutError](const TCHAR* Field, const TCHAR* Reason, const FString& Message)
				{
					TSharedRef<FJsonObject> Details = AnimMcpJson::MakeObject();
					Details->SetStringField(TEXT("field"), Field);
					Details->SetStringField(TEXT("reason"), Reason);
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, Message, Details);
				};

				// ---- 파싱 (생략 = 유지) ----
				TOptional<EAdditiveAnimationType> AdditiveType;
				TOptional<EAdditiveBasePoseType> RefPoseType;
				TOptional<UAnimSequence*> RefPoseSeq;
				TOptional<int32> RefFrameIndex;

				FString Text, Allowed;
				if (Context.Request.Params->TryGetStringField(TEXT("additive_type"), Text))
				{
					EAdditiveAnimationType Parsed;
					if (!ParseEnum<EAdditiveAnimationType>(Text, TEXT("AAT_"), Parsed, Allowed))
					{
						BadField(TEXT("additive_type"), TEXT("BAD_ENUM"), FString::Printf(TEXT("Unknown additive_type '%s' (allowed: %s)"), *Text, *Allowed));
						return nullptr;
					}
					AdditiveType = Parsed;
				}
				if (Context.Request.Params->TryGetStringField(TEXT("ref_pose_type"), Text))
				{
					EAdditiveBasePoseType Parsed;
					if (!ParseEnum<EAdditiveBasePoseType>(Text, TEXT("ABPT_"), Parsed, Allowed))
					{
						BadField(TEXT("ref_pose_type"), TEXT("BAD_ENUM"), FString::Printf(TEXT("Unknown ref_pose_type '%s' (allowed: %s)"), *Text, *Allowed));
						return nullptr;
					}
					RefPoseType = Parsed;
				}
				if (Context.Request.Params->HasField(TEXT("ref_pose_sequence")))
				{
					if (Context.Request.Params->HasTypedField<EJson::Null>(TEXT("ref_pose_sequence")))
					{
						RefPoseSeq = static_cast<UAnimSequence*>(nullptr);
					}
					else if (Context.Request.Params->TryGetStringField(TEXT("ref_pose_sequence"), Text))
					{
						UAnimSequence* Base = Cast<UAnimSequence>(AnimMcpAssetResolver::LoadAssetOfClass(Text, UAnimSequence::StaticClass(), OutError));
						if (!Base) { return nullptr; }
						// PostEditChangeProperty 가 다른 스켈레톤의 기준 포즈를 조용히 null 로 만든다 — 먼저 거부
						if (Base->GetSkeleton() != Sequence->GetSkeleton())
						{
							BadField(TEXT("ref_pose_sequence"), TEXT("SKELETON_MISMATCH"), FString::Printf(TEXT("'%s' is on skeleton '%s' but '%s' is on '%s'"), *Base->GetPathName(), *GetPathNameSafe(Base->GetSkeleton()), *Sequence->GetPathName(), *GetPathNameSafe(Sequence->GetSkeleton())));
							return nullptr;
						}
						RefPoseSeq = Base;
					}
					else
					{
						BadField(TEXT("ref_pose_sequence"), TEXT("BAD_TYPE"), TEXT("ref_pose_sequence must be an asset path string or null"));
						return nullptr;
					}
				}
				if (Context.Request.Params->HasTypedField<EJson::Number>(TEXT("ref_frame_index")))
				{
					const int32 Index = static_cast<int32>(Context.Request.GetOptionalNumber(TEXT("ref_frame_index"), 0.0));
					if (Index < 0)
					{
						BadField(TEXT("ref_frame_index"), TEXT("OUT_OF_RANGE"), TEXT("ref_frame_index must be >= 0"));
						return nullptr;
					}
					RefFrameIndex = Index;
				}

				// ---- 변경 집합 ----
				TArray<FName> Changed;
				if (AdditiveType.IsSet() && AdditiveType.GetValue() != Sequence->AdditiveAnimType) { Changed.Add(GET_MEMBER_NAME_CHECKED(UAnimSequence, AdditiveAnimType)); }
				if (RefPoseType.IsSet() && RefPoseType.GetValue() != Sequence->RefPoseType) { Changed.Add(GET_MEMBER_NAME_CHECKED(UAnimSequence, RefPoseType)); }
				if (RefPoseSeq.IsSet() && RefPoseSeq.GetValue() != Sequence->RefPoseSeq) { Changed.Add(GET_MEMBER_NAME_CHECKED(UAnimSequence, RefPoseSeq)); }
				if (RefFrameIndex.IsSet() && RefFrameIndex.GetValue() != Sequence->RefFrameIndex) { Changed.Add(GET_MEMBER_NAME_CHECKED(UAnimSequence, RefFrameIndex)); }

				bool bSaved = false;
				if (Changed.Num() > 0)
				{
					Sequence->Modify();
					if (AdditiveType.IsSet()) { Sequence->AdditiveAnimType = AdditiveType.GetValue(); }
					if (RefPoseType.IsSet()) { Sequence->RefPoseType = RefPoseType.GetValue(); }
					if (RefPoseSeq.IsSet()) { Sequence->RefPoseSeq = RefPoseSeq.GetValue(); }
					if (RefFrameIndex.IsSet()) { Sequence->RefFrameIndex = RefFrameIndex.GetValue(); }

					// 디테일 패널과 같은 경로 — additive 설정 이름 중 하나로 통지하면 재압축·유효성 갱신 (바뀐 프로퍼티마다 한 번)
					for (const FName& Name : Changed)
					{
						FProperty* Property = UAnimSequence::StaticClass()->FindPropertyByName(Name);
						FPropertyChangedEvent Event(Property, EPropertyChangeType::ValueSet);
						Sequence->PostEditChangeProperty(Event);
					}
					if (bSave)
					{
						bSaved = AnimMcpMontage::SaveAsset(Sequence, Context);
					}
				}
				else
				{
					Context.AddDiagnostic(TEXT("info"), TEXT("UNCHANGED"), TEXT("Additive settings already match"));
				}

				TSharedRef<FJsonObject> Result = DescribeAdditive(Sequence);
				TArray<TSharedPtr<FJsonValue>> ChangedValues;
				for (const FName& Name : Changed) { ChangedValues.Add(MakeShared<FJsonValueString>(Name.ToString())); }
				Result->SetArrayField(TEXT("changed"), ChangedValues);
				Result->SetBoolField(TEXT("unchanged"), Changed.Num() == 0);
				Result->SetBoolField(TEXT("saved"), bSaved);
				Result->SetBoolField(TEXT("dirty"), Changed.Num() > 0 && !bSaved);
				return Result;
			});
	}
}
