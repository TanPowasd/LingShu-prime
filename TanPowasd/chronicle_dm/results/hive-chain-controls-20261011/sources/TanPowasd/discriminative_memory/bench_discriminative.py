"""Fixed offline tests of generic schemas, temporal semantics and evidence budgets."""
from collections import defaultdict
from dataclasses import asdict
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import socket
import statistics
import subprocess
import sys
import time
from unittest.mock import patch
from discriminative_memory import Memory,Slot,Dependency,Need,Query,solve,encoded,coverage,cost

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent.parent
OUTPUT=ROOT/'outputs'
PARAMETERS={'seed':917281,'packing_cases':150,'formats':5,'budgets':[512,1024,2048],
    'requirements':[4,7],'composite_records':[4,6],'copy_records_per_case':8,
    'exact_every':10,'exact_max_sources':12,'renaming_cases':20,
    'temporal_entities':24,'facets_per_entity':3,'episodes_per_facet':8,'temporal_queries':800}
ARMS={'判别记忆':('discriminative',True),'判别记忆-无替换':('discriminative',False),
      'SQL直接取证':('sql',True),'最短证据包':('shortest',True),'BM25证据包':('bm25',True),
      'AGM证据包':('agm',True),'RRF三路证据包':('rrf',True)}


def dump(name,obj): (OUTPUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def value(rng,index):
    options=[rng.randrange(1000),bool(rng.randrange(2)),f'v_{rng.getrandbits(24):06x}',
             [index,rng.randrange(7),False],{'code':rng.randrange(40),'flags':[True,False]}]
    return options[index%len(options)]


def make_case(index,prefix='k',copies=True):
    rng=random.Random(PARAMETERS['seed']+index)
    n=rng.randint(*PARAMETERS['requirements']);style=index%PARAMETERS['formats']
    slots=[Slot.of(f'{prefix}{index:04d}',f'{prefix}_f_{j:02d}',f'{prefix}_r',{'ctx':prefix+'_c'}) for j in range(n)]
    vals=[value(rng,j) for j in range(n)];weights=[rng.choice([1.,1.,2.]) for _ in range(n)]
    anchor=Slot.of(f'{prefix}_parent',f'{prefix}_guard');m=Memory()
    m.append('anchor',encoded({anchor.key:True}),assertions={anchor:True},effective_at=50,recorded_at=0)
    definitions=[]
    for j in range(n):definitions.append((frozenset({j}),rng.randrange(0,260)))
    for _ in range(rng.randint(*PARAMETERS['composite_records'])):
        subset=frozenset(rng.sample(range(n),rng.randint(2,min(n,5))))
        definitions.append((subset,rng.randrange(0,330)))
    rng.shuffle(definitions);definitions_with_source=[]
    for number,(subset,padding) in enumerate(definitions,1):
        assignments={slots[j]:vals[j] for j in sorted(subset)}
        deps={slots[j]:[Dependency.of(anchor,True)] for j in sorted(subset) if rng.random()<.2}
        body=encoded({s.key:v for s,v in assignments.items()})
        if style==0:text='Observations: '+body+'\n'+('context '*math.ceil(padding/8))[:padding]
        elif style==1:text='记录：'+body+'。'+('附记内容'*math.ceil(padding/4))[:padding]
        elif style==2:text=encoded({'observations':json.loads(body),'note':('xyz '*math.ceil(padding/4))[:padding]})
        elif style==3:text='\n'.join(s.key+' = '+encoded(v) for s,v in assignments.items())+'\n'+'.'*padding
        else:text=('description '*math.ceil(padding/12))[:padding]+'\n'+body
        sid=f's_{index:03d}_{number:02d}'
        m.append(sid,text,assertions=assignments,effective_at=100,recorded_at=number,
                 dependencies=deps,provenance_group='g_'+sid)
        definitions_with_source.append((sid,text,assignments,deps))
    requirements=tuple(Need('r'+str(j),slot,weight=weights[j]) for j,slot in enumerate(slots))
    query=Query(requirements,200,text=' '.join([slots[0].entity,*[s.facet for s in slots]]))
    problem=m.prepare(query)
    if copies:
        sid,text,assignments,deps=definitions_with_source[0]
        before=solve(problem,2048)
        for j in range(PARAMETERS['copy_records_per_case']):
            m.append('copy_'+str(j),text,assertions=assignments,effective_at=100,recorded_at=300+j,
                dependencies=deps,provenance_group='g_'+sid)
        after=m.prepare(query)
        assert before==solve(after,2048)
    expected={n.name:vals[j] for j,n in enumerate(requirements)}
    return m,problem,expected,style


def packing():
    rows=[];exact_rows=[];duplicate_checks=0
    for index in range(PARAMETERS['packing_cases']):
        m,problem,expected,style=make_case(index)
        try:
            duplicate_checks+=1
            assert len(problem.query.requirements)==len(coverage(problem,frozenset(problem.sources)))
            for budget in PARAMETERS['budgets']:
                for arm,(strategy,improve) in ARMS.items():
                    start=time.perf_counter();result=solve(problem,budget,strategy=strategy,improve=improve)
                    elapsed=(time.perf_counter()-start)*1000
                    assert result['budget_used']<=budget
                    for name in result['covered']:
                        assert result['answers'][name]['value']==expected[name]
                    for name in result['missing']:assert result['answers'][name]['value'] is None
                    assert all(item['text']==problem.sources[item['id']].text for item in result['evidence'])
                    rows.append({'case':index,'format':style,'arm':arm,'budget':budget,'coverage':result['weighted_coverage'],
                        'covered_count':len(result['covered']),'requirements':len(expected),'complete':not result['missing'],
                        'budget_used':result['budget_used'],'source_count':len(result['selected']),'query_ms':elapsed,
                        'selected':result['selected'],'missing':result['missing']})
                if index%PARAMETERS['exact_every']==0 and len(problem.sources)<=PARAMETERS['exact_max_sources']:
                    exact=solve(problem,budget,strategy='exact');heuristic=solve(problem,budget)
                    assert exact['weighted_coverage']+1e-12>=heuristic['weighted_coverage']
                    exact_rows.append({'case':index,'budget':budget,'sources':len(problem.sources),
                        'exact_coverage':exact['weighted_coverage'],'heuristic_coverage':heuristic['weighted_coverage'],
                        'exact_cost':exact['budget_used'],'heuristic_cost':heuristic['budget_used']})
            if index in (0,1):
                dump(f'packing_example_{index}.json',{'query':{**asdict(problem.query),'known_at':None},
                    'sources':{key:asdict(s) for key,s in problem.sources.items()},
                    'certificates':[{'refs':sorted(c.refs),'covers':sorted(c.covers)} for c in problem.certificates],
                    'deliveries':{str(b):m.query(problem.query,b) for b in PARAMETERS['budgets']}})
        finally:m.close()
        if (index+1)%25==0:print(f'generic packing {index+1}/{PARAMETERS["packing_cases"]}',flush=True)
    readings={};format_readings={}
    for budget in PARAMETERS['budgets']:
        readings[str(budget)]={};format_readings[str(budget)]={}
        for arm in ARMS:
            relevant=[r for r in rows if r['arm']==arm and r['budget']==budget]
            readings[str(budget)][arm]={'mean_weighted_requirement_coverage':statistics.mean(r['coverage'] for r in relevant),
                'complete_queries':sum(r['complete'] for r in relevant),'queries':len(relevant),
                'mean_budget_used':statistics.mean(r['budget_used'] for r in relevant),
                'query_median_ms':statistics.median(r['query_ms'] for r in relevant)}
            format_readings[str(budget)][arm]={str(fmt):statistics.mean(r['coverage'] for r in relevant if r['format']==fmt)
                                             for fmt in range(PARAMETERS['formats'])}
    renaming=[]
    for index in range(PARAMETERS['renaming_cases']):
        a,pa,_,_=make_case(index,'k',False);b,pb,_,_=make_case(index,'z',False)
        try:
            for budget in PARAMETERS['budgets']:
                ra=solve(pa,budget);rb=solve(pb,budget)
                assert ra['covered']==rb['covered'] and ra['selected']==rb['selected'] and ra['budget_used']==rb['budget_used']
                renaming.append({'case':index,'budget':budget,'identical_structured_result':True})
        finally:a.close();b.close()
    return {'readings':readings,'by_format':format_readings,'details':rows,'exact_diagnostic':exact_rows,
            'duplicate_case_checks':duplicate_checks,'schema_renaming_checks':len(renaming)}


def temporal():
    rng=random.Random(PARAMETERS['seed']+100000);m=Memory();roots={};slots=[];operations=[]
    for entity in range(PARAMETERS['temporal_entities']):
        entity_id=f'entity_{rng.getrandbits(48):012x}'
        for facet in range(PARAMETERS['facets_per_entity']):
            slot=Slot.of(entity_id,f'facet_{facet}',f'role_{entity%3}',{'cond':entity%4})
            slots.append(slot)
            for episode in range(PARAMETERS['episodes_per_facet']):
                at=rng.randrange(10,500);sid='e_'+str(len(roots));received=10+len(roots)
                val=None if rng.random()<.07 else value(rng,episode)
                end=at+rng.randrange(2,30) if rng.random()<.12 else None
                visible=rng.random()>=.06
                root={'slot':slot,'versions':[(received,at,end,encoded(val))],'controls':[],
                      'searchable':visible,'id':sid,'scope':'default'}
                roots[sid]=root
                operations.append(('state',received,root,val))
    for ordinal,root in enumerate(roots.values()):
        if rng.random()<.25:
            received=2000+ordinal;old=root['versions'][0]
            val=value(rng,ordinal);at=old[1]+rng.choice([0,0,2,-2]);end=None if old[2] is None else max(old[2],at+1)
            root['versions'].append((received,at,end,encoded(val)))
            operations.append(('correction',received,root,val))
        if rng.random()<.12:
            received=3000+ordinal;root['controls'].append((received,False));operations.append(('control',received,root,False))
            if rng.random()<.5:
                received=4000+ordinal;root['controls'].append((received,True));operations.append(('control',received,root,True))
    for i,slot in enumerate(slots):operations.append(('plan',1000+i,{'slot':slot,'id':'p_'+str(i)},value(rng,i)))
    tips={};start=time.perf_counter()
    for kind,received,root,val in sorted(operations,key=lambda x:x[1]):
        if kind=='state':
            version=root['versions'][0]
            m.append(root['id'],encoded({'slot':root['slot'].key,'value':val}),assertions={root['slot']:val},
                     effective_at=version[1],recorded_at=received,valid_to=version[2],searchable=root['searchable'])
            tips[root['id']]=root['id']
        elif kind=='plan':m.append(root['id'],encoded({'proposed':val}),assertions={root['slot']:val},kind='plan',recorded_at=received)
        elif kind=='correction':
            version=root['versions'][-1];sid='fix_'+root['id']
            m.correct(sid,tips[root['id']],encoded({'revised':val}),replacements={root['slot']:val},recorded_at=received,
                      effective_at=version[1],valid_to=version[2]);tips[root['id']]=sid
        else:m.set_enabled(('on_' if val else 'off_')+root['id'],tips[root['id']],encoded({'enabled':val}),enabled=val,recorded_at=received)
    write_ms=(time.perf_counter()-start)*1000
    rows=[];counts=defaultdict(int)
    for number in range(PARAMETERS['temporal_queries']):
        slot=rng.choice(slots);at=rng.randrange(0,530);known=rng.randrange(0,4600)
        eligible=[]
        for root in roots.values():
            if root['slot']!=slot or not root['searchable']:continue
            versions=[v for v in root['versions'] if v[0]<=known]
            controls=[v for v in root['controls'] if v[0]<=known]
            if not versions or (controls and not controls[-1][1]):continue
            tip=versions[-1]
            if tip[1]<=at:eligible.append(tip)
        if eligible:
            newest=max(t[1] for t in eligible)
            values=sorted({t[3] for t in eligible if t[1]==newest and (t[2] is None or at<t[2])})
        else:values=[]
        status='unknown' if not values or values==['null'] else 'known' if len(values)==1 else 'conflict'
        query=Query((Need('result',slot),),at,known)
        before=m.db.conn.total_changes;start=time.perf_counter();answer=m.query(query,100000)
        elapsed=(time.perf_counter()-start)*1000
        assert m.db.conn.total_changes==before
        actual=answer['answers']['result'];ok=actual['status']==status
        if status=='known':ok &= encoded(actual['value'])==values[0]
        elif status=='conflict':ok &= {encoded(v) for v in actual['value']}==set(values)
        else:ok &= actual['value'] is None
        if not ok:raise AssertionError({'query':asdict(query),'expected':(status,values),'actual':actual})
        counts[status]+=1
        rows.append({'case':number,'at':at,'known_at':known,'slot':slot.key,'status':status,'correct':bool(ok),
                     'query_ms':elapsed,'budget_used':answer['budget_used']})
    statistics_out=m.statistics();m.close()
    return {'queries':len(rows),'correct':sum(r['correct'] for r in rows),'logical_statuses':dict(counts),
        'input_state_episodes':len(roots),'entities':len({s.entity for s in slots}),'slots':len(slots),'operations':len(operations),'write_total_ms':write_ms,
        'query_median_ms':statistics.median(r['query_ms'] for r in rows),'statistics':statistics_out,'details':rows}


def hive_raw_smoke(root):
    # Genuine unstructured input is kept unconfirmed. This is a compatibility
    # and provenance test of the cold-text fallback, not an end-to-end score
    # for discriminative planning with a secretly supplied oracle schema.
    sys.path.insert(0,str(REPO/'TanPowasd/agm/bench'))
    from hive_retrieval import load_chunks
    root=Path(root).resolve();chunks=load_chunks(root)
    if not chunks:raise ValueError("Hive corpus contains no chunks")
    questions=json.loads((root/'questions/题目_主轮.json').read_text(encoding='utf-8'))+json.loads((root/'questions/题目_干预轮.json').read_text(encoding='utf-8'))
    m=Memory()
    original={}
    for i,c in enumerate(chunks):
        sid=f'chunk_{i:05d}';original[sid]=c['text'];m.append_raw(sid,c['text'],scope='novel',recorded_at=i)
    before=m.db.conn.total_changes;retrieved=0
    for q in questions:
        result=m.search_raw(q['question'],scope='novel',budget=4000)
        assert result['budget_used']<=4000 and result['status']=='evidence_only'
        assert all(h['text']==original[h['id']] for h in result['hits'])
        retrieved+=len(result['hits'])
    assert before==m.db.conn.total_changes
    stats=m.statistics();m.close()
    return {'questions_executed':len(questions),'chunks':len(chunks),'quoted_hits_checked':retrieved,
            'source_integrity':True,'budget_violations':0,'confirmed_claims_inferred':stats['interpreted_claims'],
            'note':'Raw fallback only; no natural-language assertion or query-family extraction was performed; no new algorithm HMB score claimed.'}


def main():
    global OUTPUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT,help='Write a new offline run here')
    parser.add_argument('--hive-root',type=Path,help='Optional local hive-memory-bench checkout; no downloading')
    args=parser.parse_args()
    OUTPUT=args.output.resolve()
    archive=(ROOT/'results').resolve()
    if OUTPUT==archive or archive in OUTPUT.parents:
        parser.error('Archived results are immutable; choose another output directory')
    OUTPUT.mkdir(parents=True,exist_ok=True)
    for key in tuple(os.environ):
        if key.endswith('API_KEY') or key.startswith('LINGSHU_NG_'):os.environ.pop(key)
    dump('parameters.json',PARAMETERS)
    frozen_paths=(ROOT/'discriminative_memory.py',ROOT/'bench_discriminative.py',ROOT/'parameters.json',
                  ROOT/'temporal_facts.py',REPO/'TanPowasd/agm/bench/hive_retrieval.py')
    frozen={os.path.relpath(path,ROOT).replace(os.sep,'/'):digest(path) for path in frozen_paths}
    attempts=[]
    def deny(*a,**k):attempts.append(True);raise RuntimeError('Offline benchmark rejects all networking')
    with patch.object(socket.socket,'connect',deny),patch.object(socket.socket,'connect_ex',deny),patch.object(socket,'create_connection',deny):
        packed=packing();temporal_results=temporal()
        smoke=hive_raw_smoke(args.hive_root) if args.hive_root else {'status':'skipped','reason':'Supply --hive-root for a local raw-interface check'}
    assert not attempts and all(digest(ROOT/path)==value for path,value in frozen.items())
    out={'metadata':{'model_calls':0,'network_attempts':len(attempts),'key_required':False,'frozen_hashes':frozen,
        'parameters':PARAMETERS,'budget_unit':'original Unicode characters including headers, links and qualifiers',
        'shared_input':'All planners receive the same confirmed assertions, bound question frames, certificate candidates and mandatory conflict policy.',
        'notes':['Synthetic tasks use unseen random identifiers, generic JSON values and five text formats; no domain word rules.',
                 'This isolates structured evidence selection; no arbitrary-language understanding or semantic extraction accuracy is implied.',
                 'SQL is straightforward requested-field certificate assembly, not an optimal database query planner.',
                 'AGM/RRF are rankings adapted to this shared certificate problem, not their official unstructured benchmark implementations.',
                 'Exhaustive search is a small-instance upper bound, not a scalable production method.',
                 'No tuning/search of parameters from the scores in this run.']},
        'packing':packed,'temporal':temporal_results,'hive_raw_smoke':smoke}
    dump('readings.json',out)
    print(json.dumps({'packing':packed['readings'],'temporal':{k:v for k,v in temporal_results.items() if k!='details'},
                      'exact_cases':len(packed['exact_diagnostic']),'schema_renaming_checks':packed['schema_renaming_checks'],
                      'hive_raw_smoke':smoke},ensure_ascii=False,indent=2))


if __name__=='__main__':
    if os.environ.get('PYTHONHASHSEED')!='0':
        raise SystemExit(subprocess.call([sys.executable,'-B','-X','utf8',__file__,*sys.argv[1:]],env={**os.environ,'PYTHONHASHSEED':'0'}))
    main()
