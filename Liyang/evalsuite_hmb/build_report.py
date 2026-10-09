# -*- coding: utf-8 -*-
"""汇总 r1（零 LLM 检索轨）+ r2（生成轨）→ REPORT_HMB.md；含与作者公布读数对照、ng 失分点清单。

  python build_report.py
读：out/hmb_r1.json、out/hmb_r2.json、out/_work/r1_detail.json、out/_work/judge_main_final.json、out/_e2e/e2e_final.json
"""
import json
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hmb_lib as H  # noqa: E402

ARMS = H.arms()
R1A_ALL = ["base", "integrated", "ng", "ng_1a2bc2b", "ng_head", "bm25"]
LABEL = {"ng": "ng@d523cfd", "ng_1a2bc2b": "ng@1a2bc2b", "ng_head": f"ng@{H.NGHEAD_REV}(HEAD)"}
ED = os.path.join(H.OUT, "_e2e")


def f(v, pct=False):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.1%}" if pct else (f"{v:.4f}" if abs(v) < 10 else f"{v:.1f}")
    return str(v)


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join([":--"] + ["--:"] * (len(head) - 1)) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main():
    r1 = H.load(os.path.join(H.OUT, "hmb_r1.json"), {})
    r2 = H.load(os.path.join(H.OUT, "hmb_r2.json"), {})
    det = H.load(os.path.join(H.WORK, "r1_detail.json"), {})
    jm = H.load(os.path.join(H.WORK, "judge_main_final.json"), {})
    e2 = H.load(os.path.join(ED, "e2e_final.json"), {})
    cards = H.load_cards()
    L = []
    A = L.append
    m2 = r2.get("meta", {})
    res1 = r1.get("results", {})
    R1A = [a for a in R1A_ALL if a in res1]
    A("# HMB（hive-memory-bench）测评报告：base / integrated / ng / BM25 / 闭卷" + (" ＋ ng_head" if "ng_head" in ARMS else "") + "\n")
    A("快照：base=upstream@2bb8291，integrated=integrated@667e84a，ng=rewrite/ng@d523cfd"
      + (f"，ng_head=rewrite/ng@{H.NGHEAD_REV}（r2 完成时 ng 的 HEAD，lingshu_ng 最后一次改动；含 77c1c27 退役不交付/矛盾对侧随交付"
         + ("、19551ef 召回第二阶段 idf 重排" if H.NGHEAD_REV != "1a2bc2b" else "") + "）" if "ng_head" in R1A or "ng_head" in ARMS else "")
      + ("；检索轨另列中间快照 ng@1a2bc2b（77c1c27 后、19551ef 前）" if "ng_1a2bc2b" in R1A else "")
      + "；HMB 仓库 commit "
      f"{(r1.get('meta') or {}).get('hmb_commit', '?')}（只读）。检索 k=10，小说 178 块（~400 字、不跨章）、e2e 1,611 块。\n")
    A("## 0. 口径与如实声明\n")
    A(f"- **生成器**：`{m2.get('generator', 'cline-pass/deepseek-v4.1-flash')}`（ClinePass 包月套餐）。"
      "**r2 早期已落盘的部分答卷来自按量计费的 `deepseek/deepseek-v4.1-flash`——同一模型、同一提示词与参数，"
      "按用户指示沿用（缓存/答卷文件不重跑）**；具体是哪些见 §0.1。")
    A("- **判官**：两个判官均为 `cline-pass/deepseek-v4.1-flash`，作为**两个独立实例**运行：J1 temperature 0 / seed 11，"
      "J2 temperature 0.6 / seed 29，thinking 关；各自独立打乱题序，真实答卷（五臂）与锚混在一起盲判，请求不含臂名或期望标签。"
      "**同模型双实例判官，独立性弱于异模型**——两判官一致率偏高的部分可能来自同源偏差，不能当作异模型间的互证。")
    A("- 按用户指示弃用 `deepseek-v4-pro`：检查费用日志与判官目录，此前**没有任何 pro 判决落盘**（无需作废的结果）；本报告全部判决均来自 flash。")
    A("- 判分链：作者 `score_sut.py` 规则层 → `semantic.py` 语义层（覆盖率判官）+ L2 依据契合判官 → `judge_audit.py check` 硬闸（锚自证 ≥ +15pp，"
      "一致率 同分 ≥0.8 或 kappa ≥0.6 ⇒ 可报值；≥0.5 ⇒ 只报序；否则不可测）。**未过闸的读数不报值。**")
    A("- 干预轮 92 题：作者答案键未公开（cards/ 无 intervention 子结构）⇒ 只报机械依据轴（引文逐字率、cid 正确率），不报通过率。")
    A("- 费用：包月套餐无按 token 上限；网关仍回传按量折算的名义费用 "
      f"${m2.get('cost_usd_total', '?')}（含早期按量批），仅供参考。")
    A("- 已知与作者口径的差异：①统一切块（作者各家原生切块不同）；②矛盾对/地基句用公开 cards 机械构造的**代理清单**（作者 9 对未公开）；"
      "③e2e 判官提示词按作者公开判据自写；④单次采样，未做多次重复。\n")
    # 0.1 legacy answers
    leg = r2.get("legacy_answers") or {}
    if leg:
        A("### 0.1 来自按量 `deepseek/deepseek-v4.1-flash` 的沿用答卷\n")
        A(table(["轨/臂", "沿用份数"], [[k, v] for k, v in sorted(leg.items())]) + "\n")

    # ---------------- r1
    A("## 1. 检索轨 r1（零 LLM，机械读数）\n")
    keys = [("cid_recall", "必需章 cid 召回"), ("cid_full_rate", "必需章全召回率"), ("quote_recall", "证据句逐字召回"),
            ("point_keyword_cov", "采分点关键词覆盖"), ("must_exclude_mix", "须排除句混入（越低越好）"),
            ("frag_verbatim_strict", "片段逐字可回源"), ("tri.L2", "L2 逐字保地基（代理）"), ("tri.L2p", "L2p 关键词覆盖（代理）"),
            ("pairs_all.both_n8", "矛盾对两侧同进（72 对，代理）"), ("pairs_hard9.both_n8", "难 9 对两侧同进（代理）"),
            ("store_verbatim_strict", "存储面逐字"), ("write_sec_novel", "小说建库秒"), ("query_ms_median_novel", "小说检索中位 ms"),
            ("e2e.human_4gram_cov", "e2e 下文 4-gram 覆盖"), ("e2e.human_strict12_rate", "e2e 下文 12 字逐字命中率"),
            ("e2e.material_chars_mean", "e2e 材料均字数"), ("write_sec_e2e", "e2e 建库秒"), ("query_ms_median_e2e", "e2e 检索中位 ms"),
            ("retire.leak_prod_path", "退役泄漏（生产路径 recall，越低越好）"),
            ("retire.leak_base_path", "退役泄漏（基类路径 search_content）")]
    A(table(["指标"] + [LABEL.get(a, a) for a in R1A], [[n] + [f(res1.get(a, {}).get(k)) for a in R1A] for k, n in keys]) + "\n")
    ref1 = r1.get("reference", {})
    A("**与作者公布读数对照（r1）**\n")
    rows = []
    for k, v in ref1.items():
        rows.append([k, "；".join(f"{a}={b}" for a, b in v.items())])
    A(table(["指标", "参照"], rows) + "\n")

    # ---------------- r2 main
    A("## 2. 生成轨 r2 · 主轮 92 题（同一生成器，唯一变量＝材料）\n")
    au = (r2.get("audit") or {}).get("main") or {}
    rec = au.get("record") or {}
    mode = rec.get("report_mode") or "?"
    A(f"**判官硬闸（judge_audit，48 机械锚）**：结论 `{mode}`。")
    if au.get("stdout"):
        A("```\n" + au["stdout"].strip()[-1500:] + "\n```")
    ra = au.get("real_agreement") or {}
    if ra:
        A(f"真实答卷上两实例逐题 pass/非 pass 一致：n={ra.get('n')}，同分 {f(ra.get('identical'), True)}，kappa {f(ra.get('kappa'))}。\n")
    res2 = r2.get("results", {})
    ok_val = mode in ("可报值", "report-value", "value")
    rows = []
    for a in ARMS:
        m = res2.get(a, {})
        rl = m.get("main.rule_layer") or {}
        rows.append([LABEL.get(a, a), f"{rl.get('pass', 0)}/{rl.get('review', 0)}/{rl.get('fail', 0)}",
                     m.get("main.pass_J1", "—"), m.get("main.pass_J2", "—"), m.get("main.pass_both", "—"),
                     m.get("main.pass_either", "—"), f(m.get("main.merged_mean_J1")), f(m.get("main.merged_mean_J2")),
                     f(m.get("main.merged_mean")), f(m.get("main.evidence.verbatim_rate"), True),
                     f(m.get("main.evidence.cid_correct_rate"), True), m.get("main.evidence.parse_err", "—")])
    A(("" if ok_val else f"> ⚠ 硬闸结论为 `{mode}`：下表通过数**不作为数值读数**，仅供排序/诊断。\n\n") +
      table(["臂", "规则层 pass/review/fail", "pass@J1", "pass@J2", "两判官皆过", "任一判官过", "合并均@J1", "合并均@J2", "合并均", "引文逐字率", "引文 cid 正确率", "解析失败"], rows) + "\n")
    A("> 合并均＝作者《秤》口径（docs/秤_对照测_v1.0.md:55）：规则层先决、语义层终裁（review/fail 面取覆盖率判官 score）后的覆盖率均分，92 题平均。\n")
    A("**干预轮 92 题（只报机械依据轴）**\n")
    A(table(["臂", "引文数", "逐字率", "cid 正确率", "unknown 置信", "解析失败"],
            [[LABEL.get(a, a), res2.get(a, {}).get("interv.evidence.quotes", "—"), f(res2.get(a, {}).get("interv.evidence.verbatim_rate"), True),
              f(res2.get(a, {}).get("interv.evidence.cid_correct_rate"), True), res2.get(a, {}).get("interv.evidence.unknown_conf", "—"),
              res2.get(a, {}).get("interv.evidence.parse_err", "—")] for a in ARMS]) + "\n")

    # ---------------- e2e
    A("## 3. 端到端轨 e2e · C 型续接预测 89 卡全量\n")
    ae = (r2.get("audit") or {}).get("e2e") or {}
    rec2 = ae.get("record") or {}
    mode2 = rec2.get("report_mode") or "?"
    A(f"**判官硬闸（judge_audit，48 锚：24 正/12 跨卡负/12 无关负）**：结论 `{mode2}`。")
    if ae.get("stdout"):
        A("```\n" + ae["stdout"].strip()[-1500:] + "\n```")
    ra2 = ae.get("real_agreement") or {}
    if ra2:
        A(f"真实答卷三档一致：n={ra2.get('n')}，同分 {f(ra2.get('identical'), True)}，kappa {f(ra2.get('kappa'))}。\n")
    ok2 = mode2 in ("可报值", "report-value", "value")
    rows = []
    for a in ARMS:
        m = res2.get(a, {})
        rows.append([LABEL.get(a, a), f(m.get("e2e.J1.weighted")), f(m.get("e2e.J2.weighted")), f(m.get("e2e.lenient.weighted")),
                     f(m.get("e2e.strict.weighted")), m.get("e2e.lenient.spm", "—"), f(m.get("e2e.basis_verbatim_rate"), True),
                     m.get("e2e.cards_with_basis", "—"), f(m.get("e2e.material_chars_mean"))])
    A(("" if ok2 else f"> ⚠ 硬闸结论为 `{mode2}`：下表仅供排序/诊断。\n\n") +
      table(["臂", "加权@J1", "加权@J2", "加权·宽（取高档）", "加权·严（取低档）", "宽 s/p/m", "依据逐字率", "有依据卡", "材料均字"], rows) + "\n")
    A(f"**31 卡子集（作者口径：file ∈ 确认协议内容.md / 用户与AI交换称呼.md，n={e2.get('sub31_n', 31)}）**\n")
    A(table(["臂", "加权@J1", "加权·宽", "加权·严", "宽 s/p/m", "依据逐字率", "依据条数", "有依据卡"],
            [[LABEL.get(a, a), f(res2.get(a, {}).get("e2e.J1_31.weighted")), f(res2.get(a, {}).get("e2e.lenient31.weighted")),
              f(res2.get(a, {}).get("e2e.strict31.weighted")), res2.get(a, {}).get("e2e.lenient31.spm", "—"),
              f(res2.get(a, {}).get("e2e31.basis_verbatim_rate"), True), res2.get(a, {}).get("e2e31.basis_n", "—"),
              res2.get(a, {}).get("e2e31.cards_with_basis", "—")] for a in ARMS]) + "\n")

    # ---------------- 对照
    A("## 4. 与作者公布读数对照\n")
    ref = r2.get("reference") or {}
    rows = [[k, "；".join(f"{a}={b}" for a, b in v.items())] for k, v in ref.items()]
    A(table(["项", "作者读数（出处）"], rows) + "\n")
    lines = []
    bm = res2.get("bm25", {})
    if bm:
        lines.append(f"- 主轮：作者「DeepSeek V4.1 Flash 整本入提示」43/92；本测同一生成器在 k=10 片段下："
                     + "，".join(f"{a} {res2.get(a, {}).get('main.pass_J1', '—')}/{res2.get(a, {}).get('main.pass_J2', '—')}（J1/J2）" for a in ARMS)
                     + "。材料口径不同（整本 vs 片段），只作量级参照。")
        lines.append(f"- e2e 89 卡（作者：BM25 0.2022 / OV 0.1348 / 灵枢 0.1067 / 闭卷 0.1011）；本测宽口径加权："
                     + "，".join(f"{a} {f(res2.get(a, {}).get('e2e.lenient.weighted'))}" for a in ARMS)
                     + "；31 卡子集（作者：BM25 0.1935 / OV 0.1452 / Hindsight 0.1452 / 灵枢 0.1290 / 闭卷 0.1129）本测："
                     + "，".join(f"{a} {f(res2.get(a, {}).get('e2e.lenient31.weighted'))}" for a in ARMS)
                     + "。作者为同一判官两轮重放、本测为同模型两实例，判官不同，**不可逐值互比**，只看排序是否复现。")
        lines.append("- 依据轴：作者 BM25 100% / 灵枢 v0.7.1 86.0%（主轮引文）；本测主轮引文逐字率："
                     + "，".join(f"{a} {f(res2.get(a, {}).get('main.evidence.verbatim_rate'), True)}" for a in ARMS) + "。")
        lines.append("- 合并均：作者《秤》168 题（不同题集，量级参照）灵枢 0.669 / BM25 0.595 / 闭卷 0.213；本测主轮 92 题："
                     + "，".join(f"{a} {f(res2.get(a, {}).get('main.merged_mean'))}" for a in ARMS) + "。")
        lines.append("- 干预轮：作者答案键不公开，作者只公布整本入提示的模型读数（DeepSeek V4.1 Flash 47/92、参考实现 55/92，"
                     "results/成绩总表.md §1.1），无记忆系统读数；本测只报依据轴。")
    A("\n".join(lines) + "\n")

    # ---------------- ng@d523cfd vs ng@HEAD
    if "ng_head" in res1 or "ng_head" in res2:
        A("## 4.1 ng@d523cfd 与 ng@HEAD 并列\n")
        keys2 = [("r1", k, n) for k, n in keys] + [
            ("r2", "main.pass_J1", "主轮 pass@J1"), ("r2", "main.pass_J2", "主轮 pass@J2"), ("r2", "main.pass_both", "主轮两判官皆过"),
            ("r2", "main.merged_mean", "主轮合并均"), ("r2", "main.evidence.verbatim_rate", "主轮引文逐字率"),
            ("r2", "interv.evidence.verbatim_rate", "干预轮引文逐字率"), ("r2", "e2e.lenient.weighted", "e2e 89 卡加权·宽"),
            ("r2", "e2e.strict.weighted", "e2e 89 卡加权·严"), ("r2", "e2e.lenient31.weighted", "e2e 31 卡加权·宽"),
            ("r2", "e2e.basis_verbatim_rate", "e2e 依据逐字率")]
        rows = []
        for src, k, n in keys2:
            d = res1 if src == "r1" else res2
            a, b = d.get("ng", {}).get(k), d.get("ng_head", {}).get(k)
            rows.append([n, f(a, "rate" in k and src == "r2"), f(b, "rate" in k and src == "r2"), f(d.get("bm25", {}).get(k), "rate" in k and src == "r2")])
        A(table(["指标", "ng@d523cfd", LABEL["ng_head"], "BM25（参照）"], rows) + "\n")
        sm = H.load(os.path.join(H.OUT, "ng_1a2bc2b_summary.json"))
        if sm:
            A(f"> 中间快照 ng@1a2bc2b（r2 期间的 HEAD，留存件 out/ng_1a2bc2b_summary.json）：主轮 pass J1/J2 = {sm['main']['J1'].get('pass')}/{sm['main']['J2'].get('pass')}，"
              f"合并均 {sm['main']['merged_mean']}，e2e 89 卡加权·宽 {sm['e2e']['lenient']['weighted']}、·严 {sm['e2e']['strict']['weighted']}，31 卡·宽 {sm['e2e']['lenient31']['weighted']}；"
              "检索轨见 §1 的 ng@1a2bc2b 列（与 d523cfd 仅退役泄漏不同）。\n")

    # ---------------- ng 失分点
    A("## 5. ng 的失分点（机械清单）\n")
    pts = []
    for NG in [x for x in ("ng", "ng_head") if x in res1 or x in res2]:
        pts.append(f"\n### {LABEL.get(NG, NG)}\n")
        pts.extend(ng_points(NG, res1, res2, det, jm, cards))
    A("\n".join(pts) if pts else "（数据未齐，暂无）")
    fx = os.path.join(H.HERE, "REPORT_HMB_ng_fixes.md")
    if os.path.exists(fx):
        A("\n" + open(fx, encoding="utf-8").read())
    A("\n## 7. 产物\n")
    A("- `out/hmb_r1.json`（检索轨）、`out/hmb_r2.json`（生成轨）、`out/_work/judge_main_final.json`、`out/_e2e/e2e_final.json`、"
      "`out/_work/audit_main_rec.json`、`out/_e2e/audit_e2e_rec.json`（judge_audit 记录）。")
    open(os.path.join(H.HERE, "REPORT_HMB.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L)[:3000])


def ng_points(NG, res1, res2, det, jm, cards):
    pts = []
    bm = res2.get("bm25", {})
    n1, b1 = res1.get(NG, {}), res1.get("bm25", {})
    for k, nm, lower_better in [("cid_recall", "必需章 cid 召回", False), ("quote_recall", "证据句逐字召回", False),
                                ("point_keyword_cov", "采分点关键词覆盖", False), ("pairs_all.both_n8", "矛盾对两侧同进", False),
                                ("pairs_hard9.b_side_n8", "难 9 对另一侧召回", False), ("tri.L2p", "L2p 关键词覆盖", False)]:
        if n1.get(k) is not None and b1.get(k) is not None and n1[k] < b1[k]:
            pts.append(f"- **r1 · {nm}**：{NG} {f(n1[k])} < 朴素 BM25 {f(b1[k])}（同块同查询）。")
    if n1.get("retire.leak_prod_path") and n1["retire.leak_prod_path"] != "0/6":
        pts.append(f"- **r1 · 退役泄漏**：{NG} 生产路径 {n1['retire.leak_prod_path']}（作者修复后 MdCGOS 0/6）——"
                   "降级 archived 后检索仍返回旧值，与 base/integrated 同病，未兑现退役语义。")
    elif n1.get("retire.leak_prod_path") == "0/6":
        pts.append(f"- r1 · 退役泄漏：{NG} 生产路径 0/6（已兑现，与作者 9d26266d 修复后口径一致）；基类路径 store.search_content "
                   f"{n1.get('retire.leak_base_path')}（与作者「基类路径为修复自列边界、同口径 6/6 持平」同形，docs/秤_对照测_v1.0.md:141-143）。")
    dn, db = det.get(NG, {}), det.get("bm25", {})
    worse = sorted([q for q in dn if q in db and dn[q]["cid"] < db[q]["cid"]], key=lambda q: dn[q]["cid"] - db[q]["cid"])
    if worse:
        pts.append(f"- r1 逐题：{NG} 必需章召回低于 BM25 的题 {len(worse)} 道（最差 10：" +
                   "、".join(f"{q}({dn[q]['cid']:.2f}<{db[q]['cid']:.2f})" for q in worse[:10]) + "）。")
    # r2 main
    boards = jm.get("boards") or {}

    def verd(a, j):
        return {r["qid"]: r["verdict"] for r in ((boards.get(a) or {}).get(j) or {}).get("detail", [])}
    ngJ = {j: verd(NG, j) for j in ("J1", "J2")}
    if ngJ["J1"]:
        lost = []
        for q in sorted(ngJ["J1"]):
            ng_pass = ngJ["J1"].get(q) == "pass" and ngJ["J2"].get(q) == "pass"
            others = [a for a in ("bm25", "integrated", "closed") if verd(a, "J1").get(q) == "pass" and verd(a, "J2").get(q) == "pass"]
            if not ng_pass and others:
                lost.append((q, others))
        cat = Counter((cards.get(q) or {}).get("category") or (cards.get(q) or {}).get("qtype") or "?" for q, _ in lost)
        pts.append(f"- **r2 主轮**：{NG} 未被两判官同时判过、而 BM25/integrated/闭卷至少一家两判官皆过的题 {len(lost)} 道"
                   f"（按类：{dict(cat)}）：" + "、".join(f"{q}[{'/'.join(o)}]" for q, o in lost[:30]) + "。")
        clo = [q for q, o in lost if "closed" in o]
        if clo:
            pts.append(f"  - 其中闭卷（无材料）能过而 {NG} 过不了的 {len(clo)} 道：{'、'.join(clo[:20])}——材料把生成器带偏（作者结论一的同型现象）。")
    nm2 = res2.get(NG, {})
    if nm2.get("main.evidence.verbatim_rate") is not None and bm.get("main.evidence.verbatim_rate") is not None:
        if nm2["main.evidence.verbatim_rate"] < bm["main.evidence.verbatim_rate"]:
            pts.append(f"- **r2 依据轴**：{NG} 主轮引文逐字率 {f(nm2['main.evidence.verbatim_rate'], True)} < BM25 "
                       f"{f(bm['main.evidence.verbatim_rate'], True)}。")
    # e2e
    V = defaultdict(dict)
    jd = os.path.join(ED, "judge")
    if os.path.isdir(jd):
        for fn in os.listdir(jd):
            j, rest = fn[:-5].split("__", 1)
            V[j][rest] = H.load(os.path.join(jd, fn))["verdict"]
        order = {"strict": 2, "paraphrase": 1, "miss": 0, "parse_err": 0}

        def lv(a, c):
            v1, v2 = V["J1"].get(f"{a}__{c}"), V["J2"].get(f"{a}__{c}")
            return None if v1 is None or v2 is None else max(order[v1], order[v2])
        cids = sorted({k.split("__")[1] for k in V["J1"] if k.startswith(NG + "__")})
        lostc = [(c, [a for a in ("bm25", "integrated", "closed") if (lv(a, c) or 0) > (lv(NG, c) or 0)]) for c in cids]
        lostc = [(c, o) for c, o in lostc if o]
        if lostc:
            pts.append(f"- **e2e**：{NG} 宽口径档位低于 BM25/integrated/闭卷任一家的卡 {len(lostc)} 张：" +
                       "、".join(f"{c}[{'/'.join(o)}]" for c, o in lostc[:30]) + "。")
    ne = res2.get(NG, {})
    if ne.get("e2e.lenient.weighted") is not None and bm.get("e2e.lenient.weighted") is not None and \
            ne["e2e.lenient.weighted"] < bm["e2e.lenient.weighted"]:
        pts.append(f"- e2e 总分：{NG} {f(ne['e2e.lenient.weighted'])} < BM25 {f(bm['e2e.lenient.weighted'])}（宽口径）。")
    return pts

if __name__ == "__main__":
    main()
