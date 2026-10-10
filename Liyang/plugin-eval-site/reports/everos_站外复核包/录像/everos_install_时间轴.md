# 录像时间轴 · everos_install

源：`everos_install.jsonl`，共 50 个事件。时间轴为单调钟 mm:ss（续跑累加），墙钟见右列。

| mm:ss | #seq | 墙钟(CST) | 事件 | 摘要 |
|:--|--:|:--|:--|:--|
| 00:00 | 1 | 07:33:24.029 | rec.start | {"pid": 1219} |
| 00:00 | 2 | 07:33:24.030 | cmd.start | {"cmd": "uv venv venv --python 3.12"} |
| 00:00 | 3 | 07:33:24.268 | cmd.end | {"rc": 0, "dur_s": 0.238} |
| 00:00 | 4 | 07:33:24.268 | cmd.start | {"cmd": "uv pip install everos"} |
| 00:23 | 5 | 07:33:47.411 | cmd.end | {"rc": 0, "dur_s": 23.144} |
| 00:23 | 6 | 07:33:47.415 | rec.stop | {} |
| 00:23 | 7 | 07:33:49.487 | rec.resume | {"pid": 1366} |
| 00:23 | 8 | 07:33:49.487 | cmd.start | {"cmd": "everos --version; pip show everos 2>/dev/null \| head -3; uv pip show everos \| head -3"} |
| 00:50 | 9 | 07:34:16.433 | cmd.end | {"rc": 0, "dur_s": 26.945} |
| 00:50 | 10 | 07:34:16.433 | cmd.start | {"cmd": "everos demo --plain"} |
| 00:53 | 11 | 07:34:19.740 | cmd.end | {"rc": 0, "dur_s": 3.307} |
| 00:53 | 12 | 07:34:19.741 | cmd.start | {"cmd": "everos init"} |
| 00:56 | 13 | 07:34:22.395 | cmd.end | {"rc": 0, "dur_s": 2.654} |
| 00:56 | 14 | 07:34:22.395 | rec.stop | {} |
| 00:56 | 15 | 07:34:43.490 | rec.resume | {"pid": 1452} |
| 00:56 | 16 | 07:34:43.492 | file.edit | {"step": "S5", "path": "~/.everos/everos.toml", "note": "README 3：只改 [llm] 段。本站不用 OpenRouter：base_url 指向考场侧本地转发器（密钥只在转发器进程里，插件环境拿不到），model 写成站方唯一允许的模型", "before |
| 00:56 | 17 | 07:34:43.492 | cmd.start | {"cmd": "ulimit -n 4096; (setsid nohup everos server start > /workspace/work/pes/runs/everos/install_sbx/server.log 2>&1 < /dev/null &); for i in $(seq 1 90); do sleep 1; curl -s -m 2 http://127.0.0.1:8000/health && break; done; echo; tail -5 /workspace/work/pes/runs/everos/install_sbx/server.log"} |
| 02:26 | 18 | 07:36:14.111 | cmd.end | {"rc": 0, "dur_s": 90.619} |
| 02:26 | 19 | 07:36:14.112 | rec.stop | {} |
| 02:26 | 20 | 07:36:19.791 | rec.resume | {"pid": 1681} |
| 02:26 | 21 | 07:36:19.792 | file.edit | {"step": "S5", "path": "~/.everos/everos.toml", "note": "README 3：只改 [llm] 段。本站不用 OpenRouter：base_url 指向考场侧本地转发器（密钥只在转发器进程里，插件环境拿不到），model 写成站方唯一允许的模型", "before |
| 02:26 | 22 | 07:36:19.792 | cmd.start | {"cmd": "ulimit -n 4096; (setsid nohup everos server start > /workspace/work/pes/runs/everos/install_sbx/server.log 2>&1 < /dev/null &); for i in $(seq 1 90); do sleep 1; curl -s -m 2 http://127.0.0.1:8000/health && break; done; echo; tail -5 /workspace/work/pes/runs/everos/install_sbx/server.log"} |
| 03:57 | 23 | 07:37:50.417 | cmd.end | {"rc": 0, "dur_s": 90.625} |
| 03:57 | 24 | 07:37:50.418 | rec.stop | {} |
| 03:57 | 25 | 07:37:54.139 | rec.resume | {"pid": 1910} |
| 03:57 | 26 | 07:37:54.144 | file.edit | {"step": "S5", "path": "~/.everos/everos.toml", "note": "README 3：只改 [llm] 段。本站不用 OpenRouter：base_url 指向考场侧本地转发器（密钥只在转发器进程里，插件环境拿不到），model 写成站方唯一允许的模型", "before |
| 03:57 | 27 | 07:37:54.144 | cmd.start | {"cmd": "ulimit -n 4096; (setsid nohup everos server start > /workspace/work/pes/runs/everos/install_sbx/server.log 2>&1 < /dev/null &); for i in $(seq 1 90); do sleep 1; curl -s -m 2 http://127.0.0.1:8000/health && break; done; echo; tail -5 /workspace/work/pes/runs/everos/install_sbx/server.log"} |
| 04:05 | 28 | 07:38:02.312 | cmd.end | {"rc": 0, "dur_s": 8.168} |
| 04:05 | 29 | 07:38:02.312 | rec.stop | {} |
| 04:05 | 30 | 07:38:05.505 | rec.resume | {"pid": 1970} |
| 04:05 | 31 | 07:38:05.510 | cmd.start | {"cmd": "curl -s -X POST http://127.0.0.1:8000/api/v2/memory/add -H 'Content-Type: application/json' -d @/workspace/work/pes/runs/everos/install_sbx/add.json"} |
| 04:15 | 32 | 07:38:15.615 | cmd.end | {"rc": 0, "dur_s": 10.104} |
| 04:15 | 33 | 07:38:15.615 | cmd.start | {"cmd": "curl -s -X POST http://127.0.0.1:8000/api/v2/memory/flush -H 'Content-Type: application/json' -d '{\"session_id\":\"demo-001\",\"app_id\":\"default\",\"project_id\":\"default\"}'"} |
| 04:18 | 34 | 07:38:18.500 | cmd.end | {"rc": 0, "dur_s": 2.885} |
| 04:18 | 35 | 07:38:18.500 | cmd.start | {"cmd": "sleep 5; curl -s -X POST http://127.0.0.1:8000/api/v2/memory/search -H 'Content-Type: application/json' -d '{\"user_id\":\"alice\",\"app_id\":\"default\",\"project_id\":\"default\",\"query\":\"Where do I like to climb?\",\"method\":\"keyword\",\"top_k\":5}'"} |
| 04:23 | 36 | 07:38:23.541 | cmd.end | {"rc": 0, "dur_s": 5.04} |
| 04:23 | 37 | 07:38:23.541 | cmd.start | {"cmd": "find /workspace/work/pes/runs/everos/install_sbx/home/.everos -name '*.md' \| sed 's#/workspace/work/pes/runs/everos/install_sbx/home#~#' ; cat /workspace/work/pes/runs/everos/install_sbx/home/.everos/default_app/default_project/users/alice/episodes/*.md 2>/dev/null \| head -60"} |
| 04:23 | 38 | 07:38:23.576 | cmd.end | {"rc": 0, "dur_s": 0.035} |
| 04:23 | 39 | 07:38:23.576 | rec.stop | {} |
| 04:23 | 40 | 07:48:49.511 | rec.resume | {"pid": 3345} |
| 04:23 | 41 | 07:48:49.511 | note | {"step": "U0", "note": "卸载：README/QUICKSTART/docs 均无卸载章节；CLI 无 `server stop`（只有 start），服务需 Ctrl+C/kill。本录像的服务进程已在 07:43 被考场 pkill 停掉（未单独录像，如实记）"} |
| 04:23 | 42 | 07:48:49.511 | cmd.start | {"cmd": "curl -s -m 3 http://127.0.0.1:8000/health \|\| echo 'no server on :8000'; everos server --help \| tail -4"} |
| 04:26 | 43 | 07:48:52.224 | cmd.end | {"rc": 0, "dur_s": 2.713} |
| 04:26 | 44 | 07:48:52.225 | cmd.start | {"cmd": "uv pip uninstall everos"} |
| 04:26 | 45 | 07:48:52.682 | cmd.end | {"rc": 0, "dur_s": 0.458} |
| 04:26 | 46 | 07:48:52.683 | cmd.start | {"cmd": "du -sh home/.everos home/.cache 2>/dev/null; find home/.everos -type f \| sed 's#^#  #' \| head -80; find home/.everos -type f \| wc -l"} |
| 04:27 | 47 | 07:48:53.522 | cmd.end | {"rc": 0, "dur_s": 0.839} |
| 04:27 | 48 | 07:48:53.522 | cmd.start | {"cmd": "ls -la /tmp \| head -40; ls -la ${REALHOME:-/home/sandbox}/.everos 2>&1 \| head -3"} |
| 04:27 | 49 | 07:48:53.529 | cmd.end | {"rc": 0, "dur_s": 0.006} |
| 04:27 | 50 | 07:48:53.529 | rec.stop | {} |
