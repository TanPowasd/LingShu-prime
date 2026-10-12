# -*- coding: utf-8 -*-
"""chain-r15 H11：换实体、换取值（PREREG_R15.md；与 H8、H9、H10 映射都不同的新目标名/新取值，seed 15000）。对 HMB chain 语料的 test 文档（dev 文档 猎户项目/青石镇 不动）做固定映射的一致替换：
主体（项目名/人名/模块名）、取值与并存值（依赖名、秒数、键值对、函数签名、cfg_ 编号、情绪/位置/立场/信任对象词）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）；cfg_ 编号用固定种子 15000 的随机数。不调用被测代码。
  python h11_map.py   → out/heldout_h11/entity_value_map.json + corpus_h11base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h11")
DEVDOCS = {"猎户项目", "青石镇"}

WORDS = {
    # 主体
    "流明": "琅嬛", "织女": "朱雀", "缓存模块": "队列模块",
    "杜衡": "孟川", "林昭": "谢棠", "沈砚": "陶勉", "阿桑": "阿蘅", "白芨": "郁菁", "雪姑": "莲婆",
    "陆平": "庞朔", "程雪": "裴绮", "九爷": "六婶", "顾九": "莫十",
    # 情绪 / 位置 / 立场 / 信任对象
    "低落": "黯然", "犹豫": "迟徊", "戒备": "设防", "欣慰": "快慰", "释然": "舒心", "平静": "恬淡", "愤怒": "愠怒", "焦虑": "焦灼",
    "祠堂": "鼓楼", "渡口": "水榭", "驿站": "盐仓", "粮仓": "义庄", "集市": "草市", "磨坊": "油坊", "后山": "松岗", "码头": "栈桥",
    "暧昧": "含混", "沉默": "噤声", "反对": "拒斥", "支持": "力挺", "中立": "居间", "观望": "守望",
    "外人": "过客",
}
DEPS = {"bbolt": "lsmdb", "rocksdb": "speedb", "badger": "pogreb", "sled": "redb", "sqlite": "libsql", "lmdb": "cassandra", "redis": "keydb"}
SECS = {"21600": "32400", "300": "660", "1800": "3300", "3600": "4200", "900": "1140", "7200": "9600", "10800": "23400", "600": "780"}
KEYS = {"batch_size": "flush_size", "retry": "retry_cap", "max_conn": "conn_max", "timeout_ms": "idle_ms"}
KNUM = {"16": "28", "32": "44", "64": "88", "128": "176", "256": "352"}
FUNCS = {"load": "absorb", "get": "probe", "fetch": "gather", "resolve": "settle", "sync": "mirror"}
PARAMS = {"key": "entry", "ttl": "span", "tag": "token", "refresh": "revive", "force": "strict_on", "id": "oid"}

W_RE = re.compile("|".join(sorted(map(re.escape, WORDS), key=len, reverse=True)))
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")


def build():
    rng = random.Random(15000); cfgmap = {}
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
    prev = set()
    for v in ("h8", "h9", "h10"):
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
    mp = {"words": WORDS, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 15000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h11base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap))


if __name__ == "__main__":
    build()
