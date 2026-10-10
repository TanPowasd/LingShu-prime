"""Offline evaluation of the zero-model NL interpreter (no network, no key).

Part A  hand-written NL cases (dev set + held-out set hashed before the
        interpreter existed).  Reports claim precision/recall, question
        binding, end-to-end answers, and attributes each wrong answer to
        interpretation, binding, or memory/selection.
Part B  the 150 synthetic schema tasks of bench_discriminative: raw texts
        only -> interpreter -> memory -> same requirements; coverage vs the
        caller-confirmed structure at the same budgets.

Usage:  python -B -X utf8 nl_eval/eval_nl.py [--output outputs/nl]
"""
import argparse, hashlib, json, math, socket, sys, statistics
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from discriminative_memory import Memory, Need, Query, solve  # noqa: E402
from nl_interpret import NLMemory, interpret, parse_value     # noqa: E402

HELDOUT_SHA = '3de04c68f8f56da55e83bf221f3b989f33914e12288a3ce24ba810fca5e0ba54'


def nv(v):
    if isinstance(v, str):
        v = parse_value(v)
    if isinstance(v, str):
        return v.casefold().strip()
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def same_slot(e1, f1, e2, f2):
    return e1 is not None and f1 is not None and e1.casefold() == e2.casefold() and f1.casefold() == f2.casefold()


def run_cases(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    tp = fp = fn = 0
    qrows = []
    claim_rows = []
    for case in data['cases']:
        nm = NLMemory()
        missed_slots = set()
        for k, turn in enumerate(case['turns']):
            rep = nm.ingest(f"{case['id']}_{k}", turn['text'], recorded_at=turn['t'])
            pred = []
            for c in rep['candidates']:
                if c['op'] == 'retract':
                    tgt = [a for a in rep['applied'] if a['op'] == 'retract']
                    slots = []
                    for a in tgt:
                        for sid, keys in nm.last_sources:
                            if sid == a['target']:
                                slots += [json.loads(x)[:2] for x in keys]
                    pred += [('retract', e, f, None) for e, f in slots] or [('retract', None, None, None)]
                else:
                    pred.append((c['op'], c['entity'], c['facet'], c['value']))
            gold = [(g['op'], g['e'], g['f'], g.get('v')) for g in turn['gold']]
            used = set()
            for g in gold:
                hit = None
                for i, p in enumerate(pred):
                    if i in used:
                        continue
                    if p[0] == g[0] and same_slot(p[1], p[2], g[1], g[2]) and (g[0] == 'retract' or nv(p[3]) == nv(g[3])):
                        hit = i
                        break
                if hit is None:
                    fn += 1
                    missed_slots.add((g[1].casefold(), g[2].casefold()))
                else:
                    used.add(hit)
                    tp += 1
            fp += len(pred) - len(used)
            claim_rows.append({'case': case['id'], 'text': turn['text'], 'gold': gold, 'pred': pred})
        for q in case['questions']:
            r = nm.ask(q['q'], now=q['t'])
            b = r['binding']
            bound_ok = False
            if b['status'] == 'bound':
                e, f = json.loads(b['slot'])[:2]
                bound_ok = same_slot(e, f, *q['slot']) and b['mode'] == q['mode']
            if r['status'] == 'evidence_only':
                got = None
            else:
                ans = r['answer']
                if q['mode'] == 'history':
                    got = [x['value'] for x in ans['value']] if ans['value'] else None
                elif q['mode'] == 'plans':
                    got = ans['value'][-1] if ans['value'] else None
                else:
                    got = ans['value'] if ans['status'] == 'known' else None
            if q['answer'] is None:
                ok = got is None
            elif q['mode'] == 'history':
                ok = got is not None and sorted(map(str, map(nv, got))) == sorted(map(str, map(nv, q['answer'])))
            else:
                ok = got is not None and nv(got) == nv(q['answer'])
            if ok:
                cause = None
            elif (q['slot'][0].casefold(), q['slot'][1].casefold()) in missed_slots:
                cause = 'interpretation'
            elif not bound_ok:
                cause = 'binding'
            else:
                cause = 'memory_or_selection'
            qrows.append({'case': case['id'], 'q': q['q'], 'mode': q['mode'], 'gold': q['answer'], 'got': got,
                          'bound_ok': bound_ok, 'ok': ok, 'cause': cause})
    prec = tp / (tp + fp) if tp + fp else 1.
    rec = tp / (tp + fn) if tp + fn else 1.
    causes = {}
    for r in qrows:
        if r['cause']:
            causes[r['cause']] = causes.get(r['cause'], 0) + 1
    return {'claims': {'tp': tp, 'fp': fp, 'fn': fn, 'precision': round(prec, 4), 'recall': round(rec, 4)},
            'questions': {'n': len(qrows), 'answer_ok': sum(r['ok'] for r in qrows),
                          'binding_ok': sum(r['bound_ok'] for r in qrows), 'error_causes': causes},
            'claim_rows': claim_rows, 'question_rows': qrows}


def run_bench():
    import bench_discriminative as B
    out = {str(b): {'confirmed': [], 'confirmed_recorded_clock': [], 'interpreted': []} for b in B.PARAMETERS['budgets']}
    tp = fp = fn = 0
    for index in range(B.PARAMETERS['packing_cases']):
        m, problem, expected, style = B.make_case(index, copies=False)
        rows = m.db.all("SELECT id,text,recorded FROM dm_sources WHERE kind='state' ORDER BY seq")
        gold_rows = m.db.all("SELECT source_id,slot,value_json FROM dm_claims")
        gold = {}
        for g in gold_rows:
            gold.setdefault(g['source_id'], {})[g['slot']] = json.loads(g['value_json'])
        nm = NLMemory(Memory())
        ctrl = Memory()
        from discriminative_memory import Slot
        for r in rows:
            g = gold.get(r['id'], {})
            ctrl.append(r['id'], r['text'], assertions={Slot.from_key(k): v for k, v in g.items()},
                        effective_at=r['recorded'], recorded_at=r['recorded'])
        for r in rows:
            cands, _, _ = interpret(r['text'], recorded_at=r['recorded'])
            pred = {c._slot.key: c.value for c in cands if hasattr(c, '_slot')}
            g = gold.get(r['id'], {})
            tp += sum(1 for k, v in pred.items() if k in g and g[k] == v)
            fp += sum(1 for k, v in pred.items() if k not in g or g[k] != v)
            fn += sum(1 for k in g if k not in pred or pred[k] != g[k])
            nm.ingest(r['id'], r['text'], recorded_at=r['recorded'])
        iprob = nm.m.prepare(problem.query)
        cprob = ctrl.prepare(problem.query)
        for b in B.PARAMETERS['budgets']:
            out[str(b)]['confirmed'].append(solve(problem, b)['weighted_coverage'])
            out[str(b)]['confirmed_recorded_clock'].append(solve(cprob, b)['weighted_coverage'])
            out[str(b)]['interpreted'].append(solve(iprob, b)['weighted_coverage'])
    summary = {b: {k: round(statistics.mean(v), 4) for k, v in d.items()} for b, d in out.items()}
    return {'claims': {'tp': tp, 'fp': fp, 'fn': fn}, 'coverage': summary,
            'note': 'confirmed_recorded_clock = gold assertions but each record effective at its receipt clock and no dependencies, the only clock a raw text gives. anchor claim and its dependencies plus effective_at=100 are not in the raw text; interpreted memory uses recorded clocks and no dependencies.'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default=str(HERE.parent / 'outputs' / 'nl'))
    a = ap.parse_args()
    attempts = []

    def deny(*x, **k):
        attempts.append(1)
        raise RuntimeError('offline')
    held = HERE / 'heldout_cases.json'
    sha = hashlib.sha256(held.read_bytes()).hexdigest()
    assert sha == HELDOUT_SHA, 'held-out cases changed'
    with patch.object(socket, 'create_connection', deny), patch.object(socket.socket, 'connect', deny):
        res = {'dev': run_cases(HERE / 'dev_cases.json'), 'heldout': run_cases(held), 'bench_structured': run_bench()}
    res['heldout_sha256'] = sha
    res['network_attempts'] = len(attempts)
    res['model_calls'] = 0
    o = Path(a.output)
    o.mkdir(parents=True, exist_ok=True)
    (o / 'nl_readings.json').write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding='utf-8')
    brief = {k: {kk: vv for kk, vv in v.items() if kk in ('claims', 'questions', 'coverage')} for k, v in res.items() if isinstance(v, dict)}
    print(json.dumps(brief, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
