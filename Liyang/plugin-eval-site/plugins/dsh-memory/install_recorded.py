# -*- coding: utf-8 -*-
"""dsh-memory 隔离安装（全程录像）。

隔离：BASE=/tmp/pes-dshm（可用 --base 改）
  BASE/home   临时 HOME（令牌库 ~/.mdcg、npm 缓存等都落这里）
  BASE/root   MDCG_ROOT（记忆真源）
  BASE/venv   独立 venv（插件声明零 pip 依赖，venv 只用来隔离解释器）
  BASE/work   工作目录（git clone 在这里）
产物：
  <out>/install.jsonl / install_时间轴.md     录像
  <out>/snap_before.json / snap_after_install.json  快照
  BASE/secrets/*.token                          令牌明文（0600，不进录像不进仓）
用法：python3 install_recorded.py --sha <commit> --out <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rec_local import Rec, render_md  # noqa: E402

REPO = "https://github.com/FuRongJun-1999/dsh-memory.git"


def snapshot(*roots):
    out = {}
    for r in roots:
        for dp, dn, fn in os.walk(r):
            for n in fn:
                p = os.path.join(dp, n)
                try:
                    st = os.lstat(p)
                    h = ""
                    if st.st_size < 2_000_000 and os.path.isfile(p):
                        with open(p, "rb") as f:
                            h = hashlib.sha1(f.read()).hexdigest()[:12]
                    out[p] = {"size": st.st_size, "sha1": h, "mode": oct(st.st_mode & 0o777)}
                except OSError:
                    pass
            if not fn and not dn:
                out[dp + "/"] = {"dir": True}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="/tmp/pes-dshm")
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    B = a.base
    if os.path.exists(B):
        shutil.rmtree(B)
    HOME, ROOT, VENV, WORK, SEC = (os.path.join(B, x) for x in ("home", "root", "venv", "work", "secrets"))
    for d in (HOME, ROOT, WORK, SEC):
        os.makedirs(d)
    os.chmod(SEC, 0o700)
    os.makedirs(a.out, exist_ok=True)

    env = {"HOME": HOME, "PATH": f"{VENV}/bin:/usr/local/bin:/usr/bin:/bin",
           "MDCG_ROOT": ROOT, "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8",
           "npm_config_cache": os.path.join(HOME, ".npm"), "npm_config_yes": "true"}
    rec = Rec(os.path.join(a.out, "install.jsonl"), "dsh-memory 隔离安装", run="dsh_install")
    rec.event("env", base=B, HOME=HOME, MDCG_ROOT=ROOT, venv=VENV, sha=a.sha,
              note="按 README「其它 MCP 宿主 → 直接挂载大脑」+「一键配置（推荐）」+「写入凭据」三节走；"
                   "本机无 DSH 宿主，DSH 专属步骤（dsh plugin add / cordis.yml）不适用，如实标注")
    json.dump(snapshot(HOME, ROOT), open(os.path.join(a.out, "snap_before.json"), "w"), indent=0)
    rec.event("snapshot", which="before", files=0)

    clone = os.path.join(WORK, "dsh-memory")
    steps = []

    def step(name, cmd, cwd=WORK, timeout=300, redact=(), doc=""):
        rec.event("step", name=name, doc=doc)
        rc, out, err, dt = rec.run(cmd, cwd=cwd, env=env, timeout=timeout, step=name, redact=redact)
        steps.append({"name": name, "cmd": cmd, "rc": rc, "secs": dt})
        return rc, out, err

    # S0 venv（我们的隔离手段，非 README 要求）
    step("S0 建 venv（隔离用，非 README 步骤）", f"/usr/local/bin/python3 -m venv {VENV}")
    # S1 README ① 克隆
    step("S1 git clone（README 手工步骤①）", f"git clone {REPO} && cd dsh-memory && git checkout -q {a.sha} && git log -1 --format=%H",
         doc="README §快速开始 ①")
    # S2 README 一键配置（推荐）：npx init，非交互形态，端=generic(通用 MCP)
    step("S2 npx init（README「一键配置（推荐）」，非交互，--end generic）",
         f"npx @furongjun1999/dsh-memory init -- --end generic --root {ROOT} --python {VENV}/bin/python",
         timeout=300, doc="README §一键配置")
    # S2b 失败时按包内同一 CLI 本地跑（若 lib/ 未构建需 npm run build）
    step("S2b 本地仓内 init CLI（lib/ 是否随仓提供）", "ls lib 2>&1 | head; ls lib/init.js 2>&1", cwd=clone)
    # S3 大脑直连自检（README 装后验证）：--show-config
    step("S3 python3 -m md_cg.mcp_server --show-config（README 装后验证/写入凭据节）",
         "python3 -m md_cg.mcp_server --show-config", cwd=clone, timeout=120)
    # S4 README 写入凭据原文命令（Windows 续行 ^ + setx）照抄在 Linux 上
    readme_cmd = ("python -m md_cg.tokens issue --role designer --actor dsh-memory --clearance internal ^\n"
                  "  --ops-allow info,route,read,write,recent,goal,identity,whitebox,verify ^\n"
                  "  --layers-allow knowledge,contextual,structural,self,goals,unresolved,rejected")
    rc, out, err = step("S4 README 令牌命令原样照抄（Windows 续行符 ^）", readme_cmd, cwd=clone, timeout=60,
                        doc="README §写入凭据 的代码块为 Windows cmd 语法")
    for m in re.findall(r"mdcg1\.[A-Za-z0-9._\-]+", out):
        pass
    # S5 Linux 正确形态：designer（README 原参数）
    rc, out, err = step("S5 令牌签发 designer（README 参数，Linux 单行）",
                        "python3 -m md_cg.tokens issue --role designer --actor dsh-memory --clearance internal "
                        "--ops-allow info,route,read,write,recent,goal,identity,whitebox,verify "
                        "--layers-allow knowledge,contextual,structural,self,goals,unresolved,rejected "
                        f"> {SEC}/designer.out 2>&1; echo rc=$?; sed -E 's/mdcg1\\.[A-Za-z0-9._-]+/<REDACTED>/g' {SEC}/designer.out",
                        cwd=clone, timeout=60)
    # S6 recorder 最小权限令牌（README 提到 --role recorder）
    step("S6 令牌签发 recorder（README 所称最小权限版）",
         f"python3 -m md_cg.tokens issue --role recorder --actor pes-recorder > {SEC}/recorder.out 2>&1; echo rc=$?; "
         f"sed -E 's/mdcg1\\.[A-Za-z0-9._-]+/<REDACTED>/g' {SEC}/recorder.out", cwd=clone, timeout=60)
    # 抽取令牌明文到 0600 文件
    for nm in ("designer", "recorder"):
        try:
            txt = open(f"{SEC}/{nm}.out", encoding="utf-8").read()
            m = re.search(r"mdcg1\.[A-Za-z0-9._\-]+", txt)
            if m:
                p = f"{SEC}/{nm}.token"
                with open(p, "w") as f:
                    f.write(m.group(0))
                os.chmod(p, 0o600)
                rec.event("token_saved", role=nm, path=p, shown="<REDACTED>")
            else:
                rec.event("token_missing", role=nm)
        except OSError as e:
            rec.event("token_missing", role=nm, err=str(e))
    # S7 令牌 list（看落盘位置与权限）
    step("S7 tokens list + 令牌库位置/权限", "python3 -m md_cg.tokens list 2>&1 | sed -E 's/mdcg1\\.[A-Za-z0-9._-]+/<REDACTED>/g' | head -40; "
         f"ls -la {HOME}/.mdcg 2>&1", cwd=clone, timeout=60)
    # ---- 追加：把首轮里观察到的问题逐个复现进录像 ----
    here = os.path.dirname(os.path.abspath(__file__))
    PROBE = f"python3 {here}/probe_cli.py"
    common = f"--base {B} --clone {clone}"
    step("S2c npx init 是否产出（README 承诺打印片段并写 lingshu-mcp-snippet.json）",
         "ls -la lingshu-mcp-snippet.json 2>&1; echo '--- npx 缓存里的包版本 ---'; "
         "grep -m1 '\"version\"' $HOME/.npm/_npx/*/node_modules/@furongjun1999/dsh-memory/package.json; "
         "grep -n 'import.meta.url === entryUrl' $HOME/.npm/_npx/*/node_modules/@furongjun1999/dsh-memory/lib/cli.js")
    step("S2d 绕过：直接 node 执行 npx 缓存里的 lib/cli.js（证明是符号链接入口判定 bug，源码 29e24da9 已修、npm 包未发）",
         f"node $HOME/.npm/_npx/*/node_modules/@furongjun1999/dsh-memory/lib/cli.js init -- --end generic "
         f"--root {ROOT} --python {VENV}/bin/python; echo; cat lingshu-mcp-snippet.json | head -30", timeout=120)
    step("S8 按 init 片段（surface=kernel，README designer 令牌）握手",
         f"{PROBE} handshake {common} --root {ROOT} --surface kernel --token {SEC}/designer.token", timeout=120)
    step("S9 同上，surface=full（DSH 插件运行时自身用 full）",
         f"{PROBE} handshake {common} --root {ROOT} --surface full --token {SEC}/designer.token", timeout=120)
    # 写一份小会话 JSONL（公式符号复制乱码原因.md → 50 轮）
    jl = os.path.join(B, "probe_session.jsonl")
    sys.path.insert(0, here)
    from corpus_to_jsonl import turns  # noqa: E402
    with open(jl, "w", encoding="utf-8") as f:
        for t in turns("/workspace/work/ls/hmb/e2e/corpus/公式符号复制乱码原因.md"):
            f.write(json.dumps({"role": t["role"], "text": t["text"], "session": "probe.md",
                                "seq": t["line_start"]}, ensure_ascii=False) + "\n")
    step("S10 README designer 令牌（clearance internal）走会话摄取 cg(op=ingest,jsonl)，连做两次看水位",
         f"{PROBE} ingest {common} --root {B}/probe_root_a --token {SEC}/designer.token --jsonl {jl} --repeat 2", timeout=120)
    step("S10b 同一 README 令牌改走细粒度工具 mdcg_ingest（ops 白名单不含 ingest，看是否同样被闸）连做两次",
         f"{PROBE} ingest_fine {common} --root {B}/probe_root_e --token {SEC}/designer.token --jsonl {jl} --repeat 2", timeout=120)
    step("S11 recorder 令牌（README 所称最小权限）走会话摄取",
         f"{PROBE} ingest {common} --root {B}/probe_root_b --token {SEC}/recorder.token --jsonl {jl}", timeout=120)
    step("S12 按服务端 hint 补签 designer --clearance private（+ops ingest,session）",
         "python3 -m md_cg.tokens issue --role designer --actor pes-dsh --clearance private "
         "--ops-allow info,route,read,write,recent,goal,identity,whitebox,verify,ingest,session "
         "--layers-allow knowledge,contextual,structural,self,goals,unresolved,rejected "
         f"> {SEC}/designer_private.out 2>&1; echo rc=$?; sed -E 's/mdcg1\\.[A-Za-z0-9._-]+/<REDACTED>/g' {SEC}/designer_private.out | head -8",
         cwd=clone, timeout=60)
    try:
        txt = open(f"{SEC}/designer_private.out", encoding="utf-8").read()
        mm = re.search(r"mdcg1\.[A-Za-z0-9._\-]+", txt)
        with open(f"{SEC}/designer_private.token", "w") as f:
            f.write(mm.group(0))
        os.chmod(f"{SEC}/designer_private.token", 0o600)
    except Exception as e:  # noqa: BLE001
        rec.event("token_missing", role="designer_private", err=str(e))
    step("S13 private designer 令牌走会话摄取（新库）",
         f"{PROBE} ingest {common} --root {B}/probe_root_c --token {SEC}/designer_private.token --jsonl {jl}", timeout=120)
    step("S13b 同一令牌对 S10 已被拒的库重试（水位是否已被拒绝事件推进）",
         f"{PROBE} ingest {common} --root {B}/probe_root_a --token {SEC}/designer_private.token --jsonl {jl}", timeout=120)
    step("S13c 对 S11（recorder 被拒 50/50）的库用 private 令牌重试：被拒事件是否已推进水位",
         f"{PROBE} ingest {common} --root {B}/probe_root_b --token {SEC}/designer_private.token --jsonl {jl}", timeout=120)
    step("S13d 对 S10b 的库用 private 令牌重试", 
         f"{PROBE} ingest {common} --root {B}/probe_root_e --token {SEC}/designer_private.token --jsonl {jl}", timeout=120)
    step("S14 DSH 运行时自动记忆缺省通道 mdcg_remember(gated) 逐条写 25 条用户消息：闸门四态+时延",
         f"{PROBE} remember {common} --root {B}/probe_root_d --token {SEC}/designer.token --jsonl {jl} --n 25", timeout=120)
    json.dump(snapshot(HOME, ROOT), open(os.path.join(a.out, "snap_after_install.json"), "w"), indent=0)
    rec.event("snapshot", which="after_install")
    # ---- 卸载：README 无卸载章节；按常识删 clone + venv（+npx 缓存另列） ----
    step("U1 卸载（README 无卸载说明；删 clone 与 venv）", f"rm -rf {clone} {VENV}; echo done")
    step("U2 残留检查：HOME / MDCG_ROOT / 临时目录",
         f"cd {HOME} && find . -type f | sort | head -80; echo '--- /tmp/md_cg_servers ---'; ls -la /tmp/md_cg_servers 2>&1 | head -20; "
         f"echo '--- MDCG_ROOT ---'; find {ROOT} -type f | head")
    after = snapshot(HOME, ROOT)
    before = json.load(open(os.path.join(a.out, "snap_before.json")))
    new = sorted(set(after) - set(before))
    tops = {}
    for p in new:
        rel = p.replace(HOME, "~").split("/")
        key = "/".join(rel[:3]) if p.startswith(HOME) else p.replace(ROOT, "$MDCG_ROOT").split("/")[0]
        tops.setdefault(key, [0, 0])
        tops[key][0] += 1
        tops[key][1] += after[p].get("size", 0) if isinstance(after[p], dict) else 0
    json.dump({"new_files": new, "by_top": tops}, open(os.path.join(a.out, "residue_after_uninstall.json"), "w"),
              ensure_ascii=False, indent=1)
    rec.event("residue", by_top=tops, n_new=len(new))
    rec.event("summary", steps=steps, clone=clone)
    rec.close()
    render_md(os.path.join(a.out, "install.jsonl"), os.path.join(a.out, "install_时间轴.md"),
              "dsh-memory 隔离安装 · 录像时间轴")
    print(json.dumps(steps, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
