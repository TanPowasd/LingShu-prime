#!/usr/bin/env python3
"""灵枢 lingshu 自建测评体系（榜单依据）一键入口。

用法：
  python evalsuite/run_all.py \
      --snap base=/workspace/work/ls/upstream@2bb8291 \
      --snap integrated=/workspace/work/ls/integrated \
      --snap ng=/workspace/work/ls/rewrite
快照写法：name=path[@git-rev][#impl]
  - @rev：用 `git archive <rev>` 把该提交冻结到 evalsuite/out/_snapcache/<name>-<rev>/ 再测（工作树在变也不影响）。
  - #impl：legacy（lingshu.core 旧引擎）或 ng（lingshu_ng.compat 门面）。缺省：name 为 ng / ng-* 时取 ng，否则 legacy。
维度：probes（缺陷探针）· props（性质测试）· perf（性能）· quality（AST 代码质量）· legacy（bench/probes 旧探针附表，不计分）。
每个探针 / 性质 / 性能档各起一个子进程并带超时，互不影响。
"""
import argparse
import datetime
import json
import math
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import run_child, list_items, pmap, child_env  # noqa: E402
import quality  # noqa: E402

RULES_VERSION = "evalsuite-rules-v1（2026-10-09 固定，先于 ng 首次读数提交）"
WEIGHTS = {"probes": 0.40, "props": 0.30, "perf": 0.15, "quality": 0.15}
PERF_OPS = ["add", "recall", "decay_cycle", "self_check", "activation"]
QUALITY_KEYS = [("max_module_lines", 1.0), ("max_func_len", 1.0), ("cc_max", 1.0), ("cc_mean", 0.1),
                ("mean_func_len", 1.0), ("cc_over_10_per100", 1.0), ("dup_rate", 0.01)]


# ---------------------------------------------------------------- 快照

def parse_snap(s, cache):
    name, rest = s.split("=", 1)
    if rest in ("none", "NA", "-"):
        return {"name": name, "src": "-", "impl": "ng" if name.startswith("ng") else "legacy", "rev": None,
                "root": None, "placeholder": True, "commit": ""}
    impl = None
    if "#" in rest:
        rest, impl = rest.rsplit("#", 1)
    rev = None
    if "@" in rest:
        rest, rev = rest.rsplit("@", 1)
    path = os.path.abspath(rest)
    impl = impl or ("ng" if name == "ng" or name.startswith("ng-") else "legacy")
    meta = {"name": name, "src": path, "impl": impl, "rev": rev}
    if rev:
        dst = os.path.join(cache, f"{name}-{rev}")
        if not os.path.isdir(os.path.join(dst, "lingshu")):
            os.makedirs(dst, exist_ok=True)
            arch = subprocess.run(["git", "-C", path, "archive", rev], capture_output=True, check=True).stdout
            subprocess.run(["tar", "-x", "-C", dst], input=arch, check=True)
        meta["root"] = dst
        meta["commit"] = _git(path, ["rev-parse", rev])
        meta["dirty"] = False
    else:
        meta["root"] = path
        meta["commit"] = _git(path, ["rev-parse", "HEAD"])
        meta["dirty"] = bool(_git(path, ["status", "--porcelain", "--untracked-files=no"]))
        meta["branch"] = _git(path, ["rev-parse", "--abbrev-ref", "HEAD"])
    return meta


def _git(path, args):
    try:
        return subprocess.run(["git", "-C", path] + args, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ""


# ---------------------------------------------------------------- 各维度

PH = {"verdict": "NA", "reading": "快照未提供（占位列）", "sec": 0}


def _job(s, args, timeout):
    if s.get("placeholder"):
        return lambda: dict(PH)
    return lambda: run_child(s["root"], s["impl"], args, timeout)


def run_probes(snaps, ids, workers, timeout):
    jobs = [((s["name"], pid), _job(s, ["--probe", pid], timeout)) for s in snaps for pid in ids]
    res = pmap(jobs, workers)
    return {s["name"]: {pid: res[(s["name"], pid)] for pid in ids} for s in snaps}


def run_props(snaps, ids, workers, timeout, seeds):
    jobs = [((s["name"], pid), _job(s, ["--prop", pid, "--seeds", str(seeds)], timeout)) for s in snaps for pid in ids]
    res = pmap(jobs, workers)
    return {s["name"]: {pid: res[(s["name"], pid)] for pid in ids} for s in snaps}


def run_perf(snaps, sizes, t_small, t_big, rounds=2):
    """按规模交错跑各快照（base,integrated,ng,base,integrated,ng…），每格取各轮中位数里的最小值，
    以削弱共享机器上的负载漂移对某一个快照的偏置。"""
    out = {s["name"]: {} for s in snaps}
    for n in sizes:
        to = t_big if n >= 50000 else t_small
        runs = {s["name"]: [] for s in snaps}
        for rd in range(rounds):
            for s in snaps:
                if s.get("placeholder"):
                    continue
                r = run_child(s["root"], s["impl"], ["--perf", str(n)], to)
                runs[s["name"]].append(r)
                print(f"  perf {s['name']:12s} N={n:<6d} round{rd} {r.get('verdict')} {r.get('sec')}s", flush=True)
                if r.get("verdict") != "OK":
                    break
        for s in snaps:
            if s.get("placeholder"):
                out[s["name"]][str(n)] = dict(PH)
                continue
            ok = [r for r in runs[s["name"]] if r.get("verdict") == "OK"]
            if not ok:
                out[s["name"]][str(n)] = runs[s["name"]][-1] if runs[s["name"]] else {"verdict": "NA"}
                continue
            best = dict(ok[0])
            for op in PERF_OPS + ["build_s", "first_read_ms", "maxrss_mb"]:
                vals = [r.get(op) for r in ok if r.get(op) is not None]
                best[op] = min(vals) if vals else None
            best["rounds"] = len(ok)
            m = run_child(s["root"], s["impl"], ["--perf", str(n), "--trace"], to * 3)
            best["py_peak_mb"] = m.get("py_peak_mb")
            out[s["name"]][str(n)] = best
    return out


def run_legacy_bench(snaps, probe_dir, workers, timeout):
    """bench/probes 旧探针（直接用旧 API）：附表，不计分；ng 快照记 NA（旧探针不经适配层）。"""
    import glob
    files = sorted(glob.glob(os.path.join(probe_dir, "*.py")))
    out = {}

    def one(root, f):
        env = child_env(root)
        env["PYTHONPATH"] = root
        t0 = time.perf_counter()
        try:
            p = subprocess.run([sys.executable, f], cwd=root, env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"verdict": "TIMEOUT", "sec": round(time.perf_counter() - t0, 2), "reading": f"超时 {timeout}s"}
        v, d = "ERR", ((p.stdout + p.stderr).strip().splitlines() or ["<no output>"])[-1][:160]
        for line in (p.stdout + p.stderr).splitlines():
            s = line.strip()
            if s.startswith("BUG"):
                v, d = "BUG", s[:160]
            elif s.startswith("OK"):
                v, d = "OK", s[:160]
        return {"verdict": v, "reading": d, "sec": round(time.perf_counter() - t0, 2)}
    jobs = []
    for s in snaps:
        for f in files:
            pid = os.path.splitext(os.path.basename(f))[0]
            if s["impl"] == "ng" or s.get("placeholder"):
                out.setdefault(s["name"], {})[pid] = {"verdict": "NA", "reading": "旧 API 直连探针，不经适配层", "sec": 0}
            else:
                jobs.append(((s["name"], pid), (lambda r=s["root"], f=f: one(r, f))))
    res = pmap(jobs, workers)
    for (n, pid), r in res.items():
        out.setdefault(n, {})[pid] = r
    return out


# ---------------------------------------------------------------- 计分（规则固定，见 RULES_MD）

def score_probes(r):
    tot = len(r)
    ok = sum(1 for v in r.values() if v["verdict"] == "OK")
    return 100.0 * ok / max(tot, 1)


def score_props(r):
    vals = []
    for v in r.values():
        if v["verdict"] in ("OK", "VIOL"):
            vals.append(1.0 - float(v.get("rate", 1.0)))
        else:
            vals.append(0.0)
    return 100.0 * sum(vals) / max(len(vals), 1)


def _rel_lower_better(values, eps):
    """{snap: value or None} → {snap: score∈[0,1]}；最优者 1，其余 (best+eps)/(v+eps)；缺失 0。"""
    good = [v for v in values.values() if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not good:
        return {k: 0.0 for k in values}
    best = min(good)
    return {k: (0.0 if v is None else (best + eps) / (v + eps)) for k, v in values.items()}


def score_perf(perf, names, sizes):
    cells = {n: [] for n in names}
    for size in sizes:
        for op in PERF_OPS + ["py_peak_mb"]:
            vals = {}
            for n in names:
                r = perf.get(n, {}).get(str(size), {})
                vals[n] = r.get(op) if r.get("verdict") == "OK" else None
            for n, s in _rel_lower_better(vals, 1e-3).items():
                cells[n].append(s)
    return {n: 100.0 * sum(c) / max(len(c), 1) for n, c in cells.items()}


def quality_values(q):
    if not q.get("available"):
        return {k: None for k, _ in QUALITY_KEYS}
    return {"max_module_lines": q["max_module"]["lines"], "max_func_len": q["max_func"]["len"] if q["max_func"] else 0,
            "cc_max": q["cc_top10"][0]["cc"] if q["cc_top10"] else 0, "cc_mean": q["cc_mean"],
            "mean_func_len": q["mean_func_len"], "cc_over_10_per100": round(100.0 * q["cc_over_10"] / max(q["functions"], 1), 2),
            "dup_rate": q["dup_rate"]}


def score_quality(qual, names):
    cells = {n: [] for n in names}
    vals = {n: quality_values(qual[n]) for n in names}
    for k, eps in QUALITY_KEYS:
        for n, s in _rel_lower_better({n: vals[n][k] for n in names}, eps).items():
            cells[n].append(s)
    return {n: 100.0 * sum(c) / max(len(c), 1) for n, c in cells.items()}


RULES_MD = f"""## 总分规则（{RULES_VERSION}）

规则在跑 ng 之前固定并随本文件提交；对所有快照同一套代码、同一组探针 / 种子 / 规模，不按快照调整。

- **总分 = 0.40·探针分 + 0.30·性质分 + 0.15·性能分 + 0.15·质量分**（各维度 0–100）。正确性（前两项）占 70%。
- **探针分** = OK 数 / 探针总数 × 100。分母恒为全部探针；BUG、ERR（崩溃）、TIMEOUT、**NA（未实现/导入失败）一律计 0**——未实现不能靠缺席提分，但 NA 单列，便于区分「没做」和「做错」。
- **性质分** = 各性质 (1 − 违反率) 的平均 × 100；每条性质固定种子 0..N−1（默认 N=200）。NA/ERR/TIMEOUT 的性质计 0。
- **性能分**：每个 (规模, 操作) 格与「本次参评快照中最优者」比：得分 = (最优+ε)/(本快照+ε)，最优者 1，缺失 / 超时 0；
  格子 = {{add, recall, decay_cycle, self_check, activation 的中位耗时, Python 堆峰值}} × 规模；取平均 × 100。
  这是**相对分**：加入新快照会改变其他快照的性能分，但不改变排序原则；原始毫秒数另表列出。
  各快照按规模**交错**测 2 轮，每格取两轮中位数的较小者（削弱共享机器负载漂移的偏置）。
- **质量分**：7 项越低越好的 AST 指标（最大模块行数、最大函数行数、最大圈复杂度、平均圈复杂度、平均函数长度、
  每百函数中 CC>10 的个数、重复代码块率），同样按「相对最优」计分后平均 × 100。
  范围：legacy = `lingshu/core/`，ng = `lingshu_ng/`（各自的记忆引擎本体）。实现不可导入（适配层 NA）时质量记 NA、计 0，
  避免半成品靠体量小拿高分。
- **附表**（bench/probes 旧 API 直连探针、各种读数）只展示不计分。
- 修订记录：v1 首次提交（bae8544）后、ng 正式参评前，P06 往返性质改为「本地层逐项等价 + 共享层原样恢复或整条隔离」，
  与探针 i125（无密钥导入不得改写结构层）口径一致；计分公式与权重未改。
"""


# ---------------------------------------------------------------- 报告

def fmt_ms(v):
    return "—" if v is None else (f"{v:.2f}" if v < 100 else f"{v:.0f}")


def render(meta, snaps, probes, props, perf, qual, legacy, items, sizes, scores, args):
    names = [s["name"] for s in snaps]
    L = ["# 灵枢 lingshu 自建测评榜（LEADERBOARD_NG）", "",
         f"生成时间：{meta['generated']}（Asia/Shanghai）· 规则：{RULES_VERSION}"
         + (f" · 本轮复用旧读数的维度：{','.join(meta['reused'])}" if meta.get("reused") else ""), "",
         "## 参评快照", "", "| 快照 | 实现 | 来源 | 提交 | 备注 |", "|---|---|---|---|---|"]
    for s in snaps:
        note = []
        if s.get("rev"):
            note.append(f"冻结于 @{s['rev']}（git archive）")
        if s.get("dirty"):
            note.append("工作树有未提交改动")
        if s.get("placeholder"):
            note.append("占位列：本轮未参评，全部记 NA")
        if s.get("branch"):
            note.append(f"分支 {s['branch']}")
        L.append(f"| {s['name']} | {s['impl']} | `{s['src']}` | `{(s.get('commit') or '?')[:10]}` | {'；'.join(note)} |")
    L += ["", "## 总榜", "", "| 排名 | 快照 | 总分 | 探针分 | 性质分 | 性能分 | 质量分 |", "|---|---|---|---|---|---|---|"]
    order = sorted(names, key=lambda n: -scores[n]["total"])
    for i, n in enumerate(order, 1):
        sc = scores[n]
        if next(x for x in snaps if x["name"] == n).get("placeholder"):
            L.append(f"| — | {n} | NA | NA | NA | NA | NA |")
            continue
        L.append(f"| {i} | {n} | **{sc['total']:.1f}** | {sc['probes']:.1f} | {sc['props']:.1f} | {sc['perf']:.1f} | {sc['quality']:.1f} |")
    L += ["", RULES_MD]

    # 维度一：探针
    pids = sorted((k for k in items["probes"] if k in probes[names[0]]), key=lambda k: (items["probes"][k]["issue"], k))
    L += ["## 维度一 · 缺陷探针榜（行为探针，经 adapters 抽象接口）", "",
          f"探针数：**{len(pids)}**，覆盖上游 core 相关 issue **{len({items['probes'][p]['issue'] for p in pids})}** 个。"
          "OK=缺陷不复现；BUG=仍复现；NA=该实现无此能力（导入失败/未实现）；ERR=探针崩溃；TIMEOUT=超时。", "",
          "| 快照 | OK | BUG | NA | ERR | TIMEOUT | 修复率 |", "|---|---|---|---|---|---|---|"]
    for n in names:
        v = [probes[n][p]["verdict"] for p in pids]
        L.append(f"| {n} | {v.count('OK')} | {v.count('BUG')} | {v.count('NA')} | {v.count('ERR')} | {v.count('TIMEOUT')} | {v.count('OK') / max(len(v), 1):.1%} |")
    L += ["", "<details><summary>逐探针读数</summary>", "", "| 探针 | issue | 说明 | " + " | ".join(names) + " |",
          "|---|---|---|" + "---|" * len(names)]
    for p in pids:
        cells = []
        for n in names:
            r = probes[n][p]
            cells.append(f"**{r['verdict']}** {str(r.get('reading', ''))[:70].replace('|', '/')}")
        L.append(f"| {p} | #{items['probes'][p]['issue']} | {items['probes'][p]['title'][:40].replace('|', '/')} | " + " | ".join(cells) + " |")
    L += ["", "</details>", ""]

    # 维度二：性质
    L += ["## 维度二 · 性质测试（自写随机化框架，每条 %d 个固定种子）" % args.seeds, "",
          "| 性质 | 说明 | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    qids = [p for p in sorted(items["props"]) if p in props[names[0]]]
    for p in qids:
        cells = []
        for n in names:
            r = props[n][p]
            if r["verdict"] in ("OK", "VIOL"):
                cells.append(f"{r['violations']}/{r['seeds']}（{r['rate']:.1%}）")
            else:
                cells.append(r["verdict"])
        L.append(f"| {p} | {items['props'][p]} | " + " | ".join(cells) + " |")
    L += ["", "<details><summary>首个反例</summary>", ""]
    for p in qids:
        for n in names:
            f = props[n][p].get("first")
            if f:
                L.append(f"- `{p}` @ {n}：seed={f['seed']} — {f['detail'][:150]}")
    L += ["", "</details>", ""]

    # 维度三：性能
    L += ["## 维度三 · 性能（中位耗时 ms；文件库；N 个知识节点 + N/10 情境 + N/2 条 DAG 因果边）", "",
          "> 测量机为共享的 2 核沙箱，同一快照两次运行的中位数可差 ±30%（尤其 50k 档）；性能分只占 15%，"
          "跨快照比较请看数量级与趋势，正式结论建议在独占机器上用 `--skip probes,props,legacy,quality` 复跑性能档。", ""]
    for size in sizes:
        L += [f"**N = {size}**", "", "| 快照 | 灌库 s | 首读 ms（不计分） | add | recall | decay_cycle | self_check | activation | Py 堆峰值 MB | maxrss MB |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for n in names:
            r = perf.get(n, {}).get(str(size), {})
            if r.get("verdict") != "OK":
                L.append(f"| {n} | {r.get('verdict', '—')} {str(r.get('reading', ''))[:40]} | | | | | | | | |")
                continue
            L.append(f"| {n} | {r.get('build_s')} | {fmt_ms(r.get('first_read_ms'))} | " + " | ".join(fmt_ms(r.get(op)) for op in PERF_OPS) +
                     f" | {r.get('py_peak_mb', '—')} | {r.get('maxrss_mb')} |")
        L.append("")

    # 维度四：质量
    L += ["## 维度四 · 代码质量（自写 AST 指标）", "",
          "| 快照 | 范围 | 模块数 | 总行数 | 最大模块行数 | 函数数 | 最大函数行数 | 平均函数长度 | 平均 CC | CC>10 个数 | 重复块率 |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in names:
        q = qual[n]
        if not q.get("available"):
            L.append(f"| {n} | `{q.get('scope')}` | NA | | | | | | | | |")
            continue
        L.append(f"| {n} | `{q['scope']}` | {q['modules']} | {q['total_lines']} | {q['max_module']['lines']}（{os.path.basename(q['max_module']['module'])}） | "
                 f"{q['functions']} | {q['max_func']['len']} | {q['mean_func_len']} | {q['cc_mean']} | {q['cc_over_10']} | {q['dup_rate']:.1%} |")
    for n in names:
        q = qual[n]
        if q.get("available"):
            L += ["", f"<details><summary>{n} · 圈复杂度 top10</summary>", "", "| 函数 | CC | 行数 |", "|---|---|---|"]
            for f in q["cc_top10"]:
                L.append(f"| `{f['func']}` | {f['cc']} | {f['len']} |")
            L += ["", "</details>"]
    L.append("")

    # 附表
    if legacy:
        lp = sorted(next(iter(legacy.values())).keys())
        L += ["## 附表 · bench/probes 旧 API 直连探针（不计分）", "", "| 快照 | OK | BUG | ERR/TIMEOUT | NA |", "|---|---|---|---|---|"]
        for n in names:
            v = [legacy.get(n, {}).get(p, {}).get("verdict", "NA") for p in lp]
            L.append(f"| {n} | {v.count('OK')} | {v.count('BUG')} | {v.count('ERR') + v.count('TIMEOUT')} | {v.count('NA')} |")
        L += ["", "<details><summary>逐探针</summary>", "", "| 探针 | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
        for p in lp:
            L.append(f"| {p} | " + " | ".join(legacy.get(n, {}).get(p, {}).get("verdict", "NA") for n in names) + " |")
        L += ["", "</details>", ""]

    L += ["## 复跑", "", "```bash", "cd /workspace/work/ls/rewrite", "python3 evalsuite/run_all.py \\",
          "  --snap base=/workspace/work/ls/upstream@2bb8291 \\", "  --snap integrated=/workspace/work/ls/integrated \\",
          "  --snap ng=/workspace/work/ls/rewrite        # name=ng → 走 lingshu_ng.compat 门面", "```", "",
          "单个探针：`PYTHONPATH=<快照根>:evalsuite python3 evalsuite/probe_runner.py --impl legacy|ng --probe <id>`；"
          "单条性质：`... --prop <id> --seeds 200`；性能：`... --perf 10000 [--trace]`。", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snap", action="append", required=True)
    ap.add_argument("--workers", type=int, default=max(2, (os.cpu_count() or 2) * 2))
    ap.add_argument("--probe-timeout", type=float, default=60)
    ap.add_argument("--prop-timeout", type=float, default=600)
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--sizes", default="1000,10000,50000")
    ap.add_argument("--perf-timeout", type=float, default=300, help="1k/10k 档单进程超时")
    ap.add_argument("--perf-big-timeout", type=float, default=60, help="50k 档单进程超时（题设：60s 内可完成才计）")
    ap.add_argument("--skip", default="", help="逗号分隔：probes,props,perf,quality,legacy")
    ap.add_argument("--only", default="", help="只跑这些探针/性质 id（逗号分隔，调试用）")
    ap.add_argument("--reuse", help="被 --skip 的维度从这个旧 leaderboard.json 取读数（同名快照）")
    ap.add_argument("--perf-rounds", type=int, default=2)
    ap.add_argument("--legacy-probes", default=os.path.join(os.path.dirname(HERE), "bench", "probes"))
    ap.add_argument("--out", default=os.path.join(HERE, "out", "leaderboard.json"))
    ap.add_argument("--md", default=os.path.join(HERE, "LEADERBOARD_NG.md"))
    a = ap.parse_args()
    skip = set(x for x in a.skip.split(",") if x)
    cache = os.path.join(HERE, "out", "_snapcache")
    snaps = [parse_snap(s, cache) for s in a.snap]
    names = [s["name"] for s in snaps]
    sizes = [int(x) for x in a.sizes.split(",") if x]
    legacy_root = next((s["root"] for s in snaps if s["impl"] == "legacy" and s["root"]), HERE)
    items = list_items(legacy_root)   # 探针/性质清单与实现无关（只注册，不导入被测包）
    only = set(x for x in a.only.split(",") if x)
    pids = [p for p in sorted(items["probes"]) if not only or p in only]
    qids = [p for p in sorted(items["props"]) if not only or p in only]
    t0 = time.time()
    print(f"[evalsuite] 快照={names} 探针={len(pids)} 性质={len(qids)} workers={a.workers}", flush=True)

    probes = run_probes(snaps, pids, a.workers, a.probe_timeout) if "probes" not in skip else {n: {} for n in names}
    print(f"[evalsuite] probes 完成 {time.time() - t0:.0f}s", flush=True)
    props = run_props(snaps, qids, max(1, a.workers // 2), a.prop_timeout, a.seeds) if "props" not in skip else {n: {} for n in names}
    print(f"[evalsuite] props 完成 {time.time() - t0:.0f}s", flush=True)
    legacy = run_legacy_bench(snaps, a.legacy_probes, a.workers, 120) if "legacy" not in skip and os.path.isdir(a.legacy_probes) else {}
    print(f"[evalsuite] legacy 附表完成 {time.time() - t0:.0f}s", flush=True)
    perf = run_perf(snaps, sizes, a.perf_timeout, a.perf_big_timeout, a.perf_rounds) if "perf" not in skip else {}
    if a.reuse:
        old = json.load(open(a.reuse))
        if "probes" in skip:
            probes = {n: old["probes"].get(n, {}) for n in names}
        if "props" in skip:
            props = {n: old["props"].get(n, {}) for n in names}
        if "legacy" in skip:
            legacy = {n: old["legacy_bench"].get(n, {}) for n in names}
        if "perf" in skip:
            perf = {n: old["perf"].get(n, {}) for n in names}
    print(f"[evalsuite] perf 完成 {time.time() - t0:.0f}s", flush=True)
    qual = {}
    for s in snaps:
        chk = dict(PH) if s.get("placeholder") else run_child(s["root"], s["impl"], ["--check"], 120)
        s["importable"] = chk.get("verdict") == "OK"
        s["import_detail"] = chk.get("reading")
        if "quality" in skip:
            qual[s["name"]] = {"available": False, "scope": "-"}
        elif not s["importable"]:
            qual[s["name"]] = {"available": False, "scope": "实现不可导入：" + str(chk.get("reading"))[:80]}
        else:
            qual[s["name"]] = quality.analyze(s["root"], s["impl"])

    sp = {n: score_probes(probes[n]) if probes[n] else 0.0 for n in names}
    sq = {n: score_props(props[n]) if props[n] else 0.0 for n in names}
    sf = score_perf(perf, names, sizes) if perf else {n: 0.0 for n in names}
    sc = score_quality(qual, names)
    scores = {n: {"probes": sp[n], "props": sq[n], "perf": sf[n], "quality": sc[n],
                  "total": WEIGHTS["probes"] * sp[n] + WEIGHTS["props"] * sq[n] + WEIGHTS["perf"] * sf[n] + WEIGHTS["quality"] * sc[n]}
              for n in names}
    meta = {"generated": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
            "rules": RULES_VERSION, "weights": WEIGHTS, "seeds": a.seeds, "sizes": sizes,
            "python": sys.version.split()[0], "elapsed_s": round(time.time() - t0, 1),
            "reused": sorted(skip) if a.reuse else []}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"meta": meta, "snapshots": snaps, "scores": scores, "items": items,
               "probes": probes, "props": props, "perf": perf, "quality": qual, "legacy_bench": legacy},
              open(a.out, "w"), ensure_ascii=False, indent=1)
    md = render(meta, snaps, probes, props, perf, qual, legacy, items, sizes, scores, a)
    open(a.md, "w").write(md)
    print(f"[evalsuite] 完成 {time.time() - t0:.0f}s → {a.out} / {a.md}")
    for n in sorted(names, key=lambda n: -scores[n]["total"]):
        s = scores[n]
        print(f"  {n:12s} 总分 {s['total']:6.1f} | 探针 {s['probes']:5.1f} 性质 {s['props']:5.1f} 性能 {s['perf']:5.1f} 质量 {s['quality']:5.1f}")


if __name__ == "__main__":
    main()
