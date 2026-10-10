# 录像时间轴 · everos_checks

源：`everos_checks.jsonl`，共 43 个事件。时间轴为单调钟 mm:ss（续跑累加），墙钟见右列。

| mm:ss | #seq | 墙钟(CST) | 事件 | 摘要 |
|:--|--:|:--|:--|:--|
| 00:00 | 1 | 08:02:46.485 | rec.start | {"pid": 5634} |
| 00:00 | 2 | 08:02:46.485 | cmd.start | {"cmd": "curl -s -w '\\nHTTP %{http_code}\\n' -X POST http://127.0.0.1:18780/api/v2/memory/search -H 'Content-Type: application/json' -d '{\"user_id\":\"pes-user\",\"app_id\":\"dsh\",\"project_id\":\"pes-examb\",\"query\":\"信任协议\",\"top_k\":5}'"} |
| 00:00 | 3 | 08:02:46.505 | cmd.end | {"rc": 0, "dur_s": 0.02} |
| 00:00 | 4 | 08:02:46.506 | cmd.start | {"cmd": "curl -s http://127.0.0.1:18780/health"} |
| 00:00 | 5 | 08:02:46.529 | cmd.end | {"rc": 0, "dur_s": 0.023} |
| 00:00 | 6 | 08:02:46.529 | rec.stop | {} |
| 00:00 | 7 | 08:09:22.647 | rec.resume | {"pid": 6650} |
| 00:00 | 8 | 08:09:22.649 | check.tiktoken_cache | {"url": "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken", "sha1_of_url": "fb374d419588a4632f3f557e76b4b70aebbca790", "files": [{"sandb |
| 00:57 | 9 | 08:10:20.292 | cmd.start | {"cmd": "(离线模拟) everos server start --root <新根>"} |
| 01:13 | 10 | 08:10:36.357 | cmd.end | {"rc": null, "dur_s": 16.1} |
| 01:13 | 11 | 08:10:36.357 | rec.stop | {} |
| 01:13 | 12 | 08:10:59.335 | rec.resume | {"pid": 6806} |
| 01:13 | 13 | 08:10:59.342 | cmd.start | {"cmd": "POST /api/v2/memory/add（离线模拟服务）"} |
| 01:13 | 14 | 08:10:59.344 | cmd.end | {"rc": -1, "dur_s": 0.0} |
| 01:13 | 15 | 08:10:59.344 | cmd.start | {"cmd": "POST /api/v2/memory/flush（离线模拟服务）"} |
| 01:13 | 16 | 08:10:59.344 | cmd.end | {"rc": -1, "dur_s": 0.0} |
| 01:13 | 17 | 08:10:59.346 | check.offline_server_log | {"hits": []} |
| 01:13 | 18 | 08:10:59.346 | rec.stop | {} |
| 01:13 | 19 | 08:11:06.778 | rec.resume | {"pid": 6818} |
| 01:13 | 20 | 08:11:06.793 | cmd.start | {"cmd": "(离线模拟，同 C4 环境) everos server start --root <C4 的根>"} |
| 01:19 | 21 | 08:11:12.812 | cmd.start | {"cmd": "POST /api/v2/memory/add（离线模拟服务）"} |
| 01:19 | 22 | 08:11:12.914 | cmd.end | {"rc": 200, "dur_s": 0.1} |
| 01:19 | 23 | 08:11:12.914 | cmd.start | {"cmd": "POST /api/v2/memory/flush（离线模拟服务）"} |
| 01:21 | 24 | 08:11:14.527 | cmd.end | {"rc": 500, "dur_s": 1.6} |
| 01:21 | 25 | 08:11:14.531 | check.offline_server_log | {"hits": ["\u001b[2m2026-10-10T00:11:13.895024Z\u001b[0m [\u001b[31m\u001b[1merror    \u001b[0m] \u001b[1munhandled_exception           \u001b[0m \u001b[36mexce |
| 01:21 | 26 | 08:11:14.531 | rec.stop | {} |
| 01:21 | 27 | 08:11:57.096 | rec.resume | {"pid": 6925} |
| 01:21 | 28 | 08:11:57.329 | check.profile_share | {"qid": "C-001", "profile_chars": [16171], "episode_chars": [1193, 1455, 1682, 2030, 1323], "episodes_summary_equals_episode": "0/5", "dsh_budget": 12000, "dsh_ |
| 01:21 | 29 | 08:11:57.329 | rec.stop | {} |
| 01:21 | 30 | 08:12:16.057 | rec.resume | {"pid": 7034} |
| 01:21 | 31 | 08:12:16.067 | check.full_snapshot | {"batches_done": 16, "batches_total": 698, "sessions_started": 2, "progress": {"智能论恢复确认.md": 6, "信任与协作的传递.md": 10}, "flush_events": 16, "flush_failed": 0} |
| 01:21 | 32 | 08:12:16.067 | rec.stop | {} |
| 01:21 | 33 | 08:19:58.195 | rec.resume | {"pid": 7619} |
| 01:21 | 34 | 08:19:58.360 | check.full_snapshot | {"batches_done": 22, "batches_total": 698, "sessions_started": 2, "progress": {"智能论恢复确认.md": 9, "信任与协作的传递.md": 13}, "flush_events": 22, "flush_failed": 0} |
| 01:21 | 35 | 08:19:58.360 | rec.stop | {} |
| 01:21 | 36 | 09:30:37.470 | rec.resume | {"pid": 2736} |
| 01:21 | 37 | 09:30:37.474 | check.profile_prompt_growth | {"n_calls_total": 692, "n_big": 28, "big_cost_usd": 0.9455, "total_cost_usd": 1.7441, "big_finish_length": 18, "max_prompt_tokens_accepted": 1045377} |
| 01:21 | 38 | 09:30:37.476 | check.user_profile_frozen | {"path": "runs/B_everos/everos_state/root/dsh/pes-examb/users/pes-user/user.md", "bytes": 35722, "mtime_cst": "08:00:10", "profile_timestamp_ms": 1767312900000, |
| 01:21 | 39 | 09:30:37.506 | check.profile_strategy_retries | {"retry_total": 59, "retry_profile": 29, "retry_profile_first": "01:19", "retry_profile_last": "01:29", "retry_other_first": "01:25", "non_stop_finish": 13} |
| 01:21 | 40 | 09:30:37.508 | check.profile_source_facts | {"file": "everos/memory/strategies/extract_user_profile.py (everos==1.4.1)", "sha256_16": "8c70f98997df331e", "lines": {"74": "PROFILE_EXTRACTION_INTERVAL = 1", |
| 01:21 | 41 | 09:30:37.510 | check.throughput_and_stop | {"per_minute": {"9:09": 8, "9:10": 13, "9:11": 12, "9:12": 14, "9:13": 12, "9:14": 12, "9:15": 13, "9:16": 13, "9:17": 11, "9:18": 14, "9:19": 12, "9:20": 12, " |
| 01:21 | 42 | 09:30:46.958 | rec.resume | {"pid": 2739} |
| 01:21 | 43 | 09:30:46.958 | check.note | {"ref_seq": 39, "note": "#39 的 retry_*_first/last 取自服务日志 ISO 时间戳，为 UTC：01:19＝09:19 CST，01:25＝09:25 CST，01:29＝09:29 CST（停机前最后一次）。#38 profile_timestamp_ms 1767312 |
