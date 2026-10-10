# 录像时间轴 · dam-install

源：`install.recording.jsonl`，共 33 个事件。时间轴为单调钟 mm:ss（续跑累加），墙钟见右列。

| mm:ss | #seq | 墙钟(CST) | 事件 | 摘要 |
|:--|--:|:--|:--|:--|
| 00:00 | 1 | 10:26:50.326 | rec.start | {"pid": 1892} |
| 00:00 | 2 | 10:26:50.326 | sandbox.create | {"root": "/workspace/work/pes/plugins/dsh-auto-memory/_sbx/install", "env_keys": ["HOME", "LANG", "LC_ALL", "PATH", "TMPDIR", "npm_config_audit", "npm_config_ca |
| 00:00 | 3 | 10:26:50.326 | step | {"id": "S1a"} |
| 00:00 | 4 | 10:26:50.326 | cmd.start | {"cmd": ["node", "-v"]} |
| 00:00 | 5 | 10:26:50.330 | cmd.end | {"rc": 0, "dur_s": 0.004} |
| 00:00 | 6 | 10:26:50.332 | step | {"id": "S1b"} |
| 00:00 | 7 | 10:26:50.332 | cmd.start | {"cmd": ["npm", "-v"]} |
| 00:00 | 8 | 10:26:50.652 | cmd.end | {"rc": 0, "dur_s": 0.32} |
| 00:00 | 9 | 10:26:50.654 | step | {"id": "S2"} |
| 00:00 | 10 | 10:26:50.654 | cmd.start | {"cmd": ["npm", "i", "-g", "--prefix", "/workspace/work/pes/plugins/dsh-auto-memory/_sbx/install/npm-global", "@deepseek-ai/dsh@0.2.0-rc.2"]} |
| 01:43 | 11 | 10:28:33.586 | cmd.end | {"rc": 0, "dur_s": 102.932} |
| 01:43 | 12 | 10:28:33.588 | step | {"id": "S3a"} |
| 01:43 | 13 | 10:28:33.589 | cmd.start | {"cmd": ["dsh", "--version"]} |
| 01:44 | 14 | 10:28:34.635 | cmd.end | {"rc": 0, "dur_s": 1.046} |
| 01:44 | 15 | 10:28:34.638 | step | {"id": "S3b"} |
| 01:44 | 16 | 10:28:34.638 | cmd.start | {"cmd": ["dsh", "--help"]} |
| 01:44 | 17 | 10:28:34.777 | cmd.end | {"rc": 0, "dur_s": 0.139} |
| 01:44 | 18 | 10:28:34.786 | step | {"id": "S4"} |
| 01:44 | 19 | 10:28:34.786 | cmd.start | {"cmd": ["dsh", "plugin", "--profile", "demo", "add", "dsh-auto-memory"]} |
| 01:47 | 20 | 10:28:37.687 | cmd.end | {"rc": 0, "dur_s": 2.901} |
| 01:47 | 21 | 10:28:37.688 | step | {"id": "S6"} |
| 01:47 | 22 | 10:28:37.688 | cmd.start | {"cmd": ["dsh", "plugin", "--help"]} |
| 01:47 | 23 | 10:28:37.811 | cmd.end | {"rc": 1, "dur_s": 0.123} |
| 01:47 | 24 | 10:28:37.813 | step | {"id": "S5a"} |
| 01:47 | 25 | 10:28:37.814 | cmd.start | {"cmd": "find $HOME -maxdepth 4 -not -path '*/node_modules/*' -not -path '*/.npm/*' \| head -100"} |
| 01:47 | 26 | 10:28:37.848 | cmd.end | {"rc": 0, "dur_s": 0.035} |
| 01:47 | 27 | 10:28:37.950 | step | {"id": "S5b"} |
| 01:47 | 28 | 10:28:37.950 | cmd.start | {"cmd": "find $HOME -name cordis.patch.yml -not -path '*/.npm/*' \| head; for f in $(find $HOME -name 'cordis*.yml' -not -path '*/.npm/*' \| head -5); do echo == $f; cat $f; done"} |
| 01:49 | 29 | 10:28:39.959 | cmd.end | {"rc": 0, "dur_s": 2.009} |
| 01:49 | 30 | 10:28:39.960 | step | {"id": "S5c"} |
| 01:49 | 31 | 10:28:39.961 | cmd.start | {"cmd": "for d in $(find $HOME /workspace/work/pes/plugins/dsh-auto-memory/_sbx/install/npm-global -type d -name dsh-auto-memory -path '*node_modules*' 2>/dev/null \| head -5); do echo == $d; cat $d/package.json \| head -5; sha256sum $d/lib/index.js; done"} |
| 01:52 | 32 | 10:28:42.790 | cmd.end | {"rc": 0, "dur_s": 2.829} |
| 01:52 | 33 | 10:28:42.794 | rec.stop | {} |
