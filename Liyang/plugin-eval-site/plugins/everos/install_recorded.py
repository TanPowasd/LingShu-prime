# -*- coding: utf-8 -*-
"""EverOS 隔离安装（照官方 README / QUICKSTART 走一遍，全程录像）。

隔离：BASE（默认 runs/everos/install_sbx，持久盘；沙箱夜里会重启、/tmp 会清空）
  BASE/home  临时 HOME（EverOS 缺省记忆根 ~/.everos 就落这里；uv 缓存也在这）
  BASE/venv  独立 venv
录像：runs/everos_install/recording.jsonl（run id = everos_install）+ timeline.md
步骤号 S1..：一个普通用户照 README 要亲手做的操作。
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from harness.recorder import Recorder, render_timeline  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--base", default=os.path.join(ROOT, "runs/everos/install_sbx"))
ap.add_argument("--out", default=os.path.join(ROOT, "runs/everos_install"))
ap.add_argument("--steps", default="all")
ap.add_argument("--resume", action="store_true")
a = ap.parse_args()
B = a.base
HOME, VENV = f"{B}/home", f"{B}/venv"
if not a.resume and os.path.exists(B):
    shutil.rmtree(B)
os.makedirs(HOME, exist_ok=True)
rec = Recorder(f"{a.out}/recording.jsonl", "everos_install", resume=a.resume)
ENV = {"HOME": HOME, "PATH": f"{VENV}/bin:/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
       "TMPDIR": f"{B}/tmp", "XDG_CACHE_HOME": f"{HOME}/.cache", "UV_CACHE_DIR": f"{HOME}/.cache/uv",
       "VIRTUAL_ENV": VENV, "PYTHONNOUSERSITE": "1", "TERM": "dumb", "NO_COLOR": "1"}
os.makedirs(ENV["TMPDIR"], exist_ok=True)


def run(step, cmd, timeout=110, note=None, cwd=None):
    rec.event("cmd.start", step=step, cmd=cmd, note=note, cwd=cwd or B)
    t0 = time.monotonic()
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd or B, env=ENV, capture_output=True, text=True, timeout=timeout)
        rc, so, se = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, so, se = "timeout", (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), "TIMEOUT"
    ev = rec.event("cmd.end", step=step, rc=rc, stdout=so[-12000:], stderr=se[-12000:], dur_s=round(time.monotonic() - t0, 3))
    print(f"[{step}] rc={rc} {ev['dur_s']}s #{ev['seq']}\n--- out\n{so[-2500:]}\n--- err\n{se[-2500:]}")
    return ev


steps = a.steps.split(",")
want = lambda s: a.steps == "all" or s in steps
if want("S1"):
    run("S1", "uv venv venv --python 3.12", note="README 前置：Python 3.12+；给 everos 一个独立 venv")
if want("S2"):
    run("S2", "uv pip install everos", note="README Quick Start 1. Install（PyPI）")
if want("S2v"):
    run("S2v", "everos --version; pip show everos 2>/dev/null | head -3; uv pip show everos | head -3", note="确认装上的版本")
if want("S3"):
    run("S3", "everos demo --plain", note="README 2. standalone demo（无需密钥）")
if want("S4"):
    run("S4", "everos init", note="README 3. Initialize：生成 ~/.everos/everos.toml、ome.toml")
if want("S5"):
    cfg = f"{HOME}/.everos/everos.toml"
    t = open(cfg).read()
    lines, sec, out = t.split("\n"), None, []
    for ln in lines:
        st = ln.strip()
        if st.startswith("[") and st.endswith("]"):
            sec = st
        if sec == "[llm]" and st.startswith("model") and "=" in st:
            ln = 'model = "cline-pass/deepseek-v4.1-flash"'
        elif sec == "[llm]" and st.startswith("api_key") and "=" in st:
            ln = 'api_key = "pes-local-proxy-no-secret"'
        elif sec == "[llm]" and st.startswith("base_url") and "=" in st:
            ln = 'base_url = "http://127.0.0.1:18611/v1"'
        out.append(ln)
    new = "\n".join(out)
    open(cfg, "w").write(new)
    rec.event("file.edit", step="S5", path="~/.everos/everos.toml", note="README 3：只改 [llm] 段。本站不用 OpenRouter：base_url 指向考场侧本地转发器（密钥只在转发器进程里，插件环境拿不到），model 写成站方唯一允许的模型",
              before='[llm]\nmodel = "openai/gpt-4.1-mini"\napi_key = ""\nbase_url = "https://openrouter.ai/api/v1"',
              after='[llm]\nmodel = "cline-pass/deepseek-v4.1-flash"\napi_key = "pes-local-proxy-no-secret"\nbase_url = "http://127.0.0.1:18611/v1"', changed=new != t)
    print("S5 changed", new != t)
if want("S6"):
    run("S6", f"ulimit -n 4096; (setsid nohup everos server start > {B}/server.log 2>&1 < /dev/null &); for i in $(seq 1 90); do sleep 1; curl -s -m 2 http://127.0.0.1:8000/health && break; done; echo; tail -5 {B}/server.log",
        note="README 4. Start EverOS（前台常驻；这里后台起）+ curl /health；QUICKSTART 建议 ulimit -n 4096")
if want("S7"):
    TS = int(time.time() * 1000)
    body = {"session_id": "demo-001", "app_id": "default", "project_id": "default", "messages": [
        {"sender_id": "alice", "role": "user", "timestamp": TS, "content": "I love climbing in Yosemite every spring."},
        {"sender_id": "alice", "role": "user", "timestamp": TS + 10000, "content": "My favorite coffee shop is Blue Bottle in SOMA."}]}
    open(f"{B}/add.json", "w").write(json.dumps(body))
    run("S7a", f"curl -s -X POST http://127.0.0.1:8000/api/v2/memory/add -H 'Content-Type: application/json' -d @{B}/add.json", note="README 5. add")
    run("S7b", """curl -s -X POST http://127.0.0.1:8000/api/v2/memory/flush -H 'Content-Type: application/json' -d '{"session_id":"demo-001","app_id":"default","project_id":"default"}'""", note="README 5. flush（一次抽取 LLM 调用）")
    run("S7c", """sleep 5; curl -s -X POST http://127.0.0.1:8000/api/v2/memory/search -H 'Content-Type: application/json' -d '{"user_id":"alice","app_id":"default","project_id":"default","query":"Where do I like to climb?","method":"keyword","top_k":5}'""", note="README 5. search keyword")
    run("S7d", f"find {HOME}/.everos -name '*.md' | sed 's#{HOME}#~#' ; cat {HOME}/.everos/default_app/default_project/users/alice/episodes/*.md 2>/dev/null | head -60", note="README TIP：去 ~/.everos 看生成的 Markdown")
if want("U"):
    rec.event("note", step="U0", note="卸载：README/QUICKSTART/docs 均无卸载章节；CLI 无 `server stop`（只有 start），服务需 Ctrl+C/kill。本录像的服务进程已在 07:43 被考场 pkill 停掉（未单独录像，如实记）")
    run("U0", "curl -s -m 3 http://127.0.0.1:8000/health || echo 'no server on :8000'; everos server --help | tail -4", note="确认服务已停；看 CLI 有无 stop")
    run("U1", "uv pip uninstall everos", note="按 pip 常识卸载包本体")
    run("U2", "du -sh home/.everos home/.cache 2>/dev/null; find home/.everos -type f | sed 's#^#  #' | head -80; find home/.everos -type f | wc -l", note="残留：记忆根 ~/.everos（配置+Markdown+SQLite+LanceDB）与 uv 缓存")
    run("U3", "ls -la /tmp | head -40; ls -la ${REALHOME:-/home/sandbox}/.everos 2>&1 | head -3", note="沙箱外粗看：/tmp 新条目、真实 HOME 是否被写 ~/.everos")
rec.close()
render_timeline(f"{a.out}/recording.jsonl", f"{a.out}/timeline.md")
