"""零模型召回诊断：各检索臂材料里是否含金标版本段（doc#at_seq），按题型、测试集。"""
import json, sys, collections
from pathlib import Path
R = Path(sys.argv[1]); arms = sys.argv[2].split(',')
K = json.loads((R / 'data' / 'keys.json').read_text(encoding='utf-8'))
DEV = {'A1', 'B1'}
for arm in arms:
    st = collections.defaultdict(lambda: [0, 0]); n = []
    for q in K:
        if q['doc_id'] in DEV:
            continue
        m = json.loads((R / 'runs' / f'chain_{arm}' / 'retrieval' / f"{q['qid']}.json").read_text(encoding='utf-8'))['material']
        n.append(len(m)); s = q['answer'].get('at_seq')
        if s is None:
            continue
        st[q['type']][0] += f"{q['doc']}#{s}" in {x['cid'] for x in m}; st[q['type']][1] += 1
    tot = [sum(v[0] for v in st.values()), sum(v[1] for v in st.values())]
    print(f"{arm:10s}", ' '.join(f"{k}{v[0]}/{v[1]}" for k, v in st.items()), f"合计{tot[0]}/{tot[1]} 均段{sum(n)/len(n):.1f}")
