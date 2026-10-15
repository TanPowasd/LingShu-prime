# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""UMB v0.1 冻结清单守卫（脚本式，不需要外部数据、零模型）。
用法：python -X utf8 test_umb.py            → 逐条守卫，全绿退出 0
      python -X utf8 test_umb.py --mutate   → 定点变异自证：每条变异必须恰好点红其目标守卫（且只点红它），报告 N/N
守卫：
  G1 manifest  顶层与每集字段完整、status=ok、组/集名一致、文件清单含必需文件、corpus.jsonl 不入库
  G2 sha       仓内冻结文件 sha256/字节数 == manifest，目录无多余/缺失
  G3 cap       每集题数 ≤500，且 == min(500, 候选题数)（manifest source_full 登记）
  G4 order     题序 == sha256("umb-v0.1|"+集名+"|"+qid) 升序（即「排序前 500」），无重复，题数 == manifest
  G5 split     dev/test 不相交、并集 = 全部题、逐题符合 sha256("umb-split|"+qid)[0] 偶→dev 奇→test、计数 == manifest
  G6 qrels     qrels 题集 == queries 题集（每题都在 queries 里且每题有金标），分数全为正
  G7 docids    检索集 doc_ids.txt 无重复、数目 == n_docs、金标文档在库（上游缺失登记除外）
  G8 memsrc    记忆集 source.json 题号 == queries 顺序；源路径全为 ${UMB_*} 形式；hive gold_quotes 与 qrels 一致
  G9 hygiene   入库文本无本机绝对路径、无邮箱；.py 文件头 SPDX LicenseRef-TanPowasd-Proprietary
"""
import copy, hashlib, json, pathlib, re, sys

UMB = pathlib.Path(__file__).resolve().parent
MAXQ = 500
SETS_REQ = {"group", "kind", "metric", "metric_def", "n_queries", "n_dev", "n_test", "n_docs", "n_chars",
            "source_full", "sources", "files", "status"}
TOP_REQ = {"name", "version", "rules", "groups", "sets", "path_vars"}
FULL_KEY = {"retrieval": "queries_with_pos_qrels", "lme": "queries_with_gold", "locomo": "queries_with_evidence", "hive": "cards_with_gold"}
ABS = re.compile(r"/(?:workspace|home|Users|tmp|root)/|\b[A-Za-z]:(?:\\\\|\\|/)Users\b")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]+")
SPDX = "# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary"


def qkey(name, qid):
    return hashlib.sha256(f"umb-v0.1|{name}|{qid}".encode("utf-8")).hexdigest()


def split_of(qid):
    return "dev" if hashlib.sha256(f"umb-split|{qid}".encode("utf-8")).digest()[0] % 2 == 0 else "test"


# ---------------------------------------------------------------- 读入（一次读盘，变异只改内存结构）
def load():
    man = json.loads((UMB / "manifest.json").read_text(encoding="utf-8"))
    st = {"man": man, "sets": {}, "texts": {}, "disk": {}}
    for p in sorted(UMB.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".md", ".json", ".jsonl", ".tsv", ".txt") \
                and not p.relative_to(UMB).parts[0] in ("data", "runs"):
            st["texts"][p.relative_to(UMB).as_posix()] = p.read_text(encoding="utf-8")
    for name in man["sets"]:
        d = UMB / name
        files = {p.name: p.read_bytes() for p in d.iterdir() if p.is_file()} if d.is_dir() else {}
        st["disk"][name] = {fn: (hashlib.sha256(b).hexdigest(), len(b)) for fn, b in files.items()}
        s = {"queries": [json.loads(l) for l in files["queries.jsonl"].decode("utf-8").splitlines()],
             "qrels": [l.split("\t") for l in files["qrels.tsv"].decode("utf-8").splitlines()],
             "split": json.loads(files["split.json"])}
        if "doc_ids.txt" in files:
            s["doc_ids"] = files["doc_ids.txt"].decode("utf-8").split("\n")[:-1]
        if "source.json" in files:
            s["source"] = json.loads(files["source.json"])
        if "gold_quotes.json" in files:
            s["gold_quotes"] = json.loads(files["gold_quotes.json"])
        st["sets"][name] = s
    return st


# ---------------------------------------------------------------- 守卫
def g_manifest(st):
    m, bad = st["man"], []
    bad += [f"顶层缺 {k}" for k in TOP_REQ - set(m)]
    if m.get("rules", {}).get("max_queries") != MAXQ:
        bad.append("rules.max_queries ≠ 500")
    grp = [x for v in m.get("groups", {}).values() for x in v]
    if sorted(grp) != sorted(m.get("sets", {})) or len(grp) != 12:
        bad.append("groups 与 sets 不一致或不是 12 集")
    for name, info in m.get("sets", {}).items():
        bad += [f"{name} 缺 {k}" for k in SETS_REQ - set(info)]
        if info.get("status") != "ok":
            bad.append(f"{name} status≠ok")
        need = {"queries.jsonl", "qrels.tsv", "split.json"} | ({"corpus.jsonl", "doc_ids.txt"} if info.get("kind") == "retrieval" else {"source.json"})
        if name == "hive":
            need.add("gold_quotes.json")
        bad += [f"{name} files 缺 {k}" for k in need - set(info.get("files", {}))]
        if "corpus.jsonl" in st["disk"].get(name, {}):
            bad.append(f"{name}: corpus.jsonl 不应入库")
    return bad


def g_sha(st):
    bad = []
    for name, info in st["man"]["sets"].items():
        want = {k: (v["sha256"], v["bytes"]) for k, v in info["files"].items() if k != "corpus.jsonl"}
        if want != st["disk"][name]:
            bad.append(f"{name}: 冻结文件与 manifest 不符 {sorted(set(want.items()) ^ set(st['disk'][name].items()))[:3]}")
    return bad


def g_cap(st):
    bad = []
    for name, info in st["man"]["sets"].items():
        n = len(st["sets"][name]["queries"])
        full = info["source_full"][FULL_KEY["retrieval" if info["kind"] == "retrieval" else name]]
        if n > MAXQ:
            bad.append(f"{name}: 题数 {n} > {MAXQ}")
        if n != min(MAXQ, full):
            bad.append(f"{name}: 题数 {n} ≠ min(500, 候选 {full})")
    return bad


def g_order(st):
    bad = []
    for name, info in st["man"]["sets"].items():
        q = [o["_id"] for o in st["sets"][name]["queries"]]
        if q != sorted(q, key=lambda x: qkey(name, x)):
            bad.append(f"{name}: 题序不是 sha256(umb-v0.1|集|qid) 升序")
        if len(q) != len(set(q)):
            bad.append(f"{name}: 题号重复")
        if len(q) != info["n_queries"]:
            bad.append(f"{name}: 题数 ≠ manifest n_queries")
    return bad


def g_split(st):
    bad = []
    for name, info in st["man"]["sets"].items():
        sp, q = st["sets"][name]["split"], {o["_id"] for o in st["sets"][name]["queries"]}
        dev, test = set(sp["dev"]), set(sp["test"])
        if dev & test:
            bad.append(f"{name}: dev/test 相交 {len(dev & test)}")
        if dev | test != q:
            bad.append(f"{name}: dev∪test ≠ 全部题")
        wrong = [x for x in dev if split_of(x) != "dev"] + [x for x in test if split_of(x) != "test"]
        if wrong:
            bad.append(f"{name}: {len(wrong)} 题不符 split 规则")
        if (len(sp["dev"]), len(sp["test"])) != (info["n_dev"], info["n_test"]):
            bad.append(f"{name}: dev/test 数 ≠ manifest")
    return bad


def g_qrels(st):
    bad = []
    for name in st["man"]["sets"]:
        q = {o["_id"] for o in st["sets"][name]["queries"]}
        rq = {r[0] for r in st["sets"][name]["qrels"]}
        if rq - q:
            bad.append(f"{name}: {len(rq - q)} 道 qrels 题不在 queries 里")
        if q - rq:
            bad.append(f"{name}: {len(q - rq)} 道题在 qrels 里没有金标")
        if any(len(r) != 3 or int(r[2]) <= 0 for r in st["sets"][name]["qrels"]):
            bad.append(f"{name}: qrels 行格式错或非正分")
    return bad


def g_docids(st):
    bad = []
    for name, info in st["man"]["sets"].items():
        if info["kind"] != "retrieval":
            continue
        ids = st["sets"][name]["doc_ids"]
        gold = {r[1] for r in st["sets"][name]["qrels"]}
        miss = gold - set(ids) - set(info.get("gold_missing_upstream", []))
        if len(ids) != len(set(ids)) or len(ids) != info["n_docs"]:
            bad.append(f"{name}: doc_ids 重复或数目 ≠ n_docs")
        if miss:
            bad.append(f"{name}: {len(miss)} 篇金标文档不在 doc_ids（且未登记为上游缺失）")
    return bad


def g_memsrc(st):
    bad = []
    for name, info in st["man"]["sets"].items():
        if info["kind"] != "memory":
            continue
        s = st["sets"][name]
        if s["source"]["qids"] != [o["_id"] for o in s["queries"]]:
            bad.append(f"{name}: source.json 题号 ≠ queries 顺序")
        paths = [p for p in list(s["source"]["files"]) + list(info["sources"]) if p != "commit"]
        if any(not p.startswith("${UMB_") for p in paths):
            bad.append(f"{name}: 源路径不是 ${{UMB_*}} 形式")
        if name == "hive":
            gq = s["gold_quotes"]
            rel = {}
            for r in s["qrels"]:
                rel.setdefault(r[0], set()).add(r[1])
            if set(gq) != set(rel) or any(set(gq[q]) != rel[q] for q in gq):
                bad.append("hive: gold_quotes 与 qrels 不一致")
            if any(k != f"ev:{hashlib.sha256(v.encode('utf-8')).hexdigest()[:16]}" for d in gq.values() for k, v in d.items()):
                bad.append("hive: gold_quotes 键 ≠ ev:sha256(句)[:16]")
    return bad


def g_hygiene(st):
    bad = []
    for rel, t in st["texts"].items():
        if ABS.search(t):
            bad.append(f"{rel}: 含本机绝对路径 {ABS.search(t).group(0)}")
        if EMAIL.search(t):
            bad.append(f"{rel}: 含邮箱")
        if rel.endswith(".py") and not t.startswith(SPDX):
            bad.append(f"{rel}: 缺 SPDX 头")
    return bad


GUARDS = {"G1 manifest": g_manifest, "G2 sha": g_sha, "G3 cap": g_cap, "G4 order": g_order, "G5 split": g_split,
          "G6 qrels": g_qrels, "G7 docids": g_docids, "G8 memsrc": g_memsrc, "G9 hygiene": g_hygiene}


def run(st):
    return {k: f(st) for k, f in GUARDS.items()}


# ---------------------------------------------------------------- 定点变异（只改内存）
def m_split_reversed(st):          # split 规则反转：偶→test 奇→dev（计数同步改，只该点红 split 规则）
    for name, s in st["sets"].items():
        s["split"]["dev"], s["split"]["test"] = s["split"]["test"], s["split"]["dev"]
        i = st["man"]["sets"][name]; i["n_dev"], i["n_test"] = i["n_test"], i["n_dev"]


def m_cap_501(st):                 # 题数上限放到 501：arguana（候选 1406）按哈希序多收第 501 题（金标、split、计数全同步）
    name, s = "arguana", st["sets"]["arguana"]
    q = "umb-mutant-501"
    s["queries"].append({"_id": q, "text": "mutant"}); s["queries"].sort(key=lambda o: qkey(name, o["_id"]))
    s["qrels"].append([q, s["doc_ids"][0], "1"])
    s["split"][split_of(q)].append(q); s["split"][split_of(q)].sort(key=lambda x: qkey(name, x))
    i = st["man"]["sets"][name]; i["n_queries"] += 1; i["n_" + split_of(q)] += 1


def m_qrels_drop(st):              # qrels 漏一题
    s = st["sets"]["scifact"]; q0 = s["qrels"][0][0]
    s["qrels"] = [r for r in s["qrels"] if r[0] != q0]


def m_qrels_extra(st):             # qrels 多出 queries 里没有的题
    st["sets"]["nfcorpus"]["qrels"].append(["umb-mutant-q", st["sets"]["nfcorpus"]["doc_ids"][0], "1"])


def m_order_swap(st):              # 选题排序被改（交换前两题；source.json 题号同步，模拟 build 一致地写错序）
    s = st["sets"]["locomo"]; q = s["queries"]; q[0], q[1] = q[1], q[0]
    s["source"]["qids"] = [o["_id"] for o in q]


def m_split_overlap(st):           # 一道 dev 题同时进 test（test 计数同步）
    for name, s in st["sets"].items():
        x = s["split"]["dev"][0]
        s["split"]["test"].append(x); st["man"]["sets"][name]["n_test"] += 1
        return


def m_manifest_field(st):          # manifest 丢字段
    del st["man"]["sets"]["hive"]["metric"]


def m_frozen_tamper(st):           # 冻结文件被改（指纹变化）
    st["disk"]["lme"]["qrels.tsv"] = ("0" * 64, st["disk"]["lme"]["qrels.tsv"][1])


def m_docids_drop_gold(st):        # doc_ids 丢一篇金标文档（n_docs 同步）
    s = st["sets"]["EcomRetrieval"]; g = s["qrels"][0][1]
    s["doc_ids"] = [d for d in s["doc_ids"] if d != g]; st["man"]["sets"]["EcomRetrieval"]["n_docs"] -= 1


def m_abs_path(st):                # 源路径泄回本机绝对路径
    st["texts"]["lme/source.json"] += "\n" + "/".join(["", "workspace", "x"])   # 拼接以免本文件自身命中


def m_mem_abs_src(st):             # source.json 源路径不再是 ${UMB_*}
    s = st["sets"]["locomo"]["source"]; k = next(iter(s["files"])); s["files"]["~/locomo10.json"] = s["files"].pop(k)


MUTANTS = [("split 规则反转", m_split_reversed, "G5 split"), ("题数上限放到 501", m_cap_501, "G3 cap"),
           ("qrels 漏一题", m_qrels_drop, "G6 qrels"), ("qrels 多一题", m_qrels_extra, "G6 qrels"),
           ("题序交换", m_order_swap, "G4 order"), ("dev/test 相交", m_split_overlap, "G5 split"),
           ("manifest 丢 metric", m_manifest_field, "G1 manifest"), ("冻结文件指纹篡改", m_frozen_tamper, "G2 sha"),
           ("doc_ids 丢金标", m_docids_drop_gold, "G7 docids"), ("绝对路径泄漏", m_abs_path, "G9 hygiene"),
           ("源路径非 ${UMB_*}", m_mem_abs_src, "G8 memsrc")]


def main():
    base = load()
    res = run(base)
    for k, v in res.items():
        print(("PASS " if not v else "FAIL ") + k + ("" if not v else "：" + "；".join(v[:5])))
    green = not any(res.values())
    print(f"守卫 {sum(not v for v in res.values())}/{len(res)} 绿")
    if "--mutate" not in sys.argv:
        sys.exit(0 if green else 1)
    if not green:
        print("基线未全绿，变异自证无意义"); sys.exit(1)
    ok = 0
    for label, fn, target in MUTANTS:
        st = copy.deepcopy(base); fn(st)
        red = [k for k, v in run(st).items() if v]
        hit = red == [target]
        ok += hit
        print(f"{'OK ' if hit else 'BAD'} 变异「{label}」→ 点红 {red}（目标 {target}）")
    print(f"mutate {ok}/{len(MUTANTS)}")
    sys.exit(0 if ok == len(MUTANTS) else 1)


if __name__ == "__main__":
    main()
