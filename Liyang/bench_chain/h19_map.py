# -*- coding: utf-8 -*-
"""chain-r23 H19：换实体、换取值 + 分块换名（PREREG_R23.md；seed 26000）。对 HMB chain 语料 test 文档（dev 文档 猎户项目/青石镇 不动）：
取值与并存值做固定映射（与 H8–H18 目标值都不同）；主体（项目名/人名/模块名）按「段号块」换名：同一文档每 BLOCK=3 段一个块，
块内一致、块间不同（模拟真实记忆流里主体不断换新：冷启动主体占事件句约 1/3，H8–H18 只有约 4%）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）。不调用被测代码。
  python h19_map.py   → out/heldout_h19/entity_value_map.json + corpus_h19base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h19"); os.makedirs(D, exist_ok=True)
DEVDOCS = {"猎户项目", "青石镇"}
BLOCK = 3
SUBJ = ["流明", "织女", "缓存模块", "杜衡", "林昭", "沈砚", "阿桑", "白芨", "雪姑", "陆平", "程雪", "九爷", "顾九"]
VALW = {
    "低落": "郁郁寡欢", "犹豫": "举棋不定", "戒备": "草木皆兵", "欣慰": "怡然", "释然": "如释重负", "平静": "波澜不惊", "愤怒": "怒不可遏", "焦虑": "坐立不安",
    "祠堂": "社庙", "渡口": "过河滩", "驿站": "递铺", "粮仓": "常平仓", "集市": "草墟", "磨坊": "石磨棚", "后山": "北岭坡", "码头": "泊船湾",
    "暧昧": "语焉不详", "沉默": "三缄其口", "反对": "断然拒绝", "支持": "竭力拥护", "中立": "隔岸观火", "观望": "按兵不动",
    "外人": "异乡客",
}
DEPS = {"bbolt": "wrenvault", "rocksdb": "egretstore", "badger": "stoatlog", "sled": "finchtable", "sqlite": "ternbase", "lmdb": "cranevault", "redis": "puffincache"}
SECS = {"21600": "23940", "300": "2370", "1800": "4410", "3600": "6630", "900": "3270", "7200": "15960", "10800": "52380", "600": "1770"}
KEYS = {"batch_size": "crate_size", "retry": "retry_allowance", "max_conn": "conn_allotment", "timeout_ms": "patience_ms"}
KNUM = {"16": "79", "32": "97", "64": "179", "128": "353", "256": "613"}
FUNCS = {"load": "lug", "get": "winnow", "fetch": "ferry", "resolve": "referee", "sync": "braid"}
PARAMS = {"key": "kpin", "ttl": "shelflife", "tag": "insignia", "refresh": "rekindle", "force": "impel", "id": "tagno"}

SURN = list("祁鞠雍逯荆蔺缪芮郦栾甘骆萧廉阚柏樊邵戚冉")
GIV = list("砺珩翊琰骁湛萦黛蘅棠瑗珂岫澈翎璟琮蔚")
PROJ = list("岚汐枫霁晗澜屿曜璞澄霆筠苒珀岱汀沅峤朔琼")
MOD = ["滤网", "游标", "信标", "码盘", "闸门", "簧片", "齿轮", "罗盘", "漏斗", "锚链", "穹顶", "水准", "杠杆", "滑轨", "绞盘", "风箱", "铆钉", "棱镜", "砝码", "弦轴", "箍环", "楔块"]
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")


def build():
    rng = random.Random(26000)
    _all = "".join(c["text"] + c["doc"] for c in corpus())
    nblk = max(c["seq"] for c in corpus()) // BLOCK + 1
    prev = set()
    for v in range(8, 19):
        m = json.load(open(os.path.join(OUT, f"heldout_h{v}", "entity_value_map.json"), encoding="utf-8"))
        for k in ("words", "deps", "secs", "keys", "knum", "funcs", "params"):
            prev |= set(m[k].values())
    used = set(); alias = {}

    def fresh(kind):
        for _ in range(10000):
            if kind == "proj":
                t = rng.choice(PROJ) + rng.choice(PROJ)
            elif kind == "mod":
                t = rng.choice(MOD) + "模块"
            else:
                t = rng.choice(SURN) + rng.choice(GIV) + (rng.choice(GIV) if rng.random() < .3 else "")
            if t in used or t in _all or t in prev or len(set(t)) < len(t):
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
    rngc = random.Random(26001); cfgmap = {}; cused = set()

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
    mp = {"words": VALW, "alias": alias, "block": BLOCK, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 26000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h19base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap), "aliases", len(alias))


if __name__ == "__main__":
    build()
