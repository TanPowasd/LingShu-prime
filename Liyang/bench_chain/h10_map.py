# -*- coding: utf-8 -*-
"""chain-r14 H10：换实体、换取值（PREREG_R14.md；与 H8、H9 映射都不同的新目标名/新取值，seed 14000）。对 HMB chain 语料的 test 文档（dev 文档 猎户项目/青石镇 不动）做固定映射的一致替换：
主体（项目名/人名/模块名）、取值与并存值（依赖名、秒数、键值对、函数签名、cfg_ 编号、情绪/位置/立场/信任对象词）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）；cfg_ 编号用固定种子 14000 的随机数。不调用被测代码。
  python h10_map.py   → out/heldout_h10/entity_value_map.json + corpus_h10base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h10")
DEVDOCS = {"猎户项目", "青石镇"}

WORDS = {
    # 主体
    "流明": "云笈", "织女": "鸿雁", "缓存模块": "网关模块",
    "杜衡": "蒋岚", "林昭": "方黎", "沈砚": "霍铮", "阿桑": "阿蕙", "白芨": "芮棠", "雪姑": "桂嫂",
    "陆平": "卢坚", "程雪": "傅瑶", "九爷": "五叔", "顾九": "邵五",
    # 情绪 / 位置 / 立场 / 信任对象
    "低落": "颓丧", "犹豫": "彷徨", "戒备": "防范", "欣慰": "畅快", "释然": "轻松", "平静": "泰然", "愤怒": "恼怒", "焦虑": "烦躁",
    "祠堂": "牌坊", "渡口": "凉亭", "驿站": "当铺", "粮仓": "书院", "集市": "墟场", "磨坊": "窑厂", "后山": "溪畔", "码头": "碉楼",
    "暧昧": "游移", "沉默": "不语", "反对": "排斥", "支持": "附和", "中立": "超然", "观望": "等候",
    "外人": "路人",
}
DEPS = {"bbolt": "kvrocks", "rocksdb": "foundationdb", "badger": "immudb", "sled": "fjall", "sqlite": "firebird", "lmdb": "mongodb", "redis": "dragonfly"}
SECS = {"21600": "25200", "300": "360", "1800": "2400", "3600": "6000", "900": "1080", "7200": "8400", "10800": "19800", "600": "540"}
KEYS = {"batch_size": "bulk_size", "retry": "retries", "max_conn": "conn_limit", "timeout_ms": "expire_ms"}
KNUM = {"16": "12", "32": "36", "64": "72", "128": "144", "256": "288"}
FUNCS = {"load": "ingest", "get": "peek", "fetch": "pick", "resolve": "bind", "sync": "persist"}
PARAMS = {"key": "field", "ttl": "maxage", "tag": "badge", "refresh": "rescan", "force": "must", "id": "pk"}

W_RE = re.compile("|".join(sorted(map(re.escape, WORDS), key=len, reverse=True)))
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")


def build():
    rng = random.Random(14000); cfgmap = {}
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
    out = []
    for c in corpus():
        if c["doc"] in DEVDOCS:
            out.append(c); continue
        out.append(dict(c, text=sub(c["text"]), doc=sub(c["doc"]), cid=c["cid"]))
    mp = {"words": WORDS, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 14000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h10base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap))


if __name__ == "__main__":
    build()
