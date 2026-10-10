# -*- coding: utf-8 -*-
"""逐案例结果 case-results.jsonl（验证计划 §8：预期、观察、检测事件、处置事件、受影响对象、证据、恢复结果、复核人）。

  python plugins/dsh-auto-memory/cases.py --vdir validation/dam-20261010T1045
未运行 → result="未运行"（不算通过）；阻塞 → result="阻塞"。
"""
from __future__ import annotations
import argparse, json
from pathlib import Path


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--vdir", required=True); a = ap.parse_args()
    vd = Path(a.vdir).resolve()
    pr = rj(vd / "preregistration.json")
    br = rj(vd / "baseline-report.json") if (vd / "baseline-report.json").exists() else {}
    em = rj(vd / "evidence-manifest.json") if (vd / "evidence-manifest.json").exists() else {}
    status = rj(vd / "raw/_status.json") if (vd / "raw/_status.json").exists() else {"runs": {}}
    inst = rj(vd / "install/install_result.json")
    rows = []

    def add(cid, title, expected, observed, result, evidence, detection=None, disposal=None, affected=None, recovery=None):
        rows.append({"case_id": cid, "title": title, "expected": expected, "observed": observed, "result": result,
                     "detection_event": detection, "disposal_event": disposal, "affected_objects": affected or [],
                     "evidence": evidence, "recovery": recovery, "reviewer": None})

    s = {x["id"]: x for x in inst["steps"]}
    ok_install = s.get("S2", {}).get("rc") == 0 and s.get("S4", {}).get("rc") == 0
    add("DAM-01", "真实宿主安装 + README 原命令装插件", "DSH ≥0.1.5-rc.2 装得上；dsh plugin --profile demo add dsh-auto-memory 成功；插件进入 profile",
        f"S2 rc={s.get('S2',{}).get('rc')}；S4 rc={s.get('S4',{}).get('rc')}；--dump-config 出现 id: auto-memory；pnpm 报 8 项 peer missing（宿主提供）",
        "通过" if ok_install else "失败", ["install/install.recording.jsonl", "install/install_result.json"])
    add("DAM-02", "插件身份核实", "npm 最新版、tarball 哈希、commit、依赖、宿主要求、权限、能力照实登记",
        "0.7.0；integrity 本地重算一致；tag v0.7.0=08972390；包内无 gitHead（tarball↔commit 未重建比对）；无权限声明", "通过（附局限：未做源码重建比对）",
        ["manifest.json#plugin_identity"])
    add("DAM-03", "状态清点与快照档位", "列全部状态对象并定档；快照契约三要素写死；独立校验脚本与恢复代码不共用路径",
        "13 个对象；本验证档位=可完全重置（真实宿主推断为只能部分重置）；契约 dam-snap-v1；verify_state.py 不 import 运行代码", "通过（未经独立复核）",
        ["state-inventory.json", "plugins/dsh-auto-memory/verify_state.py"])
    add("DAM-04", "题包核查", "授权、答案键/判分器哈希、泄漏、独立场景分组、权重",
        "哈希已登记；e2e/ 授权=材料待核实；独立场景=1；作者自带 evals 不纳入", "阻塞（授权待核实；场景 1<8 → 只能方法试验）",
        ["fixture-manifest.json"])
    add("DAM-05", "预注册先于运行", "preregistration.json 在第一条运行事件之前提交", "commit a73ecf3 早于 raw/pair2-B0 第一条事件（10:45:53 CST）",
        "通过", ["preregistration.json", "git a73ecf3"])
    order = pr["execution_order"] + status.get("appended_reruns", [])
    for e in order:
        rid = e["run_id"]; rd = vd / "raw" / rid
        st = status["runs"].get(rid, {})
        if not rd.exists():
            add(f"RUN-{rid}", f"运行 {rid}（{e['condition']}）", "运行完成、快照检查通过、判官过闸、证据完整", "未运行", "未运行", [f"raw/{rid}/"])
            continue
        v = rj(rd / "validity.json") if (rd / "validity.json").exists() else None
        sc = rj(rd / "scores.json") if (rd / "scores.json").exists() else None
        pre = rj(rd / "snapshot-check.run-pre.json") if (rd / "snapshot-check.run-pre.json").exists() else None
        miss = (em.get("runs", {}).get(rid) or {}).get("required_missing")
        if v is None:
            res, obs = "未完成", "运行中/中断待续"
        elif v["valid"]:
            res = "通过" if not miss else "失败"
            obs = f"run-pre={pre and pre['pass']}；分数 {sc and sc['score_0_100']}；判官第 {sc and sc['judge_attempt']} 次过闸；parse_err {sc and sc['parse_err']}；证据缺失 {miss}"
        else:
            res, obs = "无效（留痕）", "；".join(v.get("reasons", []))
        add(f"RUN-{rid}", f"运行 {rid}（{e['condition']}，seed {e['gen_seed']}）", "运行完成、快照检查通过、判官过闸、证据完整", obs, res,
            [f"raw/{rid}/"], detection=(v or {}).get("reasons"), disposal=("整对重跑" if v and v["valid"] is False else None), affected=[e["pair_id"]])
    pairs = br.get("pairs", [])
    # 已整对作废留痕的配对（invalid=True）只剩一侧读数是作废留痕，不是"只补一边"；只查未作废的配对（pes-close 修正）
    single = [p for p in pairs if not p.get("invalid") and (p.get("B0") is None) != (p.get("P") is None) and status.get("all_done")]
    add("DAM-06", "无只补一边", "无效运行整对重跑；不存在只有一侧的有效配对", f"整对作废 {len(status.get('invalidated_pairs', []))}；单边配对 {len(single)}",
        "通过" if not single else "失败", ["raw/_status.json"])
    vv = br.get("verdict_v3") or {}
    add("DAM-07", "判定（verdict_v3）", "按预注册算法给出运行层/发布层状态；场景=1 时只能方法试验，不出正式五状态",
        f"run_state={vv.get('run_state')}；release_state={vv.get('release_state')}；capability={vv.get('capability')}；observed={vv.get('capability_observed')}；估计={vv.get('estimate')}；区间={vv.get('interval')}",
        "通过" if vv.get("release_state") in ("方法试验", "待验证/待修复") and vv.get("capability") is None else ("未运行" if not vv else ("需复核" if status.get("all_done") else "未完成（样本未齐）")),
        ["baseline-report.json#verdict_v3"])
    add("DAM-08", "证据完整性", "每个运行的必要证据齐全、登记哈希", f"problems={len(em.get('problems', []))}", ("通过" if em and not em.get("problems") else ("未运行" if not em else ("失败" if status.get("all_done") else "未完成（运行未全部结束）"))),
        ["evidence-manifest.json"])
    add("DAM-09", "独立复核", "独立复核者重算并签字", "未指派", "阻塞", ["review.json"])
    add("DAM-10", "受控夹具/故障注入/边界回归", "归 pes-e2e-gates", "不在本批范围", "未运行（他方负责）", ["validation/_gates/"])
    (vd / "case-results.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    from collections import Counter
    print(Counter(r["result"] for r in rows))


if __name__ == "__main__":
    main()
