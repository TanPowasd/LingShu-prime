"""HARD 榜计分（规则 hard-rules-v1，先于 r1 读数固定；参考值 = 理想上限，而不是任何现有实现）。

各维 0–100；总分 = Σ w·维分 / Σ w（缺席的可选维不进分母，并在报告中注明）。
主榜 = seed 0；seed 1 为防过拟合复核，单列总分。
"""
import datetime
import json
import math
import os

from dims.metrics import logscore, mean

WEIGHTS = {"scale": 15, "retrieval": 20, "dedup": 15, "robust": 10, "meta": 10, "causal": 10, "stability": 5, "world": 15,
           "hmb": 10, "llm": 5}
OPTIONAL = ("hmb", "llm")
NAMES = {"scale": "规模", "retrieval": "检索质量", "dedup": "去重/新奇门控", "robust": "对抗与边界", "meta": "变形一致",
         "causal": "因果图", "stability": "长期稳定", "world": "世界/生成/网络", "hmb": "HMB 作者基准", "llm": "LLM 判官（作答充分性）"}
SIZES = (1000, 10000, 50000, 200000)
# 规模格的理想上限 / 零分点（越小越好；对数插值）
SCALE_REF = {
    "build_us_per_add": lambda n: (10, 10000),
    "edge_us": lambda n: (10, 10000),
    "add_ms": lambda n: (0.03, 30),
    "recall_ms": lambda n: (0.1, 1000),
    "decay_ms": lambda n: (n * 1e-4, n * 1e-1),
    "self_check_ms": lambda n: (1, 10000),
    "reopen_ms": lambda n: (2, 20000),
    "maxrss_mb": lambda n: (30 + n * 5e-4, (30 + n * 5e-4) * 30),
}


REPS = 3          # 计时作业重复次数（r3 起：三方同轮交替执行，逐指标取中位数）


def _median_merge(rs):
    """同一作业多次重复的读数逐叶合并：数值取中位数（缺失/None 视为 +inf，即「没测出来」），布尔取多数，其余取首份。"""
    import statistics
    rs = [r for r in rs if r is not None]
    if not rs:
        return None
    if len(rs) == 1:
        return rs[0]
    if all(isinstance(r, dict) for r in rs):
        keys = []
        for r in rs:
            keys += [k for k in r if k not in keys]
        return {k: _median_merge([r.get(k) for r in rs]) if all(isinstance(r.get(k), dict) or r.get(k) is None for r in rs) and any(isinstance(r.get(k), dict) for r in rs)
                else _leaf([r.get(k) for r in rs]) for k in keys}
    return _leaf(rs)


def _leaf(vs):
    import statistics
    nums = [v for v in vs if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if nums and len(nums) + sum(v is None for v in vs) == len(vs):
        xs = sorted([float(v) for v in nums] + [math.inf] * (len(vs) - len(nums)))
        m = statistics.median(xs)
        return None if not math.isfinite(m) else (round(m, 4) if isinstance(m, float) else m)
    if vs and all(isinstance(v, bool) for v in vs):
        return sum(vs) * 2 > len(vs)
    return next((v for v in vs if v is not None), None)


def _load(cdir, key):
    """读作业缓存；存在重复读数（<key>.r1.json、<key>.r2.json）时逐指标取中位数，status 取多数。"""
    p = os.path.join(cdir, key + ".json")
    reps = [p] + [os.path.join(cdir, f"{key}.r{i}.json") for i in range(1, REPS)]
    got = [json.load(open(q)) for q in reps if os.path.exists(q)]
    if not got:
        return None
    if len(got) == 1:
        return got[0]
    sts = [g.get("status") for g in got]
    st = max(set(sts), key=sts.count)
    raw = _median_merge([g.get("raw") for g in got])
    return {"status": st, "raw": raw, "reps": len(got), "rep_status": sts}


def _raw(r):
    if r is None:
        return None
    return r.get("raw")


def s_retrieval(cdir, sd):
    per, raw = [], {}
    for n in (1000, 10000, 50000):
        r = _raw(_load(cdir, f"retrieval_{n}_s{sd}"))
        if not r or str(n) not in r:
            per.append(0.0)
            continue
        a = r[str(n)]["all"]
        per.append(mean([a["recall@10"], a["mrr"], a["ndcg@10"]]))
        raw[n] = r[str(n)]
    return 100 * mean(per), raw


def s_dedup(cdir, sd):
    r = _raw(_load(cdir, f"dedup_s{sd}"))
    if not r:
        return 0.0, None
    f1 = mean(v["f1"] for v in r["dedup"].values())
    nov = mean(max(0.0, (v["balanced_acc"] - 0.5) / 0.5) for v in r["novelty"].values())
    return 100 * (0.5 * f1 + 0.5 * nov), r


ROBUST_CASES = ("unicode", "empty", "long", "numeric", "sqlish", "threads", "crash", "roundtrip", "stress")


def s_robust(cdir, sd):
    """每个用例组一个作业；组超时/崩溃 → 该组按其用例数（取自任一快照的完整读数，缺则按 1）全记失败。"""
    checks, notes, status = {}, {}, {}
    for c in ROBUST_CASES:
        res = _load(cdir, f"robust_{c}_s{sd}")
        status[c] = (res or {}).get("status")
        r = _raw(res)
        if r:
            checks.update(r["checks"])
            notes.update(r.get("notes", {}))
        else:
            checks[f"{c}:job_{status[c] or 'missing'}"] = False
    passed = sum(checks.values())
    return 100 * passed / len(checks), {"checks": checks, "passed": passed, "total": len(checks), "notes": notes, "status": status}


def s_meta(cdir, sd):
    r = _raw(_load(cdir, f"meta_s{sd}"))
    if not r:
        return 0.0, None
    return 100 * mean(r[k] for k in r["score_inputs"]), r


def s_causal(cdir, sd):
    a = _raw(_load(cdir, f"causal_small_s{sd}"))
    b = _raw(_load(cdir, f"causal_big_s{sd}"))
    sa = mean([a["paths"]["f1"], a["has_cycle_acc"], a["cycle_nodes_jaccard"]]) if a else 0.0
    sb = mean([logscore(b.get("big_has_cycle_ms"), 5, 5000), logscore(b.get("big_reason_ms"), 10, 60000)]) if b else 0.0
    return 100 * (0.6 * sa + 0.4 * sb), {"small": a, "big": b}


def s_stability(cdir, sd):
    fr, last = [], None
    for c in range(5):
        r = _raw(_load(cdir, f"stability_c{c}_s{sd}"))
        if not r:
            fr.append(0.0)
            continue
        inv = r["invariants"]
        fr.append(sum(inv.values()) / len(inv))
        last = r
    drift = 0.0
    if last and last.get("lat_by_chunk", {}).get("0") and last["lat_by_chunk"].get("4"):
        drift = logscore(last["lat_by_chunk"]["4"] / last["lat_by_chunk"]["0"], 1.2, 10)
    return 100 * (0.8 * mean(fr) + 0.2 * drift), {"invariant_pass_by_chunk": fr, "last": last, "drift_score": drift}


def s_scale(cdir, sd):
    cells, raw = [], {}
    for n in SIZES:
        res = _load(cdir, f"scale_{n}_s{sd}")
        r = (res or {}).get("raw") or {}
        raw[n] = dict(r, status=(res or {}).get("status"))
        for k, ref in SCALE_REF.items():
            ideal, zero = ref(n)
            cells.append(logscore(r.get(k), ideal, zero))
        cells.append(float(r.get("needle_found@10") or 0.0))
        cells.append(float(r.get("dedup_far_merge") or 0.0))
    return 100 * mean(cells), raw


def s_world(cdir, sd):
    raw, parts = {}, []
    h = _raw(_load(cdir, f"world_hexgen_s{sd}"))
    parts.append(mean([h["compile_acc"], h["pixel_acc"], h["transform_acc"], h["resolution_acc"]]) if h else 0.0)
    s = _raw(_load(cdir, f"world_scene_s{sd}"))
    parts.append(0.8 * mean(s[k] for k in ("speed_bound", "in_bounds", "finite", "deterministic", "seek_converge", "follow_visits"))
                 + 0.2 * logscore(s["us_per_entity_tick"], 0.2, 200) if s else 0.0)
    t = _raw(_load(cdir, f"world_stcnn_s{sd}"))
    parts.append(mean(t.values()) if t else 0.0)
    nn = _raw(_load(cdir, f"world_nn_s{sd}"))
    parts.append(0.8 * max(0.0, (nn["test_acc"] - 0.25) / 0.75) + 0.2 * logscore(nn["train_s"], 2, 600) if nn else 0.0)
    raw = {"hexgen": h, "scene": s, "stcnn": t, "nn": nn, "part_scores": [round(x, 4) for x in parts]}
    return 100 * mean(parts), raw


_HMB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evalsuite_hmb", "out")


def _hmb_path():
    """优先最新一版快照读数：hmb_r<N>.json 取 N 最大者（另一子代理维护，只读）。"""
    import re
    best, bn = os.path.join(_HMB_DIR, "hmb_r1.json"), 1
    if os.path.isdir(_HMB_DIR):
        for f in os.listdir(_HMB_DIR):
            mm = re.fullmatch(r"hmb_r(\d+)\.json", f)
            if mm and int(mm.group(1)) > bn and _hmb_has_zero_llm_track(os.path.join(_HMB_DIR, f)):
                best, bn = os.path.join(_HMB_DIR, f), int(mm.group(1))
    return best


def _hmb_has_zero_llm_track(path):
    """只采用带零 LLM 检索轨读数（results.<臂>.cid_recall）的版本。hmb_r2.json 是 LLM 判官五臂读数（另一套键），
    直接套 HMB_METRICS 会让三方 HMB 维全为 0（r3 首次 render 实测），故跳过。"""
    try:
        res = (json.load(open(path)).get("results") or {})
    except (OSError, ValueError):
        return False
    return any(isinstance(v, dict) and "cid_recall" in v for v in res.values())


HMB_PATH = _hmb_path()


def s_hmb(snap_name):
    """evalsuite_hmb（另一子代理维护，只读）。结构 {snapshot:{metric:value}} + 参考上限；
    维分 = mean(min(1, value / 参考上限))，参考上限优先取 BM25 / 作者 O 参照（文件内给出）。文件缺席 → None（不计入）。"""
    if not os.path.exists(HMB_PATH):
        return None, None
    try:
        d = json.load(open(HMB_PATH))
    except Exception:
        return None, None
    return hmb_score(d, snap_name)


HMB_METRICS = [  # (指标, 方向, 参考上限来源) —— 上限优先取作者 O 参照，其次理想值，延迟类以 BM25 为理想
    ("cid_recall", "ratio", "O_fullbook"),
    ("quote_recall", "ratio", "O_fullbook"),
    ("point_keyword_cov", "ratio", "O_fullbook"),
    ("must_exclude_mix", "lower01", None),
    ("pairs_all.both_n8", "frac_of:pairs_all.total", None),
    ("pairs_hard9.b_side_n8", "frac_of_const:9", None),
    ("store_verbatim_strict", "ratio_ideal1", None),
    ("retire.leak_prod_path", "leak", None),
    ("query_ms_median_novel", "log:bm25x1000", "bm25"),
    ("write_ms_per_chunk_novel", "log:bm25x1000", "bm25"),
]


def hmb_score(d, snap_name):
    # ng 优先取 ng_head 臂（evalsuite_hmb 对 rewrite/ng 最新快照的读数；其快照提交见 meta.snapshots.ng_head），
    # 没有时回落 ng 臂。报告注明所用臂与其快照，HMB 维不随 HARD 各轮的 ng 改动重测（另一子代理维护）。
    arm = snap_name
    if snap_name == "ng" and isinstance((d.get("results") or {}).get("ng_head"), dict):
        arm = "ng_head"
    res = (d.get("results") or {}).get(arm)
    if not isinstance(res, dict):
        return None, None
    ref = d.get("reference") or {}
    bm = (d.get("results") or {}).get("bm25") or {}
    parts = {}
    for k, how, src in HMB_METRICS:
        v = res.get(k)
        try:
            if how == "ratio":
                cap = (ref.get(k) or {}).get(src) or (ref.get(k) or {}).get("bm25")
                sc = min(1.0, float(v) / float(cap))
            elif how == "lower01":
                sc = max(0.0, 1.0 - float(v))
            elif how.startswith("frac_of:"):
                sc = float(v) / max(1.0, float(res.get(how.split(":", 1)[1])))
            elif how.startswith("frac_of_const:"):
                sc = float(v) / float(how.split(":", 1)[1])
            elif how == "ratio_ideal1":
                sc = min(1.0, float(v))
            elif how == "leak":
                a, b = str(v).split("/")
                sc = 1.0 - float(a) / float(b)
            elif how.startswith("log:"):
                ideal = float(bm.get(k))
                sc = logscore(float(v), ideal, ideal * 1000)
            else:
                sc = 0.0
        except Exception:
            sc = 0.0
        parts[k] = round(sc, 4)
    return 100 * mean(parts.values()), {"part_scores": parts, "hmb_arm": arm,
                                        "hmb_arm_snapshot": ((d.get("meta") or {}).get("snapshots") or {}).get(arm),
                                        "hmb_meta": d.get("meta")}


def s_llm(cdir, sd):
    r = _load(cdir, f"llm_s{sd}")
    if not r or r.get("status") != "OK" or r["raw"].get("score") is None:
        return None, None
    return r["raw"]["score"], r["raw"]


DIMS = {"scale": s_scale, "retrieval": s_retrieval, "dedup": s_dedup, "robust": s_robust, "meta": s_meta,
        "causal": s_causal, "stability": s_stability, "world": s_world}


def compute(rdir, snaps):
    res = {}
    for sn in snaps:
        cdir = os.path.join(rdir, sn["name"])
        res[sn["name"]] = {}
        for sd in (0, 1):
            dims, raw = {}, {}
            for k, fn in DIMS.items():
                sc, rw = fn(cdir, sd)
                dims[k], raw[k] = round(sc, 2), rw
            hs, hr = s_hmb(sn["name"])
            if hs is not None:
                dims["hmb"], raw["hmb"] = round(hs, 2), hr
            ls, lr = s_llm(cdir, sd)
            if ls is not None:
                dims["llm"], raw["llm"] = round(ls, 2), lr
            wsum = sum(WEIGHTS[k] for k in dims)
            total = sum(WEIGHTS[k] * v for k, v in dims.items()) / wsum
            res[sn["name"]][f"s{sd}"] = {"total": round(total, 2), "dims": dims, "raw": raw}
    return res


def render(run, snaps, rdir, log_md=None):
    res = compute(rdir, snaps)
    out = {"run": run, "rules": "hard-rules-v1", "generated": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
           "weights": WEIGHTS, "snapshots": snaps, "results": res}
    here = os.path.dirname(os.path.abspath(__file__))
    json.dump(out, open(os.path.join(here, "out", f"hard_{run}.json"), "w"), ensure_ascii=False, indent=1, default=str)
    md = _md(out)
    lb = os.path.join(here, "LEADERBOARD_HARD.md")
    tail = ""
    if os.path.exists(lb):
        txt = open(lb, encoding="utf-8").read()
        i = txt.find("## 迭代日志")
        if i >= 0:
            tail = txt[i:]
    if not tail:
        tail = "## 迭代日志\n\n（每轮：改了什么 → 重跑维度 → 分数变化。）\n"
    open(lb, "w", encoding="utf-8").write(md + "\n" + tail)
    for name, r in res.items():
        print(name, "s0", r["s0"]["total"], r["s0"]["dims"], "| s1", r["s1"]["total"])


def _md(out):
    res, snaps = out["results"], out["snapshots"]
    L = [f"# 灵枢 HARD 榜（{out['run']}）", "",
         f"生成：{out['generated']}（Asia/Shanghai）· 规则 {out['rules']}（参考值=理想上限，见 README.md / score.py）", "",
         "## 参评快照", "", "| 快照 | 实现 | 来源 | 提交 |", "|---|---|---|---|"]
    for s in snaps:
        L.append(f"| {s['name']} | {s['impl']} | `{s['path']}` | `{s['rev'][:10]}` |")
    dims = [k for k in WEIGHTS if any(k in res[s['name']]['s0']['dims'] for s in snaps)]
    L += ["", "## 总榜（seed 0 主榜；seed 1 复核）", "",
          "| 快照 | 总分 s0 | 总分 s1 | " + " | ".join(f"{NAMES[k]}({WEIGHTS[k]})" for k in dims) + " |",
          "|---|---|---|" + "---|" * len(dims)]
    for s in snaps:
        r = res[s["name"]]
        L.append(f"| {s['name']} | **{r['s0']['total']}** | {r['s1']['total']} | " +
                 " | ".join(f"{r['s0']['dims'].get(k, '—')} / {r['s1']['dims'].get(k, '—')}" for k in dims) + " |")
    names = [s["name"] for s in snaps]
    if "ng" in names and "integrated" in names:
        for sd in ("s0", "s1"):
            a, b = res["ng"][sd]["total"], res["integrated"][sd]["total"]
            L.append(f"\nng / integrated（{sd}）= **{a / b:.2f}×**" if b else "")
    missing = [NAMES[k] for k in OPTIONAL if k not in dims]
    if missing:
        L.append(f"\n可选维度缺席（不进分母）：{'、'.join(missing)}。")
    L += ["", "## 原始指标（seed 0）", ""]
    L += _raw_tables(res, snaps)
    return "\n".join(L) + "\n"


def _g(d, *ks):
    for k in ks:
        if d is None:
            return "—"
        d = d.get(k) if isinstance(d, dict) else None
    return "—" if d is None else d


def _raw_tables(res, snaps):
    L = []
    nm = [s["name"] for s in snaps]
    R = {n: res[n]["s0"]["raw"] for n in nm}
    L += ["### 规模（原始耗时 / 内存）", "", "| N | 指标 | " + " | ".join(nm) + " |", "|---|---|" + "---|" * len(nm)]
    for n in SIZES:
        for k in list(SCALE_REF) + ["needle_found@10", "dedup_far_merge", "status"]:
            L.append(f"| {n} | {k} | " + " | ".join(str(_g(R[x]['scale'], n, k)) for x in nm) + " |")
    L += ["", "### 检索质量（recall@10 / MRR / nDCG@10，all 与分类型）", "", "| N | 类型 | " + " | ".join(nm) + " |", "|---|---|" + "---|" * len(nm)]
    for n in (1000, 10000, 50000):
        for t in ("all", "ea", "noisy", "rev", "ent", "pair", "upd"):
            L.append(f"| {n} | {t} | " + " | ".join(
                "/".join(str(_g(R[x]['retrieval'], n, t, m)) for m in ("recall@10", "mrr", "ndcg@10")) for x in nm) + " |")
    L += ["", "### 去重 F1 / 新奇门控 balanced acc", "", "| 项 | " + " | ".join(nm) + " |", "|---|" + "---|" * len(nm)]
    for M in ("300", "3000"):
        L.append(f"| dedup M={M} P/R/F1 | " + " | ".join(
            f"{_g(R[x]['dedup'], 'dedup', M, 'precision')}/{_g(R[x]['dedup'], 'dedup', M, 'recall')}/{_g(R[x]['dedup'], 'dedup', M, 'f1')}" for x in nm) + " |")
        L.append(f"| dedup M={M} 分类正确 | " + " | ".join(str(_g(R[x]['dedup'], 'dedup', M, 'by_kind_correct')).replace("|", "/") for x in nm) + " |")
    for K in ("200", "2000"):
        L.append(f"| novelty K={K} bacc (TPR/TNR) | " + " | ".join(
            f"{_g(R[x]['dedup'], 'novelty', K, 'balanced_acc')} ({_g(R[x]['dedup'], 'novelty', K, 'tpr')}/{_g(R[x]['dedup'], 'novelty', K, 'tnr')})" for x in nm) + " |")
        L.append(f"| novelty K={K} 分类正确 | " + " | ".join(str(_g(R[x]['dedup'], 'novelty', K, 'by_kind_correct')) for x in nm) + " |")
    L += ["", "### 对抗与边界（失败用例）", ""]
    for x in nm:
        r = R[x]["robust"]
        if r:
            fails = [k for k, v in r["checks"].items() if not v]
            L.append(f"- **{x}**：{r['passed']}/{r['total']}；失败：{', '.join(fails) or '无'}")
    L += ["", "### 变形一致", "", "| 项 | " + " | ".join(nm) + " |", "|---|" + "---|" * len(nm)]
    keys = (R[nm[0]]["meta"] or {}).get("score_inputs") or []
    for k in keys:
        L.append(f"| {k} | " + " | ".join(str(_g(R[x]['meta'], k)) for x in nm) + " |")
    L += ["", "### 因果图", "", "| 项 | " + " | ".join(nm) + " |", "|---|" + "---|" * len(nm)]
    for k in (("small", "paths", "f1"), ("small", "has_cycle_acc"), ("small", "cycle_nodes_jaccard"), ("big", "big_has_cycle_ms"), ("big", "big_reason_ms")):
        L.append(f"| {'.'.join(k)} | " + " | ".join(str(_g(R[x]['causal'], *k)) for x in nm) + " |")
    L += ["", "### 长期稳定（10 万次操作）", "", "| 项 | " + " | ".join(nm) + " |", "|---|" + "---|" * len(nm)]
    L.append("| 每段不变量通过率 | " + " | ".join(str([round(v, 2) for v in _g(R[x]['stability'], 'invariant_pass_by_chunk')]) if R[x]['stability'] else '—' for x in nm) + " |")
    L.append("| 末段失败不变量 | " + " | ".join(str([k for k, v in (_g(R[x]['stability'], 'last', 'invariants') or {}).items() if not v] if isinstance(_g(R[x]['stability'], 'last', 'invariants'), dict) else '—') for x in nm) + " |")
    L.append("| 写入 p50 ms 按段 | " + " | ".join(str({k: round(v, 3) for k, v in (_g(R[x]['stability'], 'last', 'lat_by_chunk') or {}).items()} if isinstance(_g(R[x]['stability'], 'last', 'lat_by_chunk'), dict) else '—') for x in nm) + " |")
    L += ["", "### 世界 / 生成 / 网络", "", "| 项 | " + " | ".join(nm) + " |", "|---|" + "---|" * len(nm)]
    for sub, ks in (("hexgen", ("compile_acc", "pixel_acc", "transform_acc", "resolution_acc", "gen_ms")),
                    ("scene", ("speed_bound", "in_bounds", "finite", "deterministic", "seek_converge", "follow_visits", "us_per_entity_tick")),
                    ("stcnn", ("direction_acc", "speed_acc", "period_acc", "affine_invariance", "noise_robust_dir", "memory_selfcheck")),
                    ("nn", ("test_acc", "init_acc", "train_s"))):
        for k in ks:
            L.append(f"| {sub}.{k} | " + " | ".join(str(_g(R[x]['world'], sub, k)) for x in nm) + " |")
    return L


# =====================================================================================================
# 规则 hard-rules-v2（r3 起与 v1 并列单独出榜；v1 计分函数与读数一律不变）
#   保留 v1 全部子项；新增子项按「维内平均摊入」：维内 v1 有 n1 个等权子项、v2 新增 k 个时，
#   v2 维分 = (n1 · v1 维分 + Σ 新子项分) / (n1 + k)；维间权重不变。新增子项出处见 INTENT_MAP.md「v2 新增」节。
#   · 对抗 robust：n1 = 9（v1 的 9 个用例组）+ 4（维护/导出途中 SIGKILL、200k 崩溃恢复、导入期间并发读；各取组内通过率）
#   · 因果 causal：n1 = 5（v1 = 0.6·mean(3 项) + 0.4·mean(2 项) 恰为 5 项各 0.2）+ 3
#     （3000 点 find_cycles 对 Johnson 的 F1、链 truncated/cyclic 对预言机 F1、20 万边判环对数耗时分（正确性不过记 0））
#   · 世界 world：n1 = 4 + 2（2 万实体场景、hexgen 开放词汇组合泛化）
#   · 稳定 stability：子项不增，口径改为段内截止 + 按完成规模给分（stability2 作业，段分 = 不变量通过率 × ops_done/ops）
#   · 其余维（规模、检索、去重、变形、HMB、LLM）与 v1 相同。
# =====================================================================================================
RULES_V2 = "hard-rules-v2"
ROBUST2_ITEMS = ("crash_maint", "crash_export", "crash200k", "import_read")


def s2_robust(cdir, sd):
    v1, raw1 = s_robust(cdir, sd)
    items, raw = {}, {"v1": v1}
    for it in ROBUST2_ITEMS:
        r = _raw(_load(cdir, f"robust2_{it}_s{sd}"))
        if r and r.get("total"):
            items[it] = r["passed"] / r["total"]
            raw[it] = {"passed": r["passed"], "total": r["total"], "fails": [k for k, v in r["checks"].items() if not v],
                       "notes": r.get("notes")}
        else:
            items[it] = 0.0
            raw[it] = {"status": (_load(cdir, f"robust2_{it}_s{sd}") or {}).get("status", "missing")}
    raw["items"] = {k: round(v, 4) for k, v in items.items()}
    return (9 * v1 + 100 * sum(items.values())) / (9 + len(items)), raw


def s2_causal(cdir, sd):
    v1, raw1 = s_causal(cdir, sd)
    j = _raw(_load(cdir, f"causal2_johnson_s{sd}"))
    c = _raw(_load(cdir, f"causal2_chains_s{sd}"))
    h = _raw(_load(cdir, f"causal2_huge_s{sd}"))
    sj = float(j["f1"]) if j else 0.0
    sc = float(c["f1"]) if c else 0.0
    sh = 0.0
    if h and h.get("acyclic_ok") and h.get("cyclic_ok"):
        sh = mean([logscore(h.get("acyclic_ms"), 50, 50000), logscore(h.get("cyclic_ms"), 50, 50000)])
    items = {"johnson_f1": sj, "chains_flag_f1": sc, "huge200k_has_cycle": sh}
    return (5 * v1 + 100 * sum(items.values())) / 8, {"v1": v1, "items": {k: round(v, 4) for k, v in items.items()},
                                                       "johnson": j, "chains": c, "huge": h}


def s2_world(cdir, sd):
    v1, raw1 = s_world(cdir, sd)
    sc = _raw(_load(cdir, f"world2_scene20k_s{sd}"))
    hx = _raw(_load(cdir, f"world2_hexgen_open_s{sd}"))
    s_sc = (0.5 * mean([sc["speed_bound"], sc["in_bounds"], sc["finite"]]) + 0.5 * logscore(sc["us_per_entity_tick"], 0.2, 200)) if sc else 0.0
    s_hx = mean([hx["compile_acc"], hx["pixel_acc"]]) if hx else 0.0
    items = {"scene20k": s_sc, "hexgen_open": s_hx}
    return (4 * v1 + 100 * sum(items.values())) / 6, {"v1": v1, "items": {k: round(v, 4) for k, v in items.items()},
                                                       "scene20k": sc, "hexgen_open": hx}


def s2_stability(cdir, sd):
    fr, last, done = [], None, []
    for c in range(5):
        res = _load(cdir, f"stability2_c{c}_s{sd}")
        r = _raw(res)
        if not r:
            fr.append(0.0)
            done.append((res or {}).get("status", "missing"))
            continue
        inv = r["invariants"]
        frac = min(1.0, r.get("ops_done", 0) / max(1, r.get("ops", 20000)))
        fr.append(sum(inv.values()) / len(inv) * frac)
        done.append(round(frac, 3))
        last = r
    drift = 0.0
    if last and last.get("lat_by_chunk", {}).get("0") and last["lat_by_chunk"].get("4"):
        drift = logscore(last["lat_by_chunk"]["4"] / last["lat_by_chunk"]["0"], 1.2, 10)
    return 100 * (0.8 * mean(fr) + 0.2 * drift), {"chunk_scores": [round(x, 4) for x in fr], "ops_frac_by_chunk": done,
                                                 "last": last, "drift_score": drift}


DIMS_V2 = dict(DIMS, robust=s2_robust, causal=s2_causal, world=s2_world, stability=s2_stability)


def compute_v2(rdir, snaps):
    res = {}
    for sn in snaps:
        cdir = os.path.join(rdir, sn["name"])
        res[sn["name"]] = {}
        for sd in (0, 1):
            dims, raw = {}, {}
            for k, fn in DIMS_V2.items():
                sc, rw = fn(cdir, sd)
                dims[k], raw[k] = round(sc, 2), rw
            hs, hr = s_hmb(sn["name"])
            if hs is not None:
                dims["hmb"], raw["hmb"] = round(hs, 2), hr
            ls, lr = s_llm(cdir, sd)
            if ls is not None:
                dims["llm"], raw["llm"] = round(ls, 2), lr
            wsum = sum(WEIGHTS[k] for k in dims)
            res[sn["name"]][f"s{sd}"] = {"total": round(sum(WEIGHTS[k] * v for k, v in dims.items()) / wsum, 2),
                                         "dims": dims, "raw": raw}
    return res


def render_v2(run, snaps, rdir):
    res = compute_v2(rdir, snaps)
    here = os.path.dirname(os.path.abspath(__file__))
    out = {"run": run, "rules": RULES_V2, "generated": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
           "weights": WEIGHTS, "snapshots": snaps, "hmb_source": os.path.basename(HMB_PATH), "results": res}
    json.dump(out, open(os.path.join(here, "out", f"hard_v2_{run}.json"), "w"), ensure_ascii=False, indent=1, default=str)
    nm = [s["name"] for s in snaps]
    dims = [k for k in WEIGHTS if any(k in res[s]['s0']['dims'] for s in nm)]
    L = [f"# 灵枢 HARD 榜 v2（{run}）", "",
         f"生成：{out['generated']}（Asia/Shanghai）· 规则 **{RULES_V2}**（与 v1 并列单独出榜；v1 见 LEADERBOARD_HARD.md）。"
         f"v2 = v1 全部子项 + 更难的新子项（维内平均摊入，维间权重不变），出处见 INTENT_MAP.md「v2 新增」节。HMB 读数：`{out['hmb_source']}`。", "",
         "## 参评快照", "", "| 快照 | 实现 | 提交 |", "|---|---|---|"]
    for s in snaps:
        L.append(f"| {s['name']} | {s['impl']} | `{s['rev'][:10]}` |")
    L += ["", "## 总榜 v2（seed 0 / seed 1）", "",
          "| 快照 | 总分 s0 | 总分 s1 | " + " | ".join(f"{NAMES[k]}({WEIGHTS[k]})" for k in dims) + " |",
          "|---|---|---|" + "---|" * len(dims)]
    for x in nm:
        r = res[x]
        L.append(f"| {x} | **{r['s0']['total']}** | {r['s1']['total']} | " +
                 " | ".join(f"{r['s0']['dims'].get(k, '—')} / {r['s1']['dims'].get(k, '—')}" for k in dims) + " |")
    if "ng" in nm and "integrated" in nm:
        for sd in ("s0", "s1"):
            a, b = res["ng"][sd]["total"], res["integrated"][sd]["total"]
            L.append(f"\nng / integrated（{sd}）= **{a / b:.2f}×**")
    L += ["", "## v2 新增子项读数（s0 / s1）", "", "| 子项 | " + " | ".join(nm) + " |", "|---|" + "---|" * len(nm)]

    def it(x, dim, k):
        return " / ".join(str(_g(res[x][sd]["raw"][dim], "items", k)) for sd in ("s0", "s1"))
    for k in ROBUST2_ITEMS:
        L.append(f"| 对抗.{k}（通过率） | " + " | ".join(it(x, "robust", k) for x in nm) + " |")
    for k in ("johnson_f1", "chains_flag_f1", "huge200k_has_cycle"):
        L.append(f"| 因果.{k} | " + " | ".join(it(x, "causal", k) for x in nm) + " |")
    for k in ("scene20k", "hexgen_open"):
        L.append(f"| 世界.{k} | " + " | ".join(it(x, "world", k) for x in nm) + " |")
    L.append("| 稳定.段分（s0） | " + " | ".join(str(_g(res[x]["s0"]["raw"]["stability"], "chunk_scores")) for x in nm) + " |")
    L.append("| 稳定.完成比例（s0） | " + " | ".join(str(_g(res[x]["s0"]["raw"]["stability"], "ops_frac_by_chunk")) for x in nm) + " |")
    L += ["", "### 新增子项原始读数（seed 0）", "", "| 项 | " + " | ".join(nm) + " |", "|---|" + "---|" * len(nm)]
    for k in (("causal", "johnson", "n_truth"), ("causal", "johnson", "find_ms"), ("causal", "chains", "graph_exact"),
              ("causal", "huge", "build_s"), ("causal", "huge", "acyclic_ms"), ("causal", "huge", "cyclic_ms"),
              ("world", "scene20k", "ticks_done"), ("world", "scene20k", "us_per_entity_tick"), ("world", "scene20k", "speed_bound"),
              ("world", "hexgen_open", "compile_acc"), ("world", "hexgen_open", "prompt_exact"), ("world", "hexgen_open", "pixel_acc")):
        L.append(f"| {'.'.join(k)} | " + " | ".join(str(_g(res[x]["s0"]["raw"], *k)) for x in nm) + " |")
    for x in nm:
        fails = []
        for k in ROBUST2_ITEMS:
            fails += _g(res[x]["s0"]["raw"]["robust"], k, "fails") if isinstance(_g(res[x]["s0"]["raw"]["robust"], k, "fails"), list) else [f"{k}:{_g(res[x]['s0']['raw']['robust'], k, 'status')}"]
        L.append(f"\n- 对抗新增失败（{x}，s0）：{', '.join(fails) or '无'}")
    md = "\n".join(L) + "\n"
    lb = os.path.join(here, "LEADERBOARD_HARD_V2.md")
    tail = ""
    if os.path.exists(lb):
        txt = open(lb, encoding="utf-8").read()
        i = txt.find("## 迭代日志")
        if i >= 0:
            tail = txt[i:]
    if not tail:
        tail = "## 迭代日志\n\n（v1/v2 两版并列的逐轮记录见 LEADERBOARD_HARD.md 迭代日志。）\n"
    open(lb, "w", encoding="utf-8").write(md + "\n" + tail)
    for name, r in res.items():
        print("v2", name, "s0", r["s0"]["total"], r["s0"]["dims"], "| s1", r["s1"]["total"])
    return res
