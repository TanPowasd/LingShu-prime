# -*- coding: utf-8 -*-
"""chain-r25 H21：换实体、换取值 + 分块换名（PREREG_R25.md；seed 28000；由 h20_map.py 改值表/名库/种子，口径同 H19/H20）。对 HMB chain 语料 test 文档（dev 文档 猎户项目/青石镇 不动）：
取值与并存值做固定映射（与 H8–H20 目标值、H19/H20 别名都不同）；主体（项目名/人名/模块名）按「段号块」换名：同一文档每 BLOCK=3 段一个块，
块内一致、块间不同（模拟真实记忆流里主体不断换新：冷启动主体占事件句约 1/3，H8–H18 只有约 4%）。属性名与起因原样保留。
单次正则交替替换（最长优先，不链式替换）。不调用被测代码。
  python h21_map.py   → out/heldout_h21/entity_value_map.json + corpus_h21base.json"""
import hashlib, json, os, random, re
from cb_common import OUT, corpus, dump

D = os.path.join(OUT, "heldout_h21"); os.makedirs(D, exist_ok=True)
DEVDOCS = {"猎户项目", "青石镇"}
BLOCK = 3
SUBJ = ["流明", "织女", "缓存模块", "杜衡", "林昭", "沈砚", "阿桑", "白芨", "雪姑", "陆平", "程雪", "九爷", "顾九"]
VALW = {
    "低落": "垂头丧气", "犹豫": "迟疑不决", "戒备": "提心吊胆", "欣慰": "眉开眼笑", "释然": "云开雾散", "平静": "泰然自若", "愤怒": "暴跳如雷", "焦虑": "寝食难安",
    "祠堂": "宗庙堂", "渡口": "柳荫津", "驿站": "马递铺", "粮仓": "谷廪", "集市": "墟市街", "磨坊": "碾米寮", "后山": "西岭坳", "码头": "系缆埠",
    "暧昧": "吞吞吐吐", "沉默": "闭口不谈", "反对": "坚决抵制", "支持": "倾力声援", "中立": "冷眼旁观", "观望": "袖手旁观",
    "外人": "局外客",
}
DEPS = {"bbolt": "plovervault", "rocksdb": "grebedb", "badger": "shrewledger", "sled": "linnetstore", "sqlite": "kittiwakebase", "lmdb": "stiltkv", "redis": "whimbrelcache"}
SECS = {"21600": "27180", "300": "2970", "1800": "5490", "3600": "8370", "900": "3690", "7200": "17460", "10800": "44730", "600": "1890"}
KEYS = {"batch_size": "skein_size", "retry": "retry_quantum", "max_conn": "conn_ration", "timeout_ms": "linger_ms"}
KNUM = {"16": "69", "32": "113", "64": "211", "128": "409", "256": "691"}
FUNCS = {"load": "tote", "get": "skim", "fetch": "fetchback", "resolve": "mend", "sync": "lace"}
PARAMS = {"key": "kcell", "ttl": "durance", "tag": "badgemark", "refresh": "refurb", "force": "enforce", "id": "rowmark"}

SURN = list("禹聂隋巫鄢邬娄宦楚阎翟訾龚寇糜鄂敖郗沃谯")
GIV = list("骞衎旻炅暄昀炜焜熠烨铮锷钧镛珅瑱琇璇")
PROJ = list("岑峪崂嶂巍嵩崴峦嵯岢嵛岈峄崃峤嶙崟嵬嶷巘")
MOD = ["卡榫", "绳轮", "泵体", "钟摆", "旋钮", "插销", "簧圈", "衬套", "转轴", "法兰", "拨叉", "顶针", "压板", "销钉", "导杆", "夹钳", "挡圈", "曲柄", "蜗杆", "滚珠", "链轮", "撞针"]
CFG_RE = re.compile(r"cfg_(\d{4,7})(?!\d)")
DEP_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(DEPS) + r")(?![A-Za-z_])")
SEC_RE = re.compile(r"(?<![\d,.])(" + "|".join(sorted(SECS, key=len, reverse=True)) + r")(?![\d,])")
KV_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(KEYS) + r")=(\d+)(?!\d)")
FN_RE = re.compile(r"(?<![A-Za-z_])(" + "|".join(FUNCS) + r")\(([a-z, ]*)\)")


def build():
    rng = random.Random(28000)
    _all = "".join(c["text"] + c["doc"] for c in corpus())
    nblk = max(c["seq"] for c in corpus()) // BLOCK + 1
    prev = set()
    for v in range(8, 21):
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
    rngc = random.Random(28001); cfgmap = {}; cused = set()

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
    mp = {"words": VALW, "alias": alias, "block": BLOCK, "deps": DEPS, "secs": SECS, "keys": KEYS, "knum": KNUM, "funcs": FUNCS, "params": PARAMS, "cfg": cfgmap, "seed": 28000}
    dump(os.path.join(D, "entity_value_map.json"), mp, indent=1)
    dump(os.path.join(D, "corpus_h21base.json"), out)
    h = hashlib.sha256(json.dumps(out, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    print("base_sha", h, "cfg", len(cfgmap), "aliases", len(alias))


if __name__ == "__main__":
    build()
