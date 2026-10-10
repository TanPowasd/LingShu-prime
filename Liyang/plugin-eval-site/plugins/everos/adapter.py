# -*- coding: utf-8 -*-
"""EverOS（EverMind-AI/EverOS，PyPI everos 1.4.1）适配器 —— 经 EverOS 本地 HTTP API 接入考场。

接口：harness/adapter.py 固定契约 v0.1（install / ingest / recall / uninstall）。

接法（只走作者推荐的正经路径，不替插件调参；理由见 README_适配器.md）：
  · 安装：README Quick Start 原样 —— venv 里 `pip install everos`（钉 1.4.1）→ `everos init` →
    只改 everos.toml 的 [llm] 三行 → `everos server start`。embedding / rerank / multimodal 不配
    （README「One OpenRouter key is enough」的 Tier 1 一键档；本站也没有可用嵌入端点）。
  · LLM：插件只能用站方的 cline-pass/deepseek-v4.1-flash。everos.toml 的 base_url 指向考场侧本地转发器
    （llm_proxy.py），密钥只在转发器进程里，EverOS 进程环境里没有 CLINE_API_KEY；转发器走
    harness/llm.py 的跨进程匀速闸，并逐次记 token（plugin.tokens）。
  · 写入：模拟官方 DSH 插件（EverMind-AI/plugins/dsh，@f76f4d0）的 capture 策略 ——
    每轮 → MessageItem{sender_id, role, timestamp(ms), content}，/api/v2/memory/add 带 defer_extraction=true
    先落缓冲；缓冲累计 ≥50 条或估算 ≥12,000 token（插件 estimateMessageTokens：ASCII/4 + 非 ASCII 每字 1）
    即 /api/v2/memory/flush；换会话（文件）时 flush 收尾（flushOnSessionSwitch）。单条正文超 50,000 字照插件
    clipText 截断（captureMaxChars）。以上全是插件缺省值。
  · 召回：照 DSH 插件 recall —— query 截前 2,000 字（queryMaxChars, clipHead）；user 轨
    （user_id, include_profile=true）与 agent 轨（agent_id）各 /api/v2/memory/search，method=keyword
    （插件缺省；Tier 1 唯一可用），top_k=考场给的 k（=5，与插件缺省 recallTopK=5 相同）。
    返回顺序照插件 renderMemory：profiles → episodes → agent_cases → agent_skills；文本照 episodeText 等。
  · source（可回源）：episode 由插件的 memcell 生成；适配器读 EverOS 自己的 system.db 里 memcell.payload_json
    的条目时间戳，反查我们写入时给每轮的唯一时间戳 → 原文行号区间 `<文件>#L<s>-L<e>`。profile / agent case /
    skill 是跨会话汇总，插件不给出处 → source=None（考场按 SPEC 保守剔除，单列计数）。
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from harness.adapter import InstallResult, Plugin  # noqa: E402

EVEROS_VERSION = "1.4.1"            # PyPI；= tag v1.4.1 = commit 462ebf9fd59b55c03fefb8eec855c62500f2a3cf
EVEROS_SHA = "462ebf9fd59b55c03fefb8eec855c62500f2a3cf"
DSH_PLUGIN_SHA = "f76f4d06135a0b5d784d15eed133ecdcedc12d47"   # 召回/写入策略照抄的官方 DSH 插件版本
APP_ID, PROJECT_ID, USER_ID, AGENT_ID = "dsh", "pes-examb", "pes-user", "dsh"
FLUSH_MSGS, FLUSH_TOKENS, CAPTURE_MAX, QUERY_MAX = 50, 12000, 50000, 2000
T0_MS = 1767225600000               # 2026-01-01T00:00:00Z：语料无时间戳，按会话×日、轮×60s 造唯一时间戳（只为回源）
SPEAKER = {"**我说：**", "**DeepSeek说：**"}


_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 本地服务直连（沙箱有 HTTP(S)_PROXY 环境变量）


def est_tokens(text: str) -> int:
    a = sum(1 for ch in text if ord(ch) < 128)
    return max(1, -(-a // 4) + (len(text) - a))


def clip(text: str, n: int = CAPTURE_MAX) -> str:
    if len(text) <= n:
        return text
    m = "\n[truncated by everos-memory]"
    return text[: n - len(m)] + m


class EverOS(Plugin):
    name = "everos"
    version = f"{EVEROS_VERSION}@{EVEROS_SHA[:7]}"
    kind = "http-local"
    permissions = ["本地 HTTP 服务 127.0.0.1:<port>（无鉴权）", "读写 ~/.everos（记忆根：Markdown+SQLite+LanceDB）",
                   "出网：[llm].base_url（本站=本地转发器→api.cline.bot）", "无子进程/无 shell 工具面"]

    def __init__(self, base: str | None = None, port: int = 18780, proxy_port: int = 18781,
                 sessions_limit: list | None = None, ingest_par: int = 4):
        self.base = base
        self.port = int(os.environ.get("PES_EVEROS_PORT", port))
        self.proxy_port = int(os.environ.get("PES_EVEROS_PROXY_PORT", self.port + 1 if "PES_EVEROS_PORT" in os.environ else proxy_port))
        env_s = os.environ.get("PES_EVEROS_SESSIONS")          # 只给冒烟用：限定写入哪几份语料（正式臂不设）
        self.sessions_limit = sessions_limit or (env_s.split(",") if env_s else None)
        self.ingest_par = int(os.environ.get("PES_EVEROS_PAR", ingest_par))
        self.ts2src: dict[int, tuple] = {}
        self.server = self.proxy = None
        self.stats = {"add": 0, "flush": [], "search": []}

    # ------------------------------------------------------------ paths/env
    def _bind(self):
        sbx = getattr(self, "sandbox", None)
        if sbx is not None:
            self.base = str(sbx.root)
            self.home, self.venv = str(sbx.home), str(sbx.venv)
        else:
            self.base = self.base or os.path.join(ROOT, "runs/everos/selftest_sbx")
            self.home, self.venv = os.path.join(self.base, "home"), os.path.join(self.base, "venv")
        self.mroot = os.path.join(self.home, ".everos")
        # 持久化（考场适配，不改插件行为）：harness 续跑会清空沙箱（fresh=True），而 EverOS 全量写入要数小时，
        # 且沙箱夜里会重启。故 harness 下把记忆根放到运行目录 runs/<run>/everos_state/root（持久盘），
        # 用 README 支持的 --root 指定；写入按 flush 批次记进度，续跑跳过已提交批次。卸载时把它算作残留单列。
        self.state = None
        if sbx is not None:
            self.state = os.path.join(ROOT, "runs", os.path.basename(str(sbx.root)), "everos_state")
            self.mroot = os.path.join(self.state, "root")
            self.llm_log = None
            os.makedirs(self.state, exist_ok=True)
        self.tmp = os.path.join(self.base, "tmp")
        self.llm_log = os.path.join(self.state or self.base, "everos_llm_calls.jsonl")
        for d in (self.home, self.tmp):
            os.makedirs(d, exist_ok=True)

    def _env(self):
        return {"HOME": self.home, "PATH": f"{self.venv}/bin:/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8", "TMPDIR": self.tmp, "VIRTUAL_ENV": self.venv, "PYTHONNOUSERSITE": "1",
                "XDG_CACHE_HOME": os.path.join(self.home, ".cache"), "UV_CACHE_DIR": os.path.join(self.home, ".cache/uv"),
                "NO_COLOR": "1", "TERM": "dumb", "EVEROS_API__PORT": str(self.port), "EVEROS_ROOT": self.mroot}

    def _run(self, rec, step, cmd, timeout=600):
        rec.event("cmd.start", step=step, cmd=cmd, cwd=self.base)
        t0 = time.monotonic()
        p = subprocess.run(cmd, shell=True, cwd=self.base, env=self._env(), capture_output=True, text=True, timeout=timeout)
        rec.event("cmd.end", step=step, rc=p.returncode, stdout=p.stdout[-8000:], stderr=p.stderr[-8000:],
                  dur_s=round(time.monotonic() - t0, 3))
        return p

    def _http(self, path, body=None, timeout=900):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        req = urllib.request.Request(url, data=data, method="GET" if body is None else "POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with _LOCAL.open(req, timeout=timeout) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except Exception:  # noqa: BLE001
                return e.code, {}

    # ------------------------------------------------------------ install
    def install(self, rec) -> InstallResult:
        self._bind()
        errors, steps = [], 0
        rec.event("plugin.install.begin", plugin=self.name, version=self.version, base=self.base, HOME=self.home,
                  memory_root=self.mroot, port=self.port)
        plan = [("venv", f"uv venv {self.venv} --python 3.12"),
                ("pip", f"uv pip install everos=={EVEROS_VERSION}"),
                ("init", f"everos init --root {self.mroot}")]
        if os.path.exists(os.path.join(self.mroot, "everos.toml")):
            plan = plan[:2]
            rec.event("plugin.install.note", note="续跑：持久记忆根已有 everos.toml，跳过 init（init 无 --force 会 rc=1）", root=self.mroot)
        for step, cmd in plan:
            steps += 1
            p = self._run(rec, step, cmd)
            if p.returncode != 0:
                errors.append(f"{step}: rc={p.returncode} {p.stderr[-300:]}")
                return InstallResult(False, steps, errors)
        steps += 1   # 用户亲手改 everos.toml 的 [llm]
        self._edit_toml(rec)
        try:
            self._start_proxy(rec)
            steps += 1   # everos server start
            self._start_server(rec)
        except Exception as e:  # noqa: BLE001
            errors.append(f"start: {e}")
            return InstallResult(False, steps, errors)
        return InstallResult(True, steps, errors)

    def _edit_toml(self, rec):
        cfg = os.path.join(self.mroot, "everos.toml")
        t = open(cfg, encoding="utf-8").read()
        sec, out = None, []
        for ln in t.split("\n"):
            st = ln.strip()
            if st.startswith("[") and st.endswith("]"):
                sec = st
            if sec == "[llm]" and "=" in st and not st.startswith("#"):
                k = st.split("=")[0].strip()
                ln = {"model": 'model = "cline-pass/deepseek-v4.1-flash"',
                      "api_key": 'api_key = "pes-local-proxy-no-secret"',
                      "base_url": f'base_url = "http://127.0.0.1:{self.proxy_port}/v1"'}.get(k, ln)
            out.append(ln)
        open(cfg, "w", encoding="utf-8").write("\n".join(out))
        rec.event("file.edit", path="~/.everos/everos.toml", section="[llm]",
                  after={"model": "cline-pass/deepseek-v4.1-flash", "api_key": "<占位，非密钥>",
                         "base_url": f"http://127.0.0.1:{self.proxy_port}/v1"})

    def _start_proxy(self, rec):
        env = dict(os.environ)   # 考场侧进程：带 CLINE_API_KEY（只在这里）
        logf = open(os.path.join(self.base, "proxy.log"), "a")
        self.proxy = subprocess.Popen([sys.executable, os.path.join(HERE, "llm_proxy.py"), "--port", str(self.proxy_port),
                                       "--log", self.llm_log], env=env, stdout=logf, stderr=logf, start_new_session=True)
        rec.event("station.proxy.start", pid=self.proxy.pid, port=self.proxy_port, note="考场侧转发器，不属于插件")
        time.sleep(1.5)

    def _start_server(self, rec):
        logf = open(os.path.join(self.base, "server.log"), "a")
        cmd = f"ulimit -n 4096; exec everos server start --root {self.mroot}"
        rec.event("cmd.start", step="server", cmd=cmd, background=True)
        self.server = subprocess.Popen(cmd, shell=True, cwd=self.base, env=self._env(), stdout=logf, stderr=logf,
                                       start_new_session=True)
        t0 = time.monotonic()
        while time.monotonic() - t0 < 120:
            time.sleep(1)
            try:
                code, h = self._http("/health", timeout=3)
                if code == 200:
                    rec.event("cmd.end", step="server", rc=0, health=h, dur_s=round(time.monotonic() - t0, 3), pid=self.server.pid)
                    return
            except Exception:  # noqa: BLE001
                pass
            if self.server.poll() is not None:
                break
        tail = open(os.path.join(self.base, "server.log"), encoding="utf-8", errors="replace").read()[-3000:]
        rec.event("cmd.end", step="server", rc=self.server.poll(), stderr=tail, dur_s=round(time.monotonic() - t0, 3))
        raise RuntimeError("everos server 未就绪：" + tail[-300:])

    # ------------------------------------------------------------ ingest
    def _items(self, si, s):
        out = []
        for t in s["turns"]:
            if t["role"] not in ("user", "assistant"):
                continue                                     # 文件头 meta 段不是对话轮
            lines = t["text"].split("\n")
            if lines and lines[0].strip() in SPEAKER:
                lines = lines[1:]                            # 说话人标记行 → role 字段（纯格式转换）
            text = "\n".join(lines).strip()
            if not text:
                continue
            ts = T0_MS + si * 86_400_000 + t["idx"] * 60_000
            self.ts2src[ts] = (s["session_id"], t["start_line"], t["end_line"])
            out.append({"sender_id": USER_ID if t["role"] == "user" else AGENT_ID, "role": t["role"],
                        "timestamp": ts, "content": clip(text)})
        return out

    def _sid(self, fname):
        import hashlib
        return "pes-" + hashlib.sha1(fname.encode()).hexdigest()[:16]

    def _progress(self):
        p = os.path.join(self.state or self.base, "ingest_progress.json")
        try:
            return p, json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return p, {}

    def ingest(self, sessions, rec):
        """每份语料一个会话；会话内照插件阈值分批 add(defer)+flush。会话之间互不依赖，
        为把 8,146 轮的离线导入压进考场时间，最多 INGEST_PAR 个会话并行（插件服务端本就按会话加锁、支持并发会话）；
        LLM 总速率仍由 harness/llm.py 匀速闸限定。批次进度落盘，续跑跳过已 flush 的批次。"""
        from concurrent.futures import ThreadPoolExecutor
        import threading
        t_all = time.monotonic()
        plock = threading.Lock()
        ppath, prog = self._progress()
        jobs = []
        for si, s in enumerate(sessions):
            items = self._items(si, s)          # 对全部会话建时间戳→行号表（续跑也要）
            if self.sessions_limit and s["session_id"] not in self.sessions_limit:
                continue
            batches, pend, ptok = [], [], 0
            for it in items:
                pend.append(it); ptok += est_tokens(it["content"])
                if len(pend) >= FLUSH_MSGS or ptok >= FLUSH_TOKENS:
                    batches.append((pend, ptok)); pend, ptok = [], 0
            if pend:
                batches.append((pend, ptok))
            jobs.append((s["session_id"], self._sid(s["session_id"]), batches))
        jobs.sort(key=lambda j: -len(j[2]))
        total_b = sum(len(j[2]) for j in jobs)
        done0 = sum(min(prog.get(j[0], 0), len(j[2])) for j in jobs)
        rec.event("plugin.ingest.plan", sessions=len(jobs), batches=total_b, already_done=done0,
                  par=self.ingest_par, flush_msgs=FLUSH_MSGS, flush_tokens=FLUSH_TOKENS)

        def run_session(job):
            fname, sid, batches = job
            t_s = time.monotonic()
            for bi, (pend, ptok) in enumerate(batches):
                if bi < prog.get(fname, 0):
                    continue
                self._commit(rec, sid, fname, pend, ptok, bi=bi, nb=len(batches))
                with plock:
                    prog[fname] = bi + 1
                    tmp = ppath + ".tmp"
                    json.dump(prog, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
                    os.replace(tmp, ppath)
            rec.event("plugin.ingest.session", file=fname, session_id=sid, batches=len(batches),
                      dur_s=round(time.monotonic() - t_s, 1), llm=self.llm_totals())

        with ThreadPoolExecutor(self.ingest_par) as ex:
            list(ex.map(run_session, jobs))
        # 等 cascade 把 Markdown 投影进 LanceDB（关键词检索读的是索引）
        t_w = time.monotonic()
        while time.monotonic() - t_w < 600:
            code, h = self._http("/health", timeout=10)
            if code == 200 and not ((h.get("cascade") or {}).get("pending")):
                break
            time.sleep(5)
        rec.event("plugin.ingest.summary", batches=total_b, dur_s=round(time.monotonic() - t_all, 1),
                  cascade_wait_s=round(time.monotonic() - t_w, 1), llm=self.llm_totals())
        rec.event("plugin.tokens", phase="ingest", **self.llm_totals())

    def _commit(self, rec, sid, fname, pend, ptok, bi=0, nb=0):
        t0 = time.monotonic()
        for i in range(0, len(pend), 500):
            code, r = self._http("/api/v2/memory/add", {"session_id": sid, "app_id": APP_ID, "project_id": PROJECT_ID,
                                                        "messages": pend[i:i + 500], "defer_extraction": True})
            if code != 200:
                rec.event("plugin.add.error", file=fname, code=code, resp=json.dumps(r, ensure_ascii=False)[:800])
                raise RuntimeError(f"/add HTTP {code}: {json.dumps(r, ensure_ascii=False)[:300]}")
            self.stats["add"] += 1
        t1 = time.monotonic()
        for attempt in range(3):     # flush 失败（多为 LLM 超时→5xx）照常理重试，最多 3 次；仍失败则记为插件写入失败、继续下一批
            try:
                code, r = self._http("/api/v2/memory/flush", {"session_id": sid, "app_id": APP_ID, "project_id": PROJECT_ID})
            except Exception as e:  # noqa: BLE001
                code, r = 599, {"error": repr(e)[:300]}
            if code == 200:
                break
            rec.event("plugin.flush.retry", file=fname, batch=bi + 1, attempt=attempt + 1, code=code,
                      resp=json.dumps(r, ensure_ascii=False)[:500])
            time.sleep(10)
        dt = time.monotonic() - t1
        self.stats["flush"].append(dt)
        rec.event("plugin.flush", file=fname, batch=f"{bi + 1}/{nb}", msgs=len(pend), est_tokens=ptok, code=code,
                  status=(r.get("data") or {}).get("status") if isinstance(r, dict) else None,
                  add_s=round(t1 - t0, 2), flush_s=round(dt, 2),
                  error=None if code == 200 else json.dumps(r, ensure_ascii=False)[:500])
        if code != 200:
            self.stats.setdefault("flush_failed", []).append((fname, bi + 1))

    def llm_totals(self):
        tot = {"calls": 0, "ok": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "non_chat_501": 0}
        if os.path.exists(self.llm_log):
            for ln in open(self.llm_log, encoding="utf-8"):
                try:
                    r = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                tot["calls"] += 1
                if r.get("status") == 501:
                    tot["non_chat_501"] += 1
                if r.get("status") == 200:
                    tot["ok"] += 1
                    tot["prompt_tokens"] += r.get("prompt_tokens") or 0
                    tot["completion_tokens"] += r.get("completion_tokens") or 0
                    tot["cost_usd"] += float(r.get("cost_usd") or 0)
        tot["cost_usd"] = round(tot["cost_usd"], 4)
        return tot

    # ------------------------------------------------------------ recall
    def _memcell_src(self):
        """episode id → (file, start, end)。读 EverOS 自己的 Markdown（parent_id）与 system.db（memcell.payload_json）。"""
        import glob
        import re
        ep2mc = {}
        for p in glob.glob(os.path.join(self.mroot, "*", "*", "users", "*", "episodes", "*.md")):
            cur = None
            for ln in open(p, encoding="utf-8"):
                m = re.match(r"^## (\S+)", ln)
                if m:
                    cur = m.group(1)
                m = re.match(r"^\*\*parent_id\*\*: (\S+)", ln)
                if m and cur:
                    ep2mc[cur] = m.group(1)
        db = os.path.join(self.mroot, ".index", "sqlite", "system.db")
        mc = {}
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
        for mid, pj in con.execute("select memcell_id, payload_json from memcell"):
            try:
                items = json.loads(pj).get("items") or []
            except Exception:  # noqa: BLE001
                continue
            srcs = []
            for it in items:
                ts = it.get("timestamp")
                if isinstance(ts, str):
                    continue
                if ts is not None and ts < 10**11:
                    ts = int(ts * 1000)
                if ts in self.ts2src:
                    srcs.append(self.ts2src[ts])
            mc[mid] = srcs
        con.close()
        return ep2mc, mc

    def recall(self, query, k, rec):
        q = query[:QUERY_MAX]
        common = {"app_id": APP_ID, "project_id": PROJECT_ID, "query": q, "method": "keyword", "top_k": k}
        t0 = time.monotonic()
        cu, u = self._http("/api/v2/memory/search", {**common, "user_id": USER_ID, "include_profile": True}, timeout=120)
        ca, ag = self._http("/api/v2/memory/search", {**common, "agent_id": AGENT_ID}, timeout=120)
        dt = time.monotonic() - t0
        self.stats["search"].append(dt)
        u = (u or {}).get("data") or {}
        ag = (ag or {}).get("data") or {}
        if not hasattr(self, "_ep_cache") or self._ep_cache_n != self.stats["add"]:
            self._ep_cache = self._memcell_src(); self._ep_cache_n = self.stats["add"]
        ep2mc, mc = self._ep_cache
        out, unmapped = [], 0
        for p in u.get("profiles") or []:
            out.append({"text": json.dumps(p.get("profile_data"), ensure_ascii=False), "source": None, "kind": "profile"})
        for e in u.get("episodes") or []:
            facts = "; ".join(f.get("content", "") for f in (e.get("atomic_facts") or []) if f.get("content"))
            text = " — ".join(x for x in [e.get("subject"), e.get("summary"), e.get("episode"), f"Facts: {facts}" if facts else ""] if x)
            eid = e.get("id", "")
            key = eid.split("_ep_", 1)[-1] if "_ep_" in eid else eid
            srcs = mc.get(ep2mc.get("ep_" + key, ep2mc.get(key, "")), [])
            files = {s[0] for s in srcs}
            if srcs and len(files) == 1:
                src = f"{srcs[0][0]}#L{min(s[1] for s in srcs)}-L{max(s[2] for s in srcs)}"
            else:
                src, unmapped = None, unmapped + 1
            out.append({"text": text, "source": src, "kind": "episode", "score": e.get("score")})
        for c in ag.get("agent_cases") or []:
            out.append({"text": " — ".join(x for x in [f"Intent: {c.get('task_intent')}", f"Approach: {c.get('approach')}",
                        f"Insight: {c.get('key_insight')}" if c.get("key_insight") else ""] if x), "source": None, "kind": "agent_case"})
        for s in ag.get("agent_skills") or []:
            out.append({"text": f"{s.get('name')}: {s.get('description')} — {s.get('content')}", "source": None, "kind": "agent_skill"})
        rec.event("plugin.search", http=[cu, ca], latency_s=round(dt, 3), query_chars=len(q),
                  n={"profiles": len(u.get("profiles") or []), "episodes": len(u.get("episodes") or []),
                     "agent_cases": len(ag.get("agent_cases") or []), "agent_skills": len(ag.get("agent_skills") or [])},
                  episode_unmapped=unmapped, injected_chars=sum(len(o["text"]) for o in out))
        # 考场只认 text/source；把带出处的 episode 排前（插件 renderMemory 里 profile 在前，但 profile 无出处、反正被剔除）
        return [o for o in out if o["source"]] + [o for o in out if not o["source"]]

    # ------------------------------------------------------------ uninstall
    def uninstall(self, rec):
        rec.event("plugin.tokens", phase="total", **self.llm_totals())
        for name, p in (("server", self.server), ("proxy", self.proxy)):
            if p and p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGTERM)
                    p.wait(20)
                except Exception:  # noqa: BLE001
                    try:
                        os.killpg(p.pid, signal.SIGKILL)
                    except Exception:  # noqa: BLE001
                        pass
            rec.event("plugin.stop", what=name)
        # README 无卸载章节；按常识：pip uninstall everos（venv 里），记忆根 ~/.everos 是用户数据，不删、列为残留
        p = self._run(rec, "uninstall", "uv pip uninstall everos", timeout=120)
        residue = []
        for dp, dn, fn in os.walk(self.mroot):
            for n in fn:
                residue.append(os.path.relpath(os.path.join(dp, n), ROOT if self.state else self.base))
        return {"residue_paths": sorted(residue)[:400], "residue_count": len(residue), "pip_uninstall_rc": p.returncode,
                "flush_failed": self.stats.get("flush_failed", []),
                "note": "README/QUICKSTART 无卸载说明；记忆根（Markdown+SQLite+LanceDB+配置）保留。考场下记忆根在 runs/<run>/everos_state/root（持久盘，沙箱快照看不到，故在此自报）"}


EverOSPlugin = EverOS
