"""适配器接口（固定契约 v0.1 —— pes-harness 与 pes-dsh 双方按此实现）。

class Plugin:
    name: str; version: str
    install(rec)               -> InstallResult(ok, steps, errors)
    ingest(sessions, rec)      -> None
    recall(query, k, rec)      -> list[{"text": str, "source": str|None}]
    uninstall(rec)             -> {"residue_paths": [...]}

约定（详见 SPEC_接线规范_v0.1.md §2）：
- rec 是录像器（harness.recorder.Recorder）。插件执行的每条外部命令及其输出都必须 rec.event(...)；
  推荐用本文件的 run_cmd()，它会自动录像。
- sessions：list[Session]，Session = {"session_id": 语料文件名, "turns": [Turn...]}，
  Turn = {"idx": int, "role": "user"|"assistant", "start_line": int, "end_line": int, "text": str}
  （行号 1 起，按 "\\n" 切分的语料行号；text = 语料 start_line..end_line 原文按 "\\n" 拼接，含说话人标记行）。
- recall 返回的 source 规范写法："<文件名>#L<start>-L<end>"（例如 "确认协议内容.md#L120-L188"）。
  harness 依 source 做防泄题过滤：同文件且 start ≥ 答案行 → 剔除；跨答案行 → 若 text 与语料
  start..end 行逐行对齐则截到答案行前一行，否则剔除；source 为 None 或不可解析 → 保守剔除。
"""
from __future__ import annotations
import dataclasses, re, subprocess, time
from typing import Any, Optional

SOURCE_RE = re.compile(r"^(?P<file>[^#]+)#L(?P<start>\d+)-L(?P<end>\d+)$")


@dataclasses.dataclass
class InstallResult:
    ok: bool
    steps: int
    errors: list = dataclasses.field(default_factory=list)


class Plugin:
    name: str = "base"
    version: str = "0"
    kind: str = "python"          # "python" | "mcp-stdio"

    def install(self, rec) -> InstallResult:
        raise NotImplementedError

    def ingest(self, sessions: list[dict], rec) -> None:
        raise NotImplementedError

    def recall(self, query: str, k: int, rec) -> list[dict]:
        raise NotImplementedError

    def uninstall(self, rec) -> dict:
        raise NotImplementedError


def parse_source(src: Optional[str]):
    if not src:
        return None
    m = SOURCE_RE.match(src.strip())
    if not m:
        return None
    return m.group("file"), int(m.group("start")), int(m.group("end"))


def run_cmd(cmd, rec, *, cwd=None, env=None, timeout=600, input=None) -> subprocess.CompletedProcess:
    """跑一条外部命令并完整录像（命令、退出码、stdout/stderr、耗时）。"""
    t0 = time.monotonic()
    rec.event("cmd.start", cmd=cmd if isinstance(cmd, str) else list(cmd), cwd=str(cwd) if cwd else None)
    p = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout, input=input,
                       capture_output=True, text=True, shell=isinstance(cmd, str))
    rec.event("cmd.end", rc=p.returncode, stdout=p.stdout[-20000:], stderr=p.stderr[-20000:],
              dur_s=round(time.monotonic() - t0, 3))
    return p
