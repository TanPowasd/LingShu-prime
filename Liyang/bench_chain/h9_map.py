# -*- coding: utf-8 -*-
"""chain-r13 H9：换实体、换取值（PREREG_R13.md；与 H8 映射不同的新目标名/新取值，seed 13000）。对 HMB chain 语料的 test 文档（dev 文档 猎户项目/青石镇 不动）做固定映射的一致替换：
主体（项目名/人名/模块名）、取值与并存值（依赖名、秒数、键值对、函数签名、cfg_ 编号、情绪/位置/立场/信任对象词）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）；cfg_ 编号用固定种子 13000 的随机数。不调用被测代码。
  python h9_map.py   → out/heldout_h9/entity_value_map.json + corpus_h9base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h9")
DEVDOCS = {"猎户项目", "青石镇"}

WORDS = {
    # 主体
    "流明": "玄圃", "织女": "鹊桥", "缓存模块": "调度模块",
    "杜衡": "魏澜", "林昭": "钱溪", "沈砚": "周屿", "阿桑": "阿芷", "白芨": "柏蓉", "雪姑": "柳娘",
    "陆平": "严朗", "程雪": "罗依", "九爷": "三伯", "顾九": "贺三",
    # 情绪 / 位置 / 立场 / 信任对象
    "低落": "消沉", "犹豫": "踌躇", "戒备": "提防", "欣慰": "满足", "释然": "舒坦", "平静": "安然", "愤怒": "气愤", "焦虑": "不安",
    "祠堂": "城隍庙", "渡口": "河埠", "驿站": "客栈", "粮仓": "酒坊", "集市": "庙会", "磨坊": "染坊", "后山": "山坳", "码头": "船坞",
    "暧昧": "摇摆", "沉默": "缄默", "反对": "抗拒", "支持": "赞成", "中立": "骑墙", "观望": "旁观",
    "外人": "生人",
}
DEPS = {"bbolt": "nutsdb", "rocksdb": "wiredtiger", "badger": "bitcask", "sled": "mdbx", "sqlite": "h2db", "lmdb": "couchdb", "redis": "valkey"}
SECS = {"21600": "28800", "300": "420", "1800": "3000", "3600": "18000", "900": "1500", "7200": "4800", "10800": "16200", "600": "720"}
KEYS = {"batch_size": "page_size", "retry": "retry_limit", "max_conn": "conn_cap", "timeout_ms": "wait_ms"}
KNUM = {"16": "20", "32": "40", "64": "80", "128": "160", "256": "320"}
FUNCS = {"load": "open", "get": "find", "fetch": "grab", "resolve": "match", "sync": "commit"}
PARAMS = {"key": "slot", "ttl": "lifetime", "tag": "marker", "refresh": "renew", "force": "hard", "id": "ref"}

W_RE = re.compile("|".join(sorted(map(re.escape, WORDS), key=len, reverse=True)))
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")


def build():
    rng = random.Random(13000); cfgmap = {}
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
    mp = {"words": WORDS, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 13000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h9base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap))


if __name__ == "__main__":
    build()
