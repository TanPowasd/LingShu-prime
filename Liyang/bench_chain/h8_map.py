# -*- coding: utf-8 -*-
"""chain-r12 H8：换实体、换取值（PREREG_R12.md）。对 HMB chain 语料的 test 文档（dev 文档 猎户项目/青石镇 不动）做固定映射的一致替换：
主体（项目名/人名/模块名）、取值与并存值（依赖名、秒数、键值对、函数签名、cfg_ 编号、情绪/位置/立场/信任对象词）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）；cfg_ 编号用固定种子 12000 的随机数。不调用被测代码。
  python h8_map.py   → out/heldout_h8/entity_value_map.json + corpus_h8base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h8")
DEVDOCS = {"猎户项目", "青石镇"}

WORDS = {
    # 主体
    "流明": "星槎", "织女": "青鸾", "缓存模块": "索引模块",
    "杜衡": "秦峥", "林昭": "苏晚", "沈砚": "韩霁", "阿桑": "阿蛮", "白芨": "葛蘅", "雪姑": "梅婶",
    "陆平": "许岩", "程雪": "温宁", "九爷": "七叔", "顾九": "骆七",
    # 情绪 / 位置 / 立场 / 信任对象
    "低落": "沮丧", "犹豫": "迟疑", "戒备": "警惕", "欣慰": "宽慰", "释然": "坦然", "平静": "淡定", "愤怒": "恼火", "焦虑": "忐忑",
    "祠堂": "钟楼", "渡口": "石桥", "驿站": "茶棚", "粮仓": "药铺", "集市": "戏台", "磨坊": "铁匠铺", "后山": "竹林", "码头": "灯塔",
    "暧昧": "含糊", "沉默": "缄口", "反对": "抵制", "支持": "拥护", "中立": "两可", "观望": "静观",
    "外人": "旁人",
}
DEPS = {"bbolt": "pebble", "rocksdb": "leveldb", "badger": "boltdb", "sled": "tikv", "sqlite": "duckdb", "lmdb": "etcd", "redis": "memcached"}
SECS = {"21600": "14400", "300": "240", "1800": "2700", "3600": "5400", "900": "1200", "7200": "9000", "10800": "12600", "600": "480"}
KEYS = {"batch_size": "chunk_size", "retry": "max_retry", "max_conn": "pool_size", "timeout_ms": "deadline_ms"}
KNUM = {"16": "24", "32": "48", "64": "96", "128": "192", "256": "384"}
FUNCS = {"load": "read", "get": "lookup", "fetch": "pull", "resolve": "query", "sync": "flush"}
PARAMS = {"key": "name", "ttl": "expire", "tag": "label", "refresh": "reload", "force": "strict", "id": "uid"}

W_RE = re.compile("|".join(sorted(map(re.escape, WORDS), key=len, reverse=True)))
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")


def build():
    rng = random.Random(12000); cfgmap = {}
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

    out = []
    for c in corpus():
        if c["doc"] in DEVDOCS:
            out.append(c); continue
        out.append(dict(c, text=sub(c["text"]), doc=sub(c["doc"]), cid=c["cid"]))
    mp = {"words": WORDS, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 12000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h8base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap))


if __name__ == "__main__":
    build()
