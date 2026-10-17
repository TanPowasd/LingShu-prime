# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""可复用保留集守卫（PREREG_reuse.md）。
R1 训练侧与保留侧接近 ⇒ 答训练值、不耗预算；R2 差距大 ⇒ 答带噪保留值、预算 −1；R3 预算用完 ⇒ 拒答；
R4 同一问题再问 ⇒ 原答案、不再耗预算；R5 超阈答案带噪（≠ 保留真值）；R6 账本被改 ⇒ 加载即拒；R7 阈值状态跨进程保持。
--mutate：M1 去噪（R5）、M2 不扣预算（R3）、M3 不查缓存（R4）、M4 总答保留值（R1）、M5 不验哈希链（R6）、M6 不存阈值（R7）。"""
import importlib, json, pathlib, random, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import reuse  # noqa: E402

P = {"T": 0.01, "sigma": 0.002, "budget": 2}


def L(d, seed=1, state=None):
    return reuse.Ledger(pathlib.Path(d) / "l.jsonl", rng=random.Random(seed), params=P, state=state)


def checks():
    ok = []
    with tempfile.TemporaryDirectory() as d:
        a = L(d).ask("x", "k1", 0.010, 0.0101)
        ok.append(("R1 接近 ⇒ 答训练值、不耗预算", a["answer"] == 0.010 and not a["over"] and L(d).left("x") == 2, str(a)))
        b = L(d).ask("x", "k2", 0.000, 0.200)
        ok.append(("R2 差距大 ⇒ 答带噪保留值、预算 −1", b["over"] and abs(b["answer"] - 0.2) < 0.05 and L(d).left("x") == 1, str(b)))
        ok.append(("R5 超阈答案带噪", b["answer"] != 0.2, str(b)))
        c = L(d).ask("x", "k2", 0.000, 0.200)
        ok.append(("R4 同一问题再问 ⇒ 原答案、不耗预算", c.get("cached") and c["answer"] == b["answer"] and L(d).left("x") == 1))
        L(d).ask("x", "k3", 0.000, -0.300)
        try:
            L(d).ask("x", "k4", 0.000, 0.300); ex = False
        except reuse.Exhausted:
            ex = True
        ok.append(("R3 预算用完 ⇒ 拒答", ex and L(d).left("y") == 2))
        f = pathlib.Path(d) / "l.jsonl"
        lines = f.read_text(encoding="utf-8").splitlines()
        r = json.loads(lines[1]); r["answer"] = 0.0; lines[1] = json.dumps(r, ensure_ascii=False, sort_keys=True)
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            L(d); tp = False
        except reuse.Tampered:
            tp = True
        ok.append(("R6 账本被改 ⇒ 加载即拒", tp))
    with tempfile.TemporaryDirectory() as d:
        st = pathlib.Path(d) / "s.json"
        L(d, 3, st).ask("z", "k1", 0.0, 0.0)
        t1 = json.loads(st.read_text()).get("z") if st.exists() else None
        L(d, 4, st).ask("z", "k2", 0.0, 0.0)
        t2 = json.loads(st.read_text()).get("z") if st.exists() else None
        ok.append(("R7 两次超阈之间阈值跨进程不变", t1 is not None and t1 == t2, f"{t1} {t2}"))
    return ok


def run():
    r = checks()
    return r, [c[0] for c in r if not c[1]]


def m_nonoise():
    reuse._lap = lambda rng, b: 0.0


def m_nobudget():
    reuse.Ledger.left = lambda self, s: self.p["budget"]


def m_nocache():
    o = reuse.Ledger.ask
    def f(self, s, key, t, h, meta=None):
        return o(self, s, key + str(len(self.rows)), t, h, meta)
    reuse.Ledger.ask = f


def m_alwayshold():
    o = reuse.Ledger.ask
    def f(self, s, key, t, h, meta=None):
        return o(self, s, key, t - 1.0 if h >= t else t + 1.0, h, meta)
    reuse.Ledger.ask = f


def m_nochain():
    o = reuse.Ledger.__init__
    def f(self, path=reuse.LEDGER, rng=None, params=None, state=None):
        p = pathlib.Path(path)
        txt = p.read_text(encoding="utf-8") if p.exists() else None
        if txt is not None:
            p.write_text("", encoding="utf-8")
        o(self, path, rng, params, state)
        if txt is not None:
            p.write_text(txt, encoding="utf-8")
            self.rows = [json.loads(x) for x in txt.splitlines() if x.strip()]
    reuse.Ledger.__init__ = f


def m_nostate():
    o = reuse.Ledger.__init__
    def f(self, path=reuse.LEDGER, rng=None, params=None, state=None):
        o(self, path, rng, params, None)
    reuse.Ledger.__init__ = f


MUTS = {"M1 去噪": (m_nonoise, "R5"), "M2 不扣预算": (m_nobudget, "R3"), "M3 不查缓存": (m_nocache, "R4"),
        "M4 总答保留值": (m_alwayshold, "R1"), "M5 不验哈希链": (m_nochain, "R6"), "M6 不存阈值": (m_nostate, "R7")}

if __name__ == "__main__":
    if "--mutate" in sys.argv:
        res = []
        for name, (f, tid) in MUTS.items():
            importlib.reload(reuse); f()
            try:
                _, bad = run(); k = any(b.startswith(tid + " ") for b in bad)
            except (reuse.Exhausted, reuse.Tampered):   # 意外拒答也是变红
                k = True
            res.append(f"{name.split()[0]} {'killed' if k else 'SURVIVED'}")
        print(" | ".join(res)); sys.exit(0 if all("killed" in x for x in res) else 1)
    r, bad = run()
    for c in r:
        print("PASS" if c[1] else "FAIL", c[0], *(c[2:] if not c[1] else []))
    print("RED:" + ",".join(bad)); sys.exit(1 if bad else 0)
