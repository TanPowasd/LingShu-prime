# -*- coding: utf-8 -*-
"""录像器（本地后备实现）。

harness/ 的正式录像器落地前，dsh-memory 侧先用这个最小实现：
- 事件行与 harness/recorder.py 同格式：{"run", "seq", "t"(单调钟秒), "wall"(CST), "type", **data}（另带 mmss 便于肉眼读），
  报告可用 ⟦录像:<run>@<mm:ss>#<seq>⟧ 引用并由 harness.recorder.validate_report 校验。
- render_md() 优先用 harness 的 render_timeline；不可用时用本地渲染。
接口与约定的 rec.event(kind, **data) 一致；harness 的 Rec 出现后，adapter 只依赖 .event()。
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import time

CST = _dt.timezone(_dt.timedelta(hours=8))


class Rec:
    def __init__(self, path: str, title: str = "", run: str = None):
        self.path = path
        self.run_id = run or os.path.splitext(os.path.basename(path))[0]
        self.seq = 0
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.t0 = time.monotonic()
        self._f = open(path, "a", encoding="utf-8")
        self.event("rec_start", title=title)

    def mmss(self, t=None) -> str:
        t = (time.monotonic() - self.t0) if t is None else t
        return "%02d:%02d" % (int(t) // 60, int(t) % 60)

    def event(self, kind: str, **data):
        t = time.monotonic() - self.t0
        self.seq += 1
        now = time.time()
        wall = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now + 8 * 3600)) + f".{int(now * 1000) % 1000:03d}+08:00"
        row = {"run": self.run_id, "seq": self.seq, "t": round(t, 3), "mmss": self.mmss(t), "wall": wall,
               "type": kind}
        row.update(data)
        self._f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._f.flush()
        return row

    def run(self, cmd: str, *, cwd=None, env=None, timeout=300, step=None,
            redact=(), max_out=6000):
        """跑一条 shell 命令并全程录像。redact：输出里需遮掉的串（令牌明文等）。"""
        self.event("cmd_start", step=step, cmd=cmd, cwd=cwd)
        t = time.monotonic()
        try:
            p = subprocess.run(cmd, shell=True, cwd=cwd, env=env, timeout=timeout,
                               capture_output=True, text=True)
            rc, out, err = p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired as e:
            rc, out, err = "timeout", (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), "TIMEOUT"
        dt = round(time.monotonic() - t, 3)
        for s in redact:
            if s:
                out = out.replace(s, "<REDACTED>")
                err = err.replace(s, "<REDACTED>")
        self.event("cmd_end", step=step, rc=rc, secs=dt,
                   stdout=out[-max_out:], stderr=err[-max_out:],
                   stdout_len=len(out), stderr_len=len(err))
        return rc, out, err, dt

    def close(self):
        self.event("rec_end")
        self._f.close()


def render_md(jsonl_path: str, md_path: str, title: str = "录像时间轴"):
    try:
        import sys as _s
        _s.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from harness.recorder import render_timeline  # noqa
        md = render_timeline(jsonl_path)
        md = md.replace("# 录像时间轴", "# " + title + " ·", 1)
        detail = _render_local(jsonl_path)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md + "\n---\n\n## 命令输出明细\n\n" + detail)
        return
    except Exception:
        pass
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# " + title + "\n\n" + _render_local(jsonl_path))


def _render_local(jsonl_path: str) -> str:
    lines = [f"> 源：`{os.path.basename(jsonl_path)}`（JSONL 事件流；mm:ss = 自录像开始的单调钟）", ""]
    with open(jsonl_path, encoding="utf-8") as f:
        for ln in f:
            r = json.loads(ln)
            k = r["type"]
            head = f"- **[{r['mmss']}] #{r['seq']}** `{k}`"
            if k == "cmd_start":
                lines.append(head + f" step={r.get('step')} ：`{r.get('cmd')}`")
            elif k == "cmd_end":
                lines.append(head + f" step={r.get('step')} rc={r.get('rc')} 用时 {r.get('secs')}s")
                for nm in ("stdout", "stderr"):
                    v = (r.get(nm) or "").strip()
                    if v:
                        v = v if len(v) < 1500 else (v[:700] + "\n…（截断，全文见 JSONL）…\n" + v[-700:])
                        lines.append(f"  <details><summary>{nm}（{r.get(nm + '_len')} 字符）</summary>\n\n```\n{v}\n```\n</details>")
            else:
                extra = {kk: vv for kk, vv in r.items() if kk not in ("run", "seq", "t", "mmss", "wall", "type")}
                s = json.dumps(extra, ensure_ascii=False)
                lines.append(head + (" " + (s if len(s) < 600 else s[:600] + "…") if extra else ""))
    return "\n".join(lines) + "\n"
