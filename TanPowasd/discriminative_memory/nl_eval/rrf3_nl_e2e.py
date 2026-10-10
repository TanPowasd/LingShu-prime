"""RRF3 + discriminative-memory channel on the hive-memory-bench e2e stream (zero model, zero key).

Per conversation file, RRF3Memory and NLMemory receive the same turns.  For
every human turn followed by an AI turn, the human text is the query; target
= salient bigrams of the true next AI reply (same proxy as
agm/bench/hive_e2e_full.py).  When the interpreter binds the query to a
slot, the turns cited by the discriminative answer become
  * RRF3+判别:      a 4th RRF list
  * RRF3+判别置顶:  pinned ahead of the RRF3 order
Unbound queries leave both arms identical to RRF3.  Metrics: coverage and
window-out gain (covered but not by the full-budget recent window), per file
sign tests.  Parameters fixed before the run.
Usage: python -B -X utf8 nl_eval/rrf3_nl_e2e.py <hive-memory-bench> [--json out]
"""
import argparse, collections, json, socket, sys, math
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
TAN = HERE.parent.parent
sys.path[:0] = [str(HERE.parent), str(TAN / 'agm' / 'rrf3'), str(TAN / 'agm' / 'bench')]
import rrf3 as R                                   # noqa: E402
from hive_e2e_stream import bset, chunk_turn, parse            # noqa: E402
from nl_interpret import NLMemory, bind_question   # noqa: E402
from discriminative_memory import Need, Query      # noqa: E402

BUDGET = 4000


def take(order, mem, budget=BUDGET):
    got, used = [], 0
    for i in order:
        if used + mem.size[i] > budget and used:
            break
        got.append(i); used += mem.size[i]
    return got


def sign_p(w, l):
    n = w + l
    if not n:
        return 1.0
    k = min(w, l)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('root')
    ap.add_argument('--json')
    a = ap.parse_args()
    files = sorted((Path(a.root) / 'e2e' / 'corpus').glob('*.md'))
    arms = ('最近窗口', 'RRF3', 'RRF3+判别', 'RRF3+判别置顶')
    per_file = {}
    tot = {'查询': 0, '绑定': 0, '绑定且有证据': 0, '声明': 0, '轮': 0}
    bound_examples = []
    for f in files:
        turns = parse(f)
        allc = [c for t in turns for c in chunk_turn(t)]
        dfc = collections.Counter(g for _, x in allc for g in bset(x))
        capf = max(2, int(0.02 * len(allc)))
        mem, nm = R.RRF3Memory(), NLMemory()
        turn_chunks = {}
        sums = {k: [0.0, 0.0] for k in arms}
        n = 0
        for ti, t in enumerate(turns):
            if t['who'] == 'human' and ti + 1 < len(turns) and turns[ti + 1]['who'] == 'ai' and mem.N:
                q = bset(t['text'])
                tgt = {g for g in bset(turns[ti + 1]['text']) if dfc.get(g, 0) <= capf} - q
                if tgt:
                    n += 1; tot['查询'] += 1
                    base = mem.rank(t['text'])
                    extra = []
                    b = bind_question(t['text'], now=ti, known=nm.known, topic=nm.topic)
                    if b['status'] == 'bound':
                        tot['绑定'] += 1
                        r = nm.m.query(Query((Need('a', b['slots'][0], b['mode']),), b['at']), 10 ** 9)
                        for sid in r['selected']:
                            tj = int(sid.split('/')[0][1:])
                            for c in turn_chunks.get(tj, []):
                                if c not in extra:
                                    extra.append(c)
                        if extra:
                            tot['绑定且有证据'] += 1
                        if len(bound_examples) < 30:
                            bound_examples.append({'file': f.name, 'turn': ti, 'q': t['text'][:80], 'slot': b['slots'][0].key, 'evidence_turns': sorted({mem.turn_of[c] for c in extra})})
                    recent = take(mem.rank_recent(), mem)
                    orders = {'最近窗口': recent, 'RRF3': take(base, mem),
                              'RRF3+判别置顶': take(extra + [i for i in base if i not in extra], mem)}
                    orders['RRF3+判别'] = take(R.rrf([mem.rank_recent(), *_bm_agm(mem, t['text']), extra]) if extra else base, mem)
                    rctx = set().union(*(bset(mem.raw[i]) for i in recent)) if recent else set()
                    for k, got in orders.items():
                        cx = set().union(*(bset(mem.raw[i]) for i in got)) if got else set()
                        sums[k][0] += len(tgt & cx) / len(tgt)
                        sums[k][1] += len((tgt & cx) - rctx) / len(tgt)
            turn_chunks[ti] = mem.add_turn(t['who'], t['text'])
            rep = nm.ingest(f't{ti}', t['text'], recorded_at=ti)
            tot['声明'] += sum(len(x.get('slots', [])) for x in rep['applied'] if x['op'] in ('state', 'plan', 'correct'))
            tot['轮'] += 1
        per_file[f.name] = {k: {'覆盖': round(v[0] / n, 4), '窗口外': round(v[1] / n, 4)} for k, v in sums.items()} | {'查询': n}
        print(f.name, n, json.dumps({k: per_file[f.name][k] for k in arms}, ensure_ascii=False), flush=True)
    summary, tests = {}, {}
    for k in arms:
        w = sum(per_file[x]['查询'] for x in per_file)
        summary[k] = {m: round(sum(per_file[x][k][m] * per_file[x]['查询'] for x in per_file) / w, 4) for m in ('覆盖', '窗口外')}
    for x, y in (('RRF3+判别', 'RRF3'), ('RRF3+判别置顶', 'RRF3')):
        for m in ('覆盖', '窗口外'):
            wi = sum(per_file[f][x][m] > per_file[f][y][m] for f in per_file)
            lo = sum(per_file[f][x][m] < per_file[f][y][m] for f in per_file)
            tests[f'{x} 对 {y} {m}'] = {'胜': wi, '负': lo, '平': len(per_file) - wi - lo, '符号p': round(sign_p(wi, lo), 4)}
    out = {'说明': 'RRF3 加判别记忆通道；零模型零 key；参数跑前写死', '预算': BUDGET, '总计': tot, '汇总': summary,
           '按文件符号检验': tests, '按文件': per_file, '绑定样例': bound_examples}
    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if a.json:
        Path(a.json).write_text(txt, encoding='utf-8')
    print(json.dumps({k: out[k] for k in ('总计', '汇总', '按文件符号检验')}, ensure_ascii=False, indent=1))


def _bm_agm(mem, text):
    sc = mem.bm25(text)
    return [sorted(sc, key=lambda i: -sc[i]), mem.rank_agm(sc)]


if __name__ == '__main__':
    def deny(*x, **k):
        raise RuntimeError('offline')
    with patch.object(socket, 'create_connection', deny), patch.object(socket.socket, 'connect', deny):
        main()
