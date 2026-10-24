"""정책 — 기본 + 로컬 병합 · 금지 키 · 요청 단위 모드 (지침서 §6)."""
from __future__ import annotations

import json

import pytest

from anim_gen import policy as policy_mod
from anim_gen.envelope import AnimGenError


def test_default_policy_is_free_first_without_paid(state_dir):
    p = policy_mod.effective(state_dir)
    assert p["mode"] == "FREE_FIRST"
    assert p["billing"]["paid_api_enabled"] is False
    assert p["billing"]["require_explicit_approval"] is True
    assert "output_path" not in json.dumps(p)


def test_local_override_is_deep_merged_and_reset(state_dir):
    p = policy_mod.set_local(state_dir, {"billing": {"max_total_cost_usd": 3}})
    assert p["billing"]["max_total_cost_usd"] == 3
    assert p["billing"]["require_explicit_approval"] is True  # 같은 묶음의 다른 키는 기본값 유지
    p = policy_mod.set_local(state_dir, {"mode": "FREE_ONLY"})
    assert p["mode"] == "FREE_ONLY" and p["billing"]["max_total_cost_usd"] == 3
    assert json.loads(policy_mod.local_path(state_dir).read_text(encoding="utf-8")) == {"billing": {"max_total_cost_usd": 3}, "mode": "FREE_ONLY"}
    p = policy_mod.set_local(state_dir, {}, reset=True)
    assert p == policy_mod.load_default()


@pytest.mark.parametrize("patch, reason", [
    ({"output_paths": ["/Game/X/"]}, "FORBIDDEN_KEY"),
    ({"paths": {"output_root": "/Game/X"}}, "FORBIDDEN_KEY"),
    ({"allow_asset_overwrite": True}, "FORBIDDEN_KEY"),
    ({"billing": {"meshy_api_key": "sk-123"}}, "FORBIDDEN_KEY"),
    ({"candidate_root": "/Game/X"}, "FORBIDDEN_KEY"),
    ({"billing": {"require_explicit_approval": False}}, "FORBIDDEN_VALUE"),
    ({"mode": "CHEAPEST"}, "BAD_VALUE"),
    ({"execution": {"max_generation_attempts": 0}}, "BAD_VALUE"),
    ({"billing": {"max_cost_per_job_usd": -1}}, "BAD_VALUE"),
    ({"billing": {"paid_api_enabled": "yes"}}, "BAD_VALUE"),
    ({"execution": {"retries": 2}}, "UNKNOWN_KEY"),
    ({"modes": "FREE_ONLY"}, "UNKNOWN_KEY"),
])
def test_bad_patches_are_refused_and_nothing_is_written(state_dir, patch, reason):
    with pytest.raises(AnimGenError) as exc:
        policy_mod.set_local(state_dir, patch)
    assert exc.value.code == "BAD_REQUEST" and exc.value.reason == reason
    assert not policy_mod.local_path(state_dir).exists()


def test_request_mode_cannot_escape_free_only():
    base = policy_mod.load_default()
    free_only = policy_mod.deep_merge(base, {"mode": "FREE_ONLY"})
    mode, diags = policy_mod.resolve_mode(free_only, "QUALITY_FIRST")
    assert mode == "FREE_ONLY" and diags[0]["code"] == "POLICY_CLAMPED"
    assert policy_mod.resolve_mode(base, "QUALITY_FIRST") == ("QUALITY_FIRST", [])
    assert policy_mod.resolve_mode(base, "FREE_ONLY") == ("FREE_ONLY", [])
    with pytest.raises(AnimGenError):
        policy_mod.resolve_mode(base, "CHEAP")


def test_paid_block_reason():
    base = policy_mod.load_default()
    assert policy_mod.paid_block_reason(base, "FREE_ONLY") == "POLICY_FREE_ONLY"
    assert policy_mod.paid_block_reason(base, "FREE_FIRST") == "PAID_API_DISABLED"
    enabled = policy_mod.deep_merge(base, {"billing": {"paid_api_enabled": True}})
    assert policy_mod.paid_block_reason(enabled, "QUALITY_FIRST") is None


def test_policy_tools_envelopes(service):
    env = service.get_generation_policy()
    assert env["ok"] and set(env) == {"ok", "tool", "request_id", "result", "error", "diagnostics"}
    assert env["result"]["sources"]["local_exists"] is False
    env = service.set_generation_policy(patch={"billing": {"paid_api_enabled": True}})
    assert env["ok"] and [d["code"] for d in env["diagnostics"]] == ["PAID_API_ENABLED"]
    assert service.get_generation_policy()["result"]["sources"]["local_exists"] is True
    env = service.set_generation_policy(patch={"output_path": "/Game/X"})
    assert not env["ok"] and env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["reason"] == "FORBIDDEN_KEY"
