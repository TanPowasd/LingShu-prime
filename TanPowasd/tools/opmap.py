"""dsh-memory md_cg: map each cg op in _cg_dispatch to its handler and the md_cg modules it uses.
Usage: python opmap.py <dsh-memory>/md_cg
"""
import ast, os, re, sys
root = sys.argv[1] if len(sys.argv) > 1 else "."
os.chdir(root)
mods = {f[:-3] for f in os.listdir(".") if f.endswith(".py") and not f.startswith(("test_", "bench"))}
src = open("mcp_server.py", encoding="utf-8").read(); t = ast.parse(src)
fns = {n.name: n for n in t.body if isinstance(n, ast.FunctionDef)}
alias = {}
for n in t.body:
    if isinstance(n, ast.ImportFrom) and n.level:
        for a in n.names:
            if a.name in mods: alias[a.asname or a.name] = a.name
            elif n.module in mods: alias[a.asname or a.name] = n.module
def scan(fn, seen, depth=0):
    used = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.ImportFrom) and n.level:
            if n.module in mods: used.add(n.module)
            used |= {a.name for a in n.names if a.name in mods}
        elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in alias:
            used.add(alias[n.value.id])
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in fns
              and n.func.id.startswith("_") and n.func.id not in seen and depth < 2):
            seen.add(n.func.id); used |= scan(fns[n.func.id], seen, depth + 1)
    return used
seg = ast.get_source_segment(src, fns["_cg_dispatch"])
ops = re.findall(r'if op == "([a-z_]+)":\s*\n\s*return (_[a-z_]+)\(', seg)
allops = re.findall(r'if op == "([a-z_]+)"', seg)
for op, f in ops:
    u = scan(fns[f], set()) - {"mcp_server", "fsutil", "security"} if f in fns else set()
    print(f"{op:14s} {f:22s} {','.join(sorted(u)) or '(cg methods only)'}")
print(f"\nhandler-delegated ops: {len(ops)} / op branches in _cg_dispatch: {len(set(allops))}")
