from lab import *
import numpy as np
exec(open("fuse.py").read().split("report(\"bm25 raw\"")[0])
for span in (1,2,3):
  for pen in (0.3,0.5):
    report(f"bm25uni +adj s{span} p{pen}", adj_div(B,span,pen))
    report(f"bm25raw +adj s{span} p{pen}", adj_div(B2,span,pen))
