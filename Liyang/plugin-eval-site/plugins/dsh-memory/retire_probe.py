# -*- coding: utf-8 -*-
"""旧账复测：退役/撤销后，召回面还会不会返回被撤销的值？（对应 hmb《秤》退役纪律 6/6 泄漏旧账）

在 @c8c3655 上经 MCP 公开面复测（不是 hmb 当时的私有探针，口径不同，只作同题复查）：
每个场景：mdcg_remember 写 v1 → 写矛盾 v2 → 召回(查 v2 在不在) → cg(op=forget, node_id=v2) 撤销 v2 → 召回(查 v2 还在不在)
另：forget 后用 cg(op=read, node_id=v2) 看节点状态。全程录像。
用法：python3 retire_probe.py --out <录像目录>（复用 install_recorded 的 /tmp/pes-dshm 环境需先 clone；本脚本自建沙箱）
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adapter import DshMemory  # noqa: E402
from rec_local import Rec, render_md  # noqa: E402

SCEN = [
    ("发布窗口", "我们团队的发布窗口是每周三下午。", "更正：我们团队的发布窗口改为每周五上午。", "我们团队的发布窗口是哪天？", "周五"),
    ("会议室", "周会固定在三楼 A301 会议室开。", "周会改到五楼 B502 会议室了。", "周会在哪个会议室开？", "B502"),
    ("负责人", "支付模块的负责人是王磊。", "支付模块负责人换成了陈静。", "支付模块现在谁负责？", "陈静"),
    ("预算", "本季度市场预算是 30 万元。", "本季度市场预算下调为 18 万元。", "本季度市场预算是多少？", "18 万"),
    ("截止", "接口文档的截止日期是 10 月 15 日。", "接口文档截止日期延后到 10 月 22 日。", "接口文档什么时候截止？", "10 月 22"),
    ("端口", "测试环境服务端口是 8080。", "测试环境服务端口改成了 9090。", "测试环境的服务端口是多少？", "9090"),
]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args()
    rec = Rec(os.path.join(a.out, "retire_probe.jsonl"), "退役/撤销复测（6 场景）", run="dsh_retire")
    pl = DshMemory(base="/tmp/pes-dshm-retire", extra_ops="forget,review")
    r = pl.install(rec); rec.event("install.result", ok=r.ok, errors=r.errors)
    m = pl.mcp
    res = []
    for name, v1, v2, q, key in SCEN:
        p1, _, _ = m.call_tool("mdcg_remember", {"content": v1, "gated": True, "layer": "contextual", "role": "user", "importance": 0.6})
        p2, _, _ = m.call_tool("mdcg_remember", {"content": v2, "gated": True, "layer": "contextual", "role": "user", "importance": 0.6})
        id2 = (p2 or {}).get("written") or (p2 or {}).get("node_id")
        rec.event("write", scen=name, v1_verdict=(p1 or {}).get("verdict"), v2_verdict=(p2 or {}).get("verdict"), v2_id=id2,
                  v2_gate=json.dumps((p2 or {}).get("gate"), ensure_ascii=False)[:400])
        before, _, _ = m.call_tool("mdcg_recall", {"query": q})
        b_hit = any(key in (it.get("content") or "") for it in (before or {}).get("pack", []))
        f, raw, ferr = m.call_tool("cg", {"op": "forget", "node_id": id2, "reason": "用户撤销该更正"}) if id2 else (None, "", True)
        rec.event("forget", scen=name, isError=ferr, resp=json.dumps(f, ensure_ascii=False)[:600])
        after1, _, _ = m.call_tool("mdcg_recall", {"query": q})
        a1_hit = any(key in (it.get("content") or "") for it in (after1 or {}).get("pack", []))
        pid = f.get("pid") if isinstance(f, dict) else None
        rv = None
        if pid:   # forget 只出变更单进审核队列 → 按 hint 用 cg(op=review) 裁决 accept，再查
            rv, _, rverr = m.call_tool("cg", {"op": "review", "pid": pid, "decision": "accept", "reason": "复测：确认撤销"})
            rec.event("review", scen=name, isError=rverr, resp=json.dumps(rv, ensure_ascii=False)[:500])
        after, _, _ = m.call_tool("mdcg_recall", {"query": q})
        a_hit = [it.get("id") for it in (after or {}).get("pack", []) if key in (it.get("content") or "")]
        rd, _, _ = m.call_tool("cg", {"op": "read", "node_id": id2})
        state = None
        if isinstance(rd, dict):
            fm = rd.get("frontmatter") or (rd.get("node") or {}).get("frontmatter") or {}
            state = fm.get("lifecycle_state") or rd.get("state") or rd.get("error")
        row = {"scen": name, "v2_in_recall_before": b_hit, "v2_in_recall_after_forget_only": a1_hit, "review_accepted": bool(rv and isinstance(rv, dict) and rv.get("ok")),
               "v2_in_recall_after_review": bool(a_hit),
               "v2_written": bool(id2), "forget_resp": json.dumps(f, ensure_ascii=False)[:200], "v2_state_after": state}
        res.append(row); rec.event("result", **row)
    leak = sum(r["v2_in_recall_after_review"] for r in res)
    rec.event("summary", leak=f"{leak}/{len(res)}", rows=res)
    pl.uninstall(rec); rec.close()
    render_md(os.path.join(a.out, "retire_probe.jsonl"), os.path.join(a.out, "retire_probe_时间轴.md"), "退役/撤销复测 · 录像时间轴")
    print(json.dumps(res, ensure_ascii=False, indent=1)); print("leak", leak)


if __name__ == "__main__":
    main()
