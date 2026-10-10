# -*- coding: utf-8 -*-
"""不经 harness 的探针/自测：装 → 只写入指定会话 → 召回指定卡 → 不卸载（便于看库）。
用途：① 测单会话写入的 LLM 调用数/token/耗时，外推全量 16 份语料的成本与时长（可行性）；② 适配器冒烟。
用法：python3 plugins/everos/selftest.py --files 公式符号复制乱码原因.md --cards C-xxx,C-yyy --out runs/everos_probe
"""
import argparse, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from harness import examB  # noqa
from harness.recorder import Recorder, render_timeline  # noqa
from adapter import EverOS  # noqa

ap = argparse.ArgumentParser()
ap.add_argument("--files", required=True); ap.add_argument("--cards", default="")
ap.add_argument("--out", default=os.path.join(ROOT, "runs/everos_probe")); ap.add_argument("--base", default=os.path.join(ROOT, "runs/everos/probe_sbx"))
ap.add_argument("--port", type=int, default=18790); ap.add_argument("--proxy-port", type=int, default=18791)
a = ap.parse_args()
import shutil
if os.path.exists(a.base): shutil.rmtree(a.base)
rec = Recorder(os.path.join(a.out, "recording.jsonl"), os.path.basename(a.out), resume=os.path.exists(os.path.join(a.out, "recording.jsonl")))
p = EverOS(base=a.base, port=a.port, proxy_port=a.proxy_port, sessions_limit=a.files.split(","))
ir = p.install(rec); rec.event("plugin.install.result", ok=ir.ok, steps=ir.steps, errors=ir.errors); print("install", ir)
sess = examB.all_sessions()
t0 = time.time(); p.ingest(sess, rec); print("ingest", round(time.time() - t0, 1), p.llm_totals(), flush=True)
cards = {c["id"]: c for c in examB.load_cards()}
for cid in [x for x in a.cards.split(",") if x]:
    c = cards[cid]; q = examB.query_of(c)
    items = p.recall(q, 5, rec)
    kept, audit = examB.leak_filter([{"text": i["text"], "source": i["source"]} for i in items], c)
    rec.event("probe.recall", qid=cid, sources=[i["source"] for i in items], kinds=[i.get("kind") for i in items], kept=len(kept), audit=audit)
    print(cid, "answer line", c["answer"]["human"]["line"], [(i.get("kind"), i["source"], len(i["text"])) for i in items], "kept", len(kept))
    for i in items[:2]: print("   ", i["text"][:300].replace("\n", " "))
json.dump({"llm": p.llm_totals(), "flush_s": p.stats["flush"], "search_s": p.stats["search"]}, open(os.path.join(a.out, "probe_stats.json"), "w"), ensure_ascii=False, indent=1)
rec.close(); render_timeline(os.path.join(a.out, "recording.jsonl"), os.path.join(a.out, "timeline.md"))
print("done")
