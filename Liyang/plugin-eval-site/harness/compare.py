"""对比与出单：底子臂 vs 插件臂 → 四结论 + 三张单子（分开输出，绝不合成总分）+ 扣分点录像引用校验。

  python -m harness.compare --base runs/B_null --plug runs/B_bm25 --out reports/B_bm25_vs_null
"""
from __future__ import annotations
import argparse, json, statistics
from pathlib import Path

from .classify import THRESH, classify, fmt_items
from .recorder import cite, load_events, validate_report

COMPARE_KEYS = ("exam", "generator", "judge", "seeds", "k", "material_cap", "prompt_sha", "cards_sha", "hmb_git")


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def pct(a, b):
    return "—" if not b else f"{round(100 * a / b)}%"


class Arm:
    def __init__(self, d):
        self.d = Path(d)
        self.cfg = rj(self.d / "config.json")
        self.summ = rj(self.d / "summary.json")
        self.state = rj(self.d / "state.json") if (self.d / "state.json").exists() else {}
        self.run_id = self.d.name
        self.rec = self.d / "recording.jsonl"
        self.seeds = self.cfg["seeds"]
        self.judge = {s: rj(self.d / "judge" / f"s{s}.json") for s in self.seeds if (self.d / "judge" / f"s{s}.json").exists()}

    def scores(self):
        out = {}
        for s, j in self.judge.items():
            for r in j["items"]:
                out.setdefault(r["card"], {})[s] = r["score"]
        return out

    def gen(self, qid, s):
        return rj(self.d / "q" / f"{qid}.s{s}.gen.json")

    def recall(self, qid):
        return rj(self.d / "q" / f"{qid}.recall.json")

    def c(self, ev):
        """ev: [seq,t] 或 {"seq","t"} → 引用串。"""
        if ev is None:
            return ""
        if isinstance(ev, dict):
            ev = [ev["seq"], ev["t"]]
        return cite(self.run_id, {"seq": ev[0], "t": ev[1]})

    def token_split(self):
        tot = {}
        for e in load_events(self.rec):
            if e["type"] == "llm.response":
                role = "generator" if e.get("role") == "generator" else "judge"
                u = e.get("usage") or {}
                t = tot.setdefault(role, {"calls": 0, "prompt": 0, "completion": 0, "cost_usd": 0.0})
                t["calls"] += 1; t["prompt"] += u.get("prompt_tokens") or 0; t["completion"] += u.get("completion_tokens") or 0
                t["cost_usd"] += float(e.get("cost_usd") or 0)
            elif e["type"] == "plugin.tokens":
                t = tot.setdefault("plugin", {"calls": 0, "prompt": 0, "completion": 0, "cost_usd": 0.0})
                t["calls"] += 1; t["prompt"] += int(e.get("prompt_tokens") or 0); t["completion"] += int(e.get("completion_tokens") or 0)
        return tot


def header(base, plug, title):
    p = plug.cfg
    return [f"# {title}", "",
            f"- 考卷：B（hive-memory-bench e2e C 型续接预测，题卡 sha `{p['cards_sha']}`，hmb `{p['hmb_git'][:10]}`，{p['n_cards']} 卡）",
            f"- 生成器/判官：`{p['generator']['model']}`（生成 T={p['generator']['temperature']}，判官 T=0，thinking off，双判官独立实例）",
            f"- 插件臂：`{p['plugin_name']}` v{p['plugin_version']}（{p['plugin']}）｜底子臂：`{base.cfg['plugin_name']}`",
            f"- 种子：{p['seeds']}｜k={p['k']}｜材料上限 {p['material_cap']} 字符/卡｜harness `{p['harness_git'][:10]}`",
            f"- 录像：插件臂 `{plug.run_id}`，底子臂 `{base.run_id}`（引用格式 ⟦录像:<run>@mm:ss#seq⟧）", ""]


def arm_table(arms):
    L = ["| 臂 | 种子 | strict | paraphrase | miss | 折合答对（题/满分） | 判官批次 |", "|:--|--:|--:|--:|--:|--:|:--|"]
    for a in arms:
        for s in a.seeds:
            st = a.summ["per_seed"][str(s)]
            w = st["strict"] + 0.5 * st["paraphrase"]
            L.append(f"| {a.cfg['plugin_name']} | {s} | {st['strict']} | {st['paraphrase']} | {st['miss']} | "
                     f"{w:g} / {st['n']} | {st['judge_status']}（第 {st['judge_attempts']} 批，作废 {st['voided_batches']}） |")
    return L


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--plug", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default=None)
    a = ap.parse_args(argv)
    # 考卷 A（config.exam 以 "A/" 开头）分派到 compareA；考卷 B 行为不变
    if str(rj(Path(a.plug) / "config.json").get("exam", "")).startswith("A/"):
        from . import compareA
        return compareA.main(a)
    base, plug = Arm(a.base), Arm(a.plug)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    mism = {k: (base.cfg.get(k), plug.cfg.get(k)) for k in COMPARE_KEYS if base.cfg.get(k) != plug.cfg.get(k)}
    title = a.title or f"{plug.cfg['plugin_name']} vs {base.cfg['plugin_name']} · 考卷 B"
    n = plug.cfg["n_cards"]
    judge_valid = all(j["status"] == "valid" for arm in (base, plug) for j in arm.judge.values()) and \
        len(base.judge) == len(base.seeds) and len(plug.judge) == len(plug.seeds)
    install_ok = bool((plug.state.get("install") or {}).get("ok"))
    cov = 1 - plug.summ.get("recall_errors", 0) / n
    res = classify(base.scores(), plug.scores(), install_ok=install_ok, coverage=cov, judge_valid=judge_valid and not mism)
    if mism:
        res.setdefault("reasons", []).append(f"两臂配置不同：{list(mism)}")

    # ---------- 单 1：能力分 ----------
    L = header(base, plug, f"能力分单 · {title}")
    L += [f"## 结论：{res['verdict']} {res['label']}", ""]
    if "D" in res:
        lo, hi = res["ci_items"]
        L += [f"- 净提升：**{fmt_items(res['items_gain'])} 题**（{n} 题折算，种子均值；95% 配对 bootstrap 区间 {fmt_items(lo)} ～ {fmt_items(hi)} 题）",
              f"- 底子臂折合答对 {round(res['base_mean'] * n)} 题，插件臂 {round(res['plug_mean'] * n)} 题（满分 {n}）",
              f"- 逐种子净提升：" + "，".join(f"s{s} {fmt_items(v * n)} 题" for s, v in res["per_seed_D"].items()),
              f"- 符号检验：插件更好 {res['sign'][0]} 题 / 更差 {res['sign'][1]} 题，双侧 p {'< 0.05' if res['sign'][2] < 0.05 else '≥ 0.05'}"]
    if res.get("reasons"):
        L.append("- 判定理由：" + "；".join(res["reasons"]))
    L += ["", f"判定阈值（SPEC §6）：≥{THRESH['min_seeds']} 种子；✅ 需 95% 区间下界 > 0 且各种子同为正且净提升 ≥ {THRESH['min_effect_items']:g} 题；"
          f"❌ 对称；其余 😐；安装失败/有效作答 < {round(THRESH['min_coverage']*100)}%/判官批次作废未恢复 → 🚧。", "",
          "## 逐臂读数（主口径：双判官一致或取更宽松档）", ""]
    L += arm_table([base, plug])
    # 判官上岗
    L += ["", "## 判官上岗考（每批混入 48 锚；两判官各自达标且一致率达标才批）", "",
          "| 臂 | 种子 | 尝试 | 锚正确率 j1/j2 | 超多数类基线 | 锚一致/κ | 题目一致/κ | 结果 | 录像 |", "|:--|--:|--:|:--|:--|:--|:--|:--|:--|"]
    for arm in (base, plug):
        for s, j in arm.judge.items():
            g = j["gate"]
            L.append(f"| {arm.cfg['plugin_name']} | {s} | {j['attempt']} | {round(g['anchor_acc_v1']*100)}% / {round(g['anchor_acc_v2']*100)}% | "
                     f"+{round(g['anchor_margin_pp_v1'])}pp / +{round(g['anchor_margin_pp_v2'])}pp | {round(g['anchor_agree']*100)}% / {g['anchor_kappa']:.2f} | "
                     f"{round(g['items_agree']*100)}% / {g['items_kappa']:.2f} | {'通过' if g['pass'] else '不通过'} | {arm.c(j.get('gate_ev'))} |")
    # 依据轴
    L += ["", "## 依据轴（答卷引文逐字回源，机械面；与预测力是两条独立轴）", "",
          "| 臂 | basis 条数 | 逐字可回源 | 精确行(±3) | 有依据作答 |", "|:--|--:|--:|--:|--:|"]
    for arm in (base, plug):
        b = arm.summ["basis"]; tot = n * len(arm.seeds)
        L.append(f"| {arm.cfg['plugin_name']} | {b['n']} | {b['verbatim']}（{pct(b['verbatim'], b['n'])}） | {b['line_pm3']} | {b['cards_with_basis']}/{tot} |")
    # 扣分点（插件臂相对底子臂更差的题）
    L += ["", "## 扣分点：插件臂比底子臂更差的题（种子均值）", ""]
    bs, ps = base.scores(), plug.scores()
    worse = sorted([q for q in ps if q in bs and sum(ps[q].values()) < sum(bs[q].values())])
    for q in worse:
        cites = []
        for s in plug.seeds:
            r = next(x for x in plug.judge[s]["items"] if x["card"] == q)
            rb = next(x for x in base.judge[s]["items"] if x["card"] == q)
            cites.append(f"s{s} 插件 {r['final']} {plug.c(r['ev1'])} vs 底子 {rb['final']} {base.c(rb['ev1'])}")
        rc = plug.recall(q)
        L.append(f"- 【扣】{q}：" + "；".join(cites) + f"；材料 {len(rc['material'])} 条 {plug.c(rc['ev'])}")
    if not worse:
        L.append("（无）")
    L += ["", f"逐题全部扣分明细（插件臂每个非 strict 判定）见 `能力分_扣分明细.md`。"]
    (out / "能力分.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    D = header(base, plug, f"能力分 · 扣分明细 · {title}")
    D += ["每行一个扣分点：插件臂某题某种子未得满分（strict）。引用判官 1 判词事件与作答事件。", ""]
    for s in plug.seeds:
        for r in sorted(plug.judge[s]["items"], key=lambda x: x["card"]):
            if r["final"] == "strict":
                continue
            g = plug.gen(r["card"], s)
            why = (r.get("why1") or "").replace("\n", " ")[:120]
            D.append(f"- 【扣】{r['card']} s{s} {r['final']}（j1 {r['v1']}／j2 {r['v2']}）：{why} 判词 {plug.c(r['ev1'])} 作答 {plug.c(g['ev'])}")
    (out / "能力分_扣分明细.md").write_text("\n".join(D) + "\n", encoding="utf-8")

    # ---------- 单 2：好不好用 ----------
    ins, ing = plug.state.get("install") or {}, plug.state.get("ingest") or {}
    U = header(base, plug, f"好不好用单 · {title}")
    U += ["| 项 | 读数 | 录像 |", "|:--|:--|:--|",
          f"| 安装成功 | {'是' if ins.get('ok') else '否'} | {plug.c(ins.get('ev'))} |",
          f"| 安装步数（插件自报，需人工动手的命令数） | {ins.get('steps')} | {plug.c(ins.get('ev'))} |",
          f"| 安装耗时 | {round(ins.get('dur_s') or 0)} 秒 | {plug.c(ins.get('ev'))} |",
          f"| 安装报错 | {len(ins.get('errors') or [])} 条 | {plug.c(ins.get('ev'))} |",
          f"| 写入（ingest）成功 | {'是' if ing.get('ok') else '否'}{'：' + str(ing.get('error')) if ing.get('error') else ''} | {plug.c(ing.get('ev'))} |",
          f"| 检索出错题数 | {plug.summ.get('recall_errors')} / {n} | — |",
          "| 文档可读性 | 人工评定栏（按 SPEC §5.2 清单逐项打勾，附录像/文档链接） | — |", ""]
    for e in ins.get("errors") or []:
        U.append(f"- 【扣】安装报错：{str(e)[:200]} {plug.c(ins.get('ev'))}")
    (out / "好不好用.md").write_text("\n".join(U) + "\n", encoding="utf-8")

    # ---------- 单 3：成本与安全 ----------
    tb, tp = base.token_split(), plug.token_split()
    un = plug.state.get("uninstall") or {}
    lat = plug.state.get("recall_latency_s") or []
    C = header(base, plug, f"成本与安全单 · {title}")
    C += ["## 成本（token 硬数据，来自录像 llm.response.usage）", "", "| 臂 | 角色 | 调用 | prompt tok | completion tok | 网关计费 USD |", "|:--|:--|--:|--:|--:|--:|"]
    for arm, t in ((base, tb), (plug, tp)):
        for role, v in sorted(t.items()):
            C.append(f"| {arm.cfg['plugin_name']} | {role} | {v['calls']} | {v['prompt']} | {v['completion']} | {v['cost_usd']:.4f} |")
    gp = (tp.get("generator", {}).get("prompt", 0) - tb.get("generator", {}).get("prompt", 0))
    C += ["", f"- 插件带来的生成器上下文增量：{gp:+d} prompt tokens（全种子合计；= 插件材料的 token 代价）",
          f"- 写入耗时：{round(ing.get('dur_s') or 0)} 秒 / {ing.get('turns')} 轮 {plug.c(ing.get('ev'))}",
          f"- 检索延迟：中位 {round(statistics.median(lat) * 1000) if lat else '—'} ms，最大 {round(max(lat) * 1000) if lat else '—'} ms（{len(lat)} 次）",
          "", "## 安全", "",
          f"- 声明权限：{plug.state.get('permissions') or '插件未声明'}",
          f"- 沙箱环境是否带评测密钥：{'是（违规）' if plug.state.get('sandbox_env_has_api_key') else '否（CLINE_API_KEY 不进沙箱）'}",
          f"- 安装足迹：新增 {len((ins.get('footprint') or {}).get('added', []))} 个文件 {plug.c(ins.get('ev'))}",
          f"- 卸载后残留（沙箱 diff）：新增 {len((un.get('residue') or {}).get('added', []))} 个文件 / {(un.get('residue') or {}).get('added_bytes', 0)} 字节；"
          f"插件自报残留 {len((un.get('reported') or {}).get('residue_paths', []))} 条；沙箱外 /tmp 新条目 {sum(len(v) for v in ((un.get('residue') or {}).get('outside_new') or {}).values())} 个（粗粒度，可能含并发进程噪声） {plug.c(un.get('ev'))}", ""]
    for pth in ((un.get("residue") or {}).get("added") or [])[:50]:
        C.append(f"- 【扣】卸载残留：`{pth}` {plug.c(un.get('ev'))}")
    (out / "成本与安全.md").write_text("\n".join(C) + "\n", encoding="utf-8")

    # ---------- 校验 + 机读 ----------
    recs = {base.run_id: base.rec, plug.run_id: plug.rec}
    val = {}
    for f in ("能力分.md", "能力分_扣分明细.md", "好不好用.md", "成本与安全.md"):
        v = validate_report((out / f).read_text(encoding="utf-8"), recs)
        val[f] = {k: v[k] for k in ("total", "ok", "pass")} | {"problems": v["problems"][:20]}
    allpass = all(v["pass"] for v in val.values())
    (out / "录像引用校验.json").write_text(json.dumps({"all_pass": allpass, "files": val}, ensure_ascii=False, indent=1), encoding="utf-8")
    res_j = {k: v for k, v in res.items() if k != "thresholds"}
    (out / "结论.json").write_text(json.dumps({"classify": res_j, "config_mismatch": mism, "citation_check_all_pass": allpass},
                                             ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"verdict": res["verdict"], "label": res["label"], "items_gain": res.get("items_gain"),
                      "ci_items": res.get("ci_items"), "citations_all_pass": allpass,
                      "deductions": {f: v["total"] for f, v in val.items()}}, ensure_ascii=False, default=str))
    return 0 if allpass else 1


if __name__ == "__main__":
    raise SystemExit(main())
