# -*- coding: utf-8 -*-
"""保留扰动集 H1 生成（见 PREREG_HELDOUT.md）：事件句由 LLM（cline-pass/deepseek-v4.1-flash，thinking 关，temperature 1.0）
按段批量改写——与 perturb.py 的规则替换是两种生成方式。主体/属性/值/并存值/起因逐字保留由机械校验保证，校验不过重试 2 次，
仍不过则保留原句并计数。生成结果只落盘、不人工查看，评测前不据此改任何代码。
  python heldout_gen.py run [budget_sec]     （缓存命中即跳过，可断点续跑）
  python heldout_gen.py build                → out/heldout/corpus_h1.json（全部事件句改写）+ rewrite_map.json"""
import hashlib, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from cb_common import *  # noqa
sys.path[1:1] = [HMBD]
import llm as L  # noqa: E402
from lingshu_ng.chain.extract import extract  # noqa: E402

VARIANT = os.environ.get("HO_VARIANT", "h1")
D = os.path.join(OUT, "heldout" if VARIANT == "h1" else f"heldout_{VARIANT}"); os.makedirs(D, exist_ok=True)
L.CACHE = os.path.join(OUT, "llm", "cache"); L.COSTLOG = os.path.join(OUT, "llm", "cost.jsonl")   # 与本线同一账本
import llm_shared  # noqa: E402   2026-10-12：统一缓存 LINGSHU_LLM_CACHE（键不变，旧缓存只读回退），记前缀缓存命中
llm_shared.install(L, costlog=L.COSTLOG)
BUDGET_USD = 1.5
SPLIT = re.compile(r"(?<=[。])")
EV_MARK = ("首次确立为", "此后确立为", "调整为", "转为", " 移到了 ", "被撤销，此后不再保留取值", "出现两种并存的取值：", "的争议就此裁定为")
BANNED = ("首次确立为", "此后确立为", "调整为", "转为", "移到了", "被撤销", "并存的取值", "裁定为", "起因是")
SYS = ("你是中文写作者。下面每条是一句工作日志/叙事里的「状态变更记录」。请把每条改写成一句自然的中文叙述句。要求：\n"
       "1. 意思不变：首次定下某值、改成新值、搬到新位置、被撤销此后不再有值、出现两个并存的值尚未定下、争议最终定为某值——原句是哪种就写哪种；原句有起因就保留起因。\n"
       "2. 每条后面列出的「必须逐字出现」的字符串，要原样出现在改写句里（不改字、不拆开、不加引号）。\n"
       "3. 换一种与原句明显不同的说法和语序，不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。"
       "句式自由选择（倒装、口语、被动、把主体放在后面、把起因放在前面等都可以），各条风格可以不同。\n"
       "4. 不要引入任何别的名称或数值。\n"
       "5. 每条只写一句话，以句号结尾，句中不出现其他句号。\n"
       "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")


#: H2（PREREG_HELDOUT_H2.md）：另一种提示词——口语化的群聊/随笔/旁白，允许插话、先说结论再补细节、一句里带语气词；
#: temperature 1.3、只改写 test 文档（dev 文档 A1/B1 不生成）
SYS_H2 = ("你是一位写东西很随意的中文作者。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条用你自己的话、"
          "像在工作群聊里随口汇报、或在随笔/小说旁白里顺带一提那样，写成一句中文。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开）。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。"
          "可以口语、可以加语气词、可以先说结论再补原因、可以用问句或感叹句的语气，但整条只能是一句话。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以句号结尾，句中不出现其他句号、问号或叹号。\n"
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")
#: d3（dev 改写集，只改 dev 文档 A1/B1，用于迭代 v8 宽松抽取；2026-10-12 加）：叙事/旁白式长句，时间或场景开头、可插入修饰语
SYS_D3 = ("你是一位中文小说/纪实作者。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条写成叙事文字里的一句话，"
          "可以用时间或场景开头（如「到了那时」「会后」「那阵子」），可以在主体前后加修饰语，可以把起因放在句首或句中。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开）。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以句号结尾，句中不出现其他句号、问号或叹号。\n"
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")
#: H3（PREREG_HELDOUT_H3.md，保留集，只改 test 文档）：书面公文体——周报/会议纪要/公告/新闻通稿条目，可用被动、名词化、「经…」「鉴于…」「根据…」
SYS_H3 = ("你是一位负责写周报、会议纪要和对外公告的中文文秘。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条改写成正式书面语的一句话，"
          "风格像周报条目、会议纪要决议、通知公告或新闻通稿：可以用被动句、名词化表达、「经……」「鉴于……」「根据……」「为……」等书面连接，可以把主体放在句中或句末。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开）。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以句号结尾，句中不出现其他句号、问号或叹号。\n"
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")
#: H4（PREREG_HELDOUT_H4.md，保留集，只改 test 文档）：中英夹杂的工单/提交说明/站会速记体
SYS_H4 = ("你是一位习惯中英夹杂写工作记录的工程师或项目助理。下面每条是一件「某个东西的某个属性发生了变化」的事实。请把每条改写成一句中英夹杂的速记，"
          "风格像工单备注、commit message 的中文说明、站会速记或交接便条：可以夹英文动词或术语（如 switch、bump、rollback、deprecate、pin、update、move、TBD、pending），"
          "可以省略主语前的修饰，可以用冒号、括号或箭头（→）。要求：\n"
          "1. 事实不能变：是首次定下、改成新值、搬去新地方、作废不再有值、两个值并存还没定、还是争议最终定了某值——原句是哪种就写哪种；原句有起因就要带上起因（起因可以写成中文）。\n"
          "2. 每条后面列出的「必须逐字出现」的字符串要原样出现（不改字、不拆开、不翻译成英文）。\n"
          "3. 不要照搬原句的说法；不要使用这些词：首次确立为、此后确立为、调整为、转为、移到了、被撤销、并存的取值、裁定为、起因是。\n"
          "4. 不要引入任何别的名称或数值。\n"
          "5. 以句号结尾，句中不出现其他句号、问号或叹号。\n"
          "只输出一个 JSON 字符串数组，顺序与输入一致，不要任何其他文字。")
TEMP = {"h2": 1.3, "d2": 1.3, "d3": 1.2}.get(VARIANT, 1.0)
DEVDOCS = {"猎户项目", "青石镇"}
TEST_ONLY = VARIANT in ("h2", "h3", "h4")       # 保留集：只改 test 文档
DEV_ONLY = VARIANT in ("d2", "d3")        # dev 改写集：只改 dev 文档
SYSP = {"h2": SYS_H2, "d2": SYS_H2, "d3": SYS_D3, "h3": SYS_H3, "h4": SYS_H4}.get(VARIANT, SYS)
SEED0 = {"h2": 2000, "d2": 3000, "d3": 4000, "h3": 5000, "h4": 6000}.get(VARIANT)


def event_sents():
    """[(cid, 句号, 原句, 必须逐字串)]：原句用本分支抽取器解析（原句式全部在表内）。"""
    out = []
    for c in corpus():
        if (TEST_ONLY and c["doc"] in DEVDOCS) or (DEV_ONLY and c["doc"] not in DEVDOCS):
            continue
        for i, s in enumerate(SPLIT.split(c["text"])):
            if not any(m in s for m in EV_MARK):
                continue
            ev = [e for e in extract(s) if e.op != "mention"]
            assert ev, s
            e = ev[0]
            req = [x for x in (e.entity, None if e.attr == "位置" else e.attr, e.value, e.alt, e.reason) if x]
            out.append((c["cid"], i, s, req))
    return out


def by_seg(evs):
    g = {}
    for t in evs:
        g.setdefault(t[0], []).append(t)
    return g


def prompt(items):
    lines = [f"{k + 1}. 原句：{s}\n   必须逐字出现：" + "；".join(f"「{x}」" for x in req) for k, (_, _, s, req) in enumerate(items)]
    return [{"role": "system", "content": SYSP}, {"role": "user", "content": "\n".join(lines)}]


def parse(content, n):
    m = re.search(r"\[.*\]", content or "", re.S)
    try:
        arr = json.loads(m.group(0)) if m else None
    except ValueError:
        arr = None
    return arr if isinstance(arr, list) and len(arr) == n and all(isinstance(x, str) for x in arr) else None


def ok(sent, req):
    s = sent.strip()
    if VARIANT != "h1" and re.search(r"[？?！!]", s):
        return False
    return bool(s) and s.endswith("。") and s.count("。") == 1 and all(x in s for x in req)


def cost():
    try:
        return sum(json.loads(l)["cost"] for l in open(L.COSTLOG))
    except OSError:
        return 0.0


def gen_seg(items):
    """返回每句改写（None＝3 次都不过校验）。逐句判：某次调用里过校验的句子即采用，不过的再试。"""
    res = [None] * len(items)
    for attempt in range(3):
        todo = [k for k in range(len(items)) if res[k] is None]
        if not todo or cost() > BUDGET_USD:
            break
        sub = [items[k] for k in todo]
        r = L.call(prompt(sub), max_tokens=2000, temperature=TEMP, thinking=False, tag=f"cb:heldout_gen_{VARIANT}",
                   seed=(None if attempt == 0 else 100 + attempt) if VARIANT == "h1" else SEED0 + attempt)
        arr = parse(r.get("content"), len(sub))
        if arr is None:
            continue
        for k, s in zip(todo, arr):
            if ok(s, items[k][3]):
                res[k] = s.strip()
    return res


def run(budget):
    g = by_seg(event_sents()); t0 = time.time()
    resp = load(os.path.join(D, "gen_raw.json"), {})
    todo = [cid for cid in g if cid not in resp]

    def one(cid):
        if time.time() - t0 > budget or cost() > BUDGET_USD:
            return None
        return cid, gen_seg(g[cid])
    from concurrent.futures import as_completed
    ex = ThreadPoolExecutor(6)
    futs = [ex.submit(one, cid) for cid in todo]
    try:
        for f in as_completed(futs, timeout=budget + 20):
            r = f.result()
            if r:
                resp[r[0]] = r[1]
                dump(os.path.join(D, "gen_raw.json"), resp)     # 逐段落盘：被外层超时杀掉也不丢
    except Exception as e:  # noqa: BLE001
        print("stop:", type(e).__name__, flush=True)
    ex.shutdown(wait=False, cancel_futures=True)
    n = sum(len(v) for v in resp.values()); bad = sum(x is None for v in resp.values() for x in v)
    print(f"segs {len(resp)}/{len(g)} sents {n} fail {bad} cost_total ${cost():.4f}", flush=True)


def build():
    g = by_seg(event_sents()); resp = load(os.path.join(D, "gen_raw.json"))
    assert set(resp) == set(g), (len(resp), len(g))
    rw = {}
    for cid, items in g.items():
        for (c, i, s, req), new in zip(items, resp[cid]):
            rw[f"{c}|{i}"] = {"orig": s, "new": new, "req": req}
    out = []
    for c in corpus():
        sents = SPLIT.split(c["text"])
        if (TEST_ONLY and c["doc"] in DEVDOCS) or (DEV_ONLY and c["doc"] not in DEVDOCS):
            out.append(c); continue
        for i in range(len(sents)):
            r = rw.get(f"{c['cid']}|{i}")
            if r and r["new"]:
                sents[i] = r["new"]
        out.append(dict(c, text="".join(sents)))
    dump(os.path.join(D, "rewrite_map.json"), rw)
    dump(os.path.join(D, f"corpus_{VARIANT}.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    fails = sum(1 for r in rw.values() if not r["new"])
    print(f"event_sents {len(rw)} fallback_orig {fails} corpus_sha {h}")


if __name__ == "__main__":
    if sys.argv[1] == "run":
        run(float(sys.argv[2]) if len(sys.argv) > 2 else 100)
    else:
        build()
