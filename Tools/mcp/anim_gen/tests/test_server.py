"""MCP 서버 — Tool 9개 등록 · 봉투 모양 · 서버 함수가 service 를 그대로 부른다."""
from __future__ import annotations

import asyncio
import importlib

import pytest

from conftest import request

TOOLS = {"list_motion_providers", "get_generation_policy", "set_generation_policy", "plan_motion_generation", "estimate_generation_cost",
         "approve_generation", "generate_motion", "get_generation_status", "cancel_generation"}
ENVELOPE = {"ok", "tool", "request_id", "result", "error", "diagnostics"}


@pytest.fixture
def server(monkeypatch, state_dir, service):
    monkeypatch.setenv("ANIM_GEN_STATE_DIR", str(state_dir))
    module = importlib.import_module("anim_gen.server")
    monkeypatch.setattr(module, "service", service)
    return module


def test_nine_tools_registered(server):
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} == TOOLS
    assert all(t.description for t in tools)


def test_tools_return_envelopes(server):
    plan = server.plan_motion_generation(request=request())
    assert set(plan) == ENVELOPE and plan["ok"] and plan["tool"] == "plan_motion_generation"
    plan_id = plan["result"]["plan_id"]
    for name, kwargs in (("list_motion_providers", {}), ("get_generation_policy", {}), ("estimate_generation_cost", {"plan_id": plan_id}),
                         ("generate_motion", {"plan_id": plan_id}), ("get_generation_status", {}),
                         ("set_generation_policy", {"patch": {"mode": "FREE_ONLY"}})):
        env = getattr(server, name)(**kwargs)
        assert set(env) == ENVELOPE and env["tool"] == name and env["ok"], (name, env["error"])
    job_id = server.get_generation_status()["result"]["jobs"][0]["job_id"]
    env = server.cancel_generation(job_id=job_id)
    assert set(env) == ENVELOPE and not env["ok"] and env["error"]["code"] == "BAD_REQUEST"
    env = server.approve_generation(plan_id=plan_id, max_cost_usd=1.0)
    assert set(env) == ENVELOPE and not env["ok"] and env["result"] is None


def test_unexpected_exception_is_an_internal_envelope(service, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(service.store, "load_plan", boom)
    env = service.estimate_generation_cost(plan_id="x")
    assert set(env) == ENVELOPE and env["error"]["code"] == "INTERNAL" and "disk on fire" in env["error"]["message"]
