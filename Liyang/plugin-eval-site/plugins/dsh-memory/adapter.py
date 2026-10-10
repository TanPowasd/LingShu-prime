# -*- coding: utf-8 -*-
"""dsh-memory（灵枢官方记忆插件）适配器 —— 经 stdio MCP（JSON-RPC）接入考场。

接口：harness/adapter.py 固定契约 v0.1（Plugin.install / ingest / recall / uninstall）。

接法（只用插件作者推荐的正经路径，不调参）：
  · 大脑：`python3 -m md_cg.mcp_server`（README「其它 MCP 宿主 → 直接挂载大脑」），
    MDCG_MCP_SURFACE=full（插件自己的 DSH 运行时客户端也强制 full，见 src/lib/mdcg_client.ts:122）。
  · 写入通道：`cg(op=ingest, action=jsonl)` —— 插件自带的「会话文件增量摄取」设备驱动
    （md_cg/sources.py FileDispatcher → Ingestor），每轮对话一个节点、正文逐字保留、
    落层 contextual、密级按插件缺省 private。选它的理由见 README_适配器.md §2：
      - 这是插件为「把已有会话记录导入记忆」设计的入口（第三方复评 v7 也点名它是后向索引通道）；
      - `cg(op=write)` 的 text 类须 CCG 六要素，原始对话必被 REJECT——要过闸只能由我们替插件
        编六要素外壳，那等于替插件做内容加工（作弊）；
      - `mdcg_remember(gated=true)` 是 DSH 运行时逐条实时沉淀的通道（默认只记用户消息、
        过主动遗忘闸门），离线导入 8,146 轮不是它的设计场景；本适配器另附它的抽样测量（cost_probe.py）。
  · 召回通道：`mdcg_recall(query, k)` —— README 工具面「多路融合检索」与 FAQ「自动召回注入 →
    mdcg_recall」点名的入口；除 k 外全用缺省（budget_tokens=1200、max_item_tokens=250、
    fuzzy/semantic 关、causal/temporal 开）。返回的 content 原样作为 text（含插件自加的
    CCG 外壳行——那就是插件注入上下文的真实形态）。
  · 令牌：designer 角色、--clearance private、ops 在 README 原参数上**只加 ingest、session**。
    原因：会话摄取的缺省密级是 private，而 README 令牌命令签的是 internal ⇒ 全部事件被拒
    （录像 install S10/S11 实测）；非 designer 角色密级上限一律 internal（md_cg/tokens.py 头注），
    所以「导入会话史」这件事在插件现行权限模型下**只能用 designer**——这是权限面的扣分点，不是适配器的选择。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # 仓根，便于 import harness

from mcp_stdio import StdioMCP  # noqa: E402

try:
    from harness.adapter import InstallResult, Plugin  # noqa: E402
except Exception:  # harness 尚未落地时的后备（签名一致）
    import dataclasses

    @dataclasses.dataclass
    class InstallResult:  # type: ignore[no-redef]
        ok: bool
        steps: int
        errors: list = dataclasses.field(default_factory=list)

    class Plugin:  # type: ignore[no-redef]
        name = "base"
        version = "0"
        kind = "mcp-stdio"

REPO = "https://github.com/FuRongJun-1999/dsh-memory.git"
PINNED_SHA = "c8c3655234d57214ae990ab2c7590f7ba590d901"
TOKEN_RE = re.compile(r"mdcg1\.[A-Za-z0-9._\-]+")
OPS = "info,route,read,write,recent,goal,identity,whitebox,verify,ingest,session"
LAYERS = "knowledge,contextual,structural,self,goals,unresolved,rejected"


def _redact(s: str) -> str:
    return TOKEN_RE.sub("<REDACTED>", s or "")


def snapshot(*roots):
    out = {}
    for r in roots:
        if not os.path.exists(r):
            continue
        for dp, dn, fn in os.walk(r):
            for n in fn:
                p = os.path.join(dp, n)
                try:
                    st = os.lstat(p)
                    out[p] = st.st_size
                except OSError:
                    pass
    return out


class DshMemory(Plugin):
    name = "dsh-memory"
    version = PINNED_SHA[:12]
    kind = "mcp-stdio"

    def __init__(self, base: str = "/tmp/pes-dshm-run", sha: str = PINNED_SHA,
                 python: str = "/usr/local/bin/python3", recall_args: dict | None = None,
                 cache_dir: str | None = None, extra_ops: str = "", extra_env: dict | None = None):
        self.base = base
        self.sha = sha
        self.version = sha[:12]
        self.py_host = python
        self.home = os.path.join(base, "home")
        self.root = os.path.join(base, "root")          # MDCG_ROOT
        self.venv = os.path.join(base, "venv")
        self.work = os.path.join(base, "work")
        self.clone = os.path.join(self.work, "dsh-memory")
        self.secrets = os.path.join(base, "secrets")
        self.jsonl_dir = os.path.join(base, "ingest_jsonl")
        self.recall_args = dict(recall_args or {})      # 缺省空 = 全用插件缺省
        self.mcp: StdioMCP | None = None
        self.nid2src: dict[str, tuple] = {}
        self.stats = {"ingest": [], "recall": []}
        self._snap_before = None
        # 召回缓存（可选）：mdcg_recall 在同一库上对同一查询逐次结果一致（2026-10-10 实测 4 查询×3 轮全同，
        # 见 README_适配器.md §4），而 8,146 节点库上单次召回约 60s ⇒ 多种子重跑时检索结果按
        # (sha, 写入指纹, k, recall_args, query) 落盘复用；种子只影响生成器。缓存命中照样录像并带原始时延。
        self.cache_dir = cache_dir
        self.extra_env = dict(extra_env or {})   # 只给附录臂用（非缺省口径），主臂恒为空
        self.ops = OPS + ("," + extra_ops if extra_ops else "")   # 考卷 B 不加任何额外 op；只供旧账复测探针用
        self.ingest_fp = None

    # ------------------------------------------------------------------ util
    def _env(self, with_token=True):
        env = {"HOME": self.home, "PATH": f"{self.venv}/bin:/usr/local/bin:/usr/bin:/bin",
               "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
               "PYTHONPATH": self.clone, "MDCG_ROOT": self.root, "MDCG_MCP_SURFACE": "full"}
        env.update(self.extra_env)
        if with_token:
            tp = os.path.join(self.secrets, "designer.token")
            if os.path.exists(tp):
                env["MDCG_TOKEN"] = open(tp).read().strip()
        return env

    def _run(self, rec, cmd, cwd=None, timeout=600, step=None):
        rec.event("cmd.start", cmd=_redact(cmd), cwd=cwd, step=step)
        t0 = time.monotonic()
        p = subprocess.run(cmd, shell=True, cwd=cwd, env=self._env(with_token=False),
                           capture_output=True, text=True, timeout=timeout)
        rec.event("cmd.end", rc=p.returncode, stdout=_redact(p.stdout)[-8000:],
                  stderr=_redact(p.stderr)[-8000:], dur_s=round(time.monotonic() - t0, 3), step=step)
        return p

    # --------------------------------------------------------------- install
    def _bind_sandbox(self):
        """harness 运行器会在 install 前设 plugin.sandbox（harness/sandbox.py）：用它的 HOME/work/venv，
        MDCG_ROOT 与令牌目录也放进沙箱根，便于 harness 的快照 diff 一并看到。"""
        sbx = getattr(self, "sandbox", None)
        if sbx is None:
            return False
        self.base = str(sbx.root)
        self.home, self.work, self.venv = str(sbx.home), str(sbx.work), str(sbx.venv)
        self.root = os.path.join(self.base, "mdcg_root")
        self.clone = os.path.join(self.work, "dsh-memory")
        self.secrets = os.path.join(self.base, "secrets")
        self.jsonl_dir = os.path.join(self.base, "ingest_jsonl")
        return True

    def install(self, rec) -> InstallResult:
        errors, steps = [], 0
        if not self._bind_sandbox():
            if os.path.exists(self.base):
                shutil.rmtree(self.base)
        for d in (self.home, self.root, self.work, self.secrets, self.jsonl_dir):
            os.makedirs(d, exist_ok=True)
        os.chmod(self.secrets, 0o700)
        self._snap_before = snapshot(self.home, self.root, "/tmp/md_cg_servers")
        rec.event("plugin.install.begin", plugin=self.name, sha=self.sha, base=self.base,
                  HOME=self.home, MDCG_ROOT=self.root)
        plan = [
            ("venv", f"{self.py_host} -m venv {self.venv}", self.base),
            ("clone", f"git clone -q {REPO} {self.clone} && git -C {self.clone} checkout -q {self.sha} "
                      f"&& git -C {self.clone} log -1 --format=%H", self.base),
            ("selfcheck", "python3 -m md_cg.mcp_server --show-config", self.clone),
            ("token", "python3 -m md_cg.tokens issue --role designer --actor pes-dsh --clearance private "
                      f"--ops-allow {self.ops} --layers-allow {LAYERS} > {self.secrets}/designer.out 2>&1; "
                      f"echo rc=$?", self.clone),
        ]
        for name, cmd, cwd in plan:
            steps += 1
            p = self._run(rec, cmd, cwd=cwd, step=name)
            if p.returncode != 0:
                errors.append(f"{name}: rc={p.returncode} {_redact(p.stderr)[-300:]}")
                return InstallResult(False, steps, errors)
        txt = open(f"{self.secrets}/designer.out", encoding="utf-8").read()
        m = TOKEN_RE.search(txt)
        if not m:
            errors.append("token: 未取到令牌明文")
            return InstallResult(False, steps, errors)
        tp = os.path.join(self.secrets, "designer.token")
        with open(tp, "w") as f:
            f.write(m.group(0))
        os.chmod(tp, 0o600)
        os.remove(f"{self.secrets}/designer.out")
        info = json.loads(TOKEN_RE.sub("<REDACTED>", txt))
        rec.event("plugin.token", role=info.get("role"), clearance=info.get("clearance"),
                  ops_allow=info.get("ops_allow"), layers_allow=info.get("layers_allow"),
                  token="<REDACTED>", token_file=info.get("token_file"))
        steps += 1
        try:
            self._start(rec)
        except Exception as e:  # noqa: BLE001
            errors.append(f"mcp start: {e}")
            return InstallResult(False, steps, errors)
        return InstallResult(True, steps, errors)

    def _start(self, rec):
        t0 = time.monotonic()
        self.mcp = StdioMCP([f"{self.venv}/bin/python", "-m", "md_cg.mcp_server"], cwd=self.base,
                            env=self._env(), stderr_path=os.path.join(self.base, "mcp_stderr.log"))
        self.server_pid = self.mcp.p.pid
        init = self.mcp.initialize()
        tools = [t["name"] for t in self.mcp.request("tools/list")["tools"]]
        who, _, _ = self.mcp.call_tool("mdcg_whoami", {})
        pr = (who or {}).get("principal", {}) if isinstance(who, dict) else {}
        rec.event("mcp.ready", server=init.get("serverInfo"), n_tools=len(tools), tools=tools,
                  role=pr.get("role"), clearance=pr.get("clearance"), can_admin=pr.get("can_admin"),
                  dur_s=round(time.monotonic() - t0, 3))
        self.permissions = {
            "token_role": pr.get("role"), "clearance": pr.get("clearance"), "can_write": pr.get("can_write"),
            "can_admin": pr.get("can_admin"), "ops_allow": pr.get("ops_allow"), "layers_allow": pr.get("layers_allow"),
            "n_tools_exposed": len(tools),
            "why_not_minimal": "会话摄取缺省密级 private；非 designer 角色密级上限 internal ⇒ 导入会话史只能用 designer"
                               "（can_admin=true）。recorder 令牌实测 50/50 被拒（录像 install S11）。",
            "outside_sandbox_writes": ["/tmp/md_cg_servers/<pid>.json（服务自报文件，见 uninstall 残留）"]}

    # ---------------------------------------------------------------- ingest
    def ingest(self, sessions, rec) -> None:
        """sessions：harness 契约 list[{"session_id", "turns":[{idx, role, start_line, end_line, text}]}]。
        纯格式转换为插件的通用会话 JSONL（role/text/session/seq），再调 cg(op=ingest, action=jsonl)。"""
        tot_t = time.monotonic()
        h = hashlib.sha256()
        for s_ in sessions:
            h.update(s_["session_id"].encode())
            for t_ in s_["turns"]:
                h.update(f"{t_['start_line']}:{t_['end_line']}:{t_['role']}:".encode() + t_["text"].encode())
        self.ingest_fp = h.hexdigest()[:16]
        total_w = total_d = total_ev = 0
        for s in sessions:
            sid = s["session_id"]
            p = os.path.join(self.jsonl_dir, hashlib.sha1(sid.encode()).hexdigest()[:10] + ".jsonl")
            evs = []
            with open(p, "w", encoding="utf-8") as f:
                for t in s["turns"]:
                    ev = {"role": t["role"], "text": t["text"], "session": sid, "seq": int(t["start_line"])}
                    evs.append((sid, int(t["start_line"]), int(t["end_line"])))
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
            t0 = time.monotonic()
            payload, raw, is_err = self.mcp.call_tool("cg", {"op": "ingest", "action": "jsonl", "path": p},
                                                      timeout=3600)
            dt = round(time.monotonic() - t0, 3)
            if is_err or not isinstance(payload, dict):
                rec.event("plugin.ingest.error", session=sid, dur_s=dt, raw=_redact(raw)[:1500])
                continue
            ids = payload.get("ids") or []
            # ids 与写入事件同序（sources.Ingestor.ingest：逐条 append）；denied 时序列会错位 → 用节点 id 重算
            if payload.get("denied"):
                rec.event("plugin.ingest.denied", session=sid, denied=payload.get("denied"),
                          sample=payload.get("denied_events", [])[:3], last_error=payload.get("last_error"))
            key = payload.get("source") or ("jsonl:" + os.path.basename(p))
            for (sid_, a, b) in evs:
                nid = "src_%s_%s" % (hashlib.sha1(key.encode()).hexdigest()[:6],
                                     hashlib.sha1(f"{sid_}:{a}".encode()).hexdigest()[:10])
                self.nid2src[nid] = (sid_, a, b)
            hit = sum(1 for i in ids if i in self.nid2src)
            row = {"session": sid, "turns": len(evs), "new_events": payload.get("new_events"),
                   "written": payload.get("written"), "denied": payload.get("denied"),
                   "id_map_hit": f"{hit}/{len(ids)}", "dur_s": dt,
                   "chars": sum(len(t["text"]) for t in s["turns"])}
            self.stats["ingest"].append(row)
            rec.event("plugin.ingest", **row)
            total_w += payload.get("written") or 0
            total_d += payload.get("denied") or 0
            total_ev += len(evs)
        root_bytes = sum(snapshot(self.root).values())
        rec.event("plugin.ingest.done", sessions=len(sessions), events=total_ev, written=total_w,
                  denied=total_d, dur_s=round(time.monotonic() - tot_t, 3), root_bytes=root_bytes)

    # ---------------------------------------------------------------- recall
    def _cache_path(self, query, k):
        if not self.cache_dir or not self.ingest_fp:
            return None
        key = hashlib.sha256(json.dumps([self.sha, self.ingest_fp, int(k), self.recall_args, query],
                                        ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]
        return os.path.join(self.cache_dir, key + ".json")

    def recall(self, query: str, k: int, rec) -> list:
        cp = self._cache_path(query, k)
        if cp and os.path.exists(cp):
            c = json.load(open(cp, encoding="utf-8"))
            row = dict(c["row"], cached=True)
            self.stats["recall"].append(row)
            rec.event("plugin.recall", query=query[:300], sources=[x["source"] for x in c["hits"]], **row)
            return c["hits"]
        out = self._recall_live(query, k, rec)
        if cp and out is not None and self.stats["recall"] and not self.stats["recall"][-1].get("error"):
            os.makedirs(self.cache_dir, exist_ok=True)
            json.dump({"query": query, "k": k, "hits": out, "row": self.stats["recall"][-1]},
                      open(cp, "w", encoding="utf-8"), ensure_ascii=False)
        return out

    def _recall_live(self, query: str, k: int, rec) -> list:
        args = {"query": query, "k": int(k)}
        args.update(self.recall_args)
        t0 = time.monotonic()
        payload, raw, is_err = self.mcp.call_tool("mdcg_recall", args, timeout=900)
        dt = round(time.monotonic() - t0, 3)
        if is_err or not isinstance(payload, dict):
            rec.event("plugin.recall.error", query=query[:200], dur_s=dt, raw=_redact(raw)[:1500])
            self.stats["recall"].append({"dur_s": dt, "error": True})
            return []
        out = []
        for it in payload.get("pack") or []:
            nid = it.get("id")
            src = self.nid2src.get(nid)
            out.append({"text": it.get("content") or "",
                        "source": f"{src[0]}#L{src[1]}-L{src[2]}" if src else None,
                        "node_id": nid, "tokens": it.get("tokens"), "truncated": bool(it.get("truncated")),
                        "state": it.get("state")})
        row = {"dur_s": dt, "k": k, "n": len(out), "tokens_used": payload.get("tokens_used"),
               "budget": payload.get("budget"), "skipped": len(payload.get("skipped") or []),
               "chars": sum(len(x["text"]) for x in out),
               "unmapped": sum(1 for x in out if not x["source"])}
        self.stats["recall"].append(row)
        rec.event("plugin.recall", query=query[:300], sources=[x["source"] for x in out], **row)
        return out

    # ------------------------------------------------------------- uninstall
    def uninstall(self, rec) -> dict:
        """README 没有卸载章节（录像 install 记为文档缺口）。按通用 MCP 宿主的常识卸载：
        停服务 → 删 clone 与 venv（宿主配置里的 mcpServers 片段由宿主侧删除，本考场未写入宿主配置）。
        **不删** MDCG_ROOT（用户记忆数据，正常卸载不应替用户删）——残留 diff 里单列。"""
        if self.mcp:
            self.mcp.close()
            self.mcp = None
        for d in (self.clone, self.venv):
            shutil.rmtree(d, ignore_errors=True)
            rec.event("plugin.uninstall.rm", path=d)
        pidf = f"/tmp/md_cg_servers/{getattr(self, 'server_pid', 'x')}.json"
        rec.event("plugin.uninstall.outside", server_selfreport=pidf, exists_after_stop=os.path.exists(pidf))
        after = snapshot(self.home, self.root, "/tmp/md_cg_servers")
        before = self._snap_before or {}
        new = sorted(set(after) - set(before))
        groups = {"HOME": [p for p in new if p.startswith(self.home)],
                  "MDCG_ROOT": [p for p in new if p.startswith(self.root)],
                  "/tmp/md_cg_servers": [p for p in new if p.startswith("/tmp/md_cg_servers")]}
        summary = {g: {"files": len(v), "bytes": sum(after[p] for p in v)} for g, v in groups.items()}
        rec.event("plugin.uninstall.residue", summary=summary,
                  home_files=[p.replace(self.home, "~") for p in groups["HOME"]][:200],
                  tmp_files=groups["/tmp/md_cg_servers"][:50])
        return {"residue_paths": new, "summary": summary}


# harness/run.py 约定的类名
DshMemoryPlugin = DshMemory


class DshMemoryJaccardPlugin(DshMemory):
    """**附录臂，不进结论**：插件缺省词法打分是 legacy（|q∩d|/|q|，源码注释自认"长文档天然占优"），
    而作者自己的评测侧显式注入 jaccard（md_cg/mdcg.py:517-539 注释）。本臂只把 MDCG_SCORE_MODE=jaccard
    这一个插件自带开关打开，供作者申诉/对照参考；主结论只认缺省口径。"""
    name = "dsh-memory[jaccard-附录]"

    def __init__(self, **kw):
        super().__init__(extra_env={"MDCG_SCORE_MODE": "jaccard"}, **kw)
