# -*- coding: utf-8 -*-
"""安装录像用的小探针（每个子命令一条录像命令）。令牌只从 0600 文件读，输出一律脱敏。
用法：python3 probe_cli.py <sub> --base B --clone C --token <file> --root <MDCG_ROOT> [...]
  handshake  ：initialize + tools/list + whoami（surface 由 --surface 给）
  ingest     ：cg(op=ingest, action=jsonl, path=--jsonl)，可 --repeat 2 看水位
  remember   ：mdcg_remember(gated=true, layer=contextual, role=user, importance=0.6) 逐条写 --jsonl 里的用户消息（--n 条），
               统计闸门四态与耗时（= DSH 运行时自动记忆的缺省通道）
  recallone  ：mdcg_recall(--query) 一次
"""
import argparse
import collections
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_stdio import StdioMCP  # noqa: E402

TOK = re.compile(r"mdcg1\.[A-Za-z0-9._\-]+")


def red(x):
    return TOK.sub("<REDACTED>", json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sub")
    ap.add_argument("--base", required=True)
    ap.add_argument("--clone", required=True)
    ap.add_argument("--token", default="")
    ap.add_argument("--root", required=True)
    ap.add_argument("--surface", default="full")
    ap.add_argument("--jsonl", default="")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--query", default="")
    a = ap.parse_args()
    os.makedirs(a.root, exist_ok=True)
    env = {"HOME": a.base + "/home", "PATH": a.base + "/venv/bin:/usr/bin:/bin", "PYTHONPATH": a.clone,
           "PYTHONUTF8": "1", "MDCG_ROOT": a.root, "MDCG_MCP_SURFACE": a.surface}
    if a.token:
        env["MDCG_TOKEN"] = open(a.token).read().strip()
    t0 = time.monotonic()
    m = StdioMCP([a.base + "/venv/bin/python", "-m", "md_cg.mcp_server"], cwd=a.base, env=env,
                 stderr_path=a.base + "/probe_stderr.log")
    init = m.initialize()
    print("initialize %.2fs %s" % (time.monotonic() - t0, red(init.get("serverInfo"))))
    if a.sub == "handshake":
        tools = [t["name"] for t in m.request("tools/list")["tools"]]
        print("tools/list (%d): %s" % (len(tools), tools))
        p, raw, e = m.call_tool("mdcg_whoami", {}) if "mdcg_whoami" in tools else m.call_tool("cg", {"op": "info"})
        pr = p.get("principal", p) if isinstance(p, dict) else {}
        print("principal:", red({k: pr.get(k) for k in ("role", "clearance", "can_write", "can_admin", "auth_mode", "ops_allow")}))
    elif a.sub == "ingest":
        for i in range(a.repeat):
            t = time.monotonic()
            p, raw, e = m.call_tool("cg", {"op": "ingest", "action": "jsonl", "path": a.jsonl})
            d = p if isinstance(p, dict) else {"raw": raw[:400]}
            print("ingest#%d %.2fs isError=%s %s" % (i + 1, time.monotonic() - t, e, red(
                {k: d.get(k) for k in ("new_events", "written", "denied", "sensitivity", "last_error", "hint", "error")})))
    elif a.sub == "ingest_fine":
        for i in range(a.repeat):
            t = time.monotonic()
            p, raw, e = m.call_tool("mdcg_ingest", {"source": a.jsonl})
            d = p if isinstance(p, dict) else {"raw": raw[:400]}
            print("mdcg_ingest#%d %.2fs isError=%s %s" % (i + 1, time.monotonic() - t, e, red(
                {k: d.get(k) for k in ("new_events", "written", "denied", "sensitivity", "last_error", "error")})))
    elif a.sub == "remember":
        msgs = [json.loads(l) for l in open(a.jsonl, encoding="utf-8")]
        msgs = [x for x in msgs if x["role"] == "user"][:a.n]
        cnt, lat = collections.Counter(), []
        for x in msgs:
            t = time.monotonic()
            p, raw, e = m.call_tool("mdcg_remember", {"content": x["text"], "gated": True, "layer": "contextual",
                                                      "role": "user", "importance": 0.6})
            lat.append(time.monotonic() - t)
            cnt[(p.get("verdict") if isinstance(p, dict) else None) or ("ERROR" if e else "?")] += 1
        lat.sort()
        print("remember n=%d verdicts=%s  mean=%.3fs p50=%.3fs p95=%.3fs" % (
            len(msgs), dict(cnt), sum(lat) / max(1, len(lat)), lat[len(lat) // 2], lat[int(len(lat) * .95) - 1]))
    elif a.sub == "recallone":
        t = time.monotonic()
        p, raw, e = m.call_tool("mdcg_recall", {"query": a.query})
        d = p if isinstance(p, dict) else {}
        print("recall %.2fs n=%s tokens_used=%s" % (time.monotonic() - t, len(d.get("pack") or []), d.get("tokens_used")))
    m.close()


if __name__ == "__main__":
    main()
