# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""md_cg×TriCue 原 AGM vs 拓展 AGM（RA）在 LongMemEval-S test 上的成对读数（零模型零 key）。
每题一个独立 MdCGOS 库，haystack 各轮按序 add（role=原角色，layer=knowledge，verification_basis=data）；
MDCG_TRICUE=1；同一库上先查 RA 关（tricue_rerank.RA_ROLES 置空）、再查 RA 开，两次之间清索引缓存。
划分与 agm/lex 相同：md5(question_id)%3==0 为 dev，其余 test。指标 r@5/10/25、hit@10（轮级）。
用法：PYTHONUTF8=1 python -X utf8 bench_lme_ra.py --repo <dsh-memory 仓根> --data partK.json --out x.json [--shard i/n]"""
import argparse, atexit, hashlib, json, os, shutil, sys, tempfile, time

KS = (5, 10, 25)


def score(r, gold):
    x = {f"r@{k}": len(gold & set(r[:k])) / len(gold) for k in KS}
    x["hit@10"] = float(bool(gold & set(r[:10]))); return x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True); ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--split", default="test"); ap.add_argument("--shard", default="0/1")
    a = ap.parse_args(); si, sn = map(int, a.shard.split("/"))
    sys.path.insert(0, os.path.abspath(a.repo)); os.environ["MDCG_TRICUE"] = "1"
    from md_cg.mdcos import MdCGOS
    from md_cg import tricue_rerank as TR
    on_roles = TR.RA_ROLES
    root = tempfile.mkdtemp(prefix="lme_ra_"); atexit.register(shutil.rmtree, root, True)
    per, t0, n = [], time.time(), -1
    for it in json.load(open(a.data, encoding="utf-8")):
        if ("dev" if int(hashlib.md5(it["question_id"].encode()).hexdigest(), 16) % 3 == 0 else "test") != a.split:
            continue
        texts, gold, roles = [], set(), []
        for ses in it["haystack_sessions"]:
            for t in ses:
                if t.get("has_answer"):
                    gold.add(len(texts))
                texts.append(f"{t['role']}: {t['content']}"); roles.append(t["role"])
        if not gold:
            continue
        n += 1
        if n % sn != si:
            continue
        cg = MdCGOS(os.path.join(root, it["question_id"]))
        for i, (t, r) in enumerate(zip(texts, roles)):
            cg.add(f"t_{i}", t, layer="knowledge", verification_basis="data", role=r)
        out = {}
        for arm, rs in (("md_cg×TriCue", frozenset()), ("md_cg×TriCue+RA", on_roles)):
            TR.RA_ROLES = rs; cg._tricue_cache = None
            res, _ = cg.search(it["question"], k=100, judge=False, record=False)
            out[arm] = [int(x[0]["id"][2:]) for x in res]
        TR.RA_ROLES = on_roles
        shutil.rmtree(os.path.join(root, it["question_id"]), True)
        per.append({"qid": it["question_id"], "type": it["question_type"], "arms": {k: score(v, gold) for k, v in out.items()}})
        print(n, {k: v["r@10"] for k, v in per[-1]["arms"].items()}, f"{time.time() - t0:.0f}s", flush=True)
    json.dump({"meta": {"split": a.split, "shard": a.shard, "n": len(per), "secs": round(time.time() - t0, 1)}, "per": per},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False)
    print(a.out, len(per), f"{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
