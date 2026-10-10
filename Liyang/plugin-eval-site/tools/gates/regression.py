"""判官回归集（已知正确 / 已知错误 / 边界，各 ≥20）——固定成回归集并可对任意「判分器版本」（模块文件）重跑。

判分器版本 = 考卷 B 判分链路模块文件（缺省 harness/judge.py）的 sha256。回归集冻结在
validation/_gates/regression/regression-set.json（含自身哈希）。LLM 部分走真实 judge_batch（双判官+48 锚上岗考），
判词缓存按 (attempt, 判官实例, key) 复用：同一原始判词下，只有判分器代码不同才会让结果不同。

  python -m tools.gates.regression build
  python -m tools.gates.regression run [--judge-module PATH] [--tag NAME]
"""
from __future__ import annotations
import argparse, importlib.util, json, random, re, sys, types
from pathlib import Path

from tools.gates.common import ROOT, VAL, rjson, wjson, sha256_file, sha256_text, now_cst
from harness import llm, examB
from harness import judge as JB0

RDIR = VAL / "regression"
SET = RDIR / "regression-set.json"
SEED = 20261011
IRREL2 = ["请帮我查一下下周三从北京到广州的高铁票。", "家里的绿萝叶子发黄了，要怎么养？", "推荐一款适合跑步时戴的蓝牙耳机。",
          "我想学做提拉米苏，需要准备哪些材料？"]


def load_judge(path) -> types.ModuleType:
    path = str(path)
    if Path(path).resolve() == (ROOT / "harness/judge.py").resolve():
        return JB0
    name = "judge_under_test_" + sha256_file(path)[:8]
    spec = importlib.util.spec_from_file_location(name, path, submodule_search_locations=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "harness"          # 允许 `from .examB import extract_json`
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _ng(s, n=8):
    s = re.sub(r"\s+", "", s)
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def build():
    from tools.gates.fixtures import B_SWAPS
    cards = examB.load_cards(); by = {c["id"]: c for c in cards}
    used = {a["card"] for a in JB0.build_anchors(cards)}
    el = [c for c in cards if c["id"] not in used and c["id"] not in JB0.DIRTY and c["id"] not in B_SWAPS]
    rng = random.Random(SEED)
    llm_cases = []
    for c in el:
        llm_cases.append({"rid": f"R+{c['id']}", "class": "correct", "card": c["id"], "prediction": c["answer"]["human"]["text"], "expect": "strict"})
    for c in el[:4]:
        t = c["answer"]["human"]["text"]
        llm_cases.append({"rid": f"R+ws{c['id']}", "class": "correct", "card": c["id"], "prediction": "  " + t.rstrip("。？！?!") + " ", "expect": "strict"})
    for c in el:
        g = _ng(c["answer"]["human"]["text"])
        others = [o for o in el if o["id"] != c["id"] and not (_ng(o["answer"]["human"]["text"]) & g)
                  and o["answer"]["human"]["text"][:10] != c["answer"]["human"]["text"][:10]]
        o = rng.choice(others)
        llm_cases.append({"rid": f"R×{c['id']}<{o['id']}", "class": "wrong", "card": c["id"], "prediction": o["answer"]["human"]["text"], "expect": "miss"})
    for i, c in enumerate(el[:4]):
        llm_cases.append({"rid": f"R0{c['id']}", "class": "wrong", "card": c["id"], "prediction": IRREL2[i], "expect": "miss"})
    det = [  # 边界：确定性的判分链路规则（不调模型）
        ("parse_verdict 大写 STRICT", "parse_verdict", ['{"verdict":"STRICT","why":"x"}'], ["strict"]),
        ("parse_verdict 非 JSON 但含字段", "parse_verdict", ['判定 "verdict": "miss" 完'], ["miss"]),
        ("parse_verdict 垃圾输出", "parse_verdict", ["我觉得还行"], ["parse_err"]),
        ("parse_verdict 越界档位 partial", "parse_verdict", ['{"verdict":"partial"}'], ["parse_err"]),
        ("parse_verdict 空串", "parse_verdict", [""], ["parse_err"]),
        ("combine strict+miss 取宽松", "combine", ["strict", "miss"], [["strict", "miss"]]),
        ("combine parse_err+miss", "combine", ["parse_err", "miss"], [["miss", "parse_err"]]),
        ("combine paraphrase+paraphrase", "combine", ["paraphrase", "paraphrase"], [["paraphrase", "paraphrase"]]),
        ("WEIGHT paraphrase=0.5", "weight", ["paraphrase"], [0.5]),
        ("WEIGHT parse_err=0", "weight", ["parse_err"], [0.0]),
        ("WEIGHT miss=0", "weight", ["miss"], [0.0]),
        ("parse_answer 非 JSON → parse_err", "parse_answer", ["没有 JSON", "C-001"], [True]),
        ("parse_answer 代码块包裹 → 可解析", "parse_answer", ['```json\n{"qid":"C-001","prediction":"x","basis":[]}\n```', "C-001"], [False]),
        ("judge prompt 空预测显示（空）", "judge_prompt_has", ["C-001", "", "（空）"], [True]),
        ("judge prompt 盲评：不含文件名", "judge_prompt_lacks_file", ["C-001", "预测"], [True]),
        ("judge prompt 不含臂名/插件名", "judge_prompt_lacks", ["C-001", "预测", "dsh"], [True]),
        ("gate：锚正确率 43/48(0.896) 不过", "gate_acc", [43, 48], [False]),
        ("gate：锚正确率 44/48(0.917) 过", "gate_acc", [44, 48], [True]),
        ("gate：一致率 0.8 但 κ<0.6 不过", "gate_kappa_low", [], [False]),
        ("gate：单类塌缩一致率 1.0 过", "gate_single_class", [], [True]),
        ("leak_filter：起于答案行 → 剔除", "leak_after", ["C-001"], ["drop:after-answer"]),
        ("leak_filter：不可解析 source → 剔除", "leak_unparse", ["C-001"], ["drop:unparseable"]),
        ("leak_filter：跨答案行且对齐 → 截到答案行前", "leak_cross", ["C-001"], ["truncate"]),
        ("check_basis：多空白仍逐字", "basis_ws", ["C-001"], [True]),
        ("check_basis：改一字 → 不可回源", "basis_alter", ["C-001"], [False]),
        ("check_basis：文件名写错 → 不可回源", "basis_wrongfile", ["C-001"], [False]),
    ]
    det_cases = [{"rid": f"RB{i:02d}", "class": "boundary", "name": n, "op": op, "args": a, "expect": e[0]} for i, (n, op, a, e) in enumerate(det, 1)]
    obj = {"created": now_cst(), "seed": SEED, "cards_sha256": sha256_file(examB.CARDS_JSON),
           "counts": {k: sum(1 for x in llm_cases + det_cases if x["class"] == k) for k in ("correct", "wrong", "boundary")},
           "llm_cases": llm_cases, "boundary_cases": det_cases}
    obj["set_sha256"] = sha256_text(json.dumps({k: obj[k] for k in ("llm_cases", "boundary_cases")}, ensure_ascii=False, sort_keys=True))
    wjson(SET, obj)
    print(obj["counts"], obj["set_sha256"][:16])


def run_boundary(J, case):
    op, a = case["op"], case["args"]
    by = {c["id"]: c for c in examB.load_cards()}
    if op == "parse_verdict":
        return J.parse_verdict(a[0])[0]
    if op == "combine":
        return list(J.combine(*a))
    if op == "weight":
        return J.WEIGHT[a[0]]
    if op == "parse_answer":
        return examB.parse_answer(a[0], a[1])["parse_err"]
    if op == "judge_prompt_has":
        return a[2] in J.judge_messages(by[a[0]], a[1])[1]["content"]
    if op == "judge_prompt_lacks_file":
        c = by[a[0]]; m = json.dumps(J.judge_messages(c, a[1]), ensure_ascii=False)
        return c["file"] not in m and c["file"].replace(".md", "") not in m
    if op == "judge_prompt_lacks":
        return a[2] not in json.dumps(J.judge_messages(by[a[0]], a[1]), ensure_ascii=False)
    if op == "gate_acc":
        k, n = a
        rows = [{"v1": "strict" if i < k else "miss", "v2": "strict" if i < k else "miss", "expect": "strict"} for i in range(n // 2)] + \
               [{"v1": "miss", "v2": "miss", "expect": "miss"} for _ in range(n // 2)]
        # 让 j1 错 n-k 个：把前 n-k 个正锚改错
        rows = [{"v1": "strict", "v2": "strict", "expect": "strict"} for _ in range(n // 2)] + [{"v1": "miss", "v2": "miss", "expect": "miss"} for _ in range(n // 2)]
        for i in range(n - k):
            rows[i]["v1"] = rows[i]["v2"] = "miss"
        return J.gate_check(rows, [{"v1": "strict", "v2": "strict"}])["pass"]
    if op == "gate_kappa_low":
        anc = [{"v1": "strict", "v2": "strict", "expect": "strict"}] * 24 + [{"v1": "miss", "v2": "miss", "expect": "miss"}] * 24
        items = [{"v1": "strict", "v2": "strict"}] * 80 + [{"v1": "strict", "v2": "paraphrase"}] * 20
        return J.gate_check(anc, items)["pass"]
    if op == "gate_single_class":
        anc = [{"v1": "strict", "v2": "strict", "expect": "strict"}] * 24 + [{"v1": "miss", "v2": "miss", "expect": "miss"}] * 24
        return J.gate_check(anc, [{"v1": "miss", "v2": "miss"}] * 10)["pass"]
    c = by[a[0]]; cut = int(c["answer"]["human"]["line"]); f = c["file"]; L = examB.corpus_lines(f)
    if op == "leak_after":
        return examB.leak_filter([{"text": "x", "source": f"{f}#L{cut}-L{cut + 2}"}], c)[1][0]["action"]
    if op == "leak_unparse":
        return examB.leak_filter([{"text": "x", "source": None}], c)[1][0]["action"]
    if op == "leak_cross":
        s, e = cut - 3, cut + 2
        act = examB.leak_filter([{"text": "\n".join(L[s - 1:e]), "source": f"{f}#L{s}-L{e}"}], c)[1][0]["action"]
        return "truncate" if act.startswith("truncate") else act
    p = c["pre"][-1]
    if op == "basis_ws":
        return examB.check_basis([{"file": f, "line": p["line"], "quote": " ".join(p["text"][:30])}])[0]["verbatim"]
    if op == "basis_alter":
        q = p["text"][:30]; q = q[:10] + ("甲" if q[10] != "甲" else "乙") + q[11:]
        return examB.check_basis([{"file": f, "line": p["line"], "quote": q}])[0]["verbatim"]
    if op == "basis_wrongfile":
        return examB.check_basis([{"file": "不存在.md", "line": p["line"], "quote": p["text"][:30]}])[0]["verbatim"]
    raise ValueError(op)


def run(judge_module=str(ROOT / "harness/judge.py"), tag="original", llm_ok=True):
    J = load_judge(judge_module)
    S = rjson(SET)
    jhash = sha256_file(judge_module)
    out = RDIR / f"run_{tag}"; out.mkdir(parents=True, exist_ok=True)
    results = []
    for c in S["boundary_cases"]:
        try:
            got = run_boundary(J, c)
        except Exception as e:
            got = f"EXC {e!r}"
        results.append({"rid": c["rid"], "class": "boundary", "name": c["name"], "expect": c["expect"], "got": got, "pass": got == c["expect"]})
    batch = None
    if llm_ok:
        from harness.recorder import Recorder
        cards = examB.load_cards(); by = {c["id"]: c for c in cards}
        rec = Recorder(out / "recording.jsonl", f"regress_{tag}", resume=(out / "recording.jsonl").exists())
        items = [{"key": x["rid"], "card": x["card"], "prediction": x["prediction"], "auto": None} for x in S["llm_cases"]]
        batch = J.judge_batch(by, items, J.build_anchors(cards), rec,
                              make_client=lambda role: llm.Client(role, temperature=0.0, max_tokens=600),
                              concurrency=3, batch_tag="gate_regress_B", cache_path=str(RDIR / "verdicts.jsonl"))
        rec.close()
        rows = {r["key"]: r for r in batch["items"]}
        for x in S["llm_cases"]:
            r = rows[x["rid"]]
            results.append({"rid": x["rid"], "class": x["class"], "card": x["card"], "expect": x["expect"], "got": r["final"],
                            "v1": r["v1"], "v2": r["v2"], "pass": r["final"] == x["expect"]})
    fails = [r for r in results if not r["pass"]]
    summ = {"judge_module": str(judge_module), "judge_sha256": jhash, "tag": tag, "set_sha256": S["set_sha256"], "at": now_cst(),
            "n": len(results), "by_class": {k: {"n": sum(1 for r in results if r["class"] == k), "pass": sum(1 for r in results if r["class"] == k and r["pass"])}
                                            for k in ("correct", "wrong", "boundary")},
            "batch_status": batch and batch["status"], "batch_gate_pass": batch and batch["gate"]["pass"],
            "all_pass": not fails, "fails": fails}
    wjson(out / "result.json", {"summary": summ, "results": results})
    return summ


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--judge-module", default=str(ROOT / "harness/judge.py"))
    ap.add_argument("--tag", default="original"); ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    if a.cmd == "build":
        build()
    else:
        s = run(a.judge_module, a.tag, not a.no_llm)
        print(json.dumps({k: v for k, v in s.items() if k != "fails"}, ensure_ascii=False, indent=1), "\nfails:", json.dumps(s["fails"], ensure_ascii=False)[:2000])
