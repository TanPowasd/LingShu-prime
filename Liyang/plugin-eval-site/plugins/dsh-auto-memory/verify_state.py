# -*- coding: utf-8 -*-
"""独立状态校验脚本（快照契约 dam-snap-v1 的检查端）。

与恢复/运行代码不共用任何代码路径：不 import emu.py / run_pairs.py / harness，只用标准库直接读盘、读进程表。
不信任插件或 node 驱动的自报：文件清单与哈希在这里由 Python 重新计算后再与自报比对。

用法（每次输出一行 JSON 到 stdout，并以退出码 0=通过 / 1=不通过）：
  verify_state.py run-pre   --state-root R --emu-home H --plugin-lib L --expect-lib-sha S
  verify_state.py card-pre  --mem M
  verify_state.py card-post --mem M --reported J      （J = node 驱动自报的 manifest JSON 文件）
  verify_state.py b0        --state-root R            （B0 运行：不得出现任何记忆目录）
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess, sys

INDEX = "MEMORY.md"
LINE_RE = re.compile(r"^- \[(?P<title>.*)\]\((?P<file>[a-z0-9-]+\.md)\)")


def walk(root):
    out = []
    if not os.path.isdir(root):
        return out
    for dp, dn, fn in os.walk(root):
        for n in fn:
            p = os.path.join(dp, n)
            with open(p, "rb") as f:
                b = f.read()
            out.append({"path": os.path.relpath(p, root), "bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()})
    return sorted(out, key=lambda x: x["path"])


def emu_procs():
    try:
        r = subprocess.run(["pgrep", "-af", "^node host_emu.mjs"], capture_output=True, text=True)
        return [l for l in r.stdout.splitlines() if "pgrep" not in l]
    except FileNotFoundError:
        return ["pgrep-unavailable"]


def check_run_pre(a):
    fails = []
    if os.path.exists(a.state_root) and os.listdir(a.state_root):
        fails.append(f"state_root 非空：{sorted(os.listdir(a.state_root))[:10]}")
    procs = emu_procs()
    if procs:
        fails.append(f"残留 host_emu 进程：{procs[:5]}")
    for sub in ("memory", "sessions"):
        p = os.path.join(a.emu_home, ".dsh", sub)
        if os.path.exists(p) and walk(p):
            fails.append(f"宿主目录残留状态：{p}")
    with open(a.plugin_lib, "rb") as f:
        got = hashlib.sha256(f.read()).hexdigest()
    if got != a.expect_lib_sha:
        fails.append(f"插件包被改动：lib sha {got}")
    return {"check": "run-pre", "pass": not fails, "fails": fails, "lib_sha256": got}


def check_card_pre(a):
    fails = []
    if os.path.exists(a.mem):
        fails.append(f"记忆根已存在（未恢复到空基线）：{walk(a.mem)[:5]}")
    procs = emu_procs()
    return {"check": "card-pre", "pass": not fails, "fails": fails, "emu_procs_running": len(procs)}


def check_card_post(a):
    fails = []
    files = walk(a.mem)
    with open(a.reported, encoding="utf-8") as f:
        rep = json.load(f)
    rep_n = sorted(({"path": x["path"], "bytes": x["bytes"], "sha256": x["sha256"]} for x in rep), key=lambda x: x["path"])
    if rep_n != files:
        fails.append("自报清单与磁盘实测不一致")
    leftovers = [x["path"] for x in files if x["path"].endswith((".lock", ".tmp")) or ".tmp-" in x["path"]]
    if leftovers:
        fails.append(f"锁/临时文件残留：{leftovers}")
    # 索引一致性：每个作用域目录里 MEMORY.md 的每一行都指向本目录真实存在的记忆文件；有记忆文件则必须有索引
    dirs = sorted({os.path.dirname(x["path"]) for x in files})
    index_lines = 0
    for d in dirs:
        names = {os.path.basename(x["path"]) for x in files if os.path.dirname(x["path"]) == d}
        mems = {n for n in names if n.endswith(".md") and n != INDEX}
        if mems and INDEX not in names:
            fails.append(f"{d}: 有 {len(mems)} 条记忆但无 {INDEX}")
        if INDEX in names:
            with open(os.path.join(a.mem, d, INDEX), encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    m = LINE_RE.match(line)
                    if not m:
                        fails.append(f"{d}/{INDEX} 行格式不符：{line[:80]!r}"); continue
                    index_lines += 1
                    if m.group("file") not in mems:
                        fails.append(f"{d}/{INDEX} 指向不存在的文件 {m.group('file')}")
    return {"check": "card-post", "pass": not fails, "fails": fails, "n_files": len(files), "index_lines": index_lines,
            "manifest_sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()}


def check_b0(a):
    fails = []
    for dp, dn, fn in os.walk(a.state_root):
        for d in dn:
            if d in ("mem", "memory", "_user") or d.startswith("--"):
                fails.append(f"B0 运行出现记忆目录：{os.path.join(dp, d)}")
    return {"check": "b0", "pass": not fails, "fails": fails}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["run-pre", "card-pre", "card-post", "b0"])
    ap.add_argument("--state-root"); ap.add_argument("--emu-home"); ap.add_argument("--plugin-lib")
    ap.add_argument("--expect-lib-sha"); ap.add_argument("--mem"); ap.add_argument("--reported")
    a = ap.parse_args()
    r = {"run-pre": check_run_pre, "card-pre": check_card_pre, "card-post": check_card_post, "b0": check_b0}[a.mode](a)
    r["verifier"] = "verify_state.py/dam-snap-v1"
    print(json.dumps(r, ensure_ascii=False))
    sys.exit(0 if r["pass"] else 1)


if __name__ == "__main__":
    main()
