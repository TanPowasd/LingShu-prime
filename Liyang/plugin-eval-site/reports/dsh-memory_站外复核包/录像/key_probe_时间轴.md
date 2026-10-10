# 主密钥分居探针 · 录像时间轴 · · dsh_key

源：`key_probe.jsonl`，共 18 个事件。时间轴为单调钟 mm:ss（续跑累加），墙钟见右列。

| mm:ss | #seq | 墙钟(CST) | 事件 | 摘要 |
|:--|--:|:--|:--|:--|
| 00:00 | 1 | 00:52:10.399 | rec_start | {"mmss": "00:00", "title": "主密钥分居探针"} |
| 00:00 | 2 | 00:52:10.459 | plugin.install.begin | {"mmss": "00:00", "plugin": "dsh-memory", "sha": "c8c3655234d57214ae990ab2c7590f7ba590d901", "base": "/tmp/pes-dshm-key", "HOME": "/tmp/pes-dshm-key/home", "MDC |
| 00:00 | 3 | 00:52:10.459 | cmd.start | {"cmd": "/usr/local/bin/python3 -m venv /tmp/pes-dshm-key/venv"} |
| 00:01 | 4 | 00:52:12.163 | cmd.end | {"rc": 0, "dur_s": 1.704} |
| 00:01 | 5 | 00:52:12.163 | cmd.start | {"cmd": "git clone -q https://github.com/FuRongJun-1999/dsh-memory.git /tmp/pes-dshm-key/work/dsh-memory && git -C /tmp/pes-dshm-key/work/dsh-memory checkout -q c8c3655234d57214ae990ab2c7590f7ba590d901 && git -C /tmp/pes-dshm-key/work/dsh-memory log -1 --format=%H"} |
| 00:04 | 6 | 00:52:14.750 | cmd.end | {"rc": 0, "dur_s": 2.587} |
| 00:04 | 7 | 00:52:14.750 | cmd.start | {"cmd": "python3 -m md_cg.mcp_server --show-config"} |
| 00:04 | 8 | 00:52:14.942 | cmd.end | {"rc": 0, "dur_s": 0.192} |
| 00:04 | 9 | 00:52:14.942 | cmd.start | {"cmd": "python3 -m md_cg.tokens issue --role designer --actor pes-dsh --clearance private --ops-allow info,route,read,write,recent,goal,identity,whitebox,verify,ingest,session --layers-allow knowledge,contextual,structural,self,goals,unresolved,rejected > /tmp/pes-dshm-key/secrets/designer.out 2>&1; echo rc=$?"} |
| 00:04 | 10 | 00:52:15.056 | cmd.end | {"rc": 0, "dur_s": 0.114} |
| 00:04 | 11 | 00:52:15.057 | plugin.token | {"mmss": "00:04", "role": "designer", "clearance": "private", "ops_allow": ["info", "route", "read", "write", "recent", "goal", "identity", "whitebox", "verify" |
| 00:06 | 12 | 00:52:16.869 | mcp.ready | {"mmss": "00:06", "server": {"name": "mdcg-mcp", "version": "0.8.1"}, "n_tools": 33, "tools": ["cg", "stg", "mdcg_remember", "mdcg_recall", "mdcg_search", "mdcg |
| 00:07 | 13 | 00:52:17.475 | plugin.ingest | {"mmss": "00:07", "session": "公式符号复制乱码原因.md", "turns": 50, "new_events": 50, "written": 50, "denied": 0} |
| 00:07 | 14 | 00:52:17.476 | plugin.ingest.done | {"mmss": "00:07", "sessions": 1, "events": 50, "written": 50, "denied": 0, "dur_s": 0.352} |
| 00:07 | 15 | 00:52:17.837 | plugin.recall | {"mmss": "00:07", "query": "公式符号复制后保存到md里乱码", "sources": ["公式符号复制乱码原因.md#L3-L39"], "dur_s": 0.361, "k": 5, "n": 1} |
| 00:08 | 16 | 00:52:19.338 | mcp.ready | {"mmss": "00:08", "server": {"name": "mdcg-mcp", "version": "0.8.1"}, "n_tools": 33, "tools": ["cg", "stg", "mdcg_remember", "mdcg_recall", "mdcg_search", "mdcg |
| 00:08 | 17 | 00:52:19.346 | plugin.recall | {"mmss": "00:08", "query": "公式符号复制后保存到md里乱码", "sources": [], "dur_s": 0.008, "k": 5, "n": 0} |
| 00:08 | 18 | 00:52:19.346 | rec_end | {"mmss": "00:08"} |

---

## 命令输出明细

> 源：`key_probe.jsonl`（JSONL 事件流；mm:ss = 自录像开始的单调钟）

- **[00:00] #1** `rec_start` {"title": "主密钥分居探针"}
- **[00:00] #2** `plugin.install.begin` {"plugin": "dsh-memory", "sha": "c8c3655234d57214ae990ab2c7590f7ba590d901", "base": "/tmp/pes-dshm-key", "HOME": "/tmp/pes-dshm-key/home", "MDCG_ROOT": "/tmp/pes-dshm-key/root"}
- **[00:00] #3** `cmd.start` {"cmd": "/usr/local/bin/python3 -m venv /tmp/pes-dshm-key/venv", "cwd": "/tmp/pes-dshm-key", "step": "venv"}
- **[00:01] #4** `cmd.end` {"rc": 0, "stdout": "", "stderr": "", "dur_s": 1.704, "step": "venv"}
- **[00:01] #5** `cmd.start` {"cmd": "git clone -q https://github.com/FuRongJun-1999/dsh-memory.git /tmp/pes-dshm-key/work/dsh-memory && git -C /tmp/pes-dshm-key/work/dsh-memory checkout -q c8c3655234d57214ae990ab2c7590f7ba590d901 && git -C /tmp/pes-dshm-key/work/dsh-memory log -1 --format=%H", "cwd": "/tmp/pes-dshm-key", "step": "clone"}
- **[00:04] #6** `cmd.end` {"rc": 0, "stdout": "c8c3655234d57214ae990ab2c7590f7ba590d901\n", "stderr": "", "dur_s": 2.587, "step": "clone"}
- **[00:04] #7** `cmd.start` {"cmd": "python3 -m md_cg.mcp_server --show-config", "cwd": "/tmp/pes-dshm-key/work/dsh-memory", "step": "selfcheck"}
- **[00:04] #8** `cmd.end` {"rc": 0, "stdout": "{\"server\": \"mdcg-mcp\", \"version\": \"0.8.1\", \"policy\": {\"source\": \"package_default\", \"path\": \"/tmp/pes-dshm-key/work/dsh-memory/data/policy.json\", \"available\": true, \"forbidden\": 12, \"required\": 6, \"error\": null}}\n", "stderr": "", "dur_s": 0.192, "step": "selfcheck"}
- **[00:04] #9** `cmd.start` {"cmd": "python3 -m md_cg.tokens issue --role designer --actor pes-dsh --clearance private --ops-allow info,route,read,write,recent,goal,identity,whitebox,verify,ingest,session --layers-allow knowledge,contextual,structural,self,goals,unresolved,rejected > /tmp/pes-dshm-key/secrets/designer.out 2>&1; echo rc=$?", "cwd": "/tmp/pes-dshm-key/work/dsh-memory", "step": "token"}
- **[00:04] #10** `cmd.end` {"rc": 0, "stdout": "rc=0\n", "stderr": "", "dur_s": 0.114, "step": "token"}
- **[00:04] #11** `plugin.token` {"role": "designer", "clearance": "private", "ops_allow": ["info", "route", "read", "write", "recent", "goal", "identity", "whitebox", "verify", "ingest", "session"], "layers_allow": ["knowledge", "contextual", "structural", "self", "goals", "unresolved", "rejected"], "token": "<REDACTED>", "token_file": "/tmp/pes-dshm-key/home/.mdcg/_tokens.json"}
- **[00:06] #12** `mcp.ready` {"server": {"name": "mdcg-mcp", "version": "0.8.1"}, "n_tools": 33, "tools": ["cg", "stg", "mdcg_remember", "mdcg_recall", "mdcg_search", "mdcg_get", "mdcg_reflect", "mdcg_verify", "mdcg_flywheel", "mdcg_mine_fix_pairs", "mdcg_rejected", "mdcg_unresolved", "mdcg_propose", "mdcg_review_list", "mdcg_review_decide", "mdcg_review_records", "mdcg_forget", "mdcg_protect", "mdcg_forgetting_history", "mdcg_identity", "mdcg_consistency", "mdcg_metacognition", "mdcg_self_state", "mdcg_predict", "mdcg_causal", "mdcg_evolution", "mdcg_restore", "mdcg_health", "mdcg_whoami", "mdcg_ingest", "mdcg_watermarks…
- **[00:07] #13** `plugin.ingest` {"session": "公式符号复制乱码原因.md", "turns": 50, "new_events": 50, "written": 50, "denied": 0, "id_map_hit": "50/50", "dur_s": 0.35, "chars": 106464}
- **[00:07] #14** `plugin.ingest.done` {"sessions": 1, "events": 50, "written": 50, "denied": 0, "dur_s": 0.352, "root_bytes": 428259}
- **[00:07] #15** `plugin.recall` {"query": "公式符号复制后保存到md里乱码", "sources": ["公式符号复制乱码原因.md#L3-L39"], "dur_s": 0.361, "k": 5, "n": 1, "tokens_used": 1185, "budget": 1200, "skipped": 4, "chars": 2856, "unmapped": 0}
- **[00:08] #16** `mcp.ready` {"server": {"name": "mdcg-mcp", "version": "0.8.1"}, "n_tools": 33, "tools": ["cg", "stg", "mdcg_remember", "mdcg_recall", "mdcg_search", "mdcg_get", "mdcg_reflect", "mdcg_verify", "mdcg_flywheel", "mdcg_mine_fix_pairs", "mdcg_rejected", "mdcg_unresolved", "mdcg_propose", "mdcg_review_list", "mdcg_review_decide", "mdcg_review_records", "mdcg_forget", "mdcg_protect", "mdcg_forgetting_history", "mdcg_identity", "mdcg_consistency", "mdcg_metacognition", "mdcg_self_state", "mdcg_predict", "mdcg_causal", "mdcg_evolution", "mdcg_restore", "mdcg_health", "mdcg_whoami", "mdcg_ingest", "mdcg_watermarks…
- **[00:08] #17** `plugin.recall` {"query": "公式符号复制后保存到md里乱码", "sources": [], "dur_s": 0.008, "k": 5, "n": 0, "tokens_used": 0, "budget": 1200, "skipped": 0, "chars": 0, "unmapped": 0}
- **[00:08] #18** `rec_end`
