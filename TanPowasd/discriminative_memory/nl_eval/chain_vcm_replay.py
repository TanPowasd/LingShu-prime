"""零 key 重放：RRF3 召回 → LLM 抽取（复用 llm_dm 已缓存的原始回复，不发任何请求）
→ 写入 TanPowasd/version_chain_memory.VersionChainMemory → 按 VCM.query 作答。

与 llm_dm 唯一差别：中间的记忆核心由 discriminative_memory.Memory 换成版本链记忆。
抽取提示当时未要求缘由，故事件 reason=None，缘由题按实得分（预期 0），不做任何补救。
判分：官方 probe_judge.judge_arm（机械、零 LLM）。

用法：python chain_vcm_replay.py <bench>
前置：chain_bench.py 已生成 results/chain/data/，llm_raw/llm_dm/ 已有缓存。
"""
from __future__ import annotations

import json, math, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))
import chain_bench as CB                              # noqa: E402
from chain_llm import parse_events, RES               # noqa: E402
from version_chain_memory import Event, Query, VersionChainMemory   # noqa: E402

ARM = 'llm_vcm'


def vcm_answer(events, q, n_seq, by_cid):
    typ, T, ent, fac = CB.parse_q(q['question'], n_seq)
    a = dict(qid=q['qid'], value=None, state='absent', at_seq=None, chain=[], basis=[], confidence='unknown')
    if not ent:
        return a, 0
    m = VersionChainMemory()
    seen, prev, n = set(), None, 0
    for e in sorted(events, key=lambda e: e['seq']):
        key = (e['seq'], e['op'], json.dumps(e['value'], ensure_ascii=False), json.dumps(e['alt'], ensure_ascii=False))
        if key in seen:
            continue
        seen.add(key)
        t = float(e['seq'])
        common = dict(event_id=f"{q['qid']}:{n}", source_id=str(e.get('cid') or f'seq{e["seq"]}'),
                      entity=ent, facet=fac, effective_at=t, recorded_at=t, previous=prev,
                      quote=(by_cid.get(e.get('cid')) or {}).get('text', '')[:200])
        try:
            if e['op'] == 'retire':
                m.add_event(Event(operation='retire', value=None, **common)); prev = None
            elif e['op'] == 'unresolve' and e['alt'] is not None:
                m.add_event(Event(operation='unresolved', value=str(e['value']), alternative=str(e['alt']), **common))
                prev = str(e['value'])
            elif e['value'] is not None:
                m.add_event(Event(operation='set', value=str(e['value']), **common)); prev = str(e['value'])
            else:
                continue
            n += 1
        except Exception:   # noqa: BLE001
            continue
    at = float(T) if T is not None else math.inf
    if typ == '变更':
        r = m.query(Query(ent, fac, mode='chain', at=at))
        a['chain'] = [{'seq': int(x['seq']), 'from': x['from'], 'to': x['to']} for x in r['chain']]
    mode = 'reason' if typ == '缘由' else 'state' if typ == '状态归属' else 'at'
    r = m.query(Query(ent, fac, mode=mode, at=at, event_at=at if mode == 'reason' else None))
    if mode == 'reason':                              # 原因字段（抽取时未取，故为 None）+ 该时点状态
        s = m.query(Query(ent, fac, mode='at', at=at))
        a['state'], a['value'] = s['state'], r['value']
        a['at_seq'] = int(s['at']) if s['at'] is not None else None
    else:
        a['state'], a['value'] = r['state'], r['value']
        a['at_seq'] = int(r['at']) if r['at'] is not None else None
    a['confidence'] = 'certain' if n else 'unknown'
    for ev in m.events(ent, fac, at=at)[-3:]:
        c = by_cid.get(ev.source_id)
        if c:
            a['basis'].append({'file': ev.source_id, 'line': c['seq'], 'quote': c['text'][:200]})
    return a, n


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
    missing = events_total = 0
    for q in keys:
        p = raw_dir / f"{q['qid']}.txt"
        missing += not p.exists()
        a, n = vcm_answer(parse_events(p.read_text(encoding='utf-8') if p.exists() else ''), q, n_seq[q['doc']], by_cid)
        events_total += n
        (d / 'sut' / 'out' / f"{q['qid']}.json").write_text(json.dumps(a, ensure_ascii=False), encoding='utf-8')
    (d / 'manifest.json').write_text(json.dumps(dict(arm=ARM, llm_calls=0, source_cache='llm_raw/llm_dm',
                                                     missing_cache=missing), ensure_ascii=False), encoding='utf-8')
    _, doc_norms, decoys = J._corpus_index()
    row = {'arm': ARM, 'llm_calls': 0, 'missing_cache': missing, 'events_written': events_total}
    for split, ks in (('all', keys), ('test', [k for k in keys if k['doc_id'] not in CB.DEV])):
        row[split] = J.judge_arm(ARM, ks, doc_norms, decoys)
    (RES / 'chain_readings_vcm.json').write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding='utf-8')
    t = row['test']
    print(f"{ARM:10s} test 现值{t['present']:.3f} 历史{t['history']:.3f} 变更{t['chain']:.3f} "
          f"四态{t['four_state']:.3f} 缘由{t['reason']:.3f} 滞后{t['stale']:.3f} 回源{t['verbatim']:.3f} "
          f"n={t['n']} 缺缓存{missing} 写入事件{events_total} 调用0")


if __name__ == '__main__':
    main()
