"""규칙 표 라우터 · 요청 검증 · 계획은 실행하지 않는다 (지침서 §5 · §9)."""
from __future__ import annotations

import pytest

import conftest
from conftest import AIM_IDLE, KATANA, OUT, SB, SB_ANIM, SB_CHAINS, UE4_MESH, VESPER, VESPER_MESH, mock_ai, mock_paid, request


def plan(service, **overrides) -> dict:
    env = service.plan_motion_generation(request=request(**overrides))
    assert env["ok"], env["error"]
    return env["result"]


def excluded(p: dict) -> dict:
    return {e["provider"]: (e["cause"], e["reason"]) for e in p["excluded"]}


def test_idle_free_first_pins_source_and_previews_edits(service, fake):
    p = plan(service)
    assert p["executable"] and p["order"] == ["existing_motion", "local_ai", "external.meshy"]
    [cand] = p["candidates"]
    assert cand["provider"] == "existing_motion" and cand["chain"] == ["existing_motion", "direct_key"] and not cand["paid"]
    resolve, edit, validate = cand["steps"]
    assert resolve["resolved"]["source"] == AIM_IDLE and resolve["resolved"]["skeleton"] == VESPER
    assert edit["step"] == "edit" and edit["preview"]["length"] == pytest.approx(1.3333)
    assert validate["step"] == "validate"
    assert "SEARCH_PICKED_TOP" in cand["risks"]
    assert excluded(p) == {"local_ai": ("PROVIDER_UNAVAILABLE", "NOT_INSTALLED"),  # Phase 5 — conftest 가 Kimodo 경로를 없는 곳으로
                           "external.meshy": ("APPROVAL_REQUIRED", "PAID_API_DISABLED")}
    assert fake.count("preview_animation_edits") == 1
    assert not fake.writes  # 계획은 아무것도 만들지 않는다


def test_free_only_excludes_paid_as_policy(service):
    service.set_generation_policy(patch={"mode": "FREE_ONLY", "billing": {"paid_api_enabled": True}})
    p = plan(service)
    assert excluded(p)["external.meshy"] == ("APPROVAL_REQUIRED", "POLICY_FREE_ONLY")
    assert p["policy"]["effective_mode"] == "FREE_ONLY" and not p["policy"]["paid_allowed"]


def test_mode_orders(service):
    assert plan(service, generation_policy="QUALITY_FIRST")["order"] == ["existing_motion", "external.meshy", "local_ai"]
    p = plan(service, motion_category="full_body_new")
    assert p["order"] == ["local_ai", "external.meshy", "existing_motion"]
    [cand] = p["candidates"]
    assert cand["role"] == "approximate"
    assert {"NOT_NEW_MOTION", "SEGMENTED_PLAN_SUGGESTED"} <= {lim["code"] for lim in cand["expected_limitations"]}
    assert plan(service, motion_category="full_body_new", generation_policy="QUALITY_FIRST")["order"][0] == "external.meshy"


def test_request_mode_clamped_under_free_only(service):
    service.set_generation_policy(patch={"mode": "FREE_ONLY"})
    env = service.plan_motion_generation(request=request(generation_policy="QUALITY_FIRST"))
    assert env["ok"] and "POLICY_CLAMPED" in [d["code"] for d in env["diagnostics"]]
    assert env["result"]["order"] == ["existing_motion", "local_ai", "external.meshy"]


def test_weapon_action_limitations(service):
    # Phase 7 — integrate_anim_bp 는 이제 anim_bp 를 요구하고 실제로 연결한다(ANIM_BP_NOT_INTEGRATED 폐지 → test_integrate.py)
    p = plan(service, motion_category="weapon_action", constraints={"two_hand_weapon_grip": True, "foot_contact": True, "spin_three_times": True})
    codes = [(lim["code"], lim.get("constraint")) for lim in p["candidates"][0]["expected_limitations"]]
    assert ("GRIP_NOT_VALIDATED", None) in codes and ("FOOT_CONTACT_NOT_ENFORCED", "foot_contact") in codes
    assert ("CONSTRAINT_UNSUPPORTED", "spin_three_times") in codes and not [c for c, _ in codes if c.startswith("ANIM_BP")]
    assert [c for c, _ in codes].count("GRIP_NOT_VALIDATED") == 1  # 요청 유형 + 파지 제약이 같은 한계를 한 번만 낸다


def test_other_skeleton_source_adds_retarget_with_pinned_mesh(service, fake):
    p = plan(service, reference_animations=[KATANA], search=None, edits=..., target_mesh=VESPER_MESH)
    [cand] = p["candidates"]
    assert cand["chain"] == ["existing_motion", "retarget"]
    retarget = cand["steps"][1]
    assert retarget["inputs"]["source_mesh"] == UE4_MESH and retarget["inputs"]["source_mesh_source"] == "skeleton_preview"
    assert retarget["inputs"]["ops"] == "match_existing" and not retarget["conditional"]
    assert "SOURCE_MESH_IMPLICIT" in cand["risks"]
    # 소스(메시 + 정면, details 한 번) · 대상(정면) — UE4 마네킹과 Vesper 는 둘 다 +Y 라 맞출 것이 없다
    assert fake.count("inspect_skeleton") == 2 and not fake.writes
    facing = retarget["inputs"]["facing"]
    assert (facing["source"], facing["target"], facing["yaw_deg"]) == ("+Y", "+Y", 0.0)
    assert not [r for r in cand["risks"] if r.startswith("FACING")]


def test_differently_facing_source_is_a_risk_and_is_aligned(service, fake):
    """SB(+X) → Vesper(+Y): 계획에 위험 FACING_DIFFERS + 한계 FACING_ALIGNED, 실행은 create_ik_retargeter(facing_yaw_deg=+90)."""
    p = plan(service, reference_animations=[SB_ANIM], search=None, edits=..., target_mesh=VESPER_MESH,
             retarget={"source_chains": SB_CHAINS, "source_pelvis": "Bip001-Pelvis"})
    [cand] = p["candidates"]
    facing = cand["steps"][1]["inputs"]["facing"]
    assert (facing["source"], facing["target"], facing["yaw_deg"]) == ("+X", "+Y", 90.0)
    assert facing["source_detail"]["feet"]["outliers"] == 1 and facing["source_detail"]["lateral"]["axis"] == "+X"
    assert "FACING_DIFFERS" in cand["risks"]
    [lim] = [lim for lim in cand["expected_limitations"] if lim["code"].startswith("FACING")]
    assert lim["code"] == "FACING_ALIGNED" and lim["yaw_deg"] == 90.0 and lim["source"] == "retarget"
    env = service.generate_motion(plan_id=p["plan_id"])
    assert env["ok"], env["error"]
    [(_, rtg)] = [(t, q) for t, q in fake.writes if t == "create_ik_retargeter"]
    assert rtg["facing_yaw_deg"] == 90.0
    assert "FACING_ALIGNED" in {lim["code"] for lim in env["result"]["limitations"]}


def test_source_facing_keep_and_explicit(service, fake):
    p = plan(service, reference_animations=[SB_ANIM], search=None, edits=..., target_mesh=VESPER_MESH, retarget={"source_facing": "keep"})
    [cand] = p["candidates"]
    assert cand["steps"][1]["inputs"]["facing"]["yaw_deg"] == 0.0 and not [r for r in cand["risks"] if r.startswith("FACING")]
    assert fake.count("inspect_skeleton") == 1  # 소스 메시만 — 정면은 재지 않는다
    p = plan(service, reference_animations=[KATANA], search=None, edits=..., target_mesh=VESPER_MESH, retarget={"source_facing": "-X"})
    facing = p["candidates"][0]["steps"][1]["inputs"]["facing"]
    assert (facing["source"], facing["target"], facing["yaw_deg"]) == ("-X", "+Y", -90.0)
    env = service.plan_motion_generation(request=request(reference_animations=[KATANA], search=None, edits=..., retarget={"source_facing": "north"}))
    assert not env["ok"] and env["error"]["details"]["field"] == "retarget.source_facing"


def test_unmeasurable_or_ambiguous_facing_is_not_aligned(service, fake):
    fake.bones[SB] = [b for b in fake.bones[SB] if "Foot" not in b["name"] and "Toe" not in b["name"]]  # 발이 없다
    p = plan(service, reference_animations=[SB_ANIM], search=None, edits=..., target_mesh=VESPER_MESH)
    [cand] = p["candidates"]
    assert cand["steps"][1]["inputs"]["facing"]["source"] is None and "FACING_UNKNOWN" in cand["risks"]
    assert "FACING_UNKNOWN" in {lim["code"] for lim in cand["expected_limitations"]}
    # 발은 +X 인데 좌우 체인을 거꾸로 주면(왼쪽 = +Y → 정면 −X) 둘이 어긋나 모른다고 본다
    fake.bones[SB] = conftest.SB_BONES
    swapped = [{**c, "name": "Right" + c["name"][4:]} if c["name"].startswith("Left") else {**c, "name": "Left" + c["name"][5:]} for c in SB_CHAINS]
    facing = plan(service, reference_animations=[SB_ANIM], search=None, edits=..., target_mesh=VESPER_MESH,
                  retarget={"source_chains": swapped})["candidates"][0]["steps"][1]["inputs"]["facing"]
    assert facing["source"] is None and facing["source_detail"]["reason"] == "FEET_LATERAL_DISAGREE" and facing["yaw_deg"] == 0.0


def test_generated_motion_measures_facing_after_import(make_service, fake):
    """생성 FBX 는 임포트 전에는 스켈레톤이 없다 — 계획은 FACING_UNRESOLVED_AT_PLAN, 실행이 임포트된 스켈레톤으로 잰다."""
    service, _ = make_service(local_ai=mock_ai())
    p = plan(service, motion_category="full_body_new", target_mesh=VESPER_MESH, edits=...)
    cand = p["candidates"][0]
    assert cand["provider"] == "local_ai" and "FACING_UNRESOLVED_AT_PLAN" in cand["risks"]
    env = service.generate_motion(plan_id=p["plan_id"])
    assert env["ok"], env["error"]
    # Mock 임포트 스켈레톤은 본 정보가 없다 → 실행 한계 FACING_UNKNOWN, 맞추지 않는다
    assert "FACING_UNKNOWN" in {lim["code"] for lim in env["result"]["limitations"]}
    [(_, rtg)] = [(t, q) for t, q in fake.writes if t == "create_ik_retargeter"]
    assert "facing_yaw_deg" not in rtg


def test_align_mode_defaults_per_bone_with_match_existing(service, fake):
    """retarget.align_mode — match_existing 의 기본 per_bone(뼈 수 같은 체인 FK 1:1 + 본 대 본 정렬), default ops 는 engine 만."""
    p = plan(service, reference_animations=[KATANA], search=None, edits=..., target_mesh=VESPER_MESH, retarget={"align_mode": "engine"})
    assert p["candidates"][0]["steps"][1]["inputs"]["align_mode"] == "engine"
    p = plan(service, reference_animations=[KATANA], search=None, edits=..., target_mesh=VESPER_MESH, retarget={"ops": "default"})
    assert p["candidates"][0]["steps"][1]["inputs"]["align_mode"] == "engine"
    for bad, reason in (({"align_mode": "chain"}, None), ({"ops": "default", "align_mode": "per_bone"}, "ALIGN_MODE_WITHOUT_ALIGN")):
        env = service.plan_motion_generation(request=request(reference_animations=[KATANA], search=None, edits=..., target_mesh=VESPER_MESH, retarget=bad))
        assert not env["ok"] and env["error"]["details"]["field"] == "retarget.align_mode"
        if reason:
            assert env["error"]["details"]["reason"] == reason
    p = plan(service, reference_animations=[KATANA], search=None, edits=..., target_mesh=VESPER_MESH)
    assert p["candidates"][0]["steps"][1]["inputs"]["align_mode"] == "per_bone"
    env = service.generate_motion(plan_id=p["plan_id"])
    assert env["ok"], env["error"]
    [(_, rtg)] = [(t, q) for t, q in fake.writes if t == "create_ik_retargeter"]
    assert (rtg["ops"], rtg["align_mode"]) == ("match_existing", "per_bone")


def test_body_clearance_defaults_resolve(service, fake):
    """retarget.body_clearance — 기본 resolve 가 retarget_animations 로 가고 보정 결과가 진단 BODY_CLEARANCE_RESOLVED 로 남는다. off 면 인자 없음."""
    p = plan(service, reference_animations=[KATANA], search=None, edits=..., target_mesh=VESPER_MESH)
    assert p["candidates"][0]["steps"][1]["inputs"]["body_clearance"] == "resolve"
    env = service.generate_motion(plan_id=p["plan_id"])
    assert env["ok"], env["error"]
    [(_, rt)] = [(t, q) for t, q in fake.writes if t == "retarget_animations"]
    assert rt["body_clearance"] == "resolve"
    resolved = [d for d in env["result"]["diagnostics"] if d["code"] == "BODY_CLEARANCE_RESOLVED"]
    assert resolved and "upperarm_l 40% frames ≤ 9.5° (penetration frames 30.0% → 0.0%)" in resolved[0]["message"]

    fake.calls.clear()
    p = plan(service, reference_animations=[KATANA], search=None, edits=..., target_mesh=VESPER_MESH, retarget={"body_clearance": "off"},
             animation_name="AS_Vesper_Katana_ClearanceOff")
    assert service.generate_motion(plan_id=p["plan_id"])["ok"]
    [(_, rt)] = [(t, q) for t, q in fake.writes if t == "retarget_animations"]
    assert "body_clearance" not in rt
    env = service.plan_motion_generation(request=request(reference_animations=[KATANA], search=None, edits=..., target_mesh=VESPER_MESH,
                                                         retarget={"body_clearance": "fix"}))
    assert not env["ok"] and env["error"]["details"]["field"] == "retarget.body_clearance"


def test_retarget_without_target_mesh_is_excluded(service):
    p = plan(service, reference_animations=[KATANA], search=None, edits=...)
    assert not p["executable"]
    assert excluded(p)["existing_motion"] == ("UNSUPPORTED_REQUEST", "MISSING_INPUT")
    env = service.generate_motion(plan_id=p["plan_id"])
    assert not env["ok"] and env["error"]["code"] == "UNSUPPORTED_REQUEST"


def test_same_skeleton_without_edits_is_reuse(service):
    [cand] = plan(service, edits=..., duration_seconds=3.0, frame_rate=60)["candidates"]
    assert cand["chain"] == ["existing_motion"] and cand["steps"][-1]["tool"] == "validate_animation"
    codes = {lim["code"] for lim in cand["expected_limitations"]}
    assert {"REUSED_EXISTING", "DURATION_MISMATCH", "FRAME_RATE_MISMATCH"} <= codes


def test_bad_operations_exclude_the_candidate(service):
    p = plan(service, edits={"operations": [{"op": "explode"}]})
    assert excluded(p)["existing_motion"] == ("UNSUPPORTED_REQUEST", "BAD_OPERATIONS")


def test_output_path_and_existing_asset_are_checked_at_plan(service, fake):
    env = service.plan_motion_generation(request=request(output_path="/Game/Animation/Hero/Vesper/Gen"))
    assert not env["ok"] and env["error"]["code"] == "OUTPUT_PATH_NOT_ALLOWED"
    assert env["error"]["details"]["allowed"] == fake.output_paths
    fake.assets[f"{OUT}/AS_Vesper_Rifle_AimIdle_TwistP3"] = {"class": "AnimSequence", "skeleton": VESPER, "length": 1, "frame_rate": 30, "loop": False}
    env = service.plan_motion_generation(request=request())
    assert not env["ok"] and env["error"]["code"] == "ASSET_EXISTS"


def test_editor_down_gives_unresolved_plan(service, fake):
    fake.up = False
    env = service.plan_motion_generation(request=request(target_mesh=VESPER_MESH))
    assert env["ok"]
    codes = [d["code"] for d in env["diagnostics"]]
    assert "EDITOR_UNAVAILABLE" in codes and "OUTPUT_PATH_UNCHECKED" in codes
    [cand] = env["result"]["candidates"]
    assert cand["steps"][0]["resolved"] is None and cand["steps"][1]["step"] == "retarget" and cand["steps"][1]["conditional"]
    assert {"UNRESOLVED_AT_PLAN", "EDITS_NOT_PREVIEWED"} <= set(cand["risks"])


def test_explicit_provider_disables_fallback(service):
    p = plan(service, provider="existing_motion")
    assert p["order"] == ["existing_motion"] and p["fallback"] is False
    env = service.plan_motion_generation(request=request(provider="retarget"))
    assert env["error"]["details"]["reason"] == "PIPE_NOT_PROVIDER"
    env = service.plan_motion_generation(request=request(provider="nope"))
    assert env["error"]["details"]["reason"] == "UNKNOWN_PROVIDER"
    p = plan(service, provider="direct_key", reference_animations=[AIM_IDLE], search=None)
    assert p["candidates"][0]["chain"] == ["existing_motion", "direct_key"]


def test_mock_ai_candidate_chain(make_service):
    service, _ = make_service(local_ai=mock_ai())
    p = plan(service, motion_category="full_body_new", target_mesh=VESPER_MESH)
    assert [c["provider"] for c in p["candidates"]] == ["local_ai", "existing_motion"]
    assert p["candidates"][0]["chain"] == ["local_ai", "retarget", "direct_key"]
    assert [s["step"] for s in p["candidates"][0]["steps"]] == ["generate", "import", "retarget", "edit", "validate"]


def test_paid_candidate_needs_approval_and_unknown_cost_is_excluded(make_service):
    service, _ = make_service(**{"external.meshy": mock_paid()})
    service.set_generation_policy(patch={"billing": {"paid_api_enabled": True, "max_cost_per_job_usd": 2, "max_total_cost_usd": 5}})
    p = plan(service, motion_category="full_body_new", target_mesh=VESPER_MESH)
    paid = [c for c in p["candidates"] if c["paid"]]
    assert paid and paid[0]["needs_approval"] and paid[0]["estimated_cost_usd"] == 0.5 and paid[0]["cost_known"]
    service2, _ = make_service(**{"external.meshy": mock_paid(cost_known=False)})
    p = plan(service2, motion_category="full_body_new", target_mesh=VESPER_MESH)
    assert excluded(p)["external.meshy"][0] == "COST_UNKNOWN"


@pytest.mark.parametrize("bad, reason", [
    ({"save": True}, "UNKNOWN_FIELD"),
    ({"colour": "red"}, "UNKNOWN_FIELD"),
    ({"motion_category": "combat"}, "BAD_FIELD"),
    ({"animation_name": "AS Vesper"}, "BAD_FIELD"),
    ({"edits": {"operations": []}}, "BAD_FIELD"),
    ({"edits": {"source": KATANA, "operations": [{"op": "trim"}]}, "reference_animations": [AIM_IDLE]}, "CONFLICTING_SOURCE"),
    ({"retarget": {"reuse": True}}, "UNKNOWN_FIELD"),
    ({"target_skeleton": None}, "MISSING_FIELD"),
])
def test_request_validation(service, fake, bad, reason):
    env = service.plan_motion_generation(request=request(**bad))
    assert not env["ok"] and env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["reason"] == reason
    assert not fake.calls  # 요청 검증은 에디터를 부르기 전


def test_name_rule_warning(service):
    env = service.plan_motion_generation(request=request(animation_name="TwistIdle"))
    assert env["ok"] and "NAME_RULE" in [d["code"] for d in env["diagnostics"]]


def test_list_motion_providers_reports_state_without_key_values(service, monkeypatch):
    monkeypatch.setenv("MESHY_API_KEY", "sk-SENTINEL-LIST")
    env = service.list_motion_providers()
    assert env["ok"] and "sk-SENTINEL-LIST" not in str(env)
    providers = {p["name"]: p for p in env["result"]["providers"]}
    assert set(providers) == {"retarget", "existing_motion", "direct_key", "blender", "local_ai", "external.meshy", "package", "anim_bp", "review",
                              "control_rig"}
    assert providers["package"]["role"] == providers["anim_bp"]["role"] == "pipe"  # Phase 7 — 포장 · AnimBP 연결 파이프
    assert providers["review"]["role"] == "pipe" and providers["review"]["state"]["available"]  # Phase 8-2 — 대상 메시 캡처 파이프
    assert providers["external.meshy"]["state"]["auth"] == {"env": "MESHY_API_KEY", "present": True}
    # Phase 6: 구현 · 키 있음 → 사용 가능(유료 차단은 정책 · 승인 게이트의 몫). 크레딧은 공식 가격, 돈 값은 정책이 비어 미확인
    assert providers["external.meshy"]["pricing"] == "unconfirmed"
    meshy = providers["external.meshy"]
    assert meshy["state"]["implemented"] and meshy["state"]["available"] and meshy["capabilities"]["license"] == "ok"
    assert meshy["capabilities"]["pricing"]["credits"] == {"prime": 10, "swift": 3} and meshy["capabilities"]["max_duration_seconds"] == 10
    assert providers["retarget"]["role"] == "pipe" and providers["existing_motion"]["state"]["available"]
    assert providers["control_rig"]["state"]["unavailable_reason"]["reason"] == "NOT_IMPLEMENTED"
    # Phase 4 · 5: 구현됐지만 정책의 실행 파일이 없다(conftest 가 없는 경로를 준다)
    for name in ("blender", "local_ai"):
        assert providers[name]["state"]["implemented"] and providers[name]["state"]["unavailable_reason"]["reason"] == "NOT_INSTALLED"
    assert providers["local_ai"]["capabilities"]["license"] == "ok" and providers["local_ai"]["capabilities"]["max_duration_seconds"] == 10
    assert {p["name"] for p in service.list_motion_providers(include_inactive=False)["result"]["providers"]} == {
        "retarget", "existing_motion", "direct_key", "external.meshy", "package", "anim_bp", "review"}
    monkeypatch.delenv("MESHY_API_KEY")
    meshy = {p["name"]: p for p in service.list_motion_providers()["result"]["providers"]}["external.meshy"]
    assert meshy["state"]["unavailable_reason"] == {"cause": "AUTHENTICATION_FAILED", "reason": "API_KEY_MISSING"}
