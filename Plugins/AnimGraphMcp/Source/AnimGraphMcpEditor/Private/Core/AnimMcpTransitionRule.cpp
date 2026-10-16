#include "AnimMcpTransitionRule.h"

#include "AnimGraphNode_TransitionResult.h"
#include "AnimMcpLog.h"
#include "AnimStateTransitionNode.h"
#include "Animation/AnimBlueprint.h"
#include "Animation/AnimInstance.h"
#include "AnimationTransitionGraph.h"
#include "Bridge/AnimMcpTypes.h"
#include "Dom/JsonValue.h"
#include "EdGraph/EdGraph.h"
#include "EdGraph/EdGraphNode.h"
#include "EdGraph/EdGraphPin.h"
#include "EdGraphNode_Comment.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_CallFunction.h"
#include "K2Node_VariableGet.h"
#include "Kismet/KismetMathLibrary.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Misc/SecureHash.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/UnrealType.h"

namespace AnimMcpTransitionRule
{
	const TCHAR* const SourceMarker = TEXT("AnimGraphMcp rule_source v1");

	namespace
	{
		/** 피연산자 타입 — 비교 함수 표의 열 */
		enum class ECat : uint8 { Bool, Real, Int, Int64, Name, Literal, Unsupported };

		const TCHAR* CatName(ECat Cat)
		{
			switch (Cat)
			{
			case ECat::Bool: return TEXT("bool");
			case ECat::Real: return TEXT("real");
			case ECat::Int: return TEXT("int");
			case ECat::Int64: return TEXT("int64");
			case ECat::Name: return TEXT("name");
			case ECat::Literal: return TEXT("literal");
			default: return TEXT("unsupported");
			}
		}

		ECat CatFromPinType(const FEdGraphPinType& Type)
		{
			if (Type.IsContainer()) { return ECat::Unsupported; }
			if (Type.PinCategory == UEdGraphSchema_K2::PC_Boolean) { return ECat::Bool; }
			if (Type.PinCategory == UEdGraphSchema_K2::PC_Real) { return ECat::Real; }
			if (Type.PinCategory == UEdGraphSchema_K2::PC_Int) { return ECat::Int; }
			if (Type.PinCategory == UEdGraphSchema_K2::PC_Int64) { return ECat::Int64; }
			if (Type.PinCategory == UEdGraphSchema_K2::PC_Name) { return ECat::Name; }
			return ECat::Unsupported;
		}

		ECat CatFromProperty(const FProperty* Property)
		{
			FEdGraphPinType Type;
			return (Property && GetDefault<UEdGraphSchema_K2>()->ConvertPropertyToPinType(Property, Type)) ? CatFromPinType(Type) : ECat::Unsupported;
		}

		/**
		 * (op, 타입) → UKismetMathLibrary 함수 이름 (KismetMathLibrary.h:217-587, 3919-3923). 전부 BlueprintPure, 클래스 메타 BlueprintThreadSafe (:188).
		 * 지원하지 않는 조합은 NAME_None
		 */
		FName CompareFunction(const FString& Op, ECat Cat)
		{
			const TCHAR* Suffix = nullptr;
			switch (Cat)
			{
			case ECat::Real: Suffix = TEXT("DoubleDouble"); break;
			case ECat::Int: Suffix = TEXT("IntInt"); break;
			case ECat::Int64: Suffix = TEXT("Int64Int64"); break;
			case ECat::Bool: Suffix = TEXT("BoolBool"); break;
			case ECat::Name: Suffix = TEXT("NameName"); break;
			default: return NAME_None;
			}
			const bool bOrdered = (Cat == ECat::Real || Cat == ECat::Int || Cat == ECat::Int64);
			const TCHAR* Prefix = nullptr;
			if (Op == TEXT(">")) { Prefix = bOrdered ? TEXT("Greater_") : nullptr; }
			else if (Op == TEXT("<")) { Prefix = bOrdered ? TEXT("Less_") : nullptr; }
			else if (Op == TEXT(">=")) { Prefix = bOrdered ? TEXT("GreaterEqual_") : nullptr; }
			else if (Op == TEXT("<=")) { Prefix = bOrdered ? TEXT("LessEqual_") : nullptr; }
			else if (Op == TEXT("==")) { Prefix = TEXT("EqualEqual_"); }
			else if (Op == TEXT("!=")) { Prefix = TEXT("NotEqual_"); }
			if (!Prefix)
			{
				return NAME_None;
			}
			return FName(*(FString(Prefix) + Suffix));
		}

		UClass* VariableClassOf(UAnimBlueprint* Blueprint)
		{
			if (Blueprint->SkeletonGeneratedClass) { return Blueprint->SkeletonGeneratedClass; }
			if (Blueprint->GeneratedClass) { return Blueprint->GeneratedClass; }
			return Blueprint->ParentClass;
		}

		/** 리터럴 → 핀 기본값 텍스트 (TrySetDefaultValue 가 받는 형식) */
		bool LiteralToPinText(const TSharedPtr<FJsonValue>& Lit, ECat Cat, FString& Out, FAnimMcpError& OutError)
		{
			switch (Cat)
			{
			case ECat::Bool:
				if (Lit->Type != EJson::Boolean) { OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("literal must be a boolean here")); return false; }
				Out = Lit->AsBool() ? TEXT("true") : TEXT("false");
				return true;
			case ECat::Real:
				if (Lit->Type != EJson::Number) { OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("literal must be a number here")); return false; }
				Out = FString::SanitizeFloat(Lit->AsNumber());
				return true;
			case ECat::Int:
			case ECat::Int64:
				if (Lit->Type != EJson::Number || FMath::Frac(Lit->AsNumber()) != 0.0) { OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("literal must be an integer here")); return false; }
				Out = FString::Printf(TEXT("%lld"), static_cast<int64>(Lit->AsNumber()));
				return true;
			case ECat::Name:
				if (Lit->Type != EJson::String) { OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("literal must be a string here")); return false; }
				Out = Lit->AsString();
				return true;
			default:
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("literal type cannot be inferred (compare with a non-literal operand)"));
				return false;
			}
		}

		FString LiteralCanonical(const TSharedPtr<FJsonValue>& Lit)
		{
			switch (Lit->Type)
			{
			case EJson::Boolean: return Lit->AsBool() ? TEXT("true") : TEXT("false");
			case EJson::Number: return FString::SanitizeFloat(Lit->AsNumber());
			case EJson::String: return TEXT("\"") + Lit->AsString().ReplaceCharWithEscapedChar() + TEXT("\"");
			default: return TEXT("null");
			}
		}

		/** 공유 문맥 — 검증과 생성이 같은 해석을 쓴다 */
		struct FRuleContext
		{
			UAnimBlueprint* Blueprint = nullptr;
			UClass* VarClass = nullptr;
			/** Build 전용 */
			UEdGraph* Graph = nullptr;
			int32 OriginX = 0;
			int32 OriginY = 0;
			int32 NextRow = 0;
			int32 MaxDepth = 0;
			TArray<UEdGraphNode*>* Created = nullptr;
		};

		/** 식 하나의 해석 결과 — 검증 단계에선 타입만, 생성 단계에선 핀 또는 리터럴 */
		struct FExpr
		{
			ECat Cat = ECat::Unsupported;
			UEdGraphPin* Pin = nullptr;
			TSharedPtr<FJsonValue> Literal;
			bool IsLiteral() const { return Literal.IsValid(); }
		};

		bool GetSingleKey(const TSharedPtr<FJsonObject>& Obj, FString& OutKey, FAnimMcpError& OutError, bool bAllowTriggerTime = false)
		{
			if (!Obj.IsValid())
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("rule expression must be an object"));
				return false;
			}
			TArray<FString> Keys;
			Obj->Values.GetKeys(Keys);
			if (bAllowTriggerTime)
			{
				Keys.Remove(TEXT("trigger_time"));
			}
			if (Keys.Num() != 1)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("rule expression must have exactly one key (var|not|and|or|compare|literal|call|automatic), got %d"), Keys.Num()));
				return false;
			}
			OutKey = Keys[0];
			return true;
		}

		bool ResolveVariable(const FRuleContext& Ctx, const FString& Name, FProperty*& OutProperty, ECat& OutCat, FAnimMcpError& OutError)
		{
			OutProperty = Ctx.VarClass ? Ctx.VarClass->FindPropertyByName(FName(*Name)) : nullptr;
			if (!OutProperty || !OutProperty->HasAnyPropertyFlags(CPF_BlueprintVisible))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("var '%s' is not a BlueprintVisible property of %s (see get_anim_blueprint_info.variables)"), *Name, Ctx.VarClass ? *Ctx.VarClass->GetName() : TEXT("?")));
				return false;
			}
			OutCat = CatFromProperty(OutProperty);
			if (OutCat == ECat::Unsupported)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("var '%s' has type %s which rules do not support (bool, float/double, int, int64, name)"), *Name, *OutProperty->GetCPPType()));
				return false;
			}
			return true;
		}

		/** call 화이트리스트 — 핸드오프 §9 */
		UFunction* ResolveFunction(const FRuleContext& Ctx, const FString& Name, const FString& ClassPath, FAnimMcpError& OutError)
		{
			UFunction* Function = nullptr;
			if (!ClassPath.IsEmpty())
			{
				UClass* Class = FindObject<UClass>(nullptr, *ClassPath);
				Function = Class ? Class->FindFunctionByName(FName(*Name)) : nullptr;
			}
			else
			{
				Function = Ctx.VarClass ? Ctx.VarClass->FindFunctionByName(FName(*Name)) : nullptr;
				if (!Function)
				{
					Function = UKismetMathLibrary::StaticClass()->FindFunctionByName(FName(*Name));
				}
			}
			if (!Function)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("call: function '%s' not found on the AnimInstance class chain or UKismetMathLibrary"), *Name));
				return nullptr;
			}
			UClass* Owner = Function->GetOwnerClass();
			const bool bMathLib = (Owner == UKismetMathLibrary::StaticClass());
			const bool bAnimInstanceChain = Owner && Owner->IsChildOf(UAnimInstance::StaticClass()) && Ctx.VarClass && Ctx.VarClass->IsChildOf(Owner);
			if (!bMathLib && !bAnimInstanceChain)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, FString::Printf(TEXT("call: '%s' is owned by %s — only this AnimInstance's class chain and UKismetMathLibrary are allowed"), *Name, Owner ? *Owner->GetName() : TEXT("?")));
				return nullptr;
			}
			if (!Function->HasAnyFunctionFlags(FUNC_BlueprintPure))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, FString::Printf(TEXT("call: '%s' is not BlueprintPure"), *Name));
				return nullptr;
			}
			if (!FBlueprintEditorUtils::HasFunctionBlueprintThreadSafeMetaData(Function))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::PropertyNotAllowed, FString::Printf(TEXT("call: '%s' is not marked BlueprintThreadSafe (function or owning class)"), *Name));
				return nullptr;
			}
			return Function;
		}

		FProperty* ReturnProperty(UFunction* Function)
		{
			for (TFieldIterator<FProperty> It(Function); It; ++It)
			{
				if (It->HasAnyPropertyFlags(CPF_ReturnParm))
				{
					return *It;
				}
			}
			return nullptr;
		}

		bool IsInputParam(const FProperty* P)
		{
			return P->HasAnyPropertyFlags(CPF_Parm) && !P->HasAnyPropertyFlags(CPF_ReturnParm) && !(P->HasAnyPropertyFlags(CPF_OutParm) && !P->HasAnyPropertyFlags(CPF_ReferenceParm));
		}

		//~ 검증 + 정규화 (재귀). Canonical 은 키 순서 고정

		bool ValidateExpr(const FRuleContext& Ctx, const TSharedPtr<FJsonValue>& Value, int32 Depth, FExpr& Out, FString& Canonical, FAnimMcpError& OutError)
		{
			if (!Value.IsValid() || Value->Type != EJson::Object)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("rule expression must be an object like {\"var\": \"Speed\"}"));
				return false;
			}
			if (Depth > 32)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("rule expression nests too deep"));
				return false;
			}
			const TSharedPtr<FJsonObject> Obj = Value->AsObject();
			FString Key;
			if (!GetSingleKey(Obj, Key, OutError))
			{
				return false;
			}
			const TSharedPtr<FJsonValue> Inner = Obj->TryGetField(Key);

			if (Key == TEXT("var"))
			{
				if (!Inner.IsValid() || Inner->Type != EJson::String)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("var expects a property name string"));
					return false;
				}
				FProperty* Property = nullptr;
				if (!ResolveVariable(Ctx, Inner->AsString(), Property, Out.Cat, OutError))
				{
					return false;
				}
				Canonical += TEXT("{\"var\":\"") + Inner->AsString() + TEXT("\"}");
				return true;
			}
			if (Key == TEXT("literal"))
			{
				if (!Inner.IsValid() || (Inner->Type != EJson::Boolean && Inner->Type != EJson::Number && Inner->Type != EJson::String))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("literal expects a boolean, number or string"));
					return false;
				}
				Out.Cat = ECat::Literal;
				Out.Literal = Inner;
				Canonical += TEXT("{\"literal\":") + LiteralCanonical(Inner) + TEXT("}");
				return true;
			}
			if (Key == TEXT("not"))
			{
				FExpr Child;
				Canonical += TEXT("{\"not\":");
				if (!ValidateExpr(Ctx, Inner, Depth + 1, Child, Canonical, OutError))
				{
					return false;
				}
				if (Child.Cat != ECat::Bool)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("not expects a bool operand, got %s"), CatName(Child.Cat)));
					return false;
				}
				Canonical += TEXT("}");
				Out.Cat = ECat::Bool;
				return true;
			}
			if (Key == TEXT("and") || Key == TEXT("or"))
			{
				if (!Inner.IsValid() || Inner->Type != EJson::Array || Inner->AsArray().Num() < 2)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("%s expects an array of at least two bool expressions"), *Key));
					return false;
				}
				Canonical += TEXT("{\"") + Key + TEXT("\":[");
				bool bFirst = true;
				for (const TSharedPtr<FJsonValue>& Element : Inner->AsArray())
				{
					if (!bFirst) { Canonical += TEXT(","); }
					bFirst = false;
					FExpr Child;
					if (!ValidateExpr(Ctx, Element, Depth + 1, Child, Canonical, OutError))
					{
						return false;
					}
					if (Child.Cat != ECat::Bool)
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("%s operands must be bool, got %s"), *Key, CatName(Child.Cat)));
						return false;
					}
				}
				Canonical += TEXT("]}");
				Out.Cat = ECat::Bool;
				return true;
			}
			if (Key == TEXT("compare"))
			{
				const TSharedPtr<FJsonObject> Cmp = (Inner.IsValid() && Inner->Type == EJson::Object) ? Inner->AsObject() : nullptr;
				FString Op;
				if (!Cmp.IsValid() || !Cmp->TryGetStringField(TEXT("op"), Op) || !Cmp->HasField(TEXT("left")) || !Cmp->HasField(TEXT("right")))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("compare expects {op, left, right}"));
					return false;
				}
				Canonical += TEXT("{\"compare\":{\"op\":\"") + Op + TEXT("\",\"left\":");
				FExpr Left, Right;
				if (!ValidateExpr(Ctx, Cmp->TryGetField(TEXT("left")), Depth + 1, Left, Canonical, OutError)) { return false; }
				Canonical += TEXT(",\"right\":");
				if (!ValidateExpr(Ctx, Cmp->TryGetField(TEXT("right")), Depth + 1, Right, Canonical, OutError)) { return false; }
				Canonical += TEXT("}}");

				if (Left.IsLiteral() && Right.IsLiteral())
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("compare needs at least one non-literal operand"));
					return false;
				}
				const ECat Cat = Left.IsLiteral() ? Right.Cat : Left.Cat;
				if (!Left.IsLiteral() && !Right.IsLiteral() && Left.Cat != Right.Cat)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("compare operands differ in type (%s vs %s)"), CatName(Left.Cat), CatName(Right.Cat)));
					return false;
				}
				if (CompareFunction(Op, Cat).IsNone())
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("compare op '%s' is not supported for %s operands"), *Op, CatName(Cat)));
					return false;
				}
				FString Unused;
				if (Left.IsLiteral() && !LiteralToPinText(Left.Literal, Cat, Unused, OutError)) { return false; }
				if (Right.IsLiteral() && !LiteralToPinText(Right.Literal, Cat, Unused, OutError)) { return false; }
				Out.Cat = ECat::Bool;
				return true;
			}
			if (Key == TEXT("call"))
			{
				const TSharedPtr<FJsonObject> Call = (Inner.IsValid() && Inner->Type == EJson::Object) ? Inner->AsObject() : nullptr;
				FString FunctionName, ClassPath;
				if (!Call.IsValid() || !Call->TryGetStringField(TEXT("function"), FunctionName))
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("call expects {function, class?, args?}"));
					return false;
				}
				Call->TryGetStringField(TEXT("class"), ClassPath);
				UFunction* Function = ResolveFunction(Ctx, FunctionName, ClassPath, OutError);
				if (!Function)
				{
					return false;
				}
				FProperty* Return = ReturnProperty(Function);
				Out.Cat = CatFromProperty(Return);
				if (Out.Cat == ECat::Unsupported)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("call: '%s' returns %s which rules do not support"), *FunctionName, Return ? *Return->GetCPPType() : TEXT("void")));
					return false;
				}
				Canonical += TEXT("{\"call\":{\"function\":\"") + FunctionName + TEXT("\"");
				if (!ClassPath.IsEmpty())
				{
					Canonical += TEXT(",\"class\":\"") + ClassPath + TEXT("\"");
				}
				const TSharedPtr<FJsonObject> Args = Call->HasTypedField<EJson::Object>(TEXT("args")) ? Call->GetObjectField(TEXT("args")) : nullptr;
				TArray<FString> ArgKeys;
				if (Args.IsValid())
				{
					Args->Values.GetKeys(ArgKeys);
					ArgKeys.Sort();
				}
				// 모든 입력 파라미터가 주어져야 한다 (기본값 의존 금지 — 그래프가 결정적이도록)
				for (TFieldIterator<FProperty> It(Function); It; ++It)
				{
					if (!IsInputParam(*It))
					{
						continue;
					}
					const FString ParamName = It->GetName();
					if (!ArgKeys.Contains(ParamName))
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("call: '%s' requires arg '%s' (%s)"), *FunctionName, *ParamName, *It->GetCPPType()));
						return false;
					}
					const ECat ParamCat = CatFromProperty(*It);
					FExpr Arg;
					FString ArgCanon;
					if (!ValidateExpr(Ctx, Args->TryGetField(ParamName), Depth + 1, Arg, ArgCanon, OutError))
					{
						return false;
					}
					if (Arg.IsLiteral())
					{
						FString Unused;
						if (!LiteralToPinText(Arg.Literal, ParamCat, Unused, OutError)) { return false; }
					}
					else if (Arg.Cat != ParamCat)
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("call: arg '%s' expects %s, got %s"), *ParamName, CatName(ParamCat), CatName(Arg.Cat)));
						return false;
					}
				}
				for (const FString& K : ArgKeys)
				{
					if (!Function->FindPropertyByName(FName(*K)))
					{
						OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("call: '%s' has no parameter '%s'"), *FunctionName, *K));
						return false;
					}
				}
				if (ArgKeys.Num() > 0)
				{
					Canonical += TEXT(",\"args\":{");
					bool bFirst = true;
					for (const FString& K : ArgKeys)
					{
						if (!bFirst) { Canonical += TEXT(","); }
						bFirst = false;
						Canonical += TEXT("\"") + K + TEXT("\":");
						FExpr Dummy;
						ValidateExpr(Ctx, Args->TryGetField(K), Depth + 1, Dummy, Canonical, OutError);
					}
					Canonical += TEXT("}");
				}
				Canonical += TEXT("}}");
				return true;
			}
			if (Key == TEXT("automatic"))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("automatic is only allowed as the whole rule, not nested"));
				return false;
			}
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("unknown rule key '%s' (var|not|and|or|compare|literal|call|automatic)"), *Key));
			return false;
		}
	}

	bool Validate(UAnimBlueprint* Blueprint, const TSharedPtr<FJsonObject>& Rule, FString& OutCanonical, bool& bOutAutomatic, double& OutTriggerTime, FAnimMcpError& OutError)
	{
		bOutAutomatic = false;
		OutTriggerTime = -1.0;
		OutCanonical.Reset();
		if (!Blueprint || !Rule.IsValid())
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("set_transition_rule requires 'rule' object"));
			return false;
		}
		FString Key;
		if (!GetSingleKey(Rule, Key, OutError, /*bAllowTriggerTime*/ true))
		{
			return false;
		}
		if (Key == TEXT("automatic"))
		{
			bool bAuto = false;
			if (!Rule->TryGetBoolField(TEXT("automatic"), bAuto) || !bAuto)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("automatic must be true (omit the key for a graph rule)"));
				return false;
			}
			Rule->TryGetNumberField(TEXT("trigger_time"), OutTriggerTime);
			bOutAutomatic = true;
			OutCanonical = FString::Printf(TEXT("{\"automatic\":true,\"trigger_time\":%s}"), *FString::SanitizeFloat(OutTriggerTime));
			return true;
		}
		if (Rule->HasField(TEXT("trigger_time")))
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("trigger_time is only valid with automatic"));
			return false;
		}

		FRuleContext Ctx;
		Ctx.Blueprint = Blueprint;
		Ctx.VarClass = VariableClassOf(Blueprint);
		FExpr Top;
		if (!ValidateExpr(Ctx, MakeShared<FJsonValueObject>(Rule), 0, Top, OutCanonical, OutError))
		{
			return false;
		}
		if (Top.IsLiteral())
		{
			if (Top.Literal->Type != EJson::Boolean)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, TEXT("a literal rule must be true or false"));
				return false;
			}
			return true;
		}
		if (Top.Cat != ECat::Bool)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::BadRequest, FString::Printf(TEXT("the rule must evaluate to bool, got %s"), CatName(Top.Cat)));
			return false;
		}
		return true;
	}

	//~ 생성

	namespace
	{
		template <typename T>
		T* PlaceNode(FRuleContext& Ctx, int32 Depth, TFunctionRef<void(T*)> Configure)
		{
			FGraphNodeCreator<T> Creator(*Ctx.Graph);
			T* Node = Creator.CreateNode(/*bSelectNewNode*/ false);
			Configure(Node);
			Node->NodePosX = Ctx.OriginX - 360 * (Depth + 1);
			Node->NodePosY = Ctx.OriginY + 140 * Ctx.NextRow++;
			Ctx.MaxDepth = FMath::Max(Ctx.MaxDepth, Depth);
			Creator.Finalize();
			Ctx.Created->Add(Node);
			return Node;
		}

		bool Feed(FRuleContext& Ctx, UEdGraphPin* Input, const FExpr& Value, ECat Cat, FAnimMcpError& OutError)
		{
			if (!Input)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("rule: expected input pin missing on generated node"));
				return false;
			}
			if (Value.IsLiteral())
			{
				FString Text;
				if (!LiteralToPinText(Value.Literal, Cat, Text, OutError))
				{
					return false;
				}
				GetDefault<UEdGraphSchema_K2>()->TrySetDefaultValue(*Input, Text);
				return true;
			}
			const UEdGraphSchema* Schema = Ctx.Graph->GetSchema();
			const FPinConnectionResponse Response = Schema->CanCreateConnection(Value.Pin, Input);
			if (Response.Response == CONNECT_RESPONSE_DISALLOW || Response.Response == CONNECT_RESPONSE_MAKE_WITH_CONVERSION_NODE)
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::ConnectionRejected, FString::Printf(TEXT("rule: cannot connect %s.%s -> %s.%s: %s"), *Value.Pin->GetOwningNode()->GetClass()->GetName(), *Value.Pin->PinName.ToString(), *Input->GetOwningNode()->GetClass()->GetName(), *Input->PinName.ToString(), *Response.Message.ToString()));
				return false;
			}
			if (!Schema->TryCreateConnection(Value.Pin, Input))
			{
				OutError = FAnimMcpError::Make(AnimMcpErrorCodes::ConnectionRejected, TEXT("rule: TryCreateConnection failed"));
				return false;
			}
			return true;
		}

		UK2Node_CallFunction* PlaceCall(FRuleContext& Ctx, UFunction* Function, int32 Depth)
		{
			return PlaceNode<UK2Node_CallFunction>(Ctx, Depth, [Function](UK2Node_CallFunction* Node)
			{
				// 자기 클래스 함수면 self 문맥, 라이브러리면 외부 참조 — SetFromFunction 이 GetBlueprintClassFromNode 로 가른다 (K2Node_CallFunction.cpp:1772)
				Node->SetFromFunction(Function);
			});
		}

		bool BuildExpr(FRuleContext& Ctx, const TSharedPtr<FJsonValue>& Value, int32 Depth, FExpr& Out, FAnimMcpError& OutError)
		{
			const TSharedPtr<FJsonObject> Obj = Value->AsObject();
			FString Key;
			GetSingleKey(Obj, Key, OutError);
			const TSharedPtr<FJsonValue> Inner = Obj->TryGetField(Key);

			if (Key == TEXT("literal"))
			{
				Out.Cat = ECat::Literal;
				Out.Literal = Inner;
				return true;
			}
			if (Key == TEXT("var"))
			{
				FProperty* Property = nullptr;
				if (!ResolveVariable(Ctx, Inner->AsString(), Property, Out.Cat, OutError)) { return false; }
				UK2Node_VariableGet* Getter = PlaceNode<UK2Node_VariableGet>(Ctx, Depth, [&](UK2Node_VariableGet* Node)
				{
					Node->SetFromProperty(Property, /*bSelfContext*/ true, Ctx.VarClass);
				});
				Out.Pin = Getter->FindPin(Property->GetFName(), EGPD_Output);
				if (!Out.Pin)
				{
					OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("rule: variable getter for '%s' has no output pin"), *Property->GetName()));
					return false;
				}
				return true;
			}
			if (Key == TEXT("not"))
			{
				FExpr Child;
				if (!BuildExpr(Ctx, Inner, Depth + 1, Child, OutError)) { return false; }
				UK2Node_CallFunction* Call = PlaceCall(Ctx, UKismetMathLibrary::StaticClass()->FindFunctionByName(TEXT("Not_PreBool")), Depth);
				if (!Feed(Ctx, Call->FindPin(TEXT("A"), EGPD_Input), Child, ECat::Bool, OutError)) { return false; }
				Out.Cat = ECat::Bool;
				Out.Pin = Call->GetReturnValuePin();
				return true;
			}
			if (Key == TEXT("and") || Key == TEXT("or"))
			{
				UFunction* Function = UKismetMathLibrary::StaticClass()->FindFunctionByName(Key == TEXT("and") ? TEXT("BooleanAND") : TEXT("BooleanOR"));
				const TArray<TSharedPtr<FJsonValue>>& Elements = Inner->AsArray();
				FExpr Acc;
				if (!BuildExpr(Ctx, Elements[0], Depth + 1, Acc, OutError)) { return false; }
				for (int32 i = 1; i < Elements.Num(); ++i)
				{
					FExpr Next;
					if (!BuildExpr(Ctx, Elements[i], Depth + 1, Next, OutError)) { return false; }
					UK2Node_CallFunction* Call = PlaceCall(Ctx, Function, Depth);
					if (!Feed(Ctx, Call->FindPin(TEXT("A"), EGPD_Input), Acc, ECat::Bool, OutError)) { return false; }
					if (!Feed(Ctx, Call->FindPin(TEXT("B"), EGPD_Input), Next, ECat::Bool, OutError)) { return false; }
					Acc = FExpr();
					Acc.Cat = ECat::Bool;
					Acc.Pin = Call->GetReturnValuePin();
				}
				Out = Acc;
				return true;
			}
			if (Key == TEXT("compare"))
			{
				const TSharedPtr<FJsonObject> Cmp = Inner->AsObject();
				const FString Op = Cmp->GetStringField(TEXT("op"));
				FExpr Left, Right;
				if (!BuildExpr(Ctx, Cmp->TryGetField(TEXT("left")), Depth + 1, Left, OutError)) { return false; }
				if (!BuildExpr(Ctx, Cmp->TryGetField(TEXT("right")), Depth + 1, Right, OutError)) { return false; }
				const ECat Cat = Left.IsLiteral() ? Right.Cat : Left.Cat;
				UFunction* Function = UKismetMathLibrary::StaticClass()->FindFunctionByName(CompareFunction(Op, Cat));
				UK2Node_CallFunction* Call = PlaceCall(Ctx, Function, Depth);
				if (!Feed(Ctx, Call->FindPin(TEXT("A"), EGPD_Input), Left, Cat, OutError)) { return false; }
				if (!Feed(Ctx, Call->FindPin(TEXT("B"), EGPD_Input), Right, Cat, OutError)) { return false; }
				Out.Cat = ECat::Bool;
				Out.Pin = Call->GetReturnValuePin();
				return true;
			}
			if (Key == TEXT("call"))
			{
				const TSharedPtr<FJsonObject> CallObj = Inner->AsObject();
				FString ClassPath;
				CallObj->TryGetStringField(TEXT("class"), ClassPath);
				UFunction* Function = ResolveFunction(Ctx, CallObj->GetStringField(TEXT("function")), ClassPath, OutError);
				if (!Function) { return false; }
				const TSharedPtr<FJsonObject> Args = CallObj->HasTypedField<EJson::Object>(TEXT("args")) ? CallObj->GetObjectField(TEXT("args")) : nullptr;

				// 인자 식을 먼저 (깊이 +1), 그 다음 호출 노드
				TArray<TPair<FProperty*, FExpr>> ArgValues;
				for (TFieldIterator<FProperty> It(Function); It; ++It)
				{
					if (!IsInputParam(*It)) { continue; }
					FExpr Arg;
					if (!BuildExpr(Ctx, Args->TryGetField(It->GetName()), Depth + 1, Arg, OutError)) { return false; }
					ArgValues.Emplace(*It, Arg);
				}
				UK2Node_CallFunction* Call = PlaceCall(Ctx, Function, Depth);
				for (const TPair<FProperty*, FExpr>& Pair : ArgValues)
				{
					if (!Feed(Ctx, Call->FindPin(Pair.Key->GetFName(), EGPD_Input), Pair.Value, CatFromProperty(Pair.Key), OutError)) { return false; }
				}
				Out.Cat = CatFromProperty(ReturnProperty(Function));
				Out.Pin = Call->GetReturnValuePin();
				return true;
			}
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, FString::Printf(TEXT("rule: unexpected key '%s' at build time"), *Key));
			return false;
		}

		UEdGraphNode_Comment* PlaceComment(FRuleContext& Ctx, const FString& Text, int32 Width)
		{
			FGraphNodeCreator<UEdGraphNode_Comment> Creator(*Ctx.Graph);
			UEdGraphNode_Comment* Comment = Creator.CreateNode(/*bSelectNewNode*/ false);
			Comment->NodePosX = Ctx.OriginX - Width;
			Comment->NodePosY = Ctx.OriginY - 260;
			Comment->NodeWidth = Width + 320;
			Comment->NodeHeight = 120;
			Creator.Finalize();
			// Finalize 뒤에 쓴다 — UEdGraphNode_Comment::PostPlacedNewNode 가 NodeComment 를 기본 "Comment" 로 되돌린다 (EdGraphNode_Comment.cpp:86-)
			Comment->Modify();
			Comment->NodeComment = Text;
			Comment->CommentColor = FLinearColor(0.2f, 0.45f, 0.85f, 1.f);
			Ctx.Created->Add(Comment);
			return Comment;
		}
	}

	bool Build(UAnimStateTransitionNode* Transition, const TSharedPtr<FJsonObject>& Rule, const FString& Canonical, bool bAutomatic, TArray<UEdGraphNode*>& OutCreated, FAnimMcpError& OutError)
	{
		UAnimationTransitionGraph* Graph = Transition ? Cast<UAnimationTransitionGraph>(Transition->BoundGraph) : nullptr;
		UAnimGraphNode_TransitionResult* Result = Graph ? Graph->GetResultNode() : nullptr;
		if (!Graph || !Result)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("transition has no rule graph / result node"));
			return false;
		}
		UAnimBlueprint* Blueprint = Cast<UAnimBlueprint>(FBlueprintEditorUtils::FindBlueprintForGraph(Graph));
		if (!Blueprint)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("transition graph has no owning Animation Blueprint"));
			return false;
		}

		FRuleContext Ctx;
		Ctx.Blueprint = Blueprint;
		Ctx.VarClass = VariableClassOf(Blueprint);
		Ctx.Graph = Graph;
		Ctx.OriginX = Result->NodePosX;
		Ctx.OriginY = Result->NodePosY;
		Ctx.Created = &OutCreated;
		Graph->Modify();

		UEdGraphPin* ResultPin = Result->FindPin(TEXT("bCanEnterTransition"), EGPD_Input);
		if (!ResultPin)
		{
			OutError = FAnimMcpError::Make(AnimMcpErrorCodes::Internal, TEXT("transition result node has no bCanEnterTransition pin"));
			return false;
		}

		if (!bAutomatic)
		{
			FExpr Top;
			if (!BuildExpr(Ctx, MakeShared<FJsonValueObject>(Rule), 0, Top, OutError))
			{
				return false;
			}
			Result->Modify();
			if (!Feed(Ctx, ResultPin, Top, ECat::Bool, OutError))
			{
				return false;
			}
		}

		// 원문 + 생성 직후 그래프 해시 — 해시는 주석 노드를 제외하므로 주석을 마지막에 만들어도 같다
		const FString Hash = HashRuleGraph(Graph);
		PlaceComment(Ctx, FString::Printf(TEXT("%s\n%s\n%s"), SourceMarker, *Hash, *Canonical), 360 * (Ctx.MaxDepth + 1));
		return true;
	}

	//~ 조회

	void CollectRuleNodes(UEdGraph* BoundGraph, TArray<UEdGraphNode*>& OutNodes)
	{
		OutNodes.Reset();
		if (!BoundGraph)
		{
			return;
		}
		for (UEdGraphNode* Node : BoundGraph->Nodes)
		{
			if (Node && !Node->IsA<UAnimGraphNode_TransitionResult>() && !Node->IsA<UEdGraphNode_Comment>())
			{
				OutNodes.Add(Node);
			}
		}
	}

	FString HashRuleGraph(UEdGraph* BoundGraph)
	{
		TArray<UEdGraphNode*> Nodes;
		if (BoundGraph)
		{
			for (UEdGraphNode* Node : BoundGraph->Nodes)
			{
				if (Node && !Node->IsA<UEdGraphNode_Comment>())
				{
					Nodes.Add(Node);
				}
			}
		}
		Nodes.Sort([](const UEdGraphNode& A, const UEdGraphNode& B)
		{
			if (A.NodePosX != B.NodePosX) { return A.NodePosX < B.NodePosX; }
			if (A.NodePosY != B.NodePosY) { return A.NodePosY < B.NodePosY; }
			return A.GetClass()->GetName() < B.GetClass()->GetName();
		});
		TMap<const UEdGraphNode*, int32> Index;
		for (int32 i = 0; i < Nodes.Num(); ++i)
		{
			Index.Add(Nodes[i], i);
		}

		FString Buffer;
		for (int32 i = 0; i < Nodes.Num(); ++i)
		{
			const UEdGraphNode* Node = Nodes[i];
			FString Title;
			if (const UK2Node_CallFunction* Call = Cast<UK2Node_CallFunction>(Node)) { Title = Call->GetFunctionName().ToString(); }
			else if (const UK2Node_VariableGet* Var = Cast<UK2Node_VariableGet>(Node)) { Title = Var->GetVarNameString(); }
			Buffer += FString::Printf(TEXT("N|%d|%s|%s|%d|%d\n"), i, *Node->GetClass()->GetName(), *Title, Node->NodePosX, Node->NodePosY);

			TArray<UEdGraphPin*> Pins = Node->Pins;
			Pins.RemoveAll([](UEdGraphPin* P) { return P == nullptr || P->bHidden; });
			Pins.Sort([](const UEdGraphPin& A, const UEdGraphPin& B) { return A.PinName.LexicalLess(B.PinName); });
			for (const UEdGraphPin* Pin : Pins)
			{
				TArray<FString> Links;
				for (const UEdGraphPin* Other : Pin->LinkedTo)
				{
					if (Other && Other->GetOwningNodeUnchecked())
					{
						const int32* OtherIndex = Index.Find(Other->GetOwningNodeUnchecked());
						Links.Add(FString::Printf(TEXT("%d:%s"), OtherIndex ? *OtherIndex : -1, *Other->PinName.ToString()));
					}
				}
				Links.Sort();
				Buffer += FString::Printf(TEXT("P|%s|%s|%s\n"), *Pin->PinName.ToString(), *Pin->DefaultValue, *FString::Join(Links, TEXT(";")));
			}
		}
		const FTCHARToUTF8 Utf8(*Buffer);
		return TEXT("sha1:") + FSHA1::HashBuffer(Utf8.Get(), Utf8.Length()).ToString().ToLower();
	}

	FSource ReadSource(UEdGraph* BoundGraph)
	{
		FSource Out;
		if (!BoundGraph)
		{
			return Out;
		}
		for (UEdGraphNode* Node : BoundGraph->Nodes)
		{
			const UEdGraphNode_Comment* Comment = Cast<UEdGraphNode_Comment>(Node);
			if (!Comment || !Comment->NodeComment.StartsWith(SourceMarker))
			{
				continue;
			}
			TArray<FString> Lines;
			Comment->NodeComment.ParseIntoArrayLines(Lines, /*bCullEmpty*/ false);
			if (Lines.Num() < 3)
			{
				continue;
			}
			Out.bHasSource = true;
			Out.StoredHash = Lines[1].TrimStartAndEnd();
			TArray<FString> Rest(Lines.GetData() + 2, Lines.Num() - 2);
			Out.Canonical = FString::Join(Rest, TEXT("\n")).TrimStartAndEnd();
			TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Out.Canonical);
			TSharedPtr<FJsonObject> Parsed;
			if (FJsonSerializer::Deserialize(Reader, Parsed) && Parsed.IsValid())
			{
				Out.Source = Parsed;
			}
			Out.bModified = (HashRuleGraph(BoundGraph) != Out.StoredHash);
			return Out;
		}
		return Out;
	}
}
