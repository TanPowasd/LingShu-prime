# -*- coding: utf-8 -*-
"""dsh-auto-memory 0.7.0 · 真实宿主安装录像（照 README「安装」节）。

  python plugins/dsh-auto-memory/install_recorded.py <out_dir>

步骤（每条命令都经 harness.adapter.run_cmd 录像）：
  S1 环境：node -v / npm -v（README：Node ^22.19 || >=24）
  S2 装宿主：npm i -g --prefix <sbx>/npm-global @deepseek-ai/dsh@<HOST_VER>（README：@deepseek-ai/dsh >= 0.1.5-rc.2）
  S3 dsh --version / dsh --help
  S4 README 原命令：dsh plugin --profile demo add dsh-auto-memory
  S5 查看 profile 目录、cordis.patch.yml、插件落点、node_modules 中插件包哈希
  S6 dsh plugin --help（找卸载命令）
沙箱：临时 HOME（plugins/dsh-auto-memory/_sbx/install/home），不带 CLINE_API_KEY。
"""
from __future__ import annotations
import hashlib, json, os, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from harness.adapter import run_cmd  # noqa: E402
from harness.recorder import Recorder, render_timeline  # noqa: E402

HOST_VER = os.environ.get("DAM_HOST_VER", "0.2.0-rc.2")
SBX = ROOT / "plugins/dsh-auto-memory/_sbx/install"


def main(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    if SBX.exists():
        shutil.rmtree(SBX)
    home = SBX / "home"; prefix = SBX / "npm-global"; tmp = SBX / "tmp"
    for d in (home, prefix, tmp):
        d.mkdir(parents=True, exist_ok=True)
    env = {"HOME": str(home), "TMPDIR": str(tmp), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
           "PATH": f"{prefix}/bin:/usr/local/bin:/usr/bin:/bin", "npm_config_cache": str(home / ".npm"),
           "npm_config_update_notifier": "false", "npm_config_fund": "false", "npm_config_audit": "false"}
    assert "CLINE_API_KEY" not in env
    rec = Recorder(out / "install.recording.jsonl", "dam-install", resume=False)
    rec.event("sandbox.create", root=str(SBX), env_keys=sorted(env), host_ver=HOST_VER)
    res = {"host_ver": HOST_VER, "steps": []}

    def step(sid, cmd, timeout=900):
        rec.event("step", id=sid)
        p = run_cmd(cmd, rec, cwd=str(home), env=env, timeout=timeout)
        res["steps"].append({"id": sid, "cmd": cmd, "rc": p.returncode, "stdout_tail": p.stdout[-1500:], "stderr_tail": p.stderr[-1500:]})
        (out / "install_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
        return p

    step("S1a", ["node", "-v"]); step("S1b", ["npm", "-v"])
    p = step("S2", ["npm", "i", "-g", "--prefix", str(prefix), f"@deepseek-ai/dsh@{HOST_VER}"], timeout=1500)
    step("S3a", ["dsh", "--version"]); step("S3b", ["dsh", "--help"])
    step("S4", ["dsh", "plugin", "--profile", "demo", "add", "dsh-auto-memory"], timeout=900)
    step("S6", ["dsh", "plugin", "--help"])
    step("S5a", "find $HOME -maxdepth 4 -not -path '*/node_modules/*' -not -path '*/.npm/*' | head -100")
    step("S5b", "find $HOME -name cordis.patch.yml -not -path '*/.npm/*' | head; for f in $(find $HOME -name 'cordis*.yml' -not -path '*/.npm/*' | head -5); do echo == $f; cat $f; done")
    step("S5c", "for d in $(find $HOME %s -type d -name dsh-auto-memory -path '*node_modules*' 2>/dev/null | head -5); do echo == $d; cat $d/package.json | head -5; sha256sum $d/lib/index.js; done" % prefix)
    # 插件包哈希对照 npm tarball 内 lib/index.js
    pkg = ROOT / "plugins/dsh-auto-memory/_pkg/package/lib/index.js"
    res["tarball_lib_index_sha256"] = hashlib.sha256(pkg.read_bytes()).hexdigest() if pkg.exists() else None
    (out / "install_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    rec.close(); render_timeline(out / "install.recording.jsonl", out / "install.timeline.md")


if __name__ == "__main__":
    main(sys.argv[1])
