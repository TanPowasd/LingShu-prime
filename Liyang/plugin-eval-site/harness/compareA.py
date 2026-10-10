"""考卷 A 对比出单（由 `python -m harness.compare` 按 config.exam 自动分派；考卷 B 行为不变）。

分数口径：上游终裁 pass/fail（pass=1，fail=0）→ 四结论（classify，阈值同 SPEC §6）；
三张单子分开出、绝不合成总分；扣分点录像引用 100% 校验。两套考卷**不合并排名**。
"""
from __future__ import annotations
import json, statistics
from pathlib import Path

from .classify import THRESH, classify, fmt_items
from .compare import Arm, pct
from .recorder import validate_report

COMPARE_KEYS = ("exam", "generator", "judge", "seeds", "k", "material_cap", "prompt_sha", "cards_sha", "hmb_git")


class ArmA(Arm):
    def scores(self, key="final"):
        out = {}
        for s, j in self.judge.items():
            for r in j["items"]:
                out.setdefault(r["qid"], {})[s] = 1.0 if r[key] == "pass" else 0.0
        return out

    def row(self, s, qid):
        return next(x for x in self.judge[s]["items"] if x["qid"] == qid)

    def merged_mean(self, s):
        """诊断（不进结论）：近似上游《秤》「合并均」——规则层覆盖率分为先，进语义层的题以双判官均分为准。"""
        from . import examA
        C, idx = examA.cards(), examA.units()
        J, _ = examA.upstream()
        vals = []
        for r in self.judge[s]["items"]:
            if r.get("sem"):
                vals.append(r["sem"]["mean"]); continue
            res = J.judge(C[r["qid"]], self.gen(r["qid"], s)["resp"], idx)
            a = res["axes"].get("conclusion") or res["axes"].get("coverage") or {}
            vals.append(float(a.get("score", a.get("coverage", 0.0)) or 0.0))
        return round(sum(vals) / len(vals), 3) if vals else None

    def best_ev(self, r):
        if r.get("sem"):
            return r["sem"]["ev1"]
        if r.get("cite"):
            return r["cite"]["ev1"]
        return r["gen_ev"]


def header(base, plug, title):
    p = plug.cfg
    g = p.get("gradable", {})
    return [f"# {title}", "",
            f"- 考卷：**A**（hive-memory-bench 长文章理解《蜂巢世界漫游指南》23 章；可判＝主轮 {g.get('主轮', {}).get('gradable', p['n_cards'])} 题，"
            f"题面+答案键 sha `{p['cards_sha']}`，hmb `{p['hmb_git'][:10]}`，judge.py `{p.get('judge_py_sha')}`，semantic.py `{p.get('semantic_py_sha')}`）",
            f"- **干预轮 {g.get('干预轮', {}).get('n', 92)} 题：不可判、不出分**（{g.get('干预轮', {}).get('note', '')}）",
            f"- 生成器/判官：`{p['generator']['model']}`（生成 T={p['generator']['temperature']}、max_tokens {p['generator']['max_tokens']}；判官 T=0，thinking off，"
            f"双判官独立实例，语义层 `{p['prompt_sha'].get('semantic_version')}`、L2 `{p['prompt_sha'].get('cite_version')}`）",
            f"- 插件臂：`{p['plugin_name']}` v{p['plugin_version']}（{p['plugin']}）｜底子臂：`{base.cfg['plugin_name']}`（闭卷＝无材料）",
            f"- 种子：{p['seeds']}｜k={p['k']}｜材料上限 {p['material_cap']} 字符/题｜harness `{p['harness_git'][:10]}`",
            f"- 录像：插件臂 `{plug.run_id}`，底子臂 `{base.run_id}`（引用格式 ⟦录像:<run>@mm:ss#seq⟧）",
            "- 本单只属考卷 A；**与考卷 B 分开排名，不合并**（方案 v2.2 §3）。", ""]


def arm_table(arms):
    L = ["| 臂 | 种子 | 通过（主口径：均值） | 宽松档（任一判官过） | 严格档（两判官都过） | 规则层直接过 | 结构违规判负 | 交语义层 | 交 L2 | 语义层均分 | 判官批次 |",
         "|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--|"]
    for a in arms:
        for s in a.seeds:
            st = a.summ["per_seed"][str(s)]; r = st.get("routes", {})
            L.append(f"| {a.cfg['plugin_name']} | {s} | {st['pass']} / {st['n']} | {st['pass_lenient']} | {st['pass_strict']} | {r.get('pass_rule', 0)} | "
                     f"{r.get('fail_struct', 0)} | {r.get('sem', 0)} | {r.get('cite', 0)} | {st.get('sem_mean_score')} | "
                     f"{st['judge_status']}（第 {st['judge_attempts']} 批，作废 {st['voided_batches']}） |")
    return L


def gate_rows(arm):
    L = []
    for s, j in arm.judge.items():
        g = j["gate"]
        cite = (f"{round(g['cite_acc_j1']*100)}%/{round(g['cite_acc_j2']*100)}%（锚 {g['cite_n_anchor']}）" if "cite_acc_j1" in g else "本批无 L2 题")
        ia = g.get("sem_items_agree"); ik = g.get("sem_items_kappa")
        L.append(f"| {arm.cfg['plugin_name']} | {s} | {j['attempt']} | {round(g['sem_acc_j1']*100)}% / {round(g['sem_acc_j2']*100)}% | "
                 f"+{round(g['sem_margin_pp_j1'])}pp / +{round(g['sem_margin_pp_j2'])}pp | {round(g['sem_anchor_agree']*100)}% / {g['sem_anchor_kappa']:.2f} | "
                 f"{'—' if ia is None else str(round(ia*100)) + '%'} / {'—' if ik is None else format(ik, '.2f')}（{g['sem_n_items']} 题） | {cite} | "
                 f"{'通过' if g['pass'] else '不通过'} | {arm.c(j.get('gate_ev'))} |")
    return L


def main(a) -> int:
    base, plug = ArmA(a.base), ArmA(a.plug)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    mism = {k: (base.cfg.get(k), plug.cfg.get(k)) for k in COMPARE_KEYS if base.cfg.get(k) != plug.cfg.get(k)}
    title = a.title or f"{plug.cfg['plugin_name']} vs {base.cfg['plugin_name']} · 考卷 A"
    n = plug.cfg["n_cards"]
    judge_valid = all(j["status"] == "valid" for arm in (base, plug) for j in arm.judge.values()) and \
        len(base.judge) == len(base.seeds) and len(plug.judge) == len(plug.seeds)
    install_ok = bool((plug.state.get("install") or {}).get("ok"))
    cov = 1 - plug.summ.get("recall_errors", 0) / n
    res = classify(base.scores(), plug.scores(), install_ok=install_ok, coverage=cov, judge_valid=judge_valid and not mism)
    if mism:
        res.setdefault("reasons", []).append(f"两臂配置不同：{list(mism)}")
    rob = {}
    for key in ("final_lenient", "final_strict"):
        r2 = classify(base.scores(key), plug.scores(key), install_ok=install_ok, coverage=cov, judge_valid=judge_valid and not mism)
        rob[key] = {k: r2.get(k) for k in ("verdict", "label", "items_gain", "ci_items", "per_seed_D")}

    L = header(base, plug, f"能力分单 · {title}")
    L += [f"## 结论：{res['verdict']} {res['label']}", ""]
    if "D" in res:
        lo, hi = res["ci_items"]
        L += [f"- 净提升：**{fmt_items(res['items_gain'])} 题**（主轮 {n} 题，种子均值；95% 配对 bootstrap 区间 {fmt_items(lo)} ～ {fmt_items(hi)} 题）",
              f"- 底子臂（闭卷）通过 {round(res['base_mean'] * n)} 题，插件臂 {round(res['plug_mean'] * n)} 题（满分 {n}，上游终裁 pass/fail）",
              "- 逐种子净提升：" + "，".join(f"s{s} {fmt_items(v * n)} 题" for s, v in res["per_seed_D"].items()),
              f"- 符号检验：插件更好 {res['sign'][0]} 题 / 更差 {res['sign'][1]} 题，双侧 p {'< 0.05' if res['sign'][2] < 0.05 else '≥ 0.05'}",
              "- 稳健性（不改结论）：" + "；".join(f"{'宽松档' if k == 'final_lenient' else '严格档'} {v['verdict']} 净 {fmt_items((v.get('items_gain') or 0))} 题"
                                          for k, v in rob.items()),
              "- 题目独立性提醒（上游 docs/题目独立性_v1.0.md）：92 题≠92 个独立样本，有效样本量按 ≤24 量级理解；本区间按题重抽，偏窄。"]
    if res.get("reasons"):
        L.append("- 判定理由：" + "；".join(res["reasons"]))
    L += ["", f"判定阈值（SPEC §6）：≥{THRESH['min_seeds']} 种子；✅ 需 95% 区间下界 > 0 且各种子同为正且净提升 ≥ {THRESH['min_effect_items']:g} 题；"
          "❌ 对称；其余 😐；安装失败/有效作答不足/判官批次作废未恢复 → 🚧。", "",
          "## 逐臂读数（上游终裁口径：规则层 → L2 依据契合 → 覆盖率判官；双判官覆盖率分取均值 ≥0.7 通过）", ""]
    L += arm_table([base, plug])
    L += ["", "诊断（不进结论）：近似上游《秤》「合并均」＝规则层覆盖率分为先、进语义层的题以双判官均分为准，逐种子："]
    for arm in (base, plug):
        L.append(f"- {arm.cfg['plugin_name']}：" + "，".join(f"s{s} {arm.merged_mean(s)}" for s in arm.seeds))
    L += ["", "## 判官上岗考（每批混入分层锚：语义 8 正 8 负，有 L2 题时另加依据锚 4 正 4 负；锚先自证）", "",
          "| 臂 | 种子 | 尝试 | 语义锚正确率 j1/j2 | 超多数类基线 | 锚同分/κ | 真题同分/κ | 依据锚 j1/j2 | 结果 | 录像 |",
          "|:--|--:|--:|:--|:--|:--|:--|:--|:--|:--|"]
    L += gate_rows(base) + gate_rows(plug)
    L += ["", "达标线：每名判官锚正确率 ≥90% 且超多数类基线 ≥15pp（上游 judge_audit 判据＋本站 90% 下限）；两判官同分 ≥0.8 或 κ ≥0.6（上游「可报值」）；任一不达标整批作废重批。", ""]
    L += ["## 依据轴（答卷引文在声明章内逐字可定位；上游 judge.py axis_evidence，机械面）", "",
          "| 臂 | 引文条数 | 逐字可定位 | 章号错位 | 全库查无（编造） | 至少 1 条有效引文的答卷 |", "|:--|--:|--:|--:|--:|--:|"]
    for arm in (base, plug):
        e = arm.summ["evidence"]; tot = n * len(arm.seeds)
        L.append(f"| {arm.cfg['plugin_name']} | {e['n']} | {e['valid']}（{pct(e['valid'], e['n'])}） | {e['mislocated']} | {e['fabricated']} | {e['answers_with_valid']}/{tot} |")
    L += ["", "## 扣分点：插件臂比底子臂更差的题（三种子合计通过数更少）", ""]
    bs, ps = base.scores(), plug.scores()
    worse = sorted(q for q in ps if q in bs and sum(ps[q].values()) < sum(bs[q].values()))
    for q in worse:
        cs = []
        for s in plug.seeds:
            r, rb = plug.row(s, q), base.row(s, q)
            cs.append(f"s{s} 插件 {r['final']}（{r['path']}）{plug.c(plug.best_ev(r))} vs 底子 {rb['final']} {base.c(base.best_ev(rb))}")
        rc = plug.recall(q)
        L.append(f"- 【扣】{q}：" + "；".join(cs) + f"；材料 {len(rc['material'])} 条 {plug.c(rc['ev'])}")
    if not worse:
        L.append("（无）")
    L += ["", "逐题全部扣分明细（插件臂每个 fail）见 `能力分_扣分明细.md`。"]
    (out / "能力分.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    D = header(base, plug, f"能力分 · 扣分明细 · {title}")
    D += ["每行一个扣分点：插件臂某题某种子终裁 fail。引用该题判词（或作答）录像事件。", ""]
    for s in plug.seeds:
        for r in sorted(plug.judge[s]["items"], key=lambda x: x["qid"]):
            if r["final"] == "pass":
                continue
            extra = ""
            if r.get("sem"):
                extra = f"覆盖率 j1 {r['sem']['s1']}／j2 {r['sem']['s2']}"
            elif r.get("rule"):
                ev = r["rule"].get("evidence") or {}
                extra = f"有效引文 {ev.get('valid')}，错位 {len(ev.get('mislocated') or [])}，查无 {len(ev.get('fabricated') or [])}；诚实轴：{r['rule'].get('honesty')}"
            g = plug.gen(r["qid"], s)
            D.append(f"- 【扣】{r['qid']} s{s} {r['path']}｜{extra} 判词/作答 {plug.c(plug.best_ev(r))} 作答 {plug.c(g['ev'])}")
    (out / "能力分_扣分明细.md").write_text("\n".join(D) + "\n", encoding="utf-8")

    ins, ing = plug.state.get("install") or {}, plug.state.get("ingest") or {}
    U = header(base, plug, f"好不好用单 · {title}")
    U += ["| 项 | 读数 | 录像 |", "|:--|:--|:--|",
          f"| 安装成功 | {'是' if ins.get('ok') else '否'} | {plug.c(ins.get('ev'))} |",
          f"| 安装步数（插件自报，需人工动手的命令数） | {ins.get('steps')} | {plug.c(ins.get('ev'))} |",
          f"| 安装耗时 | {round(ins.get('dur_s') or 0)} 秒 | {plug.c(ins.get('ev'))} |",
          f"| 安装报错 | {len(ins.get('errors') or [])} 条 | {plug.c(ins.get('ev'))} |",
          f"| 写入（ingest）成功 | {'是' if ing.get('ok') else '否'}{'：' + str(ing.get('error')) if ing.get('error') else ''} | {plug.c(ing.get('ev'))} |",
          f"| 检索出错题数 | {plug.summ.get('recall_errors')} / {n} | — |",
          f"| 返回条目因 source 不可回源被剔除 | {plug.summ.get('dropped_unparseable')} 条 | — |",
          "| 文档可读性 | 人工评定栏（按 SPEC §5.2 清单逐项打勾，附录像/文档链接） | — |", ""]
    for e in ins.get("errors") or []:
        U.append(f"- 【扣】安装报错：{str(e)[:200]} {plug.c(ins.get('ev'))}")
    (out / "好不好用.md").write_text("\n".join(U) + "\n", encoding="utf-8")

    tb, tp = base.token_split(), plug.token_split()
    un = plug.state.get("uninstall") or {}
    lat = plug.state.get("recall_latency_s") or []
    C = header(base, plug, f"成本与安全单 · {title}")
    C += ["## 成本（token 硬数据，来自录像 llm.response.usage）", "", "| 臂 | 角色 | 调用 | prompt tok | completion tok | 网关计费 USD |", "|:--|:--|--:|--:|--:|--:|"]
    for arm, t in ((base, tb), (plug, tp)):
        for role, v in sorted(t.items()):
            C.append(f"| {arm.cfg['plugin_name']} | {role} | {v['calls']} | {v['prompt']} | {v['completion']} | {v['cost_usd']:.4f} |")
    gp = tp.get("generator", {}).get("prompt", 0) - tb.get("generator", {}).get("prompt", 0)
    C += ["", f"- 插件带来的生成器上下文增量：{gp:+d} prompt tokens（全种子合计）；平均材料 {plug.summ.get('material_chars_mean')} 字符/题",
          f"- 写入耗时：{round(ing.get('dur_s') or 0, 1)} 秒 / {ing.get('turns')} 段 {plug.c(ing.get('ev'))}",
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

    recs = {base.run_id: base.rec, plug.run_id: plug.rec}
    val = {}
    for f in ("能力分.md", "能力分_扣分明细.md", "好不好用.md", "成本与安全.md"):
        v = validate_report((out / f).read_text(encoding="utf-8"), recs)
        val[f] = {k: v[k] for k in ("total", "ok", "pass")} | {"problems": v["problems"][:20]}
    # 本站加严：被引事件的 seq 在录像内必须唯一（2026-10-10 并发事故后加；重复 seq 区间的事件不得被引用）
    import collections, re as _re
    from .recorder import CITE_RE, load_events
    dup = {rid: {s for s, c in collections.Counter(e["seq"] for e in load_events(p)).items() if c > 1} for rid, p in recs.items()}
    for f in val:
        txt = (out / f).read_text(encoding="utf-8")
        bad = [m.group(0) for m in CITE_RE.finditer(txt) if int(m.group("seq")) in dup.get(m.group("run"), set())]
        val[f]["cites_to_duplicate_seq"] = len(bad)
        if bad:
            val[f]["pass"] = False; val[f]["problems"] = (val[f]["problems"] + [("dup-seq", b) for b in bad[:10]])[:20]
    allpass = all(v["pass"] for v in val.values())
    (out / "录像引用校验.json").write_text(json.dumps({"all_pass": allpass, "files": val}, ensure_ascii=False, indent=1), encoding="utf-8")
    res_j = {k: v for k, v in res.items() if k != "thresholds"}
    (out / "结论.json").write_text(json.dumps({"exam": plug.cfg["exam"], "classify": res_j, "robustness": rob, "config_mismatch": mism,
                                             "citation_check_all_pass": allpass, "gradable": plug.cfg.get("gradable")},
                                            ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"exam": "A", "verdict": res["verdict"], "label": res["label"], "items_gain": res.get("items_gain"),
                      "ci_items": res.get("ci_items"), "citations_all_pass": allpass,
                      "deductions": {f: v["total"] for f, v in val.items()}}, ensure_ascii=False, default=str))
    return 0 if allpass else 1
