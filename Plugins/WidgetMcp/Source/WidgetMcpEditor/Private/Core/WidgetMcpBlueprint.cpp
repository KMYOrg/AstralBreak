#include "Core/WidgetMcpBlueprint.h"

#include "AnimMcpLog.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetTree.h"
#include "Components/CanvasPanel.h"
#include "Components/PanelWidget.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/CompilerResultsLog.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Misc/PackageName.h"
#include "UObject/Package.h"
#include "UObject/StrongObjectPtr.h"
#include "WidgetBlueprint.h"
#include "WidgetBlueprintEditorUtils.h"
#include "WidgetBlueprintFactory.h"

namespace WidgetMcpBlueprint
{
	namespace BlueprintPrivate
	{
		constexpr ERenameFlags RenameFlags = REN_DontCreateRedirectors | REN_NonTransactional | REN_DoNotDirty;

		struct FTarget
		{
			FString Id;
			FString Type;
			FString Parent;
			TSharedPtr<FJsonObject> Json;
			TSharedPtr<FJsonObject> Norm;
			UClass* Class = nullptr;
			bool bKeepUnsupported = false;   // 어휘 밖 위젯 — locked 이고 지금 그대로일 때만 통과, 손대지 않는다
		};

		struct FCurrent
		{
			TSharedPtr<FJsonObject> Json;
			FString Parent;
			int32 Index = 0;
		};

		bool IsIdentifier(const FString& Id)
		{
			if (Id.IsEmpty() || Id.Len() > 64 || !FChar::IsAlpha(Id[0]))
			{
				return false;
			}
			for (const TCHAR C : Id) { if (!FChar::IsAlnum(C) && C != TEXT('_')) { return false; } }
			return true;
		}

		FString Str(const TSharedPtr<FJsonObject>& O, const TCHAR* Key)
		{
			FString V;
			if (O.IsValid()) { O->TryGetStringField(Key, V); }
			return V;
		}

		void AddError(TArray<FString>& Errors, const TCHAR* Code, const FString& Message)
		{
			Errors.Add(FString::Printf(TEXT("%s: %s"), Code, *Message));
		}

		FString FirstCode(const TArray<FString>& Errors)
		{
			FString Code;
			return Errors.Num() && Errors[0].Split(TEXT(":"), &Code, nullptr) ? Code : FString(TEXT("SPEC_INVALID"));
		}

		TSharedPtr<FJsonObject> WidgetsById(const TSharedRef<FJsonObject>& Tree, TMap<FString, FCurrent>& Out, TArray<FString>& Order)
		{
			const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
			if (!Tree->TryGetArrayField(TEXT("widgets"), Arr))
			{
				return nullptr;
			}
			TMap<FString, int32> ChildCount;
			for (const TSharedPtr<FJsonValue>& V : *Arr)
			{
				const TSharedPtr<FJsonObject> W = V->AsObject();
				FCurrent C;
				C.Json = W;
				C.Parent = Str(W, TEXT("parent"));
				C.Index = ChildCount.FindOrAdd(C.Parent)++;
				const FString Id = Str(W, TEXT("id"));
				Out.Add(Id, C);
				Order.Add(Id);
			}
			return Tree;
		}

		/** 비교용 필드(id · type · parent 밖) */
		TArray<FString> FieldKeys(const TSharedPtr<FJsonObject>& A, const TSharedPtr<FJsonObject>& B)
		{
			TSet<FString> Keys;
			for (const TSharedPtr<FJsonObject>& O : { A, B })
			{
				if (!O.IsValid()) { continue; }
				for (const TPair<FString, TSharedPtr<FJsonValue>>& P : O->Values) { Keys.Add(P.Key); }
			}
			Keys.Remove(TEXT("id"));
			Keys.Remove(TEXT("type"));
			Keys.Remove(TEXT("parent"));
			TArray<FString> Sorted = Keys.Array();
			Sorted.Sort();
			return Sorted;
		}

		TSharedPtr<FJsonValue> Field(const TSharedPtr<FJsonObject>& O, const FString& Key)
		{
			const TSharedPtr<FJsonValue>* V = O.IsValid() ? O->Values.Find(Key) : nullptr;
			return V ? *V : nullptr;
		}

		TSharedRef<FJsonObject> Op(const TCHAR* Kind, const FString& Widget)
		{
			TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
			O->SetStringField(TEXT("op"), Kind);
			O->SetStringField(TEXT("widget"), Widget);
			return O;
		}

		/** 사본 트리에 목표를 적용 — 실패면 false + OutError (사본은 버린다) */
		bool ApplyToTree(UWidgetTree* Tree, const TArray<FTarget>& Targets, const TMap<FString, int32>& TargetIndex, const FString& RootId,
			const WidgetMcpSpec::FAssets& Assets, TSet<FString>& OutReplaced, FString& OutError)
		{
			TMap<FString, UWidget*> Existing;
			Tree->ForEachWidget([&Existing](UWidget* W) { Existing.Add(W->GetName(), W); });

			// 1) 지울 것(목표에 없거나 타입이 바뀜) · 떼어 낼 것(부모가 바뀌거나 부모가 지워짐)
			TSet<FString> Remove;
			for (const TPair<FString, UWidget*>& P : Existing)
			{
				const int32* TI = TargetIndex.Find(P.Key);
				if (!TI)
				{
					Remove.Add(P.Key);
				}
				else if (!Targets[*TI].bKeepUnsupported && P.Value->GetClass() != Targets[*TI].Class)
				{
					Remove.Add(P.Key);
					OutReplaced.Add(P.Key);
				}
			}
			for (const TPair<FString, UWidget*>& P : Existing)
			{
				const int32* TI = TargetIndex.Find(P.Key);
				if (!TI || Remove.Contains(P.Key) || P.Key == RootId)
				{
					continue;
				}
				UPanelWidget* Parent = P.Value->GetParent();
				const FString ParentName = Parent ? Parent->GetName() : FString();
				if (ParentName != Targets[*TI].Parent || Remove.Contains(ParentName))
				{
					P.Value->RemoveFromParent();
				}
			}
			for (const FString& Id : Remove)
			{
				UWidget* W = Existing[Id];
				if (Id == RootId)
				{
					OutError = TEXT("the root widget cannot be removed or change type");
					return false;
				}
				W->RemoveFromParent();
				W->Rename(*MakeUniqueObjectName(GetTransientPackage(), W->GetClass(), *(TEXT("WidgetMcpRemoved_") + Id)).ToString(), GetTransientPackage(), RenameFlags);
				Existing.Remove(Id);
			}

			// 2) 새로 만들 것
			for (const FTarget& T : Targets)
			{
				if (Existing.Contains(T.Id))
				{
					continue;
				}
				if (T.Id == RootId && Tree->RootWidget)
				{
					OutError = TEXT("the tree already has a different root");
					return false;
				}
				UWidget* W = Tree->ConstructWidget<UWidget>(T.Class, FName(*T.Id));
				if (!W)
				{
					OutError = FString::Printf(TEXT("ConstructWidget failed for '%s' (%s)"), *T.Id, *T.Type);
					return false;
				}
				W->bIsVariable = true;
				Existing.Add(T.Id, W);
				if (T.Id == RootId)
				{
					Tree->RootWidget = W;
				}
			}
			if (!Tree->RootWidget || Tree->RootWidget->GetName() != RootId)
			{
				OutError = FString::Printf(TEXT("root is '%s', spec root is '%s'"), *GetNameSafe(Tree->RootWidget), *RootId);
				return false;
			}

			// 3) 패널마다 자식 순서 — 다르면 비우고 목표 순서로 다시 넣는다(슬롯은 4 에서 전부 쓴다)
			TMap<FString, TArray<FString>> Children;
			for (const FTarget& T : Targets)
			{
				if (!T.Parent.IsEmpty())
				{
					Children.FindOrAdd(T.Parent).Add(T.Id);
				}
			}
			for (const FTarget& T : Targets)
			{
				if (T.bKeepUnsupported || !WidgetMcpSpec::IsPanelType(T.Type))
				{
					continue;
				}
				UPanelWidget* Panel = Cast<UPanelWidget>(Existing[T.Id]);
				const TArray<FString> Desired = Children.FindRef(T.Id);
				TArray<FString> Current;
				for (int32 i = 0; i < Panel->GetChildrenCount(); ++i) { Current.Add(GetNameSafe(Panel->GetChildAt(i))); }
				if (Current == Desired)
				{
					continue;
				}
				Panel->ClearChildren();
				for (const FString& ChildId : Desired)
				{
					UWidget* Child = Existing[ChildId];
					if (Child->GetParent())
					{
						Child->RemoveFromParent();
					}
					if (!Panel->AddChild(Child))
					{
						OutError = FString::Printf(TEXT("'%s' could not take child '%s'"), *T.Id, *ChildId);
						return false;
					}
				}
			}

			// 4) 슬롯 · 속성 — 목표값을 전부 쓴다(멱등)
			for (const FTarget& T : Targets)
			{
				if (T.bKeepUnsupported)
				{
					continue;
				}
				UWidget* W = Existing[T.Id];
				if (!T.Parent.IsEmpty())
				{
					const TSharedPtr<FJsonObject>* Slot = nullptr;
					if (!W->Slot || !T.Norm->TryGetObjectField(TEXT("slot"), Slot) || !WidgetMcpSpec::ApplySlot(W->Slot, **Slot, OutError))
					{
						OutError = FString::Printf(TEXT("'%s' slot: %s"), *T.Id, OutError.IsEmpty() ? TEXT("no slot after reparenting") : *OutError);
						return false;
					}
				}
				if (!WidgetMcpSpec::ApplyWidget(W, *T.Norm, Assets, OutError))
				{
					OutError = FString::Printf(TEXT("'%s': %s"), *T.Id, *OutError);
					return false;
				}
			}
			return true;
		}

		bool ReadPath(const FString& Path, TArray<FString>& Out)
		{
			Path.ParseIntoArray(Out, TEXT("."));
			return Out.Num() > 0;
		}
	}

	using namespace BlueprintPrivate;

	UWidgetBlueprint* Load(const FString& AssetPath, FEditorMcpError& OutError)
	{
		const FString Package = WidgetMcp::ToPackagePath(AssetPath);
		const FString ObjectPath = Package + TEXT(".") + FPackageName::GetShortName(Package);
		UWidgetBlueprint* WBP = FindObject<UWidgetBlueprint>(nullptr, *ObjectPath);
		if (!WBP && FPackageName::DoesPackageExist(Package))
		{
			WBP = LoadObject<UWidgetBlueprint>(nullptr, *ObjectPath, nullptr, LOAD_NoWarn);
		}
		if (!WBP || !WBP->WidgetTree)
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::AssetNotFound, FString::Printf(TEXT("No Widget Blueprint at '%s'"), *ObjectPath));
			return nullptr;
		}
		return WBP;
	}

	TArray<FBindWidget> BindWidgets(const UClass* Class)
	{
		TArray<FBindWidget> Out;
		if (!Class)
		{
			return Out;
		}
		for (TFieldIterator<FObjectProperty> It(Class); It; ++It)
		{
			bool bOptional = false;
			if (FWidgetBlueprintEditorUtils::IsBindWidgetProperty(*It, bOptional))
			{
				Out.Add({ It->GetName(), It->PropertyClass, bOptional });
			}
		}
		Out.Sort([](const FBindWidget& A, const FBindWidget& B) { return A.Name < B.Name; });
		return Out;
	}

	TArray<TSharedPtr<FJsonValue>> BindWidgetsJson(const TArray<FBindWidget>& Bindings)
	{
		TArray<TSharedPtr<FJsonValue>> Out;
		for (const FBindWidget& B : Bindings)
		{
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			J->SetStringField(TEXT("name"), B.Name);
			J->SetStringField(TEXT("widget_class"), GetNameSafe(B.WidgetClass));
			J->SetStringField(TEXT("widget_class_path"), GetPathNameSafe(B.WidgetClass));
			J->SetBoolField(TEXT("optional"), B.bOptional);
			Out.Add(MakeShared<FJsonValueObject>(J));
		}
		return Out;
	}

	TSharedRef<FJsonObject> ExportTree(const UWidgetTree* Tree, const WidgetMcpSpec::FAssets* Assets, TArray<TSharedPtr<FJsonValue>>& OutUnsupported, TArray<FString>& OutLocked)
	{
		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		TArray<TSharedPtr<FJsonValue>> Widgets;
		UWidget* Root = Tree ? Tree->RootWidget.Get() : nullptr;
		Out->SetStringField(TEXT("root"), Root ? Root->GetName() : FString());
		TFunction<void(const UWidget*, const UWidget*)> Visit = [&](const UWidget* W, const UWidget* Parent)
		{
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			const FString Id = W->GetName();
			J->SetStringField(TEXT("id"), Id);
			FString Type = WidgetMcpSpec::TypeForWidget(W);
			const bool bKnown = !Type.IsEmpty();
			if (!bKnown)
			{
				Type = W->GetClass()->GetName();
				OutLocked.Add(Id);
				TSharedRef<FJsonObject> U = MakeShared<FJsonObject>();
				U->SetStringField(TEXT("widget"), Id);
				U->SetStringField(TEXT("property"), TEXT("class"));
				U->SetStringField(TEXT("reason"), FString::Printf(TEXT("%s is not in the Phase 1 widget vocabulary — kept as-is and locked"), *Type));
				OutUnsupported.Add(MakeShared<FJsonValueObject>(U));
			}
			J->SetStringField(TEXT("type"), Type);
			if (Parent)
			{
				J->SetStringField(TEXT("parent"), Parent->GetName());
				if (TSharedPtr<FJsonObject> Slot = WidgetMcpSpec::ExportSlot(W->Slot))
				{
					J->SetObjectField(TEXT("slot"), Slot);
				}
				else
				{
					TSharedRef<FJsonObject> U = MakeShared<FJsonObject>();
					U->SetStringField(TEXT("widget"), Id);
					U->SetStringField(TEXT("property"), TEXT("slot"));
					U->SetStringField(TEXT("reason"), FString::Printf(TEXT("slot %s is not in the spec vocabulary"), W->Slot ? *W->Slot->GetClass()->GetName() : TEXT("(none)")));
					OutUnsupported.Add(MakeShared<FJsonValueObject>(U));
					OutLocked.AddUnique(Id);
				}
			}
			if (bKnown)
			{
				WidgetMcpSpec::ExportWidgetProps(W, Assets, J, OutUnsupported);
			}
			Widgets.Add(MakeShared<FJsonValueObject>(J));
			if (const UPanelWidget* Panel = Cast<UPanelWidget>(W))
			{
				for (int32 i = 0; i < Panel->GetChildrenCount(); ++i)
				{
					if (const UWidget* Child = Panel->GetChildAt(i))
					{
						Visit(Child, W);
					}
				}
			}
		};
		if (Root)
		{
			Visit(Root, nullptr);
		}
		Out->SetArrayField(TEXT("widgets"), Widgets);
		return Out;
	}

	FString Revision(const UWidgetBlueprint* WBP)
	{
		TArray<TSharedPtr<FJsonValue>> Unsupported;
		TArray<FString> Locked;
		TSharedRef<FJsonObject> Doc = MakeShared<FJsonObject>();
		Doc->SetStringField(TEXT("parent_class"), GetPathNameSafe(WBP->ParentClass));
		Doc->SetObjectField(TEXT("tree"), ExportTree(WBP->WidgetTree, nullptr, Unsupported, Locked));
		return WidgetMcp::Sha1Revision(WidgetMcp::CanonicalJson(Doc));
	}

	TSharedRef<FJsonObject> Compile(UWidgetBlueprint* WBP)
	{
		FCompilerResultsLog Log;
		Log.bSilentMode = true;
		FKismetEditorUtilities::CompileBlueprint(WBP, EBlueprintCompileOptions::SkipGarbageCollection, &Log);
		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		const bool bOk = WBP->GeneratedClass != nullptr && (WBP->Status == BS_UpToDate || WBP->Status == BS_UpToDateWithWarnings);
		Out->SetBoolField(TEXT("ok"), bOk);
		Out->SetStringField(TEXT("status"), WBP->Status == BS_UpToDate ? TEXT("up_to_date") : WBP->Status == BS_UpToDateWithWarnings ? TEXT("up_to_date_with_warnings")
			: WBP->Status == BS_Error ? TEXT("error") : TEXT("dirty"));
		Out->SetNumberField(TEXT("errors"), Log.NumErrors);
		Out->SetNumberField(TEXT("warnings"), Log.NumWarnings);
		TArray<TSharedPtr<FJsonValue>> Messages;
		for (const TSharedRef<FTokenizedMessage>& M : Log.Messages)
		{
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			const EMessageSeverity::Type Sev = M->GetSeverity();
			J->SetStringField(TEXT("level"), Sev == EMessageSeverity::Error ? TEXT("error") : Sev == EMessageSeverity::Warning || Sev == EMessageSeverity::PerformanceWarning ? TEXT("warning") : TEXT("info"));
			J->SetStringField(TEXT("text"), M->ToText().ToString());
			Messages.Add(MakeShared<FJsonValueObject>(J));
		}
		Out->SetArrayField(TEXT("messages"), Messages);
		TArray<TSharedPtr<FJsonValue>> Missing;
		for (const FBindWidget& B : BindWidgets(WBP->ParentClass))
		{
			UWidget* W = WBP->WidgetTree ? WBP->WidgetTree->FindWidget(FName(*B.Name)) : nullptr;
			if (W && W->IsA(B.WidgetClass))
			{
				continue;
			}
			if (!W && B.bOptional)
			{
				continue;
			}
			TSharedRef<FJsonObject> J = MakeShared<FJsonObject>();
			J->SetStringField(TEXT("name"), B.Name);
			J->SetStringField(TEXT("reason"), W ? TEXT("type") : TEXT("missing"));
			J->SetStringField(TEXT("expected"), GetNameSafe(B.WidgetClass));
			J->SetStringField(TEXT("actual"), W ? W->GetClass()->GetName() : FString());
			J->SetBoolField(TEXT("optional"), B.bOptional);
			Missing.Add(MakeShared<FJsonValueObject>(J));
		}
		Out->SetArrayField(TEXT("missing_bindings"), Missing);
		Out->SetStringField(TEXT("generated_class"), GetPathNameSafe(WBP->GeneratedClass));
		return Out;
	}

	TSharedPtr<FJsonObject> Create(const WidgetMcp::FSettings& Settings, const FString& AssetPath, const FString& ParentClassPath, const FString& RootIdIn,
		FEditorMcpContext& Context, FEditorMcpError& OutError)
	{
		const FString Package = WidgetMcp::ToPackagePath(AssetPath);
		if (!WidgetMcp::CheckOutputAsset(Settings, Package, TEXT("asset_path"), OutError))
		{
			return nullptr;
		}
		if (WidgetMcp::PackageExists(Package))
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::AssetExists, FString::Printf(TEXT("'%s' already exists — widget blueprints are never overwritten (new run folder)"), *Package), TEXT("OVERWRITE_NOT_ALLOWED"));
			return nullptr;
		}
		const FString RootId = RootIdIn.IsEmpty() ? FString(WidgetMcp::RootIdDefault) : RootIdIn;
		if (!IsIdentifier(RootId))
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("root_id '%s' is not [A-Za-z][A-Za-z0-9_]*"), *RootId));
			return nullptr;
		}
		UClass* Parent = UUserWidget::StaticClass();
		if (!ParentClassPath.IsEmpty())
		{
			Parent = LoadObject<UClass>(nullptr, *ParentClassPath, nullptr, LOAD_NoWarn);
			if (!Parent)
			{
				OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::TypeNotFound, FString::Printf(TEXT("parent_class '%s' does not load (C++ class path /Script/<Module>.<Class> — built and loaded?)"), *ParentClassPath));
				return nullptr;
			}
		}
		// UUserWidget 자체는 Abstract 지만 WBP 의 표준 부모다. 그 밖의 Abstract(생성 베이스 ViewBase)는 거부 — 부모는 사람 소유 스텁(설계 §3-3)
		const bool bAbstractBase = Parent != UUserWidget::StaticClass() && Parent->HasAnyClassFlags(CLASS_Abstract);
		if (!Parent->IsChildOf(UUserWidget::StaticClass()) || bAbstractBase || Parent->HasAnyClassFlags(CLASS_Deprecated | CLASS_NewerVersionExists))
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::TypeNotAllowed, FString::Printf(TEXT("parent_class '%s' must be a non-abstract UUserWidget subclass (use the stub, not the generated ViewBase)"), *GetPathNameSafe(Parent)));
			return nullptr;
		}
		const WidgetMcp::FWriteGuard Guard;
		UPackage* Pkg = CreatePackage(*Package);
		UWidgetBlueprintFactory* Factory = NewObject<UWidgetBlueprintFactory>(GetTransientPackage());
		Factory->ParentClass = Parent;
		UWidgetBlueprint* WBP = Cast<UWidgetBlueprint>(Factory->FactoryCreateNew(UWidgetBlueprint::StaticClass(), Pkg, FName(*FPackageName::GetShortName(Package)),
			RF_Public | RF_Standalone | RF_Transactional, nullptr, GWarn));
		if (!WBP || !WBP->WidgetTree)
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::Internal, TEXT("UWidgetBlueprintFactory::FactoryCreateNew returned no widget blueprint"));
			return nullptr;
		}
		FAssetRegistryModule::AssetCreated(WBP);
		// 설계 §12-1 A7 — 대화창 없는 팩토리는 루트를 만들지 않는다(이 프로젝트 설정). Canvas 를 직접 만들고 GUID 맵에 올린다
		if (!WBP->WidgetTree->RootWidget)
		{
			UCanvasPanel* Root = WBP->WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), FName(*RootId));
			Root->bIsVariable = true;
			WBP->WidgetTree->RootWidget = Root;
			WBP->OnVariableAdded(Root->GetFName());
		}
		else if (WBP->WidgetTree->RootWidget->GetName() != RootId)
		{
			const FName Old = WBP->WidgetTree->RootWidget->GetFName();
			WBP->WidgetTree->RootWidget->Rename(*RootId, nullptr, RenameFlags);
			WBP->OnVariableRenamed(Old, FName(*RootId));
			Context.AddDiagnostic(TEXT("info"), TEXT("ROOT_RENAMED"), FString::Printf(TEXT("factory root '%s' renamed to '%s'"), *Old.ToString(), *RootId));
		}
		Pkg->MarkPackageDirty();
		// 필수 BindWidget 이 있는 부모(스텁)는 빈 캔버스로 컴파일하면 'required widget binding … not found' 오류만 남긴다 — 그때는 apply 뒤에 컴파일
		const TArray<FBindWidget> ParentBindings = BindWidgets(Parent);
		const int32 Required = ParentBindings.FilterByPredicate([](const FBindWidget& B) { return !B.bOptional; }).Num();
		TSharedRef<FJsonObject> CompileResult = MakeShared<FJsonObject>();
		if (Required == 0)
		{
			CompileResult = Compile(WBP);
			CompileResult->SetBoolField(TEXT("ran"), true);
		}
		else
		{
			CompileResult->SetBoolField(TEXT("ran"), false);
			CompileResult->SetStringField(TEXT("reason"), FString::Printf(TEXT("parent has %d required BindWidget(s) — the empty canvas cannot compile; apply_widget_spec compiles"), Required));
		}
		TArray<FString> NewlyDirty;
		if (!Guard.Finish(Settings, OutError, NewlyDirty))
		{
			return nullptr;
		}
		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetStringField(TEXT("asset_path"), WBP->GetPathName());
		Out->SetStringField(TEXT("parent_class"), GetPathNameSafe(Parent));
		Out->SetStringField(TEXT("root"), WBP->WidgetTree->RootWidget->GetName());
		Out->SetStringField(TEXT("root_type"), WidgetMcpSpec::TypeForWidget(WBP->WidgetTree->RootWidget));
		Out->SetStringField(TEXT("revision"), Revision(WBP));
		Out->SetObjectField(TEXT("compile"), CompileResult);
		Out->SetArrayField(TEXT("bindings"), BindWidgetsJson(ParentBindings));
		Out->SetArrayField(TEXT("newly_dirty"), WidgetMcp::StringArray(NewlyDirty));
		Out->SetBoolField(TEXT("saved"), false);
		return Out;
	}

	TSharedPtr<FJsonObject> Reconcile(const WidgetMcp::FSettings& Settings, UWidgetBlueprint* WBP, const TSharedRef<FJsonObject>& Spec, const WidgetMcpSpec::FAssets& Assets,
		const FString& ExpectedRevision, bool bApply, bool bCompile, FEditorMcpContext& Context, FEditorMcpError& OutError)
	{
		if (!WidgetMcp::CheckOutputAsset(Settings, WBP->GetPathName(), TEXT("asset_path"), OutError))
		{
			return nullptr;
		}
		TArray<FString> Errors;
		FString RootId;
		Spec->TryGetStringField(TEXT("root"), RootId);
		const TArray<TSharedPtr<FJsonValue>>* WidgetArr = nullptr;
		if (!Spec->TryGetArrayField(TEXT("widgets"), WidgetArr) || RootId.IsEmpty())
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, TEXT("spec needs 'root' and 'widgets[]'"));
			return nullptr;
		}
		TSet<FString> LockedIds;
		const TArray<TSharedPtr<FJsonValue>>* LockedArr = nullptr;
		if (Spec->TryGetArrayField(TEXT("locked"), LockedArr))
		{
			for (const TSharedPtr<FJsonValue>& V : *LockedArr) { LockedIds.Add(V->AsString()); }
		}

		// ---- 지금 상태 --------------------------------------------------------------------------------------------
		TArray<TSharedPtr<FJsonValue>> CurrentUnsupported;
		TArray<FString> CurrentLocked;
		const TSharedRef<FJsonObject> CurrentTree = ExportTree(WBP->WidgetTree, &Assets, CurrentUnsupported, CurrentLocked);
		TMap<FString, FCurrent> Current;
		TArray<FString> CurrentOrder;
		WidgetsById(CurrentTree, Current, CurrentOrder);
		const FString CurrentRoot = CurrentTree->GetStringField(TEXT("root"));

		// ---- 목표 파싱 · 검사 ---------------------------------------------------------------------------------------
		TArray<FTarget> Raw;
		TMap<FString, int32> RawIndex;
		for (const TSharedPtr<FJsonValue>& V : *WidgetArr)
		{
			FTarget T;
			T.Json = V.IsValid() ? V->AsObject() : nullptr;
			T.Id = Str(T.Json, TEXT("id"));
			T.Type = Str(T.Json, TEXT("type"));
			T.Parent = Str(T.Json, TEXT("parent"));
			if (!IsIdentifier(T.Id))
			{
				AddError(Errors, TEXT("BAD_ID"), FString::Printf(TEXT("widget id '%s' is not [A-Za-z][A-Za-z0-9_]{0,63}"), *T.Id));
				continue;
			}
			if (RawIndex.Contains(T.Id))
			{
				AddError(Errors, TEXT("DUPLICATE_ID"), T.Id);
				continue;
			}
			T.Class = WidgetMcpSpec::ClassForType(T.Type);
			if (!T.Class)
			{
				const FCurrent* C = Current.Find(T.Id);
				if (LockedIds.Contains(T.Id) && C && Str(C->Json, TEXT("type")) == T.Type)
				{
					T.bKeepUnsupported = true;
				}
				else
				{
					AddError(Errors, TEXT("TYPE_NOT_ALLOWED"), FString::Printf(TEXT("'%s' type '%s' is not in the widget vocabulary"), *T.Id, *T.Type));
					continue;
				}
			}
			RawIndex.Add(T.Id, Raw.Num());
			Raw.Add(T);
		}
		if (!RawIndex.Contains(RootId))
		{
			AddError(Errors, TEXT("NO_ROOT"), FString::Printf(TEXT("root '%s' is not in widgets[]"), *RootId));
		}
		else if (!Raw[RawIndex[RootId]].Parent.IsEmpty())
		{
			AddError(Errors, TEXT("ROOT_HAS_PARENT"), RootId);
		}
		if (!CurrentRoot.IsEmpty() && RawIndex.Contains(RootId) && (CurrentRoot != RootId || Str(Current[CurrentRoot].Json, TEXT("type")) != Raw[RawIndex[RootId]].Type))
		{
			AddError(Errors, TEXT("ROOT_MISMATCH"), FString::Printf(TEXT("the blueprint root is '%s' (%s); the spec root is '%s' (%s) — the root never changes"),
				*CurrentRoot, *Str(Current[CurrentRoot].Json, TEXT("type")), *RootId, *Raw[RawIndex[RootId]].Type));
		}
		TMap<FString, TArray<FString>> Kids;
		for (const FTarget& T : Raw)
		{
			if (T.Id == RootId)
			{
				continue;
			}
			const int32* ParentIdx = RawIndex.Find(T.Parent);
			if (!ParentIdx)
			{
				AddError(Errors, TEXT("PARENT_NOT_FOUND"), FString::Printf(TEXT("'%s' → '%s'"), *T.Id, *T.Parent));
				continue;
			}
			const FString& ParentType = Raw[*ParentIdx].Type;
			const FString Kind = WidgetMcpSpec::ChildSlotKind(ParentType);
			if (Kind.IsEmpty() && !Raw[*ParentIdx].bKeepUnsupported)
			{
				AddError(Errors, TEXT("PARENT_IS_LEAF"), FString::Printf(TEXT("'%s' under %s '%s'"), *T.Id, *ParentType, *T.Parent));
				continue;
			}
			const TSharedPtr<FJsonObject>* Slot = nullptr;
			if (T.Json->TryGetObjectField(TEXT("slot"), Slot) && Str(*Slot, TEXT("kind")) != Kind && !Str(*Slot, TEXT("kind")).IsEmpty())
			{
				AddError(Errors, TEXT("SLOT_KIND"), FString::Printf(TEXT("'%s' slot.kind '%s' but parent '%s' is a %s (needs '%s')"), *T.Id, *Str(*Slot, TEXT("kind")), *T.Parent, *ParentType, *Kind));
			}
			Kids.FindOrAdd(T.Parent).Add(T.Id);
		}
		for (const TPair<FString, TArray<FString>>& P : Kids)
		{
			const int32* ParentIdx = RawIndex.Find(P.Key);
			if (ParentIdx && WidgetMcpSpec::IsSingleChild(Raw[*ParentIdx].Type) && P.Value.Num() > 1)
			{
				AddError(Errors, TEXT("TOO_MANY_CHILDREN"), FString::Printf(TEXT("%s '%s' holds one child, has %d"), *Raw[*ParentIdx].Type, *P.Key, P.Value.Num()));
			}
		}
		// 트리 순서(깊이 우선) + 도달 검사
		TArray<FTarget> Targets;
		TMap<FString, int32> TargetIndex;
		if (RawIndex.Contains(RootId))
		{
			TArray<FString> Stack = { RootId };
			while (Stack.Num())
			{
				const FString Id = Stack.Pop();
				if (TargetIndex.Contains(Id))
				{
					AddError(Errors, TEXT("CYCLE"), Id);
					break;
				}
				TargetIndex.Add(Id, Targets.Num());
				Targets.Add(Raw[RawIndex[Id]]);
				const TArray<FString> Children = Kids.FindRef(Id);
				for (int32 i = Children.Num() - 1; i >= 0; --i) { Stack.Push(Children[i]); }
			}
		}
		for (const FTarget& T : Raw)
		{
			if (!TargetIndex.Contains(T.Id))
			{
				AddError(Errors, TEXT("UNREACHABLE"), FString::Printf(TEXT("'%s' is not under root '%s'"), *T.Id, *RootId));
			}
		}
		// 위젯마다 값 검사 · 정규화
		for (FTarget& T : Targets)
		{
			if (T.bKeepUnsupported)
			{
				continue;
			}
			FString Problem;
			if (!WidgetMcpSpec::ValidateWidget(*T.Json, T.Type, Assets, Problem))
			{
				AddError(Errors, TEXT("BAD_VALUE"), Problem);
				continue;
			}
			const FString ParentType = T.Parent.IsEmpty() ? FString() : Targets[TargetIndex[T.Parent]].Type;
			T.Norm = WidgetMcpSpec::NormalizeWidget(T.Json.ToSharedRef(), ParentType, Assets);
		}
		// 바인딩 — 추가만 · 타입 일치
		const TArray<FBindWidget> Bindings = BindWidgets(WBP->ParentClass);
		TArray<TSharedPtr<FJsonValue>> MissingBindings;
		for (const FBindWidget& B : Bindings)
		{
			const int32* TI = TargetIndex.Find(B.Name);
			if (!TI)
			{
				if (Current.Contains(B.Name))
				{
					AddError(Errors, TEXT("BINDING_REMOVAL"), FString::Printf(TEXT("'%s' is bound by %s (BindWidget%s) — bound widgets cannot be removed (bindings only grow)"),
						*B.Name, *GetNameSafe(WBP->ParentClass), B.bOptional ? TEXT("Optional") : TEXT("")));
				}
				else if (!B.bOptional)
				{
					TSharedRef<FJsonObject> M = MakeShared<FJsonObject>();
					M->SetStringField(TEXT("name"), B.Name);
					M->SetStringField(TEXT("expected"), GetNameSafe(B.WidgetClass));
					MissingBindings.Add(MakeShared<FJsonValueObject>(M));
				}
				continue;
			}
			const FTarget& T = Targets[*TI];
			if (T.Class && !T.Class->IsChildOf(B.WidgetClass))
			{
				AddError(Errors, TEXT("BINDING_TYPE"), FString::Printf(TEXT("'%s' is a %s but %s binds it as %s"), *T.Id, *T.Type, *GetNameSafe(WBP->ParentClass), *GetNameSafe(B.WidgetClass)));
			}
		}
		// locked — 지금과 같아야 한다
		for (const FString& Id : LockedIds)
		{
			const int32* TI = TargetIndex.Find(Id);
			const FCurrent* C = Current.Find(Id);
			if (!TI || !C)
			{
				AddError(Errors, TEXT("LOCKED"), FString::Printf(TEXT("locked widget '%s' must exist in both the blueprint and the spec"), *Id));
				continue;
			}
			const FTarget& T = Targets[*TI];
			if (T.Parent != C->Parent)
			{
				AddError(Errors, TEXT("LOCKED"), FString::Printf(TEXT("locked widget '%s' cannot move ('%s' → '%s')"), *Id, *C->Parent, *T.Parent));
				continue;
			}
			if (!T.bKeepUnsupported && T.Norm.IsValid())
			{
				TArray<FString> Diffs;
				WidgetMcp::DiffJson(MakeShared<FJsonValueObject>(C->Json), MakeShared<FJsonValueObject>(WidgetMcpSpec::WbpView(T.Norm.ToSharedRef())), Id, Diffs, 5);
				if (Diffs.Num())
				{
					AddError(Errors, TEXT("LOCKED"), FString::Printf(TEXT("locked widget '%s' would change: %s"), *Id, *FString::Join(Diffs, TEXT("; "))));
				}
			}
		}

		// ---- op 계산(보고용) ----------------------------------------------------------------------------------------
		TArray<TSharedPtr<FJsonValue>> Ops;
		TMap<FString, int32> TargetSiblingIndex;
		{
			TMap<FString, int32> Count;
			for (const FTarget& T : Targets) { TargetSiblingIndex.Add(T.Id, Count.FindOrAdd(T.Parent)++); }
		}
		for (const FString& Id : CurrentOrder)
		{
			if (!TargetIndex.Contains(Id))
			{
				Ops.Add(MakeShared<FJsonValueObject>(Op(TEXT("remove_widget"), Id)));
			}
		}
		for (const FTarget& T : Targets)
		{
			const FCurrent* C = Current.Find(T.Id);
			if (!C)
			{
				TSharedRef<FJsonObject> O = Op(TEXT("add_widget"), T.Id);
				O->SetStringField(TEXT("type"), T.Type);
				O->SetStringField(TEXT("parent"), T.Parent);
				Ops.Add(MakeShared<FJsonValueObject>(O));
				continue;
			}
			if (Str(C->Json, TEXT("type")) != T.Type)
			{
				TSharedRef<FJsonObject> O = Op(TEXT("replace_widget"), T.Id);
				O->SetStringField(TEXT("from"), Str(C->Json, TEXT("type")));
				O->SetStringField(TEXT("to"), T.Type);
				Ops.Add(MakeShared<FJsonValueObject>(O));
				continue;
			}
			if (C->Parent != T.Parent || C->Index != TargetSiblingIndex[T.Id])
			{
				TSharedRef<FJsonObject> O = Op(TEXT("move"), T.Id);
				O->SetStringField(TEXT("parent"), T.Parent);
				O->SetNumberField(TEXT("index"), TargetSiblingIndex[T.Id]);
				Ops.Add(MakeShared<FJsonValueObject>(O));
			}
			if (!T.Norm.IsValid())
			{
				continue;
			}
			const TSharedRef<FJsonObject> View = WidgetMcpSpec::WbpView(T.Norm.ToSharedRef());
			for (const FString& Key : FieldKeys(View, C->Json))
			{
				const TSharedPtr<FJsonValue> A = Field(C->Json, Key);
				const TSharedPtr<FJsonValue> B = Field(View, Key);
				if ((A.IsValid() ? WidgetMcp::CanonicalJson(A) : FString()) != (B.IsValid() ? WidgetMcp::CanonicalJson(B) : FString()))
				{
					TSharedRef<FJsonObject> O = Op(TEXT("set"), T.Id);
					O->SetStringField(TEXT("path"), Key);
					O->SetField(TEXT("value"), B.IsValid() ? B : MakeShared<FJsonValueNull>());
					Ops.Add(MakeShared<FJsonValueObject>(O));
				}
			}
		}

		const FString RevisionBefore = Revision(WBP);
		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetStringField(TEXT("asset_path"), WBP->GetPathName());
		Out->SetArrayField(TEXT("ops"), Ops);
		Out->SetArrayField(TEXT("missing_bindings"), MissingBindings);
		Out->SetArrayField(TEXT("unsupported"), CurrentUnsupported);
		if (!bApply)
		{
			Out->SetBoolField(TEXT("valid"), Errors.Num() == 0);
			Out->SetArrayField(TEXT("errors"), WidgetMcp::StringArray(Errors));
			Out->SetStringField(TEXT("revision"), RevisionBefore);
			return Out;
		}
		if (Errors.Num())
		{
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetArrayField(TEXT("errors"), WidgetMcp::StringArray(Errors));
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("spec failed validation (%d error(s)) — nothing was applied: %s"), Errors.Num(), *Errors[0]), *FirstCode(Errors), D);
			return nullptr;
		}
		if (ExpectedRevision.IsEmpty())
		{
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, TEXT("expected_revision is required (from create_widget_blueprint / export_widget_spec / the last apply)"), TEXT("NO_EXPECTED_REVISION"));
			return nullptr;
		}
		if (ExpectedRevision != RevisionBefore)
		{
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetStringField(TEXT("expected"), ExpectedRevision);
			D->SetStringField(TEXT("actual"), RevisionBefore);
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::RevisionMismatch, TEXT("The widget blueprint changed since that revision — export again; nothing was applied"), nullptr, D);
			return nullptr;
		}

		// ---- 사본에 적용 → 확인 → 바꿔 끼우기 ---------------------------------------------------------------------------
		const WidgetMcp::FWriteGuard Guard;
		UWidgetTree* Live = WBP->WidgetTree;
		UWidgetTree* Work = DuplicateObject<UWidgetTree>(Live, GetTransientPackage(), MakeUniqueObjectName(GetTransientPackage(), UWidgetTree::StaticClass(), TEXT("WidgetMcpWorkTree")));
		TStrongObjectPtr<UWidgetTree> KeepWork(Work);
		TSet<FString> Replaced;
		FString ApplyError;
		bool bOk = ApplyToTree(Work, Targets, TargetIndex, RootId, Assets, Replaced, ApplyError);
		TArray<FString> VerifyDiffs;
		if (bOk)
		{
			TArray<TSharedPtr<FJsonValue>> U;
			TArray<FString> L;
			const TSharedRef<FJsonObject> Applied = ExportTree(Work, &Assets, U, L);
			TArray<TSharedPtr<FJsonValue>> Expected;
			for (const FTarget& T : Targets)
			{
				if (T.bKeepUnsupported)
				{
					const FCurrent* C = Current.Find(T.Id);
					Expected.Add(MakeShared<FJsonValueObject>(C ? C->Json.ToSharedRef() : MakeShared<FJsonObject>()));
				}
				else
				{
					Expected.Add(MakeShared<FJsonValueObject>(WidgetMcpSpec::WbpView(T.Norm.ToSharedRef())));
				}
			}
			WidgetMcp::DiffJson(MakeShared<FJsonValueArray>(Expected), Applied->Values.FindRef(TEXT("widgets")), TEXT("widgets"), VerifyDiffs, 40);
			if (VerifyDiffs.Num())
			{
				bOk = false;
				ApplyError = FString::Printf(TEXT("applied tree differs from the spec in %d place(s) — first: %s"), VerifyDiffs.Num(), *VerifyDiffs[0]);
			}
		}
		if (!bOk)
		{
			Work->Rename(*MakeUniqueObjectName(GetTransientPackage(), UWidgetTree::StaticClass(), TEXT("WidgetMcpDiscardedTree")).ToString(), GetTransientPackage(), RenameFlags);
			const bool bRollbackVerified = Revision(WBP) == RevisionBefore;
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetArrayField(TEXT("verify_diffs"), WidgetMcp::StringArray(VerifyDiffs));
			D->SetBoolField(TEXT("rollback_verified"), bRollbackVerified);
			D->SetStringField(TEXT("revision"), RevisionBefore);
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::ValidationFailed, ApplyError + TEXT(" — the blueprint was left unchanged"), VerifyDiffs.Num() ? TEXT("APPLY_MISMATCH") : TEXT("APPLY_FAILED"), D);
			return nullptr;
		}

		const FString TreeName = Live->GetName();
		Live->Rename(*MakeUniqueObjectName(GetTransientPackage(), UWidgetTree::StaticClass(), TEXT("WidgetMcpOldTree")).ToString(), GetTransientPackage(), RenameFlags);
		Work->Rename(*TreeName, WBP, RenameFlags);
		Work->ClearFlags(RF_Transient);
		Work->SetFlags(RF_Transactional);
		WBP->WidgetTree = Work;
		Live->MarkAsGarbage();

		TSet<FName> Names;
		Work->ForEachWidget([&Names](UWidget* W) { Names.Add(W->GetFName()); });
		TArray<FName> Keys;
		WBP->WidgetVariableNameToGuidMap.GetKeys(Keys);
		for (const FName& K : Keys)
		{
			if (!Names.Contains(K) || Replaced.Contains(K.ToString()))
			{
				WBP->OnVariableRemoved(K);
			}
		}
		for (const FName& N : Names)
		{
			if (!WBP->WidgetVariableNameToGuidMap.Contains(N))
			{
				WBP->OnVariableAdded(N);
			}
		}
		FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(WBP);
		WBP->MarkPackageDirty();
		if (bCompile)
		{
			Out->SetObjectField(TEXT("compile"), Compile(WBP));
		}
		TArray<FString> NewlyDirty;
		if (!Guard.Finish(Settings, OutError, NewlyDirty))
		{
			return nullptr;
		}
		Out->SetStringField(TEXT("revision_before"), RevisionBefore);
		Out->SetStringField(TEXT("revision_after"), Revision(WBP));
		Out->SetNumberField(TEXT("applied"), Ops.Num());
		Out->SetBoolField(TEXT("verified"), true);
		Out->SetNumberField(TEXT("guid_map_count"), WBP->WidgetVariableNameToGuidMap.Num());
		Out->SetArrayField(TEXT("newly_dirty"), WidgetMcp::StringArray(NewlyDirty));
		Out->SetBoolField(TEXT("saved"), false);
		UE_LOG(LogAnimGraphMcp, Log, TEXT("apply_widget_spec: %s — %d op(s), %s -> %s"), *WBP->GetPathName(), Ops.Num(), *RevisionBefore, *Out->GetStringField(TEXT("revision_after")));
		return Out;
	}

	TSharedPtr<FJsonObject> PatchTarget(UWidgetBlueprint* WBP, const TArray<TSharedPtr<FJsonValue>>& Ops, const WidgetMcpSpec::FAssets& Assets, FEditorMcpError& OutError)
	{
		TArray<TSharedPtr<FJsonValue>> Unsupported;
		TArray<FString> Locked;
		const TSharedRef<FJsonObject> Tree = ExportTree(WBP->WidgetTree, &Assets, Unsupported, Locked);
		TArray<TSharedPtr<FJsonObject>> Widgets;
		for (const TSharedPtr<FJsonValue>& V : Tree->GetArrayField(TEXT("widgets"))) { Widgets.Add(V->AsObject()); }
		auto Find = [&Widgets](const FString& Id) -> int32 { return Widgets.IndexOfByPredicate([&Id](const TSharedPtr<FJsonObject>& W) { return Str(W, TEXT("id")) == Id; }); };
		auto Descendants = [&Widgets](const FString& Id)
		{
			TArray<FString> Out;
			TArray<FString> Stack = { Id };
			while (Stack.Num())
			{
				const FString P = Stack.Pop();
				for (const TSharedPtr<FJsonObject>& W : Widgets) { if (Str(W, TEXT("parent")) == P) { Out.Add(Str(W, TEXT("id"))); Stack.Push(Str(W, TEXT("id"))); } }
			}
			return Out;
		};
		auto InsertAt = [&Widgets](const TSharedPtr<FJsonObject>& W, const FString& Parent, int32 Index)
		{
			TArray<int32> Siblings;
			for (int32 i = 0; i < Widgets.Num(); ++i) { if (Str(Widgets[i], TEXT("parent")) == Parent) { Siblings.Add(i); } }
			int32 Pos;
			if (Index < 0 || Index >= Siblings.Num())
			{
				Pos = Siblings.Num() ? Siblings.Last() + 1 : Widgets.IndexOfByPredicate([&Parent](const TSharedPtr<FJsonObject>& X) { return Str(X, TEXT("id")) == Parent; }) + 1;
			}
			else
			{
				Pos = Siblings[Index];
			}
			Widgets.Insert(W, Pos);
		};
		auto Fail = [&OutError](int32 Index, const TCHAR* Reason, const FString& Message) -> TSharedPtr<FJsonObject>
		{
			TSharedRef<FJsonObject> D = MakeShared<FJsonObject>();
			D->SetNumberField(TEXT("op_index"), Index);
			OutError = WidgetMcp::MakeMcpError(EditorMcpErrorCodes::BadRequest, FString::Printf(TEXT("op %d: %s — nothing was applied"), Index, *Message), Reason, D);
			return nullptr;
		};
		for (int32 i = 0; i < Ops.Num(); ++i)
		{
			const TSharedPtr<FJsonObject> O = Ops[i].IsValid() ? Ops[i]->AsObject() : nullptr;
			const FString Kind = Str(O, TEXT("op"));
			if (Kind == TEXT("set"))
			{
				const FString Id = Str(O, TEXT("widget"));
				const int32 Idx = Find(Id);
				TArray<FString> Parts;
				if (Idx == INDEX_NONE) { return Fail(i, TEXT("NOT_FOUND"), FString::Printf(TEXT("no widget '%s'"), *Id)); }
				if (!ReadPath(Str(O, TEXT("path")), Parts)) { return Fail(i, TEXT("BAD_OP"), TEXT("set needs a path")); }
				if (Parts[0] == TEXT("id") || Parts[0] == TEXT("type") || Parts[0] == TEXT("parent") || (Parts[0] == TEXT("slot") && Parts.Num() > 1 && Parts[1] == TEXT("kind")))
				{
					return Fail(i, TEXT("BAD_OP"), FString::Printf(TEXT("'%s' cannot be set (use move / remove_widget + add_widget)"), *Str(O, TEXT("path"))));
				}
				if (Parts[0] == TEXT("binding"))
				{
					return Fail(i, TEXT("PIPELINE_ONLY"), TEXT("binding changes go through codegen (Tools/uigen) — the bridge only edits the blueprint"));
				}
				TSharedPtr<FJsonObject> Node = Widgets[Idx];
				for (int32 p = 0; p + 1 < Parts.Num(); ++p)
				{
					const TSharedPtr<FJsonObject>* Next = nullptr;
					if (!Node->TryGetObjectField(Parts[p], Next))
					{
						TSharedRef<FJsonObject> Fresh = MakeShared<FJsonObject>();
						Node->SetObjectField(Parts[p], Fresh);
						Node = Fresh;
					}
					else
					{
						Node = *Next;
					}
				}
				const TSharedPtr<FJsonValue> Value = O->Values.FindRef(TEXT("value"));
				if (!Value.IsValid() || Value->IsNull()) { Node->RemoveField(Parts.Last()); }
				else { Node->SetField(Parts.Last(), Value); }
			}
			else if (Kind == TEXT("add_widget"))
			{
				const TSharedPtr<FJsonObject>* W = nullptr;
				if (!O->TryGetObjectField(TEXT("widget"), W)) { return Fail(i, TEXT("BAD_OP"), TEXT("add_widget needs widget{}")); }
				const FString Id = Str(*W, TEXT("id"));
				const FString Parent = Str(*W, TEXT("parent"));
				if (Find(Id) != INDEX_NONE) { return Fail(i, TEXT("DUPLICATE_ID"), FString::Printf(TEXT("'%s' already exists"), *Id)); }
				if (Find(Parent) == INDEX_NONE) { return Fail(i, TEXT("NOT_FOUND"), FString::Printf(TEXT("parent '%s' does not exist"), *Parent)); }
				InsertAt(*W, Parent, static_cast<int32>(O->HasField(TEXT("index")) ? O->GetNumberField(TEXT("index")) : -1));
			}
			else if (Kind == TEXT("remove_widget"))
			{
				const FString Id = Str(O, TEXT("widget"));
				if (Find(Id) == INDEX_NONE) { return Fail(i, TEXT("NOT_FOUND"), FString::Printf(TEXT("no widget '%s'"), *Id)); }
				if (Id == Tree->GetStringField(TEXT("root"))) { return Fail(i, TEXT("BAD_OP"), TEXT("the root cannot be removed")); }
				TArray<FString> Gone = Descendants(Id);
				Gone.Add(Id);
				Widgets.RemoveAll([&Gone](const TSharedPtr<FJsonObject>& W) { return Gone.Contains(Str(W, TEXT("id"))); });
			}
			else if (Kind == TEXT("move"))
			{
				const FString Id = Str(O, TEXT("widget"));
				const FString Parent = Str(O, TEXT("parent"));
				const int32 Idx = Find(Id);
				const int32 PIdx = Find(Parent);
				if (Idx == INDEX_NONE || PIdx == INDEX_NONE) { return Fail(i, TEXT("NOT_FOUND"), FString::Printf(TEXT("'%s' or '%s' does not exist"), *Id, *Parent)); }
				if (Id == Tree->GetStringField(TEXT("root"))) { return Fail(i, TEXT("BAD_OP"), TEXT("the root cannot be moved")); }
				if (Parent == Id || Descendants(Id).Contains(Parent)) { return Fail(i, TEXT("CYCLE"), FString::Printf(TEXT("'%s' is '%s' or below it"), *Parent, *Id)); }
				TSharedPtr<FJsonObject> W = Widgets[Idx];
				const FString OldKind = WidgetMcpSpec::ChildSlotKind(Str(Widgets[Find(Str(W, TEXT("parent")))], TEXT("type")));
				const FString NewKind = WidgetMcpSpec::ChildSlotKind(Str(Widgets[PIdx], TEXT("type")));
				Widgets.RemoveAt(Idx);
				W->SetStringField(TEXT("parent"), Parent);
				const TSharedPtr<FJsonObject>* Slot = nullptr;
				if (O->TryGetObjectField(TEXT("slot"), Slot)) { W->SetObjectField(TEXT("slot"), *Slot); }
				else if (OldKind != NewKind)
				{
					TSharedRef<FJsonObject> Fresh = MakeShared<FJsonObject>();
					Fresh->SetStringField(TEXT("kind"), NewKind);
					W->SetObjectField(TEXT("slot"), Fresh);
				}
				InsertAt(W, Parent, static_cast<int32>(O->HasField(TEXT("index")) ? O->GetNumberField(TEXT("index")) : -1));
			}
			else if (Kind == TEXT("replace_asset"))
			{
				return Fail(i, TEXT("PIPELINE_ONLY"), TEXT("replace_asset regenerates a texture — run it through Tools/uigen (generate → refine → import), then apply the spec"));
			}
			else
			{
				return Fail(i, TEXT("BAD_OP"), FString::Printf(TEXT("unknown op '%s'"), *Kind));
			}
		}
		TSharedRef<FJsonObject> Out = MakeShared<FJsonObject>();
		Out->SetStringField(TEXT("root"), Tree->GetStringField(TEXT("root")));
		TArray<TSharedPtr<FJsonValue>> Arr;
		for (const TSharedPtr<FJsonObject>& W : Widgets) { Arr.Add(MakeShared<FJsonValueObject>(W)); }
		Out->SetArrayField(TEXT("widgets"), Arr);
		Out->SetArrayField(TEXT("locked"), WidgetMcp::StringArray(Locked));
		return Out;
	}
}
