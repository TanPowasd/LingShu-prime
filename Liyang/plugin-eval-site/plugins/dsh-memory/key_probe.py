# -*- coding: utf-8 -*-
"""主密钥分居探针：会话摄取节点缺省 private 且加密；主密钥在 ~/.mdcg（aux 根），与 MDCG_ROOT 分居。
拿掉 ~/.mdcg 下除令牌库外的文件后重启，看召回。用法：python3 key_probe.py <录像目录>"""
import sys,os,json,shutil
sys.path.insert(0,'.')
from adapter import DshMemory
from selftest import load_sessions
from rec_local import Rec
rec=Rec(sys.argv[1]+'/key_probe.jsonl','主密钥分居探针', run='dsh_key')
pl=DshMemory(base='/tmp/pes-dshm-key'); print(pl.install(rec))
ss=[s for s in load_sessions() if s['session_id']=='公式符号复制乱码原因.md']
pl.ingest(ss,rec)
q='公式符号复制后保存到md里乱码'
h=pl.recall(q,5,rec); print('before', len(h), [x['text'][-80:].replace('\n',' ') for x in h[:1]])
pl.mcp.close()
shutil.move(pl.home+'/.mdcg', '/tmp/pes-dshm-key/mdcg_moved')
os.makedirs(pl.home+'/.mdcg'); shutil.copy('/tmp/pes-dshm-key/mdcg_moved/_tokens.json', pl.home+'/.mdcg/_tokens.json')  # 令牌库保留，只拿掉 master.key 等
try:
    pl._start(rec); h=pl.recall(q,5,rec); print('after(no master.key)', len(h), [x['text'][-120:].replace('\n',' ') for x in h[:2]])
except Exception as e: print('ERR',e)
rec.close()

from rec_local import render_md
render_md(sys.argv[1]+'/key_probe.jsonl', sys.argv[1]+'/key_probe_时间轴.md', '主密钥分居探针 · 录像时间轴')
