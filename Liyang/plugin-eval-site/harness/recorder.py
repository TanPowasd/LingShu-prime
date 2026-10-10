"""录像器：JSONL 事件流 + mm:ss 时间轴渲染 + 报告扣分点引用校验。

事件行：{"run": run_id, "seq": n, "t": 相对开录秒(单调钟, 跨续跑累加), "wall": ISO8601 CST, "type": ..., ...payload}
- 续跑（--resume）时追加到同一文件：t 从上次最后一条事件的 t 继续累加（中间停机时间不计入，
  另记 rec.resume 事件带墙钟），因此 t 单调不减。
- 报告引用格式（唯一合法写法）：⟦录像:<run_id>@<mm:ss>#<seq>⟧
- 扣分点标记：报告中含「【扣】」的行即一个扣分点，必须带 ≥1 个合法引用。
"""
from __future__ import annotations
import datetime as _dt, json, os, re, threading, time
from pathlib import Path

CST = _dt.timezone(_dt.timedelta(hours=8))
CITE_RE = re.compile(r"⟦录像:(?P<run>[^@⟧]+)@(?P<mmss>\d+:\d{2})#(?P<seq>\d+)⟧")
DEDUCT_MARK = "【扣】"


def wall_cst() -> str:
    """墙钟（CST，ISO8601 毫秒）。不用 datetime.isoformat（沙箱环境对其有改写）。"""
    now = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now + 8 * 3600)) + f".{int(now * 1000) % 1000:03d}+08:00"


def mmss(t: float) -> str:
    t = int(t)
    return f"{t // 60:02d}:{t % 60:02d}"


def cite(run_id: str, ev: dict) -> str:
    return f"⟦录像:{run_id}@{mmss(ev['t'])}#{ev['seq']}⟧"


class Recorder:
    def __init__(self, path, run_id: str, *, resume: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self._lock = threading.Lock()
        self.seq = 0
        base_t = 0.0
        if self.path.exists() and resume:
            last = None
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            last = json.loads(line)
                        except json.JSONDecodeError:
                            pass  # 断电半行：忽略
            if last:
                self.seq = int(last["seq"])
                base_t = float(last["t"])
        elif self.path.exists():
            raise FileExistsError(f"{self.path} 已存在；续跑请加 --resume")
        self._base = base_t
        self._m0 = time.monotonic()
        self._f = open(self.path, "a", encoding="utf-8")
        self.event("rec.resume" if base_t or self.seq else "rec.start", pid=os.getpid())

    def now(self) -> float:
        return round(self._base + (time.monotonic() - self._m0), 3)

    def event(self, type_: str, **payload) -> dict:
        with self._lock:
            self.seq += 1
            ev = {"run": self.run_id, "seq": self.seq, "t": self.now(),
                  "wall": wall_cst(), "type": type_}
            ev.update(payload)
            self._f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            self._f.flush()
            return ev

    def close(self):
        self.event("rec.stop")
        self._f.close()


def load_events(path) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def _summ(ev: dict) -> str:
    t = ev["type"]
    if t == "llm.request":
        n = sum(len(m.get("content", "")) for m in ev.get("messages", []))
        return f"{ev.get('role')}[{ev.get('instance')}] {ev.get('tag')} 送入 {n} 字符"
    if t == "llm.response":
        u = ev.get("usage") or {}
        raw = (ev.get("raw") or "").replace("\n", " ")
        return f"{ev.get('role')} {ev.get('tag')} 回复 {u.get('total_tokens')} tok：{raw[:80]}"
    if t.startswith("cmd."):
        return json.dumps({k: ev.get(k) for k in ("cmd", "rc", "dur_s") if k in ev}, ensure_ascii=False)
    keys = [k for k in ev if k not in ("run", "seq", "t", "wall", "type")]
    s = json.dumps({k: ev[k] for k in keys[:6]}, ensure_ascii=False)
    return s[:160]


def render_timeline(jsonl_path, md_path=None) -> str:
    evs = load_events(jsonl_path)
    run = evs[0]["run"] if evs else "?"
    lines = [f"# 录像时间轴 · {run}", "", f"源：`{Path(jsonl_path).name}`，共 {len(evs)} 个事件。"
             "时间轴为单调钟 mm:ss（续跑累加），墙钟见右列。", "",
             "| mm:ss | #seq | 墙钟(CST) | 事件 | 摘要 |", "|:--|--:|:--|:--|:--|"]
    for ev in evs:
        s = _summ(ev).replace("|", "\\|")
        lines.append(f"| {mmss(ev['t'])} | {ev['seq']} | {ev['wall'][11:23]} | {ev['type']} | {s} |")
    md = "\n".join(lines) + "\n"
    if md_path:
        Path(md_path).write_text(md, encoding="utf-8")
    return md


def validate_report(report_text: str, recordings: dict) -> dict:
    """recordings: {run_id: jsonl_path}。返回 {total, ok, coverage, problems}。
    扣分点 = 含【扣】的行；合法 = 至少一个引用，且 run 存在、seq 存在、mm:ss 与该事件 t 一致。"""
    idx = {}
    for rid, p in recordings.items():
        idx[rid] = {e["seq"]: e for e in load_events(p)}
    total = ok = 0
    problems = []
    for ln, line in enumerate(report_text.splitlines(), 1):
        if DEDUCT_MARK not in line:
            continue
        total += 1
        cites = list(CITE_RE.finditer(line))
        if not cites:
            problems.append((ln, "无录像引用"))
            continue
        bad = None
        for m in cites:
            run, seq, ts = m.group("run"), int(m.group("seq")), m.group("mmss")
            if run not in idx:
                bad = f"录像 {run} 不存在"
            elif seq not in idx[run]:
                bad = f"{run}#{seq} 无此事件"
            elif mmss(idx[run][seq]["t"]) != ts:
                bad = f"{run}#{seq} 时间不符（{ts} vs {mmss(idx[run][seq]['t'])}）"
            if bad:
                break
        if bad:
            problems.append((ln, bad))
        else:
            ok += 1
    cov = 1.0 if total == 0 else ok / total
    return {"total": total, "ok": ok, "coverage": cov, "pass": ok == total, "problems": problems}
