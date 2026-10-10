# -*- coding: utf-8 -*-
"""validation-report.md 生成器（验证计划 v0 §8：通过/失败/阻塞，未运行不算通过）。

  python plugins/dsh-auto-memory/report.py --vdir validation/dam-20261010T1045 [--incomplete] [--judge-v2 PATH.json]

输入：preregistration.json、raw/_status.json、baseline-report.json（analyze.py）、evidence-manifest.json（evidence.py）、
case-results.jsonl（cases.py）、各 P 运行 state/cards/*.json（插件行为描述统计）。成本口径 harness/cost_v3.py。
本脚本只汇总，不重判、不改 verdict_v3 输出。
"""
from __future__ import annotations
import argparse, glob, json, re, statistics, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from harness import cost_v3 as C  # noqa: E402


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def now():
    return time.strftime("%Y-%m-%d %H:%M CST", time.gmtime(time.time() + 8 * 3600))


def inject_stats(rdir: Path) -> dict | None:
    cards = [p for p in sorted((rdir / "state/cards").glob("C-*.json")) if "manifest" not in p.name] if (rdir / "state/cards").exists() else []
    if not cards:
        return None
    vis = tot = anyvis = lines = trunc = 0
    sb, nm, own_written = [], [], []
    for p in cards:
        c = rj(p)
        sec = c.get("section") or ""
        sb.append(c.get("section_bytes") or 0)
        nm.append(len([m for m in (c.get("manifest") or []) if not m["path"].endswith("MEMORY.md")]))
        trunc += "index truncated" in sec
        lines += len(re.findall(r"^- \[", sec, re.M))
        names = []
        t = c["calls"][0]["text"] if c.get("calls") else ""
        m = re.search(r"\[.*\]", t, re.S)
        try:
            names = [x["name"] for x in json.loads(m.group(0))] if m else []
        except Exception:
            names = []
        v = [n for n in names if f"({n}.md)" in sec]
        vis += len(v); tot += len(names); anyvis += bool(v); own_written.append(len(names))
    n = len(cards)
    return {"n_cards": n, "section_bytes": [min(sb), statistics.median(sb), max(sb)], "memories": [min(nm), statistics.median(nm), max(nm)],
            "index_truncated_cards": trunc, "index_lines_shown_mean": round(lines / n, 1),
            "own_session_written": tot, "own_session_visible": vis, "cards_with_own_visible": anyvis}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vdir", required=True); ap.add_argument("--incomplete", action="store_true")
    ap.add_argument("--judge-v2", default=None)
    a = ap.parse_args()
    vd = Path(a.vdir).resolve()
    pr = rj(vd / "preregistration.json")
    st = rj(vd / "raw/_status.json")
    br = rj(vd / "baseline-report.json")
    em = rj(vd / "evidence-manifest.json") if (vd / "evidence-manifest.json").exists() else {}
    cases = [json.loads(l) for l in (vd / "case-results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    vv = br.get("verdict_v3") or {}
    order = pr["execution_order"] + st.get("appended_reruns", [])
    inval = {x["pair_id"] for x in st.get("invalidated_pairs", [])}
    L = []
    w = L.append
    title_state = "未完成（中间验证报告）" if a.incomplete else "完成（方法试验）"
    w(f"# dsh-auto-memory 0.7.0 · 端到端验证报告（真实链路）· {title_state}\n")
    w(f"- 验证编号：`{pr['validation_id']}`；分析编号：`{pr['analysis_id']}`；执行：pes-e2e-dam（11:50 起由接手代理续跑）；生成：{now()}")
    w(f"- 依据：docs/v3/端到端验证计划-v0.md §3（完整链路）、§8（验证输出）；预注册 `preregistration.json`（git a73ecf3，sha256 `{br.get('preregistration_sha256','')[:16]}…`）")
    w(f"- **发布层状态：{vv.get('release_state') or '未产出（预注册样本未完成）'}**（运行层：{vv.get('run_state')}）。独立场景 = 1 < 8、记忆域判定规范未冻结、独立复核未完成 → 按计划 §1 只出方法试验报告，**不产生正式五状态结论**；下文的“观察到的方向”不是能力结论。\n")

    # ---- 1 读数 ----
    w("## 1 各对读数（0–100，题目等权；strict=1、paraphrase=0.5、miss/parse_err=0）\n")
    w("| 配对 | 重跑号 | B0 | P | Δ = P − B0 | 状态 |\n|:--|--:|--:|--:|--:|:--|")
    for r in br["pairs"]:
        stt = "作废留痕（不计入）" if r["invalid"] else ("有效" if r["complete"] else "未完成/未运行")
        f = lambda x: "—" if x is None else f"{x:.2f}"
        w(f"| {r['pair_id']} | {r['rerun']} | {f(r['B0'])} | {f(r['P'])} | {f(r.get('delta'))} | {stt} |")
    w("\n逐次运行：\n")
    w("| 运行 | 臂 | seed | 开始 | 分数 | strict/para/miss | parse_err | 判官过闸（第几批 · 锚准确率 v1/v2 · κ） | 有效性 |\n|:--|:--|--:|:--|--:|:--|--:|:--|:--|")
    for e in order:
        rid = e["run_id"]; r = br["runs"].get(rid, {})
        sc = r.get("score"); cnt = r.get("counts") or {}
        g = r.get("judge_gate") or {}
        val = (r.get("validity") or {})
        vs = "未运行" if not (vd / "raw" / rid).exists() else ("有效" if val.get("valid") else ("无效：" + "；".join(val.get("reasons", []))[:90] if val.get("valid") is False else "进行中/未完成"))
        if e["pair_id"] in inval and val.get("valid"):
            vs = "有效，但所属配对整对作废"
        gate = f"第{r.get('judge_attempt')}批 · {g.get('anchor_acc_v1', 0):.3f}/{g.get('anchor_acc_v2', 0):.3f} · κ{g.get('anchor_kappa', 0):.2f}" if g else "—"
        w(f"| {rid} | {e['condition']} | {e['gen_seed']} | {(r.get('started') or '—')[11:16]} | {'—' if sc is None else f'{sc:.2f}'} | "
          f"{'/'.join(str(cnt.get(k, '—')) for k in ('strict', 'paraphrase', 'miss')) if cnt else '—'} | {r.get('parse_err', '—') if r.get('parse_err') is not None else '—'} | {gate} | {vs} |")
    d = br.get("card_level_descriptive")
    if d:
        w(f"\n卡级描述（卡不是独立单位，仅描述、不进判定）：{d['n_pairs']} 个有效配对上逐卡平均 Δ = {d['mean_delta']}，卡 bootstrap 95% [{d['ci95_card_bootstrap'][0]}, {d['ci95_card_bootstrap'][1]}]；P 更好 {d['cards_P_better']} 卡、B0 更好 {d['cards_B0_better']} 卡、持平 {d['cards_tied']} 卡。")

    # ---- 2 判定 ----
    w("\n## 2 v3 判定（harness/verdict_v3.py，方法试验）\n")
    w(f"- 实现 sha256 `{br.get('verdict_v3_impl_sha256','')[:16]}…`；冻结规格 SplitMix64 / type-7 / B=10000 / 95% / a=b=5 / 半宽≤5 / 场景≥8 / 重跑≥3。")
    for k in ("run_state", "release_state", "capability", "capability_observed", "install_stage", "estimate", "interval", "half_width", "base_abs", "plug_abs", "n_scenarios", "reruns_per_scenario", "excluded_pairs", "rankable"):
        if k in vv:
            w(f"- `{k}`：{json.dumps(vv.get(k), ensure_ascii=False)}")
    if vv.get("reasons"):
        w("- 理由：" + "；".join(map(str, vv["reasons"])))
    if vv.get("errors"):
        w("- errors：" + "；".join(f"{x.get('code')}（{x.get('detail')}）" for x in vv["errors"]))
    w("- 读法：场景只有 1 个，场景层 bootstrap 区间退化（同一场景反复抽样），区间宽度不反映跨场景不确定性；`capability_observed` 只是该单一场景上观察到的方向，不得当作能力结论或排名。")

    # ---- 3 成本 ----
    w("\n## 3 成本（harness/cost_v3.py 口径）\n")
    roles_cost = {}
    for rid, r in br["runs"].items():
        s = r.get("stats") or {}
        roles_cost[rid] = {"cost": s.get("cost_usd", {}), "calls": s.get("llm_calls", {}), "truncated": s.get("recording_truncated_by_eio")}
    valid_pairs = [p for p in br["pairs"] if p["complete"] and not p["invalid"]]
    by_pair = {e["pair_id"]: {} for e in order}
    for e in order:
        by_pair[e["pair_id"]][e["condition"]] = e["run_id"]

    def arm(cond):
        comp = {}
        succ = 0
        for p in valid_pairs:
            rid = by_pair[p["pair_id"]][cond]
            for role, v in roles_cost[rid]["cost"].items():
                comp[role] = comp.get(role, 0) + v
            succ += (br["runs"][rid].get("counts") or {}).get("strict", 0)
        items = [C.CostItem(name=f"{k}（{len(valid_pairs)} 次运行合计）", value=round(v, 6)) for k, v in sorted(comp.items())]
        items.append(C.CostItem(name="真实宿主安装（npm/pnpm，无 LLM）", value=None, status="unmeasured", included=False, note="一次性，未计费"))
        return {"items": items, "successes": succ, "failed_cost_included": True, "cache": "冷（每卡独立空记忆根）" if cond == "P" else "不适用",
                "machine_wait_s": None, "human_ops_s": None}
    if valid_pairs:
        try:
            sheet = C.cost_sheet(arm("P"), arm("B0"))
            w(f"成功 = 判 strict 的题（判 paraphrase 不算“干成”；这是本报告对 cost_v3“成功任务数”的取法，已登记）。有效配对 {len(valid_pairs)} 对。\n")
            w("| 项 | P（插件） | B0（基线） |\n|:--|:--|:--|")
            w(f"| 总成本 | {sheet['plug']['total']['display']} | {sheet['base']['total']['display']} |")
            w(f"| 成功数（strict 合计） | {sheet['plug']['unit']['successes']} | {sheet['base']['unit']['successes']} |")
            w(f"| 每干成一件花多少 | {sheet['plug']['unit']['display']} | {sheet['base']['unit']['display']} |")
            w(f"| 多干成一件多花多少 | {sheet['incremental']['display'] if 'incremental' in sheet else '—'} | |")
            w(f"| 缓存 | {sheet['plug']['cache']} | {sheet['base']['cache']} |")
            w(f"| 机器等待 / 人工 | {sheet['plug']['machine_wait']} / {sheet['plug']['human_ops']} | {sheet['base']['machine_wait']} / {sheet['base']['human_ops']} |")
            w("\nP 侧分项：" + "；".join(c["display"] and f"{c['name']} {c['display']}" for c in sheet["plug"]["total"]["components"]))
        except Exception as ex:  # 成本单子不得因口径问题吞掉
            w(f"cost_v3 生成失败：{ex!r}")
    else:
        w("尚无有效配对 → 单位成功成本：没测到。")
    used = br.get("budget", {}).get("used", {})
    w(f"\n本验证全部 LLM 花费（含作废运行，按录像；坏录像取可读前缀）：{used.get('llm_calls')} 次、{used.get('cost_usd')} USD；预算上限 {pr['budget']['max_llm_calls']} 次 / {pr['budget']['max_cost_usd']} USD。")
    for rid, r in roles_cost.items():
        if r["truncated"]:
            w(f"- ⚠ `{rid}` 录像有 EIO 坏尾段，上面的花费只含可读前缀；预算闸按逐题产物下界计（见 raw/{rid}/interruption-audit.json）。")

    # ---- 4 通过/失败/阻塞 ----
    w("\n## 4 通过 / 失败 / 阻塞（case-results.jsonl；未运行不算通过）\n")
    w("| 案例 | 内容 | 结果 | 观察 |\n|:--|:--|:--|:--|")
    for c in cases:
        w(f"| {c['case_id']} | {c['title']} | **{c['result']}** | {str(c['observed'])[:160].replace('|', '/')} |")
    from collections import Counter
    cnt = Counter(c["result"] for c in cases)
    w("\n合计：" + "，".join(f"{k} {v}" for k, v in cnt.items()) + "。按计划 §8 通过规则（必测全过 + 无未处置阻塞 + 独立复核完成），**本批不通过**：至少独立复核、题包授权两项阻塞。")
    if em:
        w(f"\n证据：evidence-manifest.json problems = {len(em.get('problems', []))}；作废运行的证据缺口单列 {len(em.get('invalidated_runs_evidence_gaps', []))} 条（不计入有效证据链）。")

    # ---- 5 插件行为与问题 ----
    w("\n## 5 发现的插件问题与行为观察\n")
    for e in order:
        if e["condition"] != "P":
            continue
        s = inject_stats(vd / "raw" / e["run_id"])
        if not s:
            continue
        tag = "（作废配对，状态经独立校验，仅作行为描述）" if e["pair_id"] in inval else ""
        w(f"- `{e['run_id']}`{tag}：{s['n_cards']} 卡；每卡记忆条数 {s['memories'][0]}–{s['memories'][2]}（中位 {s['memories'][1]}）；注入段 {s['section_bytes'][0]}–{s['section_bytes'][2]} 字节；"
          f"**索引被截断 {s['index_truncated_cards']}/{s['n_cards']} 卡**，平均只露出 {s['index_lines_shown_mean']} 条索引；本卡断点前会话刚固化的新记忆在注入段可见 {s['own_session_visible']}/{s['own_session_written']} 条（{s['cards_with_own_visible']}/{s['n_cards']} 卡至少可见 1 条）。")
    w(FINDINGS)

    # ---- 6 宿主仿真 ----
    w("\n## 6 宿主仿真范围与偏差\n")
    w(EMU_SCOPE)

    # ---- 7 中断与处置 ----
    w("\n## 7 中断、作废与代码改动（留痕）\n")
    for x in st.get("invalidated_pairs", []):
        w(f"- 配对 `{x['pair_id']}` 整对作废（由 `{x['by_run']}` 触发）：" + "；".join(x["reasons"]))
    for x in st.get("appended_reruns", []):
        w(f"- 追加重跑 `{x['run_id']}`（{x['condition']}，seed {x['gen_seed']}）：{x.get('reason', '')[:120]}")
    w(CHANGES)

    # ---- 8 局限 ----
    w("\n## 8 局限\n")
    w(LIMITS)
    if a.judge_v2 and Path(a.judge_v2).exists():
        jv = rj(a.judge_v2)
        w("\n## 9 判分器 v2 下的读数（只新增判分，不重跑作答）\n")
        w(jv.get("markdown", json.dumps(jv, ensure_ascii=False, indent=1)))
    Path(vd / "validation-report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("written", vd / "validation-report.md", len(L), "lines")


FINDINGS = """
- **P1 索引截断让“刚记住的”进不了提示词（影响本任务的主要机制）**：`maxBytes=4096` 同时装索引与约 1.1 KB 的写入指导，索引实际只剩约 2.9 KB；用户作用域条目排在项目条目前面，`pinned` 之外按三因子排序。结果是几十条记忆里只露出十来条，且多为“用户身份/偏好”类泛化条目，本卡会话刚写入的项目记忆大多被截掉。模型在没有 agent 循环（不能调 `memory_read`/`memory_list`）的情况下拿不到正文，续接预测基本得不到具体线索。真实宿主中模型可以调工具补读，所以这一条在真实宿主里的影响会小一些（方向：本仿真对插件偏保守）。
- **P2 近义重复记忆**：同一位使用者在 16 份语料里有不同称呼（荣 / 阿符 / 符荣峻 / furongjun），固化后出现 4 条以上“用户身份”条目并列占用索引额度。插件的去重只按 `name` 复用，不做语义合并；其中一部分是仿真偏差 6 放大的（阶段 A 各语料单独固化，当时看不到已有名单），不能全算插件。
- **P3 “零配置”不成立于自动记忆**：autoSummarize 缺省 false；不开则没有 agent 主动 `memory_write` 时一条也写不进。README 宣称的“零配置”只对手动写入成立（manifest.json#readme_claims_checked）。
- **P4 文件系统绕过宿主沙箱**：插件用 `node:fs` 直接读写 `$DSH_HOME/memory`，源码注释说明是刻意绕过 `ctx.fs` 的 fs-sandbox；未声明权限清单。`_user` 作用域跨工作区注入，同机多项目会互相渗入（state-inventory.json#snapshot_tier）。
- **P5 文档缺口**：README 未写卸载方法；peer 依赖上界 `<0.3.0` 未在 README 写出；包内无 gitHead，tarball↔commit 只能按版本号/时间推断。
- **P6 读也是写**：`memory_read` 会改写 `reads/lastRead`，排序依赖当天日期 → 跨日重跑索引顺序可能不同（本验证每卡新建记忆根，未触发）。
"""

EMU_SCOPE = """**真实（未改一行）**：插件包 `lib/index.js`（sha256 bd7d79ea…1858，与 npm tarball 一致）、`@deepseek-ai/cordis 4.0.4`、`dsh-system-prompt`/`dsh-tools`/`dsh-llm`（`createUserMessage`、`BlockAssembler`）/`dsh-atomic-write`/`dsh-home-paths`、`schemastery`、`yaml`，全部取自真实宿主 DSH 0.2.0-rc.2 安装目录；真实宿主安装与 README 原命令 `dsh plugin --profile demo add dsh-auto-memory` 成功并录像（install/）。

**仿真**（plugins/dsh-auto-memory/README_适配器.md §1 全文）：
1. 会话事件由语料逐轮 `session/event` 回放；AI 轮推理块按 text 进缓冲（真实宿主不捕获），偏差方向不明。
2. 会话结束用 `agent/disposed` 仿真（根会话、delegationDepth=0）。
3. `llm` 服务换成 Cline `cline-pass/deepseek-v4.1-flash`（T=0.7、max_tokens=2048、thinking off；插件不带 temperature，本站固定 0.7 并登记）；无 `dsh-llm-retry`/供应商路由/计量。真实宿主用 DeepSeek Anthropic-Messages 端点。
4. 每会话重挂插件 fiber，记忆只靠磁盘延续。
5. **没有 agent 循环**：模型不能调 `memory_read`/`memory_write`，P 只得到注入段（索引：标题+一行描述）→ 对插件是偏保守的下界。
6. 阶段 A 每份语料单独固化时“已有记忆名”为空；阶段 B 回放时插件看到已有记忆（更新/去重真实发生，但模型当初没看到已有名单）。
7. 16 份语料视为同一工作区；`_user` 作用域也注入。
8. 防泄题：本卡语料只固化答案行之前的轮次；其它 15 份整份固化（语料先后未知，对 P 有利，已登记）。

快照档位：本验证内“可完全重置”（每卡独立空记忆根 + 每作业新 node 进程，`verify_state.py` 独立校验 run-pre/card-pre/card-post/b0）；真实宿主推断“只能部分重置”（会话历史、供应商缓存、`_user` 跨工作区）。"""

CHANGES = """- `104e73f`、`ff27181`：`run_pairs.budget()` 对 EIO 每文件重试 4 次（间隔 2/4/6/8 s），仍失败取 max(可读前缀统计, 逐题产物下界) 并在返回值 `degraded` 留痕。**只影响预算读数，不改判定、有效性或作废规则。**
- `f9aaee4`：`analyze.py`/`evidence.py` 对坏录像容错（可读前缀、哈希登记 `UNREADABLE`）；作废配对的证据缺口单列；`evidence_complete` 闸门改由 evidence-manifest 的 problems 得出（原为硬编码 True）。不改 `verdict_v3`。
- 新增 `report.py`（本报告生成器，只汇总）。
- **三次沙箱重启**（第三次见本节末条）：① 11:43 左右——pair2-P 录像 4 MiB 后 EIO → pair2 整对作废（`2bdd790`）。② 12:57 左右——工作区盘**回退到约 12:45 的状态**（此后写入全部丢失，包括已提交的 pair1-B0 完成结果与 commit `5c3394b`/`d9b4c29`），pair1-B0 录像/判词 EIO；同时 `.git/refs/heads/master`、`.git/index`、`OVERNIGHT.md`、`raw/_status.json` EIO。处置：master 指回 reflog 最后一条 `806f6e1`、重建 index、两文件从 HEAD 取回（坏文件留 `work/eio-broken/`），pair1 整对作废（`1af7090`）。③ 约 14:20 左右——第三次重启（进程全停）；pair1-P-r1 结果此前已入库（`2f93cfd`），14:24 续跑外壳重启（`work/loop_restart.log`），pair1-B0-r1 于 14:25 全新开始（录像仅 1 个 rec.start、无 resume），14:34 完成；收尾时 fscheck 逐文件读 pair1-B0-r1 98/98 可读，git 仓 30,997 个已跟踪文件全部可读；本次重启未造成运行作废。
- 留痕（不进分析）：回退前观察到 pair1-B0 = 37.64（strict 8/para 51/miss 30，判官首批过闸），与 pair1-P = 32.02 构成 Δ = −5.62；该 B0 结果文件已随回退丢失、无法复核，故按作废处理，pair1 以 pair1-r1 重跑。"""

LIMITS = """- **独立场景 = 1**：只证明管线处理这一份历史材料的行为，不能证明跨场景能力；verdict_v3 的场景层区间在 1 个场景上没有跨场景含义。
- **宿主仿真**：见 §6；尤其没有 agent 循环（P 读不到记忆正文），结论方向对插件偏保守。
- **判分器缺陷（validation/_gates/gates-report.md 门槛 2 失败·部分）**：考卷 B 判官对“句式不变、关键实体全换”的答案 3/20 判 strict、15/20 判 paraphrase（得半分）——替换实体漏判。本验证的分数用的正是这个判分器（harness.judge v1），因此 paraphrase 得分可能虚高，且若 P 的注入段让模型给出“像但实体错”的续接，会被同样宽容对待；两臂同一判分器，差值方向受影响程度未知。门槛 2 同时报告考卷 B 在真实模型下 gold=none=0.35，即判分口径分不出“有正确上下文”和“没信息”，这直接限制本验证 Δ 的可解释性。
- **题包授权**：hive-memory-bench `e2e/` 未被 LICENSE 点名 → 材料待核实（DAM-04 阻塞）。
- **独立复核未完成**：review.json 无复核人签字（DAM-09 阻塞）。
- **网关**：与 pes-judge-v2 共享 Cline 网关与匀速闸；网关不保证 seed 复现；两臂温度 0.7，单次运行内随机性未与插件效应分离（每对仅 1 次重跑）。
- **沙箱 I/O**：沙箱重启导致工作区盘出现 EIO（pair2-P 录像；pair1-B0 录像/判词）与一次盘回退，已按预注册整对作废两对（pair2、pair1），各用尽 1 次补跑上限；后续运行若再遇同类故障同样处理。"""


if __name__ == "__main__":
    main()
