"""考卷 C：LongMemEval（cleaned，MIT）接成本站任务契约 —— 多场景记忆域题包。

来源与登记见 taskpacks/longmemeval/SOURCE.md（URL、HF 提交、SHA-256、LICENSE 原文）。不改题、不改答案键。

本模块负责：
- 读题包（LongMemEval_S cleaned：500 个实例，每个实例自带一份独立 haystack ≈48 个会话）
- **场景 id**：按「证据会话共享」做并查集：共享任一 answer_session_id 的实例并为同一场景（_abs 变体与原题会并到一起），
  其余每个实例＝一个独立场景（不同事实组合）。场景 id 显式写进每题记录（`scenario_id`），供 verdict_v3 按场景聚类。
- 灌库语料：把 haystack 渲染成 adapter 契约的 Session/Turn（每个会话一个虚拟文件 `<session_id>.md`，
  第 1 行 `Session date: …`，每轮以 `**user:**` / `**assistant:**` 标记行开头，行号 1 起）。插件 ingest 的就是它。
- 三个受控臂（端到端验证计划 §5 的三类夹具中的两类 + 朴素参照）：
    null   ＝ 不给材料（B0 / 无信息夹具，兼作闭卷泄漏读数）
    bm25   ＝ 朴素 BM25（harness.plugins_builtin.BM25Plugin，块长改 1,500 字符），材料上限 12,000 字符
    oracle ＝ 正确信息上限：直接给金标证据会话（answer_session_ids 对应会话全文，上限 60,000 字符；超限时保留 has_answer 轮及其前后各 2 轮）
- 生成器提示词：上游 src/generation/run_generation.py 的 direct 模板（逐字）。
- 判分：上游 src/evaluation/evaluate_qa.py 的 get_anscheck_prompt（逐字，按题型分模板，_abs 用拒答模板），yes→1 / no→0。
  偏差（如实登记）：上游判官是 gpt-4o-2024-08-06；本站只能用 cline-pass/deepseek-v4.1-flash，须锚题自证（见 judge_anchor_*）。
- 主要指标：每次运行 0–100 分 ＝ 100 × 判对题数 / 题数（metric.kind="binary"，verdict_v3 统一换算）。

CLI（结果逐题落盘，可续跑）：
  python -m harness.examC subset --n 96 --seed 20261010 --out taskpacks/longmemeval/pilot/subset.json
  python -m harness.examC run --subset … --arm bm25 --rerun 1 --out taskpacks/longmemeval/pilot_runs
  python -m harness.examC anchors --subset … --out …
"""
from __future__ import annotations
import argparse, hashlib, json, os, random, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PACK = Path(os.environ.get("PES_LME", REPO / "taskpacks" / "longmemeval"))
RAW_S = PACK / "raw" / "longmemeval_s_cleaned.json"
SOURCE_PIN = {"hf_repo": "xiaowu0162/longmemeval-cleaned", "hf_commit": "98d7416c24c778c2fee6e6f3006e7a073259d48f",
              "s_sha256": "d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442",
              "oracle_sha256": "821a2034d219ab45846873dd14c14f12cfe7776e73527a483f9dac095d38620c",
              "gh_commit": "9e0b455f4ef0e2ab8f2e582289761153549043fc", "license": "MIT"}
TASKSET_ID = "pes/memory/examC/longmemeval-s-cleaned@98d7416"

BM25_CAP = 12000
BM25_BLOCK = 1500
BM25_K = 40
ORACLE_CAP = 60000
GEN_TEMPERATURE = 0.7
GEN_MAX_TOKENS = 800
JUDGE_MAX_TOKENS = 400
ARMS = ("null", "bm25", "oracle", "leakprobe")
MARK = {"user": "**user:**", "assistant": "**assistant:**"}

# ---------------- 上游提示词（逐字复制，来源 commit 9e0b455） ----------------
GEN_TEMPLATE = ('I will give you several history chats between you and a user. Please answer the question based on the '
                'relevant chat history.\n\n\nHistory Chats:\n\n{}\n\nCurrent Date: {}\nQuestion: {}\nAnswer:')
# 泄漏探针（本站自拟，非上游）：明示题源，看模型能否凭记忆背出参考答案。
LEAK_TEMPLATE = ('The following question comes from the public benchmark LongMemEval (Wu et al., 2024; ICLR 2025), '
                 'whose chat histories and reference answers are published on GitHub and Hugging Face. You are NOT given '
                 'the chat history. If you remember this benchmark item, state its reference answer; otherwise give your '
                 'single best guess. Do not refuse.\n\nQuestion date: {}\nQuestion: {}\nAnswer:')


def get_anscheck_prompt(task, question, answer, response, abstention=False):
    if not abstention:
        if task in ['single-session-user', 'single-session-assistant', 'multi-session']:
            template = "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. \n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."
            prompt = template.format(question, answer, response)
        elif task == 'temporal-reasoning':
            template = "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a subset of the information required by the answer, answer no. In addition, do not penalize off-by-one errors for the number of days. If the question asks for the number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., predicting 19 days when the answer is 18), the model's response is still correct. \n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."
            prompt = template.format(question, answer, response)
        elif task == 'knowledge-update':
            template = "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response contains the correct answer. Otherwise, answer no. If the response contains some previous information along with an updated answer, the response should be considered as correct as long as the updated answer is the required answer.\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."
            prompt = template.format(question, answer, response)
        elif task == 'single-session-preference':
            template = "I will give you a question, a rubric for desired personalized response, and a response from a model. Please answer yes if the response satisfies the desired response. Otherwise, answer no. The model does not need to reflect all the points in the rubric. The response is correct as long as it recalls and utilizes the user's personal information correctly.\n\nQuestion: {}\n\nRubric: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only."
            prompt = template.format(question, answer, response)
        else:
            raise NotImplementedError(task)
    else:
        template = "I will give you an unanswerable question, an explanation, and a response from a model. Please answer yes if the model correctly identifies the question as unanswerable. The model could say that the information is incomplete, or some other information is given but the asked information is not.\n\nQuestion: {}\n\nExplanation: {}\n\nModel Response: {}\n\nDoes the model correctly identify the question as unanswerable? Answer yes or no only."
        prompt = template.format(question, answer, response)
    return prompt


# ---------------- 题包读取与场景分组 ----------------
def load_raw(path=RAW_S) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def is_abs(inst) -> bool:
    return inst["question_id"].endswith("_abs")


def scenario_ids(instances: list[dict]) -> dict:
    """并查集：共享任一证据会话（answer_session_ids）的实例为同一场景。返回 {question_id: scenario_id}。
    scenario_id = 'lme:' + 组内字典序最小的 question_id（去 _abs 后缀不影响，取原 id）。"""
    parent = {x["question_id"]: x["question_id"] for x in instances}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    owner = {}
    for x in instances:
        for sid in x["answer_session_ids"]:
            if sid in owner:
                ra, rb = find(owner[sid]), find(x["question_id"])
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
            else:
                owner[sid] = x["question_id"]
    groups = {}
    for q in parent:
        groups.setdefault(find(q), []).append(q)
    out = {}
    for root, qs in groups.items():
        sid = "lme:" + min(qs)
        for q in qs:
            out[q] = sid
    return out


def item_record(inst: dict, scen: str) -> dict:
    """本站题目记录（答案键与判分器版本随记录走）。scenario_id 显式写入。"""
    return {"item_id": inst["question_id"], "scenario_id": scen, "question_type": inst["question_type"],
            "abstention": is_abs(inst), "question": inst["question"], "answer": str(inst["answer"]),
            "question_date": inst["question_date"], "weight": 1.0,
            "gold_sessions": list(inst["answer_session_ids"]), "scorer": "lme-anscheck@9e0b455/flash"}


def make_subset(instances, n, seed) -> list[str]:
    """简单随机抽 n 个场景（按场景抽，场景内全部题入选），返回 question_id 列表（按场景再按题排序）。"""
    sc = scenario_ids(instances)
    scen = sorted(set(sc.values()))
    rng = random.Random(seed)
    pick = set(rng.sample(scen, n))
    return sorted((q for q, s in sc.items() if s in pick), key=lambda q: (sc[q], q))


# ---------------- 灌库语料（adapter 契约） ----------------
def render_sessions(inst: dict) -> list[dict]:
    out = []
    for sid, date, sess in zip(inst["haystack_session_ids"], inst["haystack_dates"], inst["haystack_sessions"]):
        lines = [f"Session date: {date}"]
        turns = [{"idx": 0, "role": "meta", "start_line": 1, "end_line": 1, "text": lines[0]}]
        for j, t in enumerate(sess, 1):
            st = len(lines) + 1
            body = (t.get("content") or "").split("\n")
            lines.append(MARK.get(t["role"], f"**{t['role']}:**"))
            lines += body
            turns.append({"idx": j, "role": t["role"], "start_line": st, "end_line": len(lines),
                          "text": "\n".join(lines[st - 1:]), "has_answer": bool(t.get("has_answer"))})
        out.append({"session_id": f"{sid}.md", "date": date, "turns": turns})
    return out


# ---------------- 三臂材料 ----------------
def material_null(inst) -> list[dict]:
    return []


def material_bm25(inst, cap=BM25_CAP, rec=None) -> list[dict]:
    from .plugins_builtin import BM25Plugin

    class _B(BM25Plugin):
        BLOCK_CHARS = BM25_BLOCK
    sessions = render_sessions(inst)
    dates = {s["session_id"]: s["date"] for s in sessions}
    p = _B()
    p.ingest(sessions, _NullRec())
    hits = p.recall(inst["question"], BM25_K, _NullRec())
    out, used = [], 0
    for h in hits:
        t = h["text"]
        if used + len(t) > cap:
            continue
        f = h["source"].split("#")[0]
        out.append({"text": t, "source": h["source"], "date": dates.get(f, ""), "score": h.get("score")})
        used += len(t)
    return out


def material_oracle(inst, cap=ORACLE_CAP) -> list[dict]:
    gold = set(inst["answer_session_ids"])
    sessions = [s for s in render_sessions(inst) if s["session_id"][:-3] in gold]
    full = [{"text": "\n".join(t["text"] for t in s["turns"][1:]), "source": s["session_id"], "date": s["date"],
             "turns": s["turns"]} for s in sessions]
    if sum(len(m["text"]) for m in full) <= cap:
        return [{k: m[k] for k in ("text", "source", "date")} for m in full]
    out = []
    for m in full:   # 超限：只留 has_answer 轮 ±2
        tr = m["turns"][1:]
        keep = sorted({j for i, t in enumerate(tr) if t.get("has_answer") for j in range(max(0, i - 2), min(len(tr), i + 3))})
        if keep:
            out.append({"text": "\n".join(tr[j]["text"] for j in keep), "source": m["source"], "date": m["date"]})
    return out


MATERIAL = {"null": material_null, "bm25": material_bm25, "oracle": material_oracle}


def format_history(material: list[dict]) -> str:
    if not material:
        return "(no chat history is available)"
    ms = sorted(material, key=lambda m: (m.get("date", ""), m.get("source", "")))   # 按时间排，同上游
    return "\n\n".join(f"### Session Date: {m.get('date', '')}\nSession Content:\n{m['text']}" for m in ms)


def gen_messages(inst, material) -> list[dict]:
    return [{"role": "user", "content": GEN_TEMPLATE.format(format_history(material), inst["question_date"],
                                                            inst["question"])}]


def leak_messages(inst) -> list[dict]:
    return [{"role": "user", "content": LEAK_TEMPLATE.format(inst["question_date"], inst["question"])}]


def judge_messages(inst, response) -> list[dict]:
    return [{"role": "user", "content": get_anscheck_prompt(inst["question_type"], inst["question"], str(inst["answer"]),
                                                            response, abstention=is_abs(inst))}]


def parse_yes(raw: str):
    s = (raw or "").strip().lower()
    s = re.sub(r"[^a-z]", " ", s).split()
    if not s:
        return None
    if s[0] in ("yes", "no"):
        return 1 if s[0] == "yes" else 0
    if "yes" in s and "no" not in s:
        return 1
    if "no" in s and "yes" not in s:
        return 0
    return None


class _NullRec:
    def event(self, *a, **k):
        return {}


# ---------------- 任务契约（手册 §3.1 七项） ----------------
def task_contract() -> dict:
    return {
        "taskset_id": TASKSET_ID, "source": SOURCE_PIN,
        "1_initial_env_input": "每场景：从空库开始，按时间顺序灌入该实例 haystack 的全部会话（render_sessions，约 48 个会话、中位 49 万字符）；"
                               "插件之外的宿主/模型/提示词/预算一律相同。题目在灌库结束后提出，附 question_date。",
        "2_expected_final_state": "每题一段自然语言回答；插件库内只含本场景语料（场景之间清库/从快照恢复）。",
        "3_acceptance": "判官（上游 get_anscheck_prompt 逐字，按题型）对回答判 yes；_abs 题须识别为无法回答。",
        "4_forbidden_side_effects": "跨场景串库（A 场景记忆出现在 B 场景）；读取答案键/题包原文件；联网；写出插件沙箱目录；修改宿主配置。",
        "5_partial_completion": "无部分分：判 yes=1、no=0；判官输出无法解析→该题判分失败，整对（pair）作废重判，不按 0 计。",
        "6_timeout_dependency_interrupt": "单次 LLM 调用按 llm.py 退避重试（≤30 次）；仍失败→该 pair 记 invalid（外部故障），"
                                          "按样本计划补跑上限 2 次整对重跑；达到上限仍缺→SAMPLE_PLAN_INCOMPLETE（实验无效/待重跑）。",
        "7_scorer_version_limits": "lme-anscheck@9e0b455 提示词 + cline-pass/deepseek-v4.1-flash（temperature 0，单判官）。"
                                   "已知局限：上游校准的是 gpt-4o 判官（论文报与人工一致率 >97%），flash 判官未经人工一致率校准，"
                                   "只做了锚题自证（金标答案→应判 yes；他题答案→应判 no）；preference 题为评分细则式判分，主观性最高；"
                                   "题包 2024-10 起公开，存在被训练见过的污染风险（见泄漏抽检）。",
    }


# ---------------- verdict_v3 接口 ----------------
def to_pairs(results: dict, base_arm: str, plug_arm: str, items: dict) -> list[dict]:
    """results[arm][rerun][item_id] = score(0/1|None)。按 (scenario, rerun) 组 pair。"""
    pairs = []
    reruns = sorted(set(results.get(base_arm, {})) & set(results.get(plug_arm, {})))
    scen = {}
    for q, it in items.items():
        scen.setdefault(it["scenario_id"], []).append(q)
    for r in reruns:
        B, P = results[base_arm][r], results[plug_arm][r]
        for s, qs in sorted(scen.items()):
            if not all(q in B and q in P for q in qs):
                continue
            ok = all(B[q] is not None and P[q] is not None for q in qs)
            pairs.append({"pair_id": f"{s}#r{r}", "scenario_id": s, "rerun": r, "valid": ok,
                          "invalid_reason": None if ok else "judge_unparsed",
                          "base": {q: B[q] for q in qs}, "plug": {q: P[q] for q in qs}})
    return pairs


def make_spec(analysis_id, pairs, items, params=None) -> dict:
    from . import verdict_v3 as V
    w = {q: it["weight"] for q, it in items.items()}
    return {"analysis_id": analysis_id, "metric": {"kind": "binary", "scale_max": 1}, "weights": w,
            "weights_sha256": V.weights_sha256(w), "pairs": pairs, "scenario_weighting": "equal",
            "params": params or {}}


# ---------------- 运行器 ----------------
def _item_path(out: Path, arm, rerun, qid) -> Path:
    return out / arm / f"r{rerun}" / f"{qid}.json"


def run_one(inst, arm, rerun, out: Path, gen, judge):
    p = _item_path(out, arm, rerun, inst["question_id"])
    if p.exists():
        d = json.loads(p.read_text())
        if d.get("score") is not None:
            return d
    if arm == "leakprobe":
        mat, msgs = [], leak_messages(inst)
    else:
        mat = MATERIAL[arm](inst)
        msgs = gen_messages(inst, mat)
    g = gen.chat(msgs)
    j = judge.chat(judge_messages(inst, g["content"]))
    d = {"item_id": inst["question_id"], "scenario_id": inst["_scenario_id"], "arm": arm, "rerun": rerun,
         "question_type": inst["question_type"], "abstention": is_abs(inst),
         "material_chars": sum(len(m["text"]) for m in mat), "material_sources": [m.get("source") for m in mat],
         "gold_hit": bool(set(inst["answer_session_ids"]) & {(m.get("source") or "").split("#")[0][:-3] for m in mat}),
         "prompt_sha256": hashlib.sha256(json.dumps(msgs, ensure_ascii=False).encode()).hexdigest(),
         "answer": g["content"], "gen_usage": g["usage"], "gen_cost": g["cost_usd"], "gen_finish": g["finish_reason"],
         "judge_raw": j["content"], "judge_usage": j["usage"], "judge_cost": j["cost_usd"],
         "score": parse_yes(j["content"]), "model_served": g["model_served"], "ts": time.time()}
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    os.replace(tmp, p)
    return d


def load_subset(path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["instances"]


def cmd_subset(a):
    inst = load_raw()
    sc = scenario_ids(inst)
    ids = make_subset(inst, a.n, a.seed)
    by = {x["question_id"]: x for x in inst}
    sel = []
    for q in ids:
        x = dict(by[q]); x["_scenario_id"] = sc[q]; sel.append(x)
    meta = {"taskset_id": TASKSET_ID, "source": SOURCE_PIN, "n_scenarios_total": len(set(sc.values())),
            "n_instances_total": len(inst), "subset_seed": a.seed, "n_scenarios": a.n, "question_ids": ids,
            "items": [item_record(x, x["_scenario_id"]) for x in sel]}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({**meta, "instances": sel}, ensure_ascii=False))
    Path(a.out).with_suffix(".items.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(json.dumps({k: meta[k] for k in ("n_scenarios_total", "n_instances_total", "n_scenarios")}), len(ids))


def cmd_run(a):
    from . import llm
    inst = load_subset(a.subset)
    if a.limit:
        scen = sorted({x["_scenario_id"] for x in inst})[: a.limit]
        inst = [x for x in inst if x["_scenario_id"] in set(scen)]
    if getattr(a, "reverse", False):
        inst = inst[::-1]
    out = Path(a.out)
    gen = llm.Client("generator", temperature=GEN_TEMPERATURE, max_tokens=GEN_MAX_TOKENS)
    judge = llm.Client("judge", temperature=0.0, max_tokens=JUDGE_MAX_TOKENS)
    lock = threading.Lock()
    done = [0]

    def job(x):
        try:
            d = run_one(x, a.arm, a.rerun, out, gen, judge)
        except Exception as e:   # 外部故障：留空，续跑补
            d = {"error": repr(e)[:200]}
        with lock:
            done[0] += 1
        return d
    with ThreadPoolExecutor(a.workers) as ex:
        res = list(ex.map(job, inst))
    sc = [d.get("score") for d in res]
    print(json.dumps({"arm": a.arm, "rerun": a.rerun, "n": len(res), "yes": sum(1 for s in sc if s == 1),
                      "none": sum(1 for s in sc if s is None), "calls": llm.TOTALS["calls"],
                      "cost_usd": round(llm.TOTALS["cost_usd"], 4)}, ensure_ascii=False))


def cmd_anchors(a):
    """判官锚题自证：金标答案作回答 → 应 yes；另一场景同题型的答案作回答 → 应 no。"""
    from . import llm
    inst = load_subset(a.subset)[: a.n]
    judge = llm.Client("judge", temperature=0.0, max_tokens=JUDGE_MAX_TOKENS)
    out = Path(a.out) / "anchors"
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    jobs = []
    for x in inst:
        jobs.append((x, "pos", str(x["answer"]) if not is_abs(x) else "I don't know; the chat history does not mention this.", 1))
        others = [y for y in inst if y["question_id"] != x["question_id"] and not is_abs(y)]
        neg = rng.choice(others)
        jobs.append((x, "neg", str(neg["answer"]) if not is_abs(x) else str(neg["answer"]), 0))

    def job(t):
        x, kind, resp, want = t
        p = out / f"{x['question_id']}.{kind}.json"
        if p.exists():
            return json.loads(p.read_text())
        j = judge.chat(judge_messages(x, resp))
        d = {"item_id": x["question_id"], "kind": kind, "response": resp, "want": want, "raw": j["content"],
             "got": parse_yes(j["content"]), "question_type": x["question_type"], "abstention": is_abs(x)}
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1))
        return d
    with ThreadPoolExecutor(a.workers) as ex:
        res = list(ex.map(job, jobs))
    ok = sum(1 for d in res if d["got"] == d["want"])
    print(json.dumps({"anchors": len(res), "agree": ok, "rate": round(ok / max(1, len(res)), 3)}))


def collect(out: Path, arms=("null", "bm25", "oracle", "leakprobe")) -> dict:
    """读回逐题结果：{arm: {rerun: {item_id: score}}}，附逐题详情。"""
    res, det = {}, {}
    for arm in arms:
        for rd in sorted((out / arm).glob("r*")) if (out / arm).exists() else []:
            r = int(rd.name[1:])
            for f in rd.glob("*.json"):
                d = json.loads(f.read_text())
                res.setdefault(arm, {}).setdefault(r, {})[d["item_id"]] = d.get("score")
                det[(arm, r, d["item_id"])] = d
    return {"scores": res, "detail": det}


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def _var(xs):
    xs = list(xs)
    if len(xs) < 2:
        return float("nan")
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def pilot_analysis(subset_path, out: Path, z=1.959964, target_hw=5.0) -> dict:
    """试跑读数：三臂绝对分、泄漏、锚题、verdict_v3 区间、方差分解与样本量反推。"""
    import math
    from . import verdict_v3 as V
    meta = json.loads(Path(subset_path).with_suffix(".items.json").read_text())
    items = {it["item_id"]: it for it in meta["items"]}
    col = collect(out)
    S, det = col["scores"], col["detail"]
    rep = {"taskset_id": TASKSET_ID, "n_items": len(items), "n_scenarios": len({i["scenario_id"] for i in items.values()})}
    # 1 绝对分
    absr = {}
    for arm, rr in S.items():
        for r, sc in rr.items():
            vals = [v for q, v in sc.items() if v is not None and q in items]
            bytype = {}
            for q, v in sc.items():
                if v is None or q not in items:
                    continue
                t = items[q]["question_type"] + ("_abs" if items[q]["abstention"] else "")
                bytype.setdefault(t, []).append(v)
            costs = [(det[(arm, r, q)].get("gen_cost") or 0) + (det[(arm, r, q)].get("judge_cost") or 0) for q in sc]
            ptok = [((det[(arm, r, q)].get("gen_usage") or {}).get("prompt_tokens") or 0) for q in sc]
            absr[f"{arm}/r{r}"] = {"n": len(vals), "unparsed": sum(1 for v in sc.values() if v is None),
                                   "score_0_100": round(100 * _mean(vals), 1) if vals else None,
                                   "by_type": {t: f"{sum(v)}/{len(v)}" for t, v in sorted(bytype.items())},
                                   "mean_cost_usd_per_item": round(_mean(costs), 6) if costs else None,
                                   "mean_gen_prompt_tokens": round(_mean(ptok)) if ptok else None,
                                   "gold_hit_rate": round(_mean(1.0 if det[(arm, r, q)].get("gold_hit") else 0.0 for q in sc), 3)
                                   if arm in ("bm25", "oracle") else None}
    rep["arms"] = absr
    # 2 泄漏：非拒答题闭卷答对
    leak = {}
    for arm in ("null", "leakprobe"):
        sc = S.get(arm, {}).get(1, {})
        na = [v for q, v in sc.items() if q in items and not items[q]["abstention"] and v is not None]
        leak[arm] = {"non_abs_correct": f"{sum(na)}/{len(na)}", "rate": round(_mean(na), 3) if na else None}
    rep["leak"] = leak
    # 3 锚题
    an = [json.loads(f.read_text()) for f in (out / "anchors").glob("*.json")] if (out / "anchors").exists() else []
    rep["anchors"] = {"n": len(an), "agree": sum(1 for d in an if d["got"] == d["want"]),
                      "disagree": [(d["item_id"], d["kind"], d["raw"][:40]) for d in an if d["got"] != d["want"]]}
    # 4 verdict_v3 区间（r1；试跑 min_reruns 放宽为 1，只作方法试验）
    comps = {}
    for base, plug in (("null", "bm25"), ("null", "oracle"), ("bm25", "oracle")):
        if base not in S or plug not in S:
            continue
        r1 = {base: {1: S[base].get(1, {})}, plug: {1: S[plug].get(1, {})}}
        pairs = to_pairs(r1, base, plug, items)
        spec = make_spec(f"pes/memory/examC-pilot/{plug}-vs-{base}/r1", pairs, items, params={"min_reruns": 1})
        res = V.analyze(spec)
        tab = V.scenario_table(spec)["scenarios"]
        d = [e["d"] for e in tab.values()]
        # 场景内重跑方差：r1 与 r2 都有的场景
        both = []
        if 2 in S[base] and 2 in S[plug]:
            r2 = {base: {1: S[base][1], 2: S[base][2]}, plug: {1: S[plug][1], 2: S[plug][2]}}
            p12 = [p for p in to_pairs(r2, base, plug, items) if p["valid"]]
            byS = {}
            for p in p12:
                sb = 100 * _mean(p["base"].values()); sp = 100 * _mean(p["plug"].values())
                byS.setdefault(p["scenario_id"], {})[p["rerun"]] = sp - sb
            both = [v[1] - v[2] for v in byS.values() if 1 in v and 2 in v]
        var_tot = _var(d)
        var_w = (_mean(x * x for x in both) / 2) if both else float("nan")
        var_b = max(var_tot - var_w, 0.0) if both else float("nan")
        plan = {}
        for R in (1, 3, 5):
            v = var_b + var_w / R if both else var_tot
            plan[f"R{R}"] = math.ceil(z * z * v / target_hw ** 2)
        comps[f"{plug}_vs_{base}"] = {
            "verdict": {k: res.get(k) for k in ("run_state", "release_state", "capability_observed", "estimate",
                                                 "interval", "half_width", "base_abs", "plug_abs", "n_scenarios",
                                                 "reruns_per_scenario")},
            "errors": [e["code"] for e in res.get("errors", [])],
            "sd_scenario_diff_r1": round(math.sqrt(var_tot), 2), "n_rerun_pairs": len(both),
            "sd_within_rerun": round(math.sqrt(var_w), 2) if both else None,
            "sd_between": round(math.sqrt(var_b), 2) if both else None,
            "scenarios_needed_for_hw5": plan}
    rep["comparisons"] = comps
    return rep


def cmd_analyze(a):
    rep = pilot_analysis(a.subset, Path(a.out))
    Path(a.report).write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps(rep, ensure_ascii=False, indent=1)[:6000])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="harness.examC")
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("subset"); s.add_argument("--n", type=int, default=96); s.add_argument("--seed", type=int, default=20261010)
    s.add_argument("--out", required=True); s.set_defaults(f=cmd_subset)
    r = sp.add_parser("run"); r.add_argument("--subset", required=True); r.add_argument("--arm", choices=ARMS, required=True)
    r.add_argument("--rerun", type=int, default=1); r.add_argument("--out", required=True)
    r.add_argument("--workers", type=int, default=4); r.add_argument("--limit", type=int, default=0)
    r.add_argument("--reverse", action="store_true", help="倒序处理（第二个进程并行补同一臂时用）"); r.set_defaults(f=cmd_run)
    an = sp.add_parser("anchors"); an.add_argument("--subset", required=True); an.add_argument("--n", type=int, default=32)
    an.add_argument("--out", required=True); an.add_argument("--workers", type=int, default=4); an.set_defaults(f=cmd_anchors)
    z = sp.add_parser("analyze"); z.add_argument("--subset", required=True); z.add_argument("--out", required=True)
    z.add_argument("--report", required=True); z.set_defaults(f=cmd_analyze)
    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
