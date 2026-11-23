"""1b 후속 L-2 — 글자 없는 컨셉부터 + 글자 참고판 (설계 §11 'L 설계' L-2 ① ~ ⑦).

우리가 만드는 컨셉(M4 HUD 등)은 codex 가 처음부터 **글자 없이** 그린 원본 아트(사람이 승인하는 픽셀 정답)와, 그 아트에 codex 편집 1 회로 글자만
얹은 **글자 참고판**(글자 스타일 측정용 — 다시 그린 그림이라 바탕 픽셀은 정답이 아니다) 두 장이다. 여기는 그 두 장을 잇는 결정적 부분:

- `text_items` · `text_ref_prompt` — 참고판 편집 프롬프트(inputs static_text 값 · 바인딩 글자의 sample 값, 칸은 desc 로만 — 좌표 없음).
- `merge` — 참고판을 원본 아트에 정합(위상 상관 — 글자 없는 판 정합의 반대 방향: 참고판을 옮김)하고, 참고판 OCR 상자 안에서 아트와 ±2 px 이동
  최소 차가 큰 픽셀(글자 획 · 안티앨리어싱 · 획에 붙은 빛)만 아트 위에 옮겨 붙인 그림 = **'원본 아트 + 참고판 글자'**. 이 그림이 레퍼런스(analyze ·
  글자 맞춤 · 진단 글자 비교가 읽는 그림)이고, 아트 · 글자 없는 판은 원본 아트다 — 다시 그린 바탕의 색조 차가 어느 비교에도 섞이지 않는다.
- 검사(설계 위험 · 가드): 이동 ≤ MAX_SHIFT · 참고판에 글자 상자가 있음 · 글자 상자 밖 차이(큰 차 · 새 불투명 픽셀 비율)가 작음. 실패면 참고판을
  쓰지 않는다(글자는 사양 — LLM 이 어휘에서).
"""
from __future__ import annotations

import numpy as np

MAX_SHIFT = 12             # 참고판 정합 — 위상 상관 이동이 이보다 크면 같은 그림으로 보지 않는다(px, normalize.NOTEXT_MAX_SHIFT 와 같음)
SHIFT_TOL = 2              # 다시 그린 장식 어긋남을 덮는 이동 범위(px, diagnose.SHIFT_TOL 과 같음)
OCR_MIN_SCORE = 0.6        # 참고판 글자 상자 — 글자가 있다는 걸 아는 그림이라 구운 글자 문턱(0.7)보다 낮게, 아트에도 있는 자국(장식)은 뺀다
BOX_PAD = 6                # 글자 상자 둘레 여유(px) — 검출 상자가 획 끝 · 빛을 조금 자른다
GLYPH_D = 48.0             # 글자 획 = 이동 최소 채널 차가 이 이상(diagnose.INK_MIN 과 같음)
GLYPH_MIN_PX = 6           # 이보다 작은 덩어리는 잡티
EDGE_R = 2                 # 획 둘레 안티앨리어싱 — 이만큼 넓혀 붙인다(진단은 획 + 2 px 를 바탕 검사에서 뺀다)
GLOW_R = 12                # 획에 붙은 빛 — 획에서 이 거리 안
GLOW_L = 8.0               # 빛 = 참고판이 아트보다 L* 이만큼 더 밝음(둘레 바탕 색조 차를 뺀 뒤)
OUT_D = 80.0               # 글자 상자 밖 '큰 차'(이동 최소 채널 차) — 다시 그린 색조 차는 이보다 작다
OUT_MAX = 0.03             # 칸 밖 차이(아래 둘 각각)가 이 비율을 넘으면 칸 밖을 바꾼 것으로 본다
ALPHA_NEW = 0.5            # 새 불투명(또는 사라진) 픽셀 = 이동 최소 알파 차가 이 이상
SOLID_A, EMPTY_A = 0.9, 0.05   # 아트가 단단히 그린 자리 · 아무것도 없는 자리. 그 사이(옅은 바깥 빛 · 반투명 가장자리)는 codex 가 알파를 다시 그린다
# [실측 L-2 첫 참고판 — 원본 아트의 옅은 바깥 빛을 불투명한 갈색 띠로 다시 그림: 칸 밖 큰 차 18 % · 알파 차 20 %, 글자 · 칸 자리는 그대로]. 합친 그림은
# 글자 상자 안 픽셀만 참고판에서 가져와 그 차가 결과에 안 섞인다 → 칸 밖 검사는 '단단한 자리의 큰 색 차' · '아트가 비운 먼 자리에 새로 그림'만, 가장자리는 기록만
OWN_EDGE_D = 16.0          # 획 둘레 2 px 중 참고판 자기 바탕과 이만큼 다른 것만 안티앨리어싱으로(반투명 · 빈 자리)
OWN_BG_MIN, OWN_BG_MAX = 15, 61    # 반투명 면 위 글자의 자기 바탕(참고판) 중앙값 창(px, 글자 상자 높이 — 획보다 넉넉히)
FAR_R = 16                 # '먼 자리' = 아트 보이는 픽셀(알파 > 0.02)에서 이 거리 밖


def format_sample(d: dict):
    """바인딩 글자의 sample → 화면 글자(number 는 format '0' · '0.0…' 대로). 없으면 None."""
    s = d.get("sample")
    if s is None or isinstance(s, bool):
        return None
    if d.get("type") == "number":
        try:
            v = float(s)
        except (TypeError, ValueError):
            return str(s)
        fmt = str(d.get("format") or "0")
        nd = len(fmt.split(".")[1]) if "." in fmt else 0
        return f"{v:.{nd}f}"
    return str(s)


def text_items(inputs: dict) -> list[dict]:
    """참고판에 얹을 글자 — static_text(값) + 바인딩 text · number(sample). 칸 설명 = desc(static_text · data · required_elements 순), 없으면 위젯 id."""
    req = {e["id"]: e.get("desc") for e in inputs.get("required_elements") or []}
    out = []
    for st in inputs.get("static_text") or []:
        v = str(st.get("value") or "").strip()
        if v:
            out.append({"widget": st["widget"], "value": v, "slot": st.get("desc") or req.get(st["widget"]) or st["widget"]})
    for d in inputs.get("data") or []:
        if d.get("type") not in ("text", "number") or d.get("widget_type") != "TextBlock":
            continue
        v = format_sample(d)
        if v:
            out.append({"widget": d["widget"], "value": v, "slot": d.get("desc") or req.get(d["widget"]) or d["widget"]})
    return out


TEXT_REF_HEAD = ("Add text to the attached UI image. Write exactly these texts, each one into its empty slot, and nothing else "
                 "(the slot is described after the dash — the description is not text to write):")
TEXT_REF_RULES = (
    "Draw them as finished game UI typography: crisp, legible, the Korean and the digits exactly as written, sized to fit their slots, "
    "in a color and weight that suit the UI.\n"
    "Change nothing else: keep every element, frame, ornament, glow, color, position and size identical, the same framing and aspect ratio, "
    "the same sharpness and resolution. Do not add any other text, number, symbol, icon or decoration.\n"
    "The attached image has a transparent background (PNG alpha). Keep the result genuinely transparent with the same alpha everywhere outside the "
    "new text: no background color, no checkerboard, translucent parts equally translucent."
)
TEXT_REF_PURPOSE = "keep every UI element, line, color, position and size identical; only add the listed text into the empty slots"


def text_ref_prompt(inputs: dict) -> str:
    items = text_items(inputs)
    lines = [TEXT_REF_HEAD] + [f'- "{it["value"]}" — {it["slot"]}' for it in items]
    return "\n".join(lines) + "\n" + TEXT_REF_RULES


def _gray(black):
    import cv2
    return cv2.cvtColor(np.clip(black, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)


def _dilate(m, r: int):
    import cv2
    if r <= 0:
        return m.copy()
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.dilate(m.astype(np.uint8), k) > 0


def _shift_min(a, b, tol: int = SHIFT_TOL):
    """채널 최대 차(3 채널) 또는 절대 차(1 채널) — b 를 ±tol px 옮긴 것 중 가장 작은 차."""
    H, W = a.shape[:2]
    best = None
    for dy in range(-tol, tol + 1):
        for dx in range(-tol, tol + 1):
            ys = np.clip(np.arange(H) + dy, 0, H - 1)
            xs = np.clip(np.arange(W) + dx, 0, W - 1)
            bs = b[np.ix_(ys, xs)]
            d = np.abs(a - bs)
            d = d.max(axis=2) if d.ndim == 3 else d
            best = d if best is None else np.minimum(best, d)
    return best.astype(np.float32)


def _box_mask(shape, boxes, pad: int) -> np.ndarray:
    H, W = shape
    m = np.zeros((H, W), bool)
    for b in boxes:
        x, y, w, h = (int(round(v)) for v in b)
        m[max(0, y - pad):min(H, y + h + pad), max(0, x - pad):min(W, x + w + pad)] = True
    return m


def _iou(a, b) -> float:
    ax0, ay0, ax1, ay1 = a[0], a[1], a[0] + a[2], a[1] + a[3]
    bx0, by0, bx1, by1 = b[0], b[1], b[0] + b[2], b[1] + b[3]
    iw, ih = max(0.0, min(ax1, bx1) - max(ax0, bx0)), max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    return inter / max(1e-6, a[2] * a[3] + b[2] * b[3] - inter)


def _rgba(col, a):
    from PIL import Image
    return Image.fromarray(np.dstack([np.clip(col, 0, 255), np.clip(a, 0, 1) * 255]).round().astype(np.uint8), "RGBA")


def detect_boxes(col, a, detect=None, min_score: float = OCR_MIN_SCORE) -> list[dict]:
    """OCR 검출 상자(곧은 색 · 알파 → 회색 바탕 합성으로 검출 — core.ocr)."""
    if detect is None:
        from core import ocr
        detect = ocr.detect
    return list(detect(_rgba(col, a), min_score=min_score).get("boxes") or [])


def merge(a_col, a_a, t_col, t_a, *, detect=None) -> tuple:
    """원본 아트(a_col · a_a — 곧은 색 · 알파 0 ~ 1)와 글자 참고판(같은 크기)을 → (합친 색, 합친 알파, 정합된 참고판 (색, 알파), 기록).
    기록 `used` 가 False 면 합친 그림은 아트 그대로(참고판을 쓰지 않음 — 이유 `reason`)."""
    import cv2
    H, W = a_a.shape
    a_col, a_a = np.asarray(a_col, float), np.clip(np.asarray(a_a, float), 0, 1)
    t_col, t_a = np.asarray(t_col, float), np.clip(np.asarray(t_a, float), 0, 1)
    win = cv2.createHanningWindow((W, H), cv2.CV_32F)
    (dx, dy), resp = cv2.phaseCorrelate(_gray(a_col * a_a[..., None]), _gray(t_col * t_a[..., None]), win)
    rec: dict = {"shift_px": [round(float(dx), 2), round(float(dy), 2)], "response": round(float(resp), 4), "used": False}
    if max(abs(dx), abs(dy)) > MAX_SHIFT:
        rec["reason"] = f"phase correlation shift {rec['shift_px']} > {MAX_SHIFT} px — the text reference is not the same picture"
        return a_col, a_a, (t_col, t_a), rec
    # 정수 px 로 옮긴다 — 붙일 것은 참고판 글자 획(아트에 짝이 없는 픽셀)이라 0.5 px 안 어긋남은 상관없고, 소수 이동(쌍선형)은 획을 흐려 굵기 측정이 달라진다.
    # 다시 그린 바탕의 어긋남은 아래 ±2 px 이동 최소 차가 덮는다
    ix, iy = int(round(dx)), int(round(dy))
    rec["shift_applied"] = [ix, iy]
    M = np.float32([[1, 0, -ix], [0, 1, -iy]])

    def warp(ch):
        return cv2.warpAffine(ch.astype(np.float32), M, (W, H), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_REPLICATE)
    t_col = np.clip(np.dstack([warp(t_col[..., i]) for i in range(3)]), 0, 255).astype(float)
    t_a = np.clip(warp(t_a), 0, 1).astype(float)
    ab, tb = a_col * a_a[..., None], t_col * t_a[..., None]
    # 글자 상자 — 참고판 OCR 중 아트에도 있는 자국(장식 오검출 — IoU ≥ 0.3)은 뺀다
    tboxes = detect_boxes(t_col, t_a, detect)
    aboxes = detect_boxes(a_col, a_a, detect)
    boxes = [b for b in tboxes if not any(_iou(b["box"], c["box"]) >= 0.3 for c in aboxes)]
    rec["ocr"] = {"text_ref_boxes": [b["box"] for b in tboxes], "art_boxes": [b["box"] for b in aboxes], "boxes": [b["box"] for b in boxes],
                  "scores": [b["score"] for b in boxes], "min_score": OCR_MIN_SCORE}
    ui = (a_a > 0.1) | (t_a > 0.1)
    inbox = _box_mask((H, W), [b["box"] for b in boxes], BOX_PAD)
    d = _shift_min(tb, ab)
    da = _shift_min(t_a, a_a)
    out = ui & ~_dilate(inbox, 2)
    n_ui = max(1, int(ui.sum()))
    solid, fringe = a_a > SOLID_A, (a_a >= EMPTY_A) & (a_a <= SOLID_A)
    big = out & solid & (d > OUT_D)                                           # 아트가 단단히 그린 자리의 큰 색 차(칸 · 패널 · 장식을 바꿔 그림)
    far = out & (t_a > ALPHA_NEW) & ~_dilate(a_a > 0.02, FAR_R)               # 아트가 비운 먼 자리에 새로 그림(칸 밖 글자 · 요소)
    edge = out & fringe & (da > ALPHA_NEW)                                    # 반투명 가장자리 알파 차 — 기록만
    rec["checks"] = {"ui_px": n_ui, "outside_solid_big_frac": round(float(big.sum()) / n_ui, 4), "outside_far_new_frac": round(float(far.sum()) / n_ui, 4),
                     "fringe_alpha_frac": round(float(edge.sum()) / n_ui, 4),
                     "outside_median_d": round(float(np.median(d[out])), 2) if out.any() else None,
                     "outside_p95_d": round(float(np.percentile(d[out], 95)), 2) if out.any() else None, "limit": OUT_MAX}
    # 글자 획 — 상자 안에서 아트와 크게 다른 픽셀(작은 잡티 빼기). 아트의 반투명 가장자리는 빼고 본다(codex 가 알파를 다시 그린 띠가 상자에 걸치면 획으로 잡힘)
    # 반투명 면 위에서는 codex 가 띠 끝을 다시 그린 옅은 안개도 아트와 크게 다르다 → 참고판 **자기 바탕**(글자 상자 높이만 한 중앙값 창)과도 달라야 획
    # [실측 combat_hud_blade — '체인' · '2/4' 둘레 회색 덩어리가 획으로 붙어 글자 빛 · 굵기 측정을 흐림]
    own_d = np.full((H, W), np.inf, np.float32)
    for b in boxes:
        x, y, bw, bh = (int(round(v)) for v in b["box"])
        k = int(np.clip(bh, OWN_BG_MIN, OWN_BG_MAX)) | 1
        x0, y0, x1, y1 = max(0, x - BOX_PAD - k), max(0, y - BOX_PAD - k), min(W, x + bw + BOX_PAD + k), min(H, y + bh + BOX_PAD + k)
        win_ = np.clip(tb[y0:y1, x0:x1], 0, 255).astype(np.uint8)
        med = np.dstack([cv2.medianBlur(win_[..., i], k) for i in range(3)]).astype(float)
        own_d[y0:y1, x0:x1] = np.minimum(own_d[y0:y1, x0:x1], np.abs(tb[y0:y1, x0:x1] - med).max(axis=2))
    cand = inbox & (d > GLYPH_D)
    glyph = cand & ~fringe
    cand &= (own_d > GLYPH_D) | ~fringe
    # L-2 기본 전환(11-23) — 글자가 **반투명 면** 위에 앉으면(끝이 사라지는 먹색 띠 — 알파 0.4 ~ 0.9) 그 획이 통째로 빠졌다 [실측 combat_hud_blade — 여섯 글자 중
    # 다섯의 획 8,900 px 중 7,400 px]. 다시 그린 띠는 글자 상자 가장자리까지 이어지고 획은 상자 안에 갇혀 있다(상자 + BOX_PAD) → 가장자리에 안 닿는 덩어리는 획
    if (cand & fringe).any():
        k3 = np.ones((3, 3), np.uint8)
        edge = inbox & ~(cv2.erode(inbox.astype(np.uint8), k3, borderValue=0) > 0)
        n0, lab0 = cv2.connectedComponents(cand.astype(np.uint8), connectivity=8)
        touching = set(np.unique(lab0[edge & cand]).tolist())
        inside = np.isin(lab0, [i for i in range(1, n0) if i not in touching])
        rec["glyph_on_translucent_px"] = int((inside & fringe).sum())
        glyph |= inside
    n, lab, st, _ = cv2.connectedComponentsWithStats(glyph.astype(np.uint8), connectivity=8)
    small = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] < GLYPH_MIN_PX]
    if small:
        glyph &= ~np.isin(lab, small)
    # 획에 붙은 빛 — 둘레 바탕 색조 차(획에서 GLOW_R + 2 ~ + 8 px 고리의 L* 차 중앙값)를 빼고도 참고판이 더 밝은 픽셀
    from core import color
    lt, la = color.srgb_to_lab(tb)[..., 0], color.srgb_to_lab(ab)[..., 0]
    # 둘레 색조 차는 글자마다 — 한 글자(투명 바탕 위) 뒤에만 codex 가 옅은 안개를 깔면 그 안개가 '빛'으로 붙었다 [실측 combat_hud_blade '오의 불가']
    glow = np.zeros((H, W), bool)
    tones = []
    for b in boxes:
        reg = _box_mask((H, W), [b["box"]], BOX_PAD)
        g_b = glyph & reg
        if not g_b.any():
            continue
        ring = _dilate(g_b, GLOW_R + 8) & ~_dilate(glyph, GLOW_R + 2) & ui
        tone = float(np.median((lt - la)[ring])) if ring.any() else 0.0
        tones.append(tone)
        glow |= _dilate(g_b, GLOW_R) & reg & ((lt - la) > tone + GLOW_L) & ~fringe
    tone = float(np.median(tones)) if tones else 0.0
    # 획 둘레(안티앨리어싱) — 단단한 면 위는 그대로, 반투명 · 빈 자리 위는 참고판 자기 바탕과 다른 픽셀만(다시 그린 안개의 2 px 고리가 '글자 빛'으로 재졌다
    # [실측 combat_hud_blade '2/4' · '오의 불가' — 띠 밝기 5.8 · 5.2 로 글자 맞춤이 없는 빛을 넣어 글자가 흐려짐])
    edge_ok = glyph | (a_a > SOLID_A) | (own_d > OWN_EDGE_D)
    paste = (_dilate(glyph, EDGE_R) & inbox & edge_ok) | glow
    rec.update(glyph_px=int(glyph.sum()), glow_px=int(glow.sum()), paste_px=int(paste.sum()), ring_tone_l=round(tone, 2))
    why = None
    if not boxes:
        why = "no text detected in the text reference"
    elif not glyph.any():
        why = "the text reference does not differ from the art inside its text boxes"
    elif rec["checks"]["outside_solid_big_frac"] > OUT_MAX or rec["checks"]["outside_far_new_frac"] > OUT_MAX:
        why = (f"the text reference changed the art outside the text boxes (big difference on solid art {rec['checks']['outside_solid_big_frac']}, "
               f"new pixels where the art is empty {rec['checks']['outside_far_new_frac']} > {OUT_MAX})")
    if why:
        rec["reason"] = why
        return a_col, a_a, (t_col, t_a), rec
    rec["used"] = True
    c_col = np.where(paste[..., None], t_col, a_col)
    c_a = np.where(paste, t_a, a_a)
    rec["paste"] = paste
    return c_col, c_a, (t_col, t_a), rec


def check_files(art_path, ref_path, *, detect=None) -> dict:
    """make_concept 용 — 두 PNG(원본 아트 크기로 맞춤)로 merge 검사만. → 기록(paste 마스크 뺌)."""
    from PIL import Image
    with Image.open(art_path) as im:
        art = np.asarray(im.convert("RGBA"), float)
        size = im.size
    with Image.open(ref_path) as im:
        has_a = "A" in im.getbands()
        ref = np.asarray(im.convert("RGBA").resize(size, Image.Resampling.LANCZOS), float)
    t_a = ref[..., 3] / 255.0 if has_a else art[..., 3] / 255.0
    _, _, _, rec = merge(art[..., :3], art[..., 3] / 255.0, ref[..., :3], t_a, detect=detect)
    rec.pop("paste", None)
    return rec
