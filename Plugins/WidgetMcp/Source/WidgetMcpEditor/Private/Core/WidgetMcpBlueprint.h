#pragma once

#include "CoreMinimal.h"
#include "Core/WidgetMcpCommon.h"
#include "Core/WidgetMcpSpec.h"

class UWidgetBlueprint;
class UWidgetTree;

/**
 * WBP 단위 — 생성 · 트리 역추출 · revision · 컴파일 · 바인딩 계약 · 조정기 (설계 §6 · §4-4 · §9).
 *
 * 조정기(preview/apply): 지금 WBP 와 목표 spec 의 차이를 op 로 계산하고, 전체를 먼저 검사한 뒤 적용한다.
 *   적용은 '사본에 짓고 바꿔 끼우기' — WidgetTree 를 트랜지언트로 복제해 거기에 op 를 적용하고, 사본을 역추출해 목표와 같은지
 *   확인한 다음에만 WBP 의 WidgetTree 와 바꾼다. 어느 단계든 실패하면 원본은 손대지 않은 그대로다(rollback_verified = revision 불변).
 *   GUID 맵은 바꾼 뒤 이름 차이로 OnVariableAdded / OnVariableRemoved 를 부른다(WidgetBlueprint.h:259-261 — 비어 있지 않은 맵에
 *   그냥 더하면 컴파일러 ensureAlways, WidgetBlueprintCompiler.cpp:794).
 * revision = (부모 클래스 + 역추출 트리)의 정규 JSON SHA1. apply 는 expected_revision 이 다르면 REVISION_MISMATCH 로 무변경.
 * 바인딩은 추가만 — 부모 클래스의 BindWidget 위젯을 목표에서 빼면 BINDING_REMOVAL, 타입이 안 맞으면 BINDING_TYPE.
 * spec.locked 의 위젯은 지금과 같아야 한다(LOCKED).
 */
namespace WidgetMcpBlueprint
{
	struct FBindWidget
	{
		FString Name;
		UClass* WidgetClass = nullptr;
		bool bOptional = false;
	};

	UWidgetBlueprint* Load(const FString& AssetPath, FEditorMcpError& OutError);

	/** 클래스의 BindWidget 프로퍼티(상속 포함, 이름 순) — FWidgetBlueprintEditorUtils::IsBindWidgetProperty (WidgetBlueprintEditorUtils.h:104) */
	TArray<FBindWidget> BindWidgets(const UClass* Class);
	TArray<TSharedPtr<FJsonValue>> BindWidgetsJson(const TArray<FBindWidget>& Bindings);

	/** 트리 역추출 → {root, widgets[]}. 어휘 밖 위젯 · 속성은 OutUnsupported, 어휘 밖 위젯 id 는 OutLocked */
	TSharedRef<FJsonObject> ExportTree(const UWidgetTree* Tree, const WidgetMcpSpec::FAssets* Assets, TArray<TSharedPtr<FJsonValue>>& OutUnsupported, TArray<FString>& OutLocked);
	FString Revision(const UWidgetBlueprint* WBP);

	/** 컴파일 → {ok, status, errors, warnings, messages[], missing_bindings[]} */
	TSharedRef<FJsonObject> Compile(UWidgetBlueprint* WBP);

	TSharedPtr<FJsonObject> Create(const WidgetMcp::FSettings& Settings, const FString& AssetPath, const FString& ParentClassPath, const FString& RootId,
		FEditorMcpContext& Context, FEditorMcpError& OutError);

	/** bApply=false 면 preview(무변경). Spec = {root, widgets[], locked[]?} */
	TSharedPtr<FJsonObject> Reconcile(const WidgetMcp::FSettings& Settings, UWidgetBlueprint* WBP, const TSharedRef<FJsonObject>& Spec, const WidgetMcpSpec::FAssets& Assets,
		const FString& ExpectedRevision, bool bApply, bool bCompile, FEditorMcpContext& Context, FEditorMcpError& OutError);

	/** spec patch(set · add_widget · remove_widget · move) 를 지금 트리의 역추출에 적용한 목표 spec. replace_asset · binding 은 파이프라인 몫이라 거부 */
	TSharedPtr<FJsonObject> PatchTarget(UWidgetBlueprint* WBP, const TArray<TSharedPtr<FJsonValue>>& Ops, const WidgetMcpSpec::FAssets& Assets, FEditorMcpError& OutError);
}
