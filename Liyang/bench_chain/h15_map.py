# -*- coding: utf-8 -*-
"""chain-r19 H15：换实体、换取值（PREREG_R19.md；与 H8–H14 映射都不同的新目标名/新取值，seed 19000）。对 HMB chain 语料的 test 文档（dev 文档 猎户项目/青石镇 不动）做固定映射的一致替换：
主体（项目名/人名/模块名）、取值与并存值（依赖名、秒数、键值对、函数签名、cfg_ 编号、情绪/位置/立场/信任对象词）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）；cfg_ 编号用固定种子 19000 的随机数。不调用被测代码。
  python h15_map.py   → out/heldout_h15/entity_value_map.json + corpus_h15base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h15")
DEVDOCS = {"猎户项目", "青石镇"}

WORDS = {
    # 主体
    "流明": "方壶", "织女": "蓬丘", "缓存模块": "分发模块",
    "杜衡": "甘棠", "林昭": "邵弦", "沈砚": "裴迁", "阿桑": "阿蓁", "白芨": "苏枋", "雪姑": "榴姨",
    "陆平": "祁望", "程雪": "葛蔚", "九爷": "七叔公", "顾九": "韦三",
    # 情绪 / 位置 / 立场 / 信任对象
    "低落": "寥落", "犹豫": "畏缩", "戒备": "警醒", "欣慰": "慰藉", "释然": "旷达", "平静": "澹然", "愤怒": "激愤", "焦虑": "郁悒",
    "祠堂": "祖祠", "渡口": "渡头", "驿站": "茶亭", "粮仓": "仓廒", "集市": "墟市", "磨坊": "碓房", "后山": "松坡", "码头": "舟埠",
    "暧昧": "不置可否", "沉默": "无言", "反对": "驳斥", "支持": "赞同", "中立": "守中", "观望": "静待",
    "外人": "外客",
}
DEPS = {"bbolt": "cabinetdb", "rocksdb": "hamsterdb", "badger": "unqlite", "sled": "lightkv", "sqlite": "wisckey", "lmdb": "ardb", "redis": "leveldbx"}
SECS = {"21600": "34200", "300": "1440", "1800": "2460", "3600": "2640", "900": "1680", "7200": "13800", "10800": "36000", "600": "1620"}
KEYS = {"batch_size": "chunk_len", "retry": "retry_quota", "max_conn": "conn_ceiling", "timeout_ms": "deadline_cap"}
KNUM = {"16": "63", "32": "77", "64": "136", "128": "264", "256": "424"}
FUNCS = {"load": "gulp", "get": "glimpse", "fetch": "haul", "resolve": "decide", "sync": "align"}
PARAMS = {"key": "pkey", "ttl": "expiry", "tag": "stamp", "refresh": "redo", "force": "forceful", "id": "ident"}

W_RE = re.compile("|".join(sorted(map(re.escape, WORDS), key=len, reverse=True)))
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")


def build():
    rng = random.Random(19000); cfgmap = {}
    used = set()

    def cfg(m):
        k = m.group(1)
        if k not in cfgmap:
            while True:
                v = str(rng.randrange(100000, 1000000))
                if v not in used:
                    used.add(v); break
            cfgmap[k] = v
        return "cfg_" + cfgmap[k]

    def kv(m):
        return KEYS[m.group(1)] + "=" + KNUM.get(m.group(2), m.group(2))

    def fn(m):
        ps = ", ".join(PARAMS.get(p.strip(), p.strip()) for p in m.group(2).split(",") if p.strip())
        return FUNCS[m.group(1)] + "(" + ps + ")"

    def sub(t):
        t = FN_RE.sub(fn, t)
        t = KV_RE.sub(kv, t)
        t = CFG_RE.sub(cfg, t)
        t = DEP_RE.sub(lambda m: DEPS[m.group(1)], t)
        t = SEC_RE.sub(lambda m: SECS[m.group(1)], t)
        return W_RE.sub(lambda m: WORDS[m.group(0)], t)

    _all = "".join(c["text"] for c in corpus())
    for t in list(WORDS.values()) + list(DEPS.values()):
        assert t not in _all, t
    for t in list(SECS.values()) + list(KNUM.values()):          # 数值目标不在原语料出现
        assert not re.search(r"(?<!\d)" + t + r"(?!\d)", _all), ("num in corpus", t)
    prev = set()
    for v in ("h8", "h9", "h10", "h11", "h12", "h13", "h14"):
        m = json.load(open(os.path.join(OUT, f"heldout_{v}", "entity_value_map.json"), encoding="utf-8"))
        for k in ("words", "deps", "secs", "keys", "knum", "funcs", "params"):
            prev |= set(m[k].values())
    for d_ in (WORDS, DEPS, SECS, KEYS, KNUM, FUNCS, PARAMS):
        for t in d_.values():
            assert t not in prev, ("reused", t)
    out = []
    for c in corpus():
        if c["doc"] in DEVDOCS:
            out.append(c); continue
        out.append(dict(c, text=sub(c["text"]), doc=sub(c["doc"]), cid=c["cid"]))
    mp = {"words": WORDS, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 19000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h15base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap))


if __name__ == "__main__":
    build()
