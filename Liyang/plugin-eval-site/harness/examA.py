"""考卷 A：hive-memory-bench 长文章理解（《蜂巢世界漫游指南》23 章，184 题）。

只判**主轮 92 题**（答案键公开于 hmb/cards/）；**干预轮 92 题答案键不公开 ⇒ 不可判、不作答、不出分**（如实标注）。

口径一律取上游，不自编、不改题：
- 作答契约：逐字取 `questions/作答契约.md` 主轮段（两条 `---` 之间）；
- 规则层：直接 import 上游 `judge.py` 的 `judge(card, resp, idx)`（依据轴／排除轴／诚实轴／外源轴／禁编造轴／L2 依据契合降级）；
- 语义层：上游 `semantic.py` 的判官 prompt（semantic-v0.1）与请求文件版式原样生成；finalize 的 span 机械校验与
  覆盖率算法照抄（strict 1.0 / paraphrase 0.7、≥0.7 pass）；L2 依据契合判官用上游 PROMPT_CITE（cite-v0.3）；
- 路由照 `score_sut.py report`：结构违规/空答 → fail（判官不改）；规则层 pass 且无降级 → pass；
  有降级 → L2 判官（仅 `cite` 类降级可撤销）→ 未撤销则交语义判官；其余 review/fail（非结构）→ 语义判官终裁；
- 判官协议（`docs/判分可靠性_v1.0.md`／`judge_audit.py`）：≥2 名判官（两个独立 flash 实例）、同材料同判据、盲混、
  掺分层锚且**锚先自证**（正确率 − 多数类基线 ≥ 15pp；本站另加正确率 ≥ 90%）；一致率 同分 ≥ 0.8 或 κ ≥ 0.6 ⇒ 可报值；
  任一判官不合格 ⇒ 整批作废重批（最多 3 次）；聚合：两判官覆盖率分取均值（§四「达标 ⇒ 取均值」）。

本站做法（如实声明，与上游外测不同处）：
- 被测方不是"读全书的模型"，而是"同一生成器 + 插件交来的材料"：契约里的「正文」段换成插件检索返回的片段
  （底子臂 A_null：无材料＝闭卷）。三臂除【正文】段外逐字相同；
- 检索 k=10（上游记忆系统对比口径）；材料上限 12,000 字符/题（沿用考卷 B）；查询＝题面原文；
- 语料切分：每章一个 Session（session_id＝cid），每个非空自然段一个 Turn（行号＝该章 text 按 \\n 切分的行号）；
  source＝`<cid>#L<s>-L<e>`；不给 source 或 cid 不存在的条目剔除（SPEC §2「可回源」硬要求）。

  python -m harness.examA --plugin null --seeds 1,2,3 --out runs/A_null
  python -m harness.examA --plugin bm25 --seeds 1,2,3 --out runs/A_bm25
  python -m harness.examA --plugin plugins/dsh-memory/adapter.py:DshMemoryPlugin --seeds 1,2,3 --out runs/A_dsh
  python -m harness.compare --base runs/A_null --plug runs/A_dsh --out reports/A_dsh_vs_null   # compare 自动识别考卷 A
"""
from __future__ import annotations
import argparse, hashlib, importlib, json, math, os, random, re, statistics, sys, threading, time, traceback
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from . import llm
from .adapter import parse_source
from .examB import assemble_material, extract_json
from .plugins_builtin import BM25Plugin, NullPlugin
from .recorder import Recorder, cite, load_events, render_timeline, validate_report
from .sandbox import Sandbox

HMB = Path(os.environ.get("PES_HMB", "/workspace/work/ls/hmb"))
EXAM_ID = "A/hmb-main92 v1.0"
DEFAULT_K = 10
MATERIAL_CAP = 12000
GEN_TEMPERATURE = 0.7
GEN_MAX_TOKENS = 2000
JUDGE_MAX_TOKENS = 1500
ANCHOR_SEED = 20261006
N_SEM_ANCHORS = (8, 8)     # 正锚（该卡要点原文当答案 → 应 pass）／跨卡负锚（他卡要点 → 应 fail）
N_CITE_ANCHORS = (4, 4)    # 依据契合锚：本卡认可依据 → 应 fit ／ 他卡依据 → 应非 fit
GATE = {"anchor_acc_min": 0.90, "anchor_margin_pp_min": 15.0, "agree_min": 0.80, "kappa_min": 0.60, "max_attempts": 3}

_J = _S = None


def set_root(p):
    global HMB, _J, _S
    HMB = Path(p)
    _J = _S = None
    for f in (units, cards, questions, contract_text):
        f.cache_clear()


def upstream():
    """import 上游 judge.py 与 semantic.py（只读，不改）。"""
    global _J, _S
    if _J is None:
        if str(HMB) not in sys.path:
            sys.path.insert(0, str(HMB))
        for m in ("judge", "semantic"):
            mod = sys.modules.get(m)
            if mod is not None and Path(getattr(mod, "__file__", "")).resolve().parent != HMB.resolve():
                del sys.modules[m]
        _J = importlib.import_module("judge")
        _S = importlib.import_module("semantic")
    return _J, _S


def file_sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]


@lru_cache(maxsize=None)
def units():
    J, _ = upstream()
    return J.chapter_index(J.load_units())          # {cid: chapter}


def chapter_lines(cid: str) -> list[str]:
    return [l.rstrip("\r") for l in units()[cid]["text"].split("\n")]


@lru_cache(maxsize=None)
def questions(round_: str = "主轮") -> tuple:
    return tuple(json.loads((HMB / "questions" / f"题目_{round_}.json").read_text(encoding="utf-8")))


@lru_cache(maxsize=None)
def cards() -> dict:
    J, _ = upstream()
    return {q["qid"]: J.load_card(J.CARDS / f"{q['qid']}.yaml") for q in questions("主轮")}


def gradable_status() -> dict:
    """主轮：有答案键可判；干预轮：答案键不公开 ⇒ 不可判（只数题、不作答）。"""
    iv = questions("干预轮")
    have_iv_keys = sum(1 for q in iv if (cards().get(q.get("base_qid") or q["qid"][:-1]) or {}).get("intervention", {}).get("answer_points"))
    return {"主轮": {"n": len(questions("主轮")), "gradable": len(cards())},
            "干预轮": {"n": len(iv), "gradable": have_iv_keys,
                    "note": "答案键不公开（上游 README「两条必读声明·一」），本站不作答、不出分；上游提交通道见 docs/干预轮对比_v1.0.md §5（PR 逐题判定到 results/boards/），需答案键请联系作者——本站未提交"}}


@lru_cache(maxsize=None)
def contract_text() -> str:
    """作答契约主轮段，逐字（两条 `---` 之间）。"""
    raw = (HMB / "questions" / "作答契约.md").read_text(encoding="utf-8")
    parts = re.split(r"\n---\n", raw)
    return parts[1].strip("\n")


def sessions() -> list[dict]:
    out = []
    for cid in sorted(units(), key=lambda c: (c.split("_")[0], int(c.split("_c")[1]))):
        L = chapter_lines(cid)
        turns = [{"idx": i, "role": "user", "start_line": n, "end_line": n, "text": l}
                 for i, (n, l) in enumerate([(n, l) for n, l in enumerate(L, 1) if l.strip()])]
        for i, t in enumerate(turns):
            t["idx"] = i
        out.append({"session_id": cid, "turns": turns})
    return out


class BM25ParaPlugin(BM25Plugin):
    """朴素 BM25 参照臂（考卷 A 版）：每个自然段一块（BLOCK_CHARS=1 ⇒ 逐 Turn 成块），算法与参数同考卷 B 的 BM25Plugin。"""
    name = "bm25"
    version = "1.0-para"
    BLOCK_CHARS = 1


def load_plugin(spec: str):
    if spec == "null":
        return NullPlugin()
    if spec == "bm25":
        return BM25ParaPlugin()
    from .run import load_plugin as lp
    return lp(spec)


def filter_items(items: list[dict]) -> tuple[list[dict], list[dict]]:
    kept, audit = [], []
    for rank, it in enumerate(items):
        ps = parse_source(it.get("source"))
        if ps is None or ps[0] not in units():
            audit.append({"rank": rank, "source": it.get("source"), "action": "drop:unparseable"}); continue
        kept.append({**it, "file": ps[0], "start": ps[1], "end": ps[2]})
        audit.append({"rank": rank, "source": it["source"], "action": "keep"})
    return kept, audit


# ---------------- 生成器提示词 ----------------
MATERIAL_NOTE = "【正文】（本考场的正文由被测记忆插件提供：下面只是它检索返回的片段，不是全书；每个片段头给出所在章的标签 cid 与该章内行号）"
OUTPUT_NOTE = "（本考场：直接输出该 JSON 对象本身即可，考场代为写入 sut/out/<qid>.json。）"


def gen_messages(q: dict, material: list[dict]) -> list[dict]:
    parts = [contract_text(), "", MATERIAL_NOTE]
    if material:
        for i, m in enumerate(material, 1):
            parts.append(f"--- 片段 {i}｜cid={m.get('file')}（{units()[m['file']]['title']}）｜L{m.get('start')}-L{m.get('end')} ---")
            parts.append(m["text"])
    else:
        parts.append("（本臂无检索材料）")
    parts += ["", "【提问】", f"qid: {q['qid']}", f"问题：{q['question']}", "", OUTPUT_NOTE, f"现在输出 qid={q['qid']} 的 JSON 对象。"]
    return [{"role": "user", "content": "\n".join(parts)}]


def parse_resp(raw: str, qid: str) -> tuple[dict, bool]:
    d = extract_json(raw or "")
    if not isinstance(d, dict):
        return {"qid": qid}, True
    d = dict(d)
    d["qid"] = qid          # 题号以考场为准（防错位）
    if not isinstance(d.get("evidence"), list):
        d["evidence"] = []
    d["evidence"] = [e for e in d["evidence"] if isinstance(e, dict)]
    return d, False


# ---------------- 判官（上游 semantic.py 口径） ----------------
def sem_request(card: dict, qid: str, answer: str) -> str:
    """逐字复刻 semantic.cmd_prepare 的请求文件版式（case == qid，同 score_sut build）。"""
    _, S = upstream()
    pts = S._points_of(card, qid)
    lines = [f"<!-- {S.PROMPT_VERSION} · 请求文件由 semantic.py prepare 生成；不含期望标签 -->", "", S.PROMPT, "", "---", "",
             "## 材料（全部材料都在这里）", "", f"qid: {qid}", f"case: {qid}", f"问题：{card.get('question','')}", "", "要点清单："]
    for p in pts:
        tag = "required" if p.get("required") else "加分项（不计入分母）"
        lines.append(f"- {p.get('id')}（{tag}，权重 {p.get('weight', 1)}）：{p.get('point','')}")
    lines += ["", "## 被测答案（唯一被评判对象）", "", answer if answer else "（被测系统未给出结论/回答字段）", ""]
    return "\n".join(lines)


def sem_finalize(card: dict, qid: str, answer: str, raw: str) -> dict:
    """照抄 semantic.cmd_finalize 的单例逻辑：span 机械校验（定位不到 ⇒ 该点作废记 miss）→ 加权覆盖率。"""
    J, S = upstream()
    pts = S._points_of(card, qid)
    weights = {p.get("id"): float(p.get("weight", 1) or 1) for p in pts}
    required = [p.get("id") for p in pts if p.get("required")]
    m2 = re.search(r"\{.*\}", raw or "", re.S)
    jr = None
    if m2:
        try:
            jr = json.loads(m2.group(0))
        except json.JSONDecodeError:
            jr = extract_json(raw)
    if not isinstance(jr, dict):
        return {"ok": False, "error": "判官输出不是 JSON", "score": 0.0, "verdict": "fail"}
    verdicts, invalid = {}, []
    for p in jr.get("points") or []:
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        v = (p.get("verdict") or "").strip().lower()
        span = (p.get("span") or "").strip()
        if pid not in weights:
            continue
        if v not in {"strict", "paraphrase", "miss"}:
            v = "miss"
        if v != "miss":
            if not span or J.norm(span) not in J.norm(answer):
                invalid.append(pid); v = "miss"
        verdicts[pid] = v
    got = sum(weights[pid] * (S.FULL if v == "strict" else S.PARA if v == "paraphrase" else 0.0)
              for pid, v in verdicts.items() if pid in required)
    den = sum(weights[pid] for pid in required) or 1.0
    score = got / den
    return {"ok": True, "score": round(score, 3), "verdict": "pass" if score >= J.PASS_SCORE else "fail",
            "strict": [k for k, v in verdicts.items() if v == "strict"],
            "paraphrase": [k for k, v in verdicts.items() if v == "paraphrase"],
            "miss": [k for k, v in verdicts.items() if v == "miss"], "span_invalid": invalid}


def cite_request(card: dict, qid: str, resp: dict, res: dict | None) -> str:
    _, S = upstream()
    obj = {"qid": qid, "case": qid, "response": resp}
    return "\n".join([f"<!-- {S.CITE_VERSION} · 请求文件由 semantic.py prepare --task cite 生成；不含期望标签 -->",
                      "", S.PROMPT_CITE, "", "---", "", S._cite_materials(card, obj, res), ""])


def cite_finalize(raw: str) -> str:
    mm = re.search(r"\{.*\}", raw or "", re.S)
    try:
        jr = json.loads(mm.group(0)) if mm else {}
    except json.JSONDecodeError:
        jr = extract_json(raw) or {}
    v = (str(jr.get("verdict") or "")).strip().lower() if isinstance(jr, dict) else ""
    return v if v in {"fit", "unfit", "thin"} else "parse_err"


def _ngrams(s, n=8):
    s = re.sub(r"\s+", "", s or "")
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _pts_text(card, qid):
    _, S = upstream()
    return "；".join(p.get("point", "") for p in S._points_of(card, qid) if p.get("required"))


def build_anchors() -> list[dict]:
    """分层固定锚（seed 20261006）：语义锚 8 正 8 负、依据锚 4 正 4 负。答案键条目当已知答案（判分可靠性 §三.3）。"""
    rng = random.Random(ANCHOR_SEED)
    C = cards()
    qids = sorted(C)
    pick = rng.sample(qids, sum(N_SEM_ANCHORS) + sum(N_CITE_ANCHORS))
    out = []
    a, b = N_SEM_ANCHORS
    for q in pick[:a]:
        out.append({"aid": f"S+{q}", "task": "sem", "qid": q, "answer": _pts_text(C[q], q), "expect": "pass"})
    for q in pick[a:a + b]:
        g = _ngrams(_pts_text(C[q], q))
        others = [o for o in qids if o != q and not (_ngrams(_pts_text(C[o], o)) & g)]
        o = rng.choice(others)
        out.append({"aid": f"S×{q}<{o}", "task": "sem", "qid": q, "answer": _pts_text(C[o], o), "expect": "fail"})
    c, d = N_CITE_ANCHORS
    base = a + b
    for q in pick[base:base + c]:
        pool = (C[q].get("supporting_evidence") or C[q].get("evidence_pool") or [])   # 全池（v1 只取前 2 条＝尺子歪：判官一致判 thin，见 OVERNIGHT 08:3x）
        out.append({"aid": f"C+{q}·全池", "task": "cite", "qid": q, "expect": "fit",
                    "resp": {"qid": q, "answer": _pts_text(C[q], q), "evidence": [{"cid": e.get("cid"), "quote": e.get("quote")} for e in pool]}})
    for q in pick[base + c:base + c + d]:
        g = _ngrams(_pts_text(C[q], q))
        # 负锚须"真负"：他卡依据与本卡依据**不共章**（v2 只查 8-gram，C×q006<q031 两卡同讲永生、两判官一致判 fit＝尺子歪）
        mine = {e.get("cid") for e in (C[q].get("supporting_evidence") or C[q].get("evidence_pool") or [])}
        others = [o for o in qids if o != q and (C[o].get("evidence_pool") or C[o].get("supporting_evidence"))
                  and not (_ngrams(" ".join(e.get("quote") or "" for e in (C[o].get("evidence_pool") or C[o].get("supporting_evidence")))) & g)
                  and not ({e.get("cid") for e in (C[o].get("supporting_evidence") or C[o].get("evidence_pool"))} & mine)]
        o = rng.choice(others)
        pool = (C[o].get("supporting_evidence") or C[o].get("evidence_pool") or [])
        out.append({"aid": f"C×{q}<{o}·全池·异章", "task": "cite", "qid": q, "expect": "notfit",
                    "resp": {"qid": q, "answer": _pts_text(C[q], q), "evidence": [{"cid": e.get("cid"), "quote": e.get("quote")} for e in pool]}})
    return out


def kappa(a, b):
    n = len(a)
    if n == 0:
        return float("nan")
    po = sum(x == y for x, y in zip(a, b)) / n
    cats = set(a) | set(b)
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return 1.0 if pe >= 1 else (po - pe) / (1 - pe)


def _gate_part(anchor_rows, item_rows, label):
    res = {f"{label}_n_anchor": len(anchor_rows), f"{label}_n_items": len(item_rows)}
    ok = True
    if anchor_rows:
        exp = [r["expect"] for r in anchor_rows]
        base = max(exp.count(x) for x in set(exp)) / len(exp)
        res[f"{label}_baseline"] = base
        for j in ("1", "2"):
            acc = sum(r["l" + j] == r["expect"] for r in anchor_rows) / len(anchor_rows)
            res[f"{label}_acc_j{j}"] = acc
            res[f"{label}_margin_pp_j{j}"] = round((acc - base) * 100, 1)
            ok &= acc >= GATE["anchor_acc_min"] and (acc - base) * 100 >= GATE["anchor_margin_pp_min"]
    for nm, rows in (("anchor", anchor_rows), ("items", item_rows)):
        a = [r["l1"] for r in rows]; b = [r["l2"] for r in rows]
        agree = sum(x == y for x, y in zip(a, b)) / len(rows) if rows else None
        k = kappa(a, b) if rows else None
        res[f"{label}_{nm}_agree"] = agree
        res[f"{label}_{nm}_kappa"] = k
        if rows:   # 上游 judge_audit：同分 ≥ 0.8 或 κ ≥ 0.6 ⇒ 可报值
            ok &= agree >= GATE["agree_min"] or (k is not None and not math.isnan(k) and k >= GATE["kappa_min"])
    res[f"{label}_pass"] = bool(ok)
    return res


def _load_cache(path):
    cache = {}
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line); cache[(d["attempt"], d["judge"], d["task"], d["key"])] = d
                except (json.JSONDecodeError, KeyError):
                    pass
    return cache


def route(card, resp, idx):
    J, _ = upstream()
    res = J.judge(card, resp, idx)
    if res["struct_bad"] or res["empty"]:
        return "fail_struct", res
    if res["verdict"] == "pass" and not res.get("downgrade"):
        return "pass_rule", res
    if res.get("downgrade"):
        return "cite", res
    return "sem", res


def judge_batch(items: list[dict], anchors: list[dict], rec, *, make_client, concurrency=3, batch_tag="", cache_path=None) -> dict:
    """items: [{"key","qid","resp","route","res_brief","ev"}]。两名判官同材料、盲混（与锚一起打乱）、各判一次。"""
    C = cards()
    cache = _load_cache(cache_path)
    lock = threading.Lock()
    g = None
    for attempt in range(1, GATE["max_attempts"] + 1):
        j1 = make_client("judge-1"); j2 = make_client("judge-2")
        j1.instance = f"{batch_tag}#a{attempt}-judge-1"; j2.instance = f"{batch_tag}#a{attempt}-judge-2"
        need_cite = any(it["route"] == "cite" for it in items)
        anc = [a for a in anchors if a["task"] == "sem" or need_cite]
        work = []
        for it in items:
            if it["route"] in ("cite",):
                work.append(("cite", it)); work.append(("sem", it))
            elif it["route"] == "sem":
                work.append(("sem", it))
        work += [("anchor", a) for a in anc]
        rec.event("judge.batch.start", batch=batch_tag, attempt=attempt, judges=[j1.instance, j2.instance],
                  n_items=len(items), n_judged=len(work) - len(anc), n_anchors=len(anc),
                  routes={r: sum(1 for it in items if it["route"] == r) for r in ("pass_rule", "fail_struct", "cite", "sem")})
        random.Random(f"{batch_tag}-{attempt}").shuffle(work)

        def run(w):
            kind, x = w
            task = x["task"] if kind == "anchor" else kind
            key = x["aid"] if kind == "anchor" else x["key"]
            qid = x["qid"]; card = C[qid]
            if task == "sem":
                answer = x["answer"] if kind == "anchor" else (x["resp"].get("answer") or x["resp"].get("conclusion") or "").strip()
                msgs = [{"role": "user", "content": sem_request(card, qid, answer)}]
            else:
                resp = x["resp"]
                msgs = [{"role": "user", "content": cite_request(card, qid, resp, None)}]
            outs = {}
            for nm, cl in (("1", j1), ("2", j2)):
                hit = cache.get((attempt, cl.instance, task, key))
                if hit:
                    outs[nm] = hit; continue
                r = cl.chat(msgs, rec, tag=f"{batch_tag}|{kind}|{task}|{key}|j{nm}")
                if task == "sem":
                    fin = sem_finalize(card, qid, answer, r["content"])
                    lab = fin["verdict"]
                else:
                    fin = {"cite": cite_finalize(r["content"])}
                    lab = fin["cite"] if kind != "anchor" else ("fit" if fin["cite"] == "fit" else "notfit")
                ev = rec.event("judge.verdict", batch=batch_tag, attempt=attempt, judge=cl.instance, kind=kind, task=task,
                               key=key, qid=qid, label=lab, fin=fin, raw=r["content"])
                d = {"attempt": attempt, "judge": cl.instance, "task": task, "key": key, "label": lab, "fin": fin,
                     "ev": {"seq": ev["seq"], "t": ev["t"]}}
                outs[nm] = d
                if cache_path:
                    with lock, open(cache_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(d, ensure_ascii=False) + "\n")
            return kind, task, x, outs

        with ThreadPoolExecutor(concurrency) as ex:
            results = list(ex.map(run, work))
        sem_a, cite_a, sem_i, cite_i = [], [], [], []
        per = {}
        for kind, task, x, o in results:
            row = {"l1": o["1"]["label"], "l2": o["2"]["label"], "ev1": o["1"]["ev"], "ev2": o["2"]["ev"],
                   "fin1": o["1"]["fin"], "fin2": o["2"]["fin"]}
            if kind == "anchor":
                row.update(aid=x["aid"], expect=x["expect"], qid=x["qid"])
                (sem_a if task == "sem" else cite_a).append(row)
            else:
                per.setdefault(x["key"], {})[task] = row
                if task == "sem":
                    sem_i.append(row)
                else:
                    cite_i.append({**row, "l1": "fit" if row["l1"] == "fit" else "notfit", "l2": "fit" if row["l2"] == "fit" else "notfit"})
        gate = {**_gate_part(sem_a, sem_i, "sem")}
        if need_cite:
            gate.update(_gate_part(cite_a, cite_i, "cite"))
        gate["pass"] = gate["sem_pass"] and (gate.get("cite_pass", True))
        g = gate
        ev = rec.event("judge.batch.gate", batch=batch_tag, attempt=attempt, **gate)
        rows = []
        J, _ = upstream()
        for it in items:
            p = per.get(it["key"], {})
            row = {"key": it["key"], "qid": it["qid"], "route": it["route"], "gen_ev": it["ev"]}
            if it["route"] == "pass_rule":
                row.update(final="pass", path="规则层通过", score=1.0, final_lenient="pass", final_strict="pass")
            elif it["route"] == "fail_struct":
                row.update(final="fail", path="规则层结构违规：" + "、".join(it["res_brief"]["struct_bad"] or (["空答"] if it["res_brief"]["empty"] else [])),
                           score=0.0, final_lenient="fail", final_strict="fail")
            else:
                c = p.get("cite")
                revoked = bool(c) and c["l1"] == "fit" and c["l2"] == "fit" and it["res_brief"].get("down_kind") == "cite"
                rev_len = bool(c) and "fit" in (c["l1"], c["l2"]) and it["res_brief"].get("down_kind") == "cite"
                s = p["sem"]
                s1, s2 = s["fin1"].get("score", 0.0), s["fin2"].get("score", 0.0)
                mean = (s1 + s2) / 2
                row.update(cite=c and {"l1": c["l1"], "l2": c["l2"], "ev1": c["ev1"], "ev2": c["ev2"]},
                           sem={"s1": s1, "s2": s2, "mean": round(mean, 4), "l1": s["l1"], "l2": s["l2"], "ev1": s["ev1"], "ev2": s["ev2"],
                                "fin1": s["fin1"], "fin2": s["fin2"]})
                if revoked:
                    row.update(final="pass", path="L2 判官撤销降级（仅依据轴，双判官均 fit）", score=1.0)
                else:
                    row.update(final="pass" if mean >= J.PASS_SCORE else "fail", path="覆盖率判官（双判官均值）", score=1.0 if mean >= J.PASS_SCORE else 0.0)
                row["final_lenient"] = "pass" if (rev_len or max(s1, s2) >= J.PASS_SCORE) else "fail"
                row["final_strict"] = "pass" if (revoked or min(s1, s2) >= J.PASS_SCORE) else "fail"
            rows.append(row)
        if gate["pass"]:
            return {"status": "valid", "attempt": attempt, "gate": gate, "gate_ev": {"seq": ev["seq"], "t": ev["t"]},
                    "items": rows, "anchors": {"sem": sem_a, "cite": cite_a}, "voided": attempt - 1}
        rec.event("judge.batch.void", batch=batch_tag, attempt=attempt, reason="锚自证/一致率不达标，整批作废重批")
    return {"status": "void", "attempt": GATE["max_attempts"], "gate": g, "items": rows, "anchors": {"sem": sem_a, "cite": cite_a},
            "voided": GATE["max_attempts"]}


# ---------------- 运行器 ----------------
def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def wjson(p: Path, obj):
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, p)


def rjson(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def evidence_stats(resp: dict) -> dict:
    J, _ = upstream()
    ax = J.axis_evidence({}, resp, units(), min_required=0)
    n = len(resp.get("evidence") or [])
    return {"n": n, "valid": ax["valid"], "mislocated": len(ax["mislocated"]), "fabricated": len(ax["fabricated"])}


def main(argv=None):
    from .run import git_sha
    ap = argparse.ArgumentParser()
    ap.add_argument("--plugin", required=True)
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=DEFAULT_K)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--hmb", default=str(HMB))
    ap.add_argument("--skip-judge", action="store_true")
    a = ap.parse_args(argv)
    set_root(a.hmb)
    out = Path(a.out); (out / "q").mkdir(parents=True, exist_ok=True); (out / "judge").mkdir(exist_ok=True)
    seeds = [int(s) for s in a.seeds.split(",") if s.strip()]
    plugin = load_plugin(a.plugin)
    run_id = out.name
    rec = Recorder(out / "recording.jsonl", run_id, resume=a.resume)
    qs = list(questions("主轮"))
    if a.limit:
        qs = qs[:a.limit]
    _, S = upstream()
    J, _ = upstream()
    cfg = {"exam": EXAM_ID, "plugin": a.plugin, "plugin_name": plugin.name, "plugin_version": plugin.version,
           "plugin_kind": getattr(plugin, "kind", "python"),
           "generator": {"model": llm.MODEL, "temperature": GEN_TEMPERATURE, "max_tokens": GEN_MAX_TOKENS, "thinking": "off"},
           "judge": {"model": llm.MODEL, "temperature": 0.0, "max_tokens": JUDGE_MAX_TOKENS, "thinking": "off", "n_judges": 2,
                     "aggregate": "覆盖率分双判官均值；L2 撤销需双判官均 fit", "gate": GATE},
           "seeds": seeds, "k": a.k, "material_cap": MATERIAL_CAP, "n_cards": len(qs),
           "prompt_sha": {"contract": _sha(contract_text()), "material_note": _sha(MATERIAL_NOTE + OUTPUT_NOTE),
                          "semantic_prompt": _sha(S.PROMPT), "cite_prompt": _sha(S.PROMPT_CITE),
                          "semantic_version": S.PROMPT_VERSION, "cite_version": S.CITE_VERSION},
           "cards_sha": _sha("".join(file_sha(J.CARDS / f"{q['qid']}.yaml") for q in qs)) + "+" + file_sha(HMB / "questions" / "题目_主轮.json"),
           "hmb_git": git_sha(HMB), "judge_py_sha": file_sha(HMB / "judge.py"), "semantic_py_sha": file_sha(HMB / "semantic.py"),
           "harness_git": git_sha(Path(__file__).resolve().parent.parent), "anchor_seed": ANCHOR_SEED,
           "gradable": gradable_status()}
    cfgp = out / "config.json"
    if cfgp.exists() and a.resume:
        old = rjson(cfgp)
        for key in ("exam", "plugin", "generator", "judge", "seeds", "k", "material_cap", "prompt_sha", "cards_sha"):
            if old.get(key) != cfg.get(key):
                raise SystemExit(f"--resume 配置不一致：{key}（旧 {old.get(key)} vs 新 {cfg.get(key)}）")
    wjson(cfgp, cfg)
    rec.event("run.config", **cfg)
    statep = out / "state.json"
    state = rjson(statep) if statep.exists() else {}

    # ① 插件期
    need = [q for q in qs if not (out / "q" / f"{q['qid']}.recall.json").exists()]
    if need:
        sbx = Sandbox(run_id, fresh=True)
        plugin.sandbox = sbx
        rec.event("sandbox.create", root=str(sbx.root), env_keys=sorted(sbx.env))
        snap0 = sbx.snapshot()
        t0 = time.monotonic()
        try:
            ir = plugin.install(rec)
        except Exception as e:
            ir = type("IR", (), {"ok": False, "steps": 0, "errors": [repr(e)]})()
            rec.event("plugin.install.exception", tb=traceback.format_exc()[-4000:])
        ev = rec.event("plugin.install.result", ok=ir.ok, steps=ir.steps, errors=ir.errors, dur_s=round(time.monotonic() - t0, 3))
        state["install"] = {"ok": ir.ok, "steps": ir.steps, "errors": ir.errors, "dur_s": ev["dur_s"], "ev": [ev["seq"], ev["t"]]}
        state["install"]["footprint"] = Sandbox.diff(snap0, sbx.snapshot())
        wjson(statep, state)
        if not ir.ok:
            rec.event("run.abort", reason="安装失败 → 🚧 没法测（只出好不好用单）")
            state["aborted"] = "install_failed"; wjson(statep, state); rec.close()
            render_timeline(out / "recording.jsonl", out / "timeline.md"); return 2
        ss = sessions()
        t0 = time.monotonic(); ingest_err = None
        try:
            plugin.ingest(ss, rec)
        except Exception as e:
            ingest_err = repr(e)
            rec.event("plugin.ingest.exception", tb=traceback.format_exc()[-4000:])
        ev = rec.event("plugin.ingest.result", ok=ingest_err is None, error=ingest_err, dur_s=round(time.monotonic() - t0, 3),
                       turns=sum(len(s["turns"]) for s in ss), chars=sum(len(t["text"]) for s in ss for t in s["turns"]))
        state["ingest"] = {"ok": ingest_err is None, "error": ingest_err, "dur_s": ev["dur_s"], "turns": ev["turns"], "ev": [ev["seq"], ev["t"]]}
        wjson(statep, state)
        lat = []
        for q in need:
            query = q["question"]
            t1 = time.monotonic(); err = None
            try:
                items = plugin.recall(query, a.k, rec) if ingest_err is None else []
            except Exception as e:
                items, err = [], repr(e)
                rec.event("plugin.recall.exception", qid=q["qid"], tb=traceback.format_exc()[-3000:])
            dt = time.monotonic() - t1; lat.append(dt)
            items = [{"text": str(i.get("text", "")), "source": i.get("source")} for i in (items or [])][:a.k]
            kept, audit = filter_items(items)
            mat = assemble_material(kept, query, MATERIAL_CAP)
            ev = rec.event("plugin.recall", qid=q["qid"], query=query, k=a.k, latency_s=round(dt, 3), error=err,
                           sources=[i["source"] for i in items], audit=audit,
                           material=[{"source": m["source"], "chars": len(m["text"])} for m in mat])
            wjson(out / "q" / f"{q['qid']}.recall.json", {"qid": q["qid"], "error": err or (ingest_err and "ingest_failed"),
                  "latency_s": dt, "raw_sources": [i["source"] for i in items], "audit": audit,
                  "material": [{k: m[k] for k in ("text", "source", "file", "start", "end")} for m in mat], "ev": [ev["seq"], ev["t"]]})
            state.setdefault("recall_latency_s", []).append(round(dt, 4)); wjson(statep, state)
        t0 = time.monotonic()
        try:
            un = plugin.uninstall(rec) or {}
        except Exception as e:
            un = {"residue_paths": [], "error": repr(e)}
        residue = Sandbox.diff(snap0, sbx.snapshot())
        ev = rec.event("plugin.uninstall.result", reported=un, residue=residue, dur_s=round(time.monotonic() - t0, 3))
        state["uninstall"] = {"reported": un, "residue": residue, "ev": [ev["seq"], ev["t"]]}
        state["permissions"] = getattr(plugin, "permissions", None)
        state["sandbox_env_has_api_key"] = "CLINE_API_KEY" in sbx.env
        wjson(statep, state)

    # ② 作答期
    gen = llm.Client("generator", temperature=GEN_TEMPERATURE, max_tokens=GEN_MAX_TOKENS)

    def answer(job):
        seed, q = job
        p = out / "q" / f"{q['qid']}.s{seed}.gen.json"
        if p.exists():
            return
        r = rjson(out / "q" / f"{q['qid']}.recall.json")
        try:
            res = gen.chat(gen_messages(q, r["material"]), rec, tag=f"gen|{q['qid']}|s{seed}", seed=seed)
        except llm.LLMError as e:
            rec.event("gen.error", qid=q["qid"], seed=seed, error=str(e)[:300]); return
        resp, perr = parse_resp(res["content"], q["qid"])
        es = evidence_stats(resp)
        ev = rec.event("gen.answer", qid=q["qid"], seed=seed, parse_err=perr, conclusion=str(resp.get("conclusion", ""))[:300],
                       confidence=resp.get("confidence"), evidence=es, usage=res["usage"], finish_reason=res["finish_reason"])
        wjson(p, {"qid": q["qid"], "seed": seed, "raw": res["content"], "resp": resp, "parse_err": perr, "evidence": es,
                  "usage": res["usage"], "finish_reason": res["finish_reason"], "ev": [ev["seq"], ev["t"]]})

    jobs = [(s, q) for s in seeds for q in qs]
    with ThreadPoolExecutor(a.concurrency) as ex:
        list(ex.map(answer, jobs))
    missing = [(s, q["qid"]) for s, q in jobs if not (out / "q" / f"{q['qid']}.s{s}.gen.json").exists()]
    if missing:
        rec.event("gen.incomplete", missing=len(missing)); rec.close(); render_timeline(out / "recording.jsonl", out / "timeline.md")
        print(f"作答未完成 {len(missing)} 条，请 --resume 续跑"); return 3

    # ③ 判分期
    if not a.skip_judge:
        anchors = build_anchors()
        C = cards(); idx = units()
        for s in seeds:
            jp = out / "judge" / f"s{s}.json"
            if jp.exists() and rjson(jp).get("status") == "valid":
                continue
            items = []
            for q in qs:
                g = rjson(out / "q" / f"{q['qid']}.s{s}.gen.json")
                rt, res = route(C[q["qid"]], g["resp"], idx)
                items.append({"key": f"{q['qid']}.s{s}", "qid": q["qid"], "resp": g["resp"], "route": rt,
                              "res_brief": {"verdict": res["verdict"], "struct_bad": res["struct_bad"], "empty": res["empty"],
                                            "downgrade": res.get("downgrade"), "down_kind": res.get("down_kind"),
                                            "evidence": {k: res["axes"]["evidence"].get(k) for k in ("valid", "mislocated", "fabricated", "invalid")},
                                            "honesty": res["axes"].get("honesty", {}).get("detail")},
                              "ev": {"seq": g["ev"][0], "t": g["ev"][1]}})
            res = judge_batch(items, anchors, rec,
                              make_client=lambda role: llm.Client(role, temperature=0.0, max_tokens=JUDGE_MAX_TOKENS),
                              concurrency=a.concurrency, batch_tag=f"{run_id}|s{s}", cache_path=str(out / "judge" / f"s{s}.verdicts.jsonl"))
            for it, row in zip(items, res["items"]):
                row["rule"] = it["res_brief"]
            wjson(jp, res)

    summ = summarize(out, qs, seeds, state)
    wjson(out / "summary.json", summ)
    rec.event("run.summary", **{k: v for k, v in summ.items() if k != "per_item"}, llm_totals_this_process=dict(llm.TOTALS))
    rec.close()
    render_timeline(out / "recording.jsonl", out / "timeline.md")
    print(json.dumps({k: v for k, v in summ.items() if k != "per_item"}, ensure_ascii=False, indent=1, default=str))
    return 0


def summarize(out: Path, qs, seeds, state) -> dict:
    per_seed, per_item = {}, {}
    ev_tot = {"n": 0, "valid": 0, "mislocated": 0, "fabricated": 0, "answers_with_valid": 0}
    tok = {"gen_prompt": 0, "gen_completion": 0}
    parse_err = 0; trunc = 0
    for s in seeds:
        jp = out / "judge" / f"s{s}.json"
        j = rjson(jp) if jp.exists() else None
        rows = {r["qid"]: r for r in (j["items"] if j else [])}
        cnt = {"pass": 0, "fail": 0, "pass_lenient": 0, "pass_strict": 0}
        routes = {}
        sem_scores = []
        for q in qs:
            g = rjson(out / "q" / f"{q['qid']}.s{s}.gen.json")
            parse_err += bool(g["parse_err"]); trunc += g.get("finish_reason") == "length"
            tok["gen_prompt"] += g["usage"].get("prompt_tokens") or 0
            tok["gen_completion"] += g["usage"].get("completion_tokens") or 0
            for k in ("n", "valid", "mislocated", "fabricated"):
                ev_tot[k] += g["evidence"][k]
            ev_tot["answers_with_valid"] += g["evidence"]["valid"] > 0
            r = rows.get(q["qid"])
            if r:
                cnt[r["final"]] += 1
                cnt["pass_lenient"] += r["final_lenient"] == "pass"; cnt["pass_strict"] += r["final_strict"] == "pass"
                routes[r["route"]] = routes.get(r["route"], 0) + 1
                if r.get("sem"):
                    sem_scores.append(r["sem"]["mean"])
                per_item.setdefault(q["qid"], {})[str(s)] = {"final": r["final"], "route": r["route"], "path": r["path"],
                                                           "score": r["score"]}
        per_seed[str(s)] = {**cnt, "n": len(qs), "routes": routes,
                            "sem_mean_score": round(statistics.mean(sem_scores), 3) if sem_scores else None,
                            "judge_status": j["status"] if j else "missing", "judge_attempts": j["attempt"] if j else 0,
                            "voided_batches": j.get("voided", 0) if j else 0, "gate": j["gate"] if j else None}
    recs = [rjson(out / "q" / f"{q['qid']}.recall.json") for q in qs]
    mat_chars = [sum(len(m["text"]) for m in r["material"]) for r in recs]
    return {"exam": EXAM_ID, "n_cards": len(qs), "seeds": seeds, "per_seed": per_seed, "parse_err": parse_err, "gen_truncated": trunc,
            "recall_errors": sum(1 for r in recs if r.get("error")), "material_chars_mean": round(sum(mat_chars) / len(mat_chars)),
            "cards_with_material": sum(1 for x in mat_chars if x), "dropped_unparseable": sum(1 for r in recs for x in r["audit"] if x["action"] != "keep"),
            "evidence": ev_tot, "gen_tokens": tok, "install": state.get("install"), "ingest": state.get("ingest"),
            "gradable": gradable_status(), "per_item": per_item}


if __name__ == "__main__":
    sys.exit(main())
