# -*- coding: utf-8 -*-
"""chain-r24 H20：换实体、换取值 + 分块换名（PREREG_R24.md；seed 27000；由 h19_map.py 改值表/名库/种子，口径同 H19）。对 HMB chain 语料 test 文档（dev 文档 猎户项目/青石镇 不动）：
取值与并存值做固定映射（与 H8–H19 目标值、H19 别名都不同）；主体（项目名/人名/模块名）按「段号块」换名：同一文档每 BLOCK=3 段一个块，
块内一致、块间不同（模拟真实记忆流里主体不断换新：冷启动主体占事件句约 1/3，H8–H18 只有约 4%）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）。不调用被测代码。
  python h20_map.py   → out/heldout_h20/entity_value_map.json + corpus_h20base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h20"); os.makedirs(D, exist_ok=True)
DEVDOCS = {"猎户项目", "青石镇"}
BLOCK = 3
SUBJ = ["流明", "织女", "缓存模块", "杜衡", "林昭", "沈砚", "阿桑", "白芨", "雪姑", "陆平", "程雪", "九爷", "顾九"]
VALW = {
    "低落": "怅然若失", "犹豫": "瞻前顾后", "戒备": "疑神疑鬼", "欣慰": "喜上眉梢", "释然": "心头石落", "平静": "不动声色", "愤怒": "火冒三丈", "焦虑": "心急如焚",
    "祠堂": "族堂", "渡口": "芦花滩", "驿站": "传舍", "粮仓": "义仓", "集市": "圩场", "磨坊": "水磨房", "后山": "南麓坡", "码头": "靠船坞",
    "暧昧": "似是而非", "沉默": "默不作声", "反对": "极力阻挠", "支持": "全力扶持", "中立": "两边不靠", "观望": "坐山观虎",
    "外人": "外乡人",
}
DEPS = {"bbolt": "shrikevault", "rocksdb": "lapwingdb", "badger": "voleledger", "sled": "siskinstore", "sqlite": "dunlinbase", "lmdb": "avocetkv", "redis": "godwitcache"}
SECS = {"21600": "25380", "300": "2790", "1800": "5130", "3600": "7470", "900": "3510", "7200": "16740", "10800": "48870", "600": "1830"}
KEYS = {"batch_size": "heap_size", "retry": "retry_tally", "max_conn": "conn_quota", "timeout_ms": "stall_ms"}
KNUM = {"16": "73", "32": "109", "64": "197", "128": "389", "256": "659"}
FUNCS = {"load": "hoist", "get": "cull", "fetch": "summon", "resolve": "mediate", "sync": "splice"}
PARAMS = {"key": "kbin", "ttl": "longevity", "tag": "crest", "refresh": "revamp", "force": "insist", "id": "seqno"}

SURN = list("晁庹郜詹钮佟宓殳裘濮蒯隗乜仉蓟郏邴靳暴揭")
GIV = list("琛璠彧昶琨瑄瓒珞霖淇泓沁漪曦晔煦玹瑀")
PROJ = list("嵘崧峥岷溟湍漾泾淞汾涔浔潍泮澧瀚嵋崆峒")
MOD = ["锁扣", "卷轴", "滑轮", "活塞", "摆锤", "转盘", "阀门", "线圈", "飞轮", "刻度", "托盘", "挂钩", "垫圈", "螺母", "连杆", "轴承", "滤芯", "喷嘴", "导轨", "闩销", "棘轮", "凸轮"]
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")


def build():
    rng = random.Random(27000)
    _all = "".join(c["text"] + c["doc"] for c in corpus())
    nblk = max(c["seq"] for c in corpus()) // BLOCK + 1
    prev = set()
    for v in range(8, 20):
        m = json.load(open(os.path.join(OUT, f"heldout_h{v}", "entity_value_map.json"), encoding="utf-8"))
        for k in ("words", "deps", "secs", "keys", "knum", "funcs", "params", "alias"):
            prev |= set(m.get(k, {}).values())
    used = set(); alias = {}

    def fresh(kind):
        for _ in range(10000):
            if kind == "proj":
                t = rng.choice(PROJ) + rng.choice(PROJ)
            elif kind == "mod":
                t = rng.choice(MOD) + "模块"
            else:
                t = rng.choice(SURN) + rng.choice(GIV) + (rng.choice(GIV) if rng.random() < .3 else "")
            if t in used or t in _all or t in prev or any(t in p_ or p_ in t for p_ in prev if not p_.isdigit() and len(p_) > 1) or len(set(t)) < len(t):
                continue
            if any(t in u or u in t for u in used):
                continue
            used.add(t); return t
        raise RuntimeError(kind)
    for b in range(nblk):
        for s in SUBJ:
            alias[f"{s}@{b}"] = fresh("proj" if s in ("流明", "织女") else "mod" if s == "缓存模块" else "person")
    vals = list(VALW.values()) + list(DEPS.values())
    for t in vals:
        assert t not in _all, t
        assert not any(t in a or a in t for a in alias.values()), ("overlap", t)
    for t in list(SECS.values()) + list(KNUM.values()):
        assert not re.search(r"(?<!\d)" + t + r"(?!\d)", _all), ("num in corpus", t)
    for d_ in (VALW, DEPS, SECS, KEYS, KNUM, FUNCS, PARAMS, alias):
        for t in d_.values():
            assert t not in prev, ("reused", t)
    rngc = random.Random(27001); cfgmap = {}; cused = set()

    def cfg(m):
        k = m.group(1)
        if k not in cfgmap:
            while True:
                v = str(rngc.randrange(100000, 1000000))
                if v not in cused and v not in _all:
                    cused.add(v); break
            cfgmap[k] = v
        return "cfg_" + cfgmap[k]

    def kv(m):
        return KEYS[m.group(1)] + "=" + KNUM.get(m.group(2), m.group(2))

    def fn(m):
        ps = ", ".join(PARAMS.get(p.strip(), p.strip()) for p in m.group(2).split(",") if p.strip())
        return FUNCS[m.group(1)] + "(" + ps + ")"

    def sub(t, b):
        words = dict(VALW); words.update({s: alias[f"{s}@{b}"] for s in SUBJ})
        w_re = re.compile("|".join(sorted(map(re.escape, words), key=len, reverse=True)))
        t = FN_RE.sub(fn, t); t = KV_RE.sub(kv, t); t = CFG_RE.sub(cfg, t)
        t = DEP_RE.sub(lambda m: DEPS[m.group(1)], t); t = SEC_RE.sub(lambda m: SECS[m.group(1)], t)
        return w_re.sub(lambda m: words[m.group(0)], t)
    out = []
    for c in corpus():
        if c["doc"] in DEVDOCS:
            out.append(c); continue
        b = (c["seq"] - 1) // BLOCK
        out.append(dict(c, text=sub(c["text"], b), doc=sub(c["doc"], 0), cid=c["cid"]))
    mp = {"words": VALW, "alias": alias, "block": BLOCK, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 27000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h20base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap), "aliases", len(alias))


if __name__ == "__main__":
    build()
