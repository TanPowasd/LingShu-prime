# 录像时间轴 · everos_probe

源：`everos_probe.jsonl`，共 19 个事件。时间轴为单调钟 mm:ss（续跑累加），墙钟见右列。

| mm:ss | #seq | 墙钟(CST) | 事件 | 摘要 |
|:--|--:|:--|:--|:--|
| 00:00 | 1 | 07:43:57.813 | rec.start | {"pid": 2626} |
| 00:00 | 2 | 07:43:57.815 | plugin.install.begin | {"plugin": "everos", "version": "1.4.1@462ebf9", "base": "/workspace/work/pes/runs/everos/probe_sbx", "HOME": "/workspace/work/pes/runs/everos/probe_sbx/home",  |
| 00:00 | 3 | 07:43:57.815 | cmd.start | {"cmd": "uv venv /workspace/work/pes/runs/everos/probe_sbx/venv --python 3.12"} |
| 00:00 | 4 | 07:43:57.923 | cmd.end | {"rc": 0, "dur_s": 0.108} |
| 00:00 | 5 | 07:43:57.923 | cmd.start | {"cmd": "uv pip install everos==1.4.1"} |
| 00:17 | 6 | 07:44:15.114 | cmd.end | {"rc": 0, "dur_s": 17.19} |
| 00:17 | 7 | 07:44:15.114 | cmd.start | {"cmd": "everos init"} |
| 00:51 | 8 | 07:44:49.508 | cmd.end | {"rc": 0, "dur_s": 34.394} |
| 00:51 | 9 | 07:44:49.511 | file.edit | {"path": "~/.everos/everos.toml", "section": "[llm]", "after": {"model": "cline-pass/deepseek-v4.1-flash", "api_key": "<占位，非密钥>", "base_url": "http://127.0.0.1: |
| 00:51 | 10 | 07:44:49.513 | station.proxy.start | {"pid": 2787, "port": 18791, "note": "考场侧转发器，不属于插件"} |
| 00:53 | 11 | 07:44:51.014 | cmd.start | {"cmd": "ulimit -n 4096; exec everos server start"} |
| 01:09 | 12 | 07:45:07.107 | cmd.end | {"rc": 0, "dur_s": 16.092} |
| 01:09 | 13 | 07:45:07.108 | plugin.install.result | {"ok": true, "steps": 5, "errors": []} |
| 02:05 | 14 | 07:46:02.871 | plugin.flush | {"file": "传递信任与经验.md", "msgs": 10, "est_tokens": 12858, "code": 200, "status": "extracted", "add_s": 0.04} |
| 03:22 | 15 | 07:47:20.766 | plugin.flush | {"file": "传递信任与经验.md", "msgs": 6, "est_tokens": 12115, "code": 200, "status": "extracted", "add_s": 0.04} |
| 06:32 | 16 | 07:50:30.193 | plugin.flush | {"file": "传递信任与经验.md", "msgs": 13, "est_tokens": 12690, "code": 200, "status": "extracted", "add_s": 0.05} |
| 08:35 | 17 | 07:52:33.291 | plugin.flush | {"file": "传递信任与经验.md", "msgs": 13, "est_tokens": 12030, "code": 200, "status": "extracted", "add_s": 0.04} |
| 09:25 | 18 | 07:53:23.192 | plugin.flush | {"file": "传递信任与经验.md", "msgs": 8, "est_tokens": 15480, "code": 200, "status": "extracted", "add_s": 0.15} |
| 09:51 | 19 | 07:53:49.773 | plugin.flush | {"file": "传递信任与经验.md", "msgs": 4, "est_tokens": 12924, "code": 200, "status": "extracted", "add_s": 0.08} |
