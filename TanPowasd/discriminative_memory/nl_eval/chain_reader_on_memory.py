"""带 key：RRF3 召回 → LLM 抽取（复用 llm_dm 缓存，0 次新调用）→ 记忆核心 → 官方 LLM 读者作答。

  llm_dm_reader         记忆核心 = discriminative_memory.Memory
  llm_chronicle_reader  记忆核心 = chronicle.ChronicleMemory（编年）
  llm_chronicle_dm_reader 记忆核心 = chronicle_dm.ChronicleDM（编年判别记忆，合体）

读者材料 = 记忆核心的查询结果（一段「记忆查询」摘要）+ 写入事件对应的原文片段（按序号）。
读者提示与 llm_rrf3 完全相同（probe_runner.CHAIN_SYS + build_prompt），只换材料。
每臂每题 1 次调用。判分：官方 probe_judge.judge_arm（机械、零 LLM）。

用法：python chain_reader_on_memory.py <bench> [--arms llm_dm_reader,llm_chronicle_reader] [--dry] [--workers 16]
"""
from __future__ import annotations

import argparse, json, math, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))
import chain_bench as CB                                                        # noqa: E402
from chain_llm import (LLM, MODEL, RES, build_prompt, dm_from_events, load_official,   # noqa: E402
                       parse_answer, parse_events)
from chain_chronicle_replay import vcm_answer                                   # noqa: E402

ST = {'active': '有效', 'retired': '已撤销', 'unresolved': '未裁定', 'absent': '不存在'}


def _events_text(events):
    rows = []
    for e in sorted(events, key=lambda e: e['seq']):
        v = e['value'] if e['op'] != 'unresolve' else f"{e['value']} / {e['alt']}（并存）"
        rows.append(f"- 第{e['seq']}：{e['op']} {v if e['op'] != 'retire' else ''}".rstrip())
    return '\n'.join(rows) or '（无事件）'


def material_for(arm, events, q, n_seq, by_cid):
    typ, T, ent, fac = CB.parse_q(q['question'], n_seq)
    if arm == 'llm_chronicle_dm_reader':
        from chain_chronicle_dm_replay import build
        import math as _m
        m, _ = build(events, q, ent, fac, by_cid)
        at = float(T) if T is not None else _m.inf
        mode = 'reason' if typ == '缘由' else 'chain' if typ in ('变更', '历史') else 'at'
        summary = '记忆核心：编年判别记忆 ChronicleDM\n' + m.render(m.ask(ent, fac, mode, at=at, event_at=at if mode == 'reason' else None)) \
            + '\n已写入的版本事件：\n' + _events_text(events)
        mat = [{'cid': '记忆查询', 'text': summary}]
        seen = set()
        for e in sorted(events, key=lambda e: e['seq']):
            c = by_cid.get(e.get('cid'))
            if c and c['cid'] not in seen:
                seen.add(c['cid'])
                mat.append({'cid': c['cid'], 'text': c['text']})
        return mat
    if arm == 'llm_dm_reader':
        a = dm_from_events(events, q, n_seq, by_cid)
        core = 'discriminative_memory.Memory'
    else:
        a, _ = vcm_answer(events, q, n_seq, by_cid)
        core = '编年 ChronicleMemory'
    chain = a.get('chain') or []
    summary = (f'记忆核心：{core}\n槽位：{ent} · {fac}\n查询时点：第{T}\n'
               f"该时点状态：{ST.get(a['state'], a['state'])}；取值：{a['value']}；最近生效序号：{a['at_seq']}\n"
               + (f'变更链：{json.dumps(chain, ensure_ascii=False)}\n' if chain else '')
               + '已写入的版本事件：\n' + _events_text(events))
    mat = [{'cid': '记忆查询', 'text': summary}]
    seen = set()
    for e in sorted(events, key=lambda e: e['seq']):
        c = by_cid.get(e.get('cid'))
        if c and c['cid'] not in seen:
            seen.add(c['cid'])
            mat.append({'cid': c['cid'], 'text': c['text']})
    return mat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('bench')
    ap.add_argument('--arms', default='llm_dm_reader,llm_chronicle_reader')
    ap.add_argument('--workers', type=int, default=16)
    ap.add_argument('--model', default=MODEL)
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()
    sysmsg = load_official(args.bench)
    data = RES / 'data'
    corpus = json.loads((data / 'corpus.json').read_text(encoding='utf-8'))
    keys = json.loads((data / 'keys.json').read_text(encoding='utf-8'))
    by_cid = {c['cid']: c for c in corpus}
    n_seq = {}
    for c in corpus:
        n_seq[c['doc']] = max(n_seq.get(c['doc'], 0), c['seq'])
    sys.path.insert(0, str(Path(args.bench) / 'chain' / 'tools'))
    import probe_judge as J
    J.OUT, J.RUNS = data, RES / 'runs'
    ext = RES / 'llm_raw' / 'llm_dm'
    llm = None if args.dry else LLM(args.model)
    readings = []
    for arm in args.arms.split(','):
        d = RES / 'runs' / f'chain_{arm}'
        raw_dir = RES / 'llm_raw' / arm
        (d / 'sut' / 'out').mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)

        def prompt(q):
            p = ext / f"{q['qid']}.txt"
            ev = parse_events(p.read_text(encoding='utf-8') if p.exists() else '')
            return build_prompt(sysmsg, q['qid'], q['question'], material_for(arm, ev, q, n_seq[q['doc']], by_cid))

        todo = [q for q in keys if not (raw_dir / f"{q['qid']}.txt").exists()]
        if args.dry:
            print(f'{arm:22s} 待调用 {len(todo)} / {len(keys)}')
            if todo:
                print(prompt(todo[0])[-1]['content'][:800])
            continue

        def one(q):
            (raw_dir / f"{q['qid']}.txt").write_text(llm.chat(prompt(q)), encoding='utf-8')

        with ThreadPoolExecutor(args.workers) as ex:
            for f in [ex.submit(one, q) for q in todo]:
                try:
                    f.result()
                except Exception as e:   # noqa: BLE001
                    print('  失败', type(e).__name__, str(e)[:120], flush=True)
        miss = 0
        for q in keys:
            p = raw_dir / f"{q['qid']}.txt"
            miss += not p.exists()
            a = parse_answer(p.read_text(encoding='utf-8') if p.exists() else '', q['qid'])
            (d / 'sut' / 'out' / f"{q['qid']}.json").write_text(json.dumps(a, ensure_ascii=False), encoding='utf-8')
        _, doc_norms, decoys = J._corpus_index()
        row = {'arm': arm, 'missing': miss}
        for split, ks in (('all', keys), ('test', [k for k in keys if k['doc_id'] not in CB.DEV])):
            row[split] = J.judge_arm(arm, ks, doc_norms, decoys)
        readings.append(row)
        t = row['test']
        print(f"{arm:22s} test 现值{t['present']:.3f} 历史{t['history']:.3f} 变更{t['chain']:.3f} "
              f"四态{t['four_state']:.3f} 缘由{t['reason']:.3f} 滞后{t['stale']:.3f} n={t['n']} 缺答{miss} "
              f"本次调用{llm.calls}", flush=True)
    if not args.dry:
        (RES / 'chain_readings_reader_on_memory.json').write_text(
            json.dumps(dict(model=args.model, readings=readings), ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
