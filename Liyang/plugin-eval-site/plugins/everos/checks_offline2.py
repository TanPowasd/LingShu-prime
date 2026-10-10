# -*- coding: utf-8 -*-
"""C5：离线模拟服务（C4 起的 :18850）上做一次最小 add(defer)+flush，看首次分词（tiktoken 拉编码表）在断网时的表现。"""
import json, os, sys, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from harness.recorder import Recorder, render_timeline  # noqa
out = os.path.join(ROOT, "runs/everos_checks")
rec = Recorder(f"{out}/recording.jsonl", "everos_checks", resume=True)
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
import subprocess
B = os.path.join(ROOT, "runs/everos/offline_sbx"); root = os.path.join(B, "root"); venv = os.path.join(ROOT, "runs/sbx/B_everos/venv")
env = {"HOME": B + "/home", "PATH": f"{venv}/bin:/usr/bin:/bin", "TMPDIR": B + "/tmp", "LANG": "C.UTF-8", "NO_COLOR": "1",
       "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
       "http_proxy": "http://127.0.0.1:9", "NO_PROXY": "127.0.0.1,localhost", "EVEROS_API__PORT": "18850", "EVEROS_ROOT": root,
       "EVEROS_LLM__API_KEY": "x", "EVEROS_LLM__BASE_URL": "http://127.0.0.1:18781/v1", "EVEROS_LLM__MODEL": "cline-pass/deepseek-v4.1-flash"}
srv = subprocess.Popen(f"exec everos server start --root {root}", shell=True, env=env, stdout=open(B + "/server.log", "a"),
                       stderr=subprocess.STDOUT, start_new_session=True)
rec.event("cmd.start", step="C5-server", cmd="(离线模拟，同 C4 环境) everos server start --root <C4 的根>")
for _ in range(50):
    time.sleep(2)
    try:
        with op.open("http://127.0.0.1:18850/health", timeout=3):
            break
    except Exception:
        pass
def post(path, body):
    req = urllib.request.Request("http://127.0.0.1:18850" + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        with op.open(req, timeout=110) as r:
            return r.status, r.read().decode()[:1500], round(time.monotonic() - t0, 1)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:1500], round(time.monotonic() - t0, 1)
    except Exception as e:
        return -1, repr(e)[:500], round(time.monotonic() - t0, 1)
ts = 1767225600000
for step, path, body in (("C5a", "/api/v2/memory/add", {"session_id": "off-1", "app_id": "dsh", "project_id": "p", "defer_extraction": True,
                          "messages": [{"sender_id": "u1", "role": "user", "timestamp": ts, "content": "我喜欢每年春天去黄山。"},
                                       {"sender_id": "dsh", "role": "assistant", "timestamp": ts + 60000, "content": "黄山哪条线路？"}]}),
                         ("C5b", "/api/v2/memory/flush", {"session_id": "off-1", "app_id": "dsh", "project_id": "p"})):
    rec.event("cmd.start", step=step, cmd=f"POST {path}（离线模拟服务）", body=body)
    code, txt, dt = post(path, body)
    e = rec.event("cmd.end", step=step, rc=code, stdout=txt, dur_s=dt,
                  tiktoken_cache=os.listdir(os.path.join(ROOT, "runs/everos/offline_sbx/tmp/data-gym-cache")) if os.path.isdir(os.path.join(ROOT, "runs/everos/offline_sbx/tmp/data-gym-cache")) else [])
    print(step, e["seq"], code, dt, txt[:600])
log = open(os.path.join(ROOT, "runs/everos/offline_sbx/server.log"), errors="replace").read()
import re
hits = [l[:400] for l in log.splitlines() if re.search(r"tiktoken|data-gym|ProxyError|Max retries|openaipublic|Traceback|error", l, re.I)]
e = rec.event("check.offline_server_log", hits=hits[-30:])
print("log", e["seq"], "\n".join(hits[-12:]))
os.killpg(srv.pid, 15)
rec.close(); render_timeline(f"{out}/recording.jsonl", f"{out}/timeline.md")
