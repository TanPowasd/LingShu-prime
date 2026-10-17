# SPDX-License-Identifier: LicenseRef-TanPowasd-Proprietary
# -*- coding: utf-8 -*-
"""可复用保留集：Thresholdout（Dwork, Feldman, Hardt, Pitassi, Reingold, Roth 2015, Science「The reusable holdout」）。
PREREG_reuse.md。零模型、标准库。

问的永远是一个数：某臂相对基线的每题平均差 Δ = mean(arm[metric] − base[metric])。
  t = 训练侧（dev）的 Δ，h = 保留侧的 Δ。
  若 |h − t| ≤ T̂ + Lap(4σ)：答 t（保留集没被「问」到，不耗预算）；
  否则：预算 −1，答 h + Lap(σ)，并重抽阈值 T̂ = T + Lap(2σ)。预算用完 ⇒ 拒答（fail-closed，抛 Exhausted）。
白箱边界：机制、参数、每次问答都公开在账本里；只有噪声本身不记录——记下噪声就等于公开 h，复用保证随之失效。
同一问题（同集、同臂、同基线、同指标、同输入文件哈希）再问 ⇒ 原样返回账本里的答案，不再抽噪声、不再耗预算。
账本 results/reuse_ledger.jsonl 只追加，逐行哈希链；被改动 ⇒ 加载即抛 Tampered。

纪律（推断：机制无法替人执行）：保留侧的逐题结果只交给本脚本读，分析者不打开、不打印。

  python -X utf8 reuse.py --set kmb --arm DGC3a --base TE --train <dev.json> --hold <hold.json>
  python -X utf8 reuse.py --set tmd --arm DGC3a --base TE --md5 <tmd.json>     # 同一文件按 md5(qid)%2：0=训练、1=保留
"""
import argparse, hashlib, json, math, os, pathlib, random, sys

HERE = pathlib.Path(__file__).resolve().parent
LEDGER = HERE / "results" / "reuse_ledger.jsonl"
PARAMS = {"T": 0.01, "sigma": 0.002, "budget": 8}   # PREREG_reuse.md；按集独立计预算
# 带噪阈值 T̂ 须在两次「超阈」之间保持不变（稀疏向量技术的前提），故跨进程存于仓外秘密状态文件，不入库、不打开。
STATE = pathlib.Path(os.environ.get("REUSE_STATE", str(pathlib.Path.home() / ".reuse_state.json")))


class Exhausted(RuntimeError):
    pass


class Tampered(RuntimeError):
    pass


def _lap(rng, b):
    u = rng.random() - 0.5
    return -b * math.copysign(1.0, u) * math.log(1 - 2 * abs(u))


def _h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class Ledger:
    def __init__(self, path=LEDGER, rng=None, params=None, state=None):
        self.path = pathlib.Path(path)
        self.state = pathlib.Path(state) if state else None
        self.rng = rng or random.SystemRandom()
        self.p = dict(params or PARAMS)
        self.rows = []
        self._thr = json.loads(self.state.read_text()) if self.state and self.state.exists() else {}
        if self.path.exists():
            prev = "0" * 64
            for ln in self.path.read_text(encoding="utf-8").splitlines():
                if not ln.strip():
                    continue
                r = json.loads(ln)
                body = {k: v for k, v in r.items() if k != "chain"}
                if r.get("prev") != prev or r.get("chain") != _h(prev + json.dumps(body, sort_keys=True, ensure_ascii=False)):
                    raise Tampered(f"账本第 {len(self.rows) + 1} 行哈希链断裂")
                prev = r["chain"]
                self.rows.append(r)

    def left(self, s):
        return self.p["budget"] - sum(1 for r in self.rows if r["set"] == s and r["over"])

    def _append(self, body):
        prev = self.rows[-1]["chain"] if self.rows else "0" * 64
        body = dict(body, prev=prev)
        body["chain"] = _h(prev + json.dumps(body, sort_keys=True, ensure_ascii=False))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n")
        self.rows.append(body)
        return body

    def ask(self, s, key, t, h, meta=None):
        """key：问题身份（含输入哈希）。返回账本行。"""
        for r in self.rows:
            if r["set"] == s and r["key"] == key:
                return dict(r, cached=True)
        if self.left(s) <= 0:
            raise Exhausted(f"{s} 预算已用完（{self.p['budget']}）")
        sg = self.p["sigma"]
        if s not in self._thr:
            self._thr[s] = self.p["T"] + _lap(self.rng, 2 * sg)
        over = abs(h - t) > self._thr[s] + _lap(self.rng, 4 * sg)
        if over:
            ans = h + _lap(self.rng, sg)
            self._thr[s] = self.p["T"] + _lap(self.rng, 2 * sg)
        else:
            ans = t
        if self.state:
            self.state.write_text(json.dumps(self._thr))
        return self._append({"set": s, "key": key, "train": round(t, 6), "answer": round(ans, 6), "over": over,
                             "left": self.left(s) - (1 if over else 0), "params": self.p, **(meta or {})})


def delta(per, arm, base, metric, keep=None):
    v = [p["arms"][arm][metric] - p["arms"][base][metric] for p in per if keep is None or keep(p["qid"])]
    return sum(v) / len(v) if v else 0.0, len(v)


def _md5(q):
    return int(hashlib.md5(q.encode("utf-8")).hexdigest(), 16) % 2


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True); ap.add_argument("--arm", required=True); ap.add_argument("--base", default="TE")
    ap.add_argument("--metric", default="r@10"); ap.add_argument("--train"); ap.add_argument("--hold"); ap.add_argument("--md5")
    ap.add_argument("--ledger", default=str(LEDGER))
    a = ap.parse_args(argv)
    if a.md5:
        raw = open(a.md5, "rb").read(); per = json.loads(raw)["per"]
        t, nt = delta(per, a.arm, a.base, a.metric, lambda q: _md5(q) == 0)
        h, nh = delta(per, a.arm, a.base, a.metric, lambda q: _md5(q) == 1)
        fh = hashlib.sha256(raw).hexdigest()
    else:
        rt, rh = open(a.train, "rb").read(), open(a.hold, "rb").read()
        t, nt = delta(json.loads(rt)["per"], a.arm, a.base, a.metric)
        h, nh = delta(json.loads(rh)["per"], a.arm, a.base, a.metric)
        fh = hashlib.sha256(rt + rh).hexdigest()
    key = _h(f"{a.arm}|{a.base}|{a.metric}|{fh}")
    L = Ledger(a.ledger, state=STATE)
    r = L.ask(a.set, key, t, h, {"arm": a.arm, "base": a.base, "metric": a.metric, "n_train": nt, "n_hold": nh})
    print(json.dumps({k: r[k] for k in ("set", "arm", "base", "metric", "train", "answer", "over", "left") if k in r}
                     | {"cached": r.get("cached", False)}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (Exhausted, Tampered) as e:
        print("REFUSED:", e); sys.exit(2)
