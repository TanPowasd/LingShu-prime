"""Hive-memory-bench retrieval face with the NL interpreter (zero model, zero key).

Every corpus chunk is ingested through NLMemory (claims extracted where the
surface syntax allows; raw text always kept).  For each main-round question
the interpreter tries to bind a slot.  When bound, the chunks cited by the
discriminative answer go first and the rest of the budget is filled by the
fallback order; when not bound, the fallback order alone is used.

Arms: BM25, RRF(BM25,AGM), 判别+BM25, 判别+RRF.  Same chunks, budgets and
scoring as agm/bench/hive_retrieval_full.py (primary evidence quote fully
inside the context).  Usage:
  python -B -X utf8 nl_eval/hive_nl_bench.py <hive-memory-bench> [--json out]
"""
import argparse, json, random, socket, statistics, sys
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent / 'agm' / 'bench'))
import hive_retrieval as HR          # noqa: E402
import agm_algos as X                # noqa: E402
from hive_retrieval_full import per_q  # noqa: E402
from discriminative_memory import Need, Query  # noqa: E402
from nl_interpret import NLMemory    # noqa: E402

FAR = 1e9   # dates in prose map to ordinal days; ask after all of them


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root')
    ap.add_argument('--json')
    a = ap.parse_args()
    root = Path(a.root)
    chunks, cards = HR.load_chunks(root), HR.load_cards(root)
    N = len(chunks)
    nm = NLMemory()
    sid2chunk = {}
    claim_samples = []
    n_claim_chunks = 0
    for i, c in enumerate(chunks):
        rep = nm.ingest(f'c{i:04d}', c['text'], recorded_at=i)
        written = [x for x in rep['applied'] if x['op'] in ('state', 'plan', 'correct')]
        for x in rep['applied']:
            if x.get('sid'):
                sid2chunk[x['sid']] = i
        sid2chunk[f'c{i:04d}'] = i
        if written:
            n_claim_chunks += 1
        for cand in rep['candidates']:
            claim_samples.append({'chunk': i, **{k: cand[k] for k in ('op', 'entity', 'facet', 'value', 'span')}})
    bm = HR.BM25(chunks)
    agm = HR.AGM(chunks, bm)
    orders = {k: {} for k in ('BM25', 'RRF(BM25,AGM)', '判别+BM25', '判别+RRF')}
    bindings = []
    for c in cards:
        qid, qt = c['qid'], c['question']
        s = bm.scores(qt)
        o_bm = sorted(range(N), key=lambda i: -s[i])
        o_rrf = X.rrf([o_bm, agm.rank(qt)])
        r = nm.ask(qt, now=FAR, budget=10 ** 9)
        first = []
        if r['binding']['status'] == 'bound':
            for sid in r['result']['selected']:
                base = sid.split('/')[0]
                j = sid2chunk.get(sid, sid2chunk.get(base))
                if j is not None and j not in first:
                    first.append(j)
        bindings.append({'qid': qid, 'q': qt, 'binding': r['binding'], 'evidence_chunks': first})
        orders['BM25'][qid] = o_bm
        orders['RRF(BM25,AGM)'][qid] = o_rrf
        orders['判别+BM25'][qid] = first + [i for i in o_bm if i not in first]
        orders['判别+RRF'][qid] = first + [i for i in o_rrf if i not in first]
    res = {}
    for B in HR.BUDGETS:
        rows = {arm: [per_q(c, HR.take(orders[arm][c['qid']], chunks, B)) for c in cards] for arm in orders}
        keep = [i for i, v in enumerate(rows['BM25']) if v is not None]
        summ = {arm: {'primary召回': round(statistics.mean(rows[arm][i]['primary召回'] for i in keep), 3),
                      '全证据题': f"{int(sum(rows[arm][i]['全证据'] for i in keep))}/{len(keep)}"} for arm in rows}
        cmp = {f'{x} 对 {y}': X.compare([rows[x][i]['primary召回'] for i in keep], [rows[y][i]['primary召回'] for i in keep])
               for x, y in (('判别+BM25', 'BM25'), ('判别+RRF', 'RRF(BM25,AGM)'), ('RRF(BM25,AGM)', 'BM25'))}
        res[str(B)] = {'汇总': summ, '配对_primary召回_按题': cmp}
    bound = [b for b in bindings if b['binding']['status'] == 'bound']
    rng = random.Random(0)
    sample = rng.sample(claim_samples, min(40, len(claim_samples)))
    out = {'说明': '零模型解释器在 Hive 语料上的检索面；参数跑前写死；未调用任何模型或 key',
           '语料块': N, '题数': len(cards),
           '解释': {'候选总数': len(claim_samples), '写入声明的块': n_claim_chunks,
                    '按操作': {op: sum(1 for x in claim_samples if x['op'] == op) for op in sorted({x['op'] for x in claim_samples})},
                    '统计': nm.m.statistics(), '随机抽样40条': sample},
           '问题绑定': {'绑定成功': len(bound), '绑定详情': bound,
                       '未绑定原因': {k: sum(1 for b in bindings if b['binding']['status'] == k) for k in ('unbound', 'ambiguous')}},
           '按预算': res}
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if a.json:
        Path(a.json).write_text(txt, encoding='utf-8')
    print(json.dumps({k: v for k, v in out.items() if k not in ('解释', '问题绑定')} | {
        '解释摘要': {k: v for k, v in out['解释'].items() if k != '随机抽样40条'},
        '绑定': {'成功': len(bound), **out['问题绑定']['未绑定原因']}}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    def deny(*x, **k):
        raise RuntimeError('offline')
    with patch.object(socket, 'create_connection', deny), patch.object(socket.socket, 'connect', deny):
        main()
