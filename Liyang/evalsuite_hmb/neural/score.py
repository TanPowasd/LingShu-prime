import sys, json, statistics
sys.path.insert(0,"/workspace/work/hmb_lab")
from lab import *
idx={c["id"]:i for i,c in enumerate(CHUNKS)}
for f in sys.argv[1:]:
    D=json.load(open(f)); R=D["recall"]
    rank={q:[idx[h["chunk"]] for h in v["hits"] if h.get("chunk") in idx] for q,v in R.items()}
    ms=statistics.median(D["query_ms"]["recall"])
    o=report(f.split("retr_")[-1][:-5], rank)
    print("   query median ms", round(ms,1), "write_sec", D["write_sec"])
