"""anim-gen-mcp 서버 — stdio 전송. Claude Code 가 .mcp.json 으로 띄운다 (지침서 §3.1 · §14 Phase 3).

정책 · 라우터 · 폴백 · Job 은 service.py, 에디터 조작은 anim_graph_mcp/bridge.py 로 플러그인 Tool 을 부른다.
실행: Tools/mcp/.venv/Scripts/python.exe Tools/mcp/anim_gen/server.py
"""
from __future__ import annotations

import logging
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# mcp 2.x: FastMCP 가 MCPServer 로 개명됨 (mcp.server.mcpserver). requirements.txt 가 2.x 를 고정
from mcp.server.mcpserver import MCPServer  # noqa: E402

from anim_gen.service import Service  # noqa: E402

logging.getLogger("httpx").setLevel(logging.WARNING)

service = Service()
mcp = MCPServer(
    "anim-gen-mcp",
    version="0.1.0",
    instructions=(
        "Plan and run AI animation generation for Unreal Engine with cost policy, rule-table routing, fallback and jobs. "
        "YOU interpret natural language; these tools take a structured request (Docs/AIAnimation/DevelopmentGuide.md §9). "
        "Flow: list_motion_providers → plan_motion_generation (never executes) → show the plan to the user → "
        "[paid: estimate_generation_cost → approve_generation only after the user agrees] → generate_motion → get_generation_status. "
        "Every tool returns an envelope {ok, tool, request_id, result, error, diagnostics}. Editor work goes through the "
        f"anim-graph-mcp plugin; state lives in {service.store.root}."
    ),
)


@mcp.tool()
def list_motion_providers(include_inactive: bool = True) -> dict:
    """Motion providers with their capability manifest and current state.

    Args:
        include_inactive: Also list providers that cannot run now (not implemented, not installed, license, missing API key).

    Returns providers[{name, role (provider | pipe), phase, description, capabilities{input_types, supports_new_generation,
    supports_modification, supports_custom_skeleton, output_formats, max_duration_seconds, requires_gpu, requires_network, paid,
    cost_estimable, license, auth_env}, pricing (free | confirmed | unconfirmed), state{implemented, installed, auth{env, present},
    license, available, unavailable_reason{cause, reason}}}]. API key values are never returned — only whether the variable is set.
    """
    return service.list_motion_providers(include_inactive=include_inactive)


@mcp.tool()
def get_generation_policy() -> dict:
    """The effective generation policy (policy.default.json merged with Saved/AnimGen/policy.json) and the cost ledger totals.

    Output paths are NOT in the policy — they come only from the [AnimGraphMcp] ini (anim-graph-mcp get_editor_status.generation).
    """
    return service.get_generation_policy()


@mcp.tool()
def set_generation_policy(patch: dict | None = None, reset: bool = False) -> dict:
    """Change the LOCAL policy override (Saved/AnimGen/policy.json). Ask the user before enabling paid APIs or raising caps.

    Args:
        patch: Deep-merged keys, e.g. {"mode": "FREE_ONLY"} or {"billing": {"paid_api_enabled": true, "max_cost_per_job_usd": 2}}.
            Keys: mode (FREE_ONLY | FREE_FIRST | QUALITY_FIRST), billing{paid_api_enabled, require_explicit_approval (true only),
            max_cost_per_job_usd, max_total_cost_usd}, execution{max_generation_attempts 1-10, allow_fallback,
            preserve_intermediate_results, subprocess_timeout_seconds 10-3600}, paths{blender_executable}. Output paths, overwrite switches and API keys are refused
            (BAD_REQUEST FORBIDDEN_KEY); unknown keys are BAD_REQUEST UNKNOWN_KEY.
        reset: Drop the existing local overrides first.
    """
    return service.set_generation_policy(patch=patch, reset=reset)


@mcp.tool()
def plan_motion_generation(request: dict) -> dict:
    """Build candidate plans for a structured generation request. Executes nothing and calls no paid service.

    Args:
        request: {target_skeleton, target_mesh (required when a candidate retargets), hero, family, animation_name
            (AS_<Hero>_<Family>_<Action>), description (recorded, not interpreted), motion_category (idle | locomotion |
            weapon_action | full_body_new), duration_seconds?, frame_rate?, loop?, root_motion_mode (auto | on | off),
            reference_animations[] (explicit sources) | search{query, path_prefix, min_length, max_length, root_motion, loop, tags,
            limit}, edits{source?, operations[]} (anim-graph-mcp apply_animation_edits op dictionary), retarget{source_mesh?,
            existing_source_rig?, existing_target_rig?, existing_retargeter?, source_pelvis?, source_chains?, ops?,
            source_facing? auto|keep|+X|-X|+Y|-Y (the UE axis the SOURCE faces; auto = measured from its reference pose)}, constraints{},
            generation_policy? (cannot escape a FREE_ONLY policy), provider ("auto" or a name — a name disables fallback),
            integrate_anim_bp, output_path (under GenerationOutputPaths), motion_file? (a .bvh path under ImportSourceRoots, or
            {path, unit auto|cm|m|mm|inch|<cm per unit>, facing auto|keep|+X|-X|+Y|-Y (UE axes; auto = the target skeleton's),
            range{start, end} seconds, axis_forward "-Z", axis_up "Y"} — puts the blender provider first: BVH → FBX in a headless
            Blender subprocess, then import → retarget)}. `save` is a generate_motion argument.

    Read-only editor calls pin the chosen source, source mesh and edit preview into the plan (what you see is what runs). A retarget
    step pins the source and target facing (steps[].inputs.facing); differing facings are risk FACING_DIFFERS with the limitation
    FACING_ALIGNED (the retargeter turns them to match), unmeasurable ones FACING_UNKNOWN (not aligned). A motion_file
    plan pins the BVH header (joints with parents — propose retarget.source_chains from them if the auto IK rig fails), unit, facing
    rotation and frame range. A blender job returns RUNNING; poll get_generation_status until it finishes.
    Returns plan_id, executable, request (normalized), policy{mode, effective_mode, paid_allowed}, candidates[{index, provider, role,
    chain[], steps[{step, provider, tool, inputs, resolved?}], paid, cost_known, estimated_cost_usd, needs_approval, risks[],
    expected_limitations[{code, message, source}]}], excluded[{provider, cause, reason, message}], final_asset. Show it to the user.
    """
    return service.plan_motion_generation(request=request)


@mcp.tool()
def estimate_generation_cost(plan_id: str) -> dict:
    """Cost per candidate of a plan: {provider, paid, cost_known, estimate_usd, basis, verdict free | needs_approval | approved | blocked,
    reason}, the ledger (spent_usd, reserved_usd) and caps (max_cost_per_job_usd, max_total_cost_usd, remaining_usd).
    A paid request whose cost cannot be confirmed is never run.
    """
    return service.estimate_generation_cost(plan_id=plan_id)


@mcp.tool()
def approve_generation(plan_id: str, max_cost_usd: float, max_attempts: int = 1, provider: str | None = None) -> dict:
    """Approve the paid step of ONE plan — only after the user explicitly agreed to the amount.

    Args:
        plan_id: The plan.
        max_cost_usd: Spending cap for this approval (all its attempts). Must cover the estimate and stay within the policy caps.
        max_attempts: Paid submissions allowed (retries included). Going beyond needs a new approval.
        provider: The paid provider (needed only when the plan has several).

    Refusals: PLAN_NOT_FOUND · BAD_REQUEST (NO_PAID_STEP · POLICY_FREE_ONLY · PAID_API_DISABLED · AMBIGUOUS_PROVIDER) · COST_UNKNOWN ·
    BUDGET_EXCEEDED (ESTIMATE_OVER_APPROVAL · MAX_COST_PER_JOB · MAX_TOTAL). A job of this plan waiting for approval becomes QUEUED
    (resumed_job_id) — approval never starts execution; call generate_motion.
    """
    return service.approve_generation(plan_id=plan_id, max_cost_usd=max_cost_usd, max_attempts=max_attempts, provider=provider)


@mcp.tool()
def generate_motion(plan_id: str, save: bool = False, retry: bool = False) -> dict:
    """Run a plan as a job: candidates in order, fallback on provider failures, guard errors stop the job.

    Args:
        plan_id: From plan_motion_generation.
        save: Save the generated (and intermediate) assets. Default false — they stay dirty in the editor.
        retry: After a FAILED/CANCELLED job of this plan, start a new job. Otherwise the same plan returns the same job.

    ok=true only when the job SUCCEEDED (or RUNNING for an asynchronous provider — poll get_generation_status). Waiting for approval →
    APPROVAL_REQUIRED (error.details.job); failure → the last cause (error.details.job.fallback_history). The job holds job_id, status,
    provider, chain, generated_assets[], reused_assets[], intermediate_assets[] (<output_path>/Work/<job_id>/), validation,
    limitations[] (what is missing versus the request — always present for a fallback result), fallback_history[], cost, events[],
    diagnostics[] (including the editor tools' own warnings, each with tool and step — e.g. LENGTH_SNAPPED from the import step).
    """
    return service.generate_motion(plan_id=plan_id, save=save, retry=retry)


@mcp.tool()
def get_generation_status(job_id: str | None = None, plan_id: str | None = None, limit: int = 20) -> dict:
    """One job (job_id — an asynchronous step is polled here) or the most recent jobs (optionally of one plan)."""
    return service.get_generation_status(job_id=job_id, plan_id=plan_id, limit=limit)


@mcp.tool()
def cancel_generation(job_id: str) -> dict:
    """Cancel a job. QUEUED / WAITING_FOR_APPROVAL → CANCELLED. RUNNING → CANCELLED; a provider step in flight is not stopped but its
    result is ignored and any cost stays in the ledger. Already finished → BAD_REQUEST ALREADY_TERMINAL. Assets made so far are kept.
    """
    return service.cancel_generation(job_id=job_id)


if __name__ == "__main__":
    mcp.run()
