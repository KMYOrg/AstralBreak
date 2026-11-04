#include "AnimMcpTools.h"

#include "Bridge/AnimMcpDispatcher.h"
#include "Bridge/AnimMcpTypes.h"
#include "Core/AnimMcpPromote.h"

// AI 애니 생성 Phase 7 — 후보 → 정식 경로 승격 (Docs/AIAnimation/DevelopmentGuide.md §12 · §14 Phase 7). 규칙 · 검증은 Core/AnimMcpPromote.
namespace AnimMcpTools
{
	void RegisterPromoteTools(FAnimMcpDispatcher& Dispatcher)
	{
		Dispatcher.RegisterTool(TEXT("promote_animation"),
			TEXT("Move generated candidate animation assets (inside [AnimGraphMcp] GenerationOutputPaths) to their production paths (inside [AnimGraphMcp] PromotionPaths) with the engine's AssetTools rename — no redirectors are left, referencers are fixed. "
			     "Params: assets [{source, dest}] (full asset paths; AnimSequence · AnimMontage · AnimComposite · BlendSpace incl. 1D/AimOffset), dry_run? (default false; same checks, changes nothing, needs no confirm), confirm (must be true unless dry_run), "
			     "allow_referencers? [package paths] (referencers outside the candidate paths that the engine may fix and save — otherwise ASSET_REFERENCED REFERENCED_OUTSIDE_CANDIDATES). "
			     "Refused: source not a candidate · unsupported class · dest outside PromotionPaths / inside the candidate paths / protected / existing (incl. redirector) · duplicates · referenced by a map · a referencer with unsaved changes (DIRTY_PACKAGES REFERENCER_DIRTY) · a native class default object referencing it (PROMOTE_FAILED CDO_REFERENCED). "
			     "The engine saves the moved and referencing packages itself (no save param). Verified after the move: no asset or redirector at the old path, old file gone, same class and content hash, referencers point at the new path, no package outside candidates ∪ dests ∪ allow_referencers dirtied or saved (UNEXPECTED_DIRTY — reported, not reverted). "
			     "Returns {dry_run, planned[{source, dest, class, content_hash, referencers[{package, candidate, allowed}]}], moved[{source, dest, class, content_hash, same_content}], fixed_referencers[], saved_packages[], redirectors, removed_files[]}."),
			[](FAnimMcpContext& Context, FAnimMcpError& OutError) -> TSharedPtr<FJsonObject>
			{
				AnimMcpPromote::FRequest Request;
				if (!AnimMcpPromote::ParseRequest(Context.Request.Params, Request, OutError)) { return nullptr; }
				return AnimMcpPromote::Run(Request, Context, OutError);
			});
	}
}
