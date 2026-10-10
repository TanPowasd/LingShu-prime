# -*- coding: utf-8 -*-
"""核对 EverOS 启动时的外联（tiktoken 编码表下载）与离线行为。录像续写 runs/everos_checks。
C3：各沙箱 TMPDIR/data-gym-cache 下的文件 = sha1(o200k_base.tiktoken 的 URL)，mtime = 服务启动时刻。
C4：模拟离线（HTTPS_PROXY/HTTP_PROXY 指向不可达端口 + 全新 TMPDIR + 全新记忆根），起服务看能否就绪。"""
import hashlib, json, os, shutil, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from harness.recorder import Recorder, render_timeline  # noqa
out = os.path.join(ROOT, "runs/everos_checks")
rec = Recorder(f"{out}/recording.jsonl", "everos_checks", resume=True)
URL = "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken"
rows = []
for d in ("runs/everos/install_sbx", "runs/everos/probe_sbx", "runs/sbx/B_everos_smoke", "runs/sbx/B_everos"):
    p = os.path.join(ROOT, d, "tmp/data-gym-cache")
    for f in (os.listdir(p) if os.path.isdir(p) else []):
        st = os.stat(os.path.join(p, f))
        rows.append({"sandbox": d, "file": f, "bytes": st.st_size,
                     "mtime_cst": time.strftime("%H:%M:%S", time.gmtime(st.st_mtime + 8 * 3600))})
e = rec.event("check.tiktoken_cache", url=URL, sha1_of_url=hashlib.sha1(URL.encode()).hexdigest(), files=rows,
              note="tiktoken 把下载的编码表按 sha1(URL) 存进 $TMPDIR/data-gym-cache；mtime 与各沙箱服务启动时刻一致")
print("C3", e["seq"], json.dumps(rows, ensure_ascii=False))
# C4 离线模拟
B = os.path.join(ROOT, "runs/everos/offline_sbx")
shutil.rmtree(B, ignore_errors=True)
os.makedirs(B + "/tmp"); os.makedirs(B + "/home")
venv = os.path.join(ROOT, "runs/sbx/B_everos/venv")
root = os.path.join(B, "root")
env = {"HOME": B + "/home", "PATH": f"{venv}/bin:/usr/bin:/bin", "TMPDIR": B + "/tmp", "LANG": "C.UTF-8", "NO_COLOR": "1",
       "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
       "http_proxy": "http://127.0.0.1:9", "NO_PROXY": "127.0.0.1,localhost", "EVEROS_API__PORT": "18850", "EVEROS_ROOT": root,
       "EVEROS_LLM__API_KEY": "x", "EVEROS_LLM__BASE_URL": "http://127.0.0.1:18781/v1", "EVEROS_LLM__MODEL": "cline-pass/deepseek-v4.1-flash"}
subprocess.run(f"everos init --root {root}", shell=True, env=env, capture_output=True)
rec.event("cmd.start", step="C4", cmd="(离线模拟) everos server start --root <新根>", note="HTTP(S)_PROXY→127.0.0.1:9 使外网不可达；全新 TMPDIR（无 tiktoken 缓存）")
t0 = time.monotonic()
logf = open(B + "/server.log", "w")
p = subprocess.Popen(f"exec everos server start --root {root}", shell=True, env=env, stdout=logf, stderr=logf, start_new_session=True)
ready, health = False, None
import urllib.request
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
while time.monotonic() - t0 < 100:
    time.sleep(2)
    try:
        with op.open("http://127.0.0.1:18850/health", timeout=3) as r:
            health = json.loads(r.read()); ready = True; break
    except Exception:
        pass
    if p.poll() is not None:
        break
log = open(B + "/server.log", errors="replace").read()
e = rec.event("cmd.end", step="C4", rc=p.poll(), ready=ready, health=health, dur_s=round(time.monotonic() - t0, 1),
              stderr=log[-5000:], tiktoken_cache=os.listdir(B + "/tmp/data-gym-cache") if os.path.isdir(B + "/tmp/data-gym-cache") else [])
print("C4", e["seq"], ready, round(time.monotonic() - t0, 1), log[-1500:])
try:
    os.killpg(p.pid, 15)
except Exception:
    pass
rec.close(); render_timeline(f"{out}/recording.jsonl", f"{out}/timeline.md")
