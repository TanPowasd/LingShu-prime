"""验证计划 v0 §7 判定算法边界回归 + 附加边界；主实现（stdlib）与参考实现（numpy）必须一致。"""
import hashlib
import math
import random

import pytest

from harness import verdict_v3 as V
from harness import cost_v3 as C
from harness import labels_v3 as LB

np = pytest.importorskip("numpy")
from harness import verdict_v3_ref as R  # noqa: E402

GATES_OK = {k: True for k in V.GATE_KEYS}


# ───────── 合成数据 ─────────
def make_spec(effects, *, reruns=3, n_items=5, base_level=0.5, noise=0.0, seed=0, aid="test-analysis",
              gates=None, plan=True, weighting="equal", weights=None, kind="continuous"):
    rng = random.Random(seed)
    W, pairs = {}, []
    for s, eff in enumerate(effects):
        for i in range(n_items):
            W[f"S{s}q{i}"] = (weights or {}).get(i, 1.0)
        for r in range(reruns):
            if kind == "binary":
                b = {f"S{s}q{i}": int(rng.random() < base_level) for i in range(n_items)}
                p = {q: int(rng.random() < min(1, max(0, base_level + eff))) for q in b}
            else:
                b = {f"S{s}q{i}": min(1.0, max(0.0, base_level + rng.gauss(0, noise))) for i in range(n_items)}
                p = {q: min(1.0, max(0.0, v + eff / 100 + rng.gauss(0, noise))) for q, v in b.items()}
            pairs.append({"pair_id": f"S{s}-r{r}", "scenario_id": f"S{s}", "rerun": r, "valid": True,
                          "base": b, "plug": p})
    spec = {"analysis_id": aid, "metric": {"kind": kind, "scale_max": 1.0}, "weights": W, "pairs": pairs,
            "scenario_weighting": weighting, "gates": dict(GATES_OK if gates is None else gates)}
    if plan:
        spec["sample_plan"] = {"scenarios": [f"S{s}" for s in range(len(effects))], "reruns": reruns}
    return spec


def both(spec):
    a = V.analyze(spec)
    b = R.ref_analyze(spec)
    assert a["capability_observed"] == b["capability_observed"]
    assert a["n_scenarios"] == b["n_scenarios"] and a["reruns_per_scenario"] == b["reruns_per_scenario"]
    assert abs(a["estimate"] - b["estimate"]) < 1e-9
    assert all(abs(x - y) < 1e-9 for x, y in zip(a["interval"], b["interval"]))
    assert abs(a["base_abs"] - b["base_abs"]) < 1e-9 and abs(a["plug_abs"] - b["plug_abs"]) < 1e-9
    return a


# ───────── §7 区间表（两套实现） ─────────
TABLE = [
    ((6, 10), "✅", ""),
    ((-10, -6), "❌", ""),
    ((-2, 2), "➖", ""),
    ((4, 8), "❓", "跨过正向门槛"),
    ((-8, -4), "❓", "跨过负向门槛"),
    ((5, 8), "❓", "正好等于门槛"),
    ((-8, -5), "❓", "正好等于门槛"),
    ((-9, 9), "❓", "精度不足"),
    ((6, 30), "❓", "精度不足"),
]


@pytest.mark.parametrize("iv,state,why", TABLE)
def test_table_interval_mapping(iv, state, why):
    st, reason = V.map_interval(*iv)
    assert st == state
    assert why in reason
    assert R.five_state(float(iv[0]), float(iv[1]), 5, 5, 5) == state


@pytest.mark.parametrize("iv", [(3, 2), (float("nan"), 1), (0, float("nan")), (float("-inf"), 0)])
def test_table_bad_interval_rejected(iv):
    with pytest.raises(V.AnalysisError) as e:
        V.map_interval(*iv)
    assert e.value.code == "BAD_INTERVAL"


def test_half_width_exactly_5_is_enough_and_just_over_is_not():
    assert V.map_interval(6, 16)[0] == "✅"
    assert V.map_interval(6, 16.0001)[0] == "❓"


def test_table_missing_evidence_refuses_analysis():
    s = make_spec([10] * 8)
    s["evidence"] = {"missing": ["runs/S0-r0/artifact-manifest.json"]}
    r = V.analyze(s)
    assert r["release_state"] == V.REL_PENDING
    assert r["capability"] is None and r["capability_observed"] is None and r["interval"] is None
    assert r["errors"][0]["code"] == "EVIDENCE_MISSING"
    assert r["errors"][0]["objects"] == ["runs/S0-r0/artifact-manifest.json"]


def test_table_hash_mismatch_and_revoked_scorer_refuse():
    for k, code in (("hash_mismatch", "EVIDENCE_HASH_MISMATCH"), ("revoked_scorer", "SCORER_REVOKED")):
        s = make_spec([10] * 8)
        s["evidence"] = {k: ["x"]}
        r = V.analyze(s)
        assert r["release_state"] == V.REL_PENDING and r["capability"] is None
        assert r["errors"][0]["code"] == code


def test_table_nan_score_refuses_analysis():
    s = make_spec([10] * 8)
    s["pairs"][0]["plug"]["S0q0"] = float("nan")
    r = V.analyze(s)
    assert r["release_state"] == V.REL_PENDING and r["capability"] is None and r["interval"] is None
    assert r["errors"][0]["code"] == "BAD_SCORE"


def test_table_install_failure_double_record():
    s = make_spec([10] * 8)
    s["install"] = {"ok": False, "reason": "npm 包缺修复"}
    r = V.analyze(s)
    assert r["capability"] == "🚧" and r["untestable_reason"] == "安装失败"
    assert r["install_stage"] == "❌失败"
    assert r["interval"] is None
    assert any("安装环节：❌失败" in x for x in r["reasons"])
    e = LB.eligibility({"capability": r["capability"], "release_state": r["release_state"],
                        "completed_on": "2026-10-10"}, today="2026-10-11")
    assert e["display"] and not e["numeric_rank"]


def test_other_untestable_reasons_recorded_separately():
    for why in ("环境不支持", "任务不适用"):
        s = make_spec([10] * 8); s["untestable"] = why
        r = V.analyze(s)
        assert r["capability"] == "🚧" and r["untestable_reason"] == why
    s = make_spec([10] * 8); s["untestable"] = "随便"
    assert V.analyze(s)["release_state"] == V.REL_PENDING


def test_table_positive_gain_with_confirmed_severe_incident():
    r = both(make_spec([10] * 8))
    assert r["capability"] == "✅"
    e = LB.eligibility({"capability": r["capability"], "release_state": r["release_state"], "completed_on": "2026-10-10",
                        "incidents": [{"severity": "关键", "status": "confirmed"}]}, today="2026-10-12")
    assert e["capability_retained"] == "✅"
    assert e["recommendation"] == "暂停推荐"
    assert e["worth_trying"] is False
    assert e["display"] is True


def test_suspected_incident_is_investigating_not_fact():
    o = LB.security_overlay([{"severity": "关键", "status": "suspected"}])
    assert o["status"] == "调查中" and o["worth_trying"] is False and o["recommendation"] != "暂停推荐"


def test_table_over_90_days_exits_rank_and_badge():
    rec = {"capability": "✅", "release_state": "正式", "completed_on": "2026-01-01"}
    e = LB.eligibility(rec, today="2026-04-02")   # 第 91 天
    assert not e["numeric_rank"] and not e["badge"] and e["display"] and e["capability_retained"] == "✅"
    assert LB.eligibility(rec, today="2026-04-01")["numeric_rank"]  # 第 90 天仍有效
    # 只有按变更范围的复核记录可续期；改页面日期不算
    assert not LB.eligibility({**rec, "reviews": [{"date": "2026-03-01", "scope_matched": False}]}, today="2026-04-02")["numeric_rank"]
    assert LB.eligibility({**rec, "reviews": [{"date": "2026-03-01", "scope_matched": True}]}, today="2026-04-02")["numeric_rank"]


@pytest.mark.parametrize("cap", ["❓", "🚧"])
def test_table_unsure_and_untestable_not_ranked(cap):
    e = LB.eligibility({"capability": cap, "release_state": "正式", "completed_on": "2026-10-10"}, today="2026-10-11")
    assert e["display"] and not e["numeric_rank"] and not e["worth_trying"]


def test_formal_unsure_from_analyze_not_rankable():
    s = make_spec([1, 9, 3, 7, 2, 8, 4, 6])   # 估计 +5：区间跨正向门槛
    r = both(s)
    assert r["release_state"] == "正式" and r["capability"] == "❓" and r["rankable"] is False


def test_table_originals_deleted_insufficient_substitute():
    e = LB.eligibility({"capability": "✅", "release_state": "正式", "completed_on": "2026-10-10",
                        "evidence": {"originals_deleted": True, "redacted_sufficient": False}}, today="2026-10-11")
    assert e["evidence_state"] == "证据核验受限" and not e["numeric_rank"] and not e["badge"]
    e2 = LB.eligibility({"capability": "✅", "release_state": "正式", "completed_on": "2026-10-10",
                         "evidence": {"originals_deleted": True, "redacted_sufficient": True}}, today="2026-10-11")
    assert e2["numeric_rank"]


# ───────── 附加边界 ─────────
def test_all_correct_both_arms_is_equivalent_zero_variance():
    s = make_spec([0] * 8, base_level=1.0)
    r = both(s)
    assert r["interval"] == [0.0, 0.0] and r["capability"] == "➖"


def test_plug_all_correct_base_all_wrong():
    s = make_spec([100] * 8, base_level=0.0)
    r = both(s)
    assert r["estimate"] == 100.0 and r["capability"] == "✅" and r["plug_abs"] == 100.0 and r["base_abs"] == 0.0


def test_plug_all_wrong_base_all_correct():
    s = make_spec([-100] * 8, base_level=1.0)
    r = both(s)
    assert r["estimate"] == -100.0 and r["capability"] == "❌"


def test_no_difference_identical_arms():
    s = make_spec([0] * 10, noise=0.2, seed=3)
    for p in s["pairs"]:
        p["plug"] = dict(p["base"])
    r = both(s)
    assert r["estimate"] == 0 and r["interval"] == [0.0, 0.0] and r["capability"] == "➖"


def test_single_scenario_never_formal_and_unsure():
    s = make_spec([40], reruns=10)
    r = both(s)
    assert r["capability_observed"] == "❓"
    assert r["release_state"] == V.REL_TRIAL and r["capability"] is None
    assert r["interval"][0] == r["interval"][1]  # 只有一个场景时区间退化为一点——不代表证据充分
    assert any("有效样本不足" in x for x in r["reasons"])


def test_few_scenarios_narrow_interval_still_unsure():
    r = both(make_spec([20, 21, 22], reruns=3, gates={k: True for k in V.GATE_KEYS}, plan=True))
    assert r["half_width"] < 5 and r["capability_observed"] == "❓" and r["capability"] is None


def test_missing_pair_side_rejected():
    s = make_spec([10] * 8)
    s["pairs"][4]["base"] = None
    r = V.analyze(s)
    assert r["release_state"] == V.REL_PENDING and r["errors"][0]["code"] == "MISSING_PAIR_SIDE"


def test_missing_planned_pair_invalidates_batch():
    s = make_spec([10] * 8)
    del s["pairs"][5]
    r = V.analyze(s)
    assert r["run_state"] == V.RUN_INVALID and r["capability"] is None
    assert r["errors"][0]["code"] == "SAMPLE_PLAN_INCOMPLETE" and r["errors"][0]["objects"] == ["S1"]


def test_item_mismatch_between_sides_rejected():
    s = make_spec([10] * 8)
    s["pairs"][0]["plug"].pop("S0q0")
    assert V.analyze(s)["errors"][0]["code"] == "ITEM_MISMATCH"


@pytest.mark.parametrize("mut,code", [
    (lambda W: W.__setitem__("S0q0", -1.0), "BAD_WEIGHTS"),
    (lambda W: W.__setitem__("S0q0", float("nan")), "BAD_WEIGHTS"),
    (lambda W: W.pop("S0q0"), "WEIGHT_MISSING"),
    (lambda W: [W.__setitem__(k, 0.0) for k in W], "BAD_WEIGHTS"),
])
def test_wrong_weights_rejected(mut, code):
    s = make_spec([10] * 8)
    mut(s["weights"])
    r = V.analyze(s)
    assert r["release_state"] == V.REL_PENDING and r["errors"][0]["code"] == code


def test_weights_must_match_registered_hash():
    s = make_spec([10] * 8)
    s["weights_sha256"] = V.weights_sha256(s["weights"])
    assert V.analyze(s)["capability"] == "✅"
    s["weights"]["S0q0"] = 2.0
    assert V.analyze(s)["errors"][0]["code"] == "WEIGHTS_HASH_MISMATCH"


def test_invalid_runs_mixed_in_are_excluded_whole_pair():
    s = make_spec([10] * 8, noise=0.1, seed=5)
    clean = V.analyze(s)
    bad = {"pair_id": "S0-junk", "scenario_id": "S0", "rerun": 99, "valid": False, "invalid_reason": "判分器故障",
           "base": {q: 0.0 for q in s["pairs"][0]["base"]}, "plug": {q: 1.0 for q in s["pairs"][0]["base"]}}
    s2 = dict(s, pairs=s["pairs"] + [bad])
    mixed = V.analyze(s2)
    assert V.compare_normalized(clean, mixed) == []
    assert mixed["excluded_pairs"] == [{"pair_id": "S0-junk", "scenario_id": "S0", "reason": "判分器故障"}]
    # 无效运行顶替了计划内配对 → 计划不完整 → 实验无效/待重跑，绝不悄悄转成"还说不准"
    s3 = dict(s, pairs=[dict(p, valid=False, invalid_reason="环境崩") if p["pair_id"] == "S2-r1" else p for p in s["pairs"]])
    r3 = V.analyze(s3)
    assert r3["run_state"] == V.RUN_INVALID and r3["capability"] is None and r3["capability_observed"] is None


def test_frozen_rng_or_version_mismatch_refused():
    for fr in ({"rng": "pcg64/numpy-2"}, {"impl_version": "0.9.0"}, {"percentile": "nearest-rank"}):
        s = make_spec([10] * 8); s["frozen"] = fr
        r = V.analyze(s)
        assert r["release_state"] == V.REL_PENDING and r["errors"][0]["code"] == "ALGORITHM_MISMATCH"
    s = make_spec([10] * 8); s["frozen"] = V.frozen_algorithm()
    assert V.analyze(s)["capability"] == "✅"


def test_different_seed_changes_interval_and_is_detected():
    s1 = make_spec([4, 6, 2, 9, 5, 7, 3, 8], noise=0.1, seed=9, aid="A-1")
    s2 = dict(s1, analysis_id="A-2")
    r1, r1b, r2 = V.analyze(s1), V.analyze(s1), V.analyze(s2)
    assert V.compare_normalized(r1, r1b) == []
    assert r1["estimate"] == r2["estimate"]
    assert V.compare_normalized(r1, r2) != []   # 换种子/换 RNG 不能冒充同一分析


def test_algorithm_not_validated_blocks_interval():
    s = make_spec([10] * 8, gates={**GATES_OK, "algorithm_validated": False})
    r = V.analyze(s)
    assert r["release_state"] == V.REL_PENDING and r["interval"] is None and r["capability"] is None


def test_gates_missing_gives_method_trial_not_formal_label():
    s = make_spec([10] * 8, gates={**GATES_OK, "independent_review": False})
    r = V.analyze(s)
    assert r["release_state"] == V.REL_TRIAL and r["capability"] is None and r["capability_observed"] == "✅"


def test_formal_requires_planned_scenarios_meet_domain_minimum():
    s = make_spec([10] * 8)
    s["params"] = {"min_scenarios": 10}
    r = V.analyze(s)
    assert r["release_state"] == V.REL_TRIAL


def test_seed_derivation():
    aid = "pes/v3/B/dsh-vs-null/2026-10-10"
    expect = int.from_bytes(hashlib.sha256(aid.encode()).digest()[:8], "big")
    assert V.seed_from_analysis_id(aid) == expect == R.seed_of(aid)
    m = V.build_manifest(make_spec([1] * 8, aid=aid))
    for k in ("rng", "percentile", "aggregation_order", "B", "python", "impl_file_sha256", "seed", "scenario_weighting"):
        assert m[k] is not None
    assert m["seed"] == expect and m["B"] == 10000


def test_splitmix_known_vector():
    # SplitMix64 参考向量（seed=0 首三个输出，来自 Vigna 的 splitmix64.c）
    g = V._splitmix64(0)
    assert [next(g) for _ in range(3)] == [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F]
    assert [int(x) for x in R.splitmix_block(0, 3)] == [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F]


@pytest.mark.parametrize("seed", range(12))
def test_main_equals_reference_random(seed):
    rng = random.Random(100 + seed)
    G = rng.randint(1, 20)
    effects = [rng.gauss(rng.choice([-8, 0, 3, 8]), 6) for _ in range(G)]
    s = make_spec(effects, reruns=rng.randint(1, 5), n_items=rng.randint(1, 8), noise=rng.choice([0, 0.05, 0.2]),
                  seed=seed, aid=f"ref-{seed}", weighting=rng.choice(["equal", "item_weight"]),
                  weights={0: 3.0, 1: 0.5})
    both(s)


@pytest.mark.parametrize("seed", range(4))
def test_main_equals_reference_binary(seed):
    s = make_spec([0.2, 0.1, 0.0, 0.3, 0.15, 0.25, 0.05, 0.2, 0.1], reruns=3, n_items=6, kind="binary", seed=seed,
                  aid=f"bin-{seed}")
    r = both(s)
    assert V.paired_binary_interval(s)["interval"] == r["interval"]


def test_binary_all_success_and_bad_values():
    s = make_spec([0] * 8, base_level=1.0, kind="binary")
    r = V.paired_binary_interval(s)
    assert r["interval"] == [0.0, 0.0] and r["capability"] == "➖"
    s["pairs"][0]["plug"]["S0q0"] = 0.5
    assert V.paired_binary_interval(s)["errors"][0]["code"] == "BAD_BINARY"


def test_single_group_rate_zero_successes():
    r = V.single_group_rate(0, 20)
    assert abs(r["interval"][1] - (1 - 0.025 ** (1 / 20))) < 1e-9
    assert r["display"].startswith("0/20")
    r2 = V.single_group_rate(20, 20)
    assert abs(r2["interval"][0] - 0.025 ** (1 / 20)) < 1e-9
    with pytest.raises(V.AnalysisError):
        V.single_group_rate(3, 2)


def test_no_valid_pairs():
    s = make_spec([10] * 8, plan=False)
    for p in s["pairs"]:
        p["valid"] = False
    r = V.analyze(s)
    assert r["run_state"] == V.RUN_INVALID and r["errors"][0]["code"] == "NO_VALID_PAIRS"


def test_reruns_aggregated_within_scenario_before_resampling():
    # 一个场景重跑 10 次、其他 1 次：场景均值等权，不因重跑多而被放大
    s = make_spec([50] + [0] * 8, reruns=1, plan=False)
    extra = [dict(s["pairs"][0], pair_id=f"S0-x{r}", rerun=100 + r) for r in range(9)]
    s["pairs"] += extra
    r = V.analyze(s)
    assert abs(r["estimate"] - 50 / 9) < 1e-9


def test_scale_max_rescales_to_0_100():
    s = make_spec([10] * 8)
    for p in s["pairs"]:
        for side in ("base", "plug"):
            p[side] = {q: v * 4 for q, v in p[side].items()}
    s["metric"]["scale_max"] = 4.0
    r = both(s)
    assert abs(r["estimate"] - 10) < 1e-9


# ───────── 成本（分母 0 / 负） ─────────
def test_cost_zero_successes():
    r = C.unit_success_cost([{"name": "llm", "value": 1.5}], 0)
    assert r["value"] is None and r["display"].startswith(C.NA_NO_SUCCESS) and "1.5" in r["display"]


def test_cost_negative_or_zero_gain():
    for ps, bs in ((5, 5), (3, 5)):
        r = C.incremental_success_cost([{"name": "x", "value": 2.0}], [{"name": "x", "value": 1.0}], ps, bs)
        assert r["value"] is None and r["display"].startswith(C.NA_NO_GAIN)
        assert r["success_diff"] == ps - bs and r["cost_diff"] == 1.0


def test_cost_negative_counts_and_costs_rejected():
    with pytest.raises(C.CostError):
        C.unit_success_cost([{"name": "x", "value": 1.0}], -1)
    with pytest.raises(C.CostError):
        C.CostItem("x", -0.1)
    with pytest.raises(C.CostError):
        C.CostItem("x", 0.0, status="unmeasured")
    with pytest.raises(C.CostError):
        C.CostItem("x", 1.0, status="estimated")


def test_cost_unmeasured_never_zero():
    t = C.total_cost([{"name": "llm", "value": 1.0}, {"name": "人工", "status": "unmeasured"}])
    assert t["value"] is None and t["display"].startswith(C.NOT_MEASURED)
    u = C.unit_success_cost(t, 4)
    assert u["value"] is None and u["display"].startswith(C.NOT_MEASURED)


def test_cost_normal_and_sheet():
    r = C.incremental_success_cost([{"name": "x", "value": 3.0}], [{"name": "x", "value": 1.0}], 6, 2)
    assert r["value"] == 0.5
    sheet = C.cost_sheet({"items": [{"name": "x", "value": 3.0}], "successes": 6, "failed_cost_included": True, "cache": "冷"},
                         {"items": [{"name": "x", "value": 1.0}], "successes": 2, "failed_cost_included": True})
    assert sheet["plug"]["unit"]["value"] == 0.5 and sheet["base"]["human_ops"] == C.NOT_MEASURED
    with pytest.raises(C.CostError):
        C.cost_sheet({"items": [], "successes": 1}, {"items": [], "successes": 1, "failed_cost_included": True})


# ───────── 标签与失效传播 ─────────
def test_labels_risk_without_basis_is_unassessed():
    l = LB.make_labels("个人", "标准", "低", "可推荐")
    assert l["风险多大"] == "未评估"
    l2 = LB.make_labels("个人", "标准", "低", "可推荐", risk_basis={"权限": "只读"}, risk_reviewed=True)
    assert l2["风险多大"] == "低"
    assert LB.make_labels("个人", "作者自测", "未评估", "可推荐")["现在推不推"] == "待复核"
    with pytest.raises(LB.LabelError):
        LB.make_labels("所有人", "标准", "低", "可推荐")


def test_invalidation_propagates_to_badge():
    edges = [("scorer:v1", "run:r1"), ("scorer:v1", "run:r2"), ("run:r1", "analysis:a1"), ("run:r2", "analysis:a1"),
             ("analysis:a1", "report:x"), ("report:x", "board:memory"), ("report:x", "badge:x"), ("run:r3", "analysis:a2")]
    out = LB.propagate_invalidation(edges, {"scorer:v1"})
    assert out["by_kind"]["badge"] == ["badge:x"] and "analysis:a2" not in out["affected"]
    e = LB.eligibility({"capability": "✅", "release_state": "正式", "completed_on": "2026-10-10", "invalidated": True}, today="2026-10-11")
    assert not e["numeric_rank"] and not e["badge"] and e["evidence_state"] == "证据不完整/待复核"


@pytest.mark.parametrize("mut", [
    lambda s: s["weights"].__setitem__("S0q0", "abc"),
    lambda s: s["pairs"].__setitem__(0, "not-a-dict"),
    lambda s: s.pop("weights"),
    lambda s: s.__setitem__("analysis_id", None),
])
def test_garbage_input_never_raises(mut):
    s = make_spec([10] * 8)
    mut(s)
    r = V.analyze(s)
    assert r["release_state"] == V.REL_PENDING and r["capability"] is None and r["errors"]
