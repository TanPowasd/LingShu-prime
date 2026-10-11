# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
"""零 key 验证“章级取材”假设：hive 主轮 92 题证据句召回（8000 字预算），对比 BM25、旧 AGM、TriCue v3/v1.1 与不同块大小。用法：python hive_granularity.py（路径写死为项目根下 hive-memory-bench）"""
import sys,pathlib,json,collections
sys.path[:0]=[str(pathlib.Path(__file__).parent), str(pathlib.Path(__file__).parent.parent/'bench')]
import hive_retrieval as HR, tricue as T
root=pathlib.Path('/workspace/projects/c5e24339-1a72-4448-88c0-70df0ede0917/hive-memory-bench')
chunks,cards=HR.load_chunks(root),HR.load_cards(root)
B=8000
bm=HR.BM25(chunks); agm=HR.AGM(chunks,bm)
print('chunks',len(chunks))
res={}
res['BM25']=HR.evaluate(cards,lambda c:HR.take(sorted(range(len(chunks)),key=lambda i,s=bm.scores(c['question']):-s[i]),chunks,B))
res['AGM旧']=HR.evaluate(cards,lambda c:HR.take(agm.rank(c['question']),chunks,B))
def tri(mem_factory, unit):
    mem=mem_factory()
    if unit=='chunk':
        for c in chunks: mem.add_turn('doc',c['text'])
    else:  # chapter = one turn, tricue re-splits at its chunk size
        by=collections.OrderedDict()
        for c in chunks: by.setdefault(c['cid'],[]).append(c['text'])
        for cid,ts in by.items(): mem.add_turn('doc',''.join(ts))
    print(unit,'tricue chunks',mem.N, flush=True)
    return lambda c:'|'.join(T.norm(h.text) for h in sorted(mem.retrieve(c['question'],B),key=lambda h:h.id))
res['v3(块写入)']=HR.evaluate(cards,tri(T.TriCueMemory.v3,'chunk'))
res['v1.1(块写入)']=HR.evaluate(cards,tri(T.TriCueMemory,'chunk'))
for cs in (160,300,600,1200):
    res[f'v3(章写入,{cs})']=HR.evaluate(cards,tri(lambda cs=cs:T.TriCueMemory.v3(chunk=cs),'chapter'))
for k,v in res.items(): print(k,{a:b for a,b in v.items() if a!='_n'})
json.dump(res,open('results/hive_keyed_v3_20261011/granularity_zero_key.json','w'),ensure_ascii=False,indent=1)
