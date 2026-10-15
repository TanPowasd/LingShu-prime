"""AGM × hive-memory-bench 官方管线（主轮 92 题）：被测系统取材 → 同一生成器作答 → 官方判分器。

臂：直读（全文 6 万字，长上下文天花板）、BM25、AGM、TriCue_v11、TriCue_v3（各 8,000 字预算，与检索面同口径）。
作答契约逐字取自基准 questions/作答契约.md；检索臂前面多一句「以下是检索到的片段，不是全文」。
生成器与判官都走 OpenAI chat completions 兼容接口；key 由运行环境注入，不写在代码里。
用法：
  python hive_official.py gen   <bench> --arm 直读|BM25|AGM [--model M] [--workers 8]
  python hive_official.py judge <bench> <real目录名> [--model M]     # 回答 semantic/req/<目录>/*.md
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import threading
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hive_retrieval as HR   # noqa: E402

API = "https://api.cline.bot/api/v1/chat/completions"
MODEL = "cline-pass/deepseek-v4.1-flash"
BUDGET = 8000
# 统一系统提示词（实验开关）：环境变量 LLM_SYS=1 时，我们这侧所有 LLM 环节（源图抽取、题面扩展、追问、作答）
# 都带同一条 system 消息，缓存目录加 _sys 后缀与旧缓存隔离（qx.py cache_q、hx.py cache_h、extract.py cache、
# hive_extract.py cache_hive；后两者受 LLM_SYS_GRAPH 控制）；官方判官始终不带（system=False），保证与基线可比。
# 作答/判官产物目录带臂身份清单 _identity.json（dsh-bounty#466 F1 修复）：身份或逐题输入指纹不一致 ⇒ 拒绝、退出码 2，
# 不再「存在即 skip」。
import os  # noqa: E402
SYS_ON = os.environ.get("LLM_SYS") == "1"
SYS_SUFFIX = "_sys" if SYS_ON else ""
SYSTEM = ("你是灵枢长期记忆系统里的一个组件，负责从给定材料中抽取、检索或回答。\n"
          "1. 只依据本次用户消息里给出的材料和问题工作，不使用材料以外的知识，不猜测，不编造。\n"
          "2. 人名、地名、物品名、日期、数字一律照原文逐字写，不改写、不意译。\n"
          "3. 问题有多个要点时逐点覆盖，不遗漏；材料里确实没有的，明确说没有，不要硬凑。\n"
          "4. 严格按要求的格式输出：要 JSON 就只输出一个 JSON 对象，不加代码块、不加解释。")


def chat(prompt, model, max_tokens=None, tries=4, system=None):
    """max_tokens=None：不传上限，用模型/代理自身的最大输出（用户 2026-10-12 要求尽量不限制）。
    system=None：按 LLM_SYS 开关决定是否带统一系统提示词；system=False：强制不带（官方判官）；字符串：用它。"""
    sysmsg = (SYSTEM if SYS_ON else None) if system is None else (system or None)
    msgs = ([{"role": "system", "content": sysmsg}] if sysmsg else []) + [{"role": "user", "content": prompt}]
    req = {"model": model, "messages": msgs, "temperature": 0}
    if max_tokens:
        req["max_tokens"] = max_tokens
    body = json.dumps(req).encode()
    for k in range(tries):
        try:
            req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read())
            d = d.get("data", d)
            txt = d["choices"][0]["message"]["content"]
            if txt and txt.strip():
                return txt
        except Exception as e:  # noqa: BLE001
            err = e
        time.sleep(3 * (k + 1))
    raise RuntimeError(f"chat failed: {locals().get('err')}")


def parse_json(txt):
    t = re.sub(r"^```(?:json)?|```$", "", txt.strip(), flags=re.M).strip()
    i, j = t.find("{"), t.rfind("}")
    return json.loads(t[i:j + 1])


def contract(bench):
    s = (bench / "questions" / "作答契约.md").read_text(encoding="utf-8")
    body = s.split("---")[1].strip()
    return body.replace("写入指定的输出文件 `sut/out/<qid>.json`（文件内容就是该对象，不要代码块包裹、不要额外说明）",
                        "直接输出该对象（不要代码块包裹、不要额外说明）")


def contexts(bench, arm, questions):
    if arm == "直读":
        full = (bench / "corpus" / "语料.md").read_text(encoding="utf-8")
        return {q["qid"]: full for q in questions}
    if arm == "QMD两跳":                                      # QMD + 两跳追问（冻结配置，见 confluence/PREREG_hop.md）
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "confluence"))
        import hive_hop
        return hive_hop.contexts(bench, questions)
    if arm == "QMD":                                          # 汇流多维 + 题面 LLM 抽取（冻结配置，见 confluence/PREREG_qmd.md）
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "confluence"))
        import hive_qmd
        return hive_qmd.contexts(bench, questions)
    if arm == "汇流多维":                                     # 汇流多维 v3×3（LLM 中文源图缓存，见 confluence/hive_mdllm.py）
        sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "confluence"))
        import hive_mdllm
        return hive_mdllm.contexts(bench, questions)
    chunks = HR.load_chunks(bench)
    if arm.startswith("TriCue"):
        return tricue_contexts(chunks, arm, questions)
    bm = HR.BM25(chunks)
    agm = HR.AGM(chunks, bm) if arm == "AGM" else None
    out = {}
    for q in questions:
        qb = HR.bigrams(q["question"])
        if arm == "BM25":
            sc = bm.scores(qb); order = sorted(range(len(chunks)), key=lambda i: -sc[i])
        else:
            order = agm.rank(qb)
        got, used = [], 0                                     # 与 HR.take 同一预算规则，但要块号
        for i in order:
            L = len(chunks[i]["n"])
            if used + L > BUDGET and used:
                break
            got.append(i); used += L
        got.sort()                                            # 恢复原文顺序，便于阅读
        parts = [f"### {chunks[i]['cid']}\n{chunks[i]['text'].strip()}" for i in got]
        out[q["qid"]] = ("（以下是记忆系统按本题检索到的正文片段，不是全文；每段标题是它所在章的 cid。）\n\n"
                         + "\n\n".join(parts))
    return out


def tricue_contexts(chunks, arm, questions):
    """TriCue 臂：语料各块按原文顺序逐个写入（一块＝一轮），按 8000 字预算取材，按原文顺序排回并标 cid。"""
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "tricue"))
    import tricue as T
    mem = T.TriCueMemory.v3() if arm == "TriCue_v3" else T.TriCueMemory()
    for c in chunks:
        mem.add_turn("doc", c["text"])
    out = {}
    for q in questions:
        hits = sorted(mem.retrieve(q["question"], BUDGET), key=lambda h: h.id)
        parts, last = [], None
        for h in hits:
            cid = chunks[h.turn]["cid"]
            parts.append((f"### {cid}\n" if cid != last else "") + h.text.strip()); last = cid
        out[q["qid"]] = ("（以下是记忆系统按本题检索到的正文片段，不是全文；每段标题是它所在章的 cid。）\n\n"
                         + "\n\n".join(parts))
    return out


class IdentityMismatch(SystemExit):
    """产物目录里的既有结果不属于本次运行的臂身份（dsh-bounty#466 F1）。退出码 2。"""

    def __init__(self, msg):
        print("[身份不一致] " + msg, file=sys.stderr, flush=True)
        super().__init__(2)


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def bench_commit(bench):
    """基准仓的 git commit；取不到就写 "存疑:无git"（不猜）。"""
    try:
        r = subprocess.run(["git", "-C", str(bench), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or "存疑:无git"
    except (OSError, subprocess.SubprocessError):
        return "存疑:无git"


def gen_identity(A, bench):
    return {"kind": "gen", "arm": A.arm, "tag": A.tag, "model": A.model,
            "LLM_SYS": SYS_ON, "LLM_SYS_GRAPH": os.environ.get("LLM_SYS_GRAPH", "1"),
            "system_sha": sha(SYSTEM) if SYS_ON else None, "bench_commit": bench_commit(bench)}


class Manifest:
    """产物目录身份清单：{"identity": {...}, "inputs": {名字: 输入指纹}}。
    规则：目录里已有结果文件 ⇒ 清单必须存在且 identity 逐项相等，否则拒绝；
    单个结果只在「其输入指纹与本次相同」时复用，否则拒绝（不覆盖、不 skip）。"""

    def __init__(self, d, identity, results):
        self.f = d / "_identity.json"
        self.lock = threading.Lock()
        have = [g for g in results if g.exists()]
        if self.f.exists():
            m = json.loads(self.f.read_text(encoding="utf-8"))
            if m.get("identity") != identity:
                raise IdentityMismatch(f"{d} 的既有身份 {m.get('identity')} ≠ 本次 {identity}；换 --tag 或换目录")
            self.inputs = m.get("inputs", {})
        elif have:
            raise IdentityMismatch(f"{d} 已有 {len(have)} 个结果但没有身份清单（修复前产物）；换 --tag 或换目录")
        else:
            self.inputs = {}
        self.identity = identity
        self._save()

    def _save(self):
        self.f.write_text(json.dumps({"identity": self.identity, "inputs": self.inputs}, ensure_ascii=False, indent=1),
                          encoding="utf-8")

    def reusable(self, name, result, fp):
        """True = 结果存在且输入指纹相同，可复用；False = 需要调用；指纹不同 ⇒ 拒绝。"""
        with self.lock:
            old = self.inputs.get(name)
        if not result.exists():
            return False
        if old != fp:
            raise IdentityMismatch(f"{result} 的输入指纹 {old} ≠ 本次 {fp}（上下文或请求变了）；换 --tag 或换目录")
        return True

    def record(self, name, fp):
        with self.lock:
            self.inputs[name] = fp
            self._save()


def cmd_gen(A):
    bench = pathlib.Path(A.bench)
    qs = json.loads((bench / "questions" / "题目_主轮.json").read_text(encoding="utf-8"))
    if A.limit:
        qs = qs[: A.limit]
    ctx = contexts(bench, A.arm, qs)
    if A.dry:
        L = [len(v) for v in ctx.values()]
        print(f"{A.arm}: {len(L)} 题，上下文字数 均值 {sum(L) / len(L):.0f} 最小 {min(L)} 最大 {max(L)}")
        return
    head = contract(bench)
    outdir = bench / "sut" / f"out_{A.tag or (A.arm + SYS_SUFFIX)}"
    outdir.mkdir(parents=True, exist_ok=True)
    man = Manifest(outdir, gen_identity(A, bench), [outdir / f"{q['qid']}.json" for q in qs])
    prompts = {q["qid"]: f"{head}\n\n======== 正文 ========\n{ctx[q['qid']]}\n\n======== 问题 ========\n{q['qid']}：{q['question']}"
               for q in qs}
    print(f"[gen] outdir={outdir} identity={man.identity}", flush=True)

    reuse = {q["qid"]: man.reusable(q["qid"], outdir / f"{q['qid']}.json", sha(prompts[q["qid"]])) for q in qs}  # 先全量核对，再发任何调用

    def one(q):
        f = outdir / f"{q['qid']}.json"
        prompt = prompts[q["qid"]]
        if reuse[q["qid"]]:
            return q["qid"], "skip"
        for _ in range(3):
            try:
                obj = parse_json(chat(prompt, A.model))
                obj["qid"] = q["qid"]
                f.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
                man.record(q["qid"], sha(prompt))
                return q["qid"], "ok"
            except Exception as e:  # noqa: BLE001
                last = e
        return q["qid"], f"fail {last}"

    bad = 0
    with cf.ThreadPoolExecutor(A.workers) as ex:
        for qid, st in ex.map(one, qs):
            print(qid, st, flush=True)
            bad += st.startswith("fail")
    if bad:
        print(f"[gen] {bad} 题失败", file=sys.stderr)
        raise SystemExit(1)


def cmd_judge(A):
    bench = pathlib.Path(A.bench)
    req = bench / "semantic" / "req" / A.real
    out = bench / "semantic" / "out" / A.real
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(req.glob("*.md"))
    man = Manifest(out, {"kind": "judge", "real": A.real, "model": A.model, "system": False,
                         "bench_commit": bench_commit(bench)}, [out / (f.stem + ".json") for f in files])
    print(f"[judge] out={out} identity={man.identity}", flush=True)

    bodies = {f.stem: f.read_text(encoding="utf-8") for f in files}
    reuse = {f.stem: man.reusable(f.stem, out / (f.stem + ".json"), sha(bodies[f.stem])) for f in files}  # 先全量核对

    def one(f):
        g = out / (f.stem + ".json")
        body = bodies[f.stem]
        if reuse[f.stem]:
            return f.stem, "skip"
        for _ in range(3):
            try:
                obj = parse_json(chat(body, A.model, system=False))
                g.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
                man.record(f.stem, sha(body))
                return f.stem, "ok"
            except Exception as e:  # noqa: BLE001
                last = e
        return f.stem, f"fail {last}"

    bad = 0
    with cf.ThreadPoolExecutor(A.workers) as ex:
        for s, st in ex.map(one, files):
            print(s, st, flush=True)
            bad += st.startswith("fail")
    if bad:
        print(f"[judge] {bad} 条失败", file=sys.stderr)
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["gen", "judge"])
    ap.add_argument("bench")
    ap.add_argument("real", nargs="?")
    ap.add_argument("--arm", default="AGM")
    ap.add_argument("--tag")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry", action="store_true", help="只建上下文、报字数，不调模型")
    A = ap.parse_args()
    (cmd_gen if A.cmd == "gen" else cmd_judge)(A)


if __name__ == "__main__":
    main()
