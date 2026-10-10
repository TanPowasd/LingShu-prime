"""隔离：每个插件一个独立沙箱（临时 HOME / 工作目录 / venv 路径 / 精简环境变量），并做安装前后快照 diff。

插件拿不到生成器与判官的密钥（CLINE_API_KEY 不进入 sandbox.env）。
"""
from __future__ import annotations
import os, shutil
from pathlib import Path

SBX_ROOT = Path(os.environ.get("PES_SBX_ROOT", "/tmp/pes-sbx"))
WATCH_OUTSIDE = [Path("/tmp")]           # 粗粒度观测：沙箱外是否出现新条目（顶层）


class Sandbox:
    def __init__(self, name: str, *, fresh: bool = True):
        self.root = SBX_ROOT / name
        if fresh and self.root.exists():
            shutil.rmtree(self.root)
        self.home = self.root / "home"
        self.work = self.root / "work"
        self.venv = self.root / "venv"
        self.tmp = self.root / "tmp"
        for d in (self.home, self.work, self.tmp):
            d.mkdir(parents=True, exist_ok=True)
        self.env = {
            "HOME": str(self.home), "TMPDIR": str(self.tmp), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "PATH": f"{self.venv}/bin:/usr/local/bin:/usr/bin:/bin",
            "XDG_CONFIG_HOME": str(self.home / ".config"), "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_CACHE_HOME": str(self.home / ".cache"), "PYTHONNOUSERSITE": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        }

    def snapshot(self) -> dict:
        snap = {}
        for p in self.root.rglob("*"):
            try:
                if p.is_file() or p.is_symlink():
                    snap[str(p.relative_to(self.root))] = p.lstat().st_size
            except OSError:
                pass
        outside = {}
        for w in WATCH_OUTSIDE:
            try:
                outside[str(w)] = sorted(x.name for x in w.iterdir())
            except OSError:
                outside[str(w)] = []
        return {"files": snap, "outside": outside}

    @staticmethod
    def diff(before: dict, after: dict) -> dict:
        added = sorted(set(after["files"]) - set(before["files"]))
        changed = sorted(k for k in set(after["files"]) & set(before["files"]) if after["files"][k] != before["files"][k])
        out_new = {}
        for k, v in after["outside"].items():
            new = sorted(set(v) - set(before["outside"].get(k, [])) - {"pes-sbx"})
            if new:
                out_new[k] = new
        return {"added": added, "changed": changed, "outside_new": out_new,
                "added_bytes": sum(after["files"][k] for k in added)}
