#pragma once

#include "CoreMinimal.h"

class FAnimMcpDispatcher;

/** StateTree Tool 등록 — 모듈 시작 때 IEditorMcpCoreModule::RegisterTools("StateTreeMcp", …) 안에서 부른다 */
namespace StateTreeMcpTools
{
	/** StateTree 저작 고리 (create · inspect · list_*_types · list_*_sources · preview · apply · compile · revert) — Docs/StateTree Phase 1 · (run_state_tree_scenario) 런타임 고리 — Phase 2 */
	void RegisterStateTreeTools(FAnimMcpDispatcher& Dispatcher);
}
