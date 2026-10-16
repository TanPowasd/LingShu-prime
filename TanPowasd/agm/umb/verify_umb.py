# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""UMB v0.1 校验。全部通过退出码 0，否则打印 FAIL 清单退出 1。
用法：python -X utf8 verify_umb.py [--sets a,b] [--frozen-only]
  默认（全量）：
    1. 仓内冻结文件（queries/qrels/split/source/gold_quotes/doc_ids）与 manifest.json 的 sha256 逐个一致，目录无多余/缺失文件；
    2. 每集题数 ≤500、题序为哈希序、qrels 题集 = queries、dev/test 不相交且按 sha256("umb-split|"+qid) 规则划分；
    3. 选题复算：从公开源重算「有正金标的候选题」，按 sha256("umb-v0.1|"+集名+"|"+qid) 升序取前 500 == 冻结题表；
    4. 公开源文件 sha256 == manifest 登记（${UMB_BEIR} 等环境变量解析）；
    5. 检索集：$UMB_OUT/<集>/corpus.jsonl（build 重建产物）sha256 == manifest，文档号顺序 == doc_ids.txt，金标在库；
    6. 记忆集：逐题核对源题面与金标轮（lme/locomo），hive 金标句与 qrels 一致、块数一致。
  --frozen-only：只做 1、2（不需要外部数据），并明示未校验语料/源。
单进程；LME 源文件逐个加载。"""
import argparse, json, pathlib, sys

UMB = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(UMB))
import build_umb as B  # noqa: E402
from build_umb import sha_file, split_of, qkey, MAXQ, MAXCH, REPO_EXCLUDES  # noqa: E402

fails, notes = [], []


def check(cond, msg):
    if not cond:
        fails.append(msg)
    return cond


def verify_set(name, info, frozen_only):
    d = UMB / name
    want = {fn for fn in info["files"] if fn not in REPO_EXCLUDES}
    on_disk = {p.name for p in d.iterdir() if p.is_file()} if d.is_dir() else set()
    check(on_disk == want, f"{name}: 仓内文件与 manifest 不符 {sorted(on_disk ^ want)}")
    for fn in sorted(want & on_disk):
        check(sha_file(d / fn) == info["files"][fn]["sha256"], f"{name}/{fn}: sha256 不符"
              + ("（文件含 CRLF：疑似 Windows git core.autocrlf 检出改写，见 umb/.gitattributes）"
                 if (d / fn).exists() and b"\r\n" in (d / fn).read_bytes() else ""))
    qs = [json.loads(l) for l in open(d / "queries.jsonl", encoding="utf-8")]
    qids = [q["_id"] for q in qs]
    check(len(qids) == len(set(qids)), f"{name}: 题号重复")
    check(len(qids) <= MAXQ, f"{name}: 题数 {len(qids)} > {MAXQ}")
    check(len(qids) == info["n_queries"], f"{name}: 题数与 manifest 不符")
    check(qids == sorted(qids, key=lambda q: qkey(name, q)), f"{name}: 题序不是哈希序")
    qrels = {}
    for line in open(d / "qrels.tsv", encoding="utf-8"):
        q, doc, s = line.rstrip("\n").split("\t")
        check(int(s) > 0, f"{name}: 非正 qrel {q} {doc}")
        qrels.setdefault(q, set()).add(doc)
    check(set(qrels) == set(qids), f"{name}: qrels 题集与 queries 不一致")
    sp = json.loads((d / "split.json").read_text(encoding="utf-8"))
    dev, test = set(sp["dev"]), set(sp["test"])
    check(not dev & test, f"{name}: dev/test 相交 {len(dev & test)}")
    check(dev | test == set(qids), f"{name}: dev∪test ≠ 全部题")
    check(all(split_of(q) == "dev" for q in dev) and all(split_of(q) == "test" for q in test), f"{name}: split 不符规则")
    check(len(dev) == info["n_dev"] and len(test) == info["n_test"], f"{name}: dev/test 数与 manifest 不符")
    gold = {x for v in qrels.values() for x in v}
    up = set(info.get("gold_missing_upstream", []))
    if info["kind"] == "retrieval":
        doc_ids = (d / "doc_ids.txt").read_text(encoding="utf-8").split("\n")[:-1]
        check(len(doc_ids) == len(set(doc_ids)) == info["n_docs"], f"{name}: doc_ids.txt 重复或数目与 manifest 不符")
        check(gold - set(doc_ids) <= up, f"{name}: {len(gold - set(doc_ids) - up)} 篇金标文档不在 doc_ids.txt")
    if frozen_only:
        notes.append(f"{name}: {len(qids)} 题（dev {len(dev)} / test {len(test)}），仅冻结文件已校验（未校验语料/源）")
        return
    # ---- 源文件指纹 ----
    lme_raw = False
    for p, s in info["sources"].items():
        if p == "commit":
            continue
        rp = B.resolve(p)
        if name == "lme" and not rp.exists():
            lme_raw = True
            continue
        check(rp.exists() and sha_file(rp) == s, f"{name}: 源文件 sha256 不符 {p}")
    if lme_raw:
        notes.append("lme: 存疑——UMB_LME 下无 part 文件，读官方原始文件按 n%3 拆；字节指纹不可比，以下逐题内容核对代替")
    # ---- 选题复算 + 语料 ----
    if info["kind"] == "retrieval":
        qtext, _ = B.retr_candidates(name)
        check(B.pick(name, list(qtext)) == qids, f"{name}: 选题复算与冻结题表不符")
        check(len(qtext) == info["source_full"]["queries_with_pos_qrels"], f"{name}: 候选题数与 manifest 不符")
        cp = B.OUT / name / "corpus.jsonl"
        if not check(cp.exists(), f"{name}: 缺 {cp.name}（先跑 build_umb.py 重建到 $UMB_OUT）"):
            return
        check(sha_file(cp) == info["files"]["corpus.jsonl"]["sha256"], f"{name}: 重建 corpus.jsonl sha256 与 manifest 不符")
        ids, chars = [], 0
        for line in open(cp, encoding="utf-8"):
            o = json.loads(line); ids.append(o["_id"]); chars += len(o["title"]) + len(o["text"])
        check(ids == doc_ids, f"{name}: corpus.jsonl 文档号顺序 ≠ doc_ids.txt")
        idset = set(ids)
        check(len(ids) == len(idset), f"{name}: 文档号重复")
        miss = gold - idset
        check(miss <= up, f"{name}: {len(miss - up)} 篇金标文档不在语料里")
        if miss:
            notes.append(f"{name}: 存疑——{len(miss)} 篇金标文档原语料就缺（上游缺陷，manifest 已登记）：{sorted(miss)}")
        check(len(ids) == info["n_docs"] and chars == info["n_chars"], f"{name}: 文档数/字数与 manifest 不符")
        check(chars <= MAXCH or len(ids) == len(gold), f"{name}: 字数 {chars} 超过上限")
        notes.append(f"{name}: {len(qids)} 题 {len(ids)} 文档 {chars} 字 金标 {len(gold)} 篇（{len(gold) - len(miss)} 在库），语料重建指纹一致")
        return
    src = json.loads((d / "source.json").read_text(encoding="utf-8"))
    check(src["qids"] == qids, f"{name}: source.json 题号列表与 queries 不符")
    if name == "lme":
        byf, cand = {}, []
        for q in qs:
            byf.setdefault(q["src"], []).append(q)
        for k in range(3):
            data = B.lme_part(k)
            cand += [it["question_id"] for it in data
                     if any(t.get("has_answer") for s in it["haystack_sessions"] for t in s)]
            for q in byf.get(f"part{k}.json", []):
                it = data[q["idx"]]
                check(it["question_id"] == q["_id"] and it["question"] == q["text"], f"lme: {q['_id']} 源题不符")
                turns = [t for s in it["haystack_sessions"] for t in s]
                g = {str(i) for i, t in enumerate(turns) if t.get("has_answer")}
                check(g == qrels[q["_id"]], f"lme: {q['_id']} 金标轮不在/不符源 haystack")
            del data
        B._lme_raw[0] = None
        check(B.pick("lme", cand) == qids, "lme: 选题复算与冻结题表不符")
    elif name == "locomo":
        items = B.locomo_conv_items()
        cand = [f"{it['sid']}_{qi}" for it in items for qi, qa in enumerate(it["qa"]) if B.locomo_gold(it, qa)]
        check(B.pick("locomo", cand) == qids, "locomo: 选题复算与冻结题表不符")
        items = {it["sid"]: it for it in items}
        for q in qs:
            it = items[q["sid"]]; qa = it["qa"][q["qi"]]
            check(qa["question"] == q["text"], f"locomo: {q['_id']} 题面不符")
            check(B.locomo_gold(it, qa) == qrels[q["_id"]] and qrels[q["_id"]] <= set(it["ids"]), f"locomo: {q['_id']} 金标轮不在会话里")
    elif name == "hive":
        HR = B.hive_mod()
        _, qtext, qrels_src, gq_src, _ = B.hive_candidates()
        check(B.pick("hive", list(qtext)) == qids, "hive: 选题复算与冻结题表不符")
        chunks = HR.load_chunks(B.resolve(src["repo"]))
        full = "".join(c["n"] for c in chunks)
        gq = json.loads((d / "gold_quotes.json").read_text(encoding="utf-8"))
        check(set(gq) == set(qids), "hive: gold_quotes 题集不符")
        for q in qids:
            check(set(gq[q]) == qrels[q], f"hive: {q} gold_quotes 与 qrels 不符")
            check(gq[q] == gq_src.get(q), f"hive: {q} gold_quotes 与源卡片重算不符")
        check(len(chunks) == info["n_docs"], "hive: 块数与 manifest 不符")
        inside = sum(p in full for v in gq.values() for p in v.values())
        total = sum(len(v) for v in gq.values())
        if inside < total:
            notes.append(f"hive: 存疑——{total - inside}/{total} 条金标证据句不逐字出现在归一化语料中（这些题该句永远拿不到满分）")
    notes.append(f"{name}: {len(qids)} 题（dev {len(dev)} / test {len(test)}），源文件指纹与选题复算一致")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--sets"); ap.add_argument("--frozen-only", action="store_true")
    a = ap.parse_args()
    man = json.loads((UMB / "manifest.json").read_text(encoding="utf-8"))
    sets = a.sets.split(",") if a.sets else list(man["sets"])
    for name in sets:
        info = man["sets"].get(name)
        if not check(info is not None and info.get("status") == "ok", f"{name}: manifest 无此集或状态非 ok"):
            continue
        verify_set(name, info, a.frozen_only)
    print("\n".join(notes))
    if a.frozen_only:
        print("注意：--frozen-only 未校验语料重建、公开源指纹与选题复算")
    if fails:
        print("FAIL", len(fails)); print("\n".join(fails[:50])); sys.exit(1)
    print("ALL OK", f"({len(sets)} 集)")


if __name__ == "__main__":
    main()
