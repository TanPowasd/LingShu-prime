# -*- coding: utf-8 -*-
"""v7.1 身份核对：逐题比较两次运行的排序名单。 python v71_ident.py <a.json> <b.json> [key]"""
import json, sys
a, b = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
k = sys.argv[3] if len(sys.argv) > 3 else None
if k:
    a, b = a[k], b[k]
ra, rb = a.get("rank", a), b.get("rank", b)
qs = sorted(set(ra) | set(rb))
same = sum(1 for q in qs if ra.get(q) == rb.get(q))
print(f"{same}/{len(qs)} identical", "" if same == len(qs) else [q for q in qs if ra.get(q) != rb.get(q)][:10])
