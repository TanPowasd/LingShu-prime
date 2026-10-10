# -*- coding: utf-8 -*-
"""宿主仿真的 Python 侧：准备 node 运行目录、启动 host_emu.mjs、桥接插件固化调用到 Cline。

emu 目录（plugins/dsh-auto-memory/_sbx/emu/）：
  node_modules/@deepseek-ai -> DSH 0.2.0-rc.2 全局安装里的 @deepseek-ai（真实宿主依赖）
  node_modules/yaml         -> 同上（插件运行时依赖 yaml ^2.4.2；宿主带 2.9.1）
  node_modules/dsh-auto-memory/  ← npm tarball 解包（lib/index.js sha256 校验 = tarball）
  host_emu.mjs               ← 本目录 host_emu.mjs 的拷贝（每次启动前按哈希同步）
"""
from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from harness import llm  # noqa: E402

HOSTNM = HERE / "_sbx/install/npm-global/lib/node_modules/@deepseek-ai/dsh/node_modules"
PKG = HERE / "_pkg/package"
EMU = HERE / "_sbx/emu"
TARBALL_LIB_SHA256 = "bd7d79ea1ca6e5c4018aa95ab993312ea7aaa65bd74df477673df8d648d81858"
CONSOLIDATION_TEMPERATURE = 0.7   # 插件请求不带 temperature（走宿主/供应商缺省）；本站固定 0.7 并登记


def sha256f(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def prepare() -> dict:
    nm = EMU / "node_modules"; nm.mkdir(parents=True, exist_ok=True)
    for name in ("@deepseek-ai", "yaml"):
        link = nm / name
        if not link.exists():
            os.symlink(HOSTNM / name, link)
    dst = nm / "dsh-auto-memory"
    if not dst.exists():
        shutil.copytree(PKG, dst)
    got = sha256f(dst / "lib/index.js")
    assert got == TARBALL_LIB_SHA256, f"插件 lib/index.js 哈希不符：{got}"
    shutil.copy2(HERE / "host_emu.mjs", EMU / "host_emu.mjs")
    return {"plugin_lib_sha256": got, "host_emu_sha256": sha256f(EMU / "host_emu.mjs"),
            "host_dsh_version": json.loads((HOSTNM / "@deepseek-ai/../../package.json").read_text())["version"]
            if (HOSTNM / "../package.json").exists() else None}


def run_job(job: dict, *, rec=None, client: llm.Client | None = None, tag: str = "", timeout=1800) -> dict:
    """运行一个仿真作业。bridge 请求经 client（harness llm.Client，匀速闸）发出；返回 @@DONE 结果 + 调用记录。"""
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(EMU / "home"), "LANG": "C.UTF-8",
           "DSH_HOME": str(EMU / "home/.dsh")}
    assert "CLINE_API_KEY" not in env
    p = subprocess.Popen(["node", "host_emu.mjs"], cwd=EMU, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, bufsize=1)
    p.stdin.write(json.dumps(job, ensure_ascii=False) + "\n"); p.stdin.flush()
    calls, events, done, logs = [], [], None, []
    t0 = time.monotonic()
    for line in p.stdout:
        if line.startswith("@@REQ "):
            req = json.loads(line[6:])
            msgs = [{"role": "user", "content": req["prompt"]}]
            try:
                r = client.chat(msgs, rec, tag=f"consolidate|{tag}|{req['session']}")
                calls.append({"session": req["session"], "ok": True, "usage": r["usage"], "cost_usd": r["cost_usd"],
                              "finish_reason": r["finish_reason"], "text": r["content"],
                              "prompt_sha256": hashlib.sha256(req["prompt"].encode()).hexdigest(), "prompt_chars": len(req["prompt"]),
                              "maxTokens": req["maxTokens"]})
                p.stdin.write("@@RESP " + json.dumps({"text": r["content"]}, ensure_ascii=False) + "\n")
            except llm.LLMError as e:
                calls.append({"session": req["session"], "ok": False, "error": str(e)[:300]})
                p.stdin.write("@@RESP " + json.dumps({"error": str(e)[:300]}) + "\n")
            p.stdin.flush()
        elif line.startswith("@@EVT "):
            events.append(json.loads(line[6:]))
        elif line.startswith("@@DONE "):
            done = json.loads(line[7:])
        else:
            logs.append(line.rstrip()[:500])
        if time.monotonic() - t0 > timeout:
            p.kill(); break
    p.wait(timeout=30)
    err = p.stderr.read()[-4000:]
    return {"done": done, "calls": calls, "events": events, "logs": logs[-50:], "stderr": err, "rc": p.returncode}


def consolidation_client() -> llm.Client:
    return llm.Client("plugin-consolidate", temperature=CONSOLIDATION_TEMPERATURE, max_tokens=2048)
