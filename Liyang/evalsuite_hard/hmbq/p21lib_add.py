def load_vec(tag):
    z = np.load(f"/tmp/hmbq_vec_{tag}.npz"); return z["C"], z["Q"]
def reserve(Rl, Dl, r, n=10):
    # 词面前 n-r + 向量序里不在其中的前 r
    keep = list(Rl[:n - r]); add = [i for i in Dl if i not in keep][:r]
    return keep + add
def interleave(Rl, Dl, n=10, pat="LD"):
    out = []; a = iter(Rl); b = iter(Dl); k = 0
    while len(out) < n:
        src = a if pat[k % len(pat)] == "L" else b; k += 1
        for i in src:
            if i not in out: out.append(i); break
    return out
