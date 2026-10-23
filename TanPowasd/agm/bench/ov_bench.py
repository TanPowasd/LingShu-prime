# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""PREREG_ov.md（27e19b8）读数脚本：OpenViking v0.5.1.1 vs TE 检索层对照，LoCoMo dev 231 题。

许可边界：本文件不 import 任何 OpenViking（AGPL-3.0）模块，只经 HTTP REST 与仓外 `openviking-server` 交互；
OpenViking 装在 <仓外>/ovlib，配置与数据目录都在 <仓外>/ov_runs，不入仓。

子命令（全部 PYTHONUTF8=1 python -X utf8 agm/bench/ov_bench.py <子命令> ...）：
  embed  --port 8611                 本机 OpenAI 兼容 /v1/embeddings（fastembed BAAI/bge-small-en-v1.5，384 维）
  meter  --port 8612 --mode live|cache|zero --cap 1250 --cache <仓外>/ov_cache
                                     计量代理（PREREG_ov §4.3）：只转发 chat/completions 到 api.cline.bot，
                                     固定 model；按「请求 messages 等全文」sha256 去重缓存；逐次记 token；
                                     上游尝试数（含失败/重试）累计到 --cap 即拒绝（fail-closed）。
                                     live=缓存未命中才上游；cache=只读缓存，未命中报错（OV-L/c 用）；
                                     zero=任何请求都报错并计数（OV-E 用，验证 0 调用）。
                                     key 不经本脚本：请求不带 Authorization，由运行环境在出网时注入；本脚本不读、不写任何 key。
  conf   --arm ov-e|ov-l-s|ov-l-c --root <仓外>/ov_runs   生成该臂 ov.conf（嵌入/VLM 都指向本机，api_key 用假值）
  run    --arm ... --server http://127.0.0.1:19xx --out <json>   写入 + find() 检索 + 逐题 r@k
  agg    --te <json> --arm-json name=<json> ... --out <md>  汇总表 + 对 TE 的胜负/符号检验 + OV-L/c≡OV-E 自检
金标、切分与 agm/lex/bench_cc.py locomo 分支逐字同口径（extract.items、evidence→dia_id、qid=f"{sid}_{qi}"）。"""
import argparse, base64, hashlib, io, json, math, os, pathlib, re, sys, threading, time, urllib.error, urllib.request, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "confluence"), str(HERE.parent / "tricue")]

UPSTREAM = "https://api.cline.bot/api/v1/chat/completions"
MODEL = "cline-pass/deepseek-v4.1-flash"
DUMMY = "GOV-IMPL-DUMMY-KEY"
EMB_MODEL = "BAAI/bge-small-en-v1.5"
KS = (5, 10, 25)


# ───────────────────────── 本机嵌入服务 ─────────────────────────
def cmd_embed(a):
    from fastembed import TextEmbedding
    m = TextEmbedding(EMB_MODEL, cache_dir=a.hf)
    lock = threading.Lock()
    stat = {"n_req": 0, "n_txt": 0}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *x):
            pass

        def _send(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def do_GET(self):
            if self.path.rstrip("/").endswith("/models"):
                return self._send(200, {"object": "list", "data": [{"id": EMB_MODEL, "object": "model"}]})
            if self.path.rstrip("/").endswith("/stat"):
                return self._send(200, stat)
            self._send(404, {"error": "not found"})

        def do_POST(self):
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            inp = d.get("input", [])
            if isinstance(inp, str):
                inp = [inp]
            if inp and not isinstance(inp[0], str):   # 存疑：token id 输入不支持，显式报错不降级
                return self._send(400, {"error": {"message": "only string inputs supported"}})
            with lock:
                vs = [v.tolist() for v in m.embed(list(inp))]
                stat["n_req"] += 1; stat["n_txt"] += len(inp)
            b64 = d.get("encoding_format") == "base64"
            import struct
            data = [{"object": "embedding", "index": i,
                     "embedding": base64.b64encode(struct.pack(f"<{len(v)}f", *v)).decode() if b64 else v}
                    for i, v in enumerate(vs)]
            n = sum(len(t) // 4 for t in inp)
            self._send(200, {"object": "list", "data": data, "model": EMB_MODEL,
                             "usage": {"prompt_tokens": n, "total_tokens": n}})

    print(f"embed {EMB_MODEL} on 127.0.0.1:{a.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


# ───────────────────────── 计量代理 ─────────────────────────
def prompt_key(d):
    """缓存键：除 model/stream 外的全部请求体（messages、temperature、tools…）规范化后 sha256。"""
    k = {x: d[x] for x in sorted(d) if x not in ("model", "stream", "stream_options", "user")}
    return hashlib.sha256(json.dumps(k, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def kind_of(d):
    t = json.dumps(d.get("messages", []), ensure_ascii=False)[:4000].lower()
    return "overview" if "overview" in t or "directory" in t else ("file_summary" if "summary" in t else "other")


def _durable_write(p, text):
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text); f.flush(); os.fsync(f.fileno())
    tmp.replace(p)


class Meter:
    def __init__(self, a):
        self.mode, self.cap = a.mode, a.cap
        self.dir = pathlib.Path(a.cache); (self.dir / "resp").mkdir(parents=True, exist_ok=True)
        self.state_p = self.dir / "meter_state.json"
        self.state = json.loads(self.state_p.read_text()) if self.state_p.exists() else \
            {"upstream_attempts": 0, "upstream_ok": 0, "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0}
        if a.carry:   # 显式结转此前已发生但记录丢失的上游尝试（保守上界），计入硬上限
            self.state["upstream_attempts"] = max(self.state["upstream_attempts"], 0) + a.carry
            self.state.setdefault("carried_unrecorded_attempts", 0)
            self.state["carried_unrecorded_attempts"] += a.carry
            self.save()
        self.run = {"mode": a.mode, "requests": 0, "cache_hits": 0, "cache_miss_err": 0, "refused_cap": 0, "zero_refused": 0}
        self.lock = threading.Lock()
        self.sem = threading.Semaphore(a.conc)
        self.min_gap, self.last = a.min_gap, 0.0
        self.inflight = {}
        self.exhausted = None

    def save(self):   # fsync：沙箱重启时网络盘上未落盘的写会丢（2026-10-24 实测丢过一次），计数必须先落盘再上游
        _durable_write(self.state_p, json.dumps(self.state, indent=1))

    def log(self, row):
        with open(self.dir / "calls.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n"); f.flush(); os.fsync(f.fileno())

    def upstream(self, d):
        body = dict(d); body["model"] = MODEL; body.pop("stream", None); body.pop("stream_options", None)
        raw = json.dumps(body).encode()
        for k in range(6):
            with self.lock:
                if self.state["upstream_attempts"] >= self.cap:
                    self.run["refused_cap"] += 1
                    raise RuntimeError(f"meter cap {self.cap} reached (fail-closed)")
                if self.exhausted:
                    raise RuntimeError(f"upstream quota exhausted: {self.exhausted}")
                self.state["upstream_attempts"] += 1; self.save()
            with self.sem:
                with self.lock:
                    w = self.last + self.min_gap - time.time()
                    self.last = max(time.time(), self.last + self.min_gap)
                if w > 0:
                    time.sleep(w)
                t0 = time.time()
                try:
                    req = urllib.request.Request(UPSTREAM, data=raw, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=600) as r:
                        resp = json.loads(r.read())
                    code, err = 200, None
                except urllib.error.HTTPError as e:
                    code, err, resp = e.code, e.read()[:500].decode("utf-8", "replace"), None
                except Exception as e:  # noqa: BLE001  网络错误：记录并重试，计入尝试数
                    code, err, resp = -1, repr(e)[:300], None
            ms = int((time.time() - t0) * 1000)
            if resp is not None:
                resp = resp.get("data", resp) if isinstance(resp.get("data"), dict) else resp
                try:
                    txt = resp["choices"][0]["message"]["content"]
                except Exception:  # noqa: BLE001
                    txt = None
                u = resp.get("usage") or {}
                rt = (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
                with self.lock:
                    self.state["prompt_tokens"] += u.get("prompt_tokens", 0) or 0
                    self.state["completion_tokens"] += u.get("completion_tokens", 0) or 0
                    self.state["reasoning_tokens"] += rt
                    if txt and txt.strip():
                        self.state["upstream_ok"] += 1
                    self.save()
                self.log({"t": time.time(), "attempt": k, "code": 200, "ms": ms, "empty": not (txt and txt.strip()), "req_keys": sorted(d),
                          "pt": u.get("prompt_tokens"), "ct": u.get("completion_tokens"), "rt": rt, "kind": kind_of(d)})
                if txt and txt.strip():
                    return resp
                time.sleep(3)
                continue
            self.log({"t": time.time(), "attempt": k, "code": code, "ms": ms, "err": err, "kind": kind_of(d)})
            low = (err or "").lower()
            if code in (401, 402, 403) or "insufficient" in low or "quota" in low or ("limit" in low and code != 429):
                with self.lock:
                    self.exhausted = f"{code} {err[:200] if err else ''}"
                raise RuntimeError(f"upstream refused: {code} {err}")
            time.sleep(30 if code == 429 else 5 * (k + 1))
        raise RuntimeError("upstream failed after retries")

    def handle(self, d):
        key = prompt_key(d)
        p = self.dir / "resp" / f"{key}.json"
        with self.lock:
            self.run["requests"] += 1
        if self.mode == "zero":
            with self.lock:
                self.run["zero_refused"] += 1
            self.log({"t": time.time(), "code": "zero_refused", "kind": kind_of(d), "key": key[:12]})
            raise RuntimeError("meter in zero mode: no LLM calls allowed for this arm")
        if p.exists():
            with self.lock:
                self.run["cache_hits"] += 1
            return json.loads(p.read_text())
        if self.mode == "cache":
            with self.lock:
                self.run["cache_miss_err"] += 1
            self.log({"t": time.time(), "code": "cache_miss", "kind": kind_of(d), "key": key[:12]})
            raise RuntimeError("meter cache-only: miss")
        with self.lock:   # 同一 prompt 并发去重
            ev = self.inflight.get(key)
            mine = ev is None
            if mine:
                ev = self.inflight[key] = threading.Event()
        if not mine:
            ev.wait()
            if p.exists():
                with self.lock:
                    self.run["cache_hits"] += 1
                return json.loads(p.read_text())
            raise RuntimeError("concurrent duplicate failed")
        try:
            resp = self.upstream(d)
            _durable_write(p, json.dumps(resp, ensure_ascii=False))
            return resp
        finally:
            with self.lock:
                self.inflight.pop(key, None)
            ev.set()


def cmd_meter(a):
    M = Meter(a)

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *x):
            pass

        def _send(self, code, obj, ctype="application/json"):
            b = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code); self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def do_GET(self):
            if self.path.rstrip("/").endswith("/stat"):
                with M.lock:
                    return self._send(200, {"state": M.state, "run": M.run, "cap": M.cap, "exhausted": M.exhausted})
            if self.path.rstrip("/").endswith("/models"):
                return self._send(200, {"object": "list", "data": [{"id": MODEL, "object": "model"}]})
            self._send(404, {"error": {"message": "not found"}})

        def do_POST(self):
            d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if not self.path.rstrip("/").endswith("/chat/completions"):
                return self._send(404, {"error": {"message": "meter forwards chat/completions only"}})
            try:
                resp = M.handle(d)
            except Exception as e:  # noqa: BLE001  fail-closed：显式错误返回给 OV（OV 侧会记 VLM 失败）
                return self._send(503, {"error": {"message": str(e), "type": "meter_refused"}})
            if d.get("stream"):
                c = resp["choices"][0]["message"].get("content", "")
                ch = {"id": resp.get("id", "m"), "object": "chat.completion.chunk", "created": int(time.time()), "model": MODEL,
                      "choices": [{"index": 0, "delta": {"role": "assistant", "content": c}, "finish_reason": None}]}
                end = dict(ch, choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}], usage=resp.get("usage"))
                b = f"data: {json.dumps(ch)}\n\ndata: {json.dumps(end)}\n\ndata: [DONE]\n\n".encode()
                return self._send(200, b, "text/event-stream")
            self._send(200, resp)

    print(f"meter mode={a.mode} cap={a.cap} on 127.0.0.1:{a.port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


# ───────────────────────── ov.conf ─────────────────────────
ARMS = {   # PREREG_ov §3：只改这三个开关，其余全用 OV 默认
    "ov-e": {"text_source": "content_only", "processing_mode": "vectors_only", "meter": 8613},
    "ov-l-s": {"text_source": "summary_first", "processing_mode": "semantic_and_vectors", "meter": 8612},
    "ov-l-c": {"text_source": "content_only", "processing_mode": "semantic_and_vectors", "meter": 8614},
}
PORTS = {"ov-e": 19331, "ov-l-s": 19332, "ov-l-c": 19333}


def cmd_conf(a):
    c = ARMS[a.arm]
    root = pathlib.Path(a.root) / a.arm
    (root / "data").mkdir(parents=True, exist_ok=True)
    conf = {
        "server": {"host": "127.0.0.1", "port": PORTS[a.arm], "root_api_key": None},
        "storage": {"workspace": str(root / "data")},
        "embedding": {"dense": {"provider": "openai", "model": EMB_MODEL, "api_key": DUMMY,
                                "api_base": f"http://127.0.0.1:{a.embed_port}/v1", "dimension": 384, "input": "text"},
                      "text_source": c["text_source"]},
        "vlm": {"provider": "openai", "model": MODEL, "api_key": DUMMY, "api_base": f"http://127.0.0.1:{c['meter']}/v1",
                "temperature": 0.0, "max_concurrent": 2},
        "encryption": {"enabled": False},
        "log": {"level": "INFO", "output": "stdout"},
    }
    (root / "ov.conf").write_text(json.dumps(conf, indent=1))
    print(root / "ov.conf")


# ───────────────────────── 数据（与 bench_cc.py locomo 同口径） ─────────────────────────
def locomo_items(split):
    import extract as X
    out = []
    for it in X.items(split):
        idx = {d: i for i, d in enumerate(it["ids"])}
        qs = []
        for qi, q in enumerate(it["qa"]):
            ev = {idx[p.strip()] for e in q.get("evidence", []) for p in str(e).replace(";", ",").split(",") if p.strip() in idx}
            if ev:
                qs.append({"qid": f"{it['sid']}_{qi}", "type": str(q.get("category")), "q": q["question"], "gold": sorted(ev)})
        out.append({"sid": it["sid"], "turns": it["turns"], "ids": it["ids"], "qs": qs})
    return out


def fname(dia):
    """DEVIATION D1（PREREG_ov §8）：扩展名 .txt → .log。.txt 走 OV TextParser，被包成「每轮一个目录 + 同名 .md」，
    会多出 1 058 个目录概览调用（≈2 170 次 > 硬上限 1 250）；.log 走 direct 写入，结构保持 <sid>/s<k>/<dia>.log，
    且摘要提示词正是预注册引用的 semantic.file_summary。内容逐字不变。"""
    return dia.replace(":", "_") + ".log"


def score(rank, gold):   # = agm/bench/lme_zerokey.py:score
    gold = set(gold)
    x = {f"r@{k}": len(gold & set(rank[:k])) / len(gold) for k in KS}
    x["hit@10"] = float(bool(gold & set(rank[:10])))
    return x


# ───────────────────────── OV REST 客户端 ─────────────────────────
def http(method, url, body=None, timeout=60, files=None):
    if files:
        bnd = "----ovbench" + hashlib.md5(str(time.time()).encode()).hexdigest()
        parts = b""
        for name, (fn, data) in files.items():
            parts += (f"--{bnd}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{fn}\"\r\n"
                      "Content-Type: application/octet-stream\r\n\r\n").encode() + data + b"\r\n"
        parts += f"--{bnd}--\r\n".encode()
        req = urllib.request.Request(url, data=parts, method=method, headers={"Content-Type": f"multipart/form-data; boundary={bnd}"})
    else:
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {url} -> {e.code} {e.read()[:800].decode('utf-8', 'replace')}") from None


def ingest(srv, it, mode, work):
    """一段对话 = 一个资源根 viking://resources/<sid>；会话一子目录 s<k>；每轮一文件「说话人: 原文」。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d, t in zip(it["ids"], it["turns"]):
            s = int(d.split(":")[0].lstrip("D"))
            z.writestr(f"s{s}/{fname(d)}", t)
    tid = http("POST", f"{srv}/api/v1/resources/temp_upload", files={"file": (f"{it['sid']}.zip", buf.getvalue())})["result"]["temp_file_id"]
    t0 = time.time()
    r = http("POST", f"{srv}/api/v1/resources", {"temp_file_id": tid, "source_name": it["sid"], "to": f"viking://resources/{it['sid']}",
                                                  "wait": True, "processing_mode": mode}, timeout=6 * 3600)
    return time.time() - t0, r


def find(srv, q, root, limit):
    r = http("POST", f"{srv}/api/v1/search/find", {"query": q, "target_uri": root, "limit": limit}, timeout=300)
    res = r.get("result", {})
    recs = []
    for key in ("resources", "memories", "skills"):
        recs += res.get(key, []) or []
    return recs


def l2_rank(recs, fmap):
    """L2 过滤：丢弃目录记录，按 URI 去重，逆映射为轮下标。返回（轮下标序列，目录记录数，无法映射的文件数）。"""
    seen, rank, ndir, nunk = set(), [], 0, 0
    for x in sorted(recs, key=lambda x: -(x.get("score") or 0)):
        u = x.get("uri", "")
        base = u.rstrip("/").rsplit("/", 1)[-1]
        if not base.endswith(".log"):
            ndir += 1
            continue
        if u in seen:
            continue
        seen.add(u)
        if base in fmap:
            rank.append(fmap[base])
        else:
            nunk += 1
    out, s2 = [], set()
    for t in rank:
        if t not in s2:
            s2.add(t); out.append(t)
    return out, ndir, nunk


def cmd_run(a):
    c = ARMS[a.arm]
    srv = a.server or f"http://127.0.0.1:{PORTS[a.arm]}"
    items = locomo_items(a.split)
    stp = pathlib.Path(a.out + ".state.json")
    st = json.loads(stp.read_text()) if stp.exists() else {"ingest": {}, "per": {}}
    for it in items:
        if it["sid"] in st["ingest"]:
            continue
        secs, r = ingest(srv, it, c["processing_mode"], None)
        st["ingest"][it["sid"]] = {"secs": secs, "resp": r.get("result", r)}
        stp.write_text(json.dumps(st, ensure_ascii=False))
        print(it["sid"], "ingest", f"{secs:.0f}s", flush=True)
    if a.ingest_only:
        return
    for it in items:
        fmap = {fname(d): i for i, d in enumerate(it["ids"])}
        root = f"viking://resources/{it['sid']}"
        for q in it["qs"]:
            if q["qid"] in st["per"]:
                continue
            lim, t0 = 50, time.time()
            while True:
                recs = find(srv, q["q"], root, lim)
                rank, ndir, nunk = l2_rank(recs, fmap)
                if len(rank) >= 25 or lim >= 400 or len(recs) < lim:
                    break
                lim *= 2
            ms = (time.time() - t0) * 1000
            st["per"][q["qid"]] = {"qid": q["qid"], "type": q["type"], "ms": ms, "limit": lim, "n_rec": len(recs), "n_dir": ndir,
                                   "n_unmapped": nunk, "rank": rank[:50], "gold": q["gold"], "s": score(rank, q["gold"]),
                                   "raw": [[x.get("uri", "").replace(root, "", 1), x.get("level"), round(x.get("score") or 0, 5)] for x in recs]}
        stp.write_text(json.dumps(st, ensure_ascii=False))
        print(it["sid"], "queried", len(st["per"]), flush=True)
    per = [st["per"][q["qid"]] for it in items for q in it["qs"]]
    json.dump({"meta": {"arm": a.arm, "split": a.split, "n": len(per), "ov": "0.5.1.1", "embed": EMB_MODEL, **{k: v for k, v in c.items() if k != "meter"},
                        "ingest_secs": {k: v["secs"] for k, v in st["ingest"].items()}}, "per": per},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(a.out, len(per))


# ───────────────────────── 汇总 ─────────────────────────
def sign_p(w, l):
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n * 2
    return min(1.0, p)


def dir_expand(raw, fmap):
    """附加报告（PREREG_ov §3，不作主读数）：按分数序遍历；文件记录照常；会话目录记录（/s<k>/ 下的 .overview/.abstract 或目录本身）
    命中时，把本次返回里该会话的文件记录按其自身分数插在此处。根/父目录记录忽略。只用 find 已返回的记录（推断：近似）。"""
    out, seen = [], set()
    files = [(u, sc) for u, lv, sc in raw if u.endswith(".log")]
    for u, lv, sc in sorted(raw, key=lambda x: -x[2]):
        if u.endswith(".log"):
            group = [u]
        else:
            m = re.match(r"^/(s\d+)(/|$)", u)
            if not m:
                continue
            group = [f for f, _ in sorted(files, key=lambda x: -x[1]) if f.startswith(f"/{m.group(1)}/")]
        for f in group:
            t = fmap.get(f.rsplit("/", 1)[-1])
            if t is not None and t not in seen:
                seen.add(t); out.append(t)
    return out


def cmd_agg(a):
    te = json.load(open(a.te, encoding="utf-8"))
    te_per = {p["qid"]: p["arms"]["TE"] for p in te["per"]}
    rows, out = [], {"te_n": len(te_per), "arms": {}}
    means = lambda xs, k: sum(x[k] for x in xs) / len(xs)
    tv = list(te_per.values())
    te_ms = (te["meta"].get("rank_secs") or {}).get("TE")
    te_ms = f"{te_ms * 1000 / len(tv):.1f}（仅 TE 树排序段累计；见正文）" if te_ms is not None else "存疑"
    rows.append(("TE", len(tv), means(tv, "r@5"), means(tv, "r@10"), means(tv, "r@25"), "—", "—", te_ms))
    arms = {}
    for spec in a.arm_json:
        name, p = spec.split("=", 1)
        arms[name] = json.load(open(p, encoding="utf-8"))
    for name, d in arms.items():
        per = d["per"]
        assert {x["qid"] for x in per} == set(te_per), f"{name}: qid set differs from TE"
        w = sum(x["s"]["r@10"] > te_per[x["qid"]]["r@10"] for x in per)
        l = sum(x["s"]["r@10"] < te_per[x["qid"]]["r@10"] for x in per)
        ss = [x["s"] for x in per]
        ms = sum(x["ms"] for x in per) / len(per)
        rows.append((name, len(per), means(ss, "r@5"), means(ss, "r@10"), means(ss, "r@25"), f"{w}/{l}", f"{sign_p(w, l):.3g}", f"{ms:.1f}"))
        out["arms"][name] = {"n": len(per), "r@5": means(ss, "r@5"), "r@10": means(ss, "r@10"), "r@25": means(ss, "r@25"),
                             "hit@10": means(ss, "hit@10"), "win_vs_TE": w, "loss_vs_TE": l, "sign_p": sign_p(w, l), "ms_per_q": ms,
                             "ingest_secs_total": sum(d["meta"]["ingest_secs"].values()), "ingest_secs": d["meta"]["ingest_secs"],
                             "mean_dir_records": sum(x["n_dir"] for x in per) / len(per), "unmapped": sum(x["n_unmapped"] for x in per),
                             "short_rank(<25)": sum(len(x["rank"]) < 25 for x in per)}
    import extract as X
    fmaps = {it["sid"]: {fname(d): i for i, d in enumerate(it["ids"])} for it in X.items("dev")}
    for name, d in arms.items():
        if all("raw" in x for x in d["per"]):
            ex = [score(dir_expand(x["raw"], fmaps[x["qid"].rsplit("_", 1)[0]]), x["gold"]) for x in d["per"]]
            w = sum(e["r@10"] > te_per[x["qid"]]["r@10"] for e, x in zip(ex, d["per"]))
            l = sum(e["r@10"] < te_per[x["qid"]]["r@10"] for e, x in zip(ex, d["per"]))
            out["arms"][name]["dir_expand"] = {k: means(ex, k) for k in ("r@5", "r@10", "r@25")} | {"win_vs_TE": w, "loss_vs_TE": l, "sign_p": sign_p(w, l)}
    if "OV-L/c" in arms and "OV-E" in arms:
        A = {x["qid"]: x["rank"] for x in arms["OV-L/c"]["per"]}; B = {x["qid"]: x["rank"] for x in arms["OV-E"]["per"]}
        same50 = sum(A[q] == B[q] for q in A); same10 = sum(A[q][:10] == B[q][:10] for q in A)
        out["selfcheck_OVLc_vs_OVE"] = {"identical_rank50": same50, "identical_top10": same10, "n": len(A)}
    out["te_meta"] = te["meta"]
    md = ["| 臂 | n | r@5 | r@10（主） | r@25 | r@10 胜/负 vs TE | 符号检验 p | ms/题 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        md.append("| " + " | ".join([r[0], str(r[1]), f"{r[2]:.3f}", f"{r[3]:.3f}", f"{r[4]:.3f}", r[5], r[6], str(r[7])]) + " |")
    pathlib.Path(a.out).write_text("\n".join(md) + "\n", encoding="utf-8")
    json.dump(out, open(a.out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n".join(md)); print(json.dumps({k: v for k, v in out.items() if k != "te_meta"}, ensure_ascii=False, indent=1)[:3000])


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    e = sp.add_parser("embed"); e.add_argument("--port", type=int, default=8611); e.add_argument("--hf", default=os.environ.get("HF_HOME", ""))
    m = sp.add_parser("meter"); m.add_argument("--port", type=int, required=True); m.add_argument("--mode", choices=["live", "cache", "zero"], required=True)
    m.add_argument("--cap", type=int, default=0); m.add_argument("--cache", required=True)
    m.add_argument("--carry", type=int, default=0, help="结转记录丢失的上游尝试数（保守上界）")
    m.add_argument("--conc", type=int, default=2); m.add_argument("--min-gap", type=float, default=5.0)
    c = sp.add_parser("conf"); c.add_argument("--arm", choices=list(ARMS), required=True); c.add_argument("--root", required=True)
    c.add_argument("--embed-port", type=int, default=8611)
    r = sp.add_parser("run"); r.add_argument("--arm", choices=list(ARMS), required=True); r.add_argument("--server")
    r.add_argument("--split", default="dev"); r.add_argument("--out", required=True); r.add_argument("--ingest-only", action="store_true")
    g = sp.add_parser("agg"); g.add_argument("--te", required=True); g.add_argument("--arm-json", nargs="+", required=True)
    g.add_argument("--out", required=True); g.add_argument("--out-json", required=True)
    a = ap.parse_args()
    {"embed": cmd_embed, "meter": cmd_meter, "conf": cmd_conf, "run": cmd_run, "agg": cmd_agg}[a.cmd](a)


if __name__ == "__main__":
    main()
