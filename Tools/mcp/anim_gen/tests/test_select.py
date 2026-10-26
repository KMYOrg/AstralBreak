"""Phase 8-1 — 플래그 → 2차 생성 계획 · seed 후보 · select 단계(후보 리타깃 · 측정 · 점수) · 관통 기본값(지침서 §14 Phase 8).

Kimodo · Blender 는 test_local_ai 의 가짜 실행기(후보 report · items 변환)로, 측정은 FakeEditor 의 profile 흉내(애셋 이름 → 손목 간격 · 발 비 ·
휘두름 · 관통 · 상태)로 대신한다 — 모델 · 에디터를 띄우지 않는다.
"""
from __future__ import annotations

import pytest

from anim_gen import selection
from conftest import KATANA, OUT, UE4_MESH, request
from test_blender import FakeProc
from test_local_ai import KimodoProc, ai_request, ka, plan, status  # noqa: F401 — ka 는 픽스처

GRIP = {"two_hand_weapon_grip": True, "foot_contact": True}
FINAL = f"{OUT}/AS_Vesper_Kimodo_WalkTurn"


def sword(ka, **overrides) -> dict:
    base = {"motion_category": "weapon_action", "constraints": GRIP, "generation": {"seed": 7, "candidates": 3}}
    base.update(overrides)
    return plan(ka, **base)


def steps_of(p: dict) -> dict:
    return {s["step"]: s for s in p["candidates"][0]["steps"]}


def lims_of(cand: dict) -> set[str]:
    return {lim["code"] for lim in cand["expected_limitations"]}


def run(ka, p: dict) -> dict:
    env = ka.service.generate_motion(plan_id=p["plan_id"], save=True)
    job = env["result"]
    ka.launcher.of(KimodoProc)[-1].complete("ok")
    job = status(ka, job["job_id"])
    if job["status"] == "RUNNING" and job["stage"] == "convert":
        ka.launcher.of(FakeProc)[-1].complete("ok")
        job = status(ka, job["job_id"])
    return job


# ---- 요청 ----
@pytest.mark.parametrize("generation, field, reason", [
    ({"candidates": 0}, "generation.candidates", "BAD_FIELD"),
    ({"candidates": 7}, "generation.candidates", "BAD_FIELD"),
    ({"candidates": 2, "samples": 2}, "generation.candidates", "CONFLICTING_FIELDS"),
    ({"refine": {"mode": "always"}}, "generation.refine.mode", "BAD_FIELD"),
    ({"refine": {"passes": 2}}, "generation.refine.passes", "UNKNOWN_FIELD"),
    ({"refine": {"keyframe_step": 11}}, "generation.refine.keyframe_step", "BAD_FIELD"),
    ({"refine": {"grip": {"target": "glue"}}}, "generation.refine.grip.target", "BAD_FIELD"),
    ({"refine": {"grip": {"lead_hand": "both"}}}, "generation.refine.grip.lead_hand", "BAD_FIELD"),
    ({"refine": {"grip": {"spacing_cm": 0}}}, "generation.refine.grip.spacing_cm", "BAD_FIELD"),
    ({"refine": {"grip": {"target_spacing_cm": 0}}}, "generation.refine.grip.target_spacing_cm", "BAD_FIELD"),
    ({"refine": {"grip": {"spacing_cm": 60, "target_spacing_cm": 60}}}, "generation.refine.grip.target_spacing_cm", "CONFLICTING_FIELDS"),
    ({"refine": {"grip": {"from_s": 2.0, "to_s": 1.0}}}, "generation.refine.grip.from_s", "BAD_FIELD"),
    ({"refine": {"grip": {"hand": "right"}}}, "generation.refine.grip.hand", "UNKNOWN_FIELD"),
    ({"select": {"weights": {"speed": 1}}}, "generation.select.weights", "BAD_FIELD"),
    ({"select": {"weights": {"grip": -1}}}, "generation.select.weights", "BAD_FIELD"),
    ({"select": {"pick": 0}}, "generation.select", "BAD_FIELD"),
])
def test_request_fields(ka, generation, field, reason):
    env = ka.service.plan_motion_generation(request=ai_request(generation=generation))
    assert env["error"]["code"] == "BAD_REQUEST" and env["error"]["details"]["field"] == field and env["error"]["details"]["reason"] == reason


def test_defaults_are_filled_and_body_clearance_is_left_to_the_plan(ka):
    req = plan(ka)["request"]
    assert req["generation"]["candidates"] == 1 and req["generation"]["refine"]["grip"]["target"] == "meet" and req["generation"]["select"] == {"weights": None}
    assert req["retarget"]["body_clearance"] is None


# ---- 관통 기본값 (모든 Provider) ----
def test_grip_flag_measures_clearance_on_every_provider(service, fake):
    def rt(**kw):
        kw.setdefault("retarget", {"source_mesh": UE4_MESH})
        env = service.plan_motion_generation(request=request(reference_animations=[KATANA], target_mesh=fake.meshes["/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"],
                                                             motion_category="weapon_action", edits=..., search=..., **kw))
        assert env["ok"], env["error"]
        cand = env["result"]["candidates"][0]
        return next(s for s in cand["steps"] if s["step"] == "retarget")["inputs"], cand
    inputs, cand = rt(constraints={"two_hand_weapon_grip": True})
    assert (inputs["body_clearance"], inputs["body_clearance_from"]) == ("measure", "grip_flag")
    assert {"BODY_CLEARANCE_MEASURED_FOR_GRIP", "GRIP_NOT_VALIDATED"} <= lims_of(cand)   # existing_motion 은 파지를 바꾸지 않는다 — 한계 그대로
    inputs, cand = rt()
    assert (inputs["body_clearance"], inputs["body_clearance_from"]) == ("resolve", "default") and "BODY_CLEARANCE_MEASURED_FOR_GRIP" not in lims_of(cand)
    inputs, cand = rt(constraints={"two_hand_weapon_grip": True}, retarget={"source_mesh": UE4_MESH, "body_clearance": "resolve"})
    assert (inputs["body_clearance"], inputs["body_clearance_from"]) == ("resolve", "request") and "CLEARANCE_MAY_BREAK_GRIP" in cand["risks"]


# ---- local_ai 계획 ----
def test_flags_become_second_pass_rules_with_seed_candidates_and_a_select_step(ka):
    p = sword(ka, generation={"seed": 7, "candidates": 4})
    cand = p["candidates"][0]
    assert [s["step"] for s in cand["steps"]] == ["generate", "convert", "import", "select", "retarget", "validate"]
    assert cand["chain"] == ["local_ai", "blender", "retarget"]
    s = steps_of(p)
    g = s["generate"]["inputs"]
    assert g["seeds"] == [7, 8, 9, 10] and g["candidates"] == 4 and g["refine"]["passes"] == 2 and g["diffusions"] == 8
    assert g["timeout_s"] == 300 + 25 * 7 and g["timeout_extra_s"] == 175 and g["metric_window"] == [0.0, 6.0]
    rules = {r["flag"]: r for r in g["refine"]["rules"]}
    assert rules["two_hand_weapon_grip"]["target"] == "meet" and rules["two_hand_weapon_grip"]["frames"] == {"from": 0, "to": 180, "step": 3, "count": 61}
    assert rules["foot_contact"]["kimodo"] == ["end-effector[LeftFoot]", "end-effector[RightFoot]"] and rules[None]["kimodo"] == ["root2d"]
    sel = s["select"]["inputs"]
    assert [c["seed"] for c in sel["candidates"]] == [7, 8, 9, 10] and sel["weights"] == selection.WEIGHTS and sel["grip_on"] and sel["swing_on"]
    assert sel["body_clearance"] == "measure" and sel["bones"]["from"] == "default"   # FakeEditor 스켈레톤에는 템플릿 체인이 없다
    assert "SELECTION_BONES_DEFAULTED" in {d["code"] for d in p["diagnostics"]}
    assert s["retarget"]["inputs"]["body_clearance"] == "measure"
    codes = lims_of(cand)
    assert {"GRIP_POSITION_ONLY", "SELECTED_BY_NUMBERS", "BODY_CLEARANCE_MEASURED_FOR_GRIP", "DRAFT_NEEDS_CLEANUP"} <= codes
    assert not {"GRIP_NOT_VALIDATED", "FOOT_CONTACT_NOT_ENFORCED"} & codes
    assert {"REFINE_RESOLVED_AT_RUN", "TEXT_ENCODER_CPU"} <= set(cand["risks"])
    assert not ka.launcher.procs and not ka.fake.writes   # 계획은 모델을 띄우지 않고 쓰지 않는다


def test_without_flags_or_candidates_the_chain_is_revision_10(ka):
    for p in (plan(ka), plan(ka, motion_category="weapon_action", constraints=GRIP, generation={"seed": 7, "refine": {"mode": "off"}})):
        cand = p["candidates"][0]
        assert [s["step"] for s in cand["steps"]] == ["generate", "convert", "import", "retarget", "validate"]
        assert "seeds" not in steps_of(p)["generate"]["inputs"] and "SELECTED_BY_NUMBERS" not in lims_of(cand)
    assert {"GRIP_NOT_VALIDATED", "FOOT_CONTACT_NOT_ENFORCED"} <= lims_of(p["candidates"][0])   # refine off → 지금처럼 한계


def test_candidates_alone_select_with_one_pass(ka):
    p = plan(ka, generation={"seed": 3, "candidates": 3})
    g = steps_of(p)["generate"]["inputs"]
    assert g["refine"]["passes"] == 1 and g["diffusions"] == 3 and g["timeout_s"] == 350 and g["metric_window"] is None
    assert "select" in steps_of(p) and not steps_of(p)["select"]["inputs"]["grip_on"] and "GRIP_POSITION_ONLY" not in lims_of(p["candidates"][0])


def test_refine_blocks_and_postprocess_rules(ka):
    p = sword(ka, generation={"seed": 7, "samples": 2})
    assert {e["provider"]: e["reason"] for e in p["excluded"]}["local_ai"] == "REFINE_WITH_SAMPLES"
    p = sword(ka, generation={"seed": 7, "refine": {"grip": {"to_s": 9.0}}})
    assert {e["provider"]: e["reason"] for e in p["excluded"]}["local_ai"] == "CONSTRAINT_OUT_OF_RANGE"
    p = sword(ka, generation={"seed": 7, "postprocess": "off"})
    assert steps_of(p)["generate"]["inputs"]["postprocess"] is False and {"FOOT_CONTACT_WITHOUT_POSTPROCESS", "POSTPROCESS_OFF"} <= lims_of(p["candidates"][0])
    assert steps_of(sword(ka, animation_name="AS_Vesper_Kimodo_B"))["generate"]["inputs"]["postprocess"] is True


# ---- 실행 ----
def test_candidates_are_retargeted_measured_and_the_best_is_final(ka):
    ka.fake.profiles = {"Cand_BVH_kimodo_00": {"gap": 60.0, "stance": 5.5, "peak": 540.0, "penetration": 39.7},
                        "Cand_BVH_kimodo_01": {"gap": 7.0, "stance": 3.0, "peak": 400.0, "penetration": 5.0},
                        "Cand_BVH_kimodo_02": {"gap": 7.5, "stance": 4.5, "peak": 300.0, "penetration": 0.0, "warnings": ["ROTATION_JUMP_INHERITED"]}}
    p = sword(ka, review={"render": {"count": 2}})
    env = ka.service.generate_motion(plan_id=p["plan_id"], save=True)
    [proc] = ka.launcher.of(KimodoProc)
    a = proc.args
    assert a["candidates_mode"] and a["seeds"] == [7, 8, 9] and a["refine"]["passes"] == 2 and a["metric_window"] == [0.0, 6.0]
    assert a["refine"]["smooth_sigma_frames"] == 1.0   # A — 러너는 계획의 σ 를 받기만 한다
    assert env["result"]["pending"]["handle"]["timeout_s"] == 300 + 25 * 5
    proc.complete("ok")
    job = status(ka, env["result"]["job_id"])
    assert job["stage"] == "convert"
    [blender] = ka.launcher.of(FakeProc)
    items = blender.args["items"]
    assert [i["bvh"].rsplit("/", 1)[1] for i in items] == ["kimodo_00.bvh", "kimodo_01.bvh", "kimodo_02.bvh"]
    assert [bool(i["rest_fbx"]) for i in items] == [True, False, False] and items[1]["review"]["dir"].endswith("frames/c01")
    blender.complete("ok")
    job = status(ka, job["job_id"])
    assert job["status"] == "SUCCEEDED", job.get("error")
    calls = ka.fake.calls
    imports = [q for t, q in calls if t == "import_animation_file"]
    assert len(imports) == 1 + 3 and imports[0]["file"].endswith("_Rest.fbx") and all(q.get("skeleton") for q in imports[1:])
    batch, final = [q for t, q in calls if t == "retarget_animations"]
    assert len(batch["assets"]) == 3 and batch["name_rule"] == {"prefix": "Cand_"} and batch["validate"] is False and batch["body_clearance"] == "measure"
    assert batch["output_path"].endswith("/Candidates")
    measured = next(q for t, q in calls if t == "validate_animation" and len(q["assets"]) == 3)
    assert measured["profile_positions"] and set(measured["profile_bones"]) == {"hand_l", "hand_r", "thigh_l", "thigh_r", "foot_l", "foot_r",
                                                                                "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r", "head"}
    assert measured["body_clearance"]["ik_rig"].endswith("/IK_Target") and measured["source_pelvis"] == "Hips"
    # 최종 = 고른 후보(1) 하나, 같은 RTG(리타기터를 다시 만들지 않는다)
    assert final["assets"] == [batch["assets"][1]] and final["retargeter"] == batch["retargeter"] and final["body_clearance"] == "measure"
    assert sum(1 for t, _ in calls if t == "create_ik_retargeter") == 1
    assert job["generated_assets"] == [f"{OUT}/AS_Vesper_Kimodo_WalkTurn"]
    work = job["work_path"]
    assert {f"{work}/Candidates/Cand_BVH_kimodo_{k:02d}" for k in range(3)} <= set(job["intermediate_assets"])
    # 후보마다 빈 하위 폴더로 임포트(import_animation_file 은 빈 폴더에만 — DEST_NOT_EMPTY)
    assert [q["dest_path"].rsplit("/", 1)[1] for q in imports[1:]] == ["C00", "C01", "C02"] and [q["name"] for q in imports[1:]] == \
        ["BVH_kimodo_00", "BVH_kimodo_01", "BVH_kimodo_02"]
    sel = job["selection"]
    assert sel["picked"]["index"] == 1 and sel["picked"]["seed"] == 8 and [c["rank"] for c in sel["candidates"]] == [3, 1, 2]
    by = {c["index"]: c for c in sel["candidates"]}
    assert by[1]["metrics"]["grip"]["grip_pct"] == 100.0 and by[0]["metrics"]["stance"]["lateral_ratio"]["p90"] == pytest.approx(5.5)
    assert by[0]["metrics"]["non_grip"]["non_grip_penetration_pct_max"] == 39.7 and by[2]["penalties"]["breakage"] == 0.5
    # 관통 경고만 있는 후보(0 · 1)는 PASSED_WITH_WARNINGS 여도 깨짐 0 — 관통은 clearance 가 센다(파지면 비파지 프레임만)
    assert by[1]["status"] == "PASSED_WITH_WARNINGS" and by[1]["penalties"]["breakage"] == 0.0 and by[1]["penalties"]["clearance"] == 0.0
    assert by[1]["metrics"]["breakage"]["scored_warnings"] == [] and by[1]["metrics"]["breakage"]["all_warnings"] == ["BODY_PENETRATION"]
    assert by[0]["penalties"]["clearance"] == 0.397 and by[0]["clearance_basis"] == "non_grip" and by[1]["metrics"]["attack"]["arm_cm"] == 50.0
    again = selection.rank([{k: c[k] for k in ("index", "seed", "status", "metrics")} for c in sel["candidates"]], sel["weights"],
                           grip_on=sel["grip_on"], swing_on=sel["swing_on"])
    assert again["picked"] == sel["picked"]   # 같은 기록 → 같은 선택
    assert job["review"]["frames"][0]["path"].replace("\\", "/").split("/frames/")[1].startswith("c01/")   # Job review = 고른 후보
    codes = {d["code"] for d in job["diagnostics"]}
    assert {"KIMODO_GENERATED", "REFINE_GRIP", "FOOT_CONTACT_CONSTRAINED", "BLENDER_CANDIDATES_CONVERTED", "CANDIDATE_SELECTED"} <= codes
    lims = {lim["code"] for lim in job["limitations"]}
    assert {"SELECTED_BY_NUMBERS", "GRIP_POSITION_ONLY", "BODY_CLEARANCE_MEASURED_FOR_GRIP"} <= lims and "GRIP_NOT_REACHED" not in lims
    gen = job["cursor"]["values"]["generated"]
    assert [c["seed"] for c in gen["candidates"]] == [7, 8, 9] and gen["candidates"][0]["source_metrics"]["pass2"]["grip"]["grip_pct"] == 100.0


def test_failed_candidates_are_excluded_and_all_failed_falls_back(ka):
    ka.fake.profiles = {"Cand_BVH_kimodo_00": {"gap": 7.0, "stance": 3.0, "status": "FAILED"}, "Cand_BVH_kimodo_01": {"gap": 50.0, "stance": 3.0}}
    job = run(ka, sword(ka, generation={"seed": 7, "candidates": 2}))
    assert job["status"] == "SUCCEEDED" and job["selection"]["picked"]["index"] == 1
    assert job["selection"]["candidates"][0]["excluded"] == {"reason": "VALIDATION_FAILED"}
    assert "GRIP_NOT_REACHED" in {lim["code"] for lim in job["limitations"]}   # 남은 후보는 파지 0%
    ka.fake.profiles = {"Cand_BVH_kimodo_00": {"status": "FAILED"}, "Cand_BVH_kimodo_01": {"status": "FAILED"}}
    job = run(ka, sword(ka, generation={"seed": 7, "candidates": 2}, animation_name="AS_Vesper_Kimodo_AllFail", motion_category="full_body_new",
                        search={"query": "rifle aim idle"}))
    assert job["status"] == "SUCCEEDED" and job["provider"] == "existing_motion"
    [h] = job["fallback_history"]
    assert (h["provider"], h["step"], h["cause"], h["reason"]) == ("local_ai", "select", "VALIDATION_FAILED", "ALL_CANDIDATES_FAILED")


def test_one_candidate_with_flags_is_measured_without_a_choice(ka):
    ka.fake.profiles = {"Cand_BVH_kimodo_00": {"gap": 30.0, "stance": 4.0}}
    job = run(ka, sword(ka, generation={"seed": 7}))
    assert job["status"] == "SUCCEEDED", job.get("error")
    sel = job["selection"]
    assert len(sel["candidates"]) == 1 and "only candidate" in sel["picked"]["reason"]
    lim = {x["code"]: x for x in job["limitations"]}["GRIP_NOT_REACHED"]
    assert lim["grip_pct"] == 0.0


def test_candidate_metrics_read_the_profile_clearance_and_every_warning():
    from anim_gen.providers.builtin import DEFAULT_BONES, RetargetPipe
    from conftest import FakeEditor
    item = {"status": "PASSED_WITH_WARNINGS", "numeric": {"pelvis_height_cm": 105.0, "max_deg_per_frame": 114.6,
                                                            "profile": FakeEditor._profile(list(DEFAULT_BONES.values()), {"gap": 10.0, "stance": 4.0, "peak": 330.0}, True)},
            "issues": [{"level": "info", "code": "NOTE"}],
            "body_clearance": {"arms": [{"upper_arm": "upperarm_l", "frames_over_penetration_pct": 72.7, "depth_max": 6.3, "worst": {"time": 0.1}}],
                               "issues": [{"level": "warning", "code": "BODY_PENETRATION"}]},
            "relative": {"issues": [{"level": "warning", "code": "ROTATION_JUMP_INHERITED"}]}}
    m = RetargetPipe.candidate_metrics(item, {**DEFAULT_BONES, "from": "default"}, None, None)
    assert m["grip"]["grip_pct"] == 100.0 and m["stance"]["lateral_ratio"]["p90"] == pytest.approx(4.0) and m["swing"]["peak_cm_s"] == pytest.approx(330.0 / 1.05, abs=1.0)  # 표본 시각은 4자리로 반올림
    assert m["clearance"]["penetration_pct"] == 72.7 and m["non_grip"]["non_grip_penetration_pct_max"] == 0.0 and m["non_grip"]["worst_in_grip"] is True
    assert m["breakage"]["warnings"] == [] and m["breakage"]["all_warnings"] == ["BODY_PENETRATION", "ROTATION_JUMP_INHERITED"]
    assert m["breakage"]["scored_warnings"] == ["ROTATION_JUMP_INHERITED"]   # 관통 검사 밖 경고만 깨짐에 센다
    assert m["attack"]["width_arm_ratio"] == pytest.approx(11.0 / 50.0, abs=1e-3) and m["jitter"]["joints"] == 10 and "missing_bones" not in m


def test_selection_bones_take_shoulders_from_the_arm_chain_and_elbows_from_the_wrist_parent():
    from anim_gen.providers.builtin import RetargetPipe
    tree = (("root", None), ("pelvis", "root"), ("spine_01", "pelvis"), ("clavicle_l", "spine_01"), ("upperarm_l", "clavicle_l"), ("lowerarm_l", "upperarm_l"),
            ("lowerarm_twist_01_l", "lowerarm_l"), ("hand_l", "lowerarm_l"), ("clavicle_r", "spine_01"), ("upperarm_r", "clavicle_r"), ("hand_r", "upperarm_r"),
            ("thigh_l", "pelvis"), ("foot_l", "thigh_l"), ("thigh_r", "pelvis"), ("foot_r", "thigh_r"),
            ("index_01_l", "hand_l"), ("index_02_l", "index_01_l"), ("thumb_01_l", "hand_l"), ("index_01_r", "hand_r"))
    chains = [{"name": "LeftArm", "start": "upperarm_l", "end": "hand_l"}, {"name": "RightArm", "start": "upperarm_r", "end": "hand_r"},
              {"name": "LeftLeg", "start": "thigh_l", "end": "foot_l"}, {"name": "RightLeg", "start": "thigh_r", "end": "foot_r"},
              {"name": "Neck", "start": "neck_01", "end": "neck_02"}, {"name": "Head", "start": "Skull", "end": "Skull"}]

    class Stub:
        def __init__(self, chains):
            self.chains = chains

        def require(self, tool, **params):
            assert tool == "inspect_skeleton" and params["details"]
            return {"bones": [{"name": n, "parent": p} for n, p in tree], "template_match": {"chains": self.chains}}
    diags: list[dict] = []
    b = RetargetPipe.selection_bones(Stub(chains), "/Game/X/SK", diags)
    assert (b["shoulder_l"], b["elbow_l"], b["hand_l"], b["shoulder_r"]) == ("upperarm_l", "lowerarm_l", "hand_l", "upperarm_r")  # 트위스트 본은 형제
    # 손목의 부모가 어깨면 팔꿈치가 아니다 → 기본 이름 · 진단
    assert b["elbow_r"] == "lowerarm_r" and b["from"] == "default" and "elbow_r" in diags[0]["message"]
    # 양손 겹침 기록 — 손 본 아래 자손의 [부모, 자식] (이름을 보지 않는다) · 측정 본에 더해진다
    assert sorted(map(tuple, b["hand_tree_l"])) == [("hand_l", "index_01_l"), ("hand_l", "thumb_01_l"), ("index_01_l", "index_02_l")]
    assert b["hand_tree_r"] == [["hand_r", "index_01_r"]]
    assert {"index_02_l", "thumb_01_l", "index_01_r"} <= set(RetargetPipe.profile_bones(b))
    # 머리 = 템플릿 체인 Head 시작(이름을 보지 않는다) → 없으면 Neck 끝 → 없으면 기본 이름 'head' · 진단 · 측정 본에 더해진다
    assert b["head"] == "Skull" and "Skull" in RetargetPipe.profile_bones(b)
    assert RetargetPipe.selection_bones(Stub(chains[:5]), "/Game/X/SK", [])["head"] == "neck_02"
    diags = []
    assert RetargetPipe.selection_bones(Stub(chains[:4]), "/Game/X/SK", diags)["head"] == "head" and "'head'" in diags[0]["message"]


def test_candidate_metrics_record_hand_contact_from_the_hand_trees():
    from anim_gen.providers.builtin import DEFAULT_BONES, RetargetPipe
    from conftest import FakeEditor
    prof = FakeEditor._profile(list(DEFAULT_BONES.values()), {"gap": 3.0, "stance": 4.0, "peak": 300.0}, True)
    pos = prof["position_cm"]
    for s in ("l", "r"):   # 손가락 하나씩 — 손목에서 +y 8 cm. 손목 간격 3 cm → 손가락끼리 3 cm (2.5 × 1.05 = 2.63 cm 밖)
        pos[f"index_01_{s}"] = [[x, y + 8.0, z] for x, y, z in pos[f"hand_{s}"]]
    bones = {**DEFAULT_BONES, "hand_tree_l": [["hand_l", "index_01_l"]], "hand_tree_r": [["hand_r", "index_01_r"]]}
    item = {"status": "PASSED", "numeric": {"pelvis_height_cm": 105.0, "profile": prof}}
    hc = RetargetPipe.candidate_metrics(item, bones, None, None)["hand_contact"]
    assert hc["contact_pct"] == 0.0 and hc["min_cm"] == pytest.approx(3.0) and hc["threshold_cm"] == pytest.approx(2.625, abs=0.01)
    assert RetargetPipe.candidate_metrics(item, DEFAULT_BONES, None, None)["hand_contact"] is None   # 지표 버전 2 계획(트리 없음)
    # 버전 4 손-머리 근접 — 머리 = 왼 검지 위 9 cm(10 × 1.05 = 10.5 cm 안), 손목에서는 12 cm. 손 트리 점이 있어야 잡힌다 · 꼬임은 제자리 0 %
    pos["head"] = [[x, y, z + 9.0] for x, y, z in pos["index_01_l"]]
    m = RetargetPipe.candidate_metrics(item, bones, None, None)
    assert m["head"]["near_pct"] == 100.0 and m["head"]["points"] == 4 and m["head"]["min_cm"] == pytest.approx(9.0)
    assert RetargetPipe.candidate_metrics(item, DEFAULT_BONES, None, None)["head"]["near_pct"] == 0.0
    assert m["cross"]["crossed_pct"] == 0.0 and m["cross"]["threshold_cm"] == pytest.approx(10.5)


def test_polearm_spacing_moves_the_grip_band_into_select(ka):
    """대상 기준 간격 60 cm(Vesper 낫) — 계획이 대상 팔 치수(가짜 Vesper = 실제 기준 포즈)를 재 생성 간격 75.19 cm 로 바꿔 generate 규칙에, 대상 띠
    60 ± 11.09 cm 를 select 에 싣는다(한 번 잰 측정 본도). 대상 손목 60 cm 후보가 파지 100% · GRIP_NOT_REACHED 없음(손을 모은 후보는 0%)."""
    ka.fake.profiles = {"Cand_BVH_kimodo_00": {"gap": 60.0, "stance": 3.0, "peak": 300.0}, "Cand_BVH_kimodo_01": {"gap": 7.0, "stance": 3.0, "peak": 300.0}}
    p = sword(ka, generation={"seed": 7, "candidates": 2, "refine": {"grip": {"target_spacing_cm": 60}}})
    rule = steps_of(p)["generate"]["inputs"]["refine"]["rules"][0]
    sel = steps_of(p)["select"]["inputs"]
    assert (rule["spacing_cm"], rule["target_spacing_cm"], rule["band_cm"]) == (75.19, 60, [62.19, 88.19]) and "target_spacing_cm 60" in rule["spacing_from"]
    assert sel["grip_spacing"]["target_band_cm"] == [48.91, 71.09] and sel["grip_spacing"]["map"] == rule["spacing_map"] and sel["metric_version"] == 5
    assert sel["bones"]["arm_dims"] == {"shoulder_width_cm": 23.96, "arm_cm": 47.66} and ka.fake.count("inspect_skeleton") >= 1
    lim = {x["code"]: x for x in p["candidates"][0]["expected_limitations"]}["GRIP_SPACING_MAPPED"]
    assert (lim["source_cm"], lim["target_cm"]) == (75.19, 60)
    job = run(ka, p)
    [proc] = ka.launcher.of(KimodoProc)
    assert proc.args["refine"]["rules"][0]["spacing_cm"] == 75.19   # 러너는 생성 간격만 받는다(목표 · 소스 띠)
    by = {c["index"]: c for c in job["selection"]["candidates"]}
    assert by[0]["metrics"]["grip"]["grip_pct"] == 100.0 and by[0]["metrics"]["grip"]["band_cm"] == [48.91, 71.09]
    assert by[0]["metrics"]["grip"]["spacing_cm"] == 60 and by[0]["metrics"]["grip"]["tolerance_cm"] == 11.09 and by[0]["clearance_basis"] == "all_polearm"
    assert by[1]["metrics"]["grip"]["grip_pct"] == 0.0 and job["selection"]["picked"]["index"] == 0   # 손을 모은 후보는 낫 파지가 아니다
    assert "GRIP_NOT_REACHED" not in {lim["code"] for lim in job["limitations"]}


def test_generation_spacing_still_means_the_generation_skeleton(ka):
    """spacing_cm(생성 기준 — 처음 의미 그대로)은 러너에 그대로 가고, 대상 띠는 사상한 47.04 ± 11.09 cm — 버전 4 띠((60 ± 13) × 1.05)였다면 대상
    48 cm 후보는 파지 0% 였다(기록 Job f991aa 의 FAIL 원인). 띠를 못 채우면 GRIP_NOT_REACHED 문구에 대상 띠 · 근거가 실린다."""
    ka.fake.profiles = {"Cand_BVH_kimodo_00": {"gap": 48.0, "stance": 3.0, "peak": 300.0}, "Cand_BVH_kimodo_01": {"gap": 70.0, "stance": 3.0, "peak": 300.0}}
    p = sword(ka, generation={"seed": 7, "candidates": 2, "refine": {"grip": {"spacing_cm": 60}}})
    rule = steps_of(p)["generate"]["inputs"]["refine"]["rules"][0]
    assert (rule["spacing_cm"], rule["target_spacing_cm"], rule["target_band_cm"]) == (60, 47.04, [35.95, 58.13]) and rule["spacing_from"].startswith("request (generation")
    job = run(ka, p)
    by = {c["index"]: c for c in job["selection"]["candidates"]}
    assert by[0]["metrics"]["grip"]["grip_pct"] == 100.0 and by[1]["metrics"]["grip"]["grip_pct"] == 0.0 and job["selection"]["picked"]["index"] == 0
    ka.fake.profiles = {"Cand_BVH_kimodo_00": {"gap": 70.0, "stance": 3.0, "peak": 300.0}}
    job = run(ka, sword(ka, animation_name="AS_Vesper_Kimodo_Wide", generation={"seed": 7, "refine": {"grip": {"spacing_cm": 60}}}))
    lim = {x["code"]: x for x in job["limitations"]}["GRIP_NOT_REACHED"]
    assert lim["band_cm"] == [35.95, 58.13] and "대상 간격 47.04 ± 11.09" in lim["message"]


def test_polearm_spacing_needs_the_target_arms_at_plan_time(ka):
    """자루 무기 간격은 대상 팔 치수로 사상한다 — 에디터가 없거나 대상 어깨 · 팔꿈치 · 손목 기준 위치가 없으면 local_ai 를 계획에서 뺀다(생성 간격 ·
    띠를 정할 수 없다). 대상이 너무 작아 생성 골격 팔이 닿지 않는 간격도 뺀다. 간격이 없으면(검 손잡이) 지금 그대로."""
    def excluded(**gen):
        env = ka.service.plan_motion_generation(request=ai_request(motion_category="weapon_action", constraints=GRIP, provider="local_ai",
                                                                   generation={"seed": 7, **gen}))
        assert env["ok"] and not env["result"]["executable"], env.get("error")
        return {e["provider"]: (e["cause"], e["reason"]) for e in env["result"]["excluded"]}["local_ai"]
    ka.fake.up = False
    assert excluded(refine={"grip": {"target_spacing_cm": 60}}) == ("PROVIDER_UNAVAILABLE", "EDITOR")
    assert excluded(refine={"grip": {"spacing_cm": 60}}) == ("PROVIDER_UNAVAILABLE", "EDITOR")
    ka.fake.up = True
    vesper = ka.fake.bones["/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"]
    ka.fake.bones["/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"] = [b for b in vesper if b["name"] != "lowerarm_r"]
    assert excluded(refine={"grip": {"target_spacing_cm": 60}}) == ("UNSUPPORTED_REQUEST", "TARGET_ARMS_UNKNOWN")
    # 아이 체형(어깨 10 · 팔 20 cm) — 대상 60 cm 는 생성 골격에서 172 cm(두 팔이 닿는 139 cm 너머)
    tiny = {"upperarm_l": (5.0, 0, 120), "upperarm_r": (-5.0, 0, 120), "lowerarm_l": (15.0, 0, 120), "lowerarm_r": (-15.0, 0, 120),
            "hand_l": (25.0, 0, 120), "hand_r": (-25.0, 0, 120)}
    ka.fake.bones["/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"] = [{**b, "ref_component": {"t": list(tiny[b["name"]]), "r": [0, 0, 0]}} if b["name"] in tiny
                                                                    else b for b in vesper]
    assert excluded(refine={"grip": {"target_spacing_cm": 60}}) == ("UNSUPPORTED_REQUEST", "GRIP_SPACING_OUT_OF_RANGE")
    ka.fake.bones["/Game/Assets/IdaFaber/Meshes/Girl/SKEL_UE5_F"] = vesper
    assert steps_of(sword(ka, generation={"seed": 7}))["select"]["inputs"]["grip_spacing"] is None   # 검 손잡이


def test_an_old_plan_with_the_pelvis_scaled_band_is_refused(ka):
    """버전 4 계획(select grip_spacing_cm — × pelvis scale 띠)은 실행 때 PLAN_OUTDATED 로 멈춘다(다른 Provider 로 넘기지 않는다 — 다시 계획)."""
    p = sword(ka, generation={"seed": 7, "candidates": 2, "refine": {"grip": {"spacing_cm": 60}}})
    stored = ka.service.store.load_plan(p["plan_id"])
    inputs = next(s for s in stored["candidates"][0]["steps"] if s["step"] == "select")["inputs"]
    inputs["grip_spacing_cm"] = inputs.pop("grip_spacing")["source_cm"]
    ka.service.store.save_plan(stored)
    job = run(ka, p)
    assert job["status"] == "FAILED" and (job["error"]["code"], job["error"]["reason"]) == ("UNSUPPORTED_REQUEST", "PLAN_OUTDATED")


@pytest.mark.parametrize("spacing, ok", [(60, True), (100, True), (100.5, False), (0, False)])
def test_grip_spacing_reaches_polearm_widths(ka, spacing, ok):
    """낫 기준 보정 — Vesper 운영 낫 애니 양손 구간 50 ~ 78 cm 까지 요청할 수 있다(상한 100)."""
    env = ka.service.plan_motion_generation(request=ai_request(generation={"refine": {"grip": {"spacing_cm": spacing}}}))
    assert env["ok"] is ok or (not ok and env["error"]["details"]["field"] == "generation.refine.grip.spacing_cm")


def test_the_wider_hand_path_wins_when_everything_else_ties(ka):
    """C ③ — 같은 파지 · 발 · 휘두름이면 엉덩 기준 손 궤적 폭(팔 길이 대비)이 넓은 후보. weapon_action 이 아니면 궤적 폭은 점수 밖."""
    ka.fake.profiles = {"Cand_BVH_kimodo_00": {"gap": 7.0, "stance": 3.0, "peak": 300.0},
                        "Cand_BVH_kimodo_01": {"gap": 7.0, "stance": 3.0, "peak": 300.0, "reach": 60.0}}
    job = run(ka, sword(ka, generation={"seed": 7, "candidates": 2}))
    sel = job["selection"]
    by = {c["index"]: c for c in sel["candidates"]}
    assert sel["picked"]["index"] == 1 and "attack" in sel["picked"]["reason"] and by[1]["penalties"]["attack"] == 0.0
    w0, w1 = by[0]["metrics"]["attack"]["width_arm_ratio"], by[1]["metrics"]["attack"]["width_arm_ratio"]
    assert w1 > 1.0 > w0 and by[0]["penalties"]["attack"] == pytest.approx(max(1 - w0 / w1, 1 - w0), abs=1e-3)   # 상대 · 하한 중 큰 쪽
    job = run(ka, sword(ka, motion_category="full_body_new", animation_name="AS_Vesper_Kimodo_Plain", generation={"seed": 7, "candidates": 2}))
    assert job["selection"]["picked"]["index"] == 0 and all(c["penalties"]["attack"] is None for c in job["selection"]["candidates"])


def test_refine_off_runs_kimodo_without_candidates(ka):
    job = run(ka, sword(ka, generation={"seed": 7, "refine": {"mode": "off"}}))
    assert job["status"] == "SUCCEEDED" and job["selection"] is None
    [proc] = ka.launcher.of(KimodoProc)
    assert "candidates_mode" not in proc.args and "items" not in ka.launcher.of(FakeProc)[-1].args
    assert not any(t == "retarget_animations" and q.get("name_rule", {}).get("prefix") for t, q in ka.fake.calls)
