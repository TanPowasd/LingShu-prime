"""零 key 重放：复用 llm_dm 已缓存的 LLM 抽取 → 写入编年判别记忆（ChronicleDM，
编年时间线 + Memory 外壳双写）→ 按 ChronicleDM.ask 机械作答；同时统计两核心一致率。
不发任何请求。判分：官方 probe_judge.judge_arm（机械、零 LLM）。

用法：python chain_chronicle_dm_replay.py <bench>
"""
from __future__ import annotations

import json, math, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))
import chain_bench as CB                      # noqa: E402
from chain_llm import parse_events, RES       # noqa: E402
from chronicle_dm import ChronicleDM          # noqa: E402

ARM = 'llm_chronicle_dm'


def build(events, q, ent, fac, by_cid):
    m, seen, n = ChronicleDM(), set(), 0
    for e in sorted(events, key=lambda e: e['seq']):
        key = (e['seq'], e['op'], json.dumps(e['value'], ensure_ascii=False), json.dumps(e['alt'], ensure_ascii=False))
        if key in seen:
            continue
        seen.add(key)
        t = float(e['seq'])
        kw = dict(effective_at=t, recorded_at=t, source_id=str(e.get('cid') or f'seq{e["seq"]}'),
                  quote=(by_cid.get(e.get('cid')) or {}).get('text', '')[:200])
        try:
            if e['op'] == 'retire':
                m.record(f'e{n}', ent, fac, 'retire', **kw)
            elif e['op'] == 'unresolve' and e['alt'] is not None:
                m.record(f'e{n}', ent, fac, 'unresolved', value=str(e['value']), alternative=str(e['alt']), **kw)
            elif e['value'] is not None:
                m.record(f'e{n}', ent, fac, 'set', value=str(e['value']), **kw)
            else:
                continue
            n += 1
        except Exception:   # noqa: BLE001
            continue
    return m, n


def answer(events, q, n_seq, by_cid):
    typ, T, ent, fac = CB.parse_q(q['question'], n_seq)
    a = dict(qid=q['qid'], value=None, state='absent', at_seq=None, chain=[], basis=[], confidence='unknown')
    if not ent:
        return a, 0, None, None
    m, n = build(events, q, ent, fac, by_cid)
    at = float(T) if T is not None else math.inf
    r = m.ask(ent, fac, 'at', at=at)
    if typ == '变更':
        a['chain'] = [{'seq': int(x['seq']), 'from': x['from'], 'to': x['to']}
                      for x in m.ask(ent, fac, 'chain', at=at)['chain']]
    a['state'], a['value'] = r['state'], r['value']
    a['at_seq'] = int(r['since']) if r['since'] is not None else None
    if typ == '缘由':
        a['value'] = m.ask(ent, fac, 'reason', at=at, event_at=at)['reason']
    a['confidence'] = 'certain' if n else 'unknown'
    for ev in m.timeline.events(ent, fac, at=at)[-3:]:
        c = by_cid.get(ev.source_id)
        if c:
            a['basis'].append({'file': ev.source_id, 'line': c['seq'], 'quote': c['text'][:200]})
    return a, n, r['agree'], m


def main():
    bench = Path(sys.argv[1])
    data = RES / 'data'
    corpus = json.loads((data / 'corpus.json').read_text(encoding='utf-8'))
    keys = json.loads((data / 'keys.json').read_text(encoding='utf-8'))
    by_cid = {c['cid']: c for c in corpus}
    n_seq = {}
    for c in corpus:
        n_seq[c['doc']] = max(n_seq.get(c['doc'], 0), c['seq'])
    sys.path.insert(0, str(bench / 'chain' / 'tools'))
    import probe_judge as J
    J.OUT, J.RUNS = data, RES / 'runs'
    raw_dir = RES / 'llm_raw' / 'llm_dm'
    d = RES / 'runs' / f'chain_{ARM}'
    (d / 'sut' / 'out').mkdir(parents=True, exist_ok=True)
    agree, total_ev = Counter(), 0
    for q in keys:
        p = raw_dir / f"{q['qid']}.txt"
        a, n, ag, _ = answer(parse_events(p.read_text(encoding='utf-8') if p.exists() else ''), q, n_seq[q['doc']], by_cid)
        total_ev += n
        agree[str(ag)] += 1
        (d / 'sut' / 'out' / f"{q['qid']}.json").write_text(json.dumps(a, ensure_ascii=False), encoding='utf-8')
    _, doc_norms, decoys = J._corpus_index()
    row = {'arm': ARM, 'llm_calls': 0, 'events_written': total_ev, 'core_agreement': dict(agree)}
    for split, ks in (('all', keys), ('test', [k for k in keys if k['doc_id'] not in CB.DEV])):
        row[split] = J.judge_arm(ARM, ks, doc_norms, decoys)
    (RES / 'chain_readings_chronicle_dm.json').write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding='utf-8')
    t = row['test']
    print(f"{ARM} test 现值{t['present']:.3f} 历史{t['history']:.3f} 变更{t['chain']:.3f} 四态{t['four_state']:.3f} "
          f"缘由{t['reason']:.3f} 滞后{t['stale']:.3f} n={t['n']} 事件{total_ev} 两核心一致{dict(agree)} 调用0")


if __name__ == '__main__':
    main()
