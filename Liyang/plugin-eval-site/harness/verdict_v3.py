"""v3 判定算法（工程协议手册 v1.1 r2 §2.2–2.6、§13.4；验证计划 v0 §7）。

纯 Python 标准库实现（主实现）。独立参考实现见 harness/verdict_v3_ref.py（numpy，向量化、不同代码路径），
二者对同一输入必须得到规范化后一致的估计、区间和标签（验证计划门槛 1）。

────────────────────────────── 公开 API（接口稳定，v1） ──────────────────────────────
状态常量
    CAP_USEFUL="✅" CAP_HARMFUL="❌" CAP_EQUIV="➖" CAP_UNSURE="❓" CAP_UNTESTABLE="🚧"
    RUN_VALID="有效"  RUN_INVALID="实验无效/待重跑"
    REL_FORMAL="正式"  REL_TRIAL="方法试验"  REL_PENDING="待验证/待修复"

map_interval(L, U, *, a=5, b=5, max_half_width=5) -> (state, reason)
    §2.4 第 4–6 条的纯区间映射（不含数据/门槛检查）。L>U、NaN、inf 抛 AnalysisError("BAD_INTERVAL")。

seed_from_analysis_id(analysis_id) -> int
    SHA-256(analysis_id.encode('utf-8')) 前 8 字节，无符号大端整数。

analyze(spec: dict) -> dict
    完整判定：输入校验 → 运行有效性 → 没法测 → 场景内汇总 → 场景聚类 bootstrap → 五状态 → 发布门槛。
    永不抛异常（除编程错误）；拒绝时返回 release_state=待验证/待修复 或 run_state=实验无效/待重跑，
    capability=None，并在 errors 里给机器可读的 {code, detail, objects}。
    spec 字段见 analyze() 的 docstring。

paired_binary_interval(spec) / analyze(spec with metric.kind="binary")
    配对二元成功率差（P−B，单位：百分点 0–100），先场景聚合再按场景 bootstrap。

single_group_rate(k, n, conf=0.95) -> dict
    单组成功率：Clopper–Pearson 精确区间；k=0 给 "0/n + 95% 上限"。

compare_normalized(r1, r2, tol=1e-6) -> list[str]
    门槛 1 的规范化比较：只比估计、区间、半宽、标签、状态与场景/重跑数；忽略时间戳、审计人等元数据。

build_manifest(spec, extra=None) -> dict
    analysis manifest：RNG、种子推导、B、百分位方法、聚合顺序、场景权重、库版本、实现文件哈希。
──────────────────────────────────────────────────────────────────────────────────────

冻结的算法（manifest 原样登记）：
- RNG：SplitMix64（Steele, Lea & Flood 2014，常数 0x9E3779B97F4A7C15 / 0xBF58476D1CE4E5B9 / 0x94D049BB133111EB），
  状态初值 = seed；第 k 个输出（k 从 1 起）= mix(seed + k·γ mod 2^64)。
- 下标映射：idx = floor((x >> 11) · 2^-53 · G)（IEEE double，Python 与 numpy 逐位相同）。
- 抽取顺序：b = 0..B-1 外层，j = 0..G-1 内层，共 B·G 个输出。
- 统计量：所抽场景的加权均值 Σ w_k d_k / Σ w_k（d_k = 场景内配对差的重跑均值）。
- 百分位：Hyndman–Fan type 7（线性插值，= numpy.percentile method="linear"），取 (1−conf)/2 与 (1+conf)/2。
- 聚合顺序：题目加权分(0–100) → 同一 pair（同场景同重跑）P−B → 场景内对重跑等权平均 → 场景加权（equal | item_weight）→ 重采场景。
"""
from __future__ import annotations

import hashlib
import math
import platform
import sys
from pathlib import Path

IMPL_ID = "pes.verdict_v3"
IMPL_VERSION = "1.0.0"
RNG_ID = "splitmix64/u53-floor/v1"
PERCENTILE_METHOD = "hyndman-fan-type7-linear"
AGG_ORDER = ["item_weighted_score_0_100", "pair_diff_P_minus_B", "scenario_mean_over_reruns",
             "scenario_weighted_mean", "resample_scenarios_with_replacement"]

CAP_USEFUL, CAP_HARMFUL, CAP_EQUIV, CAP_UNSURE, CAP_UNTESTABLE = "✅", "❌", "➖", "❓", "🚧"
CAP_LABEL = {CAP_USEFUL: "真有用", CAP_HARMFUL: "帮倒忙", CAP_EQUIV: "没啥差别",
             CAP_UNSURE: "还说不准", CAP_UNTESTABLE: "没法测"}
RUN_VALID, RUN_INVALID = "有效", "实验无效/待重跑"
REL_FORMAL, REL_TRIAL, REL_PENDING = "正式", "方法试验", "待验证/待修复"

DEFAULTS = {"a": 5.0, "b": 5.0, "max_half_width": 5.0, "B": 10000, "conf": 0.95,
            "min_scenarios": 8, "min_reruns": 3}

UNTESTABLE_REASONS = ("安装失败", "环境不支持", "任务不适用")
GATE_KEYS = ("taskset_frozen", "domain_spec_frozen", "algorithm_validated",
             "evidence_complete", "independent_review", "scenarios_groupable")

_M64 = (1 << 64) - 1
_GAMMA = 0x9E3779B97F4A7C15


class AnalysisError(Exception):
    def __init__(self, code: str, detail: str = "", objects=None):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.objects = code, detail, list(objects or [])

    def as_dict(self):
        return {"code": self.code, "detail": self.detail, "objects": self.objects}


# ───────────────────────── RNG 与百分位 ─────────────────────────

def seed_from_analysis_id(analysis_id: str) -> int:
    if not isinstance(analysis_id, str) or not analysis_id:
        raise AnalysisError("NO_ANALYSIS_ID", "analysis_id 必须是非空字符串")
    return int.from_bytes(hashlib.sha256(analysis_id.encode("utf-8")).digest()[:8], "big", signed=False)


def _splitmix64(seed: int):
    s = seed & _M64
    while True:
        s = (s + _GAMMA) & _M64
        z = s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _M64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _M64
        yield z ^ (z >> 31)


def _percentile_t7(sorted_vals: list[float], p: float) -> float:
    n = len(sorted_vals)
    h = (n - 1) * p
    lo = math.floor(h)
    hi = min(lo + 1, n - 1)
    return sorted_vals[lo] + (h - lo) * (sorted_vals[hi] - sorted_vals[lo])


def cluster_bootstrap(values: list[float], weights: list[float], *, B: int, seed: int, conf: float):
    """按场景有放回重抽 G 个，统计量 = 加权均值。返回 (L, U)。"""
    G = len(values)
    if G == 0:
        raise AnalysisError("NO_SCENARIOS", "没有可用场景")
    gen = _splitmix64(seed)
    scale = 2.0 ** -53
    stats = []
    for _ in range(B):
        sw = swd = 0.0
        for _ in range(G):
            k = math.floor((next(gen) >> 11) * scale * G)
            sw += weights[k]
            swd += weights[k] * values[k]
        stats.append(swd / sw)
    stats.sort()
    alpha = (1.0 - conf) / 2.0
    return _percentile_t7(stats, alpha), _percentile_t7(stats, 1.0 - alpha)


# ───────────────────────── 区间 → 五状态 ─────────────────────────

def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def map_interval(L, U, *, a=DEFAULTS["a"], b=DEFAULTS["b"], max_half_width=DEFAULTS["max_half_width"]):
    """手册 §2.4 第 4–6 条。只做区间映射；调用者负责数据/门槛/样本检查。"""
    if not (_finite(L) and _finite(U)):
        raise AnalysisError("BAD_INTERVAL", f"区间含 NaN/inf 或非数值：[{L},{U}]")
    if L > U:
        raise AnalysisError("BAD_INTERVAL", f"L>U：[{L},{U}]")
    if not (_finite(a) and _finite(b) and a > 0 and b > 0):
        raise AnalysisError("BAD_THRESHOLD", f"a、b 必须 >0：a={a} b={b}")
    hw = (U - L) / 2.0
    if hw > max_half_width:
        return CAP_UNSURE, f"精度不足：半宽 {hw:g} > {max_half_width:g}"
    if L > a:
        return CAP_USEFUL, f"下界 {L:g} > 正向门槛 {a:g}"
    if U < -b:
        return CAP_HARMFUL, f"上界 {U:g} < −{b:g}"
    if L > -b and U < a:
        return CAP_EQUIV, f"区间完全落在 (−{b:g}, {a:g}) 内（本次范围内实际等效）"
    if L == a or U == -b or L == -b or U == a:
        return CAP_UNSURE, "区间端点正好等于门槛"
    if U >= a and L <= a:
        return CAP_UNSURE, f"区间跨过正向门槛 {a:g}"
    if L <= -b and U >= -b:
        return CAP_UNSURE, f"区间跨过负向门槛 −{b:g}"
    return CAP_UNSURE, "未满足正贡献、负贡献或等效条件"


# ───────────────────────── 场景汇总 ─────────────────────────

def _run_score(scores: dict, weights: dict, scale_max: float, kind: str) -> float:
    sw = swx = 0.0
    for q, s in scores.items():
        w = weights[q]
        if kind == "binary":
            if not _finite(s) or s not in (0, 1):
                raise AnalysisError("BAD_BINARY", f"二元指标只接受 0/1：{q}={s!r}", [q])
            x = float(s)
        else:
            if not _finite(s) or s < 0 or s > scale_max:
                raise AnalysisError("BAD_SCORE", f"题目分不在 [0,{scale_max}]：{q}={s!r}", [q])
            x = s / scale_max
        sw += w
        swx += w * x
    return 100.0 * swx / sw


def _validate_weights(weights, registered_sha256=None):
    if not isinstance(weights, dict) or not weights:
        raise AnalysisError("BAD_WEIGHTS", "weights 为空")
    bad = [q for q, w in weights.items() if not _finite(w) or w < 0]
    if bad:
        raise AnalysisError("BAD_WEIGHTS", "权重须为有限非负数", bad)
    if sum(weights.values()) <= 0:
        raise AnalysisError("BAD_WEIGHTS", "权重和须 >0")
    if registered_sha256:
        got = weights_sha256(weights)
        if got != registered_sha256:
            raise AnalysisError("WEIGHTS_HASH_MISMATCH", f"权重与登记哈希不符：{got} ≠ {registered_sha256}")


def weights_sha256(weights: dict) -> str:
    canon = "\n".join(f"{k}\t{float(weights[k])!r}" for k in sorted(weights))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def scenario_table(spec: dict) -> dict:
    """返回 {scenario_id: {"d": 场景均值差, "w": 场景权重, "reruns": n, "base": 绝对分均值, "plug": ..., "pairs": [...]}}
    以及排除记录。只用有效且完整的 pair；不符合即抛 AnalysisError 或记入 excluded。"""
    metric = spec.get("metric", {})
    kind = metric.get("kind", "continuous")
    if kind not in ("continuous", "binary"):
        raise AnalysisError("BAD_METRIC", f"metric.kind={kind!r}")
    scale_max = float(metric.get("scale_max", 1.0))
    if not (scale_max > 0 and math.isfinite(scale_max)):
        raise AnalysisError("BAD_METRIC", "scale_max 须 >0")
    weights = spec.get("weights")
    _validate_weights(weights, spec.get("weights_sha256"))
    weighting = spec.get("scenario_weighting", "equal")
    if weighting not in ("equal", "item_weight"):
        raise AnalysisError("BAD_WEIGHTING", f"scenario_weighting={weighting!r}")
    pairs = spec.get("pairs") or []
    excluded, seen = [], set()
    per = {}
    for p in pairs:
        pid, sid = p.get("pair_id"), p.get("scenario_id")
        if pid is None or sid is None:
            raise AnalysisError("BAD_PAIR", "pair 缺 pair_id/scenario_id", [pid])
        if pid in seen:
            raise AnalysisError("DUP_PAIR", "pair_id 重复", [pid])
        seen.add(pid)
        if p.get("valid") is not True:
            excluded.append({"pair_id": pid, "scenario_id": sid, "reason": p.get("invalid_reason") or "运行无效（未给原因）"})
            continue
        base, plug = p.get("base"), p.get("plug")
        if base is None or plug is None:
            raise AnalysisError("MISSING_PAIR_SIDE", "配对缺一侧（不得只用单边）", [pid])
        if set(base) != set(plug):
            raise AnalysisError("ITEM_MISMATCH", "同一 pair 两侧题目集合不同", [pid])
        if not base:
            raise AnalysisError("EMPTY_PAIR", "pair 无题目", [pid])
        unknown = sorted(set(base) - set(weights))
        if unknown:
            raise AnalysisError("WEIGHT_MISSING", "题目无登记权重", unknown)
        if sum(weights[q] for q in base) <= 0:
            raise AnalysisError("BAD_WEIGHTS", "该 pair 题目权重和为 0", [pid])
        sb = _run_score(base, weights, scale_max, kind)
        sp = _run_score(plug, weights, scale_max, kind)
        e = per.setdefault(sid, {"diffs": [], "base": [], "plug": [], "pairs": [], "items": set(base),
                                 "item_w": sum(weights[q] for q in base), "reruns": set()})
        if set(base) != e["items"]:
            raise AnalysisError("ITEM_MISMATCH", "同一场景不同重跑题目集合不同", [pid])
        r = p.get("rerun")
        if r in e["reruns"]:
            raise AnalysisError("DUP_RERUN", "同一场景重跑编号重复", [pid])
        e["reruns"].add(r)
        e["diffs"].append(sp - sb); e["base"].append(sb); e["plug"].append(sp); e["pairs"].append(pid)
    out = {}
    for sid in sorted(per, key=str):
        e = per[sid]
        n = len(e["diffs"])
        out[sid] = {"d": sum(e["diffs"]) / n, "w": 1.0 if weighting == "equal" else e["item_w"],
                    "reruns": n, "base": sum(e["base"]) / n, "plug": sum(e["plug"]) / n, "pairs": e["pairs"]}
    return {"scenarios": out, "excluded": excluded}


# ───────────────────────── 主入口 ─────────────────────────

def _impl_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def frozen_algorithm() -> dict:
    return {"impl_id": IMPL_ID, "impl_version": IMPL_VERSION, "rng": RNG_ID,
            "percentile": PERCENTILE_METHOD, "aggregation_order": AGG_ORDER}


def build_manifest(spec: dict, extra: dict | None = None) -> dict:
    p = {**DEFAULTS, **(spec.get("params") or {})}
    aid = spec.get("analysis_id")
    m = {
        "analysis_id": aid,
        "seed_derivation": "uint64_be(SHA-256(utf8(analysis_id))[0:8])",
        "seed": seed_from_analysis_id(aid) if isinstance(aid, str) and aid else None,
        **frozen_algorithm(),
        "index_mapping": "floor((x>>11) * 2^-53 * G)",
        "draw_order": "b-major (b=0..B-1, j=0..G-1)",
        "statistic": "weighted mean of resampled scenario diffs",
        "scenario_weighting": spec.get("scenario_weighting", "equal"),
        "B": p["B"], "conf": p["conf"],
        "thresholds": {"a": p["a"], "b": p["b"], "max_half_width": p["max_half_width"]},
        "sample_minimum": {"min_scenarios": p["min_scenarios"], "min_reruns": p["min_reruns"]},
        "metric": spec.get("metric", {"kind": "continuous", "scale_max": 1.0}),
        "scale": "0-100",
        "weights_sha256": weights_sha256(spec["weights"]) if isinstance(spec.get("weights"), dict) and spec["weights"] else None,
        "python": sys.version.split()[0], "platform": platform.platform(),
        "libraries": {"stdlib-only": True},
        "impl_file_sha256": _impl_sha256(),
    }
    if extra:
        m.update(extra)
    return m


def analyze(spec: dict) -> dict:
    """见 _analyze。任何未预料的输入类型错误也不抛出，而是返回 待验证/待修复 + BAD_INPUT。"""
    try:
        return _analyze(spec)
    except (TypeError, ValueError, KeyError, AttributeError) as e:
        return {"analysis_id": spec.get("analysis_id") if isinstance(spec, dict) else None,
                "run_state": RUN_VALID, "release_state": REL_PENDING, "capability": None, "capability_label": None,
                "capability_observed": None, "install_stage": None, "interval": None, "estimate": None,
                "half_width": None, "base_abs": None, "plug_abs": None, "n_scenarios": 0, "reruns_per_scenario": None,
                "scenarios": {}, "excluded_pairs": [], "rankable": False,
                "errors": [{"code": "BAD_INPUT", "detail": f"{type(e).__name__}: {e}", "objects": []}],
                "reasons": [f"输入无法解析：{type(e).__name__}: {e}"]}


def _analyze(spec: dict) -> dict:
    """spec 字段：
    analysis_id (str, 冻结)            ; frozen: {rng, impl_version, percentile}（可选：登记的冻结算法，须与当前一致）
    metric: {kind: continuous|binary, scale_max: 题目满分(连续)}；主要指标统一换算到 0–100
    weights: {item_id: w≥0}；weights_sha256（可选，登记哈希）
    pairs: [{pair_id, scenario_id, rerun, valid: bool, invalid_reason, base: {item: score}, plug: {item: score}}]
    sample_plan: {scenarios: [scenario_id...], reruns: int}（预注册固定样本；缺则用实际）
    scenario_weighting: equal | item_weight
    params: {a, b, max_half_width, B, conf, min_scenarios, min_reruns}
    install: {ok: bool, reason}; untestable: 原因（"环境不支持"/"任务不适用"…）
    evidence: {missing: [...], hash_mismatch: [...], revoked_scorer: [...]}
    gates: {taskset_frozen, domain_spec_frozen, algorithm_validated, evidence_complete, independent_review, scenarios_groupable}
    """
    p = {**DEFAULTS, **(spec.get("params") or {})}
    res = {"analysis_id": spec.get("analysis_id"), "run_state": None, "release_state": None,
           "capability": None, "capability_label": None, "capability_observed": None,
           "install_stage": None, "reasons": [], "errors": [], "excluded_pairs": [],
           "estimate": None, "interval": None, "half_width": None, "base_abs": None, "plug_abs": None,
           "n_scenarios": 0, "reruns_per_scenario": None, "scenarios": {}, "rankable": False}

    def reject(release, err: AnalysisError, run_state=RUN_VALID):
        res.update(run_state=run_state, release_state=release)
        res["errors"].append(err.as_dict())
        res["reasons"].append(err.detail or err.code)
        return res

    # 0. 冻结算法一致性（RNG/库版本不同 → 拒绝）
    fr = spec.get("frozen")
    if fr:
        cur = frozen_algorithm()
        diff = [k for k in ("rng", "impl_version", "percentile") if k in fr and fr[k] != cur[k]]
        if diff:
            return reject(REL_PENDING, AnalysisError("ALGORITHM_MISMATCH",
                          "登记的冻结算法与当前实现不同：" + "、".join(f"{k} {fr[k]}≠{cur[k]}" for k in diff), diff))
    try:
        res["manifest"] = build_manifest(spec)
    except AnalysisError as e:
        return reject(REL_PENDING, e)

    # 1. 没法测（安装失败双重记录）
    inst = spec.get("install") or {}
    if inst and inst.get("ok") is False:
        res.update(run_state=RUN_VALID, release_state=None, capability=CAP_UNTESTABLE,
                   capability_label=CAP_LABEL[CAP_UNTESTABLE], install_stage="❌失败",
                   untestable_reason="安装失败")
        res["reasons"].append("能力结论：🚧没法测（原因：安装失败）；安装环节：❌失败" + (f"（{inst['reason']}）" if inst.get("reason") else ""))
        res["release_state"] = REL_FORMAL if _gates_ok(spec, p, None)[0] else REL_TRIAL
        return res
    if inst.get("ok") is True:
        res["install_stage"] = "✅成功"
    unt = spec.get("untestable")
    if unt:
        if unt not in UNTESTABLE_REASONS:
            return reject(REL_PENDING, AnalysisError("BAD_UNTESTABLE_REASON", f"没法测原因须为 {UNTESTABLE_REASONS} 之一：{unt!r}"))
        res.update(run_state=RUN_VALID, capability=CAP_UNTESTABLE, capability_label=CAP_LABEL[CAP_UNTESTABLE],
                   untestable_reason=unt, release_state=REL_FORMAL if _gates_ok(spec, p, None)[0] else REL_TRIAL)
        res["reasons"].append(f"没法测（原因：{unt}）")
        return res

    # 2. 证据缺失 / 判分器撤销 / 哈希不符 → 待验证/待修复（§13.4，机器可读错误）
    ev = spec.get("evidence") or {}
    for key, code in (("missing", "EVIDENCE_MISSING"), ("hash_mismatch", "EVIDENCE_HASH_MISMATCH"),
                      ("revoked_scorer", "SCORER_REVOKED")):
        if ev.get(key):
            return reject(REL_PENDING, AnalysisError(code, f"证据问题：{key}", ev[key]))
    gates = spec.get("gates") or {}
    if gates.get("algorithm_validated") is False:
        return reject(REL_PENDING, AnalysisError("ALGORITHM_NOT_VALIDATED", "区间实现未完成校验，不生成数值区间和正式标签"))

    # 3. 数据与配对
    try:
        if not (_finite(p["a"]) and _finite(p["b"]) and p["a"] > 0 and p["b"] > 0):
            raise AnalysisError("BAD_THRESHOLD", f"a、b 必须 >0：a={p['a']} b={p['b']}")
        if not (isinstance(p["B"], int) and p["B"] >= 1000):
            raise AnalysisError("BAD_PARAM", f"B 须为 ≥1000 的整数：{p['B']}")
        if not (0 < p["conf"] < 1):
            raise AnalysisError("BAD_PARAM", f"conf={p['conf']}")
        tab = scenario_table(spec)
    except AnalysisError as e:
        return reject(REL_PENDING, e)
    sc, res["excluded_pairs"] = tab["scenarios"], tab["excluded"]

    # 3b. 固定样本计划：无效运行整对排除；计划内有缺口 → 实验无效/待重跑（不缩小分母、不只补一边）
    plan = spec.get("sample_plan")
    if plan:
        want_s = list(plan.get("scenarios") or [])
        want_r = int(plan.get("reruns") or 0)
        extra_s = sorted(set(sc) - set(want_s), key=str)
        if extra_s:
            return reject(REL_PENDING, AnalysisError("UNPLANNED_SCENARIO", "出现计划外场景", extra_s))
        short = [s for s in want_s if s not in sc or sc[s]["reruns"] < want_r]
        if short:
            res["n_scenarios"] = len(sc)
            return reject(None, AnalysisError("SAMPLE_PLAN_INCOMPLETE",
                          f"预注册样本未完成（{len(short)} 个场景缺有效配对；已排除无效 pair {len(tab['excluded'])} 个），该批作废待补跑",
                          short), run_state=RUN_INVALID)
    if not sc:
        return reject(None, AnalysisError("NO_VALID_PAIRS", "没有有效配对"), run_state=RUN_INVALID)

    sids = list(sc)
    vals = [sc[s]["d"] for s in sids]
    ws = [sc[s]["w"] for s in sids]
    sw = sum(ws)
    est = sum(w * v for w, v in zip(ws, vals)) / sw
    try:
        L, U = cluster_bootstrap(vals, ws, B=p["B"], seed=seed_from_analysis_id(spec["analysis_id"]), conf=p["conf"])
    except AnalysisError as e:
        return reject(REL_PENDING, e)
    if not (_finite(L) and _finite(U)) or L > U:
        return reject(REL_PENDING, AnalysisError("BAD_INTERVAL", f"区间无法计算：[{L},{U}]"))
    reruns = [sc[s]["reruns"] for s in sids]
    res.update(run_state=RUN_VALID, estimate=est, interval=[L, U], half_width=(U - L) / 2.0,
               base_abs=sum(w * sc[s]["base"] for w, s in zip(ws, sids)) / sw,
               plug_abs=sum(w * sc[s]["plug"] for w, s in zip(ws, sids)) / sw,
               n_scenarios=len(sids), reruns_per_scenario=min(reruns),
               scenarios={s: {k: sc[s][k] for k in ("d", "w", "reruns", "base", "plug")} for s in sids})

    # 4. 有效样本 → 五状态（观察值）
    if len(sids) < p["min_scenarios"] or min(reruns) < p["min_reruns"]:
        state, why = CAP_UNSURE, (f"有效样本不足：独立场景 {len(sids)}（要求 ≥{p['min_scenarios']}），"
                                  f"每场景配对重跑最少 {min(reruns)}（要求 ≥{p['min_reruns']}）；极少场景下窄区间不代表充分证据")
    else:
        state, why = map_interval(L, U, a=p["a"], b=p["b"], max_half_width=p["max_half_width"])
    res["capability_observed"] = state
    res["reasons"].append(why)

    # 5. 发布门槛（§2.5）：未达工程门槛 → 方法试验，不使用正式五状态标签
    ok, missing = _gates_ok(spec, p, sids)
    if ok:
        res.update(release_state=REL_FORMAL, capability=state, capability_label=CAP_LABEL[state],
                   rankable=state in (CAP_USEFUL, CAP_HARMFUL, CAP_EQUIV))
    else:
        res.update(release_state=REL_TRIAL)
        res["reasons"].append("未达正式发布门槛：" + "、".join(missing) + "（只发布方法试验与已知事实）")
        res["gates_missing"] = missing
    return res


def _gates_ok(spec, p, sids):
    gates = spec.get("gates") or {}
    missing = [k for k in GATE_KEYS if gates.get(k) is not True]
    if sids is not None:
        plan = spec.get("sample_plan") or {}
        n_plan = len(plan.get("scenarios") or sids)
        r_plan = int(plan.get("reruns") or 0)
        if n_plan < p["min_scenarios"]:
            missing.append(f"样本计划场景数 {n_plan} < 域要求 {p['min_scenarios']}")
        if plan and r_plan < p["min_reruns"]:
            missing.append(f"样本计划重跑数 {r_plan} < 域要求 {p['min_reruns']}")
    return (not missing), missing


# ───────────────────────── 二元与单组 ─────────────────────────

def paired_binary_interval(spec: dict) -> dict:
    """配对二元成功率差：每 pair 记 P 与 B 的 0/1；同场景先聚合（成功率差，百分点），再按场景 bootstrap。
    公式：d_s = mean_r [100·Σ_i w_i(P_{s,r,i} − B_{s,r,i}) / Σ_i w_i]；区间 = cluster_bootstrap(d_s)。
    边界：全成/全败 → d_s=0、区间 [0,0]，样本门槛仍须满足；不使用普通二项区间。"""
    s = dict(spec)
    s["metric"] = {"kind": "binary"}
    return analyze(s)


def _binom_cdf(k, n, p):
    if p <= 0:
        return 1.0
    if p >= 1:
        return 1.0 if k >= n else 0.0
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, k + 1))


def single_group_rate(k: int, n: int, conf: float = 0.95) -> dict:
    """Clopper–Pearson 精确区间（二分法求解，精度 1e-12）。题目可视为独立时才适用（手册 §2.3 附表）。"""
    if not (isinstance(k, int) and isinstance(n, int)) or n <= 0 or k < 0 or k > n:
        raise AnalysisError("BAD_COUNTS", f"k={k} n={n}")
    alpha = 1 - conf

    def solve(f, lo=0.0, hi=1.0):
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid):
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(lambda q: 1 - _binom_cdf(k - 1, n, q) < alpha / 2)
    upper = 1.0 if k == n else solve(lambda q: _binom_cdf(k, n, q) > alpha / 2)
    out = {"k": k, "n": n, "rate": k / n, "interval": [lower, upper], "method": "clopper-pearson", "conf": conf}
    if k == 0:
        out["display"] = f"0/{n}，{round(conf*100)}% 上限 {upper*100:.1f}%"
    return out


# ───────────────────────── 规范化比较（门槛 1） ─────────────────────────

_CMP_KEYS = ("run_state", "release_state", "capability", "capability_observed", "install_stage",
             "n_scenarios", "reruns_per_scenario")


def normalize(r: dict, ndigits: int = 6) -> dict:
    def rnd(x):
        return None if x is None else round(float(x), ndigits)
    return {**{k: r.get(k) for k in _CMP_KEYS},
            "estimate": rnd(r.get("estimate")), "half_width": rnd(r.get("half_width")),
            "interval": None if r.get("interval") is None else [rnd(x) for x in r["interval"]],
            "error_codes": sorted(e["code"] for e in r.get("errors", []))}


def compare_normalized(r1: dict, r2: dict, tol: float = 1e-6) -> list[str]:
    a, b = normalize(r1), normalize(r2)
    diffs = []
    for k in a:
        x, y = a[k], b[k]
        if isinstance(x, list) and isinstance(y, list) and len(x) == len(y) and all(isinstance(v, float) for v in x + y):
            if any(abs(u - v) > tol for u, v in zip(x, y)):
                diffs.append(f"{k}: {x} ≠ {y}")
        elif isinstance(x, float) and isinstance(y, float):
            if abs(x - y) > tol:
                diffs.append(f"{k}: {x} ≠ {y}")
        elif x != y:
            diffs.append(f"{k}: {x!r} ≠ {y!r}")
    return diffs
