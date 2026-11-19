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
TEXT_WIDGETS = ("TextBlock", "RichTextBlock")


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
    types = {w["id"]: w.get("type") for w in spec.get("widgets", [])}
    for i, op in enumerate(ops):
        kind = op.get("op")
        if kind == "set":
            path = str(op.get("path", ""))
            if types.get(op.get("widget")) in TEXT_WIDGETS:
                # 1b 후속 J-c — 글자 스타일(크기 · 굵기 · 외곽선 · 빛 · 색 · 자리)은 결정적 측정만(analyze 파생 · 글자 맞춤 · 진단) — [실측 R20261117_154442]
                # 외형 라운드가 측정 오판을 키워 왼쪽 라벨에 남색 외곽선 2 px · 굵게를 넣었다
                errs.append(f"op {i}: set {op.get('widget')}.{path} — text widgets are styled and placed by deterministic measurement only "
                            "(colour · glow from the concept, size · weight · position by the text fit); leave text alone in the style round")
                continue
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


TEXT_FIT_MIN_PX = 2.0         # 이보다 작은 중심 차는 그대로
TEXT_FIT_MAX_PX = 40.0        # 이보다 큰 차는 측정 오류로 보고 건너뜀(글자 높이 × TEXT_FIT_MAX_H 도 상한) — [실측 G 끝 run 3] 배너 라벨 30 px
TEXT_FIT_MAX_H = 0.8
TEXT_FIT_H = (0.88, 1.12)     # 글자 높이 비가 이 밖이면 크기 문제(크기 판 몫) — 위치 판은 위치 · 자간을 재지 않는다
TEXT_FIT_W_TOL = 0.04         # 폭 비가 이만큼 넘게 다르면 자간으로(글자 2 개 이상)
TEXT_FIT_MARGIN = 0.3         # 측정 상자 = 컨셉 획 상자 + 획 높이 × 이 비율(최소 6 px)
TEXT_FIT_WIDEN = 2            # 렌더 획이 측정 상자 끝에 닿으면 그쪽만 여유만큼 넓혀 다시 재는 횟수
TEXT_FIT_WEIGHT_STEP = 1.22   # 굵기 경계 = Bold/Regular 획 밀도 비의 기하 중간 — [실측 PIL] Pretendard 1.52 → 1.233 · Noto Serif KR 1.49 → 1.221
TEXT_FIT_TRUST_H = (0.7, 1.4)    # 크기 판 — 높이 비가 이 안이고 폭 비 ÷ 높이 비가 1 ± TEXT_FIT_TRUST_WH 면 측정을 믿고 크기 · 굵기를 판정 — 위치 · 자간은 TEXT_FIT_H.
                                 # [실측 H2 조작 안내 R184042] 'T' 컨셉 측정이 배지 베벨까지 잡아 0.632 → 크기 40 → 63(배지 밖으로) — 0.6 ~ 1.6 을 좁힘.
                                 # 하한은 0.75 면 아래 G2 '4.2' 0.742(정당한 보정)를 막아 0.7
NOTEXT_INK_MIN = 48.0            # 글자 없는 판 차이 마스크 — 글자 상자마다 오츠 문턱(차 > NOTEXT_INK_FLOOR 인 픽셀로), 최소 이것
NOTEXT_INK_FLOOR = 24.0
NOTEXT_INK_GROW = 2
TEXT_FIT_TRUST_WH = 0.3        # [실측 G2 전투 HUD run] 작게 나온 '4.2' 0.742(폭 0.674 → 0.91)를 0.75 하한이 막았다 · 잘린 '2/4' 0.379(폭 0.643 → 1.70)는 걸러야 한다
TEXT_FIT_SIZE_TOL = 0.04      # 크기 판 — |1 − 높이 비| 가 이 이상이면 새 크기 = round(크기 ÷ 높이 비) — [실측 G 굵기 끝 run] 외형 라운드가 버려지자 배너 0.90 · '4.2' 0.80
TEXT_FIT_MODES = ("size", "place")


def _frame_drop(img, spec: dict):
    """영역(루트 직계)마다 테두리에 이어진 장식선 덩어리(테두리선 · 모서리 장식 — gen/concept_pixels.frame_lines, 영역 상자를 실루엣으로) → 이미지 크기 마스크(2 px 넓힘).
    패널 폭 글자 상자('체인' · '2/4')의 획 검출에 모서리 장식이 섞이지 않게(1b 후속 G)."""
    import cv2
    import numpy as np
    from gen import concept_pixels as cp
    from gen import cutout
    H, W = img.shape[:2]
    out = np.zeros((H, W), bool)
    index = spec_mod.widget_index(spec)
    root = spec.get("root")

    def region_of(wid):
        cur = index.get(wid)
        while cur and cur.get("parent") not in (root, None) and cur.get("parent") in index:
            cur = index[cur["parent"]]
        return cur["id"] if cur else wid
    # 다른 영역의 글자 상자는 이 영역의 테두리선으로 지우지 않는다 — [실측 H3 R20261117_095249] 가운데 엠블럼 영역 상자 오른쪽 끝(x 1280)이 '어빌리티'
    # 첫 글자를 지나가 '어' 의 'ㅇ' 이 엠블럼 테두리선으로 빠짐 → 컨셉 획 1286 부터(정답 1272) · 높이 비 0.83 · 폭 비 1.17 로 어긋나 크기 판이 건너뛰고 작은 34 가 남았다
    text_boxes = [(region_of(t["id"]), t["bbox_intent"]) for t in spec.get("widgets", []) if t.get("type") == "TextBlock" and t.get("bbox_intent")]
    for w in spec.get("widgets", []):
        if w.get("parent") != spec.get("root") or not w.get("bbox_intent") or w.get("type") == "TextBlock":
            continue
        x, y, bw, bh = w["bbox_intent"]
        x0, y0, x1, y1 = max(0, int(x)), max(0, int(y)), min(W, int(np.ceil(x + bw))), min(H, int(np.ceil(y + bh)))
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        crop = img[y0:y1, x0:x1]
        # 띠처럼 큰 장식선 덩어리(실루엣의 15 % 넘게 — 밝은 청록 띠)는 테두리 띠만 — cutout.frame_keep 과 같은 규칙 [실측 H2 R20261116_212033]
        # 띠 전체와 거기 닿은 '어빌리티' 획까지 빠져 컨셉 획이 비었고 analyze 의 굵게가 그대로 남았다
        fl = cutout.frame_keep(crop, np.ones(crop.shape[:2], bool), max(2.0, cp.EDGE_FRAC * min(x1 - x0, y1 - y0)))
        m = cv2.dilate(fl.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        for rid, bb in text_boxes:
            if rid == w["id"]:
                continue
            tx0, ty0 = max(x0, int(bb[0])), max(y0, int(bb[1]))
            tx1, ty1 = min(x1, int(np.ceil(bb[0] + bb[2]))), min(y1, int(np.ceil(bb[1] + bb[3])))
            if tx1 > tx0 and ty1 > ty0:
                m[ty0 - y0:ty1 - y0, tx0 - x0:tx1 - x0] = False
        out[y0:y1, x0:x1] |= m
    return out


def _ink_abs(img, box, gaps: bool = False, drop=None, prefer: str | None = None, mask=None):
    """측정 상자 안 글자 획 상자(절대 좌표). gaps 면 (상자, 획 상자 안 세로 투영의 빈 열 수 — 글자 사이 틈, 획 밀도 = 획 픽셀 / 획 상자 넓이).
    drop = 뺄 픽셀(이미지 크기). prefer = 글자 쪽 밝기('bright' | 'dark' — fidelity.text_ink).
    mask(1b 후속 J-c) = 그 글자의 핵심 획 마스크(gen/diagnose.run_text_masks — 진단과 같은 획, 빛 번짐 제외) — 있으면 밝기 가르기 대신 그것."""
    from gen import fidelity
    x0, y0, x1, y1 = box
    if x1 - x0 < 4 or y1 - y0 < 4:
        return (None, None, None) if gaps else None
    if mask is not None:
        ink = mask[y0:y1, x0:x1].copy()
        if int(ink.sum()) < fidelity.INK_MIN_PIXELS:
            ink = None
    else:
        sub = img[y0:y1, x0:x1]
        ink = fidelity.text_ink(sub, prefer=prefer)
        if ink is not None and drop is not None:
            ink = ink & ~drop[y0:y1, x0:x1]
            if int(ink.sum()) < fidelity.INK_MIN_PIXELS:
                ink = None
    bb = fidelity.ink_box(ink)
    out = [bb[0] + x0, bb[1] + y0, bb[2], bb[3]] if bb else None
    if not gaps:
        return out
    if not bb:
        return None, None, None
    core = ink[bb[1]:bb[1] + bb[3], bb[0]:bb[0] + bb[2]]
    return out, int((~core.any(axis=0)).sum()), round(float(core.sum() / core.size), 4)


def _stop_at_others(nb: list, box: list, others) -> list:
    """넓힌 상자 nb 를 다른 글자 상자(others — [x0, y0, x1, y1]) 앞에서 멈춘다 — 이웃 글자를 끌어오지 않게.
    원래 box 와 이미 겹친 상자(채움 상자끼리)는 가를 수 없어 무시한다."""
    x0, y0, x1, y1 = box
    n0, m0, n1, m1 = nb
    for o in others:
        if o[0] < x1 and o[2] > x0 and o[1] < y1 and o[3] > y0:
            continue
        if min(o[3], y1) - max(o[1], y0) > 0:          # 세로로 겹침 → 가로로 막음
            if o[0] >= x1:
                n1 = min(n1, o[0])
            if o[2] <= x0:
                n0 = max(n0, o[2])
        if min(o[2], x1) - max(o[0], x0) > 0:          # 가로로 겹침 → 세로로 막음
            if o[1] >= y1:
                m1 = min(m1, o[1])
            if o[3] <= y0:
                m0 = max(m0, o[3])
    return [int(n0), int(m0), int(n1), int(m1)]


def _cut_sides(img, box, bb, drop, prefer: str | None = None, mask=None) -> list[bool]:
    """렌더 획이 측정 상자 끝에 닿았거나 걸쳐 잘린 쪽 [왼, 위, 오른, 아래]. text_ink 는 좌우 끝에 닿은 덩어리를 지우므로(모서리 장식 빼기)
    상자 밖으로 걸쳐 나간 글자는 그냥 사라져 '닿음'으로 안 보인다 — 지우기 전 획으로 다시 본다.
    [실측 G 크기 끝 run] 크기 판이 배너 라벨을 가운데 중심으로 키우자 왼쪽 끝이 17 px 나가 '체' 가 측정에서 빠졌다(렌더 폭 225 — 실제 약 257)."""
    from gen import fidelity
    x0, y0, x1, y1 = box
    side = [bb[0] <= x0 + 1, bb[1] <= y0 + 1, bb[0] + bb[2] >= x1 - 1, bb[1] + bb[3] >= y1 - 1]
    if mask is not None:        # 핵심 획 마스크는 상자와 무관하게 그 글자 전체 — 상자 밖에 획이 남았는지로
        import numpy as np
        out = mask.copy()
        out[y0:y1, x0:x1] = False
        if out.any():
            ys, xs = np.nonzero(out)
            side = [side[0] or xs.min() < x0, side[1] or ys.min() < y0, side[2] or xs.max() >= x1, side[3] or ys.max() >= y1]
        return side
    raw = fidelity.text_ink(img[y0:y1, x0:x1], drop_edges=False, prefer=prefer)
    if raw is not None and drop is not None:
        raw = raw & ~drop[y0:y1, x0:x1]
    rb = fidelity.ink_box(raw) if raw is not None and raw.any() else None
    if rb:
        side[0] = side[0] or rb[0] <= 0
        side[2] = side[2] or rb[0] + rb[2] >= x1 - x0
    return side


def _notext_text_mask(reference_path, ref, texts) -> "np.ndarray | None":
    """1b 후속 H2 — 글자 없는 판(normalize 의 reference_notext_color · alpha, 컨셉에 정합됨)이 있으면 컨셉과 판이 다른 픽셀 = 글자 → 마스크(없으면 None).
    글자 상자(사방 높이 × 0.5 넓힘)마다 차의 오츠 문턱(≥ NOTEXT_INK_MIN) — codex 가 글자를 지우며 배지 원판 · 띠를 조금 다시 그린 차(수십)는 빼고 획(백 넘게)만.
    [실측 H2 조작 안내 R184042] 밝기로만 가르면 '공격' · '점프' 컨셉 측정이 옆 아이콘까지 175 × 61(정답 87 × 49), 'R' 이 날개 장식까지 198 × 71
    (정답 36 × 46) — 이 마스크로 둘 다 정답. 키 배지 'E' · 'T' 는 외곽선 · 베벨 차가 남아 여전히 크다(신뢰 범위가 거른다)."""
    import pathlib
    import numpy as np
    from PIL import Image
    p = pathlib.Path(reference_path)
    cp, ap = p.with_name("reference_notext_color.png"), p.with_name("reference_notext_alpha.png")
    if not (cp.is_file() and ap.is_file()):
        return None
    with Image.open(cp) as c, Image.open(ap) as a:
        nt = np.asarray(c.convert("RGB"), float) * (np.asarray(a.convert("L"), float) / 255.0)[..., None]
    if nt.shape != ref.shape:
        return None
    return _diff_text_mask(np.abs(ref - nt).max(axis=2), texts)


def _diff_text_mask(diff, texts):
    """차이 지도(채널 최대 0 ~ 255) → 글자 마스크 — 글자 상자(사방 높이 × 0.5 넓힘)마다 오츠 문턱(≥ NOTEXT_INK_MIN), NOTEXT_INK_GROW 넓힘."""
    import cv2
    import numpy as np
    from gen import cutout
    H, W = diff.shape
    mask = np.zeros((H, W), bool)
    for w in texts:
        x, y, bw, bh = (float(v) for v in w["bbox_intent"])
        e = 0.5 * bh
        x0, y0, x1, y1 = max(0, int(x - e)), max(0, int(y - e)), min(W, int(np.ceil(x + bw + e))), min(H, int(np.ceil(y + bh + e)))
        sub = diff[y0:y1, x0:x1]
        v = np.clip(sub[sub > NOTEXT_INK_FLOOR], 0, 255).astype(np.uint8)
        if v.size < 20:
            continue
        t, _ = cv2.threshold(v.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        mask[y0:y1, x0:x1] |= sub > max(NOTEXT_INK_MIN, float(t))
    return cutout._dilate(mask, NOTEXT_INK_GROW)


RENDER_TEXTFREE_MAX = 3.0   # 글자 상자 밖에서 렌더 ↔ 글자 없는 합성 평균 차가 이보다 크면(합성이 렌더를 못 따라감) 렌더 글자 마스크를 쓰지 않는다


def _render_text_mask(render_path, ren, spec: dict, texts) -> "np.ndarray | None":
    """1b 후속 H3 — 렌더 쪽 '글자 없는 판': 최종 텍스처를 실제 렌더 상자(같은 폴더 geometry.json) · 그리는 순서대로 검정 위에 다시 쌓은 합성(gen/backdrop —
    렌더와 1/255 안으로 같음, 글자 TextBlock 만 빠짐)과 렌더가 다른 픽셀 = 엔진 글자 → 마스크(못 만들면 None).
    [실측 H3 R20261117_112216] 렌더 획 측정(text_ink 밝기 가르기)이 두 톤 띠의 밝은 윗면까지 글자로 잡아 '돌진 공격' · '점프' 획 상자가 측정 상자 위 끝에 닿아
    크기 판이 건너뛰었고(36 — 컨셉은 '공격' 42 와 같은 크기), 키 배지 'E' 는 베벨까지 잡아 건너뛰곤 했다."""
    import json
    import pathlib
    import numpy as np
    from gen import backdrop
    rd = pathlib.Path(render_path).parent
    try:
        geo = json.loads((rd / "geometry.json").read_text(encoding="utf-8"))
        man = json.loads((rd / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    H, W = ren.shape[:2]
    boxes = (geo.get("geometry") or {}).get(f"{W}x{H}")
    if not boxes:
        return None
    textures = {a["asset_id"]: backdrop._load(rd / a["file"]) for a in man.get("assets", []) if a.get("file") and (rd / a["file"]).is_file()}
    black, _, _ = backdrop.compose(spec, boxes, textures, [W, H], (0, 0, 0))
    diff = np.abs(ren - black).max(axis=2)
    outside = ~backdrop.text_mask(spec, boxes, [W, H])
    if outside.any() and float(diff[outside].mean()) > RENDER_TEXTFREE_MAX:
        return None
    return _diff_text_mask(diff, texts)


TEXT_POLARITY_DL = 8.0      # 글자색 L* 가 상자 바탕(중앙값) L* 와 이만큼 넘게 다르면 그쪽(밝음 · 어두움)을 글자로 — 아니면 '적은 쪽' 규칙


def _text_polarity(w: dict, img, box) -> str | None:
    """글자 위젯의 글자색(그라데이션이면 위 · 아래 평균, 없으면 기본색) L* 와 측정 상자 바탕 L*(중앙값)로 글자 쪽 밝기 → 'bright' | 'dark' | None."""
    import numpy as np
    from core import color as color_mod
    f = w.get("font") if isinstance(w.get("font"), dict) else {}
    g = f.get("gradient") if isinstance(f.get("gradient"), dict) else None
    hexes = [g.get("top_color"), g.get("bottom_color")] if g else [f.get("color") or spec_mod.FONT_DEFAULT.get("color") or "#FFFFFFFF"]
    rgbs = []
    for h in hexes:
        h = str(h or "").lstrip("#")
        if len(h) >= 6:
            rgbs.append([int(h[i:i + 2], 16) for i in (0, 2, 4)])
    x0, y0, x1, y1 = (int(v) for v in box)
    if not rgbs or x1 - x0 < 4 or y1 - y0 < 4:
        return None
    tl = float(color_mod.srgb_to_lab(np.asarray(rgbs, float).mean(axis=0).reshape(1, 3))[0, 0])
    bl = float(np.median(color_mod.srgb_to_lab(np.asarray(img, float)[y0:y1, x0:x1, :3])[..., 0]))
    return "bright" if tl > bl + TEXT_POLARITY_DL else ("dark" if tl < bl - TEXT_POLARITY_DL else None)


def _concept_ink(ref, box, drop, others, limit, prefer: str | None = None, mask=None) -> tuple[list[int] | None, int]:
    """컨셉 글자 획 상자 — analyze 상자가 글자보다 짧으면(획이 잘림) 획 높이 × 0.5 · 1.0 · 1.5 만큼 넓혀 다시 재 원래 획 상자를 품고 더 큰 것을 받는다.
    넓히는 쪽에 다른 글자 위젯 상자가 있으면(세로로 겹치고 아직 안 닿은 것) 그 앞에서 멈춘다 — 이웃 글자를 끌어오지 않게.
    [실측 G 끝 run 3] 배너 라벨 상자 끝 1024 · 컨셉 '트' 는 1064 까지 → 잘린 조각은 text_ink 가 '끝에 닿은 덩어리'로 지워 획 상자 222 px(실제 275)."""
    c = _ink_abs(ref, box, drop=drop, prefer=prefer, mask=mask)
    grown = 0
    if c is None:
        return None, 0
    if mask is not None:        # 핵심 획 마스크는 이미 그 글자 전체 — 상자를 넓혀 다시 잴 필요 없음(상자 밖 획까지)
        import numpy as np
        ys, xs = np.nonzero(mask)
        return [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)], 0
    h0 = c[3]
    x0, y0, x1, y1 = box
    # 잘린 조각은 text_ink 가 '상자 끝에 닿은 덩어리'로 지우므로 조금씩 넓히면 자란 것이 안 보인다 → 넓이를 0.5 · 1.0 · 1.5 배로 차례로
    for k in (0.5, 1.0, 1.5):
        e = max(6, int(round(k * h0)))
        # 가로만 — 세로로 넓히면 위아래 줄('4.2' ↔ '2/4')을 잡는다 · 이웃 글자 상자 앞에서 멈춤
        nb = _stop_at_others([max(limit[0], x0 - e), y0, min(limit[2], x1 + e), y1], box, others)
        c2 = _ink_abs(ref, nb, drop=drop, prefer=prefer)
        if c2 is None or c2 == c:
            continue
        # 넓힌 결과가 원래 획 상자를 품을 때만(다른 줄 — 예: '2/4' 위의 '4.2' — 을 잡으면 원래 상자를 안 품는다)
        if not (c2[0] <= c[0] + 1 and c2[1] <= c[1] + 1 and c2[0] + c2[2] >= c[0] + c[2] - 1 and c2[1] + c2[3] >= c[1] + c[3] - 1):
            continue
        if c2[0] < c[0] - 1 or c2[1] < c[1] - 1 or c2[0] + c2[2] > c[0] + c[2] + 1 or c2[1] + c2[3] > c[1] + c[3] + 1:
            c = c2
            grown += 1
    return c, grown


def _touches(bb, box, px: int = 1) -> bool:
    return bb[0] <= box[0] + px or bb[1] <= box[1] + px or bb[0] + bb[2] >= box[2] - px or bb[1] + bb[3] >= box[3] - px


def _take_from_neighbour(w: dict, spec: dict, axis: int, d: float) -> dict | None:
    """가로 · 세로 상자 주축으로 d 옮길 때 이동 방향 이웃에서 |d| 를 가져온다 — 이웃이 Spacer 면 그 크기를, 아니면 이웃의 맞닿은 padding 을
    (이웃 주축 정렬이 가운데가 아닐 때) 줄인다. → {"neighbour", "from", …} · 이동 방향에 형제가 없으면 {"edge": True} · 여유가 없으면 None.
    [실측 G 굵기 끝 run] 채움 칸 배너 라벨을 자기 padding ±5 로 옮기자 칸을 넘어 옆 Spacer(BurstGap)와 겹침 → overlap 게이트."""
    sibs = [s for s in spec.get("widgets", []) if s.get("parent") == w.get("parent")]
    i = next((k for k, s in enumerate(sibs) if s["id"] == w["id"]), None)
    if i is None:
        return None
    j = i + 1 if d > 0 else i - 1
    if not 0 <= j < len(sibs):
        return {"edge": True}
    nb, a = sibs[j], abs(d)
    if nb.get("type") == "Spacer":
        size = list((nb.get("style") or {}).get("size") or spec_mod.STYLE_SCALAR_DEFAULTS.get("Spacer", {}).get("size") or [1, 1])
        if size[axis] - a < 0:
            return None
        size[axis] = round(size[axis] - a, 1)
        nb.setdefault("style", {})["size"] = size
        if nb.get("bbox_intent"):
            bb = [float(v) for v in nb["bbox_intent"]]
            if d > 0:
                bb[axis] += a          # 다음 이웃: 시작이 밀리고 끝은 그대로
            bb[axis + 2] = max(0.0, bb[axis + 2] - a)
            nb["bbox_intent"] = [round(v, 1) for v in bb]
        return {"neighbour": nb["id"], "from": "spacer size", "value": size}
    ns = nb.get("slot") if isinstance(nb.get("slot"), dict) else None
    if not ns:
        return None
    nd = spec_mod.SLOT_DEFAULTS.get(ns.get("kind"), {})
    if ns.get("h_align" if axis == 0 else "v_align", nd.get("h_align" if axis == 0 else "v_align")) == "center":
        return None
    p = list(ns.get("padding") or nd.get("padding") or [0, 0, 0, 0])
    k = axis if d > 0 else axis + 2                     # 다음 이웃은 앞 여백, 앞 이웃은 뒤 여백
    if p[k] - a < 0:
        return None
    p[k] = round(p[k] - a, 2)
    ns["padding"] = p
    return {"neighbour": nb["id"], "from": "padding", "value": p}


def _shift_text(w: dict, dx: float, dy: float, spec: dict | None = None, own_main: bool = False) -> dict | None:
    """글자를 (dx, dy) 옮긴다 — 슬롯이 차지하는 자리는 그대로(형제 · 행이 안 움직임): padding 슬롯은 양쪽 ±(왼 +k · 오른 −k, 위 · 아래도),
    캔버스는 점 앵커 축만 위치 +=. bbox_intent 도 같이. → 기록 또는 None(옮길 수 없는 슬롯).
    [소스] SlateCore/Public/Layout/LayoutUtils.h:663-664 — 가운데 정렬 오프셋 = (할당 − 자식)/2 + 앞 여백 − 뒤 여백이라 양쪽 ±k 는 2k 움직인다
    (왼 · 위 · 채움 = 앞 여백, 오른 · 아래 = −뒤 여백 → k). [실측 G 끝 run 2] 세로 가운데 '3' 을 ±3.5 로 옮기자 7 px 움직였다 → 가운데 축은 k = d/2.
    가로 · 세로 상자의 주축은 양쪽 ± 가 칸을 넘어 형제와 겹치므로 이동 방향 이웃에서 공간을 가져온다(_take_from_neighbour — 자기 반대쪽 여백에 더함,
    이웃이 없으면 양쪽 ±, 이웃에 여유가 없거나 주축 가운데 정렬이면 그 축은 안 옮김). own_main = 주축도 자기 양쪽 ± — 호출자가 형제 겹침이 없다고
    예측했을 때(text_fit 위치 판): 양쪽 ±k 는 auto · 채움 칸 모두 칸 자리를 그대로 두고 위젯만 d 옮긴다 — 겹침은 위젯이 칸 밖으로 나갈 때만 생긴다."""
    slot = w.get("slot") if isinstance(w.get("slot"), dict) else None
    if not slot:
        return None
    kind = slot.get("kind")
    if kind in PADDED_SLOTS:
        d = spec_mod.SLOT_DEFAULTS.get(kind, {})
        center = [slot.get("h_align", d.get("h_align")) == "center", slot.get("v_align", d.get("v_align")) == "center"]
        p = list(slot.get("padding") or d.get("padding") or [0, 0, 0, 0])
        main = {"horizontal_box": 0, "vertical_box": 1}.get(kind)
        out: dict = {}
        moves = [dx, dy]
        for axis, dd in ((0, dx), (1, dy)):
            if not dd:
                continue
            if axis == main and spec is not None and not own_main:
                took = None if center[axis] else _take_from_neighbour(w, spec, axis, dd)
                if took is None:
                    moves[axis] = 0.0
                    out.setdefault("axis_skipped", []).append(f"{'xy'[axis]}: no room in the neighbour along the box (or centre-aligned main axis)")
                    continue
                if not took.get("edge"):
                    if dd > 0:
                        p[axis] = round(p[axis] + dd, 2)            # 다음 이웃이 준 만큼 앞 여백
                    else:
                        p[axis + 2] = round(p[axis + 2] - dd, 2)    # 앞 이웃이 준 만큼 뒤 여백
                    out["neighbour"] = took
                    continue
            k = dd / 2.0 if center[axis] else dd
            p[axis], p[axis + 2] = round(p[axis] + k, 2), round(p[axis + 2] - k, 2)
        dx, dy = moves
        if not dx and not dy:
            return {"skipped": out.get("axis_skipped")} if out.get("axis_skipped") else None
        slot["padding"] = p
        out["padding"] = p
    elif kind == "canvas":
        a = slot.get("anchors") or [0, 0, 0, 0]
        dx = dx if a[0] == a[2] else 0.0
        dy = dy if a[1] == a[3] else 0.0
        if not dx and not dy:
            return None
        pos = slot.get("position") or [0, 0]
        slot["position"] = [round(pos[0] + dx, 1), round(pos[1] + dy, 1)]
        out = {"position": slot["position"]}
    else:
        return None
    x, y, bw, bh = (float(v) for v in w["bbox_intent"])
    w["bbox_intent"] = [round(x + dx, 1), round(y + dy, 1), bw, bh]
    return {**out, "shift": [round(dx, 1), round(dy, 1)]}


def _overlap_rule(spec: dict) -> tuple[float, list] | None:
    """overlap 게이트와 같은 규칙(spec.profile 의 gates.overlap_max_ratio · stacking_parents) — 프로필이 없으면 None."""
    if not spec.get("profile"):
        return None
    try:
        prof = config.load_profile(spec["profile"])
        return float(prof["gates"]["overlap_max_ratio"]), list(prof.get("stacking_parents") or [])
    except Exception:  # noqa: BLE001 — 예측을 못 하면 build 결과(게이트)에 맡긴다
        return None


def _predicted_violations(spec: dict, rendered: dict[str, list], followed: list[dict], rule) -> set[frozenset]:
    """직전 통과 렌더 상자(rendered)에 follow_text_boxes 의 예상 변화(가운데 중심 성장 grow · 위로 옮김 shift_up)를 넣은 geometry 에서
    overlap 게이트와 같은 규칙으로 겹치는 형제 쌍."""
    return _violations(_predicted_rows(spec, rendered, followed), spec, rule)


def _violations(rows: list[dict], spec: dict, rule) -> set[frozenset]:
    from core import geometry as geo
    return {frozenset((v["a"], v["b"])) for v in geo.overlaps(rows, spec, rule[0], rule[1])["violations"]}


def _predicted_rows(spec: dict, rendered: dict[str, list], followed: list[dict]) -> list[dict]:
    fol = {r["widget"]: r for r in followed}
    rows = []
    for w in spec.get("widgets", []):
        b = rendered.get(w["id"])
        if not b:
            continue
        x, y, bw, bh = (float(v) for v in b)
        r = fol.get(w["id"]) or {}
        dw, dh = r.get("grow") or (0.0, 0.0)
        x, bw, y, bh = x - dw / 2, bw + dw, y - dh / 2, bh + dh
        su = r.get("shift_up")
        if su:                        # padding 슬롯은 위쪽만 올라가 높이 +d, 캔버스는 상자째 위로
            y -= su["by"]
            if "padding_top" in su:
                bh += su["by"]
        rows.append({"id": w["id"], "type": w.get("type"), "parent": w.get("parent"), "x": x, "y": y, "w": bw, "h": bh})
    return rows


def _fit_sizes(before: dict, after: dict, cfg: dict, rendered: dict[str, list] | None, sized: dict[str, dict]) -> tuple[dict, list[dict]]:
    """크기 판 — 크기를 바꾼 글자(sized: id → 기록)의 상자를 follow_text_boxes 로 가운데 중심으로 키우고, build 전에 형제 겹침을 예측한다:
    직전 통과 렌더 geometry 에 커질 상자를 넣어 overlap 게이트 규칙으로 재 새로 겹치는 쌍이 있으면 그 글자 크기를 원래 쪽으로 1 씩 줄여 다시
    (원래 크기까지 가면 그대로 두고 size_capped 기록). 줄 높이 표가 없는 폰트는 상자를 못 따라가니 크기를 되돌린다.
    [실측 G 굵기 끝 run] 체인 패널이 VerticalBox 인 run 에서 외형 라운드가 '4.2' 를 52 → 65 · '2/4' 를 22 → 25 로 키우자 위아래 글자와 줄 상자가
    겹쳐(0.29 · 0.48) 라운드가 통째로 버려졌다. → (새 spec, follow 기록)."""
    import copy
    rule = _overlap_rule(after) if rendered else None
    base = _predicted_violations(before, rendered, [], rule) if rule else set()
    old = {w["id"]: w for w in before.get("widgets", [])}
    for wid, rec in sized.items():
        rec["overlap_check"] = "predicted from the last passing render" if rule else "skipped — no render geometry or profile"
    for _ in range(200):
        trial = copy.deepcopy(after)
        followed = follow_text_boxes(before, trial, cfg, rendered)
        fol = {r["widget"]: r for r in followed}
        back = {wid: "no line-height table for the font — the box cannot follow" for wid in sized
                if str((fol.get(wid) or {}).get("skipped", "")).startswith("no line-height")}
        aw = {w["id"]: w for w in after.get("widgets", [])}
        step = set()
        if not back and rule:
            grown = {wid for wid in sized if float(aw[wid]["font"]["size"]) > float((old[wid].get("font") or {}).get("size") or 24)}
            for pair in _predicted_violations(trial, rendered, followed, rule) - base:
                step |= pair & grown                  # 줄인 글자는 겹침을 만들지 않는다 — 키운 쪽만 되돌린다
        if not back and not step:
            return trial, followed
        for wid in list(sized):
            if wid not in back and wid not in step:
                continue
            f, s0 = aw[wid]["font"], float((old[wid].get("font") or {}).get("size") or 24)
            cur = float(f["size"])
            nxt = s0 if wid in back else cur + (1 if cur < s0 else -1)
            if nxt == s0:
                orig = (old[wid].get("font") or {}).get("size")
                if orig is None:
                    f.pop("size", None)
                else:
                    f["size"] = orig
                sized[wid]["size_capped"] = back.get(wid) or f"growing beyond {s0:g} overlaps a sibling (predicted with the overlap gate rule) — size left as it was"
                sized[wid].pop("size", None)
                del sized[wid]
            else:
                f["size"] = int(nxt)
                sized[wid]["size"][1] = int(nxt)
                sized[wid]["size_capped"] = f"capped at {int(nxt)} — a larger size overlaps a sibling (predicted with the overlap gate rule)"
    return after, follow_text_boxes(before, after, cfg, rendered)   # pragma: no cover — 크기 차이는 많아야 수십 단계


def text_fit(spec: dict, reference_path, render_path, cfg: dict, rendered: dict[str, list] | None = None,
             mode: str = "place", only: set | None = None) -> tuple[dict, list[dict]]:
    """1b 후속 G — 글자 크기 · 굵기 · 위치 결정적 맞춤(외형 라운드 뒤, LLM 없음). 마지막 통과 렌더에서 글자마다 컨셉 ↔ 렌더 획 상자를 같은 측정 상자
    (컨셉 획 상자 + 여유 — 넓은 위젯 상자에 패널 선 · 이웃 글자가 끼지 않게, 그 글자의 영역 안)에서 재고, 두 판으로 나눠 고친다
    (run_pipeline._text_fit_round 가 판마다 build → verify — 크기를 바꾼 글자는 그 판에서 위치 · 자간을 안 건드린다):
      mode "size"(크기 판) — 높이 비가 TEXT_FIT_TRUST_H 안이고 폭 비가 높이 비와 TEXT_FIT_TRUST_WH 안에서 맞을 때만(아니면 잘리거나 섞인 측정으로 봄):
        · 크기 — |1 − 높이 비| ≥ TEXT_FIT_SIZE_TOL 이면 새 크기 = round(크기 ÷ 높이 비), 상자는 follow_text_boxes(가운데 중심 성장 · 형제 자리 유지),
          build 전 형제 겹침 예측으로 상한(_fit_sizes).
        · 굵기 — 획 밀도(획 픽셀 / 획 상자 넓이) 비가 regular ↔ bold 경계(TEXT_FIT_WEIGHT_STEP)를 넘으면 바꾼다.
      mode "place"(위치 판) — 높이 비가 TEXT_FIT_H 안일 때만:
        ① 글자 2 개 이상 · 폭 비가 TEXT_FIT_W_TOL 넘게 다르면 자간(글자 사이 px = (컨셉 틈 열 − 렌더 틈 열) / (글자 수 − 1) —
           틈 열 = 획 상자 안 세로 투영이 빈 열, 글자 모양이 넓어서 생긴 폭 차이는 자간으로 메우지 않는다)
           — 글자가 길이를 정하는 축은 follow_text_boxes 가 가운데 중심으로 키운다(자리 유지),
        ② 중심 차(자간 뒤 예상)가 TEXT_FIT_MIN_PX 이상이면 _shift_text 로 옮긴다.
    측정이 이상하면(획이 측정 상자 끝에 닿음 · 높이 비 범위 밖 · 차가 상한 넘음) 그 글자는 건너뛴다(F 교훈 — 틀린 지표로 고치지 않기).
    [실측 F run 4] 배너 라벨: 왼쪽 끝은 같고(789) 폭만 좁다(254 vs 275 — 높이 비 1.02) → 중심 dx −10.5 의 몫은 자간, dy −4.5 는 세로 자리.
    → (새 spec — 입력은 그대로, 기록)."""
    import copy
    import math
    import numpy as np
    from PIL import Image
    from gen import fidelity
    if mode not in TEXT_FIT_MODES:
        raise ValueError(f"text_fit mode {mode!r} — one of {TEXT_FIT_MODES}")
    after = copy.deepcopy(spec)
    ref = np.asarray(Image.open(reference_path).convert("RGB")).astype(float)
    ren = np.asarray(Image.open(render_path).convert("RGB")).astype(float)
    if ref.shape != ren.shape:
        return after, [{"skipped": f"reference {list(ref.shape[:2])} and render {list(ren.shape[:2])} differ"}]
    H, W = ref.shape[:2]
    by_id = {w["id"]: w for w in after.get("widgets", [])}
    root = after.get("root")
    drop_c, drop_r = _frame_drop(ref, after), _frame_drop(ren, after)
    typefaces = {str(t).lower() for t in ((cfg.get("fonts") or {}).get("typefaces") or ["Regular", "Bold"])}
    try:
        from core import config as config_mod
        font_roles = config_mod.font_roles(cfg)
    except Exception:  # noqa: BLE001
        font_roles = {}

    def region_box(w):
        cur = w
        while cur.get("parent") not in (root, None) and cur.get("parent") in by_id:
            cur = by_id[cur["parent"]]
        return cur.get("bbox_intent") if cur.get("parent") == root and cur is not w else None
    def line_box(w):
        bb = list(w["bbox_intent"])
        g = float(((w.get("font") or {}).get("glow") or {}).get("size") or 0)
        if g:   # 빛 글자는 analyze 가 상자를 사방 빛 크기만큼 넓혔다(region_report 와 같게 원래 줄 상자로)
            bb = [bb[0] + g, bb[1] + g, bb[2] - 2 * g, bb[3] - 2 * g]
        return list(fidelity._clip_box(bb, W, H))
    texts = [w for w in after.get("widgets", []) if w.get("type") == "TextBlock" and w.get("bbox_intent")]
    boxes = {w["id"]: line_box(w) for w in texts}
    # 1b 후속 J-c — 진단(gen/diagnose)과 같은 획: 컨셉 = 글자 없는 텍스처 합성 · 판과 다른 픽셀 중 핵심 획(빛 번짐 제외), 렌더 = 렌더 ↔ 글자 없는 합성.
    # [실측 J-b 기준선 154442] 밝기 · 판 차이 측정이 빛 번짐까지 획으로 잡아 보통 → 굵게 · 40 → 46 으로 키웠고 '회피' 는 덜 잡아 38 → 31
    import pathlib
    from gen import diagnose
    gm = None
    try:
        gm = diagnose.run_text_masks(pathlib.Path(render_path).parent, spec, render_path)
    except Exception:  # noqa: BLE001 — 마스크가 없으면 예전 밝기 측정
        gm = None
    nt_mask = _notext_text_mask(reference_path, ref, texts) if gm is None else None
    if nt_mask is not None:     # 컨셉 획 = 글자 없는 판과 다른 픽셀만(밝기 갈라 잡힌 배지 · 아이콘 · 장식은 뺌)
        drop_c = (drop_c if drop_c is not None else np.zeros((H, W), bool)) | ~nt_mask
    # 렌더 쪽 글자 없는 합성 차(띠 밝은 면 · 배지 베벨은 뺌) — 밝기 측정을 못 믿을 때만 대신 쓴다(아래). 늘 쓰면 획 굵기 기준이 달라 '어빌리티' 를 굵게로
    # 오판하고 '회피' 획을 덜 잡았다 [실측 H3 R20261117_113744]
    rt_mask = _render_text_mask(render_path, ren, after, texts) if nt_mask is not None else None
    drop_rt = ((drop_r if drop_r is not None else np.zeros((H, W), bool)) | ~rt_mask) if rt_mask is not None else None
    recs, measured = [], {}
    for w in texts:
        if only is not None and w["id"] not in only:
            continue                # 1b 후속 J — 판을 글자별로 다시 짤 때(run_pipeline._text_fit_pass) 고를 글자만
        rec: dict = {"widget": w["id"]}
        g = (gm or {}).get(w["id"])
        mc = g["concept"] if g is not None and g["concept"].sum() >= 20 else None
        mr = g["render"] if g is not None and g["render"].sum() >= 20 and mc is not None else None
        if mc is None:
            mr = None
        if mc is not None:
            rec["concept_mask"] = "core glyph strokes (gen/diagnose — text-free texture composite · text-free concept, glow excluded)"
        elif nt_mask is not None:
            rec["concept_mask"] = "text-free concept difference"
        recs.append(rec)
        cct = g.get("concept_contrast") if g is not None else None
        if cct is not None and cct < diagnose.CONCEPT_CONTRAST_MIN:
            # 1b 후속 L 다음 — 진단 E6 unmeasured 와 같은 판정: 컨셉 '획'이 둘레와 구별 안 되면 바탕을 글자로 잰 것 — 그 측정으로 색 · 크기 · 외곽선을
            # 바꾸지 않는다 [실측 L 다음 파티 R20261118_130201 'Lv 100' — 번진 텍스처 상자의 어두운 틈을 '100' 으로 재 #EDF2F4 · 40 · 빛 → 검정 · 52 · 외곽선]
            rec.update(concept_contrast=round(float(cct), 1),
                       skipped=f"concept glyph contrast {cct:.1f} < {diagnose.CONCEPT_CONTRAST_MIN:g} — the concept glyph was not found "
                               "(background measured as glyph, same rule as the diagnosis E6 unmeasured)")
            continue
        rb = region_box(w)
        limit = [0, 0, W, H] if not rb else [max(0, int(rb[0])), max(0, int(rb[1])), min(W, int(math.ceil(rb[0] + rb[2]))), min(H, int(math.ceil(rb[1] + rb[3])))]
        if mc is not None:
            limit = [0, 0, W, H]        # 핵심 획 마스크는 이미 그 글자만 — 영역 상자로 자르지 않는다(영역 밖으로 나간 획도 잰다)
        pol = _text_polarity(w, ref, boxes[w["id"]])    # 글자 쪽 밝기 — 컨셉 · 렌더를 같은 쪽으로 잰다
        if pol:
            rec["ink_side"] = pol
        c0, grown = _concept_ink(ref, boxes[w["id"]], drop_c, [b for k, b in boxes.items() if k != w["id"]], limit, prefer=pol, mask=mc)
        if grown:
            rec["concept_box_grown"] = grown
        if c0 is None:
            rec["skipped"] = "no glyph pixels in the concept box"
            continue
        m = max(6, int(round(TEXT_FIT_MARGIN * c0[3])))
        M = [max(limit[0], c0[0] - m), max(limit[1], c0[1] - m), min(limit[2], c0[0] + c0[2] + m), min(limit[3], c0[1] + c0[3] + m)]
        if mr is not None:      # 마스크 측정 — 렌더 획 전체가 들게(어긋난 글자도 잘리지 않게)
            ys_, xs_ = np.nonzero(mr)
            M = [max(0, min(M[0], int(xs_.min()) - m)), max(0, min(M[1], int(ys_.min()) - m)), min(W, max(M[2], int(xs_.max()) + 1 + m)),
                 min(H, max(M[3], int(ys_.max()) + 1 + m))]
        lim_box = limit
        if mc is not None and mr is not None:
            # 1b 후속 J-c — 진단(gen/diagnose._stats)과 같은 정의: 마스크 전체 · 1 ~ 99 백분위 획 상자 · 상자 안 밀도 · 빈 열 — 맞춤과 진단이 같은 숫자를 본다
            # [실측 J R20261117_181500 '2/4' — 측정 상자로 자른 맞춤 1.03 ↔ 진단 1.08 ~ 1.12 로 엇갈려 크기 결함이 남았다]
            sc_, sr_ = diagnose._stats(mc, ref), diagnose._stats(mr, ren)
            (c2, cg, cd) = (sc_["box"], sc_["gap_cols"], sc_["density"]) if sc_ else (None, None, None)
            (r2, rg, rd) = (sr_["box"], sr_["gap_cols"], sr_["density"]) if sr_ else (None, None, None)
        else:
            (c2, cg, cd), (r2, rg, rd) = (_ink_abs(ref, M, gaps=True, drop=drop_c, prefer=pol, mask=mc),
                                          _ink_abs(ren, M, gaps=True, drop=drop_r, prefer=pol, mask=mr))
        # 렌더 획이 측정 상자의 한쪽 끝에 닿거나 걸쳐 잘리면(_cut_sides) 그쪽만 여유만큼 넓혀 다시(최대 TEXT_FIT_WIDEN 번, 다른 글자 상자 앞까지)
        # — 컨셉 획 상자가 그대로일 때만 받는다
        # [실측 G 끝 run 3] 배너 라벨이 컨셉보다 18 px 왼쪽(여유 15 px)이라 닿아서 건너뛰었다
        others = [b for k, b in boxes.items() if k != w["id"]]
        for _ in range(0 if (mc is not None and mr is not None) else TEXT_FIT_WIDEN):     # 마스크 측정은 넓힐 필요 없음
            if c2 is None or r2 is None or _touches(c2, M):
                break
            side = _cut_sides(ren, M, r2, drop_r, pol, mask=mr)
            if not any(side):
                break
            M2 = [max(lim_box[0], M[0] - m) if side[0] else M[0], max(lim_box[1], M[1] - m) if side[1] else M[1],
                  min(lim_box[2], M[2] + m) if side[2] else M[2], min(lim_box[3], M[3] + m) if side[3] else M[3]]
            if mr is None:
                M2 = _stop_at_others(M2, M, others)
            if M2 == M:
                break
            (c3, cg3, cd3), (r3, rg3, rd3) = (_ink_abs(ref, M2, gaps=True, drop=drop_c, prefer=pol, mask=mc),
                                              _ink_abs(ren, M2, gaps=True, drop=drop_r, prefer=pol, mask=mr))
            if c3 != c2:
                break                       # 넓힌 자리에 컨셉의 다른 획(이웃 글자 · 선)이 들어옴 — 그만
            M, c2, cg, cd, r2, rg, rd = M2, c3, cg3, cd3, r3, rg3, rd3
            rec["widened"] = rec.get("widened", 0) + 1
        rec["measure_box"] = [M[0], M[1], M[2] - M[0], M[3] - M[1]]
        masked = False
        if drop_rt is not None and mr is None and c2 is not None and not _touches(c2, M):
            bad = r2 is None or _touches(r2, M)
            if not bad:
                hr, wr = r2[3] / c2[3], r2[2] / c2[2]
                lo, hi = TEXT_FIT_TRUST_H if mode == "size" else TEXT_FIT_H
                bad = not lo <= hr <= hi or abs(wr / max(1e-6, hr) - 1.0) > TEXT_FIT_TRUST_WH
            if bad:     # 밝기 측정을 못 믿음 — 렌더 글자 마스크로 다시(굵기는 기준이 달라 판정 안 함)
                r3, rg3, rd3 = _ink_abs(ren, M, gaps=True, drop=drop_rt, prefer=pol)
                if r3 is not None and not _touches(r3, M):
                    r2, rg, rd, masked = r3, rg3, rd3, True
                    rec["render_mask"] = "text-free composite difference (brightness measurement not trusted)"
        if c2 is None or r2 is None:
            rec["skipped"] = "no glyph pixels in the " + ("concept" if c2 is None else "render") + " measuring box"
            continue
        rec.update(concept_ink=c2, render_ink=r2, h_ratio=round(r2[3] / c2[3], 3), w_ratio=round(r2[2] / c2[2], 3), gap_cols=[cg, rg],
                   ink_density=[cd, rd])
        if _touches(c2, M) or _touches(r2, M):
            rec["skipped"] = "glyphs reach the measuring box edge (a neighbour, a frame line or the region edge is inside) — not trusted"
            continue
        f = w.get("font") if isinstance(w.get("font"), dict) else None
        if mode == "size" and f is not None and mc is not None and mr is not None:
            col = _fit_color(f, ref, ren, mc, mr)       # 1b 후속 J-c — 글자색 · 그라데이션도 진단과 같은 핵심 획에서(결정적)
            if col:
                rec["color"] = col
            ol = _fit_outline(f, ref, ren, g)           # 외곽선도 컨셉에서 잰 것만(J-c — LLM 외곽선은 analyze 에서 걷었다)
            if ol:
                rec["outline" if "new" in ol else "outline_skipped"] = ol
            gl = _fit_glow(f, ref, ren, g, font_roles)  # 1b 후속 J — 빛 크기도 같은 측정(핵심 획 밖 밝은 비율)으로
            if gl:
                rec["glow"] = gl
            sd = _fit_shadow(f, ref, ren, g)            # 1b 후속 L-3c — 그림자 유무 · 오프셋 · 색도 진단과 같은 측정(diagnose.shadow_measure)
            if sd:
                rec["shadow"] = sd
        if mode == "size":
            wh = rec["w_ratio"] / max(1e-6, rec["h_ratio"])
            if not diagnose.measure_trusted(rec["h_ratio"], rec["w_ratio"]):     # 1b 후속 K — 진단과 같은 신뢰 규칙(폭 · 높이가 맞으면 1.6 까지)
                rec["skipped"] = (f"glyph height ratio {rec['h_ratio']} (width/height {wh:.2f}) is outside {list(TEXT_FIT_TRUST_H)} or the width disagrees by more than "
                                  f"{TEXT_FIT_TRUST_WH:g} — the measurement is not trusted for size or weight (clipped or merged glyphs)")
                continue
            # 굵기 — 컨셉 ↔ 렌더 획 밀도 비가 regular ↔ bold 경계(두 굵기 밀도 비의 기하 중간)를 넘으면 바꾼다. 밀도는 크기와 거의 무관하다
            # [실측 G 끝 run 4] '오의 불가'(Pretendard Bold) 비 0.706 — 컨셉 0.254 ≈ Regular 0.237, 다른 글자 1.00 ~ 1.22 (F run 5 는 높이 비 0.838 · 비 0.72)
            from gen import diagnose as _dg
            wtab = _dg.weight_table(cfg, f.get("family")) if f is not None else None
            cur0 = (f.get("weight") or spec_mod.FONT_DEFAULT["weight"]) if f is not None else None
            resizing = abs(1.0 - rec["h_ratio"]) >= TEXT_FIT_SIZE_TOL
            if resizing and wtab and cur0 in (wtab or {}):
                rec["weight_deferred"] = "the size changes in this pass — stroke density depends on the size (small text renders denser), weight is judged next pass"
            elif f is not None and cd and rd and not masked and wtab and cur0 in wtab:
                # 1b 후속 K E9 — 가진 굵기(fonts.weight_density) 중 컨셉 밀도에 가장 가까운 것(로그 거리, 진단과 같은 규칙 · 여유)
                cur, ratio = cur0, round(cd / rd, 3)
                best, w_after = _dg.nearest_weight(rd / cd, cur, wtab)
                new = best if best != cur and abs(math.log(w_after)) + _dg.DEFAULTS["weight_margin"] < abs(math.log(rd / cd)) else None
                if new:
                    f["weight"] = new
                    rec["weight"] = [cur, new, ratio]
            elif f is not None and cd and rd and not masked and {"regular", "bold"} <= typefaces:
                cur, ratio = f.get("weight") or spec_mod.FONT_DEFAULT["weight"], round(cd / rd, 3)
                new = "regular" if cur == "bold" and ratio < 1.0 / TEXT_FIT_WEIGHT_STEP else ("bold" if cur == "regular" and ratio > TEXT_FIT_WEIGHT_STEP else None)
                if new:
                    f["weight"] = new
                    rec["weight"] = [cur, new, ratio]
            # 크기 — 글자 높이는 크기에 비례한다(같은 폰트): 새 크기 = round(크기 ÷ 높이 비), 빛 · 외곽선은 그대로
            # [실측 G 굵기 끝 run] 외형 라운드가 버려지자 analyze 크기가 남음 — 배너 0.90 · '3' 0.92 · '4.2' 0.80 · '오의 불가' 0.84
            if f is not None and abs(1.0 - rec["h_ratio"]) >= TEXT_FIT_SIZE_TOL:
                s0 = float(f.get("size") or spec_mod.FONT_DEFAULT.get("size", 24))
                s1 = int(round(s0 / rec["h_ratio"]))
                if s1 != s0 and s1 > 0:
                    f["size"] = s1
                    rec["size"] = [int(s0) if s0 == int(s0) else s0, s1, rec["h_ratio"]]
            continue
        if not TEXT_FIT_H[0] <= rec["h_ratio"] <= TEXT_FIT_H[1]:
            rec["skipped"] = f"glyph height ratio {rec['h_ratio']} is outside {list(TEXT_FIT_H)} — the size is the size pass's job"
            continue
        if not diagnose.measure_trusted(rec["h_ratio"], rec["w_ratio"]):
            # 1b 후속 K — 폭 · 높이가 안 맞는 측정(잘리거나 섞인 획)의 가운데로 옮기지 않는다 [실측 K R20261118_010950 단색 '2/4' — 폭 비 0.45 측정으로
            # (−5.5, +8.5) 옮겨 패널 아래 금선과 겹침]
            rec["skipped"] = f"width ratio {rec['w_ratio']} disagrees with height ratio {rec['h_ratio']} — the measurement is not trusted for moving"
            continue
        measured[w["id"]] = (rec, c2, r2)
    if mode == "size":
        after, followed = _fit_sizes(spec, after, cfg, rendered, {r["widget"]: r for r in recs if r.get("size")})
        if followed:
            recs.append({"text_boxes_followed": followed})
        return after, recs
    before = copy.deepcopy(after)
    for wid, (rec, c2, r2) in measured.items():
        w = by_id[wid]
        f = w.get("font") if isinstance(w.get("font"), dict) else None
        rec["dw"] = 0
        t = w.get("text") or {}
        n = len(t.get("value") or t.get("sample") or "") - 1
        if f is None or n < 1 or abs(rec["w_ratio"] - 1) < TEXT_FIT_W_TOL:
            continue
        size, ls0 = float(f.get("size") or 24), float(f.get("letter_spacing") or 0)
        px0 = int(size * ls0 / 1000.0)
        # 폭 차이 전체가 아니라 글자 사이 틈(세로 투영의 빈 열) 차이만 — 컨셉 글꼴이 더 굵고 넓어서 생긴 차이를 자간으로 메우면 글자가 벌어진다
        # [실측 G 끝 run 1] 폭 차이로 '4.2' 자간 0 → 110 — '4 . 2' 로 벌어짐(컨셉은 숫자가 넓고 틈은 비슷)
        cg, rg = rec["gap_cols"]
        step = int(round((cg - rg) / n))
        px1 = max(0, px0 + step)
        if not step or abs(step) > 0.25 * size or px1 == px0:
            continue
        ls1 = math.ceil(px1 * 1000.0 / size) if px1 > 0 else 0
        while ls1 and int(size * ls1 / 1000.0) < px1:
            ls1 += 1
        if ls1:
            f["letter_spacing"] = ls1
        else:
            f.pop("letter_spacing", None)
        rec["letter_spacing"] = [ls0, ls1]
        rec["dw"] = n * (int(size * ls1 / 1000.0) - px0)
    followed = follow_text_boxes(before, after, cfg, rendered)
    # 형제 겹침 예측(크기 판과 같은 규칙) — 직전 통과 렌더 상자 + 자간 성장. 옮긴 뒤 새로 겹치는 쌍이 없으면 주축도 자기 padding 으로 옮긴다
    # [실측 G 크기 끝 run] 크기 판 뒤 '3' 의 앞 여백이 −4 라 배너 라벨(채움 칸 · 왼쪽 정렬, 칸 안 오른쪽에 약 50 px 빈자리)을 이웃 규칙으로 못 옮겼다
    rule = _overlap_rule(after) if rendered else None
    rows = _predicted_rows(after, rendered, followed) if rule else []
    base = _violations(rows, after, rule) if rule else set()
    for wid, (rec, c2, r2) in measured.items():
        w = by_id[wid]
        fx, _ = _axis_follow(w)
        dw = rec.pop("dw", 0)
        grow_c = 0.0 if fx is not None else {"left": dw / 2.0, "right": -dw / 2.0}.get(w.get("justification", "left"), 0.0)
        dx = round(c2[0] + c2[2] / 2.0 - (r2[0] + r2[2] / 2.0 + grow_c), 1)
        dy = round(c2[1] + c2[3] / 2.0 - (r2[1] + r2[3] / 2.0), 1)
        just = w.get("justification", "left")
        # 끝 맞춤 · 가운데 맞춤 판정은 이 판의 자간을 넣은 뒤 예상 폭으로(진단 E6 이 받은 뒤 렌더를 재는 것과 같은 상태) — 자간 전 폭으로 끝 맞춤을 고르고
        # 진단은 자간 뒤 폭(모양 차 8 % 안)으로 가운데를 봐 6.5 px 어긋남이 됐다 [실측 L-2 R20261118_171644 '체인 버스트' 0.90 → 0.937]
        wh_after = (r2[2] + dw) / max(1e-6, c2[2]) / max(1e-6, rec["h_ratio"])
        rec["w_over_h_after"] = round(wh_after, 3)
        if fx is None and just in ("left", "right") and abs(wh_after - 1.0) > 0.08:
            # 1b 후속 K — 글자 모양 폭이 달라(글꼴 결 — 근사) 가운데를 맞추면 정렬 끝이 어긋난다: 정렬 끝(왼 · 오른쪽)을 맞춘다(진단 E6 과 같은 규칙,
            # 폭이 같은 글자는 예전처럼 가운데) [실측 J 남은 일 R20261117_215853 HP 현재치 — 오른쪽 정렬 · 렌더 20 % 넓음, 가운데 맞춤 뒤 끝 9 px 어긋남]
            dx = round((c2[0] - r2[0]) if just == "left" else ((c2[0] + c2[2]) - (r2[0] + r2[2])), 1)
            rec["anchor"] = f"{just} edge (glyph widths differ — w/h {wh_after:.2f} after the spacing)"
        lim = max(8.0, min(TEXT_FIT_MAX_PX, TEXT_FIT_MAX_H * c2[3]))
        rec["center_d"] = [dx, dy]
        sx = dx if TEXT_FIT_MIN_PX <= abs(dx) <= lim else 0.0
        sy = dy if TEXT_FIT_MIN_PX <= abs(dy) <= lim else 0.0
        if abs(dx) > lim or abs(dy) > lim:
            rec["too_far"] = f"centre difference {[dx, dy]} exceeds {lim:g} px on an axis — that axis is left alone"
        if sx or sy:
            own = False
            row = next((r for r in rows if r["id"] == wid), None)
            if rule and row is not None:
                # 새 겹침이 예측되지 않는 이동만 — 전체 → 한 축씩. 다 겹치면 상자 주축은 이웃 규칙(이웃에서 공간을 가져와 안 겹침)만, 나머지는 안 옮김
                # [실측 G2 파티 HUD] 캔버스 직계 '0 %' 를 위로 3.5 옮기자 옆 영역 HpGaugeArea 와 겹쳐(0.086) 위치 판 전체가 버려졌다
                def clean(dx, dy):
                    trial = [dict(r, x=r["x"] + dx, y=r["y"] + dy) if r is row else r for r in rows]
                    return not (_violations(trial, after, rule) - base)
                pick = next(((dx, dy) for dx, dy in ((sx, sy), (sx, 0.0), (0.0, sy)) if (dx or dy) and clean(dx, dy)), None)
                main = {"horizontal_box": 0, "vertical_box": 1}.get((w.get("slot") or {}).get("kind"))
                if pick is not None:
                    own = True
                    if pick != (sx, sy):
                        rec["axis_dropped"] = f"moving {['x', 'y'][0 if pick[0] == 0 else 1]} too would overlap a sibling (predicted) — that axis is left alone"
                    sx, sy = pick
                elif main is not None and (sx if main == 0 else sy):
                    sx, sy = (sx, 0.0) if main == 0 else (0.0, sy)
                    rec["axis_dropped"] = "every own-slot move overlaps a sibling (predicted) — only the box axis, with room taken from the neighbour"
                else:
                    rec["shift_skipped"] = "every move overlaps a sibling (predicted with the overlap gate rule) — left alone"
                    continue
            moved = _shift_text(w, sx, sy, after, own_main=own)
            if moved and moved.get("shift"):
                rec.update(moved)
                main = {"horizontal_box": 0, "vertical_box": 1}.get((w.get("slot") or {}).get("kind"))
                if own and main is not None and moved["shift"][main]:
                    rec["own_padding"] = "no new sibling overlap predicted — moved along the box inside its own slot"
                if row is not None:
                    row["x"] += moved["shift"][0]
                    row["y"] += moved["shift"][1]
            else:
                rec["shift_skipped"] = (moved or {}).get("skipped") or f"slot kind {(w.get('slot') or {}).get('kind')} cannot be moved without moving its siblings"
    if followed:
        recs.append({"text_boxes_followed": followed})
    return after, recs


def text_fit_changed(recs: list[dict]) -> list[str]:
    return [r["widget"] for r in recs if r.get("widget") and (r.get("shift") or r.get("letter_spacing") or r.get("weight") or r.get("size") or r.get("color")
                                                            or r.get("outline") or r.get("glow") or r.get("shadow"))]


GLOW_GAP = 0.15               # 1b 후속 J — 핵심 획 밖 '바탕보다 밝은' 비율(빛 번짐) 차가 이보다 크면 빛 크기를 비율만큼 고친다(진단 text_halo_frac 0.2 보다 앞에서)
GLOW_SCALE = (0.5, 1.5)       # 한 번에 바꿀 빛 크기 배율 범위


GLOW_NONE = 0.05              # 컨셉 빛 번짐 비율이 이 미만이면 빛 없음으로 본다(빛을 뗀다)


def _add_glow(f: dict, ref, ren, g: dict, roles: dict | None) -> dict | None:
    """1b 후속 K E7 — 컨셉은 빛나는데 렌더 글자엔 빛이 없으면(진단 E7 과 같은 기준: 컨셉 띠 밝기 − 렌더 ≥ 문턱/2) 빛을 넣는다: 크기 = 컨셉 측정 크기,
    색 = analyze derive_text_glow 와 같은 식(바탕 B 에서 1 ~ 3 px 띠 색 C 쪽으로 한 채널이 255 에 닿을 때까지), 글꼴 = 그 역할의 SDF 사본.
    [실측 K R20261118_002153 '오의 불가' — analyze 측정 7.9 로 문턱 8 바로 아래라 빛을 안 붙였고, 진단은 8.2 로 E7 — 맞춤이 넣는 길이 없었다]."""
    import cv2
    import numpy as np
    from gen import diagnose
    gmin = diagnose.DEFAULTS["glow_min"]
    gc = diagnose.glow_measure(ref, g.get("concept_glow_bg"), g["concept"])
    gr = diagnose.glow_measure(ren, g.get("render_bg"), g["render"])
    if not gc or not gr or not diagnose.glow_on(gc, gmin) or diagnose.glow_on(gr, gmin) or gc["peak"] - gr["peak"] < gmin / 2:
        return None
    sdf = next((r.get("sdf_family") for r in (roles or {}).values() if f.get("family") in (r.get("family"), r.get("sdf_family")) and r.get("sdf_family")), None)
    if not sdf:
        return {"skipped": "the concept glows but this font has no SDF copy", "peak": [gc["peak"], gr["peak"]]}
    core = np.asarray(g["concept"], bool)
    dist = cv2.distanceTransform((~core).astype(np.uint8), cv2.DIST_L2, 5)
    band = (dist > 1) & (dist <= 3)
    bgb = (dist > 10) & (dist <= 14)
    bgimg = g.get("concept_glow_bg") if g.get("concept_glow_bg") is not None else g.get("concept_bg")
    if not band.any() or not bgb.any() or bgimg is None:
        return None
    C, B = np.median(np.asarray(ref, float)[band], axis=0), np.median(np.asarray(bgimg, float)[band], axis=0)
    v = C - B
    pos = v > 1e-6
    if not pos.any():
        return None
    size = max(3, int(gc["size"] or 3))
    k = max(1.0, float(np.min((255.0 - B[pos]) / v[pos])))
    G = np.clip(B + k * v, 0, 255)
    alpha = float(np.clip(1.0 / (k * max((1.0 - 2.5 / size) ** 1.5, 1e-3)), 0.15, 1.0))
    f["glow"] = {"size": size, "color": "#" + "".join(f"{int(round(c)):02X}" for c in G) + f"{int(round(alpha * 255)):02X}"}
    old_family = f.get("family")
    f["family"] = sdf
    return {"old": 0, "new": size, "added": True, "color": f["glow"]["color"], "family": [old_family, sdf], "peak": [gc["peak"], gr["peak"]]}


def _fit_glow(f: dict, ref, ren, g: dict, roles: dict | None = None) -> dict | None:
    """1b 후속 J — 빛(font.glow) 크기를 진단과 같은 마스크 · 바탕의 빛 번짐 비율로 맞춘다: 새 크기 = 크기 × (컨셉 비율 ÷ 렌더 비율)(GLOW_SCALE 안 · 최소 2).
    [실측 J R20261117_204115 파티 HUD 'Lv' — analyze 빛 크기 10 이 컨셉보다 넓어 비율 0.32 ↔ 0.54]. 외곽선이 있는 글자는 안 건드린다. → 기록 또는 None."""
    from gen import diagnose
    gl = f.get("glow") if isinstance(f.get("glow"), dict) else None
    cb, rb = g.get("concept_bg"), g.get("render_bg")
    if (not gl or not gl.get("size")) and not f.get("outline") and cb is not None and rb is not None:
        return _add_glow(f, ref, ren, g, roles)
    if not gl or not gl.get("size") or f.get("outline") or cb is None or rb is None:
        return None
    # 1b 후속 K E7 — 진단 · analyze 와 같은 빛 측정(diagnose.glow_measure — 획 둘레 고리 ↔ 글자 없는 바탕)으로 유무 · 크기
    gc = diagnose.glow_measure(ref, g.get("concept_glow_bg"), g["concept"])
    gr = diagnose.glow_measure(ren, rb, g["render"])
    if not gc or not gr:
        return None
    old = int(round(float(gl["size"])))
    gmin = diagnose.DEFAULTS["glow_min"]
    fc, fr = (0.0, gc["frac"]), (0.0, gr["frac"])
    if not diagnose.glow_on(gc, gmin) and diagnose.glow_on(gr, gmin) and gr["peak"] - gc["peak"] >= gmin / 2:
        # 컨셉엔 빛 번짐이 사실상 없다(analyze derive_text_glow 가 두 톤 띠 밝기를 빛으로 오판) — 빛을 떼고 그 역할의 보통 글꼴로
        # [실측 J R20261117_213212 조작 안내 '점프' — 컨셉 빛 비율 0.007, SDF 빛 글자가 굵게 재져 굵기 결함]
        f.pop("glow", None)
        fam = f.get("family")
        for r in (roles or {}).values():
            if fam and fam == r.get("sdf_family"):
                f["family"] = r["family"]
        return {"old": old, "new": 0, "dropped": True, "family": f.get("family"), "peak": [gc["peak"], gr["peak"]], "halo_frac": [fc[1], fr[1]]}
    if not (diagnose.glow_on(gc, gmin) and diagnose.glow_on(gr, gmin)):
        return None
    if abs(gc["size"] - gr["size"]) <= 1:
        # 1b 후속 L-2 사람 눈 — 크기가 맞으면 세기(띠 밝기)를 빛 색 알파로 맞춘다(진단 E9 glow_strength 와 같은 기준 · 같은 측정). 크기를 바꾸는 판에선
        # 띠 밝기도 같이 바뀌어 다음 판으로 미룬다 [사용자 눈 R20261118_142524 '오의 불가' — 렌더 빛이 더 세고 붉음, 띠 밝기 30.7 ↔ 42.7 · 알파 0.96]
        st = _glow_strength(gl, gc, gr, gmin)
        if not st:
            return None
        f["glow"] = {**gl, "color": st["color"]}
        return {"old": old, "new": old, "alpha": st["alpha"], "size_measured": [gc["size"], gr["size"]], "peak": [gc["peak"], gr["peak"]]}
    st = _glow_strength(gl, gc, gr, gmin)
    if st and (gc["size"] > gr["size"]) == (st["alpha"][1] < st["alpha"][0]):
        # 1b 후속 L 다음 — 크기와 세기가 반대로 가야 하면(키워야 하는데 렌더 띠가 이미 더 밝음 · 줄여야 하는데 더 어두움) 세기(알파)를 먼저 — 크기를 키운 판이
        # 띠 밝기를 더 올려(27.1 → 31.1) 판이 버려지고 세기 E9 가 남았다 [실측 파티 R20261119_002317 '0 %' — 빛 크기 11 ↔ 9 · 띠 22.6 ↔ 27.1]. 크기는 다음 판
        f["glow"] = {**gl, "color": st["color"]}
        return {"old": old, "new": old, "alpha": st["alpha"], "size_measured": [gc["size"], gr["size"]], "peak": [gc["peak"], gr["peak"]],
                "size_deferred": "glow size and strength pull opposite ways — strength first"}
    k = min(GLOW_SCALE[1], max(GLOW_SCALE[0], gc["size"] / max(1, gr["size"])))
    new = max(2, int(round(old * k)))
    if new == old:
        new = max(2, old - 1) if gr["size"] > gc["size"] else old + 1
    if new == old:
        return None
    f["glow"] = {**gl, "size": new}
    return {"old": old, "new": new, "size_measured": [gc["size"], gr["size"]], "peak": [gc["peak"], gr["peak"]]}


def _glow_strength(gl: dict, gc: dict, gr: dict, gmin: float) -> dict | None:
    """빛 세기 맞춤 — 진단과 같은 기준(띠 밝기 비 > GLOW_PEAK_TOL · 차 ≥ 문턱/2)이면 새 알파 = 알파 × (컨셉 띠 밝기 ÷ 렌더 띠 밝기). 알파 0.15 ~ 1.0.
    엔진 빛(SDF 외곽선 층 머티리얼)의 띠 밝기(L*)는 알파에 거의 비례한다 [실측 R20261118_163950 '오의 불가' — 알파 0.957 → 0.52 에 41.0 → 21.3(비 0.54 ↔ 0.52).
    처음 쓴 선형 휘도(L* 세제곱) 모델은 절반으로 내려 반대로 어긋났다]. → {color, alpha} 또는 None."""
    import numpy as np
    from gen import diagnose
    a = diagnose.glow_alpha({"glow": gl})
    if a is None:
        return None
    ratio = max(gr["peak"], 1e-3) / max(gc["peak"], 1e-3)
    if abs(gr["peak"] - gc["peak"]) < gmin / 2 or max(ratio, 1.0 / ratio) <= diagnose.GLOW_PEAK_TOL:
        return None
    if gr["peak"] <= 0:
        return None
    lo, hi = diagnose.GLOW_ALPHA_RANGE
    na = float(np.clip(a * min(4.0, max(0.25, gc["peak"] / gr["peak"])), lo, hi))
    if abs(na - a) < 0.02:
        return None
    h = str(gl.get("color") or "#FFFFFF").lstrip("#")[:6]
    return {"color": f"#{h.upper()}{int(round(na * 255)):02X}", "alpha": [round(a, 3), round(na, 3)]}


def _fit_shadow(f: dict, ref, ren, g: dict) -> dict | None:
    """1b 후속 L-3c — 글자 그림자(font.shadow{offset, color})를 진단과 같은 측정(diagnose.shadow_measure — 옮긴 획 자리 ↔ 글자 없는 바탕, 반대쪽 빼기)으로
    컨셉에 있고 렌더에 없으면 넣고(오프셋 · 색 = 컨셉에서 잰 값), 렌더에만 있으면 뺀다 — 진단 E7 과 같은 문턱(넣기 · 떼기 한 기준 — K 교훈: 문턱이 다르면 진동).
    [사람 눈 L — 원래 전투 HUD '체인 버스트' · '체인' · '2/4' 오른쪽 아래 얇은 그림자]. → 기록 또는 None."""
    from gen import diagnose
    rb = g.get("render_bg")
    if rb is None:
        return None
    sc = diagnose.shadow_measure(ref, g.get("concept_glow_bg"), g["concept"])
    sr = diagnose.shadow_measure(ren, rb, g["render"])
    if not sc or not sr or sc["present"] == sr["present"] or abs(sc["dark"] - sr["dark"]) < diagnose.SHADOW_MIN / 2:
        return None
    old = f.get("shadow")
    if sc["present"]:
        f["shadow"] = {"offset": list(sc["offset"]), "color": sc["color"]}
    elif old:
        f.pop("shadow", None)
    else:
        return None
    return {"old": old, "new": f.get("shadow"), "dark": [sc["dark"], sr["dark"]], "offset_measured": sc["offset"]}


OUTLINE_FRAC = 0.2            # 컨셉 획 후보 중 '바탕보다 어두운' 비율이 이 이상이면 외곽선이 있는 글자(진단 text_dark_frac 과 같은 값)
OUTLINE_GAP = 0.15            # 렌더와 그 비율 차가 이보다 크면 외곽선을 넣거나 뺀다
OUTLINE_OVER_GLOW = 0.45      # 1b 후속 J — 컨셉 획 후보의 어두운 비율이 이 이상이면(굵은 외곽선) 빛 대신 외곽선 — 빛 측정(획 2 ~ 6 px 밖 밝기)은 굵은 어두운 테 바깥
                              # 바탕(방패 금속)을 빛으로 잰다 [실측 J R20261117_192631 파티 HUD 방패 '10' — 컨셉 어두운 비율 0.66 ↔ 렌더 0, 빛 때문에 외곽선을 못 넣음]


def _fit_outline(f: dict, ref, ren, g: dict) -> dict | None:
    """1b 후속 J-c — 외곽선(획 둘레 어두운 테)을 진단과 같은 마스크 · 바탕으로 재 컨셉에 있고 렌더에 없으면 넣고(두께 = 어두운 테 넓이 ÷ 핵심 획 둘레,
    1 ~ 4 px · 색 = 그 픽셀 중앙값), 렌더에만 있으면 뺀다. [실측 J R20261117_184207 단색 '오의 불가' — 컨셉 0.39 ↔ 렌더 0.15]. → 기록 또는 None."""
    import numpy as np
    from gen import diagnose
    cb, rb = g.get("concept_bg"), g.get("render_bg")
    if cb is None or rb is None:
        return None
    fc = diagnose._edge_fracs(g["concept_cand"], g["concept"], ref, cb)
    fr = diagnose._edge_fracs(g["render_cand"], g["render"], ren, rb)
    if not fc or not fr or abs(fr[0] - fc[0]) <= OUTLINE_GAP:
        return None
    old = f.get("outline")
    glow_dropped = None
    if fc[0] >= OUTLINE_FRAC and fr[0] < fc[0]:
        if (f.get("glow") or {}).get("size"):
            if fc[0] < OUTLINE_OVER_GLOW:
                # 빛은 외곽선 층으로 그린다(글자 하나에 하나 — WidgetMcp 가 둘 다 있으면 거절) [실측 J R20261117_191858 'ShieldCountText']
                return {"skipped": "the text glows — the glow uses the outline layer, so no outline is added", "dark_frac": [round(fc[0], 3), round(fr[0], 3)]}
            glow_dropped = f.pop("glow")          # 굵은 외곽선이 빛보다 앞선다(OUTLINE_OVER_GLOW) — 빛 크기만큼 넓힌 상자는 그대로(외곽선이 그 안에 든다)
        from core import color as cm
        cand, core = g["concept_cand"], g["concept"]
        dl = cm.srgb_to_lab(np.asarray(ref, float)[cand])[..., 0] - cm.srgb_to_lab(np.asarray(cb, float)[cand])[..., 0]
        dark = np.zeros_like(cand)
        dark[cand] = dl < -8
        dark &= ~core
        ring = diagnose._dilate(core, 1) & ~core
        size = int(min(4, max(1, round(int(dark.sum()) / max(1, int(ring.sum()))))))
        c = np.median(np.asarray(ref, float)[dark], axis=0) if dark.any() else np.zeros(3)
        f["outline"] = {"size": size, "color": "#%02X%02X%02XFF" % tuple(int(round(min(255.0, max(0.0, float(v))))) for v in c)}
    elif fr[0] > fc[0] and old:
        f.pop("outline", None)
    else:
        return None
    return {"old": old, "new": f.get("outline"), "dark_frac": [round(fc[0], 3), round(fr[0], 3)], **({"glow_dropped": glow_dropped} if glow_dropped else {})}


TEXT_FIT_COLOR_DE = 6.0       # 컨셉 ↔ 렌더 핵심 획 대표색(위 · 아래 반 중 큰 쪽) ΔE00 이 이보다 크면 글자색을 컨셉 쪽으로
TEXT_FIT_GRADIENT_DE = 8.0    # 컨셉 핵심 획 위 · 아래 반 대표색 차가 이보다 크면 세로 그라데이션(아니면 한 색)


def _fit_color(f: dict, ref, ren, mc, mr) -> dict | None:
    """1b 후속 J-c — 글자색을 진단과 같은 핵심 획(빛 번짐 제외)의 대표색으로: 위 · 아래 반 중앙값이 렌더와 TEXT_FIT_COLOR_DE 넘게 다르면 바꾼다
    (위 · 아래 차 > TEXT_FIT_GRADIENT_DE 면 gradient + color 흰색, 아니면 한 색). [실측 J R20261117_174247] analyze 색 파생이 두 톤 띠 위 '점프' 를
    남색으로 잡아 렌더 글자가 남색이었다(진단 '색 · 외곽선'). → 기록 또는 None."""
    import numpy as np
    from core import color as cm

    def halves(img, m):
        ys = np.nonzero(m)[0]
        mid = float(np.median(ys))
        rows = np.arange(img.shape[0])[:, None]
        top, bot = img[m & (rows <= mid)], img[m & (rows > mid)]
        if not len(top) or not len(bot):
            return None
        return np.median(img[m], axis=0), np.median(top, axis=0), np.median(bot, axis=0)

    def de(a, b):
        return float(cm.delta_e00(cm.srgb_to_lab(np.asarray(a, float).reshape(1, 3)), cm.srgb_to_lab(np.asarray(b, float).reshape(1, 3)))[0])

    def hexc(c):
        return "#%02X%02X%02XFF" % tuple(int(round(min(255.0, max(0.0, float(v))))) for v in c)
    c, r = halves(ref, mc), halves(ren, mr)
    if c is None or r is None:
        return None
    d_now = max(de(c[1], r[1]), de(c[2], r[2]))
    if d_now <= TEXT_FIT_COLOR_DE:
        return None
    old = {"color": f.get("color"), "gradient": f.get("gradient")}
    if de(c[1], c[2]) > TEXT_FIT_GRADIENT_DE:
        f["gradient"] = {"top_color": hexc(c[1]), "bottom_color": hexc(c[2])}
        f["color"] = "#FFFFFFFF"
    else:
        f.pop("gradient", None)
        f["color"] = hexc(c[0])
    return {"old": old, "new": {"color": f.get("color"), "gradient": f.get("gradient")}, "core_de_before": round(d_now, 2)}


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


def fidelity_score(fid: dict | None) -> float | None:
    """따온 에셋 충실도 한 수 — 실루엣 IoU · 장식선 F1 · 모서리 F1 최소(있는 것만) 중 가장 낮은 것(1b 후속 G — 라운드 교체 기준)."""
    if not isinstance(fid, dict):
        return None
    vals = [fid.get("shape_iou"), (fid.get("line_f1") or {}).get("f1"), (fid.get("corners") or {}).get("min")]
    vals = [float(v) for v in vals if isinstance(v, (int, float))]
    return round(min(vals), 4) if vals else None


def _last_fidelity(refine_log: dict, aid: str) -> dict | None:
    for p in reversed(refine_log.get("passes") or []):
        for a in p.get("assets") or []:
            if a.get("asset_id") == aid and a.get("fidelity"):
                return a["fidelity"]
    return None


def replace_guard(run, backup_rel: str, assets: list[str], tol: float = 0.02) -> list[dict]:
    """1b 후속 G — 외형 라운드가 다시 따온 에셋의 충실도가 라운드 전보다 tol 넘게 나빠지면 그 에셋만 옛 것(사본의 final · raw · compare ·
    manifest.json)으로 되돌린다 — 라운드의 다른 op 는 그대로 간다. [실측 F run 4] 배너 다시 따오기가 장식선 F1 0.983 → 0.914 · 선 ΔE00 7.9 → 14.6
    으로 나빠졌는데 게이트만 보고 받아들여 금테가 노랗게 됐다. → 기록 [{asset, before, after, action}]."""
    import shutil
    bdir = run.path(backup_rel)
    old_log = json.loads((bdir / "refine.json").read_text(encoding="utf-8")) if (bdir / "refine.json").is_file() else {}
    new_log = run.read_json("refine.json") if run.path("refine.json").is_file() else {}
    out, restored_ids = [], []
    for aid in assets:
        so, sn = fidelity_score(_last_fidelity(old_log, aid)), fidelity_score(_last_fidelity(new_log, aid))
        rec = {"asset": aid, "before": so, "after": sn, "tol": tol}
        if so is None or sn is None:
            out.append({**rec, "action": "kept_new", "reason": "no fidelity record to compare (not an extracted asset)"})
            continue
        if sn >= so - tol:
            out.append({**rec, "action": "kept_new"})
            continue
        restored = []
        for kind in ("final", "raw", "compare"):
            src = bdir / "assets" / kind / f"{aid}.png"
            if src.is_file():
                shutil.copyfile(src, run.path("assets", kind, f"{aid}.png"))
                restored.append(f"assets/{kind}/{aid}.png")
        restored_ids.append(aid)
        out.append({**rec, "action": "restored_old", "restored": restored})
    if restored_ids and (bdir / "manifest.json").is_file() and run.path("manifest.json").is_file():
        old_m = {a["asset_id"]: a for a in json.loads((bdir / "manifest.json").read_text(encoding="utf-8"))["assets"]}
        cur = run.read_json("manifest.json")
        cur["assets"] = [old_m.get(a["asset_id"], a) if a["asset_id"] in restored_ids else a for a in cur["assets"]]
        run.write_json("manifest.json", cur)
    return out


def _metric_lines(rep: dict) -> str:
    rows = []
    for rid, r in (rep.get("regions") or {}).items():
        rows.append(f"- region {rid}: sheet {r.get('sheet')} · frame line F1 {(r.get('line_f1') or {}).get('f1')} · corner ornament F1 min "
                    f"{(r.get('corners') or {}).get('min')} · silhouette IoU {r.get('shape_iou')} · "
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
