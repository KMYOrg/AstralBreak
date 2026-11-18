"""외부 · 단색 입력 오프라인 비교 묶음 (1b 후속 L 다음 — 검증 틀) — 판 메우기 · 글자 맞춤 · 진단 규칙을 바꾼 뒤 **에디터 run 전에** 쓴다.
에디터 · LLM · codex 없음. 판 메우기 규칙 하나를 고칠 때마다 다른 입력 · 다른 글자에서 새 결함이 났다(L-1 · L-3 — 배너 '3' · 패널 '2/4' · 배지 'E' · 'T') —
그래서 고정 입력 묶음 전부를 같은 자리에서 새 · 옛으로 맞댄다. 측정 정의를 바꾸면 그 측정으로 잰 값도 바뀌므로 결함 목록만이 아니라 측정값 차도 본다.

입력마다(SET — 입력마다 대표 끝 run 하나):
  ① 오프라인 재진단(gen/diagnose — run 의 렌더 · 텍스처 그대로): 진단 규칙 변경을 본다. 결함 목록 · 글자 측정값 · 글자 구역 바탕 · 획에 붙은 잔상.
  ② refine 오프라인 재실행(replay_refine.replay — run 사본에서 specs/000.json 으로 refine 만 다시): 판 메우기 · 오리기 규칙 변경을 본다.
     회색 위 지표(replay_refine 그대로) + **글자 상자 안 텍스처 지표**(렌더 없이 텍스처 합성만 — 글자 구역 바탕 7 × 7 국소 ΔE00 · 획에 붙은 잔상
     `diagnose.glyph_residue(render=None)`) + 회색 위 합성 그림(gray.png — 비교 그림 재료).

  python regress_set.py list
  python regress_set.py run <label> [--out DIR] [--only 이름,…] [--no-replay] [--no-pictures]
  python regress_set.py compare <old_label> <new_label> [--out DIR] [--all-texts]

기본 출력 = work/_regress/(git 무시 — 입력 하나에 replay 사본 수십 MB). 기준선 <out>/<label>/<입력>/{diag/(diagnosis.json · compare.png), replay/<run>/,
gray.png, record.json} + <out>/<label>/set.json. 비교 = <out>/compare_<old>_vs_<new>/{report.txt, summary.json, <입력>.png(글자마다
컨셉 | 옛 텍스처 | 새 텍스처 | 차 — 텍스처가 바뀐 글자만, --all-texts 면 전부)}.
기준선 run 과 비교 run 은 같은 코드 기준(커밋 · 미커밋 차)을 report 머리에 적는다(git rev + diff 해시).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time

UIGEN = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(UIGEN))

import numpy as np  # noqa: E402

from core import config  # noqa: E402
from gen import backdrop  # noqa: E402
from gen import diagnose as dg  # noqa: E402

WORK = UIGEN / "work"
OUT = WORK / "_regress"
# 고정 입력 묶음 — 1b 후속 L 끝(11-18) 대표 run. 새 입력 · 더 나은 대표 run 이 생기면 여기만 바꾼다(기준선은 다시 잼)
SET = [
    {"name": "combat_l1", "run": "R20261118_184602_CombatHUD", "input": "원래 전투 HUD — L-1(fixtures/m4_combat_hud_concept, 글자 든 생성 컨셉)", "protect": True},
    {"name": "combat_l2", "run": "R20261118_191532_CombatHUD", "input": "원래 전투 HUD — L-2(fixtures/m4_combat_hud_l2, 원본 아트 + 글자 참고판)", "protect": True},
    {"name": "combat_flat_a", "run": "R20261118_120715_CombatHUD", "input": "단색 전투 HUD(fixtures/m4_combat_hud_flat) — '4' 밑 잔상 run"},
    {"name": "combat_flat_b", "run": "R20261118_124503_CombatHUD", "input": "단색 전투 HUD — '2/4' 금선 혹 · 위치 run"},
    {"name": "controls_alpha", "run": "R20261118_180405_ProbeControlGuide", "input": "조작 안내 진짜 알파(controls_alpha)", "protect": True},
    {"name": "controls", "run": "R20261118_125054_ProbeControlGuide", "input": "조작 안내(controls)", "protect": True},
    {"name": "controls_orig", "run": "R20261118_125624_ProbeControlGuide", "input": "조작 안내 원본(합성 스크린샷 → 변환, work/_probe/controls)"},
    {"name": "party", "run": "R20261118_130201_ProbePartyHUD", "input": "파티 HUD(합성 스크린샷 → 변환, work/_probe/party)"},
]
TEXT_FIELDS = ("h_ratio", "w_ratio", "center_d", "density_ratio", "color_de", "concept_contrast", "edge_d")
EPS = {"h_ratio": 0.005, "w_ratio": 0.005, "density_ratio": 0.01, "color_de": 0.5, "concept_contrast": 1.0, "edge_d": 0.5, "center_d": 0.5}
CROP_PAD = 10
CROP_SCALE = 3
TEX_CHANGED_DE = 1.0       # 글자 상자 안 옛 ↔ 새 텍스처 ΔE00 최대가 이보다 크면 '텍스처 바뀜' 그림


def _code_state() -> dict:
    """기준선이 어떤 코드로 잰 것인지 — HEAD 와 미커밋 변경(Tools/uigen — 추적 파일 diff + 미추적 .py · .yaml 내용) 해시."""
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=UIGEN, capture_output=True, text=True, timeout=20).stdout.strip()
        h = hashlib.sha1(subprocess.run(["git", "diff", "HEAD", "--", "."], cwd=UIGEN, capture_output=True, timeout=60).stdout)
        new = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "--", "."], cwd=UIGEN, capture_output=True, text=True,
                             timeout=60).stdout.split()
        new = sorted(p for p in new if p.endswith((".py", ".yaml")))
        for p in new:
            h.update(p.encode("utf-8") + (UIGEN / p).read_bytes())
        dirty = h.hexdigest()[:12] if h.digest() != hashlib.sha1(b"").digest() else None
        return {"head": rev, "dirty_sha1": dirty, "untracked_code": new}
    except Exception as exc:  # noqa: BLE001 — 기록만
        return {"error": str(exc)[:120]}


# ---------------------------------------------------------------------------------------------------------------------
# ① 오프라인 재진단

def _diag_record(rec: dict) -> dict:
    if rec.get("skipped"):
        return {"skipped": rec["skipped"]}
    sm = rec["summary"]
    texts = {}
    for t in rec.get("texts") or []:
        g = t.get("glow") or {}
        texts[t["widget"]] = {**{k: t.get(k) for k in TEXT_FIELDS if t.get(k) is not None}, "causes": t.get("causes") or [],
                              "approx": sorted({a["kind"] for a in t.get("approx") or []}),
                              "glow_peak": [(g.get("concept") or {}).get("peak"), (g.get("render") or {}).get("peak")] if g else None}
    return {"errors": sm["errors"], "approx": sm["approx"], "by_code": sm["by_code"], "badness": rec.get("badness"),
            "defects": [{k: d.get(k) for k in ("n", "code", "stage", "widgets", "box", "area", "max_de", "causes")} | {"cause": str(d.get("cause"))[:90]}
                        for d in rec.get("defects") or []],
            "texts": texts, "text_background": rec.get("text_background"),
            "text_residue": {k: {"px": v["px"], "max_de": v["max_de"], "blobs": len(v["blobs"])} for k, v in (rec.get("text_residue") or {}).items()},
            "maps": {k: (rec.get("maps") or {}).get(k) for k in ("black_local_max", "gray_local_max")}}


# ---------------------------------------------------------------------------------------------------------------------
# ② replay + 글자 상자 안 텍스처 지표

def _texture_metrics(dst: pathlib.Path, s: dict) -> tuple[dict, np.ndarray, dict]:
    """replay 사본(dst)의 텍스처로 — 렌더 없이 합성만. → (글자마다 지표, 회색 위 합성 HxWx3, 글자 상자)."""
    import cv2
    import replay_refine
    spec = json.loads((dst / "spec.json").read_text(encoding="utf-8"))
    canvas = [int(v) for v in (spec.get("canvas") or [1920, 1080])]
    W, H = canvas
    boxes = replay_refine.boxes_from_spec(spec)
    manifest = json.loads((dst / "manifest.json").read_text(encoding="utf-8"))
    textures = {a["asset_id"]: backdrop._load(dst / a["file"]) for a in manifest["assets"] if a.get("file") and (dst / a["file"]).is_file()}
    norm = json.loads((dst / "normalize.json").read_text(encoding="utf-8"))
    bg = norm.get("background") or {}
    ref_text = dg._load_rgb(dst / "reference_color.png") * dg._load_l(dst / "reference_alpha.png")[..., None]
    nt = bg.get("notext") or {}
    notext = dg._notext_cleared(dst, nt, spec) if nt.get("used") and (dst / str(nt.get("color"))).is_file() else None
    truth = ref_text
    art = bg.get("art") or {}
    if dg.art_mode(bg) and (dst / str(art.get("color"))).is_file():
        truth = dg._load_rgb(dst / art["color"]) * dg._load_l(dst / art["alpha"])[..., None]      # L-2 — 텍스처의 정답 = 원본 아트
    comp, cov, _ = backdrop.compose(spec, boxes, textures, canvas, (0, 0, 0))
    not_drawn, _ = dg.hidden_state_split(spec, boxes, textures, canvas, truth, comp, comp, cov, ref_text=ref_text, notext_black=notext)
    sp = dg._without(spec, not_drawn) if not_drawn else spec
    comp_s = backdrop.compose(sp, boxes, textures, canvas, (0, 0, 0))[0] if not_drawn else comp
    gray = backdrop.compose(sp, boxes, textures, canvas, backdrop.GRAY)[0]
    geo = {b["id"]: b for b in boxes}
    texts = [w for w in spec.get("widgets", []) if w.get("type") in backdrop.TEXT_TYPES and w["id"] not in not_drawn and w.get("bbox_intent")]
    gm = dg.text_glyph_masks(ref_text, comp_s, comp_s, texts, geo, notext, render_bg=comp_s, notext_skip=dg.notext_unused(dst), color_gate=dg.art_mode(bg))
    residue = dg.glyph_residue(ref_text, comp_s, gm, texts, notext, render=None, de_min=float(s["residue_de"]), min_px=int(s["residue_min_px"]))
    eff_bg = notext if notext is not None else comp_s
    brighter = (dg.color.srgb_to_lab(ref_text)[..., 0] - dg.color.srgb_to_lab(eff_bg)[..., 0]) > 4.0
    attached = dg.maxabs(ref_text, eff_bg) > dg.INK_FLOOR
    strokes = np.zeros((H, W), bool)
    for w in texts:
        v = gm[w["id"]]
        gl = float(((w.get("font") or {}).get("glow") or {}).get("size") or 0) if isinstance(w.get("font"), dict) else 0.0
        strokes |= v["concept_cand"] | v["concept"] | (dg._dilate(v["concept"], 4) & attached)
        if gl:
            strokes |= dg._dilate(v["concept"], int(round(gl))) | (dg._dilate(v["concept"], dg.GLOW_MAXD) & brighter)
    strokes = dg._dilate(strokes, 2)
    de = dg.delta_e(comp_s, truth)
    T = float(s["local_de"])
    out, crops = {}, {}
    for w in texts:
        f = w.get("font") if isinstance(w.get("font"), dict) else {}
        gl = float((f.get("glow") or {}).get("size") or 0)
        zone = dg._box_mask((H, W), w["bbox_intent"], dg.TEXT_ZONE_PAD + gl) & ~strokes
        bb = dg._bbox(dg._box_mask((H, W), w["bbox_intent"], CROP_PAD + gl))
        crops[w["id"]] = bb
        r = residue.get(w["id"]) or {}
        row = {"residue_px": r.get("px", 0), "residue_max_de": r.get("max_de", 0.0), "residue_blobs": len(r.get("blobs") or [])}
        if zone.any():
            cover = cv2.blur(zone.astype(np.float32), (dg.WIN, dg.WIN))
            loc = np.where(cover >= float(s["bg_cover"]), cv2.blur((de * zone).astype(np.float32), (dg.WIN, dg.WIN)) / np.maximum(cover, 1e-6), 0.0)
            z = zone & (cover >= float(s["bg_cover"]))
            if z.any():
                row.update(bg_local_max=round(float(loc[z].max()), 2), bg_local_p95=round(float(np.percentile(loc[z], 95)), 2),
                           bg_over_px=int((loc[z] > T).sum()))
        out[w["id"]] = row
    return out, gray, crops


def run_set(label: str, out: pathlib.Path, only: set | None, replay: bool, pictures: bool) -> dict:
    import replay_refine
    cfg = config.load_pipeline()
    s = dg.settings(cfg)
    base = out / label
    if base.exists() and any(base.iterdir()):
        raise SystemExit(f"regress_set: {base} already has files — use a new label")
    base.mkdir(parents=True, exist_ok=True)
    meta = {"label": label, "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "code": _code_state(), "entries": []}
    for e in SET:
        if only and e["name"] not in only:
            continue
        src = WORK / e["run"]
        if not src.is_dir():
            print(f"!! {e['name']}: run missing {src}", flush=True)
            meta["entries"].append({**e, "missing": True})
            continue
        ed = base / e["name"]
        t0 = time.time()
        rec = dg.diagnose(src, ed / "diag" if pictures else None, cfg, pictures=pictures)
        row = {**e, "diag": _diag_record(rec)}
        if replay:
            try:
                rr = replay_refine.replay(src, ed / "replay", False, False)
                tm, gray, crops = _texture_metrics(ed / "replay" / src.name, s)
                from PIL import Image
                Image.fromarray(np.clip(gray, 0, 255).round().astype(np.uint8)).save(ed / "gray.png")
                row["replay"] = {k: rr.get(k) for k in ("gray_de00_mean", "gray_de00_p95", "alpha_mae", "cliffs_compose_only", "holes", "doubles", "missing")}
                row["replay"]["zoom_dark_px"] = (rr.get("zoom_seams") or {}).get("dark_px")
                row["text_texture"] = tm
                row["crops"] = crops
            except Exception as exc:  # noqa: BLE001 — 한 입력 실패가 묶음을 멈추지 않게(기록)
                row["replay_error"] = f"{type(exc).__name__}: {exc}"[:300]
        (ed / "record.json").write_text(json.dumps(row, ensure_ascii=False, indent=1, default=float) + "\n", encoding="utf-8")
        meta["entries"].append({k: row[k] for k in ("name", "run", "input") if k in row})
        d = row["diag"]
        res_px = sum(v.get("residue_px", 0) for v in (row.get("text_texture") or {}).values())
        print(f"== {e['name']:<15} {e['run']}  errors {d.get('errors')} {d.get('by_code')}  approx {d.get('approx')}  "
              f"replay gray {(row.get('replay') or {}).get('gray_de00_mean')}  tex residue px {res_px}  ({time.time() - t0:.0f}s)"
              + (f"  REPLAY ERROR {row['replay_error']}" if row.get("replay_error") else ""), flush=True)
    (base / "set.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return meta


# ---------------------------------------------------------------------------------------------------------------------
# 비교

def _overlap(a, b) -> bool:
    return bool(a and b) and a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def _same_defect(a: dict, b: dict) -> bool:
    return a.get("code") == b.get("code") and bool(set(a.get("widgets") or []) & set(b.get("widgets") or []) or not (a.get("widgets") or b.get("widgets"))) \
        and (_overlap(a.get("box"), b.get("box")) or a.get("stage") == "text")


def diff_defects(old: list[dict], new: list[dict]) -> dict:
    """결함 목록 새 · 사라짐 · 남음 — 같은 오류 번호 · 위젯이 겹치고 상자가 겹치면(글자 결함은 위젯만) 같은 결함."""
    used, kept, gone = set(), [], []
    for o in old:
        j = next((j for j, n in enumerate(new) if j not in used and _same_defect(o, n)), None)
        if j is None:
            gone.append(o)
        else:
            used.add(j)
            kept.append((o, new[j]))
    return {"new": [n for j, n in enumerate(new) if j not in used], "gone": gone, "kept": kept}


def _num_diff(a, b, eps: float) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return len(a) != len(b) or any(_num_diff(x, y, eps) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) > eps
    return a != b


def compare(old_label: str, new_label: str, out: pathlib.Path, all_texts: bool = False) -> dict:
    from PIL import Image
    od, nd = out / old_label, out / new_label
    cd = out / f"compare_{old_label}_vs_{new_label}"
    cd.mkdir(parents=True, exist_ok=True)
    om, nm = (json.loads((d / "set.json").read_text(encoding="utf-8")) for d in (od, nd))
    lines = [f"old {old_label} code {om.get('code')}  ·  new {new_label} code {nm.get('code')}"]
    summ = {"old": old_label, "new": new_label, "entries": []}
    for e in SET:
        po, pn = od / e["name"] / "record.json", nd / e["name"] / "record.json"
        if not (po.is_file() and pn.is_file()):
            continue
        ro, rn = (json.loads(p.read_text(encoding="utf-8")) for p in (po, pn))
        do, dn = ro["diag"], rn["diag"]
        ent = {"name": e["name"], "run": e["run"], "errors": [do.get("errors"), dn.get("errors")], "approx": [do.get("approx"), dn.get("approx")]}
        lines.append("")
        lines.append(f"== {e['name']} ({e['run']}) — errors {do.get('errors')} → {dn.get('errors')} · approx {do.get('approx')} → {dn.get('approx')}"
                     f" · by_code {do.get('by_code')} → {dn.get('by_code')}" + ("   [protected — must stay 0]" if e.get("protect") else ""))
        if e.get("protect") and dn.get("errors"):
            lines.append("   !! protected run has errors now")
            ent["protected_broken"] = True
        dd = diff_defects(do.get("defects") or [], dn.get("defects") or [])
        for tag, rows in (("+ new ", dd["new"]), ("- gone", dd["gone"])):
            for d in rows:
                lines.append(f"   {tag} {d.get('code')} {d.get('stage'):<9} {','.join(d.get('widgets') or [])[:40]:<40} box {d.get('box')} max {d.get('max_de')}  {d.get('cause')}")
        ent["defects_new"], ent["defects_gone"] = len(dd["new"]), len(dd["gone"])
        # 글자 측정값 차
        tch = []
        for wid in sorted(set(do.get("texts") or {}) | set(dn.get("texts") or {})):
            a, b = (do.get("texts") or {}).get(wid) or {}, (dn.get("texts") or {}).get(wid) or {}
            ch = {k: [a.get(k), b.get(k)] for k in set(TEXT_FIELDS) | {"causes", "approx", "glow_peak"}
                  if _num_diff(a.get(k), b.get(k), EPS.get(k, 0.5))}
            if ch:
                tch.append(wid)
                lines.append(f"   ~ text {wid:<22} " + "  ".join(f"{k} {v[0]} → {v[1]}" for k, v in sorted(ch.items())))
        for k in ("text_background", "maps"):
            if (do.get(k) or {}) != (dn.get(k) or {}):
                lines.append(f"   ~ {k} {do.get(k)} → {dn.get(k)}")
        for wid in sorted(set(do.get("text_residue") or {}) | set(dn.get("text_residue") or {})):
            a, b = (do.get("text_residue") or {}).get(wid), (dn.get("text_residue") or {}).get(wid)
            if a != b:
                lines.append(f"   ~ residue {wid:<20} {a} → {b}")
        ent["texts_changed"] = tch
        # replay 지표 · 글자 상자 안 텍스처
        if ro.get("replay") and rn.get("replay"):
            ch = {k: [ro["replay"].get(k), rn["replay"].get(k)] for k in rn["replay"] if _num_diff(ro["replay"].get(k), rn["replay"].get(k), 1e-3)}
            if ch:
                lines.append("   ~ replay " + "  ".join(f"{k} {v[0]} → {v[1]}" for k, v in ch.items()))
            tt_o, tt_n = ro.get("text_texture") or {}, rn.get("text_texture") or {}
            for wid in sorted(set(tt_o) | set(tt_n)):
                a, b = tt_o.get(wid) or {}, tt_n.get(wid) or {}
                ch = {k: [a.get(k), b.get(k)] for k in set(a) | set(b) if _num_diff(a.get(k), b.get(k), 0.05)}
                if ch:
                    lines.append(f"   ~ texture {wid:<19} " + "  ".join(f"{k} {v[0]} → {v[1]}" for k, v in sorted(ch.items())))
            # 그림 — 글자 상자마다 컨셉(회색 위) | 옛 텍스처 | 새 텍스처 | 차(ΔE00 × 8)
            go, gn = od / e["name"] / "gray.png", nd / e["name"] / "gray.png"
            if go.is_file() and gn.is_file():
                src = WORK / e["run"]
                rc, ra = dg._load_rgb(src / "reference_color.png"), dg._load_l(src / "reference_alpha.png")
                cg = rc * ra[..., None] + np.asarray(backdrop.GRAY, float) * (1 - ra[..., None])
                a_img, b_img = dg._load_rgb(go), dg._load_rgb(gn)
                rows, changed = [], {}
                for wid, bb in sorted((rn.get("crops") or {}).items()):
                    x, y, w, h = bb
                    tile = [im[y:y + h, x:x + w] for im in (cg, a_img, b_img)]
                    dmap = dg.delta_e(tile[1], tile[2])
                    mx = float(dmap.max()) if dmap.size else 0.0
                    if mx > TEX_CHANGED_DE:
                        changed[wid] = round(mx, 1)
                    if mx <= TEX_CHANGED_DE and not all_texts:
                        continue
                    heat = np.stack([np.clip(dmap * 8, 0, 255)] * 3, -1)
                    row = np.concatenate([np.pad(np.clip(t, 0, 255), ((0, 2), (0, 2), (0, 0)), constant_values=255) for t in tile + [heat]], axis=1)
                    rows.append(row)
                ent["texture_changed"] = changed
                if changed:
                    lines.append(f"   ~ texture picture: changed text boxes {changed} (max ΔE00 old ↔ new)")
                if rows:
                    wmax = max(r_.shape[1] for r_ in rows)
                    sheet = np.concatenate([np.pad(r_, ((0, 4), (0, wmax - r_.shape[1]), (0, 0)), constant_values=255) for r_ in rows], axis=0)
                    sheet = sheet.round().astype(np.uint8)
                    Image.fromarray(sheet).resize((sheet.shape[1] * CROP_SCALE, sheet.shape[0] * CROP_SCALE), Image.Resampling.NEAREST).save(cd / f"{e['name']}.png")
        summ["entries"].append(ent)
    text = "\n".join(lines) + "\n"
    (cd / "report.txt").write_text(text, encoding="utf-8")
    (cd / "summary.json").write_text(json.dumps(summ, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(text)
    return summ


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="offline regression set — re-diagnose + refine replay of fixed inputs, baseline and compare")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    r = sub.add_parser("run")
    r.add_argument("label")
    r.add_argument("--out", default=str(OUT))
    r.add_argument("--only", default="")
    r.add_argument("--no-replay", action="store_true")
    r.add_argument("--no-pictures", action="store_true")
    c = sub.add_parser("compare")
    c.add_argument("old")
    c.add_argument("new")
    c.add_argument("--out", default=str(OUT))
    c.add_argument("--all-texts", action="store_true")
    o = ap.parse_args(argv)
    if o.cmd == "list":
        for e in SET:
            print(f"{e['name']:<15} {e['run']:<36} {'protected ' if e.get('protect') else ''}{e['input']}")
    elif o.cmd == "run":
        run_set(o.label, pathlib.Path(o.out), set(filter(None, o.only.split(","))) or None, not o.no_replay, not o.no_pictures)
    else:
        compare(o.old, o.new, pathlib.Path(o.out), o.all_texts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
