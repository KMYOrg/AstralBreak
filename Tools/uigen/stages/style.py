"""style — 게이트를 통과한 뒤의 외형 검토 라운드 (1b 후속 C, 설계 §2-2 '통과 뒤 라운드' · §8-3).

합격 판정은 그대로 게이트만 한다(결정 6). 통과한 화면을 컨셉과 영역 · 글자마다 비교해(`gen/fidelity.region_report` — 기록만)
LLM 두 번으로 외형만 손본다:
  style_verifier(보는 눈 — prompts/style_verifier.md): 영역마다 '컨셉 | 렌더' 나란히 그림 + 지표 표 + spec → 보이는 외형 차이와 제안 op
  style_fix(고치는 손 — prompts/style_fix.md): 허용된 op 만의 spec patch
허용 op: set 의 경로가 `style.*` · `font.color|weight|size|family|outline|shadow|letter_spacing|gradient` · `slot.padding` · `justification` 인 것,
`replace_asset`(regenerate — 따온 에셋은 extract 그대로 다시 편집, 프롬프트 바꿀 수 있음, 라운드당 상한 · run 의 codex 상한 안).
배치(slot.position · size · anchors · alignment · size_rule …) · 트리 · 바인딩 · bbox_intent 는 못 고친다 — 게이트가 이미 맞춘 것이다.
(1b 후속 F) 단 글자 크기 · 폰트를 바꾸면 그 글자의 bbox_intent 는 파이프라인이 새 줄 상자로 따라 바꾼다(`follow_text_boxes` — bbox_intent = 그 크기의
줄 상자라는 analyze 규칙). 안 그러면 줄이는 크기가 옛 상자와의 말단 IoU 에 막힌다(C1 — 배너 44 → 37 대신 42).
라운드 뒤 게이트가 하나라도 깨지면 오케스트레이터가 그 라운드를 버린다(run_pipeline._style_review — 마지막 통과 spec 으로 다시 build).
"""
from __future__ import annotations

import json

from core import config
from core import llm
from core import patch as patch_mod
from core import schema
from core import spec as spec_mod
from stages import fix as fix_mod

STYLE_SET_EXACT = {"font.color", "font.weight", "font.size", "font.family", "font.letter_spacing", "slot.padding", "justification",
                   "font.outline", "font.shadow", "font.gradient"}
STYLE_SET_PREFIXES = ("style.", "font.outline.", "font.shadow.", "font.gradient.")
FIX_CALLS = 2


def allowed_path(path: str) -> bool:
    return path in STYLE_SET_EXACT or path.startswith(STYLE_SET_PREFIXES)


def codex_left(run) -> int:
    """run 의 codex 호출 상한까지 남은 수(codex_calls.jsonl — 실패도 센다)."""
    limit = int((run.cfg.get("limits") or {}).get("codex_calls_per_run", 20))
    p = run.path("codex_calls.jsonl")
    used = len(p.read_text(encoding="utf-8").splitlines()) if p.is_file() else 0
    return max(0, limit - used)


def guard_style_ops(ops: list[dict], spec: dict, brief: dict, cfg: dict, codex_budget: int) -> list[str]:
    """외형 라운드가 넘으면 안 되는 선 — fix 의 가드(bbox_intent · binding · 계약 글자 · 필수 요소) + 허용 경로 · 폰트 · 에셋 교체 상한."""
    errs = fix_mod.guard_ops(ops, spec, brief)
    sr = cfg.get("style_review") or {}
    families = {r["family"] for r in config.font_roles(cfg, brief.get("font")).values()}
    assets = {a["asset_id"]: a for a in spec.get("assets", [])}
    max_ops = int(sr.get("max_ops", 16))
    max_replace = min(int(sr.get("max_replace_per_round", 1)), codex_budget)
    replaces = 0
    if len(ops) > max_ops:
        errs.append(f"{len(ops)} ops — at most {max_ops} per round")
    for i, op in enumerate(ops):
        kind = op.get("op")
        if kind == "set":
            path = str(op.get("path", ""))
            if not allowed_path(path):
                errs.append(f"op {i}: set {op.get('widget')}.{path} — the style round may only set style.*, font.color/weight/size/family/outline/shadow/"
                            "letter_spacing/gradient, slot.padding or justification (layout already passes the gates)")
            if path == "font.family" and op.get("value") not in families:
                errs.append(f"op {i}: font.family {op.get('value')!r} — use one of the project fonts: {sorted(families)}")
        elif kind == "replace_asset":
            replaces += 1
            a = assets.get(op.get("asset"))
            if a is None or a.get("provenance") != "codex":
                errs.append(f"op {i}: replace_asset {op.get('asset')!r} — only codex assets can be redone in the style round")
            if not op.get("regenerate"):
                errs.append(f"op {i}: replace_asset needs regenerate: true")
        else:
            errs.append(f"op {i}: '{kind}' — the style round uses only set and replace_asset")
    if replaces > max_replace:
        errs.append(f"{replaces} replace_asset ops — at most {max_replace} this round (per-round limit / codex calls left {codex_budget})")
    return errs


def _line_height(cfg: dict, family: str | None, size: float) -> float | None:
    """그 폰트(역할 family 또는 sdf_family)의 줄 높이 표에서 크기 → px(사이는 직선 보간, 밖은 가장 가까운 칸의 비율)."""
    table = None
    for v in config.font_roles(cfg).values():
        if family in (v["family"], v.get("sdf_family")):
            table = v["line_height"]
            break
    if not table:
        return None
    pts = sorted((float(k), float(x)) for k, x in table.items())
    if size <= pts[0][0]:
        return pts[0][1] * size / pts[0][0]
    if size >= pts[-1][0]:
        return pts[-1][1] * size / pts[-1][0]
    for (s0, h0), (s1, h1) in zip(pts, pts[1:]):
        if s0 <= size <= s1:
            return h0 + (h1 - h0) * (size - s0) / (s1 - s0)
    return None


ALIGN_FRACTION = {"left": 0.0, "top": 0.0, "center": 0.5, "right": 1.0, "bottom": 1.0}    # fill = 부모가 정함(따라가지 않음)


def _axis_follow(w: dict) -> tuple[float | None, float | None]:
    """축(가로, 세로)마다 글자 크기가 상자 길이를 정하면 그대로 남는 점의 비율(0 = 시작 · 0.5 = 가운데 · 1 = 끝), 아니면 None.
    [실측 F 끝 run 1] 캔버스 고정 크기('오의 불가')나 채움 정렬(배너 라벨의 가로)은 글자 크기와 무관하게 렌더 상자가 그대로라
    bbox_intent 만 바꾸면 게이트가 깨졌다(iou_region 0.714 · iou_leaf 0.631)."""
    slot = w.get("slot") or {}
    kind = slot.get("kind")
    d = spec_mod.SLOT_DEFAULTS.get(kind, {})

    def align(key):
        return ALIGN_FRACTION.get(slot.get(key, d.get(key)))
    if kind == "canvas":
        a, al = slot.get("anchors") or [0, 0, 0, 0], slot.get("alignment") or [0, 0]
        if not slot.get("auto_size") or a[0] != a[2] or a[1] != a[3]:
            return None, None
        return float(al[0]), float(al[1])                                   # 자동 크기 — 정렬점(위치)이 그대로
    auto = slot.get("size_rule", d.get("size_rule")) == "auto"
    # 박스 주축: 자동이면 칸 = 글자 길이(가운데로 근사 — 형제가 밀리는 것은 padding 몫), 채움이면 칸은 고정이고 글자는 그 칸 안에서 정렬을 따른다
    if kind == "horizontal_box":
        return (0.5 if auto else align("h_align")), align("v_align")
    if kind == "vertical_box":
        return align("h_align"), (0.5 if auto else align("v_align"))
    if kind in ("overlay", "border", "size_box", "button", "uniform_grid"):
        return align("h_align"), align("v_align")
    return None, None


PADDED_SLOTS = ("overlay", "vertical_box", "horizontal_box", "border", "size_box", "button")


def follow_text_boxes(before: dict, after: dict, cfg: dict, rendered: dict[str, list] | None = None) -> list[dict]:
    """1b 후속 F — 라운드가 글자 크기 · 폰트 · 자간 · 외곽선을 바꾼 TextBlock 을 **자기 가운데를 중심으로만** 커지게 하고(레이아웃의 다른 것은 그대로),
    게이트 기준 bbox_intent 를 그 예상 상자로 바꾼다. 글자가 길이를 정하는 축만(`_axis_follow` — 채움 · 캔버스 고정 크기 축은 그대로):
      늘어나는 길이 Δ = 직전 통과 렌더 상자(rendered — 없으면 bbox_intent)에서 — 폭 = (글자 몸통 × 크기 비) + (글자 수 − 1) × 글자 사이 px
      + 외곽선 양쪽, 높이 = (줄 × 줄 높이 비) + 외곽선 위아래(외곽선 · 빛은 상자를 사방 그만큼 키운다),
      슬롯 padding 을 그 축 양쪽에서 Δ/2 씩 줄인다(음수 가능 — 슬롯이 차지하는 자리가 그대로라 형제 · 행 · 패널이 안 움직인다,
      빛 보정 analyze._glow_layout 과 같은 방식), 캔버스 자동 크기는 위치 += Δ(alignment − 0.5),
      bbox_intent = 그 렌더 상자를 가운데 기준 Δ 만큼 키운 것.
    [실측 F 끝 run 1 · 2] bbox_intent 를 비율로 키우면 ① 고정 · 채움 축(렌더 그대로)에서 ② analyze 상자가 글자보다 넓을 때(체인 제목 104 vs 57 px —
    높이가 48 px 를 넘어 '작은 상자 → IoU' 판정이 바뀜) 게이트가 깨졌고, ③ style_fix 가 형제를 padding 으로 직접 보정하다 '3' 을 10 px 밀었다.
    after 는 제자리에서 바뀐다. → 바꾼 기록."""
    old = {w["id"]: w for w in before.get("widgets", [])}
    rendered = rendered or {}
    out = []

    def spacing_px(f, size):      # 글자 사이 px — [실측 F 끝 run 3] 자간 133 → 280 · 크기 38 · 6 글자 → 폭 +25 = 5 × (⌊10.64⌋ − ⌊5.05⌋)
        return int(size * float(f.get("letter_spacing") or 0) / 1000.0)

    def outline_px(f):            # 외곽선(빛 포함)은 상자를 사방 그만큼 키운다(analyze._glow_layout 과 같은 실측)
        return float((f.get("outline") or {}).get("size") or 0) + float((f.get("glow") or {}).get("size") or 0)
    for w in after.get("widgets", []):
        b = old.get(w["id"])
        if w.get("type") != "TextBlock" or not b or not w.get("bbox_intent"):
            continue
        f0, f1 = b.get("font") or {}, w.get("font") or {}
        s0, s1 = float(f0.get("size") or 24), float(f1.get("size") or 24)
        sp0, sp1, o0, o1 = spacing_px(f0, s0), spacing_px(f1, s1), outline_px(f0), outline_px(f1)
        if s0 == s1 and f0.get("family") == f1.get("family") and sp0 == sp1 and o0 == o1:
            continue
        lh0, lh1 = _line_height(cfg, f0.get("family"), s0), _line_height(cfg, f1.get("family"), s1)
        rec = {"widget": w["id"], "size": [s0, s1], "old_bbox": list(w["bbox_intent"])}
        if sp0 != sp1:
            rec["letter_spacing_px"] = [sp0, sp1]
        if o0 != o1:
            rec["outline_px"] = [o0, o1]
        if not lh0 or not lh1:
            out.append({**rec, "skipped": "no line-height table for the font"})
            continue
        fx, fy = _axis_follow(w)
        slot = w.get("slot") if isinstance(w.get("slot"), dict) else None
        if fy is None:
            # 세로가 채움 · 캔버스 고정 크기 — 글자는 상자 위쪽 기준으로 그려져 아래로만 커진다 → 줄 높이 변화의 절반만큼 위로(가운데 유지)
            # [실측 F 끝 run 4] 채움 상자의 '4.2' 를 56 → 64 로 키우자 아래 '2/4' 에 닿았다
            dh_fixed = (lh1 - lh0) + 2 * (o1 - o0)
            moved = _shift_up_fixed_text(w, slot, dh_fixed / 2)
            if moved:
                rec["shift_up"] = moved
        if fx is None and fy is None:
            out.append({**rec, "skipped": "the layout fixes this text's box size (fixed canvas size or fill on both axes)"
                        + ("; moved up to keep the glyph centre" if rec.get("shift_up") else "")})
            continue
        base = rendered.get(w["id"])
        rec["from"] = "render" if base else "bbox_intent"
        bx, by, bw, bh = (float(v) for v in (base or w["bbox_intent"]))
        t = w.get("text") or {}
        gaps = max(0, len(t.get("value") or t.get("sample") or "") - 1)
        # 새 폭 = (글자 몸통 × 크기 비) + 글자 사이 + 외곽선 양쪽, 새 높이 = (줄 × 줄 높이 비) + 외곽선 위아래
        dw = ((bw - gaps * sp0 - 2 * o0) * s1 / s0 + gaps * sp1 + 2 * o1 - bw) if fx is not None else 0.0
        dh = ((bh - 2 * o0) * lh1 / lh0 + 2 * o1 - bh) if fy is not None else 0.0
        ix, iy, iw, ih = (float(v) for v in w["bbox_intent"])
        nx, nw = (bx - dw / 2, bw + dw) if fx is not None else (ix, iw)
        ny, nh = (by - dh / 2, bh + dh) if fy is not None else (iy, ih)
        if fy is None:          # 세로는 위에서 이미 위로 옮겼다(_shift_up_fixed_text) — 그 결과를 쓴다
            ny, nh = (float(v) for v in w["bbox_intent"][1::2])
        w["bbox_intent"] = [round(nx, 1), round(ny, 1), round(nw, 1), round(nh, 1)]
        if fy is None:
            dh = 0.0           # 아래 padding 계산에서 세로는 건드리지 않는다
        if isinstance(slot, dict) and slot.get("kind") in PADDED_SLOTS:
            p = list(slot.get("padding") or spec_mod.SLOT_DEFAULTS.get(slot["kind"], {}).get("padding") or [0, 0, 0, 0])
            slot["padding"] = [round(p[0] - dw / 2, 1), round(p[1] - dh / 2, 1), round(p[2] - dw / 2, 1), round(p[3] - dh / 2, 1)]
            rec["padding"] = slot["padding"]
        elif isinstance(slot, dict) and slot.get("kind") == "canvas":
            al, pos = slot.get("alignment") or [0, 0], slot.get("position") or [0, 0]
            slot["position"] = [round(pos[0] + dw * (al[0] - 0.5), 1), round(pos[1] + dh * (al[1] - 0.5), 1)]
            rec["position"] = slot["position"]
        out.append({**rec, "bbox": w["bbox_intent"], "axes": [fx is not None, fy is not None], "grow": [round(dw, 1), round(dh, 1)],
                    "line_height": [round(lh0, 1), round(lh1, 1)]})
    return out


def _shift_up_fixed_text(w: dict, slot: dict | None, d: float) -> dict | None:
    """세로 크기가 레이아웃으로 정해진 글자(채움 · 캔버스 고정 크기)를 d px 위로 — 줄이 d·2 만큼 커질 때 글자 가운데가 그대로 있게.
    padding 슬롯: 위 padding −d(상자 위쪽이 d 올라가고 높이 +d, 아래는 그대로) · 캔버스 점 앵커: 위치 y −d(상자 크기 그대로). → 기록 또는 None."""
    if not slot or abs(d) < 0.05:
        return None
    x, y, bw, bh = (float(v) for v in w["bbox_intent"])
    kind = slot.get("kind")
    if kind in PADDED_SLOTS:
        p = list(slot.get("padding") or spec_mod.SLOT_DEFAULTS.get(kind, {}).get("padding") or [0, 0, 0, 0])
        p[1] = round(p[1] - d, 1)
        slot["padding"] = p
        w["bbox_intent"] = [x, round(y - d, 1), bw, round(bh + d, 1)]
        return {"padding_top": p[1], "by": round(d, 1)}
    if kind == "canvas":
        a = slot.get("anchors") or [0, 0, 0, 0]
        if a[1] != a[3]:
            return None
        pos = slot.get("position") or [0, 0]
        slot["position"] = [pos[0], round(pos[1] - d, 1)]
        w["bbox_intent"] = [x, round(y - d, 1), bw, bh]
        return {"position_y": slot["position"][1], "by": round(d, 1)}
    return None


def rendered_boxes(run, attempt: int) -> dict[str, list]:
    """시도 attempt 의 렌더 geometry(attempts/NNN/geometry.json — 캔버스 해상도)에서 위젯 id → [x, y, w, h]. 없으면 {}."""
    p = run.path("attempts", f"{attempt:03d}", "geometry.json")
    if not p.is_file():
        return {}
    g = json.loads(p.read_text(encoding="utf-8"))
    w, h = (g.get("canvas") or [1920, 1080])[:2]
    return {e["id"]: [e["x"], e["y"], e["w"], e["h"]] for e in (g.get("geometry") or {}).get(f"{w}x{h}", [])}


SNAPSHOT_FILES = ("manifest.json", "refine.json")


def snapshot(run, k: int, assets: list[str]) -> str:
    """라운드 전 상태 사본 — 에셋 교체가 같은 파일(assets/final|raw|compare/<id>.png)을 덮어쓰므로 버릴 때 되돌릴 것. → 사본 폴더(run 기준)"""
    import shutil
    rel = f"style/round_{k:03d}_backup"
    dst = run.path(rel)
    dst.mkdir(parents=True, exist_ok=True)
    files = list(SNAPSHOT_FILES) + [f"assets/{kind}/{aid}.png" for aid in assets for kind in ("final", "raw", "compare")]
    for f in files:
        if run.path(f).is_file():
            (dst / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(run.path(f), dst / f)
    return rel


def restore(run, rel: str) -> list[str]:
    import shutil
    src = run.path(rel)
    done = []
    for p in sorted(src.rglob("*")):
        if p.is_file():
            f = p.relative_to(src).as_posix()
            shutil.copyfile(p, run.path(f))
            done.append(f)
    return done


def compare(run, label: str) -> dict:
    """reference ↔ render.png(force_visible) 영역 · 글자 비교 → style/<label>/report.json + 나란히 그림. 실패해도 예외 대신 {error}."""
    from gen import fidelity
    out_dir = run.path("style", label)
    try:
        rep = fidelity.region_report(run.path("reference.png"), run.path("render.png"), run.read_json("spec.json"), out_dir)
    except Exception as exc:  # noqa: BLE001 — 기록 지표
        rep = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    rep["label"] = label
    run.write_json(f"style/{label}/report.json", rep)
    return rep


def _metric_lines(rep: dict) -> str:
    rows = []
    for rid, r in (rep.get("regions") or {}).items():
        rows.append(f"- region {rid}: sheet {r.get('sheet')} · frame line F1 {(r.get('line_f1') or {}).get('f1')} · silhouette IoU {r.get('shape_iou')} · "
                    f"line color ΔE00 {(r.get('delta_e00') or {}).get('lines')} · texts {', '.join(r.get('texts') or []) or '-'}")
    for tid, t in (rep.get("texts") or {}).items():
        if "error" in t:
            rows.append(f"- text {tid}: {t['error']}")
            continue
        rows.append(f"- text {tid}: glyph box concept {t['ink_box_concept']} vs render {t['ink_box_render']} (in its bbox) · height ratio {t['h_ratio']} · "
                    f"width ratio {t['w_ratio']} · glyph color concept {t['concept_ink']} vs render {t['render_ink']} (ΔE00 {t['ink_de00']})")
    for gid, g in (rep.get("gauges") or {}).items():
        if isinstance(g, dict) and g.get("filled"):
            rows.append(f"- gauge {gid}: filled rows ΔE00 mean {g['filled']['rows']['mean']} · empty part ΔE00 {(g.get('empty') or {}).get('representative')}")
    return "\n".join(rows)


def propose(run, k: int, rep: dict, cli: list[str] | None = None) -> dict:
    """라운드 k — style_verifier → style_fix → 가드 · 사본 적용. → {fixes, patch(None = 고칠 것 없음), patch_file, branch, assets, cost_usd, error?}"""
    spec, brief = run.read_json("spec.json"), run.read_json("brief.json")
    sdir = run.path("style", rep.get("label", f"round_{k}"))
    sheets = [sdir / r["sheet"] for r in (rep.get("regions") or {}).values() if r.get("sheet")]
    files = {"reference": run.path("reference.png"), "render": run.path("render.png"), "spec": run.path("spec.json")}
    listing = "\n".join(f"- {n}: {p.resolve().as_posix()}" for n, p in files.items())
    listing += "".join(f"\n- region sheet (left/top = concept, right/bottom = render): {p.resolve().as_posix()}" for p in sheets)
    budget = codex_left(run)
    families = {r: v["family"] for r, v in config.font_roles(run.cfg, brief.get("font")).items()}
    common = (f"Project fonts by role: {json.dumps(families)}. {fix_mod._line_height_note(run.cfg, spec)}\n"
              f"codex calls left for replace_asset this run: {budget} (at most {min(budget, int((run.cfg.get('style_review') or {}).get('max_replace_per_round', 1)))} this round).")
    v_prompt = (f"UI style review for run {run.run_id}, round {k}. Every gate already passes; compare how the render LOOKS against the concept and list "
                f"the visible differences that the allowed ops can fix. Read the region sheets first.\n{listing}\nMeasured (recorded only):\n{_metric_lines(rep)}\n{common}")
    cost = 0.0
    try:
        v = llm.run_stage("style_verifier", v_prompt, run.cfg, fix_mod.FIXES_OUTPUT_SCHEMA, cli=cli)
    except llm.LlmError as exc:
        fix_mod._llm_row(run, "style_verifier", k, exc.details, exc.code)
        return {"fixes": [], "patch": None, "patch_file": None, "branch": None, "assets": [], "cost_usd": float((exc.details or {}).get("cost_usd") or 0),
                "error": f"style verifier failed: {exc.code}"}
    cost += float(v.get("cost_usd") or 0)
    raw = v["structured_output"].get("fixes", [])
    run.write_json(f"style/round_{k:03d}_verifier.json", v["structured_output"])
    fixes = [f for f in raw if not schema.errors("fixes", {"schema_version": 1, "fixes": [f]})]
    fix_mod._llm_row(run, "style_verifier", k, v, extra={"fixes": len(fixes)})
    if not fixes:
        return {"fixes": [], "patch": None, "patch_file": None, "branch": None, "assets": [], "cost_usd": round(cost, 4), "error": "no style findings"}
    base = (f"UI style fix for run {run.run_id}, round {k}. Turn the style findings into ONE spec patch using only the allowed ops.\n"
            f"Spec (current, absolute path — Read it): {files['spec'].resolve().as_posix()}\nFindings:\n{json.dumps(fixes, ensure_ascii=False)}\n{common}\n"
            f"Contract widgets (their binding and text are fixed): {', '.join(sorted(fix_mod._contract_widgets(brief)))}.")
    prompt, errs, ops = base, [], []
    for c in range(1, FIX_CALLS + 1):
        try:
            f = llm.run_stage("style_fix", prompt, run.cfg, fix_mod.PATCH_OUTPUT_SCHEMA, cli=cli)
        except llm.LlmError as exc:
            fix_mod._llm_row(run, "style_fix", k, exc.details, exc.code, {"call": c})
            return {"fixes": fixes, "patch": None, "patch_file": None, "branch": None, "assets": [], "cost_usd": round(cost, 4),
                    "error": f"style fix failed: {exc.code}"}
        cost += float(f.get("cost_usd") or 0)
        ops = f["structured_output"].get("ops", [])
        run.write_json(f"style/round_{k:03d}_fix_{c}.json", f["structured_output"])
        errs = guard_style_ops(ops, spec, brief, run.cfg, budget)
        if not ops:
            errs.append("the patch has no ops")
        if not errs:
            try:
                patch_mod.apply_patch(spec, {"schema_version": 1, "source": "fix", "ops": ops})
            except patch_mod.PatchError as exc:
                errs = [str(exc)] + [str(e) for e in (exc.details.get("errors") or [])[:8]]
        fix_mod._llm_row(run, "style_fix", k, f, extra={"call": c, "ops": len(ops), "errors": len(errs)})
        if not errs:
            break
        prompt = base + "\n\nYour previous patch was rejected — fix every problem and return the complete corrected patch:\n" + "\n".join(f"- {e}" for e in errs[:20])
    if errs:
        return {"fixes": fixes, "patch": None, "patch_file": None, "branch": None, "assets": [], "cost_usd": round(cost, 4),
                "error": "style fix produced no usable patch: " + "; ".join(errs[:4])}
    patch = {"schema_version": 1, "base_revision": None, "source": "fix", "note": f"style round {k} — appearance only (gates already pass)", "ops": ops}
    schema.require("patch", patch)
    rel = f"patches/style_{k:03d}.json"
    run.write_json(rel, patch)
    return {"fixes": fixes, "patch": patch, "patch_file": rel, "branch": patch_mod.branch_for(patch), "assets": patch_mod.regenerate_assets(patch),
            "cost_usd": round(cost, 4)}
