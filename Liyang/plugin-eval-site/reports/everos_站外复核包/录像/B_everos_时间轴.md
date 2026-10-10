# 录像时间轴 · B_everos

源：`B_everos.jsonl`，共 237 个事件。时间轴为单调钟 mm:ss（续跑累加），墙钟见右列。

| mm:ss | #seq | 墙钟(CST) | 事件 | 摘要 |
|:--|--:|:--|:--|:--|
| 00:00 | 1 | 07:52:42.956 | rec.start | {"pid": 3791} |
| 00:00 | 2 | 07:52:43.004 | run.config | {"exam": "B/e2e-C v0.1", "plugin": "plugins/everos/adapter.py:EverOS", "plugin_name": "everos", "plugin_version": "1.4.1@462ebf9", "plugin_kind": "http-local",  |
| 00:00 | 3 | 07:52:43.014 | sandbox.create | {"root": "/workspace/work/pes/runs/sbx/B_everos", "env_keys": ["HOME", "LANG", "LC_ALL", "PATH", "PIP_DISABLE_PIP_VERSION_CHECK", "PYTHONNOUSERSITE", "TMPDIR",  |
| 00:00 | 4 | 07:52:43.017 | plugin.install.begin | {"plugin": "everos", "version": "1.4.1@462ebf9", "base": "/workspace/work/pes/runs/sbx/B_everos", "HOME": "/workspace/work/pes/runs/sbx/B_everos/home", "memory_ |
| 00:00 | 5 | 07:52:43.018 | cmd.start | {"cmd": "uv venv /workspace/work/pes/runs/sbx/B_everos/venv --python 3.12"} |
| 00:00 | 6 | 07:52:43.238 | cmd.end | {"rc": 0, "dur_s": 0.22} |
| 00:00 | 7 | 07:52:43.238 | cmd.start | {"cmd": "uv pip install everos==1.4.1"} |
| 00:17 | 8 | 07:53:00.213 | cmd.end | {"rc": 0, "dur_s": 16.976} |
| 00:17 | 9 | 07:53:00.214 | cmd.start | {"cmd": "everos init --root /workspace/work/pes/runs/B_everos/everos_state/root"} |
| 00:48 | 10 | 07:53:31.539 | cmd.end | {"rc": 0, "dur_s": 31.325} |
| 00:48 | 11 | 07:53:31.544 | file.edit | {"path": "~/.everos/everos.toml", "section": "[llm]", "after": {"model": "cline-pass/deepseek-v4.1-flash", "api_key": "<占位，非密钥>", "base_url": "http://127.0.0.1: |
| 00:48 | 12 | 07:53:31.551 | station.proxy.start | {"pid": 4015, "port": 18781, "note": "考场侧转发器，不属于插件"} |
| 00:50 | 13 | 07:53:33.052 | cmd.start | {"cmd": "ulimit -n 4096; exec everos server start --root /workspace/work/pes/runs/B_everos/everos_state/root"} |
| 01:05 | 14 | 07:53:48.141 | cmd.end | {"rc": 0, "dur_s": 15.087} |
| 01:05 | 15 | 07:53:48.141 | plugin.install.result | {"ok": true, "steps": 5, "errors": [], "dur_s": 65.125} |
| 01:05 | 16 | 07:54:00.886 | rec.resume | {"pid": 4213} |
| 01:05 | 17 | 07:54:00.994 | run.config | {"exam": "B/e2e-C v0.1", "plugin": "plugins/everos/adapter.py:EverOS", "plugin_name": "everos", "plugin_version": "1.4.1@462ebf9", "plugin_kind": "http-local",  |
| 01:15 | 18 | 07:54:10.823 | sandbox.create | {"root": "/workspace/work/pes/runs/sbx/B_everos", "env_keys": ["HOME", "LANG", "LC_ALL", "PATH", "PIP_DISABLE_PIP_VERSION_CHECK", "PYTHONNOUSERSITE", "TMPDIR",  |
| 01:15 | 19 | 07:54:10.827 | plugin.install.begin | {"plugin": "everos", "version": "1.4.1@462ebf9", "base": "/workspace/work/pes/runs/sbx/B_everos", "HOME": "/workspace/work/pes/runs/sbx/B_everos/home", "memory_ |
| 01:15 | 20 | 07:54:10.827 | plugin.install.note | {"note": "续跑：持久记忆根已有 everos.toml，跳过 init（init 无 --force 会 rc=1）", "root": "/workspace/work/pes/runs/B_everos/everos_state/root"} |
| 01:15 | 21 | 07:54:10.827 | cmd.start | {"cmd": "uv venv /workspace/work/pes/runs/sbx/B_everos/venv --python 3.12"} |
| 01:15 | 22 | 07:54:10.919 | cmd.end | {"rc": 0, "dur_s": 0.092} |
| 01:15 | 23 | 07:54:10.919 | cmd.start | {"cmd": "uv pip install everos==1.4.1"} |
| 01:32 | 24 | 07:54:27.877 | cmd.end | {"rc": 0, "dur_s": 16.957} |
| 01:32 | 25 | 07:54:27.879 | file.edit | {"path": "~/.everos/everos.toml", "section": "[llm]", "after": {"model": "cline-pass/deepseek-v4.1-flash", "api_key": "<占位，非密钥>", "base_url": "http://127.0.0.1: |
| 01:32 | 26 | 07:54:27.881 | station.proxy.start | {"pid": 4335, "port": 18781, "note": "考场侧转发器，不属于插件"} |
| 01:33 | 27 | 07:54:29.383 | cmd.start | {"cmd": "ulimit -n 4096; exec everos server start --root /workspace/work/pes/runs/B_everos/everos_state/root"} |
| 02:18 | 28 | 07:55:14.493 | cmd.end | {"rc": 0, "dur_s": 45.108} |
| 02:18 | 29 | 07:55:14.493 | plugin.install.result | {"ok": true, "steps": 4, "errors": [], "dur_s": 63.667} |
| 02:23 | 30 | 07:55:19.539 | plugin.ingest.plan | {"sessions": 16, "batches": 698, "already_done": 0, "par": 2, "flush_msgs": 50, "flush_tokens": 12000} |
| 04:01 | 31 | 07:56:57.026 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "1/89", "msgs": 10, "est_tokens": 18685, "code": 200, "status": "extracted"} |
| 04:42 | 32 | 07:57:38.541 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "2/89", "msgs": 8, "est_tokens": 41566, "code": 200, "status": "extracted"} |
| 05:17 | 33 | 07:58:12.920 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "1/86", "msgs": 10, "est_tokens": 13126, "code": 200, "status": "extracted"} |
| 06:13 | 34 | 07:59:09.583 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "3/89", "msgs": 20, "est_tokens": 12391, "code": 200, "status": "extracted"} |
| 06:14 | 35 | 07:59:09.739 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "2/86", "msgs": 6, "est_tokens": 12170, "code": 200, "status": "extracted"} |
| 07:00 | 36 | 07:59:55.742 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "3/86", "msgs": 8, "est_tokens": 12979, "code": 200, "status": "extracted"} |
| 09:17 | 37 | 08:02:12.781 | plugin.flush.retry | {"file": "智能论恢复确认.md", "batch": 4, "attempt": 1, "code": 500, "resp": "{\"request_id\": \"c129755140424a5ca80289d19b891da9\", \"error\": {\"code\": \"INTERNAL_E |
| 10:04 | 38 | 08:03:00.381 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "4/86", "msgs": 8, "est_tokens": 12896, "code": 200, "status": "extracted"} |
| 12:17 | 39 | 08:05:12.953 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "4/89", "msgs": 20, "est_tokens": 12612, "code": 200, "status": "extracted"} |
| 12:27 | 40 | 08:05:22.842 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "5/86", "msgs": 8, "est_tokens": 13689, "code": 200, "status": "extracted"} |
| 13:05 | 41 | 08:06:01.522 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "6/86", "msgs": 6, "est_tokens": 12908, "code": 200, "status": "extracted"} |
| 14:46 | 42 | 08:07:42.588 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "7/86", "msgs": 8, "est_tokens": 13696, "code": 200, "status": "extracted"} |
| 15:02 | 43 | 08:07:57.953 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "5/89", "msgs": 16, "est_tokens": 12687, "code": 200, "status": "extracted"} |
| 15:28 | 44 | 08:08:24.546 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "8/86", "msgs": 8, "est_tokens": 12359, "code": 200, "status": "extracted"} |
| 17:00 | 45 | 08:09:55.899 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "9/86", "msgs": 8, "est_tokens": 12810, "code": 200, "status": "extracted"} |
| 18:04 | 46 | 08:10:59.821 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "10/86", "msgs": 8, "est_tokens": 13426, "code": 200, "status": "extracted"} |
| 18:26 | 47 | 08:11:21.983 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "6/89", "msgs": 20, "est_tokens": 12209, "code": 200, "status": "extracted"} |
| 20:39 | 48 | 08:13:34.846 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "11/86", "msgs": 8, "est_tokens": 13875, "code": 200, "status": "extracted"} |
| 21:15 | 49 | 08:14:10.903 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "7/89", "msgs": 34, "est_tokens": 12362, "code": 200, "status": "extracted"} |
| 24:00 | 50 | 08:16:55.883 | plugin.flush.retry | {"file": "信任与协作的传递.md", "batch": 12, "attempt": 1, "code": 500, "resp": "{\"request_id\": \"498382f0b8ce4162b79c0490899bf029\", \"error\": {\"code\": \"INTERNAL |
| 24:10 | 51 | 08:17:05.891 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "12/86", "msgs": 8, "est_tokens": 14808, "code": 200, "status": "no_extraction"} |
| 24:34 | 52 | 08:17:29.828 | plugin.flush.retry | {"file": "智能论恢复确认.md", "batch": 8, "attempt": 1, "code": 500, "resp": "{\"request_id\": \"de22906e67354598a49f353332d492c9\", \"error\": {\"code\": \"INTERNAL_E |
| 24:44 | 53 | 08:17:39.833 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "8/89", "msgs": 14, "est_tokens": 12319, "code": 200, "status": "no_extraction"} |
| 25:54 | 54 | 08:18:50.036 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "13/86", "msgs": 8, "est_tokens": 14658, "code": 200, "status": "extracted"} |
| 26:47 | 55 | 08:19:43.499 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "9/89", "msgs": 11, "est_tokens": 13142, "code": 200, "status": "extracted"} |
| 27:10 | 56 | 08:20:06.045 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "14/86", "msgs": 8, "est_tokens": 13520, "code": 200, "status": "extracted"} |
| 27:10 | 57 | 09:07:59.350 | rec.resume | {"pid": 668} |
| 27:10 | 58 | 09:07:59.523 | run.config | {"exam": "B/e2e-C v0.1", "plugin": "plugins/everos/adapter.py:EverOS", "plugin_name": "everos", "plugin_version": "1.4.1@462ebf9", "plugin_kind": "http-local",  |
| 27:19 | 59 | 09:08:08.780 | sandbox.create | {"root": "/workspace/work/pes/runs/sbx/B_everos", "env_keys": ["HOME", "LANG", "LC_ALL", "PATH", "PIP_DISABLE_PIP_VERSION_CHECK", "PYTHONNOUSERSITE", "TMPDIR",  |
| 27:19 | 60 | 09:08:08.784 | plugin.install.begin | {"plugin": "everos", "version": "1.4.1@462ebf9", "base": "/workspace/work/pes/runs/sbx/B_everos", "HOME": "/workspace/work/pes/runs/sbx/B_everos/home", "memory_ |
| 27:19 | 61 | 09:08:08.784 | plugin.install.note | {"note": "续跑：持久记忆根已有 everos.toml，跳过 init（init 无 --force 会 rc=1）", "root": "/workspace/work/pes/runs/B_everos/everos_state/root"} |
| 27:19 | 62 | 09:08:08.784 | cmd.start | {"cmd": "uv venv /workspace/work/pes/runs/sbx/B_everos/venv --python 3.12"} |
| 27:19 | 63 | 09:08:08.889 | cmd.end | {"rc": 0, "dur_s": 0.105} |
| 27:19 | 64 | 09:08:08.889 | cmd.start | {"cmd": "uv pip install everos==1.4.1"} |
| 27:35 | 65 | 09:08:24.307 | cmd.end | {"rc": 0, "dur_s": 15.417} |
| 27:35 | 66 | 09:08:24.343 | file.edit | {"path": "~/.everos/everos.toml", "section": "[llm]", "after": {"model": "cline-pass/deepseek-v4.1-flash", "api_key": "<占位，非密钥>", "base_url": "http://127.0.0.1: |
| 27:35 | 67 | 09:08:24.346 | station.proxy.start | {"pid": 794, "port": 18781, "note": "考场侧转发器，不属于插件"} |
| 27:36 | 68 | 09:08:25.846 | cmd.start | {"cmd": "ulimit -n 4096; exec everos server start --root /workspace/work/pes/runs/B_everos/everos_state/root"} |
| 28:13 | 69 | 09:09:02.887 | cmd.end | {"rc": 0, "dur_s": 37.039} |
| 28:13 | 70 | 09:09:02.889 | plugin.install.result | {"ok": true, "steps": 4, "errors": [], "dur_s": 54.105} |
| 28:22 | 71 | 09:09:11.277 | plugin.ingest.plan | {"sessions": 16, "batches": 698, "already_done": 24, "par": 4, "flush_msgs": 50, "flush_tokens": 12000} |
| 28:41 | 72 | 09:09:30.521 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "10/89", "msgs": 20, "est_tokens": 12080, "code": 200, "status": "extracted"} |
| 28:42 | 73 | 09:09:31.936 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "16/86", "msgs": 7, "est_tokens": 12055, "code": 200, "status": "extracted"} |
| 28:44 | 74 | 09:09:33.136 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "1/65", "msgs": 12, "est_tokens": 13451, "code": 200, "status": "extracted"} |
| 28:45 | 75 | 09:09:34.833 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "1/75", "msgs": 6, "est_tokens": 14804, "code": 200, "status": "extracted"} |
| 29:00 | 76 | 09:09:49.493 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "2/75", "msgs": 2, "est_tokens": 29844, "code": 200, "status": "extracted"} |
| 29:02 | 77 | 09:09:51.656 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "11/89", "msgs": 17, "est_tokens": 12067, "code": 200, "status": "extracted"} |
| 29:04 | 78 | 09:09:53.026 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "17/86", "msgs": 11, "est_tokens": 13335, "code": 200, "status": "extracted"} |
| 29:05 | 79 | 09:09:54.449 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "2/65", "msgs": 10, "est_tokens": 12853, "code": 200, "status": "extracted"} |
| 29:17 | 80 | 09:10:06.540 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "3/75", "msgs": 4, "est_tokens": 12410, "code": 200, "status": "extracted"} |
| 29:20 | 81 | 09:10:10.002 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "12/89", "msgs": 24, "est_tokens": 12812, "code": 200, "status": "extracted"} |
| 29:21 | 82 | 09:10:10.899 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "18/86", "msgs": 10, "est_tokens": 13459, "code": 200, "status": "extracted"} |
| 29:24 | 83 | 09:10:13.898 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "3/65", "msgs": 10, "est_tokens": 12313, "code": 200, "status": "extracted"} |
| 29:39 | 84 | 09:10:28.691 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "4/75", "msgs": 7, "est_tokens": 15675, "code": 200, "status": "extracted"} |
| 29:43 | 85 | 09:10:32.367 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "19/86", "msgs": 13, "est_tokens": 12484, "code": 200, "status": "extracted"} |
| 29:44 | 86 | 09:10:33.824 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "4/65", "msgs": 10, "est_tokens": 13230, "code": 200, "status": "extracted"} |
| 29:48 | 87 | 09:10:37.026 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "13/89", "msgs": 33, "est_tokens": 15069, "code": 200, "status": "extracted"} |
| 29:50 | 88 | 09:10:39.320 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "5/75", "msgs": 3, "est_tokens": 36800, "code": 200, "status": "extracted"} |
| 30:02 | 89 | 09:10:51.236 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "20/86", "msgs": 16, "est_tokens": 12959, "code": 200, "status": "extracted"} |
| 30:04 | 90 | 09:10:53.668 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "5/65", "msgs": 9, "est_tokens": 12523, "code": 200, "status": "extracted"} |
| 30:05 | 91 | 09:10:54.825 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "6/75", "msgs": 10, "est_tokens": 12216, "code": 200, "status": "extracted"} |
| 30:07 | 92 | 09:10:56.762 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "14/89", "msgs": 11, "est_tokens": 12400, "code": 200, "status": "extracted"} |
| 30:19 | 93 | 09:11:08.283 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "21/86", "msgs": 12, "est_tokens": 12968, "code": 200, "status": "extracted"} |
| 30:21 | 94 | 09:11:10.379 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "6/65", "msgs": 10, "est_tokens": 12194, "code": 200, "status": "extracted"} |
| 30:24 | 95 | 09:11:13.138 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "7/75", "msgs": 12, "est_tokens": 13050, "code": 200, "status": "extracted"} |
| 30:28 | 96 | 09:11:17.133 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "15/89", "msgs": 11, "est_tokens": 14343, "code": 200, "status": "extracted"} |
| 30:38 | 97 | 09:11:27.758 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "22/86", "msgs": 7, "est_tokens": 12661, "code": 200, "status": "extracted"} |
| 30:44 | 98 | 09:11:33.272 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "7/65", "msgs": 9, "est_tokens": 14001, "code": 200, "status": "extracted"} |
| 30:46 | 99 | 09:11:35.050 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "8/75", "msgs": 11, "est_tokens": 12526, "code": 200, "status": "extracted"} |
| 30:48 | 100 | 09:11:37.240 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "16/89", "msgs": 17, "est_tokens": 12520, "code": 200, "status": "extracted"} |
| 30:49 | 101 | 09:11:38.361 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "23/86", "msgs": 10, "est_tokens": 12853, "code": 200, "status": "extracted"} |
| 30:55 | 102 | 09:11:44.282 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "8/65", "msgs": 8, "est_tokens": 12008, "code": 200, "status": "extracted"} |
| 31:05 | 103 | 09:11:54.072 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "17/89", "msgs": 13, "est_tokens": 12701, "code": 200, "status": "extracted"} |
| 31:05 | 104 | 09:11:54.228 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "9/75", "msgs": 16, "est_tokens": 12686, "code": 200, "status": "extracted"} |
| 31:11 | 105 | 09:12:00.687 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "24/86", "msgs": 10, "est_tokens": 13377, "code": 200, "status": "extracted"} |
| 31:16 | 106 | 09:12:05.582 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "9/65", "msgs": 8, "est_tokens": 13560, "code": 200, "status": "extracted"} |
| 31:25 | 107 | 09:12:14.941 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "18/89", "msgs": 18, "est_tokens": 14067, "code": 200, "status": "extracted"} |
| 31:27 | 108 | 09:12:16.921 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "10/75", "msgs": 9, "est_tokens": 12695, "code": 200, "status": "extracted"} |
| 31:28 | 109 | 09:12:17.199 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "10/65", "msgs": 10, "est_tokens": 12624, "code": 200, "status": "extracted"} |
| 31:28 | 110 | 09:12:17.727 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "25/86", "msgs": 9, "est_tokens": 12011, "code": 200, "status": "extracted"} |
| 31:43 | 111 | 09:12:32.184 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "19/89", "msgs": 9, "est_tokens": 12832, "code": 200, "status": "extracted"} |
| 31:45 | 112 | 09:12:34.090 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "11/65", "msgs": 8, "est_tokens": 12380, "code": 200, "status": "extracted"} |
| 31:45 | 113 | 09:12:34.808 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "11/75", "msgs": 12, "est_tokens": 14987, "code": 200, "status": "extracted"} |
| 31:48 | 114 | 09:12:37.582 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "26/86", "msgs": 7, "est_tokens": 14163, "code": 200, "status": "extracted"} |
| 31:59 | 115 | 09:12:48.562 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "12/75", "msgs": 2, "est_tokens": 15047, "code": 200, "status": "extracted"} |
| 32:04 | 116 | 09:12:53.290 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "20/89", "msgs": 18, "est_tokens": 12011, "code": 200, "status": "extracted"} |
| 32:06 | 117 | 09:12:55.213 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "12/65", "msgs": 8, "est_tokens": 12705, "code": 200, "status": "extracted"} |
| 32:10 | 118 | 09:12:59.498 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "27/86", "msgs": 3, "est_tokens": 12458, "code": 200, "status": "extracted"} |
| 32:18 | 119 | 09:13:07.942 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "13/65", "msgs": 8, "est_tokens": 13427, "code": 200, "status": "extracted"} |
| 32:19 | 120 | 09:13:08.785 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "13/75", "msgs": 15, "est_tokens": 12321, "code": 200, "status": "extracted"} |
| 32:23 | 121 | 09:13:12.404 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "21/89", "msgs": 20, "est_tokens": 12310, "code": 200, "status": "extracted"} |
| 32:31 | 122 | 09:13:20.279 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "28/86", "msgs": 4, "est_tokens": 18543, "code": 200, "status": "extracted"} |
| 32:40 | 123 | 09:13:29.511 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "14/75", "msgs": 14, "est_tokens": 12262, "code": 200, "status": "extracted"} |
| 32:41 | 124 | 09:13:30.682 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "14/65", "msgs": 14, "est_tokens": 13246, "code": 200, "status": "extracted"} |
| 32:43 | 125 | 09:13:32.756 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "22/89", "msgs": 21, "est_tokens": 13166, "code": 200, "status": "extracted"} |
| 32:44 | 126 | 09:13:33.989 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "29/86", "msgs": 5, "est_tokens": 12144, "code": 200, "status": "extracted"} |
| 32:58 | 127 | 09:13:47.395 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "15/75", "msgs": 16, "est_tokens": 12371, "code": 200, "status": "extracted"} |
| 32:59 | 128 | 09:13:48.305 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "15/65", "msgs": 11, "est_tokens": 12812, "code": 200, "status": "extracted"} |
| 33:01 | 129 | 09:13:50.262 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "23/89", "msgs": 17, "est_tokens": 12336, "code": 200, "status": "extracted"} |
| 33:03 | 130 | 09:13:52.039 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "30/86", "msgs": 5, "est_tokens": 12506, "code": 200, "status": "extracted"} |
| 33:16 | 131 | 09:14:05.612 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "16/75", "msgs": 21, "est_tokens": 12328, "code": 200, "status": "extracted"} |
| 33:19 | 132 | 09:14:08.680 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "16/65", "msgs": 10, "est_tokens": 13035, "code": 200, "status": "extracted"} |
| 33:20 | 133 | 09:14:09.670 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "24/89", "msgs": 8, "est_tokens": 12004, "code": 200, "status": "extracted"} |
| 33:22 | 134 | 09:14:11.055 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "31/86", "msgs": 4, "est_tokens": 15251, "code": 200, "status": "extracted"} |
| 33:34 | 135 | 09:14:23.323 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "17/65", "msgs": 4, "est_tokens": 14149, "code": 200, "status": "extracted"} |
| 33:38 | 136 | 09:14:27.080 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "25/89", "msgs": 21, "est_tokens": 12417, "code": 200, "status": "extracted"} |
| 33:38 | 137 | 09:14:27.584 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "32/86", "msgs": 6, "est_tokens": 14516, "code": 200, "status": "extracted"} |
| 33:41 | 138 | 09:14:30.642 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "17/75", "msgs": 11, "est_tokens": 12329, "code": 200, "status": "extracted"} |
| 33:54 | 139 | 09:14:43.443 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "18/65", "msgs": 5, "est_tokens": 13356, "code": 200, "status": "extracted"} |
| 33:56 | 140 | 09:14:45.652 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "26/89", "msgs": 14, "est_tokens": 13550, "code": 200, "status": "extracted"} |
| 33:57 | 141 | 09:14:46.872 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "18/75", "msgs": 3, "est_tokens": 39276, "code": 200, "status": "extracted"} |
| 33:58 | 142 | 09:14:47.988 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "33/86", "msgs": 4, "est_tokens": 13517, "code": 200, "status": "extracted"} |
| 34:13 | 143 | 09:15:02.885 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "19/65", "msgs": 11, "est_tokens": 12613, "code": 200, "status": "extracted"} |
| 34:16 | 144 | 09:15:05.430 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "27/89", "msgs": 17, "est_tokens": 12099, "code": 200, "status": "extracted"} |
| 34:16 | 145 | 09:15:05.596 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "19/75", "msgs": 9, "est_tokens": 12252, "code": 200, "status": "extracted"} |
| 34:18 | 146 | 09:15:07.068 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "34/86", "msgs": 11, "est_tokens": 12039, "code": 200, "status": "extracted"} |
| 34:33 | 147 | 09:15:22.848 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "20/65", "msgs": 7, "est_tokens": 14146, "code": 200, "status": "extracted"} |
| 34:36 | 148 | 09:15:25.080 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "28/89", "msgs": 9, "est_tokens": 15426, "code": 200, "status": "extracted"} |
| 34:37 | 149 | 09:15:26.378 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "20/75", "msgs": 21, "est_tokens": 12125, "code": 200, "status": "extracted"} |
| 34:40 | 150 | 09:15:29.131 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "35/86", "msgs": 6, "est_tokens": 13381, "code": 200, "status": "extracted"} |
| 34:50 | 151 | 09:15:39.875 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "21/65", "msgs": 10, "est_tokens": 13638, "code": 200, "status": "extracted"} |
| 34:55 | 152 | 09:15:44.715 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "21/75", "msgs": 26, "est_tokens": 12109, "code": 200, "status": "extracted"} |
| 34:56 | 153 | 09:15:45.168 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "36/86", "msgs": 4, "est_tokens": 13101, "code": 200, "status": "extracted"} |
| 34:59 | 154 | 09:15:48.383 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "29/89", "msgs": 12, "est_tokens": 14806, "code": 200, "status": "extracted"} |
| 35:04 | 155 | 09:15:53.879 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "22/65", "msgs": 8, "est_tokens": 12577, "code": 200, "status": "extracted"} |
| 35:11 | 156 | 09:16:00.121 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "37/86", "msgs": 8, "est_tokens": 15900, "code": 200, "status": "extracted"} |
| 35:16 | 157 | 09:16:05.267 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "22/75", "msgs": 20, "est_tokens": 12108, "code": 200, "status": "extracted"} |
| 35:22 | 158 | 09:16:11.165 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "30/89", "msgs": 12, "est_tokens": 12298, "code": 200, "status": "extracted"} |
| 35:26 | 159 | 09:16:15.022 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "23/65", "msgs": 8, "est_tokens": 12889, "code": 200, "status": "extracted"} |
| 35:29 | 160 | 09:16:18.386 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "38/86", "msgs": 13, "est_tokens": 12028, "code": 200, "status": "extracted"} |
| 35:34 | 161 | 09:16:23.892 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "23/75", "msgs": 15, "est_tokens": 12474, "code": 200, "status": "extracted"} |
| 35:38 | 162 | 09:16:27.557 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "31/89", "msgs": 13, "est_tokens": 12549, "code": 200, "status": "extracted"} |
| 35:41 | 163 | 09:16:30.720 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "39/86", "msgs": 11, "est_tokens": 15269, "code": 200, "status": "extracted"} |
| 35:44 | 164 | 09:16:33.086 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "24/65", "msgs": 8, "est_tokens": 15986, "code": 200, "status": "extracted"} |
| 35:53 | 165 | 09:16:42.861 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "24/75", "msgs": 17, "est_tokens": 12469, "code": 200, "status": "extracted"} |
| 36:01 | 166 | 09:16:50.013 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "32/89", "msgs": 22, "est_tokens": 12111, "code": 200, "status": "extracted"} |
| 36:07 | 167 | 09:16:56.342 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "40/86", "msgs": 7, "est_tokens": 12346, "code": 200, "status": "extracted"} |
| 36:09 | 168 | 09:16:58.856 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "25/65", "msgs": 7, "est_tokens": 15280, "code": 200, "status": "extracted"} |
| 36:13 | 169 | 09:17:02.392 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "25/75", "msgs": 21, "est_tokens": 12360, "code": 200, "status": "extracted"} |
| 36:25 | 170 | 09:17:14.100 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "26/75", "msgs": 3, "est_tokens": 13194, "code": 200, "status": "extracted"} |
| 36:26 | 171 | 09:17:15.734 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "41/86", "msgs": 11, "est_tokens": 12518, "code": 200, "status": "extracted"} |
| 36:28 | 172 | 09:17:17.102 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "26/65", "msgs": 7, "est_tokens": 13175, "code": 200, "status": "extracted"} |
| 36:35 | 173 | 09:17:24.190 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "33/89", "msgs": 24, "est_tokens": 12021, "code": 200, "status": "extracted"} |
| 36:44 | 174 | 09:17:33.553 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "27/75", "msgs": 7, "est_tokens": 12249, "code": 200, "status": "extracted"} |
| 36:48 | 175 | 09:17:37.549 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "27/65", "msgs": 9, "est_tokens": 14470, "code": 200, "status": "extracted"} |
| 36:54 | 176 | 09:17:43.985 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "34/89", "msgs": 28, "est_tokens": 12368, "code": 200, "status": "extracted"} |
| 36:57 | 177 | 09:17:46.727 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "42/86", "msgs": 14, "est_tokens": 12160, "code": 200, "status": "extracted"} |
| 37:03 | 178 | 09:17:52.444 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "28/75", "msgs": 13, "est_tokens": 12623, "code": 200, "status": "extracted"} |
| 37:06 | 179 | 09:17:55.909 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "28/65", "msgs": 5, "est_tokens": 12942, "code": 200, "status": "extracted"} |
| 37:14 | 180 | 09:18:03.999 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "35/89", "msgs": 10, "est_tokens": 12504, "code": 200, "status": "extracted"} |
| 37:19 | 181 | 09:18:08.594 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "43/86", "msgs": 14, "est_tokens": 12787, "code": 200, "status": "extracted"} |
| 37:25 | 182 | 09:18:14.471 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "29/75", "msgs": 16, "est_tokens": 12493, "code": 200, "status": "extracted"} |
| 37:26 | 183 | 09:18:15.932 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "29/65", "msgs": 11, "est_tokens": 12767, "code": 200, "status": "extracted"} |
| 37:36 | 184 | 09:18:25.580 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "44/86", "msgs": 12, "est_tokens": 22175, "code": 200, "status": "extracted"} |
| 37:36 | 185 | 09:18:25.997 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "30/65", "msgs": 5, "est_tokens": 12805, "code": 200, "status": "extracted"} |
| 37:40 | 186 | 09:18:29.156 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "30/75", "msgs": 16, "est_tokens": 12453, "code": 200, "status": "extracted"} |
| 37:48 | 187 | 09:18:37.188 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "36/89", "msgs": 9, "est_tokens": 13415, "code": 200, "status": "extracted"} |
| 37:52 | 188 | 09:18:41.017 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "31/65", "msgs": 2, "est_tokens": 16579, "code": 200, "status": "extracted"} |
| 37:56 | 189 | 09:18:45.797 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "45/86", "msgs": 8, "est_tokens": 12576, "code": 200, "status": "extracted"} |
| 38:02 | 190 | 09:18:51.190 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "31/75", "msgs": 18, "est_tokens": 13054, "code": 200, "status": "extracted"} |
| 38:05 | 191 | 09:18:54.798 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "37/89", "msgs": 19, "est_tokens": 12407, "code": 200, "status": "extracted"} |
| 38:08 | 192 | 09:18:57.359 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "32/65", "msgs": 9, "est_tokens": 12359, "code": 200, "status": "extracted"} |
| 38:09 | 193 | 09:18:58.346 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "46/86", "msgs": 2, "est_tokens": 13420, "code": 200, "status": "extracted"} |
| 38:19 | 194 | 09:19:08.333 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "32/75", "msgs": 18, "est_tokens": 12342, "code": 200, "status": "extracted"} |
| 38:21 | 195 | 09:19:10.271 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "33/65", "msgs": 9, "est_tokens": 12208, "code": 200, "status": "extracted"} |
| 38:27 | 196 | 09:19:16.460 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "47/86", "msgs": 9, "est_tokens": 12183, "code": 200, "status": "extracted"} |
| 38:30 | 197 | 09:19:19.908 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "38/89", "msgs": 15, "est_tokens": 14062, "code": 200, "status": "extracted"} |
| 38:32 | 198 | 09:19:21.868 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "34/65", "msgs": 1, "est_tokens": 12168, "code": 200, "status": "extracted"} |
| 38:36 | 199 | 09:19:25.240 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "33/75", "msgs": 14, "est_tokens": 12332, "code": 200, "status": "extracted"} |
| 38:48 | 200 | 09:19:37.109 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "48/86", "msgs": 17, "est_tokens": 12221, "code": 200, "status": "extracted"} |
| 38:52 | 201 | 09:19:41.025 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "35/65", "msgs": 7, "est_tokens": 12804, "code": 200, "status": "extracted"} |
| 38:53 | 202 | 09:19:42.174 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "39/89", "msgs": 18, "est_tokens": 12961, "code": 200, "status": "extracted"} |
| 38:57 | 203 | 09:19:46.882 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "34/75", "msgs": 22, "est_tokens": 12197, "code": 200, "status": "extracted"} |
| 39:02 | 204 | 09:19:51.556 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "49/86", "msgs": 6, "est_tokens": 20558, "code": 200, "status": "extracted"} |
| 39:07 | 205 | 09:19:56.907 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "36/65", "msgs": 9, "est_tokens": 12175, "code": 200, "status": "extracted"} |
| 39:13 | 206 | 09:20:02.796 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "40/89", "msgs": 21, "est_tokens": 13092, "code": 200, "status": "extracted"} |
| 39:13 | 207 | 09:20:02.905 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "50/86", "msgs": 6, "est_tokens": 26935, "code": 200, "status": "extracted"} |
| 39:16 | 208 | 09:20:05.215 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "35/75", "msgs": 27, "est_tokens": 12161, "code": 200, "status": "extracted"} |
| 39:25 | 209 | 09:20:14.897 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "37/65", "msgs": 4, "est_tokens": 16642, "code": 200, "status": "extracted"} |
| 39:33 | 210 | 09:20:22.322 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "51/86", "msgs": 8, "est_tokens": 13167, "code": 200, "status": "extracted"} |
| 39:34 | 211 | 09:20:23.246 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "36/75", "msgs": 19, "est_tokens": 13196, "code": 200, "status": "extracted"} |
| 39:37 | 212 | 09:20:26.553 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "41/89", "msgs": 9, "est_tokens": 13613, "code": 200, "status": "extracted"} |
| 39:42 | 213 | 09:20:31.209 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "38/65", "msgs": 9, "est_tokens": 12195, "code": 200, "status": "extracted"} |
| 39:45 | 214 | 09:20:34.104 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "52/86", "msgs": 4, "est_tokens": 23145, "code": 200, "status": "extracted"} |
| 39:56 | 215 | 09:20:45.259 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "37/75", "msgs": 22, "est_tokens": 12092, "code": 200, "status": "extracted"} |
| 40:01 | 216 | 09:20:50.358 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "42/89", "msgs": 21, "est_tokens": 12182, "code": 200, "status": "extracted"} |
| 40:03 | 217 | 09:20:52.915 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "53/86", "msgs": 11, "est_tokens": 12214, "code": 200, "status": "extracted"} |
| 40:17 | 218 | 09:21:06.543 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "38/75", "msgs": 18, "est_tokens": 12473, "code": 200, "status": "extracted"} |
| 40:37 | 219 | 09:21:26.111 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "43/89", "msgs": 26, "est_tokens": 12742, "code": 200, "status": "extracted"} |
| 40:37 | 220 | 09:21:26.403 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "39/65", "msgs": 7, "est_tokens": 50566, "code": 200, "status": "extracted"} |
| 40:37 | 221 | 09:21:26.715 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "54/86", "msgs": 12, "est_tokens": 12570, "code": 200, "status": "extracted"} |
| 41:27 | 222 | 09:22:16.470 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "40/65", "msgs": 3, "est_tokens": 12781, "code": 200, "status": "extracted"} |
| 41:49 | 223 | 09:22:38.342 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "55/86", "msgs": 13, "est_tokens": 12116, "code": 200, "status": "extracted"} |
| 41:51 | 224 | 09:22:40.129 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "44/89", "msgs": 16, "est_tokens": 12385, "code": 200, "status": "extracted"} |
| 41:59 | 225 | 09:22:48.130 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "39/75", "msgs": 15, "est_tokens": 12140, "code": 200, "status": "extracted"} |
| 42:54 | 226 | 09:23:43.088 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "40/75", "msgs": 15, "est_tokens": 12397, "code": 200, "status": "extracted"} |
| 43:25 | 227 | 09:24:14.787 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "45/89", "msgs": 11, "est_tokens": 12191, "code": 200, "status": "extracted"} |
| 43:28 | 228 | 09:24:17.585 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "41/65", "msgs": 3, "est_tokens": 40424, "code": 200, "status": "extracted"} |
| 43:34 | 229 | 09:24:23.628 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "56/86", "msgs": 5, "est_tokens": 12915, "code": 200, "status": "extracted"} |
| 43:53 | 230 | 09:24:42.641 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "41/75", "msgs": 8, "est_tokens": 13312, "code": 200, "status": "extracted"} |
| 43:56 | 231 | 09:24:45.116 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "46/89", "msgs": 7, "est_tokens": 13384, "code": 200, "status": "extracted"} |
| 45:16 | 232 | 09:26:05.929 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "57/86", "msgs": 7, "est_tokens": 13107, "code": 200, "status": "extracted"} |
| 45:48 | 233 | 09:26:37.024 | plugin.flush | {"file": "学习能力理论讨论邀请.md", "batch": "42/65", "msgs": 7, "est_tokens": 15693, "code": 200, "status": "extracted"} |
| 45:54 | 234 | 09:26:44.004 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "42/75", "msgs": 12, "est_tokens": 12157, "code": 200, "status": "extracted"} |
| 45:56 | 235 | 09:26:45.492 | plugin.flush | {"file": "智能论恢复确认.md", "batch": "47/89", "msgs": 2, "est_tokens": 35748, "code": 200, "status": "extracted"} |
| 46:50 | 236 | 09:27:39.786 | plugin.flush | {"file": "信任与协作的传递.md", "batch": "58/86", "msgs": 16, "est_tokens": 12656, "code": 200, "status": "extracted"} |
| 46:53 | 237 | 09:27:42.355 | plugin.flush | {"file": "信任协议权重调整.md", "batch": "43/75", "msgs": 8, "est_tokens": 12277, "code": 200, "status": "extracted"} |
